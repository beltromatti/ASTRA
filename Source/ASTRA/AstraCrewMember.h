// ASTRA — a crew member at a station: a body, a name, and a spatialised voice fed by the crew's minds.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "AstraCrewMember.generated.h"

class UAudioComponent;
class USkeletalMeshComponent;
class USoundWaveProcedural;
class UTextRenderComponent;

UCLASS()
class ASTRA_API AAstraCrewMember : public AActor
{
	GENERATED_BODY()

public:
	AAstraCrewMember();

	/** Station id from data/ship/aquila_bridge.json (helm, ops, tactical, xo...): the mind's `speaker`. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "ASTRA")
	FString StationId;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "ASTRA")
	FString DisplayName;

	/** Starts a new spoken line; PCM16 mono chunks follow through QueueVoice. */
	void BeginLine(int32 LineId, int32 SampleRate);
	void QueueVoice(int32 LineId, const uint8* Pcm, int32 NumBytes);
	void EndLine(int32 LineId);

	bool IsSpeaking() const;

	static AAstraCrewMember* FindByStation(UWorld* World, const FString& Station);

protected:
	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;

	UPROPERTY(VisibleAnywhere, Category = "ASTRA")
	TObjectPtr<USkeletalMeshComponent> Body;

	UPROPERTY(VisibleAnywhere, Category = "ASTRA")
	TObjectPtr<UAudioComponent> Voice;

	UPROPERTY(VisibleAnywhere, Category = "ASTRA")
	TObjectPtr<UTextRenderComponent> NameTag;

private:
	UPROPERTY()
	TObjectPtr<USoundWaveProcedural> CurrentWave;

	int32 CurrentLine = -1;
	float SpeakingLevel = 0.f;
	FRotator RestRotation;
	float FacingBlend = 0.f;     // 0 = at the station, 1 = turned towards the Captain
	float SinceSpoke = 100.f;
};
