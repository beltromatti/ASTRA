// ASTRA — the Captain at the stick of a Falcon.

#include "AstraFighterPawn.h"

#include "ASTRA.h"
#include "AstraHangar.h"
#include "Camera/CameraComponent.h"
#include "Camera/PlayerCameraManager.h"
#include "Components/AudioComponent.h"
#include "Components/InputComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/Font.h"
#include "Engine/GameViewportClient.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "Fonts/SlateFontInfo.h"
#include "Framework/Application/SlateApplication.h"
#include "GameFramework/PlayerController.h"
#include "Kismet/GameplayStatics.h"
#include "Rendering/DrawElements.h"
#include "Sound/SoundBase.h"
#include "Styling/CoreStyle.h"
#include "Widgets/SLeafWidget.h"

// ------------------------------------------------------------------------------------------------ head-up display
/** The Falcon's head-up display, projected on the canopy: reticle, the stick, brackets on hostiles, the lock and the
 *  lead for the cannons, the way home, speed and throttle, hull, shields, missiles. Positions are normalised (0..1). */
class SAstraFlightHud : public SLeafWidget
{
public:
	SLATE_BEGIN_ARGS(SAstraFlightHud) {}
	SLATE_END_ARGS()

	struct FData
	{
		FString Hint;
		FVector2D Stick = FVector2D::ZeroVector;
		float Speed = 0.f, Throttle = 0.f, Hull = 100.f, Shield = 100.f;
		int32 Missiles = 0, Decoys = 0;
		bool bBoost = false, bFlying = false;
		TArray<FVector2D> Hostiles;
		TArray<float> HostileBox;
		TArray<FVector2D> Friends;
		bool bLock = false, bLockOn = false, bLead = false;
		FVector2D LockPos = FVector2D::ZeroVector, LeadPos = FVector2D::ZeroVector;
		float LockProgress = 0.f;
		FString LockText;
		bool bHomeOn = false, bHomeEdge = false;
		FVector2D HomePos = FVector2D::ZeroVector;
		float HomeEdgeAngle = 0.f;
		FString HomeText;
	};
	FData Data;

	void Construct(const FArguments&)
	{
		UFont* Mono = LoadObject<UFont>(nullptr, TEXT("/Game/ASTRA/UI/Fonts/F_ASTRA_Mono.F_ASTRA_Mono"));
		Font = Mono ? FSlateFontInfo(Mono, 16) : FCoreStyle::GetDefaultFontStyle("Mono", 16);
		Small = Mono ? FSlateFontInfo(Mono, 12) : FCoreStyle::GetDefaultFontStyle("Mono", 12);
	}

	virtual FVector2D ComputeDesiredSize(float) const override { return FVector2D(100.f, 100.f); }

