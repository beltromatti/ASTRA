// ASTRA — ABBORDAGGI-2: the assault craft of the war: the kinds, what a carrier has, and the battle's side of a boarding (members of UAstraBattleSubsystem): the launches, the flights, the
// hatch, the point defence's chance, the berths, the events. Docs: AstraBoardCraft.h, docs/brief/ABBORDAGGI-2.md §1.
//
//   leave      out of the boat bay of the carrier, along the bay's axis, clear of the hull
//   cross      to a point in front of the hatch it was given (the target's frame: it follows her if she turns), straight through whatever point defence the target has: it does not
//              keep out of an envelope, it has to pass it; round the target's hull, not through it
//   approach   down the hatch's axis, slowing, lining up (nose to the hull, the hull's up above it); the shield on that face must be down (or the ship dead): else it waits off the hull
//   latch      touching: it moves with the hull as a part of it; after the kind's time the way in is cut and the men go through (the host's event)
//   depart     the fight is over: it lets go, backs off, and goes home to the bay (the carrier's: it comes to the mouth along its axis like a landing)

#include "AstraBoardCraft.h"
#include "AstraBattleSubsystem.h"
#include "AstraWarClasses.h"
#include "ASTRA.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/World.h"
#include "HAL/IConsoleManager.h"

namespace AstraBoardCraft
{
	const FKind& Skiff()
	{
		// the Mandate's: a crude, armoured wedge with a cutting ring on its nose; slower to answer the stick than a Kestrel
		static const FKind K{FName(TEXT("skiff")), TEXT("Skiff"), TEXT("SM_CRAFT_MANDATE_Skiff"), TEXT("Kharon Mandate boarding skiff"), true, 10, 140.f, 9.f, 7.5f, 220.f, 45.f, 0.06f, 70.f, 12.f};
		return K;
	}

	const FKind& Kestrel()
	{
		// ASTRA's assault shuttle (Deck 8's bay): a heavier hull, a clamp collar that mates with a hatch
		static const FKind K{FName(TEXT("kestrel")), TEXT("Kestrel"), TEXT("SM_CRAFT_ASTRA_Kestrel"), TEXT("ASTRA assault shuttle (Kestrel)"), false, 12, 200.f, 11.f, 9.f, 180.f, 40.f, 0.05f, 70.f, 9.f};
		return K;
	}

	const FKind* KindByKey(FName Key)
	{
		if (Key == Skiff().Key)
		{
			return &Skiff();
		}
		if (Key == Kestrel().Key)
		{
			return &Kestrel();
		}
		return nullptr;
	}

	double AquilaSkinM(double HullXm)
	{
		// the half beam of her plating at the decks of the airlocks (z about 0 to 14 m), sampled on the mesh: constant along the middle, narrowing towards the bow
		static const double X[] = {170.0, 188.0, 212.0, 236.0, 260.0};
		static const double Y[] = {50.6, 49.5, 47.35, 45.2, 43.2};
		if (HullXm <= X[0])
		{
			return 50.7;
		}
		for (int32 i = 1; i < UE_ARRAY_COUNT(X); ++i)
		{
			if (HullXm <= X[i])
			{
				return Y[i - 1] + (Y[i] - Y[i - 1]) * (HullXm - X[i - 1]) / (X[i] - X[i - 1]);
			}
		}
		return Y[UE_ARRAY_COUNT(Y) - 1];
	}

	FBerths BerthsOf(FName ClassKey, const FVector& HullHalfM, float HullMidM)
	{
		FBerths B;
		const FString K = ClassKey.ToString().ToLower();
		if (K == TEXT("aquila"))
		{
			B.Kind = &Kestrel();
			B.Count = 2;
			B.Bay = FVector(212.0, -AquilaSkinM(212.0), 2.0);       // Deck 8's assault-shuttle bay (d8_shuttle_bay_B1: the plan's x 24..56, y -38..-22, with the hull's origin 172 m ahead of the bridge) opens on the port side, on her plating
			B.BayNormal = FVector(0.0, -1.0, 0.0);
			return B;
		}
		int32 Count = 0;
		bool bMandate = false;
		if (K == TEXT("praetorian")) { Count = 2; }
		else if (K == TEXT("vigilant")) { Count = 1; }
		else if (K == TEXT("acheron")) { Count = 4; bMandate = true; }
		else if (K == TEXT("styx")) { Count = 2; bMandate = true; }
		else if (K == TEXT("lethe")) { Count = 1; bMandate = true; }
		if (Count == 0)
		{
			return B;
		}
		B.Kind = bMandate ? &Skiff() : &Kestrel();
		B.Count = Count;
		const double Y = FMath::Max(10.0, HullHalfM.Y * 0.9);
		B.Bay = FVector(HullMidM + HullHalfM.X * 0.15, bMandate ? Y : -Y, 0.0);
		B.BayNormal = FVector(0.0, bMandate ? 1.0 : -1.0, 0.0);
		return B;
	}

	const TCHAR* PhaseName(EPhase P, bool bHome)
	{
		switch (P)
		{
		case EPhase::Idle: return TEXT("in the bay");
		case EPhase::Leaving: return TEXT("leaving the bay");
		case EPhase::Transit: return bHome ? TEXT("going home") : TEXT("crossing to the target");
		case EPhase::Approach: return bHome ? TEXT("coming into the bay") : TEXT("closing on the hatch");
		case EPhase::Hold: return TEXT("held off the hull by a shield");
		case EPhase::Latching: return TEXT("latched, cutting in");
		case EPhase::Docked: return TEXT("docked");
		case EPhase::Undocking: return TEXT("letting go");
		}
		return TEXT("?");
	}

