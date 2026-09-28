// ASTRA — damage effects on the bridge.

#include "AstraBridgeFX.h"

#include "AstraCrewMember.h"
#include "AstraShipSubsystem.h"
#include "Camera/PlayerCameraManager.h"
#include "Components/PointLightComponent.h"
#include "Engine/World.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/Light.h"
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshActor.h"
#include "EngineUtils.h"
#include "Kismet/GameplayStatics.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Sound/SoundBase.h"

namespace
{
	int32 GSparkRequests = 0;
	FAutoConsoleCommand CmdSparks(TEXT("astra.fx.sparks"), TEXT("Testing: a burst of sparks on the bridge"),
		FConsoleCommandDelegate::CreateLambda([]() { ++GSparkRequests; }));
	constexpr int32 MaxSparks = 180;
	constexpr float Gravity = 980.f;      // cm/s², the gravity plating
	constexpr float BridgeRadius = 1500.f;
}

AAstraBridgeFX::AAstraBridgeFX()
{
	PrimaryActorTick.bCanEverTick = true;
	SetRootComponent(CreateDefaultSubobject<USceneComponent>(TEXT("Root")));
}

void AAstraBridgeFX::BeginPlay()
{
	Super::BeginPlay();
	LineMesh = LoadObject<UStaticMesh>(nullptr, TEXT("/Game/ASTRA/Holo/SM_HOLO_Line.SM_HOLO_Line"));
	GlowMat = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/ASTRA/Materials/M_FX_Glow.M_FX_Glow"));
	SparkSound = LoadObject<USoundBase>(nullptr, TEXT("/Game/ASTRA/Audio/SW_Sparks.SW_Sparks"));
	Flash = NewObject<UPointLightComponent>(this, TEXT("SparkFlash"));
	Flash->SetupAttachment(GetRootComponent());
	Flash->RegisterComponent();
	Flash->SetMobility(EComponentMobility::Movable);
	Flash->SetIntensityUnits(ELightUnits::Lumens);
	Flash->SetIntensity(0.f);
	Flash->SetLightColor(FLinearColor(1.f, 0.62f, 0.3f));
	Flash->SetAttenuationRadius(700.f);
	Flash->SetCastShadows(false);
	Flash->SetVisibility(false);
	CollectSources();
}

void AAstraBridgeFX::CollectSources()
{
	// the bridge's light fixtures (sparks fall from the ceiling) and its consoles (sparks spit towards the operator)
	for (TActorIterator<AActor> It(GetWorld()); It; ++It)
	{
		const FVector P = It->GetActorLocation();
		if (FVector2D(P.X, P.Y).Size() > BridgeRadius)
		{
			continue;
		}
		if (It->ActorHasTag(TEXT("ASTRA.ShipLight")) && Cast<ALight>(*It))
		{
			Sources.Add({P - FVector(0, 0, 8.f), FVector(0, 0, -1)});
			SourceIsConsole.Add(false);
		}
		else if (const AStaticMeshActor* SM = Cast<AStaticMeshActor>(*It))
		{
			const UStaticMeshComponent* C = SM->GetStaticMeshComponent();
			if (C && C->GetStaticMesh() && (C->GetStaticMesh()->GetName().Contains(TEXT("Console")) ||
			                                C->GetStaticMesh()->GetName().Contains(TEXT("MasterDisplay"))))
			{
				const FBoxSphereBounds B = C->Bounds;
				const FVector Top = B.Origin + FVector(0, 0, B.BoxExtent.Z * 0.75f);
				// towards the room's centre, and up
				const FVector Out = (FVector(0, 0, Top.Z) - FVector(Top.X, Top.Y, Top.Z)).GetSafeNormal2D();
				Sources.Add({Top, (Out + FVector(0, 0, 1.2f)).GetSafeNormal()});
				SourceIsConsole.Add(true);
			}
		}
	}
	UE_LOG(LogTemp, Log, TEXT("[BridgeFX] %d spark sources"), Sources.Num());
}

int32 AAstraBridgeFX::TakeSlot()
{
	if (FreeSlots.Num())
	{
		return FreeSlots.Pop();
	}
	if (Pool.Num() >= MaxSparks || !LineMesh || !GlowMat)
	{
		return -1;
	}
	UStaticMeshComponent* C = NewObject<UStaticMeshComponent>(this);
	C->SetupAttachment(GetRootComponent());
	C->SetMobility(EComponentMobility::Movable);
	C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	C->SetCastShadow(false);
	C->RegisterComponent();
	C->SetStaticMesh(LineMesh);
	UMaterialInstanceDynamic* M = C->CreateDynamicMaterialInstance(0, GlowMat);
	Pool.Add(C);
	PoolMIDs.Add(M);
	return Pool.Num() - 1;
}