	virtual int32 OnPaint(const FPaintArgs& Args, const FGeometry& G, const FSlateRect& Clip, FSlateWindowElementList& Out, int32 Layer,
	                      const FWidgetStyle& Style, bool bParentEnabled) const override
	{
		const FVector2D Size = G.GetLocalSize();
		const FVector2D C = Size * 0.5;
		const FLinearColor Ink(0.45f, 1.f, 0.85f, 0.85f), Dim(0.45f, 1.f, 0.85f, 0.35f), Warn(1.f, 0.7f, 0.2f, 0.95f), Foe(1.f, 0.42f, 0.3f, 0.9f);
		const float U = Size.Y / 1080.f;   // design unit: 1 px at 1080p
		auto Lines = [&](const TArray<FVector2D>& P, const FLinearColor& Col, float W = 1.5f)
		{
			FSlateDrawElement::MakeLines(Out, Layer, G.ToPaintGeometry(), P, ESlateDrawEffect::None, Col, true, W * FMath::Max(1.f, U));
		};
		auto Circle = [&](const FVector2D& At, float R, const FLinearColor& Col, float W = 1.5f, float From = 0.f, float To = 1.f)
		{
			TArray<FVector2D> P;
			const int32 N = 32;
			for (int32 i = 0; i <= N; ++i)
			{
				const float A = 2.f * PI * (From + (To - From) * i / N) - PI / 2;
				P.Add(At + FVector2D(FMath::Cos(A), FMath::Sin(A)) * R);
			}
			Lines(P, Col, W);
		};
		auto Text = [&](const FVector2D& At, const FString& S, const FLinearColor& Col, bool bSmall = false)
		{
			// a dark halo under the glyphs keeps them legible against a sunlit hull or a planet
			FSlateDrawElement::MakeText(Out, Layer + 1, G.ToPaintGeometry(FVector2D(900.f, 40.f), FSlateLayoutTransform(At + FVector2D(1.5f, 1.5f))), S,
			                            bSmall ? Small : Font, ESlateDrawEffect::None, FLinearColor(0.f, 0.f, 0.f, 0.65f * Col.A));
			FSlateDrawElement::MakeText(Out, Layer + 2, G.ToPaintGeometry(FVector2D(900.f, 40.f), FSlateLayoutTransform(At)), S,
			                            bSmall ? Small : Font, ESlateDrawEffect::None, Col);
		};
		auto Bracket = [&](const FVector2D& At, float H, const FLinearColor& Col)
		{
			const float L = H * 0.45f;
			for (const FVector2D& Sg : {FVector2D(-1, -1), FVector2D(1, -1), FVector2D(1, 1), FVector2D(-1, 1)})
			{
				const FVector2D Corner = At + Sg * H;
				Lines({Corner - FVector2D(Sg.X * L, 0), Corner, Corner - FVector2D(0, Sg.Y * L)}, Col);
			}
		};
		if (!Data.Hint.IsEmpty())
		{
			const bool bAlarm = Data.Hint.StartsWith(TEXT("MISSILE")) || Data.Hint.StartsWith(TEXT("HULL"));
			const bool bBlink = !bAlarm || FMath::Fmod(FPlatformTime::Seconds(), 0.8) < 0.5;
			if (bBlink)
			{
				Text(FVector2D(C.X - 300.f * U, Size.Y * 0.3f), Data.Hint, bAlarm ? Warn : Ink);
			}
		}
		if (!Data.bFlying)
		{
			return Layer + 3;
		}
		// the reticle and the stick
		Circle(C, 14.f * U, Ink);
		Lines({C + FVector2D(-26, 0) * U, C + FVector2D(-16, 0) * U}, Ink);
		Lines({C + FVector2D(16, 0) * U, C + FVector2D(26, 0) * U}, Ink);
		Lines({C + FVector2D(0, 16) * U, C + FVector2D(0, 24) * U}, Ink);
		Circle(C, 150.f * U, Dim, 1.f);
		const FVector2D StickAt = C + Data.Stick * 150.f * U;
		Circle(StickAt, 5.f * U, Ink, 2.f);
		if (Data.Stick.Size() > 0.05f)
		{
			Lines({C + Data.Stick.GetSafeNormal() * 14.f * U, StickAt}, Dim, 1.f);
		}
		// who is out there
		for (int32 i = 0; i < Data.Hostiles.Num(); ++i)
		{
			Bracket(Data.Hostiles[i] * Size, Data.HostileBox[i] * U, Foe);
		}
		for (const FVector2D& F : Data.Friends)
		{
			Circle(F * Size, 6.f * U, Dim, 1.f);
		}
		// the lock and the lead
		if (Data.bLock)
		{
			const FVector2D L = Data.LockPos * Size;
			const float H = 30.f * U;
			Lines({L + FVector2D(-H, -H), L + FVector2D(H, -H), L + FVector2D(H, H), L + FVector2D(-H, H), L + FVector2D(-H, -H)},
			      Data.bLockOn ? Warn : Ink, Data.bLockOn ? 2.5f : 1.5f);
			if (!Data.bLockOn)
			{
				Circle(L, H * 1.4f, Ink, 2.f, 0.f, Data.LockProgress);
			}
			Text(L + FVector2D(H + 6.f * U, -H), Data.LockText, Data.bLockOn ? Warn : Ink, true);
		}
		if (Data.bLead)
		{
			const FVector2D P = Data.LeadPos * Size;
			const float D = 7.f * U;
			Lines({P + FVector2D(0, -D), P + FVector2D(D, 0), P + FVector2D(0, D), P + FVector2D(-D, 0), P + FVector2D(0, -D)}, Ink, 2.f);
		}
		// the way home
		if (Data.bHomeOn)
		{
			const FVector2D P = Data.HomePos * Size;
			Lines({P + FVector2D(-12, -8) * U, P + FVector2D(0, 4) * U, P + FVector2D(12, -8) * U}, Ink, 2.f);
			Text(P + FVector2D(-40.f, 10.f) * U, Data.HomeText, Ink, true);
		}
		else if (Data.bHomeEdge)
		{
			const FVector2D Dir(FMath::Cos(Data.HomeEdgeAngle), FMath::Sin(Data.HomeEdgeAngle));
			const FVector2D P = C + Dir * 240.f * U;
			const FVector2D N(-Dir.Y, Dir.X);
			Lines({P - Dir * 10.f * U + N * 8.f * U, P + Dir * 6.f * U, P - Dir * 10.f * U - N * 8.f * U}, Ink, 2.f);
			Text(P + FVector2D(14.f, -6.f) * U, Data.HomeText, Dim, true);
		}
		// the instruments: speed and throttle (left), hull, shields and missiles (right)
		const FVector2D LB(C.X - 470.f * U, C.Y + 170.f * U), RB(C.X + 360.f * U, C.Y + 170.f * U);
		Text(LB, FString::Printf(TEXT("SPD %4.0f m/s%s"), Data.Speed, Data.bBoost ? TEXT("  BOOST") : TEXT("")), Ink);
		Lines({LB + FVector2D(0, 30) * U, LB + FVector2D(120, 30) * U}, Dim, 4.f);
		Lines({LB + FVector2D(0, 30) * U, LB + FVector2D(120.f * Data.Throttle, 30.f) * U}, Ink, 4.f);
		Text(LB + FVector2D(0, 38) * U, TEXT("THR"), Dim, true);
		const FLinearColor HullCol = Data.Hull < 35.f ? Warn : Ink;
		Text(RB, FString::Printf(TEXT("HULL %3.0f%%"), Data.Hull), HullCol);
		Text(RB + FVector2D(0, 22) * U, FString::Printf(TEXT("SHLD %3.0f%%"), Data.Shield), Data.Shield < 20.f ? Warn : Ink);
		Text(RB + FVector2D(0, 44) * U, FString::Printf(TEXT("MSL  %d"), Data.Missiles), Data.Missiles == 0 ? Dim : Ink);
		Text(RB + FVector2D(0, 66) * U, FString::Printf(TEXT("DCY  %d"), Data.Decoys), Data.Decoys == 0 ? Dim : Ink);
		return Layer + 3;
	}

private:
	FSlateFontInfo Font, Small;
};

