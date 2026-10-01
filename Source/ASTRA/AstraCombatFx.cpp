#include "AstraCombatFx.h"

#include "ASTRA.h"
#include "Camera/PlayerCameraManager.h"
#include "Components/PointLightComponent.h"
#include "Components/SceneComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "GameFramework/Actor.h"
#include "Kismet/GameplayStatics.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
#include "Sound/SoundAttenuation.h"
#include "Sound/SoundBase.h"

DECLARE_CYCLE_STAT(TEXT("CombatFx"), STAT_AstraCombatFx, STATGROUP_Astra);

namespace
{
	constexpr int32 MaxParts = 160;              // tracers and sparks together
	constexpr int32 NumFlashes = 6;
	constexpr float SparkGravity = 980.f;
	constexpr float WhizRadiusCm = 130.f;
}

bool UAstraCombatFx::ShouldCreateSubsystem(UObject* Outer) const
{
	const UWorld* World = Cast<UWorld>(Outer);
	return World && (World->WorldType == EWorldType::Game || World->WorldType == EWorldType::PIE);
}

void UAstraCombatFx::OnWorldBeginPlay(UWorld& InWorld)
{
	Super::OnWorldBeginPlay(InWorld);
	FActorSpawnParameters P;
	P.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	Host = InWorld.SpawnActor<AActor>(FVector::ZeroVector, FRotator::ZeroRotator, P);
	if (!Host)
	{
		return;
	}
	USceneComponent* Root = NewObject<USceneComponent>(Host, TEXT("Root"));
	Host->SetRootComponent(Root);
	Root->RegisterComponent();
	LineMesh = LoadObject<UStaticMesh>(nullptr, TEXT("/Game/ASTRA/Holo/SM_HOLO_Line.SM_HOLO_Line"));
	GlowMat = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/ASTRA/Materials/M_FX_Glow.M_FX_Glow"));
	for (int32 i = 0; i < NumFlashes; ++i)
	{
		UPointLightComponent* L = NewObject<UPointLightComponent>(Host);
		L->SetupAttachment(Root);
		L->RegisterComponent();
		L->SetMobility(EComponentMobility::Movable);
		L->SetIntensityUnits(ELightUnits::Lumens);
		L->SetIntensity(0.f);
		L->SetLightColor(FLinearColor(1.f, 0.72f, 0.38f));
		L->SetAttenuationRadius(650.f);
		L->SetCastShadows(false);
		L->SetVisibility(false);
		Flashes.Add(L);
		FlashT.Add(0.f);
	}
	// a shot carries down a corridor: full up to 25 m, gone by 130 m (the walls and doors that shut it in are the level's, not a rule here)
	Attenuation = NewObject<USoundAttenuation>(this);
	Attenuation->Attenuation.bAttenuate = true;
	Attenuation->Attenuation.bSpatialize = true;
	Attenuation->Attenuation.AttenuationShape = EAttenuationShape::Sphere;
	Attenuation->Attenuation.DistanceAlgorithm = EAttenuationDistanceModel::NaturalSound;
	Attenuation->Attenuation.AttenuationShapeExtents = FVector(2500.f);
	Attenuation->Attenuation.FalloffDistance = 10500.f;
	Attenuation->Attenuation.dBAttenuationAtMax = -24.f;
	Attenuation->Attenuation.FalloffMode = ENaturalSoundFalloffMode::Continues;
}

void UAstraCombatFx::Deinitialize()
{
	if (Host)
	{
		Host->Destroy();
	}
	Host = nullptr;
	Pool.Reset();
	PoolMIDs.Reset();
	Flashes.Reset();
	Super::Deinitialize();
}

int32 UAstraCombatFx::TakeSlot()
{
	if (FreeSlots.Num())
	{
		return FreeSlots.Pop();
	}
	if (!Host || Pool.Num() >= MaxParts || !LineMesh || !GlowMat)
	{
		return INDEX_NONE;
	}
	UStaticMeshComponent* C = NewObject<UStaticMeshComponent>(Host);
	C->SetupAttachment(Host->GetRootComponent());
	C->SetMobility(EComponentMobility::Movable);
	C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	C->SetCastShadow(false);
	C->SetReceivesDecals(false);
	C->RegisterComponent();
	C->SetStaticMesh(LineMesh);
	UMaterialInstanceDynamic* M = C->CreateDynamicMaterialInstance(0, GlowMat);
	Pool.Add(C);
	PoolMIDs.Add(M);
	return Pool.Num() - 1;
}

