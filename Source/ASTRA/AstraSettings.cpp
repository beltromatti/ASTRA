// ASTRA — the player's settings.

#include "AstraSettings.h"

#include "ASTRA.h"
#include "Engine/Engine.h"
#include "Engine/Font.h"
#include "GameFramework/GameUserSettings.h"
#include "HAL/IConsoleManager.h"
#include "Misc/ConfigCacheIni.h"
#include "Styling/CoreStyle.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
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
	enum ERow : int32 { RowGraphics, RowImage, RowRetina, RowFrameRate, RowMusic, RowVoices, RowSubtitles, RowBack, NumRowIds };
	const TCHAR* Rows[] = {TEXT("GRAPHICS"), TEXT("IMAGE"), TEXT("RETINA"), TEXT("FRAME RATE"), TEXT("MUSIC"), TEXT("VOICES"), TEXT("SUBTITLES"), TEXT("BACK")};
	static_assert(UE_ARRAY_COUNT(Rows) == NumRowIds, "a name for every row");

	// RETINA (the 3D view at the display's own pixels instead of half of them, upscaled) is the Mac's: that is what the engine does on a Retina screen by
	// default. A game on Windows or Linux renders at its window's pixels, and has neither the row nor the setting.
	constexpr bool bMac = PLATFORM_MAC;   // portable-ok: the page and the settings of the other systems are the ones without RETINA

	/** The rows this system shows, in order (every one on the Mac). */
	const TArray<int32>& VisibleRows()
	{
		static const TArray<int32> Visible = []()
		{
			TArray<int32> V;
			for (int32 Id = 0; Id < NumRowIds; ++Id)
			{
				if (Id != RowRetina || bMac)
				{
					V.Add(Id);
				}
			}
			return V;
		}();
		return Visible;
	}

	/** The Retina output is on: chosen, and a system that has it. */
	bool RetinaOutput(const FAstraSettings& S)
	{
		return bMac && S.bRetina;
	}

	void SetCVar(const TCHAR* Name, float Value)
	{
		if (IConsoleVariable* V = IConsoleManager::Get().FindConsoleVariable(Name))
		{
			// over the platform's ini (MacEngine.ini sets the defaults the player now changes)
			V->Set(Value, ECVF_SetByGameOverride);
		}
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
		GConfig->GetBool(SettingsSection, TEXT("Retina"), S.bRetina, GGameUserSettingsIni);
		GConfig->GetInt(SettingsSection, TEXT("FrameRate"), S.FrameRate, GGameUserSettingsIni);
		GConfig->GetFloat(SettingsSection, TEXT("Music"), S.Music, GGameUserSettingsIni);
		GConfig->GetFloat(SettingsSection, TEXT("Voices"), S.Voices, GGameUserSettingsIni);
		GConfig->GetBool(SettingsSection, TEXT("Subtitles"), S.bSubtitles, GGameUserSettingsIni);
		S.Quality = FMath::Clamp(S.Quality, -1, 3);
		S.Image = FMath::Clamp(S.Image, 0, 2);
		S.FrameRate = S.FrameRate <= 30 ? 30 : 60;
		S.Music = FMath::Clamp(S.Music, 0.f, 1.f);
		S.Voices = FMath::Clamp(S.Voices, 0.f, 1.f);
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
	GConfig->SetBool(SettingsSection, TEXT("Retina"), bRetina, GGameUserSettingsIni);
	GConfig->SetInt(SettingsSection, TEXT("FrameRate"), FrameRate, GGameUserSettingsIni);
	GConfig->SetFloat(SettingsSection, TEXT("Music"), Music, GGameUserSettingsIni);
	GConfig->SetFloat(SettingsSection, TEXT("Voices"), Voices, GGameUserSettingsIni);
	GConfig->SetBool(SettingsSection, TEXT("Subtitles"), bSubtitles, GGameUserSettingsIni);
	GConfig->Flush(false, GGameUserSettingsIni);
}

float FAstraSettings::FloorOf(int32 InImage)
{
	return InImage == 0 ? 70.f : (InImage == 1 ? 55.f : 40.f);
}

float FAstraSettings::EngineFloor() const
{
	return RetinaOutput(*this) ? FMath::Max(33.f, FloorOf(Image) * 0.5f) : FloorOf(Image);
}

void FAstraSettings::Apply() const
{
	if (UGameUserSettings* GS = GEngine ? GEngine->GetGameUserSettings() : nullptr)
	{
		if (Quality >= 0 && GS->GetOverallScalabilityLevel() != Quality)
		{
			GS->SetOverallScalabilityLevel(Quality);
		}
		GS->SetFrameRateLimit((float)FrameRate);
		GS->ApplyNonResolutionSettings();
		GS->SaveSettings();
	}
	// the dynamic resolution keeps the frame inside its time: at 30 frames a second it has twice the time for each image
	SetCVar(TEXT("r.DynamicRes.FrameTimeBudget"), 1000.f / (float)FrameRate);
	// the upscaler's output (the Mac): the display's own pixels, or (0) the engine's default, half of them on a Retina screen, doubled by the window
	// (the user saw the doubled image as pixelated: a 1710 x 1107 picture spread over a 3420 x 2214 panel)
	if (bMac)
	{
		SetCVar(TEXT("r.SecondaryScreenPercentage.GameViewport"), bRetina ? 100.f : 0.f);
	}
	SetCVar(TEXT("r.DynamicRes.MinScreenPercentage"), EngineFloor());
	UE_LOG(LogASTRA, Log, TEXT("[Settings] quality %d, image floor %.0f%%, retina output %s, %d fps, music %.0f%%, voices %.0f%%, subtitles %s"), Quality,
	       EngineFloor(), !bMac ? TEXT("n/a") : bRetina ? TEXT("on") : TEXT("off"), FrameRate, Music * 100.f, Voices * 100.f, bSubtitles ? TEXT("on") : TEXT("off"));
}

