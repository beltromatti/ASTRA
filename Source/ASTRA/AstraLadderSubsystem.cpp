// ASTRA — the Jefferies trunks' ladders (see AstraLadderSubsystem.h).

#include "AstraLadderSubsystem.h"

#include "ASTRA.h"
#include "ASTRACharacter.h"
#include "ASTRAPlayerController.h"
#include "AstraLiftSubsystem.h"
#include "Components/CapsuleComponent.h"
#include "Engine/World.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "HAL/IConsoleManager.h"
#include "Kismet/GameplayStatics.h"

namespace
{
	constexpr float LadderUpCmS = 130.f;        // a brisk climb, hand over hand
	constexpr float LadderDownCmS = 160.f;
	constexpr float LadderAccel = 700.f;        // cm/s²: he starts and stops in a fraction of a second
	constexpr float LadderSnapS = 0.22f;        // from where he took it to the spot in front of the rungs
	constexpr float LadderDeckTol = 40.f;       // feet this near a deck's floor: he can step off there
}

TStatId UAstraLadderSubsystem::GetStatId() const
{
	RETURN_QUICK_DECLARE_CYCLE_STAT(UAstraLadderSubsystem, STATGROUP_Tickables);
}

float UAstraLadderSubsystem::FeetZ(const ACharacter* C)
{
	return C ? (float)C->GetActorLocation().Z - C->GetCapsuleComponent()->GetScaledCapsuleHalfHeight() : 0.f;
}

void UAstraLadderSubsystem::Notice(const FString& Text, float Seconds) const
{
	if (AASTRAPlayerController* PC = Cast<AASTRAPlayerController>(UGameplayStatics::GetPlayerController(GetWorld(), 0)))
	{
		PC->ShowNotice(Text, Seconds);
	}
}

int32 UAstraLadderSubsystem::NearLadder(const FVector& Feet, float Reach, int32& OutStop) const
{
	int32 Best = INDEX_NONE;
	float BestD = Reach;
	for (int32 I = 0; I < Ladders.Num(); ++I)
	{
		const FAstraLadder& L = Ladders[I];
		const float D = (float)FVector2D::Distance(FVector2D(Feet), L.Spot);
		if (D >= BestD)
		{
			continue;
		}
		for (int32 S = 0; S < L.Stops.Num(); ++S)
		{
			if (FMath::Abs(Feet.Z - L.Stops[S].FloorZ) < LadderDeckTol + 20.f)
			{
				Best = I;
				BestD = D;
				OutStop = S;
				break;
			}
		}
	}
	return Best;
}

int32 UAstraLadderSubsystem::StopAt(float Feet, float Tol) const
{
	if (!Ladders.IsValidIndex(On))
	{
		return INDEX_NONE;
	}
	const TArray<FAstraLadderStop>& Stops = Ladders[On].Stops;
	int32 Best = INDEX_NONE;
	float BestD = Tol;
	for (int32 S = 0; S < Stops.Num(); ++S)
	{
		const float D = FMath::Abs(Stops[S].FloorZ - Feet);
		if (D <= BestD)
		{
			Best = S;
			BestD = D;
		}
	}
	return Best;
}

bool UAstraLadderSubsystem::IsClimbing(const APawn* Pawn) const
{
	return On != INDEX_NONE && Climber.IsValid() && Climber.Get() == Pawn;
}

bool UAstraLadderSubsystem::ClimbInput(const APawn* Pawn, const FVector2D& Axis)
{
	if (!IsClimbing(Pawn))
	{
		return false;
	}
	InputY = FMath::Clamp((float)Axis.Y, -1.f, 1.f);
	InputAt = GetWorld()->GetTimeSeconds();
	return true;
}

void UAstraLadderSubsystem::Grab(ACharacter* C, int32 Ladder)
{
	if (!C || !Ladders.IsValidIndex(Ladder))
	{
		return;
	}
	if (AASTRACharacter* AC = Cast<AASTRACharacter>(C))
	{
		AC->ResetPosture();                         // (on his feet: a ladder is not climbed crouched)
	}
	On = Ladder;
	Climber = C;
	Vz = 0.f;
	InputY = 0.f;
	InputAt = -1.0;
	EndHeldSince = -1.0;
	PushSince = -1.0;
	SnapFrom = FVector2D(C->GetActorLocation());
	SnapT = 0.f;
	TurnFrom = C->GetControlRotation().Yaw;
	C->GetCharacterMovement()->StopMovementImmediately();
	C->GetCharacterMovement()->DisableMovement();   // MOVE_None: this subsystem places him while he climbs
	const int32 S = StopAt(FeetZ(C), 200.f);
	DeckShown = Ladders[On].Stops.IsValidIndex(S) ? Ladders[On].Stops[S].Deck : 0;
	Notice(FString::Printf(TEXT("%s  ·  W / S  climb, down  ·  E  step off at a deck"), *Ladders[On].Name.ToUpper()), 6.f);
	UE_LOG(LogASTRA, Log, TEXT("[Ladder] the Captain takes %s at deck %d"), *Ladders[On].Id, DeckShown);
}

