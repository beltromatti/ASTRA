// ASTRA — a proving ground for the lifts (see AstraLiftTestRig.h).

#include "AstraLiftTestRig.h"

#include "ASTRA.h"
#include "AstraLiftCar.h"
#include "AstraLiftSubsystem.h"
#include "Components/BoxComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Misc/Paths.h"

namespace
{
	/** A box of the arena in an actor's frame: collision always, a plain cube to see it when asked. */
	void LiftSlab(AActor* Owner, const FName& Name, const FVector& Centre, const FRotator& Rot, const FVector& HalfExtent, bool bVisible, UStaticMesh* Cube)
	{
		UBoxComponent* B = NewObject<UBoxComponent>(Owner, Name);
		B->SetupAttachment(Owner->GetRootComponent());
		B->SetBoxExtent(HalfExtent, false);
		B->SetWorldLocationAndRotation(Centre, Rot);
		B->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
		B->SetCollisionObjectType(ECC_WorldStatic);
		B->SetCollisionResponseToAllChannels(ECR_Block);
		B->SetGenerateOverlapEvents(false);
		B->SetCanEverAffectNavigation(false);
		B->SetHiddenInGame(true);
		B->RegisterComponent();
		if (bVisible && Cube)
		{
			UStaticMeshComponent* M = NewObject<UStaticMeshComponent>(Owner, *(Name.ToString() + TEXT("_Look")));
			M->SetupAttachment(Owner->GetRootComponent());
			M->SetStaticMesh(Cube);
			M->SetWorldLocationAndRotation(Centre, Rot);
			M->SetWorldScale3D(HalfExtent * 2.f / 100.f);
			M->SetCollisionEnabled(ECollisionEnabled::NoCollision);
			M->RegisterComponent();
		}
	}
}

