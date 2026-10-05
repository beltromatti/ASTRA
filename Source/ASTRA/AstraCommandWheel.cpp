#include "AstraCommandWheel.h"
#include "AstraFonts.h"
#include "ASTRA.h"
#include "ASTRAPlayerController.h"
#include "AstraBattleSubsystem.h"
#include "AstraShipSubsystem.h"
#include "AstraStations.h"
#include "AstraViewscreen.h"
#include "AstraWarClasses.h"
#include "Camera/PlayerCameraManager.h"
#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "Engine/Font.h"
#include "Engine/GameViewportClient.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "Fonts/FontMeasure.h"
#include "Fonts/SlateFontInfo.h"
#include "Framework/Application/SlateApplication.h"
#include "GameFramework/Character.h"
#include "GameFramework/PlayerController.h"
#include "Kismet/GameplayStatics.h"
#include "Sound/SoundBase.h"
#include "Rendering/DrawElements.h"
#include "Styling/CoreStyle.h"
#include "Widgets/SLeafWidget.h"

namespace
{
	constexpr int32 NumItems = 8;
	constexpr float RingX = 300.f, RingY = 185.f;   // the buttons' ring (an ellipse round the middle of the view), px at 1080p
	constexpr float PointerMax = 150.f;   // how far the pointer goes from the centre
	constexpr float DeadPx = 34.f;        // a pointer this close to the centre lights nothing

	TSharedPtr<FJsonObject> StationArgs(const TCHAR* Station, const TCHAR* Aspect, const TCHAR* Mode, const FString& Target = FString())
	{
		TSharedPtr<FJsonObject> A = MakeShared<FJsonObject>();
		A->SetStringField(TEXT("station"), Station);
		if (Aspect)
		{
			A->SetStringField(TEXT("aspect"), Aspect);
		}
		A->SetStringField(TEXT("mode"), Mode);
		A->SetStringField(TEXT("by"), TEXT("captain"));
		A->SetStringField(TEXT("until"), TEXT("order"));
		if (!Target.IsEmpty())
		{
			TSharedPtr<FJsonObject> P = MakeShared<FJsonObject>();
			P->SetStringField(TEXT("target"), Target);
			A->SetObjectField(TEXT("params"), P);
		}
		return A;
	}

	bool Run(UWorld* W, const FString& Name, const TSharedPtr<FJsonObject>& Args, FString& Detail)
	{
		UAstraShipSubsystem* Ship = W ? W->GetSubsystem<UAstraShipSubsystem>() : nullptr;
		return Ship && Ship->ApplyCommand(Name, Args, Detail);
	}

	bool InFlight(const FString& Mode)
	{
		return Mode == TEXT("cap") || Mode == TEXT("escort") || Mode == TEXT("strike") || Mode == TEXT("ew");
	}
}

// ================================================================================================ the widget
class SAstraCommandWheelWidget : public SLeafWidget
{
public:
	SLATE_BEGIN_ARGS(SAstraCommandWheelWidget) {}
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
			const float A = FMath::DegreesToRadians(i * 360.f / NumItems);
			const FVector2D At = C + FVector2D(FMath::Sin(A) * RingX, -FMath::Cos(A) * RingY) * U - BtnSize * 0.5f;
			const bool bLit = i == Lit;
			const FLinearColor Edge = !B.bEnabled ? Dim * 0.6f : (bLit ? Amber : (B.bOn ? Ink : Dim));
			FSlateDrawElement::MakeBox(Out, Layer + 1, G.ToPaintGeometry(BtnSize, FSlateLayoutTransform(At)), White, ESlateDrawEffect::None,
			                           bLit ? FLinearColor(0.16f, 0.10f, 0.02f, 0.92f) : Shade);
			const FVector2D P0 = At, P1 = At + FVector2D(BtnSize.X, 0.f), P2 = At + BtnSize, P3 = At + FVector2D(0.f, BtnSize.Y);
			FSlateDrawElement::MakeLines(Out, Layer + 2, G.ToPaintGeometry(), {P0, P1, P2, P3, P0}, ESlateDrawEffect::None, Edge, true, bLit ? 2.f : 1.f);
			FSlateDrawElement::MakeText(Out, Layer + 3, G.ToPaintGeometry(FVector2D(30.f, 14.f), FSlateLayoutTransform(At + FVector2D(6.f, 4.f) * U)),
			                            FString::FromInt(i + 1), Num, ESlateDrawEffect::None, Dim);
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
		Centred(TEXT("POINT AND LET GO OF G  ·  OR A NUMBER  ·  ESC: NO ORDER"), Num, C.Y + (RingY + 46.f) * U, Dim);
		return Layer + 4;
	}

