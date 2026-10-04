// ASTRA — VITA, the life simulation (see AstraLifeSim.h).

#include "AstraLifeSim.h"

#include "ASTRA.h"
#include "AstraShipSubsystem.h"
#include "HAL/PlatformTime.h"

// ====================================================================================================== routes

FAstraLifeRoute::ESeg FAstraLifeRoute::Kind(int32 S) const
{
	const FVector3f& A = Pts[S];
	const FVector3f& B = Pts[S + 1];
	if (FMath::Abs(B.Z - A.Z) < 150.f)
	{
		return ESeg::Walk;
	}
	return FVector2f::Distance(FVector2f(A.X, A.Y), FVector2f(B.X, B.Y)) < 150.f ? ESeg::Stair : ESeg::Lift;
}

float FAstraLifeRoute::SegSeconds(int32 S, float SpeedCmS, const FAstraLifeSpeed& Sp) const
{
	switch (Kind(S))
	{
	case ESeg::Stair: return Sp.StairsS * FMath::Clamp(Sp.WalkCmS / FMath::Max(SpeedCmS, 30.f), 0.45f, 1.5f);
	case ESeg::Lift:  return Sp.LiftS;
	default:          return FMath::Max(0.05f, FVector3f::Dist(Pts[S], Pts[S + 1]) / FMath::Max(SpeedCmS, 30.f));
	}
}

void FAstraLifeRoute::Advance(float Dt, float SpeedCmS, const FAstraLifeSpeed& Sp)
{
	while (Dt > 0.f && !Done())
	{
		const float T = SegSeconds(Seg, SpeedCmS, Sp);
		const float Left = (1.f - F) * T;
		if (Dt < Left)
		{
			F += Dt / T;
			return;
		}
		Dt -= Left;
		++Seg;
		F = 0.f;
	}
}

FVector FAstraLifeRoute::Position() const
{
	if (Pts.Num() == 0)
	{
		return FVector::ZeroVector;
	}
	if (Done())
	{
		return FVector(Pts.Last());
	}
	if (Kind(Seg) == ESeg::Lift)
	{
		return FVector(Pts[Seg]);                       // in the car: still at the landing it went in by
	}
	return FVector(FMath::Lerp(Pts[Seg], Pts[Seg + 1], F));
}

FVector2D FAstraLifeRoute::Heading() const
{
	// the direction of the segment they are on; a stair or a lift has none, so the last one that had
	for (int32 S = FMath::Min(Seg, Pts.Num() - 2); S >= 0; --S)
	{
		const FVector2D D(Pts[S + 1].X - Pts[S].X, Pts[S + 1].Y - Pts[S].Y);
		if (D.SizeSquared() > 25.0)
		{
			return D.GetSafeNormal();
		}
	}
	return FVector2D::ZeroVector;
}

float FAstraLifeRoute::RemainingCm() const
{
	float L = 0.f;
	for (int32 S = Seg; S + 1 < Pts.Num(); ++S)
	{
		L += FVector3f::Dist(Pts[S], Pts[S + 1]) * (S == Seg ? 1.f - F : 1.f);
	}
	return L;
}

// ====================================================================================================== helpers

namespace
{
	FString Pad2(int32 V) { return FString::Printf(TEXT("%02d"), V); }

	/** Weighted pick of an index (a weight of 0 or less never wins); INDEX_NONE when nothing has weight. */
	int32 PickWeighted(const TArray<float>& W, FRandomStream& R)
	{
		double Sum = 0.0;
		for (const float X : W)
		{
			Sum += FMath::Max(0.f, X);
		}
		if (Sum <= 0.0)
		{
			return INDEX_NONE;
		}
		double T = R.FRand() * Sum;
		for (int32 i = 0; i < W.Num(); ++i)
		{
			if (W[i] > 0.f && (T -= W[i]) <= 0.0)
			{
				return i;
			}
		}
		for (int32 i = W.Num() - 1; i >= 0; --i)
		{
			if (W[i] > 0.f)
			{
				return i;
			}
		}
		return INDEX_NONE;
	}

	bool IsPost(EAstraPlaceKind K)
	{
		return K == EAstraPlaceKind::Work || K == EAstraPlaceKind::Stand || K == EAstraPlaceKind::Sit || K == EAstraPlaceKind::Watch;
	}

	constexpr int32 NoEpisode = MIN_int32;
	constexpr double StepPeriodS = 1.0;      // every person is thought about about once a second of game time
}

uint32 FAstraLifeSim::Hash(int32 A, int32 B, int32 C) const
{
	uint32 H = HashCombineFast((uint32)Seed * 2654435761u, (uint32)A + 0x9e3779b9u);
	H = HashCombineFast(H, (uint32)B * 40503u + 17u);
	H = HashCombineFast(H, (uint32)C * 2246822519u + 5u);
	return H;
}

FString FAstraLifeSim::HourText(double ShipSec)
{
	const int32 M = (int32)FMath::Fmod(ShipSec / 60.0, 1440.0);
	return Pad2(M / 60) + TEXT(":") + Pad2(M % 60);
}

FString FAstraLifeSim::MemoryLine(const FAstraLifeMemory& M) const
{
	const double Ago = FMath::Max(0.0, Clock - M.T);
	FString When;
	if (Ago < 20.0 * 60.0)
	{
		When = TEXT("a few minutes ago");
	}
	else if (Ago < 3.0 * 3600.0)
	{
		When = FString::Printf(TEXT("about %d minutes ago"), FMath::RoundToInt(Ago / 600.0) * 10);
	}
	else if (Ago < 30.0 * 3600.0)
	{
		When = FString::Printf(TEXT("about %d hours ago"), FMath::RoundToInt(Ago / 3600.0));
	}
	else
	{
		When = FString::Printf(TEXT("%d days ago"), FMath::RoundToInt(Ago / 86400.0));
	}
	return FString::Printf(TEXT("%s (%s, ship time %s)"), *M.Text, *When, *HourText(M.T));
}

void FAstraLifeSim::Remember(int32 Person, uint8 Weight, const FString& Text)
{
	if (!People.IsValidIndex(Person) || People[Person].Status == 2)
	{
		return;
	}
	TArray<FAstraLifeMemory>& Mem = People[Person].Mem;
	for (const FAstraLifeMemory& M : Mem)
	{
		if (M.Text == Text)
		{
			return;
		}
	}
	Mem.Add({Clock, Weight, Text});
	while (Mem.Num() > 8)
	{
		// the weakest, oldest memory goes first: what they will not forget stays
		int32 Drop = 0;
		for (int32 i = 1; i < Mem.Num(); ++i)
		{
			if (Mem[i].Weight < Mem[Drop].Weight)
			{
				Drop = i;
			}
		}
		Mem.RemoveAt(Drop);
	}
}

void FAstraLifeSim::RememberNear(int32 CompIdx, float RadiusCm, uint8 Weight, const FString& Text, int32 Except)
{
	if (!Map.IsValid() || !Map->Comps.IsValidIndex(CompIdx))
	{
		return;
	}
	const FVector C = Map->Comps[CompIdx].Box.GetCenter();
	for (int32 i = 0; i < People.Num(); ++i)
	{
		if (i != Except && FMath::Abs(People[i].Pos.Z - C.Z) < 450.f && FVector::Dist2D(People[i].Pos, C) < RadiusCm)
		{
			Remember(i, Weight, Text);
		}
	}
}

// ====================================================================================================== init

