// ASTRA — live bridge screens.

#include "AstraScreensSubsystem.h"

#include "ASTRA.h"
#include "AstraBattleSubsystem.h"
#include "AstraShipSubsystem.h"
#include "CanvasItem.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/Canvas.h"
#include "Engine/CanvasRenderTarget2D.h"
#include "Engine/Font.h"
#include "EngineUtils.h"
#include "Fonts/FontMeasure.h"
#include "Framework/Application/SlateApplication.h"
#include "Materials/MaterialInstance.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "RenderingThread.h"

namespace
{
	// diagnostics: time each page's redraw including the render thread's work (blocks the game thread while on)
	TAutoConsoleVariable<int32> CVarScreensProfile(TEXT("astra.screens.profile"), 0, TEXT("Log the cost of each bridge screen redraw"));
	FLinearColor RGB(uint8 R, uint8 G, uint8 B, float A = 1.f)
	{
		FLinearColor C(FColor(R, G, B));
		C.A = A;
		return C;
	}

	const FLinearColor BG = RGB(4, 9, 18);
	const FLinearColor PANEL = RGB(10, 22, 40);
	const FLinearColor LINE = RGB(70, 140, 210);
	const FLinearColor DIM = RGB(40, 80, 125);
	const FLinearColor TEXTC = RGB(205, 228, 255);
	const FLinearColor CYAN = RGB(111, 195, 255);
	const FLinearColor AMBER = RGB(255, 179, 71);
	const FLinearColor RED = RGB(255, 74, 46);
	const FLinearColor GREEN = RGB(80, 220, 150);
	const FLinearColor YELLOW = RGB(255, 214, 10);
	const FLinearColor HEADER = RGB(6, 14, 28);
	const FLinearColor COMMAND = RGB(62, 123, 250);
	const FLinearColor ENGINEERING = RGB(255, 159, 28);
	const FLinearColor SCIENCE = RGB(155, 93, 229);

	FLinearColor Level(float Frac)   // a resource: low is bad
	{
		return Frac < 0.25f ? RED : (Frac < 0.5f ? AMBER : CYAN);
	}

	/** Thin drawing helper over a UCanvas, in render-target pixels. */
	struct FPaint
	{
		UCanvas* C = nullptr;
		UFont* Title = nullptr;
		UFont* Mono = nullptr;
		float Time = 0.f;

		void Rect(float X, float Y, float W, float H, const FLinearColor& Col) const
		{
			FCanvasTileItem T(FVector2D(X, Y), FVector2D(W, H), Col);
			T.BlendMode = Col.A < 1.f ? SE_BLEND_Translucent : SE_BLEND_Opaque;
			C->DrawItem(T);
		}
		void Frame(float X, float Y, float W, float H, const FLinearColor& Col, float Thick = 1.f) const
		{
			FCanvasBoxItem B(FVector2D(X, Y), FVector2D(W, H));
			B.SetColor(Col);
			B.LineThickness = Thick;
			C->DrawItem(B);
		}
		void Line(float X0, float Y0, float X1, float Y1, const FLinearColor& Col, float Thick = 1.f) const
		{
			FCanvasLineItem L(FVector2D(X0, Y0), FVector2D(X1, Y1));
			L.SetColor(Col);
			L.LineThickness = Thick;
			C->DrawItem(L);
		}
		FSlateFontInfo Font(bool bMono, float Px, bool bBold = false) const
		{
			// sizes are given in pixels like the static screens (PIL); Slate sizes are points at 96 dpi
			return FSlateFontInfo(bMono ? Mono : Title, FMath::RoundToInt(Px * 0.75f), bMono ? (bBold ? TEXT("Bold") : TEXT("Regular")) : TEXT("Regular"));
		}
		float Width(const FString& S, const FSlateFontInfo& F) const
		{
			if (!FSlateApplication::IsInitialized())
			{
				return S.Len() * F.Size * 0.8f;
			}
			return FSlateApplication::Get().GetRenderer()->GetFontMeasureService()->Measure(S, F).X;
		}
		/** Align: 0 left, 1 centre, 2 right. Y is the top of the text. */
		void Text(float X, float Y, const FString& S, bool bMono, float Px, const FLinearColor& Col, int32 Align = 0, bool bBold = false) const
		{
			const FSlateFontInfo F = Font(bMono, Px, bBold);
			const float W = Align ? Width(S, F) : 0.f;
			FCanvasTextItem T(FVector2D(X - (Align == 1 ? W * 0.5f : (Align == 2 ? W : 0.f)), Y), FText::FromString(S), F, Col);
			T.BlendMode = SE_BLEND_Translucent;
			C->DrawItem(T);
		}
		void Brackets(float X0, float Y0, float X1, float Y1, const FLinearColor& Col, float L = 14.f) const
		{
			Line(X0, Y0, X0 + L, Y0, Col, 2.f); Line(X0, Y0, X0, Y0 + L, Col, 2.f);
			Line(X1, Y0, X1 - L, Y0, Col, 2.f); Line(X1, Y0, X1, Y0 + L, Col, 2.f);
			Line(X0, Y1, X0 + L, Y1, Col, 2.f); Line(X0, Y1, X0, Y1 - L, Col, 2.f);
			Line(X1, Y1, X1 - L, Y1, Col, 2.f); Line(X1, Y1, X1, Y1 - L, Col, 2.f);
		}
		void Panel(float X0, float Y0, float X1, float Y1, const FString& Label = FString()) const
		{
			Rect(X0, Y0, X1 - X0, Y1 - Y0, PANEL);
			Frame(X0, Y0, X1 - X0, Y1 - Y0, DIM);
			Brackets(X0, Y0, X1, Y1, LINE);
			if (!Label.IsEmpty())
			{
				Text(X0 + 10, Y0 + 5, Label.ToUpper(), false, 17, CYAN);
				Line(X0 + 10, Y0 + 28, X1 - 10, Y0 + 28, DIM);
			}
		}
		void Header(float W, const FString& TitleText, const FString& Sub, const FLinearColor& Accent) const
		{
			Rect(0, 0, W, 44, HEADER);
			Rect(0, 0, 8, 44, Accent);
			Text(20, 6, TitleText.ToUpper(), false, 28, TEXTC);
			Text(W - 16, 12, Sub, true, 15, CYAN, 2);
			Line(0, 44, W, 44, Accent, 2.f);
		}
		void Footer(float W, float H, const FString& S, const FLinearColor& Col) const
		{
			Rect(0, H - 28, W, 28, HEADER);
			Text(16, H - 25, S.Left(int32(W / 9.f)), true, 14, Col);
		}
		/** Segmented bar with a label on the left and a value on the right. */
		void Bar(float X, float Y, float W, float H, float Frac, const FString& Label, const FString& Value, const FLinearColor& Col) const
		{
			Text(X, Y - 2, Label.ToUpper(), false, 17, TEXTC);
			Text(X + W, Y - 2, Value, true, 16, Col, 2);
			const float YB = Y + 22;
			Rect(X, YB, W, H, RGB(6, 12, 24));
			Frame(X, YB, W, H, DIM);
			const int32 Segs = 40;
			const float SW = W / Segs;
			const int32 N = FMath::Clamp(FMath::RoundToInt(Frac * Segs), 0, Segs);
			for (int32 i = 0; i < N; ++i)
			{
				Rect(X + i * SW + 1, YB + 2, SW - 2, H - 4, Col);
			}
		}
		float Pulse(float Hz = 1.2f) const { return 0.55f + 0.45f * FMath::Sin(Time * Hz * 2.f * PI); }
	};

