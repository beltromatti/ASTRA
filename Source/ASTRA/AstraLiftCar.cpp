// ASTRA — a lift car (see AstraLiftCar.h).

#include "AstraLiftCar.h"

#include "ASTRA.h"
#include "AstraLiftSubsystem.h"
#include "Components/AudioComponent.h"
#include "Components/BoxComponent.h"
#include "Components/PointLightComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "GameFramework/Pawn.h"
#include "Kismet/GameplayStatics.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Sound/SoundBase.h"

DECLARE_CYCLE_STAT(TEXT("Car tick"), STAT_AstraLiftCar, STATGROUP_AstraLifts);

namespace
{
	UStaticMesh* LiftKitMesh(const FString& Name)
	{
		return LoadObject<UStaticMesh>(nullptr, *FString::Printf(TEXT("/Game/ASTRA/Kit/Lift/%s.%s"), *Name, *Name), nullptr, LOAD_NoWarn | LOAD_Quiet);
	}

	USoundBase* LiftSound(const TCHAR* Name)
	{
		return LoadObject<USoundBase>(nullptr, *FString::Printf(TEXT("/Game/ASTRA/Audio/%s.%s"), Name, Name), nullptr, LOAD_NoWarn | LOAD_Quiet);
	}

	UStaticMesh* LiftCube()
	{
		return LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/LiftCube.LiftCube"), nullptr, LOAD_NoWarn | LOAD_Quiet);
	}
}

// ================================================================================================================================ spec

FAstraLiftSpec FAstraLiftSpec::Make(const FAstraLiftLine& L)
{
	FAstraLiftSpec S;
	S.W = L.CarW - 2.f * S.WallT;
	S.D = L.CarD - 2.f * S.WallT;
	S.H = L.CarH;
	// the doors: a pair of leaves that slide into the piers each side of the opening, so the opening is at most half the car's width
	float OpW = 120.f, OpH = 220.f;
	switch (L.Kind)
	{
	case EAstraLiftKind::Service:  OpW = 140.f; OpH = 230.f; S.Suffix = TEXT("sv"); break;
	case EAstraLiftKind::Cargo:    OpW = 180.f; OpH = 260.f; S.Suffix = TEXT("cg"); break;
	case EAstraLiftKind::Shuttle:  OpW = 130.f; OpH = 210.f; S.Suffix = TEXT("sh"); break;
	default:                       S.Suffix = TEXT("tl"); break;
	}
	OpW = FMath::Min(OpW, L.CarW * 0.5f - 2.f);
	OpH = FMath::Min(OpH, S.H - 30.f);
	if (L.bShuttle)
	{
		for (const float Y : {-350.f, 0.f, 350.f})
		{
			S.Openings.Add({Y, OpW, OpH});
		}
		S.ScreenCenter = FVector(-S.D * 0.5f + 4.f, 0.f, 165.f);
		S.ScreenYaw = 0.f;
		S.ScreenSize = FVector2D(140.0, 88.0);
	}
	else
	{
		S.Openings.Add({0.f, OpW, OpH});
		// by the door, on the wall to the right of whoever comes in
		const bool bBig = L.Kind == EAstraLiftKind::Service || L.Kind == EAstraLiftKind::Cargo;
		S.ScreenSize = bBig ? FVector2D(100.0, 62.5) : FVector2D(80.0, 50.0);
		S.ScreenCenter = FVector(S.D * 0.5f - 70.f, -S.W * 0.5f + 3.f, 150.f);
		S.ScreenYaw = 90.f;
	}
	return S;
}

// ================================================================================================================================ car

AAstraLiftCar::AAstraLiftCar()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.bStartWithTickEnabled = false;
	PrimaryActorTick.TickGroup = TG_PrePhysics;          // before the Captain's movement: he is carried by where the car has got to this frame
	SetRootComponent(CreateDefaultSubobject<USceneComponent>(TEXT("Root")));
	GetRootComponent()->SetMobility(EComponentMobility::Movable);
	SetCanBeDamaged(false);
}

UPrimitiveComponent* AAstraLiftCar::FloorComponent() const
{
	return Floor;
}

