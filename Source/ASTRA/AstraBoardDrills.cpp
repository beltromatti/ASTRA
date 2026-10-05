// ASTRA — ABBORDAGGI-4: the infantry orders (docs/ABBORDAGGI.md §15.2). A squad that is given sweep, breach, take, ambush or escort runs a drill with phases of its own; the men's
// work in each phase (corners, bursts, reloads, the stairs) is still the men's (AstraBoardSim.cpp), and what a drill is worth is what the mechanics below make it (the bench says it, with and without):
//
//   take / breach / sweep   approach the door the room is entered by; STACK beside it with the door held shut (a man who is stacked does not open it: nobody inside sees them); a sealed bulkhead
//                           is CHARGED (the Mandate's torches take twenty-two seconds; a charge nine, but everyone near hears it: no surprise); then ENTRY, a man every 0.7 s, each to his corner of
//                           the room, quick on the first targets (EntryT); the men in the room who were not covering the door and not alerted are startled (StartleT); the ones who were, hold
//                           the doorway: a fatal funnel (FunnelBonus), which is what sync is for (two doors at once: the room cannot cover both); CLEAR holds the corners until nothing has been
//                           seen in the room for ClearHoldS; then the next room (sweep) or HOLD (take, breach). Squads of one sync stack at their own doors and go in at the same moment
//   ambush                  the corners of a place, fire held, the men hidden (seen only from HiddenSeeCm): the enemy that walks in is fired on all at once when he is in the killing ground in sight
//                           of half the squad, or when a man of the squad is found; the first volley is better (the men were laid on their targets) and the enemy is startled
//   seal behind (modifier)  the last man of a squad that has gone through a pressure door closes it behind them (four seconds at the console, nobody in the doorway): the enemy must cut it open
//
// Plain code over the same map and the same men: deterministic from the seed, nothing here knows a word of what the minds say.

#include "AstraBoardSim.h"

using namespace AstraBoard;

namespace
{
	constexpr float DrStackSpacingCm = 85.f;        // the men of a stack stand this far apart along the wall
	constexpr float DrNoCornerBackCm = 110.f;       // (no corner beside the door) the first man stands this far back from it, in a file
	constexpr float DrQuick = 1.15f;                // a man who goes through a door in a drill runs this much faster than the jog
	constexpr float DrEntryMaxS = 14.f;             // the men are in the room, or the squad goes on, by then
	constexpr float DrApproachQuiet = 0.9f;         // the approach to a door is a little quieter than the jog
	constexpr int32 DrMaxSweepRooms = 16;
	constexpr float DrRoomMarginCm = 100.f;         // the corners of a room a man goes to are this far off its walls
	constexpr float DrSealWaitMaxS = 8.f;           // a door with somebody in it is waited for this long, then given up
	constexpr float DrStragglerCm = 600.f;          // a man this near his place in the stack is not waited for ... if four in five are there

	/** 2D unit vector of a yaw in degrees. */
	FVector2D DrDir(float Deg)
	{
		const float R = FMath::DegreesToRadians(Deg);
		return FVector2D(FMath::Cos(R), FMath::Sin(R));
	}
}

const TCHAR* AstraBoard::DrillName(EDrill D)
{
	switch (D)
	{
	case EDrill::Approach: return TEXT("on its way to the door");
	case EDrill::Stack: return TEXT("stacked at the door");
	case EDrill::Charge: return TEXT("setting a charge on the bulkhead");
	case EDrill::Entry: return TEXT("going in");
	case EDrill::Clear: return TEXT("clearing the room");
	case EDrill::Hold: return TEXT("holding what it has taken");
	case EDrill::Spring: return TEXT("hidden, fire held");
	case EDrill::Done: return TEXT("done");
	default: return TEXT("");
	}
}

// ================================================================================================================== small things

void FAstraBoardSim::ResetDrill(FSquad& S)
{
	S.Drill = EDrill::None;
	S.DrillT = 0.f;
	S.StackPortal = S.StackComp = S.RoomTo = INDEX_NONE;
	S.Queue.Reset();
	S.Cleared.Reset();
	S.Sector.Reset();
	S.Sync = 0;
	S.CoverComp = INDEX_NONE;
	S.Door = INDEX_NONE;
	S.bFireHeld = false;
	S.bHoldInside = false;
	S.bSealBehind = false;
	S.StackedAt = S.SprungAt = S.SyncGoAt = S.EntryAt = -1.f;
	S.FirstVolleyT = 0.f;
	S.bSpotted = false;
	S.SealPortal = S.SealMan = INDEX_NONE;
	S.SealT = 0.f;
	S.SealPassed.Reset();
	S.StackSpots.Reset();
	S.ClearT = 0.f;
	S.bStackReady = false;
	S.bCharged = false;
	S.SweptHostiles = 0;
	S.Where.Reset();
	S.EscortStillT = 0.f;
	for (const int32 M : S.Members)
	{
		FUnit& U = People[M];
		U.bHidden = false;
		U.HoldDoor = INDEX_NONE;
		U.bBusy = false;
		U.bMoveFire = false;
		U.StackIdx = INDEX_NONE;
		U.GoAt = 0.f;
	}
}

bool FAstraBoardSim::Held(const FUnit& U) const
{
	return Teams.IsValidIndex(U.Squad) && Teams[U.Squad].bFireHeld;
}

void FAstraBoardSim::Announce(const FSquad& S, const FString& Text)
{
	const FVector At = S.Leader != INDEX_NONE && People.IsValidIndex(S.Leader) ? People[S.Leader].Pos : FVector::ZeroVector;
	Emit(EEvent::Drill, S.Leader, S.Id, At, At, 0.f, false, Text);
}

