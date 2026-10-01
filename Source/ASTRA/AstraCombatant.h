// ASTRA — ABBORDAGGI: the body of a soldier in the fight inside the ship (docs/ABBORDAGGI.md): a marine of the Aquila (the person VITA keeps in the roster, with their
// name and their uniform) or a boarder of the Mandate. It is the same body as the crew's (AAstraCrewMember: the mannequin, the uniform, the voice and the earshot, so
// the minds and the Captain's words treat a marine as one of the people aboard), with a rifle in its hands, playing the mannequin's rifle animations.
//
// The soldier's mind is the squad simulation's (AstraBoardSim.*): this body only shows it. UAstraBoardSubsystem makes the bodies of the soldiers near the Captain (a
// pooled few), gives each its unit of the simulation each tick (Drive), and takes the Captain's rounds back: a round that strikes the body is the unit's wound.

#pragma once

#include "CoreMinimal.h"
#include "AstraBoardSim.h"
#include "AstraCrewMember.h"
#include "AstraCombatant.generated.h"

class UAnimSequence;
class UMaterialInstanceDynamic;
class UStaticMeshComponent;

UCLASS()
class ASTRA_API AAstraCombatant : public AAstraCrewMember
{
	GENERATED_BODY()

public:
	AAstraCombatant();

	/** Becomes a soldier: name, side, body, uniform, the place and the way he stands. RosterIdx: the roster's person (a marine), INDEX_NONE for the Mandate. */
	void Bind(int32 InUnit, bool bInMandate, const FString& InName, bool bFemale, int32 InRoster, const FVector& At, float Yaw);
	/** Back to the pool: hidden, not ticking. */
	void Unbind();
	int32 UnitId() const { return UnitIdx; }
	bool InUse() const { return UnitIdx != INDEX_NONE; }
	bool IsMandate() const { return bMandate; }
	int32 RosterIndex() const { return RosterIdx; }
	const FString& SoldierName() const { return NameOf; }

	/** This tick of the squad simulation's soldier: where he is (feet, cm), which way he faces, what he does. Dt: the game's frame. */
	void Drive(const AstraBoard::FUnit& U, float Dt);
	/** Where his rifle's muzzle is now (world cm), and the way it points. */
	FVector MuzzleAt() const;
	FVector MuzzleDir() const;
	/** He fired: the little kick of the rifle on his shoulder. */
	void NoteShot();
	/** He was hit from a place (world cm): which way he falls if he does. */
	void NoteHit(const FVector& From);
	/** The pose he is in now is a fallen man's. */
	bool IsFallen() const { return bFallen; }
	/** Seen by the camera lately (not worth a body when nobody sees it). */
	bool SeenRecently(float Within = 1.0f) const { return Body && Body->WasRecentlyRendered(Within); }

	/** The bone a trace hit, as a share of the man it is on: the head, the limbs, the rest (the Captain's rounds hit by where they land). */
	enum class EZone : uint8 { Body, Head, Limb };
	static EZone ZoneOfBone(const FName& Bone);

	/** The assets every soldier needs, loaded now and given back to be kept (the first soldier made would pay for them in the middle of a frame). */
	static void PreloadAssets(TArray<TObjectPtr<UObject>>& OutKeep);

protected:
	virtual void Tick(float DeltaSeconds) override;

private:
	enum class EPose : uint8 { None, Idle, Walk, Jog, Reload, Fallen };

	int32 UnitIdx = INDEX_NONE;
	int32 RosterIdx = INDEX_NONE;
	bool bMandate = false;
	bool bFallen = false;
	FString NameOf;
	FVector Goal = FVector::ZeroVector;      // where the simulation puts his feet
	float GoalYaw = 0.f;
	float FaceYaw = 0.f;                     // the way he faces now (degrees)
	FVector Vel = FVector::ZeroVector;       // his velocity, from his moves (cm/s)
	float FloorZ = 0.f;                      // the deck under his feet, found with a trace now and then
	float FloorT = 0.f;
	float SinceDrive = 0.f;
	float PoseT = 0.f;                       // since the animation last changed
	EPose Pose = EPose::None;
	int32 PoseSub = -1;                      // which of the eight ways (walk, jog) or which fall
	float KickT = 0.f;
	FVector HitFrom = FVector::ZeroVector;
	bool bHaveHitFrom = false;
	bool bHide = false;
	bool bStairs = false;
	bool bFirstDrive = true;

	UPROPERTY() TObjectPtr<UStaticMeshComponent> Gun;
	UPROPERTY() TObjectPtr<UMaterialInstanceDynamic> JacketMID;
	UPROPERTY() TObjectPtr<UMaterialInstanceDynamic> TrousersMID;

	void DressMandate();
	void ArmUp();
	void SetPose(EPose P, int32 Sub, float Rate = 1.f);
	void Show(bool bOn);
};
