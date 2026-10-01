// ASTRA — TELETRASPORTO, what is seen and heard (docs/TELETRASPORTO.md §7): the dematerialization and the rematerialization on whoever is carried, the pads' light,
// the Captain's own view. The transporter subsystem (AstraTransporterSubsystem.*) says what happens and when; this draws it.
//
// The budget is a MacBook Air's: no Niagara, no actor per sparkle (the war's and the damage's effects are built the same way, docs/VFX.md). Three instanced layers (one
// component and one material each): sparkles (a few hundred soft points moved by plain code), columns (a soft shimmering cylinder of light round each subject, at most a dozen
// alive) and the pads' rings. When a body is carried, a ghost of its mesh (a follower with a dissolve material that eats it from the feet up, or forms it from the feet up) stands
// in for it while the real body is out of sight. The Captain's own view is a Slate overlay (cells that turn to light, a white-gold wash) that needs no material.
// Everything that needs an asset the lead has not made yet (tools/ue_scripts/make_transporter_fx.py, tools/art/transporter_sounds.py + tools/ue_scripts/import_transporter_audio.py)
// is skipped, with one line in the log: the rules and the orders never depend on it.

#pragma once

#include "CoreMinimal.h"
#include "UObject/Object.h"
#include "AstraTransportFx.generated.h"

class AActor;
class UAudioComponent;
class UInstancedStaticMeshComponent;
class UMaterialInstanceDynamic;
class UMaterialInterface;
class UPointLightComponent;
class USkeletalMeshComponent;
class USkinnedMeshComponent;
class USoundAttenuation;
class USoundBase;
class UStaticMesh;
class SAstraXportOverlay;

/** How a pad looks: the colour of its ring says what the lock is doing. */
enum class EAstraPadLook : uint8 { Idle, Selected, Locking, Locked, Energizing, Fault };

namespace AstraXportFx
{
	constexpr int32 Stride = 8;                 // floats of per-instance custom data: 0-2 colour, 3 intensity, 4 progress or age, 5 direction or mode, 6 fade, 7 seed
	constexpr int32 CapSparkles = 420, CapColumns = 12, CapRings = 12;

	/** One layer of instances: staged each frame, written once. */
	struct FLayer
	{
		TWeakObjectPtr<UInstancedStaticMeshComponent> Comp;
		int32 Capacity = 0, Count = 0, Prev = 0;
		TArray<FTransform> Xf;
		TArray<float> Data;
		void Init(int32 InCapacity);
		void Begin() { Count = 0; }
		/** The next free instance, or null when the layer is full. */
		float* Next(FTransform*& OutXf);
		void Flush();
	};
}

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
	 *  whose body is carried (null: only the column: cargo, someone with no body in view); MassKg sizes the column; bCaptain: his own column (others see him as a column of light,
	 *  he sees his screen: BeginCaptainView). Returns an id. */
	int32 BeginColumn(const FVector& FeetCm, float YawDeg, bool bRematerialize, float Seconds, AActor* Source, float MassKg, bool bCaptain);
	/** The body that was not there when the column began (a person VITA has just made a body for) is bound to it: from now on it forms with the column. */
	void BindSource(int32 Id, AActor* Source);
	/** An abort: the column runs back (the figure re-forms, or dissolves back out). */
	void ReverseColumn(int32 Id);
	/** The column ends (it fades over a short time unless bNow). */
	void EndColumn(int32 Id, bool bNow = false);
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
	/** The emitter's glow over the dais: 0..1. */
	void SetEmitter(const FVector& CentreCm, float Glow);

	/** A sound at a place (SW_Xport_*): Id is the asset's short name ("Demat", "Remat", "Lock", "Fault", "Energize", "Hum"); the volume is 0..1. */
	void PlaySound(const TCHAR* Id, const FVector& AtCm, float Volume = 1.f, float Pitch = 1.f);
	/** A loop that stays until stopped (the pad hum while a cycle runs): returns an id. */
	int32 StartLoop(const TCHAR* Id, const FVector& AtCm, float Volume);
	void StopLoop(int32 Id, float FadeS = 0.4f);

	/** The state for the tests and astra.xport.info. */
	FString Describe() const;
	int32 NumColumns() const { return Cols.Num(); }
	int32 NumSparkles() const { return NumLive; }
	bool IsDrawing() const { return bReady && bLayers; }

