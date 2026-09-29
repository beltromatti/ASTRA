// Copyright Epic Games, Inc. All Rights Reserved.


#include "ASTRAPlayerController.h"
#include "Widgets/SBoxPanel.h"
#include "Styling/CoreStyle.h"
#include "Widgets/Text/STextBlock.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/SOverlay.h"
#include "Widgets/Input/SEditableTextBox.h"
#include "Framework/Application/SlateApplication.h"
#include "Engine/GameViewportClient.h"
#include "Engine/Font.h"
#include "AstraCampaign.h"
#include "AstraFighterPawn.h"
#include "AstraHangar.h"
#include "AstraLifepod.h"
#include "AstraQuarters.h"
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
#include "AstraScreensSubsystem.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/TextureRenderTarget2D.h"
#include "Materials/MaterialInstanceDynamic.h"
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
					.ColorAndOpacity(FLinearColor(0.82f, 0.88f, 0.95f, 0.95f)).Text(FText::FromString(TEXT("F1  controls  ·  hold V  talk to the crew  ·  T  type")))
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
		InputComponent->BindKey(EKeys::T, IE_Pressed, this, &AASTRAPlayerController::OnTypePressed);
		InputComponent->BindKey(EKeys::Tab, IE_Pressed, this, &AASTRAPlayerController::TogglePad);
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
		Deck(EKeys::Five, 5);
		Deck(EKeys::Six, 6);
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
	// a lifepod's hatch: sealed, or (abandoning ship) the way off her
	if (APawn* Me = GetPawn())
	{
		for (TActorIterator<AAstraLifepodHatch> It(GetWorld()); It; ++It)
		{
			if (It->IsWithinReach(Me))
			{
				UAstraShipSubsystem* Ship = GetWorld()->GetSubsystem<UAstraShipSubsystem>();
				if (Ship && Ship->IsAbandoning())
				{
					Ship->BoardLifepod(*It, this);
				}
				else
				{
					Subtitle(-1 - It->PodName.Len(), TEXT("notice"), FString::Printf(TEXT("LIFEPOD %s"), *It->PodName),
					         TEXT("Sealed. It opens on ABANDON SHIP."));
				}
				return;
			}
		}
	}
	// the Captain's quarters: the bunk (lie down to rest, or get up)
	if (APawn* Me = GetPawn())
	{
		for (TActorIterator<AAstraQuarters> It(GetWorld()); It; ++It)
		{
			if (It->TryRest(Me))
			{
				return;
			}
		}
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

void AASTRAPlayerController::TickPad(float DeltaTime)
{
	// held up in the left hand below the line of sight, tilted to face the eye; only on foot (a Falcon has its own
	// instruments). Its page is painted only while it is up.
	ACharacter* Me = Cast<ACharacter>(GetPawn());
	PadAlpha = FMath::FInterpConstantTo(PadAlpha, (bPadUp && Me) ? 1.f : 0.f, DeltaTime, 4.f);
	UAstraScreensSubsystem* Screens = GetWorld() ? GetWorld()->GetSubsystem<UAstraScreensSubsystem>() : nullptr;
	if (Screens)
	{
		Screens->SetPadVisible(PadAlpha > 0.f);
	}
	UCameraComponent* Cam = Me ? Me->FindComponentByClass<UCameraComponent>() : nullptr;
	if (PadAlpha <= 0.f || !Cam)
	{
		if (PadMesh)
		{
			PadMesh->SetVisibility(false);
		}
		return;
	}
	if (!PadMesh || PadMesh->GetOwner() != Me)
	{
		if (PadMesh)
		{
			PadMesh->DestroyComponent();
		}
		PadMesh = NewObject<UStaticMeshComponent>(Me, TEXT("CaptainDatapad"));
		PadMesh->SetStaticMesh(LoadObject<UStaticMesh>(nullptr, TEXT("/Game/ASTRA/Kit/Props/SM_PROP_Datapad.SM_PROP_Datapad")));
		PadMesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		PadMesh->SetCastShadow(false);
		PadMesh->SetupAttachment(Cam);
		PadMesh->RegisterComponent();
		const int32 Slot = PadMesh->GetMaterialIndex(TEXT("MI_PAD_Screen"));
		UTextureRenderTarget2D* Page = Screens ? Screens->GetPadTarget() : nullptr;
		if (Slot != INDEX_NONE && Page)
		{
			if (UMaterialInstanceDynamic* M = PadMesh->CreateDynamicMaterialInstance(Slot))
			{
				M->SetTextureParameterValue(TEXT("ScreenTexture"), Page);
			}
		}
	}
	const float A = FMath::InterpEaseInOut(0.f, 1.f, PadAlpha, 2.f);
	const FVector Down(20.f, -14.f, -44.f), Up(27.f, -5.f, -8.5f);
	const FQuat RDown = FRotator(-70.f, -10.f, 8.f).Quaternion(), RUp = FRotator(-17.f, -10.f, 3.f).Quaternion();
	PadMesh->SetRelativeLocationAndRotation(FMath::Lerp(Down, Up, A), FQuat::Slerp(RDown, RUp, A));
	PadMesh->SetVisibility(true);
}

namespace
{
	const TCHAR* HelpCard =
		TEXT("ON THE BRIDGE\n")
		TEXT("  V (hold)        talk to the crew, in any language\n")
		TEXT("  T               type to the crew instead (Enter sends, Esc cancels)\n")
		TEXT("  Tab             the datapad: the ship at a glance, anywhere aboard\n")
		TEXT("  E               stand up / sit down · doors · the lift\n")
		TEXT("  WASD, mouse     walk and look\n")
		TEXT("  Esc             pause · save · menu\n")
		TEXT("\n")
		TEXT("THE LIFT (at the end of the port corridor)\n")
		TEXT("  E, then 1-6     Bridge · Crew Berthing · Mess Hall · Medbay · Main Engineering · Flight Deck\n")
		TEXT("  the Captain's quarters: the door at the end of the starboard corridor;\n")
		TEXT("  E beside the bunk to rest (the XO wakes you if anything happens)\n")
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
	// the lift's decks, top to bottom, by the number on its panel: 1 the bridge (landing 0), 2 the Mess Hall (4), 3 the
	// Medbay (3), 4 Main Engineering (2), 5 the flight deck (1)
	constexpr int32 NumDecks = 6;
	const int32 DeckLanding[NumDecks + 1] = {-1, 0, 5, 4, 3, 2, 1};
	const TCHAR* DeckName[NumDecks + 1] = {TEXT(""), TEXT("BRIDGE  ·  DECK 1"), TEXT("CREW BERTHING  ·  DECK 3"), TEXT("MESS HALL  ·  DECK 4"),
	                                       TEXT("MEDBAY  ·  DECK 6"), TEXT("MAIN ENGINEERING  ·  DECK 7"), TEXT("FLIGHT DECK  ·  DECK 9")};
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

void AASTRAPlayerController::EnsureStoryWidget()
{
	UGameViewportClient* VC = GetWorld() ? GetWorld()->GetGameViewport() : nullptr;
	if (!VC || StoryWidget.IsValid())
	{
		return;
	}
	UFont* Title = LoadObject<UFont>(nullptr, TEXT("/Game/ASTRA/UI/Fonts/F_ASTRA_Title.F_ASTRA_Title"));
	UFont* Mono = LoadObject<UFont>(nullptr, TEXT("/Game/ASTRA/UI/Fonts/F_ASTRA_Mono.F_ASTRA_Mono"));
	StoryWidget = SNew(SOverlay)
		+ SOverlay::Slot()
		[
			SAssignNew(StoryShade, SBorder).BorderImage(FCoreStyle::Get().GetBrush("WhiteBrush")).BorderBackgroundColor(FLinearColor(0.f, 0.f, 0.f, 0.f))
		]
		+ SOverlay::Slot().HAlign(HAlign_Center).VAlign(VAlign_Center)
		[
			SNew(SBox).MaxDesiredWidth(1100.f)
			[
				SNew(SVerticalBox)
				+ SVerticalBox::Slot().AutoHeight().HAlign(HAlign_Center).Padding(0, 0, 0, 14)
				[
					SAssignNew(StoryTitle, STextBlock).Font(Title ? FSlateFontInfo(Title, 46) : FCoreStyle::GetDefaultFontStyle("Bold", 46))
					.ColorAndOpacity(FLinearColor(0.75f, 0.88f, 1.f, 0.f)).Justification(ETextJustify::Center).AutoWrapText(true)
				]
				+ SVerticalBox::Slot().AutoHeight().HAlign(HAlign_Center)
				[
					// an epilogue line can be long: it wraps, and reads as prose
					SAssignNew(StorySub, STextBlock).Font(Mono ? FSlateFontInfo(Mono, 17) : FCoreStyle::GetDefaultFontStyle("Mono", 17))
					.ColorAndOpacity(FLinearColor(0.45f, 0.55f, 0.66f, 0.f)).Justification(ETextJustify::Center).AutoWrapText(true)
					.LineHeightPercentage(1.25f)
				]
			]
		];
	VC->AddViewportWidgetContent(StoryWidget.ToSharedRef(), 60);
}

void AASTRAPlayerController::StoryCard(const FString& Title, const FString& Sub, float Hold, bool bStayBlack, bool bStartBlack)
{
	EnsureStoryWidget();
	if (!StoryWidget.IsValid())
	{
		return;
	}
	if (bStartBlack)
	{
		StoryBlackNow = 1.f;          // a scene that opens in the dark (a new level after the loss)
	}
	StoryTitle->SetText(FText::FromString(Title));
	StorySub->SetText(FText::FromString(Sub));
	StoryTextT = 0.f;
	StoryHold = FMath::Max(1.f, Hold);
	bStoryStayBlack = bStayBlack;
	StoryBlackWant = 1.f;
	StoryFade = 1.2f;
}

void AASTRAPlayerController::StoryBlack(bool bOn, float Fade)
{
	EnsureStoryWidget();
	StoryBlackWant = bOn ? 1.f : 0.f;
	bStoryStayBlack = bOn;
	StoryFade = FMath::Max(0.05f, Fade);
}

static FLinearColor SpeakerColor(const FString& S)
{
	// the bridge's departments (the stations' colours), then the voices from outside: radio, the enemy, the story
	if (S == TEXT("xo") || S == TEXT("captain")) { return FLinearColor(0.92f, 0.94f, 1.f); }
	if (S == TEXT("helm") || S == TEXT("flight")) { return FLinearColor(0.35f, 0.62f, 1.f); }
	if (S == TEXT("ops") || S == TEXT("comms") || S == TEXT("engineering") || S == TEXT("chief")) { return FLinearColor(1.f, 0.72f, 0.25f); }
	if (S == TEXT("tactical")) { return FLinearColor(1.f, 0.36f, 0.3f); }
	if (S == TEXT("sensors") || S == TEXT("doctor")) { return FLinearColor(0.3f, 0.85f, 0.8f); }
	if (S == TEXT("admiral") || S.StartsWith(TEXT("board"))) { return FLinearColor(1.f, 0.85f, 0.45f); }
	if (S == TEXT("director")) { return FLinearColor(0.75f, 0.6f, 1.f); }
	if (S.StartsWith(TEXT("mess")) || S.StartsWith(TEXT("patient"))) { return FLinearColor(0.75f, 0.78f, 0.82f); }
	if (S == TEXT("finder") || S.Contains(TEXT("field")) || S.Contains(TEXT("port"))) { return FLinearColor(0.5f, 0.9f, 0.5f); }
	return FLinearColor(1.f, 0.45f, 0.35f);                   // the Mandate, a captor: anyone else on the channel
}

void AASTRAPlayerController::EnsureSubtitles()
{
	UGameViewportClient* VC = GetWorld() ? GetWorld()->GetGameViewport() : nullptr;
	if (!VC || SubWidget.IsValid())
	{
		return;
	}
	UFont* Mono = LoadObject<UFont>(nullptr, TEXT("/Game/ASTRA/UI/Fonts/F_ASTRA_Mono.F_ASTRA_Mono"));
	const FSlateFontInfo NameFont = Mono ? FSlateFontInfo(Mono, 14) : FCoreStyle::GetDefaultFontStyle("Bold", 14);
	const FSlateFontInfo TextFont = Mono ? FSlateFontInfo(Mono, 15) : FCoreStyle::GetDefaultFontStyle("Regular", 15);
	TSharedRef<SVerticalBox> Box = SNew(SVerticalBox);
	for (int32 i = 0; i < 3; ++i)
	{
		TSharedPtr<STextBlock> N, T;
		TSharedPtr<SBorder> Row;
		Box->AddSlot().AutoHeight().Padding(0, 3)
		[
			SAssignNew(Row, SBorder).BorderImage(FCoreStyle::Get().GetBrush("WhiteBrush")).BorderBackgroundColor(FLinearColor(0.f, 0.f, 0.f, 0.f))
			.Padding(FMargin(12, 5)).Visibility(EVisibility::Collapsed)
			[
				SNew(SHorizontalBox)
				+ SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Top).Padding(0, 0, 10, 0)
				[
					SAssignNew(N, STextBlock).Font(NameFont)
				]
				+ SHorizontalBox::Slot().FillWidth(1.f)
				[
					SAssignNew(T, STextBlock).Font(TextFont).AutoWrapText(true)
				]
			]
		];
		SubNames.Add(N);
		SubTexts.Add(T);
		SubRows.Add(Row);
	}
	SubWidget = SNew(SBox).HAlign(HAlign_Center).VAlign(VAlign_Bottom).Padding(FMargin(0, 0, 0, 60))
	[
		SNew(SBox).MaxDesiredWidth(1150.f)
		[
			Box
		]
	];
	VC->AddViewportWidgetContent(SubWidget.ToSharedRef(), 45);
}

void AASTRAPlayerController::Subtitle(int32 Id, const FString& Speaker, const FString& Name, const FString& Text)
{
	EnsureSubtitles();
	// the name as a crew would say it: the surname alone ("Vice Admiral Adrian Rourke (7th Fleet command)" -> ROURKE)
	FString Short = Name;
	int32 Paren = INDEX_NONE;
	if (Short.FindChar(TEXT('('), Paren))
	{
		Short = Short.Left(Paren);
	}
	Short.TrimStartAndEndInline();
	TArray<FString> Words;
	Short.ParseIntoArrayWS(Words);
	FSubLine L;
	L.Id = Id;
	L.Name = (Words.Num() ? Words.Last() : Short).ToUpper();
	L.Text = Text;
	L.Color = SpeakerColor(Speaker);
	SubLines.Add(L);
	while (SubLines.Num() > 3)
	{
		SubLines.RemoveAt(0);
	}
}

void AASTRAPlayerController::SubtitleEnd(int32 Id)
{
	for (FSubLine& L : SubLines)
	{
		if (L.Id == Id && L.EndAge < 0.f)
		{
			L.EndAge = L.Age;
		}
	}
}

void AASTRAPlayerController::TickSubtitles(float DeltaTime)
{
	if (!SubWidget.IsValid())
	{
		return;
	}
	for (int32 i = SubLines.Num() - 1; i >= 0; --i)
	{
		FSubLine& L = SubLines[i];
		L.Age += DeltaTime;
		// said: it stays two seconds and fades; never said (no audio came): it goes after its reading time
		const float Gone = L.EndAge >= 0.f ? L.EndAge + 2.5f : 4.f + L.Text.Len() * 0.07f;
		if (L.Age > Gone)
		{
			SubLines.RemoveAt(i);
		}
	}
	for (int32 i = 0; i < SubRows.Num(); ++i)
	{
		const bool bOn = SubLines.IsValidIndex(i);
		SubRows[i]->SetVisibility(bOn ? EVisibility::HitTestInvisible : EVisibility::Collapsed);
		if (!bOn)
		{
			continue;
		}
		const FSubLine& L = SubLines[i];
		const float Gone = L.EndAge >= 0.f ? L.EndAge + 2.5f : 4.f + L.Text.Len() * 0.07f;
		const float A = FMath::Clamp(FMath::Min(L.Age / 0.25f, (Gone - L.Age) / 0.8f), 0.f, 1.f);
		SubRows[i]->SetBorderBackgroundColor(FLinearColor(0.f, 0.005f, 0.01f, 0.62f * A));
		SubNames[i]->SetText(FText::FromString(L.Name));
		SubNames[i]->SetColorAndOpacity(FLinearColor(L.Color.R, L.Color.G, L.Color.B, A));
		SubTexts[i]->SetText(FText::FromString(L.Text));
		SubTexts[i]->SetColorAndOpacity(FLinearColor(0.92f, 0.94f, 0.97f, A));
	}
}

void AASTRAPlayerController::PlayerTick(float DeltaTime)
{
	Super::PlayerTick(DeltaTime);
	TickSubtitles(DeltaTime);
	TickPad(DeltaTime);
	if (!StoryWidget.IsValid())
	{
		return;
	}
	StoryBlackNow = FMath::FInterpConstantTo(StoryBlackNow, StoryBlackWant, DeltaTime, 1.f / StoryFade);
	float TextA = 0.f;
	if (StoryTextT >= 0.f)
	{
		// the lines come once the screen is dark: a second in, the hold, a second out
		StoryTextT += StoryBlackNow > 0.95f ? DeltaTime : 0.f;
		TextA = FMath::Clamp(FMath::Min(StoryTextT, StoryHold + 2.f - StoryTextT), 0.f, 1.f);
		if (StoryTextT > StoryHold + 2.f)
		{
			StoryTextT = -1.f;
			StoryBlackWant = bStoryStayBlack ? 1.f : 0.f;
		}
	}
	StoryShade->SetBorderBackgroundColor(FLinearColor(0.f, 0.f, 0.f, StoryBlackNow));
	StoryTitle->SetColorAndOpacity(FLinearColor(0.75f, 0.88f, 1.f, TextA));
	StorySub->SetColorAndOpacity(FLinearColor(0.45f, 0.55f, 0.66f, TextA));
	if (StoryBlackNow <= 0.f && StoryBlackWant <= 0.f && StoryTextT < 0.f)
	{
		if (UGameViewportClient* VC = GetWorld() ? GetWorld()->GetGameViewport() : nullptr)
		{
			VC->RemoveViewportWidgetContent(StoryWidget.ToSharedRef());
		}
		StoryWidget.Reset();
	}
}

void AASTRAPlayerController::OnTypePressed()
{
	GetWorldTimerManager().SetTimerForNextTick(this, &AASTRAPlayerController::OpenOrderLine);
}

void AASTRAPlayerController::AstraTypeTest(const FString& Text)
{
	OpenOrderLine();
	GetWorldTimerManager().SetTimerForNextTick([this, Text]()
	{
		FSlateApplication& App = FSlateApplication::Get();
		for (const TCHAR Ch : Text)
		{
			App.ProcessKeyCharEvent(FCharacterEvent(Ch, FModifierKeysState(), 0, false));
		}
		UE_LOG(LogASTRA, Log, TEXT("[Order line] typed: %s"), OrderBox.IsValid() ? *OrderBox->GetText().ToString() : TEXT("(no box)"));
		FTimerHandle H;
		GetWorldTimerManager().SetTimer(H, []()
		{
			FSlateApplication::Get().ProcessKeyDownEvent(FKeyEvent(EKeys::Enter, FModifierKeysState(), 0, false, 13, 13));
			FSlateApplication::Get().ProcessKeyUpEvent(FKeyEvent(EKeys::Enter, FModifierKeysState(), 0, false, 13, 13));
		}, 1.5f, false);
	});
}

void AASTRAPlayerController::OpenOrderLine()
{
	UGameViewportClient* VC = GetWorld() ? GetWorld()->GetGameViewport() : nullptr;
	if (!VC || OrderLine.IsValid() || LiftMenu.IsValid())
	{
		return;
	}
	UFont* Mono = LoadObject<UFont>(nullptr, TEXT("/Game/ASTRA/UI/Fonts/F_ASTRA_Mono.F_ASTRA_Mono"));
	const FSlateFontInfo Font = Mono ? FSlateFontInfo(Mono, 16) : FCoreStyle::GetDefaultFontStyle("Mono", 16);
	const FSlateFontInfo Small = Mono ? FSlateFontInfo(Mono, 11) : FCoreStyle::GetDefaultFontStyle("Mono", 11);
	OrderLine = SNew(SBox).HAlign(HAlign_Center).VAlign(VAlign_Bottom).Padding(FMargin(0, 0, 0, 150))
	[
		SNew(SBox).WidthOverride(900.f)
		[
			SNew(SBorder).BorderImage(FCoreStyle::Get().GetBrush("WhiteBrush")).BorderBackgroundColor(FLinearColor(0.004f, 0.006f, 0.01f, 0.82f))
			.Padding(FMargin(16, 10))
			[
				SNew(SVerticalBox)
				+ SVerticalBox::Slot().AutoHeight().Padding(0, 0, 0, 6)
				[
					SNew(STextBlock).Font(Small).ColorAndOpacity(FLinearColor(1.f, 0.84f, 0.47f, 0.9f))
					.Text(FText::FromString(TEXT("CAPTAIN  ·  to the crew, in any language  ·  Enter sends  ·  Esc cancels")))
				]
				+ SVerticalBox::Slot().AutoHeight()
				[
					SAssignNew(OrderBox, SEditableTextBox).Font(Font)
					.BackgroundColor(FLinearColor(0.02f, 0.03f, 0.045f, 1.f))
					.ForegroundColor(FLinearColor(0.9f, 0.94f, 1.f))
					.ClearKeyboardFocusOnCommit(false)
					.OnKeyDownHandler_Lambda([this](const FGeometry&, const FKeyEvent& Key)
					{
						// Esc cancels the line (unhandled, it would climb to the game and open the menu)
						if (Key.GetKey() == EKeys::Escape)
						{
							GetWorldTimerManager().SetTimerForNextTick(this, &AASTRAPlayerController::CloseOrderLine);
							return FReply::Handled();
						}
						return FReply::Unhandled();
					})
					.OnTextCommitted_Lambda([this](const FText& Text, ETextCommit::Type How)
					{
						// only Enter sends and closes (a focus change keeps the line open: it takes the focus back)
						if (How != ETextCommit::OnEnter)
						{
							return;
						}
						const FString Line = Text.ToString().TrimStartAndEnd();
						if (!Line.IsEmpty())
						{
							if (UAstraMindSubsystem* Mind = GetGameInstance() ? GetGameInstance()->GetSubsystem<UAstraMindSubsystem>() : nullptr)
							{
								Mind->SayText(Line);
							}
						}
						// closed on the next tick: Slate is still inside the box's own event
						GetWorldTimerManager().SetTimerForNextTick(this, &AASTRAPlayerController::CloseOrderLine);
					})
				]
			]
		]
	];
	VC->AddViewportWidgetContent(OrderLine.ToSharedRef(), 50);
	FInputModeUIOnly Mode;
	Mode.SetWidgetToFocus(OrderBox);
	Mode.SetLockMouseToViewportBehavior(EMouseLockMode::LockAlways);
	SetInputMode(Mode);
	FSlateApplication::Get().SetKeyboardFocus(OrderBox, EFocusCause::SetDirectly);
	GetWorldTimerManager().SetTimer(OrderFocusTimer, [this]()
	{
		if (OrderBox.IsValid() && !OrderBox->HasKeyboardFocus())
		{
			FSlateApplication::Get().SetKeyboardFocus(OrderBox, EFocusCause::SetDirectly);
		}
	}, 0.1f, true);
}

void AASTRAPlayerController::CloseOrderLine()
{
	UGameViewportClient* VC = GetWorld() ? GetWorld()->GetGameViewport() : nullptr;
	if (!OrderLine.IsValid())
	{
		return;             // already closed (removing the box commits it a second time, as focus lost)
	}
	if (VC)
	{
		VC->RemoveViewportWidgetContent(OrderLine.ToSharedRef());
	}
	GetWorldTimerManager().ClearTimer(OrderFocusTimer);
	OrderLine.Reset();
	OrderBox.Reset();
	SetInputMode(FInputModeGameOnly());
	UE_LOG(LogASTRA, Log, TEXT("[Order line] closed"));
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
