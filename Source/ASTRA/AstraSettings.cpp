// ASTRA — the player's settings.

#include "AstraSettings.h"
#include "AstraFonts.h"

#include "ASTRA.h"
#include "ASTRACharacter.h"
#include "AstraApiKey.h"
#include "AstraMindSubsystem.h"
#include "AudioDevice.h"
#include "Camera/CameraComponent.h"
#include "Engine/Engine.h"
#include "Engine/Font.h"
#include "Engine/GameInstance.h"
#include "Engine/GameViewportClient.h"
#include "Engine/World.h"
#include "GameFramework/GameUserSettings.h"
#include "HAL/IConsoleManager.h"
#include "Kismet/GameplayStatics.h"
#include "Misc/ConfigCacheIni.h"
#include "Styling/CoreStyle.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Layout/SScrollBox.h"
#include "Widgets/Layout/SSpacer.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/SOverlay.h"
#include "Widgets/Text/STextBlock.h"

namespace
{
	const TCHAR* SettingsSection = TEXT("ASTRA.Settings");
	const FLinearColor Ink(0.86f, 0.9f, 0.95f);
	const FLinearColor Dim(0.52f, 0.58f, 0.66f);
	const FLinearColor Accent(0.42f, 0.78f, 1.f);
	enum ERow : int32
	{
		RowGraphics, RowImage, RowRetina, RowFrameRate, RowDisplay, RowMotionBlur, RowFov,
		RowMaster, RowMusic, RowVoices, RowSubtitles,
		RowLanguage, RowFollow,
		RowSensitivity, RowInvert, RowTalkKey, RowOrdersKey,
		RowAiKey,
		RowBack, NumRowIds
	};
	const TCHAR* Rows[] = {TEXT("QUALITY"), TEXT("IMAGE"), TEXT("RETINA"), TEXT("FRAME RATE"), TEXT("DISPLAY"), TEXT("MOTION BLUR"), TEXT("FIELD OF VIEW"),
	                       TEXT("MASTER"), TEXT("MUSIC"), TEXT("VOICES"), TEXT("SUBTITLES"),
	                       TEXT("CREW LANGUAGE"), TEXT("FOLLOW MY VOICE"),
	                       TEXT("MOUSE SPEED"), TEXT("INVERT MOUSE"), TEXT("TALK KEY"), TEXT("ORDERS KEY"),
	                       TEXT("OPENROUTER KEY"),
	                       TEXT("BACK")};
	static_assert(UE_ARRAY_COUNT(Rows) == NumRowIds, "a name for every row");

	/** The page's sections: the row each one opens with, and its heading. */
	struct FSection { int32 First; const TCHAR* Title; };
	const FSection Sections[] = {{RowGraphics, TEXT("GRAPHICS")}, {RowMaster, TEXT("AUDIO")}, {RowLanguage, TEXT("LANGUAGE")},
	                             {RowSensitivity, TEXT("CONTROLS")}, {RowAiKey, TEXT("THE CREW'S MINDS")}};

	// RETINA (the 3D view at the display's own pixels instead of half of them, upscaled) is the Mac's: that is what the engine does on a Retina screen by
	// default. A game on Windows or Linux renders at its window's pixels, and has neither the row nor the setting. The difference is the preprocessor's,
	// not an `if` on a constant: MSVC may report the branch that cannot run as unreachable code (C4702), which this project's build settings make an error.
	// portable-ok: the rows and the notes of the other systems are the ones without RETINA
#if PLATFORM_MAC
	constexpr int32 SettingsShownRows[] = {RowGraphics, RowImage, RowRetina, RowFrameRate, RowDisplay, RowMotionBlur, RowFov, RowMaster, RowMusic, RowVoices,
	                                       RowSubtitles, RowLanguage, RowFollow, RowSensitivity, RowInvert, RowTalkKey, RowOrdersKey, RowAiKey, RowBack};
	const TCHAR* const SettingsThirtyNote = TEXT("30 frames a second: twice the time for each image, much sharper and cooler on a fanless Mac");
#else
	constexpr int32 SettingsShownRows[] = {RowGraphics, RowImage, RowFrameRate, RowDisplay, RowMotionBlur, RowFov, RowMaster, RowMusic, RowVoices,
	                                       RowSubtitles, RowLanguage, RowFollow, RowSensitivity, RowInvert, RowTalkKey, RowOrdersKey, RowAiKey, RowBack};
	const TCHAR* const SettingsThirtyNote = TEXT("30 frames a second: twice the time for each image, much sharper and cooler running");
#endif
	const int32 FrameRates[] = {30, 60, 120, 0};

