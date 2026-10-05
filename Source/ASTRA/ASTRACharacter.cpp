// Copyright Epic Games, Inc. All Rights Reserved.

#include "ASTRACharacter.h"
#include "AstraSettings.h"
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
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshActor.h"
#include "EngineUtils.h"
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
	// the lean: a head and shoulders out from a corner (the arms and the weapon with them): how far the eyes go out of the line of the body, how far they come down, how far the picture rolls
	constexpr float LeanOutCm = 34.f;
	constexpr float LeanDownCm = 7.f;
	constexpr float LeanRollMaxDeg = 11.f;
	constexpr float LeanProneShare = 0.55f;  // lying he can only turn out: just over half
	constexpr float LeanRateOut = 8.f;       // 1/s of the easing (a lean takes a third of a second)
	constexpr float LeanRateBack = 11.f;     // and coming back is a little quicker
	constexpr float LeanSweepRadiusCm = 12.f;      // the eyes' margin from a wall (the near plane and some air)
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
	FirstPersonCameraComponent->SetFieldOfView(FAstraSettings::Get().Fov);       // (the player's FIELD OF VIEW: SETTINGS)
	UCharacterMovementComponent* Move = GetCharacterMovement();
	Move->MaxWalkSpeed = WalkSpeed;
	Move->MaxAcceleration = 1800.f;
	Move->BrakingDecelerationWalking = 2400.f;
	Move->GroundFriction = 9.f;
	Move->JumpZVelocity = 380.f;
	// the ship's outside skin is no wall for a man on foot inside her: the decks run within the hull and the island's blocks, and where a lift's shaft
	// crosses the skin (the bridge lifts go down from the island into the hull) its surfaces held the Captain while the car went on without him
	for (TActorIterator<AStaticMeshActor> It(GetWorld()); It; ++It)
	{
		const UStaticMeshComponent* SM = It->GetStaticMeshComponent();
		if (SM && SM->GetStaticMesh() && SM->GetStaticMesh()->GetName().StartsWith(TEXT("SM_SHIP_ASTRA_Aquila")))
		{
			GetCapsuleComponent()->IgnoreActorWhenMoving(*It, true);
		}
	}
}

void AASTRACharacter::PossessedBy(AController* NewController)
{
	Super::PossessedBy(NewController);
	// a lean key that was held when he left the body (a Falcon's cockpit took the input) does not lean him when he is back: its release went to the other pawn
	bLeanLeft = bLeanRight = false;
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
	EIC->BindAction(In->LeanLeft, ETriggerEvent::Started, this, &AASTRACharacter::LeanLeftStart);
	EIC->BindAction(In->LeanLeft, ETriggerEvent::Completed, this, &AASTRACharacter::LeanLeftEnd);
	EIC->BindAction(In->LeanRight, ETriggerEvent::Started, this, &AASTRACharacter::LeanRightStart);
	EIC->BindAction(In->LeanRight, ETriggerEvent::Completed, this, &AASTRACharacter::LeanRightEnd);
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
	const float Scale = (Fps ? Fps->LookMultiplier() : 1.f) * FAstraSettings::Get().MouseSensitivity;      // (and the player's MOUSE SPEED)
	const FVector2D LookAxisVector = Value.Get<FVector2D>() * Scale;
	DoAim(LookAxisVector.X, FAstraSettings::Get().bInvertMouse ? -LookAxisVector.Y : LookAxisVector.Y);
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
	// and no lean: the eyes are on the body's line and the picture is level (the roll is the control rotation's)
	bLeanLeft = bLeanRight = false;
	Lean = LeanSideCm = LeanDropCm = LeanRollDeg = 0.f;
	FirstPersonCameraComponent->SetRelativeLocation(FVector(0.f, 0.f, EyeZ));
	if (AController* PC = GetController())
	{
		FRotator R = PC->GetControlRotation();
		if (!FMath::IsNearlyZero(FRotator::NormalizeAxis(R.Roll), 0.02f))
		{
			R.Roll = 0.f;
			PC->SetControlRotation(R);
		}
	}
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
	}
	TickLean(DeltaSeconds);                              // (places the camera: the posture's height and the lean's offset)
}

// ================================================================================================================== the lean

void AASTRACharacter::LeanFrame(float Lean, EAstraPosture Posture, float& OutSideCm, float& OutDropCm, float& OutRollDeg)
{
	const float L = FMath::Clamp(Lean, -1.f, 1.f);
	const float Share = Posture == EAstraPosture::Prone ? LeanProneShare : 1.f;
	OutSideCm = L * LeanOutCm * Share;
	OutDropCm = FMath::Abs(L) * LeanDownCm * Share;            // the head tips as well as moves
	OutRollDeg = L * LeanRollMaxDeg * Share;
}

