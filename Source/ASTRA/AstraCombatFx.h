// ASTRA — ABBORDAGGI: what a fight inside the ship looks and sounds like beyond the soldiers themselves: the short tracers, the sparks where a round strikes metal and
// the puff where it strikes a man, the flash at a muzzle, the crack of a round that passes the Captain's head, and the sounds of the guns.
//
// A handful of pooled parts (the line mesh and the glow material the bridge's sparks use, AstraBridgeFX.*) that exist only while something is going on: nothing is
// made per shot, nothing ticks while the ship is quiet. Both the Captain's rifle (UAstraFpsComponent) and the soldiers (UAstraBoardSubsystem) draw through it.

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "AstraCombatFx.generated.h"

class AActor;
class UMaterialInstanceDynamic;
class UMaterialInterface;
class UPointLightComponent;
class USoundAttenuation;
class USoundBase;
class UStaticMesh;
class UStaticMeshComponent;

UCLASS()
class ASTRA_API UAstraCombatFx : public UTickableWorldSubsystem
{
	GENERATED_BODY()

public:
	virtual void OnWorldBeginPlay(UWorld& InWorld) override;
	virtual void Deinitialize() override;
	virtual void Tick(float DeltaTime) override;
	virtual TStatId GetStatId() const override { RETURN_QUICK_DECLARE_CYCLE_STAT(UAstraCombatFx, STATGROUP_Tickables); }
	virtual bool ShouldCreateSubsystem(UObject* Outer) const override;

	/** What a round strikes. */
	enum class ESurface : uint8 { Metal, Flesh };

	/** A tracer: a bright streak of Length cm that goes from From to To (world cm) at Speed cm/s and is gone when it arrives. Color is HDR-ish (the glow material's). */
	void Tracer(const FVector& From, const FVector& To, const FLinearColor& Color, float Speed = 70000.f, float Length = 260.f, float Thick = 0.7f);
	/** A round struck: sparks off metal (thrown along the surface's normal), a red puff and a few drops off a man. */
	void Impact(const FVector& At, const FVector& Normal, ESurface Surface);
	/** The flash at a muzzle: a short light, a spray of bright streaks along Dir. */
	void MuzzleFlash(const FVector& At, const FVector& Dir, float Scale = 1.f);
	/** A sound from a content path (cached), at a place: Volume and Pitch as the engine's; the shot's carry is the attenuation's (rooms and corridors shut it in). */
	void PlaySoundAt(const TCHAR* Path, const FVector& At, float Volume = 1.f, float Pitch = 1.f);
	/** A shot was fired from Muzzle to End: the crack of it going by the Captain's head, if it did. */
	void Whiz(const FVector& Muzzle, const FVector& End);

	/** How many parts are in use now (the tests, `astra.board.info`). */
	int32 ActiveParts() const { return Tracers.Num() + Sparks.Num(); }

private:
	struct FTracer
	{
		FVector From = FVector::ZeroVector, Dir = FVector::ForwardVector;
		float Dist = 0.f, Speed = 0.f, Len = 0.f, T = 0.f, Thick = 1.f;
		FLinearColor Color = FLinearColor::White;
		int32 Slot = INDEX_NONE;
	};
	struct FSpark
	{
		FVector Pos = FVector::ZeroVector, Vel = FVector::ZeroVector;
		float Age = 0.f, Life = 0.4f;
		FLinearColor Color = FLinearColor::White;
		int32 Slot = INDEX_NONE;
		bool bDrop = false;
	};

	TArray<FTracer> Tracers;
	TArray<FSpark> Sparks;
	UPROPERTY() TObjectPtr<AActor> Host;
	UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> Pool;
	UPROPERTY() TArray<TObjectPtr<UMaterialInstanceDynamic>> PoolMIDs;
	TArray<int32> FreeSlots;
	UPROPERTY() TArray<TObjectPtr<UPointLightComponent>> Flashes;
	TArray<float> FlashT;
	UPROPERTY() TObjectPtr<UStaticMesh> LineMesh;
	UPROPERTY() TObjectPtr<UMaterialInterface> GlowMat;
	UPROPERTY() TObjectPtr<USoundAttenuation> Attenuation;
	UPROPERTY() TMap<FString, TObjectPtr<USoundBase>> Sounds;
	double LastWhizAt = -10.0;

	int32 TakeSlot();
	void FreeSlot(int32 Slot);
	void Paint(int32 Slot, const FVector& Pos, const FVector& Dir, float Len, float Thick, const FLinearColor& Color, float Intensity);
	USoundBase* SoundOf(const TCHAR* Path);
};
