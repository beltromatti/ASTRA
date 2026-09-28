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

	// the Aquila first (index 0): the player's ship, heading 045 mark 10 like the helm
	const int32 P = AddShip(TEXT("AQUILA"), TEXT("ASN Aquila"), TEXT("Aquila-class carrier cruiser"), TEXT(""), EAstraSide::Astra,
	                        FVector::ZeroVector, 45.f, 419.f, 330.f, 2400.f, 900.f);
	Ships[P].bPlayer = true;
	Ships[P].RailCd = 5.f;
	Ships[P].RailRange = 10000.f;
	Ships[P].RailDamage = 70.f;
	Ships[P].Missiles = 96;
	Ships[P].Att = HeadingQuat(45.0, 0.0);

	const FVector A0 = FVector::ZeroVector;
	int32 I = AddShip(TEXT("T-01"), TEXT("ASN Praetorian"), TEXT("ASTRA battleship (7th Fleet flagship)"), TEXT("SM_SHIP_ASTRA_Praetorian"),
	                  EAstraSide::Astra, A0 + Polar(4.5 * Km, 25, 3), 45.f, 419.f, 420.f, 3200.f, 1200.f);
	Ships[I].RailDamage = 90.f;
	Ships[I].RailCd = 6.f;
	I = AddShip(TEXT("T-02"), TEXT("ASN Vigilant"), TEXT("ASTRA destroyer"), TEXT("SM_SHIP_ASTRA_Vigilant"), EAstraSide::Astra,
	            A0 + Polar(3 * Km, 70, 2), 45.f, 419.f, 140.f, 900.f, 380.f);
	I = AddShip(TEXT("T-07"), TEXT("Brightwater"), TEXT("Free Guilds freighter"), TEXT("SM_SHIP_GUILD_Freighter"), EAstraSide::Neutral,
	            A0 + Polar(22 * Km, 15, 4), 120.f, 180.f, 170.f, 700.f, 60.f);
	Ships[I].RailDamage = 0.f;
	Ships[I].Missiles = 0;
	I = AddShip(TEXT("T-11"), TEXT("Lethe"), TEXT("Kharon Mandate frigate, Lethe class"), TEXT("SM_SHIP_MANDATE_Lethe"), EAstraSide::Mandate,
	            A0 + Polar(30 * Km, 200, -3), 30.f, 0.f, 90.f, 520.f, 220.f);
	Ships[I].bCold = true;
	Ships[I].bIdentified = false;
	Ships[I].Missiles = 8;

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
	if (SphereMesh && ShellMat)
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
	TickPlayer(Dt);
	TickScenario(Dt);
	for (FAstraBattleShip& S : Ships)
	{
		if (!S.bAlive)
		{
			continue;
		}
		if (!S.bPlayer)
		{
			TickAI(S, Dt);
		}
		TickWeapons(S, Dt);
		if (S.bShieldsUp)
		{
			S.Shield = FMath::Min(S.ShieldMax, S.Shield + S.ShieldRegen * Dt);
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
		P.bShieldsUp = Ship->AreShieldsUp();
	}
	P.Pos += P.Vel * Dt;
}