	FString KindShort(const FString& Kind)
	{
		return Kind == TEXT("fire") ? TEXT("FIRE") : (Kind == TEXT("hull breach") ? TEXT("BREACH") : TEXT("CONDUIT"));
	}

	FLinearColor KindColor(const FString& Kind)
	{
		return Kind == TEXT("fire") ? RED : (Kind == TEXT("hull breach") ? AMBER : YELLOW);
	}

	FString AlertText(EAstraAlert A)
	{
		return A == EAstraAlert::Red ? TEXT("RED") : (A == EAstraAlert::Yellow ? TEXT("YELLOW") : TEXT("GREEN"));
	}

	FLinearColor AlertColor(EAstraAlert A)
	{
		return A == EAstraAlert::Red ? RED : (A == EAstraAlert::Yellow ? AMBER : GREEN);
	}

	FString ShipClock(float T)
	{
		const int32 S = 3 * 3600 + 38 * 60 + int32(T);
		return FString::Printf(TEXT("2491.271  %02d:%02d:%02d SHIP"), (S / 3600) % 24, (S / 60) % 60, S % 60);
	}
}

// -------------------------------------------------------------------------------------------------------------- page
void UAstraScreenPage::Draw(UCanvas* Canvas, int32 Width, int32 Height)
{
	if (UAstraScreensSubsystem* O = Owner.Get())
	{
		O->DrawPage(Name, Canvas, Width, Height);
	}
}

// --------------------------------------------------------------------------------------------------------- subsystem
bool UAstraScreensSubsystem::ShouldCreateSubsystem(UObject* Outer) const
{
	const UWorld* World = Cast<UWorld>(Outer);
	return World && (World->WorldType == EWorldType::Game || World->WorldType == EWorldType::PIE);
}

bool UAstraScreensSubsystem::IsLive(const FString& Name)
{
	static const TSet<FString> Live = {TEXT("Master"), TEXT("Tactical"), TEXT("Helm_A"), TEXT("Helm_B"), TEXT("Ops_A"), TEXT("Ops_B"),
	                                   TEXT("Ops_C"), TEXT("Sensors_A"), TEXT("Sensors_B"), TEXT("Eng_A"), TEXT("Eng_B")};
	return Live.Contains(Name);
}

UAstraScreenPage* UAstraScreensSubsystem::PageFor(const FString& Name)
{
	for (UAstraScreenPage* P : Pages)
	{
		if (P->Name == Name)
		{
			return P;
		}
	}
	const FIntPoint Size = Name == TEXT("Master") ? FIntPoint(2048, 864) : (Name == TEXT("Tactical") ? FIntPoint(2048, 256) : FIntPoint(1024, 640));
	UAstraScreenPage* P = NewObject<UAstraScreenPage>(this);
	P->Name = Name;
	P->Owner = this;
	P->Target = UCanvasRenderTarget2D::CreateCanvasRenderTarget2D(this, UCanvasRenderTarget2D::StaticClass(), Size.X, Size.Y);
	P->Target->ClearColor = BG;
	P->Target->OnCanvasRenderTargetUpdate.AddDynamic(P, &UAstraScreenPage::Draw);
	P->Wait = FMath::FRand() * P->Interval;   // spread the redraws over frames
	Pages.Add(P);
	return P;
}

void UAstraScreensSubsystem::OnWorldBeginPlay(UWorld& InWorld)
{
	Super::OnWorldBeginPlay(InWorld);
	TitleFont = LoadObject<UFont>(nullptr, TEXT("/Game/ASTRA/UI/Fonts/F_ASTRA_Title.F_ASTRA_Title"));
	MonoFont = LoadObject<UFont>(nullptr, TEXT("/Game/ASTRA/UI/Fonts/F_ASTRA_Mono.F_ASTRA_Mono"));
	if (!TitleFont || !MonoFont)
	{
		UE_LOG(LogASTRA, Warning, TEXT("[Screens] UI fonts missing (tools/ue_scripts/make_fonts.py): live screens off"));
		return;
	}
	int32 Bound = 0;
	for (TActorIterator<AActor> It(&InWorld); It; ++It)
	{
		TArray<UStaticMeshComponent*> Comps;
		It->GetComponents<UStaticMeshComponent>(Comps);
		for (UStaticMeshComponent* SMC : Comps)
		{
			for (int32 i = 0; i < SMC->GetNumMaterials(); ++i)
			{
				UMaterialInterface* M = SMC->GetMaterial(i);
				if (!M)
				{
					continue;
				}
				FString N = M->GetName();
				FString Page;
				if (N == TEXT("MI_ASTRA_ScreenMaster")) { Page = TEXT("Master"); }
				else if (N == TEXT("MI_ASTRA_ScreenTactical")) { Page = TEXT("Tactical"); }
				else if (N.RemoveFromStart(TEXT("MI_UI_"))) { Page = N; }
				if (Page.IsEmpty() || !IsLive(Page))
				{
					continue;
				}
				UAstraScreenPage* P = PageFor(Page);
				if (UMaterialInstanceDynamic* MID = SMC->CreateDynamicMaterialInstance(i, M))
				{
					MID->SetTextureParameterValue(TEXT("ScreenTexture"), P->Target);
					++Bound;
				}
			}
		}
	}
	UE_LOG(LogASTRA, Log, TEXT("[Screens] %d live pages on %d screen surfaces"), Pages.Num(), Bound);
}

