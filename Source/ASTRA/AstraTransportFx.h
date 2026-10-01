// ASTRA — TELETRASPORTO, what is seen and heard (docs/TELETRASPORTO.md §7): the dematerialization and the rematerialization on whoever is carried, the pads' light,
// the Captain's own view. The transporter subsystem (AstraTransporterSubsystem.*) says what happens and when; this draws it.
//
// The budget is a MacBook Air's: no Niagara, no actor per sparkle (the war's and the damage's effects are built the same way, docs/VFX.md). One instanced layer of
// sparkles (one component, one material, a few hundred instances moved by plain code), at most a few columns alive at a time (the party of six and the cargo),
// each a soft shimmering cylinder of light and, when a body is being carried, a follower of its mesh in a dissolve material that eats it from the feet up. The Captain's
// own view is a Slate overlay (cells that turn to light, a column of glitter, a white-gold wash) that needs no material and dims the real picture with a camera fade.
// Everything that needs an asset the lead has not yet made (tools/ue_scripts/make_transporter_fx.py) falls back to what the project already has, or draws nothing:
// the rules and the orders never depend on it.

#pragma once

#include "CoreMinimal.h"
#include "UObject/Object.h"
#include "AstraTransportFx.generated.h"

class AActor;
class AStaticMeshActor;
class UInstancedStaticMeshComponent;
class UMaterialInterface;
class UMaterialInstanceDynamic;
class USkeletalMeshComponent;
class UPointLightComponent;
class UAudioComponent;
class UStaticMesh;
class SAstraXportOverlay;

/** How a pad looks: the colour of its ring says what the lock is doing. */
enum class EAstraPadLook : uint8 { Idle, Selected, Locking, Locked, Energizing, Fault };

UCLASS()
class UAstraTransportFx : public UObject
{
	GENERATED_BODY()

public:
	void Init(UWorld* InWorld);
	void Shutdown();
	/** Every frame the subsystem ticks (Dt in game seconds). */
	void Tick(float Dt, const FVector& CaptainEyeCm);

	/** A column of light on a spot: bRematerialize false = the figure dissolves and rises as sparkles, true = sparkles gather and the figure forms. Seconds long. Source: the actor
	 *  whose body is carried (null: only the column: cargo, someone with no body in view); MassKg sizes the column; bCaptain: his own column (others see him as a shimmer, he sees his
	 *  screen: CaptainView). Returns an id. */
	int32 BeginColumn(const FVector& FeetCm, float YawDeg, bool bRematerialize, float Seconds, AActor* Source, float MassKg, bool bCaptain);
	/** The body that was not there when the column began (a person VITA has just made a body for) is bound to it: from now on it forms with the column. */
	void BindSource(int32 Id, AActor* Source);
	/** An abort: the column runs back (the figure re-forms, or dissolves back out). */
	void ReverseColumn(int32 Id);
	/** The column ends (it fades over a short time unless bNow). */
	void EndColumn(int32 Id, bool bNow = false);
	/** Where a column stands now (it may follow its source). */
	bool HasColumn(int32 Id) const;

	/** The Captain's screen: dissolving (bRematerialize false) or recomposing; Seconds long. Progress runs by itself; ReverseCaptainView plays it back. */
	void BeginCaptainView(bool bRematerialize, float Seconds);
	void ReverseCaptainView();
	void EndCaptainView();
	/** 0 clear .. 1 full white-gold (the wash the screen sits in between the dissolve and the recomposition). */
	void HoldCaptainView(float Level01);

	/** The pads' rings: the pad's world position (cm, feet) and its look. */
	void SetPadLook(int32 PadIndex, const FVector& PosCm, float RadiusCm, EAstraPadLook Look);
	void ClearPads();
	/** The emitter ring's glow over the dais: 0..1. */
	void SetEmitter(const FVector& CentreCm, float Glow);

