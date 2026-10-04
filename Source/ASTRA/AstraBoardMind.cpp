// ASTRA — ABBORDAGGI: the fight as the minds see it and command it (docs/ABBORDAGGI.md): the snapshot the bridge crew reads, the marines' picture, the commands
// (the one entrance of the game's orders: "boarding", "marine_order", "lockdown"), and the console's tests and displays.

#include "AstraBoardSubsystem.h"

#include "ASTRA.h"
#include "AstraCombatant.h"
#include "AstraCrewRoster.h"
#include "AstraFpsComponent.h"
#include "AstraShipSubsystem.h"
#include "DrawDebugHelpers.h"
#include "Engine/World.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"
#include "HAL/IConsoleManager.h"
#include "Kismet/GameplayStatics.h"
#include "Serialization/JsonSerializer.h"

using namespace AstraBoard;

namespace
{
	TAutoConsoleVariable<int32> BdCVarBoardDebug(TEXT("astra.board.debug"), 0, TEXT("Draws the boarding fight in the world: 1 the soldiers, 2 also their squads' places, the Mandate's route and the marines' ambush opening"));

	FString BdStr(const TSharedPtr<FJsonObject>& A, const TCHAR* K)
	{
		FString V;
		if (A.IsValid())
		{
			A->TryGetStringField(K, V);
		}
		return V;
	}
	double BdNum(const TSharedPtr<FJsonObject>& A, const TCHAR* K, double Def = 0.0)
	{
		double V = Def;
		if (A.IsValid())
		{
			A->TryGetNumberField(K, V);
		}
		return V;
	}

	/** A place named in an order: the plan's id, or else the one room of that kind or name ("medbay", "Main Engineering"); when several fit they are listed, so that the order names one of them. */
	int32 BdResolvePlace(const FAstraDamageMap& D, const FString& Said, FString& OutWhy)
	{
		if (const int32* P = D.CompByName.Find(FName(*Said)))
		{
			return *P;
		}
		const FString Q = Said.TrimStartAndEnd().ToLower();
		TArray<int32> Hits;
		for (int32 i = 0; i < D.Comps.Num(); ++i)
		{
			const FAstraDmgComp& C = D.Comps[i];
			if (C.Name.ToLower() == Q || C.Kind.ToString().ToLower() == Q)
			{
				Hits.Add(i);
			}
		}
		if (Hits.Num() == 1)
		{
			return Hits[0];
		}
		if (Hits.IsEmpty())
		{
			OutWhy = FString::Printf(TEXT("the plan has no place '%s' (use an id from the picture: where_id, likely_approach, objective_entrances)"), *Said);
			return INDEX_NONE;
		}
		FString List;
		for (int32 i = 0; i < FMath::Min(6, Hits.Num()); ++i)
		{
			List += FString::Printf(TEXT("%s%s [%s]"), i ? TEXT("; ") : TEXT(""), *D.Comps[Hits[i]].Id.ToString(), *D.Describe(Hits[i]));
		}
		OutWhy = FString::Printf(TEXT("'%s' fits %d places (%s%s): name one by its id"), *Said, Hits.Num(), *List, Hits.Num() > 6 ? TEXT("; ...") : TEXT(""));
		return INDEX_NONE;
	}
}

// ================================================================================================================== what the minds read

