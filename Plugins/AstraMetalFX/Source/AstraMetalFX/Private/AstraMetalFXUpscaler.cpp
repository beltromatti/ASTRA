// Copyright ASTRA.

#include "AstraMetalFXUpscaler.h"
#include "AstraMetalFXManager.h"
#include "RenderGraphBuilder.h"
#include "RenderGraphUtils.h"
#include "RHICommandList.h"
#include "ScreenPass.h"
#include "ShaderParameterStruct.h"

BEGIN_SHADER_PARAMETER_STRUCT(FAstraMetalFXPassParameters, )
	RDG_TEXTURE_ACCESS(SceneColor, ERHIAccess::SRVCompute)
	RDG_TEXTURE_ACCESS(SceneDepth, ERHIAccess::SRVCompute)
	RDG_TEXTURE_ACCESS(SceneVelocity, ERHIAccess::SRVCompute)
	RDG_TEXTURE_ACCESS(EyeAdaptation, ERHIAccess::SRVCompute)
	RDG_TEXTURE_ACCESS(Output, ERHIAccess::UAVCompute)
END_SHADER_PARAMETER_STRUCT()

namespace
{
	// The view uniform buffer's ClipToPrevClip, built exactly as SetupCommonViewUniformBufferParameters does (SceneView.cpp),
	// from the current and the previous frame's matrices: maps the clip position of a pixel of this frame (without the TAA
	// jitter) to where the same world point was in the previous frame. TSR uses the same matrix to give depth a motion.
	FMatrix44f ComputeClipToPrevClip(const FViewMatrices& Current, const FViewMatrices& Previous)
	{
		const FVector DeltaTranslation = Previous.GetPreViewTranslation() - Current.GetPreViewTranslation();
		const FMatrix InvViewProj = Current.ComputeInvProjectionNoAAMatrix() * Current.GetTranslatedViewMatrix().GetTransposed();
		const FMatrix PrevViewProj = FTranslationMatrix(DeltaTranslation) * Previous.GetTranslatedViewMatrix() * Previous.ComputeProjectionNoAAMatrix();
		return FMatrix44f(InvViewProj * PrevViewProj);
	}
}

FAstraMetalFXUpscaler::FAstraMetalFXUpscaler(FContextPtr InContext)
	: Context(MoveTemp(InContext))
{
	check(Context.IsValid());
}

const TCHAR* FAstraMetalFXUpscaler::GetUpscalerDebugName()
{
	static const TCHAR* const Name = TEXT("AstraMetalFX");
	return Name;
}

float FAstraMetalFXUpscaler::GetMinUpsampleResolutionFraction() const
{
	// A hair above the exact limit so that rounding the rendered size up can never cross it (MetalFX asserts outside its range).
	return FMath::Min(Context->GetMinInputFraction() + 0.004f, 1.0f);
}

float FAstraMetalFXUpscaler::GetMaxUpsampleResolutionFraction() const
{
	return Context->GetMaxInputFraction();
}

UE::Renderer::Private::ITemporalUpscaler* FAstraMetalFXUpscaler::Fork_GameThread(const FSceneViewFamily& ViewFamily) const
{
	return new FAstraMetalFXUpscaler(Context);
}

