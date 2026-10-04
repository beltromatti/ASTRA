#include "AstraBoardScene.h"

#include "AstraFleetInterior.h"

using namespace AstraBoard;

namespace
{
	/** A place of the plan by a name the minds and the commands use. */
	int32 ScObjective(const FBoardShipPlan& Plan, const FString& Name, FString& OutName)
	{
		struct FKey { const TCHAR* Name; const TCHAR* Kind; const TCHAR* Label; };
		static const FKey Keys[] = {{TEXT("bridge"), TEXT("bridge"), TEXT("the bridge")}, {TEXT("engineering"), TEXT("engineering"), TEXT("engineering")}, {TEXT("captain"), TEXT("quarters"), TEXT("the commander's suite")},
		                            {TEXT("armory"), TEXT("armory"), TEXT("the armoury")}, {TEXT("medbay"), TEXT("medbay"), TEXT("the medbay")}, {TEXT("brig"), TEXT("brig"), TEXT("the brig")},
		                            {TEXT("comms"), TEXT("comms"), TEXT("the comms room")}, {TEXT("hangar"), TEXT("hangar"), TEXT("the boat bay")}};
		for (const FKey& K : Keys)
		{
			if (Name.Equals(K.Name, ESearchCase::IgnoreCase))
			{
				OutName = K.Label;
				return Plan.Objective(K.Name, K.Kind);
			}
		}
		if (Plan.Dmg.IsValid())
		{
			if (const int32* C = Plan.Dmg->CompByName.Find(FName(*Name)))
			{
				OutName = Plan.Map->Describe(*C);
				return *C;
			}
		}
		return INDEX_NONE;
	}

	FVector ScSpot(const FAstraBoardMap& Map, int32 Comp, FRandomStream& Rng)
	{
		const FBox& B = Map.GetComps()[Comp].Box;
		const FVector P(FMath::Lerp(B.Min.X, B.Max.X, (double)Rng.FRandRange(0.15f, 0.85f)), FMath::Lerp(B.Min.Y, B.Max.Y, (double)Rng.FRandRange(0.15f, 0.85f)), B.Min.Z);
		return Map.Inset(Comp, P, 70.f);
	}

	/** What a squad of a ship's people is called by what they do (EFleetRole). */
	const TCHAR* ScRoleTitle(uint8 Role)
	{
		static const TCHAR* Titles[] = {TEXT("Bridge"), TEXT("Control"), TEXT("Gunnery"), TEXT("Magazine"), TEXT("Engineering"), TEXT("Damage Control"), TEXT("Medical"), TEXT("Flight"), TEXT("Sensors"),
		                                TEXT("Marines"), TEXT("Dock Guard"), TEXT("Crew")};
		return Titles[FMath::Min<int32>(Role, UE_ARRAY_COUNT(Titles) - 1)];
	}

