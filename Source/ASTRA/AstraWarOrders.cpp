// ASTRA — the commanders' tools on the battle groups (docs/GUERRA.md, "Il contratto dei comandanti"): the `group_order` command,
// what each side's mind may read of its groups and of the enemy's (the fog of war applies), and the events that say something
// happened to a group. The code here is the body of the fleet — it obeys, reports, and tells what it will do; what to order and
// when is the commanders' (the minds') to decide, never this file's.

#include "AstraBattleSubsystem.h"
#include "AstraWarClasses.h"
#include "AstraWarAI.h"
#include "ASTRA.h"
#include "AstraShipSubsystem.h"
#include "Dom/JsonValue.h"

namespace
{
	using AstraWar::WarKm;

	double OrdRound(double V, double Step)
	{
		return Step >= 1.0 ? FMath::RoundToDouble(V / Step) * Step : FMath::RoundToDouble(V / Step) / FMath::RoundToDouble(1.0 / Step);   // (no 0.8200000000000001)
	}
	double OrdPct(double V, double Max) { return Max > 0.0 ? FMath::Clamp(FMath::RoundToDouble(100.0 * V / Max), 0.0, 100.0) : 0.0; }

	/** The class as a mind names it (the key: acheron, styx...), or "unknown" while the sensors cannot tell. */
	FString OrdClassOf(const FAstraBattleShip& S, bool bKnownClass)
	{
		return bKnownClass && !S.ClassKey.IsNone() ? S.ClassKey.ToString() : FString(TEXT("unknown"));
	}

	const TCHAR* OrdTaskName(EAstraTask T)
	{
		switch (T)
		{
		case EAstraTask::Flank: return TEXT("flank");
		case EAstraTask::Reserve: return TEXT("reserve");
		case EAstraTask::RearGuard: return TEXT("rear_guard");
		default: return TEXT("formation");
		}
	}
}

// ---------------------------------------------------------------------------------------------- the events
void UAstraBattleSubsystem::NoteGroupEvent(int32 SideIdx, const FString& Text)
{
	if (SideIdx < 0 || SideIdx > 1)
	{
		return;
	}
	for (int32 i = GroupEvents.Num() - 1; i >= 0 && Time - GroupEvents[i].T < 6.f; --i)
	{
		if (GroupEvents[i].SideIdx == SideIdx && GroupEvents[i].Text == Text)
		{
			return;                                   // the same thing said again a moment later: once is enough
		}
	}
	FAstraGroupEvent E;
	E.Serial = NextGroupEventSerial++;
	E.T = Time;
	E.SideIdx = SideIdx;
	E.Text = Text;
	GroupEvents.Add(E);
	if (GroupEvents.Num() > 48)
	{
		GroupEvents.RemoveAt(0, GroupEvents.Num() - 48, EAllowShrinking::No);
	}
	UE_LOG(LogASTRA, Log, TEXT("[War] %s group: %s"), SideIdx == 0 ? TEXT("ASTRA") : TEXT("Mandate"), *Text);
	if (SideIdx == 0 && !bSandbox)
	{
		// the fleet's own datalink: the bridge's crew hears what happens to ASTRA groups. (The Mandate's are private to its mind: the
		// shared event stream also feeds the bridge screens and the crew's prompts, and must not carry the enemy's internal picture.)
		Report(FString::Printf(TEXT("fleet: %s"), *Text), false);
	}
}

void UAstraBattleSubsystem::SetGroupState(FAstraBattleGroup& G, EAstraGroupState New, const FString& Why)
{
	if (G.State == New)
	{
		return;
	}
	const EAstraGroupState Old = G.State;
	G.State = New;
	const int32 Me = AstraSideIdx(G.Side);
	int32 Alive = 0;
	for (const int32 Id : G.Members)
	{
		const FAstraBattleShip* S = FindById(Id);
		Alive += (S && S->bAlive && !S->bDisabled) ? 1 : 0;
	}
	switch (New)
	{
	case EAstraGroupState::Withdraw:
		if (Old == EAstraGroupState::Regroup)
		{
			NoteGroupEvent(Me, FString::Printf(TEXT("%s: pressed while regrouping, falling back again (%s)"), *G.Name, *Why));
		}
		else
		{
			NoteGroupEvent(Me, FString::Printf(TEXT("%s: breaking off, %s (%d ships, strength %.1f against %.1f, morale %.2f)"), *G.Name, *Why, Alive,
			                                   G.Strength, G.EnemyStrength, G.Morale));
		}
		break;
	case EAstraGroupState::Regroup:
		NoteGroupEvent(Me, FString::Printf(TEXT("%s: %s, regrouping with %d ships"), *G.Name, *Why, Alive));
		break;
	default:
		NoteGroupEvent(Me, FString::Printf(TEXT("%s: back in the fight with %d ships (%s, morale %.2f)"), *G.Name, Alive, *Why, G.Morale));
		break;
	}
}

