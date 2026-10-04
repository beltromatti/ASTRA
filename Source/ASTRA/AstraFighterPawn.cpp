// ASTRA — the Captain at the stick of a Falcon.

#include "AstraFighterPawn.h"
#include "Components/PointLightComponent.h"
#include "Fonts/FontMeasure.h"

#include "ASTRA.h"
#include "AstraHangar.h"
#include "AstraShipSubsystem.h"
#include "AstraSpaceLife.h"
#include "Camera/CameraComponent.h"
#include "Camera/PlayerCameraManager.h"
#include "Components/AudioComponent.h"
#include "Components/InputComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/Font.h"
#include "Engine/GameViewportClient.h"
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshActor.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Engine/World.h"
#include "Fonts/SlateFontInfo.h"
#include "Framework/Application/SlateApplication.h"
#include "GameFramework/PlayerController.h"
#include "Kismet/GameplayStatics.h"
#include "Rendering/DrawElements.h"
#include "Sound/SoundBase.h"
#include "Styling/CoreStyle.h"
#include "Widgets/SLeafWidget.h"

// ------------------------------------------------------------------------------------------------ head-up display
/** The Falcon's head-up display, projected on the canopy: reticle, the stick, brackets on hostiles, the lock and the
 *  lead for the cannons, the way home, speed and throttle, hull, shields, missiles. Positions are normalised (0..1). */
class SAstraFlightHud : public SLeafWidget
{
public:
	SLATE_BEGIN_ARGS(SAstraFlightHud) {}
	SLATE_END_ARGS()

	struct FData
	{
		FString Hint;
		FVector2D Stick = FVector2D::ZeroVector;
		float Speed = 0.f, Throttle = 0.f, Hull = 100.f, Shield = 100.f;
		int32 Missiles = 0, Decoys = 0;
		bool bBoost = false, bFlying = false;
		TArray<FVector2D> Hostiles;
		TArray<float> HostileBox;
		TArray<FVector2D> Friends;
		bool bLock = false, bLockOn = false, bLead = false;
		FVector2D LockPos = FVector2D::ZeroVector, LeadPos = FVector2D::ZeroVector;
		float LockProgress = 0.f;
		FString LockText;
		bool bHomeOn = false, bHomeEdge = false;
		FVector2D HomePos = FVector2D::ZeroVector;
		float HomeEdgeAngle = 0.f;
		FString HomeText;
		// the datalink's picture (the Aquila's plot) on the canopy: ships bracketed and named, craft as diamonds
		struct FMark
		{
			FVector2D Pos = FVector2D::ZeroVector;   // normalised
			float Box = 10.f;                        // px at 1080p (half size)
			FString Name, Sub;
			bool bCraft = false, bCapital = false;
			bool bPod = false;                       // a lifepod adrift (SPAZIO-VIVO): a ring and a cross, named before the craft
			bool bReach = false;                     // ... and within her grapples' reach: a second ring (R takes it aboard)
			int32 Side = 0;                          // 0 unknown, 1 friend, 2 foe, 3 neutral
		};
		TArray<FMark> Marks;
		struct FEdge { float Angle = 0.f; FString Text; bool bFoe = true; };
		TArray<FEdge> Edges;                         // threats out of view: arrows on a ring around the reticle
		float Plasma = 0.f;          // the entry's glow over everything
		bool bPlanet = false;        // over New Ravenna: altitude instead of weapons
		float Alt = 0.f, AGL = 0.f;
	};
	FData Data;

	void Construct(const FArguments&)
	{
		UFont* Mono = LoadObject<UFont>(nullptr, TEXT("/Game/ASTRA/UI/Fonts/F_ASTRA_Mono.F_ASTRA_Mono"));
		Font = Mono ? FSlateFontInfo(Mono, 16) : FCoreStyle::GetDefaultFontStyle("Mono", 16);
		Small = Mono ? FSlateFontInfo(Mono, 12) : FCoreStyle::GetDefaultFontStyle("Mono", 12);
	}

	virtual FVector2D ComputeDesiredSize(float) const override { return FVector2D(100.f, 100.f); }

