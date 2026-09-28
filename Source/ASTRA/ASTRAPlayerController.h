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
	/** The lift's panel: which deck (1 the bridge, 2 Main Engineering, 3 the flight deck). */
	void ShowLiftMenu(class AAstraHangar* Hangar, int32 From);
	void CloseLiftMenu();
	void ChooseDeck(int32 Number);
	TSharedPtr<class SWidget> LiftMenu;
	TWeakObjectPtr<class AAstraHangar> LiftHangar;
	/** F1: the controls card (shown for a while at the start of a campaign as a hint). */
	void ToggleHelp();
	UFUNCTION(Exec) void AstraHelp() { ToggleHelp(); }
	/** Console: pick a deck on the open lift panel (1 bridge, 2 engineering, 3 flight deck). */
	UFUNCTION(Exec) void AstraDeck(int32 N) { if (LiftMenu.IsValid()) { ChooseDeck(N); } }
	void ShowHelp(bool bShow);
	/** T: a line typed to the crew instead of spoken (the voice is never required); Enter sends it, Esc cancels. */
	void OnTypePressed();   // opens the line on the next tick (the T itself must not land in the box)
	/** Test of the typed line through Slate itself: opens it, types the text key by key, presses Enter. */
	UFUNCTION(Exec) void AstraTypeTest(const FString& Text);
	void OpenOrderLine();
	void CloseOrderLine();
	TSharedPtr<class SWidget> OrderLine;
	TSharedPtr<class SEditableTextBox> OrderBox;
	FTimerHandle OrderFocusTimer;
	TSharedPtr<class SWidget> HelpWidget;
	TSharedPtr<class SWidget> HintWidget;
	FTimerHandle HintTimer;

public:
	/** Console twin of the E key (the lift, the captain's chair): for tests and accessibility. */
	UFUNCTION(Exec)
	void AstraUse() { ToggleSeat(); }

protected:
	void SetSeated(bool bSit);
};
