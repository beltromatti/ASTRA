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
		TAutoConsoleVariable<float> CVarWake(TEXT("astra.fx.wake"), 1.f, TEXT("Brightness of the line a rail slug draws behind it (0 none, 0.2..3)"));
		TAutoConsoleVariable<float> CVarMuzzle(TEXT("astra.fx.muzzle"), 1.f, TEXT("Size of the flash at a gun's mouth (0.2..3)"));

		const FTransform& HiddenXf()
		{
			static const FTransform X(FQuat::Identity, FVector::ZeroVector, FVector(0.0001));
			return X;
		}

		constexpr float WakeSeconds = 1.1f;     // how far back a slug's line is drawn, in seconds of its flight
		constexpr float WakeTau = 0.42f;        // and how fast it dies: e^-t/tau (seen at the bridge a battle's worth of these is a starburst: long enough to be a line, short enough to be a line and not a net)
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
	MatDebris = Mat(TEXT("M_WAR_Debris"));
	static const TCHAR* const Dmg[8] = {TEXT("Burn"), TEXT("Hole"), TEXT("Torn"), TEXT("Impact"), TEXT("Strafe"), TEXT("Melt"), TEXT("Gouge"), TEXT("Blast")};
	DamageMats.Reset();
	for (const TCHAR* N : Dmg)
	{
		// the war's own decal (make_war_fx.py) first; the ship generator's, as it stands, if that has not been made yet
		UMaterialInterface* M = LoadObject<UMaterialInterface>(nullptr, *FString::Printf(TEXT("/Game/ASTRA/Materials/Instances/MI_WAR_Damage_%s.MI_WAR_Damage_%s"), N, N), nullptr, LOAD_Quiet | LOAD_NoWarn);
		if (!M)
		{
			M = LoadObject<UMaterialInterface>(nullptr, *FString::Printf(TEXT("/Game/ASTRA/Materials/Instances/MI_ShipDamage_%s.MI_ShipDamage_%s"), N, N), nullptr, LOAD_Quiet | LOAD_NoWarn);
		}
		DamageMats.Add(M);
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

void UAstraWarFX::MakeLayer(FLayer& L, const TCHAR* Name, UStaticMesh* Mesh, UMaterialInterface* Mat, int32 Capacity, int32 SortPriority, bool bLit, int32 NumData)
{
	L.Init(Capacity);
	if (!Host || !Mesh || !Mat)
	{
		return;
	}
	L.NumData = NumData;
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
	C->SetNumCustomDataFloats(NumData);
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
	for (FLayer* L : {&Darts, &Tubes, &Glows, &Fires, &Smokes, &Plumes, &DebrisL})
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
			Plumes.Init(CapPlumes); DebrisL.Init(CapDebris);
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
	MakeLayer(Smokes, TEXT("FxSmoke"), SphereMesh, MatSmoke, CapSmokes, -2, false, Stride);
	MakeLayer(Fires, TEXT("FxFire"), SphereMesh, MatFire, CapFires, 0, false, Stride);
	MakeLayer(Plumes, TEXT("FxPlume"), CylinderMesh, MatPlume, CapPlumes, 1, false, Stride);
	MakeLayer(Tubes, TEXT("FxTube"), CylinderMesh, MatTube, CapTubes, 2, false, Stride);
	MakeLayer(Darts, TEXT("FxDart"), CylinderMesh, MatDart, CapDarts, 3, false, Stride);       // (a cylinder shaded as a spindle: M_WAR_Dart; a stretched sphere was dark seen end-on)
	MakeLayer(Glows, TEXT("FxGlow"), SphereMesh, MatGlow, CapGlows, 4, false, Stride);
	// chunks of metal: lit, with their colour and glow per instance (M_WAR_Debris), or in the engine's plain material until that exists
	UMaterialInterface* DebrisMat = MatDebris ? MatDebris.Get() : LoadObject<UMaterialInterface>(nullptr, TEXT("/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial"));
	MakeLayer(DebrisL, TEXT("FxDebris"), CubeMesh, DebrisMat, CapDebris, 0, true, MatDebris ? Stride : 0);
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
	UE_LOG(LogASTRA, Log, TEXT("[WarFX] effects ready: darts %d, tubes %d, glows %d, fire %d, smoke %d, plumes %d, debris %d, lights %d (debris material: %s)"),
	       CapDarts, CapTubes, CapGlows, CapFires, CapSmokes, CapPlumes, CapDebris, MaxLights, MatDebris ? TEXT("M_WAR_Debris") : TEXT("engine default"));
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
	Ghosts.Reset();
	Wakes.Reset();
	Blasts.Reset();
	FlashLights.Reset();
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
		if (AActor* H = P.HullActor.Get())
		{
			H->Destroy();
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
	for (FLayer* L : {&Darts, &Tubes, &Glows, &Fires, &Smokes, &Plumes, &DebrisL})
	{
		L->Begin();
	}
}

float UAstraWarFX::Room(uint8 Layer) const
{
	const int32 Cap = Layer == LFire ? CapFires : (Layer == LSmoke ? CapSmokes : CapGlows);
	const float Used = (float)PuffLive[FMath::Min<int32>(Layer, 3)] / (float)Cap;
	return FMath::Clamp((1.f - Used) / 0.35f, 0.f, 1.f);
}

float UAstraWarFX::RoomSparks() const
{
	const float Used = FMath::Max((float)Sparks.Num() / (float)CapSparks, (float)Darts.Prev / (float)CapDarts);
	return FMath::Clamp((1.f - Used) / 0.4f, 0.f, 1.f);
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
	// fewer where they are far (past 60 km a spark is a point: down to a sixth of them at 160 km), fewer still when the pool is filling
	const float Dist = (float)FVector::Dist(Pos, F.Origin);
	const float Near = Dist > 60000.f ? FMath::Clamp(1.f - (Dist - 60000.f) / 120000.f, 0.15f, 1.f) : 1.f;
	const float K = FMath::Clamp(Density, 0.2f, 2.f) * FMath::Max(0.12f, RoomSparks()) * Near;
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
	if (FVector::DistSquared(Pos, F.Origin) > FMath::Square(40000.0))
	{
		return;                              // (a chunk of metal farther than 40 km is under a pixel: it would only take the place of a near one)
	}
	FDebris* Slot;
	if (Debris.Num() < CapDebrisSim)
	{
		Slot = &Debris.AddDefaulted_GetRef();
	}
	else
	{
		// the pool is full: the chunk furthest through its life makes way (a blast near the eye is worth more than the last one's last chunks)
		int32 Oldest = 0;
		float Furthest = -1.f;
		for (int32 i = 0; i < Debris.Num(); ++i)
		{
			const float K = Debris[i].Age / Debris[i].Life;
			if (K > Furthest)
			{
				Furthest = K;
				Oldest = i;
			}
		}
		Slot = &Debris[Oldest];
		*Slot = FDebris();
	}
	FDebris& D = *Slot;
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
	const bool bParked = Owner->bSandbox && !A.bAlive;              // (a bench scenario parks the Aquila far away: what is measured is round the origin; one that keeps her
	F.Origin = bParked ? FVector::ZeroVector : A.Pos;               //  — astra.war.scenario <name> aquila — is drawn round her, as the game does)
	F.Att = A.Att;
	F.InvAtt = A.Att.Inverse();
	F.Vel = bParked ? FVector::ZeroVector : A.Vel;
	F.Bridge = Owner->BridgeOffset;
	Intensity = FMath::Clamp(CVarIntensity.GetValueOnGameThread(), 0.1f, 6.f);
	Density = FMath::Clamp(CVarDensity.GetValueOnGameThread(), 0.2f, 2.f);
	LightScale = FMath::Clamp(CVarLights.GetValueOnGameThread(), 0.f, 4.f);
	WakeGain = FMath::Clamp(CVarWake.GetValueOnGameThread(), 0.f, 3.f);
	MuzzleGain = FMath::Clamp(CVarMuzzle.GetValueOnGameThread(), 0.2f, 3.f);
	for (FLayer* L : {&Darts, &Tubes, &Glows, &Fires, &Smokes, &Plumes, &DebrisL})
	{
		L->Begin();
	}
}

void UAstraWarFX::EndFrame()
{
	for (FLayer* L : {&Darts, &Tubes, &Glows, &Fires, &Smokes, &Plumes, &DebrisL})
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
	for (int32 i = Blasts.Num() - 1; i >= 0; --i)
	{
		Blasts[i].Age += Dt;
		if (Blasts[i].Age > 8.f)
		{
			Blasts.RemoveAtSwap(i, EAllowShrinking::No);
		}
	}
	const double TestT0 = FPlatformTime::Seconds();
	RunTests();                            // what astra.fx.* asked for (AstraWarFXTest.cpp)
	const double TestMs = (FPlatformTime::Seconds() - TestT0) * 1000.0;       // (its pictures cost what they cost: not the effects')
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
	const double Ms = (FPlatformTime::Seconds() - T0) * 1000.0 - TestMs;
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
	Out = FString::Printf(TEXT("%s | %.3f ms/frame (max %.2f) over %d frames | instances now/peak: darts %d/%d tubes %d/%d glows %d/%d fire %d/%d smoke %d/%d plumes %d/%d debris %d | "
	                           "dropped (full): darts %d tubes %d glows %d fire %d smoke %d | puffs %d sparks %d beams %d tracks %d wakes %d pieces %d scars %d lights %d"),
	                      bLive ? TEXT("drawing") : (bSim ? TEXT("bench (not drawn)") : TEXT("off")), TickCount ? TickMs / TickCount : 0.0, TickMsMax, TickCount,
	                      Darts.Prev, Darts.Peak, Tubes.Prev, Tubes.Peak, Glows.Prev, Glows.Peak, Fires.Prev, Fires.Peak, Smokes.Prev, Smokes.Peak,
	                      Plumes.Prev, Plumes.Peak, DebrisL.Prev, Darts.Dropped, Tubes.Dropped, Glows.Dropped, Fires.Dropped, Smokes.Dropped,
	                      Puffs.Num(), Sparks.Num(), Beams.Num(), Tracks.Num() - FreeTracks.Num(), Wakes.Num(), Pieces.Num(), Scars.Num(), FlashLights.Num());
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
	T->Start = Muzzle;
	T->HistN = 1;
	// the muzzle's flash
	if (FVector::DistSquared(Muzzle, F.Origin) < FMath::Square(90000.0))
	{
		const float Heavy = FMath::Clamp(Pr.Damage / 60.f, 0.5f, 1.8f);
		if (bRail)
		{
			// the discharge, in the size of the gun (a destroyer's mount is small, the Aquila's is not): a white-hot core inside a bloom of the shot's colour with its streaks, a hot jet
			// along the aim, a ring that spreads off the barrel, a spray of sparks, and the light of it on the hull round the mouth
			const float Gun = FMath::Clamp(From.Radius * 0.03f, 3.f, 14.f) * Heavy * MuzzleGain;
			if (FPuff* Pf = AddPuff(Muzzle, From.Vel, 0.24f, 0.5f * Gun, 1.9f * Gun, T->Col, 420.f, LGlow))
			{
				Pf->P1 = 1.f;
			}
			AddPuff(Muzzle, From.Vel, 0.1f, 0.25f * Gun, 0.8f * Gun, FLinearColor(1.f, 0.97f, 0.9f), 560.f, LGlow);
			AddSpark(Muzzle + Aim * (Gun * 2.f), From.Vel + Aim * 120.f, 0.16f, Gun * 7.f, 0.4f + 0.16f * Gun, T->Col, 420.f, 0.f);
			Shockwave(Muzzle + Aim * Gun, From.Vel, Gun * 2.6f, 0.3f, T->Col, 0.02f);
			SparkBurst(Muzzle, Aim, 0.6f, 6, 60.f, 260.f, 0.14f, 0.4f, 10.f + Gun, T->Col, 300.f, From.Vel);
			AddLight(Muzzle + Aim * Gun, 0.18f, Gun * 20.f, 6500.f * Gun * Gun * 0.6f, Mix(T->Col, FLinearColor::White, 0.35f), From.Vel);
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
		// what it is is read each frame: a torpedo and a rocket are missiles made over after they leave the gun
		T.Style = Pr.Kind == EAstraProjKind::Rail ? 0 : (Pr.bTorpedo ? 2 : (Pr.HitKind == EAstraHitKind::Rocket ? 3 : 1));
		T.Col = ShotColor(bAstra, Pr.HitKind);
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
		T.Last = Head;
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
			// and the line it has drawn from the gun, bright at the slug and gone at the far end: a slug at 12 km/s is a dot that crosses the sky in a few frames, the line is what
			// says where the fire is going (seen from behind, from the side, from 40 km)
			T.bWake = false;
			if (WakeGain > 0.f)
			{
				const FVector Path = Head - T.Start;
				const double PathLen = Path.Size();
				const double WakeLen = FMath::Min(PathLen, Speed * (double)WakeSeconds);
				if (WakeLen > 40.0)
				{
					const FVector Dir = Path / PathLen;
					const FVector TailS = Head - Dir * WakeLen;
					const FVector TailW = F.ToWorld(TailS);
					const FVector Along = (HeadW - TailW).GetSafeNormal();
					T.WakeTail = TailS;
					T.WakeKappa = (float)(WakeLen / (Speed * (double)WakeTau));
					T.WakeWidth = 1.6f + Pr.Damage * 0.012f;
					T.bWake = true;
					FTransform* Xw;
					if (float* Dw = Tubes.Next(Xw))
					{
						const float WakeW = T.WakeWidth;
						*Xw = FTransform(FQuat::FindBetweenNormals(FVector::ZAxisVector, Along), (TailW + HeadW) * 0.5, FVector(WakeW, WakeW, (float)WakeLen));
						Fill(Dw, T.Col, 190.f * Intensity * WakeGain, 0.f, 5.f, T.WakeKappa, (float)(Pr.FxSlot & 255) / 255.f, WakeW, (float)WakeLen);
					}
				}
			}
			continue;
		}
		// a missile, a torpedo, a rocket: a glowing head, a trail laid down behind it
		const float Hot = T.Style == 2 ? 1.5f : (T.Style == 3 ? 0.7f : 1.f);
		{
			FTransform* X;
			if (float* D = Glows.Next(X))
			{
				const float R = (T.Style == 2 ? 11.f : 7.f) * GlowK * (0.8f + 0.2f * FMath::Sin(T.Age * 40.f));
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
				// a bead: an ellipsoid a little longer than its stretch of the path, so that it melts into its neighbours; older, wider, dimmer
				FTransform* X;
				if (float* D = Darts.Next(X))
				{
					const float AgeTail = (float)(i + 1) / (float)FTrack::TrailPts, AgeHead = (float)i / (float)FTrack::TrailPts;
					const float Width = (T.Style == 2 ? 3.6f : 2.2f) * (1.f + 2.2f * AgeTail);
					const FVector Dir = (A - B) / L;
					const float Len = (float)(L / 100.0) * 1.7f;
					*X = FTransform(FQuat::FindBetweenNormals(FVector::ZAxisVector, Dir), (A + B) * 0.5, FVector(Width, Width, Len));
					Fill(D, T.Col, 65.f * Intensity * Hot, AgeTail, 2.f, AgeHead, (float)(Pr.FxSlot & 255) / 255.f, Width, Len);
				}
			}
			Newer = Older;
		}
		if (WakeGain > 0.f)
		{
			// the engine: a short, hot flame behind the head (the bright end of a wake, at the nozzle)
			{
				FTransform* X;
				if (float* D = Tubes.Next(X))
				{
					const float FlameLen = (T.Style == 2 ? 28.f : 18.f) + (float)Speed * 0.012f;
					const float FlameW = T.Style == 2 ? 4.5f : 3.f;
					*X = FTransform(FQuat::FindBetweenNormals(FVector::ZAxisVector, DirW), HeadW - DirW * (FlameLen * 50.0), FVector(FlameW, FlameW, FlameLen));
					Fill(D, T.Style == 2 ? FLinearColor(0.8f, 0.95f, 1.f) : FLinearColor(1.f, 0.78f, 0.5f), 320.f * Intensity * Hot * WakeGain, 0.f, 5.f, 2.2f, (float)(Pr.FxSlot & 255) / 255.f, FlameW, FlameLen);
				}
			}
			// the long smoke: a point every half second, a pale line through them that dies away (where the missile has been, so also where it turned)
			T.LongAcc += Dt;
			if (T.LongAcc >= 0.5f)
			{
				T.LongAcc = FMath::Fmod(T.LongAcc, 0.5f);
				for (int32 i = FTrack::LongPts - 1; i > 0; --i)
				{
					T.LongHist[i] = T.LongHist[i - 1];
				}
				T.LongHist[0] = Head;
				T.LongN = FMath::Min(T.LongN + 1, (int32)FTrack::LongPts);
			}
			const int32 LSegs = Dist < 40000.0 ? T.LongN : FMath::Min(T.LongN, 3);
			const FLinearColor Pale = Mix(T.Col, FLinearColor::White, 0.5f);
			FVector LNewer = Head;
			for (int32 i = 0; i < LSegs; ++i)
			{
				const FVector LOlder = T.LongHist[i];
				const FVector A = F.ToWorld(LNewer), B = F.ToWorld(LOlder);
				const double L = FVector::Dist(A, B);
				FTransform* X;
				if (L > 200.0)
				{
					if (float* D = Tubes.Next(X))
					{
						const float AgeTail = (float)(i + 1) / (float)(FTrack::LongPts + 1), AgeHead = (float)i / (float)(FTrack::LongPts + 1);
						const float Width = (T.Style == 2 ? 4.f : 2.6f) * (1.f + 1.6f * AgeTail);
						const FVector Dir = (A - B) / L;
						const float Len = (float)(L / 100.0);
						*X = FTransform(FQuat::FindBetweenNormals(FVector::ZAxisVector, Dir), (A + B) * 0.5, FVector(Width, Width, Len));
						Fill(D, Pale, 34.f * Intensity * Hot * WakeGain, AgeTail, 2.f, AgeHead, (float)(Pr.FxSlot & 255) / 255.f, Width, Len);
					}
				}
				LNewer = LOlder;
			}
			// the seeker's turns: a puff of attitude gas on the side opposite to the push, while it turns hard (a missile that curves in the sky is a thing with a mind)
			if (T.bPrevVel && Dt > 1.e-4f && Dist < 60000.0)
			{
				const FVector Acc = (Pr.Vel - T.PrevVel) / (double)Dt;
				const FVector Dir0 = Pr.Vel.GetSafeNormal();
				const FVector Lat = Acc - Dir0 * FVector::DotProduct(Acc, Dir0);
				const double LatMag = Lat.Size();
				T.RcsAcc += Dt;
				if (LatMag > 40.0 && T.RcsAcc >= 0.09f)
				{
					T.RcsAcc = 0.f;
					const FVector Side = -Lat / LatMag;
					if (FPuff* Rc = AddPuff(Pr.Pos + Side * 3.f, Pr.Vel * 0.3 + Side * 30.f, 0.15f, 0.8f, 3.2f, Mix(T.Col, FLinearColor::White, 0.5f), 300.f * Hot, LGlow))
					{
						Rc->P1 = 0.f;
					}
				}
			}
			T.PrevVel = Pr.Vel;
			T.bPrevVel = true;
		}
	}
	// a track not seen this frame belongs to a shot that is gone: its trail stays a moment, fading
	for (int32 i = 0; i < Tracks.Num(); ++i)
	{
		FTrack& T = Tracks[i];
		if (T.Frame >= 0 && T.Frame != Frame)
		{
			if (T.Style == 0 && T.bWake && Wakes.Num() < CapWakes)
			{
				// the slug is gone (it struck, it missed): the line it drew stays a moment, fading as it would have behind the slug
				FWake& Wk = Wakes.AddDefaulted_GetRef();
				Wk.Head = T.Last;
				Wk.Tail = T.WakeTail;
				Wk.Kappa = T.WakeKappa;
				Wk.Width = T.WakeWidth;
				Wk.Col = T.Col;
				Wk.Seed = (float)(i & 255) / 255.f;
			}
			if (T.Style >= 1 && T.HistN >= 2 && Ghosts.Num() < 120)
			{
				FGhost& G = Ghosts.AddDefaulted_GetRef();
				G.Pts[0] = T.Last;
				G.N = FMath::Min(T.HistN + 1, (int32)FTrack::TrailPts + 1);
				for (int32 k = 1; k < G.N; ++k)
				{
					G.Pts[k] = T.Hist[k - 1];
				}
				G.Style = T.Style;
				G.Col = T.Col;
				G.Seed = (uint8)(i & 255);
				G.BeadLife = 1.0f + 0.5f * (T.Style == 2);
				G.Life = G.BeadLife;
				if (T.LongN > 0)
				{
					// the long smoke stays where the missile drew it and thins away over a few seconds (the head's end first)
					G.Long[0] = T.Last;
					G.LongN = FMath::Min(T.LongN + 1, (int32)FTrack::LongPts + 1);
					for (int32 k = 1; k < G.LongN; ++k)
					{
						G.Long[k] = T.LongHist[k - 1];
					}
					G.Life = 3.2f;
				}
			}
			T.Frame = -2;
			FreeTracks.Add(i);
		}
	}
	// the wakes the ended slugs left: the line hangs where it was and dims as it would have (e^-t/tau everywhere on it)
	for (int32 g = Wakes.Num() - 1; g >= 0; --g)
	{
		FWake& Wk = Wakes[g];
		Wk.Age += Dt;
		const float K = FMath::Exp(-Wk.Age / WakeTau);
		if (K < 0.05f)
		{
			Wakes.RemoveAtSwap(g, EAllowShrinking::No);
			continue;
		}
		const FVector TailW = F.ToWorld(Wk.Tail), HeadW = F.ToWorld(Wk.Head);
		const double LenCm = FVector::Dist(TailW, HeadW);
		FTransform* Xw;
		if (LenCm < 4000.0 || WakeGain <= 0.f)
		{
			continue;
		}
		if (float* Dw = Tubes.Next(Xw))
		{
			const FVector Along = (HeadW - TailW) / LenCm;
			*Xw = FTransform(FQuat::FindBetweenNormals(FVector::ZAxisVector, Along), (TailW + HeadW) * 0.5, FVector(Wk.Width, Wk.Width, (float)(LenCm / 100.0)));
			Fill(Dw, Wk.Col, 190.f * Intensity * WakeGain * K, 0.f, 5.f, Wk.Kappa, Wk.Seed, Wk.Width, (float)(LenCm / 100.0));
		}
	}
	// the trails the ended shots left: the same beads, ageing together
	for (int32 g = Ghosts.Num() - 1; g >= 0; --g)
	{
		FGhost& G = Ghosts[g];
		G.Age += Dt;
		if (G.Age >= G.Life)
		{
			Ghosts.RemoveAtSwap(g, EAllowShrinking::No);
			continue;
		}
		const float Shift = FMath::Min(1.f, G.Age / G.BeadLife);
		const float Hot = G.Style == 2 ? 1.5f : (G.Style == 3 ? 0.7f : 1.f);
		for (int32 k = 0; k + 1 < G.N && Shift < 1.f; ++k)
		{
			const FVector A = F.ToWorld(G.Pts[k]), B = F.ToWorld(G.Pts[k + 1]);
			const double L = FVector::Dist(A, B);
			FTransform* X;
			if (L < 20.0)
			{
				continue;
			}
			if (float* D = Darts.Next(X))
			{
				const float AgeTail = FMath::Min(1.f, (float)(k + 1) / (float)FTrack::TrailPts + Shift);
				const float AgeHead = FMath::Min(1.f, (float)k / (float)FTrack::TrailPts + Shift);
				const float Width = (G.Style == 2 ? 3.6f : 2.2f) * (1.f + 2.2f * AgeTail);
				const FVector Dir = (A - B) / L;
				const float Len = (float)(L / 100.0) * 1.7f;
				*X = FTransform(FQuat::FindBetweenNormals(FVector::ZAxisVector, Dir), (A + B) * 0.5, FVector(Width, Width, Len));
				Fill(D, G.Col, 65.f * Intensity * Hot, AgeTail, 2.f, AgeHead, (float)G.Seed / 255.f, Width, Len);
			}
		}
		if (G.LongN > 1 && WakeGain > 0.f)
		{
			// the long smoke of the missile that has ended, thinning where it was drawn (the same tubes as the living one, their ages running on)
			const float LShift = G.Age / G.Life;
			const FLinearColor Pale = Mix(G.Col, FLinearColor::White, 0.5f);
			for (int32 k = 0; k + 1 < G.LongN; ++k)
			{
				const FVector A = F.ToWorld(G.Long[k]), B = F.ToWorld(G.Long[k + 1]);
				const double L = FVector::Dist(A, B);
				FTransform* X;
				if (L > 200.0)
				{
					if (float* D = Tubes.Next(X))
					{
						const float AgeTail = FMath::Min(1.f, (float)(k + 1) / (float)(FTrack::LongPts + 1) + LShift), AgeHead = FMath::Min(1.f, (float)k / (float)(FTrack::LongPts + 1) + LShift);
						const float Width = (G.Style == 2 ? 4.f : 2.6f) * (1.f + 1.6f * AgeTail);
						const FVector Dir = (A - B) / L;
						const float Len = (float)(L / 100.0);
						*X = FTransform(FQuat::FindBetweenNormals(FVector::ZAxisVector, Dir), (A + B) * 0.5, FVector(Width, Width, Len));
						Fill(D, Pale, 34.f * Intensity * Hot * WakeGain, AgeTail, 2.f, AgeHead, (float)G.Seed / 255.f, Width, Len);
					}
				}
			}
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
	if (FVector::DistSquared(B, F.Origin) > FMath::Square(160000.0) && FVector::DistSquared(A, F.Origin) > FMath::Square(160000.0))
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
		Bm.Inten = ASTRA_FX_TUNE("laser", 168.f);              // (a white-hot core with the beam's own colour at its edges: at 520 the whole width was over the exposure's white, 5 Oct, from the broadside)
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
		if (Kind != EAstraFxShot::Laser && FVector::DistSquared(P, F.Origin) < FMath::Square(30000.0))
		{
			AddPuff(P, Src->Vel, 0.07f, 0.6f, 2.4f * MuzzleGain, Col, 240.f, LGlow);      // (a gun's mouth, for the instant a burst leaves it)
		}
	}
	else
	{
		Bm.FromId = -1;
	}
	if (Dst)
	{
		FVector Local = Dst->Att.UnrotateVector(B - Dst->Pos);
		Bm.RawToLoc = Local;
		if (Dst->Dmg.bModel && Dst->Box.Valid())
		{
			// the simulation ends it on the face of the target's box: it ends on the hull's skin (a beam that meets a shield is put on the shell by ShieldHit)
			const FVector O = Local - FVector(Dst->Box.Mid, 0.f, 0.f);                                  // (the face of the box it lies on: the axis it is nearest the wall along)
			const FVector Rel(FMath::Abs(O.X) / Dst->Box.Hx, FMath::Abs(O.Y) / Dst->Box.Hy, FMath::Abs(O.Z) / Dst->Box.Hz);
			const int32 Face = Rel.X >= Rel.Y && Rel.X >= Rel.Z ? (O.X >= 0.f ? AstraWar::Bow : AstraWar::Stern)
			                                                       : (Rel.Y >= Rel.Z ? (O.Y >= 0.f ? AstraWar::Starboard : AstraWar::Port) : (O.Z >= 0.f ? AstraWar::Dorsal : AstraWar::Ventral));
			SnapToHull(*Dst, Face, Local);
		}
		Bm.ToLoc = Local;
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
			const float Fade = 1.f - Ease((K - 0.30f) / 0.70f);
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
					const float R = Bm.Width * GlowK * (e == 0 ? 3.4f : 2.2f) * (0.85f + 0.3f * FMath::Frac(Bm.Seed * 13.f + Clock * 31.f));
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
	int32 Live[4] = {0, 0, 0, 0};
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
		++Live[FMath::Min<int32>(P.Layer, 3)];
		if (P.Drag > 0.f)
		{
			P.Vel *= FMath::Max(0.f, 1.f - P.Drag * Dt);
		}
		P.Pos += P.Vel * Dt;
		const float K = P.Age / P.Life;
		FTransform* X;
		float* D = nullptr;
		float R = FMath::Lerp(P.R0, P.R1, Out(K));
		if (P.Layer == LGlow)
		{
			R *= GlowK;                        // (the soft falloff of a glow reaches about 0.6 of its sphere: the sphere is drawn larger)
		}
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
			Fill(D, P.Col, P.Inten * Intensity, K, 3.f, P.P2, P.Seed, R * 2.f, 0.f);
			break;
		default:
			Fill(D, P.Col, P.Inten * Intensity, K, P.P1, P.P2, P.Seed, R * 2.f, 0.f);
			break;
		}
	}
	Live[LGlow] += Live[LShock];             // (the blast waves are drawn with the glows)
	for (int32 k = 0; k < 4; ++k)
	{
		PuffLive[k] = Live[k];
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
		FTransform* X;
		if (float* Dat = DebrisL.Next(X))
		{
			// shrinks away in its last second; the metal of its side, glowing a little while it is hot
			const float S = FMath::Min(1.f, (D.Life - D.Age) * 1.5f);
			*X = FTransform(F.ToWorldRot(D.Att), F.ToWorld(D.Pos), D.Size * S);
			Fill(Dat, D.bAstra ? FLinearColor(0.5f, 0.49f, 0.46f) : FLinearColor(0.07f, 0.062f, 0.055f), D.Glow > 0.f ? 55.f * FMath::Min(1.f, D.Glow) : 0.f, 0.f, 0.f, 0.f, 0.f, 0.f, 0.f);
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
