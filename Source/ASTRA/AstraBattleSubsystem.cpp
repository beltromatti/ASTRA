// ASTRA — battle simulation.

#include "AstraBattleSubsystem.h"

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
	S.Hull = S.HullMax = Hull;
	S.Shield = S.ShieldMax = Shield;
	S.Mode = Speed > 1.f ? EAstraShipMode::Cruise : EAstraShipMode::Idle;
	Ships.Add(S);
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
	I = AddShip(TEXT("T-02"), TEXT("ASN Vigilant"), TEXT("ASTRA destroyer"), TEXT("SM_SHIP_ASTRA_Vigilant"), EAstraSide::Astra,
	            A0 + Polar(3 * OneKm, 70, 2), 45.f, 288.f, 140.f, 1200.f, 500.f);
	DestroyerStats(Ships[I]);
	I = AddShip(TEXT("T-07"), TEXT("Brightwater"), TEXT("Free Guilds freighter"), TEXT("SM_SHIP_GUILD_Freighter"), EAstraSide::Neutral,
	            A0 + Polar(22 * OneKm, 15, 4), 120.f, 180.f, 170.f, 700.f, 60.f);
	Ships[I].RailDamage = 0.f;
	Ships[I].Missiles = 0;
	I = AddShip(TEXT("T-11"), TEXT("Lethe"), TEXT("Kharon Mandate frigate, Lethe class"), TEXT("SM_SHIP_MANDATE_Lethe"), EAstraSide::Mandate,
	            A0 + Polar(30 * OneKm, 200, -3), 30.f, 0.f, 90.f, 520.f, 220.f);
	Ships[I].bCold = true;
	Ships[I].bIdentified = false;
	Ships[I].Missiles = 8;

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
	{
		UAstraNavLights* NL = NewObject<UAstraNavLights>(S.Actor);
		NL->SetupAttachment(S.Actor->GetRootComponent());
		NL->RegisterComponent();
		NL->Setup(S.Mesh, S.Side == EAstraSide::Mandate);
	}
	if (SphereMesh && ShellMat && !S.bCraft)
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
	if (SphereMesh && GlowMat)
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
	return Ships.FindByPredicate([Id](const FAstraBattleShip& S) { return S.Id == Id; });
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
		return;
	}
	const float Dt = FMath::Min(DeltaTime, 0.1f) * GBattleTimeScale;
	Time += Dt;
	TickDetection(Dt);
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
				UE_LOG(LogASTRA, Log, TEXT("[Status] t=%.0f %s %-12s %s hull %4.0f/%4.0f shield %4.0f/%4.0f target %s range %.1f km mode %d%s%s"), Time,
				       *S.ContactId, *S.Name, S.bAlive ? TEXT("alive") : TEXT("DEAD "), S.Hull, S.HullMax, S.Shield, S.ShieldMax,
				       T ? *T->ContactId : TEXT("-"), T ? FVector::Dist(S.Pos, T->Pos) / OneKm : 0.0, (int32)S.Mode,
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
	TickPlayer(Dt);
	TickGateRun(Dt);
	TickPOIs(Dt);
	TickScenario(Dt);
	TickSquadrons(Dt);
	for (FAstraBattleShip& S : Ships)
	{
		S.bJammed = false;   // EW drones set it again this tick
	}
	for (FAstraBattleShip& S : Ships)
	{
		if (!S.bAlive)
		{
			continue;
		}
		if (S.bPiloted)
		{
			TickPiloted(S, Dt);
			continue;
		}
		if (S.bCraft)
		{
			TickCraft(S, Dt);
			continue;
		}
		if (!S.bPlayer)
		{
			TickAI(S, Dt);
		}
		TickWeapons(S, Dt);
		if (S.bShieldsUp)
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
	}
	TickProjectiles(Dt);
	TickFlashes(Dt);
	SyncVisuals();
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
	Km *= 0.55f + 0.45f * Ship->GetThrottlePct() / 100.f;                                  // the drive's plume
	Km *= 1.f + Ship->SignatureBoost() + 0.4f * FMath::Max(0.f, Ship->GetHeatPct() - 50.f) / 50.f;   // hot panels, a vent, a hot hull
	return Km;
}