void UAstraScreensSubsystem::Tick(float DeltaTime)
{
	Time += DeltaTime;
	// one screen redrawn per frame at most (the most overdue one): drawing them all in the same frame was a
	// 12 ms hitch four times a second
	UAstraScreenPage* Due = nullptr;
	for (UAstraScreenPage* P : Pages)
	{
		P->Wait -= DeltaTime;
		if (P->Wait <= 0.f && (!Due || P->Wait < Due->Wait))
		{
			Due = P;
		}
	}
	if (Due)
	{
		Due->Wait = FMath::Max(Due->Wait + Due->Interval, Due->Interval * 0.5f);
		const bool bProfile = CVarScreensProfile.GetValueOnGameThread() != 0;
		TSharedPtr<double> RT0 = MakeShared<double>(0.0);
		if (bProfile)
		{
			ENQUEUE_RENDER_COMMAND(AstraScreenT0)([RT0](FRHICommandListImmediate&) { *RT0 = FPlatformTime::Seconds(); });
		}
		const double T0 = FPlatformTime::Seconds();
		Due->Target->FastUpdateResource();   // repaint only (UpdateResource re-creates the texture every time)
		if (bProfile)
		{
			const double GameMs = (FPlatformTime::Seconds() - T0) * 1000.0;
			ENQUEUE_RENDER_COMMAND(AstraScreenT1)([RT0, GameMs, Name = Due->Name](FRHICommandListImmediate&)
			{
				UE_LOG(LogASTRA, Log, TEXT("[Screens] %s: game %.2f ms, render %.2f ms"), *Name, GameMs, (FPlatformTime::Seconds() - *RT0) * 1000.0);
			});
		}
	}
}

void UAstraScreensSubsystem::DrawPage(const FString& Name, UCanvas* Canvas, int32 Width, int32 Height)
{
	FString Station, Slot;
	if (Name == TEXT("Master")) { DrawMaster(Canvas, Width, Height); }
	else if (Name == TEXT("Tactical")) { DrawTactical(Canvas, Width, Height); }
	else if (Name.Split(TEXT("_"), &Station, &Slot))
	{
		if (Station == TEXT("Helm")) { DrawHelm(Canvas, Width, Height, Slot); }
		else if (Station == TEXT("Ops")) { DrawOps(Canvas, Width, Height, Slot); }
		else if (Station == TEXT("Sensors")) { DrawSensors(Canvas, Width, Height, Slot); }
		else if (Station == TEXT("Eng")) { DrawEngineering(Canvas, Width, Height, Slot); }
	}
}

