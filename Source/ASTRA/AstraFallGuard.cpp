// ASTRA — the Captain never falls out of his ship (AstraFallGuard.h).

#include "AstraFallGuard.h"
#include "ASTRA.h"
#include "AstraHarness.h"
#include "AstraShipPlan.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Kismet/GameplayStatics.h"

namespace
{
	// the longest drop inside the ship: from the Flight Deck's top gallery to its floor (21 m) takes ~2.1 s at the level's gravity
	constexpr double FallGuardSeconds = 2.4;
	constexpr double StoodEvery = 0.2;       // s between the places remembered
	constexpr int32 StoodKept = 30;          // ~6 s of them
	constexpr float BackFromEdge = 150.f;    // cm: where he is put back, at least this far from the edge he went over
	constexpr float FarMoveCm = 50000.f;     // cm between two steps: no walk, a transfer (a beam, a boat, a teleport)
}

TStatId UAstraFallGuard::GetStatId() const
{
	RETURN_QUICK_DECLARE_CYCLE_STAT(UAstraFallGuard, STATGROUP_Tickables);
}

void UAstraFallGuard::Tick(float DeltaTime)
{
	UWorld* W = GetWorld();
	ACharacter* C = W ? Cast<ACharacter>(UGameplayStatics::GetPlayerPawn(W, 0)) : nullptr;
	UCharacterMovementComponent* M = C ? C->GetCharacterMovement() : nullptr;
	if (!M)
	{
		FallSince = -1.0;
		return;
	}
	const double Now = W->GetTimeSeconds();
	if (M->MovementMode == MOVE_Walking || M->MovementMode == MOVE_NavWalking)
	{
		FallSince = -1.0;
		if (Stood.Num() && FVector::DistSquared(Stood.Last().Loc, C->GetActorLocation()) > FMath::Square(FarMoveCm))
		{
			Stood.Reset();                       // put somewhere else (the enemy decks, the boat's bay, the planet): the old places are of another world
		}
		if (M->CurrentFloor.bBlockingHit && (Stood.Num() == 0 || Now - Stood.Last().At >= StoodEvery))
		{
			Stood.Add({C->GetActorLocation(), Now});
			if (Stood.Num() > StoodKept)
			{
				Stood.RemoveAt(0);
			}
		}
		return;
	}
	if (M->MovementMode != MOVE_Falling)
	{
		FallSince = -1.0;                    // seated, on a ladder, in a cockpit: someone else places him
		return;
	}
	if (FallSince < 0.0)
	{
		FallSince = Now;
		FallFrom = C->GetActorLocation();
		Edge = Stood.Num() ? Stood.Last().Loc : FallFrom;
		return;
	}
	if (Now - FallSince < FallGuardSeconds || Stood.Num() == 0)
	{
		return;
	}
	// back where he stood: the newest place a step away from the edge (he was walking towards the gap)
	FVector Back = Stood[0].Loc;
	for (int32 I = Stood.Num() - 1; I >= 0; --I)
	{
		if (FVector::Dist2D(Stood[I].Loc, Edge) >= BackFromEdge)
		{
			Back = Stood[I].Loc;
			break;
		}
	}
	const FVector Fell = C->GetActorLocation();
	C->SetActorLocation(Back, false, nullptr, ETeleportType::TeleportPhysics);
	M->Velocity = FVector::ZeroVector;
	M->SetMovementMode(MOVE_Walking);
	FallSince = -1.0;
	++Caught;
	// the gap: where he walked off the floor, or, when the fall began far from where he last stood (moved there), where it began
	const bool bMoved = FVector::Dist(FallFrom, Edge) > 300.f;
	const FVector Gap = bMoved ? FallFrom : Edge;
	FString Where = TEXT("outside the plan");
	if (const UAstraShipPlan* Plan = W->GetSubsystem<UAstraShipPlan>())
	{
		if (const FAstraPlanCompartment* Comp = Plan->CompartmentAt(Gap - FVector(0.f, 0.f, C->GetSimpleCollisionHalfHeight() - 20.f)))
		{
			Where = FString::Printf(TEXT("Deck %d, %s (%s)"), Comp->Deck, *Comp->Name, *Comp->Id);
		}
	}
	const FString Line = FString::Printf(TEXT("the Captain fell through a missing floor %s (%.1f, %.1f, %.1f) m, %s; %.0f m down after %.1f s: put back at (%.1f, %.1f, %.1f) m"),
	                                     bMoved ? TEXT("where he was put, at") : TEXT("near"), Gap.X / 100.0, Gap.Y / 100.0, Gap.Z / 100.0, *Where,
	                                     (Gap.Z - Fell.Z) / 100.0, FallGuardSeconds, Back.X / 100.0, Back.Y / 100.0, Back.Z / 100.0);
	UE_LOG(LogASTRA, Warning, TEXT("[FallGuard] %s"), *Line);
	FAstraTimeline::Record(TEXT("event"), Line);
}
