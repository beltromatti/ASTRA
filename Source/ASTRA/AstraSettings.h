// ASTRA — the player's settings (the menu's SETTINGS page): graphics, display, audio, the crew's language, the controls, the OpenRouter key.
// Kept in GameUserSettings.ini ([ASTRA.Settings]); applied at start and on every change.
#pragma once

#include "CoreMinimal.h"
#include "InputCoreTypes.h"
#include "Widgets/SCompoundWidget.h"

struct ASTRA_API FAstraSettings
{
	// GRAPHICS
	int32 Quality = -1;       // the engine's scalability: 0 low · 1 medium · 2 high · 3 epic; -1 as the engine found it (the platform's profile, or the PC's benchmark)
	int32 Image = 2;          // how low the dynamic resolution may go: 0 sharp (70 %) · 1 balanced (55 %) · 2 smooth (40 %)
	// the Mac's: the image out at the display's own pixels (a Retina Mac: twice the half the engine makes by default), upscaled by MetalFX; on by default there.
	// Windows and Linux have no such setting: no row in the page, no key in the file, and the field stays false (portable-ok: the default is the platform's)
	bool bRetina = PLATFORM_MAC;
	int32 FrameRate = 60;     // 30, 60, 120, or 0 (no limit)
	int32 Display = 1;        // 0 full screen · 1 borderless window (full screen) · 2 window
	bool bMotionBlur = false; // off by default: ~1 ms of GPU in a battle, and a bridge camera gains little from it
	float Fov = 90.f;         // the first-person field of view (degrees, horizontal): 70 .. 110
	// AUDIO
	float Master = 1.f;       // 0..1 of everything
	float Music = 1.f;        // 0..1 of the score's own level (it already sits under the dialogue)
	float Voices = 1.f;       // 0..1 of the voices' level
	bool bSubtitles = true;
	// LANGUAGE: the language the crew speaks at the start of every session (their first lines), and whether they then answer in the language the
	// Captain speaks to them (a Captain may speak any language: the crew follows)
	FString Language = TEXT("en");
	bool bFollowVoice = true;
	// CONTROLS
	float MouseSensitivity = 1.f;   // 0.2 .. 2.0
	bool bInvertMouse = false;
	FKey TalkKey = EKeys::V;        // push to talk (hold)
	FKey OrdersKey = EKeys::G;      // the orders wheel (hold)

	/** The settings, read from GameUserSettings.ini the first time. */
	static FAstraSettings& Get();
	void Save() const;
	/** Into the engine: scalability, the resolution floor, the frame rate and its time budget, motion blur, the master volume, the field of view of
	 *  the Captain's camera (the other volumes, the subtitles, the language, the mouse and the keys are read where they are used). The window mode
	 *  only with bWindowMode (the DISPLAY row): at start the engine's saved mode stands, and on the Mac a window made full screen while the app is
	 *  not in front waits for macOS for ever (ASTRA.cpp takes it to full screen once it is). */
	void Apply(bool bWindowMode = false) const;
	/** The dynamic resolution's floor for Image (per cent), of the half-resolution output. */
	static float FloorOf(int32 Image);
	/** The floor the engine is given: with the Retina output the same number of pixels as the half output's floor would be, never under the
	 *  upscaler's own limit (MetalFX takes 33 % of its output at least). */
	float EngineFloor() const;

	/** The crew's languages: the code the mind uses and the language's own name. */
	static const TArray<TPair<FString, FString>>& Languages();
	/** A key as the player sees it on the keyboard ("V", "Mouse 4", "F5"). */
	static FString KeyName(const FKey& K);
};

/** The SETTINGS page: sections of rows (click or Enter: the next value; left and right arrows; a key row waits for the key to bind), BACK. */
class SAstraSettingsPage : public SCompoundWidget
{
public:
	SLATE_BEGIN_ARGS(SAstraSettingsPage) {}
		SLATE_EVENT(FSimpleDelegate, OnBack)
		SLATE_EVENT(FSimpleDelegate, OnApiKey)      // the OPENROUTER KEY row: the key's own page (AstraApiKey.h)
	SLATE_END_ARGS()

	void Construct(const FArguments& Args);
	virtual bool SupportsKeyboardFocus() const override { return true; }
	virtual FReply OnKeyDown(const FGeometry& Geometry, const FKeyEvent& Key) override;
	virtual FReply OnMouseButtonDown(const FGeometry& Geometry, const FPointerEvent& Mouse) override;

private:
	FSimpleDelegate OnBack, OnApiKey;
	int32 Selected = 0;
	int32 Capturing = -1;                    // the key row waiting for its key (-1: none)
	TSharedPtr<class SButton> Buttons[32];   // one for each of the page's rows by its number (AstraSettings.cpp: NumRowIds)
	TSharedPtr<class SScrollBox> Scroll;
	bool IsLit(int32 Row) const;
	void Change(int32 Row, int32 Step);
	FString ValueOf(int32 Row) const;
	FString NoteOf(int32 Row) const;
	void Bind(const FKey& K);
};