	/** The rows this system shows, in order (every one on the Mac). */
	const TArray<int32>& VisibleRows()
	{
		static const TArray<int32> Visible(SettingsShownRows, UE_ARRAY_COUNT(SettingsShownRows));
		return Visible;
	}

	void SetCVar(const TCHAR* Name, float Value)
	{
		if (IConsoleVariable* V = IConsoleManager::Get().FindConsoleVariable(Name))
		{
			// over the platform's ini (MacEngine.ini sets the defaults the player now changes)
			V->Set(Value, ECVF_SetByGameOverride);
		}
	}

	/** The keys the game already gives other work: a TALK or ORDERS key cannot take them. */
	bool Reserved(const FKey& K)
	{
		static const TArray<FKey> Taken = {EKeys::W, EKeys::A, EKeys::S, EKeys::D, EKeys::E, EKeys::Escape, EKeys::Tab, EKeys::T, EKeys::F1, EKeys::F10,
		                                   EKeys::SpaceBar, EKeys::C, EKeys::LeftShift, EKeys::Z, EKeys::X, EKeys::R, EKeys::H, EKeys::Q, EKeys::One,
		                                   EKeys::Two, EKeys::Enter, EKeys::LeftMouseButton, EKeys::RightMouseButton, EKeys::MouseScrollUp,
		                                   EKeys::MouseScrollDown, EKeys::MouseX, EKeys::MouseY};
		return Taken.Contains(K);
	}

	UWorld* GameWorld()
	{
		return GEngine && GEngine->GameViewport ? GEngine->GameViewport->GetWorld() : nullptr;
	}
}

FAstraSettings& FAstraSettings::Get()
{
	static FAstraSettings S;
	static bool bLoaded = false;
	if (!bLoaded && GConfig)
	{
		bLoaded = true;
		GConfig->GetInt(SettingsSection, TEXT("Quality"), S.Quality, GGameUserSettingsIni);
		GConfig->GetInt(SettingsSection, TEXT("Image"), S.Image, GGameUserSettingsIni);
		// portable-ok: only the Mac has the Retina setting (the other systems' bRetina stays false: no row, no cvar, no key)
#if PLATFORM_MAC
		GConfig->GetBool(SettingsSection, TEXT("Retina"), S.bRetina, GGameUserSettingsIni);
#endif
		GConfig->GetInt(SettingsSection, TEXT("FrameRate"), S.FrameRate, GGameUserSettingsIni);
		GConfig->GetInt(SettingsSection, TEXT("Display"), S.Display, GGameUserSettingsIni);
		GConfig->GetBool(SettingsSection, TEXT("MotionBlur"), S.bMotionBlur, GGameUserSettingsIni);
		GConfig->GetFloat(SettingsSection, TEXT("Fov"), S.Fov, GGameUserSettingsIni);
		GConfig->GetFloat(SettingsSection, TEXT("Master"), S.Master, GGameUserSettingsIni);
		GConfig->GetFloat(SettingsSection, TEXT("Music"), S.Music, GGameUserSettingsIni);
		GConfig->GetFloat(SettingsSection, TEXT("Voices"), S.Voices, GGameUserSettingsIni);
		GConfig->GetBool(SettingsSection, TEXT("Subtitles"), S.bSubtitles, GGameUserSettingsIni);
		GConfig->GetString(SettingsSection, TEXT("Language"), S.Language, GGameUserSettingsIni);
		GConfig->GetBool(SettingsSection, TEXT("FollowVoice"), S.bFollowVoice, GGameUserSettingsIni);
		GConfig->GetFloat(SettingsSection, TEXT("MouseSensitivity"), S.MouseSensitivity, GGameUserSettingsIni);
		GConfig->GetBool(SettingsSection, TEXT("InvertMouse"), S.bInvertMouse, GGameUserSettingsIni);
		FString Talk, Orders;
		if (GConfig->GetString(SettingsSection, TEXT("TalkKey"), Talk, GGameUserSettingsIni) && FKey(FName(*Talk)).IsValid())
		{
			S.TalkKey = FKey(FName(*Talk));
		}
		if (GConfig->GetString(SettingsSection, TEXT("OrdersKey"), Orders, GGameUserSettingsIni) && FKey(FName(*Orders)).IsValid())
		{
			S.OrdersKey = FKey(FName(*Orders));
		}
		S.Quality = FMath::Clamp(S.Quality, -1, 3);
		S.Image = FMath::Clamp(S.Image, 0, 2);
		S.FrameRate = S.FrameRate == 0 ? 0 : (S.FrameRate <= 30 ? 30 : (S.FrameRate <= 60 ? 60 : 120));
		S.Display = FMath::Clamp(S.Display, 0, 2);
		S.Fov = FMath::Clamp(S.Fov, 70.f, 110.f);
		S.Master = FMath::Clamp(S.Master, 0.f, 1.f);
		S.Music = FMath::Clamp(S.Music, 0.f, 1.f);
		S.Voices = FMath::Clamp(S.Voices, 0.f, 1.f);
		S.MouseSensitivity = FMath::Clamp(S.MouseSensitivity, 0.2f, 2.f);
		const FString Lang = S.Language;
		if (!Languages().ContainsByPredicate([&Lang](const TPair<FString, FString>& L) { return L.Key == Lang; }))
		{
			S.Language = TEXT("en");
		}
	}
	return S;
}

