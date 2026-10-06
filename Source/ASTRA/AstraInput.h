// The Captain's controls on foot, built in code (no input assets): Enhanced Input actions and their default keys for
// keyboard and mouse and for a gamepad. The player controller owns one set and adds its mapping context; the character
// binds to its actions. The discrete keys of the ship (V, T, E, Tab, K, Esc) stay bound on the controller.

#pragma once

#include "CoreMinimal.h"
#include "UObject/Object.h"
#include "AstraInput.generated.h"

class UInputAction;
class UInputMappingContext;

UCLASS()
class UAstraInputSet : public UObject
{
	GENERATED_BODY()

public:
	/** Creates the actions and the on-foot mapping context (call once, right after construction). */
	void Build();

	/** Walk (Axis2D: X right, Y forward) — WASD, arrows, left stick. */
	UPROPERTY() TObjectPtr<UInputAction> Move;
	/** Look with the mouse (Axis2D, per-frame delta; Y already turned so that up looks up). */
	UPROPERTY() TObjectPtr<UInputAction> MouseLook;
	/** Look with a stick (Axis2D, a rate scaled by the frame time). */
	UPROPERTY() TObjectPtr<UInputAction> StickLook;
	UPROPERTY() TObjectPtr<UInputAction> Jump;
	/** Held: run. */
	UPROPERTY() TObjectPtr<UInputAction> Sprint;
	/** Tap: crouch or stand up; hold: lie down (the character times it). */
	UPROPERTY() TObjectPtr<UInputAction> Crouch;
	/** Held: lean out to the left / right (Z, X; the shoulders of a gamepad): the eyes and the weapon come out from behind a corner without the body. */
	UPROPERTY() TObjectPtr<UInputAction> LeanLeft;
	UPROPERTY() TObjectPtr<UInputAction> LeanRight;

	// --- ABBORDAGGI: the weapons (UAstraFpsComponent): fire, aim through the sights, reload, the two weapons, the last one, holster, the wheel
	UPROPERTY() TObjectPtr<UInputAction> Fire;
	UPROPERTY() TObjectPtr<UInputAction> Aim;
	UPROPERTY() TObjectPtr<UInputAction> Reload;
	UPROPERTY() TObjectPtr<UInputAction> Weapon1;
	UPROPERTY() TObjectPtr<UInputAction> Weapon2;
	UPROPERTY() TObjectPtr<UInputAction> QuickSwitch;
	UPROPERTY() TObjectPtr<UInputAction> Holster;
	UPROPERTY() TObjectPtr<UInputAction> WeaponWheel;     // Axis1D: the mouse wheel

	UPROPERTY() TObjectPtr<UInputMappingContext> OnFoot;
};
