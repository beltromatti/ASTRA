#include "AstraEquipmentWheel.h"
#include "ASTRAPlayerController.h"
#include "AstraFpsComponent.h"
#include "AstraFonts.h"
#include "Engine/Font.h"
#include "Engine/GameViewportClient.h"
#include "Engine/World.h"
#include "GameFramework/Character.h"
#include "Fonts/FontMeasure.h"
#include "Fonts/SlateFontInfo.h"
#include "Framework/Application/SlateApplication.h"
#include "Rendering/DrawElements.h"
#include "Styling/CoreStyle.h"
#include "Widgets/SLeafWidget.h"
namespace
{
    constexpr int32 EquipNumItems = 4;
    constexpr float EquipRingX = 300.f, EquipRingY = 185.f;
}
class SAstraEquipmentWheelWidget : public SLeafWidget
{
public:
	SLATE_BEGIN_ARGS(SAstraEquipmentWheelWidget) {}
	SLATE_END_ARGS()

	struct FButton { FString Label, Sub; bool bOn = false, bEnabled = true; };
	TArray<FButton> Buttons;
	int32 Lit = INDEX_NONE;
	FVector2D Pointer = FVector2D::ZeroVector;
	FString CentreHow, CentreWhat;        // where the target comes from ("ON THE MAIN SCREEN"), and which it is

	void Construct(const FArguments&)
	{
		UFont* Mono = AstraFonts::Mono();
		UFont* Title = AstraFonts::Title();
		Small = Mono ? FSlateFontInfo(Mono, 10) : FCoreStyle::GetDefaultFontStyle("Mono", 10);
		Big = Title ? FSlateFontInfo(Title, 15) : FCoreStyle::GetDefaultFontStyle("Bold", 15);
		Num = Mono ? FSlateFontInfo(Mono, 9) : FCoreStyle::GetDefaultFontStyle("Mono", 9);
	}

	virtual FVector2D ComputeDesiredSize(float) const override { return FVector2D(100.f, 100.f); }