// --------------------------------------------------------------------------------------------------- the page
void SAstraSettingsPage::Construct(const FArguments& Args)
{
	static_assert(UE_ARRAY_COUNT(Buttons) == NumRowIds, "a button for every row: BACK's was one past the end of a seven-button array");
	OnBack = Args._OnBack;
	UFont* Title = LoadObject<UFont>(nullptr, TEXT("/Game/ASTRA/UI/Fonts/F_ASTRA_Title.F_ASTRA_Title"));
	UFont* Mono = LoadObject<UFont>(nullptr, TEXT("/Game/ASTRA/UI/Fonts/F_ASTRA_Mono.F_ASTRA_Mono"));
	auto TitleFont = [Title](int32 Size) { return Title ? FSlateFontInfo(Title, Size) : FCoreStyle::GetDefaultFontStyle("Bold", Size); };
	auto MonoFont = [Mono](int32 Size) { return Mono ? FSlateFontInfo(Mono, Size) : FCoreStyle::GetDefaultFontStyle("Mono", Size); };

	TSharedRef<SVerticalBox> List = SNew(SVerticalBox);
	for (const int32 Row : VisibleRows())
	{
		List->AddSlot().AutoHeight().Padding(0, Row == RowBack ? 22 : 5)
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
						SNew(SBox).WidthOverride(250.f)
						[
							SNew(STextBlock).Font(TitleFont(24)).Text(FText::FromString(Rows[Row]))
							.ColorAndOpacity_Lambda([this, Row]() { return FSlateColor(IsLit(Row) ? Accent : Ink); })
						]
					]
					+ SHorizontalBox::Slot().AutoWidth()
					[
						SNew(STextBlock).Font(TitleFont(24)).Text_Lambda([this, Row]() { return FText::FromString(ValueOf(Row)); })
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
			SNew(SBox).WidthOverride(620.f)
			[
				SNew(SBorder).BorderImage(FCoreStyle::Get().GetBrush("WhiteBrush")).BorderBackgroundColor(FLinearColor(0.004f, 0.006f, 0.01f, 0.84f))
				.Padding(FMargin(72, 90, 48, 54))
				[
					SNew(SVerticalBox)
					+ SVerticalBox::Slot().AutoHeight()
					[
						SNew(STextBlock).Font(TitleFont(60)).ColorAndOpacity(Ink).Text(FText::FromString(TEXT("SETTINGS")))
					]
					+ SVerticalBox::Slot().AutoHeight().Padding(4, 0, 0, 0)
					[
						SNew(STextBlock).Font(MonoFont(12)).ColorAndOpacity(Accent)
						.Text(FText::FromString(TEXT("CLICK OR ENTER: NEXT  ·  ARROWS  ·  ESC: DONE")))
					]
					+ SVerticalBox::Slot().FillHeight(0.5f) [ SNew(SSpacer) ]
					+ SVerticalBox::Slot().AutoHeight() [ List ]
					+ SVerticalBox::Slot().FillHeight(1.f) [ SNew(SSpacer) ]
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
	case RowFrameRate: return FString::Printf(TEXT("%d"), S.FrameRate);
	case RowMusic: return FString::Printf(TEXT("%d%%"), FMath::RoundToInt(S.Music * 100.f));
	case RowVoices: return FString::Printf(TEXT("%d%%"), FMath::RoundToInt(S.Voices * 100.f));
	case RowSubtitles: return S.bSubtitles ? TEXT("ON") : TEXT("OFF");
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
	case RowFrameRate: return S.FrameRate == 30 ? (bMac ? TEXT("30 frames a second: twice the time for each image, much sharper and cooler on a fanless Mac")
	                                                    : TEXT("30 frames a second: twice the time for each image, much sharper and cooler running"))
	                                            : TEXT("60 frames a second: the smoothest motion; the resolution adapts to keep it");
	default: return FString();
	}
}

void SAstraSettingsPage::Change(int32 Row, int32 Step)
{
	FAstraSettings& S = FAstraSettings::Get();
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
	case RowFrameRate: S.FrameRate = S.FrameRate == 60 ? 30 : 60; break;
	case RowMusic: S.Music = FMath::Fmod(FMath::RoundToFloat(S.Music * 10.f + Step + 11.f), 11.f) / 10.f; break;
	case RowVoices: S.Voices = FMath::Fmod(FMath::RoundToFloat(S.Voices * 10.f + Step + 11.f), 11.f) / 10.f; break;
	case RowSubtitles: S.bSubtitles = !S.bSubtitles; break;
	default: OnBack.ExecuteIfBound(); return;
	}
	S.Apply();
	S.Save();
}

FReply SAstraSettingsPage::OnKeyDown(const FGeometry& Geometry, const FKeyEvent& Key)
{
	const FKey K = Key.GetKey();
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
		return FReply::Handled();
	}
	if (K == EKeys::Left || K == EKeys::Right || K == EKeys::Enter)
	{
		Change(Selected, K == EKeys::Left ? -1 : 1);
		return FReply::Handled();
	}
	return FReply::Unhandled();
}