FString FAstraBoardSim::DrillText(const FSquad& S) const
{
	if (S.Task < ETask::Sweep)
	{
		return FString();
	}
	const auto Where = [this](int32 C) { return Map->GetComps().IsValidIndex(C) ? Map->Describe(C) : FString(TEXT("?")); };
	FString T;
	switch (S.Task)
	{
	case ETask::Sweep:
		T = FString::Printf(TEXT("sweeping %s: %d rooms cleared, %d to go%s"), S.Where.IsEmpty() ? TEXT("the place") : *S.Where, S.Cleared.Num(), S.Queue.Num() + (S.Drill == EDrill::Done ? 0 : 1),
		                    S.Drill != EDrill::None && S.Drill != EDrill::Done && S.RoomTo != INDEX_NONE ? *FString::Printf(TEXT("; now %s %s"), DrillName(S.Drill), *Where(S.RoomTo)) : TEXT(""));
		break;
	case ETask::Breach:
	case ETask::Take:
		T = FString::Printf(TEXT("%s %s: %s%s"), S.Task == ETask::Take ? TEXT("taking") : TEXT("breaching into"), S.Where.IsEmpty() ? *Where(S.RoomTo) : *S.Where, DrillName(S.Drill),
		                    S.Sync != 0 && S.Drill == EDrill::Stack ? TEXT(" (waiting for the squads of its sync)") : TEXT(""));
		break;
	case ETask::Ambush:
		T = S.SprungAt >= 0.f ? FString::Printf(TEXT("ambush at %s sprung %.0f s ago"), S.Where.IsEmpty() ? *Where(S.TargetComp) : *S.Where, (float)(Clock - S.SprungAt))
		                      : FString::Printf(TEXT("hidden at %s, fire held, %.0f s"), S.Where.IsEmpty() ? *Where(S.TargetComp) : *S.Where, S.DrillT);
		break;
	case ETask::Escort:
		T = TEXT("escorting the Captain (a man ahead, two at his sides, the rest behind)");
		break;
	default:
		break;
	}
	if (S.bFireHeld && S.Task != ETask::Ambush)
	{
		T += TEXT(", fire held");
	}
	if (S.bSealBehind)
	{
		T += TEXT(", closing the pressure doors behind");
	}
	return T;
}

/** The men of the other side near a point hear it, or are stunned by it: they are alerted (no surprise on them), and within the stun's reach they are hurt for a moment. */
void FAstraBoardSim::AlertAround(const FVector& At, float Cm, ESide Alerter, float StunS)
{
	for (FUnit& E : People)
	{
		if (E.Side == Alerter || !E.Able() || E.bExternal || E.Act == EAct::Waiting || FMath::Abs(E.Pos.Z - At.Z) > 400.f)
		{
			continue;
		}
		const float D = (float)FVector::Dist2D(E.Pos, At);
		if (D > Cm)
		{
			continue;
		}
		E.AlertT = 0.f;
		if (StunS > 0.f && D < 420.f)
		{
			E.StartleT = FMath::Max(E.StartleT, StunS);
			E.Suppression = FMath::Max(E.Suppression, 0.5f);
		}
	}
}

// ================================================================================================================== the orders

void FAstraBoardSim::OrderEx(int32 SquadId, const FOrder& O)
{
	if (!Teams.IsValidIndex(SquadId))
	{
		return;
	}
	Order(SquadId, O.Task, O.Comp, O.Pos, O.Radius, O.Note);          // (the squad's old drill is dropped there)
	FSquad& S = Teams[SquadId];
	S.Sector = O.Sector;
	S.Sync = O.Sync;
	S.CoverComp = O.CoverComp;
	S.Door = O.Door;
	S.bFireHeld = O.bFireHeld || O.Task == ETask::Ambush;
	S.bHoldInside = O.bInside;
	S.bSealBehind = O.bSealBehind;
	S.Where = O.Where;
	if (O.Task == ETask::Breach || O.Task == ETask::Take)
	{
		S.RoomTo = O.Comp;
	}
}

// ================================================================================================================== the room drills

/** The door the squad goes in by, and the compartment it stacks in (the side the room is not on). A room the leader is already in has no door to go through. */
bool FAstraBoardSim::FindEntry(FSquad& S, int32 Room, const FUnit& From)
{
	S.StackPortal = S.StackComp = INDEX_NONE;
	if (!Map->GetComps().IsValidIndex(Room))
	{
		return false;
	}
	// a door the order names (breach): the room is the side of it the leader is not on
	if (S.Task == ETask::Breach && S.Door != INDEX_NONE)
	{
		const int32 Pi = Map->PortalOfDoor(S.Door);
		if (Pi == INDEX_NONE)
		{
			return false;
		}
		const FBoardPortal& P = Map->GetPortals()[Pi];
		const double DA = FVector::DistSquared(Map->CentreOf(P.A), From.Pos), DB = FVector::DistSquared(Map->CentreOf(P.B), From.Pos);
		S.StackPortal = Pi;
		S.StackComp = DA <= DB ? P.A : P.B;
		S.RoomTo = DA <= DB ? P.B : P.A;
		return true;
	}
	if (From.Comp == Room)
	{
		return true;                                                  // already in it: no door
	}
	FBoardRouteOptions Opt;
	Opt.Doors = &Doors;
	Opt.bThroughSealed = IsAttacker(S.Side) || S.Task == ETask::Breach || S.Task == ETask::Take;
	// squads of one sync go in by doors of their own: the room cannot cover them all (the doors another squad of the sync has taken cost more)
	TArray<float> Pen;
	if (S.Sync != 0)
	{
		for (const FSquad& O : Teams)
		{
			if (O.Id != S.Id && O.Side == S.Side && O.Sync == S.Sync && O.StackPortal != INDEX_NONE && O.RoomTo == Room)
			{
				if (Pen.IsEmpty())
				{
					Pen.Init(0.f, Map->GetPortals().Num());
				}
				Pen[O.StackPortal] = 6000.f;
			}
		}
		if (Pen.Num())
		{
			Opt.PortalPenalty = &Pen;
		}
	}
	TArray<int32> Ps;
	if (!Map->RoutePortals(From.Pos, Map->CentreOf(Room), Ps, Opt) || Ps.IsEmpty())
	{
		return false;
	}
	const int32 Pi = Ps.Last();
	const FBoardPortal& P = Map->GetPortals()[Pi];
	S.StackPortal = Pi;
	S.StackComp = P.Other(Room);
	return true;
}