	const TCHAR* EventName(EEventKind K)
	{
		switch (K)
		{
		case EEventKind::Launched: return TEXT("launched");
		case EEventKind::Docked: return TEXT("docked");
		case EEventKind::Destroyed: return TEXT("destroyed");
		case EEventKind::Aborted: return TEXT("aborted");
		case EEventKind::Departed: return TEXT("departed");
		case EEventKind::Recovered: return TEXT("recovered");
		case EEventKind::Lost: return TEXT("lost");
		}
		return TEXT("?");
	}

	int32 FacingOfNormal(const FVector& LocalNormal)
	{
		return AstraFacingOf(LocalNormal);
	}
}

using namespace AstraBoardCraft;



// ---------------------------------------------------------------------------------------------------------- the facts
bool UAstraBattleSubsystem::BoardingDockOpen(const FAstraBattleShip& T, const FVector& LocalNormal, float* OutFrac) const
{
	float Frac = 0.f;
	bool bOpen = true;
	if (T.bDisabled)
	{
		Frac = 0.f;                                              // no power: no shield
	}
	else if (T.Dmg.bModel)
	{
		const int32 F = AstraFacingOf(LocalNormal);
		Frac = T.Dmg.SectorMax[F] > 0.f ? T.Dmg.Sector[F] / T.Dmg.SectorMax[F] : 0.f;
		bOpen = !T.bShieldsUp || Frac <= ShieldDownFrac;
		if (!T.bShieldsUp)
		{
			Frac = 0.f;
		}
	}
	else
	{
		Frac = (T.bShieldsUp && T.ShieldMax > 0.f) ? T.Shield / T.ShieldMax : 0.f;
		bOpen = Frac <= ShieldDownFrac;
	}
	if (OutFrac)
	{
		*OutFrac = Frac;
	}
	return bOpen;
}

bool UAstraBattleSubsystem::AssessBoarding(int32 CarrierId, int32 TargetId, FAssess& Out) const
{
	Out = FAssess();
	const FAstraBattleShip* T = FindById(TargetId);
	const FAstraBattleShip* C = CarrierId >= 0 ? FindById(CarrierId) : nullptr;
	if (!T)
	{
		return false;
	}
	Out.TargetName = T->Name;
	Out.TargetClass = T->Class;
	Out.HullFrac = T->HullMax > 0.f ? T->Hull / T->HullMax : 1.f;
	Out.bTargetDisabled = T->bDisabled;
	if (!T->bAlive)
	{
		Out.TargetWhy = TEXT("she is destroyed");
	}
	else if (T->bFixture)
	{
		Out.TargetWhy = TEXT("she is a place of the system, not a ship in this war: nobody docks a boat at her");
	}
	else if (T->bCraft || T->bGhost)
	{
		Out.TargetWhy = TEXT("a craft cannot be boarded");
	}
	else if (!T->Dmg.bModel)
	{
		Out.TargetWhy = TEXT("she is not a ship with a hull that can be boarded");
	}
	else
	{
		Out.bTargetOk = true;
	}
	if (T->bAlive)
	{
		const int32 Channels = T->bDisabled ? 0 : (T->Dmg.bModel ? FMath::CeilToInt(T->PDChannels * T->Dmg.Sys[AstraWar::SysPointDefence]) : T->PDChannels);
		Out.PdChannels = Channels;
		Out.PdRangeKm = Channels > 0 ? (T->PDRange + T->Radius) / 1000.f : 0.f;
		Out.bShieldsKnown = true;
		for (int32 f = 0; f < 6; ++f)
		{
			Out.ShieldFrac[f] = T->bDisabled || !T->bShieldsUp ? 0.f : (T->Dmg.bModel ? (T->Dmg.SectorMax[f] > 0.f ? FMath::Clamp(T->Dmg.Sector[f] / T->Dmg.SectorMax[f], 0.f, 1.f) : 0.f)
			                                                                          : (T->ShieldMax > 0.f ? FMath::Clamp(T->Shield / T->ShieldMax, 0.f, 1.f) : 0.f));
		}
		const int32 Side = AstraSideIdx(T->Side);
		if (Side >= 0)
		{
			for (const int32 J : CraftBySide[Side])
			{
				const FAstraBattleShip& O = Ships[J];
				Out.EnemyCraftNear += (O.bAlive && O.CraftKind != 3 && FVector::DistSquared(O.Pos, T->Pos) < FMath::Square(4000.0 + T->Radius)) ? 1 : 0;
			}
		}
	}
	if (!C || !C->bAlive || C->bCraft || C->bFixture)
	{
		Out.CarrierWhy = TEXT("there is no such carrier");
		return true;
	}
	Out.CarrierName = C->Name;
	const FBerths Bth = BerthsOf(C->ClassKey, FVector(C->Box.Hx, C->Box.Hy, C->Box.Hz), C->Box.Mid);
	if (!Bth.Kind || Bth.Count <= 0)
	{
		Out.CarrierWhy = FString::Printf(TEXT("the %s carries no boarding craft"), C->ClassKey.IsNone() ? *C->Class : *C->ClassKey.ToString());
		return true;
	}
	Out.KindKey = Bth.Kind->Key.ToString();
	Out.MenPerCraft = Bth.Kind->Men;
	FBay Bay = BoardBays.FindRef(C->Id);
	if (Bay.Total == 0 && Bay.Lost == 0)
	{
		Bay.Total = Bth.Count;
	}
	int32 Queued = 0;
	for (const FPendingLaunch& P : BoardLaunches)
	{
		Queued += P.Req.CarrierId == C->Id ? FMath::Max(0, P.Req.Docks.Num() - P.Index) : 0;
	}
	Out.BerthsTotal = Bay.Total - Bay.Lost;
	Out.BerthsFree = FMath::Max(0, Bay.Free() - Queued);
	if (C->bDisabled)
	{
		Out.CarrierWhy = TEXT("she has no power: nothing can leave her");
	}
	else if (HangarFactor(*C) <= 0.f)
	{
		Out.CarrierWhy = TEXT("her hangar is wrecked: nothing can leave her");
	}
	else if (Out.BerthsFree <= 0)
	{
		Out.CarrierWhy = Bay.Total - Bay.Lost > 0 ? FString::Printf(TEXT("all %d of her %ss are away or on their way"), Bay.Total - Bay.Lost, Bth.Kind->Callsign)
		                                          : FString::Printf(TEXT("her %ss are all lost"), Bth.Kind->Callsign);
	}
	else
	{
		Out.bCarrierOk = true;
	}
	Out.DistKm = (float)(FVector::Dist(C->Pos, T->Pos) / 1000.0);
	Out.EtaS = (float)(FMath::Max(0.0, FVector::Dist(C->Pos, T->Pos) - T->Radius - StageM) / FMath::Max(80.0, (double)Bth.Kind->Cruise * 0.85) + 20.0 + Bth.Kind->LatchS);
	return true;
}

