// ASTRA — battle simulation.

#include "AstraBattleSubsystem.h"

#include "ASTRA.h"
#include "AstraShipSubsystem.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/World.h"
#include "Kismet/GameplayStatics.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Sound/SoundBase.h"

namespace
{
	const double Km = 1000.0;
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
	FAutoConsoleCommand CmdBattleKill(TEXT("astra.battle.kill"), TEXT("Destroy a contact at once (testing effects): astra.battle.kill <contact id>"),
		FConsoleCommandWithArgsDelegate::CreateLambda([](const TArray<FString>& A) { if (A.Num()) { GKillRequests.Add(A[0].ToUpper()); } }));
	FAutoConsoleCommand CmdBattleSpawn(TEXT("astra.battle.spawn"),
		TEXT("Spawn a hostile ship for testing: astra.battle.spawn <styx|lethe|acheron> <range_km> <bearing relative to the bow, deg>"),
		FConsoleCommandWithArgsDelegate::CreateLambda([](const TArray<FString>& A)
		{
			if (A.Num() >= 3) { GSpawnRequests.Add({A[0].ToLower(), FCString::Atof(*A[1]), FCString::Atof(*A[2])}); }
		}));
	FAutoConsoleCommand CmdBattleTime(TEXT("astra.battle.time"), TEXT("Jump the scenario clock: astra.battle.time <seconds>"),
		FConsoleCommandWithArgsDelegate::CreateLambda([](const TArray<FString>& A) { if (A.Num()) { GBattleJumpTo = FCString::Atof(*A[0]); } }));
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
	int32 I = AddShip(TEXT("T-01"), TEXT("ASN Praetorian"), TEXT("ASTRA battleship (7th Fleet flagship)"), TEXT("SM_SHIP_ASTRA_Praetorian"),
	                  EAstraSide::Astra, A0 + Polar(4.5 * Km, 25, 3), 45.f, 288.f, 420.f, 3200.f, 1200.f);
	Ships[I].RailDamage = 90.f;
	Ships[I].RailCd = 9.f;
	Ships[I].PDChannels = 3;
	I = AddShip(TEXT("T-02"), TEXT("ASN Vigilant"), TEXT("ASTRA destroyer"), TEXT("SM_SHIP_ASTRA_Vigilant"), EAstraSide::Astra,
	            A0 + Polar(3 * Km, 70, 2), 45.f, 288.f, 140.f, 900.f, 380.f);
	I = AddShip(TEXT("T-07"), TEXT("Brightwater"), TEXT("Free Guilds freighter"), TEXT("SM_SHIP_GUILD_Freighter"), EAstraSide::Neutral,
	            A0 + Polar(22 * Km, 15, 4), 120.f, 180.f, 170.f, 700.f, 60.f);
	Ships[I].RailDamage = 0.f;
	Ships[I].Missiles = 0;
	I = AddShip(TEXT("T-11"), TEXT("Lethe"), TEXT("Kharon Mandate frigate, Lethe class"), TEXT("SM_SHIP_MANDATE_Lethe"), EAstraSide::Mandate,
	            A0 + Polar(30 * Km, 200, -3), 30.f, 0.f, 90.f, 520.f, 220.f);
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
		UMaterialInstanceDynamic* M = D->CreateAndSetMaterialInstanceDynamicFromMaterial(0, GlowMat);
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
	if (Ships.Num() == 0)
	{
		return;
	}
	const float Dt = FMath::Min(DeltaTime, 0.1f) * GBattleTimeScale;
	Time += Dt;
	if (GBattleJumpTo >= 0.f)
	{
		Time = GBattleJumpTo;
		GBattleJumpTo = -1.f;
	}
	for (const FSpawnRequest& R : GSpawnRequests)
	{
		const FRotator Bow = Ships[0].Att.Rotator();
		const FVector Pos = Ships[0].Pos + Polar(R.RangeKm * Km, Bow.Yaw + R.RelBearing, Bow.Pitch + 2.0);
		const bool bBig = R.Kind == TEXT("acheron");
		const FString Mesh = bBig ? TEXT("SM_SHIP_MANDATE_Acheron") : (R.Kind == TEXT("lethe") ? TEXT("SM_SHIP_MANDATE_Lethe") : TEXT("SM_SHIP_MANDATE_Styx"));
		// broadside to us: its heading is perpendicular to our line of sight
		const int32 I = AddShip(FString::Printf(TEXT("T-%d"), 30 + NextId), TEXT("Test contact"), TEXT("Kharon Mandate warship (test)"), Mesh,
		                        EAstraSide::Mandate, Pos, Bow.Yaw + R.RelBearing + 90.f, 200.f, bBig ? 240.f : 130.f, bBig ? 2200.f : 950.f, 380.f);
		Ships[I].bHostile = true;
		Ships[I].Mode = EAstraShipMode::Attack;
		Ships[I].TargetId = Ships[0].Id;
		SpawnVisual(Ships[I]);
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
	TickPlayer(Dt);
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
			S.Shield = FMath::Min(S.ShieldMax, S.Shield + S.ShieldRegen * S.ShieldPower * Dt);
		}
		S.ShieldFlash = FMath::Max(0.f, S.ShieldFlash - Dt * 2.5f);
	}
	TickProjectiles(Dt);
	TickFlashes(Dt);
	SyncVisuals();
}

