// ASTRA — the lamps of the ship's decks are data, and a handful of real lights follow the Captain (docs/NAVE.md §7bis). A built deck has some 250 lamps
// (the plan's compartments[].lights: a 15 m rectangle over every corridor section, panels over the rooms); twelve decks have 3000. As actors, 3000 light
// components in the level; as data, a flat array of FAstraPlanLamp in the plan, and a pool of ~12 URectLightComponent that this subsystem moves onto the
// lamps nearest the Captain that he can see: his own room, the corridor he stands in as far as he can see down it, and the room behind a door when he is at
// the door. A lamp leaves and arrives by fading (0.35 s), so nothing pops when the pool is re-pointed.
//
// The lights of the older rooms (bridge, Mess Hall, Medbay, Engineering, Flight Deck) are actors of the persistent level and keep their own rules
// (AstraZoneLights.*, AstraHangar.*).
//
// The damage inside the ship (DISTRUZIONE, docs/DISTRUZIONE.md) reaches the lamps here: a compartment that lost its power burns only the emergency strips (red,
// dim), one with a faulty supply or a blow a moment ago flickers, one on fire is orange, one open to space is red, one full of smoke is dimmer, a lost one is dark.

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "AstraLampPool.generated.h"

class AActor;
class UAstraShipPlan;
class UMaterialParameterCollection;
class URectLightComponent;

/** Which lamps should burn for a Captain at a place: the choice itself, with no engine objects but the plan, so that a commandlet can run it. */
struct ASTRA_API FAstraLampPicker
{
	/** At most `Max` lamps (indices into Plan.GetLamps()), best first: those within ReachCm of the eye on his deck (and the one above and below), in his
	 *  compartment or the ones he can see into by an open way (a corridor into the next section) or through a door he is near. `Lit`: the lamps burning
	 *  now, which keep their place unless clearly beaten. */
	static void Pick(const UAstraShipPlan& Plan, const FVector& Eye, const FVector& Feet, int32 Max, float ReachCm, const TSet<int32>& Lit,
	                 TArray<int32>& Out, int32* OutCompartment = nullptr);
	/** A room behind a door is lit while the Captain is within this many cm of the door. */
	static constexpr float DoorSeeCm = 900.f;
};

UCLASS()
class ASTRA_API UAstraLampPool : public UTickableWorldSubsystem
{
	GENERATED_BODY()

public:
	virtual bool ShouldCreateSubsystem(UObject* Outer) const override;
	virtual void OnWorldBeginPlay(UWorld& InWorld) override;
	virtual void Deinitialize() override;
	virtual void Tick(float DeltaTime) override;
	virtual TStatId GetStatId() const override { RETURN_QUICK_DECLARE_CYCLE_STAT(UAstraLampPool, STATGROUP_Tickables); }

	/** Lamps burning (or fading) now, the pool's size, the lamps of the plan. */
	int32 NumLit() const;
	int32 PoolSize() const { return Slots.Num(); }
	FString Describe() const;

	/** The tests' Captain: where the eye and the feet are (no pawn, no camera needed). */
	void SetTestCaptain(const FVector& InEye, const FVector& InFeet) { bTest = true; TestEye = InEye; TestFeet = InFeet; }
	/** Picks the lamps now (the tests call it after moving the Captain, then Advance to finish the fades). */
	void ReselectNow() { Reselect(); }
	void Advance(float Seconds);
	/** Lamp indices lit now, for the tests. */
	TArray<int32> LitLamps() const;

private:
	struct FSlot
	{
		TWeakObjectPtr<URectLightComponent> Light;
		int32 Lamp = INDEX_NONE;     // the plan's lamp it stands for
		float Level = 0.f;           // 0..1: the fade
		float Target = 0.f;
		float Applied = -1.f;        // the intensity last set (to skip a set that changes nothing)
		// what the damage inside the ship leaves of the lamp (read from the interior model at each pass: UAstraShipSubsystem::GetInterior().LightOf)
		int32 ModelComp = INDEX_NONE;                       // the damage model's compartment the lamp is in
		float Mains = 1.f, Strips = 0.f, Flicker = 0.f;     // the room's power share, the emergency strips' share, how unsteady
		float Unsteady = 1.f;                               // the flicker's factor of this instant
		float Mix = 0.f;
		FLinearColor Tint = FLinearColor::White;
		float AppliedMix = -1.f;
		FLinearColor AppliedTint = FLinearColor::White;
	};
	UPROPERTY() TObjectPtr<AActor> PoolActor;
	TArray<FSlot> Slots;
	TWeakObjectPtr<UMaterialParameterCollection> ShipMPC;
	float Accum = 0.f;
	float LightLevel = 1.f;          // the ship's light level and the red alert's tint, read from the ship's material collection
	float AlertBlend = 0.f;
	float AppliedAlert = -1.f;
	float FlickT = 0.f;              // the flicker is drawn at about 12 Hz, not every frame
	bool bTest = false;
	FVector TestEye = FVector::ZeroVector, TestFeet = FVector::ZeroVector;

	bool CaptainView(FVector& OutEye, FVector& OutFeet) const;
	void Reselect();
	void Assign(FSlot& S, int32 Lamp);
	void Apply(FSlot& S, bool bTint);
	void ReadShipState();
	void ReadDamage(FSlot& S, const class UAstraShipSubsystem* Ship) const;
};
