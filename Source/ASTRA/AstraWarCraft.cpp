// ASTRA — the craft's minds (docs/GUERRA.md, F2.2): carrier wings, squadrons, flights of two to four (a leader and wingmen),
// and the craft. A flight flies one mission (cap, escort, intercept, strike, ew, recon, sar, recall); the craft fly like
// aircraft (a heading that turns at a fighter's rate, a speed that changes at a fighter's thrust), never through the
// point-defence envelope of a ship that has any, never into a hull, and clear of one another. Both sides fly the same code
// on what their own sensors hold.
//
//   dogfight     lead pursuit at range, pure pursuit close in; a craft with an enemy on its tail breaks across his line;
//                one that has overshot extends and comes back; guns fire inside a cone, hits by range and angle;
//   attack run   a bomber runs in on the target's future position from outside its point defence, releases its torpedoes at
//                4 km, and egresses on a vector away; a fighter with rockets does the same from 4.5 km;
//   return       a craft that is hurt, or empty, goes home; a hangar that cannot take it leaves it circling.

#include "AstraBattleSubsystem.h"
#include "AstraWarClasses.h"
#include "AstraWarAI.h"
#include "ASTRA.h"
#include "AstraShipSubsystem.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMeshActor.h"
#include "Materials/MaterialInstanceDynamic.h"

namespace
{
	using AstraWar::WarKm;
	const float TorpedoRelease = 4000.f;
	const float RocketRelease = 4500.f;

	/** Where a craft's flight slot is, in the leader's frame: a loose finger-four (behind, to each side, a little apart). */
	FVector FlightSlot(int32 Slot)
	{
		const int32 Rank = (Slot + 1) / 2;
		return FVector(-95.0 * Rank, (Slot % 2 ? 1.0 : -1.0) * 115.0 * Rank, (Slot % 2 ? 12.0 : -12.0) * Rank);
	}

	FVector RotateAbout(const FVector& V, const FVector& Axis, double Deg)
	{
		return FQuat(Axis.GetSafeNormal(), FMath::DegreesToRadians(Deg)).RotateVector(V);
	}
}

// ---------------------------------------------------------------------------------------------- flights
void UAstraBattleSubsystem::AssignFlight(FAstraBattleShip& C, int32 Qi)
{
	const FAstraSquadron& Q = Squadrons[Qi];
	const int32 Size = Q.Kind == 1 ? 3 : 4;                       // bombers fly in threes, fighters and drones in fours
	int32 Alive = 0;
	FAstraFlight* Open = nullptr;
	for (FAstraFlight& F : Flights)
	{
		if (F.Squadron != Qi || Time - F.PhaseT > 25.f)
		{
			continue;                                               // an earlier sortie's, or one that is full and gone
		}
		Alive = 0;
		for (const int32 Id : F.Members)
		{
			const FAstraBattleShip* M = FindById(Id);
			Alive += (M && M->bAlive) ? 1 : 0;
		}
		if (Alive < Size)
		{
			Open = &F;
			break;
		}
	}
	if (!Open)
	{
		FAstraFlight F;
		F.Id = NextFlightId++;
		F.Squadron = Qi;
		F.Side = Q.Side;
		F.PhaseT = Time;                                            // formed now
		F.NextThink = Time;
		Flights.Add(F);
		Open = &Flights.Last();
	}
	Open->Members.Add(C.Id);
	if (Open->LeaderId < 0)
	{
		Open->LeaderId = C.Id;
	}
	C.FlightId = Open->Id;
	C.CraftSlot = Open->Members.Num() - 1;
	C.ThinkAcc = FMath::FRand() * 0.1f;
	// fighter dynamics: a heading that turns fast, a speed that changes briskly (the velocity follows the nose)
	C.MaxAccel = 200.f;
	C.MaxTurnDeg = Q.Kind == 1 ? 45.f : (Q.Kind == 2 ? 130.f : 100.f);
	C.Speed = C.Vel.Size();
}

FAstraFlight* UAstraBattleSubsystem::FindFlight(int32 Id)
{
	return Id < 0 ? nullptr : Flights.FindByPredicate([Id](const FAstraFlight& F) { return F.Id == Id; });
}

// ---------------------------------------------------------------------------------------------- the steering fields
/** What pushes a craft off its course: enemy ships' point-defence envelopes (any ship that has point defence), hulls, hulks,
 *  and the craft round it. A velocity, in m/s. */