/** A ship of a group is gone (destroyed, broken up, disabled): the group says so and what is left. */
void UAstraBattleSubsystem::NoteGroupLoss(const FAstraBattleShip& S, const TCHAR* How)
{
	const FAstraBattleGroup* G = FindGroup(S.GroupId);
	if (!G || S.bCraft)
	{
		return;
	}
	int32 Left = 0;
	for (const int32 Id : G->Members)
	{
		const FAstraBattleShip* M = FindById(Id);
		Left += (M && M->Id != S.Id && M->bAlive && !M->bDisabled) ? 1 : 0;
	}
	NoteGroupEvent(AstraSideIdx(G->Side), FString::Printf(TEXT("%s: lost %s (%s), %s; %d of %d ships left"), *G->Name, *S.ContactId, *OrdClassOf(S, true), How, Left,
	                                                     FMath::Max(G->StartCount, Left)));
}

bool UAstraBattleSubsystem::OnPlot(int32 SideIdx, const FAstraBattleShip& X, FVector& OutPos) const
{
	if (SideIdx == 0 && (!X.bFog || X.Track >= 2))
	{
		OutPos = X.Pos;                                  // the Aquila's own plot: a firm track, or a scripted ship that is always on it
		return true;
	}
	if (SideIdx == 0 && X.bFog)
	{
		return false;                                    // a bearing only, or nothing
	}
	if (!Knows(SideIdx, X))
	{
		return false;
	}
	OutPos = KnownPos(SideIdx, X);
	return true;
}

// ---------------------------------------------------------------------------------------------- finding what an order names
FAstraBattleGroup* UAstraBattleSubsystem::ResolveGroup(const FString& Key, int32 SideIdx, FString* OutWhy)
{
	const FString K = Key.TrimStartAndEnd();
	if (K.IsEmpty())
	{
		return nullptr;
	}
	auto Mine = [&](const FAstraBattleGroup& G) { return AstraSideIdx(G.Side) == SideIdx && G.Members.Num() > 0; };
	if (K.IsNumeric())
	{
		const int32 Id = FCString::Atoi(*K);
		for (FAstraBattleGroup& G : Groups)
		{
			if (G.Id == Id && Mine(G))
			{
				return &G;
			}
		}
	}
	for (FAstraBattleGroup& G : Groups)
	{
		if (Mine(G) && G.Name.Equals(K, ESearchCase::IgnoreCase))
		{
			return &G;
		}
	}
	// a ship of it ("A-02") or "group of A-02"
	FString Tag = K;
	for (const TCHAR* Prefix : {TEXT("hostile group of "), TEXT("group of "), TEXT("group with ")})
	{
		if (Tag.StartsWith(Prefix, ESearchCase::IgnoreCase))
		{
			Tag = Tag.Mid(FCString::Strlen(Prefix)).TrimStartAndEnd();
			break;
		}
	}
	if (const FAstraBattleShip* S = FindByContact(Tag.ToUpper()); S && S->GroupId >= 0)
	{
		if (FAstraBattleGroup* G = FindGroup(S->GroupId); G && Mine(*G))
		{
			return G;
		}
	}
	FAstraBattleGroup* Found = nullptr;
	TArray<FString> Names;
	for (FAstraBattleGroup& G : Groups)
	{
		if (Mine(G) && G.Name.Contains(K, ESearchCase::IgnoreCase))
		{
			Found = &G;
			Names.Add(G.Name);
		}
	}
	if (Names.Num() > 1 && OutWhy)
	{
		*OutWhy = FString::Printf(TEXT("'%s' matches several groups (%s): name one exactly"), *K, *FString::Join(Names, TEXT(", ")));
	}
	return Names.Num() == 1 ? Found : nullptr;
}

// ---------------------------------------------------------------------------------------------- telling what an order will do
namespace
{
	/** Where the group's ships would be in this many seconds, given how far there is to go at the group's pace. */
	double OrdEtaS(double DistM, double SpeedMps)
	{
		return DistM <= 0.0 ? 0.0 : OrdRound(DistM / FMath::Max(40.0, SpeedMps), 5.0);
	}
}

