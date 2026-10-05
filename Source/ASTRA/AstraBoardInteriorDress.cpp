// ASTRA — ABBORDAGGI-3: the dressing of the decks in the world: the kit's pieces as instanced meshes (one component for each piece the decks use), the boxes that make the props solid, the lamps that light the
// rooms near the Captain, the signs over the doors, the flames, the smoke and the sparks where the war has been, the fallen where they fell. What goes where is AstraBoardDress's (plain code, benched); this
// only puts it in the world and keeps the few pooled parts that are alive near the Captain. No part exists for a room he cannot see, nothing ticks while nothing is near.

#include "AstraBoardInterior.h"

#include "ASTRA.h"
#include "AstraBoardDress.h"
#include "AstraCombatFx.h"
#include "Components/AudioComponent.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Components/PointLightComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Components/TextRenderComponent.h"
#include "Engine/CollisionProfile.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "HAL/IConsoleManager.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
#include "Misc/App.h"
#include "Sound/SoundAttenuation.h"
#include "Sound/SoundBase.h"

using namespace AstraBoardDress;

// the light of the dressed decks (ABBORDAGGI-4, from the first play of a powered ship's corridors, which were too dark to read): the lamps near the Captain give a point light each; these say how much, how far and how many
static TAutoConsoleVariable<float> CVarBoardLampLumens(TEXT("astra.board.lamp_lumens"), 1.8f, TEXT("The dressed decks' lamps: how many times the base light of a lit lamp (2300-2600 lumens; a red one 650) each of the lights near the Captain gives. 1 is what the decks had at first."), ECVF_Default);
static TAutoConsoleVariable<float> CVarBoardLampRadius(TEXT("astra.board.lamp_radius"), 1.4f, TEXT("The dressed decks' lamps: how many times the reach of a lamp's light (11 m, a red one 9.5 m). 1 is what the decks had at first."), ECVF_Default);
static TAutoConsoleVariable<int32> CVarBoardLampCount(TEXT("astra.board.lamp_count"), 12, TEXT("The dressed decks' lamps: how many of the nearest lamps on the Captain's deck give light at once (1 to 16; the pool of lights is made when the decks are dressed). Each costs a movable light without shadows."), ECVF_Default);
static TAutoConsoleVariable<int32> CVarBoardDress(TEXT("astra.board.dress"), 2,
                                                  TEXT("The decks of a boarded ship: 0 plain boxes, 1 the structure of the kit (bays, ceilings, floors, frames, lamps), 2 also props, banners, signs, debris, the fallen, flames, smoke and sparks; "
                                                       "3 as 2 with the engine's cube for every piece (the bench's: the content of a headless run has none of the kit). Read when the decks are made."),
                                                  ECVF_Default);

namespace
{
	/** A pooled flame or puff: the effects' own sphere and materials (UAstraDamageFx's), assigned to the nearest hazards. */
	struct FFxPart
	{
		UStaticMeshComponent* Mesh = nullptr;
		UMaterialInstanceDynamic* Mid = nullptr;
		int32 Spot = INDEX_NONE;
		float Level = 0.f, Target = 0.f, Phase = 0.f;
		double Shown = -1.0;
	};

	float Flicker(double T, float Phase)
	{
		return 0.5f + 0.25f * FMath::Sin((float)T * 9.1f + Phase * 6.28f) + 0.15f * FMath::Sin((float)T * 17.3f + Phase * 3.1f) + 0.1f * FMath::Sin((float)T * 31.7f + Phase);
	}

	/** The tint a side gives a finish of the kit (the Mandate's are the instances' own). False: leave it as it is. */
	bool SideTint(EDressSide Side, const FString& Slot, FLinearColor& Out)
	{
		if (Side == EDressSide::Astra)
		{
			static const TMap<FString, FLinearColor> M = {
				{TEXT("MI_BRD_Plating"), FLinearColor(0.42f, 0.43f, 0.44f)}, {TEXT("MI_BRD_Frame"), FLinearColor(0.067f, 0.078f, 0.091f)}, {TEXT("MI_BRD_Iron"), FLinearColor(0.023f, 0.026f, 0.031f)},
				{TEXT("MI_BRD_Deck"), FLinearColor(0.07f, 0.075f, 0.085f)}, {TEXT("MI_BRD_Stencil"), FLinearColor(0.7f, 0.7f, 0.68f)}, {TEXT("MI_BRD_Cloth"), FLinearColor(0.014f, 0.042f, 0.147f)},
				{TEXT("MI_BRD_Uniform"), FLinearColor(0.01f, 0.02f, 0.05f)}, {TEXT("MI_BRD_Verdigris"), FLinearColor(0.12f, 0.2f, 0.22f)},
			};
			if (const FLinearColor* C = M.Find(Slot))
			{
				Out = *C;
				return true;
			}
		}
		else if (Side == EDressSide::Guild)
		{
			static const TMap<FString, FLinearColor> M = {
				{TEXT("MI_BRD_Plating"), FLinearColor(0.12f, 0.07f, 0.04f)}, {TEXT("MI_BRD_Frame"), FLinearColor(0.04f, 0.035f, 0.03f)}, {TEXT("MI_BRD_Deck"), FLinearColor(0.1f, 0.09f, 0.08f)},
				{TEXT("MI_BRD_Hazard"), FLinearColor(0.5f, 0.35f, 0.02f)}, {TEXT("MI_BRD_Stencil"), FLinearColor(0.6f, 0.55f, 0.4f)}, {TEXT("MI_BRD_Cloth"), FLinearColor(0.15f, 0.1f, 0.04f)},
			};
			if (const FLinearColor* C = M.Find(Slot))
			{
				Out = *C;
				return true;
			}
		}
		return false;
	}

