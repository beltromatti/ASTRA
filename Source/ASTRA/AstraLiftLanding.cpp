// ASTRA — a lift's landings and shaft (see AstraLiftCar.h).

#include "AstraLiftCar.h"

#include "ASTRA.h"
#include "Components/BoxComponent.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"

namespace
{
	// the shaft's segments (the kit's meshes are built to these heights)
	constexpr float LiftSegH = 400.f;            // a plain segment
	constexpr float LiftDoorSegH = 320.f;        // a segment with a landing's opening in it: from this far under the floor
	constexpr float LiftDoorSegDown = 40.f;

	UStaticMeshComponent* LiftMakeMesh(AActor* Owner, USceneComponent* Parent, const FName& Name, UStaticMesh* Mesh, const FVector& Rel, const FVector& Scale)
	{
		UStaticMeshComponent* M = NewObject<UStaticMeshComponent>(Owner, Name);
		M->SetupAttachment(Parent);
		M->SetMobility(EComponentMobility::Movable);
		M->SetStaticMesh(Mesh);
		M->SetRelativeLocation(Rel);
		M->SetRelativeScale3D(Scale);
		M->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		M->SetCanEverAffectNavigation(false);
		M->SetGenerateOverlapEvents(false);
		M->RegisterComponent();
		return M;
	}
}

// ============================================================================================================================ landing

AAstraLiftLanding::AAstraLiftLanding()
{
	PrimaryActorTick.bCanEverTick = false;
	SetRootComponent(CreateDefaultSubobject<USceneComponent>(TEXT("Root")));
	GetRootComponent()->SetMobility(EComponentMobility::Movable);
}

void AAstraLiftLanding::Setup(const FAstraLiftLine& InLine, int32 InStop, const FAstraLiftSpec& InSpec)
{
	Stop = InStop;
	Spec = InSpec;
	const FAstraLiftStop& S = InLine.Stops[InStop];
	OutDir = S.Out;
	bDoors = !InLine.bShuttle;
	SetActorLocationAndRotation(S.DoorCm, FRotator(0.f, InLine.FrontYaw, 0.f), false, nullptr, ETeleportType::TeleportPhysics);
	const FAstraLiftSpec::FOpening& Op = Spec.Openings[0];
	PanelLocal = bDoors ? FVector(6.f, -(Op.Width * 0.5f + 45.f), 110.f) : FVector(130.f, -175.f, 110.f);
	if (bDoors)
	{
		// the doors: a pair of leaves just outside the shaft's front plane (X 0.5 to 6.5 cm: three and a half centimetres from the car's sill), closed over the opening and sliding apart into the frame's piers
		UStaticMesh* LeafKit = AstraLiftKit::Mesh(FString::Printf(TEXT("SM_LIFT_LandingLeaf_%s"), *Spec.Suffix));
		UStaticMesh* CubeMesh = AstraLiftKit::Cube();
		for (int32 Side = 0; Side < 2; ++Side)
		{
			const float HalfW = Op.Width * 0.25f + 1.f;
			const FVector Scale = LeafKit ? FVector(1.f, Side ? 1.f : -1.f, 1.f) : FVector(Spec.DoorLeaf / 100.f, HalfW * 2.f / 100.f, Op.Height / 100.f);
			if (LeafKit || CubeMesh)
			{
				LeafMesh.Add(LiftMakeMesh(this, GetRootComponent(), *FString::Printf(TEXT("Leaf%d"), Side), LeafKit ? LeafKit : CubeMesh, FVector::ZeroVector, Scale));
			}
			UBoxComponent* B = NewObject<UBoxComponent>(this, *FString::Printf(TEXT("LeafBox%d"), Side));
			B->SetupAttachment(GetRootComponent());
			B->SetMobility(EComponentMobility::Movable);
			B->SetBoxExtent(FVector(Spec.DoorLeaf * 0.5f, HalfW, Op.Height * 0.5f), false);
			B->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
			B->SetCollisionObjectType(ECC_WorldDynamic);
			B->SetCollisionResponseToAllChannels(ECR_Block);
			B->SetGenerateOverlapEvents(false);
			B->SetCanEverAffectNavigation(false);
			B->SetHiddenInGame(true);
			B->RegisterComponent();
			LeafBox.Add(B);
		}
	}
	BuildLooks();
	SetOpen(0.f);
}

