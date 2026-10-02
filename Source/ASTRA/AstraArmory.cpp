#include "AstraArmory.h"

#include "ASTRA.h"
#include "AstraCombatFx.h"
#include "AstraFpsComponent.h"
#include "AstraWeapon.h"
#include "Camera/CameraComponent.h"
#include "Components/SceneComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "Kismet/GameplayStatics.h"
#include "GameFramework/Pawn.h"
#include "HAL/IConsoleManager.h"
#include "Materials/MaterialInterface.h"

namespace
{
	constexpr float ArmoryReachCm = 230.f;
}

AAstraArmoryRack::AAstraArmoryRack()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.TickInterval = 0.08f;
	SetRootComponent(CreateDefaultSubobject<USceneComponent>(TEXT("Root")));
}

void AAstraArmoryRack::BeginPlay()
{
	Super::BeginPlay();
	UStaticMesh* Cube = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cube.Cube"));
	UMaterialInterface* Steel = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/ASTRA/Materials/Instances/MI_ASTRA_Structure.MI_ASTRA_Structure"));
	UMaterialInterface* Trim = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/ASTRA/Materials/Instances/MI_ASTRA_Trim.MI_ASTRA_Trim"));
	const auto Piece = [&](const FVector& Loc, const FVector& Size, UMaterialInterface* M) -> UStaticMeshComponent*
	{
		UStaticMeshComponent* C = NewObject<UStaticMeshComponent>(this);
		C->SetupAttachment(GetRootComponent());
		C->SetStaticMesh(Cube);
		if (M)
		{
			C->SetMaterial(0, M);
		}
		C->SetRelativeLocation(Loc);
		C->SetRelativeScale3D(Size / 100.f);
		C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		C->RegisterComponent();
		Parts.Add(C);
		return C;
	};
	if (Cube)
	{
		// a freestanding rack: a foot, a back panel with two bars and a lamp strip; the weapons lie on its bars, barrels along the panel
		Piece(FVector(0, 0, 3), FVector(34, 150, 6), Steel);
		Frame = Piece(FVector(-12, 0, 100), FVector(5, 140, 190), Steel);
		Piece(FVector(-5, 0, 128), FVector(6, 124, 3), Trim);
		Piece(FVector(-5, 0, 74), FVector(6, 124, 3), Trim);
		Piece(FVector(-9, 0, 188), FVector(3, 60, 3), Trim);
	}
	const FAstraWeaponDef& R = AstraWeapons::Get(EAstraWeapon::Rifle);
	const FAstraWeaponDef& P = AstraWeapons::Get(EAstraWeapon::Pistol);
	if (UStaticMesh* RM = LoadObject<UStaticMesh>(nullptr, R.MeshPath))
	{
		Rifle = NewObject<UStaticMeshComponent>(this);
		Rifle->SetupAttachment(GetRootComponent());
		Rifle->SetStaticMesh(RM);
		Rifle->SetRelativeLocation(FVector(1, -18, 134));
		Rifle->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		Rifle->RegisterComponent();
		if (UStaticMesh* MM = LoadObject<UStaticMesh>(nullptr, R.MagPath))
		{
			UStaticMeshComponent* Mg = NewObject<UStaticMeshComponent>(this);
			Mg->SetupAttachment(Rifle);
			Mg->SetStaticMesh(MM);
			Mg->SetCollisionEnabled(ECollisionEnabled::NoCollision);
			Mg->RegisterComponent();
			Parts.Add(Mg);
		}
	}
	if (UStaticMesh* PM = LoadObject<UStaticMesh>(nullptr, P.MeshPath))
	{
		Pistol = NewObject<UStaticMeshComponent>(this);
		Pistol->SetupAttachment(GetRootComponent());
		Pistol->SetStaticMesh(PM);
		Pistol->SetRelativeLocation(FVector(1, 38, 82));
		Pistol->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		Pistol->RegisterComponent();
	}
	Show(true);
}

