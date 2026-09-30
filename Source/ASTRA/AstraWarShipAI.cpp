// ASTRA — one warship's mind (docs/GUERRA.md, F2.2): the right range for its armament, its weapons' fields of fire kept on
// the target, its strongest shield towards the threat, point defence on the most dangerous missiles, and no collisions.
// It thinks about ten times a second (each ship on its own phase, slower with a shot-up bridge) and moves every tick.
// The battle group (AstraWarGroups.cpp) tells it where to be and what to shoot; the ship keeps the orders of the minds too
// (OrderTarget, Stance, salvo, conserve), which the group respects.

#include "AstraBattleSubsystem.h"
#include "AstraWarClasses.h"
#include "AstraWarAI.h"
#include "ASTRA.h"
#include "AstraShipSubsystem.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMeshActor.h"

namespace
{
	const double WarKm = 1000.0;
}

// ---------------------------------------------------------------------------------------------- what a ship can do
double UAstraBattleSubsystem::ShipDps(const FAstraBattleShip& S, double RangeM) const
{
	double Dps = 0.0;
	const float Power = FMath::Clamp(PowerFactorOf(S), 0.f, 1.5f);
	for (const FAstraMount& M : S.Mounts)
	{
		if (M.Health < 0.2f)
		{
			continue;
		}
		if (M.Kind == EAstraMountKind::Rail && S.RailDamage > 0.f && RangeM < S.RailRange)
		{
			Dps += M.Barrels * S.RailDamage / FMath::Max(1.f, S.RailCd) * M.Health;
		}
		else if (M.Kind == EAstraMountKind::Laser && S.LaserDamage > 0.f && RangeM < S.LaserRange)
		{
			Dps += M.Barrels * S.LaserDamage / FMath::Max(1.f, S.LaserCd) * M.Health;
		}
	}
	if (S.Missiles > 0 && RangeM > 2500.0 && RangeM < S.MissileRange)
	{
		Dps += (S.Radius > 200.f ? 4.0 : 2.0) * 110.0 / FMath::Max(1.f, S.MissileCd) * 0.5;   // half of them meet point defence
	}
	return Dps * Power;
}

float UAstraBattleSubsystem::Readiness(const FAstraBattleShip& S) const
{
	if (!S.bAlive || S.bDisabled)
	{
		return 0.f;
	}
	if (!S.Dmg.bModel)
	{
		return FMath::Clamp(S.Hull / FMath::Max(1.f, S.HullMax), 0.f, 1.f);
	}
	float Guns = 0.f, Total = 0.f;
	for (const FAstraMount& M : S.Mounts)
	{
		Total += 1.f;
		Guns += M.Health >= 0.2f ? M.Health : 0.f;
	}
	const float GunF = Total > 0.f ? Guns / Total : 1.f;
	const float ShieldF = S.ShieldMax > 0.f ? S.Shield / S.ShieldMax : 1.f;
	return FMath::Clamp(0.5f * (S.Hull / FMath::Max(1.f, S.HullMax)) + 0.25f * ShieldF + 0.15f * GunF + 0.10f * EngineFactor(S), 0.f, 1.f);
}

bool UAstraBattleSubsystem::CanEngage(const FAstraBattleShip& S, const FAstraBattleShip& O) const
{
	const int32 Me = AstraSideIdx(S.Side);
	if (!O.bAlive || O.bCold || O.bDisabled || O.bGhost || O.bDerelict || Me < 0)
	{
		return false;
	}
	if (AstraSideIdx(O.Side) != 1 - Me || O.bCraft)
	{
		return false;                                        // warships shoot at warships (craft are point defence's)
	}
	if (O.bHoldFire || (O.bFleeing && O.bNegotiated))
	{
		return false;                                        // it has ceased fire, or withdraws under agreed terms
	}
	return Knows(Me, O);
}