void UAstraCombatFx::FreeSlot(int32 Slot)
{
	if (Pool.IsValidIndex(Slot))
	{
		Pool[Slot]->SetVisibility(false);
		FreeSlots.Push(Slot);
	}
}

void UAstraCombatFx::Paint(int32 Slot, const FVector& Pos, const FVector& Dir, float Len, float Thick, const FLinearColor& Color, float Intensity)
{
	if (!Pool.IsValidIndex(Slot))
	{
		return;
	}
	UStaticMeshComponent* C = Pool[Slot];
	// the line mesh is 100 cm long from its origin along +X: its origin is the tail, Pos is the head
	C->SetWorldLocationAndRotation(Pos - Dir * Len, Dir.Rotation());
	C->SetWorldScale3D(FVector(Len / 100.f, Thick, Thick));
	if (!C->IsVisible())
	{
		C->SetVisibility(true);
	}
	if (UMaterialInstanceDynamic* M = PoolMIDs[Slot])
	{
		M->SetVectorParameterValue(TEXT("Color"), Color);
		M->SetScalarParameterValue(TEXT("Intensity"), Intensity);
	}
}

USoundBase* UAstraCombatFx::SoundOf(const TCHAR* Path)
{
	if (!Path || !*Path)
	{
		return nullptr;
	}
	if (const TObjectPtr<USoundBase>* Have = Sounds.Find(Path))
	{
		return Have->Get();
	}
	USoundBase* S = LoadObject<USoundBase>(nullptr, Path);       // a sound that is not imported yet is just not heard (and not asked for again)
	Sounds.Add(Path, S);
	return S;
}

void UAstraCombatFx::PlaySoundAt(const TCHAR* Path, const FVector& At, float Volume, float Pitch)
{
	if (USoundBase* S = SoundOf(Path); S && GetWorld())
	{
		UGameplayStatics::PlaySoundAtLocation(GetWorld(), S, At, FRotator::ZeroRotator, Volume, Pitch, 0.f, Attenuation);
	}
}

void UAstraCombatFx::Tracer(const FVector& From, const FVector& To, const FLinearColor& Color, float Speed, float Length, float Thick)
{
	const float Dist = (float)FVector::Dist(From, To);
	if (Dist < 30.f || Tracers.Num() > 40)
	{
		return;
	}
	const int32 Slot = TakeSlot();
	if (Slot == INDEX_NONE)
	{
		return;
	}
	FTracer T;
	T.From = From;
	T.Dir = (To - From) / Dist;
	T.Dist = Dist;
	T.Speed = FMath::Max(1000.f, Speed);
	T.Len = FMath::Min(Length, Dist);
	T.Color = Color;
	T.Thick = Thick;
	T.Slot = Slot;
	Tracers.Add(T);
}

void UAstraCombatFx::Impact(const FVector& At, const FVector& Normal, ESurface Surface)
{
	const bool bFlesh = Surface == ESurface::Flesh;
	const int32 N = bFlesh ? 5 : 8;
	for (int32 i = 0; i < N && Sparks.Num() < 100; ++i)
	{
		const int32 Slot = TakeSlot();
		if (Slot == INDEX_NONE)
		{
			break;
		}
		FSpark S;
		S.Slot = Slot;
		S.Pos = At + Normal * 1.5f;
		const FVector D = (Normal + FMath::VRand() * (bFlesh ? 0.9f : 0.75f)).GetSafeNormal();
		S.Vel = D * FMath::FRandRange(bFlesh ? 60.f : 180.f, bFlesh ? 260.f : 620.f);
		S.Life = FMath::FRandRange(0.18f, bFlesh ? 0.5f : 0.45f);
		S.bDrop = bFlesh;
		S.Color = bFlesh ? FLinearColor(0.55f, 0.02f, 0.02f) : FLinearColor(1.f, 0.82f, 0.45f);
		Sparks.Add(S);
	}
	// the tick of a round on a bulkhead, the thud in a man (quiet: the shot's own sound carries the fight)
	if (Surface == ESurface::Metal)
	{
		PlaySoundAt(TEXT("/Game/ASTRA/Audio/SW_Bullet_Impact.SW_Bullet_Impact"), At, 0.55f, FMath::FRandRange(0.9f, 1.15f));
	}
	else
	{
		PlaySoundAt(TEXT("/Game/ASTRA/Audio/SW_Body_Hit.SW_Body_Hit"), At, 0.6f, FMath::FRandRange(0.9f, 1.1f));
	}
}