void AstraLiftArena::Build(AActor* Owner, const FAstraLiftNetwork& Net, bool bVisible)
{
	UStaticMesh* Cube = bVisible ? LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cube.Cube"), nullptr, LOAD_NoWarn | LOAD_Quiet) : nullptr;
	int32 N = 0;
	for (const FAstraLiftLine& L : Net.Lines)
	{
		if (L.bShuttle)
		{
			// the platform: a floor along the line on the lobby side, and the tunnel's floor under the car's track
			const FRotator Yaw(0.f, L.FrontYaw, 0.f);
			for (int32 S = 0; S < L.Stops.Num(); ++S)
			{
				const FAstraLiftStop& St = L.Stops[S];
				const FVector Centre = St.DoorCm + St.Out * 300.f - FVector(0.f, 0.f, 20.f);
				LiftSlab(Owner, *FString::Printf(TEXT("Platform_%s_%d"), *L.Id, S), Centre, Yaw, FVector(300.f, 900.f, 20.f), bVisible, Cube);
				++N;
			}
			const FVector Mid = (L.Path.At(0.f) + L.Path.At(L.Path.Length)) * 0.5f;
			LiftSlab(Owner, *FString::Printf(TEXT("Track_%s"), *L.Id), Mid - FVector(0.f, 0.f, 40.f), Yaw, FVector(FMath::Abs(L.Path.Length) * 0.5f + 800.f, 200.f, 20.f), bVisible, Cube);
			continue;
		}
		const FAstraLiftSpec Spec = FAstraLiftSpec::Make(L);
		const FRotator Yaw(0.f, L.FrontYaw, 0.f);
		const FTransform Frame(Yaw, FVector(L.ShaftCm.X, L.ShaftCm.Y, 0.f));      // the shaft's own frame: +X toward the doors, origin at its middle
		auto World = [&Frame](const FVector& Local) { return Frame.TransformPosition(Local); };
		const float Bottom = L.ZBottom - 150.f, Top = L.ZTop + 600.f;
		const float HW = L.ShaftW * 0.5f + 10.f, HD = L.ShaftD * 0.5f;
		// the shaft: the back and the two sides, the whole way
		LiftSlab(Owner, *FString::Printf(TEXT("ShaftBack_%s"), *L.Id), World(FVector(-HD - 10.f, 0.f, (Top + Bottom) * 0.5f)), Yaw, FVector(10.f, HW + 10.f, (Top - Bottom) * 0.5f), bVisible, Cube);
		for (const float Side : {-1.f, 1.f})
		{
			LiftSlab(Owner, *FString::Printf(TEXT("ShaftSide_%s_%d"), *L.Id, Side > 0.f), World(FVector(0.f, Side * (HW + 10.f), (Top + Bottom) * 0.5f)), Yaw, FVector(HD, 10.f, (Top - Bottom) * 0.5f), bVisible, Cube);
		}
		LiftSlab(Owner, *FString::Printf(TEXT("ShaftPit_%s"), *L.Id), World(FVector(0.f, 0.f, Bottom - 10.f)), Yaw, FVector(HD, HW, 10.f), bVisible, Cube);
		// the front wall (on the +X side): solid except at the doors: the piers either side of each opening, the wall between landings
		const float OpW = Spec.Openings[0].Width, OpH = Spec.Openings[0].Height;
		const float Pier = HW - OpW * 0.5f;
		float Z = Bottom;
		for (int32 S = 0; S <= L.Stops.Num(); ++S)
		{
			const float StopZ = S < L.Stops.Num() ? L.Stops[S].FloorZ : Top;
			if (StopZ - Z > 1.f)
			{
				LiftSlab(Owner, *FString::Printf(TEXT("FrontWall_%s_%d"), *L.Id, S), World(FVector(HD + 10.f, 0.f, (Z + StopZ) * 0.5f)), Yaw, FVector(10.f, HW, (StopZ - Z) * 0.5f), bVisible, Cube);
			}
			if (S < L.Stops.Num())
			{
				const FAstraLiftStop& St = L.Stops[S];
				const float Z0 = St.FloorZ;
				for (const float Side : {-1.f, 1.f})
				{
					LiftSlab(Owner, *FString::Printf(TEXT("Pier_%s_%d_%d"), *L.Id, S, Side > 0.f), World(FVector(HD + 10.f, Side * (OpW * 0.5f + Pier * 0.5f), Z0 + OpH * 0.5f)), Yaw,
					     FVector(10.f, Pier * 0.5f, OpH * 0.5f), bVisible, Cube);
				}
				// the lobby: a floor in front of the doors, and a wall either side so that nobody walks round to the back of the shaft
				LiftSlab(Owner, *FString::Printf(TEXT("Lobby_%s_%d"), *L.Id, S), World(FVector(HD + 20.f + 350.f, 0.f, Z0 - 20.f)), Yaw, FVector(350.f, 450.f, 20.f), bVisible, Cube);
				Z = Z0 + OpH;
				++N;
			}
		}
		// (the wall above the last landing's doors is the front wall's last piece: Z ran on to it)
	}
	UE_LOG(LogASTRA, Log, TEXT("[Lift] test arena: %d landings' floors and the walls of %d lines"), N, Net.Lines.Num());
}

AAstraLiftTestRig::AAstraLiftTestRig()
{
	PrimaryActorTick.bCanEverTick = false;
	SetRootComponent(CreateDefaultSubobject<USceneComponent>(TEXT("Root")));
}

void AAstraLiftTestRig::BeginPlay()
{
	Super::BeginPlay();
	UAstraLiftSubsystem* Lifts = GetWorld() ? GetWorld()->GetSubsystem<UAstraLiftSubsystem>() : nullptr;
	if (!Lifts)
	{
		return;
	}
	const FString Path = FPaths::IsRelative(PlanPath) ? FPaths::Combine(FPaths::ProjectDir(), PlanPath) : PlanPath;
	if (!Lifts->LoadNetwork(Path))
	{
		UE_LOG(LogASTRA, Warning, TEXT("[Lift] the test rig cannot read %s"), *Path);
		return;
	}
	AstraLiftArena::Build(this, Lifts->Network(), bVisible);
}
