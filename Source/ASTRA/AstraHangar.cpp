// ASTRA — the flight deck.

#include "AstraHangar.h"

#include "ASTRA.h"
#include "AstraBattleSubsystem.h"
#include "Camera/PlayerCameraManager.h"
#include "Components/CapsuleComponent.h"
#include "Components/LightComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/Light.h"
#include "Engine/StaticMeshActor.h"
#include "EngineUtils.h"
#include "GameFramework/Character.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"
#include "Kismet/GameplayStatics.h"
#include "Sound/SoundBase.h"

namespace
{
	const FName ZoneTag(TEXT("ASTRA.Zone.Hangar"));
	const FName EngZoneTag(TEXT("ASTRA.Zone.Engineering"));
	const FName MedZoneTag(TEXT("ASTRA.Zone.Medbay"));
	const FName CraftTag(TEXT("ASTRA.Hangar.Craft"));
	constexpr float HangarLength = 16000.f, HangarHalfWidth = 2900.f, HangarHeight = 2200.f;   // cm, with the tubes
	constexpr float TrackStartX = 4600.f, TubeEndX = 16200.f, TubeY = 1490.f;
	constexpr float CradleX = 12000.f;   // the Captain's Falcon waits here, ahead of Alpha's bays
}

AAstraHangar::AAstraHangar()
{
	PrimaryActorTick.bCanEverTick = true;
	SetRootComponent(CreateDefaultSubobject<USceneComponent>(TEXT("Root")));
}

void AAstraHangar::BeginPlay()
{
	Super::BeginPlay();
	CatapultSound = LoadObject<USoundBase>(nullptr, TEXT("/Game/ASTRA/Audio/SW_Catapult.SW_Catapult"));
	LiftSound = LoadObject<USoundBase>(nullptr, TEXT("/Game/ASTRA/Audio/SW_Door_Close.SW_Door_Close"));
	for (TActorIterator<AActor> It(GetWorld()); It; ++It)
	{
		if (It->ActorHasTag(ZoneTag))
		{
			if (ALight* L = Cast<ALight>(*It))
			{
				ZoneLights.Add(L);
			}
		}
		else if (It->ActorHasTag(EngZoneTag))
		{
			if (ALight* L = Cast<ALight>(*It))
			{
				EngLights.Add(L);
			}
		}
		else if (It->ActorHasTag(MedZoneTag))
		{
			if (ALight* L = Cast<ALight>(*It))
			{
				MedLights.Add(L);
			}
		}
		else if (It->ActorHasTag(CraftTag))
		{
			AStaticMeshActor* A = Cast<AStaticMeshActor>(*It);
			if (!A)
			{
				continue;
			}
			for (const TCHAR* Sq : {TEXT("alpha"), TEXT("bravo"), TEXT("drones")})
			{
				if (A->ActorHasTag(FName(FString::Printf(TEXT("ASTRA.Hangar.%s"), Sq))))
				{
					A->GetStaticMeshComponent()->SetMobility(EComponentMobility::Movable);
					FParked P;
					P.Actor = A;
					P.Home = A->GetActorTransform();
					Parked.FindOrAdd(Sq).Add(P);
				}
			}
		}
	}
	// bay order: the craft nearest the tubes launch first (they are the last ones kept home)
	const FTransform Me = GetActorTransform();
	for (auto& KV : Parked)
	{
		KV.Value.Sort([&Me](const FParked& A, const FParked& B)
		{
			const FVector La = Me.InverseTransformPosition(A.Home.GetLocation()), Lb = Me.InverseTransformPosition(B.Home.GetLocation());
			return La.X + La.Z * 0.1f < Lb.X + Lb.Z * 0.1f;
		});
	}
	SetZoneLights(IsPawnInHangar(UGameplayStatics::GetPlayerPawn(this, 0)));
	UE_LOG(LogASTRA, Log, TEXT("[Hangar] %d zone lights, %d flight groups parked"), ZoneLights.Num(), Parked.Num());
}