// ------------------------------------------------------------------------------------------------ the pawn
AAstraFighterPawn::AAstraFighterPawn()
{
	PrimaryActorTick.bCanEverTick = true;
	Root = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	SetRootComponent(Root);
	Cockpit = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Cockpit"));
	Cockpit->SetupAttachment(Root);
	Cockpit->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Cockpit->SetCastShadow(true);                       // the canopy frame's shadow sweeps the cockpit as she rolls
	Cockpit->bCastDynamicShadow = true;
	static ConstructorHelpers::FObjectFinder<UStaticMesh> Mesh(TEXT("/Game/ASTRA/Ships/Cockpit/SM_CRAFT_ASTRA_Falcon_Cockpit.SM_CRAFT_ASTRA_Falcon_Cockpit"));
	if (Mesh.Succeeded())
	{
		Cockpit->SetStaticMesh(Mesh.Object);
	}
	Camera = CreateDefaultSubobject<UCameraComponent>(TEXT("Camera"));
	Camera->SetupAttachment(Root);
	Camera->bUsePawnControlRotation = false;
	Camera->SetFieldOfView(88.f);
	AutoPossessPlayer = EAutoReceiveInput::Disabled;
}

void AAstraFighterPawn::BeginOnCatapult(AAstraHangar* InHangar, APawn* InWalker)
{
	Hangar = InHangar;
	Walker = InWalker;
	Phase = EPhase::Catapult;
	PhaseT = 0.f;
	if (InHangar)
	{
		SetActorLocationAndRotation(InHangar->CatapultPose(0.f).GetLocation(), InHangar->CatapultPose(0.f).GetRotation());
	}
	ShowHud(true);
	StartSounds();
}

