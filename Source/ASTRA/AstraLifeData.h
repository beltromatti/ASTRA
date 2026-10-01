// ASTRA — VITA, the data of life aboard: the rooms and places of the Aquila's plan (data/ship/aquila_plan.json) as the
// crew uses them (where one sleeps, works, eats, stands a watch), and the tables of how they live (data/ship/aquila_life.json:
// the watches, the day, the departments' jobs and battle stations). Pure data, no world: it loads on a worker thread, and
// the life simulation (AstraLifeSim.*) and its headless test (AstraLifeSimCommandlet) stand on it.
//
// The plan's own subsystem (UAstraShipPlan) answers the routes; this reads the same file for what routes do not need:
// what each room is for, how many it holds, where the seats, bunks and posts are.

#pragma once

#include "CoreMinimal.h"

/** What a person is doing (the schedule's word, or the ship's: an alarm, an incident, a wound). */
enum class EAstraLifeAct : uint8
{
	Sleep,      // in a bunk
	Duty,       // at their post, working their watch
	Meal,       // eating
	Leisure,    // off duty, awake: the lounge, the library, the gym, their cabin...
	Battle,     // at their battle station (general quarters)
	Repair,     // in a damage-control party: on the way to an incident, or working it
	Patient,    // wounded: on the way to the Medbay, or in its care
	Dead,
	Count
};

const TCHAR* AstraLifeActName(EAstraLifeAct A);

/** What a place is for. */
enum class EAstraPlaceKind : uint8 { Hub, Sleep, Sit, Stand, Work, Eat, Watch };

enum class EAstraRoomStatus : uint8 { Planned, Built, Existing };

/** A spot where one person can be for a while: a seat, a bunk, a post, or the heart of a room (a hub: room for several). */
struct FAstraLifePlace
{
	FName Id;                                    // the plan's station id, or the room's id for a hub
	int32 Comp = INDEX_NONE;                     // the room it is in
	FVector Pos = FVector::ZeroVector;           // world cm, on the floor (a bunk: the floor under it)
	float Yaw = 0.f;                             // degrees: the way the person faces (the plan's yaw); a bunk: the way the head lies
	EAstraPlaceKind Kind = EAstraPlaceKind::Hub;
	int16 Deck = 0;
	int16 Capacity = 1;                          // people at once (a hub: the room's crew slots)
	FName External;                              // a pre-placed actor keeps this place (its station id): no body is made for whoever is here
	FName Role;                                  // what whoever stands here does ("cook", "plane captain"...), from the plan
	float Height = 0.f;                          // a seat: hip height (cm); a bunk: the body's height over the floor (cm)
};

/** A room of the plan (a compartment), as life uses it. */
struct FAstraLifeComp
{
	FName Id;
	FName Kind;
	FString Name;
	TCHAR Section = TEXT('A');
	int16 Deck = 0;
	FName Dept;                                  // the plan's department: command, engineering, services, flight, science, security, medical, neutral
	EAstraRoomStatus Status = EAstraRoomStatus::Planned;
	int32 Slots = 0;                             // people it holds at work (crew_slots, or capacity)
	FBox Box = FBox(ForceInit);                  // world cm
	int32 Hub = INDEX_NONE;                      // its heart: a place
	TArray<int32> Places;                        // the stations in it
	bool bWalled = false;                        // every door locked (a room the level does not open): nobody goes there
	bool bCorridor = false;
	bool bHall = false;                          // a great hall (hangar, engineering, mess): posts come from the life data
	int16 DeckLo = 0, DeckHi = 0;                // the decks it spans (a hall is tall)
};

/** One department's jobs. */
struct FAstraLifeSelector
{
	TArray<FName> Kinds;
	FName Dept;                                  // NAME_None: any
	TArray<int32> Decks;                         // empty: any
	float Weight = 1.f;
};

enum class EAstraLifeClass : uint8 { Rating, Officer, Marine };

struct FAstraLifeDept
{
	FString Name;                                // the roster's department
	FName PlanDept;
	EAstraLifeClass Class = EAstraLifeClass::Rating;
	FString Job;
	TArray<FAstraLifeSelector> Duty;
	TArray<FAstraLifeSelector> Battle;
	bool bYellow = false;                        // goes to the post at condition yellow
};

/** One way to spend free time. */
struct FAstraLifeLeisure
{
	FName Id;
	TArray<FName> Kinds;                         // room kinds; "__home": their own cabin
	FVector2D Taste = FVector2D(0.f, 1.f);       // each person draws their liking for it from here
	FString Label;
};

