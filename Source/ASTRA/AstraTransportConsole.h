// ASTRA — TELETRASPORTO, the Transporter Room's live display: a hologram-bright wall screen that shows the pads, the locks and the state (the card the Chief reads), drawn
// like the bridge's own screens (a canvas render target, redrawn a few times a second only while somebody looks). The room's mesh is a static kit instance, so the screen is
// a separate actor laid over the kit's wall panel; the subsystem puts it where the plan says the room is (data/ship/aquila_transport.json `room.layout.wall_screen`).

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "AstraTransportConsole.generated.h"

class UStaticMeshComponent;
class UMaterialInstanceDynamic;
class UCanvasRenderTarget2D;
class UCanvas;
class UAstraTransporterSubsystem;

UCLASS()
class AAstraTransportConsole : public AActor
{
	GENERATED_BODY()

public:
	AAstraTransportConsole();
	/** Where and how big: the centre of the picture (world cm), the way it faces (yaw), its size (cm). */
	void Place(const FVector& CentreCm, float YawDeg, const FVector2D& SizeCm);
	/** The page is redrawn at most this often while it is looked at (s). */
	float RedrawEvery = 0.25f;
	/** Draws the page now into a PNG (the lead's astra.xport.dump). */
	bool Dump(const FString& Path);
	/** The screen is lit and redrawn while somebody is near it; dark and idle otherwise. */
	void SetShown(bool bOn);
	virtual void Tick(float DeltaSeconds) override;
	/** The subsystem the page reads (set when it makes the actor). */
	TWeakObjectPtr<UAstraTransporterSubsystem> Owner;

	UFUNCTION()
	void Draw(UCanvas* Canvas, int32 Width, int32 Height);

protected:
	UPROPERTY(VisibleAnywhere) TObjectPtr<UStaticMeshComponent> Panel;
	UPROPERTY() TObjectPtr<UMaterialInstanceDynamic> Mid;
	UPROPERTY() TObjectPtr<UCanvasRenderTarget2D> Target;
	UPROPERTY() TObjectPtr<UObject> TitleFont;
	UPROPERTY() TObjectPtr<UObject> MonoFont;
	float Wait = 0.f;
	float Age = 0.f;
	FVector2D Size = FVector2D(410.0, 185.0);
	bool bShown = false;
	void EnsureTarget();
};