	/** How a lamp lights the room under it (colour, lumens, radius) by its state and its side's hand. */
	void LampLook(EDressSide Side, ELamp State, FLinearColor& Col, float& Lumens, float& Radius)
	{
		const float Scale = FMath::Clamp(CVarBoardLampLumens.GetValueOnGameThread(), 0.2f, 12.f), Reach = FMath::Clamp(CVarBoardLampRadius.GetValueOnGameThread(), 0.4f, 4.f);
		if (State == ELamp::Red)
		{
			Col = FLinearColor(1.f, 0.14f, 0.06f);
			Lumens = 650.f * Scale;
			Radius = 950.f * Reach;
			return;
		}
		Col = Side == EDressSide::Mandate ? FLinearColor(1.f, 0.74f, 0.42f) : (Side == EDressSide::Guild ? FLinearColor(1.f, 0.85f, 0.6f) : FLinearColor(1.f, 0.95f, 0.88f));
		Lumens = (Side == EDressSide::Astra ? 2600.f : 2300.f) * Scale;
		Radius = 1100.f * Reach;
	}
}

struct AAstraBoardInterior::FKitState
{
	FDressContext Ctx;
	TArray<FFallen> Fallen;
	TSet<int32> FallenDone;
	TMap<int32, UInstancedStaticMeshComponent*> Isms;                  // by piece
	TSet<int32> Missing;
	UInstancedStaticMeshComponent* Blocks = nullptr;                    // the boxes of the solid props (hidden: they stop the Captain, they are not drawn)
	TMap<FName, UMaterialInstanceDynamic*> StyleMids;                   // a side's tint of a finish (the Mandate's have none: the instances are theirs)
	TMap<int32, int32> LeafInstance;                                    // door -> its instance of the kit's blast leaf
	TMap<int32, FTransform> LeafHome;
	TArray<FLamp> Lamps;
	TArray<FDoorSign> Signs;
	TArray<FWarMark> Fx;
	TArray<UTextRenderComponent*> SignPool;
	UMaterialInstanceDynamic* SignMid = nullptr;
	TArray<FFxPart> Flames, Smokes;
	UStaticMesh* Sphere = nullptr;
	UMaterialInterface* BlastMat = nullptr;
	UMaterialInterface* SmokeMat = nullptr;
	TArray<FLinearColor> LightCol;
	TArray<float> LightLumens;
	TArray<int32> SparkSpots;                                           // the nearest spark spots now, and when each spits next
	TArray<double> SparkNext;
	UAudioComponent* FireAudio = nullptr;
	USoundAttenuation* Falloff = nullptr;
	float FireLevel = 0.f, FireTarget = 0.f;
	FVector FireAt = FVector::ZeroVector;
	int32 Instances = 0, Props = 0, Bodies = 0, Rooms = 0;
	int32 ByFrame[6] = {0, 0, 0, 0, 0, 0};
	double Clock = 0.0;
	bool bWarned = false;
	bool bTest = false;                                                 // the bench's: every piece is the engine's cube

