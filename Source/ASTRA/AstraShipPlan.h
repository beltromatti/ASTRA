// ASTRA — the ship's plan in the game (data/ship/aquila_plan.json, written by art/blender/ship_plan_gen.py; docs/NAVE.md):
// the compartments, doors and walk graph of the whole Aquila, and routes over it for anyone who walks the ship (the crew,
// damage-control teams, a guide for the Captain).
#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "AstraShipPlan.generated.h"

/** A place of the walk graph: a corridor module, a doorway, a room, a station, a stair or a lift landing. */
struct FAstraPlanNode
{
	FString Id;
	FVector Pos = FVector::ZeroVector;   // world cm (the plan's metres, same axes: the origin under the Captain's chair)
	int32 Deck = 0;
	FName Kind;                          // corridor, door_in, room, station, stair, lift, lift_core
	int32 Comp = INDEX_NONE;             // its compartment
};

/** A way between two places. */
struct FAstraPlanEdge
{
	enum class EKind : uint8 { Walk, Door, Stair, Lift };
	int32 A = INDEX_NONE, B = INDEX_NONE;
	float LenM = 0.f;
	EKind Kind = EKind::Walk;
	int32 Door = INDEX_NONE;
	float WidthM = 0.f;
	bool bBlast = false;                 // a section's pressure bulkhead: shut when the section is breached
};

struct FAstraPlanCompartment
{
	FString Id, Name, Kind, Section;
	int32 Deck = 0;
	FBox Box = FBox(ForceInit);          // world cm
	int32 Plane = 0;                     // the deck whose floor plane it stands on (an existing room's signage may say another deck)
	FName Passage;                       // a corridor's run (SPF, SBP, PP ... or a cross link's own): sections of one run are one straight view
	bool bBuilt = false;                 // modelled in the level: status "built" or "existing"
	bool bExisting = false;              // one of the rooms the level already held (bridge, Mess Hall, Berthing, Medbay, Engineering, Flight Deck ...)
	int32 FirstLamp = 0, NumLamps = 0;   // its lamps: a slice of UAstraShipPlan::GetLamps() (only the built ones have any)
};

/** A lamp of a built compartment: the plan's lights[]. The level has none of them as actors: the lamp pool (AstraLampPool.*) makes a handful
 *  of real lights out of the ones near the Captain. */
struct FAstraPlanLamp
{
	FVector Pos = FVector::ZeroVector;           // world cm
	FVector2D SizeCm = FVector2D(100.0, 30.0);   // the lit rectangle: along X, along Y
	float Lumens = 0.f;                          // as rated in the plan (for a dim ship: the pool applies its gain)
	float TempK = 5000.f;
	float RadiusCm = 1000.f;
	int32 Comp = INDEX_NONE;
	bool bRect = true;                           // else a point
	bool bShadows = false;
};

/** Where the Captain can walk to from a compartment: along a corridor into the next section (open all the way), or through a room's doorway (a door he
 *  sees through only when it opens for him, a few metres from it: the lamp pool lights a room behind a door only when he is near the door). */
struct FAstraPlanLink
{
	int32 Comp = INDEX_NONE;
	bool bDoor = false;                  // through a door (not a corridor, not an open blast door)
	FVector DoorCm = FVector::ZeroVector;   // the door's place (world cm) when bDoor
};

/** A deck: its floor, its sections along the ship and how wide it is where (the hull's envelope less the wall). */
struct FAstraPlanDeck
{
	int32 Id = 0;
	FString Name;
	float FloorZ = 0.f;                  // world cm
	struct FSection { FString Id; float X0 = 0.f, X1 = 0.f; };   // world cm, aft to fore
	TArray<FSection> Sections;
	TArray<FVector2D> HalfWidth;         // (x, half width), world cm, from the bow aft
	/** The deck's half width at x (cm; 0 outside its envelope). */
	float HalfWidthAt(float X) const;
};

struct FAstraPlanDoor
{
	FString Id, Kind;
	int32 Deck = 0;
	FVector Pos = FVector::ZeroVector;   // world cm
	float Yaw = 0.f;
	int32 A = INDEX_NONE, B = INDEX_NONE;  // the compartments either side
	bool bLocked = false;                // only for who holds the access (not the general crew)
	bool bSealed = false;                // shut by damage control (a breach beyond): nobody passes
};