void AAstraFighterPawn::StartSounds()
{
	auto Make = [this](const TCHAR* Name, float Volume) -> UAudioComponent*
	{
		USoundBase* S = LoadObject<USoundBase>(nullptr, *FString::Printf(TEXT("/Game/ASTRA/Audio/%s.%s"), Name, Name));
		return S ? UGameplayStatics::CreateSound2D(this, S, Volume, 1.f, 0.f, nullptr, false, false) : nullptr;
	};
	EngineAudio = Make(TEXT("SW_Falcon_Engine"), 0.3f);
	LockAudio = Make(TEXT("SW_Lock_Solid"), 0.35f);
	WarnAudio = Make(TEXT("SW_Missile_Warning"), 0.45f);
	if (EngineAudio)
	{
		EngineAudio->SetPitchMultiplier(0.75f);
		EngineAudio->Play();
	}
}

void AAstraFighterPawn::StopSounds()
{
	for (UAudioComponent* A : {EngineAudio.Get(), LockAudio.Get(), WarnAudio.Get()})
	{
		if (A)
		{
			A->Stop();
			A->DestroyComponent();
		}
	}
	EngineAudio = LockAudio = WarnAudio = nullptr;
}

void AAstraFighterPawn::UpdateSounds(const FAstraPilotStatus& St, float Dt)
{
	const bool bFlying = Phase == EPhase::Flying && St.bFlying;
	if (EngineAudio)
	{
		// the lever and the afterburner in the airframe; the catapult's run pushes it up too
		const float Push = Phase == EPhase::Launching ? 1.f : In.Throttle;
		const float Boost = (bFlying && In.bBoost) ? 1.f : 0.f;
		EngineAudio->SetPitchMultiplier(0.72f + 0.5f * Push + 0.22f * Boost);
		EngineAudio->SetVolumeMultiplier(Phase == EPhase::Ending ? 0.f : 0.28f + 0.35f * Push + 0.15f * Boost);
	}
	// the seeker: beeps while it works on a target, a steady tone once locked
	const bool bLocked = bFlying && St.bHasLock && St.LockProgress >= 1.f;
	if (LockAudio)
	{
		if (bLocked && !LockAudio->IsPlaying()) { LockAudio->Play(); }
		else if (!bLocked && LockAudio->IsPlaying()) { LockAudio->Stop(); }
	}
	if (bFlying && St.bHasLock && !bLocked && (BeepT -= Dt) <= 0.f)
	{
		BeepT = 0.28f;
		if (USoundBase* B = LoadObject<USoundBase>(nullptr, TEXT("/Game/ASTRA/Audio/SW_Lock_Beep.SW_Lock_Beep")))
		{
			UGameplayStatics::PlaySound2D(this, B, 0.4f);
		}
	}
	if (WarnAudio)
	{
		const bool bWarn = bFlying && St.Incoming > 0;
		if (bWarn && !WarnAudio->IsPlaying()) { WarnAudio->Play(); }
		else if (!bWarn && WarnAudio->IsPlaying()) { WarnAudio->Stop(); }
	}
}