	virtual int32 OnPaint(const FPaintArgs& Args, const FGeometry& G, const FSlateRect& Clip, FSlateWindowElementList& Out, int32 Layer,
	                      const FWidgetStyle& Style, bool bParentEnabled) const override
	{
		const FVector2D Size = G.GetLocalSize();
		const FVector2D C = Size * 0.5;
		const FLinearColor Ink(0.45f, 1.f, 0.85f, 0.85f), Dim(0.45f, 1.f, 0.85f, 0.35f), Warn(1.f, 0.7f, 0.2f, 0.95f), Foe(1.f, 0.42f, 0.3f, 0.9f);
		const float U = Size.Y / 1080.f;   // design unit: 1 px at 1080p
		auto Lines = [&](const TArray<FVector2D>& P, const FLinearColor& Col, float W = 1.5f)
		{
			FSlateDrawElement::MakeLines(Out, Layer, G.ToPaintGeometry(), P, ESlateDrawEffect::None, Col, true, W * FMath::Max(1.f, U));
		};
		auto Circle = [&](const FVector2D& At, float R, const FLinearColor& Col, float W = 1.5f, float From = 0.f, float To = 1.f)
		{
			TArray<FVector2D> P;
			const int32 N = 32;
			for (int32 i = 0; i <= N; ++i)
			{
				const float A = 2.f * PI * (From + (To - From) * i / N) - PI / 2;
				P.Add(At + FVector2D(FMath::Cos(A), FMath::Sin(A)) * R);
			}
			Lines(P, Col, W);
		};
		auto Text = [&](const FVector2D& At, const FString& S, const FLinearColor& Col, bool bSmall = false)
		{
			// a dark halo under the glyphs keeps them legible against a sunlit hull or a planet
			FSlateDrawElement::MakeText(Out, Layer + 1, G.ToPaintGeometry(FVector2D(900.f, 40.f), FSlateLayoutTransform(At + FVector2D(1.5f, 1.5f))), S,
			                            bSmall ? Small : Font, ESlateDrawEffect::None, FLinearColor(0.f, 0.f, 0.f, 0.65f * Col.A));
			FSlateDrawElement::MakeText(Out, Layer + 2, G.ToPaintGeometry(FVector2D(900.f, 40.f), FSlateLayoutTransform(At)), S,
			                            bSmall ? Small : Font, ESlateDrawEffect::None, Col);
		};
		auto Bracket = [&](const FVector2D& At, float H, const FLinearColor& Col)
		{
			const float L = H * 0.45f;
			for (const FVector2D& Sg : {FVector2D(-1, -1), FVector2D(1, -1), FVector2D(1, 1), FVector2D(-1, 1)})
			{
				const FVector2D Corner = At + Sg * H;
				Lines({Corner - FVector2D(Sg.X * L, 0), Corner, Corner - FVector2D(0, Sg.Y * L)}, Col);
			}
		};
		if (Data.Plasma > 0.001f)
		{
			// the entry: the air burning around the canopy — rings of glow crowding in from the edges, orange turning
			// white, until at its height the whole view is fire
			const FSlateBrush* White = FCoreStyle::Get().GetBrush("WhiteBrush");
			const FLinearColor Glow = FMath::Lerp(FLinearColor(1.f, 0.42f, 0.12f, 1.f), FLinearColor(1.f, 0.88f, 0.75f, 1.f), Data.Plasma);
			const int32 Rings = 14;
			for (int32 k = 0; k < Rings; ++k)
			{
				const float In0 = 0.5f * k / Rings, In1 = 0.5f * (k + 1) / Rings;
				const float A = Data.Plasma * FMath::Square(1.f - (float)k / Rings) * 0.55f;
				if (A < 0.01f)
				{
					continue;
				}
				const FVector2D P0 = Size * In0, P1 = Size * (1.f - In0), Q0 = Size * In1, Q1 = Size * (1.f - In1);
				const FLinearColor Cc(Glow.R, Glow.G, Glow.B, A);
				auto Rect = [&](const FVector2D& From, const FVector2D& To)
				{
					FSlateDrawElement::MakeBox(Out, Layer, G.ToPaintGeometry(To - From, FSlateLayoutTransform(From)), White, ESlateDrawEffect::None, Cc);
				};
				Rect(P0, FVector2D(P1.X, Q0.Y));                  // top band
				Rect(FVector2D(P0.X, Q1.Y), P1);                  // bottom band
				Rect(FVector2D(P0.X, Q0.Y), FVector2D(Q0.X, Q1.Y));   // left
				Rect(FVector2D(Q1.X, Q0.Y), FVector2D(P1.X, Q1.Y));   // right
			}
			const float Core = FMath::Clamp((Data.Plasma - 0.55f) * 2.2f, 0.f, 1.f);
			if (Core > 0.f)
			{
				FSlateDrawElement::MakeBox(Out, Layer, G.ToPaintGeometry(), White, ESlateDrawEffect::None, FLinearColor(Glow.R, Glow.G, Glow.B, Core));
			}
		}
		if (!Data.Hint.IsEmpty())
		{
			const bool bAlarm = Data.Hint.StartsWith(TEXT("MISSILE")) || Data.Hint.StartsWith(TEXT("HULL")) || Data.Hint.StartsWith(TEXT("COLLISION"));
			const bool bCaution = Data.Hint.StartsWith(TEXT("PROXIMITY"));         // (a hull close: amber, steady)
			const bool bBlink = !bAlarm || FMath::Fmod(FPlatformTime::Seconds(), 0.8) < 0.5;
			if (bBlink)
			{
				Text(FVector2D(C.X - 300.f * U, Size.Y * 0.3f), Data.Hint, (bAlarm || bCaution) ? Warn : Ink);
			}
		}
		if (!Data.bFlying)
		{
			return Layer + 3;
		}
		// the reticle and the stick
		Circle(C, 14.f * U, Ink);
		Lines({C + FVector2D(-26, 0) * U, C + FVector2D(-16, 0) * U}, Ink);
		Lines({C + FVector2D(16, 0) * U, C + FVector2D(26, 0) * U}, Ink);
		Lines({C + FVector2D(0, 16) * U, C + FVector2D(0, 24) * U}, Ink);
		Circle(C, 150.f * U, Dim, 1.f);
		const FVector2D StickAt = C + Data.Stick * 150.f * U;
		Circle(StickAt, 5.f * U, Ink, 2.f);
		if (Data.Stick.Size() > 0.05f)
		{
			Lines({C + Data.Stick.GetSafeNormal() * 14.f * U, StickAt}, Dim, 1.f);
		}
		// who is out there: the datalink's picture
		const FLinearColor Friend(0.45f, 0.8f, 1.f, 0.85f), Neutral(1.f, 0.9f, 0.4f, 0.8f), Unknown(0.75f, 0.78f, 0.8f, 0.7f);
		// the marks first, then their names, the foes' warships first and the nearest of each kind before the farther, each where it
		// covers nothing already written (up-right, up-left, down-right, down-left of its mark): a group seen along one line of sight
		// wrote its names on top of each other
		TArray<FSlateRect> Taken;
		TArray<int32> Named;
		for (int32 i = 0; i < Data.Marks.Num(); ++i)
		{
			const FData::FMark& M = Data.Marks[i];
			const FLinearColor Col = M.Side == 2 ? Foe : (M.Side == 1 ? Friend : (M.Side == 3 ? Neutral : Unknown));
			const FVector2D At = M.Pos * Size;
			const float H = (M.bPod ? 8.f : (M.bCraft ? 6.f : M.Box)) * U;
			if (M.bPod)
			{
				// a lifepod: a ring with a cross in it (a second, larger ring when it is within the grapples' reach: R)
				Circle(At, H, Col, 1.5f);
				Lines({At + FVector2D(-H * 0.5f, 0.f), At + FVector2D(H * 0.5f, 0.f)}, Col, 1.5f);
				Lines({At + FVector2D(0.f, -H * 0.5f), At + FVector2D(0.f, H * 0.5f)}, Col, 1.5f);
				if (M.bReach)
				{
					Circle(At, H * 1.9f, Warn, 2.f);
				}
			}
			else if (M.bCraft)
			{
				Lines({At + FVector2D(0, -H), At + FVector2D(H, 0), At + FVector2D(0, H), At + FVector2D(-H, 0), At + FVector2D(0, -H)}, Col, 1.5f);
			}
			else
			{
				Bracket(At, H, Col);
			}
			Taken.Add(FSlateRect(At.X - H, At.Y - H, At.X + H, At.Y + H));
			if (!M.Name.IsEmpty())
			{
				Named.Add(i);
			}
		}
		Named.Sort([this](int32 A, int32 B)
		{
			const FData::FMark& Ma = Data.Marks[A];
			const FData::FMark& Mb = Data.Marks[B];
			const int32 Ra = Ma.bPod ? -1 : (Ma.Side == 2 ? 0 : 2) + (Ma.bCraft ? 1 : 0), Rb = Mb.bPod ? -1 : (Mb.Side == 2 ? 0 : 2) + (Mb.bCraft ? 1 : 0);   // (the lifepods first: someone is waiting in them)
			return Ra != Rb ? Ra < Rb : Ma.Box > Mb.Box;
		});
		const TSharedRef<FSlateFontMeasure> Measure = FSlateApplication::Get().GetRenderer()->GetFontMeasureService();
		for (const int32 i : Named)
		{
			const FData::FMark& M = Data.Marks[i];
			const FLinearColor Col = M.Side == 2 ? Foe : (M.Side == 1 ? Friend : (M.Side == 3 ? Neutral : Unknown));
			const FVector2D At = M.Pos * Size;
			const float Off = (M.bCraft ? 9.f : M.Box + 6.f) * U;
			const FVector2D NameSz = Measure->Measure(M.Name, Small);
			const FVector2D SubSz = M.Sub.IsEmpty() ? FVector2D::ZeroVector : Measure->Measure(M.Sub, Small);
			const FVector2D Block(FMath::Max(NameSz.X, SubSz.X), M.Sub.IsEmpty() ? NameSz.Y : 15.f * U + SubSz.Y);
			const FVector2D Tries[4] = {At + FVector2D(Off, -Off), At + FVector2D(-Off - Block.X, -Off), At + FVector2D(Off, Off - Block.Y * 0.3f),
			                            At + FVector2D(-Off - Block.X, Off - Block.Y * 0.3f)};
			for (const FVector2D& T : Tries)
			{
				const FSlateRect R(T.X - 2.f, T.Y - 2.f, T.X + Block.X + 2.f, T.Y + Block.Y + 2.f);
				bool bClear = R.Left > 2.f && R.Top > 2.f && R.Right < Size.X - 2.f && R.Bottom < Size.Y - 2.f;
				for (int32 k = 0; k < Taken.Num() && bClear; ++k)
				{
					bClear = !FSlateRect::DoRectanglesIntersect(R, Taken[k]);
				}
				if (!bClear)
				{
					continue;
				}
				Taken.Add(R);
				Text(T, M.Name, Col, true);
				if (!M.Sub.IsEmpty())
				{
					Text(T + FVector2D(0.f, 15.f * U), M.Sub, FLinearColor(Col.R, Col.G, Col.B, Col.A * 0.75f), true);
				}
				break;
			}
		}
		for (const FData::FEdge& E : Data.Edges)
		{
			// threats in the same quarter would write on top of each other: the arrow stays on the ring, its words stack in a
			// column beside it until clear
			const FVector2D Dir(FMath::Cos(E.Angle), FMath::Sin(E.Angle));
			const FVector2D N(-Dir.Y, Dir.X);
			const FLinearColor Col = E.bFoe ? Foe : Friend;
			const FVector2D TextSz = Measure->Measure(E.Text, Small);
			const FVector2D P = C + Dir * 330.f * U;
			Lines({P - Dir * 12.f * U + N * 9.f * U, P + Dir * 6.f * U, P - Dir * 12.f * U - N * 9.f * U}, Col, 2.f);
			for (int32 Step = 0; Step < 6; ++Step)
			{
				const FVector2D At = P + Dir * 14.f * U + FVector2D(-20.f, -8.f + (TextSz.Y / FMath::Max(U, 0.01f) + 3.f) * (Step % 2 ? (Step + 1) / 2 : -(Step / 2))) * U;
				const FSlateRect R(At.X - 2.f, At.Y - 2.f, At.X + TextSz.X + 2.f, At.Y + TextSz.Y + 2.f);
				bool bClear = true;
				for (int32 k = 0; k < Taken.Num() && bClear; ++k)
				{
					bClear = !FSlateRect::DoRectanglesIntersect(R, Taken[k]);
				}
				if (!bClear)
				{
					continue;                // (six places taken: the arrow alone says where)
				}
				Taken.Add(R);
				Text(At, E.Text, Col, true);
				break;
			}
		}
		// the lock and the lead
		if (Data.bLock)
		{
			const FVector2D L = Data.LockPos * Size;
			const float H = 30.f * U;
			Lines({L + FVector2D(-H, -H), L + FVector2D(H, -H), L + FVector2D(H, H), L + FVector2D(-H, H), L + FVector2D(-H, -H)},
			      Data.bLockOn ? Warn : Ink, Data.bLockOn ? 2.5f : 1.5f);
			if (!Data.bLockOn)
			{
				Circle(L, H * 1.4f, Ink, 2.f, 0.f, Data.LockProgress);
			}
			Text(L + FVector2D(H + 6.f * U, -H), Data.LockText, Data.bLockOn ? Warn : Ink, true);
		}
		if (Data.bLead)
		{
			const FVector2D P = Data.LeadPos * Size;
			const float D = 7.f * U;
			Lines({P + FVector2D(0, -D), P + FVector2D(D, 0), P + FVector2D(0, D), P + FVector2D(-D, 0), P + FVector2D(0, -D)}, Ink, 2.f);
		}
		// the way home
		if (Data.bHomeOn)
		{
			const FVector2D P = Data.HomePos * Size;
			Lines({P + FVector2D(-12, -8) * U, P + FVector2D(0, 4) * U, P + FVector2D(12, -8) * U}, Ink, 2.f);
			Text(P + FVector2D(-40.f, 10.f) * U, Data.HomeText, Ink, true);
		}
		else if (Data.bHomeEdge)
		{
			const FVector2D Dir(FMath::Cos(Data.HomeEdgeAngle), FMath::Sin(Data.HomeEdgeAngle));
			const FVector2D P = C + Dir * 240.f * U;
			const FVector2D N(-Dir.Y, Dir.X);
			Lines({P - Dir * 10.f * U + N * 8.f * U, P + Dir * 6.f * U, P - Dir * 10.f * U - N * 8.f * U}, Ink, 2.f);
			Text(P + FVector2D(14.f, -6.f) * U, Data.HomeText, Dim, true);
		}
		// the instruments: speed and throttle (left), hull, shields and missiles (right)
		const FVector2D LB(C.X - 470.f * U, C.Y + 170.f * U), RB(C.X + 360.f * U, C.Y + 170.f * U);
		Text(LB, FString::Printf(TEXT("SPD %4.0f m/s%s"), Data.Speed, Data.bBoost ? TEXT("  BOOST") : TEXT("")), Ink);
		Lines({LB + FVector2D(0, 30) * U, LB + FVector2D(120, 30) * U}, Dim, 4.f);
		Lines({LB + FVector2D(0, 30) * U, LB + FVector2D(120.f * Data.Throttle, 30.f) * U}, Ink, 4.f);
		Text(LB + FVector2D(0, 38) * U, TEXT("THR"), Dim, true);
		if (Data.bPlanet)
		{
			Text(RB, FString::Printf(TEXT("ALT %6.0f m"), Data.Alt), Ink);
			Text(RB + FVector2D(0, 22) * U, FString::Printf(TEXT("AGL %6.0f m"), FMath::Min(Data.AGL, 99999.f)), Data.AGL < 60.f ? Warn : Ink);
			return Layer + 3;
		}
		const FLinearColor HullCol = Data.Hull < 35.f ? Warn : Ink;
		Text(RB, FString::Printf(TEXT("HULL %3.0f%%"), Data.Hull), HullCol);
		Text(RB + FVector2D(0, 22) * U, FString::Printf(TEXT("SHLD %3.0f%%"), Data.Shield), Data.Shield < 20.f ? Warn : Ink);
		Text(RB + FVector2D(0, 44) * U, FString::Printf(TEXT("MSL  %d"), Data.Missiles), Data.Missiles == 0 ? Dim : Ink);
		Text(RB + FVector2D(0, 66) * U, FString::Printf(TEXT("DCY  %d"), Data.Decoys), Data.Decoys == 0 ? Dim : Ink);
		return Layer + 3;
	}

private:
	FSlateFontInfo Font, Small;
};

