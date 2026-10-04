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
		uint8 State = 0;                         // 0 flying, 1 recalled (running for the berths), 2 away (back after the calm)
		float AwayT = 0.f;
		float Scale = 1.f;                       // the craft's size (the mesh's own: a tug is not a Falcon)
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

	struct FWorldView
	{
		FVector Aquila = FVector::ZeroVector;
		FVector AquilaVel = FVector::ZeroVector;
		float AquilaRadiusM = 420.f;
		TArray<FHostile> Hostiles;
		TArray<FObstacle> Obstacles;
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
		Resume         // the traffic goes back to its routes
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
	};

	class ASTRA_API FTraffic
	{
	public:
		/** Makes the vessels of a layout's tours (Density scales their number) and the patrols. The layout must outlive the traffic. */
		void Init(const FDataSet& Set, FLayout& Layout, uint32 Seed, double Now, float Density);
		/** Runs the traffic forward without reporting (a system entered: the lanes are already busy; the bench). */
		void Warmup(double Seconds, double Step = 1.0);
		/** One step: Dt seconds of game time (the battle's clock reads Now). */
		void Tick(double Now, float Dt, const FWorldView& View, TArray<FEvent>& Out);
		void Reset();

		const TArray<FVessel>& Vessels() const { return Vs; }
		const TArray<FPatrol>& Patrols() const { return Ps; }
		const FTrafficStats& Stats() const { return St; }
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
