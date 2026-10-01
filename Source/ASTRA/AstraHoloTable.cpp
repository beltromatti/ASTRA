// ASTRA — holographic tactical plot.

#include "AstraHoloTable.h"

#include "AstraBattleSubsystem.h"
#include "AstraShipPlan.h"
#include "AstraShipSubsystem.h"
#include "Camera/PlayerCameraManager.h"
#include "GameFramework/Pawn.h"
#include "Components/StaticMeshComponent.h"
#include "Components/TextRenderComponent.h"
#include "Engine/StaticMesh.h"
#include "Kismet/GameplayStatics.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "ASTRA.h"

DECLARE_CYCLE_STAT(TEXT("Holo table"), STAT_AstraHolo, STATGROUP_Astra);

namespace
{
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
		T->SetWorldSize(4.2f);
		T->SetTextRenderColor(FColor(120, 200, 255));
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
		C->SetStaticMesh(Mesh);
		C->CreateDynamicMaterialInstance(0, HoloMat);
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
			T->SetText(FText::FromString(FString::Printf(TEXT("%03d"), Deg)));
			T->SetWorldSize(4.0f);
			T->SetTextRenderColor(FColor(120, 200, 255, 255));
			FaceViewer(T, ViewerLocal);
		}
	}
	// the bow: a bright wedge on the rim straight ahead, where the view through the window looks
	PlaceLine(Pooled(Ticks, NT++, LineMesh), C + FVector(R, 0.f, 0.f), C + FVector(R + 9.f, 0.f, 0.f), 0.5f, ColAquila, 40.f * Fade);
	HideFrom(Ticks, NT);
}

void AAstraHoloTable::HideSector()
{
	for (TArray<TObjectPtr<UStaticMeshComponent>>* Pool : {&SectorNodes, &SectorLinks, &SectorMarks})
	{
		HideFrom(*Pool, 0);
	}
	HideTextFrom(SectorLabels, 0);
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
		T->SetText(FText::FromString(S.Name.ToUpper() + TEXT("<br>") + Sub));
		T->SetTextRenderColor((Col * FMath::Max(0.25f, Fade)).ToFColor(true));
		T->SetWorldSize(bHere ? 5.6f : 4.6f);
		T->SetRelativeLocation(P + FVector(0, 0, 3.2f));
		FaceViewer(T, ViewerLocal);
	}
	HideFrom(SectorLinks, NL);
	HideFrom(SectorNodes, NN);
	HideFrom(SectorMarks, NM);
	HideTextFrom(SectorLabels, NT);
}

void AAstraHoloTable::HideShip()
{
	HideFrom(ShipSlabs, 0);
	HideFrom(ShipMarks, 0);
	HideFrom(ShipDots, 0);
	HideTextFrom(ShipLabels, 0);
}

