// ASTRA — the civilian traffic of a system (SPAZIO-VIVO, docs/SPAZIO.md): freighters, tankers, liners, tugs and ore barges that live between the places of the system
// (the Arsenal's docks, Keeper Station, the refineries of Tiberius, the Gate, the orbit of the main world, the belt's mines), and the patrols that fly round them.
//
// A few hundred bytes a vessel and nothing drawn here: the core is plain C++ in the battle's system frame, deterministic for a seed and a step, so that the bench
// (AstraSpaceLifeSimCommandlet) can run hours of it in seconds, check the routes, the queues at the Gate, the reactions to a war and what a tick costs. The drawing
// (AstraSpaceLifeDraw.cpp) reads the vessels as they stand.
//
// A vessel keeps a tour (the places it calls at, in turn). At each it lies in a berth for a few minutes, backs out, flies the lane to the next place on the
// right-hand side of the lane, slows, waits for a berth if there is none, eases in. A tour that includes the Gate goes out through the ring (the Gate takes one
// vessel at a time) and comes back, from the same ring, some minutes later; when the Gate is closed (the Aquila's transit, an alert) the vessels queue on the lane.
// When hostile warships come near, they react: they divert, run for the berths of the Arsenal or Keeper Station, hide dark, and call for help (an event for the
// sensors and the comms: the space reacts).

#pragma once

#include "CoreMinimal.h"
#include "AstraSpaceLifeData.h"

namespace AstraSpace
{
	enum class EVState : uint8
	{
		Docked,        // lying in a berth
		Departing,     // backing out of a berth, then turning for the lane
		Cruise,        // under way along its route
		Docking,       // easing into a berth
		Holding,       // waiting at a holding point (for a berth, or for the Gate)
		GateOut,       // running through the ring: it is gone when it gets there
		GateIn,        // just out of the ring, braking along the lane
		Away,          // beyond the Gate: not in the system until ReturnAt
		Fleeing,       // running from a danger
		Hiding,        // dark and drifting
		Tending,       // a tug on station beside a hulk it was sent to (docs/SPAZIO.md §14)
		Num
	};
	const TCHAR* StateName(EVState S);

	struct FVessel
	{
		int32 Id = 0;
		FName Hull;
		int32 MeshIdx = 0;                       // which variant of the hull
		FString Name;
		FString Company;
		uint32 Seed = 0;
		EVState State = EVState::Docked;
		float StateT = 0.f;                      // seconds in this state
		FVector Pos = FVector::ZeroVector, Vel = FVector::ZeroVector;
		FQuat Att = FQuat::Identity;
		float Thrust = 0.f;                      // 0..1, smoothed: what the plume shows
		bool bLit = true;                        // its lamps and windows (a hiding vessel is dark)
		// the tour
		TArray<int32> Tour;
		int32 TourIdx = 0;                       // the node it is at, or on its way to
		FVector2D Dwell = FVector2D(180.0, 420.0);
		float DwellLeft = 0.f;
		// the route
		TArray<FVector, TInlineAllocator<12>> Route;
		int32 RouteIdx = 0;
		int32 Node = INDEX_NONE;                 // the node it is docked at, or bound for
		int32 Slot = INDEX_NONE;                 // its berth there (held or reserved)
		int32 Hold = INDEX_NONE;                 // its waiting point there
		FVector DockApproach = FVector::ZeroVector;
		FVector DockPos = FVector::ZeroVector;   // the berth it is leaving: where it was, and the way it backs out
		FVector DockBack = FVector::ForwardVector;
		float LateralM = 0.f, VertM = 0.f;       // where it keeps in a lane
		double ReturnAt = 0.0;
		// the reaction
		uint8 Alert = 0;                         // 0 none, 1 diverting, 2 fleeing, 3 hiding
		float AlertT = 0.f;                      // seconds since it first took the alert (grows), or since danger was last near
		float CalmT = 0.f;                       // seconds without danger near
		bool bCalled = false;                    // it has called for help in this alert
		float DangerKm = -1.f;                   // how far the nearest hostile is (-1: none seen)
		FVector DangerDir = FVector::ZeroVector; // where it lies from the vessel (unit)
		float ThinkT = 0.f;
		// the convoy it runs with (docs/SPAZIO.md §14): its column, and what it flies at to keep it
		int32 Convoy = INDEX_NONE;               // an index in the traffic's convoys
		int32 ConvoyRank = 0;                    // its place in the column (0 the head)
		float GapScale = 1.f;                    // how fast it flies against its class's cruise: it closes up on the hull ahead (above 1) or eases back from it (below)
		// what it has slowed to look at (a wreck, a hulk), and when it last did, so that it does not look twice
		int32 Look = INDEX_NONE;                 // the interest it is looking at (FInterest::Key)
		float LookT = 0.f;                       // how long (s)
		int32 LastLook = INDEX_NONE;
		double LastLookAt = -1.0e9;
		// a tug sent to a hulk
		int32 TendKey = INDEX_NONE;              // the interest it was sent to (FInterest::Key)
		float TendT = 0.f;                       // how long it has been on station (s)
		FVector TendOffset = FVector::ZeroVector;// where it lies about the hulk (metres, a fixed direction: it does not circle)
	};

