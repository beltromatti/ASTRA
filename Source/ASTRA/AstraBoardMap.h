// ASTRA — ABBORDAGGI: the Aquila's plan as soldiers see it (docs/ABBORDAGGI.md).
//
// A fight inside the ship is fought in corridors and rooms, through doors and round corners: what a soldier needs of the plan is where he can go,
// what he can see from where he stands and where he can hide. The plan's compartments tile the ship in boxes that share faces; the faces are open
// (a corridor going on), a door, a section's pressure bulkhead, a stair or a lift. From those faces this map makes:
//
//   - PORTALS: every opening between two compartments, with its place, its width and its way, and (for a door) its index in the damage map
//     (a door shuts when it is sealed and opens when someone stands at it);
//   - a route over the portals (A*: the compartments are convex boxes, so the way across one is a straight line), with the cost of a flank;
//   - the line of sight: a ray that crosses a face is stopped unless it goes through an open door or an open stretch of corridor;
//   - SLOTS: the corners beside each doorway and junction, where a man can stand out of the line of fire and step out to shoot.
//
// Plain code (no actors, no world): the squad AI (AstraBoardSim.*) stands on it, so it can be tested headless on the real plan
// (AstraBoardSimCommandlet). It borrows the damage model's map (AstraDamageMap.*) for the boxes, the doors and the grid that finds a
// compartment at a point, and keeps its own copy of what it needs of them.

#pragma once

#include "CoreMinimal.h"
#include "AstraDamageMap.h"

/** A way between two compartments. */
struct FBoardPortal
{
	enum class EKind : uint8 { Open, Door, Blast, Stair, Lift };

	EKind Kind = EKind::Open;
	int32 A = INDEX_NONE, B = INDEX_NONE;     // the compartments either side
	int32 Door = INDEX_NONE;                  // the damage map's door, for Door and Blast
	FVector Pos = FVector::ZeroVector;        // the middle of the opening on the floor (cm); stairs and lifts: where it is in A
	FVector PosB = FVector::ZeroVector;       // stairs and lifts: where it comes out in B (another deck); else the same as Pos
	FVector2D Along = FVector2D(1.0, 0.0);    // unit: along the opening (the wall's direction)
	FVector2D Normal = FVector2D(0.0, 1.0);   // unit: through the opening, from A to B
	float Half = 80.f;                        // half the opening's width (cm)
	float ExtraCost = 0.f;                    // what a stair or a lift adds to the way (cm of walking)
	bool bVertical() const { return Kind == EKind::Stair || Kind == EKind::Lift; }
	bool bDoor() const { return Kind == EKind::Door || Kind == EKind::Blast; }
	int32 Other(int32 Comp) const { return Comp == A ? B : A; }
	const FVector& PosIn(int32 Comp) const { return Comp == A ? Pos : PosB; }
};

/** A compartment as the soldiers use it. */
struct FBoardComp
{
	FBox Box = FBox(ForceInit);               // cm
	int16 Deck = 0;
	TCHAR Section = TEXT('A');
	bool bCorridor = false;
	bool bHall = false;
	FName Kind;
	TArray<int32> Portals;                    // indices into the map's portals
	TArray<int32> Slots;                      // indices into the map's slots
	float FloorZ() const { return (float)Box.Min.Z; }
};

/** A place beside an opening where a man is out of the line through it, and the step he takes to see through it. */
struct FBoardSlot
{
	FVector Pos = FVector::ZeroVector;        // where he waits (cm, on the floor)
	FVector Peek = FVector::ZeroVector;       // where he stands to shoot through the opening
	int32 Comp = INDEX_NONE;
	int32 Portal = INDEX_NONE;
	FVector2D Out = FVector2D(0.0, 1.0);      // the way the opening looks from here (unit): into the line he hides from
};

/** The state of the doors and the stairs, as the fight keeps it: whether each door of the damage map lets a ray and a man through now. */
struct FBoardDoors
{
	TBitArray<> Open;                         // by the damage map's door index: standing open (someone is at it)
	TBitArray<> Sealed;                       // shut for good (a pressure bulkhead, a lockdown): nobody passes
	void Init(int32 NumDoors) { Open.Init(false, NumDoors); Sealed.Init(false, NumDoors); }
	bool IsOpen(int32 Door) const { return Door == INDEX_NONE || (Open.IsValidIndex(Door) && Open[Door] && !Sealed[Door]); }
	bool IsSealed(int32 Door) const { return Door != INDEX_NONE && Sealed.IsValidIndex(Door) && Sealed[Door]; }
};