void FAstraSettings::Save() const
{
	if (!GConfig)
	{
		return;
	}
	GConfig->SetInt(SettingsSection, TEXT("Quality"), Quality, GGameUserSettingsIni);
	GConfig->SetInt(SettingsSection, TEXT("Image"), Image, GGameUserSettingsIni);
	// portable-ok: only the Mac has the Retina setting
#if PLATFORM_MAC
	GConfig->SetBool(SettingsSection, TEXT("Retina"), bRetina, GGameUserSettingsIni);
#endif
	GConfig->SetInt(SettingsSection, TEXT("FrameRate"), FrameRate, GGameUserSettingsIni);
	GConfig->SetInt(SettingsSection, TEXT("Display"), Display, GGameUserSettingsIni);
	GConfig->SetBool(SettingsSection, TEXT("MotionBlur"), bMotionBlur, GGameUserSettingsIni);
	GConfig->SetFloat(SettingsSection, TEXT("Fov"), Fov, GGameUserSettingsIni);
	GConfig->SetFloat(SettingsSection, TEXT("Master"), Master, GGameUserSettingsIni);
	GConfig->SetFloat(SettingsSection, TEXT("Music"), Music, GGameUserSettingsIni);
	GConfig->SetFloat(SettingsSection, TEXT("Voices"), Voices, GGameUserSettingsIni);
	GConfig->SetBool(SettingsSection, TEXT("Subtitles"), bSubtitles, GGameUserSettingsIni);
	GConfig->SetString(SettingsSection, TEXT("Language"), *Language, GGameUserSettingsIni);
	GConfig->SetBool(SettingsSection, TEXT("FollowVoice"), bFollowVoice, GGameUserSettingsIni);
	GConfig->SetFloat(SettingsSection, TEXT("MouseSensitivity"), MouseSensitivity, GGameUserSettingsIni);
	GConfig->SetBool(SettingsSection, TEXT("InvertMouse"), bInvertMouse, GGameUserSettingsIni);
	GConfig->SetString(SettingsSection, TEXT("TalkKey"), *TalkKey.GetFName().ToString(), GGameUserSettingsIni);
	GConfig->SetString(SettingsSection, TEXT("OrdersKey"), *OrdersKey.GetFName().ToString(), GGameUserSettingsIni);
	GConfig->Flush(false, GGameUserSettingsIni);
}

const TArray<TPair<FString, FString>>& FAstraSettings::Languages()
{
	// the seven the crew's voices speak natively (Pocket TTS); the Captain may speak others: with FOLLOW MY VOICE the crew answers in them too
	static const TArray<TPair<FString, FString>> L = {{TEXT("en"), TEXT("ENGLISH")}, {TEXT("it"), TEXT("ITALIANO")}, {TEXT("es"), TEXT("ESPAÑOL")},
	                                                  {TEXT("fr"), TEXT("FRANÇAIS")}, {TEXT("de"), TEXT("DEUTSCH")}, {TEXT("pt"), TEXT("PORTUGUÊS")},
	                                                  {TEXT("nl"), TEXT("NEDERLANDS")}};
	return L;
}

