#include "AstraFpsHud.h"

#include "Engine/Font.h"
#include "Fonts/FontMeasure.h"
#include "Framework/Application/SlateApplication.h"
#include "Rendering/DrawElements.h"
#include "Rendering/SlateRenderer.h"
#include "Styling/CoreStyle.h"

namespace
{
	/** A key and what it does, for the card that is up when he arms. */
	struct FKeyHint { const TCHAR* Key; const TCHAR* What; };
	const FKeyHint FpsKeysWeapon[] = {{TEXT("LMB"), TEXT("fire")}, {TEXT("RMB"), TEXT("aim")}, {TEXT("R"), TEXT("reload")}, {TEXT("1"), TEXT("rifle")}, {TEXT("2"), TEXT("sidearm")}, {TEXT("Q"), TEXT("last weapon")}, {TEXT("H"), TEXT("holster")}};
	const FKeyHint FpsKeysMove[] = {{TEXT("W A S D"), TEXT("move")}, {TEXT("Shift"), TEXT("run")}, {TEXT("C"), TEXT("crouch")}, {TEXT("hold C"), TEXT("prone")}, {TEXT("Space"), TEXT("jump")}, {TEXT("E"), TEXT("use")}, {TEXT("F1"), TEXT("all keys")}};
}

void SAstraCombatHud::Construct(const FArguments&)
{
	UFont* Mono = LoadObject<UFont>(nullptr, TEXT("/Game/ASTRA/UI/Fonts/F_ASTRA_Mono.F_ASTRA_Mono"));
	UFont* Title = LoadObject<UFont>(nullptr, TEXT("/Game/ASTRA/UI/Fonts/F_ASTRA_Title.F_ASTRA_Title"));
	Small = Mono ? FSlateFontInfo(Mono, 11) : FCoreStyle::GetDefaultFontStyle("Mono", 11);
	Mid = Title ? FSlateFontInfo(Title, 14) : FCoreStyle::GetDefaultFontStyle("Regular", 14);
	Cap = Mono ? FSlateFontInfo(Mono, 12) : FCoreStyle::GetDefaultFontStyle("Mono", 12);
	Big = Title ? FSlateFontInfo(Title, 26) : FCoreStyle::GetDefaultFontStyle("Bold", 26);
}

