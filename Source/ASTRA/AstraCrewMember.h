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
	SeatedArmchair, // on a chair without a console (XO): forearms on the armrests
	Lying           // in a medbay bed, the backrest raised: the actor's origin is the backrest's hinge on the mattress,
	                // its +X towards the head of the bed
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

	/** A woman's body (the placeholder mannequins: Quinn rather than Manny). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "ASTRA")
	bool bFemaleBody = false;

	/** Lying: the backrest's angle (degrees). */
	UPROPERTY(EditAnywhere, Category = "ASTRA")
	float ReclineDeg = 20.f;

	/** A spoken line begins at this officer's place: the wave it plays on (the mind's link queues its PCM16 mono), null
	 *  if the voice cannot play. A line that begins while the last one still sounds (the game fell behind the mind's
	 *  clock) follows it on the same wave instead of cutting it short (docs/protocollo_voce.md §3.2). */
	class UAstraVoiceWave* BeginLine(int32 LineId, int32 SampleRate);
	/** Some of the line's audio arrived: its loudness moves the officer. */
	void HearVoice(const uint8* Pcm, int32 NumBytes);
	/** The mind stopped the line (the Captain spoke, an answer comes first): the voice fades out over FadeSeconds. */
	void CancelLine(float FadeSeconds);
	UAudioComponent* GetVoice() const { return Voice; }

	bool IsSpeaking() const;

	/** Whether a voice carries between them and a listener's ear: near, or a line just over their head reaches it (a
	 *  wall, a bulkhead or a closed door stops a voice; consoles and chairs do not). */
	bool CanBeHeardFrom(const FVector& Eye, const AActor* Listener) const;

	static AAstraCrewMember* FindByStation(UWorld* World, const FString& Station);

	/** Something burst right in front of them (their console shorted out): they recoil and shield their face. */
	void Startle(float Strength);

	/** The placeholder body (a mannequin until the MetaHuman crew), its uniform and its pose; called again when a
	 *  patient's bed changes hands. */
	void SetBody(bool bFemale);

	/** The jacket of someone from the roster (its department: "engineering", "flight deck", "marines"...), not of the
	 *  station: the off-duty crew in the Mess Hall come from all over the ship. */
	void SetUniformDept(const FString& RosterDept);

	/** A visit (the Captain's quarters): the officer leaves their place and walks the route (world, cm, deck level: the
	 *  height follows the points, stairs and the dais included) to its end, where they stand and face the Captain; at the
	 *  point WaitAt they stop for WaitSeconds first (at the door). Leave() walks them back along it (bHurry: at a jog)
	 *  and returns them to their place. */
	void Visit(const TArray<FVector>& Route, int32 WaitAt = INDEX_NONE, float WaitSeconds = 0.f);
	void Leave(bool bHurry = false);
	bool IsVisiting() const { return VisitPhase != 0; }
	bool HasArrived() const { return VisitPhase == 2; }
	bool IsWalking() const { return VisitPhase == 1 || VisitPhase == 3; }
	bool IsWaiting() const { return VisitWaitLeft > 0.f; }
	/** Everyone walking on a visit right now (doors open for them). */
	static const TArray<TWeakObjectPtr<AAstraCrewMember>>& Walkers();

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
	TObjectPtr<class UAstraVoiceWave> CurrentWave;

	int32 CurrentLine = -1;
	float SpeakingLevel = 0.f;
	FRotator RestRotation;
	float FacingBlend = 0.f;     // 0 = at the station, 1 = turned towards the Captain
	float SinceSpoke = 100.f;
	float Phase = 0.f;           // desynchronises idle motion between crew members
	float LifeTime = 0.f;
	float StartleT = 0.f;        // 1 at the burst, down to 0 (recoil, then back to work)
	float StartleStrength = 0.f;

	// procedural seated pose: reference pose data and the basis of the body (component space)
	TArray<FTransform> RefLocal;
	TArray<FTransform> RefCS;
	TArray<int32> Parent;
	FVector Fwd = FVector::YAxisVector, Right = FVector::XAxisVector;
	bool bBodyFemale = false;
	void InitSeated();
	void UpdateSeated(float DeltaSeconds);
	void ApplyUniform();
	FString UniformDept;   // a roster department's uniform (SetUniformDept); empty: the station's
	uint8 VisitPhase = 0;  // 0 at their place, 1 walking there, 2 arrived, 3 walking back
	TArray<FVector> VisitRoute;
	int32 VisitNext = 0;
	int32 VisitWaitAt = INDEX_NONE;
	float VisitWaitS = 0.f;
	float VisitWaitLeft = 0.f;
	float VisitSpeedNow = 140.f;
	FTransform HomeXf;
	EAstraCrewPosture HomePosture = EAstraCrewPosture::Standing;
	void TickVisit(float DeltaSeconds);
	void StandingBody(bool bWalk);   // the standing mannequin, idle or walking
	int32 Bone(const TCHAR* Name) const;
};
