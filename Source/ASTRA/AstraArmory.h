// ASTRA — ABBORDAGGI: the armory's rack on Deck 8: the rifle and the sidearm hang on it, and E takes them (or puts them back). One stands in the middle of the armory
// when the level has none (UAstraBoardSubsystem makes it while the Captain is near, from the plan's armory); the level may place its own where the kit has a rack.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "AstraArmory.generated.h"

class UStaticMeshComponent;

UCLASS()
class ASTRA_API AAstraArmoryRack : public AActor
{
	GENERATED_BODY()

public:
	AAstraArmoryRack();

	/** E: the Captain takes the weapons, or puts them back. True when he was in reach of the rack (the key was its). */
	bool TryUse(APawn* Me);
	bool IsWithinReach(const APawn* Me) const;

protected:
	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;

private:
	UPROPERTY() TObjectPtr<UStaticMeshComponent> Frame;
	UPROPERTY() TObjectPtr<UStaticMeshComponent> Rifle;
	UPROPERTY() TObjectPtr<UStaticMeshComponent> Pistol;
	UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> Parts;
	bool bShowingWeapons = true;
	void Show(bool bWeaponsThere);
};
