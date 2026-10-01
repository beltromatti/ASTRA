// ASTRA — live bridge screens.

#include "AstraScreensSubsystem.h"

#include "ASTRA.h"
#include "AstraBattleSubsystem.h"
#include "AstraDamageModel.h"
#include "AstraShipPlan.h"
#include "AstraShipSubsystem.h"
#include "AstraStations.h"
#include "GameFramework/Pawn.h"
#include "AstraMindSubsystem.h"
#include "Engine/GameInstance.h"
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
#include "Engine/StaticMeshActor.h"
#include "Engine/StaticMesh.h"
#include "Sound/SoundBase.h"
#include "Kismet/GameplayStatics.h"
#include "ASTRAPlayerController.h"
#include "Engine/TextureRenderTarget2D.h"
#include "Misc/Paths.h"
#include "Misc/FileHelper.h"
#include "ImageUtils.h"

DECLARE_CYCLE_STAT(TEXT("Screens"), STAT_AstraScreens, STATGROUP_Astra);

namespace
{
	// diagnostics: time each page's redraw including the render thread's work (blocks the game thread while on)
	TAutoConsoleVariable<int32> CVarScreensProfile(TEXT("astra.screens.profile"), 0, TEXT("Log the cost of each bridge screen redraw"));
	FAutoConsoleCommandWithWorldAndArgs CmdScreensDump(TEXT("astra.screens.dump"),
		TEXT("Testing: astra.screens.dump <Page> [path.png] (Helm_A, Ops_Touch, Master, Tactical...)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& A, UWorld* World)
		{
			UAstraScreensSubsystem* S = World ? World->GetSubsystem<UAstraScreensSubsystem>() : nullptr;
			if (S && A.Num())
			{
				const FString Path = A.Num() > 1 ? A[1] : FPaths::ProjectSavedDir() / TEXT("Play") / (A[0] + TEXT(".png"));
				UE_LOG(LogASTRA, Display, TEXT("[Screens] dump %s -> %s: %s"), *A[0], *Path, S->DumpPage(A[0], Path) ? TEXT("ok") : TEXT("failed"));
			}
		}));
	TAutoConsoleVariable<FString> CVarScreensSkip(TEXT("astra.screens.skip"), TEXT(""), TEXT("Diagnostics: pages never redrawn (comma-separated names, e.g. Master,Tactical)"));
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

	/** Thin drawing helper over a UCanvas, in render-target pixels. The items are kept and drawn together when the
	 *  page is done — every fill, then every line, then every text: the canvas starts a new batch each time the kind
	 *  of item changes, and the Master page's hundreds of alternating cells, frames and labels made it an 11 ms GPU
	 *  spike each time it was redrawn (a stutter every 11 frames on the bridge). */
	struct FPaint
	{
		UCanvas* C = nullptr;
		UFont* Title = nullptr;
		UFont* Mono = nullptr;
		float Time = 0.f;
		mutable TArray<FCanvasTileItem> Tiles;
		mutable TArray<FCanvasLineItem> Lines;
		mutable TArray<FCanvasTextItem> Texts;

		~FPaint() { Flush(); }
		void Flush() const
		{
			for (FCanvasTileItem& T : Tiles) { C->DrawItem(T); }
			for (FCanvasLineItem& L : Lines) { C->DrawItem(L); }
			for (FCanvasTextItem& T : Texts) { C->DrawItem(T); }
			Tiles.Reset();
			Lines.Reset();
			Texts.Reset();
		}
		void Rect(float X, float Y, float W, float H, const FLinearColor& Col) const
		{
			FCanvasTileItem T(FVector2D(X, Y), FVector2D(W, H), Col);
			T.BlendMode = Col.A < 1.f ? SE_BLEND_Translucent : SE_BLEND_Opaque;
			Tiles.Add(T);
		}
		void Frame(float X, float Y, float W, float H, const FLinearColor& Col, float Thick = 1.f) const
		{
			Line(X, Y, X + W, Y, Col, Thick);
			Line(X + W, Y, X + W, Y + H, Col, Thick);
			Line(X + W, Y + H, X, Y + H, Col, Thick);
			Line(X, Y + H, X, Y, Col, Thick);
		}
		void Line(float X0, float Y0, float X1, float Y1, const FLinearColor& Col, float Thick = 1.f) const
		{
			FCanvasLineItem L(FVector2D(X0, Y0), FVector2D(X1, Y1));
			L.SetColor(Col);
			L.LineThickness = Thick;
			Lines.Add(L);
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
			Texts.Add(T);
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
		return Kind == TEXT("fire") ? TEXT("FIRE") : (Kind == TEXT("hull breach") ? TEXT("BREACH") : (Kind.Contains(TEXT("radiator")) ? TEXT("RADIATOR") : TEXT("CONDUIT")));
	}

	/** How urgent an incident is on a damage board: the unattended first, then a breach (the air goes) before a fire (it spreads) before power, then how bad. */
	float IncidentRank(const FAstraDamage& D)
	{
		return (D.Team < 0 ? 100.f : 0.f) + (D.Kind.Contains(TEXT("breach")) ? 30.f : (D.Kind.Contains(TEXT("fire")) ? 20.f : 10.f)) + 9.f * D.Severity;
	}

