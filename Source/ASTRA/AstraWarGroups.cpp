// ASTRA — the battle group's mind (docs/GUERRA.md, F2.2): what a handful of warships do together.
//
//   FORMATION   a guide point ahead of the group leads it to the range its armament likes (the DPS of both sides at each
//               range decides); each ship keeps its slot in the guide's frame: a line abreast, a wedge, a column, or a
//               screen on an arc between the enemy and the ship it protects;
//   TARGETS     one focus of fire chosen by value, vulnerability and reach, held until it falls or a much better one
//               appears; ships that cannot reach it shoot the nearest;
//   FLANKS      one or two agile, healthy ships swing round the enemy to its blind arc (the quarter its guns cover least);
//   ROTATION    the ships that have taken the most fall back behind the line to recover, and the fresh ones take their place;
//   MISSILES    the cells are kept until enough are ready to saturate the target's point defence, then launched all
//               together, timed to land at the same moment;
//   MORALE      the balance of strength, sustained, breaks the group: it withdraws in order (a rear guard covers the
//               weak), reforms out of contact, and goes back in if it is strong enough. The orders of the minds (attack,
//               pin, flank, screen, withdraw, regroup, reinforce, hold) override its own judgement until they lapse.
// Both sides use the same code, each on what its own sensors hold (AstraWarKnowledge.cpp).

#include "AstraBattleSubsystem.h"
#include "AstraWarClasses.h"
#include "AstraWarAI.h"
#include "ASTRA.h"
#include "AstraShipSubsystem.h"

namespace
{
	const double WarKm = 1000.0;

	float TargetValue(const FAstraBattleShip& E)
	{
		static const FName Aquila(TEXT("aquila")), Praetorian(TEXT("praetorian")), Acheron(TEXT("acheron")), Vigilant(TEXT("vigilant")), Styx(TEXT("styx")),
		                   Lethe(TEXT("lethe")), Freighter(TEXT("freighter"));
		const FName K = E.ClassKey;
		float V = E.bPlayer ? 1.9f : (K == Aquila ? 1.7f : (K == Praetorian ? 1.3f : (K == Acheron ? 1.25f : ((K == Vigilant || K == Styx) ? 0.85f
		        : (K == Lethe ? 0.7f : (K == Freighter ? 0.15f : 1.0f))))));
		if (E.bLeader)
		{
			V *= 1.15f;
		}
		return V;
	}

	FVector HorizontalRight(const FVector& Axis)
	{
		FVector R = FVector::CrossProduct(Axis, FVector::UpVector);
		if (R.SizeSquared() < 1e-4)
		{
			R = FVector::CrossProduct(Axis, FVector::ForwardVector);
		}
		return R.GetSafeNormal();
	}

	FVector RotateAboutUp(const FVector& V, double Deg)
	{
		return FQuat(FVector::UpVector, FMath::DegreesToRadians(Deg)).RotateVector(V);
	}
}

// ---------------------------------------------------------------------------------------------- membership
int32 UAstraBattleSubsystem::NewGroup(EAstraSide Side, const FString& Name, EAstraFormation Formation)
{
	FAstraBattleGroup G;
	G.Id = NextGroupId++;
	G.Side = Side;
	G.Name = Name;
	G.Formation = Formation;
	G.NextThink = Time + FMath::FRandRange(0.f, 0.5f);
	Groups.Add(G);
	return G.Id;
}

void UAstraBattleSubsystem::JoinGroup(FAstraBattleShip& S, int32 GroupId)
{
	FAstraBattleGroup* G = FindGroup(GroupId);
	if (!G)
	{
		return;
	}
	if (FAstraBattleGroup* Old = FindGroup(S.GroupId); Old && Old != G)
	{
		Old->Members.Remove(S.Id);
	}
	S.GroupId = G->Id;
	G->Members.AddUnique(S.Id);
	G->StartCount = FMath::Max(G->StartCount, G->Members.Num());
	if (G->LeaderId < 0 || !FindById(G->LeaderId) || !FindById(G->LeaderId)->bAlive)
	{
		G->LeaderId = S.Id;
	}
}

int32 UAstraBattleSubsystem::NoteGroupSpawn(EAstraSide Side, const FString& Name, const FString& Formation, const TArray<int32>& ShipIdx, int32 ProtecteeId)
{
	if (ShipIdx.Num() == 0)
	{
		return INDEX_NONE;
	}
	const EAstraFormation F = Formation == TEXT("wedge") ? EAstraFormation::Wedge : (Formation == TEXT("column") ? EAstraFormation::Column
	                        : (Formation == TEXT("screen") ? EAstraFormation::Screen : EAstraFormation::Line));
	const int32 Gid = NewGroup(Side, Name, F);
	for (const int32 I : ShipIdx)
	{
		if (Ships.IsValidIndex(I))
		{
			JoinGroup(Ships[I], Gid);
		}
	}
	if (FAstraBattleGroup* G = FindGroup(Gid))
	{
		G->ProtecteeId = ProtecteeId;
		G->LeaderId = Ships[ShipIdx[0]].Id;
	}
	return Gid;
}

/** Ships that belong to no group (a beat's arrivals, a test contact) join the nearest group of their side within reach, or
 *  found one; groups with nobody left are dropped. */