void AAstraFighterPawn::SetupPlayerInputComponent(UInputComponent* IC)
{
	Super::SetupPlayerInputComponent(IC);
	IC->BindAxisKey(EKeys::MouseX, this, &AAstraFighterPawn::MouseX);
	IC->BindAxisKey(EKeys::MouseY, this, &AAstraFighterPawn::MouseY);
	auto Hold = [IC, this](const FKey& K, bool AAstraFighterPawn::* Flag)
	{
		FInputKeyBinding P(FInputChord(K), IE_Pressed);
		P.KeyDelegate.GetDelegateForManualSet().BindLambda([this, Flag]() { this->*Flag = true; });
		IC->KeyBindings.Add(P);
		FInputKeyBinding R(FInputChord(K), IE_Released);
		R.KeyDelegate.GetDelegateForManualSet().BindLambda([this, Flag]() { this->*Flag = false; });
		IC->KeyBindings.Add(R);
	};
	Hold(EKeys::W, &AAstraFighterPawn::bThrUp);
	Hold(EKeys::S, &AAstraFighterPawn::bThrDown);
	Hold(EKeys::A, &AAstraFighterPawn::bRollL);
	Hold(EKeys::D, &AAstraFighterPawn::bRollR);
	Hold(EKeys::Q, &AAstraFighterPawn::bLeft);
	Hold(EKeys::E, &AAstraFighterPawn::bRight);
	Hold(EKeys::SpaceBar, &AAstraFighterPawn::bUp);
	Hold(EKeys::LeftControl, &AAstraFighterPawn::bDown);
	Hold(EKeys::LeftAlt, &AAstraFighterPawn::bFreeLook);
	auto Flag = [IC, this](const FKey& K, TFunction<void(bool)> F)
	{
		FInputKeyBinding P(FInputChord(K), IE_Pressed);
		P.KeyDelegate.GetDelegateForManualSet().BindLambda([F]() { F(true); });
		IC->KeyBindings.Add(P);
		FInputKeyBinding R(FInputChord(K), IE_Released);
		R.KeyDelegate.GetDelegateForManualSet().BindLambda([F]() { F(false); });
		IC->KeyBindings.Add(R);
	};
	Flag(EKeys::LeftShift, [this](bool b) { In.bBoost = b; });
	Flag(EKeys::LeftMouseButton, [this](bool b) { In.bGuns = b; });
	Flag(EKeys::RightMouseButton, [this](bool b) { In.bMissile = b; });
	Flag(EKeys::C, [this](bool b) { In.bDecoy = b; });
	Flag(EKeys::X, [this](bool b) { if (b) { In.Throttle = 0.f; } });   // X: cut the throttle
	IC->BindKey(EKeys::F, IE_Pressed, this, &AAstraFighterPawn::Land);
}

bool AAstraFighterPawn::ClimbOut()
{
	if (Phase != EPhase::Catapult)
	{
		return false;
	}
	FinishFlight();
	return true;
}

void AAstraFighterPawn::MouseX(float V)
{
	if (bFreeLook)
	{
		LookYaw = FMath::Clamp(LookYaw + V * 2.f, -150.f, 150.f);
		return;
	}
	Stick.X = FMath::Clamp(Stick.X + V * 0.035f, -1.f, 1.f);
}

void AAstraFighterPawn::MouseY(float V)
{
	if (bFreeLook)
	{
		LookPitch = FMath::Clamp(LookPitch + V * 2.f, -70.f, 80.f);
		return;
	}
	Stick.Y = FMath::Clamp(Stick.Y - V * 0.035f, -1.f, 1.f);
}

void AAstraFighterPawn::Land()
{
	UAstraBattleSubsystem* Battle = GetWorld()->GetSubsystem<UAstraBattleSubsystem>();
	if (Phase != EPhase::Flying || !Battle)
	{
		return;
	}
	FAstraPilotStatus St;
	Battle->GetPilotStatus(St);
	if (St.bCanLand)
	{
		Phase = EPhase::Ending;
		PhaseT = 0.f;
		bLandedEnd = true;
		if (APlayerCameraManager* Cam = UGameplayStatics::GetPlayerCameraManager(this, 0))
		{
			Cam->StartCameraFade(0.f, 1.f, 0.8f, FLinearColor::Black, false, true);
		}
	}
}

