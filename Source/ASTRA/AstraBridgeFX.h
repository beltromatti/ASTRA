// ASTRA — what a hard hit does to the bridge: a shorted light fixture or a console spits a shower of sparks that
// bounce on the deck and cool from white to red, a flash of orange light, the crackle of the discharge.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "AstraBridgeFX.generated.h"

class UMaterialInstanceDynamic;
class UMaterialInterface;
class UPointLightComponent;
class USoundBase;
class UStaticMesh;
class UStaticMeshComponent;

UCLASS()
class ASTRA_API AAstraBridgeFX : public AActor
{
	GENERATED_BODY()

public:
	AAstraBridgeFX();
	virtual void BeginPlay() override;
	virtual void Tick(float DeltaTime) override;

	/** A burst of sparks from a random fixture or console of the bridge (Strength 0..1: how many, how violent). */
	void RandomBurst(float Strength);
	/** A burst at a given point (world cm), thrown along Dir (with spread). */
	void Burst(const FVector& At, const FVector& Dir, float Strength);

private:
	struct FSpark
	{
		FVector Pos, Vel;
		float Age = 0.f, Life = 1.f;
		float Floor = 0.f;
		int32 Slot = -1;
	};
	TArray<FSpark> Sparks;
	UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> Pool;
	UPROPERTY() TArray<TObjectPtr<UMaterialInstanceDynamic>> PoolMIDs;
	TArray<int32> FreeSlots;
	UPROPERTY() TObjectPtr<UPointLightComponent> Flash;
	float FlashT = 0.f;
	UPROPERTY() TObjectPtr<UStaticMesh> LineMesh;
	UPROPERTY() TObjectPtr<UMaterialInterface> GlowMat;
	UPROPERTY() TObjectPtr<USoundBase> SparkSound;
	TArray<TPair<FVector, FVector>> Sources;   // where sparks can come from on the bridge, and which way they fly
	TArray<bool> SourceIsConsole;
	void CollectSources();
	int32 TakeSlot();
};
