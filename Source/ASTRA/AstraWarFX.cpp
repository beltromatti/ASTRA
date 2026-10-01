// ASTRA — the war's visual effects: the layers of instances, the shots, the beams, the particles, the drives, the lights.
// The events (blows, deaths, shields) are in AstraWarFXEvents.cpp, the hulls in AstraWarFXHull.cpp, the console in AstraWarFXTest.cpp.
// How it is meant to look and why it is built this way: docs/VFX.md.

#include "AstraWarFX.h"
#include "AstraBattleSubsystem.h"
#include "ASTRA.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Components/PointLightComponent.h"
#include "Components/SceneComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/World.h"
#include "HAL/PlatformTime.h"
#include "Kismet/GameplayStatics.h"
#include "Camera/PlayerCameraManager.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Components/DecalComponent.h"

namespace AstraFx
{
	namespace
	{
		TAutoConsoleVariable<int32> CVarEnable(TEXT("astra.fx.enable"), 1, TEXT("The war's visual effects (weapons, shields, explosions, break-ups, plumes): 0 off (the old drawing is used), 1 on"));
		TAutoConsoleVariable<float> CVarIntensity(TEXT("astra.fx.intensity"), 1.f, TEXT("Brightness of every effect (0.2..4)"));
		TAutoConsoleVariable<float> CVarDensity(TEXT("astra.fx.density"), 1.f, TEXT("How many particles an effect throws (0.2..2)"));
		TAutoConsoleVariable<float> CVarLights(TEXT("astra.fx.lights"), 1.f, TEXT("Strength of the flash lights of explosions (0 none)"));
		TAutoConsoleVariable<int32> CVarSim(TEXT("astra.fx.sim"), 1, TEXT("The effects' simulation also runs where nothing is drawn (the war bench), so its cost is measured: 1 yes"));
		TAutoConsoleVariable<int32> CVarLog(TEXT("astra.fx.log"), 0, TEXT("Log the effects' counters every N seconds (0 never)"));

		const FTransform& HiddenXf()
		{
			static const FTransform X(FQuat::Identity, FVector::ZeroVector, FVector(0.0001));
			return X;
		}
	}

	// -------------------------------------------------------------------------------------------------------------- layers
	void FLayer::Init(int32 InCapacity)
	{
		Capacity = InCapacity;
		Xf.SetNumUninitialized(Capacity);
		for (FTransform& T : Xf)
		{
			T = HiddenXf();
		}
		Data.SetNumZeroed(Capacity * Stride);
		Count = Prev = Peak = Dropped = 0;
	}

	float* FLayer::Next(FTransform*& OutXf)
	{
		static float Scratch[Stride];            // (a layer with no custom data hands this out and ignores it)
		if (Count >= Capacity)
		{
			++Dropped;
			return nullptr;
		}
		OutXf = &Xf[Count];
		float* D = NumData > 0 ? &Data[Count * Stride] : Scratch;
		++Count;
		Peak = FMath::Max(Peak, Count);
		return D;
	}

	void FLayer::Flush()
	{
		if (UInstancedStaticMeshComponent* C = Comp.Get())
		{
			const int32 N = FMath::Max(Count, Prev);
			if (N > 0)
			{
				for (int32 i = Count; i < Prev; ++i)
				{
					Xf[i] = HiddenXf();             // what was drawn last frame and is gone now
				}
				C->BatchUpdateInstancesTransforms(0, MakeArrayView(Xf.GetData(), N), false, false, false);
				if (NumData > 0)
				{
					C->SetCustomData(0, N - 1, MakeArrayView(Data.GetData(), N * Stride), false);
				}
			}
		}
		Prev = Count;
	}

	// -------------------------------------------------------------------------------------------------------------- colours
	FLinearColor ShotColor(bool bAstra, EAstraHitKind Kind)
	{
		switch (Kind)
		{
		case EAstraHitKind::Laser:        return bAstra ? FLinearColor(0.22f, 0.58f, 1.0f) : FLinearColor(1.0f, 0.16f, 0.07f);
		case EAstraHitKind::PointDefence: return FLinearColor(1.0f, 0.86f, 0.5f);
		case EAstraHitKind::Missile:      return bAstra ? FLinearColor(0.62f, 0.82f, 1.0f) : FLinearColor(1.0f, 0.46f, 0.16f);
		case EAstraHitKind::Torpedo:      return bAstra ? FLinearColor(0.45f, 0.92f, 1.0f) : FLinearColor(1.0f, 0.3f, 0.35f);
		case EAstraHitKind::Rocket:       return bAstra ? FLinearColor(0.7f, 0.85f, 1.0f) : FLinearColor(1.0f, 0.55f, 0.2f);
		case EAstraHitKind::Cannon:       return bAstra ? FLinearColor(0.55f, 0.85f, 1.0f) : FLinearColor(1.0f, 0.6f, 0.25f);
		default:                          return bAstra ? FLinearColor(0.42f, 0.7f, 1.0f) : FLinearColor(1.0f, 0.42f, 0.12f);   // rails
		}
	}

	FLinearColor ShieldColor(bool bAstra)
	{
		return bAstra ? FLinearColor(0.28f, 0.6f, 1.0f) : FLinearColor(1.0f, 0.5f, 0.14f);
	}

}

using namespace AstraFx;

