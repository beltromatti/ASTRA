// ASTRA — ABBORDAGGI-2: boarding by assault craft, the host's side (docs/brief/ABBORDAGGI-2.md §1, §4, §6).
//
// The battle flies the boats (AstraBoardCraft.*: the Mandate's skiffs, the Aquila's Kestrels: a hull, point defence and fighters that shoot them, a hatch to latch to); this orders them, reads what
// they do, and makes the fight of what they carry:
//
//   in   the Mandate's skiffs at the Aquila: the scene is her own decks (the soldiers' map of her plan, the bodies and the Captain, the bulkheads); it begins when the first boat is out (the alarm:
//        the marines are called, the ship goes to general quarters) and the boarders cut in where each boat latches (her airlocks are her hatches); a boat that is shot down takes its men with it
//   out  the Aquila's marines of the ship's roster in Kestrels at a ship of the Mandate (or a boat of a consort at another ship): the scene is the boarded ship's own plan (her class's), run by the
//        simulation alone (the Captain is not in it unless he rides along): reports on the net, casualties to the roster, the ship's fate (taken, still a hulk) and the boats going home
//
// One assault at a time (a boat flying, a fight, the boats coming home), on the one scene the host has. What to board, where, with how many is the minds'; what the world lets happen (a shield on the
// hatch, point defence, a boat's hull) is the battle's and the plan's; here are the facts told truly, the men and what becomes of them.

#include "AstraBoardSubsystem.h"

#include "ASTRA.h"
#include "AstraBattleSubsystem.h"
#include "AstraBoardScene.h"
#include "AstraCombatFx.h"
#include "AstraCrewRoster.h"
#include "AstraLifeSubsystem.h"
#include "AstraShipSubsystem.h"
#include "Async/Async.h"
#include "Engine/World.h"
#include "Misc/App.h"

using namespace AstraBoard;
using AstraBoardCraft::FAssess;
using AstraBoardCraft::FLaunchResult;
using AstraBoardCraft::FShipFacts;

namespace
{
	constexpr int32 AsMarinesPerBoat = 12;
	constexpr float AsRecoveryLimitS = 420.f;        // the boats have this long to be home after the fight (else the assault is closed and what is left is told)
	constexpr float AsLaunchLimitS = 90.f;           // a launch the battle never made

	const TCHAR* AsFaceName(int32 F)
	{
		static const TCHAR* Names[] = {TEXT("bow"), TEXT("stern"), TEXT("port"), TEXT("starboard"), TEXT("dorsal"), TEXT("ventral")};
		return Names[FMath::Clamp(F, 0, 5)];
	}

	/** "port" from a hatch's outward normal in the target's frame. */
	FString AsFaceOfNormal(const FVector& N)
	{
		return AsFaceName(AstraBoardCraft::FacingOfNormal(N));
	}

	FString AsShipLabel(const AstraBoardCraft::FShipFacts& F)
	{
		return F.bPlayer ? FString(TEXT("the Aquila")) : F.Name;
	}

	/** A place the objective names: bridge | engineering | captain | armory | medbay | brig | comms | hangar, or a compartment's id. */
	int32 AsObjective(const FBoardShipPlan& Plan, const FString& Name, FString& OutLabel)
	{
		struct FKey { const TCHAR* Name; const TCHAR* Kind; const TCHAR* Label; };
		static const FKey Keys[] = {{TEXT("bridge"), TEXT("bridge"), TEXT("the bridge")}, {TEXT("engineering"), TEXT("engineering"), TEXT("Main Engineering")}, {TEXT("captain"), TEXT("quarters"), TEXT("the commander's suite")},
		                            {TEXT("armory"), TEXT("armory"), TEXT("the armoury")}, {TEXT("medbay"), TEXT("medbay"), TEXT("the medbay")}, {TEXT("brig"), TEXT("brig"), TEXT("the brig")},
		                            {TEXT("comms"), TEXT("comms"), TEXT("the comms room")}, {TEXT("hangar"), TEXT("hangar"), TEXT("the boat bay")}};
		for (const FKey& K : Keys)
		{
			if (Name.Equals(K.Name, ESearchCase::IgnoreCase))
			{
				OutLabel = K.Label;
				return Plan.Objective(K.Name, K.Kind);
			}
		}
		if (Plan.Dmg.IsValid())
		{
			if (const int32* C = Plan.Dmg->CompByName.Find(FName(*Name)))
			{
				OutLabel = Plan.Map->Describe(*C);
				return *C;
			}
		}
		return INDEX_NONE;
	}
}

UAstraBattleSubsystem* UAstraBoardSubsystem::Battle() const
{
	return GetWorld() ? GetWorld()->GetSubsystem<UAstraBattleSubsystem>() : nullptr;
}

UAstraBoardSubsystem::FLeg* UAstraBoardSubsystem::LegOf(int32 Index)
{
	return Assault.Legs.IsValidIndex(Index) ? &Assault.Legs[Index] : nullptr;
}

// ================================================================================================================== the Aquila as a ship that is boarded

void UAstraBoardSubsystem::BuildAquilaPlan()
{
	AqPlan = MakeShared<FBoardShipPlan>();
	AqPlan->Class = FName(TEXT("aquila"));
	AqPlan->Label = TEXT("the Aquila");
	AqPlan->Dmg = AqDmg;
	AqPlan->Map = AqMap;
	AqPlan->Crew = 480;
	if (!AqDmg.IsValid())
	{
		return;
	}
	// her hatches are her airlocks (four to a deck pair along each beam): a boat latches to the skin where one has its outer door
	for (int32 i = 0; i < AqDmg->Comps.Num(); ++i)
	{
		const FAstraDmgComp& C = AqDmg->Comps[i];
		if (C.Kind != FName(TEXT("airlock")) || C.Status == 0)
		{
			continue;
		}
		const FVector Mid = C.Box.GetCenter();
		const bool bPort = Mid.Y < 0.0;
		FBoardShipPlan::FDock D;
		D.Id = C.Id;
		D.Comp = i;
		D.Face = bPort ? FName(TEXT("port")) : FName(TEXT("starboard"));
		D.Kind = FName(TEXT("hatch"));
		const double HullX = Mid.X / 100.0 + AqPlan->OriginInHullM().X;
		D.Pos = FVector(Mid.X, (bPort ? -1.0 : 1.0) * AstraBoardCraft::AquilaSkinM(HullX) * 100.0, Mid.Z);
		D.Normal = FVector(0.0, bPort ? -1.0 : 1.0, 0.0);
		D.Deck = C.Deck;
		AqPlan->Docks.Add(D);
	}
	UE_LOG(LogASTRA, Log, TEXT("[Board] the Aquila's hatches: %d airlocks on her beams"), AqPlan->Docks.Num());
}

// ================================================================================================================== choosing hatches

void UAstraBoardSubsystem::FillLeg(FLeg& L, const FBoardShipPlan& Plan, int32 DockIdx, const TCHAR*) const
{
	const FBoardShipPlan::FDock& D = Plan.Docks[DockIdx];
	const FAstraBoardMap& M = *Plan.Map;
	L.DockId = D.Id;
	L.BreachComp = D.Comp;
	L.HatchCm = D.Pos;
	L.OutNormal = D.Normal.GetSafeNormal();
	L.Into = -L.OutNormal;
	L.HullM = Plan.PlanToHullM(D.Pos);
	// the boat latches to the skin (D.Pos); the way in is the room's own outer wall, which may stand a little inside it: the breach is a step in from that wall
	const FBox& Room = M.GetComps()[D.Comp].Box;
	FVector Wall = D.Pos;
	if (FMath::Abs(L.OutNormal.Y) > 0.5)
	{
		Wall.Y = L.OutNormal.Y > 0.0 ? Room.Max.Y : Room.Min.Y;
	}
	else if (FMath::Abs(L.OutNormal.X) > 0.5)
	{
		Wall.X = L.OutNormal.X > 0.0 ? Room.Max.X : Room.Min.X;
	}
	else
	{
		Wall.Z = L.OutNormal.Z > 0.0 ? Room.Max.Z : Room.Min.Z;
	}
	FVector In = Wall + L.Into * 90.0;
	In.Z = M.GetComps()[D.Comp].FloorZ();
	L.InCm = M.Inset(D.Comp, In, 60.f);
	L.PlaceText = M.Describe(D.Comp);
}

