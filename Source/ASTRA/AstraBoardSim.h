// ASTRA — ABBORDAGGI: the fight inside a ship, as code (docs/ABBORDAGGI.md, docs/brief/ABBORDAGGI-2.md).
//
// A boarding party comes through a breach and goes for an objective; the ship's own people meet it. In F5.1 the party is the Kharon Mandate's and the ship the Aquila; in F5.2 it
// goes both ways: the Mandate boards the Aquila (or her consorts) and the Aquila's marines board a Mandate ship. The sides stay the factions (Aquila: the marines and the Captain;
// Mandate: the Mandate's soldiers); who attacks and who holds is the mission's (FMission::Attacker), and the squad drill is by that role. Both sides are squads of
// men on the ship's plan (AstraBoardMap.*): they move through doors and along corridors, see each other only where the line of sight is open, take
// the corners beside the doorways, step out to shoot and back in to reload, are suppressed by the fire that misses them, flank a position the
// enemy covers by a way he does not, and break off when the cost is more than they will pay. The Captain is one more man on it (his position and
// his state come from the game, his bullets from his hand); the people the game shows near him are these men's bodies.
//
// It is the simulation's own truth (the bodies, the tracers and the wounds in the game follow it; nobody is hit twice, once in the world and once
// here), plain code over the plan (no actors, no world), deterministic from a seed, and testable headless on the real ship
// (AstraBoardSimCommandlet: who wins, at what cost, how long). The judgment about what the marines are told to do is the Captain's and the squad
// leader's (the mind); the code is the squad drill: the corners, the bounds, the reloads, the aim.

#pragma once

#include "CoreMinimal.h"
#include "AstraBoardMap.h"

namespace AstraBoard
{
	enum class ESide : uint8 { Aquila = 0, Mandate = 1 };
	enum class ERole : uint8 { Rifleman, Leader, Heavy, Captain };
	enum class EAct : uint8 { Idle, Move, Cover, Peek, Reload, Down, Dead, Gone, Waiting };   // Gone: off the ship (retreated or carried out); Waiting: not in yet
	/** What a squad is doing: the drill the code runs (the mind's orders to the marines are these). */
	enum class ETask : uint8
	{
		Idle,        // no plan: respond to what is seen
		Advance,     // go to a place (a compartment, a point) along the best way, in a column, covering each other
		Hold,        // hold the ground round a place: fighting positions that cover the way in
		Assault,     // go for the nearest known enemy, firing as they move
		FallBack,    // withdraw to a place by bounds
		Follow,      // stay with the Captain
		Rescue,      // reach the Captain who is down and carry him out
		Withdraw,    // leave the ship by the breach
		// the infantry orders (AstraBoardDrills.cpp, docs/ABBORDAGGI.md §15.2): a squad runs a drill with phases of its own
		Sweep,       // clear the rooms of a place one after the other: stack at each door, go in together, clear, report, the next
		Breach,      // open a door (a sealed bulkhead is charged) and go in through it: stack, charge, entry, clear, then hold what is taken
		Take,        // take a room and hold it: stack at its door (several squads on a sync: each at its own door, in together), entry, clear, hold from inside
		Ambush,      // hidden in the corners of a place with the fire held: it is opened all together when the enemy is in the killing ground, or when the squad is found
		Escort       // with the Captain in formation: a man ahead who looks past every opening, two at the sides, one behind
	};
	/** Where a squad is in the drill of one of the infantry orders. */
	enum class EDrill : uint8
	{
		None,        // no drill (the older tasks)
		Approach,    // on its way to the door it will go in by
		Stack,       // stacked at the door, the door held shut, waiting for all of them (and for the squads of its sync)
		Charge,      // a sealed bulkhead: the charge is set, the others wait clear of it
		Entry,       // through the door a man a moment apart, each to his corner of the room
		Clear,       // in the room: looking for what is in it, holding until it is clear
		Hold,        // the place is theirs: held from inside
		Spring,      // (ambush) hidden, fire held, waiting for the enemy to be where the squad wants him
		Done         // the order is carried out: the squad holds where it is
	};
	const TCHAR* TaskName(ETask T);
	const TCHAR* DrillName(EDrill D);
	const TCHAR* ActName(EAct A);

	/** The weapons the fight knows (the player's own are in AstraWeapon.*; these are what a soldier's rifle does in the squad's reckoning). */
	struct FWeapon
	{
		FName Id;
		float Rps = 9.f;             // rounds per second in a burst
		int32 Mag = 30;
		float ReloadS = 2.2f;
		float Damage = 17.f;         // a hit's damage to an unarmoured man (hit points of 100)
		float Suppress = 1.f;        // how much a round that passes near a man frightens him
		int32 Burst = 4;             // rounds in a burst
		float RangeCm = 3500.f;
	};