void AAstraLiftLanding::BuildLooks()
{
	if (UStaticMesh* F = AstraLiftKit::Mesh(FString::Printf(TEXT("SM_LIFT_Landing_%s"), *Spec.Suffix)))
	{
		Frame = LiftMakeMesh(this, GetRootComponent(), TEXT("Frame"), F, FVector::ZeroVector, FVector::OneVector);
	}
	else if (UStaticMesh* C = AstraLiftKit::Cube(); C && bDoors)
	{
		// the kit is not imported: a plain frame round the opening so that the landing is a place
		const FAstraLiftSpec::FOpening& Op = Spec.Openings[0];
		LiftMakeMesh(this, GetRootComponent(), TEXT("JambL"), C, FVector(4.f, -(Op.Width * 0.5f + 6.f), Op.Height * 0.5f), FVector(0.1f, 0.12f, Op.Height / 100.f));
		LiftMakeMesh(this, GetRootComponent(), TEXT("JambR"), C, FVector(4.f, Op.Width * 0.5f + 6.f, Op.Height * 0.5f), FVector(0.1f, 0.12f, Op.Height / 100.f));
		LiftMakeMesh(this, GetRootComponent(), TEXT("Head"), C, FVector(4.f, 0.f, Op.Height + 6.f), FVector(0.1f, Op.Width / 100.f + 0.24f, 0.12f));
	}
	// the call panel's lamp: lit while a car is on its way
	UStaticMesh* LampMesh = AstraLiftKit::Mesh(TEXT("SM_LIFT_CallLamp"));
	if (!LampMesh)
	{
		LampMesh = AstraLiftKit::Cube();
	}
	if (LampMesh)
	{
		Lamp = LiftMakeMesh(this, GetRootComponent(), TEXT("CallLamp"), LampMesh, PanelLocal + FVector(2.f, 0.f, 6.f), AstraLiftKit::Mesh(TEXT("SM_LIFT_CallLamp")) ? FVector::OneVector : FVector(0.02f, 0.06f, 0.06f));
		Lamp->SetVisibility(false);
		Lamp->SetCastShadow(false);
	}
	if (!bDoors)
	{
		// the shuttle's call post: a slim pillar on the platform with the lamp on it (the car has its own doors; the platform has none)
		if (UStaticMesh* Post = AstraLiftKit::Mesh(TEXT("SM_LIFT_CallPost")))
		{
			Frame = LiftMakeMesh(this, GetRootComponent(), TEXT("Post"), Post, FVector(PanelLocal.X, PanelLocal.Y, 0.f), FVector::OneVector);
		}
		else if (UStaticMesh* C = AstraLiftKit::Cube())
		{
			LiftMakeMesh(this, GetRootComponent(), TEXT("Post"), C, FVector(PanelLocal.X, PanelLocal.Y, 60.f), FVector(0.12f, 0.12f, 1.2f));
		}
	}
}

void AAstraLiftLanding::SetOpen(float Alpha)
{
	OpenNow = FMath::Clamp(Alpha, 0.f, 1.f);
	if (!bDoors)
	{
		return;
	}
	const FAstraLiftSpec::FOpening& Op = Spec.Openings[0];
	const float Ease = FMath::SmoothStep(0.f, 1.f, OpenNow);
	const float Closed = Op.Width * 0.25f - 1.f;
	for (int32 Side = 0; Side < 2; ++Side)
	{
		const FVector At(3.5f, (Side ? 1.f : -1.f) * (Closed + Op.Width * 0.5f * Ease), Op.Height * 0.5f);
		if (LeafMesh.IsValidIndex(Side) && LeafMesh[Side])
		{
			LeafMesh[Side]->SetRelativeLocation(At);
		}
		if (LeafBox.IsValidIndex(Side) && LeafBox[Side])
		{
			LeafBox[Side]->SetRelativeLocation(At);
		}
	}
}