bool UAstraLadderSubsystem::StepOff(int32 StopIdx, FString& OutNotice)
{
	ACharacter* C = Climber.Get();
	if (!C || !Ladders.IsValidIndex(On) || !Ladders[On].Stops.IsValidIndex(StopIdx))
	{
		return false;
	}
	const FAstraLadder& L = Ladders[On];
	const FAstraLadderStop& S = L.Stops[StopIdx];
	// the walkway must be there (a deck's level streams in around the Captain as he climbs): a ray down from above the step
	const float Half = C->GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
	FHitResult Hit;
	FCollisionQueryParams Q(SCENE_QUERY_STAT(AstraLadderStep), false, C);
	const FVector Top(S.Step.X, S.Step.Y, S.FloorZ + 120.f);
	const bool bFloor = GetWorld()->LineTraceSingleByChannel(Hit, Top, FVector(S.Step.X, S.Step.Y, S.FloorZ - 80.f), ECC_Visibility, Q)
	                    && FMath::Abs(Hit.ImpactPoint.Z - S.FloorZ) < 60.f;
	if (!bFloor)
	{
		OutNotice = FString::Printf(TEXT("Deck %d is not there yet: hold on a moment"), S.Deck);
		return true;
	}
	C->SetActorLocation(FVector(S.Step.X, S.Step.Y, (bFloor ? Hit.ImpactPoint.Z : S.FloorZ) + Half + 2.f), false, nullptr, ETeleportType::TeleportPhysics);
	C->GetCharacterMovement()->SetMovementMode(MOVE_Walking);
	if (AController* Ctl = C->GetController())
	{
		Ctl->SetControlRotation(FRotator(Ctl->GetControlRotation().Pitch, L.FacingYaw + 180.f, 0.f));     // (his back to the ladder)
	}
	UE_LOG(LogASTRA, Log, TEXT("[Ladder] the Captain steps off %s at deck %d"), *L.Id, S.Deck);
	OutNotice = FString::Printf(TEXT("DECK %d"), S.Deck);
	On = INDEX_NONE;
	Climber.Reset();
	return true;
}

bool UAstraLadderSubsystem::Use(APawn* Pawn, FString& OutNotice)
{
	ACharacter* C = Cast<ACharacter>(Pawn);
	if (!C || !bLoaded)
	{
		return false;
	}
	if (IsClimbing(C))
	{
		const int32 S = StopAt(FeetZ(C), LadderDeckTol);
		if (S == INDEX_NONE)
		{
			OutNotice = TEXT("Climb to a deck to step off");
			return true;
		}
		return StepOff(S, OutNotice);
	}
	if (On != INDEX_NONE || C->GetCharacterMovement()->MovementMode == MOVE_None)
	{
		return false;
	}
	int32 Stop = INDEX_NONE;
	const int32 L = NearLadder(C->GetActorLocation() - FVector(0.f, 0.f, C->GetCapsuleComponent()->GetScaledCapsuleHalfHeight()), 170.f, Stop);
	if (L == INDEX_NONE)
	{
		return false;
	}
	Grab(C, L);
	return true;
}

