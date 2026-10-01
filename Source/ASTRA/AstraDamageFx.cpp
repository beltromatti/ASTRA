// ASTRA — DISTRUZIONE: the damage effects near the Captain.

#include "AstraDamageFx.h"

#include "ASTRA.h"
#include "AstraBridgeFX.h"
#include "AstraDeckStreaming.h"
#include "AstraDoor.h"
#include "AstraShipSubsystem.h"
#include "Camera/PlayerCameraManager.h"
#include "Components/AudioComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/DecalComponent.h"
#include "Components/PointLightComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Components/TextRenderComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "GameFramework/Actor.h"
#include "GameFramework/Character.h"
#include "HAL/IConsoleManager.h"
#include "Kismet/GameplayStatics.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Misc/App.h"
#include "Sound/SoundAttenuation.h"
#include "Sound/SoundBase.h"

DECLARE_CYCLE_STAT(TEXT("Damage FX"), STAT_AstraDamageFx, STATGROUP_Astra);

namespace
{
	TAutoConsoleVariable<int32> CVarFx(TEXT("astra.damage.fx"), 1, TEXT("0 turns off the damage effects near the Captain (flames, smoke, fields, sparks, signs, sounds)"));
	TAutoConsoleVariable<float> CVarFxReach(TEXT("astra.damage.fx.reach"), 35.f, TEXT("How far from the Captain's eye a hazard still gets effects (m)"));
	TAutoConsoleVariable<float> CVarFxGlow(TEXT("astra.damage.fx.glow"), 1.f, TEXT("Multiplier on the brightness of the flames and the containment fields (if they look blown out or too faint)"));
	TAutoConsoleVariable<float> CVarFxSmoke(TEXT("astra.damage.fx.smoke"), 1.f, TEXT("Multiplier on the brightness and thickness of the smoke"));
	TAutoConsoleVariable<float> CVarFxVolume(TEXT("astra.damage.fx.volume"), 1.f, TEXT("Multiplier on the volume of the damage sounds"));
	TAutoConsoleVariable<int32> CVarFxFires(TEXT("astra.damage.fx.fires"), 3, TEXT("Rooms on fire that get flames at once"));
	TAutoConsoleVariable<int32> CVarFxHazes(TEXT("astra.damage.fx.hazes"), 3, TEXT("Rooms full of smoke that get puffs at once"));
	TAutoConsoleVariable<int32> CVarFxVents(TEXT("astra.damage.fx.vents"), 2, TEXT("Holes in the hull that get a field, streaming air and a scorch at once"));
	TAutoConsoleVariable<int32> CVarFxSparks(TEXT("astra.damage.fx.sparks"), 2, TEXT("Rooms where the conduits spit sparks at once"));

	constexpr int32 FxMaxStreaks = 40;
	constexpr int32 FxMaxLights = 2;
	constexpr int32 FxMaxScars = 3;
	constexpr int32 FxMaxParts[4] = {12, 16, 4, 4};        // flames, puffs, mist, fields
	enum { FxLoopFire, FxLoopVent, FxLoopField, FxLoopMist };

	/** A cheap smooth flicker in 0..1 (two sines): the flames' and the light's life. */
	float FxFlicker(float T, float Phase)
	{
		return 0.5f + 0.25f * FMath::Sin(T * 13.f + Phase) + 0.15f * FMath::Sin(T * 23.7f + Phase * 2.3f) + 0.10f * FMath::Sin(T * 41.f + Phase * 0.7f);
	}
}

// ------------------------------------------------------------------------------------------------------------------------------ the choice
void FAstraFxPlanner::HoleWall(const FBox& Room, const FVector& HoleAt, FVector& OutPoint, FVector& OutNormal)
{
	// the wall the hole is in: the face of the room that the point where the blow came in is nearest to
	const double D[6] = {FMath::Abs(HoleAt.X - Room.Min.X), FMath::Abs(HoleAt.X - Room.Max.X), FMath::Abs(HoleAt.Y - Room.Min.Y), FMath::Abs(HoleAt.Y - Room.Max.Y),
	                     FMath::Abs(HoleAt.Z - Room.Min.Z), FMath::Abs(HoleAt.Z - Room.Max.Z)};
	int32 Face = 0;
	for (int32 i = 1; i < 6; ++i)
	{
		Face = D[i] < D[Face] ? i : Face;
	}
	static const FVector Normals[6] = {FVector(-1, 0, 0), FVector(1, 0, 0), FVector(0, -1, 0), FVector(0, 1, 0), FVector(0, 0, -1), FVector(0, 0, 1)};
	OutNormal = Normals[Face];
	FVector P(FMath::Clamp(HoleAt.X, Room.Min.X + 20.0, Room.Max.X - 20.0), FMath::Clamp(HoleAt.Y, Room.Min.Y + 20.0, Room.Max.Y - 20.0),
	          FMath::Clamp(HoleAt.Z, Room.Min.Z + 80.0, FMath::Max(Room.Min.Z + 80.0, Room.Max.Z - 80.0)));
	switch (Face)
	{
	case 0: P.X = Room.Min.X; break;
	case 1: P.X = Room.Max.X; break;
	case 2: P.Y = Room.Min.Y; break;
	case 3: P.Y = Room.Max.Y; break;
	case 4: P.Z = Room.Min.Z; break;
	default: P.Z = Room.Max.Z; break;
	}
	OutPoint = P;
}

FVector FAstraFxPlanner::FlameSpot(const FAstraFxPlan::FFire& Fire, int32 Index, int32 Count)
{
	const FBox& B = Fire.Box;
	FRandomStream R(Fire.Comp * 7919 + Index * 104729 + Count * 31 + 17);
	// the first flame stands where the fire began; the others round it, farther as the fire grows
	const float Spread = Index == 0 ? 0.f : FMath::Lerp(70.f, 320.f, FMath::Clamp(Fire.Level, 0.f, 1.f));
	FVector P = Fire.Anchor + FVector(R.FRandRange(-1.f, 1.f), R.FRandRange(-1.f, 1.f), 0.f) * Spread;
	const FVector Size = B.GetSize();
	P.X = Size.X > 130.0 ? FMath::Clamp(P.X, B.Min.X + 50.0, B.Max.X - 50.0) : B.GetCenter().X;
	P.Y = Size.Y > 130.0 ? FMath::Clamp(P.Y, B.Min.Y + 50.0, B.Max.Y - 50.0) : B.GetCenter().Y;
	P.Z = B.Min.Z + 4.0;
	return P;
}

