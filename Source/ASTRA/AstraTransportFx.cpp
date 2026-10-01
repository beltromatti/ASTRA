#include "AstraTransportFx.h"

#include "ASTRA.h"
#include "Components/AudioComponent.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Components/PointLightComponent.h"
#include "Components/PoseableMeshComponent.h"
#include "Components/SceneComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/Engine.h"
#include "Engine/GameViewportClient.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "Framework/Application/SlateApplication.h"
#include "Kismet/GameplayStatics.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Misc/App.h"
#include "Rendering/DrawElements.h"
#include "Sound/SoundAttenuation.h"
#include "Sound/SoundBase.h"
#include "Styling/CoreStyle.h"
#include "Widgets/SLeafWidget.h"

// The columns, the sparkles, the pads' light, the ghosts of the bodies and the Captain's own view (docs/TELETRASPORTO.md §7). The shaders are tools/ue_scripts/make_transporter_fx.py's.

namespace
{
	TAutoConsoleVariable<int32> CVarXFx(TEXT("astra.xport.fx"), 1, TEXT("TELETRASPORTO: 0 draws and plays nothing of the transporter's effects (the rules and the orders do not change)"));
	TAutoConsoleVariable<float> CVarXGain(TEXT("astra.xport.gain"), 1.f, TEXT("TELETRASPORTO: the brightness of every transporter effect (1 as made; the room's exposure may want more or less)"));

	const FTransform& XHiddenXf()
	{
		static const FTransform X(FQuat::Identity, FVector::ZeroVector, FVector(0.0001));
		return X;
	}

	float XSmooth(float A, float B, float X)
	{
		const float T = FMath::Clamp((X - A) / FMath::Max(1.0e-4f, B - A), 0.f, 1.f);
		return T * T * (3.f - 2.f * T);
	}

	/** A hash of three small integers in 0..1 (the same cells light up in the same order every time, whatever the frame rate). */
	float XHash(int32 A, int32 B, int32 S = 0)
	{
		uint32 H = (uint32)A * 374761393u + (uint32)B * 668265263u + (uint32)S * 2246822519u;
		H = (H ^ (H >> 13)) * 1274126177u;
		H ^= H >> 16;
		return (float)(H & 0xFFFFFF) / (float)0x1000000;
	}
}

// ================================================================================================ the layers
namespace AstraXportFx
{
	void FLayer::Init(int32 InCapacity)
	{
		Capacity = InCapacity;
		Xf.SetNumUninitialized(Capacity);
		for (FTransform& T : Xf)
		{
			T = XHiddenXf();
		}
		Data.SetNumZeroed(Capacity * Stride);
		Count = Prev = 0;
	}

	float* FLayer::Next(FTransform*& OutXf)
	{
		if (Count >= Capacity)
		{
			return nullptr;
		}
		OutXf = &Xf[Count];
		float* D = &Data[Count * Stride];
		++Count;
		return D;
	}

	void FLayer::Flush()
	{
		if (UInstancedStaticMeshComponent* C = Comp.Get())
		{
			const int32 N = FMath::Max(Count, Prev);
			if (N > 0)
			{
				for (int32 i = Count; i < Prev; ++i)
				{
					Xf[i] = XHiddenXf();             // what was drawn last frame and is gone now
				}
				C->BatchUpdateInstancesTransforms(0, MakeArrayView(Xf.GetData(), N), false, false, false);
				C->SetCustomData(0, N - 1, MakeArrayView(Data.GetData(), N * Stride), false);
			}
		}
		Prev = Count;
	}
}

using namespace AstraXportFx;

// ================================================================================================ the Captain's screen (a Slate overlay: no material, no render target)
class SAstraXportOverlay : public SLeafWidget
{
public:
	SLATE_BEGIN_ARGS(SAstraXportOverlay) {}
	SLATE_END_ARGS()

	void Construct(const FArguments&)
	{
		SetVisibility(EVisibility::HitTestInvisible);
	}

	float Wash = 0.f;       // 0..1: the white-gold over everything
	float Cells = 0.f;      // 0..1: how many of the cells have turned to light
	float Clock = 0.f;
	float Alpha = 1.f;      // the whole overlay's fade

	virtual FVector2D ComputeDesiredSize(float) const override { return FVector2D(1920.0, 1080.0); }

