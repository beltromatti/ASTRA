// ASTRA — a sliding pressure door: two leaves that open into the wall when someone comes near (and close behind).

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "AstraDoor.generated.h"

class UStaticMeshComponent;

/** The doors' list of walkers: anyone who goes about the ship on their own feet and whom the doors open for, besides the player's pawn
 *  and the officers on a visit (AAstraCrewMember::Walkers): the crew's bodies (AAstraLifeBody), damage-control teams in view, whatever
 *  comes next. A walker adds itself while it moves and removes itself when it stops; an actor that is destroyed leaves the list by
 *  itself (weak pointers). A door opens when any walker is within its OpenRadius on its deck. Cheap by design: the list is as long as
 *  the people who walk in view, and a door only reads it. */
namespace AstraDoors
{
	ASTRA_API void AddWalker(const AActor* Walker);
	ASTRA_API void RemoveWalker(const AActor* Walker);
	ASTRA_API const TArray<TWeakObjectPtr<const AActor>>& Walkers();
}

UCLASS()
class ASTRA_API AAstraDoor : public AActor
{
	GENERATED_BODY()

public:
	AAstraDoor();
	virtual void BeginPlay() override;
	virtual void Tick(float DeltaTime) override;

	/** Clear opening (cm). The leaves are the corridor kit's (1.4 m x 2.3 m for the pair), scaled to fit. */
	UPROPERTY(EditAnywhere, Category = "Door")
	float Width = 160.f;

	UPROPERTY(EditAnywhere, Category = "Door")
	float Height = 240.f;

	/** Opens when the player is within this distance (cm). */
	UPROPERTY(EditAnywhere, Category = "Door")
	float OpenRadius = 260.f;

	UPROPERTY(EditAnywhere, Category = "Door")
	bool bLocked = false;

	UPROPERTY(EditAnywhere, Category = "Door")
	float SlideTime = 0.6f;

private:
	UPROPERTY() TObjectPtr<USceneComponent> Root;
	UPROPERTY() TObjectPtr<UStaticMeshComponent> LeafA;
	UPROPERTY() TObjectPtr<UStaticMeshComponent> LeafB;
	float Open = 0.f;          // 0 closed .. 1 open
	bool bWantOpen = false;
	float CloseDelay = 0.f;
	void Place();
	void Sound(bool bOpening);
};