bool UAstraBoardSubsystem::ChooseHatches(const FBoardShipPlan& Plan, const FString& Face, const FString& BreachId, const FShipFacts& Target, const FShipFacts& Carrier, int32 Count,
                                         TArray<int32>& OutDocks, FString& OutWhy) const
{
	OutDocks.Reset();
	if (Plan.Docks.IsEmpty())
	{
		OutWhy = TEXT("the plan of that ship has no hatch to dock at");
		return false;
	}
	// where the carrier is, in the target's own frame (m): the nearest hatch on the side it comes from
	const FVector Toward = Target.Att.UnrotateVector(Carrier.Pos - Target.Pos);
	const FVector Dir = Toward.GetSafeNormal();
	int32 First = INDEX_NONE;
	if (!BreachId.IsEmpty())
	{
		for (int32 i = 0; i < Plan.Docks.Num(); ++i)
		{
			const FBoardShipPlan::FDock& D = Plan.Docks[i];
			if (D.Id.ToString().Equals(BreachId, ESearchCase::IgnoreCase) || (Plan.Dmg.IsValid() && Plan.Dmg->Comps.IsValidIndex(D.Comp) && Plan.Dmg->Comps[D.Comp].Id.ToString().Equals(BreachId, ESearchCase::IgnoreCase)))
			{
				First = i;
				break;
			}
		}
		if (First == INDEX_NONE)
		{
			TArray<FString> Ids;
			for (int32 i = 0; i < Plan.Docks.Num() && Ids.Num() < 8; ++i)
			{
				Ids.Add(Plan.Docks[i].Id.ToString());
			}
			OutWhy = FString::Printf(TEXT("there is no hatch '%s' on that ship (hatches: %s%s)"), *BreachId, *FString::Join(Ids, TEXT(", ")), Plan.Docks.Num() > 8 ? TEXT(", ...") : TEXT(""));
			return false;
		}
	}
	TArray<int32> Cand;
	const FString WantFace = Face.ToLower();
	for (int32 i = 0; i < Plan.Docks.Num(); ++i)
	{
		const FBoardShipPlan::FDock& D = Plan.Docks[i];
		if (D.Kind == FName(TEXT("mouth")) && i != First)
		{
			continue;                                    // (a boat's mouth is no way in)
		}
		const bool bFaceOk = WantFace.IsEmpty() || WantFace == TEXT("any") ? FVector::DotProduct(D.Normal.GetSafeNormal(), Dir) > -0.2 : D.Face.ToString().Equals(WantFace, ESearchCase::IgnoreCase);
		if (bFaceOk || i == First)
		{
			Cand.Add(i);
		}
	}
	if (Cand.IsEmpty())
	{
		TArray<FString> Faces;
		for (const FBoardShipPlan::FDock& D : Plan.Docks)
		{
			Faces.AddUnique(D.Face.ToString());
		}
		OutWhy = FString::Printf(TEXT("that ship has no hatch on her %s (her hatches are on: %s)"), *Face, *FString::Join(Faces, TEXT(", ")));
		return false;
	}
	if (First == INDEX_NONE)
	{
		double Best = 1.0e18;
		for (const int32 i : Cand)
		{
			const double D = FVector::DistSquared(Plan.PlanToHullM(Plan.Docks[i].Pos), Toward);
			if (D < Best)
			{
				Best = D;
				First = i;
			}
		}
	}
	OutDocks.Add(First);
	// the others: the nearest hatches to the first on the same face, in other rooms and not on top of it
	while (OutDocks.Num() < Count)
	{
		int32 Next = INDEX_NONE;
		double Best = 1.0e18;
		const FVector P0 = Plan.PlanToHullM(Plan.Docks[First].Pos);
		for (const int32 i : Cand)
		{
			if (OutDocks.Contains(i) || Plan.Docks[i].Face != Plan.Docks[First].Face)
			{
				continue;
			}
			bool bSame = false;
			for (const int32 O : OutDocks)
			{
				bSame |= Plan.Docks[O].Comp == Plan.Docks[i].Comp || FVector::DistSquared(Plan.PlanToHullM(Plan.Docks[O].Pos), Plan.PlanToHullM(Plan.Docks[i].Pos)) < FMath::Square(9.0);
			}
			if (bSame)
			{
				continue;
			}
			const double D = FVector::DistSquared(Plan.PlanToHullM(Plan.Docks[i].Pos), P0);
			if (D < Best)
			{
				Best = D;
				Next = i;
			}
		}
		if (Next == INDEX_NONE)
		{
			break;
		}
		OutDocks.Add(Next);
	}
	return true;
}

// ================================================================================================================== the marines who go

int32 UAstraBoardSubsystem::PickMarines(int32 Total, TArray<TArray<int32>>& OutLegs) const
{
	UAstraLifeSubsystem* L = LifeSub();
	const UAstraShipSubsystem* S = ShipSub();
	for (TArray<int32>& Leg : OutLegs)
	{
		Leg.Reset();
	}
	if (!L || !L->IsRunning() || !S || !AqMap.IsValid() || OutLegs.IsEmpty() || Total <= 0)
	{
		return 0;
	}
	const FAstraLifeSim& LS = L->Sim();
	const TArray<FAstraCrewman>& Crew = S->GetRoster().Get();
	// the boat bay: whoever is nearest to it, awake and able, goes first (the commander stays on the net)
	FVector Bay = FVector::ZeroVector;
	bool bBay = false;
	if (AqDmg.IsValid())
	{
		if (const int32* C = AqDmg->CompByName.Find(FName(TEXT("d8_shuttle_bay_B1"))))
		{
			Bay = AqMap->CentreOf(*C);
			bBay = true;
		}
	}
	struct FCand { int32 Roster; int32 Rank; float Score; };
	TArray<FCand> Pool;
	for (int32 p = 0; p < LS.NumPeople(); ++p)
	{
		const FAstraLifePerson& P = LS.Person(p);
		if (P.Status != 0 || P.Act == EAstraLifeAct::Dead || P.Act == EAstraLifeAct::Patient || P.Act == EAstraLifeAct::Repair || LS.IsOffShip(p) || P.bCommandeered)
		{
			continue;
		}
		if (!Crew.IsValidIndex(P.Roster) || !Crew[P.Roster].Dept.Equals(TEXT("marines"), ESearchCase::IgnoreCase) || Crew[P.Roster].Rank.Equals(TEXT("Captain")))
		{
			continue;
		}
		FCand C;
		C.Roster = P.Roster;
		C.Rank = Crew[P.Roster].Rank.Equals(TEXT("Sergeant")) ? 1 : 0;
		C.Score = (P.Act == EAstraLifeAct::Sleep ? 1.0e5f : 0.f) + (bBay ? (float)(FVector::Dist(P.Pos, Bay) + FMath::Abs(P.Pos.Z - Bay.Z) * 3.0) : 0.f);
		Pool.Add(C);
	}
	Pool.Sort([](const FCand& A, const FCand& B) { return A.Score < B.Score; });
	const int32 N = FMath::Min(Total, Pool.Num());
	Pool.SetNum(N);
	// the sergeants lead: the best ranks take the head of each squad (six to a squad, in each boat), the rest fill in
	Pool.StableSort([](const FCand& A, const FCand& B) { return A.Rank > B.Rank; });
	const int32 Legs = OutLegs.Num();
	TArray<int32> Size;
	for (int32 i = 0; i < Legs; ++i)
	{
		Size.Add(N / Legs + (i < N % Legs ? 1 : 0));
	}
	TArray<TPair<int32, int32>> Slots;                // (leg, position in the leg): heads first
	for (int32 Pos = 0; Pos < AsMarinesPerBoat; Pos += 6)
	{
		for (int32 i = 0; i < Legs; ++i)
		{
			if (Pos < Size[i])
			{
				Slots.Emplace(i, Pos);
			}
		}
	}
	for (int32 i = 0; i < Legs; ++i)
	{
		for (int32 Pos = 0; Pos < Size[i]; ++Pos)
		{
			if (Pos % 6 != 0)
			{
				Slots.Emplace(i, Pos);
			}
		}
	}
	TArray<TArray<int32>> Fill;
	Fill.SetNum(Legs);
	for (int32 i = 0; i < Legs; ++i)
	{
		Fill[i].Init(INDEX_NONE, Size[i]);
	}
	for (int32 k = 0; k < N && k < Slots.Num(); ++k)
	{
		Fill[Slots[k].Key][Slots[k].Value] = Pool[k].Roster;
	}
	for (int32 i = 0; i < Legs; ++i)
	{
		for (const int32 R : Fill[i])
		{
			if (R != INDEX_NONE)
			{
				OutLegs[i].Add(R);
			}
		}
	}
	return N;
}

// ================================================================================================================== the order

