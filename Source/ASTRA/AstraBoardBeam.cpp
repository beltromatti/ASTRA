// ASTRA — ABBORDAGGI: the transporter's side of a boarding (docs/ABBORDAGGI.md §13.10, docs/TELETRASPORTO.md §10).
//
// The transporter (AstraTransporter*.cpp) carries people between the Aquila's pads and a ship in range by its own rules: the shield on the face between them, the range, the jamming, the Aquila's
// manoeuvring. What it cannot know is what is aboard the other ship when our marines are fighting there: where they hold a room, where the Mandate does, where there is no air. This is that, and the
// news of who has been set down and who taken off:
//
//   BeamAboardQuery  may the beam set people down aboard that ship now, and where: a room our marines hold (one of ours on his feet in it, no enemy who can fight in it or who can see the spot), with air and
//                    no fire, beside them on clear floor: never in a room the Mandate holds, never where there is no air; and for the Captain a boat of ours at her hatches (the way home if the beam is blocked)
//   BeamPrepare      the pattern has left the ship: her decks are made solid round where he will stand (the Captain only: marines have no body of their own there)
//   BeamedAboard     the Captain is set down: he is in the fight on her decks as the one who came in the boat is; a marine: a man of the simulation in a squad of his own that goes for the objective
//   BeamedOff        the Captain, or a person, was taken off her decks: out of the fight, aboard the Aquila
//
// The rules of the beam itself stay the transporter's (his shields, the range, the jamming): nothing here relaxes them.

#include "AstraBoardSubsystem.h"

#include "ASTRA.h"
#include "AstraBattleSubsystem.h"
#include "AstraBoardInterior.h"
#include "AstraCrewRoster.h"
#include "AstraLifeSubsystem.h"
#include "AstraShipSubsystem.h"
#include "Engine/World.h"

using namespace AstraBoard;
using AstraBoardCraft::FShipFacts;

namespace
{
	/** Where one of ours stands; the places round him are tried in a ring that starts at the way he faces (his comrades face the enemy). */
	constexpr double BmRings[] = {130.0, 210.0, 300.0};
	constexpr int32 BmDirections = 8;
	constexpr float BmClearCm = 95.f;                  // nobody stands nearer than this to where a person materializes
	constexpr float BmSeenFromCm = 3200.f;             // an enemy who sees the spot from this near and can fight: it is no place to arrive
}

bool UAstraBoardSubsystem::BoardedByUs(FString& OutContact, FString& OutName) const
{
	if (!Assault.bOn || !Assault.bRoster || Assault.bObserved || !Assault.bSceneBegun || Phase != EPhase::Active || Mode != EMode::Remote || !Map.IsValid() || Fight.Over())
	{
		return false;
	}
	const UAstraBattleSubsystem* B = Battle();
	FShipFacts T;
	if (!B || !B->ShipFacts(Assault.TargetId, T))
	{
		return false;
	}
	OutContact = T.ContactId;
	OutName = Assault.TargetName;
	return true;
}

int32 UAstraBoardSubsystem::BoatForTheWayHome() const
{
	for (const FLeg& L : Assault.Legs)
	{
		if (L.State == FLeg::EState::Latched || L.State == FLeg::EState::Through)
		{
			return L.Index;
		}
	}
	return INDEX_NONE;
}