	virtual int32 OnPaint(const FPaintArgs&, const FGeometry& G, const FSlateRect&, FSlateWindowElementList& Out, int32 Layer,
	                      const FWidgetStyle&, bool) const override
	{
		const FVector2D Size = G.GetLocalSize();
		const float U = Size.Y / 1080.f;
		const FVector2D C = Size * 0.5f;
		const FSlateBrush* White = FCoreStyle::Get().GetBrush("GenericWhiteBox");
		const FLinearColor Ink(0.62f, 0.86f, 1.f), Dim(0.30f, 0.42f, 0.55f), Amber(1.f, 0.72f, 0.28f), Shade(0.01f, 0.02f, 0.04f, 0.78f);
		const FVector2D BtnSize(236.f * U, 52.f * U);
		const TSharedRef<FSlateFontMeasure> Measure = FSlateApplication::Get().GetRenderer()->GetFontMeasureService();
		auto Centred = [&](const FString& Text, const FSlateFontInfo& Font, float Y, const FLinearColor& Col)
		{
			const FVector2D Sz = Measure->Measure(Text, Font) * G.Scale;
			FSlateDrawElement::MakeText(Out, Layer + 3, G.ToPaintGeometry(FVector2D(Sz.X / G.Scale + 4.f, 24.f), FSlateLayoutTransform(FVector2D(C.X - Sz.X * 0.5f / G.Scale, Y))),
			                            Text, Font, ESlateDrawEffect::None, Col);
		};
		for (int32 i = 0; i < Buttons.Num(); ++i)
		{
			const FButton& B = Buttons[i];
			const float A = FMath::DegreesToRadians(i * 360.f / EquipNumItems);
			const FVector2D At = C + FVector2D(FMath::Sin(A) * EquipRingX, -FMath::Cos(A) * EquipRingY) * U - BtnSize * 0.5f;
			const bool bLit = i == Lit;
			const FLinearColor Edge = !B.bEnabled ? Dim * 0.6f : (bLit ? Amber : (B.bOn ? Ink : Dim));
			FSlateDrawElement::MakeBox(Out, Layer + 1, G.ToPaintGeometry(BtnSize, FSlateLayoutTransform(At)), White, ESlateDrawEffect::None,
			                           bLit ? FLinearColor(0.16f, 0.10f, 0.02f, 0.92f) : Shade);
			const FVector2D P0 = At, P1 = At + FVector2D(BtnSize.X, 0.f), P2 = At + BtnSize, P3 = At + FVector2D(0.f, BtnSize.Y);
			FSlateDrawElement::MakeLines(Out, Layer + 2, G.ToPaintGeometry(), {P0, P1, P2, P3, P0}, ESlateDrawEffect::None, Edge, true, bLit ? 2.f : 1.f);

			FSlateDrawElement::MakeText(Out, Layer + 3, G.ToPaintGeometry(FVector2D(BtnSize.X, 20.f), FSlateLayoutTransform(At + FVector2D(22.f, 6.f) * U)),
			                            B.Label, Big, ESlateDrawEffect::None, B.bEnabled ? (bLit ? Amber : FLinearColor(0.92f, 0.96f, 1.f)) : Dim);
			FSlateDrawElement::MakeText(Out, Layer + 3, G.ToPaintGeometry(FVector2D(BtnSize.X, 14.f), FSlateLayoutTransform(At + FVector2D(22.f, 30.f) * U)),
			                            B.Sub, Small, ESlateDrawEffect::None, B.bOn ? Ink : Dim);
		}
		// the target in the middle (where it comes from, then which it is) on a dark band, and the pointer
		FSlateDrawElement::MakeBox(Out, Layer + 1, G.ToPaintGeometry(FVector2D(330.f * U, 44.f * U), FSlateLayoutTransform(C - FVector2D(165.f, 30.f) * U)), White,
		                           ESlateDrawEffect::None, Shade);
		Centred(CentreHow, Num, C.Y - 26.f * U, Dim);
		Centred(CentreWhat, Big, C.Y - 10.f * U, Ink);
		const FVector2D Pt = C + Pointer * U;
		FSlateDrawElement::MakeLines(Out, Layer + 4, G.ToPaintGeometry(), {Pt - FVector2D(7.f, 0.f) * U, Pt + FVector2D(7.f, 0.f) * U}, ESlateDrawEffect::None, Amber, true, 2.f);
		FSlateDrawElement::MakeLines(Out, Layer + 4, G.ToPaintGeometry(), {Pt - FVector2D(0.f, 7.f) * U, Pt + FVector2D(0.f, 7.f) * U}, ESlateDrawEffect::None, Amber, true, 2.f);
		Centred(TEXT("POINT AND LET GO OF Q  ·  ESC: CANCEL"), Num, C.Y + (EquipRingY + 46.f) * U, Dim);
		return Layer + 4;
	}

private:
	FSlateFontInfo Small, Big, Num;
};