// ------------------------------------------------------------------------------------------------ the pawn
AAstraFighterPawn::AAstraFighterPawn()
{
	PrimaryActorTick.bCanEverTick = true;
	Root = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	SetRootComponent(Root);
	Cockpit = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Cockpit"));
	Cockpit->SetupAttachment(Root);
	Cockpit->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Cockpit->SetCastShadow(true);                       // the canopy frame's shadow sweeps the cockpit as she rolls
	Cockpit->bCastDynamicShadow = true;
	// (the cockpit's mesh is loaded when she launches, BeginOnCatapult, not here: a mesh the class default object loads stays loaded for the
	// whole session with every material it uses, and those are rooted for good - the editor could no longer rebuild M_ASTRA_Screen,
	// DeleteMaterialExpression asserts on a rooted expression)
	Camera = CreateDefaultSubobject<UCameraComponent>(TEXT("Camera"));
	Camera->SetupAttachment(Root);
	Camera->bUsePawnControlRotation = false;
	Camera->SetFieldOfView(88.f);
	// the instruments' own glow on the pilot's side of the cockpit: with the star behind her the seat and the consoles read black (ARTE-PLANCIA-2);
	// a faint warm fill under the hood, no shadows (a moving shadow-casting light in the pilot's face costs and flickers)
	CockpitFill = CreateDefaultSubobject<UPointLightComponent>(TEXT("CockpitFill"));
	CockpitFill->SetupAttachment(Root);
	CockpitFill->SetRelativeLocation(FVector(55.f, 0.f, -30.f));    // ahead of the eye and below it: the dash's screens
	CockpitFill->SetIntensityUnits(ELightUnits::Candelas);
	CockpitFill->SetIntensity(1.6f);
	CockpitFill->SetAttenuationRadius(160.f);
	CockpitFill->SetLightColor(FLinearColor(1.f, 0.82f, 0.62f));
	CockpitFill->SetCastShadows(false);
	CockpitFill->SetSourceRadius(12.f);
	AutoPossessPlayer = EAutoReceiveInput::Disabled;
}

void AAstraFighterPawn::BeginOnCatapult(AAstraHangar* InHangar, APawn* InWalker)
{
	if (!Cockpit->GetStaticMesh())
	{
		Cockpit->SetStaticMesh(LoadObject<UStaticMesh>(nullptr, TEXT("/Game/ASTRA/Ships/Cockpit/SM_CRAFT_ASTRA_Falcon_Cockpit.SM_CRAFT_ASTRA_Falcon_Cockpit")));
	}
	Hangar = InHangar;
	Walker = InWalker;
	Phase = EPhase::Catapult;
	PhaseT = 0.f;
	if (InHangar)
	{
		SetActorLocationAndRotation(InHangar->CatapultPose(0.f).GetLocation(), InHangar->CatapultPose(0.f).GetRotation());
	}
	ShowHud(true);
	StartSounds();
}

void AAstraFighterPawn::StartSounds()
{
	auto Make = [this](const TCHAR* Name, float Volume) -> UAudioComponent*
	{
		USoundBase* S = LoadObject<USoundBase>(nullptr, *FString::Printf(TEXT("/Game/ASTRA/Audio/%s.%s"), Name, Name));
		return S ? UGameplayStatics::CreateSound2D(this, S, Volume, 1.f, 0.f, nullptr, false, false) : nullptr;
	};
	EngineAudio = Make(TEXT("SW_Falcon_Engine"), 0.3f);
	LockAudio = Make(TEXT("SW_Lock_Solid"), 0.35f);
	WarnAudio = Make(TEXT("SW_Missile_Warning"), 0.45f);
	if (EngineAudio)
	{
		EngineAudio->SetPitchMultiplier(0.75f);
		EngineAudio->Play();
	}
}

void AAstraFighterPawn::StopSounds()
{
	for (UAudioComponent* A : {EngineAudio.Get(), LockAudio.Get(), WarnAudio.Get()})
	{
		if (A)
		{
			A->Stop();
			A->DestroyComponent();
		}
	}
	EngineAudio = LockAudio = WarnAudio = nullptr;
}

void AAstraFighterPawn::UpdateSounds(const FAstraPilotStatus& St, float Dt)
{
	const bool bFlying = (Phase == EPhase::Flying && St.bFlying) || Phase == EPhase::Atmosphere;
	if (EngineAudio)
	{
		// the lever and the afterburner in the airframe; the catapult's run pushes it up too
		const float Push = Phase == EPhase::Launching ? 1.f : In.Throttle;
		const float Boost = (bFlying && In.bBoost) ? 1.f : 0.f;
		EngineAudio->SetPitchMultiplier(0.72f + 0.5f * Push + 0.22f * Boost);
		EngineAudio->SetVolumeMultiplier(Phase == EPhase::Ending ? 0.f : 0.28f + 0.35f * Push + 0.15f * Boost);
	}
	// the seeker: beeps while it works on a target, a steady tone once locked
	const bool bLocked = bFlying && St.bHasLock && St.LockProgress >= 1.f;
	if (LockAudio)
	{
		if (bLocked && !LockAudio->IsPlaying()) { LockAudio->Play(); }
		else if (!bLocked && LockAudio->IsPlaying()) { LockAudio->Stop(); }
	}
	if (bFlying && St.bHasLock && !bLocked && (BeepT -= Dt) <= 0.f)
	{
		BeepT = 0.28f;
		if (USoundBase* B = LoadObject<USoundBase>(nullptr, TEXT("/Game/ASTRA/Audio/SW_Lock_Beep.SW_Lock_Beep")))
		{
			UGameplayStatics::PlaySound2D(this, B, 0.4f);
		}
	}
	if (WarnAudio)
	{
		const bool bWarn = bFlying && St.Incoming > 0;
		if (bWarn && !WarnAudio->IsPlaying()) { WarnAudio->Play(); }
		else if (!bWarn && WarnAudio->IsPlaying()) { WarnAudio->Stop(); }
	}
}

void AAstraFighterPawn::SetupPlayerInputComponent(UInputComponent* IC)
{
	Super::SetupPlayerInputComponent(IC);
	IC->BindAxisKey(EKeys::MouseX, this, &AAstraFighterPawn::MouseX);
	IC->BindAxisKey(EKeys::MouseY, this, &AAstraFighterPawn::MouseY);
	// a gamepad: left stick flies (pitch, roll), right stick yaws and slides, triggers are the lever, the face
	// buttons the weapons, the bumpers boost and decoys
	IC->BindAxisKey(EKeys::Gamepad_LeftX, this, &AAstraFighterPawn::PadRoll);
	IC->BindAxisKey(EKeys::Gamepad_LeftY, this, &AAstraFighterPawn::PadPitch);
	IC->BindAxisKey(EKeys::Gamepad_RightX, this, &AAstraFighterPawn::PadYaw);
	IC->BindAxisKey(EKeys::Gamepad_RightY, this, &AAstraFighterPawn::PadLift);
	IC->BindAxisKey(EKeys::Gamepad_RightTriggerAxis, this, &AAstraFighterPawn::PadThrottleUp);
	IC->BindAxisKey(EKeys::Gamepad_LeftTriggerAxis, this, &AAstraFighterPawn::PadThrottleDown);
	auto Hold = [IC, this](const FKey& K, bool AAstraFighterPawn::* Flag)
	{
		FInputKeyBinding P(FInputChord(K), IE_Pressed);
		P.KeyDelegate.GetDelegateForManualSet().BindLambda([this, Flag]() { this->*Flag = true; });
		IC->KeyBindings.Add(P);
		FInputKeyBinding R(FInputChord(K), IE_Released);
		R.KeyDelegate.GetDelegateForManualSet().BindLambda([this, Flag]() { this->*Flag = false; });
		IC->KeyBindings.Add(R);
	};
	Hold(EKeys::W, &AAstraFighterPawn::bThrUp);
	Hold(EKeys::S, &AAstraFighterPawn::bThrDown);
	Hold(EKeys::A, &AAstraFighterPawn::bRollL);
	Hold(EKeys::D, &AAstraFighterPawn::bRollR);
	Hold(EKeys::Q, &AAstraFighterPawn::bLeft);
	Hold(EKeys::E, &AAstraFighterPawn::bRight);
	Hold(EKeys::SpaceBar, &AAstraFighterPawn::bUp);
	Hold(EKeys::LeftControl, &AAstraFighterPawn::bDown);
	Hold(EKeys::LeftAlt, &AAstraFighterPawn::bFreeLook);
	auto Flag = [IC, this](const FKey& K, TFunction<void(bool)> F)
	{
		FInputKeyBinding P(FInputChord(K), IE_Pressed);
		P.KeyDelegate.GetDelegateForManualSet().BindLambda([F]() { F(true); });
		IC->KeyBindings.Add(P);
		FInputKeyBinding R(FInputChord(K), IE_Released);
		R.KeyDelegate.GetDelegateForManualSet().BindLambda([F]() { F(false); });
		IC->KeyBindings.Add(R);
	};
	Flag(EKeys::LeftShift, [this](bool b) { In.bBoost = b; });
	Flag(EKeys::LeftMouseButton, [this](bool b) { In.bGuns = b; });
	Flag(EKeys::RightMouseButton, [this](bool b) { In.bMissile = b; });
	Flag(EKeys::C, [this](bool b) { In.bDecoy = b; });
	Flag(EKeys::Gamepad_FaceButton_Bottom, [this](bool b) { In.bGuns = b; });
	Flag(EKeys::Gamepad_FaceButton_Right, [this](bool b) { In.bMissile = b; });
	Flag(EKeys::Gamepad_LeftShoulder, [this](bool b) { In.bDecoy = b; });
	Flag(EKeys::Gamepad_RightShoulder, [this](bool b) { In.bBoost = b; });
	IC->BindKey(EKeys::Gamepad_FaceButton_Top, IE_Pressed, this, &AAstraFighterPawn::Land);
	IC->BindKey(EKeys::Gamepad_FaceButton_Left, IE_Pressed, this, &AAstraFighterPawn::Descend);
	IC->BindKey(EKeys::G, IE_Pressed, this, &AAstraFighterPawn::Descend);
	Flag(EKeys::X, [this](bool b) { if (b) { In.Throttle = 0.f; } });   // X: cut the throttle
	IC->BindKey(EKeys::F, IE_Pressed, this, &AAstraFighterPawn::Land);
	IC->BindKey(EKeys::R, IE_Pressed, this, &AAstraFighterPawn::TakePod);                     // R: a lifepod within the grapples' reach comes aboard
	IC->BindKey(EKeys::Gamepad_DPad_Up, IE_Pressed, this, &AAstraFighterPawn::TakePod);
}

