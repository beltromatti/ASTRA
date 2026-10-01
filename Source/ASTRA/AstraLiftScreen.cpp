// ASTRA — the lift car's screen (see AstraLiftSubsystem.h): drawn like the bridge's consoles (a canvas render target, the same palette and type), but
// only while the Captain is in the car.

#include "AstraLiftSubsystem.h"

#include "ASTRA.h"
#include "AstraLiftCar.h"
#include "CanvasItem.h"
#include "Engine/Canvas.h"
#include "Engine/CanvasRenderTarget2D.h"
#include "Engine/Font.h"
#include "Fonts/FontMeasure.h"
#include "Framework/Application/SlateApplication.h"

namespace
{
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
	const FLinearColor GREEN = RGB(80, 220, 150);
	const FLinearColor HEADER = RGB(6, 14, 28);
	const FLinearColor COMMAND = RGB(62, 123, 250);

	/** The canvas as the bridge's screens use it: fills, then lines, then texts, each in one batch (the canvas starts a new batch each time the kind of item
	 *  changes). */
	struct FPaint
	{
		UCanvas* C = nullptr;
		UFont* Title = nullptr;
		UFont* Mono = nullptr;
		TArray<FCanvasTileItem> Tiles;
		TArray<FCanvasLineItem> Lines;
		TArray<FCanvasTextItem> Texts;

		~FPaint()
		{
			for (FCanvasTileItem& T : Tiles) { C->DrawItem(T); }
			for (FCanvasLineItem& L : Lines) { C->DrawItem(L); }
			for (FCanvasTextItem& T : Texts) { C->DrawItem(T); }
		}
		void Rect(float X, float Y, float W, float H, const FLinearColor& Col)
		{
			FCanvasTileItem T(FVector2D(X, Y), FVector2D(W, H), Col);
			T.BlendMode = Col.A < 1.f ? SE_BLEND_Translucent : SE_BLEND_Opaque;
			Tiles.Add(T);
		}
		void Line(float X0, float Y0, float X1, float Y1, const FLinearColor& Col, float Thick = 1.f)
		{
			FCanvasLineItem L(FVector2D(X0, Y0), FVector2D(X1, Y1));
			L.SetColor(Col);
			L.LineThickness = Thick;
			Lines.Add(L);
		}
		void Frame(float X, float Y, float W, float H, const FLinearColor& Col, float Thick = 1.f)
		{
			Line(X, Y, X + W, Y, Col, Thick);
			Line(X + W, Y, X + W, Y + H, Col, Thick);
			Line(X + W, Y + H, X, Y + H, Col, Thick);
			Line(X, Y + H, X, Y, Col, Thick);
		}
		FSlateFontInfo Font(bool bMono, float Px, bool bBold = false) const
		{
			return FSlateFontInfo(bMono ? Mono : Title, FMath::RoundToInt(Px * 0.75f), bMono ? (bBold ? TEXT("Bold") : TEXT("Regular")) : TEXT("Regular"));
		}
		float Width(const FString& S, const FSlateFontInfo& F) const
		{
			return FSlateApplication::IsInitialized() ? FSlateApplication::Get().GetRenderer()->GetFontMeasureService()->Measure(S, F).X : S.Len() * F.Size * 0.8f;
		}
		/** Align: 0 left, 1 centre, 2 right. Y is the top of the text. */
		void Text(float X, float Y, const FString& S, bool bMono, float Px, const FLinearColor& Col, int32 Align = 0, bool bBold = false)
		{
			const FSlateFontInfo F = Font(bMono, Px, bBold);
			const float W = Align ? Width(S, F) : 0.f;
			FCanvasTextItem T(FVector2D(X - (Align == 1 ? W * 0.5f : (Align == 2 ? W : 0.f)), Y), FText::FromString(S), F, Col);
			T.BlendMode = SE_BLEND_Translucent;
			Texts.Add(T);
		}
	};
}

void UAstraLiftScreen::Draw(UCanvas* Canvas, int32 Width, int32 Height)
{
	if (UAstraLiftSubsystem* O = Owner.Get())
	{
		O->PaintScreen(Line, Canvas, Width, Height);
	}
}

