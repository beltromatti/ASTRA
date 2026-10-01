// ASTRA — DISTRUZIONE: what the damage inside the Aquila looks and sounds like near the Captain (docs/DISTRUZIONE.md).
//
// The damage model (AstraDamageModel.*) knows every compartment that burns, vents or has lost its power. This subsystem shows the few of them the Captain
// can see and hear: flames and smoke where a room burns, the hole a blow made with the containment field shimmering on it (or the air streaking out of it,
// and a scorch on the wall), sparks where the conduits are cut, the suppression's mist, a blow going off, the slam of a pressure bulkhead and the sign the
// shut door wears. The lights are the lamp pool's (AstraLampPool.*: the room goes red on its emergency strips).
//
// The cost is kept to a handful of pooled parts that exist only for the nearest hazards on the decks that are loaded: no actor per compartment, nothing
// ticking for a room the Captain cannot be in, no text redrawn. Which hazards deserve a part is decided by FAstraFxPlanner, which is plain code over the
// model (the bench runs it); the subsystem only turns its answer into parts, four times a second, and animates them.

#pragma once

#include "CoreMinimal.h"
#include "AstraDamageModel.h"
#include "Subsystems/WorldSubsystem.h"
#include "AstraDamageFx.generated.h"

class AActor;
class AAstraDoor;
class UAudioComponent;
class UDecalComponent;
class UMaterialInstanceDynamic;
class UMaterialInterface;
class UPointLightComponent;
class USoundAttenuation;
class USoundBase;
class UStaticMesh;
class UStaticMeshComponent;
class UTextRenderComponent;

/** How many of each effect the Captain's eyes and ears get at once, and how far they reach. */
struct ASTRA_API FAstraFxBudget
{
	int32 Fires = 3;              // rooms on fire shown with flames
	int32 Hazes = 3;              // rooms full of smoke
	int32 Vents = 2;              // holes (the field on them, or the air streaking out)
	int32 Sparks = 2;             // rooms where the conduits spit
	int32 Mists = 1;              // rooms the fixed suppression is discharging in
	float ReachCm = 3500.f;       // how far off a room can be (its walls, from the Captain's eye)
};

/** What the effects show now: the hazards chosen from the model for a Captain at a place. */
struct ASTRA_API FAstraFxPlan
{
	struct FFire { int32 Comp = INDEX_NONE; float Level = 0.f; float Dist = 0.f; FVector Anchor = FVector::ZeroVector; FBox Box = FBox(ForceInit); };
	struct FHaze { int32 Comp = INDEX_NONE; float Level = 0.f; float Dist = 0.f; FBox Box = FBox(ForceInit); bool bMist = false; };
	struct FVent
	{
		int32 Comp = INDEX_NONE;
		float Hole = 0.f;                  // m2
		float Air = 1.f;                   // the room's pressure
		float Dist = 0.f;
		FVector At = FVector::ZeroVector;  // on the wall (cm)
		FVector Normal = FVector::ForwardVector;     // out of the room
		float RadiusCm = 40.f;
		FAstraDmgState::EField Field = FAstraDmgState::EField::Off;
		float Stress = 0.f;
	};
	struct FSpark { int32 Comp = INDEX_NONE; float Level = 0.f; float Dist = 0.f; FVector Anchor = FVector::ZeroVector; FBox Box = FBox(ForceInit); };
	TArray<FFire> Fires;
	TArray<FHaze> Hazes;
	TArray<FVent> Vents;
	TArray<FSpark> Sparks;
	int32 Total() const { return Fires.Num() + Hazes.Num() + Vents.Num() + Sparks.Num(); }
};

/** The choice of what to show: plain code over the model, no engine objects, so the bench can run it. */
class ASTRA_API FAstraFxPlanner
{
public:
	/** The hazards of the model near an eye (world cm), nearest first, each kind kept to its budget. `IsReady(cm)` says whether the ship around a point is in the
	 *  world (a deck that has not streamed in has nothing to show them on); null: everywhere is. */
	static void Plan(const FAstraDamageModel& Model, const FVector& Eye, const FAstraFxBudget& Budget, const TFunction<bool(const FVector& Cm)>& IsReady, FAstraFxPlan& Out);
	/** Where the n-th of Count flames of a fire stands: round the fire's anchor, kept inside the room (deterministic: a room burns in the same places each time). */
	static FVector FlameSpot(const FAstraFxPlan::FFire& Fire, int32 Index, int32 Count);
	/** The wall a hole is in: the point on it (cm) and the normal out of the room, from the room's walls and where the blow came in. */
	static void HoleWall(const FBox& Room, const FVector& HoleAt, FVector& OutPoint, FVector& OutNormal);
};

UCLASS()
class ASTRA_API UAstraDamageFx : public UTickableWorldSubsystem
{
	GENERATED_BODY()

public:
	virtual bool ShouldCreateSubsystem(UObject* Outer) const override;
	virtual void OnWorldBeginPlay(UWorld& InWorld) override;
	virtual void Deinitialize() override;
	virtual void Tick(float DeltaTime) override;
	virtual TStatId GetStatId() const override { RETURN_QUICK_DECLARE_CYCLE_STAT(UAstraDamageFx, STATGROUP_Tickables); }

	/** A blow has just gone off in the compartments of R: the boom where it is near the Captain, the shower of sparks, the hole opening. */
	void OnBlow(const FAstraImpactResult& R, float Energy);
	/** A pressure bulkhead was shut (or opened) at a place (world cm): the slam, if it is near. */
	void OnBulkhead(const FVector& AtCm, bool bSealed);
	/** A door actor is shut by a sealed bulkhead (or let go): the sign it wears (made the first time, then shown or hidden). */
	void DressDoor(AAstraDoor* Door, bool bSealed);

