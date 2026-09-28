// ASTRA — sliding pressure door.

#include "AstraDoor.h"

#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "GameFramework/Pawn.h"
#include "Kismet/GameplayStatics.h"
#include "Sound/SoundBase.h"
#include "UObject/ConstructorHelpers.h"

AAstraDoor::AAstraDoor()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.TickInterval = 0.f;
	Root = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	SetRootComponent(Root);
	static ConstructorHelpers::FObjectFinder<UStaticMesh> Leaf(TEXT("/Game/ASTRA/Kit/Interior/Corridor/SM_COR_DoorLeaf.SM_COR_DoorLeaf"));
	for (int32 i = 0; i < 2; ++i)
	{
		UStaticMeshComponent* C = CreateDefaultSubobject<UStaticMeshComponent>(i ? TEXT("LeafB") : TEXT("LeafA"));
		C->SetupAttachment(Root);
		C->SetMobility(EComponentMobility::Movable);
		if (Leaf.Succeeded())
		{
			C->SetStaticMesh(Leaf.Object);
		}
		(i ? LeafB : LeafA) = C;
	}
}

void AAstraDoor::BeginPlay()
{
	Super::BeginPlay();
	Place();
}

void AAstraDoor::Place()
{
	// kit leaf: 0.7 m wide towards local -Y, 2.3 m tall; the second one is mirrored
	const float SY = Width / 140.f, SZ = Height / 230.f;
	const float Slide = 70.f * SY * FMath::SmoothStep(0.f, 1.f, Open);
	LeafA->SetRelativeScale3D(FVector(1.f, SY, SZ));
	LeafB->SetRelativeScale3D(FVector(1.f, -SY, SZ));
	LeafA->SetRelativeLocation(FVector(0.f, -Slide, 0.f));
	LeafB->SetRelativeLocation(FVector(0.f, Slide, 0.f));
}

void AAstraDoor::Sound(bool bOpening)
{
	if (USoundBase* S = LoadObject<USoundBase>(nullptr, bOpening ? TEXT("/Game/ASTRA/Audio/SW_Door_Open.SW_Door_Open")
	                                                             : TEXT("/Game/ASTRA/Audio/SW_Door_Close.SW_Door_Close")))
	{
		UGameplayStatics::PlaySoundAtLocation(this, S, GetActorLocation() + FVector(0, 0, 120.f), 0.7f, FMath::FRandRange(0.96f, 1.04f));
	}
}

void AAstraDoor::Tick(float DeltaTime)
{
	Super::Tick(DeltaTime);
	bool bNear = false;
	if (!bLocked)
	{
		if (const APawn* P = UGameplayStatics::GetPlayerPawn(this, 0))
		{
			const FVector D = P->GetActorLocation() - GetActorLocation();
			bNear = FVector2D(D.X, D.Y).Size() < OpenRadius && FMath::Abs(D.Z) < 300.f;
		}
	}
	// close only after the way has been clear for a moment
	CloseDelay = bNear ? 1.2f : FMath::Max(0.f, CloseDelay - DeltaTime);
	const bool bWant = bNear || CloseDelay > 0.f;
	if (bWant != bWantOpen)
	{
		bWantOpen = bWant;
		Sound(bWant);
	}
	const float Target = bWantOpen ? 1.f : 0.f;
	if (Open != Target)
	{
		Open = FMath::FInterpConstantTo(Open, Target, DeltaTime, 1.f / FMath::Max(0.1f, SlideTime));
		Place();
	}
}
