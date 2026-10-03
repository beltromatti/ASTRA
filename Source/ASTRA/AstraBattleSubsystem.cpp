// ASTRA — battle simulation.

#include "AstraBattleSubsystem.h"
#include "AstraHullName.h"
#include "AstraWarFX.h"
#include "AstraWarDraw.h"
#include "Misc/Crc.h"
#include "EngineUtils.h"
#include "Components/DecalComponent.h"

#include "ASTRA.h"
#include "AstraNavLights.h"
#include "AstraShipSubsystem.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/World.h"
#include "Kismet/GameplayStatics.h"
#include "Camera/PlayerCameraManager.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Sound/SoundBase.h"
#include "HAL/PlatformTime.h"

DECLARE_CYCLE_STAT(TEXT("Battle tick"), STAT_AstraBattle, STATGROUP_Astra);
DECLARE_CYCLE_STAT(TEXT("War draw"), STAT_AstraWarDraw, STATGROUP_Astra);
DECLARE_CYCLE_STAT(TEXT("War FX"), STAT_AstraWarFx, STATGROUP_Astra);

namespace
{
	const double OneKm = 1000.0;
	// ASTRA classes (the Mandate's are set where they spawn)
	void BattleshipStats(FAstraBattleShip& S)
	{
		S.RailSlugs = 4;          // six triple turrets firing in pairs: four heavy slugs per volley
		S.RailDamage = 72.f;
		S.RailCd = 9.f;
		S.RailRange = 10000.f;
		S.Missiles = 24;
		S.PDChannels = 4;
		S.ShieldRegen = 8.f;
	}
	void DestroyerStats(FAstraBattleShip& S)
	{
		S.RailSlugs = 2;
		S.RailDamage = 55.f;
		S.RailCd = 7.f;
		S.Missiles = 12;
		S.PDChannels = 2;
		S.ShieldRegen = 5.f;
	}
	FVector Polar(double RangeM, double BearingDeg, double MarkDeg)
	{
		const double B = FMath::DegreesToRadians(BearingDeg), M = FMath::DegreesToRadians(MarkDeg);
		return FVector(RangeM * FMath::Cos(M) * FMath::Cos(B), RangeM * FMath::Cos(M) * FMath::Sin(B), RangeM * FMath::Sin(M));
	}
	FQuat HeadingQuat(double HeadingDeg, double MarkDeg) { return FRotator(MarkDeg, HeadingDeg, 0.0).Quaternion(); }
	const FLinearColor RailColor(1.0f, 0.75f, 0.45f);
	const FLinearColor AstraShield(0.35f, 0.65f, 1.0f);
	const FLinearColor MandateShield(1.0f, 0.55f, 0.2f);

	// development: jump the scenario clock / speed up the battle
	float GBattleTimeScale = 1.f;
	float GBattleJumpTo = -1.f;
	struct FSpawnRequest { FString Kind; float RangeKm; float RelBearing; };
	TArray<FSpawnRequest> GSpawnRequests;
	TArray<FString> GKillRequests;
	TArray<TArray<FString>> GTransitRequests;
	FAutoConsoleCommand CmdBattleTransit(TEXT("astra.battle.transit"),
		TEXT("Janus transit (testing; the helm flies to the gate): astra.battle.transit <system_name> [red_dwarf|orange|yellow|blue_white] [ocean|desert|ice|lava|gas_giant|barren] [planet_name]"),
		FConsoleCommandWithArgsDelegate::CreateLambda([](const TArray<FString>& A) { if (A.Num() >= 1) { GTransitRequests.Add(A); } }));
	TArray<TArray<FString>> GArriveRequests;
	FAutoConsoleCommand CmdBattleArrive(TEXT("astra.battle.arrive"),
		TEXT("Testing: come out of a gate at once, no lane: astra.battle.arrive <system_name> [star] [planet type] [planet_name]"),
		FConsoleCommandWithArgsDelegate::CreateLambda([](const TArray<FString>& A) { if (A.Num() >= 1) { GArriveRequests.Add(A); } }));
	bool GStatusRequest = false;
	FAutoConsoleCommand CmdBattleStatus(TEXT("astra.battle.status"), TEXT("Log every ship's hull, shields, target and mode (balancing)"),
		FConsoleCommandDelegate::CreateLambda([]() { GStatusRequest = true; }));
	bool GGateJump = false;
	FAutoConsoleCommand CmdBattleGateJump(TEXT("astra.battle.gatejump"), TEXT("Testing: put the Aquila 30 km in front of the Janus Gate, bow on"),
		FConsoleCommandDelegate::CreateLambda([]() { GGateJump = true; }));
	/** A percentage for the snapshot: a derelict has no shields at all (0 of 0), and JSON has no NaN. */
	double Pct(double V, double Max)
	{
		return Max > 0.0 ? FMath::RoundToDouble(100.0 * V / Max) : 0.0;
	}
	FString EtaText(double Seconds)
	{
		const int32 S = FMath::Max(0, FMath::RoundToInt(Seconds / 10.0) * 10);
		return S >= 60 ? FString::Printf(TEXT("%d min %02d s"), S / 60, S % 60) : FString::Printf(TEXT("%d s"), FMath::Max(S, 10));
	}
	const double LaneEntryKm = 25.0;    // the gate's approach lane opens this far off the ring
	const float LaneRingStepM = 2500.f; // the lane's markers, every 2.5 km out to 22.5 km
	FAutoConsoleCommand CmdBattleKill(TEXT("astra.battle.kill"), TEXT("Destroy a contact at once (testing effects): astra.battle.kill <contact id>"),
		FConsoleCommandWithArgsDelegate::CreateLambda([](const TArray<FString>& A) { if (A.Num()) { GKillRequests.Add(A[0].ToUpper()); } }));
	FAutoConsoleCommand CmdBattleSpawn(TEXT("astra.battle.spawn"),
		TEXT("Spawn a hostile ship for testing: astra.battle.spawn <styx|lethe|acheron|harpies> <range_km> <bearing relative to the bow, deg> (harpies: a destroyer launching four strike fighters)"),
		FConsoleCommandWithArgsDelegate::CreateLambda([](const TArray<FString>& A)
		{
			if (A.Num() >= 3) { GSpawnRequests.Add({A[0].ToLower(), FCString::Atof(*A[1]), FCString::Atof(*A[2])}); }
		}));
	FAutoConsoleCommand CmdBattleTime(TEXT("astra.battle.time"), TEXT("Jump the scenario clock: astra.battle.time <seconds>"),
		FConsoleCommandWithArgsDelegate::CreateLambda([](const TArray<FString>& A) { if (A.Num()) { GBattleJumpTo = FCString::Atof(*A[0]); } }));
	FString GFaceRequest;
	bool GHomeRequest = false;
	FAutoConsoleCommand CmdFlyHome(TEXT("astra.fly.home"), TEXT("Testing: put the Captain's Falcon 300 m ahead of the Aquila's port tube, matching her speed"),
		FConsoleCommandDelegate::CreateLambda([]() { GHomeRequest = true; }));
	FAutoConsoleCommand CmdFlyFace(TEXT("astra.fly.face"), TEXT("Testing: turn the Captain's Falcon to face a contact: astra.fly.face <contact id|aquila>"),
		FConsoleCommandWithArgsDelegate::CreateLambda([](const TArray<FString>& A) { if (A.Num()) { GFaceRequest = A[0].ToUpper(); } }));
	FAutoConsoleCommand CmdBattleScale(TEXT("astra.battle.timescale"), TEXT("Battle simulation speed: astra.battle.timescale <x>"),
		FConsoleCommandWithArgsDelegate::CreateLambda([](const TArray<FString>& A) { if (A.Num()) { GBattleTimeScale = FMath::Clamp(FCString::Atof(*A[0]), 0.1f, 20.f); } }));
}

bool UAstraBattleSubsystem::ShouldCreateSubsystem(UObject* Outer) const
{
	const UWorld* World = Cast<UWorld>(Outer);
	return World && (World->WorldType == EWorldType::Game || World->WorldType == EWorldType::PIE);
}

// ------------------------------------------------------------------------------------------------------ setup
int32 UAstraBattleSubsystem::AddShip(const FString& Contact, const FString& Name, const FString& Class, const FString& Mesh,
                                     EAstraSide Side, const FVector& Pos, float HeadingDeg, float Speed, float Radius,
                                     float Hull, float Shield)
{
	FAstraBattleShip S;
	S.Id = NextId++;
	S.ContactId = Contact;
	S.Name = Name;
	S.Class = Class;
	S.Mesh = Mesh;
	S.Side = Side;
	S.Pos = Pos;
	S.Att = HeadingQuat(HeadingDeg, 0.0);
	S.Vel = S.Att.GetForwardVector() * Speed;
	S.CruiseSpeed = FMath::Max(Speed, 150.f);
	S.Radius = Radius;
	S.SizeTier = Radius >= 300.f ? 3 : (Radius >= 200.f ? 2 : (Radius >= 130.f ? 1 : 0));   // (a class table, where there is one, sets it at InitShipModel)
	S.Hull = S.HullMax = Hull;
	S.Shield = S.ShieldMax = Shield;
	S.Mode = Speed > 1.f ? EAstraShipMode::Cruise : EAstraShipMode::Idle;
	Ships.Add(S);
	IdIndex.Add(S.Id, Ships.Num() - 1);
	++PlotStamp;
	InitShipModel(Ships.Last());     // a warship gets its class's sections, plates, shield sectors and mounts (AstraWarDamage.cpp)
	return Ships.Num() - 1;
}

void UAstraBattleSubsystem::OnWorldBeginPlay(UWorld& InWorld)
{
	Super::OnWorldBeginPlay(InWorld);
	SphereMesh = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Sphere.Sphere"));
	CylinderMesh = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cylinder.Cylinder"));
	GlowMat = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/ASTRA/Materials/M_FX_Glow.M_FX_Glow"));
	FlareMat = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/ASTRA/Materials/M_FX_Flare.M_FX_Flare"));
	ShellMat = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/ASTRA/Materials/M_FX_Shell.M_FX_Shell"));
	RingMesh = LoadObject<UStaticMesh>(nullptr, TEXT("/Game/ASTRA/Holo/SM_HOLO_Ring.SM_HOLO_Ring"));
	BlastMat = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/ASTRA/Materials/M_FX_Blast.M_FX_Blast"));
	CubeMesh = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cube.Cube"));
	WarFX = NewObject<UAstraWarFX>(this);   // the war's visual effects (before any ship is drawn: SpawnVisual asks whether they draw the shields and the drives)
	WarFX->Init(this);
	WarDraw = NewObject<UAstraWarDraw>(this);   // the craft and the lamps as instances (SpawnVisual asks it to claim a ship)
	WarDraw->Init(this);

	// the Aquila first (index 0): the player's ship, heading 045 mark 10 like the helm
	const int32 P = AddShip(TEXT("AQUILA"), TEXT("ASN Aquila"), TEXT("Aquila-class carrier cruiser"), TEXT(""), EAstraSide::Astra,
	                        FVector::ZeroVector, 45.f, 288.f, 330.f, 3000.f, 1100.f);
	Ships[P].bPlayer = true;
	Ships[P].RailCd = 7.f;
	Ships[P].RailSlugs = 4;              // four twin turrets
	Ships[P].RailRange = 10000.f;
	Ships[P].RailDamage = 55.f;
	Ships[P].MissileCd = 14.f;           // VLS cycle between salvos
	Ships[P].MissileT = 0.f;
	Ships[P].Missiles = 96;
	Ships[P].PDChannels = 4;             // 24 point-defence mounts
	Ships[P].Att = HeadingQuat(45.0, 0.0);

	const FVector A0 = FVector::ZeroVector;
	// the picket: the flagship battleship is the strongest ship on the field (six triple turrets); with its destroyer it
	// can trade blows with the Mandate strike group, but the fight is won only if the Aquila joins in
	int32 I = AddShip(TEXT("T-01"), TEXT("ASN Praetorian"), TEXT("ASTRA battleship (7th Fleet flagship)"), TEXT("SM_SHIP_ASTRA_Praetorian"),
	                  EAstraSide::Astra, A0 + Polar(4.5 * OneKm, 25, 3), 45.f, 288.f, 460.f, 5200.f, 2000.f);
	BattleshipStats(Ships[I]);
	const int32 PicketBB = I;
	I = AddShip(TEXT("T-02"), TEXT("ASN Vigilant"), TEXT("ASTRA destroyer"), TEXT("SM_SHIP_ASTRA_Vigilant"), EAstraSide::Astra,
	            A0 + Polar(3 * OneKm, 70, 2), 45.f, 288.f, 140.f, 1200.f, 500.f);
	DestroyerStats(Ships[I]);
	const int32 PicketDD = I;
	I = AddShip(TEXT("T-07"), TEXT("Brightwater"), TEXT("Free Guilds freighter"), TEXT("SM_SHIP_GUILD_Freighter"), EAstraSide::Neutral,
	            A0 + Polar(22 * OneKm, 15, 4), 120.f, 180.f, 170.f, 700.f, 60.f);
	Ships[I].RailDamage = 0.f;
	Ships[I].Missiles = 0;
	I = AddShip(TEXT("T-11"), TEXT("Lethe"), TEXT("Kharon Mandate frigate, Lethe class"), TEXT("SM_SHIP_MANDATE_Lethe"), EAstraSide::Mandate,
	            A0 + Polar(30 * OneKm, 200, -3), 30.f, 0.f, 90.f, 520.f, 220.f);
	Ships[I].bCold = true;
	Ships[I].bIdentified = false;
	Ships[I].Missiles = 8;
	// the 7th Fleet's picket screens the Aquila (its battle group: they fight where she can support them)
	NoteGroupSpawn(EAstraSide::Astra, TEXT("7th Fleet picket"), TEXT("screen"), TArray<int32>({PicketBB, PicketDD}), Ships[0].Id);

	// the Aquila's flight groups (Flight Control): fighters, torpedo bombers, drones
	auto Group = [this](const TCHAR* Name, const TCHAR* Call, const TCHAR* Mesh, int32 Kind, int32 Count)
	{
		FAstraSquadron Q;
		Q.Name = Name;
		Q.CallSign = Call;
		Q.Mesh = Mesh;
		Q.Kind = Kind;
		Q.Total = Q.OnDeck = Count;
		Q.CarrierId = Ships[0].Id;
		Squadrons.Add(Q);
	};
	Group(TEXT("alpha"), TEXT("Falcon"), TEXT("SM_CRAFT_ASTRA_Falcon"), 0, 8);
	Group(TEXT("bravo"), TEXT("Hammer"), TEXT("SM_CRAFT_ASTRA_Hammer"), 1, 7);
	Group(TEXT("drones"), TEXT("Wasp"), TEXT("SM_CRAFT_ASTRA_Wasp"), 2, 12);

	for (FAstraBattleShip& S : Ships)
	{
		if (!S.bPlayer)
		{
			SpawnVisual(S);
		}
	}
	// Janus Gate Aurelia: 110 km out on bearing 070 (where the Mandate comes from), its ring facing us
	{
		const FVector GPos = Ships[0].Pos + Polar(110 * OneKm, 70, 3);
		SpawnGate(GPos, FRotationMatrix::MakeFromX((Ships[0].Pos - GPos).GetSafeNormal()).ToQuat() * FQuat(FVector::XAxisVector, 0.3f));
	}
	SyncVisuals();
	UE_LOG(LogASTRA, Log, TEXT("[Battle] scenario 'Aurelia patrol' ready: %d ships"), Ships.Num());
}

void UAstraBattleSubsystem::SpawnVisual(FAstraBattleShip& S)
{
	if (WarDraw && WarDraw->Claim(S))
	{
		return;                           // a craft the war draws as an instance of its kind of hull (AstraWarDraw.cpp): no actor, no components, no ticks
	}
	if (!FApp::CanEverRender())
	{
		return;                           // headless (the war bench, -nullrhi): the battle runs without its pictures
	}
	UWorld* World = GetWorld();
	UStaticMesh* Mesh = LoadObject<UStaticMesh>(nullptr, *FString::Printf(TEXT("/Game/ASTRA/Ships/%s.%s"), *S.Mesh, *S.Mesh));
	if (!World || !Mesh)
	{
		return;
	}
	FActorSpawnParameters P;
	P.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	S.Actor = World->SpawnActor<AStaticMeshActor>(FVector::ZeroVector, FRotator::ZeroRotator, P);
	S.Actor->SetMobility(EComponentMobility::Movable);
	UStaticMeshComponent* C = S.Actor->GetStaticMeshComponent();
	C->SetStaticMesh(Mesh);
	C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	C->SetCastShadow(false);          // km-scale shadows are invisible and cost VSM pages
	C->bAffectDynamicIndirectLighting = false;
	C->SetLightingChannels(true, true, false);   // outside the hull: the planet's light reaches it too
	if (!S.bDrawLamps)                  // (the war draws a ship's lamps itself: instances of its glow, no component and no tick)
	{
		UAstraNavLights* NL = NewObject<UAstraNavLights>(S.Actor);
		NL->SetupAttachment(S.Actor->GetRootComponent());
		NL->RegisterComponent();
		NL->Setup(S.Mesh, S.Side == EAstraSide::Mandate);
	}
	if (S.Side == EAstraSide::Astra && !S.bCraft && !S.bDerelict && !S.Name.IsEmpty())
	{
		// her name on both flanks, and a hull number of her class (the same name always has the same number)
		const bool bBattleship = S.Mesh.Contains(TEXT("Praetorian"));
		const uint32 H = FCrc::StrCrc32(*S.Name);
		UAstraHullName::Paint(S.Actor, S.Name, FString::Printf(TEXT("%s-%02d"), bBattleship ? TEXT("BB") : TEXT("DD"),
		                                                      bBattleship ? 2 + H % 9 : 10 + H % 80));
	}
	if (SphereMesh && ShellMat && !S.bCraft && !FxOn())
	{
		S.ShieldBubble = World->SpawnActor<AStaticMeshActor>(FVector::ZeroVector, FRotator::ZeroRotator, P);
		S.ShieldBubble->SetMobility(EComponentMobility::Movable);
		UStaticMeshComponent* B = S.ShieldBubble->GetStaticMeshComponent();
		B->SetStaticMesh(SphereMesh);
		B->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		B->SetCastShadow(false);
		S.ShieldMID = B->CreateAndSetMaterialInstanceDynamicFromMaterial(0, ShellMat);
		S.ShieldMID->SetVectorParameterValue(TEXT("Color"), S.Side == EAstraSide::Mandate ? MandateShield : AstraShield);
		S.ShieldMID->SetScalarParameterValue(TEXT("Fade"), 0.f);
		// the engine sphere is 100 cm across: scale to an ellipsoid around the hull
		const float R = S.Radius * 100.f / 50.f;
		S.ShieldBubble->SetActorScale3D(FVector(R * 1.25f, R * 0.45f, R * 0.4f));
		S.ShieldBubble->SetActorHiddenInGame(true);
	}
	if (SphereMesh && GlowMat && !FxOn())
	{
		S.DriveFlare = World->SpawnActor<AStaticMeshActor>(FVector::ZeroVector, FRotator::ZeroRotator, P);
		S.DriveFlare->SetMobility(EComponentMobility::Movable);
		UStaticMeshComponent* D = S.DriveFlare->GetStaticMeshComponent();
		D->SetStaticMesh(SphereMesh);
		D->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		D->SetCastShadow(false);
		UMaterialInstanceDynamic* M = D->CreateAndSetMaterialInstanceDynamicFromMaterial(0, FlareMat ? FlareMat.Get() : GlowMat.Get());
		M->SetVectorParameterValue(TEXT("Color"), S.Side == EAstraSide::Mandate ? FLinearColor(1.f, 0.45f, 0.3f)
		                                        : (S.Side == EAstraSide::Astra ? FLinearColor(0.55f, 0.78f, 1.f) : FLinearColor(0.9f, 0.9f, 1.f)));
		M->SetScalarParameterValue(TEXT("Intensity"), 60.f);
	}
}

// ------------------------------------------------------------------------------------------------------ frames
FVector UAstraBattleSubsystem::ToWorld(const FVector& SystemPos) const
{
	const FAstraBattleShip& P = Ships[0];
	const FVector Local = P.Att.UnrotateVector(SystemPos - P.Pos) - BridgeOffset;
	return Local * 100.0;
}

FQuat UAstraBattleSubsystem::ToWorldRot(const FQuat& SystemRot) const
{
	return Ships[0].Att.Inverse() * SystemRot;
}

double UAstraBattleSubsystem::BearingDeg(const FVector& From, const FVector& To) const
{
	const FVector D = To - From;
	return FMath::Fmod(FMath::RadiansToDegrees(FMath::Atan2(D.Y, D.X)) + 360.0, 360.0);
}

double UAstraBattleSubsystem::MarkDeg(const FVector& From, const FVector& To) const
{
	const FVector D = To - From;
	return FMath::RadiansToDegrees(FMath::Atan2(D.Z, FVector2D(D.X, D.Y).Size()));
}

FString UAstraBattleSubsystem::SideName(EAstraSide S) const
{
	return S == EAstraSide::Astra ? TEXT("friendly") : (S == EAstraSide::Mandate ? TEXT("hostile") : TEXT("neutral"));
}

FAstraBattleShip* UAstraBattleSubsystem::FindByContact(const FString& Contact)
{
	return Ships.FindByPredicate([&](const FAstraBattleShip& S) { return S.ContactId.Equals(Contact, ESearchCase::IgnoreCase); });
}

FAstraBattleShip* UAstraBattleSubsystem::FindById(int32 Id)
{
	const int32* I = IdIndex.Find(Id);
	return (I && Ships.IsValidIndex(*I) && Ships[*I].Id == Id) ? &Ships[*I] : nullptr;
}

void UAstraBattleSubsystem::Report(const FString& Text, bool bReport)
{
	UE_LOG(LogASTRA, Log, TEXT("[Battle] %s"), *Text);
	if (UAstraShipSubsystem* Ship = GetWorld()->GetSubsystem<UAstraShipSubsystem>())
	{
		Ship->PublishEvent(Text, bReport);
	}
}

// ------------------------------------------------------------------------------------------------------ tick
void UAstraBattleSubsystem::Tick(float DeltaTime)
{
	if (Ships.Num() == 0 || bFrozen)
	{
		return;
	}
	if (!bStarted)
	{
		SyncVisuals();   // the plot stays drawn behind the menu
		TickWrecks(0.f);
		if (WarDraw)
		{
			SCOPE_CYCLE_COUNTER(STAT_AstraWarDraw);
			WarDraw->Tick(DeltaTime);
		}
		if (WarFX)
		{
			SCOPE_CYCLE_COUNTER(STAT_AstraWarFx);
			WarFX->Tick(DeltaTime);
		}
		return;
	}
	SCOPE_CYCLE_COUNTER(STAT_AstraBattle);
	const double PerfT0 = FPlatformTime::Seconds();
	const float Dt = FMath::Min(DeltaTime, 0.1f) * GBattleTimeScale;
	struct FTickTimer
	{
		FAstraWarStats& S;
		double T0 = FPlatformTime::Seconds();
		explicit FTickTimer(FAstraWarStats& InS) : S(InS) {}
		~FTickTimer() { S.NoteTick((FPlatformTime::Seconds() - T0) * 1000.0); }
	} TickTimer(Stats);
	for (double& Ph : Stats.PhaseNow)
	{
		Ph = 0.0;
	}
	Time += Dt;
	if (Time - Stats.WinStart >= 10.f)
	{
		Stats.CloseWindow(0);
		Stats.CloseWindow(1);
		Stats.WinStart = Time;
	}
	{
		int32 Cap = 0, Craft = 0;
		for (const FAstraBattleShip& S : Ships)
		{
			Cap += (S.bAlive && !S.bCraft) ? 1 : 0;
			Craft += (S.bAlive && S.bCraft) ? 1 : 0;
		}
		Stats.PeakShips = FMath::Max(Stats.PeakShips, Cap);
		Stats.PeakCraft = FMath::Max(Stats.PeakCraft, Craft);
		Stats.PeakProjectiles = FMath::Max(Stats.PeakProjectiles, Projectiles.Num());
	}
	TickDetection(Dt);
	TickSensors(Dt);
	if (GBattleJumpTo >= 0.f)
	{
		Time = GBattleJumpTo;
		GBattleJumpTo = -1.f;
	}
	for (const FSpawnRequest& R : GSpawnRequests)
	{
		const FRotator Bow = Ships[0].Att.Rotator();
		const FVector Pos = Ships[0].Pos + Polar(R.RangeKm * OneKm, Bow.Yaw + R.RelBearing, Bow.Pitch + 2.0);
		const bool bBig = R.Kind == TEXT("acheron");
		const FString Mesh = bBig ? TEXT("SM_SHIP_MANDATE_Acheron") : (R.Kind == TEXT("lethe") ? TEXT("SM_SHIP_MANDATE_Lethe") : TEXT("SM_SHIP_MANDATE_Styx"));
		// broadside to us: its heading is perpendicular to our line of sight
		const int32 I = AddShip(FString::Printf(TEXT("T-%d"), 30 + NextId), TEXT("Test contact"), TEXT("Kharon Mandate warship (test)"), Mesh,
		                        EAstraSide::Mandate, Pos, Bow.Yaw + R.RelBearing + 90.f, 200.f, bBig ? 240.f : 130.f, bBig ? 2200.f : 950.f, 380.f);
		Ships[I].bHostile = true;
		Ships[I].Mode = EAstraShipMode::Attack;
		Ships[I].TargetId = Ships[0].Id;
		SpawnVisual(Ships[I]);
		if (R.Kind == TEXT("harpies"))
		{
			AddEnemyWing(I, 4, 1.f);   // testing: a carrier that launches strike fighters at once
		}
	}
	GSpawnRequests.Reset();
	for (const FString& K : GKillRequests)
	{
		if (FAstraBattleShip* S = FindByContact(K); S && S->bAlive)
		{
			Destroy(*S);
		}
	}
	GKillRequests.Reset();
	for (const TArray<FString>& A : GTransitRequests)
	{
		TSharedPtr<FJsonObject> B = MakeShared<FJsonObject>();
		B->SetStringField(TEXT("system_name"), A[0].Replace(TEXT("_"), TEXT(" ")));
		B->SetStringField(TEXT("star_class"), A.IsValidIndex(1) ? A[1] : FString());
		B->SetStringField(TEXT("planet_type"), A.IsValidIndex(2) ? A[2] : FString());
		B->SetStringField(TEXT("planet_name"), A.IsValidIndex(3) ? A[3].Replace(TEXT("_"), TEXT(" ")) : FString());
		FString Detail;
		BeginGateRun(B, Detail);
		UE_LOG(LogASTRA, Log, TEXT("[Battle] transit request: %s"), *Detail);
	}
	GTransitRequests.Reset();
	for (const TArray<FString>& A : GArriveRequests)
	{
		TSharedPtr<FJsonObject> B = MakeShared<FJsonObject>();
		B->SetStringField(TEXT("system_name"), A[0].Replace(TEXT("_"), TEXT(" ")));
		B->SetStringField(TEXT("star_class"), A.IsValidIndex(1) ? A[1] : FString());
		B->SetStringField(TEXT("planet_type"), A.IsValidIndex(2) ? A[2] : FString());
		B->SetStringField(TEXT("planet_name"), A.IsValidIndex(3) ? A[3].Replace(TEXT("_"), TEXT(" ")) : FString());
		DoTransit(B);
	}
	GArriveRequests.Reset();
	if (GStatusRequest)
	{
		GStatusRequest = false;
		for (const FAstraBattleShip& S : Ships)
		{
			if (!S.bCraft)
			{
				const FAstraBattleShip* T = FindById(S.TargetId);
				UE_LOG(LogASTRA, Log, TEXT("[Status] t=%.0f %s %-12s %s hull %4.0f/%4.0f shield %4.0f/%4.0f target %s range %.1f km mode %d "
				                           "from us %03.0f/%.1f km%s%s%s%s"), Time,
				       *S.ContactId, *S.Name, S.bAlive ? TEXT("alive") : TEXT("DEAD "), S.Hull, S.HullMax, S.Shield, S.ShieldMax,
				       T ? *T->ContactId : TEXT("-"), T ? FVector::Dist(S.Pos, T->Pos) / OneKm : 0.0, (int32)S.Mode,
				       BearingDeg(Ships[0].Pos, S.Pos), FVector::Dist(Ships[0].Pos, S.Pos) / OneKm,
				       S.bFog ? *FString::Printf(TEXT(" track %d"), S.Track) : TEXT(""), S.bJamming ? TEXT(" JAM") : TEXT(""),
				       S.bHoldFire ? TEXT(" HOLD") : TEXT(""), S.bFleeing ? TEXT(" FLEE") : TEXT(""));
			}
		}
	}
	if (GGateJump && Landmarks.IsValidIndex(GateLandmark))
	{
		GGateJump = false;
		const FAstraWreck& G = Landmarks[GateLandmark];
		const FVector Axis = G.Att.GetForwardVector();
		const float Side = FVector::DotProduct(Ships[0].Pos - G.Pos, Axis) >= 0.0 ? 1.f : -1.f;
		Ships[0].Pos = G.Pos + Axis * Side * 30 * OneKm;
		const FVector Dir = -Axis * Side;
		if (UAstraShipSubsystem* Ship = GetWorld()->GetSubsystem<UAstraShipSubsystem>())
		{
			Ship->DriveExternally(FMath::RadiansToDegrees(FMath::Atan2(Dir.Y, Dir.X)),
			                      FMath::RadiansToDegrees(FMath::Atan2(Dir.Z, FVector2D(Dir.X, Dir.Y).Size())), Ship->GetSpeedMps());
		}
	}
	ProcessWarCommands();                                   // the bench's scenarios and spawns (AstraWarScenario.cpp)
	TickScenarioWaves();                                    // the reinforcements of a scenario file arrive when their time comes
	// the war's minds: what each side holds on its sensors, who is near whom, what the groups want
	if ((CompactT -= Dt) <= 0.f)
	{
		CompactT = 10.f;
		CompactShips();
	}
	double PhaseMark = FPlatformTime::Seconds();
	auto EndPhase = [this, &PhaseMark](int32 P)
	{
		const double Now = FPlatformTime::Seconds();
		Stats.PhaseNow[P] += (Now - PhaseMark) * 1000.0;
		PhaseMark = Now;
	};
	BuildGrid();
	if ((KnowledgeT -= Dt) <= 0.f)
	{
		KnowledgeT = 0.25f;
		TickKnowledge();
	}
	EndPhase(0);
	TickGroups(Dt);
	EndPhase(1);
	TickPlayer(Dt);
	TickGateRun(Dt);
	TickPOIs(Dt);
	TickScenario(Dt);
	TickSquadrons(Dt);
	TickEagleWing(Dt);
	EndPhase(2);
	for (FAstraBattleShip& S : Ships)
	{
		S.bJammed = false;   // EW drones set it again this tick
	}
	for (FAstraBattleShip& S : Ships)
	{
		if (!S.bAlive)
		{
			S.DeadT += S.bCraft ? Dt : 0.f;
			continue;
		}
		if (S.bPiloted)
		{
			TickPiloted(S, Dt);
			continue;
		}
		if (S.bCraft)
		{
			const double C0 = FPlatformTime::Seconds();
			TickCraft(S, Dt);
			Stats.PhaseNow[4] += (FPlatformTime::Seconds() - C0) * 1000.0;
			continue;
		}
		const double Sh0 = FPlatformTime::Seconds();
		if (!S.bPlayer)
		{
			TickAI(S, Dt);
		}
		TickWeapons(S, Dt);
		if (S.Dmg.bModel)
		{
			TickDamageState(S, Dt);                // sectors regenerate and move, sections burn, hulls break, systems fail
		}
		else if (S.bShieldsUp)
		{
			const float Before = S.Shield;
			S.Shield = FMath::Min(S.ShieldMax, S.Shield + S.ShieldRegen * S.ShieldPower * Dt);
			if (S.bPlayer && S.Shield > Before)
			{
				if (UAstraShipSubsystem* Ship = GetWorld()->GetSubsystem<UAstraShipSubsystem>())
				{
					Ship->AddHeat((S.Shield - Before) * 0.06f);   // the emitters recharging run hot
				}
			}
		}
		S.ShieldFlash = FMath::Max(0.f, S.ShieldFlash - Dt * 2.5f);
		Stats.PhaseNow[3] += (FPlatformTime::Seconds() - Sh0) * 1000.0;
	}
	PhaseMark = FPlatformTime::Seconds();
	TickProjectiles(Dt);
	TickFlashes(Dt);
	DecoyT = FMath::Max(0.f, DecoyT - Dt);
	TickScars(Dt);
	if (DecoysSeduced > 0 && Time - LastDecoyReport > 6.f)
	{
		Report(FString::Printf(TEXT("tactical: the decoys drew off %d missile%s"), DecoysSeduced, DecoysSeduced > 1 ? TEXT("s") : TEXT("")));
		DecoysSeduced = 0;
		LastDecoyReport = Time;
	}
	const double PerfT1 = FPlatformTime::Seconds();
	SyncVisuals();
	const double PerfT2 = FPlatformTime::Seconds();
	if (WarDraw)
	{
		SCOPE_CYCLE_COUNTER(STAT_AstraWarDraw);
		WarDraw->Tick(DeltaTime);                  // the craft's hulls and every ship's lamps, as instances (AstraWarDraw.cpp)
	}
	const double PerfT3 = FPlatformTime::Seconds();
	if (WarFX)
	{
		SCOPE_CYCLE_COUNTER(STAT_AstraWarFx);
		WarFX->Tick(DeltaTime);                    // the war's effects: shots, particles, shields, drives (AstraWarFX.cpp)
	}
	EndPhase(5);
	++PlotStamp;                                   // the plot has moved: the shared lists (Contacts, HoloBlips) are made again for whoever reads them next
	const double PerfT4 = FPlatformTime::Seconds();
	PerfWin.Sim += (PerfT1 - PerfT0) * 1000.0;
	PerfWin.Sync += (PerfT2 - PerfT1) * 1000.0;
	PerfWin.Draw += (PerfT3 - PerfT2) * 1000.0;
	PerfWin.Fx += (PerfT4 - PerfT3) * 1000.0;
	PerfWin.Total += (PerfT4 - PerfT0) * 1000.0;
	PerfWin.TotalMax = FMath::Max(PerfWin.TotalMax, (PerfT4 - PerfT0) * 1000.0);
	++PerfWin.Frames;
}

FString UAstraBattleSubsystem::PerfReport(bool bReset)
{
	const FPerfWindow W = PerfWin;
	if (bReset)
	{
		PerfWin = FPerfWindow();
	}
	const double N = FMath::Max(1, W.Frames);
	return FString::Printf(TEXT("battle tick over %d frames: %.3f ms avg (max %.2f) = simulation %.3f + moving the hulls %.3f + instanced drawing %.3f + effects %.3f"), W.Frames,
	                       W.Total / N, W.TotalMax, W.Sim / N, W.Sync / N, W.Draw / N, W.Fx / N);
}

void UAstraBattleSubsystem::StartCampaign()
{
	bStarted = true;
	if (WarDraw)
	{
		WarDraw->Prewarm();                        // the craft's kinds of hull ready before the first wing launches
	}
}

void UAstraBattleSubsystem::SetLensHint(bool bActive, double WithinKm, int32 ExemptId)
{
	if (WarDraw)
	{
		WarDraw->SetLensHint(bActive, WithinKm, ExemptId);
	}
}

void UAstraBattleSubsystem::GetNearLensComponents(TArray<UPrimitiveComponent*>& Out) const
{
	if (WarDraw)
	{
		WarDraw->GetNearLensComponents(Out);
	}
}

FString UAstraBattleSubsystem::DrawStats() const
{
	FString S;
	if (WarDraw)
	{
		WarDraw->Stats(S);
	}
	return S;
}

TSharedRef<FJsonObject> UAstraBattleSubsystem::DrawStatsJson() const
{
	return WarDraw ? WarDraw->StatsJson() : MakeShared<FJsonObject>();
}

float UAstraBattleSubsystem::PlayerSignatureKm() const
{
	const UAstraShipSubsystem* Ship = GetWorld() ? GetWorld()->GetSubsystem<UAstraShipSubsystem>() : nullptr;
	if (!Ship)
	{
		return 30.f;
	}
	const FString E = Ship->GetEmcon();
	float Km = E == TEXT("silent") ? 12.f : (E == TEXT("full") ? 60.f : 30.f);
	Km *= 0.55f + 0.45f * FMath::Max(0.f, Ship->GetThrottlePct()) / 100.f;                 // the drive's plume (backing off, it idles)
	Km *= 1.f + Ship->SignatureBoost() + 0.4f * FMath::Max(0.f, Ship->GetHeatPct() - 50.f) / 50.f;   // hot panels, a vent, a hot hull
	return Km;
}

