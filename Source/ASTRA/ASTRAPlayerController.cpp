// Copyright Epic Games, Inc. All Rights Reserved.


#include "ASTRAPlayerController.h"
#include "AstraCampaign.h"
#include "EnhancedInputSubsystems.h"
#include "Engine/LocalPlayer.h"
#include "InputMappingContext.h"
#include "ASTRACameraManager.h"
#include "Blueprint/UserWidget.h"
#include "ASTRA.h"
#include "Widgets/Input/SVirtualJoystick.h"
#include "AstraMindSubsystem.h"
#include "Camera/CameraComponent.h"
#include "Engine/GameInstance.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "TimerManager.h"

AASTRAPlayerController::AASTRAPlayerController()
{
	// set the player camera manager class
	PlayerCameraManagerClass = AASTRACameraManager::StaticClass();
}

void AASTRAPlayerController::BeginPlay()
{
	Super::BeginPlay();
	if (IsLocalPlayerController() && bStartSeated)
	{
		// the Captain starts in the chair (the pawn is possessed right after BeginPlay)
		GetWorldTimerManager().SetTimer(SeatTimer, FTimerDelegate::CreateUObject(this, &AASTRAPlayerController::SetSeated, true), 0.3f, false);
	}

	
	// only spawn touch controls on local player controllers
	if (IsLocalPlayerController() && ShouldUseTouchControls())
	{
		// spawn the mobile controls widget
		MobileControlsWidget = CreateWidget<UUserWidget>(this, MobileControlsWidgetClass);

		if (MobileControlsWidget)
		{
			// add the controls to the player screen
			MobileControlsWidget->AddToPlayerScreen(0);

		} else {

			UE_LOG(LogASTRA, Error, TEXT("Could not spawn mobile controls widget."));

		}

	}
}

void AASTRAPlayerController::SetupInputComponent()
{
	Super::SetupInputComponent();

	// push-to-talk to the bridge crew
	if (IsLocalPlayerController() && InputComponent)
	{
		InputComponent->BindKey(EKeys::V, IE_Pressed, this, &AASTRAPlayerController::OnTalkPressed);
		InputComponent->BindKey(EKeys::V, IE_Released, this, &AASTRAPlayerController::OnTalkReleased);
		InputComponent->BindKey(EKeys::E, IE_Pressed, this, &AASTRAPlayerController::ToggleSeat);
		// the campaign menu (the game pauses behind it)
		InputComponent->BindKey(EKeys::Escape, IE_Pressed, this, &AASTRAPlayerController::OpenMenu);
		InputComponent->BindKey(EKeys::F10, IE_Pressed, this, &AASTRAPlayerController::OpenMenu);
	}

	// only add IMCs for local player controllers
	if (IsLocalPlayerController())
	{
		// Add Input Mapping Context
		if (UEnhancedInputLocalPlayerSubsystem* Subsystem = ULocalPlayer::GetSubsystem<UEnhancedInputLocalPlayerSubsystem>(GetLocalPlayer()))
		{
			for (UInputMappingContext* CurrentContext : DefaultMappingContexts)
			{
				Subsystem->AddMappingContext(CurrentContext, 0);
			}

			// only add these IMCs if we're not using mobile touch input
			if (!ShouldUseTouchControls())
			{
				for (UInputMappingContext* CurrentContext : MobileExcludedMappingContexts)
				{
					Subsystem->AddMappingContext(CurrentContext, 0);
				}
			}
		}
	}
	
}

bool AASTRAPlayerController::ShouldUseTouchControls() const
{
	// are we on a mobile platform? Should we force touch?
	return SVirtualJoystick::ShouldDisplayTouchInterface() || bForceTouchControls;
}

void AASTRAPlayerController::OnTalkPressed()
{
	if (UAstraMindSubsystem* Mind = GetGameInstance() ? GetGameInstance()->GetSubsystem<UAstraMindSubsystem>() : nullptr)
	{
		Mind->PushToTalk(true);
	}
}

void AASTRAPlayerController::OnTalkReleased()
{
	if (UAstraMindSubsystem* Mind = GetGameInstance() ? GetGameInstance()->GetSubsystem<UAstraMindSubsystem>() : nullptr)
	{
		Mind->PushToTalk(false);
	}
}

void AASTRAPlayerController::ToggleSeat()
{
	const APawn* P = GetPawn();
	if (!P)
	{
		return;
	}
	if (bSeated)
	{
		SetSeated(false);
	}
	else if (FVector::Dist2D(P->GetActorLocation(), CaptainSeat) < 220.f)
	{
		SetSeated(true);
	}
}

void AASTRAPlayerController::SetSeated(bool bSit)
{
	ACharacter* C = Cast<ACharacter>(GetPawn());
	if (!C)
	{
		return;
	}
	const UCameraComponent* Cam = C->FindComponentByClass<UCameraComponent>();
	const float EyeZ = Cam ? Cam->GetRelativeLocation().Z : 64.f;
	if (bSit)
	{
		// seated eye height about 1.18 m above the dais, a little forward of the seat back, facing the bow window
		C->SetActorEnableCollision(false);
		C->GetCharacterMovement()->DisableMovement();
		C->SetActorLocation(CaptainSeat + FVector(8.f, 0.f, 118.f - EyeZ), false, nullptr, ETeleportType::TeleportPhysics);
		SetControlRotation(FRotator(-6.f, 0.f, 0.f));
		SetIgnoreMoveInput(true);
	}
	else
	{
		SetIgnoreMoveInput(false);
		C->SetActorLocation(CaptainSeat + FVector(-85.f, 0.f, C->GetDefaultHalfHeight() + 2.f), false, nullptr, ETeleportType::TeleportPhysics);
		C->SetActorEnableCollision(true);
		C->GetCharacterMovement()->SetMovementMode(MOVE_Walking);
	}
	bSeated = bSit;
}

void AASTRAPlayerController::OpenMenu()
{
	if (UAstraCampaignSubsystem* C = GetWorld() ? GetWorld()->GetSubsystem<UAstraCampaignSubsystem>() : nullptr)
	{
		if (C->IsStarted() && !C->IsMenuOpen())
		{
			C->ShowMenu(true);
		}
	}
}
