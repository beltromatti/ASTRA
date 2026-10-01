// ASTRA — the physical damage of a warship (docs/GUERRA.md, F2.1).
//
//   a blow lands on a face of the hull (from where it strikes, in the ship's own frame) and a lengthwise section:
//     1. the SHIELD SECTOR of that face takes what its type lets it take (energy: nearly all; kinetic: less, and a heavy
//        slug bleeds through; explosive: least). Sectors regenerate, and the generator can shift its capacity between
//        them (a reallocation moves energy through a buffer at a finite rate);
//     2. the ARMOUR PLATE over that face of that section takes a share of what got through (a heavy blow ignores part of
//        it), wearing away;
//     3. the STRUCTURE of the section takes the rest, spilling over to its neighbours once it is gone; a section at zero
//        is gutted: what lived in it is lost, and the hull may break apart there;
//     4. the SYSTEMS and WEAPON MOUNTS in that section wear down with the damage (engines, sensors, hangar, bridge,
//        reactor, point defence; each mount has its own field of fire), and the section may burn or vent.
//   A ship dies by its reactor (a blast), by breaking up along a gutted section, or is left DISABLED: no power, drifting,
//   a derelict. What the visuals and the crew may read of it (fog of war applied) is GetDamageView / ConsumeDeathEvents.

#include "AstraBattleSubsystem.h"
#include "AstraWarClasses.h"
#include "AstraWarFX.h"
#include "ASTRA.h"
#include "AstraShipSubsystem.h"
#include "Engine/World.h"
#include "Kismet/GameplayStatics.h"
#include "Sound/SoundBase.h"

namespace
{
	/** How each kind of blow meets shields, plates and structure. */
	struct FWarHitProfile
	{
		float ShieldEff;       // the share of the blow the shield can take (before power)
		float ArmourResist;    // the share of what reaches the plating that the plate takes
		float ArmourPen;       // a blow heavier than this ignores the armour for the excess (0: none)
		float Splash;          // the share of the structure damage that spills onto the neighbouring sections
		float SystemMul;       // how hard it is on what lives inside
		float FireK, BreachK;  // how likely it is to set the section burning / open it to space
	};

	FWarHitProfile WarProfileOf(EAstraDamageType T, float Damage)
	{
		switch (T)
		{
		case EAstraDamageType::Energy:
			return {0.95f, 0.30f, 0.f, 0.f, 0.8f, 0.55f, 0.20f};
		case EAstraDamageType::Explosive:
			// the warhead goes off on the shield's edge and inside the plating: the least stopped, and the most spread
			return {0.75f * (1.f - 0.35f * FMath::Clamp((Damage - 60.f) / 200.f, 0.f, 1.f)), 0.40f, 100.f, 0.30f, 1.4f, 0.75f, 0.60f};
		default:
			// a slug: shields stop part of it, and a heavy one bleeds through
			return {0.85f * (1.f - 0.5f * FMath::Clamp((Damage - 30.f) / 100.f, 0.f, 1.f)), 0.55f, 60.f, 0.f, 1.0f, 0.20f, 0.50f};
		}
	}

	/** How exposed each system is on each face of the hull [system][facing]: the engines are seen from astern, the sensors
	 *  from ahead and above, the reactor is deep inside. */
	const float WarSystemExposure[AstraWar::NumSystems][AstraWar::NumFacings] = {
		//  bow    stern  port   stbd   dors   vent
		{0.30f, 1.00f, 0.50f, 0.50f, 0.60f, 0.60f},   // engines
		{1.00f, 0.30f, 0.50f, 0.50f, 0.80f, 0.40f},   // sensors
		{0.90f, 0.40f, 0.80f, 0.80f, 0.50f, 0.50f},   // hangar
		{0.70f, 0.30f, 0.60f, 0.60f, 1.00f, 0.30f},   // bridge
		{0.60f, 0.90f, 0.50f, 0.50f, 0.50f, 0.50f},   // reactor
		{0.60f, 0.60f, 0.60f, 0.60f, 0.60f, 0.60f}};  // point defence

	/** How readily each system breaks with the damage its section takes: the reactor sits deep inside, the sensors and the
	 *  mounts sit on the skin. */
	const float WarSystemFragility[AstraWar::NumSystems] = {2.4f, 3.0f, 2.2f, 1.6f, 0.9f, 2.0f};

	int32 WarOpposite(int32 F) { return F ^ 1; }
}

// ---------------------------------------------------------------------------------------------- where a shot strikes
bool UAstraBattleSubsystem::HullSweep(const FAstraBattleShip& T, const FVector& P0, const FVector& P1, FVector& OutEntry) const
{
	// the bounding sphere first (what is far from the path costs one closest-point test)
	const FVector Closest = FMath::ClosestPointOnSegment(T.Pos, P0, P1);
	const double Bound = T.Radius * (T.Box.Valid() ? 1.05 : 1.0) + 1.0;
	if (FVector::DistSquared(Closest, T.Pos) > Bound * Bound)
	{
		return false;
	}
	if (!T.Box.Valid())
	{
		// no measures (craft, decoys): a sphere of Radius, struck where the path enters it
		const FVector Dir = (P1 - P0).GetSafeNormal();
		FVector Entry = AstraWar::SphereEntry(T.Pos, T.Radius, Closest, Dir);
		if (FVector::DotProduct(Entry - P0, Dir) < 0.0)
		{
			Entry = P0;                                        // it started inside
		}
		OutEntry = Entry;
		return true;
	}
	// the box, in the ship's frame (the slab test: the last entry against the first exit on the three axes)
	const FQuat Inv = T.Att.Inverse();
	const FVector Off(T.Box.Mid, 0.0, 0.0);
	const FVector L0 = Inv.RotateVector(P0 - T.Pos) - Off;
	const FVector L1 = Inv.RotateVector(P1 - T.Pos) - Off;
	const FVector D = L1 - L0;
	const double H[3] = {(double)T.Box.Hx, (double)T.Box.Hy, (double)T.Box.Hz};
	double T0 = 0.0, T1 = 1.0;
	for (int32 a = 0; a < 3; ++a)
	{
		const double O = L0[a], Dd = D[a];
		if (FMath::Abs(Dd) < 1e-9)
		{
			if (FMath::Abs(O) > H[a])
			{
				return false;                                  // parallel to the slab and outside it
			}
			continue;
		}
		double Ta = (-H[a] - O) / Dd, Tb = (H[a] - O) / Dd;
		if (Ta > Tb)
		{
			Swap(Ta, Tb);
		}
		T0 = FMath::Max(T0, Ta);
		T1 = FMath::Min(T1, Tb);
		if (T0 > T1)
		{
			return false;
		}
	}
	OutEntry = P0 + (P1 - P0) * T0;                            // (T0 = 0: it started inside the hull)
	return true;
}