void UAstraBattleSubsystem::AssignGroups()
{
	for (FAstraBattleShip& S : Ships)
	{
		if (!S.bAlive || S.bCraft || S.bGhost || S.bDerelict || S.bDisabled || S.bPlayer || !S.Dmg.bModel || AstraSideIdx(S.Side) < 0 || S.Mode == EAstraShipMode::Dead)
		{
			continue;
		}
		if (const FAstraBattleGroup* Have = FindGroup(S.GroupId); Have && Have->Members.Contains(S.Id))
		{
			continue;
		}
		FAstraBattleGroup* Best = nullptr;
		double BestD = 40.0 * WarKm;
		for (FAstraBattleGroup& G : Groups)
		{
			const double D = FVector::Dist(G.Centroid, S.Pos);
			if (G.Side == S.Side && G.Members.Num() < 8 && D < BestD && !G.Centroid.IsZero())
			{
				BestD = D;
				Best = &G;
			}
		}
		int32 Gid = Best ? Best->Id : INDEX_NONE;
		if (Gid == INDEX_NONE)
		{
			Gid = NewGroup(S.Side, FString::Printf(TEXT("%s group %d"), S.Side == EAstraSide::Astra ? TEXT("ASTRA") : TEXT("Mandate"), NextGroupId), EAstraFormation::Line);
			if (FAstraBattleGroup* N = FindGroup(Gid))
			{
				N->Centroid = S.Pos;
			}
		}
		JoinGroup(S, Gid);
	}
	for (int32 i = Groups.Num() - 1; i >= 0; --i)
	{
		FAstraBattleGroup& G = Groups[i];
		G.Members.RemoveAll([this](int32 Id) { const FAstraBattleShip* S = FindById(Id); return !S || !S->bAlive || S->bDisabled; });
		if (G.Members.Num() == 0)
		{
			// the group is gone: its ships' orders with it
			Groups.RemoveAtSwap(i);
		}
	}
}

// ---------------------------------------------------------------------------------------------- one group
void UAstraBattleSubsystem::TickGroups(float Dt)
{
	GroupAssignT -= Dt;
	if (GroupAssignT <= 0.f)
	{
		GroupAssignT = 1.5f;
		AssignGroups();
	}
	for (int32 g = 0; g < Groups.Num(); ++g)
	{
		FAstraBattleGroup& G = Groups[g];
		if (Time >= G.NextThink)
		{
			const float DtT = FMath::Max(0.1f, Time - G.NextThink + 0.4f);
			G.NextThink = Time + 0.4f;
			ThinkGroup(G, DtT);
		}
	}
}