void UAstraBattleSubsystem::TickDetection(float Dt)
{
	if (bSandbox)
	{
		return;
	}
	PlayerSinceFired += Dt;
	const FAstraBattleShip& P = Ships[0];
	const float SigKm = PlayerSignatureKm();
	bool bSeen = PlayerSinceFired < 45.f;
	bool bHostiles = false;
	for (const FAstraBattleShip& O : Ships)
	{
		if (O.bAlive && O.bHostile && !O.bDisabled && O.Side == EAstraSide::Mandate && !O.bCraft && !O.bCold)
		{
			bHostiles = true;
			bSeen = bSeen || FVector::Dist(O.Pos, P.Pos) < SigKm * OneKm;
		}
	}
	if (bSeen)
	{
		PlayerTrackT = 60.f;
		PlayerLastKnown = P.Pos;
	}
	else
	{
		PlayerTrackT = FMath::Max(0.f, PlayerTrackT - Dt);
	}
	if (!bHostiles)
	{
		bPlayerEverTracked = false;   // a new fight starts with a clean slate
	}
	const bool bNow = PlayerTrackT > 0.f || !bHostiles;   // no hostile out there: nothing to hide from
	if (bNow != bPlayerTracked)
	{
		bPlayerTracked = bNow;
		if (bHostiles && bNow)
		{
			Report(FString::Printf(TEXT("sensors: the Mandate has found us — a firm track (our signature reaches about %.0f km)"), SigKm));
		}
		else if (bHostiles)
		{
			Report(bPlayerEverTracked
				? FString::Printf(TEXT("sensors: the Mandate has lost our track — they are sweeping our last known position (our signature now "
				                       "about %.0f km)"), SigKm)
				: FString::Printf(TEXT("sensors: the Mandate ships have not found us: we are outside their sensors (our signature about %.0f km)"), SigKm));
		}
	}
	bPlayerEverTracked = bPlayerEverTracked || (bHostiles && bNow);
}

float UAstraBattleSubsystem::SignatureKmOf(const FAstraBattleShip& S) const
{
	// what a Mandate ship gives off (drive plume, reactor, emissions): a cruiser shows further than a frigate; running
	// dark cuts it to a third; the drive at speed shows more
	const float Base = S.bCraft ? 7.f : (S.SizeTier >= 3 ? 48.f : (S.SizeTier >= 2 ? 36.f : 27.f));
	const float Speed = FMath::Clamp(S.Vel.Size() / FMath::Max(S.CruiseSpeed, 1.f), 0.f, 1.5f);
	return Base * (S.bDark ? 0.33f : 1.f) * (0.6f + 0.4f * Speed);
}

FString UAstraBattleSubsystem::KnownLabel(const FAstraBattleShip& S) const
{
	if (!S.bFog || S.bIdentified)
	{
		return FString::Printf(TEXT("%s (%s)"), *S.Name, *S.ContactId);
	}
	return S.bClassified ? FString::Printf(TEXT("a %s (%s)"), *S.Class, *S.ContactId) : S.ContactId;
}

void UAstraBattleSubsystem::TickSensors(float Dt)
{
	if (Ships.Num() == 0 || !Ships[0].bAlive)
	{
		return;
	}
	const UAstraShipSubsystem* Ship = GetWorld()->GetSubsystem<UAstraShipSubsystem>();
	const FString E = Ship ? Ship->GetEmcon() : FString(TEXT("restricted"));
	const float SensorPower = Ship ? FMath::Clamp(Ship->PowerFactor(TEXT("sensors")), 0.2f, 1.5f) : 1.f;
	// the Aquila's active sensors (radar, lidar): full EMCON sees furthest; silent only listens
	const float ActiveKm = (E == TEXT("full") ? 55.f : (E == TEXT("restricted") ? 28.f : 0.f)) * SensorPower * SensorFactor(Ships[0]);   // (a hurt sensor suite sees less far)
	const FAstraBattleShip& P = Ships[0];
	TArray<FString> NewBearings, NewTracks, Classified, Lost, JamOn, BurnThrough, Unmasked, Faded;
	// the Mandate's jammers: a capital ship that has stopped running dark (it came close, fired, or heard our ping and
	// knows it has been found) floods our radar along its bearing; inside 12 km the returns burn through the noise
	TArray<FVector> JamDirs;
	for (FAstraBattleShip& S : Ships)
	{
		if (!S.bFog || !S.bAlive || S.bPlayer || S.bGhost)
		{
			continue;
		}
		const float R = FVector::Dist(S.Pos, P.Pos) / OneKm;
		// their warning receivers hear a radar painting them: ours, or a fleet ship's inside 30 km
		S.bIlluminated = R < ActiveKm;
		for (const FAstraBattleShip& A : Ships)
		{
			if (!S.bIlluminated && A.bAlive && !A.bPlayer && !A.bCraft && !A.bDerelict && A.Side == EAstraSide::Astra)
			{
				S.bIlluminated = FVector::Dist(A.Pos, S.Pos) < 30.f * OneKm;
			}
		}
		// the commander's EW orders: jam now, or stay quiet (no jamming; back to dark when not fighting close)
		if (S.EwMode == 2 && !S.bDark && S.LitT <= 0.f && R > 20.f && !S.bFleeing)
		{
			S.bDark = true;
		}
		const bool bWantJam = S.EwMode == 1 || (S.EwMode == 0 && !S.bDark);
		const bool bJam = S.SizeTier >= 2 && S.bHostile && bWantJam && !S.bFleeing && !S.bHoldFire && R > 12.f && R < 55.f;
		if (bJam)
		{
			S.bDark = false;                           // a jammer is anything but dark
		}
		if (bJam && !S.bJamming)
		{
			JamOn.Add(FString::Printf(TEXT("%s on bearing %03.0f"), *KnownLabel(S), BearingDeg(P.Pos, S.Pos)));
		}
		else if (!bJam && S.bJamming && R <= 12.f)
		{
			BurnThrough.Add(KnownLabel(S));
		}
		S.bJamming = bJam;
		if (bJam)
		{
			JamDirs.Add((S.Pos - P.Pos).GetSafeNormal());
		}
	}
	auto Jammed = [&JamDirs](const FVector& From, const FVector& To) -> bool
	{
		const FVector D = (To - From).GetSafeNormal();
		for (const FVector& J : JamDirs)
		{
			if (FVector::DotProduct(D, J) > 0.9f)      // within about 25 degrees of a jammer's bearing
			{
				return true;
			}
		}
		return false;
	};
	for (FAstraBattleShip& S : Ships)
	{
		if (!S.bFog || !S.bAlive || S.bPlayer)
		{
			continue;
		}
		if (S.bGhost)
		{
			// a decoy gives a loud bearing and nothing else: the first radar return (ours inside our active range, the
			// fleet's inside theirs, jammed or not), or a flight group near it, shows a return far too small for that
			// drive — a drone. Its battery dies after a few minutes: the bearing fades like any other
			const float R = FVector::Dist(S.Pos, P.Pos) / OneKm;
			bool bUnmask = R < ActiveKm * (Jammed(P.Pos, S.Pos) ? 0.45f : 1.f);
			for (const FAstraBattleShip& A : Ships)
			{
				if (bUnmask)
				{
					break;
				}
				if (A.bAlive && !A.bPlayer && !A.bDerelict && A.Side == EAstraSide::Astra)
				{
					const float RA = FVector::Dist(A.Pos, S.Pos) / OneKm;
					bUnmask = A.bCraft ? RA < 10.f : RA < 30.f * (Jammed(A.Pos, S.Pos) ? 0.45f : 1.f);
				}
			}
			const uint8 OldTrack = S.Track;
			if (bUnmask)
			{
				if (OldTrack > 0)
				{
					Unmasked.Add(FString::Printf(TEXT("%s (bearing %03.0f)"), *S.ContactId, BearingDeg(P.Pos, S.Pos)));
				}
				S.bAlive = false;
				continue;
			}
			S.Track = (R < 85.f && S.GhostLife > 0.f) ? 1 : 0;
			if (OldTrack == 0 && S.Track == 1)
			{
				NewBearings.Add(FString::Printf(TEXT("%s bearing %03.0f"), *S.ContactId, BearingDeg(P.Pos, S.Pos)));
			}
			else if (OldTrack == 1 && S.Track == 0)
			{
				Faded.Add(S.ContactId);
			}
			if (S.GhostLife <= 0.f)
			{
				S.bAlive = false;
			}
			continue;
		}
		S.LitT = FMath::Max(0.f, S.LitT - Dt);
		// running dark until close, until it fights, until it runs
		if (S.bDark && (FVector::Dist(S.Pos, P.Pos) < 20.f * OneKm || S.LitT > 0.f || S.bFleeing))
		{
			S.bDark = false;
		}
		const float Sig = SignatureKmOf(S);
		auto Sense = [&S, Sig, this](const FVector& From, float Active, bool bRecon) -> uint8
		{
			const float R = FVector::Dist(From, S.Pos) / OneKm;
			uint8 K = 0;
			if (R < Active * 0.35f) { K = 4; }            // close enough to read its hull: identified
			else if (R < Active * 0.7f) { K = 3; }        // classified
			else if (R < Active) { K = 2; }               // a firm track
			if (R < Sig * 0.7f) { K = FMath::Max<uint8>(K, 2); }   // loud and near: passive gives a track too
			else if (R < Sig * 1.7f) { K = FMath::Max<uint8>(K, 1); }   // a bearing from its emissions
			if (S.LitT > 0.f && R < 90.f) { K = FMath::Max<uint8>(K, 2); }   // it fired: everyone saw it
			if (bRecon && R < 8.f) { K = 4; }             // eyes on it: a flight group reads its name off the hull
			return K;
		};
		uint8 Best = Sense(P.Pos, ActiveKm * (Jammed(P.Pos, S.Pos) ? 0.45f : 1.f), false);
		for (const FAstraBattleShip& A : Ships)
		{
			// the 7th Fleet's ships and our flight groups share their tracks by datalink (jammed like ours)
			if (A.bAlive && !A.bPlayer && !A.bDerelict && A.Side == EAstraSide::Astra)
			{
				Best = FMath::Max(Best, Sense(A.Pos, (A.bCraft ? 10.f : 30.f) * (Jammed(A.Pos, S.Pos) ? 0.45f : 1.f), A.bCraft));
			}
		}
		bool bCrossFix = false;
		if (S.bJamming)
		{
			// the jammer gives its own bearing away (the strobe) but hides its range until burn-through. Two strobe
			// bearings from far enough apart (a fleet ship, a flight group out on the flank) cross at its range: a
			// track, not a classification; eyes on it (a flight group inside 8 km) still read its hull
			uint8 J = 1;
			const FVector FromUs = (S.Pos - P.Pos).GetSafeNormal();
			for (const FAstraBattleShip& A : Ships)
			{
				if (!A.bAlive || A.bPlayer || A.bDerelict || A.Side != EAstraSide::Astra)
				{
					continue;
				}
				if (A.bCraft && FVector::Dist(A.Pos, S.Pos) < 8.f * OneKm)
				{
					J = 4;
					break;
				}
				if (FVector::Dist(A.Pos, S.Pos) < 90.f * OneKm && FVector::DotProduct(FromUs, (S.Pos - A.Pos).GetSafeNormal()) < 0.99756f)
				{
					J = FMath::Max<uint8>(J, 2);              // the bearings cross at better than 4 degrees
					bCrossFix = J == 2;
				}
			}
			Best = S.LitT > 0.f ? FMath::Max<uint8>(J, 2) : J;
		}
		const uint8 OldTrack = S.Track;
		const bool bWasClassified = S.bClassified;
		if (Best >= 2)
		{
			S.Track = 2;
			S.TrackHold = 30.f;                          // a lost track lingers half a minute
		}
		else if (Best == 1 && S.Track <= 1)
		{
			S.Track = 1;
			S.TrackHold = 20.f;                          // a bearing lingers a little when the emissions dip
		}
		else if ((S.TrackHold -= Dt) <= 0.f)
		{
			S.Track = FMath::Max<uint8>(Best, S.Track == 2 ? 1 : Best);   // a firm track fades to a bearing, then to nothing
			S.TrackHold = S.Track == 1 && Best < 1 ? 30.f : 0.f;
		}
		else if (S.Track < Best)
		{
			S.Track = Best;
		}
		S.bClassified = S.bClassified || Best >= 3;
		if (Best >= 4 && !S.bIdentified)
		{
			S.bIdentified = true;
			Classified.Add(FString::Printf(TEXT("%s identified: %s"), *S.ContactId, *S.Name));
		}
		else if (S.bClassified && !bWasClassified)
		{
			Classified.Add(FString::Printf(TEXT("%s classified: %s"), *S.ContactId, *S.Class));
		}
		if (OldTrack == 0 && S.Track == 1)
		{
			NewBearings.Add(FString::Printf(TEXT("%s bearing %03.0f"), *S.ContactId, BearingDeg(P.Pos, S.Pos)));
		}
		else if (OldTrack < 2 && S.Track == 2)
		{
			NewTracks.Add(FString::Printf(TEXT("%s at %.0f km, bearing %03.0f%s"), *KnownLabel(S), FVector::Dist(P.Pos, S.Pos) / OneKm, BearingDeg(P.Pos, S.Pos),
			                              bCrossFix ? TEXT(" (a cross-fix on its jamming, with the fleet's bearing)") : TEXT("")));
		}
		else if (OldTrack == 2 && S.Track < 2)
		{
			Lost.Add(KnownLabel(S));
		}
		else if (OldTrack == 1 && S.Track == 0)
		{
			Faded.Add(S.ContactId);
		}
	}
	// the sensors officer's calls, grouped (a raid group lighting up is one call, not eight)
	if (NewBearings.Num())
	{
		Report(FString::Printf(TEXT("sensors: faint drive emissions — %s: passive bearing%s only, no range yet (an active scan, a recon flight or "
		                            "closing in would give a track)"), *FString::Join(NewBearings, TEXT("; ")), NewBearings.Num() > 1 ? TEXT("s") : TEXT("")));
	}
	if (NewTracks.Num())
	{
		Report(FString::Printf(TEXT("sensors: firm track%s — %s"), NewTracks.Num() > 1 ? TEXT("s") : TEXT(""), *FString::Join(NewTracks, TEXT("; "))));
	}
	if (Classified.Num())
	{
		Report(FString::Printf(TEXT("sensors: %s"), *FString::Join(Classified, TEXT("; "))));
	}
	if (Lost.Num())
	{
		Report(FString::Printf(TEXT("sensors: lost the track on %s — a bearing at most now"), *FString::Join(Lost, TEXT(", "))));
	}
	if (JamOn.Num())
	{
		// the receivers at the sensors station rasp as the jammers come on (heard on the bridge)
		if (Ship && Ship->CaptainPlace() == TEXT("BRIDGE"))
		{
			HullSound(TEXT("SW_Jam_Static"), 0.35f, 8.f);
		}
		Report(FString::Printf(TEXT("sensors: jamming — a strobe from %s: it floods our radar along that bearing (its range is hidden and our "
		                            "tracks there fade, the fleet's too). Missiles can home on the jamming; the railguns need a range: a "
		                            "cross-fix (a fleet ship or a flight group well off our line), a recon flight's eyes, an active ping "
		                            "burning through for a moment, or burn-through inside 12 km"), *FString::Join(JamOn, TEXT("; "))));
	}
	if (BurnThrough.Num())
	{
		Report(FString::Printf(TEXT("sensors: burn-through on %s — the jamming no longer hides it"), *FString::Join(BurnThrough, TEXT(", "))));
	}
	if (Unmasked.Num())
	{
		Report(FString::Printf(TEXT("sensors: %s — a decoy: the radar return is far too small for that drive, a Mandate drone emitter "
		                            "faking a warship. Dropped from the plot"), *FString::Join(Unmasked, TEXT(", "))));
	}
	if (Faded.Num())
	{
		Report(FString::Printf(TEXT("sensors: the bearing on %s has faded — its emissions stopped (it went quiet, or it was never "
		                            "there)"), *FString::Join(Faded, TEXT(", "))));
	}
}

void UAstraBattleSubsystem::TickPlayer(float Dt)
{
	FAstraBattleShip& P = Ships[0];
	if (const UAstraShipSubsystem* Ship = GetWorld()->GetSubsystem<UAstraShipSubsystem>())
	{
		P.Att = HeadingQuat(Ship->GetHeadingDeg(), Ship->GetMarkDeg());
		P.Vel = P.Att.GetForwardVector() * Ship->GetSpeedMps();
		P.bShieldsUp = Ship->AreShieldsUp() && Ship->PowerFactor(TEXT("shields")) > 0.05f;
		// an overheated ship throttles her own shields and guns (the heat factor: 1 up to 70 %)
		const float HF = Ship->HeatFactor();
		P.ShieldPower = Ship->PowerFactor(TEXT("shields")) * HF;
		P.WeaponPower = Ship->PowerFactor(TEXT("weapons")) * HF;
		const FString M = Ship->GetShieldMode();
		P.ShieldFacing = M == TEXT("forward") ? FVector(1, 0, 0) : M == TEXT("aft") ? FVector(-1, 0, 0)
		               : M == TEXT("port") ? FVector(0, -1, 0) : M == TEXT("starboard") ? FVector(0, 1, 0)
		               : M == TEXT("dorsal") ? FVector(0, 0, 1) : M == TEXT("ventral") ? FVector(0, 0, -1) : FVector::ZeroVector;
	}
	if (GateRun != EAstraGateRun::Lane)   // in the lane the gate's field moves the ship (TickGateRun)
	{
		P.Pos += P.Vel * Dt;
	}
}

void UAstraBattleSubsystem::TickScenario(float Dt)
{
	if (bSandbox)
	{
		return;                                   // a bench scenario: no script, no outcome, no director
	}
	FAstraBattleShip* Frigate = FindByContact(TEXT("T-11"));
	// the Captain has just come onto the bridge: the XO gives the situation
	if (!bBriefed && Time > 6.f)
	{
		bBriefed = true;
		Report(TEXT("bridge: the Captain has just come onto the bridge — the XO greets them and briefs the situation in two or "
		            "three short lines (where we are, the patrol with the 7th Fleet, anything on the sensors worth their attention)"));
	}
	// stage 1: the drifting contact wakes up and goes for the freighter (earlier if we poked it with an active scan)
	if (StageDone == 0 && Frigate && Frigate->bAlive && Time > 80.f)
	{
		StageDone = 1;
		Frigate->bCold = false;
		Frigate->bIdentified = Frigate->bClassified = true;
		Frigate->bHostile = true;
		Frigate->Mode = EAstraShipMode::Attack;
		Frigate->CruiseSpeed = 650.f;
		if (FAstraBattleShip* F = FindByContact(TEXT("T-07")))
		{
			Frigate->TargetId = F->Id;
		}
		Report(TEXT("sensors: contact T-11 has lit its drive and is accelerating towards the freighter Brightwater (T-07); "
		            "drive signature matches a Kharon Mandate frigate, Lethe class"));
	}
	// stage 2: the strike group arrives from the Janus Gate side
	if (StageDone == 1 && Time > 170.f)
	{
		StageDone = 2;
		StageTwoAt = Time;
		const FVector C = Ships[0].Pos + Polar(25 * OneKm, 70, 4);
		const int32 A = AddShip(TEXT("T-21"), TEXT("Acheron"), TEXT("Kharon Mandate cruiser (flagship of Archon Varek Solm)"),
		                        TEXT("SM_SHIP_MANDATE_Acheron"), EAstraSide::Mandate, C, 70.f, 500.f, 240.f, 3600.f, 1500.f);
		const int32 B = AddShip(TEXT("T-22"), TEXT("Styx"), TEXT("Kharon Mandate destroyer, Styx class"), TEXT("SM_SHIP_MANDATE_Styx"),
		                        EAstraSide::Mandate, C + Polar(4 * OneKm, 340, 1), 70.f, 550.f, 130.f, 1300.f, 500.f);
		const int32 D = AddShip(TEXT("T-23"), TEXT("Cocytus"), TEXT("Kharon Mandate destroyer, Styx class"), TEXT("SM_SHIP_MANDATE_Styx"),
		                        EAstraSide::Mandate, C + Polar(4 * OneKm, 160, -2), 70.f, 550.f, 130.f, 1300.f, 500.f);
		const int32 E = AddShip(TEXT("T-24"), TEXT("Phlegethon"), TEXT("Kharon Mandate destroyer, Styx class"), TEXT("SM_SHIP_MANDATE_Styx"),
		                        EAstraSide::Mandate, C + Polar(5 * OneKm, 250, 3), 70.f, 550.f, 130.f, 1300.f, 500.f);
		for (int32 Idx : {A, B, D, E})
		{
			FAstraBattleShip& S = Ships[Idx];
			S.bHostile = true;
			S.Mode = EAstraShipMode::Attack;
			S.CruiseSpeed = 450.f;
			S.RailDamage = 60.f;
			S.RailCd = 9.f;
			S.Missiles = 16;
			// the Archon and the Styx go for the Aquila (the carrier is the prize), the others for the escorts
			S.TargetId = (Idx == A || Idx == B) ? Ships[0].Id : (Idx == D ? Ships[1].Id : Ships[2].Id);
			SpawnVisual(S);
		}
		Ships[A].RailDamage = 85.f;
		Ships[A].RailSlugs = 3;
		Ships[A].RailCd = 8.f;
		Ships[A].Missiles = 32;
		Ships[A].PDChannels = 3;
		// the Archon's strike group: one battle group, the cruiser leading a wedge, sent at the picket and the carrier
		NoteGroupSpawn(EAstraSide::Mandate, TEXT("Strike Group Varek Solm"), TEXT("wedge"), TArray<int32>({A, B, D, E}), -1);
		if (FAstraBattleGroup* SG = FindGroup(Ships[A].GroupId))
		{
			SG->Objective = Ships[0].Pos;
			SG->bHasObjective = true;
		}
		AddEnemyWing(A, 6, 28.f);   // the flagship launches its strike fighters once the group is committed
		for (FAstraBattleShip& S : Ships)   // the fleet engages
		{
			if (S.Side == EAstraSide::Astra && !S.bPlayer && S.bAlive)
			{
				S.Mode = EAstraShipMode::Attack;
				S.TargetId = Ships[A].Id;
			}
		}
		TransmissionAt = Time + 12.f;
		TransmissionText = TEXT("T-21 — Archon Varek Solm hails the Aquila on an open channel");
		Ships[A].bLeader = true;
		bEngagementActive = true;
		Report(TEXT("sensors: four new contacts at 25 km, bearing 070 — Kharon Mandate strike group: cruiser Acheron (T-21) "
		            "and three Styx-class destroyers (T-22 Styx, T-23 Cocytus, T-24 Phlegethon), closing at 450 m/s; the 7th Fleet is moving to engage"));
	}
	// stage 3: the strike group was the Interdiction Fleet's probe; its vanguard comes through the Janus Gate, and the 7th Fleet's relief
	// from New Ravenna follows it — the opening grows into a fleet battle. Not after a surrender or under a truce (the war's director
	// takes the story from there)
	if (StageDone == 2 && StageTwoAt >= 0.f && Time > StageTwoAt + VanguardAfterS && !bSurrenderAccepted && TruceSince < 0.f && Landmarks.IsValidIndex(GateLandmark))
	{
		StageDone = 3;
		Report(TEXT("sensors: the Janus Gate is cycling — a transit wake with many drives behind it: a Mandate force is coming through; Keeper "
		            "Station confirms an unscheduled transit"));
		ScheduleOpeningForce(TEXT("vanguard"), Time + 50.f);
		ScheduleOpeningForce(TEXT("relief"), Time + 50.f + 170.f);
		TransmissionNotes.Add(TPair<float, FString>(Time + 62.f, TEXT("comms: Fleet to the Aquila — Battle Group Constance (the battleship ASN Constance and "
		                                                         "three destroyers) is under way from New Ravenna to the Gate, three minutes out")));
	}
	for (int32 i = TransmissionNotes.Num() - 1; i >= 0; --i)
	{
		if (Time >= TransmissionNotes[i].Key)
		{
			Report(TransmissionNotes[i].Value);
			TransmissionNotes.RemoveAt(i);
		}
	}
	// a Mandate captain opens a channel to the Aquila (arrival, succession after the flagship's loss, a broken ceasefire)
	if (TransmissionAt > 0.f && Time >= TransmissionAt)
	{
		TransmissionAt = -1.f;
		FString From, Rest;
		TransmissionText.Split(TEXT(" — "), &From, &Rest);
		const FAstraBattleShip* Caller = FindByContact(From);
		if (Caller && Caller->bAlive)
		{
			Report(TEXT("transmission: ") + TransmissionText);
		}
	}
	// the director's beats: arrivals when their time comes, repairs, quiet periods
	for (int32 i = PendingBeats.Num() - 1; i >= 0; --i)
	{
		if (Time >= PendingBeats[i].Key)
		{
			const TSharedPtr<FJsonObject> B = PendingBeats[i].Value;
			PendingBeats.RemoveAt(i);
			ArriveBeat(B);
		}
	}
	if (RepairUntil > 0.f)
	{
		FAstraBattleShip& P = Ships[0];
		AddHullDelta(P, RepairHullPerSec * Dt);
		if (Time >= RepairUntil)
		{
			RepairUntil = -1.f;
			P.Missiles += RepairMissiles;
			PlayerDecoys = 8;                              // the decoy magazines refilled with the missiles
			Report(FString::Printf(TEXT("engineering: repairs and resupply complete — hull at %.0f%%, %d missiles in the VLS"), 100.f * P.Hull / P.HullMax, P.Missiles));
			if (!bEngagementActive)
			{
				Report(TEXT("director: beat complete — resupply"), false);
			}
		}
	}
	if (CalmUntil > 0.f && Time >= CalmUntil)
	{
		CalmUntil = -1.f;
		Report(TEXT("director: beat complete — calm"), false);
	}
	// outcome
	if (bEngagementActive)
	{
		int32 Fighting = 0, Holding = 0, Withdrawing = 0, AgreedWithdraw = 0;
		for (const FAstraBattleShip& S : Ships)
		{
			if (S.bAlive && S.bHostile && !S.bDisabled)
			{
				Fighting += (!S.bFleeing && !S.bHoldFire) ? 1 : 0;
				Holding += (S.bHoldFire && !S.bFleeing) ? 1 : 0;
				Withdrawing += S.bFleeing ? 1 : 0;
				AgreedWithdraw += (S.bFleeing && S.bNegotiated) ? 1 : 0;
			}
		}
		// a ceasefire is a truce, not an end: the fight is over only when it has held for two minutes
		TruceSince = (Fighting == 0 && Holding > 0) ? (TruceSince < 0.f ? Time : TruceSince) : -1.f;
		FString Result;
		if (bSurrenderAccepted)
		{
			Result = TEXT("surrender accepted by the Mandate");
			Report(TEXT("tactical: the Mandate has accepted our surrender and ceased fire — their ships are closing to board the Aquila"));
		}
		else if (Fighting == 0 && Holding > 0 && Time - TruceSince > 120.f)
		{
			Result = TEXT("a truce holds: the Mandate ships hold fire under the terms spoken over the channel and pull back");
			Report(TEXT("tactical: two minutes without a shot — the truce with the Mandate holds; their ships are pulling back towards the Janus Gate"));
			for (FAstraBattleShip& S : Ships)
			{
				if (S.bAlive && S.bHostile && S.bHoldFire)
				{
					S.bFleeing = true;   // a standoff does not last: under the truce they withdraw
					S.Mode = EAstraShipMode::Evade;
				}
			}
		}
		else if (Fighting == 0 && Holding == 0)
		{
			Result = AgreedWithdraw > 0 ? TEXT("the enemy withdrew under the terms agreed over the channel")
			       : (Withdrawing > 0 ? TEXT("victory: the surviving enemy ships broke off and withdrew") : TEXT("victory: no hostile ship left"));
			Report(AgreedWithdraw > 0 ? TEXT("tactical: the Mandate ships are withdrawing as agreed over the channel; the engagement is over")
			                          : TEXT("tactical: no hostile ship left fighting in the engagement zone — the engagement is over"));
		}
		else if (Ships[0].Hull / Ships[0].HullMax < 0.08f)
		{
			Result = TEXT("the Aquila is crippled and cannot stay in the fight");
			Report(TEXT("engineering: hull integrity critical, main reactor containment failing — the Aquila cannot stay in the fight"));
		}
		if (!Result.IsEmpty())
		{
			bScenarioOver = true;
			bEngagementActive = false;
			EngagementEndedAt = Time;
			FString Fleet;
			int32 MandateLost = 0;
			for (const FAstraBattleShip& S : Ships)
			{
				if (!S.bCraft && !S.bPlayer && S.Side == EAstraSide::Astra)
				{
					Fleet += FString::Printf(TEXT("%s%s %s"), Fleet.IsEmpty() ? TEXT("") : TEXT(", "), *S.Name, S.bAlive ? TEXT("in action") : TEXT("lost"));
				}
				MandateLost += (S.Side == EAstraSide::Mandate && S.Mode == EAstraShipMode::Dead) ? 1 : 0;
			}
			Report(FString::Printf(TEXT("director: engagement over — %s; Aquila hull %.0f%%, %d missiles; our fleet: %s; Mandate ships destroyed so far: %d"),
			                       *Result, 100.f * Ships[0].Hull / Ships[0].HullMax, Ships[0].Missiles, *Fleet, MandateLost), false);
		}
	}
}

void UAstraBattleSubsystem::TickAI(FAstraBattleShip& S, float Dt)
{
	if (S.bGhost)
	{
		// a decoy flies out fast to its false bearing, then comes in like a warship at cruise, holding outside the
		// reach of the radar that would unmask it; its battery runs out after five minutes or so
		const FVector Aq = Ships[0].Pos;
		FVector Want = FVector::ZeroVector;
		if (!S.GhostGoal.IsZero())
		{
			Want = (S.GhostGoal - S.Pos).GetSafeNormal() * 900.f;
			if (FVector::Dist(S.Pos, S.GhostGoal) < 2.f * OneKm)
			{
				S.GhostGoal = FVector::ZeroVector;
			}
		}
		else if (FVector::Dist(S.Pos, Aq) > 34.f * OneKm)
		{
			Want = (Aq - S.Pos).GetSafeNormal() * 170.f;
		}
		S.Vel += (Want - S.Vel).GetClampedToMaxSize(120.f * Dt);
		S.Pos += S.Vel * Dt;
		if (!S.Vel.IsNearlyZero())
		{
			S.Att = S.Vel.ToOrientationQuat();
		}
		S.GhostLife -= Dt;
		return;
	}
	if (S.bDerelict || S.bDisabled)
	{
		S.Pos += S.Vel * Dt;
		S.Att = FQuat(FVector(0.2f, 0.3f, 1.f).GetSafeNormal(), FMath::DegreesToRadians(S.SpinDeg * Dt)) * S.Att;
		return;
	}
	if (S.Dmg.bModel && S.Side != EAstraSide::Neutral)
	{
		TickShipAI(S, Dt);                          // the warships of both sides: their own minds, their groups' orders
		return;
	}
	FVector DesiredVel = S.Vel;
	FVector Face = S.Vel.IsNearlyZero() ? S.Att.GetForwardVector() : S.Vel.GetSafeNormal();
	FAstraBattleShip* T = FindById(S.TargetId);
	// rules of engagement: the fleet does not shoot at an enemy that has ceased fire or is withdrawing
	const bool bFleet = S.Side == EAstraSide::Astra && !S.bPlayer;
	const auto Engageable = [this, &S](const FAstraBattleShip& O)
	{
		return O.bAlive && !O.bCold && !O.bDisabled && ((S.Side == EAstraSide::Mandate && O.Side == EAstraSide::Astra && !O.bCraft && (!O.bPlayer || bPlayerTracked)) ||
		                                (S.Side == EAstraSide::Astra && O.bHostile && !O.bFleeing && !O.bHoldFire));
	};
	if (T && T->bPlayer && S.Side == EAstraSide::Mandate && !bPlayerTracked)
	{
		T = nullptr;   // she went quiet: no firing solution on what they cannot see
		S.TargetId = -1;
	}
	if (T && (!T->bAlive || (bFleet && !Engageable(*T))))
	{
		T = nullptr;
		S.TargetId = -1;
	}
	// hostiles pick a target if theirs died; the fleet retargets too (and re-engages if the enemy resumes)
	if (!T && (S.Mode == EAstraShipMode::Attack || (bFleet && S.Mode == EAstraShipMode::Cruise)))
	{
		double Best = 1e18;
		for (FAstraBattleShip& O : Ships)
		{
			if (Engageable(O))
			{
				const double D = FVector::Dist(S.Pos, O.Pos);
				if (D < Best) { Best = D; T = &O; }
			}
		}
		S.TargetId = T ? T->Id : -1;
		S.Mode = T ? EAstraShipMode::Attack : EAstraShipMode::Cruise;
	}
	// the commander's focus of fire (datalink orders; the fleet: the Captain's request) wins over "the nearest"
	if ((S.Side == EAstraSide::Mandate || bFleet) && S.OrderTarget >= 0 && (S.Mode == EAstraShipMode::Attack || S.Mode == EAstraShipMode::Cruise))
	{
		FAstraBattleShip* F = FindById(S.OrderTarget);
		if (F && Engageable(*F))
		{
			T = F;
			S.TargetId = F->Id;
			S.Mode = EAstraShipMode::Attack;
		}
		else
		{
			S.OrderTarget = -1;   // gone: back to the nearest
		}
	}
	// the Aquila lost: the Mandate sweeps towards where she was last seen
	if (!T && S.Side == EAstraSide::Mandate && S.bHostile && !S.bFleeing && S.Mode == EAstraShipMode::Cruise && !bPlayerTracked)
	{
		const FVector ToLast = PlayerLastKnown - S.Pos;
		DesiredVel = ToLast.Size() > 3 * OneKm ? ToLast.GetSafeNormal() * S.CruiseSpeed * 0.8f : FVector::ZeroVector;
		if (!ToLast.IsNearlyZero())
		{
			Face = ToLast.GetSafeNormal();
		}
	}
	// neutral freighter: run from any close hostile
	if (S.Side == EAstraSide::Neutral)
	{
		for (const FAstraBattleShip& O : Ships)
		{
			if (O.bAlive && O.bHostile && FVector::Dist(S.Pos, O.Pos) < 40 * OneKm)
			{
				DesiredVel = (S.Pos - O.Pos).GetSafeNormal() * 260.f;
				Face = DesiredVel.GetSafeNormal();
			}
		}
	}
	if (S.Mode == EAstraShipMode::Attack && T)
	{
		// hold a preferred engagement range, circling at an angle; break off when badly hurt. The commander's stance
		// changes the fight: close (lasers, knife range), standoff (out of the lasers, railguns and missiles), flank
		// (onto the target's weak shield sector, or its beam), screen (between the target and the flagship)
		float Pref = S.SizeTier >= 2 ? 4 * OneKm : 3 * OneKm;
		if (S.Stance == 1) { Pref = 1.8f * OneKm; }
		else if (S.Stance == 2) { Pref = FMath::Clamp(S.RailRange * 0.9f, 5.f * OneKm, 9.f * OneKm); }
		const FVector ToT = T->Pos - S.Pos;
		const double Dist = ToT.Size();
		const FVector Dir = ToT / FMath::Max(1.0, Dist);
		const FVector Side = FVector::CrossProduct(Dir, FVector::UpVector).GetSafeNormal();
		FVector Goal = T->Pos - Dir * Pref + Side * Pref * 0.35;
		if (S.Stance == 3)
		{
			// away from a reinforced sector, else onto the beam (half the group each side)
			const FVector Weak = !T->ShieldFacing.IsNearlyZero() ? T->Att.RotateVector(-T->ShieldFacing.GetSafeNormal())
			                                                     : T->Att.GetRightVector() * ((S.Id % 2) ? 1.f : -1.f);
			Goal = T->Pos + Weak * Pref;
		}
		else if (S.Stance == 4 && bFleet)
		{
			// cover the Aquila: between her and the enemy, off her beam
			const FVector Out = (T->Pos - Ships[0].Pos).GetSafeNormal();
			Goal = Ships[0].Pos + Out * 2.2f * OneKm + FVector::CrossProduct(Out, FVector::UpVector).GetSafeNormal() * ((S.Id % 2) ? 0.9f : -0.9f) * OneKm;
		}
		else if (S.Stance == 4)
		{
			const FAstraBattleShip* Flag = FindByContact(MandateCommander());
			if (Flag && Flag != &S && Flag->bAlive)
			{
				const FVector Out = (T->Pos - Flag->Pos).GetSafeNormal();
				Goal = Flag->Pos + Out * 2.5f * OneKm + FVector::CrossProduct(Out, FVector::UpVector).GetSafeNormal() * ((S.Id % 2) ? 1.2f : -1.2f) * OneKm;
			}
		}
		DesiredVel = (Goal - S.Pos).GetClampedToMaxSize(S.CruiseSpeed * 1.0) ;
		if (Dist < Pref * 1.4)
		{
			DesiredVel = DesiredVel * 0.5 + T->Vel * 0.5;
		}
		Face = Dir;
		if (S.Hull < S.HullMax * 0.25f && S.bHostile && !S.bFleeing)
		{
			S.bFleeing = true;
			S.Mode = EAstraShipMode::Evade;
			Report(FString::Printf(TEXT("sensors: %s is badly damaged and breaking off, heading away from the fight"), *KnownLabel(S)));
		}
	}
	if (S.bHoldFire && !S.bFleeing)
	{
		DesiredVel = FVector::ZeroVector;   // ceasefire: hold station, guns trained
	}
	if (S.Mode == EAstraShipMode::Evade)
	{
		DesiredVel = (S.Pos - Ships[0].Pos).GetSafeNormal() * S.CruiseSpeed * 1.3f;
		Face = DesiredVel.GetSafeNormal();
		if (FVector::Dist(S.Pos, Ships[0].Pos) > 160 * OneKm && S.bAlive)
		{
			const bool bWasCommander = S.Side == EAstraSide::Mandate && S.bHostile && MandateCommander() == S.ContactId;
			S.bAlive = false;   // out of the theatre (jumped away)
			if (S.Side != EAstraSide::Neutral && !S.bGhost)
			{
				++Stats.ShipFate[S.Side == EAstraSide::Astra ? 0 : 1][(int32)EAstraFate::Withdrew];
			}
			if (bWasCommander)
			{
				OnCommanderLost(S, TEXT("jumped out of the system"));
			}
			if (S.Actor) { S.Actor->Destroy(); }
			if (S.ShieldBubble) { S.ShieldBubble->Destroy(); }
			if (S.DriveFlare) { S.DriveFlare->Destroy(); }
			Report(FString::Printf(TEXT("sensors: %s has left sensor range"), *KnownLabel(S)));
		}
	}
	if (S.Mode == EAstraShipMode::Idle && !S.bHostile)
	{
		DesiredVel = FVector::ZeroVector;
	}
	// accelerate towards the desired velocity, turn at a capital-ship rate (the engines' health sets both)
	const float Engines = EngineFactor(S);
	if (S.bHoldStation)
	{
		DesiredVel = FVector::ZeroVector;           // a test dummy or a picket kept on its mark (bench scenarios)
		S.Vel = FVector::ZeroVector;
	}
	const FVector DV = (DesiredVel - S.Vel).GetClampedToMaxSize(S.MaxAccel * Engines * Dt);
	S.Vel += DV;
	if (!Face.IsNearlyZero() && Engines > 0.f && !S.bFixedAtt)
	{
		const FQuat Want = FRotationMatrix::MakeFromX(Face).ToQuat();
		const float MaxStep = FMath::DegreesToRadians(S.MaxTurnDeg * Engines * Dt);
		const float Ang = S.Att.AngularDistance(Want);
		S.Att = Ang <= MaxStep ? Want : FQuat::Slerp(S.Att, Want, MaxStep / Ang);
	}
	S.Pos += S.Vel * Dt;
}