FAstraBattleGroup* UAstraBattleSubsystem::FindGroup(int32 Id)
{
	return Id < 0 ? nullptr : Groups.FindByPredicate([Id](const FAstraBattleGroup& G) { return G.Id == Id; });
}

FAstraBattleShip* UAstraBattleSubsystem::ChooseTarget(FAstraBattleShip& S, FAstraBattleGroup* G)
{
	const int32 Me = AstraSideIdx(S.Side);
	// the minds' orders first (the Mandate commander's focus of fire, the Captain's request to the fleet)
	if (S.OrderTarget >= 0)
	{
		FAstraBattleShip* F = FindById(S.OrderTarget);
		if (F && CanEngage(S, *F))
		{
			return F;
		}
		S.OrderTarget = -1;                                   // gone: back to the group's choice
	}
	const double Reach = FMath::Max(S.RailRange, S.LaserRange) * 1.6 + S.Radius;
	if (G && G->FocusTarget >= 0)
	{
		FAstraBattleShip* F = FindById(G->FocusTarget);
		if (F && CanEngage(S, *F) && FVector::Dist(S.Pos, KnownPos(Me, *F)) < FMath::Max(Reach, (double)G->EngageRange * 2.2))
		{
			return F;
		}
	}
	// the nearest it can engage
	FAstraBattleShip* Best = nullptr;
	double BestD = 1e18;
	for (FAstraBattleShip& O : Ships)
	{
		if (!CanEngage(S, O))
		{
			continue;
		}
		const double D = FVector::DistSquared(S.Pos, KnownPos(Me, O));
		if (D < BestD)
		{
			BestD = D;
			Best = &O;
		}
	}
	return Best;
}

// ---------------------------------------------------------------------------------------------- facing
/** The heading that keeps its guns on the target and its strongest shield and plating between it and the threat. */
FVector UAstraBattleSubsystem::ChooseFacing(const FAstraBattleShip& S, const FVector& ToTarget, double Dist) const
{
	if (S.Mounts.Num() == 0 || ToTarget.IsNearlyZero())
	{
		return ToTarget.GetSafeNormal();
	}
	const FVector Dir = ToTarget.GetSafeNormal();
	// candidate headings: the bearing to the target turned in the horizontal plane
	static const float Turns[9] = {0.f, 35.f, -35.f, 70.f, -70.f, 100.f, -100.f, 140.f, 180.f};
	const FVector Up = FMath::Abs(Dir.Z) > 0.95 ? FVector::ForwardVector : FVector::UpVector;
	float BestScore = -1e9f;
	FVector Best = Dir;
	// what the shields look like on each face (a fraction of full): the strong face should meet the fire
	const FAstraShipDamage& D = S.Dmg;
	for (int32 k = 0; k < 9; ++k)
	{
		const FVector H = FQuat(Up, FMath::DegreesToRadians(Turns[k])).RotateVector(Dir).GetSafeNormal();
		const FQuat Att = FRotationMatrix::MakeFromX(H).ToQuat();
		const FVector Local = Att.UnrotateVector(Dir);            // the target in the ship's frame at this heading
		float Guns = 0.f;
		for (const FAstraMount& M : S.Mounts)
		{
			if (!M.CanBear(Local))
			{
				continue;
			}
			if (M.Kind == EAstraMountKind::Rail && Dist < S.RailRange)
			{
				Guns += M.Barrels * S.RailDamage / FMath::Max(1.f, S.RailCd) * M.Health;
			}
			else if (M.Kind == EAstraMountKind::Laser && Dist < S.LaserRange)
			{
				Guns += M.Barrels * S.LaserDamage / FMath::Max(1.f, S.LaserCd) * M.Health;
			}
		}
		float Guard = 1.f;
		if (D.bModel && D.Pool > 0.f)
		{
			const int32 F = AstraFacingOf(Local);                  // the face that would take the fire
			const float Frac = D.SectorMax[F] > 0.f ? D.Sector[F] / D.SectorMax[F] : 0.f;
			Guard = 0.7f + 0.6f * Frac * (0.5f + 2.f * D.Base[F]);   // a full, thick face: better
		}
		const float Cost = 1.f - 0.25f * FMath::Abs(Turns[k]) / 180.f;   // a heading close to the present one is cheaper to take
		const float Score = (Guns + 4.f) * Guard * Cost;
		if (Score > BestScore * 1.0f)
		{
			BestScore = Score;
			Best = H;
		}
	}
	return Best;
}