// ------------------------------------------------------------------------------------------------------------------ setup
bool UAstraWarFX::LoadAssets()
{
	SphereMesh = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Sphere.Sphere"));
	CylinderMesh = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cylinder.Cylinder"));
	CubeMesh = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cube.Cube"));
	BallMesh = LoadObject<UStaticMesh>(nullptr, TEXT("/Game/ASTRA/FX/SM_WAR_Ball.SM_WAR_Ball"));   // optional: a finer sphere (tools/art/war_fx_meshes.py)
	if (!BallMesh)
	{
		BallMesh = SphereMesh;
	}
	const auto Mat = [](const TCHAR* Name) { return LoadObject<UMaterialInterface>(nullptr, *FString::Printf(TEXT("/Game/ASTRA/Materials/%s.%s"), Name, Name)); };
	MatDart = Mat(TEXT("M_WAR_Dart"));
	MatTube = Mat(TEXT("M_WAR_Tube"));
	MatGlow = Mat(TEXT("M_WAR_Glow"));
	MatFire = Mat(TEXT("M_WAR_Fire"));
	MatSmoke = Mat(TEXT("M_WAR_Smoke"));
	MatPlume = Mat(TEXT("M_WAR_Plume"));
	MatShield = Mat(TEXT("M_WAR_Shield"));
	static const TCHAR* const Dmg[8] = {TEXT("Burn"), TEXT("Hole"), TEXT("Torn"), TEXT("Impact"), TEXT("Strafe"), TEXT("Melt"), TEXT("Gouge"), TEXT("Blast")};
	DamageMats.Reset();
	for (const TCHAR* N : Dmg)
	{
		DamageMats.Add(LoadObject<UMaterialInterface>(nullptr, *FString::Printf(TEXT("/Game/ASTRA/Materials/Instances/MI_ShipDamage_%s.MI_ShipDamage_%s"), N, N)));
	}
	const bool bOk = SphereMesh && CylinderMesh && CubeMesh && MatDart && MatTube && MatGlow && MatFire && MatSmoke && MatPlume && MatShield;
	if (!bOk)
	{
		UE_LOG(LogASTRA, Warning, TEXT("[WarFX] materials missing (%s%s%s%s%s%s%s): the old drawing of shots, flashes and wrecks stays; run tools/ue_scripts/make_war_fx.py in the editor"),
		       MatDart ? TEXT("") : TEXT("M_WAR_Dart "), MatTube ? TEXT("") : TEXT("M_WAR_Tube "), MatGlow ? TEXT("") : TEXT("M_WAR_Glow "),
		       MatFire ? TEXT("") : TEXT("M_WAR_Fire "), MatSmoke ? TEXT("") : TEXT("M_WAR_Smoke "), MatPlume ? TEXT("") : TEXT("M_WAR_Plume "),
		       MatShield ? TEXT("") : TEXT("M_WAR_Shield "));
	}
	return bOk;
}

void UAstraWarFX::MakeLayer(FLayer& L, const TCHAR* Name, UStaticMesh* Mesh, UMaterialInterface* Mat, int32 Capacity, int32 SortPriority, bool bLit)
{
	L.Init(Capacity);
	if (!Host || !Mesh || !Mat)
	{
		return;
	}
	L.NumData = bLit ? 0 : Stride;
	UInstancedStaticMeshComponent* C = NewObject<UInstancedStaticMeshComponent>(Host, Name);
	C->SetupAttachment(Host->GetRootComponent());
	C->SetMobility(EComponentMobility::Movable);
	C->SetStaticMesh(Mesh);
	C->SetMaterial(0, Mat);
	C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	C->bDisableCollision = true;
	C->SetCanEverAffectNavigation(false);
	C->SetGenerateOverlapEvents(false);
	C->SetCastShadow(false);
	C->bCastDynamicShadow = false;
	C->bAffectDynamicIndirectLighting = false;
	C->bAffectDistanceFieldLighting = false;
	C->bNeverDistanceCull = true;
	C->bUseAsOccluder = false;
	C->SetReceivesDecals(false);
	C->SetTranslucentSortPriority(SortPriority);
	if (bLit)
	{
		C->SetLightingChannels(true, true, false);   // outside the hull: the star's light and the planet's, like the ships
	}
	C->SetNumCustomDataFloats(bLit ? 0 : Stride);
	TArray<FTransform> Init;
	Init.Init(HiddenXf(), Capacity);
	C->AddInstances(Init, false, false, false);
	C->RegisterComponent();
	L.Comp = C;
}