FString FAstraSettings::KeyName(const FKey& K)
{
	if (K == EKeys::ThumbMouseButton)
	{
		return TEXT("Mouse 4");
	}
	if (K == EKeys::ThumbMouseButton2)
	{
		return TEXT("Mouse 5");
	}
	if (K == EKeys::MiddleMouseButton)
	{
		return TEXT("Mouse 3");
	}
	return K.GetDisplayName(false).ToString();
}

float FAstraSettings::FloorOf(int32 InImage)
{
	return InImage == 0 ? 70.f : (InImage == 1 ? 55.f : 40.f);
}

float FAstraSettings::EngineFloor() const
{
	return bRetina ? FMath::Max(33.f, FloorOf(Image) * 0.5f) : FloorOf(Image);
}

void FAstraSettings::Apply(bool bWindowMode) const
{
	if (UGameUserSettings* GS = GEngine ? GEngine->GetGameUserSettings() : nullptr)
	{
		// portable-ok: a PC can be anything from a laptop to a tower: on the first start the engine measures it and picks the quality levels; the Mac keeps
		// its profile (Config/Mac), measured on the MacBook Air the game is tuned for
#if PLATFORM_WINDOWS
		bool bBenchmarked = false;
		GConfig->GetBool(SettingsSection, TEXT("Benchmarked"), bBenchmarked, GGameUserSettingsIni);
		if (Quality < 0 && !bBenchmarked)
		{
			GS->RunHardwareBenchmark();
			GS->ApplyHardwareBenchmarkResults();
			GConfig->SetBool(SettingsSection, TEXT("Benchmarked"), true, GGameUserSettingsIni);
			UE_LOG(LogASTRA, Log, TEXT("[Settings] first start: the machine was measured, quality %d"), GS->GetOverallScalabilityLevel());
		}
#endif
		if (Quality >= 0 && GS->GetOverallScalabilityLevel() != Quality)
		{
			GS->SetOverallScalabilityLevel(Quality);
		}
		GS->SetFrameRateLimit((float)FrameRate);
		const EWindowMode::Type Mode = Display == 0 ? EWindowMode::Fullscreen : (Display == 1 ? EWindowMode::WindowedFullscreen : EWindowMode::Windowed);
		if (bWindowMode && GS->GetFullscreenMode() != Mode && GEngine->GameViewport && !FParse::Param(FCommandLine::Get(), TEXT("windowed")))
		{
			GS->SetFullscreenMode(Mode);
			if (Mode != EWindowMode::Windowed)
			{
				GS->SetScreenResolution(GS->GetDesktopResolution());
			}
			GS->ApplyResolutionSettings(false);
		}
		GS->ApplyNonResolutionSettings();
		GS->SaveSettings();
	}
	// the dynamic resolution keeps the frame inside its time: at 30 frames a second it has twice the time for each image (no limit: it keeps 60 at least)
	SetCVar(TEXT("r.DynamicRes.FrameTimeBudget"), 1000.f / (float)(FrameRate > 0 ? FrameRate : 60));
	// the upscaler's output (the Mac): the display's own pixels, or (0) the engine's default, half of them on a Retina screen, doubled by the window
	// (the user saw the doubled image as pixelated: a 1710 x 1107 picture spread over a 3420 x 2214 panel)
	// portable-ok: the Mac's Retina output; the other systems keep the engine's own
#if PLATFORM_MAC
	SetCVar(TEXT("r.SecondaryScreenPercentage.GameViewport"), bRetina ? 100.f : 0.f);
#endif
	SetCVar(TEXT("r.DynamicRes.MinScreenPercentage"), EngineFloor());
	SetCVar(TEXT("r.MotionBlurQuality"), bMotionBlur ? 4.f : 0.f);
	if (GEngine)
	{
		if (FAudioDeviceHandle Audio = GEngine->GetMainAudioDevice())
		{
			Audio->SetTransientPrimaryVolume(Master);
		}
	}
	if (UWorld* W = GameWorld())
	{
		if (AASTRACharacter* C = Cast<AASTRACharacter>(UGameplayStatics::GetPlayerPawn(W, 0)))
		{
			C->GetFirstPersonCameraComponent()->SetFieldOfView(Fov);
		}
	}
	UE_LOG(LogASTRA, Log, TEXT("[Settings] quality %d, image floor %.0f%%, retina output %s, %d fps, display %d, motion blur %s, fov %.0f, master %.0f%%, music %.0f%%, voices %.0f%%, subtitles %s, language %s (%s), mouse %.1f%s, talk %s, orders %s"),
	       Quality, EngineFloor(), bRetina ? TEXT("on") : TEXT("off"), FrameRate, Display, bMotionBlur ? TEXT("on") : TEXT("off"), Fov, Master * 100.f, Music * 100.f,
	       Voices * 100.f, bSubtitles ? TEXT("on") : TEXT("off"), *Language, bFollowVoice ? TEXT("follows the voice") : TEXT("fixed"), MouseSensitivity,
	       bInvertMouse ? TEXT(" inverted") : TEXT(""), *KeyName(TalkKey), *KeyName(OrdersKey));
}