int32 UAstraBattleSubsystem::ResolveShip(const FString& Key, FString* OutWhy) const
{
	const FString K = Key.TrimStartAndEnd();
	if (K.IsEmpty())
	{
		if (OutWhy) { *OutWhy = TEXT("no ship named"); }
		return -1;
	}
	if (K.Equals(TEXT("aquila"), ESearchCase::IgnoreCase) || K.Equals(TEXT("the aquila"), ESearchCase::IgnoreCase) || K.Equals(TEXT("us"), ESearchCase::IgnoreCase) || K.Equals(TEXT("player"), ESearchCase::IgnoreCase))
	{
		return Ships.Num() ? Ships[0].Id : -1;
	}
	if (const FAstraBattleShip* S = FindByContact(K); S && !S->bCraft)
	{
		return S->Id;
	}
	TArray<int32> Hits;
	const FString Q = K.ToLower();
	for (const FAstraBattleShip& S : Ships)
	{
		if (S.bCraft || S.bGhost || !S.bAlive)
		{
			continue;
		}
		const FString N = S.Name.ToLower();
		if (N == Q || N == TEXT("asn ") + Q || N == TEXT("kms ") + Q)
		{
			return S.Id;
		}
		if (N.Contains(Q) || (!S.ClassKey.IsNone() && S.ClassKey.ToString() == Q))
		{
			Hits.Add(S.Id);
		}
	}
	if (Hits.Num() == 1)
	{
		return Hits[0];
	}
	if (OutWhy)
	{
		if (Hits.IsEmpty())
		{
			*OutWhy = FString::Printf(TEXT("no ship of the battle is called '%s' (a contact id, as T-30, or her name)"), *K);
		}
		else
		{
			FString List;
			for (int32 i = 0; i < FMath::Min(5, Hits.Num()); ++i)
			{
				const FAstraBattleShip* S = FindById(Hits[i]);
				List += FString::Printf(TEXT("%s%s (%s)"), i ? TEXT(", ") : TEXT(""), S ? *S->Name : TEXT("?"), S ? *S->ContactId : TEXT("?"));
			}
			*OutWhy = FString::Printf(TEXT("'%s' fits %d ships: %s — name one by its contact id"), *K, Hits.Num(), *List);
		}
	}
	return -1;
}

bool UAstraBattleSubsystem::ShipFacts(int32 Id, FShipFacts& Out) const
{
	const FAstraBattleShip* S = FindById(Id);
	if (!S)
	{
		return false;
	}
	Out = FShipFacts();
	Out.Id = S->Id;
	Out.ContactId = S->ContactId;
	Out.Name = S->Name;
	Out.ClassText = S->Class;
	Out.ClassKey = S->ClassKey;
	Out.Side = AstraSideIdx(S->Side) >= 0 ? AstraSideIdx(S->Side) : 2;
	Out.bAlive = S->bAlive;
	Out.bDisabled = S->bDisabled;
	Out.bCraft = S->bCraft;
	Out.bPlayer = S->bPlayer;
	Out.bDerelict = S->bDerelict;
	Out.bHasModel = S->Dmg.bModel;
	Out.bFixture = S->bFixture;
	Out.Pos = S->Pos;
	Out.Vel = S->Vel;
	Out.Att = S->Att;
	if (S->Box.Valid())
	{
		Out.BoxHalf = FVector(S->Box.Hx, S->Box.Hy, S->Box.Hz);
		Out.BoxMid = S->Box.Mid;
	}
	Out.Radius = S->Radius;
	Out.HullFrac = S->HullMax > 0.f ? S->Hull / S->HullMax : 1.f;
	return true;
}

void UAstraBattleSubsystem::ListShipFacts(TArray<FShipFacts>& Out) const
{
	for (const FAstraBattleShip& S : Ships)
	{
		if (S.bAlive && !S.bCraft && !S.bGhost && !S.bFixture)         // (a place of the system is neither a carrier nor a target: it is not listed)
		{
			FShipFacts F;
			if (ShipFacts(S.Id, F))
			{
				Out.Add(MoveTemp(F));
			}
		}
	}
}