/** Where each man of a stack stands: along the wall either side of the door (its corners), then further along the wall; with no corner, in a file in front of it. */
void FAstraBoardSim::MakeStackSpots(FSquad& S, int32 Count)
{
	S.StackSpots.Reset();
	if (S.StackPortal == INDEX_NONE || S.StackComp == INDEX_NONE)
	{
		return;
	}
	const FBoardPortal& P = Map->GetPortals()[S.StackPortal];
	const int32 Cs = S.StackComp;
	const FVector Door = P.PosIn(Cs);
	const FVector2D Into2 = P.A == Cs ? P.Normal : -P.Normal;      // from the stack's compartment into the room
	TArray<int32, TInlineAllocator<2>> Mine;
	for (const int32 Si : Map->GetComps()[Cs].Slots)
	{
		if (Map->GetSlots()[Si].Portal == S.StackPortal)
		{
			Mine.Add(Si);
		}
	}
	for (int32 k = 0; k < Count; ++k)
	{
		FVector Spot;
		if (Mine.Num() > 0)
		{
			const FBoardSlot& Sl = Map->GetSlots()[Mine[k % Mine.Num()]];
			const double Lat = FVector2D::DotProduct(FVector2D(Sl.Pos.X - Door.X, Sl.Pos.Y - Door.Y), P.Along);
			const FVector2D Away = P.Along * (Lat >= 0.0 ? 1.0 : -1.0);              // along the wall, away from the door
			const int32 Depth = k / FMath::Max(1, Mine.Num());
			Spot = Sl.Pos + FVector(Away.X * DrStackSpacingCm * Depth, Away.Y * DrStackSpacingCm * Depth, 0.0);
		}
		else
		{
			Spot = Door - FVector(Into2.X, Into2.Y, 0.0) * (DrNoCornerBackCm + DrStackSpacingCm * k);
		}
		Spot = Map->Inset(Cs, Spot, 40.f);
		S.StackSpots.Add(Spot);
	}
}

/** The place in the room each man goes to once he is through the door: the two corners beside the door inside (the first two through go left and right), then the far corners and the walls' middles. */
void FAstraBoardSim::PickEntryDests(FSquad& S, const TArray<int32>& Men, TArray<FVector>& OutSpots, TArray<int32>& OutSlots)
{
	OutSpots.Reset();
	OutSlots.Reset();
	const int32 Room = S.RoomTo;
	if (!Map->GetComps().IsValidIndex(Room))
	{
		return;
	}
	const FBoardComp& R = Map->GetComps()[Room];
	const FVector Door = S.StackPortal != INDEX_NONE ? Map->GetPortals()[S.StackPortal].PosIn(Room) : Map->CentreOf(Room);
	// the corners beside the door, inside
	TArray<int32> Beside;
	for (const int32 Si : R.Slots)
	{
		if (S.StackPortal != INDEX_NONE && Map->GetSlots()[Si].Portal == S.StackPortal)
		{
			Beside.Add(Si);
		}
	}
	// ... then the room's four corners and the middles of its walls, the farthest from the door first
	struct FCand { FVector Pos; float Far; };
	TArray<FCand> Rest;
	const FBox& B = R.Box;
	const double M = FMath::Min(DrRoomMarginCm, 0.35 * FMath::Min(B.Max.X - B.Min.X, B.Max.Y - B.Min.Y));
	const double X0 = B.Min.X + M, X1 = B.Max.X - M, Y0 = B.Min.Y + M, Y1 = B.Max.Y - M;
	const double Xm = 0.5 * (X0 + X1), Ym = 0.5 * (Y0 + Y1);
	const FVector Pts[] = {FVector(X0, Y0, B.Min.Z), FVector(X1, Y0, B.Min.Z), FVector(X0, Y1, B.Min.Z), FVector(X1, Y1, B.Min.Z), FVector(Xm, Y0, B.Min.Z), FVector(Xm, Y1, B.Min.Z), FVector(X0, Ym, B.Min.Z), FVector(X1, Ym, B.Min.Z)};
	for (const FVector& P : Pts)
	{
		const FVector Q = Map->Inset(Room, P, 55.f);
		Rest.Add({Q, (float)FVector::Dist2D(Q, Door)});
	}
	Rest.Sort([](const FCand& A, const FCand& C) { return A.Far > C.Far; });
	for (int32 i = 0; i < Men.Num(); ++i)
	{
		if (i < Beside.Num())
		{
			OutSlots.Add(Beside[i]);
			OutSpots.Add(Map->GetSlots()[Beside[i]].Pos);
			continue;
		}
		// the next place that is not taken (a metre from the others)
		FVector Pick = Map->Inset(Room, Map->CentreOf(Room), 70.f);
		for (const FCand& C : Rest)
		{
			bool bTaken = false;
			for (const FVector& T : OutSpots)
			{
				bTaken |= FVector::Dist2D(T, C.Pos) < 100.0;
			}
			if (!bTaken)
			{
				Pick = C.Pos;
				break;
			}
		}
		OutSlots.Add(INDEX_NONE);
		OutSpots.Add(Pick);
	}
}

