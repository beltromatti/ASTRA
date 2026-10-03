#include "AstraArmory.h"

#include "ASTRA.h"
#include "AstraBoardSubsystem.h"
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
	constexpr float LockerReachCm = 170.f;
}

AAstraArmoryRack::AAstraArmoryRack()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.TickInterval = 0.08f;
	SetRootComponent(CreateDefaultSubobject<USceneComponent>(TEXT("Root")));
}

void AAstraArmoryRack::MakePost(FName InPostId, EKind InKind)
{
	PostId = InPostId;
	Kind = InKind;
}

void AAstraArmoryRack::BeginPlay()
{
	Super::BeginPlay();
	UStaticMesh* Cube = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cube.Cube"));
	UMaterialInterface* Steel = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/ASTRA/Materials/Instances/MI_ASTRA_Structure.MI_ASTRA_Structure"));
	UMaterialInterface* Trim = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/ASTRA/Materials/Instances/MI_ASTRA_Trim.MI_ASTRA_Trim"));
	const auto Piece = [&](const FVector& Loc, const FVector& Size, UMaterialInterface* M, const FRotator& Rot = FRotator::ZeroRotator) -> UStaticMeshComponent*
	{
		UStaticMeshComponent* C = NewObject<UStaticMeshComponent>(this);
		C->SetupAttachment(GetRootComponent());
		C->SetStaticMesh(Cube);
		if (M)
		{
			C->SetMaterial(0, M);
		}
		C->SetRelativeLocation(Loc);
		C->SetRelativeRotation(Rot);
		C->SetRelativeScale3D(Size / 100.f);
		C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		C->RegisterComponent();
		Parts.Add(C);
		return C;
	};
	const FAstraWeaponDef& R = AstraWeapons::Get(EAstraWeapon::Rifle);
	const FAstraWeaponDef& P = AstraWeapons::Get(EAstraWeapon::Pistol);
	if (Kind == EKind::Rack)
	{
		if (Cube)
		{
			// a freestanding rack: a foot, a back panel with two bars and a lamp strip; the weapons lie on its bars, barrels along the panel
			Piece(FVector(0, 0, 3), FVector(34, 150, 6), Steel);
			Frame = Piece(FVector(-12, 0, 100), FVector(5, 140, 190), Steel);
			Piece(FVector(-5, 0, 128), FVector(6, 124, 3), Trim);
			Piece(FVector(-5, 0, 74), FVector(6, 124, 3), Trim);
			Piece(FVector(-9, 0, 188), FVector(3, 60, 3), Trim);
		}
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
	}
	else if (Cube)
	{
		// a small steel locker on the wall (the actor stands on the floor under it, its front along +X): a body with an inner back, the door swung wide, a hook bar and the sidearm hanging
		// on it; a green lamp over the door says it is the Captain's
		Piece(FVector(-9, 0, 144), FVector(18, 40, 80), Steel);                                   // the cabinet (40 cm wide: it stands in a 66 cm stretch of wall)
		Frame = Piece(FVector(-0.5, 0, 144), FVector(1.2, 34, 74), Trim);                         // its inner back (inside the mouth)
		Piece(FVector(3.0, 0, 119), FVector(5, 32, 3), Steel);                                   // the shelf under the weapon
		Piece(FVector(1.5, 0, 168), FVector(3, 30, 3), Steel);                                   // the hook bar
		Piece(FVector(14.7, -16.9, 144), FVector(1.8, 30, 74), Steel, FRotator(0.f, -78.f, 0.f)); // the door, open on its hinge at the left
		Piece(FVector(3.0, 0, 188), FVector(2, 14, 1.4), Trim);                                  // the lamp's plate
		if (UStaticMesh* PM = LoadObject<UStaticMesh>(nullptr, P.MeshPath))
		{
			Pistol = NewObject<UStaticMeshComponent>(this);
			Pistol->SetupAttachment(GetRootComponent());
			Pistol->SetStaticMesh(PM);
			Pistol->SetRelativeLocation(FVector(3.5, 0, 150));
			Pistol->SetRelativeRotation(FRotator(0.f, 0.f, 0.f));
			Pistol->SetCollisionEnabled(ECollisionEnabled::NoCollision);
			Pistol->RegisterComponent();
		}
	}
	Show(true, true);
}