TSharedRef<FJsonObject> UAstraBoardSubsystem::MarinesPicture() const
{
	TSharedRef<FJsonObject> J = MakeShared<FJsonObject>();
	if (Phase != EPhase::Active || !Map.IsValid() || !Dmg.IsValid())
	{
		return J;
	}
	if (Mode == EMode::Remote && !Assault.bRoster)
	{
		return J;                                          // a fight on another ship that is not the marines' (the Mandate on a consort): not theirs to command
	}
	const auto CompId = [this](int32 C) { return Dmg->Comps.IsValidIndex(C) ? Dmg->Comps[C].Id.ToString() : FString(); };
	const UAstraShipSubsystem* ShipS = ShipSub();
	const TArray<FAstraCrewman>* Crew = ShipS ? &ShipS->GetRoster().Get() : nullptr;
	const bool bWeAttack = Fight.IsAttacker(ESide::Aquila);
	J->SetNumberField(TEXT("elapsed_s"), FMath::RoundToInt(Since));
	// who is attacking whom and where: the marines defend their own ship (a Mandate boarding party in the Aquila) or attack a ship that is not (their boats at her hatches)
	J->SetStringField(TEXT("role"), bWeAttack ? TEXT("attacking") : TEXT("defending"));
	J->SetStringField(TEXT("ship"), Mode == EMode::Remote ? Assault.TargetName : FString(TEXT("the Aquila")));
	if (Mode == EMode::Remote)
	{
		J->SetStringField(TEXT("ship_class"), Assault.TargetClassText);
	}
	J->SetStringField(TEXT("breach"), BreachText);
	J->SetStringField(TEXT("objective"), Map->Describe(Fight.Mission().Objective));
	J->SetStringField(TEXT("objective_id"), CompId(Fight.Mission().Objective));
	J->SetBoolField(TEXT("breach_open"), bBreachOpen);
	// the squads of the marines
	TArray<TSharedPtr<FJsonValue>> Squads;
	for (const FSquad& S : Fight.Squads())
	{
		if (S.Side != ESide::Aquila)
		{
			continue;
		}
		int32 Able = 0, Down = 0, Dead = 0, Waiting = 0;
		for (const int32 M : S.Members)
		{
			const FUnit& U = Fight.Units()[M];
			Able += U.Able() ? 1 : 0;
			Down += U.Act == EAct::Down ? 1 : 0;
			Dead += U.Act == EAct::Dead ? 1 : 0;
			Waiting += U.Act == EAct::Waiting ? 1 : 0;
		}
		TSharedRef<FJsonObject> O = MakeShared<FJsonObject>();
		O->SetStringField(TEXT("name"), S.Name);
		O->SetNumberField(TEXT("able"), Able);
		O->SetNumberField(TEXT("down"), Down);
		O->SetNumberField(TEXT("dead"), Dead);
		if (Waiting)
		{
			O->SetNumberField(TEXT("still_arming_or_waking"), Waiting);
		}
		O->SetStringField(TEXT("doing"), TaskName(S.Task));
		O->SetBoolField(TEXT("under_orders"), S.bOrdered);
		O->SetBoolField(TEXT("in_contact"), S.bContact);
		if (S.Leader != INDEX_NONE && Fight.Units().IsValidIndex(S.Leader))
		{
			const FUnit& L = Fight.Units()[S.Leader];
			O->SetStringField(TEXT("leader"), L.Name);
			// who the leader is as a person (the mind gives them a voice of their own and the rank to speak with)
			if (const int32* R = RosterOfUnit.Find(S.Leader); R && Crew && Crew->IsValidIndex(*R))
			{
				O->SetStringField(TEXT("leader_id"), FString::Printf(TEXT("npc%d"), *R));
				O->SetStringField(TEXT("leader_rank"), (*Crew)[*R].Rank);
				O->SetStringField(TEXT("leader_gender"), (*Crew)[*R].bFemale ? TEXT("f") : TEXT("m"));
			}
			O->SetStringField(TEXT("where"), Map->Describe(L.Comp));
			O->SetStringField(TEXT("where_id"), CompId(L.Comp));
		}
		if (!S.Note.IsEmpty())
		{
			O->SetStringField(TEXT("note"), S.Note);
		}
		Squads.Add(MakeShared<FJsonValueObject>(O));
	}
	J->SetArrayField(TEXT("squads"), Squads);
	// what is known of the enemy (the ship's own sensors in the corridors when she has them, and what the marines have seen)
	TArray<FSeen> Seen;
	Fight.Intel(ESide::Aquila, Seen);
	TMap<int32, int32> ByComp;
	TMap<int32, float> Age;
	for (const FSeen& S : Seen)
	{
		const int32 C = Map->CompAt(S.Pos);
		ByComp.FindOrAdd(C) += 1;
		float& A = Age.FindOrAdd(C);
		A = A == 0.f ? S.AgeS : FMath::Min(A, S.AgeS);
	}
	TArray<TSharedPtr<FJsonValue>> Hostiles;
	for (const auto& KV : ByComp)
	{
		TSharedRef<FJsonObject> O = MakeShared<FJsonObject>();
		O->SetStringField(TEXT("where"), Map->Describe(KV.Key));
		O->SetStringField(TEXT("where_id"), CompId(KV.Key));
		O->SetNumberField(TEXT("count"), KV.Value);
		O->SetNumberField(TEXT("age_s"), FMath::RoundToInt(Age.FindRef(KV.Key)));
		Hostiles.Add(MakeShared<FJsonValueObject>(O));
	}
	J->SetArrayField(TEXT("hostiles_known"), Hostiles);
	// the pressure bulkheads round the breach
	TArray<TSharedPtr<FJsonValue>> Doors;
	const int32 Deck = Map->GetComps().IsValidIndex(Fight.Mission().Breach) ? Map->GetComps()[Fight.Mission().Breach].Deck : 0;
	for (const FBoardPortal& P : Map->GetPortals())
	{
		if (P.Kind == FBoardPortal::EKind::Blast && Map->GetComps()[P.A].Deck == Deck && FVector::Dist2D(P.Pos, BreachAt) < 12000.0 && Dmg->Doors.IsValidIndex(P.Door))
		{
			TSharedRef<FJsonObject> O = MakeShared<FJsonObject>();
			O->SetStringField(TEXT("id"), Dmg->Doors[P.Door].Id.ToString());
			O->SetStringField(TEXT("between"), FString::Printf(TEXT("%s | %s"), *Map->Describe(P.A), *Map->Describe(P.B)));
			O->SetBoolField(TEXT("sealed"), Fight.IsDoorSealed(P.Door));
			Doors.Add(MakeShared<FJsonValueObject>(O));
			if (Doors.Num() >= 16)
			{
				break;
			}
		}
	}
	J->SetArrayField(TEXT("bulkheads"), Doors);
	// the way the boarders will most likely come: the rooms between the breach and Main Engineering (the plan is the marines' own)
	TArray<FVector> Pts;
	TArray<int32> Comps;
	FBoardRouteOptions Opt;
	Opt.Doors = &Fight.DoorState();
	Opt.bThroughSealed = true;
	float Metres = 0.f;
	TArray<TSharedPtr<FJsonValue>> Approach;
	if (Map->Route(BreachAt, Map->CentreOf(Fight.Mission().Objective), Pts, Opt, &Metres, &Comps))
	{
		int32 Last = INDEX_NONE;
		for (const int32 C : Comps)
		{
			if (C == Last || !Map->GetComps().IsValidIndex(C))
			{
				continue;
			}
			Last = C;
			TSharedRef<FJsonObject> O = MakeShared<FJsonObject>();
			O->SetStringField(TEXT("id"), CompId(C));
			O->SetStringField(TEXT("name"), Map->Describe(C));
			Approach.Add(MakeShared<FJsonValueObject>(O));
			if (Approach.Num() >= 16)
			{
				break;
			}
		}
	}
	J->SetArrayField(TEXT("likely_approach"), Approach);
	// the rooms that open onto the objective (where a squad can hold the way in), and the marines' own default ambush: both named by the plan's ids, so that an order can name them
	{
		TArray<TSharedPtr<FJsonValue>> Doors2;
		TSet<int32> Seen2;
		const int32 Obj = Fight.Mission().Objective;
		for (const FBoardPortal& P : Map->GetPortals())
		{
			const int32 Other = P.A == Obj ? P.B : (P.B == Obj ? P.A : INDEX_NONE);
			if (Other == INDEX_NONE || Seen2.Contains(Other) || !Map->GetComps().IsValidIndex(Other) || Doors2.Num() >= 8)
			{
				continue;
			}
			Seen2.Add(Other);
			TSharedRef<FJsonObject> O = MakeShared<FJsonObject>();
			O->SetStringField(TEXT("id"), CompId(Other));
			O->SetStringField(TEXT("name"), Map->Describe(Other));
			Doors2.Add(MakeShared<FJsonValueObject>(O));
		}
		J->SetArrayField(TEXT("objective_entrances"), Doors2);
		const int32 Amb = bWeAttack ? INDEX_NONE : Fight.AmbushPortal();               // (the holders' plan is theirs: an attacker does not know it)
		if (Amb != INDEX_NONE && Map->GetPortals().IsValidIndex(Amb))
		{
			const FBoardPortal& P = Map->GetPortals()[Amb];
			TSharedRef<FJsonObject> O = MakeShared<FJsonObject>();
			O->SetStringField(TEXT("between"), FString::Printf(TEXT("%s | %s"), *Map->Describe(P.A), *Map->Describe(P.B)));
			O->SetStringField(TEXT("id_a"), CompId(P.A));
			O->SetStringField(TEXT("id_b"), CompId(P.B));
			J->SetObjectField(TEXT("default_ambush"), O);
		}
	}
	// the Captain
	if (const FUnit* C = Fight.Unit(Fight.CaptainId()); C && bCaptainIn)
	{
		TSharedRef<FJsonObject> O = MakeShared<FJsonObject>();
		O->SetStringField(TEXT("where"), Map->Describe(C->Comp));
		O->SetStringField(TEXT("where_id"), CompId(C->Comp));
		O->SetBoolField(TEXT("down"), bCapDown);
		O->SetNumberField(TEXT("strength_pct"), FMath::RoundToInt(CaptainStrength() * 100.f));
		J->SetObjectField(TEXT("captain"), O);
	}
	TArray<TSharedPtr<FJsonValue>> Recent;
	for (int32 i = FMath::Max(0, Log.Num() - 8); i < Log.Num(); ++i)
	{
		Recent.Add(MakeShared<FJsonValueString>(Log[i]));
	}
	J->SetArrayField(TEXT("recent"), Recent);
	return J;
}

