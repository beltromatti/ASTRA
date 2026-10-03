// ASTRA — FLOTTA-VIVA: the inside of a ship that is not the Aquila (docs/FLOTTA-VIVA.md).
//
// The Aquila's damage model (AstraDamageModel.*) run on the plan of a ship's class (AstraFleetPlan.*), with the Aquila's own people replaced by the
// ship's light roster: so many aboard, standing at action stations where the class's garrison puts them, a few of them named (the captain and the
// chain of command), a few damage-control parties that walk where the damage is and work it down through the model. A blow the war lands on the hull
// enters where it struck, runs through the rooms behind the plating and spends itself in them, exactly as it does on the Aquila: the air leaves by
// the holes, fires grow and spread by the open doors, conduits are cut and the systems that pass through them lose power, the pressure bulkheads
// shut, and the people who were there are hurt or killed.
//
// What comes out goes back to the war: how much of each power allocation the ship's distribution still carries (shields, weapons, engines, sensors,
// flight deck: Factor), what burns and what vents (the war's sections, the effects), how many are left and who commands, and what the ship's captain
// would tell the others (BriefJson) and what a sensor sees from outside (SeenJson, FillView).
//
// Plain code (no actors, no world), deterministic from a seed. A ship that has not been hit has no interior (it is made at the first blow that gets
// through, and costs nothing before it); one that is calm costs nothing between blows.

#pragma once

#include "CoreMinimal.h"
#include "Dom/JsonObject.h"
#include "AstraDamageModel.h"
#include "AstraFleetPlan.h"

/** The words for a billet of the chain of command ("captain", "executive officer"...). */
ASTRA_API const TCHAR* AstraFleetBilletWord(FName Role);

/** What the crew of a ship is doing at action stations. */
enum class EFleetRole : uint8 { Bridge, Control, Gunnery, Magazine, Engineering, DamageControl, Medical, Flight, Sensors, Marine, MarineDock, Reserve, Num };

/** One of the ship's people. */
struct FFleetPerson
{
	int32 Comp = INDEX_NONE;                 // the compartment they are in
	FVector3f PosCm = FVector3f::ZeroVector; // where in it (plan cm)
	EFleetRole Role = EFleetRole::Reserve;
	uint8 State = 0;                         // 0 fit, 1 wounded, 2 dead
	uint8 Cause = 0;                         // EAstraDmgHarm of what hurt them
	int8 Party = -1;                         // the damage party they are in
	int16 Named = -1;                        // index in Named, -1: no name that matters
	float HarmAt = 0.f;
};

/** An officer of the chain of command: the one the war and the minds know by name. */
struct FFleetNamed
{
	FName Role;
	FString Rank, Name;
	int32 Line = 0;
	int32 Person = INDEX_NONE;
	bool bToldGone = false;
};

/** A damage-control party at work. */
struct FFleetPartyState
{
	int32 Home = INDEX_NONE;
	int32 Size0 = 4;
	TArray<int32> Members;                   // people
	int32 Incident = 0;                      // the incident it is on (0: free)
	bool bOnScene = false;
	int32 Comp = INDEX_NONE;                 // where it is
};

/** A thing the interior wants the war to hear: told in the ship's own words. */
struct FFleetEvent
{
	float T = 0.f;
	FString Text;
	bool bGrave = false;
};

/** What a sensor or the holo table may be told about an inside. Detail 1: what the eye sees of a hull (a breach venting, a fire showing, dark windows); 2: what the sensors of a
 *  classified track make of her (life signs, hot spots, power); 3: the ship's own (the datalink). */
struct FAstraFleetView
{
	int32 Detail = 0;
	int32 CrewTotal = 0, CrewFit = 0, CrewWounded = 0, CrewDead = 0;   // (the ship's own side: Detail 3)
	int32 LifeSignsPct = -1;                        // what a classified track's emissions give away of the crew, to the nearest five per cent (Detail 2); -1 where nothing shows
	int32 Fires = 0, Breaches = 0, Dark = 0;
	TArray<FVector> FireM, BreachM;                 // hull frame, metres (the ship's mesh frame)
	FVector HullCentreM = FVector::ZeroVector, HullHalfM = FVector(1.0);   // the plan's hull volume in the same frame: where the points lie in it (for a diagram)
	float Power[6] = {1.f, 1.f, 1.f, 1.f, 1.f, 1.f};
	int32 PartiesBusy = 0, Parties = 0;
	int32 BulkheadsShut = 0;
	bool bCaptainDown = false, bCaptainDead = false;
	FString Command;
};

/** What an inside is at this moment, for a boarding (ABBORDAGGI): the rooms that are not as the plan built them, the pressure bulkheads shut, and who is alive and where. A room that is not
 *  listed is as built: full air, no fire, full power. The rooms are the plan's (the compartments of FFleetClassPlan::Map), by index. */