	/** A flight of patrol craft flying a racetrack round a place, in formation: elegant and cheap (a leader on a curve, wingmen on springs). */
	struct FPatrolCraft
	{
		FVector Pos = FVector::ZeroVector, Vel = FVector::ZeroVector;
		FQuat Att = FQuat::Identity;
		float Bank = 0.f;                        // radians, smoothed
		bool bLit = true;
	};

	struct FPatrol
	{
		int32 Id = 0;
		int32 Node = INDEX_NONE;
		FString Mesh;
		TArray<FPatrolCraft> Craft;              // [0] the leader
		TArray<FVector> Slots;                   // formation offsets in the leader's frame (metres)
		FVector Centre = FVector::ZeroVector;
		FQuat Tilt = FQuat::Identity;            // the racetrack's plane
		float RadiusM = 6000.f, SpeedMps = 160.f;
		double Phase = 0.0;                      // radians along the track
		uint8 State = 0;                         // 0 flying, 1 recalled (running for the berths), 2 away (back after the calm; an escort: in port, no convoy under way), 3 taken by the war (the flight is its own)
		float AwayT = 0.f;
		float Scale = 1.f;                       // the craft's size (the mesh's own: a tug is not a Falcon)
		int32 Convoy = INDEX_NONE;               // an escort: the convoy it flies cover for (it is made with the convoy and flies round the hulls of it that are under way)
		float RebuildS = 0.f;                    // lost to the war: seconds until a new flight takes its place
		int32 Complement = 0;                    // how many craft it was made with (a flight that comes back from the war short is made whole again after a rest)
		FString NodeName;                        // the place it flies from, for what the crew is told ("the Arsenal patrol")
	};

	/** What the traffic needs of the world each step: the hostiles to run from, what to keep clear of, whether the Gate is in use. */
	struct FHostile
	{
		FVector Pos = FVector::ZeroVector;
		FVector Vel = FVector::ZeroVector;
		bool bCraft = false;
	};

	struct FObstacle
	{
		FVector Pos = FVector::ZeroVector;
		float RadiusM = 100.f;
	};

	/** Something worth a look as the traffic passes: a wreck (what is left of a ship the war broke, with lifepods adrift near it perhaps) or a hulk nobody has in tow. A vessel on a lane that comes near slows to look and says so;
	 *  for a hulk the yard sends a tug. The living space makes the list from what the war has left (UAstraSpaceLife::ReadWorld). */
	struct FInterest
	{
		int32 Key = 0;                           // what it is (a wreck site, a ship): the traffic remembers what it has looked at by this
		uint8 Kind = 0;                          // 0 a wreck, 1 a hulk
		FVector Pos = FVector::ZeroVector, Vel = FVector::ZeroVector;
		float RadiusM = 300.f;
		float AgeS = -1.f;                       // how long ago it came to be, where that is known (a wreck: since she was lost); -1 not known
		int32 Pods = 0;                          // lifepods adrift near it with air left
		FString Name;                            // "ASN Vigilant"
		FString What;                            // "the wreck of ASN Vigilant (her hull broke apart)", "the hulk of the Mandate frigate Brightwater Two (T-11)"
	};