FVector UAstraBattleSubsystem::HullRandomEntry(const FVector& From, const FAstraBattleShip& T) const
{
	if (T.Box.Valid())
	{
		const FVector LP(FMath::FRandRange(-0.9f, 0.9f) * T.Box.Hx, FMath::FRandRange(-0.9f, 0.9f) * T.Box.Hy, FMath::FRandRange(-0.9f, 0.9f) * T.Box.Hz);
		const FVector Aim = T.Pos + T.Att.RotateVector(LP + FVector(T.Box.Mid, 0.0, 0.0));
		const FVector Dir = (Aim - From).GetSafeNormal();
		FVector Entry;
		if (HullSweep(T, From, Aim + Dir * (double)T.Radius * 2.0, Entry))
		{
			return Entry;
		}
		return Aim;
	}
	const FVector Dir = (T.Pos - From).GetSafeNormal();
	const FVector Off = FVector::VectorPlaneProject(FMath::VRand(), Dir).GetSafeNormal() * T.Radius * 0.9 * FMath::Sqrt(FMath::FRand());
	return AstraWar::SphereEntry(T.Pos, T.Radius, T.Pos + Off, Dir);
}

float UAstraBattleSubsystem::BreakX(const FAstraBattleShip& S, int32 Section) const
{
	if (!S.Box.Valid() || (S.Box.CutBow == 0.f && S.Box.CutStern == 0.f))
	{
		return (Section == AstraWar::SecBow ? 1.f : (Section == AstraWar::SecStern ? -1.f : 0.f)) * 0.33f * S.Radius;   // (no cuts known: a third of the way)
	}
	return Section == AstraWar::SecBow ? S.Box.CutBow : (Section == AstraWar::SecStern ? S.Box.CutStern : 0.5f * (S.Box.CutBow + S.Box.CutStern));
}

// ---------------------------------------------------------------------------------------------- building a ship's model
void UAstraBattleSubsystem::InitShipModel(FAstraBattleShip& S)
{
	const FName Key = AstraWar::KeyFor(S.Class, S.Mesh);
	const AstraWar::FShipClass* C = Key.IsNone() ? nullptr : AstraWar::FindClass(Key);
	if (!C)
	{
		return;                                   // craft, decoys, anything with no class: hull and shield stay lumps
	}
	S.ClassKey = Key;
	S.Radius = C->Radius;                      // the class's measures, not the caller's guess: the game draws the mesh at true scale
	S.Box = C->Box;
	S.SizeTier = (uint8)FMath::Clamp(C->Tier, 0, 3);
	S.MaxAccel = C->Accel;
	S.MaxTurnDeg = C->TurnDeg;
	S.SensorKm = C->SensorKm;
	S.RailSlugs = C->RailSlugs;
	S.RailDamage = C->RailDamage;
	S.RailCd = C->RailCd;
	S.RailRange = C->RailRange;
	S.Missiles = C->Missiles;
	S.MissileCd = C->MissileCd;
	S.MissileRange = C->MissileRange;
	S.LaserDamage = C->LaserDamage;
	S.LaserCd = C->LaserCd;
	S.LaserRange = C->LaserRange;
	S.PDChannels = C->PDChannels;
	S.PDRange = C->PDRange;
	S.ShieldRegen = C->ShieldRegen;
	S.Mounts.Reset();
	for (const AstraWar::FMountDef& D : C->Mounts)
	{
		FAstraMount M;
		M.Kind = D.Kind;
		M.Dir = D.Dir;
		M.ArcCos = FMath::Cos(FMath::DegreesToRadians(D.ArcDeg));
		M.Section = D.Section;
		M.Barrels = D.Barrels;
		M.T = FMath::FRand() * FMath::Max(1.f, D.Kind == EAstraMountKind::Rail ? C->RailCd : C->LaserCd);   // the volleys do not all start together
		S.Mounts.Add(M);
	}
	BuildDurability(S, S.HullMax, S.ShieldMax);
	// what it is worth in a fight: its firepower at mid range and what it takes to put it out
	S.CombatValue = (float)(0.5 * ShipDps(S, 5000.0) / 40.0 + 0.5 * (S.HullMax + S.ShieldMax) / 6000.0);
}

void UAstraBattleSubsystem::BuildDurability(FAstraBattleShip& S, float Hull, float Shield)
{
	const AstraWar::FShipClass* C = S.ClassKey.IsNone() ? nullptr : AstraWar::FindClass(S.ClassKey);
	if (!C)
	{
		S.Dmg.bModel = false;
		S.Hull = S.HullMax = Hull;
		S.Shield = S.ShieldMax = Shield;
		return;
	}
	static AstraWar::FTuneVar KShield(TEXT("shield_scale"), 1.f), KArmour(TEXT("armour_scale"), 1.f), KStruct(TEXT("struct_scale"), 1.2f);
	FAstraShipDamage& D = S.Dmg;
	D = FAstraShipDamage();
	D.bModel = true;
	D.ShieldScale = (Shield > 0.f ? C->ShieldScale : 1.f) * KShield.Get();
	D.Pool = Shield * D.ShieldScale;
	const float Armour = C->ArmourFrac * Hull * KArmour.Get();
	for (int32 s = 0; s < AstraWar::NumSections; ++s)
	{
		D.StructureMax[s] = D.Structure[s] = Hull * C->SectionShare[s] * KStruct.Get();
		for (int32 f = 0; f < AstraWar::NumFacings; ++f)
		{
			D.PlateMax[s][f] = D.Plate[s][f] = Armour * C->SectionShare[s] * C->FacingArmour[f];
		}
	}
	for (int32 f = 0; f < AstraWar::NumFacings; ++f)
	{
		D.Base[f] = D.Alloc[f] = C->ShieldAlloc[f];
		D.SectorMax[f] = D.Sector[f] = D.Pool * D.Alloc[f];
	}
	for (int32 k = 0; k < AstraWar::NumSystems; ++k)
	{
		D.SysSection[k] = C->SysSection[k];
	}
	for (FAstraMount& M : S.Mounts)
	{
		M.Health = 1.f;
	}
	SyncTotals(S);
}