bool UAstraBoardSubsystem::BeamAboardQuery(const FString& ShipContact, int32 Count, bool bCaptain, const FBeamLimits& Lim, FBeamAboard& Out) const
{
	Out = FBeamAboard();
	FString Contact, Name;
	if (!BoardedByUs(Contact, Name) || !Contact.Equals(ShipContact, ESearchCase::IgnoreCase))
	{
		Out.Why = TEXT("no marine of ours is fighting aboard her: her decks are not in the pattern library, and there is nobody to materialize beside");
		Out.Fix = TEXT("land the marines first (the Kestrels at her hatches): the beam sets people down beside them");
		return false;
	}
	Out.bScene = true;
	Count = FMath::Max(1, Count);
	if (bCaptain && BoatForTheWayHome() == INDEX_NONE)
	{
		Out.Why = FString::Printf(TEXT("no boat of ours is at %s's hatches: the Captain goes aboard her only with a boat there to bring him off if the beam is blocked"), *Name);
		Out.Fix = TEXT("a Kestrel latched at her hatch (the marines cut in)");
		return false;
	}
	// the rooms of her plan with someone in them who can fight: ours and theirs
	struct FRoom
	{
		int32 Comp = INDEX_NONE;
		TArray<int32> Friends;
		int32 Foes = 0;
	};
	TMap<int32, FRoom> Rooms;
	TArray<const FUnit*> Foes;
	for (const FUnit& U : Fight.Units())
	{
		if (U.bExternal || !U.Able() || !Map->GetComps().IsValidIndex(U.Comp))
		{
			continue;
		}
		FRoom& R = Rooms.FindOrAdd(U.Comp);
		R.Comp = U.Comp;
		if (U.Side == ESide::Aquila)
		{
			R.Friends.Add(U.Id);
		}
		else
		{
			++R.Foes;
			Foes.Add(&U);
		}
	}
	TArray<FRoom> Held;
	for (const TPair<int32, FRoom>& KV : Rooms)
	{
		if (KV.Value.Friends.Num() > 0)
		{
			Held.Add(KV.Value);
		}
	}
	if (Held.IsEmpty())
	{
		Out.Why = TEXT("not one marine of ours is on his feet aboard her: nobody to materialize beside");
		Out.Fix = TEXT("wait for the marines to be up, or for the boats to put more in");
		return false;
	}
	Held.Sort([](const FRoom& A, const FRoom& B) { return A.Friends.Num() != B.Friends.Num() ? A.Friends.Num() > B.Friends.Num() : A.Comp < B.Comp; });
	bool bHot = false, bThin = false, bCrowded = false;
	for (const FRoom& R : Held)
	{
		if (R.Foes > 0)
		{
			bHot = true;                                          // the Mandate holds a part of that room
			continue;
		}
		if (const FBoardRoomMood* M = Assault.Moods.Find(R.Comp); M && (M->bGutted || M->Air < Lim.AirMin || M->Fire > Lim.FireMax || M->Smoke > Lim.SmokeMax))
		{
			bThin = true;                                         // no air to speak of, or fire, smoke: no place to arrive
			continue;
		}
		const FBoardComp& C = Map->GetComps()[R.Comp];
		const float Floor = (float)C.FloorZ();
		TArray<FVector> Chosen;
		TArray<float> Yaws;
		const auto Clear = [&](const FVector& P)
		{
			for (const FUnit& U : Fight.Units())
			{
				if (!U.bExternal && U.Act != EAct::Gone && U.Act != EAct::Waiting && U.CarriedBy == INDEX_NONE && FVector::Dist2D(U.Pos, P) < BmClearCm && FMath::Abs(U.Pos.Z - P.Z) < 150.0)
				{
					return false;                                 // a man standing, or lying, there
				}
			}
			for (const FVector& Done : Chosen)
			{
				if (FVector::Dist2D(Done, P) < BmClearCm + 5.f)
				{
					return false;
				}
			}
			return true;
		};
		for (const int32 Uid : R.Friends)
		{
			const FUnit& F = *Fight.Unit(Uid);
			for (const double Radius : BmRings)
			{
				for (int32 k = 0; k < BmDirections && Chosen.Num() < Count; ++k)
				{
					const double A = FMath::DegreesToRadians((double)F.Yaw + 360.0 * (double)k / (double)BmDirections);
					FVector P(F.Pos.X + FMath::Cos(A) * Radius, F.Pos.Y + FMath::Sin(A) * Radius, Floor);
					P = Map->Inset(R.Comp, P, 60.f);
					P.Z = Floor;
					if (Map->CompAt(P) != R.Comp || !Clear(P))
					{
						continue;
					}
					Chosen.Add(P);
					Yaws.Add(F.Yaw);
				}
			}
			if (Chosen.Num() >= Count)
			{
				break;
			}
		}
		if (Chosen.Num() < Count)
		{
			bCrowded = true;
			continue;
		}
		// an enemy who can fight and who sees the spot is a Mandate hold of it, door or no door
		bool bSeen = false;
		for (const FUnit* E : Foes)
		{
			bSeen |= FVector::Dist(E->Pos, Chosen[0]) < BmSeenFromCm && FMath::Abs(E->Pos.Z - Chosen[0].Z) < 300.0 && Fight.Sees(E->Eye(), Chosen[0] + FVector(0.0, 0.0, 152.0));
		}
		if (bSeen)
		{
			bHot = true;
			continue;
		}
		for (int32 i = 0; i < Count; ++i)
		{
			FBeamSpot S;
			S.FeetWorld = Chosen[i] + AAstraBoardInterior::ZoneOrigin();
			S.Yaw = Yaws[i];
			Out.Spots.Add(S);
		}
		Out.bOk = true;
		Out.MarinesThere = R.Friends.Num();
		FString Squad;
		if (const FUnit* First = Fight.Unit(R.Friends[0]); First && Fight.Squad(First->Squad))
		{
			Squad = Fight.Squad(First->Squad)->Name;
		}
		Out.Place = FString::Printf(TEXT("%s, beside %d marine%s%s"), *Map->Describe(R.Comp), R.Friends.Num(), R.Friends.Num() == 1 ? TEXT("") : TEXT("s"), Squad.IsEmpty() ? TEXT("") : *FString::Printf(TEXT(" (%s)"), *Squad));
		return true;
	}
	if (bHot)
	{
		Out.Why = FString::Printf(TEXT("every room our marines hold aboard %s has the Mandate in it or in sight of it: the beam does not set a person down in a compartment the Mandate holds"), *Name);
		Out.Fix = TEXT("when the marines have cleared the room, or when the fight has moved off");
	}
	else if (bThin)
	{
		Out.Why = FString::Printf(TEXT("the rooms our marines hold aboard %s have no air to speak of, or are on fire or full of smoke: nobody is set down there"), *Name);
		Out.Fix = TEXT("the marines fall back to a room with air, or the incident is put out");
	}
	else
	{
		Out.Why = FString::Printf(TEXT("there is no clear floor for %d beside our marines aboard %s"), Count, *Name);
		Out.Fix = TEXT("fewer people, or the marines spread out");
	}
	(void)bCrowded;
	return false;
}