	/** What the fight is tuned by (every number a bench can move). */
	struct FTuning
	{
		float MarineSkill = 0.86f, MandateSkill = 0.78f, LeaderSkill = 0.92f;
		float MarineArmor = 0.72f, MandateArmor = 0.80f;        // the share of a hit that goes through
		float AcquireMinS = 0.28f, AcquireMaxS = 0.7f;          // seeing a man and having a gun on him
		float HideMinS = 0.45f, HideMaxS = 1.25f;               // behind the corner between two looks
		float PeekS = 0.85f;                                    // a look's length at most (a burst ends it)
		float JogCmS = 330.f, WalkCmS = 175.f, CoverCmS = 210.f;
		float SuppressDecay = 0.30f, SuppressPerRound = 0.035f, SuppressMiss = 130.f;   // a round within this many cm of a man frightens him
		float CoverFactor = 0.55f;                              // a hit chance behind a corner's edge, against one in the open
		float MoveFactor = 0.62f;                               // a man in motion against one who stands
		float RangeFullCm = 450.f, RangeFarCm = 2000.f, RangeMaxCm = 3800.f;
		float DownBleedMinS = 70.f, DownBleedMaxS = 130.f;      // how long a man who is down lasts without help
		float MandateRetreatLoss = 0.55f;                       // the share of a squad lost at which the Mandate breaks off
		float MarineRetreatLoss = 1.1f;                         // and the marines (never on their own: they break off when they are told to)
		float HoldS = 70.f;                                     // how long the objective must be held to be taken
		float HearCm = 2600.f;                                  // a shot is heard this far (through the open ways)
		float SensorDelayS = 2.0f;                              // the ship's internal sensors: how stale the marines' picture of the corridors is
		float CutS = 22.f;                                      // how long the Mandate need to cut through a sealed bulkhead
		float PushS = 40.f;                                     // how long the Mandate sit in contact without getting nearer before they press the attack
		bool bShipSensors = true;                               // the holders' ship has its internal sensors (the Aquila's: a few seconds stale picture of the corridors); a dead hulk has none
		bool bEvacuate = false;                                 // the attackers' wounded are carried out to their boats by their own men (a boarding by boats: nobody is left to bleed where he fell while the way is clear)
		float EvacPickupS = 2.5f;                               // seconds to get a man up and on his bearer's shoulders
		float EvacCmS = 115.f;                                  // the pace of a man who carries one
		float EvacReachCm = 2400.f;                             // how far from the casualty a man may be called to carry him
		float EvacClearCm = 1500.f;                             // nobody comes for a casualty while an enemy who can see him is this near (the fight comes first)
		float EvacBleedBonusS = 45.f;                           // first aid on the spot: the seconds it gives a man who is down
		float LethalScale[2] = {0.75f, 1.f};                    // by side (Aquila, Mandate): how much of a beaten man's chance of dying outright is his (1: the base rule; a marine's armour and field surgery make it less)
		bool bFlank = true;                                     // squads go round (the bench turns it off to see what it is worth)
		bool bCover = true;                                     // men look for corners (the bench turns it off for the duels in the open)
		// ---- the infantry orders (AstraBoardDrills.cpp): what each is worth is what these say, and the bench moves them
		float StartleS = 1.3f;                                  // a man who is not alerted sees an enemy come through a door he was not covering: he is this long getting over it ...
		float StartleMul = 1.9f;                                // ... and his time to get a gun on him is this much longer
		float EntryS = 2.5f;                                    // a man who comes through a door in a drill is quick on his first targets for this long ...
		float EntryMul = 0.55f;                                 // ... his time to lay a gun on one is this much shorter ...
		float EntryHit = 1.1f;                                  // ... and his rounds a little better (it is what he is trained for)
		float FunnelBonus = 1.25f;                              // a man holding a corner on a door, alerted, against the one who comes through it: a doorway is a fatal funnel
		float HiddenSeeCm = 450.f;                              // a man hidden in a corner is seen only from this near
		float StackReadyCm = 170.f;                             // stacked: within this of his place at the door
		float StackMaxWaitS = 30.f;                             // a squad waits this long for the last of its men
		float SyncMaxWaitS = 45.f;                              // and this long, from the first of its squads stacked, for the others of its sync
		float EntryGapS = 0.7f;                                 // the next man goes through this long after the one before
		float ClearHoldS = 4.f;                                 // a room is clear when nothing has been seen in it for this long with the men at their corners
		float BreachChargeS = 9.f;                              // a charge on a sealed bulkhead (the torches of the Mandate take CutS)
		float BreachStunS = 1.6f;                               // what it does to the men near the door on the other side: they are stunned this long
		float BreachNoiseCm = 2600.f;                           // and who hears it (alerted: no surprise on them)
		float AmbushMaxS = 180.f;                               // an ambush held this long with nobody coming is given up (the squad holds the place)
		float AmbushFirstS = 2.5f;                              // the first volley of a sprung ambush: for this long ...
		float AmbushFirstHit = 1.3f;                            // ... its rounds are this much better (the men were laid on their targets) and the enemy is startled
		float AmbushKillCm = 1100.f;                            // the killing ground: an enemy this near the squad's place and in sight of half of it (the full range of a rifle is 4.5 m, a third of the hits at 20)
		float AmbushStartleS = 2.2f;                            // the enemy caught in it is startled this long
		float SealS = 4.f;                                      // the last man at a bulkhead's console: how long it takes to close it (and for his side to open it again)
		float OverrideS = 10.f;                                 // the ship's own people, at a door the enemy shut behind him: how long they take to override it (the attackers cut it: CutS)
		float SealClearCm = 250.f;                              // and nobody (friend or enemy) may be in the doorway
		float EscortPointCm = 560.f;                            // the man ahead of the Captain
	};

