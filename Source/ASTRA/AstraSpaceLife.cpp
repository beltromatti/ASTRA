// ASTRA — the living space of a system, in the game: setup, the places as the plot's contacts, the world as the traffic sees it, the events for the crew, the console.
// The drawing is in AstraSpaceLifeDraw.cpp. What it is and why: AstraSpaceLife.h, docs/SPAZIO.md.

#include "AstraSpaceLife.h"
#include "AstraBattleSubsystem.h"
#include "AstraShipSubsystem.h"
#include "AstraWarDraw.h"
#include "ASTRA.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Components/SceneComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/World.h"
#include "HAL/PlatformTime.h"
#include "Materials/MaterialInterface.h"
#include "Misc/DateTime.h"

namespace
{
	TAutoConsoleVariable<int32> CVarSpaceEnable(TEXT("astra.space.enable"), 1,
		TEXT("The living space of a system (places, civilian traffic, belt, buoys, wrecks): 1 on, 0 off (takes effect at the next system entered)"));
	TAutoConsoleVariable<int32> CVarSpaceDraw(TEXT("astra.space.draw"), 1, TEXT("Draw the living space (0: it runs and is counted, nothing is shown)"));
	TAutoConsoleVariable<float> CVarSpaceDensity(TEXT("astra.space.density"), 1.f, TEXT("How much traffic (1 as the system's data lists it, 0 none, 2 twice); read when a system is entered"));
	TAutoConsoleVariable<float> CVarSpaceRocks(TEXT("astra.space.rocks"), 1.f, TEXT("How many of the belt's rocks are made (1 all, 0.5 half, 0 none); read when a system is entered"));
	TAutoConsoleVariable<int32> CVarSpaceReact(TEXT("astra.space.reactions"), 1, TEXT("The civilian traffic reacts to the war (1), or flies on as if there were none (0: for looking at the traffic in a fight, and for the bench's peace), or to the console's test hostile only (2: astra.space.alert)"));
	TAutoConsoleVariable<int32> CVarSpaceBench(TEXT("astra.space.bench"), 0, TEXT("The war bench's worlds (deterministic runs) have no living space unless this is 1: their results stay what they were"));

	const double SpKm = 1000.0;
}

// ------------------------------------------------------------------------------------------------------------------ setup
bool UAstraSpaceLife::IsActive() const
{
	return (bLive || bSim) && CVarSpaceEnable.GetValueOnGameThread() != 0 && AstraSpace::Data().bLoaded && (!GAstraDeterministic || CVarSpaceBench.GetValueOnGameThread() != 0);
}

void UAstraSpaceLife::MakeLayer(AstraFx::FLayer& L, const TCHAR* Name, UStaticMesh* Mesh, UMaterialInterface* Mat, int32 Capacity, int32 Sort)
{
	L.Init(Capacity);
	L.NumData = AstraFx::Stride;
	if (!Host || !Mesh || !Mat)
	{
		return;
	}
	if (UInstancedStaticMeshComponent* C = AstraDraw::MakeComp(Host, Host->GetRootComponent(), Name, Mesh, Mat, Capacity, AstraFx::Stride, false, false))
	{
		C->SetTranslucentSortPriority(Sort);
		L.Comp = C;
	}
}

bool UAstraSpaceLife::LoadAssets()
{
	SphereMesh = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Sphere.Sphere"));
	CylinderMesh = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cylinder.Cylinder"));
	MatGlow = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/ASTRA/Materials/M_WAR_Glow.M_WAR_Glow"));
	MatPlume = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/ASTRA/Materials/M_WAR_Plume.M_WAR_Plume"));
	if (!SphereMesh || !MatGlow)
	{
		UE_LOG(LogASTRA, Warning, TEXT("[Space] M_WAR_Glow missing (tools/ue_scripts/make_war_fx.py): the living space stays out of the sky"));
	}
	return SphereMesh && MatGlow;
}

