// ASTRA — ABBORDAGGI: the small arms of the Aquila (docs/ABBORDAGGI.md): the service rifle (AR-181) and the sidearm (M27S) the Captain takes from the Deck 8
// armory, and the same rifle in the hands of the marines and of the Mandate's boarders. What a weapon does in the Captain's hands is data here (the table in
// AstraWeapon.cpp: UAstraFpsComponent handles it); the soldiers' fire is the squad simulation's (AstraBoardSim.*, tuned by its own bench), the model the same.
//
// The models are free third-party ones prepared by art/blender/weapons.py (docs/LICENZE.md): the sockets below are what that script writes in
// art/export/weapons/weapons.json (Unreal's frame, centimetres, origin in the middle of the pistol grip, the barrel to +Y, the top +Z).

#pragma once

#include "CoreMinimal.h"

enum class EAstraWeapon : uint8 { None = 0, Rifle = 1, Pistol = 2 };

struct FAstraWeaponDef
{
	EAstraWeapon Id = EAstraWeapon::None;
	const TCHAR* Key = TEXT("");           // "rifle", "pistol" (the console's and the mind's word)
	const TCHAR* Name = TEXT("");          // "AR-181"
	const TCHAR* Role = TEXT("");          // "service rifle"

	// --- how it fires
	bool bAuto = false;
	float Rpm = 600.f;                     // rounds a minute at most (a semi-automatic's cap: one a click)
	int32 Mag = 30;                        // rounds in a magazine
	int32 SpareMags = 4;                   // magazines carried besides the one in it
	float ReloadS = 2.3f;                  // with rounds left in it
	float ReloadEmptyS = 2.9f;             // dry (the bolt is closed on a round)
	float DrawS = 0.8f;                    // from the holster to ready
	float HolsterS = 0.45f;

	// --- what a round does (before the target's armour)
	float Damage = 22.f;
	float HeadMul = 2.4f;
	float LimbMul = 0.75f;
	float FullRangeCm = 2500.f;            // full damage out to here
	float FarRangeCm = 7000.f;             // and this far it has fallen to FarMul
	float FarMul = 0.7f;

	// --- the aim (degrees)
	float HipSpreadDeg = 1.6f;             // the cone a round goes in, from the hip, standing still
	float AdsSpreadDeg = 0.15f;
	float BloomPerShotDeg = 0.18f;         // the cone opens with every round...
	float BloomMaxDeg = 2.2f;
	float BloomRecoverDegS = 4.5f;         // ...and closes again
	float KickPitchDeg = 0.62f;            // the sights climb with every round (the camera's recoil)
	float KickYawDeg = 0.25f;              // and wander to either side by up to this
	float AdsFov = 62.f;                   // the camera's field of view looking through the sights
	float AdsTimeS = 0.18f;
	float MoveMul = 0.9f;                  // walking speed with it in the hands, against empty hands
	float AdsMoveMul = 0.6f;

	// --- the model (Content/ASTRA/Weapons, made by tools/ue_scripts/import_weapons.py)
	const TCHAR* MeshPath = TEXT("");
	const TCHAR* MagPath = TEXT("");       // empty: the model has no magazine of its own
	FVector Muzzle = FVector::ZeroVector;      // cm, palm origin, +Y forward
	FVector Sight = FVector::ZeroVector;       // the rear sight's aperture: the sight line goes through it
	FVector SightFront = FVector::ZeroVector;
	FVector GripL = FVector::ZeroVector;       // where the left hand takes it
	FVector MagWell = FVector::ZeroVector;
	FVector Eject = FVector::ZeroVector;

	// --- the arms: the mannequin's own animations, played on the first-person arms
	const TCHAR* AnimIdle = TEXT("");      // the ready pose (looped)
	const TCHAR* AnimEquip = TEXT("");
	const TCHAR* AnimReload = TEXT("");
	const TCHAR* AnimDry = TEXT("");
	// the right hand's socket (HandGrip_R) in the ready pose, in the mannequin's mesh space (cm; the pose's axes as unit vectors): where the first-person arms put the weapon.
	// Read from the animation by a headless probe; the arms are placed against the camera from these (UAstraFpsComponent::DressArms).
	FVector PoseGripLoc = FVector::ZeroVector;
	FVector PoseGripX = FVector(1.0, 0.0, 0.0), PoseGripY = FVector(0.0, 1.0, 0.0), PoseGripZ = FVector(0.0, 0.0, 1.0);
	float EquipAnimS = 1.6f;               // their lengths, which the handling's times are fitted to
	float ReloadAnimS = 2.2f;
	float DryAnimS = 0.8f;
	// Where the weapon's rear sight (the notch the line of sight goes over, its Sight above) stands against the camera (cm; x ahead, y right, z up) and how the weapon is turned
	// about it (pitch, yaw, roll): at the hip, through the sights and carried low (running, being put away). The weapon is far enough from the camera and small enough on the
	// screen for the arms that hold it to be in the picture: the left hand on the hand-guard and the right on the grip, both forearms coming up from its lower edge; fitted on
	// the bench (tools/boarding.py run --scenario fps, which also checks them) and on offline renders of the arms and the weapon seen with the first-person camera
	// (tools/ue_scripts/make_fp_arms.py, docs/ABBORDAGGI.md §4).
	FVector HipPlace = FVector(76.0, 15.4, -4.0);
	FRotator HipTurn = FRotator(-3.0, -12.0, 0.0);
	FVector AdsPlace = FVector(32.0, 0.0, 0.0);
	FVector LowPlace = FVector(70.0, 30.0, -24.0);
	FRotator LowTurn = FRotator(12.0, -30.0, -20.0);
	float FpFov = 90.f;                     // the first-person camera's field of view while it is in his hands (the arms and the weapon are drawn with it; empty-handed it is the character's)
	FVector GripLHand = FVector::ZeroVector;    // where the left palm goes on the weapon (its own frame, cm): the arm is solved to put the animation's left grip socket there
	// Where the Captain's shoulders stand against the camera (cm; right, left), at the hip and carried low and through the sights, and every place between as the weapon comes up: a body
	// has them near the eye, but the weapon is held far from it so that it is not a third of the picture, and the arms are made to reach it from shoulders that stand as far ahead as the
	// weapon does, below the picture (the cut ends of the arms must not show: the bench checks that, in every state and on the way between them).
	FVector ShoulderHipR = FVector(40.0, 30.0, -55.0);
	FVector ShoulderHipL = FVector(70.0, -18.0, -58.0);
	FVector ShoulderAdsR = FVector(-9.0, 4.0, -32.0);
	FVector ShoulderAdsL = FVector(16.0, -22.0, -30.0);

	// --- the sounds (Content/ASTRA/Audio, synthesised by tools/art/weapon_sounds.py)
	const TCHAR* ShotSound = TEXT("");
	const TCHAR* DrySound = TEXT("");
	const TCHAR* ReloadSound = TEXT("");
	const TCHAR* DrawSound = TEXT("");

	float RoundIntervalS() const { return 60.f / FMath::Max(1.f, Rpm); }
	/** What a round does at a distance: full inside FullRangeCm, falling to FarMul at FarRangeCm and a little more beyond. */
	float DamageAt(float DistCm) const;
};

namespace AstraWeapons
{
	const FAstraWeaponDef& Get(EAstraWeapon Id);
	EAstraWeapon FromKey(const FString& Key);
}