bool UAstraBoardSubsystem::StartAssault(const FAssaultSpec& Spec, FString& OutDetail)
{
	UAstraBattleSubsystem* B = Battle();
	if (!IsReady() || !Map.IsValid() || !AqPlan.IsValid())
	{
		OutDetail = TEXT("the ship's plan is not read yet");
		return false;
	}
	if (Assault.bOn)
	{
		OutDetail = FString::Printf(TEXT("a boarding is already under way (%s): nothing else can be ordered until it is over"), *AssaultText());
		return false;
	}
	if (Phase == EPhase::Active)
	{
		OutDetail = TEXT("a boarding is already on");
		return false;
	}
	if (!B)
	{
		OutDetail = TEXT("there is no battle to fly boats in");
		return false;
	}
	FString Why;
	// the target (the Aquila when none is named), the carrier
	const int32 TargetId = Spec.Target.IsEmpty() ? B->ResolveShip(TEXT("aquila"), &Why) : B->ResolveShip(Spec.Target, &Why);
	if (TargetId < 0)
	{
		OutDetail = Why.IsEmpty() ? FString(TEXT("no such target")) : Why;
		return false;
	}
	FShipFacts T;
	if (!B->ShipFacts(TargetId, T))
	{
		OutDetail = TEXT("no such target");
		return false;
	}
	int32 CarrierId = INDEX_NONE;
	if (!Spec.Source.IsEmpty())
	{
		CarrierId = B->ResolveShip(Spec.Source, &Why);
		if (CarrierId < 0)
		{
			OutDetail = Why.IsEmpty() ? FString(TEXT("no such carrier")) : Why;
			return false;
		}
	}
	else
	{
		// no carrier named: the Aquila's own boats against another ship; the Mandate's carrier with the most boats free (and the nearest) against the Aquila
		TArray<FShipFacts> All;
		B->ListShipFacts(All);
		double BestScore = -1.0e18;
		for (const FShipFacts& F : All)
		{
			if (F.Id == TargetId || F.bDisabled || (T.bPlayer ? F.Side != 1 : !F.bPlayer))
			{
				continue;
			}
			FAssess A;
			if (!B->AssessBoarding(F.Id, TargetId, A) || !A.bCarrierOk)
			{
				continue;
			}
			const double Score = A.BerthsFree * 1000.0 - FVector::Dist(F.Pos, T.Pos) / 1000.0;
			if (Score > BestScore)
			{
				BestScore = Score;
				CarrierId = F.Id;
			}
		}
		if (CarrierId == INDEX_NONE)
		{
			OutDetail = T.bPlayer ? FString(TEXT("no Mandate ship has a boarding craft free")) : FString(TEXT("the Aquila has no Kestrel free"));
			return false;
		}
	}
	FShipFacts C;
	if (!B->ShipFacts(CarrierId, C))
	{
		OutDetail = TEXT("no such carrier");
		return false;
	}
	if (C.Side == 2 || T.Side == 2)
	{
		OutDetail = FString::Printf(TEXT("%s takes no part in this war: nobody boards or sends boats from her"), *AsShipLabel(C.Side == 2 ? C : T));
		return false;
	}
	if (C.Side == T.Side)
	{
		OutDetail = FString::Printf(TEXT("%s and %s are on the same side: nobody boards a friend"), *AsShipLabel(C), *AsShipLabel(T));
		return false;
	}
	FAssess Ass;
	if (!B->AssessBoarding(CarrierId, TargetId, Ass))
	{
		OutDetail = TEXT("no such target");
		return false;
	}
	if (!Ass.bTargetOk)
	{
		OutDetail = FString::Printf(TEXT("%s cannot be boarded: %s"), *AsShipLabel(T), *Ass.TargetWhy);
		return false;
	}
	if (!Ass.bCarrierOk)
	{
		OutDetail = FString::Printf(TEXT("%s cannot send boats: %s"), *AsShipLabel(C), *Ass.CarrierWhy);
		return false;
	}
	// who attacks and where it is fought: the Mandate against the Aquila is the Captain's own fight on her decks; every other is the simulation's alone
	FAssault A;
	A.bOn = true;
	A.Order = NextOrder++;
	A.Attacker = C.Side == 1 ? ESide::Mandate : ESide::Aquila;
	A.bObserved = T.bPlayer && A.Attacker == ESide::Mandate;
	A.bRoster = C.bPlayer;
	A.CarrierId = CarrierId;
	A.TargetId = TargetId;
	A.CarrierName = AsShipLabel(C);
	A.TargetName = AsShipLabel(T);
	A.CarrierClass = C.ClassText;
	A.TargetClassText = T.ClassText;
	A.TargetClass = T.ClassKey;
	A.Objective = Spec.Objective.IsEmpty() ? (A.Attacker == ESide::Mandate ? FString(TEXT("engineering")) : FString(TEXT("captain"))) : Spec.Objective;
	A.By = Spec.By;
	A.bLockdown = Spec.bLockdown;
	A.bCaptain = Spec.bCaptain;
	A.Spec = Spec;
	A.EtaS = Ass.EtaS;
	if (T.bPlayer && !A.bObserved)
	{
		OutDetail = TEXT("the Aquila does not board herself");
		return false;
	}
	if (Spec.bCaptain)
	{
		if (!A.bRoster)
		{
			OutDetail = TEXT("the Captain rides only in the Aquila's own boats, with her marines");
			return false;
		}
		if (!CaptainOnFoot())
		{
			OutDetail = TEXT("the Captain is not on foot aboard (in a Falcon, a pod, or planetside): he cannot go with the marines");
			return false;
		}
		if (Ride != ERide::None)
		{
			OutDetail = TEXT("the Captain is already away with the marines");
			return false;
		}
	}
	// her plan: the Aquila's is read; any other ship's is read on a worker (a second or two the first time) before the boats are sent
	if (T.bPlayer)
	{
		A.PlanKey = TEXT("aquila");
		Assault = MoveTemp(A);
		return LaunchAssault(OutDetail);
	}
	const FName Class = T.ClassKey;
	if (Class.IsNone())
	{
		OutDetail = FString::Printf(TEXT("%s is not a ship with a plan of her decks"), *AsShipLabel(T));
		return false;
	}
	bool bStop = false;
	if (AstraBoardPlans::Peek(Class).IsValid())
	{
		A.PlanKey = Class.ToString();
		Assault = MoveTemp(A);
		return LaunchAssault(OutDetail);
	}
	if (AstraBoardPlans::PathFor(Class, bStop).IsEmpty())
	{
		OutDetail = FString::Printf(TEXT("there is no plan of the %s class: nobody knows her decks"), *Class.ToString());
		return false;
	}
	A.PlanKey = Class.ToString();
	A.bPlanWait = true;
	A.PlanSinceS = FPlatformTime::Seconds();
	A.PlanFuture = Async(EAsyncExecution::ThreadPool, [Class]() -> TSharedPtr<FBoardShipPlan>
	{
		FString W;
		return AstraBoardPlans::Load(Class, W);
	});
	Assault = MoveTemp(A);
	OutDetail = FString::Printf(TEXT("order %d accepted: %s's decks are being read, then %s sends the boats"), Assault.Order, *Assault.TargetName, *Assault.CarrierName);
	UE_LOG(LogASTRA, Log, TEXT("[Board] %s"), *OutDetail);
	return true;
}