bool AAstraFighterPawn::ClimbOut()
{
	if (Phase == EPhase::Landed)
	{
		ClimbOutPlanetside();
		return true;
	}
	if (Phase != EPhase::Catapult)
	{
		return false;
	}
	FinishFlight();
	return true;
}

void AAstraFighterPawn::PadRoll(float V) { PadAxes.X = V; }
void AAstraFighterPawn::PadPitch(float V) { PadAxes.Y = V; }
void AAstraFighterPawn::PadYaw(float V) { PadAxes.Z = V; }
void AAstraFighterPawn::PadLift(float V) { PadLiftV = V; }
void AAstraFighterPawn::PadThrottleUp(float V) { PadThr.X = V; }
void AAstraFighterPawn::PadThrottleDown(float V) { PadThr.Y = V; }

void AAstraFighterPawn::MouseX(float V)
{
	if (bFreeLook)
	{
		LookYaw = FMath::Clamp(LookYaw + V * 2.f, -150.f, 150.f);
		return;
	}
	Stick.X = FMath::Clamp(Stick.X + V * 0.035f, -1.f, 1.f);
}

void AAstraFighterPawn::MouseY(float V)
{
	if (bFreeLook)
	{
		LookPitch = FMath::Clamp(LookPitch + V * 2.f, -70.f, 80.f);
		return;
	}
	Stick.Y = FMath::Clamp(Stick.Y - V * 0.035f, -1.f, 1.f);
}

void AAstraFighterPawn::Land()
{
	if (Phase == EPhase::Atmosphere)
	{
		FVector Ground;
		const float AGL = TraceAGL(&Ground);
		if (AGL < 90.f && AirVel.Size() < 7500.f)
		{
			Phase = EPhase::Settling;
			PhaseT = 0.f;
			SettleFrom = GetActorLocation();
			SettleTo = Ground + FVector(0.f, 0.f, 260.f);   // the eye 2.6 m over the ground, as on the deck
			SettleRot = FRotator(0.f, GetActorRotation().Yaw, 0.f);
		}
		return;
	}
	UAstraBattleSubsystem* Battle = GetWorld()->GetSubsystem<UAstraBattleSubsystem>();
	if (Phase != EPhase::Flying || !Battle)
	{
		return;
	}
	FAstraPilotStatus St;
	Battle->GetPilotStatus(St);
	if (St.bCanLand)
	{
		Phase = EPhase::Ending;
		PhaseT = 0.f;
		bLandedEnd = true;
		if (APlayerCameraManager* Cam = UGameplayStatics::GetPlayerCameraManager(this, 0))
		{
			Cam->StartCameraFade(0.f, 1.f, 0.8f, FLinearColor::Black, false, true);
		}
	}
	else if (St.bCanRecover)
	{
		// farther out: the deck's recovery guidance brings her in (an automatic carrier landing): flying into the tube's mouth by eye ended twice
		// against the hull (2 Oct)
		Battle->StartPilotRecovery(TEXT("the Captain"));
	}
	else if (St.bRecovering)
	{
		Battle->StopPilotRecovery(TEXT("the Captain called it off"));
	}
}

void AAstraFighterPawn::TakePod()
{
	UAstraBattleSubsystem* Battle = GetWorld() ? GetWorld()->GetSubsystem<UAstraBattleSubsystem>() : nullptr;
	UAstraSpaceLife* Space = Battle ? Battle->GetSpace() : nullptr;
	if (Phase != EPhase::Flying || !Space || !Space->IsActive())
	{
		return;
	}
	const AstraSpace::FRescued R = Space->PilotRescue(Battle->GetPilotedId());
	NoticeT = 5.f;
	Notice = R.Pods > 0 ? FString::Printf(TEXT("LIFEPOD ABOARD  ·  %d SURVIVOR%s  ·  %s"), R.Survivors, R.Survivors == 1 ? TEXT("") : TEXT("S"), *AstraSpace::FWrecks::BareName(R.Of).ToUpper())
	                    : FString(TEXT("NO LIFEPOD IN REACH"));
}

void AAstraFighterPawn::Tick(float DeltaTime)
{
	Super::Tick(DeltaTime);
	TickFlakFx(DeltaTime);
	NoticeT = FMath::Max(0.f, NoticeT - DeltaTime);
	UAstraBattleSubsystem* Battle = GetWorld()->GetSubsystem<UAstraBattleSubsystem>();
	// the hands on the controls: the lever moves at 0.6 a second, the stick recentres when the mouse rests
	In.Throttle = FMath::Clamp(In.Throttle + ((bThrUp ? 1.f : 0.f) - (bThrDown ? 1.f : 0.f) + PadThr.X - PadThr.Y) * 0.6f * DeltaTime, 0.f, 1.f);
	if (TestRoll == 0.f)
	{
		Stick *= FMath::Max(0.f, 1.f - 1.6f * DeltaTime);
	}
	const FVector2D Shaped(FMath::Sign(Stick.X) * FMath::Square(Stick.X) * 0.7f + Stick.X * 0.3f, FMath::Sign(Stick.Y) * FMath::Square(Stick.Y) * 0.7f + Stick.Y * 0.3f);
	In.Yaw = FMath::Clamp(Shaped.X + PadAxes.Z * FMath::Abs(PadAxes.Z), -1.f, 1.f);
	In.Pitch = FMath::Clamp(Shaped.Y - PadAxes.Y * FMath::Abs(PadAxes.Y), -1.f, 1.f);   // stick back = nose up
	In.Roll = FMath::Clamp((bRollR ? 1.f : 0.f) - (bRollL ? 1.f : 0.f) + TestRoll + PadAxes.X * FMath::Abs(PadAxes.X), -1.f, 1.f);
	if (MissilePulse > 0.f && (MissilePulse -= DeltaTime) <= 0.f)
	{
		In.bMissile = false;
	}
	In.Strafe = FVector(0.f, (bRight ? 1.f : 0.f) - (bLeft ? 1.f : 0.f), FMath::Clamp((bUp ? 1.f : 0.f) - (bDown ? 1.f : 0.f) + PadLiftV, -1.f, 1.f));
	if (!bFreeLook)
	{
		LookYaw = FMath::FInterpTo(LookYaw, 0.f, DeltaTime, 4.f);
		LookPitch = FMath::FInterpTo(LookPitch, 0.f, DeltaTime, 4.f);
	}
	Camera->SetRelativeRotation(FRotator(LookPitch, LookYaw, 0.f));

	FAstraPilotStatus St;
	switch (Phase)
	{
	case EPhase::Catapult:
		// on the catapult: throttle up to launch, E to climb out
		if (In.Throttle > 0.25f)
		{
			Phase = EPhase::Launching;
			PhaseT = 0.f;
			if (USoundBase* S = LoadObject<USoundBase>(nullptr, TEXT("/Game/ASTRA/Audio/SW_Catapult.SW_Catapult")))
			{
				UGameplayStatics::PlaySound2D(this, S, 1.f);
			}
		}
		break;
	case EPhase::Launching:
	{
		// the catapult: a hard kick down the track and out of the tube (the view narrows with the acceleration)
		PhaseT += DeltaTime;
		const float T = FMath::Min(1.f, PhaseT / 1.1f);
		Camera->SetFieldOfView(88.f - 9.f * FMath::Sin(PI * T));
		if (AAstraHangar* H = Hangar.Get())
		{
			const FTransform P = H->CatapultPose(T * T);
			SetActorLocationAndRotation(P.GetLocation(), P.GetRotation());
			if (T >= 1.f && Battle && Battle->LaunchPiloted(this, P.GetLocation(), P.GetRotation(), H->CatapultExitSpeed(1.1f)))
			{
				Phase = EPhase::Flying;
				In.Throttle = 0.6f;
				Cockpit->SetLightingChannels(true, true, false);   // outside now: the planet's light reaches the nose
			}
		}
		break;
	}
	case EPhase::Flying:
		if (Battle)
		{
			Battle->SetPilotInput(In);
			Battle->GetPilotStatus(St);
			if (St.bRecovered)
			{
				Land();                            // the guidance has her at the mouth, slow: into the tube
			}
			if (St.bDown)
			{
				// shot down: the canopy blows, black, the pod tumbles; the Wasp brings it home
				Phase = EPhase::Ending;
				PhaseT = 0.f;
				bLandedEnd = false;
				if (APlayerCameraManager* Cam = UGameplayStatics::GetPlayerCameraManager(this, 0))
				{
					Cam->StartCameraFade(0.f, 1.f, 0.25f, FLinearColor(1.f, 0.85f, 0.7f), false, true);
				}
			}
		}
		break;
	case EPhase::Ending:
		PhaseT += DeltaTime;
		if (Battle)
		{
			Battle->SetPilotInput(In);
		}
		if (PhaseT > (bLandedEnd ? 1.0f : 3.5f))
		{
			FinishFlight();
			return;
		}
		break;
	case EPhase::Entry:
		TickEntryExit(DeltaTime, true);
		if (!bSwitched && Battle)
		{
			Battle->GetPilotStatus(St);
		}
		else
		{
			St = PlanetStatus();
		}
		break;
	case EPhase::Exit:
		TickEntryExit(DeltaTime, false);
		St = PlanetStatus();
		break;
	case EPhase::Atmosphere:
		TickAtmosphere(DeltaTime);
		if (Phase == EPhase::Atmosphere)
		{
			TickGroundFire(DeltaTime);
		}
		St = PlanetStatus();
		break;
	case EPhase::Settling:
	{
		// touching down: level off and sink onto the ground over two and a half seconds
		PhaseT += DeltaTime;
		const float T = FMath::SmoothStep(0.f, 1.f, FMath::Min(1.f, PhaseT / 2.5f));
		SetActorLocationAndRotation(FMath::Lerp(SettleFrom, SettleTo, T), FQuat::Slerp(GetActorQuat(), SettleRot.Quaternion(), FMath::Min(1.f, DeltaTime * 3.f)));
		In.Throttle = 0.f;
		if (PhaseT >= 2.5f)
		{
			Phase = EPhase::Landed;
			AirVel = FVector::ZeroVector;
			if (UAstraShipSubsystem* Ship = GetWorld()->GetSubsystem<UAstraShipSubsystem>())
			{
				Ship->SetCaptainPlanetside(FString::Printf(TEXT("landed on %s near %s, in a Falcon of Alpha; the XO has the conn"), *Ship->SurfaceWorldName(), *Ship->SurfaceSiteName()));
				Ship->PublishEvent(FString::Printf(TEXT("flight: Eagle has landed on %s, near %s"), *Ship->SurfaceWorldName(), *Ship->SurfaceSiteName()), true);
			}
		}
		St = PlanetStatus();
		break;
	}
	case EPhase::Landed:
		if (UAstraShipSubsystem* ShipG = GetWorld()->GetSubsystem<UAstraShipSubsystem>(); ShipG && ShipG->SurfaceOwner() == TEXT("mandate"))
		{
			// down at an enemy field: the garrison turns out (the crew hears of it, and the story remembers)
			const float Before = GarrisonT;
			GarrisonT += DeltaTime;
			if (Before < 40.f && GarrisonT >= 40.f)
			{
				ShipG->PublishEvent(FString::Printf(TEXT("flight: a Mandate garrison column is closing on Eagle's landing site on %s — armoured "
				                                          "vehicles on the road from %s"), *ShipG->SurfaceWorldName(), *ShipG->SurfaceSiteName()), true);
			}
		}
		// on the ground: W lifts off, E climbs out
		if (In.Throttle > 0.2f)
		{
			Phase = EPhase::Atmosphere;
			AirVel = GetActorUpVector() * 1500.f;
			In.Throttle = 0.15f;
			if (UAstraShipSubsystem* Ship = GetWorld()->GetSubsystem<UAstraShipSubsystem>())
			{
				Ship->SetCaptainPlanetside(FString::Printf(TEXT("flying a Falcon over %s near %s; the XO has the conn"), *Ship->SurfaceWorldName(), *Ship->SurfaceSiteName()));
			}
		}
		St = PlanetStatus();
		break;
	case EPhase::Parked:
		return;
	}
	if (Phase == EPhase::Flying && St.bFlying)
	{
		const float HS = St.HullPct + St.ShieldPct;
		if (LastHS >= 0.f && HS < LastHS - 0.5f)
		{
			HitJolt = FMath::Min(1.f, HitJolt + (LastHS - HS) / 25.f + 0.3f);
			if (USoundBase* Bang = LoadObject<USoundBase>(nullptr, TEXT("/Game/ASTRA/Audio/SW_Impact.SW_Impact")))
			{
				UGameplayStatics::PlaySound2D(this, Bang, 0.35f + 0.4f * HitJolt, 1.5f);
			}
		}
		LastHS = HS;
	}
	HitJolt = FMath::Max(0.f, HitJolt - DeltaTime * 3.f);
	if (HitJolt > 0.f)
	{
		Camera->SetRelativeRotation(FRotator(LookPitch + FMath::FRandRange(-1.5f, 1.5f) * HitJolt, LookYaw + FMath::FRandRange(-1.5f, 1.5f) * HitJolt,
		                                     FMath::FRandRange(-1.f, 1.f) * HitJolt));
	}
	UpdateSounds(St, DeltaTime);
	UpdateHud(St);
}