	struct FSeen
	{
		int32 Unit = INDEX_NONE;
		FVector Pos = FVector::ZeroVector;
		float AgeS = 0.f;
		bool bVisibleNow = false;
	};

	struct FUnit
	{
		int32 Id = INDEX_NONE;
		ESide Side = ESide::Aquila;
		ERole Role = ERole::Rifleman;
		FString Name;
		int32 Roster = INDEX_NONE;       // an Aquila marine of the ship's roster (VITA): INDEX_NONE for the rest
		int32 Person = INDEX_NONE;       // a person of a boarded ship's crew in the war's books (FLOTTA-VIVA: FFleetSnapshot::FHand::Person), so that what the fight does to him is written back
		int32 Squad = INDEX_NONE;
		int32 Party = INDEX_NONE;        // the craft he came in (the host's number for it): what happens to the craft happens to him until he is through
		bool bExternal = false;          // the Captain: the game moves him
		// body
		FVector Pos = FVector::ZeroVector;
		float Yaw = 0.f;                 // degrees, the way he faces
		int32 Comp = INDEX_NONE;
		float Hp = 100.f;
		float Armor = 1.f;               // the share of a hit that goes through
		float Skill = 0.8f;
		float Speed = 0.f;               // cm/s now (0 while he waits at a shut bulkhead or stands to shoot)
		float Cruise = 0.f;              // the pace of the way he is on (he goes at it again when nothing holds him)
		bool bSprint = false;
		bool bLow = false;               // crouched or prone (a harder target)
		EAct Act = EAct::Idle;
		float Bleed = 0.f;               // seconds he has left when he is down
		int32 Bearer = INDEX_NONE;       // down: the man called to carry him out
		int32 CarriedBy = INDEX_NONE;    // down: the man who has him on his shoulders now (he does not bleed, and his body is not seen on the floor)
		int32 Carrying = INDEX_NONE;     // the man he has been called to carry out, or carries (he does not fight meanwhile)
		float CarryT = 0.f;              // seconds spent getting the casualty up
		// weapon
		FWeapon Weapon;
		int32 Rounds = 30;
		int32 Reserve = 120;
		float ReloadT = 0.f;
		float FireT = 0.f;               // until the next burst may begin
		int32 BurstLeft = 0;
		float RoundT = 0.f;
		// what he knows and does
		int32 Target = INDEX_NONE;
		float AcquireT = 0.f;
		float Suppression = 0.f;         // 0..1
		float Morale = 1.f;
		TArray<FSeen, TInlineAllocator<8>> Seen;
		float PercT = 0.f;               // since he last looked about (a man looks four times a second, each at his own beat)
		// moving and fighting
		TArray<FVector> Path;
		int32 PathI = 0;
		FVector Dest = FVector::ZeroVector;      // where the path ends
		int32 Slot = INDEX_NONE;                 // the corner he fights from
		float CycleT = 0.f;                      // until he steps out / back
		bool bAtPeek = false;
		float Lane = 0.f;                        // his place across a corridor (cm from the middle)
		float StairT = 0.f;
		float CoverT = 0.f;                      // no new search for a corner until then
		// the infantry orders (AstraBoardDrills.cpp)
		bool bHidden = false;                    // in a corner with his fire held: he is seen only from close
		int32 HoldDoor = INDEX_NONE;             // stacked at this door (the damage map's index): he does not open it, nor cut it
		int32 WaitDoor = INDEX_NONE;             // waiting at this shut door (his way goes through it)
		bool bBusy = false;                      // at a work of his own (the console of a bulkhead): the squad's drill does not move him
		bool bMoveFire = false;                  // he goes on with his squad's move while he shoots (a bodyguard with the Captain on the move), firing on the move (a worse shot)
		float EntryT = 0.f;                      // seconds left of the quick first targets of a man who came through a door in a drill
		float StartleT = 0.f;                    // seconds left of being startled (not alerted, an enemy come out of a door he was not covering)
		float AlertT = 999.f;                    // seconds since he heard a shot, saw an enemy or was hit: the ones who are not alerted are surprised
		float GoAt = 0.f;                        // (entry) the time he goes through the door
		int32 StackIdx = INDEX_NONE;             // his place in the stack
		FVector DrillSpot = FVector::ZeroVector; // where he stacks, or the spot of the room he goes to when it is not a corner
		// the story
		float Time0 = 0.f;
		int32 Kills = 0;
		int32 HitsTaken = 0;
		FString FellTo;                          // what put him down
		bool Able() const { return Act != EAct::Dead && Act != EAct::Gone && Act != EAct::Down && Act != EAct::Waiting; }
		FVector Eye() const { return Pos + FVector(0.0, 0.0, bLow ? 105.0 : 152.0); }
	};