void FAstraFxPlanner::Plan(const FAstraDamageModel& Model, const FVector& Eye, const FAstraFxBudget& Budget, const TFunction<bool(const FVector& Cm)>& IsReady, FAstraFxPlan& Out)
{
	Out.Fires.Reset();
	Out.Hazes.Reset();
	Out.Vents.Reset();
	Out.Sparks.Reset();
	if (!Model.IsReady())
	{
		return;
	}
	const FAstraDamageMap& Map = Model.GetMap();
	const double Reach2 = FMath::Square((double)Budget.ReachCm);
	for (const TPair<int32, FAstraDmgState>& KV : Model.States())
	{
		const FAstraDmgState& S = KV.Value;
		if (S.bGutted || !Map.Comps.IsValidIndex(KV.Key))
		{
			continue;
		}
		const FAstraDmgComp& C = Map.Comps[KV.Key];
		if (C.Status == 0)
		{
			continue;                                                    // not built: there is nothing there to show it on
		}
		const bool bFire = S.Fire >= 0.05f;
		const bool bMist = S.Suppress > 0.f;
		const bool bSmoke = S.Smoke >= 0.15f && !bMist;
		const bool bVent = S.Hole >= 0.02f;
		const bool bSpark = S.Power < 0.9f && S.Wreck < 1.f && (S.ConduitId != 0 || S.HitAge < 8.f);
		if (!(bFire || bMist || bSmoke || bVent || bSpark))
		{
			continue;
		}
		const double D2 = C.Box.ComputeSquaredDistanceToPoint(Eye);
		if (D2 > Reach2 || Eye.Z < C.Box.Min.Z - 900.0 || Eye.Z > C.Box.Max.Z + 900.0)
		{
			continue;
		}
		if (IsReady && !IsReady(C.Box.GetCenter()))
		{
			continue;
		}
		const float Dist = (float)FMath::Sqrt(D2);
		auto Inside = [&C](const FVector& P)
		{
			return FVector(FMath::Clamp(P.X, C.Box.Min.X + 40.0, FMath::Max(C.Box.Min.X + 40.0, C.Box.Max.X - 40.0)), FMath::Clamp(P.Y, C.Box.Min.Y + 40.0, FMath::Max(C.Box.Min.Y + 40.0, C.Box.Max.Y - 40.0)), C.Box.Min.Z);
		};
		if (bFire)
		{
			FAstraFxPlan::FFire F;
			F.Comp = KV.Key;
			F.Level = S.Fire;
			F.Dist = Dist;
			F.Box = C.Box;
			F.Anchor = Inside(S.FireAt.IsZero() ? C.Box.GetCenter() : S.FireAt);
			Out.Fires.Add(F);
		}
		if (bSmoke || bMist)
		{
			FAstraFxPlan::FHaze H;
			H.Comp = KV.Key;
			H.Level = bMist ? FMath::Clamp(S.Suppress / 6.f, 0.f, 1.f) : S.Smoke;
			H.Dist = Dist;
			H.Box = C.Box;
			H.bMist = bMist;
			Out.Hazes.Add(H);
		}
		if (bVent)
		{
			FAstraFxPlan::FVent V;
			V.Comp = KV.Key;
			V.Hole = S.Hole;
			V.Air = S.Air;
			V.Dist = Dist;
			V.Field = S.Field;
			V.Stress = S.FieldStress;
			V.RadiusCm = FMath::Clamp(FMath::Sqrt(S.Hole / PI) * 100.f, 30.f, 220.f);
			HoleWall(C.Box, S.HoleAt.IsZero() ? C.Box.GetCenter() : S.HoleAt, V.At, V.Normal);
			Out.Vents.Add(V);
		}
		if (bSpark)
		{
			FAstraFxPlan::FSpark P;
			P.Comp = KV.Key;
			P.Level = FMath::Clamp(1.f - S.Power, 0.1f, 1.f);
			P.Dist = Dist;
			P.Box = C.Box;
			P.Anchor = Inside(S.BlowAt.IsZero() ? C.Box.GetCenter() : S.BlowAt);
			Out.Sparks.Add(P);
		}
	}
	// nearest first, each kind to its budget
	Out.Fires.Sort([](const FAstraFxPlan::FFire& A, const FAstraFxPlan::FFire& B) { return A.Dist < B.Dist; });
	Out.Hazes.Sort([](const FAstraFxPlan::FHaze& A, const FAstraFxPlan::FHaze& B) { return A.Dist < B.Dist; });
	Out.Vents.Sort([](const FAstraFxPlan::FVent& A, const FAstraFxPlan::FVent& B) { return A.Dist < B.Dist; });
	Out.Sparks.Sort([](const FAstraFxPlan::FSpark& A, const FAstraFxPlan::FSpark& B) { return A.Dist < B.Dist; });
	// (the suppression's mist counts against the hazes' budget, but its own limit is the smaller)
	int32 Mists = 0;
	Out.Hazes.RemoveAll([&Mists, &Budget](const FAstraFxPlan::FHaze& H) { return H.bMist && ++Mists > Budget.Mists; });
	if (Out.Fires.Num() > Budget.Fires) { Out.Fires.SetNum(Budget.Fires); }
	if (Out.Hazes.Num() > Budget.Hazes + Budget.Mists) { Out.Hazes.SetNum(Budget.Hazes + Budget.Mists); }
	if (Out.Vents.Num() > Budget.Vents) { Out.Vents.SetNum(Budget.Vents); }
	if (Out.Sparks.Num() > Budget.Sparks) { Out.Sparks.SetNum(Budget.Sparks); }
}

// ------------------------------------------------------------------------------------------------------------------------------ the subsystem
bool UAstraDamageFx::ShouldCreateSubsystem(UObject* Outer) const
{
	const UWorld* World = Cast<UWorld>(Outer);
	// (a headless bench has no scene to put effects in)
	return World && (World->WorldType == EWorldType::Game || World->WorldType == EWorldType::PIE) && FApp::CanEverRender();
}