void FAstraLifeSim::Init(TSharedRef<const FAstraLifeMap> InMap, const FAstraCrewRoster& Roster, int32 InSeed, float StartHour)
{
	Map = InMap;
	Seed = InSeed;
	People.Reset();
	PartyList.Reset();
	Queue.Reset();
	Queued.Reset();
	Fails.Reset();
	KnownIncidents.Reset();
	SectionBoxes.Reset();
	Counters = FAstraLifeStats();
	Occ.Init(0, Map->Places.Num());
	Holder.Init(INDEX_NONE, Map->Places.Num());
	MedbayComp = Map->CompByName.FindRef(FName(TEXT("medbay")), INDEX_NONE);
	MessComp = Map->CompByName.FindRef(FName(TEXT("mess")), INDEX_NONE);
	ExternalPlace.Reset();
	for (int32 i = 0; i < Map->Places.Num(); ++i)
	{
		if (Map->Places[i].External != NAME_None)
		{
			ExternalPlace.Add(Map->Places[i].External, i);
		}
	}
	LeisureRooms.Reset();
	for (const FAstraLifeLeisure& L : Map->Leisure)
	{
		TArray<int32>& Rooms = LeisureRooms.AddDefaulted_GetRef();
		for (const FName K : L.Kinds)
		{
			if (const TArray<int32>* C = Map->CompsByKind.Find(K))
			{
				for (const int32 CI : *C)
				{
					if (!Map->Comps[CI].bWalled && Map->Comps[CI].Hub != INDEX_NONE)
					{
						Rooms.Add(CI);
					}
				}
			}
		}
	}
	AlertLevel = 0;
	AlertSerial = 0;
	GameT = 0.0;
	Clock = (double)StartHour * 3600.0;
	RosterRev = -1;
	Cursor = 0;
	SliceAcc = 0.f;

	const TArray<FAstraCrewman>& R = Roster.Get();
	People.SetNum(R.Num());
	Queued.Init(0, R.Num());
	RosterToPerson.Init(INDEX_NONE, R.Num());
	static FAstraLifeDept Generic;
	if (Generic.Name.IsEmpty())
	{
		Generic.Name = TEXT("crew");
		Generic.Job = TEXT("crewman");
	}
	for (int32 i = 0; i < R.Num(); ++i)
	{
		FAstraLifePerson& P = People[i];
		P.Roster = i;
		RosterToPerson[i] = i;
		const FAstraLifeDept* D = Map->Depts.Find(R[i].Dept);
		P.Dept = D ? D : &Generic;
		P.Class = P.Dept->Class;
		P.bFemale = R[i].bFemale;
		P.Status = R[i].Status;
		P.Bed = R[i].Bed;
		P.Job = P.Dept->Job;
		P.Taste.SetNum(Map->Leisure.Num());
		P.Episode = NoEpisode;
	}
	FRandomStream Rng = Stream(1);
	AssignWatches(Roster, Rng);
	for (int32 i = 0; i < People.Num(); ++i)
	{
		FAstraLifePerson& P = People[i];
		FRandomStream S = Stream(i, 77);
		auto Draw = [&S](const FVector2D& V) { return (float)FMath::Lerp(V.X, V.Y, (double)S.FRand()); };
		P.J[0] = Draw(Map->Day.J1);
		P.J[1] = Draw(Map->Day.J2);
		P.J[2] = Draw(Map->Day.J3);
		P.J[3] = Draw(Map->Day.J4);
		P.J[4] = Draw(Map->Day.JSleep);
		P.SpeedFactor = 1.f + (S.FRand() * 2.f - 1.f) * Map->Speed.Spread;
		P.WakeDelayS = (float)FMath::Lerp(Map->Day.WakeDelayS.X, Map->Day.WakeDelayS.Y, (double)S.FRand());
		for (int32 k = 0; k < Map->Leisure.Num(); ++k)
		{
			P.Taste[k] = (float)FMath::Lerp(Map->Leisure[k].Taste.X, Map->Leisure[k].Taste.Y, (double)S.FRand());
		}
	}
	AssignPosts();
	// the job in words fits the rank: an officer in a department of ratings leads its division (a lieutenant in the stores is the supply
	// officer, never a "storekeeper"; an ensign at a galley station is the mess officer, not a cook); a rating among the staff officers is
	// their clerk or yeoman.
	for (int32 i = 0; i < People.Num(); ++i)
	{
		FAstraLifePerson& P = People[i];
		const FString& Rank = R[i].Rank;
		const bool bOfficerRank = Rank == TEXT("Ensign") || Rank.StartsWith(TEXT("Lieutenant")) || Rank == TEXT("Commander");
		const bool bOfficerDept = P.Class == EAstraLifeClass::Officer;
		if (P.Class == EAstraLifeClass::Marine || bOfficerRank == bOfficerDept || !Map->Places.IsValidIndex(P.Duty))
		{
			continue;
		}
		const int32 Room = Map->Places[P.Duty].Comp;
		const FName Kind = Map->Comps.IsValidIndex(Room) ? Map->Comps[Room].Kind : NAME_None;
		if (bOfficerRank)
		{
			const FString* J = Map->OfficerJobByRoom.Find(Kind);
			P.Job = J ? *J : FString::Printf(TEXT("%s division officer"), *R[i].Dept);
		}
		else
		{
			const FString* J = Map->JobByRoom.Find(Kind);
			P.Job = J && !J->Contains(TEXT("officer")) ? *J : FString(TEXT("yeoman"));
		}
	}
	AssignHomes();
	AssignBattle();
	// friends: colleagues of their department (two of their own watch), the people they see most
	TMap<FString, TArray<int32>> ByDept;
	for (int32 i = 0; i < People.Num(); ++i)
	{
		ByDept.FindOrAdd(R[i].Dept).Add(i);
	}
	for (int32 i = 0; i < People.Num(); ++i)
	{
		FRandomStream S = Stream(i, 91);
		const TArray<int32>& Mates = ByDept.FindOrAdd(R[i].Dept);
		int32 N = 0;
		for (int32 Try = 0; Try < 40 && N < 3 && Mates.Num() > 3; ++Try)
		{
			const int32 J = Mates[S.RandHelper(Mates.Num())];
			const bool bSameWatch = People[J].Watch == People[i].Watch;
			if (J != i && (bSameWatch || N == 2) && People[i].Friends[0] != J && People[i].Friends[1] != J)
			{
				People[i].Friends[N++] = J;
			}
		}
	}
	SetHour(StartHour);
}

void FAstraLifeSim::AssignWatches(const FAstraCrewRoster& Roster, FRandomStream& R)
{
	TMap<FString, TArray<int32>> ByDept;
	for (int32 i = 0; i < People.Num(); ++i)
	{
		ByDept.FindOrAdd(Roster.Get()[i].Dept).Add(i);
	}
	const int32 NW = FMath::Max(1, Map->Watches.Num());
	// the departments in a fixed order (a map's order is not), each split evenly over the watches
	TArray<FString> Names;
	ByDept.GetKeys(Names);
	Names.Sort();
	int32 Offset = 0;
	for (const FString& Name : Names)
	{
		TArray<int32>& L = ByDept[Name];
		for (int32 n = L.Num() - 1; n > 0; --n)
		{
			L.Swap(n, R.RandHelper(n + 1));
		}
		for (int32 k = 0; k < L.Num(); ++k)
		{
			People[L[k]].Watch = (uint8)((k + Offset) % NW);
		}
		Offset += L.Num() % NW;      // the odd ones of each department fall on different watches
	}
}

bool FAstraLifeSim::RoomMatches(const FAstraLifeComp& C, const FAstraLifeSelector& S) const
{
	if (C.bWalled || C.bCorridor || C.Hub == INDEX_NONE || !S.Kinds.Contains(C.Kind))
	{
		return false;
	}
	if (S.Dept != NAME_None && C.Dept != S.Dept)
	{
		return false;
	}
	if (S.Decks.Num() && !S.Decks.Contains((int32)C.Deck))
	{
		return false;
	}
	return true;
}

void FAstraLifeSim::RoomsOf(const FAstraLifeSelector& Sel, TArray<int32>& Out) const
{
	Out.Reset();
	for (const FName K : Sel.Kinds)
	{
		if (const TArray<int32>* L = Map->CompsByKind.Find(K))
		{
			for (const int32 CI : *L)
			{
				if (RoomMatches(Map->Comps[CI], Sel))
				{
					Out.Add(CI);
				}
			}
		}
	}
}

int32 FAstraLifeSim::PostIn(int32 Comp, int32 Watch, TArray<uint8>* Used, FRandomStream& R) const
{
	// a free post of the room (not one a named character keeps), else its heart
	const FAstraLifeComp& C = Map->Comps[Comp];
	TArray<int32> Free;
	for (const int32 P : C.Places)
	{
		const FAstraLifePlace& Pl = Map->Places[P];
		if (IsPost(Pl.Kind) && Pl.External == NAME_None && (!Used || !((*Used)[P] & (1 << Watch))))
		{
			Free.Add(P);
		}
	}
	return Free.Num() ? Free[R.RandHelper(Free.Num())] : C.Hub;
}

void FAstraLifeSim::AssignPosts()
{
	const int32 NW = FMath::Clamp(Map->Watches.Num(), 1, 8);
	TArray<uint8> UsedPost;                              // per place, a bit per watch
	UsedPost.Init(0, Map->Places.Num());
	TArray<TArray<float>> RoomLoad;                      // per watch, per room: people already posted there
	RoomLoad.SetNum(NW);
	for (TArray<float>& L : RoomLoad)
	{
		L.Init(0.f, Map->Comps.Num());
	}
	struct FPool { TArray<TArray<int32>> Rooms; TArray<float> Weight; };
	TMap<const FAstraLifeDept*, FPool> Pools;
	for (const auto& KV : Map->Depts)
	{
		FPool& Pool = Pools.Add(&KV.Value);
		for (const FAstraLifeSelector& Sel : KV.Value.Duty)
		{
			TArray<int32>& Rooms = Pool.Rooms.AddDefaulted_GetRef();
			RoomsOf(Sel, Rooms);
			Pool.Weight.Add(Rooms.Num() ? Sel.Weight : 0.f);
		}
	}
	for (int32 Idx = 0; Idx < People.Num(); ++Idx)
	{
		FAstraLifePerson& P = People[Idx];
		const FPool* Pool = Pools.Find(P.Dept);
		if (!Pool)
		{
			continue;
		}
		FRandomStream S = Stream(Idx, 31);
		const int32 Sel = PickWeighted(Pool->Weight, S);
		if (Sel == INDEX_NONE)
		{
			continue;
		}
		const TArray<int32>& Rooms = Pool->Rooms[Sel];
		TArray<float> W;
		W.SetNum(Rooms.Num());
		for (int32 i = 0; i < Rooms.Num(); ++i)
		{
			const FAstraLifeComp& C = Map->Comps[Rooms[i]];
			W[i] = FMath::Max(0.08f, (float)FMath::Max(1, C.Slots) - RoomLoad[P.Watch][Rooms[i]]) * Map->StatusWeight[(int32)C.Status];
		}
		const int32 Pick = PickWeighted(W, S);
		if (Pick == INDEX_NONE)
		{
			continue;
		}
		const int32 Room = Rooms[Pick];
		RoomLoad[P.Watch][Room] += 1.f;
		const int32 Post = PostIn(Room, P.Watch, &UsedPost, S);
		P.Duty = Post;
		if (Post != INDEX_NONE && Map->Places[Post].Kind != EAstraPlaceKind::Hub)
		{
			UsedPost[Post] |= (uint8)(1 << P.Watch);
		}
		// the job in words: the post's own role, else what the room is for, else the department's
		const FAstraLifePlace& Pl = Map->Places[Post != INDEX_NONE ? Post : Map->Comps[Room].Hub];
		if (Pl.Role != NAME_None)
		{
			P.Job = Pl.Role.ToString();
		}
		else if (const FString* J = Map->JobByRoom.Find(Map->Comps[Room].Kind))
		{
			P.Job = *J;
		}
	}
}

