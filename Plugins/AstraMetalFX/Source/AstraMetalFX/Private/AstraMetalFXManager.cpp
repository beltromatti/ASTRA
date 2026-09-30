// Copyright ASTRA.

#include "AstraMetalFXManager.h"
#include "AstraMetalFXViewExtension.h"
#include "Async/Async.h"
#include "HAL/IConsoleManager.h"
#include "HAL/PlatformProcess.h"
#include "HAL/PlatformTime.h"
#include "RHI.h"
#include "RenderingThread.h"
#include "SceneViewExtension.h"

DEFINE_LOG_CATEGORY(LogAstraMetalFX);
DEFINE_STAT(STAT_AstraMetalFXGpuLast);
DEFINE_STAT(STAT_AstraMetalFXGpuAverage);
DEFINE_STAT(STAT_AstraMetalFXFrames);

static TAutoConsoleVariable<int32> CVarAstraMetalFX(
	TEXT("r.AstraMetalFX"),
	1,
	TEXT("Apple MetalFX temporal upscaler instead of TSR for the game view (Mac, Metal RHI).\n")
	TEXT("  0: TSR\n")
	TEXT("  1: MetalFX (default); TSR whenever MetalFX cannot run (other GPU or platform, a failure: see the log)\n")
	TEXT("Takes effect on the next frame; the temporal history restarts on every switch."),
	ECVF_Default);

static TAutoConsoleVariable<int32> CVarAstraMetalFXDebug(
	TEXT("r.AstraMetalFX.Debug"),
	0,
	TEXT("Shows what MetalFX is fed instead of the upscaled image.\n")
	TEXT("  0: off\n")
	TEXT("  1: motion vectors (hue = direction, brightness = length)\n")
	TEXT("  2: pixels that take their motion from the velocity buffer (moving objects) in red, the rest is camera motion"),
	ECVF_RenderThreadSafe);

static TAutoConsoleVariable<float> CVarAstraMetalFXLogInterval(
	TEXT("r.AstraMetalFX.LogInterval"),
	0.0f,
	TEXT("Seconds between log lines with the GPU cost of the MetalFX work (0: never). See also stat AstraMetalFX."),
	ECVF_RenderThreadSafe);

static FAutoConsoleCommandWithOutputDevice GAstraMetalFXStatusCommand(
	TEXT("astra.metalfx.status"),
	TEXT("Prints whether the MetalFX upscaler is running, why not, and what it costs on the GPU."),
	FConsoleCommandWithOutputDeviceDelegate::CreateLambda([](FOutputDevice& Ar)
	{
		const FAstraMetalFXModule* Module = FAstraMetalFXModule::Get();
		if (!Module)
		{
			Ar.Log(TEXT("MetalFX: the plugin is not loaded on this platform (TSR)"));
			return;
		}
		const FAstraMetalFXStatus Status = Module->GetStatus();
		Ar.Logf(TEXT("MetalFX: %s | supported %s, r.AstraMetalFX %s%s%s"),
			Status.bActive ? TEXT("ACTIVE") : TEXT("not active (TSR)"),
			Status.bSupported ? TEXT("yes") : TEXT("no"), Status.bEnabled ? TEXT("on") : TEXT("off"),
			Status.Reason.IsEmpty() ? TEXT("") : TEXT(" | why not: "), *Status.Reason);
		Ar.Logf(TEXT("MetalFX: output %dx%d, GPU %.3f ms last, %.3f ms average over %llu frames, %llu errors"),
			Status.OutputSize.X, Status.OutputSize.Y, Status.LastGpuMs, Status.AverageGpuMs, Status.FramesUpscaled, Status.Errors);
	}));

FAstraMetalFXManager& FAstraMetalFXManager::Get()
{
	static FAstraMetalFXManager Instance;
	return Instance;
}

bool FAstraMetalFXManager::IsEnabledByCVar() const
{
	return CVarAstraMetalFX.GetValueOnGameThread() != 0;
}

bool FAstraMetalFXManager::IsEngineUpscalerSwitchOn() const
{
	static IConsoleVariable* const EngineSwitch = IConsoleManager::Get().FindConsoleVariable(TEXT("r.TemporalAA.Upscaler"));
	return EngineSwitch == nullptr || EngineSwitch->GetInt() != 0;
}