	struct FSquad
	{
		int32 Id = INDEX_NONE;
		ESide Side = ESide::Aquila;
		FString Name;
		TArray<int32> Members;           // unit ids
		int32 Leader = INDEX_NONE;
		ETask Task = ETask::Idle;
		int32 TargetComp = INDEX_NONE;   // Advance, Hold, FallBack: the place
		FVector TargetPos = FVector::ZeroVector;
		float Radius = 0.f;              // Hold: how far round the place
		float TaskT = 0.f;               // since the task began
		float PlanT = 0.f;               // since the leader last thought
		bool bContact = false;
		float ContactT = 0.f;
		int32 Flankers[2] = {INDEX_NONE, INDEX_NONE};
		FVector FlankAt = FVector::ZeroVector;
		TArray<FVector> Trail;           // where the leader has been (the column follows it)
		float FlankT = 0.f;
		float BestDist = 1.0e9f;         // the Mandate's way in: the nearest the leader has got to the objective (cm)
		float StallT = 0.f;              // how long the squad has been in contact without getting any nearer (they press the attack after PushS)
		bool bQuickReaction = false;     // the reaction team: arms itself before it goes
		float MusterT = 0.f;
		float StartStrength = 0.f;
		int32 Lost = 0;
		bool bOrdered = false;           // an order of the Captain's or the marines' commander's stands (the squad does not re-plan its place)
		int32 BreachComp = INDEX_NONE;   // the hatch an attack squad came in by (INDEX_NONE: the mission's): a boarding by several craft has several
		FVector BreachPos = FVector::ZeroVector;
		bool bStand = false;             // stand fast where they are and shoot (no corners, no moves: the bench's duels)
		FString Note;                    // what it was last told or decided, for the reports
		// ---- the infantry orders (AstraBoardDrills.cpp)
		EDrill Drill = EDrill::None;
		float DrillT = 0.f;              // seconds in this phase
		int32 StackPortal = INDEX_NONE;  // the opening the squad stacks at and goes through
		int32 StackComp = INDEX_NONE;    // the compartment it stacks in (the side the room is not on)
		int32 RoomTo = INDEX_NONE;       // the room it goes in to (clear, take)
		TArray<int32> Queue;             // sweep: the rooms still to clear (the first is next)
		TArray<int32> Cleared;           // the rooms it has cleared, in order
		TArray<int32> Sector;            // sweep: the compartments of the place
		int32 Sync = 0;                  // squads of one sync (a non-zero number) go through their doors together
		int32 CoverComp = INDEX_NONE;    // the place the squad covers with its fire while another squad goes in
		int32 Door = INDEX_NONE;         // the door the order names (breach), the damage map's index
		bool bFireHeld = false;          // fire discipline: nobody fires until the squad is found or the order is given (an ambush)
		bool bHoldInside = false;        // (hold) the corners of the room itself, none of the corridors outside its doors
		bool bSealBehind = false;        // a pressure door is closed behind the squad when it has gone through
		float StackedAt = -1.f;          // the sim's clock when the squad first stacked (the sync's wait counts from it)
		float SprungAt = -1.f;           // (ambush) when it was sprung
		float FirstVolleyT = 0.f;        // seconds left of the first volley's advantage
		bool bSpotted = false;           // (ambush) a man of the squad was seen, shot at or heard
		int32 SealPortal = INDEX_NONE;   // the pressure door being closed behind the squad
		int32 SealMan = INDEX_NONE;      // and the man at its console
		float SealT = 0.f;
		TArray<int32> SealPassed;        // the men who have gone through it
		TArray<FVector> StackSpots;      // where each man of the stack stands (by his place in it)
		float ClearT = 0.f;              // seconds with nothing seen in the room (it is clear at ClearHoldS)
		float SyncGoAt = -1.f;           // the clock when the squads of a sync go in together
		bool bStackReady = false;        // every man is at his place in the stack
		bool bCharged = false;           // the sealed bulkhead has been opened by the charge
		float EntryAt = -1.f;            // when the first man went through
		FVector2D EscortDir = FVector2D(1.0, 0.0);   // the way the Captain is going (escort)
		FVector EscortLast = FVector::ZeroVector;
		float EscortStillT = 0.f;
		int32 SweptHostiles = 0;         // (sweep) the enemy put down in the rooms it cleared
		FString Where;                   // the place the order names, in words (the picture's)
	};

	enum class EEvent : uint8
	{
		Shot,        // Unit fired at Target: End is where the round went (or hit), bHit
		Hit,         // Unit was hit (Dmg): End is where on him
		Down,        // Unit is down
		Died,        // Unit died
		Retreat,     // Unit's squad is breaking off
		Exit,        // Unit left the ship (the Mandate's retreat)
		Contact,     // Unit saw an enemy for the first time
		Rescue,      // the Captain was reached and carried out
		Reload,
		Spawn,       // Unit came into the fight
		Order,       // a squad's task changed
		Outcome,
		Cut,         // the Mandate cut through a sealed bulkhead: Target is the door (the damage map's index), Start where it is
		Carried,     // Unit, who was down, has been carried out to the boats by Target: he is alive and off the ship
		Drill,       // a squad's drill moved on (stacked, going in, cleared a room, sprung an ambush, swept a place...): Text says it, Unit is the squad's leader, Target the squad
		Sealed       // a squad closed a pressure door behind it: Target is the door (the damage map's index), Start where it is
	};
	struct FBoardEvent
	{
		EEvent Type = EEvent::Shot;
		float T = 0.f;
		int32 Unit = INDEX_NONE;
		int32 Target = INDEX_NONE;
		FVector Start = FVector::ZeroVector;
		FVector End = FVector::ZeroVector;
		float Dmg = 0.f;
		bool bHit = false;
		bool bHead = false;
		FString Text;
	};