bool UAstraBoardSubsystem::LaunchAssault(FString& OutDetail)
{
	UAstraBattleSubsystem* B = Battle();
	FShipFacts T, C;
	if (!B || !B->ShipFacts(Assault.TargetId, T) || !B->ShipFacts(Assault.CarrierId, C))
	{
		OutDetail = TEXT("the ships are gone");
		CloseAssault(TEXT("the ships are gone"));
		return false;
	}
	const TSharedPtr<FBoardShipPlan> Plan = Assault.PlanKey == TEXT("aquila") ? AqPlan : AstraBoardPlans::Peek(FName(*Assault.PlanKey));
	if (!Plan.IsValid() || !Plan->IsReady())
	{
		OutDetail = TEXT("the plan of her decks could not be read");
		CloseAssault(TEXT("no plan"));
		return false;
	}
	FAssess Ass;
	B->AssessBoarding(Assault.CarrierId, Assault.TargetId, Ass);
	if (!Ass.bCarrierOk)
	{
		OutDetail = FString::Printf(TEXT("%s cannot send boats: %s"), *Assault.CarrierName, *Ass.CarrierWhy);
		CloseAssault(TEXT("no boat"));
		return false;
	}
	const AstraBoardCraft::FKind* Kind = AstraBoardCraft::KindByKey(FName(*Ass.KindKey));
	if (!Kind)
	{
		OutDetail = TEXT("her boats are not known");
		CloseAssault(TEXT("no kind"));
		return false;
	}
	// how many boats and how many men in each
	int32 Boats = Assault.Spec.Craft > 0 ? Assault.Spec.Craft : FMath::Min(2, Ass.BerthsFree);
	Boats = FMath::Clamp(Boats, 1, FMath::Max(1, Ass.BerthsFree));
	TArray<TArray<int32>> Marines;                    // (the Aquila's) roster indices by boat
	TArray<int32> Men;
	if (Assault.bRoster)
	{
		int32 Total = Assault.Spec.Boarders > 0 ? Assault.Spec.Boarders : Boats * Kind->Men;
		Total = FMath::Min(Total, Boats * Kind->Men);
		Marines.SetNum(Boats);
		const int32 Picked = PickMarines(Total, Marines);
		UAstraLifeSubsystem* L = LifeSub();
		if (L && L->IsRunning())
		{
			if (Picked <= 0)
			{
				OutDetail = TEXT("no marine is free to go (they are all down, away or in a fight)");
				CloseAssault(TEXT("no marines"));
				return false;
			}
			Boats = FMath::Min(Boats, FMath::DivideAndRoundUp(Picked, Kind->Men));
			Marines.SetNum(Boats);
			// (PickMarines dealt them over the boats it was given; deal again over the boats there will be)
			TArray<int32> All;
			for (const TArray<int32>& Leg : Marines) { All.Append(Leg); }
			Marines.Reset();
			Marines.SetNum(Boats);
			for (int32 i = 0; i < All.Num(); ++i) { Marines[i % Boats].Add(All[i]); }
			for (const TArray<int32>& Leg : Marines) { Men.Add(Leg.Num()); }
		}
		else
		{
			for (int32 i = 0; i < Boats; ++i)
			{
				Men.Add(FMath::Min(Kind->Men, FMath::Max(1, Total / Boats)));          // a bench world: nameless marines
			}
			Marines.Reset();
		}
	}
	else
	{
		const int32 Total = Assault.Spec.Boarders > 0 ? FMath::Min(Assault.Spec.Boarders, Boats * Kind->Men) : Boats * Kind->Men;
		for (int32 i = 0; i < Boats; ++i)
		{
			Men.Add(FMath::Max(1, Total / Boats + (i < Total % Boats ? 1 : 0)));
		}
	}
	TArray<int32> Docks;
	FString HatchWhy;
	if (!ChooseHatches(*Plan, Assault.Spec.Face, Assault.Spec.Breach, T, C, Boats, Docks, HatchWhy))
	{
		OutDetail = HatchWhy;
		CloseAssault(TEXT("no hatch"));
		return false;
	}
	Boats = FMath::Min(Boats, Docks.Num());
	AstraBoardCraft::FLaunch Req;
	Req.CarrierId = Assault.CarrierId;
	Req.TargetId = Assault.TargetId;
	Req.Order = Assault.Order;
	Req.bCaptain = Assault.bCaptain;
	Req.FirstS = Assault.bRoster ? 25.f : 4.f;
	Req.GapS = 3.f;
	Assault.Legs.Reset();
	for (int32 i = 0; i < Boats; ++i)
	{
		FLeg L;
		L.Index = i;
		FillLeg(L, *Plan, Docks[i], nullptr);
		L.Men = Men.IsValidIndex(i) ? Men[i] : Kind->Men;
		const UAstraShipSubsystem* S = ShipSub();
		if (Marines.IsValidIndex(i) && S)
		{
			for (const int32 R : Marines[i])
			{
				FArrival Ar;
				Ar.Roster = R;
				Ar.Name = S->GetRoster().Get().IsValidIndex(R) ? S->GetRoster().Get()[R].Name() : FString();
				L.Arrivals.Add(Ar);
			}
		}
		else
		{
			L.Arrivals.SetNum(L.Men);                    // nameless: the simulation names them
		}
		Req.Docks.Add({L.HullM, L.OutNormal, L.DockId});
		Req.Men.Add(L.Men);
		Assault.Legs.Add(MoveTemp(L));
	}
	FLaunchResult R;
	if (!B->LaunchBoarding(Req, R))
	{
		OutDetail = R.Why.IsEmpty() ? FString(TEXT("the boats could not be launched")) : R.Why;
		CloseAssault(TEXT("not launched"));
		return false;
	}
	Assault.Legs.SetNum(FMath::Min(Assault.Legs.Num(), R.Craft));
	Assault.EtaS = R.EtaS;
	Assault.LaunchT = Assault.T;
	Assault.bLaunched = true;
	// the marines who go leave the ship's life (they are in the boats)
	if (Assault.bRoster)
	{
		UAstraLifeSubsystem* L = LifeSub();
		if (L && L->IsRunning())
		{
			for (FLeg& Leg : Assault.Legs)
			{
				for (const FArrival& Ar : Leg.Arrivals)
				{
					const int32 P = L->Sim().PersonOfRoster(Ar.Roster);
					if (P != INDEX_NONE)
					{
						L->ReleaseBodyOf(P);
						L->Sim().SetAway(P, FString::Printf(TEXT("aboard a Kestrel on its way to board %s"), *Assault.TargetName));
					}
				}
			}
		}
	}
	// the facts that go back to who ordered it
	FString Hatches;
	int32 Total = 0;
	for (const FLeg& L : Assault.Legs)
	{
		Hatches += (Hatches.IsEmpty() ? TEXT("") : TEXT(", ")) + FString::Printf(TEXT("%s (%s)"), *L.DockId.ToString(), *L.PlaceText);
		Total += L.Men;
	}
	FString Warn;
	if (Ass.PdChannels > 0)
	{
		Warn += FString::Printf(TEXT(" %s's point defence is up (%d channels, %.0f km): boats that cross it are shot at."), *Assault.TargetName, Ass.PdChannels, Ass.PdRangeKm);
	}
	if (Ass.EnemyCraftNear > 0)
	{
		Warn += FString::Printf(TEXT(" %d of her craft are about her and will fire on the boats."), Ass.EnemyCraftNear);
	}
	if (Assault.bCaptain)
	{
		Warn += FString::Printf(TEXT(" The Captain goes with the marines in the first boat: if it is shot down, he is in it."));
	}
	const FString Face = AsFaceOfNormal(Assault.Legs[0].OutNormal);
	if (Ass.bShieldsKnown && Ass.ShieldFrac[AstraBoardCraft::FacingOfNormal(Assault.Legs[0].OutNormal)] > AstraBoardCraft::ShieldDownFrac)
	{
		Warn += FString::Printf(TEXT(" The shield on her %s face holds (%.0f%%): the boats cannot dock through it and will turn back."), *Face, Ass.ShieldFrac[AstraBoardCraft::FacingOfNormal(Assault.Legs[0].OutNormal)] * 100.f);
	}
	OutDetail = FString::Printf(TEXT("order %d: %s launches %d %s%s (%d %s) at %s, hatches %s; first at the hull in about %.0f s.%s"), Assault.Order, *Assault.CarrierName, Assault.Legs.Num(), Kind->Callsign,
	                            Assault.Legs.Num() > 1 ? TEXT("s") : TEXT(""), Total, Assault.bRoster ? TEXT("marines") : TEXT("boarders"), *Assault.TargetName, *Hatches, R.EtaS, *Warn);
	UE_LOG(LogASTRA, Log, TEXT("[Board] %s"), *OutDetail);
	if (!R.Why.IsEmpty())
	{
		OutDetail += TEXT(" (") + R.Why + TEXT(")");
	}
	AssaultNote.Add(FString::Printf(TEXT("order %d placed%s%s"), Assault.Order, Assault.By.IsEmpty() ? TEXT("") : TEXT(" by "), *Assault.By));
	if (!Assault.bObserved)
	{
		Tell(FString::Printf(TEXT("%s is sending %d %s%s with %d %s to board %s"), *Assault.CarrierName, Assault.Legs.Num(), Kind->Callsign, Assault.Legs.Num() > 1 ? TEXT("s") : TEXT(""), Total,
		                     Assault.bRoster ? TEXT("marines") : TEXT("boarders"), *Assault.TargetName), Assault.bRoster || Assault.TargetName == TEXT("the Aquila"));
	}
	return true;
}

FString UAstraBoardSubsystem::AssaultText() const
{
	if (!Assault.bOn)
	{
		return TEXT("none");
	}
	int32 Flying = 0, Latched = 0, Through = 0, Lost = 0, Back = 0;
	for (const FLeg& L : Assault.Legs)
	{
		Flying += L.State == FLeg::EState::Flying || L.State == FLeg::EState::Ordered;
		Latched += L.State == FLeg::EState::Latched;
		Through += L.State == FLeg::EState::Through;
		Lost += L.State == FLeg::EState::Lost;
		Back += L.State == FLeg::EState::Home || L.State == FLeg::EState::TurnedBack;
	}
	return FString::Printf(TEXT("order %d: %s boards %s, %d boats (%d flying, %d latched, %d through, %d lost, %d back)"), Assault.Order, *Assault.CarrierName, *Assault.TargetName, Assault.Legs.Num(), Flying,
	                       Latched, Through, Lost, Back);
}