void UAstraCombatFx::MuzzleFlash(const FVector& At, const FVector& Dir, float Scale)
{
	// a light that lasts a few frames (the nearest free one; the oldest when all are lit)
	int32 Pick = 0;
	float Oldest = 1.0e9f;
	for (int32 i = 0; i < Flashes.Num(); ++i)
	{
		if (FlashT[i] <= 0.f)
		{
			Pick = i;
			Oldest = -1.f;
			break;
		}
		if (FlashT[i] < Oldest)
		{
			Oldest = FlashT[i];
			Pick = i;
		}
	}
	if (Flashes.IsValidIndex(Pick))
	{
		Flashes[Pick]->SetWorldLocation(At + Dir * 12.f);
		Flashes[Pick]->SetVisibility(true);
		Flashes[Pick]->SetIntensity(9000.f * Scale);
		FlashT[Pick] = 0.05f;
	}
	for (int32 i = 0; i < 3 && Sparks.Num() < 100; ++i)
	{
		const int32 Slot = TakeSlot();
		if (Slot == INDEX_NONE)
		{
			break;
		}
		FSpark S;
		S.Slot = Slot;
		S.Pos = At;
		S.Vel = (Dir + FMath::VRand() * 0.22f).GetSafeNormal() * FMath::FRandRange(900.f, 1800.f) * Scale;
		S.Life = FMath::FRandRange(0.04f, 0.09f);
		S.Color = FLinearColor(1.f, 0.9f, 0.55f);
		Sparks.Add(S);
	}
}

void UAstraCombatFx::Whiz(const FVector& Muzzle, const FVector& End)
{
	const APlayerCameraManager* Cam = GetWorld() ? UGameplayStatics::GetPlayerCameraManager(GetWorld(), 0) : nullptr;
	if (!Cam)
	{
		return;
	}
	const FVector Eye = Cam->GetCameraLocation();
	const double Now = GetWorld()->GetTimeSeconds();
	if (Now - LastWhizAt < 0.12)
	{
		return;
	}
	if (FMath::PointDistToSegment(Eye, Muzzle, End) < WhizRadiusCm && FVector::Dist(Eye, Muzzle) > 250.0)
	{
		LastWhizAt = Now;
		PlaySoundAt(TEXT("/Game/ASTRA/Audio/SW_Bullet_Whiz.SW_Bullet_Whiz"), Eye + (End - Muzzle).GetSafeNormal() * 40.f, 0.8f, FMath::FRandRange(0.85f, 1.2f));
	}
}

void UAstraCombatFx::Tick(float DeltaTime)
{
	SCOPE_CYCLE_COUNTER(STAT_AstraCombatFx);
	Super::Tick(DeltaTime);
	const float Dt = FMath::Min(DeltaTime, 0.05f);
	for (int32 i = 0; i < Flashes.Num(); ++i)
	{
		if (FlashT[i] > 0.f)
		{
			FlashT[i] -= Dt;
			if (FlashT[i] <= 0.f)
			{
				Flashes[i]->SetIntensity(0.f);
				Flashes[i]->SetVisibility(false);
			}
		}
	}
	for (int32 i = Tracers.Num() - 1; i >= 0; --i)
	{
		FTracer& T = Tracers[i];
		T.T += Dt;
		const float Head = T.Speed * T.T;
		if (Head - T.Len >= T.Dist)
		{
			FreeSlot(T.Slot);
			Tracers.RemoveAtSwap(i);
			continue;
		}
		const float H = FMath::Min(Head, T.Dist);
		const float Tail = FMath::Max(0.f, Head - T.Len);
		const float Len = FMath::Max(8.f, H - Tail);
		Paint(T.Slot, T.From + T.Dir * H, T.Dir, Len, T.Thick, T.Color, 700.f);
	}
	for (int32 i = Sparks.Num() - 1; i >= 0; --i)
	{
		FSpark& S = Sparks[i];
		S.Age += Dt;
		if (S.Age >= S.Life)
		{
			FreeSlot(S.Slot);
			Sparks.RemoveAtSwap(i);
			continue;
		}
		S.Vel.Z -= SparkGravity * Dt * (S.bDrop ? 0.8f : 1.f);
		S.Vel *= 1.f - 1.4f * Dt;
		S.Pos += S.Vel * Dt;
		const float T = S.Age / S.Life;
		const float Speed = S.Vel.Size();
		const float Len = FMath::Clamp(Speed * 0.035f, 0.8f, 14.f);
		const FVector Dir = Speed > 1.f ? S.Vel / Speed : FVector::UpVector;
		Paint(S.Slot, S.Pos, Dir, Len, S.bDrop ? 1.1f * (1.f - 0.4f * T) : 0.6f * (1.f - 0.5f * T), S.Color, (S.bDrop ? 30.f : 500.f) * (1.f - T) + 10.f);
	}
}
