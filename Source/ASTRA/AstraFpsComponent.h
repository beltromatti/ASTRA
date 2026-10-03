// ASTRA — ABBORDAGGI: the Captain with a weapon in his hands (docs/ABBORDAGGI.md). The first-person core: the rifle and the sidearm from the Deck 8 armory, the arms (the
// mannequin's own animations on a first-person body: drawing, holding, reloading), the aim (the right button looks through the sights; the cone of the rounds is
// the weapon's, the posture's and the movement's), the rounds (hitscan, short tracers, impacts, the sounds), the recoil (the sights climb and wander, the weapon kicks on his
// shoulder), the reload, the change of weapon, and the screen that goes with it (the crosshair, the rounds, how he is, where it hurts, the keys).
//
// The Captain's walking, crouching and lying down are the character's (ASTRACharacter.*): this component asks the character what he is doing (posture, speed, sprint) and tells it
// what the weapon costs him (his pace, how fast he turns while aiming). A round that strikes a soldier is the soldier's wound (UAstraBoardSubsystem::PlayerHit); a round
// that reaches the Captain is his (UAstraBoardSubsystem calls OnHurt).

#pragma once

#include "CoreMinimal.h"
#include "AstraArmsRig.h"
#include "AstraWeapon.h"
#include "Components/ActorComponent.h"
#include "AstraFpsComponent.generated.h"

class AASTRACharacter;
class UCameraComponent;
class UPoseableMeshComponent;
class USkeletalMeshComponent;
class UStaticMeshComponent;
class UAnimSequence;
struct FKey;
class FOutputDevice;

UCLASS(ClassGroup = (ASTRA))
class ASTRA_API UAstraFpsComponent : public UActorComponent
{
	GENERATED_BODY()

public:
	UAstraFpsComponent();
	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type Reason) override;
	virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;

	// ------------------------------------------------------------------------------------------------ the kit
	/** The Captain takes the rifle and the sidearm with all the rounds they carry (the armory); false puts them back. Drawn: the rifle. */
	void SetKit(bool bTake);
	bool HasKit() const { return bHasKit; }
	/** A weapon is in his hands or on its way there (drawing, ready, reloading). */
	bool IsArmed() const { return State != EState::Holstered && State != EState::Holstering; }
	EAstraWeapon Current() const { return Cur; }
	/** "AR-181 24/90", or empty when he carries nothing (the mind's picture of the Captain). */
	FString StatusText() const;
	int32 Rounds(EAstraWeapon W) const { return W == EAstraWeapon::Rifle ? Rifle.Mag : (W == EAstraWeapon::Pistol ? Pistol.Mag : 0); }
	int32 Spare(EAstraWeapon W) const { return W == EAstraWeapon::Rifle ? Rifle.Reserve : (W == EAstraWeapon::Pistol ? Pistol.Reserve : 0); }

	// ------------------------------------------------------------------------------------------------ the controls (the character binds them)
	void FirePressed();
	void FireReleased();
	void AimPressed();
	void AimReleased();
	void ReloadPressed();
	void SelectWeapon(EAstraWeapon W);
	void CycleWeapon(float Direction);
	void QuickSwitch();
	void ToggleHolster();
	void SelectRifle() { SelectWeapon(EAstraWeapon::Rifle); }
	void SelectPistol() { SelectWeapon(EAstraWeapon::Pistol); }
	void WheelInput(const struct FInputActionValue& Value);

	// ------------------------------------------------------------------------------------------------ what the weapon costs the Captain (the character asks)
	/** His pace with the weapon in his hands, against empty ones (1 when none is drawn). */
	float MoveMultiplier() const;
	/** How much of his turn is left looking through the sights (the field of view's share), 1 when not aiming. */
	float LookMultiplier() const;
	/** Aiming down the sights now (0 hip .. 1 sights). */
	float AdsAlpha() const { return Ads; }

	// ------------------------------------------------------------------------------------------------ the fight tells him
	/** A round of the enemy reached him from a place (world cm): the screen shows where, the weapon jerks. */
	void OnHurt(const FVector& From, float Amount);
	/** A short line on the screen where the keys are told ("E  TAKE THE WEAPONS"). */
	void Prompt(const FString& Text, float Seconds);

	/** The tests: fire once, as if the button were pressed and released; the rounds that were fired are counted. */
	int32 ShotsFired() const { return NumShots; }
	int32 HitsLanded() const { return NumHits; }

	/** The tests (astra.fps.* in the console): a key goes into the player's input as the viewport would send it, so that it takes the road of a real one (the mapping, the action, the
	 *  binding); and a report of the state, the arms and where the weapon stands in the view. */
	void SimulateKey(const FKey& Key, bool bDown);
	void Describe(FOutputDevice& Ar) const;