void UAstraBattleSubsystem::SyncTotals(FAstraBattleShip& S) const
{
	const FAstraShipDamage& D = S.Dmg;
	if (!D.bModel)
	{
		return;
	}
	float H = 0.f, HM = 0.f, Sh = 0.f, ShM = 0.f;
	for (int32 s = 0; s < AstraWar::NumSections; ++s)
	{
		H += D.Structure[s];
		HM += D.StructureMax[s];
	}
	for (int32 f = 0; f < AstraWar::NumFacings; ++f)
	{
		Sh += D.Sector[f];
		ShM += D.SectorMax[f];
	}
	S.Hull = H;
	S.HullMax = HM;
	S.Shield = Sh;
	S.ShieldMax = ShM;
}

void UAstraBattleSubsystem::SetShieldFocus(FAstraBattleShip& S, int32 Facing, float K)
{
	FAstraShipDamage& D = S.Dmg;
	if (!D.bModel || D.FocusFacing == Facing)
	{
		return;
	}
	D.FocusFacing = Facing;
	if (Facing < 0)
	{
		for (int32 f = 0; f < AstraWar::NumFacings; ++f)
		{
			D.Alloc[f] = D.Base[f];
		}
		return;
	}
	// the generator's capacity gathers on the facing (and a little on the four faces next to it, none opposite)
	float Sum = 0.f;
	for (int32 f = 0; f < AstraWar::NumFacings; ++f)
	{
		const float Bump = f == Facing ? 0.7f : (f == WarOpposite(Facing) ? 0.f : 0.075f);
		D.Alloc[f] = D.Base[f] * (1.f - K) + K * Bump;
		Sum += D.Alloc[f];
	}
	for (int32 f = 0; f < AstraWar::NumFacings; ++f)
	{
		D.Alloc[f] /= FMath::Max(Sum, 1e-4f);
	}
}

float UAstraBattleSubsystem::EngineFactor(const FAstraBattleShip& S) const
{
	if (S.bDisabled)
	{
		return 0.f;
	}
	if (!S.Dmg.bModel)
	{
		return 1.f;
	}
	const float E = S.Dmg.Sys[AstraWar::SysEngines];
	return E <= 0.05f ? 0.f : 0.15f + 0.85f * E;
}

float UAstraBattleSubsystem::PowerFactorOf(const FAstraBattleShip& S) const
{
	if (S.bDisabled)
	{
		return 0.f;
	}
	return S.Dmg.bModel ? 0.15f + 0.85f * S.Dmg.Sys[AstraWar::SysReactor] : 1.f;
}

float UAstraBattleSubsystem::SensorFactor(const FAstraBattleShip& S) const
{
	if (S.bDisabled)
	{
		return 0.f;
	}
	return S.Dmg.bModel ? 0.3f + 0.7f * S.Dmg.Sys[AstraWar::SysSensors] : 1.f;
}

float UAstraBattleSubsystem::HangarFactor(const FAstraBattleShip& S) const
{
	if (S.bDisabled)
	{
		return 0.f;
	}
	if (!S.Dmg.bModel)
	{
		return 1.f;
	}
	const float H = S.Dmg.Sys[AstraWar::SysHangar];
	return H < 0.2f ? 0.f : H;
}

float UAstraBattleSubsystem::PlayerEngineFactor() const
{
	return Ships.Num() ? EngineFactor(Ships[0]) : 1.f;
}

void UAstraBattleSubsystem::RepairPlayerSystems(float Amount)
{
	if (Ships.Num() == 0 || !Ships[0].Dmg.bModel)
	{
		return;
	}
	FAstraBattleShip& P = Ships[0];
	for (int32 k = 0; k < AstraWar::NumSystems; ++k)
	{
		if (k == AstraWar::SysPointDefence || P.Dmg.GuttedT[FMath::Min<int32>(P.Dmg.SysSection[k], 2)] < 0.f)
		{
			P.Dmg.Sys[k] = FMath::Min(1.f, P.Dmg.Sys[k] + Amount);
		}
	}
	for (FAstraMount& M : P.Mounts)
	{
		if (P.Dmg.GuttedT[M.Section] < 0.f)
		{
			M.Health = FMath::Min(1.f, M.Health + Amount);
		}
	}
}

// ---------------------------------------------------------------------------------------------- hull, repairs
void UAstraBattleSubsystem::AddHullDelta(FAstraBattleShip& S, float Delta)
{
	FAstraShipDamage& D = S.Dmg;
	if (!D.bModel)
	{
		S.Hull = FMath::Clamp(S.Hull + Delta, 1.f, S.HullMax);
		return;
	}
	float Total = 0.f, Room = 0.f;
	for (int32 s = 0; s < AstraWar::NumSections; ++s)
	{
		Total += D.Structure[s];
		Room += D.StructureMax[s] - D.Structure[s];
	}
	if (Delta >= 0.f)
	{
		// repairs fill the sections in proportion to what is missing
		const float Give = FMath::Min(Delta, Room);
		for (int32 s = 0; s < AstraWar::NumSections && Room > 1e-3f; ++s)
		{
			const float Missing = D.StructureMax[s] - D.Structure[s];
			D.Structure[s] = FMath::Min(D.StructureMax[s], D.Structure[s] + Give * Missing / Room);
			if (D.GuttedT[s] >= 0.f && D.Structure[s] > 0.05f * D.StructureMax[s])
			{
				D.GuttedT[s] = -1.f;            // a section patched up is no longer gutted
			}
		}
	}
	else
	{
		// fires and the like: from what stands, but never to nothing (the old rule: the last point stays)
		const float Take = FMath::Min(-Delta, FMath::Max(0.f, Total - 1.f));
		for (int32 s = 0; s < AstraWar::NumSections && Total > 1e-3f; ++s)
		{
			D.Structure[s] = FMath::Max(0.f, D.Structure[s] - Take * D.Structure[s] / Total);
		}
	}
	SyncTotals(S);
}

void UAstraBattleSubsystem::SetHullFraction(FAstraBattleShip& S, float Frac)
{
	FAstraShipDamage& D = S.Dmg;
	Frac = FMath::Clamp(Frac, 0.f, 1.f);
	if (!D.bModel)
	{
		S.Hull = S.HullMax * Frac;
		return;
	}
	for (int32 s = 0; s < AstraWar::NumSections; ++s)
	{
		D.Structure[s] = D.StructureMax[s] * Frac;
		if (Frac > 0.05f)
		{
			D.GuttedT[s] = -1.f;
		}
	}
	SyncTotals(S);
}

