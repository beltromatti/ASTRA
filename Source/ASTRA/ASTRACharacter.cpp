// Copyright Epic Games, Inc. All Rights Reserved.

#include "ASTRACharacter.h"
#include "Animation/AnimInstance.h"
#include "Camera/CameraComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "EnhancedInputComponent.h"
#include "InputActionValue.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "ASTRAPlayerController.h"
#include "AstraInput.h"
#include "AstraFpsComponent.h"
#include "AstraLadderSubsystem.h"
#include "Engine/World.h"
#include "ASTRA.h"

namespace
{
	// capsule half-heights and eye heights above the floor for each posture (cm)
	constexpr float CrouchHalfHeight = 58.f;
	constexpr float ProneHalfHeight = 36.f;
	constexpr float StandEyes = 165.f;
	constexpr float CrouchEyes = 105.f;
	constexpr float ProneEyes = 40.f;
	constexpr double HoldToLieDown = 0.38;   // s of C held that means "lie down" rather than "crouch"
}

AASTRACharacter::AASTRACharacter()
{
	PrimaryActorTick.bCanEverTick = true;

	// Set size for collision capsule
	GetCapsuleComponent()->InitCapsuleSize(55.f, 96.0f);

	// Create the first person mesh that will be viewed only by this character's owner
	FirstPersonMesh = CreateDefaultSubobject<USkeletalMeshComponent>(TEXT("First Person Mesh"));

	FirstPersonMesh->SetupAttachment(GetMesh());
	FirstPersonMesh->SetOnlyOwnerSee(true);
	FirstPersonMesh->FirstPersonPrimitiveType = EFirstPersonPrimitiveType::FirstPerson;
	FirstPersonMesh->SetCollisionProfileName(FName("NoCollision"));

	// the eyes ride on the capsule (not on the animated head), so crouching and lying down lower them smoothly
	FirstPersonCameraComponent = CreateDefaultSubobject<UCameraComponent>(TEXT("First Person Camera"));
	FirstPersonCameraComponent->SetupAttachment(GetCapsuleComponent());
	FirstPersonCameraComponent->SetRelativeLocation(FVector(0.f, 0.f, StandEyes - 96.f));
	FirstPersonCameraComponent->bUsePawnControlRotation = true;
	FirstPersonCameraComponent->bEnableFirstPersonFieldOfView = true;
	FirstPersonCameraComponent->bEnableFirstPersonScale = true;
	FirstPersonCameraComponent->FirstPersonFieldOfView = 70.0f;
	FirstPersonCameraComponent->FirstPersonScale = 0.6f;

	// ABBORDAGGI: the weapons in his hands
	Fps = CreateDefaultSubobject<UAstraFpsComponent>(TEXT("Fps"));

	// configure the character comps
	GetMesh()->SetOwnerNoSee(true);
	GetMesh()->FirstPersonPrimitiveType = EFirstPersonPrimitiveType::WorldSpaceRepresentation;

	GetCapsuleComponent()->SetCapsuleSize(34.0f, 96.0f);

	// Configure character movement
	GetCharacterMovement()->BrakingDecelerationFalling = 1500.0f;
	GetCharacterMovement()->AirControl = 0.5f;
}

void AASTRACharacter::BeginPlay()
{
	Super::BeginPlay();
	StandHalfHeight = GetCapsuleComponent()->GetUnscaledCapsuleHalfHeight();
	// whatever an old Blueprint stored for the camera, the eyes sit above the capsule centre, facing forward
	EyeZ = StandEyes - StandHalfHeight;
	FirstPersonCameraComponent->SetRelativeLocationAndRotation(FVector(0.f, 0.f, EyeZ), FRotator::ZeroRotator);
	FirstPersonCameraComponent->SetFieldOfView(90.f);
	UCharacterMovementComponent* Move = GetCharacterMovement();
	Move->MaxWalkSpeed = WalkSpeed;
	Move->MaxAcceleration = 1800.f;
	Move->BrakingDecelerationWalking = 2400.f;
	Move->GroundFriction = 9.f;
	Move->JumpZVelocity = 380.f;
}