TSharedRef<FJsonObject> UAstraBoardSubsystem::Snapshot() const
{
	TSharedRef<FJsonObject> J = MakeShared<FJsonObject>();
	if (Assault.bOn)
	{
		J->SetObjectField(TEXT("assault"), AssaultJson());           // the boats: where each is, what it carries (also while no fight is on yet)
	}
	if (Phase != EPhase::Active || !Map.IsValid())
	{
		return J;
	}
	const FBook& B = Fight.Book();
	const bool bWeAttack = Fight.IsAttacker(ESide::Aquila);
	J->SetBoolField(TEXT("active"), true);
	J->SetStringField(TEXT("direction"), Mode == EMode::Observed ? TEXT("in") : (Assault.bRoster ? TEXT("out") : TEXT("other")));
	J->SetStringField(TEXT("ship"), Mode == EMode::Observed ? FString(TEXT("the Aquila")) : Assault.TargetName);
	J->SetNumberField(TEXT("elapsed_s"), FMath::RoundToInt(Since));
	if (!Source.IsEmpty())
	{
		J->SetStringField(TEXT("source"), Source);
	}
	J->SetStringField(TEXT("breach"), BreachText);
	J->SetBoolField(TEXT("breach_open"), bBreachOpen);
	J->SetStringField(TEXT("objective"), Map->Describe(Fight.Mission().Objective));
	J->SetStringField(TEXT("hostiles"), Fight.HostileSummary());
	TSharedRef<FJsonObject> M = MakeShared<FJsonObject>();
	M->SetNumberField(TEXT("able"), Fight.CountAble(ESide::Aquila) - (Fight.CaptainId() != INDEX_NONE ? 1 : 0));
	M->SetNumberField(TEXT("down"), B.Down[0]);
	M->SetNumberField(TEXT("dead"), B.Killed[0]);
	J->SetObjectField(TEXT("marines"), M);
	TSharedRef<FJsonObject> E = MakeShared<FJsonObject>();
	E->SetNumberField(TEXT("down_or_dead"), B.Down[1] + B.Killed[1]);
	E->SetNumberField(TEXT("left_ship"), B.Exited[1]);
	if (bWeAttack)
	{
		J->SetObjectField(TEXT("defenders_known_losses"), E);       // (the marines attack: it is the ship's people who fall)
	}
	else
	{
		J->SetObjectField(TEXT("boarders_known_losses"), E);
	}
	int32 Sealed = 0;
	for (const FBoardPortal& P : Map->GetPortals())
	{
		Sealed += (P.Kind == FBoardPortal::EKind::Blast && Fight.IsDoorSealed(P.Door)) ? 1 : 0;
	}
	J->SetNumberField(TEXT("bulkheads_sealed"), Sealed);
	if (bCaptainIn)
	{
		TSharedRef<FJsonObject> C = MakeShared<FJsonObject>();
		C->SetNumberField(TEXT("strength_pct"), FMath::RoundToInt(CaptainStrength() * 100.f));
		C->SetBoolField(TEXT("down"), bCapDown);
		if (const APlayerController* PC = GetWorld() ? UGameplayStatics::GetPlayerController(GetWorld(), 0) : nullptr)
		{
			if (const UAstraFpsComponent* F = PC->GetPawn() ? PC->GetPawn()->FindComponentByClass<UAstraFpsComponent>() : nullptr)
			{
				const FString Armed = F->StatusText();
				if (!Armed.IsEmpty())
				{
					C->SetStringField(TEXT("armed"), Armed);
				}
			}
		}
		J->SetObjectField(TEXT("captain"), C);
	}
	TArray<TSharedPtr<FJsonValue>> Recent;
	for (int32 i = FMath::Max(0, Log.Num() - 6); i < Log.Num(); ++i)
	{
		Recent.Add(MakeShared<FJsonValueString>(Log[i]));
	}
	J->SetArrayField(TEXT("recent"), Recent);
	return J;
}