void UAstraBattleSubsystem::ThinkGroup(FAstraBattleGroup& G, float DtT)
{
	const int32 Me = AstraSideIdx(G.Side);
	static AstraWar::FTuneVar KRetreat(TEXT("retreat_ratio"), 0.38f), KFlank(TEXT("flank"), 1.f), KSalvo(TEXT("saturate"), 1.f), KRotate(TEXT("rotate"), 1.f),
	                          KFocus(TEXT("focus"), 1.f), KRange(TEXT("range_ai"), 1.f), KMorale(TEXT("morale_ai"), 1.f);
	// --- who is in it and where
	TArray<FAstraBattleShip*, TInlineAllocator<12>> M;
	for (const int32 Id : G.Members)
	{
		FAstraBattleShip* S = FindById(Id);
		if (S && S->bAlive && !S->bDisabled)
		{
			M.Add(S);
		}
	}
	if (M.Num() == 0)
	{
		return;
	}
	FVector C = FVector::ZeroVector, V = FVector::ZeroVector;
	float Str = 0.f, W = 0.f, MinCruise = 1e9f;
	int32 Fleeing = 0;
	for (FAstraBattleShip* S : M)
	{
		const float Wt = FMath::Max(1.f, S->Radius);
		C += S->Pos * Wt;
		V += S->Vel * Wt;
		W += Wt;
		Str += S->CombatValue * Readiness(*S);
		MinCruise = FMath::Min(MinCruise, S->CruiseSpeed);
		Fleeing += S->bFleeing ? 1 : 0;
	}
	C /= W;
	V /= W;
	G.Centroid = C;
	G.Vel = V;
	if (const FAstraBattleShip* Pt = FindById(G.ProtecteeId); Pt && Pt->bAlive && FVector::Dist(Pt->Pos, C) < 20.0 * WarKm)
	{
		Str += Pt->CombatValue * Readiness(*Pt);                       // the ship it protects fights with it
	}
	G.Strength = Str;
	G.StartStrength = FMath::Max(G.StartStrength, Str);
	if (G.LeaderId < 0 || !FindById(G.LeaderId) || !FindById(G.LeaderId)->bAlive || FindById(G.LeaderId)->bDisabled)
	{
		FAstraBattleShip* Lead = M[0];
		for (FAstraBattleShip* S : M)
		{
			Lead = S->Radius > Lead->Radius ? S : Lead;               // no leader left: the biggest ship's captain takes over
		}
		G.LeaderId = Lead->Id;
	}
	if (G.OrderUntil > 0.f && Time >= G.OrderUntil)
	{
		G.Order = EAstraGroupOrder::Auto;                             // an order lapses
		G.OrderShip = G.OrderGroup = -1;
		G.OrderUntil = -1.f;
	}
	// --- what it knows of the enemy: the warships held by its side, near it
	struct FEnemy { FAstraBattleShip* S; FVector Pos; double D; };
	TArray<FEnemy, TInlineAllocator<24>> E;
	int32 EnemyCraftNear = 0;
	FVector EC = FVector::ZeroVector;
	float EStr = 0.f, EW = 0.f;
	for (FAstraBattleShip& O : Ships)
	{
		if (!O.bAlive || O.bGhost || O.bDisabled || O.bDerelict || AstraSideIdx(O.Side) != 1 - Me || !Knows(Me, O))
		{
			continue;
		}
		const FVector P = KnownPos(Me, O);
		const double D = FVector::Dist(P, C);
		if (O.bCraft)
		{
			EnemyCraftNear += D < 20.0 * WarKm ? 1 : 0;
			continue;
		}
		if (D < 80.0 * WarKm)
		{
			E.Add({&O, P, D});
			if (D < 45.0 * WarKm)
			{
				EC += P * O.Radius;
				EW += O.Radius;
				EStr += O.CombatValue * Readiness(O);
			}
		}
	}
	EStr += 0.05f * EnemyCraftNear;
	G.EnemyStrength = EStr;
	const bool bEnemy = E.Num() > 0;
	if (EW > 0.f)
	{
		EC /= EW;
	}
	// an order from the minds: the withdrawal ordered by the commander marks the ships (EnemyOrder), the group notices
	int32 Ordered = 0;
	for (FAstraBattleShip* S : M)
	{
		Ordered += (S->bFleeing && S->bNegotiated) ? 1 : 0;
	}
	if (Ordered > 0 && G.State != EAstraGroupState::Withdraw)
	{
		G.State = EAstraGroupState::Withdraw;
		G.WithdrawSince = Time;
		G.Order = EAstraGroupOrder::Withdraw;
		G.OrderBy = TEXT("admiral");
	}
	if (G.Order == EAstraGroupOrder::Withdraw && G.State == EAstraGroupState::Withdraw && Ordered == 0 && Fleeing < M.Num())
	{
		G.Order = EAstraGroupOrder::Auto;                             // "continue the attack": the ships are back in the fight
		G.State = EAstraGroupState::Engage;
	}
	// --- morale: the balance of strength, and how long it has been against the group
	const float Ratio = EStr > 0.02f ? Str / EStr : 9.f;
	if (G.State == EAstraGroupState::Engage)
	{
		const float Losses = G.StartStrength > 0.f ? 1.f - Str / G.StartStrength : 0.f;
		const bool bWeak = bEnemy && (Ratio < KRetreat.Get() * KMorale.Get() || (Losses > 0.6f && Ratio < 0.8f));
		if (bWeak)
		{
			G.WeakSince = G.WeakSince < 0.f ? Time : G.WeakSince;
		}
		else
		{
			G.WeakSince = -1.f;
		}
		G.Morale = FMath::Clamp(Ratio / 1.2f, 0.f, 1.f) * (1.f - 0.3f * FMath::Clamp(Losses, 0.f, 1.f));
		const bool bBreak = G.WeakSince >= 0.f && Time - G.WeakSince > 14.f;
		if (bBreak && G.Order != EAstraGroupOrder::Hold && G.Order != EAstraGroupOrder::Attack)
		{
			G.State = EAstraGroupState::Withdraw;
			G.WithdrawSince = Time;
			G.Rally = FVector::ZeroVector;
			UE_LOG(LogASTRA, Log, TEXT("[War] %s breaks off: strength %.2f against %.2f, %d of %d ships"), *G.Name, Str, EStr, M.Num(), G.StartCount);
		}
	}
	// --- orders that change the state
	if (G.Order == EAstraGroupOrder::Withdraw && G.State != EAstraGroupState::Withdraw)
	{
		G.State = EAstraGroupState::Withdraw;
		G.WithdrawSince = Time;
	}
	if (G.Order == EAstraGroupOrder::Regroup && G.State != EAstraGroupState::Regroup)
	{
		G.State = EAstraGroupState::Regroup;
		G.Rally = C;
		G.RegroupSince = Time;
	}
	// --- the axis: towards the enemy (its nearest), the protectee's threat axis, or the objective
	FVector Ref = C + G.Axis * 10000.0;
	if (bEnemy)
	{
		double Nearest = 1e18;
		for (const FEnemy& X : E)
		{
			if (X.D < Nearest)
			{
				Nearest = X.D;
				Ref = X.Pos;
			}
		}
		if (EW > 0.f && FVector::Dist(EC, C) < 45.0 * WarKm)
		{
			Ref = EC;
		}
	}
	else if (G.bHasObjective)
	{
		Ref = G.Objective;
	}
	FVector NewAxis = (Ref - C).GetSafeNormal();
	if (!NewAxis.IsNearlyZero())
	{
		G.Axis = (G.Axis * 0.5 + NewAxis * 0.5).GetSafeNormal();
	}
	// --- withdraw / regroup
	if (G.State == EAstraGroupState::Withdraw)
	{
		const FAstraBattleShip* Prot = FindById(G.ProtecteeId);
		if (Prot && Prot->bAlive && G.Rally.IsZero())
		{
			G.Rally = Prot->Pos - G.Axis * 3000.0;                    // fall back behind the ship it protects
		}
		else if (G.Rally.IsZero())
		{
			G.Rally = C - G.Axis * 60.0 * WarKm;
			// the Mandate falls back on the gate it came through, if the system has one
			if (G.Side == EAstraSide::Mandate && Landmarks.IsValidIndex(GateLandmark))
			{
				G.Rally = Landmarks[GateLandmark].Pos;
			}
		}
		// the healthiest covers the rest (a rear guard), the others go
		FAstraBattleShip* Guard = nullptr;
		for (FAstraBattleShip* S : M)
		{
			S->bFleeing = true;
			S->Mode = EAstraShipMode::Evade;
			S->Task = EAstraTask::Formation;
			if (M.Num() >= 3 && (!Guard || Readiness(*S) > Readiness(*Guard)))
			{
				Guard = S;
			}
		}
		if (Guard && bEnemy && Readiness(*Guard) > 0.55f)
		{
			Guard->Task = EAstraTask::RearGuard;
		}
		double Nearest = 1e18;
		for (const FEnemy& X : E)
		{
			Nearest = FMath::Min(Nearest, X.D);
		}
		const bool bContactLost = !bEnemy || Nearest > 38.0 * WarKm;
		if (bContactLost && Time - G.WithdrawSince > 20.f && G.Order != EAstraGroupOrder::Withdraw)
		{
			G.State = EAstraGroupState::Regroup;                        // out of contact: stop and reform
			G.Rally = C;
			G.RegroupSince = Time;
		}
		return;
	}
	if (G.State == EAstraGroupState::Regroup)
	{
		G.Morale = FMath::Min(1.f, G.Morale + 0.012f * DtT);
		for (FAstraBattleShip* S : M)
		{
			S->bFleeing = true;                                         // still off the field (the reports say "retreating")
			S->Mode = EAstraShipMode::Evade;                            // (ThinkWithdraw holds them at the rally point)
		}
		double Nearest = 1e18;
		for (const FEnemy& X : E)
		{
			Nearest = FMath::Min(Nearest, X.D);
		}
		const bool bPressed = bEnemy && Nearest < 22.0 * WarKm;
		if (bPressed && Ratio < 0.9f)
		{
			G.State = EAstraGroupState::Withdraw;                       // they are coming and we are not ready: on
			G.WithdrawSince = Time;
			G.Rally = FVector::ZeroVector;
		}
		else if (G.Order != EAstraGroupOrder::Regroup && (G.Morale >= 0.75f || Time - G.RegroupSince > 150.f) && (!bEnemy || Ratio >= 0.9f))
		{
			G.State = EAstraGroupState::Engage;
			G.WeakSince = -1.f;
			G.bGuideSet = false;
			for (FAstraBattleShip* S : M)
			{
				S->bFleeing = false;
				S->Mode = EAstraShipMode::Attack;
			}
			if (Me == 1 && !bSandbox)
			{
				bEngagementActive = true;                               // they are back
				bScenarioOver = false;
			}
		}
		return;
	}
	// --- engaging: the group fights
	FAstraBattleShip* Prot = FindById(G.ProtecteeId);
	if (Prot && !Prot->bAlive)
	{
		G.ProtecteeId = -1;
		Prot = nullptr;
	}
	// the focus of fire
	FAstraBattleShip* Focus = FindById(G.FocusTarget);
	auto InReachOfGroup = [&](const FAstraBattleShip& X) { return FVector::Dist(KnownPos(Me, X), C) < 45.0 * WarKm; };
	if (Focus && (!Focus->bAlive || Focus->bDisabled || !Knows(Me, *Focus) || !InReachOfGroup(*Focus) || (Focus->bFleeing && Focus->bNegotiated)))
	{
		Focus = nullptr;
	}
	FAstraBattleShip* OrderedTarget = nullptr;
	if ((G.Order == EAstraGroupOrder::Attack || G.Order == EAstraGroupOrder::Pin || G.Order == EAstraGroupOrder::FlankLeft || G.Order == EAstraGroupOrder::FlankRight) && G.OrderShip >= 0)
	{
		OrderedTarget = FindById(G.OrderShip);
		if (OrderedTarget && (!OrderedTarget->bAlive || OrderedTarget->bDisabled))
		{
			OrderedTarget = nullptr;
			G.OrderShip = -1;
		}
	}
	if (OrderedTarget)
	{
		Focus = OrderedTarget;
	}
	else if (bEnemy && (KFocus.Get() > 0.5f))
	{
		FAstraBattleShip* Best = nullptr;
		float BestScore = -1.f;
		for (const FEnemy& X : E)
		{
			const FAstraBattleShip& O = *X.S;
			if (O.Side == EAstraSide::Neutral || O.bHoldFire || (O.bFleeing && O.bNegotiated))
			{
				continue;
			}
			if (G.Order == EAstraGroupOrder::Attack && G.OrderGroup >= 0)
			{
				const FAstraBattleGroup* EG = FindGroup(G.OrderGroup);
				if (EG && !EG->Members.Contains(O.Id))
				{
					continue;
				}
			}
			const float HullF = O.Hull / FMath::Max(1.f, O.HullMax);
			float ShieldF = 0.5f;
			if (O.Dmg.bModel && O.Dmg.Pool > 0.f)
			{
				const int32 Face = AstraFacingOf(O.Att.UnrotateVector((C - X.Pos).GetSafeNormal()));
				ShieldF = O.Dmg.SectorMax[Face] > 0.f ? O.Dmg.Sector[Face] / O.Dmg.SectorMax[Face] : 0.f;
			}
			const float Vuln = FMath::Clamp(1.15f - 0.55f * HullF - 0.35f * ShieldF, 0.2f, 1.3f);
			const double Over = FMath::Max(0.0, X.D - (double)G.EngageRange * 1.4);
			const float ReachF = (float)FMath::Clamp(1.3 - 0.6 * Over / 15000.0, 0.45, 1.0);
			float Score = TargetValue(O) * (0.5f + Vuln) * ReachF;
			if (Focus && O.Id == Focus->Id)
			{
				Score *= 1.4f;                                          // the stickiness: no dithering between two
			}
			if (Prot && O.TargetId == Prot->Id)
			{
				Score *= 1.25f;                                         // it is going for what we protect
			}
			if (O.bFleeing)
			{
				Score *= 0.6f;
			}
			if (Score > BestScore)
			{
				BestScore = Score;
				Best = X.S;
			}
		}
		if (Best && (!Focus || Best->Id != Focus->Id))
		{
			G.FocusSince = Time;
		}
		Focus = Best ? Best : Focus;
	}
	G.FocusTarget = Focus ? Focus->Id : -1;
	const FVector FocusPos = Focus ? KnownPos(Me, *Focus) : Ref;
	if (Focus)
	{
		const FVector A = (FocusPos - C).GetSafeNormal();
		if (!A.IsNearlyZero())
		{
			G.Axis = (G.Axis * 0.4 + A * 0.6).GetSafeNormal();
		}
	}
	// --- the range its armament likes against this enemy (the DPS of both sides at each range)
	if (bEnemy && Focus)
	{
		double MinRail = 1e9;
		for (FAstraBattleShip* S : M)
		{
			MinRail = S->RailDamage > 0.f ? FMath::Min(MinRail, (double)S->RailRange) : MinRail;
		}
		const double Cap = MinRail < 1e8 ? MinRail * 0.92 : 7000.0;
		double BestR = G.EngageRange, BestScore = -1.0;
		for (double R = 3000.0; R <= FMath::Min(9500.0, Cap) + 1.0; R += 1000.0)
		{
			double Mine = 0.0, Theirs = 0.0;
			for (FAstraBattleShip* S : M)
			{
				Mine += ShipDps(*S, R);
			}
			for (const FEnemy& X : E)
			{
				if (FVector::Dist(X.Pos, FocusPos) < 15.0 * WarKm)
				{
					Theirs += ShipDps(*X.S, R);
				}
			}
			double Score = (Mine + 4.0) / (Theirs + 4.0) * (1.0 + 0.015 * R / 1000.0);
			if (FMath::Abs(R - G.EngageRange) < 1.0)
			{
				Score *= 1.06;                                          // hysteresis: keep the range unless another is clearly better
			}
			if (Score > BestScore)
			{
				BestScore = Score;
				BestR = R;
			}
		}
		double MyCruise = MinCruise;
		double TheirCruise = 0.0;
		for (const FEnemy& X : E)
		{
			TheirCruise = FMath::Max(TheirCruise, (double)X.S->CruiseSpeed);
		}
		if (TheirCruise > 1.25 * MyCruise && BestR > 5500.0)
		{
			BestR = 5500.0;                                             // it is faster: it will close on us whatever the range we choose
		}
		if (G.Order == EAstraGroupOrder::Pin)
		{
			BestR = FMath::Min(Cap, 9000.0);
		}
		G.EngageRange = (float)(BestR * KRange.Get());
	}
	else if (!bEnemy)
	{
		G.EngageRange = FMath::Max(G.EngageRange, 5500.f);
	}
	// --- the guide: it leads the group to the range and holds there
	const float GuideSpeed = MinCruise * 0.92f;
	FVector GuideTarget = C;
	if (Focus)
	{
		GuideTarget = FocusPos - G.Axis * (double)G.EngageRange;
		if (G.Formation == EAstraFormation::Screen && Prot)
		{
			GuideTarget = Prot->Pos;
		}
	}
	else if (Prot)
	{
		GuideTarget = Prot->Pos + Prot->Att.GetForwardVector() * 1500.0;
	}
	else if (G.bHasObjective)
	{
		GuideTarget = G.Objective - G.Axis * 3000.0;
	}
	if (G.Order == EAstraGroupOrder::Reinforce && G.OrderGroup >= 0)
	{
		if (const FAstraBattleGroup* Ally = FindGroup(G.OrderGroup))
		{
			GuideTarget = Ally->Centroid - G.Axis * 2500.0;
		}
	}
	if (!G.bGuideSet)
	{
		G.Guide = C;
		G.bGuideSet = true;
	}
	if (G.Order == EAstraGroupOrder::Hold)
	{
		GuideTarget = G.Guide;
	}
	if (G.Order == EAstraGroupOrder::Screen && Prot)
	{
		G.Formation = EAstraFormation::Screen;
	}
	// a ship far behind its slot slows the guide (the group keeps together)
	double MaxLag = 0.0;
	for (const FAstraBattleShip* S : M)
	{
		if (S->bTaskSet && S->Task == EAstraTask::Formation)
		{
			MaxLag = FMath::Max(MaxLag, FVector::Dist(S->Pos, S->TaskPos));
		}
	}
	const float LagK = MaxLag > 4.0 * WarKm ? 0.45f : 1.f;
	const FVector ToGuide = GuideTarget - G.Guide;
	const double Step = (double)GuideSpeed * LagK * DtT;
	FVector GuideVel = FVector::ZeroVector;
	if (ToGuide.Size() > Step)
	{
		GuideVel = ToGuide.GetSafeNormal() * GuideSpeed * LagK;
		G.Guide += GuideVel * DtT;
	}
	else
	{
		G.Guide = GuideTarget;
		GuideVel = FVector::ZeroVector;                                 // (no matching of the enemy's velocity: two groups doing it drift off together)
	}
	// --- the slots
	const FVector Right = HorizontalRight(G.Axis);
	double AvgR = 0.0;
	for (const FAstraBattleShip* S : M)
	{
		AvgR += S->Radius;
	}
	AvgR /= M.Num();
	const double Sp = FMath::Clamp(AvgR * 2.4 + 500.0, 900.0, 3500.0);
	M.Sort([&](const FAstraBattleShip& A, const FAstraBattleShip& B)      // (a pointer array hands the predicate what they point at)
	{
		if ((A.Id == G.LeaderId) != (B.Id == G.LeaderId))
		{
			return A.Id == G.LeaderId;                                  // the leader takes the point
		}
		return A.Id < B.Id;
	});
	const int32 N = M.Num();
	// rotation: the most battered fall back behind the line while others are fit to hold it
	int32 Fit = 0;
	for (const FAstraBattleShip* S : M)
	{
		Fit += Readiness(*S) > 0.6f ? 1 : 0;
	}
	const bool bRotate = KRotate.Get() > 0.5f && N >= 2 && Fit >= 1 && bEnemy;
	for (int32 k = 0; k < N; ++k)
	{
		FAstraBattleShip& S = *M[k];
		FVector Slot = G.Guide;
		const double Lat = (k - (N - 1) * 0.5);
		switch (G.Formation)
		{
		case EAstraFormation::Wedge:
		{
			const int32 Rank = (k + 1) / 2;
			Slot += Right * ((k % 2 ? 1.0 : -1.0) * Rank * Sp) - G.Axis * (0.8 * Sp * Rank);
			break;
		}
		case EAstraFormation::Column:
			Slot += -G.Axis * (Sp * 1.2 * k);
			break;
		case EAstraFormation::Screen:
			if (Prot)
			{
				const double Angle = Lat * 32.0;
				const double ScreenR = FMath::Max(2500.0, (double)Prot->Radius + 2400.0);
				const FVector Out = (Ref - Prot->Pos).GetSafeNormal();
				Slot = Prot->Pos + RotateAboutUp(Out.IsNearlyZero() ? G.Axis : Out, Angle) * ScreenR;
			}
			else
			{
				Slot += Right * (Lat * Sp);
			}
			break;
		default:
			Slot += Right * (Lat * Sp);
			break;
		}
		S.Task = EAstraTask::Formation;
		const float Ready = Readiness(S);
		if (bRotate && Ready < 0.5f && N >= 2 && (Fit >= 1))
		{
			S.Task = EAstraTask::Reserve;
			Slot -= G.Axis * 3800.0;                                    // behind the line, still in the fight
		}
		S.TaskPos = Slot;
		S.TaskVel = GuideVel;
		S.bTaskSet = true;
	}
	// --- flanks: one or two agile, healthy ships swing to the enemy's blind arc
	const bool bFlankOrder = G.Order == EAstraGroupOrder::FlankLeft || G.Order == EAstraGroupOrder::FlankRight;
	const bool bAutoFlank = KFlank.Get() > 0.5f && G.Order == EAstraGroupOrder::Auto && N >= 3 && bEnemy && Focus && EStr > 0.5f * Str;
	if (Focus && (bFlankOrder || bAutoFlank))
	{
		const int32 Want = bFlankOrder ? FMath::Max(1, N / 2) : FMath::Min(2, N / 3);
		if (Time - G.FlankAssignedAt > 45.f || G.FlankShip[0] < 0)
		{
			// the most agile of the fit ships (acceleration and turn rate), not the leader
			TArray<FAstraBattleShip*, TInlineAllocator<12>> Cand;
			for (FAstraBattleShip* S : M)
			{
				if (S->Id != G.LeaderId && Readiness(*S) > 0.6f && S->Task == EAstraTask::Formation)
				{
					Cand.Add(S);
				}
			}
			Cand.Sort([](const FAstraBattleShip& A, const FAstraBattleShip& B) { return A.MaxAccel * A.MaxTurnDeg > B.MaxAccel * B.MaxTurnDeg; });
			G.FlankShip[0] = G.FlankShip[1] = -1;
			for (int32 i = 0; i < FMath::Min(Want, Cand.Num()) && i < 2; ++i)
			{
				G.FlankShip[i] = Cand[i]->Id;
				// the side: as ordered, else the enemy's blind arc (the quarter its guns cover least)
				int8 Side = i == 0 ? 1 : -1;
				if (G.Order == EAstraGroupOrder::FlankLeft) { Side = -1; }
				else if (G.Order == EAstraGroupOrder::FlankRight) { Side = 1; }
				else
				{
					const FVector Dir = (FocusPos - Cand[i]->Pos).GetSafeNormal();
					float BestCov = 1e9f;
					for (const int8 Sd : {(int8)1, (int8)-1})
					{
						const FVector Where = RotateAboutUp(-Dir, Sd * 105.0);           // the bearing from the enemy to the flank point
						float Cov = 0.f;
						const FVector Local = Focus->Att.UnrotateVector(Where);
						for (const FAstraMount& Mt : Focus->Mounts)
						{
							Cov += Mt.CanBear(Local) ? Mt.Barrels * Focus->RailDamage / FMath::Max(1.f, Focus->RailCd) * Mt.Health : 0.f;
						}
						if (Cov + (Sd == Side ? 0.f : 3.f) < BestCov)
						{
							BestCov = Cov + (Sd == Side ? 0.f : 3.f);
							Side = Sd;
						}
					}
					if (Want >= 2 && i == 1 && G.FlankSide[0] == Side)
					{
						Side = -Side;                                                    // two flankers go round opposite ways
					}
				}
				G.FlankSide[i] = Side;
			}
			G.FlankAssignedAt = Time;
		}
		for (int32 i = 0; i < 2; ++i)
		{
			FAstraBattleShip* F = G.FlankShip[i] >= 0 ? FindById(G.FlankShip[i]) : nullptr;
			if (!F || !F->bAlive || F->bFleeing)
			{
				G.FlankShip[i] = -1;
				continue;
			}
			// round the enemy on an arc of its range: the bearing steps on towards the flank, never a straight run through its guns
			const FVector FromEnemy = (F->Pos - FocusPos);
			const double Now2 = FMath::RadiansToDegrees(FMath::Atan2(FromEnemy.Y, FromEnemy.X));
			const FVector Back = -G.Axis;
			const double Goal2 = FMath::RadiansToDegrees(FMath::Atan2(Back.Y, Back.X)) - G.FlankSide[i] * 105.0;
			double Delta = FMath::UnwindDegrees(Goal2 - Now2);
			const double Rr = FMath::Max((double)G.EngageRange * 1.05, 3500.0);
			// the point it heads for is a few seconds ahead of it on the arc (what it can fly), never a point running away round the circle
			const double MaxStep = FMath::RadiansToDegrees((double)F->CruiseSpeed * 8.0 / Rr);
			Delta = FMath::Clamp(Delta, -MaxStep, MaxStep);
			const double A = FMath::DegreesToRadians(Now2 + Delta);
			F->TaskPos = FocusPos + FVector(FMath::Cos(A), FMath::Sin(A), 0.0) * Rr;
			F->TaskVel = FVector::ZeroVector;
			F->Task = EAstraTask::Flank;
			F->bTaskSet = true;
		}
	}
	else
	{
		G.FlankShip[0] = G.FlankShip[1] = -1;
	}
	// --- the missiles: kept until enough are ready to saturate the target's defence, then all together
	if (Focus && KSalvo.Get() > 0.5f)
	{
		TArray<FAstraBattleShip*, TInlineAllocator<12>> Ready;
		double MaxTof = 0.0;
		int32 Cells = 0;
		for (FAstraBattleShip* S : M)
		{
			S->bHoldMissiles = false;
			const double D = FVector::Dist(S->Pos, FocusPos);
			if (S->Missiles > 0 && S->MissileT <= 0.f && !S->bConserve && S->SalvoAt < 0.f && D > 2600.0 && D < S->MissileRange * 0.95)
			{
				Ready.Add(S);
				Cells += FMath::Min(S->Missiles, S->Radius > 200.f ? 6 : 3);
				MaxTof = FMath::Max(MaxTof, D / 1200.0 + 1.5);
			}
		}
		float PdCh = Focus->PDChannels * (Focus->Dmg.bModel ? Focus->Dmg.Sys[AstraWar::SysPointDefence] : 1.f);
		const int32 Need = FMath::CeilToInt(3.f + 1.6f * PdCh);
		const bool bEnough = Cells >= Need;
		const bool bStale = Time - G.LastSalvo > 35.f;
		if (Ready.Num() && (bEnough || (bStale && Ready.Num() >= 1 && (Cells >= 3 || Time - G.LastSalvo > 60.f))))
		{
			const double TOT = Time + MaxTof;
			for (FAstraBattleShip* S : Ready)
			{
				const double D = FVector::Dist(S->Pos, FocusPos);
				S->SalvoAt = (float)(TOT - (D / 1200.0 + 1.5));
				S->bHoldMissiles = true;
			}
			G.SalvoTOT = (float)TOT;
			G.LastSalvo = Time;
		}
		else
		{
			for (FAstraBattleShip* S : Ready)
			{
				S->bHoldMissiles = true;                                        // wait for the rest
			}
		}
	}
	else
	{
		for (FAstraBattleShip* S : M)
		{
			S->bHoldMissiles = false;
		}
	}
	// the ships of the group that have no orders of their own fight on the group's target
	for (FAstraBattleShip* S : M)
	{
		if (S->Mode == EAstraShipMode::Cruise && bEnemy)
		{
			S->Mode = EAstraShipMode::Attack;
		}
	}
}