UBoxComponent* AAstraLiftCar::AddBox(const FName& Name, const FVector& Center, const FVector& Extent)
{
	UBoxComponent* B = NewObject<UBoxComponent>(this, Name);
	B->SetupAttachment(GetRootComponent());
	B->SetMobility(EComponentMobility::Movable);
	B->SetRelativeLocation(Center);
	B->SetBoxExtent(Extent, false);
	B->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
	B->SetCollisionObjectType(ECC_WorldDynamic);
	B->SetCollisionResponseToAllChannels(ECR_Block);
	B->SetGenerateOverlapEvents(false);
	B->SetCanEverAffectNavigation(false);
	B->SetHiddenInGame(true);
	B->bAffectDistanceFieldLighting = false;
	B->RegisterComponent();
	return B;
}

UStaticMeshComponent* AAstraLiftCar::AddMesh(const FName& Name, UStaticMesh* Mesh, const FVector& Rel, const FVector& Scale)
{
	UStaticMeshComponent* M = NewObject<UStaticMeshComponent>(this, Name);
	M->SetupAttachment(GetRootComponent());
	M->SetMobility(EComponentMobility::Movable);
	M->SetStaticMesh(Mesh);
	M->SetRelativeLocation(Rel);
	M->SetRelativeScale3D(Scale);
	M->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	M->SetCanEverAffectNavigation(false);
	M->SetGenerateOverlapEvents(false);
	// a moving mesh must not feed the global illumination (the surface cache of a thing that moves at eight metres a second is a cost for nothing)
	M->bAffectDynamicIndirectLighting = false;
	M->bAffectDistanceFieldLighting = false;
	M->RegisterComponent();
	return M;
}

void AAstraLiftCar::Setup(UAstraLiftSubsystem* InOwner, int32 InLine, const FAstraLiftLine& InData, int32 StartStop)
{
	Owner = InOwner;
	Line = InLine;
	Data = InData;
	CarSpec = FAstraLiftSpec::Make(Data);
	SetActorRotation(FRotator(0.f, Data.FrontYaw, 0.f));
	SetActorLocation(Data.Path.At(Data.Stops[StartStop].S), false, nullptr, ETeleportType::TeleportPhysics);
	LastLocation = GetActorLocation();
	BuildShell();
	BuildLooks();

	// the brain: the stops along the path, the line's speed, and the world as the subsystem answers for it
	TArray<float> S;
	for (const FAstraLiftStop& Stop : Data.Stops)
	{
		S.Add(Stop.S);
	}
	FAstraLiftBrain::FConfig Cfg;
	Cfg.VmaxCmS = Data.SpeedCmS;
	Cfg.AccelCmS2 = Data.AccelCmS2;
	Brain.Init(S, StartStop, Cfg, InOwner ? InOwner->MakeHooks(InLine) : FAstraLiftBrain::FHooks());
	SetActorTickEnabled(false);
}