private:
	FSlateFontInfo Small, Big, Num;
};

// ================================================================================================ the wheel
FString FAstraCommandWheel::PickTarget(APlayerController* PC, FString& OutLine) const
{
	UWorld* W = PC ? PC->GetWorld() : nullptr;
	const UAstraBattleSubsystem* B = W ? W->GetSubsystem<UAstraBattleSubsystem>() : nullptr;
	if (!B)
	{
		return FString();
	}
	auto Line = [](const UAstraBattleSubsystem::FContactView& C, const TCHAR* How)
	{
		return FString::Printf(TEXT("%s|%s %s%s"), How, *C.ContactId, *C.Label.ToUpper(), C.RangeKm >= 0.0 ? *FString::Printf(TEXT(" · %.1f KM"), C.RangeKm) : TEXT(""));
	};
	const TArray<UAstraBattleSubsystem::FContactView>& Cs = B->Contacts();
	auto Hostile = [](const UAstraBattleSubsystem::FContactView& C) { return C.Side == EAstraSide::Mandate && !C.bCraft && !C.bDerelict; };
	// 1. the one he is looking at: the hostile nearest the middle of his view, through the window (a tenth of the screen's width at most)
	FVector2D VP(1920.f, 1080.f);
	if (UGameViewportClient* VC = W->GetGameViewport())
	{
		VC->GetViewportSize(VP);
	}
	const UAstraBattleSubsystem::FContactView* Best = nullptr;
	double BestD = VP.X * 0.1;
	for (const UAstraBattleSubsystem::FContactView& C : Cs)
	{
		FVector2D S;
		if (Hostile(C) && C.Track >= 2 && PC->ProjectWorldLocationToScreen(B->WorldOf(C.Pos), S, true))
		{
			const double D = FVector2D::Distance(S, VP * 0.5);
			if (D < BestD)
			{
				BestD = D;
				Best = &C;
			}
		}
	}
	if (Best)
	{
		OutLine = Line(*Best, TEXT("IN YOUR SIGHT"));
		return Best->ContactId;
	}
	// 2. the one on the main screen, when he is looking at it
	const APlayerCameraManager* Cam = PC->PlayerCameraManager.Get();
	for (TActorIterator<AAstraViewscreen> It(W); It && Cam; ++It)
	{
		const FVector To = (It->GetActorLocation() + FVector(0.f, 0.f, It->HeightM * 50.f) - Cam->GetCameraLocation()).GetSafeNormal();
		const FString Id = It->SubjectId();
		if (!Id.IsEmpty() && FVector::DotProduct(Cam->GetCameraRotation().Vector(), To) > 0.9)
		{
			for (const UAstraBattleSubsystem::FContactView& C : Cs)
			{
				if (C.ContactId == Id && Hostile(C))
				{
					OutLine = Line(C, TEXT("ON THE MAIN SCREEN"));
					return C.ContactId;
				}
			}
		}
	}
	// 3. tactical's, 4. the nearest hostile (the list is nearest first)
	const UAstraStationsSubsystem* St = W->GetSubsystem<UAstraStationsSubsystem>();
	const FString Engaged = St ? St->ActionTarget() : FString();
	for (const UAstraBattleSubsystem::FContactView& C : Cs)
	{
		if (!Engaged.IsEmpty() && C.ContactId == Engaged && Hostile(C))
		{
			OutLine = Line(C, TEXT("TACTICAL'S TARGET"));
			return C.ContactId;
		}
	}
	for (const UAstraBattleSubsystem::FContactView& C : Cs)
	{
		if (Hostile(C) && C.Track >= 2)
		{
			OutLine = Line(C, TEXT("NEAREST HOSTILE"));
			return C.ContactId;
		}
	}
	OutLine = TEXT("TARGET|NO HOSTILE ON THE PLOT");
	return FString();
}