void UAstraDamageFx::OnWorldBeginPlay(UWorld& InWorld)
{
	Super::OnWorldBeginPlay(InWorld);
	FActorSpawnParameters SP;
	SP.ObjectFlags |= RF_Transient;
	SP.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	FxActor = InWorld.SpawnActor<AActor>(AActor::StaticClass(), FTransform::Identity, SP);
	if (!FxActor)
	{
		return;
	}
#if WITH_EDITOR
	FxActor->SetActorLabel(TEXT("AstraDamageFx"));
#endif
	USceneComponent* Root = NewObject<USceneComponent>(FxActor, TEXT("Root"));
	FxActor->SetRootComponent(Root);
	Root->RegisterComponent();
	SphereMesh = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Sphere.Sphere"));
	LineMesh = LoadObject<UStaticMesh>(nullptr, TEXT("/Game/ASTRA/Holo/SM_HOLO_Line.SM_HOLO_Line"));
	BlastMat = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/ASTRA/Materials/M_FX_Blast.M_FX_Blast"));
	SmokeMat = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/ASTRA/Materials/M_FX_Smoke.M_FX_Smoke"));
	GlowMat = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/ASTRA/Materials/M_FX_Glow.M_FX_Glow"));
	ScarMat = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/ASTRA/Materials/M_FX_ScorchDecal.M_FX_ScorchDecal"));
	TextMat = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/ASTRA/Materials/M_ASTRA_HoloText.M_ASTRA_HoloText"));
	// the sounds are made by tools/art/damage_sounds.py and imported by tools/ue_scripts/import_damage_audio.py; any of them may be missing (that effect is silent)
	BlastSound = LoadObject<USoundBase>(nullptr, TEXT("/Game/ASTRA/Audio/SW_Blast_Inside.SW_Blast_Inside"));
	DecompressSound = LoadObject<USoundBase>(nullptr, TEXT("/Game/ASTRA/Audio/SW_Decompression.SW_Decompression"));
	SlamSound = LoadObject<USoundBase>(nullptr, TEXT("/Game/ASTRA/Audio/SW_Bulkhead_Slam.SW_Bulkhead_Slam"));
	static const TCHAR* LoopPaths[4] = {TEXT("/Game/ASTRA/Audio/SW_Fire_Loop.SW_Fire_Loop"), TEXT("/Game/ASTRA/Audio/SW_Vent_Loop.SW_Vent_Loop"),
	                                    TEXT("/Game/ASTRA/Audio/SW_Field_Hum.SW_Field_Hum"), TEXT("/Game/ASTRA/Audio/SW_Suppress_Loop.SW_Suppress_Loop")};
	for (int32 i = 0; i < 4; ++i)
	{
		USoundBase* S = LoadObject<USoundBase>(nullptr, LoopPaths[i]);
		Loops[i].Sound = S;
		if (S)
		{
			LoopSounds.Add(S);
		}
	}
	// what is heard from far off is faint and from near by is full: a sphere of full volume and a falloff out to some thirty metres
	Falloff = NewObject<USoundAttenuation>(this);
	Falloff->Attenuation.bAttenuate = true;
	Falloff->Attenuation.bSpatialize = true;
	Falloff->Attenuation.AttenuationShape = EAttenuationShape::Sphere;
	Falloff->Attenuation.AttenuationShapeExtents = FVector(500.f, 0.f, 0.f);
	Falloff->Attenuation.FalloffDistance = 3000.f;
	Falloff->Attenuation.DistanceAlgorithm = EAttenuationDistanceModel::NaturalSound;
	if (TextMat)
	{
		SignMid = UMaterialInstanceDynamic::Create(TextMat, this);
		if (SignMid)
		{
			SignMid->SetScalarParameterValue(TEXT("Intensity"), 7.f);
		}
	}
	UE_LOG(LogASTRA, Log, TEXT("[DamageFx] effects near the Captain: blast %s, smoke %s, glow %s, scorch %s; sounds %d of 4 loops, blast %s, bulkhead %s"), BlastMat ? TEXT("ok") : TEXT("MISSING"),
	       SmokeMat ? TEXT("ok") : TEXT("MISSING"), GlowMat ? TEXT("ok") : TEXT("MISSING"), ScarMat ? TEXT("ok") : TEXT("MISSING"), LoopSounds.Num(), BlastSound ? TEXT("ok") : TEXT("missing"),
	       SlamSound ? TEXT("ok") : TEXT("missing"));
}

void UAstraDamageFx::Deinitialize()
{
	for (FLoop& L : Loops)
	{
		if (UAudioComponent* A = L.Audio.Get())
		{
			A->Stop();
		}
	}
	if (FxActor)
	{
		FxActor->Destroy();
		FxActor = nullptr;
	}
	Insts.Reset();
	Streaks.Reset();
	Lights.Reset();
	Scars.Reset();
	Signs.Reset();
	for (TArray<FPart>& S : Spare)
	{
		S.Reset();
	}
	SpareStreaks.Reset();
	Super::Deinitialize();
}

bool UAstraDamageFx::CaptainEye(FVector& OutEye) const
{
	if (bTest)
	{
		OutEye = TestEye;
		return true;
	}
	// only the Captain on foot is among the compartments (a Falcon, the viewscreen's chair at the helm are out of it as the model sees it)
	const ACharacter* C = Cast<ACharacter>(UGameplayStatics::GetPlayerPawn(this, 0));
	const APlayerCameraManager* Cam = UGameplayStatics::GetPlayerCameraManager(this, 0);
	if (!C || !Cam)
	{
		return false;
	}
	OutEye = Cam->GetCameraLocation();
	return true;
}

bool UAstraDamageFx::Ready(const FVector& Cm) const
{
	const UAstraDeckStreaming* Decks = GetWorld() ? GetWorld()->GetSubsystem<UAstraDeckStreaming>() : nullptr;
	return !Decks || Decks->IsReadyAt(Cm);
}

// ------------------------------------------------------------------------------------------------------------------------------ parts
UAstraDamageFx::FPart UAstraDamageFx::TakePart(EPart Kind)
{
	TArray<FPart>& Pool = Spare[(int32)Kind];
	while (Pool.Num())
	{
		FPart P = Pool.Pop();
		if (P.Mesh.IsValid() && P.Mid.IsValid())
		{
			P.Mesh->SetVisibility(true);
			return P;
		}
	}
	FPart P;
	UMaterialInterface* Mat = Kind == EPart::Smoke || Kind == EPart::Mist ? SmokeMat.Get() : BlastMat.Get();
	if (!FxActor || !SphereMesh || !Mat)
	{
		return P;
	}
	UStaticMeshComponent* C = NewObject<UStaticMeshComponent>(FxActor);
	C->SetupAttachment(FxActor->GetRootComponent());
	C->SetMobility(EComponentMobility::Movable);
	C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	C->SetCastShadow(false);
	C->bReceivesDecals = false;
	C->RegisterComponent();
	C->SetStaticMesh(SphereMesh);
	P.Mid = C->CreateDynamicMaterialInstance(0, Mat);
	P.Mesh = C;
	return P;
}

void UAstraDamageFx::GiveBack(EPart Kind, FPart& P)
{
	if (UStaticMeshComponent* C = P.Mesh.Get())
	{
		C->SetVisibility(false);
		Spare[(int32)Kind].Add(P);
	}
	P = FPart();
}

void UAstraDamageFx::Upsert(EPart Kind, int32 Comp, int32 Index, const FVector& Pos, const FVector& Normal, float Size, float Strength, uint8 Mode, float Stress)
{
	FInst* Found = Insts.FindByPredicate([Kind, Comp, Index](const FInst& I) { return I.Kind == Kind && I.Comp == Comp && I.Index == Index; });
	if (!Found)
	{
		int32 Of = 0;
		for (const FInst& I : Insts)
		{
			Of += I.Kind == Kind ? 1 : 0;
		}
		if (Of >= FxMaxParts[(int32)Kind])
		{
			return;
		}
		FPart P = TakePart(Kind);
		if (!P.Mesh.IsValid())
		{
			return;
		}
		FInst I;
		I.Kind = Kind;
		I.Comp = Comp;
		I.Index = Index;
		I.Part = P;
		I.Phase = FMath::FRandRange(0.f, 6.28f);
		Insts.Add(I);
		Found = &Insts.Last();
	}
	Found->Pos = Pos;
	Found->Normal = Normal;
	Found->Size = Size;
	Found->Strength = Strength;
	Found->Mode = Mode;
	Found->Stress = Stress;
	Found->Target = 1.f;
}