void FAstraBoardSim::DrillSweepNext(FSquad& S)
{
	S.StackPortal = S.StackComp = INDEX_NONE;
	S.StackSpots.Reset();
	S.StackedAt = S.EntryAt = S.SyncGoAt = -1.f;
	S.bStackReady = false;
	S.bCharged = false;
	S.ClearT = 0.f;
	for (const int32 M : S.Members)
	{
		People[M].HoldDoor = INDEX_NONE;
		People[M].StackIdx = INDEX_NONE;
	}
	if (S.Queue.Num() > 0)
	{
		S.RoomTo = S.Queue[0];
		S.Queue.RemoveAt(0);
		S.Drill = EDrill::None;                                       // (the next step finds its door)
		S.DrillT = 0.f;
		return;
	}
	S.Drill = EDrill::Done;
	S.RoomTo = INDEX_NONE;
	Announce(S, FString::Printf(TEXT("%s has swept %s: %d rooms clear"), *S.Name, S.Where.IsEmpty() ? TEXT("the place") : *S.Where, S.Cleared.Num()));
}

void FAstraBoardSim::DrillRoom(FSquad& S, const TArray<int32>& Able)
{
	const FUnit& L = People[S.Leader];
	// the squad's sync: its mates that are still in the room drill
	// ---- begin
	if (S.Drill == EDrill::None)
	{
		if (S.Task == ETask::Sweep && S.RoomTo == INDEX_NONE)
		{
			// the rooms of the place nearest first, each from the one before
			TArray<int32> Rooms;
			if (S.Sector.Num() > 0)
			{
				for (const int32 C : S.Sector)
				{
					if (Map->GetComps().IsValidIndex(C) && !Map->GetComps()[C].bCorridor && !Map->GetComps()[C].bHall)
					{
						Rooms.AddUnique(C);
					}
				}
			}
			if (Rooms.IsEmpty() && Map->GetComps().IsValidIndex(S.TargetComp))
			{
				Rooms.Add(S.TargetComp);
			}
			FVector From = L.Pos;
			while (Rooms.Num() > 0 && S.Queue.Num() < DrMaxSweepRooms)
			{
				int32 Best = 0;
				double BestD = TNumericLimits<double>::Max();
				for (int32 i = 0; i < Rooms.Num(); ++i)
				{
					const double D = FVector::Dist2D(Map->CentreOf(Rooms[i]), From) + FMath::Abs(Map->CentreOf(Rooms[i]).Z - From.Z) * 6.0;
					if (D < BestD)
					{
						BestD = D;
						Best = i;
					}
				}
				S.Queue.Add(Rooms[Best]);
				From = Map->CentreOf(Rooms[Best]);
				Rooms.RemoveAtSwap(Best);
			}
			DrillSweepNext(S);
			if (S.Drill == EDrill::Done)
			{
				return;
			}
		}
		else if (S.RoomTo == INDEX_NONE)
		{
			S.RoomTo = S.TargetComp;
		}
		if (!FindEntry(S, S.RoomTo, L))
		{
			// no way to it (a sealed bulkhead the squad may not cut, a deck with no way down): the squad says so and holds where it is
			Announce(S, FString::Printf(TEXT("%s has no way to %s"), *S.Name, Map->GetComps().IsValidIndex(S.RoomTo) ? *Map->Describe(S.RoomTo) : TEXT("the place")));
			if (S.Task == ETask::Sweep && S.Queue.Num() > 0)
			{
				DrillSweepNext(S);
			}
			else
			{
				S.Drill = EDrill::Done;
			}
			return;
		}
		S.Drill = S.StackPortal == INDEX_NONE ? EDrill::Entry : EDrill::Approach;                // (already in the room: no door)
		S.DrillT = 0.f;
		if (S.Drill == EDrill::Entry)
		{
			S.EntryAt = (float)Clock;
			for (const int32 M : Able)
			{
				People[M].DrillSpot = People[M].Pos;                    // (they clear the room they are in where they stand)
				People[M].StackIdx = INDEX_NONE;
				People[M].GoAt = 0.f;
			}
		}
	}
	const FBoardPortal* P = S.StackPortal != INDEX_NONE ? &Map->GetPortals()[S.StackPortal] : nullptr;
	const int32 DoorIdx = P && P->bDoor() ? P->Door : INDEX_NONE;
	// the men by their place in the stack: the nearest to the door first
	const auto Assign = [&]()
	{
		if (!P)
		{
			return;
		}
		const FVector At = P->PosIn(S.StackComp);
		TArray<int32> Order = Able;
		Order.Sort([&](int32 A, int32 B) { return FVector::DistSquared(People[A].Pos, At) < FVector::DistSquared(People[B].Pos, At); });
		for (int32 i = 0; i < Order.Num(); ++i)
		{
			People[Order[i]].StackIdx = i;
		}
		if (S.StackSpots.Num() < Order.Num())
		{
			MakeStackSpots(S, Order.Num());
		}
	};
	switch (S.Drill)
	{
	case EDrill::Approach:
	{
		if (S.StackSpots.Num() < Able.Num() || (Able.Num() > 0 && People[Able[0]].StackIdx == INDEX_NONE))
		{
			Assign();
		}
		int32 Near = 0;
		for (const int32 M : Able)
		{
			FUnit& U = People[M];
			if (U.StackIdx == INDEX_NONE || !S.StackSpots.IsValidIndex(U.StackIdx) || U.bBusy)
			{
				continue;
			}
			const FVector Spot = S.StackSpots[U.StackIdx];
			const float D = (float)FVector::Dist2D(U.Pos, Spot);
			if (D < Tuning.StackReadyCm)
			{
				++Near;
				U.HoldDoor = DoorIdx;                                   // (at the door: it is not opened for them to be seen through)
			}
			if (D > Tuning.StackReadyCm * 0.5f && U.Path.IsEmpty() && U.Target == INDEX_NONE && U.Act != EAct::Reload)
			{
				U.Slot = INDEX_NONE;
				GoTo(U, Spot, Tuning.JogCmS * DrApproachQuiet);
			}
		}
		if (Near > 0)
		{
			S.Drill = EDrill::Stack;
			S.DrillT = 0.f;
		}
		break;
	}
	case EDrill::Stack:
	case EDrill::Charge:
	{
		if (S.StackSpots.Num() < Able.Num() || (Able.Num() > 0 && People[Able[0]].StackIdx == INDEX_NONE))
		{
			Assign();
		}
		int32 Ready = 0, Close = 0;
		for (const int32 M : Able)
		{
			FUnit& U = People[M];
			if (U.StackIdx == INDEX_NONE || !S.StackSpots.IsValidIndex(U.StackIdx))
			{
				continue;
			}
			const FVector Spot = S.StackSpots[U.StackIdx];
			const float D = (float)FVector::Dist2D(U.Pos, Spot);
			Close += D < DrStragglerCm ? 1 : 0;
			if (D < Tuning.StackReadyCm)
			{
				++Ready;
				U.HoldDoor = DoorIdx;
				if (U.Path.IsEmpty())
				{
					U.Speed = 0.f;
				}
			}
			else if (U.Path.IsEmpty() && U.Target == INDEX_NONE && U.Act != EAct::Reload)
			{
				U.Slot = INDEX_NONE;
				GoTo(U, Spot, Tuning.JogCmS * DrApproachQuiet);
			}
		}
		// all of them at their places, or four in five with the last one coming (a stack does not wait for a man who is a few metres off: he joins it as it goes in)
		const bool bAll = Ready >= Able.Num() || (Ready * 5 >= Able.Num() * 4 && Close >= Able.Num());
		const bool bLate = S.DrillT > Tuning.StackMaxWaitS;
		S.bStackReady = (bAll || bLate) && Ready > 0;
		if (S.bStackReady && S.StackedAt < 0.f)
		{
			S.StackedAt = (float)Clock;
			Announce(S, FString::Printf(TEXT("%s is stacked at %s, ready to go in"), *S.Name, P && P->bDoor() ? *Map->Describe(S.StackComp) : TEXT("the opening")));
		}
		if (!S.bStackReady)
		{
			break;
		}
		// a sealed bulkhead: the charge (everyone near hears it)
		if (P && P->bDoor() && Doors.IsSealed(P->Door) && !S.bCharged)
		{
			if (S.Drill != EDrill::Charge)
			{
				S.Drill = EDrill::Charge;
				S.DrillT = 0.f;
				AlertAround(P->Pos, Tuning.BreachNoiseCm, S.Side, 0.f);
				Announce(S, FString::Printf(TEXT("%s is setting a charge on the bulkhead at %s"), *S.Name, *Map->Describe(S.StackComp)));
			}
			else if (S.DrillT >= Tuning.BreachChargeS)
			{
				Doors.Sealed[P->Door] = false;
				Doors.ClosedBy[P->Door] = -1;
				++Stats.DrillCharges;
				S.bCharged = true;
				S.Drill = EDrill::Stack;
				S.DrillT = 0.f;
				AlertAround(P->Pos, Tuning.BreachNoiseCm, S.Side, Tuning.BreachStunS);
				Emit(EEvent::Cut, INDEX_NONE, P->Door, P->Pos, FVector::ZeroVector, 0.f, false, FString::Printf(TEXT("%s charged the bulkhead at %s"), *S.Name, *Map->Describe(S.StackComp)));
			}
			break;
		}
		// the squads of its sync go in together: the first moment all of them are stacked (or the wait is up) fixes the time for all
		if (S.Sync != 0)
		{
			if (S.SyncGoAt < 0.f)
			{
				bool bAllReady = true;
				float FirstStacked = (float)Clock;
				for (const FSquad& O : Teams)
				{
					if (O.Side != S.Side || O.Sync != S.Sync || O.Leader == INDEX_NONE || !People[O.Leader].Able())
					{
						continue;
					}
					if (O.Task < ETask::Sweep || O.Drill == EDrill::Approach || O.Drill == EDrill::None || ((O.Drill == EDrill::Stack || O.Drill == EDrill::Charge) && !O.bStackReady))
					{
						bAllReady = false;                              // one of them is not at its door yet
					}
					if (O.StackedAt >= 0.f)
					{
						FirstStacked = FMath::Min(FirstStacked, O.StackedAt);
					}
				}
				if (bAllReady || Clock - FirstStacked > Tuning.SyncMaxWaitS)
				{
					const float GoAt = (float)Clock + 1.0f;
					for (FSquad& O : Teams)
					{
						if (O.Side == S.Side && O.Sync == S.Sync && O.SyncGoAt < 0.f)
						{
							O.SyncGoAt = GoAt;
						}
					}
					Announce(S, FString::Printf(TEXT("%s: all of sync %d are at their doors: in together"), *S.Name, S.Sync));
				}
			}
			if (S.SyncGoAt < 0.f || Clock < S.SyncGoAt)
			{
				break;                                                  // the door is held shut, the men wait
			}
		}
		// in: a man every EntryGapS, each to his place in the room
		S.Drill = EDrill::Entry;
		S.DrillT = 0.f;
		S.EntryAt = (float)Clock;
		TArray<int32> Men = Able;
		Men.Sort([&](int32 A, int32 B) { return People[A].StackIdx < People[B].StackIdx; });
		TArray<FVector> Spots;
		TArray<int32> Slots;
		PickEntryDests(S, Men, Spots, Slots);
		const float Base = S.Sync != 0 && S.SyncGoAt > 0.f ? S.SyncGoAt : (float)Clock;          // (the squads of a sync go at the one moment, not at the moment each looks)
		for (int32 i = 0; i < Men.Num(); ++i)
		{
			FUnit& U = People[Men[i]];
			U.GoAt = Base + 0.2f + i * Tuning.EntryGapS;
			U.DrillSpot = Spots[i];
			U.Slot = INDEX_NONE;
			U.StackIdx = Slots[i];                                      // (from now on the slot he goes to, or none)
		}
		Announce(S, FString::Printf(TEXT("%s is going in at %s"), *S.Name, *Map->Describe(S.RoomTo)));
		break;
	}
	case EDrill::Entry:
	{
		int32 Inside = 0, Started = 0;
		for (const int32 M : Able)
		{
			FUnit& U = People[M];
			if (U.bBusy)
			{
				continue;
			}
			Inside += U.Comp == S.RoomTo ? 1 : 0;
			if (U.GoAt > 0.f && Clock >= U.GoAt)
			{
				// his turn: the door is his to open, and he is quick on his first targets
				U.GoAt = -1.f;
				U.HoldDoor = INDEX_NONE;
				U.EntryT = Tuning.EntryS;
				U.Slot = INDEX_NONE;
				if (U.Comp != S.RoomTo || FVector::Dist2D(U.Pos, U.DrillSpot) > 90.f)
				{
					GoTo(U, U.DrillSpot, Tuning.JogCmS * DrQuick);
				}
				if (S.EntryAt >= 0.f)
				{
					S.EntryAt = -1.f;                                   // (the door is gone through: counted once)
					++Stats.DrillEntries;
				}
			}
			Started += U.GoAt <= 0.f ? 1 : 0;
			if (U.GoAt <= 0.f && U.Path.IsEmpty() && U.Target == INDEX_NONE && U.Act != EAct::Reload && FVector::Dist2D(U.Pos, U.DrillSpot) > 90.f && !U.bAtPeek)
			{
				GoTo(U, U.DrillSpot, Tuning.JogCmS * DrQuick);          // (stopped by a fight on the way: on again)
			}
		}
		if (Inside >= FMath::Max(1, (Able.Num() * 7) / 10) && Started >= Able.Num() || S.DrillT > DrEntryMaxS)
		{
			S.Drill = EDrill::Clear;
			S.DrillT = 0.f;
			S.ClearT = 0.f;
			for (const int32 M : Able)
			{
				FUnit& U = People[M];
				if (U.StackIdx != INDEX_NONE && Map->GetSlots().IsValidIndex(U.StackIdx))
				{
					U.Slot = U.StackIdx;                                // (the corner he went to: he holds it)
					U.bAtPeek = false;
					U.CycleT = Rng.FRandRange(0.2f, 0.9f);
				}
			}
		}
		break;
	}
	case EDrill::Clear:
	{
		// nothing seen in the room, the men at their corners: clear after ClearHoldS
		bool bHot = false;
		for (const int32 M : Able)
		{
			for (const FSeen& Sn : People[M].Seen)
			{
				if (Sn.AgeS < 2.5f && People.IsValidIndex(Sn.Unit) && People[Sn.Unit].Able() && Map->CompAt(Sn.Pos) == S.RoomTo)
				{
					bHot = true;
				}
			}
		}
		for (const int32 M : Able)
		{
			FUnit& U = People[M];
			if (U.bBusy || U.Target != INDEX_NONE || U.Act == EAct::Reload)
			{
				continue;
			}
			if (U.Slot != INDEX_NONE)
			{
				if (U.Path.IsEmpty() && FVector::Dist2D(U.Pos, Map->GetSlots()[U.Slot].Pos) > 45.f && !U.bAtPeek)
				{
					GoTo(U, Map->GetSlots()[U.Slot].Pos, Tuning.CoverCmS);
				}
			}
			else if (U.Path.IsEmpty() && FVector::Dist2D(U.Pos, U.DrillSpot) > 90.f)
			{
				GoTo(U, U.DrillSpot, Tuning.CoverCmS);
			}
		}
		S.ClearT = bHot ? 0.f : S.ClearT + 0.5f;
		if (S.ClearT >= Tuning.ClearHoldS)
		{
			S.Cleared.Add(S.RoomTo);
			++Stats.DrillRooms;
			Announce(S, FString::Printf(TEXT("%s has cleared %s"), *S.Name, *Map->Describe(S.RoomTo)));
			if (S.Task == ETask::Sweep)
			{
				DrillSweepNext(S);
			}
			else
			{
				S.Drill = EDrill::Hold;
				S.DrillT = 0.f;
			}
		}
		break;
	}
	case EDrill::Hold:
	{
		if (Map->GetComps().IsValidIndex(S.RoomTo))
		{
			HoldAround(S, Map->CentreOf(S.RoomTo), 1100.f, true);
		}
		break;
	}
	default:
		break;
	}
}

