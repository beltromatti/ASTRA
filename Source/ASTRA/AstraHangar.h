// ASTRA — the flight deck (Deck 9): its lights come on while the Captain is down there, the parked flight groups follow
// the simulation (a launch: the craft taxis to its catapult and is thrown down the tube; a landing: it is back in its
// bay). The old rooms' lights (Main Engineering, the Medbay, the Mess Hall, Crew Berthing) follow the Captain here too. The lifts are no longer
// this actor's: the real ones are AstraLiftSubsystem's (docs/ASCENSORI.md).

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

	/** Where the old lift's two landings were (the bridge's corridor, the flight deck's alcove): kept so that the saved level and tools/ue_scripts/build_hangar.py
	 *  still read and write them; nothing uses them now. */
	UPROPERTY(EditAnywhere, Category = "Hangar")
	FVector BridgeLanding = FVector(-1860.f, -390.f, 20.f);

	UPROPERTY(EditAnywhere, Category = "Hangar")
	FVector HangarLanding = FVector(250.f, 0.f, 20.f);

	/** Main Engineering's old lift alcove (world, cm; zero = none): the room's volume is measured from it (its lights, the Captain's visit), and the ship's tests put him there. */
	UPROPERTY(EditAnywhere, Category = "Hangar")
	FVector EngineeringLanding = FVector::ZeroVector;

	/** The Medbay's (the same). */
	UPROPERTY(EditAnywhere, Category = "Hangar")
	FVector MedbayLanding = FVector::ZeroVector;

	/** The Mess Hall's (the same). */
	UPROPERTY(EditAnywhere, Category = "Hangar")
	FVector MessLanding = FVector::ZeroVector;

	/** Crew Berthing's (Deck 4, Section C; the same). */
	UPROPERTY(EditAnywhere, Category = "Hangar")
	FVector BerthLanding = FVector::ZeroVector;

	bool IsPawnInEngineering(const APawn* Pawn) const;
	bool IsPawnInMedbay(const APawn* Pawn) const;
	bool IsPawnInMess(const APawn* Pawn) const;
	bool IsPawnInBerths(const APawn* Pawn) const;

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
	/** The introduction's look at the flight deck (AstraIntro.cpp): its lights on as if the Captain were down there. */
	void Showcase(bool bOn) { bShowcase = bOn; CheckT = 0.f; }
	/** Where Alpha's Falcons wait in their bays (world cm, their middle), the deck's length axis and the way across it from the bays to the
	 *  middle of the deck. False when none is home. */
	bool GetAlphaView(FVector& OutCenter, FVector& OutAlong, FVector& OutAcross) const;

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
	UPROPERTY() TArray<TObjectPtr<ALight>> MedLights;
	UPROPERTY() TArray<TObjectPtr<ALight>> MessLights;
	bool bMessLightsOn = true;
	UPROPERTY() TArray<TObjectPtr<ALight>> BerthLights;
	bool bBerthLightsOn = true;
	bool bEngLightsOn = true;
	bool bMedLightsOn = true;
	UPROPERTY() TObjectPtr<USoundBase> CatapultSound;
	bool bLightsOn = true;
	bool bShowcase = false;
	float CheckT = 0.f;

	void SetZoneLights(bool bOn);
	void SyncSquadrons();
	void Animate(FParked& P, const FString& Squadron, float Dt);
};