private:
	struct FColumn
	{
		int32 Id = 0;
		FVector Feet = FVector::ZeroVector;
		float Yaw = 0.f;
		bool bRemat = false, bCaptain = false, bEnding = false, bBodyHidden = false;
		float Age = 0.f, Seconds = 3.6f, Dir = 1.f;     // Dir -1: running back
		float Mass = 90.f;
		float Fade = 1.f;
		TWeakObjectPtr<AActor> Source;
		TWeakObjectPtr<USkeletalMeshComponent> Ghost;
		TWeakObjectPtr<USkinnedMeshComponent> Leader;    // the body's mesh the ghost follows
		TWeakObjectPtr<UMaterialInstanceDynamic> GhostMid;
		float Height = 190.f, Radius = 45.f;
		int32 Seed = 0;
		float Emit = 0.f;                                // sparkles owed to the emitter
		FLinearColor Col = FLinearColor(1.f, 0.78f, 0.38f);
	};
	struct FSparkle
	{
		FVector Pos = FVector::ZeroVector, Vel = FVector::ZeroVector, Swirl = FVector::ZeroVector;
		float Age = 0.f, Life = 1.f, Size = 3.f, Seed = 0.f, Inten = 4.f;
		FLinearColor Col = FLinearColor::White;
		bool bLive = false;
	};
	struct FPadFx
	{
		FVector Pos = FVector::ZeroVector;
		float Radius = 60.f;
		EAstraPadLook Look = EAstraPadLook::Idle;
		float Glow = 0.f;
		bool bSet = false;
	};

	UPROPERTY() TObjectPtr<UWorld> World;
	UPROPERTY() TObjectPtr<AActor> Host;
	UPROPERTY() TObjectPtr<UMaterialInterface> SparkleMat;
	UPROPERTY() TObjectPtr<UMaterialInterface> ColumnMat;
	UPROPERTY() TObjectPtr<UMaterialInterface> RingMat;
	UPROPERTY() TObjectPtr<UMaterialInterface> GhostMat;
	UPROPERTY() TObjectPtr<UStaticMesh> SphereMesh;
	UPROPERTY() TObjectPtr<UStaticMesh> CylinderMesh;
	UPROPERTY() TObjectPtr<UStaticMesh> PlaneMesh;
	UPROPERTY() TObjectPtr<UPointLightComponent> Light;
	UPROPERTY() TMap<FName, TObjectPtr<USoundBase>> Sounds;
	UPROPERTY() TMap<int32, TObjectPtr<UAudioComponent>> Loops;
	UPROPERTY() TObjectPtr<USoundAttenuation> Attenuation;
	AstraXportFx::FLayer SparkleL, ColumnL, RingL;
	TArray<FColumn> Cols;
	TArray<FSparkle> Pool;
	TArray<FPadFx> PadList;
	FVector EmitterCm = FVector::ZeroVector;
	float EmitterGlow = 0.f, EmitterShown = 0.f;
	int32 NextId = 1, NumLive = 0, NextLoop = 1, NextSparkle = 0;
	bool bReady = false, bLayers = false, bAssetsTried = false, bWarned = false;
	double Clock = 0.0;
	FRandomStream Rng = FRandomStream(8197);
	TSharedPtr<SAstraXportOverlay> Overlay;
	bool bOverlayOn = false;
	float ViewAge = 0.f, ViewSeconds = 3.6f, ViewDir = 1.f, ViewHold = 0.f, ViewShown = 0.f, ShownWash = 0.f, ShownCells = 0.f;
	bool bViewRemat = false, bViewActive = false, bViewEnding = false;
	float EmitterWritten = -1.f;
	bool bPadsDirty = true, bWasBusy = false;

	void LoadAssets();
	bool EnsureLayers();
	void StepColumns(float Dt);
	void StepSparkles(float Dt);
	void Emit(FColumn& C, float Prog, float Dt);
	void SpawnSparkle(const FVector& At, const FVector& Vel, float Life, float Size, const FLinearColor& Col, float Inten);
	void WriteInstances();
	void StepPads(float Dt);
	void StepOverlay(float Dt);
	void StepLight(float Dt);
	void DropColumn(FColumn& C);
	USkeletalMeshComponent* MakeGhost(AActor* Source, UMaterialInstanceDynamic*& OutMid, USkinnedMeshComponent*& OutLeader, float FeetZ, float Height);
	void HideBody(FColumn& C, bool bHide);
	USoundBase* SoundFor(const TCHAR* Id);
	friend class SAstraXportOverlay;
};