void UAstraBattleSubsystem::TickDetection(float Dt)
{
	PlayerSinceFired += Dt;
	const FAstraBattleShip& P = Ships[0];
	const float SigKm = PlayerSignatureKm();
	bool bSeen = PlayerSinceFired < 45.f;
	bool bHostiles = false;
	for (const FAstraBattleShip& O : Ships)
	{
		if (O.bAlive && O.bHostile && O.Side == EAstraSide::Mandate && !O.bCraft && !O.bCold)
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
		Frigate->bIdentified = true;
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
		P.Hull = FMath::Min(P.HullMax, P.Hull + RepairHullPerSec * Dt);
		if (Time >= RepairUntil)
		{
			RepairUntil = -1.f;
			P.Missiles += RepairMissiles;
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
			if (S.bAlive && S.bHostile)
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
	if (S.bDerelict)
	{
		S.Pos += S.Vel * Dt;
		S.Att = FQuat(FVector(0.2f, 0.3f, 1.f).GetSafeNormal(), FMath::DegreesToRadians(S.SpinDeg * Dt)) * S.Att;
		return;
	}
	FVector DesiredVel = S.Vel;
	FVector Face = S.Vel.IsNearlyZero() ? S.Att.GetForwardVector() : S.Vel.GetSafeNormal();
	FAstraBattleShip* T = FindById(S.TargetId);
	// rules of engagement: the fleet does not shoot at an enemy that has ceased fire or is withdrawing
	const bool bFleet = S.Side == EAstraSide::Astra && !S.bPlayer;
	const auto Engageable = [this, &S](const FAstraBattleShip& O)
	{
		return O.bAlive && !O.bCold && ((S.Side == EAstraSide::Mandate && O.Side == EAstraSide::Astra && !O.bCraft && (!O.bPlayer || bPlayerTracked)) ||
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
		float Pref = S.Radius > 200.f ? 4 * OneKm : 3 * OneKm;
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
			Report(FString::Printf(TEXT("sensors: %s (%s) is badly damaged and breaking off, heading away from the fight"), *S.Name, *S.ContactId));
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
			if (bWasCommander)
			{
				OnCommanderLost(S, TEXT("jumped out of the system"));
			}
			if (S.Actor) { S.Actor->Destroy(); }
			if (S.ShieldBubble) { S.ShieldBubble->Destroy(); }
			if (S.DriveFlare) { S.DriveFlare->Destroy(); }
			Report(FString::Printf(TEXT("sensors: %s (%s) has left sensor range"), *S.Name, *S.ContactId));
		}
	}
	if (S.Mode == EAstraShipMode::Idle && !S.bHostile)
	{
		DesiredVel = FVector::ZeroVector;
	}
	// accelerate towards the desired velocity, turn at a capital-ship rate
	const FVector DV = (DesiredVel - S.Vel).GetClampedToMaxSize(S.MaxAccel * Dt);
	S.Vel += DV;
	if (!Face.IsNearlyZero())
	{
		const FQuat Want = FRotationMatrix::MakeFromX(Face).ToQuat();
		const float MaxStep = FMath::DegreesToRadians(S.MaxTurnDeg * Dt);
		const float Ang = S.Att.AngularDistance(Want);
		S.Att = Ang <= MaxStep ? Want : FQuat::Slerp(S.Att, Want, MaxStep / Ang);
	}
	S.Pos += S.Vel * Dt;
}

void UAstraBattleSubsystem::TickWeapons(FAstraBattleShip& S, float Dt)
{
	S.RailT = FMath::Max(0.f, S.RailT - Dt);
	S.MissileT = FMath::Max(0.f, S.MissileT - Dt);
	S.PDT = FMath::Max(0.f, S.PDT - Dt);
	// point defence: every ship shoots at missiles aimed at it (the Aquila's PD is automatic, 24 mounts)
	if (S.PDT <= 0.f)
	{
		int32 Channels = S.PDChannels;
		for (FAstraProjectile& Pr : Projectiles)
		{
			if (Channels > 0 && !Pr.bDead && Pr.Kind == EAstraProjKind::Missile && Pr.Target == S.Id &&
			    FVector::Dist(Pr.Pos, S.Pos) < S.PDRange + S.Radius)
			{
				--Channels;
				S.PDT = 0.5f;
				AddBeam(S.Pos + (Pr.Pos - S.Pos).GetSafeNormal() * S.Radius * 0.6, Pr.Pos, 0.12f, FLinearColor(1.f, 0.85f, 0.5f));
				if (S.bPlayer)
				{
					HullSound(TEXT("SW_PD_Burst"), 0.4f, 0.6f);
				}
				if (FMath::FRand() < (S.bPlayer ? 0.32f : 0.25f) * (Pr.bTorpedo ? 0.8f : 1.f))
				{
					Pr.bDead = true;
					AddFlash(Pr.Pos, 25.f, 0.6f, FLinearColor(1.f, 0.7f, 0.35f), 60.f);
					if (S.bPlayer)
					{
						Report(TEXT("tactical: point defense splashed an incoming missile"), false);
					}
				}
			}
		}
		if (S.Side == EAstraSide::Mandate || S.Side == EAstraSide::Astra)
		{
			const EAstraSide Foe = S.Side == EAstraSide::Mandate ? EAstraSide::Astra : EAstraSide::Mandate;
			for (FAstraBattleShip& C : Ships)
			{
				if (Channels <= 0)
				{
					break;
				}
				if (C.bCraft && C.bAlive && C.Side == Foe && FVector::Dist(C.Pos, S.Pos) < 1500.f + S.Radius)
				{
					--Channels;
					S.PDT = 0.5f;
					AddBeam(S.Pos + (C.Pos - S.Pos).GetSafeNormal() * S.Radius * 0.6, C.Pos, 0.1f, FLinearColor(1.f, 0.6f, 0.3f));
					if (C.bPiloted)
					{
						if (FMath::FRand() < 0.22f)
						{
							ApplyHit(C, (C.Pos - S.Pos).GetSafeNormal(), 14.f, C.Pos);   // the Captain's Falcon: hurt, not erased
						}
					}
					else if (FMath::FRand() < (C.CraftKind == 0 ? 0.07f : (C.CraftKind == 1 ? 0.1f : 0.14f)))
					{
						ApplyHit(C, (C.Pos - S.Pos).GetSafeNormal(), 1000.f, C.Pos);
					}
				}
			}
		}
	}
	if (S.bPlayer)
	{
		TickPlayerFire(S, Dt);
		return;
	}
	if (S.Mode != EAstraShipMode::Attack || S.bFleeing || S.bHoldFire)
	{
		return;
	}
	FAstraBattleShip* T = FindById(S.TargetId);
	if (!T || !T->bAlive)
	{
		return;
	}
	const double Dist = FVector::Dist(S.Pos, T->Pos);
	if (S.RailDamage > 0.f && S.RailT <= 0.f && Dist < S.RailRange)
	{
		S.RailT = S.RailCd * FMath::FRandRange(0.8f, 1.2f);
		for (int32 i = 0; i < S.RailSlugs; ++i)
		{
			FireRail(S, *T, (0.0012f + Dist / 30e6) * (S.bJammed ? 3.f : 1.f));
		}
	}
	if (S.Missiles > 0 && (S.MissileT <= 0.f || S.bSalvo) && Dist < S.MissileRange && Dist > 2.5 * OneKm && T->Side != EAstraSide::Neutral)
	{
		// a massed salvo empties the ready cells (6 on a cruiser, 3 on a destroyer): the cells then reload for longer
		S.MissileT = S.MissileCd * FMath::FRandRange(0.8f, 1.2f) * (S.bConserve ? 2.2f : 1.f) * (S.bSalvo ? 2.f : 1.f);
		const int32 N = FMath::Min(S.Missiles, S.bSalvo ? (S.Radius > 200.f ? 6 : 3) : (S.Radius > 200.f ? 4 : 2));
		S.bSalvo = false;
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
			Report(FString::Printf(TEXT("tactical: %d missiles inbound from %s (%s)%s, point defense tracking"), InboundSinceReport, *S.Name,
			                       *S.ContactId, bSpeak ? TEXT("") : TEXT(" [same engagement, already reported]")), bSpeak);
			if (bSpeak)
			{
				LastInboundReport = Time;
				InboundSinceReport = 0;
			}
		}
	}
	if (Dist < 4 * OneKm && FMath::FRand() < Dt * 0.6f)
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
	Pr.Pos = From.Pos + Aim * From.Radius * 0.8;
	Pr.Vel = From.Vel + Aim * Speed;
	Pr.Owner = From.Id;
	Pr.Target = To.Id;
	Pr.Damage = From.RailDamage;
	Pr.Life = Tof + 1.5f;
	if (UWorld* World = GetWorld(); World && CylinderMesh && GlowMat)
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
	Projectiles.Add(Pr);
}

void UAstraBattleSubsystem::FireMissile(FAstraBattleShip& From, FAstraBattleShip& To)
{
	FAstraProjectile Pr;
	Pr.Kind = EAstraProjKind::Missile;
	const FVector Out = (From.Att.GetUpVector() + FMath::VRand() * 0.5f).GetSafeNormal();
	Pr.Pos = From.Pos + Out * From.Radius * 0.5;
	Pr.Vel = From.Vel + Out * 300.f;
	Pr.Owner = From.Id;
	Pr.Target = To.Id;
	Pr.Damage = 110.f;
	Pr.Life = 150.f;
	if (UWorld* World = GetWorld(); World && SphereMesh && GlowMat)
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
	Projectiles.Add(Pr);
}

void UAstraBattleSubsystem::FireLaser(FAstraBattleShip& From, FAstraBattleShip& To)
{
	const FVector Hit = To.Pos + FMath::VRand() * To.Radius * 0.5;
	AddBeam(From.Pos, Hit, 0.35f, From.Side == EAstraSide::Mandate ? FLinearColor(1.f, 0.35f, 0.15f) : FLinearColor(0.5f, 0.8f, 1.f));
	ApplyHit(To, (To.Pos - From.Pos).GetSafeNormal(), 18.f, Hit);
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
	if (T->Side == EAstraSide::Mandate && T->bNegotiated)
	{
		BreakCeasefire(*T);
	}
	FAstraBattleShip& P = Ships[0];
	const double Dist = FVector::Dist(P.Pos, T->Pos);
	const FString W = Weapon.ToLower();
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
		OutDetail = FString::Printf(TEXT("%d missiles away at %s, %d left in the VLS, time to target about %.0f s"), N, *T->ContactId,
		                            P.Missiles, Dist / 1400.0 + 2.0);
	}
	else if (W == TEXT("lasers"))
	{
		P.FireTarget = T->Id;
		P.LaserShots = FMath::Clamp(Salvo, 1, 12) * 2;
		OutDetail = Dist > 4 * OneKm ? FString::Printf(TEXT("lasers assigned to %s, now at %.1f km: they fire once it is inside 4 km"), *T->ContactId, Dist / OneKm)
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

void UAstraBattleSubsystem::GetHoloBlips(TArray<FAstraHoloBlip>& Out) const
{
	Out.Reset();
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
	for (const FAstraBattleShip& S : Ships)
	{
		if (!S.bAlive)
		{
			continue;
		}
		FAstraHoloBlip B;
		B.Kind = 0;
		B.Rel = ToWorld(S.Pos) - Origin;
		B.Rot = ToWorldRot(S.Att);
		B.VelDir = Dir(S.Pos, S.Vel);
		B.Speed = S.Vel.Size();
		B.Side = S.Side;
		B.bPlayer = S.bPlayer;
		B.bHostile = S.bHostile;
		B.bUnknown = !S.bIdentified || S.bCold;
		B.bRetreating = S.bFleeing;
		B.bHoldFire = S.bHoldFire;
		B.bTargeted = !S.bPlayer && (P.FireTarget == S.Id) && (P.RailVolleys > 0 || P.LaserShots > 0);
		B.Size = S.Radius >= 300.f ? 1.f : (S.Radius >= 200.f ? 0.85f : (S.Radius >= 130.f ? 0.7f : 0.55f));
		B.RangeKm = FVector::Dist(S.Pos, P.Pos) / OneKm;
		B.Name = S.bIdentified ? S.Name : FString();
		B.Contact = S.ContactId;
		if (S.bCraft && Squadrons.IsValidIndex(S.Squadron))
		{
			B.bCraft = true;
			B.Size = S.CraftKind == 2 ? 0.2f : 0.3f;
			const FAstraSquadron& Q = Squadrons[S.Squadron];
			// the first airborne aircraft of a group carries the group's label
			const FAstraBattleShip* Lead = Ships.FindByPredicate([&S](const FAstraBattleShip& X) { return X.bAlive && X.bCraft && X.Squadron == S.Squadron; });
			B.bNoLabel = Lead != &S;
			B.Name = FString::Printf(TEXT("%s x%d"), *Q.Name.ToUpper(), AirborneCount(S.Squadron));
			B.Contact = Q.Mission.ToUpper();
		}
		Out.Add(B);
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
		const FAstraBattleShip* Owner = Ships.FindByPredicate([&Pr](const FAstraBattleShip& S) { return S.Id == Pr.Owner; });
		B.Side = Owner ? Owner->Side : EAstraSide::Neutral;
		B.bHostile = Owner && Owner->bHostile;
		Out.Add(B);
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
	                                                          : FString(TEXT("ready, 12 batteries, range 4 km")));
	int32 InFlight = 0;
	for (const FAstraProjectile& Pr : Projectiles)
	{
		InFlight += (!Pr.bDead && Pr.Owner == P.Id && Pr.Kind == EAstraProjKind::Missile) ? 1 : 0;
	}
	W->SetStringField(TEXT("missiles"), FString::Printf(TEXT("%d in the VLS, %s; %d of ours in flight; range 25 km"), P.Missiles,
		P.MissileT > 0.f ? *FString::Printf(TEXT("cycling, next salvo in %.0f s"), P.MissileT) : TEXT("ready (max 8 per salvo)"), InFlight));
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
	if (P.RailVolleys > 0 && P.RailT <= 0.f && Dist <= P.RailRange)
	{
		P.RailT = P.RailCd / FMath::Max(0.25f, P.WeaponPower);   // capacitor recharge follows weapons power (and the heat)
		HullSound(TEXT("SW_Rail_Fire"), 0.9f, 0.3f);
		--P.RailVolleys;
		PlayerSinceFired = 0.f;
		if (Heat)
		{
			Heat->RailgunDraw();   // the capacitors pull on the ship's power: the lights sag for a moment
			Heat->AddHeat(4.0f);   // eight slugs out of the rails: the capacitors and the barrels dump their heat
		}
		for (int32 i = 0; i < P.RailSlugs; ++i)
		{
			FireRail(P, *T, 0.001f + Dist / 30e6);
		}
	}
	if (P.LaserShots > 0 && P.LaserT <= 0.f && Dist <= 4 * OneKm)
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
		if (!S.bAlive || !S.bHostile || S.bCraft || S.Side != EAstraSide::Mandate)
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
	FString Focus, StanceName, Missiles, Fighters;
	Args->TryGetStringField(TEXT("focus"), Focus);
	Args->TryGetStringField(TEXT("stance"), StanceName);
	Args->TryGetStringField(TEXT("missiles"), Missiles);
	Args->TryGetStringField(TEXT("fighters"), Fighters);
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
			Salvo += FMath::Min(S.Missiles, S.Radius > 200.f ? 6 : 3);
		}
		else if (Missiles.Equals(TEXT("conserve"), ESearchCase::IgnoreCase)) { S.bConserve = true; }
		else if (Missiles.Equals(TEXT("normal"), ESearchCase::IgnoreCase)) { S.bConserve = false; }
		if (S.Mode != EAstraShipMode::Attack && S.Mode != EAstraShipMode::Evade)
		{
			S.Mode = EAstraShipMode::Attack;
		}
	}
	if (Group.Num() == 0)
	{
		OutDetail = TEXT("no ship of the strike group is fighting");
		return false;
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
	const FString Who = Group.Num() > 1 ? FString(TEXT("the Mandate ships")) : FString::Printf(TEXT("%s (%s)"), *Group[0]->Name, *Group[0]->ContactId);
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
	OutDetail = FString::Printf(TEXT("%d ship%s: focus %s, stance %s, missiles %s%s%s"), Group.Num(), Group.Num() == 1 ? TEXT("") : TEXT("s"),
	                            F ? *F->ContactId : TEXT("nearest"), Stance >= 0 ? Stances[Stance] : TEXT("unchanged"),
	                            Missiles.IsEmpty() ? TEXT("unchanged") : *Missiles.ToLower(),
	                            Salvo ? *FString::Printf(TEXT(" (%d in the salvo)"), Salvo) : TEXT(""),
	                            Launched ? *FString::Printf(TEXT(", %d fighters launching"), Launched) : TEXT(""));
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
	TArray<FString> Names;
	for (const FAstraBattleShip* S : Fleet) { Names.Add(S->Name); }
	const FString What = R == TEXT("focus_fire") ? FString::Printf(TEXT("shifting fire to the %s (%s)"), *T->Name, *T->ContactId)
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
	OutDetail = FString::Printf(TEXT("channel open to %s (%s)%s"), *T->Name, *T->ContactId,
	                            T->Side == EAstraSide::Mandate ? TEXT(", Mandate ship: reply expected") : TEXT(""));
	return true;
}

void UAstraBattleSubsystem::ApplyHit(FAstraBattleShip& To, const FVector& FromDir, float Damage, const FVector& HitPos)
{
	if (!To.bAlive)
	{
		return;
	}
	float ToHull = Damage;
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
		To.ShieldFlash = 1.f;
	}
	To.Hull -= ToHull;
	AddFlash(HitPos, ToHull > 10.f ? 45.f : 25.f, 0.8f, To.ShieldFlash > 0.f ? FLinearColor(0.6f, 0.8f, 1.f) : FLinearColor(1.f, 0.6f, 0.3f), 80.f);
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
		Destroy(To);
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

void UAstraBattleSubsystem::Destroy(FAstraBattleShip& S)
{
	const bool bWasCommander = S.Side == EAstraSide::Mandate && S.bHostile && MandateCommander() == S.ContactId;
	S.bAlive = false;
	S.Mode = EAstraShipMode::Dead;
	AddFlash(S.Pos, S.Radius * 1.4f, 2.6f, FLinearColor(1.f, 0.5f, 0.2f), 160.f);    // fireball: the gas cloud expands and thins
	AddFlash(S.Pos, S.Radius * 0.9f, 1.1f, FLinearColor(1.f, 0.92f, 0.75f), 600.f);  // the flash of the reactor letting go
	if (!S.bCraft)
	{
		Explode(S);   // takes over the ship's actor as the hulk
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
	}
	else if (S.bCraft)
	{
		if (Squadrons.IsValidIndex(S.Squadron))
		{
			FAstraSquadron& Q = Squadrons[S.Squadron];
			--Q.Total;
			++Q.LostSinceReport;
			// a manned aircraft of ours: somebody was flying it
			if (Q.Side == EAstraSide::Astra && Q.Kind != 2)
			{
				if (UAstraShipSubsystem* Ship = GetWorld()->GetSubsystem<UAstraShipSubsystem>())
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
		Report(FString::Printf(TEXT("tactical: %s (%s, %s) destroyed"), *S.Name, *S.ContactId, *S.Class));
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
			const FVector C = FMath::ClosestPointOnSegment(S.Pos, Prev, Pr.Pos);
			if (FVector::DistSquared(C, S.Pos) < FMath::Square(S.Radius))
			{
				ApplyHit(S, (S.Pos - Prev).GetSafeNormal(), Pr.Damage, C);
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

void UAstraBattleSubsystem::AddFlash(const FVector& Pos, float Size, float Life, const FLinearColor& Color, float Intensity)
{
	FAstraFlash F;
	F.Pos = Pos;
	F.Size = Size;
	F.Life = Life;
	F.Color = Color;
	F.Intensity = Intensity;
	if (UWorld* World = GetWorld(); World && SphereMesh && ShellMat)
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
	FAstraFlash F;
	F.Pos = A;
	F.BeamTo = B;
	F.bBeam = true;
	F.Life = Life;
	F.Color = Color;
	F.Intensity = 300.f;
	if (UWorld* World = GetWorld(); World && CylinderMesh && GlowMat)
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
				O->SetStringField(TEXT("state"), S.bFleeing ? (S.bNegotiated ? TEXT("withdrawing, as ordered") : TEXT("breaking off: too damaged to keep fighting"))
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
		TSharedRef<FJsonObject> O = MakeShared<FJsonObject>();
		O->SetStringField(TEXT("id"), S.ContactId);
		O->SetStringField(TEXT("class"), S.bIdentified ? S.Class : TEXT("unknown"));
		if (S.bIdentified)
		{
			O->SetStringField(TEXT("name"), S.Name);
		}
		O->SetStringField(TEXT("status"), S.bDerelict ? TEXT("derelict: no power, no transponder, tumbling")
		                                  : S.bCold ? TEXT("unidentified, cold drive, drifting")
		                                          : (S.bHostile ? (S.bFleeing ? TEXT("hostile, retreating") : (S.bHoldFire ? TEXT("hostile, holding fire") : TEXT("hostile"))) : SideName(S.Side)));
		O->SetNumberField(TEXT("range_km"), FMath::RoundToDouble(FVector::Dist(P.Pos, S.Pos) / 100.0) / 10.0);
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
	return Ships.ContainsByPredicate([](const FAstraBattleShip& X) { return X.bAlive && X.Side == EAstraSide::Mandate && X.bNegotiated && X.bLeader; });
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
	                            T ? *FString::Printf(TEXT(" on %s (%s)"), *T->ContactId, *T->Name) : TEXT(""));
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
			Report(FString::Printf(TEXT("flight: %s squadron torpedo run on the %s: %d torpedoes away, bombers returning"), *Q.Name,
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
		Q.LaunchT = bOurs ? 2.f / FMath::Max(0.3f, Deck) : 1.5f;
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
			             : FString::Printf(TEXT("sensors: the %s (%s) has launched strike fighters — %d Harpies inbound on the Aquila"),
			                               Cr ? *Cr->Name : TEXT("enemy cruiser"), Cr ? *Cr->ContactId : TEXT("?"), Q.Launched));
		}
	}
}

void UAstraBattleSubsystem::TickCraft(FAstraBattleShip& S, float Dt)
{
	FAstraSquadron& Q = Squadrons[S.Squadron];
	FAstraBattleShip* Home = FindById(Q.CarrierId);
	FAstraBattleShip& Carrier = (Home && Home->bAlive) ? *Home : Ships[0];
	if (S.Side == EAstraSide::Mandate)
	{
		// Kharon strike fighters: go for the Aquila (or the nearest ASTRA warship), rockets then guns
		FAstraBattleShip* T = FindById(S.MissionTarget);
		if (!T || !T->bAlive || T->bCraft)
		{
			T = nullptr;
			double Best = 1e18;
			for (FAstraBattleShip& O : Ships)
			{
				if (O.bAlive && !O.bCraft && O.Side == EAstraSide::Astra && FVector::Dist(O.Pos, S.Pos) < Best)
				{
					Best = FVector::Dist(O.Pos, S.Pos);
					T = &O;
				}
			}
			S.MissionTarget = T ? T->Id : -1;
		}
		FVector Goal = S.Pos + S.Vel;
		const float Orbit = Time * 0.3f + S.OrbitPhase;
		// the Captain's Falcon near them: the two nearest Harpies break off and hunt it (a dogfight)
		bool bDogfight = false;
		FAstraBattleShip* Eagle = PilotedId >= 0 ? FindById(PilotedId) : nullptr;
		if (Eagle && Eagle->bAlive && !bMandateStandDown() && FVector::Dist(Eagle->Pos, S.Pos) < 5 * OneKm)
		{
			int32 Closer = 0;
			for (const FAstraBattleShip& O : Ships)
			{
				Closer += (O.bAlive && O.bCraft && O.Side == EAstraSide::Mandate && O.Id != S.Id &&
				           FVector::Dist(O.Pos, Eagle->Pos) < FVector::Dist(S.Pos, Eagle->Pos)) ? 1 : 0;
			}
			if (Closer < 2)
			{
				const FVector ToE = Eagle->Pos - S.Pos;
				const double D = ToE.Size();
				Goal = Eagle->Pos + Eagle->Vel * 0.6 - ToE.GetSafeNormal() * 250.0;   // onto its tail
				const float Facing = FVector::DotProduct(S.Att.GetForwardVector(), ToE / FMath::Max(1.0, D));
				if (D < 900.0 && Facing > 0.93f && (S.GunT -= Dt) <= 0.f)
				{
					S.GunT = 0.25f;
					const bool bHit = FMath::FRand() < 0.33f;
					AddBeam(S.Pos, Eagle->Pos + (bHit ? FVector::ZeroVector : FMath::VRand() * 25.0), 0.06f, FLinearColor(1.f, 0.55f, 0.3f));
					if (bHit)
					{
						ApplyHit(*Eagle, ToE.GetSafeNormal(), 7.f, Eagle->Pos);
					}
				}
				else if (S.Missiles > 0 && D > 1200.0 && D < 3500.0 && Facing > 0.8f && (S.GunT -= Dt) <= 0.f)
				{
					S.GunT = 4.f;
					--S.Missiles;
					FireMissile(S, *Eagle);
					FAstraProjectile& R = Projectiles.Last();
					R.Damage = 40.f;
					R.MaxSpeed = 1250.f;
					if (R.Actor) { R.Actor->SetActorScale3D(FVector(3.f)); }
				}
				bDogfight = true;   // not striking the carrier while it dogfights
			}
		}
		if (bDogfight)
		{
			// (the goal is set: on the Falcon's tail)
		}
		else if (T && !bMandateStandDown())
		{
			const FVector ToT = T->Pos - S.Pos;
			const double D = ToT.Size();
			Goal = T->Pos + FVector(FMath::Cos(Orbit * 2.f), FMath::Sin(Orbit * 2.f), 0.35f) * (T->Radius + 1100.0);
			if (S.Missiles > 0 && D < 4500.0 && (S.GunT -= Dt) <= 0.f)
			{
				S.GunT = 0.8f;
				--S.Missiles;
				FireMissile(S, *T);
				FAstraProjectile& R = Projectiles.Last();
				R.Damage = 45.f;
				R.MaxSpeed = 1300.f;
				if (R.Actor) { R.Actor->SetActorScale3D(FVector(4.f)); }
				if (T->bPlayer)
				{
					++InboundSinceReport;
					if (Time - LastInboundReport > 20.f)
					{
						Report(FString::Printf(TEXT("tactical: rockets inbound from the Harpy strike fighters (%d so far), point defense tracking"), InboundSinceReport));
						LastInboundReport = Time;
						InboundSinceReport = 0;
					}
				}
			}
			else if (S.Missiles <= 0 && D < 1800.0 && (S.GunT -= Dt) <= 0.f)
			{
				S.GunT = 0.5f;
				const FVector Dir = ToT.GetSafeNormal();
				AddBeam(S.Pos, T->Pos - Dir * T->Radius, 0.08f, FLinearColor(1.f, 0.55f, 0.3f));
				ApplyHit(*T, Dir, 2.5f, T->Pos - Dir * T->Radius);
			}
			// our fighters close by get shot at too
			for (FAstraBattleShip& O : Ships)
			{
				if (O.bAlive && O.bCraft && O.Side == EAstraSide::Astra && FVector::Dist(O.Pos, S.Pos) < 600.0 && FMath::FRand() < Dt * 0.25f)
				{
					AddBeam(S.Pos, O.Pos, 0.08f, FLinearColor(1.f, 0.55f, 0.3f));
					ApplyHit(O, (O.Pos - S.Pos).GetSafeNormal(), 1000.f, O.Pos);
					break;
				}
			}
		}
		else
		{
			// nothing left to strike (or ordered to stand down): back to the carrier, or away if it is gone
			Goal = (Home && Home->bAlive) ? Home->Pos : S.Pos + (S.Pos - Ships[0].Pos).GetSafeNormal() * 20000.0;
			if (Home && Home->bAlive && FVector::Dist(S.Pos, Home->Pos) < 400.0)
			{
				S.bAlive = false;
				if (S.Actor) { S.Actor->Destroy(); S.Actor = nullptr; }
				if (S.DriveFlare) { S.DriveFlare->Destroy(); S.DriveFlare = nullptr; }
				return;
			}
			if (FVector::Dist(S.Pos, Ships[0].Pos) > 80 * OneKm)
			{
				S.bAlive = false;
				if (S.Actor) { S.Actor->Destroy(); S.Actor = nullptr; }
				if (S.DriveFlare) { S.DriveFlare->Destroy(); S.DriveFlare = nullptr; }
				return;
			}
		}
		const FVector ToGoal = Goal - S.Pos;
		const double L = ToGoal.Size();
		const FVector DesiredVel = ToGoal / FMath::Max(L, 1.0) * FMath::Min((double)S.CruiseSpeed, L * 0.8 + 80.0);
		S.Vel += (DesiredVel - S.Vel).GetClampedToMaxSize(S.MaxAccel * Dt);
		if (!S.Vel.IsNearlyZero())
		{
			const FQuat Want = FRotationMatrix::MakeFromX(S.Vel.GetSafeNormal()).ToQuat();
			const float MaxStep = FMath::DegreesToRadians(S.MaxTurnDeg * Dt);
			const float Ang = S.Att.AngularDistance(Want);
			S.Att = Ang <= MaxStep ? Want : FQuat::Slerp(S.Att, Want, MaxStep / Ang);
		}
		S.Pos += S.Vel * Dt;
		return;
	}
	FAstraBattleShip* T = FindById(S.MissionTarget);
	if (T && !T->bAlive)
	{
		T = nullptr;
	}
	FString& M = S.Mission;
	if (!T && (M == TEXT("strike") || M == TEXT("escort") || M == TEXT("ew")))
	{
		M = TEXT("recall");   // the target is gone: come home
	}
	FVector Goal = Carrier.Pos;
	float Speed = S.CruiseSpeed;
	const float Orbit = Time * 0.22f + S.OrbitPhase;
	auto KillThreats = [&](const FVector& Around, float Radius) -> bool
	{
		// enemy strike fighters near what we protect come first: chase and shoot
		FAstraBattleShip* Bandit = nullptr;
		double BanditD = 4500.0;
		for (FAstraBattleShip& O : Ships)
		{
			if (O.bAlive && O.bCraft && O.Side == EAstraSide::Mandate)
			{
				const double D = FVector::Dist(O.Pos, Around);
				if (D < BanditD)
				{
					BanditD = D;
					Bandit = &O;
				}
			}
		}
		if (Bandit && S.CraftKind != 1)
		{
			Goal = Bandit->Pos + Bandit->Vel * 0.5;
			if (FVector::Dist(S.Pos, Bandit->Pos) < 900.f && (S.GunT -= Dt) <= 0.f)
			{
				S.GunT = 0.4f;
				AddBeam(S.Pos, Bandit->Pos, 0.08f, FLinearColor(0.6f, 0.85f, 1.f));
				if (FMath::FRand() < (S.CraftKind == 0 ? 0.2f : 0.08f))
				{
					ApplyHit(*Bandit, (Bandit->Pos - S.Pos).GetSafeNormal(), 1000.f, Bandit->Pos);
				}
			}
			return true;
		}
		// intercept the nearest Mandate missile or torpedo near what we protect
		FAstraProjectile* Best = nullptr;
		double BestD = Radius;
		for (FAstraProjectile& Pr : Projectiles)
		{
			const FAstraBattleShip* O = FindById(Pr.Owner);
			if (Pr.bDead || Pr.Kind != EAstraProjKind::Missile || !O || O->Side != EAstraSide::Mandate)
			{
				continue;
			}
			const double D = FVector::Dist(Pr.Pos, Around);
			if (D < BestD)
			{
				BestD = D;
				Best = &Pr;
			}
		}
		if (!Best)
		{
			return false;
		}
		Goal = Best->Pos + Best->Vel * 0.6;
		if (FVector::Dist(S.Pos, Best->Pos) < 700.f && (S.GunT -= Dt) <= 0.f)
		{
			S.GunT = 0.4f;
			AddBeam(S.Pos, Best->Pos, 0.08f, FLinearColor(0.6f, 0.85f, 1.f));
			if (FMath::FRand() < (S.CraftKind == 0 ? 0.35f : 0.15f))
			{
				Best->bDead = true;
				AddFlash(Best->Pos, 20.f, 0.5f, FLinearColor(1.f, 0.7f, 0.35f), 50.f);
			}
		}
		return true;
	};
	if (M == TEXT("recall"))
	{
		Goal = Carrier.Pos + Carrier.Att.RotateVector(FVector(-60.0, 0.0, -30.0));
		if (FVector::Dist(S.Pos, Goal) < 400.f)
		{
			// trapped aboard
			S.bAlive = false;
			if (S.Actor) { S.Actor->Destroy(); S.Actor = nullptr; }
			if (S.DriveFlare) { S.DriveFlare->Destroy(); S.DriveFlare = nullptr; }
			++Q.OnDeck;
			if (AirborneCount(S.Squadron) == 0)
			{
				Q.RearmT = Q.Kind == 1 ? 120.f : 60.f;
				Q.Mission = TEXT("recall");
				Report(FString::Printf(TEXT("flight: %s squadron recovered, %d of %d %ss aboard, rearming (%.0f s)"), *Q.Name, Q.OnDeck, Q.Total, *Q.CallSign, Q.RearmT));
			}
			return;
		}
	}
	else if (M == TEXT("cap") || M == TEXT("escort"))
	{
		const FAstraBattleShip& Guard = (M == TEXT("escort") && T) ? *T : Carrier;
		if (!KillThreats(Guard.Pos, 7000.f))
		{
			Goal = Guard.Pos + FVector(FMath::Cos(Orbit), FMath::Sin(Orbit), 0.25f * FMath::Sin(2.f * Orbit)) * 2500.0;
			Speed *= 0.6f;
		}
	}
	else if (M == TEXT("strike") && T)
	{
		const FVector ToT = T->Pos - S.Pos;
		const double D = ToT.Size();
		if (S.CraftKind == 1)
		{
			// torpedo run: close to 4 km, release, come home
			Goal = T->Pos + T->Vel * 2.0;
			if (S.Torpedoes > 0 && D < 4000.0)
			{
				for (int32 k = 0; k < S.Torpedoes; ++k)
				{
					FireTorpedo(S, *T);
				}
				Q.TorpedoesAway += S.Torpedoes;
				Q.TorpedoTarget = FString::Printf(TEXT("%s (%s)"), *T->Name, *T->ContactId);
				if (Q.TorpedoReportAt < 0.f)
				{
					Q.TorpedoReportAt = Time + 6.f;   // the rest of the group releases within seconds: one report for the run
				}
				S.Torpedoes = 0;
				M = TEXT("recall");
			}
		}
		else
		{
			// fighters strafe the target, circling at about a kilometre
			Goal = T->Pos + FVector(FMath::Cos(Orbit * 2.5f), FMath::Sin(Orbit * 2.5f), 0.3f) * (T->Radius + 900.0);
			if (D < 1800.0 && (S.GunT -= Dt) <= 0.f)
			{
				S.GunT = 0.5f;
				const FVector Dir = ToT.GetSafeNormal();
				AddBeam(S.Pos, T->Pos - Dir * T->Radius, 0.08f, FLinearColor(0.6f, 0.85f, 1.f));
				ApplyHit(*T, Dir, S.CraftKind == 2 ? 1.f : 3.f, T->Pos - Dir * T->Radius);
			}
		}
	}
	else if (M == TEXT("ew") && T)
	{
		Goal = T->Pos + FVector(FMath::Cos(Orbit), FMath::Sin(Orbit), 0.2f) * 5000.0;
		if (FVector::Dist(S.Pos, T->Pos) < 7000.0)
		{
			T->bJammed = true;
		}
	}
	else if (M == TEXT("recon"))
	{
		if (!T)
		{
			// nearest contact nobody has identified yet
			double Best = 1e18;
			for (FAstraBattleShip& O : Ships)
			{
				if (O.bAlive && !O.bCraft && !O.bPlayer && !O.bIdentified && FVector::Dist(O.Pos, S.Pos) < Best)
				{
					Best = FVector::Dist(O.Pos, S.Pos);
					T = &O;
				}
			}
			S.MissionTarget = T ? T->Id : -1;
		}
		if (T)
		{
			Goal = T->Pos + (S.Pos - T->Pos).GetSafeNormal() * (T->bDerelict ? 700.0 : 6000.0);   // a derelict is looked at up close
			if (!T->bIdentified && FVector::Dist(S.Pos, T->Pos) < 9000.0)
			{
				T->bIdentified = true;
				Report(FString::Printf(TEXT("flight: %s recon has identified %s: %s, %s"), *Q.CallSign, *T->ContactId, *T->Class, *T->Name));
			}
		}
		else
		{
			Goal = Carrier.Pos + Carrier.Att.GetForwardVector() * 9000.0 + FVector(FMath::Cos(Orbit), FMath::Sin(Orbit), 0.f) * 2000.0;
		}
	}
	else if (M == TEXT("sar"))
	{
		Goal = LastWreckPos;
		if (!LastWreckName.IsEmpty() && FVector::Dist(S.Pos, LastWreckPos) < 1200.0)
		{
			Report(FString::Printf(TEXT("flight: search and rescue at the wreck of the %s: lifeboats found, %d survivors picked up"),
			                       *LastWreckName, FMath::RandRange(18, 74)));
			LastWreckName.Empty();
			for (FAstraBattleShip& O : Ships)
			{
				if (O.bCraft && O.bAlive && O.Squadron == S.Squadron)
				{
					O.Mission = TEXT("recall");
				}
			}
		}
	}
	// fly: steer the velocity towards the goal, turn the airframe along it
	const FVector ToGoal = Goal - S.Pos;
	const double L = ToGoal.Size();
	const FVector DesiredVel = ToGoal / FMath::Max(L, 1.0) * FMath::Min((double)Speed, L * 0.8 + 60.0) + (M == TEXT("recall") ? Carrier.Vel : FVector::ZeroVector);
	S.Vel += (DesiredVel - S.Vel).GetClampedToMaxSize(S.MaxAccel * Dt);
	if (!S.Vel.IsNearlyZero())
	{
		const FQuat Want = FRotationMatrix::MakeFromX(S.Vel.GetSafeNormal()).ToQuat();
		const float MaxStep = FMath::DegreesToRadians(S.MaxTurnDeg * Dt);
		const float Ang = S.Att.AngularDistance(Want);
		S.Att = Ang <= MaxStep ? Want : FQuat::Slerp(S.Att, Want, MaxStep / Ang);
	}
	S.Pos += S.Vel * Dt;
}

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
	if (World && RingMesh && GlowMat)
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
	// the hulk: the ship's own mesh, burnt dark, drifting and tumbling slowly
	if (S.Actor)
	{
		FAstraWreck W;
		W.Actor = S.Actor;
		S.Actor = nullptr;
		W.Pos = S.Pos;
		W.Vel = Drift + FMath::VRand() * 4.f;
		W.Att = S.Att;
		W.SpinAxis = FMath::VRand();
		W.SpinDeg = FMath::FRandRange(1.5f, 4.5f);
		if (UStaticMeshComponent* C = W.Actor->GetStaticMeshComponent())
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
	if (World && CubeMesh)
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
		if (!W.Actor || (W.Life > 0.f && W.Age > W.Life) || FVector::Dist(W.Pos, Ships[0].Pos) > 200 * OneKm)
		{
			if (W.Actor) { W.Actor->Destroy(); }
			Wrecks.RemoveAtSwap(i);
			continue;
		}
		W.Actor->SetActorLocationAndRotation(ToWorld(W.Pos), ToWorldRot(W.Att));
	}
}

// ---------------------------------------------------------------------------------------------- the war director
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
	if (Type == TEXT("distress"))
	{
		++N;   // the ship calling for help comes first
	}
	N = FMath::Clamp(N, 1, 8);
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
	const FVector Centre = Ships[0].Pos + Polar(Range * OneKm, Bearing, FMath::FRandRange(-3.f, 5.f));
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
	if (Type == TEXT("raid") || Type == TEXT("reinforcements"))
	{
		const TArray<TSharedPtr<FJsonObject>> Specs = ShipSpecs(TEXT("ships"));
		int32 k = 0;
		int32 LeaderIdx = INDEX_NONE;
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
			if (Type == TEXT("raid") && Ships[I].Radius >= 200.f)
			{
				AddEnemyWing(I, 4, 30.f);
			}
			if (Type == TEXT("raid"))
			{
				Ships[I].TargetId = (k == 0 || Ships.Num() < 3) ? PlayerId : Ships[FMath::RandRange(0, 2)].Id;
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
			++k;
		}
		if (Type == TEXT("raid"))
		{
			bEngagementActive = true;
			bScenarioOver = false;
			bSurrenderAccepted = false;
			Report(FString::Printf(TEXT("sensors: %d new contacts at %.0f km, bearing %03.0f — Kharon Mandate raid group: %s; closing at 450 m/s"),
			                       k, Range, Bearing, *Listing));
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
		Ships[V].Hull = Ships[V].HullMax = 1500.f;   // a big hauler takes a while to die: time for the Aquila to get there
		Ships[V].Shield = Ships[V].ShieldMax = 200.f;
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
	StageDone = 3;
	bBriefed = true;
	FAstraBattleShip& P = Ships[0];
	P.Pos = FVector::ZeroVector;
	double V = 1.0;
	if (Save->TryGetNumberField(TEXT("hull_frac"), V)) { P.Hull = FMath::Clamp((float)V, 0.05f, 1.f) * P.HullMax; }
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
					A->bIdentified = true;
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
		if (S.bAlive && S.bHostile && !S.bCraft && !S.bFleeing && !S.bHoldFire && FVector::Dist(S.Pos, Ships[0].Pos) < WithinKm * OneKm)
		{
			++N;
		}
	}
	return N;
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
	TransmissionAt = -1.f;
	bEngagementActive = false;
	bScenarioOver = false;
	bSurrenderAccepted = false;
	StageDone = 3;
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
	return FString::Printf(TEXT("flying a Falcon of Alpha (callsign Eagle), %.1f km from the Aquila, hull %.0f%%, %d missiles; the XO has the conn "
	                            "and the Captain talks to the bridge by radio"),
	                       FVector::Dist(S->Pos, Ships[0].Pos) / OneKm, 100.f * S->Hull / S->HullMax, S->Missiles);
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
			AddFlash(S.Pos - S.Att.GetForwardVector() * (8.0 + 6.0 * k) + FMath::VRand() * 6.0, 4.f, 1.6f, FLinearColor(1.f, 0.75f, 0.4f), 90.f);
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
	AddBeam(Muzzle, Muzzle + Dir * HitT, 0.05f, FLinearColor(0.55f, 0.85f, 1.f));
	HullSound(TEXT("SW_PD_Burst"), 0.22f, 0.09f);
	if (Hit)
	{
		ApplyHit(*Hit, Dir, Hit->bCraft ? 14.f : 5.f, Muzzle + Dir * HitT);
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