void UAstraLadderSubsystem::Tick(float DeltaTime)
{
	UWorld* W = GetWorld();
	if (!W || !W->IsGameWorld())
	{
		return;
	}
	if (!bLoaded)
	{
		// the ladders come with the lifts' reading of the plan (a worker thread at the start of play)
		const UAstraLiftSubsystem* Lifts = W->GetSubsystem<UAstraLiftSubsystem>();
		if (Lifts && (Lifts->NumLines() > 0 || Lifts->Network().Ladders.Num() > 0))
		{
			Ladders = Lifts->Network().Ladders;
			bLoaded = true;
			UE_LOG(LogASTRA, Log, TEXT("[Ladder] %d Jefferies ladders from the plan"), Ladders.Num());
		}
		return;
	}
	if (Ladders.Num() == 0)
	{
		return;
	}
	ACharacter* C = Cast<ACharacter>(UGameplayStatics::GetPlayerPawn(W, 0));
	const double Now = W->GetTimeSeconds();
	if (On == INDEX_NONE || !Climber.IsValid())
	{
		On = INDEX_NONE;
		if (!C)
		{
			return;
		}
		UCharacterMovementComponent* M = C->GetCharacterMovement();
		const FVector Feet = C->GetActorLocation() - FVector(0.f, 0.f, C->GetCapsuleComponent()->GetScaledCapsuleHalfHeight());
		// a fall into a niche's hole is caught by the ladder (the rungs are within reach of a hand)
		if (M->MovementMode == MOVE_Falling)
		{
			for (int32 I = 0; I < Ladders.Num(); ++I)
			{
				const FAstraLadder& L = Ladders[I];
				if (FVector2D::Distance(FVector2D(Feet), L.Spot) < 80.f && Feet.Z > L.Stops[0].FloorZ - 50.f && Feet.Z < L.Stops.Last().FloorZ + 250.f)
				{
					Grab(C, I);
					return;
				}
			}
			return;
		}
		if (M->MovementMode != MOVE_Walking)
		{
			return;
		}
		// walking into a niche (pushing toward the rungs at its edge) takes the ladder, as a hand reaches for it
		int32 Stop = INDEX_NONE;
		const int32 L = NearLadder(Feet, 120.f, Stop);
		const FVector Push = C->GetLastMovementInputVector();
		const FVector ToRungs = FRotator(0.f, L != INDEX_NONE ? Ladders[L].FacingYaw : 0.f, 0.f).Vector();
		if (L != INDEX_NONE && Push.SizeSquared2D() > 0.25f && FVector::DotProduct(Push.GetSafeNormal2D(), ToRungs) > 0.6f)
		{
			if (PushLadder != L || PushSince < 0.0)
			{
				PushLadder = L;
				PushSince = Now;
			}
			else if (Now - PushSince > 0.25)
			{
				Grab(C, L);
			}
		}
		else
		{
			PushSince = -1.0;
		}
		return;
	}
	// ---- climbing
	ACharacter* Cl = Climber.Get();
	const FAstraLadder& L = Ladders[On];
	const float Half = Cl->GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
	const float In = Now - InputAt < 0.15 ? InputY : 0.f;
	const float Want = In >= 0.f ? In * LadderUpCmS : In * LadderDownCmS;
	Vz = FMath::FInterpConstantTo(Vz, Want, DeltaTime, LadderAccel);
	const float Lo = L.Stops[0].FloorZ, Hi = L.Stops.Last().FloorZ;
	float Feet = FeetZ(Cl) + Vz * DeltaTime;
	if (Feet <= Lo || Feet >= Hi)
	{
		Feet = FMath::Clamp(Feet, Lo, Hi);
		Vz = 0.f;
	}
	SnapT = FMath::Min(1.f, SnapT + DeltaTime / LadderSnapS);
	const float A = FMath::SmoothStep(0.f, 1.f, SnapT);
	const FVector2D XY = FMath::Lerp(SnapFrom, L.Spot, A);
	Cl->SetActorLocation(FVector(XY.X, XY.Y, Feet + Half), false, nullptr, ETeleportType::TeleportPhysics);
	if (SnapT < 1.f || A < 1.f)
	{
		if (AController* Ctl = Cl->GetController())
		{
			const float Yaw = FMath::Lerp(TurnFrom, TurnFrom + FMath::FindDeltaAngleDegrees(TurnFrom, L.FacingYaw), A);
			Ctl->SetControlRotation(FRotator(Ctl->GetControlRotation().Pitch, Yaw, 0.f));
		}
	}
	// the deck he is level with: its name once, and the way off
	const int32 At = StopAt(Feet, LadderDeckTol);
	if (At != INDEX_NONE && L.Stops[At].Deck != DeckShown)
	{
		DeckShown = L.Stops[At].Deck;
		Notice(FString::Printf(TEXT("DECK %d  ·  E  step off"), DeckShown), 2.5f);
	}
	// up at the top, down at the bottom: pushing on steps off there
	const bool bAtTop = Feet >= Hi - 2.f && In > 0.5f;
	const bool bAtBottom = Feet <= Lo + 2.f && In < -0.5f;
	if (bAtTop || bAtBottom)
	{
		if (EndHeldSince < 0.0)
		{
			EndHeldSince = Now;
		}
		else if (Now - EndHeldSince > 0.3)
		{
			FString Text;
			StepOff(bAtTop ? L.Stops.Num() - 1 : 0, Text);
			if (!Text.IsEmpty())
			{
				Notice(Text, 2.5f);
			}
			EndHeldSince = -1.0;
		}
	}
	else
	{
		EndHeldSince = -1.0;
	}
}

FString UAstraLadderSubsystem::Describe() const
{
	FString S = FString::Printf(TEXT("%d ladders%s"), Ladders.Num(), bLoaded ? TEXT("") : TEXT(" (not read yet)"));
	if (Ladders.IsValidIndex(On) && Climber.IsValid())
	{
		S += FString::Printf(TEXT("; the Captain is on %s, feet at %.2f m, %.1f m/s"), *Ladders[On].Id, FeetZ(Climber.Get()) / 100.f, Vz / 100.f);
	}
	return S;
}

namespace
{
	FAutoConsoleCommandWithWorld CmdLadders(TEXT("astra.ladders.info"), TEXT("The Jefferies ladders: how many, and the one the Captain is on"),
		FConsoleCommandWithWorldDelegate::CreateLambda([](UWorld* W)
		{
			if (const UAstraLadderSubsystem* L = W ? W->GetSubsystem<UAstraLadderSubsystem>() : nullptr)
			{
				UE_LOG(LogASTRA, Log, TEXT("[Ladder] %s"), *L->Describe());
			}
		}));
}