	virtual int32 OnPaint(const FPaintArgs& Args, const FGeometry& AllottedGeometry, const FSlateRect& MyCullingRect, FSlateWindowElementList& OutDrawElements, int32 LayerId,
	                      const FWidgetStyle& InWidgetStyle, bool bParentEnabled) const override
	{
		const FSlateBrush* Brush = FCoreStyle::Get().GetBrush("GenericWhiteBox");
		const FVector2f Size = FVector2f(AllottedGeometry.GetLocalSize());
		if (Size.X < 8.f || Size.Y < 8.f || Alpha <= 0.002f)
		{
			return LayerId;
		}
		auto Box = [&](float X, float Y, float W, float H, const FLinearColor& Tint)
		{
			FSlateDrawElement::MakeBox(OutDrawElements, LayerId, AllottedGeometry.ToPaintGeometry(FVector2f(W, H), FSlateLayoutTransform(FVector2f(X, Y))), Brush, ESlateDrawEffect::None, Tint);
		};
		// the cells: a lattice over the picture, each turning to light at its own moment, the way a pattern is taken apart cell by cell
		const int32 NumCols = 44;
		const int32 NumRows = FMath::Max(8, FMath::RoundToInt((float)NumCols * Size.Y / Size.X));
		const float CW = Size.X / (float)NumCols, CH = Size.Y / (float)NumRows;
		if (Cells > 0.001f)
		{
			for (int32 j = 0; j < NumRows; ++j)
			{
				for (int32 i = 0; i < NumCols; ++i)
				{
					const float H = XHash(i, j);
					const float Th = 0.04f + 0.82f * H + 0.14f * (1.f - (float)j / (float)NumRows);        // the lower cells go a little earlier: the energy rises
					const float Age = Cells - Th;
					if (Age <= 0.f)
					{
						continue;
					}
					const float Twinkle = 0.78f + 0.22f * FMath::Sin(Clock * (5.f + 9.f * H) + H * 31.f);
					// a cell flashes white as it turns, then settles into gold
					const float Flash = 1.f - XSmooth(0.f, 0.08f, Age);
					const FLinearColor Col = FLinearColor::LerpUsingHSV(FLinearColor(1.f, 0.82f, 0.42f), FLinearColor(1.f, 0.97f, 0.85f), Flash);
					const float A = Alpha * (0.5f * Twinkle + 0.5f * Flash);
					Box((float)i * CW + 1.f, (float)j * CH + 1.f, CW - 2.f, CH - 2.f, FLinearColor(Col.R, Col.G, Col.B, FMath::Clamp(A, 0.f, 1.f) * 0.62f));
				}
			}
			// glitter: points that flash for an instant, more of them as the cells go
			const int32 Glints = (int32)(160.f * Cells);
			for (int32 g = 0; g < Glints; ++g)
			{
				const int32 Slot = (int32)(Clock * 16.f) + g * 7;
				const float X = XHash(g, Slot, 1) * Size.X, Y = XHash(g, Slot, 2) * Size.Y;
				const float S = 2.f + 4.f * XHash(g, Slot, 3);
				Box(X, Y, S, S, FLinearColor(1.f, 0.95f, 0.75f, Alpha * (0.4f + 0.6f * XHash(g, Slot, 4))));
			}
		}
		if (Wash > 0.002f)
		{
			Box(0.f, 0.f, Size.X, Size.Y, FLinearColor(1.f, 0.93f, 0.72f, Alpha * FMath::Min(1.f, Wash) * 0.97f));
		}
		return LayerId + 1;
	}
};

// ================================================================================================ the subsystem's calls
void UAstraTransportFx::Init(UWorld* InWorld)
{
	World = InWorld;
	bReady = World != nullptr && FApp::CanEverRender();
	Pool.SetNum(CapSparkles);
}

void UAstraTransportFx::Shutdown()
{
	for (FColumn& C : Cols)
	{
		DropColumn(C);
	}
	Cols.Reset();
	for (TPair<int32, TObjectPtr<UAudioComponent>>& L : Loops)
	{
		if (L.Value)
		{
			L.Value->Stop();
		}
	}
	Loops.Reset();
	if (Overlay.IsValid())
	{
		if (UGameViewportClient* VC = GEngine ? GEngine->GameViewport : nullptr)
		{
			VC->RemoveViewportWidgetContent(Overlay.ToSharedRef());
		}
		Overlay.Reset();
		bOverlayOn = false;
	}
	if (Host)
	{
		Host->Destroy();
		Host = nullptr;
	}
	SparkleL = FLayer();
	ColumnL = FLayer();
	RingL = FLayer();
	Light = nullptr;
	bLayers = false;
	bReady = false;
}

void UAstraTransportFx::LoadAssets()
{
	bAssetsTried = true;
	SphereMesh = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Sphere.Sphere"));
	CylinderMesh = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cylinder.Cylinder"));
	PlaneMesh = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Plane.Plane"));
	const auto Mat = [](const TCHAR* Name) { return LoadObject<UMaterialInterface>(nullptr, *FString::Printf(TEXT("/Game/ASTRA/Materials/%s.%s"), Name, Name), nullptr, LOAD_Quiet | LOAD_NoWarn); };
	SparkleMat = Mat(TEXT("M_XPORT_Sparkle"));
	ColumnMat = Mat(TEXT("M_XPORT_Column"));
	RingMat = Mat(TEXT("M_XPORT_Ring"));
	GhostMat = Mat(TEXT("M_XPORT_Ghost"));
	if (!(SparkleMat && ColumnMat && RingMat && GhostMat) && !bWarned)
	{
		bWarned = true;
		UE_LOG(LogASTRA, Warning, TEXT("[XportFx] materials missing (%s%s%s%s): what they draw is skipped; run tools/ue_scripts/make_transporter_fx.py in the editor"), SparkleMat ? TEXT("") : TEXT("M_XPORT_Sparkle "),
		       ColumnMat ? TEXT("") : TEXT("M_XPORT_Column "), RingMat ? TEXT("") : TEXT("M_XPORT_Ring "), GhostMat ? TEXT("") : TEXT("M_XPORT_Ghost "));
	}
}