	struct FWorldView
	{
		FVector Aquila = FVector::ZeroVector;
		FVector AquilaVel = FVector::ZeroVector;
		float AquilaRadiusM = 420.f;
		TArray<FHostile> Hostiles;
		TArray<FObstacle> Obstacles;
		TArray<FInterest> Interests;
		bool bGateBusy = false;                  // the Aquila's own transit has the lane
		bool bEngagement = false;
	};

	enum class EEventKind : uint8
	{
		GatePulse,     // a vessel went through the ring (or came out): the Gate flares a little
		GateClosed,    // Keeper Station closes the Gate to civilian traffic
		GateOpen,
		Mayday,        // a vessel calls for help
		Scatter,       // the traffic is clearing the area
		Resume,        // the traffic goes back to its routes
		// what the war leaves (AstraWrecks.h)
		Beacon,        // the beacons of lifepods are heard
		BeaconSilent,  // the beacons of a wreck's lifepods have gone silent (the air ran out)
		WreckLook,     // a close look at a wreck
		Rescue,        // lifepods taken aboard
		Derelict,      // a hulk left behind is found again
		// the traffic's own life (docs/SPAZIO.md §14)
		Look,          // a passing vessel slows to look at a wreck or a hulk
		Tug,           // a yard tug is sent to a hulk, is on station, goes home
		Convoy,        // a convoy comes out of the Gate, is in port
		Patrol         // a patrol is released to the war, or comes home from it
	};

	struct FEvent
	{
		EEventKind Kind = EEventKind::Scatter;
		FString Text;                            // what the sensors or the comms say (empty for a pulse)
		bool bReport = false;                    // worth telling the Captain (the crew's turn)
		FVector At = FVector::ZeroVector;        // system frame
		int32 Vessel = INDEX_NONE;
		float Strength = 1.f;
	};

	/** The numbers the bench and the console read. */
	struct FTrafficStats
	{
		int32 Vessels = 0;
		int32 ByState[(int32)EVState::Num] = {};
		int32 QueueGate = 0;                     // vessels waiting for the Gate
		int32 Docked = 0, InFlight = 0, Away = 0;
		int32 Alerted = 0;
		int32 GateOutTotal = 0, GateInTotal = 0; // since the start
		int32 DockedTotal = 0, DepartedTotal = 0;
		int32 Maydays = 0;
		float MaxQueue = 0.f;
		double TickMs = 0.0, TickMsMax = 0.0;
		int32 Ticks = 0;
		// the traffic's own life (docs/SPAZIO.md §14)
		int32 Convoys = 0, ConvoyHulls = 0, ConvoysCame = 0;       // convoys in the system, the hulls in them, the times one has come out of the Gate (a convoy's first hull)
		int32 Looking = 0, LooksTotal = 0;                          // vessels slowed to look at something now, and the looks there have been
		int32 TugsSent = 0, Tending = 0, TugsHome = 0;              // tugs sent to a hulk, on station now, gone home again
		int32 EscortsFlying = 0;                                    // convoy escorts' craft drawn now
		float MaxColumnGapKm = 0.f;                                 // the longest gap between two hulls of a convoy on the lane in from the Gate (more than 40 s out of the ring), at the end of the last think
		float MinColumnGapKm = 1.0e6f;                              // the shortest gap there has been between two such hulls, at any time (the bench's checks that a column forms and that no hull is run into)
	};

