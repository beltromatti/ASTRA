// ASTRA — the player's settings (the menu's SETTINGS page): the graphics quality, sharpness against smoothness, the frame
// rate, the volumes, the subtitles. Kept in GameUserSettings.ini ([ASTRA.Settings]); applied at start and on every change.
#pragma once

#include "CoreMinimal.h"
#include "Widgets/SCompoundWidget.h"

struct ASTRA_API FAstraSettings
{
	int32 Quality = -1;       // the engine's scalability: 0 low · 1 medium · 2 high · 3 epic; -1 as the engine found it
	int32 Image = 2;          // how low the dynamic resolution may go: 0 sharp (70 %) · 1 balanced (55 %) · 2 smooth (40 %)
	int32 FrameRate = 60;     // 30 or 60
	float Music = 1.f;        // 0..1 of the score's own level (it already sits under the dialogue)
	float Voices = 1.f;       // 0..1 of the voices' level
	bool bSubtitles = true;

	/** The settings, read from GameUserSettings.ini the first time. */
	static FAstraSettings& Get();
	void Save() const;
	/** Into the engine: scalability, the resolution floor, the frame rate and its time budget (volumes and subtitles are read
	 *  where they are used). */
	void Apply() const;
	/** The dynamic resolution's floor for Image (per cent). */
	static float FloorOf(int32 Image);
};

/** The SETTINGS page: one row per setting (click or Enter: the next value; left and right arrows), BACK. */
class SAstraSettingsPage : public SCompoundWidget
{
public:
	SLATE_BEGIN_ARGS(SAstraSettingsPage) {}
		SLATE_EVENT(FSimpleDelegate, OnBack)
	SLATE_END_ARGS()

	void Construct(const FArguments& Args);
	virtual bool SupportsKeyboardFocus() const override { return true; }
	virtual FReply OnKeyDown(const FGeometry& Geometry, const FKeyEvent& Key) override;

private:
	FSimpleDelegate OnBack;
	int32 Selected = 0;
	TSharedPtr<class SButton> Buttons[7];
	bool IsLit(int32 Row) const;
	void Change(int32 Row, int32 Step);
	FString ValueOf(int32 Row) const;
	FString NoteOf(int32 Row) const;
};