// --------------------------------------------------------------------------------------------------- the page
void SAstraSettingsPage::Construct(const FArguments& Args)
{
	static_assert(UE_ARRAY_COUNT(Buttons) >= NumRowIds, "a button for every row");
	OnBack = Args._OnBack;
	OnApiKey = Args._OnApiKey;
	UFont* Title = AstraFonts::Title();
	UFont* Mono = AstraFonts::Mono();
	auto TitleFont = [Title](int32 Size) { return Title ? FSlateFontInfo(Title, Size) : FCoreStyle::GetDefaultFontStyle("Bold", Size); };
	auto MonoFont = [Mono](int32 Size) { return Mono ? FSlateFontInfo(Mono, Size) : FCoreStyle::GetDefaultFontStyle("Mono", Size); };

	SAssignNew(Scroll, SScrollBox);
	for (const int32 Row : VisibleRows())
	{
		for (const FSection& Sec : Sections)
		{
			if (Sec.First == Row)
			{
				Scroll->AddSlot().Padding(0, Row == RowGraphics ? 0 : 18, 0, 4)
				[
					SNew(STextBlock).Font(MonoFont(12)).ColorAndOpacity(Accent).Text(FText::FromString(Sec.Title))
				];
			}
		}
		Scroll->AddSlot().Padding(0, Row == RowBack ? 22 : 3)
		[
			SAssignNew(Buttons[Row], SButton)
			.ButtonStyle(&FCoreStyle::Get().GetWidgetStyle<FButtonStyle>("NoBorder"))
			.OnClicked_Lambda([this, Row]() { Selected = Row; Change(Row, +1); return FReply::Handled(); })
			[
				SNew(SVerticalBox)
				+ SVerticalBox::Slot().AutoHeight()
				[
					SNew(SHorizontalBox)
					+ SHorizontalBox::Slot().AutoWidth()
					[
						SNew(SBox).WidthOverride(280.f)
						[
							SNew(STextBlock).Font(TitleFont(22)).Text(FText::FromString(Rows[Row]))
							.ColorAndOpacity_Lambda([this, Row]() { return FSlateColor(IsLit(Row) ? Accent : Ink); })
						]
					]
					+ SHorizontalBox::Slot().AutoWidth()
					[
						SNew(STextBlock).Font(TitleFont(22)).Text_Lambda([this, Row]() { return FText::FromString(ValueOf(Row)); })
						.ColorAndOpacity_Lambda([this, Row]() { return FSlateColor(IsLit(Row) ? Accent : Ink); })
					]
				]
				+ SVerticalBox::Slot().AutoHeight().Padding(2, 0, 0, 0)
				[
					SNew(STextBlock).Font(MonoFont(10)).ColorAndOpacity(Dim).AutoWrapText(true)
					.Text_Lambda([this, Row]() { return FText::FromString(NoteOf(Row)); })
					.Visibility_Lambda([this, Row]() { return NoteOf(Row).IsEmpty() ? EVisibility::Collapsed : EVisibility::Visible; })
				]
			]
		];
	}

	ChildSlot
	[
		SNew(SOverlay)
		+ SOverlay::Slot().HAlign(HAlign_Left).VAlign(VAlign_Fill)
		[
			SNew(SBox).WidthOverride(700.f)
			[
				SNew(SBorder).BorderImage(FCoreStyle::Get().GetBrush("WhiteBrush")).BorderBackgroundColor(FLinearColor(0.004f, 0.006f, 0.01f, 0.86f))
				.Padding(FMargin(72, 70, 48, 40))
				[
					SNew(SVerticalBox)
					+ SVerticalBox::Slot().AutoHeight()
					[
						SNew(STextBlock).Font(TitleFont(56)).ColorAndOpacity(Ink).Text(FText::FromString(TEXT("SETTINGS")))
					]
					+ SVerticalBox::Slot().AutoHeight().Padding(4, 0, 0, 18)
					[
						SNew(STextBlock).Font(MonoFont(12)).ColorAndOpacity(Accent)
						.Text(FText::FromString(TEXT("CLICK OR ENTER: NEXT  ·  ARROWS  ·  ESC: DONE")))
					]
					+ SVerticalBox::Slot().FillHeight(1.f) [ Scroll.ToSharedRef() ]
				]
			]
		]
	];
}

