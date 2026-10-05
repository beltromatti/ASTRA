// ASTRA — the lifts of the ship's first rooms (AstraRoomLift.h).

#include "AstraRoomLift.h"

#include "ASTRA.h"
#include "ASTRAPlayerController.h"
#include "AstraDeckStreaming.h"
#include "AstraShipPlan.h"
#include "Camera/PlayerCameraManager.h"
#include "Components/CapsuleComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Components/TextRenderComponent.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Kismet/GameplayStatics.h"
#include "Sound/SoundBase.h"

namespace
{
	USoundBase* RoomLiftSound(const TCHAR* Name)
	{
		return LoadObject<USoundBase>(nullptr, *FString::Printf(TEXT("/Game/ASTRA/Audio/%s.%s"), Name, Name), nullptr, LOAD_NoWarn | LOAD_Quiet);
	}

	/** The floor under a point (within a deck's height): its height, else the point's own. */
	FVector OnFloor(UWorld* W, const FVector& P, const AActor* Ignore = nullptr)
	{
		FHitResult H;
		FCollisionQueryParams Q(SCENE_QUERY_STAT(AstraRoomLiftFloor), false, Ignore);
		if (W && W->LineTraceSingleByChannel(H, P + FVector(0, 0, 150), P - FVector(0, 0, 400), ECC_Pawn, Q) && H.ImpactNormal.Z > 0.7f)
		{
			return FVector(P.X, P.Y, H.ImpactPoint.Z);
		}
		return P;
	}

	FVector Flat(const FVector& V)
	{
		return FVector(V.X, V.Y, 0.0).GetSafeNormal();
	}
}

AAstraRoomLift::AAstraRoomLift()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.TickInterval = 0.1f;
	SetRootComponent(CreateDefaultSubobject<USceneComponent>(TEXT("Root")));
}

bool AAstraRoomLift::Near(const APawn* Me, const FVector& Door) const
{
	if (!Me)
	{
		return false;
	}
	const FVector P = Me->GetActorLocation();
	return FVector::Dist2D(P, Door) < 230.0 && FMath::Abs(P.Z - Door.Z) < 300.0;
}

bool AAstraRoomLift::TryUse(APawn* Me)
{
	if (Stage != EStage::Idle || !Me)
	{
		return false;
	}
	if (Near(Me, RoomDoor))
	{
		bToRoom = false;
	}
	else if (Near(Me, DeckDoor))
	{
		bToRoom = true;
	}
	else
	{
		return false;
	}
	Rider = Me;
	Stage = EStage::Closing;
	T = 0.f;
	SetActorTickInterval(0.f);
	if (AController* C = Me->GetController())
	{
		C->SetIgnoreMoveInput(true);
	}
	if (APlayerController* PC = Cast<APlayerController>(Me->GetController()); PC && PC->PlayerCameraManager)
	{
		PC->PlayerCameraManager->StartCameraFade(0.f, 1.f, 0.45f, FLinearColor::Black, true, true);
	}
	if (SndThump)
	{
		UGameplayStatics::PlaySound2D(this, SndThump, 0.7f);
	}
	if (UAstraDeckStreaming* D = GetWorld()->GetSubsystem<UAstraDeckStreaming>())
	{
		D->RequestAt(bToRoom ? RoomFeet : DeckFeet, 30.f);       // (the other end's deck loads while the doors close)
	}
	UE_LOG(LogASTRA, Log, TEXT("[RoomLift] %s: the Captain rides to %s"), *RoomName, bToRoom ? *RoomName : *FString::Printf(TEXT("deck %d"), Deck));
	return true;
}