// ---------------------------------------------------------------------------------------------- the blow
void UAstraBattleSubsystem::ApplyHit(FAstraBattleShip& To, const FVector& FromDir, float Damage, const FVector& HitPos, EAstraHitKind Kind, int32 SourceId)
{
	if (!To.bAlive || Damage <= 0.f)
	{
		return;
	}
	if (To.Dmg.bModel)
	{
		ApplyHitModel(To, FromDir, Damage, HitPos, Kind, SourceId);
	}
	else
	{
		ApplyHitLump(To, FromDir, Damage, HitPos, Kind, SourceId);
	}
}

void UAstraBattleSubsystem::ApplyHitModel(FAstraBattleShip& To, const FVector& FromDir, float Damage, const FVector& HitPos, EAstraHitKind Kind, int32 SourceId)
{
	FAstraShipDamage& D = To.Dmg;
	const EAstraDamageType Type = AstraDamageTypeOf(Kind);
	const FWarHitProfile P = WarProfileOf(Type, Damage);
	// --- where: the face it struck and the section along the hull, from the point where its path entered it
	static AstraWar::FTuneVar KScatter(TEXT("hit_scatter"), 0.5f);
	FVector N;
	int32 F, Sec;
	if (To.Box.Valid())
	{
		// the hull is a box of the mesh's own measures: the face is the one the point lies on, the section comes from where along
		// the hull it is against the class's cut planes; the fall of shot and the gunners' choice of aim scatter the hits along it
		const FVector Lp = To.Att.UnrotateVector(HitPos - To.Pos) - FVector(To.Box.Mid, 0.0, 0.0);
		const FVector R(Lp.X / To.Box.Hx, Lp.Y / To.Box.Hy, Lp.Z / To.Box.Hz);          // 1 on the surface, along each axis
		const FVector A = R.GetAbs();
		if (A.X >= A.Y && A.X >= A.Z)
		{
			F = R.X >= 0.0 ? AstraWar::Bow : AstraWar::Stern;
		}
		else if (A.Y >= A.Z)
		{
			F = R.Y >= 0.0 ? AstraWar::Starboard : AstraWar::Port;
		}
		else
		{
			F = R.Z >= 0.0 ? AstraWar::Dorsal : AstraWar::Ventral;
		}
		N = R.SizeSquared() > 1e-6 ? R.GetSafeNormal() : AstraWar::FacingVector(F);   // where on the hull, as a direction out of it
		const double X = Lp.X + To.Box.Mid + FMath::FRandRange(-1.f, 1.f) * KScatter.Get() * 1.3 * To.Box.Hx;
		Sec = X > To.Box.CutBow ? AstraWar::SecBow : (X < To.Box.CutStern ? AstraWar::SecStern : AstraWar::SecMid);
	}
	else
	{
		// no measures: the sphere's outward normal, the section scattered (a shot from ahead still strikes the bow)
		N = To.Att.UnrotateVector(HitPos - To.Pos);
		if (N.SizeSquared() < 1.0)
		{
			N = To.Att.UnrotateVector(-FromDir);                 // dead centre: from where it came
		}
		N = N.GetSafeNormal();
		F = AstraFacingOf(N);
		Sec = AstraWar::SectionOfNormal(FVector(N.X + FMath::FRandRange(-KScatter.Get(), KScatter.Get()), N.Y, N.Z));
	}
	D.LastHitLocal = N;
	D.LastHitAge = 0.f;
	D.LastHitFacing = (uint8)F;
	// --- 1. the shield sector of that face
	float Rem = Damage, ShieldTook = 0.f;
	if (To.bShieldsUp && !To.bDisabled && D.Sector[F] > 0.f)
	{
		const float PowerK = FMath::Clamp(0.7f + 0.3f * To.ShieldPower, 0.5f, 1.f);
		const float Absorbed = FMath::Min(D.Sector[F], Damage * P.ShieldEff * PowerK);
		D.Sector[F] -= Absorbed;
		Rem = Damage - Absorbed;
		ShieldTook = Absorbed;
		D.SectorFlash[F] = 1.f;
		To.ShieldFlash = 1.f;
		if (D.Sector[F] <= 0.f)
		{
			D.Sector[F] = 0.f;
			++Stats.SectorsCollapsed;
		}
	}
	// --- 2. the plate over that face of that section
	float PlateTook = 0.f;
	if (Rem > 0.f && D.Plate[Sec][F] > 0.f)
	{
		const float Reach = P.ArmourPen > 0.f ? FMath::Min(Rem, P.ArmourPen) : Rem;   // a heavy blow ignores the armour for the excess
		PlateTook = FMath::Min(D.Plate[Sec][F], Reach * P.ArmourResist);
		D.Plate[Sec][F] -= PlateTook;
		Rem -= PlateTook;
	}
	// --- 3. the structure (and what lives in the section)
	float StructTook = 0.f;
	if (Rem > 0.f)
	{
		StructTook = StructureDamage(To, Sec, Rem, Type, N, F);
	}
	SyncTotals(To);
	// --- the books
	{
		const int32 T = (int32)Type;
		Stats.DmgIn[T] += Damage;
		Stats.DmgShield[T] += ShieldTook;
		Stats.DmgPlate[T] += PlateTook;
		Stats.DmgStructure[T] += StructTook;
		Stats.DmgFacing[T][F] += Damage;
		++Stats.Hits[T];
		if (const FAstraBattleShip* Src = SourceId >= 0 ? FindById(SourceId) : nullptr)
		{
			Stats.NoteFocus(Src->Side == EAstraSide::Astra ? 0 : (Src->Side == EAstraSide::Mandate ? 1 : -1), To.Id, Damage);
		}
	}
	// --- what it looks like
	const float Felt = StructTook + 0.25f * PlateTook;            // what the hull feels of it (the crew's incidents, the scars, the shudder)
	if (FxOn())
	{
		FAstraFxHit H;                                              // the war's effects: the shield's ripple, the flash and sparks, the scar
		H.Pos = HitPos;
		H.Dir = FromDir.GetSafeNormal();
		H.Kind = Kind;
		H.Damage = Damage;
		H.ShieldTook = ShieldTook;
		H.Through = Damage - ShieldTook;
		H.Felt = Felt;
		H.Facing = F;
		H.Section = Sec;
		H.LocalOut = N;
		H.SectorFrac = D.SectorMax[F] > 0.f ? D.Sector[F] / D.SectorMax[F] : 0.f;
		H.bSectorFell = ShieldTook > 0.f && D.Sector[F] <= 0.f;
		WarFX->OnHit(To, H);
	}
	else
	{
		AddFlash(HitPos, Felt > 10.f ? 45.f : 25.f, 0.8f, ShieldTook > 0.f && Rem < Damage * 0.5f ? FLinearColor(0.6f, 0.8f, 1.f) : FLinearColor(1.f, 0.6f, 0.3f), 80.f);
		if (Felt > 8.f)
		{
			AddScar(To, HitPos, Felt);             // the plating remembers it
		}
	}
	if (To.bPlayer)
	{
		Shake = FMath::Min(1.f, Shake + (Felt > 20.f ? 0.8f : 0.35f));
		if (UAstraShipSubsystem* Ship = GetWorld()->GetSubsystem<UAstraShipSubsystem>())
		{
			Ship->AddHeat(ShieldTook * 0.012f * (Type == EAstraDamageType::Energy ? 1.5f : 1.f));   // what the shields stop becomes heat in the emitters
			Ship->OnHullHit(Felt, ShieldTook, FromDir);
		}
		if (USoundBase* Snd = LoadObject<USoundBase>(nullptr, TEXT("/Game/ASTRA/Audio/SW_Impact.SW_Impact")))
		{
			UGameplayStatics::PlaySound2D(GetWorld(), Snd, FMath::Clamp(0.4f + Felt / 60.f, 0.4f, 1.f));
		}
	}
	// --- what became of the ship
	if (To.Hull <= 0.5f)
	{
		if (To.bPlayer)
		{
			// the Aquila does not simply vanish: her reactor's containment fails and she is abandoned (the ship
			// subsystem runs the evacuation and calls AquilaBlasts/AquilaBreach when the reactor goes)
			for (int32 s = 0; s < AstraWar::NumSections; ++s)
			{
				D.Structure[s] = 0.f;
			}
			SyncTotals(To);
			To.Hull = 0.f;
			if (UAstraShipSubsystem* Ship = GetWorld()->GetSubsystem<UAstraShipSubsystem>())
			{
				Ship->ReactorFailing();
			}
			return;
		}
		KillModelShip(To, D.Sys[AstraWar::SysReactor] < 0.35f ? EAstraFate::ReactorBreach : EAstraFate::Breakup, Kind, Sec);
	}
}

