// ASTRA — ABBORDAGGI: the squad drill: columns, contact, the base of fire and the flank, holding a corner, falling back, bringing the Captain out.
// What a squad does follows from its task (the Mandate's objective, the marines' orders) and from what its men see; the men's own work
// (corners, bursts, reloads) is in AstraBoardSim.cpp. See AstraBoardSim.h.

#include "AstraBoardSim.h"

using namespace AstraBoard;

namespace
{
	float BoardYaw(const FVector& D) { return FMath::RadiansToDegrees(FMath::Atan2(D.Y, D.X)); }
}

// ================================================================================================================== orders

void FAstraBoardSim::Order(int32 SquadId, ETask Task, int32 Comp, const FVector& Pos, float Radius, const FString& Note)
{
	if (!Teams.IsValidIndex(SquadId))
	{
		return;
	}
	FSquad& S = Teams[SquadId];
	S.Task = Task;
	S.TargetComp = Comp != INDEX_NONE ? Comp : Map->CompAt(Pos, 80.f);
	S.TargetPos = Pos;
	S.Radius = Radius;
	S.TaskT = 0.f;
	S.PlanT = 1.f;
	S.bOrdered = true;
	S.Flankers[0] = S.Flankers[1] = INDEX_NONE;
	S.Trail.Reset();
	S.Note = Note;
	for (const int32 M : S.Members)
	{
		FUnit& U = People[M];
		if (U.Able())
		{
			U.Slot = INDEX_NONE;
			U.Path.Reset();
			U.PathI = 0;
			U.Speed = 0.f;
			U.bAtPeek = false;
		}
	}
	Emit(EEvent::Order, S.Leader, INDEX_NONE, Pos, Pos, 0.f, false, FString::Printf(TEXT("%s: %s%s%s"), *S.Name, TaskName(Task), Note.IsEmpty() ? TEXT("") : TEXT(" — "), *Note));
}

void FAstraBoardSim::Respond(int32 SquadId)
{
	if (Teams.IsValidIndex(SquadId))
	{
		Teams[SquadId].bOrdered = false;
		Teams[SquadId].Task = ETask::Idle;
		Teams[SquadId].PlanT = 1.f;
	}
}

// ================================================================================================================== the squad's step

void FAstraBoardSim::StepSquad(FSquad& S, float Dt)
{
	if (S.Members.IsEmpty())
	{
		return;
	}
	S.TaskT += Dt;
	S.PlanT += Dt;
	S.FlankT += Dt;
	if (S.MusterT > 0.f)
	{
		S.MusterT = FMath::Max(0.f, S.MusterT - Dt);
	}
	// the leader: the first able man of the squad when he falls
	if (S.Leader == INDEX_NONE || !People[S.Leader].Able())
	{
		S.Leader = INDEX_NONE;
		for (const int32 M : S.Members)
		{
			if (People[M].Able() && (S.Leader == INDEX_NONE || People[M].Role == ERole::Leader))
			{
				S.Leader = M;
			}
		}
	}
	// contact: any of them sees an enemy; the squad shares what each sees (they talk to each other)
	bool bSee = false;
	for (const int32 M : S.Members)
	{
		const FUnit& U = People[M];
		if (!U.Able())
		{
			continue;
		}
		for (const FSeen& Sn : U.Seen)
		{
			if (Sn.bVisibleNow)
			{
				bSee = true;
				for (const int32 O : S.Members)
				{
					FUnit& V = People[O];
					if (O == M || !V.Able())
					{
						continue;
					}
					FSeen* X = V.Seen.FindByPredicate([&Sn](const FSeen& Y) { return Y.Unit == Sn.Unit; });
					if (!X && V.Seen.Num() < 8)
					{
						X = &V.Seen.AddDefaulted_GetRef();
						X->Unit = Sn.Unit;
						X->AgeS = 0.5f;
						X->Pos = Sn.Pos;
					}
					else if (X && !X->bVisibleNow && X->AgeS > 0.4f)
					{
						X->Pos = Sn.Pos;
						X->AgeS = 0.4f;
					}
				}
			}
		}
	}
	if (bSee)
	{
		S.bContact = true;
		S.ContactT = 0.f;
	}
	else
	{
		S.ContactT += Dt;
		if (S.ContactT > 7.f)
		{
			S.bContact = false;
		}
	}
	if (S.Leader != INDEX_NONE && S.Side == ESide::Mandate && (S.Trail.IsEmpty() || FVector::Dist2D(S.Trail.Last(), People[S.Leader].Pos) > 90.f))
	{
		S.Trail.Add(People[S.Leader].Pos);
		if (S.Trail.Num() > 80)
		{
			S.Trail.RemoveAt(0, 20);
		}
	}
	if (S.PlanT >= 0.5f)
	{
		S.PlanT = 0.f;
		if (!S.bStand)
		{
			Plan(S);
		}
	}
}

