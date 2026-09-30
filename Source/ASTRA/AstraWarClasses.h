// ASTRA — the ship class table of the war: what each hull is made of (structure by section, armour plates, shield sectors,
// systems, weapon mounts with their fields of fire) and how it handles. Built in (AstraWarClassesData.inl, regenerated from
// data/war/classes.json with `tools/war.py embed`), and read again from data/war/classes.json at startup when the file
// exists, so the numbers can be tuned without a build. See docs/GUERRA.md.

#pragma once

#include "CoreMinimal.h"
#include "AstraWarTypes.h"

namespace AstraWar
{
	struct FMountDef
	{
		EAstraMountKind Kind = EAstraMountKind::Rail;
		FVector Dir = FVector(1, 0, 0);
		float ArcDeg = 120.f;
		uint8 Section = SecMid;
		uint8 Barrels = 1;
	};

	struct FShipClass
	{
		FName Key;
		FString Label;
		FString Mesh;                                   // the mesh the game draws it with (empty: none, headless)
		float Radius = 150.f, Hull = 1000.f, Shield = 400.f, ShieldRegen = 4.f;
		float Accel = 15.f, TurnDeg = 3.f, Cruise = 300.f, SensorKm = 45.f;
		float SectionShare[NumSections] = {0.3f, 0.4f, 0.3f};
		float ArmourFrac = 0.25f;
		float FacingArmour[NumFacings] = {0.22f, 0.12f, 0.2f, 0.2f, 0.13f, 0.13f};
		float ShieldAlloc[NumFacings] = {0.24f, 0.11f, 0.17f, 0.17f, 0.155f, 0.155f};
		float ShieldScale = 1.6f;                       // sector capacity over the old single bubble: no facing has it all
		int32 RailSlugs = 2;
		float RailDamage = 55.f, RailCd = 8.f, RailRange = 8000.f;
		int32 Missiles = 12;
		float MissileCd = 30.f, MissileRange = 25000.f;
		float LaserDamage = 18.f, LaserCd = 5.f, LaserRange = 4000.f;
		int32 PDChannels = 2;
		float PDRange = 2000.f;
		uint8 SysSection[NumSystems] = {SecStern, SecBow, SecMid, SecMid, SecMid, EverySection};
		float RangeMinKm = 4.f, RangeMaxKm = 6.5f;      // the range its armament likes
		TArray<FMountDef> Mounts;
	};

	/** The class for a key ("praetorian"); a generic warship if there is none. */
	const FShipClass& GetClass(FName Key);
	const FShipClass* FindClass(FName Key);
	/** The class key of a ship from what it says about itself (its class text and mesh); NAME_None for craft and unknowns. */
	FName KeyFor(const FString& ClassText, const FString& Mesh);
	/** Read the table (once): the built-in one, then data/war/classes.json over it. */
	void EnsureClassesLoaded();
	/** Every class key, for the scenarios and the console. */
	void ClassKeys(TArray<FName>& Out);
}
