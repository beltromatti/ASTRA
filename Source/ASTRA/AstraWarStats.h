// ASTRA — what the war bench measures (docs/GUERRA.md, "Risultati del banco"): damage by type and facing, losses by cause,
// focus of fire, retreats, and what the simulation costs per tick. Plain counters; the battle fills them, the commandlet
// writes them into the record (final.stats) and tools/war.py reads them.

#pragma once

#include "CoreMinimal.h"
#include "Dom/JsonObject.h"

/** What struck what. The damage type follows from it (kinetic, energy, explosive). */
enum class EAstraHitKind : uint8
{
	Rail,           // railgun slug (kinetic)
	Laser,          // a capital ship's laser battery (energy)
	PointDefence,   // a point-defence beam (energy)
	Missile,        // guided missile (explosive)
	Torpedo,        // bomber torpedo (explosive)
	Rocket,         // strike-fighter rocket (explosive)
	Cannon,         // a fighter's cannon (kinetic)
	Internal,       // fires, collisions
	Num
};

enum class EAstraDamageType : uint8
{
	Kinetic,
	Energy,
	Explosive,
	Num
};

inline EAstraDamageType AstraDamageTypeOf(EAstraHitKind K)
{
	switch (K)
	{
	case EAstraHitKind::Laser:
	case EAstraHitKind::PointDefence:
		return EAstraDamageType::Energy;
	case EAstraHitKind::Missile:
	case EAstraHitKind::Torpedo:
	case EAstraHitKind::Rocket:
		return EAstraDamageType::Explosive;
	default:
		return EAstraDamageType::Kinetic;
	}
}

/** The six faces of a hull in the ship's own frame: bow (+X), stern (-X), port (-Y), starboard (+Y), dorsal (+Z), ventral (-Z).
 *  The face a direction (pointing out of the ship) falls on: the dominant axis. */
inline int32 AstraFacingOf(const FVector& LocalOut)
{
	const FVector A = LocalOut.GetAbs();
	if (A.X >= A.Y && A.X >= A.Z)
	{
		return LocalOut.X >= 0.0 ? 0 : 1;
	}
	if (A.Y >= A.Z)
	{
		return LocalOut.Y >= 0.0 ? 3 : 2;
	}
	return LocalOut.Z >= 0.0 ? 4 : 5;
}

/** How a warship's story ended. */
enum class EAstraFate : uint8
{
	Alive,
	ReactorBreach,   // the reactor went: a blast that takes the whole ship
	Breakup,         // a gutted section let go: the hull broke apart
	Disabled,        // dead in the water, no power, a derelict (boardable)
	Destroyed,       // any other death (structure at zero)
	Withdrew,        // left the theatre alive
	Num
};

/** Why a craft was lost (its killer), or that it came home. */
enum class EAstraCraftFate : uint8
{
	PointDefence,
	CraftGuns,
	Missile,        // missiles, torpedoes, rockets
	Other,
	Num
};

struct FAstraWarStats
{
	// --- damage dealt to warships (craft not counted), by damage type and by the facing it landed on
	double DmgIn[3] = {0, 0, 0};                 // everything that struck the hull sphere, by type (kinetic, energy, explosive)
	double DmgShield[3] = {0, 0, 0};             // the part the shields took
	double DmgPlate[3] = {0, 0, 0};              // the part the armour took
	double DmgStructure[3] = {0, 0, 0};          // the part that reached the structure
	double DmgFacing[3][6] = {};                 // by type x facing (bow, stern, port, starboard, dorsal, ventral) of the target
	int32 Hits[3] = {0, 0, 0};
	int32 SectorsCollapsed = 0;                  // a shield sector taken down to nothing by a hit
	// --- craft
	int32 CraftLaunched[2] = {0, 0};             // by side (0 ASTRA, 1 Mandate)
	int32 CraftRecovered[2] = {0, 0};
	int32 CraftLost[2][4] = {};                  // side x EAstraCraftFate
	// --- warships (side x fate)
	int32 ShipFate[2][6] = {};
	int32 LostWhileRetreating[2] = {0, 0};       // died after breaking off
	// --- missiles
	int32 MissilesFired[2] = {0, 0};
	int32 MissilesShot[2] = {0, 0};              // by point defence or fighters
	int32 MissilesDecoyed[2] = {0, 0};
	// --- focus of fire: in 10 s windows, the share of a side's damage on its most-hit target
	double FocusSum[2] = {0, 0};
	int32 FocusWindows[2] = {0, 0};
	double WinDmg[2][48] = {};                   // per window: damage by target slot
	int32 WinTarget[2][48] = {};
	int32 WinCount[2] = {0, 0};
	double WinTotal[2] = {0, 0};
	float WinStart = 0.f;
	// --- what the simulation costs
	double TickMsSum = 0.0, TickMsMax = 0.0;
	int32 Ticks = 0;
	TArray<float> TickMsSamples;                 // for the percentiles (capped)
	// where the tick's time goes: knowledge+grid, groups, squadrons+scenario, capital ships (AI, weapons, damage), craft, projectiles+effects
	static constexpr int32 NumPhases = 6;
	double PhaseNow[NumPhases] = {};             // this tick (reset at its start)
	double PhaseSum[NumPhases] = {};
	double PhaseMax[NumPhases] = {};
	int32 PeakShips = 0, PeakCraft = 0, PeakProjectiles = 0;