/** The structure of a section takes the damage; what is left over spills into the neighbours. Returns what the structure took. */
float UAstraBattleSubsystem::StructureDamage(FAstraBattleShip& S, int32 Sec, float Amount, EAstraDamageType Type, const FVector& N, int32 F)
{
	FAstraShipDamage& D = S.Dmg;
	const FWarHitProfile P = WarProfileOf(Type, Amount);
	float Taken = 0.f, Left = Amount;
	int32 At = Sec;
	for (int32 Hop = 0; Hop < 3 && Left > 0.01f; ++Hop)
	{
		const bool bStood = D.Structure[At] > 0.f;
		const float Take = FMath::Min(D.Structure[At], Left);
		D.Structure[At] -= Take;
		Taken += Take;
		Left -= Take;
		if (Take > 0.f)
		{
			DamageInside(S, At, Take, P.SystemMul, N, F);
		}
		if (bStood && D.Structure[At] <= 0.f)
		{
			OnSectionGutted(S, At);
		}
		if (Left <= 0.01f)
		{
			break;
		}
		// what is left goes on into the next section: an end into the middle, the middle into the stronger end
		At = At == AstraWar::SecMid ? (D.Structure[AstraWar::SecBow] >= D.Structure[AstraWar::SecStern] ? AstraWar::SecBow : AstraWar::SecStern) : AstraWar::SecMid;
		Left *= 0.6f;
	}
	// a blast tears at the next sections too
	if (P.Splash > 0.f && Taken > 0.f)
	{
		const float Sp = Taken * P.Splash;
		const int32 Next[2] = {Sec == AstraWar::SecMid ? (int32)AstraWar::SecBow : (int32)AstraWar::SecMid, Sec == AstraWar::SecMid ? (int32)AstraWar::SecStern : -1};
		const float Share = Sec == AstraWar::SecMid ? 0.5f : 1.f;
		for (const int32 n : Next)
		{
			if (n < 0 || D.Structure[n] <= 0.f)
			{
				continue;
			}
			const bool bStood = D.Structure[n] > 0.f;
			const float Tk = FMath::Min(D.Structure[n], Sp * Share);
			D.Structure[n] -= Tk;
			Taken += Tk;
			DamageInside(S, n, Tk, P.SystemMul * 0.6f, N, F);
			if (bStood && D.Structure[n] <= 0.f)
			{
				OnSectionGutted(S, n);
			}
		}
	}
	// fire and venting where it hit
	if (Taken > 0.f)
	{
		const float Frac = Taken / FMath::Max(1.f, D.StructureMax[Sec]);
		if (FMath::FRand() < FMath::Clamp(Frac / 0.05f, 0.f, 1.f) * P.FireK * 0.5f)
		{
			D.Burn[Sec] = FMath::FRandRange(30.f, 90.f);
		}
		if (FMath::FRand() < FMath::Clamp(Frac / 0.04f, 0.f, 1.f) * P.BreachK * 0.5f)
		{
			D.Breach[Sec] = 40.f;
		}
	}
	return Taken;
}

/** What lives in a section wears down with the damage it takes: the systems (by how exposed they are on the face that was
 *  hit) and the weapon mounts. */