void FAstraBoardSim::Plan(FSquad& S)
{
	if (S.Side == ESide::Mandate)
	{
		PlanMandate(S);
	}
	else
	{
		PlanMarines(S);
	}
}

// ================================================================================================================== moving a squad

/** A column: the leader goes to the place, the others follow where he has been, a couple of metres apart. */
void FAstraBoardSim::ColumnTo(FSquad& S, const FVector& To, float Speed)
{
	if (S.Leader == INDEX_NONE)
	{
		return;
	}
	FUnit& L = People[S.Leader];
	if (L.Act != EAct::Reload && (L.Path.IsEmpty() || FVector::Dist2D(L.Dest, To) > 150.f) && FVector::Dist2D(L.Pos, To) > 120.f)
	{
		L.Slot = INDEX_NONE;
		GoTo(L, To, Speed);
	}
	int32 Slot = 0;
	for (const int32 M : S.Members)
	{
		FUnit& U = People[M];
		if (M == S.Leader || !U.Able())
		{
			continue;
		}
		++Slot;
		U.Slot = INDEX_NONE;
		if (U.Act == EAct::Reload)
		{
			continue;
		}
		// the place in the file: where the leader was a couple of metres a man ago
		const int32 Back = FMath::Min(S.Trail.Num() - 1, Slot * 2 + 1);
		const FVector Want = Back >= 0 ? S.Trail[S.Trail.Num() - 1 - Back] : L.Pos;
		const float Gap = (float)FVector::Dist2D(U.Pos, Want);
		if (Gap > 130.f && (U.Path.IsEmpty() || FVector::Dist2D(U.Dest, Want) > 220.f))
		{
			GoTo(U, Want, FMath::Min(Speed * 1.12f, Tuning.JogCmS * 1.1f));
		}
		else if (Gap <= 130.f && U.Path.IsEmpty())
		{
			U.Speed = 0.f;
			U.Act = EAct::Idle;
		}
	}
}

/** Fighting positions round a place: each man a corner of his own, the ones that cover the way the enemy comes first. */
void FAstraBoardSim::HoldAround(FSquad& S, const FVector& At, float Radius)
{
	// the way the enemy comes from: what is known of them, else the planned route's start
	FVector Approach = Mis.BreachPos;
	TArray<FSeen> Seen;
	Intel(S.Side == ESide::Aquila ? ESide::Aquila : ESide::Mandate, Seen);
	if (Seen.Num())
	{
		FVector C = FVector::ZeroVector;
		for (const FSeen& X : Seen)
		{
			C += X.Pos;
		}
		Approach = C / Seen.Num();
	}
	const int32 HomeComp = Map->CompAt(At, 120.f);
	if (HomeComp == INDEX_NONE)
	{
		return;
	}
	TArray<TPair<float, int32>> Cands;
	TArray<int32> Comps;
	Comps.Add(HomeComp);
	for (const int32 Pi : Map->GetComps()[HomeComp].Portals)
	{
		const FBoardPortal& P = Map->GetPortals()[Pi];
		if (!P.bVertical() && FVector::Dist2D(P.Pos, At) < Radius + 300.f)
		{
			Comps.AddUnique(P.Other(HomeComp));
		}
	}
	for (const int32 C : Comps)
	{
		for (const int32 Si : Map->GetComps()[C].Slots)
		{
			const FBoardSlot& Sl = Map->GetSlots()[Si];
			if (FVector::Dist2D(Sl.Pos, At) > Radius + 400.f)
			{
				continue;
			}
			// a corner whose opening looks towards the enemy covers his way in
			const FVector2D ToEnemy = FVector2D(Approach.X - Sl.Pos.X, Approach.Y - Sl.Pos.Y).GetSafeNormal();
			const float Facing = (float)FVector2D::DotProduct(Sl.Out, ToEnemy);
			Cands.Emplace(-Facing * 400.f + (float)FVector::Dist2D(Sl.Pos, At) * 0.3f, Si);
		}
	}
	Cands.Sort([](const TPair<float, int32>& A, const TPair<float, int32>& B) { return A.Key < B.Key; });
	TArray<int32> Taken;
	for (const int32 M : S.Members)
	{
		FUnit& U = People[M];
		if (!U.Able())
		{
			continue;
		}
		if (U.Slot != INDEX_NONE && Cands.ContainsByPredicate([&U](const TPair<float, int32>& P) { return P.Value == U.Slot; }))
		{
			Taken.AddUnique(U.Slot);                       // he keeps the corner he has
			continue;
		}
		int32 Pick = INDEX_NONE;
		for (const TPair<float, int32>& P : Cands)
		{
			if (!Taken.Contains(P.Value) && !People.ContainsByPredicate([&](const FUnit& O) { return O.Id != U.Id && O.Side == U.Side && O.Slot == P.Value && O.Able(); }))
			{
				Pick = P.Value;
				break;
			}
		}
		if (Pick == INDEX_NONE)
		{
			// no corner left: he stands near the place
			if (U.Path.IsEmpty() && FVector::Dist2D(U.Pos, At) > 400.f)
			{
				GoTo(U, Map->Inset(HomeComp, At, 60.f), Tuning.JogCmS);
			}
			continue;
		}
		Taken.Add(Pick);
		U.Slot = Pick;
		U.bAtPeek = false;
		U.CycleT = Rng.FRandRange(0.2f, 0.9f);
		GoTo(U, Map->GetSlots()[Pick].Pos, Tuning.JogCmS);
	}
}

