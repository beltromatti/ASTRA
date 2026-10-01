// ASTRA — a proving ground for the lifts (docs/ASCENSORI.md): floors and walls round every landing of a lift plan, so that the cars have somewhere to
// stand and a Captain somewhere to walk before the ship's own decks have real shafts. The offline bench (AstraLiftSim) builds it in a headless world;
// AAstraLiftTestRig builds it in a level (tools/ue_scripts/build_lifts.py --test makes /Game/ASTRA/Maps/L_LiftTest with one of these in it) and loads the
// test plan, so the lead can ride the same lifts in the game.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "AstraLiftData.h"
#include "AstraLiftTestRig.generated.h"

class UBoxComponent;

namespace AstraLiftArena
{
	/** The floors of every lobby, the walls round every shaft and the walls either side of every door (boxes with collision; with bVisible, plain cubes too). */
	ASTRA_API void Build(AActor* Owner, const FAstraLiftNetwork& Net, bool bVisible);
}

UCLASS()
class ASTRA_API AAstraLiftTestRig : public AActor
{
	GENERATED_BODY()

public:
	AAstraLiftTestRig();
	virtual void BeginPlay() override;

	/** The plan the rig loads (relative to the project): the lifts' own test plan. */
	UPROPERTY(EditAnywhere, Category = "Lifts")
	FString PlanPath = TEXT("data/ship/test/lifts_fixture.json");

	UPROPERTY(EditAnywhere, Category = "Lifts")
	bool bVisible = true;
};