void UAstraWarFX::Init(UAstraBattleSubsystem* InOwner)
{
	Owner = InOwner;
	UWorld* World = Owner ? Owner->GetWorld() : nullptr;
	if (!World || bInitDone)
	{
		return;
	}
	bInitDone = true;
	Puffs.Reserve(CapPuffs);
	Sparks.Reserve(CapSparks);
	Beams.Reserve(CapBeams);
	Debris.Reserve(CapDebrisSim);
	for (FLayer* L : {&Darts, &Tubes, &Glows, &Fires, &Smokes, &Plumes, &DebrisA, &DebrisM})
	{
		L->Init(0);
	}
	if (!FApp::CanEverRender())
	{
		// the bench: the same simulation of effects, nothing drawn (its cost is part of the war's)
		bSim = CVarSim.GetValueOnGameThread() != 0;
		if (bSim)
		{
			Darts.Init(CapDarts); Tubes.Init(CapTubes); Glows.Init(CapGlows); Fires.Init(CapFires); Smokes.Init(CapSmokes);
			Plumes.Init(CapPlumes); DebrisA.Init(CapDebris); DebrisM.Init(CapDebris);
		}
		return;
	}
	if (!LoadAssets())
	{
		return;
	}
	FActorSpawnParameters P;
	P.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	P.ObjectFlags |= RF_Transient;
	Host = World->SpawnActor<AActor>(AActor::StaticClass(), FTransform::Identity, P);
	if (!Host)
	{
		return;
	}
	USceneComponent* Root = NewObject<USceneComponent>(Host, TEXT("FXRoot"));
	Host->SetRootComponent(Root);
	Root->SetMobility(EComponentMobility::Movable);
	Root->RegisterComponent();
	Host->Tags.Add(TEXT("ASTRA.Sky"));              // the main viewscreen's camera shows what is out there: tagged like the sky
	UMaterialInterface* HullA = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/ASTRA/Materials/Instances/MI_HULL_A_Plate.MI_HULL_A_Plate"));
	UMaterialInterface* HullM = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/ASTRA/Materials/Instances/MI_HULL_M_Frame.MI_HULL_M_Frame"));
	MakeLayer(Smokes, TEXT("FxSmoke"), SphereMesh, MatSmoke, CapSmokes, -2, false);
	MakeLayer(Fires, TEXT("FxFire"), SphereMesh, MatFire, CapFires, 0, false);
	MakeLayer(Plumes, TEXT("FxPlume"), CylinderMesh, MatPlume, CapPlumes, 1, false);
	MakeLayer(Tubes, TEXT("FxTube"), CylinderMesh, MatTube, CapTubes, 2, false);
	MakeLayer(Darts, TEXT("FxDart"), SphereMesh, MatDart, CapDarts, 3, false);
	MakeLayer(Glows, TEXT("FxGlow"), SphereMesh, MatGlow, CapGlows, 4, false);
	MakeLayer(DebrisA, TEXT("FxDebrisA"), CubeMesh, HullA ? HullA : MatGlow.Get(), CapDebris, 0, true);
	MakeLayer(DebrisM, TEXT("FxDebrisM"), CubeMesh, HullM ? HullM : MatGlow.Get(), CapDebris, 0, true);
	// the flash lights: exterior only (lighting channel 1: the hulls are on it, the bridge's interior is not)
	for (int32 i = 0; i < MaxLights; ++i)
	{
		UPointLightComponent* L = NewObject<UPointLightComponent>(Host, *FString::Printf(TEXT("FxLight%d"), i));
		L->SetupAttachment(Host->GetRootComponent());
		L->SetMobility(EComponentMobility::Movable);
		L->SetIntensityUnits(ELightUnits::Candelas);
		L->SetIntensity(0.f);
		L->SetCastShadows(false);
		L->SetLightingChannels(false, true, false);
		L->SetAttenuationRadius(1000.f);
		L->SetSourceRadius(40.f);
		L->SetVisibility(false);
		L->RegisterComponent();
		Lights.Add(L);
	}
	bLive = true;
	UE_LOG(LogASTRA, Log, TEXT("[WarFX] effects ready: darts %d, tubes %d, glows %d, fire %d, smoke %d, plumes %d, debris %d x2, lights %d"),
	       CapDarts, CapTubes, CapGlows, CapFires, CapSmokes, CapPlumes, CapDebris, MaxLights);
}

bool UAstraWarFX::IsActive() const
{
	return (bLive || bSim) && AstraFx::CVarEnable.GetValueOnGameThread() != 0;
}

void UAstraWarFX::Reset()
{
	ClearAll();
}

void UAstraWarFX::ClearAll()
{
	Puffs.Reset();
	Sparks.Reset();
	Beams.Reset();
	Debris.Reset();
	Tracks.Reset();
	FreeTracks.Reset();
	FlashLights.Reset();
	Timed.Reset();
	for (FScar& S : Scars)
	{
		if (UDecalComponent* D = S.Decal.Get())
		{
			D->DestroyComponent();
		}
	}
	Scars.Reset();
	for (FPiece& P : Pieces)
	{
		if (AStaticMeshActor* A = P.Actor.Get())
		{
			A->Destroy();
		}
	}
	Pieces.Reset();
	for (TPair<int32, FShipFx>& It : ShipFx)
	{
		if (AStaticMeshActor* A = It.Value.Shield.Actor.Get())
		{
			A->Destroy();
		}
	}
	ShipFx.Reset();
	for (FLayer* L : {&Darts, &Tubes, &Glows, &Fires, &Smokes, &Plumes, &DebrisA, &DebrisM})
	{
		L->Begin();
	}
}

AstraFx::FShipFx& UAstraWarFX::ShipOf(int32 Id)
{
	return ShipFx.FindOrAdd(Id);
}

FVector UAstraWarFX::PlayerEye() const
{
	if (const UWorld* W = Owner ? Owner->GetWorld() : nullptr)
	{
		if (const APlayerCameraManager* Cam = UGameplayStatics::GetPlayerCameraManager(W, 0))
		{
			return Cam->GetCameraLocation();
		}
	}
	return FVector::ZeroVector;
}

// ------------------------------------------------------------------------------------------------------------------ spawning
AstraFx::FPuff* UAstraWarFX::AddPuff(const FVector& Pos, const FVector& Vel, float Life, float R0, float R1, const FLinearColor& Col, float Inten, uint8 Layer, float Delay)
{
	if (Puffs.Num() >= CapPuffs)
	{
		return nullptr;
	}
	FPuff& P = Puffs.AddDefaulted_GetRef();
	P.Pos = Pos;
	P.Vel = Vel;
	P.Age = -Delay;
	P.Life = FMath::Max(Life, 0.05f);
	P.R0 = R0;
	P.R1 = R1;
	P.Col = Col;
	P.Inten = Inten;
	P.Layer = Layer;
	P.Seed = FMath::FRand();
	return &P;
}

AstraFx::FSpark* UAstraWarFX::AddSpark(const FVector& Pos, const FVector& Vel, float Life, float Len, float Width, const FLinearColor& Col, float Inten, float Drag)
{
	if (Sparks.Num() >= CapSparks)
	{
		return nullptr;
	}
	FSpark& S = Sparks.AddDefaulted_GetRef();
	S.Pos = Pos;
	S.Vel = Vel;
	S.Life = FMath::Max(Life, 0.05f);
	S.Len = Len;
	S.Width = Width;
	S.Col = Col;
	S.Inten = Inten;
	S.Drag = Drag;
	S.Seed = FMath::FRand();
	return &S;
}

