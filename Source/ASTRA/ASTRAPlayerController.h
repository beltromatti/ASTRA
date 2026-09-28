// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/PlayerController.h"
#include "ASTRAPlayerController.generated.h"

class UInputMappingContext;
class UUserWidget;

/**
 *  Simple first person Player Controller
 *  Manages the input mapping context.
 *  Overrides the Player Camera Manager class.
 */
UCLASS(abstract, config="Game")
class ASTRA_API AASTRAPlayerController : public APlayerController
{
	GENERATED_BODY()
	
public:

	/** Constructor */
	AASTRAPlayerController();

protected:

	/** Input Mapping Contexts */
	UPROPERTY(EditAnywhere, Category="Input|Input Mappings")
	TArray<UInputMappingContext*> DefaultMappingContexts;

	/** Input Mapping Contexts */
	UPROPERTY(EditAnywhere, Category="Input|Input Mappings")
	TArray<UInputMappingContext*> MobileExcludedMappingContexts;

	/** Mobile controls widget to spawn */
	UPROPERTY(EditAnywhere, Category="Input|Touch Controls")
	TSubclassOf<UUserWidget> MobileControlsWidgetClass;

	/** Pointer to the mobile controls widget */
	UPROPERTY()
	TObjectPtr<UUserWidget> MobileControlsWidget;

	/** If true, the player will use UMG touch controls even if not playing on mobile platforms */
	UPROPERTY(EditAnywhere, Config, Category = "Input|Touch Controls")
	bool bForceTouchControls = false;

	/** Gameplay initialization */
	virtual void BeginPlay() override;

	/** Input mapping context setup */
	virtual void SetupInputComponent() override;

	/** Returns true if the player should use UMG touch controls */
	bool ShouldUseTouchControls() const;

	/** Push-to-talk (V): the Captain speaks to the bridge crew */
	void OnTalkPressed();
	void OnTalkReleased();

	/** The captain's chair (E): sit down / stand up. The game starts seated. */
	UPROPERTY(EditAnywhere, Category = "ASTRA")
	FVector CaptainSeat = FVector(0.f, 0.f, 20.f);

	UPROPERTY(EditAnywhere, Config, Category = "ASTRA")
	bool bStartSeated = true;

	bool bSeated = false;
	FTimerHandle SeatTimer;
	void ToggleSeat();
	void OpenMenu();
	/** The Captain climbs into a Falcon of Alpha on the flight deck: the cockpit on the port catapult. */
	void BoardFalcon(class AAstraHangar* Hangar, APawn* Walker);

public:
	/** Console twin of the E key (the lift, the captain's chair): for tests and accessibility. */
	UFUNCTION(Exec)
	void AstraUse() { ToggleSeat(); }

protected:
	void SetSeated(bool bSit);
};