void FAstraLifeSim::AssignBattle()
{
	TArray<float> Load;
	Load.Init(0.f, Map->Comps.Num());
	TMap<const FAstraLifeDept*, TArray<TArray<int32>>> Cache;
	for (int32 Idx = 0; Idx < People.Num(); ++Idx)
	{
		FAstraLifePerson& P = People[Idx];
		if (!P.Dept || P.Dept->Battle.Num() == 0)
		{
			P.Battle = P.Duty;
			continue;
		}
		TArray<TArray<int32>>* Rooms = Cache.Find(P.Dept);
		if (!Rooms)
		{
			Rooms = &Cache.Add(P.Dept);
			for (const FAstraLifeSelector& Sel : P.Dept->Battle)
			{
				RoomsOf(Sel, Rooms->AddDefaulted_GetRef());
			}
		}
		FRandomStream S = Stream(Idx, 37);
		TArray<float> SelW;
		for (int32 k = 0; k < Rooms->Num(); ++k)
		{
			SelW.Add((*Rooms)[k].Num() ? P.Dept->Battle[k].Weight : 0.f);
		}
		const int32 Sel = PickWeighted(SelW, S);
		if (Sel == INDEX_NONE)
		{
			P.Battle = P.Duty;
			continue;
		}
		TArray<float> W;
		for (const int32 CI : (*Rooms)[Sel])
		{
			const FAstraLifeComp& C = Map->Comps[CI];
			W.Add(FMath::Max(0.1f, (float)FMath::Max(1, C.Slots) * 2.f - Load[CI]) * Map->StatusWeight[(int32)C.Status]);
		}
		const int32 Pick = PickWeighted(W, S);
		const int32 Room = (*Rooms)[Sel][FMath::Max(0, Pick)];
		Load[Room] += 1.f;
		P.Battle = PostIn(Room, 0, nullptr, S);
	}
}

void FAstraLifeSim::AssignHomes()
{
	const int32 NW = FMath::Clamp(Map->Watches.Num(), 1, 4);
	struct FUse { int32 Watch[4] = {0, 0, 0, 0}; int32 Total = 0; };
	TArray<FUse> Use;
	Use.SetNum(Map->Comps.Num());
	auto SleepCapacity = [this](const FAstraLifeComp& C)
	{
		int32 N = 0;
		for (const int32 P : C.Places)
		{
			N += Map->Places[P].Kind == EAstraPlaceKind::Sleep ? 1 : 0;
		}
		return N > 0 ? N : FMath::Max(1, C.Slots);
	};
	TMap<int32, TArray<int32>> Cache;                    // class -> every room that could be a home
	auto HomeRooms = [&](EAstraLifeClass Cl) -> const TArray<int32>&
	{
		if (TArray<int32>* C = Cache.Find((int32)Cl))
		{
			return *C;
		}
		TArray<int32>& C = Cache.Add((int32)Cl);
		const TArray<FAstraLifeSelector>& Sels = Cl == EAstraLifeClass::Marine ? Map->HomeMarine : Cl == EAstraLifeClass::Officer ? Map->HomeOfficer : Map->HomeRating;
		TArray<int32> L;
		for (const FAstraLifeSelector& Sel : Sels)
		{
			RoomsOf(Sel, L);
			for (const int32 CI : L)
			{
				C.AddUnique(CI);
			}
		}
		return C;
	};
	// people are housed in an order that depends on nothing but the seed
	TArray<int32> Order;
	for (int32 i = 0; i < People.Num(); ++i)
	{
		Order.Add(i);
	}
	FRandomStream S = Stream(2);
	for (int32 n = Order.Num() - 1; n > 0; --n)
	{
		Order.Swap(n, S.RandHelper(n + 1));
	}
	for (const int32 Idx : Order)
	{
		FAstraLifePerson& P = People[Idx];
		const TArray<int32>& Rooms = HomeRooms(P.Class);
		const FAstraLifePlace* DutyPl = P.Duty != INDEX_NONE ? &Map->Places[P.Duty] : nullptr;
		const FVector From = DutyPl ? DutyPl->Pos : FVector::ZeroVector;
		const int32 FromDeck = DutyPl ? DutyPl->Deck : 4;
		int32 Best = INDEX_NONE;
		float BestScore = TNumericLimits<float>::Max();
		for (const int32 CI : Rooms)
		{
			const FAstraLifeComp& C = Map->Comps[CI];
			const int32 Cap = SleepCapacity(C);
			// a room holds its bunks per watch, and the watches share them (two at most): the watch that is up has the bunk
			if (Use[CI].Watch[FMath::Min<int32>(P.Watch, NW - 1)] >= Cap || Use[CI].Total >= Cap * 2)
			{
				continue;
			}
			const FAstraLifePlace& H = Map->Places[C.Hub];
			float Score = (float)(FVector::Dist2D(From, H.Pos) + 1800.0 * FMath::Abs(H.Deck - FromDeck));
			if (C.Kind == TEXT("berthing"))
			{
				Score *= P.Watch == 0 ? 0.35f : 1.6f;        // the ratings of the Red watch sleep in the Crew Berthing, as its sign says
			}
			Score *= Use[CI].Watch[FMath::Min<int32>(P.Watch, NW - 1)] > 0 ? 0.85f : 1.f;   // cabin-mates share a watch
			if (Score < BestScore)
			{
				BestScore = Score;
				Best = CI;
			}
		}
		if (Best == INDEX_NONE && Rooms.Num())
		{
			Best = Rooms[S.RandHelper(Rooms.Num())];         // every bunk taken: a cot in a room of their kind
		}
		P.Home = Best;
		if (Best != INDEX_NONE)
		{
			++Use[Best].Watch[FMath::Min<int32>(P.Watch, NW - 1)];
			++Use[Best].Total;
		}
		// how long before a block they must set out: the walk in ship hours, and a margin (a day is short on the clock and a walk is long)
		auto LeadHours = [this, &P](const FAstraLifePlace& A, const FAstraLifePlace& B)
		{
			const double Metres = FVector::Dist2D(A.Pos, B.Pos) / 100.0 * 1.35 + 28.0 * FMath::Abs(A.Deck - B.Deck) + 25.0;
			const double Seconds = Metres / (Map->Speed.WalkCmS * P.SpeedFactor / 100.0);
			return (float)FMath::Clamp(Seconds * Map->TimeScale / 3600.0 * 1.15 + 0.06, 0.08, 1.4);
		};
		if (P.Home != INDEX_NONE && DutyPl)
		{
			const FAstraLifePlace& H = Map->Places[Map->Comps[P.Home].Hub];
			P.LeadH = LeadHours(H, *DutyPl);
			if (MessComp != INDEX_NONE)
			{
				const FAstraLifePlace& Mess = Map->Places[Map->Comps[MessComp].Hub];
				P.LeadMessHomeH = LeadHours(H, Mess);
				P.LeadMessDutyH = LeadHours(*DutyPl, Mess);
			}
		}
	}
}

// ====================================================================================================== the clock and the day

void FAstraLifeSim::SetHour(float H)
{
	Clock = FMath::FloorToDouble(Clock / 86400.0) * 86400.0 + (double)H * 3600.0;
	Occ.Init(0, Map->Places.Num());
	Holder.Init(INDEX_NONE, Map->Places.Num());
	Queue.Reset();
	Queued.Init(0, People.Num());
	for (int32 i = 0; i < People.Num(); ++i)
	{
		FAstraLifePerson& P = People[i];
		P.Claimed = INDEX_NONE;
		P.Episode = NoEpisode;
		P.Phase = FAstraLifePerson::EPhase::Settled;
		P.Route.Clear();
		P.LastStep = GameT;
		P.bBody = false;
		P.Party = INDEX_NONE;
		P.Act = EAstraLifeAct::Duty;
	}
	PartyList.Reset();
	KnownIncidents.Reset();
	for (int32 i = 0; i < People.Num(); ++i)
	{
		FAstraLifePerson& P = People[i];
		if (P.Status == 2)
		{
			P.Act = EAstraLifeAct::Dead;
			continue;
		}
		Begin(i, Decide(P), true);
	}
}

void FAstraLifeSim::BlockAt(const FAstraLifePerson& P, double Sec, EAstraLifeAct& Act, int32& Block, int32& Cycle) const
{
	const FAstraLifeDay& D = Map->Day;
	const double Start = Map->Watches.IsValidIndex(P.Watch) ? Map->Watches[P.Watch].Start : 0.0;
	const double Rel = Sec / 3600.0 - Start + P.LeadH;           // hours since they set out for this cycle's duty
	const double Cyc = FMath::FloorToDouble(Rel / 24.0);
	const float U = (float)(Rel - Cyc * 24.0) - P.LeadH;         // hours since the watch began (negative while they walk to it)
	Cycle = (int32)Cyc;
	// the meals are sat down to at T1, T4 and T7 and last MealLen; whoever has a walk to the Mess sets out that much earlier
	const float T1 = D.DutyFirst + P.J[0];
	const float T1s = FMath::Max(0.6f, T1 - P.LeadMessDutyH);
	const float T2 = T1 + D.MealLen;
	const float T3 = 8.f;
	const float T4 = T3 + D.WindDown + P.J[1];
	const float T4s = FMath::Max(T3 + 0.05f, T4 - P.LeadMessHomeH);
	const float T5 = T4 + D.MealLen;
	// sleep: from about the twelfth hour of the watch for about seven and a half, but never so late that there is no time to wake, eat and walk to the post
	const float T7max = 24.f - P.LeadH - D.MealLen;
	const float Sleep1 = FMath::Min(FMath::Max(T5 + 0.3f, D.SleepStart + P.J[2]) + D.SleepLen + P.J[4], T7max - P.LeadMessHomeH - 0.1f);
	const float Sleep0 = FMath::Max(T5 + 0.3f, FMath::Min(D.SleepStart + P.J[2], Sleep1 - 5.f));
	const float T7 = FMath::Clamp(D.MealBefore + P.J[3], Sleep1 + 0.1f + P.LeadMessHomeH, T7max);
	const float T7s = FMath::Max(Sleep1 + 0.05f, T7 - P.LeadMessHomeH);
	const float T8 = FMath::Min(T7 + D.MealLen, 24.f - P.LeadH);
	if (U < T1s)         { Act = EAstraLifeAct::Duty;    Block = 0; }
	else if (U < T2)     { Act = EAstraLifeAct::Meal;    Block = 1; }
	else if (U < T3)     { Act = EAstraLifeAct::Duty;    Block = 2; }
	else if (U < T4s)    { Act = EAstraLifeAct::Leisure; Block = 3; }
	else if (U < T5)     { Act = EAstraLifeAct::Meal;    Block = 4; }
	else if (U < Sleep0) { Act = EAstraLifeAct::Leisure; Block = 5; }
	else if (U < Sleep1) { Act = EAstraLifeAct::Sleep;   Block = 6; }
	else if (U < T7s)    { Act = EAstraLifeAct::Leisure; Block = 7; }
	else if (U < T8)     { Act = EAstraLifeAct::Meal;    Block = 8; }
	else                 { Act = EAstraLifeAct::Leisure; Block = 9; }       // up and dressed, a little time before the walk to the post
}