void AAstraFighterPawn::Tick(float DeltaTime)
{
	Super::Tick(DeltaTime);
	UAstraBattleSubsystem* Battle = GetWorld()->GetSubsystem<UAstraBattleSubsystem>();
	// the hands on the controls: the lever moves at 0.6 a second, the stick recentres when the mouse rests
	In.Throttle = FMath::Clamp(In.Throttle + ((bThrUp ? 1.f : 0.f) - (bThrDown ? 1.f : 0.f)) * 0.6f * DeltaTime, 0.f, 1.f);
	if (TestRoll == 0.f)
	{
		Stick *= FMath::Max(0.f, 1.f - 1.6f * DeltaTime);
	}
	const FVector2D Shaped(FMath::Sign(Stick.X) * FMath::Square(Stick.X) * 0.7f + Stick.X * 0.3f, FMath::Sign(Stick.Y) * FMath::Square(Stick.Y) * 0.7f + Stick.Y * 0.3f);
	In.Yaw = Shaped.X;
	In.Pitch = Shaped.Y;
	In.Roll = FMath::Clamp((bRollR ? 1.f : 0.f) - (bRollL ? 1.f : 0.f) + TestRoll, -1.f, 1.f);
	if (MissilePulse > 0.f && (MissilePulse -= DeltaTime) <= 0.f)
	{
		In.bMissile = false;
	}
	In.Strafe = FVector(0.f, (bRight ? 1.f : 0.f) - (bLeft ? 1.f : 0.f), (bUp ? 1.f : 0.f) - (bDown ? 1.f : 0.f));
	if (!bFreeLook)
	{
		LookYaw = FMath::FInterpTo(LookYaw, 0.f, DeltaTime, 4.f);
		LookPitch = FMath::FInterpTo(LookPitch, 0.f, DeltaTime, 4.f);
	}
	Camera->SetRelativeRotation(FRotator(LookPitch, LookYaw, 0.f));

	FAstraPilotStatus St;
	switch (Phase)
	{
	case EPhase::Catapult:
		// on the catapult: throttle up to launch, E to climb out
		if (In.Throttle > 0.25f)
		{
			Phase = EPhase::Launching;
			PhaseT = 0.f;
			if (USoundBase* S = LoadObject<USoundBase>(nullptr, TEXT("/Game/ASTRA/Audio/SW_Catapult.SW_Catapult")))
			{
				UGameplayStatics::PlaySound2D(this, S, 1.f);
			}
		}
		break;
	case EPhase::Launching:
	{
		// the catapult: a hard kick down the track and out of the tube (the view narrows with the acceleration)
		PhaseT += DeltaTime;
		const float T = FMath::Min(1.f, PhaseT / 1.1f);
		Camera->SetFieldOfView(88.f - 9.f * FMath::Sin(PI * T));
		if (AAstraHangar* H = Hangar.Get())
		{
			const FTransform P = H->CatapultPose(T * T);
			SetActorLocationAndRotation(P.GetLocation(), P.GetRotation());
			if (T >= 1.f && Battle && Battle->LaunchPiloted(this, P.GetLocation(), P.GetRotation(), H->CatapultExitSpeed(1.1f)))
			{
				Phase = EPhase::Flying;
				In.Throttle = 0.6f;
				Cockpit->SetLightingChannels(true, true, false);   // outside now: the planet's light reaches the nose
			}
		}
		break;
	}
	case EPhase::Flying:
		if (Battle)
		{
			Battle->SetPilotInput(In);
			Battle->GetPilotStatus(St);
			if (St.bDown)
			{
				// shot down: the canopy blows, black, the pod tumbles; the Wasp brings it home
				Phase = EPhase::Ending;
				PhaseT = 0.f;
				bLandedEnd = false;
				if (APlayerCameraManager* Cam = UGameplayStatics::GetPlayerCameraManager(this, 0))
				{
					Cam->StartCameraFade(0.f, 1.f, 0.25f, FLinearColor(1.f, 0.85f, 0.7f), false, true);
				}
			}
		}
		break;
	case EPhase::Ending:
		PhaseT += DeltaTime;
		if (Battle)
		{
			Battle->SetPilotInput(In);
		}
		if (PhaseT > (bLandedEnd ? 1.0f : 3.5f))
		{
			FinishFlight();
			return;
		}
		break;
	}
	if (Phase == EPhase::Flying && St.bFlying)
	{
		const float HS = St.HullPct + St.ShieldPct;
		if (LastHS >= 0.f && HS < LastHS - 0.5f)
		{
			HitJolt = FMath::Min(1.f, HitJolt + (LastHS - HS) / 25.f + 0.3f);
			if (USoundBase* Bang = LoadObject<USoundBase>(nullptr, TEXT("/Game/ASTRA/Audio/SW_Impact.SW_Impact")))
			{
				UGameplayStatics::PlaySound2D(this, Bang, 0.35f + 0.4f * HitJolt, 1.5f);
			}
		}
		LastHS = HS;
	}
	HitJolt = FMath::Max(0.f, HitJolt - DeltaTime * 3.f);
	if (HitJolt > 0.f)
	{
		Camera->SetRelativeRotation(FRotator(LookPitch + FMath::FRandRange(-1.5f, 1.5f) * HitJolt, LookYaw + FMath::FRandRange(-1.5f, 1.5f) * HitJolt,
		                                     FMath::FRandRange(-1.f, 1.f) * HitJolt));
	}
	UpdateSounds(St, DeltaTime);
	UpdateHud(St);
}