void UAstraBoardSubsystem::BeamPrepare(const FBeamAboard& Where, bool bCaptain)
{
	if (!bCaptain || Where.Spots.IsEmpty())
	{
		return;
	}
	EnsureEnemyDecks(Where.Spots[0].FeetWorld - AAstraBoardInterior::ZoneOrigin(), 60);
}

void UAstraBoardSubsystem::BeamedAboard(int32 Roster, bool bCaptain, const FBeamSpot& At)
{
	FString Contact, Name;
	if (!BoardedByUs(Contact, Name))
	{
		UE_LOG(LogASTRA, Warning, TEXT("[Board] a pattern was set down aboard a ship our marines no longer fight on (the fight ended while it was in the buffer)"));
		return;
	}
	const FVector Plan = At.FeetWorld - AAstraBoardInterior::ZoneOrigin();
	if (bCaptain)
	{
		if (Ride != ERide::None)
		{
			return;
		}
		EnsureEnemyDecks(Plan, 60);
		RemoteOffset = AAstraBoardInterior::ZoneOrigin();
		if (bTestCaptain)
		{
			TestFeet = At.FeetWorld;
			TestYaw = At.Yaw;
		}
		if (Fight.CaptainId() == INDEX_NONE)
		{
			Fight.AddCaptain(Plan);
		}
		Fight.SetCaptain(Plan, At.Yaw, false, 0.f, false);
		bCaptainIn = true;                                       // (he is on his feet where the beam set him: the next step of the fight need not find it out)
		Ride = ERide::Aboard;
		RideT = 0.f;
		RideStep = 1;                                            // (the transporter put him on his feet: there is no boat's lock to unlock)
		RideLeg = BoatForTheWayHome();
		bBeamed = true;
		bCaptainInBeam = false;
		bCaptainAboard = true;
		bCapDown = false;
		bChainDown = false;
		MakeSightOverride();
		bPadArmed = false;
		PadDwellS = 0.f;
		bHomeHintShown = false;
		Tell(FString::Printf(TEXT("the Captain is aboard %s with the marines, beamed in from the Transporter Room, in %s: going for %s"), *Assault.TargetName, *Map->Describe(Fight.Unit(Fight.CaptainId()) ? Fight.Unit(Fight.CaptainId())->Comp : INDEX_NONE),
		          *Map->Describe(Fight.Mission().Objective)), true);
		CaptainPrompt(FString::Printf(TEXT("ABOARD %s  ·  %s"), *Assault.TargetName.ToUpper(), *Map->Describe(Fight.Mission().Objective).ToUpper()), 6.f);
		return;
	}
	// a marine of the roster: a man of the simulation in a squad of his own, who goes for the objective with the others
	const UAstraShipSubsystem* S = ShipSub();
	const UAstraLifeSubsystem* L = LifeSub();
	if (!S || !S->GetRoster().Get().IsValidIndex(Roster))
	{
		return;
	}
	const FAstraCrewman& Man = S->GetRoster().Get()[Roster];
	if (!Man.Dept.Equals(TEXT("marines"), ESearchCase::IgnoreCase))
	{
		return;                                                  // (the others are aboard her but no soldiers of the simulation: they keep to the boat's hatch, away, as a person beamed to an allied ship does)
	}
	int32 Sq = INDEX_NONE;
	for (const FSquad& Q : Fight.Squads())
	{
		if (Q.Side == ESide::Aquila && Q.Name.StartsWith(TEXT("Beamed Marines")) && Q.Members.Num() < 6)
		{
			Sq = Q.Id;
		}
	}
	if (Sq == INDEX_NONE)
	{
		int32 Made = 0;
		for (const FSquad& Q : Fight.Squads())
		{
			Made += (Q.Side == ESide::Aquila && Q.Name.StartsWith(TEXT("Beamed Marines"))) ? 1 : 0;
		}
		Sq = Fight.AddSquad(ESide::Aquila, Made == 0 ? FString(TEXT("Beamed Marines")) : FString::Printf(TEXT("Beamed Marines %d"), Made + 1));
	}
	const bool bLeader = Fight.Squad(Sq) && Fight.Squad(Sq)->Members.IsEmpty();
	const int32 U = Fight.AddMarine(Man.Name(), Roster, Plan, bLeader, Sq);
	Fight.BriefAttackers(Sq);
	MarineUnits.AddUnique(U);
	RosterOfUnit.Add(U, Roster);
	if (L && L->IsRunning())
	{
		const int32 P = L->Sim().PersonOfRoster(Roster);
		if (P != INDEX_NONE)
		{
			PersonOfUnit.Add(U, P);
		}
	}
	Tell(FString::Printf(TEXT("%s has been beamed aboard %s beside the marines, in %s"), *Man.Name(), *Assault.TargetName, *Map->Describe(Fight.Unit(U) ? Fight.Unit(U)->Comp : INDEX_NONE)), false);
}