bool FAstraEquipmentWheel::Open(AASTRAPlayerController* PC)
{
    if (bOpen || !PC || PC->IsSeated() || PC->IsCinematic() || !Cast<ACharacter>(PC->GetPawn()) || PC->IsMoveInputIgnored()) { return false; }
    auto* Fps = PC->GetPawn()->FindComponentByClass<UAstraFpsComponent>();
    auto* VC = PC->GetWorld()->GetGameViewport();
    if (!Fps || !VC) { return false; }
    if (!Widget.IsValid()) { Widget = SNew(SAstraEquipmentWheelWidget); }
    Widget->Buttons.Reset();
    auto Weapon = [&](EAstraWeapon Kind, const TCHAR* Name)
    {
        const bool bOwned = Fps->Carries(Kind);
        Widget->Buttons.Add({Name, bOwned ? FString::Printf(TEXT("%d / %d ROUNDS"), Fps->Rounds(Kind), Fps->Spare(Kind)) : FString(TEXT("DECK 8 · ASK THE ARMOURER")),
                            bOwned && Fps->IsArmed() && Fps->Current() == Kind && !PC->IsPadUp(), bOwned});
    };
    Weapon(EAstraWeapon::Rifle, TEXT("AR-181 RIFLE"));
    Weapon(EAstraWeapon::Pistol, TEXT("SIDEARM"));
    Widget->Buttons.Add({TEXT("DATAPAD"), TEXT("PERSONAL · TAB ALSO OPENS IT"), PC->IsPadUp(), true});
    Widget->Buttons.Add({TEXT("EMPTY HANDS"), TEXT("PUT YOUR EQUIPMENT AWAY"), !PC->IsPadUp() && !Fps->IsArmed(), true});
    Widget->CentreHow = TEXT("CAPTAIN'S EQUIPMENT");
    Widget->CentreWhat = TEXT("CHOOSE WHAT YOU CARRY");
    Widget->Lit = Lit = INDEX_NONE;
    Widget->Pointer = Pointer = FVector2D::ZeroVector;
    Fps->FireReleased();
    Fps->AimReleased();
    PC->SetIgnoreLookInput(true);
    PC->SetIgnoreMoveInput(true);
    VC->AddViewportWidgetContent(Widget.ToSharedRef(), 35);
    bOpen = true;
    return true;
}

void FAstraEquipmentWheel::Tick(AASTRAPlayerController* PC, float DeltaTime)
{
    if (!bOpen || !PC) { return; }
    float DX = 0.f, DY = 0.f;
    PC->GetInputMouseDelta(DX, DY);
    Pointer += FVector2D(DX, -DY) * 1.6f;
    if (Pointer.Size() > 150.f) { Pointer = Pointer.GetSafeNormal() * 150.f; }
    Lit = INDEX_NONE;
    if (Pointer.Size() > 34.f)
    {
        const float Deg = FMath::Fmod(FMath::RadiansToDegrees(FMath::Atan2(Pointer.X, -Pointer.Y)) + 405.f, 360.f);
        Lit = FMath::Clamp(FMath::FloorToInt(Deg / 90.f), 0, 3);
        if (!Widget->Buttons[Lit].bEnabled) { Lit = INDEX_NONE; }
    }
    Widget->Lit = Lit;
    Widget->Pointer = Pointer;
}

void FAstraEquipmentWheel::Close(AASTRAPlayerController* PC, bool bExecute)
{
    if (!bOpen) { return; }
    bOpen = false;
    if (PC)
    {
        if (auto* VC = PC->GetWorld() ? PC->GetWorld()->GetGameViewport() : nullptr) { VC->RemoveViewportWidgetContent(Widget.ToSharedRef()); }
        PC->SetIgnoreLookInput(false);
        PC->SetIgnoreMoveInput(false);
        if (bExecute && Lit != INDEX_NONE) { Execute(PC, Lit); }
    }
    Lit = INDEX_NONE;
}

void FAstraEquipmentWheel::Execute(AASTRAPlayerController* PC, int32 Index)
{
    auto* Fps = PC->GetPawn() ? PC->GetPawn()->FindComponentByClass<UAstraFpsComponent>() : nullptr;
    if (!Fps) { return; }
    if (Index == 2) { PC->SetPadRaised(true); }
    else
    {
        PC->SetPadRaised(false);
        if (Index == 3) { if (Fps->IsArmed()) { Fps->ToggleHolster(); } }
        else
        {
            const EAstraWeapon Kind = Index == 0 ? EAstraWeapon::Rifle : EAstraWeapon::Pistol;
            if (Fps->Carries(Kind) && !(Fps->IsArmed() && Fps->Current() == Kind)) { Fps->SelectWeapon(Kind); }
        }
    }
}
