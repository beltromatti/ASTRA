// ASTRA — ABBORDAGGI-3: the dressing of the decks of a boarded ship (docs/ABBORDAGGI.md, "I ponti abbordati").
//
// AstraBoardInterior makes a ship's plan solid: floors, walls with the gaps of their doors, frames, the leaves of the pressure bulkheads. This is what stands on and in those boxes so that a boarded ship
// reads as a warship of her side and not as a plain set of rooms: the Kharon Mandate's heavy plating in bays between ribs, copper pipes and cable trays under the ceiling, caged lamps, diamond plate and
// hazard thresholds, their words in stencil, their cots and crates and pumps and guns; the cold of a hulk in the red of the emergency lamps; where the war has been, burnt bays, torn ceilings and cables,
// debris, and the crew she lost where they fell. The pieces are art/blender/board_kit.py's, placed as instances (one instanced mesh for each piece the decks use).
//
// Plain code (no actors, no world, no content): the same functions run in the game and in the bench (AstraBoardSimCommandlet's `dress` scenario: how many instances and triangles a deck costs, that no prop
// stands where the soldiers go, that a room is always dressed the same). Two layers:
//   - the LAYOUT of a plan's props (MakeLayout): which crate, bunk or pump stands where in each room, from the plan alone (the class, the room's kind and size, its doors): the same on every ship of the class and
//     before any war, so the simulation can know it (the plan's map keeps the boxes: nobody is placed in a crate: FAstraBoardMap::SetBlocks) and the Captain's walk can be stopped by it;
//   - the DRESSING of a room (DressRoom): the layout plus everything that depends on the ship (her side, whether she has power, what the war did to the room).
// Intelligence is not here: this places things; what the people on these decks do is the minds' and the simulation's.

#pragma once

#include "CoreMinimal.h"
#include "AstraBoardPlans.h"

namespace AstraBoardDress
{
	/** Whose ship she is, as her plan's style says (data/ship/plans/<class>.json "style": mandate | astra | guild). */
	enum class EDressSide : uint8 { Mandate, Astra, Guild };
	ASTRA_API EDressSide SideOfStyle(const FString& PlanStyle);

	/** The frame a piece is made in (art/blender/board_kit_defs.py): wall pieces stand on a wall with their relief into the room, ceiling pieces hang, floor pieces lie, opening pieces straddle the plane between
	 *  two rooms, props and bodies stand on the floor with their front towards +X. */
	enum class EFrame : uint8 { Wall, Ceiling, Floor, Opening, Prop, Body };

	/** The kit's pieces, in the order of the catalog's table (a placement carries the index). */
	enum class EPiece : uint8
	{
		WallA, WallB, WallC, WallD, WallE, WallF, WallMotto, WallHold, WallPlain, Rib, Cornice, Header,
		Pipes, Tray, Lamp, LampDead, LampRed, Vent, Cables,
		Floor, Threshold, Guide, Debris,
		Jamb, DoorHeader, BlastJamb, BlastHeader, BlastLeaf,
		Crate, CrateLong, Barrel, Locker, Rack, Bunk, Table, Bench, Console, Machine, Motor, Tank, Reactor, Breech, Bed, Cell, Banner,
		BodyA, BodyB, BodyC,
		Count
	};

	struct FPieceDef
	{
		const TCHAR* Key;              // the kit's key ("wall_a": data/ship/board_kit.json)
		const TCHAR* Mesh;             // the static mesh's name ("SM_BRD_WallA": /Game/ASTRA/Kit/Board/<Mesh>.<Mesh>)
		EFrame Frame;
		bool bSolid;                   // a prop that stops the Captain (the game gives it a box of collision: the instanced meshes carry none)
		float MinX, MinY, MaxX, MaxY;  // props and bodies: the footprint in the piece's own frame (cm)
		float Height;                  // props and bodies: how tall (cm)
	};
	ASTRA_API const FPieceDef& Def(EPiece P);
	ASTRA_API FString MeshPath(EPiece P);
	ASTRA_API bool FindPiece(const FString& Key, EPiece& Out);

	/** One piece placed: where (cm, the plan's frame), how it is turned (a yaw about the vertical puts the piece's +X towards (cos, sin); a lamp on a wall is turned on its side), scaled in the piece's own axes. */
	struct FPlacement
	{
		EPiece Piece = EPiece::Floor;
		FVector Pos = FVector::ZeroVector;
		FRotator Rot = FRotator::ZeroRotator;
		FVector Scale = FVector::OneVector;
		int32 Comp = INDEX_NONE;
		int32 Door = INDEX_NONE;       // BlastLeaf: the damage map's door it closes (the leaf follows the fight's)
	};

	/** A prop's footprint in the layout: where it stands (the plan's frame) and the box (cm, axis aligned: props stand square to the walls) the Captain cannot pass through and nobody is placed in. */
	struct FProp
	{
		EPiece Piece = EPiece::Crate;
		FVector Pos = FVector::ZeroVector;
		float Yaw = 0.f;
		FBox2D Box = FBox2D(ForceInit);
		float Height = 0.f;
		int32 Comp = INDEX_NONE;
	};