void AASTRACharacter::SetupPlayerInputComponent(UInputComponent* PlayerInputComponent)
{
	UEnhancedInputComponent* EIC = Cast<UEnhancedInputComponent>(PlayerInputComponent);
	if (!EIC)
	{
		UE_LOG(LogASTRA, Error, TEXT("'%s' Failed to find an Enhanced Input Component!"), *GetNameSafe(this));
		return;
	}
	// the controls are built in code by the player controller (see AstraInput.h)
	const AASTRAPlayerController* PC = Cast<AASTRAPlayerController>(GetController());
	const UAstraInputSet* In = PC ? PC->GetInputSet() : nullptr;
	if (!In)
	{
		UE_LOG(LogASTRA, Error, TEXT("'%s': no ASTRA input set on the controller, the Captain cannot move"), *GetNameSafe(this));
		return;
	}
	EIC->BindAction(In->Jump, ETriggerEvent::Started, this, &AASTRACharacter::DoJumpStart);
	EIC->BindAction(In->Jump, ETriggerEvent::Completed, this, &AASTRACharacter::DoJumpEnd);
	EIC->BindAction(In->Move, ETriggerEvent::Triggered, this, &AASTRACharacter::MoveInput);
	EIC->BindAction(In->MouseLook, ETriggerEvent::Triggered, this, &AASTRACharacter::LookInput);
	EIC->BindAction(In->StickLook, ETriggerEvent::Triggered, this, &AASTRACharacter::LookInput);
	EIC->BindAction(In->Sprint, ETriggerEvent::Started, this, &AASTRACharacter::SprintStart);
	EIC->BindAction(In->Sprint, ETriggerEvent::Completed, this, &AASTRACharacter::SprintEnd);
	EIC->BindAction(In->Crouch, ETriggerEvent::Started, this, &AASTRACharacter::CrouchPressed);
	EIC->BindAction(In->Crouch, ETriggerEvent::Completed, this, &AASTRACharacter::CrouchReleased);
	// ABBORDAGGI: the weapons (UAstraFpsComponent)
	if (Fps)
	{
		EIC->BindAction(In->Fire, ETriggerEvent::Started, Fps, &UAstraFpsComponent::FirePressed);
		EIC->BindAction(In->Fire, ETriggerEvent::Completed, Fps, &UAstraFpsComponent::FireReleased);
		EIC->BindAction(In->Aim, ETriggerEvent::Started, Fps, &UAstraFpsComponent::AimPressed);
		EIC->BindAction(In->Aim, ETriggerEvent::Completed, Fps, &UAstraFpsComponent::AimReleased);
		EIC->BindAction(In->Reload, ETriggerEvent::Started, Fps, &UAstraFpsComponent::ReloadPressed);
		EIC->BindAction(In->Weapon1, ETriggerEvent::Started, Fps, &UAstraFpsComponent::SelectRifle);
		EIC->BindAction(In->Weapon2, ETriggerEvent::Started, Fps, &UAstraFpsComponent::SelectPistol);
		EIC->BindAction(In->QuickSwitch, ETriggerEvent::Started, Fps, &UAstraFpsComponent::QuickSwitch);
		EIC->BindAction(In->Holster, ETriggerEvent::Started, Fps, &UAstraFpsComponent::ToggleHolster);
		EIC->BindAction(In->WeaponWheel, ETriggerEvent::Triggered, Fps, &UAstraFpsComponent::WheelInput);
	}
}


void AASTRACharacter::MoveInput(const FInputActionValue& Value)
{
	const FVector2D MovementVector = Value.Get<FVector2D>();
	// in the chair, walking away means standing up
	if (AASTRAPlayerController* PC = Cast<AASTRAPlayerController>(GetController()))
	{
		if (PC->IsSeated())
		{
			if (MovementVector.Size() > 0.5f)
			{
				PC->StandUp();
			}
			return;
		}
	}
	// on a Jefferies ladder: W and S climb and go down (AstraLadderSubsystem places him while he climbs)
	if (UAstraLadderSubsystem* Ladder = GetWorld() ? GetWorld()->GetSubsystem<UAstraLadderSubsystem>() : nullptr; Ladder && Ladder->ClimbInput(this, MovementVector))
	{
		return;
	}
	DoMove(MovementVector.X, MovementVector.Y);
}

void AASTRACharacter::LookInput(const FInputActionValue& Value)
{
	// ABBORDAGGI: through the sights the turn is slower, as the field of view is narrower
	const float Scale = Fps ? Fps->LookMultiplier() : 1.f;
	const FVector2D LookAxisVector = Value.Get<FVector2D>() * Scale;
	DoAim(LookAxisVector.X, LookAxisVector.Y);
}

void AASTRACharacter::DoAim(float Yaw, float Pitch)
{
	if (GetController())
	{
		// pass the rotation inputs
		AddControllerYawInput(Yaw);
		AddControllerPitchInput(Pitch);
	}
}

void AASTRACharacter::DoMove(float Right, float Forward)
{
	if (GetController())
	{
		// pass the move inputs
		AddMovementInput(GetActorRightVector(), Right);
		AddMovementInput(GetActorForwardVector(), Forward);
	}
}

void AASTRACharacter::DoJumpStart()
{
	// low down, Space first brings the Captain back up
	if (Posture != EAstraPosture::Standing)
	{
		SetPosture(Posture == EAstraPosture::Prone ? EAstraPosture::Crouched : EAstraPosture::Standing);
		return;
	}
	Jump();
}

void AASTRACharacter::DoJumpEnd()
{
	// pass StopJumping to the character
	StopJumping();
}

void AASTRACharacter::CrouchPressed()
{
	CrouchDownAt = GetWorld()->GetTimeSeconds();
	bCrouchHoldDone = false;
}

