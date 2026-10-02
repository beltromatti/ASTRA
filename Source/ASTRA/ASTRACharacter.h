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
 *  The Captain on foot: walks, runs, jumps, crouches and lies down; the eyes follow the posture.
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

	EAstraPosture GetPosture() const { return Posture; }
	bool IsSprinting() const { return bSprintHeld && Posture == EAstraPosture::Standing; }
	/** Back on the feet at once (seated, the lift, a cutscene): no crouch, no prone, eyes at standing height. */
	void ResetPosture();

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
