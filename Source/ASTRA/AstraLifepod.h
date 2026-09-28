// ASTRA — the lifepods: the hatches off Corridor 1-A and the pod the Captain rides away in when the Aquila is abandoned.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "GameFramework/Pawn.h"
#include "AstraLifepod.generated.h"

class UStaticMeshComponent;
class UCameraComponent;
class UPointLightComponent;
class UAudioComponent;
class UMaterialInstanceDynamic;

/** A lifepod's hatch in a corridor wall (SM_POD_Hatch, art/blender/lifepod.py). Sealed until ABANDON SHIP (a green
 *  lamp: ready), then open to board (the lamp blinks amber), red once its pod has gone. */
UCLASS()
class ASTRA_API AAstraLifepodHatch : public AActor
{
	GENERATED_BODY()

public:
	AAstraLifepodHatch();
	virtual void BeginPlay() override;
	virtual void Tick(float DeltaTime) override;

	/** "1-A": the name on the plate, and the pod's call sign. */
	UPROPERTY(EditAnywhere, Category = "Lifepod")
	FString PodName = TEXT("1-A");

	/** Where the pod goes when it is fired (world direction, out of the hull; normalised at launch). */
	UPROPERTY(EditAnywhere, Category = "Lifepod")
	FVector LaunchDir = FVector(-0.25f, -1.f, 0.45f);

	enum class EState : uint8 { Ready, Boarding, Gone };
	void SetState(EState S);
	EState GetState() const { return State; }
	/** The Captain is at the hatch (in front of it, within reach). */
	bool IsWithinReach(const APawn* Pawn) const;
	/** Where the pod starts, outside the hull behind the hatch. */
	FVector PodStart() const;

private:
	UPROPERTY() TObjectPtr<UStaticMeshComponent> Mesh;
	UPROPERTY() TObjectPtr<UMaterialInstanceDynamic> Lamp;
	EState State = EState::Ready;
	float Blink = 0.f;
};

/** The pod itself, from inside (SM_POD_Interior): the Captain strapped into the front seat, the porthole ahead. The
 *  player possesses it; the mouse only looks around. Fired out of the hull it burns for a few seconds, then drifts,
 *  its porthole kept on the ship it left. */
UCLASS()
class ASTRA_API AAstraLifepod : public APawn
{
	GENERATED_BODY()

public:
	AAstraLifepod();
	virtual void Tick(float DeltaTime) override;
	virtual void SetupPlayerInputComponent(UInputComponent* IC) override;

	/** Fired: from Start along Dir (world), the porthole turned towards LookAt. */
	void Launch(const FVector& Start, const FVector& Dir, const FVector& LookAt, const FString& Name);
	float SinceLaunch() const { return Age; }
	const FString& GetPodName() const { return PodName; }
	/** The Aquila's end, felt through the shell: a shake and the sound of it. */
	void FeelBreach(float Strength);

private:
	UPROPERTY() TObjectPtr<USceneComponent> Root;
	UPROPERTY() TObjectPtr<UStaticMeshComponent> Interior;
	UPROPERTY() TObjectPtr<UCameraComponent> Camera;
	UPROPERTY() TObjectPtr<UPointLightComponent> RedLight;
	UPROPERTY() TObjectPtr<UPointLightComponent> PanelGlow;
	UPROPERTY() TObjectPtr<UAudioComponent> Hum;
	FString PodName;
	FVector Vel = FVector::ZeroVector;
	FVector Dir = FVector::ZeroVector;
	FQuat BaseRot = FQuat::Identity;
	FVector LookAtPoint = FVector::ZeroVector;   // the ship it left: the porthole is kept on her
	float Age = -1.f;
	float LookYaw = 0.f;
	float LookPitch = 0.f;
	float Shake = 0.f;
	void MouseX(float V);
	void MouseY(float V);
};