bool UAstraBattleSubsystem::CaptureShip(int32 Id, const FString& By, FString& OutDetail, int32 ForSide)
{
	FAstraBattleShip* S = FindById(Id);
	if (!S || !S->bAlive || S->bCraft || S->bPlayer)
	{
		OutDetail = TEXT("there is no such ship to take");
		return false;
	}
	const EAstraSide To = ForSide == 1 ? EAstraSide::Mandate : EAstraSide::Astra;
	if (S->Side == To)
	{
		OutDetail = To == EAstraSide::Astra ? TEXT("she is ours already") : TEXT("she is theirs already");
		return false;
	}
	S->Side = To;
	S->bHostile = To != EAstraSide::Astra;
	S->bHoldFire = true;
	S->bFleeing = false;
	S->bFog = false;
	S->bIdentified = true;
	S->bClassified = true;
	S->Track = 2;
	S->Mode = EAstraShipMode::Idle;
	S->TargetId = -1;
	S->OrderTarget = -1;
	++PlotStamp;
	Report(To == EAstraSide::Astra ? FString::Printf(TEXT("tactical: %s is ours — taken by %s; she has no power and a prize crew aboard"), *S->Name, *By)
	                               : FString::Printf(TEXT("tactical: %s has been taken by the Mandate (%s); she has no power and a prize crew aboard"), *S->Name, *By), true);
	OutDetail = FString::Printf(TEXT("%s is %s"), *S->Name, To == EAstraSide::Astra ? TEXT("ours") : TEXT("the Mandate's"));
	return true;
}

AstraBoardCraft::FBay UAstraBattleSubsystem::BoardBayOf(int32 CarrierId) const
{
	if (const FBay* B = BoardBays.Find(CarrierId))
	{
		return *B;
	}
	FBay Out;
	if (const FAstraBattleShip* C = FindById(CarrierId))
	{
		Out.Total = BerthsOf(C->ClassKey, FVector(C->Box.Hx, C->Box.Hy, C->Box.Hz), C->Box.Mid).Count;
	}
	return Out;
}

void UAstraBattleSubsystem::ConsumeBoardEvents(TArray<FCraftEvent>& Out)
{
	Out.Append(MoveTemp(BoardEvents));
	BoardEvents.Reset();
}

// ---------------------------------------------------------------------------------------------------------- events
void UAstraBattleSubsystem::EmitBoardEvent(EEventKind Kind, const FAstraBattleShip& S, const FString& Cause)
{
	FCraftEvent E;
	E.Time = Time;
	E.Kind = Kind;
	E.CraftId = S.Id;
	E.Order = S.Board.Order;
	E.Leg = S.Board.Leg;
	E.CarrierId = S.Board.CarrierId;
	E.TargetId = S.Board.TargetId;
	E.KindKey = S.Board.Kind;
	E.CraftName = S.Name;
	E.Men = S.Board.Men;
	E.bMenAboard = !S.Board.bUnloaded && S.Board.Men > 0;
	E.bCaptain = S.Board.bCaptain;
	E.DockId = S.Board.DockId;
	E.Dock = S.Board.Dock;
	E.DockNormal = S.Board.DockNormal;
	E.Cause = Cause;
	if (const FAstraBattleShip* C = FindById(S.Board.CarrierId))
	{
		E.CarrierName = C->Name;
	}
	if (const FAstraBattleShip* T = FindById(S.Board.TargetId))
	{
		E.TargetName = T->Name;
	}
	UE_LOG(LogASTRA, Display, TEXT("[Boarding] %7.1f %s %s (order %d leg %d, %d men%s) %s -> %s%s%s"), Time, EventName(E.Kind), *E.CraftName, E.Order, E.Leg, E.Men, E.bMenAboard ? TEXT(", aboard") : TEXT(""),
	       *E.CarrierName, *E.TargetName, E.Cause.IsEmpty() ? TEXT("") : TEXT(": "), *E.Cause);
	BoardEvents.Add(MoveTemp(E));
	if (BoardEvents.Num() > 128)
	{
		BoardEvents.RemoveAt(0, 32);
	}
}

void UAstraBattleSubsystem::RemoveBoardingCraft(FAstraBattleShip& S)
{
	S.bAlive = false;
	S.Mode = EAstraShipMode::Dead;
	if (S.Actor) { S.Actor->Destroy(); S.Actor = nullptr; }
	if (S.DriveFlare) { S.DriveFlare->Destroy(); S.DriveFlare = nullptr; }
}

void UAstraBattleSubsystem::NoteBoardingCraftLost(FAstraBattleShip& S, EAstraHitKind Cause)
{
	// called by Destroy for a boarding craft: it is a boat the carrier will not get back, and the men in it (if they are still aboard) go with it
	FString Why;
	const FAstraBattleShip* Killer = S.LastHitBy >= 0 ? FindById(S.LastHitBy) : nullptr;
	switch (Cause)
	{
	case EAstraHitKind::PointDefence:
		Why = Killer ? FString::Printf(TEXT("shot down by the point defence of %s"), *Killer->Name) : FString(TEXT("shot down by point defence"));
		break;
	case EAstraHitKind::Cannon:
		Why = Killer ? FString::Printf(TEXT("shot down by %s"), *Killer->Name) : FString(TEXT("shot down by fighters"));
		break;
	case EAstraHitKind::Missile:
	case EAstraHitKind::Torpedo:
	case EAstraHitKind::Rocket:
		Why = TEXT("hit by a missile");
		break;
	default:
		Why = (S.Board.Phase == EPhase::Latching || S.Board.Phase == EPhase::Docked || S.Board.Phase == EPhase::Undocking) ? FString(TEXT("lost with the ship she was latched to")) : FString(TEXT("destroyed"));
		break;
	}
	if (FBay* B = BoardBays.Find(S.Board.CarrierId))
	{
		B->Away = FMath::Max(0, B->Away - 1);
		++B->Lost;
	}
	EmitBoardEvent(EEventKind::Destroyed, S, Why);
	// the crew sees a boat of the enemy's go, when it is one that was coming for the Aquila or is near her
	if (S.Side == EAstraSide::Mandate && Ships.Num() && (S.Board.TargetId == Ships[0].Id || FVector::DistSquared(S.Pos, Ships[0].Pos) < FMath::Square(40000.0)))
	{
		Report(FString::Printf(TEXT("tactical: %s (a Mandate boarding skiff) %s"), *S.Name, *Why), false);
	}
}

