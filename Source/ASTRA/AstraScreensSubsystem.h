// ASTRA — live bridge screens. Every screen surface whose material is a known screen instance (MI_ASTRA_ScreenMaster,
// MI_ASTRA_ScreenTactical, MI_UI_<Station>_<Slot>) gets a canvas render target instead of its static texture, redrawn a
// few times a second from the ship's real state. Same visual language as the static screens (tools/art/ui_screens.py).

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "AstraScreensSubsystem.generated.h"

class UCanvas;
class UCanvasRenderTarget2D;
class UFont;
class UAstraScreensSubsystem;

/** One live page (a render target) and its draw callback. */
UCLASS()
class UAstraScreenPage : public UObject
{
	GENERATED_BODY()

public:
	FString Name;
	TWeakObjectPtr<UAstraScreensSubsystem> Owner;
	UPROPERTY() TObjectPtr<UCanvasRenderTarget2D> Target;
	float Interval = 0.25f;
	float Wait = 0.f;

	UFUNCTION()
	void Draw(UCanvas* Canvas, int32 Width, int32 Height);
};

UCLASS()
class ASTRA_API UAstraScreensSubsystem : public UTickableWorldSubsystem
{
	GENERATED_BODY()

public:
	virtual void OnWorldBeginPlay(UWorld& InWorld) override;
	virtual void Tick(float DeltaTime) override;
	virtual TStatId GetStatId() const override { RETURN_QUICK_DECLARE_CYCLE_STAT(UAstraScreensSubsystem, STATGROUP_Tickables); }
	virtual bool ShouldCreateSubsystem(UObject* Outer) const override;

	void DrawPage(const FString& Name, UCanvas* Canvas, int32 Width, int32 Height);
	/** The Captain's datapad: its live page (painted only while it is raised). */
	class UTextureRenderTarget2D* GetPadTarget();
	void SetPadVisible(bool bVisible);
	/** The datapad's pages: overview, contact (a dossier; Focus = the contact), damage, fleet, orders. Ops pushes one to the
	 *  Captain (a notice and a chime; the page is there when the pad is raised). False for an unknown page. */
	bool PushPad(const FString& Page, const FString& Focus, const FString& By);
	/** The mouse wheel on the raised pad: the next or previous page. */
	void CyclePad(int32 Dir);
	const FString& GetPadPage() const { return PadPage; }

private:
	bool bPadVisible = false;
	FString PadPage = TEXT("overview");
	FString PadFocus;
	FString PadPushedBy;
	float PadPushedAt = -100.f;
	void DrawPad(UCanvas* C, int32 W, int32 H);
	void DrawPadOverview(UCanvas* C, int32 W, int32 H);
	void DrawPadContact(UCanvas* C, int32 W, int32 H);
	void DrawPadDamage(UCanvas* C, int32 W, int32 H);
	void DrawPadFleet(UCanvas* C, int32 W, int32 H);
	void DrawPadOrders(UCanvas* C, int32 W, int32 H);
	void DrawPadTabs(UCanvas* C, int32 W, int32 H);
	void RedrawPadNow();
	UPROPERTY() TArray<TObjectPtr<UAstraScreenPage>> Pages;
	UPROPERTY() TObjectPtr<UFont> TitleFont;
	UPROPERTY() TObjectPtr<UFont> MonoFont;
	float Time = 0.f;

	UAstraScreenPage* PageFor(const FString& Name);
public:
	/** Testing: a live page as it is now, to a PNG (astra.screens.dump <Page> [path]). */
	bool DumpPage(const FString& Name, const FString& Path);
private:
	static bool IsLive(const FString& Name);

	void DrawMaster(UCanvas* C, int32 W, int32 H);
	void DrawTactical(UCanvas* C, int32 W, int32 H);
	void DrawHelm(UCanvas* C, int32 W, int32 H, const FString& Slot);
	void DrawOps(UCanvas* C, int32 W, int32 H, const FString& Slot);
	void DrawSensors(UCanvas* C, int32 W, int32 H, const FString& Slot);
	void DrawEngineering(UCanvas* C, int32 W, int32 H, const FString& Slot);
	void DrawMess(UCanvas* C, int32 W, int32 H, const FString& Slot);
	/** Communications: the channel (open, with whom), the traffic heard (A), the fleet net and the log (B). */
	void DrawComms(UCanvas* C, int32 W, int32 H, const FString& Slot);
	/** Flight operations: the air group (A), the craft in flight and the deck (B). */
	void DrawFlight(UCanvas* C, int32 W, int32 H, const FString& Slot);
	/** A station's control surface: its modes in force as lit buttons, who set them, what the officer just did. */
	void DrawControls(UCanvas* C, int32 W, int32 H, const FString& Station);
};