void FAstraCommandWheel::Build(APlayerController* PC)
{
	UWorld* W = PC->GetWorld();
	const UAstraStationsSubsystem* St = W->GetSubsystem<UAstraStationsSubsystem>();
	const UAstraShipSubsystem* Ship = W->GetSubsystem<UAstraShipSubsystem>();
	Items.Reset();
	TargetId = PickTarget(PC, TargetLine);
	const FString T = TargetId;
	const bool bT = !T.IsEmpty();
	auto Mode = [St](const TCHAR* S, const TCHAR* A) { return St ? St->ModeOf(S, A) : FString(); };
	const FString Fire = Mode(TEXT("tactical"), TEXT("engagement"));
	const bool bFiring = Fire == TEXT("weapons_free") || Fire == TEXT("engage");

	// 1 — fire
	{
		FItem I;
		I.Label = bFiring ? TEXT("HOLD FIRE") : TEXT("WEAPONS FREE");
		I.Sub = FString::Printf(TEXT("now: %s"), Fire.IsEmpty() ? TEXT("-") : *Fire.Replace(TEXT("_"), TEXT(" ")).ToUpper());
		I.bOn = bFiring;
		const bool bHold = bFiring;
		I.Run = [W, bHold](FString& D) { return Run(W, TEXT("station"), StationArgs(TEXT("tactical"), TEXT("engagement"), bHold ? TEXT("hold_fire") : TEXT("weapons_free")), D); };
		I.Told = bHold ? TEXT("hold fire") : TEXT("weapons free on every hostile in range");
		Items.Add(I);
	}
	// 2 — engage the target: guns on it, the bow on it
	{
		FItem I;
		I.Label = TEXT("ENGAGE");
		I.Sub = bT ? T + TEXT(": guns and bow on it") : TEXT("no target");
		I.bEnabled = bT;
		// the helm takes her to the range her guns like (the middle of the Aquila's band, classes.json: her rails outreach every Mandate hull there), and a ship
		// that runs is cut off a little inside the band instead of chased from behind (BATTAGLIA-3: 85% of the time in reach against 31%)
		float Band = 24.f, Cut = 16.f;
		if (const AstraWar::FShipClass* Cl = AstraWar::FindClass(TEXT("aquila")); Cl && Cl->RangeMaxKm > 0.f)
		{
			Band = 0.5f * (Cl->RangeMinKm + Cl->RangeMaxKm);
			Cut = FMath::Max(8.f, Cl->RangeMinKm - 2.f);
		}
		bool bRuns = false;
		if (const UAstraBattleSubsystem* B = W ? W->GetSubsystem<UAstraBattleSubsystem>() : nullptr)
		{
			const UAstraBattleSubsystem::FContactView* C = B->Contacts().FindByPredicate([&T](const UAstraBattleSubsystem::FContactView& X) { return X.ContactId == T; });
			bRuns = C && C->bFleeing;
		}
		I.Run = [W, T, Band, Cut, bRuns](FString& D)
		{
			FString D2;
			const bool bA = Run(W, TEXT("station"), StationArgs(TEXT("tactical"), TEXT("engagement"), TEXT("engage"), T), D);
			const TSharedPtr<FJsonObject> H = StationArgs(TEXT("helm"), TEXT("course"), bRuns ? TEXT("intercept") : TEXT("keep_on_bow"), T);
			H->GetObjectField(TEXT("params"))->SetNumberField(TEXT("standoff_km"), bRuns ? Cut : Band);
			const bool bB = Run(W, TEXT("station"), H, D2);
			D = D + TEXT("; ") + D2;
			return bA || bB;
		};
		I.Told = bRuns ? FString::Printf(TEXT("engage %s: tactical's guns on it and the helm cutting it off at %.0f km as it runs"), *T, Cut)
		               : FString::Printf(TEXT("engage %s: tactical's guns on it and the helm keeping the bow on it at %.0f km, the Aquila's own range"), *T, Band);
		Items.Add(I);
	}
	// 3 — a missile salvo: engage it and saturate
	{
		FItem I;
		I.Label = TEXT("MISSILE SALVO");
		I.Sub = bT ? T + TEXT(": saturate its defence") : TEXT("no target");
		I.bEnabled = bT;
		I.bOn = Mode(TEXT("tactical"), TEXT("missiles")) == TEXT("saturate");
		I.Run = [W, T](FString& D)
		{
			FString D2;
			const bool bA = Run(W, TEXT("station"), StationArgs(TEXT("tactical"), TEXT("engagement"), TEXT("engage"), T), D2);
			const bool bB = Run(W, TEXT("station"), StationArgs(TEXT("tactical"), TEXT("missiles"), TEXT("saturate")), D);
			return bA && bB;
		};
		I.Told = FString::Printf(TEXT("missiles on %s, saturating its point defence"), *T);
		Items.Add(I);
	}
	// 4 — the fighters: a strike on the target while they are aboard, home when they are out (one item: the wheel has room for the aim)
	{
		FItem I;
		int32 Out = 0;
		for (const TCHAR* Sq : {TEXT("alpha"), TEXT("bravo"), TEXT("drones")})
		{
			Out += InFlight(Mode(TEXT("flight"), Sq)) ? 1 : 0;
		}
		if (Out > 0)
		{
			I.Label = TEXT("RECALL FIGHTERS");
			I.Sub = FString::Printf(TEXT("%d squadron%s out"), Out, Out > 1 ? TEXT("s") : TEXT(""));
			I.bOn = true;
			I.Run = [W](FString& D)
			{
				bool bAny = false;
				for (const TCHAR* Sq : {TEXT("alpha"), TEXT("bravo"), TEXT("drones")})
				{
					FString D1;
					if (Run(W, TEXT("station"), StationArgs(TEXT("flight"), Sq, TEXT("recall")), D1))
					{
						bAny = true;
						D += (D.IsEmpty() ? TEXT("") : TEXT("; ")) + D1;
					}
				}
				return bAny;
			};
			I.Told = TEXT("every squadron back aboard");
		}
		else
		{
			I.Label = TEXT("FIGHTERS: STRIKE");
			I.Sub = bT ? FString::Printf(TEXT("Alpha, Bravo, drones on %s"), *T) : TEXT("no target");
			I.bEnabled = bT;
			I.Run = [W, T](FString& D)
			{
				bool bAny = false;
				for (const TCHAR* Sq : {TEXT("alpha"), TEXT("bravo"), TEXT("drones")})
				{
					FString D1;
					if (Run(W, TEXT("station"), StationArgs(TEXT("flight"), Sq, TEXT("strike"), T), D1))
					{
						bAny = true;
						D += (D.IsEmpty() ? TEXT("") : TEXT("; ")) + D1;
					}
				}
				return bAny;
			};
			I.Told = FString::Printf(TEXT("all squadrons on a strike on %s"), *T);
		}
		Items.Add(I);
	}
	// 5 — disable, not destroy: the gunners aim at her engines (BATTAGLIA-3's aim: reachable on her quarter, her side or her stern, a ship that runs);
	// a ship left adrift is a hulk the marines can board
	{
		FItem I;
		I.Label = TEXT("DISABLE");
		I.Sub = bT ? T + TEXT(": guns on her engines") : TEXT("no target");
		I.bEnabled = bT;
		I.Run = [W, T](FString& D)
		{
			const TSharedPtr<FJsonObject> A = StationArgs(TEXT("tactical"), TEXT("engagement"), TEXT("engage"), T);
			A->GetObjectField(TEXT("params"))->SetStringField(TEXT("aim"), TEXT("engines"));
			return Run(W, TEXT("station"), A, D);
		};
		I.Told = FString::Printf(TEXT("disable %s: tactical's guns on her engines, to leave her adrift (a prize for the marines), not to destroy her"), *T);
		Items.Add(I);
	}
	// 6 — the shields
	{
		const FString Sh = Mode(TEXT("tactical"), TEXT("shields"));
		const bool bFace = Sh == TEXT("face_threat");
		FItem I;
		I.Label = bFace ? TEXT("SHIELDS BALANCED") : TEXT("SHIELDS TO THREAT");
		I.Sub = FString::Printf(TEXT("now: %s"), Sh.IsEmpty() ? TEXT("-") : *Sh.Replace(TEXT("_"), TEXT(" ")).ToUpper());
		I.bOn = bFace;
		I.Run = [W, bFace](FString& D) { return Run(W, TEXT("station"), StationArgs(TEXT("tactical"), TEXT("shields"), bFace ? TEXT("balanced") : TEXT("face_threat")), D); };
		I.Told = bFace ? TEXT("shields balanced all round") : TEXT("shields to the threat");
		Items.Add(I);
	}
	// 7 — the alert
	{
		const bool bRed = Ship && Ship->GetAlert() == EAstraAlert::Red;
		FItem I;
		I.Label = bRed ? TEXT("STAND DOWN") : TEXT("RED ALERT");
		I.Sub = bRed ? TEXT("now: CONDITION RED") : TEXT("battle stations");
		I.bOn = bRed;
		I.Run = [W, bRed](FString& D)
		{
			TSharedPtr<FJsonObject> A = MakeShared<FJsonObject>();
			A->SetStringField(TEXT("level"), bRed ? TEXT("green") : TEXT("red"));
			A->SetStringField(TEXT("by"), TEXT("captain"));
			return Run(W, TEXT("set_alert"), A, D);
		};
		I.Told = bRed ? TEXT("stand down from red alert") : TEXT("red alert, battle stations");
		Items.Add(I);
	}
	// 8 — the main screen
	{
		const FString Vs = Mode(TEXT("ops"), TEXT("viewscreen"));
		const bool bOnT = Vs == TEXT("target");
		FItem I;
		I.Label = bOnT || !bT ? TEXT("SCREEN: AUTO") : TEXT("SCREEN ON TARGET");
		I.Sub = bOnT || !bT ? TEXT("ops follows the action") : T + TEXT(", held");
		I.bOn = Vs == TEXT("auto");
		const bool bToAuto = bOnT || !bT;
		I.Run = [W, bToAuto, T](FString& D) { return Run(W, TEXT("station"), StationArgs(TEXT("ops"), TEXT("viewscreen"), bToAuto ? TEXT("auto") : TEXT("target"), bToAuto ? FString() : T), D); };
		I.Told = bToAuto ? TEXT("main screen back to following the action") : FString::Printf(TEXT("main screen on %s"), *T);
		Items.Add(I);
	}
}