// ---------------------------------------------------------------------------------------------------------- the launches
bool UAstraBattleSubsystem::LaunchBoarding(const FLaunch& Req, FLaunchResult& Out)
{
	Out = FLaunchResult();
	const FAstraBattleShip* C = FindById(Req.CarrierId);
	const FAstraBattleShip* T = FindById(Req.TargetId);
	if (!C || !C->bAlive || C->bCraft || C->bFixture)
	{
		Out.Why = TEXT("there is no such carrier");
		return false;
	}
	if (!T || !T->bAlive || T->bCraft || T->bGhost || T->bFixture || !T->Dmg.bModel)
	{
		Out.Why = !T || !T->bAlive ? TEXT("the target is gone") : (T->bFixture ? TEXT("that is a place of the system, not a ship to dock a boat at") : TEXT("that is not a ship with a hull to board"));
		return false;
	}
	if (C->Id == T->Id)
	{
		Out.Why = TEXT("a ship does not board herself");
		return false;
	}
	const FBerths Bth = BerthsOf(C->ClassKey, FVector(C->Box.Hx, C->Box.Hy, C->Box.Hz), C->Box.Mid);
	if (!Bth.Kind || Bth.Count <= 0)
	{
		Out.Why = FString::Printf(TEXT("the %s carries no boarding craft"), C->ClassKey.IsNone() ? *C->Class : *C->ClassKey.ToString());
		return false;
	}
	const FKind& K = *Bth.Kind;
	if (C->bDisabled || HangarFactor(*C) <= 0.f)
	{
		Out.Why = C->bDisabled ? TEXT("she has no power: nothing can leave her") : TEXT("her hangar is wrecked: nothing can leave her");
		return false;
	}
	if (Req.Docks.IsEmpty())
	{
		Out.Why = TEXT("no hatch was given to dock at");
		return false;
	}
	FBay& Bay = BoardBays.FindOrAdd(C->Id);
	if (Bay.Total == 0 && Bay.Lost == 0)
	{
		Bay.Total = Bth.Count;
	}
	int32 Queued = 0;
	for (const FPendingLaunch& P : BoardLaunches)
	{
		Queued += P.Req.CarrierId == C->Id ? FMath::Max(0, P.Req.Docks.Num() - P.Index) : 0;
	}
	const int32 Free = Bay.Free() - Queued;
	if (Free <= 0)
	{
		Out.Why = Bay.Total - Bay.Lost > 0 ? FString::Printf(TEXT("all %d of her %ss are away or on their way"), Bay.Total - Bay.Lost, K.Callsign)
		                                   : FString::Printf(TEXT("her %ss are all lost"), K.Callsign);
		return false;
	}
	const int32 N = FMath::Min(Req.Docks.Num(), Free);
	FPendingLaunch P;
	P.Req = Req;
	P.Req.KindKey = K.Key;
	P.Req.Docks.SetNum(N);
	P.Req.Men.SetNum(N);
	for (int32 i = 0; i < N; ++i)
	{
		const int32 M = Req.Men.IsValidIndex(i) ? Req.Men[i] : K.Men;
		P.Req.Men[i] = FMath::Clamp(M, 0, K.Men);
		Out.Men += P.Req.Men[i];
	}
	P.T = FMath::Max(0.f, Req.FirstS);
	BoardLaunches.Add(P);
	Out.bOk = true;
	Out.Craft = N;
	Out.KindKey = K.Key.ToString();
	Out.EtaS = (float)(FMath::Max(0.0, FVector::Dist(C->Pos, T->Pos) - T->Radius - StageM) / FMath::Max(80.0, (double)K.Cruise * 0.85) + 20.0 + P.T + K.LatchS);
	if (N < Req.Docks.Num())
	{
		Out.Why = FString::Printf(TEXT("only %d of the %d %ss asked for were free"), N, Req.Docks.Num(), K.Callsign);
	}
	UE_LOG(LogASTRA, Log, TEXT("[Boarding] %s launches %d %s%s at %s (%d men, order %d)"), *C->Name, N, K.Callsign, N > 1 ? TEXT("s") : TEXT(""), *T->Name, Out.Men, Req.Order);
	return true;
}

namespace
{
	/** What the bench asks of a ship (astra.board.strip / shield / disable / pd): kept until the battle's next tick makes it (the console is not the battle's thread of work). */
	struct FBenchOp
	{
		FString What;
		FString Key;
		float Value = 0.f;
	};
	TArray<FBenchOp> GBenchOps;
	int32 GBenchOrder = 9000;
}