	/** The people of a ship the war has shot at, put on her plan as the holders: the living at the places the war has them, the fit who take up arms as soldiers (the marines of the ship all do,
	 *  the rest by Spec.PostShare, at most Spec.MaxDefenders in all), the wounded lying where they are; the bulkheads she has shut are shut. Returns the people who fight. */
	void ScFromWar(FAstraBoardSim& Sim, const FBoardShipPlan& Plan, const AstraBoardScene::FSpec& Spec, ESide Def, FRandomStream& Rng, AstraBoardScene::FResult& R)
	{
		const FFleetSnapshot& Snap = *Spec.Inside;
		const FAstraBoardMap& Map = *Plan.Map;
		R.bFromWar = true;
		// the bulkheads the war shut
		if (Plan.Dmg.IsValid())
		{
			for (const FName& Id : Snap.SealedDoors)
			{
				if (const int32* D = Plan.Dmg->DoorByName.Find(Id))
				{
					Sim.SealDoor(*D, true);
					++R.ShutBulkheads;
				}
			}
		}
		// who fights: the ship's marines (EFleetRole::Marine, MarineDock) as a rule, the others by the share, the whole not past the most the simulation is given
		int32 Guard = 0, Others = 0;
		for (const FFleetSnapshot::FHand& H : Snap.Hands)
		{
			if (H.bWounded)
			{
				continue;
			}
			if (H.Role == (uint8)EFleetRole::Marine || H.Role == (uint8)EFleetRole::MarineDock)
			{
				++Guard;
			}
			else
			{
				++Others;
			}
		}
		const float GuardShare = Spec.GuardShare >= 0.f ? Spec.GuardShare : 0.9f;
		const float OtherShare = Others > 0 ? FMath::Min(Spec.PostShare, FMath::Max(0.f, (float)(Spec.MaxDefenders - FMath::RoundToInt(Guard * GuardShare)) / (float)Others)) : 0.f;
		TMap<int32, TArray<int32>> Armed;                             // by room: the hands who fight
		int32 Counter = 0;
		for (int32 i = 0; i < Snap.Hands.Num(); ++i)
		{
			const FFleetSnapshot::FHand& H = Snap.Hands[i];
			if (!Map.GetComps().IsValidIndex(H.Comp))
			{
				continue;
			}
			const FVector Spot = [&]()
			{
				FVector P = Map.Inset(H.Comp, FVector(H.PosCm), 45.f);
				P.Z = Map.GetComps()[H.Comp].FloorZ();
				return P;
			}();
			R.bCaptainAlive |= H.Billet == TEXT("captain");
			if (H.bWounded)
			{
				Sim.AddWounded(Def, !H.Name.IsEmpty() ? H.Name : Sim.MakeName(Def, ++Counter), Spot);
				++R.Wounded;
				continue;
			}
			const bool bGuard = H.Role == (uint8)EFleetRole::Marine || H.Role == (uint8)EFleetRole::MarineDock;
			if (Rng.FRand() < (bGuard ? GuardShare : OtherShare) || !H.Billet.IsEmpty())
			{
				Armed.FindOrAdd(H.Comp).Add(i);
			}
			else
			{
				++R.Unarmed;
			}
		}
		// the rooms in a fixed order (the same ship, the same answer), the people of each in squads of six who hold the room; the ship's marines answer the alarm instead of holding
		TArray<int32> Rooms;
		Armed.GetKeys(Rooms);
		Rooms.Sort();
		for (const int32 Room : Rooms)
		{
			const TArray<int32>& Hands = Armed[Room];
			for (int32 From = 0; From < Hands.Num(); From += 6)
			{
				const int32 N = FMath::Min(6, Hands.Num() - From);
				// the name of the squad: what most of them do
				int32 Roles[(int32)EFleetRole::Num] = {};
				for (int32 k = 0; k < N; ++k)
				{
					++Roles[FMath::Min<int32>(Snap.Hands[Hands[From + k]].Role, (int32)EFleetRole::Num - 1)];
				}
				int32 Main = 0;
				for (int32 k = 1; k < (int32)EFleetRole::Num; ++k)
				{
					Main = Roles[k] > Roles[Main] ? k : Main;
				}
				const bool bReact = Main == (int32)EFleetRole::Marine;
				const int32 Sq = Sim.AddSquad(Def, ScRoleTitle((uint8)Main));
				int32 Lead = 0;
				for (int32 k = 0; k < N; ++k)
				{
					Lead = !Snap.Hands[Hands[From + k]].Billet.IsEmpty() ? k : Lead;          // an officer leads the men about him
				}
				for (int32 k = 0; k < N; ++k)
				{
					const FFleetSnapshot::FHand& H = Snap.Hands[Hands[From + k]];
					FVector Spot = Map.Inset(H.Comp, FVector(H.PosCm), 45.f);
					Spot.Z = Map.GetComps()[H.Comp].FloorZ();
					const ERole Role = k == Lead ? ERole::Leader : (k == N - 1 && N >= 5 && Roles[(int32)EFleetRole::Marine] > 2 ? ERole::Heavy : ERole::Rifleman);
					Sim.AddUnit(Def, Role, !H.Name.IsEmpty() ? H.Name : Sim.MakeName(Def, ++Counter), Spot, Sq);       // (the first of a squad leads it; an officer, added later as its Leader, takes it over)
					++R.Defenders;
				}
				if (bReact)
				{
					if (FAstraBoardSim::FSquad* S = Sim.SquadMutable(Sq))
					{
						S->bQuickReaction = true;                                // (the guard of the ship is armed already: it goes to meet them)
						S->MusterT = 4.f + 6.f * Rng.FRand();
					}
				}
				else
				{
					Sim.Order(Sq, ETask::Hold, Room, Map.CentreOf(Room), 700.f, TEXT("at the post"));
				}
				R.DefendSquads.Add(Sq);
			}
		}
	}