bool SAstraSettingsPage::IsLit(int32 Row) const
{
	// the row under the mouse, else the one the arrows chose
	for (const int32 i : VisibleRows())
	{
		if (Buttons[i].IsValid() && Buttons[i]->IsHovered())
		{
			return i == Row;
		}
	}
	return Selected == Row;
}

FString SAstraSettingsPage::ValueOf(int32 Row) const
{
	const FAstraSettings& S = FAstraSettings::Get();
	static const TCHAR* Quality[] = {TEXT("LOW"), TEXT("MEDIUM"), TEXT("HIGH"), TEXT("EPIC")};
	static const TCHAR* Image[] = {TEXT("SHARP"), TEXT("BALANCED"), TEXT("SMOOTH")};
	static const TCHAR* Display[] = {TEXT("FULL SCREEN"), TEXT("BORDERLESS"), TEXT("WINDOW")};
	if (Capturing == Row)
	{
		return TEXT("PRESS A KEY...");
	}
	switch (Row)
	{
	case RowGraphics:
	{
		int32 Q = S.Quality;
		if (Q < 0 && GEngine && GEngine->GetGameUserSettings())
		{
			Q = GEngine->GetGameUserSettings()->GetOverallScalabilityLevel();
		}
		return Q >= 0 && Q <= 3 ? Quality[Q] : TEXT("CUSTOM");
	}
	case RowImage: return Image[S.Image];
	case RowRetina: return S.bRetina ? TEXT("FULL") : TEXT("HALF");
	case RowFrameRate: return S.FrameRate > 0 ? FString::Printf(TEXT("%d"), S.FrameRate) : FString(TEXT("NO LIMIT"));
	case RowDisplay: return Display[S.Display];
	case RowMotionBlur: return S.bMotionBlur ? TEXT("ON") : TEXT("OFF");
	case RowFov: return FString::Printf(TEXT("%d°"), FMath::RoundToInt(S.Fov));
	case RowMaster: return FString::Printf(TEXT("%d%%"), FMath::RoundToInt(S.Master * 100.f));
	case RowMusic: return FString::Printf(TEXT("%d%%"), FMath::RoundToInt(S.Music * 100.f));
	case RowVoices: return FString::Printf(TEXT("%d%%"), FMath::RoundToInt(S.Voices * 100.f));
	case RowSubtitles: return S.bSubtitles ? TEXT("ON") : TEXT("OFF");
	case RowLanguage:
	{
		const TPair<FString, FString>* L = FAstraSettings::Languages().FindByPredicate([&S](const TPair<FString, FString>& P) { return P.Key == S.Language; });
		return L ? L->Value : S.Language.ToUpper();
	}
	case RowFollow: return S.bFollowVoice ? TEXT("ON") : TEXT("OFF");
	case RowSensitivity: return FString::Printf(TEXT("%.1f"), S.MouseSensitivity);
	case RowInvert: return S.bInvertMouse ? TEXT("ON") : TEXT("OFF");
	case RowTalkKey: return FAstraSettings::KeyName(S.TalkKey).ToUpper() + TEXT("  (HOLD)");
	case RowOrdersKey: return FAstraSettings::KeyName(S.OrdersKey).ToUpper() + TEXT("  (HOLD)");
	case RowAiKey: return FAstraApiKey::Summary();
	default: return FString();
	}
}