void UAstraBattleSubsystem::DamageInside(FAstraBattleShip& S, int32 Sec, float Taken, float SystemMul, const FVector& N, int32 F)
{
	FAstraShipDamage& D = S.Dmg;
	const float Frac = Taken / FMath::Max(1.f, D.StructureMax[Sec]);
	if (Frac <= 0.f)
	{
		return;
	}
	for (int32 k = 0; k < AstraWar::NumSystems; ++k)
	{
		const bool bSpread = k == AstraWar::SysPointDefence;
		if (!bSpread && D.SysSection[k] != Sec)
		{
			continue;
		}
		const float dH = Frac * WarSystemFragility[k] * SystemMul * (bSpread ? 0.5f : 1.f) * WarSystemExposure[k][F] * FMath::FRandRange(0.4f, 1.6f);
		D.Sys[k] = FMath::Max(0.f, D.Sys[k] - dH);
	}
	for (FAstraMount& M : S.Mounts)
	{
		if (M.Section != Sec)
		{
			continue;
		}
		const float Align = FVector::DotProduct(M.Dir, N) > 0.3f ? 1.f : 0.5f;
		M.Health = FMath::Max(0.f, M.Health - Frac * 2.2f * SystemMul * Align * FMath::FRandRange(0.3f, 1.7f));
	}
	// a real bite out of the section: one thing in it is struck outright
	if (Frac > 0.06f && FMath::FRand() < 0.5f)
	{
		TArray<int32, TInlineAllocator<12>> Here;
		for (int32 k = 0; k < AstraWar::NumSystems; ++k)
		{
			if (k != AstraWar::SysPointDefence && D.SysSection[k] == Sec)
			{
				Here.Add(k);
			}
		}
		for (int32 i = 0; i < S.Mounts.Num(); ++i)
		{
			if (S.Mounts[i].Section == Sec)
			{
				Here.Add(100 + i);
			}
		}
		if (Here.Num())
		{
			const int32 Pick = Here[FMath::RandRange(0, Here.Num() - 1)];
			const float Hit = FMath::FRandRange(0.2f, 0.5f);
			if (Pick >= 100)
			{
				S.Mounts[Pick - 100].Health = FMath::Max(0.f, S.Mounts[Pick - 100].Health - Hit);
			}
			else
			{
				D.Sys[Pick] = FMath::Max(0.f, D.Sys[Pick] - Hit);
			}
		}
	}
}

void UAstraBattleSubsystem::OnSectionGutted(FAstraBattleShip& S, int32 Sec)
{
	FAstraShipDamage& D = S.Dmg;
	D.Structure[Sec] = 0.f;
	D.GuttedT[Sec] = 0.f;
	D.Burn[Sec] = 90.f;
	D.Breach[Sec] = 90.f;
	for (int32 k = 0; k < AstraWar::NumSystems; ++k)
	{
		if (k == AstraWar::SysPointDefence)
		{
			D.Sys[k] *= 0.66f;                  // a third of the point defence sat there
		}
		else if (D.SysSection[k] == Sec)
		{
			D.Sys[k] = 0.f;
		}
	}
	for (FAstraMount& M : S.Mounts)
	{
		if (M.Section == Sec)
		{
			M.Health = 0.f;
		}
	}
	// the hull may break apart at the gutted section (a few seconds' warning): rarely at the first, likely at the second, and
	// surely at the third (the middle holds the rest together, so it is likelier to let go). The Aquila never does: her end
	// is the reactor's.
	static AstraWar::FTuneVar KP1(TEXT("breakup_p1"), 0.25f), KP2(TEXT("breakup_p2"), 0.7f);
	int32 Gutted = 0;
	for (int32 s = 0; s < AstraWar::NumSections; ++s)
	{
		Gutted += D.GuttedT[s] >= 0.f ? 1 : 0;
	}
	const float PBreak = FMath::Min(1.f, (Gutted <= 1 ? KP1.Get() : (Gutted == 2 ? KP2.Get() : 1.f)) * (Sec == AstraWar::SecMid ? 1.5f : 1.f));
	if (!S.bPlayer && !D.bBreakingUp && FMath::FRand() < PBreak)
	{
		D.bBreakingUp = true;
		D.BreakupT = FMath::FRandRange(2.5f, 8.f);
		D.BreakSection = (uint8)Sec;
	}
	if (!S.bFog || S.Track >= 2)
	{
		Report(FString::Printf(TEXT("tactical: %s — the %s section is gutted%s"), *KnownLabel(S), AstraWar::SectionName(Sec),
		                       D.bBreakingUp && !S.bPlayer ? TEXT(", the hull is breaking up") : TEXT("")), true);
	}
}

void UAstraBattleSubsystem::DisableShip(FAstraBattleShip& S, const TCHAR* Why)
{
	if (S.bDisabled || S.bPlayer || !S.bAlive)
	{
		return;
	}
	const bool bWasCommander = S.Side == EAstraSide::Mandate && S.bHostile && MandateCommander() == S.ContactId;
	S.bDisabled = true;
	S.DeathHow = EAstraFate::Disabled;
	if (FxOn())
	{
		WarFX->OnShipDisabled(S);                 // the lights go out, a last discharge of sparks (AstraWarFX.cpp)
	}
	if (!S.bCraft && !S.bGhost)
	{
		NoteGroupLoss(S, *FString::Printf(TEXT("disabled, %s"), Why));
	}
	S.Mode = EAstraShipMode::Idle;
	S.bFleeing = false;
	S.TargetId = -1;
	S.OrderTarget = -1;
	S.bShieldsUp = false;
	for (int32 f = 0; f < AstraWar::NumFacings; ++f)
	{
		S.Dmg.Sector[f] = 0.f;
	}
	S.Dmg.Buffer = 0.f;
	S.Dmg.bBreakingUp = false;
	S.Dmg.Sys[AstraWar::SysReactor] = 0.f;
	S.SpinDeg = FMath::FRandRange(0.3f, 1.0f);
	SyncTotals(S);
	if (S.Side != EAstraSide::Neutral)
	{
		++Stats.ShipFate[S.Side == EAstraSide::Astra ? 0 : 1][(int32)EAstraFate::Disabled];
	}
	FAstraDeathEvent E;
	E.Time = Time;
	E.ShipId = S.Id;
	E.ContactId = S.ContactId;
	E.Name = S.Name;
	E.Class = S.Class;
	E.How = EAstraFate::Disabled;
	E.Pos = S.Pos;
	E.Vel = S.Vel;
	E.Att = S.Att;
	E.Radius = S.Radius;
	E.CutBowX = S.Box.CutBow;
	E.CutSternX = S.Box.CutStern;
	E.bAstra = S.Side == EAstraSide::Astra;
	DeathEvents.Add(E);
	if (DeathEvents.Num() > 64)
	{
		DeathEvents.RemoveAt(0);
	}
	if (!S.bFog || S.Track >= 2)
	{
		Report(FString::Printf(TEXT("tactical: %s has gone dark — %s: no power, drifting, no longer a threat"), *KnownLabel(S), Why), true);
	}
	if (bWasCommander)
	{
		OnCommanderLost(S, TEXT("was disabled"));
	}
}

void UAstraBattleSubsystem::KillModelShip(FAstraBattleShip& S, EAstraFate How, EAstraHitKind Cause, int32 Section)
{
	Destroy(S, Cause, How, (uint8)Section);
}