void UAstraDamageFx::HideAll()
{
	for (FInst& I : Insts)
	{
		GiveBack(I.Kind, I.Part);
	}
	Insts.Reset();
	for (FStreak& S : Streaks)
	{
		if (UStaticMeshComponent* C = S.Part.Mesh.Get())
		{
			C->SetVisibility(false);
			SpareStreaks.Add(S.Part);
		}
	}
	Streaks.Reset();
	for (FLightSlot& L : Lights)
	{
		L.Target = 0.f;
		L.Level = 0.f;
		if (UPointLightComponent* C = L.Light.Get())
		{
			C->SetVisibility(false);
		}
	}
	for (FScar& S : Scars)
	{
		S.Target = 0.f;
		S.Level = 0.f;
		if (UDecalComponent* D = S.Decal.Get())
		{
			D->SetVisibility(false);
		}
	}
	for (FLoop& L : Loops)
	{
		L.bWanted = false;
		L.Target = 0.f;
	}
	Plan = FAstraFxPlan();
}

// ------------------------------------------------------------------------------------------------------------------------------ the plan
void UAstraDamageFx::Replan()
{
	UAstraShipSubsystem* Ship = GetWorld() ? GetWorld()->GetSubsystem<UAstraShipSubsystem>() : nullptr;
	FVector Eye;
	if (!Ship || !Ship->GetInterior().IsReady() || !CaptainEye(Eye))
	{
		if (bHaveEye)
		{
			bHaveEye = false;
			HideAll();
		}
		return;
	}
	bHaveEye = true;
	LastEye = Eye;
	FAstraFxBudget Budget;
	Budget.Fires = FMath::Clamp(CVarFxFires.GetValueOnGameThread(), 0, 8);
	Budget.Hazes = FMath::Clamp(CVarFxHazes.GetValueOnGameThread(), 0, 8);
	Budget.Vents = FMath::Clamp(CVarFxVents.GetValueOnGameThread(), 0, 4);
	Budget.Sparks = FMath::Clamp(CVarFxSparks.GetValueOnGameThread(), 0, 6);
	Budget.ReachCm = FMath::Clamp(CVarFxReach.GetValueOnGameThread(), 5.f, 120.f) * 100.f;
	FAstraFxPlanner::Plan(Ship->GetInterior(), Eye, Budget, [this](const FVector& Cm) { return Ready(Cm); }, Plan);

	// what the plan does not name again fades out; what it names is raised (or made)
	for (FInst& I : Insts)
	{
		I.Target = 0.f;
	}
	for (FLoop& L : Loops)
	{
		L.bWanted = false;
	}
	const float SmokeK = FMath::Max(0.f, CVarFxSmoke.GetValueOnGameThread());
	for (const FAstraFxPlan::FFire& F : Plan.Fires)
	{
		// flames: one where the fire began, more round it as it grows; a plume of smoke over the first
		const int32 Count = 1 + (F.Level > 0.35f ? 1 : 0) + (F.Level > 0.7f ? 1 : 0);
		for (int32 k = 0; k < Count; ++k)
		{
			Upsert(EPart::Flame, F.Comp, k, FAstraFxPlanner::FlameSpot(F, k, Count), FVector::UpVector, FMath::Lerp(60.f, 120.f, F.Level) * (k == 0 ? 1.f : 0.8f), F.Level, 0, 0.f);
		}
		const FVector Plume = FAstraFxPlanner::FlameSpot(F, 0, Count) + FVector(0.f, 0.f, FMath::Min(F.Box.GetSize().Z * 0.5f, 190.f));
		Upsert(EPart::Smoke, F.Comp, 10, Plume, FVector::UpVector, 130.f + 150.f * F.Level, F.Level * 0.8f * SmokeK, 0, 0.f);
		if (F.Dist < 3000.f)
		{
			WantLoop(FxLoopFire, FAstraFxPlanner::FlameSpot(F, 0, Count) + FVector(0.f, 0.f, 80.f), F.Level, 0.9f + 0.2f * F.Level);
		}
	}
	for (const FAstraFxPlan::FHaze& H : Plan.Hazes)
	{
		// puffs under the ceiling, toward the Captain's end of the room (where he would see them from)
		const FVector Size = H.Box.GetSize();
		const float Ceil = H.Box.Min.Z + FMath::Min((float)Size.Z, 380.f) - 70.f;
		const FVector Mid = H.Box.GetCenter();
		const FVector Toward(FMath::Clamp(LastEye.X, H.Box.Min.X + 60.0, H.Box.Max.X - 60.0), FMath::Clamp(LastEye.Y, H.Box.Min.Y + 60.0, H.Box.Max.Y - 60.0), Ceil);
		const float Span = FMath::Clamp((float)FMath::Min(Size.X, Size.Y) * 0.9f, 170.f, 420.f);
		const int32 Count = H.Level > 0.5f ? 2 : 1;
		for (int32 k = 0; k < Count; ++k)
		{
			const FVector At = FMath::Lerp(FVector(Mid.X, Mid.Y, Ceil), Toward, k == 0 ? 0.35f : 0.7f);
			Upsert(H.bMist ? EPart::Mist : EPart::Smoke, H.Comp, 20 + k, At, FVector::UpVector, Span * (0.7f + 0.5f * H.Level), H.bMist ? H.Level * 0.55f : H.Level * 0.75f * SmokeK, 0, 0.f);
		}
		if (H.bMist && H.Dist < 3000.f)
		{
			WantLoop(FxLoopMist, FVector(Mid.X, Mid.Y, Ceil), H.Level, 1.f);
		}
	}
	for (const FAstraFxPlan::FVent& V : Plan.Vents)
	{
		if (V.Field != FAstraDmgState::EField::Off)
		{
			const uint8 Mode = V.Field == FAstraDmgState::EField::Forming ? 1 : (V.Field == FAstraDmgState::EField::Holding ? 2 : 3);
			Upsert(EPart::Field, V.Comp, 0, V.At - V.Normal * 6.f, V.Normal, V.RadiusCm * 2.4f, 1.f, Mode, V.Stress);
			if (Mode != 3 && V.Dist < 3500.f)
			{
				WantLoop(FxLoopField, V.At, 1.f, 1.f);
			}
		}
		if (V.Field != FAstraDmgState::EField::Holding && V.Air > 0.05f && V.Dist < 3500.f)
		{
			WantLoop(FxLoopVent, V.At, FMath::Clamp(0.35f + 0.5f * FMath::Sqrt(V.Hole), 0.2f, 1.f) * FMath::Clamp(V.Air * 1.3f, 0.2f, 1.f), 0.9f + 0.2f * FMath::Min(V.Hole, 2.f) / 2.f);
		}
	}
	StepScars(0.f);
	StepLights(0.f);
	// sparks: a shower from where the blow landed every second or two, more often the worse the room
	for (const FAstraFxPlan::FSpark& S : Plan.Sparks)
	{
		float& Next = SparkNext.FindOrAdd(S.Comp, FMath::FRandRange(0.2f, 1.2f));
		if ((Next -= 0.25f) <= 0.f)
		{
			Next = FMath::FRandRange(1.1f, 3.4f) / FMath::Max(0.3f, S.Level);
			SparkShower(S, S.Level);
		}
	}
	for (auto It = SparkNext.CreateIterator(); It; ++It)
	{
		if (!Plan.Sparks.ContainsByPredicate([&It](const FAstraFxPlan::FSpark& S) { return S.Comp == It.Key(); }))
		{
			It.RemoveCurrent();
		}
	}
}