	/** How a boarding ended, by role: the defenders held (every attacker was put down or got off the ship), the attackers took the objective, the attackers broke off and left, or the time ran out. */
	enum class EOutcome : uint8 { Running, DefenderHolds, AttackerTakes, AttackerRepelled, TimedOut };

	struct FMission
	{
		ESide Attacker = ESide::Mandate; // the side that came aboard (the other holds the ship)
		int32 Objective = INDEX_NONE;    // the compartment the attackers want
		int32 Breach = INDEX_NONE;       // the compartment they came in by
		FVector BreachPos = FVector::ZeroVector;
		bool bSweep = false;             // the attackers also win when no defender is left on his feet (a derelict: nothing to hold but the ship)
		float HeldS = 0.f;
		double StartedS = -1.0;          // the clock when the first attacker came aboard (the time limits count from it: a craft's flight is not the fight's time)
		EOutcome Outcome = EOutcome::Running;
	};

	/** One man who comes aboard from a craft: a name (the Mandate's are made when it is empty), the roster place of one of the Aquila's marines (VITA's), the skill that is his own (0: his side's). */
	struct FArrival
	{
		FString Name;
		int32 Roster = INDEX_NONE;
		float Skill = 0.f;
	};

	/** An order to a squad with everything it says (the marines' `marine_order`): the task, the place, and what goes with it. */
	struct FOrder
	{
		ETask Task = ETask::Hold;
		int32 Comp = INDEX_NONE;          // the place (a room or a corridor)
		FVector Pos = FVector::ZeroVector;
		float Radius = 0.f;               // hold: how far round the place
		int32 Door = INDEX_NONE;          // breach: the door the order names (the damage map's index)
		TArray<int32> Sector;             // sweep: the compartments of the place when it is a deck's section or a radius round a spot
		int32 CoverComp = INDEX_NONE;     // the place the squad covers with its fire
		bool bFireHeld = false;           // nobody fires until the squad is found or the order is given
		bool bInside = false;             // (hold) the corners of the room itself
		bool bSealBehind = false;         // close the pressure doors behind the squad
		int32 Sync = 0;                   // squads of one non-zero number go through their doors together
		FString Where;                    // the place in words, for the reports
		FString Note;
	};

	struct FBook
	{
		int32 Shots = 0, Hits = 0, Misses = 0;
		int32 Killed[2] = {0, 0}, Down[2] = {0, 0}, Exited[2] = {0, 0}, Spawned[2] = {0, 0}, Carried[2] = {0, 0};   // Down: who is down now
		int32 Contacts = 0, Flanks = 0, Retreats = 0, Reloads = 0, Suppressed = 0, Rescues = 0;
		int32 DrillEntries = 0, DrillRooms = 0, DrillAmbushes = 0, DrillSeals = 0, DrillCharges = 0;     // the infantry orders: doors gone through in a drill, rooms cleared, ambushes sprung, doors closed behind a squad, bulkheads charged
		double FirstContactT = -1.0, FirstBloodT = -1.0, EndT = -1.0;
		int32 CaptainHits = 0;
		float MarineRoundsFired = 0.f;
		// the cost, in milliseconds, of the step's parts (what each took in total and in its worst step): sensing, the squads' plans, the men's moves and shots
		double Ms[3] = {0.0, 0.0, 0.0}, MsWorst[3] = {0.0, 0.0, 0.0};
	};
}

class ASTRA_API FAstraBoardSim
{
public:
	using FUnit = AstraBoard::FUnit;
	using FSquad = AstraBoard::FSquad;

	void Init(TSharedRef<const FAstraBoardMap> InMap, int32 Seed);
	bool IsReady() const { return Map.IsValid(); }
	const FAstraBoardMap& GetMap() const { return *Map; }
	AstraBoard::FTuning Tuning;

