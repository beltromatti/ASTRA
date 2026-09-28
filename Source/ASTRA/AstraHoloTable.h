// ASTRA — the bridge's holographic tactical plot: a live miniature of the battle above the holo table, in the same
// frame as the view through the bow window (forward = the bow). Ships by side, missiles, explosions, range rings.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "AstraHoloTable.generated.h"

class UMaterialInstanceDynamic;
class UMaterialInterface;
class UStaticMesh;
class UStaticMeshComponent;
class UTextRenderComponent;

UCLASS()
class ASTRA_API AAstraHoloTable : public AActor
{
	GENERATED_BODY()

public:
	AAstraHoloTable();
	virtual void BeginPlay() override;
	virtual void Tick(float DeltaTime) override;

	/** Radius of the plotted disc (cm). */
	UPROPERTY(EditAnywhere, Category = "Holo")
	float PlotRadius = 118.f;

	/** Height of the tactical plane above the actor origin (the table top), cm. */
	UPROPERTY(EditAnywhere, Category = "Holo")
	float PlaneHeight = 24.f;

	/** How far above/below the plane a contact may be drawn (cm). */
	UPROPERTY(EditAnywhere, Category = "Holo")
	float MaxDepth = 18.f;

private:
	UPROPERTY() TObjectPtr<USceneComponent> Root;
	UPROPERTY() TObjectPtr<UStaticMeshComponent> Disc;
	UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> Rings;
	UPROPERTY() TArray<TObjectPtr<UTextRenderComponent>> RingLabels;
	UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> Icons;
	UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> Stems;
	UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> Vectors;
	UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> Dots;
	UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> Blasts;
	UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> Leaders;   // icon -> raised label
	UPROPERTY() TArray<TObjectPtr<UTextRenderComponent>> Labels;

	UPROPERTY() TObjectPtr<UStaticMesh> ShipMesh;
	UPROPERTY() TObjectPtr<UStaticMesh> UnknownMesh;
	UPROPERTY() TObjectPtr<UStaticMesh> RingMesh;
	UPROPERTY() TObjectPtr<UStaticMesh> DiscMesh;
	UPROPERTY() TObjectPtr<UStaticMesh> LineMesh;
	UPROPERTY() TObjectPtr<UStaticMesh> SphereMesh;
	UPROPERTY() TObjectPtr<UMaterialInterface> HoloMat;
	UPROPERTY() TObjectPtr<UMaterialInterface> GridMat;
	UPROPERTY() TObjectPtr<UMaterialInterface> TextMat;

	float RangeKm = 20.f;         // plotted range at the disc's edge (smoothed)
	float TargetRangeKm = 20.f;
	float Time = 0.f;

	UStaticMeshComponent* Pooled(TArray<TObjectPtr<UStaticMeshComponent>>& Pool, int32 Index, UStaticMesh* Mesh);
	UTextRenderComponent* PooledText(TArray<TObjectPtr<UTextRenderComponent>>& Pool, int32 Index);
	static void HideFrom(TArray<TObjectPtr<UStaticMeshComponent>>& Pool, int32 Index);
	static void HideTextFrom(TArray<TObjectPtr<UTextRenderComponent>>& Pool, int32 Index);
	static void SetColor(UStaticMeshComponent* C, const FLinearColor& Color, float Intensity);
	FVector PlotPoint(const FVector& RelCm) const;   // battle-relative cm -> actor-local plot point
	float PlotRadiusOf(float Km) const;              // logarithmic radial scale: detail near the Aquila, context far out
	void FaceViewer(USceneComponent* C, const FVector& ViewerLocal) const;
};
