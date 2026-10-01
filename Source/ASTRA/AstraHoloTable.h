// ASTRA — the bridge's holographic tactical plot: a live miniature of the battle above the holo table, in the same
// frame as the view through the bow window (forward = the bow). Ships by side, missiles, explosions, range rings, the
// true bearings on the rim, who is firing on us and the line to our target.

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
	float PlaneHeight = 42.f;         // a plot that floats well above the v3 table, seen from the Captain's chair

	/** How far above/below the plane a contact may be drawn (cm). */
	UPROPERTY(EditAnywhere, Category = "Holo")
	float MaxDepth = 28.f;

	/** The projector angles the plot towards someone looking from afar (the Captain in the chair, 4 m back and barely
	 *  above the plane, would see it edge on): at most this many degrees, rising as it tilts so that its near edge stays
	 *  above the table; flat for someone leaning over the table. 32: from the chair the plot reads about four times
	 *  taller than flat, and its top stays under the main viewscreen. */
	UPROPERTY(EditAnywhere, Category = "Holo")
	float MaxTilt = 32.f;

	/** Brightness of the plot's light (a bridge in sunlight washes a faint hologram out). */
	UPROPERTY(EditAnywhere, Category = "Holo")
	float Brightness = 3.f;

private:
	UPROPERTY() TObjectPtr<USceneComponent> Root;
	UPROPERTY() TObjectPtr<USceneComponent> PlotFrame;   // everything plotted hangs here: tilted towards the viewer about the plot's centre
	UPROPERTY() TObjectPtr<USceneComponent> ShipFrame;   // the ship plot: a cutaway seen from the side, upright over the table
	UPROPERTY() TObjectPtr<UMaterialInstanceDynamic> TextMID;
	UPROPERTY() TObjectPtr<UStaticMeshComponent> Disc;
	UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> Rings;
	UPROPERTY() TArray<TObjectPtr<UTextRenderComponent>> RingLabels;
	UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> Icons;
	UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> Stems;
	UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> Vectors;
	UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> Dots;
	UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> Blasts;
	UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> Leaders;   // icon -> raised label
	UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> Strobes;   // a jammer's strobe: the Aquila -> its bearing
	UPROPERTY() TArray<TObjectPtr<UTextRenderComponent>> Labels;
	// the rim: true bearings as the crew calls them (the ring turns as the ship turns; the bow stays forward)
	UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> Ticks;
	UPROPERTY() TArray<TObjectPtr<UTextRenderComponent>> TickLabels;
	// who is firing on us (a line from the shooter to the Aquila), and the line to the target under fire control
	UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> Threats;
	UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> TargetLine;
	// how far the Aquila's guns reach: the railguns' and the lasers' rings
	UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> ReachRings;
	UPROPERTY() TArray<TObjectPtr<UTextRenderComponent>> ReachLabels;
	UPROPERTY() TArray<TObjectPtr<UTextRenderComponent>> TargetLabel;
	// the sector plot (the war map): systems, gate links, names
	UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> SectorNodes;
	UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> SectorLinks;
	UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> SectorMarks;
	UPROPERTY() TArray<TObjectPtr<UTextRenderComponent>> SectorLabels;

	// the ship plot: the Aquila deck by deck (the plan), the damage where it is, the damage-control teams, the Captain
	UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> ShipSlabs;
	UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> ShipMarks;
	UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> ShipDots;
	UPROPERTY() TArray<TObjectPtr<UTextRenderComponent>> ShipLabels;
	UPROPERTY() TObjectPtr<UStaticMeshComponent> ScanHull;   // a scanned ship's own hull, as a hologram

	UPROPERTY() TObjectPtr<UStaticMesh> ShipMesh;
	UPROPERTY() TObjectPtr<UStaticMesh> CubeMesh;
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

	/** A pooled component on the plot (or on another frame of the table: the ship plot stands upright, untilted). */
	UStaticMeshComponent* Pooled(TArray<TObjectPtr<UStaticMeshComponent>>& Pool, int32 Index, UStaticMesh* Mesh, USceneComponent* Parent = nullptr);
	UTextRenderComponent* PooledText(TArray<TObjectPtr<UTextRenderComponent>>& Pool, int32 Index, USceneComponent* Parent = nullptr);
	static void HideFrom(TArray<TObjectPtr<UStaticMeshComponent>>& Pool, int32 Index);
	static void HideTextFrom(TArray<TObjectPtr<UTextRenderComponent>>& Pool, int32 Index);
	void SetColor(UStaticMeshComponent* C, const FLinearColor& Color, float Intensity) const;
	FVector PlotPoint(const FVector& RelCm) const;   // battle-relative cm -> actor-local plot point
	float PlotRadiusOf(float Km) const;              // logarithmic radial scale: detail near the Aquila, context far out
	void FaceViewer(USceneComponent* C, const FVector& ViewerLocal) const;
	float Tilt = 0.f;             // degrees, smoothed
	float TiltAzimuth = 180.f;    // where the viewer is around the table (degrees, actor frame), smoothed
	float SectorBlend = 0.f;      // 0 tactical .. 1 sector (cross-fade)
	float SectorYaw = 0.f;        // the sector map turns to face whoever looks at it (south towards the viewer)
	float ShipBlend = 0.f;        // 0 .. 1 the ship plot (cross-fade)
	float ShipYaw = 0.f;          // the ship turns to show her side to whoever looks at her, the bow to their right
	void TickTactical(float DeltaTime, const FVector& ViewerLocal, float Fade);
	void TickSector(float DeltaTime, const FVector& ViewerLocal, float Fade);
	void HideTactical();
	void TickBearings(const class UAstraBattleSubsystem* Battle, const FVector& ViewerLocal, float Fade);
	/** A line on the plot from A to B (actor-local), with its colour and brightness. */
	void PlaceLine(UStaticMeshComponent* L, const FVector& A, const FVector& B, float Thickness, const FLinearColor& Color, float Intensity);
	void HideSector();
	void TickShip(float DeltaTime, const FVector& ViewerLocal, float Fade);
	/** A scanned ship on the table (holo ship with a target): her sections, her shield faces, what burns, what the sensors
	 *  know of her (GUERRA's damage view, with the fog of war). False when the sensors hold no firm track on her. */
	bool TickScannedShip(float DeltaTime, const FVector& ViewerLocal, float Fade, const FString& Id);
	void HideShip();
};