void AAstraLiftCar::BuildShell()
{
	const FAstraLiftSpec& S = CarSpec;
	const float Z0 = Data.CarFloor;                       // the floor's top over the origin (the shuttle's low step)
	const float OW = S.W + 2.f * S.WallT, OD = S.D + 2.f * S.WallT;
	// floor and ceiling, the back (-X) and the sides
	Floor = AddBox(TEXT("Floor"), FVector(0.f, 0.f, Z0 - S.FloorT * 0.5f), FVector(OD * 0.5f, OW * 0.5f, S.FloorT * 0.5f));
	Walls.Add(AddBox(TEXT("Ceiling"), FVector(0.f, 0.f, Z0 + S.H + S.CeilT * 0.5f), FVector(OD * 0.5f, OW * 0.5f, S.CeilT * 0.5f)));
	Walls.Add(AddBox(TEXT("Back"), FVector(-S.D * 0.5f - S.WallT * 0.5f, 0.f, Z0 + S.H * 0.5f), FVector(S.WallT * 0.5f, OW * 0.5f, S.H * 0.5f)));
	Walls.Add(AddBox(TEXT("SideL"), FVector(0.f, -S.W * 0.5f - S.WallT * 0.5f, Z0 + S.H * 0.5f), FVector(S.D * 0.5f, S.WallT * 0.5f, S.H * 0.5f)));
	Walls.Add(AddBox(TEXT("SideR"), FVector(0.f, S.W * 0.5f + S.WallT * 0.5f, Z0 + S.H * 0.5f), FVector(S.D * 0.5f, S.WallT * 0.5f, S.H * 0.5f)));
	// the front wall (+X): the piers between the openings, and the header over each
	TArray<FAstraLiftSpec::FOpening> Ops = S.Openings;
	Ops.Sort([](const FAstraLiftSpec::FOpening& A, const FAstraLiftSpec::FOpening& B) { return A.Y < B.Y; });
	const float FX = S.D * 0.5f + S.WallT * 0.5f;
	float Cursor = -OW * 0.5f;
	int32 K = 0;
	auto Pier = [&](float Y0, float Y1)
	{
		if (Y1 - Y0 > 1.f)
		{
			Walls.Add(AddBox(*FString::Printf(TEXT("Pier%d"), K++), FVector(FX, (Y0 + Y1) * 0.5f, Z0 + S.H * 0.5f), FVector(S.WallT * 0.5f, (Y1 - Y0) * 0.5f, S.H * 0.5f)));
		}
	};
	for (const FAstraLiftSpec::FOpening& O : Ops)
	{
		Pier(Cursor, O.Y - O.Width * 0.5f);
		const float Hh = S.H - O.Height;
		if (Hh > 1.f)
		{
			Walls.Add(AddBox(*FString::Printf(TEXT("Header%d"), K++), FVector(FX, O.Y, Z0 + O.Height + Hh * 0.5f), FVector(S.WallT * 0.5f, O.Width * 0.5f, Hh * 0.5f)));
		}
		Cursor = O.Y + O.Width * 0.5f;
	}
	Pier(Cursor, OW * 0.5f);
	// the leaves: a pair for each opening (the visible leaf and its collision move together)
	UStaticMesh* LeafKit = LiftKitMesh(FString::Printf(TEXT("SM_LIFT_CarLeaf_%s"), *S.Suffix));
	UStaticMesh* CubeMesh = LiftCube();
	for (int32 I = 0; I < Ops.Num(); ++I)
	{
		for (int32 Side = 0; Side < 2; ++Side)
		{
			const float HalfW = Ops[I].Width * 0.25f + 1.f;
			UStaticMeshComponent* M = AddMesh(*FString::Printf(TEXT("Leaf%d_%d"), I, Side), LeafKit ? LeafKit : CubeMesh, FVector::ZeroVector,
			                                  LeafKit ? FVector(1.f, Side ? 1.f : -1.f, 1.f) : FVector(S.DoorLeaf / 100.f, HalfW * 2.f / 100.f, Ops[I].Height / 100.f));
			M->SetCastShadow(false);
			LeafMesh.Add(M);
			// (the collision is its own box on the car, moved with the leaf: a child of the leaf would inherit the leaf's scale)
			LeafBox.Add(AddBox(*FString::Printf(TEXT("LeafBox%d_%d"), I, Side), FVector::ZeroVector, FVector(S.DoorLeaf * 0.5f, HalfW, Ops[I].Height * 0.5f)));
		}
	}
	ApplyDoors(0.f);
	// where the passengers stand: the back of the car first, the doors' lane kept clear
	const float Lane = S.D * 0.5f - 85.f;
	TArray<FVector> Grid;
	const float StepX = Data.bShuttle ? 70.f : 55.f, StepY = Data.bShuttle ? 85.f : 55.f;
	for (float X = -S.D * 0.5f + 45.f; X <= Lane; X += StepX)
	{
		for (float Y = -S.W * 0.5f + 45.f; Y <= S.W * 0.5f - 45.f; Y += StepY)
		{
			Grid.Add(FVector(X, Y, Z0));
		}
	}
	Grid.Sort([](const FVector& A, const FVector& B) { return A.X != B.X ? A.X < B.X : FMath::Abs(A.Y) < FMath::Abs(B.Y); });
	Slots = Grid;
}