// ------------------------------------------------------------------------------------------------------------ pages
void UAstraScreensSubsystem::DrawMaster(UCanvas* C, int32 W, int32 H)
{
	const UAstraShipSubsystem* Ship = GetWorld()->GetSubsystem<UAstraShipSubsystem>();
	const UAstraBattleSubsystem* Battle = GetWorld()->GetSubsystem<UAstraBattleSubsystem>();
	if (!Ship)
	{
		return;
	}
	FPaint P{C, TitleFont, MonoFont, Time};
	P.Rect(0, 0, W, H, BG);
	P.Header(W, TEXT("ASN Aquila · Master Systems Display"), TEXT("CVC-01 · AQUILA CLASS · 780 M"), COMMAND);

	// damage control board: decks 1-12 x sections A-H
	P.Text(40, 58, TEXT("DAMAGE CONTROL"), false, 22, CYAN);
	P.Text(1134, 64, TEXT("DECKS 1-12 · SECTIONS A-H"), true, 14, DIM, 2);
	const float GX = 120.f, GY = 120.f, CW = 120.f, CH = 50.f, Gap = 8.f;
	for (int32 c = 0; c < 8; ++c)
	{
		P.Text(GX + c * (CW + Gap) + CW * 0.5f, GY - 26, FString::Chr(TEXT('A') + c), false, 18, DIM, 1);
	}
	for (int32 r = 0; r < 12; ++r)
	{
		const float Y = GY + r * (CH + Gap);
		P.Text(40, Y + 14, FString::Printf(TEXT("DECK %d"), r + 1), true, 15, DIM);
		for (int32 c = 0; c < 8; ++c)
		{
			const float X = GX + c * (CW + Gap);
			P.Rect(X, Y, CW, CH, PANEL);
			P.Frame(X, Y, CW, CH, RGB(20, 40, 64));
		}
	}
	for (const FAstraDamage& D : Ship->GetDamage())
	{
		const int32 r = FMath::Clamp(D.Deck - 1, 0, 11), c = FMath::Clamp(int32(D.Section - TEXT('A')), 0, 7);
		const float X = GX + c * (CW + Gap), Y = GY + r * (CH + Gap);
		FLinearColor K = KindColor(D.Kind);
		const float A = D.Team < 0 ? P.Pulse(D.Kind == TEXT("fire") ? 1.6f : 0.8f) : 0.55f;
		P.Rect(X, Y, CW, CH, FLinearColor(K.R, K.G, K.B, 0.35f * A + 0.1f));
		P.Frame(X, Y, CW, CH, K, 2.f);
		P.Text(X + 8, Y + 4, KindShort(D.Kind), true, 15, TEXTC, 0, true);
		if (D.Team >= 0)
		{
			P.Text(X + CW - 8, Y + 4, FString::Printf(TEXT("T%d"), D.Team + 1), true, 15, CYAN, 2, true);
			if (D.Travel > 0.f)
			{
				P.Text(X + 8, Y + 26, TEXT("EN ROUTE"), true, 13, CYAN);
			}
			else
			{
				P.Rect(X + 6, Y + CH - 12, (CW - 12) * FMath::Clamp(D.Progress, 0.f, 1.f), 6, CYAN);
			}
		}
		else
		{
			P.Text(X + 8, Y + 26, TEXT("NO TEAM"), true, 13, K);
		}
	}

	// status column
	const float RX = 1220.f, RW = 790.f;
	const EAstraAlert Alert = Ship->GetAlert();
	P.Text(RX, 62, TEXT("CONDITION"), false, 28, CYAN);
	FLinearColor AC = AlertColor(Alert);
	if (Alert == EAstraAlert::Red)
	{
		AC.A = P.Pulse(0.8f) * 0.6f + 0.4f;
	}
	P.Text(RX + RW, 50, AlertText(Alert), false, 64, AC, 2);
	P.Line(RX, 128, RX + RW, 128, DIM);
	const float Sh = Battle ? Battle->PlayerShieldFraction() : 1.f;
	const float Hu = Battle ? Battle->PlayerHullFraction() : 1.f;
	P.Bar(RX, 142, RW, 22, Sh, TEXT("Shields"), FString::Printf(TEXT("%.0f %%  %s"), 100.f * Sh, *Ship->GetShieldMode().ToUpper()), Ship->AreShieldsUp() ? Level(Sh) : DIM);
	P.Bar(RX, 204, RW, 22, Hu, TEXT("Hull integrity"), FString::Printf(TEXT("%.0f %%"), 100.f * Hu), Level(Hu));
	P.Bar(RX, 266, RW, 22, Ship->GetReactorPct() / 100.f, TEXT("Reactor output"), FString::Printf(TEXT("%.0f %%"), Ship->GetReactorPct()),
	      Ship->GetReactorPct() > 90.f ? AMBER : CYAN);
	P.Text(RX, 330, TEXT("POWER ALLOCATION"), false, 20, CYAN);
	float Sum = 0.f;
	int32 i = 0;
	static const TCHAR* Order[] = {TEXT("shields"), TEXT("weapons"), TEXT("engines"), TEXT("sensors"), TEXT("life_support"), TEXT("flight_deck")};
	for (const TCHAR* Sys : Order)
	{
		const float* V = Ship->GetPowerPct().Find(Sys);
		const float Val = V ? *V : 100.f;
		Sum += Val;
		const float X = RX + (i % 2) * (RW * 0.5f + 10.f), Y = 362.f + (i / 2) * 56.f;
		const float Eff = Ship->PowerFactor(Sys) * 100.f;
		const FString Name = FString(Sys).Replace(TEXT("_"), TEXT(" "));
		P.Bar(X, Y, RW * 0.5f - 10.f, 12, Val / 150.f, Name, Eff + 0.5f < Val ? FString::Printf(TEXT("%.0f %% (%.0f)"), Val, Eff) : FString::Printf(TEXT("%.0f %%"), Val),
		      Eff + 0.5f < Val ? AMBER : (Val > 100.f ? GREEN : CYAN));
		++i;
	}
	P.Text(RX + RW, 330, FString::Printf(TEXT("ALLOCATED %.0f / %.0f %%"), Sum, Ship->GetPowerBudget()), true, 15, Sum > 660.f ? AMBER : DIM, 2);
	P.Line(RX, 540, RX + RW, 540, DIM);
	P.Text(RX, 552, TEXT("NAVIGATION"), false, 20, CYAN);
	P.Text(RX, 584, FString::Printf(TEXT("HDG %03.0f  MK %+.0f  ·  %.0f M/S  ·  THROTTLE %.0f %%"), Ship->GetHeadingDeg(), Ship->GetMarkDeg(),
	                                Ship->GetSpeedMps(), Ship->GetThrottlePct()), true, 22, TEXTC);
	FString Helm = TEXT("STEADY ON COURSE");
	if (!Ship->GetInterceptId().IsEmpty())
	{
		Helm = FString::Printf(TEXT("INTERCEPT %s  ·  %.1f KM  ·  %s"), *Ship->GetInterceptId(), Ship->GetInterceptRangeKm(),
		                       Ship->IsBroadside() ? TEXT("BROADSIDE") : TEXT("CLOSING"));
	}
	else if (Ship->IsTurning())
	{
		Helm = FString::Printf(TEXT("TURNING TO %03.0f MK %+.0f"), Ship->GetTargetHeadingDeg(), Ship->GetTargetMarkDeg());
	}
	P.Text(RX, 620, Helm, true, 20, Ship->GetInterceptId().IsEmpty() ? CYAN : AMBER);
	P.Line(RX, 664, RX + RW, 664, DIM);
	int32 Busy = 0;
	for (const FAstraDamage& D : Ship->GetDamage())
	{
		Busy += D.Team >= 0 ? 1 : 0;
	}
	const int32 Teams = Ship->GetNumDamageTeams();
	P.Text(RX, 676, TEXT("DAMAGE CONTROL TEAMS"), false, 20, CYAN);
	P.Text(RX + RW, 680, FString::Printf(TEXT("%d / %d FREE"), Teams - Busy, Teams), true, 18, Busy >= Teams ? RED : TEXTC, 2);
	for (int32 t = 0; t < Teams; ++t)
	{
		const bool bBusy = Ship->GetDamage().ContainsByPredicate([t](const FAstraDamage& D) { return D.Team == t; });
		const float X = RX + t * (RW / Teams);
		P.Rect(X, 714, RW / Teams - 12, 34, bBusy ? RGB(20, 60, 100) : PANEL);
		P.Frame(X, 714, RW / Teams - 12, 34, bBusy ? CYAN : DIM);
		P.Text(X + 12, 719, FString::Printf(TEXT("TEAM %d  %s"), t + 1, bBusy ? TEXT("DEPLOYED") : TEXT("READY")), true, 16, bBusy ? CYAN : DIM);
	}
	int32 Hostiles = 0, Friends = 0;
	if (Battle)
	{
		TArray<FAstraHoloBlip> Blips;
		Battle->GetHoloBlips(Blips);
		for (const FAstraHoloBlip& B : Blips)
		{
			Hostiles += (B.Kind == 0 && B.bHostile && !B.bRetreating) ? 1 : 0;
			Friends += (B.Kind == 0 && !B.bPlayer && !B.bCraft && B.Side == EAstraSide::Astra) ? 1 : 0;
		}
	}
	P.Text(RX, 766, FString::Printf(TEXT("CONTACTS  %d HOSTILE  ·  %d FRIENDLY"), Hostiles, Friends), true, 18, Hostiles ? RED : TEXTC);
	const TArray<FString>& Ev = Ship->GetRecentEvents();
	P.Footer(W, H, Ev.Num() ? Ev.Last().ToUpper() : FString(TEXT("ALL DECKS PRESSURIZED · ALL STATIONS MANNED")), Ship->GetDamage().Num() ? AMBER : GREEN);
	P.Text(W - 16, H - 25, ShipClock(Time), true, 14, DIM, 2);
}