EAstraLifeAct FAstraLifeSim::ScheduleAt(int32 Person, double ShipSec, int32* OutBlock) const
{
	EAstraLifeAct Act;
	int32 Block, Cycle;
	BlockAt(People[Person], ShipSec, Act, Block, Cycle);
	if (OutBlock)
	{
		*OutBlock = Block;
	}
	return Act;
}

FAstraLifeSim::FDesire FAstraLifeSim::Decide(const FAstraLifePerson& P) const
{
	if (P.Status == 2)
	{
		return {EAstraLifeAct::Dead, 90000000};
	}
	if (P.Status == 1)
	{
		return {EAstraLifeAct::Patient, 80000000 + P.Roster * 4 + FMath::Clamp(P.Bed + 1, 0, 3)};
	}
	if (P.Party != INDEX_NONE)
	{
		return {EAstraLifeAct::Repair, 70000000 + P.Party};
	}
	EAstraLifeAct Act;
	int32 Block, Cycle;
	BlockAt(P, Clock, Act, Block, Cycle);
	if (AlertLevel == 2)
	{
		return {EAstraLifeAct::Battle, 60000000 + AlertSerial};
	}
	if (AlertLevel == 1 && P.Dept && P.Dept->bYellow && Act != EAstraLifeAct::Sleep)
	{
		return {EAstraLifeAct::Duty, 50000000 + AlertSerial};
	}
	return {Act, Cycle * 16 + Block};
}

// ====================================================================================================== places and claims

bool FAstraLifeSim::Claim(FAstraLifePerson& P, int32 Idx, int32 PlaceIdx)
{
	if (!Map->Places.IsValidIndex(PlaceIdx))
	{
		return false;
	}
	const FAstraLifePlace& Pl = Map->Places[PlaceIdx];
	if (Pl.Kind != EAstraPlaceKind::Hub && Occ[PlaceIdx] >= Pl.Capacity)
	{
		return false;
	}
	++Occ[PlaceIdx];
	Holder[PlaceIdx] = Idx;
	P.Claimed = PlaceIdx;
	P.Place = PlaceIdx;
	return true;
}

void FAstraLifeSim::Release(FAstraLifePerson& P, int32 Idx)
{
	if (P.Claimed != INDEX_NONE)
	{
		Occ[P.Claimed] = (int16)FMath::Max(0, Occ[P.Claimed] - 1);
		if (Holder[P.Claimed] == Idx)
		{
			Holder[P.Claimed] = INDEX_NONE;
		}
		P.Claimed = INDEX_NONE;
	}
}

FVector FAstraLifeSim::SpotAt(int32 PlaceIdx, int32 Slot, float& OutYaw) const
{
	const FAstraLifePlace& Pl = Map->Places[PlaceIdx];
	if (Pl.Kind != EAstraPlaceKind::Hub)
	{
		OutYaw = Pl.Yaw;
		return Pl.Pos;
	}
	// a room's heart holds several: they stand in rings round it (golden-angle packing), kept inside the walls
	const FAstraLifeComp& C = Map->Comps[Pl.Comp];
	FRandomStream R((int32)Hash(PlaceIdx, Slot, 5));
	const float Ang = Slot * 2.39996f + R.FRand() * 0.5f;
	const float Rad = Slot == 0 ? 50.f * R.FRand() : 75.f * FMath::Sqrt((float)Slot) + 25.f * R.FRand();
	FVector P = Pl.Pos + FVector(FMath::Cos(Ang) * Rad, FMath::Sin(Ang) * Rad, 0.0);
	const float M = 70.f;
	if (C.Box.Max.X - C.Box.Min.X > 2 * M) { P.X = FMath::Clamp(P.X, C.Box.Min.X + M, C.Box.Max.X - M); }
	if (C.Box.Max.Y - C.Box.Min.Y > 2 * M) { P.Y = FMath::Clamp(P.Y, C.Box.Min.Y + M, C.Box.Max.Y - M); }
	OutYaw = R.FRand() * 360.f - 180.f;
	return P;
}

int32 FAstraLifeSim::FreePlaceIn(int32 Comp, const TFunction<bool(const FAstraLifePlace&)>& Want, FRandomStream& R) const
{
	TArray<int32> Free;
	for (const int32 P : Map->Comps[Comp].Places)
	{
		const FAstraLifePlace& Pl = Map->Places[P];
		if (Occ[P] < Pl.Capacity && Want(Pl))
		{
			Free.Add(P);
		}
	}
	return Free.Num() ? Free[R.RandHelper(Free.Num())] : INDEX_NONE;
}

void FAstraLifeSim::TargetPlace(FAstraLifePerson& P, int32 Idx, int32 PlaceIdx)
{
	if (!Map->Places.IsValidIndex(PlaceIdx))
	{
		P.Target = P.Pos;                                    // nowhere to go: they stay
		P.Place = INDEX_NONE;
		return;
	}
	if (!Claim(P, Idx, PlaceIdx))
	{
		// a seat or post that is taken: the heart of the room takes one more
		PlaceIdx = Map->Comps[Map->Places[PlaceIdx].Comp].Hub;
		if (!Claim(P, Idx, PlaceIdx))
		{
			P.Target = P.Pos;
			return;
		}
	}
	const FAstraLifePlace& Pl = Map->Places[PlaceIdx];
	float Yaw = Pl.Yaw;
	P.Target = SpotAt(PlaceIdx, FMath::Max(0, (int32)Occ[PlaceIdx] - 1), Yaw);
	P.TargetYaw = Yaw;
	P.TargetHeight = Pl.Height;
	P.TargetKind = Pl.Kind;
}

void FAstraLifeSim::TargetBunk(FAstraLifePerson& P, int32 Idx, FRandomStream& R)
{
	int32 Choice = INDEX_NONE;
	// a bunk is any sleeping place but the Medbay's beds (those are the wounded's)
	const auto IsBunk = [](const FAstraLifePlace& Pl) { return Pl.Kind == EAstraPlaceKind::Sleep && !Pl.External.ToString().StartsWith(TEXT("patient")); };
	if (P.Bunk != INDEX_NONE && Occ[P.Bunk] < Map->Places[P.Bunk].Capacity)
	{
		Choice = P.Bunk;                                     // the one they had, if it is free
	}
	if (Choice == INDEX_NONE && P.Home != INDEX_NONE)
	{
		Choice = FreePlaceIn(P.Home, IsBunk, R);
	}
	if (Choice == INDEX_NONE && P.Home != INDEX_NONE)
	{
		// the watch before them has not left: another room of the same kind, the nearest with a free bunk
		if (const TArray<int32>* Kin = Map->CompsByKind.Find(Map->Comps[P.Home].Kind))
		{
			double Best = TNumericLimits<double>::Max();
			for (const int32 CI : *Kin)
			{
				const double D = FVector::Dist(Map->Comps[CI].Box.GetCenter(), Map->Comps[P.Home].Box.GetCenter());
				if (D < Best && !Map->Comps[CI].bWalled)
				{
					const int32 F = FreePlaceIn(CI, IsBunk, R);
					if (F != INDEX_NONE)
					{
						Best = D;
						Choice = F;
					}
				}
			}
		}
	}
	if (Choice == INDEX_NONE && P.Home != INDEX_NONE)
	{
		Choice = Map->Comps[P.Home].Hub;                     // a cot: the heart of their room
	}
	if (Choice != INDEX_NONE && Map->Places[Choice].Kind == EAstraPlaceKind::Sleep)
	{
		P.Bunk = Choice;
	}
	TargetPlace(P, Idx, Choice);
}

void FAstraLifeSim::TargetMeal(FAstraLifePerson& P, int32 Idx, FRandomStream& R)
{
	// The Mess Hall seats them at its tables. When it is full a meal is taken at a lounge table or on a bench (a plate on the knees: the other
	// kinds of the list), and only when there is no seat anywhere a plate standing in the nearest of those halls.
	const auto IsTable = [](const FAstraLifePlace& Pl) { return Pl.Kind == EAstraPlaceKind::Eat; };
	const auto IsBench = [](const FAstraLifePlace& Pl) { return (Pl.Kind == EAstraPlaceKind::Eat || Pl.Kind == EAstraPlaceKind::Sit) && Pl.External == NAME_None; };
	int32 Choice = INDEX_NONE;
	int32 Stand = INDEX_NONE;
	double StandBest = TNumericLimits<double>::Max();
	for (int32 K = 0; K < Map->MealKinds.Num() && Choice == INDEX_NONE; ++K)
	{
		const TArray<int32>* Kin = Map->CompsByKind.Find(Map->MealKinds[K]);
		if (!Kin)
		{
			continue;
		}
		// the nearest room of the kind with a free seat (the Mess Hall first: it is the first of the kinds)
		double Best = TNumericLimits<double>::Max();
		for (const int32 CI : *Kin)
		{
			const FAstraLifeComp& C = Map->Comps[CI];
			if (C.bWalled)
			{
				continue;
			}
			const double D = FVector::Dist(C.Box.GetCenter(), P.Pos);
			if (C.Status != EAstraRoomStatus::Planned && C.Hub != INDEX_NONE && D < StandBest)
			{
				StandBest = D;
				Stand = C.Hub;
			}
			if (D < Best)
			{
				const int32 F = FreePlaceIn(CI, K == 0 ? TFunction<bool(const FAstraLifePlace&)>(IsTable) : TFunction<bool(const FAstraLifePlace&)>(IsBench), R);
				if (F != INDEX_NONE)
				{
					Best = D;
					Choice = F;
				}
			}
		}
	}
	if (Choice == INDEX_NONE)
	{
		Choice = Stand != INDEX_NONE ? Stand : (MessComp != INDEX_NONE ? Map->Comps[MessComp].Hub : INDEX_NONE);
	}
	TargetPlace(P, Idx, Choice);
}

