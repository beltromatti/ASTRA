#include "AstraTransportFx.h"

#include "ASTRA.h"
#include "Engine/World.h"

// The columns, the sparkles, the pads' light and the Captain's own view (written in the effects' pass: see AstraTransportFx.h).

void UAstraTransportFx::Init(UWorld* InWorld)
{
	World = InWorld;
	bReady = World != nullptr;
}

void UAstraTransportFx::Shutdown()
{
	bReady = false;
	Cols.Reset();
	Pool.Reset();
	PadList.Reset();
}

void UAstraTransportFx::Tick(float Dt, const FVector& CaptainEyeCm)
{
	(void)Dt;
	(void)CaptainEyeCm;
}

int32 UAstraTransportFx::BeginColumn(const FVector& FeetCm, float YawDeg, bool bRematerialize, float Seconds, AActor* Source, float MassKg, bool bCaptain)
{
	FColumn C;
	C.Id = NextId++;
	C.Feet = FeetCm;
	C.Yaw = YawDeg;
	C.bRemat = bRematerialize;
	C.bCaptain = bCaptain;
	C.Seconds = Seconds;
	C.Mass = MassKg;
	C.Source = Source;
	Cols.Add(C);
	return C.Id;
}

void UAstraTransportFx::BindSource(int32 Id, AActor* Source)
{
	for (FColumn& C : Cols)
	{
		if (C.Id == Id)
		{
			C.Source = Source;
		}
	}
}

void UAstraTransportFx::ReverseColumn(int32 Id)
{
	for (FColumn& C : Cols)
	{
		if (C.Id == Id)
		{
			C.Dir = -C.Dir;
		}
	}
}

void UAstraTransportFx::EndColumn(int32 Id, bool bNow)
{
	Cols.RemoveAll([Id](const FColumn& C) { return C.Id == Id; });
	(void)bNow;
}

bool UAstraTransportFx::HasColumn(int32 Id) const
{
	return Cols.ContainsByPredicate([Id](const FColumn& C) { return C.Id == Id; });
}

void UAstraTransportFx::BeginCaptainView(bool bRematerialize, float Seconds)
{
	bViewActive = true;
	bViewRemat = bRematerialize;
	ViewSeconds = Seconds;
	ViewAge = 0.f;
	ViewDir = 1.f;
}

void UAstraTransportFx::ReverseCaptainView()
{
	ViewDir = -ViewDir;
}

void UAstraTransportFx::EndCaptainView()
{
	bViewActive = false;
}

void UAstraTransportFx::HoldCaptainView(float Level01)
{
	ViewHold = Level01;
}

void UAstraTransportFx::SetPadLook(int32 PadIndex, const FVector& PosCm, float RadiusCm, EAstraPadLook Look)
{
	if (PadIndex < 0)
	{
		return;
	}
	if (PadList.Num() <= PadIndex)
	{
		PadList.SetNum(PadIndex + 1);
	}
	PadList[PadIndex].Pos = PosCm;
	PadList[PadIndex].Radius = RadiusCm;
	PadList[PadIndex].Look = Look;
}

void UAstraTransportFx::ClearPads()
{
	PadList.Reset();
}

void UAstraTransportFx::SetEmitter(const FVector& CentreCm, float Glow)
{
	EmitterCm = CentreCm;
	EmitterGlow = Glow;
}

void UAstraTransportFx::PlaySound(const TCHAR* Id, const FVector& AtCm, float Volume, float Pitch)
{
	(void)Id;
	(void)AtCm;
	(void)Volume;
	(void)Pitch;
}

int32 UAstraTransportFx::StartLoop(const TCHAR* Id, const FVector& AtCm, float Volume)
{
	(void)Id;
	(void)AtCm;
	(void)Volume;
	return NextLoop++;
}

void UAstraTransportFx::StopLoop(int32 Id, float FadeS)
{
	(void)Id;
	(void)FadeS;
}

FString UAstraTransportFx::Describe() const
{
	return FString::Printf(TEXT("%d columns, %d sparkles, %d pads"), Cols.Num(), NumLive, PadList.Num());
}

void UAstraTransportFx::LoadAssets() {}
void UAstraTransportFx::EmitFor(FColumn&, float) {}
void UAstraTransportFx::StepSparkles(float) {}
void UAstraTransportFx::WriteInstances(const FVector&) {}
void UAstraTransportFx::StepColumns(float) {}
void UAstraTransportFx::StepOverlay(float) {}
void UAstraTransportFx::StepPads(float) {}
void UAstraTransportFx::EnsureLayers() {}
void UAstraTransportFx::DropColumn(int32) {}
USkeletalMeshComponent* UAstraTransportFx::MakeGhost(AActor*) { return nullptr; }