bool UAstraTransportFx::EnsureLayers()
{
	if (bLayers)
	{
		return true;
	}
	if (!bReady || !World)
	{
		return false;
	}
	if (!bAssetsTried)
	{
		LoadAssets();
	}
	if (!SphereMesh || !CylinderMesh || !PlaneMesh)
	{
		return false;
	}
	FActorSpawnParameters P;
	P.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	P.ObjectFlags |= RF_Transient;
	Host = World->SpawnActor<AActor>(AActor::StaticClass(), FTransform::Identity, P);
	if (!Host)
	{
		return false;
	}
	USceneComponent* Root = NewObject<USceneComponent>(Host, TEXT("XportRoot"));
	Host->SetRootComponent(Root);
	Root->SetMobility(EComponentMobility::Movable);
	Root->RegisterComponent();
	auto Make = [this, Root](FLayer& L, const TCHAR* Name, UStaticMesh* Mesh, UMaterialInterface* Mat, int32 Capacity, int32 Sort)
	{
		L.Init(Capacity);
		if (!Mesh || !Mat)
		{
			return;
		}
		UInstancedStaticMeshComponent* C = NewObject<UInstancedStaticMeshComponent>(Host, Name);
		C->SetupAttachment(Root);
		C->SetMobility(EComponentMobility::Movable);
		C->SetStaticMesh(Mesh);
		C->SetMaterial(0, Mat);
		C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		C->bDisableCollision = true;
		C->SetCanEverAffectNavigation(false);
		C->SetGenerateOverlapEvents(false);
		C->SetCastShadow(false);
		C->bCastDynamicShadow = false;
		C->bAffectDynamicIndirectLighting = false;
		C->bAffectDistanceFieldLighting = false;
		C->bNeverDistanceCull = true;
		C->bUseAsOccluder = false;
		C->SetReceivesDecals(false);
		C->SetTranslucentSortPriority(Sort);
		C->SetNumCustomDataFloats(Stride);
		TArray<FTransform> Init;
		Init.Init(XHiddenXf(), Capacity);
		C->AddInstances(Init, false, false, false);
		C->RegisterComponent();
		L.Comp = C;
	};
	Make(RingL, TEXT("XportRings"), PlaneMesh, RingMat, CapRings, -1);
	Make(ColumnL, TEXT("XportColumns"), CylinderMesh, ColumnMat, CapColumns, 1);
	Make(SparkleL, TEXT("XportSparkles"), SphereMesh, SparkleMat, CapSparkles, 2);
	// one soft warm light that follows the columns (no shadows: the room's own lamps do the rest)
	Light = NewObject<UPointLightComponent>(Host, TEXT("XportLight"));
	Light->SetupAttachment(Root);
	Light->SetMobility(EComponentMobility::Movable);
	Light->SetIntensityUnits(ELightUnits::Candelas);
	Light->SetIntensity(0.f);
	Light->SetCastShadows(false);
	Light->SetAttenuationRadius(900.f);
	Light->SetSourceRadius(30.f);
	Light->SetLightColor(FLinearColor(1.f, 0.82f, 0.5f));
	Light->SetVisibility(false);
	Light->RegisterComponent();
	bLayers = true;
	UE_LOG(LogASTRA, Log, TEXT("[XportFx] effects ready (sparkles %d, columns %d, rings %d; materials: %s%s%s%s)"), CapSparkles, CapColumns, CapRings, SparkleMat ? TEXT("sparkle ") : TEXT(""),
	       ColumnMat ? TEXT("column ") : TEXT(""), RingMat ? TEXT("ring ") : TEXT(""), GhostMat ? TEXT("ghost") : TEXT(""));
	return true;
}

// ================================================================================================ columns
int32 UAstraTransportFx::BeginColumn(const FVector& FeetCm, float YawDeg, bool bRematerialize, float Seconds, AActor* Source, float MassKg, bool bCaptain)
{
	FColumn C;
	C.Id = NextId++;
	C.Feet = FeetCm;
	C.Yaw = YawDeg;
	C.bRemat = bRematerialize;
	C.bCaptain = bCaptain;
	C.Seconds = FMath::Max(0.4f, Seconds);
	C.Mass = MassKg;
	C.Source = Source;
	C.Seed = Rng.RandRange(0, 9999);
	// a person: 1.95 m by 0.9 m; a load of cargo is as tall as its mass says (a crate)
	const bool bCargo = Source == nullptr && !bCaptain && MassKg > 120.f;
	C.Height = bCargo ? FMath::Clamp(70.f + MassKg * 0.16f, 90.f, 220.f) : 195.f;
	C.Radius = bCargo ? FMath::Clamp(35.f + MassKg * 0.045f, 40.f, 85.f) : 46.f;
	C.Col = bCaptain ? FLinearColor(1.f, 0.88f, 0.55f) : (bCargo ? FLinearColor(0.8f, 0.95f, 1.f) : FLinearColor(1.f, 0.78f, 0.38f));
	if (bReady && CVarXFx.GetValueOnGameThread() != 0)
	{
		EnsureLayers();
		if (Source && GhostMat && bLayers)
		{
			UMaterialInstanceDynamic* Mid = nullptr;
			USkinnedMeshComponent* Lead = nullptr;
			C.Ghost = MakeGhost(Source, Mid, Lead, FeetCm.Z, C.Height);
			C.GhostMid = Mid;
			C.Leader = Lead;
		}
		if (bRematerialize && Source)
		{
			C.Source = Source;
			HideBody(C, true);                               // the body that is being made stays out of sight until the figure is formed
		}
	}
	Cols.Add(C);
	return C.Id;
}