void UAstraBattleSubsystem::TickBoardingLaunches(float Dt)
{
	for (const FBenchOp& Op : GBenchOps)
	{
		const int32 Id = ResolveShip(Op.Key);
		FAstraBattleShip* S = Id >= 0 ? FindById(Id) : nullptr;
		if (!S)
		{
			UE_LOG(LogASTRA, Display, TEXT("[Boarding] bench: no ship '%s'"), *Op.Key);
			continue;
		}
		if (Op.What == TEXT("strip") || Op.What == TEXT("shield"))
		{
			const float F = Op.What == TEXT("strip") ? 0.f : Op.Value;
			for (int32 f = 0; f < AstraWar::NumFacings; ++f)
			{
				S->Dmg.Sector[f] = S->Dmg.SectorMax[f] * F;
			}
			if (S->Dmg.bModel)
			{
				SyncTotals(*S);
			}
			S->bShieldsUp = F > 0.f;
		}
		else if (Op.What == TEXT("disable"))
		{
			DisableShip(*S, TEXT("test"));
		}
		else if (Op.What == TEXT("pd"))
		{
			S->PDChannels = FMath::RoundToInt(Op.Value);
		}
		else if (Op.What == TEXT("fixture"))
		{
			S->bFixture = true;                                      // (what SPAZIO-VIVO makes of a station: the war bench has no living space to ask it of)
		}
		UE_LOG(LogASTRA, Display, TEXT("[Boarding] bench: %s %s %g"), *Op.What, *S->Name, Op.Value);
	}
	GBenchOps.Reset();
	if (BoardLaunches.IsEmpty())
	{
		return;
	}
	for (int32 pi = BoardLaunches.Num() - 1; pi >= 0; --pi)
	{
		FPendingLaunch& P = BoardLaunches[pi];
		P.T -= Dt;
		const FKind* K = KindByKey(P.Req.KindKey);
		const FAstraBattleShip* C = FindById(P.Req.CarrierId);
		const FAstraBattleShip* T = FindById(P.Req.TargetId);
		FString Cancel;
		if (!K || !C || !C->bAlive)
		{
			Cancel = TEXT("the carrier is lost");
		}
		else if (!T || !T->bAlive)
		{
			Cancel = TEXT("the target is gone");
		}
		else if (T->bFixture || C->bFixture)
		{
			Cancel = TEXT("a place of the system is no ship to dock a boat at");
		}
		else if (C->bDisabled || HangarFactor(*C) <= 0.f)
		{
			Cancel = TEXT("the carrier can no longer launch");
		}
		if (!Cancel.IsEmpty())
		{
			// what has not left will not: the order is told, craft by craft
			for (int32 i = P.Index; i < P.Req.Docks.Num(); ++i)
			{
				FCraftEvent E;
				E.Time = Time;
				E.Kind = EEventKind::Aborted;
				E.Order = P.Req.Order;
				E.Leg = i;
				E.CarrierId = P.Req.CarrierId;
				E.TargetId = P.Req.TargetId;
				E.KindKey = P.Req.KindKey;
				E.Men = P.Req.Men.IsValidIndex(i) ? P.Req.Men[i] : 0;
				E.bMenAboard = false;
				E.Cause = Cancel;
				E.CraftName = TEXT("(not launched)");
				if (C) { E.CarrierName = C->Name; }
				if (T) { E.TargetName = T->Name; }
				BoardEvents.Add(E);
			}
			BoardLaunches.RemoveAt(pi);
			continue;
		}
		if (P.T > 0.f)
		{
			continue;
		}
		// the next boat leaves the bay
		const int32 Leg = P.Index;
		const FBerths Bth = BerthsOf(C->ClassKey, FVector(C->Box.Hx, C->Box.Hy, C->Box.Hz), C->Box.Mid);
		const FVector CarrierPos = C->Pos, CarrierVel = C->Vel;     // copies: AddShip may reallocate Ships
		const FQuat CarrierAtt = C->Att;
		const EAstraSide Side = C->Side;
		const FString CarrierName = C->Name, CarrierClass = C->Class, TargetName = T->Name;
		const FVector NormalW = CarrierAtt.RotateVector(Bth.BayNormal).GetSafeNormal();
		const FVector Pos = CarrierPos + CarrierAtt.RotateVector(Bth.Bay) + NormalW * (K->HalfLength + 4.0);
		const int32 SideIdx = K->bMandate ? 1 : 0;
		const int32 Number = NextBoardCraft[SideIdx]++;
		const FDockPoint Dock = P.Req.Docks[Leg];
		const int32 Men = P.Req.Men.IsValidIndex(Leg) ? P.Req.Men[Leg] : K->Men;
		const FLaunch Req = P.Req;
		++P.Index;
		P.T = P.Req.GapS;
		const bool bLast = P.Index >= P.Req.Docks.Num();
		const FVector TargetPos = T->Pos;
		const float TargetRadius = T->Radius;
		const bool bTargetIsPlayer = T->bPlayer;
		if (bLast)
		{
			BoardLaunches.RemoveAt(pi);
		}
		const int32 I = AddShip(FString::Printf(TEXT("%s-%d"), *FString(K->Callsign).ToUpper(), Number), FString::Printf(TEXT("%s %d"), K->Callsign, Number), K->ClassText, K->Mesh,
		                        K->bMandate ? EAstraSide::Mandate : EAstraSide::Astra, Pos, 0.f, 0.f, K->Radius, K->Hull, 0.f);
		FAstraBattleShip& S = Ships[I];
		S.bCraft = true;
		S.Squadron = -1;
		S.CraftKind = 3;
		S.Mission = TEXT("board");
		S.MissionTarget = Req.TargetId;
		S.Torpedoes = 0;
		S.RailDamage = 0.f;
		S.Missiles = 0;
		S.PDRange = 0.f;
		S.PDChannels = 0;
		S.bShieldsUp = false;
		S.Att = FRotationMatrix::MakeFromX(NormalW).ToQuat();
		S.Vel = CarrierVel + NormalW * 40.0;
		S.CruiseSpeed = K->Cruise;
		S.MaxAccel = K->Accel;
		S.MaxTurnDeg = 70.f;
		S.Speed = S.Vel.Size();
		S.Mode = EAstraShipMode::Cruise;
		S.bHostile = K->bMandate;
		S.SensorKm = 12.f;
		S.CombatValue = 0.3f;
		FFlight& B = S.Board;
		B = FFlight();
		B.Phase = EPhase::Leaving;
		B.Order = Req.Order;
		B.Leg = Leg;
		B.TargetId = Req.TargetId;
		B.CarrierId = Req.CarrierId;
		B.Men = Men;
		B.bCaptain = Req.bCaptain && Leg == 0;
		B.Kind = K->Key;
		B.DockId = Dock.Id;
		B.Dock = Dock.Local;
		B.DockNormal = Dock.Normal.GetSafeNormal();
		B.Bay = Bth.Bay;
		B.BayNormal = Bth.BayNormal;
		B.Side = (Number % 2) ? 1.f : -1.f;
		++Stats.CraftLaunched[SideIdx];
		SpawnVisual(S);
		if (K->bMandate == false)
		{
			HullSound(TEXT("SW_Catapult"), 0.7f, 0.9f);
		}
		BoardBays.FindOrAdd(Req.CarrierId).Away += 1;
		EmitBoardEvent(EEventKind::Launched, S, FString());
		if (K->bMandate && Leg == 0 && bTargetIsPlayer)
		{
			const FAstraBattleShip* Cr = FindById(Req.CarrierId);
			const double DistKm = FVector::Dist(TargetPos, CarrierPos) / 1000.0;
			Report(FString::Printf(TEXT("sensors: %s has launched boarding craft (%d on this run) — they are heading for the Aquila's %s side, about %.0f s away; point defence and the fighters can stop them, and they cannot dock where our shield is up"),
			                       Cr ? *KnownLabel(*Cr) : *CarrierName, Req.Docks.Num(), AstraWar::FacingName(FacingOfNormal(Dock.Normal)), (float)(FMath::Max(0.0, DistKm * 1000.0 - TargetRadius) / FMath::Max(80.0, (double)K->Cruise * 0.85) + 20.0)), true);
		}
		(void)CarrierClass;
		(void)TargetName;
	}
}

