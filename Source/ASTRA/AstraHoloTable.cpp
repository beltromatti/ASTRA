// ASTRA — holographic tactical plot.

#include "AstraHoloTable.h"

#include "AstraBattleSubsystem.h"
#include "Camera/PlayerCameraManager.h"
#include "Components/StaticMeshComponent.h"
#include "Components/TextRenderComponent.h"
#include "Engine/StaticMesh.h"
#include "Kismet/GameplayStatics.h"
#include "Materials/MaterialInstanceDynamic.h"

namespace
{
	const FLinearColor ColAstra(0.22f, 0.72f, 1.f);
	const FLinearColor ColAquila(0.62f, 0.95f, 1.f);
	const FLinearColor ColHostile(1.f, 0.2f, 0.08f);
	const FLinearColor ColHolding(1.f, 0.62f, 0.12f);
	const FLinearColor ColNeutral(0.95f, 0.88f, 0.45f);
	const FLinearColor ColUnknown(0.62f, 0.66f, 0.7f);
	const float RangeLadderKm[] = {5.f, 10.f, 15.f, 20.f, 30.f, 40.f, 60.f, 80.f, 120.f, 160.f};

	FLinearColor BlipColor(const FAstraHoloBlip& B)
	{
		if (B.bPlayer) { return ColAquila; }
		if (B.bUnknown) { return ColUnknown; }
		if (B.Side == EAstraSide::Astra) { return ColAstra; }
		if (B.bHostile) { return B.bHoldFire ? ColHolding : ColHostile; }
		return B.Side == EAstraSide::Mandate ? ColHostile * 0.8f : ColNeutral;
	}

	FString RangeText(float Km)
	{
		return Km < 10.f ? FString::Printf(TEXT("%.1f km"), Km) : FString::Printf(TEXT("%.0f km"), Km);
	}
}

AAstraHoloTable::AAstraHoloTable()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.TickGroup = TG_PostUpdateWork;   // after the battle has moved everything this frame
	Root = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	SetRootComponent(Root);
}

void AAstraHoloTable::BeginPlay()
{
	Super::BeginPlay();
	ShipMesh = LoadObject<UStaticMesh>(nullptr, TEXT("/Game/ASTRA/Holo/SM_HOLO_Ship.SM_HOLO_Ship"));
	UnknownMesh = LoadObject<UStaticMesh>(nullptr, TEXT("/Game/ASTRA/Holo/SM_HOLO_Unknown.SM_HOLO_Unknown"));
	RingMesh = LoadObject<UStaticMesh>(nullptr, TEXT("/Game/ASTRA/Holo/SM_HOLO_Ring.SM_HOLO_Ring"));
	DiscMesh = LoadObject<UStaticMesh>(nullptr, TEXT("/Game/ASTRA/Holo/SM_HOLO_Disc.SM_HOLO_Disc"));
	LineMesh = LoadObject<UStaticMesh>(nullptr, TEXT("/Game/ASTRA/Holo/SM_HOLO_Line.SM_HOLO_Line"));
	SphereMesh = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Sphere.Sphere"));
	HoloMat = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/ASTRA/Materials/M_ASTRA_Holo.M_ASTRA_Holo"));
	GridMat = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/ASTRA/Materials/M_ASTRA_HoloGrid.M_ASTRA_HoloGrid"));
	TextMat = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/ASTRA/Materials/M_ASTRA_HoloText.M_ASTRA_HoloText"));

	// the projector disc on the table top
	Disc = NewObject<UStaticMeshComponent>(this, TEXT("HoloDisc"));
	Disc->SetupAttachment(Root);
	Disc->RegisterComponent();
	Disc->SetStaticMesh(DiscMesh);
	Disc->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Disc->SetCastShadow(false);
	Disc->SetMaterial(0, GridMat);
	Disc->SetRelativeLocation(FVector(0, 0, 1.5f));
	Disc->SetRelativeScale3D(FVector(PlotRadius / 100.f, PlotRadius / 100.f, 1.f));

	// three range rings on the tactical plane, with their distances
	for (int32 i = 0; i < 3; ++i)
	{
		UStaticMeshComponent* R = Pooled(Rings, i, RingMesh);
		SetColor(R, ColAstra, i == 0 ? 10.f : 5.f);
		UTextRenderComponent* T = PooledText(RingLabels, i);
		T->SetWorldSize(2.6f);
		T->SetTextRenderColor(FColor(120, 200, 255));
	}
}