// ================================================================================================================== the ambush

void FAstraBoardSim::DrillAmbush(FSquad& S, const TArray<int32>& Able)
{
	if (S.Drill == EDrill::None)
	{
		S.Drill = EDrill::Spring;
		S.DrillT = 0.f;
		S.bFireHeld = true;
	}
	const float Radius = S.Radius > 0.f ? S.Radius : 700.f;
	if (S.Drill == EDrill::Spring)
	{
		// the corners of the place (each man a corner of his own, the ones that look the way the enemy comes first), and there hidden
		HoldAround(S, S.TargetPos, Radius, false);
		int32 Kill = 0, Seers = 0;
		for (const int32 M : Able)
		{
			FUnit& U = People[M];
			// each at the step-out of his corner (where he can see and fire at once); hidden from beyond HiddenSeeCm
			if (U.Slot != INDEX_NONE && U.Path.IsEmpty() && FVector::Dist2D(U.Pos, Map->GetSlots()[U.Slot].Peek) > 45.f && U.Act != EAct::Reload)
			{
				GoTo(U, Map->GetSlots()[U.Slot].Peek, Tuning.CoverCmS);
			}
			U.bHidden = U.Path.IsEmpty() && U.Speed < 1.f && (U.Slot == INDEX_NONE || FVector::Dist2D(U.Pos, Map->GetSlots()[U.Slot].Peek) < 60.f);        // (still, at his post)
			bool bSees = false;
			for (const FSeen& Sn : U.Seen)
			{
				if (Sn.bVisibleNow && People.IsValidIndex(Sn.Unit) && People[Sn.Unit].Able() && FVector::Dist2D(People[Sn.Unit].Pos, S.TargetPos) < Tuning.AmbushKillCm)
				{
					bSees = true;
					++Kill;
				}
			}
			Seers += bSees ? 1 : 0;
		}
		const bool bSprung = (Kill > 0 && Seers * 2 >= Able.Num()) || S.bSpotted;
		if (bSprung)
		{
			S.bFireHeld = false;
			S.SprungAt = (float)Clock;
			S.FirstVolleyT = Tuning.AmbushFirstS;
			S.Drill = EDrill::Hold;
			S.DrillT = 0.f;
			++Stats.DrillAmbushes;
			for (const int32 M : Able)
			{
				FUnit& U = People[M];
				U.bHidden = false;
				U.AcquireT = 0.f;
				U.FireT = 0.f;
				U.bAtPeek = true;                                        // (he is at the step-out already: firing at once)
				U.CycleT = Tuning.PeekS * 1.6f;
				for (const FSeen& Sn : U.Seen)
				{
					if (People.IsValidIndex(Sn.Unit) && Sn.bVisibleNow)
					{
						People[Sn.Unit].StartleT = FMath::Max(People[Sn.Unit].StartleT, Tuning.AmbushStartleS);
						People[Sn.Unit].AlertT = 0.f;
					}
				}
			}
			Announce(S, FString::Printf(TEXT("%s has sprung the ambush at %s%s"), *S.Name, S.Where.IsEmpty() ? *Map->Describe(S.TargetComp) : *S.Where, S.bSpotted ? TEXT(" (found: they open fire)") : TEXT("")));
		}
		else if (S.DrillT > Tuning.AmbushMaxS)
		{
			S.bFireHeld = false;
			S.Drill = EDrill::Hold;
			S.DrillT = 0.f;
			for (const int32 M : Able)
			{
				People[M].bHidden = false;
			}
			Announce(S, FString::Printf(TEXT("%s gives up the ambush at %s: nobody came; they hold it with their fire free"), *S.Name, S.Where.IsEmpty() ? *Map->Describe(S.TargetComp) : *S.Where));
		}
		return;
	}
	HoldAround(S, S.TargetPos, Radius, false);
}

