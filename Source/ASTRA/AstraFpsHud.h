// ASTRA — ABBORDAGGI: the screen of a Captain with a weapon in his hands: a quiet overlay, like the window's (AstraWindowHud.*): the crosshair (it opens with the cone his
// rounds go in), the rounds, how he is (the strength bar when he is hurt or a fight is on), the red at the edges and the arcs that say where a round came from, the white cross of a
// round that struck, the prompt of the key at hand and the strip of keys that is up for a while when he arms (F1 has the whole card). UAstraFpsComponent owns one and fills its state
// every frame.

#pragma once

#include "CoreMinimal.h"
#include "Fonts/SlateFontInfo.h"
#include "Widgets/SLeafWidget.h"

struct FAstraFpsHudState
{
	bool bShow = false;                  // anything at all (a weapon in his hands, hurt, a prompt)
	bool bCrosshair = false;
	bool bAds = false;
	float SpreadPx = 6.f;                // half the gap between the crosshair's ticks (px at 1080p)
	FString WeaponName;                  // "AR-181"
	int32 Mag = 0, Reserve = 0, MagSize = 30;
	bool bReloading = false;
	float ReloadAlpha = 0.f;             // 0..1 through the reload
	float Strength = 1.f;                // 0..1
	bool bShowStrength = false;
	bool bDown = false;
	float HurtAlpha = 0.f;               // the red at the edges
	struct FArc { float Yaw = 0.f; float Alpha = 0.f; };
	TArray<FArc> Arcs;                   // degrees round the view (0 ahead, 90 on his right)
	float HitMark = 0.f;                 // 0..1
	bool bHitHead = false;
	FString Prompt;
	float PromptAlpha = 0.f;
	float KeysAlpha = 0.f;
	FString Keys;
	bool bLowHint = false;               // "R  RELOAD"
};

class SAstraCombatHud : public SLeafWidget
{
public:
	SLATE_BEGIN_ARGS(SAstraCombatHud) {}
	SLATE_END_ARGS()

	FAstraFpsHudState State;

	void Construct(const FArguments&);
	virtual FVector2D ComputeDesiredSize(float) const override { return FVector2D(100.f, 100.f); }
	virtual int32 OnPaint(const FPaintArgs&, const FGeometry& G, const FSlateRect&, FSlateWindowElementList& Out, int32 Layer, const FWidgetStyle&, bool) const override;

private:
	FSlateFontInfo Small, Big, Mid;
};