/** What a route may do. */
struct FBoardRouteOptions
{
	bool bThroughSealed = false;              // breach a sealed door (cut through it: takes time)
	float SealedCost = 4000.f;                // ... and what that costs
	bool bStairs = true;                      // may use stairs
	const TArray<float>* PortalPenalty = nullptr;   // extra cost (cm) per portal: a flank avoids the portals the enemy covers
	const FBoardDoors* Doors = nullptr;       // sealed doors stop a route
};

class ASTRA_API FAstraBoardMap
{
public:
	/** Builds the map from the damage model's (it must stay alive: the map borrows its grid). Returns false when it has no compartments. */
	bool Build(TSharedRef<const FAstraDamageMap> Src);
	bool IsReady() const { return Comps.Num() > 0; }

	const TArray<FBoardComp>& GetComps() const { return Comps; }
	const TArray<FBoardPortal>& GetPortals() const { return Portals; }
	const TArray<FBoardSlot>& GetSlots() const { return Slots; }
	const FAstraDamageMap& Source() const { return *Src; }
	int32 NumDoors() const { return Src->Doors.Num(); }

	/** The compartment a point (cm) is in (a few cm of slack at the walls), or INDEX_NONE. A man's feet are on the floor, which is also the ceiling of the
	 *  deck below (the decks' pitch is the height of a deck): the point is lifted 60 cm off the floor first (an eye or a chest is lifted too, harmlessly) and the
	 *  slack is kept small so that it never reaches into the deck below. */
	int32 CompAt(const FVector& P, float SlackCm = 25.f) const { return Src->CompartmentAt(P + FVector(0.0, 0.0, 60.0), FMath::Min(SlackCm, 30.f)); }

	/** Whether a soldier's eye at A sees a point B (cm): the ray stays in the compartments and crosses faces only where they are open. Doors
	 *  count as they are in Doors (null: every door open). Stairs, lifts and different decks never see each other. */
	bool Visible(const FVector& A, const FVector& B, const FBoardDoors* Doors = nullptr, int32 ForceOpenDoor = INDEX_NONE) const;

	/** A way from one point to another (cm): the points to walk through, From first and To last. OutComps (optional) is the compartment of each
	 *  leg: leg i runs from Out[i] to Out[i+1] inside OutComps[i]. OutMetres is its length. False when there is none. */
	bool Route(const FVector& From, const FVector& To, TArray<FVector>& Out, const FBoardRouteOptions& Opt, float* OutMetres = nullptr, TArray<int32>* OutComps = nullptr) const;

	/** The portals a route from One to Other would pass through, in order (for the flank's penalties and the chokepoints). */
	bool RoutePortals(const FVector& From, const FVector& To, TArray<int32>& OutPortals, const FBoardRouteOptions& Opt) const;

	/** Where a door (the damage map's index) is as a portal, or INDEX_NONE. */
	int32 PortalOfDoor(int32 Door) const { return DoorPortal.IsValidIndex(Door) ? DoorPortal[Door] : INDEX_NONE; }
	/** The portal nearest to a point, among the compartment's own. */
	int32 NearestPortal(int32 Comp, const FVector& P) const;

	/** The compartment's centre on the floor (cm), and a spot inside it, clamped away from the walls. */
	FVector CentreOf(int32 Comp) const;
	FVector Inset(int32 Comp, const FVector& P, float MarginCm = 45.f) const;

	/** A readable place name ("deck 7 section F (Main Engineering)"). */
	FString Describe(int32 Comp) const { return Src->Describe(Comp); }

	/** The slots of a compartment hidden from a point and from which a step shows it: the places to fight a man who stands there, nearest to From first. */
	void FightingSlots(int32 Comp, const FVector& Enemy, const FVector& From, const FBoardDoors* Doors, TArray<int32>& Out) const;

	/** The boxes (cm, the plan's frame, axis aligned) of what stands in each room, the props of AstraBoardDress::MakeLayout: a spot picked with Inset is kept out of them, so nobody is placed in a crate or a
	 *  cot. Set once, when the plan is read (the lanes the soldiers walk are kept clear of the props by the layout itself). All = every room's boxes one after the other, First = where each room's begin (and one more). */
	void SetBlocks(TArray<FBox2D>&& All, TArray<int32>&& First);
	TArrayView<const FBox2D> BlocksOf(int32 Comp) const;

private:
	TArray<FBox2D> BlockAll;
	TArray<int32> BlockFirst;
	TSharedPtr<const FAstraDamageMap> Src;
	TArray<FBoardComp> Comps;
	TArray<FBoardPortal> Portals;
	TArray<FBoardSlot> Slots;
	TArray<int32> DoorPortal;                  // damage map door index -> portal
	void MakePortals();
	void MakeSlots();
};
