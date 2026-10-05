// ASTRA — the flight deck.

#include "AstraHangar.h"

#include "AstraShipSubsystem.h"

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

DECLARE_CYCLE_STAT(TEXT("Hangar"), STAT_AstraHangar, STATGROUP_Astra);

namespace
{
	const FName ZoneTag(TEXT("ASTRA.Zone.Hangar"));
	const FName EngZoneTag(TEXT("ASTRA.Zone.Engineering"));
	const FName MedZoneTag(TEXT("ASTRA.Zone.Medbay"));
	const FName MessZoneTag(TEXT("ASTRA.Zone.Mess"));
	const FName BerthZoneTag(TEXT("ASTRA.Zone.Berths"));
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
		else if (It->ActorHasTag(MessZoneTag))
		{
			if (ALight* L = Cast<ALight>(*It))
			{
				MessLights.Add(L);
			}
		}
		else if (It->ActorHasTag(BerthZoneTag))
		{
			if (ALight* L = Cast<ALight>(*It))
			{
				BerthLights.Add(L);
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

bool AAstraHangar::IsPawnInEngineering(const APawn* Pawn) const
{
	// only the Captain on foot is in a room (a Falcon crossing the hull, a lifepod: never)
	if (!Pawn || !Pawn->IsA<ACharacter>() || EngineeringLanding.IsNearlyZero())
	{
		return false;
	}
	const FVector D = Pawn->GetActorLocation() - EngineeringLanding;
	return D.X < 800.f && D.X > -5000.f && FMath::Abs(D.Y) < 1600.f && D.Z > -600.f && D.Z < 1800.f;
}

bool AAstraHangar::IsPawnInMedbay(const APawn* Pawn) const
{
	// only the Captain on foot is in a room (a Falcon crossing the hull, a lifepod: never)
	if (!Pawn || !Pawn->IsA<ACharacter>() || MedbayLanding.IsNearlyZero())
	{
		return false;
	}
	const FVector D = Pawn->GetActorLocation() - MedbayLanding;
	return D.X < 400.f && D.X > -2900.f && FMath::Abs(D.Y) < 950.f && D.Z > -300.f && D.Z < 600.f;
}

bool AAstraHangar::IsPawnInMess(const APawn* Pawn) const
{
	// only the Captain on foot is in a room (a Falcon crossing the hull, a lifepod: never)
	if (!Pawn || !Pawn->IsA<ACharacter>() || MessLanding.IsNearlyZero())
	{
		return false;
	}
	// the hall runs aft of its lift: 34 m long, 20 m wide
	const FVector D = Pawn->GetActorLocation() - MessLanding;
	return D.X < 400.f && D.X > -3600.f && FMath::Abs(D.Y) < 1100.f && D.Z > -300.f && D.Z < 700.f;
}

bool AAstraHangar::IsPawnInBerths(const APawn* Pawn) const
{
	if (!Pawn || !Pawn->IsA<ACharacter>() || BerthLanding.IsNearlyZero())
	{
		return false;
	}
	// the compartment runs 24 m aft of its lift, 7 m wide
	const FVector D = Pawn->GetActorLocation() - BerthLanding;
	return D.X < 400.f && D.X > -2500.f && FMath::Abs(D.Y) < 450.f && D.Z > -300.f && D.Z < 600.f;
}

bool AAstraHangar::TryBoard(APawn* Pawn)
{
	TArray<FParked>* Alpha = Parked.Find(TEXT("alpha"));
	if (!Pawn || !Alpha)
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

bool AAstraHangar::GetAlphaView(FVector& OutCenter, FVector& OutAlong, FVector& OutAcross) const
{
	const TArray<FParked>* Alpha = Parked.Find(TEXT("alpha"));
	FVector Sum = FVector::ZeroVector;
	int32 N = 0;
	for (const FParked& P : Alpha ? *Alpha : TArray<FParked>())
	{
		if (P.Actor && !P.bAway)
		{
			Sum += P.Home.GetLocation();
			++N;
		}
	}
	if (N == 0)
	{
		return false;
	}
	OutCenter = Sum / N;
	const FTransform Me = GetActorTransform();
	OutAlong = Me.GetUnitAxis(EAxis::X);
	const double Y = Me.InverseTransformPosition(OutCenter).Y;
	OutAcross = Me.GetUnitAxis(EAxis::Y) * (Y > 0.0 ? -1.0 : 1.0);
	return true;
}

FTransform AAstraHangar::DeckSpot() const
{
	return FTransform(GetActorRotation(), GetActorTransform().TransformPosition(FVector(2800.f, -1150.f, 100.f)));
}

void AAstraHangar::Tick(float DeltaTime)
{
	SCOPE_CYCLE_COUNTER(STAT_AstraHangar);
	Super::Tick(DeltaTime);
	if ((CheckT -= DeltaTime) <= 0.f)
	{
		CheckT = 0.25f;
		SetZoneLights(bShowcase || IsPawnInHangar(UGameplayStatics::GetPlayerPawn(this, 0)));
		const APawn* Me = UGameplayStatics::GetPlayerPawn(this, 0);
		auto Zone = [](TArray<TObjectPtr<ALight>>& Lights, bool& bOnNow, bool bIn) -> bool   // true: the Captain just came in
		{
			if (bIn == bOnNow)
			{
				return false;
			}
			bOnNow = bIn;
			for (ALight* L : Lights)
			{
				if (L && L->GetLightComponent())
				{
					L->GetLightComponent()->SetVisibility(bIn);
				}
			}
			return bIn;
		};
		const bool bToEng = Zone(EngLights, bEngLightsOn, IsPawnInEngineering(Me));
		const bool bToMed = Zone(MedLights, bMedLightsOn, IsPawnInMedbay(Me));
		const bool bToMess = Zone(MessLights, bMessLightsOn, IsPawnInMess(Me));
		const bool bToBerth = Zone(BerthLights, bBerthLightsOn, IsPawnInBerths(Me));
		// the ship notices where the Captain goes: the crew talks about it, the story remembers it
		if ((bToEng || bToMed || bToMess || bToBerth) && GetWorld()->GetTimeSeconds() > 5.0)
		{
			if (UAstraShipSubsystem* Ship = GetWorld()->GetSubsystem<UAstraShipSubsystem>())
			{
				Ship->PublishEvent(bToMed
					? FString::Printf(TEXT("the Captain came down to the Medbay to see the wounded (%s)"), *Ship->GetRoster().Summary())
					: bToMess ? FString(TEXT("the Captain came down to the Mess Hall on Deck 4, where the off-duty watch is eating"))
					: bToBerth ? FString(TEXT("the Captain came down to Crew Berthing on Deck 4, where the Red watch sleeps in its racks"))
					: FString(TEXT("the Captain came down to Main Engineering to see Chief Okonkwo and the reactor watch")), false);
			}
		}
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
