#include "AstraTransportConsole.h"
#include "AstraFonts.h"

#include "ASTRA.h"
#include "AstraTransporterSubsystem.h"
#include "CanvasItem.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/Canvas.h"
#include "Engine/CanvasRenderTarget2D.h"
#include "Engine/Font.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "Framework/Application/SlateApplication.h"
#include "ImageUtils.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Misc/FileHelper.h"
#include "Rendering/SlateRenderer.h"
#include "Fonts/FontMeasure.h"
#include "Kismet/GameplayStatics.h"

namespace
{
	FLinearColor XcRGB(int32 R, int32 G, int32 B, float A = 1.f)
	{
		return FLinearColor::FromSRGBColor(FColor((uint8)R, (uint8)G, (uint8)B, (uint8)(A * 255.f)));
	}
	const FLinearColor XcBG = XcRGB(4, 9, 18);
	const FLinearColor XcPanel = XcRGB(10, 22, 40);
	const FLinearColor XcLine = XcRGB(70, 140, 210);
	const FLinearColor XcDim = XcRGB(40, 80, 125);
	const FLinearColor XcText = XcRGB(205, 228, 255);
	const FLinearColor XcCyan = XcRGB(111, 195, 255);
	const FLinearColor XcAmber = XcRGB(255, 179, 71);
	const FLinearColor XcRed = XcRGB(255, 74, 46);
	const FLinearColor XcGreen = XcRGB(80, 220, 150);
	const FLinearColor XcGold = XcRGB(255, 226, 150);
	const FLinearColor XcHeader = XcRGB(6, 14, 28);
	const FLinearColor XcScience = XcRGB(155, 93, 229);

	/** A thin painter over a UCanvas (the bridge screens' way: every fill, then every line, then every text, so the canvas batches). */
	struct FXcPaint
	{
		UCanvas* C = nullptr;
		UFont* Title = nullptr;
		UFont* Mono = nullptr;
		float Time = 0.f;
		mutable TArray<FCanvasTileItem> Tiles;
		mutable TArray<FCanvasLineItem> Lines;
		mutable TArray<FCanvasTextItem> Texts;
		~FXcPaint() { Flush(); }
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
		void Line(float X0, float Y0, float X1, float Y1, const FLinearColor& Col, float Thick = 1.f) const
		{
			FCanvasLineItem L(FVector2D(X0, Y0), FVector2D(X1, Y1));
			L.SetColor(Col);
			L.LineThickness = Thick;
			Lines.Add(L);
		}
		void Frame(float X, float Y, float W, float H, const FLinearColor& Col, float Thick = 1.f) const
		{
			Line(X, Y, X + W, Y, Col, Thick);
			Line(X + W, Y, X + W, Y + H, Col, Thick);
			Line(X + W, Y + H, X, Y + H, Col, Thick);
			Line(X, Y + H, X, Y, Col, Thick);
		}
		void Ring(float CX, float CY, float R, const FLinearColor& Col, float Thick = 2.f, int32 Seg = 28) const
		{
			for (int32 i = 0; i < Seg; ++i)
			{
				const float A0 = 2.f * PI * i / Seg, A1 = 2.f * PI * (i + 1) / Seg;
				Line(CX + R * FMath::Cos(A0), CY + R * FMath::Sin(A0), CX + R * FMath::Cos(A1), CY + R * FMath::Sin(A1), Col, Thick);
			}
		}
		FSlateFontInfo Font(bool bMono, float Px, bool bBold = false) const
		{
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
			Rect(X0, Y0, X1 - X0, Y1 - Y0, XcPanel);
			Frame(X0, Y0, X1 - X0, Y1 - Y0, XcDim);
			Brackets(X0, Y0, X1, Y1, XcLine);
			if (!Label.IsEmpty())
			{
				Text(X0 + 10, Y0 + 5, Label.ToUpper(), false, 17, XcCyan);
				Line(X0 + 10, Y0 + 28, X1 - 10, Y0 + 28, XcDim);
			}
		}
		void Bar(float X, float Y, float W, float H, float Frac, const FLinearColor& Col) const
		{
			Rect(X, Y, W, H, XcRGB(6, 12, 24));
			Frame(X, Y, W, H, XcDim);
			const int32 Segs = 24;
			const float SW = W / Segs;
			const int32 N = FMath::Clamp(FMath::RoundToInt(Frac * Segs), 0, Segs);
			for (int32 i = 0; i < N; ++i)
			{
				Rect(X + i * SW + 1, Y + 2, SW - 2, H - 4, Col);
			}
		}
		float Pulse(float Hz = 1.2f) const { return 0.55f + 0.45f * FMath::Sin(Time * Hz * 2.f * PI); }
	};
}