FString UAstraBattleSubsystem::DescribeGroupOrder(const FAstraBattleGroup& G, const FAstraBattleShip* Target, const FAstraBattleGroup* Other) const
{
	const int32 Me = AstraSideIdx(G.Side);
	FVector C = FVector::ZeroVector;
	double W = 0.0, Pace = 1e9;
	int32 N = 0;
	for (const int32 Id : G.Members)
	{
		const FAstraBattleShip* S = FindById(Id);
		if (S && S->bAlive && !S->bDisabled)
		{
			C += S->Pos * S->Radius;
			W += S->Radius;
			Pace = FMath::Min(Pace, (double)S->CruiseSpeed * 0.7);
			++N;
		}
	}
	if (N == 0)
	{
		return FString::Printf(TEXT("%s: no ship left to carry it out"), *G.Name);
	}
	C /= FMath::Max(1.0, W);
	auto Label = [&](const FAstraBattleShip& T) -> FString
	{
		const bool bClass = !T.bFog || T.bClassified || Me == 1;
		return FString::Printf(TEXT("%s (%s)"), T.bPlayer ? TEXT("AQUILA") : *T.ContactId, *OrdClassOf(T, bClass));
	};
	FString Text;
	switch (G.Order)
	{
	case EAstraGroupOrder::Auto:
		Text = TEXT("back to its own judgement: it picks its targets and its range, closes, holds the line and breaks off by itself if it is being beaten");
		break;
	case EAstraGroupOrder::Attack:
		if (Target)
		{
			FVector TPos = Target->Pos;
			OnPlot(Me, *Target, TPos);
			const double D = FVector::Dist(TPos, C);
			const double Hold = G.OrderRangeM > 0.f ? G.OrderRangeM : G.EngageRange;
			Text = FString::Printf(TEXT("attacking %s, %.1f km away: every ship that can reach it fires on it, the group %s %.1f km (on its firing line in ~%.0f s)"),
			                       *Label(*Target), D / WarKm, G.OrderRangeM > 0.f ? TEXT("closes to the ordered") : TEXT("closes to"), Hold / WarKm, OrdEtaS(D - Hold, Pace));
		}
		else if (Other)
		{
			Text = FString::Printf(TEXT("attacking the %s group: fire on whichever of its ships is worth most"), *Other->Name);
		}
		else
		{
			Text = TEXT("pressing the attack on whatever it judges best");
		}
		break;
	case EAstraGroupOrder::Pin:
		Text = Target ? FString::Printf(TEXT("pinning %s: fire on it from no closer than %.1f km, the group does not commit past that"), *Label(*Target),
		                                (G.OrderRangeM > 0.f ? G.OrderRangeM : FMath::Min(G.EngageRange, 9000.f)) / WarKm)
		              : FString(TEXT("pinning the enemy: holding at long range and keeping its attention without closing"));
		break;
	case EAstraGroupOrder::FlankLeft:
	case EAstraGroupOrder::FlankRight:
	{
		const bool bLeft = G.Order == EAstraGroupOrder::FlankLeft;
		FString On = Target ? FString::Printf(TEXT(" on %s"), *Label(*Target)) : (Other ? FString::Printf(TEXT(" on the %s group"), *Other->Name) : FString());
		// how long the swing takes: the most agile fit ship, round an arc of the engagement range to the enemy's beam
		double Eta = 0.0;
		int32 EnemiesThere = 0;
		const FAstraBattleShip* Mover = nullptr;
		for (const int32 Id : G.Members)
		{
			const FAstraBattleShip* S = FindById(Id);
			if (S && S->bAlive && !S->bDisabled && S->Id != G.LeaderId && (!Mover || S->MaxAccel * S->MaxTurnDeg > Mover->MaxAccel * Mover->MaxTurnDeg))
			{
				Mover = S;
			}
		}
		if (Mover && Target)
		{
			FVector TP = Target->Pos;
			OnPlot(Me, *Target, TP);
			const FVector Back = (C - TP).GetSafeNormal();
			const double Rr = FMath::Max((double)G.EngageRange * 1.05, 3500.0);
			const FVector From = Mover->Pos - TP;
			const double Now = FMath::Atan2(From.Y, From.X);
			const double Goal = FMath::Atan2(Back.Y, Back.X) - (bLeft ? -1.0 : 1.0) * FMath::DegreesToRadians(105.0);
			const double Arc = FMath::Abs(FMath::UnwindRadians(Goal - Now)) * Rr + FMath::Abs(From.Size2D() - Rr);
			Eta = OrdEtaS(Arc, Mover->CruiseSpeed * 0.85);
			// how many of the enemy's guns can reach the flank point (what the flankers will face)
			const FVector Point = TP + FVector(FMath::Cos(Goal), FMath::Sin(Goal), 0.0) * Rr;
			for (const FAstraBattleShip& X : Ships)
			{
				FVector XP;
				if (X.bAlive && !X.bCraft && !X.bDisabled && !X.bGhost && AstraSideIdx(X.Side) == 1 - Me && X.RailDamage > 0.f && OnPlot(Me, X, XP) && FVector::Dist(XP, Point) < X.RailRange)
				{
					++EnemiesThere;
				}
			}
		}
		Text = FString::Printf(TEXT("flanking %s%s, %d ship%s swinging to its beam%s%s; the rest of the line holds the enemy's attention"), bLeft ? TEXT("left") : TEXT("right"), *On,
		                       FMath::Clamp(N / 2, 1, 2), N / 2 > 1 ? TEXT("s") : TEXT(""), Eta > 0.0 ? *FString::Printf(TEXT(", ~%.0f s to get there"), Eta) : TEXT(""),
		                       EnemiesThere > 0 ? *FString::Printf(TEXT("; %d enemy ships have that point inside their gun range"), EnemiesThere) : TEXT(""));
		break;
	}
	case EAstraGroupOrder::Screen:
	{
		const FAstraBattleShip* P = FindById(G.ProtecteeId);
		Text = P ? FString::Printf(TEXT("screening %s: the ships take a ring about %.1f km out on the enemy's side of it"), P->bPlayer ? TEXT("the Aquila") : *P->ContactId,
		                           FMath::Max(2500.0, (double)P->Radius + 2400.0) / WarKm)
		         : FString(TEXT("screening: no ship to protect is named, so the group forms its screen where it stands"));
		break;
	}
	case EAstraGroupOrder::Withdraw:
	{
		double Nearest = 1e18;
		for (const FAstraBattleShip& X : Ships)
		{
			FVector XP;
			if (X.bAlive && !X.bCraft && !X.bDisabled && AstraSideIdx(X.Side) == 1 - Me && OnPlot(Me, X, XP))
			{
				Nearest = FMath::Min(Nearest, (double)FVector::Dist(XP, C));
			}
		}
		Text = Nearest < 1e17 ? FString::Printf(TEXT("withdrawing: the nearest enemy is %.1f km away; the group breaks contact, the healthiest ship covering the rear, and is clear of them in ~%.0f s"), Nearest / WarKm,
		                                        OrdEtaS(FMath::Max(0.0, 38.0 * WarKm - Nearest), Pace))
		                      : FString(TEXT("withdrawing: no enemy in contact; the group falls back and reforms"));
		break;
	}
	case EAstraGroupOrder::Regroup:
		Text = TEXT("regrouping: stopping and reforming where it stands, guns free on what comes in range");
		break;
	case EAstraGroupOrder::Reinforce:
		if (Other)
		{
			const double D = FVector::Dist(Other->Centroid, C);
			Text = FString::Printf(TEXT("going to reinforce the %s group, %.1f km away, ~%.0f s to close on it"), *Other->Name, D / WarKm, OrdEtaS(D - 2500.0, Pace));
		}
		else
		{
			Text = TEXT("reinforcing: no group named, so it holds where it is");
		}
		break;
	case EAstraGroupOrder::Hold:
		Text = TEXT("holding this position, firing at what comes in range");
		break;
	}
	FString Tail;
	if (G.OrderRangeM > 0.f && G.Order != EAstraGroupOrder::Attack && G.Order != EAstraGroupOrder::Pin && G.Order != EAstraGroupOrder::Withdraw && G.Order != EAstraGroupOrder::Regroup)
	{
		Tail = FString::Printf(TEXT("; it holds %.1f km from its target"), G.OrderRangeM / WarKm);
	}
	if (G.Order != EAstraGroupOrder::Auto && G.Order != EAstraGroupOrder::Withdraw && G.Order != EAstraGroupOrder::Regroup)
	{
		Tail += TEXT("; while this order stands the group does not break off by itself");       // (the automatic retreat is for a group with no commander)
	}
	if (G.OrderUntil > 0.f)
	{
		Tail += FString::Printf(TEXT(" (for %.0f s, then back to its own judgement)"), FMath::Max(0.f, G.OrderUntil - Time));
	}
	return FString::Printf(TEXT("%s: %s%s"), *G.Name, *Text, *Tail);
}