AstraMetalFX::EDebugView FAstraMetalFXManager::GetDebugView() const
{
	return (AstraMetalFX::EDebugView)FMath::Clamp(CVarAstraMetalFXDebug.GetValueOnRenderThread(), 0, 2);
}

void FAstraMetalFXManager::Startup()
{
	if (bStarted)
	{
		return;
	}
	bStarted = true;

#if PLATFORM_MAC
	if (!GDynamicRHI || GDynamicRHI->GetInterfaceType() != ERHIInterfaceType::Metal)
	{
		UnsupportedReason = TEXT("the RHI is not Metal");
		UE_LOG(LogAstraMetalFX, Log, TEXT("MetalFX upscaler off: %s (TSR stays)"), *UnsupportedReason);
		return;
	}
	UnsupportedReason = AstraMetalFX::QueryUnsupportedReason();
	if (!UnsupportedReason.IsEmpty())
	{
		UE_LOG(LogAstraMetalFX, Warning, TEXT("MetalFX upscaler off: %s (TSR stays)"), *UnsupportedReason);
		return;
	}

	bSupported = true;
	ViewExtension = FSceneViewExtensions::NewExtension<FAstraMetalFXViewExtension>();
	UE_LOG(LogAstraMetalFX, Log, TEXT("MetalFX upscaler ready: r.AstraMetalFX is %s"), IsEnabledByCVar() ? TEXT("on") : TEXT("off"));

	// The very first MetalFX scaler of a machine compiles its pipelines for seconds (later ones take a fraction of a second):
	// start now, off the game thread, for the usual window size. The game view keeps TSR until the real size is ready.
	if (IsEnabledByCVar())
	{
		bool bStartBuild = false;
		{
			FScopeLock ScopeLock(&Lock);
			if (!bBuilding)
			{
				bBuilding = bStartBuild = true;
			}
		}
		if (bStartBuild)
		{
			StartBuild(FIntPoint(1600, 900));
		}
	}
#else
	UnsupportedReason = TEXT("MetalFX is Mac only");
#endif
}

void FAstraMetalFXManager::Shutdown()
{
	if (!bStarted)
	{
		return;
	}
	bStarted = false;
	bDisabled.store(true);
	ViewExtension.Reset();

#if PLATFORM_MAC
	// Nothing of ours may be left running when the module's code goes away: builds, the render thread's frames, the Metal
	// submission thread's callbacks and the command buffers on the GPU.
	const double Start = FPlatformTime::Seconds();
	while (BuildsInFlight.load() > 0 && FPlatformTime::Seconds() - Start < 10.0)
	{
		FPlatformProcess::Sleep(0.01f);
	}
	if (bSupported)
	{
		FlushRenderingCommands();
		AstraMetalFX::DrainSubmissionQueue();
		AstraMetalFX::WaitForCommandBuffers(3.0);
	}
#endif
	{
		FScopeLock ScopeLock(&Lock);
		Current.Reset();
	}
#if PLATFORM_MAC
	AstraMetalFX::ReleaseSharedResources();
#endif
}

void FAstraMetalFXManager::DisableForSession(const FString& Reason)
{
	bool bFirst = false;
	{
		FScopeLock ScopeLock(&Lock);
		if (DisabledReason.IsEmpty())
		{
			DisabledReason = Reason;
			bFirst = true;
		}
	}
	bDisabled.store(true);
	if (bFirst)
	{
		UE_LOG(LogAstraMetalFX, Error, TEXT("MetalFX disabled for this session, the game view uses TSR: %s"), *Reason);
	}
}

FAstraMetalFXManager::FContextPtr FAstraMetalFXManager::AcquireContext(FIntPoint OutputSize)
{
	// A tiny or empty view (a window being dragged, minimised) is a transient state, not a reason to give MetalFX up.
	if (!IsAvailable() || OutputSize.X < 64 || OutputSize.Y < 64)
	{
		return nullptr;
	}

	FContextPtr Result;
	bool bStartBuild = false;
	{
		FScopeLock ScopeLock(&Lock);
		if (Current.IsValid() && Current->GetOutputSize() == OutputSize)
		{
			Result = Current;
		}
		else if (!bBuilding)
		{
			bBuilding = bStartBuild = true;
		}
	}

	if (Result.IsValid() && !Result->IsHealthy())
	{
		DisableForSession(Result->GetFailureReason());
		return nullptr;
	}
	if (bStartBuild)
	{
		StartBuild(OutputSize);
	}
	return Result;
}