void UAstraSpaceLife::Init(UAstraBattleSubsystem* InOwner)
{
	Owner = InOwner;
	UWorld* World = Owner ? Owner->GetWorld() : nullptr;
	if (!World || bInitDone)
	{
		return;
	}
	bInitDone = true;
	Lamps.Init(0);
	Plumes.Init(0);
	Glints.Init(0);
	if (!FApp::CanEverRender())
	{
		// the bench: the same traffic and the same staging, nothing drawn (its cost is part of the world's)
		bSim = true;
		Lamps.Init(AstraSpaceDraw::CapLamps);
		Plumes.Init(AstraSpaceDraw::CapPlumes);
		Glints.Init(AstraSpaceDraw::CapGlints);
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
	USceneComponent* Root = NewObject<USceneComponent>(Host, TEXT("SpaceRoot"));
	Host->SetRootComponent(Root);
	Root->SetMobility(EComponentMobility::Movable);
	Root->RegisterComponent();
	Host->Tags.Add(TEXT("ASTRA.Sky"));                  // the main viewscreen's camera shows what is out there: tagged like the sky
	SystemRoot = NewObject<USceneComponent>(Host, TEXT("SystemFrame"));
	SystemRoot->SetupAttachment(Root);
	SystemRoot->SetMobility(EComponentMobility::Movable);
	SystemRoot->RegisterComponent();
	MakeLayer(Plumes, TEXT("SpacePlumes"), CylinderMesh, MatPlume, AstraSpaceDraw::CapPlumes, 1);
	MakeLayer(Lamps, TEXT("SpaceLamps"), SphereMesh, MatGlow, AstraSpaceDraw::CapLamps, 4);
	MakeLayer(Glints, TEXT("SpaceGlints"), SphereMesh, MatGlow, AstraSpaceDraw::CapGlints, 4);
	bLive = true;
	UE_LOG(LogASTRA, Log, TEXT("[Space] ready: %d lamps, %d plumes, %d glints; hulls in pages of %d"), AstraSpaceDraw::CapLamps, AstraSpaceDraw::CapPlumes, AstraSpaceDraw::CapGlints, AstraSpaceDraw::PageSize);
}

// ------------------------------------------------------------------------------------------------------------------ arriving and leaving
void UAstraSpaceLife::Arrive(const FString& InSystem)
{
	bPending = true;
	PendingSystem = InSystem;
}

void UAstraSpaceLife::Leave()
{
	ClearScene();
	bPending = false;
}

void UAstraSpaceLife::ClearScene()
{
	HideSets();
	for (FRigid& R : Rigids)
	{
		if (UInstancedStaticMeshComponent* C = R.Comp.Get())
		{
			C->ClearInstances();
		}
		R.Count = 0;
	}
	BuoyRigid = INDEX_NONE;
	for (FSpaceLifePlace& P : Places)
	{
		for (FSpaceLifePlace::FTurning& T : P.Parts)
		{
			if (UStaticMeshComponent* C = T.Comp.Get())
			{
				C->DestroyComponent();
			}
		}
	}
	Places.Reset();
	Traffic.Reset();
	Layout = AstraSpace::FLayout();
	Events.Reset();
	bLaidOut = false;
	for (AstraSpace::FSite& S : Wrecks.SitesMutable())
	{
		for (AstraSpace::FPieceRec& P : S.Pieces)
		{
			P.bInFx = false;                         // (the war's effects have cleared their actors with the system: what is left of a wreck is its own record)
		}
	}
	Lamps.Begin();
	Plumes.Begin();
	Glints.Begin();
	Lamps.Flush();
	Plumes.Flush();
	Glints.Flush();
}

AstraSpace::FAnchors UAstraSpaceLife::ReadAnchors() const
{
	AstraSpace::FAnchors A;
	if (!Owner || Owner->Ships.Num() == 0)
	{
		return A;
	}
	const FAstraBattleShip& P = Owner->Ships[0];
	A.Origin = P.Pos;
	if (const UAstraShipSubsystem* Ship = Owner->GetWorld() ? Owner->GetWorld()->GetSubsystem<UAstraShipSubsystem>() : nullptr)
	{
		// where the main world lies in the sky: the ship subsystem has it in the ship's frame (unset until the sky is up: then the home's own)
		const FVector W = Ship->PlanetDirectionWorld();
		if (!W.IsNearlyZero() && !W.Equals(FVector::DownVector, 1e-4))
		{
			A.PlanetDir = P.Att.RotateVector(W).GetSafeNormal();
		}
	}
	if (Owner->Landmarks.IsValidIndex(Owner->GateLandmark))
	{
		const FAstraWreck& G = Owner->Landmarks[Owner->GateLandmark];
		A.bGate = true;
		A.GatePos = G.Pos;
		A.GateAtt = G.Att;
	}
	else if (bSim)
	{
		// the bench has no Gate mesh to spawn: it stands where the opening puts it (110 km out on bearing 070, its ring facing the Aquila)
		A.bGate = true;
		A.GatePos = A.Origin + AstraSpace::FLayout::Polar(110.0 * SpKm, 70.0, 3.0);
		A.GateAtt = FRotationMatrix::MakeFromX((A.Origin - A.GatePos).GetSafeNormal()).ToQuat() * FQuat(FVector::XAxisVector, 0.3f);
	}
	return A;
}

void UAstraSpaceLife::DoArrive(const FString& InSystem)
{
	ClearScene();
	SystemName = InSystem;
	SystemKey = InSystem.ToLower();
	bPending = false;
	if (!Owner || Owner->Ships.Num() == 0)
	{
		return;
	}
	const AstraSpace::FDataSet& D = AstraSpace::Data();
	const AstraSpace::FSystemSpec* Spec = D.System(InSystem);
	if (!Spec)
	{
		UE_LOG(LogASTRA, Warning, TEXT("[Space] no spec for %s and no generic one"), *InSystem);
		return;
	}
	const AstraSpace::FAnchors A = ReadAnchors();
	Sky.Origin = A.bGate ? A.GatePos : A.Origin;                  // what the war left here is kept in the Gate's frame: it is where it was when the Captain comes back
	Sky.Att = A.bGate ? A.GateAtt : FQuat::Identity;
	Wrecks.Settle(WreckClock());
	// the same system always lays out the same (its rocks, its lanes); its traffic is the day's
	Seed = (uint32)GetTypeHash(InSystem.ToLower());
	AstraSpace::BuildLayout(*Spec, D, A, Seed, Layout);
	MakePlaces();
	MakeRocksAndBuoys();
	const double Now = Owner->GetBattleTime();
	const uint32 TrafficSeed = GAstraDeterministic ? Seed : (uint32)(FDateTime::Now().GetTicks() & 0x7fffffff);
	Traffic.Init(D, Layout, TrafficSeed, Now, FMath::Max(0.f, CVarSpaceDensity.GetValueOnGameThread()));
	Traffic.Warmup(300.0, 1.0);                 // five minutes ahead: the lanes are busy when the Aquila comes in
	bLaidOut = true;
	TickMs = TickMsMax = TrafficMs = DrawMs = 0.0;
	TickCount = 0;
	TArray<int32> Left;
	Wrecks.Of(SystemKey, Left);
	UE_LOG(LogASTRA, Log, TEXT("[Space] %s: %d places, %d lanes, %d rocks, %d vessels, %d patrols, %d wrecks of the war"), *InSystem, Layout.Nodes.Num(), Layout.Lanes.Num(), Layout.Rocks.Num(),
	       Traffic.Vessels().Num(), Traffic.Patrols().Num(), Left.Num());
}

FAstraBattleShip* UAstraSpaceLife::ShipOfPlace(const FSpaceLifePlace& P) const
{
	return Owner && P.ShipId >= 0 ? Owner->FindById(P.ShipId) : nullptr;
}

void UAstraSpaceLife::MakePlaces()
{
	if (!Owner)
	{
		return;
	}
	UWorld* World = Owner->GetWorld();
	for (int32 n = 0; n < Layout.Nodes.Num(); ++n)
	{
		AstraSpace::FNode& N = Layout.Nodes[n];
		const AstraSpace::FPlaceSpec* Sp = N.Spec;
		if (!Sp || Sp->Contact.IsEmpty() || Sp->Mesh.IsEmpty())
		{
			continue;                                   // a place with no body in the plot (the Gate has its own, an orbit and a belt are only points)
		}
		UStaticMesh* Mesh = nullptr;
		if (bLive)
		{
			Mesh = LoadObject<UStaticMesh>(nullptr, *FString::Printf(TEXT("/Game/ASTRA/Space/%s.%s"), *Sp->Mesh, *Sp->Mesh), nullptr, LOAD_Quiet | LOAD_NoWarn);
			if (!Mesh)
			{
				UE_LOG(LogASTRA, Warning, TEXT("[Space] %s: no mesh %s yet (art/blender/spacegen3.py, tools/ue_scripts/import_space_v3.py): the place is left out"), *N.Name, *Sp->Mesh);
				continue;
			}
			KeepMeshes.AddUnique(Mesh);
		}
		// its ship in the battle's plot: a fixture (nobody fights over it, nothing hits it, it does not move), a neutral contact the crew can name, put on the screen, steer for
		const int32 I = Owner->AddShip(Sp->Contact, Sp->Name, Sp->Class.IsEmpty() ? FString(TEXT("Station")) : Sp->Class, Sp->Mesh, EAstraSide::Neutral, N.Pos, 0.f, 0.f, N.RadiusM, 9000.f, 0.f);
		FAstraBattleShip& S = Owner->Ships[I];
		S.Att = N.Att;
		S.Vel = FVector::ZeroVector;
		S.bFixture = true;
		S.bHoldStation = true;
		S.bFixedAtt = true;
		S.RailDamage = 0.f;
		S.Missiles = 0;
		S.PDChannels = 0;
		S.Mode = EAstraShipMode::Idle;
		S.Radius = N.RadiusM;
		FSpaceLifePlace P;
		P.Id = N.Id;
		P.Node = n;
		P.ShipId = S.Id;
		if (Mesh && World)
		{
			FActorSpawnParameters Par;
			Par.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
			AStaticMeshActor* A = World->SpawnActor<AStaticMeshActor>(FVector::ZeroVector, FRotator::ZeroRotator, Par);
			if (A)
			{
				A->SetMobility(EComponentMobility::Movable);
				UStaticMeshComponent* C = A->GetStaticMeshComponent();
				C->SetStaticMesh(Mesh);
				C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
				C->SetCastShadow(false);                 // km-scale shadows are invisible and cost virtual shadow pages
				C->bAffectDynamicIndirectLighting = false;
				C->bAffectDistanceFieldLighting = false;
				C->SetLightingChannels(true, true, false);   // outside the hull: the star's light and the planet's
				A->Tags.Add(TEXT("ASTRA.Sky"));
				A->SetActorLocationAndRotation(Owner->ToWorld(N.Pos), Owner->ToWorldRot(N.Att));
				S.Actor = A;
				P.Actor = A;
				// what turns on it: the control ring of Keeper Station, a crane
				if (N.Mesh)
				{
					for (const AstraSpace::FPart& Part : N.Mesh->Parts)
					{
						UStaticMesh* PM = LoadObject<UStaticMesh>(nullptr, *FString::Printf(TEXT("/Game/ASTRA/Space/%s.%s"), *Part.Mesh, *Part.Mesh), nullptr, LOAD_Quiet | LOAD_NoWarn);
						if (!PM)
						{
							continue;
						}
						KeepMeshes.AddUnique(PM);
						UStaticMeshComponent* PC = NewObject<UStaticMeshComponent>(A);
						PC->SetupAttachment(A->GetRootComponent());
						PC->SetMobility(EComponentMobility::Movable);
						PC->SetStaticMesh(PM);
						PC->SetCollisionEnabled(ECollisionEnabled::NoCollision);
						PC->SetCastShadow(false);
						PC->bAffectDynamicIndirectLighting = false;
						PC->SetLightingChannels(true, true, false);
						PC->SetRelativeLocation(Part.Pivot * 100.0);
						PC->RegisterComponent();
						FSpaceLifePlace::FTurning T;
						T.Comp = PC;
						T.Def = Part;
						P.Parts.Add(T);
					}
				}
			}
		}
		Places.Add(MoveTemp(P));
	}
}

void UAstraSpaceLife::MakeRocksAndBuoys()
{
	if (!bLive || !SystemRoot)
	{
		return;
	}
	const float RockScale = FMath::Clamp(CVarSpaceRocks.GetValueOnGameThread(), 0.f, 2.f);
	if (Layout.Spec && Layout.Spec->Rocks.bOn && RockScale > 0.f)
	{
		const AstraSpace::FRockSpec& K = Layout.Spec->Rocks;
		TArray<int32> Rg;
		for (const FString& M : K.Meshes)
		{
			Rg.Add(RigidFor(M));
		}
		const int32 Keep = FMath::RoundToInt(Layout.Rocks.Num() * FMath::Min(RockScale, 1.f));
		TArray<TArray<FTransform>> PerMesh;
		PerMesh.SetNum(K.Meshes.Num());
		for (int32 i = 0; i < Keep && i < Layout.Rocks.Num(); ++i)
		{
			const AstraSpace::FRock& R = Layout.Rocks[i];
			if (PerMesh.IsValidIndex(R.Mesh) && Rg.IsValidIndex(R.Mesh) && Rg[R.Mesh] != INDEX_NONE)
			{
				// the rock meshes are made 100 m across (art/blender/spacegen3.py): a rock of SizeM metres is that many hundredths of one
				PerMesh[R.Mesh].Add(FTransform(R.Att, R.Pos * 100.0, FVector(R.SizeM / 100.0)));
			}
		}
		for (int32 m = 0; m < PerMesh.Num(); ++m)
		{
			if (Rg[m] != INDEX_NONE && PerMesh[m].Num() && Rigids[Rg[m]].Comp.IsValid())
			{
				Rigids[Rg[m]].Comp->AddInstances(PerMesh[m], false, false, false);
				Rigids[Rg[m]].Count += PerMesh[m].Num();
			}
		}
	}
	// the route buoys: a lamp-topped lattice every few kilometres along each lane (their lights are drawn with the rest of the lamps)
	const int32 B = RigidFor(TEXT("SM_BUOY_Lane"));
	if (B != INDEX_NONE && Rigids[B].Comp.IsValid())
	{
		TArray<FTransform> Xf;
		for (const AstraSpace::FLane& L : Layout.Lanes)
		{
			for (const FVector& P : L.Buoys)
			{
				Xf.Add(FTransform(FQuat(FVector::ZAxisVector, FMath::DegreesToRadians((float)((GetTypeHash(P.X) >> 3) % 360))), P * 100.0, FVector::OneVector));
			}
		}
		if (Xf.Num())
		{
			Rigids[B].Comp->AddInstances(Xf, false, false, false);
			Rigids[B].Count = Xf.Num();
		}
		BuoyRigid = B;
	}
}

int32 UAstraSpaceLife::RigidFor(const FString& Mesh)
{
	for (int32 i = 0; i < Rigids.Num(); ++i)
	{
		if (Rigids[i].Mesh == Mesh)
		{
			return Rigids[i].Comp.IsValid() ? i : INDEX_NONE;
		}
	}
	FRigid R;
	R.Mesh = Mesh;
	UStaticMesh* M = LoadObject<UStaticMesh>(nullptr, *FString::Printf(TEXT("/Game/ASTRA/Space/%s.%s"), *Mesh, *Mesh), nullptr, LOAD_Quiet | LOAD_NoWarn);
	if (M && Host && SystemRoot)
	{
		// instanced Nanite meshes are shaded only if their materials are flagged for instancing (tools/ue_scripts/make_scala_materials.py: the hull base material)
		FString Unflagged;
		for (const FStaticMaterial& SM : M->GetStaticMaterials())
		{
			if (SM.MaterialInterface && !SM.MaterialInterface->GetUsageByFlag(MATUSAGE_InstancedStaticMeshes))
			{
				Unflagged += SM.MaterialInterface->GetName() + TEXT(" ");
			}
		}
		if (Unflagged.IsEmpty())
		{
			KeepMeshes.AddUnique(M);
			R.Comp = AstraDraw::MakeComp(Host, SystemRoot, *FString::Printf(TEXT("Rigid_%s"), *Mesh), M, nullptr, 0, 0, false, true);
		}
		else
		{
			UE_LOG(LogASTRA, Warning, TEXT("[Space] %s: its materials (%s) are not flagged 'Used with Instanced Static Meshes' (tools/ue_scripts/make_scala_materials.py): left out"), *Mesh, *Unflagged.TrimEnd());
		}
	}
	else if (!M)
	{
		UE_LOG(LogASTRA, Log, TEXT("[Space] no mesh %s yet: its instances are left out"), *Mesh);
	}
	Rigids.Add(R);
	return R.Comp.IsValid() ? Rigids.Num() - 1 : INDEX_NONE;
}

// ------------------------------------------------------------------------------------------------------------------ the world, as the traffic sees it
void UAstraSpaceLife::ReadWorld()
{
	View = AstraSpace::FWorldView();
	if (!Owner || Owner->Ships.Num() == 0)
	{
		return;
	}
	const FAstraBattleShip& P = Owner->Ships[0];
	View.Aquila = P.Pos;
	View.AquilaVel = P.Vel;
	View.AquilaRadiusM = P.Radius;
	for (const FAstraBattleShip& S : Owner->Ships)
	{
		if (!S.bAlive || S.bPlayer || S.bFixture || S.bGhost)
		{
			continue;
		}
		if (S.Side == EAstraSide::Mandate && S.bHostile && !S.bDisabled && !S.bCold)
		{
			if (!S.bCraft || FVector::Dist(S.Pos, P.Pos) < 160.0 * SpKm)
			{
				AstraSpace::FHostile H;
				H.Pos = S.Pos;
				H.Vel = S.Vel;
				H.bCraft = S.bCraft;
				View.Hostiles.Add(H);
			}
		}
		else if (!S.bCraft && S.Radius >= 60.f)
		{
			AstraSpace::FObstacle O;
			O.Pos = S.Pos;
			O.RadiusM = S.Radius;
			View.Obstacles.Add(O);
		}
	}
	if (bTestHostile)
	{
		AstraSpace::FHostile H;
		H.Pos = TestHostile;
		View.Hostiles.Add(H);
	}
	View.bGateBusy = Owner->GateRun != EAstraGateRun::None;
	View.bEngagement = Owner->bEngagementActive;
	const int32 React = CVarSpaceReact.GetValueOnGameThread();
	if (React == 0)
	{
		View.Hostiles.Reset();                                // (the test hostile too: the switch is for peace)
		View.bEngagement = false;
	}
	else if (React == 2)
	{
		// the war is not heard, only the console's test hostile (the bench's war test: the opening's own war goes on unseen)
		View.Hostiles.Reset();
		if (bTestHostile)
		{
			AstraSpace::FHostile H;
			H.Pos = TestHostile;
			View.Hostiles.Add(H);
		}
		View.bEngagement = false;
	}
}

void UAstraSpaceLife::FlushEvents()
{
	for (const AstraSpace::FEvent& E : Events)
	{
		if (E.Kind == AstraSpace::EEventKind::GatePulse)
		{
			if (Owner)
			{
				Owner->PulseGate(0.22f * E.Strength);      // the ring flares a little: a vessel went through or came out (the lane's own wave is the Aquila's transit)
			}
			continue;
		}
		if (!E.Text.IsEmpty() && Owner)
		{
			Owner->Report(E.Text, E.bReport);
		}
	}
	Events.Reset();
}

// ------------------------------------------------------------------------------------------------------------------ a frame
void UAstraSpaceLife::Tick(float SimDt, float RealDt)
{
	if (!IsActive() || !Owner || Owner->Ships.Num() == 0)
	{
		return;
	}
	const double T0 = FPlatformTime::Seconds();
	Dt = FMath::Clamp(RealDt, 0.f, 0.1f);
	Clock += Dt;
	++Frame;
	const FAstraBattleShip& A = Owner->Ships[0];
	F.Origin = A.bAlive ? A.Pos : FVector::ZeroVector;
	F.InvAtt = A.Att.Inverse();
	F.Bridge = Owner->BridgeOffset;
	if (bPending)
	{
		// the sky is up a frame after the transit (the planet's direction is read from it): lay the system out now
		DoArrive(PendingSystem);
	}
	if (!bLaidOut)
	{
		return;
	}
	if ((HostileScanT -= Dt) <= 0.0)
	{
		HostileScanT = 0.25;
		ReadWorld();
	}
	const double T1 = FPlatformTime::Seconds();
	Traffic.Tick(Owner->GetBattleTime() + 0.0, SimDt, View, Events);
	TickWrecks(SimDt);                              // what the war left: the effects' pieces handed over, the beacons heard, a close look (their events join the traffic's)
	FlushEvents();
	const double T2 = FPlatformTime::Seconds();
	if (CVarSpaceDraw.GetValueOnGameThread() != 0)
	{
		Lamps.Begin();
		Plumes.Begin();
		Glints.Begin();
		float Fx = 1.f;
		if (const TConsoleVariableData<float>* V = IConsoleManager::Get().FindTConsoleVariableDataFloat(TEXT("astra.fx.intensity")))
		{
			Fx = FMath::Clamp(V->GetValueOnGameThread(), 0.1f, 6.f);
		}
		LampGain = Fx;
		HullsNow = LampsDropped = 0;
		DrawPlaces();
		DrawVessels();
		DrawPatrols();
		{
			const double W0 = FPlatformTime::Seconds();
			DrawWrecks(WreckClock());
			WrecksMs += (FPlatformTime::Seconds() - W0) * 1000.0;
		}
		FlushSets();
		Lamps.Flush();
		Plumes.Flush();
		Glints.Flush();
		LampsNow = Lamps.Prev;
		PlumesNow = Plumes.Prev;
		LampsPeak = FMath::Max(LampsPeak, LampsNow);
		HullsPeak = FMath::Max(HullsPeak, HullsNow);
		if (SystemRoot)
		{
			// everything still in the system frame (the belt, the buoys) moves with this one transform
			SystemRoot->SetWorldLocationAndRotation(F.ToWorld(FVector::ZeroVector), F.InvAtt);
		}
	}
	const double T3 = FPlatformTime::Seconds();
	TrafficMs += (T2 - T1) * 1000.0;
	DrawMs += (T3 - T2) * 1000.0;
	const double Ms = (T3 - T0) * 1000.0;
	TickMs += Ms;
	TickMsMax = FMath::Max(TickMsMax, Ms);
	++TickCount;
}

void UAstraSpaceLife::Skip(double Seconds)
{
	if (bLaidOut)
	{
		Traffic.Warmup(FMath::Clamp(Seconds, 0.0, 7200.0), 1.0);
		AdvanceWrecks(Seconds);                     // (the wrecks drift on as well, and the lifepods' air goes)
	}
}

void UAstraSpaceLife::SetTestHostile(bool bOn, const FVector& Pos)
{
	bTestHostile = bOn;
	TestHostile = Pos;
	HostileScanT = 0.0;
}

// ------------------------------------------------------------------------------------------------------------------ what the rest of the game may ask
FString UAstraSpaceLife::Stat() const
{
	int32 Buoys = 0;
	for (const AstraSpace::FLane& L : Layout.Lanes)
	{
		Buoys += L.Buoys.Num();
	}
	return FString::Printf(TEXT("%s | %s | tick %.4f ms avg (max %.3f): traffic %.4f, drawing %.4f | drawn: hulls %d now / %d peak, lamps %d now / %d peak (%d dropped), plumes %d | places %d, lanes %d, buoys %d, rocks %d | %s"),
	                       bLive ? TEXT("drawing") : (bSim ? TEXT("bench (not drawn)") : TEXT("off")), *Traffic.Describe(), TickCount ? TickMs / TickCount : 0.0, TickMsMax,
	                       TickCount ? TrafficMs / TickCount : 0.0, TickCount ? DrawMs / TickCount : 0.0, HullsNow, HullsPeak, LampsNow, LampsPeak, LampsDropped, PlumesNow, Places.Num(), Layout.Lanes.Num(),
	                       Buoys, Layout.Rocks.Num(), *WreckStat());
}

FString UAstraSpaceLife::WhereText() const
{
	FString Out = FString::Printf(TEXT("%s: "), *SystemName);
	if (!Owner || Owner->Ships.Num() == 0)
	{
		return Out;
	}
	const FVector Me = Owner->Ships[0].Pos;
	for (const AstraSpace::FNode& N : Layout.Nodes)
	{
		Out += FString::Printf(TEXT("\n  %-18s %-8s bearing %03.0f mark %+.0f  %.1f km%s"), *N.Name, AstraSpace::PlaceKindName(N.Kind), Owner->BearingTo(N.Pos), Owner->MarkTo(N.Pos),
		                       FVector::Dist(Me, N.Pos) / SpKm, N.bClosed ? TEXT("  (closed)") : TEXT(""));
	}
	return Out;
}

TSharedRef<FJsonObject> UAstraSpaceLife::SummaryJson() const
{
	TSharedRef<FJsonObject> O = MakeShared<FJsonObject>();
	if (!bLaidOut || !Owner || Owner->Ships.Num() == 0)
	{
		return O;
	}
	const FVector Me = Owner->Ships[0].Pos;
	O->SetStringField(TEXT("system"), SystemName);
	TArray<TSharedPtr<FJsonValue>> Pl;
	for (const AstraSpace::FNode& N : Layout.Nodes)
	{
		if (N.Kind == AstraSpace::EPlaceKind::Orbit || N.Kind == AstraSpace::EPlaceKind::Belt)
		{
			continue;
		}
		TSharedRef<FJsonObject> P = MakeShared<FJsonObject>();
		P->SetStringField(TEXT("name"), N.Name);
		if (N.Spec && !N.Spec->Contact.IsEmpty())
		{
			P->SetStringField(TEXT("contact"), N.Spec->Contact);
		}
		P->SetStringField(TEXT("kind"), AstraSpace::PlaceKindName(N.Kind));
		P->SetNumberField(TEXT("bearing_deg"), FMath::RoundToDouble(Owner->BearingTo(N.Pos)));
		P->SetNumberField(TEXT("mark_deg"), FMath::RoundToDouble(Owner->MarkTo(N.Pos)));
		P->SetNumberField(TEXT("range_km"), FMath::RoundToDouble(FVector::Dist(Me, N.Pos) / 100.0) / 10.0);
		if (N.bClosed)
		{
			P->SetStringField(TEXT("status"), TEXT("closed to civilian traffic"));
		}
		Pl.Add(MakeShared<FJsonValueObject>(P));
	}
	O->SetArrayField(TEXT("places"), Pl);
	const AstraSpace::FTrafficStats& St = Traffic.Stats();
	TSharedRef<FJsonObject> T = MakeShared<FJsonObject>();
	T->SetNumberField(TEXT("vessels"), St.Vessels - St.Away);
	T->SetNumberField(TEXT("under_way"), St.InFlight);
	T->SetNumberField(TEXT("docked"), St.Docked);
	T->SetNumberField(TEXT("gate_queue"), St.QueueGate);
	static const TCHAR* const Alerts[3] = {TEXT("calm"), TEXT("alert: hostile contacts near the lanes; civilian traffic is diverting"), TEXT("lockdown: hostiles at a place; civilian traffic is running or hiding")};
	T->SetStringField(TEXT("state"), Alerts[FMath::Clamp(Traffic.AlertLevel(), 0, 2)]);
	// the nearest few the Aquila's eyes could pick out, with what they are doing
	TArray<TPair<double, const AstraSpace::FVessel*>> Near;
	for (const AstraSpace::FVessel& V : Traffic.Vessels())
	{
		if (V.State != AstraSpace::EVState::Away)
		{
			const double D = FVector::Dist(Me, V.Pos);
			if (D < 45.0 * SpKm)
			{
				Near.Add({D, &V});
			}
		}
	}
	Near.Sort([](const TPair<double, const AstraSpace::FVessel*>& A, const TPair<double, const AstraSpace::FVessel*>& B) { return A.Key < B.Key; });
	TArray<TSharedPtr<FJsonValue>> Nv;
	for (int32 i = 0; i < FMath::Min(4, Near.Num()); ++i)
	{
		const AstraSpace::FVessel& V = *Near[i].Value;
		const AstraSpace::FHullDef* H = AstraSpace::Data().Hull(V.Hull);
		TSharedRef<FJsonObject> J = MakeShared<FJsonObject>();
		J->SetStringField(TEXT("name"), V.Name);
		J->SetStringField(TEXT("class"), H ? H->Class : FString());
		J->SetNumberField(TEXT("bearing_deg"), FMath::RoundToDouble(Owner->BearingTo(V.Pos)));
		J->SetNumberField(TEXT("range_km"), FMath::RoundToDouble(Near[i].Key / 100.0) / 10.0);
		FString Doing = AstraSpace::StateName(V.State);
		if (V.Node != INDEX_NONE && Layout.Nodes.IsValidIndex(V.Node) && (V.State == AstraSpace::EVState::Cruise || V.State == AstraSpace::EVState::Docked || V.State == AstraSpace::EVState::Docking || V.State == AstraSpace::EVState::Fleeing))
		{
			Doing += (V.State == AstraSpace::EVState::Docked ? TEXT(" at ") : TEXT(" for ")) + Layout.Nodes[V.Node].Name;
		}
		J->SetStringField(TEXT("doing"), Doing);
		Nv.Add(MakeShared<FJsonValueObject>(J));
	}
	if (Nv.Num())
	{
		T->SetArrayField(TEXT("nearest"), Nv);
	}
	O->SetObjectField(TEXT("traffic"), T);
	// what the war has left here: the wrecks near enough to pick out and the lifepods whose beacons are heard
	const TSharedRef<FJsonObject> W = WreckSummaryJson();
	if (W->HasField(TEXT("here")) && (W->GetNumberField(TEXT("here")) > 0.0 || W->HasField(TEXT("lifepods"))))
	{
		O->SetObjectField(TEXT("wrecks"), W);
	}
	return O;
}

TSharedRef<FJsonObject> UAstraSpaceLife::BenchJson() const
{
	TSharedRef<FJsonObject> O = MakeShared<FJsonObject>();
	const AstraSpace::FTrafficStats& St = Traffic.Stats();
	O->SetStringField(TEXT("system"), SystemName);
	O->SetNumberField(TEXT("vessels"), St.Vessels);
	O->SetNumberField(TEXT("docked"), St.Docked);
	O->SetNumberField(TEXT("in_flight"), St.InFlight);
	O->SetNumberField(TEXT("away"), St.Away);
	O->SetNumberField(TEXT("gate_queue"), St.QueueGate);
	O->SetNumberField(TEXT("max_gate_queue"), St.MaxQueue);
	O->SetNumberField(TEXT("gate_out"), St.GateOutTotal);
	O->SetNumberField(TEXT("gate_in"), St.GateInTotal);
	O->SetNumberField(TEXT("dockings"), St.DockedTotal);
	O->SetNumberField(TEXT("departures"), St.DepartedTotal);
	O->SetNumberField(TEXT("maydays"), St.Maydays);
	O->SetNumberField(TEXT("alerted"), St.Alerted);
	O->SetNumberField(TEXT("alert_level"), Traffic.AlertLevel());
	O->SetNumberField(TEXT("traffic_ms_avg"), St.Ticks ? St.TickMs / St.Ticks : 0.0);
	O->SetNumberField(TEXT("traffic_ms_max"), St.TickMsMax);
	O->SetNumberField(TEXT("space_ms_avg"), TickCount ? TickMs / TickCount : 0.0);
	O->SetNumberField(TEXT("space_ms_max"), TickMsMax);
	O->SetNumberField(TEXT("lamps_peak"), LampsPeak);
	O->SetNumberField(TEXT("hulls_peak"), HullsPeak);
	{
		const AstraSpace::FWreckStats Ws = Wrecks.Stats(SystemName, WreckClock());
		O->SetNumberField(TEXT("wreck_sites"), Ws.Sites);
		O->SetNumberField(TEXT("wreck_sites_here"), Ws.SitesHere);
		O->SetNumberField(TEXT("wreck_pieces"), Ws.Pieces);
		O->SetNumberField(TEXT("wreck_chunks"), Ws.Chunks);
		O->SetNumberField(TEXT("pods"), Ws.Pods);
		O->SetNumberField(TEXT("pods_adrift"), Ws.PodsAdrift);
		O->SetNumberField(TEXT("pods_recovered"), Ws.PodsRecovered);
		O->SetNumberField(TEXT("pods_lost"), Ws.PodsLost);
		O->SetNumberField(TEXT("pod_survivors_adrift"), Ws.Survivors);
		O->SetNumberField(TEXT("rescued"), Ws.Rescued);
		O->SetNumberField(TEXT("losses"), Ws.Losses);
		O->SetNumberField(TEXT("wreck_ms_avg"), TickCount ? WrecksMs / TickCount : 0.0);
		O->SetNumberField(TEXT("wreck_hulls_peak"), WreckHullsPeak);
		O->SetNumberField(TEXT("wreck_chunks_peak"), ChunksPeak);
	}
	TArray<TSharedPtr<FJsonValue>> States;
	for (int32 s = 0; s < (int32)AstraSpace::EVState::Num; ++s)
	{
		TSharedRef<FJsonObject> J = MakeShared<FJsonObject>();
		J->SetStringField(TEXT("state"), AstraSpace::StateName((AstraSpace::EVState)s));
		J->SetNumberField(TEXT("n"), St.ByState[s]);
		States.Add(MakeShared<FJsonValueObject>(J));
	}
	O->SetArrayField(TEXT("by_state"), States);
	return O;
}

bool UAstraSpaceLife::LookAt(const FString& Key, double Km, FString& OutDetail)
{
	if (!bLaidOut || !Owner || Owner->Ships.Num() == 0)
	{
		OutDetail = TEXT("no living space laid out here");
		return false;
	}
	const AstraSpace::FNode* Hit = nullptr;
	for (const AstraSpace::FNode& N : Layout.Nodes)
	{
		if (N.Id.ToString().Equals(Key, ESearchCase::IgnoreCase) || N.Name.Contains(Key, ESearchCase::IgnoreCase) || (N.Spec && N.Spec->Contact.Equals(Key, ESearchCase::IgnoreCase)))
		{
			Hit = &N;
			break;
		}
	}
	if (!Hit)
	{
		OutDetail = FString::Printf(TEXT("no place called %s (try astra.space.where)"), *Key);
		return false;
	}
	FAstraBattleShip& P = Owner->Ships[0];
	FVector Out = P.Pos - Hit->Pos;
	Out = Out.IsNearlyZero() ? FVector(1.0, 0.0, 0.0) : Out.GetSafeNormal();
	P.Pos = Hit->Pos + Out * (Km * SpKm);
	P.Vel = FVector::ZeroVector;
	const FVector Dir = -Out;
	if (UAstraShipSubsystem* Ship = Owner->GetWorld()->GetSubsystem<UAstraShipSubsystem>())
	{
		Ship->DriveExternally((float)FMath::RadiansToDegrees(FMath::Atan2(Dir.Y, Dir.X)), (float)FMath::RadiansToDegrees(FMath::Atan2(Dir.Z, FVector2D(Dir.X, Dir.Y).Size())), 0.f);
		Ship->SetSpeedMps(0.f);
		Ship->SetThrottle(0.f);
	}
	OutDetail = FString::Printf(TEXT("the Aquila is %.1f km from %s, bow on it"), Km, *Hit->Name);
	return true;
}

// ------------------------------------------------------------------------------------------------------------------ the console
namespace
{
	UAstraSpaceLife* SpaceOf(UWorld* World)
	{
		UAstraBattleSubsystem* B = World ? World->GetSubsystem<UAstraBattleSubsystem>() : nullptr;
		return B ? B->GetSpace() : nullptr;
	}

	FAutoConsoleCommandWithWorld CmdSpaceStat(TEXT("astra.space.stat"), TEXT("What the living space holds and what it costs: traffic, drawing, places"),
		FConsoleCommandWithWorldDelegate::CreateLambda([](UWorld* W)
		{
			if (UAstraSpaceLife* S = SpaceOf(W)) { UE_LOG(LogASTRA, Display, TEXT("[Space] %s"), *S->Stat()); }
			else { UE_LOG(LogASTRA, Display, TEXT("[Space] none in this world")); }
		}));

	FAutoConsoleCommandWithWorld CmdSpaceWhere(TEXT("astra.space.where"), TEXT("The places of this system: bearing, mark and range from the Aquila"),
		FConsoleCommandWithWorldDelegate::CreateLambda([](UWorld* W)
		{
			if (UAstraSpaceLife* S = SpaceOf(W)) { UE_LOG(LogASTRA, Display, TEXT("[Space] %s"), *S->WhereText()); }
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdSpaceLook(TEXT("astra.space.look"), TEXT("Put the Aquila a few km from a place, bow on it: astra.space.look <keeper|arsenal|tiberius|id|name> [km, default 12]"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& A, UWorld* W)
		{
			UAstraSpaceLife* S = SpaceOf(W);
			if (!S || A.Num() < 1) { UE_LOG(LogASTRA, Display, TEXT("[Space] astra.space.look <place> [km]")); return; }
			FString Detail;
			S->LookAt(A[0], A.Num() > 1 ? FCString::Atod(*A[1]) : 12.0, Detail);
			UE_LOG(LogASTRA, Display, TEXT("[Space] %s"), *Detail);
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdSpaceSkip(TEXT("astra.space.skip"), TEXT("Run the traffic ahead: astra.space.skip <seconds>"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& A, UWorld* W)
		{
			if (UAstraSpaceLife* S = SpaceOf(W)) { S->Skip(A.Num() ? FCString::Atod(*A[0]) : 60.0); }
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdSpaceAlert(TEXT("astra.space.alert"), TEXT("Test the traffic's reactions with a hostile warship that is not there: astra.space.alert <km> puts it that far from the Aquila on her bow, astra.space.alert vessel puts it 9 km from the vessel nearest her, astra.space.alert 0 takes it away"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& A, UWorld* W)
		{
			UAstraBattleSubsystem* B = W ? W->GetSubsystem<UAstraBattleSubsystem>() : nullptr;
			UAstraSpaceLife* S = B ? B->GetSpace() : nullptr;
			if (!S || !B) { return; }
			if (A.Num() && A[0].Equals(TEXT("vessel"), ESearchCase::IgnoreCase))
			{
				const AstraSpace::FVessel* Near = nullptr;
				double Best = 1e18;
				for (const AstraSpace::FVessel& V : S->GetTraffic().Vessels())
				{
					const double D = FVector::Dist(V.Pos, B->PlayerPos());
					if ((V.State == AstraSpace::EVState::Cruise || V.State == AstraSpace::EVState::Holding) && D < Best)
					{
						Best = D;
						Near = &V;
					}
				}
				if (!Near) { UE_LOG(LogASTRA, Display, TEXT("[Space] no vessel under way to put a hostile by")); return; }
				const FVector Side = FVector::CrossProduct(FVector::UpVector, Near->Vel.GetSafeNormal());
				S->SetTestHostile(true, Near->Pos + Side * 9.0 * SpKm);
				UE_LOG(LogASTRA, Display, TEXT("[Space] a test hostile 9 km abeam of %s (%.0f km from the Aquila): watch astra.space.stat"), *Near->Name, Best / SpKm);
				return;
			}
			const double Km = A.Num() ? FCString::Atod(*A[0]) : 20.0;
			if (Km <= 0.0) { S->SetTestHostile(false, FVector::ZeroVector); UE_LOG(LogASTRA, Display, TEXT("[Space] the test hostile is gone")); return; }
			S->SetTestHostile(true, B->PlayerPos() + B->PlayerAtt().GetForwardVector() * Km * SpKm);
			UE_LOG(LogASTRA, Display, TEXT("[Space] a test hostile %.0f km on the bow: watch astra.space.stat"), Km);
		}));

	FAutoConsoleCommandWithWorld CmdSpaceReload(TEXT("astra.space.reload"), TEXT("Read data/space again and lay the system out afresh (places, rocks, traffic)"),
		FConsoleCommandWithWorldDelegate::CreateLambda([](UWorld* W)
		{
			AstraSpace::ReloadData();
			if (UAstraSpaceLife* S = SpaceOf(W)) { S->Arrive(S->GetSystem().IsEmpty() ? FString(TEXT("Aurelia")) : S->GetSystem()); }
		}));
}