void UAstraBattleSubsystem::TickWeapons(FAstraBattleShip& S, float Dt)
{
	if (S.bDisabled)
	{
		return;                                   // no power: nothing fires, nothing defends
	}
	S.RailT = FMath::Max(0.f, S.RailT - Dt);
	S.MissileT = FMath::Max(0.f, S.MissileT - Dt);
	S.PDT = FMath::Max(0.f, S.PDT - Dt);
	for (FAstraMount& M : S.Mounts)
	{
		M.T = FMath::Max(0.f, M.T - Dt);
	}
	// point defence: every ship shoots at the missiles that threaten it and what stands beside it, the most dangerous first,
	// and at the craft inside its envelope (the Aquila's PD is automatic, 24 mounts)
	TickPointDefence(S);
	if (S.bPlayer)
	{
		TickPlayerFire(S, Dt);
		return;
	}
	const bool bRearGuard = S.bFleeing && S.Task == EAstraTask::RearGuard;
	if ((S.Mode != EAstraShipMode::Attack && !bRearGuard) || (S.bFleeing && !bRearGuard) || S.bHoldFire)
	{
		return;
	}
	FAstraBattleShip* T = FindById(S.TargetId);
	if (!T || !T->bAlive)
	{
		return;
	}
	const double Dist = FVector::Dist(S.Pos, T->Pos);
	if (S.Mounts.Num())
	{
		FireMounts(S, *T, Dist);                    // rails and lasers, mount by mount, each within its field of fire
	}
	else if (S.RailDamage > 0.f && S.RailT <= 0.f && Dist < S.RailRange)
	{
		S.LitT = 40.f;                                  // the muzzle flashes and the rails' pulse: every sensor sees it
		S.RailT = S.RailCd * FMath::FRandRange(0.8f, 1.2f);
		for (int32 i = 0; i < S.RailSlugs; ++i)
		{
			FireRail(S, *T, (0.0012f + Dist / 30e6) * (S.bJammed ? 3.f : 1.f));
		}
	}
	// the missiles: as the ship's cadence allows, unless its group keeps the cells for a saturating salvo, launched together
	// at the moment the group times (each ship at its own flight time before it), or by the commander's order to salvo
	if (S.SalvoAt >= 0.f && Time > S.SalvoAt + 8.f)
	{
		S.SalvoAt = -1.f;                               // the moment passed with no shot at it: the plan lapses
	}
	const bool bTimed = S.SalvoAt >= 0.f && Time >= S.SalvoAt;
	const bool bMassed = bTimed || S.bSalvo;
	const bool bMayLaunch = bMassed || (S.MissileT <= 0.f && !S.bHoldMissiles && S.SalvoAt < 0.f);
	if (S.Missiles > 0 && bMayLaunch && Dist < S.MissileRange && Dist > 2.5 * OneKm && T->Side != EAstraSide::Neutral)
	{
		// a massed salvo empties the ready cells (6 on a cruiser, 3 on a destroyer): the cells then reload for longer
		S.LitT = 40.f;
		S.MissileT = S.MissileCd * FMath::FRandRange(0.8f, 1.2f) * (S.bConserve ? 2.2f : 1.f) * (bMassed ? 2.f : 1.f);
		const int32 N = FMath::Min(S.Missiles, bMassed ? (S.SizeTier >= 2 ? 6 : 3) : (S.SizeTier >= 2 ? 4 : 2));
		S.bSalvo = false;
		S.SalvoAt = -1.f;
		S.bHoldMissiles = false;
		for (int32 i = 0; i < N; ++i)
		{
			FireMissile(S, *T);
			if (S.bJammed && FMath::FRand() < 0.35f)
			{
				Projectiles.Last().Target = -1;   // jammed seeker: the missile flies on blind
			}
		}
		S.Missiles -= N;
		if (T->bPlayer)
		{
			// one spoken report per 20 s at most, with the total: a real tactical officer does not call every salvo
			InboundSinceReport += N;
			const bool bSpeak = Time - LastInboundReport > 20.f;
			Report(FString::Printf(TEXT("tactical: %d missiles inbound from %s%s, point defense tracking"), InboundSinceReport, *KnownLabel(S),
			                       bSpeak ? TEXT("") : TEXT(" [same engagement, already reported]")), bSpeak);
			if (bSpeak)
			{
				LastInboundReport = Time;
				InboundSinceReport = 0;
			}
		}
	}
	if (S.Mounts.Num() == 0 && Dist < 4 * OneKm && FMath::FRand() < Dt * 0.6f)
	{
		FireLaser(S, *T);
	}
}

// ------------------------------------------------------------------------------------------------------ weapons
void UAstraBattleSubsystem::FireRail(FAstraBattleShip& From, FAstraBattleShip& To, float Spread)
{
	const float Speed = 12000.f;   // m/s (compressed game scale)
	const FVector Rel = To.Pos - From.Pos;
	const float Tof = Rel.Size() / Speed;
	FVector Aim = (To.Pos + To.Vel * Tof - From.Pos).GetSafeNormal();
	Aim = (Aim + FMath::VRand() * Spread).GetSafeNormal();
	FAstraProjectile Pr;
	Pr.Kind = EAstraProjKind::Rail;
	Pr.HitKind = EAstraHitKind::Rail;
	Pr.OwnerSide = (int8)AstraSideIdx(From.Side);
	Pr.Pos = From.Pos + Aim * From.Radius * 0.8;
	Pr.Vel = From.Vel + Aim * Speed;
	Pr.Owner = From.Id;
	Pr.Target = To.Id;
	Pr.Damage = From.RailDamage;
	Pr.Life = Tof + 1.5f;
	if (UWorld* World = GetWorld(); World && CylinderMesh && GlowMat && FApp::CanEverRender() && !FxOn())
	{
		FActorSpawnParameters P;
		P.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
		Pr.Actor = World->SpawnActor<AStaticMeshActor>(FVector::ZeroVector, FRotator::ZeroRotator, P);
		Pr.Actor->SetMobility(EComponentMobility::Movable);
		UStaticMeshComponent* C = Pr.Actor->GetStaticMeshComponent();
		C->SetStaticMesh(CylinderMesh);
		C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		C->SetCastShadow(false);
		UMaterialInstanceDynamic* M = C->CreateAndSetMaterialInstanceDynamicFromMaterial(0, GlowMat);
		M->SetVectorParameterValue(TEXT("Color"), From.Side == EAstraSide::Mandate ? FLinearColor(1.f, 0.5f, 0.25f) : RailColor);
		M->SetScalarParameterValue(TEXT("Intensity"), 400.f);
		Pr.Actor->SetActorScale3D(FVector(2.5f, 2.5f, 120.f));   // a 120 m streak, 2.5 m thick: readable at km range
	}
	if (FxOn())
	{
		Pr.FxSlot = WarFX->OnProjectile(From, To, Pr);     // drawn by the effects, from the gun's muzzle
	}
	Projectiles.Add(Pr);
}

void UAstraBattleSubsystem::FireMissile(FAstraBattleShip& From, FAstraBattleShip& To)
{
	FAstraProjectile Pr;
	Pr.Kind = EAstraProjKind::Missile;
	Pr.OwnerSide = (int8)AstraSideIdx(From.Side);
	const FVector Out = (From.Att.GetUpVector() + FMath::VRand() * 0.5f).GetSafeNormal();
	Pr.Pos = From.Pos + Out * From.Radius * 0.5;
	Pr.Vel = From.Vel + Out * 300.f;
	Pr.Owner = From.Id;
	Pr.Target = To.Id;
	Pr.Damage = 110.f;
	Pr.Life = 150.f;
	if (From.Side != EAstraSide::Neutral)
	{
		++Stats.MissilesFired[From.Side == EAstraSide::Astra ? 0 : 1];
	}
	if (UWorld* World = GetWorld(); World && SphereMesh && GlowMat && FApp::CanEverRender() && !FxOn())
	{
		FActorSpawnParameters P;
		P.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
		Pr.Actor = World->SpawnActor<AStaticMeshActor>(FVector::ZeroVector, FRotator::ZeroRotator, P);
		Pr.Actor->SetMobility(EComponentMobility::Movable);
		UStaticMeshComponent* C = Pr.Actor->GetStaticMeshComponent();
		C->SetStaticMesh(SphereMesh);
		C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		C->SetCastShadow(false);
		UMaterialInstanceDynamic* M = C->CreateAndSetMaterialInstanceDynamicFromMaterial(0, GlowMat);
		M->SetVectorParameterValue(TEXT("Color"), FLinearColor(1.f, 0.55f, 0.3f));
		M->SetScalarParameterValue(TEXT("Intensity"), 250.f);
		Pr.Actor->SetActorScale3D(FVector(8.f));   // an 8 m bright drive flare
		if (CylinderMesh)
		{
			Pr.Trail = World->SpawnActor<AStaticMeshActor>(FVector::ZeroVector, FRotator::ZeroRotator, P);
			Pr.Trail->SetMobility(EComponentMobility::Movable);
			UStaticMeshComponent* TC = Pr.Trail->GetStaticMeshComponent();
			TC->SetStaticMesh(CylinderMesh);
			TC->SetCollisionEnabled(ECollisionEnabled::NoCollision);
			TC->SetCastShadow(false);
			UMaterialInstanceDynamic* TM = TC->CreateAndSetMaterialInstanceDynamicFromMaterial(0, GlowMat);
			TM->SetVectorParameterValue(TEXT("Color"), From.Side == EAstraSide::Mandate ? FLinearColor(1.f, 0.5f, 0.25f) : FLinearColor(0.7f, 0.85f, 1.f));
			TM->SetScalarParameterValue(TEXT("Intensity"), 35.f);
		}
	}
	if (FxOn())
	{
		Pr.FxSlot = WarFX->OnProjectile(From, To, Pr);
	}
	Projectiles.Add(Pr);
}

void UAstraBattleSubsystem::FireLaser(FAstraBattleShip& From, FAstraBattleShip& To)
{
	// the beam strikes the hull where it enters it, at a random point of the side it comes from
	const FVector Dir = (To.Pos - From.Pos).GetSafeNormal();
	const FVector Hit = HullRandomEntry(From.Pos, To);
	AddBeam(From.Pos, Hit, 0.35f, From.Side == EAstraSide::Mandate ? FLinearColor(1.f, 0.35f, 0.15f) : FLinearColor(0.5f, 0.8f, 1.f), EAstraFxShot::Laser, From.Id, To.Id);
	ApplyHit(To, Dir, From.LaserDamage > 0.f ? From.LaserDamage : 18.f, Hit, EAstraHitKind::Laser, From.Id);
}

bool UAstraBattleSubsystem::PlayerFire(const FString& Weapon, const FString& ContactId, int32 Salvo, FString& OutDetail)
{
	FAstraBattleShip* T = FindByContact(ContactId);
	if (!T || !T->bAlive)
	{
		OutDetail = FString::Printf(TEXT("no contact %s on the plot"), *ContactId);
		return false;
	}
	if (T->Side == EAstraSide::Astra)
	{
		OutDetail = TEXT("weapons interlock: target is a friendly vessel");
		return false;
	}
	const FString W = Weapon.ToLower();
	const bool bHomeOnJam = T->bJamming && T->Track < 2 && (W == TEXT("missiles") || W == TEXT("torpedoes"));
	if (T->bFog && T->Track < 2 && !bHomeOnJam)
	{
		OutDetail = T->bJamming
			? FString::Printf(TEXT("no firing solution for the %s on %s: it is jamming, we have its bearing but no range — missiles can "
			                       "home on the jamming; for the guns we need a cross-fix, a recon flight, an active ping or to close "
			                       "inside 12 km"), *W, *T->ContactId)
			: FString::Printf(TEXT("no firing solution on %s: only a passive bearing, no range — we need a track (an active scan, "
			                       "EMCON full, a recon flight, or closing in)"), *T->ContactId);
		return false;
	}
	if (T->Side == EAstraSide::Mandate && T->bNegotiated)
	{
		BreakCeasefire(*T);
	}
	FAstraBattleShip& P = Ships[0];
	const double Dist = FVector::Dist(P.Pos, T->Pos);
	if (W == TEXT("railguns"))
	{
		P.FireTarget = T->Id;
		P.RailVolleys = FMath::Clamp(Salvo, 1, 12);
		OutDetail = Dist > P.RailRange
			? FString::Printf(TEXT("railguns assigned to %s, now at %.0f km: they open fire by themselves once it is inside %.0f km (%d volleys)"),
			                  *T->ContactId, Dist / OneKm, P.RailRange / OneKm, P.RailVolleys)
			: FString::Printf(TEXT("railguns engaging %s: %d volleys of %d slugs, one every %.0f s, time of flight %.1f s"),
			                  *T->ContactId, P.RailVolleys, P.RailSlugs, P.RailCd, Dist / 12000.0);
	}
	else if (W == TEXT("missiles") || W == TEXT("torpedoes"))
	{
		if (P.MissileT > 0.f)
		{
			OutDetail = FString::Printf(TEXT("VLS cycling after the last salvo, next salvo ready in %.0f s"), P.MissileT);
			return false;
		}
		const int32 N = FMath::Clamp(Salvo, 1, 8);
		if (P.Missiles < N)
		{
			OutDetail = FString::Printf(TEXT("not enough missiles in the VLS (%d left)"), P.Missiles);
			return false;
		}
		for (int32 i = 0; i < N; ++i)
		{
			FireMissile(P, *T);
		}
		P.Missiles -= N;
		P.MissileT = P.MissileCd;
		HullSound(TEXT("SW_VLS_Launch"), 0.85f, 0.2f);
		if (UAstraShipSubsystem* Ship = GetWorld()->GetSubsystem<UAstraShipSubsystem>())
		{
			Ship->AddHeat(0.1f * N);   // the launch cells' exhaust
		}
		PlayerSinceFired = 0.f;   // the launch lights them up
		OutDetail = bHomeOnJam
			? FString::Printf(TEXT("%d missiles away at %s in home-on-jam mode (they ride its jamming; the range is theirs to find), %d "
			                       "left in the VLS"), N, *T->ContactId, P.Missiles)
			: FString::Printf(TEXT("%d missiles away at %s, %d left in the VLS, time to target about %.0f s"), N, *T->ContactId,
			                  P.Missiles, Dist / 1400.0 + 2.0);
	}
	else if (W == TEXT("lasers"))
	{
		P.FireTarget = T->Id;
		P.LaserShots = FMath::Clamp(Salvo, 1, 12) * 2;
		OutDetail = Dist > P.LaserRange ? FString::Printf(TEXT("lasers assigned to %s, now at %.1f km: they fire once it is inside %.0f km"), *T->ContactId, Dist / OneKm, P.LaserRange / OneKm)
		                                : FString::Printf(TEXT("laser batteries firing on %s"), *T->ContactId);
	}
	else
	{
		OutDetail = FString::Printf(TEXT("unknown weapon %s"), *Weapon);
		return false;
	}
	return true;
}

bool UAstraBattleSubsystem::PlayerCeaseFire(FString& OutDetail)
{
	if (Ships.Num() == 0)
	{
		return false;
	}
	FAstraBattleShip& P = Ships[0];
	const int32 Pending = P.RailVolleys + P.LaserShots;
	P.RailVolleys = 0;
	P.LaserShots = 0;
	P.FireTarget = -1;
	int32 InFlight = 0;
	for (const FAstraProjectile& Pr : Projectiles)
	{
		InFlight += (!Pr.bDead && Pr.Owner == P.Id && Pr.Kind == EAstraProjKind::Missile) ? 1 : 0;
	}
	OutDetail = FString::Printf(TEXT("all offensive fire stopped (%d volleys cancelled); %d of our missiles still in flight; point defense stays on"),
	                            Pending, InFlight);
	return true;
}

FString UAstraBattleSubsystem::FlightLine() const
{
	TArray<FString> Out;
	for (int32 i = 0; i < Squadrons.Num(); ++i)
	{
		const FAstraSquadron& Q = Squadrons[i];
		if (Q.Side != EAstraSide::Astra)
		{
			continue;
		}
		const int32 Up = AirborneCount(i);
		Out.Add(Up > 0 ? FString::Printf(TEXT("%s %d UP · %s"), *Q.Name.ToUpper(), Up, *Q.Mission.ToUpper())
		        : Q.RearmT > 0.f ? FString::Printf(TEXT("%s REARMING %.0fS"), *Q.Name.ToUpper(), Q.RearmT)
		                         : FString::Printf(TEXT("%s %d ON DECK"), *Q.Name.ToUpper(), Q.OnDeck));
	}
	return FString::Join(Out, TEXT("   "));
}

UAstraBattleSubsystem::FFireControl UAstraBattleSubsystem::GetFireControl() const
{
	FFireControl F;
	if (Ships.Num() == 0)
	{
		return F;
	}
	const FAstraBattleShip& P = Ships[0];
	if (const FAstraBattleShip* T = Ships.FindByPredicate([&P](const FAstraBattleShip& S) { return S.Id == P.FireTarget && S.bAlive; }))
	{
		if (P.RailVolleys > 0 || P.LaserShots > 0)
		{
			F.Target = T->ContactId;
			F.TargetRangeKm = FVector::Dist(P.Pos, T->Pos) / OneKm;
		}
	}
	F.RailVolleys = P.RailVolleys;
	F.RailNext = P.RailT;
	F.LaserShots = P.LaserShots;
	F.Missiles = P.Missiles;
	F.MissileCycle = P.MissileT;
	for (const FAstraProjectile& Pr : Projectiles)
	{
		if (!Pr.bDead && Pr.Kind == EAstraProjKind::Missile)
		{
			F.OursInFlight += Pr.Owner == P.Id ? 1 : 0;
			F.Inbound += Pr.Target == P.Id ? 1 : 0;
		}
	}
	return F;
}

void UAstraBattleSubsystem::BuildHoloBlips(TArray<FAstraHoloBlip>& Out, FPlotCounts& Counts) const
{
	Out.Reset();
	Counts = FPlotCounts();
	if (Ships.Num() == 0)
	{
		return;
	}
	const FAstraBattleShip& P = Ships[0];
	const FVector Origin = ToWorld(P.Pos);
	auto Dir = [this](const FVector& Pos, const FVector& Vel)
	{
		return Vel.IsNearlyZero() ? FVector::ZeroVector : (ToWorld(Pos + Vel) - ToWorld(Pos)).GetSafeNormal();
	};
	// a flight group's airborne aircraft and the first of them (it carries the group's label): found in one pass over the ships, not once for each of the aircraft
	TArray<int32, TInlineAllocator<16>> SquadCount, SquadLead;
	SquadCount.SetNumZeroed(Squadrons.Num());
	SquadLead.Init(-1, Squadrons.Num());
	for (int32 i = 0; i < Ships.Num(); ++i)
	{
		const FAstraBattleShip& S = Ships[i];
		if (S.bAlive && S.bCraft && Squadrons.IsValidIndex(S.Squadron))
		{
			SquadLead[S.Squadron] = SquadLead[S.Squadron] < 0 ? i : SquadLead[S.Squadron];
			++SquadCount[S.Squadron];
		}
	}
	for (int32 Si = 0; Si < Ships.Num(); ++Si)
	{
		const FAstraBattleShip& S = Ships[Si];
		if (!S.bAlive)
		{
			continue;
		}
		if (S.bFog && S.Track == 0)
		{
			continue;
		}
		FAstraHoloBlip B;
		B.Id = S.Id;
		B.bFiringAtUs = S.Side == EAstraSide::Mandate && !S.bHoldFire && !S.bDisabled && (S.TargetId == P.Id || S.FireTarget == P.Id);
		B.Kind = 0;
		B.bBearingOnly = S.bFog && S.Track == 1;
		B.bJamming = S.bJamming;
		B.Rel = ToWorld(S.Pos) - Origin;
		B.Rot = ToWorldRot(S.Att);
		B.VelDir = Dir(S.Pos, S.Vel);
		B.Speed = S.Vel.Size();
		B.Side = S.Side;
		B.bPlayer = S.bPlayer;
		B.bHostile = S.bHostile;
		B.bUnknown = (S.bFog ? !S.bClassified : !S.bIdentified) || S.bCold;
		B.bRetreating = S.bFleeing;
		B.bHoldFire = S.bHoldFire;
		B.bTargeted = !S.bPlayer && (P.FireTarget == S.Id) && (P.RailVolleys > 0 || P.LaserShots > 0);
		B.Size = S.SizeTier >= 3 ? 1.f : (S.SizeTier >= 2 ? 0.85f : (S.SizeTier >= 1 ? 0.7f : 0.55f));
		B.RangeKm = FVector::Dist(S.Pos, P.Pos) / OneKm;
		B.Name = S.bIdentified ? S.Name : FString();
		B.Contact = S.ContactId;
		if (S.bFog && S.bClassified && !S.bIdentified)
		{
			FString Head, Tail;
			B.ClassShort = S.Class.Split(TEXT(", "), &Head, &Tail) ? Tail : S.Class;   // "Kharon Mandate cruiser, Acheron class"
		}
		if (S.bGhost)
		{
			B.Side = EAstraSide::Mandate;                 // it is made to look like one
			B.bHostile = true;
		}
		if (B.bBearingOnly)
		{
			// a bearing has no range, no speed, no size: only a direction (every plot pins it to its rim)
			B.Rel = B.Rel.GetSafeNormal() * 1.0e9f;
			B.RangeKm = -1.f;
			B.Speed = 0.f;
			B.VelDir = FVector::ZeroVector;
			B.Size = 0.7f;
			B.Rot = FQuat::Identity;
		}
		if (S.bCraft && Squadrons.IsValidIndex(S.Squadron))
		{
			B.bCraft = true;
			B.Squadron = S.Squadron;
			B.Size = S.CraftKind == 2 ? 0.2f : 0.3f;
			// the first airborne aircraft of a group carries the group's label (only it has a name and a mission to show)
			B.bNoLabel = SquadLead[S.Squadron] != Si;
			if (!B.bNoLabel)
			{
				const FAstraSquadron& Q = Squadrons[S.Squadron];
				B.Name = FString::Printf(TEXT("%s x%d"), *Q.Name.ToUpper(), SquadCount[S.Squadron]);
				B.Contact = Q.Mission.ToUpper();
			}
		}
		if (!S.bPlayer)
		{
			const bool bHostileNow = B.bHostile && !B.bRetreating;
			if (B.bCraft)
			{
				Counts.HostileCraft += bHostileNow ? 1 : 0;
				Counts.FriendlyCraft += B.Side == EAstraSide::Astra ? 1 : 0;
			}
			else
			{
				Counts.HostileShips += bHostileNow ? 1 : 0;
				Counts.FriendlyShips += B.Side == EAstraSide::Astra ? 1 : 0;
			}
		}
		Out.Add(MoveTemp(B));
	}
	for (const FAstraProjectile& Pr : Projectiles)
	{
		if (Pr.bDead || Pr.Kind != EAstraProjKind::Missile)
		{
			continue;
		}
		FAstraHoloBlip B;
		B.Kind = 1;
		B.Rel = ToWorld(Pr.Pos) - Origin;
		B.VelDir = Dir(Pr.Pos, Pr.Vel);
		const FAstraBattleShip* Owner = FindById(Pr.Owner);
		B.Side = Owner ? Owner->Side : EAstraSide::Neutral;
		B.bHostile = Owner && Owner->bHostile;
		++Counts.Missiles;
		Out.Add(MoveTemp(B));
	}
	for (const FAstraFlash& F : Flashes)
	{
		if (F.bBeam || F.Size < 60.f)
		{
			continue;   // only explosions and heavy hits make it to the plot
		}
		FAstraHoloBlip B;
		B.Kind = 2;
		B.Rel = ToWorld(F.Pos) - Origin;
		B.Size = F.Size;
		B.Fade = 1.f - F.Age / F.Life;
		Out.Add(B);
	}
}

TSharedRef<FJsonObject> UAstraBattleSubsystem::PlayerWeaponsJson() const
{
	TSharedRef<FJsonObject> W = MakeShared<FJsonObject>();
	if (Ships.Num() == 0)
	{
		return W;
	}
	const FAstraBattleShip& P = Ships[0];
	const FAstraBattleShip* T = Ships.FindByPredicate([&P](const FAstraBattleShip& S) { return S.Id == P.FireTarget && S.bAlive; });
	const double Dist = T ? FVector::Dist(P.Pos, T->Pos) : 0.0;
	W->SetStringField(TEXT("railguns"), (T && P.RailVolleys > 0)
		? (Dist > P.RailRange ? FString::Printf(TEXT("assigned to %s, waiting for it to close inside %.0f km (now %.0f km), %d volleys queued"),
		                                        *T->ContactId, P.RailRange / OneKm, Dist / OneKm, P.RailVolleys)
		                      : FString::Printf(TEXT("engaging %s, %d volleys left, next in %.0f s"), *T->ContactId, P.RailVolleys, P.RailT))
		: FString::Printf(TEXT("ready, 4 twin turrets, range %.0f km, one volley every %.0f s"), P.RailRange / OneKm, P.RailCd));
	W->SetStringField(TEXT("lasers"), (T && P.LaserShots > 0) ? FString::Printf(TEXT("assigned to %s, %d shots queued"), *T->ContactId, P.LaserShots)
	                                                          : FString::Printf(TEXT("ready, 12 batteries, range %.0f km"), P.LaserRange / OneKm));
	int32 InFlight = 0;
	for (const FAstraProjectile& Pr : Projectiles)
	{
		InFlight += (!Pr.bDead && Pr.Owner == P.Id && Pr.Kind == EAstraProjKind::Missile) ? 1 : 0;
	}
	W->SetStringField(TEXT("missiles"), FString::Printf(TEXT("%d in the VLS, %s; %d of ours in flight; range %.0f km"), P.Missiles,
		P.MissileT > 0.f ? *FString::Printf(TEXT("cycling, next salvo in %.0f s"), P.MissileT) : TEXT("ready (max 8 per salvo)"), InFlight, P.MissileRange / OneKm));
	return W;
}

void UAstraBattleSubsystem::TickPlayerFire(FAstraBattleShip& P, float Dt)
{
	P.LaserT = FMath::Max(0.f, P.LaserT - Dt);
	if (P.RailVolleys <= 0 && P.LaserShots <= 0)
	{
		return;
	}
	FAstraBattleShip* T = FindById(P.FireTarget);
	if (!T || !T->bAlive)
	{
		P.RailVolleys = P.LaserShots = 0;
		return;
	}
	const double Dist = FVector::Dist(P.Pos, T->Pos);
	// out of range: the assignment stands and the guns wait for the target to close
	if (P.WeaponPower < 0.05f)
	{
		return;   // no power to the weapons
	}
	UAstraShipSubsystem* Heat = GetWorld()->GetSubsystem<UAstraShipSubsystem>();
	// the mounts that bear on the target (their fields of fire, their health): with none in arc the volley waits for the helm
	const FVector AimDir = T->Pos + T->Vel * (Dist / 12000.0) - P.Pos;
	if (P.RailVolleys > 0 && P.RailT <= 0.f && Dist <= P.RailRange)
	{
		const int32 Slugs = BearingBarrels(P, EAstraMountKind::Rail, AimDir);
		if (Slugs > 0)
		{
			P.RailT = P.RailCd / FMath::Max(0.25f, P.WeaponPower * PowerFactorOf(P));   // capacitor recharge follows weapons power (and the heat)
			HullSound(TEXT("SW_Rail_Fire"), 0.9f, 0.3f);
			--P.RailVolleys;
			PlayerSinceFired = 0.f;
			if (Heat)
			{
				Heat->RailgunDraw();   // the capacitors pull on the ship's power: the lights sag for a moment
				Heat->AddHeat(4.0f);   // eight slugs out of the rails: the capacitors and the barrels dump their heat
			}
			for (int32 i = 0; i < Slugs; ++i)
			{
				FireRail(P, *T, 0.001f + Dist / 30e6);
			}
		}
	}
	if (P.LaserShots > 0 && P.LaserT <= 0.f && Dist <= P.LaserRange && BearingBarrels(P, EAstraMountKind::Laser, AimDir) > 0)
	{
		P.LaserT = 0.5f / FMath::Max(0.4f, Heat ? Heat->HeatFactor() : 1.f);
		--P.LaserShots;
		FireLaser(P, *T);
		PlayerSinceFired = 0.f;
		if (Heat)
		{
			Heat->AddHeat(0.2f);
		}
	}
}

bool UAstraBattleSubsystem::PlayerScan(const FString& ContactId, FString& OutDetail)
{
	PlayerSinceFired = 0.f;   // an active ping: every sensor out there hears it
	FAstraBattleShip* T = ContactId.IsEmpty() ? nullptr : FindByContact(ContactId);
	int32 Found = 0;
	TArray<FString> Decoys;
	const bool bTargetGhost = T && T->bGhost && T->bAlive;
	for (FAstraBattleShip& S : Ships)
	{
		if (S.bGhost && S.bAlive && FVector::Dist(S.Pos, Ships[0].Pos) < 90.f * OneKm)
		{
			Decoys.Add(S.ContactId);                   // the return is a drone's: a decoy, off the plot
			S.bAlive = false;
			continue;
		}
		if (S.bFog && S.bAlive && FVector::Dist(S.Pos, Ships[0].Pos) < 90.f * OneKm)
		{
			Found += S.Track < 2 ? 1 : 0;
			S.Track = 2;
			S.TrackHold = 45.f;
			S.bDark = S.bDark && !S.bHostile;          // they heard it: found, no point in running dark (their jammers come on)
			S.bClassified = true;
			S.bIdentified = S.bIdentified || (&S == T && FVector::Dist(S.Pos, Ships[0].Pos) < 60.f * OneKm);
		}
	}
	const FString DecoyNote = Decoys.Num() ? FString::Printf(TEXT("; %s %s decoy%s — drone emitters faking a warship's drive (a radar "
	                                                            "return far too small), dropped from the plot"), *FString::Join(Decoys, TEXT(", ")),
	                                                            Decoys.Num() > 1 ? TEXT("were") : TEXT("was a"), Decoys.Num() > 1 ? TEXT("s") : TEXT(""))
	                                       : FString();
	if (bTargetGhost)
	{
		OutDetail = FString::Printf(TEXT("active ping on %s: the return is far too small for that drive — a decoy emitter, a Mandate drone; "
		                                 "dropped from the plot%s — and every sensor out there heard our ping"), *T->ContactId, *DecoyNote);
		return true;
	}
	if (!T && (Found > 0 || Decoys.Num()))
	{
		OutDetail = FString::Printf(TEXT("full active sweep: %d contact(s) now tracked and classified%s — and every sensor out there heard our ping"),
		                            Found, *DecoyNote);
		return true;
	}
	if (T && T->ContactId == TEXT("T-11") && StageDone == 0)
	{
		Time = FMath::Max(Time, 78.f);   // the ping gives us away: the frigate reacts
		OutDetail = TEXT("active ping on T-11: hull ~160 m, reactor warm, weapons ports detected — it has seen us");
		return true;
	}
	if (T)
	{
		if (FAstraPOI* Poi = POIs.FindByPredicate([T](const FAstraPOI& X) { return X.ShipId == T->Id; }))
		{
			if (Poi->Revealed == 0)
			{
				RevealPOI(*Poi);
				OutDetail = FString::Printf(TEXT("scan of %s (%s): %s"), *T->ContactId, *Poi->Name, *Poi->Findings[0]);
			}
			else
			{
				OutDetail = FString::Printf(TEXT("scan of %s (%s): nothing new from this range — %s"), *T->ContactId, *Poi->Name,
				                            Poi->Revealed < Poi->Findings.Num() ? TEXT("a flight group, or the Aquila closing to 5 km, would learn more")
				                                                                : TEXT("everything there is to learn has been learned"));
			}
			return true;
		}
	}
	OutDetail = T ? FString::Printf(TEXT("scan of %s: %s, hull %.0f%%, shields %.0f%%"), *T->ContactId, *T->Class,
	                                 100.f * T->Hull / T->HullMax, 100.f * T->Shield / T->ShieldMax)
	              : TEXT("full active sweep: no new contacts inside 150 km");
	return true;
}

bool UAstraBattleSubsystem::ContactGeometry(const FString& ContactId, double& OutBearing, double& OutMark, double& OutRangeKm) const
{
	const FAstraBattleShip* T = Ships.FindByPredicate([&ContactId](const FAstraBattleShip& S)
	{
		return !S.bPlayer && S.bAlive && S.ContactId.Equals(ContactId, ESearchCase::IgnoreCase);
	});
	if (!T || Ships.Num() == 0)
	{
		return false;
	}
	const FAstraBattleShip& P = Ships[0];
	if (T->bFog && T->Track < 2)
	{
		// only a bearing: the helm can steer down it, but has no range and no lead
		OutBearing = BearingDeg(P.Pos, T->Pos);
		OutMark = MarkDeg(P.Pos, T->Pos);
		OutRangeKm = -1.0;
		return true;
	}
	const double D = FVector::Dist(P.Pos, T->Pos);
	const double Lead = FMath::Min(D / FMath::Max((double)P.Vel.Size(), 100.0), 60.0) * 0.5;
	const FVector Aim = T->Pos + T->Vel * Lead;
	OutBearing = BearingDeg(P.Pos, Aim);
	OutMark = MarkDeg(P.Pos, Aim);
	OutRangeKm = D / OneKm;
	return true;
}

FString UAstraBattleSubsystem::MandateCommander() const
{
	const FAstraBattleShip* Best = nullptr;
	for (const FAstraBattleShip& S : Ships)
	{
		if (!S.bAlive || !S.bHostile || S.bCraft || S.bDisabled || S.Side != EAstraSide::Mandate)
		{
			continue;
		}
		if (S.bLeader)
		{
			return S.ContactId;
		}
		if (!Best || S.Radius > Best->Radius)
		{
			Best = &S;   // no leader left: the biggest ship's captain takes over
		}
	}
	return Best ? Best->ContactId : FString();
}