// ================================================================================================================== the flank

bool FAstraBoardSim::FlankFor(FSquad& S, const FVector& Enemy)
{
	if (!Tuning.bFlank || S.Flankers[0] != INDEX_NONE || S.FlankT < 12.f || S.bOrdered)
	{
		return false;
	}
	TArray<int32> Cand;
	for (const int32 M : S.Members)
	{
		if (M != S.Leader && People[M].Able() && People[M].Role != ERole::Heavy && People[M].Rounds > 8)
		{
			Cand.Add(M);
		}
	}
	if (Cand.Num() < 3)
	{
		return false;
	}
	Cand.Sort([this](int32 A, int32 B) { return People[A].Hp > People[B].Hp; });
	// the portals the enemy covers cost a lot: the flank goes round them
	TArray<float> Pen;
	Pen.Init(0.f, Map->GetPortals().Num());
	const FVector EnemyEye = Enemy + FVector(0, 0, 150);
	for (int32 i = 0; i < Map->GetPortals().Num(); ++i)
	{
		const FBoardPortal& P = Map->GetPortals()[i];
		if (FVector::Dist2D(P.Pos, Enemy) < 6000.f && FMath::Abs(P.Pos.Z - Enemy.Z) < 300.f && Map->Visible(P.Pos + FVector(0, 0, 150), EnemyEye, &Doors, P.Door))
		{
			Pen[i] = 3500.f;
		}
	}
	FBoardRouteOptions Plain, Around;
	Plain.Doors = &Doors;
	Around.Doors = &Doors;
	Around.PortalPenalty = &Pen;
	Plain.bThroughSealed = Around.bThroughSealed = S.Side == ESide::Mandate;       // the Mandate cut through another bulkhead to get round
	int32 Got = 0;
	for (const int32 M : Cand)
	{
		FUnit& U = People[M];
		TArray<FVector> Pts;
		TArray<int32> Direct, Round;
		float Metres = 0.f;
		if (!Map->Route(U.Pos, Enemy, Pts, Around, &Metres) || Metres > 220.f)
		{
			continue;
		}
		if (!Map->RoutePortals(U.Pos, Enemy, Direct, Plain) || !Map->RoutePortals(U.Pos, Enemy, Round, Around) || Direct == Round)
		{
			continue;                                      // there is no other way: no flank
		}
		// a way in under his eyes is no flank (the last portal is the one he is at)
		int32 Exposed = 0;
		for (int32 k = 0; k + 1 < Round.Num(); ++k)
		{
			Exposed += Pen[Round[k]] > 0.f ? 1 : 0;
		}
		if (Exposed > 0)
		{
			continue;
		}
		U.Slot = INDEX_NONE;
		U.bAtPeek = false;
		U.Path = MoveTemp(Pts);
		U.PathI = 1;
		U.Dest = Enemy;
		U.Speed = Tuning.JogCmS;
		U.Cruise = Tuning.JogCmS;
		U.Act = EAct::Move;
		U.Target = INDEX_NONE;
		S.Flankers[Got++] = M;
		if (Got == 2)
		{
			break;
		}
	}
	if (Got == 0)
	{
		S.FlankT = 8.f;                                    // no way found: think again in a few seconds
		return false;
	}
	S.FlankAt = Enemy;
	S.FlankT = 0.f;
	++Stats.Flanks;
	Emit(EEvent::Order, S.Leader, INDEX_NONE, Enemy, Enemy, 0.f, false, FString::Printf(TEXT("%s: %d man flank round the position"), *S.Name, Got));
	return true;
}

