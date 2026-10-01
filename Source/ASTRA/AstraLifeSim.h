// ASTRA — VITA, the life simulation: the Aquila's 560 people on the ship's plan. Everyone has a watch, a home, a post, a battle
// station and tastes; their day (duty, meals, leisure, sleep) follows from the ship's clock and their own small offsets, and the
// ship's state changes it (an alarm sends everyone to their battle station; an incident sends a repair party; the wounded go to
// the Medbay). Nothing is scripted: what a person does at any moment is a function of their job, the hour and the ship.
//
// It is pure code over the plan (no actors): cheap enough to run for everyone all the time (a slice of the people each frame),
// deterministic from a seed, and testable headless (AstraLifeSimCommandlet). The bodies of the few people near the Captain
// (AstraLifeBody.*) are driven by this simulation and write their progress back to it: a body is the person, where the
// schedule says they are.
//
// Routes come from the plan's subsystem (UAstraShipPlan::FindRoute) through a function the owner gives.

#pragma once

#include "CoreMinimal.h"
#include "AstraCrewRoster.h"
#include "AstraLifeData.h"

struct FAstraDamage;

/** A way over the ship (the plan's route: world cm) and how far along a walker is. The segments that change deck are stairs and
 *  lifts: they take time, not distance. */
struct FAstraLifeRoute
{
	enum class ESeg : uint8 { Walk, Stair, Lift };

	TArray<FVector3f> Pts;
	int32 Seg = 0;                   // walking from Pts[Seg] to Pts[Seg + 1]
	float F = 0.f;                   // 0..1 along that segment

	bool Done() const { return Pts.Num() < 2 || Seg >= Pts.Num() - 1; }
	void Clear() { Pts.Reset(); Seg = 0; F = 0.f; }
	ESeg Kind(int32 S) const;
	/** Seconds one segment takes at a walking speed. */
	float SegSeconds(int32 S, float SpeedCmS, const FAstraLifeSpeed& Sp) const;
	/** Moves Dt seconds along the route (stairs and lifts by their own clocks). */
	void Advance(float Dt, float SpeedCmS, const FAstraLifeSpeed& Sp);
	FVector Position() const;
	/** The direction of travel on the floor plane (a unit vector), zero when there is none. */
	FVector2D Heading() const;
	bool InLift() const { return !Done() && Kind(Seg) == ESeg::Lift; }
	/** On a stair or in a lift: nobody can see them there. */
	bool InShaft() const { return !Done() && Kind(Seg) != ESeg::Walk; }
	float RemainingCm() const;
};

/** Something a person remembers: what they did or saw, in a short English line (the mind plays the person in the Captain's language). */
struct FAstraLifeMemory
{
	double T = 0.0;                  // ship seconds
	uint8 Weight = 1;                // 1 passing .. 3 they will not forget
	FString Text;
};

struct FAstraLifePerson
{
	enum class EPhase : uint8 { Settled, WaitRoute, Walking };

	int32 Roster = INDEX_NONE;
	const FAstraLifeDept* Dept = nullptr;
	uint8 Watch = 0;
	EAstraLifeClass Class = EAstraLifeClass::Rating;
	bool bFemale = false;
	float J[5] = {0, 0, 0, 0, 0};    // the day's own offsets (hours): mid-watch meal, wind-down, turning in, waking meal, sleep length
	float SpeedFactor = 1.f;
	float LeadH = 0.3f;              // how long before their watch they set out (ship hours)
	float LeadMessDutyH = 0.2f;      // how long before sitting down to the mid-watch meal they leave their post
	float LeadMessHomeH = 0.2f;      // how long before the other meals they set out from where they live
	float WakeDelayS = 30.f;         // how long they need to be up and dressed when an alarm goes
	TArray<float> Taste;             // their liking for each way of spending free time
	int32 Home = INDEX_NONE;         // the room they sleep in
	int32 Bunk = INDEX_NONE;         // the bunk they used last
	int32 Duty = INDEX_NONE;         // their post (a place)
	int32 Battle = INDEX_NONE;       // their battle station (a place)
	int32 Friends[3] = {INDEX_NONE, INDEX_NONE, INDEX_NONE};
	FString Job;                     // what they do, in words