	/** The props of a plan: from the plan alone (the same for every ship of the class). */
	struct ASTRA_API FLayout
	{
		TArray<FProp> Props;                         // grouped by room, in room order
		TArray<int32> First;                         // first prop of each room (and one more: the end), indexed by compartment
		TArrayView<const FProp> PropsOf(int32 Comp) const;
		int32 NumRooms() const { return First.Num() > 0 ? First.Num() - 1 : 0; }
	};
	/** Lays out the props of every room of the plan and gives the plan's map their boxes (nobody is placed or stands in a prop). Deterministic: the plan alone decides. Safe on a worker thread; done once per
	 *  plan. A plan of the Aquila is not laid out (her decks are authored). */
	ASTRA_API TSharedRef<FLayout> MakeLayout(FBoardShipPlan& Plan);

	enum class ELamp : uint8 { Lit, Red, Dead };
	/** A caged lamp (cm): the game lights a few of the lit and the red ones near the Captain. */
	struct FLamp
	{
		FVector Pos = FVector::ZeroVector;
		ELamp State = ELamp::Lit;
		int32 Comp = INDEX_NONE;
	};
	/** A sign above a door that names the room beyond it: where (the lintel's face, cm), the way it faces (out of the wall, into the room), what it says. */
	struct FDoorSign
	{
		FVector Pos = FVector::ZeroVector;
		FVector2D Facing = FVector2D(1.0, 0.0);
		FString Text;
		int32 Comp = INDEX_NONE;
	};
	/** Where the war shows in a room: flames, smoke under the ceiling, sparks from cut conduits (cm). */
	struct FWarMark
	{
		enum class EKind : uint8 { Flame, Smoke, Spark };
		EKind Kind = EKind::Flame;
		FVector Pos = FVector::ZeroVector;
		float Size = 100.f;
		float Strength = 0.f;
		int32 Comp = INDEX_NONE;
	};
	/** A solid prop as a box for the Captain's collision (cm, the plan's frame). */
	struct FSolid
	{
		FVector Centre = FVector::ZeroVector;
		FVector Half = FVector::ZeroVector;
		int32 Comp = INDEX_NONE;
	};

	/** Everything that stands in one room. */
	struct FRoomDress
	{
		TArray<FPlacement> Pieces;
		TArray<FLamp> Lamps;
		TArray<FDoorSign> Signs;
		TArray<FWarMark> Fx;
		TArray<FSolid> Blocks;
		void Reset() { Pieces.Reset(); Lamps.Reset(); Signs.Reset(); Fx.Reset(); Blocks.Reset(); }
	};

	/** What a ship's dressing depends on besides her plan. */
	struct FDressContext
	{
		const FBoardShipPlan* Plan = nullptr;
		EDressSide Side = EDressSide::Mandate;
		uint32 Seed = 0;                                       // the plan's own seed (SeedOf)
		bool bHulk = false;                                    // she has lost her power: the red of the emergency lamps
		const TMap<int32, FBoardRoomMood>* Moods = nullptr;    // the rooms the war has left not as built (null: all as built)
		int32 Level = 2;                                       // 0 nothing, 1 the structure (bays, ceilings, floors, frames, lamps, burnt bays), 2 also the props, banners, signs, debris, flames and sparks
	};
	ASTRA_API uint32 SeedOf(FName Class);

	/** The dressing of one room: the structure from the plan's walls (AstraBoardInterior::FaceGeo), the props of the layout (null: none), what the war did to it. */
	ASTRA_API void DressRoom(const FDressContext& Ctx, const FLayout* Layout, int32 Comp, FRoomDress& Out);

	/** One of the crew she lost, where he fell (cm). */
	struct FFallen
	{
		int32 Comp = INDEX_NONE;
		FVector Pos = FVector::ZeroVector;
		int32 Person = INDEX_NONE;
	};
	/** The fallen as placements: the pose, the way he lies and the side he lies on from who he was and where (never inside a prop or a wall: kept in the room's free floor). */
	ASTRA_API void DressFallen(const FDressContext& Ctx, const TArray<FFallen>& Fallen, TArray<FPlacement>& Out);

	/** The cost of a dressing as numbers: pieces by kind, triangles (from the kit's own account of its meshes: data/ship/board_kit.json), for the bench. */
	struct FTally
	{
		int32 Pieces[(int32)EFrame::Body + 1] = {0, 0, 0, 0, 0, 0};
		int32 Blocks = 0, Lamps = 0, Signs = 0, Fx = 0;
		int64 Tris = 0;
		void Add(const FRoomDress& R, const TArray<int32>& TrisOf);
		int32 TotalPieces() const;
	};
	/** The kit's triangles by piece, read from data/ship/board_kit.json (the bench's). False (and why) when the file is missing or does not parse. */
	ASTRA_API bool LoadKitTris(TArray<int32>& OutTrisOf, FString& OutWhy);
	/** Whether the kit's data file agrees with this catalog (names, footprints within 3 cm); the bench's. Empty when it does. */
	ASTRA_API FString CheckKit();
}