// ================================================================================================================== what the boats do

void UAstraBoardSubsystem::TickAssault(float Dt)
{
	if (!Assault.bOn)
	{
		return;
	}
	Assault.T += Dt;
	if (Assault.bPlanWait)
	{
		if (!Assault.PlanFuture.IsReady())
		{
			if (FPlatformTime::Seconds() - Assault.PlanSinceS > 40.0)
			{
				Tell(FString::Printf(TEXT("the boarding of %s could not be set up: her decks could not be read in time"), *Assault.TargetName), false);
				CloseAssault(TEXT("plan too slow"));
			}
			return;
		}
		const TSharedPtr<FBoardShipPlan> P = Assault.PlanFuture.Get();
		Assault.PlanFuture = TFuture<TSharedPtr<FBoardShipPlan>>();
		Assault.bPlanWait = false;
		FString D;
		if (!P.IsValid() || !LaunchAssault(D))
		{
			Tell(FString::Printf(TEXT("the boarding of %s is off: %s"), *Assault.TargetName, D.IsEmpty() ? TEXT("her decks could not be read") : *D), false);
			CloseAssault(TEXT("not launched"));
		}
		return;
	}
	if (!Assault.bLaunched)
	{
		return;
	}
	if (UAstraBattleSubsystem* B = Battle())
	{
		TArray<AstraBoardCraft::FCraftEvent> Evs;
		B->ConsumeBoardEvents(Evs);
		for (const AstraBoardCraft::FCraftEvent& E : Evs)
		{
			if (E.Order == Assault.Order)
			{
				OnCraftEvent(E);
			}
		}
	}
	if (!Assault.bOn)
	{
		return;
	}
	// a launch the battle never made
	if (Assault.T - Assault.LaunchT > AsLaunchLimitS)
	{
		bool bAny = false;
		for (const FLeg& L : Assault.Legs) { bAny |= L.State != FLeg::EState::Ordered; }
		if (!bAny)
		{
			Tell(FString::Printf(TEXT("the boats of %s never left"), *Assault.CarrierName), false);
			CloseAssault(TEXT("the boats never left"));
			return;
		}
	}
	// the boats are all resolved and no fight is on: it is over
	bool bAllDone = !Assault.Legs.IsEmpty();
	bool bAnyLatched = false;
	for (const FLeg& L : Assault.Legs)
	{
		bAllDone &= L.Resolved();
		bAnyLatched |= L.State == FLeg::EState::Latched;
	}
	if (bAllDone && Phase != EPhase::Active)
	{
		CloseAssault(TEXT("the boats are all accounted for"));
		return;
	}
	// every boat was shot down or turned back before one touched: there is no boarding, and nobody to wait for
	if (Assault.bObserved && Assault.bSceneBegun && Phase == EPhase::Active)
	{
		bool bNone = true;
		for (const FLeg& L : Assault.Legs)
		{
			bNone &= !L.bLanded && (L.State == FLeg::EState::Lost || L.State == FLeg::EState::TurnedBack || L.State == FLeg::EState::Home);
		}
		if (bNone)
		{
			Tell(TEXT("not one boarder reached the ship: every boat was destroyed or turned back; the marines stand down"), true);
			Finish(TEXT("no boarder came"));
		}
	}
	// no fight any more but boats still latched (or the fight over): they let go
	if (!Assault.bDeparting && Assault.bSceneBegun && Phase != EPhase::Active)
	{
		EndAssaultFight(TEXT("the fight is over"));
	}
	if (Assault.bDeparting)
	{
		Assault.DoneT += Dt;
		if (Assault.DoneT > AsRecoveryLimitS)
		{
			CloseAssault(TEXT("the boats did not come home in time"));
		}
	}
	(void)bAnyLatched;
}

void UAstraBoardSubsystem::OnCraftEvent(const AstraBoardCraft::FCraftEvent& E)
{
	FLeg* L = LegOf(E.Leg);
	if (!L)
	{
		return;
	}
	if (!E.CraftName.IsEmpty())
	{
		L->CraftName = E.CraftName;
	}
	L->CraftId = E.CraftId;
	switch (E.Kind)
	{
	case AstraBoardCraft::EEventKind::Launched:
	{
		L->State = FLeg::EState::Flying;
		L->bSailing = true;
		if (E.bCaptain && Assault.bCaptain)
		{
			RideBegin(*L);                               // the Captain is in this boat: the screen goes dark, he is in its troop bay
		}
		if (Assault.bObserved && !Assault.bSceneBegun)
		{
			BeginObservedScene();
		}
		else if (!Assault.bObserved)
		{
			UE_LOG(LogASTRA, Log, TEXT("[Board] %s is away with %d %s"), *L->CraftName, L->Men, Assault.bRoster ? TEXT("marines") : TEXT("boarders"));
		}
		break;
	}
	case AstraBoardCraft::EEventKind::Docked:
	{
		L->State = FLeg::EState::Latched;
		if (Assault.bObserved)
		{
			if (!Assault.bSceneBegun || Phase != EPhase::Active)
			{
				break;                                   // (the fight is over or never began: nobody goes through)
			}
			OpenBreachAt(*L);
			Fight.ReleaseParty(L->Index, 1.0f);
			L->bLanded = true;
			L->State = FLeg::EState::Through;
		}
		else
		{
			if (Phase == EPhase::Active && !Assault.bSceneBegun)
			{
				// another fight holds the scene (the Mandate are on the Aquila's decks): the marines wait in their boat at the hatch
				Tell(FString::Printf(TEXT("%s is latched to %s but the fight on the Aquila's decks comes first: the marines wait in their boat"), *L->CraftName, *Assault.TargetName), false);
				break;
			}
			if (Assault.bSceneBegun && Phase != EPhase::Active)
			{
				break;                                   // (the fight is over: the boat only waits to be told to let go)
			}
			if (!Assault.bSceneBegun && !BeginRemoteScene())
			{
				Tell(FString::Printf(TEXT("%s could not cut in at %s: the boarding is off"), *L->CraftName, *L->PlaceText), false);
				EndAssaultFight(TEXT("no scene"));
				break;
			}
			LandLeg(*L);
			if (E.bCaptain && Ride == ERide::Out)
			{
				RideArrive(*L);                          // his boat has cut in: he goes onto the other ship's decks
			}
			}
			break;
			}
			case AstraBoardCraft::EEventKind::Destroyed:
			{
			const bool bAboard = E.bMenAboard && !L->bLanded;
			L->State = FLeg::EState::Lost;
			L->bSailing = false;
			if (L->Index == RideLeg && Ride == ERide::Out)
			{
			CaptainLostInBoat(E.Cause);                  // he was in it
			}
			else if (L->Index == RideLeg && Ride == ERide::Aboard)
			{
			// his boat is gone with him on the other ship: another boat that is still there takes him off, or nothing does
			int32 Other = INDEX_NONE;
			for (const FLeg& O : Assault.Legs)
			{
				if (O.Index != L->Index && (O.State == FLeg::EState::Through || O.State == FLeg::EState::Latched))
				{
					Other = O.Index;
					break;
				}
			}
			if (Other != INDEX_NONE)
			{
				RideLeg = Other;
			}
			else
			{
				CaptainLeftScene(TEXT("his boat is gone"));
				if (UAstraShipSubsystem* S = ShipSub())
				{
					S->GetInterior().CaptainDied(TEXT("stranded on a ship with no boat left to take him off"));
				}
			}
			}
		if (bAboard)
		{
			if (Assault.bObserved && Phase == EPhase::Active)
			{
				const int32 N = Fight.LoseParty(L->Index, E.Cause);
				Tell(FString::Printf(TEXT("%s has been destroyed (%s): its %d boarders are lost with it"), *L->CraftName, *E.Cause, N), true);
			}
			else if (Assault.bRoster)
			{
				MarkMarinesLost(*L, E.Cause);
				Tell(FString::Printf(TEXT("%s was destroyed (%s) with %d marines aboard"), *L->CraftName, *E.Cause, L->Men), true);
			}
			else
			{
				Tell(FString::Printf(TEXT("%s was destroyed (%s): its %d men are lost with it"), *L->CraftName, *E.Cause, L->Men), Assault.TargetName == TEXT("the Aquila"));
			}
		}
		else
		{
			Tell(FString::Printf(TEXT("%s was destroyed (%s)"), *L->CraftName, *E.Cause), false);
		}
		break;
	}
	case AstraBoardCraft::EEventKind::Aborted:
	{
		L->State = FLeg::EState::TurnedBack;
		if (L->Index == RideLeg && Ride == ERide::Out)
		{
			Ride = ERide::Home;                          // his boat turned back: he rides home in it
			RideStep = 31;
			RideT = 0.f;
		}
		if (Assault.bObserved && Phase == EPhase::Active)
		{
			Fight.RecallParty(L->Index);
		}
		Tell(FString::Printf(TEXT("%s has turned back (%s)"), *L->CraftName, *E.Cause), Assault.bRoster || Assault.TargetName == TEXT("the Aquila"));
		break;
	}
	case AstraBoardCraft::EEventKind::Departed:
	{
		L->bSailing = true;
		break;
	}
	case AstraBoardCraft::EEventKind::Recovered:
	{
		L->State = FLeg::EState::Home;
		L->bSailing = false;
		if (Assault.bRoster)
		{
			ReturnMarines(*L, true);
		}
		UE_LOG(LogASTRA, Log, TEXT("[Board] %s is home"), *L->CraftName);
		break;
	}
	case AstraBoardCraft::EEventKind::Lost:
	{
		L->State = FLeg::EState::Lost;
		L->bSailing = false;
		if (Assault.bRoster)
		{
			MarkMarinesLost(*L, TEXT("their boat could not come home"));
		}
		Tell(FString::Printf(TEXT("%s could not come home and drifts away"), *L->CraftName), Assault.bRoster);
		break;
	}
	}
}

