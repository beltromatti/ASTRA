#include "AstraWeapon.h"

namespace
{
	FAstraWeaponDef WpnMakeRifle()
	{
		FAstraWeaponDef W;
		W.Id = EAstraWeapon::Rifle;
		W.Key = TEXT("rifle");
		W.Name = TEXT("AR-181");
		W.Role = TEXT("service rifle");
		W.bAuto = true;
		W.Rpm = 650.f;
		W.Mag = 30;
		W.SpareMags = 4;
		W.ReloadS = 2.3f;
		W.ReloadEmptyS = 2.9f;
		W.DrawS = 0.85f;
		W.HolsterS = 0.45f;
		W.Damage = 22.f;
		W.HeadMul = 2.4f;
		W.LimbMul = 0.75f;
		W.FullRangeCm = 2500.f;
		W.FarRangeCm = 7000.f;
		W.FarMul = 0.7f;
		W.HipSpreadDeg = 1.6f;
		W.AdsSpreadDeg = 0.15f;
		W.BloomPerShotDeg = 0.18f;
		W.BloomMaxDeg = 2.2f;
		W.BloomRecoverDegS = 4.5f;
		W.KickPitchDeg = 0.62f;
		W.KickYawDeg = 0.25f;
		W.AdsFov = 62.f;
		W.AdsTimeS = 0.18f;
		W.MoveMul = 0.9f;
		W.AdsMoveMul = 0.6f;
		W.MeshPath = TEXT("/Game/ASTRA/Weapons/SM_AR181.SM_AR181");
		W.MagPath = TEXT("/Game/ASTRA/Weapons/SM_AR181_Mag.SM_AR181_Mag");
		// art/export/weapons/weapons.json (art/blender/weapons.py)
		W.Muzzle = FVector(0.f, 68.85f, 11.53f);
		W.Sight = FVector(0.f, 7.51f, 19.24f);                  // (the notch's bottom: 1.15 cm above the sight blade's middle, 18.09 in weapons.json)
		W.SightFront = FVector(0.f, 45.04f, 17.42f);
		W.GripL = FVector(0.f, 36.86f, 5.23f);
		W.MagWell = FVector(0.f, 17.69f, 6.3f);
		W.Eject = FVector(3.62f, 12.73f, 8.98f);
		W.AnimIdle = TEXT("/Game/Characters/Mannequins/Anims/Rifle/MF_Rifle_Idle_ADS.MF_Rifle_Idle_ADS");
		W.AnimEquip = TEXT("/Game/Characters/Mannequins/Anims/Rifle/MM_Rifle_Equip.MM_Rifle_Equip");
		W.AnimReload = TEXT("/Game/Characters/Mannequins/Anims/Rifle/MM_Rifle_Reload.MM_Rifle_Reload");
		W.AnimDry = TEXT("/Game/Characters/Mannequins/Anims/Rifle/MM_Rifle_DryFire.MM_Rifle_DryFire");
		// the right-hand socket in MF_Rifle_Idle_ADS at its first frame, as the engine evaluates the animation on the arms' mesh (tools/boarding.py run --scenario fps checks and prints them)
		W.PoseGripLoc = FVector(-15.87, 14.29, 140.79);
		W.PoseGripX = FVector(0.9423, 0.1942, -0.2726);
		W.PoseGripY = FVector(-0.1400, 0.9685, 0.2060);
		W.PoseGripZ = FVector(0.3040, -0.1559, 0.9398);
		W.EquipAnimS = 1.67f;
		W.ReloadAnimS = 2.2f;
		W.DryAnimS = 0.8f;
		W.GripLHand = FVector(3.0, 28.0, 3.0);            // under the hand-guard's rear half, a little to its left: the fingers wrap its left side
		W.ShotSound = TEXT("/Game/ASTRA/Audio/SW_Rifle_Shot.SW_Rifle_Shot");
		W.DrySound = TEXT("/Game/ASTRA/Audio/SW_Gun_Dry.SW_Gun_Dry");
		W.ReloadSound = TEXT("/Game/ASTRA/Audio/SW_Rifle_Reload.SW_Rifle_Reload");
		W.DrawSound = TEXT("/Game/ASTRA/Audio/SW_Gun_Draw.SW_Gun_Draw");
		return W;
	}

