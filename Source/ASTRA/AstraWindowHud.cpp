#include "AstraWindowHud.h"
#include "ASTRA.h"
#include "AstraBattleSubsystem.h"
#include "AstraShipSubsystem.h"
#include "AstraStations.h"
#include "Camera/PlayerCameraManager.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/Font.h"
#include "Engine/GameViewportClient.h"
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/World.h"
#include "Fonts/SlateFontInfo.h"
#include "GameFramework/Character.h"
#include "GameFramework/PlayerController.h"
#include "Rendering/DrawElements.h"
#include "Styling/CoreStyle.h"
#include "Widgets/SLeafWidget.h"

namespace
{
	TAutoConsoleVariable<int32> CVarWindowAr(TEXT("astra.window.ar"), 1, TEXT("Bracket and name the contacts seen through the bridge's bow window (0 = off)"));
	// the glass: a cylinder of radius 10 m around the bridge's centre, from the sill (0.3 m) to the head (4.2 m), over
	// the arc of the bow (+-66 degrees) (data/ship/aquila_bridge.json "window")
	constexpr double WindowR = 1000.0, Sill = 30.0, Head = 420.0, HalfArcDeg = 66.0;
	// the main viewscreen's image in front of the glass (AAstraViewscreen: x 9 m, 7.2 x 3.0 m, bottom 1.2 m)
	constexpr double ScreenX = 900.0, ScreenHalfW = 360.0, ScreenLo = 120.0, ScreenHi = 420.0;
}

class SAstraWindowHudWidget : public SLeafWidget
{
public:
	SLATE_BEGIN_ARGS(SAstraWindowHudWidget) {}
	SLATE_END_ARGS()

	struct FMark
	{
		FVector2D Pos;       // normalised
		float Box = 8.f;     // half size, px at 1080p
		FString Name, Sub;
		FLinearColor Col;
		bool bEngaged = false;
	};
	TArray<FMark> Marks;
	float Alpha = 1.f;

	void Construct(const FArguments&)
	{
		UFont* Mono = LoadObject<UFont>(nullptr, TEXT("/Game/ASTRA/UI/Fonts/F_ASTRA_Mono.F_ASTRA_Mono"));
		UFont* Title = LoadObject<UFont>(nullptr, TEXT("/Game/ASTRA/UI/Fonts/F_ASTRA_Title.F_ASTRA_Title"));
		Small = Mono ? FSlateFontInfo(Mono, 10) : FCoreStyle::GetDefaultFontStyle("Mono", 10);
		Name = Title ? FSlateFontInfo(Title, 13) : FCoreStyle::GetDefaultFontStyle("Regular", 13);
	}

	virtual FVector2D ComputeDesiredSize(float) const override { return FVector2D(100.f, 100.f); }

	virtual int32 OnPaint(const FPaintArgs&, const FGeometry& G, const FSlateRect&, FSlateWindowElementList& Out, int32 Layer,
	                      const FWidgetStyle&, bool) const override
	{
		const FVector2D Size = G.GetLocalSize();
		const float U = Size.Y / 1080.f;
		for (const FMark& M : Marks)
		{
			const FLinearColor Col(M.Col.R, M.Col.G, M.Col.B, M.Col.A * Alpha);
			const FVector2D At = M.Pos * Size;
			const float H = M.Box * U, L = FMath::Max(3.f, H * 0.4f);
			for (const FVector2D& Sg : {FVector2D(-1, -1), FVector2D(1, -1), FVector2D(1, 1), FVector2D(-1, 1)})
			{
				const FVector2D Corner = At + Sg * H;
				FSlateDrawElement::MakeLines(Out, Layer, G.ToPaintGeometry(), {Corner - FVector2D(Sg.X * L, 0), Corner, Corner - FVector2D(0, Sg.Y * L)},
				                             ESlateDrawEffect::None, Col, true, (M.bEngaged ? 1.8f : 1.2f) * FMath::Max(1.f, U));
			}
			if (!M.Name.IsEmpty())
			{
				const FVector2D T = At + FVector2D(H + 5.f * U, -H - 2.f * U);
				FSlateDrawElement::MakeText(Out, Layer + 1, G.ToPaintGeometry(FVector2D(400.f, 20.f), FSlateLayoutTransform(T)), M.Name, Name, ESlateDrawEffect::None, Col);
				FSlateDrawElement::MakeText(Out, Layer + 1, G.ToPaintGeometry(FVector2D(400.f, 20.f), FSlateLayoutTransform(T + FVector2D(0.f, 15.f * U))), M.Sub, Small,
				                            ESlateDrawEffect::None, FLinearColor(Col.R, Col.G, Col.B, Col.A * 0.8f));
			}
		}
		return Layer + 2;
	}

private:
	FSlateFontInfo Small, Name;
};

void FAstraWindowHud::Remove(APlayerController* PC)
{
	UGameViewportClient* VC = PC && PC->GetWorld() ? PC->GetWorld()->GetGameViewport() : nullptr;
	if (Widget.IsValid() && VC)
	{
		VC->RemoveViewportWidgetContent(Widget.ToSharedRef());
	}
	Widget.Reset();
}

