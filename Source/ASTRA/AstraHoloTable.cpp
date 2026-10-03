// ASTRA — holographic tactical plot.

#include "AstraHoloTable.h"

#include "AstraBattleSubsystem.h"
#include "AstraDamageModel.h"
#include "AstraShipPlan.h"
#include "AstraShipSubsystem.h"
#include "AstraWarDraw.h"
#include "Camera/PlayerCameraManager.h"
#include "GameFramework/Pawn.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Components/TextRenderComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshActor.h"
#include "Kismet/GameplayStatics.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "ASTRA.h"

DECLARE_CYCLE_STAT(TEXT("Holo table"), STAT_AstraHolo, STATGROUP_Astra);

namespace
{
	TAutoConsoleVariable<float> CVarHoloDots(TEXT("astra.holo.dots"), 1.f,
		TEXT("Strength of the craft and missile dots on the tactical table (they are instances of the war's glow, M_WAR_Glow, not the table's own material: 1 as made, 0 off)"));

	// a label's text, colour and size, set only when they change: each of UTextRenderComponent's setters makes its render proxy again (new
	// vertex buffers on the render thread, 3 ms a frame with the table's dozens of labels set every frame)
	void HoloSetText(UTextRenderComponent* T, const FString& S)
	{
		if (!T->Text.ToString().Equals(S, ESearchCase::CaseSensitive)) { T->SetText(FText::FromString(S)); }
	}
	void HoloSetColor(UTextRenderComponent* T, const FColor& C)
	{
		if (T->TextRenderColor != C) { T->SetTextRenderColor(C); }
	}
	void HoloSetSize(UTextRenderComponent* T, float Size)
	{
		if (!FMath::IsNearlyEqual(T->WorldSize, Size)) { T->SetWorldSize(Size); }
	}

	const FLinearColor ColAstra(0.22f, 0.72f, 1.f);
	const FLinearColor ColAquila(0.62f, 0.95f, 1.f);
	const FLinearColor ColHostile(1.f, 0.2f, 0.08f);
	const FLinearColor ColHolding(1.f, 0.62f, 0.12f);
	const FLinearColor ColNeutral(0.95f, 0.88f, 0.45f);
	const FLinearColor ColUnknown(0.62f, 0.66f, 0.7f);
	// the ship plot's damage: a fire, a breach (air going), a damaged conduit or panel
	const FLinearColor ColFire(1.f, 0.45f, 0.05f);
	const FLinearColor ColBreach(1.f, 0.07f, 0.12f);
	const FLinearColor ColConduit(0.95f, 0.85f, 0.2f);
	int32 DamageSeverity(const FAstraDamage& D)
	{
		return D.Kind == TEXT("hull breach") ? 3 : (D.Kind == TEXT("fire") ? 2 : 1);
	}
	FLinearColor DamageColor(const FAstraDamage& D)
	{
		return D.Kind == TEXT("hull breach") ? ColBreach : (D.Kind == TEXT("fire") ? ColFire : ColConduit);
	}
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

	FLinearColor OwnerColor(const FString& Owner)
	{
		if (Owner == TEXT("astra")) { return ColAstra; }
		if (Owner == TEXT("mandate")) { return ColHostile; }
		if (Owner == TEXT("guilds")) { return ColNeutral; }
		if (Owner == TEXT("contested")) { return ColHolding; }
		return ColUnknown;
	}