bool AAstraHangar::IsPawnInHangar(const APawn* Pawn) const
{
	if (!Pawn)
	{
		return false;
	}
	const FVector L = GetActorTransform().InverseTransformPosition(Pawn->GetActorLocation());
	return L.X > -1200.f && L.X < HangarLength && FMath::Abs(L.Y) < HangarHalfWidth && L.Z > -300.f && L.Z < HangarHeight;
}

void AAstraHangar::SetZoneLights(bool bOn)
{
	if (bOn == bLightsOn)
	{
		return;
	}
	bLightsOn = bOn;
	for (ALight* L : ZoneLights)
	{
		if (L && L->GetLightComponent())
		{
			L->GetLightComponent()->SetVisibility(bOn);
		}
	}
}

FVector AAstraHangar::LandingWorld(int32 Index) const
{
	switch (Index)
	{
	case 0: return BridgeLanding;
	case 1: return GetActorTransform().TransformPosition(HangarLanding);
	case 2: return EngineeringLanding;
	case 3: return MedbayLanding;
	default: return FVector::ZeroVector;
	}
}

int32 AAstraHangar::NumLandings() const
{
	int32 N = 0;
	for (int32 i = 0; i < MaxLandings; ++i)
	{
		N += HasLanding(i) ? 1 : 0;
	}
	return N;
}

int32 AAstraHangar::LiftLandingNear(const APawn* Pawn) const
{
	if (!Pawn || LiftT >= 0.f || LiftCooldown > 0.f)
	{
		return -1;
	}
	const FVector P = Pawn->GetActorLocation();
	for (int32 i = 0; i < MaxLandings; ++i)
	{
		if (!HasLanding(i))
		{
			continue;
		}
		const FVector L = LandingWorld(i);
		if (FVector::Dist2D(P, L) < 320.f && FMath::Abs(P.Z - L.Z) < 400.f)
		{
			return i;
		}
	}
	return -1;
}

bool AAstraHangar::IsPawnInEngineering(const APawn* Pawn) const
{
	if (!Pawn || EngineeringLanding.IsNearlyZero())
	{
		return false;
	}
	const FVector D = Pawn->GetActorLocation() - EngineeringLanding;
	return D.X < 800.f && D.X > -5000.f && FMath::Abs(D.Y) < 1600.f && D.Z > -600.f && D.Z < 1800.f;
}

bool AAstraHangar::IsPawnInMedbay(const APawn* Pawn) const
{
	if (!Pawn || MedbayLanding.IsNearlyZero())
	{
		return false;
	}
	const FVector D = Pawn->GetActorLocation() - MedbayLanding;
	return D.X < 400.f && D.X > -2900.f && FMath::Abs(D.Y) < 950.f && D.Z > -300.f && D.Z < 600.f;
}

bool AAstraHangar::RideLift(APawn* Pawn, int32 ToLanding)
{
	const int32 From = LiftLandingNear(Pawn);
	if (From < 0 || !HasLanding(ToLanding) || ToLanding == From)
	{
		return false;
	}
	RideTo = LandingWorld(ToLanding);
	RideToLanding = ToLanding;
	Rider = Pawn;
	LiftT = 0.f;
	if (APlayerCameraManager* Cam = UGameplayStatics::GetPlayerCameraManager(this, 0))
	{
		Cam->StartCameraFade(0.f, 1.f, 0.4f, FLinearColor::Black, false, true);
	}
	if (LiftSound)
	{
		UGameplayStatics::PlaySound2D(this, LiftSound, 0.8f);
	}
	return true;
}

bool AAstraHangar::TryUseLift(APawn* Pawn)
{
	if (!Pawn || LiftT >= 0.f || LiftCooldown > 0.f)
	{
		return false;
	}
	const FVector P = Pawn->GetActorLocation();
	const FVector Down = GetActorTransform().TransformPosition(HangarLanding);
	const FVector Up = BridgeLanding;
	if (FVector::Dist2D(P, Up) < 320.f && FMath::Abs(P.Z - Up.Z) < 400.f)
	{
		RideTo = Down;
	}
	else if (FVector::Dist2D(P, Down) < 320.f && FMath::Abs(P.Z - Down.Z) < 400.f)
	{
		RideTo = Up;
	}
	else
	{
		return false;
	}
	Rider = Pawn;
	LiftT = 0.f;
	if (APlayerCameraManager* Cam = UGameplayStatics::GetPlayerCameraManager(this, 0))
	{
		Cam->StartCameraFade(0.f, 1.f, 0.4f, FLinearColor::Black, false, true);
	}
	if (LiftSound)
	{
		UGameplayStatics::PlaySound2D(this, LiftSound, 0.8f);
	}
	return true;
}