	// --- now
	EAstraLifeAct Act = EAstraLifeAct::Duty;
	uint8 Status = 0;                // the roster's: 0 fit, 1 wounded, 2 killed
	int32 Episode = -1;              // the block of the day (or the emergency) they are acting on: a change means choosing again
	int32 Place = INDEX_NONE;        // the place they are at or heading for
	int32 Claimed = INDEX_NONE;      // the place whose occupancy counts them
	FVector Target = FVector::ZeroVector;        // the exact spot they are heading for or stand at (world cm)
	float TargetYaw = 0.f;
	float TargetHeight = 0.f;
	EAstraPlaceKind TargetKind = EAstraPlaceKind::Hub;
	int32 LeisureKind = INDEX_NONE;  // what they chose to do with their free time
	int32 Bed = -1;                  // a wounded person's bed in the Medbay (the roster's), -1 a cot
	EPhase Phase = EPhase::Settled;
	FVector Pos = FVector::ZeroVector;
	FAstraLifeRoute Route;
	float SpeedOverride = 0.f;       // a repair party's pace (cm/s), 0: the usual
	double ReadyAt = 0.0;            // not before this game time (waking, dressing)
	double RetryAt = 0.0;            // no route was found: try again then (game time)
	double LastStep = 0.0;           // game time of the last step
	int32 Party = INDEX_NONE;        // the incident they are working
	int32 PartySlot = 0;
	bool bBody = false;              // a body is moving them (the abstract step leaves their feet to it)
	bool bCommandeered = false;      // ABBORDAGGI: a fight has them (a marine at the guns): no steps, no routes; they stand where the fight puts them
	bool bHurry = false;
	TArray<FAstraLifeMemory> Mem;
};

/** A damage-control party on an incident. */
struct FAstraLifeParty
{
	enum class EState : uint8 { Gathering, EnRoute, Working, Done };

	int32 Incident = INDEX_NONE;     // the ship's damage id
	int32 ShipTeam = -1;             // the ship's number for the team (0..3)
	int32 Deck = 0;
	TCHAR Section = TEXT('A');
	FString Kind;
	int32 SiteComp = INDEX_NONE;
	FVector Site = FVector::ZeroVector;
	TArray<int32> Members;           // people (indices into the simulation's)
	EState State = EState::Gathering;
	double DispatchedAt = 0.0;       // ship time
	double ArrivedAt = 0.0;
	float ShipTravel0 = 0.f;         // what the ship said the team needed to get there (s)
	bool bLate = false;              // the ship's repair began before they arrived
	float DispatchedGame = 0.f;      // game seconds since dispatch
};

/** Everything counted for the tests and the stats. */
struct FAstraLifeStats
{
	int32 Routes = 0, RouteFails = 0, Steps = 0;
	double RouteMs = 0.0, RouteMsMax = 0.0;
	int32 PerAct[(int32)EAstraLifeAct::Count] = {0};
	int32 Walking = 0, Waiting = 0;
};

class ASTRA_API FAstraLifeSim
{
public:
	/** A route over the ship's plan; bRepair: a damage-control party's (it goes through the pressure bulkheads that are shut: its people are suited and cycle the hatch). */
	using FRouter = TFunction<bool(const FVector& From, const FVector& To, TArray<FVector>& Out, bool bRepair)>;

	// ------------------------------------------------------------------------------------------------ set up
	/** The people of the roster on the plan's map: watches, homes, posts, battle stations, tastes, all from the seed; then everyone where the
	 *  schedule puts them at StartHour. */
	void Init(TSharedRef<const FAstraLifeMap> InMap, const FAstraCrewRoster& Roster, int32 InSeed, float StartHour);
	bool IsReady() const { return Map.IsValid() && People.Num() > 0; }
	void SetRouter(FRouter R) { Router = MoveTemp(R); }
	const FAstraLifeMap& GetMap() const { return *Map; }

	// ------------------------------------------------------------------------------------------------ the clock
	double ShipSeconds() const { return Clock; }
	double GameSeconds() const { return GameT; }
	float Hour() const { return (float)FMath::Fmod(Clock / 3600.0, 24.0); }
	int32 DayNumber() const { return (int32)(Clock / 86400.0); }
	/** Sets the ship's hour of the day (everyone goes where the schedule puts them). */
	void SetHour(float H);
	static FString HourText(double ShipSec);