void UAstraBattleSubsystem::TickPlayer(float Dt)
{
	FAstraBattleShip& P = Ships[0];
	if (const UAstraShipSubsystem* Ship = GetWorld()->GetSubsystem<UAstraShipSubsystem>())
	{
		P.Att = HeadingQuat(Ship->GetHeadingDeg(), Ship->GetMarkDeg());
		P.Vel = P.Att.GetForwardVector() * Ship->GetSpeedMps();
		P.bShieldsUp = Ship->AreShieldsUp() && Ship->PowerFactor(TEXT("shields")) > 0.05f;
		P.ShieldPower = Ship->PowerFactor(TEXT("shields"));
		P.WeaponPower = Ship->PowerFactor(TEXT("weapons"));
		const FString M = Ship->GetShieldMode();
		P.ShieldFacing = M == TEXT("forward") ? FVector(1, 0, 0) : M == TEXT("aft") ? FVector(-1, 0, 0)
		               : M == TEXT("port") ? FVector(0, -1, 0) : M == TEXT("starboard") ? FVector(0, 1, 0)
		               : M == TEXT("dorsal") ? FVector(0, 0, 1) : M == TEXT("ventral") ? FVector(0, 0, -1) : FVector::ZeroVector;
	}
	P.Pos += P.Vel * Dt;
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
		const FVector C = Ships[0].Pos + Polar(25 * Km, 70, 4);
		const int32 A = AddShip(TEXT("T-21"), TEXT("Acheron"), TEXT("Kharon Mandate cruiser (flagship of Archon Varek Solm)"),
		                        TEXT("SM_SHIP_MANDATE_Acheron"), EAstraSide::Mandate, C, 70.f, 500.f, 240.f, 3600.f, 1500.f);
		const int32 B = AddShip(TEXT("T-22"), TEXT("Styx"), TEXT("Kharon Mandate destroyer, Styx class"), TEXT("SM_SHIP_MANDATE_Styx"),
		                        EAstraSide::Mandate, C + Polar(4 * Km, 340, 1), 70.f, 550.f, 130.f, 1300.f, 500.f);
		const int32 D = AddShip(TEXT("T-23"), TEXT("Cocytus"), TEXT("Kharon Mandate destroyer, Styx class"), TEXT("SM_SHIP_MANDATE_Styx"),
		                        EAstraSide::Mandate, C + Polar(4 * Km, 160, -2), 70.f, 550.f, 130.f, 1300.f, 500.f);
		const int32 E = AddShip(TEXT("T-24"), TEXT("Phlegethon"), TEXT("Kharon Mandate destroyer, Styx class"), TEXT("SM_SHIP_MANDATE_Styx"),
		                        EAstraSide::Mandate, C + Polar(5 * Km, 250, 3), 70.f, 550.f, 130.f, 1300.f, 500.f);
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
	// outcome
	if (!bScenarioOver && StageDone == 2)
	{
		int32 Fighting = 0, Truce = 0;
		for (const FAstraBattleShip& S : Ships)
		{
			if (S.bAlive && S.bHostile)
			{
				Fighting += (!S.bFleeing && !S.bHoldFire) ? 1 : 0;
				Truce += S.bNegotiated ? 1 : 0;
			}
		}
		if (bSurrenderAccepted)
		{
			bScenarioOver = true;
			Report(TEXT("tactical: the Mandate has accepted our surrender and ceased fire — their ships are closing to board the Aquila; the battle for Aurelia is lost"));
		}
		else if (Fighting == 0)
		{
			bScenarioOver = true;
			Report(Truce > 0 ? TEXT("tactical: no Mandate ship is fighting any more — they hold fire or withdraw under the terms agreed over the channel; the battle for Aurelia is over")
			                 : TEXT("tactical: no hostile ship left in the engagement zone — the Mandate attack on Aurelia has been repelled"));
		}
		else if (Ships[0].Hull / Ships[0].HullMax < 0.08f)
		{
			bScenarioOver = true;
			Report(TEXT("engineering: hull integrity critical, main reactor containment failing — the Aquila cannot stay in the fight"));
		}
	}
}