	// --- the fight log (BATTAGLIA-3): how continuous the fire is, how accurate it is at each range, who kills whom, who breaks off and when.
	// The weapons that hurt a warship: a railgun slug, a capital ship's laser, a missile, a bomber's torpedo, a strike fighter's rocket, a craft's cannon.
	enum EWeapon : int32 { WRail = 0, WLaser, WMissile, WTorpedo, WRocket, WCannon, NumWeapons };
	static constexpr int32 NumRangeBuckets = 10;          // range of the shot, km: 0-2, 2-5, 5-10, 10-15, 15-20, 20-30, 30-40, 40-50, 50-70, 70+
	static int32 RangeBucket(double RangeM);
	static int32 WeaponOf(EAstraHitKind K);
	int32 AccShots[2][NumWeapons][NumRangeBuckets] = {};  // by the shooter's side: shots fired at a warship (rails, lasers, torpedoes, rockets: each slug or beam; missiles: each one launched)
	int32 AccHits[2][NumWeapons][NumRangeBuckets] = {};   // the ones that struck a warship (counted at the range they were fired from)
	double AccDamage[2][NumWeapons][NumRangeBuckets] = {};// what those hits carried before the shields (the blow's own damage)
	int32 FriendlyHits[2] = {0, 0};                        // a slug that struck a ship of its own side (it was in the line of fire)
	TArray<uint8> FireBins;                               // one byte per second of battle: 1 ASTRA warship fired, 2 Mandate warship fired, 4 a blow struck an ASTRA warship, 8 a blow struck a Mandate warship
	void NoteFire(float Time, int32 SideIdx, int32 Weapon, double RangeM, bool bCapitalShooter);
	void NoteHit(float Time, int32 ShooterSide, int32 VictimSide, int32 Weapon, double FireRangeM, float Damage);
	struct FKill
	{
		float T = 0.f;
		int8 VictimSide = -1;                             // 0 ASTRA, 1 Mandate
		int8 VictimTier = 0;
		FName VictimClass;
		bool bVictimCraft = false;
		int8 KillerSide = -1;
		FName KillerClass;                                // a warship's class, or the craft's kind (fighter, bomber, drone)
		bool bKillerAquila = false;
		bool bKillerCraft = false;
		bool bFleeing = false;                            // it was breaking off when it died
		uint8 Weapon = 0;                                 // the blow that finished it
		uint8 How = 0;                                    // EAstraFate
		float KillRangeKm = -1.f;                         // from the killer, when known
	};
	TArray<FKill> Kills;
	struct FRetreat
	{
		float T = 0.f;
		int8 Side = -1;
		FString What;                                     // "group Vanguard: it is being beaten" / "ship T-31: too hurt"
		int32 Ships = 0;
	};
	TArray<FRetreat> Retreats;
	void NoteKill(const FKill& K);
	void NoteRetreat(float Time, int32 SideIdx, const FString& What, int32 Ships);

	void NoteTick(double Ms)
	{
		for (int32 p = 0; p < NumPhases; ++p)
		{
			PhaseSum[p] += PhaseNow[p];
			PhaseMax[p] = FMath::Max(PhaseMax[p], PhaseNow[p]);
		}
		TickMsSum += Ms;
		TickMsMax = FMath::Max(TickMsMax, Ms);
		++Ticks;
		if (TickMsSamples.Num() < 20000)
		{
			TickMsSamples.Add((float)Ms);
		}
	}
	/** A hit on a warship: window bookkeeping for the focus-of-fire index. */
	void NoteFocus(int32 SideIdx, int32 TargetId, double Damage);
	void CloseWindow(int32 SideIdx);
	TSharedRef<FJsonObject> ToJson() const;
};