// ---------------------------------------------------------------------------------------------- the command
bool UAstraBattleSubsystem::GroupOrderCommand(const TSharedPtr<FJsonObject>& Args, FString& OutDetail)
{
	if (!Args.IsValid())
	{
		OutDetail = TEXT("group_order needs arguments: side, group, order (and target, for_s, by)");
		return false;
	}
	FString SideText, GroupText, OrderText, TargetText, ByText, FormationText;
	double ForS = 0.0, RangeKm = 0.0;
	Args->TryGetStringField(TEXT("side"), SideText);
	Args->TryGetStringField(TEXT("group"), GroupText);
	Args->TryGetStringField(TEXT("order"), OrderText);
	Args->TryGetStringField(TEXT("target"), TargetText);
	Args->TryGetStringField(TEXT("by"), ByText);
	Args->TryGetStringField(TEXT("formation"), FormationText);
	if (!Args->TryGetNumberField(TEXT("for_s"), ForS))
	{
		Args->TryGetNumberField(TEXT("duration_s"), ForS);
	}
	Args->TryGetNumberField(TEXT("range_km"), RangeKm);                   // optional: the distance to hold from the target
	SideText = SideText.ToLower().TrimStartAndEnd();
	ByText = ByText.ToLower().TrimStartAndEnd();
	const FString Order = OrderText.ToLower().TrimStartAndEnd();
	TargetText = TargetText.TrimStartAndEnd();
	// whose groups, and who may order them
	int32 Me = INDEX_NONE;
	if (SideText == TEXT("astra")) { Me = 0; }
	else if (SideText == TEXT("mandate")) { Me = 1; }
	if (Me == INDEX_NONE)
	{
		OutDetail = FString::Printf(TEXT("side must be \"astra\" or \"mandate\" (got '%s')"), *SideText);
		return false;
	}
	if (Me == 1 && ByText != TEXT("admiral") && ByText != TEXT("commander"))
	{
		OutDetail = TEXT("Mandate groups take orders from the Mandate's admiral or from a group commander (by: \"admiral\" or \"commander\")");
		return false;
	}
	if (Me == 0 && ByText != TEXT("captain") && ByText != TEXT("xo") && ByText != TEXT("commander"))
	{
		OutDetail = TEXT("ASTRA groups take orders from the Captain (through the XO) or from an allied commander (by: \"captain\", \"xo\" or \"commander\")");
		return false;
	}
	static const TCHAR* const Known[] = {TEXT("auto"), TEXT("attack"), TEXT("pin"), TEXT("flank_left"), TEXT("flank_right"), TEXT("screen"), TEXT("withdraw"), TEXT("regroup"), TEXT("reinforce"), TEXT("hold")};
	bool bKnownOrder = false;
	for (const TCHAR* K : Known)
	{
		bKnownOrder |= Order == K;
	}
	if (!bKnownOrder && FormationText.IsEmpty())
	{
		OutDetail = FString::Printf(TEXT("unknown order '%s': auto, attack, pin, flank_left, flank_right, screen, withdraw, regroup, reinforce or hold"), *OrderText);
		return false;
	}
	// which groups: one by name, id or a ship of it; "all" is for the admiral, the Captain and the fleet's commander
	TArray<FAstraBattleGroup*> Targets;
	if (GroupText.TrimStartAndEnd().Equals(TEXT("all"), ESearchCase::IgnoreCase))
	{
		if (ByText == TEXT("commander") && Me == 1)
		{
			OutDetail = TEXT("a group commander orders one group; \"all\" is the admiral's");
			return false;
		}
		for (FAstraBattleGroup& G : Groups)
		{
			if (AstraSideIdx(G.Side) == Me && G.Members.Num() > 0)
			{
				Targets.Add(&G);
			}
		}
	}
	else
	{
		FString Why;
		FAstraBattleGroup* G = ResolveGroup(GroupText, Me, &Why);
		if (!G)
		{
			TArray<FString> Names;
			for (const FAstraBattleGroup& X : Groups)
			{
				if (AstraSideIdx(X.Side) == Me && X.Members.Num() > 0)
				{
					Names.Add(X.Name);
				}
			}
			OutDetail = !Why.IsEmpty() ? Why : FString::Printf(TEXT("no %s group '%s' (yours: %s)"), Me == 0 ? TEXT("ASTRA") : TEXT("Mandate"), *GroupText, Names.Num() ? *FString::Join(Names, TEXT(", ")) : TEXT("none"));
			return false;
		}
		Targets.Add(G);
	}
	if (Targets.Num() == 0)
	{
		OutDetail = TEXT("that side has no groups in the fight");
		return false;
	}
	// what the order is about: an enemy ship, or an enemy group by one of its ships (a track the side holds), or a friendly group/ship
	FAstraBattleShip* TargetShip = nullptr;
	FAstraBattleGroup* TargetGroup = nullptr;
	const bool bNeedsEnemy = Order == TEXT("attack") || Order == TEXT("pin") || Order == TEXT("flank_left") || Order == TEXT("flank_right");
	if (!TargetText.IsEmpty() && Order != TEXT("auto") && Order != TEXT("withdraw") && Order != TEXT("regroup") && Order != TEXT("hold"))
	{
		if (bNeedsEnemy)
		{
			FString Tag = TargetText;
			bool bGroupOf = false;
			for (const TCHAR* Prefix : {TEXT("hostile group of "), TEXT("group of ")})
			{
				if (Tag.StartsWith(Prefix, ESearchCase::IgnoreCase))
				{
					Tag = Tag.Mid(FCString::Strlen(Prefix)).TrimStartAndEnd();
					bGroupOf = true;
					break;
				}
			}
			FAstraBattleShip* T = Tag.Contains(TEXT("AQUILA"), ESearchCase::IgnoreCase) ? (Ships.Num() ? &Ships[0] : nullptr) : FindByContact(Tag.ToUpper());
			if (!T || !T->bAlive || T->bCraft || AstraSideIdx(T->Side) != 1 - Me)
			{
				OutDetail = FString::Printf(TEXT("'%s' is not a hostile warship on your plot: name one by its contact id (or \"group of <id>\")"), *TargetText);
				return false;
			}
			FVector TSeen;
			if (!OnPlot(Me, *T, TSeen))
			{
				OutDetail = FString::Printf(TEXT("you hold no track on %s now: an order needs a contact you can see"), *Tag.ToUpper());
				return false;
			}
			if (bGroupOf && T->GroupId >= 0)
			{
				TargetGroup = FindGroup(T->GroupId);
			}
			else
			{
				TargetShip = T;
			}
		}
		else if (Order == TEXT("reinforce"))
		{
			FString Why;
			TargetGroup = ResolveGroup(TargetText, Me, &Why);
			if (!TargetGroup)
			{
				OutDetail = !Why.IsEmpty() ? Why : FString::Printf(TEXT("no friendly group '%s' to reinforce"), *TargetText);
				return false;
			}
		}
		else if (Order == TEXT("screen"))
		{
			FAstraBattleShip* P = TargetText.Contains(TEXT("AQUILA"), ESearchCase::IgnoreCase) ? (Ships.Num() ? &Ships[0] : nullptr) : FindByContact(TargetText.ToUpper());
			if (!P || !P->bAlive || AstraSideIdx(P->Side) != Me || P->bCraft)
			{
				OutDetail = FString::Printf(TEXT("'%s' is not a friendly ship to screen"), *TargetText);
				return false;
			}
			TargetShip = P;
		}
	}
	if (Order == TEXT("reinforce") && !TargetGroup)
	{
		OutDetail = TEXT("reinforce needs a target: the friendly group to go to");
		return false;
	}
	// carry it out
	TArray<FString> Done;
	for (FAstraBattleGroup* G : Targets)
	{
		if (Order == TEXT("reinforce") && TargetGroup && TargetGroup->Id == G->Id)
		{
			Done.Add(FString::Printf(TEXT("%s: cannot reinforce itself"), *G->Name));
			continue;
		}
		if (FormationText == TEXT("line")) { G->Formation = EAstraFormation::Line; }
		else if (FormationText == TEXT("wedge")) { G->Formation = EAstraFormation::Wedge; }
		else if (FormationText == TEXT("column")) { G->Formation = EAstraFormation::Column; }
		else if (FormationText == TEXT("screen")) { G->Formation = EAstraFormation::Screen; }
		if (!bKnownOrder)
		{
			Done.Add(FString::Printf(TEXT("%s: %s formation"), *G->Name, *FormationText));
			continue;
		}
		G->OrderShip = G->OrderGroup = -1;                                   // (no stale target from an earlier order)
		G->OrderRangeM = 0.f;
		FString Detail;
		const float Duration = FMath::Clamp((float)ForS, 0.f, 3600.f);
		const FString ShipContact = (TargetShip && bNeedsEnemy) ? (TargetShip->bPlayer ? FString(TEXT("AQUILA")) : TargetShip->ContactId) : FString();
		if (!SetGroupOrder(G->Id, Order, ShipContact, TargetGroup && Order == TEXT("reinforce") ? TargetGroup->Id : INDEX_NONE, Duration, ByText, Detail))
		{
			Done.Add(Detail);
			continue;
		}
		if (bNeedsEnemy && TargetGroup)
		{
			G->OrderGroup = TargetGroup->Id;                                 // "group of X": the whole group, its ships in turn
			G->OrderShip = -1;
		}
		if (Order == TEXT("screen") && TargetShip)
		{
			G->ProtecteeId = TargetShip->Id;
		}
		if (RangeKm > 0.0 && Order != TEXT("auto") && Order != TEXT("withdraw") && Order != TEXT("regroup"))
		{
			G->OrderRangeM = (float)(FMath::Clamp(RangeKm, 1.5, 12.0) * WarKm);   // the commander's distance: stands over the group's own choice
		}
		Done.Add(DescribeGroupOrder(*G, bNeedsEnemy ? TargetShip : nullptr, TargetGroup));
	}
	OutDetail = FString::Join(Done, TEXT("; "));
	return true;
}

