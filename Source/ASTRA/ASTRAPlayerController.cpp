// Copyright Epic Games, Inc. All Rights Reserved.


#include "ASTRAPlayerController.h"
#include "Widgets/SBoxPanel.h"
#include "Styling/CoreStyle.h"
#include "Widgets/Text/STextBlock.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Engine/GameViewportClient.h"
#include "Engine/Font.h"
#include "AstraCampaign.h"
#include "AstraFighterPawn.h"
#include "AstraHangar.h"
#include "AstraShipSubsystem.h"
#include "EngineUtils.h"
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
	if (IsLocalPlayerController())
	{
		GetWorldTimerManager().SetTimerForNextTick([this]()
		{
			UGameViewportClient* VC = GetWorld() ? GetWorld()->GetGameViewport() : nullptr;
			if (!VC || HintWidget.IsValid())
			{
				return;
			}
			UFont* Mono = LoadObject<UFont>(nullptr, TEXT("/Game/ASTRA/UI/Fonts/F_ASTRA_Mono.F_ASTRA_Mono"));
			HintWidget = SNew(SBox).HAlign(HAlign_Right).VAlign(VAlign_Bottom).Padding(FMargin(0, 0, 28, 22))
			[
				SNew(SBorder).BorderImage(FCoreStyle::Get().GetBrush("WhiteBrush")).BorderBackgroundColor(FLinearColor(0.004f, 0.006f, 0.01f, 0.7f))
				.Padding(FMargin(14, 8))
				[
					SNew(STextBlock).Font(Mono ? FSlateFontInfo(Mono, 13) : FCoreStyle::GetDefaultFontStyle("Mono", 13))
					.ColorAndOpacity(FLinearColor(0.82f, 0.88f, 0.95f, 0.95f)).Text(FText::FromString(TEXT("F1  controls  ·  hold V  talk to the crew")))
				]
			];
			VC->AddViewportWidgetContent(HintWidget.ToSharedRef(), 5);
			GetWorldTimerManager().SetTimer(HintTimer, [this]()
			{
				if (HintWidget.IsValid() && GetWorld() && GetWorld()->GetGameViewport())
				{
					GetWorld()->GetGameViewport()->RemoveViewportWidgetContent(HintWidget.ToSharedRef());
					HintWidget.Reset();
				}
			}, 45.f, false);
		});
	}
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
		InputComponent->BindKey(EKeys::E, IE_Pressed, this, &AASTRAPlayerController::ToggleSeat).bConsumeInput = false;   // a Falcon uses E too
		// the campaign menu (the game pauses behind it)
		InputComponent->BindKey(EKeys::Escape, IE_Pressed, this, &AASTRAPlayerController::OpenMenu);
		InputComponent->BindKey(EKeys::F10, IE_Pressed, this, &AASTRAPlayerController::OpenMenu);
		InputComponent->BindKey(EKeys::F1, IE_Pressed, this, &AASTRAPlayerController::ToggleHelp);
		// the lift's panel (only while it is open)
		auto Deck = [this](const FKey& K, int32 N)
		{
			FInputKeyBinding B(FInputChord(K), IE_Pressed);
			B.bConsumeInput = false;
			B.KeyDelegate.GetDelegateForManualSet().BindLambda([this, N]() { if (LiftMenu.IsValid()) { ChooseDeck(N); } });
			InputComponent->KeyBindings.Add(B);
		};
		Deck(EKeys::One, 1);
		Deck(EKeys::Two, 2);
		Deck(EKeys::Three, 3);
		Deck(EKeys::Four, 4);
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
	// in a Falcon: E is the pilot's (on the catapult it climbs out, in flight it is a thruster)
	if (AAstraFighterPawn* F = Cast<AAstraFighterPawn>(GetPawn()))
	{
		F->ClimbOut();
		return;
	}
	// on New Ravenna: back into the parked Falcon
	if (APawn* Me = GetPawn())
	{
		for (TActorIterator<AAstraFighterPawn> It(GetWorld()); It; ++It)
		{
			if (It->IsParkedPlanetside() && FVector::Dist(It->GetActorLocation(), Me->GetActorLocation()) < 900.f)
			{
				It->Reboard(Me);
				return;
			}
		}
	}
	// the lift to the flight deck (or back up) when standing at one of its landings; a Falcon of Alpha on the deck
	if (APawn* Me = GetPawn())
	{
		if (LiftMenu.IsValid())
		{
			CloseLiftMenu();   // E again: never mind
			return;
		}
		for (TActorIterator<AAstraHangar> It(GetWorld()); It; ++It)
		{
			const int32 From = It->LiftLandingNear(Me);
			if (From >= 0)
			{
				if (It->NumLandings() > 2)
				{
					ShowLiftMenu(*It, From);
				}
				else
				{
					It->RideLift(Me, From == 0 ? 1 : 0);
				}
				return;
			}
			if (It->TryBoard(Me))
			{
				BoardFalcon(*It, Me);
				return;
			}
		}
	}
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