bool AAstraHangar::TryBoard(APawn* Pawn)
{
	TArray<FParked>* Alpha = Parked.Find(TEXT("alpha"));
	if (!Pawn || !Alpha || LiftT >= 0.f)
	{
		return false;
	}
	bool bNear = false;
	for (const FParked& P : *Alpha)
	{
		bNear |= P.Actor && !P.bAway && FVector::Dist2D(P.Actor->GetActorLocation(), Pawn->GetActorLocation()) < 900.f;
	}
	UAstraBattleSubsystem* Battle = GetWorld()->GetSubsystem<UAstraBattleSubsystem>();
	if (!bNear || !Battle || Battle->IsPiloting() || !Battle->TakeFalcon())
	{
		return false;
	}
	// the Falcon next in line leaves its bay while the screen is dark (the deck count is one fewer already)
	SyncSquadrons();
	for (FParked& P : *Alpha)
	{
		if (P.Anim >= 0.f)
		{
			P.Anim = -1.f;
			P.bAway = true;
			P.Actor->SetActorHiddenInGame(true);
		}
	}
	return true;
}

FTransform AAstraHangar::CatapultPose(float T) const
{
	// Alpha's track (port tube), from a cradle just ahead of the bays (the wings clear the parked Falcons) to clear of
	// the mouth; the eye 2.6 m over the deck (the Falcon's axis at 1.4 m, the pilot 1.2 m above it)
	const FVector Local(FMath::Lerp(CradleX, TubeEndX + 300.f, T), -TubeY, 260.f);
	return FTransform(GetActorRotation(), GetActorTransform().TransformPosition(Local));
}

float AAstraHangar::CatapultExitSpeed(float Seconds) const
{
	return 2.f * ((TubeEndX + 300.f) - CradleX) / 100.f / FMath::Max(0.1f, Seconds);
}

FTransform AAstraHangar::DeckSpot() const
{
	return FTransform(GetActorRotation(), GetActorTransform().TransformPosition(FVector(2800.f, -1150.f, 100.f)));
}

void AAstraHangar::Tick(float DeltaTime)
{
	Super::Tick(DeltaTime);
	LiftCooldown = FMath::Max(0.f, LiftCooldown - DeltaTime);
	// the lift ride: fade out, the car moves (a moment of dark and the hum), fade in on the other deck
	if (LiftT >= 0.f)
	{
		const float Before = LiftT;
		LiftT += DeltaTime;
		if (Before < 0.9f && LiftT >= 0.9f && Rider.IsValid())
		{
			float Half = 96.f;
			if (const ACharacter* C = Cast<ACharacter>(Rider.Get()))
			{
				Half = C->GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
			}
			Rider->SetActorLocation(RideTo + FVector(0, 0, Half), false, nullptr, ETeleportType::TeleportPhysics);
			if (AController* Ctl = Rider->GetController())
			{
				// out of the car facing into the deck: aft into Main Engineering and the Medbay, forward on the others
				Ctl->SetControlRotation(FRotator(0.f, RideToLanding >= 2 ? 180.f : (RideToLanding == 1 ? GetActorRotation().Yaw : 0.f), 0.f));
			}
			SetZoneLights(IsPawnInHangar(Rider.Get()));
			if (APlayerCameraManager* Cam = UGameplayStatics::GetPlayerCameraManager(this, 0))
			{
				Cam->StartCameraFade(1.f, 0.f, 0.7f, FLinearColor::Black, false, false);
			}
			if (LiftSound)
			{
				UGameplayStatics::PlaySound2D(this, LiftSound, 0.6f, 1.08f);
			}
		}
		if (LiftT > 1.8f)
		{
			LiftT = -1.f;
			LiftCooldown = 1.0f;
		}
	}
		if ((CheckT -= DeltaTime) <= 0.f)
	{
		CheckT = 0.25f;
		SetZoneLights(IsPawnInHangar(UGameplayStatics::GetPlayerPawn(this, 0)));
		const APawn* Me = UGameplayStatics::GetPlayerPawn(this, 0);
		auto Zone = [](TArray<TObjectPtr<ALight>>& Lights, bool& bOnNow, bool bIn)
		{
			if (bIn != bOnNow)
			{
				bOnNow = bIn;
				for (ALight* L : Lights)
				{
					if (L && L->GetLightComponent())
					{
						L->GetLightComponent()->SetVisibility(bIn);
					}
				}
			}
		};
		Zone(EngLights, bEngLightsOn, IsPawnInEngineering(Me));
		Zone(MedLights, bMedLightsOn, IsPawnInMedbay(Me));
		SyncSquadrons();
	}
	for (auto& KV : Parked)
	{
		for (FParked& P : KV.Value)
		{
			if (P.Anim >= 0.f)
			{
				Animate(P, KV.Key, DeltaTime);
			}
		}
	}
}