void AAstraFighterPawn::FinishFlight()
{
	UAstraBattleSubsystem* Battle = GetWorld()->GetSubsystem<UAstraBattleSubsystem>();
	if (Battle && Battle->IsPiloting())
	{
		Battle->EndPiloted(bLandedEnd);
	}
	else if (Battle && Phase != EPhase::Ending)
	{
		Battle->ReturnFalcon();   // climbed out on the catapult
	}
	ShowHud(false);
	APlayerController* PC = Cast<APlayerController>(GetController());
	APawn* W = Walker.Get();
	if (PC && W)
	{
		// back on the flight deck, beside Alpha's bays
		if (AAstraHangar* H = Hangar.Get())
		{
			const FTransform Spot = H->DeckSpot();
			W->SetActorLocation(Spot.GetLocation(), false, nullptr, ETeleportType::TeleportPhysics);
			PC->SetControlRotation(Spot.Rotator());
		}
		W->SetActorHiddenInGame(false);
		W->SetActorEnableCollision(true);
		PC->Possess(W);
		if (APlayerCameraManager* Cam = PC->PlayerCameraManager)
		{
			Cam->StartCameraFade(1.f, 0.f, 1.0f, FLinearColor::Black, false, false);
		}
	}
	Destroy();
}

void AAstraFighterPawn::EndPlay(const EEndPlayReason::Type Reason)
{
	for (AStaticMeshActor* A : FlakFx)
	{
		if (A)
		{
			A->Destroy();
		}
	}
	FlakFx.Reset();
	ShowHud(false);
	StopSounds();
	Super::EndPlay(Reason);
}

void AAstraFighterPawn::ShowHud(bool bShow)
{
	UGameViewportClient* VC = GetWorld() ? GetWorld()->GetGameViewport() : nullptr;
	if (bShow && !Hud.IsValid() && VC)
	{
		Hud = SNew(SAstraFlightHud);
		VC->AddViewportWidgetContent(Hud.ToSharedRef(), 10);
	}
	else if (!bShow && Hud.IsValid())
	{
		if (VC)
		{
			VC->RemoveViewportWidgetContent(Hud.ToSharedRef());
		}
		Hud.Reset();
	}
}