bool UAstraBattleSubsystem::EnemyTactics(const TSharedPtr<FJsonObject>& Args, FString& OutDetail)
{
	Ships.Reserve(Ships.Num() + 4);                   // decoys may be added below: no reallocation under our pointers
	FString Focus, StanceName, Missiles, Fighters, Ew;
	Args->TryGetStringField(TEXT("focus"), Focus);
	Args->TryGetStringField(TEXT("stance"), StanceName);
	Args->TryGetStringField(TEXT("missiles"), Missiles);
	Args->TryGetStringField(TEXT("fighters"), Fighters);
	Args->TryGetStringField(TEXT("ew"), Ew);
	Ew = Ew.ToLower();
	TArray<FString> Only;
	Args->TryGetStringArrayField(TEXT("ships"), Only);
	for (FString& O : Only) { O = O.ToUpper(); }
	StanceName = StanceName.ToLower();
	static const TCHAR* Stances[] = {TEXT("standard"), TEXT("close"), TEXT("standoff"), TEXT("flank"), TEXT("screen")};
	int32 Stance = -1;
	for (int32 i = 0; i < 5; ++i) { if (StanceName == Stances[i]) { Stance = i; } }
	// the focus: an ASTRA warship still in the fight ("" or "nearest": each ship its own)
	const FAstraBattleShip* F = nullptr;
	if (!Focus.IsEmpty() && !Focus.Equals(TEXT("nearest"), ESearchCase::IgnoreCase))
	{
		F = Focus.Contains(TEXT("AQUILA"), ESearchCase::IgnoreCase) ? &Ships[0] : FindByContact(Focus.ToUpper());
		if (!F)
		{
			for (const FAstraBattleShip& X : Ships)
			{
				if (X.bAlive && X.Side == EAstraSide::Astra && X.Name.Contains(Focus, ESearchCase::IgnoreCase)) { F = &X; }
			}
		}
		if (!F || !F->bAlive || F->Side != EAstraSide::Astra || F->bCraft)
		{
			OutDetail = FString::Printf(TEXT("no ASTRA warship '%s' in the fight"), *Focus);
			return false;
		}
	}
	TArray<FAstraBattleShip*> Group;
	bool bFocusChanged = false, bStanceChanged = false;
	int32 Salvo = 0;
	for (FAstraBattleShip& S : Ships)
	{
		if (!S.bAlive || S.Side != EAstraSide::Mandate || !S.bHostile || S.bCraft || S.bFleeing || S.bHoldFire || S.bCold ||
		    (Only.Num() && !Only.Contains(S.ContactId)))
		{
			continue;
		}
		Group.Add(&S);
		const int32 NewTarget = F ? F->Id : -1;
		bFocusChanged |= NewTarget >= 0 && S.OrderTarget != NewTarget;
		S.OrderTarget = NewTarget;
		if (Stance >= 0)
		{
			bStanceChanged |= S.Stance != Stance;
			S.Stance = (uint8)Stance;
		}
		if (Missiles.Equals(TEXT("salvo"), ESearchCase::IgnoreCase) && S.Missiles > 0)
		{
			S.bSalvo = true;
			S.bConserve = false;
			Salvo += FMath::Min(S.Missiles, S.SizeTier >= 2 ? 6 : 3);
		}
		else if (Missiles.Equals(TEXT("conserve"), ESearchCase::IgnoreCase)) { S.bConserve = true; }
		else if (Missiles.Equals(TEXT("normal"), ESearchCase::IgnoreCase)) { S.bConserve = false; }
		if (S.Mode != EAstraShipMode::Attack && S.Mode != EAstraShipMode::Evade)
		{
			S.Mode = EAstraShipMode::Attack;
		}
	}
	// electronic warfare: jammers on, everything quiet, or decoys out (the capital ships carry them)
	int32 GhostsOut = 0;
	FString EwDone;
	if (Ew == TEXT("jam") || Ew == TEXT("quiet") || Ew == TEXT("auto"))
	{
		for (FAstraBattleShip* S : Group)
		{
			S->EwMode = Ew == TEXT("jam") ? 1 : (Ew == TEXT("quiet") ? 2 : 0);
		}
		EwDone = Ew == TEXT("jam") ? TEXT(", jammers on") : (Ew == TEXT("quiet") ? TEXT(", emissions down (no jamming)") : TEXT(", EW as the situation calls"));
	}
	else if (Ew == TEXT("decoys"))
	{
		for (int32 i = 0; i < Group.Num(); ++i)
		{
			if (Group[i]->Decoys >= 2 && Group[i]->bFog)
			{
				Group[i]->Decoys -= 2;
				const int32 Idx = UE_PTRDIFF_TO_INT32(Group[i] - Ships.GetData());
				GhostsOut += LaunchGhosts(Idx, 2);   // (within the reserve: Group and F stay valid)
				break;                                // one ship's pair per order: the rest are kept for later
			}
		}
		EwDone = GhostsOut ? FString::Printf(TEXT(", %d decoy emitters out"), GhostsOut) : FString(TEXT(", no decoys left aboard"));
	}
	if (Group.Num() == 0)
	{
		OutDetail = TEXT("no ship of the strike group is fighting");
		return false;
	}
	// the battle groups' menu (docs/GUERRA.md): order (auto | attack | attack_group | pin | flank_left | flank_right | screen |
	// withdraw | regroup | reinforce | hold), target (an ASTRA contact id), group (an own group's name or "all"; by default
	// the commander's), reinforce_group (an own group's name), formation (line | wedge | column | screen), duration_s
	FString GroupOrderDone;
	{
		FString OrderName, FormationName, GroupName, TargetId, ReinforceName;
		double DurationS = 0.0;
		Args->TryGetStringField(TEXT("order"), OrderName);
		Args->TryGetStringField(TEXT("formation"), FormationName);
		Args->TryGetStringField(TEXT("group"), GroupName);
		Args->TryGetStringField(TEXT("target"), TargetId);
		Args->TryGetStringField(TEXT("reinforce_group"), ReinforceName);
		Args->TryGetNumberField(TEXT("duration_s"), DurationS);
		if (!OrderName.IsEmpty() || !FormationName.IsEmpty())
		{
			TArray<int32> Gids;
			auto MandateGroup = [this](const FString& Name) -> int32
			{
				for (const FAstraBattleGroup& G : Groups)
				{
					if (G.Side == EAstraSide::Mandate && (G.Name.Contains(Name, ESearchCase::IgnoreCase) || FString::FromInt(G.Id) == Name))
					{
						return G.Id;
					}
				}
				return INDEX_NONE;
			};
			if (Only.Num())
			{
				for (const FString& Contact : Only)
				{
					if (const FAstraBattleShip* S = FindByContact(Contact); S && S->GroupId >= 0)
					{
						Gids.AddUnique(S->GroupId);
					}
				}
			}
			else if (GroupName.Equals(TEXT("all"), ESearchCase::IgnoreCase) || GroupName.IsEmpty())
			{
				if (GroupName.IsEmpty())
				{
					if (const FAstraBattleShip* Cmd = FindByContact(MandateCommander()); Cmd && Cmd->GroupId >= 0)
					{
						Gids.AddUnique(Cmd->GroupId);
					}
				}
				if (Gids.Num() == 0)
				{
					for (const FAstraBattleGroup& G : Groups)
					{
						if (G.Side == EAstraSide::Mandate)
						{
							Gids.AddUnique(G.Id);
						}
					}
				}
			}
			else if (const int32 Gid = MandateGroup(GroupName); Gid != INDEX_NONE)
			{
				Gids.Add(Gid);
			}
			const int32 Other = ReinforceName.IsEmpty() ? INDEX_NONE : MandateGroup(ReinforceName);
			TArray<FString> Done;
			for (const int32 Gid : Gids)
			{
				FString D;
				if (FAstraBattleGroup* G = FindGroup(Gid))
				{
					if (FormationName == TEXT("line")) { G->Formation = EAstraFormation::Line; }
					else if (FormationName == TEXT("wedge")) { G->Formation = EAstraFormation::Wedge; }
					else if (FormationName == TEXT("column")) { G->Formation = EAstraFormation::Column; }
					else if (FormationName == TEXT("screen")) { G->Formation = EAstraFormation::Screen; }
					if (!OrderName.IsEmpty() && SetGroupOrder(Gid, OrderName, TargetId, Other, (float)DurationS, TEXT("admiral"), D))
					{
						Done.Add(D);
					}
					else if (OrderName.IsEmpty())
					{
						Done.Add(FString::Printf(TEXT("%s: %s formation"), *G->Name, *FormationName));
					}
				}
			}
			GroupOrderDone = Done.Num() ? FString::Printf(TEXT(", group orders: %s"), *FString::Join(Done, TEXT("; "))) : FString();
			if (Done.Num())
			{
				Report(FString::Printf(TEXT("sensors: the Mandate ships are changing their dispositions (%s)"), *OrderName), true);
			}
		}
	}
	// the Mandate's strike fighters: launch now, or keep them aboard
	int32 Launched = 0;
	for (FAstraSquadron& Q : Squadrons)
	{
		if (Q.Side != EAstraSide::Mandate)
		{
			continue;
		}
		if (Fighters.Equals(TEXT("launch"), ESearchCase::IgnoreCase) && Q.ToLaunch > 0)
		{
			Q.LaunchT = FMath::Min(Q.LaunchT, 2.f);
			Q.TargetId = F ? F->Id : Q.TargetId;
			Launched += Q.ToLaunch;
		}
		else if (Fighters.Equals(TEXT("hold"), ESearchCase::IgnoreCase) && Q.ToLaunch > 0)
		{
			Q.LaunchT = FMath::Max(Q.LaunchT, 90.f);
		}
	}
	// what the Aquila's sensors see of it (the fire shifting, ships swinging wide, opening or closing the range)
	const FString Who = Group.Num() > 1 ? FString(TEXT("the Mandate ships")) : KnownLabel(*Group[0]);
	const FString Them = F ? (F->bPlayer ? FString(TEXT("us")) : FString::Printf(TEXT("the %s (%s)"), *F->Name.Replace(TEXT("ASN "), TEXT("")), *F->ContactId)) : FString();
	TArray<FString> Seen;
	if (bFocusChanged && F)
	{
		Seen.Add(FString::Printf(TEXT("%s are shifting their fire onto %s"), *Who, *Them));
	}
	if (bStanceChanged)
	{
		switch (Stance)
		{
		case 1: Seen.Add(FString::Printf(TEXT("%s are closing hard, to knife-fight range"), *Who)); break;
		case 2: Seen.Add(FString::Printf(TEXT("%s are opening the range to about %.0f km, out of laser reach"), *Who, FMath::Clamp(Group[0]->RailRange * 0.9f, 5000.f, 9000.f) / 1000.f)); break;
		case 3:
		{
			const FAstraBattleShip& T = F ? *F : Ships[0];
			Seen.Add(FString::Printf(TEXT("%s are swinging wide to flank %s%s"), *Who, T.bPlayer ? TEXT("us") : *FString::Printf(TEXT("the %s"), *T.Name),
			                         !T.ShieldFacing.IsNearlyZero() ? TEXT(", away from the reinforced shield sector") : TEXT("")));
			break;
		}
		case 4: Seen.Add(FString::Printf(TEXT("%s are pulling back to screen their flagship"), *Who)); break;
		default: break;
		}
	}
	if (Launched > 0)
	{
		Seen.Add(TEXT("launch bays opening on the Mandate carrier"));
	}
	if (Seen.Num())
	{
		Report(FString::Printf(TEXT("sensors: %s"), *FString::Join(Seen, TEXT("; "))), true);
	}
	OutDetail = FString::Printf(TEXT("%d ship%s: focus %s, stance %s, missiles %s%s%s%s"), Group.Num(), Group.Num() == 1 ? TEXT("") : TEXT("s"),
	                            F ? *F->ContactId : TEXT("nearest"), Stance >= 0 ? Stances[Stance] : TEXT("unchanged"),
	                            Missiles.IsEmpty() ? TEXT("unchanged") : *Missiles.ToLower(),
	                            Salvo ? *FString::Printf(TEXT(" (%d in the salvo)"), Salvo) : TEXT(""),
	                            Launched ? *FString::Printf(TEXT(", %d fighters launching"), Launched) : TEXT(""), *(EwDone + GroupOrderDone));
	UE_LOG(LogASTRA, Log, TEXT("[Battle] Mandate tactics: %s"), *OutDetail);
	return true;
}

bool UAstraBattleSubsystem::FleetRequest(const FString& Ship, const FString& Request, const FString& Target, FString& OutDetail)
{
	const FString R = Request.ToLower();
	const bool bAll = Ship.IsEmpty() || Ship.Equals(TEXT("all"), ESearchCase::IgnoreCase);
	TArray<FAstraBattleShip*> Fleet;
	for (FAstraBattleShip& S : Ships)
	{
		if (S.bAlive && S.Side == EAstraSide::Astra && !S.bPlayer && !S.bCraft &&
		    (bAll || S.ContactId.Equals(Ship, ESearchCase::IgnoreCase) || S.Name.Contains(Ship, ESearchCase::IgnoreCase)))
		{
			Fleet.Add(&S);
		}
	}
	if (Fleet.Num() == 0)
	{
		OutDetail = bAll ? TEXT("no friendly warship in company") : FString::Printf(TEXT("no friendly warship '%s' in company"), *Ship);
		return false;
	}
	const FAstraBattleShip* T = nullptr;
	if (R == TEXT("focus_fire"))
	{
		T = FindByContact(Target.ToUpper());
		if (T && T->bAlive && T->bFog && T->Track < 2)
		{
			OutDetail = FString::Printf(TEXT("focus fire needs a track: %s is only a bearing, for the whole fleet"), *T->ContactId);
			return false;
		}
		if (!T || !T->bAlive || !T->bHostile || T->bCraft)
		{
			OutDetail = FString::Printf(TEXT("focus fire needs a hostile warship on the plot ('%s' is not one)"), *Target);
			return false;
		}
	}
	for (FAstraBattleShip* S : Fleet)
	{
		if (R == TEXT("focus_fire")) { S->OrderTarget = T->Id; S->bHoldFire = false; }
		else if (R == TEXT("engage_freely")) { S->OrderTarget = -1; S->Stance = 0; S->bHoldFire = false; }
		else if (R == TEXT("cover_us")) { S->Stance = 4; S->bHoldFire = false; }
		else if (R == TEXT("close_in")) { S->Stance = 1; S->bHoldFire = false; }
		else if (R == TEXT("stand_off")) { S->Stance = 2; S->bHoldFire = false; }
		else if (R == TEXT("hold_fire")) { S->bHoldFire = true; S->OrderTarget = -1; }
		else
		{
			OutDetail = FString::Printf(TEXT("unknown request '%s'"), *Request);
			return false;
		}
		if (!S->bHoldFire && S->Mode == EAstraShipMode::Cruise && (T || R != TEXT("engage_freely")))
		{
			S->Mode = EAstraShipMode::Attack;
		}
	}
	// the groups the request reaches follow it too (the ships' own orders above stand)
	{
		TArray<int32> Gids;
		for (const FAstraBattleShip* S : Fleet)
		{
			if (S->GroupId >= 0)
			{
				Gids.AddUnique(S->GroupId);
			}
		}
		for (const int32 Gid : Gids)
		{
			FString D;
			if (R == TEXT("focus_fire") && T)
			{
				SetGroupOrder(Gid, TEXT("attack"), T->ContactId, INDEX_NONE, 0.f, TEXT("captain"), D);
			}
			else if (R == TEXT("cover_us"))
			{
				if (FAstraBattleGroup* G = FindGroup(Gid))
				{
					G->ProtecteeId = Ships[0].Id;
				}
				SetGroupOrder(Gid, TEXT("screen"), FString(), INDEX_NONE, 0.f, TEXT("captain"), D);
			}
			else if (R == TEXT("stand_off"))
			{
				SetGroupOrder(Gid, TEXT("pin"), FString(), INDEX_NONE, 0.f, TEXT("captain"), D);
			}
			else if (R == TEXT("engage_freely") || R == TEXT("close_in"))
			{
				SetGroupOrder(Gid, TEXT("auto"), FString(), INDEX_NONE, 0.f, TEXT("captain"), D);
			}
		}
	}
	TArray<FString> Names;
	for (const FAstraBattleShip* S : Fleet) { Names.Add(S->Name); }
	const FString What = R == TEXT("focus_fire") ? FString::Printf(TEXT("shifting fire to %s"), *KnownLabel(*T))
	                   : R == TEXT("engage_freely") ? FString(TEXT("engaging targets of opportunity"))
	                   : R == TEXT("cover_us") ? FString(TEXT("moving to cover the Aquila, between us and the enemy"))
	                   : R == TEXT("close_in") ? FString(TEXT("closing to knife-fight range"))
	                   : R == TEXT("stand_off") ? FString(TEXT("holding at railgun range, out of their lasers"))
	                   : FString(TEXT("holding fire"));
	OutDetail = FString::Printf(TEXT("%s acknowledge%s: %s"), *FString::Join(Names, TEXT(" and ")), Names.Num() == 1 ? TEXT("s") : TEXT(""), *What);
	UE_LOG(LogASTRA, Log, TEXT("[Battle] fleet request: %s"), *OutDetail);
	return true;
}

bool UAstraBattleSubsystem::EnemyOrder(const FString& Order, const FString& Reason, const FString& Commander, FString& OutDetail)
{
	const FString O = Order.ToLower();
	const FString Senior = MandateCommander();
	const FString Cmd = Commander.IsEmpty() ? Senior : Commander.ToUpper();
	const FAstraBattleShip* Own = FindByContact(Cmd);
	if (!Own || !Own->bAlive)
	{
		OutDetail = FString::Printf(TEXT("%s is no longer in the fight"), *Cmd);
		return false;
	}
	const bool bGroup = Cmd == Senior;
	int32 N = 0;
	bool bWasHolding = false;
	for (FAstraBattleShip& S : Ships)
	{
		if (!S.bAlive || S.Side != EAstraSide::Mandate || !S.bHostile || (!bGroup && S.ContactId != Cmd))
		{
			continue;
		}
		++N;
		bWasHolding |= S.bHoldFire;
		if (O == TEXT("withdraw"))
		{
			S.bFleeing = true;
			S.bNegotiated = true;
			S.Mode = EAstraShipMode::Evade;
		}
		else if (O == TEXT("continue_attack"))
		{
			S.bHoldFire = false;
			S.bNegotiated = false;
			if (S.Hull >= S.HullMax * 0.25f)
			{
				S.bFleeing = false;
				S.Mode = EAstraShipMode::Attack;
			}
		}
		else if (O == TEXT("hold_fire") || O == TEXT("accept_surrender"))
		{
			S.bHoldFire = true;
			S.bNegotiated = true;
		}
	}
	bSurrenderAccepted |= (O == TEXT("accept_surrender") && bGroup);
	const FAstraBattleShip& First = *Own;
	if (O == TEXT("withdraw"))
	{
		Report(N > 1 ? FString::Printf(TEXT("sensors: the Mandate strike group is turning away — all %d ships withdrawing towards the Janus Gate"), N)
		             : FString::Printf(TEXT("sensors: %s (%s) is turning away, withdrawing towards the Janus Gate"), *First.Name, *First.ContactId));
	}
	else if (O == TEXT("hold_fire") || O == TEXT("accept_surrender"))
	{
		Report(N > 1 ? FString(TEXT("tactical: the Mandate ships have ceased fire"))
		             : FString::Printf(TEXT("tactical: %s (%s) has ceased fire"), *First.Name, *First.ContactId));
	}
	else if (O == TEXT("continue_attack") && bWasHolding)
	{
		Report(TEXT("tactical: the Mandate ships are resuming the attack"));
	}
	OutDetail = FString::Printf(TEXT("%s (%d ship%s): %s"), bGroup ? TEXT("strike group") : TEXT("own ship only"), N, N == 1 ? TEXT("") : TEXT("s"), *O);
	UE_LOG(LogASTRA, Log, TEXT("[Battle] %s orders %s (%s)"), *Cmd, *O, *Reason);
	return true;
}

void UAstraBattleSubsystem::BreakCeasefire(const FAstraBattleShip& Victim)
{
	for (FAstraBattleShip& S : Ships)
	{
		if (!S.bAlive || S.Side != EAstraSide::Mandate || !S.bNegotiated)
		{
			continue;
		}
		S.bNegotiated = false;
		S.bHoldFire = false;
		if (S.Hull >= S.HullMax * 0.25f)
		{
			S.bFleeing = false;
			S.Mode = EAstraShipMode::Attack;
			S.TargetId = Ships[0].Id;
		}
	}
	bScenarioOver = false;
	bSurrenderAccepted = false;
	bEngagementActive = true;
	Report(FString::Printf(TEXT("tactical: we fired on the %s (%s) during the ceasefire — the Mandate ships are coming about and re-engaging"),
	                       *Victim.Name, *Victim.ContactId));
	const FString Cmd = MandateCommander();
	if (!Cmd.IsEmpty())
	{
		TransmissionText = FString::Printf(TEXT("%s — the Mandate commander hails the Aquila: the Aquila fired on the %s during the ceasefire"),
		                                   *Cmd, *Victim.Name);
		TransmissionAt = Time + 4.f;
	}
}

bool UAstraBattleSubsystem::PlayerHail(const FString& ContactId, FString& OutDetail)
{
	FAstraBattleShip* T = FindByContact(ContactId);
	if (!T || !T->bAlive)
	{
		OutDetail = FString::Printf(TEXT("no contact %s to hail"), *ContactId);
		return false;
	}
	OutDetail = (T->bFog && !T->bClassified && !T->bIdentified)
		? FString::Printf(TEXT("hailing %s on all frequencies: a reply will come if anyone there wants to talk"), *T->ContactId)
		: FString::Printf(TEXT("channel open to %s%s"), *KnownLabel(*T), T->Side == EAstraSide::Mandate ? TEXT(", Mandate ship: reply expected") : TEXT(""));
	return true;
}

/** The old lump model (craft, and any ship with no class): one shield value, one hull value. */
void UAstraBattleSubsystem::ApplyHitLump(FAstraBattleShip& To, const FVector& FromDir, float Damage, const FVector& HitPos, EAstraHitKind Kind, int32 SourceId)
{
	if (!To.bAlive)
	{
		return;
	}
	To.LastHitBy = SourceId;                              // (a kill is credited to whoever struck last: the Captain's wing calls its own)
	float ToHull = Damage;
	float ShieldTook = 0.f;
	if (To.bShieldsUp && To.Shield > 0.f)
	{
		// a reinforced sector spends less shield per point stopped, the others more; power sets how much gets through
		float Cost = 1.f;
		if (!To.ShieldFacing.IsNearlyZero())
		{
			const FVector From = To.Att.UnrotateVector(-FromDir).GetSafeNormal();
			Cost = FVector::DotProduct(From, To.ShieldFacing) > 0.5f ? 0.6f : 1.5f;
		}
		const float Stop = FMath::Clamp(0.85f * (0.7f + 0.3f * To.ShieldPower), 0.5f, 0.95f);
		const float Absorbed = FMath::Min(To.Shield / Cost, Damage * Stop);
		To.Shield = FMath::Max(0.f, To.Shield - Absorbed * Cost);
		ToHull = Damage - Absorbed;
		ShieldTook = Absorbed;
		To.ShieldFlash = 1.f;
	}
	if (!To.bCraft)
	{
		// the bench's books: what struck a warship, by type and by the face it landed on, and who is concentrating fire
		const int32 T = (int32)AstraDamageTypeOf(Kind);
		const int32 F = AstraFacingOf(To.Att.UnrotateVector(-FromDir).GetSafeNormal());
		Stats.DmgIn[T] += Damage;
		Stats.DmgShield[T] += ShieldTook;
		Stats.DmgStructure[T] += ToHull;
		Stats.DmgFacing[T][F] += Damage;
		++Stats.Hits[T];
		if (const FAstraBattleShip* Src = SourceId >= 0 ? FindById(SourceId) : nullptr)
		{
			Stats.NoteFocus(Src->Side == EAstraSide::Astra ? 0 : (Src->Side == EAstraSide::Mandate ? 1 : -1), To.Id, Damage);
		}
	}
	To.Hull -= ToHull;
	if (FxOn())
	{
		FAstraFxHit H;                                    // a craft or a ship with no class: one shield, one hull
		H.Pos = HitPos;
		H.Dir = FromDir.GetSafeNormal();
		H.Kind = Kind;
		H.Damage = Damage;
		H.ShieldTook = ShieldTook;
		H.Through = ToHull;
		H.Felt = To.bCraft ? 0.f : ToHull;
		H.LocalOut = To.Att.UnrotateVector((HitPos - To.Pos).GetSafeNormal());
		H.Facing = AstraFacingOf(H.LocalOut);
		WarFX->OnHit(To, H);
	}
	else
	{
		AddFlash(HitPos, ToHull > 10.f ? 45.f : 25.f, 0.8f, To.ShieldFlash > 0.f ? FLinearColor(0.6f, 0.8f, 1.f) : FLinearColor(1.f, 0.6f, 0.3f), 80.f);
		if (ToHull > 8.f && !To.bCraft)
		{
			AddScar(To, HitPos, ToHull);             // the plating remembers it
		}
	}
	if (To.bPlayer)
	{
		Shake = FMath::Min(1.f, Shake + (ToHull > 20.f ? 0.8f : 0.35f));
		if (UAstraShipSubsystem* Ship = GetWorld()->GetSubsystem<UAstraShipSubsystem>())
		{
			Ship->AddHeat((Damage - ToHull) * 0.012f);   // what the shields stop becomes heat in the emitters
			Ship->OnHullHit(ToHull, Damage - ToHull, FromDir);
		}
		if (USoundBase* S = LoadObject<USoundBase>(nullptr, TEXT("/Game/ASTRA/Audio/SW_Impact.SW_Impact")))
		{
			UGameplayStatics::PlaySound2D(GetWorld(), S, FMath::Clamp(0.4f + ToHull / 60.f, 0.4f, 1.f));
		}
	}
	if (To.Hull <= 0.f)
	{
		if (To.bPlayer)
		{
			// the Aquila does not simply vanish: her reactor's containment fails and she is abandoned (the ship
			// subsystem runs the evacuation and calls AquilaBlasts/AquilaBreach when the reactor goes)
			To.Hull = 0.f;
			if (UAstraShipSubsystem* Ship = GetWorld()->GetSubsystem<UAstraShipSubsystem>())
			{
				Ship->ReactorFailing();
			}
			return;
		}
		Destroy(To, Kind);
	}
}

void UAstraBattleSubsystem::AquilaBlasts(const FVector& HullCentreW, const FVector& HullExtentW)
{
	FAstraBattleShip& P = Ships[0];
	P.bShieldsUp = false;
	P.Shield = 0.f;
	// explosions running along her over four seconds, the burning compartments letting go one after another
	for (int32 i = 0; i < 18; ++i)
	{
		const FVector W(HullCentreW.X + FMath::FRandRange(-0.95f, 0.9f) * HullExtentW.X, HullCentreW.Y + FMath::FRandRange(-0.75f, 0.75f) * HullExtentW.Y,
		                HullCentreW.Z + FMath::FRandRange(-0.4f, 0.8f) * HullExtentW.Z);
		if (FxOn())
		{
			WarFX->OnFlash(EAstraFxFlash::Blast, FromWorld(W), FMath::FRandRange(60.f, 160.f), 1.4f, FLinearColor(1.f, 0.55f, 0.18f), 320.f, P.Vel, FMath::FRandRange(0.f, 3.6f));
			continue;
		}
		AddFlash(FromWorld(W), FMath::FRandRange(60.f, 160.f), FMath::FRandRange(0.9f, 1.8f), FLinearColor(1.f, FMath::FRandRange(0.4f, 0.7f), 0.18f), 320.f);
		Flashes.Last().Age = -FMath::FRandRange(0.f, 3.6f);
	}
}

FString UAstraBattleSubsystem::ForcesLine(bool bAstra) const
{
	TArray<FString> Out;
	for (const FAstraBattleShip& S : Ships)
	{
		if (!S.bPlayer && !S.bCraft && S.bAlive && !S.bDerelict && (S.Side == EAstraSide::Astra) == bAstra && (bAstra || S.Side == EAstraSide::Mandate))
		{
			Out.Add(FString::Printf(TEXT("%s (%s, %s)"), *S.Name, *S.Class, *S.ContactId));
		}
	}
	return FString::Join(Out, TEXT(", "));
}

void UAstraBattleSubsystem::AquilaBreach(const FVector& ReactorW)
{
	FAstraBattleShip& P = Ships[0];
	if (!P.bAlive)
	{
		return;
	}
	P.bAlive = false;
	P.Mode = EAstraShipMode::Dead;
	P.Hull = 0.f;
	P.Vel *= 0.2f;
	// the reactor, aft: a ship's death centred on it (the flash of the core letting go, the fireball, the shockwave ring,
	// blasts along her axis, the debris); her own actor is the level's hull, which the ship subsystem darkens. Pos is
	// the frame's origin: moved to the reactor for the explosion only, and put back
	if (FxOn())
	{
		WarFX->OnAquilaBreach(FromWorld(ReactorW), 240.f, P.Vel);              // the war's effects: the flash, the ball of fire, the wave, the debris
		UE_LOG(LogASTRA, Log, TEXT("[Battle] the Aquila's reactor breached"));
		return;
	}
	const FVector Centre = P.Pos;
	const float R0 = P.Radius;
	P.Pos = FromWorld(ReactorW);
	P.Radius = 240.f;
	Explode(P);
	AddFlash(P.Pos, 700.f, 0.9f, FLinearColor(1.f, 0.97f, 0.9f), 1200.f);    // the first instant: white, huge, gone
	P.Pos = Centre;
	P.Radius = R0;
	UE_LOG(LogASTRA, Log, TEXT("[Battle] the Aquila's reactor breached"));
}

void UAstraBattleSubsystem::Destroy(FAstraBattleShip& S, EAstraHitKind Cause, EAstraFate How, uint8 Section)
{
	{
		const int32 Side = S.Side == EAstraSide::Astra ? 0 : (S.Side == EAstraSide::Mandate ? 1 : -1);
		if (Side >= 0 && !S.bPlayer)
		{
			if (S.bCraft)
			{
				const EAstraCraftFate Fate = Cause == EAstraHitKind::PointDefence ? EAstraCraftFate::PointDefence
				                           : Cause == EAstraHitKind::Cannon ? EAstraCraftFate::CraftGuns
				                           : (Cause == EAstraHitKind::Missile || Cause == EAstraHitKind::Torpedo || Cause == EAstraHitKind::Rocket) ? EAstraCraftFate::Missile
				                           : EAstraCraftFate::Other;
				++Stats.CraftLost[Side][(int32)Fate];
			}
			else if (!S.bGhost)
			{
				++Stats.ShipFate[Side][(int32)How];
				Stats.LostWhileRetreating[Side] += S.bFleeing ? 1 : 0;
			}
		}
	}
	const bool bWasCommander = S.Side == EAstraSide::Mandate && S.bHostile && MandateCommander() == S.ContactId;
	S.bAlive = false;
	S.Mode = EAstraShipMode::Dead;
	S.DeathHow = How;
	if (!S.bCraft && !S.bGhost && !S.bPlayer && !S.bDisabled)                 // (a hulk shot to pieces was reported when it went dark)
	{
		NoteGroupLoss(S, How == EAstraFate::ReactorBreach ? TEXT("the reactor went") : (How == EAstraFate::Breakup ? TEXT("the hull broke apart") : TEXT("destroyed")));
	}
	const float Blast = How == EAstraFate::ReactorBreach ? 1.8f : 1.f;    // a reactor going takes the whole ship in a bigger ball of fire
	// the war's effects draw the death (the hull's pieces, the fireball, the wave); where they cannot, the older explosion does
	const bool bEvent = !S.bCraft && !S.bGhost && !S.bPlayer;
	FAstraDeathEvent E;                          // for the visuals: how it went, where it broke
	if (bEvent)
	{
		{
			E.Time = Time;
			E.ShipId = S.Id;
			E.ContactId = S.ContactId;
			E.Name = S.Name;
			E.Class = S.Class;
			E.How = How;
			E.Section = Section;
			E.Pos = S.Pos;
			E.Vel = S.Vel;
			E.Att = S.Att;
			E.Radius = S.Radius;
			E.CutBowX = S.Box.CutBow;
			E.CutSternX = S.Box.CutStern;
			E.bAstra = S.Side == EAstraSide::Astra;
			if (How == EAstraFate::Breakup)
			{
				E.BreakAxis = S.Att.GetForwardVector();
				E.BreakPoint = S.Pos + E.BreakAxis * BreakX(S, Section);                // on the true cut of the section that lets go
				E.BreakSpeed = FMath::FRandRange(8.f, 25.f);
			}
		}
	}
	bool bFxDone = false;
	if (FxOn())
	{
		if (S.bCraft)
		{
			WarFX->OnCraftDestroyed(S);
			bFxDone = true;
		}
		else if (bEvent)
		{
			bFxDone = WarFX->OnShipDestroyed(S, E);
		}
	}
	if (!bFxDone)
	{
		AddFlash(S.Pos, S.Radius * 1.4f * Blast, 2.6f, FLinearColor(1.f, 0.5f, 0.2f), 160.f, EAstraFxFlash::Blast);   // fireball: the gas cloud expands and thins
		AddFlash(S.Pos, S.Radius * 0.9f * Blast, 1.1f, FLinearColor(1.f, 0.92f, 0.75f), 600.f);                       // the flash of the reactor letting go
		if (!S.bCraft)
		{
			Explode(S);   // takes over the ship's actor as the hulk
		}
	}
	if (bEvent)
	{
		DeathEvents.Add(E);
		if (DeathEvents.Num() > 64)
		{
			DeathEvents.RemoveAt(0);
		}
	}
	if (S.Actor) { S.Actor->Destroy(); S.Actor = nullptr; }
	if (S.ShieldBubble) { S.ShieldBubble->Destroy(); S.ShieldBubble = nullptr; }
	if (S.DriveFlare) { S.DriveFlare->Destroy(); S.DriveFlare = nullptr; }
	if (S.bPiloted)
	{
		bPilotDown = true;
		if (Squadrons.IsValidIndex(S.Squadron))
		{
			--Squadrons[S.Squadron].Total;
		}
		Report(TEXT("flight: Eagle is down — the Captain's Falcon was destroyed, the Captain ejected; a Wasp is going out for the pod"), true);
		EndEagleWing();                                                       // (his wing has lost its leader: it comes home)
	}
	else if (S.bCraft)
	{
		if (S.Side == EAstraSide::Mandate && !S.bGhost)
		{
			// a Harpy splashed by one of the Captain's wing: that wingman calls it (the squadron's own count is told as before)
			const FAstraBattleShip* Killer = S.LastHitBy >= 0 ? FindById(S.LastHitBy) : nullptr;
			if (Killer && Killer->bCraft && Killer->Side == EAstraSide::Astra && !Killer->Radio.IsEmpty())
			{
				Report(FString::Printf(TEXT("flight: %s splashed a Harpy"), *Killer->Radio));
			}
		}
		if (Squadrons.IsValidIndex(S.Squadron))
		{
			FAstraSquadron& Q = Squadrons[S.Squadron];
			--Q.Total;
			++Q.LostSinceReport;
			// a manned aircraft of ours: somebody was flying it
			if (Q.Side == EAstraSide::Astra && Q.Kind != 2)
			{
				if (!S.Radio.IsEmpty())
				{
					// one of the Captain's wing (the flight net's own people, not the roster's): told now by its radio name, not in the squadron's report twelve
					// seconds later; the pilot ejects and search and rescue picks them up (the aircraft is a real loss: Total went down above)
					--Q.LostSinceReport;
					Report(FString::Printf(TEXT("flight: %s is down — the pilot ejected, search and rescue is on the way"), *S.Radio));
				}
				else if (UAstraShipSubsystem* Ship = GetWorld()->GetSubsystem<UAstraShipSubsystem>())
				{
					const FString Who = Ship->AircrewLost();
					if (!Who.IsEmpty())
					{
						Q.LostCrew.Add(Who);
					}
				}
			}
		}
	}
	else if (!S.bPlayer)
	{
		Report(FString::Printf(TEXT("tactical: %s %s"), (!S.bFog || S.bIdentified)
			? *FString::Printf(TEXT("%s (%s, %s)"), *S.Name, *S.ContactId, *S.Class) : *KnownLabel(S),
			How == EAstraFate::ReactorBreach ? TEXT("destroyed: her reactor breached")
			: How == EAstraFate::Breakup ? *FString::Printf(TEXT("destroyed: the hull broke apart at the %s"), AstraWar::SectionName(Section)) : TEXT("destroyed")));
		if (S.Side == EAstraSide::Astra)
		{
			LastWreckPos = S.Pos;
			LastWreckName = S.Name;
		}
	}
	if (bWasCommander)
	{
		OnCommanderLost(S, TEXT("was destroyed"));
	}
}

void UAstraBattleSubsystem::OnCommanderLost(const FAstraBattleShip& Old, const TCHAR* How)
{
	if (!bEngagementActive)
	{
		return;
	}
	if (const FAstraBattleShip* Next = FindByContact(MandateCommander()))
	{
		TransmissionText = FString::Printf(TEXT("%s — the %s (%s) now leads what is left of the strike group, because the %s %s; it hails the Aquila"),
		                                   *Next->ContactId, *Next->Name, *Next->Class, *Old.Name, How);
		TransmissionAt = Time + 9.f;
	}
}

void UAstraBattleSubsystem::TickProjectiles(float Dt)
{
	for (FAstraProjectile& Pr : Projectiles)
	{
		if (Pr.bDead)
		{
			continue;
		}
		Pr.Life -= Dt;
		FAstraBattleShip* T = FindById(Pr.Target);
		if (Pr.Kind == EAstraProjKind::Missile && T && T->bPlayer && DecoyT > 0.f && !Pr.bDecoyChecked
		    && FVector::Dist(Pr.Pos, T->Pos) < 7.f * OneKm)
		{
			// the terminal run through the Aquila's decoys: about half the seekers take the bait and fly on blind
			Pr.bDecoyChecked = true;
			if (FMath::FRand() < 0.5f)
			{
				Pr.Target = -1;
				T = nullptr;
				++DecoysSeduced;
				++Stats.MissilesDecoyed[1];
			}
		}
		if (Pr.Kind == EAstraProjKind::Missile && T && T->bAlive)
		{
			// guided: accelerate towards an intercept point
			const FVector To = T->Pos + T->Vel * 2.0 - Pr.Pos;
			Pr.Vel += (To.GetSafeNormal() * Pr.MaxSpeed - Pr.Vel).GetClampedToMaxSize(900.f * Dt);
		}
		const FVector Prev = Pr.Pos;
		Pr.Pos += Pr.Vel * Dt;
		// swept hit test against the target (and anyone in the way for slugs)
		for (FAstraBattleShip& S : Ships)
		{
			if (!S.bAlive || S.Id == Pr.Owner)
			{
				continue;
			}
			if (S.Id != Pr.Target && Pr.Kind == EAstraProjKind::Missile)
			{
				continue;
			}
			FVector Entry;
			if (HullSweep(S, Prev, Pr.Pos, Entry))
			{
				// it strikes where its path enters the hull (the box of the mesh's own measures), not where it comes closest to the
				// centre: the point that says which face and which section of the hull it lands on
				const FVector Dir = (Pr.Pos - Prev).GetSafeNormal();
				ApplyHit(S, Dir, Pr.Damage, Entry, Pr.HitKind, Pr.Owner);
				Pr.bDead = true;
				break;
			}
		}
		if (Pr.Life <= 0.f)
		{
			Pr.bDead = true;
		}
	}
	for (int32 i = Projectiles.Num() - 1; i >= 0; --i)
	{
		if (Projectiles[i].bDead)
		{
			if (Projectiles[i].Actor) { Projectiles[i].Actor->Destroy(); }
			if (Projectiles[i].Trail) { Projectiles[i].Trail->Destroy(); }
			Projectiles.RemoveAtSwap(i);
		}
	}
}