	// ------------------------------------------------------------------------------------------------ stepping
	/** Advances the clocks by game seconds and steps a slice of the people (each about every second of game time); then spends at most
	 *  RouteBudgetS on routes (at least one when someone waits). Focus: where the Captain is (whoever is near is routed first). */
	void Tick(float DtGame, float TimeScale, double RouteBudgetS, const FVector& Focus);
	/** One person's movement by Dt game seconds: what a body asks while it carries them (the same integration as the abstract step). */
	void MoveBody(int32 Person, float Dt, float SpeedCmS);
	/** A body carries the person now (or has let go). */
	void SetBodied(int32 Person, bool bBody);
	/** ABBORDAGGI: a fight takes a person over (a marine at the guns) and puts them at Pos; bOn false gives them back (they decide again from where they stand). */
	void Commandeer(int32 Person, bool bOn, const FVector& Pos);
	/** The speed this person walks at now (cm/s). */
	float WalkSpeed(const FAstraLifePerson& P) const;

	// ------------------------------------------------------------------------------------------------ the ship speaks
	void SetAlert(uint8 Level /* 0 green, 1 yellow, 2 red */);
	uint8 Alert() const { return AlertLevel; }
	/** The roster changed (someone wounded, killed, healed). */
	void SyncRoster(const FAstraCrewRoster& Roster);
	/** The ship's open incidents and their teams. */
	void SyncDamage(const TArray<FAstraDamage>& Damage);
	/** The plan changed (a door sealed): routes in progress are made again. */
	void PlanChanged();

	// ------------------------------------------------------------------------------------------------ asking
	int32 NumPeople() const { return People.Num(); }
	const FAstraLifePerson& Person(int32 I) const { return People[I]; }
	int32 PersonOfRoster(int32 RosterIdx) const { return RosterToPerson.IsValidIndex(RosterIdx) ? RosterToPerson[RosterIdx] : INDEX_NONE; }
	const TArray<FAstraLifeParty>& Parties() const { return PartyList; }
	const TCHAR* WatchName(int32 W) const { return Map.IsValid() && Map->Watches.IsValidIndex(W) ? *Map->Watches[W].Name : TEXT("?"); }
	/** Where the person is, as a room and in words. */
	int32 CompOf(int32 Person) const;
	FString Where(int32 Person) const;
	FString Doing(int32 Person) const;
	/** Fit people physically in a room, or in a deck's section (what a hit there can hurt). */
	void PeopleInComp(int32 CompIdx, TArray<int32>& Out) const;
	void PeopleIn(int32 Deck, TCHAR Section, TArray<int32>& Out) const;
	/** The person at a pre-placed actor's place (a Mess seat, a rack): who the actor should be, or INDEX_NONE. */
	int32 WhoIsAt(FName ExternalStation) const;
	void Stats(FAstraLifeStats& Out) const;
	/** Seconds a repair party needs to reach a place, from where the nearest people who would go are (the ship's "on scene in"). */
	float PartyEtaSeconds(const FVector& Site, int32 Deck) const;
	/** Where an incident in a deck and section is worked (a room or a stretch of corridor the same on every call for that incident), and how
	 *  long a party takes to get there: what the ship should say when it dispatches a team. */
	FVector SiteOf(int32 Deck, TCHAR Section, int32 IncidentId, int32* OutComp = nullptr) const;
	float RepairEtaSeconds(int32 Deck, TCHAR Section, int32 IncidentId) const;
	/** The same for an incident that knows its compartment (DISTRUZIONE): the party goes to that room (a corridor tract, a store), or to the
	 *  nearest place that is open when the room is walled off. */
	FVector SiteOfIncident(const FAstraDamage& D, int32* OutComp = nullptr) const;
	float RepairEtaFor(const FAstraDamage& D) const;
	/** A test hook: a person's schedule at an hour (their act and block), ignoring the ship's state. */
	EAstraLifeAct ScheduleAt(int32 Person, double ShipSec, int32* OutBlock = nullptr) const;

	// ------------------------------------------------------------------------------------------------ memory
	void Remember(int32 Person, uint8 Weight, const FString& Text);
	/** Something happened in or near a room: all who were within RadiusCm of it remember. */
	void RememberNear(int32 CompIdx, float RadiusCm, uint8 Weight, const FString& Text, int32 Except = INDEX_NONE);
	FString MemoryLine(const FAstraLifeMemory& M) const;