// ================================================================================================================== the Mandate

void FAstraBoardSim::PlanMandate(FSquad& S)
{
	if (S.Leader == INDEX_NONE)
	{
		return;
	}
	TArray<int32> Able;
	for (const int32 M : S.Members)
	{
		if (People[M].Able())
		{
			Able.Add(M);
		}
	}
	if (Able.IsEmpty())
	{
		return;
	}
	const float LossShare = S.StartStrength > 0.f ? S.Lost / S.StartStrength : 0.f;
	if (S.Task != ETask::Withdraw && LossShare >= Tuning.MandateRetreatLoss && !S.bOrdered)
	{
		S.Task = ETask::Withdraw;
		S.TaskT = 0.f;
		S.Flankers[0] = S.Flankers[1] = INDEX_NONE;
		++Stats.Retreats;
		for (const int32 M : Able)
		{
			People[M].Slot = INDEX_NONE;
			People[M].Path.Reset();
		}
		Emit(EEvent::Retreat, S.Leader, INDEX_NONE, People[S.Leader].Pos, People[S.Leader].Pos, 0.f, false, S.Name);
	}
	FUnit& L = People[S.Leader];
	if (S.Task != ETask::Advance)
	{
		S.StallT = 0.f;
	}
	switch (S.Task)
	{
	case ETask::Withdraw:
	{
		for (const int32 M : Able)
		{
			FUnit& U = People[M];
			if (U.Comp == Mis.Breach && FVector::Dist2D(U.Pos, Mis.BreachPos) < 420.f)
			{
				U.Act = EAct::Gone;
				U.Path.Reset();
				++Stats.Exited[1];
				Emit(EEvent::Exit, U.Id, INDEX_NONE, U.Pos, U.Pos, 0.f, false, U.Name);
				continue;
			}
			if (U.Act != EAct::Reload && (U.Path.IsEmpty() || FVector::Dist2D(U.Dest, Mis.BreachPos) > 200.f))
			{
				U.Slot = INDEX_NONE;
				GoTo(U, Mis.BreachPos, Tuning.JogCmS * 1.05f, true);
			}
		}
		break;
	}
	case ETask::Advance:
	{
		if (L.Comp == S.TargetComp || FVector::Dist2D(L.Pos, S.TargetPos) < 600.f)
		{
			S.Task = ETask::Hold;                          // the objective: they hold it
			S.TaskT = 0.f;
			Emit(EEvent::Order, S.Leader, INDEX_NONE, L.Pos, L.Pos, 0.f, false, FString::Printf(TEXT("%s: at the objective, holding"), *S.Name));
			break;
		}
		// the way in: not getting any nearer with the enemy about for long enough, the squad presses the attack (a boarding party that sits at a door loses the ship it came to take)
		{
			const float Dist = (float)FVector::Dist2D(L.Pos, S.TargetPos);
			if (Dist < S.BestDist - 400.f)
			{
				S.BestDist = Dist;
				S.StallT = 0.f;
			}
			else if (S.ContactT < 20.f)
			{
				S.StallT += 0.5f;
			}
			if (S.StallT >= Tuning.PushS)
			{
				S.Task = ETask::Assault;
				S.TaskT = 0.f;
				S.StallT = 0.f;
				Emit(EEvent::Order, S.Leader, INDEX_NONE, L.Pos, L.Pos, 0.f, false, FString::Printf(TEXT("%s: pressing the attack"), *S.Name));
				break;
			}
		}
		if (!S.bContact)
		{
			if (S.Flankers[0] != INDEX_NONE)
			{
				S.Flankers[0] = S.Flankers[1] = INDEX_NONE;
			}
			ColumnTo(S, S.TargetPos, Tuning.JogCmS);
			break;
		}
		// contact: the squad fixes the enemy where he is and a pair goes round
		FVector EnemyAt = FVector::ZeroVector;
		bool bAny = false;
		float Nearest = 1.0e9f;
		for (const int32 M : Able)
		{
			for (const FSeen& Sn : People[M].Seen)
			{
				const float D = (float)FVector::Dist(People[M].Pos, Sn.Pos);
				if (D < Nearest && Sn.AgeS < 4.f)
				{
					Nearest = D;
					EnemyAt = Sn.Pos;
					bAny = true;
				}
			}
		}
		if (bAny)
		{
			if (S.Flankers[0] == INDEX_NONE)
			{
				FlankFor(S, EnemyAt);
			}
			// the ones who are not going round take a corner on the enemy
			for (const int32 M : Able)
			{
				FUnit& U = People[M];
				if (M == S.Flankers[0] || M == S.Flankers[1] || U.Slot != INDEX_NONE || U.Act == EAct::Reload || U.Act == EAct::Peek)
				{
					continue;
				}
				if (U.Path.IsEmpty() || U.Speed < 1.f)
				{
					TakeCover(U, EnemyAt);
				}
			}
			// the enemy is weak, close and pinned: go in
			int32 Fit = 0;
			for (const int32 M : Able) { Fit += People[M].Suppression < 0.5f ? 1 : 0; }
			int32 Theirs = 0;
			for (const FUnit& E : People) { Theirs += (E.Side == ESide::Aquila && E.Able() && !E.bExternal && FVector::Dist(E.Pos, EnemyAt) < 2500.f) ? 1 : 0; }
			if (Theirs > 0 && Theirs * 2 <= Fit && Nearest < 1500.f && S.TaskT > 8.f)
			{
				S.Task = ETask::Assault;
				S.TaskT = 0.f;
				Emit(EEvent::Order, S.Leader, INDEX_NONE, EnemyAt, EnemyAt, 0.f, false, FString::Printf(TEXT("%s: going in"), *S.Name));
			}
		}
		break;
	}
	case ETask::Assault:
	{
		FVector EnemyAt = S.TargetPos;
		float Nearest = 1.0e9f;
		for (const int32 M : Able)
		{
			for (const FSeen& Sn : People[M].Seen)
			{
				const float D = (float)FVector::Dist(People[M].Pos, Sn.Pos);
				if (D < Nearest && Sn.AgeS < 5.f)
				{
					Nearest = D;
					EnemyAt = Sn.Pos;
				}
			}
		}
		if (Nearest > 1.0e8f && !S.bContact)
		{
			S.Task = ETask::Advance;                       // nobody left to go for: back to the objective
			S.TaskT = 0.f;
			break;
		}
		for (const int32 M : Able)
		{
			FUnit& U = People[M];
			U.Slot = INDEX_NONE;
			if (U.Act != EAct::Reload && (U.Path.IsEmpty() || FVector::Dist2D(U.Dest, EnemyAt) > 300.f))
			{
				GoTo(U, EnemyAt, Tuning.JogCmS);
			}
		}
		break;
	}
	case ETask::Hold:
	default:
	{
		// holding the objective: corners round it, facing the ways in
		HoldAround(S, S.TargetPos, 1100.f);
		break;
	}
	}
}