void FAstraWindowHud::Tick(APlayerController* PC, float DeltaTime)
{
	UWorld* W = PC ? PC->GetWorld() : nullptr;
	const UAstraBattleSubsystem* B = W ? W->GetSubsystem<UAstraBattleSubsystem>() : nullptr;
	const APlayerCameraManager* Cam = PC ? PC->PlayerCameraManager.Get() : nullptr;
	UGameViewportClient* VC = W ? W->GetGameViewport() : nullptr;
	if (!B || !Cam || !VC)
	{
		return;
	}
	const FVector Eye = Cam->GetCameraLocation();
	const bool bOnBridge = FMath::Abs(Eye.X) < 950.0 && FMath::Abs(Eye.Y) < 950.0 && Eye.Z > -150.0 && Eye.Z < 700.0 && Cast<ACharacter>(PC->GetPawn());
	const bool bWant = bOnBridge && CVarWindowAr.GetValueOnGameThread() != 0;
	Alpha = FMath::FInterpConstantTo(Alpha, bWant ? 1.f : 0.f, DeltaTime, 3.f);
	if (Alpha <= 0.f)
	{
		Remove(PC);
		return;
	}
	if (!Widget.IsValid())
	{
		Widget = SNew(SAstraWindowHudWidget);
		VC->AddViewportWidgetContent(Widget.ToSharedRef(), 4);
	}
	Widget->Alpha = Alpha;
	Widget->Marks.Reset();
	FVector2D VP(1920.f, 1080.f);
	VC->GetViewportSize(VP);
	const UAstraStationsSubsystem* St = W->GetSubsystem<UAstraStationsSubsystem>();
	const FString Engaged = St ? St->ActionTarget() : FString();
	const UAstraShipSubsystem* Ship = W->GetSubsystem<UAstraShipSubsystem>();
	const bool bScreenOn = !Ship || !Ship->GetViewscreenDescription().StartsWith(TEXT("off"));
	TArray<UAstraBattleSubsystem::FContactView> Cs;
	B->GetContacts(Cs);
	const float Fov = FMath::DegreesToRadians(Cam->GetFOVAngle());
	for (const UAstraBattleSubsystem::FContactView& C : Cs)
	{
		if (C.Track < 2 || (C.bCraft && C.RangeKm > 6.0))
		{
			continue;                     // bearings have no place in the sky; far craft are too many specks
		}
		const FVector Target = C.Actor ? C.Actor->GetActorLocation() : B->WorldOf(C.Pos);
		const FVector Dir = (Target - Eye).GetSafeNormal();
		// where the line of sight crosses the glass cylinder (the eye is inside it)
		const FVector2D E2(Eye.X, Eye.Y), D2(Dir.X, Dir.Y);
		const double a = D2.SizeSquared(), b = 2.0 * FVector2D::DotProduct(E2, D2), c = E2.SizeSquared() - WindowR * WindowR;
		const double Disc = b * b - 4.0 * a * c;
		if (a < 1e-6 || Disc < 0.0)
		{
			continue;
		}
		const double T = (-b + FMath::Sqrt(Disc)) / (2.0 * a);
		const FVector Hit = Eye + Dir * T;
		const double AngleDeg = FMath::RadiansToDegrees(FMath::Atan2(Hit.Y, Hit.X));
		if (T <= 0.0 || FMath::Abs(AngleDeg) > HalfArcDeg || Hit.Z < Sill || Hit.Z > Head)
		{
			continue;                     // through the walls or the roof: not seen
		}
		if (bScreenOn && Dir.X > 0.0)
		{
			// behind the main viewscreen's image: its own overlay names it
			const double Ts = (ScreenX - Eye.X) / Dir.X;
			const FVector S = Eye + Dir * Ts;
			if (Ts > 0.0 && FMath::Abs(S.Y) < ScreenHalfW && S.Z > ScreenLo && S.Z < ScreenHi)
			{
				continue;
			}
		}
		FVector2D Px;
		if (!PC->ProjectWorldLocationToScreen(Target, Px, true))
		{
			continue;
		}
		SAstraWindowHudWidget::FMark M;
		M.Pos = Px / VP;
		const double DistCm = FVector::Dist(Eye, Target);
		const float R = C.Actor && C.Actor->GetStaticMeshComponent() ? C.Actor->GetStaticMeshComponent()->Bounds.SphereRadius : C.RadiusM * 100.f;
		M.Box = FMath::Clamp((float)(R / FMath::Max(DistCm, 1.0) / FMath::Tan(Fov * 0.5) * 540.0), C.bCraft ? 4.f : 7.f, 90.f);
		M.bEngaged = C.ContactId == Engaged;
		M.Col = M.bEngaged ? FLinearColor(1.f, 0.35f, 0.22f, 0.9f)
		      : C.Side == EAstraSide::Astra ? FLinearColor(0.45f, 0.78f, 1.f, 0.75f)
		      : C.Side == EAstraSide::Mandate ? FLinearColor(1.f, 0.62f, 0.25f, 0.85f) : FLinearColor(0.85f, 0.88f, 0.92f, 0.6f);
		if (!C.bCraft)
		{
			M.Name = C.Label.ToUpper();
			M.Sub = FString::Printf(TEXT("%s  %.1f KM"), *C.ContactId, C.RangeKm);
		}
		Widget->Marks.Add(M);
	}
}