// ================================================================================================================== the scenes

void UAstraBoardSubsystem::ResetScene(EMode NewMode)
{
	if (Phase == EPhase::Over)
	{
		Finish(TEXT("a new boarding begins"));
	}
	ClearBodies();
	for (AAstraBoardBreach* B : Breaches)
	{
		if (B && B->IsOpen())
		{
			B->Close();
		}
	}
	Mode = NewMode;
	if (NewMode == EMode::Observed)
	{
		Map = AqMap;
		Dmg = AqDmg;
		ScenePlan.Reset();
	}
	Fight = FAstraBoardSim();
	MarineUnits.Reset();
	RosterOfUnit.Reset();
	PersonOfUnit.Reset();
	HarmTold.Reset();
	ToldDown.Reset();
	Log.Reset();
	LastShotSound.Reset();
	bToldContact = false;
	bToldTakeover = false;
	TakeoverFuse = -1.f;
	CasualtyT = 0.f;
	ToldMarinesLost = ToldMandateLost = 0;
	Since = 0.f;
	AfterEnd = 0.f;
	bBreachOpen = false;
	SealedByUs.Reset();
}

void UAstraBoardSubsystem::BeginObservedScene()
{
	FLeg& L0 = Assault.Legs[0];
	FString ObjLabel;
	const int32 Obj = AsObjective(*AqPlan, Assault.Objective, ObjLabel);
	if (Obj == INDEX_NONE)
	{
		Tell(FString::Printf(TEXT("the boarders have nothing to go for: the plan has no '%s'"), *Assault.Objective), false);
		return;
	}
	ResetScene(EMode::Observed);
	Fight.Init(Map.ToSharedRef(), GAstraDeterministic ? 7001 : (int32)(FDateTime::Now().GetTicks() & 0x7fffffff));
	Fight.SetMission(ESide::Mandate, L0.BreachComp, L0.InCm, Obj, false);
	int32 Men = 0;
	for (FLeg& L : Assault.Legs)
	{
		// the boats are on their way: the men wait in them (the holders reckon their ambush against the time they will be at the hatch)
		const float Eta = Assault.EtaS + 3.f * L.Index;
		Fight.LandParty(ESide::Mandate, L.Index, L.Arrivals, L.BreachComp, L.InCm, Eta, 5);
		Men += L.Men;
	}
	Assault.bSceneBegun = true;
	Assault.bFightSeen = true;
	// the alarm: the marines called, the Captain in the fight, the section bulkheads round the hatches, general quarters
	FString Places;
	for (const FLeg& L : Assault.Legs)
	{
		Places += (Places.IsEmpty() ? TEXT("") : TEXT(", ")) + L.PlaceText;
	}
	EnterObserved(Assault.CarrierName, L0.BreachComp, L0.InCm, Assault.bLockdown);
	for (const FLeg& L : Assault.Legs)
	{
		if (Assault.bLockdown && L.BreachComp != L0.BreachComp)
		{
			SealSections(L.BreachComp, L.InCm);
		}
	}
	Tell(FString::Printf(TEXT("%s has launched %d assault craft at the Aquila (about %d boarders): they will be at her hull in about %.0f seconds, at %s, going for %s; the section bulkheads are %s and the marines are being called to arms"),
	                     *Assault.CarrierName, Assault.Legs.Num(), Men, Assault.EtaS, *Places, *ObjLabel, Assault.bLockdown ? TEXT("closing") : TEXT("open")), true);
}

bool UAstraBoardSubsystem::BeginRemoteScene()
{
	const TSharedPtr<FBoardShipPlan> Plan = AstraBoardPlans::Peek(FName(*Assault.PlanKey));
	if (!Plan.IsValid() || !Plan->IsReady())
	{
		return false;
	}
	FLeg* First = nullptr;
	for (FLeg& L : Assault.Legs)
	{
		if (L.State == FLeg::EState::Latched)
		{
			First = &L;
			break;
		}
	}
	if (!First)
	{
		return false;
	}
	ResetScene(EMode::Remote);
	ScenePlan = Plan;
	Map = Plan->Map;
	Dmg = Plan->Dmg;
	Fight.Init(Map.ToSharedRef(), GAstraDeterministic ? 7001 : (int32)(FDateTime::Now().GetTicks() & 0x7fffffff));
	FShipFacts T;
	const UAstraBattleSubsystem* B = Battle();
	const bool bFacts = B && B->ShipFacts(Assault.TargetId, T);
	AstraBoardScene::FSpec S;
	S.Attacker = Assault.Attacker;
	S.Breach = First->BreachComp;
	S.Objective = Assault.Objective;
	S.Attackers = 0;
	S.bSweep = bFacts && T.bDisabled;
	S.bShipSensors = bFacts && !T.bDisabled;
	S.Seed = GAstraDeterministic ? 7 : (int32)(FDateTime::Now().GetTicks() & 0xffff);
	// a ship that has lost her power is a poor place to defend: fewer on their feet, the bulkheads that are shut stay shut
	if (bFacts && T.bDisabled)
	{
		S.PostShare = 0.55f;
		S.Roaming = 3;
	}
	const AstraBoardScene::FResult R = AstraBoardScene::Build(Fight, *Plan, S);
	if (!R.bOk)
	{
		UE_LOG(LogASTRA, Log, TEXT("[Board] the scene on %s could not be made: %s"), *Assault.TargetName, *R.Why);
		Mode = EMode::Observed;
		Map = AqMap;
		Dmg = AqDmg;
		ScenePlan.Reset();
		return false;
	}
	First->InCm = R.BreachPos;
	BreachAt = R.BreachPos;
	BreachText = Map->Describe(R.Breach);
	Source = Assault.CarrierName;
	CapHp = 100.f;
	bCapDown = false;
	bCaptainIn = false;
	Assault.bSceneBegun = true;
	Assault.bFightSeen = true;
	Phase = EPhase::Active;
	Tell(FString::Printf(TEXT("%s's %s has latched to %s at %s and cut in: %d %s are through, going for %s; she holds about %d of her people at their posts"), *Assault.CarrierName,
	                     *First->CraftName, *Assault.TargetName, *BreachText, First->Men, Assault.bRoster ? TEXT("marines") : TEXT("boarders"), *R.ObjectiveName, R.Defenders), true);
	return true;
}

void UAstraBoardSubsystem::LandLeg(FLeg& L)
{
	if (L.bLanded)
	{
		return;
	}
	const TArray<int32> Squads = Fight.LandParty(Assault.Attacker, L.Index, L.Arrivals, L.BreachComp, L.InCm, 0.f, Assault.bRoster ? 6 : 5, FString());
	Fight.ReleaseParty(L.Index, 1.0f);
	L.bLanded = true;
	L.State = FLeg::EState::Through;
	if (Assault.bRoster)
	{
		UAstraLifeSubsystem* Life2 = LifeSub();
		for (const FUnit& U : Fight.Units())
		{
			if (U.Party == L.Index && U.Roster != INDEX_NONE)
			{
				MarineUnits.Add(U.Id);
				RosterOfUnit.Add(U.Id, U.Roster);
				const int32 Person = Life2 && Life2->IsRunning() ? Life2->Sim().PersonOfRoster(U.Roster) : INDEX_NONE;
				if (Person != INDEX_NONE)
				{
					PersonOfUnit.Add(U.Id, Person);
				}
			}
		}
	}
	Tell(FString::Printf(TEXT("%s has cut in at %s: %d %s are through"), *L.CraftName, *L.PlaceText, L.Men, Assault.bRoster ? TEXT("marines") : TEXT("boarders")), Assault.bRoster);
	(void)Squads;
}