void AAstraRoomLift::SettleDeckEnd()
{
	UWorld* W = GetWorld();
	if (bDeckSettled || !W)
	{
		return;
	}
	bDeckSettled = true;
	// from the corridor towards the lobby: the first wall is the corridor's real end
	FHitResult H;
	FCollisionQueryParams Q(SCENE_QUERY_STAT(AstraRoomLiftEnd), false, this);
	if (APawn* Me = UGameplayStatics::GetPlayerPawn(this, 0))
	{
		Q.AddIgnoredActor(Me);
	}
	const FVector From = FVector(Corridor.X, Corridor.Y, DeckDoor.Z + 120.0);
	if (W->LineTraceSingleByChannel(H, From, From - Out * 1200.0, ECC_Visibility, Q))
	{
		DeckDoor = FVector(H.ImpactPoint.X, H.ImpactPoint.Y, DeckDoor.Z) + Out * 4.0;
	}
	DeckFeet = DeckDoor + Out * 130.0;
	FActorSpawnParameters SP;
	SP.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	const FTransform DeckFrame(Out.Rotation(), DeckDoor);
	int32 N = 0;
	for (const FLeaf& L : Leaves)
	{
		if (!L.Mesh.IsValid())
		{
			continue;
		}
		if (AStaticMeshActor* Copy = W->SpawnActor<AStaticMeshActor>(AStaticMeshActor::StaticClass(), L.Rel * DeckFrame, SP))
		{
			UStaticMeshComponent* M = Copy->GetStaticMeshComponent();
			M->SetMobility(EComponentMobility::Movable);
			M->SetStaticMesh(L.Mesh.Get());
			for (int32 m = 0; m < L.Materials.Num(); ++m)
			{
				M->SetMaterial(m, L.Materials[m].Get());
			}
			M->SetCollisionProfileName(TEXT("BlockAll"));
			++N;
		}
	}
	if (AActor* Sign = W->SpawnActor<AActor>(AActor::StaticClass(), FTransform(DeckDoor), SP))
	{
		UTextRenderComponent* Text = NewObject<UTextRenderComponent>(Sign, TEXT("Sign"));
		Sign->SetRootComponent(Text);
		Text->RegisterComponent();
		Text->SetWorldLocationAndRotation(DeckDoor + FVector(0, 0, 255) + Out * 6.0, Out.Rotation());
		Text->SetHorizontalAlignment(EHTA_Center);
		Text->SetWorldSize(16.f);
		Text->SetTextRenderColor(FColor(225, 232, 240));
		Text->SetText(FText::FromString(RoomName.ToUpper() + TEXT("  ·  LIFT")));
	}
	UE_LOG(LogASTRA, Log, TEXT("[RoomLift] %s: the corridor's end on deck %d is at %.2f %.2f (%d pieces of door there)"), *RoomName, Deck, DeckDoor.X / 100.0, DeckDoor.Y / 100.0, N);
}

void AAstraRoomLift::Arrive()
{
	APawn* Me = Rider.Get();
	if (!Me)
	{
		return;
	}
	SettleDeckEnd();
	const FVector Feet = OnFloor(GetWorld(), bToRoom ? RoomFeet : DeckFeet, Me);
	const float Half = Me->IsA<ACharacter>() ? Cast<ACharacter>(Me)->GetCapsuleComponent()->GetScaledCapsuleHalfHeight() : 90.f;
	const float Yaw = bToRoom ? RoomYaw : DeckYaw;
	Me->SetActorLocationAndRotation(Feet + FVector(0, 0, Half + 2.f), FRotator(0.f, Yaw, 0.f), false, nullptr, ETeleportType::TeleportPhysics);
	if (AController* C = Me->GetController())
	{
		C->SetControlRotation(FRotator(0.f, Yaw, 0.f));
	}
	if (ACharacter* Ch = Cast<ACharacter>(Me))
	{
		Ch->GetCharacterMovement()->StopMovementImmediately();
		Ch->GetCharacterMovement()->SetMovementMode(MOVE_Walking);
	}
}