void AASTRACharacter::CrouchReleased()
{
	if (!bCrouchHoldDone && CrouchDownAt >= 0.0)
	{
		// a tap: down to a crouch, or back up
		SetPosture(Posture == EAstraPosture::Crouched ? EAstraPosture::Standing : EAstraPosture::Crouched);
	}
	CrouchDownAt = -1.0;
}

void AASTRACharacter::ResetPosture()
{
	if (Posture != EAstraPosture::Standing)
	{
		SetPosture(EAstraPosture::Standing);
	}
	EyeZ = StandEyes - StandHalfHeight;
	FirstPersonCameraComponent->SetRelativeLocation(FVector(0.f, 0.f, EyeZ));
	CrouchDownAt = -1.0;
}

bool AASTRACharacter::RoomToGrow(float NewHalfHeight) const
{
	const UCapsuleComponent* Cap = GetCapsuleComponent();
	const float Half = Cap->GetUnscaledCapsuleHalfHeight();
	if (NewHalfHeight <= Half)
	{
		return true;
	}
	// the taller capsule, standing on the same floor, must not touch anything
	const FVector At = GetActorLocation() + FVector(0.f, 0.f, NewHalfHeight - Half + 1.f);
	FCollisionQueryParams Q(SCENE_QUERY_STAT(AstraPosture), false, this);
	return !GetWorld()->OverlapBlockingTestByChannel(At, FQuat::Identity, Cap->GetCollisionObjectType(),
	                                                 FCollisionShape::MakeCapsule(Cap->GetUnscaledCapsuleRadius() - 1.f, NewHalfHeight), Q);
}

void AASTRACharacter::SetPosture(EAstraPosture New)
{
	if (New == Posture || GetCharacterMovement()->MovementMode == MOVE_None)
	{
		return;
	}
	const float NewHalf = New == EAstraPosture::Standing ? StandHalfHeight : New == EAstraPosture::Crouched ? CrouchHalfHeight : ProneHalfHeight;
	if (!RoomToGrow(NewHalf))
	{
		return;                    // a low ceiling, a console overhead: stay down
	}
	UCapsuleComponent* Cap = GetCapsuleComponent();
	const float OldHalf = Cap->GetUnscaledCapsuleHalfHeight();
	// the feet stay where they are: the centre moves by the change of half-height, and the body mesh with it
	const FVector MeshAt = GetMesh()->GetRelativeLocation();
	Cap->SetCapsuleHalfHeight(NewHalf, true);
	AddActorWorldOffset(FVector(0.f, 0.f, NewHalf - OldHalf), false, nullptr, ETeleportType::TeleportPhysics);
	GetMesh()->SetRelativeLocation(MeshAt + FVector(0.f, 0.f, OldHalf - NewHalf));
	// the eyes keep their height above the floor this instant, then ease to the new posture's (no jump)
	EyeZ += OldHalf - NewHalf;
	Posture = New;
}

float AASTRACharacter::TargetEyeZ() const
{
	const float Eyes = Posture == EAstraPosture::Standing ? StandEyes : Posture == EAstraPosture::Crouched ? CrouchEyes : ProneEyes;
	return Eyes - GetCapsuleComponent()->GetUnscaledCapsuleHalfHeight();
}

void AASTRACharacter::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	// C held long enough: lie down (or, lying, get up to a crouch)
	if (CrouchDownAt >= 0.0 && !bCrouchHoldDone && GetWorld()->GetTimeSeconds() - CrouchDownAt >= HoldToLieDown)
	{
		bCrouchHoldDone = true;
		SetPosture(Posture == EAstraPosture::Prone ? EAstraPosture::Crouched : EAstraPosture::Prone);
	}
	UCharacterMovementComponent* Move = GetCharacterMovement();
	const bool bMovingForward = FVector::DotProduct(GetVelocity(), GetActorForwardVector()) > 50.f;
	// running from a crouch stands the Captain up
	if (bSprintHeld && bMovingForward && Posture == EAstraPosture::Crouched)
	{
		SetPosture(EAstraPosture::Standing);
	}
	const float Want = Posture == EAstraPosture::Prone ? ProneSpeed : Posture == EAstraPosture::Crouched ? CrouchSpeed
	                 : (bSprintHeld && bMovingForward ? SprintSpeed : WalkSpeed);
	// ABBORDAGGI: a weapon in the hands slows him (through the sights, more)
	Move->MaxWalkSpeed = FMath::FInterpTo(Move->MaxWalkSpeed, Want * (Fps ? Fps->MoveMultiplier() : 1.f), DeltaSeconds, 6.f);
	const float Target = TargetEyeZ();
	if (!FMath::IsNearlyEqual(EyeZ, Target, 0.1f))
	{
		EyeZ = FMath::FInterpTo(EyeZ, Target, DeltaSeconds, 9.f);
		FirstPersonCameraComponent->SetRelativeLocation(FVector(0.f, 0.f, EyeZ));
	}
}