// ------------------------------------------------------------------------------------------------------------------------------ every frame
void UAstraDamageFx::Tick(float DeltaTime)
{
	SCOPE_CYCLE_COUNTER(STAT_AstraDamageFx);
	const double T0 = FPlatformTime::Seconds();
	const float Dt = FMath::Min(DeltaTime, 0.1f);
	Clock += Dt;
	if (CVarFx.GetValueOnGameThread() == 0)
	{
		if (bHaveEye || Insts.Num() || Streaks.Num())
		{
			bHaveEye = false;
			HideAll();
		}
		StepLoops(Dt);
		return;
	}
	PlanT += Dt;
	if (PlanT >= 0.25f)
	{
		PlanT = 0.f;
		Replan();
	}
	bool bSounding = false;
	for (const FLoop& L : Loops)
	{
		bSounding |= L.Level > 0.01f;
	}
	if (bHaveEye || Insts.Num() || Streaks.Num() || bSounding)
	{
		Animate(Dt);                                 // (also while a loop fades out after the Captain has left, or the room has gone calm)
	}
	MsAvg = MsAvg * 0.98 + (FPlatformTime::Seconds() - T0) * 1000.0 * 0.02;
}

void UAstraDamageFx::Animate(float Dt)
{
	const float Glow = FMath::Max(0.f, CVarFxGlow.GetValueOnGameThread());
	const float SmokeK = FMath::Max(0.f, CVarFxSmoke.GetValueOnGameThread());
	for (int32 n = Insts.Num() - 1; n >= 0; --n)
	{
		FInst& I = Insts[n];
		UStaticMeshComponent* M = I.Part.Mesh.Get();
		UMaterialInstanceDynamic* Mid = I.Part.Mid.Get();
		if (!M || !Mid)
		{
			Insts.RemoveAtSwap(n);
			continue;
		}
		I.Level = FMath::FInterpConstantTo(I.Level, I.Target, Dt, I.Target > I.Level ? 1.f / 0.6f : 1.f / 1.4f);
		if (I.Level <= 0.002f && I.Target <= 0.f)
		{
			GiveBack(I.Kind, I.Part);
			Insts.RemoveAtSwap(n);
			continue;
		}
		const bool bParams = Clock - I.Shown >= 0.083f;           // the material is set at 12 Hz, the transform every frame
		if (bParams)
		{
			I.Shown = Clock;
		}
		switch (I.Kind)
		{
		case EPart::Flame:
		{
			const float F = FxFlicker(Clock, I.Phase);
			const float Hgt = I.Size * (0.8f + 0.5f * F) * I.Level;
			const float Wid = I.Size * 0.62f * (0.9f + 0.2f * (1.f - F)) * I.Level;
			M->SetWorldLocationAndRotation(I.Pos + FVector(FMath::Sin(Clock * 3.1f + I.Phase) * 5.f, FMath::Cos(Clock * 2.7f + I.Phase) * 5.f, Hgt * 0.5f), FRotator(0.f, I.Phase * 57.f, 0.f));
			M->SetWorldScale3D(FVector(Wid, Wid, Hgt) / 100.f);
			if (bParams)
			{
				Mid->SetVectorParameterValue(TEXT("Color"), FLinearColor(1.f, 0.38f + 0.12f * F, 0.08f));
				Mid->SetScalarParameterValue(TEXT("Intensity"), (22.f + 40.f * I.Strength) * (0.7f + 0.6f * F) * Glow);
				Mid->SetScalarParameterValue(TEXT("Fade"), I.Level);
			}
			break;
		}
		case EPart::Smoke:
		case EPart::Mist:
		{
			const float Drift = Clock * 0.25f + I.Phase;
			M->SetWorldLocation(I.Pos + FVector(FMath::Sin(Drift) * 24.f, FMath::Cos(Drift * 0.83f) * 24.f, FMath::Sin(Drift * 0.6f) * 12.f));
			const float S = I.Size * (0.85f + 0.15f * I.Level) / 100.f;
			M->SetWorldScale3D(FVector(S, S, S * 0.7f));
			if (bParams)
			{
				const bool bMist = I.Kind == EPart::Mist;
				Mid->SetVectorParameterValue(TEXT("Color"), bMist ? FLinearColor(0.55f, 0.58f, 0.62f) : FLinearColor(0.13f, 0.125f, 0.12f));
				Mid->SetScalarParameterValue(TEXT("Intensity"), (bMist ? 22.f : 14.f) * SmokeK);
				Mid->SetScalarParameterValue(TEXT("Opacity"), FMath::Clamp(I.Strength * I.Level, 0.f, 0.92f));
			}
			break;
		}
		case EPart::Field:
		{
			// a disc of light on the hole, flat on the wall: calm cyan while it holds (it shivers more as it is strained), amber while it forms, red and ragged as it fails
			const float F = FxFlicker(Clock * (I.Mode == 3 ? 1.8f : 1.f), I.Phase);
			const float Shiver = I.Mode == 3 ? 0.7f : (I.Mode == 1 ? 0.35f : 0.08f + 0.5f * FMath::Clamp(I.Stress, 0.f, 1.f));
			const float D = I.Size / 100.f;
			M->SetWorldLocationAndRotation(I.Pos, FRotationMatrix::MakeFromZ(I.Normal).Rotator());
			M->SetWorldScale3D(FVector(D, D, D * 0.07f));
			if (bParams)
			{
				const FLinearColor Col = I.Mode == 3 ? FLinearColor(1.f, 0.1f, 0.06f) : (I.Mode == 1 ? FLinearColor(1.f, 0.62f, 0.12f) : FLinearColor(0.2f, 0.7f, 1.f));
				Mid->SetVectorParameterValue(TEXT("Color"), Col);
				Mid->SetScalarParameterValue(TEXT("Intensity"), 26.f * (1.f - Shiver + Shiver * F * 1.6f) * Glow);
				Mid->SetScalarParameterValue(TEXT("Fade"), I.Level);
			}
			break;
		}
		default:
			break;
		}
	}
	StepStreaks(Dt);
	StepLights(Dt);
	StepScars(Dt);
	StepLoops(Dt);
}

