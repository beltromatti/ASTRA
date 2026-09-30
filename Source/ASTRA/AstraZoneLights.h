// Lights of the ship's interior that burn only near the Captain (docs/NAVE.md): every local light on an actor tagged
// "ASTRA.ZoneLight.<compartment>" is off unless it is among the nearest few within reach of the Captain's eyes. The ship
// has hundreds of lamps and a MacBook Air can shade a handful: the rooms the Captain walks through are lit, the rest of
// the hull waits in the dark (nobody sees it). The flight deck, the bridge and the older rooms keep their own rules.

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "AstraZoneLights.generated.h"

class ULightComponent;

UCLASS()
class UAstraZoneLights : public UTickableWorldSubsystem
{
	GENERATED_BODY()

public:
	virtual bool ShouldCreateSubsystem(UObject* Outer) const override;
	virtual void OnWorldBeginPlay(UWorld& InWorld) override;
	virtual void Tick(float DeltaTime) override;
	virtual TStatId GetStatId() const override { RETURN_QUICK_DECLARE_CYCLE_STAT(UAstraZoneLights, STATGROUP_Tickables); }

	/** At most this many zone lights lit at once (astra.zonelights.max), within this reach (m, astra.zonelights.reach). */
	int32 MaxLit = 8;
	float ReachM = 30.f;

private:
	struct FZoneLight { TWeakObjectPtr<ULightComponent> Light; FString Zone; bool bOn = true; };
	TArray<FZoneLight> Lights;
	float Accum = 0.f;
};