void AAstraArmoryRack::Show(bool bRifleThere, bool bPistolThere)
{
	bShowRifle = bRifleThere;
	bShowPistol = bPistolThere;
	if (Rifle)
	{
		Rifle->SetVisibility(bRifleThere, true);
	}
	if (Pistol)
	{
		Pistol->SetVisibility(bPistolThere, true);
	}
}

bool AAstraArmoryRack::IsWithinReach(const APawn* Me) const
{
	if (!Me)
	{
		return false;
	}
	const FVector At = GetActorLocation() + GetActorRotation().RotateVector(FVector(30.f, 0.f, 0.f));
	return FVector::Dist2D(Me->GetActorLocation(), At) < (Kind == EKind::Rack ? ArmoryReachCm + 60.0 : LockerReachCm) && FMath::Abs(Me->GetActorLocation().Z - GetActorLocation().Z) < 220.0;
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
	FString Notice;
	if (!PostId.IsNone())
	{
		// a post of the ship's: it holds what it holds (the board subsystem keeps the stock)
		UAstraBoardSubsystem* Board = GetWorld() ? GetWorld()->GetSubsystem<UAstraBoardSubsystem>() : nullptr;
		if (!Board || !Board->UseArmsPost(PostId, Me, Notice))
		{
			return false;                             // (in reach, and nothing to take or to put back: the key is another's)
		}
	}
	else
	{
		F->SetKit(!F->HasKit());
		Notice = F->HasKit() ? TEXT("RIFLE AND SIDEARM TAKEN   ·   LMB fire   RMB aim   R reload   1 / 2 weapons   H holster") : TEXT("WEAPONS RETURNED TO THE RACK");
	}
	if (UAstraCombatFx* Fx = GetWorld() ? GetWorld()->GetSubsystem<UAstraCombatFx>() : nullptr)
	{
		Fx->PlaySoundAt(TEXT("/Game/ASTRA/Audio/SW_Gun_Draw.SW_Gun_Draw"), GetActorLocation() + FVector(0, 0, 120), 0.9f, F->HasKit() ? 1.f : 0.85f);
	}
	F->Prompt(Notice, 4.f);
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
	FString Prompt;
	if (!PostId.IsNone())
	{
		// the post shows what the ship's stock says is on it
		const UAstraBoardSubsystem* Board = GetWorld() ? GetWorld()->GetSubsystem<UAstraBoardSubsystem>() : nullptr;
		bool bRifle = false, bPistol = false;
		if (Board && Board->ArmsPostView(PostId, F, bRifle, bPistol, Prompt))
		{
			if (bRifle != bShowRifle || bPistol != bShowPistol)
			{
				Show(bRifle, bPistol);
			}
		}
	}
	else
	{
		// a level's rack shows what is on it (the Captain's own weapons are in his hands, not on the rack)
		if (bShowRifle == F->HasKit())
		{
			Show(!F->HasKit(), !F->HasKit());
		}
		Prompt = F->HasKit() ? TEXT("E   PUT THE WEAPONS BACK") : TEXT("E   TAKE THE RIFLE AND THE SIDEARM");
	}
	if (!IsWithinReach(Me) || Prompt.IsEmpty())
	{
		return;
	}
	const UCameraComponent* Cam = Me->FindComponentByClass<UCameraComponent>();
	if (Cam)
	{
		const FVector To = (GetActorLocation() + FVector(0, 0, Kind == EKind::Locker ? 150 : 110) - Cam->GetComponentLocation()).GetSafeNormal();
		if (FVector::DotProduct(To, Cam->GetForwardVector()) < 0.45f)
		{
			return;                                   // he is not looking at it
		}
	}
	F->Prompt(Prompt, 0.25f);
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