// ================================================================================================================== the marines

bool FAstraBoardSim::AmbushWins(const FAmbushPass::FStop& Stop, float Margin, int32& InOutRoutes) const
{
	const FBoardPortal& P = Map->GetPortals()[Stop.Portal];
	// the time by which Need marines can be at the opening, from the arrivals of each squad (the time its men are there, how many they are)
	const auto TimeOfForce = [this](TArray<TPair<float, int32>, TInlineAllocator<12>>& Arrivals) -> float
	{
		Arrivals.Sort([](const TPair<float, int32>& A, const TPair<float, int32>& B) { return A.Key < B.Key; });
		int32 Men = 0;
		for (const TPair<float, int32>& A : Arrivals)
		{
			Men += A.Value;
			if (Men >= AmbPass.Need)
			{
				return A.Key;
			}
		}
		return 1.0e9f;
	};
	// the straight line first: a place the marines could not reach in time even if they flew is not worth a search
	TArray<TPair<float, int32>, TInlineAllocator<12>> Arrivals;
	for (const FAmbushPass::FWing& W : AmbPass.Wings)
	{
		Arrivals.Emplace(W.Ready + (float)FVector::Dist(W.From, P.Pos) / Tuning.JogCmS, W.Men);
	}
	if (Stop.Theirs - TimeOfForce(Arrivals) < Margin)
	{
		return false;
	}
	Arrivals.Reset();
	for (const FAmbushPass::FWing& W : AmbPass.Wings)
	{
		TArray<FVector> Pts;
		float Metres = 0.f;
		FBoardRouteOptions Mine;
		Mine.Doors = &Doors;
		++InOutRoutes;
		if (Map->Route(W.From, P.Pos, Pts, Mine, &Metres))
		{
			Arrivals.Emplace(W.Ready + Metres * 100.f / Tuning.JogCmS, W.Men);
		}
	}
	return Stop.Theirs - TimeOfForce(Arrivals) >= Margin;
}