void UAstraBoardSubsystem::BeamedOff(int32 Roster, bool bCaptain, const FVector& FeetWorld)
{
	if (bCaptain)
	{
		if (bTestCaptain)
		{
			TestFeet = FeetWorld;                                // (the bench's Captain stands where the beam set him down)
		}
		const bool bWas = bCaptainAboard;
		bCaptainInBeam = false;
		bBeamed = false;
		if (bWas)
		{
			CaptainLeftScene(TEXT("beamed up"));
		}
		return;
	}
	for (const int32 U : MarineUnits)
	{
		const int32* R = RosterOfUnit.Find(U);
		if (!R || *R != Roster)
		{
			continue;
		}
		const FUnit* Un = Fight.Unit(U);
		if (!Un)
		{
			break;
		}
		if (Un->Act == EAct::Down && !HarmTold.Contains(Roster))
		{
			// wounded and taken off by the beam: alive, to the Medbay as a man carried to his boat is
			HarmTold.Add(Roster);
			if (UAstraShipSubsystem* S = ShipSub())
			{
				S->HarmPerson(Roster, false, TEXT("gunfire"));
			}
		}
		Fight.LeaveShip(U);
		ReleaseBody(U);
		break;
	}
}

void UAstraBoardSubsystem::SetCaptainInBeam(bool bOn)
{
	bCaptainInBeam = bOn;
}

void UAstraBoardSubsystem::BeamOver()
{
	bCaptainInBeam = false;                                      // (a pattern recomposed where it stood is back in the fight)
	if (!bCaptainAboard && Interior && Interior->IsBegun() && Ride == ERide::None)
	{
		EndEnemyDecks();                                         // (decks made for a Captain who did not come)
	}
}

bool UAstraBoardSubsystem::CaptainAboardOtherShip(FString* OutContact) const
{
	if (!bCaptainAboard || Ride != ERide::Aboard)
	{
		return false;
	}
	if (OutContact)
	{
		FShipFacts T;
		const UAstraBattleSubsystem* B = Battle();
		*OutContact = B && B->ShipFacts(Assault.TargetId, T) ? T.ContactId : FString();
	}
	return true;
}

bool UAstraBoardSubsystem::PersonAboardOtherShip(int32 Roster, FString* OutContact) const
{
	FString Contact, Name;
	if (!BoardedByUs(Contact, Name))
	{
		return false;
	}
	for (const int32 U : MarineUnits)
	{
		const int32* R = RosterOfUnit.Find(U);
		const FUnit* Un = Fight.Unit(U);
		if (R && *R == Roster && Un && Un->Act != EAct::Gone && Un->Act != EAct::Dead && Un->Act != EAct::Waiting)
		{
			if (OutContact)
			{
				*OutContact = Contact;
			}
			return true;
		}
	}
	return false;
}