void AAstraFighterPawn::UpdateHud(const FAstraPilotStatus& St)
{
	if (!Hud.IsValid())
	{
		return;
	}
	SAstraFlightHud::FData& D = Hud->Data;
	D = SAstraFlightHud::FData();
	const bool bAir = Phase == EPhase::Atmosphere || Phase == EPhase::Settling || Phase == EPhase::Landed ||
	                  ((Phase == EPhase::Entry || Phase == EPhase::Exit) && bSwitched == (Phase == EPhase::Entry));
	D.bFlying = (Phase == EPhase::Flying && St.bFlying) || bAir || Phase == EPhase::Entry || Phase == EPhase::Exit;
	D.bPlanet = bAir;
	D.Plasma = Plasma;
	D.Stick = Stick;
	D.Throttle = In.Throttle;
	D.bBoost = In.bBoost;
	if (Phase == EPhase::Catapult)
	{
		D.Hint = TEXT("ON ALPHA'S CATAPULT  ·  W: THROTTLE UP TO LAUNCH  ·  E: CLIMB OUT");
		return;
	}
	if (bAir)
	{
		D.Alt = (GetActorLocation().Z - UAstraShipSubsystem::PlanetZone().Z) / 100.f;
		D.AGL = GroundAGL;
		if (Phase == EPhase::Landed)
		{
			D.Hint = TEXT("ON THE GROUND  ·  W: LIFT OFF  ·  E: CLIMB OUT");
		}
		else if (Phase == EPhase::Atmosphere && GroundAGL < 90.f && St.SpeedMps < 75.f)
		{
			D.Hint = TEXT("F: SET HER DOWN");
		}
		else if (Phase == EPhase::Atmosphere && D.Alt > 9000.f && AirVel.Z > 0.f)
		{
			D.Hint = TEXT("KEEP CLIMBING: ORBIT PAST 14 KM");
		}
	}
	else if (CanDescend())
	{
		const UAstraShipSubsystem* ShipB = GetWorld()->GetSubsystem<UAstraShipSubsystem>();
		D.Hint = FString::Printf(TEXT("%s BELOW  ·  G: BEGIN DESCENT"), ShipB ? *ShipB->SurfaceWorldName().ToUpper() : TEXT("THE WORLD"));
	}
	if (!D.bFlying)
	{
		return;
	}
	D.Speed = St.SpeedMps;
	D.Hull = St.HullPct;
	D.Shield = St.ShieldPct;
	D.Missiles = St.Missiles;
	D.Decoys = St.Decoys;
	APlayerController* PC = Cast<APlayerController>(GetController());
	FVector2D VP(1920.f, 1080.f);
	if (GetWorld()->GetGameViewport())
	{
		GetWorld()->GetGameViewport()->GetViewportSize(VP);
	}
	auto Project = [PC, &VP](const FVector& W, FVector2D& OutN) -> bool
	{
		FVector2D S;
		if (!PC || !PC->ProjectWorldLocationToScreen(W, S, true))
		{
			return false;
		}
		OutN = S / VP;
		return OutN.X > -0.05 && OutN.X < 1.05 && OutN.Y > -0.05 && OutN.Y < 1.05;
	};
	const FVector Eye = Camera->GetComponentLocation();
	const float Fov = FMath::DegreesToRadians(Camera->FieldOfView);
	// the datalink: every contact on the Aquila's plot, as the Aquila knows it, seen from this cockpit
	if (const UAstraBattleSubsystem* Battle = GetWorld()->GetSubsystem<UAstraBattleSubsystem>())
	{
		const TArray<UAstraBattleSubsystem::FContactView>& Cs = Battle->Contacts();
		const FVector Fwd = Camera->GetForwardVector();
		int32 Named = 0;
		for (const UAstraBattleSubsystem::FContactView& Ct : Cs)
		{
			if (Ct.Id == Battle->GetPilotedId() || Ct.Track < 2)
			{
				continue;
			}
			const FVector W = Ct.Actor ? Ct.Actor->GetActorLocation() : Battle->WorldOf(Ct.Pos);
			const float DistKm = FVector::Dist(Eye, W) / 100000.f;
			const int32 Side = Ct.bUnknown ? 0 : (Ct.Side == EAstraSide::Astra ? 1 : (Ct.Side == EAstraSide::Mandate ? 2 : 3));
			FVector2D N;
			if (FVector::DotProduct(W - Eye, Fwd) > 0.f && Project(W, N))
			{
				SAstraFlightHud::FData::FMark M;
				M.Pos = N;
				M.bCraft = Ct.bCraft;
				M.Side = Side;
				const float R = Ct.Actor && Ct.Actor->GetStaticMeshComponent() ? Ct.Actor->GetStaticMeshComponent()->Bounds.SphereRadius / 100.f : Ct.RadiusM;
				M.Box = FMath::Clamp(R / FMath::Max(0.05f, DistKm * 1000.f) / FMath::Tan(Fov / 2) * 540.f * 0.8f, 10.f, 160.f);
				// names for the warships near enough to matter, and for the craft close to the Falcon
				const bool bLocked = St.bHasLock && Ct.Label.Equals(St.LockName, ESearchCase::IgnoreCase);   // the lock box names it
				if (!bLocked && ((!Ct.bCraft && DistKm < 60.f && Named < 8) || (Ct.bCraft && DistKm < 3.f)))
				{
					M.Name = Ct.bCraft ? FString::Printf(TEXT("%.1f"), DistKm) : Ct.Label.ToUpper();
					M.Sub = Ct.bCraft ? FString() : FString::Printf(TEXT("%.1f km"), DistKm);
					Named += Ct.bCraft ? 0 : 1;
				}
				D.Marks.Add(M);
			}
			else if (Side == 2 && (DistKm < 8.f || (!Ct.bCraft && DistKm < 40.f)) && D.Edges.Num() < 6)
			{
				// a threat behind or beside: an arrow on the ring pointing the way to turn
				const FVector L = Camera->GetComponentTransform().InverseTransformPosition(W);
				SAstraFlightHud::FData::FEdge E;
				E.Angle = FMath::Atan2(-L.Z, L.Y);
				E.Text = Ct.bCraft ? FString::Printf(TEXT("%.1f"), DistKm) : FString::Printf(TEXT("%s %.0f"), *Ct.ContactId, DistKm);
				D.Edges.Add(E);
			}
		}
	}
	// the lifepods near her (SPAZIO-VIVO): a ring and a cross where each is, the nearest named; one out of view is an arrow on the ring
	{
		const FVector Fwd = Camera->GetForwardVector();
		for (int32 i = 0; i < St.Pods.Num(); ++i)
		{
			const FAstraPilotStatus::FPod& P = St.Pods[i];
			const FString Air = P.AirMin >= 100.f ? FString::Printf(TEXT("AIR %d H %02d"), FMath::FloorToInt(P.AirMin / 60.f), FMath::FloorToInt(P.AirMin) % 60) : FString::Printf(TEXT("AIR %.0f MIN"), P.AirMin);
			FVector2D N;
			if (FVector::DotProduct(P.World - Eye, Fwd) > 0.f && Project(P.World, N))
			{
				SAstraFlightHud::FData::FMark M;
				M.Pos = N;
				M.bCraft = true;
				M.bPod = true;
				M.bReach = i == St.PodInReach;
				M.Side = P.Faction == 0 ? 1 : 3;                 // (ours: the datalink's blue; theirs and the Guilds': a neutral amber, someone to bring in)
				M.Name = M.bReach ? FString(TEXT("R: TAKE ABOARD")) : FString::Printf(TEXT("LIFEPOD %.1f km"), P.RangeM / 1000.f);
				M.Sub = FString::Printf(TEXT("%d ALIVE  ·  %s"), P.Survivors, *Air);
				D.Marks.Add(M);
			}
			else if (P.RangeM < 6000.f && D.Edges.Num() < 6)
			{
				const FVector L = Camera->GetComponentTransform().InverseTransformPosition(P.World);
				SAstraFlightHud::FData::FEdge E;
				E.Angle = FMath::Atan2(-L.Z, L.Y);
				E.Text = FString::Printf(TEXT("POD %.1f"), P.RangeM / 1000.f);
				E.bFoe = false;
				D.Edges.Add(E);
			}
		}
	}
	if (St.bHasLock && Project(St.LockWorld, D.LockPos))
	{
		D.bLock = true;
		D.bLockOn = St.LockProgress >= 1.f;
		D.LockProgress = St.LockProgress;
		D.LockText = FString::Printf(TEXT("%s  %.1f km%s"), *St.LockName.ToUpper(), St.LockRangeKm, D.bLockOn ? TEXT("  LOCK") : TEXT(""));
		D.bLead = Project(St.LeadWorld, D.LeadPos);
	}
	const UAstraShipSubsystem* ShipH = GetWorld()->GetSubsystem<UAstraShipSubsystem>();
	D.HomeText = bAir ? FString::Printf(TEXT("%s %.1f km"), ShipH ? *ShipH->SurfaceSiteName().ToUpper() : TEXT("FIELD"), St.HomeRangeKm)
	                  : FString::Printf(TEXT("AQUILA %.1f km%s"), St.HomeRangeKm, St.bCanLand ? TEXT("  ·  F: RECOVER")
	                                                                                   : (St.bCanRecover ? TEXT("  ·  F: RECOVERY GUIDANCE") : TEXT("")));
	if (Project(St.HomeWorld, D.HomePos))
	{
		D.bHomeOn = true;
	}
	else
	{
		const FVector Local = Camera->GetComponentTransform().InverseTransformPosition(St.HomeWorld);
		D.bHomeEdge = true;
		D.HomeEdgeAngle = FMath::Atan2(-Local.Z, Local.Y);
	}
	if (bAir)
	{
		return;
	}
	if (St.Incoming > 0)
	{
		D.Hint = FString::Printf(TEXT("MISSILE%s INBOUND  ·  C: DECOYS  ·  BREAK AND BOOST"), St.Incoming > 1 ? TEXT("S") : TEXT(""));
	}
	else if (St.CueLevel == 2)
	{
		// a hull on her course within five seconds (SPAZIO-VIVO: the places, the pieces of the wrecks, the ships, the Aquila): where, how far along her course, how soon
		D.Hint = FString::Printf(TEXT("COLLISION COURSE  ·  %s  ·  %.0f m  ·  %.1f s"), *St.CueWhat.ToUpper(), St.CueRangeM, St.CueTtcS);
	}
	else if (St.bRecovering)
	{
		D.Hint = TEXT("RECOVERY GUIDANCE  ·  THE DECK IS FLYING YOU IN  ·  PUSH THE STICK OR F: TAKE HER BACK");
	}
	else if (NoticeT > 0.f && !Notice.IsEmpty())
	{
		D.Hint = Notice;
	}
	else if (St.PodInReach >= 0 && St.Pods.IsValidIndex(St.PodInReach))
	{
		const FAstraPilotStatus::FPod& P = St.Pods[St.PodInReach];
		D.Hint = FString::Printf(TEXT("R: TAKE THE LIFEPOD ABOARD  ·  %d ALIVE  ·  %s"), P.Survivors, *P.Of.ToUpper());
	}
	else if (St.bCanLand)
	{
		D.Hint = TEXT("RECOVERY APPROACH  ·  F: INTO THE TUBE");
	}
	else if (St.bCanRecover && St.HullPct < 60.f)
	{
		D.Hint = TEXT("F: RECOVERY GUIDANCE  ·  THE DECK FLIES YOU HOME");
	}
	else if (St.CueLevel == 1)
	{
		D.Hint = FString::Printf(TEXT("PROXIMITY  ·  %s  ·  %.0f m"), *St.CueWhat.ToUpper(), St.CueRangeM);
	}
	else if (St.Pods.Num() > 0 && St.Pods[0].RangeM < 3000.f)
	{
		const FAstraPilotStatus::FPod& P = St.Pods[0];
		D.Hint = FString::Printf(TEXT("LIFEPOD  ·  %.1f km  ·  %d ALIVE  ·  CLOSE TO WITHIN %.0f m, THEN R"), P.RangeM / 1000.f, P.Survivors, UAstraSpaceLife::PodReachM());
	}
	else if (St.HullPct < 30.f)
	{
		D.Hint = TEXT("HULL CRITICAL  ·  RETURN TO THE AQUILA");
	}
}

// ------------------------------------------------------------------------------------------------ New Ravenna
namespace
{
	// the planet's zone: where the Falcon comes out of the entry (over the sea south of the bay, heading north for the
	// coast) and where Port Aurelius Field is (the zone's frame: +X east, -Y north, metres; the terrain generator's
	// y is mirrored by the import)
	const FVector EntryStart(0.0, 17000.0, 8500.0);
	const FVector FieldSpot(1800.0, -1400.0, 191.4);   // nr_sites.json (y mirrored)
	constexpr float OrbitAltitude = 14000.f;   // climbing past this takes the Falcon back up
}

void AAstraFighterPawn::AstraFacePlanet(float X, float Y, float Z)
{
	const FVector Target = UAstraShipSubsystem::PlanetZone() + FVector(X, Y, Z) * 100.0;
	const FRotator R = (Target - GetActorLocation()).Rotation();
	SetActorRotation(R);
	AirVel = R.Vector() * AirVel.Size();
}

bool AAstraFighterPawn::CanDescend() const
{
	const UAstraShipSubsystem* Ship = GetWorld()->GetSubsystem<UAstraShipSubsystem>();
	if (Phase != EPhase::Flying || !Ship || !Ship->HasSurface())
	{
		return false;
	}
	// the nose on the world (within 25 degrees)
	return FVector::DotProduct(GetActorForwardVector(), Ship->PlanetDirectionWorld()) > FMath::Cos(FMath::DegreesToRadians(25.f));
}