void UAstraBattleSubsystem::TickScenario(float Dt)
{
	FAstraBattleShip* Frigate = FindByContact(TEXT("T-11"));
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
		                        TEXT("SM_SHIP_MANDATE_Acheron"), EAstraSide::Mandate, C, 70.f, 500.f, 240.f, 2200.f, 900.f);
		const int32 B = AddShip(TEXT("T-22"), TEXT("Styx"), TEXT("Kharon Mandate destroyer, Styx class"), TEXT("SM_SHIP_MANDATE_Styx"),
		                        EAstraSide::Mandate, C + Polar(4 * Km, 340, 1), 70.f, 550.f, 130.f, 950.f, 380.f);
		const int32 D = AddShip(TEXT("T-23"), TEXT("Cocytus"), TEXT("Kharon Mandate destroyer, Styx class"), TEXT("SM_SHIP_MANDATE_Styx"),
		                        EAstraSide::Mandate, C + Polar(4 * Km, 160, -2), 70.f, 550.f, 130.f, 950.f, 380.f);
		for (int32 Idx : {A, B, D})
		{
			FAstraBattleShip& S = Ships[Idx];
			S.bHostile = true;
			S.Mode = EAstraShipMode::Attack;
			S.CruiseSpeed = 450.f;
			S.TargetId = Idx == A ? Ships[0].Id : (Idx == B ? Ships[0].Id : Ships[1].Id);
			SpawnVisual(S);
		}
		Ships[A].RailDamage = 80.f;
		for (FAstraBattleShip& S : Ships)   // the fleet engages
		{
			if (S.Side == EAstraSide::Astra && !S.bPlayer && S.bAlive)
			{
				S.Mode = EAstraShipMode::Attack;
				S.TargetId = Ships[A].Id;
			}
		}
		Report(TEXT("sensors: three new contacts at 25 km, bearing 070 — Kharon Mandate strike group: cruiser Acheron (T-21) "
		            "and two Styx-class destroyers (T-22, T-23), closing at 450 m/s; the 7th Fleet is moving to engage"));
	}
	// outcome
	if (!bScenarioOver && StageDone == 2)
	{
		bool bAnyHostile = false;
		for (const FAstraBattleShip& S : Ships)
		{
			bAnyHostile |= (S.bAlive && S.bHostile && !S.bFleeing);
		}
		if (!bAnyHostile)
		{
			bScenarioOver = true;
			Report(TEXT("tactical: no hostile ship left in the engagement zone — the Mandate attack on Aurelia has been repelled"));
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
	if (T && !T->bAlive)
	{
		T = nullptr;
		S.TargetId = -1;
	}
	// hostiles pick a target if theirs died; the fleet retargets too
	if (!T && S.Mode == EAstraShipMode::Attack)
	{
		double Best = 1e18;
		for (FAstraBattleShip& O : Ships)
		{
			const bool bEnemy = (S.Side == EAstraSide::Mandate && O.Side == EAstraSide::Astra) ||
			                    (S.Side == EAstraSide::Astra && O.bHostile);
			if (O.bAlive && bEnemy && !O.bCold)
			{
				const double D = FVector::Dist(S.Pos, O.Pos);
				if (D < Best) { Best = D; T = &O; }
			}
		}
		S.TargetId = T ? T->Id : -1;
		if (!T) { S.Mode = EAstraShipMode::Cruise; }
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
	if (S.Mode == EAstraShipMode::Evade)
	{
		DesiredVel = (S.Pos - Ships[0].Pos).GetSafeNormal() * S.CruiseSpeed * 1.3f;
		Face = DesiredVel.GetSafeNormal();
		if (FVector::Dist(S.Pos, Ships[0].Pos) > 160 * Km && S.bAlive)
		{
			S.bAlive = false;   // out of the theatre (jumped away)
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
		for (FAstraProjectile& Pr : Projectiles)
		{
			if (!Pr.bDead && Pr.Kind == EAstraProjKind::Missile && Pr.Target == S.Id && FVector::Dist(Pr.Pos, S.Pos) < S.PDRange + S.Radius)
			{
				S.PDT = S.bPlayer ? 0.35f : 0.7f;
				AddBeam(S.Pos + (Pr.Pos - S.Pos).GetSafeNormal() * S.Radius * 0.6, Pr.Pos, 0.12f, FLinearColor(1.f, 0.85f, 0.5f));
				if (FMath::FRand() < (S.bPlayer ? 0.45f : 0.3f))
				{
					Pr.bDead = true;
					AddFlash(Pr.Pos, 25.f, 0.6f, FLinearColor(1.f, 0.7f, 0.35f), 60.f);
					if (S.bPlayer)
					{
						Report(TEXT("tactical: point defense splashed an incoming missile"), false);
					}
				}
				break;
			}
		}
	}
	if (S.bPlayer || S.Mode != EAstraShipMode::Attack || S.bFleeing)
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
		for (int32 i = 0; i < 2; ++i)
		{
			FireRail(S, *T, 0.0012f + Dist / 30e6);
		}
	}
	if (S.Missiles > 0 && S.MissileT <= 0.f && Dist < S.MissileRange && Dist > 2.5 * Km)
	{
		S.MissileT = S.MissileCd * FMath::FRandRange(0.8f, 1.2f);
		const int32 N = FMath::Min(S.Missiles, S.Radius > 200.f ? 4 : 2);
		for (int32 i = 0; i < N; ++i)
		{
			FireMissile(S, *T);
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
	Pr.Damage = 140.f;
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
	FAstraBattleShip& P = Ships[0];
	const double Dist = FVector::Dist(P.Pos, T->Pos);
	const FString W = Weapon.ToLower();
	if (W == TEXT("railguns"))
	{
		if (Dist > P.RailRange)
		{
			OutDetail = FString::Printf(TEXT("target at %.0f km, beyond railgun range (%.0f km)"), Dist / Km, P.RailRange / Km);
			return false;
		}
		for (int32 i = 0; i < FMath::Clamp(Salvo, 1, 8) * 2; ++i)
		{
			FireRail(P, *T, 0.001f + Dist / 30e6);
		}
		OutDetail = FString::Printf(TEXT("railgun salvo x%d away at %s, time of flight %.1f s"), FMath::Clamp(Salvo, 1, 8), *T->ContactId, Dist / 12000.0);
	}
	else if (W == TEXT("missiles") || W == TEXT("torpedoes"))
	{
		const int32 N = FMath::Clamp(Salvo, 1, 12);
		if (P.Missiles < N)
		{
			OutDetail = TEXT("not enough missiles in the VLS");
			return false;
		}
		for (int32 i = 0; i < N; ++i)
		{
			FireMissile(P, *T);
		}
		P.Missiles -= N;
		OutDetail = FString::Printf(TEXT("%d missiles away at %s, %d left"), N, *T->ContactId, P.Missiles);
	}
	else if (W == TEXT("lasers"))
	{
		if (Dist > 4 * Km)
		{
			OutDetail = FString::Printf(TEXT("target at %.1f km, beyond laser range (4 km)"), Dist / Km);
			return false;
		}
		for (int32 i = 0; i < FMath::Clamp(Salvo, 1, 12); ++i)
		{
			FireLaser(P, *T);
		}
		OutDetail = FString::Printf(TEXT("laser batteries firing on %s"), *T->ContactId);
	}
	else
	{
		OutDetail = FString::Printf(TEXT("unknown weapon %s"), *Weapon);
		return false;
	}
	if (!T->bHostile && T->Side == EAstraSide::Neutral)
	{
		OutDetail += TEXT(" (WARNING: the target is a neutral civilian vessel)");
	}
	return true;
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
		const float Absorb = FMath::Min(To.Shield, Damage * 0.85f);
		To.Shield -= Absorb;
		ToHull = Damage - Absorb;
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
	S.bAlive = false;
	S.Mode = EAstraShipMode::Dead;
	AddFlash(S.Pos, S.Radius * 2.2f, 4.f, FLinearColor(1.f, 0.55f, 0.25f), 120.f);
	AddFlash(S.Pos, S.Radius * 1.2f, 2.f, FLinearColor(1.f, 0.9f, 0.7f), 400.f);
	if (S.Actor) { S.Actor->Destroy(); S.Actor = nullptr; }
	if (S.ShieldBubble) { S.ShieldBubble->Destroy(); S.ShieldBubble = nullptr; }
	if (S.DriveFlare) { S.DriveFlare->Destroy(); S.DriveFlare = nullptr; }
	if (!S.bPlayer)
	{
		Report(FString::Printf(TEXT("tactical: %s (%s, %s) destroyed"), *S.Name, *S.ContactId, *S.Class));
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
			Pr.Vel += (To.GetSafeNormal() * 1600.f - Pr.Vel).GetClampedToMaxSize(900.f * Dt);
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
		F.MID = C->CreateAndSetMaterialInstanceDynamicFromMaterial(0, GlowMat);
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
	for (int32 i = Flashes.Num() - 1; i >= 0; --i)
	{
		FAstraFlash& F = Flashes[i];
		F.Age += Dt;
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
		const float K = F.Age / FMath::Max(0.01f, F.Life);
		if (F.bBeam)
		{
			const FVector A = ToWorld(F.Pos), B = ToWorld(F.BeamTo);
			const FVector D = B - A;
			F.Actor->SetActorLocationAndRotation((A + B) * 0.5, FRotationMatrix::MakeFromZ(D.GetSafeNormal()).Rotator());
			F.Actor->SetActorScale3D(FVector(1.5f, 1.5f, D.Size() / 100.f));
		}
		else
		{
			F.Actor->SetActorLocation(ToWorld(F.Pos));
			F.Actor->SetActorScale3D(FVector(F.Size * (0.4f + 1.6f * FMath::Sqrt(K))));   // metres -> sphere scale (100 cm mesh)
		}
		if (F.MID)
		{
			F.MID->SetScalarParameterValue(TEXT("Fade"), FMath::Square(1.f - K));
		}
	}
}

float UAstraBattleSubsystem::ConsumeShake(float DeltaTime)
{
	const float S = Shake;
	Shake = FMath::Max(0.f, Shake - DeltaTime * 1.2f);
	return S;
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
		if (S.bPlayer || !S.bAlive)
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
		                                          : (S.bHostile ? (S.bFleeing ? TEXT("hostile, retreating") : TEXT("hostile")) : SideName(S.Side)));
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