FString SAstraSettingsPage::NoteOf(int32 Row) const
{
	const FAstraSettings& S = FAstraSettings::Get();
	switch (Row)
	{
	case RowGraphics: return TEXT("HIGH and EPIC light the ship with Lumen and full shadows; LOW and MEDIUM trade that light for speed");
	case RowImage: return S.Image == 0 ? TEXT("the image never drops below 70% resolution: the sharpest, and in a heavy battle the frame rate may fall")
	             : S.Image == 1 ? TEXT("never below 55% resolution: sharp, and smooth in most battles")
	                            : TEXT("down to 40% resolution when the battle is heavy: the frame rate first");
	case RowRetina: return S.bRetina ? TEXT("the picture is rebuilt at your display's own pixels: the sharpest on a Retina Mac, a few milliseconds more")
	                                 : TEXT("half the display's pixels, doubled by the window: softer, the frame rate first");
	case RowFrameRate: return S.FrameRate == 30 ? SettingsThirtyNote : S.FrameRate == 60 ? TEXT("60 frames a second: smooth motion; the resolution adapts to keep it")
	                        : S.FrameRate == 120 ? TEXT("for a fast display and a strong graphics card: the resolution drops to keep 120")
	                                             : TEXT("as many frames as the machine makes (the resolution still keeps 60 at least)");
	case RowDisplay: return S.Display == 2 ? TEXT("a window you can move and resize") : TEXT("the whole screen");
	case RowFov: return TEXT("how wide the Captain's eyes see: wider shows more of the bridge, narrower is closer to a film");
	case RowLanguage: return TEXT("the language the crew speaks when a session begins");
	case RowFollow: return S.bFollowVoice ? TEXT("the crew answers in the language you speak to them (any language: they follow you)")
	                                      : TEXT("the crew always speaks the language above, whatever you speak");
	case RowTalkKey: return TEXT("hold it and speak to the crew; Enter here, then press the key you want (Esc: keep this one)");
	case RowOrdersKey: return TEXT("hold it for the orders wheel; Enter here, then press the key you want (Esc: keep this one)");
	case RowAiKey: return FAstraApiKey::Note();
	default: return FString();
	}
}

