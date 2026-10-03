#include "AstraBoardInterior.h"

#include "ASTRA.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Components/PointLightComponent.h"
#include "Components/SceneComponent.h"
#include "Components/SpotLightComponent.h"
#include "Engine/CollisionProfile.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
#include "Misc/App.h"

using namespace AstraBoardInterior;

namespace
{
	/** A portal on one of a room's four faces (the face's plane is Plane along X when bXFace, else along Y; Sign: which way the face looks out of the room). */
	bool IbOnFace(const FBoardPortal& P, int32 Comp, bool bXFace, double Plane, double Sign)
	{
		const double N = bXFace ? P.Normal.X : P.Normal.Y;
		if (FMath::Abs(N) < 0.7)
		{
			return false;
		}
		const double Pos = bXFace ? P.Pos.X : P.Pos.Y;
		if (FMath::Abs(Pos - Plane) > 90.0)
		{
			return false;
		}
		// the portal's normal runs from its first room to its second: leaving this room through this face means the normal points the way the face looks (out of A) or the other way (out of B)
		return N * (P.A == Comp ? 1.0 : -1.0) * Sign > 0.5;
	}

	struct FIbOpening
	{
		double S0 = 0.0, S1 = 0.0, Top = 0.0;
		int32 Portal = INDEX_NONE;
		bool bFramed = false;
	};
}