void UAstraTransportFx::BindSource(int32 Id, AActor* Source)
{
	if (!Source)
	{
		return;
	}
	for (FColumn& C : Cols)
	{
		if (C.Id != Id)
		{
			continue;
		}
		C.Source = Source;
		if (bReady && bLayers && GhostMat && !C.Ghost.IsValid())
		{
			UMaterialInstanceDynamic* Mid = nullptr;
			USkinnedMeshComponent* Lead = nullptr;
			C.Ghost = MakeGhost(Source, Mid, Lead, C.Feet.Z, C.Height);
			C.GhostMid = Mid;
			C.Leader = Lead;
		}
		if (C.bRemat && C.Age < C.Seconds * 0.94f)
		{
			HideBody(C, true);
		}
	}
}

void UAstraTransportFx::ReverseColumn(int32 Id)
{
	for (FColumn& C : Cols)
	{
		if (C.Id == Id && !C.bEnding)
		{
			C.Dir = -1.f;
		}
	}
}

void UAstraTransportFx::EndColumn(int32 Id, bool bNow)
{
	for (FColumn& C : Cols)
	{
		if (C.Id == Id)
		{
			C.bEnding = true;
			if (bNow)
			{
				C.Fade = 0.f;
			}
		}
	}
}

bool UAstraTransportFx::HasColumn(int32 Id) const
{
	return Cols.ContainsByPredicate([Id](const FColumn& C) { return C.Id == Id; });
}

void UAstraTransportFx::HideBody(FColumn& C, bool bHide)
{
	if (AActor* A = C.Source.Get())
	{
		A->SetActorHiddenInGame(bHide);
		C.bBodyHidden = bHide;
	}
}

USkeletalMeshComponent* UAstraTransportFx::MakeGhost(AActor* Source, UMaterialInstanceDynamic*& OutMid, USkinnedMeshComponent*& OutLeader, float FeetZ, float Height)
{
	OutMid = nullptr;
	OutLeader = nullptr;
	if (!Source || !Host || !GhostMat)
	{
		return nullptr;
	}
	// the mesh that is on show: the standing body, else the seated one
	USkinnedMeshComponent* Leader = nullptr;
	TInlineComponentArray<USkeletalMeshComponent*> Skels(Source);
	for (USkeletalMeshComponent* S : Skels)
	{
		if (S && S->GetSkinnedAsset() && S->IsVisible())
		{
			Leader = S;
			break;
		}
	}
	if (!Leader)
	{
		TInlineComponentArray<UPoseableMeshComponent*> Poses(Source);
		for (UPoseableMeshComponent* P : Poses)
		{
			if (P && P->GetSkinnedAsset() && P->IsVisible())
			{
				Leader = P;
				break;
			}
		}
	}
	if (!Leader)
	{
		return nullptr;
	}
	USkeletalMeshComponent* G = NewObject<USkeletalMeshComponent>(Host, NAME_None, RF_Transient);
	G->SetupAttachment(Host->GetRootComponent());
	G->SetSkinnedAssetAndUpdate(Leader->GetSkinnedAsset());
	G->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	G->SetCastShadow(false);
	G->SetReceivesDecals(false);
	G->bNeverDistanceCull = true;
	G->RegisterComponent();
	G->SetWorldTransform(Leader->GetComponentTransform());
	G->SetLeaderPoseComponent(Leader);
	UMaterialInstanceDynamic* Mid = UMaterialInstanceDynamic::Create(GhostMat, this);
	Mid->SetScalarParameterValue(TEXT("FeetZ"), FeetZ);
	Mid->SetScalarParameterValue(TEXT("Height"), Height);
	Mid->SetScalarParameterValue(TEXT("Prog"), 0.f);
	Mid->SetScalarParameterValue(TEXT("Gain"), 0.f);
	for (int32 i = 0; i < G->GetNumMaterials(); ++i)
	{
		G->SetMaterial(i, Mid);
	}
	OutMid = Mid;
	OutLeader = Leader;
	return G;
}

void UAstraTransportFx::DropColumn(FColumn& C)
{
	if (USkeletalMeshComponent* G = C.Ghost.Get())
	{
		G->DestroyComponent();
	}
	C.Ghost = nullptr;
	// a figure that was being made is there for good, and a dematerialization that ran back leaves the body as it was; one that went through leaves it to VITA, who has let it go
	if (C.bBodyHidden && (C.bRemat || C.Dir < 0.f))
	{
		HideBody(C, false);
	}
}

