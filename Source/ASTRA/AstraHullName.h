// ASTRA — a ship's name painted on her flanks (the ASTRA warships the story brings: each has her own name).

#pragma once

#include "CoreMinimal.h"
#include "UObject/Object.h"
#include "AstraHullName.generated.h"

class UCanvas;
class UCanvasRenderTarget2D;

/** Draws a name and a hull number once into a transparent render target, and puts it on both flanks of a hull as
 *  decals (M_ASTRA_HullDecal, the Aquila's own marking material). */
UCLASS()
class ASTRA_API UAstraHullName : public UObject
{
	GENERATED_BODY()

public:
	/** Paint "ASN RESOLUTE" / "DD-14" on the actor's hull (its static mesh's bounds say where the flanks are). */
	static void Paint(AActor* Ship, const FString& Name, const FString& HullCode);

	UFUNCTION()
	void Draw(UCanvas* Canvas, int32 Width, int32 Height);

private:
	UPROPERTY() TObjectPtr<UCanvasRenderTarget2D> Target;
	FString Name;
	FString Code;
};