	// ------------------------------------------------------------------------------------------------ the people
	/** The boarding party: Count men of the Mandate come in at the breach (a compartment of the hull's wall) and go for the objective. They come in a few
	 *  at a time. Returns the squads' ids. (The Mandate attacks: SetAttacker(ESide::Mandate), the default.) */
	TArray<int32> SpawnBoarders(int32 BreachComp, const FVector& BreachPos, int32 ObjectiveComp, int32 Count, float FirstAtS = 0.f);
	/** The same for either side: the attackers (Side) come in at the breach in squads of PerSquad, a few at a time, and go for the objective. Marines of the bench are named
	 *  "Marine n" (the game's own are made with AddMarine from the roster and briefed with BriefAttackers). Sets the mission's attacker. */
	TArray<int32> SpawnAttackers(AstraBoard::ESide Side, int32 BreachComp, const FVector& BreachPos, int32 ObjectiveComp, int32 Count, float FirstAtS = 0.f, int32 PerSquad = 5);
	/** Sets the mission: who attacks, where they came in, what they want. */
	void SetMission(AstraBoard::ESide Attacker, int32 BreachComp, const FVector& BreachPos, int32 ObjectiveComp, bool bSweep = false);
	/** The men of one craft (Party: the host's number for it) wait to come in at a hatch (BreachComp, BreachPos): they are made now, not yet in the fight, in squads of PerSquad (named
	 *  SquadBase and the next letter of the alphabet: "Ferry Guard Alpha"), and cut in when the party is released (the craft has latched) or, if that is never told, EtaS seconds from now (what the
	 *  holders' ambush reckons against). The mission is SetMission's. Returns the squads' ids. The first man of a squad leads it. */
	TArray<int32> LandParty(AstraBoard::ESide Side, int32 Party, const TArray<AstraBoard::FArrival>& Men, int32 BreachComp, const FVector& BreachPos, float EtaS, int32 PerSquad = 5, const FString& SquadBase = FString());
	/** The craft has cut in: the party's men come aboard, a few at a time, DelayS from now. */
	void ReleaseParty(int32 Party, float DelayS = 0.f);
	/** The craft was shot down with them in it: they die with it (Cause: how, for the story). Men who have already come aboard are not touched. How many died. */
	int32 LoseParty(int32 Party, const FString& Cause);
	/** The craft turned back with them in it: they never came aboard (nobody died). How many. */
	int32 RecallParty(int32 Party);
	/** The men of a party still in their craft (not yet through the breach). */
	int32 PartyWaiting(int32 Party) const;
	/** Where a squad came in: its own hatch, else the mission's. */
	FVector BreachPosOf(const AstraBoard::FSquad& S) const { return S.BreachComp != INDEX_NONE ? S.BreachPos : Mis.BreachPos; }
	int32 BreachCompOf(const AstraBoard::FSquad& S) const { return S.BreachComp != INDEX_NONE ? S.BreachComp : Mis.Breach; }
	/** An attack squad's standing order: go to the objective and take it. */
	void BriefAttackers(int32 SquadId);
	AstraBoard::ESide Attacker() const { return Mis.Attacker; }
	AstraBoard::ESide Defender() const { return Mis.Attacker == AstraBoard::ESide::Mandate ? AstraBoard::ESide::Aquila : AstraBoard::ESide::Mandate; }
	bool IsAttacker(AstraBoard::ESide S) const { return S == Mis.Attacker; }
	/** A marine of the Aquila, at a place: Roster is VITA's roster index (INDEX_NONE: a man of the bench). */
	int32 AddMarine(const FString& Name, int32 Roster, const FVector& Pos, bool bLeader, int32 SquadId, float Skill = 0.f);
	/** Any man of either side (the bench's duels, a scenario's hand-made squads). */
	int32 AddUnit(AstraBoard::ESide Side, AstraBoard::ERole Role, const FString& Name, const FVector& Pos, int32 SquadId);
	int32 AddSquad(AstraBoard::ESide Side, const FString& Name);
	/** A man of the ship's own who was hurt before the fight began (a ship the war has shot up): he lies where he is, alive, and is counted among the wounded; he does not bleed out within the fight (his own medics have him). */
	int32 AddWounded(AstraBoard::ESide Side, const FString& Name, const FVector& Pos);
	/** A unit that is not in the fight yet: it joins where it stands Seconds from now (a marine roused from his bunk who has to dress and arm). */
	void DelayUnit(int32 UnitId, float Seconds);
	/** A squad by its name ("Watch 1", "Reaction 2", "Ferry Guard Alpha"), exactly as the fight names it (INDEX_NONE when there is none). */
	int32 FindSquad(const FString& Name) const;
	/** The Captain joins the fight as a man the game moves. */
	int32 AddCaptain(const FVector& Pos);
	/** A name for a man a scene or the bench makes (the Mandate's: a first and a last name of the Kharon; ASTRA's: Marine and a number). */
	FString MakeName(AstraBoard::ESide Side, int32 N) { return Side == AstraBoard::ESide::Mandate ? MandateName(N) : FString::Printf(TEXT("Marine %d"), N); }
	void SetCaptain(const FVector& Pos, float Yaw, bool bLow, float Speed, bool bDown);
	int32 CaptainId() const { return CaptainUnit; }

	// ------------------------------------------------------------------------------------------------ orders (the squad drill the mind's words come to)
	void Order(int32 SquadId, AstraBoard::ETask Task, int32 Comp, const FVector& Pos, float Radius = 0.f, const FString& Note = FString());
	/** An order with everything it says: the task and the place, and what goes with them (fire held, the doors closed behind the squad, the place it covers, the sync it goes in with). The infantry orders
	 *  (sweep, breach, take, ambush, hold the line, escort) are carried out by their drills (AstraBoardDrills.cpp). */
	void OrderEx(int32 SquadId, const AstraBoard::FOrder& O);
	void Respond(int32 SquadId);              // no order: the squad goes to meet what is coming
	/** The squad's drill in words, for the picture and the reports ("stacked at deck 7 section D (Capacitor Hall), waiting for Bravo"); empty when it has none. */
	FString DrillText(const FSquad& S) const;
	void SealDoor(int32 Door, bool bSealed);
	bool IsDoorSealed(int32 Door) const { return Doors.IsSealed(Door); }
	const FBoardDoors& DoorState() const { return Doors; }