void AstraBoardInterior::BuildComp(const FAstraBoardMap& Map, int32 Comp, TArray<FSlab>& Out)
{
	if (!Map.GetComps().IsValidIndex(Comp))
	{
		return;
	}
	const FBoardComp& C = Map.GetComps()[Comp];
	const FBox& B = C.Box;
	const FVector Mid = B.GetCenter();
	const double Sx = B.Max.X - B.Min.X, Sy = B.Max.Y - B.Min.Y, H = B.Max.Z - B.Min.Z;
	if (Sx < 60.0 || Sy < 60.0 || H < 120.0)
	{
		return;
	}
	const auto Add = [&](ESlab Kind, const FVector& Centre, const FVector& Half, int32 Door = INDEX_NONE)
	{
		FSlab S;
		S.Kind = Kind;
		S.Centre = Centre;
		S.Half = Half;
		S.Comp = Comp;
		S.Door = Door;
		Out.Add(S);
	};
	// the floor (its top is the room's floor: the soldiers' feet are there) and the ceiling
	Add(ESlab::Floor, FVector(Mid.X, Mid.Y, B.Min.Z - FloorCm * 0.5), FVector(Sx * 0.5, Sy * 0.5, FloorCm * 0.5));
	Add(ESlab::Ceiling, FVector(Mid.X, Mid.Y, B.Max.Z + CeilingCm * 0.5), FVector(Sx * 0.5, Sy * 0.5, CeilingCm * 0.5));
	// the walls, face by face: 0 +X, 1 -X, 2 +Y, 3 -Y
	for (int32 f = 0; f < 4; ++f)
	{
		const bool bX = f < 2;
		const double Sign = (f % 2 == 0) ? 1.0 : -1.0;
		const double Plane = bX ? (Sign > 0.0 ? B.Max.X : B.Min.X) : (Sign > 0.0 ? B.Max.Y : B.Min.Y);
		const double T0 = bX ? B.Min.Y : B.Min.X, T1 = bX ? B.Max.Y : B.Max.X;
		TArray<FIbOpening> Opens;
		for (const int32 Pi : C.Portals)
		{
			const FBoardPortal& P = Map.GetPortals()[Pi];
			if (P.bVertical() || !IbOnFace(P, Comp, bX, Plane, Sign))
			{
				continue;
			}
			FIbOpening O;
			O.Portal = Pi;
			const double Along = bX ? P.Pos.Y : P.Pos.X;
			O.S0 = Along - P.Half;
			O.S1 = Along + P.Half;
			if (P.Kind == FBoardPortal::EKind::Open)
			{
				// an open way: the whole stretch the two rooms share (a corridor going on is not a wall with a hole in it)
				const FBox& Other = Map.GetComps()[P.Other(Comp)].Box;
				const double A0 = FMath::Max(T0, bX ? Other.Min.Y : Other.Min.X), A1 = FMath::Min(T1, bX ? Other.Max.Y : Other.Max.X);
				if (A1 - A0 > 60.0)
				{
					O.S0 = A0;
					O.S1 = A1;
				}
				O.Top = H;
			}
			else
			{
				O.Top = FMath::Min<double>(P.Kind == FBoardPortal::EKind::Blast ? BlastHeightCm : DoorHeightCm, H - 10.0);
				O.bFramed = true;
				// a door stands in the stretch the two rooms share: one that the plan puts at the edge of it (the end of a corridor's segment, a room that runs on past it) is moved in until the
				// whole gap is in front of both rooms (the same gap in both rooms' walls: nothing stands half in the way of a door)
				const FBox& Other = Map.GetComps()[P.Other(Comp)].Box;
				const double Lo = FMath::Max(T0, bX ? Other.Min.Y : Other.Min.X), Hi = FMath::Min(T1, bX ? Other.Max.Y : Other.Max.X);
				if (Hi - Lo > 60.0)
				{
					const double Half = FMath::Min<double>(P.Half, 0.5 * (Hi - Lo));
					const double Centre = FMath::Clamp(Along, Lo + Half, Hi - Half);
					O.S0 = Centre - Half;
					O.S1 = Centre + Half;
				}
			}
			O.S0 = FMath::Max(O.S0, T0 + 6.0);
			O.S1 = FMath::Min(O.S1, T1 - 6.0);
			if (O.S1 - O.S0 > 20.0)
			{
				Opens.Add(O);
			}
		}
		Opens.Sort([](const FIbOpening& A, const FIbOpening& B2) { return A.S0 < B2.S0; });
		// a wall stands inside the room's own box, its thickness in from the face's plane
		const auto Wall = [&](ESlab Kind, double S0, double S1, double Z0, double Z1, double Thick, int32 Door = INDEX_NONE)
		{
			const double L = S1 - S0, T = 0.5 * (S0 + S1), Zh = 0.5 * (Z1 - Z0), Zc = 0.5 * (Z0 + Z1);
			const double AxisCenter = Plane - Sign * Thick * 0.5;
			if (L < 4.0 || Zh < 2.0)
			{
				return;
			}
			Add(Kind, bX ? FVector(AxisCenter, T, Zc) : FVector(T, AxisCenter, Zc), bX ? FVector(Thick * 0.5, L * 0.5, Zh) : FVector(L * 0.5, Thick * 0.5, Zh), Door);
		};
		// the solid stretches between the openings
		double Cur = T0;
		for (const FIbOpening& O : Opens)
		{
			if (O.S0 > Cur + 4.0)
			{
				Wall(ESlab::Wall, Cur, O.S0, B.Min.Z, B.Max.Z, WallCm);
			}
			Cur = FMath::Max(Cur, O.S1);
		}
		if (T1 > Cur + 4.0)
		{
			Wall(ESlab::Wall, Cur, T1, B.Min.Z, B.Max.Z, WallCm);
		}
		// above the openings, the frames round the doors, the leaves of the pressure bulkheads
		for (const FIbOpening& O : Opens)
		{
			if (O.Top < H - 6.0)
			{
				Wall(ESlab::Wall, O.S0, O.S1, B.Min.Z + O.Top, B.Max.Z, WallCm);
			}
			if (O.bFramed)
			{
				Wall(ESlab::Frame, O.S0 - 10.0, O.S0, B.Min.Z, B.Min.Z + O.Top, WallCm + 6.f);
				Wall(ESlab::Frame, O.S1, O.S1 + 10.0, B.Min.Z, B.Min.Z + O.Top, WallCm + 6.f);
				const FBoardPortal& P = Map.GetPortals()[O.Portal];
				if (P.Kind == FBoardPortal::EKind::Blast && P.A == Comp && P.Door != INDEX_NONE)
				{
					Wall(ESlab::Leaf, O.S0, O.S1, B.Min.Z, B.Min.Z + O.Top, WallCm - 2.f, P.Door);
				}
			}
		}
	}
	// the light: a strip along a corridor's length, a panel in a room
	if (C.bCorridor)
	{
		const bool bLongX = Sx >= Sy;
		const double L = FMath::Max(40.0, (bLongX ? Sx : Sy) - 120.0);
		Add(ESlab::Strip, FVector(Mid.X, Mid.Y, B.Max.Z - 3.0), bLongX ? FVector(L * 0.5, 9.0, 2.0) : FVector(9.0, L * 0.5, 2.0));
	}
	else
	{
		Add(ESlab::Strip, FVector(Mid.X, Mid.Y, B.Max.Z - 3.0), FVector(FMath::Min(70.0, Sx * 0.3), FMath::Min(25.0, Sy * 0.3), 2.0));
	}
}

