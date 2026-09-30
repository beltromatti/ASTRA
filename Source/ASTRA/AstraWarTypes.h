// ASTRA — the war's data types: the physical model of a warship (shield sectors, armour plates, structure by section,
// subsystems, weapon mounts with fields of fire), the class table those are built from, and the deaths the visuals read.
// Plain structs (no UObjects): they live inside FAstraBattleShip and are filled by AstraWarClasses.cpp / AstraWarDamage.cpp.
// See docs/GUERRA.md, "F2.1 Danni fisici".

#pragma once

#include "CoreMinimal.h"
#include "AstraWarStats.h"

namespace AstraWar
{
	const double OneKm = 1000.0;
	const double WarKm = OneKm;                 // (the war files' own short name, brought in with a using-declaration: no clash in a unity build)

	// the six faces of a hull (shield sectors and armour plates) — the same order as AstraFacingOf()
	constexpr int32 NumFacings = 6;
	enum EFacing : int32 { Bow = 0, Stern = 1, Port = 2, Starboard = 3, Dorsal = 4, Ventral = 5 };
	// the three lengthwise sections of a hull
	constexpr int32 NumSections = 3;
	enum ESection : int32 { SecBow = 0, SecMid = 1, SecStern = 2 };
	// the subsystems, each living in one section (point defence is spread over the whole hull)
	constexpr int32 NumSystems = 6;
	enum ESystem : int32 { SysEngines = 0, SysSensors = 1, SysHangar = 2, SysBridge = 3, SysReactor = 4, SysPointDefence = 5 };
	constexpr uint8 EverySection = 255;

	inline const TCHAR* FacingName(int32 F)
	{
		static const TCHAR* const N[NumFacings] = {TEXT("bow"), TEXT("stern"), TEXT("port"), TEXT("starboard"), TEXT("dorsal"), TEXT("ventral")};
		return N[FMath::Clamp(F, 0, NumFacings - 1)];
	}
	inline const TCHAR* SectionName(int32 S)
	{
		static const TCHAR* const N[NumSections] = {TEXT("bow"), TEXT("mid"), TEXT("stern")};
		return N[FMath::Clamp(S, 0, NumSections - 1)];
	}
	inline const TCHAR* SystemName(int32 S)
	{
		static const TCHAR* const N[NumSystems] = {TEXT("engines"), TEXT("sensors"), TEXT("hangar"), TEXT("bridge"), TEXT("reactor"), TEXT("point defence")};
		return N[FMath::Clamp(S, 0, NumSystems - 1)];
	}
	/** The unit vector of a facing in the ship's frame (X forward, Y starboard, Z up). */
	inline FVector FacingVector(int32 F)
	{
		switch (F)
		{
		case Bow: return FVector(1, 0, 0);
		case Stern: return FVector(-1, 0, 0);
		case Port: return FVector(0, -1, 0);
		case Starboard: return FVector(0, 1, 0);
		case Dorsal: return FVector(0, 0, 1);
		default: return FVector(0, 0, -1);
		}
	}
	/** The lengthwise section a hit lands on, from the outward normal at the point it strikes (ship frame). */
	inline int32 SectionOfNormal(const FVector& N)
	{
		return N.X > 0.33 ? SecBow : (N.X < -0.33 ? SecStern : SecMid);
	}
	/** The tuning table of the war (astra.war.tune <name> <value>: from the console or the bench's --exec): a change bumps
	 *  the version, and every FTuneVar reads its value again. For A/B runs without a build. */
	ASTRA_API int32& TuneVersion();
	ASTRA_API bool TuneLookup(const TCHAR* Name, float& Out);
	struct FTuneVar
	{
		const TCHAR* Name;
		float Default;
		float Value;
		int32 Version = -1;
		FTuneVar(const TCHAR* InName, float InDefault) : Name(InName), Default(InDefault), Value(InDefault) {}
		float Get()
		{
			if (Version != TuneVersion())
			{
				Version = TuneVersion();
				Value = Default;
				TuneLookup(Name, Value);
			}
			return Value;
		}
	};
	/** Where a ray travelling along Dir enters a sphere (Centre, R) when Closest, a point on the ray, is where it comes nearest
	 *  to the centre. */
	inline FVector SphereEntry(const FVector& Centre, double R, const FVector& Closest, const FVector& Dir)
	{
		return Closest - Dir * FMath::Sqrt(FMath::Max(0.0, R * R - FVector::DistSquared(Closest, Centre)));
	}
}

/** A weapon mount: a fixed field of fire (a cone around Dir in the ship's frame), where it sits, how it is doing. */
enum class EAstraMountKind : uint8
{
	Rail,
	Laser
};