// ---------------------------------------------------------------------------------------------- each tick
void UAstraBattleSubsystem::TickShields(FAstraBattleShip& S, float Dt)
{
	FAstraShipDamage& D = S.Dmg;
	if (D.Pool <= 0.f)
	{
		return;
	}
	for (int32 f = 0; f < AstraWar::NumFacings; ++f)
	{
		D.SectorMax[f] = D.Pool * D.Alloc[f];
	}
	if (!S.bShieldsUp || S.bDisabled)
	{
		return;                                   // down: inert (the charge stays, nothing regenerates)
	}
	const float SumBefore = S.Shield;
	// a reallocation: the sectors above their new capacity give the excess up, at a finite rate, into the buffer
	const float Rate = 0.10f * D.Pool * Dt;
	for (int32 f = 0; f < AstraWar::NumFacings; ++f)
	{
		if (D.Sector[f] > D.SectorMax[f])
		{
			const float Give = FMath::Min(D.Sector[f] - D.SectorMax[f], Rate);
			D.Sector[f] -= Give;
			D.Buffer += Give;
		}
	}
	// the buffer and the generator's regeneration fill the deficits, in proportion to the allocation
	float Avail = FMath::Min(D.Buffer, 2.f * Rate);
	D.Buffer -= Avail;
	const float Regen = S.ShieldRegen * D.ShieldScale * S.ShieldPower * PowerFactorOf(S) * Dt;
	Avail += Regen;
	for (int32 Pass = 0; Pass < 3 && Avail > 1e-4f; ++Pass)
	{
		float W = 0.f;
		for (int32 f = 0; f < AstraWar::NumFacings; ++f)
		{
			W += D.Sector[f] < D.SectorMax[f] ? D.Alloc[f] : 0.f;
		}
		if (W <= 1e-6f)
		{
			break;
		}
		const float Pool = Avail;
		Avail = 0.f;
		for (int32 f = 0; f < AstraWar::NumFacings; ++f)
		{
			if (D.Sector[f] >= D.SectorMax[f])
			{
				continue;
			}
			const float Want = Pool * D.Alloc[f] / W;
			const float Room = D.SectorMax[f] - D.Sector[f];
			const float Put = FMath::Min(Want, Room);
			D.Sector[f] += Put;
			Avail += Want - Put;
		}
	}
	D.Buffer += Avail;                            // what fits nowhere waits for the next tick
	SyncTotals(S);
	if (S.bPlayer && S.Shield > SumBefore)
	{
		if (UAstraShipSubsystem* Ship = GetWorld()->GetSubsystem<UAstraShipSubsystem>())
		{
			Ship->AddHeat((S.Shield - SumBefore) * 0.06f / D.ShieldScale);   // the emitters recharging run hot
		}
	}
}

void UAstraBattleSubsystem::TickDamageState(FAstraBattleShip& S, float Dt)
{
	FAstraShipDamage& D = S.Dmg;
	D.LastHitAge += Dt;
	for (int32 f = 0; f < AstraWar::NumFacings; ++f)
	{
		D.SectorFlash[f] = FMath::Max(0.f, D.SectorFlash[f] - Dt * 2.5f);
	}
	// the shield officer: the Aquila's mode (set by the tactical station) or, for the others, the main threat
	if (S.bPlayer)
	{
		SetShieldFocus(S, S.ShieldFacing.IsNearlyZero() ? -1 : AstraFacingOf(S.ShieldFacing), 0.5f);
	}
	else if (!S.bDisabled && (D.AutoFocusT -= Dt) <= 0.f)
	{
		D.AutoFocusT = 1.5f;
		FVector Threat = FVector::ZeroVector;
		int32 Inbound = 0;
		for (const FAstraProjectile& Pr : Projectiles)
		{
			if (!Pr.bDead && Pr.Target == S.Id && Pr.Kind == EAstraProjKind::Missile && FVector::DistSquared(Pr.Pos, S.Pos) < FMath::Square(9000.0))
			{
				Threat += (Pr.Pos - S.Pos).GetSafeNormal();
				++Inbound;
			}
		}
		if (Inbound == 0)
		{
			if (const FAstraBattleShip* T = FindById(S.TargetId); T && T->bAlive && S.Mode == EAstraShipMode::Attack)
			{
				Threat = (T->Pos - S.Pos).GetSafeNormal();
			}
		}
		SetShieldFocus(S, Threat.IsNearlyZero() ? -1 : AstraFacingOf(S.Att.UnrotateVector(Threat.GetSafeNormal())), 0.5f);
	}
	TickShields(S, Dt);
	// fire and venting; the crews put fires out in time (the Aquila's are the incident system's, not this one's)
	static AstraWar::FTuneVar KFire(TEXT("fire_dps"), 0.0015f);
	for (int32 s = 0; s < AstraWar::NumSections; ++s)
	{
		D.Breach[s] = FMath::Max(0.f, D.Breach[s] - Dt);
		if (D.Burn[s] > 0.f)
		{
			D.Burn[s] = FMath::Max(0.f, D.Burn[s] - Dt);
			if (!S.bPlayer && !S.bDisabled && D.Structure[s] > 0.f)
			{
				D.Structure[s] = FMath::Max(0.f, D.Structure[s] - KFire.Get() * D.StructureMax[s] * Dt);
				if (D.Structure[s] <= 0.f)
				{
					OnSectionGutted(S, s);
				}
			}
		}
		if (D.GuttedT[s] >= 0.f)
		{
			D.GuttedT[s] += Dt;
		}
	}
	SyncTotals(S);
	// the crew's repair of what is broken (the Aquila's damage control: slow, and not in a gutted section)
	if (S.bPlayer && S.bAlive)
	{
		RepairPlayerSystems(0.004f * Dt);
	}
	D.bReactorCritical = D.Sys[AstraWar::SysReactor] < 0.3f;
	D.ThinkDelay = 3.f * (1.f - D.Sys[AstraWar::SysBridge]);
	if (S.bPlayer)
	{
		return;
	}
	// --- what becomes of it
	if (D.bBreakingUp && (D.BreakupT -= Dt) <= 0.f)
	{
		KillModelShip(S, EAstraFate::Breakup, EAstraHitKind::Internal, D.BreakSection);
		return;
	}
	if (!S.bDisabled)
	{
		if (D.Sys[AstraWar::SysReactor] <= 0.02f)
		{
			// the reactor is gone: a breach takes the ship, or it scrams and she is left without power
			if (FMath::FRand() < (S.Hull < 0.5f * S.HullMax ? 0.5f : 0.3f))
			{
				KillModelShip(S, EAstraFate::ReactorBreach, EAstraHitKind::Internal, AstraWar::SecMid);
			}
			else
			{
				DisableShip(S, TEXT("the reactor scrammed"));
			}
		}
		else if (S.Hull < 0.06f * S.HullMax && S.bHostile)
		{
			DisableShip(S, TEXT("the crew has abandoned her"));
		}
	}
}