// ================================================================================================================== escort

void FAstraBoardSim::DrillEscort(FSquad& S, const TArray<int32>& Able)
{
	const FUnit* C = Unit(CaptainUnit);
	if (!C)
	{
		return;
	}
	S.Drill = EDrill::Hold;
	// the way he is going: from where he was half a second ago, else the way he faces
	const FVector2D Moved(C->Pos.X - S.EscortLast.X, C->Pos.Y - S.EscortLast.Y);
	if (S.EscortLast.IsZero() || Moved.Size() < 20.0)
	{
		S.EscortStillT += 0.5f;
	}
	else
	{
		S.EscortStillT = 0.f;
		S.EscortDir = Moved.GetSafeNormal();
	}
	if (S.EscortLast.IsZero())
	{
		S.EscortDir = DrDir(C->Yaw);
	}
	S.EscortLast = C->Pos;
	// standing: the corners round him, facing the openings of his room
	if (S.EscortStillT >= 1.5f)
	{
		for (const int32 M : Able)
		{
			People[M].bMoveFire = false;
		}
		HoldAround(S, C->Pos, 520.f);
		return;
	}
	const FVector2D Fwd = S.EscortDir, Side(-Fwd.Y, Fwd.X);
	TArray<int32> Men = Able;
	Men.Sort([](int32 A, int32 B) { return A < B; });
	const bool bWalking = S.EscortStillT < 0.5f;
	for (int32 i = 0; i < Men.Num(); ++i)
	{
		FUnit& U = People[Men[i]];
		U.bMoveFire = bWalking;                                          // (while he walks they walk and shoot: a bodyguard who stops to fight is a man left behind; when he stands they hold)
		if (U.bBusy || U.Act == EAct::Reload || (U.Target != INDEX_NONE && !bWalking))
		{
			continue;                                                    // (a man who is firing keeps firing when the Captain stands: the formation closes up again after)
		}
		FVector2D Want;
		if (i == 0)
		{
			Want = FVector2D(C->Pos.X, C->Pos.Y) + Fwd * Tuning.EscortPointCm;                              // the point: ahead, where he looks past each opening first
		}
		else if (i <= 2)
		{
			Want = FVector2D(C->Pos.X, C->Pos.Y) + Fwd * 60.0 + Side * (i == 1 ? 230.0 : -230.0);           // the sides
		}
		else
		{
			Want = FVector2D(C->Pos.X, C->Pos.Y) - Fwd * (320.0 + 160.0 * (i - 3));                         // the rear
		}
		FVector Spot(Want.X, Want.Y, C->Pos.Z);
		// a place in the ship: pulled back towards him until it is one
		for (int32 k = 0; k < 6 && Map->CompAt(Spot, 60.f) == INDEX_NONE; ++k)
		{
			Spot = FMath::Lerp(Spot, C->Pos, 0.25);
		}
		const int32 Cs = Map->CompAt(Spot, 60.f);
		if (Cs != INDEX_NONE)
		{
			Spot = Map->Inset(Cs, Spot, 50.f);
		}
		U.Slot = INDEX_NONE;
		if (FVector::Dist2D(U.Pos, Spot) > (i == 0 ? 160.f : 130.f) && (U.Path.IsEmpty() || FVector::Dist(U.Dest, Spot) > 220.f))
		{
			GoTo(U, Spot, Tuning.JogCmS * 1.1f);
		}
	}
}