struct FFleetSnapshot
{
	struct FRoom
	{
		int32 Comp = INDEX_NONE;
		float Air = 1.f, Hole = 0.f, Fire = 0.f, Smoke = 0.f, Heat = 0.f, Power = 1.f, Wreck = 0.f;
		bool bGutted = false, bLocked = false;
	};
	struct FHand
	{
		int32 Comp = INDEX_NONE;
		FVector PosCm = FVector::ZeroVector;
		uint8 Role = 0;                  // EFleetRole
		bool bWounded = false;
		FString Billet;                  // "captain", "chief_engineer"... for the named; empty for the rest
		FString Name;                    // "Commander Idris Haldane" for the named
	};
	TArray<FRoom> Rooms;
	TArray<FName> SealedDoors;           // the pressure bulkheads that are shut (door ids of the plan)
	TArray<FHand> Hands;                 // the people alive (fit or wounded), where they are now
	int32 Killed = 0, LostWithShip = 0;
	FString Command;                     // who has the conn
};

/** Where an inside shows on the hull: the effects draw fires and streaming atmosphere there, and light the windows by what is still powered. */
struct FFleetFxPoints
{
	TArray<FVector> Fire[3], Vent[3];               // by the war's three sections (bow, mid, stern): hull frame, metres
	float Lit = 1.f;                                // the share of the windows still lit (1 as built)
};

class ASTRA_API FAstraShipInterior
{
public:
	FAstraShipInterior(TSharedRef<const FFleetClassPlan> InPlan, int32 InShipId, const FString& InShipName, int32 Seed);

	// ---------------------------------------------------------------------------------------------------------------- what the war does to it
	/** A blow on the hull (the same record the Aquila's takes). */
	void Impact(const FAstraHullHit& Hit);
	/** One of the war's three lengthwise sections (0 bow, 1 mid, 2 stern) has no structure left: what lived in its rooms is lost. */
	void GutSection(int32 WarSection);
	/** A room takes a blow directly (the bench and the console): an energy as a hit's, spent there. */
	void Strike(int32 Comp, float Energy, uint8 Type, bool bHole);
	/** What the war should be told, once each: the crew falling to three quarters, half, a quarter; the captain down or dead; weapons or engines
	 *  down by a fifth; a fire in a magazine. Lines in the ship's own words (the ship's name first). */
	void CollectNews(TArray<FString>& Out);
	/** Advances it by Dt seconds. */
	void Tick(float Dt);

	// ---------------------------------------------------------------------------------------------------------------- what comes out
	/** How much of an allocation the ship's distribution still carries (0.5..1: the backup ring keeps half). */
	float Factor(EAstraDmgCategory C) const { return Model.Power().Factor[(int32)C]; }
	/** The structure the fires have eaten since this was last asked (hull points of the Aquila's scale). */
	float TakeBurn() { const float B = BurnPending; BurnPending = 0.f; return B; }
	/** How much of what a room gives is left: its fabric and its power (1 as built, 0 lost or gutted). */
	float RoomFit(int32 Comp) const;
	/** How much each of the war's six systems (engines, sensors, hangar, bridge, reactor, point defence) still has of what the inside gives it: its room's fabric and power,
	 *  and the people who work it (1 as built). The war multiplies its own, hull-level state by it (it is never written into it: a room that is mended gives it back). */
	float SysFit(int32 WarSystem) const { return SysFitV[FMath::Clamp(WarSystem, 0, 5)]; }
	/** What the room that serves a weapon mount (the class's mount list, in order) gives it: 1 as built; 1 too where no room serves it. */
	float MountFit(int32 MountIndex) const;
	/** How many of the gunners and the magazine hands are left, as a share of the guns' work (0.4..1). */
	float WeaponCrew() const { return WeaponCrewV; }
	int32 CrewTotal() const { return People.Num(); }
	int32 CrewFit() const { return Fit; }
	int32 CrewWounded() const { return Wounded; }
	int32 CrewDead() const { return Dead; }
	/** The ship is gone (her reactor breached, her hull broke apart, she was shot to pieces): those still aboard, fit or wounded, are lost with her ("destroyed with all hands").
	 *  Returns how many. They are counted apart from the people the blows killed. */
	int32 LoseWithShip();
	int32 CrewLostWithShip() const { return Lost; }
	/** Fit crew and half the wounded, over the complement: how much of a crew is left to fight the ship. */
	float CrewStrength() const { return People.Num() ? (Fit + 0.5f * Wounded) / (float)People.Num() : 0.f; }
	int32 Fires() const;
	int32 Breaches() const;
	int32 DarkRooms() const;
	/** Does anything burn (vent to space) in a lengthwise section of the war? */
	bool SectionBurning(int32 WarSection) const;
	bool SectionVenting(int32 WarSection) const;
	/** The ship's captain: 0 fit, 1 wounded, 2 dead; the officer who commands the ship now (the next of the chain who is fit), or null. */
	int32 CaptainState() const;
	const FFleetNamed* Commander() const;
	/** True when the interior has nothing going on (no hazard, no team at work): it costs nothing. */
	bool IsCalm() const { return bCalm; }
	void TakeEvents(TArray<FFleetEvent>& Out) { Out.Append(Outbox); Outbox.Reset(); }
	const FAstraDamageModel& GetModel() const { return Model; }
	FAstraDamageModel& GetModel() { return Model; }
	const FFleetClassPlan& GetPlan() const { return *Plan; }
	const TArray<FFleetPerson>& GetPeople() const { return People; }
	const TArray<FFleetNamed>& GetNamed() const { return Named; }
	/** The captain's name and rank (the minds' persona of the ship's commander): what the war and the minds say of the captain from then on. */
	void SetCaptain(const FString& Rank, const FString& Name);
	/** The damage-control parties, and how many of each are on their feet. */
	int32 PartiesCount() const { return Parties.Num(); }
	int32 PartyMembersNow(int32 Party) const { return Parties.IsValidIndex(Party) ? Parties[Party].Members.Num() : 0; }