FString UAstraBoardSubsystem::InfoText() const
{
	if (Phase == EPhase::Loading)
	{
		return TEXT("boarding: the plan is being read");
	}
	if (Phase == EPhase::Failed)
	{
		return TEXT("boarding: no plan, no fighting inside the hull");
	}
	if (Phase == EPhase::Idle)
	{
		return FString::Printf(TEXT("boarding: ready (%d compartments, %d portals); none on; assault %s"), Map->GetComps().Num(), Map->GetPortals().Num(), *AssaultText());
	}
	const FBook& B = Fight.Book();
	return FString::Printf(TEXT("boarding %s%s at %.0f s: marines %d able, %d down, %d dead; boarders %d able, %d down, %d dead, %d left the ship; Captain %d%%%s; %d bodies; "
	                            "%.2f ms a step (sensing %.2f, plans %.2f, men %.2f); outcome %d%s%s"),
	                       Phase == EPhase::Active ? TEXT("ON") : TEXT("over"), Mode == EMode::Remote ? TEXT(" (on another ship)") : TEXT(""), Since,
	                       Fight.CountAble(ESide::Aquila) - (Fight.CaptainId() != INDEX_NONE ? 1 : 0), B.Down[0], B.Killed[0], Fight.CountAble(ESide::Mandate),
	                       B.Down[1], B.Killed[1], B.Exited[1], FMath::RoundToInt(CaptainStrength() * 100.f), bCapDown ? TEXT(" (down)") : TEXT(""), BodyOf.Num(),
	                       (B.Ms[0] + B.Ms[1] + B.Ms[2]) / FMath::Max(1.0, Since * 10.0), B.Ms[0] / FMath::Max(1.0, Since * 10.0), B.Ms[1] / FMath::Max(1.0, Since * 10.0),
	                       B.Ms[2] / FMath::Max(1.0, Since * 10.0), (int32)Fight.Mission().Outcome, Assault.bOn ? TEXT("; assault ") : TEXT(""), Assault.bOn ? *AssaultText() : TEXT(""));
}

// ================================================================================================================== the orders

