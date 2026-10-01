// ASTRA — ABBORDAGGI: the fight inside the Aquila, as code (docs/ABBORDAGGI.md).
//
// A boarding party of the Kharon Mandate comes through a breach and goes for an objective; the Aquila's marines meet it. Both sides are squads of
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
		Withdraw     // leave the ship by the breach
	};
	const TCHAR* TaskName(ETask T);
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
		float HoldS = 70.f;                                     // how long the objective must be held to be taken
		float HearCm = 2600.f;                                  // a shot is heard this far (through the open ways)
		float SensorDelayS = 2.0f;                              // the ship's internal sensors: how stale the marines' picture of the corridors is
		float CutS = 22.f;                                      // how long the Mandate need to cut through a sealed bulkhead
		float PushS = 40.f;                                     // how long the Mandate sit in contact without getting nearer before they press the attack
		bool bFlank = true;                                     // squads go round (the bench turns it off to see what it is worth)
		bool bCover = true;                                     // men look for corners (the bench turns it off for the duels in the open)
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
		int32 Squad = INDEX_NONE;
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
		bool bStand = false;             // stand fast where they are and shoot (no corners, no moves: the bench's duels)
		FString Note;                    // what it was last told or decided, for the reports
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
		Cut          // the Mandate cut through a sealed bulkhead: Target is the door (the damage map's index), Start where it is
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

	enum class EOutcome : uint8 { Running, AquilaHolds, MandateTakes, MandateRepelled, TimedOut };

	struct FMission
	{
		int32 Objective = INDEX_NONE;    // the compartment the Mandate wants
		int32 Breach = INDEX_NONE;       // the compartment they came in by
		FVector BreachPos = FVector::ZeroVector;
		float HeldS = 0.f;
		EOutcome Outcome = EOutcome::Running;
	};

	struct FBook
	{
		int32 Shots = 0, Hits = 0, Misses = 0;
		int32 Killed[2] = {0, 0}, Down[2] = {0, 0}, Exited[2] = {0, 0}, Spawned[2] = {0, 0}, Carried[2] = {0, 0};   // Down: who is down now
		int32 Contacts = 0, Flanks = 0, Retreats = 0, Reloads = 0, Suppressed = 0, Rescues = 0;
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
	 *  at a time. Returns the squads' ids. */
	TArray<int32> SpawnBoarders(int32 BreachComp, const FVector& BreachPos, int32 ObjectiveComp, int32 Count, float FirstAtS = 0.f);
	/** A marine of the Aquila, at a place: Roster is VITA's roster index (INDEX_NONE: a man of the bench). */
	int32 AddMarine(const FString& Name, int32 Roster, const FVector& Pos, bool bLeader, int32 SquadId, float Skill = 0.f);
	/** Any man of either side (the bench's duels, a scenario's hand-made squads). */
	int32 AddUnit(AstraBoard::ESide Side, AstraBoard::ERole Role, const FString& Name, const FVector& Pos, int32 SquadId);
	int32 AddSquad(AstraBoard::ESide Side, const FString& Name);
	/** The Captain joins the fight as a man the game moves. */
	/** A unit that is not in the fight yet: it joins where it stands Seconds from now (a marine roused from his bunk who has to dress and arm). */
	void DelayUnit(int32 UnitId, float Seconds);
	/** A squad by its name ("Watch 1", "Reaction 2", "Ferry Guard Alpha"), exactly as the fight names it (INDEX_NONE when there is none). */
	int32 FindSquad(const FString& Name) const;
	int32 AddCaptain(const FVector& Pos);
	void SetCaptain(const FVector& Pos, float Yaw, bool bLow, float Speed, bool bDown);
	int32 CaptainId() const { return CaptainUnit; }

	// ------------------------------------------------------------------------------------------------ orders (the squad drill the mind's words come to)
	void Order(int32 SquadId, AstraBoard::ETask Task, int32 Comp, const FVector& Pos, float Radius = 0.f, const FString& Note = FString());
	void Respond(int32 SquadId);              // no order: the squad goes to meet what is coming
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
	/** What the Aquila knows of the Mandate's men (the ship's internal sensors in the corridors and what the marines have seen): unit ids and where they were
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
	/** The marines' default response, when nobody has given an order: from the alarm they go (the watch at once, the reaction team after it has armed) to the
	 *  opening that wins the race against the boarders and take its corners (AmbushPortal). */
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
	float SensorT = 0.f;
	TArray<FVector> BreachRoute;
	// boarders still to come in
	struct FPending { int32 Unit; float At; };
	TArray<FPending> Pending;
	float DoorT = 0.f;
	int32 AmbushIdx = INDEX_NONE;
	FMarineCommand Cmd;
	float CmdT = 0.f;
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
	void PlanMandate(FSquad& S);
	void PlanMarines(FSquad& S);
	void ColumnTo(FSquad& S, const FVector& To, float Speed);
	void HoldAround(FSquad& S, const FVector& At, float Radius);
	bool FlankFor(FSquad& S, const FVector& Enemy);
	void Emit(AstraBoard::EEvent Type, int32 Unit, int32 Target = INDEX_NONE, const FVector& Start = FVector::ZeroVector, const FVector& End = FVector::ZeroVector,
	          float Dmg = 0.f, bool bHit = false, const FString& Text = FString());
	FUnit& Spawn(AstraBoard::ESide Side, AstraBoard::ERole Role, const FString& Name, const FVector& Pos, int32 SquadId);
	void ArmUnit(FUnit& U);
	bool Known(const FUnit& U, int32 Enemy, FVector& OutPos, float& OutAge) const;
	FString MandateName(int32 N);
	friend struct FAstraBoardSimTest;
};
