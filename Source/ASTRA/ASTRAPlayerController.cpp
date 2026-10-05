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
#include "Engine/Engine.h"
#include "Misc/CommandLine.h"
#include "Engine/Font.h"
#include "AstraArmory.h"
#include "AstraCampaign.h"
#include "AstraCommandWheel.h"
#include "AstraFighterPawn.h"
#include "AstraHangar.h"
#include "AstraLadderSubsystem.h"
#include "AstraLiftSubsystem.h"
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
#include "AstraSettings.h"
#include "AstraInput.h"
#include "AstraHarness.h"
#include "ASTRACharacter.h"
#include "AstraScreensSubsystem.h"
#include "AstraWindowHud.h"
#include "Sound/SoundBase.h"
#include "Kismet/GameplayStatics.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/TextureRenderTarget2D.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Camera/CameraComponent.h"
#include "Engine/GameInstance.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "TimerManager.h"

DECLARE_CYCLE_STAT(TEXT("Player controller"), STAT_AstraPC, STATGROUP_Astra);

AASTRAPlayerController::AASTRAPlayerController()
{
	// set the player camera manager class
	PlayerCameraManagerClass = AASTRACameraManager::StaticClass();
}

UAstraInputSet* AASTRAPlayerController::GetInputSet()
{
	if (!InputSet)
	{
		InputSet = NewObject<UAstraInputSet>(this, TEXT("AstraInput"));
		InputSet->Build();
	}
	return InputSet;
}