void UAstraBattleSubsystem::AddScar(const FAstraBattleShip& S, const FVector& SystemHit, float Damage)
{
	UWorld* World = GetWorld();
	UMaterialInterface* Mat = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/ASTRA/Materials/M_FX_ScorchDecal.M_FX_ScorchDecal"));
	if (!World || !Mat)
	{
		return;
	}
	const FVector W = ToWorld(SystemHit);
	AActor* On = nullptr;
	FVector Loc, N;
	float Depth = 1000.f;
	if (S.bPlayer)
	{
		// the Aquila's hull has its collision: from outside the hit, in towards her keel line, to the plating it struck
		AActor* Hull = nullptr;
		for (TActorIterator<AStaticMeshActor> It(World); It; ++It)
		{
			const UStaticMeshComponent* C = It->GetStaticMeshComponent();
			if (C && C->GetStaticMesh() && C->GetStaticMesh()->GetName() == TEXT("SM_SHIP_ASTRA_Aquila") && !It->ActorHasTag(TEXT("ASTRA.Interior")))
			{
				Hull = *It;
				break;
			}
		}
		if (!Hull)
		{
			return;
		}
		FVector C, E;
		Hull->GetActorBounds(false, C, E);
		const FVector Axis(FMath::Clamp(W.X, C.X - E.X, C.X + E.X), C.Y, C.Z);
		const FVector Out = (W - Axis).GetSafeNormal();
		FHitResult Hit;
		FCollisionQueryParams Q(SCENE_QUERY_STAT(AstraScar), true);
		// the hit point may lie inside her outline (the battle's hit sphere is wider than her beam): start well outside it
		const FVector From = Axis + Out * (E.Y + E.Z + 5000.f);
		if (Out.IsNearlyZero() || !World->LineTraceSingleByChannel(Hit, From, Axis, ECC_Visibility, Q) || !Hit.GetActor())
		{
			return;
		}
		On = Hit.GetActor();
		Loc = Hit.ImpactPoint;
		N = Hit.ImpactNormal;
	}
	else
	{
		// the others have no collision: the scar is projected from the hit in towards the centre of the ship
		On = S.Actor;
		if (!On)
		{
			return;
		}
		const FVector Centre = On->GetActorLocation();
		N = (W - Centre).GetSafeNormal();
		Loc = W;
		Depth = FMath::Max(1000.f, (W - Centre).Size());
	}
	// twenty scars at most on one hull: the oldest goes
	int32 OnThis = 0;
	for (const FAstraScar& X : Scars) { OnThis += X.On.Get() == On ? 1 : 0; }
	if (OnThis >= 20)
	{
		const int32 Oldest = Scars.IndexOfByPredicate([On](const FAstraScar& X) { return X.On.Get() == On; });
		if (Scars.IsValidIndex(Oldest))
		{
			if (UDecalComponent* D = Scars[Oldest].Decal.Get()) { D->DestroyComponent(); }
			Scars.RemoveAt(Oldest);
		}
	}
	UDecalComponent* D = NewObject<UDecalComponent>(On);
	D->SetupAttachment(On->GetRootComponent());
	D->SetUsingAbsoluteScale(true);
	D->RegisterComponent();
	UMaterialInstanceDynamic* M = UMaterialInstanceDynamic::Create(Mat, D);
	M->SetScalarParameterValue(TEXT("Heat"), 1.f);
	M->SetScalarParameterValue(TEXT("Breach"), Damage > 45.f ? 1.f : 0.f);
	M->SetScalarParameterValue(TEXT("Fade"), 1.f);
	D->SetDecalMaterial(M);
	const float Half = FMath::Clamp(Damage * 28.f, 600.f, 2600.f);           // 12-52 m across
	D->DecalSize = FVector(Depth, Half, Half);
	FRotator R = FRotationMatrix::MakeFromX(-N).Rotator();                   // it projects along X, into the plating
	R.Roll = FMath::FRandRange(0.f, 360.f);
	D->SetWorldLocationAndRotation(Loc, R);
	D->SetFadeScreenSize(0.0004f);
	FAstraScar X;
	X.Decal = D;
	X.Mid = M;
	X.On = On;
	Scars.Add(X);
}

void UAstraBattleSubsystem::TickScars(float Dt)
{
	for (int32 i = Scars.Num() - 1; i >= 0; --i)
	{
		FAstraScar& X = Scars[i];
		if (!X.Decal.IsValid() || !X.Mid.IsValid())
		{
			Scars.RemoveAtSwap(i);
			continue;
		}
		X.Heat = FMath::Max(0.f, X.Heat - Dt / 50.f);                         // the embers die in under a minute
		if (FMath::Abs(X.Heat - X.Shown) > 0.02f)
		{
			X.Shown = X.Heat;
			X.Mid->SetScalarParameterValue(TEXT("Heat"), X.Heat);
		}
	}
}

bool UAstraBattleSubsystem::LaunchDecoys(FString& OutDetail)
{
	if (Ships.Num() == 0 || !Ships[0].bAlive)
	{
		OutDetail = TEXT("no ship to launch from");
		return false;
	}
	if (DecoyT > 0.f)
	{
		OutDetail = FString::Printf(TEXT("decoys already out: %.0f s left"), DecoyT);
		return true;
	}
	if (PlayerDecoys <= 0)
	{
		OutDetail = TEXT("no decoys left aboard (a resupply brings more)");
		return false;
	}
	PlayerDecoys = FMath::Max(0, PlayerDecoys - 2);
	DecoyT = 18.f;
	// the flares and the chaff blooms drifting off her flanks: bright, then fading
	const FAstraBattleShip& P = Ships[0];
	for (int32 i = 0; i < 10; ++i)
	{
		const FVector Out = (P.Att.GetRightVector() * (i % 2 ? 1.f : -1.f) + FMath::VRand() * 0.6f).GetSafeNormal();
		if (FxOn())
		{
			WarFX->OnFlash(EAstraFxFlash::Decoy, P.Pos + Out * P.Radius * 1.1f, FMath::FRandRange(6.f, 14.f), 18.f, FLinearColor(1.f, 0.8f, 0.55f), 400.f,
			               P.Vel + Out * FMath::FRandRange(25.f, 60.f), FMath::FRandRange(0.f, 1.2f));
			continue;
		}
		AddFlash(P.Pos + Out * P.Radius * 1.1f, FMath::FRandRange(6.f, 14.f), 18.f, FLinearColor(1.f, 0.8f, 0.55f), 400.f);
		Flashes.Last().Vel = P.Vel + Out * FMath::FRandRange(25.f, 60.f);
		Flashes.Last().Age = -FMath::FRandRange(0.f, 1.2f);
	}
	HullSound(TEXT("SW_PD_Burst"), 0.5f, 0.2f);
	OutDetail = FString::Printf(TEXT("decoys away: flares and chaff for 18 s, %d left aboard"), PlayerDecoys);
	return true;
}

bool UAstraBattleSubsystem::FxOn() const
{
	return WarFX && WarFX->IsActive();
}

void UAstraBattleSubsystem::AddFlash(const FVector& Pos, float Size, float Life, const FLinearColor& Color, float Intensity)
{
	AddFlash(Pos, Size, Life, Color, Intensity, EAstraFxFlash::Spark);
}

void UAstraBattleSubsystem::AddFlash(const FVector& Pos, float Size, float Life, const FLinearColor& Color, float Intensity, EAstraFxFlash Kind)
{
	if (FxOn())
	{
		WarFX->OnFlash(Kind, Pos, Size, Life, Color, Intensity);
		return;
	}
	FAstraFlash F;
	F.Pos = Pos;
	F.Size = Size;
	F.Life = Life;
	F.Color = Color;
	F.Intensity = Intensity;
	if (UWorld* World = GetWorld(); World && SphereMesh && ShellMat && FApp::CanEverRender())
	{
		FActorSpawnParameters P;
		P.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
		F.Actor = World->SpawnActor<AStaticMeshActor>(FVector::ZeroVector, FRotator::ZeroRotator, P);
		F.Actor->SetMobility(EComponentMobility::Movable);
		UStaticMeshComponent* C = F.Actor->GetStaticMeshComponent();
		C->SetStaticMesh(SphereMesh);
		C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		C->SetCastShadow(false);
		// fireballs get the soft, billowing blast material; small hit sparks stay simple glows
		F.MID = C->CreateAndSetMaterialInstanceDynamicFromMaterial(0, (Size >= 40.f && BlastMat) ? BlastMat : GlowMat);
		F.MID->SetVectorParameterValue(TEXT("Color"), Color);
		F.MID->SetScalarParameterValue(TEXT("Intensity"), Intensity);
	}
	Flashes.Add(F);
}

void UAstraBattleSubsystem::AddBeam(const FVector& A, const FVector& B, float Life, const FLinearColor& Color)
{
	AddBeam(A, B, Life, Color, EAstraFxShot::Cannon);
}

void UAstraBattleSubsystem::AddBeam(const FVector& A, const FVector& B, float Life, const FLinearColor& Color, EAstraFxShot Kind, int32 FromId, int32 ToId)
{
	if (FxOn())
	{
		WarFX->OnBeam(Kind, A, B, Life, Color, FromId, ToId);
		return;
	}
	FAstraFlash F;
	F.Pos = A;
	F.BeamTo = B;
	F.bBeam = true;
	F.Life = Life;
	F.Color = Color;
	F.Intensity = 300.f;
	if (UWorld* World = GetWorld(); World && CylinderMesh && GlowMat && FApp::CanEverRender())
	{
		FActorSpawnParameters P;
		P.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
		F.Actor = World->SpawnActor<AStaticMeshActor>(FVector::ZeroVector, FRotator::ZeroRotator, P);
		F.Actor->SetMobility(EComponentMobility::Movable);
		UStaticMeshComponent* C = F.Actor->GetStaticMeshComponent();
		C->SetStaticMesh(CylinderMesh);
		C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		C->SetCastShadow(false);
		F.MID = C->CreateAndSetMaterialInstanceDynamicFromMaterial(0, GlowMat);
		F.MID->SetVectorParameterValue(TEXT("Color"), Color);
		F.MID->SetScalarParameterValue(TEXT("Intensity"), F.Intensity);
	}
	Flashes.Add(F);
}

void UAstraBattleSubsystem::TickFlashes(float Dt)
{
	TickWrecks(Dt);
	for (int32 i = Flashes.Num() - 1; i >= 0; --i)
	{
		FAstraFlash& F = Flashes[i];
		F.Age += Dt;
		F.Pos += F.Vel * Dt;
		if (F.Age >= F.Life)
		{
			if (F.Actor) { F.Actor->Destroy(); }
			Flashes.RemoveAtSwap(i);
		}
	}
}

// ------------------------------------------------------------------------------------------------------ visuals
void UAstraBattleSubsystem::SyncVisuals()
{
	if (PilotedId >= 0)
	{
		const FAstraBattleShip* P = FindById(PilotedId);
		if (AActor* Pawn = PilotActor.Get(); Pawn && P && P->bAlive)
		{
			Pawn->SetActorLocationAndRotation(ToWorld(P->Pos), ToWorldRot(P->Att));
		}
	}
	FVector Eye = FVector::ZeroVector;   // the camera (the bridge, the hangar, the lift...)
	if (const APlayerCameraManager* Cam = UGameplayStatics::GetPlayerCameraManager(GetWorld(), 0))
	{
		Eye = Cam->GetCameraLocation();
	}
	for (FAstraBattleShip& S : Ships)
	{
		if (!S.bAlive || !S.Actor)
		{
			continue;
		}
		const FVector W = ToWorld(S.Pos);
		const FRotator R = ToWorldRot(S.Att).Rotator();
		S.Actor->SetActorLocationAndRotation(W, R);
		if (S.DriveFlare)
		{
			// the plume at the stern, never smaller than ~0.25 degrees from where the Captain stands (a torch drive
			// is visible from far away); a soft ball of light that fades to nothing at its rim
			const FVector Stern = ToWorld(S.Pos - S.Att.GetForwardVector() * S.Radius * 1.05);
			const float Dist = FVector::Dist(Stern, Eye) / 100.f;
			const float Speed = S.Vel.Size();
			const float Throttle = FMath::Clamp(Speed / 400.f, 0.15f, 1.f);
			S.DriveFlare->SetActorLocation(Stern);
			S.DriveFlare->SetActorScale3D(FVector(FMath::Max(S.Radius * 0.16f, Dist * 0.0065f) * Throttle));
		}
		if (S.ShieldBubble && S.ShieldMID)
		{
			const bool bShow = S.ShieldFlash > 0.01f;
			S.ShieldBubble->SetActorHiddenInGame(!bShow);
			if (bShow)
			{
				S.ShieldBubble->SetActorLocationAndRotation(W, R);
				S.ShieldMID->SetScalarParameterValue(TEXT("Fade"), S.ShieldFlash);
				S.ShieldMID->SetScalarParameterValue(TEXT("Intensity"), 30.f);
			}
		}
	}
	for (FAstraProjectile& Pr : Projectiles)
	{
		if (!Pr.Actor)
		{
			continue;
		}
		const FVector W = ToWorld(Pr.Pos);
		if (Pr.Kind == EAstraProjKind::Rail)
		{
			// the cylinder's axis is Z: align it with the (world-space) velocity
			const FVector Dir = Ships[0].Att.UnrotateVector((Pr.Vel - Ships[0].Vel).GetSafeNormal());
			Pr.Actor->SetActorLocationAndRotation(W, FRotationMatrix::MakeFromZ(Dir).Rotator());
		}
		else
		{
			Pr.Actor->SetActorLocation(W);
			if (Pr.Trail)
			{
				// a streak behind the missile along its path (relative to the Aquila, like everything drawn)
				const FVector Rel = Pr.Vel - Ships[0].Vel;
				const float Len = FMath::Clamp(Rel.Size() * 0.18f, 20.f, 260.f);   // m
				const FVector Dir = Ships[0].Att.UnrotateVector(Rel.GetSafeNormal());
				Pr.Trail->SetActorLocationAndRotation(W - Dir * Len * 50.f, FRotationMatrix::MakeFromZ(Dir).Rotator());
				Pr.Trail->SetActorScale3D(FVector(Pr.bTorpedo ? 2.2f : 1.4f, Pr.bTorpedo ? 2.2f : 1.4f, Len / 100.f));
			}
		}
	}
	for (FAstraFlash& F : Flashes)
	{
		if (!F.Actor)
		{
			continue;
		}
		if (F.Age < 0.f)
		{
			F.Actor->SetActorHiddenInGame(true);   // a delayed blast (secondary explosions)
			continue;
		}
		F.Actor->SetActorHiddenInGame(false);
		const float K = F.Age / FMath::Max(0.01f, F.Life);
		if (F.bRing)
		{
			F.Actor->SetActorLocationAndRotation(ToWorld(F.Pos), ToWorldRot(F.Rot));
			const float R = F.Size * (0.15f + 0.85f * FMath::Sqrt(K));   // ring mesh radius is 1 m
			F.Actor->SetActorScale3D(FVector(R, R, R * 0.6f));
		}
		else if (F.bBeam)
		{
			const FVector A = ToWorld(F.Pos), B = ToWorld(F.BeamTo);
			const FVector D = B - A;
			F.Actor->SetActorLocationAndRotation((A + B) * 0.5, FRotationMatrix::MakeFromZ(D.GetSafeNormal()).Rotator());
			F.Actor->SetActorScale3D(FVector(1.5f, 1.5f, D.Size() / 100.f));
		}
		else
		{
			F.Actor->SetActorLocation(ToWorld(F.Pos));
			F.Actor->SetActorScale3D(FVector(F.Size * (0.4f + 1.4f * FMath::Sqrt(K))));   // metres -> sphere scale (100 cm mesh)
		}
		if (F.MID)
		{
			F.MID->SetScalarParameterValue(TEXT("Fade"), FMath::Pow(1.f - K, 3.5f));
		}
	}
}

float UAstraBattleSubsystem::ConsumeShake(float DeltaTime)
{
	const float S = Shake;
	Shake = FMath::Max(0.f, Shake - DeltaTime * 1.2f);
	return S;
}

TSharedRef<FJsonObject> UAstraBattleSubsystem::MandateViewJson() const
{
	TSharedRef<FJsonObject> V = MakeShared<FJsonObject>();
	TArray<TSharedPtr<FJsonValue>> Own, Foe;
	const FString Cmd = MandateCommander();
	const FVector Aquila = Ships.Num() ? Ships[0].Pos : FVector::ZeroVector;
	for (const FAstraBattleShip& S : Ships)
	{
		if (S.bCraft)
		{
			continue;   // fighters are summarised below
		}
		TSharedRef<FJsonObject> O = MakeShared<FJsonObject>();
		O->SetStringField(TEXT("name"), S.Name);
		O->SetStringField(TEXT("class"), S.Class);
		if (S.Side == EAstraSide::Mandate)
		{
			O->SetStringField(TEXT("id"), S.ContactId);
			if (!S.bAlive)
			{
				O->SetStringField(TEXT("state"), S.Mode == EAstraShipMode::Dead ? TEXT("destroyed with all hands") : TEXT("jumped out of the system"));
			}
			else
			{
				O->SetStringField(TEXT("state"), S.bDisabled ? TEXT("disabled: no power, drifting, out of the fight")
				                                 : S.bFleeing ? (S.bNegotiated ? TEXT("withdrawing, as ordered") : TEXT("breaking off: too damaged to keep fighting"))
				                                 : S.bHoldFire ? TEXT("holding fire, as ordered")
				                                 : S.bCold ? TEXT("running silent, waiting")
				                                 : S.bHostile ? TEXT("attacking") : TEXT("standing by"));
				O->SetNumberField(TEXT("hull_pct"), Pct(S.Hull, S.HullMax));
				O->SetNumberField(TEXT("shields_pct"), Pct(S.Shield, S.ShieldMax));
				O->SetNumberField(TEXT("missiles_left"), S.Missiles);
				O->SetNumberField(TEXT("range_to_aquila_km"), FMath::RoundToDouble(FVector::Dist(S.Pos, Aquila) / 100.0) / 10.0);
				if (const FAstraBattleShip* T = FindById(S.TargetId); T && T->bAlive && !S.bFleeing)
				{
					O->SetStringField(TEXT("engaging"), T->bPlayer ? FString(TEXT("AQUILA")) : T->ContactId);
					O->SetNumberField(TEXT("range_to_target_km"), FMath::RoundToDouble(FVector::Dist(S.Pos, T->Pos) / 100.0) / 10.0);
				}
				static const TCHAR* StanceNames[] = {TEXT("standard"), TEXT("close"), TEXT("standoff"), TEXT("flank"), TEXT("screen")};
				O->SetStringField(TEXT("stance"), StanceNames[FMath::Min<int32>(S.Stance, 4)]);
				if (S.bConserve) { O->SetBoolField(TEXT("conserving_missiles"), true); }
				if (S.bFog)
				{
					// what the ASTRA can see of it, as far as its own warning receivers can tell
					O->SetStringField(TEXT("emissions"), S.bJamming ? TEXT("jamming the ASTRA radar (they see your bearing, not your range)")
					                                     : S.bDark ? TEXT("running dark (hard to find at range)")
					                                               : TEXT("drive and sensors lit (visible at range)"));
					O->SetStringField(TEXT("ew_orders"), S.EwMode == 1 ? TEXT("jam") : (S.EwMode == 2 ? TEXT("quiet") : TEXT("auto: jam once found")));
					if (S.Decoys > 0) { O->SetNumberField(TEXT("decoys_aboard"), S.Decoys); }
					if (S.bIlluminated) { O->SetBoolField(TEXT("astra_radar_painting_you"), true); }
					// the ship's EW officer: what the ASTRA can know of it now, and what would change that
					const float RKm = FVector::Dist(S.Pos, Aquila) / OneKm;
					O->SetStringField(TEXT("ew_officer"),
						S.bJamming ? TEXT("jamming: they hold our bearing, not our range; inside 12 km their radar burns through")
						: (S.bIlluminated && RKm <= 12.f) ? TEXT("their radar paints us at close range: they see everything — jamming, going quiet or decoys change nothing here")
						: S.bIlluminated ? TEXT("their radar paints us: they have our range and class — going quiet hides nothing now; only jamming takes our range away (beyond 12 km); decoys would be unmasked at once")
						: S.bDark ? TEXT("dark and outside their radar: at most a faint bearing, likely nothing — decoys now would draw their eyes elsewhere")
						          : TEXT("outside their radar but lit: they may hold our bearing from the drive — going quiet would fade us, decoys would muddle their picture"));
				}
				if (S.ContactId == Cmd)
				{
					O->SetBoolField(TEXT("commands_the_strike_group"), true);
				}
			}
			Own.Add(MakeShared<FJsonValueObject>(O));
		}
		else if (S.Side == EAstraSide::Astra && S.bAlive && !S.bCraft)
		{
			O->SetStringField(TEXT("id"), S.bPlayer ? FString(TEXT("AQUILA")) : S.ContactId);
			if (S.bPlayer)
			{
				O->SetStringField(TEXT("name"), TEXT("ASN Aquila (the carrier cruiser, the ship on the channel)"));
				if (!bPlayerTracked)
				{
					O->SetStringField(TEXT("track"), TEXT("LOST: she has gone quiet; your ships are sweeping her last known position"));
					Foe.Add(MakeShared<FJsonValueObject>(O));
					continue;
				}
			}
			O->SetNumberField(TEXT("hull_pct"), Pct(S.Hull, S.HullMax));
			O->SetNumberField(TEXT("shields_pct"), Pct(S.Shield, S.ShieldMax));
			// what their sensors read of the shield: a reinforced sector is stronger, the others weaker
			const FVector Fz = S.ShieldFacing;
			O->SetStringField(TEXT("shields"), Fz.IsNearlyZero() ? TEXT("balanced")
			                  : FString::Printf(TEXT("reinforced %s (the other sectors weaker)"), Fz.X > 0.5f ? TEXT("forward") : Fz.X < -0.5f ? TEXT("aft")
			                                    : Fz.Y > 0.5f ? TEXT("starboard") : Fz.Y < -0.5f ? TEXT("port") : Fz.Z > 0.5f ? TEXT("dorsal") : TEXT("ventral")));
			if (const FAstraBattleShip* Flag = FindByContact(Cmd); Flag && Flag->bAlive)
			{
				O->SetNumberField(TEXT("range_from_your_flagship_km"), FMath::RoundToDouble(FVector::Dist(S.Pos, Flag->Pos) / 100.0) / 10.0);
			}
			Foe.Add(MakeShared<FJsonValueObject>(O));
		}
	}
	V->SetArrayField(TEXT("your_ships"), Own);
	V->SetArrayField(TEXT("astra_ships"), Foe);
	int32 GhostsFlying = 0;
	for (const FAstraBattleShip& S : Ships)
	{
		GhostsFlying += (S.bGhost && S.bAlive) ? 1 : 0;
	}
	if (GhostsFlying)
	{
		V->SetNumberField(TEXT("decoys_flying"), GhostsFlying);   // (those the ASTRA unmask stop transmitting: the count drops)
	}
	int32 Craft = 0;
	for (const FAstraBattleShip& S : Ships)
	{
		Craft += (S.bCraft && S.bAlive && S.Side == EAstraSide::Astra) ? 1 : 0;
	}
	V->SetNumberField(TEXT("astra_fighters_and_drones_airborne"), Craft);
	int32 Ours = 0;
	for (const FAstraBattleShip& S : Ships)
	{
		Ours += (S.bCraft && S.bAlive && S.Side == EAstraSide::Mandate) ? 1 : 0;
	}
	V->SetNumberField(TEXT("your_strike_fighters_airborne"), Ours);
	int32 Ready = 0;
	for (const FAstraSquadron& Q : Squadrons)
	{
		Ready += Q.Side == EAstraSide::Mandate ? Q.ToLaunch : 0;
	}
	V->SetNumberField(TEXT("your_strike_fighters_still_aboard"), Ready);
	// the battle groups the ships fight in (docs/GUERRA.md: the orders menu: `order`, `target`, `group`, `formation`)
	{
		static const TCHAR* const States[] = {TEXT("engaged"), TEXT("withdrawing"), TEXT("regrouping")};
		static const TCHAR* const Orders[] = {TEXT("auto"), TEXT("attack"), TEXT("pin"), TEXT("flank_left"), TEXT("flank_right"), TEXT("screen"), TEXT("withdraw"),
		                                      TEXT("regroup"), TEXT("reinforce"), TEXT("hold")};
		static const TCHAR* const Forms[] = {TEXT("line"), TEXT("wedge"), TEXT("column"), TEXT("screen")};
		TArray<TSharedPtr<FJsonValue>> Gs;
		for (const FAstraBattleGroup& G : Groups)
		{
			if (G.Side != EAstraSide::Mandate || G.Members.Num() == 0)
			{
				continue;
			}
			TSharedRef<FJsonObject> J = MakeShared<FJsonObject>();
			J->SetStringField(TEXT("name"), G.Name);
			TArray<TSharedPtr<FJsonValue>> Ids;
			for (const int32 Id : G.Members)
			{
				if (const FAstraBattleShip* S = FindById(Id))
				{
					Ids.Add(MakeShared<FJsonValueString>(S->ContactId));
				}
			}
			J->SetArrayField(TEXT("ships"), Ids);
			J->SetStringField(TEXT("state"), States[(int32)G.State]);
			J->SetStringField(TEXT("order_in_force"), Orders[(int32)G.Order]);
			J->SetStringField(TEXT("formation"), Forms[(int32)G.Formation]);
			if (const FAstraBattleShip* F = FindById(G.FocusTarget))
			{
				J->SetStringField(TEXT("focus_fire_on"), F->bPlayer ? FString(TEXT("AQUILA")) : F->ContactId);
			}
			J->SetNumberField(TEXT("engagement_range_km"), FMath::RoundToDouble(G.EngageRange / 100.0) / 10.0);
			J->SetNumberField(TEXT("your_strength"), FMath::RoundToDouble(G.Strength * 10.0) / 10.0);
			J->SetNumberField(TEXT("enemy_strength_near"), FMath::RoundToDouble(G.EnemyStrength * 10.0) / 10.0);
			J->SetNumberField(TEXT("morale"), FMath::RoundToDouble(G.Morale * 100.0) / 100.0);
			Gs.Add(MakeShared<FJsonValueObject>(J));
		}
		V->SetArrayField(TEXT("your_groups"), Gs);
	}
	{
		// (docs/GUERRA.md, "Il contratto dei comandanti": the groups with their members, the enemy's groups as seen, what happened to them)
		const TSharedRef<FJsonObject> Sg = SideGroupsJson(1);
		V->SetArrayField(TEXT("your_groups"), Sg->GetArrayField(TEXT("your_groups")));
		V->SetArrayField(TEXT("enemy_groups"), Sg->GetArrayField(TEXT("enemy_groups")));
		V->SetArrayField(TEXT("group_events"), Sg->GetArrayField(TEXT("group_events")));
	}
	return V;
}

TArray<TSharedPtr<FJsonValue>> UAstraBattleSubsystem::ContactsJson() const
{
	TArray<TSharedPtr<FJsonValue>> Out;
	if (Ships.Num() == 0)
	{
		return Out;
	}
	const FAstraBattleShip& P = Ships[0];
	for (const FAstraBattleShip& S : Ships)
	{
		if (S.bPlayer || !S.bAlive || S.bCraft)
		{
			continue;
		}
		if (S.bFog && S.Track == 0)
		{
			continue;                                  // not on our plot at all
		}
		TSharedRef<FJsonObject> O = MakeShared<FJsonObject>();
		O->SetStringField(TEXT("id"), S.ContactId);
		if (S.bFog && S.Track == 1)
		{
			// a passive bearing: where it is along a line, not how far
			O->SetStringField(TEXT("class"), S.bClassified ? S.Class : FString(TEXT("unknown")));
			if (S.bIdentified)
			{
				O->SetStringField(TEXT("name"), S.Name);
			}
			O->SetStringField(TEXT("status"), S.bJamming
				? TEXT("JAMMING: its strobe gives the bearing, the noise hides the range — missiles can home on the jamming; the guns need a "
				       "cross-fix (a fleet ship or a flight group well off our line), a recon flight, an active ping or burn-through inside 12 km")
				: TEXT("bearing only (passive, faint drive emissions): no range, no firing solution — an active scan, "
				       "EMCON full, a recon flight or closing in would give a track"));
			O->SetNumberField(TEXT("bearing_deg"), FMath::RoundToDouble(BearingDeg(P.Pos, S.Pos)));
			O->SetNumberField(TEXT("mark_deg"), FMath::RoundToDouble(MarkDeg(P.Pos, S.Pos)));
			Out.Add(MakeShared<FJsonValueObject>(O));
			continue;
		}
		O->SetStringField(TEXT("class"), (S.bFog ? S.bClassified : S.bIdentified) ? S.Class : TEXT("unknown"));
		if (S.bIdentified)
		{
			O->SetStringField(TEXT("name"), S.Name);
		}
		O->SetStringField(TEXT("status"), S.bDerelict ? TEXT("derelict: no power, no transponder, tumbling")
		                                  : S.bDisabled ? TEXT("disabled: no power, drifting, no longer a threat (a derelict, boardable later)")
		                                  : S.bCold ? TEXT("unidentified, cold drive, drifting")
		                                          : (S.bHostile ? (S.bFleeing ? TEXT("hostile, retreating") : (S.bHoldFire ? TEXT("hostile, holding fire") : TEXT("hostile"))) : SideName(S.Side)));
		O->SetNumberField(TEXT("range_km"), FMath::RoundToDouble(FVector::Dist(P.Pos, S.Pos) / 100.0) / 10.0);
		if (S.bJamming)
		{
			O->SetStringField(TEXT("jamming"), TEXT("still jamming: this range comes from a cross-fix, a ping or a flight's eyes"));
		}
		O->SetNumberField(TEXT("bearing_deg"), FMath::RoundToDouble(BearingDeg(P.Pos, S.Pos)));
		O->SetNumberField(TEXT("mark_deg"), FMath::RoundToDouble(MarkDeg(P.Pos, S.Pos)));
		if (!S.bCold)
		{
			O->SetNumberField(TEXT("speed_mps"), FMath::RoundToDouble(S.Vel.Size()));
			O->SetNumberField(TEXT("shields_pct"), Pct(S.Shield, S.ShieldMax));
			O->SetNumberField(TEXT("hull_pct"), Pct(S.Hull, S.HullMax));
		}
		Out.Add(MakeShared<FJsonValueObject>(O));
	}
	return Out;
}

// ------------------------------------------------------------------------------------------------ flight groups
bool UAstraBattleSubsystem::bMandateStandDown() const
{
	return bStandDownCache;                       // (found once per tick, at BuildGrid: every craft asks it every tick)
}

void UAstraBattleSubsystem::AddEnemyWing(int32 CarrierIdx, int32 Count, float Delay)
{
	FAstraSquadron Q;
	Q.Name = TEXT("harpies");
	Q.CallSign = TEXT("Harpy");
	Q.Mesh = TEXT("SM_CRAFT_MANDATE_Harpy");
	Q.Kind = 0;
	Q.Total = Q.OnDeck = Count;
	Q.ToLaunch = Count;
	Q.LaunchT = Delay;
	Q.Side = EAstraSide::Mandate;
	Q.CarrierId = Ships[CarrierIdx].Id;
	Q.Mission = TEXT("strike");
	Q.TargetId = Ships[0].Id;
	Q.Rockets = 4;
	Q.bAuto = true;
	Squadrons.Add(Q);
}

FString UAstraBattleSubsystem::EnemyCraftSummary() const
{
	int32 N = 0;
	double Nearest = 1e18;
	for (const FAstraBattleShip& S : Ships)
	{
		if (S.bAlive && S.bCraft && S.Side == EAstraSide::Mandate)
		{
			++N;
			Nearest = FMath::Min(Nearest, (double)FVector::Dist(S.Pos, Ships[0].Pos));
		}
	}
	return N ? FString::Printf(TEXT("%d Harpy strike fighters airborne (rockets and guns), the nearest %.1f km from us"), N, Nearest / OneKm)
	         : FString(TEXT("none"));
}

int32 UAstraBattleSubsystem::AirborneCount(int32 Squadron) const
{
	int32 N = 0;
	for (const FAstraBattleShip& S : Ships)
	{
		N += (S.bCraft && S.bAlive && S.Squadron == Squadron) ? 1 : 0;
	}
	return N;
}

bool UAstraBattleSubsystem::LaunchSquadron(const FString& Name, const FString& Mission, const FString& ContactId, FString& OutDetail)
{
	const int32 Qi = Squadrons.IndexOfByPredicate([&Name](const FAstraSquadron& Q) { return Q.Side == EAstraSide::Astra && Q.Name.Equals(Name, ESearchCase::IgnoreCase); });
	if (Qi == INDEX_NONE)
	{
		OutDetail = FString::Printf(TEXT("no flight group called %s"), *Name);
		return false;
	}
	FAstraSquadron& Q = Squadrons[Qi];
	const FString M = Mission.ToLower();
	FAstraBattleShip* T = ContactId.IsEmpty() ? nullptr : FindByContact(ContactId);
	if (T && (!T->bAlive || T->bCraft))
	{
		T = nullptr;
	}
	if (Q.Total <= 0)
	{
		OutDetail = FString::Printf(TEXT("%s squadron has no aircraft left"), *Q.Name);
		return false;
	}
	if ((M == TEXT("strike") || M == TEXT("ew") || M == TEXT("escort")) && !T)
	{
		OutDetail = FString::Printf(TEXT("mission %s needs a live contact (got '%s')"), *M, *ContactId);
		return false;
	}
	if ((M == TEXT("strike") || M == TEXT("ew")) && T->Side == EAstraSide::Astra)
	{
		OutDetail = TEXT("cannot task a strike on a friendly vessel");
		return false;
	}
	if (M == TEXT("escort") && T->Side == EAstraSide::Mandate)
	{
		OutDetail = TEXT("escort is for friendly or civilian ships");
		return false;
	}
	if (M == TEXT("sar") && LastWreckName.IsEmpty())
	{
		OutDetail = TEXT("no distress beacons on the plot: nobody to rescue");
		return false;
	}
	const int32 Airborne = AirborneCount(Qi);
	if (Airborne == 0 && Q.RearmT > 0.f)
	{
		OutDetail = FString::Printf(TEXT("%s squadron is rearming on the flight deck, ready in %.0f s"), *Q.Name, Q.RearmT);
		return false;
	}
	const UAstraShipSubsystem* Ship = GetWorld()->GetSubsystem<UAstraShipSubsystem>();
	const float Deck = Ship ? Ship->PowerFactor(TEXT("flight_deck")) : 1.f;
	if (Airborne == 0 && Deck < 0.3f)
	{
		OutDetail = FString::Printf(TEXT("flight deck power too low to launch (%.0f %%)"), Deck * 100.f);
		return false;
	}
	Q.Mission = M;
	Q.TargetId = T ? T->Id : -1;
	for (FAstraBattleShip& S : Ships)
	{
		if (S.bCraft && S.bAlive && S.Squadron == Qi)
		{
			S.Mission = M;
			S.MissionTarget = Q.TargetId;
		}
	}
	FString Launch;
	if (Q.OnDeck > 0 && Q.RearmT <= 0.f)
	{
		Q.ToLaunch = Q.OnDeck;
		Q.LaunchT = 0.f;
		Q.Launched = 0;
		Q.bAirborneReported = false;
		Launch = FString::Printf(TEXT("launching %d %ss, one every %.0f s"), Q.ToLaunch, *Q.CallSign, 2.f / FMath::Max(0.3f, Deck));
	}
	OutDetail = FString::Printf(TEXT("%s squadron: %s%s%s, mission %s%s"), *Q.Name,
	                            Airborne ? *FString::Printf(TEXT("%d airborne re-tasked"), Airborne) : TEXT(""),
	                            (Airborne && !Launch.IsEmpty()) ? TEXT(", ") : TEXT(""), *Launch, *M,
	                            T ? *FString::Printf(TEXT(" on %s"), *KnownLabel(*T)) : TEXT(""));
	return true;
}

