#include "AstraViewscreen.h"
#include "ASTRA.h"
#include "AstraShipSubsystem.h"
#include "AstraStations.h"
#include "CanvasItem.h"
#include "Camera/PlayerCameraManager.h"
#include "Components/SceneCaptureComponent2D.h"
#include "Components/StaticMeshComponent.h"
#include "Dom/JsonObject.h"
#include "Engine/Canvas.h"
#include "Engine/CanvasRenderTarget2D.h"
#include "Engine/Font.h"
#include "Engine/PostProcessVolume.h"
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/TextureRenderTarget2D.h"
#include "EngineUtils.h"
#include "Fonts/FontMeasure.h"
#include "ImageUtils.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Framework/Application/SlateApplication.h"
#include "Kismet/GameplayStatics.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
#include "ProceduralMeshComponent.h"

namespace
{
	TAutoConsoleVariable<int32> CVarViewscreenHz(TEXT("astra.viewscreen.hz"), 30, TEXT("Main viewscreen: optical feed and overlay refreshes per second (0 = frozen)"));
	FAutoConsoleCommandWithWorldAndArgs CmdViewscreenDump(TEXT("astra.viewscreen.dump"),
		TEXT("Testing: astra.viewscreen.dump [path.png] (the main viewscreen's image at full resolution, feed under overlay)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& A, UWorld* World)
		{
			for (TActorIterator<AAstraViewscreen> It(World); It; ++It)
			{
				const FString Path = A.Num() ? A[0] : FPaths::ProjectSavedDir() / TEXT("Play/viewscreen.png");
				UE_LOG(LogASTRA, Display, TEXT("[Viewscreen] dump %s: %s"), *Path, It->Dump(Path) ? TEXT("ok") : TEXT("failed"));
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdViewscreenWhat(TEXT("astra.viewscreen.what"),
		TEXT("Testing: astra.viewscreen.what (every visible thing in the optical sensors' field of view, nearest first)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& A, UWorld* World)
		{
			for (TActorIterator<AAstraViewscreen> It(World); It; ++It)
			{
				It->LogWhatIsInView();
			}
		}));

	using FContact = UAstraBattleSubsystem::FContactView;
	const FLinearColor ColAstra(0.40f, 0.74f, 1.0f);
	const FLinearColor ColMandate(1.0f, 0.60f, 0.20f);
	const FLinearColor ColNeutral(0.84f, 0.87f, 0.91f);
	const FLinearColor ColBearing(0.58f, 0.60f, 0.64f);
	const FLinearColor ColAlarm(1.0f, 0.28f, 0.18f);
	const FLinearColor ColText(0.88f, 0.94f, 1.0f);
	const FLinearColor ColDim(0.50f, 0.62f, 0.74f);
	const double StandOff = 100000.0;     // cm: the optical sensors look from 1 km out, beyond the Aquila's hull

	FLinearColor SideColor(const FContact& C)
	{
		if (C.Track < 2) return ColBearing;
		return C.Side == EAstraSide::Astra ? ColAstra : C.Side == EAstraSide::Mandate ? ColMandate : ColNeutral;
	}

	FLinearColor Dimmed(const FLinearColor& C, float K)
	{
		return FLinearColor(C.R * K, C.G * K, C.B * K, C.A);
	}

	/** A contact by id ("T-23"), or else by name ("Cocytus"). */
	const FContact* FindC(const TArray<FContact>& Cs, const FString& Id)
	{
		if (Id.IsEmpty()) return nullptr;
		if (const FContact* C = Cs.FindByPredicate([&Id](const FContact& X) { return X.ContactId.Equals(Id, ESearchCase::IgnoreCase); }))
		{
			return C;
		}
		return Cs.FindByPredicate([&Id](const FContact& X) { return X.Label.Contains(Id, ESearchCase::IgnoreCase); });
	}

	/** The 8 corners of a ship's hull box in the level (false when the optical sensors have nothing to look at). */
	bool HullCorners(const FContact& C, FVector (&Out)[8])
	{
		const UStaticMeshComponent* M = C.Actor ? C.Actor->GetStaticMeshComponent() : nullptr;
		const UStaticMesh* SM = M ? M->GetStaticMesh() : nullptr;
		if (!SM || C.Actor->IsHidden())
		{
			return false;
		}
		const FBox B = SM->GetBoundingBox();
		const FTransform& T = M->GetComponentTransform();
		for (int32 i = 0; i < 8; ++i)
		{
			Out[i] = T.TransformPosition(FVector((i & 1) ? B.Max.X : B.Min.X, (i & 2) ? B.Max.Y : B.Min.Y, (i & 4) ? B.Max.Z : B.Min.Z));
		}
		return true;
	}

	/** Batched drawing on a canvas: tiles, then lines, then texts (FCanvas starts a batch at each change of item type). */
	struct FDraw
	{
		UCanvas* C = nullptr;
		UFont* Mono = nullptr;
		UFont* Title = nullptr;
		TArray<FCanvasTileItem> Tiles;
		TArray<FCanvasLineItem> Lines;
		TArray<FCanvasTextItem> Texts;

		FSlateFontInfo Font(bool bMono, float Px) const
		{
			// sizes in pixels; Slate sizes are points at 96 dpi
			return FSlateFontInfo(bMono ? Mono : Title, FMath::Max(6, FMath::RoundToInt(Px * 0.75f)), TEXT("Regular"));
		}
		float Width(const FString& S, bool bMono, float Px) const
		{
			if (!FSlateApplication::IsInitialized())
			{
				return S.Len() * Px * 0.6f;
			}
			return FSlateApplication::Get().GetRenderer()->GetFontMeasureService()->Measure(S, Font(bMono, Px)).X;
		}
		/** Align: 0 left, 1 centre, 2 right. Y is the top of the text. */
		void Text(float X, float Y, const FString& S, bool bMono, float Px, const FLinearColor& Col, int32 Align = 0)
		{
			const float W = Align ? Width(S, bMono, Px) : 0.f;
			FCanvasTextItem T(FVector2D(X - (Align == 1 ? W * 0.5f : (Align == 2 ? W : 0.f)), Y), FText::FromString(S), Font(bMono, Px), Col);
			T.BlendMode = SE_BLEND_Translucent;
			T.EnableShadow(FLinearColor(0.f, 0.f, 0.f, 0.75f), FVector2D(1.f, 1.f));
			Texts.Add(T);
		}
		void Tile(float X, float Y, float W, float H, const FLinearColor& Col)
		{
			FCanvasTileItem T(FVector2D(X, Y), FVector2D(W, H), Col);
			T.BlendMode = SE_BLEND_Translucent;
			Tiles.Add(T);
		}
		void Line(FVector2D A, FVector2D B, const FLinearColor& Col, float Thick = 1.5f)
		{
			FCanvasLineItem L(A, B);
			L.SetColor(Col);
			L.LineThickness = Thick;
			Lines.Add(L);
		}
		void Brackets(const FBox2D& R, const FLinearColor& Col, float Thick)
		{
			const FVector2D Sz = R.GetSize();
			const float L = FMath::Clamp(FMath::Min(Sz.X, Sz.Y) * 0.3f, 4.f, 28.f);
			const FVector2D P[4] = {R.Min, FVector2D(R.Max.X, R.Min.Y), R.Max, FVector2D(R.Min.X, R.Max.Y)};
			const FVector2D Sg[4] = {FVector2D(1, 1), FVector2D(-1, 1), FVector2D(-1, -1), FVector2D(1, -1)};
			for (int32 i = 0; i < 4; ++i)
			{
				Line(P[i], P[i] + FVector2D(Sg[i].X * L, 0.f), Col, Thick);
				Line(P[i], P[i] + FVector2D(0.f, Sg[i].Y * L), Col, Thick);
			}
		}
		void Ring(FVector2D Ctr, float R, const FLinearColor& Col, float Spin)
		{
			// the lock reticle: four arcs with gaps, turning slowly
			for (int32 s = 0; s < 4; ++s)
			{
				const float A0 = Spin + s * UE_HALF_PI, A1 = A0 + UE_HALF_PI * 0.6f;
				FVector2D Prev = Ctr + FVector2D(FMath::Cos(A0), FMath::Sin(A0)) * R;
				for (int32 k = 1; k <= 6; ++k)
				{
					const float A = FMath::Lerp(A0, A1, k / 6.f);
					const FVector2D P = Ctr + FVector2D(FMath::Cos(A), FMath::Sin(A)) * R;
					Line(Prev, P, Col, 2.f);
					Prev = P;
				}
			}
		}
		void Bar(float X, float Y, float W, float Frac, const FLinearColor& Col)
		{
			Tile(X, Y, W, 4.f, FLinearColor(0.f, 0.f, 0.f, 0.6f));
			Tile(X, Y, W * FMath::Clamp(Frac, 0.f, 1.f), 4.f, Col);
		}
		void Flush()
		{
			for (FCanvasTileItem& T : Tiles) { C->DrawItem(T); }
			for (FCanvasLineItem& L : Lines) { C->DrawItem(L); }
			for (FCanvasTextItem& T : Texts) { C->DrawItem(T); }
		}
	};
}

AAstraViewscreen::AAstraViewscreen()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.TickGroup = TG_PostUpdateWork;
	RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	Capture = CreateDefaultSubobject<USceneCaptureComponent2D>(TEXT("OpticalSensors"));
	Capture->SetupAttachment(RootComponent);
	Capture->SetUsingAbsoluteLocation(true);
	Capture->SetUsingAbsoluteRotation(true);
	Capture->bCaptureEveryFrame = false;
	Capture->bCaptureOnMovement = false;
	Capture->bAlwaysPersistRenderingState = true;   // its own exposure and anti-aliasing history, like an eye
	Capture->CaptureSource = ESceneCaptureSource::SCS_FinalColorLDR;
}

void AAstraViewscreen::BeginPlay()
{
	Super::BeginPlay();
	Mono = LoadObject<UFont>(nullptr, TEXT("/Game/ASTRA/UI/Fonts/F_ASTRA_Mono.F_ASTRA_Mono"));
	Title = LoadObject<UFont>(nullptr, TEXT("/Game/ASTRA/UI/Fonts/F_ASTRA_Title.F_ASTRA_Title"));
	// the image plane: a quad facing the Captain (-X), bottom edge at the actor, UVs 0-1 left to right, top to bottom
	UProceduralMeshComponent* Quad = NewObject<UProceduralMeshComponent>(this, TEXT("ScreenQuad"));
	Screen = Quad;
	Quad->SetupAttachment(RootComponent);
	Quad->RegisterComponent();
	const float W = WidthM * 50.f, H = HeightM * 100.f;
	const TArray<FVector> V = {FVector(0, -W, 0), FVector(0, W, 0), FVector(0, W, H), FVector(0, -W, H)};
	const TArray<int32> T = {0, 2, 1, 0, 3, 2};
	const TArray<FVector> N(std::initializer_list<FVector>{FVector(-1, 0, 0), FVector(-1, 0, 0), FVector(-1, 0, 0), FVector(-1, 0, 0)});
	const TArray<FVector2D> Uv = {FVector2D(0, 1), FVector2D(1, 1), FVector2D(1, 0), FVector2D(0, 0)};
	Quad->CreateMeshSection(0, V, T, N, Uv, {}, {}, false);
	Quad->SetCastShadow(false);
	Quad->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Quad->SetTranslucentSortPriority(10);

	Feed = NewObject<UTextureRenderTarget2D>(this, TEXT("RT_ViewscreenFeed"));
	Feed->RenderTargetFormat = ETextureRenderTargetFormat::RTF_RGBA8;
	Feed->ClearColor = FLinearColor::Black;
	Feed->InitAutoFormat(FeedWidth, FeedHeight);
	Feed->UpdateResourceImmediate(true);
	Capture->TextureTarget = Feed;
	Overlay = UCanvasRenderTarget2D::CreateCanvasRenderTarget2D(this, UCanvasRenderTarget2D::StaticClass(), FeedWidth, FeedHeight);
	Overlay->ClearColor = FLinearColor(0.f, 0.f, 0.f, 1.f);   // the canvas leaves 1 - coverage in alpha: feed * a + rgb
	Overlay->OnCanvasRenderTargetUpdate.AddDynamic(this, &AAstraViewscreen::DrawOverlay);

	// the camera sees space as the eye does through the window (the level's exposure), minus what a sensor feed does
	// not need (global illumination and reflections of a bridge it never looks at, motion blur)
	float EV = 6.6f;                  // EV100 of the bridge in space (tools/ue_scripts/build_bridge.py)
	for (TActorIterator<APostProcessVolume> It(GetWorld()); It; ++It)
	{
		if (It->bUnbound && It->Settings.bOverride_AutoExposureMinBrightness)
		{
			Capture->PostProcessSettings = It->Settings;
			EV = It->Settings.AutoExposureMinBrightness;
			break;
		}
	}
	FPostProcessSettings& PP = Capture->PostProcessSettings;
	PP.bOverride_AutoExposureMethod = true;
	PP.AutoExposureMethod = EAutoExposureMethod::AEM_Histogram;
	PP.bOverride_AutoExposureMinBrightness = PP.bOverride_AutoExposureMaxBrightness = true;
	// the sensor's gain: one stop over the eye at the window, fixed. An adaptive gain lifted the empty sky around a
	// small ship until a zoomed patch of nebula filled the frame with a flat blue.
	PP.AutoExposureMinBrightness = PP.AutoExposureMaxBrightness = EV - 1.f;
	PP.bOverride_AutoExposureBias = true;
	PP.AutoExposureBias = 0.f;
	PP.bOverride_DynamicGlobalIlluminationMethod = true;
	PP.DynamicGlobalIlluminationMethod = EDynamicGlobalIlluminationMethod::None;
	PP.bOverride_ReflectionMethod = true;
	PP.ReflectionMethod = EReflectionMethod::None;
	PP.bOverride_MotionBlurAmount = true;
	PP.MotionBlurAmount = 0.f;
	PP.bOverride_AmbientOcclusionIntensity = true;
	PP.AmbientOcclusionIntensity = 0.f;
	Capture->PostProcessBlendWeight = 1.f;
	// what a sensor feed of ships in sunlight does not need, at 30 Hz next to the bridge's own frame: no shadow maps (the
	// ships cast none), no screen-space or distance-field effects, no fog
	FEngineShowFlags& SF = Capture->ShowFlags;
	SF.SetMotionBlur(false);
	SF.SetDynamicShadows(false);
	SF.SetContactShadows(false);
	SF.SetAmbientOcclusion(false);
	SF.SetDistanceFieldAO(false);
	SF.SetScreenSpaceReflections(false);
	SF.SetFog(false);
	SF.SetVolumetricFog(false);
	SF.SetLumenGlobalIllumination(false);
	SF.SetLumenReflections(false);

	if (UMaterialInterface* M = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/ASTRA/UI/Materials/M_ASTRA_Viewscreen.M_ASTRA_Viewscreen")))
	{
		Mid = UMaterialInstanceDynamic::Create(M, this);
		Mid->SetTextureParameterValue(TEXT("Feed"), Feed);
		Mid->SetTextureParameterValue(TEXT("Overlay"), Overlay);
		Mid->SetScalarParameterValue(TEXT("Fade"), 0.f);
		Mid->SetScalarParameterValue(TEXT("Opacity"), 0.985f);   // the window's mullions must not show through the image
		Mid->SetScalarParameterValue(TEXT("Intensity"), 21.f);    // as bright as the consoles (M_ASTRA_Screen instances: 22)
		Quad->SetMaterial(0, Mid);
	}
	else
	{
		UE_LOG(LogASTRA, Warning, TEXT("[Viewscreen] M_ASTRA_Viewscreen missing (tools/ue_scripts/make_viewscreen_material.py): the screen stays dark"));
		Quad->SetVisibility(false);
	}
}

FString AAstraViewscreen::Describe() const
{
	if (Shot == EShot::Off || FadeWant < 0.5f)
	{
		return TEXT("off (the bare window)");
	}
	FString What;
	switch (Shot)
	{
	case EShot::Contact: What = FString::Printf(TEXT("%s (%s)"), *ShotId, *ShotName); break;
	case EShot::Group: What = ShotName.ToLower(); break;
	case EShot::Point: What = FString::Printf(TEXT("where %s was destroyed"), *ShotName); break;
	case EShot::Ship: What = TEXT("the Aquila from outside"); break;
	default: What = TEXT("the view ahead"); break;
	}
	return FString::Printf(TEXT("%s: %s, %s, zoom x%.0f"), *Mode, *ShotWhy.ToLower(), *What, 58.f / FMath::Max(Fov, 0.05f));
}

void AAstraViewscreen::Cut(EShot NewShot, const FString& Id, const FString& Name, const FString& Why, int32 Pri, double Hold)
{
	const bool bSame = NewShot == Shot && Id == ShotId;
	Shot = NewShot;
	ShotId = Id;
	ShotName = Name;
	ShotWhy = Why;
	ShotPri = Pri;
	HoldUntil = Now + Hold;
	if (!bSame)
	{
		ShotSince = Now;
		FromRot = CamRot;
		PanSince = Now;
		bPushIn = true;
	}
}

void AAstraViewscreen::ReleaseOrder(const FString& Why)
{
	UAstraStationsSubsystem* St = GetWorld() ? GetWorld()->GetSubsystem<UAstraStationsSubsystem>() : nullptr;
	if (!St)
	{
		return;
	}
	TSharedPtr<FJsonObject> A = MakeShared<FJsonObject>();
	A->SetStringField(TEXT("station"), TEXT("ops"));
	A->SetStringField(TEXT("aspect"), TEXT("viewscreen"));
	A->SetStringField(TEXT("mode"), TEXT("auto"));
	A->SetStringField(TEXT("note"), Why);
	FString Detail;
	St->SetMode(A, TEXT("auto"), Detail);
}

void AAstraViewscreen::Direct(float Dt)
{
	UWorld* W = GetWorld();
	const UAstraStationsSubsystem* St = W ? W->GetSubsystem<UAstraStationsSubsystem>() : nullptr;
	const UAstraBattleSubsystem* B = W ? W->GetSubsystem<UAstraBattleSubsystem>() : nullptr;
	if (!St || !B)
	{
		return;
	}
	const TArray<FContact>& Cs = Contacts;
	const FString Engaged = St->ActionTarget();
	// what happened since the last look: ships destroyed (not merely lost from the plot), heavy hits
	FString HitId, HitName;
	TMap<FString, TPair<FVector, FString>> Seen;
	for (const FContact& C : Cs)
	{
		if (C.Track < 2 || C.bCraft)
		{
			continue;
		}
		Seen.Add(C.ContactId, TPair<FVector, FString>(C.Pos, C.Label));
		if (C.HullFrac >= 0.f)
		{
			float& Dmg = RecentDamage.FindOrAdd(C.ContactId);
			Dmg *= FMath::Exp(-Dt / 2.5f);
			if (const float* Prev = LastHull.Find(C.ContactId))
			{
				Dmg += FMath::Max(0.f, *Prev - C.HullFrac);
			}
			LastHull.Add(C.ContactId, C.HullFrac);
			if (Dmg > 0.07f && HitId.IsEmpty() && (C.Side == EAstraSide::Astra || C.ContactId == Engaged))
			{
				HitId = C.ContactId;
				HitName = C.Label;
				Dmg = 0.f;
			}
		}
	}
	for (const auto& KV : LastSeen)
	{
		if (!Seen.Contains(KV.Key) && B->WasDestroyed(KV.Key) && FVector::Dist(KV.Value.Key, B->PlayerPos()) < 150000.0)
		{
			Deaths.Add({KV.Key, KV.Value.Value, KV.Value.Key, Now});
		}
	}
	LastSeen = MoveTemp(Seen);
	Deaths.RemoveAll([this](const FDeath& D) { return Now - D.At > 4.0; });

	// ops' order
	Mode = St->ModeOf(TEXT("ops"), TEXT("viewscreen"));
	if (Mode.IsEmpty())
	{
		Mode = TEXT("auto");
	}
	const TSharedPtr<FJsonObject> Params = St->ParamsOf(TEXT("ops"), TEXT("viewscreen"));
	FString Target;
	Zoom = 1.f;
	if (Params.IsValid())
	{
		if (!Params->TryGetStringField(TEXT("target"), Target))
		{
			Params->TryGetStringField(TEXT("party"), Target);
		}
		double Zn = 0.0;
		FString Zs;
		if (Params->TryGetNumberField(TEXT("zoom"), Zn))
		{
			Zoom = FMath::Clamp((float)Zn, 0.25f, 8.f);
		}
		else if (Params->TryGetStringField(TEXT("zoom"), Zs))
		{
			Zoom = Zs == TEXT("close") ? 2.f : Zs == TEXT("max") ? 4.f : Zs == TEXT("wide") ? 0.4f : 1.f;
		}
	}
	const FString Key = Mode + TEXT("|") + Target.ToUpper();
	if (Key != LastModeKey)
	{
		LastModeKey = Key;
		LostSince = -1.0;
	}
	FadeWant = Mode == TEXT("off") ? 0.f : 1.f;
	if (Mode == TEXT("off"))
	{
		Shot = EShot::Off;
		return;
	}
	if (Mode == TEXT("forward"))
	{
		Cut(EShot::Forward, FString(), FString(), TEXT("AHEAD"), 9, 1.0);
		return;
	}
	if (Mode == TEXT("damage"))
	{
		Cut(EShot::Ship, FString(), TEXT("ASN Aquila"), TEXT("EXTERNAL"), 9, 1.0);
		return;
	}
	if (Mode == TEXT("target") || Mode == TEXT("comms"))
	{
		if (const FContact* C = FindC(Cs, Target))
		{
			Cut(EShot::Contact, C->ContactId, C->Label, Mode == TEXT("comms") ? TEXT("CHANNEL OPEN") : TEXT("ORDERED"), 9, 1.0);
			return;
		}
		// the ordered subject is gone: the screen says so (or shows where it died), then the director takes over
		if (LostSince < 0.0)
		{
			LostSince = Now;
			const FDeath* D = Deaths.FindByPredicate([&Target](const FDeath& X) { return X.Id.Equals(Target, ESearchCase::IgnoreCase) || X.Name.Contains(Target); });
			if (D)
			{
				ShotPoint = D->Pos;
				Cut(EShot::Point, D->Id, D->Name, TEXT("DESTROYED"), 9, 4.0);
				Deaths.Reset();
			}
			else
			{
				ShotWhy = FString::Printf(TEXT("%s LOST"), *Target.ToUpper());
			}
		}
		if (Now - LostSince > 4.0)
		{
			LostSince = Now + 1e7;   // once
			ReleaseOrder(FString::Printf(TEXT("%s is gone"), *Target));
		}
		return;
	}
	if (Mode == TEXT("tactical") || Mode == TEXT("fleet") || Mode == TEXT("sector"))
	{
		TArray<FString> Ids;
		for (const FContact& C : Cs)
		{
			if (C.bCraft || C.Track < 2)
			{
				continue;
			}
			const bool bWant = Mode == TEXT("fleet") ? C.Side == EAstraSide::Astra
			                 : Mode == TEXT("tactical") ? (C.Side == EAstraSide::Mandate && C.RangeKm < 90.0)
			                 : C.RangeKm < 150.0;
			if (bWant)
			{
				Ids.Add(C.ContactId);
			}
		}
		if (Ids.Num())
		{
			GroupIds = MoveTemp(Ids);
			Cut(EShot::Group, FString(), FString::Printf(TEXT("%d %s"), GroupIds.Num(), Mode == TEXT("fleet") ? TEXT("ships of the fleet") : Mode == TEXT("tactical") ? TEXT("hostiles") : TEXT("contacts")),
			    Mode.ToUpper(), 9, 1.0);
			return;
		}
		// nothing to show that way now: the director runs until there is (the order stays in force)
	}

	// --- the director: the strongest thing happening, each shot held a few seconds
	struct FCand { EShot Shot = EShot::Forward; FString Id, Name, Why; int32 Pri = 0; double Hold = 0.0; FVector Point = FVector::ZeroVector; TArray<FString> Group; };
	FCand Best;
	if (Deaths.Num())
	{
		const FDeath& D = Deaths.Last();
		Best = {EShot::Point, D.Id, D.Name, TEXT("DESTROYED"), 6, 5.0, D.Pos, {}};
	}
	else if (!HitId.IsEmpty())
	{
		Best = {EShot::Contact, HitId, HitName, TEXT("HEAVY HIT"), 5, 4.0, FVector::ZeroVector, {}};
	}
	else if (const FContact* E = FindC(Cs, Engaged))
	{
		Best = {EShot::Contact, E->ContactId, E->Label, E->Track >= 2 ? TEXT("TARGET") : TEXT("BEARING"), 4, 8.0, FVector::ZeroVector, {}};
		if (Shot == EShot::Contact && ShotId == E->ContactId && Now - ShotSince > 16.0)
		{
			// a long fight: now and then the wider picture, every hostile together, then back on the target
			TArray<FString> Hostiles;
			for (const FContact& C : Cs)
			{
				if (!C.bCraft && C.Track >= 2 && C.Side == EAstraSide::Mandate && C.RangeKm < 90.0)
				{
					Hostiles.Add(C.ContactId);
				}
			}
			if (Hostiles.Num() >= 2)
			{
				const FString Name = FString::Printf(TEXT("%d hostiles"), Hostiles.Num());
				Best = {EShot::Group, FString(), Name, TEXT("TACTICAL"), 4, 6.0, FVector::ZeroVector, MoveTemp(Hostiles)};
			}
		}
	}
	else
	{
		const FContact* Firing = Cs.FindByPredicate([](const FContact& C) { return C.Side == EAstraSide::Mandate && C.bFiringAtUs && C.Track >= 2; });
		const FContact* Near = Cs.FindByPredicate([](const FContact& C) { return C.Side == EAstraSide::Mandate && !C.bCraft && C.Track >= 2 && C.RangeKm < 90.0; });
		if (Firing)
		{
			Best = {EShot::Contact, Firing->ContactId, Firing->Label, TEXT("FIRING ON US"), 3, 7.0, FVector::ZeroVector, {}};
		}
		else if (Near)
		{
			Best = {EShot::Contact, Near->ContactId, Near->Label, TEXT("HOSTILE"), 2, 7.0, FVector::ZeroVector, {}};
		}
	}
	if (Best.Pri == 0)
	{
		// at rest: the view ahead, then the ships of the fleet one by one
		TArray<const FContact*> Fleet;
		for (const FContact& C : Cs)
		{
			if (C.Side == EAstraSide::Astra && !C.bCraft && C.Track >= 2 && C.Actor)
			{
				Fleet.Add(&C);
			}
		}
		const int32 N = Fleet.Num() + 1;
		if (ShotPri == 1 && Now >= HoldUntil)
		{
			IdleIdx = (IdleIdx + 1) % N;
		}
		IdleIdx %= N;
		if (IdleIdx == 0)
		{
			Best = {EShot::Forward, FString(), FString(), TEXT("AHEAD"), 1, 14.0, FVector::ZeroVector, {}};
		}
		else
		{
			const FContact* F = Fleet[IdleIdx - 1];
			Best = {EShot::Contact, F->ContactId, F->Label, TEXT("FLEET"), 1, 9.0, FVector::ZeroVector, {}};
		}
	}
	const bool bSame = Best.Shot == Shot && Best.Id == ShotId && (Best.Shot != EShot::Group || Shot == EShot::Group);
	if (bSame)
	{
		ShotPri = Best.Pri;          // the same subject for a new reason (a hostile that starts firing on us)
		ShotWhy = Best.Why;
		ShotName = Best.Name;
		if (Best.Shot == EShot::Group)
		{
			GroupIds = Best.Group;
		}
		return;
	}
	if ((Best.Pri > ShotPri && Now - ShotSince > 1.5) || Now >= HoldUntil || Shot == EShot::Off)
	{
		if (Best.Shot == EShot::Point)
		{
			ShotPoint = Best.Point;
			Deaths.Reset();
		}
		if (Best.Shot == EShot::Group)
		{
			GroupIds = Best.Group;
		}
		Cut(Best.Shot, Best.Id, Best.Name, Best.Why, Best.Pri, Best.Hold);
	}
}

void AAstraViewscreen::Aim(float DeltaSeconds)
{
	const UAstraBattleSubsystem* B = GetWorld() ? GetWorld()->GetSubsystem<UAstraBattleSubsystem>() : nullptr;
	if (!B)
	{
		return;
	}
	const double Aspect = (double)FeedWidth / FeedHeight;
	FVector WantDir = CamRot.GetForwardVector();      // a subject that has vanished: stay where we are
	FVector WantPos = CamPos;
	FovWant = Fov;
	bool bOrbit = false;
	// the zoom that makes a set of points fill about 60% of the frame, seen from 1 km out along Dir
	auto FitFov = [&](const FVector& Dir, const TArray<FVector>& Pts, double Margin) -> float
	{
		const FQuat R = Dir.ToOrientationQuat();
		const FVector Fw = R.GetForwardVector(), Rt = R.GetRightVector(), Up = R.GetUpVector();
		const FVector From = Dir * StandOff;
		double T = 0.0;
		for (const FVector& P : Pts)
		{
			const FVector D = P - From;
			const double X = FMath::Max(FVector::DotProduct(D, Fw), 100.0);
			T = FMath::Max3(T, FMath::Abs(FVector::DotProduct(D, Rt)) / X, FMath::Abs(FVector::DotProduct(D, Up)) / X * Aspect);
		}
		return (float)FMath::RadiansToDegrees(2.0 * FMath::Atan(T * Margin));
	};
	switch (Shot)
	{
	case EShot::Contact:
		if (const FContact* C = FindC(Contacts, ShotId))
		{
			FVector Corners[8];
			if (C->Track >= 2 && HullCorners(*C, Corners))
			{
				FVector Ctr = FVector::ZeroVector;
				for (const FVector& P : Corners) { Ctr += P; }
				WantDir = (Ctr / 8.0).GetSafeNormal();
				FovWant = FMath::Clamp(FitFov(WantDir, TArray<FVector>(Corners, 8), 1.7) / Zoom, 0.12f, 60.f);
			}
			else
			{
				// a bearing, or nothing to see yet: a wide look down the bearing
				WantDir = B->WorldOf(C->Pos).GetSafeNormal();
				FovWant = FMath::Clamp(24.f / Zoom, 2.f, 60.f);
			}
		}
		break;
	case EShot::Point:
	{
		const FVector P = B->WorldOf(ShotPoint);
		WantDir = P.GetSafeNormal();
		const double D = FMath::Max(P.Size() - StandOff, 1000.0);
		FovWant = FMath::Clamp((float)FMath::RadiansToDegrees(2.0 * FMath::Atan(45000.0 / D * 1.8)) / Zoom, 0.4f, 60.f);
		break;
	}
	case EShot::Group:
	{
		TArray<FVector> Pts;
		FVector Sum = FVector::ZeroVector;
		for (const FString& Id : GroupIds)
		{
			if (const FContact* C = FindC(Contacts, Id))
			{
				Pts.Add(B->WorldOf(C->Pos));
				Sum += Pts.Last().GetSafeNormal();
			}
		}
		if (Pts.Num())
		{
			WantDir = Sum.GetSafeNormal();
			FovWant = FMath::Clamp(FitFov(WantDir, Pts, 1.3) + 2.f, 3.f, 75.f) / Zoom;
		}
		break;
	}
	case EShot::Ship:
	{
		// around the Aquila, slowly: her hull frame is 172 m aft and 62 m below the bridge (BridgeOffset)
		const FVector Hull(-17200.f, 0.f, -6200.f);
		const double A = Now * 0.07;
		WantPos = Hull + FVector(FMath::Cos(A) * 140000.0, FMath::Sin(A) * 140000.0, 45000.0);
		WantDir = (Hull - WantPos).GetSafeNormal();
		FovWant = FMath::Clamp(38.f / Zoom, 5.f, 75.f);
		bOrbit = true;
		break;
	}
	default:
		WantDir = FVector::ForwardVector;
		FovWant = FMath::Clamp(58.f / Zoom, 5.f, 75.f);
		break;
	}
	const FQuat WantRot = WantDir.ToOrientationQuat();
	if (!bCamInit)
	{
		CamRot = FromRot = WantRot;
		Fov = FovWant;
		bCamInit = true;
	}
	if (bPushIn)
	{
		bPushIn = false;
		if (FMath::RadiansToDegrees(FromRot.AngularDistance(WantRot)) > 40.f || Shot == EShot::Ship || bOrbit)
		{
			// a big change of subject is a clean cut, a little wide, then the zoom pushes in
			PanSince = -100.0;
			Fov = FMath::Min(FovWant * 1.8f, 75.f);
		}
	}
	const double PanT = FMath::Clamp((Now - PanSince) / 0.9, 0.0, 1.0);
	CamRot = PanT < 1.0 ? FQuat::Slerp(FromRot, WantRot, FMath::SmoothStep(0.f, 1.f, (float)PanT)) : WantRot;
	CamPos = bOrbit ? WantPos : CamRot.GetForwardVector() * StandOff;
	// zoom in log space: the same pace whether x2 or x200
	Fov = FMath::Exp(FMath::Lerp(FMath::Loge(FMath::Max(Fov, 0.05f)), FMath::Loge(FMath::Max(FovWant, 0.05f)), 1.f - FMath::Exp(-2.4f * DeltaSeconds)));
	Capture->SetWorldLocationAndRotation(CamPos, CamRot);
	Capture->FOVAngle = Fov;
	// the drive plumes are sized to be seen with the naked eye from the bridge: through a zoom they would be suns
	Capture->HiddenActors.Reset();
	if (Fov < 25.f)
	{
		for (const FContact& C : Contacts)
		{
			if (C.Flare)
			{
				Capture->HiddenActors.Add(C.Flare);
			}
		}
	}
}

bool AAstraViewscreen::Project(const FVector& World, int32 W, int32 H, FVector2D& Out) const
{
	const FVector D = World - CamPos;
	const double X = FVector::DotProduct(D, CamRot.GetForwardVector());
	if (X <= 1.0)
	{
		return false;
	}
	const double F = (W * 0.5) / FMath::Tan(FMath::DegreesToRadians(Fov * 0.5));
	Out.X = W * 0.5 + FVector::DotProduct(D, CamRot.GetRightVector()) / X * F;
	Out.Y = H * 0.5 - FVector::DotProduct(D, CamRot.GetUpVector()) / X * F;
	return true;
}

void AAstraViewscreen::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	UWorld* W = GetWorld();
	Now = W->GetTimeSeconds();
	++Frame;
	if (const UAstraBattleSubsystem* B = W->GetSubsystem<UAstraBattleSubsystem>())
	{
		B->GetContacts(Contacts);
	}
	if (Frame % 8 == 0)
	{
		Direct(DeltaSeconds * 8.f);
	}
	Fade = FMath::FInterpConstantTo(Fade, FadeWant, DeltaSeconds, 1.8f);
	if (Mid)
	{
		Mid->SetScalarParameterValue(TEXT("Fade"), Fade);
	}
	if (Screen)
	{
		Screen->SetVisibility(Fade > 0.001f);
	}
	if (Fade <= 0.001f)
	{
		return;                           // off: nothing drawn, nothing captured
	}
	Aim(DeltaSeconds);
	// nobody on the bridge looking this way: the optical feed and the overlay wait (the director keeps directing)
	bWatched = true;
	if (APlayerCameraManager* PCM = UGameplayStatics::GetPlayerCameraManager(this, 0))
	{
		const FVector Eye = PCM->GetCameraLocation();
		const FVector ToScreen = GetActorLocation() + FVector(0.f, 0.f, HeightM * 50.f) - Eye;
		const bool bOnBridge = FMath::Abs(Eye.X) < 1100.0 && FMath::Abs(Eye.Y) < 1100.0 && Eye.Z > -150.0 && Eye.Z < 700.0;
		bWatched = bOnBridge && FVector::DotProduct(PCM->GetCameraRotation().Vector(), ToScreen.GetSafeNormal()) > 0.15;
	}
	// camera and overlay together (the brackets stay on the image), 30 times a second by default
	const int32 Hz = CVarViewscreenHz.GetValueOnGameThread();
	const bool bDue = Hz > 0 && Now - LastCaptureAt >= 1.0 / Hz - 0.004;
	if (bWatched && bDue)
	{
		LastCaptureAt = Now;
		Capture->CaptureScene();
		if (Overlay)
		{
			Overlay->FastUpdateResource();    // repaint only (UpdateResource re-creates the texture)
		}
	}
}

void AAstraViewscreen::DrawOverlay(UCanvas* Canvas, int32 Width, int32 Height)
{
	UWorld* W = GetWorld();
	const UAstraBattleSubsystem* B = W ? W->GetSubsystem<UAstraBattleSubsystem>() : nullptr;
	const UAstraShipSubsystem* Ship = W ? W->GetSubsystem<UAstraShipSubsystem>() : nullptr;
	const UAstraStationsSubsystem* St = W ? W->GetSubsystem<UAstraStationsSubsystem>() : nullptr;
	if (!B || !Canvas)
	{
		return;
	}
	FDraw D;
	D.C = Canvas;
	D.Mono = Mono;
	D.Title = Title;
	const float S = Height / 534.f;
	const float Top = 38.f * S, Bottom = Height - 34.f * S;
	const float PxName = 30.f * S, PxData = 20.f * S;    // read from the Captain's chair, 9 m away
	const FString Engaged = St ? St->ActionTarget() : FString();
	const FVector2D Ctr(Width * 0.5f, Height * 0.5f);
	int32 Labelled = 0, Arrows = 0;
	TMap<EAstraSide, TPair<FVector2D, int32>> CraftGroups;
	for (const FContact& C : Contacts)
	{
		const FVector World = B->WorldOf(C.Pos);
		const FLinearColor Col = C.ContactId == Engaged ? ColAlarm : SideColor(C);
		FVector2D P;
		const bool bFront = Project(World, Width, Height, P);
		const bool bOn = bFront && P.X > 8.f && P.X < Width - 8.f && P.Y > Top && P.Y < Bottom;
		if (!bOn)
		{
			// out of frame: hostile warships and the target get an arrow on the edge towards them
			if (((C.Side == EAstraSide::Mandate && !C.bCraft) || C.ContactId == Engaged) && Arrows < 8)
			{
				++Arrows;
				const FVector Dl = CamRot.UnrotateVector(World - CamPos);
				FVector2D Dir(Dl.Y, -Dl.Z);
				Dir = Dir.IsNearlyZero() ? FVector2D(1.f, 0.f) : Dir.GetSafeNormal();
				const FVector2D Half(Width * 0.5f - 30.f * S, (Bottom - Top) * 0.5f - 20.f * S);
				const float K = FMath::Min(Half.X / FMath::Max(FMath::Abs(Dir.X), 1e-3f), Half.Y / FMath::Max(FMath::Abs(Dir.Y), 1e-3f));
				const FVector2D Mid2(Ctr.X, (Top + Bottom) * 0.5f);
				const FVector2D Tip = Mid2 + Dir * K;
				const FVector2D Side(-Dir.Y, Dir.X);
				D.Line(Tip, Tip - Dir * 16.f * S + Side * 8.f * S, Col, 2.f);
				D.Line(Tip, Tip - Dir * 16.f * S - Side * 8.f * S, Col, 2.f);
				const FString Tag = C.RangeKm >= 0.0 ? FString::Printf(TEXT("%s %.0f km"), *C.ContactId, C.RangeKm) : C.ContactId;
				const FVector2D At = Tip - Dir * 30.f * S;
				D.Text(At.X, At.Y - PxData * 0.5f, Tag, true, PxData, Col, Dir.X > 0.3f ? 2 : (Dir.X < -0.3f ? 0 : 1));
			}
			continue;
		}
		if (C.Track < 2)
		{
			// a bearing only: a dashed line down the bearing, no box (we don't know how far)
			for (float y = FMath::Max(Top, P.Y - 70.f * S); y < FMath::Min(Bottom, P.Y + 70.f * S); y += 16.f * S)
			{
				D.Line(FVector2D(P.X, y), FVector2D(P.X, y + 8.f * S), Col, 1.2f);
			}
			D.Text(P.X + 8.f * S, P.Y - 70.f * S, FString::Printf(TEXT("%s  BRG %03.0f  NO RANGE%s"), *C.ContactId, C.BearingDeg, C.bJamming ? TEXT("  JAMMING") : TEXT("")), true, PxData, Col);
			continue;
		}
		// the box: the hull's corners as the camera sees them (a small square when too far to tell)
		FBox2D R(ForceInit);
		FVector Corners[8];
		if (HullCorners(C, Corners))
		{
			for (const FVector& Cn : Corners)
			{
				FVector2D Q;
				if (Project(Cn, Width, Height, Q))
				{
					R += Q;
				}
			}
		}
		const float MinHalf = (C.bCraft ? 6.f : 11.f) * S;
		if (!R.bIsValid || R.GetExtent().GetMax() < MinHalf)
		{
			R = FBox2D(P - FVector2D(MinHalf, MinHalf), P + FVector2D(MinHalf, MinHalf));
		}
		R = R.ExpandBy(4.f * S);
		if (C.bCraft)
		{
			D.Brackets(R, Dimmed(Col, 0.85f), 1.2f);
			TPair<FVector2D, int32>& G = CraftGroups.FindOrAdd(C.Side);
			G.Key += P;
			G.Value++;
			continue;                     // fighters: a small box; one label per wing below
		}
		D.Brackets(R, Col, C.ContactId == Engaged ? 2.4f : 1.8f);
		if (C.ContactId == Engaged && R.GetExtent().GetMax() < Height * 0.3f)
		{
			D.Ring(R.GetCenter(), R.GetExtent().GetMax() * 1.25f + 8.f * S, ColAlarm, (float)Now * 0.7f);   // not around a ship that fills the frame
		}
		if (Labelled >= 6 && C.ContactId != Engaged)
		{
			D.Text(R.Max.X + 6.f * S, R.Min.Y, C.ContactId, true, PxData, Dimmed(Col, 0.8f));
			continue;                     // a crowded screen: names only for the nearest few and the target
		}
		++Labelled;
		// the label: name, class, range and speed, hull and shields; on the left when the right has no room
		const FString Name = C.Label.ToUpper();
		FString Kind = C.Class;
		Kind.RemoveFromStart(TEXT("Kharon Mandate "));
		Kind.RemoveFromStart(TEXT("ASTRA "));
		Kind.RemoveFromStart(TEXT("Free Guilds "));
		const FString Cls = Kind.IsEmpty() ? FString::Printf(TEXT("%s  UNCLASSIFIED"), *C.ContactId) : FString::Printf(TEXT("%s  %s"), *C.ContactId, *Kind);
		const FString Kin = FString::Printf(TEXT("%.1f km   %.0f m/s"), C.RangeKm, C.Vel.Size());
		const float Bw = 110.f * S;
		const float BlockW = FMath::Max3(D.Width(Name, false, PxName), D.Width(Cls, true, PxData), FMath::Max(D.Width(Kin, true, PxData), Bw));
		// the side with more room; always whole on the screen (over the hull when the ship fills the frame)
		const bool bLeft = R.Max.X + 10.f * S + BlockW > Width - 8.f && R.Min.X > Width - R.Max.X;
		const float X = bLeft ? FMath::Max(R.Min.X - 10.f * S, BlockW + 12.f * S) : FMath::Min(R.Max.X + 10.f * S, Width - BlockW - 12.f * S);
		const int32 Al = bLeft ? 2 : 0;
		float Y = FMath::Clamp((float)R.Min.Y - 4.f * S, Top + 4.f * S, Bottom - 104.f * S);
		D.Text(X, Y, Name, false, PxName, Col, Al);
		Y += PxName * 1.08f;
		D.Text(X, Y, Cls, true, PxData, Dimmed(Col, 0.78f), Al);
		Y += PxData * 1.25f;
		D.Text(X, Y, Kin, true, PxData, Dimmed(Col, 0.78f), Al);
		Y += PxData * 1.45f;
		if (C.HullFrac >= 0.f)
		{
			const float Bx = bLeft ? X - Bw : X;
			D.Bar(Bx, Y, Bw, C.HullFrac, C.HullFrac < 0.35f ? ColAlarm : Col);
			D.Bar(Bx, Y + 7.f * S, Bw, FMath::Max(0.f, C.ShieldFrac), ColAstra);
			Y += 16.f * S;
		}
		FString Tags;
		if (C.ContactId == Engaged) { Tags += TEXT("ENGAGED   "); }
		if (C.bFiringAtUs) { Tags += TEXT("FIRING ON US   "); }
		if (C.bFleeing) { Tags += TEXT("RUNNING   "); }
		if (C.bJamming) { Tags += TEXT("JAMMING"); }
		if (!Tags.IsEmpty())
		{
			D.Text(X, Y, Tags.TrimEnd(), true, PxData, ColAlarm, Al);
		}
	}
	for (const auto& KV : CraftGroups)
	{
		const FVector2D At = KV.Value.Key / KV.Value.Value;
		const FLinearColor Col = KV.Key == EAstraSide::Astra ? ColAstra : KV.Key == EAstraSide::Mandate ? ColMandate : ColNeutral;
		D.Text(At.X, FMath::Min(At.Y + 18.f * S, Bottom - PxData * 1.2f), FString::Printf(TEXT("%s CRAFT x%d"), KV.Key == EAstraSide::Astra ? TEXT("ASTRA") : KV.Key == EAstraSide::Mandate ? TEXT("MANDATE") : TEXT("UNKNOWN"), KV.Value.Value),
		       true, PxData, Dimmed(Col, 0.85f), 1);
	}
	// missiles coming at us
	TArray<FVector> Missiles;
	B->GetInboundMissiles(Missiles);
	for (const FVector& M : Missiles)
	{
		FVector2D P;
		if (Project(B->WorldOf(M), Width, Height, P))
		{
			const float r = 6.f * S;
			D.Line(P + FVector2D(0, -r), P + FVector2D(r, 0), ColAlarm, 1.8f);
			D.Line(P + FVector2D(r, 0), P + FVector2D(0, r), ColAlarm, 1.8f);
			D.Line(P + FVector2D(0, r), P + FVector2D(-r, 0), ColAlarm, 1.8f);
			D.Line(P + FVector2D(-r, 0), P + FVector2D(0, -r), ColAlarm, 1.8f);
		}
	}
	// the bars: what is on screen and why (top), the Aquila (bottom)
	D.Tile(0.f, 0.f, Width, Top, FLinearColor(0.f, 0.f, 0.f, 0.42f));
	D.Tile(0.f, Bottom, Width, Height - Bottom, FLinearColor(0.f, 0.f, 0.f, 0.42f));
	D.Line(FVector2D(0.f, Top), FVector2D(Width, Top), Dimmed(ColDim, 0.7f), 1.f);
	D.Line(FVector2D(0.f, Bottom), FVector2D(Width, Bottom), Dimmed(ColDim, 0.7f), 1.f);
	const float Ty = (Top - PxData) * 0.5f;
	D.Text(16.f * S, Ty, FString::Printf(TEXT("MAIN VIEWSCREEN  ·  %s"), *Mode.ToUpper()), true, PxData, ColDim);
	FString Caption;
	switch (Shot)
	{
	case EShot::Contact: Caption = FString::Printf(TEXT("%s  ·  %s"), *ShotWhy, *ShotName.ToUpper()); break;
	case EShot::Group: Caption = FString::Printf(TEXT("%s  ·  %s"), *ShotWhy, *ShotName.ToUpper()); break;
	case EShot::Point: Caption = FString::Printf(TEXT("%s DESTROYED"), *ShotName.ToUpper()); break;
	case EShot::Ship: Caption = FString::Printf(TEXT("ASN AQUILA  ·  HULL %.0f%%"), 100.f * B->PlayerHullFraction()); break;
	default: Caption = ShotWhy; break;
	}
	D.Text(Width * 0.5f, (Top - PxName) * 0.5f, Caption, false, PxName, ShotPri >= 5 ? ColAlarm : ColText, 1);
	D.Text(Width - 16.f * S, Ty, FString::Printf(TEXT("x%.0f   FOV %.1f°"), 58.f / FMath::Max(Fov, 0.05f), Fov), true, PxData, ColDim, 2);
	const float By = Bottom + (Height - Bottom - PxData) * 0.5f;
	if (Missiles.Num())
	{
		D.Text(16.f * S, By, FString::Printf(TEXT(">> %d MISSILE%s INBOUND"), Missiles.Num(), Missiles.Num() > 1 ? TEXT("S") : TEXT("")), true, PxData, ColAlarm);
	}
	else
	{
		int32 Hostile = 0, Friendly = 0;
		for (const FContact& C : Contacts)
		{
			Hostile += C.Side == EAstraSide::Mandate && !C.bCraft;
			Friendly += C.Side == EAstraSide::Astra && !C.bCraft;
		}
		D.Text(16.f * S, By, FString::Printf(TEXT("PLOT  %d HOSTILE  ·  %d FRIENDLY  ·  %d CONTACTS"), Hostile, Friendly, Contacts.Num()), true, PxData, ColDim);
	}
	if (Ship)
	{
		D.Text(Width - 16.f * S, By, FString::Printf(TEXT("AQUILA  HULL %.0f%%   SHIELDS %.0f%% %s   HEAT %.0f%%"), 100.f * B->PlayerHullFraction(),
		                                              100.f * B->PlayerShieldFraction(), *Ship->GetShieldMode().ToUpper(), Ship->GetHeatPct()),
		       true, PxData, ColDim, 2);
	}
	D.Flush();
}

bool AAstraViewscreen::Dump(const FString& Path) const
{
	FTextureRenderTargetResource* FR = Feed ? Feed->GameThread_GetRenderTargetResource() : nullptr;
	FTextureRenderTargetResource* OR = Overlay ? Overlay->GameThread_GetRenderTargetResource() : nullptr;
	TArray<FColor> Fp, Op;
	if (!FR || !OR || !FR->ReadPixels(Fp) || !OR->ReadPixels(Op) || Fp.Num() != Op.Num() || Fp.Num() != FeedWidth * FeedHeight)
	{
		return false;
	}
	// as the material composes it: feed * overlay alpha + overlay colour
	for (int32 i = 0; i < Fp.Num(); ++i)
	{
		const float K = Op[i].A / 255.f;
		Fp[i] = FColor((uint8)FMath::Min(255.f, Fp[i].R * K + Op[i].R), (uint8)FMath::Min(255.f, Fp[i].G * K + Op[i].G),
		               (uint8)FMath::Min(255.f, Fp[i].B * K + Op[i].B), 255);
	}
	TArray64<uint8> Png;
	FImageUtils::PNGCompressImageArray(FeedWidth, FeedHeight, TArrayView64<const FColor>(Fp.GetData(), Fp.Num()), Png);
	return Png.Num() > 0 && FFileHelper::SaveArrayToFile(Png, *Path);
}

void AAstraViewscreen::LogWhatIsInView() const
{
	const FVector Fwd = CamRot.GetForwardVector();
	const double HalfTan = FMath::Tan(FMath::DegreesToRadians(Fov * 0.5)) * 1.2;   // a little wider than the frame
	TArray<TPair<double, FString>> Seen;
	for (TActorIterator<AActor> It(GetWorld()); It; ++It)
	{
		if (It->IsHidden() || *It == this)
		{
			continue;
		}
		TArray<UPrimitiveComponent*> Prims;
		It->GetComponents<UPrimitiveComponent>(Prims);
		for (const UPrimitiveComponent* P : Prims)
		{
			if (!P || !P->IsVisible() || !P->IsRegistered())
			{
				continue;
			}
			const FBoxSphereBounds& B = P->Bounds;
			const FVector D = B.Origin - CamPos;
			const double X = FVector::DotProduct(D, Fwd);
			const double Lat = (D - Fwd * X).Size();
			// the bounds sphere touches the cone of the view (or contains the camera)
			if (D.Size() < B.SphereRadius || (X > -B.SphereRadius && Lat - B.SphereRadius < FMath::Max(X, 0.0) * HalfTan))
			{
				Seen.Add({FMath::Max(0.0, D.Size() - B.SphereRadius), FString::Printf(TEXT("%s.%s (%s, r %.0f m)"), *It->GetName(), *P->GetName(),
				                                                                        *P->GetClass()->GetName(), B.SphereRadius / 100.0)});
			}
		}
	}
	Seen.Sort([](const TPair<double, FString>& L, const TPair<double, FString>& R) { return L.Key < R.Key; });
	UE_LOG(LogASTRA, Display, TEXT("[Viewscreen] in view (FOV %.2f, %s): %d"), Fov, *Describe(), Seen.Num());
	for (int32 i = 0; i < FMath::Min(Seen.Num(), 40); ++i)
	{
		UE_LOG(LogASTRA, Display, TEXT("[Viewscreen]   %8.1f km  %s"), Seen[i].Key / 100000.0, *Seen[i].Value);
	}
}