bool AstraBoardInterior::SegmentBlocked(const TArray<FSlab>& Slabs, const FVector& A, const FVector& B, const TSet<int32>* OpenDoors)
{
	const FVector Dir = B - A;
	for (const FSlab& S : Slabs)
	{
		if (S.Kind == ESlab::Floor || S.Kind == ESlab::Ceiling || S.Kind == ESlab::Strip)
		{
			continue;
		}
		if (S.Kind == ESlab::Leaf && OpenDoors && OpenDoors->Contains(S.Door))
		{
			continue;
		}
		// the slab, a hair smaller (a way along a wall's face is not a way through it)
		const FVector Lo = S.Centre - S.Half + FVector(1.5), Hi = S.Centre + S.Half - FVector(1.5);
		if (Hi.X <= Lo.X || Hi.Y <= Lo.Y || Hi.Z <= Lo.Z)
		{
			continue;
		}
		double T0 = 0.0, T1 = 1.0;
		bool bHit = true;
		for (int32 Axis = 0; Axis < 3 && bHit; ++Axis)
		{
			const double D = Dir[Axis];
			if (FMath::Abs(D) < 1.0e-9)
			{
				bHit = A[Axis] > Lo[Axis] && A[Axis] < Hi[Axis];
				continue;
			}
			double Ta = (Lo[Axis] - A[Axis]) / D, Tb = (Hi[Axis] - A[Axis]) / D;
			if (Ta > Tb)
			{
				Swap(Ta, Tb);
			}
			T0 = FMath::Max(T0, Ta);
			T1 = FMath::Min(T1, Tb);
			bHit = T0 < T1;
		}
		if (bHit)
		{
			return true;
		}
	}
	return false;
}

// ================================================================================================================== the actor

AAstraBoardInterior::AAstraBoardInterior()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.TickInterval = 0.25f;
	SetRootComponent(CreateDefaultSubobject<USceneComponent>(TEXT("Root")));
}

FVector AAstraBoardInterior::ZoneOrigin()
{
	return FVector(0.0, 0.0, -1.6e8);          // (the planet's zone is at -1e8: nobody is ever in both)
}

FVector AAstraBoardInterior::CabinOrigin()
{
	return FVector(0.0, 0.0, -1.7e8);
}

UInstancedStaticMeshComponent* AAstraBoardInterior::MakeIsm(const TCHAR* Name, UMaterialInterface* Mat)
{
	UInstancedStaticMeshComponent* C = NewObject<UInstancedStaticMeshComponent>(this, Name);
	C->SetupAttachment(GetRootComponent());
	C->SetStaticMesh(Cube);
	if (Mat)
	{
		C->SetMaterial(0, Mat);
	}
	C->SetMobility(EComponentMobility::Movable);
	C->SetCastShadow(false);
	C->RegisterComponent();
	return C;
}