bool UAstraBattleSubsystem::RecallSquadron(const FString& Name, FString& OutDetail)
{
	const int32 Qi = Squadrons.IndexOfByPredicate([&Name](const FAstraSquadron& Q) { return Q.Side == EAstraSide::Astra && Q.Name.Equals(Name, ESearchCase::IgnoreCase); });
	if (Qi == INDEX_NONE)
	{
		OutDetail = FString::Printf(TEXT("no flight group called %s"), *Name);
		return false;
	}
	FAstraSquadron& Q = Squadrons[Qi];
	Q.ToLaunch = 0;
	Q.Mission = TEXT("recall");
	int32 N = 0;
	for (FAstraBattleShip& S : Ships)
	{
		if (S.bCraft && S.bAlive && S.Squadron == Qi)
		{
			S.Mission = TEXT("recall");
			++N;
		}
	}
	OutDetail = N ? FString::Printf(TEXT("%s squadron recalled: %d aircraft returning to the flight deck"), *Q.Name, N)
	              : FString::Printf(TEXT("%s squadron is already aboard (%d on deck)"), *Q.Name, Q.OnDeck);
	return true;
}

TSharedRef<FJsonObject> UAstraBattleSubsystem::SquadronsJson() const
{
	TSharedRef<FJsonObject> J = MakeShared<FJsonObject>();
	for (int32 Qi = 0; Qi < Squadrons.Num(); ++Qi)
	{
		const FAstraSquadron& Q = Squadrons[Qi];
		if (Q.Side != EAstraSide::Astra)
		{
			continue;
		}
		const int32 Air = AirborneCount(Qi);
		const int32 Lost = (Q.Name == TEXT("alpha") ? 8 : (Q.Name == TEXT("bravo") ? 7 : 12)) - Q.Total;
		FString St;
		if (Q.Total <= 0)
		{
			St = TEXT("lost: no aircraft left");
		}
		else if (Air == 0)
		{
			St = Q.RearmT > 0.f ? FString::Printf(TEXT("on deck, rearming: ready in %.0f s (%d %ss)"), Q.RearmT, Q.OnDeck, *Q.CallSign)
			                    : FString::Printf(TEXT("on deck, ready (%d %ss)"), Q.OnDeck, *Q.CallSign);
		}
		else
		{
			const FAstraBattleShip* T = Ships.FindByPredicate([&Q](const FAstraBattleShip& S) { return S.Id == Q.TargetId && S.bAlive; });
			St = FString::Printf(TEXT("%s: %d %ss airborne, mission %s%s%s"), Q.ToLaunch > 0 ? TEXT("launching") : (Q.Mission == TEXT("recall") ? TEXT("returning") : TEXT("airborne")),
			                     Air, *Q.CallSign, *Q.Mission, T ? *FString::Printf(TEXT(" on %s"), *T->ContactId) : TEXT(""),
			                     Q.OnDeck ? *FString::Printf(TEXT(", %d on deck"), Q.OnDeck) : TEXT(""));
		}
		if (Lost > 0)
		{
			St += FString::Printf(TEXT("; %d lost"), Lost);
		}
		J->SetStringField(Q.Name, St);
	}
	return J;
}

void UAstraBattleSubsystem::FireTorpedo(FAstraBattleShip& From, FAstraBattleShip& To)
{
	FireMissile(From, To);
	FAstraProjectile& Pr = Projectiles.Last();
	Pr.bTorpedo = true;
	Pr.HitKind = EAstraHitKind::Torpedo;
	Pr.Damage = 220.f;
	Pr.MaxSpeed = 900.f;
	Pr.Life = 90.f;
	Pr.Vel = From.Vel + (To.Pos - From.Pos).GetSafeNormal() * 200.f;
	if (Pr.Actor)
	{
		if (UMaterialInstanceDynamic* M = Cast<UMaterialInstanceDynamic>(Pr.Actor->GetStaticMeshComponent()->GetMaterial(0)))
		{
			M->SetVectorParameterValue(TEXT("Color"), FLinearColor(0.55f, 0.8f, 1.f));
			M->SetScalarParameterValue(TEXT("Intensity"), 400.f);
		}
		Pr.Actor->SetActorScale3D(FVector(10.f));
	}
}

void UAstraBattleSubsystem::TickSquadrons(float Dt)
{
	const UAstraShipSubsystem* Ship = GetWorld()->GetSubsystem<UAstraShipSubsystem>();
	const float Deck = Ship ? Ship->PowerFactor(TEXT("flight_deck")) : 1.f;
	for (int32 Qi = 0; Qi < Squadrons.Num(); ++Qi)
	{
		FAstraSquadron& Q = Squadrons[Qi];
		if (Q.RearmT > 0.f && (Q.RearmT -= Dt) <= 0.f && Q.OnDeck > 0)
		{
			Report(FString::Printf(TEXT("flight: %s squadron rearmed, %d %ss ready on the flight deck"), *Q.Name, Q.OnDeck, *Q.CallSign), false);
		}
		if (Q.LostSinceReport > 0 && Time - Q.LastLossReport > 12.f)
		{
			Report(Q.Side == EAstraSide::Astra
				? FString::Printf(TEXT("flight: %s squadron has lost %d %s%s to enemy fire, %d left%s"), *Q.Name, Q.LostSinceReport, *Q.CallSign,
				                  Q.LostSinceReport > 1 ? TEXT("s") : TEXT(""), Q.Total,
				                  Q.LostCrew.Num() ? *(TEXT(" — ") + FString::Join(Q.LostCrew, TEXT("; "))) : TEXT(""))
				: FString::Printf(TEXT("tactical: %d Harp%s splashed, %d of the enemy strike fighters left"), Q.LostSinceReport,
				                  Q.LostSinceReport > 1 ? TEXT("ies") : TEXT("y"), Q.Total));
			Q.LostSinceReport = 0;
			Q.LostCrew.Reset();
			Q.LastLossReport = Time;
		}
		if (Q.TorpedoReportAt > 0.f && Time >= Q.TorpedoReportAt)
		{
			Report(FString::Printf(TEXT("flight: %s squadron torpedo run on %s: %d torpedoes away, bombers returning"), *Q.Name,
			                       *Q.TorpedoTarget, Q.TorpedoesAway));
			Q.TorpedoesAway = 0;
			Q.TorpedoReportAt = -1.f;
		}
		if (Q.ToLaunch <= 0 || (Q.LaunchT -= Dt) > 0.f)
		{
			continue;
		}
		if (Q.Side != EAstraSide::Astra && bMandateStandDown())
		{
			Q.LaunchT = 3.f;   // their commander holds fire: the strike wing waits on deck
			continue;
		}
		const FAstraBattleShip* Carrier = FindById(Q.CarrierId);
		if (!Carrier || !Carrier->bAlive)
		{
			Q.ToLaunch = 0;   // the carrier is gone: the rest of the wing dies with it
			continue;
		}
		const bool bOurs = Q.Side == EAstraSide::Astra;
		const float Hangar = HangarFactor(*Carrier);
		if (Hangar <= 0.f)
		{
			Q.LaunchT = 3.f;                  // the hangar is wrecked, or the carrier is dead in the water: the wing waits on deck
			continue;
		}
		Q.LaunchT = (bOurs ? 2.f / FMath::Max(0.3f, Deck) : 1.5f) / FMath::Max(0.3f, Hangar);
		--Q.ToLaunch;
		--Q.OnDeck;
		++Q.Launched;
		const FVector CarrierPos = Carrier->Pos, CarrierVel = Carrier->Vel;   // copies: AddShip may reallocate Ships
		const FQuat CarrierAtt = Carrier->Att;
		const float Side = (Q.Launched % 2) ? 1.f : -1.f;
		// the Aquila's craft leave through her bow launch tubes (hull frame: x 390 m, y +-14.9 m, z -4.3 m)
		const bool bFromAquila = Q.CarrierId == Ships[0].Id;
		const float TubeSide = Q.Name == TEXT("bravo") ? 1.f : (Q.Name == TEXT("alpha") ? -1.f : Side);
		const FVector Pos = CarrierPos + CarrierAtt.RotateVector(bFromAquila ? FVector(398.0, TubeSide * 14.9, -4.3) : FVector(-60.0, Side * 40.0, -30.0));
		const float Radius = Q.Kind == 1 ? 14.f : (Q.Kind == 2 ? 5.f : 10.f);
		const float Hull = Q.Kind == 1 ? 110.f : (Q.Kind == 2 ? 25.f : 60.f);
		const TCHAR* Role = Q.Kind == 1 ? TEXT("torpedo bomber") : (Q.Kind == 2 ? TEXT("drone") : TEXT("fighter"));
		const int32 I = AddShip(FString::Printf(TEXT("%s-%d"), *Q.CallSign.ToUpper(), Q.Launched), FString::Printf(TEXT("%s %d"), *Q.CallSign, Q.Launched),
		                        FString::Printf(TEXT("%s %s (%s)"), bOurs ? TEXT("ASTRA") : TEXT("Kharon Mandate"), Role, *Q.CallSign), Q.Mesh, Q.Side, Pos,
		                        CarrierAtt.Rotator().Yaw, 200.f, Radius, Hull, Q.Kind == 2 ? 0.f : 20.f);
		FAstraBattleShip& C = Ships[I];
		C.bCraft = true;
		C.Squadron = Qi;
		C.CraftKind = Q.Kind;
		C.Mission = Q.Mission;
		C.MissionTarget = Q.TargetId;
		C.Torpedoes = Q.Kind == 1 ? 2 : 0;
		C.RailDamage = 0.f;
		C.Missiles = 0;
		C.PDRange = 0.f;
		C.PDChannels = 0;
		C.bShieldsUp = C.Shield > 0.f;
		C.Vel = CarrierVel + CarrierAtt.RotateVector(FVector(120.0, Side * 80.0, -40.0));
		C.CruiseSpeed = Q.Kind == 1 ? 650.f : (Q.Kind == 2 ? 900.f : 850.f);
		C.MaxAccel = 160.f;
		C.MaxTurnDeg = 45.f;
		C.OrbitPhase = FMath::FRand() * 2.f * PI;
		C.Mode = EAstraShipMode::Cruise;
		C.bHostile = !bOurs;
		C.Missiles = Q.Rockets;
		++Stats.CraftLaunched[bOurs ? 0 : 1];
		AssignFlight(C, Qi);                                    // a flight of two to four: a leader and wingmen (AstraWarCraft.cpp)
		SpawnVisual(C);
		if (bOurs)
		{
			HullSound(TEXT("SW_Catapult"), 0.75f, 0.9f);
		}
		if (Q.ToLaunch == 0 && !Q.bAirborneReported)
		{
			Q.bAirborneReported = true;
			const FAstraBattleShip* Cr = FindById(Q.CarrierId);
			Report(bOurs ? FString::Printf(TEXT("flight: %s squadron airborne, %d %ss on %s"), *Q.Name, Q.Launched, *Q.CallSign, *Q.Mission.ToUpper())
			             : FString::Printf(TEXT("sensors: %s has launched strike fighters — %d Harpies inbound on the Aquila"),
			                               Cr ? *KnownLabel(*Cr) : TEXT("an enemy cruiser"), Q.Launched));
		}
	}
}

// (the craft's minds — flights, dogfights, attack runs — are in AstraWarCraft.cpp)

// ------------------------------------------------------------------------------------------------ destruction
void UAstraBattleSubsystem::Explode(FAstraBattleShip& S)
{
	UWorld* World = GetWorld();
	const FVector Drift = S.Vel * 0.55f;
	const FVector Axis = S.Att.GetForwardVector();
	// secondary blasts running along the hull over two seconds
	for (int32 i = 0; i < 6; ++i)
	{
		const FVector P = S.Pos + Axis * FMath::FRandRange(-1.f, 1.f) * S.Radius + FMath::VRand() * S.Radius * 0.25f;
		AddFlash(P, S.Radius * FMath::FRandRange(0.35f, 0.8f), FMath::FRandRange(1.f, 2.f), FLinearColor(1.f, FMath::FRandRange(0.45f, 0.7f), 0.2f), 220.f);
		Flashes.Last().Age = -FMath::FRandRange(0.15f, 2.2f);
		Flashes.Last().Vel = Drift;
	}
	// shockwave ring in the ship's plane
	if (World && RingMesh && GlowMat && FApp::CanEverRender())
	{
		FAstraFlash F;
		F.Pos = S.Pos;
		F.Size = S.Radius * 4.5f;
		F.Life = 1.8f;
		F.bRing = true;
		F.Vel = Drift;
		F.Rot = S.Att * FQuat(FVector::ForwardVector, FMath::DegreesToRadians(FMath::FRandRange(-25.f, 25.f)));
		FActorSpawnParameters SP;
		SP.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
		F.Actor = World->SpawnActor<AStaticMeshActor>(FVector::ZeroVector, FRotator::ZeroRotator, SP);
		F.Actor->SetMobility(EComponentMobility::Movable);
		UStaticMeshComponent* C = F.Actor->GetStaticMeshComponent();
		C->SetStaticMesh(RingMesh);
		C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		C->SetCastShadow(false);
		F.MID = C->CreateAndSetMaterialInstanceDynamicFromMaterial(0, GlowMat);
		F.MID->SetVectorParameterValue(TEXT("Color"), FLinearColor(1.f, 0.72f, 0.45f));
		F.MID->SetScalarParameterValue(TEXT("Intensity"), 80.f);
		Flashes.Add(F);
	}
	// the hulk: the ship's own mesh, burnt dark, drifting and tumbling slowly (headless: only the obstacle it is)
	if (S.Actor || !FApp::CanEverRender())
	{
		FAstraWreck W;
		W.Actor = S.Actor;
		S.Actor = nullptr;
		W.Radius = S.Radius * 0.8f;
		W.Pos = S.Pos;
		W.Vel = Drift + FMath::VRand() * 4.f;
		W.Att = S.Att;
		W.SpinAxis = FMath::VRand();
		W.SpinDeg = FMath::FRandRange(1.5f, 4.5f);
		if (UStaticMeshComponent* C = W.Actor ? W.Actor->GetStaticMeshComponent() : nullptr)
		{
			for (int32 i = 0; i < C->GetNumMaterials(); ++i)
			{
				if (UMaterialInstanceDynamic* M = C->CreateDynamicMaterialInstance(i))
				{
					M->SetVectorParameterValue(TEXT("Tint"), FLinearColor(0.025f, 0.023f, 0.022f));
					M->SetVectorParameterValue(TEXT("EmissiveColor"), FLinearColor(0.9f, 0.3f, 0.08f));
					M->SetScalarParameterValue(TEXT("Intensity"), FMath::FRandRange(0.f, 3.f));   // a few embers still glowing
				}
			}
		}
		Wrecks.Add(W);
	}
	// debris
	if (World && CubeMesh && FApp::CanEverRender())
	{
		UMaterialInterface* Frame = LoadObject<UMaterialInterface>(nullptr, S.Side == EAstraSide::Mandate
			? TEXT("/Game/ASTRA/Materials/Instances/MI_HULL_M_Frame.MI_HULL_M_Frame")
			: TEXT("/Game/ASTRA/Materials/Instances/MI_HULL_A_Plate.MI_HULL_A_Plate"));
		for (int32 i = 0; i < 16; ++i)
		{
			FAstraWreck D;
			D.Pos = S.Pos + FMath::VRand() * S.Radius * 0.4f;
			D.Vel = Drift + FMath::VRand() * FMath::FRandRange(25.f, 130.f);
			D.Att = FQuat(FMath::VRand(), FMath::FRandRange(0.f, 6.f));
			D.SpinAxis = FMath::VRand();
			D.SpinDeg = FMath::FRandRange(20.f, 140.f);
			D.Life = FMath::FRandRange(18.f, 30.f);
			D.Scale = S.Radius * FMath::FRandRange(0.015f, 0.06f);
			FActorSpawnParameters SP;
			SP.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
			D.Actor = World->SpawnActor<AStaticMeshActor>(FVector::ZeroVector, FRotator::ZeroRotator, SP);
			D.Actor->SetMobility(EComponentMobility::Movable);
			UStaticMeshComponent* C = D.Actor->GetStaticMeshComponent();
			C->SetStaticMesh(CubeMesh);
			C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
			C->SetCastShadow(false);
			C->SetLightingChannels(true, true, false);
			if (Frame)
			{
				C->SetMaterial(0, Frame);
			}
			D.Actor->SetActorScale3D(FVector(D.Scale * FMath::FRandRange(0.5f, 1.5f), D.Scale * FMath::FRandRange(0.3f, 1.f), D.Scale * FMath::FRandRange(0.1f, 0.5f)));
			Wrecks.Add(D);
		}
	}
}

void UAstraBattleSubsystem::TickWrecks(float Dt)
{
	for (FAstraWreck& L : Landmarks)
	{
		if (L.Actor)
		{
			L.Actor->SetActorLocationAndRotation(ToWorld(L.Pos), ToWorldRot(L.Att));
		}
	}
	for (int32 i = Wrecks.Num() - 1; i >= 0; --i)
	{
		FAstraWreck& W = Wrecks[i];
		W.Age += Dt;
		W.Pos += W.Vel * Dt;
		W.Att = FQuat(W.SpinAxis, FMath::DegreesToRadians(W.SpinDeg * Dt)) * W.Att;
		// (a hulk with no actor, headless, stays as the obstacle it is; the far ones go: from the Aquila, or from the origin in a bench)
		const FVector Ref = (bSandbox && !Ships[0].bAlive) ? FVector::ZeroVector : Ships[0].Pos;
		if ((!W.Actor && W.Radius <= 0.f) || (W.Life > 0.f && W.Age > W.Life) || FVector::Dist(W.Pos, Ref) > 250 * OneKm)
		{
			if (W.Actor) { W.Actor->Destroy(); }
			Wrecks.RemoveAtSwap(i);
			continue;
		}
		if (W.Actor)
		{
			W.Actor->SetActorLocationAndRotation(ToWorld(W.Pos), ToWorldRot(W.Att));
		}
	}
}

// ---------------------------------------------------------------------------------------------- the war director
int32 UAstraBattleSubsystem::LaunchGhosts(int32 OwnerIdx, int32 N)
{
	if (!Ships.IsValidIndex(OwnerIdx) || Ships.Num() == 0)
	{
		return 0;
	}
	const FVector From = Ships[OwnerIdx].Pos;       // copies: adding ships may reallocate
	const FVector Aquila = Ships[0].Pos;
	const double R = FMath::Clamp(FVector::Dist(From, Aquila) / OneKm, 38.0, 80.0);
	const double B = BearingDeg(Aquila, From);
	int32 Made = 0;
	for (int32 k = 0; k < N; ++k)
	{
		// a false bearing well off the real one, at about the same range: a second group, a pincer that is not there
		const double Off = ((k + FMath::RandRange(0, 1)) % 2 ? 1.0 : -1.0) * FMath::FRandRange(35.f, 70.f);
		const FVector Goal = Aquila + Polar(R * OneKm, B + Off, FMath::FRandRange(-6.f, 6.f));
		const FString Id = FString::Printf(TEXT("T-%d"), NextContact++);
		const int32 I = AddShip(Id, TEXT("decoy emitter"), TEXT("Mandate decoy emitter, a drone faking a warship's drive"), TEXT(""),
		                        EAstraSide::Neutral, From + FMath::VRand() * 300.f, 0.f, 0.f, 4.f, 1.f, 0.f);
		FAstraBattleShip& G = Ships[I];
		G.bGhost = true;
		G.bFog = true;
		G.Track = 0;
		G.bIdentified = G.bClassified = false;
		G.GhostGoal = Goal;
		G.GhostLife = FMath::FRandRange(270.f, 340.f);
		G.CruiseSpeed = 900.f;
		G.Vel = (Goal - G.Pos).GetSafeNormal() * 400.f;
		G.Att = G.Vel.ToOrientationQuat();
		G.Missiles = 0;
		G.RailDamage = 0.f;
		G.Mode = EAstraShipMode::Cruise;
		++Made;
	}
	UE_LOG(LogASTRA, Log, TEXT("[Battle] %d decoy emitters out from %s"), Made, *Ships[OwnerIdx].ContactId);
	return Made;
}

int32 UAstraBattleSubsystem::SpawnClass(const FString& Class, const FString& Contact, const FString& Name, const FVector& Pos, float HeadingDeg)
{
	const FString C = Class.ToLower();
	int32 I = INDEX_NONE;
	if (C.Contains(TEXT("acheron")) || C.Contains(TEXT("cruiser")))
	{
		I = AddShip(Contact, Name, TEXT("Kharon Mandate cruiser, Acheron class"), TEXT("SM_SHIP_MANDATE_Acheron"), EAstraSide::Mandate, Pos, HeadingDeg, 450.f, 240.f, 3600.f, 1500.f);
		Ships[I].RailDamage = 85.f; Ships[I].RailSlugs = 3; Ships[I].RailCd = 8.f; Ships[I].Missiles = 32; Ships[I].PDChannels = 3;
	}
	else if (C.Contains(TEXT("lethe")) || C.Contains(TEXT("frigate")))
	{
		I = AddShip(Contact, Name, TEXT("Kharon Mandate frigate, Lethe class"), TEXT("SM_SHIP_MANDATE_Lethe"), EAstraSide::Mandate, Pos, HeadingDeg, 500.f, 90.f, 520.f, 220.f);
		Ships[I].Missiles = 8;
	}
	else if (C.Contains(TEXT("praetorian")) || C.Contains(TEXT("battleship")))
	{
		I = AddShip(Contact, Name, TEXT("ASTRA battleship"), TEXT("SM_SHIP_ASTRA_Praetorian"), EAstraSide::Astra, Pos, HeadingDeg, 300.f, 460.f, 5200.f, 2000.f);
		BattleshipStats(Ships[I]);
	}
	else if (C.Contains(TEXT("vigilant")) || C.Contains(TEXT("astra")))
	{
		I = AddShip(Contact, Name, TEXT("ASTRA destroyer"), TEXT("SM_SHIP_ASTRA_Vigilant"), EAstraSide::Astra, Pos, HeadingDeg, 300.f, 140.f, 1200.f, 500.f);
		DestroyerStats(Ships[I]);
	}
	else if (C.Contains(TEXT("freighter")) || C.Contains(TEXT("guild")))
	{
		I = AddShip(Contact, Name, TEXT("Free Guilds freighter"), TEXT("SM_SHIP_GUILD_Freighter"), EAstraSide::Neutral, Pos, HeadingDeg, 180.f, 170.f, 700.f, 60.f);
		Ships[I].RailDamage = 0.f; Ships[I].Missiles = 0;
	}
	else
	{
		I = AddShip(Contact, Name, TEXT("Kharon Mandate destroyer, Styx class"), TEXT("SM_SHIP_MANDATE_Styx"), EAstraSide::Mandate, Pos, HeadingDeg, 450.f, 130.f, 1300.f, 500.f);
		Ships[I].RailDamage = 60.f; Ships[I].RailCd = 9.f; Ships[I].Missiles = 16;
	}
	if (Ships[I].Side == EAstraSide::Mandate)
	{
		Ships[I].bHostile = true;
		Ships[I].Mode = EAstraShipMode::Attack;
		Ships[I].CruiseSpeed = 450.f;
	}
	SpawnVisual(Ships[I]);
	return I;
}

bool UAstraBattleSubsystem::StartBeat(const TSharedPtr<FJsonObject>& Beat, FString& OutDetail)
{
	if (!Beat.IsValid() || Ships.Num() == 0)
	{
		OutDetail = TEXT("no beat");
		return false;
	}
	FString Type;
	Beat->TryGetStringField(TEXT("type"), Type);
	Type = Type.ToLower();
	double Delay = 60.0;
	Beat->TryGetNumberField(TEXT("delay_s"), Delay);
	Delay = FMath::Clamp(Delay, 5.0, 900.0);
	if (Type == TEXT("resupply"))
	{
		double Dur = 120.0, HullTo = 85.0, Missiles = 24.0;
		Beat->TryGetNumberField(TEXT("duration_s"), Dur);
		Beat->TryGetNumberField(TEXT("hull_pct"), HullTo);
		Beat->TryGetNumberField(TEXT("missiles"), Missiles);
		Dur = FMath::Clamp(Dur, 30.0, 600.0);
		const FAstraBattleShip& P = Ships[0];
		RepairUntil = Time + Dur;
		RepairHullPerSec = FMath::Max(0.f, (float)(FMath::Clamp(HullTo, 0.0, 100.0) / 100.0 * P.HullMax - P.Hull)) / (float)Dur;
		RepairMissiles = FMath::Clamp((int32)Missiles, 0, 96);
		OutDetail = FString::Printf(TEXT("resupply under way for %.0f s: hull to %.0f%%, %d missiles"), Dur, HullTo, RepairMissiles);
		return true;
	}
	if (Type == TEXT("calm"))
	{
		CalmUntil = Time + Delay;
		OutDetail = FString::Printf(TEXT("quiet period of %.0f s"), Delay);
		return true;
	}
	if (Type == TEXT("transit"))
	{
		// Fleet orders the transit and Keeper Station tunes the gate; the Captain decides when the Aquila goes through
		FString Name, Star, Planet, PName;
		Beat->TryGetStringField(TEXT("system_name"), Name);
		Beat->TryGetStringField(TEXT("star_class"), Star);
		Beat->TryGetStringField(TEXT("planet_type"), Planet);
		Beat->TryGetStringField(TEXT("planet_name"), PName);
		UAstraShipSubsystem* Ship = GetWorld()->GetSubsystem<UAstraShipSubsystem>();
		if (Name.TrimStartAndEnd().IsEmpty() || !Ship || !Landmarks.IsValidIndex(GateLandmark))
		{
			OutDetail = TEXT("a transit needs a destination system and a gate");
			return false;
		}
		if (bEngagementActive)
		{
			OutDetail = TEXT("the Aquila is in the middle of an engagement");
			return false;
		}
		if (Name.TrimStartAndEnd().Equals(Ship->GetSystemName(), ESearchCase::IgnoreCase))
		{
			OutDetail = FString::Printf(TEXT("the Aquila is already in the %s system"), *Ship->GetSystemName());
			return false;
		}
		const FAstraSystemLook L = Ship->ChartSystem(Name, Star, Planet, PName);
		FleetOrderedDest = L.Name;
		Report(FString::Printf(TEXT("comms: orders from Fleet — the Aquila is to transit the Janus Gate to the %s system; Keeper Station has "
		                            "tuned the gate for us. The helm lays in the approach on the Captain's order (%s)"), *L.Name, *GateStatus()));
		OutDetail = FString::Printf(TEXT("Fleet orders the Aquila to the %s system (%s star, %s world %s); the gate is tuned, the Captain "
		                                 "decides when to go through"), *L.Name, *L.StarClass, *L.PlanetType, *L.PlanetName);
		return true;
	}
	if (Type == TEXT("investigate"))
	{
		// a place to search: it is on the plot at once (a station, a hulk); an ambush may be lying cold around it
		const TSharedPtr<FJsonObject>* PoiObj = nullptr;
		FString Kind = TEXT("listening_post"), PName = TEXT("the derelict");
		if (Beat->TryGetObjectField(TEXT("poi"), PoiObj))
		{
			(*PoiObj)->TryGetStringField(TEXT("kind"), Kind);
			(*PoiObj)->TryGetStringField(TEXT("name"), PName);
		}
		double Brg = FMath::FRandRange(0.f, 359.f), Rng = 30.0;
		Beat->TryGetNumberField(TEXT("bearing_deg"), Brg);
		Beat->TryGetNumberField(TEXT("range_km"), Rng);
		Rng = FMath::Clamp(Rng, 12.0, 60.0);
		const FVector Pos = Ships[0].Pos + Polar(Rng * OneKm, Brg, FMath::FRandRange(-4.f, 4.f));
		const FString Cid = FString::Printf(TEXT("T-%d"), NextContact++);
		const bool bStation = Kind.Contains(TEXT("post")) || Kind.Contains(TEXT("station"));
		const bool bWarship = Kind.Contains(TEXT("warship"));
		const int32 I = AddShip(Cid, PName, bStation ? TEXT("ASTRA listening post, Watch class (derelict)")
		                                    : (bWarship ? TEXT("ASTRA destroyer, Vigilant class (derelict)") : TEXT("Free Guilds freighter (derelict)")),
		                        bStation ? TEXT("SM_STATION_ASTRA_Watch") : (bWarship ? TEXT("SM_SHIP_ASTRA_Vigilant") : TEXT("SM_SHIP_GUILD_Freighter")),
		                        EAstraSide::Neutral, Pos, FMath::FRandRange(0.f, 360.f), 0.f, bStation ? 120.f : 150.f, 5000.f, 0.f);
		FAstraBattleShip& D = Ships[I];
		D.bDerelict = true;
		D.RailDamage = 0.f;
		D.Missiles = 0;
		D.bShieldsUp = false;
		D.Vel = FMath::VRand() * 2.f;
		D.SpinDeg = FMath::FRandRange(0.15f, 0.5f);
		SpawnVisual(D);
		FAstraPOI Poi;
		Poi.ShipId = D.Id;
		Poi.Name = PName;
		const TArray<TSharedPtr<FJsonValue>>* F = nullptr;
		if (Beat->TryGetArrayField(TEXT("findings"), F))
		{
			for (const TSharedPtr<FJsonValue>& V : *F)
			{
				if (!V->AsString().IsEmpty() && Poi.Findings.Num() < 3) { Poi.Findings.Add(V->AsString()); }
			}
		}
		if (Poi.Findings.Num() == 0)
		{
			Poi.Findings.Add(TEXT("no power, no life signs from this range; the hull is intact"));
		}
		TArray<FString> Ids = {Cid};
		const TArray<TSharedPtr<FJsonValue>>* Amb = nullptr;
		if (Beat->TryGetArrayField(TEXT("ambush"), Amb))
		{
			for (const TSharedPtr<FJsonValue>& V : *Amb)
			{
				const TSharedPtr<FJsonObject> O = V->AsObject();
				FString Cls = TEXT("styx"), Nm = TEXT("Unknown");
				if (O.IsValid()) { O->TryGetStringField(TEXT("class"), Cls); O->TryGetStringField(TEXT("name"), Nm); }
				const FString AId = FString::Printf(TEXT("T-%d"), NextContact++);
				const FVector APos = Pos + Polar(FMath::FRandRange(3.f, 6.5f) * OneKm, FMath::FRandRange(0.f, 359.f), FMath::FRandRange(-6.f, 6.f));
				const int32 J = SpawnClass(Cls, AId, Nm, APos, FMath::FRandRange(0.f, 360.f));
				FAstraBattleShip& A = Ships[J];
				A.bCold = true;           // lying dark: drives off, no emissions
				A.bHostile = false;
				A.bIdentified = false;
				A.Mode = EAstraShipMode::Idle;
				A.Vel = FVector::ZeroVector;
				Poi.Ambush.Add(A.Id);
				Ids.Add(AId);
				if (Poi.Ambush.Num() == 1) { A.bLeader = true; }
			}
			double Ak = 12.0;
			Beat->TryGetNumberField(TEXT("ambush_km"), Ak);
			Poi.AmbushKm = FMath::Clamp((float)Ak, 4.f, 25.f);
		}
		POIs.Add(Poi);
		Report(FString::Printf(TEXT("sensors: new contact %s at bearing %03.0f, %.0f km — %s: no power, no transponder, tumbling slowly"),
		                       *Cid, Brg, Rng, *PName));
		OutDetail = FString::Printf(TEXT("%s placed at bearing %03.0f, %.0f km (%s); contact ids %s"), *PName, Brg, Rng, *Kind, *FString::Join(Ids, TEXT(", ")));
		return true;
	}
	if (Type != TEXT("raid") && Type != TEXT("distress") && Type != TEXT("reinforcements"))
	{
		OutDetail = FString::Printf(TEXT("unknown beat type %s"), *Type);
		return false;
	}
	// contact ids now, so the new commanders can be given a mind before they arrive
	TArray<FString> Ids;
	const TArray<TSharedPtr<FJsonValue>>* List = nullptr;
	int32 N = 0;
	if (Beat->TryGetArrayField(TEXT("ships"), List))
	{
		N += List->Num();
	}
	if (Beat->TryGetArrayField(TEXT("attackers"), List))
	{
		N += List->Num();
	}
	if (Beat->TryGetArrayField(TEXT("groups"), List))
	{
		// a force in battle groups (a fleet-scale beat): the ids follow the groups' ships in order, each group's leader first
		for (const TSharedPtr<FJsonValue>& GV : *List)
		{
			const TArray<TSharedPtr<FJsonValue>>* GShips = nullptr;
			if (GV->Type == EJson::Object && GV->AsObject()->TryGetArrayField(TEXT("ships"), GShips))
			{
				N += FMath::Min(GShips->Num(), MaxBeatGroupShips);
			}
		}
	}
	if (Type == TEXT("distress"))
	{
		++N;   // the ship calling for help comes first
	}
	N = FMath::Clamp(N, 1, MaxBeatShips);
	TArray<TSharedPtr<FJsonValue>> IdValues;
	for (int32 i = 0; i < N; ++i)
	{
		Ids.Add(FString::Printf(TEXT("T-%d"), NextContact++));
		IdValues.Add(MakeShared<FJsonValueString>(Ids.Last()));
	}
	Beat->SetArrayField(TEXT("_ids"), IdValues);
	PendingBeats.Add(TPair<float, TSharedPtr<FJsonObject>>(Time + (float)Delay, Beat));
	OutDetail = FString::Printf(TEXT("%s scheduled in %.0f s; contact ids %s; the first is the group's leader"), *Type, Delay, *FString::Join(Ids, TEXT(", ")));
	return true;
}