struct FAstraMount
{
	EAstraMountKind Kind = EAstraMountKind::Rail;
	FVector Dir = FVector(1, 0, 0);     // ship frame: the middle of its field of fire
	float ArcCos = 0.f;                 // cos of the half-angle of the field: it bears on a target when dot(Dir, aim) >= ArcCos
	uint8 Section = AstraWar::SecMid;   // where it sits: hits on that section wear it down
	uint8 Barrels = 1;                  // slugs a volley (rails); beams a burst (lasers)
	float Cd = 1.f;                     // multiplier on the ship's cooldown for this weapon (1: the ship's own cadence)
	float T = 0.f;                      // cooldown left
	float Health = 1.f;                 // 0 = destroyed (below 0.2 it will not fire)
	bool CanBear(const FVector& LocalAim) const { return Health >= 0.2f && FVector::DotProduct(Dir, LocalAim) >= ArcCos; }
};

/** What a warship is made of, as damage sees it. Craft and decoys have none (bModel false): hull and shield lumps. */
struct FAstraShipDamage
{
	bool bModel = false;
	// --- shields: six sectors, each with its own value; the allocation says how the generator's capacity is shared out.
	float Sector[AstraWar::NumFacings] = {};
	float SectorMax[AstraWar::NumFacings] = {};
	float SectorFlash[AstraWar::NumFacings] = {};   // 1 at a hit, fading (the visuals' hexagons)
	float Alloc[AstraWar::NumFacings] = {};         // wanted shares of the capacity (sum 1)
	float Base[AstraWar::NumFacings] = {};          // the balanced allocation of the class
	float ShieldScale = 1.f;                        // the class's sector capacity over the old single bubble (regeneration follows it)
	int32 FocusFacing = -1;                         // the facing the allocation is reinforcing (-1: balanced)
	float AutoFocusT = 0.f;                         // the AI's shield officer looks at the threat again in this many seconds
	float Pool = 0.f;                               // the capacity to share out (sum of the sector maxima)
	float Buffer = 0.f;                             // energy in transit between sectors after a reallocation
	// --- structure by lengthwise section, with the armour plates over each face of each section
	float Structure[AstraWar::NumSections] = {};
	float StructureMax[AstraWar::NumSections] = {};
	float Plate[AstraWar::NumSections][AstraWar::NumFacings] = {};
	float PlateMax[AstraWar::NumSections][AstraWar::NumFacings] = {};
	float GuttedT[AstraWar::NumSections] = {-1.f, -1.f, -1.f};   // seconds since the section reached zero (-1: it has not)
	float Burn[AstraWar::NumSections] = {};                       // seconds of fire left in the section
	float Breach[AstraWar::NumSections] = {};                     // seconds of venting left
	// --- subsystems (1 = sound, 0 = gone)
	float Sys[AstraWar::NumSystems] = {1, 1, 1, 1, 1, 1};
	uint8 SysSection[AstraWar::NumSystems] = {AstraWar::SecStern, AstraWar::SecBow, AstraWar::SecMid, AstraWar::SecMid, AstraWar::SecMid, AstraWar::EverySection};
	// --- the last blow (for the visuals: where to flash the shield)
	FVector LastHitLocal = FVector::ZeroVector;    // unit vector, ship frame, out of the ship
	float LastHitAge = 1e9f;
	uint8 LastHitFacing = 0;
	// --- how the ship is going
	bool bBreakingUp = false;                      // a gutted section is letting go: seconds left in BreakupT
	float BreakupT = 0.f;
	uint8 BreakSection = 0;
	bool bReactorCritical = false;                 // the reactor is hurt and could go
	float ThinkDelay = 0.f;                        // the bridge's reaction lag (s) from the damage to it
	float HullLastReported = 1.f;
	float Repair = 0.f;                            // crew repair of subsystems per second (the Aquila's damage control)
};

/** A hull's death, for the visuals (VFX, the breakup of the mesh) and the books: the lead reads them with
 *  ConsumeDeathEvents(). Where the ship broke and along which axis, and how fast the pieces part. */
struct FAstraDeathEvent
{
	float Time = 0.f;
	int32 ShipId = -1;
	FString ContactId, Name, Class;
	EAstraFate How = EAstraFate::Destroyed;
	uint8 Section = 0;                       // Breakup: the section that let go (0 bow, 1 mid, 2 stern)
	FVector Pos = FVector::ZeroVector;       // system frame, m
	FVector Vel = FVector::ZeroVector;
	FQuat Att = FQuat::Identity;
	FVector BreakAxis = FVector::ZeroVector; // Breakup: the ship's long axis (the cut is a plane across it), system frame
	FVector BreakPoint = FVector::ZeroVector;// Breakup: where the plane crosses the axis, system frame
	float BreakSpeed = 0.f;                  // Breakup: relative speed of the two pieces along the axis (m/s)
	float Radius = 100.f;
	bool bAstra = false;
};