bool FAstraCommandWheel::Open(APlayerController* PC)
{
	if (bOpen || !PC || !PC->GetWorld() || !Cast<ACharacter>(PC->GetPawn()))
	{
		return false;                        // (a Falcon, a lifepod: the wheel is the Aquila's)
	}
	Build(PC);
	Lit = INDEX_NONE;
	Pointer = FVector2D::ZeroVector;
	bOpen = true;
	PC->SetIgnoreLookInput(true);
	Show(PC);
	return true;
}

void FAstraCommandWheel::Show(APlayerController* PC)
{
	UGameViewportClient* VC = PC->GetWorld()->GetGameViewport();
	if (!VC)
	{
		return;
	}
	if (!Widget.IsValid())
	{
		Widget = SNew(SAstraCommandWheelWidget);
	}
	Widget->Buttons.Reset();
	for (const FItem& I : Items)
	{
		Widget->Buttons.Add({I.Label, I.Sub, I.bOn, I.bEnabled});
	}
	if (!TargetLine.Split(TEXT("|"), &Widget->CentreHow, &Widget->CentreWhat))
	{
		Widget->CentreHow.Reset();
		Widget->CentreWhat = TargetLine;
	}
	Widget->Lit = INDEX_NONE;
	Widget->Pointer = FVector2D::ZeroVector;
	VC->AddViewportWidgetContent(Widget.ToSharedRef(), 30);
}