void UAstraBattleSubsystem::ArriveBeat(const TSharedPtr<FJsonObject>& Beat)
{
	FString Type;
	Beat->TryGetStringField(TEXT("type"), Type);
	Type = Type.ToLower();
	double Bearing = FMath::FRandRange(0.f, 360.f), Range = 25.0;
	Beat->TryGetNumberField(TEXT("bearing_deg"), Bearing);
	Beat->TryGetNumberField(TEXT("range_km"), Range);
	Range = FMath::Clamp(Range, 6.0, 120.0);
	TArray<FString> Ids;
	const TArray<TSharedPtr<FJsonValue>>* IdList = nullptr;
	if (Beat->TryGetArrayField(TEXT("_ids"), IdList))
	{
		for (const TSharedPtr<FJsonValue>& V : *IdList)
		{
			Ids.Add(V->AsString());
		}
	}
	int32 NextIdx = 0;
	auto TakeId = [&]() { return Ids.IsValidIndex(NextIdx) ? Ids[NextIdx++] : FString::Printf(TEXT("T-%d"), NextContact++); };
	const int32 PlayerId = Ships[0].Id;                  // copies: spawning may reallocate Ships
	FVector Centre = Ships[0].Pos + Polar(Range * OneKm, Bearing, FMath::FRandRange(-3.f, 5.f));
	const TArray<TSharedPtr<FJsonValue>>* AtM = nullptr;
	if (Beat->TryGetArrayField(TEXT("at_m"), AtM) && AtM->Num() >= 3)
	{
		// a fixed place (the Janus Gate's mouth): the bearing is where it lies from the Aquila now
		Centre = FVector((*AtM)[0]->AsNumber(), (*AtM)[1]->AsNumber(), (*AtM)[2]->AsNumber());
		const FVector To = Centre - Ships[0].Pos;
		Bearing = FMath::Fmod(FMath::RadiansToDegrees(FMath::Atan2(To.Y, To.X)) + 360.0, 360.0);
		Range = To.Size() / OneKm;
	}
	const float Facing = (float)FMath::Fmod(Bearing + 180.0, 360.0);   // they come towards us
	auto ShipSpecs = [&Beat](const TCHAR* Field) -> TArray<TSharedPtr<FJsonObject>>
	{
		TArray<TSharedPtr<FJsonObject>> Out;
		const TArray<TSharedPtr<FJsonValue>>* L = nullptr;
		if (Beat->TryGetArrayField(Field, L))
		{
			for (const TSharedPtr<FJsonValue>& V : *L)
			{
				if (V->Type == EJson::Object)
				{
					Out.Add(V->AsObject());
				}
			}
		}
		return Out;
	};
	FString Listing;
	const TArray<TSharedPtr<FJsonObject>> GroupSpecs = ShipSpecs(TEXT("groups"));
	if ((Type == TEXT("raid") || Type == TEXT("reinforcements")) && GroupSpecs.Num())
	{
		ArriveGroups(Beat, Type, GroupSpecs, Centre, Bearing, Ids);
		return;
	}
	if (Type == TEXT("raid") || Type == TEXT("reinforcements"))
	{
		const TArray<TSharedPtr<FJsonObject>> Specs = ShipSpecs(TEXT("ships"));
		int32 k = 0;
		int32 LeaderIdx = INDEX_NONE;
		TArray<int32> RaidShips;
		for (const TSharedPtr<FJsonObject>& Spec : Specs)
		{
			if (k >= 8)
			{
				break;
			}
			FString Class, Name;
			Spec->TryGetStringField(TEXT("class"), Class);
			Spec->TryGetStringField(TEXT("name"), Name);
			const FString Id = TakeId();
			const FVector Pos = Centre + Polar(k == 0 ? 0.0 : 3.5 * OneKm, Bearing + 90.0 + 70.0 * k, (k % 2) ? 2.0 : -2.0);
			const int32 I = SpawnClass(Type == TEXT("reinforcements") && !Class.ToLower().Contains(TEXT("praetorian")) ? TEXT("vigilant") : Class, Id,
			                           Name.IsEmpty() ? Id : Name, Pos, Facing);
			if (Type == TEXT("raid") && Ships[I].SizeTier >= 2)
			{
				AddEnemyWing(I, 4, 30.f);
				Ships[I].Decoys = 4;
			}
			else if (Type == TEXT("raid") && Ships[I].SizeTier >= 1)
			{
				Ships[I].Decoys = 2;                      // a destroyer carries a pair of decoy emitters too
			}
			if (Type == TEXT("raid"))
			{
				// the fog of war: they come through dark; what the Aquila knows of them grows with her sensors (TickSensors)
				Ships[I].bFog = true;
				Ships[I].bDark = true;
				Ships[I].Track = 0;
				Ships[I].bClassified = false;
				Ships[I].bIdentified = false;
				// the leader goes for the Aquila; the others for her or one of the ASTRA warships with her (never
				// another ship that merely happens to be in the system)
				TArray<int32> Prey = {PlayerId};
				for (const FAstraBattleShip& O : Ships)
				{
					if (O.bAlive && !O.bPlayer && !O.bCraft && !O.bDerelict && O.Side == EAstraSide::Astra)
					{
						Prey.Add(O.Id);
					}
				}
				Ships[I].TargetId = k == 0 ? PlayerId : Prey[FMath::RandRange(0, Prey.Num() - 1)];
				if (k == 0)
				{
					Ships[I].bLeader = true;
					LeaderIdx = I;
				}
			}
			else
			{
				Ships[I].Mode = EAstraShipMode::Cruise;
			}
			Listing += FString::Printf(TEXT("%s%s (%s, %s)"), Listing.IsEmpty() ? TEXT("") : TEXT(", "), *Ships[I].Name, *Id, *Ships[I].Class);
			RaidShips.Add(Ships[I].Id);
			++k;
		}
		if (Type == TEXT("raid"))
		{
			bEngagementActive = true;
			bScenarioOver = false;
			bSurrenderAccepted = false;
			// the raid is one battle group, sent at the Aquila's position
			if (FAstraBattleShip* First = FindById(RaidShips.IsValidIndex(0) ? RaidShips[0] : -1))
			{
				const int32 Gid = NewGroup(EAstraSide::Mandate, FString::Printf(TEXT("Raid group %s"), *First->ContactId), EAstraFormation::Wedge);
				for (const int32 Rid : RaidShips)
				{
					if (FAstraBattleShip* RS = FindById(Rid))
					{
						JoinGroup(*RS, Gid);
					}
				}
				if (FAstraBattleGroup* RG = FindGroup(Gid))
				{
					RG->LeaderId = First->Id;
					RG->Objective = Ships[0].Pos;
					RG->bHasObjective = true;
				}
			}
			// (no listing here: the raid is under the fog of war, and the sensors report it as they find it)
			UE_LOG(LogASTRA, Log, TEXT("[Battle] raid in, dark: %d ships at %.0f km, bearing %03.0f — %s"), k, Range, Bearing, *Listing);
			bool bHail = true;
			Beat->TryGetBoolField(TEXT("hail"), bHail);
			if (bHail && LeaderIdx != INDEX_NONE)
			{
				TransmissionText = FString::Printf(TEXT("%s — the commander of the raid group, aboard the %s, hails the Aquila"), *Ships[LeaderIdx].ContactId, *Ships[LeaderIdx].Name);
				TransmissionAt = Time + 14.f;
			}
		}
		else
		{
			Report(FString::Printf(TEXT("sensors: friendly contacts at %.0f km, bearing %03.0f — %s, joining the 7th Fleet picket"), Range, Bearing, *Listing));
			bool bGranted = false;
			Beat->TryGetBoolField(TEXT("granted"), bGranted);
			if (!bGranted && !bEngagementActive)
			{
				Report(FString::Printf(TEXT("director: beat complete — reinforcements arrived (%s)"), *Listing), false);
			}
		}
		return;
	}
	if (Type == TEXT("distress"))
	{
		FString VName = TEXT("Morning Star"), VClass = TEXT("freighter");
		const TSharedPtr<FJsonObject>* Victim = nullptr;
		if (Beat->TryGetObjectField(TEXT("ship"), Victim))
		{
			(*Victim)->TryGetStringField(TEXT("name"), VName);
			(*Victim)->TryGetStringField(TEXT("class"), VClass);
		}
		const FString VId = TakeId();
		const int32 V = SpawnClass(TEXT("freighter"), VId, VName, Centre, Facing);
		Ships[V].Vel = Ships[V].Att.GetForwardVector() * 200.f;
		BuildDurability(Ships[V], 1500.f, 200.f);   // a big hauler takes a while to die: time for the Aquila to get there
		int32 k = 0;
		FString Attackers;
		int32 LeaderIdx = INDEX_NONE;
		for (const TSharedPtr<FJsonObject>& Spec : ShipSpecs(TEXT("attackers")))
		{
			if (k >= 6)
			{
				break;
			}
			FString Class, Name;
			Spec->TryGetStringField(TEXT("class"), Class);
			Spec->TryGetStringField(TEXT("name"), Name);
			const FString Id = TakeId();
			// the raiders come from further out, behind their prey
			const int32 I = SpawnClass(Class.IsEmpty() ? TEXT("lethe") : Class, Id, Name.IsEmpty() ? Id : Name,
			                           Centre + Polar(11.0 * OneKm, Bearing + FMath::FRandRange(-25.f, 25.f), 1.0), Facing);
			Ships[I].TargetId = Ships[V].Id;
			if (k == 0)
			{
				Ships[I].bLeader = true;
				LeaderIdx = I;
			}
			Attackers += FString::Printf(TEXT("%s%s (%s)"), Attackers.IsEmpty() ? TEXT("") : TEXT(", "), *Ships[I].Name, *Id);
			++k;
		}
		bEngagementActive = k > 0;
		bScenarioOver = false;
		Report(FString::Printf(TEXT("comms: distress call — the %s %s (%s) is under attack at %.0f km, bearing %03.0f, by %s"),
		                       VClass.Contains(TEXT("Guild")) ? *VClass : *(TEXT("Free Guilds ") + VClass), *VName, *VId, Range, Bearing,
		                       Attackers.IsEmpty() ? TEXT("unknown attackers") : *Attackers));
		(void)LeaderIdx;
	}
}

void UAstraBattleSubsystem::ScheduleOpeningForce(const TCHAR* Which, float At)
{
	// the forces of the opening's third stage, with the contact ids their commanders' minds know them by (mind/astra_mind/enemy.py COMMANDERS,
	// war_minds.py ALLIES): the vanguard is T-31..T-38, the relief T-03..T-06
	const bool bVanguard = FCString::Strcmp(Which, TEXT("vanguard")) == 0;
	const TCHAR* Json = bVanguard
		? TEXT(R"({"type":"raid","hail":false,"groups":[
			{"name":"Interdiction Vanguard","formation":"column","goes_for":"aquila","offset_km":[0,0],
			 "ships":[{"class":"acheron","name":"Nyx"},{"class":"styx","name":"Asphodel"}],
			 "wings":[{"carrier":0,"kind":"fighter","n":8,"mission":"strike"},{"carrier":0,"kind":"bomber","n":4,"mission":"strike"}]},
			{"name":"Styx Line Dorn","formation":"line","goes_for":"escorts","offset_km":[1.5,-6],
			 "ships":[{"class":"styx","name":"Tartarus"},{"class":"styx","name":"Hypnos"},{"class":"styx","name":"Thanatos"},{"class":"styx","name":"Erinys"}]},
			{"name":"Raider Wedge Morrow","formation":"wedge","goes_for":"escorts","offset_km":[2,7],
			 "ships":[{"class":"lethe","name":"Moros"},{"class":"lethe","name":"Keres"}]}]})")
		: TEXT(R"({"type":"reinforcements","granted":true,"groups":[
			{"name":"Battle Group Constance","formation":"line",
			 "ships":[{"class":"praetorian","name":"ASN Constance"},{"class":"vigilant","name":"ASN Steadfast"},{"class":"vigilant","name":"ASN Valour"},
			          {"class":"vigilant","name":"ASN Kestrel"}],
			 "wings":[{"carrier":0,"kind":"fighter","n":8,"mission":"cap"}]}]})");
	TSharedPtr<FJsonObject> Beat;
	if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Json), Beat) || !Beat.IsValid() || !Landmarks.IsValidIndex(GateLandmark))
	{
		return;
	}
	TArray<TSharedPtr<FJsonValue>> IdValues;
	for (const int32 n : bVanguard ? TArray<int32>({31, 32, 33, 34, 35, 36, 37, 38}) : TArray<int32>({3, 4, 5, 6}))
	{
		IdValues.Add(MakeShared<FJsonValueString>(FString::Printf(TEXT("T-%02d"), n)));
	}
	Beat->SetArrayField(TEXT("_ids"), IdValues);
	// the vanguard comes out of the gate's mouth on the Aquila's side; the relief from the other quarter, where New Ravenna lies
	const FVector Gate = Landmarks[GateLandmark].Pos;
	const FVector Us = Ships[0].Pos;
	const FVector ToUs = (Us - Gate).GetSafeNormal();
	const FVector Where = bVanguard ? Gate + ToUs * 4.0 * OneKm : Us + ToUs * 22.0 * OneKm;
	Beat->SetArrayField(TEXT("at_m"), {MakeShared<FJsonValueNumber>(Where.X), MakeShared<FJsonValueNumber>(Where.Y), MakeShared<FJsonValueNumber>(Where.Z)});
	PendingBeats.Add(TPair<float, TSharedPtr<FJsonObject>>(At, Beat));
}

void UAstraBattleSubsystem::ArriveGroups(const TSharedPtr<FJsonObject>& Beat, const FString& Type, const TArray<TSharedPtr<FJsonObject>>& Force,
                                         const FVector& Centre, double Bearing, const TArray<FString>& Ids)
{
	// A fleet-scale beat: each battle group comes in its own formation around its own point (offset_km: ahead towards the Aquila,
	// and to her right, from the beat's arrival point), with its leader first, its carriers' wings and its own objective; the
	// Mandate's come through dark under the fog of war, the 7th Fleet's are on the plot at once. The groups' commanders think
	// for them (war_minds.py: one seat per group).
	// whose a group is comes from its ships, not from the beat's word for it: an Acheron, a Styx, a Lethe are the Mandate's, a
	// Praetorian or a Vigilant the 7th Fleet's (a world fact; a "reinforcements" beat that brought a Styx line once turned it into
	// five ASTRA destroyers with Mandate names)
	const auto IsMandateClass = [](FString C)
	{
		C = C.ToLower();
		return C.Contains(TEXT("acheron")) || C.Contains(TEXT("styx")) || C.Contains(TEXT("lethe")) || C.Contains(TEXT("cruiser")) || C.Contains(TEXT("frigate"));
	};
	const auto IsAstraClass = [](FString C)
	{
		C = C.ToLower();
		return C.Contains(TEXT("praetorian")) || C.Contains(TEXT("vigilant")) || C.Contains(TEXT("battleship")) || C.Contains(TEXT("destroyer"));
	};
	bool bAnyRaid = false;
	const int32 PlayerId = Ships[0].Id;                  // copies: spawning may reallocate Ships
	const FVector PlayerPos = Ships[0].Pos;
	const FVector Fwd = (PlayerPos - Centre).GetSafeNormal2D().IsNearlyZero() ? FVector::ForwardVector : (PlayerPos - Centre).GetSafeNormal2D();
	const FVector Right = FVector::CrossProduct(FVector::UpVector, Fwd).GetSafeNormal();
	const float Facing = (float)FMath::Fmod(Bearing + 180.0, 360.0);
	int32 NextIdx = 0;
	int32 Total = 0;
	int32 FirstLeader = INDEX_NONE;
	TArray<FString> Listing, FriendlyListing;
	for (int32 g = 0; g < Force.Num(); ++g)
	{
		const TSharedPtr<FJsonObject>& G = Force[g];
		const TArray<TSharedPtr<FJsonValue>>* GShips = nullptr;
		G->TryGetArrayField(TEXT("ships"), GShips);
		// the group's side: its leader's class (else the beat's word)
		FString LeadClass;
		if (GShips && GShips->Num() && (*GShips)[0]->Type == EJson::Object)
		{
			(*GShips)[0]->AsObject()->TryGetStringField(TEXT("class"), LeadClass);
		}
		const bool bRaid = IsMandateClass(LeadClass) ? true : (IsAstraClass(LeadClass) ? false : Type == TEXT("raid"));
		const EAstraSide Side = bRaid ? EAstraSide::Mandate : EAstraSide::Astra;
		bAnyRaid |= bRaid;
		FString GName = FString::Printf(TEXT("%s group %d"), bRaid ? TEXT("Mandate") : TEXT("7th Fleet"), g + 1), Formation = bRaid ? TEXT("wedge") : TEXT("line"), GoesFor;
		G->TryGetStringField(TEXT("name"), GName);
		G->TryGetStringField(TEXT("formation"), Formation);
		G->TryGetStringField(TEXT("goes_for"), GoesFor);
		GoesFor = GoesFor.ToLower();
		FVector GC = Centre;
		const TArray<TSharedPtr<FJsonValue>>* Off = nullptr;
		if (G->TryGetArrayField(TEXT("offset_km"), Off) && Off->Num() >= 2)
		{
			GC += Fwd * FMath::Clamp((*Off)[0]->AsNumber(), -40.0, 40.0) * OneKm + Right * FMath::Clamp((*Off)[1]->AsNumber(), -40.0, 40.0) * OneKm;
		}
		const int32 NShips = GShips ? FMath::Min(GShips->Num(), MaxBeatGroupShips) : 0;
		const double Sp = (bRaid ? 1.6 : 1.8) * OneKm;
		TArray<int32> Made;
		for (int32 k = 0; k < NShips && Total < MaxBeatShips; ++k)
		{
			const TSharedPtr<FJsonObject> Spec = (*GShips)[k]->Type == EJson::Object ? (*GShips)[k]->AsObject() : nullptr;
			if (!Spec.IsValid())
			{
				continue;
			}
			FString Class, Name;
			Spec->TryGetStringField(TEXT("class"), Class);
			Spec->TryGetStringField(TEXT("name"), Name);
			Class = Class.ToLower();
			if (bRaid ? IsAstraClass(Class) : IsMandateClass(Class))
			{
				const FString Id = Ids.IsValidIndex(NextIdx) ? Ids[NextIdx++] : FString();   // (its id is spent: the ids follow the ships)
				UE_LOG(LogASTRA, Warning, TEXT("[Battle] a %s in a %s group left out (%s)"), *Class, bRaid ? TEXT("Mandate") : TEXT("7th Fleet"), *Id);
				continue;
			}
			if (!bRaid && !Class.Contains(TEXT("praetorian")))
			{
				Class = TEXT("vigilant");                       // the 7th Fleet sends what it has: battleships and destroyers
			}
			else if (bRaid && !(Class.Contains(TEXT("acheron")) || Class.Contains(TEXT("styx")) || Class.Contains(TEXT("lethe"))))
			{
				Class = TEXT("styx");
			}
			// the formation's slots, the leader at the point: line abreast, a wedge, a column (a screen spreads abreast ahead of its group)
			FVector Slot = GC;
			if (Formation == TEXT("column"))
			{
				Slot -= Fwd * (Sp * k);
			}
			else if (Formation == TEXT("wedge"))
			{
				const int32 Rank = (k + 1) / 2;
				Slot += Right * ((k % 2 ? 1.0 : -1.0) * Rank * Sp) - Fwd * (Sp * 0.8 * Rank);
			}
			else
			{
				Slot += Right * ((k - (NShips - 1) * 0.5) * Sp);
			}
			Slot.Z += FMath::FRandRange(-0.4f, 0.4f) * OneKm;
			const FString Id = Ids.IsValidIndex(NextIdx) ? Ids[NextIdx++] : FString::Printf(TEXT("T-%d"), NextContact++);
			const int32 I = SpawnClass(Class, Id, Name.IsEmpty() ? Id : Name, Slot, Facing);
			FAstraBattleShip& S = Ships[I];
			// a fleet that fought elsewhere arrives as it is (the March's strategic layer: hull, shields and magazines of each ship, when it says)
			double HullPct = 100.0, ShieldsPct = 100.0, Missiles = -1.0;
			if (Spec->TryGetNumberField(TEXT("hull_pct"), HullPct) && HullPct < 99.5)
			{
				SetHullFraction(S, (float)FMath::Clamp(HullPct, 5.0, 100.0) / 100.f);
			}
			if (Spec->TryGetNumberField(TEXT("shields_pct"), ShieldsPct) && ShieldsPct < 99.5)
			{
				const float K = (float)FMath::Clamp(ShieldsPct, 0.0, 100.0) / 100.f;
				if (S.Dmg.bModel)
				{
					for (int32 f = 0; f < AstraWar::NumFacings; ++f)
					{
						S.Dmg.Sector[f] = S.Dmg.SectorMax[f] * K;
					}
					SyncTotals(S);
				}
				else
				{
					S.Shield = S.ShieldMax * K;
				}
			}
			if (Spec->TryGetNumberField(TEXT("missiles"), Missiles) && Missiles >= 0.0)
			{
				S.Missiles = FMath::Min(S.Missiles, (int32)Missiles);
			}
			if (bRaid)
			{
				S.bFog = true;
				S.bDark = true;
				S.Track = 0;
				S.bClassified = false;
				S.bIdentified = false;
				S.Decoys = S.SizeTier >= 2 ? 4 : (S.SizeTier >= 1 ? 2 : 0);
			}
			else
			{
				S.Mode = EAstraShipMode::Cruise;
			}
			Made.Add(I);
			++Total;
		}
		if (Made.Num() == 0)
		{
			continue;
		}
		// what the group goes for: the Aquila, her consorts, the Janus Gate, or a contact on the plot
		TArray<int32> Prey;
		for (const FAstraBattleShip& O : Ships)
		{
			if (O.bAlive && !O.bPlayer && !O.bCraft && !O.bDerelict && O.Side == EAstraSide::Astra)
			{
				Prey.Add(O.Id);
			}
		}
		int32 TargetId = PlayerId;
		FVector Objective = PlayerPos;
		if (GoesFor == TEXT("escorts") && Prey.Num())
		{
			TargetId = Prey[FMath::RandRange(0, Prey.Num() - 1)];
		}
		else if (GoesFor == TEXT("gate") && Landmarks.IsValidIndex(GateLandmark))
		{
			Objective = Landmarks[GateLandmark].Pos;
		}
		else if (const FAstraBattleShip* T = GoesFor.IsEmpty() || GoesFor == TEXT("aquila") ? nullptr : FindByContact(GoesFor.ToUpper()))
		{
			TargetId = T->Id;
			Objective = T->Pos;
		}
		for (const int32 I : Made)
		{
			if (bRaid)
			{
				Ships[I].TargetId = TargetId;
			}
		}
		const int32 Gid = NoteGroupSpawn(Side, GName, Formation, Made, INDEX_NONE);
		if (FAstraBattleGroup* NG = FindGroup(Gid))
		{
			NG->Objective = bRaid || GoesFor.Len() ? Objective : PlayerPos;
			NG->bHasObjective = true;
		}
		Ships[Made[0]].bLeader = true;
		if (FirstLeader == INDEX_NONE)
		{
			FirstLeader = Made[0];
		}
		// the carriers' wings: Harpies (and Talon bombers) off an Acheron, Falcons and Hammers off a Praetorian
		const TArray<TSharedPtr<FJsonValue>>* Ws = nullptr;
		if (G->TryGetArrayField(TEXT("wings"), Ws))
		{
			for (const TSharedPtr<FJsonValue>& WV : *Ws)
			{
				const TSharedPtr<FJsonObject> WO = WV->Type == EJson::Object ? WV->AsObject() : nullptr;
				if (!WO.IsValid())
				{
					continue;
				}
				double CarrierK = 0.0, NCraft = 8.0;
				FString KindS = TEXT("fighter"), Mission = bRaid ? TEXT("strike") : TEXT("cap");
				WO->TryGetNumberField(TEXT("carrier"), CarrierK);
				WO->TryGetNumberField(TEXT("n"), NCraft);
				WO->TryGetStringField(TEXT("kind"), KindS);
				WO->TryGetStringField(TEXT("mission"), Mission);
				const int32 C = Made.IsValidIndex((int32)CarrierK) ? Made[(int32)CarrierK] : Made[0];
				if (Ships[C].SizeTier < 2)
				{
					continue;                                    // only a carrier launches: an Acheron or a Praetorian
				}
				const int32 Kind = KindS.StartsWith(TEXT("b")) ? 1 : (KindS.StartsWith(TEXT("d")) ? 2 : 0);
				const int32 Q = AddWing(C, Kind, FMath::Clamp((int32)NCraft, 2, 16), Mission.ToLower(), FMath::FRandRange(20.f, 45.f));
				if (bRaid && Squadrons.IsValidIndex(Q) && Mission.ToLower() == TEXT("strike"))
				{
					Squadrons[Q].TargetId = TargetId;
				}
			}
		}
		Listing.Add(FString::Printf(TEXT("%s: %d ships"), *GName, Made.Num()));
		if (!bRaid)
		{
			FriendlyListing.Add(Listing.Last());
		}
	}
	if (bAnyRaid)
	{
		bEngagementActive = true;
		bScenarioOver = false;
		bSurrenderAccepted = false;
		UE_LOG(LogASTRA, Log, TEXT("[Battle] a Mandate force in, dark: %d ships in %d groups at %.0f km, bearing %03.0f — %s"), Total, Force.Num(),
		       (Centre - PlayerPos).Size() / OneKm, Bearing, *FString::Join(Listing, TEXT("; ")));
		bool bHail = true;
		Beat->TryGetBoolField(TEXT("hail"), bHail);
		if (bHail && FirstLeader != INDEX_NONE)
		{
			TransmissionText = FString::Printf(TEXT("%s — the commander of the Mandate force, aboard the %s, hails the Aquila"), *Ships[FirstLeader].ContactId, *Ships[FirstLeader].Name);
			TransmissionAt = Time + 14.f;
		}
	}
	if (FriendlyListing.Num())
	{
		Report(FString::Printf(TEXT("sensors: friendly contacts at %.0f km, bearing %03.0f — the 7th Fleet: %s"), (Centre - PlayerPos).Size() / OneKm, Bearing,
		                       *FString::Join(FriendlyListing, TEXT("; "))));
		bool bGranted = false;
		Beat->TryGetBoolField(TEXT("granted"), bGranted);
		if (!bGranted && !bEngagementActive)
		{
			Report(FString::Printf(TEXT("director: beat complete — reinforcements arrived (%s)"), *FString::Join(FriendlyListing, TEXT("; "))), false);
		}
	}
}

void UAstraBattleSubsystem::HullSound(const TCHAR* Name, float Volume, float MinInterval)
{
	const FName Key(Name);
	const float RealTime = GetWorld() ? GetWorld()->GetRealTimeSeconds() : 0.f;
	if (const float* Last = SoundLast.Find(Key); Last && RealTime - *Last < MinInterval)
	{
		return;
	}
	TObjectPtr<USoundBase>& S = Sounds.FindOrAdd(Key);
	if (!S)
	{
		S = LoadObject<USoundBase>(nullptr, *FString::Printf(TEXT("/Game/ASTRA/Audio/%s.%s"), Name, Name));
	}
	if (S)
	{
		SoundLast.Add(Key, RealTime);
		UGameplayStatics::PlaySound2D(GetWorld(), S, Volume, FMath::FRandRange(0.95f, 1.05f));
	}
}

// ---------------------------------------------------------------------------------------------- Janus transit
void UAstraBattleSubsystem::SpawnGate(const FVector& Pos, const FQuat& Att)
{
	UStaticMesh* GateMesh = LoadObject<UStaticMesh>(nullptr, TEXT("/Game/ASTRA/Space/SM_JANUS_Gate.SM_JANUS_Gate"));
	if (!GateMesh || !GetWorld())
	{
		return;
	}
	FAstraWreck G;
	G.Pos = Pos;
	G.Att = Att;
	G.SpinDeg = 0.f;
	FActorSpawnParameters GP;
	GP.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	G.Actor = GetWorld()->SpawnActor<AStaticMeshActor>(FVector::ZeroVector, FRotator::ZeroRotator, GP);
	G.Actor->SetMobility(EComponentMobility::Movable);
	UStaticMeshComponent* GC = G.Actor->GetStaticMeshComponent();
	GC->SetStaticMesh(GateMesh);
	GC->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	GC->SetCastShadow(false);
	GC->bAffectDistanceFieldLighting = false;
	GC->SetLightingChannels(true, true, false);
	GateGlyphMID = nullptr;
	for (int32 i = 0; i < GC->GetNumMaterials(); ++i)
	{
		if (const UMaterialInterface* M = GC->GetMaterial(i); M && M->GetName().Contains(TEXT("Glyph")))
		{
			GateGlyphMID = GC->CreateAndSetMaterialInstanceDynamic(i);
		}
	}
	Landmarks.Add(G);
	GateLandmark = Landmarks.Num() - 1;
	LaneRingMIDs.Reset();
	LaneRingIdx.Reset();
	LaneRingAxial.Reset();
	UStaticMesh* RingM = LoadObject<UStaticMesh>(nullptr, TEXT("/Game/ASTRA/Space/SM_JANUS_LaneRing.SM_JANUS_LaneRing"));
	if (!RingM || !GlowMat)
	{
		return;
	}
	for (const int32 Side : {1, -1})
	{
		for (int32 k = 1; k <= 9; ++k)
		{
			FAstraWreck W;
			W.Pos = Pos + Att.GetForwardVector() * (Side * k * LaneRingStepM);
			W.Att = Att * FQuat(FVector::XAxisVector, FMath::DegreesToRadians(k * 4.f));
			W.SpinDeg = 0.f;
			FActorSpawnParameters RP;
			RP.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
			W.Actor = GetWorld()->SpawnActor<AStaticMeshActor>(FVector::ZeroVector, FRotator::ZeroRotator, RP);
			W.Actor->SetMobility(EComponentMobility::Movable);
			UStaticMeshComponent* RC = W.Actor->GetStaticMeshComponent();
			RC->SetStaticMesh(RingM);
			RC->SetCollisionEnabled(ECollisionEnabled::NoCollision);
			RC->SetCastShadow(false);
			UMaterialInstanceDynamic* M = RC->CreateAndSetMaterialInstanceDynamicFromMaterial(0, GlowMat);
			M->SetVectorParameterValue(TEXT("Color"), FLinearColor(0.55f, 0.85f, 1.f));
			M->SetScalarParameterValue(TEXT("Intensity"), 0.f);
			W.Actor->SetActorHiddenInGame(true);
			Landmarks.Add(W);
			LaneRingIdx.Add(Landmarks.Num() - 1);
			LaneRingMIDs.Add(M);
			LaneRingAxial.Add(Side * k * LaneRingStepM);
		}
	}
}

bool UAstraBattleSubsystem::BeginGateRun(const TSharedPtr<FJsonObject>& Args, FString& OutDetail)
{
	FString Name, Star, Planet, PName;
	if (Args.IsValid())
	{
		Args->TryGetStringField(TEXT("system_name"), Name);
		Args->TryGetStringField(TEXT("star_class"), Star);
		Args->TryGetStringField(TEXT("planet_type"), Planet);
		Args->TryGetStringField(TEXT("planet_name"), PName);
	}
	Name.TrimStartAndEndInline();
	if (Name.IsEmpty())
	{
		Name = FleetOrderedDest;   // "take us through" = where Fleet sends us
	}
	UAstraShipSubsystem* Ship = GetWorld() ? GetWorld()->GetSubsystem<UAstraShipSubsystem>() : nullptr;
	if (Name.IsEmpty())
	{
		OutDetail = TEXT("which system? Keeper Station needs a destination to tune the gate");
		return false;
	}
	if (!Ship || Ships.Num() == 0 || !Landmarks.IsValidIndex(GateLandmark))
	{
		OutDetail = TEXT("there is no Janus Gate in this system");
		return false;
	}
	if (GateRun == EAstraGateRun::Lane)
	{
		OutDetail = FString::Printf(TEXT("already in the gate's lane to the %s system"), *GateDest);
		return false;
	}
	if (Name.Equals(Ship->GetSystemName(), ESearchCase::IgnoreCase))
	{
		OutDetail = FString::Printf(TEXT("the Aquila is already in the %s system"), *Ship->GetSystemName());
		return false;
	}
	// a Gate is bound to a few others only: Keeper Station can tune it to one of those
	if (const FAstraSectorSystem* Here = Ship->FindSector(Ship->GetSystemName()))
	{
		const FString* Dest = Here->Links.FindByPredicate([&Name](const FString& L) { return L.Equals(Name, ESearchCase::IgnoreCase); });
		if (!Dest)
		{
			OutDetail = FString::Printf(TEXT("the Janus Gate in %s is bound only to %s: Keeper Station cannot reach %s from here"),
			                            *Here->Name, *FString::Join(Here->Links, TEXT(", ")), *Name);
			return false;
		}
		Name = *Dest;
	}
	const FAstraSystemLook L = Ship->ChartSystem(Name, Star, Planet, PName);
	TransitBeat = MakeShared<FJsonObject>();
	TransitBeat->SetStringField(TEXT("system_name"), L.Name);
	TransitBeat->SetStringField(TEXT("star_class"), L.StarClass);
	TransitBeat->SetStringField(TEXT("planet_type"), L.PlanetType);
	TransitBeat->SetStringField(TEXT("planet_name"), L.PlanetName);
	GateDest = L.Name;
	const FAstraWreck& G = Landmarks[GateLandmark];
	const FVector Axis = G.Att.GetForwardVector();
	GateSide = FVector::DotProduct(Ships[0].Pos - G.Pos, Axis) >= 0.0 ? 1.f : -1.f;
	GateRun = EAstraGateRun::Approach;
	GateSteerT = 0.f;
	Ship->SetThrottle(100.f);
	const FVector Aim = G.Pos + Axis * GateSide * LaneEntryKm * OneKm;
	const double D = FVector::Dist(Ships[0].Pos, Aim);
	OutDetail = FString::Printf(TEXT("course laid in for the Janus Gate (bearing %03.0f, %.0f km); Keeper Station tunes it to the %s system (%s star). "
	                                 "Full ahead to the approach lane %.0f km off the ring, where the gate's field takes the ship and draws her "
	                                 "through (no turning back once in the lane); transit in about %s%s"),
	                            BearingDeg(Ships[0].Pos, G.Pos), FVector::Dist(Ships[0].Pos, G.Pos) / OneKm, *L.Name, *L.StarClass.Replace(TEXT("_"), TEXT("-")),
	                            LaneEntryKm, *EtaText(D / 480.0 + 22.0), bEngagementActive ? TEXT(" — the engagement will be left behind") : TEXT(""));
	Report(FString::Printf(TEXT("helm: Janus approach to the %s system begun"), *L.Name), false);
	return true;
}

void UAstraBattleSubsystem::AbortGateRun()
{
	if (GateRun == EAstraGateRun::Approach)
	{
		GateRun = EAstraGateRun::None;
		Report(FString::Printf(TEXT("helm: Janus approach to the %s system cancelled"), *GateDest), false);
		GateDest.Empty();
	}
}

TSharedRef<FJsonObject> UAstraBattleSubsystem::SaveJson() const
{
	TSharedRef<FJsonObject> O = MakeShared<FJsonObject>();
	if (Ships.Num() == 0)
	{
		return O;
	}
	const FAstraBattleShip& P = Ships[0];
	O->SetNumberField(TEXT("hull_frac"), P.Hull / P.HullMax);
	O->SetNumberField(TEXT("missiles"), P.Missiles);
	O->SetNumberField(TEXT("torpedoes"), P.Torpedoes);
	TArray<TSharedPtr<FJsonValue>> Q;
	for (const FAstraSquadron& S : Squadrons)
	{
		if (S.Side != EAstraSide::Astra)
		{
			continue;
		}
		TSharedRef<FJsonObject> J = MakeShared<FJsonObject>();
		J->SetStringField(TEXT("name"), S.Name);
		J->SetNumberField(TEXT("total"), S.Total);
		Q.Add(MakeShared<FJsonValueObject>(J));
	}
	O->SetArrayField(TEXT("squadrons"), Q);
	return O;
}

void UAstraBattleSubsystem::ResumeFrom(const TSharedPtr<FJsonObject>& Save)
{
	if (!Save.IsValid() || Ships.Num() == 0)
	{
		return;
	}
	ClearSystem();
	StageDone = OpeningOver;
	bBriefed = true;
	FAstraBattleShip& P = Ships[0];
	P.Pos = FVector::ZeroVector;
	double V = 1.0;
	if (Save->TryGetNumberField(TEXT("hull_frac"), V)) { SetHullFraction(P, FMath::Clamp((float)V, 0.05f, 1.f)); }
	if (Save->TryGetNumberField(TEXT("missiles"), V)) { P.Missiles = (int32)V; }
	if (Save->TryGetNumberField(TEXT("torpedoes"), V)) { P.Torpedoes = (int32)V; }
	const TArray<TSharedPtr<FJsonValue>>* Q = nullptr;
	if (Save->TryGetArrayField(TEXT("squadrons"), Q))
	{
		for (const TSharedPtr<FJsonValue>& J : *Q)
		{
			const TSharedPtr<FJsonObject> O = J->AsObject();
			FString Name;
			double Total = 0.0;
			if (O.IsValid() && O->TryGetStringField(TEXT("name"), Name) && O->TryGetNumberField(TEXT("total"), Total))
			{
				if (FAstraSquadron* S = Squadrons.FindByPredicate([&Name](const FAstraSquadron& X) { return X.Name == Name; }))
				{
					S->Total = S->OnDeck = FMath::Max(0, (int32)Total);
				}
			}
		}
	}
	// the system's gate, some way off the bow
	const FVector GPos = P.Pos + Polar(70 * OneKm, P.Att.Rotator().Yaw + 35.0, 2.0);
	SpawnGate(GPos, FRotationMatrix::MakeFromX((P.Pos - GPos).GetSafeNormal()).ToQuat() * FQuat(FVector::XAxisVector, 0.8f));
	SyncVisuals();
	bStarted = true;
	Report(TEXT("bridge: the Captain returns to the bridge after the watch change — the XO welcomes them back and sums up in two or "
	            "three short lines where the Aquila is, her state, and what the war needs from her now"));
}

void UAstraBattleSubsystem::RevealPOI(FAstraPOI& Poi)
{
	if (Poi.Revealed >= Poi.Findings.Num())
	{
		return;
	}
	const FString& F = Poi.Findings[Poi.Revealed++];
	Poi.NextRevealT = Time + 8.f;
	Report(FString::Printf(TEXT("sensors: %s — %s"), *Poi.Name, *F));
	Report(FString::Printf(TEXT("story: at %s the crew learned: %s"), *Poi.Name, *F), false);
	if (Poi.Revealed >= Poi.Findings.Num() && !Poi.bDone)
	{
		Poi.bDone = true;
		if (!bEngagementActive)
		{
			Report(FString::Printf(TEXT("director: beat complete — investigation of %s: %s"), *Poi.Name, *FString::Join(Poi.Findings, TEXT(" / "))), false);
		}
	}
}

void UAstraBattleSubsystem::TickPOIs(float Dt)
{
	for (FAstraPOI& Poi : POIs)
	{
		const FAstraBattleShip* S = FindById(Poi.ShipId);
		if (!S || !S->bAlive || Ships.Num() == 0)
		{
			continue;
		}
		const double D = FVector::Dist(Ships[0].Pos, S->Pos);
		// the ambush wakes when the Aquila is close enough to be sure of her
		if (!Poi.bAmbushSprung && Poi.Ambush.Num() && D < Poi.AmbushKm * OneKm)
		{
			Poi.bAmbushSprung = true;
			int32 N = 0;
			for (const int32 Id : Poi.Ambush)
			{
				if (FAstraBattleShip* A = FindById(Id); A && A->bAlive)
				{
					A->bCold = false;
					A->bHostile = true;
					A->bIdentified = A->bClassified = true;
					A->Mode = EAstraShipMode::Attack;
					A->TargetId = Ships[0].Id;
					++N;
				}
			}
			if (N)
			{
				bEngagementActive = true;
				bScenarioOver = false;
				Report(FString::Printf(TEXT("sensors: drives lighting up around %s — %d Kharon Mandate warship%s lying cold: it is an ambush!"),
				                       *Poi.Name, N, N > 1 ? TEXT("s were") : TEXT(" was")));
				const FAstraBattleShip* Lead = FindById(Poi.Ambush[0]);
				if (Lead && Lead->bAlive)
				{
					TransmissionAt = Time + 10.f;
					TransmissionText = FString::Printf(TEXT("%s — the ambush's commander hails the Aquila"), *Lead->ContactId);
				}
			}
		}
		if (Poi.Revealed >= Poi.Findings.Num() || Time < Poi.NextRevealT)
		{
			continue;
		}
		// what the crew learns without a scan: a flight group reaching it, the Aquila closing in, alongside
		bool bCraftThere = false;
		for (const FAstraBattleShip& C : Ships)
		{
			bCraftThere |= C.bAlive && C.bCraft && C.Side == EAstraSide::Astra && FVector::Dist(C.Pos, S->Pos) < 1500.0;
		}
		if ((Poi.Revealed == 0 && D < 8 * OneKm) || (Poi.Revealed == 1 && (D < 5 * OneKm || bCraftThere)) || (Poi.Revealed == 2 && D < 2 * OneKm))
		{
			RevealPOI(Poi);
		}
	}
}

void UAstraBattleSubsystem::GetDeckState(TMap<FString, int32>& Out) const
{
	for (const FAstraSquadron& Q : Squadrons)
	{
		if (Q.Side == EAstraSide::Astra)
		{
			Out.Add(Q.Name, Q.OnDeck);
		}
	}
}