struct FAstraLifeWatch
{
	FString Name;
	float Start = 0.f;
};

/** How a day goes (hours from the start of a watch). */
struct FAstraLifeDay
{
	float DutyFirst = 4.f, MealLen = 0.6f, WindDown = 1.f, SleepStart = 12.f, SleepLen = 7.5f, MealBefore = 22.75f;
	FVector2D J1 = FVector2D(-0.5, 0.5), J2 = FVector2D(-0.25, 0.75), J3 = FVector2D(-0.5, 1.25), J4 = FVector2D(-0.5, 0.25), JSleep = FVector2D(-0.5, 0.5);
	FVector2D WakeDelayS = FVector2D(15.0, 70.0);
};

struct FAstraLifeSpeed
{
	float WalkCmS = 135.f, HurryCmS = 300.f, Spread = 0.12f, StairsS = 11.f, LiftS = 9.f;
};

struct FAstraLifeVisibility
{
	int32 MaxBodies = 40;
	float SpawnM = 95.f, DespawnM = 115.f, DeckBandCm = 420.f;
};

struct FAstraLifeTeams
{
	int32 Count = 4, Size = 6, Min = 2;
	FString Dept = TEXT("damage control"), BackupDept = TEXT("engineering");
	TArray<FName> LockerKinds;
	float JogCmS = 360.f;
};

/** A stair tower, for walking its flights (the plan lists the tower as a compartment; its mesh is the kit's 8 x 8 m tower). */
struct FAstraLifeTower
{
	FVector Origin = FVector::ZeroVector;        // world cm, the mesh's corner on its deck's floor
	float YawDeg = 0.f;
	int16 Deck = 0;
	bool bBuilt = false;
	FVector Well = FVector::ZeroVector;          // the graph's stair node (world cm)
};

class FAstraLifeMap
{
public:
	// ---- the plan
	TArray<FAstraLifeComp> Comps;
	TArray<FAstraLifePlace> Places;
	TMap<FName, int32> CompByName;
	TMap<FName, int32> PlaceByName;
	TMap<FName, TArray<int32>> CompsByKind;
	TArray<float> DeckFloorCm;                   // by deck number (index 0 unused)
	TArray<FAstraLifeTower> Towers;

	// ---- the tables
	TArray<FAstraLifeWatch> Watches;
	FAstraLifeDay Day;
	FAstraLifeSpeed Speed;
	FAstraLifeVisibility Vis;
	FAstraLifeTeams Teams;
	TMap<FString, FAstraLifeDept> Depts;         // by the roster's department name
	TArray<FAstraLifeLeisure> Leisure;
	TMap<FName, FString> JobByRoom;
	TMap<FName, FString> OfficerJobByRoom;      // an officer's job by the room of their post (a division officer, not a rating)
	TArray<FAstraLifeSelector> HomeMarine, HomeOfficer, HomeRating;
	TArray<FName> MealKinds;
	FString Menu;
	float TimeScale = 12.f;
	float StartHour = 9.5f;
	float StatusWeight[3] = {1.f, 2.5f, 3.f};    // planned, built, existing
	TArray<FName> MedbayKinds;

	/** Reads the plan and the life tables. False (and a reason in OutError) when the plan is missing or does not parse. The life tables
	 *  fall back to their defaults when missing (a game without the life file still has a plan). */
	bool Load(FString& OutError);

	/** The smallest room containing a point (world cm), or INDEX_NONE. */
	int32 CompartmentAt(const FVector& Cm) const;

	/** The deck a point is on: the room's, or the nearest floor below. */
	int32 DeckAt(const FVector& Cm) const;

	/** A human name of a place, "Deck 4 · Section B · Main Galley". */
	FString Describe(int32 CompIdx) const;

private:
	// a coarse grid over x, y: the rooms overlapping each cell, for the point lookup
	static constexpr float CellCm = 1000.f;
	int32 GridX0 = 0, GridY0 = 0, GridNX = 0, GridNY = 0;
	TArray<TArray<int32>> Grid;
	void BuildGrid();
	void AddStations(const TSharedPtr<class FJsonObject>& Room, int32 CompIdx);
	void AddHalls(const TSharedPtr<class FJsonObject>& Life);
	void LoadLife(const TSharedPtr<class FJsonObject>& Life);
};