	/** The routes that failed (for the tests): who, from where to where. */
	const TArray<FString>& FailLog() const { return Fails; }
	FAstraLifeStats Counters;

private:
	TSharedPtr<const FAstraLifeMap> Map;
	FRouter Router;
	TArray<FAstraLifePerson> People;
	TArray<int32> RosterToPerson;
	TArray<int16> Occ;                       // per place: who is counted there
	TArray<int32> Holder;                    // per place: the last person counted there
	TArray<FAstraLifeParty> PartyList;
	TArray<int32> Queue;                     // people waiting for a route
	TArray<uint8> Queued;
	TArray<FString> Fails;
	TSet<int32> KnownIncidents;
	TMap<int32, FBox> SectionBoxes;
	TMap<FName, int32> ExternalPlace;        // a pre-placed actor's station id -> its place
	TArray<TArray<int32>> LeisureRooms;      // per way of spending free time: the rooms that serve it
	int32 Seed = 1;
	double Clock = 0.0;                      // ship seconds
	double GameT = 0.0;                      // game seconds
	uint8 AlertLevel = 0;
	int32 AlertSerial = 0;
	int32 RosterRev = -1;
	int32 Cursor = 0;
	float SliceAcc = 0.f;
	FVector FocusPos = FVector::ZeroVector;
	int32 MedbayComp = INDEX_NONE;
	int32 MessComp = INDEX_NONE;

	// --- init
	void AssignWatches(const FAstraCrewRoster& Roster, FRandomStream& R);
	void AssignHomes();
	void AssignPosts();
	void AssignBattle();
	bool RoomMatches(const FAstraLifeComp& C, const FAstraLifeSelector& S) const;
	int32 PostIn(int32 Comp, int32 Watch, TArray<uint8>* Used, FRandomStream& R) const;
	void RoomsOf(const FAstraLifeSelector& Sel, TArray<int32>& Out) const;

	// --- the day
	struct FDesire { EAstraLifeAct Act; int32 Episode; };
	FDesire Decide(const FAstraLifePerson& P) const;
	void BlockAt(const FAstraLifePerson& P, double Sec, EAstraLifeAct& Act, int32& Block, int32& Cycle) const;
	void Begin(int32 Idx, const FDesire& D, bool bTeleport);
	void Settle(int32 Idx);
	void StepPerson(int32 Idx);
	void Enqueue(int32 Idx);
	bool RouteOne();
	void Release(FAstraLifePerson& P, int32 Idx);
	bool Claim(FAstraLifePerson& P, int32 Idx, int32 PlaceIdx);
	FVector SpotAt(int32 PlaceIdx, int32 Slot, float& OutYaw) const;

	// --- choosing the spot
	void TargetPlace(FAstraLifePerson& P, int32 Idx, int32 PlaceIdx);
	void TargetBunk(FAstraLifePerson& P, int32 Idx, FRandomStream& R);
	void TargetMeal(FAstraLifePerson& P, int32 Idx, FRandomStream& R);
	void TargetLeisure(FAstraLifePerson& P, int32 Idx, FRandomStream& R);
	int32 FreePlaceIn(int32 Comp, const TFunction<bool(const FAstraLifePlace&)>& Want, FRandomStream& R) const;

	// --- the ship's word
	int32 PartyIndex(int32 IncidentId) const;
	void FormParty(const FAstraDamage& D);
	void EndParty(int32 PartyIdx, bool bRepaired);
	int32 PickSite(int32 Deck, TCHAR Section, int32 IncidentId) const;
	/** Who would go to a site, the nearest first: the damage-control ratings who are fit (a sleeper is roused), engineering if they are too few.
	 *  Key: a cost (cm), value: the person; EtaS: their own time to get there. */
	struct FGoer { double Cost; int32 Person; float EtaS; };
	void Goers(int32 Deck, const FVector& Site, TArray<FGoer>& Out) const;
	int32 DeckOfZ(double Z) const;
	const FBox& SectionBox(int32 Deck, TCHAR Section);

	uint32 Hash(int32 A, int32 B = 0, int32 C = 0) const;
	FRandomStream Stream(int32 A, int32 B = 0, int32 C = 0) const { return FRandomStream((int32)Hash(A, B, C)); }
};