void UAstraWarFX::SparkBurst(const FVector& Pos, const FVector& Dir, float Spread, int32 N, float SpeedLo, float SpeedHi, float LifeLo, float LifeHi,
                             float Len, const FLinearColor& Col, float Inten, const FVector& BaseVel)
{
	const float K = FMath::Clamp(Density, 0.2f, 2.f);
	N = FMath::Max(1, FMath::RoundToInt(N * K));
	for (int32 i = 0; i < N; ++i)
	{
		const FVector D = (Dir + FMath::VRand() * Spread).GetSafeNormal();
		AddSpark(Pos, BaseVel + D * FMath::FRandRange(SpeedLo, SpeedHi), FMath::FRandRange(LifeLo, LifeHi), Len * FMath::FRandRange(0.6f, 1.4f),
		         FMath::FRandRange(0.5f, 1.3f), Col, Inten * FMath::FRandRange(0.7f, 1.2f), 0.4f);
	}
}

void UAstraWarFX::AddLight(const FVector& Pos, float Life, float Radius, float Candela, const FLinearColor& Col, const FVector& Vel, float Delay)
{
	if (!bLive || LightScale <= 0.f || FlashLights.Num() >= 24)
	{
		return;
	}
	FFlashLight& L = FlashLights.AddDefaulted_GetRef();
	L.Pos = Pos;
	L.Vel = Vel;
	L.Age = -Delay;
	L.Life = FMath::Max(Life, 0.05f);
	L.Radius = Radius;
	L.Inten = FMath::Min(Candela * LightScale, 4.e9f);
	L.Col = Col;
}

void UAstraWarFX::AddDebris(const FVector& Pos, const FVector& Vel, float SizeM, bool bAstra, float Life)
{
	if (Debris.Num() >= CapDebrisSim)
	{
		return;
	}
	FDebris& D = Debris.AddDefaulted_GetRef();
	D.Pos = Pos;
	D.Vel = Vel;
	D.Att = FQuat(FMath::VRand(), FMath::FRandRange(0.f, 6.28f));
	D.SpinAxis = FMath::VRand();
	D.SpinRate = FMath::FRandRange(0.3f, 2.4f);
	D.Size = FVector(SizeM * FMath::FRandRange(0.6f, 1.5f), SizeM * FMath::FRandRange(0.3f, 1.0f), SizeM * FMath::FRandRange(0.08f, 0.45f));
	D.Life = Life;
	D.bAstra = bAstra;
	D.Glow = FMath::FRandRange(0.4f, 2.2f);
}

// ------------------------------------------------------------------------------------------------------------------ a frame
void UAstraWarFX::BeginFrame()
{
	const FAstraBattleShip& A = Owner->Ships[0];
	F.Origin = A.Pos;
	F.Att = A.Att;
	F.InvAtt = A.Att.Inverse();
	F.Vel = A.Vel;
	F.Bridge = Owner->BridgeOffset;
	Intensity = FMath::Clamp(CVarIntensity.GetValueOnGameThread(), 0.1f, 6.f);
	Density = FMath::Clamp(CVarDensity.GetValueOnGameThread(), 0.2f, 2.f);
	LightScale = FMath::Clamp(CVarLights.GetValueOnGameThread(), 0.f, 4.f);
	for (FLayer* L : {&Darts, &Tubes, &Glows, &Fires, &Smokes, &Plumes, &DebrisA, &DebrisM})
	{
		L->Begin();
	}
}

void UAstraWarFX::EndFrame()
{
	for (FLayer* L : {&Darts, &Tubes, &Glows, &Fires, &Smokes, &Plumes, &DebrisA, &DebrisM})
	{
		L->Flush();
	}
}

void UAstraWarFX::Tick(float InDt)
{
	if (!IsActive() || !Owner || Owner->Ships.Num() == 0)
	{
		return;
	}
	if (CVarEnable.GetValueOnGameThread() == 0)
	{
		if (bLive && Host)
		{
			BeginFrame();                      // (hides what was drawn: every layer is written empty)
			EndFrame();
		}
		return;
	}
	const double T0 = FPlatformTime::Seconds();
	Dt = FMath::Clamp(InDt, 0.f, 0.1f);
	Clock += Dt;
	++Frame;
	BeginFrame();
	RunTests();                            // what astra.fx.* asked for (AstraWarFXTest.cpp)
	TickTimed();
	TickShips();
	TickPieces();
	DrawShots();
	DrawBeams();
	DrawPuffs();
	DrawSparks();
	DrawDebris();
	DrawDrives();
	TickShields();
	TickLights();
	TickScars();
	EndFrame();
	const double Ms = (FPlatformTime::Seconds() - T0) * 1000.0;
	TickMs += Ms;
	TickMsMax = FMath::Max(TickMsMax, Ms);
	++TickCount;
	const int32 LogEvery = CVarLog.GetValueOnGameThread();
	if (LogEvery > 0 && (StatClock += Dt) >= LogEvery)
	{
		StatClock = 0.f;
		FString S;
		Stats(S);
		UE_LOG(LogASTRA, Log, TEXT("[WarFX] %s"), *S);
	}
}

void UAstraWarFX::Stats(FString& Out) const
{
	Out = FString::Printf(TEXT("%s | %.3f ms/frame (max %.2f) over %d frames | instances now/peak: darts %d/%d tubes %d/%d glows %d/%d fire %d/%d smoke %d/%d plumes %d/%d debris %d+%d | "
	                           "dropped (full): darts %d tubes %d glows %d fire %d smoke %d | puffs %d sparks %d beams %d tracks %d pieces %d scars %d lights %d"),
	                      bLive ? TEXT("drawing") : (bSim ? TEXT("bench (not drawn)") : TEXT("off")), TickCount ? TickMs / TickCount : 0.0, TickMsMax, TickCount,
	                      Darts.Prev, Darts.Peak, Tubes.Prev, Tubes.Peak, Glows.Prev, Glows.Peak, Fires.Prev, Fires.Peak, Smokes.Prev, Smokes.Peak,
	                      Plumes.Prev, Plumes.Peak, DebrisA.Prev, DebrisM.Prev, Darts.Dropped, Tubes.Dropped, Glows.Dropped, Fires.Dropped, Smokes.Dropped,
	                      Puffs.Num(), Sparks.Num(), Beams.Num(), Tracks.Num() - FreeTracks.Num(), Pieces.Num(), Scars.Num(), FlashLights.Num());
}

