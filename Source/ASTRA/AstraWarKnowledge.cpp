// ASTRA — what each side knows (docs/GUERRA.md, principle 4: the truth and the belief), and the bookkeeping that keeps a
// battle of hundreds cheap: the id index, the clearing of dead craft, the proximity grid.
//
// Every warship and craft of a side is a sensor; what any of them holds is shared by datalink across the side. A ship is
// held when some observer of the other side is inside the reach of its sensors (their health scales it) times the
// target's signature (a capital ship 1, a craft a third, a ship running dark or dead in the water much less, a ship that
// has just fired more). A held ship is remembered for a while: its last position and velocity are what the AI goes on.
// The Aquila's own picture (TickSensors: EMCON, jamming, bearings) stays what the crew and the ASTRA fleet know of the
// Mandate's fogged ships; the Mandate finds the Aquila only as TickDetection says.

#include "AstraBattleSubsystem.h"
#include "AstraWarClasses.h"
#include "ASTRA.h"

namespace
{
	using AstraWar::WarKm;
}

// ---------------------------------------------------------------------------------------------- the id index
void UAstraBattleSubsystem::RebuildIdIndex()
{
	IdIndex.Reset();
	for (int32 i = 0; i < Ships.Num(); ++i)
	{
		IdIndex.Add(Ships[i].Id, i);
	}
}

/** Craft that have been off the plot for a while leave the array (a long battle launches thousands of sorties): everything
 *  else refers to ships by id, so nothing dangles. Called between ticks, where no pointer into Ships is held. */
void UAstraBattleSubsystem::CompactShips()
{
	int32 Dead = 0;
	for (const FAstraBattleShip& S : Ships)
	{
		Dead += (S.bCraft && !S.bAlive && S.DeadT > 20.f && S.Id != PilotedId) ? 1 : 0;
	}
	if (Dead < 48)
	{
		return;
	}
	for (int32 i = Ships.Num() - 1; i >= 1; --i)
	{
		const FAstraBattleShip& S = Ships[i];
		if (S.bCraft && !S.bAlive && S.DeadT > 20.f && S.Id != PilotedId)
		{
			Ships.RemoveAt(i, EAllowShrinking::No);
		}
	}
	RebuildIdIndex();
}

void UAstraBattleSubsystem::BuildGrid()
{
	Grid.Reset(Ships.Num());
	CapIdx.Reset();
	HulkIdx.Reset();
	for (int32 i = 0; i < Ships.Num(); ++i)
	{
		const FAstraBattleShip& S = Ships[i];
		if (S.bAlive && !S.bGhost)
		{
			Grid.Add(i, S.Pos);
			if (!S.bCraft)
			{
				CapIdx.Add(i);
			}
		}
	}
	for (int32 i = 0; i < Wrecks.Num(); ++i)
	{
		if (Wrecks[i].Radius > 0.f)
		{
			HulkIdx.Add(i);
		}
	}
}

// ---------------------------------------------------------------------------------------------- sensors
float UAstraBattleSubsystem::SignatureOf(const FAstraBattleShip& T) const
{
	float Sig = T.bCraft ? (T.CraftKind == 2 ? 0.25f : 0.35f) : 1.f;
	if (T.bDisabled || T.bDerelict)
	{
		return 0.25f;                                   // no emissions: seen by eye and radar return only
	}
	if (T.bDark || T.bCold)
	{
		Sig *= 0.33f;
	}
	const float Speed = FMath::Clamp(T.Vel.Size() / FMath::Max(T.CruiseSpeed, 1.f), 0.f, 1.5f);
	Sig *= 0.75f + 0.25f * Speed;                         // the drive at speed shows more
	if (T.LitT > 0.f)
	{
		Sig *= 1.6f;                                      // it fired: every sensor saw it
	}
	return Sig;
}

double UAstraBattleSubsystem::SensorReachM(const FAstraBattleShip& O) const
{
	double Km = O.bCraft ? (O.CraftKind == 2 ? 8.0 : (O.CraftKind == 1 ? 10.0 : 12.0)) : O.SensorKm;
	Km *= SensorFactor(O);
	return Km * WarKm;
}

void UAstraBattleSubsystem::TickKnowledge()
{
	// each side's observers against the other's ships
	for (FAstraBattleShip& T : Ships)
	{
		if (!T.bAlive || T.bGhost || AstraSideIdx(T.Side) < 0)
		{
			continue;
		}
		const int32 Us = AstraSideIdx(T.Side);          // the side T belongs to; the OTHER side is the one that looks
		const int32 Them = 1 - Us;
		if (T.bPlayer)
		{
			// the Mandate finds the Aquila as TickDetection says (her signature, EMCON, what she fired)
			if (Them == 1 && bPlayerTracked)
			{
				T.SeenT[Them] = Time;
				T.SeenPos[Them] = T.Pos;
				T.SeenVel[Them] = T.Vel;
			}
			continue;
		}
		if (T.bFog && T.Side == EAstraSide::Mandate)
		{
			// the Aquila's picture of a fogged Mandate ship (TickSensors) is the ASTRA side's: a firm track
			if (T.Track >= 2)
			{
				T.SeenT[0] = Time;
				T.SeenPos[0] = T.Pos;
				T.SeenVel[0] = T.Vel;
			}
			// (and the Mandate needs no eyes on its own)
		}
		const float Sig = SignatureOf(T);
		bool bSeen = false;
		for (const FAstraBattleShip& O : Ships)
		{
			if (!O.bAlive || O.bGhost || O.bDerelict || O.bDisabled || O.bPlayer || AstraSideIdx(O.Side) != Them)
			{
				continue;
			}
			const double Reach = SensorReachM(O) * Sig;
			if (FVector::DistSquared(O.Pos, T.Pos) < Reach * Reach)
			{
				bSeen = true;
				break;
			}
		}
		if (bSeen && !(T.bFog && T.Side == EAstraSide::Mandate && Them == 0))
		{
			T.SeenT[Them] = Time;
			T.SeenPos[Them] = T.Pos;
			T.SeenVel[Them] = T.Vel;
		}
	}
}

bool UAstraBattleSubsystem::Knows(int32 SideIdx, const FAstraBattleShip& T) const
{
	if (SideIdx < 0)
	{
		return false;
	}
	if (T.bPlayer && SideIdx == 0)
	{
		return true;                                       // our own carrier
	}
	return Time - T.SeenT[SideIdx] <= (T.bCraft ? 4.f : 25.f);
}

FVector UAstraBattleSubsystem::KnownPos(int32 SideIdx, const FAstraBattleShip& T) const
{
	if (SideIdx < 0 || AstraSideIdx(T.Side) != 1 - SideIdx)
	{
		return T.Pos;                                      // not an enemy of that side: no fog to keep (the freighter, a friend)
	}
	const float Age = Time - T.SeenT[SideIdx];
	if (Age <= 0.6f || (T.bPlayer && SideIdx == 0))
	{
		return T.Pos;                                      // held right now: where it is
	}
	return T.SeenPos[SideIdx] + T.SeenVel[SideIdx] * FMath::Min(Age, 25.f);   // lost a moment ago: dead reckoning
}
