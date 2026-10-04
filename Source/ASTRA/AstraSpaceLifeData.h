// ASTRA — the living space of a system (SPAZIO-VIVO, docs/SPAZIO.md): what is where and what flies between. This file is the static half: the kinds of civilian hull,
// the places of a system (the Janus Gate and its Keeper Station, the Arsenal, the refineries of Tiberius, the Ceres Belt), the lanes between them and the traffic
// that runs on them, all read from data/space/*.json (a designer changes the sky of a system without touching the code), and the layout of one system once its
// anchors are known (where the Gate stands, which way the world lies in the sky).
//
// Plain structs, no engine objects: the traffic (AstraSpaceLifeTraffic.*), the wrecks (AstraWrecks.*) and the bench run on them as they stand, and everything is in
// the battle's system frame (metres, doubles' worth of float: the Aquila is where the simulation says; the game draws round her).

#pragma once

#include "CoreMinimal.h"

namespace AstraSpace
{
	constexpr double OneKm = 1000.0;

	/** What a hull is for: the traffic's tours, the berths it may use, its look. */
	enum class ERole : uint8 { Freight, Fuel, Passenger, Tug, Ore, Patrol, Num };
	inline uint32 RoleBit(ERole R) { return 1u << (uint32)R; }
	ERole RoleFromName(const FString& Name);
	const TCHAR* RoleName(ERole R);

	/** What a place is to the traffic. */
	enum class EPlaceKind : uint8 { Gate, Keeper, Arsenal, Refinery, Orbit, Belt, Station, Num };
	EPlaceKind PlaceKindFromName(const FString& Name);
	const TCHAR* PlaceKindName(EPlaceKind K);

	// ------------------------------------------------------------------------------------------------------------------ what a mesh carries
	/** One lamp of a hull or a place: where (metres, the mesh's frame: x forward, y to starboard, z up), what colour, how big, how bright, how it blinks. */
	struct FLamp
	{
		FVector P = FVector::ZeroVector;
		FLinearColor C = FLinearColor::White;
		float SizeM = 1.f;                       // metres across up close
		float Glow = 100.f;                      // the intensity when lit (the war's glow scale: 160-900)
		uint8 Pattern = 0;                       // see PatternOn
		float Phase = 0.f;                       // seconds, where in its pattern it starts (chasers use it to run along a row)
	};

	/** The pattern of a lamp at time T (s) with a phase: 0..1. 0 steady, 1 a double white flash, 2 a slow red pulse (the ships' own, AstraNavLights), 3 an amber
	 *  blink, 4 a quick triple strobe (obstruction lights), 5 a slow beacon, 6 a chaser (a short flash, its phase running down a row), 7 a flame's flicker. */
	float PatternOn(uint8 Pattern, float T, float Phase);

	/** A drive bell of a hull: where its lip is (metres, the mesh's frame) and its throat radius (the plume is as wide as the throat and as long as the thrust is hard). */
	struct FBell
	{
		FVector P = FVector::ZeroVector;
		float R = 3.f;
	};

	/** A berth: where a hull lies when it is docked (its centre and the way its bow points), the point it comes in from, the longest hull it takes, who may use it. */
	struct FDock
	{
		FVector P = FVector::ZeroVector;
		FVector Dir = FVector::ForwardVector;
		FVector Approach = FVector::ZeroVector;
		float MaxLen = 400.f;
		uint32 Roles = 0;                        // bits of RoleBit; 0: any
	};

	/** A part of a place that moves (the control ring of Keeper Station, a crane): its own mesh, turning about an axis through a pivot. */
	struct FPart
	{
		FString Mesh;
		FVector Pivot = FVector::ZeroVector;     // metres, the place's mesh frame
		FVector Axis = FVector::ForwardVector;
		float PeriodS = 600.f;                   // a full turn (negative: the other way); 0: it does not turn
		float Phase = 0.f;                       // fraction of a turn at the start
		float SwingDeg = 0.f;                    // > 0: it swings this far either way (a crane's slew) instead of turning round
		TArray<FLamp> Lamps;                     // its own lamps (the part's mesh frame: they turn with it)
	};