void AASTRAPlayerController::BoardFalcon(AAstraHangar* Hangar, APawn* Walker)
{
	// a moment of dark (climbing the ladder, strapping in), then the cockpit on Alpha's catapult
	if (PlayerCameraManager)
	{
		PlayerCameraManager->StartCameraFade(1.f, 0.f, 1.2f, FLinearColor::Black, false, false);
	}
	FActorSpawnParameters P;
	P.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	const FTransform Cradle = Hangar->CatapultPose(0.f);
	AAstraFighterPawn* F = GetWorld()->SpawnActor<AAstraFighterPawn>(AAstraFighterPawn::StaticClass(), Cradle, P);
	if (!F)
	{
		return;
	}
	Walker->SetActorHiddenInGame(true);
	Walker->SetActorEnableCollision(false);
	Possess(F);
	F->BeginOnCatapult(Hangar, Walker);
	if (UWorld* W = GetWorld())
	{
		if (UAstraShipSubsystem* Ship = W->GetSubsystem<UAstraShipSubsystem>())
		{
			Ship->PublishEvent(TEXT("flight: the Captain has climbed into a Falcon of Alpha on the port catapult"), true);
		}
	}
}

namespace
{
	const TCHAR* HelpCard =
		TEXT("ON THE BRIDGE\n")
		TEXT("  V (hold)        talk to the crew, in any language\n")
		TEXT("  E               stand up / sit down · doors · the lift\n")
		TEXT("  WASD, mouse     walk and look\n")
		TEXT("  Esc             pause · save · menu\n")
		TEXT("\n")
		TEXT("THE LIFT (at the end of the port corridor)\n")
		TEXT("  E, then 1-4     Bridge · Medbay · Main Engineering · Flight Deck\n")
		TEXT("\n")
		TEXT("ON THE FLIGHT DECK\n")
		TEXT("  E               beside a Falcon of Alpha: climb in\n")
		TEXT("  W               on the catapult: launch\n")
		TEXT("\n")
		TEXT("IN A FALCON\n")
		TEXT("  mouse           the stick (pitch, yaw)      A / D    roll\n")
		TEXT("  W / S           throttle (X: cut)           Shift    afterburner\n")
		TEXT("  Q / E           slide left / right          Space / Ctrl   up / down\n")
		TEXT("  left mouse      cannons                     right mouse    missile (locked)\n")
		TEXT("  C               decoys                      Alt      look around\n")
		TEXT("  F               near the Aquila's port bow tube, slow: recover\n")
		TEXT("  V (hold)        talk to the bridge by radio · G  facing a planet: descend\n")
		TEXT("  gamepad         left stick fly · right stick yaw/lift · triggers throttle · A guns · B missile\n")
		TEXT("                  RB boost · LB decoys · Y recover/land · X descend\n")
		TEXT("\n")
		TEXT("F1  this card");
}

namespace
{
	// the lift's decks, top to bottom, by the number on its panel: 1 the bridge (landing 0), 2 the Medbay (3), 3 Main
	// Engineering (2), 4 the flight deck (1)
	constexpr int32 NumDecks = 4;
	const int32 DeckLanding[NumDecks + 1] = {-1, 0, 3, 2, 1};
	const TCHAR* DeckName[NumDecks + 1] = {TEXT(""), TEXT("BRIDGE  ·  DECK 1"), TEXT("MEDBAY  ·  DECK 6"), TEXT("MAIN ENGINEERING  ·  DECK 7"),
	                                       TEXT("FLIGHT DECK  ·  DECK 9")};
}

