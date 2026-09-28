// ASTRA — the surface of any world, built at run time where the planet zone lies (1000 km below the bridge): the
// ground (FAstraWorldGen) as procedural mesh tiles, its sea (water or lava), its sky (atmosphere, fog, clouds, sky
// light) tuned to the kind of world, and a landing pad with a small outpost. New Ravenna keeps its hand-built zone;
// every other world the Aquila reaches gets one of these, the same every time (seeded by its name).

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "AstraWorldGen.h"
#include "AstraWorldSurface.generated.h"

class UProceduralMeshComponent;
class UStaticMeshComponent;
class USkyAtmosphereComponent;
class UVolumetricCloudComponent;
class UExponentialHeightFogComponent;
class USkyLightComponent;
class UPointLightComponent;

UCLASS()
class ASTRA_API AAstraWorldSurface : public AActor
{
	GENERATED_BODY()

public:
	AAstraWorldSurface();

	/** Builds the world (the actor stands at the zone's origin: sea level, the landing zone's centre). */
	void Build(const FString& InWorldName, const FString& InPlanetType, const FString& InOwner = FString());
	void Show(bool bShow);
	bool IsBuilt() const { return Gen.IsValid(); }

	FString WorldName;
	FString PlanetType;
	FString Owner;   // who holds the system (the mind's war map): a silent world's field is dark
	/** The landing pad's centre on the ground (world, cm), and the height of the sea (world z, cm; none: very low). */
	FVector SiteWorld() const;
	float SeaWorldZ() const;
	/** What the outpost is called ("Cassia Prime landing field"...), for the crew and the HUD. */
	FString SiteName() const;

private:
	UPROPERTY() TObjectPtr<USceneComponent> Root;
	UPROPERTY() TObjectPtr<UProceduralMeshComponent> Core;
	UPROPERTY() TObjectPtr<UProceduralMeshComponent> ShadowProxy;
	UPROPERTY() TObjectPtr<UProceduralMeshComponent> Far;
	UPROPERTY() TObjectPtr<UProceduralMeshComponent> Sea;
	UPROPERTY() TObjectPtr<USkyAtmosphereComponent> Atmosphere;
	UPROPERTY() TObjectPtr<UVolumetricCloudComponent> Clouds;
	UPROPERTY() TObjectPtr<UExponentialHeightFogComponent> Fog;
	UPROPERTY() TObjectPtr<USkyLightComponent> SkyLight;
	UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> Outpost;
	UPROPERTY() TObjectPtr<UPointLightComponent> Beacon;
	TUniquePtr<FAstraWorldGen> Gen;
	float HorizonZ = 0.f;   // m: the height the far ground settles to at its rim, and the horizon rings beyond it (over the curve)

	void BuildGround();
	void BuildSky();
	void BuildOutpost();
};