void UAstraTransportFx::Emit(FColumn& C, float Prog, float Dt)
{
	if (!SparkleL.Comp.IsValid())
	{
		return;
	}
	C.Emit += 52.f * C.Fade * Dt;
	while (C.Emit >= 1.f)
	{
		C.Emit -= 1.f;
		const float A = Rng.FRand() * 2.f * PI;
		const float R = C.Radius * FMath::Sqrt(Rng.FRand()) * (C.bRemat ? 1.8f : 0.95f);
		const float Front = Prog * C.Height;
		const float Z = C.bRemat ? FMath::Clamp(Front + Rng.FRandRange(-20.f, 70.f), 0.f, C.Height + 40.f) : FMath::Clamp(Front + Rng.FRandRange(-45.f, 18.f), 0.f, C.Height);
		const FVector At = C.Feet + FVector(FMath::Cos(A) * R, FMath::Sin(A) * R, Z);
		const FLinearColor Col = FLinearColor::LerpUsingHSV(C.Col, FLinearColor(0.78f, 0.92f, 1.f), Rng.FRand() * 0.55f);
		const float Life = Rng.FRandRange(0.7f, 1.4f);
		FVector Vel;
		if (C.bRemat)
		{
			// they gather: from outside the column toward the front, quickly, and settle
			const FVector To = C.Feet + FVector(0.f, 0.f, FMath::Clamp(Front, 10.f, C.Height));
			Vel = (To - At) / Life * 0.9f;
		}
		else
		{
			Vel = FVector(Rng.FRandRange(-12.f, 12.f), Rng.FRandRange(-12.f, 12.f), Rng.FRandRange(55.f, 150.f));
		}
		SpawnSparkle(At, Vel, Life, Rng.FRandRange(1.4f, 3.6f), Col, Rng.FRandRange(3.5f, 7.f));
		FSparkle& S = Pool[(NextSparkle + CapSparkles - 1) % CapSparkles];
		S.Swirl = FVector(C.Feet.X, C.Feet.Y, Rng.FRandRange(-2.6f, 2.6f));
	}
}

void UAstraTransportFx::SpawnSparkle(const FVector& At, const FVector& Vel, float Life, float Size, const FLinearColor& Col, float Inten)
{
	if (Pool.Num() != CapSparkles)
	{
		Pool.SetNum(CapSparkles);
	}
	FSparkle& S = Pool[NextSparkle];
	NextSparkle = (NextSparkle + 1) % CapSparkles;
	S.Pos = At;
	S.Vel = Vel;
	S.Swirl = FVector::ZeroVector;
	S.Age = 0.f;
	S.Life = Life;
	S.Size = Size;
	S.Col = Col;
	S.Inten = Inten;
	S.Seed = Rng.FRand();
	S.bLive = true;
}

void UAstraTransportFx::StepColumns(float Dt)
{
	for (int32 i = Cols.Num() - 1; i >= 0; --i)
	{
		FColumn& C = Cols[i];
		C.Age = FMath::Clamp(C.Age + Dt * C.Dir, 0.f, C.Seconds);
		const float P = C.Age / C.Seconds;
		if ((C.Dir > 0.f && C.Age >= C.Seconds) || (C.Dir < 0.f && C.Age <= 0.f))
		{
			C.bEnding = true;
		}
		if (C.bEnding)
		{
			C.Fade = FMath::Max(0.f, C.Fade - Dt / 0.5f);
		}
		// the body: out of sight under the figure of light once the figure has begun; back in sight when a figure is complete
		if (AActor* A = C.Source.Get())
		{
			if (!C.bRemat && C.Dir > 0.f && P >= 0.06f && !C.bEnding && !A->IsHidden())
			{
				HideBody(C, true);
			}
			if (C.bRemat && C.Dir > 0.f && P >= 0.94f && C.bBodyHidden)
			{
				HideBody(C, false);
				if (USkeletalMeshComponent* G = C.Ghost.Get())
				{
					G->DestroyComponent();
					C.Ghost = nullptr;
				}
			}
			else if (C.bRemat && C.bBodyHidden && !A->IsHidden())
			{
				HideBody(C, true);                           // (VITA showed it: it stays out of sight until the figure is formed)
			}
		}
		if (USkeletalMeshComponent* G = C.Ghost.Get())
		{
			if (USkinnedMeshComponent* Lead = C.Leader.Get())
			{
				G->SetWorldTransform(Lead->GetComponentTransform());
			}
			if (UMaterialInstanceDynamic* M = C.GhostMid.Get())
			{
				M->SetScalarParameterValue(TEXT("Prog"), P);
				M->SetScalarParameterValue(TEXT("Dir"), C.bRemat ? -1.f : 1.f);
				M->SetScalarParameterValue(TEXT("Gain"), CVarXGain.GetValueOnGameThread() * C.Fade);
				M->SetVectorParameterValue(TEXT("Col"), C.Col);
			}
		}
		if (!C.bEnding || C.Fade > 0.f)
		{
			Emit(C, P, Dt);
		}
		if (C.bEnding && C.Fade <= 0.f)
		{
			DropColumn(C);
			Cols.RemoveAtSwap(i);
		}
	}
}