// ------------------------------------------------------------------------------------------------------------------ the shots
int32 UAstraWarFX::OnProjectile(const FAstraBattleShip& From, const FAstraBattleShip& To, const FAstraProjectile& Pr)
{
	if (!IsActive())
	{
		return -1;
	}
	const bool bAstra = From.Side == EAstraSide::Astra;
	const bool bRail = Pr.Kind == EAstraProjKind::Rail;
	FTrack* T;
	int32 Slot;
	if (FreeTracks.Num())
	{
		Slot = FreeTracks.Pop(EAllowShrinking::No);
		T = &Tracks[Slot];
	}
	else
	{
		Slot = Tracks.AddDefaulted();
		T = &Tracks[Slot];
	}
	*T = FTrack();
	T->Frame = Frame;
	T->Style = bRail ? 0 : (Pr.bTorpedo ? 2 : (Pr.HitKind == EAstraHitKind::Rocket ? 3 : 1));
	T->Col = ShotColor(bAstra, Pr.HitKind);
	// where it is drawn from: the gun's muzzle on the hull (the simulation starts it a little off, along the aim)
	const FVector Aim = (Pr.Vel - From.Vel).GetSafeNormal();
	FVector Muzzle = bRail ? MuzzleOf(From, EAstraMountKind::Rail, Aim, Slot) : MuzzleOf(From, EAstraMountKind::Laser, FVector(0.0, 0.0, 1.0), Slot);
	if (!bRail)
	{
		// a missile climbs out of the launch cells on the upper hull
		Muzzle = HullPoint(From, AstraWar::SecMid, FMath::FRandRange(0.2f, 0.8f), FMath::FRandRange(-0.5f, 0.5f), 1.f, true);
	}
	const FVector Off = Muzzle - Pr.Pos;
	T->Offset = Off.Size() < 1.5 * FMath::Max(From.Radius, 50.f) ? Off : FVector::ZeroVector;
	T->OffsetTau = bRail ? 0.22f : (Pr.bTorpedo ? 0.9f : 0.55f);
	T->Hist[0] = Muzzle;
	T->HistN = 1;
	// the muzzle's flash
	if (FVector::DistSquared(Muzzle, F.Origin) < FMath::Square(90000.0))
	{
		const float Heavy = FMath::Clamp(Pr.Damage / 60.f, 0.5f, 1.8f);
		if (bRail)
		{
			if (FPuff* Pf = AddPuff(Muzzle, From.Vel, 0.16f, 3.f * Heavy, 9.f * Heavy, T->Col, 320.f, LGlow))
			{
				Pf->P1 = 1.f;
			}
			SparkBurst(Muzzle, Aim, 0.5f, 5, 60.f, 220.f, 0.12f, 0.3f, 14.f, T->Col, 260.f, From.Vel);
		}
		else
		{
			AddPuff(Muzzle, From.Vel, 0.35f, 2.5f, 9.f, FLinearColor(1.f, 0.85f, 0.6f), 260.f, LGlow);
		}
	}
	return Slot;
}

