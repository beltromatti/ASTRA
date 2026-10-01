// ASTRA — DISTRUZIONE: what a hit does inside the Aquila, where it lands (docs/DISTRUZIONE.md).
//
// A blow that gets through the shield, the plate and the structure (GUERRA's ApplyHitModel: where it struck, which way it came, what is
// left of it) enters the ship at the plating, follows its own path through the compartments of the ship's plan and spends itself in
// them. What it does in each is physics, not luck: a hole opens to space where it came in (the air goes out, the containment field forms
// on the hole, costs power and may fail), what is combustible in the room takes fire and the fire spreads through the open doors, smoke
// and heat build, the conduits of the room are cut and the systems that pass through it lose power, the section's pressure bulkheads
// close behind the air. The people who really were there (VITA) are hurt or killed by what happens to the room they stand in; the
// damage-control teams (VITA's parties) walk there and work the hazard down.
//
// Plain code over the plan (no actors, no world): cheap enough to run beside the battle (only the compartments that are not as they
// were built are simulated), deterministic from a seed, testable headless (AstraDamageSimCommandlet). The ship subsystem owns an
// instance, feeds it the hits and the teams' work, and reads from it the list of incidents, the power each allocation still carries,
// and what the screens and the effects show.

#pragma once

#include "CoreMinimal.h"
#include "AstraDamageMap.h"
#include "AstraDamageTypes.h"

/** A person physically in a compartment (the life simulation's, handed over by whoever hosts the model). */
struct FAstraDmgPerson
{
	int32 Roster = INDEX_NONE;
	FVector PosCm = FVector::ZeroVector;
	bool bSuited = false;         // in a damage-control party (suited for vacuum and smoke)
	bool bAtPost = false;         // at their duty or battle station (they hold it a few seconds longer than a person off duty)
};

enum class EAstraDmgHarm : uint8 { Decompression, Fire, Smoke, Blast, Electric };

/** What the model asks of the world around it. */
struct FAstraDmgHooks
{
	TFunction<void(const FString& Text, bool bReport)> Event;
	TFunction<void(const FAstraDmgComp& Comp, TArray<FAstraDmgPerson>& Out)> PeopleIn;
	/** Wounds (or kills) a person of the roster: the roster's own words about them ("Crewman ... (engineering, from ...) wounded, taken to the medbay"). */
	TFunction<FString(int32 Roster, bool bKill, EAstraDmgHarm Cause)> Harm;
	TFunction<void(FName DoorId, bool bSealed)> SealDoor;
	TFunction<void()> PlanChanged;    // some door of the plan changed state: the people's routes are made again
	TFunction<void(float Pct)> AddHeat;
	TFunction<void(float Points)> StructureBurn;
	TFunction<int32()> Alert;     // 0 green, 1 yellow, 2 red
};

/** A person's exposure to what is going on in a compartment. */
struct FAstraDmgExposure
{
	enum class EState : uint8 { Exposed, Escaped, Down };
	EState State = EState::Exposed;
	float Seconds = 0.f;          // since the hazard began for them
	float EscapeS = 5.f;          // how long they need to get out
	float Hypoxia = 0.f, Burn = 0.f, Smoke = 0.f;
};

/** One compartment that is not as it was built. */
struct FAstraDmgState
{
	int32 Comp = INDEX_NONE;
	// the air
	float Air = 1.f;              // pressure, 1 = nominal (a person is at ease down to 0.6, faints under 0.35)
	float Hole = 0.f;             // m2 open to space
	FVector HoleAt = FVector::ZeroVector;   // where the blow came in (cm)
	// the containment field on the hole
	enum class EField : uint8 { Off, Forming, Holding, Failed };
	EField Field = EField::Off;
	float FieldT = 0.f;           // seconds until it forms / until it may form again
	float FieldStress = 0.f;      // 0..1: at 1 it gives way
	// the fire
	float Fire = 0.f;             // 0..1
	float Fuel = 1.f;             // what is left to burn
	float Smoke = 0.f;            // 0..1
	float Heat = 0.f;             // 0..1 (0.5: a person burns)
	float FireAge = 0.f;
	float Suppress = 0.f;         // fixed suppression discharging: seconds left
	bool bSuppressSpent = false;
	// power and structure
	float Power = 1.f;            // the power the room still has
	float Wreck = 0.f;            // 0..1: the room's fabric and what it holds; at 1 it is gutted
	// the doors
	bool bLocked = false;         // locked down: its doors hold the air, the smoke and the fire in
	bool bGutted = false;         // lost with its section of the hull: no air, no power, no repair (the war's: a section whose structure is gone)
	float TeamT = 0.f;            // a damage-control team is working here (seconds since it last was)
	float TeamFire = 0.f;         // how hard the team on the fire sprays (the rate the fire dies at)
	// the people in it
	TMap<int32, FAstraDmgExposure> People;
	// the incidents that stand for it in the ship's list (0: none)
	int32 BreachId = 0, FireId = 0, ConduitId = 0;
	float Age = 0.f;              // since anything last happened in it