void AAstraFighterPawn::FinishFlight()
{
	UAstraBattleSubsystem* Battle = GetWorld()->GetSubsystem<UAstraBattleSubsystem>();
	if (Battle && Battle->IsPiloting())
	{
		Battle->EndPiloted(bLandedEnd);
	}
	else if (Battle && Phase != EPhase::Ending)
	{
		Battle->ReturnFalcon();   // climbed out on the catapult
	}
	ShowHud(false);
	APlayerController* PC = Cast<APlayerController>(GetController());
	APawn* W = Walker.Get();
	if (PC && W)
	{
		// back on the flight deck, beside Alpha's bays
		if (AAstraHangar* H = Hangar.Get())
		{
			const FTransform Spot = H->DeckSpot();
			W->SetActorLocation(Spot.GetLocation(), false, nullptr, ETeleportType::TeleportPhysics);
			PC->SetControlRotation(Spot.Rotator());
		}
		W->SetActorHiddenInGame(false);
		W->SetActorEnableCollision(true);
		PC->Possess(W);
		if (APlayerCameraManager* Cam = PC->PlayerCameraManager)
		{
			Cam->StartCameraFade(1.f, 0.f, 1.0f, FLinearColor::Black, false, false);
		}
	}
	Destroy();
}

void AAstraFighterPawn::EndPlay(const EEndPlayReason::Type Reason)
{
	ShowHud(false);
	StopSounds();
	Super::EndPlay(Reason);
}

void AAstraFighterPawn::ShowHud(bool bShow)
{
	UGameViewportClient* VC = GetWorld() ? GetWorld()->GetGameViewport() : nullptr;
	if (bShow && !Hud.IsValid() && VC)
	{
		Hud = SNew(SAstraFlightHud);
		VC->AddViewportWidgetContent(Hud.ToSharedRef(), 10);
	}
	else if (!bShow && Hud.IsValid())
	{
		if (VC)
		{
			VC->RemoveViewportWidgetContent(Hud.ToSharedRef());
		}
		Hud.Reset();
	}
}