void AAstraHoloTable::TickShip(float DeltaTime, const FVector& ViewerLocal, float Fade)
{
	const UAstraShipPlan* Plan = GetWorld()->GetSubsystem<UAstraShipPlan>();
	const UAstraShipSubsystem* Ship = GetWorld()->GetSubsystem<UAstraShipSubsystem>();
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
		T->SetText(FText::FromString(Text));
		T->SetTextRenderColor((Col * FMath::Max(0.25f, Fade)).ToFColor(true));
		T->SetWorldSize(Size);
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
	// the damage: where it is, what it is, who is on it
	FVector Station;
	const bool bStation = SectionCentre(6, TEXT('D'), Station);   // the damage-control teams muster on Deck 6
	for (const FAstraDamage& X : Damage)
	{
		FVector P;
		if (!SectionCentre(X.Deck, X.Section, P))
		{
			continue;
		}
		const FLinearColor Col = DamageColor(X);
		const float Ph = FMath::Frac(Time * 0.8f + X.Id * 0.37f);
		UStaticMeshComponent* Ring = Pooled(ShipMarks, NM++, RingMesh, ShipFrame);
		Ring->SetRelativeLocationAndRotation(P, FRotator::ZeroRotator);
		Ring->SetRelativeScale3D(FVector((2.f + 2.5f * Ph) / 100.f, (2.f + 2.5f * Ph) / 100.f, 1.f));
		SetColor(Ring, Col, Fade * 20.f * (1.f - Ph));
		const FString Who = X.Team < 0 ? FString(TEXT("UNATTENDED"))
		                  : X.Travel > 0.f ? FString::Printf(TEXT("TEAM %d · %.0f S OUT"), X.Team + 1, X.Travel)
		                                   : FString::Printf(TEXT("TEAM %d · %.0f%%"), X.Team + 1, 100.f * X.Progress);
		Label(FString::Printf(TEXT("%s · %d%c<br>%s"), *X.Kind.ToUpper(), X.Deck, X.Section, *Who), P + FVector(0.f, 0.f, 3.5f), Col, 2.8f);
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
	Label(FString::Printf(TEXT("ASN AQUILA · HULL %.0f%%<br>%s"), Battle ? 100.f * Battle->PlayerHullFraction() : 100.f,
	                      Open == 0 ? TEXT("NO DAMAGE REPORTED") : *FString::Printf(TEXT("%d INCIDENT%s"), Open, Open == 1 ? TEXT("") : TEXT("S"))),
	      FVector(0.f, 0.f, RowZ(1) + 12.f), ColAquila, 3.6f);
	HideFrom(ShipSlabs, NS);
	HideFrom(ShipMarks, NM);
	HideFrom(ShipDots, ND);
	HideTextFrom(ShipLabels, NT);
}

void AAstraHoloTable::TickTactical(float DeltaTime, const FVector& ViewerLocal, float Fade)
{
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

	TickBearings(Battle, ViewerLocal, Fade);

	int32 NI = 0, NL = 0, ND = 0, NB = 0, NS = 0;
	TArray<FVector4> PlacedLabels;
	TMap<FString, FVector> PlotOf;   // contact id -> where it is on the plot (for the lines below)
	// the viewer's picture plane (for label decluttering), seen from the player towards the table centre
	const FVector ViewDir = (FVector(0, 0, PlaneHeight) - ViewerLocal).GetSafeNormal();
	const FVector ViewRight = FVector::CrossProduct(FVector::UpVector, ViewDir).GetSafeNormal();
	const FVector ViewUp0 = FVector::CrossProduct(ViewDir, ViewRight).GetSafeNormal();
	const FVector ViewUp = ViewUp0.Z < 0.f ? -ViewUp0 : ViewUp0;
	const float Pulse = 0.75f + 0.25f * FMath::Sin(Time * 6.f);
	for (const FAstraHoloBlip& B : Blips)
	{
		// a passive bearing has no range: it sits on the rim, along its line
		const FVector P = PlotPoint(B.bBearingOnly ? B.Rel.GetSafeNormal() * 1.0e12f : B.Rel);
		const bool bBeyond = B.bBearingOnly || B.Rel.Size() / 100000.f > RangeKm * 1.02f;
		if (B.Kind == 0)
		{
			const FLinearColor Col = BlipColor(B);
			if (!B.Contact.IsEmpty() && !B.bBearingOnly)
			{
				PlotOf.Add(B.Contact, P);
			}
			// bright enough for a bridge in sunlight, big enough to read from the chair (the v3 table is 2.7 m across)
			const float Base = (B.bPlayer ? 80.f : 60.f) * (bBeyond ? 0.45f : 1.f) * (B.bRetreating ? 0.6f : 1.f) * (B.bTargeted ? Pulse * 1.5f : 1.f);
			const float Size = (B.bPlayer ? 22.f : 18.f) * B.Size;
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
			SetColor(Stem, Col, 12.f);

			// velocity vector: 500 m/s = 12 cm
			UStaticMeshComponent* Vec = Pooled(Vectors, NI, LineMesh);
			const float L = FMath::Clamp(B.Speed / 500.f * (B.bCraft ? 3.f : 12.f), 0.f, 24.f);
			Vec->SetVisibility(L > 0.8f && !B.VelDir.IsNearlyZero());
			Vec->SetRelativeLocationAndRotation(P, B.VelDir.Rotation());
			Vec->SetRelativeScale3D(FVector(L / 100.f, 0.18f, 0.18f));
			SetColor(Vec, Col, 14.f);
			++NI;

			if (B.bJamming)
			{
				// the jamming strobe, as a radar scope shows it: a line of noise from us out along its bearing
				const FVector C = FVector(0, 0, PlaneHeight);
				const FVector ToP = P - C;
				UStaticMeshComponent* Strobe = Pooled(Strobes, NS++, LineMesh);
				Strobe->SetRelativeLocationAndRotation(C, ToP.Rotation());
				Strobe->SetRelativeScale3D(FVector(ToP.Size() / 100.f, 0.45f, 0.45f));
				const float Noise = 0.45f + 0.35f * FMath::Abs(FMath::Sin(Time * 23.f + NS)) + 0.2f * FMath::Sin(Time * 57.f);
				SetColor(Strobe, Col, 10.f * Noise);
			}

			if (B.bNoLabel)
			{
				if (Leaders.IsValidIndex(NI - 1))
				{
					Leaders[NI - 1]->SetVisibility(false);
				}
				continue;
			}
			UTextRenderComponent* T = PooledText(Labels, NL++);
			const FString Title = B.bPlayer ? FString(TEXT("ASN AQUILA"))
			                    : (B.Name.IsEmpty() ? FString::Printf(TEXT("%s  %s"), *B.Contact, B.ClassShort.IsEmpty() ? TEXT("UNKNOWN") : *B.ClassShort.ToUpper())
			                                        : FString::Printf(TEXT("%s  %s"), *B.Name.ToUpper(), *B.Contact));
			FString Sub = B.bPlayer ? FString() : (B.bBearingOnly ? FString(B.bJamming ? TEXT("JAMMING  NO RANGE") : TEXT("BEARING ONLY  NO RANGE"))
			                                                      : RangeText(B.RangeKm) + (B.bJamming ? TEXT("  JAMMING") : TEXT("")));
			if (B.bHoldFire) { Sub += TEXT("  HOLDING FIRE"); }
			else if (B.bRetreating) { Sub += TEXT("  WITHDRAWING"); }
			if (B.bTargeted) { Sub += TEXT("  [TARGET]"); }
			T->SetText(FText::FromString(Sub.IsEmpty() ? Title : Title + TEXT("<br>") + Sub));
			T->SetTextRenderColor(Col.ToFColor(true));
			T->SetWorldSize(B.bPlayer ? 6.0f : 5.4f);   // (WS below)
			// declutter in the viewer's picture plane: a label that would cover another climbs just above it
			const float WS = B.bPlayer ? 6.0f : 5.4f;
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
			SetColor(Lead, Col, 16.f);
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
	// who is firing on us: a thin red line from each shooter the plot shows to the Aquila, flickering like tracer fire
	const FVector Us(0.f, 0.f, PlaneHeight);
	int32 NT = 0;
	FString Target;
	float TargetKm = 0.f;
	if (Battle)
	{
		TArray<UAstraBattleSubsystem::FContactView> Cs;
		Battle->GetContacts(Cs);
		for (const UAstraBattleSubsystem::FContactView& C : Cs)
		{
			const FVector* At = C.bFiringAtUs ? PlotOf.Find(C.ContactId) : nullptr;
			if (At)
			{
				const float Flick = 0.6f + 0.4f * FMath::Abs(FMath::Sin(Time * 9.f + NT * 1.7f));
				PlaceLine(Pooled(Threats, NT++, LineMesh), *At, Us, 0.2f, ColHostile, 16.f * Flick * Fade);
			}
		}
		const UAstraBattleSubsystem::FFireControl FC = Battle->GetFireControl();
		Target = FC.Target;
		TargetKm = FC.TargetRangeKm;
	}
	HideFrom(Threats, NT);
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
			T->SetText(FText::FromString(FString::Printf(TEXT("%s %s"), W.Value, *RangeText(W.Key))));
			T->SetWorldSize(3.6f);
			T->SetTextRenderColor((Col * FMath::Max(0.3f, Fade)).ToFColor(true));
			FaceViewer(T, ViewerLocal);
			++NR;
		}
	}
	HideFrom(ReachRings, NR);
	HideTextFrom(ReachLabels, NR);
	// our target under fire control: a line from the Aquila with its distance at the middle, whether our guns reach it, and
	// whether its guns reach us (once the sensors have classified it): red when we are inside them
	const FVector* TargetAt = Target.IsEmpty() ? nullptr : PlotOf.Find(Target);
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
			T->SetText(FText::FromString(RangeText(TargetKm) + TEXT(" · ") + Reach));
			T->SetWorldSize(4.4f);
			T->SetTextRenderColor((bInTheirs ? ColHostile : ColAquila).ToFColor(true));
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
	HideFrom(Leaders, NI);
	HideFrom(Dots, ND);
	HideFrom(Blasts, NB);
	HideFrom(Strobes, NS);
}