	/** What the generator says of a mesh, per mesh name (data/space/meshes.json: written by art/blender/spacegen3.py and copied by tools/space.py sync). */
	struct FMeshData
	{
		FString Mesh;
		FVector Min = FVector::ZeroVector, Max = FVector::ZeroVector;      // the bounds, metres, the mesh's frame
		float Length = 100.f;
		TArray<FLamp> Lamps;
		TArray<FBell> Bells;
		TArray<FDock> Docks;
		TArray<FVector> Holds;                   // where a hull waits for a berth (metres, the mesh's frame)
		TArray<FPart> Parts;
		FVector Flare = FVector::ZeroVector;     // a refinery's flare stack tip (zero: none)
		float FlareLenM = 0.f;
	};

	// ------------------------------------------------------------------------------------------------------------------ hulls
	/** A civilian hull: the meshes it comes in (variants of one design), how it flies, what it is called. */
	struct FHullDef
	{
		FName Key;
		FString Class;                           // what the plot calls it ("Free Guilds freighter")
		ERole Role = ERole::Freight;
		TArray<FString> Meshes;                  // the variants
		float Length = 300.f, Radius = 150.f;    // m
		float Cruise = 140.f, Accel = 3.f;       // m/s, m/s^2
		float TurnDeg = 2.f;                     // deg/s
		float Weight = 1.f;                      // how common in the mix
		bool bAmber = false;                     // the drive's plume: false blue-white (the ASTRA's), true amber
		TArray<FString> Names;                   // ship names
		TArray<FString> Companies;
		float HullKm = 0.f;                      // how far its hull is drawn (0: 350 hull radii)
	};

	// ------------------------------------------------------------------------------------------------------------------ the places and lanes of a system
	/** How a place is put in its system (the layout resolves it once the anchors are known). */
	struct FPlaceSpec
	{
		FName Id;
		FString Name;
		EPlaceKind Kind = EPlaceKind::Station;
		FString Mesh;                            // the main mesh (empty: no body: an orbit, a belt)
		FString Contact;                         // the plot's id ("K-1"); empty: not a contact
		FString Class;                           // the plot's class line
		float RadiusM = 500.f;                   // what avoidance gives it
		FString Anchor = TEXT("origin");         // gate | origin | sky
		// origin: bearing/mark/range from where the Aquila comes in. sky: Dir ("planet" | "star") turned by Yaw/Pitch, Range. gate: Gate frame (axis out of the ring, right, up), km
		double BearingDeg = 0.0, MarkDeg = 0.0, RangeKm = 50.0;
		FString Dir = TEXT("planet");
		double YawDeg = 0.0, PitchDeg = 0.0;
		FVector GatePosKm = FVector::ZeroVector;
		// how it faces: gate_axis | broadside | toward_origin | explicit (the Yaw/Pitch/Roll below as turns of the mesh frame)
		FString Face = TEXT("broadside");
		double FaceYawDeg = 0.0, FacePitchDeg = 0.0, FaceRollDeg = 0.0;
		FString Comms;                           // who answers a hail ("Keeper Station Control")
		TArray<FString> Services;
	};

	/** A lane of the traffic network: from one place to another by way of a few points (anchored like the places), with beacon buoys along it. */
	struct FViaSpec
	{
		FString Anchor = TEXT("origin");         // origin | sky | between (a fraction of the way between the two ends, pushed aside)
		double BearingDeg = 0.0, MarkDeg = 0.0, RangeKm = 30.0;
		FString Dir = TEXT("planet");
		double YawDeg = 0.0, PitchDeg = 0.0;
		double Fraction = 0.5, AsideKm = 0.0, UpKm = 0.0;
	};