void UAstraBattleSubsystem::TickAI(FAstraBattleShip& S, float Dt)
{
	FVector DesiredVel = S.Vel;
	FVector Face = S.Vel.IsNearlyZero() ? S.Att.GetForwardVector() : S.Vel.GetSafeNormal();
	FAstraBattleShip* T = FindById(S.TargetId);
	// rules of engagement: the fleet does not shoot at an enemy that has ceased fire or is withdrawing
	const bool bFleet = S.Side == EAstraSide::Astra && !S.bPlayer;
	const auto Engageable = [&S](const FAstraBattleShip& O)
	{
		return O.bAlive && !O.bCold && ((S.Side == EAstraSide::Mandate && O.Side == EAstraSide::Astra && !O.bCraft) ||
		                                (S.Side == EAstraSide::Astra && O.bHostile && !O.bFleeing && !O.bHoldFire));
	};
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
	// neutral freighter: run from any close hostile
	if (S.Side == EAstraSide::Neutral)
	{
		for (const FAstraBattleShip& O : Ships)
		{
			if (O.bAlive && O.bHostile && FVector::Dist(S.Pos, O.Pos) < 40 * Km)
			{
				DesiredVel = (S.Pos - O.Pos).GetSafeNormal() * 260.f;
				Face = DesiredVel.GetSafeNormal();
			}
		}
	}
	if (S.Mode == EAstraShipMode::Attack && T)
	{
		// hold a preferred engagement range, circling at an angle; break off when badly hurt
		const float Pref = S.Radius > 200.f ? 4 * Km : 3 * Km;
		const FVector ToT = T->Pos - S.Pos;
		const double Dist = ToT.Size();
		const FVector Dir = ToT / FMath::Max(1.0, Dist);
		const FVector Side = FVector::CrossProduct(Dir, FVector::UpVector).GetSafeNormal();
		FVector Goal = T->Pos - Dir * Pref + Side * Pref * 0.35;
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
		if (FVector::Dist(S.Pos, Ships[0].Pos) > 160 * Km && S.bAlive)
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
		if (S.Side == EAstraSide::Mandate)
		{
			for (FAstraBattleShip& C : Ships)
			{
				if (Channels <= 0)
				{
					break;
				}
				if (C.bCraft && C.bAlive && C.Side == EAstraSide::Astra && FVector::Dist(C.Pos, S.Pos) < 1500.f + S.Radius)
				{
					--Channels;
					S.PDT = 0.5f;
					AddBeam(S.Pos + (C.Pos - S.Pos).GetSafeNormal() * S.Radius * 0.6, C.Pos, 0.1f, FLinearColor(1.f, 0.6f, 0.3f));
					if (FMath::FRand() < (C.CraftKind == 0 ? 0.07f : (C.CraftKind == 1 ? 0.1f : 0.14f)))
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
	if (S.Missiles > 0 && S.MissileT <= 0.f && Dist < S.MissileRange && Dist > 2.5 * Km)
	{
		S.MissileT = S.MissileCd * FMath::FRandRange(0.8f, 1.2f);
		const int32 N = FMath::Min(S.Missiles, S.Radius > 200.f ? 4 : 2);
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
	if (Dist < 4 * Km && FMath::FRand() < Dt * 0.6f)
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
			                  *T->ContactId, Dist / Km, P.RailRange / Km, P.RailVolleys)
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
		OutDetail = FString::Printf(TEXT("%d missiles away at %s, %d left in the VLS, time to target about %.0f s"), N, *T->ContactId,
		                            P.Missiles, Dist / 1400.0 + 2.0);
	}
	else if (W == TEXT("lasers"))
	{
		P.FireTarget = T->Id;
		P.LaserShots = FMath::Clamp(Salvo, 1, 12) * 2;
		OutDetail = Dist > 4 * Km ? FString::Printf(TEXT("lasers assigned to %s, now at %.1f km: they fire once it is inside 4 km"), *T->ContactId, Dist / Km)
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
			F.TargetRangeKm = FVector::Dist(P.Pos, T->Pos) / Km;
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
		B.RangeKm = FVector::Dist(S.Pos, P.Pos) / Km;
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
		                                        *T->ContactId, P.RailRange / Km, Dist / Km, P.RailVolleys)
		                      : FString::Printf(TEXT("engaging %s, %d volleys left, next in %.0f s"), *T->ContactId, P.RailVolleys, P.RailT))
		: FString::Printf(TEXT("ready, 4 twin turrets, range %.0f km, one volley every %.0f s"), P.RailRange / Km, P.RailCd));
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
	if (P.RailVolleys > 0 && P.RailT <= 0.f && Dist <= P.RailRange)
	{
		P.RailT = P.RailCd / FMath::Max(0.25f, P.WeaponPower);   // capacitor recharge follows weapons power
		--P.RailVolleys;
		for (int32 i = 0; i < P.RailSlugs; ++i)
		{
			FireRail(P, *T, 0.001f + Dist / 30e6);
		}
	}
	if (P.LaserShots > 0 && P.LaserT <= 0.f && Dist <= 4 * Km)
	{
		P.LaserT = 0.5f;
		--P.LaserShots;
		FireLaser(P, *T);
	}
}

bool UAstraBattleSubsystem::PlayerScan(const FString& ContactId, FString& OutDetail)
{
	FAstraBattleShip* T = ContactId.IsEmpty() ? nullptr : FindByContact(ContactId);
	if (T && T->ContactId == TEXT("T-11") && StageDone == 0)
	{
		Time = FMath::Max(Time, 78.f);   // the ping gives us away: the frigate reacts
		OutDetail = TEXT("active ping on T-11: hull ~160 m, reactor warm, weapons ports detected — it has seen us");
		return true;
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
	OutRangeKm = D / Km;
	return true;
}

FString UAstraBattleSubsystem::MandateCommander() const
{
	for (const TCHAR* C : {TEXT("T-21"), TEXT("T-22"), TEXT("T-23"), TEXT("T-24"), TEXT("T-11")})
	{
		const FAstraBattleShip* S = Ships.FindByPredicate([C](const FAstraBattleShip& X) { return X.ContactId == C; });
		if (S && S->bAlive && S->bHostile)
		{
			return C;
		}
	}
	return FString();
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
			Ship->OnHullHit(ToHull, Damage - ToHull, FromDir);
		}
		if (USoundBase* S = LoadObject<USoundBase>(nullptr, TEXT("/Game/ASTRA/Audio/SW_Impact.SW_Impact")))
		{
			UGameplayStatics::PlaySound2D(GetWorld(), S, FMath::Clamp(0.4f + ToHull / 60.f, 0.4f, 1.f));
		}
	}
	if (To.Hull <= 0.f)
	{
		Destroy(To);
	}
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
	if (S.bCraft)
	{
		if (Squadrons.IsValidIndex(S.Squadron))
		{
			--Squadrons[S.Squadron].Total;
			++Squadrons[S.Squadron].LostSinceReport;
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
	if (StageDone < 2)
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
			// the plume at the stern, never smaller than ~0.25 degrees (a torch drive is visible from far away)
			const FVector Stern = ToWorld(S.Pos - S.Att.GetForwardVector() * S.Radius * 1.05);
			const float Dist = Stern.Size() / 100.f;
			const float Speed = S.Vel.Size();
			const float Throttle = FMath::Clamp(Speed / 400.f, 0.15f, 1.f);
			S.DriveFlare->SetActorLocation(Stern);
			S.DriveFlare->SetActorScale3D(FVector(FMath::Max(S.Radius * 0.12f, Dist * 0.0045f) * Throttle));
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
				O->SetNumberField(TEXT("hull_pct"), FMath::RoundToDouble(100.0 * S.Hull / S.HullMax));
				O->SetNumberField(TEXT("shields_pct"), FMath::RoundToDouble(100.0 * S.Shield / S.ShieldMax));
				O->SetNumberField(TEXT("missiles_left"), S.Missiles);
				O->SetNumberField(TEXT("range_to_aquila_km"), FMath::RoundToDouble(FVector::Dist(S.Pos, Aquila) / 100.0) / 10.0);
				if (S.ContactId == Cmd)
				{
					O->SetBoolField(TEXT("commands_the_strike_group"), true);
				}
			}
			Own.Add(MakeShared<FJsonValueObject>(O));
		}
		else if (S.Side == EAstraSide::Astra && S.bAlive && !S.bCraft)
		{
			if (S.bPlayer)
			{
				O->SetStringField(TEXT("name"), TEXT("ASN Aquila (the ship on the channel)"));
			}
			O->SetNumberField(TEXT("hull_pct"), FMath::RoundToDouble(100.0 * S.Hull / S.HullMax));
			O->SetNumberField(TEXT("shields_pct"), FMath::RoundToDouble(100.0 * S.Shield / S.ShieldMax));
			Foe.Add(MakeShared<FJsonValueObject>(O));
		}
	}
	V->SetArrayField(TEXT("your_ships"), Own);
	V->SetArrayField(TEXT("astra_ships"), Foe);
	int32 Craft = 0;
	for (const FAstraBattleShip& S : Ships)
	{
		Craft += (S.bCraft && S.bAlive) ? 1 : 0;
	}
	V->SetNumberField(TEXT("astra_fighters_and_drones_airborne"), Craft);
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
		O->SetStringField(TEXT("status"), S.bCold ? TEXT("unidentified, cold drive, drifting")
		                                          : (S.bHostile ? (S.bFleeing ? TEXT("hostile, retreating") : (S.bHoldFire ? TEXT("hostile, holding fire") : TEXT("hostile"))) : SideName(S.Side)));
		O->SetNumberField(TEXT("range_km"), FMath::RoundToDouble(FVector::Dist(P.Pos, S.Pos) / 100.0) / 10.0);
		O->SetNumberField(TEXT("bearing_deg"), FMath::RoundToDouble(BearingDeg(P.Pos, S.Pos)));
		O->SetNumberField(TEXT("mark_deg"), FMath::RoundToDouble(MarkDeg(P.Pos, S.Pos)));
		if (!S.bCold)
		{
			O->SetNumberField(TEXT("speed_mps"), FMath::RoundToDouble(S.Vel.Size()));
			O->SetNumberField(TEXT("shields_pct"), FMath::RoundToDouble(100.0 * S.Shield / S.ShieldMax));
			O->SetNumberField(TEXT("hull_pct"), FMath::RoundToDouble(100.0 * S.Hull / S.HullMax));
		}
		Out.Add(MakeShared<FJsonValueObject>(O));
	}
	return Out;
}