void UAstraWarFX::DrawShots()
{
	if (!Owner)
	{
		return;
	}
	const FVector Eye = PlayerEye();
	for (FAstraProjectile& Pr : Owner->Projectiles)
	{
		if (Pr.bDead)
		{
			continue;
		}
		if (!Tracks.IsValidIndex(Pr.FxSlot) || Tracks[Pr.FxSlot].Frame < -1)
		{
			// a shot that did not come through the hook (the older call sites): give it a track now
			const FAstraBattleShip* From = Owner->FindById(Pr.Owner);
			Pr.FxSlot = From ? OnProjectile(*From, *From, Pr) : -1;
			if (!Tracks.IsValidIndex(Pr.FxSlot))
			{
				continue;
			}
			Tracks[Pr.FxSlot].Offset = FVector::ZeroVector;
		}
		FTrack& T = Tracks[Pr.FxSlot];
		T.Frame = Frame;
		T.Age += Dt;
		const bool bAstra = Pr.OwnerSide == 0;
		const float Fade = T.Age < T.OffsetTau ? 1.f - Ease(T.Age / T.OffsetTau) : 0.f;
		const FVector Head = Pr.Pos + T.Offset * Fade;
		// the way it moves in the Aquila's frame, with the muzzle's correction in it
		FVector Vrel = Pr.Vel - F.Vel;
		if (Fade > 0.f)
		{
			Vrel -= T.Offset * (Fade > 0.f ? (1.f / T.OffsetTau) * 6.f * (T.Age / T.OffsetTau) * (1.f - T.Age / T.OffsetTau) : 0.f);
		}
		const double Speed = Vrel.Size();
		if (Speed < 1.0)
		{
			continue;
		}
		const FVector DirW = F.DirToWorld(Vrel / Speed);
		const FVector HeadW = F.ToWorld(Head);
		const double Dist = FVector::Dist(HeadW, Eye) / 100.0;
		if (T.Style == 0)
		{
			// a slug: a dart, white-hot at the head and fading behind it; a frame's travel or more, so it reads as a line
			FTransform* X;
			if (float* D = Darts.Next(X))
			{
				const float Len = FMath::Clamp((float)Speed * 0.05f, 90.f, 560.f);
				const float Width = FMath::Clamp(3.2f + Pr.Damage * 0.055f, 4.f, 9.f);
				const FVector Centre = HeadW - DirW * (Len * 50.0);
				*X = FTransform(FQuat::FindBetweenNormals(FVector::ZAxisVector, DirW), Centre, FVector(Width, Width, Len));
				Fill(D, T.Col, 700.f * Intensity, 0.f, 0.f, 0.f, (float)(Pr.FxSlot & 255) / 255.f, Width, Len);
			}
			continue;
		}
		// a missile, a torpedo, a rocket: a glowing head, a trail laid down behind it
		const float Hot = T.Style == 2 ? 1.5f : (T.Style == 3 ? 0.7f : 1.f);
		{
			FTransform* X;
			if (float* D = Glows.Next(X))
			{
				const float R = (T.Style == 2 ? 11.f : 7.f) * (0.8f + 0.2f * FMath::Sin(T.Age * 40.f));
				*X = FTransform(FQuat::Identity, HeadW, FVector(R * 2.f));
				Fill(D, T.Style == 2 ? FLinearColor(1.f, 1.f, 1.f) : FLinearColor(1.f, 0.85f, 0.6f), 260.f * Intensity * Hot, 0.f, 0.f, 0.f, 0.f, R * 2.f, 0.f);
			}
		}
		T.SampleAcc += Dt;
		if (T.SampleAcc >= 0.1f)
		{
			T.SampleAcc = FMath::Fmod(T.SampleAcc, 0.1f);
			for (int32 i = FTrack::TrailPts - 1; i > 0; --i)
			{
				T.Hist[i] = T.Hist[i - 1];
			}
			T.Hist[0] = Head;
			T.HistN = FMath::Min(T.HistN + 1, (int32)FTrack::TrailPts);
		}
		const int32 Segs = Dist < 40000.0 ? T.HistN : FMath::Min(T.HistN, 3);
		FVector Newer = Head;
		for (int32 i = 0; i < Segs; ++i)
		{
			const FVector Older = T.Hist[i];
			const FVector A = F.ToWorld(Newer), B = F.ToWorld(Older);
			const double L = FVector::Dist(A, B);
			if (L > 20.0)
			{
				FTransform* X;
				if (float* D = Tubes.Next(X))
				{
					const float Age01 = (float)(i + 1) / (float)FTrack::TrailPts;
					const float Width = (T.Style == 2 ? 3.6f : 2.2f) * (1.f + 2.2f * Age01);
					const FVector Dir = (A - B) / L;
					*X = FTransform(FQuat::FindBetweenNormals(FVector::ZAxisVector, Dir), (A + B) * 0.5, FVector(Width, Width, (float)L / 100.f));
					Fill(D, T.Col, 90.f * Intensity * Hot, Age01, 2.f, (float)(L / 100.0), (float)(Pr.FxSlot & 255) / 255.f, Width, (float)(L / 100.0));
				}
			}
			Newer = Older;
		}
	}
	// a track not seen this frame belongs to a shot that is gone: its trail stays a moment, fading
	for (int32 i = 0; i < Tracks.Num(); ++i)
	{
		FTrack& T = Tracks[i];
		if (T.Frame >= 0 && T.Frame != Frame)
		{
			T.Frame = -2;
			FreeTracks.Add(i);
		}
	}
}

// ------------------------------------------------------------------------------------------------------------------ beams
void UAstraWarFX::OnBeam(EAstraFxShot Kind, const FVector& A, const FVector& B, float Life, const FLinearColor& Col, int32 FromId, int32 ToId)
{
	if (!IsActive() || Beams.Num() >= CapBeams)
	{
		return;
	}
	if (FVector::DistSquared(B, Owner->Ships[0].Pos) > FMath::Square(160000.0) && FVector::DistSquared(A, Owner->Ships[0].Pos) > FMath::Square(160000.0))
	{
		return;
	}
	FBeam& Bm = Beams.AddDefaulted_GetRef();
	Bm.Kind = Kind;
	Bm.A = A;
	Bm.B = B;
	Bm.Life = FMath::Max(Life, 0.04f);
	Bm.Col = Col;
	Bm.Seed = FMath::FRand();
	Bm.FromId = FromId;
	Bm.ToId = ToId;
	const FAstraBattleShip* Src = FromId >= 0 ? Owner->FindById(FromId) : nullptr;
	const FAstraBattleShip* Dst = ToId >= 0 ? Owner->FindById(ToId) : nullptr;
	switch (Kind)
	{
	case EAstraFxShot::Laser:
		Bm.Width = Src ? FMath::Clamp(Src->Radius * 0.016f, 2.5f, 7.f) : 3.f;
		Bm.Inten = 520.f;
		break;
	case EAstraFxShot::Cannon:
		Bm.Width = 1.1f;
		Bm.Inten = 420.f;
		break;
	default:
		Bm.Width = 0.9f;
		Bm.Inten = 360.f;
		break;
	}
	// the beam leaves a gun on the hull and rides on the ships at both ends while it lives
	if (Src && Src->Box.Valid())
	{
		const FVector P = MuzzleOf(*Src, EAstraMountKind::Laser, B - A, (int32)(Frame + Beams.Num()));
		Bm.FromLoc = Src->Att.UnrotateVector(P - Src->Pos);
		Bm.A = P;
	}
	else
	{
		Bm.FromId = -1;
	}
	if (Dst)
	{
		Bm.ToLoc = Dst->Att.UnrotateVector(B - Dst->Pos);
	}
	else
	{
		Bm.ToId = -1;
	}
}