	FAstraWeaponDef WpnMakePistol()
	{
		FAstraWeaponDef W;
		W.Id = EAstraWeapon::Pistol;
		W.Key = TEXT("pistol");
		W.Name = TEXT("M27S");
		W.Role = TEXT("sidearm");
		W.bAuto = false;
		W.Rpm = 400.f;
		W.Mag = 15;
		W.SpareMags = 3;
		W.ReloadS = 1.7f;
		W.ReloadEmptyS = 2.1f;
		W.DrawS = 0.6f;
		W.HolsterS = 0.35f;
		W.Damage = 30.f;
		W.HeadMul = 2.4f;
		W.LimbMul = 0.75f;
		W.FullRangeCm = 1500.f;
		W.FarRangeCm = 4500.f;
		W.FarMul = 0.65f;
		W.HipSpreadDeg = 1.2f;
		W.AdsSpreadDeg = 0.1f;
		W.BloomPerShotDeg = 0.5f;
		W.BloomMaxDeg = 2.5f;
		W.BloomRecoverDegS = 5.f;
		W.KickPitchDeg = 1.1f;
		W.KickYawDeg = 0.4f;
		W.AdsFov = 72.f;
		W.AdsTimeS = 0.12f;
		W.MoveMul = 0.95f;
		W.AdsMoveMul = 0.75f;
		W.MeshPath = TEXT("/Game/ASTRA/Weapons/SM_M27S.SM_M27S");
		W.MagPath = TEXT("");
		W.Muzzle = FVector(0.f, 17.69f, 6.16f);
		W.Sight = FVector(0.f, -1.23f, 8.35f);                  // (the front post's tip is 0.26 above the rear blade's middle, 8.09 in weapons.json)
		W.SightFront = FVector(0.f, 17.24f, 8.09f);
		W.GripL = FVector(0.f, 4.72f, -4.11f);
		W.MagWell = FVector(0.f, -1.03f, 3.28f);
		W.Eject = FVector(-1.15f, 5.13f, 6.36f);
		W.AnimIdle = TEXT("/Game/Characters/Mannequins/Anims/Pistol/MF_Pistol_Idle_ADS.MF_Pistol_Idle_ADS");
		W.AnimEquip = TEXT("/Game/Characters/Mannequins/Anims/Pistol/MM_Pistol_Equip.MM_Pistol_Equip");
		W.AnimReload = TEXT("/Game/Characters/Mannequins/Anims/Pistol/MM_Pistol_Reload.MM_Pistol_Reload");
		W.AnimDry = TEXT("/Game/Characters/Mannequins/Anims/Pistol/MM_Pistol_DryFire.MM_Pistol_DryFire");
		// MF_Pistol_Idle_ADS, first frame
		W.PoseGripLoc = FVector(-13.10, 42.27, 149.68);
		W.PoseGripX = FVector(0.9979, 0.0634, -0.0106);
		W.PoseGripY = FVector(-0.0612, 0.9877, 0.1438);
		W.PoseGripZ = FVector(0.0196, -0.1428, 0.9896);
		W.EquipAnimS = 1.4f;
		W.ReloadAnimS = 2.0f;
		W.DryAnimS = 0.8f;
		W.GripLHand = FVector(0.0, 4.72, -4.11);
		W.ShoulderAdsR = FVector(-22.0, 3.0, -28.0);
		W.ShoulderAdsL = FVector(2.0, -24.0, -35.0);
		W.HipPlace = FVector(48.0, 12.0, -6.0);
		W.HipTurn = FRotator(0.0, -6.0, 0.0);
		W.AdsPlace = FVector(34.0, 0.0, 0.0);
		W.LowPlace = FVector(46.0, 20.0, -16.0);
		W.LowTurn = FRotator(25.0, -20.0, -10.0);
		W.ShotSound = TEXT("/Game/ASTRA/Audio/SW_Pistol_Shot.SW_Pistol_Shot");
		W.DrySound = TEXT("/Game/ASTRA/Audio/SW_Gun_Dry.SW_Gun_Dry");
		W.ReloadSound = TEXT("/Game/ASTRA/Audio/SW_Pistol_Reload.SW_Pistol_Reload");
		W.DrawSound = TEXT("/Game/ASTRA/Audio/SW_Gun_Draw.SW_Gun_Draw");
		return W;
	}
}

float FAstraWeaponDef::DamageAt(float DistCm) const
{
	if (DistCm <= FullRangeCm)
	{
		return Damage;
	}
	if (DistCm <= FarRangeCm)
	{
		return Damage * FMath::Lerp(1.f, FarMul, (DistCm - FullRangeCm) / FMath::Max(1.f, FarRangeCm - FullRangeCm));
	}
	return Damage * FarMul * FMath::Clamp(1.f - (DistCm - FarRangeCm) / FarRangeCm, 0.5f, 1.f);
}

namespace AstraWeapons
{
	const FAstraWeaponDef& Get(EAstraWeapon Id)
	{
		static const FAstraWeaponDef Rifle = WpnMakeRifle();
		static const FAstraWeaponDef Pistol = WpnMakePistol();
		static const FAstraWeaponDef None;
		return Id == EAstraWeapon::Rifle ? Rifle : (Id == EAstraWeapon::Pistol ? Pistol : None);
	}

	EAstraWeapon FromKey(const FString& Key)
	{
		const FString K = Key.ToLower();
		if (K == TEXT("rifle") || K == TEXT("ar-181") || K == TEXT("ar181") || K == TEXT("1"))
		{
			return EAstraWeapon::Rifle;
		}
		if (K == TEXT("pistol") || K == TEXT("sidearm") || K == TEXT("m27s") || K == TEXT("2"))
		{
			return EAstraWeapon::Pistol;
		}
		return EAstraWeapon::None;
	}
}