FVector UAstraBattleSubsystem::CraftAvoidance(const FAstraBattleShip& S) const
{
	FVector Push = FVector::ZeroVector;
	const int32 Me = AstraSideIdx(S.Side);
	const double Fast = FMath::Max((double)S.CruiseSpeed, 300.0);
	const int32 HomeId = Squadrons.IsValidIndex(S.Squadron) ? Squadrons[S.Squadron].CarrierId : -1;
	for (const int32 Ei : CapIdx)
	{
		const FAstraBattleShip& E = Ships[Ei];
		if (E.Id == S.Id || E.Id == HomeId)
		{
			continue;                                               // (the ship it launches from and lands on is no obstacle)
		}
		const FVector Rel = S.Pos - E.Pos;
		const double D = Rel.Size();
		const bool bHostile = AstraSideIdx(E.Side) == 1 - Me && Me >= 0;
		// the envelope (its PD reach and its radius, with a margin): only ships with point defence that works have one
		double Env = 0.0;
		static AstraWar::FTuneVar KWall[2] = {AstraWar::FTuneVar(TEXT("wall_a"), 1.f), AstraWar::FTuneVar(TEXT("wall_m"), 1.f)};
		if (bHostile && Me >= 0 && KWall[Me].Get() > 0.5f && E.PDChannels > 0 && !E.bDisabled && (!E.Dmg.bModel || E.Dmg.Sys[AstraWar::SysPointDefence] > 0.15f))
		{
			Env = (E.PDRange + E.Radius) * 1.35 + 350.0;
		}
		const double Hull = E.Radius + 120.0 + Fast * 0.6;         // any hull: clear of it in time to turn
		const double Reach = FMath::Max(Env, Hull);
		if (D > Reach + 500.0)
		{
			continue;
		}
		const FVector Away = D > 1.0 ? Rel / D : S.Att.GetRightVector();
		if (D < Env)
		{
			Push += Away * Fast * 2.4 * FMath::Square(1.0 - D / Env);
		}
		if (D < Hull)
		{
			Push += Away * Fast * 1.6 * FMath::Square(1.0 - D / Hull);
		}
	}
	for (const int32 Wi : HulkIdx)
	{
		const FAstraWreck& W = Wrecks[Wi];
		if (Wrecks.IsValidIndex(Wi) && W.Radius > 0.f)
		{
			const FVector Rel = S.Pos - W.Pos;
			const double D = Rel.Size();
			const double Reach = W.Radius + 250.0 + Fast * 0.5;
			if (D < Reach)
			{
				Push += (D > 1.0 ? Rel / D : FVector::UpVector) * Fast * 1.8 * (1.0 - D / Reach);
			}
		}
	}
	// the craft around it: keep apart, and step out of a collision course (the closest approach within two seconds)
	Grid.Query(S.Pos, 500.0, [&](int32 J)
	{
		const FAstraBattleShip& O = Ships[J];
		if (O.Id == S.Id || !O.bCraft || !O.bAlive)
		{
			return;
		}
		const FVector Rel = O.Pos - S.Pos;
		const double D2 = Rel.SizeSquared();
		if (D2 > 500.0 * 500.0)
		{
			return;
		}
		const FVector RelV = O.Vel - S.Vel;
		const double V2 = RelV.SizeSquared();
		const double Tc = V2 > 1.0 ? FMath::Clamp(-FVector::DotProduct(Rel, RelV) / V2, 0.0, 2.0) : 0.0;
		const FVector AtCpa = Rel + RelV * Tc;
		const double Dmin = AtCpa.Size();
		const double Safe = 70.0;
		const bool bFriend = AstraSideIdx(O.Side) == Me;
		if (Dmin < Safe && bFriend)
		{
			const FVector Away = Dmin > 1.0 ? -AtCpa / Dmin : S.Att.GetRightVector();
			Push += Away * 300.0 * (1.0 - Dmin / Safe);
		}
	});
	return Push;
}

/** A velocity that flies a circle of Radius round a point that moves with CenterVel, at Speed, the way it is already going. */
static FVector WarOrbit(const FAstraBattleShip& S, const FVector& Centre, const FVector& CentreVel, double Radius, double Speed, double Lift)
{
	FVector Rel = S.Pos - Centre;
	Rel.Z -= Lift;
	const double D = Rel.Size();
	FVector Radial = D > 1.0 ? Rel / D : FVector::ForwardVector;
	FVector Tangent = FVector::CrossProduct(FVector::UpVector, Radial).GetSafeNormal();
	if (FVector::DotProduct(Tangent, S.Vel) < 0.0)
	{
		Tangent = -Tangent;                                         // the way it is already going round
	}
	const double Err = FMath::Clamp((Radius - D) / Radius, -1.0, 1.0);
	return CentreVel + (Tangent + Radial * Err * 1.2).GetSafeNormal() * Speed;
}

/** The point-defence envelope is a wall: a craft may slide along it, never cross it (a soft push alone is beaten by a
 *  wanted velocity towards the ship). The wall stands a turning radius outside the reach of the guns. */