void UAstraWarFX::DrawBeams()
{
	const FVector Eye = PlayerEye();
	for (int32 i = Beams.Num() - 1; i >= 0; --i)
	{
		FBeam& Bm = Beams[i];
		Bm.Age += Dt;
		if (Bm.Age >= Bm.Life)
		{
			Beams.RemoveAtSwap(i, EAllowShrinking::No);
			continue;
		}
		FVector A = Bm.A, B = Bm.B;
		if (Bm.FromId >= 0)
		{
			if (const FAstraBattleShip* S = Owner->FindById(Bm.FromId))
			{
				A = S->Pos + S->Att.RotateVector(Bm.FromLoc);
			}
		}
		if (Bm.ToId >= 0)
		{
			if (const FAstraBattleShip* S = Owner->FindById(Bm.ToId))
			{
				B = S->Pos + S->Att.RotateVector(Bm.ToLoc);
			}
		}
		const FVector AW = F.ToWorld(A), BW = F.ToWorld(B);
		const double LenCm = FVector::Dist(AW, BW);
		if (LenCm < 100.0)
		{
			continue;
		}
		const FVector Dir = (BW - AW) / LenCm;
		const float K = Bm.Age / Bm.Life;
		if (Bm.Kind == EAstraFxShot::Laser)
		{
			// the pulse is drawn in from the gun to the target in the first instants, holds, and thins out
			const float Reach = FMath::Min(1.f, Bm.Age / 0.06f);
			const FVector HeadW = AW + Dir * (LenCm * Reach);
			const float Fade = 1.f - Ease((K - 0.45f) / 0.55f);
			FTransform* X;
			if (float* D = Tubes.Next(X))
			{
				const float Width = Bm.Width * (0.7f + 0.3f * Fade);
				const double L = LenCm * Reach;
				*X = FTransform(FQuat::FindBetweenNormals(FVector::ZAxisVector, Dir), (AW + HeadW) * 0.5, FVector(Width, Width, (float)(L / 100.0)));
				Fill(D, Bm.Col, Bm.Inten * Intensity * Fade, K, 1.f, (float)(L / 100.0), Bm.Seed, Width, (float)(L / 100.0));
			}
			// the glow where it touches, and where it leaves
			for (int32 e = 0; e < 2; ++e)
			{
				if (e == 0 && Reach < 1.f)
				{
					continue;
				}
				if (float* D = Glows.Next(X))
				{
					const float R = Bm.Width * (e == 0 ? 3.4f : 2.2f) * (0.85f + 0.3f * FMath::Frac(Bm.Seed * 13.f + Clock * 31.f));
					*X = FTransform(FQuat::Identity, e == 0 ? BW : AW, FVector(R * 2.f));
					Fill(D, e == 0 ? Mix(Bm.Col, FLinearColor::White, 0.45f) : Bm.Col, (e == 0 ? 300.f : 160.f) * Intensity * Fade, K, 0.f, 0.f, Bm.Seed, R * 2.f, 0.f);
				}
			}
		}
		else
		{
			// a burst: tracers that run from the gun to the target (cannon: a few; point defence: a stream)
			const int32 N = Bm.Kind == EAstraFxShot::Cannon ? 2 : 4;
			for (int32 k = 0; k < N; ++k)
			{
				const float S = FMath::Frac(K * 1.15f + (float)k / (float)N + Bm.Seed);
				const float Len = (Bm.Kind == EAstraFxShot::Cannon ? 70.f : 38.f) * 100.f;
				const double Along = LenCm * S;
				const double TailLen = FMath::Min((double)Len, Along);
				if (TailLen < 300.0)
				{
					continue;
				}
				FTransform* X;
				if (float* D = Tubes.Next(X))
				{
					const FVector HeadW = AW + Dir * Along;
					*X = FTransform(FQuat::FindBetweenNormals(FVector::ZAxisVector, Dir), HeadW - Dir * (TailLen * 0.5), FVector(Bm.Width, Bm.Width, (float)(TailLen / 100.0)));
					Fill(D, Bm.Col, Bm.Inten * Intensity * (1.f - Ease((K - 0.6f) / 0.4f)), K, 4.f, (float)(TailLen / 100.0), Bm.Seed, Bm.Width, (float)(TailLen / 100.0));
				}
			}
		}
		(void)Eye;
	}
}

// ------------------------------------------------------------------------------------------------------------------ particles
void UAstraWarFX::DrawPuffs()
{
	for (int32 i = Puffs.Num() - 1; i >= 0; --i)
	{
		FPuff& P = Puffs[i];
		P.Age += Dt;
		if (P.Age >= P.Life)
		{
			Puffs.RemoveAtSwap(i, EAllowShrinking::No);
			continue;
		}
		if (P.Age < 0.f)
		{
			continue;                              // not born yet
		}
		if (P.Drag > 0.f)
		{
			P.Vel *= FMath::Max(0.f, 1.f - P.Drag * Dt);
		}
		P.Pos += P.Vel * Dt;
		const float K = P.Age / P.Life;
		FTransform* X;
		float* D = nullptr;
		float R = FMath::Lerp(P.R0, P.R1, Out(K));
		switch (P.Layer)
		{
		case LFire:
			D = Fires.Next(X);
			break;
		case LSmoke:
			D = Smokes.Next(X);
			break;
		default:
			D = Glows.Next(X);
			break;
		}
		if (!D)
		{
			continue;
		}
		*X = FTransform(FQuat::Identity, F.ToWorld(P.Pos), FVector(R * 2.f));
		switch (P.Layer)
		{
		case LFire:
			Fill(D, P.Col, P.Inten * Intensity, K, P.Seed, P.P1, P.Seed, R * 2.f, 0.f);
			break;
		case LSmoke:
			Fill(D, P.Col, P.Inten, K, P.Seed, P.P1, P.Seed, R * 2.f, P.P2);
			break;
		case LShock:
			Fill(D, P.Col, P.Inten * Intensity, K, 2.f, P.P2, P.Seed, R * 2.f, 0.f);
			break;
		default:
			Fill(D, P.Col, P.Inten * Intensity, K, P.P1, P.P2, P.Seed, R * 2.f, 0.f);
			break;
		}
	}
}