	bool Calm() const
	{
		return Air > 0.995f && Hole < 0.005f && Fire < 0.02f && Smoke < 0.02f && Heat < 0.02f && Power > 0.995f && Wreck < 0.005f && Suppress <= 0.f && !bLocked
		       && People.Num() == 0 && BreachId == 0 && FireId == 0 && ConduitId == 0;
	}
};

/** What one blow did, for the ship's report. */
struct FAstraImpactResult
{
	FVector EntryCm = FVector::ZeroVector;     // where it came in (the plan's frame, cm)
	TArray<int32> Comps;                       // the compartments it spent itself in, the first where it came in
	float Energy = 0.f;                        // what reached the first
	TArray<FString> Lines;                     // what happened, in the report's words
	int32 Killed = 0, Wounded = 0;
	TArray<FString> People;                    // who (the roster's words)
	bool bBreach = false, bFire = false, bPower = false, bWreck = false;
};

/** The Captain, as the model sees them: where they stand and what the air, the smoke and the fire have done to them. */
struct FAstraDmgCaptain
{
	enum class EState : uint8 { Well, Impaired, Down, Dead };
	EState State = EState::Well;
	float Hypoxia = 0.f, Burn = 0.f, Smoke = 0.f, Trauma = 0.f;
	float Peril = 0.f;             // 0..1: how bad the compartment is for them now (the screen's tunnel)
	float DownS = 0.f;             // how long they have been down
	int32 Comp = INDEX_NONE;
	FString Cause;                 // what is doing it
	FString Why;                   // how they ended (for the record)
};

/** How much of each power allocation the ship's distribution still carries (0..1), and what the fields cost. */
struct FAstraDmgPower
{
	float Factor[(int32)EAstraDmgCategory::Num] = {1.f, 1.f, 1.f, 1.f, 1.f, 1.f};
	float FieldLoad = 0.f;        // 0..1 of the life-support allocation spent on containment fields
	int32 Fields = 0;
};

class ASTRA_API FAstraDamageModel
{
public:
	void Init(TSharedRef<const FAstraDamageMap> InMap, FAstraDmgHooks InHooks, int32 Seed);
	bool IsReady() const { return Map.IsValid(); }
	const FAstraDamageMap& GetMap() const { return *Map; }
	void Reset();

	// ------------------------------------------------------------------------------------------------ the blows
	/** A blow on the hull. Appends its incidents to Incidents (new ones get ids from NextId). */
	void Impact(const FAstraHullHit& Hit, FAstraImpactResult& Out);
	/** Where a blow would enter the plan and which compartments it would cross, without doing anything (the tests, the displays). */
	bool Trace(const FAstraHullHit& Hit, FVector& OutEntryCm, TArray<int32>& OutComps, float* OutEnergy = nullptr) const;
	/** A compartment takes damage directly (the tests, the war's catastrophes): an energy as a hit's, spent there. */
	void Strike(int32 Comp, float Energy, uint8 Type, const FVector& AtCm, bool bHole, FAstraImpactResult& Out);
	/** A lengthwise section of the hull is gutted (the war's: its structure is at zero): what lived in the compartments along it, between two points on the
	 *  ship's axis (plan cm), is lost: the air, the power, most of the people (the bridge's island, above the hull, is not part of it). */
	void GutSection(float XMinCm, float XMaxCm, const FString& Name, FAstraImpactResult& Out);
	/** The conduits of a compartment burn out (the reactor's heat past what the coolant holds): Loss of its power, and a scorch for whoever is at the panels. */
	void Overload(int32 Comp, float Loss, FAstraImpactResult& Out);

	// ------------------------------------------------------------------------------------------------ time
	/** Advances the physics by Dt seconds (it steps itself on a fixed 0.2 s, a long Dt is several steps). */
	void Tick(float Dt, TArray<FAstraDamage>& Incidents);
	/** A team is on the scene of an incident: it works the hazard down for Dt seconds. True when the incident is done (and removed). */
	bool Work(FAstraDamage& Incident, float Dt, TArray<FAstraDamage>& Incidents);
	/** How long a team needs for an incident as it stands (s). */
	float WorkSeconds(const FAstraDamage& Incident) const;

	// ------------------------------------------------------------------------------------------------ the Captain
	/** The Captain stands in Comp (INDEX_NONE: outside the plan, a Falcon, a planet): the air and the fire work on them. */
	void TickCaptain(float Dt, int32 Comp, const FVector& PosCm);
	const FAstraDmgCaptain& Captain() const { return Cap; }
	/** The Captain was taken out of harm's way (the rescue's end): the doses are cleared. */
	void CaptainRescued();
	void CaptainDied(const FString& Why) { Cap.State = FAstraDmgCaptain::EState::Dead; Cap.Why = Why; }