void FAstraBoardSim::StepAmbush()
{
	if (!Cmd.bActive || Mis.Breach == INDEX_NONE || Mis.Objective == INDEX_NONE)
	{
		return;
	}
	FAmbushPass& Pass = AmbPass;
	if (!Pass.bRunning)
	{
		if (Clock - AmbushAge < 3.0)
		{
			return;
		}
		TArray<int32> Ps;
		FBoardRouteOptions Opt;
		Opt.Doors = &Doors;
		Opt.bThroughSealed = true;
		AmbushAge = Clock;
		if (!Map->RoutePortals(Mis.BreachPos, Map->CentreOf(Mis.Objective), Ps, Opt))
		{
			AmbushIdx = INDEX_NONE;
			return;
		}
		// the marines by squad: where each leader is, how many men it brings, when it can move (the reaction team after it has armed)
		Pass.Wings.Reset();
		for (const FSquad& S : Teams)
		{
			if (S.Side != ESide::Aquila || S.bOrdered || S.Leader == INDEX_NONE || !People[S.Leader].Able())
			{
				continue;
			}
			int32 Men = 0;
			for (const int32 M : S.Members)
			{
				Men += People[M].Able() ? 1 : 0;
			}
			Pass.Wings.Add({People[S.Leader].Pos, Men, (float)Clock + S.MusterT});
		}
		// as many marines as there are boarders (the ones still to come in count)
		int32 Hostile = Pending.Num();
		for (const FUnit& U : People)
		{
			Hostile += (U.Side == ESide::Mandate && U.Able() && !U.bExternal) ? 1 : 0;
		}
		Pass.Need = FMath::Max(6, FMath::CeilToInt(Hostile * 0.8f));
		// the openings with corners along the Mandate's way, and when the boarders get to each (the bulkheads they must cut count)
		float Walked = 0.f, Cut = 0.f, FirstIn = 1.0e9f;
		FVector Prev = Mis.BreachPos;
		for (const FPending& P : Pending)
		{
			FirstIn = FMath::Min(FirstIn, P.At);
		}
		if (FirstIn > 1.0e8f)
		{
			FirstIn = (float)Clock;
		}
		Pass.Stops.Reset();
		for (const int32 Pi : Ps)
		{
			const FBoardPortal& P = Map->GetPortals()[Pi];
			Walked += (float)FVector::Dist(Prev, P.Pos);
			Prev = P.Pos;
			if (P.bDoor() && Doors.IsSealed(P.Door))
			{
				Cut += Tuning.CutS;
			}
			if ((Map->GetComps()[P.A].Slots.Num() > 0 || Map->GetComps()[P.B].Slots.Num() > 0) && !P.bVertical())
			{
				Pass.Stops.Add({Pi, FirstIn + Walked / Tuning.JogCmS + Cut});
			}
		}
		Pass.Cursor = 0;
		Pass.bKeepChecked = false;
		Pass.bRunning = true;
	}
	// a slice of the search
	int32 Routes = 0;
	const int32 Budget = 12;
	if (!Pass.bKeepChecked)
	{
		Pass.bKeepChecked = true;
		for (const FAmbushPass::FStop& Stop : Pass.Stops)
		{
			if (Stop.Portal == AmbushIdx && AmbushWins(Stop, 0.f, Routes))
			{
				Pass.bRunning = false;                     // the place they are going to still wins the race: no change of mind
				AmbushAge = Clock;
				return;
			}
		}
	}
	while (Pass.Cursor < Pass.Stops.Num())
	{
		if (AmbushWins(Pass.Stops[Pass.Cursor], 8.f, Routes))
		{
			AmbushIdx = Pass.Stops[Pass.Cursor].Portal;    // the first opening they can reach in force ahead of the boarders
			Pass.bRunning = false;
			AmbushAge = Clock;
			return;
		}
		++Pass.Cursor;
		if (Routes >= Budget && Pass.Cursor < Pass.Stops.Num())
		{
			return;                                        // the rest in the next slice
		}
	}
	// none wins the race: the way into the objective, the last opening on it
	AmbushIdx = Pass.Stops.Num() ? Pass.Stops.Last().Portal : INDEX_NONE;
	Pass.bRunning = false;
	AmbushAge = Clock;
}

