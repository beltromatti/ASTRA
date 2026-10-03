#include "AstraBoardScene.h"

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
		const int32 N = FMath::Max(1, FMath::RoundToInt(Post.N * Spec.PostShare));
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