	struct FLaneSpec
	{
		FName Id;
		FName From, To;
		TArray<FViaSpec> Via;
		float BuoyEveryKm = 20.f;                // 0: no buoys
		FLinearColor BuoyColor = FLinearColor(1.f, 0.62f, 0.15f);
		float LateralM = 450.f;                  // the right-hand rule: traffic keeps this far to its right of the lane's axis
	};

	/** Which tours the traffic of a system runs and how many hulls run them. */
	struct FTourSpec
	{
		FName Hull;                              // the hull key
		int32 Count = 1;
		TArray<FName> Nodes;                     // the places it calls at, in turn (the cycle repeats); "gate" means out through the Gate and back some time later
		FVector2D DwellMin = FVector2D(180.0, 420.0);   // seconds docked at each call: min, max
	};

	struct FPatrolSpec
	{
		FName Node;                              // the place it flies round
		int32 Craft = 4;                         // hulls in the flight
		float RadiusKm = 6.f;                    // the racetrack's size
		float SpeedMps = 160.f;
		FString Mesh = TEXT("SM_CRAFT_ASTRA_Falcon");
		FString Formation = TEXT("wedge");       // wedge | echelon | diamond | line
	};

	struct FRockSpec
	{
		bool bOn = false;
		double BearingMinDeg = 120.0, BearingMaxDeg = 210.0;     // the arc of the belt seen from where the Aquila comes in
		double RangeMinKm = 190.0, RangeMaxKm = 250.0;
		double MarkSpreadDeg = 5.0;
		int32 Count = 520;
		TArray<FString> Meshes;
		FVector2D SizeM = FVector2D(90.0, 2200.0);               // the smallest and the largest, a long tail of small ones
	};

	/** A system's space: places, lanes, tours, belts. Systems without one use the generic spec (a Gate and its Keeper Station, a few buoys, sparse traffic). */
	struct FSystemSpec
	{
		FString Name;
		TArray<FPlaceSpec> Places;
		TArray<FLaneSpec> Lanes;
		TArray<FTourSpec> Tours;
		TArray<FPatrolSpec> Patrols;
		FRockSpec Rocks;
		float Density = 1.f;                     // traffic scale (1 = as listed)
	};

	/** Everything read from data/space: the hulls, the meshes' data and the systems' specs. One instance for the game (Data()). */
	struct FDataSet
	{
		TMap<FName, FHullDef> Hulls;
		TMap<FString, FMeshData> Meshes;
		TMap<FString, FSystemSpec> Systems;      // by system name (lowercase); "_generic" for the rest
		bool bLoaded = false;
		FString Source;

		const FHullDef* Hull(FName Key) const { return Hulls.Find(Key); }
		const FMeshData* Mesh(const FString& Name) const { return Meshes.Find(Name); }
		/** The spec of a system by name, else the generic one. */
		const FSystemSpec* System(const FString& Name) const;
		/** Parses the three documents (hulls and systems in one: space.json; meshes.json). False when space.json does not parse. */
		bool Parse(const FString& SpaceJson, const FString& MeshesJson, FString& OutError);
	};

	/** The game's data set, loaded once from Content/ASTRA/Data/space (the staged copy) or data/space (the source). */
	ASTRA_API const FDataSet& Data();
	/** Reloads it from disk (the console's astra.space.reload; the bench). */
	ASTRA_API void ReloadData();

	// ------------------------------------------------------------------------------------------------------------------ one system, laid out
	/** Where things are in the system frame once the anchors are known. */
	struct FAnchors
	{
		FVector Origin = FVector::ZeroVector;                   // where the Aquila comes in
		FVector PlanetDir = FVector(0.941, 0.145, -0.307);      // unit, system frame: where the main world lies in the sky
		FVector StarDir = FVector(0.3, 0.6, 0.4);               // unit
		bool bGate = false;
		FVector GatePos = FVector::ZeroVector;
		FQuat GateAtt = FQuat::Identity;                        // +X out of the ring on the side the system's traffic uses (towards the Aquila)
		float GateRadiusM = 8000.f;
		float LaneEntryKm = 25.f;                               // where the Gate's field takes a ship (the battle's lane)
	};