int32 SAstraCombatHud::OnPaint(const FPaintArgs&, const FGeometry& G, const FSlateRect&, FSlateWindowElementList& Out, int32 Layer, const FWidgetStyle&, bool) const
{
	if (!State.bShow)
	{
		return Layer;
	}
	const FVector2D Size = G.GetLocalSize();
	const float U = FMath::Max(0.5f, Size.Y / 1080.f);
	const FVector2D C = Size * 0.5;
	const FSlateBrush* White = FCoreStyle::Get().GetBrush("WhiteBrush");
	const auto Box = [&](const FVector2D& Pos, const FVector2D& Sz, const FLinearColor& Col, int32 L)
	{
		FSlateDrawElement::MakeBox(Out, L, G.ToPaintGeometry(Sz, FSlateLayoutTransform(Pos)), White, ESlateDrawEffect::None, Col);
	};
	const auto Line = [&](const FVector2D& A, const FVector2D& B, const FLinearColor& Col, float Th, int32 L)
	{
		FSlateDrawElement::MakeLines(Out, L, G.ToPaintGeometry(), {A, B}, ESlateDrawEffect::None, Col, true, Th * U);
	};
	const auto Text = [&](const FString& T, const FVector2D& Pos, const FSlateFontInfo& F, const FLinearColor& Col, int32 L)
	{
		FSlateDrawElement::MakeText(Out, L, G.ToPaintGeometry(FVector2D(900.f, 60.f), FSlateLayoutTransform(Pos)), T, F, ESlateDrawEffect::None, Col);
	};
	int32 L = Layer;
	// the red at the edges: layers of thin bands, each fainter than the last, as the pain is
	if (State.HurtAlpha > 0.01f)
	{
		for (int32 i = 0; i < 9; ++i)
		{
			const float T = (float)i / 9.f;
			const float A = State.HurtAlpha * 0.34f * FMath::Square(1.f - T);
			const float W = (10.f + 22.f * i) * U;
			const FLinearColor Red(0.62f, 0.02f, 0.02f, A);
			Box(FVector2D(0, 0), FVector2D(Size.X, W * 0.5f), Red, L);
			Box(FVector2D(0, Size.Y - W * 0.5f), FVector2D(Size.X, W * 0.5f), Red, L);
			Box(FVector2D(0, 0), FVector2D(W * 0.5f, Size.Y), Red, L);
			Box(FVector2D(Size.X - W * 0.5f, 0), FVector2D(W * 0.5f, Size.Y), Red, L);
		}
	}
	// where it came from: a short red arc at the edge of the picture, towards it
	for (const FAstraFpsHudState::FArc& Arc : State.Arcs)
	{
		if (Arc.Alpha <= 0.02f)
		{
			continue;
		}
		const float R0 = FMath::DegreesToRadians(Arc.Yaw - 18.f), R1 = FMath::DegreesToRadians(Arc.Yaw + 18.f);
		TArray<FVector2D> Pts;
		for (int32 k = 0; k <= 6; ++k)
		{
			const float A = FMath::Lerp(R0, R1, k / 6.f);
			// 0 is straight ahead (up the screen), 90 degrees on his right
			Pts.Add(C + FVector2D(FMath::Sin(A) * Size.X * 0.30f, -FMath::Cos(A) * Size.Y * 0.36f));
		}
		FSlateDrawElement::MakeLines(Out, L + 1, G.ToPaintGeometry(), Pts, ESlateDrawEffect::None, FLinearColor(0.95f, 0.1f, 0.06f, Arc.Alpha * 0.9f), true, 7.f * U);
	}
	// the crosshair: it opens with his cone; looking through the sights only a dot
	if (State.bCrosshair)
	{
		const FLinearColor White85(1.f, 1.f, 1.f, 0.82f);
		if (!State.bAds)
		{
			const float Gap = State.SpreadPx * U, Len = 9.f * U;
			Line(C + FVector2D(Gap, 0), C + FVector2D(Gap + Len, 0), White85, 1.6f, L + 2);
			Line(C - FVector2D(Gap, 0), C - FVector2D(Gap + Len, 0), White85, 1.6f, L + 2);
			Line(C + FVector2D(0, Gap), C + FVector2D(0, Gap + Len), White85, 1.6f, L + 2);
			Line(C - FVector2D(0, Gap), C - FVector2D(0, Gap + Len), White85, 1.6f, L + 2);
		}
		Box(C - FVector2D(1.f * U, 1.f * U), FVector2D(2.f * U, 2.f * U), FLinearColor(1.f, 1.f, 1.f, State.bAds ? 0.55f : 0.9f), L + 2);
		if (State.HitMark > 0.02f)
		{
			const FLinearColor Mark = State.bHitHead ? FLinearColor(1.f, 0.25f, 0.12f, State.HitMark) : FLinearColor(1.f, 1.f, 1.f, State.HitMark);
			const float A = (9.f + (1.f - State.HitMark) * 6.f) * U, B = (16.f + (1.f - State.HitMark) * 6.f) * U;
			for (const FVector2D& D : {FVector2D(1, 1), FVector2D(-1, 1), FVector2D(1, -1), FVector2D(-1, -1)})
			{
				Line(C + D * A, C + D * B, Mark, 2.2f, L + 3);
			}
		}
		if (State.bLowHint)
		{
			Text(TEXT("R  RELOAD"), C + FVector2D(-34.f * U, 40.f * U), Small, FLinearColor(1.f, 0.78f, 0.3f, 0.9f), L + 2);
		}
	}
	// the weapon: its name and the rounds, bottom right
	if (!State.WeaponName.IsEmpty())
	{
		const bool bEmpty = State.Mag <= 0;
		const bool bLow = !bEmpty && State.Mag <= FMath::Max(3, State.MagSize / 4);
		const FLinearColor Col = bEmpty ? FLinearColor(1.f, 0.28f, 0.2f) : (bLow ? FLinearColor(1.f, 0.78f, 0.3f) : FLinearColor(0.9f, 0.95f, 1.f));
		const FVector2D P(Size.X - 250.f * U, Size.Y - 120.f * U);
		Text(State.WeaponName, P, Small, FLinearColor(0.62f, 0.7f, 0.8f, 0.9f), L + 2);
		Text(FString::Printf(TEXT("%d"), State.Mag), P + FVector2D(0.f, 14.f * U), Big, Col, L + 2);
		Text(FString::Printf(TEXT("/ %d"), State.Reserve), P + FVector2D(70.f * U, 26.f * U), Mid, FLinearColor(0.7f, 0.76f, 0.85f, 0.9f), L + 2);
		// the rounds as little ticks
		const int32 N = FMath::Clamp(State.MagSize, 1, 40);
		const float Tw = FMath::Min(5.f, 190.f / N) * U;
		for (int32 i = 0; i < N; ++i)
		{
			const bool bOn = i < FMath::Min(State.Mag, N);
			Box(P + FVector2D(i * Tw, 62.f * U), FVector2D(FMath::Max(1.f, Tw - 1.5f * U), 4.f * U), bOn ? FLinearColor(Col.R, Col.G, Col.B, 0.85f) : FLinearColor(0.3f, 0.34f, 0.4f, 0.4f), L + 2);
		}
		if (State.bReloading)
		{
			Box(P + FVector2D(0.f, 74.f * U), FVector2D(190.f * U, 3.f * U), FLinearColor(0.2f, 0.24f, 0.3f, 0.6f), L + 2);
			Box(P + FVector2D(0.f, 74.f * U), FVector2D(190.f * U * FMath::Clamp(State.ReloadAlpha, 0.f, 1.f), 3.f * U), FLinearColor(0.9f, 0.95f, 1.f, 0.9f), L + 3);
		}
	}
	// how he is, bottom left: when he is hurt or the fight is on
	if (State.bShowStrength)
	{
		const FVector2D P(90.f * U, Size.Y - 100.f * U);
		const float S = FMath::Clamp(State.Strength, 0.f, 1.f);
		const FLinearColor Col = S > 0.6f ? FLinearColor(0.5f, 0.9f, 0.6f) : (S > 0.3f ? FLinearColor(1.f, 0.78f, 0.3f) : FLinearColor(1.f, 0.28f, 0.2f));
		Text(State.bDown ? TEXT("DOWN") : TEXT("STRENGTH"), P, Small, FLinearColor(Col.R, Col.G, Col.B, 0.95f), L + 2);
		Box(P + FVector2D(0.f, 18.f * U), FVector2D(220.f * U, 6.f * U), FLinearColor(0.2f, 0.24f, 0.3f, 0.55f), L + 2);
		Box(P + FVector2D(0.f, 18.f * U), FVector2D(220.f * U * S, 6.f * U), FLinearColor(Col.R, Col.G, Col.B, 0.9f), L + 3);
	}
	// the prompt of the key at hand, and the strip of keys
	if (State.PromptAlpha > 0.02f && !State.Prompt.IsEmpty())
	{
		Text(State.Prompt, FVector2D(C.X - 200.f * U, Size.Y * 0.70f), Mid, FLinearColor(0.95f, 0.97f, 1.f, State.PromptAlpha), L + 2);
	}
	if (State.KeysAlpha > 0.02f)
	{
		// the card: two columns of keys on caps (the weapon's and the walking ones), at the top left. Not at the bottom: the lower middle is where the crew's subtitles stand (the
		// controller's: up to three rows of up to three lines, from 60 px above the edge to some 310 px) and the lower right has the walking notice and the rounds
		const TSharedRef<FSlateFontMeasure> Measure = FSlateApplication::Get().GetRenderer()->GetFontMeasureService();
		const float A = State.KeysAlpha;
		const float RowH = 26.f * U, HeadH = 24.f * U, Pad = 12.f * U, CapPad = 7.f * U, After = 8.f * U, ColGap = 28.f * U;
		const auto ColWidth = [&](const FKeyHint* Col, int32 N)
		{
			float W = 0.f;
			for (int32 i = 0; i < N; ++i)
			{
				W = FMath::Max(W, Measure->Measure(FString(Col[i].Key), Cap).X + 2.f * CapPad + After + Measure->Measure(FString(Col[i].What), Cap).X);
			}
			return W;
		};
		FKeyHint WeaponRows[UE_ARRAY_COUNT(FpsKeysWeapon)];
		int32 NW = 0;
		for (const FKeyHint& K : FpsKeysWeapon)
		{
			if (State.bRifle || FCString::Strcmp(K.What, TEXT("rifle")) != 0)
			{
				WeaponRows[NW++] = K;
			}
		}
		constexpr int32 NM = UE_ARRAY_COUNT(FpsKeysMove);
		const float W1 = ColWidth(WeaponRows, NW), W2 = ColWidth(FpsKeysMove, NM);
		const float W = 2.f * Pad + W1 + ColGap + W2;
		const float H = 1.5f * Pad + HeadH + FMath::Max(NW, NM) * RowH;
		const FVector2D Origin(24.f * U, 24.f * U);
		Box(Origin, FVector2D(W, H), FLinearColor(0.004f, 0.006f, 0.01f, 0.62f * A), L + 1);
		const auto DrawColumn = [&](const TCHAR* Head, const FKeyHint* Col, int32 N, float X0)
		{
			Text(Head, FVector2D(X0, Origin.Y + 0.75f * Pad), Small, FLinearColor(0.62f, 0.7f, 0.8f, 0.9f * A), L + 3);
			float Y = Origin.Y + 0.75f * Pad + HeadH;
			for (int32 i = 0; i < N; ++i, Y += RowH)
			{
				const float KW = Measure->Measure(FString(Col[i].Key), Cap).X;
				Box(FVector2D(X0, Y + 1.f * U), FVector2D(KW + 2.f * CapPad, RowH - 2.f * U), FLinearColor(0.46f, 0.52f, 0.6f, 0.9f * A), L + 2);
				Box(FVector2D(X0 + 1.f * U, Y + 2.f * U), FVector2D(KW + 2.f * CapPad - 2.f * U, RowH - 4.f * U), FLinearColor(0.1f, 0.125f, 0.16f, 0.96f * A), L + 2);
				Text(Col[i].Key, FVector2D(X0 + CapPad, Y + 5.f * U), Cap, FLinearColor(0.96f, 0.98f, 1.f, A), L + 3);
				Text(Col[i].What, FVector2D(X0 + KW + 2.f * CapPad + After, Y + 5.f * U), Cap, FLinearColor(0.7f, 0.78f, 0.88f, 0.95f * A), L + 3);
			}
		};
		DrawColumn(TEXT("WEAPON"), WeaponRows, NW, Origin.X + Pad);
		DrawColumn(TEXT("MOVING"), FpsKeysMove, NM, Origin.X + Pad + W1 + ColGap);
	}
	return L + 4;
}