AAstraTransportConsole::AAstraTransportConsole()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.TickInterval = 0.f;
	Panel = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Panel"));
	SetRootComponent(Panel);
	Panel->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Panel->SetCastShadow(false);
	Panel->SetMobility(EComponentMobility::Movable);
	static ConstructorHelpers::FObjectFinder<UStaticMesh> PlaneMesh(TEXT("/Engine/BasicShapes/Plane.Plane"));
	if (PlaneMesh.Succeeded())
	{
		Panel->SetStaticMesh(PlaneMesh.Object);
	}
	SetActorHiddenInGame(true);
}

void AAstraTransportConsole::Place(const FVector& CentreCm, float YawDeg, const FVector2D& SizeCm)
{
	Size = SizeCm;
	// the engine's Plane is 100 x 100 cm lying in XY, facing +Z: stand it up with its face along the way the screen faces (the yaw) and its local y up; its local x then runs to the
	// viewer's LEFT (the axes are left-handed: x cross y is z), which M_XPORT_Screen knows (it lays the picture by that local position, u = 0.5 - x/100, v = 0.5 - y/100, whatever
	// the plane's own texture mapping is); a centimetre off the wall's panel
	const FVector Face = FRotator(0.f, YawDeg, 0.f).Vector();
	SetActorLocationAndRotation(CentreCm + Face * 1.0, FRotationMatrix::MakeFromZY(Face, FVector::UpVector).ToQuat());
	SetActorScale3D(FVector(SizeCm.X / 100.0, SizeCm.Y / 100.0, 1.0));
}

void AAstraTransportConsole::EnsureTarget()
{
	if (Target)
	{
		return;
	}
	TitleFont = AstraFonts::Title();
	MonoFont = AstraFonts::Mono();
	if (!TitleFont || !MonoFont)
	{
		return;
	}
	const int32 W = 1536, H = FMath::Max(256, FMath::RoundToInt(W * (float)(Size.Y / Size.X)));
	Target = UCanvasRenderTarget2D::CreateCanvasRenderTarget2D(this, UCanvasRenderTarget2D::StaticClass(), W, H);
	Target->ClearColor = XcBG;
	Target->OnCanvasRenderTargetUpdate.AddDynamic(this, &AAstraTransportConsole::Draw);
	UMaterialInterface* Base = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/ASTRA/Materials/M_XPORT_Screen.M_XPORT_Screen"), nullptr, LOAD_Quiet | LOAD_NoWarn);
	if (!Base)
	{
		UE_LOG(LogASTRA, Warning, TEXT("[XportFx] M_XPORT_Screen is missing: the wall display stays dark; run tools/ue_scripts/make_transporter_fx.py in the editor"));
	}
	if (Base && Panel)
	{
		Mid = UMaterialInstanceDynamic::Create(Base, this);
		Mid->SetTextureParameterValue(TEXT("ScreenTexture"), Target);
		Mid->SetScalarParameterValue(TEXT("Intensity"), 5.f);
		Panel->SetMaterial(0, Mid);
	}
}

void AAstraTransportConsole::SetShown(bool bOn)
{
	if (bOn == bShown)
	{
		return;
	}
	bShown = bOn;
	SetActorHiddenInGame(!bOn);
	Wait = 0.f;
}