void UAstraBoardSubsystem::OpenBreachAt(FLeg& L)
{
	UWorld* W = GetWorld();
	if (!W)
	{
		return;
	}
	if (!bBreachOpen)
	{
		bBreachOpen = true;
		BreachAt = L.InCm;
	}
	FActorSpawnParameters P;
	P.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	AAstraBoardBreach* Actor = W->SpawnActor<AAstraBoardBreach>(L.InCm, FRotator::ZeroRotator, P);
	if (Actor)
	{
		Actor->Open(L.InCm, L.Into);
		Breaches.Add(Actor);
		L.Breach = Breaches.Num() - 1;
	}
	if (UAstraCombatFx* X = FxSub())
	{
		X->Impact(L.InCm + FVector(0.0, 0.0, 150.0), L.Into, UAstraCombatFx::ESurface::Metal);
		X->PlaySoundAt(TEXT("/Game/ASTRA/Audio/SW_Blast_Inside.SW_Blast_Inside"), L.InCm + FVector(0.0, 0.0, 150.0), 1.f, 1.f);
	}
	Tell(FString::Printf(TEXT("the hull is cut open at %s: boarders are coming through"), *L.PlaceText), true);
}

// ================================================================================================================== the marines of a boat

void UAstraBoardSubsystem::ReturnMarines(FLeg& L, bool bAlive)
{
	UAstraLifeSubsystem* Life2 = LifeSub();
	UAstraShipSubsystem* S = ShipSub();
	if (!Life2 || !Life2->IsRunning() || !AqMap.IsValid())
	{
		return;
	}
	FVector Bay = FVector::ZeroVector;
	if (AqDmg.IsValid())
	{
		if (const int32* C = AqDmg->CompByName.Find(FName(TEXT("d8_shuttle_bay_B1"))))
		{
			Bay = AqMap->CentreOf(*C);
		}
	}
	int32 Home = 0;
	for (const FArrival& Ar : L.Arrivals)
	{
		const int32 P = Life2->Sim().PersonOfRoster(Ar.Roster);
		if (P == INDEX_NONE || !bAlive)
		{
			continue;
		}
		if (S && S->GetRoster().Get().IsValidIndex(Ar.Roster) && S->GetRoster().Get()[Ar.Roster].Status == 2)
		{
			continue;                                    // dead: he does not come home on his feet
		}
		const FAstraLifePerson& Pe = Life2->Sim().Person(P);
		if (!Pe.bAway)
		{
			continue;
		}
		Life2->Sim().PlaceTransported(P, Bay + FVector(FMath::FRandRange(-250.f, 250.f), FMath::FRandRange(-250.f, 250.f), 0.f), 0.f, 4.f);
		++Home;
	}
	if (Home > 0)
	{
		Tell(FString::Printf(TEXT("%s is back in the boat bay: %d marines aboard"), *L.CraftName, Home), false);
	}
}

void UAstraBoardSubsystem::MarkMarinesLost(FLeg& L, const FString& Cause)
{
	UAstraShipSubsystem* S = ShipSub();
	if (!S)
	{
		return;
	}
	for (const FArrival& Ar : L.Arrivals)
	{
		if (Ar.Roster != INDEX_NONE && !HarmTold.Contains(Ar.Roster))
		{
			HarmTold.Add(Ar.Roster);
			S->HarmPerson(Ar.Roster, true, Cause);
		}
	}
}

// ================================================================================================================== the end

void UAstraBoardSubsystem::EndAssaultFight(const TCHAR* Why)
{
	if (!Assault.bOn || Assault.bDeparting)
	{
		return;
	}
	Assault.bDeparting = true;
	Assault.DoneT = 0.f;
	if (UAstraBattleSubsystem* B = Battle())
	{
		const int32 Called = B->AbortBoardingOrder(Assault.Order, Why);
		const int32 Let = B->DepartBoardingOrder(Assault.Order);
		UE_LOG(LogASTRA, Log, TEXT("[Board] the boats of order %d are told to go home (%s): %d turned back, %d let go"), Assault.Order, Why, Called, Let);
	}
}

void UAstraBoardSubsystem::CloseAssault(const TCHAR* Why)
{
	if (!Assault.bOn)
	{
		return;
	}
	UE_LOG(LogASTRA, Log, TEXT("[Board] assault %d closed: %s (%s)"), Assault.Order, Why, *AssaultText());
	// the marines who never came home (a boat that was lost) are told
	if (Assault.bRoster)
	{
		for (FLeg& L : Assault.Legs)
		{
			if (L.State != FLeg::EState::Home && L.State != FLeg::EState::Lost)
			{
				ReturnMarines(L, true);
			}
		}
	}
	if (UAstraBattleSubsystem* B = Battle())
	{
		B->AbortBoardingOrder(Assault.Order, Why);
	}
	Assault = FAssault();
}

void UAstraBoardSubsystem::RemoteStep(float Dt)
{
	Since += Dt;
	Fight.Tick(Dt);
	ProcessEvents(Dt);
	if (Fight.Over())
	{
		OnRemoteOutcome();
	}
}

void UAstraBoardSubsystem::OnRemoteOutcome()
{
	const FMission& M = Fight.Mission();
	const FBook& B = Fight.Book();
	const bool bUs = Assault.bRoster;                        // the Aquila's marines attack
	const int32 Mine = bUs ? 0 : 1, Theirs = bUs ? 1 : 0;
	const FString Tally = FString::Printf(TEXT("%s: %d dead, %d wounded; %s: %d dead, %d wounded, %d got away"), bUs ? TEXT("marines") : TEXT("the boarders"), B.Killed[Mine], B.Down[Mine],
	                                      bUs ? TEXT("her crew") : TEXT("her defenders"), B.Killed[Theirs], B.Down[Theirs], B.Exited[Theirs]);
	UAstraBattleSubsystem* Bat = Battle();
	FString Detail;
	switch (M.Outcome)
	{
	case EOutcome::AttackerTakes:
	{
		if (Bat)
		{
			Bat->CaptureShip(Assault.TargetId, bUs ? FString(TEXT("the Aquila's marines")) : FString(TEXT("Mandate boarders")), Detail, bUs ? 0 : 1);
		}
		if (bUs)
		{
			Tell(FString::Printf(TEXT("%s is ours: the marines hold %s and her people have laid down their arms; her commander and the survivors of her crew are in custody. %s"), *Assault.TargetName,
			                     *Map->Describe(M.Objective), *Tally), true);
		}
		else
		{
			Tell(FString::Printf(TEXT("the Mandate's boarders hold %s on %s: she is theirs. %s"), *Map->Describe(M.Objective), *Assault.TargetName, *Tally), true);
		}
		break;
		}
		case EOutcome::DefenderHolds:
		if (bUs)
		{
			Tell(FString::Printf(TEXT("the boarding of %s has failed: every marine on her decks is down or out, and she holds. %s"), *Assault.TargetName, *Tally), true);
		}
		else
		{
			Tell(FString::Printf(TEXT("the boarders on %s are beaten: she holds. %s"), *Assault.TargetName, *Tally), true);
		}
		break;
		case EOutcome::AttackerRepelled:
		if (bUs)
		{
			Tell(FString::Printf(TEXT("the marines have broken off and are back in their boats: %s still holds out. %s"), *Assault.TargetName, *Tally), true);
		}
		else
		{
			Tell(FString::Printf(TEXT("the boarders have broken off from %s. %s"), *Assault.TargetName, *Tally), true);
		}
		break;
	case EOutcome::TimedOut:
		Tell(FString::Printf(TEXT("the fight on %s has gone quiet: the objective is not taken. %s"), *Assault.TargetName, *Tally), true);
		break;
	default:
		break;
	}
	Finish(TEXT("the fight is decided"));
}

// ================================================================================================================== what the minds read