	/** A convoy: its hulls (head first), what flies cover, when it next comes out of the Gate. */
	struct FConvoy
	{
		int32 Index = 0;
		FString Name;                            // "GC-1"
		FName Hull;
		TArray<int32> Members;                   // vessel ids, head first
		int32 Patrol = INDEX_NONE;               // the escort's flight (an index in the traffic's patrols)
		double NextAt = 0.0;                     // when it next comes out of the Gate (the clock): its hulls follow one by one
		double FirstAwayAt = -1.0;               // when the first hull of this round went beyond the Gate (-1: none has): the others are waited for, but not for ever
		FVector2D PeriodS = FVector2D(900.0, 1500.0);
		float GapM = 1400.f;
		bool bToldOut = false;                   // the crew has been told it is coming (reset when all its hulls are beyond the Gate again)
		bool bToldBerthed = false;               // ... and that it is in
		FString Where;                           // where it is bound ("Keeper Station and the Arsenal"), for what the crew is told
	};

	/** What the traffic keeps of something it may look at (a wreck, a hulk): since when it has been there, who was sent, how many looks. */
	struct FInterestState
	{
		double FirstSeen = 0.0;
		double LastToldAt = -1.0e9;
		int32 TugId = INDEX_NONE;                // the tug sent to it (a vessel's id)
		bool bTugDone = false;                   // a tug has been to it and gone: no second
		int32 Looks = 0;
		int32 Frame = 0;                         // the think it was last in the view (what is not any more is forgotten)
	};

	class ASTRA_API FTraffic
	{
	public:
		/** Makes the vessels of a layout's tours (Density scales their number) and the patrols. The layout must outlive the traffic. */
		void Init(const FDataSet& Set, FLayout& Layout, uint32 Seed, double Now, float Density);
		/** Runs the traffic forward without reporting (a system entered: the lanes are already busy; the bench). View: what it sees as it goes (default: a quiet system: no hostiles, nothing to look at); Events: where
		 *  what it would have said is kept (default: dropped). */
		void Warmup(double Seconds, double Step = 1.0, const FWorldView* View = nullptr, TArray<FEvent>* Events = nullptr);
		/** One step: Dt seconds of game time (the battle's clock reads Now). */
		void Tick(double Now, float Dt, const FWorldView& View, TArray<FEvent>& Out);
		void Reset();

		const TArray<FVessel>& Vessels() const { return Vs; }
		const TArray<FPatrol>& Patrols() const { return Ps; }
		const TArray<FConvoy>& Convoys() const { return Cs; }
		/** The traffic's clock (the battle's time at its last step). */
		double TimeNow() const { return Clock; }
		const FTrafficStats& Stats() const { return St; }
		/** The war takes a patrol (a flight that is flying: not an escort that is in port, not one already taken): it leaves the traffic and its craft are handed over as they are (where, how fast, which way they point), so
		 *  that the war can make real craft of the plot of them without a jump. False when it cannot be taken (the reason in OutWhy). The flight is the war's until it is given back. */
		bool TakePatrol(int32 PatrolId, TArray<FPatrolCraft>& OutCraft, FString& OutMesh, float& OutScale, FString* OutWhy = nullptr);
		/** The war gives the flight back: Survivors craft (0: none) are made a flight again at the place it flew from after a rest; a flight that lost everyone is made new after twenty minutes. */
		void GivePatrolBack(int32 PatrolId, int32 Survivors);
		/** What a patrol is, for whoever may pull it in: its id, where it flies, how many craft, what state. */
		int32 PatrolIndex(int32 PatrolId) const;
		int32 AlertLevel() const { return SystemAlert; }
		/** The state as a short text, for the console and the bench. */
		FString Describe() const;
		/** Ships clear of a place when it is told to (a place under attack: its berths are not used). */
		void SetNodeClosed(int32 Node, bool bClosed);

	private:
		const FDataSet* Set = nullptr;
		FLayout* L = nullptr;
		TArray<FVessel> Vs;
		TArray<FPatrol> Ps;
		TArray<FConvoy> Cs;
		TMap<int32, FInterestState> Seen;        // by FInterest::Key
		int32 ThinkFrame = 0;
		FTrafficStats St;
		FRandomStream Rng;
		double Clock = 0.0;
		float ThinkAcc = 0.f;
		float ThinkDt = 0.2f;                    // the time since the vessels last thought
		int32 NextId = 1;
		int32 SystemAlert = 0;                   // 0 calm, 1 alert (hostiles within the system's lanes), 2 lockdown (hostiles at the Gate or near a place)
		double AlertSince = -1.0;
		double LastDanger = -1e9;
		double LastMayday = -1e9;
		double LastScatter = -1e9;
		bool bGateWasClosed = false;
		TSet<FString> UsedNames;
		TArray<int32> GateQueue;                 // ids, in the order they came

