// ASTRA — the campaign: the title menu (continue the war or begin a new one), autosaves of the Aquila's state
// (Saved/Campaign/ship.json; the mind keeps the war map and the story), and resuming where the Captain left off.

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "AstraCampaign.generated.h"

class SAstraMainMenu;
class SWidget;

UCLASS()
class ASTRA_API UAstraCampaignSubsystem : public UTickableWorldSubsystem
{
	GENERATED_BODY()

public:
	virtual bool ShouldCreateSubsystem(UObject* Outer) const override;
	virtual void OnWorldBeginPlay(UWorld& InWorld) override;
	virtual void Deinitialize() override;
	virtual void Tick(float DeltaTime) override;
	virtual bool IsTickableWhenPaused() const override { return true; }
	virtual TStatId GetStatId() const override { RETURN_QUICK_DECLARE_CYCLE_STAT(UAstraCampaignSubsystem, STATGROUP_Tickables); }

	bool HasSave() const;
	/** "Cassia · hull 72% · 3 fallen · saved 10:42" for the menu. */
	FString SaveSummary() const;

	void StartNew();
	void Continue();
	void SaveNow(const TCHAR* Why);
	/** After the loss of the Aquila: the Captain's new command, a sister ship renamed Aquila, weeks later in System —
	 *  the save is rewritten (a new hull, a full magazine and air group; the fallen stay fallen, the wounded have
	 *  healed or gone home) and the level starts over from it. */
	void NewCommand(const FString& System);
	bool IsStarted() const { return bStarted; }

	/** The title menu (bInGame: opened with Esc during play — the game pauses, Resume comes first). */
	void ShowMenu(bool bInGame);
	void HideMenu();
	bool IsMenuOpen() const { return MenuWidget.IsValid(); }

private:
	bool bStarted = false;
	bool bMenuInGame = false;
	float AutoSaveT = 0.f;
	float PendingStartT = -1.f;   // console/command-line start, once the world is running
	FString PendingMode;
	TSharedPtr<SAstraMainMenu> Menu;
	TSharedPtr<SWidget> MenuWidget;
	FDelegateHandle ShipEventHandle;

	FString SavePath() const;
	TSharedPtr<class FJsonObject> LoadSave() const;
	void SetMenuInput(bool bMenu);
	void Begin(const FString& Mode);
};