int32 UAstraBattleSubsystem::HostilesFighting(double WithinKm) const
{
	int32 N = 0;
	for (const FAstraBattleShip& S : Ships)
	{
		if (S.bAlive && S.bHostile && !S.bDisabled && !S.bCraft && !S.bFleeing && !S.bHoldFire && FVector::Dist(S.Pos, Ships[0].Pos) < WithinKm * OneKm)
		{
			++N;
		}
	}
	return N;
}

double UAstraBattleSubsystem::GateDistanceKm() const
{
	if (!Landmarks.IsValidIndex(GateLandmark) || Ships.Num() == 0)
	{
		return -1.0;
	}
	return FVector::Dist(Ships[0].Pos, Landmarks[GateLandmark].Pos) / OneKm;
}

FString UAstraBattleSubsystem::GateStatus() const
{
	if (!Landmarks.IsValidIndex(GateLandmark) || Ships.Num() == 0)
	{
		return TEXT("no Janus Gate in this system");
	}
	const FAstraWreck& G = Landmarks[GateLandmark];
	const FAstraBattleShip& P = Ships[0];
	FString Out = FString::Printf(TEXT("Janus Gate: bearing %03.0f mark %.0f, %.1f km"), BearingDeg(P.Pos, G.Pos), MarkDeg(P.Pos, G.Pos),
	                              FVector::Dist(P.Pos, G.Pos) / OneKm);
	if (const UAstraShipSubsystem* Ship = GetWorld() ? GetWorld()->GetSubsystem<UAstraShipSubsystem>() : nullptr)
	{
		if (const FAstraSectorSystem* Here = Ship->FindSector(Ship->GetSystemName()))
		{
			Out += FString::Printf(TEXT(", bound to %s"), *FString::Join(Here->Links, TEXT(", ")));
		}
	}
	if (GateRun == EAstraGateRun::Approach)
	{
		const FVector Aim = G.Pos + G.Att.GetForwardVector() * GateSide * LaneEntryKm * OneKm;
		const double D = FVector::Dist(P.Pos, Aim);
		Out += FString::Printf(TEXT("; Janus approach to the %s system under way: %.0f km to the lane, transit in about %s"), *GateDest, D / OneKm,
		                       *EtaText(D / FMath::Max(150.0, (double)P.Vel.Size()) + 22.0));
	}
	else if (GateRun == EAstraGateRun::Lane)
	{
		Out += FString::Printf(TEXT("; in the gate's lane to the %s system: helm locked, transit in %.0f s"), *GateDest, FMath::Max(0.0, LaneDur - LaneT));
	}
	else if (!FleetOrderedDest.IsEmpty())
	{
		Out += FString::Printf(TEXT("; Fleet orders a transit to the %s system (the gate is tuned for us): the helm lays in the approach on the "
		                            "Captain's order"), *FleetOrderedDest);
	}
	return Out;
}

void UAstraBattleSubsystem::TickGateRun(float Dt)
{
	// the ring's glyphs: calm, tuned (a slow pulse), spinning up in the lane, hot after a transit
	const float Pulse = 0.5f + 0.5f * FMath::Sin(Time * 1.7f);
	GateHeat = FMath::Max(0.f, GateHeat - Dt / 14.f);
	float Glow = 1.f;
	if (GateRun == EAstraGateRun::Lane)
	{
		const float X = (float)FMath::Clamp(LaneT / LaneDur, 0.0, 1.0);
		Glow = 2.5f + 16.f * X * X;
	}
	else if (GateRun == EAstraGateRun::Approach || !FleetOrderedDest.IsEmpty())
	{
		Glow = 1.6f + 0.9f * Pulse;
	}
	Glow = FMath::Max(Glow, 1.f + 10.f * GateHeat * GateHeat);
	if (GateGlyphMID)
	{
		GateGlyphMID->SetScalarParameterValue(TEXT("Intensity"), 70.f * Glow);
		const float W = FMath::Clamp((Glow - 1.f) / 12.f, 0.f, 1.f);
		GateGlyphMID->SetVectorParameterValue(TEXT("EmissiveColor"), FMath::Lerp(FLinearColor(0.55f, 0.85f, 1.f), FLinearColor(0.9f, 0.96f, 1.f), W));
	}
	// the lane's markers on our face of the ring: dark when the gate is idle; tuned, a slow wave of light runs along them
	// into the ring; in the lane they blaze and the wave races; after a transit they cool down with the ring
	if (Landmarks.IsValidIndex(GateLandmark) && Ships.Num() > 0)
	{
		const FAstraWreck& G0 = Landmarks[GateLandmark];
		const bool bTuned = GateRun != EAstraGateRun::None || !FleetOrderedDest.IsEmpty();
		const float Side = GateRun != EAstraGateRun::None ? GateSide
		                 : (FVector::DotProduct(Ships[0].Pos - G0.Pos, G0.Att.GetForwardVector()) >= 0.0 ? 1.f : -1.f);
		const bool bLane = GateRun == EAstraGateRun::Lane;
		const float WaveSpeed = bLane ? 3.f : 0.9f;                 // rings per second
		const float Wave = 9.5f - FMath::Fmod(Time * WaveSpeed, 11.f);  // ring index the band is on (9 -> 0)
		for (int32 i = 0; i < LaneRingMIDs.Num(); ++i)
		{
			if (!LaneRingMIDs[i] || !Landmarks.IsValidIndex(LaneRingIdx[i]) || !Landmarks[LaneRingIdx[i]].Actor)
			{
				continue;
			}
			const float Axial = LaneRingAxial[i];
			const float K = FMath::Abs(Axial) / LaneRingStepM;
			float B = 0.f;
			if (Axial * Side > 0.f)
			{
				if (bTuned)
				{
					B = (bLane ? 0.7f : 0.22f) + FMath::Exp(-FMath::Square(K - Wave) / 0.7f) * (bLane ? 1.6f : 1.f);
				}
				B = FMath::Max(B, GateHeat * GateHeat * 1.5f);
			}
			AActor* RA = Landmarks[LaneRingIdx[i]].Actor;
			RA->SetActorHiddenInGame(B < 0.01f);
			LaneRingMIDs[i]->SetScalarParameterValue(TEXT("Intensity"), 70.f * B);
		}
	}
	if (GateRun == EAstraGateRun::None || !Landmarks.IsValidIndex(GateLandmark) || Ships.Num() == 0)
	{
		return;
	}
	UAstraShipSubsystem* Ship = GetWorld()->GetSubsystem<UAstraShipSubsystem>();
	if (!Ship)
	{
		return;
	}
	FAstraBattleShip& P = Ships[0];
	const FAstraWreck& G = Landmarks[GateLandmark];
	const FVector N = G.Att.GetForwardVector() * GateSide;   // out of the ring, towards our side
	if (GateRun == EAstraGateRun::Approach)
	{
		const FVector Rel = P.Pos - G.Pos;
		const double A = FVector::DotProduct(Rel, N);
		const double R = (Rel - N * A).Size();
		const FVector F = P.Att.GetForwardVector();
		// inside the approach cone, bow towards the ring: the lane field takes the ship
		if (A > 3 * OneKm && A < 2 * LaneEntryKm * OneKm && R < 0.5 * A + 4 * OneKm && FVector::DotProduct(F, -N) > 0.35)
		{
			GateRun = EAstraGateRun::Lane;
			LaneT = 0.0;
			LaneP0 = P.Pos;
			LaneP1 = G.Pos;
			const double L = FVector::Dist(LaneP0, LaneP1);
			LaneT0 = F * L;
			LaneT1 = -N * L;
			LaneDur = FMath::Clamp(L / 1250.0, 12.0, 32.0);
			LaneK = FMath::Clamp(FMath::Max(150.0, (double)P.Vel.Size()) * LaneDur / L, 0.05, 1.0);
			bLaneSound = bLaneFade = false;
			Ship->SetLaneControl(true);
			Report(FString::Printf(TEXT("helm: the gate's lane field has the Aquila — helm locked, transit to the %s system in %.0f seconds"),
			                       *GateDest, LaneDur));
			return;
		}
		if ((GateSteerT -= Dt) <= 0.f)
		{
			GateSteerT = 0.5f;
			const FVector Aim = G.Pos + N * LaneEntryKm * OneKm;
			Ship->SteerTo((float)BearingDeg(P.Pos, Aim), (float)MarkDeg(P.Pos, Aim));
		}
		return;
	}
	// in the lane: a smooth path from where the field took us to the heart of the ring, faster and faster
	LaneT += Dt;
	const double X = FMath::Clamp(LaneT / LaneDur, 0.0, 1.0);
	const double U = LaneK * X + (1.0 - LaneK) * X * X;
	const double DUdt = (LaneK + 2.0 * (1.0 - LaneK) * X) / LaneDur;
	const double U2 = U * U, U3 = U2 * U;
	const FVector Pos = LaneP0 * (2 * U3 - 3 * U2 + 1) + LaneT0 * (U3 - 2 * U2 + U) + LaneP1 * (-2 * U3 + 3 * U2) + LaneT1 * (U3 - U2);
	const FVector Tan = LaneP0 * (6 * U2 - 6 * U) + LaneT0 * (3 * U2 - 4 * U + 1) + LaneP1 * (-6 * U2 + 6 * U) + LaneT1 * (3 * U2 - 2 * U);
	const FVector Dir = Tan.GetSafeNormal();
	const float H = FMath::RadiansToDegrees(FMath::Atan2(Dir.Y, Dir.X));
	const float M = FMath::RadiansToDegrees(FMath::Atan2(Dir.Z, FVector2D(Dir.X, Dir.Y).Size()));
	P.Vel = Tan * DUdt;
	P.Pos = Pos;
	Ship->DriveExternally(H, M, (float)P.Vel.Size());
	P.Att = FRotator(M, H, 0.f).Quaternion();
	Shake = FMath::Max(Shake, (float)(0.08 + 0.4 * X * X * X));
	if (!bLaneSound && LaneT >= LaneDur - 2.3)
	{
		bLaneSound = true;   // the recording's crack lands on the crossing
		HullSound(TEXT("SW_Transit"), 1.f, 0.f);
	}
	if (!bLaneFade && LaneT >= LaneDur - 0.35)
	{
		bLaneFade = true;
		if (APlayerCameraManager* Cam = UGameplayStatics::GetPlayerCameraManager(this, 0))
		{
			Cam->StartCameraFade(0.f, 1.f, 0.35f, FLinearColor::White, false, true);
		}
	}
	if (X >= 1.0)
	{
		DoTransit(TransitBeat);
	}
}

void UAstraBattleSubsystem::ClearSystem()
{
	// everything left behind in the old system (our own aircraft come aboard first)
	for (int32 i = Ships.Num() - 1; i >= 1; --i)
	{
		FAstraBattleShip& S = Ships[i];
		if (S.bCraft && S.bAlive && S.Side == EAstraSide::Astra && Squadrons.IsValidIndex(S.Squadron))
		{
			++Squadrons[S.Squadron].OnDeck;
		}
		if (S.Actor) { S.Actor->Destroy(); }
		if (S.ShieldBubble) { S.ShieldBubble->Destroy(); }
		if (S.DriveFlare) { S.DriveFlare->Destroy(); }
	}
	Ships.SetNum(1);
	RebuildIdIndex();
	++PlotStamp;
	Groups.Reset();
	GroupEvents.Reset();                          // (what happened to the old system's groups is not news here)
	Flights.Reset();
	WingToLaunch = 0;                             // (and the Captain's wing is gone with them)
	WingFlightId = -1;
	POIs.Reset();
	Squadrons.RemoveAll([](const FAstraSquadron& Q) { return Q.Side != EAstraSide::Astra; });
	for (FAstraSquadron& Q : Squadrons)
	{
		Q.ToLaunch = 0;
		Q.Mission = TEXT("recall");
	}
	for (FAstraProjectile& Pr : Projectiles)
	{
		if (Pr.Actor) { Pr.Actor->Destroy(); }
		if (Pr.Trail) { Pr.Trail->Destroy(); }
	}
	Projectiles.Reset();
	if (WarFX)
	{
		WarFX->ClearAll();                            // its shots, sparks, shells, pieces and scars are of the old system
	}
	if (WarDraw)
	{
		WarDraw->ClearAll();                          // the craft and the lamps of the old system
	}
	for (FAstraFlash& F : Flashes)
	{
		if (F.Actor) { F.Actor->Destroy(); }
	}
	Flashes.Reset();
	for (TArray<FAstraWreck>* List : {&Wrecks, &Landmarks})
	{
		for (FAstraWreck& W : *List)
		{
			if (W.Actor) { W.Actor->Destroy(); }
		}
		List->Reset();
	}
	PendingBeats.Reset();
	TransmissionNotes.Reset();
	TransmissionAt = -1.f;
	bEngagementActive = false;
	bScenarioOver = false;
	bSurrenderAccepted = false;
	StageDone = OpeningOver;
}

void UAstraBattleSubsystem::DoTransit(const TSharedPtr<FJsonObject>& Beat)
{
	if (!Beat.IsValid() || Ships.Num() == 0)
	{
		return;
	}
	FString Name = TEXT("Unknown"), Star, Planet, PName;
	Beat->TryGetStringField(TEXT("system_name"), Name);
	Beat->TryGetStringField(TEXT("star_class"), Star);
	Beat->TryGetStringField(TEXT("planet_type"), Planet);
	Beat->TryGetStringField(TEXT("planet_name"), PName);
	UAstraShipSubsystem* Ship = GetWorld()->GetSubsystem<UAstraShipSubsystem>();
	const FString From = Ship ? Ship->GetSystemName() : FString(TEXT("Aurelia"));
	const bool bLeftFight = bEngagementActive;
	const float ExitSpeed = FMath::Max(600.f, (float)Ships[0].Vel.Size());
	// the gate's flash and the jolt through the hull (the sound was started in the lane, timed to the crossing)
	if (APlayerCameraManager* Cam = UGameplayStatics::GetPlayerCameraManager(this, 0))
	{
		Cam->StartCameraFade(1.f, 0.f, 3.5f, FLinearColor::White, false, false);
	}
	Shake = 1.f;
	if (!bLaneSound)
	{
		HullSound(TEXT("SW_Transit"), 1.f, 0.f);
	}
	ClearSystem();
	Ships[0].Pos = FVector::ZeroVector;
	// out of the destination's gate: its ring right behind us, the ship still carrying the lane's speed
	const FVector Bow = Ships[0].Att.GetForwardVector();
	GateLandmark = INDEX_NONE;
	SpawnGate(Ships[0].Pos - Bow * 1.5 * OneKm, FRotationMatrix::MakeFromX(Bow).ToQuat() * FQuat(FVector::XAxisVector, FMath::FRandRange(0.f, 1.f)));
	GateHeat = 1.f;
	GateRun = EAstraGateRun::None;
	FleetOrderedDest.Empty();
	GateDest.Empty();
	// the new sky: star, main world, nebula tint (a charted system always looks the same)
	FAstraSystemLook L;
	if (Ship)
	{
		L = Ship->ChartSystem(Name, Star, Planet, PName);
		Ship->SetLaneControl(false);
		Ship->SetSpeedMps(ExitSpeed);
		Ship->SetThrottle(40.f);
		Ship->ApplySystem(L);
	}
	Name = L.Name;
	Star = L.StarClass;
	Planet = L.PlanetType;
	PName = L.PlanetName;
	SyncVisuals();
	const bool bHome = Name.Equals(TEXT("Aurelia"), ESearchCase::IgnoreCase);
	Report(FString::Printf(TEXT("helm: transit complete — the Aquila is through the gate into the %s system (%s star)%s; coasting out of the "
	                            "lane at %.0f m/s, throttle 40%%"), *Name, *Star.Replace(TEXT("_"), TEXT(" ")),
	                       bHome ? TEXT(", home: New Ravenna in the distance")
	                             : *FString::Printf(TEXT("; the %s world %s ahead"), *Planet.Replace(TEXT("_"), TEXT(" ")), *PName), ExitSpeed));
	Report(FString::Printf(TEXT("director: beat complete — transit from %s into the %s system (%s star, %s world %s)%s"), *From, *Name, *Star, *Planet,
	                       *PName, bLeftFight ? TEXT("; the Aquila left an engagement behind") : TEXT("")), false);
}

// ------------------------------------------------------------------------------------------ the Captain's Falcon
FVector UAstraBattleSubsystem::FromWorld(const FVector& WorldCm) const
{
	const FAstraBattleShip& P = Ships[0];
	return P.Pos + P.Att.RotateVector(WorldCm / 100.0 + BridgeOffset);
}

bool UAstraBattleSubsystem::PilotCollision(FAstraBattleShip& S, const FVector& Prev)
{
	FString What;
	// the Aquila's hull is solid (the level's actor has its collision), except at the tube she launches and
	// recovers the Falcon through
	const FAstraBattleShip& A = Ships[0];
	if (A.bAlive && FVector::Dist(S.Pos, A.Pos) < 900.0 && FVector::Dist(S.Pos, PilotMouth()) > 70.0)
	{
		FHitResult Hit;
		FCollisionQueryParams Q(SCENE_QUERY_STAT(AstraPilotHit), true);
		if (APawn* Me = UGameplayStatics::GetPlayerPawn(this, 0))
		{
			Q.AddIgnoredActor(Me);
		}
		if (GetWorld()->LineTraceSingleByChannel(Hit, ToWorld(Prev), ToWorld(S.Pos), ECC_Visibility, Q) && Hit.GetActor())
		{
			What = TEXT("the Aquila's hull");
		}
	}
	// the others have no collision: the box of their hull (a little inside its outline, which takes in masts and guns)
	for (const FAstraBattleShip& O : Ships)
	{
		if (!What.IsEmpty())
		{
			break;
		}
		if (O.bPlayer || O.bCraft || O.Id == S.Id || !O.bAlive || !O.Actor || FVector::Dist(S.Pos, O.Pos) > O.Radius * 2.5)
		{
			continue;
		}
		const UStaticMeshComponent* C = O.Actor->GetStaticMeshComponent();
		if (!C || !C->GetStaticMesh())
		{
			continue;
		}
		const FBox B = C->GetStaticMesh()->GetBoundingBox();                        // cm, the mesh's own frame
		const FVector Local = O.Att.UnrotateVector(S.Pos - O.Pos) * 100.0 / C->GetComponentScale();
		const FVector Ext = B.GetExtent() * 0.8f;
		const FVector Ctr = B.GetCenter();
		if (FMath::Abs(Local.X - Ctr.X) < Ext.X && FMath::Abs(Local.Y - Ctr.Y) < Ext.Y && FMath::Abs(Local.Z - Ctr.Z) < Ext.Z)
		{
			What = FString::Printf(TEXT("the hull of %s"), *O.Name);
		}
	}
	if (What.IsEmpty())
	{
		return false;
	}
	Report(FString::Printf(TEXT("flight: Eagle flew into %s"), *What));
	Destroy(S, EAstraHitKind::Internal);
	return true;
}

FVector UAstraBattleSubsystem::PilotMouth() const
{
	// Alpha's tube (port): the recovery approach is just outside its mouth
	return Ships[0].Pos + Ships[0].Att.RotateVector(FVector(420.0, -14.9, -4.3));
}

bool UAstraBattleSubsystem::TakeFalcon()
{
	for (FAstraSquadron& Q : Squadrons)
	{
		if (Q.Side == EAstraSide::Astra && Q.Name == TEXT("alpha") && Q.OnDeck > 0 && Q.ToLaunch == 0)
		{
			--Q.OnDeck;
			return true;
		}
	}
	return false;
}

void UAstraBattleSubsystem::ReturnFalcon()
{
	for (FAstraSquadron& Q : Squadrons)
	{
		if (Q.Side == EAstraSide::Astra && Q.Name == TEXT("alpha"))
		{
			Q.OnDeck = FMath::Min(Q.OnDeck + 1, Q.Total);
		}
	}
}

bool UAstraBattleSubsystem::LaunchPiloted(AActor* Pawn, const FVector& WorldPos, const FQuat& WorldRot, float SpeedMps, bool bFromPlanet)
{
	if (Ships.Num() == 0 || PilotedId >= 0)
	{
		return false;
	}
	const FVector Pos = FromWorld(WorldPos);
	const FQuat Att = Ships[0].Att * WorldRot;
	const int32 I = AddShip(TEXT("EAGLE"), TEXT("Eagle (the Captain's Falcon)"), TEXT("ASTRA fighter (Falcon)"), TEXT(""), EAstraSide::Astra,
	                        Pos, 0.f, 0.f, 10.f, 90.f, 40.f);
	FAstraBattleShip& C = Ships[I];
	C.Att = Att;
	C.Vel = Ships[0].Vel + Att.GetForwardVector() * SpeedMps;
	C.bCraft = true;
	C.bPiloted = true;
	C.CraftKind = 0;
	C.Squadron = Squadrons.IndexOfByPredicate([](const FAstraSquadron& Q) { return Q.Side == EAstraSide::Astra && Q.Name == TEXT("alpha"); });
	C.Missiles = 4;
	C.RailDamage = 0.f;
	C.PDRange = 0.f;
	C.PDChannels = 0;
	C.bShieldsUp = true;
	C.ShieldRegen = 3.f;
	C.CruiseSpeed = 720.f;
	C.MaxAccel = 150.f;
	C.Mode = EAstraShipMode::Cruise;
	PilotedId = C.Id;
	PilotActor = Pawn;
	bPilotDown = false;
	PilotLock = -1;
	PilotLockT = 0.f;
	PilotDecoys = 4;
	Pilot = FAstraPilotInput();
	Pilot.Throttle = 0.6f;
	const UAstraShipSubsystem* ShipW = GetWorld()->GetSubsystem<UAstraShipSubsystem>();
	const FString WorldN = ShipW ? ShipW->SurfaceWorldName() : FString(TEXT("the world below"));
	Report(bFromPlanet ? FString::Printf(TEXT("flight: Eagle is back in orbit from %s, climbing to rejoin the Aquila"), *WorldN)
	                   : TEXT("flight: the Captain is off the catapult in a Falcon of Alpha, callsign Eagle — the XO has the conn"), true);
	if (!bFromPlanet)
	{
		StartEagleWing();                      // two more Falcons of Alpha follow him off the deck: his wing
	}
	return true;
}

void UAstraBattleSubsystem::FalconLostPlanetside()
{
	for (FAstraSquadron& Q : Squadrons)
	{
		if (Q.Side == EAstraSide::Astra && Q.Name == TEXT("alpha"))
		{
			Q.Total = FMath::Max(0, Q.Total - 1);
		}
	}
}

void UAstraBattleSubsystem::LeavePiloted()
{
	EndEagleWing();
	if (FAstraBattleShip* S = FindById(PilotedId))
	{
		S->bAlive = false;
		S->Mode = EAstraShipMode::Dead;
		S->ContactId = FString::Printf(TEXT("EAGLE-%d"), S->Id);
	}
	PilotedId = -1;
	PilotActor = nullptr;
	const UAstraShipSubsystem* ShipD = GetWorld()->GetSubsystem<UAstraShipSubsystem>();
	Report(FString::Printf(TEXT("flight: Eagle has left the plot — the Captain is descending into %s's atmosphere"),
	                       ShipD ? *ShipD->SurfaceWorldName() : TEXT("the world's")), true);
}

void UAstraBattleSubsystem::EndPiloted(bool bLanded)
{
	EndEagleWing();
	if (FAstraBattleShip* S = FindById(PilotedId))
	{
		S->bAlive = false;
		S->Mode = EAstraShipMode::Dead;
		S->ContactId = FString::Printf(TEXT("EAGLE-%d"), S->Id);   // the callsign is free for the next sortie
	}
	if (bLanded)
	{
		ReturnFalcon();
		Report(TEXT("flight: Eagle recovered through the port tube, the Captain is back aboard"), true);
	}
	else
	{
		Report(TEXT("flight: the Captain's escape pod is aboard — the Captain is unhurt"), true);
	}
	PilotedId = -1;
	PilotActor = nullptr;
	bPilotDown = false;
}

FString UAstraBattleSubsystem::PilotSummary() const
{
	const FAstraBattleShip* S = PilotedId >= 0 ? FindById(PilotedId) : nullptr;
	if (!S)
	{
		return FString();
	}
	if (!S->bAlive)
	{
		return TEXT("the Captain ejected from a destroyed Falcon; the pod is being recovered");
	}
	// the picture around the Falcon as a pilot takes it: clock positions off the nose, high or low, range, closing
	auto Clock = [S](const FVector& Pos) -> FString
	{
		const FVector D = S->Att.UnrotateVector(Pos - S->Pos);
		const float Az = FMath::RadiansToDegrees(FMath::Atan2(D.Y, D.X));
		int32 Hr = FMath::RoundToInt(Az / 30.f);
		Hr = ((Hr % 12) + 12) % 12;
		const float El = FMath::RadiansToDegrees(FMath::Atan2(D.Z, FVector2D(D.X, D.Y).Size()));
		return FString::Printf(TEXT("%d o'clock %s"), Hr == 0 ? 12 : Hr, El > 15.f ? TEXT("high") : (El < -15.f ? TEXT("low") : TEXT("level")));
	};
	struct FNear { const FAstraBattleShip* T; double D; };
	TArray<FNear> Threats;
	for (const FAstraBattleShip& O : Ships)
	{
		if (O.bAlive && O.Id != S->Id && !O.bGhost && (O.bHostile || (O.bCraft && O.Side == EAstraSide::Mandate)) && (!O.bFog || O.Track >= 2))
		{
			const double D = FVector::Dist(O.Pos, S->Pos);
			if (D < 15.0 * OneKm)
			{
				Threats.Add({&O, D});
			}
		}
	}
	Threats.Sort([](const FNear& A, const FNear& B) { return A.D < B.D; });
	TArray<FString> Around;
	for (int32 i = 0; i < FMath::Min(Threats.Num(), 3); ++i)
	{
		const FAstraBattleShip& T = *Threats[i].T;
		const bool bClosing = FVector::DotProduct(T.Vel - S->Vel, (S->Pos - T.Pos).GetSafeNormal()) > 30.f;
		Around.Add(FString::Printf(TEXT("%s at %s, %.1f km%s"), T.bCraft ? TEXT("a Harpy (Mandate strike fighter)") : *KnownLabel(T),
		                           *Clock(T.Pos), Threats[i].D / OneKm, bClosing ? TEXT(", closing") : TEXT("")));
	}
	return FString::Printf(TEXT("flying a Falcon of Alpha (callsign Eagle), %.1f km from the Aquila (she is at %s), hull %.0f%%, %d missiles; %s; "
	                            "the XO has the conn and the Captain talks to the bridge by radio (Price is the Captain's flight controller)"),
	                       FVector::Dist(S->Pos, Ships[0].Pos) / OneKm, *Clock(Ships[0].Pos), 100.f * S->Hull / S->HullMax, S->Missiles,
	                       Around.Num() ? *FString::Printf(TEXT("around the Falcon: %s"), *FString::Join(Around, TEXT("; ")))
	                                    : TEXT("no threats within 15 km of the Falcon"));
}

void UAstraBattleSubsystem::TickPiloted(FAstraBattleShip& S, float Dt)
{
	if (GHomeRequest)
	{
		GHomeRequest = false;
		S.Pos = PilotMouth() + Ships[0].Att.GetForwardVector() * 300.0;
		S.Vel = Ships[0].Vel;
		S.Att = Ships[0].Att * FQuat(FVector::UpVector, PI);   // facing the bow
	}
	if (!GFaceRequest.IsEmpty())
	{
		const FAstraBattleShip* T = GFaceRequest == TEXT("AQUILA") ? &Ships[0] : FindByContact(GFaceRequest);
		if (T)
		{
			S.Att = FRotationMatrix::MakeFromX((T->Pos - S.Pos).GetSafeNormal()).ToQuat();
		}
		else if (GFaceRequest == TEXT("PLANET"))
		{
			if (const UAstraShipSubsystem* Ship = GetWorld()->GetSubsystem<UAstraShipSubsystem>())
			{
				S.Att = FRotationMatrix::MakeFromX(Ships[0].Att.RotateVector(Ship->PlanetDirectionWorld())).ToQuat();
			}
		}
		GFaceRequest.Reset();
	}
	// the stick: rates in the craft's own frame (pitch 75, yaw 55, roll 140 deg/s at full deflection)
	const float Boost = Pilot.bBoost ? 1.f : 0.f;
	const FRotator Turn(Pilot.Pitch * 75.f * Dt, Pilot.Yaw * 55.f * Dt, Pilot.Roll * 140.f * Dt);
	S.Att = (S.Att * Turn.Quaternion()).GetNormalized();
	// flight assist: the velocity follows the lever and the strafe thrusters, in the carrier's frame (the fleet moves
	// together: throttle zero keeps station with the Aquila, which is also how she is brought home)
	const float MaxV = FMath::Lerp(720.f, 1050.f, Boost);
	const FVector Want = Ships[0].Vel + S.Att.RotateVector(FVector(Pilot.Throttle * MaxV, Pilot.Strafe.Y * 160.f, Pilot.Strafe.Z * 160.f));
	S.Vel += (Want - S.Vel).GetClampedToMaxSize(FMath::Lerp(150.f, 260.f, Boost) * Dt);
	S.Pos += S.Vel * Dt;
	if (PilotCollision(S, S.Pos - S.Vel * Dt))
	{
		return;                                   // she flew into a hull: the Captain ejects (the usual recovery)
	}
	S.Shield = FMath::Min(S.ShieldMax, S.Shield + S.ShieldRegen * Dt);
	// guns: two cannons in the wing roots, alternating, ten rounds a second
	PilotGunT -= Dt;
	if (Pilot.bGuns && PilotGunT <= 0.f)
	{
		PilotGunT = 0.1f;
		FirePilotGuns(S);
	}
	// the lock: the hostile nearest the nose inside 12 degrees and 6 km, held for 1.2 s
	const FVector Fwd = S.Att.GetForwardVector();
	const FAstraBattleShip* Best = nullptr;
	float BestAng = 12.f;
	for (const FAstraBattleShip& O : Ships)
	{
		if (!O.bAlive || !O.bHostile || O.bCold || O.Id == S.Id)
		{
			continue;
		}
		const FVector To = O.Pos - S.Pos;
		const double D = To.Size();
		if (D > 6 * OneKm || D < 30.0)
		{
			continue;
		}
		const float Ang = FMath::RadiansToDegrees(FMath::Acos(FMath::Clamp(FVector::DotProduct(To / D, Fwd), -1.0, 1.0)));
		if (Ang < BestAng)
		{
			BestAng = Ang;
			Best = &O;
		}
	}
	if (Best && Best->Id == PilotLock)
	{
		PilotLockT = FMath::Min(1.f, PilotLockT + Dt / 1.2f);
	}
	else
	{
		PilotLock = Best ? Best->Id : -1;
		PilotLockT = 0.f;
	}
	if (Pilot.bMissile && !bPilotMissileLatch && S.Missiles > 0 && PilotLockT >= 1.f)
	{
		if (FAstraBattleShip* T = FindById(PilotLock))
		{
			FireMissile(S, *T);
			--S.Missiles;
			HullSound(TEXT("SW_VLS_Launch"), 0.5f, 0.2f);
		}
	}
	bPilotMissileLatch = Pilot.bMissile;
	// decoys: a burst of flares and chaff; most seekers homing on the Falcon lose it
	if (Pilot.bDecoy && !bPilotDecoyLatch && PilotDecoys > 0)
	{
		--PilotDecoys;
		int32 Spoofed = 0;
		for (FAstraProjectile& Pr : Projectiles)
		{
			if (!Pr.bDead && Pr.Kind == EAstraProjKind::Missile && Pr.Target == S.Id && FMath::FRand() < 0.8f)
			{
				Pr.Target = -1;
				++Spoofed;
			}
		}
		for (int32 k = 0; k < 6; ++k)
		{
			AddFlash(S.Pos - S.Att.GetForwardVector() * (8.0 + 6.0 * k) + FMath::VRand() * 6.0, 4.f, 1.6f, FLinearColor(1.f, 0.75f, 0.4f), 90.f, EAstraFxFlash::Decoy);
		}
		HullSound(TEXT("SW_PD_Burst"), 0.35f, 0.1f);
		UE_LOG(LogASTRA, Log, TEXT("[Battle] Eagle decoys: %d seekers spoofed, %d decoys left"), Spoofed, PilotDecoys);
	}
	bPilotDecoyLatch = Pilot.bDecoy;
}

void UAstraBattleSubsystem::FirePilotGuns(FAstraBattleShip& S)
{
	const FVector Fwd = S.Att.GetForwardVector();
	bPilotGunSide = !bPilotGunSide;
	const FVector Muzzle = S.Pos + Fwd * 4.0 + S.Att.GetRightVector() * (bPilotGunSide ? 2.4 : -2.4) - S.Att.GetUpVector() * 1.3;
	const FVector Dir = (Fwd + FMath::VRand() * 0.0035f).GetSafeNormal();
	FAstraBattleShip* Hit = nullptr;
	double HitT = 2.5 * OneKm;
	for (FAstraBattleShip& O : Ships)
	{
		if (!O.bAlive || !O.bHostile || O.Id == S.Id)
		{
			continue;
		}
		if (O.Box.Valid())
		{
			// a hull of true measures: where the round's path enters the box
			FVector Entry;
			if (HullSweep(O, Muzzle, Muzzle + Dir * HitT, Entry))
			{
				const double T0 = FVector::Dist(Entry, Muzzle);
				if (T0 < HitT)
				{
					HitT = T0;
					Hit = &O;
				}
			}
			continue;
		}
		const double R = O.bCraft ? FMath::Max(O.Radius, 14.f) : O.Radius;   // a little generosity with fighters
		const FVector L = O.Pos - Muzzle;
		const double Tca = FVector::DotProduct(L, Dir);
		if (Tca < 0.0 || Tca - R > HitT)
		{
			continue;
		}
		const double D2 = L.SizeSquared() - Tca * Tca;
		if (D2 > R * R)
		{
			continue;
		}
		const double T0 = FMath::Max(0.0, Tca - FMath::Sqrt(R * R - D2));
		if (T0 < HitT)
		{
			HitT = T0;
			Hit = &O;
		}
	}
	AddBeam(Muzzle, Muzzle + Dir * HitT, 0.05f, FLinearColor(0.55f, 0.85f, 1.f), EAstraFxShot::Cannon, -1, Hit ? Hit->Id : -1);
	HullSound(TEXT("SW_PD_Burst"), 0.22f, 0.09f);
	if (Hit)
	{
		ApplyHit(*Hit, Dir, Hit->bCraft ? 14.f : 5.f, Muzzle + Dir * HitT, EAstraHitKind::Cannon, S.Id);
	}
}

void UAstraBattleSubsystem::GetPilotStatus(FAstraPilotStatus& Out) const
{
	Out = FAstraPilotStatus();
	const FAstraBattleShip* S = PilotedId >= 0 ? FindById(PilotedId) : nullptr;
	if (!S)
	{
		return;
	}
	Out.bFlying = S->bAlive;
	Out.bDown = bPilotDown;
	Out.SpeedMps = (S->Vel - Ships[0].Vel).Size();   // relative to the Aquila: the frame the pilot flies in
	Out.Throttle = Pilot.Throttle;
	Out.HullPct = 100.f * FMath::Max(0.f, S->Hull) / S->HullMax;
	Out.ShieldPct = 100.f * S->Shield / FMath::Max(1.f, S->ShieldMax);
	Out.Missiles = S->Missiles;
	Out.Decoys = PilotDecoys;
	if (const FAstraBattleShip* T = PilotLock >= 0 ? FindById(PilotLock) : nullptr; T && T->bAlive)
	{
		Out.bHasLock = true;
		Out.LockName = T->bIdentified ? T->Name : T->ContactId;
		Out.LockProgress = PilotLockT;
		Out.LockRangeKm = FVector::Dist(T->Pos, S->Pos) / OneKm;
		Out.LockWorld = ToWorld(T->Pos);
		// where to aim the cannons: the target's position when a round (1600 m/s) gets there
		const double Tof = FVector::Dist(T->Pos, S->Pos) / 1600.0;
		Out.LeadWorld = ToWorld(T->Pos + (T->Vel - S->Vel) * Tof);
	}
	const FVector Mouth = PilotMouth();
	Out.HomeWorld = ToWorld(Mouth);
	Out.HomeRangeKm = FVector::Dist(Mouth, S->Pos) / OneKm;
	Out.bCanLand = FVector::Dist(Mouth, S->Pos) < 600.0 && (S->Vel - Ships[0].Vel).Size() < 220.f;
	for (const FAstraProjectile& Pr : Projectiles)
	{
		Out.Incoming += (!Pr.bDead && Pr.Kind == EAstraProjKind::Missile && Pr.Target == S->Id) ? 1 : 0;
	}
	for (const FAstraBattleShip& O : Ships)
	{
		if (!O.bAlive || O.Id == S->Id || O.bPlayer || FVector::Dist(O.Pos, S->Pos) > 25 * OneKm)
		{
			continue;
		}
		if (O.bHostile && !O.bCold)
		{
			Out.Hostiles.Add(ToWorld(O.Pos));
			Out.HostileSizes.Add(O.Radius);
		}
		else if (O.Side == EAstraSide::Astra)
		{
			Out.Friends.Add(ToWorld(O.Pos));
		}
	}
}