	/** A sound at a place (SW_Xport_*): Id is the asset's short name ("Demat", "Remat", "Lock", "Fault", "Hum"); the volume is 0..1. */
	void PlaySound(const TCHAR* Id, const FVector& AtCm, float Volume = 1.f, float Pitch = 1.f);
	/** A loop that stays until stopped (the pad hum while a cycle runs): returns an id. */
	int32 StartLoop(const TCHAR* Id, const FVector& AtCm, float Volume);
	void StopLoop(int32 Id, float FadeS = 0.4f);

	/** The state for the tests and astra.xport.info: columns alive, sparkles alive, the overlay's progress. */
	FString Describe() const;
	int32 NumColumns() const { return Cols.Num(); }
	int32 NumSparkles() const { return NumLive; }

private:
	struct FColumn
	{
		int32 Id = 0;
		FVector Feet = FVector::ZeroVector;
		float Yaw = 0.f;
		bool bRemat = false, bCaptain = false, bEnding = false;
		float Age = 0.f, Seconds = 3.6f, Dir = 1.f;     // Dir -1: running back
		float Mass = 90.f;
		float Fade = 1.f;
		TWeakObjectPtr<AActor> Source;
		TWeakObjectPtr<USkeletalMeshComponent> Ghost;
		TWeakObjectPtr<UPointLightComponent> Light;
		float Height = 190.f, Radius = 45.f;
		int32 Seed = 0;
		float Emit = 0.f;                                // sparkles owed to the emitter
	};
	struct FSparkle
	{
		FVector Pos = FVector::ZeroVector, Vel = FVector::ZeroVector;
		float Age = 0.f, Life = 1.f, Size = 3.f, Phase = 0.f, Hue = 0.f;
		uint8 Col = 0;
		bool bLive = false;
	};
	struct FPadFx
	{
		FVector Pos = FVector::ZeroVector;
		float Radius = 60.f;
		EAstraPadLook Look = EAstraPadLook::Idle;
		float Glow = 0.f;
	};

	UPROPERTY() TObjectPtr<UWorld> World;
	UPROPERTY() TObjectPtr<AStaticMeshActor> LayerHost;
	UPROPERTY() TObjectPtr<UInstancedStaticMeshComponent> Sparkles;
	UPROPERTY() TObjectPtr<UInstancedStaticMeshComponent> PadRings;
	UPROPERTY() TObjectPtr<UInstancedStaticMeshComponent> Columns;
	UPROPERTY() TObjectPtr<UMaterialInterface> SparkleMat;
	UPROPERTY() TObjectPtr<UMaterialInterface> ColumnMat;
	UPROPERTY() TObjectPtr<UMaterialInterface> BodyMat;
	UPROPERTY() TObjectPtr<UMaterialInterface> GlowMat;
	UPROPERTY() TObjectPtr<UMaterialInstanceDynamic> BodyMid;
	UPROPERTY() TMap<FName, TObjectPtr<UObject>> Sounds;
	UPROPERTY() TArray<TObjectPtr<UAudioComponent>> LoopAudio;
	TArray<FColumn> Cols;
	TArray<FSparkle> Pool;
	TArray<FPadFx> PadList;
	FVector EmitterCm = FVector::ZeroVector;
	float EmitterGlow = 0.f, EmitterShown = 0.f;
	int32 NextId = 1, NumLive = 0, NextLoop = 1;
	bool bReady = false;
	bool bAssetsTried = false;
	TSharedPtr<SAstraXportOverlay> Overlay;
	TSharedPtr<class SWidget> OverlayRoot;
	bool bOverlayOn = false;
	float ViewAge = 0.f, ViewSeconds = 3.6f, ViewDir = 1.f, ViewHold = 0.f, ViewShown = 0.f;
	bool bViewRemat = false, bViewActive = false;

	void LoadAssets();
	void EmitFor(FColumn& C, float Dt);
	void StepSparkles(float Dt);
	void WriteInstances(const FVector& EyeCm);
	void StepColumns(float Dt);
	void StepOverlay(float Dt);
	void StepPads(float Dt);
	void EnsureLayers();
	void DropColumn(int32 Index);
	USkeletalMeshComponent* MakeGhost(AActor* Source);
	friend class SAstraXportOverlay;
};
