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

private:
	bool bPadVisible = false;
	void DrawPad(UCanvas* C, int32 W, int32 H);
	UPROPERTY() TArray<TObjectPtr<UAstraScreenPage>> Pages;
	UPROPERTY() TObjectPtr<UFont> TitleFont;
	UPROPERTY() TObjectPtr<UFont> MonoFont;
	float Time = 0.f;

	UAstraScreenPage* PageFor(const FString& Name);
	static bool IsLive(const FString& Name);

	void DrawMaster(UCanvas* C, int32 W, int32 H);
	void DrawTactical(UCanvas* C, int32 W, int32 H);
	void DrawHelm(UCanvas* C, int32 W, int32 H, const FString& Slot);
	void DrawOps(UCanvas* C, int32 W, int32 H, const FString& Slot);
	void DrawSensors(UCanvas* C, int32 W, int32 H, const FString& Slot);
	void DrawEngineering(UCanvas* C, int32 W, int32 H, const FString& Slot);
	void DrawMess(UCanvas* C, int32 W, int32 H, const FString& Slot);
};