void AAstraHangar::SyncSquadrons()
{
	const UAstraBattleSubsystem* Battle = GetWorld()->GetSubsystem<UAstraBattleSubsystem>();
	if (!Battle)
	{
		return;
	}
	TMap<FString, int32> OnDeck;
	Battle->GetDeckState(OnDeck);
	for (auto& KV : Parked)
	{
		const int32* N = OnDeck.Find(KV.Key);
		if (!N)
		{
			continue;
		}
		TArray<FParked>& Craft = KV.Value;
		for (int32 i = 0; i < Craft.Num(); ++i)
		{
			FParked& P = Craft[i];
			if (!P.Actor)
			{
				continue;
			}
			const bool bHome = i < *N;
			if (bHome && P.bAway)
			{
				// landed and struck below: back in its bay
				P.bAway = false;
				P.Anim = -1.f;
				P.Actor->SetActorTransform(P.Home);
				P.Actor->SetActorHiddenInGame(false);
			}
			else if (!bHome && !P.bAway && P.Anim < 0.f)
			{
				P.Anim = 0.f;   // launch: taxi to the catapult, then down the tube
			}
		}
	}
}

void AAstraHangar::Animate(FParked& P, const FString& Squadron, float Dt)
{
	const float Before = P.Anim;
	P.Anim = FMath::Min(1.f, P.Anim + Dt / 6.f);
	const FTransform Me = GetActorTransform();
	const FVector Home = Me.InverseTransformPosition(P.Home.GetLocation());
	const float Tube = Squadron == TEXT("bravo") ? TubeY : (Squadron == TEXT("alpha") ? -TubeY : (Home.Y > 0 ? TubeY : -TubeY));
	const FVector Start(TrackStartX, Tube, Home.Z);
	const FVector End(TubeEndX, Tube, Home.Z);
	FVector L;
	float Yaw;
	if (P.Anim < 0.55f)
	{
		// taxi: roll out of the bay, swing onto the track facing the tube
		const float T = FMath::SmoothStep(0.f, 1.f, P.Anim / 0.55f);
		L = FMath::Lerp(Home, Start, T);
		const float HomeYaw = P.Home.Rotator().Yaw - GetActorRotation().Yaw;
		Yaw = FMath::Lerp(HomeYaw, 0.f, FMath::Clamp(T * 1.4f, 0.f, 1.f));
	}
	else
	{
		// the catapult: a hard, accelerating run down the track and out of the tube
		if (Before < 0.55f && CatapultSound)
		{
			UGameplayStatics::PlaySoundAtLocation(this, CatapultSound, Me.TransformPosition(Start), 1.f, FMath::FRandRange(0.95f, 1.05f));
		}
		const float T = (P.Anim - 0.55f) / 0.45f;
		L = FMath::Lerp(Start, End, T * T);
		Yaw = 0.f;
	}
	P.Actor->SetActorLocationAndRotation(Me.TransformPosition(L), FRotator(0.f, GetActorRotation().Yaw + Yaw, 0.f));
	if (P.Anim >= 1.f)
	{
		P.Anim = -1.f;
		P.bAway = true;
		P.Actor->SetActorHiddenInGame(true);
	}
}