UStaticMeshComponent* AAstraHoloTable::Pooled(TArray<TObjectPtr<UStaticMeshComponent>>& Pool, int32 Index, UStaticMesh* Mesh)
{
	while (Pool.Num() <= Index)
	{
		UStaticMeshComponent* C = NewObject<UStaticMeshComponent>(this);
		C->SetupAttachment(Root);
		C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		C->SetCastShadow(false);
		C->SetMobility(EComponentMobility::Movable);
		C->RegisterComponent();
		C->SetStaticMesh(Mesh);
		C->CreateDynamicMaterialInstance(0, HoloMat);
		Pool.Add(C);
	}
	UStaticMeshComponent* C = Pool[Index];
	if (C->GetStaticMesh() != Mesh)
	{
		C->SetStaticMesh(Mesh);
		C->CreateDynamicMaterialInstance(0, HoloMat);
	}
	C->SetVisibility(true);
	return C;
}

UTextRenderComponent* AAstraHoloTable::PooledText(TArray<TObjectPtr<UTextRenderComponent>>& Pool, int32 Index)
{
	while (Pool.Num() <= Index)
	{
		UTextRenderComponent* T = NewObject<UTextRenderComponent>(this);
		T->SetupAttachment(Root);
		T->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		T->SetCastShadow(false);
		T->RegisterComponent();
		T->SetTextMaterial(TextMat);
		T->SetHorizontalAlignment(EHTA_Center);
		T->SetVerticalAlignment(EVRTA_TextBottom);
		T->SetWorldSize(3.f);
		Pool.Add(T);
	}
	Pool[Index]->SetVisibility(true);
	return Pool[Index];
}

void AAstraHoloTable::HideFrom(TArray<TObjectPtr<UStaticMeshComponent>>& Pool, int32 Index)
{
	for (int32 i = Index; i < Pool.Num(); ++i)
	{
		Pool[i]->SetVisibility(false);
	}
}

void AAstraHoloTable::HideTextFrom(TArray<TObjectPtr<UTextRenderComponent>>& Pool, int32 Index)
{
	for (int32 i = Index; i < Pool.Num(); ++i)
	{
		Pool[i]->SetVisibility(false);
	}
}

void AAstraHoloTable::SetColor(UStaticMeshComponent* C, const FLinearColor& Color, float Intensity)
{
	if (UMaterialInstanceDynamic* M = Cast<UMaterialInstanceDynamic>(C->GetMaterial(0)))
	{
		M->SetVectorParameterValue(TEXT("Color"), Color);
		M->SetScalarParameterValue(TEXT("Intensity"), Intensity);
	}
}

float AAstraHoloTable::PlotRadiusOf(float Km) const
{
	const float D0 = RangeKm / 12.f;
	return PlotRadius * FMath::Loge(1.f + Km / D0) / FMath::Loge(1.f + RangeKm / D0);
}

FVector AAstraHoloTable::PlotPoint(const FVector& RelCm) const
{
	const float Km = RelCm.Size() / 100000.f;
	if (Km < 1e-4f)
	{
		return FVector(0, 0, PlaneHeight);
	}
	FVector P = RelCm / RelCm.Size() * FMath::Min(PlotRadiusOf(Km), PlotRadius);   // beyond the range: pinned to the rim
	P.Z = FMath::Clamp(P.Z, -MaxDepth, MaxDepth);
	return P + FVector(0, 0, PlaneHeight);
}

void AAstraHoloTable::FaceViewer(USceneComponent* C, const FVector& ViewerLocal) const
{
	const FVector D = ViewerLocal - C->GetRelativeLocation();
	C->SetRelativeRotation(FRotator(0.f, FMath::RadiansToDegrees(FMath::Atan2(D.Y, D.X)), 0.f));
}

