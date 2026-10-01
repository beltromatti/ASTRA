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
	float EquipAnimS = 1.6f;               // their lengths, which the handling's times are fitted to
	float ReloadAnimS = 2.2f;
	float DryAnimS = 0.8f;

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