void AAstraLiftCar::BuildLooks()
{
	const FAstraLiftSpec& S = CarSpec;
	const float Z0 = Data.CarFloor;
	const FString Suf = S.Suffix;
	UStaticMesh* Cabin = LiftKitMesh(FString::Printf(TEXT("SM_LIFT_Car_%s"), *Suf));
	if (Cabin)
	{
		Hull = AddMesh(TEXT("Hull"), Cabin, FVector(0.f, 0.f, Z0), FVector::OneVector);
		if (UStaticMesh* G = LiftKitMesh(FString::Printf(TEXT("SM_LIFT_CarGlass_%s"), *Suf)))
		{
			Glass = AddMesh(TEXT("Glass"), G, FVector(0.f, 0.f, Z0), FVector::OneVector);
			Glass->SetCastShadow(false);
		}
	}
	else if (UStaticMesh* C = LiftCube())
	{
		// the kit is not imported: the shell's boxes as they are, so the car is something to ride
		auto Plain = [&](UBoxComponent* B)
		{
			const FVector E = B->GetUnscaledBoxExtent();
			UStaticMeshComponent* M = AddMesh(*(B->GetName() + TEXT("_Look")), C, B->GetRelativeLocation(), E * 2.f / 100.f);
			M->SetCastShadow(false);
		};
		Plain(Floor);
		for (UBoxComponent* W : Walls)
		{
			Plain(W);
		}
	}
	// the screen: the kit's quad (1 m square, facing +X, u to the viewer's right, v up) scaled to the screen's size and turned to face into the car; the
	// lift subsystem paints it. Without the kit, the engine's plane stands in for it (its picture may come out turned: the kit is the one that is right)
	const FVector ScreenAt = S.ScreenCenter + FVector(0.f, 0.f, Z0);
	if (UStaticMesh* Quad = LiftKitMesh(TEXT("SM_LIFT_Screen")))
	{
		Screen = AddMesh(TEXT("Screen"), Quad, ScreenAt, FVector(1.0, S.ScreenSize.X / 100.0, S.ScreenSize.Y / 100.0));
		Screen->SetRelativeRotation(FRotator(0.f, S.ScreenYaw, 0.f));
	}
	else if (UStaticMesh* Plane = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Plane.Plane"), nullptr, LOAD_NoWarn | LOAD_Quiet))
	{
		Screen = AddMesh(TEXT("Screen"), Plane, ScreenAt, FVector(S.ScreenSize.Y / 100.0, S.ScreenSize.X / 100.0, 1.0));
		Screen->SetRelativeRotation(FRotator(-90.f, S.ScreenYaw, 0.f));
	}
	if (Screen)
	{
		Screen->SetCastShadow(false);
	}
	// the cabin's own light: a lift lights itself (the deck's lamps do not reach into the shaft)
	Lamp = NewObject<UPointLightComponent>(this, TEXT("Lamp"));
	Lamp->SetupAttachment(GetRootComponent());
	Lamp->SetMobility(EComponentMobility::Movable);
	Lamp->SetRelativeLocation(FVector(0.f, 0.f, Z0 + S.H - 25.f));
	Lamp->SetIntensityUnits(ELightUnits::Lumens);
	Lamp->SetIntensity(Data.bShuttle ? 4200.f : 1500.f);
	Lamp->SetAttenuationRadius(Data.bShuttle ? 900.f : 520.f);
	Lamp->SetSourceRadius(30.f);
	Lamp->SetLightColor(FLinearColor(0.82f, 0.9f, 1.f));
	Lamp->SetCastShadows(false);
	Lamp->SetVisibility(false);
	Lamp->RegisterComponent();
	// the sounds
	SndThump = LiftSound(TEXT("SW_Lift_Thump"));
	SndChime = LiftSound(TEXT("SW_Lift_Chime"));
	SndDoor = LiftSound(TEXT("SW_Door_Open"));
	SndDoorShut = LiftSound(TEXT("SW_Door_Close"));
	if (USoundBase* HumSound = LiftSound(TEXT("SW_Lift_Hum")))
	{
		Hum = NewObject<UAudioComponent>(this, TEXT("Hum"));
		Hum->SetupAttachment(GetRootComponent());
		Hum->SetSound(HumSound);
		Hum->bAutoActivate = false;
		Hum->bAllowSpatialization = true;
		Hum->bOverrideAttenuation = true;
		Hum->AttenuationOverrides.bAttenuate = true;
		Hum->AttenuationOverrides.bSpatialize = true;
		Hum->AttenuationOverrides.AttenuationShapeExtents = FVector(250.f);
		Hum->AttenuationOverrides.FalloffDistance = 2200.f;
		Hum->RegisterComponent();
	}
}

void AAstraLiftCar::SetLandings(const TArray<AAstraLiftLanding*>& InLandings)
{
	Landings.Reset();
	for (AAstraLiftLanding* L : InLandings)
	{
		Landings.Add(L);
	}
}

void AAstraLiftCar::ApplyDoors(float Open)
{
	const float Z0 = Data.CarFloor;
	const FAstraLiftSpec& S = CarSpec;
	TArray<FAstraLiftSpec::FOpening> Ops = S.Openings;
	Ops.Sort([](const FAstraLiftSpec::FOpening& A, const FAstraLiftSpec::FOpening& B) { return A.Y < B.Y; });
	const float Ease = FMath::SmoothStep(0.f, 1.f, Open);
	const float X = S.D * 0.5f + S.WallT * 0.5f;
	for (int32 I = 0; I < Ops.Num(); ++I)
	{
		const FAstraLiftSpec::FOpening& O = Ops[I];
		const float Closed = O.Width * 0.25f - 1.f;                    // each leaf's middle when shut: a quarter of the opening from its middle, a hand's width of overlap
		const float Travel = O.Width * 0.5f * Ease;
		for (int32 Side = 0; Side < 2; ++Side)
		{
			const int32 Index = I * 2 + Side;
			const FVector At(X, O.Y + (Side ? 1.f : -1.f) * (Closed + Travel), Z0 + O.Height * 0.5f);
			if (LeafMesh.IsValidIndex(Index) && LeafMesh[Index])
			{
				LeafMesh[Index]->SetRelativeLocation(At);
			}
			if (LeafBox.IsValidIndex(Index) && LeafBox[Index])
			{
				LeafBox[Index]->SetRelativeLocation(At);
			}
		}
	}
}

bool AAstraLiftCar::Contains(const FVector& World, float Margin) const
{
	const FVector L = ToLocal(World);
	const float Z0 = Data.CarFloor;
	return FMath::Abs(L.X) < CarSpec.D * 0.5f - Margin && FMath::Abs(L.Y) < CarSpec.W * 0.5f - Margin && L.Z > Z0 - 30.f && L.Z < Z0 + CarSpec.H;
}

int32 AAstraLiftCar::CurrentStop() const
{
	return Brain.AtLanding() != INDEX_NONE ? Brain.AtLanding() : Data.StopBelow(Brain.S());
}

FVector AAstraLiftCar::SlotLocal(int32 Slot) const
{
	return Slots.IsValidIndex(Slot) ? Slots[Slot] : FVector(0.f, 0.f, Data.CarFloor);
}

void AAstraLiftCar::Wake()
{
	SetActorTickEnabled(true);
}

void AAstraLiftCar::SetNear(bool bNear)
{
	if (bNear == bNearNow)
	{
		return;
	}
	bNearNow = bNear;
	if (Lamp && !bQuiet)
	{
		Lamp->SetVisibility(bNear);
	}
	if (!bNear && Hum && Hum->IsPlaying())
	{
		Hum->FadeOut(0.5f, 0.f);
		bHumOn = false;
	}
}

void AAstraLiftCar::SetScreenTexture(UTexture* Texture)
{
	if (!Screen || !Texture)
	{
		return;
	}
	if (!ScreenMat)
	{
		// the lift's screen material (an instance of the project's screen master: art/blender/ship_lift.py names the slot, build_lifts.py makes it), else the master
		UMaterialInterface* Base = Screen->GetMaterial(0);
		if (!Base || Base->GetName() == TEXT("WorldGridMaterial"))
		{
			Base = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/ASTRA/Materials/Instances/MI_LIFT_Screen.MI_LIFT_Screen"), nullptr, LOAD_NoWarn | LOAD_Quiet);
			if (!Base)
			{
				Base = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/ASTRA/Materials/M_ASTRA_Screen.M_ASTRA_Screen"), nullptr, LOAD_NoWarn | LOAD_Quiet);
			}
		}
		if (!Base)
		{
			return;
		}
		ScreenMat = UMaterialInstanceDynamic::Create(Base, this);
		Screen->SetMaterial(0, ScreenMat);
	}
	ScreenMat->SetTextureParameterValue(TEXT("ScreenTexture"), Texture);
}

void AAstraLiftCar::Thump(float Volume)
{
	if (!bQuiet && SndThump)
	{
		UGameplayStatics::PlaySoundAtLocation(this, SndThump, GetActorLocation() + FVector(0.f, 0.f, 80.f), Volume, FMath::FRandRange(0.97f, 1.03f));
	}
}

void AAstraLiftCar::ApplyBrain(float Dt)
{
	const FVector P = Data.Path.At(Brain.S());
	// a car that nobody is near (the Captain far from it, the car between landings) moves its body a few times a second: its time is the brain's and exact, and
	// the body is where it should be as soon as it stops or anyone comes near; twelve cars on the move at once cost the frame a third of what they do at full rate
	const double Now = GetWorld() ? GetWorld()->GetTimeSeconds() : 0.0;
	const bool bCoarse = !bNearNow && Brain.AtLanding() == INDEX_NONE && Now - LastMoveAt < 0.25;
	if (!bCoarse && !P.Equals(LastLocation, 0.005f))
	{
		LastMoveAt = Now;
		// carried: the Captain's feet and the crew's bodies move with it (their movement reads this component as their base)
		SetActorLocation(P, false, nullptr, ETeleportType::None);
		LastLocation = P;
	}
	const FVector Vel = Data.Path.Tangent(Brain.S()) * Brain.V();
	if (Floor && !Floor->ComponentVelocity.Equals(Vel, 0.5f))
	{
		Floor->ComponentVelocity = Vel;
		for (UBoxComponent* W : Walls)
		{
			W->ComponentVelocity = Vel;
		}
	}
	const float Door = Brain.DoorOpen();
	const int32 At = Brain.AtLanding();
	if (Door != LastDoor || At != LastLandingOpen)
	{
		if (Door != LastDoor)
		{
			ApplyDoors(Door);
		}
		// the landing's doors move with the car's: the one it stands at; the last one it opened is shut again
		if (LastLandingOpen != INDEX_NONE && LastLandingOpen != At && Landings.IsValidIndex(LastLandingOpen) && Landings[LastLandingOpen].IsValid())
		{
			Landings[LastLandingOpen]->SetOpen(0.f);
		}
		if (At != INDEX_NONE && Landings.IsValidIndex(At) && Landings[At].IsValid())
		{
			Landings[At]->SetOpen(Door);
		}
		LastDoor = Door;
		LastLandingOpen = At != INDEX_NONE ? At : LastLandingOpen;
	}
}

void AAstraLiftCar::DrainEvents()
{
	TArray<FAstraLiftEvent>& Events = Brain.Events();
	for (const FAstraLiftEvent& E : Events)
	{
		switch (E.Type)
		{
		case FAstraLiftEvent::EType::Depart:
			Thump(0.55f);
			break;
		case FAstraLiftEvent::EType::Arrive:
			Thump(0.4f);
			break;
		case FAstraLiftEvent::EType::DoorsOpening:
			if (!bQuiet)
			{
				if (SndChime)
				{
					UGameplayStatics::PlaySoundAtLocation(this, SndChime, GetActorLocation() + FVector(0.f, 0.f, 200.f), 0.5f);
				}
				if (SndDoor)
				{
					UGameplayStatics::PlaySoundAtLocation(this, SndDoor, GetActorLocation() + CarSpec.D * 0.5f * Data.Front + FVector(0.f, 0.f, 120.f), 0.6f, FMath::FRandRange(0.96f, 1.04f));
				}
			}
			if (Landings.IsValidIndex(E.Landing) && Landings[E.Landing].IsValid())
			{
				Landings[E.Landing]->SetCalled(false);
			}
			break;
		case FAstraLiftEvent::EType::DoorsClosing:
			if (!bQuiet && SndDoorShut)
			{
				UGameplayStatics::PlaySoundAtLocation(this, SndDoorShut, GetActorLocation() + CarSpec.D * 0.5f * Data.Front + FVector(0.f, 0.f, 120.f), 0.5f, FMath::FRandRange(0.96f, 1.04f));
			}
			break;
		default:
			break;
		}
		if (UAstraLiftSubsystem* O = Owner.Get())
		{
			O->OnCarEvent(Line, E);
		}
	}
	Events.Reset();
}

void AAstraLiftCar::UpdateHum()
{
	if (!Hum)
	{
		return;
	}
	const float Speed = FMath::Abs(Brain.V()) / FMath::Max(1.f, Data.SpeedCmS);
	if (Speed > 0.01f && !bQuiet)
	{
		Hum->SetVolumeMultiplier(FMath::Lerp(0.18f, 0.85f, FMath::Min(1.f, Speed)));
		Hum->SetPitchMultiplier(FMath::Lerp(0.72f, 1.5f, FMath::Min(1.f, Speed)));
		if (!Hum->IsPlaying())
		{
			Hum->FadeIn(0.4f);
		}
		bHumOn = true;
	}
	else if (bHumOn)
	{
		Hum->FadeOut(0.6f, 0.f);
		bHumOn = false;
	}
}

void AAstraLiftCar::Tick(float DeltaTime)
{
	SCOPE_CYCLE_COUNTER(STAT_AstraLiftCar);
	Super::Tick(DeltaTime);
	Brain.Tick(FMath::Min(DeltaTime, 0.25f));
	ApplyBrain(DeltaTime);
	DrainEvents();
	UpdateHum();
	if (Brain.Quiet())
	{
		SetActorTickEnabled(false);                 // nothing moves and nothing is asked: a parked car costs nothing
	}
}

void AAstraLiftCar::EndPlay(const EEndPlayReason::Type Reason)
{
	if (Hum)
	{
		Hum->Stop();
	}
	Super::EndPlay(Reason);
}