	const TCHAR* OwnerTag(const FString& Owner)
	{
		if (Owner == TEXT("astra")) { return TEXT("ASTRA"); }
		if (Owner == TEXT("mandate")) { return TEXT("MANDATE"); }
		if (Owner == TEXT("guilds")) { return TEXT("FREE GUILDS"); }
		if (Owner == TEXT("contested")) { return TEXT("CONTESTED"); }
		return TEXT("NO CONTACT");
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
	CubeMesh = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cube.Cube"));
	HoloMat = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/ASTRA/Materials/M_ASTRA_Holo.M_ASTRA_Holo"));
	GridMat = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/ASTRA/Materials/M_ASTRA_HoloGrid.M_ASTRA_HoloGrid"));
	TextMat = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/ASTRA/Materials/M_ASTRA_HoloText.M_ASTRA_HoloText"));

	PlotFrame = NewObject<USceneComponent>(this, TEXT("PlotFrame"));
	PlotFrame->SetupAttachment(Root);
	PlotFrame->RegisterComponent();
	ShipFrame = NewObject<USceneComponent>(this, TEXT("ShipFrame"));
	ShipFrame->SetupAttachment(Root);
	ShipFrame->RegisterComponent();
	TextMID = TextMat ? UMaterialInstanceDynamic::Create(TextMat, this) : nullptr;
	if (TextMID)
	{
		TextMID->SetScalarParameterValue(TEXT("Intensity"), 12.f * Brightness);
	}

	// the projector disc on the table top
	Disc = NewObject<UStaticMeshComponent>(this, TEXT("HoloDisc"));
	Disc->SetupAttachment(Root);
	Disc->RegisterComponent();
	Disc->SetStaticMesh(DiscMesh);
	Disc->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Disc->SetCastShadow(false);
	Disc->SetMaterial(0, GridMat);
	if (UMaterialInstanceDynamic* DM = Disc->CreateDynamicMaterialInstance(0, GridMat))
	{
		DM->SetScalarParameterValue(TEXT("Intensity"), 32.f);   // the projector's grid, visible in a sunlit room
	}
	Disc->SetRelativeLocation(FVector(0, 0, 1.5f));
	Disc->SetRelativeScale3D(FVector(PlotRadius / 100.f, PlotRadius / 100.f, 1.f));

	// three range rings on the tactical plane, with their distances
	for (int32 i = 0; i < 3; ++i)
	{
		UStaticMeshComponent* R = Pooled(Rings, i, RingMesh);
		SetColor(R, ColAstra, i == 0 ? 20.f : 10.f);
		UTextRenderComponent* T = PooledText(RingLabels, i);
		HoloSetSize(T, 4.2f);
		HoloSetColor(T, FColor(120, 200, 255));
	}
}

UStaticMeshComponent* AAstraHoloTable::Pooled(TArray<TObjectPtr<UStaticMeshComponent>>& Pool, int32 Index, UStaticMesh* Mesh, USceneComponent* Parent)
{
	while (Pool.Num() <= Index)
	{
		UStaticMeshComponent* C = NewObject<UStaticMeshComponent>(this);
		C->SetupAttachment(Parent ? Parent : PlotFrame.Get());
		C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		C->SetCastShadow(false);
		C->SetMobility(EComponentMobility::Movable);
		C->RegisterComponent();
		C->SetStaticMesh(Mesh);
		C->CreateDynamicMaterialInstance(0, HoloMat);
		C->SetVisibility(false);   // only the requested index is shown below
		Pool.Add(C);
	}
	UStaticMeshComponent* C = Pool[Index];
	if (C->GetStaticMesh() != Mesh)
	{
		C->SetStaticMesh(Mesh);                          // (the slot keeps its own material instance: no new one each time)
		if (!Cast<UMaterialInstanceDynamic>(C->GetMaterial(0)))
		{
			C->CreateDynamicMaterialInstance(0, HoloMat);
		}
	}
	C->SetVisibility(true);
	return C;
}

UTextRenderComponent* AAstraHoloTable::PooledText(TArray<TObjectPtr<UTextRenderComponent>>& Pool, int32 Index, USceneComponent* Parent)
{
	while (Pool.Num() <= Index)
	{
		UTextRenderComponent* T = NewObject<UTextRenderComponent>(this);
		T->SetupAttachment(Parent ? Parent : PlotFrame.Get());
		T->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		T->SetCastShadow(false);
		T->RegisterComponent();
		T->SetTextMaterial(TextMID ? static_cast<UMaterialInterface*>(TextMID) : TextMat.Get());
		T->SetHorizontalAlignment(EHTA_Center);
		T->SetVerticalAlignment(EVRTA_TextBottom);
		HoloSetSize(T, 3.f);
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

void AAstraHoloTable::SetColor(UStaticMeshComponent* C, const FLinearColor& Color, float Intensity) const
{
	if (UMaterialInstanceDynamic* M = Cast<UMaterialInstanceDynamic>(C->GetMaterial(0)))
	{
		M->SetVectorParameterValue(TEXT("Color"), Color);
		M->SetScalarParameterValue(TEXT("Intensity"), Intensity * Brightness);
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
	// the text turns to face the viewer entirely (the plot may be tilted: the words stay square to the eye)
	const FVector D = ViewerLocal - C->GetRelativeLocation();
	C->SetRelativeRotation(D.Rotation());
}

void AAstraHoloTable::Tick(float DeltaTime)
{
	SCOPE_CYCLE_COUNTER(STAT_AstraHolo);
	Super::Tick(DeltaTime);
	Time += DeltaTime;
	FVector ViewerRoot = FVector(-430.f, 0.f, 100.f);   // (the Captain's chair)
	if (const APlayerCameraManager* Cam = UGameplayStatics::GetPlayerCameraManager(this, 0))
	{
		ViewerRoot = GetActorTransform().InverseTransformPosition(Cam->GetCameraLocation());
	}
	// the projector angles the plot towards whoever looks at it from afar, about the plot's centre: from the chair
	// (4 m back, barely above the plane) it is seen face on instead of edge on; leaning over the table, it lies flat
	const FVector Centre(0.f, 0.f, PlaneHeight);
	const FVector ToViewer = ViewerRoot - Centre;
	const float Horiz = FVector2D(ToViewer.X, ToViewer.Y).Size();
	const float Elev = FMath::RadiansToDegrees(FMath::Atan2(ToViewer.Z, FMath::Max(Horiz, 1.f)));
	const float WantTilt = FMath::Clamp(70.f - Elev, 0.f, MaxTilt) * FMath::Clamp((Horiz - PlotRadius - 50.f) / 200.f, 0.f, 1.f);
	Tilt = FMath::FInterpTo(Tilt, WantTilt, DeltaTime, 2.f);
	const float WantAz = FMath::RadiansToDegrees(FMath::Atan2(ToViewer.Y, ToViewer.X));
	TiltAzimuth += FMath::Clamp(FMath::FindDeltaAngleDegrees(TiltAzimuth, WantAz), -90.f * DeltaTime, 90.f * DeltaTime);
	const FVector Towards = FRotator(0.f, TiltAzimuth, 0.f).Vector();
	const FQuat Q(FVector::CrossProduct(FVector::UpVector, Towards).GetSafeNormal(), FMath::DegreesToRadians(Tilt));
	// tilted, the plot rises so that its near edge stays above the table top (a hologram does not sink into its table)
	const float Lift = FMath::Max(0.f, PlotRadius * FMath::Sin(FMath::DegreesToRadians(Tilt)) + 5.f - PlaneHeight);
	PlotFrame->SetRelativeLocationAndRotation(Centre - Q.RotateVector(Centre) + FVector(0.f, 0.f, Lift), Q);
	const FVector ViewerLocal = PlotFrame->GetRelativeTransform().InverseTransformPosition(ViewerRoot);
	// the plot the crew put up: the battle around the Aquila, or the sector at war (a quick cross-fade between them)
	const UAstraShipSubsystem* Ship = GetWorld() ? GetWorld()->GetSubsystem<UAstraShipSubsystem>() : nullptr;
	const bool bSector = Ship && Ship->GetHoloMode() == TEXT("sector") && Ship->GetSector().Num() > 0;
	const UAstraShipPlan* Plan = GetWorld() ? GetWorld()->GetSubsystem<UAstraShipPlan>() : nullptr;
	const bool bShipPlot = Ship && Ship->GetHoloMode() == TEXT("ship") && Plan && Plan->GetDecks().Num() > 0;
	SectorBlend = FMath::FInterpConstantTo(SectorBlend, bSector ? 1.f : 0.f, DeltaTime, 2.5f);
	ShipBlend = FMath::FInterpConstantTo(ShipBlend, bShipPlot ? 1.f : 0.f, DeltaTime, 2.5f);
	const float TacticalFade = FMath::Clamp(1.f - 2.f * FMath::Max(SectorBlend, ShipBlend), 0.f, 1.f);
	const float SectorFade = FMath::Clamp(2.f * SectorBlend - 1.f, 0.f, 1.f);
	const float ShipFade = FMath::Clamp(2.f * ShipBlend - 1.f, 0.f, 1.f);
	if (TacticalFade > 0.f)
	{
		TickTactical(DeltaTime, ViewerLocal, TacticalFade);
	}
	else
	{
		HideTactical();
	}
	if (SectorFade > 0.f)
	{
		TickSector(DeltaTime, ViewerLocal, SectorFade);
	}
	else
	{
		HideSector();
	}
	if (ShipFade > 0.f)
	{
		TickShip(DeltaTime, ViewerRoot, ShipFade);   // upright: the viewer as seen from the table itself
	}
	else
	{
		HideShip();
	}
}

void AAstraHoloTable::HideTactical()
{
	for (TArray<TObjectPtr<UStaticMeshComponent>>* Pool : {&Rings, &Icons, &Stems, &Vectors, &Dots, &Blasts, &Leaders, &Strobes, &Ticks, &Threats, &TargetLine, &ReachRings})
	{
		HideFrom(*Pool, 0);
	}
	for (TArray<TObjectPtr<UTextRenderComponent>>* Pool : {&Labels, &RingLabels, &TickLabels, &TargetLabel, &ReachLabels})
	{
		HideTextFrom(*Pool, 0);
	}
	if (DotLayer.IsValid())
	{
		if (UInstancedStaticMeshComponent* C = DotLayer->Comp.Get(); C && C->IsVisible())
		{
			C->SetVisibility(false);                 // (the craft's and the missiles' dots)
		}
	}
}

void AAstraHoloTable::PlaceLine(UStaticMeshComponent* L, const FVector& A, const FVector& B, float Thickness, const FLinearColor& Color, float Intensity)
{
	const FVector D = B - A;
	L->SetRelativeLocationAndRotation(A, D.Rotation());
	L->SetRelativeScale3D(FVector(FMath::Max(D.Size(), 0.1f) / 100.f, Thickness, Thickness));
	SetColor(L, Color, Intensity);
}

void AAstraHoloTable::TickBearings(const UAstraBattleSubsystem* Battle, const FVector& ViewerLocal, float Fade)
{
	// the crew's bearings are true bearings (the system's frame: 000 along its x axis, clockwise seen from above); the
	// plot keeps the bow forward, so the ring of bearings turns with the ship — a head-up radar with a true bearing ring
	FVector North(1.f, 0.f, 0.f), East(0.f, 1.f, 0.f);
	if (Battle)
	{
		const FVector O = Battle->WorldOf(Battle->PlayerPos());
		North = (Battle->WorldOf(Battle->PlayerPos() + FVector(1000.0, 0.0, 0.0)) - O).GetSafeNormal2D();
		East = (Battle->WorldOf(Battle->PlayerPos() + FVector(0.0, 1000.0, 0.0)) - O).GetSafeNormal2D();
		if (North.IsNearlyZero() || East.IsNearlyZero())
		{
			North = FVector(1.f, 0.f, 0.f);   // the ship pointing straight up or down: no heading to show
			East = FVector(0.f, 1.f, 0.f);
		}
	}
	const float R = PlotRadius + 2.f;
	const FVector C(0.f, 0.f, PlaneHeight);
	int32 NT = 0;
	for (int32 Deg = 0; Deg < 360; Deg += 10)
	{
		const float A = FMath::DegreesToRadians((float)Deg);
		const FVector Dir = (North * FMath::Cos(A) + East * FMath::Sin(A)).GetSafeNormal();
		const bool bMajor = Deg % 30 == 0;
		const float Len = Deg % 90 == 0 ? 6.f : (bMajor ? 4.f : 2.f);
		PlaceLine(Pooled(Ticks, NT++, LineMesh), C + Dir * R, C + Dir * (R + Len), bMajor ? 0.22f : 0.14f, ColAstra, (bMajor ? 14.f : 8.f) * Fade);
		if (bMajor)
		{
			UTextRenderComponent* T = PooledText(TickLabels, Deg / 30);
			T->SetRelativeLocation(C + Dir * (R + Len + 4.5f) + FVector(0.f, 0.f, -1.5f));
			HoloSetText(T, FString::Printf(TEXT("%03d"), Deg));
			HoloSetSize(T, 4.0f);
			HoloSetColor(T, FColor(120, 200, 255, 255));
			FaceViewer(T, ViewerLocal);
		}
	}
	// the bow: a bright wedge on the rim straight ahead, where the view through the window looks
	PlaceLine(Pooled(Ticks, NT++, LineMesh), C + FVector(R, 0.f, 0.f), C + FVector(R + 9.f, 0.f, 0.f), 0.5f, ColAquila, 40.f * Fade);
	HideFrom(Ticks, NT);
}

void AAstraHoloTable::HideSector()
{
	for (TArray<TObjectPtr<UStaticMeshComponent>>* Pool : {&SectorNodes, &SectorLinks, &SectorMarks, &MarchMarks, &MarchCourses})
	{
		HideFrom(*Pool, 0);
	}
	HideTextFrom(SectorLabels, 0);
	HideTextFrom(MarchLabels, 0);
}

void AAstraHoloTable::TickSector(float DeltaTime, const FVector& ViewerLocal, float Fade)
{
	const UAstraShipSubsystem* Ship = GetWorld()->GetSubsystem<UAstraShipSubsystem>();
	const UAstraBattleSubsystem* Battle = GetWorld()->GetSubsystem<UAstraBattleSubsystem>();
	const TArray<FAstraSectorSystem>& Sector = Ship->GetSector();
	// fit the whole sector on the disc: west (the Core) to the viewer's left, north away from them
	FBox2D Box(ForceInit);
	for (const FAstraSectorSystem& S : Sector)
	{
		Box += S.Pos;
	}
	const FVector2D Centre = Box.GetCenter();
	const float Half = FMath::Max(1.f, 0.5f * (float)FMath::Max(Box.GetSize().X, Box.GetSize().Y));
	const float Scale = PlotRadius * 0.84f / Half;
	// the map turns (slowly) so that its south faces the viewer: east to their right, north away from them
	const float WantYaw = FMath::RadiansToDegrees(FMath::Atan2(ViewerLocal.Y, ViewerLocal.X));
	SectorYaw = SectorBlend < 0.05f ? WantYaw : SectorYaw + FMath::Clamp(FMath::FindDeltaAngleDegrees(SectorYaw, WantYaw), -60.f * DeltaTime, 60.f * DeltaTime);
	const FVector South = FRotator(0.f, SectorYaw, 0.f).Vector();
	const FVector North = -South;
	const FVector East = FVector::CrossProduct(FVector::UpVector, North);
	const float Z = PlaneHeight - 6.f;   // floating like the tactical plot (and angled with it towards the viewer)
	auto Where = [&](const FAstraSectorSystem& S)
	{
		const FVector2D D = S.Pos - Centre;
		return North * (D.Y * Scale) + East * (D.X * Scale) + FVector(0, 0, Z);
	};
	const FString Here = Ship->GetSystemName();
	const FString Dest = Battle ? Battle->GetGateDestination() : FString();
	const float Pulse = 0.5f + 0.5f * FMath::Sin(Time * 4.f);
	int32 NL = 0, NN = 0, NM = 0, NT = 0;
	// gate links (each once), the one the Aquila is taking alive with light
	for (int32 i = 0; i < Sector.Num(); ++i)
	{
		for (const FString& L : Sector[i].Links)
		{
			const int32 j = Sector.IndexOfByPredicate([&L](const FAstraSectorSystem& X) { return X.Name == L; });
			if (j <= i)
			{
				continue;
			}
			const FVector A = Where(Sector[i]), B = Where(Sector[j]);
			const bool bRoute = !Dest.IsEmpty() && ((Sector[i].Name == Here && Sector[j].Name == Dest) || (Sector[j].Name == Here && Sector[i].Name == Dest));
			const bool bSame = Sector[i].Owner == Sector[j].Owner;
			UStaticMeshComponent* Line = Pooled(SectorLinks, NL++, LineMesh);
			Line->SetRelativeLocationAndRotation(A, (B - A).Rotation());
			Line->SetRelativeScale3D(FVector((B - A).Size() / 100.f, bRoute ? 0.45f : 0.28f, bRoute ? 0.45f : 0.28f));
			SetColor(Line, bRoute ? ColAquila : (bSame ? OwnerColor(Sector[i].Owner) * 0.8f : ColUnknown * 0.7f),
			         Fade * (bRoute ? 12.f + 16.f * Pulse : 6.f));
		}
	}
	for (const FAstraSectorSystem& S : Sector)
	{
		const FVector P = Where(S);
		const FLinearColor Col = OwnerColor(S.Owner);
		const bool bHere = S.Name == Here;
		// the star: brighter where the Aquila is, pulsing where the fighting is
		UStaticMeshComponent* Node = Pooled(SectorNodes, NN++, SphereMesh);
		Node->SetRelativeLocation(P);
		Node->SetRelativeScale3D(FVector((bHere ? 4.2f : 3.2f) / 100.f));
		const float Threat = S.Threat >= 2 ? 0.6f + 0.4f * FMath::Sin(Time * (S.Threat >= 3 ? 7.f : 4.f)) : 1.f;
		SetColor(Node, Col, Fade * (bHere ? 60.f : 34.f) * Threat);
		// the Aquila's system ringed, the threatened ones haloed
		if (bHere || S.Threat >= 2)
		{
			UStaticMeshComponent* Mark = Pooled(SectorMarks, NM++, RingMesh);
			Mark->SetRelativeLocationAndRotation(P, FRotator::ZeroRotator);
			const float R = bHere ? 7.f + 0.8f * Pulse : 5.f + 2.5f * FMath::Frac(Time * 0.7f);
			Mark->SetRelativeScale3D(FVector(R / 100.f, R / 100.f, 1.f));
			SetColor(Mark, bHere ? ColAquila : ColHostile, Fade * (bHere ? 22.f : 14.f * (1.f - FMath::Frac(Time * 0.7f))));
		}
		UTextRenderComponent* T = PooledText(SectorLabels, NT++);
		FString Sub = OwnerTag(S.Owner);
		if (bHere) { Sub = TEXT("ASN AQUILA  ·  ") + Sub; }
		if (S.Name == Dest) { Sub += TEXT("  ·  TRANSIT"); }
		HoloSetText(T, S.Name.ToUpper() + TEXT("<br>") + Sub);
		HoloSetColor(T, (Col * FMath::Max(0.25f, Fade)).ToFColor(true));
		HoloSetSize(T, bHere ? 5.6f : 4.6f);
		T->SetRelativeLocation(P + FVector(0, 0, 3.2f));
		FaceViewer(T, ViewerLocal);
	}
	// the March (CAMPAGNA): our fleets as they are, the enemy's as tracks (dimmer, older), each beside its system with its course to the next one and its
	// arrival; the battles our high command knows of, as a red ring breathing round their system
	int32 NF = 0, NC = 0, NFL = 0;
	TMap<FString, int32> AtSystem;               // how many markers a system has already: the next one goes round it
	for (const FAstraMarchFleet& F : Ship->GetMarchFleets())
	{
		const FAstraSectorSystem* From = Sector.FindByPredicate([&F](const FAstraSectorSystem& X) { return X.Name == F.System; });
		if (!From)
		{
			continue;
		}
		const bool bOurs = F.Side == TEXT("astra");
		const FLinearColor Col = bOurs ? ColAstra : ColHostile;
		const float Seen = F.bKnown ? 1.f : FMath::Clamp(1.f - F.AgeS / 1800.f, 0.35f, 0.8f);   // a track fades as it ages
		const FAstraSectorSystem* To = F.To.IsEmpty() ? nullptr : Sector.FindByPredicate([&F](const FAstraSectorSystem& X) { return X.Name == F.To; });
		const FVector P0 = Where(*From);
		int32& K = AtSystem.FindOrAdd(F.System);
		FVector P = P0 + (North * FMath::Cos(0.9f + 1.25f * K) + East * FMath::Sin(0.9f + 1.25f * K)) * 6.5f + FVector(0.f, 0.f, 2.f);
		++K;
		if (To && To != From && F.EtaS >= 0.f)
		{
			// under way: on the gate lane, a third of the way out, the course drawn on to the system it is bound for
			const FVector P1 = Where(*To);
			P = FMath::Lerp(P0, P1, 0.33f) + FVector(0.f, 0.f, 2.f);
			UStaticMeshComponent* C = Pooled(MarchCourses, NC++, LineMesh);
			C->SetRelativeLocationAndRotation(P, (P1 + FVector(0.f, 0.f, 2.f) - P).Rotation());
			C->SetRelativeScale3D(FVector((P1 - P).Size() / 100.f, 0.22f, 0.22f));
			SetColor(C, Col, Fade * Seen * (7.f + 5.f * Pulse));
		}
		UStaticMeshComponent* M = Pooled(MarchMarks, NF++, SphereMesh);
		M->SetRelativeLocation(P);
		const float Size = FMath::Clamp(1.4f + 0.18f * F.Ships, 1.6f, 4.0f);
		M->SetRelativeScale3D(FVector(Size, Size, Size * 0.45f) / 100.f);
		SetColor(M, Col, Fade * Seen * (bOurs ? 40.f : 30.f));
		UTextRenderComponent* T = PooledText(MarchLabels, NFL++);
		FString Line = F.bKnown ? F.Name.ToUpper() : TEXT("MANDATE FORCE");
		Line += F.bKnown ? FString::Printf(TEXT("  ·  %d"), F.Ships) : FString::Printf(TEXT("  ·  ~%d"), F.Ships);
		if (To && F.EtaS >= 0.f)
		{
			Line += FString::Printf(TEXT("<br>→ %s  %d:%02d"), *To->Name.ToUpper(), (int32)F.EtaS / 60, (int32)F.EtaS % 60);
		}
		else if (!F.bKnown)
		{
			Line += FString::Printf(TEXT("<br>SEEN %d MIN AGO"), FMath::Max(0, (int32)(F.AgeS / 60.f)));
		}
		HoloSetText(T, Line);
		HoloSetColor(T, (Col * FMath::Max(0.25f, Fade * Seen)).ToFColor(true));
		HoloSetSize(T, 3.2f);
		T->SetRelativeLocation(P + FVector(0, 0, 2.6f));
		FaceViewer(T, ViewerLocal);
	}
	for (const FString& B : Ship->GetMarchBattles())
	{
		const FAstraSectorSystem* S = Sector.FindByPredicate([&B](const FAstraSectorSystem& X) { return X.Name == B; });
		if (!S)
		{
			continue;
		}
		UStaticMeshComponent* Mark = Pooled(SectorMarks, NM++, RingMesh);
		Mark->SetRelativeLocationAndRotation(Where(*S), FRotator::ZeroRotator);
		const float Ph = FMath::Frac(Time * 1.1f);
		const float R = 4.f + 6.f * Ph;
		Mark->SetRelativeScale3D(FVector(R / 100.f, R / 100.f, 1.f));
		SetColor(Mark, ColHostile, Fade * 20.f * (1.f - Ph));
	}
	HideFrom(MarchMarks, NF);
	HideFrom(MarchCourses, NC);
	HideTextFrom(MarchLabels, NFL);
	HideFrom(SectorLinks, NL);
	HideFrom(SectorNodes, NN);
	HideFrom(SectorMarks, NM);
	HideTextFrom(SectorLabels, NT);
}

void AAstraHoloTable::HideShip()
{
	if (ScanHull)
	{
		ScanHull->SetVisibility(false);
	}
	HideFrom(ShipSlabs, 0);
	HideFrom(ShipMarks, 0);
	HideFrom(ShipDots, 0);
	HideTextFrom(ShipLabels, 0);
}

bool AAstraHoloTable::TickScannedShip(float DeltaTime, const FVector& ViewerLocal, float Fade, const FString& Id)
{
	const UAstraBattleSubsystem* Battle = GetWorld()->GetSubsystem<UAstraBattleSubsystem>();
	UAstraBattleSubsystem::FDamageView V;
	if (!Battle || !Battle->GetDamageView(Id, V))
	{
		return false;
	}
	const TArray<UAstraBattleSubsystem::FContactView>& Cs = Battle->Contacts();    // (the battle's list for this step, shared: not copied every frame)
	const UAstraBattleSubsystem::FContactView* C = Cs.FindByPredicate([&Id](const UAstraBattleSubsystem::FContactView& X) { return X.ContactId == Id; });
	// a diagram of her, side on to the viewer and the bow to their right, like the Aquila's cutaway: three sections between
	// the true cuts of her break-up pieces, a hull a fifth as tall as long, her six shield faces round it
	const float HalfLen = C ? FMath::Max(C->RadiusM, 15.f) : 200.f;
	const float CutBow = (V.CutBowX != 0.f || V.CutSternX != 0.f) ? FMath::Clamp(V.CutBowX, -0.9f * HalfLen, 0.9f * HalfLen) : HalfLen / 3.f;
	const float CutStern = (V.CutBowX != 0.f || V.CutSternX != 0.f) ? FMath::Clamp(V.CutSternX, -0.9f * HalfLen, CutBow - 1.f) : -HalfLen / 3.f;
	const float S = PlotRadius * 1.3f / (2.f * HalfLen);
	const float H = 2.f * HalfLen * S * 0.2f, Depth = 2.f * HalfLen * S * 0.1f;
	const float WantYaw = FMath::RadiansToDegrees(FMath::Atan2(ViewerLocal.Y, ViewerLocal.X)) - 90.f;
	ShipYaw = ShipBlend < 0.05f ? WantYaw : ShipYaw + FMath::Clamp(FMath::FindDeltaAngleDegrees(ShipYaw, WantYaw), -60.f * DeltaTime, 60.f * DeltaTime);
	const FVector Fwd = FRotator(0.f, ShipYaw, 0.f).Vector();
	const FVector Stbd = FVector::CrossProduct(FVector::UpVector, Fwd);
	const FVector Centre(0.f, 0.f, PlaneHeight + 22.f);
	auto At = [&](float Xm, float Yrel, float Zrel) { return Centre + Fwd * (Xm * S) + Stbd * (Yrel * Depth * 0.5f) + FVector(0.f, 0.f, Zrel * H * 0.5f); };
	const float Pulse = 0.5f + 0.5f * FMath::Sin(Time * 6.f);
	const bool bHostile = V.Side == EAstraSide::Mandate;
	const FLinearColor Base = V.Side == EAstraSide::Astra ? ColAstra : (bHostile ? ColHostile * 0.85f : ColNeutral);
	int32 NS = 0, NM = 0, ND = 0, NT = 0;
	auto Text = [&](const FString& T, const FVector& P, const FLinearColor& Col, float Size)
	{
		UTextRenderComponent* L = PooledText(ShipLabels, NT++, ShipFrame);
		HoloSetText(L, T);
		HoloSetColor(L, (Col * FMath::Max(0.25f, Fade)).ToFColor(true));
		HoloSetSize(L, Size);
		L->SetRelativeLocation(P);
		FaceViewer(L, ViewerLocal);
	};
	auto Box = [&](const FVector& P, const FVector& SizeCm, const FLinearColor& Col, float Intensity)
	{
		UStaticMeshComponent* B = Pooled(ShipSlabs, NS++, CubeMesh, ShipFrame);
		B->SetRelativeLocationAndRotation(P, FRotator(0.f, ShipYaw, 0.f));
		B->SetRelativeScale3D(SizeCm / 100.f);
		SetColor(B, Col, Intensity * Fade);
	};
	// her own hull as a hologram: the ship the optical sensors see, scaled to the table and turned side on
	const UStaticMesh* HullMesh = C && C->Actor && C->Actor->GetStaticMeshComponent() ? C->Actor->GetStaticMeshComponent()->GetStaticMesh() : nullptr;
	if (HullMesh)
	{
		if (!ScanHull)
		{
			ScanHull = NewObject<UStaticMeshComponent>(this, TEXT("ScanHull"));
			ScanHull->SetupAttachment(ShipFrame);
			ScanHull->SetCollisionEnabled(ECollisionEnabled::NoCollision);
			ScanHull->SetCastShadow(false);
			ScanHull->SetMobility(EComponentMobility::Movable);
			ScanHull->RegisterComponent();
		}
		if (ScanHull->GetStaticMesh() != HullMesh)
		{
			ScanHull->SetStaticMesh(const_cast<UStaticMesh*>(HullMesh));
			for (int32 i = 0; i < ScanHull->GetNumMaterials(); ++i)
			{
				ScanHull->CreateDynamicMaterialInstance(i, HoloMat);     // translucent: drawn from its fallback mesh, a hologram's grain
			}
		}
		const FBox MB = HullMesh->GetBoundingBox();
		const float MeshLen = FMath::Max(1.0, MB.GetSize().X);
		const float K = 2.f * HalfLen * S / MeshLen;
		ScanHull->SetVisibility(true);
		ScanHull->SetRelativeScale3D(FVector(K));
		ScanHull->SetRelativeRotation(FRotator(0.f, ShipYaw, 0.f));
		ScanHull->SetRelativeLocation(Centre - FRotator(0.f, ShipYaw, 0.f).RotateVector(MB.GetCenter() * K));
		for (int32 i = 0; i < ScanHull->GetNumMaterials(); ++i)
		{
			if (UMaterialInstanceDynamic* M = Cast<UMaterialInstanceDynamic>(ScanHull->GetMaterial(i)))
			{
				M->SetVectorParameterValue(TEXT("Color"), V.bReactorCritical || V.bBreakingUp ? ColHostile : Base);
				M->SetScalarParameterValue(TEXT("Intensity"), (V.bReactorCritical || V.bBreakingUp ? 3.f + 4.f * Pulse : 2.2f) * Fade * Brightness);
			}
		}
	}
	else if (ScanHull)
	{
		ScanHull->SetVisibility(false);
	}
	// her sections (bow, mid, stern) as bars under the hull: what is left of their structure once the sensors know her
	// class, and what burns, vents or is gutted there (a flare over the hull where it happens)
	const float Ends[3][2] = {{CutBow, HalfLen}, {CutStern, CutBow}, {-HalfLen, CutStern}};
	static const TCHAR* SecName[3] = {TEXT("BOW"), TEXT("MID"), TEXT("STERN")};
	for (int32 k = 0; k < 3; ++k)
	{
		const float X0 = Ends[k][0], X1 = Ends[k][1];
		FLinearColor Col = V.Detail >= 2 ? (V.StructureFrac[k] > 0.66f ? Base : (V.StructureFrac[k] > 0.33f ? ColHolding : ColHostile)) : ColUnknown;
		if (V.bGutted[k]) { Col = FLinearColor(0.5f, 0.02f, 0.02f); }
		const float Frac = V.Detail >= 2 ? FMath::Clamp(V.StructureFrac[k], 0.f, 1.f) : 1.f;
		const float BarLen = (X1 - X0) * S * 0.94f;
		const FVector BarAt = At(0.5f * (X0 + X1), 0.f, -1.f) - FVector(0.f, 0.f, 4.f);
		Box(BarAt, FVector(BarLen, 1.f, 0.9f), Col * 0.35f, 3.f);                                       // the frame of the bar
		Box(BarAt - Fwd * (BarLen * (1.f - Frac) * 0.5f), FVector(BarLen * Frac, 1.2f, 1.1f), Col, 9.f);   // what is left
		if (V.bBurning[k] || V.bBreached[k] || V.bGutted[k])
		{
			UStaticMeshComponent* F = Pooled(ShipMarks, NM++, SphereMesh, ShipFrame);
			F->SetRelativeLocation(At(0.5f * (X0 + X1), 0.f, 0.3f));
			F->SetRelativeScale3D(FVector((3.f + 2.f * Pulse) / 100.f));
			SetColor(F, V.bBurning[k] ? FLinearColor(1.f, 0.45f, 0.05f) : ColHostile, Fade * (20.f + 30.f * Pulse));
		}
		if (V.Detail >= 2)
		{
			Text(FString::Printf(TEXT("%s %.0f%%%s"), SecName[k], 100.f * V.StructureFrac[k], V.bGutted[k] ? TEXT(" GUTTED") : (V.bBurning[k] ? TEXT(" BURNING") : (V.bBreached[k] ? TEXT(" BREACHED") : TEXT("")))),
			     BarAt - FVector(0.f, 0.f, 3.2f), Col, 2.4f);
		}
	}
	// the six shield faces: a plate outside each face, as bright as the face is strong, flashing where it takes a hit
	if (V.Detail >= 2)
	{
		const float Gap = 1.6f;
		struct FFace { FVector P; FVector Size; };
		const float Len = 2.f * HalfLen * S;
		const FFace Faces[6] = {
			{At(HalfLen, 0.f, 0.f) + Fwd * Gap, FVector(0.5f, Depth + 2.f, H + 2.f)},          // bow
			{At(-HalfLen, 0.f, 0.f) - Fwd * Gap, FVector(0.5f, Depth + 2.f, H + 2.f)},         // stern
			{At(0.f, -1.f, 0.f) - Stbd * Gap, FVector(Len, 0.4f, H + 2.f)},                    // port
			{At(0.f, 1.f, 0.f) + Stbd * Gap, FVector(Len, 0.4f, H + 2.f)},                     // starboard
			{At(0.f, 0.f, 1.f) + FVector(0.f, 0.f, Gap), FVector(Len, Depth + 2.f, 0.5f)},    // dorsal
			{At(0.f, 0.f, -1.f) - FVector(0.f, 0.f, Gap), FVector(Len, Depth + 2.f, 0.5f)}};  // ventral
		const FLinearColor Shield = bHostile ? FLinearColor(1.f, 0.35f, 0.25f) : FLinearColor(0.35f, 0.75f, 1.f);
		for (int32 f = 0; f < 6; ++f)
		{
			// a face down: nothing there; port and starboard face the viewer and would wall the hull in: their strength is in the
			// line below, and they show only while they flash under a hit
			if ((V.ShieldFrac[f] <= 0.01f && V.ShieldFlash[f] <= 0.f) || ((f == 2 || f == 3) && V.ShieldFlash[f] <= 0.05f))
			{
				continue;
			}
			Box(Faces[f].P, Faces[f].Size, Shield, 0.6f + 2.4f * V.ShieldFrac[f] + 30.f * FMath::Clamp(V.ShieldFlash[f], 0.f, 1.f));
		}
		Text(FString::Printf(TEXT("SHIELDS  BOW %.0f · STERN %.0f · PORT %.0f · STBD %.0f · DORSAL %.0f · VENTRAL %.0f"),
		                     100.f * V.ShieldFrac[0], 100.f * V.ShieldFrac[1], 100.f * V.ShieldFrac[2], 100.f * V.ShieldFrac[3], 100.f * V.ShieldFrac[4], 100.f * V.ShieldFrac[5]),
		     Centre - FVector(0.f, 0.f, H * 0.5f + 13.f), Shield, 2.6f);
	}
	// her systems and guns: only our own ships tell us (the datalink)
	if (V.Detail >= 3)
	{
		Text(FString::Printf(TEXT("ENGINES %.0f · SENSORS %.0f · HANGAR %.0f · BRIDGE %.0f · REACTOR %.0f · POINT DEFENCE %.0f"),
		                     100.f * V.Sys[0], 100.f * V.Sys[1], 100.f * V.Sys[2], 100.f * V.Sys[3], 100.f * V.Sys[4], 100.f * V.Sys[5]),
		     Centre - FVector(0.f, 0.f, H * 0.5f + 17.f), ColAquila, 2.4f);
		for (const UAstraBattleSubsystem::FDamageView::FMountView& M : V.Mounts)
		{
			UStaticMeshComponent* D = Pooled(ShipDots, ND++, SphereMesh, ShipFrame);
			D->SetRelativeLocation(At(M.Dir.X * HalfLen * 0.9f, FMath::Clamp(M.Dir.Y * 1.3f, -1.1f, 1.1f), FMath::Clamp(M.Dir.Z * 1.3f, -1.1f, 1.1f)));
			D->SetRelativeScale3D(FVector(0.8f / 100.f));
			SetColor(D, M.Health > 0.66f ? FLinearColor(0.3f, 1.f, 0.55f) : (M.Health > 0.2f ? ColHolding : ColHostile), Fade * (M.bReady ? 30.f : 10.f));
		}
	}
	// where the last blow landed, for a moment
	if (V.LastHitAge < 2.5f && !V.LastHitLocal.IsNearlyZero())
	{
		const FVector Dir = V.LastHitLocal.GetSafeNormal();
		UStaticMeshComponent* Hit = Pooled(ShipMarks, NM++, SphereMesh, ShipFrame);
		Hit->SetRelativeLocation(At(Dir.X * HalfLen, FMath::Clamp(Dir.Y * 1.4f, -1.2f, 1.2f), FMath::Clamp(Dir.Z * 1.4f, -1.2f, 1.2f)));
		Hit->SetRelativeScale3D(FVector((2.f + 3.f * V.LastHitAge) / 100.f));
		SetColor(Hit, FLinearColor(1.f, 0.85f, 0.6f), Fade * 60.f * (1.f - V.LastHitAge / 2.5f));
	}
	// who she is, and what the sensors see of her
	const FString Name = C ? C->Label.ToUpper() : Id;
	FString Kind = C ? C->Class : FString();
	Kind.RemoveFromStart(TEXT("Kharon Mandate "));
	Kind.RemoveFromStart(TEXT("ASTRA "));
	FString Head = FString::Printf(TEXT("%s · %s%s"), *Id, *Name, Kind.IsEmpty() ? TEXT("") : *FString::Printf(TEXT(" · %s"), *Kind.ToUpper()));
	if (C && C->RangeKm > 0.0)
	{
		Head += FString::Printf(TEXT(" · %.1f KM"), C->RangeKm);
	}
	FString Sub = V.Detail >= 2 && C ? FString::Printf(TEXT("HULL %.0f%% · SHIELDS %.0f%%"), 100.f * C->HullFrac, 100.f * C->ShieldFrac)
	                                 : FString(TEXT("CLASS NOT KNOWN: ONLY WHAT BURNS AND BREAKS"));
	if (V.bReactorCritical) { Sub += TEXT(" · REACTOR CRITICAL"); }
	if (V.bBreakingUp) { Sub += TEXT(" · BREAKING UP"); }
	if (V.bDisabled) { Sub += TEXT(" · DISABLED"); }
	Text(Head + TEXT("<br>") + Sub, Centre + FVector(0.f, 0.f, H * 0.5f + 8.f), V.bReactorCritical || V.bBreakingUp ? ColHostile * (0.6f + 0.4f * Pulse) : Base, 3.4f);
	HideFrom(ShipSlabs, NS);
	HideFrom(ShipMarks, NM);
	HideFrom(ShipDots, ND);
	HideTextFrom(ShipLabels, NT);
	return true;
}

void AAstraHoloTable::TickShip(float DeltaTime, const FVector& ViewerLocal, float Fade)
{
	const UAstraShipPlan* Plan = GetWorld()->GetSubsystem<UAstraShipPlan>();
	const UAstraShipSubsystem* Ship = GetWorld()->GetSubsystem<UAstraShipSubsystem>();
	if (!Ship->GetHoloShipId().IsEmpty() && TickScannedShip(DeltaTime, ViewerLocal, Fade, Ship->GetHoloShipId()))
	{
		return;                                // a scanned ship (else, her track lost: back to the Aquila)
	}
	const UAstraBattleSubsystem* Battle = GetWorld()->GetSubsystem<UAstraBattleSubsystem>();
	const TArray<FAstraPlanDeck>& Decks = Plan->GetDecks();
	// a cutaway, as in a ship's manual: the whole ship across the disc, seen from the side, her decks one row each (5 cm
	// apart, to read them from the chair: a diagram, not a model), each as long as it really is, so the stack draws her
	// shape; the bridge raised on its island over Deck 2
	float X0 = 1e9f, X1 = -1e9f;
	for (const FAstraPlanDeck& D : Decks)
	{
		for (const FAstraPlanDeck::FSection& Se : D.Sections)
		{
			X0 = FMath::Min(X0, Se.X0);
			X1 = FMath::Max(X1, Se.X1);
		}
	}
	if (X1 <= X0)
	{
		HideShip();
		return;
	}
	const float S = PlotRadius * 1.5f / (X1 - X0);
	const float Xc = 0.5f * (X0 + X1);
	const float Pitch = 5.f;
	const float Mid = PlaneHeight + 4.f;                                    // the hull's middle deck (7) at this height
	auto RowZ = [&](int32 DeckId) { return Mid + Pitch * (DeckId == 1 ? 6.6f : 7.f - (float)DeckId); };
	const float Depth = 3.5f;                                                 // the cutaway's thickness
	// she turns (slowly) to show her side to the viewer, the bow to their right
	const float WantYaw = FMath::RadiansToDegrees(FMath::Atan2(ViewerLocal.Y, ViewerLocal.X)) - 90.f;
	ShipYaw = ShipBlend < 0.05f ? WantYaw : ShipYaw + FMath::Clamp(FMath::FindDeltaAngleDegrees(ShipYaw, WantYaw), -60.f * DeltaTime, 60.f * DeltaTime);
	const FVector Fwd = FRotator(0.f, ShipYaw, 0.f).Vector();
	const FVector Stbd = FVector::CrossProduct(FVector::UpVector, Fwd);
	auto Map = [&](float X, float Y, int32 DeckId) { return Fwd * ((X - Xc) * S) + Stbd * FMath::Clamp(Y * S, -Depth, Depth) + FVector(0.f, 0.f, RowZ(DeckId)); };
	auto FindDeck = [&Decks](int32 Id) { return Decks.FindByPredicate([Id](const FAstraPlanDeck& X) { return X.Id == Id; }); };
	auto SectionCentre = [&](int32 DeckId, TCHAR Sec, FVector& Out)
	{
		const FAstraPlanDeck* D = FindDeck(DeckId);
		const FAstraPlanDeck::FSection* Se = D ? D->Sections.FindByPredicate([Sec](const FAstraPlanDeck::FSection& X) { return X.Id.Len() > 0 && X.Id[0] == Sec; }) : nullptr;
		if (!Se)
		{
			return false;
		}
		Out = Map(0.5f * (Se->X0 + Se->X1), 0.f, DeckId) + FVector(0.f, 0.f, 1.2f);
		return true;
	};
	const TArray<FAstraDamage>& Damage = Ship->GetDamage();
	const float Pulse = 0.5f + 0.5f * FMath::Sin(Time * 5.f);
	int32 NS = 0, NM = 0, ND = 0, NT = 0;
	// labels that would land on each other climb until they are clear
	TArray<FVector> Placed;
	auto Label = [&](const FString& Text, FVector At, const FLinearColor& Col, float Size)
	{
		for (int32 Guard = 0; Guard < 12; ++Guard)
		{
			const bool bClash = Placed.ContainsByPredicate([&At](const FVector& P) { return FVector::Dist2D(P, At) < 14.f && FMath::Abs(P.Z - At.Z) < 5.f; });
			if (!bClash)
			{
				break;
			}
			At.Z += 5.f;
		}
		Placed.Add(At);
		UTextRenderComponent* T = PooledText(ShipLabels, NT++, ShipFrame);
		HoloSetText(T, Text);
		HoloSetColor(T, (Col * FMath::Max(0.25f, Fade)).ToFColor(true));
		HoloSetSize(T, Size);
		T->SetRelativeLocation(At);
		FaceViewer(T, ViewerLocal);
	};

	// the decks, section by section: faint where all is well, the colour of the worst damage where it is not
	for (const FAstraPlanDeck& D : Decks)
	{
		float Aft = 1e9f;
		for (const FAstraPlanDeck::FSection& Se : D.Sections)
		{
			const float Mx = 0.5f * (Se.X0 + Se.X1);
			if (Se.Id.IsEmpty())
			{
				continue;
			}
			Aft = FMath::Min(Aft, Se.X0);
			const FAstraDamage* Worst = nullptr;
			for (const FAstraDamage& X : Damage)
			{
				if (X.Deck == D.Id && X.Section == Se.Id[0] && (!Worst || DamageSeverity(X) > DamageSeverity(*Worst)))
				{
					Worst = &X;
				}
			}
			UStaticMeshComponent* Slab = Pooled(ShipSlabs, NS++, CubeMesh, ShipFrame);
			Slab->SetRelativeLocationAndRotation(Map(Mx, 0.f, D.Id), FRotator(0.f, ShipYaw, 0.f));
			Slab->SetRelativeScale3D(FVector((Se.X1 - Se.X0) * S * 0.95f / 100.f, Depth / 100.f, 2.6f / 100.f));
			SetColor(Slab, Worst ? DamageColor(*Worst) : ColAstra, Fade * (Worst ? 12.f + 16.f * Pulse : 3.2f));
		}
		if (Aft < 1e8f)
		{
			// the deck's number at her stern end (the bridge's deck by name)
			Label(D.Id == 1 ? FString(TEXT("BRIDGE")) : FString::Printf(TEXT("%d"), D.Id), Map(Aft, 0.f, D.Id) - Fwd * 4.f + FVector(0.f, 0.f, -1.2f),
			      ColAstra, D.Id == 1 ? 2.6f : 2.4f);
		}
	}
	// the sections' letters over her hull (Deck 2, the top of the hull)
	if (const FAstraPlanDeck* Top = FindDeck(2))
	{
		for (const FAstraPlanDeck::FSection& Se : Top->Sections)
		{
			Label(Se.Id, Map(0.5f * (Se.X0 + Se.X1), 0.f, Top->Id) + FVector(0.f, 0.f, 2.5f), ColAstra * 0.8f, 2.6f);
		}
	}
	// the damage: where it is (the compartment itself, along its deck's row), what it is, who is on it
	const FAstraDamageModel* Interior = Ship->GetInterior().IsReady() ? &Ship->GetInterior() : nullptr;
	FVector Station;
	const bool bStation = SectionCentre(6, TEXT('D'), Station);   // the damage-control teams muster on Deck 6
	// the worst few are labelled (a table of thirty labels is not a table): the unattended first, by how bad
	TArray<int32> Worst;
	for (int32 i = 0; i < Damage.Num(); ++i)
	{
		Worst.Add(i);
	}
	Worst.Sort([&Damage](int32 A, int32 B)
	{
		const FAstraDamage& X = Damage[A];
		const FAstraDamage& Y = Damage[B];
		return (X.Team < 0) != (Y.Team < 0) ? X.Team < 0 : (DamageSeverity(X) != DamageSeverity(Y) ? DamageSeverity(X) > DamageSeverity(Y) : X.Severity > Y.Severity);
	});
	TSet<int32> Labelled;
	for (int32 k = 0; k < FMath::Min(Worst.Num(), 8); ++k)
	{
		Labelled.Add(Worst[k]);
	}
	for (int32 i = 0; i < Damage.Num(); ++i)
	{
		const FAstraDamage& X = Damage[i];
		FVector P;
		float LenCm = 0.f;
		if (Interior && Interior->GetMap().Comps.IsValidIndex(X.Comp))
		{
			const FBox& Box = Interior->GetMap().Comps[X.Comp].Box;
			P = Map(Box.GetCenter().X, 0.f, X.Deck) + FVector(0.f, 0.f, 1.2f);
			LenCm = Box.GetSize().X;
		}
		else if (!SectionCentre(X.Deck, X.Section, P))
		{
			continue;
		}
		const FLinearColor Col = DamageColor(X);
		if (LenCm > 0.f)
		{
			// the compartment itself, lit along its deck's row
			UStaticMeshComponent* Mark = Pooled(ShipSlabs, NS++, CubeMesh, ShipFrame);
			Mark->SetRelativeLocationAndRotation(P - FVector(0.f, 0.f, 1.2f), FRotator(0.f, ShipYaw, 0.f));
			Mark->SetRelativeScale3D(FVector(FMath::Max(LenCm * S * 0.95f, 1.4f) / 100.f, Depth * 1.25f / 100.f, 3.f / 100.f));
			SetColor(Mark, Col, Fade * (16.f + 18.f * Pulse));
		}
		const float Ph = FMath::Frac(Time * 0.8f + X.Id * 0.37f);
		UStaticMeshComponent* Ring = Pooled(ShipMarks, NM++, RingMesh, ShipFrame);
		Ring->SetRelativeLocationAndRotation(P, FRotator::ZeroRotator);
		Ring->SetRelativeScale3D(FVector((2.f + 2.5f * Ph) / 100.f, (2.f + 2.5f * Ph) / 100.f, 1.f));
		SetColor(Ring, Col, Fade * 20.f * (1.f - Ph));
		if (Labelled.Contains(i))
		{
			const FString Who = X.Team < 0 ? FString(TEXT("UNATTENDED"))
			                  : X.Travel > 0.f ? FString::Printf(TEXT("TEAM %d · %.0f S OUT"), X.Team + 1, X.Travel)
			                                   : FString::Printf(TEXT("TEAM %d · %.0f%%"), X.Team + 1, 100.f * X.Progress);
			const FString Place = X.Place.IsEmpty() ? FString() : FString::Printf(TEXT("<br>%s"), *X.Place.ToUpper().Left(26));
			Label(FString::Printf(TEXT("%s · %d%c%s<br>%s"), *X.Kind.ToUpper(), X.Deck, X.Section, *Place, *Who), P + FVector(0.f, 0.f, 3.5f), Col, 2.8f);
		}
		if (X.Team >= 0 && bStation)
		{
			// the team: walking from its station to the damage, then working round it
			const float K = X.Travel0 > 0.f ? FMath::Clamp(1.f - X.Travel / X.Travel0, 0.f, 1.f) : 1.f;
			FVector Dot = FMath::Lerp(Station, P, K);
			if (X.Travel <= 0.f)
			{
				const float A = Time * 2.2f + X.Team * 1.6f;
				Dot = P + (Fwd * FMath::Cos(A) * 2.4f + FVector(0.f, 0.f, FMath::Sin(A) * 1.2f));
			}
			UStaticMeshComponent* T = Pooled(ShipDots, ND++, SphereMesh, ShipFrame);
			T->SetRelativeLocation(Dot);
			T->SetRelativeScale3D(FVector(1.1f / 100.f));
			SetColor(T, ColAquila, Fade * 45.f);
		}
	}
	// the pressure bulkheads that are shut: a bar across the deck, where it is (a section that is sealed off reads at a glance)
	int32 Sealed = 0;
	if (Interior)
	{
		for (const int32 DoorIndex : Interior->SealedDoors())
		{
			const FAstraDmgDoor& Door = Interior->GetMap().Doors[DoorIndex];
			if (++Sealed > 24)
			{
				break;
			}
			UStaticMeshComponent* Bar = Pooled(ShipSlabs, NS++, CubeMesh, ShipFrame);
			Bar->SetRelativeLocationAndRotation(Map(Door.PosCm.X, 0.f, Door.Deck) + FVector(0.f, 0.f, 0.2f), FRotator(0.f, ShipYaw, 0.f));
			Bar->SetRelativeScale3D(FVector(0.55f / 100.f, Depth * 1.4f / 100.f, 3.4f / 100.f));
			SetColor(Bar, FLinearColor(0.85f, 0.95f, 1.f), Fade * 30.f);
		}
	}
	// the Captain, wherever they are
	if (const APawn* Pawn = UGameplayStatics::GetPlayerPawn(this, 0))
	{
		const FVector L = Pawn->GetActorLocation();
		if (const FAstraPlanDeck* D = FindDeck(Plan->DeckAt(L)))
		{
			const FVector P = Map(L.X, L.Y, D->Id) + FVector(0.f, 0.f, 2.f);
			UStaticMeshComponent* C = Pooled(ShipDots, ND++, SphereMesh, ShipFrame);
			C->SetRelativeLocation(P);
			C->SetRelativeScale3D(FVector((1.6f + 0.4f * Pulse) / 100.f));
			SetColor(C, ColAquila, Fade * 70.f);
			Label(D->Id == 1 ? FString(TEXT("CAPTAIN")) : FString::Printf(TEXT("CAPTAIN · DECK %d"), D->Id), P + FVector(0.f, 0.f, 3.f), ColAquila, 2.6f);
		}
	}
	// what she is: her name, her hull, what is open
	const int32 Open = Damage.Num();
	const FString Report = Open == 0 ? FString(TEXT("NO DAMAGE REPORTED")) : FString::Printf(TEXT("%d INCIDENT%s%s"), Open, Open == 1 ? TEXT("") : TEXT("S"),
	                                                                                      Sealed > 0 ? *FString::Printf(TEXT(" · %d SEALED"), Sealed) : TEXT(""));
	Label(FString::Printf(TEXT("ASN AQUILA · HULL %.0f%%<br>%s"), Battle ? 100.f * Battle->PlayerHullFraction() : 100.f, *Report),
	      FVector(0.f, 0.f, RowZ(1) + 12.f), ColAquila, 3.6f);
	HideFrom(ShipSlabs, NS);
	HideFrom(ShipMarks, NM);
	HideFrom(ShipDots, ND);
	HideTextFrom(ShipLabels, NT);
}


UStaticMeshComponent* AAstraHoloTable::PooledQuiet(TArray<TObjectPtr<UStaticMeshComponent>>& Pool, int32 Index, UStaticMesh* Mesh)
{
	// (as Pooled, but it leaves the visibility to the caller: a component that is shown and then hidden in the same frame — a stem too short to see — was making
	// its render state again twice a frame, every frame)
	while (Pool.Num() <= Index)
	{
		UStaticMeshComponent* C = NewObject<UStaticMeshComponent>(this);
		C->SetupAttachment(PlotFrame.Get());
		C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		C->SetCastShadow(false);
		C->SetMobility(EComponentMobility::Movable);
		C->RegisterComponent();
		C->SetStaticMesh(Mesh);
		C->CreateDynamicMaterialInstance(0, HoloMat);
		C->SetVisibility(false);
		Pool.Add(C);
	}
	UStaticMeshComponent* C = Pool[Index];
	if (C->GetStaticMesh() != Mesh)
	{
		C->SetStaticMesh(Mesh);
		if (!Cast<UMaterialInstanceDynamic>(C->GetMaterial(0)))
		{
			C->CreateDynamicMaterialInstance(0, HoloMat);
		}
	}
	return C;
}

void AAstraHoloTable::TickTactical(float DeltaTime, const FVector& ViewerLocal, float Fade)
{
	const UAstraBattleSubsystem* Battle = GetWorld() ? GetWorld()->GetSubsystem<UAstraBattleSubsystem>() : nullptr;
	static const TArray<FAstraHoloBlip> NoBlips;
	const TArray<FAstraHoloBlip>& Blips = Battle ? Battle->HoloBlips() : NoBlips;   // (the battle's own list for this step, shared: not made again here)

	// a crowd (a fleet battle: two hundred contacts) is plotted thirty times a second, not every frame: nothing on a table moves, in a thirtieth of a second, that an eye could tell
	TacticalDt += DeltaTime;
	if (Blips.Num() > 80 && TacticalDt < 1.f / 30.f - 0.003f)
	{
		return;
	}
	const float Dt = TacticalDt;
	TacticalDt = 0.f;

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
	RangeKm = FMath::Exp(FMath::FInterpTo(FMath::Loge(RangeKm), FMath::Loge(TargetRangeKm), Dt, 1.8f));

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
		HoloSetText(T, RangeText(Km));
		FaceViewer(T, ViewerLocal);
	}

	TickBearings(Battle, ViewerLocal, Fade);

	// what to put up (AstraHoloPlan.h): the ships' icons, the craft and the missiles as dots, the labels where they cover nothing
	AstraHoloPlan::FParams Par;
	Par.PlotRadius = PlotRadius;
	Par.PlaneHeight = PlaneHeight;
	Par.MaxDepth = MaxDepth;
	Par.RangeKm = RangeKm;
	Par.ViewerLocal = ViewerLocal;
	const UAstraShipSubsystem* ShipSys = GetWorld() ? GetWorld()->GetSubsystem<UAstraShipSubsystem>() : nullptr;
	Par.HeadingDeg = ShipSys ? ShipSys->GetHeadingDeg() : 0.f;
	Par.CharW = LabelCharW;
	AstraHoloPlan::Make(Blips, Par, PlanState, TacticalPlan);

	const FVector Us(0.f, 0.f, PlaneHeight);
	const float Pulse = 0.75f + 0.25f * FMath::Sin(Time * 6.f);
	int32 NS = 0;
	const int32 NI = TacticalPlan.Icons.Num();
	for (int32 k = 0; k < NI; ++k)
	{
		const AstraHoloPlan::FIcon& Ic = TacticalPlan.Icons[k];
		const FAstraHoloBlip& B = Blips[Ic.Blip];
		const FVector& P = Ic.P;
		const FLinearColor Col = AstraHoloPlan::ColorOf(B);
		// bright enough for a bridge in sunlight, big enough to read from the chair (the v3 table is 2.7 m across)
		const float Base = (B.bPlayer ? 80.f : 60.f) * (Ic.bBeyond ? 0.45f : 1.f) * (B.bRetreating ? 0.6f : 1.f) * (B.bTargeted ? Pulse * 1.5f : 1.f);
		UStaticMeshComponent* Icon = Pooled(Icons, k, B.bUnknown ? UnknownMesh.Get() : ShipMesh.Get());
		Icon->SetRelativeLocationAndRotation(P, B.bUnknown ? FRotator(0.f, Time * 40.f, 0.f) : B.Rot.Rotator());
		Icon->SetRelativeScale3D(FVector(Ic.Size / 100.f));
		SetColor(Icon, Col, Base);

		// drop line to the plane (a depth cue) and velocity vector (500 m/s = 12 cm): in a crowd only for the ships that matter
		const bool bDetail = !TacticalPlan.bDense || Ic.bMust;
		const float Dz = P.Z - PlaneHeight;
		UStaticMeshComponent* Stem = PooledQuiet(Stems, k, LineMesh);
		const bool bStem = bDetail && FMath::Abs(Dz) > 0.6f;
		if (bStem)
		{
			Stem->SetRelativeLocationAndRotation(FVector(P.X, P.Y, PlaneHeight), FRotator(Dz > 0.f ? 90.f : -90.f, 0.f, 0.f));
			Stem->SetRelativeScale3D(FVector(FMath::Max(FMath::Abs(Dz), 0.1f) / 100.f, 0.15f, 0.15f));
			SetColor(Stem, Col, 12.f);
		}
		if (Stem->IsVisible() != bStem)
		{
			Stem->SetVisibility(bStem);
		}
		UStaticMeshComponent* Vec = PooledQuiet(Vectors, k, LineMesh);
		const float VecLen = FMath::Clamp(B.Speed / 500.f * 12.f, 0.f, 24.f);
		const bool bVec = bDetail && VecLen > 0.8f && !B.VelDir.IsNearlyZero();
		if (bVec)
		{
			Vec->SetRelativeLocationAndRotation(P, B.VelDir.Rotation());
			Vec->SetRelativeScale3D(FVector(VecLen / 100.f, 0.18f, 0.18f));
			SetColor(Vec, Col, 14.f);
		}
		if (Vec->IsVisible() != bVec)
		{
			Vec->SetVisibility(bVec);
		}
		if (B.bJamming)
		{
			// the jamming strobe, as a radar scope shows it: a line of noise from us out along its bearing
			const FVector ToP = P - Us;
			UStaticMeshComponent* Strobe = Pooled(Strobes, NS++, LineMesh);
			Strobe->SetRelativeLocationAndRotation(Us, ToP.Rotation());
			Strobe->SetRelativeScale3D(FVector(ToP.Size() / 100.f, 0.45f, 0.45f));
			const float Noise = 0.45f + 0.35f * FMath::Abs(FMath::Sin(Time * 23.f + NS)) + 0.2f * FMath::Sin(Time * 57.f);
			SetColor(Strobe, Col, 10.f * Noise);
		}
	}

	// the labels, where the plan found them room, with a line to what they name when they stand off from it
	int32 NL = 0, NLead = 0;
	{
		// a label keeps its text component from frame to frame (by its key), and its words are changed four times a second at most
		const int32 NLab = TacticalPlan.Labels.Num();
		TArray<int32, TInlineAllocator<32>> SlotOf;
		SlotOf.Init(-1, NLab);
		LabelSlots.SetNum(FMath::Max(LabelSlots.Num(), NLab));
		TArray<bool, TInlineAllocator<32>> Used;
		Used.Init(false, LabelSlots.Num());
		for (int32 i = 0; i < NLab; ++i)
		{
			for (int32 s = 0; s < LabelSlots.Num(); ++s)
			{
				if (!Used[s] && LabelSlots[s].Key == TacticalPlan.Labels[i].Key)
				{
					SlotOf[i] = s;
					Used[s] = true;
					break;
				}
			}
		}
		for (int32 i = 0; i < NLab; ++i)
		{
			if (SlotOf[i] < 0)
			{
				for (int32 s = 0; s < LabelSlots.Num(); ++s)
				{
					if (!Used[s])
					{
						SlotOf[i] = s;
						Used[s] = true;
						LabelSlots[s].Key = TacticalPlan.Labels[i].Key;
						LabelSlots[s].TextAt = -1.0e9;                     // a new owner: its words at once
						break;
					}
				}
			}
		}
		for (int32 i = 0; i < NLab; ++i)
		{
			const AstraHoloPlan::FLabel& L = TacticalPlan.Labels[i];
			FLabelSlot& Sl = LabelSlots[SlotOf[i]];
			bool bNewText = false;
			if (Time - Sl.TextAt >= 0.25 || Sl.Text.IsEmpty())
			{
				bNewText = !Sl.Text.Equals(L.Text, ESearchCase::CaseSensitive);
				Sl.Text = L.Text;
				Sl.TextAt = Time;
			}
			UTextRenderComponent* T = PooledText(Labels, SlotOf[i]);
			HoloSetText(T, Sl.Text);
			HoloSetColor(T, L.Col.ToFColor(true));
			HoloSetSize(T, L.Size);
			if (bNewText && L.Size > 0.f)
			{
				// the plan reckons a label's width from its characters: measure the font as it really draws (a guess too narrow put
				// four hostile names on one line from the chair)
				int32 Longest = 0;
				TArray<FString> Lines;
				Sl.Text.ParseIntoArray(Lines, TEXT("<br>"), true);
				for (const FString& Ln : Lines)
				{
					Longest = FMath::Max(Longest, Ln.Len());
				}
				if (Longest >= 4)
				{
					const float K = (float)T->GetTextLocalSize().Y / (Longest * L.Size);
					if (K > 0.3f && K < 1.2f)
					{
						LabelCharW = FMath::Lerp(LabelCharW, K, 0.25f);
					}
				}
			}
			T->SetRelativeLocation(L.Pos);
			FaceViewer(T, ViewerLocal);
			NL = FMath::Max(NL, SlotOf[i] + 1);
			if (L.bLeader)
			{
				PlaceLine(Pooled(Leaders, NLead++, LineMesh), L.From, L.Pos, 0.16f, L.Col, 16.f);
			}
		}
		// the slots no label has now are free (and their text components hidden below)
		for (int32 s = 0; s < LabelSlots.Num(); ++s)
		{
			if (!Used[s])
			{
				LabelSlots[s].Key = MIN_int32;
				if (Labels.IsValidIndex(s))
				{
					Labels[s]->SetVisibility(false);
				}
			}
		}
	}

	// the craft and the missiles: dots, one instanced component in all (a component each, with a stem and a vector, was four hundred of them)
	if (!DotLayer.IsValid() && SphereMesh)
	{
		UMaterialInterface* Glow = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/ASTRA/Materials/M_WAR_Glow.M_WAR_Glow"));   // (the war's own glow: instanced, a colour and a strength for each dot)
		if (Glow)
		{
			DotLayer = MakeShared<AstraFx::FLayer>();
			DotLayer->Init(DotCapacity);
			DotLayer->Comp = AstraDraw::MakeComp(this, PlotFrame.Get(), TEXT("HoloDots"), SphereMesh, Glow, DotCapacity, AstraFx::Stride, false, false);
		}
	}
	if (DotLayer.IsValid())
	{
		AstraFx::FLayer& L = *DotLayer;
		L.Begin();
		const float Gain = Fade * Brightness / 3.f * FMath::Max(0.f, CVarHoloDots.GetValueOnGameThread());
		const auto Put = [&L, Gain](const TArray<AstraHoloPlan::FDot>& Dots, const FLinearColor& Col, float Inten)
		{
			for (const AstraHoloPlan::FDot& D : Dots)
			{
				FTransform* X;
				float* Dat = L.Next(X);
				if (!Dat)
				{
					return;
				}
				*X = FTransform(FQuat::Identity, D.P, FVector(D.Scale));
				AstraFx::Fill(Dat, Col, Inten * Gain, 0.f, 0.f, 0.f, 0.f, D.Scale, 0.f);
			}
		};
		Put(TacticalPlan.CraftDots[0], ColAstra, 150.f);
		Put(TacticalPlan.CraftDots[1], ColHostile, 150.f);
		Put(TacticalPlan.CraftDots[2], ColUnknown, 100.f);
		Put(TacticalPlan.MissileDots[0], ColAquila, 190.f);
		Put(TacticalPlan.MissileDots[1], ColHostile, 190.f);
		L.Flush();
		if (UInstancedStaticMeshComponent* C = L.Comp.Get())
		{
			const bool bShow = L.Count > 0 || L.Prev > 0;
			if (C->IsVisible() != bShow)
			{
				C->SetVisibility(bShow);
			}
		}
	}

	// the explosions
	int32 NB = 0;
	for (const int32 bi : TacticalPlan.Blasts)
	{
		const FAstraHoloBlip& B = Blips[bi];
		const FVector P = PlotPoint(B.Rel);
		UStaticMeshComponent* X = Pooled(Blasts, NB++, SphereMesh);
		const float Grow = 1.f - B.Fade;
		X->SetRelativeLocation(P);
		X->SetRelativeScale3D(FVector((2.f + 7.f * Grow) / 100.f));
		SetColor(X, FLinearColor(1.f, 0.55f, 0.2f), 40.f * B.Fade);
	}

	// who is firing on us: a thin red line from each shooter the plot shows (the nearest dozen) to the Aquila, flickering like tracer fire
	int32 NT = 0;
	for (const int32 k : TacticalPlan.Threats)
	{
		const float Flick = 0.6f + 0.4f * FMath::Abs(FMath::Sin(Time * 9.f + NT * 1.7f));
		PlaceLine(Pooled(Threats, NT++, LineMesh), TacticalPlan.Icons[k].P, Us, 0.2f, ColHostile, 16.f * Flick * Fade);
	}
	HideFrom(Threats, NT);
	FString Target;
	float TargetKm = 0.f;
	if (Battle)
	{
		const UAstraBattleSubsystem::FFireControl FC = Battle->GetFireControl();
		Target = FC.Target;
		TargetKm = FC.TargetRangeKm;
	}
	// how far our guns reach (the numbers the fire control uses): a ring for the railguns, one for the lasers
	int32 NR = 0;
	UAstraBattleSubsystem::FWeaponRanges Ours;
	if (Battle)
	{
		Ours = Battle->GetWeaponRanges();
		const TPair<float, const TCHAR*> Reach[] = {{Ours.RailKm, TEXT("RAIL")}, {Ours.LaserKm, TEXT("LASER")}};
		for (const TPair<float, const TCHAR*>& W : Reach)
		{
			const float R = W.Key > 0.f ? PlotRadiusOf(W.Key) : 0.f;
			if (R <= 1.f || R > PlotRadius * 1.01f)
			{
				continue;
			}
			const bool bRail = FCString::Strcmp(W.Value, TEXT("RAIL")) == 0;
			const FLinearColor Col = bRail ? ColAstra * 0.8f : ColHolding;
			UStaticMeshComponent* Ring = Pooled(ReachRings, NR, RingMesh);
			Ring->SetRelativeLocation(FVector(0, 0, PlaneHeight + 0.2f));
			Ring->SetRelativeScale3D(FVector(R / 100.f, R / 100.f, 1.f));
			SetColor(Ring, Col, 7.f * Fade);
			UTextRenderComponent* T = PooledText(ReachLabels, NR);
			const float A = FMath::DegreesToRadians(38.f + 9.f * NR);
			T->SetRelativeLocation(FVector(R * FMath::Cos(A), R * FMath::Sin(A), PlaneHeight + 0.8f));
			HoloSetText(T, FString::Printf(TEXT("%s %s"), W.Value, *RangeText(W.Key)));
			HoloSetSize(T, 3.6f);
			HoloSetColor(T, (Col * FMath::Max(0.3f, Fade)).ToFColor(true));
			FaceViewer(T, ViewerLocal);
			++NR;
		}
	}
	HideFrom(ReachRings, NR);
	HideTextFrom(ReachLabels, NR);
	// our target under fire control: a line from the Aquila with its distance at the middle, whether our guns reach it, and
	// whether its guns reach us (once the sensors have classified it): red when we are inside them
	const FVector* TargetAt = nullptr;
	if (!Target.IsEmpty())
	{
		for (const AstraHoloPlan::FIcon& Ic : TacticalPlan.Icons)
		{
			const FAstraHoloBlip& B = Blips[Ic.Blip];
			if (!B.bBearingOnly && B.Contact == Target)
			{
				TargetAt = &Ic.P;
				break;
			}
		}
	}
	if (TargetAt)
	{
		const UAstraBattleSubsystem::FWeaponRanges Theirs = Battle ? Battle->GetWeaponRanges(Target) : UAstraBattleSubsystem::FWeaponRanges();
		const bool bInTheirs = TargetKm > 0.f && TargetKm <= FMath::Max(Theirs.RailKm, Theirs.LaserKm);
		UStaticMeshComponent* L = Pooled(TargetLine, 0, LineMesh);
		PlaceLine(L, Us, *TargetAt, 0.3f, bInTheirs ? ColHostile : ColAquila, 22.f * Fade);
		if (TargetKm > 0.f)
		{
			FString Reach = TargetKm <= Ours.LaserKm ? TEXT("RAILS AND LASERS") : (TargetKm <= Ours.RailKm ? TEXT("IN RAIL RANGE") : TEXT("OUT OF OUR GUNS"));
			if (bInTheirs)
			{
				Reach += TEXT("<br>WE ARE IN ITS GUNS");
			}
			UTextRenderComponent* T = PooledText(TargetLabel, 0);
			T->SetRelativeLocation((Us + *TargetAt) * 0.5f + FVector(0.f, 0.f, 1.5f));
			HoloSetText(T, RangeText(TargetKm) + TEXT(" · ") + Reach);
			HoloSetSize(T, 4.4f);
			HoloSetColor(T, (bInTheirs ? ColHostile : ColAquila).ToFColor(true));
			FaceViewer(T, ViewerLocal);
		}
		else
		{
			HideTextFrom(TargetLabel, 0);
		}
	}
	else
	{
		HideFrom(TargetLine, 0);
		HideTextFrom(TargetLabel, 0);
	}

	HideFrom(Icons, NI);
	HideFrom(Stems, NI);
	HideFrom(Vectors, NI);
	HideTextFrom(Labels, NL);
	HideFrom(Leaders, NLead);
	HideFrom(Dots, 0);
	HideFrom(Blasts, NB);
	HideFrom(Strobes, NS);
}