void UAstraTransportFx::StepSparkles(float Dt)
{
	int32 Live = 0;
	for (FSparkle& S : Pool)
	{
		if (!S.bLive)
		{
			continue;
		}
		S.Age += Dt;
		if (S.Age >= S.Life)
		{
			S.bLive = false;
			continue;
		}
		S.Pos += S.Vel * Dt;
		S.Vel *= FMath::Max(0.f, 1.f - 0.9f * Dt);
		if (!FMath::IsNearlyZero(S.Swirl.Z))
		{
			const FVector2D Rel(S.Pos.X - S.Swirl.X, S.Pos.Y - S.Swirl.Y);
			const float Ang = S.Swirl.Z * Dt, Cs = FMath::Cos(Ang), Sn = FMath::Sin(Ang);
			S.Pos.X = S.Swirl.X + Rel.X * Cs - Rel.Y * Sn;
			S.Pos.Y = S.Swirl.Y + Rel.X * Sn + Rel.Y * Cs;
		}
		++Live;
	}
	NumLive = Live;
}

// ================================================================================================ pads, the emitter, the light
void UAstraTransportFx::SetPadLook(int32 PadIndex, const FVector& PosCm, float RadiusCm, EAstraPadLook Look)
{
	if (PadIndex < 0 || PadIndex >= CapRings)
	{
		return;
	}
	if (PadList.Num() <= PadIndex)
	{
		PadList.SetNum(PadIndex + 1);
	}
	FPadFx& P = PadList[PadIndex];
	bPadsDirty |= !P.bSet || P.Look != Look || !P.Pos.Equals(PosCm, 0.5);
	P.Pos = PosCm;
	P.Radius = RadiusCm;
	P.Look = Look;
	P.bSet = true;
}

void UAstraTransportFx::ClearPads()
{
	PadList.Reset();
}

void UAstraTransportFx::SetEmitter(const FVector& CentreCm, float Glow)
{
	EmitterCm = CentreCm;
	EmitterGlow = Glow;
}

void UAstraTransportFx::StepPads(float Dt)
{
	EmitterShown += (EmitterGlow - EmitterShown) * FMath::Min(1.f, Dt * 4.f);
}

void UAstraTransportFx::StepLight(float Dt)
{
	if (!Light)
	{
		return;
	}
	FVector At = EmitterCm + FVector(0.0, 0.0, -80.0);
	float Level = EmitterShown * 0.12f;
	for (const FColumn& C : Cols)
	{
		const float P = C.Age / C.Seconds;
		const float Env = XSmooth(0.f, 0.15f, P) * (1.f - XSmooth(0.85f, 1.f, P)) * C.Fade;
		if (Env > Level)
		{
			Level = Env;
			At = C.Feet + FVector(0.0, 0.0, C.Height * 0.55f);
		}
	}
	const float Target = 2600.f * Level * CVarXGain.GetValueOnGameThread();
	const float Now = Light->Intensity;
	const float New = Now + (Target - Now) * FMath::Min(1.f, Dt * 10.f);
	Light->SetIntensity(New);
	Light->SetVisibility(New > 4.f);
	if (New > 4.f)
	{
		Light->SetWorldLocation(At);
	}
}