void UAstraDamageFx::StepStreaks(float Dt)
{
	if (!LineMesh || !GlowMat || !FxActor)
	{
		return;
	}
	// the air going out of a hole that nothing holds: streaks drawn toward it from inside the room
	float Rate = 0.f;
	const FAstraFxPlan::FVent* Source = nullptr;
	for (const FAstraFxPlan::FVent& V : Plan.Vents)
	{
		if (V.Field != FAstraDmgState::EField::Holding && V.Air > 0.08f)
		{
			const float R = FMath::Clamp(16.f * FMath::Sqrt(V.Hole) * V.Air, 3.f, 32.f);
			if (R > Rate)
			{
				Rate = R;
				Source = &V;
			}
		}
	}
	if (Source)
	{
		StreakCarry += Rate * Dt;
		for (; StreakCarry >= 1.f; StreakCarry -= 1.f)
		{
			if (Streaks.Num() >= FxMaxStreaks)
			{
				StreakCarry = 0.f;
				break;
			}
			FStreak S;
			if (SpareStreaks.Num())
			{
				S.Part = SpareStreaks.Pop();
			}
			if (!S.Part.Mesh.IsValid())
			{
				UStaticMeshComponent* C = NewObject<UStaticMeshComponent>(FxActor);
				C->SetupAttachment(FxActor->GetRootComponent());
				C->SetMobility(EComponentMobility::Movable);
				C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
				C->SetCastShadow(false);
				C->bReceivesDecals = false;
				C->RegisterComponent();
				C->SetStaticMesh(LineMesh);
				S.Part.Mid = C->CreateDynamicMaterialInstance(0, GlowMat);
				S.Part.Mesh = C;
			}
			if (UStaticMeshComponent* C = S.Part.Mesh.Get())
			{
				C->SetVisibility(true);
			}
			// from some way in front of the hole, spread across the wall's width and the room's height
			const FVector In = -Source->Normal;
			const FVector Side = FVector::CrossProduct(In, FVector::UpVector).GetSafeNormal();
			S.Hole = Source->At + In * 25.f;
			S.Pos = Source->At + In * FMath::FRandRange(90.f, 320.f) + (Side.IsNearlyZero() ? FVector::ForwardVector : Side) * FMath::FRandRange(-1.f, 1.f) * (60.f + Source->RadiusCm)
			        + FVector(0.f, 0.f, FMath::FRandRange(-1.f, 1.f) * (50.f + Source->RadiusCm));
			S.Vel = (S.Hole - S.Pos).GetSafeNormal() * 120.f;
			S.Life = FMath::FRandRange(0.6f, 1.1f);
			Streaks.Add(S);
		}
	}
	for (int32 i = Streaks.Num() - 1; i >= 0; --i)
	{
		FStreak& S = Streaks[i];
		UStaticMeshComponent* C = S.Part.Mesh.Get();
		UMaterialInstanceDynamic* Mid = S.Part.Mid.Get();
		S.Age += Dt;
		const FVector To = S.Hole - S.Pos;
		const float Dist = (float)To.Size();
		if (!C || !Mid || S.Age >= S.Life || Dist < 28.f)
		{
			if (C)
			{
				C->SetVisibility(false);
				SpareStreaks.Add(S.Part);
			}
			Streaks.RemoveAtSwap(i);
			continue;
		}
		S.Vel += (To / Dist) * 3400.f * Dt;
		S.Pos += S.Vel * Dt;
		const float Speed = (float)S.Vel.Size();
		const FVector Dir = S.Vel / FMath::Max(Speed, 1.f);
		const float Len = FMath::Clamp(Speed * 0.045f, 6.f, 70.f);
		const float K = S.Age / S.Life;
		C->SetWorldLocationAndRotation(S.Pos - Dir * Len * 0.5f, Dir.Rotation());
		C->SetWorldScale3D(FVector(Len / 100.f, 0.5f, 0.5f));
		Mid->SetVectorParameterValue(TEXT("Color"), FLinearColor(0.8f, 0.9f, 1.f));
		Mid->SetScalarParameterValue(TEXT("Intensity"), 160.f * FMath::Sin(K * PI) * FMath::Max(0.f, CVarFxGlow.GetValueOnGameThread()));
	}
}

void UAstraDamageFx::StepLights(float Dt)
{
	// the glow of the fires on the walls: the nearest two
	if (!FxActor)
	{
		return;
	}
	for (int32 k = 0; k < FxMaxLights; ++k)
	{
		const bool bHave = Plan.Fires.IsValidIndex(k);
		if (Lights.Num() <= k)
		{
			if (!bHave)
			{
				continue;
			}
			UPointLightComponent* L = NewObject<UPointLightComponent>(FxActor);
			L->SetupAttachment(FxActor->GetRootComponent());
			L->SetMobility(EComponentMobility::Movable);
			L->SetIntensityUnits(ELightUnits::Lumens);
			L->SetIntensity(0.f);
			L->SetLightColor(FLinearColor(1.f, 0.46f, 0.16f));
			L->SetCastShadows(false);
			L->RegisterComponent();
			L->SetVisibility(false);
			FLightSlot S;
			S.Light = L;
			S.Phase = FMath::FRandRange(0.f, 6.f);
			Lights.Add(S);
		}
		FLightSlot& S = Lights[k];
		UPointLightComponent* L = S.Light.Get();
		if (!L)
		{
			continue;
		}
		if (bHave)
		{
			const FAstraFxPlan::FFire& F = Plan.Fires[k];
			S.Comp = F.Comp;
			S.Pos = FAstraFxPlanner::FlameSpot(F, 0, 1) + FVector(0.f, 0.f, 110.f);
			S.Target = F.Level;
		}
		else
		{
			S.Target = 0.f;
		}
		if (Dt <= 0.f)
		{
			continue;                                      // (the plan's pass only points the lights; the frame's pass lights them)
		}
		S.Level = FMath::FInterpTo(S.Level, S.Target, Dt, 3.f);
		const bool bOn = S.Level > 0.01f;
		if (L->IsVisible() != bOn)
		{
			L->SetVisibility(bOn);
		}
		if (bOn)
		{
			const float F = FxFlicker(Clock, S.Phase);
			L->SetWorldLocation(S.Pos);
			L->SetIntensity((2600.f + 9000.f * S.Level) * S.Level * (0.65f + 0.7f * F) * FMath::Max(0.f, CVarFxGlow.GetValueOnGameThread()));
			L->SetAttenuationRadius(600.f + 600.f * S.Level);
		}
	}
}