bool UAstraBoardSubsystem::HandleCommand(const FString& Name, const TSharedPtr<FJsonObject>& Args, FString& OutDetail)
{
	if (Name == TEXT("issue_weapon"))
	{
		return IssueWeapon(BdStr(Args, TEXT("kind")), BdStr(Args, TEXT("who")), OutDetail);       // the armourer sends a weapon up to the Captain (AstraBoardArms.cpp)
	}
	if (Name == TEXT("board_ship"))
	{
		// the crew's tool: the Aquila's marines in her Kestrels board a ship (`boats` is `craft`); `call_off` turns the boats back
		TSharedPtr<FJsonObject> Out = MakeShared<FJsonObject>();
		if (Args.IsValid())
		{
			Out->Values = Args->Values;
		}
		const FString Act = BdStr(Args, TEXT("action")).ToLower();
		if (Act == TEXT("call_off"))
		{
			Out->SetStringField(TEXT("action"), TEXT("end"));
		}
		else
		{
			if (BdStr(Args, TEXT("target")).IsEmpty())
			{
				OutDetail = TEXT("name the ship to board (target: her contact id or name)");
				return false;
			}
			Out->SetStringField(TEXT("direction"), TEXT("out"));
			if (!Out->HasField(TEXT("craft")) && Out->HasField(TEXT("boats")))
			{
				Out->SetNumberField(TEXT("craft"), BdNum(Args, TEXT("boats"), 0.0));
			}
			if (!Out->HasField(TEXT("boarders")) && Out->HasField(TEXT("marines")))
			{
				Out->SetNumberField(TEXT("boarders"), BdNum(Args, TEXT("marines"), 0.0));
			}
			if (!Out->HasField(TEXT("by")))
			{
				Out->SetStringField(TEXT("by"), TEXT("the Captain's order"));
			}
		}
		return HandleCommand(TEXT("boarding"), Out, OutDetail);
	}
	if (Name == TEXT("boarding"))
	{
		const FString Action = BdStr(Args, TEXT("action")).ToLower();
		if (Action == TEXT("end") || Action == TEXT("stop") || Action == TEXT("cancel"))
		{
			if (Phase != EPhase::Active && !Assault.bOn)
			{
				OutDetail = TEXT("no boarding is on");
				return false;
			}
			EndBoarding(TEXT("ordered"));
			OutDetail = TEXT("the boarding is called off: the boats turn back or let go");
			return true;
		}
		// with a direction (and not `instant`) the boats fly it: in (the Aquila, or a ship of hers, is boarded) or out (her marines board a ship); without one it is the old boarding that
		// is simply there (the boarders cut in after the warning)
		const FString Direction = BdStr(Args, TEXT("direction")).ToLower();
		bool bInstant = false;
		if (Args.IsValid())
		{
			Args->TryGetBoolField(TEXT("instant"), bInstant);
		}
		if (!Direction.IsEmpty() && !bInstant)
		{
			FAssaultSpec A;
			A.Source = BdStr(Args, TEXT("source"));
			A.Target = BdStr(Args, TEXT("target"));
			if (Direction == TEXT("out") || Direction == TEXT("outbound"))
			{
				if (A.Source.IsEmpty())
				{
					A.Source = TEXT("aquila");
				}
			}
			else if (Direction != TEXT("in") && Direction != TEXT("inbound"))
			{
				OutDetail = FString::Printf(TEXT("unknown direction '%s' (in: the Aquila or a ship of hers is boarded; out: her marines board a ship)"), *Direction);
				return false;
			}
			A.Face = BdStr(Args, TEXT("face"));
			A.Objective = BdStr(Args, TEXT("objective"));
			A.Breach = BdStr(Args, TEXT("breach"));
			A.Craft = FMath::Clamp((int32)BdNum(Args, TEXT("craft"), BdNum(Args, TEXT("skiffs"), 0.0)), 0, 4);
			A.Boarders = FMath::Clamp((int32)BdNum(Args, TEXT("boarders"), 0.0), 0, 48);
			bool bLockAssault = true, bCap = false;
			if (Args.IsValid())
			{
				Args->TryGetBoolField(TEXT("lockdown"), bLockAssault);
				Args->TryGetBoolField(TEXT("captain"), bCap);
			}
			A.bLockdown = bLockAssault;
			A.bCaptain = bCap;
			A.By = BdStr(Args, TEXT("by"));
			return StartAssault(A, OutDetail);
		}
		FSpec Spec;
		Spec.Breach = BdStr(Args, TEXT("breach"));
		Spec.Skiffs = FMath::Clamp((int32)BdNum(Args, TEXT("skiffs"), 1.0), 1, 4);
		Spec.Boarders = (int32)BdNum(Args, TEXT("boarders"), 0.0);
		Spec.Source = BdStr(Args, TEXT("source"));
		bool bLock = true;
		if (Args.IsValid())
		{
			Args->TryGetBoolField(TEXT("lockdown"), bLock);
		}
		Spec.bLockdown = bLock;
		Spec.WarnS = (float)BdNum(Args, TEXT("warn_s"), 45.0);
		return StartBoarding(Spec, OutDetail);
	}
	if (Phase != EPhase::Active)
	{
		OutDetail = TEXT("no boarding is on");
		return false;
	}
	if (Mode == EMode::Remote && (Name == TEXT("lockdown") || !Assault.bRoster))
	{
		OutDetail = Name == TEXT("lockdown") ? FString(TEXT("the bulkheads of another ship are not ours to seal")) : FString(TEXT("the marines are not in this fight"));
		return false;
	}
	if (Name == TEXT("lockdown"))
	{
		bool bSealed = true;
		if (Args.IsValid())
		{
			Args->TryGetBoolField(TEXT("sealed"), bSealed);
		}
		const TArray<TSharedPtr<FJsonValue>>* Doors = nullptr;
		int32 N = 0;
		FString Unknown;
		if (Args.IsValid() && Args->TryGetArrayField(TEXT("doors"), Doors))
		{
			for (const TSharedPtr<FJsonValue>& V : *Doors)
			{
				const int32* Di = Dmg->DoorByName.Find(FName(*V->AsString()));
				if (Di)
				{
					SealDoor(*Di, bSealed);
					++N;
				}
				else
				{
					Unknown += (Unknown.IsEmpty() ? TEXT("") : TEXT(", ")) + V->AsString();
				}
			}
		}
		else if (BdStr(Args, TEXT("scope")) == TEXT("breach_section") || BdStr(Args, TEXT("doors")).IsEmpty())
		{
			// every pressure bulkhead of the breach's deck round it
			const int32 Deck = Map->GetComps()[Fight.Mission().Breach].Deck;
			for (const FBoardPortal& P : Map->GetPortals())
			{
				if (P.Kind == FBoardPortal::EKind::Blast && Map->GetComps()[P.A].Deck == Deck && FVector::Dist2D(P.Pos, BreachAt) < 9000.0)
				{
					SealDoor(P.Door, bSealed);
					++N;
				}
			}
		}
		OutDetail = FString::Printf(TEXT("%d pressure bulkheads %s"), N, bSealed ? TEXT("sealed") : TEXT("opened"));
		if (!Unknown.IsEmpty())
		{
			OutDetail += FString::Printf(TEXT("; no bulkhead is called %s (the picture's bulkheads list the ids)"), *Unknown);
		}
		return N > 0;
	}
	if (Name == TEXT("marine_order"))
	{
		const FString Who = BdStr(Args, TEXT("squad"));
		const FString Task = BdStr(Args, TEXT("task")).ToLower();
		const FString PlaceId = BdStr(Args, TEXT("place"));
		const FString Note = BdStr(Args, TEXT("note"));
		const float Radius = (float)BdNum(Args, TEXT("radius_m"), 8.0) * 100.f;
		TArray<int32> Targets;
		const FString WhoL = Who.ToLower();
		for (const FSquad& S : Fight.Squads())
		{
			if (S.Side != ESide::Aquila)
			{
				continue;
			}
			const FString N = S.Name.ToLower();
			if (WhoL == TEXT("all") || WhoL == TEXT("everyone") || N == WhoL || (WhoL == TEXT("reaction") && N.StartsWith(TEXT("reaction"))) || (WhoL == TEXT("watch") && N.StartsWith(TEXT("watch")))
			    || (WhoL == TEXT("reserve") && N.StartsWith(TEXT("reserve"))))
			{
				Targets.Add(S.Id);
			}
		}
		if (Targets.IsEmpty())
		{
			OutDetail = FString::Printf(TEXT("no squad of ours is called '%s'"), *Who);
			return false;
		}
		int32 Comp = INDEX_NONE;
		FVector At = FVector::ZeroVector;
		if (!PlaceId.IsEmpty() && !PlaceId.Equals(TEXT("captain"), ESearchCase::IgnoreCase) && !PlaceId.Equals(TEXT("here"), ESearchCase::IgnoreCase))
		{
			FString Why;
			Comp = BdResolvePlace(*Dmg, PlaceId, Why);
			if (Comp == INDEX_NONE)
			{
				OutDetail = Why;
				return false;
			}
			At = Map->CentreOf(Comp);
		}
		else if (const FUnit* C = Fight.Unit(Fight.CaptainId()))
		{
			Comp = C->Comp;
			At = C->Pos;
		}
		ETask T = ETask::Hold;
		bool bRespond = false;
		if (Task == TEXT("hold")) { T = ETask::Hold; }
		else if (Task == TEXT("advance") || Task == TEXT("move")) { T = ETask::Advance; }
		else if (Task == TEXT("assault") || Task == TEXT("attack")) { T = ETask::Assault; }
		else if (Task == TEXT("fall_back")) { T = ETask::FallBack; }
		else if (Task == TEXT("withdraw")) { T = Fight.IsAttacker(ESide::Aquila) ? ETask::Withdraw : ETask::FallBack; }       // (attacking: out by the hatch, to the boats; defending: back to a place)
		else if (Task == TEXT("follow_captain") || Task == TEXT("follow")) { T = ETask::Follow; }
		else if (Task == TEXT("rescue_captain") || Task == TEXT("rescue")) { T = ETask::Rescue; }
		else if (Task == TEXT("stand_down") || Task == TEXT("free")) { bRespond = true; }
		else
		{
			OutDetail = FString::Printf(TEXT("unknown task '%s' (hold, advance, assault, fall_back, withdraw, follow_captain, rescue_captain, stand_down)"), *Task);
			return false;
		}
		FString Said;
		for (const int32 Sq : Targets)
		{
			if (bRespond)
			{
				Fight.Respond(Sq);
			}
			else
			{
				Fight.Order(Sq, T, Comp, At, Radius, Note);
			}
			Said += (Said.IsEmpty() ? TEXT("") : TEXT(", ")) + Fight.Squads()[Sq].Name;
		}
		Log.Add(FString::Printf(TEXT("%.0fs: order to %s: %s%s"), Since, *Said, *Task, Comp != INDEX_NONE && !bRespond ? *FString::Printf(TEXT(" at %s"), *Map->Describe(Comp)) : TEXT("")));
		OutDetail = FString::Printf(TEXT("%s: %s%s"), *Said, *Task, Comp != INDEX_NONE && !bRespond ? *FString::Printf(TEXT(" at %s"), *Map->Describe(Comp)) : TEXT(""));
		return true;
	}
	OutDetail = FString::Printf(TEXT("unknown boarding command '%s'"), *Name);
	return false;
}