FAstraMetalFXUpscaler::FOutputs FAstraMetalFXUpscaler::AddPasses(FRDGBuilder& GraphBuilder, const FSceneView& View, const FInputs& Inputs) const
{
	FAstraMetalFXManager& Manager = FAstraMetalFXManager::Get();

	const FIntPoint OutputSize = Inputs.OutputViewRect.Size();
	const FIntRect InputRect = Inputs.SceneColor.ViewRect;

	FRDGTextureDesc OutputDesc = FRDGTextureDesc::Create2D(
		OutputSize,
		PF_FloatRGBA,
		FClearValueBinding::Black,
		// Read/write and render target: what MetalFX asks of the texture it writes (queried, see probe_create).
		TexCreate_ShaderResource | TexCreate_UAV | TexCreate_RenderTargetable);
	FRDGTextureRef OutputTexture = GraphBuilder.CreateTexture(OutputDesc, TEXT("AstraMetalFX.Output"));

	// The history the engine kept for this view from the last frame, if it was ours.
	const FHistory* Prev = Inputs.PrevHistory.IsValid() ? static_cast<const FHistory*>(Inputs.PrevHistory.GetReference()) : nullptr;
	const bool bReset = View.bCameraCut
		|| Prev == nullptr
		|| Prev->Context != Context
		|| Prev->OutputSize != OutputSize
		|| Prev->DeclineEpoch != Manager.GetDeclineEpoch();   // TSR ran in between: the history is stale

	FOutputs Outputs;
	Outputs.FullRes = FScreenPassTexture(OutputTexture, Inputs.OutputViewRect);
	Outputs.NewHistory = MakeRefCount<FHistory>(Context, View.ViewMatrices, OutputSize, Manager.GetDeclineEpoch());

	if (!Context->IsHealthy())
	{
		// A frame failed: the manager switches to TSR from the next frame on. This one must still hand the tonemapper something valid.
		AddClearRenderTargetPass(GraphBuilder, OutputTexture, FLinearColor::Black);
		return Outputs;
	}

	// Camera motion: from the previous frame's matrices (kept in the history), moved with the world if it was rebased.
	FViewMatrices PreviousMatrices = Prev ? Prev->ViewMatrices : View.ViewMatrices;
	if (Prev && !View.OriginOffsetThisFrame.IsZero())
	{
		PreviousMatrices.ApplyWorldOffset(View.OriginOffsetThisFrame);
	}

	AstraMetalFX::FFrame Frame;
	Frame.ViewRect = InputRect;
	Frame.OutputSize = OutputSize;
	Frame.Jitter = Inputs.TemporalJitterPixels;
	Frame.PreExposure = Inputs.PreExposure;
	Frame.bReset = bReset;
	Frame.DebugView = Manager.GetDebugView();
	Frame.FrameNumber = View.Family ? View.Family->FrameNumber : 0;
	const FMatrix44f ClipToPrevClip = ComputeClipToPrevClip(View.ViewMatrices, PreviousMatrices);
	static_assert(sizeof(Frame.ClipToPrevClip) == sizeof(ClipToPrevClip.M), "a 4x4 float matrix");
	FMemory::Memcpy(Frame.ClipToPrevClip, &ClipToPrevClip.M[0][0], sizeof(Frame.ClipToPrevClip));

	FRDGTextureRef SceneColor = Inputs.SceneColor.Texture;
	FRDGTextureRef SceneDepth = Inputs.SceneDepth.Texture;
	FRDGTextureRef SceneVelocity = Inputs.SceneVelocity.Texture;
	FRDGTextureRef EyeAdaptation = Inputs.EyeAdaptationTexture;

	FAstraMetalFXPassParameters* PassParameters = GraphBuilder.AllocParameters<FAstraMetalFXPassParameters>();
	PassParameters->SceneColor = SceneColor;
	PassParameters->SceneDepth = SceneDepth;
	PassParameters->SceneVelocity = SceneVelocity;
	PassParameters->EyeAdaptation = EyeAdaptation;
	PassParameters->Output = OutputTexture;

	// The work is not recorded in the RHI command list but runs as a Metal command buffer of ours, put in between Unreal's
	// in queue order (Metal's hazard tracking orders the textures): see AstraMetalFXBridge.mm. The pass only has to
	// (1) hand everything recorded so far to Metal and (2) enqueue our submission right behind it, the same sequence
	// the Metal RHI itself uses for the present and Epic's NNE plugin uses to run an external library in the middle of a frame.
	GraphBuilder.AddPass(
		RDG_EVENT_NAME("AstraMetalFX %dx%d -> %dx%d%s", InputRect.Width(), InputRect.Height(), OutputSize.X, OutputSize.Y, bReset ? TEXT(" (reset)") : TEXT("")),
		PassParameters,
		ERDGPassFlags::Compute | ERDGPassFlags::NeverCull,
		[Context = Context, Frame, SceneColor, SceneDepth, SceneVelocity, EyeAdaptation, OutputTexture](FRHICommandListImmediate& RHICmdList) mutable
		{
			Frame.SceneColor = SceneColor->GetRHI();
			Frame.SceneDepth = SceneDepth->GetRHI();
			Frame.SceneVelocity = SceneVelocity ? SceneVelocity->GetRHI() : nullptr;
			Frame.EyeAdaptation = EyeAdaptation ? EyeAdaptation->GetRHI() : nullptr;
			Frame.Output = OutputTexture->GetRHI();

			// The RHI thread runs the lambda below later: keep the textures alive until then.
			TRefCountPtr<FRHITexture> KeepColor(Frame.SceneColor), KeepDepth(Frame.SceneDepth), KeepVelocity(Frame.SceneVelocity),
				KeepEye(Frame.EyeAdaptation), KeepOutput(Frame.Output);

			RHICmdList.ImmediateFlush(EImmediateFlushType::DispatchToRHIThread);
			RHICmdList.EnqueueLambda(TEXT("AstraMetalFX"), [Context, Frame, KeepColor, KeepDepth, KeepVelocity, KeepEye, KeepOutput](FRHICommandListImmediate&)
			{
				Context->Submit(Frame);
			});
		});

	Manager.PublishFrame(Context);
	return Outputs;
}