// ---------------------------------------------------------------------------------------------- what a side's mind may read
TSharedRef<FJsonObject> UAstraBattleSubsystem::SideGroupsJson(int32 SideIdx) const
{
	TSharedRef<FJsonObject> R = MakeShared<FJsonObject>();
	static const TCHAR* const States[] = {TEXT("engaged"), TEXT("withdrawing"), TEXT("regrouping")};
	static const TCHAR* const Orders[] = {TEXT("auto"), TEXT("attack"), TEXT("pin"), TEXT("flank_left"), TEXT("flank_right"), TEXT("screen"), TEXT("withdraw"),
	                                      TEXT("regroup"), TEXT("reinforce"), TEXT("hold")};
	static const TCHAR* const Forms[] = {TEXT("line"), TEXT("wedge"), TEXT("column"), TEXT("screen")};
	const FAstraBattleShip* Viewer = Ships.Num() ? (SideIdx == 0 ? &Ships[0] : FindByContact(MandateCommander())) : nullptr;
	FVector Ref = Viewer ? Viewer->Pos : FVector::ZeroVector;           // the ranges are given from the Aquila (ASTRA) or the strike group's flagship (Mandate)
	if (bSandbox || (Viewer && !Viewer->bAlive))
	{
		for (const FAstraBattleGroup& G : Groups)                       // (a bench scenario has no Aquila: from the side's first group)
		{
			if (AstraSideIdx(G.Side) == SideIdx && G.Members.Num() > 0 && !G.Centroid.IsZero())
			{
				Ref = G.Centroid;
				break;
			}
		}
	}
	// --- its own groups: everything (the datalink)
	TArray<TSharedPtr<FJsonValue>> Own;
	TSet<int32> OwnShips;
	for (const FAstraBattleGroup& G : Groups)
	{
		if (AstraSideIdx(G.Side) != SideIdx || G.Members.Num() == 0)
		{
			continue;
		}
		TSharedRef<FJsonObject> J = MakeShared<FJsonObject>();
		J->SetNumberField(TEXT("id"), G.Id);
		J->SetStringField(TEXT("name"), G.Name);
		J->SetStringField(TEXT("state"), States[(int32)G.State]);
		J->SetStringField(TEXT("formation"), Forms[(int32)G.Formation]);
		J->SetStringField(TEXT("order_in_force"), Orders[(int32)G.Order]);
		if (G.Order != EAstraGroupOrder::Auto)
		{
			J->SetStringField(TEXT("order_by"), G.OrderBy.IsEmpty() ? FString(TEXT("unknown")) : G.OrderBy);
			if (G.OrderUntil > 0.f)
			{
				J->SetNumberField(TEXT("order_seconds_left"), FMath::Max(0.0, OrdRound(G.OrderUntil - Time, 1.0)));
			}
			if (const FAstraBattleShip* OT = FindById(G.OrderShip))
			{
				J->SetStringField(TEXT("order_target"), OT->bPlayer ? FString(TEXT("AQUILA")) : OT->ContactId);
			}
			else if (const FAstraBattleGroup* OG = FindGroup(G.OrderGroup))
			{
				J->SetStringField(TEXT("order_target"), OG->Name);
			}
		}
		if (const FAstraBattleShip* L = FindById(G.LeaderId))
		{
			J->SetStringField(TEXT("leader"), L->ContactId);
		}
		if (const FAstraBattleShip* F = FindById(G.FocusTarget))
		{
			J->SetStringField(TEXT("focus_fire_on"), F->bPlayer ? FString(TEXT("AQUILA")) : F->ContactId);
		}
		J->SetNumberField(TEXT("engagement_range_km"), OrdRound(G.EngageRange / WarKm, 0.1));
		J->SetNumberField(TEXT("your_strength"), OrdRound(G.Strength, 0.1));
		J->SetNumberField(TEXT("enemy_strength_near"), OrdRound(G.EnemyStrength, 0.1));
		J->SetNumberField(TEXT("allied_strength_near"), OrdRound(G.AlliedStrength, 0.1));
		J->SetNumberField(TEXT("morale"), OrdRound(G.Morale, 0.01));
		TArray<TSharedPtr<FJsonValue>> Mem;
		for (const int32 Id : G.Members)
		{
			const FAstraBattleShip* S = FindById(Id);
			if (!S || !S->bAlive)
			{
				continue;
			}
			OwnShips.Add(S->Id);
			TSharedRef<FJsonObject> M = MakeShared<FJsonObject>();
			M->SetStringField(TEXT("id"), S->ContactId);
			M->SetStringField(TEXT("class"), OrdClassOf(*S, true));
			M->SetNumberField(TEXT("hull_pct"), OrdPct(S->Hull, S->HullMax));
			M->SetNumberField(TEXT("shields_pct"), OrdPct(S->Shield, S->ShieldMax));
			if (S->Dmg.bModel)
			{
				// the six shield faces (bow, stern, port, starboard, dorsal, ventral), only when one of them has been shot down
				bool bHurt = false;
				TArray<TSharedPtr<FJsonValue>> Sec;
				for (int32 f = 0; f < AstraWar::NumFacings; ++f)
				{
					const double P = OrdPct(S->Dmg.Sector[f], S->Dmg.SectorMax[f]);
					bHurt |= P < 90.0;
					Sec.Add(MakeShared<FJsonValueNumber>(P));
				}
				if (bHurt)
				{
					M->SetArrayField(TEXT("shield_faces_pct"), Sec);
				}
			}
			M->SetNumberField(TEXT("missiles"), S->Missiles);
			FleetBriefInto(*S, M, true, 3);                                // FLOTTA-VIVA: what burns aboard, how many are left, what power the guns and the drive still have
			if (S->bDisabled)
			{
				M->SetStringField(TEXT("status"), TEXT("disabled"));
			}
			else if (S->bFleeing)
			{
				M->SetStringField(TEXT("status"), S->bNegotiated ? TEXT("withdrawing as ordered") : TEXT("breaking off, too damaged"));
			}
			else if (S->Task != EAstraTask::Formation)
			{
				M->SetStringField(TEXT("status"), OrdTaskName(S->Task));
			}
			Mem.Add(MakeShared<FJsonValueObject>(M));
		}
		J->SetArrayField(TEXT("members"), Mem);
		Own.Add(MakeShared<FJsonValueObject>(J));
	}
	R->SetArrayField(TEXT("your_groups"), Own);
	// --- the enemy's groups as this side sees them: the ships it holds on its sensors, together as they fly together
	struct FSeen { int32 Key; TArray<const FAstraBattleShip*> Ships; };
	TArray<FSeen> Seen;
	for (const FAstraBattleShip& X : Ships)
	{
		if (!X.bAlive || X.bCraft || X.bGhost || X.bDerelict || X.bDisabled || AstraSideIdx(X.Side) != 1 - SideIdx)
		{
			continue;
		}
		FVector SeenAt;
		if (!OnPlot(SideIdx, X, SeenAt))
		{
			continue;
		}
		const int32 Key = X.GroupId >= 0 ? X.GroupId : -1 - X.Id;           // a ship outside any group stands alone
		FSeen* S = Seen.FindByPredicate([Key](const FSeen& F) { return F.Key == Key; });
		if (!S)
		{
			Seen.Add({Key, {}});
			S = &Seen.Last();
		}
		S->Ships.Add(&X);
	}
	TArray<TSharedPtr<FJsonValue>> Foe;
	for (const FSeen& F : Seen)
	{
		TSharedRef<FJsonObject> J = MakeShared<FJsonObject>();
		FString Lowest;
		double Near = 1e18;
		FVector C = FVector::ZeroVector;
		TArray<TSharedPtr<FJsonValue>> Mem;
		for (const FAstraBattleShip* X : F.Ships)
		{
			const FString Id = X->bPlayer ? FString(TEXT("AQUILA")) : X->ContactId;
			Lowest = (Lowest.IsEmpty() || Id < Lowest) ? Id : Lowest;
			FVector P = X->Pos;
			OnPlot(SideIdx, *X, P);
			C += P;
			Near = FMath::Min(Near, (double)FVector::Dist(P, Ref));
			TSharedRef<FJsonObject> M = MakeShared<FJsonObject>();
			M->SetStringField(TEXT("id"), Id);
			const bool bClass = SideIdx == 1 || !X->bFog || X->bClassified;
			M->SetStringField(TEXT("class"), OrdClassOf(*X, bClass));
			if (!X->bCold && (SideIdx == 1 || !X->bFog || X->Track >= 2))
			{
				M->SetNumberField(TEXT("hull_pct"), OrdPct(X->Hull, X->HullMax));
				M->SetNumberField(TEXT("shields_pct"), OrdPct(X->Shield, X->ShieldMax));
				FleetBriefInto(*X, M, false, bClass ? 2 : 1);              // FLOTTA-VIVA: what the sensors and the eye make of her inside (a breach venting, windows dark, hot spots)
			}
			if (X->bFleeing)
			{
				M->SetStringField(TEXT("status"), TEXT("breaking off"));
			}
			Mem.Add(MakeShared<FJsonValueObject>(M));
		}
		C /= FMath::Max(1, F.Ships.Num());
		J->SetStringField(TEXT("label"), FString::Printf(TEXT("group of %s"), *Lowest));
		J->SetArrayField(TEXT("ships"), Mem);
		J->SetNumberField(TEXT("range_km"), OrdRound(FVector::Dist(C, Ref) / WarKm, 0.1));
		J->SetNumberField(TEXT("nearest_ship_km"), OrdRound(Near / WarKm, 0.1));
		J->SetNumberField(TEXT("bearing_deg"), FMath::RoundToDouble(BearingDeg(Ref, C)));
		Foe.Add(MakeShared<FJsonValueObject>(J));
	}
	R->SetArrayField(TEXT("enemy_groups"), Foe);
	// --- what happened to its groups lately (the last few, newest last; `n` counts up, so a mind can tell what is new)
	TArray<TSharedPtr<FJsonValue>> Ev;
	for (int32 i = FMath::Max(0, GroupEvents.Num() - 16); i < GroupEvents.Num(); ++i)
	{
		const FAstraGroupEvent& E = GroupEvents[i];
		if (E.SideIdx != SideIdx || Time - E.T > 180.f)
		{
			continue;
		}
		TSharedRef<FJsonObject> J = MakeShared<FJsonObject>();
		J->SetNumberField(TEXT("n"), E.Serial);
		J->SetNumberField(TEXT("ago_s"), FMath::RoundToDouble(Time - E.T));
		J->SetStringField(TEXT("text"), E.Text);
		Ev.Add(MakeShared<FJsonValueObject>(J));
	}
	R->SetArrayField(TEXT("group_events"), Ev);
	return R;
}