void AASTRAPlayerController::ShowLiftMenu(AAstraHangar* Hangar, int32 From)
{
	UGameViewportClient* VC = GetWorld() ? GetWorld()->GetGameViewport() : nullptr;
	if (!VC || !Hangar)
	{
		return;
	}
	CloseLiftMenu();
	LiftHangar = Hangar;
	UFont* Mono = LoadObject<UFont>(nullptr, TEXT("/Game/ASTRA/UI/Fonts/F_ASTRA_Mono.F_ASTRA_Mono"));
	const FSlateFontInfo Font = Mono ? FSlateFontInfo(Mono, 18) : FCoreStyle::GetDefaultFontStyle("Mono", 18);
	const FSlateFontInfo Small = Mono ? FSlateFontInfo(Mono, 12) : FCoreStyle::GetDefaultFontStyle("Mono", 12);
	TSharedRef<SVerticalBox> List = SNew(SVerticalBox)
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 0, 0, 12)
		[
			SNew(STextBlock).Font(Small).ColorAndOpacity(FLinearColor(0.55f, 0.75f, 1.f)).Text(FText::FromString(TEXT("LIFT  ·  ASN AQUILA")))
		];
	for (int32 N = 1; N <= NumDecks; ++N)
	{
		if (!Hangar->HasLanding(DeckLanding[N]))
		{
			continue;
		}
		const bool bHere = DeckLanding[N] == From;
		List->AddSlot().AutoHeight().Padding(0, 4)
		[
			SNew(STextBlock).Font(Font).ColorAndOpacity(bHere ? FLinearColor(0.5f, 0.55f, 0.6f, 0.7f) : FLinearColor(0.88f, 0.92f, 0.97f))
			.Text(FText::FromString(FString::Printf(TEXT("%d   %s%s"), N, DeckName[N], bHere ? TEXT("   (here)") : TEXT(""))))
		];
	}
	List->AddSlot().AutoHeight().Padding(0, 12, 0, 0)
	[
		SNew(STextBlock).Font(Small).ColorAndOpacity(FLinearColor(0.6f, 0.65f, 0.7f)).Text(FText::FromString(TEXT("press a number  ·  E to stay")))
	];
	LiftMenu = SNew(SBox).HAlign(HAlign_Center).VAlign(VAlign_Center)
	[
		SNew(SBorder).BorderImage(FCoreStyle::Get().GetBrush("WhiteBrush")).BorderBackgroundColor(FLinearColor(0.004f, 0.006f, 0.01f, 0.88f))
		.Padding(FMargin(36, 26))
		[
			List
		]
	];
	VC->AddViewportWidgetContent(LiftMenu.ToSharedRef(), 45);
}

void AASTRAPlayerController::CloseLiftMenu()
{
	if (LiftMenu.IsValid() && GetWorld() && GetWorld()->GetGameViewport())
	{
		GetWorld()->GetGameViewport()->RemoveViewportWidgetContent(LiftMenu.ToSharedRef());
	}
	LiftMenu.Reset();
}

void AASTRAPlayerController::ChooseDeck(int32 Number)
{
	AAstraHangar* H = LiftHangar.Get();
	CloseLiftMenu();
	if (H && GetPawn() && Number >= 1 && Number <= NumDecks)
	{
		H->RideLift(GetPawn(), DeckLanding[Number]);
	}
}

void AASTRAPlayerController::ToggleHelp()
{
	ShowHelp(!HelpWidget.IsValid());
}

void AASTRAPlayerController::ShowHelp(bool bShow)
{
	UGameViewportClient* VC = GetWorld() ? GetWorld()->GetGameViewport() : nullptr;
	if (!VC)
	{
		return;
	}
	if (HintWidget.IsValid())
	{
		VC->RemoveViewportWidgetContent(HintWidget.ToSharedRef());
		HintWidget.Reset();
	}
	if (!bShow && HelpWidget.IsValid())
	{
		VC->RemoveViewportWidgetContent(HelpWidget.ToSharedRef());
		HelpWidget.Reset();
		return;
	}
	if (bShow && !HelpWidget.IsValid())
	{
		UFont* Mono = LoadObject<UFont>(nullptr, TEXT("/Game/ASTRA/UI/Fonts/F_ASTRA_Mono.F_ASTRA_Mono"));
		const FSlateFontInfo Font = Mono ? FSlateFontInfo(Mono, 14) : FCoreStyle::GetDefaultFontStyle("Mono", 14);
		HelpWidget = SNew(SBox).HAlign(HAlign_Center).VAlign(VAlign_Center)
		[
			SNew(SBorder).BorderImage(FCoreStyle::Get().GetBrush("WhiteBrush")).BorderBackgroundColor(FLinearColor(0.004f, 0.006f, 0.01f, 0.85f))
			.Padding(FMargin(40, 30))
			[
				SNew(STextBlock).Font(Font).ColorAndOpacity(FLinearColor(0.82f, 0.88f, 0.95f)).Text(FText::FromString(HelpCard))
			]
		];
		VC->AddViewportWidgetContent(HelpWidget.ToSharedRef(), 40);
	}
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