// ---------------------------------------------------------------------------------------------------------- the orders to the craft
int32 UAstraBattleSubsystem::DepartBoardingOrder(int32 Order)
{
	int32 N = 0;
	for (FAstraBattleShip& S : Ships)
	{
		if (!S.bAlive || S.CraftKind != 3 || S.Board.Order != Order)
		{
			continue;
		}
		FFlight& B = S.Board;
		if (B.Phase == EPhase::Latching || B.Phase == EPhase::Docked)
		{
			B.bDepart = true;
			++N;
		}
	}
	return N;
}

int32 UAstraBattleSubsystem::AbortBoardingOrder(int32 Order, const FString& Why)
{
	int32 N = 0;
	for (int32 pi = BoardLaunches.Num() - 1; pi >= 0; --pi)
	{
		FPendingLaunch& P = BoardLaunches[pi];
		if (P.Req.Order != Order)
		{
			continue;
		}
		const FAstraBattleShip* C = FindById(P.Req.CarrierId);
		for (int32 i = P.Index; i < P.Req.Docks.Num(); ++i)
		{
			FCraftEvent E;
			E.Time = Time;
			E.Kind = EEventKind::Aborted;
			E.Order = Order;
			E.Leg = i;
			E.CarrierId = P.Req.CarrierId;
			E.TargetId = P.Req.TargetId;
			E.KindKey = P.Req.KindKey;
			E.Men = P.Req.Men.IsValidIndex(i) ? P.Req.Men[i] : 0;
			E.Cause = Why;
			E.CraftName = TEXT("(not launched)");
			if (C) { E.CarrierName = C->Name; }
			BoardEvents.Add(E);
			++N;
		}
		BoardLaunches.RemoveAt(pi);
	}
	for (FAstraBattleShip& S : Ships)
	{
		if (!S.bAlive || S.CraftKind != 3 || S.Board.Order != Order)
		{
			continue;
		}
		const EPhase Ph = S.Board.Phase;
		if (Ph == EPhase::Leaving || Ph == EPhase::Transit || Ph == EPhase::Approach || Ph == EPhase::Hold)
		{
			if (!S.Board.bHome && !S.Board.bAbort)
			{
				S.Board.bAbort = true;
				S.Board.Men = S.Board.bUnloaded ? 0 : S.Board.Men;
				EmitBoardEvent(EEventKind::Aborted, S, Why);
				++N;
			}
		}
	}
	return N;
}



// ---------------------------------------------------------------------------------------------------------- the bench's console
namespace
{
	UAstraBattleSubsystem* BcBattle(UWorld* W)
	{
		return W ? W->GetSubsystem<UAstraBattleSubsystem>() : nullptr;
	}