void AAstraLiftLanding::SetCalled(bool bOn)
{
	bCalled = bOn;
	if (Lamp)
	{
		Lamp->SetVisibility(bOn);
	}
}

FVector AAstraLiftLanding::PanelCm() const
{
	return GetActorTransform().TransformPosition(PanelLocal);
}

bool AAstraLiftLanding::InDoorway(const FVector& World, float Margin) const
{
	const FVector L = GetActorTransform().InverseTransformPosition(World);
	const FAstraLiftSpec::FOpening& Op = Spec.Openings[0];
	return FMath::Abs(L.Y) < Op.Width * 0.5f + Margin && L.X > -60.f && L.X < 80.f && L.Z > -20.f && L.Z < Op.Height;
}

bool AAstraLiftLanding::Reaches(const FVector& Feet, float RangeCm) const
{
	const FVector P = PanelCm();
	const FVector L = GetActorTransform().InverseTransformPosition(Feet);
	return FVector::Dist2D(Feet, P) < RangeCm && FMath::Abs(Feet.Z - GetActorLocation().Z) < 120.f && L.X > -20.f;
}

// ============================================================================================================================== shaft

AAstraLiftShaft::AAstraLiftShaft()
{
	PrimaryActorTick.bCanEverTick = false;
	SetRootComponent(CreateDefaultSubobject<USceneComponent>(TEXT("Root")));
}

void AAstraLiftShaft::Setup(const FAstraLiftLine& L, const FAstraLiftSpec& S)
{
	const FString Suf = S.Suffix;
	UStaticMesh* PlainMesh = AstraLiftKit::Mesh(FString::Printf(TEXT("SM_LIFT_Shaft_%s"), *Suf));
	UStaticMesh* DoorMesh = AstraLiftKit::Mesh(FString::Printf(TEXT("SM_LIFT_ShaftDoor_%s"), *Suf));
	if (!PlainMesh || !DoorMesh || L.bShuttle)
	{
		return;                                // the kit is not imported (or this is the shuttle's line: its tunnel is the ship's): no shaft to show
	}
	auto Make = [this](const TCHAR* Name, UStaticMesh* M)
	{
		UInstancedStaticMeshComponent* C = NewObject<UInstancedStaticMeshComponent>(this, Name);
		C->SetupAttachment(GetRootComponent());
		C->SetMobility(EComponentMobility::Static);
		C->SetStaticMesh(M);
		C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		C->SetCanEverAffectNavigation(false);
		C->SetGenerateOverlapEvents(false);
		C->bAffectDynamicIndirectLighting = false;
		C->RegisterComponent();
		return C;
	};
	Seg = Make(TEXT("Segments"), PlainMesh);
	Door = Make(TEXT("DoorSegments"), DoorMesh);
	const FRotator Yaw(0.f, L.FrontYaw, 0.f);
	const FVector XY(L.ShaftCm.X, L.ShaftCm.Y, 0.f);
	// from a metre under the lowest landing to the car's height over the highest and a metre of headroom, filled with the door segments at each landing and plain
	// segments between them (a gap that is not a whole number of segments is made up by stretching the last)
	const float Bottom = L.ZBottom - 100.f;
	const float Top = L.ZTop + S.H + S.CeilT + S.FloorT + 100.f;
	float Z = Bottom;
	auto Fill = [&](float To)
	{
		while (To - Z > 1.f)
		{
			const float H = FMath::Min(LiftSegH, To - Z);
			Seg->AddInstance(FTransform(Yaw, XY + FVector(0.f, 0.f, Z), FVector(1.f, 1.f, H / LiftSegH)));
			Z += H;
			++Segments;
		}
	};
	for (const FAstraLiftStop& Stop : L.Stops)
	{
		const float Start = Stop.FloorZ - LiftDoorSegDown;
		Fill(Start);
		Door->AddInstance(FTransform(Yaw, XY + FVector(0.f, 0.f, Start)));
		Z = Start + LiftDoorSegH;
		++Segments;
	}
	Fill(Top);
}