void FAstraMetalFXManager::StartBuild(FIntPoint OutputSize)
{
	BuildsInFlight.fetch_add(1);
	UE_LOG(LogAstraMetalFX, Log, TEXT("building the MetalFX scaler for an output of %dx%d (the game view uses TSR until it is ready)"), OutputSize.X, OutputSize.Y);

	Async(EAsyncExecution::ThreadPool, [this, OutputSize]()
	{
		FString Error;
		const double Start = FPlatformTime::Seconds();
		FContextPtr Built = AstraMetalFX::CreateScalerContext(OutputSize, Error);
		const double Seconds = FPlatformTime::Seconds() - Start;
		{
			FScopeLock ScopeLock(&Lock);
			bBuilding = false;
			if (Built.IsValid() && !bDisabled.load())
			{
				Current = Built;
			}
		}
		if (Built.IsValid())
		{
			UE_LOG(LogAstraMetalFX, Log, TEXT("the MetalFX scaler for %dx%d was built in %.2f s"), OutputSize.X, OutputSize.Y, Seconds);
		}
		else
		{
			DisableForSession(Error.IsEmpty() ? TEXT("the MetalFX scaler could not be built") : Error);
		}
		BuildsInFlight.fetch_sub(1);
	});
}

void FAstraMetalFXManager::PublishFrame(const FContextPtr& Context)
{
	const AstraMetalFX::FGpuTimings Timings = Context->GetTimings();
	SET_FLOAT_STAT(STAT_AstraMetalFXGpuLast, Timings.LastMs);
	SET_FLOAT_STAT(STAT_AstraMetalFXGpuAverage, Timings.AverageMs);
	SET_DWORD_STAT(STAT_AstraMetalFXFrames, (uint32)FMath::Min<uint64>(Timings.Frames, MAX_uint32));

	const double Now = FPlatformTime::Seconds();
	const float Interval = CVarAstraMetalFXLogInterval.GetValueOnRenderThread();
	bool bLog = false;
	{
		FScopeLock ScopeLock(&Lock);
		LastActiveTime = Now;
		if (Interval > 0.0f && Now - LastLogTime >= Interval)
		{
			LastLogTime = Now;
			bLog = true;
		}
	}
	if (bLog)
	{
		UE_LOG(LogAstraMetalFX, Log, TEXT("MetalFX %dx%d: GPU %.3f ms (last), %.3f ms (average), %llu frames, %llu errors"),
			Context->GetOutputSize().X, Context->GetOutputSize().Y, Timings.LastMs, Timings.AverageMs, Timings.Frames, Timings.Errors);
	}
}

FAstraMetalFXStatus FAstraMetalFXManager::GetStatus() const
{
	FAstraMetalFXStatus Status;
	Status.bSupported = bSupported;
	Status.bEnabled = CVarAstraMetalFX.GetValueOnAnyThread() != 0;

	FScopeLock ScopeLock(&Lock);
	Status.bActive = Current.IsValid() && (FPlatformTime::Seconds() - LastActiveTime) < 0.5;
	if (!bSupported)
	{
		Status.Reason = UnsupportedReason;
	}
	else if (!DisabledReason.IsEmpty())
	{
		Status.Reason = DisabledReason;
	}
	else if (!Status.bEnabled)
	{
		Status.Reason = TEXT("r.AstraMetalFX is 0");
	}
	else if (!Current.IsValid())
	{
		Status.Reason = bBuilding ? TEXT("the scaler is being built") : TEXT("no game view asked for it yet");
	}
	else if (!Status.bActive)
	{
		Status.Reason = TEXT("the game view did not use it in the last frames (TSR)");
	}
	if (Current.IsValid())
	{
		const AstraMetalFX::FGpuTimings Timings = Current->GetTimings();
		Status.OutputSize = Current->GetOutputSize();
		Status.LastGpuMs = Timings.LastMs;
		Status.AverageGpuMs = Timings.AverageMs;
		Status.FramesUpscaled = Timings.Frames;
		Status.Errors = Timings.Errors;
	}
	return Status;
}