void AAstraTransportConsole::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	Age += DeltaSeconds;
	if (!bShown)
	{
		return;
	}
	Wait -= DeltaSeconds;
	if (Wait <= 0.f)
	{
		EnsureTarget();
		if (Target)
		{
			Wait = RedrawEvery;
			Target->FastUpdateResource();
		}
	}
}

void AAstraTransportConsole::Draw(UCanvas* Canvas, int32 Width, int32 Height)
{
	UAstraTransporterSubsystem* O = Owner.Get();
	FXcPaint P;
	P.C = Canvas;
	P.Title = Cast<UFont>(TitleFont);
	P.Mono = Cast<UFont>(MonoFont);
	P.Time = Age;
	const float W = (float)Width, H = (float)Height;
	FAstraXportView V;
	if (O)
	{
		O->GetView(V);
	}
	// ---- the header
	P.Rect(0, 0, W, 54.f, XcHeader);
	P.Rect(0, 0, 10.f, 54.f, XcScience);
	P.Text(24, 8, TEXT("TRANSPORTER ROOM"), false, 34, XcText);
	if (!V.bReady)
	{
		P.Text(W * 0.5f, H * 0.45f, TEXT("NO LINK WITH THE PATTERN BUFFER"), false, 40, XcRed, 1);
		P.Text(W * 0.5f, H * 0.45f + 56.f, TEXT("the room is not on the ship's plan"), true, 20, XcDim, 1);
		return;
	}
	const FLinearColor StateCol = V.RoomState == TEXT("ready") ? XcGreen : (V.RoomState == TEXT("reduced") ? XcAmber : XcRed);
	P.Text(W - 20.f, 16, FString::Printf(TEXT("DECK 5  ·  SYSTEM %s  ·  %.0f%% POWER  ·  REACH %.0f KM  ·  CYCLE %.1f S"), *V.RoomState.ToUpper(), V.RoomPower * 100.f, V.ReachKm, V.CycleS), true, 18, StateCol, 2);

	const float Top = 70.f, Bot = H - 18.f;
	// ---- the pads
	{
		const float X0 = 20.f, X1 = 490.f;
		P.Panel(X0, Top, X1, Bot, TEXT("Pads"));
		const float Cx = (X0 + X1) * 0.5f, Cy = Top + 215.f, R = 118.f;
		P.Ring(Cx, Cy, 26.f, XcDim, 2.f);
		P.Ring(Cx, Cy, 12.f, V.OwnFace >= 0 ? XcGold : XcLine, 3.f);
		const TArray<FAstraXportPad>& Pads = O->GetPads();
		for (int32 i = 0; i < 6 && i < Pads.Num(); ++i)
		{
			const float A = -PI * 0.5f + 2.f * PI * (float)i / 6.f;
			const float Px = Cx + R * FMath::Cos(A), Py = Cy + R * FMath::Sin(A);
			FLinearColor Col = XcDim;
			switch (Pads[i].Look)
			{
			case EAstraPadLook::Selected: Col = XcCyan; break;
			case EAstraPadLook::Locking: Col = XcAmber; break;
			case EAstraPadLook::Locked: Col = XcGreen; break;
			case EAstraPadLook::Energizing: Col = XcGold; break;
			case EAstraPadLook::Fault: Col = XcRed; break;
			default: break;
			}
			if (Pads[i].Look == EAstraPadLook::Energizing || Pads[i].Look == EAstraPadLook::Locking)
			{
				Col.A = 0.55f + 0.45f * P.Pulse(Pads[i].Look == EAstraPadLook::Energizing ? 3.f : 1.5f);
			}
			P.Line(Cx + 28.f * FMath::Cos(A), Cy + 28.f * FMath::Sin(A), Px - 30.f * FMath::Cos(A), Py - 30.f * FMath::Sin(A), XcDim);
			P.Ring(Px, Py, 30.f, Col, 4.f);
			P.Text(Px, Py - 13.f, FString::Printf(TEXT("%d"), i + 1), true, 26, Col, 1, true);
			const FString Who = Pads[i].Occupant.Replace(TEXT("Lieutenant Commander "), TEXT("LCdr ")).Replace(TEXT("Lieutenant "), TEXT("Lt ")).Replace(TEXT("Petty Officer "), TEXT("PO ")).Replace(TEXT("Crewman "), TEXT("Cm "));
			if (!Who.IsEmpty())
			{
				P.Text(Px, Py + (Py > Cy ? 36.f : -56.f), Who.Left(17), true, 14, XcText, 1);
			}
		}
		// the cargo pad and the Medbay's
		const float Yb = Top + 410.f;
		if (Pads.IsValidIndex(6))
		{
			P.Frame(X0 + 30.f, Yb, 200.f, 44.f, Pads[6].Look == EAstraPadLook::Idle ? XcDim : XcAmber, 2.f);
			P.Text(X0 + 40.f, Yb + 4.f, TEXT("CARGO PAD"), true, 14, XcCyan);
			P.Text(X0 + 40.f, Yb + 22.f, Pads[6].Occupant.IsEmpty() ? FString(TEXT("clear")) : Pads[6].Occupant.Left(22), true, 14, XcText);
		}
		P.Text(X0 + 270.f, Yb + 4.f, TEXT("MEDBAY PADS"), true, 14, XcCyan);
		for (int32 k = 0; k < 2; ++k)
		{
			const int32 Idx = 7 + k;
			const FLinearColor C = Pads.IsValidIndex(Idx) && Pads[Idx].Look != EAstraPadLook::Idle ? XcAmber : XcDim;
			P.Ring(X0 + 290.f + 70.f * (float)k, Yb + 32.f, 13.f, C, 3.f);
			P.Text(X0 + 290.f + 70.f * (float)k, Yb + 24.f, FString::Printf(TEXT("%d"), k + 1), true, 14, C, 1);
		}
		P.Text(X0 + 20.f, Bot - 60.f, FString::Printf(TEXT("%d AWAY FROM THE SHIP"), V.Away), true, 16, V.Away ? XcAmber : XcDim);
		P.Text(X0 + 20.f, Bot - 36.f, FString::Printf(TEXT("%.0f MW A CYCLE FOR ONE"), V.EnergyMW), true, 14, XcDim);
	}
	// ---- the beam: the Aquila's six shield faces, what the beam crosses, the conditions
	{
		const float X0 = 510.f, X1 = 1010.f;
		P.Panel(X0, Top, X1, Bot, TEXT("Aquila · shields and beam"));
		const float Cx = (X0 + X1) * 0.5f, Cy = Top + 170.f;
		const float HullW = 330.f, HullH = 70.f;
		P.Frame(Cx - HullW * 0.5f, Cy - HullH * 0.5f, HullW, HullH, XcDim, 2.f);
		P.Line(Cx + HullW * 0.5f, Cy - HullH * 0.5f, Cx + HullW * 0.5f + 34.f, Cy, XcDim, 2.f);
		P.Line(Cx + HullW * 0.5f, Cy + HullH * 0.5f, Cx + HullW * 0.5f + 34.f, Cy, XcDim, 2.f);
		auto Face = [&](int32 F, float Fx, float Fy, float Fw, float Fh, const TCHAR* Name, bool bVert)
		{
			const float Fr = V.Faces[F];
			const bool bOpen = !V.bShieldsUp || Fr <= 0.05f;
			const FLinearColor C = bOpen ? XcRed : (Fr < 0.4f ? XcAmber : XcCyan);
			const bool bUsed = F == V.OwnFace;
			P.Rect(Fx, Fy, Fw, Fh, FLinearColor(C.R, C.G, C.B, 0.20f + 0.35f * (V.bShieldsUp ? Fr : 0.f)));
			P.Frame(Fx, Fy, Fw, Fh, bUsed ? XcGold : C, bUsed ? 3.f : 1.f);
			P.Text(Fx + Fw * 0.5f, Fy + (bVert ? Fh * 0.5f - 18.f : 3.f), Name, true, 12, XcText, 1);
			P.Text(Fx + Fw * 0.5f, Fy + (bVert ? Fh * 0.5f - 2.f : 17.f), V.bShieldsUp ? FString::Printf(TEXT("%.0f%%"), Fr * 100.f) : FString(TEXT("DOWN")), true, 14, C, 1, true);
		};
		Face(0, Cx + HullW * 0.5f - 62.f, Cy - HullH * 0.5f + 4.f, 58.f, HullH - 8.f, TEXT("BOW"), true);
		Face(1, Cx - HullW * 0.5f + 4.f, Cy - HullH * 0.5f + 4.f, 58.f, HullH - 8.f, TEXT("STERN"), true);
		Face(2, Cx - HullW * 0.5f + 70.f, Cy - HullH * 0.5f + 4.f, HullW - 140.f, 32.f, TEXT("PORT"), false);
		Face(3, Cx - HullW * 0.5f + 70.f, Cy + HullH * 0.5f - 36.f, HullW - 140.f, 32.f, TEXT("STARBOARD"), false);
		Face(4, Cx - 70.f, Cy + HullH * 0.5f + 16.f, 64.f, 40.f, TEXT("DORSAL"), false);
		Face(5, Cx + 6.f, Cy + HullH * 0.5f + 16.f, 64.f, 40.f, TEXT("VENTRAL"), false);
		P.Text(Cx, Cy - HullH * 0.5f - 24.f, V.bShieldsUp ? TEXT("SHIELDS UP") : TEXT("SHIELDS DOWN"), true, 16, V.bShieldsUp ? XcCyan : XcRed, 1, true);
		// the conditions
		float Y = Top + 290.f;
		auto Row = [&](const TCHAR* Label, float Frac, const FString& Value, const FLinearColor& Col)
		{
			P.Text(X0 + 24.f, Y, Label, true, 14, XcDim);
			P.Bar(X0 + 170.f, Y + 2.f, 190.f, 14.f, Frac, Col);
			P.Text(X0 + 376.f, Y, Value, true, 14, XcText);
			Y += 26.f;
		};
		Row(TEXT("ROOM POWER"), V.RoomPower, FString::Printf(TEXT("%.0f%%"), V.RoomPower * 100.f), V.RoomPower < 0.6f ? XcAmber : XcGreen);
		Row(TEXT("ACCELERATION"), FMath::Clamp(V.Accel / 9.f, 0.f, 1.f), FString::Printf(TEXT("%.1f m/s2"), V.Accel), V.Accel > 3.f ? XcAmber : XcGreen);
		Row(TEXT("TURN RATE"), FMath::Clamp(V.Turn / 2.f, 0.f, 1.f), FString::Printf(TEXT("%.1f deg/s"), V.Turn), V.Turn > 0.8f ? XcAmber : XcGreen);
		Row(TEXT("JAMMING ON THE LINE"), V.Jam, FString::Printf(TEXT("%.0f%%"), V.Jam * 100.f), V.Jam > 0.25f ? XcAmber : XcGreen);
		if (V.GateKm >= 0.f)
		{
			Row(TEXT("JANUS GATE"), FMath::Clamp(1.f - V.GateKm / 60.f, 0.f, 1.f), V.bGateLane ? FString(TEXT("IN THE LANE")) : FString::Printf(TEXT("%.0f km"), V.GateKm), V.GateKm < 25.f ? XcRed : (V.GateKm < 60.f ? XcAmber : XcGreen));
		}
		else
		{
			P.Text(X0 + 24.f, Y, TEXT("JANUS GATE"), true, 14, XcDim);
			P.Text(X0 + 170.f, Y, TEXT("none in this system"), true, 14, XcDim);
		}
	}
	// ---- the transports and what can be reached
	{
		const float X0 = 1030.f, X1 = W - 20.f;
		P.Panel(X0, Top, X1, Bot, TEXT("Transports"));
		float Y = Top + 40.f;
		int32 Shown = 0;
		const TArray<FAstraXportJob>& Jobs = O->Jobs();
		for (int32 i = Jobs.Num() - 1; i >= 0 && Shown < 3; --i)
		{
			const FAstraXportJob& J = Jobs[i];
			const bool bLive = AstraXportLive(J.Phase);
			if (!bLive && P.Time > 0.f && J.EndedAt > 0.0 && O->GetWorld() && O->GetWorld()->GetTimeSeconds() - J.EndedAt > 60.0)
			{
				continue;
			}
			const FLinearColor C = bLive ? (AstraXportInBeam(J.Phase) ? XcGold : (J.Phase == EAstraXportPhase::Locked ? XcGreen : XcAmber)) : (J.Phase == EAstraXportPhase::Done ? XcGreen : XcRed);
			P.Text(X0 + 14.f, Y, FString::Printf(TEXT("%s  %s"), *J.Tag, AstraXportPhaseName(J.Phase)), true, 18, C, 0, true);
			FString Who = J.Subs.Num() == 1 ? J.Subs[0].S.Label : FString::Printf(TEXT("%d subjects"), J.Subs.Num());
			P.Text(X0 + 14.f, Y + 22.f, FString::Printf(TEXT("%s > %s"), *Who.Left(24), *J.ToText.Left(26)), true, 13, XcText);
			if (bLive)
			{
				const float Frac = AstraXportInBeam(J.Phase) ? FMath::Clamp(J.Cycle / FMath::Max(0.1f, J.CycleS), 0.f, 1.f) : J.Lock.Progress;
				P.Bar(X0 + 14.f, Y + 42.f, 210.f, 12.f, Frac, C);
				P.Text(X0 + 236.f, Y + 39.f, FString::Printf(TEXT("Q %.0f%%"), J.Lock.Quality * 100.f), true, 13, XcText);
				if (!J.Blockers.IsEmpty())
				{
					P.Text(X0 + 14.f, Y + 58.f, J.Blockers[0].Left(46), true, 12, XcRed);
				}
			}
			else
			{
				P.Text(X0 + 14.f, Y + 40.f, J.Outcome.Left(52), true, 12, XcDim);
			}
			Y += 84.f;
			++Shown;
		}
		if (!Shown)
		{
			P.Text(X0 + 14.f, Y, TEXT("NOTHING IN THE BEAM"), true, 16, XcDim);
			Y += 40.f;
		}
		Y = FMath::Max(Y, Top + 290.f);
		P.Line(X0 + 14.f, Y - 8.f, X1 - 14.f, Y - 8.f, XcDim);
		P.Text(X0 + 14.f, Y, TEXT("CAN REACH NOW"), true, 14, XcCyan);
		Y += 24.f;
		for (const FAstraXportOption& Op : V.Options)
		{
			const FLinearColor C = Op.bOk ? XcGreen : (Op.bUnknown ? XcAmber : XcRed);
			P.Text(X0 + 14.f, Y, FString::Printf(TEXT("%s  %s"), *Op.To.Left(8), Op.bOk ? TEXT("YES") : (Op.bUnknown ? TEXT("NO TRACK") : TEXT("NO"))), true, 14, C, 0, true);
			P.Text(X0 + 14.f, Y + 17.f, (Op.Why.Num() ? Op.Why[0] : Op.Label).Left(48), true, 11, XcDim);
			Y += 40.f;
		}
		if (!V.Last.IsEmpty())
		{
			P.Text(X0 + 14.f, Bot - 30.f, V.Last.Left(52), true, 11, XcDim);
		}
	}
}

bool AAstraTransportConsole::Dump(const FString& Path)
{
	bShown = true;
	EnsureTarget();
	if (!Target)
	{
		return false;
	}
	Target->UpdateResource();
	FlushRenderingCommands();
	TArray<FColor> Pixels;
	FTextureRenderTargetResource* Res = Target->GameThread_GetRenderTargetResource();
	if (!Res || !Res->ReadPixels(Pixels))
	{
		return false;
	}
	TArray64<uint8> Png;
	FImageUtils::PNGCompressImageArray(Target->SizeX, Target->SizeY, TArrayView64<const FColor>(Pixels.GetData(), Pixels.Num()), Png);
	return FFileHelper::SaveArrayToFile(Png, *Path);
}