// ================================================================================================================== close the pressure doors behind

void FAstraBoardSim::StepSealBehind(FSquad& S, const TArray<int32>& Able)
{
	// the way the squad goes: from its leader to the place it is going to (a fall back, a withdrawal, an advance)
	if (S.Leader == INDEX_NONE || Able.IsEmpty())
	{
		return;
	}
	const FUnit& L = People[S.Leader];
	if (S.SealPortal == INDEX_NONE)
	{
		FVector Goal = S.TargetPos;
		if (S.Task == ETask::Withdraw)
		{
			Goal = BreachPosOf(S);
		}
		if (Goal.IsZero() || FVector::Dist2D(L.Pos, Goal) < 600.f)
		{
			return;
		}
		FBoardRouteOptions Opt;
		Opt.Doors = &Doors;
		Opt.bThroughSealed = false;
		TArray<int32> Ps;
		if (!Map->RoutePortals(L.Pos, Goal, Ps, Opt))
		{
			return;
		}
		for (const int32 Pi : Ps)
		{
			const FBoardPortal& P = Map->GetPortals()[Pi];
			if (P.Kind == FBoardPortal::EKind::Blast && !Doors.IsSealed(P.Door))
			{
				S.SealPortal = Pi;
				S.SealMan = INDEX_NONE;
				S.SealT = 0.f;
				S.SealPassed.Reset();
				break;
			}
		}
		return;
	}
	const FBoardPortal& P = Map->GetPortals()[S.SealPortal];
	// which side is the way on? the side the leader's goal is on is the far side: a man is through when he is in the compartment beyond it (or has been)
	const FVector Goal = S.Task == ETask::Withdraw ? BreachPosOf(S) : S.TargetPos;
	const int32 Far = FVector::DistSquared(Map->CentreOf(P.A), Goal) <= FVector::DistSquared(Map->CentreOf(P.B), Goal) ? P.A : P.B;
	const int32 Near = P.Other(Far);
	for (const int32 M : Able)
	{
		if (People[M].Comp == Far && !S.SealPassed.Contains(M))
		{
			S.SealPassed.Add(M);
		}
	}
	if (Doors.IsSealed(P.Door))
	{
		S.SealPortal = INDEX_NONE;                                    // somebody has closed it already
		return;
	}
	int32 Behind = 0;
	for (const int32 M : Able)
	{
		Behind += (!S.SealPassed.Contains(M) && !People[M].bBusy) ? 1 : 0;
	}
	if (S.SealMan == INDEX_NONE)
	{
		// the last man through is the one who closes it: when all the others are through (the ones who fell stay where they are)
		int32 Pick = INDEX_NONE;
		for (const int32 M : Able)
		{
			if (S.SealPassed.Contains(M) && People[M].Comp == Far && FVector::Dist2D(People[M].Pos, P.PosIn(Far)) < 420.f)
			{
				Pick = Pick == INDEX_NONE || FVector::DistSquared(People[M].Pos, P.Pos) < FVector::DistSquared(People[Pick].Pos, P.Pos) ? M : Pick;
			}
		}
		if (Behind == 0 && Pick != INDEX_NONE)
		{
			S.SealMan = Pick;
			S.SealT = 0.f;
			FUnit& U = People[Pick];
			U.bBusy = true;
			U.Slot = INDEX_NONE;
			GoTo(U, Map->Inset(Far, P.PosIn(Far), 60.f), Tuning.JogCmS * 1.1f);
		}
		else if (Behind == 0 && Pick == INDEX_NONE)
		{
			S.SealPortal = INDEX_NONE;                                // nobody to do it
		}
		return;
	}
	FUnit& U = People[S.SealMan];
	if (!U.Able())
	{
		U.bBusy = false;
		S.SealMan = INDEX_NONE;
		S.SealPortal = INDEX_NONE;
		return;
	}
	if (FVector::Dist2D(U.Pos, P.PosIn(Far)) > 140.f)
	{
		if (U.Path.IsEmpty())
		{
			GoTo(U, Map->Inset(Far, P.PosIn(Far), 60.f), Tuning.JogCmS * 1.1f);
		}
		return;
	}
	S.SealT += 0.5f;
	if (S.SealT < Tuning.SealS)
	{
		U.Speed = 0.f;
		return;
	}
	// closed: unless somebody is in the doorway (a friend of his or the enemy: nobody is shut in a door)
	bool bBlocked = false;
	for (const FUnit& X : People)
	{
		if (X.Act != EAct::Dead && X.Act != EAct::Gone && X.Act != EAct::Waiting && X.Id != U.Id && FVector::Dist2D(X.Pos, P.Pos) < Tuning.SealClearCm && FMath::Abs(X.Pos.Z - P.Pos.Z) < 250.f)
		{
			bBlocked = true;
			break;
		}
	}
	if (bBlocked && S.SealT < Tuning.SealS + DrSealWaitMaxS)
	{
		return;
	}
	U.bBusy = false;
	if (!bBlocked)
	{
		Doors.Sealed[P.Door] = true;
		Doors.ClosedBy[P.Door] = (int8)S.Side;
		++Stats.DrillSeals;
		Emit(EEvent::Sealed, U.Id, P.Door, P.Pos, P.Pos, 0.f, false, FString::Printf(TEXT("%s closed the bulkhead at %s behind them"), *S.Name, *Map->Describe(Near)));
	}
	S.SealMan = INDEX_NONE;
	S.SealPortal = INDEX_NONE;
	U.Path.Reset();
}

// ================================================================================================================== the squad's step

void FAstraBoardSim::StepDrill(FSquad& S, const TArray<int32>& Able)
{
	switch (S.Task)
	{
	case ETask::Sweep:
	case ETask::Breach:
	case ETask::Take:
		DrillRoom(S, Able);
		break;
	case ETask::Ambush:
		DrillAmbush(S, Able);
		break;
	case ETask::Escort:
		DrillEscort(S, Able);
		break;
	default:
		break;
	}
}