void FAstraLifeSim::TargetLeisure(FAstraLifePerson& P, int32 Idx, FRandomStream& R)
{
	TArray<float> W;
	W.SetNum(Map->Leisure.Num());
	for (int32 k = 0; k < W.Num(); ++k)
	{
		const bool bHome = Map->Leisure[k].Kinds.Num() == 1 && Map->Leisure[k].Kinds[0] == FName(TEXT("__home"));
		W[k] = bHome ? (P.Home != INDEX_NONE ? P.Taste[k] : 0.f) : (LeisureRooms[k].Num() ? P.Taste[k] : 0.f);
	}
	for (int32 Try = 0; Try < 4; ++Try)
	{
		const int32 K = PickWeighted(W, R);
		if (K == INDEX_NONE)
		{
			break;
		}
		const bool bHome = Map->Leisure[K].Kinds.Num() == 1 && Map->Leisure[K].Kinds[0] == FName(TEXT("__home"));
		if (bHome)
		{
			P.LeisureKind = K;
			TargetPlace(P, Idx, Map->Comps[P.Home].Hub);
			return;
		}
		// a room of that kind, near them and with room in it
		TArray<float> RW;
		for (const int32 CI : LeisureRooms[K])
		{
			const FAstraLifeComp& C = Map->Comps[CI];
			const double Dist = FVector::Dist(C.Box.GetCenter(), P.Pos);
			RW.Add((float)FMath::Max(1, C.Slots) * Map->StatusWeight[(int32)C.Status] / (1.f + (float)Dist / 8000.f));
		}
		const int32 Pick = PickWeighted(RW, R);
		if (Pick == INDEX_NONE)
		{
			W[K] = 0.f;
			continue;
		}
		const int32 Room = LeisureRooms[K][Pick];
		const auto IsSpot = [](const FAstraLifePlace& Pl) { return Pl.Kind == EAstraPlaceKind::Sit || Pl.Kind == EAstraPlaceKind::Stand || Pl.Kind == EAstraPlaceKind::Watch; };
		int32 Place = FreePlaceIn(Room, [&IsSpot](const FAstraLifePlace& Pl) { return IsSpot(Pl) && Pl.External == NAME_None; }, R);
		if (Place == INDEX_NONE)
		{
			Place = Map->Comps[Room].Hub;
		}
		P.LeisureKind = K;
		TargetPlace(P, Idx, Place);
		return;
	}
	P.LeisureKind = INDEX_NONE;
	TargetPlace(P, Idx, P.Home != INDEX_NONE ? Map->Comps[P.Home].Hub : INDEX_NONE);
}

// ====================================================================================================== deciding and walking

void FAstraLifeSim::Begin(int32 Idx, const FDesire& D, bool bTeleport)
{
	FAstraLifePerson& P = People[Idx];
	const bool bWasAsleep = P.Act == EAstraLifeAct::Sleep && P.Phase == FAstraLifePerson::EPhase::Settled;
	Release(P, Idx);
	P.Act = D.Act;
	P.Episode = D.Episode;
	P.bHurry = D.Act == EAstraLifeAct::Battle || D.Act == EAstraLifeAct::Repair;
	if (D.Act != EAstraLifeAct::Repair)
	{
		P.SpeedOverride = 0.f;
	}
	FRandomStream R = Stream(Idx, D.Episode);
	switch (D.Act)
	{
	case EAstraLifeAct::Duty:
		TargetPlace(P, Idx, P.Duty != INDEX_NONE ? P.Duty : (P.Home != INDEX_NONE ? Map->Comps[P.Home].Hub : INDEX_NONE));
		break;
	case EAstraLifeAct::Sleep:
		TargetBunk(P, Idx, R);
		break;
	case EAstraLifeAct::Meal:
		TargetMeal(P, Idx, R);
		break;
	case EAstraLifeAct::Leisure:
		TargetLeisure(P, Idx, R);
		break;
	case EAstraLifeAct::Battle:
		TargetPlace(P, Idx, P.Battle != INDEX_NONE ? P.Battle : P.Duty);
		break;
	case EAstraLifeAct::Patient:
	{
		int32 Place = INDEX_NONE;
		if (P.Bed >= 0)
		{
			Place = Map->PlaceByName.FindRef(FName(*FString::Printf(TEXT("medbay.bed%d"), P.Bed + 1)), INDEX_NONE);
		}
		if (Place == INDEX_NONE && MedbayComp != INDEX_NONE)
		{
			Place = Map->Comps[MedbayComp].Hub;
		}
		TargetPlace(P, Idx, Place);
		break;
	}
	case EAstraLifeAct::Repair:
	{
		const int32 Pi = PartyIndex(P.Party);
		if (Pi != INDEX_NONE)
		{
			const FAstraLifeParty& Pt = PartyList[Pi];
			const float Ang = P.PartySlot * 2.39996f;
			const float Rad = 110.f + 55.f * (float)(P.PartySlot / 5);
			FVector T = Pt.Site + FVector(FMath::Cos(Ang) * Rad, FMath::Sin(Ang) * Rad, 0.0);
			if (Map->Comps.IsValidIndex(Pt.SiteComp))
			{
				const FBox& B = Map->Comps[Pt.SiteComp].Box;
				if (B.Max.X - B.Min.X > 100.f) { T.X = FMath::Clamp(T.X, B.Min.X + 50.f, B.Max.X - 50.f); }
				if (B.Max.Y - B.Min.Y > 100.f) { T.Y = FMath::Clamp(T.Y, B.Min.Y + 50.f, B.Max.Y - 50.f); }
			}
			P.Target = T;
			P.TargetYaw = FMath::RadiansToDegrees(FMath::Atan2(Pt.Site.Y - T.Y, Pt.Site.X - T.X));
			P.TargetHeight = 0.f;
			P.TargetKind = EAstraPlaceKind::Work;
			P.Place = INDEX_NONE;
		}
		break;
	}
	case EAstraLifeAct::Dead:
		P.Phase = FAstraLifePerson::EPhase::Settled;
		P.Route.Clear();
		P.bBody = false;
		return;
	default:
		break;
	}
	P.Route.Clear();
	const bool bThere = FVector::Dist2D(P.Pos, P.Target) < 60.f && FMath::Abs(P.Pos.Z - P.Target.Z) < 120.f;
	if (bTeleport || bThere)
	{
		P.Pos = bTeleport ? P.Target : P.Pos;
		Settle(Idx);
		return;
	}
	P.Phase = FAstraLifePerson::EPhase::WaitRoute;
	// nobody leaves the moment the block changes: a few seconds to finish what they were doing; a sleeper needs to get up
	const float Stagger = R.FRand() * 6.f;
	P.ReadyAt = GameT + (bWasAsleep ? (P.bHurry ? P.WakeDelayS : P.WakeDelayS * 0.6f) : (P.bHurry ? 0.f : Stagger));
	P.RetryAt = 0.0;
	Enqueue(Idx);
}

void FAstraLifeSim::Settle(int32 Idx)
{
	FAstraLifePerson& P = People[Idx];
	P.Phase = FAstraLifePerson::EPhase::Settled;
	P.Pos = P.Target;
	P.Route.Clear();
	if (P.Act == EAstraLifeAct::Battle && Map->Comps.IsValidIndex(P.Place >= 0 ? Map->Places[P.Place].Comp : INDEX_NONE))
	{
		Remember(Idx, 2, FString::Printf(TEXT("Reached my battle station (%s) when general quarters sounded"), *Map->Describe(Map->Places[P.Place].Comp)));
	}
}

float FAstraLifeSim::WalkSpeed(const FAstraLifePerson& P) const
{
	if (P.SpeedOverride > 0.f)
	{
		return P.SpeedOverride;
	}
	return (P.bHurry ? Map->Speed.HurryCmS : Map->Speed.WalkCmS) * P.SpeedFactor;
}

void FAstraLifeSim::MoveBody(int32 Idx, float Dt, float SpeedCmS)
{
	FAstraLifePerson& P = People[Idx];
	if (P.Phase != FAstraLifePerson::EPhase::Walking)
	{
		return;
	}
	P.Route.Advance(Dt, SpeedCmS, Map->Speed);
	P.Pos = P.Route.Position();
	if (P.Route.Done())
	{
		Settle(Idx);
	}
}

void FAstraLifeSim::SetBodied(int32 Idx, bool bBody)
{
	if (People.IsValidIndex(Idx))
	{
		People[Idx].bBody = bBody;
		People[Idx].LastStep = GameT;
	}
}

void FAstraLifeSim::Commandeer(int32 Idx, bool bOn, const FVector& Pos)
{
	if (!People.IsValidIndex(Idx))
	{
		return;
	}
	FAstraLifePerson& P = People[Idx];
	if (bOn)
	{
		if (!P.bCommandeered)
		{
			Release(P, Idx);
			P.Route.Clear();
			P.Phase = FAstraLifePerson::EPhase::Settled;
			P.bBody = false;
			P.Act = EAstraLifeAct::Battle;
			P.bCommandeered = true;
		}
		P.Pos = Pos;
		return;
	}
	if (P.bCommandeered)
	{
		P.bCommandeered = false;
		P.Pos = Pos;
		P.Episode = -1;                                  // they choose again from where they stand
		P.LastStep = GameT;
	}
}

