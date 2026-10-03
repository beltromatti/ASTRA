// ASTRA — ABBORDAGGI: the places the Captain's weapons hang (docs/ABBORDAGGI.md): the rack of the Marine Armory on Deck 8 (the rifle and the sidearm) and the locker of the Captain's Ready Room on
// Deck 1 (a sidearm), and E takes what is there (or puts it back). What a post holds is the ship's (UAstraBoardSubsystem keeps the stock: the armourer's delivery takes from the armory's);
// the actor is its picture, made while the Captain is near, and the key's.
//
// A rack the level has placed itself (no post) gives and takes the whole kit, as the first one did.

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
	/** A freestanding rack (the rifle and the sidearm on its bars) or a small wall locker (the sidearm on a hook inside it). */
	enum class EKind : uint8 { Rack, Locker };

	AAstraArmoryRack();

	/** Made for a post of the board subsystem's (call it before the actor begins play: SpawnActor's pre-spawn function): its stock is the subsystem's and the rack only shows it. */
	void MakePost(FName InPostId, EKind InKind);
	FName GetPostId() const { return PostId; }

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
	EKind Kind = EKind::Rack;
	FName PostId;                            // NAME_None: a rack of the level's, which gives and takes the whole kit
	bool bShowRifle = true, bShowPistol = true;
	void Show(bool bRifleThere, bool bPistolThere);
};