// ================================================================================================================== the display

void UAstraBoardSubsystem::DrawDebug() const
{
#if ENABLE_DRAW_DEBUG
	const int32 Level = BdCVarBoardDebug.GetValueOnGameThread();
	UWorld* W = GetWorld();
	if (!W || Level <= 0 || (Phase != EPhase::Active && Phase != EPhase::Over) || !Map.IsValid())
	{
		return;
	}
	for (const FUnit& U : Fight.Units())
	{
		if (U.Act == EAct::Waiting || U.Act == EAct::Gone || U.bExternal)
		{
			continue;
		}
		const FColor Col = U.Act == EAct::Dead ? FColor(90, 90, 90) : U.Act == EAct::Down ? FColor(255, 160, 0) : (U.Side == ESide::Mandate ? FColor(255, 40, 40) : FColor(60, 200, 255));
		DrawDebugCapsule(W, U.Pos + FVector(0, 0, 85), 85.f, 24.f, FQuat::Identity, Col, false, 0.f, 0, 1.5f);
		const FVector Eye = U.Eye();
		DrawDebugLine(W, Eye, Eye + FRotator(0, U.Yaw, 0).Vector() * 60.f, Col, false, 0.f, 0, 1.5f);
		if (U.Target != INDEX_NONE && Fight.Units().IsValidIndex(U.Target) && U.Able())
		{
			DrawDebugLine(W, Eye, Fight.Units()[U.Target].Eye(), FColor(Col.R, Col.G, Col.B, 90), false, 0.f, 0, 0.6f);
		}
		DrawDebugString(W, U.Pos + FVector(0, 0, 205), FString::Printf(TEXT("%s %s %d%%"), *U.Name.Right(18), ActName(U.Act), FMath::RoundToInt(U.Hp)), nullptr, Col, 0.f, true, 0.9f);
	}
	if (Level >= 2)
	{
		for (const FSquad& S : Fight.Squads())
		{
			if (S.Leader == INDEX_NONE || !Fight.Units().IsValidIndex(S.Leader) || !Fight.Units()[S.Leader].Able())
			{
				continue;
			}
			const FColor Col = S.Side == ESide::Mandate ? FColor(255, 120, 40) : FColor(80, 255, 160);
			DrawDebugLine(W, Fight.Units()[S.Leader].Pos + FVector(0, 0, 40), S.TargetPos + FVector(0, 0, 40), Col, false, 0.f, 0, 0.8f);
			DrawDebugString(W, Fight.Units()[S.Leader].Pos + FVector(0, 0, 250), FString::Printf(TEXT("%s: %s%s"), *S.Name, TaskName(S.Task), S.bOrdered ? TEXT(" (ordered)") : TEXT("")), nullptr, Col, 0.f, true, 1.0f);
		}
		TArray<FVector> Route;
		if (Fight.PlannedRoute(Route))
		{
			for (int32 i = 0; i + 1 < Route.Num(); ++i)
			{
				DrawDebugLine(W, Route[i] + FVector(0, 0, 20), Route[i + 1] + FVector(0, 0, 20), FColor(255, 200, 0, 140), false, 0.f, 0, 0.5f);
			}
		}
		const int32 Amb = Fight.AmbushPortal();
		if (Amb != INDEX_NONE)
		{
			DrawDebugSphere(W, Map->GetPortals()[Amb].Pos + FVector(0, 0, 100), 60.f, 10, FColor(0, 255, 120), false, 0.f, 0, 1.2f);
			DrawDebugString(W, Map->GetPortals()[Amb].Pos + FVector(0, 0, 190), TEXT("ambush"), nullptr, FColor(0, 255, 120), 0.f, true, 1.0f);
		}
	}
#endif
}