void UAstraLiftSubsystem::EnsureScreen(int32 Line)
{
	if (!Run.IsValidIndex(Line) || Run[Line].Screen || !Run[Line].Car || !TitleFont || !MonoFont || !FApp::CanEverRender())
	{
		return;
	}
	UAstraLiftScreen* S = NewObject<UAstraLiftScreen>(this);
	S->Owner = this;
	S->Line = Line;
	S->Target = UCanvasRenderTarget2D::CreateCanvasRenderTarget2D(this, UCanvasRenderTarget2D::StaticClass(), 1024, 640);
	S->Target->ClearColor = BG;
	S->Target->OnCanvasRenderTargetUpdate.AddDynamic(S, &UAstraLiftScreen::Draw);
	Run[Line].Screen = S;
	Run[Line].Car->SetScreenTexture(S->Target);
}

void UAstraLiftSubsystem::RepaintScreen(int32 Line, bool bNow)
{
	if (!Run.IsValidIndex(Line) || !FApp::CanEverRender())
	{
		return;
	}
	EnsureScreen(Line);
	UAstraLiftScreen* S = Run[Line].Screen;
	if (!S || !S->Target || !GetWorld())
	{
		return;
	}
	const double Now = GetWorld()->GetTimeSeconds();
	const bool bMoving = Run[Line].Car && Run[Line].Car->Brain.State() == FAstraLiftBrain::EState::Moving;
	if (bNow || Now - S->LastPaint >= (bMoving ? 0.1 : 0.5))
	{
		S->LastPaint = Now;
		S->Target->FastUpdateResource();
	}
}

// ================================================================================================================================ what it says

void UAstraLiftSubsystem::MenuRows(int32 Line, TArray<FRow>& Out) const
{
	Out.Reset();
	if (!Net.Lines.IsValidIndex(Line))
	{
		return;
	}
	const FAstraLiftLine& L = Net.Lines[Line];
	const int32 Here = Run.IsValidIndex(Line) && Run[Line].Car ? Run[Line].Car->Brain.AtLanding() : INDEX_NONE;
	for (int32 Row = 0; Row < L.Stops.Num(); ++Row)
	{
		const int32 Stop = DisplayToStop(Line, Row);
		const FAstraLiftStop& S = L.Stops[Stop];
		FRow R;
		R.Stop = Stop;
		R.Label = L.bShuttle ? S.Section.ToUpper() : FString::FromInt(S.Deck);
		R.Name = L.bShuttle ? FString::Printf(TEXT("SECTION %s"), *S.Section.ToUpper()) : S.DeckName.ToUpper();
		R.Places = FString::Join(S.Places, TEXT("  ·  "));
		R.bHere = Stop == Here;
		Out.Add(R);
	}
}

int32 UAstraLiftSubsystem::ShownStop(int32 Line) const
{
	if (!Run.IsValidIndex(Line) || !Run[Line].Car || !Net.Lines.IsValidIndex(Line))
	{
		return INDEX_NONE;
	}
	const FAstraLiftBrain& B = Run[Line].Car->Brain;
	if (B.AtLanding() != INDEX_NONE)
	{
		return B.AtLanding();
	}
	// between two stops: the nearer one, so the figure changes as a deck goes by
	const FAstraLiftLine& L = Net.Lines[Line];
	int32 Best = 0;
	for (int32 I = 1; I < L.Stops.Num(); ++I)
	{
		if (FMath::Abs(L.Stops[I].S - B.S()) < FMath::Abs(L.Stops[Best].S - B.S()))
		{
			Best = I;
		}
	}
	return Best;
}