private:
	enum class EState : uint8 { Holstered, Drawing, Ready, Reloading, Holstering };
	struct FAmmo { int32 Mag = 0; int32 Reserve = 0; };

	EState State = EState::Holstered;
	EAstraWeapon Cur = EAstraWeapon::None;       // the weapon in hand (or being drawn)
	EAstraWeapon Last = EAstraWeapon::None;      // the one before (the quick switch)
	EAstraWeapon Next = EAstraWeapon::None;      // the one he is changing to (while the first is put away)
	bool bHasKit = false;
	FAmmo Rifle, Pistol;
	float StateT = 0.f;                          // since the state began
	float StateLen = 0.f;                        // how long it lasts (the draw, the reload)
	bool bFireHeld = false;
	bool bTriggerLatched = false;                // a semi-automatic fires once a click
	bool bAimHeld = false;
	int32 AimEvents = 0, FireEvents = 0;         // how many times the actions arrived (the console's report: an input that never gets here is not the weapon's fault)
	bool bSprint = false;
	bool bLocked = false;                        // seated, in a lift, down: no weapon in the hands
	float Ads = 0.f;                             // 0 hip .. 1 sights
	double NextShotAt = 0.0;
	float Bloom = 0.f;                           // degrees the cone has opened with the rounds
	float RecoilPitch = 0.f;                     // what the sights have climbed since he began to fire (degrees), to be brought back down
	float SinceShot = 10.f;
	float DryT = 0.f;
	int32 NumShots = 0, NumHits = 0;
	bool bAutoReloadPending = false;

	// --- what the screen shows
	float HurtAlpha = 0.f;                       // the red at the edges
	struct FArc { float Yaw = 0.f; float Alpha = 0.f; };
	TArray<FArc> Arcs;                           // where it came from (degrees round the view)
	float HitMark = 0.f;                         // the white cross of a round that struck
	bool bHitWasHead = false;
	float KeysAlpha = 0.f;                       // the strip that tells the keys, up for a while when he arms
	float KeysT = 0.f;
	double KeysShownAt = -1000.0;                // when the card of keys was last put up (it does not come again at every draw)
	FString PromptText;
	float PromptT = 0.f;
	TSharedPtr<class SAstraCombatHud> Hud;

	// --- the arms: the mannequin's animation plays on a hidden skeletal mesh (Arms: the weapon rides its right-hand socket); what is seen is a poseable copy of it (Pose) whose
	// arms are solved to the weapon (AstraArmsRig.h): the shoulders where a body would have them, the left hand on the hand-guard
	UPROPERTY() TObjectPtr<USkeletalMeshComponent> Arms;
	UPROPERTY() TObjectPtr<UPoseableMeshComponent> Pose;
	UPROPERTY() TObjectPtr<UStaticMeshComponent> Gun;
	UPROPERTY() TObjectPtr<UStaticMeshComponent> Mag;
	UPROPERTY() TObjectPtr<UAnimSequence> AnimIdle;
	UPROPERTY() TObjectPtr<UAnimSequence> AnimEquip;
	UPROPERTY() TObjectPtr<UAnimSequence> AnimReload;
	UPROPERTY() TObjectPtr<UAnimSequence> AnimDry;
	AstraArms::FBones ArmBones;
	EAstraWeapon ArmsFor = EAstraWeapon::None;   // the weapon the arms and the gun are made for now
	bool bCalibrated = false;
	FQuat HipRot = FQuat::Identity, AdsRot = FQuat::Identity, LowRot = FQuat::Identity;       // where the arms stand against the camera: hip, sights and lowered (cm, relative to the camera)
	FVector HipLoc = FVector::ZeroVector, AdsLoc = FVector::ZeroVector, LowLoc = FVector::ZeroVector;
	FVector SightInMesh = FVector::ZeroVector;
	float TuneStamp = 0.f;                       // the console's nudges of the places when they were last applied (a change calibrates again)
	bool bArmsOnly = false;                      // the arms are the arms-only mesh (else the whole mannequin with its head and neck hidden)
	float LeftIk = 0.f;                          // how much the left hand is on the weapon's grip (0: as the animation moves it, 1: on the hand-guard)
	FQuat MeshQ = FQuat::Identity;               // where the arms stand against the camera this frame (the solve works from it)
	FVector MeshLoc = FVector::ZeroVector;
	FVector KickPos = FVector::ZeroVector, KickVel = FVector::ZeroVector;     // the weapon's kick on his shoulder (spring)
	float KickPitch = 0.f, KickPitchVel = 0.f;
	FVector2D Sway = FVector2D::ZeroVector;      // the weapon lags behind his turn
	FVector2D LookRate = FVector2D::ZeroVector;
	FRotator LastView = FRotator::ZeroRotator;
	float BobT = 0.f;
	float SprintAlpha = 0.f;
	bool bShown = false;
	FRotator LastControl = FRotator::ZeroRotator;
	float BaseFov = 90.f;
	bool bFovTaken = false;                      // the camera's field of view is ours (through the sights): to be given back
	float BaseFpFov = 70.f;
	bool bFpFovTaken = false;                    // the camera's first-person field of view is ours (the weapon is in his hands): to be given back

	// --- the helpers
	AASTRACharacter* Owner() const;
	UCameraComponent* Camera() const;
	FAmmo& AmmoOf(EAstraWeapon W) { return W == EAstraWeapon::Rifle ? Rifle : Pistol; }
	const FAmmo& AmmoOf(EAstraWeapon W) const { return W == EAstraWeapon::Rifle ? Rifle : Pistol; }
	bool Locked() const;
	void StartDraw(EAstraWeapon W);
	void StartHolster(EAstraWeapon Then);
	void StartReload();
	void CancelReload();
	void TickState(float Dt);
	bool TryFire();
	void FireRound(const FAstraWeaponDef& W);
	float SpreadDeg(const FAstraWeaponDef& W) const;
	void Recoil(const FAstraWeaponDef& W);
	void TickRecoil(float Dt);
	void EnsureArms();
	void DressArms(EAstraWeapon W);
	void Calibrate(const FAstraWeaponDef& W);
	void ApplyNudges();
	void SolveArms(const FAstraWeaponDef& W, float Dt);
	void TickFpFov(float Dt);
	void PlayArms(UAnimSequence* A, bool bLoop, float Rate = 1.f);
	void TickArms(float Dt);
	void ShowArms(bool bOn);
	void RestoreFov();
	void RestoreFpFov();
	void TickHud(float Dt);
	void RemoveHud();
	FVector MuzzleGuess(const FVector& Eye, const FRotator& View) const;
	void Sound(const TCHAR* Path, float Volume = 1.f, float Pitch = 1.f);
};