void UAstraScreensSubsystem::DrawTactical(UCanvas* C, int32 W, int32 H)
{
	const UAstraShipSubsystem* Ship = GetWorld()->GetSubsystem<UAstraShipSubsystem>();
	const UAstraBattleSubsystem* Battle = GetWorld()->GetSubsystem<UAstraBattleSubsystem>();
	if (!Ship || !Battle)
	{
		return;
	}
	FPaint P{C, TitleFont, MonoFont, Time};
	P.Rect(0, 0, W, H, BG);
	const UAstraBattleSubsystem::FFireControl F = Battle->GetFireControl();
	const float Sh = Battle->PlayerShieldFraction();
	int32 Hostiles = 0;
	TArray<FAstraHoloBlip> Blips;
	Battle->GetHoloBlips(Blips);
	for (const FAstraHoloBlip& B : Blips)
	{
		Hostiles += (B.Kind == 0 && B.bHostile && !B.bRetreating) ? 1 : 0;
	}
	struct FCell { FString K, V, S; FLinearColor Col; };
	TArray<FCell> Cells;
	if (F.RailVolleys > 0 && !F.Target.IsEmpty())
	{
		const bool bIn = F.TargetRangeKm <= 10.f;
		Cells.Add({TEXT("RAILGUNS"), bIn ? TEXT("ENGAGING") : TEXT("ASSIGNED"),
		           bIn ? FString::Printf(TEXT("%s · %d VOLLEYS · NEXT %.0f S"), *F.Target, F.RailVolleys, F.RailNext)
		               : FString::Printf(TEXT("%s AT %.0f KM · OPEN AT 10"), *F.Target, F.TargetRangeKm), bIn ? RED : AMBER});
	}
	else
	{
		Cells.Add({TEXT("RAILGUNS"), TEXT("READY"), TEXT("4 TWIN TURRETS · 10 KM"), GREEN});
	}
	Cells.Add({TEXT("LASERS"), F.LaserShots > 0 ? TEXT("FIRING") : TEXT("ONLINE"), TEXT("12 BATTERIES · 4 KM"), F.LaserShots > 0 ? RED : GREEN});
	Cells.Add({TEXT("VLS"), FString::FromInt(F.Missiles), F.MissileCycle > 0.f ? FString::Printf(TEXT("CYCLING · %.0f S"), F.MissileCycle) : TEXT("READY · 8 PER SALVO"),
	           F.MissileCycle > 0.f ? AMBER : CYAN});
	Cells.Add({TEXT("IN FLIGHT"), FString::FromInt(F.OursInFlight), TEXT("OUR MISSILES"), F.OursInFlight ? CYAN : DIM});
	Cells.Add({TEXT("POINT DEFENSE"), Ship->GetPointDefense().ToUpper(), F.Inbound ? FString::Printf(TEXT("%d INBOUND"), F.Inbound) : TEXT("NO INBOUND"),
	           F.Inbound ? RED : GREEN});
	Cells.Add({TEXT("SHIELDS"), FString::Printf(TEXT("%.0f %%"), 100.f * Sh), Ship->GetShieldMode().ToUpper(), Ship->AreShieldsUp() ? Level(Sh) : DIM});
	Cells.Add({TEXT("TARGET"), F.Target.IsEmpty() ? TEXT("NONE") : F.Target, F.Target.IsEmpty() ? TEXT("NO FIRE SOLUTION") : FString::Printf(TEXT("%.1f KM"), F.TargetRangeKm),
	           F.Target.IsEmpty() ? DIM : RED});
	Cells.Add({TEXT("HOSTILES"), FString::FromInt(Hostiles), Ship->GetAlert() == EAstraAlert::Red ? TEXT("CONDITION RED") : TEXT("TRACKING"), Hostiles ? RED : GREEN});
	const float CW = (W - 24.f) / Cells.Num();
	for (int32 i = 0; i < Cells.Num(); ++i)
	{
		const FCell& K = Cells[i];
		const float X = 12.f + i * CW;
		P.Rect(X, 14, CW - 12, H - 28, PANEL);
		P.Frame(X, 14, CW - 12, H - 28, DIM);
		P.Text(X + 12, 26, K.K, false, 26, TEXTC);
		P.Text(X + 12, 70, K.V, true, 44, K.Col, 0, true);
		P.Text(X + 12, 140, K.S, true, 16, CYAN);
		P.Rect(X + 12, H - 50, CW - 36, 14, K.Col);
	}
}

