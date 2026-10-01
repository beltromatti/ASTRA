#include "AstraTransportConsole.h"

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
	// the engine's Plane is 100 x 100 cm lying in XY, facing +Z: stand it up, its face along the actor's +X (the way the room's wall panel faces: yaw)
	SetActorLocationAndRotation(CentreCm, FRotator(90.f, YawDeg, 0.f));
	SetActorScale3D(FVector(SizeCm.Y / 100.0, SizeCm.X / 100.0, 1.0));
}

void AAstraTransportConsole::EnsureTarget()
{
	if (Target)
	{
		return;
	}
	TitleFont = LoadObject<UFont>(nullptr, TEXT("/Game/ASTRA/UI/Fonts/F_ASTRA_Title.F_ASTRA_Title"));
	MonoFont = LoadObject<UFont>(nullptr, TEXT("/Game/ASTRA/UI/Fonts/F_ASTRA_Mono.F_ASTRA_Mono"));
	if (!TitleFont || !MonoFont)
	{
		return;
	}
	const int32 W = 1536, H = FMath::Max(256, FMath::RoundToInt(W * (float)(Size.Y / Size.X)));
	Target = UCanvasRenderTarget2D::CreateCanvasRenderTarget2D(this, UCanvasRenderTarget2D::StaticClass(), W, H);
	Target->ClearColor = XcBG;
	Target->OnCanvasRenderTargetUpdate.AddDynamic(this, &AAstraTransportConsole::Draw);
	UMaterialInterface* Base = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/ASTRA/Materials/M_ASTRA_Screen.M_ASTRA_Screen"));
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
	P.Rect(0, 0, (float)Width, 54.f, XcHeader);
	P.Rect(0, 0, 10.f, 54.f, XcScience);
	P.Text(24, 8, TEXT("TRANSPORTER ROOM"), false, 34, XcText);
	P.Text(Width - 20.f, 16, O ? FString::Printf(TEXT("DECK 5 · %d TRANSPORTS"), O->Jobs().Num()) : FString(TEXT("OFFLINE")), true, 18, XcCyan, 2);
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