void AAstraBoardInterior::Begin(TSharedPtr<FBoardShipPlan> InPlan, const FVector& InOffset, EAstraInteriorStyle InStyle)
{
	End();
	Plan = InPlan;
	Offset = InOffset;
	Style = InStyle;
	Cube = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cube.Cube"));
	const auto Mat = [](const TCHAR* Path) { return LoadObject<UMaterialInterface>(nullptr, Path); };
	UMaterialInterface* Structure = Mat(TEXT("/Game/ASTRA/Materials/Instances/MI_ASTRA_Structure.MI_ASTRA_Structure"));
	UMaterialInterface* Floor = Mat(TEXT("/Game/ASTRA/Materials/Instances/MI_ASTRA_Floor.MI_ASTRA_Floor"));
	UMaterialInterface* Trim = Mat(TEXT("/Game/ASTRA/Materials/Instances/MI_ASTRA_Trim.MI_ASTRA_Trim"));
	UMaterialInterface* Light = Mat(TEXT("/Game/ASTRA/Materials/Instances/MI_ASTRA_Light.MI_ASTRA_Light"));
	if (!Cube)
	{
		return;
	}
	Walls = MakeIsm(TEXT("Walls"), Structure);
	Floors = MakeIsm(TEXT("Floors"), Floor);
	Frames = MakeIsm(TEXT("Frames"), Trim);
	Leaves = MakeIsm(TEXT("Leaves"), Trim);
	if (Light)
	{
		StripMat = UMaterialInstanceDynamic::Create(Light, this);
		if (StripMat)
		{
			// a ship with power has her strips as the Aquila's; a hulk has the red of her emergency lighting, low
			StripMat->SetVectorParameterValue(TEXT("EmissiveColor"), Style == EAstraInteriorStyle::Lit ? FLinearColor(1.f, 0.95f, 0.88f) : FLinearColor(1.f, 0.16f, 0.07f));
			StripMat->SetScalarParameterValue(TEXT("Intensity"), Style == EAstraInteriorStyle::Lit ? 30.f : 9.f);
		}
	}
	Strips = MakeIsm(TEXT("Strips"), StripMat ? static_cast<UMaterialInterface*>(StripMat) : Light);
	for (UInstancedStaticMeshComponent* S : {Walls.Get(), Floors.Get(), Frames.Get(), Leaves.Get()})
	{
		S->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
		S->SetCollisionProfileName(UCollisionProfile::BlockAll_ProfileName);
	}
	Strips->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	// the lights that follow the Captain: a few points, and the lamp on his rifle in a hulk
	for (int32 i = 0; i < 6; ++i)
	{
		UPointLightComponent* L = NewObject<UPointLightComponent>(this, *FString::Printf(TEXT("Light%d"), i));
		L->SetupAttachment(GetRootComponent());
		L->SetMobility(EComponentMobility::Movable);
		L->SetIntensityUnits(ELightUnits::Lumens);
		L->SetIntensity(Style == EAstraInteriorStyle::Lit ? 2600.f : 700.f);
		L->SetLightColor(Style == EAstraInteriorStyle::Lit ? FLinearColor(1.f, 0.93f, 0.82f) : FLinearColor(1.f, 0.2f, 0.1f));
		L->SetAttenuationRadius(1100.f);
		L->SetCastShadows(false);
		L->SetVisibility(false);
		L->RegisterComponent();
		Lights.Add(L);
	}
	if (Style == EAstraInteriorStyle::Emergency)
	{
		Torch = NewObject<USpotLightComponent>(this, TEXT("Torch"));
		Torch->SetupAttachment(GetRootComponent());
		Torch->SetMobility(EComponentMobility::Movable);
		Torch->SetIntensityUnits(ELightUnits::Lumens);
		Torch->SetIntensity(4200.f);
		Torch->SetLightColor(FLinearColor(0.92f, 0.96f, 1.f));
		Torch->SetAttenuationRadius(3600.f);
		Torch->SetInnerConeAngle(10.f);
		Torch->SetOuterConeAngle(26.f);
		Torch->SetCastShadows(false);
		Torch->RegisterComponent();
	}
	SetActorLocation(FVector::ZeroVector);
	SetActorTickEnabled(true);
}