void AAstraArmoryRack::Show(bool bWeaponsThere)
{
	bShowingWeapons = bWeaponsThere;
	for (UStaticMeshComponent* C : {Rifle.Get(), Pistol.Get()})
	{
		if (C)
		{
			C->SetVisibility(bWeaponsThere, true);
		}
	}
}

bool AAstraArmoryRack::IsWithinReach(const APawn* Me) const
{
	if (!Me)
	{
		return false;
	}
	const FVector At = GetActorLocation() + GetActorRotation().RotateVector(FVector(30.f, 0.f, 0.f));
	return FVector::Dist2D(Me->GetActorLocation(), At) < ArmoryReachCm + 60.0 && FMath::Abs(Me->GetActorLocation().Z - GetActorLocation().Z) < 220.0;
}

bool AAstraArmoryRack::TryUse(APawn* Me)
{
	if (!IsWithinReach(Me))
	{
		return false;
	}
	UAstraFpsComponent* F = Me->FindComponentByClass<UAstraFpsComponent>();
	if (!F)
	{
		return false;
	}
	F->SetKit(!F->HasKit());
	Show(!F->HasKit());
	if (UAstraCombatFx* Fx = GetWorld() ? GetWorld()->GetSubsystem<UAstraCombatFx>() : nullptr)
	{
		Fx->PlaySoundAt(TEXT("/Game/ASTRA/Audio/SW_Gun_Draw.SW_Gun_Draw"), GetActorLocation() + FVector(0, 0, 120), 0.9f, F->HasKit() ? 1.f : 0.85f);
	}
	F->Prompt(F->HasKit() ? TEXT("RIFLE AND SIDEARM TAKEN   ·   LMB fire   RMB aim   R reload   1 / 2 weapons   H holster") : TEXT("WEAPONS RETURNED TO THE RACK"), 4.f);
	return true;
}

void AAstraArmoryRack::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	const APawn* Me = GetWorld() ? UGameplayStatics::GetPlayerPawn(GetWorld(), 0) : nullptr;
	UAstraFpsComponent* F = Me ? Me->FindComponentByClass<UAstraFpsComponent>() : nullptr;
	if (!F)
	{
		return;
	}
	// the rack shows what is on it (the Captain's own weapons are in his hands, not on the rack)
	if (bShowingWeapons == F->HasKit())
	{
		Show(!F->HasKit());
	}
	if (!IsWithinReach(Me))
	{
		return;
	}
	const UCameraComponent* Cam = Me->FindComponentByClass<UCameraComponent>();
	if (Cam)
	{
		const FVector To = (GetActorLocation() + FVector(0, 0, 110) - Cam->GetComponentLocation()).GetSafeNormal();
		if (FVector::DotProduct(To, Cam->GetForwardVector()) < 0.45f)
		{
			return;                                   // he is not looking at it
		}
	}
	F->Prompt(F->HasKit() ? TEXT("E   PUT THE WEAPONS BACK") : TEXT("E   TAKE THE RIFLE AND THE SIDEARM"), 0.25f);
}

namespace
{
	FAutoConsoleCommandWithWorld ArmoryCmdHere(TEXT("astra.armory.here"), TEXT("Testing: a weapon rack on the deck in front of the Captain (E takes the weapons)"),
		FConsoleCommandWithWorldDelegate::CreateLambda([](UWorld* W)
		{
			const APawn* Me = W ? UGameplayStatics::GetPlayerPawn(W, 0) : nullptr;
			if (!Me)
			{
				return;
			}
			const FVector Fwd = FRotator(0.f, Me->GetControlRotation().Yaw, 0.f).Vector();
			FVector At = Me->GetActorLocation() + Fwd * 130.f;
			At.Z -= Me->GetSimpleCollisionHalfHeight();
			FActorSpawnParameters Sp;
			Sp.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
			W->SpawnActor<AAstraArmoryRack>(At, FRotator(0.f, Me->GetControlRotation().Yaw + 180.f, 0.f), Sp);
		}));
}