TSharedRef<FJsonObject> UAstraBoardSubsystem::AssaultJson() const
{
	TSharedRef<FJsonObject> J = MakeShared<FJsonObject>();
	if (!Assault.bOn)
	{
		return J;
	}
	J->SetNumberField(TEXT("order"), Assault.Order);
	J->SetStringField(TEXT("direction"), Assault.bObserved ? TEXT("in") : (Assault.bRoster ? TEXT("out") : TEXT("other")));
	J->SetStringField(TEXT("attacker"), Assault.Attacker == ESide::Mandate ? TEXT("the Mandate") : TEXT("ASTRA"));
	J->SetStringField(TEXT("carrier"), Assault.CarrierName);
	J->SetStringField(TEXT("target"), Assault.TargetName);
	J->SetStringField(TEXT("objective"), Assault.Objective);
	if (!Assault.By.IsEmpty())
	{
		J->SetStringField(TEXT("ordered_by"), Assault.By);
	}
	J->SetNumberField(TEXT("elapsed_s"), FMath::RoundToInt(Assault.T));
	TArray<TSharedPtr<FJsonValue>> Boats;
	for (const FLeg& L : Assault.Legs)
	{
		TSharedRef<FJsonObject> O = MakeShared<FJsonObject>();
		O->SetStringField(TEXT("boat"), L.CraftName.IsEmpty() ? FString::Printf(TEXT("boat %d"), L.Index + 1) : L.CraftName);
		O->SetNumberField(TEXT("men"), L.Men);
		static const TCHAR* States[] = {TEXT("being readied"), TEXT("in flight"), TEXT("latched to the hull, cutting in"), TEXT("through: the men are aboard"), TEXT("destroyed with its men"), TEXT("turned back"), TEXT("home")};
		O->SetStringField(TEXT("state"), States[(int32)L.State]);
		O->SetStringField(TEXT("hatch"), FString::Printf(TEXT("%s (%s)"), *L.DockId.ToString(), *L.PlaceText));
		Boats.Add(MakeShared<FJsonValueObject>(O));
	}
	J->SetArrayField(TEXT("boats"), Boats);
	return J;
}

TSharedRef<FJsonObject> UAstraBoardSubsystem::BoatsJson() const
{
	TSharedRef<FJsonObject> J = MakeShared<FJsonObject>();
	const UAstraBattleSubsystem* B = Battle();
	const int32 Me = B ? B->ResolveShip(TEXT("aquila")) : -1;
	if (Me < 0)
	{
		return J;
	}
	const AstraBoardCraft::FBay Bay = B->BoardBayOf(Me);
	J->SetNumberField(TEXT("kestrels_free"), Bay.Free());
	J->SetNumberField(TEXT("kestrels_in_all"), Bay.Total - Bay.Lost);
	J->SetNumberField(TEXT("marines_in_a_kestrel"), AstraBoardCraft::Kestrel().Men);
	J->SetStringField(TEXT("bay"), TEXT("the assault-shuttle bay on Deck 8 (port side)"));
	// the marines fit to go: awake or not, on their feet, aboard, not in a fight (the commander stays on the net)
	const UAstraLifeSubsystem* L = LifeSub();
	const UAstraShipSubsystem* S = ShipSub();
	if (L && L->IsRunning() && S)
	{
		const FAstraLifeSim& LS = L->Sim();
		const TArray<FAstraCrewman>& Crew = S->GetRoster().Get();
		int32 Fit = 0, Away = 0;
		for (int32 p = 0; p < LS.NumPeople(); ++p)
		{
			const FAstraLifePerson& P = LS.Person(p);
			if (!Crew.IsValidIndex(P.Roster) || !Crew[P.Roster].Dept.Equals(TEXT("marines"), ESearchCase::IgnoreCase) || Crew[P.Roster].Rank.Equals(TEXT("Captain")))
			{
				continue;
			}
			if (LS.IsOffShip(p))
			{
				++Away;
			}
			else if (P.Status == 0 && P.Act != EAstraLifeAct::Dead && P.Act != EAstraLifeAct::Patient && P.Act != EAstraLifeAct::Repair && !P.bCommandeered)
			{
				++Fit;
			}
		}
		J->SetNumberField(TEXT("marines_fit_to_go"), Fit);
		if (Away > 0)
		{
			J->SetNumberField(TEXT("marines_away_from_the_ship"), Away);
		}
	}
	return J;
}

TSharedRef<FJsonObject> UAstraBoardSubsystem::BoardingOptionsJson(int32 SideIdx) const
{
	TSharedRef<FJsonObject> J = MakeShared<FJsonObject>();
	const UAstraBattleSubsystem* B = Battle();
	if (Assault.bOn)
	{
		// the side that sent the boats follows them: where each is and, once they are in, how many of its men fight and what they hold (its officers hear its own men on the radio)
		if ((SideIdx == 1) == (Assault.Attacker == ESide::Mandate))
		{
			J->SetObjectField(TEXT("assault"), AssaultJson());
			if (Phase == EPhase::Active && Map.IsValid())
			{
				TSharedRef<FJsonObject> F = MakeShared<FJsonObject>();
				const ESide Mine = Assault.Attacker;
				const FBook& Bk = Fight.Book();
				F->SetNumberField(TEXT("your_men_able"), Fight.CountAble(Mine));
				F->SetNumberField(TEXT("your_men_down_or_dead"), Bk.Down[(int32)Mine] + Bk.Killed[(int32)Mine]);
				F->SetNumberField(TEXT("your_men_back_in_the_boats"), Bk.Exited[(int32)Mine]);
				F->SetStringField(TEXT("objective"), Map->Describe(Fight.Mission().Objective));
				F->SetNumberField(TEXT("objective_held_s"), FMath::RoundToInt(Fight.Mission().HeldS));
				F->SetNumberField(TEXT("fight_s"), FMath::RoundToInt(Since));
				J->SetObjectField(TEXT("fight"), F);
			}
		}
		return J;
	}
	if (!B)
	{
		return J;
	}
	TArray<FShipFacts> All;
	B->ListShipFacts(All);
	// the side's carriers with a boat free
	TArray<TSharedPtr<FJsonValue>> Carriers;
	int32 First = INDEX_NONE;
	for (const FShipFacts& F : All)
	{
		if (F.Side != SideIdx || F.bDisabled)
		{
			continue;
		}
		FAssess A;
		if (!B->AssessBoarding(F.Id, F.Id, A) || !A.bCarrierOk || A.BerthsFree <= 0)
		{
			continue;                                    // (a carrier's own boats do not depend on the target)
		}
		TSharedRef<FJsonObject> O = MakeShared<FJsonObject>();
		O->SetStringField(TEXT("ship"), AsShipLabel(F));
		O->SetStringField(TEXT("id"), F.bPlayer ? FString(TEXT("aquila")) : F.ContactId);
		O->SetStringField(TEXT("boat"), A.KindKey);
		O->SetNumberField(TEXT("boats_free"), A.BerthsFree);
		O->SetNumberField(TEXT("men_per_boat"), A.MenPerCraft);
		Carriers.Add(MakeShared<FJsonValueObject>(O));
		if (First == INDEX_NONE || F.bPlayer)
		{
			First = F.Id;
		}
	}
	if (Carriers.IsEmpty())
	{
		return J;
	}
	// the enemy ships a boat could dock at now: no power, or a face whose shield is down (the others are only counted: nobody docks through a shield)
	TArray<TSharedPtr<FJsonValue>> Targets;
	int32 Shielded = 0;
	for (const FShipFacts& T : All)
	{
		if (T.Side == SideIdx || T.Side == 2 || !T.bHasModel)
		{
			continue;
		}
		FAssess A;
		if (!B->AssessBoarding(First, T.Id, A) || !A.bTargetOk)
		{
			continue;
		}
		TArray<FString> Open;
		for (int32 f = 0; f < 6; ++f)
		{
			if (A.bTargetDisabled || A.ShieldFrac[f] <= AstraBoardCraft::ShieldDownFrac)
			{
				Open.Add(AsFaceName(f));
			}
		}
		if (Open.IsEmpty())
		{
			++Shielded;
			continue;
		}
		if (Targets.Num() >= 5)
		{
			continue;
		}
		TSharedRef<FJsonObject> O = MakeShared<FJsonObject>();
		O->SetStringField(TEXT("ship"), AsShipLabel(T));
		O->SetStringField(TEXT("id"), T.bPlayer ? FString(TEXT("aquila")) : T.ContactId);
		O->SetStringField(TEXT("class"), T.ClassText);
		O->SetBoolField(TEXT("no_power"), A.bTargetDisabled);
		O->SetStringField(TEXT("faces_open"), A.bTargetDisabled ? FString(TEXT("all (no power)")) : FString::Join(Open, TEXT(", ")));
		O->SetNumberField(TEXT("hull_pct"), FMath::RoundToInt(A.HullFrac * 100.f));
		O->SetNumberField(TEXT("point_defence_channels"), A.PdChannels);
		O->SetNumberField(TEXT("her_craft_about_her"), A.EnemyCraftNear);
		O->SetNumberField(TEXT("distance_km"), FMath::RoundToInt(A.DistKm * 10.f) / 10.0);
		Targets.Add(MakeShared<FJsonValueObject>(O));
	}
	if (Targets.IsEmpty())
	{
		return J;                                        // nothing to board now: nothing is said (the tokens are the war's)
	}
	J->SetArrayField(TEXT("carriers"), Carriers);
	J->SetArrayField(TEXT("boardable_now"), Targets);
	if (Shielded > 0)
	{
		J->SetNumberField(TEXT("other_enemy_ships_shielded"), Shielded);
	}
	return J;
}