namespace
{
	UAstraBoardSubsystem* BdBoard(UWorld* W) { return W ? W->GetSubsystem<UAstraBoardSubsystem>() : nullptr; }

	FAutoConsoleCommandWithWorldAndArgs BdCmdStart(TEXT("astra.board.start"), TEXT("Testing: a boarding. astra.board.start [skiffs 1..4] [the plan's id of the compartment the boarders cut into]"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& A, UWorld* W)
		{
			UAstraBoardSubsystem* B = BdBoard(W);
			if (!B)
			{
				return;
			}
			UAstraBoardSubsystem::FSpec S;
			S.Skiffs = A.Num() > 0 ? FMath::Clamp(FCString::Atoi(*A[0]), 1, 4) : 1;
			S.Breach = A.Num() > 1 ? A[1] : FString();
			S.Source = TEXT("the Mandate raider on the port beam");
			FString D;
			const bool bOk = B->StartBoarding(S, D);
			UE_LOG(LogASTRA, Log, TEXT("[Board] %s: %s"), bOk ? TEXT("started") : TEXT("not started"), *D);
			if (GEngine) { GEngine->AddOnScreenDebugMessage(-1, 6.f, bOk ? FColor::Green : FColor::Red, D); }
		}));
	FAutoConsoleCommandWithWorldAndArgs BdCmdAssault(TEXT("astra.board.assault"), TEXT("Testing: boats fly a boarding. astra.board.assault in [carrier] [target] [boats 1..4] [face] [objective]  (the Mandate's skiffs board the Aquila, or the target named) | astra.board.assault out [target] [carrier] [boats] [face] [objective] [ride]  (the Aquila's marines go in Kestrels, and the Captain with them when the word ride is there; ships by contact id or name; - for the default)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& A, UWorld* W)
		{
			UAstraBoardSubsystem* B = BdBoard(W);
			if (!B || A.Num() < 1)
			{
				return;
			}
			UAstraBoardSubsystem::FAssaultSpec S;
			const bool bOut = A[0].StartsWith(TEXT("out"));
			(bOut ? S.Target : S.Source) = A.Num() > 1 && !A[1].Equals(TEXT("-")) ? A[1] : FString();
			(bOut ? S.Source : S.Target) = A.Num() > 2 && !A[2].Equals(TEXT("-")) ? A[2] : FString();
			S.Craft = A.Num() > 3 ? FCString::Atoi(*A[3]) : 0;
			S.Face = A.Num() > 4 && !A[4].Equals(TEXT("-")) ? A[4] : FString();
			S.Objective = A.Num() > 5 && !A[5].Equals(TEXT("ride")) && !A[5].Equals(TEXT("-")) ? A[5] : FString();
			for (const FString& Word : A)
			{
				S.bCaptain |= Word.Equals(TEXT("ride"));                       // (the Captain goes with the marines: the word ride anywhere after the verb)
			}
			S.By = TEXT("the console");
			FString D;
			const bool bOk = B->StartAssault(S, D);
			UE_LOG(LogASTRA, Log, TEXT("[Board] %s: %s"), bOk ? TEXT("assault ordered") : TEXT("assault refused"), *D);
			if (GEngine) { GEngine->AddOnScreenDebugMessage(-1, 8.f, bOk ? FColor::Green : FColor::Red, D); }
		}));
	FAutoConsoleCommandWithWorld BdCmdEnd(TEXT("astra.board.end"), TEXT("Testing: calls the boarding off (bulkheads open, marines back to duty)"),
		FConsoleCommandWithWorldDelegate::CreateLambda([](UWorld* W) { if (UAstraBoardSubsystem* B = BdBoard(W)) { B->EndBoarding(TEXT("console")); } }));
	FAutoConsoleCommandWithWorld BdCmdInfo(TEXT("astra.board.info"), TEXT("The boarding fight in numbers"),
		FConsoleCommandWithWorldDelegate::CreateLambda([](UWorld* W)
		{
			if (UAstraBoardSubsystem* B = BdBoard(W))
			{
				const FString T = B->InfoText();
				UE_LOG(LogASTRA, Log, TEXT("[Board] %s"), *T);
				if (GEngine) { GEngine->AddOnScreenDebugMessage(-1, 8.f, FColor::Cyan, T); }
			}
		}));
	FAutoConsoleCommandWithWorldAndArgs BdCmdCommand(TEXT("astra.board.cmd"), TEXT("Testing: one of the boarding commands by its JSON: astra.board.cmd marine_order {\"squad\":\"all\",\"task\":\"hold\",\"place\":\"engineering\"}"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& A, UWorld* W)
		{
			UAstraBoardSubsystem* B = BdBoard(W);
			if (!B || A.Num() < 1)
			{
				return;
			}
			TSharedPtr<FJsonObject> J = MakeShared<FJsonObject>();
			if (A.Num() > 1)
			{
				FString Rest;
				for (int32 i = 1; i < A.Num(); ++i) { Rest += (i > 1 ? TEXT(" ") : TEXT("")) + A[i]; }
				const TSharedRef<TJsonReader<>> R = TJsonReaderFactory<>::Create(Rest);
				FJsonSerializer::Deserialize(R, J);
			}
			FString D;
			const bool bOk = B->HandleCommand(A[0], J, D);
			UE_LOG(LogASTRA, Log, TEXT("[Board] %s: %s"), bOk ? TEXT("ok") : TEXT("refused"), *D);
			if (GEngine) { GEngine->AddOnScreenDebugMessage(-1, 6.f, bOk ? FColor::Green : FColor::Red, D); }
		}));
	FAutoConsoleCommandWithWorld BdCmdPicture(TEXT("astra.board.picture"), TEXT("Writes the marines' picture of the fight (the mind's context) to the log"),
		FConsoleCommandWithWorldDelegate::CreateLambda([](UWorld* W)
		{
			if (UAstraBoardSubsystem* B = BdBoard(W))
			{
				FString Out;
				const TSharedRef<TJsonWriter<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>> Wr = TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&Out);
				FJsonSerializer::Serialize(B->MarinesPicture(), Wr);
				UE_LOG(LogASTRA, Log, TEXT("[Board] picture: %s"), *Out);
			}
		}));
}