// ---------------------------------------------------------------------------------------------- the minds' orders
bool UAstraBattleSubsystem::SetGroupOrder(int32 GroupId, const FString& Order, const FString& ShipContact, int32 OtherGroup, float Duration, const FString& By, FString& OutDetail)
{
	FAstraBattleGroup* G = FindGroup(GroupId);
	if (!G)
	{
		OutDetail = TEXT("no such group");
		return false;
	}
	const FString O = Order.ToLower();
	auto Ship = [&]() -> FAstraBattleShip* { return ShipContact.IsEmpty() ? nullptr : FindByContact(ShipContact.ToUpper()); };
	if (O == TEXT("auto"))
	{
		G->Order = EAstraGroupOrder::Auto;
	}
	else if (O == TEXT("attack") || O == TEXT("attack_group") || O == TEXT("pin") || O == TEXT("flank_left") || O == TEXT("flank_right"))
	{
		G->Order = O == TEXT("pin") ? EAstraGroupOrder::Pin : (O == TEXT("flank_left") ? EAstraGroupOrder::FlankLeft
		         : (O == TEXT("flank_right") ? EAstraGroupOrder::FlankRight : EAstraGroupOrder::Attack));
		if (FAstraBattleShip* T = Ship())
		{
			// a ship of an enemy group: attack it, or (attack_group) the group it belongs to
			G->OrderShip = O == TEXT("attack_group") ? -1 : T->Id;
			G->OrderGroup = (O == TEXT("attack_group") || O == TEXT("attack")) ? T->GroupId : -1;
			if (O == TEXT("attack_group") && G->OrderGroup < 0)
			{
				G->OrderShip = T->Id;
			}
		}
		else if (O != TEXT("pin"))
		{
			G->OrderShip = -1;
		}
	}
	else if (O == TEXT("screen"))
	{
		G->Order = EAstraGroupOrder::Screen;
		G->Formation = EAstraFormation::Screen;
	}
	else if (O == TEXT("withdraw"))
	{
		G->Order = EAstraGroupOrder::Withdraw;
	}
	else if (O == TEXT("regroup"))
	{
		G->Order = EAstraGroupOrder::Regroup;
	}
	else if (O == TEXT("reinforce"))
	{
		G->Order = EAstraGroupOrder::Reinforce;
		G->OrderGroup = OtherGroup;
	}
	else if (O == TEXT("hold"))
	{
		G->Order = EAstraGroupOrder::Hold;
	}
	else
	{
		OutDetail = FString::Printf(TEXT("unknown group order '%s'"), *Order);
		return false;
	}
	G->OrderBy = By;
	G->OrderUntil = Duration > 0.f ? Time + Duration : -1.f;
	OutDetail = FString::Printf(TEXT("%s: %s"), *G->Name, *O);
	return true;
}