// ================================================================================================ writing the instances
void UAstraTransportFx::WriteInstances()
{
	const float Gain = CVarXGain.GetValueOnGameThread();
	if (RingL.Comp.IsValid())
	{
		RingL.Begin();
		static const FLinearColor RingCols[6] = {FLinearColor(0.18f, 0.5f, 0.9f), FLinearColor(0.35f, 0.8f, 1.f), FLinearColor(1.f, 0.7f, 0.2f), FLinearColor(0.5f, 1.f, 0.7f),
		                                         FLinearColor(1.f, 0.9f, 0.6f), FLinearColor(1.f, 0.2f, 0.12f)};
		static const float RingInten[6] = {0.7f, 1.6f, 2.6f, 2.8f, 4.5f, 3.2f};
		for (const FPadFx& P : PadList)
		{
			if (!P.bSet)
			{
				continue;
			}
			FTransform* Xf = nullptr;
			float* D = RingL.Next(Xf);
			if (!D)
			{
				break;
			}
			const int32 L = (int32)P.Look;
			*Xf = FTransform(FQuat::Identity, P.Pos + FVector(0.0, 0.0, 1.4), FVector(P.Radius / 50.f, P.Radius / 50.f, 1.f));
			D[0] = RingCols[L].R; D[1] = RingCols[L].G; D[2] = RingCols[L].B;
			D[3] = RingInten[L] * Gain;
			D[4] = 0.f;
			D[5] = (float)L;
			D[6] = 1.f;
			D[7] = XHash((int32)P.Pos.X, (int32)P.Pos.Y);
		}
		RingL.Flush();
	}
	if (ColumnL.Comp.IsValid())
	{
		ColumnL.Begin();
		for (const FColumn& C : Cols)
		{
			FTransform* Xf = nullptr;
			float* D = ColumnL.Next(Xf);
			if (!D)
			{
				break;
			}
			*Xf = FTransform(FQuat::Identity, C.Feet + FVector(0.0, 0.0, C.Height * 0.5f), FVector(C.Radius / 50.f, C.Radius / 50.f, C.Height / 100.f));
			const float P = C.Age / C.Seconds;
			D[0] = C.Col.R; D[1] = C.Col.G; D[2] = C.Col.B;
			D[3] = 2.4f * Gain;
			D[4] = P;
			D[5] = C.bRemat ? -1.f : 1.f;
			D[6] = C.Fade * XSmooth(0.f, 0.1f, P) * (1.f - XSmooth(0.9f, 1.f, P) * 0.6f);
			D[7] = (float)C.Seed * 0.0001f;
		}
		ColumnL.Flush();
	}
	if (SparkleL.Comp.IsValid())
	{
		SparkleL.Begin();
		for (const FSparkle& S : Pool)
		{
			if (!S.bLive)
			{
				continue;
			}
			FTransform* Xf = nullptr;
			float* D = SparkleL.Next(Xf);
			if (!D)
			{
				break;
			}
			*Xf = FTransform(FQuat::Identity, S.Pos, FVector(S.Size / 100.f));
			D[0] = S.Col.R; D[1] = S.Col.G; D[2] = S.Col.B;
			D[3] = S.Inten * Gain;
			D[4] = S.Age / S.Life;
			D[5] = 0.f;
			D[6] = 1.f;
			D[7] = S.Seed;
		}
		// the emitter's glow over the dais: one soft sphere
		if (EmitterShown > 0.02f)
		{
			FTransform* Xf = nullptr;
			if (float* D = SparkleL.Next(Xf))
			{
				*Xf = FTransform(FQuat::Identity, EmitterCm, FVector((28.f + 40.f * EmitterShown) / 100.f));
				D[0] = 0.55f; D[1] = 0.85f; D[2] = 1.f;
				D[3] = (0.4f + 3.2f * EmitterShown) * Gain;
				D[4] = 0.3f;
				D[5] = 0.f;
				D[6] = 1.f;
				D[7] = 0.5f;
			}
		}
		SparkleL.Flush();
	}
	EmitterWritten = EmitterShown;
	bPadsDirty = false;
}

// ================================================================================================ the Captain's screen
void UAstraTransportFx::BeginCaptainView(bool bRematerialize, float Seconds)
{
	bViewActive = true;
	bViewEnding = false;
	bViewRemat = bRematerialize;
	ViewSeconds = FMath::Max(0.4f, Seconds);
	ViewAge = 0.f;
	ViewDir = 1.f;
	if (bRematerialize)
	{
		ViewHold = 1.f;
		ViewShown = 1.f;
	}
}

void UAstraTransportFx::ReverseCaptainView()
{
	ViewDir = -1.f;
}

void UAstraTransportFx::EndCaptainView()
{
	bViewEnding = true;
}

void UAstraTransportFx::HoldCaptainView(float Level01)
{
	ViewHold = FMath::Clamp(Level01, 0.f, 1.f);
	if (ViewHold > 0.f)
	{
		bViewActive = true;
		bViewEnding = false;
	}
}

void UAstraTransportFx::StepOverlay(float Dt)
{
	if (!bViewActive && !bOverlayOn)
	{
		return;
	}
	UGameViewportClient* VC = GEngine ? GEngine->GameViewport : nullptr;
	if (!VC || !FSlateApplication::IsInitialized())
	{
		bViewActive = false;
		return;
	}
	if (bViewActive)
	{
		ViewAge = FMath::Clamp(ViewAge + Dt * ViewDir, 0.f, ViewSeconds);
	}
	const float P = ViewAge / ViewSeconds;
	float Wash = 0.f, Cells = 0.f;
	if (bViewActive)
	{
		if (!bViewRemat)
		{
			Cells = XSmooth(0.f, 1.f, P);
			Wash = XSmooth(0.55f, 1.f, P);
		}
		else
		{
			Cells = 1.f - XSmooth(0.2f, 1.f, P);
			Wash = 1.f - XSmooth(0.f, 0.55f, P);
		}
		Wash = FMath::Max(Wash, ViewHold);
		if (ViewHold > 0.f && !bViewRemat)
		{
			Cells = 1.f;
		}
		// a dematerialization that ran back is over when it is at its start; a recomposition when it has cleared
		if (ViewDir < 0.f && ViewAge <= 0.f)
		{
			bViewActive = false;
			bViewEnding = true;
		}
		else if (bViewRemat && ViewAge >= ViewSeconds && ViewDir > 0.f)
		{
			bViewActive = false;
			bViewEnding = true;
			ViewHold = 0.f;
		}
	}
	if (bViewEnding)
	{
		ViewShown = FMath::Max(0.f, ViewShown - Dt / 0.45f);
		if (ViewShown <= 0.f && !bViewActive)
		{
			if (Overlay.IsValid())
			{
				VC->RemoveViewportWidgetContent(Overlay.ToSharedRef());
				Overlay.Reset();
			}
			bOverlayOn = false;
			bViewEnding = false;
			return;
		}
	}
	else
	{
		ViewShown = FMath::Min(1.f, ViewShown + Dt / 0.15f);
	}
	if (!Overlay.IsValid())
	{
		Overlay = SNew(SAstraXportOverlay);
		VC->AddViewportWidgetContent(Overlay.ToSharedRef(), 70);
		bOverlayOn = true;
	}
	Overlay->Wash = Wash;
	Overlay->Cells = Cells;
	Overlay->Clock = (float)Clock;
	Overlay->Alpha = FMath::Clamp(ViewShown, 0.f, 1.f);
}