	FAutoConsoleCommandWithWorldAndArgs BcCmdCraft(TEXT("astra.board.craft"),
		TEXT("Testing: boarding craft from a carrier to a target: astra.board.craft <carrier> <target> [n] [port|starboard|bow|stern|dorsal|ventral] [men]"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& A, UWorld* W)
		{
			UAstraBattleSubsystem* B = BcBattle(W);
			if (!B || A.Num() < 2)
			{
				return;
			}
			FString Why;
			const int32 Cid = B->ResolveShip(A[0], &Why);
			const int32 Tid = B->ResolveShip(A[1], &Why);
			FShipFacts C, T;
			if (Cid < 0 || Tid < 0 || !B->ShipFacts(Cid, C) || !B->ShipFacts(Tid, T))
			{
				UE_LOG(LogASTRA, Display, TEXT("[Boarding] bench: %s"), *Why);
				return;
			}
			const int32 N = A.Num() > 2 ? FMath::Clamp(FCString::Atoi(*A[2]), 1, 8) : 2;
			int32 Facing = AstraFacingOf(T.Att.UnrotateVector(C.Pos - T.Pos).GetSafeNormal());
			if (A.Num() > 3)
			{
				static const TCHAR* const Names[] = {TEXT("bow"), TEXT("stern"), TEXT("port"), TEXT("starboard"), TEXT("dorsal"), TEXT("ventral")};
				for (int32 f = 0; f < 6; ++f)
				{
					Facing = A[3].Equals(Names[f], ESearchCase::IgnoreCase) ? f : Facing;
				}
			}
			const FVector Nrm = AstraWar::FacingVector(Facing);
			const FVector Half = T.BoxHalf.IsNearlyZero() ? FVector(T.Radius) : T.BoxHalf;
			FLaunch Req;
			Req.CarrierId = Cid;
			Req.TargetId = Tid;
			Req.Order = GBenchOrder++;
			for (int32 i = 0; i < N; ++i)
			{
				const double S = N > 1 ? ((double)i / (N - 1) - 0.5) * 2.0 : 0.0;                  // -1 .. 1 along the face
				FDockPoint D;
				D.Normal = Nrm;
				D.Id = FName(*FString::Printf(TEXT("bench_%d"), i));
				FVector L(T.BoxMid + Nrm.X * Half.X, Nrm.Y * Half.Y, Nrm.Z * Half.Z);
				if (FMath::Abs(Nrm.X) < 0.5)
				{
					L.X = T.BoxMid + S * Half.X * 0.3;
				}
				else
				{
					L.Y = S * Half.Y * 0.4;
				}
				D.Local = L;
				Req.Docks.Add(D);
				if (A.Num() > 4)
				{
					Req.Men.Add(FCString::Atoi(*A[4]));
				}
			}
			FLaunchResult R;
			const bool bOk = B->LaunchBoarding(Req, R);
			UE_LOG(LogASTRA, Display, TEXT("[Boarding] bench: %s: %d craft (%d men), the first flies ~%.0f s%s%s"), bOk ? TEXT("launched") : TEXT("refused"), R.Craft, R.Men, R.EtaS, R.Why.IsEmpty() ? TEXT("") : TEXT(" — "), *R.Why);
			UE_LOG(LogASTRA, Display, TEXT("[Boarding] bench: order %d"), Req.Order);
		}));

	FAutoConsoleCommandWithWorldAndArgs BcCmdDepart(TEXT("astra.board.depart"), TEXT("Testing: the craft of an order let go of the hull and go home: astra.board.depart <order>"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& A, UWorld* W)
		{
			if (UAstraBattleSubsystem* B = BcBattle(W); B && A.Num() >= 1)
			{
				UE_LOG(LogASTRA, Display, TEXT("[Boarding] bench: %d craft let go"), B->DepartBoardingOrder(FCString::Atoi(*A[0])));
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs BcCmdAssess(TEXT("astra.board.assess"), TEXT("Testing: what a decision to board rests on: astra.board.assess <carrier> <target>"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& A, UWorld* W)
		{
			UAstraBattleSubsystem* B = BcBattle(W);
			if (!B || A.Num() < 2)
			{
				return;
			}
			FAssess F;
			if (!B->AssessBoarding(B->ResolveShip(A[0]), B->ResolveShip(A[1]), F))
			{
				UE_LOG(LogASTRA, Display, TEXT("[Boarding] bench: no such ship"));
				return;
			}
			UE_LOG(LogASTRA, Display, TEXT("[Boarding] assess: carrier %s %s%s; berths %d free of %d (%s, %d men each); target %s %s%s; %.1f km, flight ~%.0f s; point defence %d channels to %.1f km; shields bow %.0f%% stern %.0f%% port %.0f%% starboard %.0f%% dorsal %.0f%% ventral %.0f%%; %d fighters near; hull %.0f%%%s"),
			       *F.CarrierName, F.bCarrierOk ? TEXT("can launch") : TEXT("cannot"), *(F.bCarrierOk ? FString() : TEXT(": ") + F.CarrierWhy), F.BerthsFree, F.BerthsTotal, *F.KindKey, F.MenPerCraft, *F.TargetName,
			       F.bTargetOk ? TEXT("can be boarded") : TEXT("cannot be boarded"), *(F.bTargetOk ? FString() : TEXT(": ") + F.TargetWhy), F.DistKm, F.EtaS, F.PdChannels, F.PdRangeKm, F.ShieldFrac[0] * 100.f, F.ShieldFrac[1] * 100.f,
			       F.ShieldFrac[2] * 100.f, F.ShieldFrac[3] * 100.f, F.ShieldFrac[4] * 100.f, F.ShieldFrac[5] * 100.f, F.EnemyCraftNear, F.HullFrac * 100.f, F.bTargetDisabled ? TEXT(", no power") : TEXT(""));
		}));

#define BC_OP_COMMAND(NAME, HELP, NEEDS_VALUE) \
	FAutoConsoleCommandWithWorldAndArgs BcCmdOp_##NAME(TEXT("astra.board." #NAME), TEXT(HELP), \
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& A, UWorld* W) \
		{ \
			if (A.Num() >= (NEEDS_VALUE ? 2 : 1)) \
			{ \
				FBenchOp Op; \
				Op.What = TEXT(#NAME); \
				Op.Key = A[0]; \
				Op.Value = NEEDS_VALUE ? FCString::Atof(*A[1]) : 0.f; \
				GBenchOps.Add(Op); \
			} \
			(void)W; \
		}))
	BC_OP_COMMAND(strip, "Testing: a ship's shields to nothing: astra.board.strip <ship>", false);
	BC_OP_COMMAND(shield, "Testing: a ship's shield sectors to a share of their capacity: astra.board.shield <ship> <0..1>", true);
	BC_OP_COMMAND(disable, "Testing: a ship loses all power (a hulk): astra.board.disable <ship>", false);
	BC_OP_COMMAND(pd, "Testing: a ship's point-defence channels: astra.board.pd <ship> <n>", true);
	BC_OP_COMMAND(fixture, "Testing: a ship becomes a place of the system, as a station is (nobody docks a boat at her or flies one from her): astra.board.fixture <ship>", false);
#undef BC_OP_COMMAND
}
