// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "Logging/LogMacros.h"
#include "ASTRACharacter.generated.h"

class UInputComponent;
class USkeletalMeshComponent;
class UCameraComponent;
class UInputAction;
struct FInputActionValue;

DECLARE_LOG_CATEGORY_EXTERN(LogTemplateCharacter, Log, All);

/** How the Captain holds the body on foot. */
UENUM()
enum class EAstraPosture : uint8
{
	Standing,
	Crouched,
	Prone
};

/**
 *  The Captain on foot: walks, runs, jumps, crouches and lies down, and leans out from a corner; the eyes follow the posture and the lean.
 *  The controls come from the player controller's UAstraInputSet (built in code).
 */
UCLASS(abstract)
class AASTRACharacter : public ACharacter
{
	GENERATED_BODY()

	/** Pawn mesh: first person view (arms; seen only by self) */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Components", meta = (AllowPrivateAccess = "true"))
	USkeletalMeshComponent* FirstPersonMesh;

	/** First person camera */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Components", meta = (AllowPrivateAccess = "true"))
	UCameraComponent* FirstPersonCameraComponent;

	/** ABBORDAGGI: the weapons in his hands (the rifle and the sidearm of the armory): the arms, the aim, the rounds (AstraFpsComponent.*) */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Components", meta = (AllowPrivateAccess = "true"))
	class UAstraFpsComponent* Fps;

protected:

	/** Jump Input Action */
	UPROPERTY(EditAnywhere, Category ="Input")
	UInputAction* JumpAction;

	/** Move Input Action */
	UPROPERTY(EditAnywhere, Category ="Input")
	UInputAction* MoveAction;

	/** Look Input Action */
	UPROPERTY(EditAnywhere, Category ="Input")
	class UInputAction* LookAction;

	/** Mouse Look Input Action */
	UPROPERTY(EditAnywhere, Category ="Input")
	class UInputAction* MouseLookAction;

public:
	AASTRACharacter();

	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;
	virtual void PossessedBy(AController* NewController) override;

	EAstraPosture GetPosture() const { return Posture; }
	bool IsSprinting() const { return bSprintHeld && Posture == EAstraPosture::Standing; }
	/** Back on the feet at once (seated, the lift, a cutscene): no crouch, no prone, no lean, eyes at standing height. */
	void ResetPosture();

	/** The lean (Z and X held): -1 out to the left .. 1 out to the right, as far as the walls let the eyes go. The eyes come out of the line of the body and the picture rolls with them, the arms and the weapon on the camera
	 *  with it: a corner is looked round and fired round without the body showing (what the boarders see of him is the eye: UAstraBoardSubsystem takes the camera's place for his). */
	float GetLean() const { return Lean; }
	/** What the lean does now to the eyes: how far out of the line of the body (cm, to his right), how far down (cm), and the roll of the picture (degrees, to the right). */
	float GetLeanSideCm() const { return LeanSideCm; }
	float GetLeanDropCm() const { return LeanDropCm; }
	float GetLeanRoll() const { return LeanRollDeg; }
	/** The shape of a lean at Lean (-1..1) in a posture: the eyes' offset to the right of the line of the body and down, and the picture's roll. Pure (the bench checks it). */
	static void LeanFrame(float Lean, EAstraPosture Posture, float& OutSideCm, float& OutDropCm, float& OutRollDeg);
	/** One step of the easing of a lean towards what is asked of it (pure). */
	static float LeanStep(float Lean, float Target, float Dt);

	/** Speeds on foot (cm/s): a ship's corridors, not a racetrack. */
	UPROPERTY(EditAnywhere, Category = "Movement") float WalkSpeed = 380.f;
	UPROPERTY(EditAnywhere, Category = "Movement") float SprintSpeed = 640.f;
	UPROPERTY(EditAnywhere, Category = "Movement") float CrouchSpeed = 190.f;
	UPROPERTY(EditAnywhere, Category = "Movement") float ProneSpeed = 85.f;

protected:

	/** Called from Input Actions for movement input */
	void MoveInput(const FInputActionValue& Value);

	/** Called from Input Actions for looking input */
	void LookInput(const FInputActionValue& Value);

	/** Handles aim inputs from either controls or UI interfaces */
	UFUNCTION(BlueprintCallable, Category="Input")
	virtual void DoAim(float Yaw, float Pitch);

	/** Handles move inputs from either controls or UI interfaces */
	UFUNCTION(BlueprintCallable, Category="Input")
	virtual void DoMove(float Right, float Forward);

	/** Handles jump start inputs from either controls or UI interfaces */
	UFUNCTION(BlueprintCallable, Category="Input")
	virtual void DoJumpStart();

	/** Handles jump end inputs from either controls or UI interfaces */
	UFUNCTION(BlueprintCallable, Category="Input")
	virtual void DoJumpEnd();

	void SprintStart() { bSprintHeld = true; }
	void SprintEnd() { bSprintHeld = false; }
	void LeanLeftStart() { bLeanLeft = true; }
	void LeanLeftEnd() { bLeanLeft = false; }
	void LeanRightStart() { bLeanRight = true; }
	void LeanRightEnd() { bLeanRight = false; }
	void CrouchPressed();
	void CrouchReleased();

protected:

	/** Set up input action bindings */
	virtual void SetupPlayerInputComponent(UInputComponent* InputComponent) override;

private:
	EAstraPosture Posture = EAstraPosture::Standing;
	bool bSprintHeld = false;
	double CrouchDownAt = -1.0;      // when C went down (a hold of this long lies down)
	bool bCrouchHoldDone = false;    // the hold already acted: the release does nothing
	float EyeZ = 0.f;                // camera height above the capsule centre, eased towards the posture's
	float StandHalfHeight = 96.f;
	float ProneOffset = 0.f;         // how far the capsule centre went down when lying (to lift it back)
	bool bLeanLeft = false, bLeanRight = false;     // Z and X held
	float Lean = 0.f;                // -1 .. 1 (left .. right), eased, never into a wall
	float LeanSideCm = 0.f, LeanDropCm = 0.f, LeanRollDeg = 0.f;     // what it does to the eyes now (the camera's place, the picture's roll)

	bool CanLean() const;
	/** The share of a full lean to Side (-1 left, 1 right) the walls leave: the eyes are swept out from where they rest, and stop short of anything. */
	float LeanReach(float Side) const;
	void TickLean(float Dt);

	void SetPosture(EAstraPosture New);
	bool RoomToGrow(float NewHalfHeight) const;
	float TargetEyeZ() const;

public:

	/** Returns the first person mesh **/
	USkeletalMeshComponent* GetFirstPersonMesh() const { return FirstPersonMesh; }

	/** Returns first person camera component **/
	UCameraComponent* GetFirstPersonCameraComponent() const { return FirstPersonCameraComponent; }

	/** ABBORDAGGI: the Captain's weapons. */
	class UAstraFpsComponent* GetFps() const { return Fps; }

};