void AAstraBoardInterior::AddSlabs(const TArray<FSlab>& Slabs)
{
	TArray<FTransform> W, F, Fr, St;
	for (const FSlab& S : Slabs)
	{
		const FTransform Xf(FQuat::Identity, Offset + S.Centre, S.Half * 2.0 / 100.0);
		switch (S.Kind)
		{
		case ESlab::Wall: W.Add(Xf); break;
		case ESlab::Floor:
		case ESlab::Ceiling: F.Add(Xf); break;
		case ESlab::Frame: Fr.Add(Xf); break;
		case ESlab::Strip:
			St.Add(Xf);
			StripAt.Add(S.Centre);
			break;
		case ESlab::Leaf:
			if (Leaves)
			{
				// a leaf stands in its bulkhead while it is shut; open, it lies away under the deck (a body far from anyone)
				const bool bShut = ShutNow.Contains(S.Door);
				const FTransform Away(FQuat::Identity, Offset + S.Centre - FVector(0.0, 0.0, 6000.0), S.Half * 2.0 / 100.0);
				LeafHome.Add(S.Door, Xf);
				LeafInstance.Add(S.Door, Leaves->AddInstance(bShut ? Xf : Away, true));
				++NumInstances;
			}
			break;
		}
	}
	if (Walls && W.Num())
	{
		Walls->AddInstances(W, false, true);
	}
	if (Floors && F.Num())
	{
		Floors->AddInstances(F, false, true);
	}
	if (Frames && Fr.Num())
	{
		Frames->AddInstances(Fr, false, true);
	}
	if (Strips && St.Num())
	{
		Strips->AddInstances(St, false, true);
	}
	NumInstances += W.Num() + F.Num() + Fr.Num() + St.Num();
}

void AAstraBoardInterior::MakePads(int32 Comp)
{
	if (!Plan.IsValid() || !Plan->Map.IsValid())
	{
		return;
	}
	const FAstraBoardMap& Map = *Plan->Map;
	for (const int32 Pi : Map.GetComps()[Comp].Portals)
	{
		const FBoardPortal& P = Map.GetPortals()[Pi];
		if (!P.bVertical() || PadDone.Contains(Pi))
		{
			continue;
		}
		PadDone.Add(Pi);
		const bool bStair = P.Kind == FBoardPortal::EKind::Stair;
		const bool bUp = P.PosB.Z > P.Pos.Z;
		FPad A, B;
		A.Here = P.Pos;
		A.To = P.PosB;
		A.Comp = P.A;
		A.Text = FString::Printf(TEXT("%s %s"), bStair ? TEXT("STAIRS") : TEXT("LIFT"), bUp ? TEXT("UP") : TEXT("DOWN"));
		B.Here = P.PosB;
		B.To = P.Pos;
		B.Comp = P.B;
		B.Text = FString::Printf(TEXT("%s %s"), bStair ? TEXT("STAIRS") : TEXT("LIFT"), bUp ? TEXT("DOWN") : TEXT("UP"));
		Pads.Add(A);
		Pads.Add(B);
		// a plate on the floor that says where: a lit square
		TArray<FSlab> Mark;
		for (const FPad* Pad : {&A, &B})
		{
			FSlab S;
			S.Kind = ESlab::Strip;
			S.Centre = Pad->Here + FVector(0.0, 0.0, 1.5);
			S.Half = FVector(55.0, 55.0, 1.5);
			S.Comp = Pad->Comp;
			Mark.Add(S);
		}
		AddSlabs(Mark);
	}
}