	struct FSlot
	{
		FVector Pos = FVector::ZeroVector;                      // system frame: the centre of a hull as long as MaxLen (its bow at the pier's collar)
		FQuat Att = FQuat::Identity;
		FVector Approach = FVector::ZeroVector;
		float MaxLen = 400.f;
		uint32 Roles = 0;
		int32 Occupant = INDEX_NONE;                            // a vessel's id: it lies here
		int32 Reserved = INDEX_NONE;                            // a vessel's id: it is coming

		/** Where the centre of a hull of this length lies in the berth: every hull comes in bow first and its bow always meets the pier's collar, so a shorter hull lies
		 *  further out along the berth's axis than a long one. */
		FVector CentreFor(float Length) const
		{
			return Pos + Att.GetForwardVector() * (double)(FMath::Max(0.f, MaxLen - Length) * 0.5f);
		}
	};

	/** A place as the traffic knows it. */
	struct FNode
	{
		FName Id;
		FString Name;
		EPlaceKind Kind = EPlaceKind::Station;
		FVector Pos = FVector::ZeroVector;
		FQuat Att = FQuat::Identity;
		float RadiusM = 500.f;
		FVector Entry = FVector::ZeroVector;                    // where lanes meet it (a point clear of the structure, on the side the lanes come from)
		TArray<FSlot> Slots;
		TArray<FVector> Holds;                                  // waiting points (system frame)
		TArray<int32> HoldTaken;                                // a vessel's id for each, or INDEX_NONE
		const FPlaceSpec* Spec = nullptr;
		const FMeshData* Mesh = nullptr;
		bool bClosed = false;                                   // closed to traffic (an alert)
		int32 Alert = 0;
		double GateNextFree = 0.0;                              // the Gate: the battle time when it takes the next vessel
	};

	struct FLane
	{
		FName Id;
		int32 A = INDEX_NONE, B = INDEX_NONE;                   // node indices
		TArray<FVector> Pts;                                    // from A's entry to B's entry, system frame
		float LengthM = 0.f;
		float LateralM = 450.f;
		FLinearColor BuoyColor = FLinearColor(1.f, 0.62f, 0.15f);
		TArray<FVector> Buoys;
	};

	struct FRock
	{
		FVector Pos = FVector::ZeroVector;
		FQuat Att = FQuat::Identity;
		float SizeM = 100.f;
		int32 Mesh = 0;
	};

	struct FLayout
	{
		FString System;
		FAnchors Anchors;
		const FSystemSpec* Spec = nullptr;
		TArray<FNode> Nodes;
		TArray<FLane> Lanes;
		TArray<FRock> Rocks;
		int32 GateNode = INDEX_NONE;
		int32 KeeperNode = INDEX_NONE;
		int32 OrbitNode = INDEX_NONE;

		int32 FindNode(FName Id) const;
		/** The lane between two nodes (either way): its index and whether it runs A to B as asked. */
		int32 FindLane(int32 From, int32 To, bool& bForward) const;
		/** A direction in the system frame from a bearing and a mark (the battle's helm convention: degrees, the bearing about +Z from +X, the mark up from the plane). */
		static FVector Polar(double RangeM, double BearingDeg, double MarkDeg);
	};

	/** Resolves a system's spec against its anchors: each place's pose, its berths in the system frame, the lanes' points and buoys, the rocks. Deterministic (the spec,
	 *  the anchors and the seed decide). */
	void BuildLayout(const FSystemSpec& Spec, const FDataSet& Set, const FAnchors& A, uint32 Seed, FLayout& Out);
}