	// ------------------------------------------------------------------------------------------------ stepping
	/** Advances by Dt seconds (it steps itself at 10 Hz). */
	void Tick(float Dt);
	double Time() const { return Clock; }

	/** The Captain's hand: a round of his hit this unit (Dmg points, at a place on the body). */
	void HitUnit(int32 UnitId, float Dmg, bool bHead, const FString& By = FString());
	/** The Captain fired: the boarders who are near and have a way to the sound know where it came from, roughly. */
	void CaptainFired();
	/** An outside hand wounds, kills or heals (a rescue, the Medbay): a unit that is down is taken out of the fight alive. */
	void CarryOut(int32 UnitId);
	/** An outside hand takes a man off her decks, whole (the transporter): he is alive and gone, counted among those who got away (a man who is down is carried out as CarryOut does). Whoever carried him, or
	 *  was to carry him, is free. */
	void LeaveShip(int32 UnitId);

	// ------------------------------------------------------------------------------------------------ asking
	const TArray<FUnit>& Units() const { return People; }
	const FUnit* Unit(int32 Id) const { return People.IsValidIndex(Id) ? &People[Id] : nullptr; }
	FUnit* UnitMutable(int32 Id) { return People.IsValidIndex(Id) ? &People[Id] : nullptr; }
	const TArray<FSquad>& Squads() const { return Teams; }
	const FSquad* Squad(int32 Id) const { return Teams.IsValidIndex(Id) ? &Teams[Id] : nullptr; }
	FSquad* SquadMutable(int32 Id) { return Teams.IsValidIndex(Id) ? &Teams[Id] : nullptr; }
	const AstraBoard::FMission& Mission() const { return Mis; }
	AstraBoard::FMission& MissionMutable() { return Mis; }
	const AstraBoard::FBook& Book() const { return Stats; }
	/** The events since the last time they were taken (the game's effects and reports read them). */
	void TakeEvents(TArray<AstraBoard::FBoardEvent>& Out) { Out = MoveTemp(Events); Events.Reset(); }
	bool Over() const { return Mis.Outcome != AstraBoard::EOutcome::Running; }
	int32 CountAble(AstraBoard::ESide S) const;
	int32 CountDown(AstraBoard::ESide S) const;
	/** What a side knows of the enemy's men (the holders' ship's internal sensors in the corridors, when it has them, and what its own men have seen): unit ids and where they were
	 *  last seen (cm). */
	void Intel(AstraBoard::ESide Side, TArray<AstraBoard::FSeen>& Out) const;
	/** How strong a squad is (able men / men it began with). */
	float Strength(const FSquad& S) const;
	FString DescribeSquad(const FSquad& S) const;
	/** Where a unit is, in words. */
	FString WhereIs(const FUnit& U) const { return Map->Describe(U.Comp); }
	/** The route a squad of the Mandate takes from its breach to its objective (cm), for the displays and the chokepoints. */
	bool PlannedRoute(TArray<FVector>& Out) const;
	/** Where the marines should meet the boarders: the first opening along the Mandate's way, counting from the breach, where as many marines as there are boarders
	 *  can be with time to spare before the boarders arrive (the sealed bulkheads they must cut count), else the way into the objective. INDEX_NONE until there is a breach
	 *  and the first search has finished (a search takes a second or two: it goes on in slices of the step). */
	int32 AmbushPortal() const { return AmbushIdx; }
	/** The holders' default response, when nobody has given an order (the marines': in the Aquila; the Mandate's guard: in a ship of theirs): from the alarm they go (the watch at once,
	 *  the reaction team after it has armed) to the opening that wins the race against the boarders and take its corners (AmbushPortal). */
	struct FMarineCommand
	{
		bool bActive = false;                // the alarm has sounded
		float AlarmT = 0.f;                  // when
	};
	const FMarineCommand& MarineCommand() const { return Cmd; }
	/** The line of sight between two points as the fight sees it (the doors as they are). */
	bool Sees(const FVector& EyeA, const FVector& EyeB) const { return Map->Visible(EyeA, EyeB, &Doors); }
	/** The game may override sight for the Captain's own fights with a real trace (a locker is cover too). */
	TFunction<bool(const FVector&, const FVector&)> SightOverride;
	/** Summed up for a report line: "7 Mandate on Deck 7 section D". */
	FString HostileSummary() const;

private:
	TSharedPtr<const FAstraBoardMap> Map;
	FRandomStream Rng;
	TArray<FUnit> People;
	TArray<FSquad> Teams;
	FBoardDoors Doors;
	TArray<int32> OpenNow;                   // doors held open this step (to clear them next)
	TArray<float> CutT;                      // by door: how long the Mandate have been at work on it
	AstraBoard::FMission Mis;
	AstraBoard::FBook Stats;
	TArray<AstraBoard::FBoardEvent> Events;
	TArray<AstraBoard::FSeen> SensorPicture[2];
	double Clock = 0.0;
	double Acc = 0.0;
	int32 CaptainUnit = INDEX_NONE;
	bool bCaptainRescueTold = false;          // the marines' reaching the Captain has been told for this fall
	float SensorT = 0.f;
	TArray<FVector> BreachRoute;
	// boarders still to come in
	struct FPending { int32 Unit; float At; };
	TArray<FPending> Pending;
	float DoorT = 0.f;
	int32 AmbushIdx = INDEX_NONE;
	FMarineCommand Cmd;
	float CmdT = 0.f;
	float EvacT = 0.f;
	void StepMarineCommand(float Dt);
	double AmbushAge = -1.0e9;
	/** The search for the ambush opening, done in slices of a few routes a step (a long search in one go would be a hitch in the game). */
	struct FAmbushPass
	{
		struct FWing { FVector From = FVector::ZeroVector; int32 Men = 0; float Ready = 0.f; };
		struct FStop { int32 Portal = INDEX_NONE; float Theirs = 0.f; };
		bool bRunning = false;
		bool bKeepChecked = false;
		TArray<FWing> Wings;
		TArray<FStop> Stops;
		int32 Need = 6;
		int32 Cursor = 0;
	};
	FAmbushPass AmbPass;
	void StepAmbush();
	bool AmbushWins(const FAmbushPass::FStop& Stop, float Margin, int32& InOutRoutes) const;