FVector UAstraBattleSubsystem::EnvelopeWall(const FAstraBattleShip& S, const FVector& Steer) const
{
	static AstraWar::FTuneVar KWall[2] = {AstraWar::FTuneVar(TEXT("wall_a"), 1.f), AstraWar::FTuneVar(TEXT("wall_m"), 1.f)};   // (the bench's A/B)
	const int32 Me = AstraSideIdx(S.Side);
	if (Me < 0 || KWall[Me].Get() < 0.5f)
	{
		return Steer;
	}
	FVector V = Steer;
	const double Turn = FMath::Max(300.0, (double)S.CruiseSpeed / FMath::DegreesToRadians(FMath::Max(30.f, S.MaxTurnDeg)));   // its turning radius
	for (const int32 Ei : CapIdx)
	{
		const FAstraBattleShip& E = Ships[Ei];
		if (AstraSideIdx(E.Side) != 1 - Me || E.PDChannels <= 0 || E.bDisabled)
		{
			continue;
		}
		if (E.Dmg.bModel && E.Dmg.Sys[AstraWar::SysPointDefence] <= 0.15f)
		{
			continue;
		}
		const FVector Rel = S.Pos - E.Pos;
		const double D = Rel.Size();
		const double Wall = (double)E.PDRange + E.Radius + 0.75 * Turn + 250.0;
		if (D < Wall && D > 1.0)
		{
			const FVector Out = Rel / D;
			const double In = FVector::DotProduct(V, Out);
			if (In < 0.0)
			{
				V -= Out * In;                                     // no velocity into the wall: it slides along it
			}
			V += Out * FMath::Min(400.0, (Wall - D) * 1.5);          // and is eased out of it
		}
	}
	return V;
}

// ---------------------------------------------------------------------------------------------- the craft
void UAstraBattleSubsystem::TickCraft(FAstraBattleShip& S, float Dt)
{
	if (S.Squadron < 0 || !Squadrons.IsValidIndex(S.Squadron))
	{
		S.bAlive = false;
		return;
	}
	S.ThinkAcc += Dt;
	if (S.ThinkAcc >= 0.1f)
	{
		const float DtT = S.ThinkAcc;
		S.ThinkAcc = 0.f;
		ThinkCraft(S, DtT);
		if (!S.bAlive)
		{
			return;
		}
	}
	// --- fly: the heading turns at the airframe's rate towards the wanted direction, the speed changes at its thrust, the
	// velocity follows the nose
	const FVector Want = EnvelopeWall(S, S.Steer);
	const double WantSpeed = FMath::Clamp((double)Want.Size(), 90.0, (double)S.CruiseSpeed * 1.1);
	const FVector WantDir = Want.IsNearlyZero() ? S.Att.GetForwardVector() : Want.GetSafeNormal();
	const FQuat Wanted = FRotationMatrix::MakeFromX(WantDir).ToQuat();
	const float MaxStep = FMath::DegreesToRadians(S.MaxTurnDeg * (S.CraftState == 1 ? 1.15f : 1.f) * Dt);
	const float Ang = S.Att.AngularDistance(Wanted);
	S.Att = Ang <= MaxStep ? Wanted : FQuat::Slerp(S.Att, Wanted, MaxStep / Ang);
	S.Speed += (float)FMath::Clamp(WantSpeed - S.Speed, -(double)S.MaxAccel * Dt, (double)S.MaxAccel * Dt);
	S.Vel = S.Att.GetForwardVector() * S.Speed;
	S.Pos += S.Vel * Dt;
	FireCraft(S, Dt);
}

void UAstraBattleSubsystem::LandCraft(FAstraBattleShip& S, FAstraBattleShip& Carrier, FAstraSquadron& Q)
{
	S.bAlive = false;
	if (S.Actor) { S.Actor->Destroy(); S.Actor = nullptr; }
	if (S.DriveFlare) { S.DriveFlare->Destroy(); S.DriveFlare = nullptr; }
	if (const int32 Side = AstraSideIdx(S.Side); Side >= 0)
	{
		++Stats.CraftRecovered[Side];
	}
	if (Q.Side == EAstraSide::Astra)
	{
		++Q.OnDeck;
		if (AirborneCount(S.Squadron) == 0)
		{
			Q.RearmT = Q.Kind == 1 ? 120.f : 60.f;
			Q.Mission = TEXT("recall");
			Report(FString::Printf(TEXT("flight: %s squadron recovered, %d of %d %ss aboard, rearming (%.0f s)"), *Q.Name, Q.OnDeck, Q.Total, *Q.CallSign, Q.RearmT));
		}
	}
	else
	{
		++Q.OnDeck;                                                 // (the Mandate's wings simply come home)
	}
	(void)Carrier;
}