void AAstraHoloTable::Tick(float DeltaTime)
{
	Super::Tick(DeltaTime);
	Time += DeltaTime;
	const UAstraBattleSubsystem* Battle = GetWorld() ? GetWorld()->GetSubsystem<UAstraBattleSubsystem>() : nullptr;
	TArray<FAstraHoloBlip> Blips;
	if (Battle)
	{
		Battle->GetHoloBlips(Blips);
	}

	// zoom to keep every ship that matters on the table (up to 160 km)
	float Far = 4.f;
	for (const FAstraHoloBlip& B : Blips)
	{
		if (B.Kind == 0 && !B.bPlayer && B.RangeKm < 160.f)
		{
			Far = FMath::Max(Far, B.RangeKm * 1.05f);
		}
	}
	TargetRangeKm = RangeLadderKm[UE_ARRAY_COUNT(RangeLadderKm) - 1];
	for (float R : RangeLadderKm)
	{
		if (R >= Far)
		{
			TargetRangeKm = R;
			break;
		}
	}
	RangeKm = FMath::Exp(FMath::FInterpTo(FMath::Loge(RangeKm), FMath::Loge(TargetRangeKm), DeltaTime, 1.8f));

	FVector ViewerLocal = FVector(-300.f, 0.f, 170.f);
	if (const APlayerCameraManager* Cam = UGameplayStatics::GetPlayerCameraManager(this, 0))
	{
		ViewerLocal = GetActorTransform().InverseTransformPosition(Cam->GetCameraLocation());
	}

	// range rings: the plotted range, half and quarter
	for (int32 i = 0; i < 3; ++i)
	{
		const float Km = TargetRangeKm / float(1 << (2 * i));   // range, a quarter, a sixteenth (log scale)
		const float R = PlotRadiusOf(Km);
		UStaticMeshComponent* Ring = Rings[i];
		Ring->SetVisibility(R <= PlotRadius * 1.01f);
		Ring->SetRelativeLocation(FVector(0, 0, PlaneHeight));
		Ring->SetRelativeScale3D(FVector(R / 100.f, R / 100.f, 1.f));
		UTextRenderComponent* T = RingLabels[i];
		T->SetVisibility(R <= PlotRadius * 1.01f);
		const float A = FMath::DegreesToRadians(-38.f);
		T->SetRelativeLocation(FVector(R * FMath::Cos(A), R * FMath::Sin(A), PlaneHeight + 0.8f));
		T->SetText(FText::FromString(RangeText(Km)));
		FaceViewer(T, ViewerLocal);
	}

	int32 NI = 0, NL = 0, ND = 0, NB = 0;
	TArray<FVector4> PlacedLabels;
	// the viewer's picture plane (for label decluttering), seen from the player towards the table centre
	const FVector ViewDir = (FVector(0, 0, PlaneHeight) - ViewerLocal).GetSafeNormal();
	const FVector ViewRight = FVector::CrossProduct(FVector::UpVector, ViewDir).GetSafeNormal();
	const FVector ViewUp0 = FVector::CrossProduct(ViewDir, ViewRight).GetSafeNormal();
	const FVector ViewUp = ViewUp0.Z < 0.f ? -ViewUp0 : ViewUp0;
	const float Pulse = 0.75f + 0.25f * FMath::Sin(Time * 6.f);
	for (const FAstraHoloBlip& B : Blips)
	{
		const FVector P = PlotPoint(B.Rel);
		const bool bBeyond = B.Rel.Size() / 100000.f > RangeKm * 1.02f;
		if (B.Kind == 0)
		{
			const FLinearColor Col = BlipColor(B);
			const float Base = (B.bPlayer ? 32.f : 24.f) * (bBeyond ? 0.45f : 1.f) * (B.bRetreating ? 0.6f : 1.f) * (B.bTargeted ? Pulse * 1.5f : 1.f);
			const float Size = (B.bPlayer ? 11.f : 9.f) * B.Size;
			UStaticMeshComponent* Icon = Pooled(Icons, NI, B.bUnknown ? UnknownMesh.Get() : ShipMesh.Get());
			Icon->SetRelativeLocationAndRotation(P, B.bUnknown ? FRotator(0.f, Time * 40.f, 0.f) : B.Rot.Rotator());
			Icon->SetRelativeScale3D(FVector(Size / 100.f));
			SetColor(Icon, Col, Base);

			// drop line to the plane (depth cue)
			const float Dz = P.Z - PlaneHeight;
			UStaticMeshComponent* Stem = Pooled(Stems, NI, LineMesh);
			Stem->SetVisibility(FMath::Abs(Dz) > 0.6f);
			Stem->SetRelativeLocationAndRotation(FVector(P.X, P.Y, PlaneHeight), FRotator(Dz > 0.f ? 90.f : -90.f, 0.f, 0.f));
			Stem->SetRelativeScale3D(FVector(FMath::Max(FMath::Abs(Dz), 0.1f) / 100.f, 0.15f, 0.15f));
			SetColor(Stem, Col, 5.f);

			// velocity vector: 500 m/s = 12 cm
			UStaticMeshComponent* Vec = Pooled(Vectors, NI, LineMesh);
			const float L = FMath::Clamp(B.Speed / 500.f * 12.f, 0.f, 24.f);
			Vec->SetVisibility(L > 0.8f && !B.VelDir.IsNearlyZero());
			Vec->SetRelativeLocationAndRotation(P, B.VelDir.Rotation());
			Vec->SetRelativeScale3D(FVector(L / 100.f, 0.18f, 0.18f));
			SetColor(Vec, Col, 7.f);
			++NI;

			UTextRenderComponent* T = PooledText(Labels, NL++);
			const FString Title = B.bPlayer ? FString(TEXT("ASN AQUILA"))
			                    : (B.Name.IsEmpty() ? FString::Printf(TEXT("%s  UNKNOWN"), *B.Contact) : FString::Printf(TEXT("%s  %s"), *B.Name.ToUpper(), *B.Contact));
			FString Sub = B.bPlayer ? FString() : RangeText(B.RangeKm);
			if (B.bHoldFire) { Sub += TEXT("  HOLDING FIRE"); }
			else if (B.bRetreating) { Sub += TEXT("  WITHDRAWING"); }
			if (B.bTargeted) { Sub += TEXT("  [TARGET]"); }
			T->SetText(FText::FromString(Sub.IsEmpty() ? Title : Title + TEXT("<br>") + Sub));
			T->SetTextRenderColor(Col.ToFColor(true));
			T->SetWorldSize(B.bPlayer ? 3.6f : 3.2f);   // (WS below)
			// declutter in the viewer's picture plane: a label that would cover another climbs just above it
			const float WS = B.bPlayer ? 3.6f : 3.2f;
			const float W = FMath::Max(Title.Len(), Sub.Len()) * WS * 0.52f;
			const float H = (Sub.IsEmpty() ? 1.f : 2.f) * WS * 1.05f;
			const FVector Anchor = P + FVector(0, 0, Size * 0.3f + 1.2f);
			FVector LabelPos = Anchor;
			for (int32 Pass = 0; Pass < 6; ++Pass)
			{
				bool bClash = false;
				const float X = FVector::DotProduct(LabelPos, ViewRight), Y = FVector::DotProduct(LabelPos, ViewUp);
				for (const FVector4& Q : PlacedLabels)   // x, y, w, h in the picture plane
				{
					if (FMath::Abs(X - Q.X) < (W + Q.Z) * 0.5f && Y < Q.Y + Q.W && Y + H > Q.Y)
					{
						LabelPos.Z += (Q.Y + Q.W - Y + 0.4f) / FMath::Max(0.3f, (float)ViewUp.Z);
						bClash = true;
						break;
					}
				}
				if (!bClash)
				{
					break;
				}
			}
			PlacedLabels.Add(FVector4(FVector::DotProduct(LabelPos, ViewRight), FVector::DotProduct(LabelPos, ViewUp), W, H));
			T->SetRelativeLocation(LabelPos);
			UStaticMeshComponent* Lead = Pooled(Leaders, NI - 1, LineMesh);
			const float Rise = LabelPos.Z - Anchor.Z;
			Lead->SetVisibility(Rise > 1.f);
			Lead->SetRelativeLocationAndRotation(Anchor, FRotator(90.f, 0.f, 0.f));
			Lead->SetRelativeScale3D(FVector(FMath::Max(Rise, 0.1f) / 100.f, 0.16f, 0.16f));
			SetColor(Lead, Col, 9.f);
			FaceViewer(T, ViewerLocal);
		}
		else if (B.Kind == 1)
		{
			UStaticMeshComponent* D = Pooled(Dots, ND++, SphereMesh);
			D->SetRelativeLocation(P);
			D->SetRelativeScale3D(FVector(0.012f));
			SetColor(D, B.Side == EAstraSide::Astra ? ColAquila : ColHostile, bBeyond ? 20.f : 60.f);
		}
		else
		{
			UStaticMeshComponent* X = Pooled(Blasts, NB++, SphereMesh);
			const float Grow = 1.f - B.Fade;
			X->SetRelativeLocation(P);
			X->SetRelativeScale3D(FVector((2.f + 7.f * Grow) / 100.f));
			SetColor(X, FLinearColor(1.f, 0.55f, 0.2f), 40.f * B.Fade);
		}
	}
	HideFrom(Icons, NI);
	HideFrom(Stems, NI);
	HideFrom(Vectors, NI);
	HideTextFrom(Labels, NL);
	HideFrom(Leaders, NI);
	HideFrom(Dots, ND);
	HideFrom(Blasts, NB);
}