void FAstraCommandWheel::Hide(APlayerController* PC)
{
	if (Widget.IsValid() && PC && PC->GetWorld())
	{
		if (UGameViewportClient* VC = PC->GetWorld()->GetGameViewport())
		{
			VC->RemoveViewportWidgetContent(Widget.ToSharedRef());
		}
	}
}

void FAstraCommandWheel::Tick(APlayerController* PC, float DeltaTime)
{
	if (!bOpen || !PC)
	{
		return;
	}
	float DX = 0.f, DY = 0.f;
	PC->GetInputMouseDelta(DX, DY);
	Pointer += FVector2D(DX, -DY) * 1.6f;               // (raw mouse counts: a short flick of the wrist lights a button, the ring is never far)
	if (Pointer.Size() > PointerMax)
	{
		Pointer = Pointer.GetSafeNormal() * PointerMax;
	}
	Lit = INDEX_NONE;
	if (Pointer.Size() > DeadPx)
	{
		// clockwise from the top, as the ring is laid out
		const float Deg = FMath::Fmod(FMath::RadiansToDegrees(FMath::Atan2(Pointer.X, -Pointer.Y)) + 360.f + 180.f / NumItems, 360.f);
		Lit = FMath::Clamp(FMath::FloorToInt(Deg / (360.f / NumItems)), 0, NumItems - 1);
		if (!Items.IsValidIndex(Lit) || !Items[Lit].bEnabled)
		{
			Lit = INDEX_NONE;
		}
	}
	if (Widget.IsValid())
	{
		Widget->Lit = Lit;
		Widget->Pointer = Pointer;
	}
}