void FAstraLifeSim::StepPerson(int32 Idx)
{
	FAstraLifePerson& P = People[Idx];
	const float Dt = (float)FMath::Clamp(GameT - P.LastStep, 0.0, 900.0);
	P.LastStep = GameT;
	if (P.Status == 2 || P.bCommandeered || P.bTransit || P.bAway)
	{
		return;                                       // (the dead; the ones the marines have taken for a fight; the ones the transporter holds or has sent away)
	}
	++Counters.Steps;
	if (P.Phase == FAstraLifePerson::EPhase::Walking && !P.bBody)
	{
		MoveBody(Idx, Dt, WalkSpeed(P));
	}
	const FDesire D = Decide(P);
	if (D.Episode != P.Episode || D.Act != P.Act)
	{
		Begin(Idx, D, false);
	}
	if (P.Phase == FAstraLifePerson::EPhase::WaitRoute && !Queued[Idx] && GameT >= P.RetryAt)
	{
		Enqueue(Idx);
	}
}

void FAstraLifeSim::Enqueue(int32 Idx)
{
	if (!Queued[Idx])
	{
		Queued[Idx] = 1;
		Queue.Add(Idx);
	}
}

bool FAstraLifeSim::RouteOne()
{
	// the best of those waiting: one with a body first, then the nearest to the Captain; not before they are ready
	int32 Best = INDEX_NONE;
	double BestKey = TNumericLimits<double>::Max();
	for (int32 k = 0; k < Queue.Num(); ++k)
	{
		const int32 I = Queue[k];
		const FAstraLifePerson& P = People[I];
		if (P.Phase != FAstraLifePerson::EPhase::WaitRoute || P.Status == 2 || P.bTransit || P.bAway)
		{
			Queued[I] = 0;
			Queue.RemoveAtSwap(k);
			--k;
			continue;
		}
		if (GameT < P.ReadyAt)
		{
			continue;
		}
		const double Key = P.bBody ? 0.0 : 1.0 + FVector::DistSquared2D(FocusPos, P.Pos);
		if (Key < BestKey)
		{
			BestKey = Key;
			Best = k;
		}
	}
	if (Best == INDEX_NONE)
	{
		return false;
	}
	const int32 Idx = Queue[Best];
	Queue.RemoveAtSwap(Best);
	Queued[Idx] = 0;
	FAstraLifePerson& P = People[Idx];
	TArray<FVector> Pts;
	const double T0 = FPlatformTime::Seconds();
	bool bOk = false;
	if (Router)
	{
		bOk = Router(P.Pos, P.Target, Pts, P.Party != INDEX_NONE);
	}
	else
	{
		Pts = {P.Pos, P.Target};
		bOk = true;
	}
	const double Ms = (FPlatformTime::Seconds() - T0) * 1000.0;
	++Counters.Routes;
	Counters.RouteMs += Ms;
	Counters.RouteMsMax = FMath::Max(Counters.RouteMsMax, Ms);
	if (!bOk || Pts.Num() < 2)
	{
		// no way (a sealed section, a cut-off room): they wait and try again; somebody may open a door
		++Counters.RouteFails;
		FRandomStream R((int32)Hash(Idx, (int32)GameT, 9));
		P.RetryAt = GameT + 12.0 + 12.0 * R.FRand();
		if (Fails.Num() < 60)
		{
			Fails.Add(FString::Printf(TEXT("person %d (%s) %s: from (%.0f,%.0f,%.0f) to (%.0f,%.0f,%.0f)"), Idx, *P.Dept->Name, AstraLifeActName(P.Act), P.Pos.X / 100, P.Pos.Y / 100,
			                          P.Pos.Z / 100, P.Target.X / 100, P.Target.Y / 100, P.Target.Z / 100));
		}
		return true;
	}
	P.Route.Pts.SetNumUninitialized(Pts.Num());
	for (int32 i = 0; i < Pts.Num(); ++i)
	{
		P.Route.Pts[i] = FVector3f(Pts[i]);
	}
	P.Route.Seg = 0;
	P.Route.F = 0.f;
	P.Phase = FAstraLifePerson::EPhase::Walking;
	return true;
}

void FAstraLifeSim::Tick(float DtGame, float TimeScale, double RouteBudgetS, const FVector& Focus)
{
	if (!IsReady())
	{
		return;
	}
	GameT += DtGame;
	Clock += (double)DtGame * TimeScale;
	FocusPos = Focus;
	SliceAcc += (float)(DtGame * People.Num() / StepPeriodS);
	int32 N = FMath::FloorToInt(SliceAcc);
	SliceAcc -= N;
	N = FMath::Min(N, People.Num());
	for (int32 k = 0; k < N; ++k)
	{
		StepPerson(Cursor);
		Cursor = (Cursor + 1) % People.Num();
	}
	const double T0 = FPlatformTime::Seconds();
	int32 Done = 0;
	while (Queue.Num() && (Done == 0 || FPlatformTime::Seconds() - T0 < RouteBudgetS))
	{
		if (!RouteOne())
		{
			break;
		}
		++Done;
	}
}

// ====================================================================================================== the transporter

void FAstraLifeSim::SetTransit(int32 Idx, bool bOn)
{
	if (!People.IsValidIndex(Idx))
	{
		return;
	}
	FAstraLifePerson& P = People[Idx];
	P.bTransit = bOn;
	if (bOn)
	{
		// the pattern has left the ship: what they were doing is forgotten for now (the route, the claim on a place stay as they are until they are set down)
		P.Route.Clear();
		P.Phase = FAstraLifePerson::EPhase::Settled;
		P.bBody = false;
	}
	P.LastStep = GameT;
}

void FAstraLifeSim::PlaceTransported(int32 Idx, const FVector& Where, float YawDeg, float HoldGameS, const FString& Memory)
{
	if (!People.IsValidIndex(Idx))
	{
		return;
	}
	FAstraLifePerson& P = People[Idx];
	P.bTransit = false;
	P.bAway = false;
	P.AwayText.Reset();
	P.Pos = Where;
	P.Route.Clear();
	P.LastStep = GameT;
	if (P.Status == 2)
	{
		return;
	}
	// they stand where the beam set them down and go on with their day from there: the way to wherever they were going is made again
	P.Phase = FAstraLifePerson::EPhase::WaitRoute;
	P.ReadyAt = GameT + FMath::Max(0.f, HoldGameS);
	P.RetryAt = 0.0;
	Enqueue(Idx);
	Remember(Idx, 2, Memory.IsEmpty() ? FString::Printf(TEXT("Beamed to %s by the transporter at %s"), *Map->Describe(Map->CompartmentAt(Where + FVector(0, 0, 30))), *HourText(Clock))
	                                  : FString::Printf(TEXT("%s, to %s, at %s"), *Memory, *Map->Describe(Map->CompartmentAt(Where + FVector(0, 0, 30))), *HourText(Clock)));
	(void)YawDeg;
}

void FAstraLifeSim::SetAway(int32 Idx, const FString& Text, const FString& Memory)
{
	if (!People.IsValidIndex(Idx))
	{
		return;
	}
	FAstraLifePerson& P = People[Idx];
	P.bTransit = false;
	P.bAway = true;
	P.AwayText = Text;
	P.Route.Clear();
	P.Phase = FAstraLifePerson::EPhase::Settled;
	P.bBody = false;
	P.LastStep = GameT;
	Remember(Idx, 3, Memory.IsEmpty() ? FString::Printf(TEXT("Beamed away from the ship by the transporter (%s) at %s"), *Text, *HourText(Clock)) : FString::Printf(TEXT("%s at %s"), *Memory, *HourText(Clock)));
}

// ====================================================================================================== the ship speaks

void FAstraLifeSim::SetAlert(uint8 Level)
{
	if (Level == AlertLevel)
	{
		return;
	}
	const uint8 Old = AlertLevel;
	AlertLevel = Level;
	++AlertSerial;
	if (Level == 2)
	{
		for (int32 i = 0; i < People.Num(); ++i)
		{
			Remember(i, 2, FString::Printf(TEXT("General quarters sounded at %s: everyone to battle stations"), *HourText(Clock)));
		}
	}
	else if (Old == 2)
	{
		for (int32 i = 0; i < People.Num(); ++i)
		{
			Remember(i, 1, FString::Printf(TEXT("The ship stood down from general quarters at %s"), *HourText(Clock)));
		}
	}
}

void FAstraLifeSim::PlanChanged()
{
	// a door was sealed or opened: the routes being walked may cross it; they are made again from where people stand
	for (int32 i = 0; i < People.Num(); ++i)
	{
		FAstraLifePerson& P = People[i];
		if (P.Phase == FAstraLifePerson::EPhase::Walking && !P.Route.InLift())
		{
			P.Pos = P.Route.Position();
			P.Route.Clear();
			P.Phase = FAstraLifePerson::EPhase::WaitRoute;
			P.ReadyAt = GameT;
			Enqueue(i);
		}
	}
}