void AAstraBridgeFX::RandomBurst(float Strength)
{
	if (Sources.Num() == 0)
	{
		return;
	}
	// mostly where the Captain is looking (drama is for the eyes), sometimes behind them (heard, not seen)
	TArray<int32> Seen;
	if (const APlayerCameraManager* Cam = UGameplayStatics::GetPlayerCameraManager(this, 0))
	{
		const FVector Eye = Cam->GetCameraLocation(), Fwd = Cam->GetCameraRotation().Vector();
		for (int32 i = 0; i < Sources.Num(); ++i)
		{
			const FVector To = Sources[i].Key - Eye;
			if (FVector::DotProduct(To.GetSafeNormal(), Fwd) > 0.55f && To.Size() > 150.f)
			{
				Seen.Add(i);
			}
		}
	}
	const int32 Pick = (Seen.Num() && FMath::FRand() < 0.8f) ? Seen[FMath::RandHelper(Seen.Num())] : FMath::RandHelper(Sources.Num());
	Burst(Sources[Pick].Key, Sources[Pick].Value, Strength);
	if (SourceIsConsole[Pick])
	{
		// the officer at that console recoils; the bridge knows what happened
		AAstraCrewMember* Nearest = nullptr;
		float Best = 260.f;
		for (TActorIterator<AAstraCrewMember> It(GetWorld()); It; ++It)
		{
			const float D = FVector::Dist2D(It->GetActorLocation(), Sources[Pick].Key);
			if (D < Best)
			{
				Best = D;
				Nearest = *It;
			}
		}
		if (Nearest)
		{
			Nearest->Startle(Strength);
			if (UAstraShipSubsystem* Ship = GetWorld()->GetSubsystem<UAstraShipSubsystem>())
			{
				Ship->PublishEvent(FString::Printf(TEXT("bridge: the %s console shorted out in a shower of sparks (%s unhurt, the console flickers back)"),
				                                   *Nearest->StationId, *Nearest->DisplayName), false);
			}
		}
	}
}

void AAstraBridgeFX::Burst(const FVector& At, const FVector& Dir, float Strength)
{
	const int32 N = FMath::RoundToInt(FMath::Lerp(18.f, 55.f, FMath::Clamp(Strength, 0.f, 1.f)));
	// the deck under the burst (the bridge has a lower well): the sparks bounce there
	float Floor = At.Z - 400.f;
	FHitResult Hit;
	FCollisionQueryParams Q(SCENE_QUERY_STAT(AstraSparks), true);
	if (GetWorld()->LineTraceSingleByChannel(Hit, At + FVector(0, 0, -5.f), At - FVector(0, 0, 800.f), ECC_Visibility, Q))
	{
		Floor = Hit.Location.Z + 0.5f;
	}
	for (int32 i = 0; i < N; ++i)
	{
		const int32 Slot = TakeSlot();
		if (Slot < 0)
		{
			break;
		}
		FSpark Sp;
		Sp.Slot = Slot;
		Sp.Pos = At + FMath::VRand() * 3.f;
		const FVector D = (Dir + FMath::VRand() * 0.85f).GetSafeNormal();
		Sp.Vel = D * FMath::FRandRange(150.f, 520.f) * (0.7f + 0.6f * Strength);
		Sp.Life = FMath::FRandRange(0.5f, 1.6f);
		Sp.Floor = Floor;
		Sparks.Add(Sp);
		Pool[Slot]->SetVisibility(true);
	}
	Flash->SetWorldLocation(At);
	Flash->SetVisibility(true);
	FlashT = 0.3f;
	if (SparkSound)
	{
		UGameplayStatics::PlaySoundAtLocation(this, SparkSound, At, FMath::Lerp(0.5f, 1.f, Strength), FMath::FRandRange(0.9f, 1.1f));
	}
}

void AAstraBridgeFX::Tick(float DeltaTime)
{
	Super::Tick(DeltaTime);
	const float Dt = FMath::Min(DeltaTime, 0.05f);
	for (; GSparkRequests > 0; --GSparkRequests)
	{
		RandomBurst(FMath::FRandRange(0.4f, 1.f));
	}
	if (FlashT > 0.f)
	{
		FlashT -= Dt;
		// a stuttering arc: the light flickers as it dies
		Flash->SetIntensity(FlashT > 0.f ? 30000.f * (FlashT / 0.3f) * FMath::FRandRange(0.3f, 1.f) : 0.f);
		if (FlashT <= 0.f)
		{
			Flash->SetVisibility(false);
		}
	}
	for (int32 i = Sparks.Num() - 1; i >= 0; --i)
	{
		FSpark& S = Sparks[i];
		S.Age += Dt;
		if (S.Age >= S.Life)
		{
			Pool[S.Slot]->SetVisibility(false);
			FreeSlots.Push(S.Slot);
			Sparks.RemoveAtSwap(i);
			continue;
		}
		S.Vel.Z -= Gravity * Dt;
		S.Vel *= 1.f - 0.6f * Dt;   // air drag
		S.Pos += S.Vel * Dt;
		if (S.Pos.Z < S.Floor && S.Vel.Z < 0.f)   // bounce on the deck, losing most of the energy
		{
			S.Pos.Z = S.Floor;
			S.Vel.Z *= -0.28f;
			S.Vel.X *= 0.55f;
			S.Vel.Y *= 0.55f;
		}
		const float T = S.Age / S.Life;
		const float Speed = S.Vel.Size();
		const float Len = FMath::Clamp(Speed * 0.04f, 1.f, 16.f);   // motion streak
		UStaticMeshComponent* C = Pool[S.Slot];
		const FVector Dir = Speed > 1.f ? S.Vel / Speed : FVector::UpVector;
		C->SetWorldLocationAndRotation(S.Pos - Dir * Len, Dir.Rotation());
		const float Thick = 0.75f * (1.f - 0.5f * T);
		C->SetWorldScale3D(FVector(Len / 100.f, Thick, Thick));
		// white-hot to orange to a dull red as it cools
		const FLinearColor Col = T < 0.3f ? FMath::Lerp(FLinearColor(1.f, 0.95f, 0.8f), FLinearColor(1.f, 0.6f, 0.2f), T / 0.3f)
		                                   : FMath::Lerp(FLinearColor(1.f, 0.6f, 0.2f), FLinearColor(0.8f, 0.15f, 0.05f), (T - 0.3f) / 0.7f);
		if (UMaterialInstanceDynamic* M = PoolMIDs[S.Slot])
		{
			M->SetVectorParameterValue(TEXT("Color"), Col);
			M->SetScalarParameterValue(TEXT("Intensity"), 900.f * (1.f - T) * (1.f - T) + 20.f);
		}
	}
}
