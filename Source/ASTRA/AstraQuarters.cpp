// ASTRA — the Captain's quarters.

#include "AstraQuarters.h"

#include "ASTRA.h"
#include "AstraShipSubsystem.h"
#include "Camera/PlayerCameraManager.h"
#include "Components/CapsuleComponent.h"
#include "Components/LightComponent.h"
#include "Engine/Font.h"
#include "Engine/GameViewportClient.h"
#include "Engine/Light.h"
#include "EngineUtils.h"
#include "GameFramework/Character.h"
#include "GameFramework/PlayerController.h"
#include "Kismet/GameplayStatics.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Text/STextBlock.h"

namespace
{
	const FName QuartersZoneTag(TEXT("ASTRA.Zone.Quarters"));
}

AAstraQuarters::AAstraQuarters()
{
	PrimaryActorTick.bCanEverTick = true;
	SetRootComponent(CreateDefaultSubobject<USceneComponent>(TEXT("Root")));
}

void AAstraQuarters::BeginPlay()
{
	Super::BeginPlay();
	for (TActorIterator<ALight> It(GetWorld()); It; ++It)
	{
		if (It->ActorHasTag(QuartersZoneTag))
		{
			Lights.Add(*It);
		}
	}
	// something the Captain must hear: the XO wakes them
	if (UAstraShipSubsystem* Ship = GetWorld()->GetSubsystem<UAstraShipSubsystem>())
	{
		EventHandle = Ship->OnShipEvent.AddWeakLambda(this, [this](const FString& Text, bool bReport)
		{
			if (bReport && (Phase == EPhase::Asleep || Phase == EPhase::FallingAsleep))
			{
				Wake(Text);
			}
		});
	}
}

void AAstraQuarters::EndPlay(const EEndPlayReason::Type Reason)
{
	if (UWorld* W = GetWorld())
	{
		if (UAstraShipSubsystem* Ship = W->GetSubsystem<UAstraShipSubsystem>())
		{
			Ship->OnShipEvent.Remove(EventHandle);
		}
		if (IsResting())
		{
			UGameplayStatics::SetGlobalTimeDilation(this, 1.f);
		}
	}
	ShowCaption(false);
	Super::EndPlay(Reason);
}

bool AAstraQuarters::IsPawnInside(const APawn* Pawn) const
{
	if (!Pawn)
	{
		return false;
	}
	const FVector L = GetActorTransform().InverseTransformPosition(Pawn->GetActorLocation());
	return L.X > CabinMin.X && L.X < CabinMax.X && L.Y > CabinMin.Y && L.Y < CabinMax.Y && L.Z > CabinMin.Z && L.Z < CabinMax.Z;
}

void AAstraQuarters::SetPhase(EPhase P)
{
	Phase = P;
	PhaseT0 = FPlatformTime::Seconds();
}

void AAstraQuarters::SetControl(bool bEnabled)
{
	if (APlayerController* PC = UGameplayStatics::GetPlayerController(this, 0))
	{
		if (bEnabled)
		{
			PC->ResetIgnoreMoveInput();
			PC->ResetIgnoreLookInput();
		}
		else
		{
			PC->SetIgnoreMoveInput(true);
			PC->SetIgnoreLookInput(true);
		}
	}
}

bool AAstraQuarters::TryRest(APawn* Pawn)
{
	if (IsResting())
	{
		if (Phase == EPhase::Asleep)
		{
			Wake(FString());   // E: the Captain gets up
		}
		return true;
	}
	const FVector Bunk = GetActorTransform().TransformPosition(BunkSpot);
	if (!Pawn || !IsPawnInside(Pawn) || FVector::Dist2D(Pawn->GetActorLocation(), Bunk) > 170.f)
	{
		return false;
	}
	Sleeper = Pawn;
	SetControl(false);
	if (APlayerCameraManager* Cam = UGameplayStatics::GetPlayerCameraManager(this, 0))
	{
		Cam->StartCameraFade(0.f, 1.f, 1.2f, FLinearColor::Black, false, true);
	}
	SetPhase(EPhase::FallingAsleep);
	if (UAstraShipSubsystem* Ship = GetWorld()->GetSubsystem<UAstraShipSubsystem>())
	{
		Ship->PublishEvent(TEXT("the Captain lay down to rest in their quarters; the XO has the conn and will wake the Captain for anything important"), false);
	}
	UE_LOG(LogASTRA, Log, TEXT("[Quarters] the Captain rests"));
	return true;
}