	/** What is on show now, in a line a part (the console's info). */
	FString Describe() const;
	/** Parts in use now (the bench and the info). */
	int32 NumParts() const;

	/** The tests' Captain: where the eye is (no pawn, no camera needed). */
	void SetTestEye(const FVector& Eye) { bTest = true; TestEye = Eye; }

private:
	enum class EPart : uint8 { Flame, Smoke, Mist, Field, Num };
	struct FPart
	{
		TWeakObjectPtr<UStaticMeshComponent> Mesh;
		TWeakObjectPtr<UMaterialInstanceDynamic> Mid;
	};
	/** A part standing for something in a room (a flame, a puff, the field on a hole), fading in and out. */
	struct FInst
	{
		EPart Kind = EPart::Flame;
		int32 Comp = INDEX_NONE;
		int32 Index = 0;
		FPart Part;
		FVector Pos = FVector::ZeroVector;
		FVector Normal = FVector::UpVector;
		float Size = 100.f;
		float Strength = 0.f;
		float Stress = 0.f;
		uint8 Mode = 0;                 // a field: 1 forming, 2 holding, 3 failed
		float Level = 0.f, Target = 0.f;
		float Phase = 0.f;
		float Shown = -1.f;
	};
	struct FStreak
	{
		FPart Part;
		FVector Pos = FVector::ZeroVector, Vel = FVector::ZeroVector, Hole = FVector::ZeroVector;
		float Age = 0.f, Life = 1.f;
	};
	struct FLightSlot
	{
		TWeakObjectPtr<UPointLightComponent> Light;
		int32 Comp = INDEX_NONE;
		float Level = 0.f, Target = 0.f;
		FVector Pos = FVector::ZeroVector;
		float Phase = 0.f;
	};
	struct FScar
	{
		int32 Comp = INDEX_NONE;
		TWeakObjectPtr<UDecalComponent> Decal;
		TWeakObjectPtr<UMaterialInstanceDynamic> Mid;
		float Level = 0.f, Target = 0.f;
	};
	struct FLoop
	{
		TWeakObjectPtr<UAudioComponent> Audio;
		TWeakObjectPtr<USoundBase> Sound;
		FVector At = FVector::ZeroVector;
		float Level = 0.f, Target = 0.f, Pitch = 1.f;
		bool bWanted = false;
	};
	struct FSign
	{
		TWeakObjectPtr<AAstraDoor> Door;
		TWeakObjectPtr<UTextRenderComponent> Front, Back;
		bool bOn = false;
	};

	UPROPERTY() TObjectPtr<AActor> FxActor;
	UPROPERTY() TObjectPtr<UStaticMesh> SphereMesh;
	UPROPERTY() TObjectPtr<UStaticMesh> LineMesh;
	UPROPERTY() TObjectPtr<UMaterialInterface> BlastMat;
	UPROPERTY() TObjectPtr<UMaterialInterface> SmokeMat;
	UPROPERTY() TObjectPtr<UMaterialInterface> GlowMat;
	UPROPERTY() TObjectPtr<UMaterialInterface> ScarMat;
	UPROPERTY() TObjectPtr<UMaterialInterface> TextMat;
	UPROPERTY() TObjectPtr<USoundBase> BlastSound;
	UPROPERTY() TObjectPtr<USoundBase> DecompressSound;
	UPROPERTY() TObjectPtr<USoundBase> SlamSound;
	UPROPERTY() TObjectPtr<USoundAttenuation> Falloff;
	UPROPERTY() TObjectPtr<UMaterialInstanceDynamic> SignMid;
	UPROPERTY() TArray<TObjectPtr<USoundBase>> LoopSounds;
	TArray<FInst> Insts;
	TArray<FPart> Spare[(int32)EPart::Num];
	TArray<FStreak> Streaks;
	TArray<FPart> SpareStreaks;
	TArray<FLightSlot> Lights;
	TArray<FScar> Scars;
	FLoop Loops[4];                                  // fire, vent, field, mist
	TMap<int32, float> SparkNext;                    // a room's next shower of sparks (seconds)
	TMap<uint32, FSign> Signs;                       // by the door actor's id
	FAstraFxPlan Plan;
	float PlanT = 0.f;
	float Clock = 0.f;
	float StreakCarry = 0.f;
	float LastBoom = -10.f, LastSlam = -10.f;
	bool bTest = false;
	bool bAssetsTold = false;
	FVector TestEye = FVector::ZeroVector;
	FVector LastEye = FVector::ZeroVector;
	bool bHaveEye = false;
	double MsAvg = 0.0;

	bool CaptainEye(FVector& OutEye) const;
	bool Ready(const FVector& Cm) const;
	void Replan();
	void Animate(float Dt);
	void Upsert(EPart Kind, int32 Comp, int32 Index, const FVector& Pos, const FVector& Normal, float Size, float Strength, uint8 Mode, float Stress);
	FPart TakePart(EPart Kind);
	void GiveBack(EPart Kind, FPart& P);
	void StepStreaks(float Dt);
	void StepLights(float Dt);
	void StepScars(float Dt);
	void StepLoops(float Dt);
	void SparkShower(const FAstraFxPlan::FSpark& S, float Strength);
	void WantLoop(int32 Which, const FVector& At, float Level, float Pitch);
	void PlayAt(USoundBase* Sound, const FVector& At, float Volume, float Pitch = 1.f);
	void HideAll();
};