void UAstraDamageFx::StepScars(float Dt)
{
	// the mark a hole leaves on the wall it came through: soot, bare metal and a molten rim, a deferred decal (the battle's scorch material)
	if (!FxActor || !ScarMat)
	{
		return;
	}
	for (FScar& S : Scars)
	{
		S.Target = 0.f;
	}
	for (const FAstraFxPlan::FVent& V : Plan.Vents)
	{
		FScar* S = Scars.FindByPredicate([&V](const FScar& X) { return X.Comp == V.Comp; });
		if (!S)
		{
			S = Scars.FindByPredicate([](const FScar& X) { return X.Level <= 0.f && X.Target <= 0.f; });
		}
		if (!S && Scars.Num() < FxMaxScars)
		{
			UDecalComponent* D = NewObject<UDecalComponent>(FxActor);
			D->SetupAttachment(FxActor->GetRootComponent());
			D->SetUsingAbsoluteScale(true);
			D->RegisterComponent();
			D->SetFadeScreenSize(0.0004f);
			UMaterialInstanceDynamic* M = UMaterialInstanceDynamic::Create(ScarMat, D);
			M->SetScalarParameterValue(TEXT("Heat"), 0.5f);
			M->SetScalarParameterValue(TEXT("Breach"), 1.f);
			M->SetScalarParameterValue(TEXT("Fade"), 0.f);
			D->SetDecalMaterial(M);
			D->SetVisibility(false);
			FScar X;
			X.Decal = D;
			X.Mid = M;
			Scars.Add(X);
			S = &Scars.Last();
		}
		if (!S || !S->Decal.IsValid())
		{
			continue;
		}
		if (S->Comp != V.Comp || S->Level <= 0.f)
		{
			// (re)pointed at this wall: it projects along its X axis into the wall, from a little inside the room
			S->Comp = V.Comp;
			const float Half = FMath::Clamp(V.RadiusCm * 2.4f, 90.f, 280.f);
			S->Decal->DecalSize = FVector(120.f, Half, Half);
			FRotator R = FRotationMatrix::MakeFromX(V.Normal).Rotator();
			R.Roll = (float)(V.Comp % 360);
			S->Decal->SetWorldLocationAndRotation(V.At - V.Normal * 30.f, R);
		}
		S->Target = 1.f;
	}
	for (FScar& S : Scars)
	{
		UDecalComponent* D = S.Decal.Get();
		UMaterialInstanceDynamic* M = S.Mid.Get();
		if (!D || !M || Dt <= 0.f || S.Level == S.Target)
		{
			continue;
		}
		S.Level = FMath::FInterpConstantTo(S.Level, S.Target, Dt, S.Target > S.Level ? 1.f : 0.2f);
		D->SetVisibility(S.Level > 0.002f);
		M->SetScalarParameterValue(TEXT("Fade"), S.Level);
	}
}

void UAstraDamageFx::WantLoop(int32 Which, const FVector& At, float Level, float Pitch)
{
	FLoop& L = Loops[Which];
	if (L.bWanted)
	{
		return;                                      // the nearest source (the plan is sorted, nearest first) holds it
	}
	L.bWanted = true;
	L.At = At;
	L.Target = FMath::Clamp(Level, 0.f, 1.f);
	L.Pitch = Pitch;
}

void UAstraDamageFx::StepLoops(float Dt)
{
	static const float Base[4] = {0.55f, 0.6f, 0.32f, 0.5f};
	const float Vol = FMath::Max(0.f, CVarFxVolume.GetValueOnGameThread());
	for (int32 i = 0; i < 4; ++i)
	{
		FLoop& L = Loops[i];
		if (!L.bWanted)
		{
			L.Target = 0.f;
		}
		USoundBase* Sound = L.Sound.Get();
		if (!Sound)
		{
			continue;
		}
		L.Level = FMath::FInterpConstantTo(L.Level, L.Target, Dt, 1.2f);
		UAudioComponent* A = L.Audio.Get();
		if (!A)
		{
			if (L.Level <= 0.01f && L.Target <= 0.f)
			{
				continue;
			}
			A = UGameplayStatics::SpawnSoundAtLocation(this, Sound, L.At, FRotator::ZeroRotator, 0.f, L.Pitch, 0.f, Falloff, nullptr, false);
			if (!A)
			{
				continue;
			}
			L.Audio = A;
		}
		else if (L.Level > 0.01f && !A->IsPlaying())
		{
			A->Play();
		}
		if (L.Level <= 0.01f && L.Target <= 0.f)
		{
			if (A->IsPlaying())
			{
				A->Stop();
			}
			continue;
		}
		A->SetWorldLocation(L.At);
		A->SetVolumeMultiplier(L.Level * Base[i] * Vol);
		A->SetPitchMultiplier(L.Pitch);
	}
}

void UAstraDamageFx::SparkShower(const FAstraFxPlan::FSpark& S, float Strength)
{
	UAstraShipSubsystem* Ship = GetWorld() ? GetWorld()->GetSubsystem<UAstraShipSubsystem>() : nullptr;
	AAstraBridgeFX* Sparks = Ship ? Ship->GetBridgeFX() : nullptr;
	if (!Sparks)
	{
		return;
	}
	// from a panel or a cable run at about head height or over it, thrown out and down
	const FVector At = S.Anchor + FVector(FMath::FRandRange(-1.f, 1.f) * 90.f, FMath::FRandRange(-1.f, 1.f) * 90.f, FMath::FRandRange(150.f, 250.f));
	const FVector Dir = FVector(FMath::FRandRange(-1.f, 1.f), FMath::FRandRange(-1.f, 1.f), -0.2f).GetSafeNormal();
	Sparks->Burst(At, Dir, FMath::Clamp(0.25f + 0.6f * Strength, 0.25f, 0.9f));
}

void UAstraDamageFx::PlayAt(USoundBase* Sound, const FVector& At, float Volume, float Pitch)
{
	if (Sound && Volume > 0.01f)
	{
		UGameplayStatics::PlaySoundAtLocation(this, Sound, At, FRotator::ZeroRotator, Volume * FMath::Max(0.f, CVarFxVolume.GetValueOnGameThread()), Pitch, 0.f, Falloff);
	}
}