bool AAstraBoardInterior::EnsureAround(const FVector& PlanCm, int32 MaxRooms)
{
	if (!Plan.IsValid() || !Plan->Map.IsValid() || !Walls)
	{
		return false;
	}
	const FAstraBoardMap& Map = *Plan->Map;
	struct FWant { int32 Comp; double D; };
	TArray<FWant> Want;
	for (int32 i = 0; i < Map.GetComps().Num(); ++i)
	{
		if (Built.Contains(i))
		{
			continue;
		}
		const FBox& B = Map.GetComps()[i].Box;
		if (FMath::Abs(B.Min.Z - PlanCm.Z) > 250.0)
		{
			continue;                                                    // another deck
		}
		const double D = FMath::Sqrt(B.ComputeSquaredDistanceToPoint(FVector(PlanCm.X, PlanCm.Y, B.GetCenter().Z)));
		if (D < 4800.0)
		{
			Want.Add({i, D});
		}
	}
	Want.Sort([](const FWant& A, const FWant& B) { return A.D < B.D; });
	int32 Made = 0;
	for (const FWant& W : Want)
	{
		if (Made >= MaxRooms)
		{
			return true;
		}
		TArray<FSlab> Slabs;
		BuildComp(Map, W.Comp, Slabs);
		AddSlabs(Slabs);
		MakePads(W.Comp);
		Built.Add(W.Comp);
		++Made;
	}
	return false;
}

void AAstraBoardInterior::SetShut(const TSet<int32>& ShutDoors)
{
	if (!Leaves)
	{
		return;
	}
	for (const TPair<int32, int32>& KV : LeafInstance)
	{
		const bool bShut = ShutDoors.Contains(KV.Key);
		if (bShut == ShutNow.Contains(KV.Key))
		{
			continue;
		}
		const FTransform* Home = LeafHome.Find(KV.Key);
		if (!Home)
		{
			continue;
		}
		FTransform T = *Home;
		if (!bShut)
		{
			T.AddToTranslation(FVector(0.0, 0.0, -6000.0));
		}
		Leaves->UpdateInstanceTransform(KV.Value, T, true, true, true);
	}
	ShutNow = ShutDoors;
}

int32 AAstraBoardInterior::PadNear(const FVector& PlanCm, float ReachCm, FVector& OutTo, FString& OutText) const
{
	int32 Best = INDEX_NONE;
	double BestD = ReachCm;
	for (int32 i = 0; i < Pads.Num(); ++i)
	{
		const FPad& P = Pads[i];
		if (FMath::Abs(P.Here.Z - PlanCm.Z) > 120.0)
		{
			continue;
		}
		const double D = FVector::Dist2D(P.Here, PlanCm);
		if (D < BestD)
		{
			BestD = D;
			Best = i;
			OutTo = P.To;
			OutText = P.Text;
		}
	}
	return Best;
}

void AAstraBoardInterior::Follow(const FVector& EyeWorld, const FVector& LookWorld)
{
	LastEye = EyeWorld;
	LastLook = LookWorld.GetSafeNormal();
	if (Torch)
	{
		Torch->SetWorldLocationAndRotation(EyeWorld + LastLook * 18.0 + FVector(0.0, 0.0, -10.0), LastLook.Rotation());
	}
}

void AAstraBoardInterior::MoveLights()
{
	if (Lights.IsEmpty() || StripAt.IsEmpty())
	{
		return;
	}
	const FVector Eye = LastEye - Offset;
	struct FNear { int32 I; double D; };
	TArray<FNear> Ns;
	for (int32 i = 0; i < StripAt.Num(); ++i)
	{
		const double D = FVector::DistSquared(StripAt[i], Eye);
		if (D < FMath::Square(3200.0) && FMath::Abs(StripAt[i].Z - Eye.Z) < 400.0)
		{
			Ns.Add({i, D});
		}
	}
	Ns.Sort([](const FNear& A, const FNear& B) { return A.D < B.D; });
	for (int32 k = 0; k < Lights.Num(); ++k)
	{
		UPointLightComponent* L = Lights[k];
		if (!L)
		{
			continue;
		}
		if (k < Ns.Num())
		{
			L->SetWorldLocation(Offset + StripAt[Ns[k].I] - FVector(0.0, 0.0, 30.0));
			L->SetVisibility(true);
		}
		else
		{
			L->SetVisibility(false);
		}
	}
}