void UAstraScreensSubsystem::DrawHelm(UCanvas* C, int32 W, int32 H, const FString& Slot)
{
	const UAstraShipSubsystem* Ship = GetWorld()->GetSubsystem<UAstraShipSubsystem>();
	if (!Ship)
	{
		return;
	}
	FPaint P{C, TitleFont, MonoFont, Time};
	P.Rect(0, 0, W, H, BG);
	if (Slot == TEXT("B"))
	{
		DrawSensors(C, W, H, TEXT("B"));
		return;
	}
	P.Header(W, TEXT("Helm · Navigation"), TEXT("HELM · DECK 1"), COMMAND);
	// heading tape
	const float Hd = Ship->GetHeadingDeg();
	P.Rect(20, 60, W - 40, 80, RGB(6, 12, 24));
	P.Frame(20, 60, W - 40, 80, DIM);
	for (int32 d = FMath::FloorToInt(Hd / 5.f) * 5 - 70; d <= Hd + 70; d += 5)
	{
		const float X = W * 0.5f + (d - Hd) * 6.6f;
		if (X < 26 || X > W - 26)
		{
			continue;
		}
		const int32 Dn = ((d % 360) + 360) % 360;
		P.Line(X, 140, X, Dn % 30 == 0 ? 112 : 126, Dn % 30 == 0 ? LINE : DIM, Dn % 30 == 0 ? 2.f : 1.f);
		if (Dn % 30 == 0)
		{
			P.Text(X, 72, FString::Printf(TEXT("%03d"), Dn), true, 18, TEXTC, 1);
		}
	}
	if (Ship->IsTurning())
	{
		const float X = W * 0.5f + FMath::FindDeltaAngleDegrees(Hd, Ship->GetTargetHeadingDeg()) * 6.6f;
		P.Rect(FMath::Clamp(X, 26.f, W - 30.f) - 3, 62, 6, 76, AMBER);
	}
	P.Line(W * 0.5f, 58, W * 0.5f, 144, CYAN, 3.f);
	P.Text(W * 0.5f, 160, FString::Printf(TEXT("%03.0f"), Hd), true, 110, TEXTC, 1, true);
	P.Text(W * 0.5f, 300, FString::Printf(TEXT("MARK %+.0f"), Ship->GetMarkDeg()), true, 26, CYAN, 1);
	P.Panel(20, 350, W * 0.5f - 10, H - 20, TEXT("Drive"));
	const float Spd = Ship->GetSpeedMps();
	P.Bar(36, 396, W * 0.5f - 62, 16, Spd / 576.f, TEXT("Speed"), FString::Printf(TEXT("%.0f M/S"), Spd), CYAN);
	P.Bar(36, 460, W * 0.5f - 62, 16, Ship->GetThrottlePct() / 100.f, TEXT("Throttle"), FString::Printf(TEXT("%.0f %%"), Ship->GetThrottlePct()), CYAN);
	P.Bar(36, 524, W * 0.5f - 62, 16, Ship->PowerFactor(TEXT("engines")) / 1.5f, TEXT("Engine power"), FString::Printf(TEXT("%.0f %%"), 100.f * Ship->PowerFactor(TEXT("engines"))), CYAN);
	P.Panel(W * 0.5f + 10, 350, W - 20, H - 20, TEXT("Manoeuvre"));
	const float MX = W * 0.5f + 28;
	if (!Ship->GetInterceptId().IsEmpty())
	{
		P.Text(MX, 392, TEXT("INTERCEPT"), false, 30, AMBER);
		P.Text(MX, 434, Ship->GetInterceptId(), true, 40, TEXTC, 0, true);
		P.Text(MX, 494, FString::Printf(TEXT("RANGE %.1f KM"), Ship->GetInterceptRangeKm()), true, 22, CYAN);
		P.Text(MX, 526, Ship->IsBroadside() ? TEXT("BROADSIDE · HOLDING RANGE") : TEXT("CLOSING ON LEAD POINT"), true, 18, CYAN);
	}
	else if (Ship->IsTurning())
	{
		P.Text(MX, 392, TEXT("TURNING"), false, 30, AMBER);
		P.Text(MX, 434, FString::Printf(TEXT("%03.0f MK %+.0f"), Ship->GetTargetHeadingDeg(), Ship->GetTargetMarkDeg()), true, 40, TEXTC, 0, true);
		P.Text(MX, 494, TEXT("RATE 1.5 DEG/S"), true, 22, CYAN);
	}
	else
	{
		P.Text(MX, 392, TEXT("STEADY"), false, 30, GREEN);
		P.Text(MX, 434, FString::Printf(TEXT("%03.0f MK %+.0f"), Hd, Ship->GetMarkDeg()), true, 40, TEXTC, 0, true);
	}
}