void FAstraCommandWheel::Execute(APlayerController* PC, int32 Index)
{
	if (!Items.IsValidIndex(Index) || !Items[Index].bEnabled)
	{
		return;
	}
	FItem& I = Items[Index];
	FString Detail;
	const bool bOk = I.Run && I.Run(Detail);
	UE_LOG(LogASTRA, Log, TEXT("[Orders] the Captain, from the command wheel: %s -> %s (%s)"), *I.Label, bOk ? TEXT("done") : TEXT("refused"), *Detail);
	if (USoundBase* Click = LoadObject<USoundBase>(nullptr, bOk ? TEXT("/Game/ASTRA/Audio/SW_Pad_Up.SW_Pad_Up") : TEXT("/Game/ASTRA/Audio/SW_Lock_Beep.SW_Lock_Beep")))
	{
		UGameplayStatics::PlaySound2D(PC, Click, 0.55f);
	}
	if (AASTRAPlayerController* APC = Cast<AASTRAPlayerController>(PC))
	{
		APC->ShowNotice(bOk ? FString::Printf(TEXT("ORDER  ·  %s"), *I.Label) : FString::Printf(TEXT("%s  ·  %s"), *I.Label, *Detail.Left(90).ToUpper()), bOk ? 2.5f : 5.f);
	}
	if (bOk)
	{
		// the bridge hears it was his: the officer at that station answers for it (a fact for the crew's minds, not a script)
		if (UAstraShipSubsystem* Ship = PC->GetWorld()->GetSubsystem<UAstraShipSubsystem>())
		{
			Ship->PublishEvent(FString::Printf(TEXT("bridge: the Captain gave an order from his command wheel, without a word: %s (%s)"), *I.Told, *Detail.Left(160)), true);
		}
	}
}

void FAstraCommandWheel::Close(APlayerController* PC, bool bExecute)
{
	if (!bOpen)
	{
		return;
	}
	bOpen = false;
	Hide(PC);
	if (PC)
	{
		PC->SetIgnoreLookInput(false);
	}
	if (bExecute && Lit != INDEX_NONE)
	{
		Execute(PC, Lit);
	}
	Lit = INDEX_NONE;
}

void FAstraCommandWheel::Pick(APlayerController* PC, int32 Index)
{
	if (!bOpen || !Items.IsValidIndex(Index) || !Items[Index].bEnabled)
	{
		return;
	}
	Lit = Index;
	Close(PC, true);
}
