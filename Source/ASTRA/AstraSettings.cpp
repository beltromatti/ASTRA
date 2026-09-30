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
	const TCHAR* Section = TEXT("ASTRA.Settings");
	const FLinearColor Ink(0.86f, 0.9f, 0.95f);
	const FLinearColor Dim(0.52f, 0.58f, 0.66f);
	const FLinearColor Accent(0.42f, 0.78f, 1.f);
	const TCHAR* Rows[] = {TEXT("GRAPHICS"), TEXT("IMAGE"), TEXT("FRAME RATE"), TEXT("MUSIC"), TEXT("VOICES"), TEXT("SUBTITLES"), TEXT("BACK")};
	constexpr int32 NumRows = UE_ARRAY_COUNT(Rows);

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
		GConfig->GetInt(Section, TEXT("Quality"), S.Quality, GGameUserSettingsIni);
		GConfig->GetInt(Section, TEXT("Image"), S.Image, GGameUserSettingsIni);
		GConfig->GetInt(Section, TEXT("FrameRate"), S.FrameRate, GGameUserSettingsIni);
		GConfig->GetFloat(Section, TEXT("Music"), S.Music, GGameUserSettingsIni);
		GConfig->GetFloat(Section, TEXT("Voices"), S.Voices, GGameUserSettingsIni);
		GConfig->GetBool(Section, TEXT("Subtitles"), S.bSubtitles, GGameUserSettingsIni);
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
	GConfig->SetInt(Section, TEXT("Quality"), Quality, GGameUserSettingsIni);
	GConfig->SetInt(Section, TEXT("Image"), Image, GGameUserSettingsIni);
	GConfig->SetInt(Section, TEXT("FrameRate"), FrameRate, GGameUserSettingsIni);
	GConfig->SetFloat(Section, TEXT("Music"), Music, GGameUserSettingsIni);
	GConfig->SetFloat(Section, TEXT("Voices"), Voices, GGameUserSettingsIni);
	GConfig->SetBool(Section, TEXT("Subtitles"), bSubtitles, GGameUserSettingsIni);
	GConfig->Flush(false, GGameUserSettingsIni);
}

float FAstraSettings::FloorOf(int32 InImage)
{
	return InImage == 0 ? 70.f : (InImage == 1 ? 55.f : 40.f);
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
	SetCVar(TEXT("r.DynamicRes.MinScreenPercentage"), FloorOf(Image));
	UE_LOG(LogASTRA, Log, TEXT("[Settings] quality %d, image floor %.0f%%, %d fps, music %.0f%%, voices %.0f%%, subtitles %s"), Quality,
	       FloorOf(Image), FrameRate, Music * 100.f, Voices * 100.f, bSubtitles ? TEXT("on") : TEXT("off"));
}

// --------------------------------------------------------------------------------------------------- the page
void SAstraSettingsPage::Construct(const FArguments& Args)
{
	OnBack = Args._OnBack;
	UFont* Title = LoadObject<UFont>(nullptr, TEXT("/Game/ASTRA/UI/Fonts/F_ASTRA_Title.F_ASTRA_Title"));
	UFont* Mono = LoadObject<UFont>(nullptr, TEXT("/Game/ASTRA/UI/Fonts/F_ASTRA_Mono.F_ASTRA_Mono"));
	auto TitleFont = [Title](int32 Size) { return Title ? FSlateFontInfo(Title, Size) : FCoreStyle::GetDefaultFontStyle("Bold", Size); };
	auto MonoFont = [Mono](int32 Size) { return Mono ? FSlateFontInfo(Mono, Size) : FCoreStyle::GetDefaultFontStyle("Mono", Size); };

	TSharedRef<SVerticalBox> List = SNew(SVerticalBox);
	for (int32 Row = 0; Row < NumRows; ++Row)
	{
		List->AddSlot().AutoHeight().Padding(0, Row == NumRows - 1 ? 22 : 5)
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
	for (int32 i = 0; i < NumRows; ++i)
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
	case 0:
	{
		int32 Q = S.Quality;
		if (Q < 0 && GEngine && GEngine->GetGameUserSettings())
		{
			Q = GEngine->GetGameUserSettings()->GetOverallScalabilityLevel();
		}
		return Q >= 0 && Q <= 3 ? Quality[Q] : TEXT("CUSTOM");
	}
	case 1: return Image[S.Image];
	case 2: return FString::Printf(TEXT("%d"), S.FrameRate);
	case 3: return FString::Printf(TEXT("%d%%"), FMath::RoundToInt(S.Music * 100.f));
	case 4: return FString::Printf(TEXT("%d%%"), FMath::RoundToInt(S.Voices * 100.f));
	case 5: return S.bSubtitles ? TEXT("ON") : TEXT("OFF");
	default: return FString();
	}
}

FString SAstraSettingsPage::NoteOf(int32 Row) const
{
	const FAstraSettings& S = FAstraSettings::Get();
	switch (Row)
	{
	case 0: return TEXT("HIGH and EPIC light the ship with Lumen and full shadows; LOW and MEDIUM trade that light for speed");
	case 1: return S.Image == 0 ? TEXT("the image never drops below 70% resolution: the sharpest, and in a heavy battle the frame rate may fall")
	             : S.Image == 1 ? TEXT("never below 55% resolution: sharp, and smooth in most battles")
	                            : TEXT("down to 40% resolution when the battle is heavy: the frame rate first");
	case 2: return S.FrameRate == 30 ? TEXT("30 frames a second: twice the time for each image, much sharper and cooler on a fanless Mac")
	                                 : TEXT("60 frames a second: the smoothest motion; the resolution adapts to keep it");
	default: return FString();
	}
}

void SAstraSettingsPage::Change(int32 Row, int32 Step)
{
	FAstraSettings& S = FAstraSettings::Get();
	switch (Row)
	{
	case 0:
	{
		int32 Q = S.Quality;
		if (Q < 0 && GEngine && GEngine->GetGameUserSettings())
		{
			Q = FMath::Clamp(GEngine->GetGameUserSettings()->GetOverallScalabilityLevel(), 0, 3);
		}
		S.Quality = (FMath::Max(Q, 0) + Step + 4) % 4;
		break;
	}
	case 1: S.Image = (S.Image + Step + 3) % 3; break;
	case 2: S.FrameRate = S.FrameRate == 60 ? 30 : 60; break;
	case 3: S.Music = FMath::Fmod(FMath::RoundToFloat(S.Music * 10.f + Step + 11.f), 11.f) / 10.f; break;
	case 4: S.Voices = FMath::Fmod(FMath::RoundToFloat(S.Voices * 10.f + Step + 11.f), 11.f) / 10.f; break;
	case 5: S.bSubtitles = !S.bSubtitles; break;
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
		Selected = (Selected + (K == EKeys::Up ? -1 : 1) + NumRows) % NumRows;
		return FReply::Handled();
	}
	if (K == EKeys::Left || K == EKeys::Right || K == EKeys::Enter)
	{
		Change(Selected, K == EKeys::Left ? -1 : 1);
		return FReply::Handled();
	}
	return FReply::Unhandled();
}