void AAstraRoomLift::Tick(float DeltaTime)
{
	Super::Tick(DeltaTime);
	APawn* Me = Stage == EStage::Idle ? UGameplayStatics::GetPlayerPawn(this, 0) : Rider.Get();
	switch (Stage)
	{
	case EStage::Idle:
	{
		if (!bDeckSettled)
		{
			if (const UAstraDeckStreaming* D = GetWorld()->GetSubsystem<UAstraDeckStreaming>(); !D || D->IsDeckReady(Deck))
			{
				SettleDeckEnd();
			}
		}
		// the hint, once each time he comes up to either end's doors
		const bool bNearRoom = Near(Me, RoomDoor), bNearDeck = Near(Me, DeckDoor);
		if ((bNearRoom || bNearDeck) && !bHinted)
		{
			bHinted = true;
			if (AASTRAPlayerController* PC = Me ? Cast<AASTRAPlayerController>(Me->GetController()) : nullptr)
			{
				PC->Subtitle(-9100 - (int32)(GetUniqueID() % 50), TEXT("notice"), TEXT("LIFT"),
				             bNearRoom ? FString::Printf(TEXT("E · up to Deck %d"), Deck) : FString::Printf(TEXT("E · to %s"), *RoomName), 3.f);
			}
		}
		else if (!bNearRoom && !bNearDeck)
		{
			bHinted = false;
		}
		break;
	}
	case EStage::Closing:
		T += DeltaTime;
		if (T >= 0.5f)
		{
			Stage = EStage::Moving;
			T = 0.f;
			if (SndHum)
			{
				UGameplayStatics::PlaySound2D(this, SndHum, 0.5f);
			}
		}
		break;
	case EStage::Moving:
	{
		T += DeltaTime;
		const UAstraDeckStreaming* D = GetWorld()->GetSubsystem<UAstraDeckStreaming>();
		const bool bReady = !D || D->IsReadyAt(bToRoom ? RoomFeet : DeckFeet);
		if ((bReady && T >= 1.4f) || T >= 8.f)
		{
			Arrive();
			Stage = EStage::Opening;
			T = 0.f;
			if (SndChime)
			{
				UGameplayStatics::PlaySound2D(this, SndChime, 0.6f);
			}
		}
		break;
	}
	case EStage::Opening:
		T += DeltaTime;
		if (T >= 0.15f)
		{
			if (APlayerController* PC = Me ? Cast<APlayerController>(Me->GetController()) : nullptr)
			{
				if (PC->PlayerCameraManager)
				{
					PC->PlayerCameraManager->StartCameraFade(1.f, 0.f, 0.6f, FLinearColor::Black, true, false);
				}
				PC->SetIgnoreMoveInput(false);
			}
			Stage = EStage::Idle;
			bHinted = true;                                   // (he arrives at the other end's doors: no hint to ride straight back)
			Rider.Reset();
			SetActorTickInterval(0.1f);
		}
		break;
	}
}

// ---------------------------------------------------------------------------------------------- the lifts, from the plan
bool UAstraRoomLifts::ShouldCreateSubsystem(UObject* Outer) const
{
	const UWorld* W = Cast<UWorld>(Outer);
	return W && (W->WorldType == EWorldType::Game || W->WorldType == EWorldType::PIE);
}

void UAstraRoomLifts::OnWorldBeginPlay(UWorld& InWorld)
{
	Super::OnWorldBeginPlay(InWorld);
	Build(InWorld);
}

