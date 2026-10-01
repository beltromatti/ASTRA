// ASTRA — a ship's navigation lights.

#pragma once

#include "CoreMinimal.h"
#include "Components/SceneComponent.h"
#include "AstraNavLights.generated.h"

class UStaticMeshComponent;
class UMaterialInstanceDynamic;

/** One lamp of a hull: where it stands and what it is. The table every drawing of the running lights reads: the component below (the
 *  Aquila, the lifepods) and the war's instanced lamps (AstraWarDraw.cpp: every other ship and craft). */
struct FAstraNavLamp
{
	FVector Local = FVector::ZeroVector;     // cm, in the mesh's own frame
	FLinearColor Color = FLinearColor::White;
	float SizeM = 1.f;                       // metres across up close
	float Glow = 100.f;                      // intensity when lit
	uint8 Pattern = 0;                       // 0 steady, 1 a double white flash, 2 a slow red pulse
};

/**
 * Red to port, green to starboard, white at the stern, a white strobe on top and a red one below — where the hull
 * really is (data/ship/nav_lights.json, read from each mesh by tools/ue_scripts/extract_nav_lights.py). Warships of the
 * Kharon Mandate run dark but for one slow red strobe. The lamps keep a few pixels on screen however far off, so a
 * fleet reads against the stars.
 */
UCLASS()
class ASTRA_API UAstraNavLights : public USceneComponent
{
	GENERATED_BODY()

public:
	UAstraNavLights();
	/** Lights for this hull (its static mesh's name); bMandate: dark but for a slow red strobe; bNoTopStrobe: none over
	 *  a bridge the Captain looks out of. */
	void Setup(const FString& MeshName, bool bMandate, bool bNoTopStrobe = false);
	/** The lamps of a hull, from data/ship/nav_lights.json (none when the hull is not in it): the same set Setup lights. */
	static void LampsFor(const FString& MeshName, bool bMandate, bool bNoTopStrobe, TArray<FAstraNavLamp>& Out);
	/** How lit a lamp of this pattern is at time T (seconds) with this phase: 0..1. */
	static float PatternOn(uint8 Pattern, float T, float Phase);
	/** A lifepod's distress beacon: an orange double flash (local position on the pod). */
	void AddBeacon(const FVector& Local) { AddLamp(Local, FLinearColor(1.f, 0.38f, 0.06f), 0.5f, 120.f, 1); }
	virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;

private:
	UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> Lamps;
	UPROPERTY() TArray<TObjectPtr<UMaterialInstanceDynamic>> Mids;
	TArray<float> Size;        // metres across up close
	TArray<float> Glow;        // intensity when lit
	TArray<uint8> Pattern;     // 0 steady, 1 a double white flash, 2 a slow red pulse
	TArray<float> Phase;
	float T = 0.f;

	void AddLamp(const FVector& Local, const FLinearColor& Color, float SizeM, float Intensity, uint8 InPattern);
};