// ---------------------------------------------------------------------------------------------- collisions
FVector UAstraBattleSubsystem::AvoidanceVel(const FAstraBattleShip& S) const
{
	FVector Push = FVector::ZeroVector;
	for (const FAstraBattleShip& O : Ships)
	{
		if (O.Id == S.Id || !O.bAlive || O.bCraft || O.bGhost)
		{
			continue;
		}
		const FVector Rel = O.Pos - S.Pos;
		const double Reach = (S.Radius + O.Radius) * 1.6 + 250.0;
		if (Rel.SizeSquared() > FMath::Square(Reach + 9000.0))
		{
			continue;
		}
		const FVector RelV = O.Vel - S.Vel;
		const double V2 = RelV.SizeSquared();
		const double Tc = V2 > 1.0 ? FMath::Clamp(-FVector::DotProduct(Rel, RelV) / V2, 0.0, 22.0) : 0.0;
		const FVector AtCpa = Rel + RelV * Tc;               // where the other is from us at the closest approach
		const double Dmin = AtCpa.Size();
		if (Dmin < Reach)
		{
			const FVector Away = Dmin > 1.0 ? -AtCpa / Dmin : S.Att.GetRightVector();
			Push += Away * (double)S.CruiseSpeed * 0.7 * (1.0 - Dmin / Reach) * FMath::Clamp(1.0 - Tc / 30.0, 0.3, 1.0);
		}
	}
	for (const FAstraWreck& W : Wrecks)
	{
		if (W.Radius <= 0.f)
		{
			continue;                                           // debris is small
		}
		const FVector Rel = W.Pos - S.Pos;
		const double Reach = (S.Radius + W.Radius) * 1.5 + 200.0;
		const double D = Rel.Size();
		if (D < Reach + 4000.0)
		{
			const FVector RelV = W.Vel - S.Vel;
			const double V2 = RelV.SizeSquared();
			const double Tc = V2 > 1.0 ? FMath::Clamp(-FVector::DotProduct(Rel, RelV) / V2, 0.0, 22.0) : 0.0;
			const FVector AtCpa = Rel + RelV * Tc;
			const double Dmin = AtCpa.Size();
			if (Dmin < Reach)
			{
				const FVector Away = Dmin > 1.0 ? -AtCpa / Dmin : S.Att.GetRightVector();
				Push += Away * (double)S.CruiseSpeed * 0.7 * (1.0 - Dmin / Reach);
			}
		}
	}
	return Push.GetClampedToMaxSize((double)S.CruiseSpeed * 0.9);
}

// ---------------------------------------------------------------------------------------------- the mind
void UAstraBattleSubsystem::TickShipAI(FAstraBattleShip& S, float Dt)
{
	S.ThinkAcc += Dt;
	const float Period = 0.1f + S.Dmg.ThinkDelay;                 // a shot-up bridge thinks slowly
	if (S.ThinkAcc >= Period)
	{
		const float DtT = S.ThinkAcc;
		S.ThinkAcc = 0.f;
		ThinkShip(S, DtT);
	}
	// --- move: accelerate towards the wanted velocity, turn at a capital-ship rate (the engines' health sets both)
	const float Engines = EngineFactor(S);
	FVector Want = S.Steer;
	if (S.bHoldStation)
	{
		Want = FVector::ZeroVector;
		S.Vel = FVector::ZeroVector;
	}
	if (S.bHoldFire && !S.bFleeing)
	{
		Want = FVector::ZeroVector;                              // ceasefire: hold station, guns trained
	}
	S.Vel += (Want - S.Vel).GetClampedToMaxSize(S.MaxAccel * Engines * Dt);
	FVector Face = S.FaceWant;
	if (Face.IsNearlyZero())
	{
		Face = S.Vel.IsNearlyZero() ? S.Att.GetForwardVector() : S.Vel.GetSafeNormal();
	}
	if (Engines > 0.f && !S.bFixedAtt)
	{
		const FQuat Wanted = FRotationMatrix::MakeFromX(Face).ToQuat();
		const float MaxStep = FMath::DegreesToRadians(S.MaxTurnDeg * Engines * Dt);
		const float Ang = S.Att.AngularDistance(Wanted);
		S.Att = Ang <= MaxStep ? Wanted : FQuat::Slerp(S.Att, Wanted, MaxStep / Ang);
	}
	S.Pos += S.Vel * Dt;
}