// ---------------------------------------------------------------------------------------------- weapons: the mounts
int32 UAstraBattleSubsystem::BearingBarrels(const FAstraBattleShip& S, EAstraMountKind Kind, const FVector& AimDir) const
{
	if (S.Mounts.Num() == 0)
	{
		return Kind == EAstraMountKind::Rail ? S.RailSlugs : 2;
	}
	const FVector Local = S.Att.UnrotateVector(AimDir).GetSafeNormal();
	int32 N = 0;
	for (const FAstraMount& M : S.Mounts)
	{
		N += (M.Kind == Kind && M.CanBear(Local)) ? M.Barrels : 0;
	}
	return N;
}

void UAstraBattleSubsystem::FireMounts(FAstraBattleShip& S, FAstraBattleShip& T, double Dist)
{
	const float Pwr = FMath::Clamp(PowerFactorOf(S) * S.WeaponPower, 0.25f, 1.5f);
	const double Tof = Dist / 12000.0;
	const FVector Local = S.Att.UnrotateVector(T.Pos + T.Vel * Tof - S.Pos).GetSafeNormal();
	for (FAstraMount& M : S.Mounts)
	{
		if (M.T > 0.f || M.Health < 0.2f || !M.CanBear(Local))
		{
			continue;
		}
		if (M.Kind == EAstraMountKind::Rail)
		{
			if (S.RailDamage <= 0.f || Dist >= S.RailRange)
			{
				continue;
			}
			S.LitT = 40.f;                                  // the muzzle flashes and the rails' pulse: every sensor sees it
			M.T = S.RailCd * M.Cd * FMath::FRandRange(0.8f, 1.2f) / Pwr;
			for (int32 i = 0; i < M.Barrels; ++i)
			{
				FireRail(S, T, (0.0012f + Dist / 30e6) * (S.bJammed ? 3.f : 1.f));
			}
		}
		else
		{
			if (S.LaserDamage <= 0.f || Dist >= S.LaserRange)
			{
				continue;
			}
			M.T = S.LaserCd * M.Cd * FMath::FRandRange(0.8f, 1.2f) / Pwr;
			for (int32 i = 0; i < M.Barrels; ++i)
			{
				FireLaser(S, T);
			}
		}
	}
}

// ---------------------------------------------------------------------------------------------- what may be read of it
bool UAstraBattleSubsystem::GetDamageView(const FString& ContactId, FDamageView& Out) const
{
	const FAstraBattleShip* S = FindByContact(ContactId);
	return S && GetDamageViewById(S->Id, Out);
}

bool UAstraBattleSubsystem::GetDamageViewById(int32 ShipId, FDamageView& Out) const
{
	Out = FDamageView();
	const FAstraBattleShip* S = FindById(ShipId);
	if (!S || !S->bAlive || !S->Dmg.bModel)
	{
		return false;
	}
	const FAstraShipDamage& D = S->Dmg;
	// what the Aquila can know: her own side by datalink (everything), a firm track by sensors and eyes (structure and
	// shields, what burns, vents, breaks), a bearing only nothing
	const bool bOwn = S->bPlayer || S->Side == EAstraSide::Astra;
	const bool bFirm = !S->bFog || S->Track >= 2;
	Out.Detail = bOwn ? 3 : (bFirm ? ((S->bFog ? S->bClassified : S->bIdentified) ? 2 : 1) : 0);
	if (Out.Detail == 0)
	{
		return false;
	}
	Out.Id = S->Id;
	Out.ContactId = S->ContactId;
	Out.Side = S->Side;
	Out.Pos = S->Pos;
	Out.Att = S->Att;
	Out.bDisabled = S->bDisabled;
	Out.bBreakingUp = D.bBreakingUp;
	Out.BreakSection = D.BreakSection;
	Out.BreakAxis = S->Att.GetForwardVector();
	Out.BreakPoint = S->Pos + Out.BreakAxis * BreakX(*S, D.BreakSection);
	Out.CutBowX = S->Box.CutBow;
	Out.CutSternX = S->Box.CutStern;
	for (int32 s = 0; s < AstraWar::NumSections; ++s)
	{
		Out.bGutted[s] = D.GuttedT[s] >= 0.f;
		Out.bBurning[s] = D.Burn[s] > 0.f;
		Out.bBreached[s] = D.Breach[s] > 0.f;
		if (Out.Detail >= 2)
		{
			Out.StructureFrac[s] = D.StructureMax[s] > 0.f ? D.Structure[s] / D.StructureMax[s] : 0.f;
			for (int32 f = 0; f < AstraWar::NumFacings; ++f)
			{
				Out.PlateFrac[s][f] = D.PlateMax[s][f] > 0.f ? D.Plate[s][f] / D.PlateMax[s][f] : 0.f;
			}
		}
	}
	if (Out.Detail >= 2)
	{
		for (int32 f = 0; f < AstraWar::NumFacings; ++f)
		{
			Out.ShieldFrac[f] = D.SectorMax[f] > 0.f ? D.Sector[f] / D.SectorMax[f] : 0.f;
			Out.ShieldFlash[f] = D.SectorFlash[f];
			Out.ShieldValue[f] = D.Sector[f];
			Out.ShieldCap[f] = D.SectorMax[f];
		}
		Out.LastHitLocal = D.LastHitLocal;
		Out.LastHitAge = D.LastHitAge;
		Out.LastHitFacing = D.LastHitFacing;
	}
	if (Out.Detail >= 3)
	{
		for (int32 k = 0; k < AstraWar::NumSystems; ++k)
		{
			Out.Sys[k] = D.Sys[k];
		}
		for (const FAstraMount& M : S->Mounts)
		{
			FDamageView::FMountView V;
			V.Kind = M.Kind;
			V.Dir = M.Dir;
			V.ArcDeg = FMath::RadiansToDegrees(FMath::Acos(FMath::Clamp(M.ArcCos, -1.f, 1.f)));
			V.Section = M.Section;
			V.Health = M.Health;
			V.bReady = M.Health >= 0.2f && M.T <= 0.f;
			Out.Mounts.Add(V);
		}
		Out.bReactorCritical = D.bReactorCritical;
	}
	return true;
}

void UAstraBattleSubsystem::ConsumeDeathEvents(TArray<FAstraDeathEvent>& Out)
{
	Out.Append(DeathEvents);
	DeathEvents.Reset();
}
