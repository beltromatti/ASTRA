// ASTRA — the flight deck (Deck 9): its lights come on while the Captain is down there, the parked flight groups follow
// the simulation (a launch: the craft taxis to its catapult and is thrown down the tube; a landing: it is back in its
// bay), and the lift joins it to the bridge's corridor.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "AstraHangar.generated.h"

class ALight;
class AStaticMeshActor;
class USoundBase;

UCLASS()
class ASTRA_API AAstraHangar : public AActor
{
	GENERATED_BODY()

public:
	AAstraHangar();
	virtual void BeginPlay() override;
	virtual void Tick(float DeltaTime) override;

	/** The lift's two landings: on the bridge deck (world, cm) and here (relative to this actor, cm). */
	UPROPERTY(EditAnywhere, Category = "Hangar")
	FVector BridgeLanding = FVector(-1860.f, -390.f, 20.f);

	UPROPERTY(EditAnywhere, Category = "Hangar")
	FVector HangarLanding = FVector(250.f, 0.f, 20.f);

	/** Main Engineering's landing (world, cm; zero = no third stop). */
	UPROPERTY(EditAnywhere, Category = "Hangar")
	FVector EngineeringLanding = FVector::ZeroVector;

	/** The lift network: which landing the pawn stands at (0 the bridge, 1 the flight deck, 2 Main Engineering, -1 none),
	 *  and the ride to another (fade, the car's hum, the other deck). */
	int32 LiftLandingNear(const APawn* Pawn) const;
	bool RideLift(APawn* Pawn, int32 ToLanding);
	int32 NumLandings() const { return EngineeringLanding.IsNearlyZero() ? 2 : 3; }
	bool IsPawnInEngineering(const APawn* Pawn) const;

	/** The lift call: the Captain is near a landing and presses E. Returns false when no landing is near. */
	bool TryUseLift(APawn* Pawn);
	/** E beside one of Alpha's Falcons on deck: the Captain takes it (the next in line for the catapult disappears from
	 *  its bay while the screen is dark). False when no Falcon is near or none is free. */
	bool TryBoard(APawn* Pawn);
	/** The Captain's Falcon on Alpha's catapult track: T 0 = in the cradle, 1 = clear of the tube's mouth (world pose;
	 *  the camera is the pilot's eye). */
	FTransform CatapultPose(float T) const;
	/** The speed (m/s) the catapult gives over a run of Seconds. */
	float CatapultExitSpeed(float Seconds) const;
	/** Where the Captain stands after climbing down (beside Alpha's bays, facing the tubes). */
	FTransform DeckSpot() const;
	bool IsPawnInHangar(const APawn* Pawn) const;

private:
	struct FParked
	{
		TObjectPtr<AStaticMeshActor> Actor = nullptr;
		FTransform Home;
		float Anim = -1.f;       // < 0 parked or away; 0..1 taxi + catapult
		bool bAway = false;
	};
	TMap<FString, TArray<FParked>> Parked;   // squadron -> its craft, in bay order
	UPROPERTY() TArray<TObjectPtr<ALight>> ZoneLights;
	UPROPERTY() TArray<TObjectPtr<ALight>> EngLights;
	bool bEngLightsOn = true;
	int32 RideToLanding = -1;
	FVector LandingWorld(int32 Index) const;
	UPROPERTY() TObjectPtr<USoundBase> CatapultSound;
	UPROPERTY() TObjectPtr<USoundBase> LiftSound;
	bool bLightsOn = true;
	float CheckT = 0.f;
	float LiftCooldown = 0.f;
	float LiftT = -1.f;          // a ride in progress (fade, move, fade)
	TWeakObjectPtr<APawn> Rider;
	FVector RideTo;

	void SetZoneLights(bool bOn);
	void SyncSquadrons();
	void Animate(FParked& P, const FString& Squadron, float Dt);
};