void UAstraScreensSubsystem::DrawOps(UCanvas* C, int32 W, int32 H, const FString& Slot)
{
	const UAstraShipSubsystem* Ship = GetWorld()->GetSubsystem<UAstraShipSubsystem>();
	if (!Ship)
	{
		return;
	}
	FPaint P{C, TitleFont, MonoFont, Time};
	P.Rect(0, 0, W, H, BG);
	if (Slot == TEXT("A"))
	{
		P.Header(W, TEXT("Operations · Power"), FString::Printf(TEXT("REACTOR %.0f %%"), Ship->GetReactorPct()), COMMAND);
		float Sum = 0.f;
		int32 i = 0;
		static const TCHAR* Order[] = {TEXT("shields"), TEXT("weapons"), TEXT("engines"), TEXT("sensors"), TEXT("life_support"), TEXT("flight_deck")};
		for (const TCHAR* Sys : Order)
		{
			const float* V = Ship->GetPowerPct().Find(Sys);
			const float Val = V ? *V : 100.f;
			const float Eff = Ship->PowerFactor(Sys) * 100.f;
			Sum += Val;
			P.Bar(30, 70 + i * 78, W - 60, 22, Val / 150.f, FString(Sys).Replace(TEXT("_"), TEXT(" ")),
			      Eff + 0.5f < Val ? FString::Printf(TEXT("%.0f %% · EFFECTIVE %.0f"), Val, Eff) : FString::Printf(TEXT("%.0f %%"), Val),
			      Eff + 0.5f < Val ? AMBER : (Val > 100.f ? GREEN : CYAN));
			++i;
		}
		P.Footer(W, H, FString::Printf(TEXT("ALLOCATED %.0f OF %.0f %% · REACTOR %.0f %%"), Sum, Ship->GetPowerBudget(), Ship->GetReactorPct()),
		         Sum > 660.f ? AMBER : GREEN);
		return;
	}
	const TArray<FAstraDamage>& Dmg = Ship->GetDamage();
	if (Slot == TEXT("B"))
	{
		P.Header(W, TEXT("Operations · Damage Control"), TEXT("4 TEAMS"), COMMAND);
		for (int32 t = 0; t < Ship->GetNumDamageTeams(); ++t)
		{
			const FAstraDamage* D = Dmg.FindByPredicate([t](const FAstraDamage& X) { return X.Team == t; });
			const float Y = 64.f + t * 136.f;
			P.Panel(20, Y, W - 20, Y + 124, FString::Printf(TEXT("Team %d"), t + 1));
			if (!D)
			{
				P.Text(40, Y + 50, TEXT("READY · DAMAGE CONTROL LOCKER DECK 6"), true, 22, GREEN);
				continue;
			}
			P.Text(40, Y + 42, FString::Printf(TEXT("%s · %s"), *D->Where().ToUpper(), *KindShort(D->Kind)), true, 24, KindColor(D->Kind), 0, true);
			if (D->Travel > 0.f)
			{
				P.Text(40, Y + 82, FString::Printf(TEXT("EN ROUTE · ON SCENE IN %.0f S"), D->Travel), true, 20, CYAN);
			}
			else
			{
				P.Bar(40, Y + 72, W - 80, 14, D->Progress, TEXT("On scene"), FString::Printf(TEXT("%.0f %%"), 100.f * D->Progress), CYAN);
			}
		}
		return;
	}
	P.Header(W, TEXT("Operations · Incidents"), FString::Printf(TEXT("%d OPEN"), Dmg.Num()), COMMAND);
	if (Dmg.Num() == 0)
	{
		P.Text(W * 0.5f, H * 0.5f - 20, TEXT("NO OPEN INCIDENTS"), false, 36, GREEN, 1);
		return;
	}
	for (int32 i = 0; i < FMath::Min(Dmg.Num(), 10); ++i)
	{
		const FAstraDamage& D = Dmg[Dmg.Num() - 1 - i];
		const float Y = 60.f + i * 56.f;
		P.Rect(20, Y, W - 40, 48, PANEL);
		P.Rect(20, Y, 8, 48, KindColor(D.Kind));
		P.Text(40, Y + 10, FString::Printf(TEXT("%s  %s"), *D.Where().ToUpper(), *KindShort(D.Kind)), true, 20, TEXTC, 0, true);
		FString St = D.Team < 0 ? FString(TEXT("UNATTENDED")) : (D.Travel > 0.f ? FString::Printf(TEXT("TEAM %d EN ROUTE"), D.Team + 1)
		                                                                        : FString::Printf(TEXT("TEAM %d · %.0f %%"), D.Team + 1, 100.f * D.Progress));
		if (!D.System.IsEmpty())
		{
			St = FString::Printf(TEXT("%s -20 %% · %s"), *D.System.ToUpper(), *St);
		}
		P.Text(W - 36, Y + 12, St, true, 18, D.Team < 0 ? KindColor(D.Kind) : CYAN, 2);
	}
}