void AASTRAPlayerController::BeginPlay()
{
	Super::BeginPlay();
	// the engine's own debug lines on the screen ("Preparing Animation Sequences (1)" over a boarding, 5 Oct) are not the player's: off in a game the
	// player runs, kept for the test bench (-astra_harness) and the editor
	if (GEngine && !GIsEditor && !FParse::Param(FCommandLine::Get(), TEXT("astra_harness")))
	{
		GEngine->bEnableOnScreenDebugMessages = false;
	}
	if (IsLocalPlayerController())
	{
		GetWorldTimerManager().SetTimerForNextTick([this]()
		{
			if (!HintWidget.IsValid())
			{
				ShowNotice(TEXT("F1  controls  ·  W or E  stand up  ·  hold V  talk to the crew  ·  T  type  ·  hold G  orders  ·  Tab  datapad"), 45.f);
			}
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
		// the command wheel: G held; while it is open a number picks an order
		InputComponent->BindKey(EKeys::G, IE_Pressed, this, &AASTRAPlayerController::OnOrdersPressed);
		InputComponent->BindKey(EKeys::G, IE_Released, this, &AASTRAPlayerController::OnOrdersReleased);
		const FKey Numbers[] = {EKeys::One, EKeys::Two, EKeys::Three, EKeys::Four, EKeys::Five, EKeys::Six, EKeys::Seven, EKeys::Eight};
		for (int32 n = 0; n < 8; ++n)
		{
			FInputKeyBinding B(FInputChord(Numbers[n]), IE_Pressed);
			B.bConsumeInput = false;                     // (the lift's list takes the numbers too, when it is open)
			B.KeyDelegate.GetDelegateForManualSet().BindLambda([this, n]()
			{
				if (Orders.IsValid() && Orders->IsOpen())
				{
					Orders->Pick(this, n);
				}
			});
			InputComponent->KeyBindings.Add(B);
		}
		// the datapad's pages: the mouse wheel while it is raised
		auto Wheel = [this](const FKey& K, int32 Dir)
		{
			FInputKeyBinding B(FInputChord(K), IE_Pressed);
			B.bConsumeInput = false;
			B.KeyDelegate.GetDelegateForManualSet().BindLambda([this, Dir]()
			{
				UAstraScreensSubsystem* Screens = GetWorld() ? GetWorld()->GetSubsystem<UAstraScreensSubsystem>() : nullptr;
				if (bPadUp && Screens)
				{
					Screens->CyclePad(Dir);
				}
			});
			InputComponent->KeyBindings.Add(B);
		};
		Wheel(EKeys::MouseScrollDown, 1);
		Wheel(EKeys::MouseScrollUp, -1);
		// the lift's list on the car's screen (only while it is open): W / S and the arrows move the mark, Enter, Space and the left mouse button choose, a number
		// goes to that deck, the wheel scrolls it (the keys also mean other things, which is why they act only when the list is open)
		auto LiftKey = [this](const FKey& K, TFunction<void(UAstraLiftSubsystem*)> Do)
		{
			FInputKeyBinding B(FInputChord(K), IE_Pressed);
			B.bConsumeInput = false;
			B.KeyDelegate.GetDelegateForManualSet().BindLambda([this, Do]()
			{
				UAstraLiftSubsystem* Lifts = GetWorld() ? GetWorld()->GetSubsystem<UAstraLiftSubsystem>() : nullptr;
				if (Lifts && Lifts->IsMenuOpen())
				{
					Do(Lifts);
				}
			});
			InputComponent->KeyBindings.Add(B);
		};
		auto Choose = [this](UAstraLiftSubsystem* Lifts)
		{
			FString Notice;
			Lifts->MenuChoose(Notice);
			if (!Notice.IsEmpty())
			{
				ShowNotice(Notice, 3.5f);
			}
		};
		LiftKey(EKeys::W, [](UAstraLiftSubsystem* L) { L->MenuMove(-1); });
		LiftKey(EKeys::Up, [](UAstraLiftSubsystem* L) { L->MenuMove(-1); });
		LiftKey(EKeys::MouseScrollUp, [](UAstraLiftSubsystem* L) { L->MenuMove(-1); });
		LiftKey(EKeys::S, [](UAstraLiftSubsystem* L) { L->MenuMove(1); });
		LiftKey(EKeys::Down, [](UAstraLiftSubsystem* L) { L->MenuMove(1); });
		LiftKey(EKeys::MouseScrollDown, [](UAstraLiftSubsystem* L) { L->MenuMove(1); });
		LiftKey(EKeys::Enter, Choose);
		LiftKey(EKeys::SpaceBar, Choose);
		LiftKey(EKeys::LeftMouseButton, Choose);
		auto Deck = [this, &LiftKey](const FKey& K, int32 N)
		{
			LiftKey(K, [this, N](UAstraLiftSubsystem* L)
			{
				FString Detail;
				if (L->GoToDeck(N, Detail))
				{
					ShowNotice(Detail, 3.5f);
				}
			});
		};
		Deck(EKeys::One, 1);
		Deck(EKeys::Two, 2);
		Deck(EKeys::Three, 3);
		Deck(EKeys::Four, 4);
		Deck(EKeys::Five, 5);
		Deck(EKeys::Six, 6);
		Deck(EKeys::Seven, 7);
		Deck(EKeys::Eight, 8);
		Deck(EKeys::Nine, 9);
	}

	// only add IMCs for local player controllers
	if (IsLocalPlayerController())
	{
		// Add Input Mapping Context
		if (UEnhancedInputLocalPlayerSubsystem* Subsystem = ULocalPlayer::GetSubsystem<UEnhancedInputLocalPlayerSubsystem>(GetLocalPlayer()))
		{
			// the Captain's own controls on foot, built in code (the template's input assets are not used)
			Subsystem->AddMappingContext(GetInputSet()->OnFoot, 0);
			for (UInputMappingContext* CurrentContext : DefaultMappingContexts)
			{
				if (CurrentContext)       // (the template's slots, left empty in the blueprint)
				{
					Subsystem->AddMappingContext(CurrentContext, 0);
				}
			}

			// only add these IMCs if we're not using mobile touch input
			if (!ShouldUseTouchControls())
			{
				for (UInputMappingContext* CurrentContext : MobileExcludedMappingContexts)
				{
					if (CurrentContext)
					{
						Subsystem->AddMappingContext(CurrentContext, 0);
					}
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
	EnsureSubtitles();   // (the "listening" mark lives with the subtitles)
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
	// ABBORDAGGI: the armory's rack: take the weapons, or put them back
	if (APawn* Me = GetPawn())
	{
		for (TActorIterator<AAstraArmoryRack> It(GetWorld()); It; ++It)
		{
			if (It->TryUse(Me))
			{
				return;
			}
		}
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
					return;
				}
				// sealed: a word on it, unless the lift is right here (pod 1-A is beside the bridge's lift doors: the lift is what the
				// Captain came for, and E always answered "sealed")
				const UAstraLiftSubsystem* LiftsHere = GetWorld()->GetSubsystem<UAstraLiftSubsystem>();
				const bool bLiftHere = LiftsHere && LiftsHere->IsNearPanel(Me->GetActorLocation() - FVector(0.f, 0.f, Me->IsA<ACharacter>() ? Cast<ACharacter>(Me)->GetDefaultHalfHeight() : 90.f));
				if (!bLiftHere)
				{
					Subtitle(-1 - It->PodName.Len(), TEXT("notice"), FString::Printf(TEXT("LIFEPOD %s"), *It->PodName),
					         TEXT("Sealed. It opens on ABANDON SHIP."));
					return;
				}
				break;
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
	// a Jefferies trunk's ladder (docs/NAVE.md §8): by a niche E takes it, on it E steps off at a deck
	if (APawn* Me = GetPawn())
	{
		if (UAstraLadderSubsystem* Ladders = GetWorld() ? GetWorld()->GetSubsystem<UAstraLadderSubsystem>() : nullptr)
		{
			FString Notice;
			if (Ladders->Use(Me, Notice))
			{
				if (!Notice.IsEmpty())
				{
					ShowNotice(Notice, 3.f);
				}
				return;
			}
		}
	}
	// the lift (docs/ASCENSORI.md): at a landing's panel E calls the car; inside, it opens the list of decks on the car's screen, and chooses the one that is marked
	if (APawn* Me = GetPawn())
	{
		if (UAstraLiftSubsystem* Lifts = GetWorld() ? GetWorld()->GetSubsystem<UAstraLiftSubsystem>() : nullptr)
		{
			FString Notice;
			if (Lifts->Use(Me, Notice))
			{
				if (!Notice.IsEmpty())
				{
					ShowNotice(Notice, 3.5f);
				}
				return;
			}
		}
		// a Falcon of Alpha on the flight deck
		for (TActorIterator<AAstraHangar> It(GetWorld()); It; ++It)
		{
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
		if (AASTRACharacter* AC = Cast<AASTRACharacter>(C))
		{
			AC->ResetPosture();
		}
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
		if (!bWalkHintShown)
		{
			// the first time on foot: the keys for walking (the card at the start spoke of the chair)
			bWalkHintShown = true;
			ShowNotice(TEXT("WASD  walk  ·  Shift  run  ·  C  crouch (hold: lie down)  ·  Z X  lean  ·  Space  jump  ·  E  doors, lifts, use  ·  F1  all the controls"), 25.f);
		}
	}
	bSeated = bSit;
}

void AASTRAPlayerController::AstraBoardFalcon()
{
	APawn* Me = GetPawn();
	if (!Cast<ACharacter>(Me))
	{
		return;
	}
	TActorIterator<AAstraHangar> It(GetWorld());
	if (It)
	{
		if (bSeated)
		{
			SetSeated(false);
		}
		BoardFalcon(*It, Me);
	}
}

void AASTRAPlayerController::AstraDeck(int32 N)
{
	if (UAstraLiftSubsystem* Lifts = GetWorld() ? GetWorld()->GetSubsystem<UAstraLiftSubsystem>() : nullptr)
	{
		FString Detail;
		Lifts->GoToDeck(N, Detail);
		ShowNotice(Detail, 3.5f);
	}
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

void AASTRAPlayerController::ShowNotice(const FString& Text, float Seconds)
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
	UFont* Mono = LoadObject<UFont>(nullptr, TEXT("/Game/ASTRA/UI/Fonts/F_ASTRA_Mono.F_ASTRA_Mono"));
	HintWidget = SNew(SBox).HAlign(HAlign_Right).VAlign(VAlign_Bottom).Padding(FMargin(0, 0, 28, 22))
	[
		SNew(SBorder).BorderImage(FCoreStyle::Get().GetBrush("WhiteBrush")).BorderBackgroundColor(FLinearColor(0.004f, 0.006f, 0.01f, 0.7f))
		.Padding(FMargin(14, 8))
		[
			SNew(STextBlock).Font(Mono ? FSlateFontInfo(Mono, 13) : FCoreStyle::GetDefaultFontStyle("Mono", 13))
			.ColorAndOpacity(FLinearColor(0.82f, 0.88f, 0.95f, 0.95f)).Text(FText::FromString(Text))
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
	}, Seconds, false);
}

void AASTRAPlayerController::TogglePad()
{
	if (!Cast<ACharacter>(GetPawn()))
	{
		return;                                        // on foot only: a Falcon has its own instruments
	}
	bPadUp = !bPadUp;
	const TCHAR* Name = bPadUp ? TEXT("/Game/ASTRA/Audio/SW_Pad_Up.SW_Pad_Up") : TEXT("/Game/ASTRA/Audio/SW_Pad_Down.SW_Pad_Down");
	if (USoundBase* S = LoadObject<USoundBase>(nullptr, Name))
	{
		UGameplayStatics::PlaySound2D(this, S, 0.5f);
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
		PadMesh = NewObject<UStaticMeshComponent>(Me, MakeUniqueObjectName(Me, UStaticMeshComponent::StaticClass(), TEXT("CaptainDatapad")));
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
	const FVector Down(20.f, -16.f, -44.f), Up(27.f, -7.5f, -9.f);
	const FQuat RDown = FRotator(-70.f, -14.f, 8.f).Quaternion(), RUp = FRotator(-18.f, -15.f, 3.f).Quaternion();
	PadMesh->SetRelativeLocationAndRotation(FMath::Lerp(Down, Up, A), FQuat::Slerp(RDown, RUp, A));
	PadMesh->SetVisibility(true);
}

namespace
{
	const TCHAR* HelpCard =
		TEXT("ON THE BRIDGE\n")
		TEXT("  V (hold)        talk to the crew, in any language\n")
		TEXT("  T               type to the crew instead (Enter sends, Esc cancels)\n")
		TEXT("  G (hold)        the orders wheel: point and let go, or a number — weapons free / hold fire, engage what you\n")
		TEXT("                  are looking at, a missile salvo, the fighters on it or home, disable it (guns on its engines:\n")
		TEXT("                  left adrift, a prize to board), shields, red alert, the main screen\n")
		TEXT("  Tab             the datapad: the ship at a glance, anywhere aboard\n")
		TEXT("  E               stand up / sit down · doors · the lift · use\n")
		TEXT("  W (seated)      stand up and walk\n")
		TEXT("\n")
		TEXT("ON FOOT\n")
		TEXT("  WASD, mouse     walk and look          Shift (hold)   run\n")
		TEXT("  Space           jump (low down: stand)  C              crouch · hold C: lie down\n")
		TEXT("  Z, X (hold)     lean out to the left / right: the eyes and the weapon come out from behind a corner, the body stays covered\n")
		TEXT("                  (gamepad: the shoulders)\n")
		TEXT("  Esc             pause · save · menu\n")
		TEXT("\n")
		TEXT("THE LIFTS (a panel beside each door; the car's own screen inside)\n")
		TEXT("  E at the panel   call the car          E inside   the list of decks and places on the screen\n")
		TEXT("  W / S, mouse     move the mark         E, click   go            1-9   that deck            Esc   close\n")
		TEXT("  or say it: \"Deck seven\", \"Main Engineering\"; the car really moves, and the crew rides it too\n")
		TEXT("  the Captain's quarters: the door at the end of the starboard corridor;\n")
		TEXT("  E beside the bunk to rest (the XO wakes you if anything happens)\n")
		TEXT("\n")
		TEXT("ARMED (the armory, Deck 8: E at the rack takes the rifle and the sidearm)\n")
		TEXT("  left mouse      fire (the rifle holds fire: the sidearm one round a click)\n")
		TEXT("  right mouse     look through the sights (slower turn, steadier aim)\n")
		TEXT("  R               reload              1 / 2    rifle / sidearm        Q   the last weapon\n")
		TEXT("  H               holster             wheel    change weapon          the weapon is lowered when you run\n")
		TEXT("  C, hold C       crouch / lie down: the cone of your rounds closes, you are a smaller target\n")
		TEXT("  amber arc       somebody has you in sight (the red arcs are rounds that hit you): get low (C) or get behind cover\n")
		TEXT("  gamepad         right trigger fire · left trigger sights · X reload · Y last weapon · D-pad down holster\n")
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
	if (S == TEXT("computer")) { return FLinearColor(0.45f, 0.85f, 1.f); }                 // the ship's computer (the lifts answer by it)
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
	// the crew is listening: from the talk key going down until the answer begins
	Box->AddSlot().AutoHeight().HAlign(HAlign_Center).Padding(0, 0, 0, 4)
	[
		SAssignNew(ListeningText, STextBlock).Font(NameFont).Text(FText::FromString(TEXT("\u25CF  LISTENING")))
		.ColorAndOpacity(FLinearColor(1.f, 0.84f, 0.47f, 0.f))
	];
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

void AASTRAPlayerController::Subtitle(int32 Id, const FString& Speaker, const FString& Name, const FString& Text, float HoldSeconds, bool bVoiced)
{
	FAstraTimeline::Record(TEXT("line"), FString::Printf(TEXT("%s: %s"), *Name, *Text));
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
	// the time to read it: 17 characters a second after a 1.4 s start, 12 s at most (protocollo_voce §3.1)
	L.Hold = HoldSeconds > 0.f ? HoldSeconds : FMath::Min(12.f, FMath::Max(bVoiced ? 2.f : 4.f, 1.4f + Text.Len() / 17.f));
	L.bVoiced = bVoiced;
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

void AASTRAPlayerController::SubtitleCancel(int32 Id)
{
	for (FSubLine& L : SubLines)
	{
		if (L.Id == Id && L.CutAge < 0.f)
		{
			L.CutAge = L.Age;
		}
	}
}

float AASTRAPlayerController::SubtitleGone(const FSubLine& L)
{
	// said: its reading time, or a second after its voice, whichever is later; still being said: it stays (at most half
	// a minute past its reading time: a voice that never ends); a notice: its reading time; stopped: it fades at once
	float Gone = L.EndAge >= 0.f ? FMath::Max(L.Hold, L.EndAge + 1.f)
	           : L.bVoiced     ? FMath::Max(L.Hold, FMath::Min(L.Age + 1.f, L.Hold + 30.f))
	                           : L.Hold;
	if (L.CutAge >= 0.f)
	{
		Gone = FMath::Min(Gone, L.CutAge + 0.35f);
	}
	return Gone;
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
		if (L.Age > SubtitleGone(L))
		{
			SubLines.RemoveAt(i);
		}
	}
	if (ListeningText.IsValid())
	{
		const UAstraMindSubsystem* Mind = GetGameInstance() ? GetGameInstance()->GetSubsystem<UAstraMindSubsystem>() : nullptr;
		const bool bHeard = Mind && Mind->IsCaptainHeard();
		ListeningA = FMath::FInterpConstantTo(ListeningA, bHeard ? 1.f : 0.f, DeltaTime, bHeard ? 8.f : 2.5f);
		const float Pulse = Mind && Mind->IsCaptainTalking() ? 0.75f + 0.25f * FMath::Sin(GetWorld()->GetRealTimeSeconds() * 6.f) : 0.6f;
		ListeningText->SetColorAndOpacity(FLinearColor(1.f, 0.84f, 0.47f, ListeningA * Pulse));
	}
	// subtitles off in the settings: the crew's spoken lines go unwritten (notices and the Captain's own words stay)
	if (!FAstraSettings::Get().bSubtitles)
	{
		SubLines.RemoveAll([](const FSubLine& L) { return L.bVoiced; });
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
		const float A = FMath::Clamp(FMath::Min(L.Age / 0.2f, (SubtitleGone(L) - L.Age) / 0.35f), 0.f, 1.f);
		SubRows[i]->SetBorderBackgroundColor(FLinearColor(0.f, 0.005f, 0.01f, 0.62f * A));
		SubNames[i]->SetText(FText::FromString(L.Name));
		SubNames[i]->SetColorAndOpacity(FLinearColor(L.Color.R, L.Color.G, L.Color.B, A));
		SubTexts[i]->SetText(FText::FromString(L.Text));
		SubTexts[i]->SetColorAndOpacity(FLinearColor(0.92f, 0.94f, 0.97f, A));
	}
}

void AASTRAPlayerController::PlayerTick(float DeltaTime)
{
	SCOPE_CYCLE_COUNTER(STAT_AstraPC);
	Super::PlayerTick(DeltaTime);
	TickSubtitles(DeltaTime);
	TickPad(DeltaTime);
	if (IsLocalPlayerController())
	{
		if (!WindowHud.IsValid())
		{
			WindowHud = MakeShared<FAstraWindowHud>();
		}
		WindowHud->Tick(this, DeltaTime);
		if (Orders.IsValid())
		{
			Orders->Tick(this, DeltaTime);
		}
		if (const UAstraLiftSubsystem* Lifts = GetWorld() ? GetWorld()->GetSubsystem<UAstraLiftSubsystem>() : nullptr)
		{
			const bool bList = Lifts->IsMenuOpen();
			if (bList != bLiftListHeld)
			{
				bLiftListHeld = bList;
				SetIgnoreMoveInput(bList);              // (a counter: the chair's own hold is not undone)
			}
		}
	}
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
	if (!VC || OrderLine.IsValid())
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

void AASTRAPlayerController::OnOrdersPressed()
{
	if (!Orders.IsValid())
	{
		Orders = MakeShared<FAstraCommandWheel>();
	}
	if (!bPadUp)
	{
		Orders->Open(this);
	}
}

void AASTRAPlayerController::OnOrdersReleased()
{
	if (Orders.IsValid())
	{
		Orders->Close(this, true);
	}
}

void AASTRAPlayerController::OpenMenu()
{
	if (Orders.IsValid() && Orders->IsOpen())
	{
		Orders->Close(this, false);                     // Esc: no order (the pause menu is for when the wheel is closed)
		return;
	}
	if (UAstraLiftSubsystem* Lifts = GetWorld() ? GetWorld()->GetSubsystem<UAstraLiftSubsystem>() : nullptr)
	{
		if (Lifts->IsMenuOpen())
		{
			Lifts->MenuClose();                         // Esc closes the car's list; the pause menu is for when there is none
			return;
		}
	}
	if (UAstraCampaignSubsystem* C = GetWorld() ? GetWorld()->GetSubsystem<UAstraCampaignSubsystem>() : nullptr)
	{
		if (C->IsStarted() && !C->IsMenuOpen())
		{
			C->ShowMenu(true);
		}
	}
}