	FString ScTitle(const FString& Role)
	{
		FString T = Role;
		if (T.Len())
		{
			T[0] = FChar::ToUpper(T[0]);
		}
		return T;
	}
}

void AstraBoardScene::ForDisabledShip(FSpec& Spec, bool bFromWar)
{
	Spec.GuardShare = 0.5f;
	Spec.PostShare = bFromWar ? 0.08f : 0.06f;
	if (!bFromWar)
	{
		Spec.MinPerPost = 0;
		Spec.Roaming = 0;
	}
}

AstraBoardScene::FResult AstraBoardScene::Build(FAstraBoardSim& Sim, const FBoardShipPlan& Plan, const FSpec& Spec)
{
	FResult R;
	if (!Plan.IsReady() || !Sim.IsReady())
	{
		R.Why = TEXT("no plan to fight on");
		return R;
	}
	const FAstraBoardMap& Map = *Plan.Map;
	const ESide Att = Spec.Attacker;
	const ESide Def = Att == ESide::Mandate ? ESide::Aquila : ESide::Mandate;
	FRandomStream Rng(Spec.Seed * 7919 + 13);
	// where they come in
	int32 Breach = Spec.Breach;
	FVector At = FVector::ZeroVector;
	if (Breach == INDEX_NONE)
	{
		const int32 Dock = Plan.Docks.IsValidIndex(Spec.Dock) ? Spec.Dock : 0;
		if (!Plan.Docks.IsValidIndex(Dock))
		{
			R.Why = TEXT("the plan has no docks to cut in at");
			return R;
		}
		Breach = Plan.Docks[Dock].Comp;
		At = Plan.Docks[Dock].Pos;
	}
	else if (Map.GetComps().IsValidIndex(Breach))
	{
		At = Map.CentreOf(Breach);
	}
	if (!Map.GetComps().IsValidIndex(Breach))
	{
		R.Why = TEXT("no room to cut into");
		return R;
	}
	At = Map.Inset(Breach, At, 70.f);
	At.Z = Map.GetComps()[Breach].FloorZ();
	// what they want
	const int32 Obj = ScObjective(Plan, Spec.Objective, R.ObjectiveName);
	if (!Map.GetComps().IsValidIndex(Obj))
	{
		R.Why = FString::Printf(TEXT("the plan has no '%s' to go for"), *Spec.Objective);
		return R;
	}
	Sim.SetMission(Att, Breach, At, Obj, Spec.bSweep);
	Sim.Tuning.bShipSensors = Spec.bShipSensors;
	R.Breach = Breach;
	R.BreachPos = At;
	R.Objective = Obj;
	if (Spec.Inside)
	{
		ScFromWar(Sim, Plan, Spec, Def, Rng, R);
		R.bOk = true;
		R.AttackSquads = Sim.SpawnAttackers(Att, Breach, At, Obj, Spec.Attackers, Spec.FirstAtS, Spec.PerSquad);
		return R;
	}
	// the holders at their posts (the plan's hint; a plan without one still has people on the bridge and in engineering)
	TArray<FBoardShipPlan::FPost> Posts = Plan.Garrison;
	if (Posts.IsEmpty())
	{
		const int32 Crew = FMath::Max(40, Plan.Crew);
		struct FDefault { const TCHAR* Name; int32 N; };
		const FDefault Defaults[] = {{TEXT("bridge"), Crew / 40}, {TEXT("engineering"), Crew / 35}, {TEXT("captain"), 3}, {TEXT("armory"), 2}, {TEXT("hangar"), Crew / 80}};
		for (const FDefault& D : Defaults)
		{
			FString Unused;
			const int32 C = ScObjective(Plan, D.Name, Unused);
			if (C != INDEX_NONE)
			{
				Posts.Add({C, FMath::Max(2, D.N), FString(D.Name)});
			}
		}
	}
	int32 Counter = 0;
	for (const FBoardShipPlan::FPost& Post : Posts)
	{
		if (!Map.GetComps().IsValidIndex(Post.Comp))
		{
			continue;
		}
		const bool bGuardPost = Spec.GuardShare >= 0.f && (Post.Role == TEXT("marines") || Post.Role == TEXT("marines_dock"));
		const int32 N = FMath::Max(Spec.MinPerPost, FMath::RoundToInt(Post.N * (bGuardPost ? Spec.GuardShare : Spec.PostShare)));
		if (N <= 0)
		{
			continue;
		}
		const int32 Sq = Sim.AddSquad(Def, ScTitle(Post.Role));
		for (int32 k = 0; k < N; ++k)
		{
			const ERole Role = k == 0 ? ERole::Leader : (k == N - 1 && N >= 5 ? ERole::Heavy : ERole::Rifleman);
			Sim.AddUnit(Def, Role, Sim.MakeName(Def, ++Counter), ScSpot(Map, Post.Comp, Rng), Sq);
			++R.Defenders;
		}
		Sim.Order(Sq, ETask::Hold, Post.Comp, Map.CentreOf(Post.Comp), 700.f, TEXT("at the post"));
		R.DefendSquads.Add(Sq);
	}
	// the others, in the berthing and the cabins: they arm and answer the alarm
	TArray<int32> Quarters;
	for (int32 i = 0; i < Map.GetComps().Num(); ++i)
	{
		const FName K = Map.GetComps()[i].Kind;
		if (!Map.GetComps()[i].bCorridor && (K == TEXT("berthing") || K == TEXT("cabins") || K == TEXT("quarters") || K == TEXT("mess") || K == TEXT("lounge")) && i != Obj)
		{
			Quarters.Add(i);
		}
	}
	if (Quarters.Num())
	{
		int32 Left = Spec.Roaming, Team = 0;
		while (Left > 0)
		{
			const int32 Here = FMath::Min(4, Left);
			Left -= Here;
			const int32 Home = Quarters[Rng.RandHelper(Quarters.Num())];
			const int32 Sq = Sim.AddSquad(Def, FString::Printf(TEXT("Crew Watch %d"), ++Team));
			if (FSquad* S = Sim.SquadMutable(Sq))
			{
				S->bQuickReaction = true;
				S->MusterT = 12.f + 10.f * Rng.FRand();
			}
			for (int32 k = 0; k < Here; ++k)
			{
				Sim.AddUnit(Def, k == 0 ? ERole::Leader : ERole::Rifleman, Sim.MakeName(Def, ++Counter), ScSpot(Map, Home, Rng), Sq);
				++R.Defenders;
			}
			R.DefendSquads.Add(Sq);
		}
	}
	// the bulkheads that are shut when they come
	for (const FBoardPortal& P : Map.GetPortals())
	{
		if (P.Kind == FBoardPortal::EKind::Blast && Rng.FRand() < Spec.SealedShare)
		{
			Sim.SealDoor(P.Door, true);
		}
	}
	// the attackers
	R.AttackSquads = Sim.SpawnAttackers(Att, Breach, At, Obj, Spec.Attackers, Spec.FirstAtS, Spec.PerSquad);
	R.bOk = true;
	return R;
}