void UAstraScreensSubsystem::DrawSensors(UCanvas* C, int32 W, int32 H, const FString& Slot)
{
	const UAstraBattleSubsystem* Battle = GetWorld()->GetSubsystem<UAstraBattleSubsystem>();
	const UAstraShipSubsystem* Ship = GetWorld()->GetSubsystem<UAstraShipSubsystem>();
	if (!Battle || !Ship)
	{
		return;
	}
	FPaint P{C, TitleFont, MonoFont, Time};
	P.Rect(0, 0, W, H, BG);
	TArray<FAstraHoloBlip> Blips;
	Battle->GetHoloBlips(Blips);
	if (Slot == TEXT("B"))
	{
		// relative plot (bow up), logarithmic range like the holo table
		P.Header(W, TEXT("Sensors · Relative Plot"), FString::Printf(TEXT("EMCON %s"), *Ship->GetEmcon().ToUpper()), SCIENCE);
		const float CX = W * 0.5f, CY = 60.f + (H - 60.f) * 0.5f, R = (H - 90.f) * 0.5f;
		const float RangeKm = 60.f, D0 = RangeKm / 12.f;
		auto Rad = [&](float Km) { return R * FMath::Loge(1.f + Km / D0) / FMath::Loge(1.f + RangeKm / D0); };
		for (float Km : {2.f, 5.f, 15.f, 60.f})
		{
			const float RR = Rad(Km);
			for (int32 k = 0; k < 96; ++k)
			{
				const float A0 = 2.f * PI * k / 96.f, A1 = 2.f * PI * (k + 1) / 96.f;
				P.Line(CX + RR * FMath::Sin(A0), CY - RR * FMath::Cos(A0), CX + RR * FMath::Sin(A1), CY - RR * FMath::Cos(A1), Km == 60.f ? LINE : DIM);
			}
			P.Text(CX + RR * 0.72f, CY + RR * 0.72f, FString::Printf(TEXT("%.0f KM"), Km), true, 13, DIM);
		}
		const float Sweep = FMath::Fmod(Time * 60.f, 360.f);
		P.Line(CX, CY, CX + R * FMath::Sin(FMath::DegreesToRadians(Sweep)), CY - R * FMath::Cos(FMath::DegreesToRadians(Sweep)), RGB(40, 120, 90), 2.f);
		for (const FAstraHoloBlip& B : Blips)
		{
			if (B.Kind == 2 || B.bPlayer)
			{
				continue;
			}
			const float Km = B.Rel.Size() / 100000.f;
			const FVector2D Dir(B.Rel.Y, -B.Rel.X);
			const FVector2D Q = FVector2D(CX, CY) + Dir.GetSafeNormal() * FMath::Min(Rad(Km), R);
			const FLinearColor Col = B.Kind == 1 ? (B.Side == EAstraSide::Astra ? CYAN : RED)
			                       : (B.bUnknown ? DIM : (B.Side == EAstraSide::Astra ? CYAN : (B.bHostile ? (B.bHoldFire ? AMBER : RED) : YELLOW)));
			if (B.Kind == 1 || B.bCraft)
			{
				P.Rect(Q.X - 2, Q.Y - 2, 4, 4, B.bCraft ? CYAN : Col);
				continue;
			}
			P.Frame(Q.X - 7, Q.Y - 7, 14, 14, Col, 2.f);
			P.Text(Q.X + 12, Q.Y - 10, B.Contact, true, 14, Col);
		}
		P.Rect(CX - 4, CY - 10, 8, 20, CYAN);
		return;
	}
	P.Header(W, TEXT("Sensors · Contacts"), TEXT("PASSIVE + ACTIVE"), SCIENCE);
	P.Text(24, 56, TEXT("ID"), true, 15, DIM);
	P.Text(110, 56, TEXT("NAME / CLASS"), true, 15, DIM);
	P.Text(700, 56, TEXT("RANGE"), true, 15, DIM, 2);
	P.Text(790, 56, TEXT("BRG"), true, 15, DIM, 2);
	P.Text(W - 24, 56, TEXT("STATUS"), true, 15, DIM, 2);
	int32 Row = 0;
	Blips.Sort([](const FAstraHoloBlip& A, const FAstraHoloBlip& B) { return A.RangeKm < B.RangeKm; });
	for (const FAstraHoloBlip& B : Blips)
	{
		if (B.Kind != 0 || B.bPlayer || B.bCraft || Row >= 11)
		{
			continue;
		}
		const float Y = 84.f + Row * 48.f;
		const FLinearColor Col = B.bUnknown ? DIM : (B.Side == EAstraSide::Astra ? CYAN : (B.bHostile ? (B.bHoldFire ? AMBER : RED) : YELLOW));
		P.Rect(16, Y, W - 32, 42, PANEL);
		P.Rect(16, Y, 6, 42, Col);
		P.Text(30, Y + 9, B.Contact, true, 20, Col, 0, true);
		P.Text(110, Y + 9, B.Name.IsEmpty() ? TEXT("UNIDENTIFIED") : B.Name.ToUpper(), false, 22, TEXTC);
		P.Text(700, Y + 9, FString::Printf(TEXT("%.1f KM"), B.RangeKm), true, 18, TEXTC, 2);
		const float Brg = FMath::Fmod(FMath::RadiansToDegrees(FMath::Atan2(B.Rel.Y, B.Rel.X)) + Ship->GetHeadingDeg() + 720.f, 360.f);
		P.Text(790, Y + 9, FString::Printf(TEXT("%03.0f"), Brg), true, 18, TEXTC, 2);
		P.Text(W - 24, Y + 11, B.bUnknown ? TEXT("UNKNOWN") : (B.Side == EAstraSide::Astra ? TEXT("FRIENDLY")
		                     : (B.bHostile ? (B.bRetreating ? TEXT("WITHDRAWING") : (B.bHoldFire ? TEXT("HOLDING FIRE") : TEXT("HOSTILE"))) : TEXT("NEUTRAL"))),
		       true, 16, Col, 2);
		++Row;
	}
}

void UAstraScreensSubsystem::DrawEngineering(UCanvas* C, int32 W, int32 H, const FString& Slot)
{
	const UAstraShipSubsystem* Ship = GetWorld()->GetSubsystem<UAstraShipSubsystem>();
	if (!Ship)
	{
		return;
	}
	FPaint P{C, TitleFont, MonoFont, Time};
	P.Rect(0, 0, W, H, BG);
	if (Slot == TEXT("A"))
	{
		P.Header(W, TEXT("Engineering · Reactor"), TEXT("MAIN FUSION PLANT"), ENGINEERING);
		const float R = Ship->GetReactorPct();
		P.Text(W * 0.5f, 70, FString::Printf(TEXT("%.0f %%"), R), true, 120, R > 90.f ? AMBER : TEXTC, 1, true);
		P.Text(W * 0.5f, 220, TEXT("REACTOR OUTPUT"), false, 26, ENGINEERING, 1);
		P.Bar(40, 280, W - 80, 26, R / 100.f, TEXT("Output"), R > 90.f ? TEXT("HIGH · WATCH HEAT") : TEXT("NOMINAL"), R > 90.f ? AMBER : GREEN);
		float Sum = 0.f;
		for (const auto& KV : Ship->GetPowerPct())
		{
			Sum += KV.Value;
		}
		P.Bar(40, 360, W - 80, 26, Sum / Ship->GetPowerBudget(), TEXT("Allocation"), FString::Printf(TEXT("%.0f / %.0f %%"), Sum, Ship->GetPowerBudget()),
		      Sum > 660.f ? AMBER : CYAN);
		P.Footer(W, H, TEXT("CONTAINMENT STABLE · COOLANT NOMINAL"), GREEN);
		return;
	}
	P.Header(W, TEXT("Engineering · Power Conduits"), TEXT("DAMAGE TO THE GRID"), ENGINEERING);
	int32 Row = 0;
	for (const FAstraDamage& D : Ship->GetDamage())
	{
		if (D.System.IsEmpty() || Row >= 9)
		{
			continue;
		}
		const float Y = 64.f + Row++ * 60.f;
		P.Rect(20, Y, W - 40, 50, PANEL);
		P.Rect(20, Y, 8, 50, YELLOW);
		P.Text(40, Y + 12, FString::Printf(TEXT("%s · %s -20 %%"), *D.Where().ToUpper(), *D.System.ToUpper()), true, 20, TEXTC, 0, true);
		P.Text(W - 36, Y + 14, D.Team < 0 ? FString(TEXT("NO TEAM")) : FString::Printf(TEXT("TEAM %d"), D.Team + 1), true, 18, D.Team < 0 ? YELLOW : CYAN, 2);
	}
	if (Row == 0)
	{
		P.Text(W * 0.5f, H * 0.5f - 20, TEXT("GRID INTACT"), false, 40, GREEN, 1);
	}
}