	// --- the step
	void Step(float Dt);
	void StepDoors();
	void StepSenses(float Dt);
	void StepSensors(float Dt);
	void StepUnit(FUnit& U, float Dt);
	void StepSquad(FSquad& S, float Dt);
	void StepMission(float Dt);
	void StepEvacuation(float Dt);               // the wounded of the attackers: a free man is called, gets him up, carries him to the breach
	void StepCarry(FUnit& Bearer, float Dt);
	// --- the unit
	void Perceive(FUnit& U, float Dt);
	void Fight(FUnit& U, float Dt);
	void Move(FUnit& U, float Dt);
	void FireRounds(FUnit& U, float Dt);
	bool ChooseTarget(FUnit& U);
	bool TakeCover(FUnit& U, const FVector& Enemy);
	void GoTo(FUnit& U, const FVector& To, float Speed, bool bThroughSealed = false);
	void Face(FUnit& U, const FVector& At, float Dt);
	float HitChance(const FUnit& Shooter, const FUnit& Target, float DistCm) const;
	void Damage(FUnit& Target, float Dmg, bool bHead, int32 ByUnit, const FVector& At, const FString& By);
	void Kill(FUnit& U, int32 ByUnit, const FString& By);
	void Suppress(const FVector& From, const FVector& To, AstraBoard::ESide ShooterSide, float Amount, int32 Except);
	void Hear(const FUnit& Shooter);
	// --- the squad
	void Plan(FSquad& S);
	void PlanAttack(FSquad& S);                  // the attackers' own drill: to the objective, round the enemy, away when the cost is too high
	void PlanDefend(FSquad& S);                  // the holders' drill (and any squad that has an order): the ambush, the corners, the orders' tasks
	void WithdrawSquad(FSquad& S, const TArray<int32>& Able);
	void ColumnTo(FSquad& S, const FVector& To, float Speed);
	void HoldAround(FSquad& S, const FVector& At, float Radius, bool bInside = false);   // bInside: the corners of the room itself only (the attackers' objective)
	bool FlankFor(FSquad& S, const FVector& Enemy);
	// --- the infantry orders (AstraBoardDrills.cpp)
	void ResetDrill(FSquad& S);
	void StepDrill(FSquad& S, const TArray<int32>& Able);       // the order's own phases, from the squad's plan (twice a second)
	void DrillRoom(FSquad& S, const TArray<int32>& Able);       // breach, take, and every room of a sweep: approach, stack, (charge), entry, clear, hold
	void DrillSweepNext(FSquad& S);                             // the next room of a sweep, or its end
	void DrillAmbush(FSquad& S, const TArray<int32>& Able);
	void DrillEscort(FSquad& S, const TArray<int32>& Able);
	void StepSealBehind(FSquad& S, const TArray<int32>& Able);  // the last man closes a pressure door behind the squad
	bool FindEntry(FSquad& S, int32 Room, const FUnit& From);   // the door the squad goes in by and where it stacks
	void MakeStackSpots(FSquad& S, int32 Count);
	void PickEntryDests(FSquad& S, const TArray<int32>& Men, TArray<FVector>& OutSpots, TArray<int32>& OutSlots);
	void AlertAround(const FVector& At, float Cm, AstraBoard::ESide Alerter, float StunS);
	void Announce(const FSquad& S, const FString& Text);
	bool Held(const FUnit& U) const;                            // his squad has his fire held (an ambush)
	void Emit(AstraBoard::EEvent Type, int32 Unit, int32 Target = INDEX_NONE, const FVector& Start = FVector::ZeroVector, const FVector& End = FVector::ZeroVector,
	          float Dmg = 0.f, bool bHit = false, const FString& Text = FString());
	FUnit& Spawn(AstraBoard::ESide Side, AstraBoard::ERole Role, const FString& Name, const FVector& Pos, int32 SquadId);
	void ArmUnit(FUnit& U);
	bool Known(const FUnit& U, int32 Enemy, FVector& OutPos, float& OutAge) const;
	FString MandateName(int32 N);
	friend struct FAstraBoardSimTest;
};