/** The velocity that takes a ship to a point that moves with GoalVel and stops there: fast when far, braking so as not to
 *  overshoot (the ship can brake at only a fraction of its thrust). */
static FVector WarSeek(const FAstraBattleShip& S, const FVector& Goal, const FVector& GoalVel, float Engines)
{
	const FVector Rel = Goal - S.Pos;
	const double D = Rel.Size();
	if (D < 1.0)
	{
		return GoalVel;
	}
	const double A = FMath::Max(1.0, (double)S.MaxAccel * Engines * 0.55);
	const double V = FMath::Min((double)S.CruiseSpeed * 1.1, FMath::Sqrt(2.0 * A * D));
	return GoalVel + Rel / D * V;
}

void UAstraBattleSubsystem::ThinkShip(FAstraBattleShip& S, float DtT)
{
	const int32 Me = AstraSideIdx(S.Side);
	FAstraBattleGroup* G = FindGroup(S.GroupId);
	const float Engines = EngineFactor(S);
	if (S.bFleeing || S.Mode == EAstraShipMode::Evade)
	{
		ThinkWithdraw(S, G);
		return;
	}
	if (S.Mode == EAstraShipMode::Idle || S.bCold)
	{
		S.Steer = FVector::ZeroVector;
		return;
	}
	// --- who it shoots at
	FAstraBattleShip* T = FindById(S.TargetId);
	const bool bScripted = T && T->bAlive && T->Side == EAstraSide::Neutral && S.Side == EAstraSide::Mandate;   // the freighter of the opening
	if (T && !bScripted && (!CanEngage(S, *T)))
	{
		T = nullptr;
	}
	if (T && !T->bAlive)
	{
		T = nullptr;
	}
	if (!bScripted && ((S.RetargetT -= DtT) <= 0.f || !T))
	{
		S.RetargetT = 0.8f;
		T = ChooseTarget(S, G);
	}
	S.TargetId = T ? T->Id : -1;
	S.Mode = T ? EAstraShipMode::Attack : EAstraShipMode::Cruise;
	// --- a ship too hurt to fight breaks off (the group covers it)
	const float HullF = S.Hull / FMath::Max(1.f, S.HullMax);
	if (!S.bPlayer && HullF < 0.28f && Engines > 0.3f && !S.bFleeing && S.Side != EAstraSide::Neutral && (Me == 1 || G))
	{
		S.bFleeing = true;
		S.Mode = EAstraShipMode::Evade;
		Report(FString::Printf(TEXT("sensors: %s is badly damaged and breaking off, heading away from the fight"), *KnownLabel(S)));
		ThinkWithdraw(S, G);
		return;
	}
	const FVector KnownT = T ? KnownPos(Me, *T) : FVector::ZeroVector;
	const FVector ToT = KnownT - S.Pos;
	const double Dist = ToT.Size();
	const FVector Dir = T ? ToT / FMath::Max(1.0, Dist) : S.Att.GetForwardVector();
	// --- where it wants to be
	FVector Goal = S.Pos, GoalVel = FVector::ZeroVector;
	float Pref = S.RailRange > 0.f ? S.RailRange * 0.62f : 3000.f;
	if (G && G->EngageRange > 0.f)
	{
		Pref = G->EngageRange;
	}
	if (S.Stance == 1) { Pref = 1800.f; }
	else if (S.Stance == 2) { Pref = FMath::Clamp(S.RailRange * 0.9f, 5000.f, 9000.f); }
	const FVector Side = FVector::CrossProduct(Dir, FVector::UpVector).GetSafeNormal();
	if (S.Stance == 3 && T)
	{
		// the commander's flank: onto the target's weakest shield sector (or its beam), half the group each side
		FVector Weak = T->Att.GetRightVector() * ((S.Id % 2) ? 1.f : -1.f);
		if (T->Dmg.bModel && T->Dmg.Pool > 0.f)
		{
			float Lo = 2.f;
			int32 Face = -1;
			for (int32 f = 0; f < AstraWar::NumFacings; ++f)
			{
				const float Fr = T->Dmg.SectorMax[f] > 0.f ? T->Dmg.Sector[f] / T->Dmg.SectorMax[f] : 0.f;
				if (Fr < Lo)
				{
					Lo = Fr;
					Face = f;
				}
			}
			if (Face >= 0 && Lo < 0.6f)
			{
				Weak = T->Att.RotateVector(AstraWar::FacingVector(Face));
			}
		}
		Goal = KnownT + Weak * Pref;
		GoalVel = T->Vel;
	}
	else if (S.Stance == 4)
	{
		// cover the protectee: between it and the enemy (the fleet: the Aquila; the Mandate: their flagship)
		const FAstraBattleShip* Flag = Me == 0 ? &Ships[0] : FindByContact(MandateCommander());
		if (Flag && Flag != &S && Flag->bAlive && T)
		{
			const FVector Out = (KnownT - Flag->Pos).GetSafeNormal();
			Goal = Flag->Pos + Out * 2.2 * WarKm + FVector::CrossProduct(Out, FVector::UpVector).GetSafeNormal() * ((S.Id % 2) ? 0.9 : -0.9) * WarKm;
			GoalVel = Flag->Vel;
		}
		else if (T)
		{
			Goal = KnownT - Dir * Pref;
			GoalVel = T->Vel;
		}
	}
	else if (G && S.bTaskSet)
	{
		Goal = S.TaskPos;
		GoalVel = S.TaskVel;
		if (T && (S.Stance == 1 || S.Stance == 2) && G->EngageRange > 0.f)
		{
			Goal += Dir * ((double)G->EngageRange - Pref);          // its own range (close or standoff), the slot's frontage
		}
	}
	else if (T)
	{
		// alone: hold the preferred range, circling a little
		Goal = KnownT - Dir * Pref + Side * Pref * 0.35;
		GoalVel = T->Vel;
	}
	else if (G && G->bHasObjective)
	{
		Goal = G->Objective;
	}
	else
	{
		Goal = S.Pos;
		GoalVel = S.Vel * 0.f;
	}
	// --- steering: seek the goal, keep clear of the others
	FVector Steer = WarSeek(S, Goal, GoalVel, Engines);
	Steer += AvoidanceVel(S);
	S.Steer = Steer.GetClampedToMaxSize((double)S.CruiseSpeed * 1.25);
	// --- facing: the armament on the target, the strong face to the fire
	if (T && Dist < FMath::Max((double)S.RailRange, (double)S.MissileRange) * 1.05)
	{
		S.FaceWant = ChooseFacing(S, ToT, Dist);
	}
	else if (!S.Steer.IsNearlyZero())
	{
		S.FaceWant = S.Steer.GetSafeNormal();
	}
	else
	{
		S.FaceWant = FVector::ZeroVector;
	}
}

