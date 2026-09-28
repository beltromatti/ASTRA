// ASTRA — a crew member at a station: a body, a name, and a spatialised voice fed by the crew's minds.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "AstraCrewMember.generated.h"

class UAudioComponent;
class UPoseableMeshComponent;
class USkeletalMeshComponent;
class USoundWaveProcedural;
class UTextRenderComponent;

UENUM()
enum class EAstraCrewPosture : uint8
{
	Standing,       // idle animation (at a rail, walking later)
	SeatedConsole,  // on a chair, hands on the console in front
	SeatedArmchair  // on a chair without a console (XO): forearms on the armrests
};

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

	/** Seated crew sit where the actor is (the chair's centre), facing the actor's +X. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "ASTRA")
	EAstraCrewPosture Posture = EAstraCrewPosture::Standing;

	/** Height of the hip joint above the floor when seated (cm). */
	UPROPERTY(EditAnywhere, Category = "ASTRA")
	float SeatHipHeight = 62.f;

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
	TObjectPtr<UPoseableMeshComponent> Seated;

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
	float Phase = 0.f;           // desynchronises idle motion between crew members
	float LifeTime = 0.f;

	// procedural seated pose: reference pose data and the basis of the body (component space)
	TArray<FTransform> RefLocal;
	TArray<FTransform> RefCS;
	TArray<int32> Parent;
	FVector Fwd = FVector::YAxisVector, Right = FVector::XAxisVector;
	void InitSeated();
	void UpdateSeated(float DeltaSeconds);
	int32 Bone(const TCHAR* Name) const;
};
