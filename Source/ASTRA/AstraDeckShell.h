// ASTRA — the shell of a deck: the one actor of a deck's sub-level (L_Deck05 ...) that holds its corridor modules, rooms, door plates and section signs
// as instanced static meshes (docs/NAVE.md §7bis). A deck has some 700 placements of 40-60 different meshes: as actors that is 700 actors, 700
// components, 700 scene proxies and a long stall when the level streams in; as instances it is a few hundred components of a few instances each,
// one copy of every mesh in memory however many decks use it, and the instance transforms are one flat array.
//
// Built in the editor by tools/ue_scripts/build_ship_interior.py (AddInstancesChunked, from the plan's "placements"): the components are saved with the
// level, nothing is made at run time. The doors stay actors (AAstraDoor: they move) and the lamps are data (AstraLampPool.*).

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "AstraDeckShell.generated.h"

class UInstancedStaticMeshComponent;
class UStaticMesh;

UCLASS()
class ASTRA_API AAstraDeckShell : public AActor
{
	GENERATED_BODY()

public:
	AAstraDeckShell();

	/** The deck this shell is the structure of (1 .. 12). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Deck")
	int32 Deck = 0;

	/** The editor / build script: instances of a mesh at WORLD transforms (cm), split along the ship into runs of ChunkCm (an instanced component culls and
	 *  registers as a whole: a 500 m long deck in one component per mesh would never be culled and would register in one stall). Returns the number
	 *  of instances added. */
	UFUNCTION(BlueprintCallable, Category = "Deck")
	int32 AddInstancesChunked(UStaticMesh* Mesh, const TArray<FTransform>& WorldTransforms, float ChunkCm = 16000.f);

	/** Removes every instance component (the build script rebuilds a deck from scratch). */
	UFUNCTION(BlueprintCallable, Category = "Deck")
	void ClearInstances();

	UFUNCTION(BlueprintCallable, Category = "Deck")
	int32 NumInstances() const;
	UFUNCTION(BlueprintCallable, Category = "Deck")
	int32 NumInstanceComponents() const;
	/** The triangles of every instance (LOD 0): what the deck costs the geometry pipeline (Nanite: a measure of the disk, not of the frame). */
	UFUNCTION(BlueprintCallable, Category = "Deck")
	int64 CountTriangles() const;
	/** The distinct meshes the deck uses. */
	UFUNCTION(BlueprintCallable, Category = "Deck")
	int32 NumDistinctMeshes() const;

private:
	UPROPERTY() TObjectPtr<USceneComponent> Root;
};