	UInstancedStaticMeshComponent* Ism(AAstraBoardInterior* A, TArray<TObjectPtr<UObject>>& Keep, EPiece P)
	{
		if (UInstancedStaticMeshComponent** Hit = Isms.Find((int32)P))
		{
			return *Hit;
		}
		if (Missing.Contains((int32)P))
		{
			return nullptr;
		}
		UStaticMesh* Mesh = bTest ? A->Cube.Get() : LoadObject<UStaticMesh>(nullptr, *MeshPath(P));
		if (!Mesh)
		{
			Missing.Add((int32)P);
			if (!bWarned)
			{
				bWarned = true;
				UE_LOG(LogASTRA, Warning, TEXT("[BoardDress] %s is not in the content: run tools/ue_scripts/make_board_materials.py and import_board_kit.py (that piece is left out)"), *MeshPath(P));
			}
			return nullptr;
		}
		UInstancedStaticMeshComponent* C = NewObject<UInstancedStaticMeshComponent>(A, *FString::Printf(TEXT("Kit_%s"), Def(P).Key));
		C->SetupAttachment(A->GetRootComponent());
		C->SetStaticMesh(Mesh);
		C->SetMobility(EComponentMobility::Movable);
		C->SetCollisionEnabled(ECollisionEnabled::NoCollision);       // (a prop's solidity is its box's: Blocks)
		C->SetCastShadow(false);
		C->SetCullDistances(0, 9000);
		// another side's ship: the same finishes in her colours
		if (Ctx.Side != EDressSide::Mandate)
		{
			const TArray<FStaticMaterial>& Mats = Mesh->GetStaticMaterials();
			for (int32 i = 0; i < Mats.Num(); ++i)
			{
				const FString Slot = Mats[i].MaterialSlotName.ToString();
				FLinearColor Tint;
				UMaterialInterface* Base = Mats[i].MaterialInterface;
				if (!Base || !SideTint(Ctx.Side, Slot, Tint))
				{
					continue;
				}
				UMaterialInstanceDynamic*& Mid = StyleMids.FindOrAdd(Mats[i].MaterialSlotName);
				if (!Mid)
				{
					Mid = UMaterialInstanceDynamic::Create(Base, A);
					Mid->SetVectorParameterValue(TEXT("Tint"), Tint);
					Keep.Add(Mid);
				}
				C->SetMaterial(i, Mid);
			}
		}
		C->RegisterComponent();
		Isms.Add((int32)P, C);
		return C;
	}
};