void AAstraQuarters::Wake(const FString& Why)
{
	if (!IsResting() || Phase == EPhase::Waking)
	{
		return;
	}
	const double Minutes = Phase == EPhase::Asleep ? (GetWorld()->GetTimeSeconds() - AsleepWorldT) / 60.0 : 0.0;
	UGameplayStatics::SetGlobalTimeDilation(this, 1.f);
	ShowCaption(false);
	if (APawn* P = Sleeper.Get())
	{
		// up and standing beside the bunk
		float Half = 96.f;
		if (const ACharacter* C = Cast<ACharacter>(P))
		{
			Half = C->GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
		}
		P->SetActorLocation(GetActorTransform().TransformPosition(BunkSpot) + FVector(0.f, 0.f, Half), false, nullptr, ETeleportType::TeleportPhysics);
	}
	if (APlayerCameraManager* Cam = UGameplayStatics::GetPlayerCameraManager(this, 0))
	{
		Cam->StartCameraFade(1.f, 0.f, 1.5f, FLinearColor::Black, false, false);
	}
	SetPhase(EPhase::Waking);
	if (UAstraShipSubsystem* Ship = GetWorld()->GetSubsystem<UAstraShipSubsystem>())
	{
		// woken for something: that report reaches the Captain anyway (it is why); otherwise the XO gives the news
		if (Why.IsEmpty())
		{
			Ship->PublishEvent(FString::Printf(TEXT("the Captain is up again after about %d minutes of rest in their quarters"),
				FMath::Max(1, FMath::RoundToInt(Minutes))), true);
		}
		else
		{
			Ship->PublishEvent(FString::Printf(TEXT("the XO woke the Captain in their quarters after about %d minutes of rest"),
				FMath::Max(1, FMath::RoundToInt(Minutes))), false);
		}
	}
	UE_LOG(LogASTRA, Log, TEXT("[Quarters] the Captain wakes after %.1f ship minutes%s%s"), Minutes, Why.IsEmpty() ? TEXT("") : TEXT(": "), *Why);
}

void AAstraQuarters::Tick(float DeltaTime)
{
	Super::Tick(DeltaTime);
	const double Now = FPlatformTime::Seconds();
	switch (Phase)
	{
	case EPhase::FallingAsleep:
		if (Now - PhaseT0 > 1.3)
		{
			// asleep: the ship's time runs on (the XO has the conn)
			UGameplayStatics::SetGlobalTimeDilation(this, RestDilation);
			AsleepWorldT = GetWorld()->GetTimeSeconds();
			ShowCaption(true);
			SetPhase(EPhase::Asleep);
		}
		break;
	case EPhase::Asleep:
		if (Now - PhaseT0 > MaxRestSeconds)
		{
			Wake(FString());
		}
		break;
	case EPhase::Waking:
		if (Now - PhaseT0 > 1.6)
		{
			SetControl(true);
			SetPhase(EPhase::Awake);
		}
		break;
	default:
		break;
	}
	// the cabin's lights, only while the Captain is there
	if ((CheckT -= DeltaTime) <= 0.f)
	{
		CheckT = 0.25f;
		const bool bIn = IsPawnInside(UGameplayStatics::GetPlayerPawn(this, 0));
		if (bIn != bLightsOn)
		{
			bLightsOn = bIn;
			if (GetWorld()->GetTimeSeconds() > 5.0)
			{
				if (UAstraShipSubsystem* Ship = GetWorld()->GetSubsystem<UAstraShipSubsystem>())
				{
					Ship->PublishEvent(bIn ? TEXT("the Captain went into the Captain's quarters (Deck 1, behind the bridge)")
					                       : TEXT("the Captain left the Captain's quarters"), false);
				}
			}
			for (ALight* L : Lights)
			{
				if (L && L->GetLightComponent())
				{
					L->GetLightComponent()->SetVisibility(bIn);
				}
			}
		}
	}
}

void AAstraQuarters::ShowCaption(bool bShow)
{
	UGameViewportClient* VC = GetWorld() ? GetWorld()->GetGameViewport() : nullptr;
	if (Caption.IsValid() && VC)
	{
		VC->RemoveViewportWidgetContent(Caption.ToSharedRef());
	}
	Caption.Reset();
	if (!bShow || !VC)
	{
		return;
	}
	UFont* Mono = LoadObject<UFont>(nullptr, TEXT("/Game/ASTRA/UI/Fonts/F_ASTRA_Mono.F_ASTRA_Mono"));
	const FSlateFontInfo Font = Mono ? FSlateFontInfo(Mono, 16) : FCoreStyle::GetDefaultFontStyle("Mono", 16);
	Caption = SNew(SBox).HAlign(HAlign_Center).VAlign(VAlign_Bottom).Padding(FMargin(0, 0, 0, 80))
	[
		SNew(STextBlock).Font(Font).ColorAndOpacity(FLinearColor(0.55f, 0.62f, 0.7f, 0.85f))
		.Text(FText::FromString(TEXT("RESTING  ·  the XO has the conn  ·  E to get up")))
	];
	VC->AddViewportWidgetContent(Caption.ToSharedRef(), 40);
}