		// ---- making
		FVessel MakeVessel(const FTourSpec& T, int32 Index);
		bool PlaceAtStart(FVessel& V);
		void MakePatrols();
		void MakeConvoys();
		// ---- the traffic's own life (docs/SPAZIO.md §14)
		FVessel* FindVessel(int32 Id);
		const FInterest* FindInterest(const FWorldView& View, int32 Key) const;
		/** A vessel that takes the alert gives up what it was doing for the traffic's own life: the look, the tug's errand (another tug may be sent later). */
		void DropTasks(FVessel& V);
		void FlyTrack(FPatrol& P, float Dt);
		/** Slows what passes a wreck or a hulk to look, says so; sends a tug to a hulk nobody has in tow. */
		void ThinkInterests(double Now, const FWorldView& View, TArray<FEvent>& Out);
		void SendTug(FVessel& V, const FInterest& I, double Now, const FWorldView& View, TArray<FEvent>& Out);
		void SendTugHome(FVessel& V, double Now, TArray<FEvent>& Out, bool bTold);
		/** A convoy's hulls under way, their middle and how fast they go: where its escort flies. False when none is. */
		bool ConvoyMiddle(const FConvoy& C, FVector& OutPos, FVector& OutVel, int32& OutFlying) const;
		void ThinkConvoys(double Now, const FWorldView& View, TArray<FEvent>& Out);
		void TickEscort(FPatrol& P, float Dt, double Now, const FWorldView& View);
		/** The convoy a vessel that has just gone beyond the Gate belongs to has its next coming out of the ring at a time of its own, its hulls following one by one. */
		void ConvoyGoneAway(FVessel& V, double Now);
		FString PickName(const FHullDef& H, FRandomStream& R);
		// ---- routes and berths
		/** The index in its tour of the call it goes to from here: the next of the tour, or (docked at a refuge) the one it never reached. */
		int32 NextIdx(const FVessel& V) const;
		bool TryDepart(FVessel& V, double Now, TArray<FEvent>& Out);
		void BuildRoute(FVessel& V, const FVector& From, int32 FromNode, int32 ToNode);
		int32 ClaimSlot(FVessel& V, int32 Node);
		void FreeSlot(FVessel& V);
		int32 ClaimHold(FVessel& V, int32 Node);
		void FreeHold(FVessel& V);
		void ArriveAtNode(FVessel& V, double Now, TArray<FEvent>& Out);
		void SetState(FVessel& V, EVState S) { V.State = S; V.StateT = 0.f; }
		// ---- the step
		void Think(FVessel& V, double Now, const FWorldView& View, TArray<FEvent>& Out);
		void Integrate(FVessel& V, float Dt, const FWorldView& View);
		void ThinkGate(double Now, const FWorldView& View, TArray<FEvent>& Out);
		void ThinkDanger(double Now, const FWorldView& View, TArray<FEvent>& Out);
		void ReactTo(FVessel& V, double Now, const FWorldView& View, TArray<FEvent>& Out);
		int32 PickRefuge(const FVessel& V, float ClearKm) const;
		void TickPatrols(float Dt, double Now, const FWorldView& View);
		void Avoid(FVessel& V, const FWorldView& View, FVector& InOutAccel) const;
		const FHullDef* HullOf(const FVessel& V) const { return Set->Hull(V.Hull); }
		/** The length of a vessel's hull (what a berth needs to place it: its bow meets the pier's collar). */
		float HullLen(const FVessel& V) const { const FHullDef* H = HullOf(V); return H ? H->Length : 0.f; }
		FString Where(const FVector& From, const FVector& P) const;
		void RebuildStats();
	};
}
