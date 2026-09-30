// ASTRA — a crewman going about the ship.

#include "AstraWalker.h"

#include "AIController.h"
#include "Animation/AnimInstance.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/SkeletalMesh.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Materials/MaterialInterface.h"

AAstraWalker::AAstraWalker()
{
	PrimaryActorTick.bCanEverTick = true;
	AutoPossessAI = EAutoPossessAI::PlacedInWorldOrSpawned;
	AIControllerClass = AAIController::StaticClass();
	bUseControllerRotationYaw = false;
	GetCapsuleComponent()->InitCapsuleSize(34.f, 92.f);
	UCharacterMovementComponent* Move = GetCharacterMovement();
	Move->bOrientRotationToMovement = true;
	Move->RotationRate = FRotator(0.f, 240.f, 0.f);
	Move->MaxWalkSpeed = 135.f;
	Move->BrakingDecelerationWalking = 400.f;
	Move->MaxAcceleration = 500.f;
	Move->bUseRVOAvoidance = false;
	// the mannequin stands on the capsule's foot and faces the actor's +X
	GetMesh()->SetRelativeLocation(FVector(0.f, 0.f, -92.f));
	GetMesh()->SetRelativeRotation(FRotator(0.f, -90.f, 0.f));
	GetMesh()->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	GetMesh()->VisibilityBasedAnimTickOption = EVisibilityBasedAnimTickOption::OnlyTickPoseWhenRendered;   // unseen: it walks, the pose waits
	GetMesh()->bEnableUpdateRateOptimizations = true;
}

void AAstraWalker::BeginPlay()
{
	Super::BeginPlay();
	GetCharacterMovement()->MaxWalkSpeed = WalkSpeed;
	if (USkeletalMesh* Mesh = LoadObject<USkeletalMesh>(nullptr, bFemaleBody
		? TEXT("/Game/Characters/Mannequins/Meshes/SKM_Quinn_Simple.SKM_Quinn_Simple")
		: TEXT("/Game/Characters/Mannequins/Meshes/SKM_Manny_Simple.SKM_Manny_Simple")))
	{
		GetMesh()->SetSkeletalMeshAsset(Mesh);
	}
	if (UClass* Anim = LoadClass<UAnimInstance>(nullptr, TEXT("/Game/Characters/Mannequins/Anims/Unarmed/ABP_Unarmed.ABP_Unarmed_C")))
	{
		GetMesh()->SetAnimInstanceClass(Anim);
	}
	// the uniform: navy trousers, the department's jacket (as the crew at their stations)
	UMaterialInterface* Uniform = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/ASTRA/Crew/Materials/MI_Crew_Uniform.MI_Crew_Uniform"));
	UMaterialInterface* Jacket = LoadObject<UMaterialInterface>(nullptr, *FString::Printf(TEXT("/Game/ASTRA/Crew/Materials/MI_Crew_Dept_%s.MI_Crew_Dept_%s"), *Dept, *Dept));
	if (Uniform && Jacket && GetMesh()->GetNumMaterials() >= 2)
	{
		GetMesh()->SetMaterial(0, Uniform);
		GetMesh()->SetMaterial(1, Jacket);
	}
	// start somewhere along the round, not all at once
	Next = Route.Num() ? FMath::RandRange(0, Route.Num() - 1) : 0;
	Wait = FMath::FRandRange(0.f, PauseRange.Y);
}

void AAstraWalker::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	if (Route.Num() < 2)
	{
		return;
	}
	if (Wait > 0.f)
	{
		Wait -= DeltaSeconds;
		return;
	}
	const FVector To = (Route[Next] - GetActorLocation()) * FVector(1.f, 1.f, 0.f);
	if (To.Size() < 45.f)
	{
		// a stop: a look at a screen, a word with someone; then the next leg of the round
		Next = (Next + 1) % Route.Num();
		Wait = FMath::FRandRange(PauseRange.X, PauseRange.Y);
		Stuck = 0.f;
		return;
	}
	AddMovementInput(To.GetSafeNormal(), 1.f);
	// someone in the way (the Captain in a narrow corridor): after a while, turn back to the next stop
	Stuck = GetVelocity().Size2D() < 20.f ? Stuck + DeltaSeconds : 0.f;
	if (Stuck > 2.5f)
	{
		Next = (Next + 1) % Route.Num();
		Stuck = 0.f;
		Wait = 1.5f;
	}
}