	// ---------------------------------------------------------------------------------------------------------------- what is said of it (AstraFleetViews.cpp)
	/** Everything a ship's own captain knows of the inside, for the minds of her side: the people, the fires and breaches, the power, the parties. Keys only where there is something to say. */
	TSharedRef<FJsonObject> BriefJson() const;
	/** What an observer's sensors tell of her from outside, by how well they know her (Detail 1, 2). */
	TSharedRef<FJsonObject> SeenJson(int32 Detail) const;
	void FillView(FAstraFleetView& Out, int32 Detail) const;
	/** The inside as it stands, for a boarding: the rooms that are not as built, the bulkheads shut, the people alive and where (ABBORDAGGI). */
	void Snapshot(FFleetSnapshot& Out) const;
	/** Where it burns and vents, by section, and how much of the ship is still lit: for the effects (a few points per section). */
	void FxPoints(FFleetFxPoints& Out, int32 MaxPerSection = 12) const;
	/** A line for the bench and the console. */
	FString InfoText() const;
	/** The path of the last blow through the rooms, in words (kept only while KeepTrace is on: the bench and the console). */
	void KeepTrace(bool bOn) { bTrace = bOn; }
	const FString& TraceText() const { return LastTrace; }
	/** The books of a ship's interior: what the war and the bench ask. */
	TSharedRef<FJsonObject> BooksJson() const;

private:
	TSharedRef<const FFleetClassPlan> Plan;
	int32 ShipId = 0;
	FString ShipName;
	FAstraDamageModel Model;
	FRandomStream Rng;
	TArray<FAstraDamage> Incidents;
	TArray<FFleetPerson> People;
	TMap<int32, TArray<int32>> ByComp;
	TArray<FFleetNamed> Named;
	TArray<FFleetPartyState> Parties;
	TArray<int32> WoundedWaiting;                        // people hurt and not yet carried to the medbay
	TArray<FFleetEvent> Outbox, Log;
	float Clock = 0.f, SlowT = 0.f, BurnPending = 0.f;
	int32 Fit = 0, Wounded = 0, Dead = 0, Lost = 0;
	bool bCalm = true, bFlush = false;
	int32 Hits = 0, HitsInside = 0;
	bool bTrace = false;
	FString LastTrace;
	FVector LastEntryCm = FVector::ZeroVector;
	float SysFitV[6] = {1.f, 1.f, 1.f, 1.f, 1.f, 1.f};
	float WeaponCrewV = 1.f;
	int32 RoleTotal[(int32)EFleetRole::Num] = {}, RoleFit[(int32)EFleetRole::Num] = {}, RoleHurt[(int32)EFleetRole::Num] = {};
	float RoleStrength(EFleetRole R) const { return RoleTotal[(int32)R] > 0 ? (RoleFit[(int32)R] + 0.5f * RoleHurt[(int32)R]) / (float)RoleTotal[(int32)R] : 1.f; }
	void RefreshFit();
	int32 ToldCrewBand = 0, ToldCaptain = 0;             // what the war has been told (CollectNews)
	bool bToldWeapons = false, bToldEngines = false;
	bool bToldMagazine = false;
	float MagazineClearAt = -1.f;                        // since when no magazine has burned (the next fire in one is news again after a while)

	void BuildCrew();
	int32 AddPerson(int32 Comp, EFleetRole Role);
	void MovePerson(int32 Who, int32 ToComp);
	FString MakeName(bool bMandate);
	void PeopleIn(const FAstraDmgComp& C, TArray<FAstraDmgPerson>& Out) const;
	FString HarmPerson(int32 Who, bool bKill, EAstraDmgHarm Cause);
	void Note(const FString& Text, bool bGrave);
	void TickParties(float Dt);
	void TickMedevac(float Dt);
	int32 WarSectionOf(int32 Comp) const;
	FString RoomWord(int32 Comp) const;
	friend struct FFleetTestAccess;
};

/** The checks of the insides on every class's plan, with no battle and no world (AstraFleetTest.cpp, tools/fleet.py check): a line per check, "PASS" or "FAIL" first, and a verdict last. Returns how many failed. */
ASTRA_API int32 AstraFleetSelfTest(TArray<FString>& Lines);