TSharedRef<FJsonObject> UAstraBattleSubsystem::GroupsJson() const
{
	TSharedRef<FJsonObject> R = MakeShared<FJsonObject>();
	static const TCHAR* const States[] = {TEXT("engage"), TEXT("withdraw"), TEXT("regroup")};
	static const TCHAR* const Orders[] = {TEXT("auto"), TEXT("attack"), TEXT("pin"), TEXT("flank_left"), TEXT("flank_right"), TEXT("screen"), TEXT("withdraw"),
	                                      TEXT("regroup"), TEXT("reinforce"), TEXT("hold")};
	static const TCHAR* const Forms[] = {TEXT("line"), TEXT("wedge"), TEXT("column"), TEXT("screen")};
	TArray<TSharedPtr<FJsonValue>> Arr;
	for (const FAstraBattleGroup& G : Groups)
	{
		TSharedRef<FJsonObject> J = MakeShared<FJsonObject>();
		J->SetNumberField(TEXT("id"), G.Id);
		J->SetStringField(TEXT("name"), G.Name);
		J->SetStringField(TEXT("side"), G.Side == EAstraSide::Astra ? TEXT("astra") : TEXT("mandate"));
		J->SetStringField(TEXT("state"), States[(int32)G.State]);
		J->SetStringField(TEXT("order"), Orders[(int32)G.Order]);
		J->SetStringField(TEXT("formation"), Forms[(int32)G.Formation]);
		J->SetNumberField(TEXT("ships"), G.Members.Num());
		J->SetNumberField(TEXT("focus"), G.FocusTarget);
		J->SetNumberField(TEXT("protectee"), G.ProtecteeId);
		J->SetNumberField(TEXT("morale"), FMath::RoundToDouble(G.Morale * 100.0) / 100.0);
		J->SetNumberField(TEXT("range_m"), FMath::RoundToDouble(G.EngageRange));
		J->SetNumberField(TEXT("strength"), FMath::RoundToDouble(G.Strength * 100.0) / 100.0);
		J->SetNumberField(TEXT("enemy_strength"), FMath::RoundToDouble(G.EnemyStrength * 100.0) / 100.0);
		Arr.Add(MakeShared<FJsonValueObject>(J));
	}
	R->SetArrayField(TEXT("groups"), Arr);
	return R;
}