void AAstraFighterPawn::Descend()
{
	if (!CanDescend())
	{
		return;
	}
	Phase = EPhase::Entry;
	PhaseT = 0.f;
	bSwitched = false;
	AtmoHull = 100.f;       // a fresh count of the damage down there
	HostileT = FlakT = GarrisonT = 0.f;
	bGroundFire = false;
	HullBand = 4;
	if (USoundBase* S = LoadObject<USoundBase>(nullptr, TEXT("/Game/ASTRA/Audio/SW_Entry_Plasma.SW_Entry_Plasma")))
	{
		PlasmaAudio = UGameplayStatics::CreateSound2D(this, S, 0.9f, 1.f, 0.f, nullptr, false, false);
		if (PlasmaAudio)
		{
			PlasmaAudio->Play();
		}
	}
	if (UAstraShipSubsystem* Ship = GetWorld()->GetSubsystem<UAstraShipSubsystem>())
	{
		Ship->PublishEvent(FString::Printf(TEXT("flight: Eagle is starting a descent to %s — entry interface in a few seconds"), *Ship->SurfaceWorldName()), true);
	}
}

void AAstraFighterPawn::TickEntryExit(float Dt, bool bEntry)
{
	// the plasma builds for four seconds (the view goes orange-white), the worlds swap at its height, then it fades
	PhaseT += Dt;
	const float Peak = bEntry ? 4.f : 2.5f, End = bEntry ? 9.f : 6.f;
	Plasma = PhaseT < Peak ? FMath::Pow(PhaseT / Peak, 1.6f) : FMath::Clamp(1.f - (PhaseT - Peak) / (End - Peak), 0.f, 1.f);
	HitJolt = FMath::Max(HitJolt, Plasma * 0.55f);
	Camera->SetFieldOfView(88.f - 8.f * Plasma);
	UAstraShipSubsystem* Ship = GetWorld()->GetSubsystem<UAstraShipSubsystem>();
	UAstraBattleSubsystem* Battle = GetWorld()->GetSubsystem<UAstraBattleSubsystem>();
	if (!bSwitched && PhaseT >= Peak && Ship && Battle)
	{
		bSwitched = true;
		if (bEntry)
		{
			// off the fleet's plot, into the planet's zone: over the sea, nose down a little, heading for the coast
			Battle->LeavePiloted();
			Ship->SetPlanetside(true);
			Ship->SetCaptainPlanetside(FString::Printf(TEXT("flying a Falcon through %s's atmosphere toward %s; the XO has the conn"), *Ship->SurfaceWorldName(), *Ship->SurfaceSiteName()));
			// home: over the sea south of the bay; elsewhere: 17 km short of the landing field, on the same heading
			const FRotator Heading(-10.f, -90.f, 0.f);
			const FVector Site = Ship->SurfaceSite();
			SetActorLocationAndRotation(Ship->IsHomeWorld() ? UAstraShipSubsystem::PlanetZone() + EntryStart * 100.0
			                                                : FVector(Site.X, Site.Y + EntryStart.Y * 100.0, UAstraShipSubsystem::PlanetZone().Z + EntryStart.Z * 100.0),
			                            Heading);
			AirVel = Heading.Vector() * 32000.f;
			In.Throttle = 0.45f;
			Cockpit->SetLightingChannels(true, false, false);
		}
		else
		{
			// back above the atmosphere: the Aquila 4 km off, and the battle flies the Falcon again
			Ship->SetPlanetside(false);
			const FVector Pos(-2000.0 * 100.0, -4000.0 * 100.0, 300.0 * 100.0);
			const FQuat Rot = (FVector::ZeroVector - Pos).GetSafeNormal().Rotation().Quaternion();
			if (Battle->LaunchPiloted(this, Pos, Rot, 150.f, true))
			{
				In.Throttle = 0.3f;
			}
			Cockpit->SetLightingChannels(true, true, false);
		}
	}
	if (bEntry && bSwitched)
	{
		TickAtmosphere(Dt);   // already flying down there under the glow
	}
	else if (bEntry)
	{
		// still in space: the battle keeps flying the Falcon
		if (Battle)
		{
			Battle->SetPilotInput(In);
		}
	}
	if (PhaseT >= End)
	{
		Plasma = 0.f;
		Camera->SetFieldOfView(88.f);
		if (PlasmaAudio)
		{
			PlasmaAudio->FadeOut(1.5f, 0.f);
		}
		Phase = bEntry ? EPhase::Atmosphere : EPhase::Flying;
	}
}

float AAstraFighterPawn::TraceAGL(FVector* OutGround) const
{
	FHitResult Hit;
	const FVector From = GetActorLocation();
	const FVector To = From - FVector(0.f, 0.f, 2.0e6f);   // 20 km down
	FCollisionQueryParams Q(TEXT("FalconAGL"), false, this);
	if (GetWorld()->LineTraceSingleByChannel(Hit, From, To, ECC_Visibility, Q))
	{
		if (OutGround)
		{
			*OutGround = Hit.ImpactPoint;
		}
		return (From.Z - Hit.ImpactPoint.Z) / 100.f;
	}
	if (OutGround)
	{
		*OutGround = To;
	}
	return 1e6f;
}

void AAstraFighterPawn::TickAtmosphere(float Dt)
{
	// the stick and the lever as in space, in the air: 330 m/s at full throttle, softer acceleration, a little drag
	const FRotator Turn(In.Pitch * 55.f * Dt, In.Yaw * 40.f * Dt, In.Roll * 110.f * Dt);
	const FQuat Att = (GetActorQuat() * Turn.Quaternion()).GetNormalized();
	const float MaxV = In.bBoost ? 52000.f : 33000.f;
	const FVector Want = Att.RotateVector(FVector(In.Throttle * MaxV, In.Strafe.Y * 1500.f, In.Strafe.Z * 1500.f));
	AirVel += (Want - AirVel).GetClampedToMaxSize((In.bBoost ? 9000.f : 5500.f) * Dt);
	const FVector From = GetActorLocation();
	const FVector To = From + AirVel * Dt;
	// the ground and the sea stop the Falcon: slowly and nearly level is a (rough) landing, anything else a crash
	FHitResult Hit;
	FCollisionQueryParams Q(TEXT("FalconMove"), false, this);
	if (GetWorld()->SweepSingleByChannel(Hit, From, To, FQuat::Identity, ECC_Visibility, FCollisionShape::MakeSphere(250.f), Q))
	{
		const bool bSoft = AirVel.Size() < 3500.f && FVector::DotProduct(Att.GetUpVector(), FVector::UpVector) > 0.85f && Hit.ImpactNormal.Z > 0.85f;
		if (bSoft)
		{
			Phase = EPhase::Settling;
			PhaseT = 1.8f;
			SettleFrom = Hit.Location;
			SettleTo = Hit.ImpactPoint + FVector(0.f, 0.f, 260.f);
			SettleRot = FRotator(0.f, Att.Rotator().Yaw, 0.f);
			SetActorLocation(Hit.Location);
			return;
		}
		Crash();
		return;
	}
	SetActorLocationAndRotation(To, Att);
	GroundAGL = TraceAGL();
	// far above: the Falcon climbs out of the atmosphere, back to orbit
	const float Alt = (To.Z - UAstraShipSubsystem::PlanetZone().Z) / 100.f;
	if (Phase == EPhase::Atmosphere && Alt > OrbitAltitude && AirVel.Z > 0.f)
	{
		Phase = EPhase::Exit;
		PhaseT = 0.f;
		bSwitched = false;
		if (USoundBase* S = LoadObject<USoundBase>(nullptr, TEXT("/Game/ASTRA/Audio/SW_Entry_Plasma.SW_Entry_Plasma")))
		{
			PlasmaAudio = UGameplayStatics::CreateSound2D(this, S, 0.6f, 1.2f, 3.0f, nullptr, false, false);
			if (PlasmaAudio)
			{
				PlasmaAudio->Play(3.0f);
			}
		}
		if (UAstraShipSubsystem* Ship = GetWorld()->GetSubsystem<UAstraShipSubsystem>())
		{
			Ship->PublishEvent(FString::Printf(TEXT("flight: Eagle is climbing out of %s's atmosphere, back to orbit"), *Ship->SurfaceWorldName()), true);
		}
	}
}

void AAstraFighterPawn::Crash()
{
	// into the ground or the sea: the Falcon is lost; a Port Aurelius rescue craft picks the Captain up and a shuttle
	// brings the Captain back to the Aquila's flight deck
	Phase = EPhase::Ending;
	PhaseT = 0.f;
	bLandedEnd = false;
	if (APlayerCameraManager* Cam = UGameplayStatics::GetPlayerCameraManager(this, 0))
	{
		Cam->StartCameraFade(0.f, 1.f, 0.2f, FLinearColor(1.f, 0.85f, 0.7f), false, true);
	}
	if (UAstraShipSubsystem* Ship = GetWorld()->GetSubsystem<UAstraShipSubsystem>())
	{
		Ship->PublishEvent(FString::Printf(TEXT("flight: Eagle went down on %s — the Captain ejected and %s is bringing the Captain up "
		                                       "to the Aquila; the Falcon is lost"), *Ship->SurfaceWorldName(),
		                                  Ship->IsHomeWorld() ? TEXT("a Port Aurelius rescue craft") : TEXT("a search-and-rescue Wasp")), true);
		Ship->SetPlanetside(false);
	}
	if (UAstraBattleSubsystem* Battle = GetWorld()->GetSubsystem<UAstraBattleSubsystem>())
	{
		Battle->FalconLostPlanetside();
	}
}