void AAstraFighterPawn::UpdateHud(const FAstraPilotStatus& St)
{
	if (!Hud.IsValid())
	{
		return;
	}
	SAstraFlightHud::FData& D = Hud->Data;
	D = SAstraFlightHud::FData();
	D.bFlying = Phase == EPhase::Flying && St.bFlying;
	D.Stick = Stick;
	D.Throttle = In.Throttle;
	D.bBoost = In.bBoost;
	if (Phase == EPhase::Catapult)
	{
		D.Hint = TEXT("ON ALPHA'S CATAPULT  ·  W: THROTTLE UP TO LAUNCH  ·  E: CLIMB OUT");
		return;
	}
	if (!D.bFlying)
	{
		return;
	}
	D.Speed = St.SpeedMps;
	D.Hull = St.HullPct;
	D.Shield = St.ShieldPct;
	D.Missiles = St.Missiles;
	D.Decoys = St.Decoys;
	APlayerController* PC = Cast<APlayerController>(GetController());
	FVector2D VP(1920.f, 1080.f);
	if (GetWorld()->GetGameViewport())
	{
		GetWorld()->GetGameViewport()->GetViewportSize(VP);
	}
	auto Project = [PC, &VP](const FVector& W, FVector2D& OutN) -> bool
	{
		FVector2D S;
		if (!PC || !PC->ProjectWorldLocationToScreen(W, S, true))
		{
			return false;
		}
		OutN = S / VP;
		return OutN.X > -0.05 && OutN.X < 1.05 && OutN.Y > -0.05 && OutN.Y < 1.05;
	};
	const FVector Eye = Camera->GetComponentLocation();
	const float Fov = FMath::DegreesToRadians(Camera->FieldOfView);
	for (int32 i = 0; i < St.Hostiles.Num(); ++i)
	{
		FVector2D N;
		if (Project(St.Hostiles[i], N))
		{
			const float Dist = FVector::Dist(Eye, St.Hostiles[i]) / 100.f;
			const float Px = St.HostileSizes[i] / FMath::Max(1.f, Dist) / FMath::Tan(Fov / 2) * 960.f;   // its size on screen
			D.Hostiles.Add(N);
			D.HostileBox.Add(FMath::Clamp(Px, 9.f, 120.f));
		}
	}
	for (const FVector& F : St.Friends)
	{
		FVector2D N;
		if (Project(F, N))
		{
			D.Friends.Add(N);
		}
	}
	if (St.bHasLock && Project(St.LockWorld, D.LockPos))
	{
		D.bLock = true;
		D.bLockOn = St.LockProgress >= 1.f;
		D.LockProgress = St.LockProgress;
		D.LockText = FString::Printf(TEXT("%s  %.1f km%s"), *St.LockName.ToUpper(), St.LockRangeKm, D.bLockOn ? TEXT("  LOCK") : TEXT(""));
		D.bLead = Project(St.LeadWorld, D.LeadPos);
	}
	D.HomeText = FString::Printf(TEXT("AQUILA %.1f km%s"), St.HomeRangeKm, St.bCanLand ? TEXT("  ·  F: RECOVER") : TEXT(""));
	if (Project(St.HomeWorld, D.HomePos))
	{
		D.bHomeOn = true;
	}
	else
	{
		const FVector Local = Camera->GetComponentTransform().InverseTransformPosition(St.HomeWorld);
		D.bHomeEdge = true;
		D.HomeEdgeAngle = FMath::Atan2(-Local.Z, Local.Y);
	}
	if (St.Incoming > 0)
	{
		D.Hint = FString::Printf(TEXT("MISSILE%s INBOUND  ·  C: DECOYS  ·  BREAK AND BOOST"), St.Incoming > 1 ? TEXT("S") : TEXT(""));
	}
	else if (St.bCanLand)
	{
		D.Hint = TEXT("RECOVERY APPROACH  ·  F: INTO THE TUBE");
	}
	else if (St.HullPct < 30.f)
	{
		D.Hint = TEXT("HULL CRITICAL  ·  RETURN TO THE AQUILA");
	}
}
