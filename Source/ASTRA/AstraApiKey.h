// ASTRA — the player's OpenRouter key. The crew, the allies, the enemy and the war's commanders are language models reached through OpenRouter
// with the player's own key: the game asks for it on the first start, checks it (the key is valid, the account has credit, openrouter.ai can be
// reached) before the title menu, and lets the player change it in SETTINGS. The key is written to the mind's own .env in the player's data folder
// (Application Support/ASTRA, %LOCALAPPDATA%\ASTRA; the repository's .env when the game runs from the sources) and sent nowhere but openrouter.ai.
#pragma once

#include "CoreMinimal.h"
#include "Widgets/SCompoundWidget.h"

struct ASTRA_API FAstraApiKey
{
	enum class EState : uint8 { Unknown, Checking, Ok, Missing, Invalid, NoCredit, Offline, Error };

	/** The .env the mind reads. */
	static FString EnvPath();
	/** The key in it, or "". */
	static FString Read();
	/** Write the key into it (the other lines kept); the mind is told to read it again. */
	static bool Write(const FString& Key);
	/** "sk-or-v1-…a3f2". */
	static FString Masked(const FString& Key);

	/** Ask openrouter.ai: is the key valid, how much credit is left. Done() runs on the game thread. */
	static void Verify(const FString& Key, TFunction<void()> Done);

	/** The last answer this session. */
	static EState State;
	static double Balance;          // dollars left on the account (or on the key's own limit), -1 unknown
	static FString Message;         // what the player is told
	static bool IsGood() { return State == EState::Ok; }

	/** For the SETTINGS row: "sk-or-v1-…a3f2 · $8.20 left" or "NOT SET", and the line under it. */
	static FString Summary();
	static FString Note();
};

/** The key's page: the first start (no way into the game without a good key) and SETTINGS (BACK keeps the old one). */
class SAstraKeyGate : public SCompoundWidget
{
public:
	SLATE_BEGIN_ARGS(SAstraKeyGate) : _ChangeMode(false) {}
		SLATE_ARGUMENT(bool, ChangeMode)
		SLATE_EVENT(FSimpleDelegate, OnDone)        // a good key is in place
		SLATE_EVENT(FSimpleDelegate, OnCancel)      // BACK (SETTINGS), or QUIT (the first start)
	SLATE_END_ARGS()

	void Construct(const FArguments& Args);
	virtual bool SupportsKeyboardFocus() const override { return true; }
	virtual FReply OnKeyDown(const FGeometry& Geometry, const FKeyEvent& Key) override;
	/** Check the key already saved and go straight on when it is good (the page only shows when it is not). */
	void CheckSaved();

private:
	bool bChangeMode = false;
	bool bBusy = false;
	FSimpleDelegate OnDone, OnCancel;
	TSharedPtr<class SEditableTextBox> Box;
	FString Status;
	FLinearColor StatusColour = FLinearColor::White;
	void Submit();
	void ShowResult(const FString& Key, bool bSave);
};