bool FAstraBoardSim::PlannedRoute(TArray<FVector>& Out) const
{
	if (Mis.Breach == INDEX_NONE || Mis.Objective == INDEX_NONE)
	{
		return false;
	}
	FBoardRouteOptions Opt;
	Opt.Doors = &Doors;
	return Map->Route(Mis.BreachPos, Map->CentreOf(Mis.Objective), Out, Opt);
}

void FAstraBoardSim::PlanMarines(FSquad& S)
{
	if (S.Leader == INDEX_NONE)
	{
		return;
	}
	TArray<int32> Able;
	for (const int32 M : S.Members)
	{
		if (People[M].Able())
		{
			Able.Add(M);
		}
	}
	if (Able.IsEmpty())
	{
		return;
	}
	if (S.MusterT > 0.f)
	{
		return;                                            // the reaction team is arming itself
	}
	FUnit& L = People[S.Leader];
	ETask Task = S.Task;
	FVector At = S.TargetPos;
	float Radius = S.Radius > 0.f ? S.Radius : 700.f;
	// no order: from the alarm the marines go to the opening that wins the race against the boarders (AmbushPortal) and take its corners: the watch at once, the
	// reaction team when it has armed; a squad that runs into the boarders on the way goes in only when it has them two to one
	if (!S.bOrdered)
	{
		if (!Cmd.bActive)
		{
			return;                                        // nothing has come yet
		}
		const int32 Amb = AmbushPortal();
		const FVector Home = Amb != INDEX_NONE ? Map->GetPortals()[Amb].Pos : Map->CentreOf(Mis.Objective);
		TArray<FSeen> Seen;
			Intel(ESide::Aquila, Seen);
		float Nearest = 1.0e9f;
		FVector Enemy = Home;
		for (const FSeen& X : Seen)
		{
			const float D = (float)FVector::Dist(L.Pos, X.Pos);
			if (D < Nearest)
			{
				Nearest = D;
				Enemy = X.Pos;
			}
		}
		int32 Theirs = 0, Ours = 0;
		if (Nearest < 2200.f)
		{
			for (const FSeen& X : Seen)
			{
				Theirs += FVector::Dist(X.Pos, Enemy) < 2200.f ? 1 : 0;
			}
			for (const FUnit& U : People)
			{
				Ours += (U.Side == ESide::Aquila && U.Able() && !U.bExternal && FVector::Dist(U.Pos, L.Pos) < 3000.f) ? 1 : 0;
			}
		}
		if (Nearest < 2200.f && Theirs > 0 && Ours >= 2 * Theirs && Strength(S) >= 0.6f)
		{
			Task = ETask::Assault;
			At = Enemy;
		}
		else if (FVector::Dist2D(L.Pos, Home) > 900.f)
		{
			Task = ETask::Advance;
			At = Home;
		}
		else
		{
			Task = ETask::Hold;
			At = Home;
		}
		Radius = 800.f;
		S.TargetPos = At;
	}
	switch (Task)
	{
	case ETask::Follow:
	{
		const FUnit* C = Unit(CaptainUnit);
		if (!C)
		{
			break;
		}
		for (const int32 M : Able)
		{
			FUnit& U = People[M];
			if (U.Act == EAct::Reload)
			{
				continue;
			}
			const float D = (float)FVector::Dist2D(U.Pos, C->Pos);
			if (D > 650.f && (U.Path.IsEmpty() || FVector::Dist2D(U.Dest, C->Pos) > 300.f))
			{
				U.Slot = INDEX_NONE;
				GoTo(U, C->Pos, Tuning.JogCmS);
			}
			else if (D <= 650.f && U.Path.IsEmpty())
			{
				U.Speed = 0.f;
			}
		}
		if (!S.bContact)
		{
			HoldAround(S, C->Pos, 500.f);
		}
		break;
	}
	case ETask::Rescue:
	{
		const FUnit* C = Unit(CaptainUnit);
		if (!C)
		{
			break;
		}
		bool bNear = false;
		for (const int32 M : Able)
		{
			FUnit& U = People[M];
			bNear |= FVector::Dist(U.Pos, C->Pos) < 260.f;
			if (U.Path.IsEmpty() && FVector::Dist2D(U.Pos, C->Pos) > 200.f)
			{
				U.Slot = INDEX_NONE;
				GoTo(U, C->Pos, Tuning.JogCmS * 1.1f);
			}
		}
		if (bNear && C->Act == EAct::Down)
		{
			bool bClear = true;
			for (const FUnit& E : People)
			{
				bClear &= !(E.Side == ESide::Mandate && E.Able() && FVector::Dist(E.Pos, C->Pos) < 1400.f && Map->Visible(E.Eye(), C->Eye(), &Doors));
			}
			if (bClear)
			{
				Emit(EEvent::Rescue, S.Leader, CaptainUnit, C->Pos, C->Pos, 0.f, false, S.Name);
				++Stats.Rescues;
				S.Task = ETask::Idle;
				S.bOrdered = false;
			}
		}
		break;
	}
	case ETask::Hold:
	{
			HoldAround(S, At, Radius);
		break;
	}
	case ETask::Assault:
	{
			for (const int32 M : Able)
		{
			FUnit& U = People[M];
			U.Slot = INDEX_NONE;
			if (U.Act != EAct::Reload && (U.Path.IsEmpty() || FVector::Dist2D(U.Dest, At) > 300.f))
			{
				GoTo(U, At, Tuning.JogCmS);
			}
		}
		break;
	}
	case ETask::Advance:
	case ETask::FallBack:
	{
			if (!S.bContact || Task == ETask::FallBack)
		{
			if (FVector::Dist2D(L.Pos, At) < 500.f)
			{
				// there: they take the corners of the place
				HoldAround(S, At, Radius);
			}
			else
			{
				ColumnTo(S, At, Task == ETask::FallBack ? Tuning.JogCmS * 1.05f : Tuning.JogCmS);
			}
			break;
		}
		// contact on the way: a base of fire, and a pair round if there is a way
		FVector EnemyAt = At;
		bool bAny = false;
		float Nearest = 1.0e9f;
		for (const int32 M : Able)
		{
			for (const FSeen& Sn : People[M].Seen)
			{
				const float D = (float)FVector::Dist(People[M].Pos, Sn.Pos);
				if (D < Nearest && Sn.AgeS < 4.f)
				{
					Nearest = D;
					EnemyAt = Sn.Pos;
					bAny = true;
				}
			}
		}
		if (bAny)
		{
			if (!S.bOrdered && S.Flankers[0] == INDEX_NONE)
			{
				FlankFor(S, EnemyAt);
			}
			for (const int32 M : Able)
			{
				FUnit& U = People[M];
				if (M == S.Flankers[0] || M == S.Flankers[1] || U.Slot != INDEX_NONE || U.Act == EAct::Reload || U.Act == EAct::Peek)
				{
					continue;
				}
				if (U.Path.IsEmpty() || U.Speed < 1.f)
				{
					TakeCover(U, EnemyAt);
				}
			}
		}
		break;
	}
	default:
		break;
	}
	S.Task = S.bOrdered ? S.Task : Task;
}

// ================================================================================================================== the marines' command

void FAstraBoardSim::StepMarineCommand(float Dt)
{
	CmdT += Dt;
	if (CmdT < 1.0f)
	{
		return;
	}
	CmdT = 0.f;
	if (Cmd.bActive)
	{
		return;
	}
	// the alarm: boarders are coming (the breach is known, or the sensors see them)
	if (Stats.Spawned[1] == 0 && Mis.Breach == INDEX_NONE)
	{
		return;
	}
	Cmd.bActive = true;
	Cmd.AlarmT = (float)Clock;
	Emit(EEvent::Order, INDEX_NONE, INDEX_NONE, Mis.BreachPos, Mis.BreachPos, 0.f, false, TEXT("alarm: boarders — the marines go"));
}