float AASTRACharacter::LeanStep(float Lean, float Target, float Dt)
{
	// out at one rate, back at another: an eased approach that does not overshoot
	const bool bBack = FMath::Abs(Target) < FMath::Abs(Lean) || FMath::Sign(Target) != FMath::Sign(Lean);
	const float Next = FMath::FInterpTo(Lean, Target, Dt, bBack ? LeanRateBack : LeanRateOut);
	return FMath::IsNearlyEqual(Next, Target, 0.002f) ? Target : Next;
}

bool AASTRACharacter::CanLean() const
{
	const AASTRAPlayerController* PC = Cast<AASTRAPlayerController>(GetController());
	if (!PC || PC->IsSeated() || PC->IsPadUp() || PC->IsMoveInputIgnored())
	{
		return false;                                        // in the chair, reading the datapad, in a lift's list: the body is not his to bend
	}
	const UCharacterMovementComponent* Move = GetCharacterMovement();
	if (!Move || Move->MovementMode == MOVE_None || Move->IsFalling())
	{
		return false;                                        // carried (a lift's car, the transporter), or in the air
	}
	if (IsSprinting() && GetVelocity().Size2D() > 120.f)
	{
		return false;                                        // running with the weapon down
	}
	const UAstraLadderSubsystem* Ladder = GetWorld() ? GetWorld()->GetSubsystem<UAstraLadderSubsystem>() : nullptr;
	return !(Ladder && Ladder->IsClimbing(this));
}

float AASTRACharacter::LeanReach(float Side) const
{
	UWorld* W = GetWorld();
	if (!W || FMath::IsNearlyZero(Side))
	{
		return 1.f;
	}
	// from where the eyes rest to where a full lean puts them: the room is what the swept sphere finds (the camera channel: the level, not the soldiers)
	float SideCm, DropCm, RollDeg;
	LeanFrame(Side > 0.f ? 1.f : -1.f, Posture, SideCm, DropCm, RollDeg);
	const FVector Rest = GetActorLocation() + FVector(0.f, 0.f, EyeZ);
	const FVector Out = Rest + GetActorRightVector() * SideCm - FVector(0.f, 0.f, DropCm);
	FCollisionQueryParams Q(SCENE_QUERY_STAT(AstraLean), false, this);
	FHitResult Hit;
	if (!W->SweepSingleByChannel(Hit, Rest, Out, FQuat::Identity, ECC_Camera, FCollisionShape::MakeSphere(LeanSweepRadiusCm), Q))
	{
		return 1.f;
	}
	return Hit.bStartPenetrating ? 0.f : FMath::Clamp(Hit.Time, 0.f, 1.f);
}

void AASTRACharacter::TickLean(float Dt)
{
	// what he asks for, if the body may
	const bool bLocal = IsLocallyControlled();
	const float Want = bLocal && CanLean() ? (bLeanRight ? 1.f : 0.f) - (bLeanLeft ? 1.f : 0.f) : 0.f;
	const float WantReach = Want != 0.f ? LeanReach(Want) : 1.f;
	Lean = LeanStep(Lean, Want * WantReach, Dt);
	if (Lean != 0.f)
	{
		// never into a wall: held to the room on its own side (the body may have walked towards it)
		const float Side = FMath::Sign(Lean);
		const float Reach = Side == FMath::Sign(Want) ? WantReach : LeanReach(Side);
		Lean = Side * FMath::Min(FMath::Abs(Lean), Reach);
	}
	LeanFrame(Lean, Posture, LeanSideCm, LeanDropCm, LeanRollDeg);
	// the camera: the posture's height, the lean's offset
	const FVector Rel(0.f, LeanSideCm, EyeZ - LeanDropCm);
	if (!FirstPersonCameraComponent->GetRelativeLocation().Equals(Rel, 0.01f))
	{
		FirstPersonCameraComponent->SetRelativeLocation(Rel);
	}
	// the picture's roll is the control rotation's: the camera follows it, and the arms and the weapon ride the camera, so everything leans together; the rounds go where it looks
	AController* PC = bLocal ? GetController() : nullptr;
	if (PC)
	{
		FRotator R = PC->GetControlRotation();
		if (!FMath::IsNearlyEqual(FRotator::NormalizeAxis(R.Roll), LeanRollDeg, 0.02f))
		{
			R.Roll = LeanRollDeg;
			PC->SetControlRotation(R);
		}
	}
}