void UAstraWarFX::DrawSparks()
{
	for (int32 i = Sparks.Num() - 1; i >= 0; --i)
	{
		FSpark& S = Sparks[i];
		S.Age += Dt;
		if (S.Age >= S.Life)
		{
			Sparks.RemoveAtSwap(i, EAllowShrinking::No);
			continue;
		}
		if (S.Drag > 0.f)
		{
			S.Vel *= FMath::Max(0.f, 1.f - S.Drag * Dt);
		}
		S.Pos += S.Vel * Dt;
		const FVector Vrel = S.Vel - F.Vel;
		const double Speed = Vrel.Size();
		FTransform* X;
		float* D = Darts.Next(X);
		if (!D)
		{
			continue;
		}
		const float K = S.Age / S.Life;
		const FVector DirW = Speed > 0.5 ? F.DirToWorld(Vrel / Speed) : FVector::UpVector;
		const float Len = FMath::Max(S.Len * (1.f - 0.5f * K), 2.f);
		const FVector HeadW = F.ToWorld(S.Pos);
		const float W = S.Width * (1.f - 0.4f * K);
		*X = FTransform(FQuat::FindBetweenNormals(FVector::ZAxisVector, DirW), HeadW - DirW * (Len * 50.0), FVector(W, W, Len));
		// white-hot, then the colour of the metal, then red as it cools
		const FLinearColor C = K < 0.25f ? Mix(FLinearColor(1.f, 0.97f, 0.88f), S.Col, K / 0.25f)
		                                  : Mix(S.Col, FLinearColor(0.8f, 0.14f, 0.04f), (K - 0.25f) / 0.75f);
		Fill(D, C, S.Inten * Intensity * (1.f - K) * (1.f - K) + 12.f, K, 3.f, Len, S.Seed, W, Len);
	}
}

void UAstraWarFX::DrawDebris()
{
	for (int32 i = Debris.Num() - 1; i >= 0; --i)
	{
		FDebris& D = Debris[i];
		D.Age += Dt;
		if (D.Age >= D.Life)
		{
			Debris.RemoveAtSwap(i, EAllowShrinking::No);
			continue;
		}
		D.Pos += D.Vel * Dt;
		D.Att = FQuat(D.SpinAxis, D.SpinRate * Dt) * D.Att;
		D.Att.Normalize();
		if (D.Glow > 0.f)
		{
			D.Glow -= Dt;
			if (FMath::FRand() < Dt * 7.f)
			{
				AddSpark(D.Pos, D.Vel * 0.6f, 0.5f, 8.f, 0.7f, FLinearColor(1.f, 0.6f, 0.2f), 140.f, 0.5f);
			}
		}
		FLayer& L = D.bAstra ? DebrisA : DebrisM;
		FTransform* X;
		if (float* Dat = L.Next(X))
		{
			(void)Dat;
			// shrinks away in its last second
			const float S = FMath::Min(1.f, (D.Life - D.Age) * 1.5f);
			*X = FTransform(F.ToWorldRot(D.Att), F.ToWorld(D.Pos), D.Size * S);
		}
	}
}

// ------------------------------------------------------------------------------------------------------------------ lights
void UAstraWarFX::TickLights()
{
	if (!bLive)
	{
		return;
	}
	// age the lights, drop the dead
	for (int32 i = FlashLights.Num() - 1; i >= 0; --i)
	{
		FFlashLight& L = FlashLights[i];
		L.Age += Dt;
		L.Pos += L.Vel * Dt;
		if (L.Age >= L.Life)
		{
			FlashLights.RemoveAtSwap(i, EAllowShrinking::No);
		}
	}
	// the strongest few get the pooled lights (strength at the eye, so a big blast far away does not push out a small one near)
	struct FPick { int32 Idx; float Score; };
	TArray<FPick, TInlineAllocator<24>> Pick;
	for (int32 i = 0; i < FlashLights.Num(); ++i)
	{
		const FFlashLight& L = FlashLights[i];
		if (L.Age < 0.f)
		{
			continue;
		}
		const float K = L.Age / L.Life;
		const float Cur = L.Inten * (K < 0.12f ? K / 0.12f : FMath::Pow(1.f - (K - 0.12f) / 0.88f, 2.2f));
		Pick.Add({i, Cur / FMath::Max(1.f, (float)FVector::DistSquared(L.Pos, F.Origin) / 1.e4f)});
	}
	Pick.Sort([](const FPick& A, const FPick& B) { return A.Score > B.Score; });
	for (int32 s = 0; s < Lights.Num(); ++s)
	{
		UPointLightComponent* C = Lights[s];
		if (!C)
		{
			continue;
		}
		if (s >= Pick.Num())
		{
			if (C->IsVisible())
			{
				C->SetVisibility(false);
			}
			continue;
		}
		const FFlashLight& L = FlashLights[Pick[s].Idx];
		const float K = L.Age / L.Life;
		const float Cur = L.Inten * (K < 0.12f ? K / 0.12f : FMath::Pow(1.f - (K - 0.12f) / 0.88f, 2.2f));
		C->SetVisibility(true);
		C->SetWorldLocation(F.ToWorld(L.Pos));
		C->SetLightColor(L.Col);
		C->SetIntensity(Cur);
		C->SetAttenuationRadius(L.Radius * 100.f);
	}
}

void UAstraWarFX::TickTimed()
{
	for (int32 i = Timed.Num() - 1; i >= 0; --i)
	{
		FTimed& T = Timed[i];
		T.T -= Dt;
		if (T.T > 0.f)
		{
			continue;
		}
		if (AActor* A = T.Actor.Get())
		{
			if (T.What == 0)
			{
				A->SetActorHiddenInGame(true);
			}
			else
			{
				A->Destroy();
			}
		}
		Timed.RemoveAtSwap(i, EAllowShrinking::No);
	}
}