UCLASS()
class ASTRA_API UAstraShipPlan : public UWorldSubsystem
{
	GENERATED_BODY()

public:
	/** The plan, read on first use; false when the file is missing (the level has only the rooms built so far). */
	bool EnsureLoaded() const;

	/** The place of the graph nearest to a point (world cm), on that deck when Deck is given (else any). */
	int32 NearestNode(const FVector& Cm, int32 Deck = INDEX_NONE) const;

	/** A route over the walk graph from one point to another (world cm): A* on the walking time, sealed doors shut, locked
	 *  ones open only with bKeys (bThroughSealed: a damage-control party in suits cycles through the hatch of a shut one, at the cost of a
	 *  short wait), stairs slower than a corridor, a lift a short wait and a quick ride. Out: the points
	 *  from the start to the goal, both included. False: no way (a sealed section, a missing plan). */
	bool FindRoute(const FVector& From, const FVector& To, TArray<FVector>& Out, float* OutMetres = nullptr, bool bKeys = false, bool bThroughSealed = false) const;

	/** The compartment a point is in (world cm), or null. */
	const FAstraPlanCompartment* CompartmentAt(const FVector& Cm) const;

	/** A door shut by damage control (a breach beyond it) or opened again. */
	void SetDoorSealed(const FString& DoorId, bool bSealed);

	/** The decks, from the bridge (1) down to the keel (12); empty without the plan. */
	const TArray<FAstraPlanDeck>& GetDecks() const { EnsureLoaded(); return Decks; }
	/** The deck a point is on (world cm: the deck whose floor is the highest under it, within a deck's height), or 0. */
	int32 DeckAt(const FVector& Cm) const;
	int32 NumNodes() const { return Nodes.Num(); }
	int32 NumEdges() const { return Edges.Num(); }
	const FAstraPlanNode* Node(int32 I) const { return Nodes.IsValidIndex(I) ? &Nodes[I] : nullptr; }

	// ---- for the lamp pool and the deck streaming (docs/NAVE.md §7bis)
	const TArray<FAstraPlanCompartment>& GetCompartments() const { EnsureLoaded(); return Comps; }
	const TArray<FAstraPlanLamp>& GetLamps() const { EnsureLoaded(); return Lamps; }
	/** Every door of the plan (the interior's self-check walks through each: astra.check.map). */
	const TArray<FAstraPlanDoor>& GetDoors() const { EnsureLoaded(); return Doors; }
	/** The index in GetCompartments() of the smallest compartment containing a point (world cm), or INDEX_NONE. */
	int32 CompartmentIndexAt(const FVector& Cm) const;
	/** The compartments next to a compartment by an open way: a corridor into the next section (cost 0) or a room's doorway (a few metres of cost). */
	const TArray<FAstraPlanLink>& CompLinks(int32 Comp) const;
	/** The decks a deck is joined to by a stair column (the flights between two towers): where the Captain can walk to from it. */
	TArray<int32> StairNeighbours(int32 Deck) const;
	/** The deck a point belongs to as far as loading goes: the floor plane of an existing room it stands in (the Flight Deck's volume crosses six
	 *  decks), else DeckAt. */
	int32 DeckOfPoint(const FVector& Cm) const;

private:
	mutable bool bTried = false;
	mutable TArray<FAstraPlanNode> Nodes;
	mutable TArray<FAstraPlanEdge> Edges;
	mutable TArray<TArray<int32>> Adjacent;      // node -> its edges
	mutable TArray<FAstraPlanCompartment> Comps;
	mutable TArray<FAstraPlanDoor> Doors;
	mutable TArray<FAstraPlanDeck> Decks;
	mutable TMap<FString, int32> DoorIndex;
	mutable TArray<FAstraPlanLamp> Lamps;
	mutable TArray<TArray<FAstraPlanLink>> Links;   // compartment -> its open neighbours
	mutable TArray<TPair<int32, int32>> StairLinks; // deck pairs joined by a stair edge

	bool Load() const;
	float EdgeCost(const FAstraPlanEdge& E, bool bKeys, bool bThroughSealed = false) const;   // metres of walking it is worth; < 0: impassable
};