// ================================================================================================ sound
USoundBase* UAstraTransportFx::SoundFor(const TCHAR* Id)
{
	const FName Key(Id);
	if (const TObjectPtr<USoundBase>* Found = Sounds.Find(Key))
	{
		return *Found;
	}
	USoundBase* S = LoadObject<USoundBase>(nullptr, *FString::Printf(TEXT("/Game/ASTRA/Audio/Transporter/SW_Xport_%s.SW_Xport_%s"), Id, Id), nullptr, LOAD_Quiet | LOAD_NoWarn);
	Sounds.Add(Key, S);
	return S;
}

void UAstraTransportFx::PlaySound(const TCHAR* Id, const FVector& AtCm, float Volume, float Pitch)
{
	if (!bReady || !World || CVarXFx.GetValueOnGameThread() == 0)
	{
		return;
	}
	USoundBase* S = SoundFor(Id);
	if (!S)
	{
		return;
	}
	if (!Attenuation)
	{
		Attenuation = NewObject<USoundAttenuation>(this);
		Attenuation->Attenuation.bAttenuate = true;
		Attenuation->Attenuation.bSpatialize = true;
		Attenuation->Attenuation.AttenuationShape = EAttenuationShape::Sphere;
		Attenuation->Attenuation.DistanceAlgorithm = EAttenuationDistanceModel::NaturalSound;
		Attenuation->Attenuation.AttenuationShapeExtents = FVector(900.f);
		Attenuation->Attenuation.FalloffDistance = 2400.f;
		Attenuation->Attenuation.dBAttenuationAtMax = -24.f;
	}
	UGameplayStatics::PlaySoundAtLocation(World, S, AtCm, FRotator::ZeroRotator, Volume, Pitch, 0.f, Attenuation);
}

int32 UAstraTransportFx::StartLoop(const TCHAR* Id, const FVector& AtCm, float Volume)
{
	const int32 Handle = NextLoop++;
	if (!bReady || !World || CVarXFx.GetValueOnGameThread() == 0)
	{
		return Handle;
	}
	if (USoundBase* S = SoundFor(Id))
	{
		if (!Attenuation)
		{
			PlaySound(TEXT("Lock"), AtCm, 0.f, 1.f);              // (makes the attenuation; a silent call)
		}
		if (UAudioComponent* A = UGameplayStatics::SpawnSoundAtLocation(World, S, AtCm, FRotator::ZeroRotator, Volume, 1.f, 0.f, Attenuation, nullptr, false))
		{
			Loops.Add(Handle, A);
		}
	}
	return Handle;
}

void UAstraTransportFx::StopLoop(int32 Id, float FadeS)
{
	if (TObjectPtr<UAudioComponent>* L = Loops.Find(Id))
	{
		if (UAudioComponent* A = L->Get())
		{
			A->FadeOut(FMath::Max(0.05f, FadeS), 0.f);
		}
		Loops.Remove(Id);
	}
}

// ================================================================================================ the frame
void UAstraTransportFx::Tick(float Dt, const FVector& CaptainEyeCm)
{
	(void)CaptainEyeCm;
	if (!bReady)
	{
		return;
	}
	if (CVarXFx.GetValueOnGameThread() == 0)
	{
		if (Cols.Num() || bViewActive)
		{
			for (FColumn& C : Cols)
			{
				DropColumn(C);
			}
			Cols.Reset();
			bViewActive = false;
			bViewEnding = true;
			ViewShown = 0.f;
		}
		return;
	}
	Clock += Dt;
	StepColumns(Dt);
	StepSparkles(Dt);
	StepPads(Dt);
	if (!bLayers && PadList.Num() > 0)
	{
		EnsureLayers();                                      // the pads' rings are there from the start
	}
	if (bLayers)
	{
		StepLight(Dt);
		const bool bBusy = Cols.Num() > 0 || NumLive > 0;
		if (bBusy || bWasBusy || bPadsDirty || FMath::Abs(EmitterShown - EmitterWritten) > 0.004f)
		{
			WriteInstances();                               // (idle, nothing moves: nothing is written)
		}
		bWasBusy = bBusy;
	}
	StepOverlay(Dt);
}

FString UAstraTransportFx::Describe() const
{
	return FString::Printf(TEXT("%s: %d columns, %d sparkles, %d pads, overlay %s"), bLayers ? TEXT("drawing") : (bReady ? TEXT("ready, nothing drawn yet") : TEXT("off (headless)")), Cols.Num(), NumLive, PadList.Num(),
	                       bOverlayOn ? TEXT("on") : TEXT("off"));
}