	// ------------------------------------------------------------------------------------------------ what is read
	const FAstraDmgState* Find(int32 Comp) const { return Active.Find(Comp); }
	const TMap<int32, FAstraDmgState>& States() const { return Active; }
	const FAstraDmgPower& Power() const { return PowerNow; }
	/** How much of an allocation ("shields", "weapons", "engines", "sensors", "life_support", "flight_deck") the distribution still carries (1 when the model is not up). */
	float CategoryFactor(const FString& Name) const;
	/** The power allocations a compartment's conduits feed, in words ("shields, engines"; empty when it only feeds itself). */
	FString SystemsText(int32 Comp) const;
	/** The room whose conduits give way when the ship's heat is past what they carry: the Seq-th of those nearest to Main Engineering (they take turns). */
	int32 PickHeatRoom(int32 Seq) const;
	/** The pressure bulkheads that are shut now (door indices). */
	const TSet<int32>& SealedDoors() const { return Sealed; }
	/** Compartments that are lost (wrecked), and how many incidents the model has open. */
	int32 NumWrecked() const;
	int32 NumHazards() const;
	/** A hazard's severity right now (0..1) for the ship's list and the screens. */
	static float SeverityOf(const FAstraDmgState& S, int32 Kind /* 0 breach, 1 fire, 2 conduit */);
	/** The cumulative books of the run (the bench and the info command): hits, energy, holes, fires, casualties, fields failed, doors sealed. */
	struct FBooks
	{
		int32 Hits = 0, HitsInside = 0, Holes = 0, Fires = 0, Conduits = 0, Wrecks = 0, FieldsFailed = 0, DoorsSealed = 0, Explosions = 0, Suppressions = 0;
		int32 Killed = 0, Wounded = 0, Rescued = 0, Escaped = 0;
		double Energy = 0.0, EnergyInside = 0.0, StructureBurnt = 0.0;
		int32 MaxActive = 0, MaxIncidents = 0;
		int32 OccupiedBlows = 0, PeopleNear = 0;      // blows that crossed a room with someone in it, and how many were in the rooms they crossed
	};
	const FBooks& Books() const { return Stats; }
	FString InfoText() const;
	/** The ids the incidents take (the ship's other incidents, a radiator wing, use the same counter). */
	int32 NewIncidentId() { return NextIncident++; }
	int32 MaxIncidents = 28;

	/** The way a person leaves: the nearest way out of a compartment from a point (metres), 0 when there is none. */
	float ExitDistanceM(int32 Comp, const FVector& PosCm) const;
	/** Whether a compartment is in a state fit for the crew's eyes (the effects, the lights): 0 calm .. 1 grave. */
	float Emergency(int32 Comp) const;

private:
	TSharedPtr<const FAstraDamageMap> Map;
	FAstraDmgHooks Hooks;
	FRandomStream Rng;
	TMap<int32, FAstraDmgState> Active;
	TSet<int32> Sealed;                        // door indices
	TMap<int32, float> DoorTimer;              // shut blast doors: how long the section beside them has been whole
	TMap<int32, float> SpreadTold;             // when a fire spreading into a stretch of the ship was last told
	TMap<int32, float> SectionTimer;           // sections losing their air: how long (deck * 256 + section)
	FAstraDmgPower PowerNow;
	FAstraDmgCaptain Cap;
	FBooks Stats;
	FVector CapPos = FVector::ZeroVector;
	TArray<TPair<FString, bool>> Pending;
	int32 NextIncident = 1;
	int32 AlertNow = 0;
	mutable TArray<int32> HeatRooms;
	float Acc = 0.f, PeopleT = 0.f, SyncT = 0.f, SystemsT = 0.f, Clock = 0.f;
	bool bDoorsChanged = false;
	bool bImpactOccupied = false;
	float DoorsChangedAt = -100.f;

	FAstraDmgState& Get(int32 Comp);
	void Step(float Dt);
	void StepFields(float Dt);
	void StepAir(float Dt);
	void StepFire(float Dt);
	void StepDoors(float Dt);
	void StepPeople(float Dt);
	void SyncIncidents(TArray<FAstraDamage>& Incidents);
	void RecomputePower();
	float Openness(const FAstraDmgLink& L, const FAstraDmgState& A, const FAstraDmgState* B) const;
	void Deposit(int32 Comp, float Energy, uint8 Type, const FVector& AtCm, const FVector& Dir, bool bFirst, FAstraImpactResult& Out);
	void BlastPeople(int32 Comp, float Energy, uint8 Type, const FVector& From, const FVector& To, FAstraImpactResult& Out);
	bool SkinEntry(const FAstraHullHit& Hit, FVector& OutAt, FVector& OutDir) const;
	void Harm(int32 Roster, bool bKill, EAstraDmgHarm Cause, FAstraImpactResult* Out, const FAstraDmgComp& Where);
	FString Say(int32 Comp) const;
	void Report(const FString& Text, bool bReport) { Pending.Emplace(Text, bReport); }      // told at the end of the call, when the books are in order
	void Flush();
	void CloseIncident(FAstraDamage& D, const TCHAR* How);
};