void FAstraLifeSim::SyncRoster(const FAstraCrewRoster& Roster)
{
	if (Roster.Version() == RosterRev)
	{
		return;
	}
	RosterRev = Roster.Version();
	const TArray<FAstraCrewman>& R = Roster.Get();
	for (int32 i = 0; i < People.Num() && i < R.Num(); ++i)
	{
		FAstraLifePerson& P = People[i];
		const uint8 Old = P.Status;
		const int32 OldBed = P.Bed;
		P.Status = R[i].Status;
		P.Bed = R[i].Bed;
		if (P.Status == Old)
		{
			if (P.Status == 1 && P.Bed != OldBed)
			{
				P.Episode = NoEpisode;                     // their bed changed: they go to the other
			}
			continue;
		}
		const FString Name = R[i].Name();
		if (P.Status == 1)
		{
			Remember(i, 3, FString::Printf(TEXT("I was hurt at %s: %s"), *HourText(Clock), R[i].Injury.IsEmpty() ? TEXT("wounds") : *R[i].Injury));
		}
		else if (P.Status == 2)
		{
			Release(P, i);
			if (P.Party != INDEX_NONE)
			{
				const int32 Pi = PartyIndex(P.Party);
				if (Pi != INDEX_NONE)
				{
					PartyList[Pi].Members.Remove(i);
				}
				P.Party = INDEX_NONE;
			}
			P.Act = EAstraLifeAct::Dead;
			P.Phase = FAstraLifePerson::EPhase::Settled;
			P.Route.Clear();
		}
		else if (Old == 1 && P.Status == 0)
		{
			Remember(i, 2, FString::Printf(TEXT("Discharged from the Medbay at %s, fit for duty"), *HourText(Clock)));
		}
		// the people who care: friends remember what happened to them
		if (P.Status == 1 || P.Status == 2)
		{
			for (int32 j = 0; j < People.Num(); ++j)
			{
				for (int32 f = 0; f < 3; ++f)
				{
					if (People[j].Friends[f] == i && People[j].Status != 2)
					{
						Remember(j, P.Status == 2 ? 3 : 2,
						         FString::Printf(TEXT("%s, a friend and shipmate in %s, was %s at %s"), *Name, *R[i].Dept, P.Status == 2 ? TEXT("killed") : TEXT("wounded"), *HourText(Clock)));
					}
				}
			}
		}
	}
}

int32 FAstraLifeSim::PartyIndex(int32 IncidentId) const
{
	for (int32 i = 0; i < PartyList.Num(); ++i)
	{
		if (PartyList[i].Incident == IncidentId)
		{
			return i;
		}
	}
	return INDEX_NONE;
}

int32 FAstraLifeSim::PickSite(int32 Deck, TCHAR Section, int32 IncidentId) const
{
	TArray<int32> Cand;
	TArray<float> W;
	TArray<int32> DeckAll;
	for (int32 i = 0; i < Map->Comps.Num(); ++i)
	{
		const FAstraLifeComp& C = Map->Comps[i];
		if (C.Deck != Deck || C.bWalled || C.Kind == TEXT("stairs") || C.Kind == TEXT("tank") || C.Kind == TEXT("lift"))
		{
			continue;
		}
		DeckAll.Add(i);
		if (C.Section == Section)
		{
			Cand.Add(i);
			W.Add(C.bCorridor ? 2.f : 1.f);
		}
	}
	FRandomStream R = Stream(IncidentId, 13);
	if (Cand.Num())
	{
		return Cand[PickWeighted(W, R)];
	}
	return DeckAll.Num() ? DeckAll[R.RandHelper(DeckAll.Num())] : INDEX_NONE;
}

const FBox& FAstraLifeSim::SectionBox(int32 Deck, TCHAR Section)
{
	const int32 Key = Deck * 256 + (int32)Section;
	if (const FBox* B = SectionBoxes.Find(Key))
	{
		return *B;
	}
	FBox Box(ForceInit);
	for (const FAstraLifeComp& C : Map->Comps)
	{
		if (C.Deck == Deck && C.Section == Section && !C.bHall)
		{
			Box += C.Box;
		}
	}
	return SectionBoxes.Add(Key, Box);
}

void FAstraLifeSim::PeopleIn(int32 Deck, TCHAR Section, TArray<int32>& Out) const
{
	Out.Reset();
	const FBox& B = const_cast<FAstraLifeSim*>(this)->SectionBox(Deck, Section);
	if (!B.IsValid)
	{
		return;
	}
	for (int32 i = 0; i < People.Num(); ++i)
	{
		const FAstraLifePerson& P = People[i];
		if (P.Status == 0 && !P.bTransit && !P.bAway && P.Act != EAstraLifeAct::Patient && FMath::Abs(P.Pos.Z - B.Min.Z) < 450.f && P.Pos.X >= B.Min.X && P.Pos.X <= B.Max.X
		    && P.Pos.Y >= B.Min.Y && P.Pos.Y <= B.Max.Y)
		{
			Out.Add(i);
		}
	}
}

void FAstraLifeSim::PeopleInComp(int32 CompIdx, TArray<int32>& Out) const
{
	Out.Reset();
	if (!Map->Comps.IsValidIndex(CompIdx))
	{
		return;
	}
	const FBox B = Map->Comps[CompIdx].Box;
	for (int32 i = 0; i < People.Num(); ++i)
	{
		const FAstraLifePerson& P = People[i];
		if (P.Status == 0 && !P.bTransit && !P.bAway && P.Act != EAstraLifeAct::Patient && B.IsInsideOrOn(P.Pos + FVector(0, 0, 30)))
		{
			Out.Add(i);
		}
	}
}

void FAstraLifeSim::FormParty(const FAstraDamage& D)
{
	FAstraLifeParty Pt;
	Pt.Incident = D.Id;
	Pt.ShipTeam = D.Team;
	Pt.Deck = D.Deck;
	Pt.Section = D.Section;
	Pt.Kind = D.Kind;
	Pt.Site = SiteOfIncident(D, &Pt.SiteComp);
	Pt.ShipTravel0 = D.Travel;
	Pt.DispatchedAt = Clock;
	if (!Map->Comps.IsValidIndex(Pt.SiteComp))
	{
		return;
	}
	// who goes: the nearest of the damage-control ratings who are fit, and if there are too few, engineering
	TArray<FGoer> Cand;
	Goers(D.Deck, Pt.Site, Cand);
	const int32 Take = FMath::Min(Map->Teams.Size, Cand.Num());
	for (int32 k = 0; k < Take; ++k)
	{
		Pt.Members.Add(Cand[k].Person);
	}
	PartyList.Add(Pt);
	FAstraLifeParty& Made = PartyList.Last();
	for (int32 k = 0; k < Made.Members.Num(); ++k)
	{
		FAstraLifePerson& P = People[Made.Members[k]];
		P.Party = D.Id;
		P.PartySlot = k;
		P.SpeedOverride = Map->Teams.JogCmS;             // a party runs: the time it needs is what PartyEtaSeconds said (the ship's own formula does not slow it)
		Begin(Made.Members[k], {EAstraLifeAct::Repair, 70000000 + D.Id}, false);
		Remember(Made.Members[k], 2, FString::Printf(TEXT("Sent with a damage-control party to the %s in section %c of deck %d at %s"), *D.Kind, D.Section, D.Deck, *HourText(Clock)));
	}
	Made.State = FAstraLifeParty::EState::EnRoute;
}

void FAstraLifeSim::EndParty(int32 PartyIdx, bool bRepaired)
{
	const FAstraLifeParty Pt = PartyList[PartyIdx];
	PartyList.RemoveAt(PartyIdx);
	for (const int32 M : Pt.Members)
	{
		if (!People.IsValidIndex(M) || People[M].Party != Pt.Incident)
		{
			continue;
		}
		People[M].Party = INDEX_NONE;
		People[M].SpeedOverride = 0.f;
		if (bRepaired && People[M].Status == 0)
		{
			Remember(M, 2, FString::Printf(TEXT("Worked the %s in section %c of deck %d with the damage-control party until it was done (%s)"), *Pt.Kind, Pt.Section, Pt.Deck,
			                               *HourText(Clock)));
		}
	}
}

void FAstraLifeSim::SyncDamage(const TArray<FAstraDamage>& Damage)
{
	TSet<int32> Open;
	for (const FAstraDamage& D : Damage)
	{
		Open.Add(D.Id);
		if (!KnownIncidents.Contains(D.Id))
		{
			KnownIncidents.Add(D.Id);
			// the people who were in that part of the ship remember it
			TArray<int32> Near;
			PeopleIn(D.Deck, D.Section, Near);
			const FString Text = D.Kind == TEXT("fire") ? FString::Printf(TEXT("A fire broke out in section %c of deck %d at %s, where I was"), D.Section, D.Deck, *HourText(Clock))
			                   : D.Kind == TEXT("hull breach") ? FString::Printf(TEXT("The hull was breached in section %c of deck %d at %s: a rush of air, the bulkhead doors slamming shut"), D.Section, D.Deck, *HourText(Clock))
			                   : D.Kind == TEXT("conduit damage") ? FString::Printf(TEXT("A power conduit blew in section %c of deck %d at %s: sparks, then the lights"), D.Section, D.Deck, *HourText(Clock))
			                   : FString::Printf(TEXT("%s in section %c of deck %d at %s"), *D.Kind, D.Section, D.Deck, *HourText(Clock));
			for (const int32 I : Near)
			{
				Remember(I, 2, Text);
			}
		}
		const int32 Pi = PartyIndex(D.Id);
		if (D.Team >= 0 && Pi == INDEX_NONE)
		{
			FormParty(D);
		}
		else if (Pi != INDEX_NONE)
		{
			FAstraLifeParty& Pt = PartyList[Pi];
			Pt.ShipTeam = D.Team;
			int32 There = 0;
			for (const int32 M : Pt.Members)
			{
				There += (People[M].Phase == FAstraLifePerson::EPhase::Settled && People[M].Act == EAstraLifeAct::Repair) ? 1 : 0;
			}
			if (Pt.State != FAstraLifeParty::EState::Working && Pt.Members.Num() && There * 10 >= Pt.Members.Num() * 6)
			{
				Pt.State = FAstraLifeParty::EState::Working;
				Pt.ArrivedAt = Clock;
				Pt.bLate = D.Travel <= 0.f && Pt.ShipTravel0 > 0.f && D.Progress > 0.05f;
			}
		}
	}
	for (int32 i = PartyList.Num() - 1; i >= 0; --i)
	{
		if (!Open.Contains(PartyList[i].Incident))
		{
			EndParty(i, true);
		}
	}
	for (auto It = KnownIncidents.CreateIterator(); It; ++It)
	{
		if (!Open.Contains(*It))
		{
			It.RemoveCurrent();
		}
	}
}