	/** What a conduit incident costs, in words: the allocations that pass through the room and the power it has left. */
	FString ConduitText(const FAstraDamage& D)
	{
		return D.System.IsEmpty() ? FString() : FString::Printf(TEXT("%s · POWER %.0f %%"), *D.System.ToUpper(), 100.f * FMath::Clamp(1.f - D.Severity, 0.f, 1.f));
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
	                                   TEXT("Ops_C"), TEXT("Sensors_A"), TEXT("Sensors_B"), TEXT("Eng_A"), TEXT("Eng_B"),
	                                   TEXT("Mess_News"), TEXT("Mess_Memorial"), TEXT("Pad"),
	                                   // the control surfaces: the desk panels, and the third monitor where it had a static page
	                                   TEXT("Comms_A"), TEXT("Comms_B"), TEXT("Flight_A"), TEXT("Flight_B"),
	                                   TEXT("Helm_Touch"), TEXT("Ops_Touch"), TEXT("Sensors_Touch"), TEXT("Eng_Touch"), TEXT("Flight_Touch"),
	                                   TEXT("Comms_Touch"), TEXT("Helm_C"), TEXT("Sensors_C"), TEXT("Eng_C"), TEXT("Flight_C"), TEXT("Comms_C")};
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
	const FIntPoint Size = Name == TEXT("Master") ? FIntPoint(2048, 864) : (Name == TEXT("Tactical") ? FIntPoint(2048, 256)
	                     : Name.StartsWith(TEXT("Mess_")) ? FIntPoint(2048, 614) : FIntPoint(1024, 640));
	UAstraScreenPage* P = NewObject<UAstraScreenPage>(this);
	P->Name = Name;
	P->Owner = this;
	P->Target = UCanvasRenderTarget2D::CreateCanvasRenderTarget2D(this, UCanvasRenderTarget2D::StaticClass(), Size.X, Size.Y);
	P->Target->ClearColor = BG;
	P->Target->OnCanvasRenderTargetUpdate.AddDynamic(P, &UAstraScreenPage::Draw);
	if (Name.StartsWith(TEXT("Mess_")))
	{
		P->Interval = 3.f;   // the mess's walls change with the war, not by the second
	}
	if (Name == TEXT("Pad"))
	{
		P->Interval = 0.12f; // in the Captain's hand, in front of the eyes: it must answer at once
	}
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
	SCOPE_CYCLE_COUNTER(STAT_AstraScreens);
	Time += DeltaTime;
	// one screen redrawn per frame at most (the most overdue one): drawing them all in the same frame was a
	// 12 ms hitch four times a second
	UAstraScreenPage* Due = nullptr;
	for (UAstraScreenPage* P : Pages)
	{
		if (!bPadVisible && P->Name == TEXT("Pad"))
		{
			continue;                                  // the datapad is painted only while the Captain holds it up
		}
		if (!CVarScreensSkip.GetValueOnGameThread().IsEmpty() && CVarScreensSkip.GetValueOnGameThread().Contains(P->Name))
		{
			continue;
		}
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

UTextureRenderTarget2D* UAstraScreensSubsystem::GetPadTarget()
{
	if (!TitleFont || !MonoFont)
	{
		return nullptr;
	}
	UAstraScreenPage* P = PageFor(TEXT("Pad"));
	P->Interval = 0.25f;
	return P->Target;
}

void UAstraScreensSubsystem::SetPadVisible(bool bVisible)
{
	if (bVisible && !bPadVisible)
	{
		for (UAstraScreenPage* P : Pages)
		{
			if (P->Name == TEXT("Pad"))
			{
				P->Wait = -1.f;                        // raised: painted at once
			}
		}
	}
	bPadVisible = bVisible;
}

void UAstraScreensSubsystem::DrawPage(const FString& Name, UCanvas* Canvas, int32 Width, int32 Height)
{
	FString Station, Slot;
	if (Name == TEXT("Master")) { DrawMaster(Canvas, Width, Height); }
	else if (Name == TEXT("Pad")) { DrawPad(Canvas, Width, Height); }
	else if (Name == TEXT("Tactical")) { DrawTactical(Canvas, Width, Height); }
	else if (Name.Split(TEXT("_"), &Station, &Slot))
	{
		static const TMap<FString, FString> Ids = {{TEXT("Helm"), TEXT("helm")}, {TEXT("Ops"), TEXT("ops")}, {TEXT("Sensors"), TEXT("sensors")},
		                                           {TEXT("Eng"), TEXT("engineering")}, {TEXT("Flight"), TEXT("flight")}, {TEXT("Comms"), TEXT("comms")}};
		if (Slot == TEXT("Touch") || (Slot == TEXT("C") && Station != TEXT("Ops")))
		{
			if (const FString* Id = Ids.Find(Station))
			{
				DrawControls(Canvas, Width, Height, *Id);
			}
		}
		else if (Station == TEXT("Comms")) { DrawComms(Canvas, Width, Height, Slot); }
		else if (Station == TEXT("Flight")) { DrawFlight(Canvas, Width, Height, Slot); }
		else if (Station == TEXT("Helm")) { DrawHelm(Canvas, Width, Height, Slot); }
		else if (Station == TEXT("Ops")) { DrawOps(Canvas, Width, Height, Slot); }
		else if (Station == TEXT("Sensors")) { DrawSensors(Canvas, Width, Height, Slot); }
		else if (Station == TEXT("Eng")) { DrawEngineering(Canvas, Width, Height, Slot); }
		else if (Station == TEXT("Mess")) { DrawMess(Canvas, Width, Height, Slot); }
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
	P.Header(W, TEXT("ASN Aquila · Master Systems Display"), FString::Printf(TEXT("%s · AQUILA CLASS · 780 M"), Ship ? *Ship->GetHullNumber() : TEXT("CVC-01")), COMMAND);

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
	// a cell is a deck and a section; the worst incident in it shows (the place it is in, the team on it), and how many more there are
	struct FBoardCell { const FAstraDamage* Worst = nullptr; int32 N = 0; };
	TArray<FBoardCell> Cells;
	Cells.SetNum(12 * 8);
	for (const FAstraDamage& D : Ship->GetDamage())
	{
		FBoardCell& Cell = Cells[FMath::Clamp(D.Deck - 1, 0, 11) * 8 + FMath::Clamp(int32(D.Section - TEXT('A')), 0, 7)];
		++Cell.N;
		if (!Cell.Worst || IncidentRank(D) > IncidentRank(*Cell.Worst))
		{
			Cell.Worst = &D;
		}
	}
	for (int32 Index = 0; Index < Cells.Num(); ++Index)
	{
		if (!Cells[Index].Worst)
		{
			continue;
		}
		const FAstraDamage& D = *Cells[Index].Worst;
		const float X = GX + (Index % 8) * (CW + Gap), Y = GY + (Index / 8) * (CH + Gap);
		FLinearColor K = KindColor(D.Kind);
		const float A = D.Team < 0 ? P.Pulse(D.Kind == TEXT("fire") ? 1.6f : 0.8f) : 0.55f;
		P.Rect(X, Y, CW, CH, FLinearColor(K.R, K.G, K.B, 0.35f * A + 0.1f));
		P.Frame(X, Y, CW, CH, K, 2.f);
		P.Text(X + 8, Y + 3, KindShort(D.Kind), true, 15, TEXTC, 0, true);
		if (D.Team >= 0)
		{
			P.Text(X + CW - 8, Y + 3, FString::Printf(TEXT("T%d"), D.Team + 1), true, 15, CYAN, 2, true);
		}
		else
		{
			P.Text(X + CW - 8, Y + 4, Cells[Index].N > 1 ? FString::Printf(TEXT("NO TEAM +%d"), Cells[Index].N - 1) : FString(TEXT("NO TEAM")), true, 12, K, 2);
		}
		if (!D.Place.IsEmpty())
		{
			P.Text(X + 8, Y + 22, D.Place.ToUpper().Left(14), true, 12, TEXTC * 0.85f);
		}
		if (D.Team >= 0 && D.Travel > 0.f)
		{
			// the team on its way: a marker walking along a thin track
			const float Walk = D.Travel0 > 0.f ? FMath::Clamp(1.f - D.Travel / D.Travel0, 0.f, 1.f) : 0.f;
			P.Rect(X + 6, Y + CH - 9, CW - 12, 1.5f, DIM);
			P.Rect(X + 6 + (CW - 24) * Walk, Y + CH - 12, 12, 6, CYAN);
		}
		else if (D.Team >= 0)
		{
			P.Rect(X + 6, Y + CH - 11, (CW - 12) * FMath::Clamp(D.Progress, 0.f, 1.f), 6, CYAN);
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
		Helm = Ship->GetInterceptRangeKm() < 0.0 ? FString::Printf(TEXT("INTERCEPT %s  ·  BEARING ONLY"), *Ship->GetInterceptId())
		     : FString::Printf(TEXT("INTERCEPT %s  ·  %.1f KM  ·  %s"), *Ship->GetInterceptId(), Ship->GetInterceptRangeKm(),
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
		const UAstraBattleSubsystem::FPlotCounts& Pc = Battle->PlotCounts();      // (counted once for each step of the battle, with the plot's lists)
		Hostiles = Pc.HostileShips + Pc.HostileCraft;
		Friends = Pc.FriendlyShips;
	}
	P.Text(RX, 766, FString::Printf(TEXT("CONTACTS  %d HOSTILE  ·  %d FRIENDLY"), Hostiles, Friends), true, 18, Hostiles ? RED : TEXTC);
	const TArray<FString>& Ev = Ship->GetRecentEvents();
	P.Footer(W, H, Ev.Num() ? Ev.Last().ToUpper() : FString(TEXT("ALL DECKS PRESSURIZED · ALL STATIONS MANNED")), Ship->GetDamage().Num() ? AMBER : GREEN);
	P.Text(W - 16, H - 25, ShipClock(Time), true, 14, DIM, 2);
}

namespace
{
	/** Word-wraps S into lines of at most N characters (a monospaced log). */
	TArray<FString> Wrap(const FString& S, int32 N)
	{
		TArray<FString> Words, Out;
		S.ParseIntoArrayWS(Words);
		FString Line;
		for (const FString& Wd : Words)
		{
			if (!Line.IsEmpty() && Line.Len() + 1 + Wd.Len() > N)
			{
				Out.Add(Line);
				Line.Reset();
			}
			Line += (Line.IsEmpty() ? TEXT("") : TEXT(" ")) + Wd.Left(N);
		}
		if (!Line.IsEmpty())
		{
			Out.Add(Line);
		}
		return Out;
	}
}

void UAstraScreensSubsystem::DrawPadOverview(UCanvas* C, int32 W, int32 H)
{
	// the Captain's datapad: the ship at a glance anywhere aboard — condition, where the Captain is, hull, shields and
	// heat, the contacts (as the sensors know them), fire control, flight groups, damage, the standing orders in force
	// and the last words heard over the comms
	const UAstraShipSubsystem* Ship = GetWorld()->GetSubsystem<UAstraShipSubsystem>();
	const UAstraBattleSubsystem* Battle = GetWorld()->GetSubsystem<UAstraBattleSubsystem>();
	const UAstraMindSubsystem* Mind = GetWorld()->GetGameInstance() ? GetWorld()->GetGameInstance()->GetSubsystem<UAstraMindSubsystem>() : nullptr;
	if (!Ship)
	{
		return;
	}
	FPaint P{C, TitleFont, MonoFont, Time};
	P.Rect(0, 0, W, H, BG);
	// a margin all round: held at an angle, the bezel's lip hides the page's edges; secondary text brighter than on the
	// bridge's screens (the pad is read anywhere, in sunlight too)
	const float MX = 46.f, RX = W - 46.f;
	const FLinearColor SOFT = RGB(120, 160, 205);
	P.Rect(0, 0, W, 50, HEADER);
	P.Rect(MX - 14, 12, 6, 30, COMMAND);
	P.Text(MX, 12, TEXT("ASN AQUILA · CAPTAIN'S DATAPAD"), false, 26, TEXTC);
	P.Text(RX, 18, FString::Printf(TEXT("%s · %s"), *Ship->GetHullNumber(), *ShipClock(Time).Right(13)), true, 15, CYAN, 2);
	P.Line(0, 50, W, 50, COMMAND, 2.f);
	// condition and where the Captain is
	const EAstraAlert Alert = Ship->GetAlert();
	FLinearColor AC = AlertColor(Alert);
	if (Alert == EAstraAlert::Red)
	{
		AC.A = P.Pulse(0.8f) * 0.6f + 0.4f;
	}
	P.Text(MX, 54, TEXT("CONDITION"), false, 18, CYAN);
	P.Text(MX, 72, AlertText(Alert), false, 44, AC);
	P.Text(RX, 58, TEXT("CAPTAIN"), false, 16, SOFT, 2);
	P.Text(RX, 80, Ship->CaptainPlace(), true, 20, TEXTC, 2);
	// hull, shields, heat
	const float Sh = Battle ? Battle->PlayerShieldFraction() : 1.f;
	const float Hu = Battle ? Battle->PlayerHullFraction() : 1.f;
	const float He = Ship->GetHeatPct() / 100.f;
	const float BW = (RX - MX - 40) / 3.f;
	P.Bar(MX, 128, BW, 16, Hu, TEXT("Hull"), FString::Printf(TEXT("%.0f %%"), 100.f * Hu), Level(Hu));
	P.Bar(MX + BW + 20, 128, BW, 16, Sh, TEXT("Shields"), Ship->AreShieldsUp() ? FString::Printf(TEXT("%.0f %%"), 100.f * Sh) : FString(TEXT("DOWN")),
	      Ship->AreShieldsUp() ? Level(Sh) : DIM);
	P.Bar(MX + 2 * (BW + 20), 128, BW, 16, FMath::Clamp(He, 0.f, 1.f), TEXT("Heat"), FString::Printf(TEXT("%.0f %%"), 100.f * He),
	      He > 0.9f ? RED : (He > 0.7f ? AMBER : CYAN));
	// contacts, as the sensors know them: the nearest first, bearings (no range) after
	static const TArray<FAstraHoloBlip> NoBlips;
	const TArray<FAstraHoloBlip>& Blips = Battle ? Battle->HoloBlips() : NoBlips;
	int32 Hostiles = 0, Friends = 0;
	TArray<const FAstraHoloBlip*> Ships;
	for (const FAstraHoloBlip& B : Blips)
	{
		if (B.Kind != 0 || B.bPlayer || B.bCraft)
		{
			continue;
		}
		Hostiles += (B.bHostile && !B.bRetreating) ? 1 : 0;
		Friends += B.Side == EAstraSide::Astra ? 1 : 0;
		Ships.Add(&B);
	}
	Ships.Sort([](const FAstraHoloBlip& A, const FAstraHoloBlip& B)
	{
		return (A.bBearingOnly ? 1.0e6f : A.RangeKm) < (B.bBearingOnly ? 1.0e6f : B.RangeKm);
	});
	const UAstraBattleSubsystem::FFireControl Fc = Battle ? Battle->GetFireControl() : UAstraBattleSubsystem::FFireControl();
	P.Line(MX, 180, RX, 180, DIM);
	P.Text(MX, 188, TEXT("CONTACTS"), false, 18, CYAN);
	P.Text(RX, 190, FString::Printf(TEXT("%d HOSTILE · %d FRIENDLY%s"), Hostiles, Friends,
	                                    Fc.Inbound ? *FString::Printf(TEXT(" · %d MISSILES INBOUND"), Fc.Inbound) : TEXT("")), true, 16,
	       (Hostiles || Fc.Inbound) ? RED : DIM, 2);
	int32 Row = 0;
	for (const FAstraHoloBlip* B : Ships)
	{
		if (Row >= 4)
		{
			break;
		}
		const float Y = 216.f + Row * 26.f;
		const FLinearColor Col = B->bUnknown ? TEXTC : (B->Side == EAstraSide::Astra ? CYAN : (B->bHostile ? (B->bHoldFire ? AMBER : RED) : YELLOW));
		const FString What = !B->Name.IsEmpty() ? B->Name.ToUpper() : (!B->ClassShort.IsEmpty() ? B->ClassShort.ToUpper() : FString(TEXT("UNIDENTIFIED")));
		const float Brg = FMath::Fmod(FMath::RadiansToDegrees(FMath::Atan2(B->Rel.Y, B->Rel.X)) + Ship->GetHeadingDeg() + 720.f, 360.f);
		P.Text(MX, Y, B->Contact, true, 17, Col, 0, true);
		P.Text(MX + 88, Y, What.Left(28), true, 17, TEXTC);
		P.Text(640, Y, B->bBearingOnly ? FString(TEXT("NO RANGE")) : FString::Printf(TEXT("%.1f KM"), B->RangeKm), true, 17, TEXTC, 2);
		P.Text(720, Y, FString::Printf(TEXT("%03.0f"), Brg), true, 17, TEXTC, 2);
		P.Text(RX, Y, B->bJamming ? TEXT("JAMMING") : B->bBearingOnly ? TEXT("BEARING ONLY")
		                  : B->bUnknown ? TEXT("UNKNOWN") : (B->Side == EAstraSide::Astra ? TEXT("FRIENDLY")
		                  : (B->bHostile ? (B->bRetreating ? TEXT("WITHDRAWING") : (B->bHoldFire ? TEXT("HOLDING FIRE") : TEXT("HOSTILE"))) : TEXT("NEUTRAL"))),
		       true, 16, Col, 2);
		++Row;
	}
	if (Ships.Num() == 0)
	{
		P.Text(MX, 216, TEXT("NO CONTACTS ON THE PLOT"), true, 17, SOFT);
	}
	else if (Ships.Num() > 4)
	{
		P.Text(RX, 216 + 4 * 26, FString::Printf(TEXT("+%d MORE"), Ships.Num() - 4), true, 14, SOFT, 2);
	}
	// fire control, flight groups, damage
	P.Line(MX, 330, RX, 330, DIM);
	int32 Busy = 0;
	for (const FAstraDamage& D : Ship->GetDamage())
	{
		Busy += D.Team >= 0 ? 1 : 0;
	}
	P.Text(MX, 338, !Fc.Target.IsEmpty() ? FString::Printf(TEXT("FIRE CONTROL  %s  %.1f KM  ·  RAILGUNS %d VOLLEYS  ·  VLS %d"), *Fc.Target, Fc.TargetRangeKm, Fc.RailVolleys, Fc.Missiles)
	                                   : FString::Printf(TEXT("FIRE CONTROL  NO TARGET  ·  VLS %d MISSILES"), Fc.Missiles), true, 16, Fc.Target.IsEmpty() ? SOFT : AMBER);
	P.Text(MX, 360, TEXT("FLIGHT  ") + (Battle ? Battle->FlightLine() : FString()), true, 16, TEXTC);
	const int32 Incidents = Ship->GetDamage().Num();
	P.Text(MX, 382, Incidents ? FString::Printf(TEXT("DAMAGE  %d INCIDENT%s  ·  %d / %d TEAMS OUT"), Incidents, Incidents > 1 ? TEXT("S") : TEXT(""), Busy, Ship->GetNumDamageTeams())
	                          : FString(TEXT("DAMAGE  NONE  ·  ALL DECKS PRESSURIZED")), true, 16, Incidents ? AMBER : GREEN);
	// standing orders
	P.Line(MX, 410, RX, 410, DIM);
	P.Text(MX, 416, TEXT("STANDING ORDERS"), false, 18, CYAN);
	const TArray<FString>& Orders = Ship->GetStandingOrders();
	if (Orders.Num() == 0)
	{
		P.Text(MX, 442, TEXT("NONE IN FORCE"), true, 16, SOFT);
	}
	for (int32 i = 0; i < FMath::Min(Orders.Num(), 3); ++i)
	{
		P.Text(MX, 442 + i * 22, TEXT("· ") + Orders[Orders.Num() - 1 - i].Left(104), true, 15, TEXTC);
	}
	// the comms log: the last words heard, newest at the bottom
	P.Line(MX, 512, RX, 512, DIM);
	P.Text(MX, 518, TEXT("COMMS"), false, 18, CYAN);
	TArray<TPair<FString, FString>> Log;
	if (Mind)
	{
		const TArray<TPair<FString, FString>>& Heard = Mind->GetHeardLines();
		for (int32 i = FMath::Max(0, Heard.Num() - 3); i < Heard.Num(); ++i)
		{
			Log.Add(Heard[i]);
		}
	}
	TArray<TPair<FString, FString>> Lines;   // (who, text) per printed line
	for (const TPair<FString, FString>& L : Log)
	{
		FString Who = L.Key;
		int32 Paren = INDEX_NONE;
		if (Who.FindChar(TEXT('('), Paren))
		{
			Who = Who.Left(Paren).TrimEnd();
		}
		TArray<FString> Parts;
		Who.ParseIntoArrayWS(Parts);
		Who = Parts.Num() ? Parts.Last().ToUpper() : FString(TEXT("SHIP"));
		bool bFirst = true;
		for (const FString& Seg : Wrap(L.Value, 86))
		{
			Lines.Add(TPair<FString, FString>(bFirst ? Who : FString(), Seg));
			bFirst = false;
		}
	}
	const int32 MaxLines = 3;
	for (int32 i = FMath::Max(0, Lines.Num() - MaxLines), k = 0; i < Lines.Num(); ++i, ++k)
	{
		const float Y = 544.f + k * 21.f;
		P.Text(MX, Y, Lines[i].Key, true, 15, CYAN);
		P.Text(MX + 100, Y, Lines[i].Value, true, 15, TEXTC);
	}
	if (Lines.Num() == 0)
	{
		P.Text(MX, 544, TEXT("QUIET ON ALL CHANNELS"), true, 15, SOFT);
	}
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
	const UAstraBattleSubsystem::FPlotCounts& Pc = Battle->PlotCounts();
	const int32 Hostiles = Pc.HostileShips + Pc.HostileCraft;
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
		const bool bBearing = Ship->GetInterceptRangeKm() < 0.0;
		P.Text(MX, 494, bBearing ? FString(TEXT("RANGE UNKNOWN")) : FString::Printf(TEXT("RANGE %.1f KM"), Ship->GetInterceptRangeKm()), true, 22, CYAN);
		P.Text(MX, 526, bBearing ? TEXT("STEERING DOWN THE BEARING") : (Ship->IsBroadside() ? TEXT("BROADSIDE · HOLDING RANGE") : TEXT("CLOSING ON LEAD POINT")),
		       true, 18, CYAN);
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
			St = ConduitText(D) + TEXT(" · ") + St;
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
	const TArray<FAstraHoloBlip>& Blips = Battle->HoloBlips();
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
	TArray<const FAstraHoloBlip*> Nearest;            // the warships, the nearest first (the shared list is not ours to reorder)
	for (const FAstraHoloBlip& B : Blips)
	{
		if (B.Kind == 0 && !B.bPlayer && !B.bCraft)
		{
			Nearest.Add(&B);
		}
	}
	Nearest.Sort([](const FAstraHoloBlip& A, const FAstraHoloBlip& B)
	{
		return (A.bBearingOnly ? 1.0e6f : A.RangeKm) < (B.bBearingOnly ? 1.0e6f : B.RangeKm);   // bearings (no range) last
	});
	for (const FAstraHoloBlip* Bp : Nearest)
	{
		const FAstraHoloBlip& B = *Bp;
		if (Row >= 11)
		{
			break;
		}
		const float Y = 84.f + Row * 48.f;
		const FLinearColor Col = B.bUnknown ? DIM : (B.Side == EAstraSide::Astra ? CYAN : (B.bHostile ? (B.bHoldFire ? AMBER : RED) : YELLOW));
		P.Rect(16, Y, W - 32, 42, PANEL);
		P.Rect(16, Y, 6, 42, Col);
		P.Text(30, Y + 9, B.Contact, true, 20, Col, 0, true);
		P.Text(110, Y + 9, !B.Name.IsEmpty() ? B.Name.ToUpper() : (!B.ClassShort.IsEmpty() ? B.ClassShort.ToUpper() : FString(TEXT("UNIDENTIFIED"))), false, 22, TEXTC);
		P.Text(700, Y + 9, B.bBearingOnly ? FString(TEXT("—")) : FString::Printf(TEXT("%.1f KM"), B.RangeKm), true, 18, TEXTC, 2);
		const float Brg = FMath::Fmod(FMath::RadiansToDegrees(FMath::Atan2(B.Rel.Y, B.Rel.X)) + Ship->GetHeadingDeg() + 720.f, 360.f);
		P.Text(790, Y + 9, FString::Printf(TEXT("%03.0f"), Brg), true, 18, TEXTC, 2);
		P.Text(W - 24, Y + 11, B.bJamming ? TEXT("JAMMING") : B.bBearingOnly ? TEXT("BEARING ONLY") : B.bUnknown ? TEXT("UNKNOWN") : (B.Side == EAstraSide::Astra ? TEXT("FRIENDLY")
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
		P.Bar(40, 340, W - 80, 26, Sum / Ship->GetPowerBudget(), TEXT("Allocation"), FString::Printf(TEXT("%.0f / %.0f %%"), Sum, Ship->GetPowerBudget()),
		      Sum > 660.f ? AMBER : CYAN);
		// the heat: load, radiators, coolant
		const float Heat = Ship->GetHeatPct();
		const FLinearColor HeatC = Heat >= 90.f ? RED : (Heat >= 70.f ? AMBER : CYAN);
		P.Bar(40, 420, W - 80, 26, FMath::Min(1.f, Heat / 100.f), TEXT("Thermal load"), FString::Printf(TEXT("%.0f %%  %s"), Heat,
		      Ship->GetHeatRate() > 0.05f ? TEXT("RISING") : (Ship->GetHeatRate() < -0.05f ? TEXT("FALLING") : TEXT("STEADY"))), HeatC);
		P.Text(40, 500, FString::Printf(TEXT("RADIATORS %s%s"), Ship->AreRadiatorsOut() ? TEXT("EXTENDED") : TEXT("RETRACTED"),
		       Ship->GetRadiatorHealth() < 0.99f ? *FString::Printf(TEXT(" · %.0f %% EFFECTIVE"), 100.f * Ship->GetRadiatorHealth()) : TEXT("")),
		       true, 22, Ship->GetRadiatorHealth() < 0.99f ? AMBER : TEXTC, 0, true);
		P.Text(W - 40, 500, FString::Printf(TEXT("COOLANT VENTS %d / 3"), Ship->GetCoolantVents()), true, 22, Ship->GetCoolantVents() ? TEXTC : AMBER, 2, true);
		P.Footer(W, H, Heat >= 90.f ? TEXT("HEAT CRITICAL · CONDUITS AT RISK") : (Heat >= 70.f ? TEXT("RUNNING HOT · SYSTEMS THROTTLED")
		         : TEXT("CONTAINMENT STABLE · COOLANT NOMINAL")), Heat >= 90.f ? RED : (Heat >= 70.f ? AMBER : GREEN));
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
		P.Text(40, Y + 12, FString::Printf(TEXT("%s · %s"), *D.Where().ToUpper(), *ConduitText(D)), true, 20, TEXTC, 0, true);
		P.Text(W - 36, Y + 14, D.Team < 0 ? FString(TEXT("NO TEAM")) : FString::Printf(TEXT("TEAM %d"), D.Team + 1), true, 18, D.Team < 0 ? YELLOW : CYAN, 2);
	}
	if (Row == 0)
	{
		P.Text(W * 0.5f, H * 0.5f - 20, TEXT("GRID INTACT"), false, 40, GREEN, 1);
	}
}

// ------------------------------------------------------------------------------------------------------ the mess
void UAstraScreensSubsystem::DrawMess(UCanvas* C, int32 W, int32 H, const FString& Slot)
{
	FPaint P{C, TitleFont, MonoFont, Time};
	const UAstraShipSubsystem* Ship = GetWorld() ? GetWorld()->GetSubsystem<UAstraShipSubsystem>() : nullptr;
	if (!Ship)
	{
		return;
	}
	if (Slot == TEXT("Memorial"))
	{
		// the Aquila's dead, by name: the whole ship passes this wall at every meal
		P.Rect(0, 0, W, H, RGB(3, 6, 12));
		P.Text(W * 0.5f, 26, TEXT("IN MEMORIAM"), false, 96, TEXTC, 1);
		P.Text(W * 0.5f, 142, Ship && Ship->GetHullNumber() != TEXT("CVC-01")
			? FString::Printf(TEXT("ASN AQUILA  \u00B7  CVC-01 AND %s  \u00B7  THEY GAVE THEIR LIVES FOR THE AURELIA MARCH"), *Ship->GetHullNumber())
			: FString(TEXT("ASN AQUILA  \u00B7  CVC-01  \u00B7  THEY GAVE THEIR LIVES FOR THE AURELIA MARCH")), true, 22, DIM, 1);
		P.Line(W * 0.22f, 186, W * 0.78f, 186, DIM, 2.f);
		const FAstraCrewRoster& R = Ship->GetRoster();
		const TArray<int32>& Fallen = R.GetFallen();
		if (Fallen.Num() == 0)
		{
			P.Text(W * 0.5f, 300, TEXT("No one aboard has fallen."), false, 52, DIM, 1);
			return;
		}
		// three columns of names in the order they were lost; the department beside each
		constexpr int32 Cols = 3, Rows = 11;
		const float ColW = (W - 160.f) / Cols;
		for (int32 k = 0; k < FMath::Min(Fallen.Num(), Cols * Rows); ++k)
		{
			const FAstraCrewman& M = R.Get()[Fallen[k]];
			const float X = 80.f + (k / Rows) * ColW, Y = 206.f + (k % Rows) * 34.f;
			P.Text(X, Y, M.Name(), false, 29, TEXTC);
			P.Text(X + ColW - 30.f, Y + 7, M.Dept.ToUpper(), true, 14, DIM, 2);
		}
		if (Fallen.Num() > Cols * Rows)
		{
			P.Text(W * 0.5f, H - 34, FString::Printf(TEXT("AND %d MORE"), Fallen.Num() - Cols * Rows), true, 20, DIM, 1);
		}
		return;
	}
	// the fleet net: the March system by system (who holds it, how hard it is pressed), and the latest news
	P.Header(W, TEXT("Fleet News"), TEXT("7TH FLEET NET  \u00B7  AURELIA MARCH"), COMMAND);
	const TArray<FAstraSectorSystem>& Sector = Ship->GetSector();
	P.Panel(24, 64, 760, H - 24, TEXT("The March"));
	static const TCHAR* Threat[] = {TEXT("QUIET"), TEXT("RAIDS"), TEXT("UNDER ATTACK"), TEXT("FRONT LINE")};
	for (int32 i = 0; i < Sector.Num() && i < 11; ++i)
	{
		const FAstraSectorSystem& X = Sector[i];
		const float Y = 108.f + i * 42.f;
		const FLinearColor Own = X.Owner == TEXT("astra") ? CYAN : X.Owner == TEXT("mandate") ? RED
		                       : X.Owner == TEXT("guilds") ? AMBER : DIM;
		P.Rect(44, Y + 8, 14, 14, Own);
		P.Text(70, Y, X.Name.ToUpper(), false, 26, TEXTC);
		P.Text(330, Y + 6, X.Owner == TEXT("astra") ? TEXT("ASTRA") : X.Owner == TEXT("mandate") ? TEXT("MANDATE")
		                  : X.Owner == TEXT("guilds") ? TEXT("FREE GUILDS") : X.Owner.ToUpper(), true, 16, Own);
		P.Text(740, Y + 6, Threat[FMath::Clamp(X.Threat, 0, 3)], true, 16, X.Threat >= 2 ? RED : (X.Threat == 1 ? AMBER : DIM), 2);
		if (X.Name.Equals(Ship->GetSystemName(), ESearchCase::IgnoreCase))
		{
			P.Frame(38, Y - 2, 710, 38, CYAN, 2.f);
		}
	}
	if (Sector.Num() == 0)
	{
		P.Text(400, 300, TEXT("NO CONTACT WITH THE FLEET NET"), true, 20, DIM, 1);
	}
	P.Panel(800, 64, W - 24, H - 24, TEXT("Latest"));
	const TArray<FString>& News = Ship->GetSectorNews();
	float Y = 112.f;
	for (int32 k = News.Num() - 1; k >= 0 && Y < H - 80; --k)
	{
		// wrap each item to the panel (about 70 characters a line), newest first
		FString Left = News[k];
		bool bFirst = true;
		while (!Left.IsEmpty() && Y < H - 60)
		{
			int32 Cut = Left.Len() <= 72 ? Left.Len() : 72;
			if (Cut < Left.Len())
			{
				int32 Sp = INDEX_NONE;
				Left.Left(Cut).FindLastChar(TEXT(' '), Sp);
				Cut = Sp > 20 ? Sp : Cut;
			}
			P.Text(bFirst ? 824 : 846, Y, Left.Left(Cut).TrimStartAndEnd(), true, 19, bFirst ? TEXTC : DIM);
			Left = Left.Mid(Cut).TrimStartAndEnd();
			Y += 30.f;
			bFirst = false;
		}
		Y += 14.f;
	}
	if (News.Num() == 0)
	{
		P.Text(824, 112, TEXT("Nothing new on the net."), true, 19, DIM);
	}
}

void UAstraScreensSubsystem::DrawControls(UCanvas* C, int32 W, int32 H, const FString& Station)
{
	const UAstraStationsSubsystem* St = GetWorld()->GetSubsystem<UAstraStationsSubsystem>();
	const FAstraStation* S = St ? St->Find(Station) : nullptr;
	FPaint P{C, TitleFont, MonoFont, Time};
	P.Rect(0, 0, W, H, BG);
	if (!S)
	{
		return;
	}
	static const TMap<FString, FLinearColor> Accents = {{TEXT("helm"), COMMAND}, {TEXT("ops"), COMMAND}, {TEXT("comms"), COMMAND},
	                                                     {TEXT("sensors"), SCIENCE}, {TEXT("engineering"), ENGINEERING}, {TEXT("flight"), AMBER}};
	const FLinearColor Accent = Accents.Contains(Station) ? Accents[Station] : CYAN;
	const FLinearColor DelegCol = S->Delegation == TEXT("auto") ? GREEN : (S->Delegation == TEXT("advise") ? AMBER : RED);
	P.Header(W, FString::Printf(TEXT("%s · Control surface"), *Station), FString::Printf(TEXT("DELEGATION %s"), *S->Delegation.ToUpper()), Accent);
	P.Rect(W - 190, 50, 174, 26, DelegCol * 0.25f);
	P.Frame(W - 190, 50, 174, 26, DelegCol);
	P.Text(W - 103, 53, S->Delegation == TEXT("auto") ? TEXT("OFFICER IN CONTROL") : (S->Delegation == TEXT("advise") ? TEXT("ADVISING ONLY") : TEXT("MANUAL")),
	       true, 14, DelegCol, 1);
	const TArray<FString>& Aspects = UAstraStationsSubsystem::AspectsOf(Station);
	const float Top = 84.f, Bottom = H - 128.f;
	const float RowH = FMath::Min(150.f, (Bottom - Top) / FMath::Max(1, Aspects.Num()));
	const float Now = GetWorld()->GetTimeSeconds();
	for (int32 i = 0; i < Aspects.Num(); ++i)
	{
		const FString& Asp = Aspects[i];
		const FAstraStationAspect* A = S->Aspects.Find(Asp);
		const float Y = Top + i * RowH;
		P.Panel(16, Y, W - 16, Y + RowH - 8, Asp.Replace(TEXT("_"), TEXT(" ")));
		// the buttons: every mode the aspect offers, the one in force lit
		const TArray<FString>& Modes = UAstraStationsSubsystem::ModeChoices(Station, Asp);
		const int32 Rows = (Modes.Num() > 6 && RowH >= 140.f) ? 2 : 1;
		const int32 PerRow = FMath::Max(1, FMath::DivideAndRoundUp(Modes.Num(), Rows));
		const float BW = (W - 64.f - (PerRow - 1) * 8.f) / PerRow;
		const float BH = 28.f;
		int32 Longest = 1;
		for (const FString& Md : Modes) { Longest = FMath::Max(Longest, Md.Len()); }
		const float BPx = FMath::Clamp((BW - 10.f) / (Longest * 0.62f), 11.f, 15.f);
		for (int32 m = 0; m < Modes.Num(); ++m)
		{
			const float X = 32.f + (m % PerRow) * (BW + 8.f);
			const float BY = Y + 38.f + (m / PerRow) * (BH + 6.f);
			const bool bOn = A && A->Mode == Modes[m];
			P.Rect(X, BY, BW, BH, bOn ? Accent : RGB(8, 16, 30));
			P.Frame(X, BY, BW, BH, bOn ? TEXTC : DIM);
			P.Text(X + BW * 0.5f, BY + BH * 0.5f - BPx * 0.6f, Modes[m].Replace(TEXT("_"), TEXT(" ")).ToUpper(), true, BPx, bOn ? RGB(4, 9, 18) : LINE, 1, bOn);
		}
		if (A)
		{
			// what the mode is about, when it ends, who set it
			FString Detail;
			if (A->Params.IsValid())
			{
				for (const auto& KV : A->Params->Values)
				{
					FString V;
					if (KV.Value.IsValid() && KV.Value->TryGetString(V) && !V.IsEmpty())
					{
						Detail += FString::Printf(TEXT("%s %s  "), *FString(*KV.Key).Replace(TEXT("_"), TEXT(" ")), *V);
					}
					else if (double D = 0.0; KV.Value.IsValid() && KV.Value->TryGetNumber(D))
					{
						Detail += FString::Printf(TEXT("%s %g  "), *FString(*KV.Key).Replace(TEXT("_"), TEXT(" ")), D);
					}
				}
			}
			Detail += FString::Printf(TEXT("until %s · set by %s %.0f s ago"), *A->Until.Replace(TEXT("_"), TEXT(" ")), *A->SetBy, FMath::Max(0.f, Now - (float)A->Since));
			P.Text(W - 32, Y + RowH - 34, Detail.Left(int32((W - 64) / 8.4f)), true, 14, CYAN, 2);
		}
	}
	// the officer's own words for the station, and the last things done
	P.Panel(16, Bottom, W - 16, H - 12, TEXT("Officer"));
	P.Text(32, Bottom + 36, S->Status.Left(int32((W - 64) / 8.8f)), true, 15, TEXTC);
	for (int32 k = 0; k < 2 && k < S->Actions.Num(); ++k)
	{
		P.Text(32, Bottom + 60 + k * 22, (TEXT("› ") + S->Actions[S->Actions.Num() - 1 - k]).Left(int32((W - 64) / 8.4f)), true, 14, k == 0 ? CYAN : DIM);
	}
}

bool UAstraScreensSubsystem::DumpPage(const FString& Name, const FString& Path)
{
	for (UAstraScreenPage* P : Pages)
	{
		if (P && P->Name == Name && P->Target)
		{
			FTextureRenderTargetResource* R = P->Target->GameThread_GetRenderTargetResource();
			TArray<FColor> Px;
			if (!R || !R->ReadPixels(Px) || Px.Num() != P->Target->SizeX * P->Target->SizeY)
			{
				return false;
			}
			for (FColor& C : Px) { C.A = 255; }
			TArray64<uint8> Png;
			FImageUtils::PNGCompressImageArray(P->Target->SizeX, P->Target->SizeY, TArrayView64<const FColor>(Px.GetData(), Px.Num()), Png);
			return Png.Num() > 0 && FFileHelper::SaveArrayToFile(Png, *Path);
		}
	}
	return false;
}

// ------------------------------------------------------------------------------------------------ the datapad's pages
namespace
{
	const TArray<FString>& PadPages()
	{
		static const TArray<FString> P = {TEXT("overview"), TEXT("contact"), TEXT("damage"), TEXT("fleet"), TEXT("orders")};
		return P;
	}

	void PadHeader(const FPaint& P, float W, const FString& Hull, float Time, const FString& Title, const FLinearColor& Accent)
	{
		const float MX = 46.f, RX = W - 46.f;
		P.Rect(0, 0, W, 50, HEADER);
		P.Rect(MX - 14, 12, 6, 30, Accent);
		P.Text(MX, 12, Title, false, 26, TEXTC);
		P.Text(RX, 18, FString::Printf(TEXT("%s · %s"), *Hull, *ShipClock(Time).Right(13)), true, 15, CYAN, 2);
		P.Line(0, 50, W, 50, Accent, 2.f);
	}

	FLinearColor SideCol(EAstraSide S, int32 Track)
	{
		if (Track < 2) return TEXTC;
		return S == EAstraSide::Astra ? CYAN : (S == EAstraSide::Mandate ? RED : YELLOW);
	}

	/** What the ship's intelligence files say about a class (a line; the optical length is measured). */
	FString ClassNotes(const FString& Class)
	{
		static const TArray<TPair<FString, FString>> Notes = {
			{TEXT("cruiser"), TEXT("heavy guns, a deep missile magazine and a hangar of strike fighters; a command ship")},
			{TEXT("destroyer"), TEXT("spinal railgun and missiles; fast, hunts in groups of three")},
			{TEXT("frigate"), TEXT("light lasers and a few missiles; picket, escort and raider")},
			{TEXT("battleship"), TEXT("the line's anchor: the heaviest armour, guns and shields in the fleet")},
			{TEXT("freighter"), TEXT("unarmed merchant hull; under the Free Guilds' flag")},
			{TEXT("fighter"), TEXT("strike craft: cannons and anti-ship missiles")},
		};
		for (const TPair<FString, FString>& N : Notes)
		{
			if (Class.Contains(N.Key, ESearchCase::IgnoreCase))
			{
				return N.Value;
			}
		}
		return Class.IsEmpty() ? TEXT("not classified yet: a closer look or an active scan will tell") : TEXT("no intelligence on file");
	}
}

bool UAstraScreensSubsystem::PushPad(const FString& Page, const FString& Focus, const FString& By)
{
	const FString Pg = Page.ToLower();
	if (!PadPages().Contains(Pg))
	{
		return false;
	}
	PadPage = Pg;
	PadFocus = Focus.ToUpper();
	PadPushedBy = By;
	PadPushedAt = Time;
	RedrawPadNow();
	static const TMap<FString, FString> Names = {{TEXT("overview"), TEXT("THE SHIP AT A GLANCE")}, {TEXT("contact"), TEXT("CONTACT DOSSIER")},
	                                             {TEXT("damage"), TEXT("DAMAGE REPORT")}, {TEXT("fleet"), TEXT("THE FLEET")}, {TEXT("orders"), TEXT("ORDERS IN FORCE")}};
	if (AASTRAPlayerController* PC = Cast<AASTRAPlayerController>(GetWorld()->GetFirstPlayerController()))
	{
		PC->ShowNotice(FString::Printf(TEXT("%s  ›  DATAPAD:  %s%s   ·   Tab"), *By.ToUpper(), *Names[Pg], PadFocus.IsEmpty() ? TEXT("") : *FString::Printf(TEXT(" %s"), *PadFocus)), 8.f);
		if (USoundBase* S = LoadObject<USoundBase>(nullptr, TEXT("/Game/ASTRA/Audio/SW_Pad_Up.SW_Pad_Up")))
		{
			UGameplayStatics::PlaySound2D(this, S, 0.35f, 1.4f);
		}
	}
	return true;
}

void UAstraScreensSubsystem::CyclePad(int32 Dir)
{
	const int32 I = PadPages().IndexOfByKey(PadPage);
	PadPage = PadPages()[(FMath::Max(0, I) + Dir + PadPages().Num()) % PadPages().Num()];
	PadPushedAt = -100.f;
	RedrawPadNow();
}

void UAstraScreensSubsystem::RedrawPadNow()
{
	for (UAstraScreenPage* P : Pages)
	{
		if (P && P->Name == TEXT("Pad"))
		{
			P->Wait = -10.f;     // the most overdue page: painted on the next frame
		}
	}
}

void UAstraScreensSubsystem::DrawPad(UCanvas* C, int32 W, int32 H)
{
	if (PadPage == TEXT("contact")) { DrawPadContact(C, W, H); }
	else if (PadPage == TEXT("damage")) { DrawPadDamage(C, W, H); }
	else if (PadPage == TEXT("fleet")) { DrawPadFleet(C, W, H); }
	else if (PadPage == TEXT("orders")) { DrawPadOrders(C, W, H); }
	else { DrawPadOverview(C, W, H); }
	DrawPadTabs(C, W, H);
}

void UAstraScreensSubsystem::DrawPadTabs(UCanvas* C, int32 W, int32 H)
{
	FPaint P{C, TitleFont, MonoFont, Time};
	const float MX = 46.f;
	P.Rect(0, H - 30, W, 30, HEADER);
	float X = MX;
	for (const FString& Pg : PadPages())
	{
		const bool bOn = Pg == PadPage;
		const FString L = Pg.ToUpper();
		const float Wd = L.Len() * 9.2f + 18.f;
		if (bOn)
		{
			P.Rect(X - 9, H - 28, Wd, 26, COMMAND);
		}
		P.Text(X, H - 26, L, true, 15, bOn ? TEXTC : DIM, 0, bOn);
		X += Wd + 8.f;
	}
	const bool bPushed = Time - PadPushedAt < 20.f;
	P.Text(W - MX, H - 26, bPushed ? FString::Printf(TEXT("SENT BY %s"), *PadPushedBy.ToUpper()) : FString(TEXT("WHEEL  PAGES  ·  TAB  LOWER")), true, 14,
	       bPushed ? AMBER : RGB(120, 160, 205), 2);
}

void UAstraScreensSubsystem::DrawPadContact(UCanvas* C, int32 W, int32 H)
{
	const UAstraShipSubsystem* Ship = GetWorld()->GetSubsystem<UAstraShipSubsystem>();
	const UAstraBattleSubsystem* Battle = GetWorld()->GetSubsystem<UAstraBattleSubsystem>();
	const UAstraStationsSubsystem* St = GetWorld()->GetSubsystem<UAstraStationsSubsystem>();
	if (!Ship || !Battle)
	{
		return;
	}
	FPaint P{C, TitleFont, MonoFont, Time};
	P.Rect(0, 0, W, H, BG);
	PadHeader(P, W, Ship->GetHullNumber(), Time, TEXT("CONTACT DOSSIER"), RED);
	const float MX = 46.f, RX = W - 46.f;
	const TArray<UAstraBattleSubsystem::FContactView>& Cs = Battle->Contacts();
	// the pushed contact, else what the fight is about, else the nearest warship
	FString Id = PadFocus.IsEmpty() && St ? St->ActionTarget() : PadFocus;
	const UAstraBattleSubsystem::FContactView* Ct = Cs.FindByPredicate([&Id](const UAstraBattleSubsystem::FContactView& X)
	{
		return !Id.IsEmpty() && (X.ContactId.Equals(Id, ESearchCase::IgnoreCase) || X.Label.Contains(Id, ESearchCase::IgnoreCase));
	});
	if (!Ct)
	{
		Ct = Cs.FindByPredicate([](const UAstraBattleSubsystem::FContactView& X) { return !X.bCraft; });
	}
	if (!Ct)
	{
		P.Text(MX, 90, Id.IsEmpty() ? FString(TEXT("NO CONTACTS ON THE PLOT")) : FString::Printf(TEXT("%s IS NOT ON THE PLOT"), *Id), true, 20, TEXTC);
		return;
	}
	const FLinearColor Col = SideCol(Ct->Side, Ct->Track);
	const FString SideText = Ct->Track < 2 ? TEXT("PASSIVE BEARING · IFF UNKNOWN") : (Ct->Side == EAstraSide::Astra ? TEXT("FRIENDLY · ASTRA")
	                        : (Ct->Side == EAstraSide::Mandate ? TEXT("HOSTILE · KHARON MANDATE") : TEXT("NEUTRAL")));
	P.Text(MX, 60, Ct->Label.ToUpper(), false, 48, Col);
	P.Text(MX, 116, FString::Printf(TEXT("%s  ·  %s"), *Ct->ContactId, Ct->Class.IsEmpty() ? TEXT("UNCLASSIFIED") : *Ct->Class.ToUpper()), true, 18, TEXTC);
	P.Text(RX, 70, SideText, true, 17, Col, 2);
	P.Text(RX, 94, Ct->Track >= 2 ? TEXT("FIRM TRACK") : TEXT("BEARING ONLY"), true, 15, Ct->Track >= 2 ? GREEN : AMBER, 2);
	// where and how it moves
	P.Panel(MX - 10, 150, W * 0.5f - 10, 420, TEXT("Track"));
	const double Brg = Ct->BearingDeg, Mk = Ct->MarkDeg;
	float Y = 190.f;
	auto Row = [&](const FString& K, const FString& V, const FLinearColor& VC)
	{
		P.Text(MX + 6, Y, K, false, 18, CYAN);
		P.Text(W * 0.5f - 26, Y, V, true, 20, VC, 2);
		Y += 38.f;
	};
	Row(TEXT("RANGE"), Ct->RangeKm >= 0.0 ? FString::Printf(TEXT("%.1f KM"), Ct->RangeKm) : FString(TEXT("UNKNOWN")), TEXTC);
	Row(TEXT("BEARING"), FString::Printf(TEXT("%03.0f  MARK %+.0f"), Brg, Mk), TEXTC);
	if (Ct->Track >= 2)
	{
		const FVector Rel = Ct->Pos - Battle->PlayerPos();
		const double Rate = FVector::DotProduct(Ct->Vel - Battle->PlayerVel(), Rel.GetSafeNormal());
		Row(TEXT("SPEED"), FString::Printf(TEXT("%.0f M/S"), Ct->Vel.Size()), TEXTC);
		Row(Rate < 0.0 ? TEXT("CLOSING") : TEXT("OPENING"), FString::Printf(TEXT("%.0f M/S"), FMath::Abs(Rate)), Rate < -150.0 ? AMBER : TEXTC);
		if (Rate < -1.0 && Ct->RangeKm > 0.0)
		{
			const double Eta = Ct->RangeKm * 1000.0 / -Rate;
			Row(TEXT("AT 5 KM IN"), Eta > 600.0 ? FString(TEXT("OVER 10 MIN")) : FString::Printf(TEXT("%d:%02d"), int32(Eta) / 60, int32(Eta) % 60), TEXTC);
		}
	}
	// its state, as far as we know it
	P.Panel(W * 0.5f + 10, 150, RX + 10, 420, TEXT("State"));
	const float SX = W * 0.5f + 28, SW = RX - SX - 8;
	if (Ct->HullFrac >= 0.f)
	{
		P.Bar(SX, 188, SW, 14, Ct->HullFrac, TEXT("Hull"), FString::Printf(TEXT("%.0f %%"), 100.f * Ct->HullFrac), Level(Ct->HullFrac));
		P.Bar(SX, 246, SW, 14, FMath::Max(0.f, Ct->ShieldFrac), TEXT("Shields"), FString::Printf(TEXT("%.0f %%"), 100.f * FMath::Max(0.f, Ct->ShieldFrac)), CYAN);
	}
	else
	{
		P.Text(SX, 190, TEXT("DAMAGE STATE UNKNOWN"), true, 17, RGB(120, 160, 205));
	}
	float TY = 310.f;
	auto Flag = [&](bool b, const TCHAR* T, const FLinearColor& FC)
	{
		if (b)
		{
			P.Rect(SX, TY, SW, 28, FC * 0.22f);
			P.Text(SX + 10, TY + 3, T, true, 17, FC);
			TY += 34.f;
		}
	};
	Flag(Ct->bFiringAtUs, TEXT("FIRING ON THE AQUILA"), RED);
	Flag(St && St->ActionTarget() == Ct->ContactId, TEXT("OUR FIRE CONTROL IS ON IT"), AMBER);
	Flag(Ct->bFleeing, TEXT("WITHDRAWING"), GREEN);
	Flag(Ct->bJamming, TEXT("JAMMING OUR SENSORS"), AMBER);
	Flag(Ct->bDerelict, TEXT("DERELICT · NO DRIVE"), RGB(120, 160, 205));
	// what the files say
	P.Line(MX, 440, RX, 440, DIM);
	P.Text(MX, 450, TEXT("INTELLIGENCE"), false, 18, CYAN);
	FString Len;
	if (Ct->Actor)
	{
		if (const UStaticMeshComponent* M = Ct->Actor->GetStaticMeshComponent(); M && M->GetStaticMesh())
		{
			Len = FString::Printf(TEXT("LENGTH %.0f M (OPTICAL)  ·  "), M->GetStaticMesh()->GetBoundingBox().GetSize().GetMax() * M->GetComponentScale().GetMax() / 100.f);
		}
	}
	int32 L = 0;
	for (const FString& Seg : Wrap(Len + ClassNotes(Ct->Class).ToUpper(), 86))
	{
		P.Text(MX, 478 + 22 * L++, Seg, true, 15, TEXTC);
	}
}

void UAstraScreensSubsystem::DrawPadDamage(UCanvas* C, int32 W, int32 H)
{
	const UAstraShipSubsystem* Ship = GetWorld()->GetSubsystem<UAstraShipSubsystem>();
	const UAstraBattleSubsystem* Battle = GetWorld()->GetSubsystem<UAstraBattleSubsystem>();
	if (!Ship)
	{
		return;
	}
	FPaint P{C, TitleFont, MonoFont, Time};
	P.Rect(0, 0, W, H, BG);
	PadHeader(P, W, Ship->GetHullNumber(), Time, TEXT("DAMAGE REPORT"), AMBER);
	const float MX = 46.f, RX = W - 46.f;
	const float Sh = Battle ? Battle->PlayerShieldFraction() : 1.f, Hu = Battle ? Battle->PlayerHullFraction() : 1.f, He = Ship->GetHeatPct() / 100.f;
	const float BW = (RX - MX - 40) / 3.f;
	P.Bar(MX, 62, BW, 16, Hu, TEXT("Hull"), FString::Printf(TEXT("%.0f %%"), 100.f * Hu), Level(Hu));
	P.Bar(MX + BW + 20, 62, BW, 16, Sh, TEXT("Shields"), FString::Printf(TEXT("%.0f %%"), 100.f * Sh), Level(Sh));
	P.Bar(MX + 2 * (BW + 20), 62, BW, 16, FMath::Clamp(He, 0.f, 1.f), TEXT("Heat"), FString::Printf(TEXT("%.0f %%"), 100.f * He), He > 0.9f ? RED : (He > 0.7f ? AMBER : CYAN));
	const TArray<FAstraDamage>& Dmg = Ship->GetDamage();
	const FAstraDamageModel* Interior = Ship->GetInterior().IsReady() ? &Ship->GetInterior() : nullptr;
	int32 Busy = 0;
	for (const FAstraDamage& D : Dmg) { Busy += D.Team >= 0 ? 1 : 0; }
	// the ship in cutaway, as on the holo table: a row per deck (the bridge on its island), sections A-H, the damage where it is
	float ListTop = 160.f;
	const UAstraShipPlan* Plan = GetWorld()->GetSubsystem<UAstraShipPlan>();
	if (Plan && Plan->GetDecks().Num() > 0)
	{
		const TArray<FAstraPlanDeck>& Decks = Plan->GetDecks();
		float X0 = 1e9f, X1 = -1e9f;
		for (const FAstraPlanDeck& D : Decks)
		{
			for (const FAstraPlanDeck::FSection& Se : D.Sections) { X0 = FMath::Min(X0, Se.X0); X1 = FMath::Max(X1, Se.X1); }
		}
		const float CL = MX + 34.f, CR = RX - 6.f, CT = 112.f, Row = 10.f;   // the bow to the right
		const float Sx = (CR - CL) / FMath::Max(1.f, X1 - X0);
		auto RowY = [&](int32 Deck) { return CT + Row * (Deck == 1 ? 0.f : Deck - 0.f); };   // the bridge a row above Deck 2
		auto PX = [&](float X) { return CL + (X - X0) * Sx; };
		const float Pulse = 0.55f + 0.45f * FMath::Sin(Time * 6.f);
		for (const FAstraPlanDeck& D : Decks)
		{
			const float Y = RowY(D.Id);
			P.Text(MX, Y - 2.f, D.Id == 1 ? FString(TEXT("BRG")) : FString::Printf(TEXT("%2d"), D.Id), true, 11, DIM);
			for (const FAstraPlanDeck::FSection& Se : D.Sections)
			{
				if (Se.Id.IsEmpty())
				{
					continue;
				}
				int32 Worst = 0;
				FLinearColor Col = CYAN * 0.32f;
				for (const FAstraDamage& X : Dmg)
				{
					const int32 Sev = X.Kind.Contains(TEXT("breach")) ? 3 : (X.Kind.Contains(TEXT("fire")) ? 2 : 1);
					if (X.Deck == D.Id && X.Section == Se.Id[0] && Sev > Worst)
					{
						Worst = Sev;
						// the section is washed in the colour; the compartment itself, drawn below, is the bright one (an incident the plan has no compartment for is the section's)
						Col = (Sev == 3 ? RED : (Sev == 2 ? AMBER : YELLOW)) * (Interior && Interior->GetMap().Comps.IsValidIndex(X.Comp) ? 0.4f : Pulse);
					}
				}
				Col.A = 1.f;
				P.Rect(PX(Se.X0) + 1.f, Y, FMath::Max(1.f, (Se.X1 - Se.X0) * Sx - 2.f), Row - 3.f, Col);
			}
		}
		if (const FAstraPlanDeck* Top = Decks.FindByPredicate([](const FAstraPlanDeck& X) { return X.Id == 2; }))
		{
			for (const FAstraPlanDeck::FSection& Se : Top->Sections)
			{
				P.Text(PX(0.5f * (Se.X0 + Se.X1)) - 4.f, CT - 1.f + Row * 0.f - 12.f, Se.Id, true, 11, DIM);
			}
		}
		// the compartments that are hurt, where they are along their deck's row, and the pressure bulkheads that are shut
		if (Interior)
		{
			for (const FAstraDamage& X : Dmg)
			{
				if (!Interior->GetMap().Comps.IsValidIndex(X.Comp))
				{
					continue;
				}
				const FBox& Box = Interior->GetMap().Comps[X.Comp].Box;
				const int32 Sev = X.Kind.Contains(TEXT("breach")) ? 3 : (X.Kind.Contains(TEXT("fire")) ? 2 : 1);
				FLinearColor Col = (Sev == 3 ? RED : (Sev == 2 ? AMBER : YELLOW)) * Pulse;
				Col.A = 1.f;
				P.Rect(PX(Box.Min.X), RowY(X.Deck) - 1.f, FMath::Max(3.f, (Box.Max.X - Box.Min.X) * Sx), Row - 1.f, Col);
			}
			for (const int32 DoorIndex : Interior->SealedDoors())
			{
				const FAstraDmgDoor& Door = Interior->GetMap().Doors[DoorIndex];
				P.Rect(PX(Door.PosCm.X) - 1.f, RowY(Door.Deck) - 2.f, 2.f, Row + 1.f, TEXTC);
			}
		}
		// the damage-control teams (from their station on Deck 6) and the Captain
		auto SecX = [&](int32 Deck, TCHAR Sec, float& Out)
		{
			const FAstraPlanDeck* D = Decks.FindByPredicate([Deck](const FAstraPlanDeck& X) { return X.Id == Deck; });
			const FAstraPlanDeck::FSection* Se = D ? D->Sections.FindByPredicate([Sec](const FAstraPlanDeck::FSection& X) { return X.Id.Len() > 0 && X.Id[0] == Sec; }) : nullptr;
			if (Se) { Out = PX(0.5f * (Se->X0 + Se->X1)); }
			return Se != nullptr;
		};
		float StX = 0.f;
		const bool bSt = SecX(6, TEXT('D'), StX);
		for (const FAstraDamage& X : Dmg)
		{
			float IX = 0.f;
			if (X.Team < 0 || !bSt || !SecX(X.Deck, X.Section, IX))
			{
				continue;
			}
			const float K = X.Travel0 > 0.f ? FMath::Clamp(1.f - X.Travel / X.Travel0, 0.f, 1.f) : 1.f;
			const float TX = FMath::Lerp(StX, IX, K), TY = FMath::Lerp(RowY(6), RowY(X.Deck), K) + 1.5f;
			P.Rect(TX - 2.5f, TY, 5.f, 5.f, TEXTC);
		}
		if (const APawn* Pawn = UGameplayStatics::GetPlayerPawn(this, 0))
		{
			const FVector L = Pawn->GetActorLocation();
			const int32 Deck = Plan->DeckAt(L);
			if (Deck > 0)
			{
				const float CX = PX(L.X), CY = RowY(Deck);
				P.Frame(CX - 4.f, CY - 2.f, 8.f, Row + 1.f, GREEN, 2.f);
				P.Text(CX + 7.f, CY - 3.f, TEXT("YOU"), true, 11, GREEN);
			}
		}
		ListTop = CT + Row * 13.f + 50.f;
	}
	P.Line(MX, ListTop - 40.f, RX, ListTop - 40.f, DIM);
	P.Text(MX, ListTop - 32.f, TEXT("INCIDENTS"), false, 18, CYAN);
	P.Text(RX, ListTop - 30.f, FString::Printf(TEXT("%d OPEN  ·  %d OF %d DAMAGE-CONTROL TEAMS OUT"), Dmg.Num(), Busy, Ship->GetNumDamageTeams()), true, 16, Dmg.Num() ? AMBER : GREEN, 2);
	if (Interior)
	{
		// what the ship has done about it: the section bulkheads shut and the containment fields on the breaches
		const int32 Sealed = Interior->SealedDoors().Num(), Fields = Interior->Power().Fields;
		if (Sealed > 0 || Fields > 0)
		{
			P.Text(MX + 130.f, ListTop - 28.f, FString::Printf(TEXT("%d BULKHEAD%s SEALED · %d FIELD%s"), Sealed, Sealed == 1 ? TEXT("") : TEXT("S"), Fields, Fields == 1 ? TEXT("") : TEXT("S")), true, 14, CYAN);
		}
	}
	if (Dmg.Num() == 0)
	{
		P.Text(MX, ListTop + 2.f, TEXT("NONE  ·  ALL DECKS PRESSURIZED"), true, 18, GREEN);
	}
	TArray<const FAstraDamage*> Sorted;
	for (const FAstraDamage& D : Dmg)
	{
		Sorted.Add(&D);
	}
	Sorted.StableSort([](const FAstraDamage& A, const FAstraDamage& B) { return IncidentRank(A) > IncidentRank(B); });
	const int32 MaxRows = FMath::Max(3, FMath::FloorToInt((490.f - ListTop) / 27.f));
	for (int32 i = 0; i < FMath::Min(Sorted.Num(), MaxRows); ++i)
	{
		const FAstraDamage& D = *Sorted[i];
		const float Y = ListTop + i * 27.f;
		const FLinearColor KC = D.Kind.Contains(TEXT("breach")) ? RED : (D.Kind.Contains(TEXT("fire")) ? AMBER : YELLOW);
		P.Text(MX, Y, FString::Printf(TEXT("D%-2d %c  %s"), D.Deck, D.Section, *D.Place.ToUpper().Left(18)), true, 17, TEXTC);
		P.Text(MX + 270, Y, KindShort(D.Kind), true, 17, KC);
		// how it stands: the field on the hole and the air that is left, the fire and the smoke, the power a conduit's room has and what runs through it
		const FString Detail = (D.System.IsEmpty() ? FString() : D.System + TEXT(" · ")) + D.Note;
		if (!Detail.IsEmpty())
		{
			P.Text(MX + 385, Y + 3, Detail.ToUpper().Left(40), true, 13, DIM);
		}
		const FString Team = D.Team < 0 ? FString(TEXT("UNATTENDED")) : (D.Travel > 0.f ? FString::Printf(TEXT("TEAM %d  EN ROUTE %.0f S"), D.Team + 1, D.Travel)
		                                                                              : FString::Printf(TEXT("TEAM %d  %.0f %%"), D.Team + 1, 100.f * D.Progress));
		P.Text(RX, Y, Team, true, 15, D.Team < 0 ? RED : (D.Travel > 0.f ? AMBER : GREEN), 2);
	}
	if (Sorted.Num() > MaxRows)
	{
		P.Text(RX, ListTop + MaxRows * 27, FString::Printf(TEXT("+%d MORE"), Sorted.Num() - MaxRows), true, 14, DIM, 2);
	}
	P.Line(MX, 500, RX, 500, DIM);
	P.Text(MX, 508, TEXT("CASUALTIES"), false, 18, CYAN);
	int32 L = 0;
	for (const FString& Seg : Wrap(Ship->GetRoster().Summary().ToUpper(), 86))
	{
		if (L < 3)
		{
			P.Text(MX, 536 + 22 * L++, Seg, true, 15, TEXTC);
		}
	}
}

void UAstraScreensSubsystem::DrawPadFleet(UCanvas* C, int32 W, int32 H)
{
	const UAstraShipSubsystem* Ship = GetWorld()->GetSubsystem<UAstraShipSubsystem>();
	const UAstraBattleSubsystem* Battle = GetWorld()->GetSubsystem<UAstraBattleSubsystem>();
	if (!Ship || !Battle)
	{
		return;
	}
	FPaint P{C, TitleFont, MonoFont, Time};
	P.Rect(0, 0, W, H, BG);
	PadHeader(P, W, Ship->GetHullNumber(), Time, TEXT("THE FLEET"), CYAN);
	const float MX = 46.f, RX = W - 46.f;
	const TArray<UAstraBattleSubsystem::FContactView>& Cs = Battle->Contacts();
	P.Text(MX, 60, TEXT("7TH FLEET · SHIPS IN COMPANY"), false, 18, CYAN);
	float Y = 90.f;
	int32 Hostile = 0, HostileCraft = 0, OurCraft = 0;
	for (const UAstraBattleSubsystem::FContactView& Ct : Cs)
	{
		if (Ct.Side == EAstraSide::Mandate) { (Ct.bCraft ? HostileCraft : Hostile)++; }
		if (Ct.Side == EAstraSide::Astra && Ct.bCraft) { ++OurCraft; }
		if (Ct.Side != EAstraSide::Astra || Ct.bCraft || Y > 330.f)
		{
			continue;
		}
		P.Text(MX, Y, Ct.Label.ToUpper().Left(26), true, 17, CYAN, 0, true);
		P.Text(MX + 300, Y, Ct.Class.Left(30), true, 15, TEXTC);
		P.Text(RX - 250, Y, Ct.RangeKm >= 0.0 ? FString::Printf(TEXT("%.1f KM"), Ct.RangeKm) : FString(TEXT("-")), true, 16, TEXTC, 2);
		if (Ct.HullFrac >= 0.f)
		{
			P.Rect(RX - 220, Y + 6, 100, 8, RGB(6, 12, 24));
			P.Rect(RX - 220, Y + 6, 100 * Ct.HullFrac, 8, Level(Ct.HullFrac));
			P.Rect(RX - 100, Y + 6, 100, 8, RGB(6, 12, 24));
			P.Rect(RX - 100, Y + 6, 100 * FMath::Max(0.f, Ct.ShieldFrac), 8, CYAN);
		}
		Y += 28.f;
	}
	P.Text(RX - 220, 62, TEXT("HULL"), true, 13, DIM);
	P.Text(RX - 100, 62, TEXT("SHIELDS"), true, 13, DIM);
	P.Line(MX, 350, RX, 350, DIM);
	P.Text(MX, 358, TEXT("AQUILA AIR GROUP"), false, 18, CYAN);
	float QY = 388.f;
	const TSharedRef<FJsonObject> Sq = Battle->SquadronsJson();
	for (const auto& KV : Sq->Values)
	{
		FString V;
		if (!KV.Value.IsValid() || !KV.Value->TryGetString(V))
		{
			continue;
		}
		P.Text(MX, QY, FString(*KV.Key).ToUpper(), true, 17, TEXTC, 0, true);
		P.Text(MX + 120, QY, V.ToUpper().Left(80), true, 15, TEXTC);
		QY += 26.f;
	}
	P.Line(MX, 480, RX, 480, DIM);
	P.Text(MX, 488, TEXT("THE ENEMY"), false, 18, RED);
	P.Text(MX, 516, Hostile + HostileCraft ? FString::Printf(TEXT("%d WARSHIP%s  ·  %d SMALL CRAFT ON THE PLOT"), Hostile, Hostile == 1 ? TEXT("") : TEXT("S"), HostileCraft)
	                                        : FString(TEXT("NONE ON THE PLOT")), true, 17, Hostile ? RED : GREEN);
	P.Text(MX, 542, FString::Printf(TEXT("OUR CRAFT IN FLIGHT: %d"), OurCraft), true, 15, TEXTC);
}

void UAstraScreensSubsystem::DrawPadOrders(UCanvas* C, int32 W, int32 H)
{
	const UAstraShipSubsystem* Ship = GetWorld()->GetSubsystem<UAstraShipSubsystem>();
	const UAstraStationsSubsystem* St = GetWorld()->GetSubsystem<UAstraStationsSubsystem>();
	if (!Ship || !St)
	{
		return;
	}
	FPaint P{C, TitleFont, MonoFont, Time};
	P.Rect(0, 0, W, H, BG);
	PadHeader(P, W, Ship->GetHullNumber(), Time, TEXT("ORDERS IN FORCE"), COMMAND);
	const float MX = 46.f, RX = W - 46.f;
	float Y = 62.f;
	static const TCHAR* Order[] = {TEXT("helm"), TEXT("tactical"), TEXT("sensors"), TEXT("ops"), TEXT("engineering"), TEXT("comms"), TEXT("flight")};
	for (const TCHAR* Id : Order)
	{
		const FAstraStation* S = St->Find(Id);
		if (!S)
		{
			continue;
		}
		FString Line;
		for (const FString& Asp : UAstraStationsSubsystem::AspectsOf(Id))
		{
			if (const FAstraStationAspect* A = S->Aspects.Find(Asp))
			{
				FString T;
				if (A->Params.IsValid() && (A->Params->TryGetStringField(TEXT("target"), T) || A->Params->TryGetStringField(TEXT("contact_id"), T)))
				{
					T = TEXT(" ") + T;
				}
				Line += FString::Printf(TEXT("%s %s%s  ·  "), *Asp.Replace(TEXT("_"), TEXT(" ")), *A->Mode.Replace(TEXT("_"), TEXT(" ")), *T);
			}
		}
		Line.RemoveFromEnd(TEXT("  ·  "));
		P.Text(MX, Y, FString(Id).ToUpper(), false, 19, CYAN);
		P.Text(RX, Y + 2, S->Delegation.ToUpper(), true, 13, S->Delegation == TEXT("auto") ? GREEN : AMBER, 2);
		int32 L = 0;
		for (const FString& Seg : Wrap(Line.ToUpper(), 76))
		{
			if (L < 2)
			{
				P.Text(MX + 150, Y + 2 + 20 * L++, Seg, true, 14, TEXTC);
			}
		}
		Y += FMath::Max(1, L) * 20.f + 12.f;
	}
	P.Line(MX, Y + 4, RX, Y + 4, DIM);
	P.Text(MX, Y + 12, TEXT("THE CAPTAIN'S STANDING ORDERS"), false, 18, CYAN);
	const TArray<FString>& Orders = Ship->GetStandingOrders();
	if (Orders.Num() == 0)
	{
		P.Text(MX, Y + 40, TEXT("NONE IN FORCE"), true, 16, RGB(120, 160, 205));
	}
	for (int32 i = 0; i < FMath::Min(Orders.Num(), 4); ++i)
	{
		P.Text(MX, Y + 40 + i * 22, (TEXT("· ") + Orders[Orders.Num() - 1 - i]).Left(96), true, 15, TEXTC);
	}
}

void UAstraScreensSubsystem::DrawComms(UCanvas* C, int32 W, int32 H, const FString& Slot)
{
	const UAstraShipSubsystem* Ship = GetWorld()->GetSubsystem<UAstraShipSubsystem>();
	const UAstraMindSubsystem* Mind = GetWorld()->GetGameInstance() ? GetWorld()->GetGameInstance()->GetSubsystem<UAstraMindSubsystem>() : nullptr;
	if (!Ship)
	{
		return;
	}
	FPaint P{C, TitleFont, MonoFont, Time};
	P.Rect(0, 0, W, H, BG);
	const FString Party = Ship->GetChannelParty();
	P.Header(W, Slot == TEXT("A") ? TEXT("Communications · Traffic") : TEXT("Communications · Channel"),
	         Party.IsEmpty() ? FString(TEXT("NO CHANNEL OPEN")) : FString::Printf(TEXT("CHANNEL OPEN · %s"), *Party.ToUpper()), COMMAND);
	if (Slot == TEXT("B"))
	{
		// the channel: who is on it, and a live waveform while it is open
		P.Panel(20, 60, W - 20, 250, TEXT("Channel"));
		P.Text(40, 100, Party.IsEmpty() ? FString(TEXT("STANDING BY")) : Party.ToUpper(), false, 54, Party.IsEmpty() ? DIM : AMBER);
		P.Text(40, 170, Party.IsEmpty() ? FString(TEXT("FLEET NET MONITORED · ALL FREQUENCIES")) : FString(TEXT("OPEN · TWO-WAY · ENCRYPTED")), true, 18, CYAN);
		const float Base = 330.f;
		P.Panel(20, 270, W - 20, H - 20, TEXT("Signal"));
		FVector2D Prev(40.f, Base + 60.f);
		for (int32 x = 0; x <= 120; ++x)
		{
			const float T = Time * 3.f + x * 0.21f;
			const float A = Party.IsEmpty() ? 4.f : 38.f * (0.4f + 0.6f * FMath::Abs(FMath::Sin(Time * 1.7f + x * 0.05f)));
			const FVector2D Q(40.f + (W - 80.f) * x / 120.f, Base + 60.f + A * FMath::Sin(T) * FMath::Sin(T * 0.37f + 1.f));
			P.Line(Prev.X, Prev.Y, Q.X, Q.Y, Party.IsEmpty() ? DIM : CYAN, 2.f);
			Prev = Q;
		}
		return;
	}
	// A: the traffic heard, newest at the bottom; then the ship's recent events
	P.Panel(20, 60, W - 20, H * 0.62f, TEXT("Heard"));
	TArray<TPair<FString, FString>> Lines;
	if (Mind)
	{
		const TArray<TPair<FString, FString>>& Heard = Mind->GetHeardLines();
		for (int32 i = FMath::Max(0, Heard.Num() - 7); i < Heard.Num(); ++i)
		{
			Lines.Add(Heard[i]);
		}
	}
	float Y = 100.f;
	for (const TPair<FString, FString>& L : Lines)
	{
		FString Who = L.Key;
		int32 Paren = INDEX_NONE;
		if (Who.FindChar(TEXT('('), Paren))
		{
			Who = Who.Left(Paren).TrimEnd();
		}
		P.Text(40, Y, Who.ToUpper().Left(28), true, 15, CYAN);
		int32 k = 0;
		for (const FString& Seg : Wrap(L.Value, 66))
		{
			if (k++ < 2)
			{
				P.Text(300, Y, Seg, true, 15, TEXTC);
				Y += 20.f;
			}
		}
		Y += 6.f;
		if (Y > H * 0.62f - 24.f)
		{
			break;
		}
	}
	if (Lines.Num() == 0)
	{
		P.Text(40, 100, TEXT("QUIET ON ALL CHANNELS"), true, 16, DIM);
	}
	P.Panel(20, H * 0.62f + 16.f, W - 20, H - 20, TEXT("Log"));
	const TArray<FString>& Ev = Ship->GetRecentEvents();
	float EY = H * 0.62f + 56.f;
	for (int32 i = FMath::Max(0, Ev.Num() - 5); i < Ev.Num(); ++i)
	{
		P.Text(40, EY, Ev[i].Left(110), true, 14, i == Ev.Num() - 1 ? TEXTC : DIM);
		EY += 20.f;
	}
}

void UAstraScreensSubsystem::DrawFlight(UCanvas* C, int32 W, int32 H, const FString& Slot)
{
	const UAstraShipSubsystem* Ship = GetWorld()->GetSubsystem<UAstraShipSubsystem>();
	const UAstraBattleSubsystem* Battle = GetWorld()->GetSubsystem<UAstraBattleSubsystem>();
	if (!Ship || !Battle)
	{
		return;
	}
	FPaint P{C, TitleFont, MonoFont, Time};
	P.Rect(0, 0, W, H, BG);
	P.Header(W, Slot == TEXT("A") ? TEXT("Flight Operations · Air Group") : TEXT("Flight Operations · In Flight"), TEXT("CAG · DECK 9"), AMBER);
	const TArray<UAstraBattleSubsystem::FContactView>& Cs = Battle->Contacts();
	int32 Ours = 0, Theirs = 0;
	for (const UAstraBattleSubsystem::FContactView& Ct : Cs)
	{
		Ours += (Ct.bCraft && Ct.Side == EAstraSide::Astra) ? 1 : 0;
		Theirs += (Ct.bCraft && Ct.Side == EAstraSide::Mandate) ? 1 : 0;
	}
	if (Slot == TEXT("A"))
	{
		// the three groups: what each is doing, one panel each
		float Y = 60.f;
		const float PH = (H - 80.f) / 3.f;
		// the battle's own state of each group (the ship's table only holds the start of the campaign)
		TArray<TPair<FString, FString>> Groups;
		const TSharedRef<FJsonObject> Sq = Battle->SquadronsJson();   // held: a temporary's Values would dangle in the loop
		for (const auto& KV : Sq->Values)
		{
			FString V;
			if (KV.Value.IsValid() && KV.Value->TryGetString(V))
			{
				Groups.Add({FString(*KV.Key), V});
			}
		}
		for (const TPair<FString, FString>& KV : Groups)
		{
			P.Panel(20, Y, W - 20, Y + PH - 10.f, KV.Key);
			const bool bUp = KV.Value.Contains(TEXT("airborne")) || KV.Value.Contains(TEXT("CAP")) || KV.Value.Contains(TEXT("strike")) || KV.Value.Contains(TEXT("escort"));
			P.Text(40, Y + 44.f, bUp ? TEXT("IN FLIGHT") : TEXT("ON DECK"), false, 34, bUp ? AMBER : GREEN);
			int32 k = 0;
			for (const FString& Seg : Wrap(KV.Value.ToUpper(), 60))
			{
				if (k < 3)
				{
					P.Text(340, Y + 44.f + 22.f * k++, Seg, true, 16, TEXTC);
				}
			}
			Y += PH;
		}
		return;
	}
	// B: the sky around the Aquila: our craft and theirs
	P.Panel(20, 60, W - 20, 220, TEXT("Sky"));
	P.Text(40, 100, FString::Printf(TEXT("%d"), Ours), false, 64, CYAN);
	P.Text(40, 176, TEXT("OURS IN FLIGHT"), true, 16, CYAN);
	P.Text(W - 40, 100, FString::Printf(TEXT("%d"), Theirs), false, 64, Theirs ? RED : DIM, 2);
	P.Text(W - 40, 176, TEXT("ENEMY CRAFT"), true, 16, Theirs ? RED : DIM, 2);
	P.Panel(20, 240, W - 20, H - 20, TEXT("Flight line"));
	int32 k = 0;
	for (const FString& Seg : Wrap(Battle->FlightLine(), 60))
	{
		if (k < 12)
		{
			P.Text(40, 280 + 22.f * k++, Seg, true, 16, TEXTC);
		}
	}
}