void SAstraSettingsPage::Change(int32 Row, int32 Step)
{
	FAstraSettings& S = FAstraSettings::Get();
	bool bTellMind = false;
	switch (Row)
	{
	case RowGraphics:
	{
		int32 Q = S.Quality;
		if (Q < 0 && GEngine && GEngine->GetGameUserSettings())
		{
			Q = FMath::Clamp(GEngine->GetGameUserSettings()->GetOverallScalabilityLevel(), 0, 3);
		}
		S.Quality = (FMath::Max(Q, 0) + Step + 4) % 4;
		break;
	}
	case RowImage: S.Image = (S.Image + Step + 3) % 3; break;
	case RowRetina: S.bRetina = !S.bRetina; break;
	case RowFrameRate:
	{
		int32 At = 1;
		for (int32 i = 0; i < 4; ++i)
		{
			At = FrameRates[i] == S.FrameRate ? i : At;
		}
		S.FrameRate = FrameRates[(At + Step + 4) % 4];
		break;
	}
	case RowDisplay: S.Display = (S.Display + Step + 3) % 3; S.Apply(true); S.Save(); return;
	case RowMotionBlur: S.bMotionBlur = !S.bMotionBlur; break;
	case RowFov: S.Fov = 70.f + FMath::Fmod(FMath::RoundToFloat((S.Fov - 70.f) / 5.f) + Step + 9.f, 9.f) * 5.f; break;
	case RowMaster: S.Master = FMath::Fmod(FMath::RoundToFloat(S.Master * 10.f + Step + 11.f), 11.f) / 10.f; break;
	case RowMusic: S.Music = FMath::Fmod(FMath::RoundToFloat(S.Music * 10.f + Step + 11.f), 11.f) / 10.f; break;
	case RowVoices: S.Voices = FMath::Fmod(FMath::RoundToFloat(S.Voices * 10.f + Step + 11.f), 11.f) / 10.f; break;
	case RowSubtitles: S.bSubtitles = !S.bSubtitles; break;
	case RowLanguage:
	{
		const TArray<TPair<FString, FString>>& L = FAstraSettings::Languages();
		const int32 At = FMath::Max(0, L.IndexOfByPredicate([&S](const TPair<FString, FString>& P) { return P.Key == S.Language; }));
		S.Language = L[(At + Step + L.Num()) % L.Num()].Key;
		bTellMind = true;
		break;
	}
	case RowFollow: S.bFollowVoice = !S.bFollowVoice; bTellMind = true; break;
	case RowSensitivity: S.MouseSensitivity = FMath::Clamp(FMath::RoundToFloat(S.MouseSensitivity * 10.f + Step) / 10.f, 0.2f, 2.f); break;
	case RowInvert: S.bInvertMouse = !S.bInvertMouse; break;
	case RowTalkKey:
	case RowOrdersKey:
		Capturing = Row;                       // the next key pressed (or a mouse button but the left one) is the new key
		return;
	case RowAiKey:
		OnApiKey.ExecuteIfBound();
		return;
	default: OnBack.ExecuteIfBound(); return;
	}
	S.Apply();
	S.Save();
	if (bTellMind)
	{
		if (UWorld* W = GameWorld())
		{
			if (UAstraMindSubsystem* M = W->GetGameInstance() ? W->GetGameInstance()->GetSubsystem<UAstraMindSubsystem>() : nullptr)
			{
				M->SendSettings();
			}
		}
	}
}

void SAstraSettingsPage::Bind(const FKey& K)
{
	FAstraSettings& S = FAstraSettings::Get();
	const int32 Row = Capturing;
	Capturing = -1;
	if (!K.IsValid() || Reserved(K) || K.IsAnalog() || K.IsTouch() || K.IsGesture())
	{
		return;                                // (a key the game uses for something else: the old one stays)
	}
	FKey& Mine = Row == RowTalkKey ? S.TalkKey : S.OrdersKey;
	FKey& Other = Row == RowTalkKey ? S.OrdersKey : S.TalkKey;
	if (K == Other)
	{
		Other = Mine;                          // the two keys swap
	}
	Mine = K;
	S.Save();
	S.Apply();
}

FReply SAstraSettingsPage::OnKeyDown(const FGeometry& Geometry, const FKeyEvent& Key)
{
	const FKey K = Key.GetKey();
	if (Capturing >= 0)
	{
		if (K == EKeys::Escape)
		{
			Capturing = -1;
		}
		else
		{
			Bind(K);
		}
		return FReply::Handled();
	}
	if (K == EKeys::Escape)
	{
		OnBack.ExecuteIfBound();
		return FReply::Handled();
	}
	if (K == EKeys::Up || K == EKeys::Down)
	{
		const TArray<int32>& Visible = VisibleRows();
		const int32 At = FMath::Max(0, Visible.IndexOfByKey(Selected));
		Selected = Visible[(At + (K == EKeys::Up ? -1 : 1) + Visible.Num()) % Visible.Num()];
		if (Scroll.IsValid() && Buttons[Selected].IsValid())
		{
			Scroll->ScrollDescendantIntoView(Buttons[Selected], true, EDescendantScrollDestination::IntoView);
		}
		return FReply::Handled();
	}
	if (K == EKeys::Left || K == EKeys::Right || K == EKeys::Enter)
	{
		Change(Selected, K == EKeys::Left ? -1 : 1);
		return FReply::Handled();
	}
	return FReply::Unhandled();
}

FReply SAstraSettingsPage::OnMouseButtonDown(const FGeometry& Geometry, const FPointerEvent& Mouse)
{
	if (Capturing >= 0 && Mouse.GetEffectingButton() != EKeys::LeftMouseButton)
	{
		Bind(Mouse.GetEffectingButton());     // (a mouse's side button makes a good push-to-talk)
		return FReply::Handled();
	}
	return SCompoundWidget::OnMouseButtonDown(Geometry, Mouse);
}