void UAstraBattleSubsystem::ThinkCraft(FAstraBattleShip& S, float DtT)
{
	FAstraSquadron& Q = Squadrons[S.Squadron];
	const int32 Me = AstraSideIdx(S.Side);
	FAstraBattleShip* Home = FindById(Q.CarrierId);
	const bool bHomeAlive = Home && Home->bAlive;
	FAstraBattleShip& Carrier = bHomeAlive ? *Home : Ships[0];
	FAstraFlight* F = FindFlight(S.FlightId);
	FAstraBattleShip* Leader = F ? FindById(F->LeaderId) : nullptr;
	if (F && (!Leader || !Leader->bAlive))
	{
		// the leader is down: the next member takes the lead
		F->LeaderId = -1;
		for (const int32 Id : F->Members)
		{
			const FAstraBattleShip* M = FindById(Id);
			if (M && M->bAlive)
			{
				F->LeaderId = Id;
				break;
			}
		}
		Leader = FindById(F->LeaderId);
	}
	const bool bLeader = !F || !Leader || Leader->Id == S.Id;
	S.StateT -= DtT;
	S.GunHeat = FMath::Max(0.f, S.GunHeat - DtT);
	FString& M = S.Mission;
	// --- the target of the mission, if it lives
	FAstraBattleShip* T = FindById(S.MissionTarget);
	if (T && !T->bAlive)
	{
		T = nullptr;
	}
	if (Q.bAuto && M == TEXT("strike") && (!T || T->bCraft || !Knows(Me, *T)))
	{
		// a wing with no crew to give it targets picks its own: the enemy warship it holds that is worth most and nearest its carrier
		T = nullptr;
		double Best = 1e18;
		for (FAstraBattleShip& O : Ships)
		{
			if (O.bAlive && !O.bCraft && !O.bDisabled && AstraSideIdx(O.Side) == 1 - Me && Knows(Me, O))
			{
				const double Score = FVector::Dist(O.Pos, Carrier.Pos) / (0.5 + 0.5 * O.CombatValue);
				if (Score < Best)
				{
					Best = Score;
					T = &O;
				}
			}
		}
		S.MissionTarget = T ? T->Id : -1;
		if (!T)
		{
			M = TEXT("cap");                                        // nothing to strike yet: cover the carrier
		}
	}
	else if (!T && (M == TEXT("strike") || M == TEXT("escort") || M == TEXT("ew")))
	{
		M = Q.bAuto ? FString(TEXT("cap")) : FString(TEXT("recall"));   // the target is gone: come home (a self-tasked wing guards its carrier)
	}
	// --- hurt or empty: home
	const bool bHurt = S.Hull < 0.4f * S.HullMax;
	const bool bEmptyBomber = S.CraftKind == 1 && S.Torpedoes <= 0 && M == TEXT("strike");
	const bool bSpent = S.Side == EAstraSide::Mandate && S.CraftKind == 0 && S.Missiles <= 0 && M == TEXT("strike")
	                 && T && T->PDChannels > 0 && !T->bDisabled;         // rockets gone, and the target's guns would eat a fighter
	if ((bHurt || bEmptyBomber || bSpent) && M != TEXT("recall") && M != TEXT("sar"))
	{
		M = TEXT("recall");
	}
	if (bMandateStandDown() && S.Side == EAstraSide::Mandate)
	{
		M = TEXT("recall");                                         // their commander holds fire: the wing stands down
	}
	// --- the bandits: enemy craft it knows within reach of what it guards (the Captain's Falcon draws two Harpies)
	auto NearestBandit = [&](const FVector& Around, double Reach, bool bAny) -> FAstraBattleShip*
	{
		FAstraBattleShip* Best = nullptr;
		double BestD = Reach * Reach;
		Grid.Query(Around, Reach, [&](int32 J)
		{
			FAstraBattleShip& O = Ships[J];
			if (!O.bCraft || !O.bAlive || AstraSideIdx(O.Side) != 1 - Me)
			{
				return;
			}
			if (!bAny && !Knows(Me, O))
			{
				return;
			}
			const double D = FVector::DistSquared(O.Pos, Around);
			if (D < BestD)
			{
				BestD = D;
				Best = &O;
			}
		});
		return Best;
	};
	FVector Goal = S.Pos + S.Att.GetForwardVector() * 1000.0;
	FVector GoalVel = FVector::ZeroVector;
	double Speed = S.CruiseSpeed;
	S.CraftTarget = -1;
	// --- a defensive turn or an extension in progress overrides the mission
	if (S.CraftState == 1 && S.StateT > 0.f)
	{
		S.Steer = (S.BreakDir * S.CruiseSpeed + CraftAvoidance(S)).GetClampedToMaxSize(S.CruiseSpeed * 1.1);
		return;
	}
	if (S.CraftState == 2 && S.StateT > 0.f)
	{
		S.Steer = (S.Att.GetForwardVector() * S.CruiseSpeed + CraftAvoidance(S) + S.BreakDir * 200.0).GetClampedToMaxSize(S.CruiseSpeed * 1.1);
		return;
	}
	S.CraftState = 0;
	// --- the mission
	FAstraBattleShip* Bandit = nullptr;
	auto DogfightVel = [&](FAstraBattleShip& B) -> FVector
	{
		const FVector Rel = B.Pos - S.Pos;
		const double D = Rel.Size();
		const FVector Dir = Rel / FMath::Max(1.0, D);
		const FVector Fwd = S.Att.GetForwardVector();
		const double Aim = FVector::DotProduct(Fwd, Dir);                                   // 1: it is on my nose
		const double OnMe = FVector::DotProduct(B.Att.GetForwardVector(), -Dir);            // 1: it points at me
		// an enemy on my tail and close: break across his line
		if (OnMe > 0.86 && D < 1100.0 && Aim < 0.5 && S.CraftState != 1)
		{
			const FVector Across = FVector::CrossProduct(B.Att.GetForwardVector(), FVector::UpVector).GetSafeNormal();
			S.BreakDir = ((FVector::DotProduct(Across, -Dir) > 0.0 ? Across : -Across) + FVector::UpVector * FMath::FRandRange(-0.6f, 0.6f)).GetSafeNormal();
			S.CraftState = 1;
			S.StateT = FMath::FRandRange(0.9f, 1.7f);
			return S.BreakDir * S.CruiseSpeed;
		}
		// overshot: extend straight, then come back
		if (D < 220.0 && Aim > 0.9 && (S.Vel - B.Vel).Size() > 250.0)
		{
			S.CraftState = 2;
			S.StateT = FMath::FRandRange(1.1f, 1.8f);
			S.BreakDir = (S.Pos - B.Pos).GetSafeNormal();
			return Fwd * S.CruiseSpeed;
		}
		const double Lead = D > 500.0 ? FMath::Clamp(D / FMath::Max(300.0, (double)S.Speed + 1.0), 0.0, 1.6) : 0.0;   // lead pursuit far out, pure pursuit close
		const FVector Aimpoint = B.Pos + B.Vel * Lead - (D < 450.0 ? Dir * 60.0 : FVector::ZeroVector);
		const double Sp = FMath::Clamp(B.Vel.Size() * 1.05 + (D - 350.0) * 0.4, S.CruiseSpeed * 0.55, (double)S.CruiseSpeed);
		return (Aimpoint - S.Pos).GetSafeNormal() * Sp;
	};
	if (M == TEXT("recall"))
	{
		const FVector Tail = Carrier.Pos + Carrier.Att.RotateVector(FVector(-60.0, 0.0, -30.0));
		const double D = FVector::Dist(S.Pos, Tail);
		if (D < 400.0 && bHomeAlive && HangarFactor(Carrier) > 0.2f)
		{
			LandCraft(S, Carrier, Q);                               // trapped aboard
			return;
		}
		if (!bHomeAlive && FVector::Dist(S.Pos, S.Side == EAstraSide::Astra ? Ships[0].Pos : Carrier.Pos) > 80.0 * WarKm)
		{
			S.bAlive = false;                                       // no carrier and far from anything: it is gone
			if (S.Actor) { S.Actor->Destroy(); S.Actor = nullptr; }
			if (S.DriveFlare) { S.DriveFlare->Destroy(); S.DriveFlare = nullptr; }
			return;
		}
		Goal = bHomeAlive ? Tail : S.Pos + (S.Pos - Carrier.Pos).GetSafeNormal() * 20000.0;
		GoalVel = bHomeAlive ? Carrier.Vel : FVector::ZeroVector;
		Speed = bHomeAlive ? FMath::Min((double)S.CruiseSpeed, Carrier.Vel.Size() + FMath::Min(260.0, D * 0.5) + 60.0) : S.CruiseSpeed;
		if (bHomeAlive && HangarFactor(Carrier) <= 0.2f)
		{
			// nowhere to land: it circles the carrier
			S.Steer = (WarOrbit(S, Carrier.Pos, Carrier.Vel, Carrier.Radius + 2500.0, 500.0, 0.0) + CraftAvoidance(S)).GetClampedToMaxSize(S.CruiseSpeed * 1.1);
			return;
		}
	}
	else if (M == TEXT("cap") || M == TEXT("escort") || M == TEXT("intercept"))
	{
		const FAstraBattleShip& Guard = (M == TEXT("escort") && T) ? *T : Carrier;
		const FVector GuardPos = Guard.Pos;
		const double Reach = M == TEXT("intercept") ? 30.0 * WarKm : 7.0 * WarKm;
		// the Captain's Falcon near the Harpies: the two nearest hunt it
		FAstraBattleShip* Eagle = (S.Side == EAstraSide::Mandate && PilotedId >= 0) ? FindById(PilotedId) : nullptr;
		if (Eagle && Eagle->bAlive && !bMandateStandDown() && FVector::Dist(Eagle->Pos, S.Pos) < 5.0 * WarKm)
		{
			int32 Closer = 0;
			for (const FAstraBattleShip& O : Ships)
			{
				Closer += (O.bAlive && O.bCraft && O.Side == EAstraSide::Mandate && O.Id != S.Id && FVector::Dist(O.Pos, Eagle->Pos) < FVector::Dist(S.Pos, Eagle->Pos)) ? 1 : 0;
			}
			if (Closer < 2)
			{
				Bandit = Eagle;
			}
		}
		if (!Bandit)
		{
			// the flight's claimed bandit while it lives, else the nearest to the guard (bombers first: they carry the torpedoes)
			if (F && F->Bandit >= 0)
			{
				Bandit = FindById(F->Bandit);
				if (Bandit && (!Bandit->bAlive || !Knows(Me, *Bandit) || FVector::Dist(Bandit->Pos, GuardPos) > Reach * 1.5))
				{
					Bandit = nullptr;
					F->Bandit = -1;
				}
			}
			if (!Bandit && S.CraftKind != 1)
			{
				Bandit = NearestBandit(GuardPos, Reach, false);
				if (F && bLeader && Bandit)
				{
					F->Bandit = Bandit->Id;
				}
			}
		}
		if (Bandit && S.CraftKind != 1)
		{
			S.CraftTarget = Bandit->Id;
			const FVector V = DogfightVel(*Bandit);
			S.Steer = (V + CraftAvoidance(S)).GetClampedToMaxSize(S.CruiseSpeed * 1.1);
			return;
		}
		// nobody to fight: hold the patrol on the guard (a wingman keeps his place in the flight)
		if (F && Leader && !bLeader && S.CraftKind != 1)
		{
			const FVector SlotPos = Leader->Pos + Leader->Att.RotateVector(FlightSlot(S.CraftSlot));
			S.Steer = (Leader->Vel + (SlotPos - S.Pos) * 1.1 + CraftAvoidance(S)).GetClampedToMaxSize(S.CruiseSpeed * 1.05);
			return;
		}
		Goal = GuardPos;
		GoalVel = Guard.Vel;
		S.Steer = (WarOrbit(S, GuardPos, Guard.Vel, Guard.Radius + 2200.0 + 350.0 * (F ? (F->Id % 3) : 0), S.CruiseSpeed * 0.6, 200.0 * FMath::Sin(Time * 0.2 + S.OrbitPhase))
		           + CraftAvoidance(S)).GetClampedToMaxSize(S.CruiseSpeed * 1.05);
		return;
	}
	else if (M == TEXT("strike") && T)
	{
		const FVector ToT = T->Pos - S.Pos;
		const double D = ToT.Size();
		const FVector Dir = ToT / FMath::Max(1.0, D);
		const bool bDefended = T->PDChannels > 0 && !T->bDisabled && (!T->Dmg.bModel || T->Dmg.Sys[AstraWar::SysPointDefence] > 0.15f);
		if (S.CraftKind == 1 && S.Torpedoes > 0)
		{
			// the torpedo run: in on the target's future position from outside its point defence, release at 4 km
			const double Tof = FMath::Max(D, 1.0) / 900.0;
			Goal = T->Pos + T->Vel * FMath::Min(Tof, 6.0) + RotateAbout(-Dir, FVector::UpVector, (S.CraftSlot % 3 - 1) * 9.0) * 0.0;
			S.CraftState = 3;
			S.CraftTarget = T->Id;
			Speed = S.CruiseSpeed;
			if (D < TorpedoRelease && FVector::DotProduct(S.Att.GetForwardVector(), Dir) > 0.94)
			{
				for (int32 k = 0; k < S.Torpedoes; ++k)
				{
					FireTorpedo(S, *T);
				}
				Q.TorpedoesAway += S.Torpedoes;
				Q.TorpedoTarget = KnownLabel(*T);
				if (Q.TorpedoReportAt < 0.f)
				{
					Q.TorpedoReportAt = Time + 6.f;                 // the rest of the group releases within seconds: one report for the run
				}
				S.Torpedoes = 0;
				S.CraftState = 4;                                   // egress: away, then home
				S.StateT = 6.f;
				S.BreakDir = (-Dir + FVector::UpVector * 0.25 + S.Att.GetRightVector() * FMath::FRandRange(-0.5f, 0.5f)).GetSafeNormal();
				M = TEXT("recall");
			}
		}
		else if (S.Missiles > 0 && S.Side == EAstraSide::Mandate)
		{
			// a strike fighter's rocket run: close to 4.5 km, fire them, break away; the guns are for craft
			Goal = T->Pos + T->Vel * 2.0;
			S.CraftTarget = T->Id;
			Speed = S.CruiseSpeed;
		}
		else if (!bDefended)
		{
			// a ship with no point defence left can be strafed (a freighter, a wreck of a ship): a pass at a kilometre
			Goal = T->Pos + FVector(FMath::Cos(Time * 1.4 + S.OrbitPhase), FMath::Sin(Time * 1.4 + S.OrbitPhase), 0.3) * (T->Radius + 900.0);
			S.CraftTarget = T->Id;
			Speed = S.CruiseSpeed;
		}
		else
		{
			// its point defence would eat a fighter: cover the run instead (hold off its envelope, fight what comes at it)
			Bandit = NearestBandit(T->Pos, 9.0 * WarKm, false);
			if (Bandit && S.CraftKind != 1)
			{
				S.CraftTarget = Bandit->Id;
				S.Steer = (DogfightVel(*Bandit) + CraftAvoidance(S)).GetClampedToMaxSize(S.CruiseSpeed * 1.1);
				return;
			}
			const FVector Hold = T->Pos - Dir * ((double)T->PDRange + T->Radius + 3500.0);
			S.Steer = (WarOrbit(S, Hold, T->Vel, 1800.0, S.CruiseSpeed * 0.6, 0.0) + CraftAvoidance(S)).GetClampedToMaxSize(S.CruiseSpeed * 1.05);
			return;
		}
	}
	else if (M == TEXT("ew") && T)
	{
		S.Steer = (WarOrbit(S, T->Pos, T->Vel, 5000.0, S.CruiseSpeed * 0.6, 0.0) + CraftAvoidance(S)).GetClampedToMaxSize(S.CruiseSpeed * 1.05);
		if (FVector::Dist(S.Pos, T->Pos) < 7000.0)
		{
			T->bJammed = true;
		}
		return;
	}
	else if (M == TEXT("recon"))
	{
		if (!T)
		{
			// the nearest contact nobody has identified yet
			double Best = 1e18;
			for (FAstraBattleShip& O : Ships)
			{
				if (O.bAlive && !O.bCraft && !O.bPlayer && !O.bIdentified && (!O.bFog || O.Track > 0) && FVector::DistSquared(O.Pos, S.Pos) < Best)
				{
					Best = FVector::DistSquared(O.Pos, S.Pos);
					T = &O;
				}
			}
			S.MissionTarget = T ? T->Id : -1;
		}
		if (T)
		{
			Goal = T->Pos + (S.Pos - T->Pos).GetSafeNormal() * (T->bDerelict ? 700.0 : 6000.0);   // a derelict is looked at up close
			GoalVel = T->Vel;
			if (!T->bIdentified && !T->bGhost && FVector::Dist(S.Pos, T->Pos) < 9000.0)
			{
				T->bIdentified = T->bClassified = true;
				T->Track = 2;
				Report(FString::Printf(TEXT("flight: %s recon has identified %s: %s, %s"), *Q.CallSign, *T->ContactId, *T->Class, *T->Name));
			}
		}
		else
		{
			Goal = Carrier.Pos + Carrier.Att.GetForwardVector() * 9000.0 + FVector(FMath::Cos(Time * 0.22 + S.OrbitPhase), FMath::Sin(Time * 0.22 + S.OrbitPhase), 0.f) * 2000.0;
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
	else
	{
		Goal = Carrier.Pos + Carrier.Att.GetForwardVector() * 3000.0;               // hold: stay with the carrier
		GoalVel = Carrier.Vel;
	}
	// --- steer to the goal: the direction, the speed (slow when close, matching the goal's motion), what keeps it clear
	if (S.CraftState == 4 && S.StateT > 0.f)
	{
		S.Steer = (S.BreakDir * S.CruiseSpeed + CraftAvoidance(S)).GetClampedToMaxSize(S.CruiseSpeed * 1.1);   // egress
		return;
	}
	const FVector ToGoal = Goal - S.Pos;
	const double L = ToGoal.Size();
	const FVector V = GoalVel + ToGoal / FMath::Max(L, 1.0) * FMath::Min(Speed, L * 0.8 + 90.0);
	S.Steer = (V + CraftAvoidance(S)).GetClampedToMaxSize(S.CruiseSpeed * 1.1);
}

// ---------------------------------------------------------------------------------------------- guns and rockets
void UAstraBattleSubsystem::FireCraft(FAstraBattleShip& S, float Dt)
{
	if (S.GunHeat > 0.f || S.bPiloted)
	{
		return;
	}
	const int32 Me = AstraSideIdx(S.Side);
	const FVector Fwd = S.Att.GetForwardVector();
	if (S.CraftTarget >= 0)
	{
		FAstraBattleShip* B = FindById(S.CraftTarget);
		if (B && B->bAlive)
		{
			const FVector Rel = B->Pos - S.Pos;
			const double D = Rel.Size();
			const FVector Dir = Rel / FMath::Max(1.0, D);
			const double Cone = FVector::DotProduct(Fwd, Dir);
			if (B->bCraft)
			{
				// guns: inside a cone and range, the hit by range and by how true the nose points (the lead is in the aim)
				const FVector LeadDir = ((B->Pos + B->Vel * 0.25) - S.Pos).GetSafeNormal();
				const double C2 = FVector::DotProduct(Fwd, LeadDir);
				if (D < 950.0 && C2 > 0.985)
				{
					S.GunHeat = 0.25f;
					const float Pk = (float)(0.55 * FMath::Pow(1.0 - D / 950.0, 0.8) * FMath::Clamp((C2 - 0.985) / 0.014, 0.0, 1.0) + 0.05);
					AddBeam(S.Pos, S.Pos + LeadDir * FMath::Min(D, 950.0), 0.06f, S.Side == EAstraSide::Mandate ? FLinearColor(1.f, 0.55f, 0.3f) : FLinearColor(0.6f, 0.85f, 1.f));
					if (FMath::FRand() < Pk)
					{
						ApplyHit(*B, Dir, B->bPiloted ? 7.f : 22.f, B->Pos, EAstraHitKind::Cannon, S.Id);
					}
				}
				else if (S.Missiles > 0 && S.Side == EAstraSide::Mandate && B->bPiloted && D > 1200.0 && D < 3500.0 && Cone > 0.8)
				{
					// a rocket at the Captain's Falcon
					S.GunHeat = 4.f;
					--S.Missiles;
					FireMissile(S, *B);
					FAstraProjectile& R = Projectiles.Last();
					R.HitKind = EAstraHitKind::Rocket;
					R.Damage = 40.f;
					R.MaxSpeed = 1250.f;
					if (R.Actor) { R.Actor->SetActorScale3D(FVector(3.f)); }
				}
			}
			else
			{
				const bool bDefended = B->PDChannels > 0 && !B->bDisabled && (!B->Dmg.bModel || B->Dmg.Sys[AstraWar::SysPointDefence] > 0.15f);
				if (S.Missiles > 0 && D > 2600.0 && D < (double)RocketRelease && Cone > 0.9)
				{
					// a rocket from outside its point defence
					S.GunHeat = 0.8f;
					--S.Missiles;
					FireMissile(S, *B);
					FAstraProjectile& R = Projectiles.Last();
					R.HitKind = EAstraHitKind::Rocket;
					R.Damage = 45.f;
					R.MaxSpeed = 1300.f;
					if (R.Actor) { R.Actor->SetActorScale3D(FVector(4.f)); }
					if (B->bPlayer)
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
				else if (!bDefended && S.Missiles <= 0 && D < 1500.0 && Cone > 0.95)
				{
					S.GunHeat = 0.5f;
					AddBeam(S.Pos, B->Pos - Dir * B->Radius, 0.08f, FLinearColor(0.6f, 0.85f, 1.f));
					ApplyHit(*B, Dir, S.CraftKind == 2 ? 1.f : 3.f, B->Pos - Dir * B->Radius, EAstraHitKind::Cannon, S.Id);
				}
			}
			return;
		}
	}
	// no craft in the sights: the missiles at what it guards (a fighter's guns can splash them)
	if (S.CraftKind != 1 && (S.Mission == TEXT("cap") || S.Mission == TEXT("escort") || S.Mission == TEXT("intercept")))
	{
		FAstraProjectile* Best = nullptr;
		double BestD = 700.0 * 700.0;
		for (FAstraProjectile& Pr : Projectiles)
		{
			if (Pr.bDead || Pr.Kind != EAstraProjKind::Missile || Pr.OwnerSide == Me || Pr.OwnerSide < 0)
			{
				continue;
			}
			const double D2 = FVector::DistSquared(Pr.Pos, S.Pos);
			if (D2 < BestD && FVector::DotProduct(Fwd, (Pr.Pos - S.Pos).GetSafeNormal()) > 0.9)
			{
				BestD = D2;
				Best = &Pr;
			}
		}
		if (Best)
		{
			S.GunHeat = 0.4f;
			AddBeam(S.Pos, Best->Pos, 0.08f, FLinearColor(0.6f, 0.85f, 1.f));
			if (FMath::FRand() < (S.CraftKind == 0 ? 0.35f : 0.15f))
			{
				Best->bDead = true;
				if (Best->OwnerSide >= 0 && Best->OwnerSide < 2)
				{
					++Stats.MissilesShot[Best->OwnerSide];
				}
				AddFlash(Best->Pos, 20.f, 0.5f, FLinearColor(1.f, 0.7f, 0.35f), 50.f);
			}
		}
	}
	(void)Dt;
}