void AAstraBoardInterior::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	LightT -= DeltaSeconds;
	if (LightT <= 0.f)
	{
		LightT = 0.3f;
		MoveLights();
	}
}

FVector AAstraBoardInterior::BuildCabin()
{
	End();
	Offset = CabinOrigin();
	Cube = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cube.Cube"));
	UMaterialInterface* Structure = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/ASTRA/Materials/Instances/MI_ASTRA_Structure.MI_ASTRA_Structure"));
	UMaterialInterface* Floor = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/ASTRA/Materials/Instances/MI_ASTRA_Floor.MI_ASTRA_Floor"));
	UMaterialInterface* Trim = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/ASTRA/Materials/Instances/MI_ASTRA_Trim.MI_ASTRA_Trim"));
	if (!Cube)
	{
		return Offset;
	}
	Walls = MakeIsm(TEXT("Walls"), Structure);
	Floors = MakeIsm(TEXT("Floors"), Floor);
	Frames = MakeIsm(TEXT("Frames"), Trim);
	for (UInstancedStaticMeshComponent* S : {Walls.Get(), Floors.Get(), Frames.Get()})
	{
		S->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
		S->SetCollisionProfileName(UCollisionProfile::BlockAll_ProfileName);
	}
	// a boat's troop bay: six metres by three, two and a half high, a bench down each side, a lamp in red
	TArray<FSlab> Slabs;
	const auto Add = [&](ESlab Kind, const FVector& C, const FVector& H) { FSlab S; S.Kind = Kind; S.Centre = C; S.Half = H; Slabs.Add(S); };
	Add(ESlab::Floor, FVector(0, 0, -11), FVector(310, 160, 11));
	Add(ESlab::Ceiling, FVector(0, 0, 255), FVector(310, 160, 10));
	Add(ESlab::Wall, FVector(305, 0, 125), FVector(6, 150, 125));
	Add(ESlab::Wall, FVector(-305, 0, 125), FVector(6, 150, 125));
	Add(ESlab::Wall, FVector(0, 155, 125), FVector(300, 6, 125));
	Add(ESlab::Wall, FVector(0, -155, 125), FVector(300, 6, 125));
	Add(ESlab::Frame, FVector(0, 120, 24), FVector(250, 28, 24));
	Add(ESlab::Frame, FVector(0, -120, 24), FVector(250, 28, 24));
	AddSlabs(Slabs);
	UPointLightComponent* L = NewObject<UPointLightComponent>(this, TEXT("CabinLight"));
	L->SetupAttachment(GetRootComponent());
	L->SetMobility(EComponentMobility::Movable);
	L->SetIntensityUnits(ELightUnits::Lumens);
	L->SetIntensity(1800.f);
	L->SetLightColor(FLinearColor(1.f, 0.18f, 0.08f));
	L->SetAttenuationRadius(900.f);
	L->SetCastShadows(false);
	L->SetWorldLocation(Offset + FVector(0, 0, 225));
	L->RegisterComponent();
	Lights.Add(L);
	return Offset + FVector(-120.0, 0.0, 2.0);
}

void AAstraBoardInterior::End()
{
	SetActorTickEnabled(false);
	for (UInstancedStaticMeshComponent* S : {Walls.Get(), Floors.Get(), Frames.Get(), Leaves.Get(), Strips.Get()})
	{
		if (S)
		{
			S->DestroyComponent();
		}
	}
	for (UPointLightComponent* L : Lights)
	{
		if (L)
		{
			L->DestroyComponent();
		}
	}
	if (Torch)
	{
		Torch->DestroyComponent();
	}
	Walls = Floors = Frames = Leaves = Strips = nullptr;
	Lights.Reset();
	Torch = nullptr;
	StripMat = nullptr;
	Built.Reset();
	LeafInstance.Reset();
	LeafHome.Reset();
	ShutNow.Reset();
	StripAt.Reset();
	Pads.Reset();
	PadDone.Reset();
	NumInstances = 0;
	Plan.Reset();
}