void UAstraBattleSubsystem::ThinkWithdraw(FAstraBattleShip& S, FAstraBattleGroup* G)
{
	const int32 Me = AstraSideIdx(S.Side);
	if (G && G->State == EAstraGroupState::Regroup)
	{
		// out of contact and reforming: hold at the rally point
		S.Steer = ((G->Rally - S.Pos) * 0.05).GetClampedToMaxSize(S.CruiseSpeed * 0.4);
		S.FaceWant = FVector::ZeroVector;
		return;
	}
	// away from the nearest enemy warship (or to the rally point the group chose)
	FVector Ref = S.Pos + S.Att.GetForwardVector() * 1000.0;
	double Nearest = 1e18;
	for (const FAstraBattleShip& O : Ships)
	{
		if (O.bAlive && !O.bCraft && !O.bDisabled && !O.bGhost && AstraSideIdx(O.Side) == 1 - Me && Me >= 0)
		{
			const double D = FVector::DistSquared(S.Pos, O.Pos);
			if (D < Nearest)
			{
				Nearest = D;
				Ref = O.Pos;
			}
		}
	}
	Nearest = FMath::Sqrt(Nearest);
	FVector Away = (S.Pos - Ref).GetSafeNormal();
	if (G && G->State == EAstraGroupState::Withdraw && !G->Rally.IsZero())
	{
		Away = (G->Rally - S.Pos).GetSafeNormal();
		if (FVector::DotProduct(Away, (S.Pos - Ref).GetSafeNormal()) < -0.2)
		{
			Away = (S.Pos - Ref).GetSafeNormal();                    // never through the enemy
		}
	}
	if (Away.IsNearlyZero())
	{
		Away = S.Att.GetForwardVector();
	}
	const float Speed = S.CruiseSpeed * (S.Task == EAstraTask::RearGuard ? 0.7f : 1.25f);
	S.Steer = (Away * Speed + AvoidanceVel(S)).GetClampedToMaxSize(S.CruiseSpeed * 1.3);
	S.FaceWant = FVector::ZeroVector;
	// a rear guard keeps its guns on the enemy while it backs off
	if (S.Task == EAstraTask::RearGuard)
	{
		S.FaceWant = -Away;
	}
	S.Mode = EAstraShipMode::Evade;
	if (S.Task == EAstraTask::RearGuard)
	{
		FAstraBattleShip* T = FindById(S.TargetId);
		if (!T || !CanEngage(S, *T))
		{
			T = ChooseTarget(S, G);
			S.TargetId = T ? T->Id : -1;
		}
	}
	// out of the theatre: far enough from every enemy that it can jump away
	if (Nearest > 100.0 * WarKm && S.bAlive)
	{
		const bool bWasCommander = S.Side == EAstraSide::Mandate && S.bHostile && MandateCommander() == S.ContactId;
		S.bAlive = false;
		if (S.Side != EAstraSide::Neutral && !S.bGhost)
		{
			++Stats.ShipFate[Me][(int32)EAstraFate::Withdrew];
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

// ---------------------------------------------------------------------------------------------- point defence
void UAstraBattleSubsystem::TickPointDefence(FAstraBattleShip& S)
{
	if (S.PDT > 0.f)
	{
		return;
	}
	int32 Channels = S.Dmg.bModel ? FMath::CeilToInt(S.PDChannels * S.Dmg.Sys[AstraWar::SysPointDefence]) : S.PDChannels;
	if (Channels <= 0)
	{
		return;
	}
	const int32 Me = AstraSideIdx(S.Side);
	const double Envelope = S.PDRange + S.Radius;
	// the missiles that are a danger to it or to what stands next to it, the closest to landing first (a torpedo before a missile)
	struct FCand { int32 Idx; float Score; };
	TArray<FCand, TInlineAllocator<24>> Cand;
	for (int32 i = 0; i < Projectiles.Num(); ++i)
	{
		const FAstraProjectile& Pr = Projectiles[i];
		if (Pr.bDead || Pr.Kind != EAstraProjKind::Missile || FVector::DistSquared(Pr.Pos, S.Pos) > Envelope * Envelope)
		{
			continue;
		}
		if (Pr.OwnerSide == Me && Me >= 0)
		{
			continue;                                                // ours
		}
		const FAstraBattleShip* Tg = FindById(Pr.Target);
		float Prio = 0.f;
		if (Pr.Target == S.Id)
		{
			Prio = 1.f;
		}
		else if (Tg && Tg->bAlive && AstraSideIdx(Tg->Side) == Me && !Tg->bCraft && FVector::DistSquared(Tg->Pos, S.Pos) < FMath::Square(1800.0))
		{
			Prio = 0.6f;                                             // a ship beside it: cover it
		}
		if (Prio <= 0.f)
		{
			continue;
		}
		const double ToGo = Tg ? FVector::Dist(Pr.Pos, Tg->Pos) : 1000.0;
		const float Tti = (float)FMath::Max(0.25, ToGo / FMath::Max(200.0, (double)Pr.Vel.Size()));
		Cand.Add({i, (Pr.bTorpedo ? 2.f : 1.f) * Prio / Tti});
	}
	if (Cand.Num() > 1)
	{
		Cand.Sort([](const FCand& A, const FCand& B) { return A.Score > B.Score; });
	}
	for (const FCand& C : Cand)
	{
		if (Channels <= 0)
		{
			break;
		}
		FAstraProjectile& Pr = Projectiles[C.Idx];
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
			if (Pr.OwnerSide >= 0 && Pr.OwnerSide < 2)
			{
				++Stats.MissilesShot[Pr.OwnerSide];
			}
			AddFlash(Pr.Pos, 25.f, 0.6f, FLinearColor(1.f, 0.7f, 0.35f), 60.f);
			if (S.bPlayer)
			{
				Report(TEXT("tactical: point defense splashed an incoming missile"), false);
			}
		}
	}
	// then the craft inside the envelope (the bombers first: they carry the torpedoes)
	if (Channels > 0 && Me >= 0)
	{
		struct FCraftCand { int32 Idx; float Score; };
		TArray<FCraftCand, TInlineAllocator<16>> Craft;
		const double CraftReach = 1500.0 + S.Radius;
		Grid.Query(S.Pos, CraftReach, [&](int32 J)
		{
			const FAstraBattleShip& C = Ships[J];
			if (C.bCraft && C.bAlive && AstraSideIdx(C.Side) == 1 - Me && FVector::DistSquared(C.Pos, S.Pos) < CraftReach * CraftReach)
			{
				Craft.Add({J, (C.CraftKind == 1 ? 2.f : 1.f) + (C.bPiloted ? 0.5f : 0.f) - (float)(FVector::Dist(C.Pos, S.Pos) / 5000.0)});
			}
		});
		Craft.Sort([](const FCraftCand& A, const FCraftCand& B) { return A.Score > B.Score; });
		for (const FCraftCand& K : Craft)
		{
			if (Channels <= 0)
			{
				break;
			}
			FAstraBattleShip& C = Ships[K.Idx];
			--Channels;
			S.PDT = 0.5f;
			AddBeam(S.Pos + (C.Pos - S.Pos).GetSafeNormal() * S.Radius * 0.6, C.Pos, 0.1f, FLinearColor(1.f, 0.6f, 0.3f));
			if (C.bPiloted)
			{
				if (FMath::FRand() < 0.22f)
				{
					ApplyHit(C, (C.Pos - S.Pos).GetSafeNormal(), 14.f, C.Pos, EAstraHitKind::PointDefence, S.Id);   // the Captain's Falcon: hurt, not erased
				}
			}
			else if (FMath::FRand() < (C.CraftKind == 0 ? 0.07f : (C.CraftKind == 1 ? 0.1f : 0.14f)))
			{
				ApplyHit(C, (C.Pos - S.Pos).GetSafeNormal(), 1000.f, C.Pos, EAstraHitKind::PointDefence, S.Id);
			}
		}
	}
}
