#include "AstraWindowHud.h"
#include "AstraFonts.h"
#include "ASTRA.h"
#include "AstraBattleSubsystem.h"
#include "AstraHoloTable.h"
#include "AstraShipSubsystem.h"
#include "AstraStations.h"
#include "Camera/PlayerCameraManager.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/Font.h"
#include "Engine/GameViewportClient.h"
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "Fonts/FontMeasure.h"
#include "Framework/Application/SlateApplication.h"
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
		bool bThreat = false; // firing on us
	};
	TArray<FMark> Marks;
	float Alpha = 1.f;
	FBox2D Screen = FBox2D(ForceInit);   // the main viewscreen's image, normalised (the names keep off it: it has its own)
	FBox2D Holo = FBox2D(ForceInit);     // the holo table with its plot, normalised (likewise)

	void Construct(const FArguments&)
	{
		UFont* Mono = AstraFonts::Mono();
		UFont* Title = AstraFonts::Title();
		Small = Mono ? FSlateFontInfo(Mono, 10) : FCoreStyle::GetDefaultFontStyle("Mono", 10);
		Name = Title ? FSlateFontInfo(Title, 13) : FCoreStyle::GetDefaultFontStyle("Regular", 13);
	}

	virtual FVector2D ComputeDesiredSize(float) const override { return FVector2D(100.f, 100.f); }

	virtual int32 OnPaint(const FPaintArgs&, const FGeometry& G, const FSlateRect&, FSlateWindowElementList& Out, int32 Layer,
	                      const FWidgetStyle&, bool) const override
	{
		const FVector2D Size = G.GetLocalSize();
		const float U = Size.Y / 1080.f;
		// the brackets first (the names keep clear of every ship's box), then the names, most important first — the target,
		// whoever fires on us, the nearest — each where it covers nothing already written: up and right of its box, up and
		// left, down and right, down and left, then higher up; a name with no room is left out (its bracket says enough).
		// Ships seen bunched along one line of sight (a strike group head-on) otherwise wrote their names on top of each other.
		TArray<FSlateRect> Taken;
		Taken.Reserve(Marks.Num() * 2 + 1);
		for (const FBox2D* Area : {&Screen, &Holo})
		{
			if (Area->bIsValid)
			{
				Taken.Add(FSlateRect(Area->Min.X * Size.X, Area->Min.Y * Size.Y, Area->Max.X * Size.X, Area->Max.Y * Size.Y));
			}
		}
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
			Taken.Add(FSlateRect(At.X - H, At.Y - H, At.X + H, At.Y + H));
		}
		TArray<int32> Order;
		for (int32 i = 0; i < Marks.Num(); ++i)
		{
			if (!Marks[i].Name.IsEmpty())
			{
				Order.Add(i);
			}
		}
		Order.Sort([this](int32 A, int32 B)
		{
			const FMark& Ma = Marks[A];
			const FMark& Mb = Marks[B];
			if (Ma.bEngaged != Mb.bEngaged) { return Ma.bEngaged; }
			if (Ma.bThreat != Mb.bThreat) { return Ma.bThreat; }
			return Ma.Box > Mb.Box;
		});
		const TSharedRef<FSlateFontMeasure> Measure = FSlateApplication::Get().GetRenderer()->GetFontMeasureService();
		const auto Clear = [&Taken, &Size](const FSlateRect& R)
		{
			if (R.Left < 2.f || R.Top < 2.f || R.Right > Size.X - 2.f || R.Bottom > Size.Y - 2.f)
			{
				return false;
			}
			for (const FSlateRect& T : Taken)
			{
				if (FSlateRect::DoRectanglesIntersect(R, T))
				{
					return false;
				}
			}
			return true;
		};
		for (const int32 i : Order)
		{
			const FMark& M = Marks[i];
			const FLinearColor Col(M.Col.R, M.Col.G, M.Col.B, M.Col.A * Alpha);
			const FVector2D At = M.Pos * Size;
			const float H = M.Box * U;
			const FVector2D NameSz = Measure->Measure(M.Name, Name);
			const FVector2D SubSz = Measure->Measure(M.Sub, Small);
			const FVector2D Block(FMath::Max(NameSz.X, SubSz.X), 15.f * U + SubSz.Y);
			const float Gx = H + 5.f * U, Gy = H + 2.f * U;
			const FVector2D Tries[7] = {At + FVector2D(Gx, -Gy), At + FVector2D(-Gx - Block.X, -Gy), At + FVector2D(Gx, Gy - Block.Y * 0.35f),
			                            At + FVector2D(-Gx - Block.X, Gy - Block.Y * 0.35f), At + FVector2D(Gx, -Gy - Block.Y * 1.1f),
			                            At + FVector2D(-Gx - Block.X, -Gy - Block.Y * 1.1f), At + FVector2D(-Block.X * 0.5f, Gy + 2.f * U)};
			for (const FVector2D& T : Tries)
			{
				const FSlateRect R(T.X - 2.f * U, T.Y - 2.f * U, T.X + Block.X + 2.f * U, T.Y + Block.Y + 2.f * U);
				if (!Clear(R))
				{
					continue;
				}
				Taken.Add(R);
				FSlateDrawElement::MakeText(Out, Layer + 1, G.ToPaintGeometry(FVector2D(400.f, 20.f), FSlateLayoutTransform(T)), M.Name, Name, ESlateDrawEffect::None, Col);
				FSlateDrawElement::MakeText(Out, Layer + 1, G.ToPaintGeometry(FVector2D(400.f, 20.f), FSlateLayoutTransform(T + FVector2D(0.f, 15.f * U))), M.Sub, Small,
				                            ESlateDrawEffect::None, FLinearColor(Col.R, Col.G, Col.B, Col.A * 0.8f));
				break;
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
	Widget->Screen = FBox2D(ForceInit);
	if (bScreenOn)
	{
		for (const FVector& Corner : {FVector(ScreenX, -ScreenHalfW, ScreenLo), FVector(ScreenX, ScreenHalfW, ScreenLo),
		                              FVector(ScreenX, -ScreenHalfW, ScreenHi), FVector(ScreenX, ScreenHalfW, ScreenHi)})
		{
			FVector2D Px;
			if (PC->ProjectWorldLocationToScreen(Corner, Px, true))
			{
				Widget->Screen += Px / VP;
			}
		}
	}
	Widget->Holo = FBox2D(ForceInit);
	if (!HoloTable.IsValid())
	{
		TActorIterator<AAstraHoloTable> It(W);
		HoloTable = It ? *It : nullptr;
	}
	if (const AAstraHoloTable* HT = HoloTable.Get())
	{
		FVector O, E;
		HT->GetActorBounds(false, O, E);
		for (int32 c = 0; c < 8; ++c)
		{
			FVector2D Px;
			if (PC->ProjectWorldLocationToScreen(O + E * FVector(c & 1 ? 1 : -1, c & 2 ? 1 : -1, c & 4 ? 1 : -1), Px, true))
			{
				Widget->Holo += Px / VP;
			}
		}
	}
	const TArray<UAstraBattleSubsystem::FContactView>& Cs = B->Contacts();
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
		M.bThreat = C.bFiringAtUs;
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