// ------------------------------------------------------------------------------------------------------------------------------ events
void UAstraDamageFx::OnBlow(const FAstraImpactResult& R, float Energy)
{
	FVector Eye;
	if (CVarFx.GetValueOnGameThread() == 0 || !CaptainEye(Eye))
	{
		return;
	}
	// the nearest room the blow went off in that the Captain could hear
	int32 Best = INDEX_NONE;
	float BestD = 1.0e9f;
	FVector BestAt = FVector::ZeroVector;
	UAstraShipSubsystem* Ship = GetWorld() ? GetWorld()->GetSubsystem<UAstraShipSubsystem>() : nullptr;
	for (int32 i = 0; i < R.Comps.Num(); ++i)
	{
		FVector At = R.AtCm.IsValidIndex(i) ? R.AtCm[i] : FVector::ZeroVector;
		if (At.IsZero() && Ship && Ship->GetInterior().IsReady() && Ship->GetInterior().GetMap().Comps.IsValidIndex(R.Comps[i]))
		{
			At = Ship->GetInterior().GetMap().Comps[R.Comps[i]].Box.GetCenter();
		}
		const float D = (float)FVector::Dist(Eye, At);
		if (D < BestD && Ready(At))
		{
			Best = i;
			BestD = D;
			BestAt = At;
		}
	}
	if (Best == INDEX_NONE || BestD > 4500.f)
	{
		return;
	}
	const float Vol = FMath::Clamp(1.f - BestD / 4500.f, 0.1f, 1.f) * FMath::Lerp(0.55f, 1.f, FMath::Clamp(Energy / 60.f, 0.f, 1.f));
	if (Clock - LastBoom > 0.3f)
	{
		LastBoom = Clock;
		PlayAt(BlastSound, BestAt, Vol, FMath::FRandRange(0.92f, 1.08f));
		if (R.bBreach)
		{
			PlayAt(DecompressSound, BestAt, Vol * 0.9f);
		}
	}
	// a shower of sparks from the place, if it is in sight of him
	if (BestD < 1800.f && Ship && Ship->GetBridgeFX())
	{
		Ship->GetBridgeFX()->Burst(BestAt + FVector(0.f, 0.f, 120.f), FVector(FMath::FRandRange(-1.f, 1.f), FMath::FRandRange(-1.f, 1.f), 0.3f).GetSafeNormal(), FMath::Clamp(Energy / 50.f, 0.3f, 1.f));
	}
}

void UAstraDamageFx::OnBulkhead(const FVector& AtCm, bool bSealed)
{
	FVector Eye;
	if (!bSealed || CVarFx.GetValueOnGameThread() == 0 || !CaptainEye(Eye) || Clock - LastSlam < 0.35f)
	{
		return;
	}
	const float D = (float)FVector::Dist(Eye, AtCm);
	if (D > 6000.f)
	{
		return;
	}
	LastSlam = Clock;
	PlayAt(SlamSound, AtCm + FVector(0.f, 0.f, 120.f), FMath::Clamp(1.2f - D / 5000.f, 0.15f, 1.f));
}

void UAstraDamageFx::DressDoor(AAstraDoor* Door, bool bSealed)
{
	if (!Door)
	{
		return;
	}
	FSign& S = Signs.FindOrAdd(Door->GetUniqueID());
	if (bSealed && !S.Front.IsValid() && TextMat && SignMid)
	{
		// two faces, one each side of the door: a red warning (made once; shown while the door is sealed, never redrawn)
		for (int32 Side = 0; Side < 2; ++Side)
		{
			UTextRenderComponent* T = NewObject<UTextRenderComponent>(Door);
			T->SetupAttachment(Door->GetRootComponent());
			T->SetCollisionEnabled(ECollisionEnabled::NoCollision);
			T->SetCastShadow(false);
			T->SetTextMaterial(SignMid);
			T->SetHorizontalAlignment(EHTA_Center);
			T->SetVerticalAlignment(EVRTA_TextCenter);
			T->SetWorldSize(11.f);
			T->SetTextRenderColor(FColor(255, 64, 44));
			T->SetText(FText::FromString(TEXT("PRESSURE BULKHEAD<br>SEALED")));
			T->SetRelativeLocationAndRotation(FVector(Side == 0 ? 12.f : -12.f, 0.f, 175.f), FRotator(0.f, Side == 0 ? 0.f : 180.f, 0.f));
			T->RegisterComponent();
			(Side == 0 ? S.Front : S.Back) = T;
		}
	}
	S.Door = Door;
	S.bOn = bSealed;
	if (UTextRenderComponent* T = S.Front.Get())
	{
		T->SetVisibility(bSealed);
	}
	if (UTextRenderComponent* T = S.Back.Get())
	{
		T->SetVisibility(bSealed);
	}
	// the signs of doors that have gone with their deck leave the book
	for (auto It = Signs.CreateIterator(); It; ++It)
	{
		if (!It.Value().Door.IsValid())
		{
			It.RemoveCurrent();
		}
	}
}

// ------------------------------------------------------------------------------------------------------------------------------ what is shown
int32 UAstraDamageFx::NumParts() const
{
	int32 N = Insts.Num() + Streaks.Num();
	for (const FLightSlot& L : Lights) { N += L.Level > 0.01f ? 1 : 0; }
	for (const FScar& S : Scars) { N += S.Level > 0.01f ? 1 : 0; }
	for (const FLoop& L : Loops) { N += L.Audio.IsValid() && L.Level > 0.01f ? 1 : 0; }
	return N;
}

FString UAstraDamageFx::Describe() const
{
	int32 Counts[4] = {0, 0, 0, 0};
	for (const FInst& I : Insts)
	{
		++Counts[(int32)I.Kind];
	}
	int32 Signed = 0;
	for (const TPair<uint32, FSign>& KV : Signs)
	{
		Signed += KV.Value.bOn ? 1 : 0;
	}
	FString Out = FString::Printf(TEXT("%s; plan: %d fires, %d hazes, %d holes, %d spark rooms near the eye; parts: %d flames, %d smoke, %d mist, %d fields, %d streaks, %d lights, %d scars, %d signs; %.3f ms\n"),
	                              CVarFx.GetValueOnGameThread() ? TEXT("on") : TEXT("OFF"), Plan.Fires.Num(), Plan.Hazes.Num(), Plan.Vents.Num(), Plan.Sparks.Num(), Counts[0], Counts[1], Counts[2], Counts[3],
	                              Streaks.Num(), Lights.Num(), Scars.Num(), Signed, MsAvg);
	static const TCHAR* LoopNames[4] = {TEXT("fire"), TEXT("vent"), TEXT("field"), TEXT("mist")};
	for (int32 i = 0; i < 4; ++i)
	{
		Out += FString::Printf(TEXT("  loop %-5s %s level %.2f\n"), LoopNames[i], Loops[i].Sound.IsValid() ? TEXT("sound ok") : TEXT("no sound (not imported)"), Loops[i].Level);
	}
	return Out;
}

namespace
{
	FAutoConsoleCommandWithWorld CmdDamageFxInfo(TEXT("astra.damage.fx.info"), TEXT("The damage effects near the Captain: what the plan holds and which parts are on"),
		FConsoleCommandWithWorldDelegate::CreateLambda([](UWorld* World)
		{
			if (const UAstraDamageFx* Fx = World ? World->GetSubsystem<UAstraDamageFx>() : nullptr)
			{
				UE_LOG(LogASTRA, Log, TEXT("[DamageFx] %s"), *Fx->Describe());
			}
		}));
}