FVector FAstraLifeSim::SiteOf(int32 Deck, TCHAR Section, int32 IncidentId, int32* OutComp) const
{
	const int32 Comp = PickSite(Deck, Section, IncidentId);
	if (OutComp)
	{
		*OutComp = Comp;
	}
	if (!Map->Comps.IsValidIndex(Comp))
	{
		return FVector::ZeroVector;
	}
	const FAstraLifeComp& C = Map->Comps[Comp];
	return C.bCorridor || C.Hub == INDEX_NONE ? FVector(C.Box.GetCenter().X, C.Box.GetCenter().Y, C.Box.Min.Z) : Map->Places[C.Hub].Pos;
}

float FAstraLifeSim::RepairEtaSeconds(int32 Deck, TCHAR Section, int32 IncidentId) const
{
	return PartyEtaSeconds(SiteOf(Deck, Section, IncidentId), Deck);
}

FVector FAstraLifeSim::SiteOfIncident(const FAstraDamage& D, int32* OutComp) const
{
	int32 Comp = D.CompId.IsNone() ? INDEX_NONE : Map->CompByName.FindRef(D.CompId, INDEX_NONE);
	if (Comp == INDEX_NONE)
	{
		return SiteOf(D.Deck, D.Section, D.Id, OutComp);                 // an incident that is only a deck and a section
	}
	if (Map->Comps[Comp].bWalled)
	{
		// a room the level does not open (a planned one on a built deck): the team works from the nearest place that is
		const FBox Wall = Map->Comps[Comp].Box;
		int32 Best = INDEX_NONE;
		double BestD = TNumericLimits<double>::Max();
		for (int32 i = 0; i < Map->Comps.Num(); ++i)
		{
			const FAstraLifeComp& C = Map->Comps[i];
			if (C.bWalled || C.Deck != Map->Comps[Comp].Deck || C.Kind == TEXT("stairs") || C.Kind == TEXT("lift"))
			{
				continue;
			}
			const double Dist = FMath::Sqrt(Wall.ComputeSquaredDistanceToBox(C.Box));
			if (Dist < BestD)
			{
				BestD = Dist;
				Best = i;
			}
		}
		if (Best != INDEX_NONE)
		{
			Comp = Best;
		}
	}
	if (OutComp)
	{
		*OutComp = Comp;
	}
	const FAstraLifeComp& C = Map->Comps[Comp];
	return C.bCorridor || C.Hub == INDEX_NONE ? FVector(C.Box.GetCenter().X, C.Box.GetCenter().Y, C.Box.Min.Z) : Map->Places[C.Hub].Pos;
}

float FAstraLifeSim::RepairEtaFor(const FAstraDamage& D) const
{
	return PartyEtaSeconds(SiteOfIncident(D), D.Deck);
}

int32 FAstraLifeSim::DeckOfZ(double Z) const
{
	int32 Best = 1;
	for (int32 d = 2; d < Map->DeckFloorCm.Num(); ++d)
	{
		if (FMath::Abs(Map->DeckFloorCm[d] - Z) < FMath::Abs(Map->DeckFloorCm[Best] - Z))
		{
			Best = d;
		}
	}
	return Best;
}

void FAstraLifeSim::Goers(int32 Deck, const FVector& Site, TArray<FGoer>& Out) const
{
	Out.Reset();
	auto Consider = [&](const FString& DeptName)
	{
		for (int32 i = 0; i < People.Num(); ++i)
		{
			const FAstraLifePerson& P = People[i];
			if (P.Status != 0 || P.Party != INDEX_NONE || !P.Dept || P.Dept->Name != DeptName)
			{
				continue;
			}
			const int32 Decks = FMath::Abs(DeckOfZ(P.Pos.Z) - Deck);
			const bool bAsleep = P.Act == EAstraLifeAct::Sleep;
			const double Cost = FVector::Dist2D(P.Pos, Site) + 6000.0 * Decks + (bAsleep ? 3000.0 : 0.0);
			// their own time: the way is longer than the crow flies, stairs and lifts add to it, a sleeper has to be roused
			const float Eta = (float)((FVector::Dist2D(P.Pos, Site) * 1.5 + 600.0 * Decks) / Map->Teams.JogCmS + Decks * 6.0 + (bAsleep ? P.WakeDelayS : 0.0));
			Out.Add({Cost, i, Eta});
		}
	};
	Consider(Map->Teams.Dept);
	if (Out.Num() < Map->Teams.Min)
	{
		Consider(Map->Teams.BackupDept);
	}
	Out.Sort([](const FGoer& A, const FGoer& B) { return A.Cost < B.Cost; });
}

float FAstraLifeSim::PartyEtaSeconds(const FVector& Site, int32 Deck) const
{
	// The party is on scene when six in ten of it are. The members are the nearest who would go, and the time each needs is that of the plan's
	// own route at the party's pace (stairs and lifts and the way round included), a sleeper's waking too; without a router, the crow's estimate.
	TArray<FGoer> G;
	Goers(Deck, Site, G);
	const int32 N = FMath::Min(Map->Teams.Size, G.Num());
	if (N == 0)
	{
		return 60.f;
	}
	TArray<float> T;
	for (int32 k = 0; k < N; ++k)
	{
		const FAstraLifePerson& P = People[G[k].Person];
		float Eta = G[k].EtaS;
		TArray<FVector> Pts;
		if (Router && Router(P.Pos, Site, Pts, true) && Pts.Num() >= 2)
		{
			FAstraLifeRoute R;
			R.Pts.SetNumUninitialized(Pts.Num());
			for (int32 i = 0; i < Pts.Num(); ++i)
			{
				R.Pts[i] = FVector3f(Pts[i]);
			}
			Eta = P.Act == EAstraLifeAct::Sleep ? P.WakeDelayS : 0.f;
			for (int32 S = 0; S + 1 < R.Pts.Num(); ++S)
			{
				Eta += R.SegSeconds(S, Map->Teams.JogCmS, Map->Speed);
			}
		}
		T.Add(Eta);
	}
	T.Sort();
	return T[FMath::Min(N - 1, FMath::CeilToInt(N * 0.6f) - 1)] + 2.f;
}

// ====================================================================================================== asking

int32 FAstraLifeSim::CompOf(int32 Person) const
{
	return People.IsValidIndex(Person) ? Map->CompartmentAt(People[Person].Pos + FVector(0, 0, 30)) : INDEX_NONE;
}

FString FAstraLifeSim::Where(int32 Person) const
{
	return Map->Describe(CompOf(Person));
}

int32 FAstraLifeSim::WhoIsAt(FName ExternalStation) const
{
	if (const int32* P = ExternalPlace.Find(ExternalStation))
	{
		return Occ[*P] > 0 ? Holder[*P] : INDEX_NONE;
	}
	return INDEX_NONE;
}

FString FAstraLifeSim::Doing(int32 Person) const
{
	const FAstraLifePerson& P = People[Person];
	if (P.bTransit || P.bAway)
	{
		return P.bTransit ? FString(TEXT("in the transporter's buffer")) : (P.AwayText.IsEmpty() ? FString(TEXT("away from the ship")) : P.AwayText);
	}
	if (P.bCommandeered)
	{
		return FString::Printf(TEXT("fighting the boarders with their squad (%s)"), *Map->Describe(CompOf(Person)));
	}
	const bool bWalk = P.Phase != FAstraLifePerson::EPhase::Settled;
	const FString Here = Map->Describe(P.Place != INDEX_NONE ? Map->Places[P.Place].Comp : CompOf(Person));
	switch (P.Act)
	{
	case EAstraLifeAct::Sleep:
		return bWalk ? FString::Printf(TEXT("on the way to their bunk (%s)"), *Here) : FString::Printf(TEXT("asleep in their bunk (%s)"), *Here);
	case EAstraLifeAct::Duty:
		return bWalk ? FString::Printf(TEXT("on the way to their post: %s, %s"), *P.Job, *Here) : FString::Printf(TEXT("on duty, working as %s (%s)"), *P.Job, *Here);
	case EAstraLifeAct::Meal:
		return bWalk ? TEXT("on the way to a meal") : FString::Printf(TEXT("eating (%s)"), *Here);
	case EAstraLifeAct::Leisure:
	{
		const FString Label = Map->Leisure.IsValidIndex(P.LeisureKind) ? Map->Leisure[P.LeisureKind].Label : FString(TEXT("somewhere aboard"));
		return bWalk ? FString::Printf(TEXT("off duty, walking to a place to rest (%s)"), *Here) : FString::Printf(TEXT("off duty, %s (%s)"), *Label, *Here);
	}
	case EAstraLifeAct::Battle:
		return bWalk ? TEXT("running to their battle station: general quarters") : FString::Printf(TEXT("at their battle station (%s): general quarters"), *Here);
	case EAstraLifeAct::Repair:
	{
		const int32 Pi = PartyIndex(P.Party);
		const FString What = Pi != INDEX_NONE ? FString::Printf(TEXT("the %s in section %c of deck %d"), *PartyList[Pi].Kind, PartyList[Pi].Section, PartyList[Pi].Deck) : FString(TEXT("an incident"));
		return bWalk ? FString::Printf(TEXT("hurrying with a damage-control party to %s"), *What) : FString::Printf(TEXT("working with a damage-control party on %s"), *What);
	}
	case EAstraLifeAct::Patient:
		return bWalk ? TEXT("wounded, making their way to the Medbay") : TEXT("wounded, in the Medbay");
	default:
		return TEXT("gone");
	}
}

void FAstraLifeSim::Stats(FAstraLifeStats& Out) const
{
	Out = Counters;
	FMemory::Memzero(Out.PerAct);
	Out.Walking = Out.Waiting = 0;
	for (const FAstraLifePerson& P : People)
	{
		++Out.PerAct[(int32)P.Act];
		Out.Walking += P.Phase == FAstraLifePerson::EPhase::Walking ? 1 : 0;
		Out.Waiting += P.Phase == FAstraLifePerson::EPhase::WaitRoute ? 1 : 0;
	}
}