void AAstraFighterPawn::ClimbOutPlanetside()
{
	APlayerController* PC = Cast<APlayerController>(GetController());
	APawn* W = Walker.Get();
	if (!PC || !W)
	{
		return;
	}
	// down the ladder on the port side, on the ground beside the Falcon
	const FVector Side = GetActorLocation() - GetActorRightVector() * 450.f + FVector(0.f, 0.f, 400.f);
	FHitResult Hit;
	FCollisionQueryParams Q(TEXT("ClimbDown"), false, this);
	FVector Feet = Side - FVector(0.f, 0.f, 600.f);
	if (GetWorld()->LineTraceSingleByChannel(Hit, Side, Side - FVector(0.f, 0.f, 5000.f), ECC_Visibility, Q))
	{
		Feet = Hit.ImpactPoint;
	}
	W->SetActorLocation(Feet + FVector(0.f, 0.f, 110.f), false, nullptr, ETeleportType::TeleportPhysics);
	W->SetActorHiddenInGame(false);
	W->SetActorEnableCollision(true);
	ShowHud(false);
	if (EngineAudio)
	{
		EngineAudio->Stop();
	}
	Phase = EPhase::Parked;
	PC->Possess(W);
	PC->SetControlRotation(FRotator(0.f, GetActorRotation().Yaw + 90.f, 0.f));
	if (UAstraShipSubsystem* Ship = GetWorld()->GetSubsystem<UAstraShipSubsystem>())
	{
		Ship->SetCaptainPlanetside(FString::Printf(TEXT("on foot on %s near %s, beside a landed Falcon of Alpha; the XO has the conn"), *Ship->SurfaceWorldName(), *Ship->SurfaceSiteName()));
	}
}

void AAstraFighterPawn::Reboard(APawn* InWalker)
{
	APlayerController* PC = Cast<APlayerController>(InWalker ? InWalker->GetController() : nullptr);
	if (Phase != EPhase::Parked || !PC)
	{
		return;
	}
	Walker = InWalker;
	InWalker->SetActorHiddenInGame(true);
	InWalker->SetActorEnableCollision(false);
	PC->Possess(this);
	Phase = EPhase::Landed;
	In = FAstraPilotInput();
	ShowHud(true);
	if (EngineAudio)
	{
		EngineAudio->Play();
	}
	if (UAstraShipSubsystem* Ship = GetWorld()->GetSubsystem<UAstraShipSubsystem>())
	{
		Ship->SetCaptainPlanetside(FString::Printf(TEXT("in a landed Falcon on %s near %s; the XO has the conn"), *Ship->SurfaceWorldName(), *Ship->SurfaceSiteName()));
	}
}

FAstraPilotStatus AAstraFighterPawn::PlanetStatus() const
{
	FAstraPilotStatus St;
	St.bFlying = true;
	St.SpeedMps = AirVel.Size() / 100.f;
	St.Throttle = In.Throttle;
	St.HullPct = AtmoHull;
	St.ShieldPct = 100.f;
	const UAstraShipSubsystem* Ship = GetWorld()->GetSubsystem<UAstraShipSubsystem>();
	St.HomeWorld = Ship ? Ship->SurfaceSite() : UAstraShipSubsystem::PlanetZone() + FieldSpot * 100.0;
	St.HomeRangeKm = FVector::Dist(GetActorLocation(), St.HomeWorld) / 100000.f;
	return St;
}
// ------------------------------------------------------------------------------------------------ ground fire
void AAstraFighterPawn::TickGroundFire(float Dt)
{
	UAstraShipSubsystem* Ship = GetWorld()->GetSubsystem<UAstraShipSubsystem>();
	if (!Ship || Ship->SurfaceOwner() != TEXT("mandate"))
	{
		return;
	}
	const FVector Site = Ship->SurfaceSite();
	const float DistKm = FVector::Dist2D(GetActorLocation(), Site) / 100000.f;
	const float AltM = (GetActorLocation().Z - Site.Z) / 100.f;
	if (DistKm > 14.f || AltM > 6000.f)
	{
		HostileT = FMath::Max(0.f, HostileT - Dt * 0.5f);
		return;
	}
	HostileT += Dt;
	// the challenge comes first (the field's warden on the radio): the guns open twenty seconds later, at once inside 5 km
	if (HostileT < 20.f && DistKm > 5.f)
	{
		return;
	}
	if (!bGroundFire)
	{
		bGroundFire = true;
		Ship->PublishEvent(FString::Printf(TEXT("flight: ground fire over %s — the Mandate's batteries are shooting at Eagle; flak is "
		                                        "bursting around the Falcon"), *Ship->SurfaceWorldName()), true);
	}
	FlakT -= Dt;
	if (FlakT > 0.f)
	{
		return;
	}
	FlakT = FMath::FRandRange(0.6f, 1.5f) * (DistKm < 6.f ? 0.6f : 1.f);
	// a burst near the Falcon, a little ahead (the gunners lead it): tighter the nearer the field and the lower it flies
	const float Spread = FMath::Lerp(35.f, 170.f, FMath::Clamp(DistKm / 14.f, 0.f, 1.f)) * FMath::Lerp(0.7f, 1.2f, FMath::Clamp(AltM / 6000.f, 0.f, 1.f));
	const FVector At = GetActorLocation() + AirVel * FMath::FRandRange(0.15f, 0.7f) + FMath::VRand() * FMath::FRandRange(0.25f, 1.f) * Spread * 100.f;
	SpawnFlak(At);
	const float Miss = FVector::Dist(At, GetActorLocation()) / 100.f;
	HitJolt = FMath::Max(HitJolt, FMath::Clamp(1.f - Miss / 140.f, 0.f, 1.f) * 0.8f);
	if (Miss < 45.f)
	{
		AtmoHull -= FMath::Lerp(24.f, 7.f, Miss / 45.f);
		if (USoundBase* S = LoadObject<USoundBase>(nullptr, TEXT("/Game/ASTRA/Audio/SW_Impact.SW_Impact")))
		{
			UGameplayStatics::PlaySound2D(this, S, 0.9f);
		}
		if (AtmoHull <= 0.f)
		{
			Crash();
			return;
		}
		const int32 Band = FMath::CeilToInt(AtmoHull / 25.f);
		if (Band < HullBand)
		{
			HullBand = Band;
			Ship->PublishEvent(FString::Printf(TEXT("flight: Eagle is hit by flak over %s — hull %d%%"), *Ship->SurfaceWorldName(),
			                                   FMath::RoundToInt(AtmoHull)), true);
		}
	}
}

void AAstraFighterPawn::SpawnFlak(const FVector& At)
{
	// the shell's flash, and the black puff it leaves hanging in the air; the crack of it, louder the nearer
	static const TCHAR* Mats[2] = {TEXT("/Game/ASTRA/Materials/M_FX_Blast.M_FX_Blast"), TEXT("/Game/ASTRA/Materials/M_FX_Smoke.M_FX_Smoke")};
	UStaticMesh* Sphere = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Sphere.Sphere"));
	for (int32 Piece = 0; Piece < 3; ++Piece)
	{
		const uint8 Kind = Piece == 0 ? 0 : 1;   // one flash, two puffs a few metres apart (a ragged cloud)
		UMaterialInterface* M = LoadObject<UMaterialInterface>(nullptr, Mats[Kind]);
		if (!Sphere || !M)
		{
			continue;
		}
		FActorSpawnParameters P;
		P.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
		const FVector Where = At + (Piece == 0 ? FVector::ZeroVector : FMath::VRand() * FMath::FRandRange(200.f, 450.f));
		AStaticMeshActor* A = GetWorld()->SpawnActor<AStaticMeshActor>(Where, FRotator(FMath::FRandRange(0.f, 360.f), FMath::FRandRange(0.f, 360.f), 0.f), P);
		if (!A)
		{
			continue;
		}
		A->SetMobility(EComponentMobility::Movable);
		UStaticMeshComponent* C = A->GetStaticMeshComponent();
		C->SetStaticMesh(Sphere);
		C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		C->SetCastShadow(false);
		UMaterialInstanceDynamic* MID = C->CreateAndSetMaterialInstanceDynamicFromMaterial(0, M);
		if (Kind == 0)
		{
			MID->SetVectorParameterValue(TEXT("Color"), FLinearColor(1.f, 0.5f, 0.18f));
			MID->SetScalarParameterValue(TEXT("Intensity"), 350.f);
		}
		A->SetActorScale3D(FVector(Kind == 0 ? 4.f : FMath::FRandRange(7.f, 10.f)));
		FlakFx.Add(A);
		FlakAge.Add(0.f);
		FlakKind.Add(Kind);
	}
	const float Dist = FVector::Dist(At, GetActorLocation()) / 100.f;
	if (USoundBase* S = LoadObject<USoundBase>(nullptr, TEXT("/Game/ASTRA/Audio/SW_PD_Burst.SW_PD_Burst")))
	{
		UGameplayStatics::PlaySound2D(this, S, FMath::Clamp(1.3f - Dist / 350.f, 0.15f, 1.f), FMath::FRandRange(0.42f, 0.55f));
	}
}

void AAstraFighterPawn::TickFlakFx(float Dt)
{
	for (int32 i = FlakFx.Num() - 1; i >= 0; --i)
	{
		FlakAge[i] += Dt;
		AStaticMeshActor* A = FlakFx[i];
		const float Life = FlakKind[i] == 0 ? 0.16f : 5.f;
		const float T = FlakAge[i] / Life;
		if (!A || T >= 1.f)
		{
			if (A)
			{
				A->Destroy();
			}
			FlakFx.RemoveAtSwap(i);
			FlakAge.RemoveAtSwap(i);
			FlakKind.RemoveAtSwap(i);
			continue;
		}
		UStaticMeshComponent* C = A->GetStaticMeshComponent();
		UMaterialInstanceDynamic* MID = C ? Cast<UMaterialInstanceDynamic>(C->GetMaterial(0)) : nullptr;
		if (FlakKind[i] == 0)
		{
			A->SetActorScale3D(FVector(FMath::Lerp(4.f, 11.f, T)));
			if (MID)
			{
				MID->SetScalarParameterValue(TEXT("Fade"), 1.f - T);
			}
		}
		else
		{
			A->SetActorScale3D(A->GetActorScale3D() * (1.f + 0.35f * Dt));   // the puff swells and drifts apart
			if (MID)
			{
				MID->SetScalarParameterValue(TEXT("Opacity"), 0.9f * FMath::Pow(1.f - T, 1.4f));
			}
		}
	}
}