// ------------------------------------------------------------------------------------------------ flight groups
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
	const int32 Qi = Squadrons.IndexOfByPredicate([&Name](const FAstraSquadron& Q) { return Q.Name.Equals(Name, ESearchCase::IgnoreCase); });
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
	if (M == TEXT("escort") && T->Side != EAstraSide::Astra)
	{
		OutDetail = TEXT("escort is for friendly ships");
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
	const int32 Qi = Squadrons.IndexOfByPredicate([&Name](const FAstraSquadron& Q) { return Q.Name.Equals(Name, ESearchCase::IgnoreCase); });
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
			Report(FString::Printf(TEXT("flight: %s squadron has lost %d %s%s to enemy fire, %d left"), *Q.Name, Q.LostSinceReport, *Q.CallSign,
			                       Q.LostSinceReport > 1 ? TEXT("s") : TEXT(""), Q.Total));
			Q.LostSinceReport = 0;
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
		Q.LaunchT = 2.f / FMath::Max(0.3f, Deck);
		--Q.ToLaunch;
		--Q.OnDeck;
		++Q.Launched;
		const FAstraBattleShip& P = Ships[0];
		const float Side = (Q.Launched % 2) ? 1.f : -1.f;
		const FVector Pos = P.Pos + P.Att.RotateVector(FVector(-60.0, Side * 40.0, -30.0));
		const float Radius = Q.Kind == 1 ? 14.f : (Q.Kind == 2 ? 5.f : 10.f);
		const float Hull = Q.Kind == 1 ? 110.f : (Q.Kind == 2 ? 25.f : 60.f);
		const TCHAR* Role = Q.Kind == 1 ? TEXT("torpedo bomber") : (Q.Kind == 2 ? TEXT("drone") : TEXT("fighter"));
		const int32 I = AddShip(FString::Printf(TEXT("%s-%d"), *Q.CallSign.ToUpper(), Q.Launched), FString::Printf(TEXT("%s %d"), *Q.CallSign, Q.Launched),
		                        FString::Printf(TEXT("ASTRA %s (%s)"), Role, *Q.CallSign), Q.Mesh, EAstraSide::Astra, Pos, P.Att.Rotator().Yaw, 200.f,
		                        Radius, Hull, Q.Kind == 2 ? 0.f : 20.f);
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
		C.Vel = P.Vel + P.Att.RotateVector(FVector(120.0, Side * 80.0, -40.0));
		C.CruiseSpeed = Q.Kind == 1 ? 650.f : (Q.Kind == 2 ? 900.f : 850.f);
		C.MaxAccel = 160.f;
		C.MaxTurnDeg = 45.f;
		C.OrbitPhase = FMath::FRand() * 2.f * PI;
		C.Mode = EAstraShipMode::Cruise;
		SpawnVisual(C);
		if (Q.ToLaunch == 0 && !Q.bAirborneReported)
		{
			Q.bAirborneReported = true;
			Report(FString::Printf(TEXT("flight: %s squadron airborne, %d %ss on %s"), *Q.Name, Q.Launched, *Q.CallSign, *Q.Mission.ToUpper()));
		}
	}
}

void UAstraBattleSubsystem::TickCraft(FAstraBattleShip& S, float Dt)
{
	FAstraBattleShip& Carrier = Ships[0];
	FAstraSquadron& Q = Squadrons[S.Squadron];
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
			Goal = T->Pos + (S.Pos - T->Pos).GetSafeNormal() * 6000.0;
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
	for (int32 i = Wrecks.Num() - 1; i >= 0; --i)
	{
		FAstraWreck& W = Wrecks[i];
		W.Age += Dt;
		W.Pos += W.Vel * Dt;
		W.Att = FQuat(W.SpinAxis, FMath::DegreesToRadians(W.SpinDeg * Dt)) * W.Att;
		if (!W.Actor || (W.Life > 0.f && W.Age > W.Life) || FVector::Dist(W.Pos, Ships[0].Pos) > 200 * Km)
		{
			if (W.Actor) { W.Actor->Destroy(); }
			Wrecks.RemoveAtSwap(i);
			continue;
		}
		W.Actor->SetActorLocationAndRotation(ToWorld(W.Pos), ToWorldRot(W.Att));
	}
}