FString UAstraLiftSubsystem::StatusLine(int32 Line, FLinearColor& OutColor) const
{
	OutColor = CYAN;
	if (!Run.IsValidIndex(Line) || !Run[Line].Car || !Net.Lines.IsValidIndex(Line))
	{
		return FString();
	}
	const FAstraLiftLine& L = Net.Lines[Line];
	const FAstraLiftBrain& B = Run[Line].Car->Brain;
	auto Name = [&L](int32 S) { return L.Stops.IsValidIndex(S) ? L.Stops[S].Label : FString(); };
	using EState = FAstraLiftBrain::EState;
	switch (B.State())
	{
	case EState::Moving:
	{
		OutColor = AMBER;
		const int32 Dir = B.LegTarget() != INDEX_NONE && L.Stops[B.LegTarget()].S > B.S() ? 1 : -1;
		return FString::Printf(TEXT("%s  ·  %s"), L.bShuttle ? (Dir > 0 ? TEXT("AFT") : TEXT("FORWARD")) : (Dir > 0 ? TEXT("UP") : TEXT("DOWN")), *Name(B.LegTarget()));
	}
	case EState::Hold:
		OutColor = AMBER;
		return FString::Printf(TEXT("%s  ·  ARRIVING"), *Name(B.AtLanding()));
	case EState::Opening:
	case EState::Open:
		OutColor = GREEN;
		return FString::Printf(TEXT("%s  ·  DOORS OPEN"), *Name(B.AtLanding()));
	case EState::Closing:
		return FString::Printf(TEXT("%s  ·  DOORS CLOSING"), *Name(B.AtLanding()));
	default:
		return Name(B.AtLanding());
	}
}

// ================================================================================================================================= the page

