// ASTRA — the solid parts of the places' hulls (SPAZIO-VIVO, docs/SPAZIO.md): where a place is hull and where it is air, for the Captain's Falcon, which flies into a hull and is lost (the
// battle's PilotCollision). Keeper Station, the Arsenal, the refineries and the mine are fixtures in the plot, and their meshes are mostly air (a ring with its hole, bays open to space, piers,
// cranes): the bounding box of a mesh that the war tests the other ships' hulls with would crash the Falcon in the middle of the Keeper's ring and let her through a pier.
//
// art/blender/space3_solids.py makes each place's hull from its own mesh as boxes on a grid (data/space/solids.json): the cells the surface touches, what is closed inside, merged into
// a few thousand boxes. The game expands them into a bitmap (a megabit or two a place) and tests a point in a lookup; a swept path is tested every half cell. The parts that turn (the
// Keeper's ring, the Arsenal's cranes) have boxes of their own in their own frame, which UAstraSpaceLife::PilotHit turns as the drawing turns them.
//
// Plain C++ like the rest of the module's records: no engine objects, so the unit tests (RunSolidsTests) and the bench can ask of it.

#pragma once

#include "CoreMinimal.h"

namespace AstraSpace
{
	/** One mesh's solid cells: a bitmap on a grid of Cell metres from Origin (the mesh's frame: x forward, y starboard, z up). */
	struct FSolids
	{
		float Cell = 3.f;
		FVector Origin = FVector::ZeroVector;
		int32 NX = 0, NY = 0, NZ = 0;
		TBitArray<> Bits;
		int32 NumBoxes = 0;                       // what the file said (the bitmap is made from them)
		int32 NumCells = 0;                       // solid cells
		FVector Min = FVector::ZeroVector, Max = FVector::ZeroVector;     // the extent of the boxes (m, mesh frame)

		bool IsEmpty() const { return NumCells == 0; }
		/** Is this point of the mesh's frame in a solid cell? */
		bool Inside(const FVector& P) const;
		/** Does the path from A to B (mesh frame) pass through a solid cell? Sampled every half cell, ends included. */
		bool Crosses(const FVector& A, const FVector& B) const;
	};

	struct FSolidData
	{
		TMap<FString, FSolids> Meshes;
		bool bLoaded = false;
		FString Source;
		const FSolids* Find(const FString& Mesh) const { return Meshes.Find(Mesh); }
		bool Parse(const FString& Json, FString& OutError);
	};

	/** The game's table of solids, loaded once from Content/ASTRA/Data/space/solids.json (the staged copy) or data/space (the source). */
	ASTRA_API const FSolidData& SolidData();
	ASTRA_API void ReloadSolidData();

	/** The unit tests (the bench's -solidstest and tools/space.py test): the data, a ring's hole and spokes, a swept path, the cost of a lookup. True when all pass. */
	ASTRA_API bool RunSolidsTests(TArray<FString>& Fails, TArray<FString>& Notes);
}