bool AAstraBoardInterior::DressBegin(const TArray<FFallen>* InFallen)
{
	const int32 Setting = CVarBoardDress.GetValueOnGameThread();
	const int32 Level = FMath::Min(Setting, 2);
	if (Level <= 0 || !Plan.IsValid() || !Cube || !Walls)
	{
		return false;
	}
	TSharedRef<FKitState> K = MakeShared<FKitState>();
	K->bTest = Setting >= 3;
	K->Ctx.Plan = Plan.Get();
	K->Ctx.Side = SideOfStyle(Plan->Style);
	K->Ctx.Seed = SeedOf(Plan->Class);
	K->Ctx.bHulk = Style == EAstraInteriorStyle::Emergency;
	K->Ctx.Moods = Moods.IsEmpty() ? nullptr : &Moods;
	K->Ctx.Level = Level;
	// the kit must be in the content: its walls, its floor and its frames are what the dressing is made of (a deck of plain boxes is better than one of holes)
	if (!K->Ism(this, KitKeep, EPiece::WallA) || !K->Ism(this, KitKeep, EPiece::Floor) || !K->Ism(this, KitKeep, EPiece::Jamb))
	{
		for (const TPair<int32, UInstancedStaticMeshComponent*>& KV : K->Isms)
		{
			KV.Value->DestroyComponent();
		}
		return false;
	}
	if (InFallen)
	{
		K->Fallen = *InFallen;
	}
	// the structure's boxes are what the Captain walks between and what the soldiers' rounds strike; what is seen is the kit's: the frames and the pressure leaves are not drawn (their collision stays)
	for (UInstancedStaticMeshComponent* S : {Frames.Get(), Leaves.Get()})
	{
		if (S)
		{
			S->SetVisibility(false);
		}
	}
	// the boxes of the walls and the floors in the side's own colour (the Mandate's basalt and black iron: the rest of the bare structure that shows above the bays and between them)
	// (the cube's texture is stretched over a whole wall: its grain is calmed so that the bare plating above the bays is not a field of craters)
	const auto Tinted = [this](UInstancedStaticMeshComponent* C, const FLinearColor& Tint, float NormalStrength)
	{
		if (!C || !C->GetMaterial(0))
		{
			return;
		}
		UMaterialInstanceDynamic* Mid = UMaterialInstanceDynamic::Create(C->GetMaterial(0), this);
		if (Mid)
		{
			Mid->SetVectorParameterValue(TEXT("Tint"), Tint);
			Mid->SetScalarParameterValue(TEXT("NormalStrength"), NormalStrength);
			C->SetMaterial(0, Mid);
			KitKeep.Add(Mid);
		}
	};
	if (K->Ctx.Side == EDressSide::Mandate)
	{
		Tinted(Walls, FLinearColor(0.045f, 0.040f, 0.034f), 0.3f);
		Tinted(Floors, FLinearColor(0.035f, 0.035f, 0.038f), 0.4f);
	}
	else if (K->Ctx.Side == EDressSide::Guild)
	{
		Tinted(Walls, FLinearColor(0.06f, 0.045f, 0.035f), 0.3f);
		Tinted(Floors, FLinearColor(0.05f, 0.045f, 0.04f), 0.4f);
	}
	// the hidden boxes that make the solid props solid
	K->Blocks = NewObject<UInstancedStaticMeshComponent>(this, TEXT("KitBlocks"));
	K->Blocks->SetupAttachment(GetRootComponent());
	K->Blocks->SetStaticMesh(Cube);
	K->Blocks->SetMobility(EComponentMobility::Movable);
	K->Blocks->SetCastShadow(false);
	K->Blocks->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
	K->Blocks->SetCollisionProfileName(UCollisionProfile::BlockAll_ProfileName);
	K->Blocks->SetVisibility(false);
	K->Blocks->SetHiddenInGame(true);
	K->Blocks->RegisterComponent();
	// the pooled parts of the war's effects: the effects' own sphere and materials
	K->Sphere = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Sphere.Sphere"));
	K->BlastMat = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/ASTRA/Materials/M_FX_Blast.M_FX_Blast"));
	K->SmokeMat = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/ASTRA/Materials/M_FX_Smoke.M_FX_Smoke"));
	if (UMaterialInterface* TextMat = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/ASTRA/Materials/M_ASTRA_HoloText.M_ASTRA_HoloText")))
	{
		K->SignMid = UMaterialInstanceDynamic::Create(TextMat, this);
		if (K->SignMid)
		{
			K->SignMid->SetScalarParameterValue(TEXT("Intensity"), 7.f);
			KitKeep.Add(K->SignMid);
		}
	}
	// the lights of the lamps near him: more than the plain rooms' (a corridor's lamps are three metres apart: the pool is the most the cvar lets; astra.board.lamp_count says how many of them are on)
	while (Lights.Num() < 16)
	{
		UPointLightComponent* L = NewObject<UPointLightComponent>(this, *FString::Printf(TEXT("Light%d"), Lights.Num()));
		L->SetupAttachment(GetRootComponent());
		L->SetMobility(EComponentMobility::Movable);
		L->SetIntensityUnits(ELightUnits::Lumens);
		L->SetIntensity(1000.f);
		L->SetAttenuationRadius(1000.f);
		L->SetCastShadows(false);
		L->SetVisibility(false);
		L->RegisterComponent();
		Lights.Add(L);
	}
	K->LightCol.Init(FLinearColor::Black, Lights.Num());
	K->LightLumens.Init(0.f, Lights.Num());
	Kit = K;
	UE_LOG(LogASTRA, Log, TEXT("[BoardDress] the decks of the %s are dressed (level %d, %s hand): %d fallen to lay"), *Plan->Class.ToString(), Level,
	       Kit->Ctx.Side == EDressSide::Mandate ? TEXT("Mandate") : (Kit->Ctx.Side == EDressSide::Guild ? TEXT("Guild") : TEXT("Astra")), Kit->Fallen.Num());
	return true;
}

void AAstraBoardInterior::DressBuilt(int32 Comp)
{
	if (!Kit || !Plan.IsValid())
	{
		return;
	}
	FRoomDress Rd;
	DressRoom(Kit->Ctx, Plan->Layout.Get(), Comp, Rd);
	TMap<int32, TArray<FTransform>> ByPiece;
	for (const FPlacement& P : Rd.Pieces)
	{
		const FTransform Xf(P.Rot.Quaternion(), P.Pos, P.Scale);
		if (P.Piece == EPiece::BlastLeaf && P.Door != INDEX_NONE)
		{
			if (UInstancedStaticMeshComponent* Ism = Kit->Ism(this, KitKeep, P.Piece))
			{
				// a leaf stands in its bulkhead while it is shut; open, it lies away under the deck
				FTransform Away = Xf;
				Away.AddToTranslation(FVector(0.0, 0.0, -6000.0));
				Kit->LeafHome.Add(P.Door, Xf);
				Kit->LeafInstance.Add(P.Door, Ism->AddInstance(ShutNow.Contains(P.Door) ? Xf : Away, false));
				++Kit->Instances;
				++Kit->ByFrame[(int32)EFrame::Opening];
			}
			continue;
		}
		ByPiece.FindOrAdd((int32)P.Piece).Add(Xf);
	}
	for (TPair<int32, TArray<FTransform>>& KV : ByPiece)
	{
		if (UInstancedStaticMeshComponent* Ism = Kit->Ism(this, KitKeep, (EPiece)KV.Key))
		{
			Ism->AddInstances(KV.Value, false, false, false);
			Kit->Instances += KV.Value.Num();
			Kit->ByFrame[(int32)Def((EPiece)KV.Key).Frame] += KV.Value.Num();
			Kit->Props += Def((EPiece)KV.Key).Frame == EFrame::Prop ? KV.Value.Num() : 0;
		}
	}
	if (Kit->Blocks && Rd.Blocks.Num())
	{
		TArray<FTransform> Boxes;
		for (const FSolid& B : Rd.Blocks)
		{
			Boxes.Add(FTransform(FQuat::Identity, B.Centre, B.Half * 2.0 / 100.0));
		}
		Kit->Blocks->AddInstances(Boxes, false, false, false);
		NumInstances += Boxes.Num();
	}
	Kit->Lamps.Append(Rd.Lamps);
	Kit->Signs.Append(Rd.Signs);
	Kit->Fx.Append(Rd.Fx);
	++Kit->Rooms;
	// the crew she lost lie where they fell (the bodies are instanced like the rest)
	if (Kit->Ctx.Level >= 2 && !Kit->FallenDone.Contains(Comp))
	{
		Kit->FallenDone.Add(Comp);
		TArray<FFallen> Here;
		for (const FFallen& F : Kit->Fallen)
		{
			if (F.Comp == Comp)
			{
				Here.Add(F);
			}
		}
		if (Here.Num())
		{
			TArray<FPlacement> Bodies;
			DressFallen(Kit->Ctx, Here, Bodies);
			TMap<int32, TArray<FTransform>> Group;
			for (const FPlacement& P : Bodies)
			{
				Group.FindOrAdd((int32)P.Piece).Add(FTransform(P.Rot.Quaternion(), P.Pos, P.Scale));
			}
			for (TPair<int32, TArray<FTransform>>& KV : Group)
			{
				if (UInstancedStaticMeshComponent* Ism = Kit->Ism(this, KitKeep, (EPiece)KV.Key))
				{
					Ism->AddInstances(KV.Value, false, false, false);
					Kit->Bodies += KV.Value.Num();
					Kit->Instances += KV.Value.Num();
					Kit->ByFrame[(int32)EFrame::Body] += KV.Value.Num();
				}
			}
		}
	}
	NumInstances += Rd.Pieces.Num();
}

void AAstraBoardInterior::DressShut(const TSet<int32>& ShutDoors)
{
	if (!Kit)
	{
		return;
	}
	UInstancedStaticMeshComponent* Ism = Kit->Ism(this, KitKeep, EPiece::BlastLeaf);
	if (!Ism)
	{
		return;
	}
	for (const TPair<int32, int32>& KV : Kit->LeafInstance)
	{
		const FTransform* Home = Kit->LeafHome.Find(KV.Key);
		if (!Home)
		{
			continue;
		}
		FTransform T = *Home;
		if (!ShutDoors.Contains(KV.Key))
		{
			T.AddToTranslation(FVector(0.0, 0.0, -6000.0));
		}
		Ism->UpdateInstanceTransform(KV.Value, T, false, true, true);
	}
}

FString AAstraBoardInterior::DescribeDress() const
{
	if (!Kit)
	{
		return FString();
	}
	int32 Lit = 0, Red = 0, Dead = 0;
	for (const FLamp& L : Kit->Lamps)
	{
		(L.State == ELamp::Lit ? Lit : (L.State == ELamp::Red ? Red : Dead))++;
	}
	return FString::Printf(TEXT("dressed: %d rooms, %d kit instances (%d wall, %d ceiling, %d floor, %d opening, %d prop, %d fallen), %d lamps (%d lit, %d red, %d dead), %d door signs, %d flames/smoke/sparks, %d hidden boxes"),
	                       Kit->Rooms, Kit->Instances, Kit->ByFrame[0], Kit->ByFrame[1], Kit->ByFrame[2], Kit->ByFrame[3], Kit->ByFrame[4], Kit->ByFrame[5], Kit->Lamps.Num(), Lit, Red, Dead, Kit->Signs.Num(), Kit->Fx.Num(),
	                       Kit->Blocks ? Kit->Blocks->GetInstanceCount() : 0);
}

// ================================================================================================================== near the Captain
void AAstraBoardInterior::DressLights(const FVector& Eye)
{
	if (!Kit)
	{
		return;
	}
	FKitState& K = *Kit;
	const EDressSide Side = K.Ctx.Side;
	// the lamps that light: the nearest lit and red ones on his deck
	struct FNear { int32 I; double D; };
	TArray<FNear> Ns;
	for (int32 i = 0; i < K.Lamps.Num(); ++i)
	{
		const FLamp& L = K.Lamps[i];
		if (L.State == ELamp::Dead)
		{
			continue;
		}
		const double D = FVector::DistSquared(L.Pos, Eye);
		if (D < FMath::Square(3300.0) && FMath::Abs(L.Pos.Z - Eye.Z) < 520.0)
		{
			Ns.Add({i, D});
		}
	}
	Ns.Sort([](const FNear& A, const FNear& B) { return A.D < B.D; });
	const int32 On = FMath::Clamp(CVarBoardLampCount.GetValueOnGameThread(), 1, Lights.Num());
	for (int32 k = 0; k < Lights.Num(); ++k)
	{
		UPointLightComponent* L = Lights[k];
		if (!L)
		{
			continue;
		}
		if (k < Ns.Num() && k < On)
		{
			const FLamp& Lp = K.Lamps[Ns[k].I];
			FLinearColor Col;
			float Lumens, Radius;
			LampLook(Side, Lp.State, Col, Lumens, Radius);
			if (K.LightCol.IsValidIndex(k) && (!K.LightCol[k].Equals(Col) || K.LightLumens[k] != Lumens || !FMath::IsNearlyEqual(L->AttenuationRadius, Radius)))
			{
				K.LightCol[k] = Col;
				K.LightLumens[k] = Lumens;
				L->SetLightColor(Col);
				L->SetIntensity(Lumens);
				L->SetAttenuationRadius(Radius);
			}
			L->SetWorldLocation(Offset + Lp.Pos);
			L->SetVisibility(true);
		}
		else
		{
			L->SetVisibility(false);
		}
	}
	// the war's marks near him: the nearest flames, puffs of smoke, the spots that spit
	TArray<FNear> Flame, Smoke, Spark;
	for (int32 i = 0; i < K.Fx.Num(); ++i)
	{
		const FWarMark& F = K.Fx[i];
		const double D = FVector::DistSquared(F.Pos, Eye);
		const double Reach = F.Kind == FWarMark::EKind::Spark ? 2600.0 : (F.Kind == FWarMark::EKind::Smoke ? 4200.0 : 4200.0);
		if (D < FMath::Square(Reach) && FMath::Abs(F.Pos.Z - Eye.Z) < 700.0)
		{
			(F.Kind == FWarMark::EKind::Flame ? Flame : (F.Kind == FWarMark::EKind::Smoke ? Smoke : Spark)).Add({i, D});
		}
	}
	for (TArray<FNear>* A : {&Flame, &Smoke, &Spark})
	{
		A->Sort([](const FNear& X, const FNear& Y) { return X.D < Y.D; });
	}
	const auto Assign = [this, &K](TArray<FFxPart>& Pool, const TArray<FNear>& Want, UMaterialInterface* Mat, int32 Max)
	{
		if (!K.Sphere || !Mat)
		{
			return;
		}
		while (Pool.Num() < FMath::Min(Max, Want.Num()))
		{
			FFxPart P;
			UStaticMeshComponent* C = NewObject<UStaticMeshComponent>(this);
			C->SetupAttachment(GetRootComponent());
			C->SetMobility(EComponentMobility::Movable);
			C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
			C->SetCastShadow(false);
			C->bReceivesDecals = false;
			C->RegisterComponent();
			C->SetStaticMesh(K.Sphere);
			C->SetVisibility(false);
			P.Mesh = C;
			P.Mid = C->CreateDynamicMaterialInstance(0, Mat);
			P.Phase = FMath::FRand() * 6.28f;
			if (P.Mid)
			{
				KitKeep.Add(P.Mid);
			}
			Pool.Add(P);
		}
		// a part keeps its spot while the spot is still among the nearest; the rest are taken by the spots that have none
		TSet<int32> Taken;
		for (FFxPart& P : Pool)
		{
			const bool bStays = P.Spot != INDEX_NONE && Want.ContainsByPredicate([&P](const FNear& N) { return N.I == P.Spot; });
			if (bStays)
			{
				P.Target = 1.f;
				Taken.Add(P.Spot);
			}
			else
			{
				P.Target = 0.f;
			}
		}
		for (const FNear& N : Want)
		{
			if (Taken.Contains(N.I))
			{
				continue;
			}
			for (FFxPart& P : Pool)
			{
				if (P.Target <= 0.f && (P.Level <= 0.01f || P.Spot == INDEX_NONE))
				{
					P.Spot = N.I;
					P.Target = 1.f;
					break;
				}
			}
		}
	};
	Assign(K.Flames, Flame, K.BlastMat, 3);
	Assign(K.Smokes, Smoke, K.SmokeMat, 3);
	// the sparks: the two nearest spots spit on their own clocks (DressTick)
	K.SparkSpots.Reset();
	for (int32 i = 0; i < Spark.Num() && i < 2; ++i)
	{
		K.SparkSpots.Add(Spark[i].I);
	}
	K.SparkNext.SetNumZeroed(K.SparkSpots.Num());
	// the lights of the flames, and the roar of the nearest
	for (int32 i = 0; i < FireLights.Num(); ++i)
	{
		UPointLightComponent* L = FireLights[i];
		if (!L)
		{
			continue;
		}
		if (i < Flame.Num())
		{
			L->SetWorldLocation(Offset + K.Fx[Flame[i].I].Pos + FVector(0.0, 0.0, 60.0));
			L->SetIntensity(FMath::FRandRange(3400.f, 6400.f));
			L->SetVisibility(true);
		}
		else
		{
			L->SetVisibility(false);
		}
	}
	K.FireTarget = 0.f;
	if (Flame.Num() && Flame[0].D < FMath::Square(2600.0))
	{
		K.FireTarget = 1.f;
		K.FireAt = K.Fx[Flame[0].I].Pos;
	}
	// the signs over the doors: the nearest that look his way, with the name of the room beyond
	if (K.Ctx.Level >= 2 && K.SignMid)
	{
		TArray<FNear> Signs;
		for (int32 i = 0; i < K.Signs.Num(); ++i)
		{
			const FDoorSign& S = K.Signs[i];
			const double D = FVector::DistSquared(S.Pos, Eye);
			if (D < FMath::Square(1500.0) && FMath::Abs(S.Pos.Z - Eye.Z) < 300.0 && FVector2D::DotProduct(S.Facing, FVector2D(Eye.X - S.Pos.X, Eye.Y - S.Pos.Y)) > 0.0)
			{
				Signs.Add({i, D});
			}
		}
		Signs.Sort([](const FNear& A, const FNear& B) { return A.D < B.D; });
		const FColor Ink = Side == EDressSide::Mandate ? FColor(255, 172, 64) : (Side == EDressSide::Guild ? FColor(236, 208, 150) : FColor(200, 232, 255));
		while (K.SignPool.Num() < FMath::Min(8, Signs.Num()))
		{
			UTextRenderComponent* T = NewObject<UTextRenderComponent>(this);
			T->SetupAttachment(GetRootComponent());
			T->SetCollisionEnabled(ECollisionEnabled::NoCollision);
			T->SetCastShadow(false);
			T->SetTextMaterial(K.SignMid);
			T->SetHorizontalAlignment(EHTA_Center);
			T->SetVerticalAlignment(EVRTA_TextCenter);
			T->SetWorldSize(9.f);
			T->SetTextRenderColor(Ink);
			T->RegisterComponent();
			T->SetVisibility(false);
			K.SignPool.Add(T);
		}
		for (int32 k = 0; k < K.SignPool.Num(); ++k)
		{
			UTextRenderComponent* T = K.SignPool[k];
			if (k < Signs.Num())
			{
				const FDoorSign& S = K.Signs[Signs[k].I];
				const FText Txt = FText::FromString(S.Text);
				if (!T->Text.EqualTo(Txt))
				{
					T->SetText(Txt);
					// a long name is set smaller: the lintel is a metre and a half wide
					T->SetWorldSize(FMath::Clamp(150.f / FMath::Max(1, S.Text.Len()) * 1.55f, 5.f, 10.f));
				}
				T->SetWorldLocationAndRotation(Offset + S.Pos, FRotator(0.f, FMath::RadiansToDegrees(FMath::Atan2(S.Facing.Y, S.Facing.X)), 0.f));
				T->SetVisibility(true);
			}
			else
			{
				T->SetVisibility(false);
			}
		}
	}
}

void AAstraBoardInterior::DressTick(float Dt)
{
	if (!Kit)
	{
		return;
	}
	FKitState& K = *Kit;
	K.Clock += Dt;
	const double Clock = K.Clock;
	const auto Animate = [&K, this, Dt, Clock](TArray<FFxPart>& Pool, bool bSmoke)
	{
		for (FFxPart& P : Pool)
		{
			if (!P.Mesh || !P.Mid)
			{
				continue;
			}
			P.Level = FMath::FInterpConstantTo(P.Level, P.Target, Dt, P.Target > P.Level ? 1.f / 0.8f : 1.f / 1.6f);
			if (P.Level <= 0.002f && P.Target <= 0.f)
			{
				P.Mesh->SetVisibility(false);
				continue;
			}
			if (!K.Fx.IsValidIndex(P.Spot))
			{
				continue;
			}
			const FWarMark& F = K.Fx[P.Spot];
			P.Mesh->SetVisibility(true);
			const bool bParams = Clock - P.Shown >= 0.083;                  // the material is set at 12 Hz, the transform every frame
			if (bParams)
			{
				P.Shown = Clock;
			}
			if (!bSmoke)
			{
				const float Fl = Flicker(Clock, P.Phase);
				const float Hgt = F.Size * (0.8f + 0.5f * Fl) * P.Level, Wid = F.Size * 0.62f * (0.9f + 0.2f * (1.f - Fl)) * P.Level;
				P.Mesh->SetWorldLocationAndRotation(Offset + F.Pos + FVector(FMath::Sin((float)Clock * 3.1f + P.Phase) * 5.f, FMath::Cos((float)Clock * 2.7f + P.Phase) * 5.f, Hgt * 0.5f), FRotator(0.f, P.Phase * 57.f, 0.f));
				P.Mesh->SetWorldScale3D(FVector(Wid, Wid, Hgt) / 100.f);
				if (bParams)
				{
					P.Mid->SetVectorParameterValue(TEXT("Color"), FLinearColor(1.f, 0.38f + 0.12f * Fl, 0.08f));
					P.Mid->SetScalarParameterValue(TEXT("Intensity"), (22.f + 40.f * F.Strength) * (0.7f + 0.6f * Fl));
					P.Mid->SetScalarParameterValue(TEXT("Fade"), P.Level);
				}
			}
			else
			{
				const float Drift = (float)Clock * 0.25f + P.Phase;
				P.Mesh->SetWorldLocation(Offset + F.Pos + FVector(FMath::Sin(Drift) * 24.f, FMath::Cos(Drift * 0.83f) * 24.f, FMath::Sin(Drift * 0.6f) * 12.f));
				const float S = F.Size * (0.85f + 0.15f * P.Level) / 100.f;
				P.Mesh->SetWorldScale3D(FVector(S, S, S * 0.7f));
				if (bParams)
				{
					// a puff is a one-sided sphere: from inside it is not drawn, so it thins out as the eye comes into it
					const float Radius = 0.5f * F.Size;
					const float Away = FMath::Clamp(((float)FVector::Dist(LastEye, Offset + F.Pos) - 0.6f * Radius) / FMath::Max(1.f, 0.5f * Radius), 0.f, 1.f);
					P.Mid->SetVectorParameterValue(TEXT("Color"), FLinearColor(0.13f, 0.125f, 0.12f));
					P.Mid->SetScalarParameterValue(TEXT("Intensity"), 14.f);
					P.Mid->SetScalarParameterValue(TEXT("Opacity"), FMath::Clamp(F.Strength * P.Level * Away, 0.f, 0.92f));
				}
			}
		}
	};
	Animate(K.Flames, false);
	Animate(K.Smokes, true);
	// sparks from the cut conduits: a shower now and then, with its crackle
	if (K.SparkSpots.Num() && GetWorld())
	{
		if (UAstraCombatFx* Fx = GetWorld()->GetSubsystem<UAstraCombatFx>())
		{
			for (int32 i = 0; i < K.SparkSpots.Num(); ++i)
			{
				if (!K.Fx.IsValidIndex(K.SparkSpots[i]))
				{
					continue;
				}
				if (K.SparkNext[i] <= 0.0)
				{
					K.SparkNext[i] = Clock + FMath::FRandRange(0.5f, 2.2f);
				}
				else if (Clock >= K.SparkNext[i])
				{
					K.SparkNext[i] = Clock + FMath::FRandRange(0.9f, 3.6f) / FMath::Max(0.3f, K.Fx[K.SparkSpots[i]].Strength);
					const FVector At = Offset + K.Fx[K.SparkSpots[i]].Pos;
					Fx->Impact(At, FVector(FMath::FRandRange(-0.3f, 0.3f), FMath::FRandRange(-0.3f, 0.3f), -1.f).GetSafeNormal(), UAstraCombatFx::ESurface::Metal);
					Fx->PlaySoundAt(TEXT("/Game/ASTRA/Audio/SW_Sparks.SW_Sparks"), At, 0.8f);
				}
			}
		}
	}
	// the roar of the nearest fire
	K.FireLevel = FMath::FInterpConstantTo(K.FireLevel, K.FireTarget, Dt, 1.f);
	if (K.FireLevel > 0.01f || K.FireTarget > 0.f)
	{
		if (!K.FireAudio && GetWorld())
		{
			if (USoundBase* Loop = LoadObject<USoundBase>(nullptr, TEXT("/Game/ASTRA/Audio/SW_Fire_Loop.SW_Fire_Loop")))
			{
				K.Falloff = NewObject<USoundAttenuation>(this);
				K.Falloff->Attenuation.bAttenuate = true;
				K.Falloff->Attenuation.bSpatialize = true;
				K.Falloff->Attenuation.AttenuationShape = EAttenuationShape::Sphere;
				K.Falloff->Attenuation.AttenuationShapeExtents = FVector(400.f, 0.f, 0.f);
				K.Falloff->Attenuation.FalloffDistance = 2200.f;
				K.Falloff->Attenuation.DistanceAlgorithm = EAttenuationDistanceModel::NaturalSound;
				KitKeep.Add(K.Falloff);
				UAudioComponent* A = NewObject<UAudioComponent>(this);
				A->SetupAttachment(GetRootComponent());
				A->bAutoActivate = false;
				A->SetSound(Loop);
				A->AttenuationSettings = K.Falloff;
				A->SetVolumeMultiplier(0.f);
				A->RegisterComponent();
				K.FireAudio = A;
			}
		}
		if (K.FireAudio)
		{
			K.FireAudio->SetWorldLocation(Offset + K.FireAt);
			K.FireAudio->SetVolumeMultiplier(K.FireLevel * 0.9f);
			if (!K.FireAudio->IsPlaying() && K.FireLevel > 0.01f)
			{
				K.FireAudio->Play();
			}
		}
	}
	else if (K.FireAudio && K.FireAudio->IsPlaying())
	{
		K.FireAudio->Stop();
	}
}

void AAstraBoardInterior::DressEnd()
{
	if (!Kit)
	{
		return;
	}
	for (const TPair<int32, UInstancedStaticMeshComponent*>& KV : Kit->Isms)
	{
		if (KV.Value)
		{
			KV.Value->DestroyComponent();
		}
	}
	if (Kit->Blocks)
	{
		Kit->Blocks->DestroyComponent();
	}
	for (UTextRenderComponent* T : Kit->SignPool)
	{
		if (T)
		{
			T->DestroyComponent();
		}
	}
	for (TArray<FFxPart>* Pool : {&Kit->Flames, &Kit->Smokes})
	{
		for (FFxPart& P : *Pool)
		{
			if (P.Mesh)
			{
				P.Mesh->DestroyComponent();
			}
		}
	}
	if (Kit->FireAudio)
	{
		Kit->FireAudio->Stop();
		Kit->FireAudio->DestroyComponent();
	}
	Kit.Reset();
	KitKeep.Reset();
}