void UAstraLiftSubsystem::PaintScreen(int32 Line, UCanvas* Canvas, int32 W, int32 H)
{
	if (!Run.IsValidIndex(Line) || !Run[Line].Car || !Net.Lines.IsValidIndex(Line) || !Canvas || !TitleFont || !MonoFont)
	{
		return;
	}
	const FAstraLiftLine& L = Net.Lines[Line];
	const AAstraLiftCar* Car = Run[Line].Car;
	const FAstraLiftBrain& B = Car->Brain;
	FPaint P;
	P.C = Canvas;
	P.Title = TitleFont;
	P.Mono = MonoFont;
	const FLinearColor Accent = L.Kind == EAstraLiftKind::Bridge ? COMMAND : (L.Kind == EAstraLiftKind::Service || L.Kind == EAstraLiftKind::Cargo) ? AMBER : CYAN;
	P.Rect(0, 0, W, H, BG);
	// the header: the lift's name, and what it is doing
	P.Rect(0, 0, W, 70, HEADER);
	P.Rect(0, 0, 10, 70, Accent);
	P.Line(0, 70, W, 70, Accent, 2.f);
	P.Text(28, 12, L.Name.ToUpper(), false, 38, TEXTC);
	FLinearColor StatusColor;
	P.Text(W - 24, 24, StatusLine(Line, StatusColor), true, 22, StatusColor, 2, true);

	TArray<FRow> Rows;
	MenuRows(Line, Rows);
	const bool bMenu = MenuLine == Line;
	if (bMenu)
	{
		// the list: every stop, the deck's number, its name and the places on it; the mark is amber, the deck the car is at is dim
		const float Top = 90.f, Bottom = 560.f;
		const float RowH = FMath::Min(52.f, (Bottom - Top) / FMath::Max(1, Rows.Num()));
		for (int32 I = 0; I < Rows.Num(); ++I)
		{
			const FRow& R = Rows[I];
			const float Y = Top + I * RowH;
			const bool bSel = I == MenuSel;
			if (bSel)
			{
				P.Rect(30, Y, W - 60, RowH - 5, RGB(40, 28, 8));
				P.Frame(30, Y, W - 60, RowH - 5, AMBER, 2.f);
			}
			else
			{
				P.Rect(30, Y, W - 60, RowH - 5, PANEL);
				P.Frame(30, Y, W - 60, RowH - 5, DIM);
			}
			const FLinearColor Ink = R.bHere ? DIM : (bSel ? AMBER : TEXTC);
			P.Text(80, Y + (RowH - 5) * 0.5f - 18, R.Label, false, 38, Ink, 1, true);
			P.Text(130, Y + (RowH - 5) * 0.5f - 15, R.Name, false, FMath::Min(30.f, RowH * 0.6f), Ink);
			if (!R.Places.IsEmpty() && RowH > 36.f)
			{
				P.Text(W - 50, Y + (RowH - 5) * 0.5f - 9, R.bHere ? FString(TEXT("YOU ARE HERE")) : R.Places, true, 15, R.bHere ? CYAN : (bSel ? AMBER : RGB(120, 160, 205)), 2);
			}
			else if (R.bHere)
			{
				P.Text(W - 50, Y + (RowH - 5) * 0.5f - 9, TEXT("HERE"), true, 15, CYAN, 2);
			}
		}
		P.Rect(0, H - 56, W, 56, HEADER);
		P.Text(28, H - 40, TEXT("W / S  OR THE MOUSE  ·  E  GO  ·  ESC  CLOSE"), true, 18, RGB(120, 160, 205));
		return;
	}

	// at rest and on the way: the deck's figure large, and the line's ladder with the car's marker on it
	const int32 Shown = ShownStop(Line);
	const FAstraLiftStop& S = L.Stops.IsValidIndex(Shown) ? L.Stops[Shown] : L.Stops[0];
	const FString Figure = L.bShuttle ? S.Section.ToUpper() : FString::FromInt(S.Deck);
	P.Text(330, 120, Figure, false, 330, TEXTC, 1, true);
	P.Text(330, 470, L.bShuttle ? FString::Printf(TEXT("SECTION %s"), *S.Section.ToUpper()) : S.DeckName.ToUpper(), false, 38, CYAN, 1);
	if (!S.Places.IsEmpty())
	{
		P.Text(330, 520, S.Places[0], true, 17, RGB(120, 160, 205), 1);
	}
	// the ladder: the stops evenly spaced (the highest first), the car's place between them from how far it has got
	const float LX = 760.f, LTop = 110.f, LBottom = 540.f;
	const int32 N = Rows.Num();
	const float Step = N > 1 ? (LBottom - LTop) / (N - 1) : 0.f;
	P.Line(LX, LTop, LX, LBottom, DIM, 3.f);
	const int32 Target = B.LegTarget();
	for (int32 I = 0; I < N; ++I)
	{
		const float Y = LTop + I * Step;
		const bool bHere = Rows[I].Stop == B.AtLanding();
		const bool bTarget = Rows[I].Stop == Target;
		P.Line(LX - 12, Y, LX + 12, Y, bTarget ? AMBER : (bHere ? CYAN : DIM), bTarget || bHere ? 4.f : 2.f);
		P.Text(LX + 28, Y - 11, Rows[I].Label, false, 22, bTarget ? AMBER : (bHere ? CYAN : RGB(90, 130, 175)));
	}
	// the marker: between the stop it left and the one ahead (the display is ordered the other way round for a shaft: row 0 is the highest)
	{
		float RowPos = 0.f;
		if (L.Stops.Num() > 1)
		{
			int32 Lo = 0;
			for (int32 I = 0; I + 1 < L.Stops.Num(); ++I)
			{
				if (L.Stops[I].S <= B.S() + 0.5f)
				{
					Lo = I;
				}
			}
			const int32 Hi = FMath::Min(Lo + 1, L.Stops.Num() - 1);
			const float Span = L.Stops[Hi].S - L.Stops[Lo].S;
			const float F = Span > 1.f ? FMath::Clamp((B.S() - L.Stops[Lo].S) / Span, 0.f, 1.f) : 0.f;
			RowPos = FMath::Lerp((float)StopToRow(Line, Lo), (float)StopToRow(Line, Hi), F);
		}
		const float MY = LTop + RowPos * Step;
		const FLinearColor MarkCol = B.State() == FAstraLiftBrain::EState::Moving ? AMBER : CYAN;
		P.Rect(LX - 20, MY - 7, 40, 14, MarkCol);
		P.Frame(LX - 24, MY - 11, 48, 22, MarkCol, 2.f);
	}
	P.Rect(0, H - 56, W, 56, HEADER);
	P.Text(28, H - 40, B.State() == FAstraLiftBrain::EState::Moving ? FString(TEXT("IN TRANSIT")) : FString(TEXT("E  CHOOSE  ·  OR SAY WHERE TO")), true, 18, RGB(120, 160, 205));
}