void UAstraRoomLifts::Build(UWorld& W)
{
	const UAstraShipPlan* Plan = W.GetSubsystem<UAstraShipPlan>();
	if (!Plan || !Plan->EnsureLoaded())
	{
		return;
	}
	const TArray<FAstraPlanCompartment>& Comps = Plan->GetCompartments();
	for (const FAstraPlanDoor& Dr : Plan->GetDoors())
	{
		if (!Comps.IsValidIndex(Dr.A) || !Comps.IsValidIndex(Dr.B))
		{
			continue;
		}
		const bool bAIsRoom = Comps[Dr.A].bExisting && !Comps[Dr.B].bBuilt;
		const bool bBIsRoom = Comps[Dr.B].bExisting && !Comps[Dr.A].bBuilt;
		if (!bAIsRoom && !bBIsRoom)
		{
			continue;
		}
		const int32 RoomI = bAIsRoom ? Dr.A : Dr.B, LobbyI = bAIsRoom ? Dr.B : Dr.A;
		const FAstraPlanCompartment& Room = Comps[RoomI];
		const FAstraPlanCompartment& Lobby = Comps[LobbyI];
		const FVector LobbyMid = Lobby.Box.GetCenter();
		// the deck's end: the nearest place of a built compartment on the lobby's deck, at its floor
		int32 Best = INDEX_NONE;
		double BestD = 1000.0;
		for (int32 i = 0; i < Plan->NumNodes(); ++i)
		{
			const FAstraPlanNode* N = Plan->Node(i);
			if (!N || N->Deck != Lobby.Deck || !Comps.IsValidIndex(N->Comp) || N->Comp == LobbyI || N->Comp == RoomI || !Comps[N->Comp].bBuilt)
			{
				continue;
			}
			const double D = FVector::Dist2D(N->Pos, LobbyMid);
			if (D < BestD && FMath::Abs(N->Pos.Z - Lobby.Box.Min.Z) < 120.0)
			{
				BestD = D;
				Best = i;
			}
		}
		if (Best == INDEX_NONE)
		{
			UE_LOG(LogASTRA, Warning, TEXT("[RoomLift] %s: no corridor near its lobby on deck %d"), *Room.Name, Lobby.Deck);
			continue;
		}
		const FVector Corr = Plan->Node(Best)->Pos;
		const FVector DeckDoor(FMath::Clamp(Corr.X, Lobby.Box.Min.X, Lobby.Box.Max.X), FMath::Clamp(Corr.Y, Lobby.Box.Min.Y, Lobby.Box.Max.Y), Lobby.Box.Min.Z);
		const FVector Out = Flat(Corr - DeckDoor).IsNearlyZero() ? Flat(Corr - LobbyMid) : Flat(Corr - DeckDoor);
		const FVector In = Flat(Room.Box.GetCenter() - Dr.Pos);

		FActorSpawnParameters SP;
		SP.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
		AAstraRoomLift* L = W.SpawnActor<AAstraRoomLift>(Dr.Pos, FRotator::ZeroRotator, SP);
		if (!L)
		{
			continue;
		}
		L->RoomName = Room.Name;
		L->Deck = Lobby.Deck;
		L->RoomDoor = Dr.Pos;
		L->DeckDoor = DeckDoor;
		L->RoomFeet = Dr.Pos + In * 180.0;
		L->DeckFeet = DeckDoor + Out * 130.0;
		L->RoomYaw = In.Rotation().Yaw;
		L->DeckYaw = Out.Rotation().Yaw;
		L->SndThump = RoomLiftSound(TEXT("SW_Lift_Thump"));
		L->SndChime = RoomLiftSound(TEXT("SW_Lift_Chime"));
		L->SndHum = RoomLiftSound(TEXT("SW_Lift_Hum"));
		Lifts.Add(L);

		// the alcove's doors, to be copied at the corridor's end once its deck is in (SettleDeckEnd)
		L->Corridor = Corr;
		L->Out = Out;
		L->RoomIn = In;
		const FTransform RoomFrame(In.Rotation(), Dr.Pos);
		int32 Leaves = 0;
		for (TActorIterator<AStaticMeshActor> It(&W); It; ++It)
		{
			const FVector P = It->GetActorLocation();
			const UStaticMeshComponent* Mc = It->GetStaticMeshComponent();
			if (FVector::Dist2D(P, Dr.Pos) > 90.0 || FMath::Abs(P.Z - Dr.Pos.Z) > 250.0 || !Mc || !Mc->GetStaticMesh())
			{
				continue;
			}
			AAstraRoomLift::FLeaf Leaf;
			Leaf.Mesh = Mc->GetStaticMesh();
			for (int32 m = 0; m < Mc->GetNumMaterials(); ++m)
			{
				Leaf.Materials.Add(Mc->GetMaterial(m));
			}
			Leaf.Rel = It->GetActorTransform().GetRelativeTransform(RoomFrame);
			L->Leaves.Add(Leaf);
			++Leaves;
		}
		UE_LOG(LogASTRA, Log, TEXT("[RoomLift] %s: a lift from its alcove to deck %d near %.1f %.1f (%d pieces of door to copy at the corridor's end)"), *Room.Name, Lobby.Deck,
		       DeckDoor.X / 100.0, DeckDoor.Y / 100.0, Leaves);
	}
}
