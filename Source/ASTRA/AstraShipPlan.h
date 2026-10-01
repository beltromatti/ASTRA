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
	 *  ones open only with bKeys, stairs slower than a corridor, a lift a short wait and a quick ride. Out: the points
	 *  from the start to the goal, both included. False: no way (a sealed section, a missing plan). */
	bool FindRoute(const FVector& From, const FVector& To, TArray<FVector>& Out, float* OutMetres = nullptr, bool bKeys = false) const;

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

private:
	mutable bool bTried = false;
	mutable TArray<FAstraPlanNode> Nodes;
	mutable TArray<FAstraPlanEdge> Edges;
	mutable TArray<TArray<int32>> Adjacent;      // node -> its edges
	mutable TArray<FAstraPlanCompartment> Comps;
	mutable TArray<FAstraPlanDoor> Doors;
	mutable TArray<FAstraPlanDeck> Decks;
	mutable TMap<FString, int32> DoorIndex;

	bool Load() const;
	float EdgeCost(const FAstraPlanEdge& E, bool bKeys) const;   // metres of walking it is worth; < 0: impassable
};
