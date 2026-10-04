// ASTRA — the Captain's Falcon and what lies near her, in the game (SPAZIO-VIVO, docs/SPAZIO.md §13): the lifepods adrift near her and the key that takes one aboard, and a word of warning for the hull she is flying at or lies close to.
//
// The Falcon is flown by the battle (TickPiloted: the stick drives the craft; PilotCollision loses her in a hull). This reads where she is and what is about and says it: a lifepod within her grapples' reach, a hull on her course, a hull close. It moves
// nothing and changes no rule of flight: what the pilot does with the words is hers.
//
// The hulls. The ones the crash test knows, warned of a little before it: the places' hulls and the pieces of the wrecks (the solid cells of data/space/solids.json, each in the frame it is drawn in now: AstraSpaceLifeSolids.h), the warships (the war's hull
// box: the class's true measures, as a shot strikes it), the Aquila (her own box, except near the mouth of her tube, where the Falcon is meant to fly in). Of each, two questions: does her course, at the speed she has against that hull, enter it within five
// seconds (a COLLISION COURSE, with the seconds); and, if not, is it within 250 m of her (a PROXIMITY, with the metres). The most urgent answer wins: the soonest collision, else the nearest hull.
//
// The lifepods. Those adrift with air within 12 km (the beacons the Aquila hears, and any pod launched and not yet calling: a pilot who is there sees it), nearest first, four at most; the nearest within reach of her grapples (astra.space.pod.reach)
// can be taken aboard with R: RescueTake, by "Eagle", and the crew hears the flight net's search-and-rescue line.

#include "AstraSpaceLife.h"
#include "AstraBattleSubsystem.h"
#include "ASTRA.h"
#include "Engine/World.h"
#include "HAL/IConsoleManager.h"
#include "HAL/PlatformTime.h"

using AstraSpace::FSolids;
using AstraSpace::FWrecks;

namespace
{
	constexpr double FcKm = 1000.0;
	constexpr double FcPodKm = 12.0;               // the lifepods the cockpit's displays list: within this of the Falcon
	constexpr int32 FcPodsListed = 4;
	constexpr double FcLookS = 5.0;                // a course into a hull is warned this many seconds ahead
	constexpr double FcPathMaxM = 4000.0;          // and no farther than this (a Falcon at full boost goes 5 km in that time: past 4 the horizon is the battle's, not hers)
	constexpr double FcNearM = 250.0;              // a hull this close to her is a proximity
	constexpr double FcMouthM = 1200.0;            // within this of the mouth of her tube the Aquila's own hull is not warned of: the Falcon is meant to fly in there
	constexpr double FcHomeM = 250.0;              // nor when her course passes this near the mouth (she is coming home)
	constexpr double FcCrashK = 0.9;               // a ship's box is shrunk this much for a course into it (the crash test's own is 0.8 of the mesh's outline: the word comes a little before the loss)

	TAutoConsoleVariable<float> CVarFcReach(TEXT("astra.space.pod.reach"), 200.f,
		TEXT("How near (m) the Captain's Falcon must be to a lifepod to take it aboard with R (the reach of her grapples)"));
	TAutoConsoleVariable<int32> CVarFcCue(TEXT("astra.space.falcon.cue"), 1,
		TEXT("The Captain's Falcon's word of the hulls near her (COLLISION COURSE and PROXIMITY on the canopy): 1 on, 0 off"));

	/** The most urgent word so far: a course into a hull (the soonest) over a hull close (the nearest). */
	struct FFcCue
	{
		uint8 Level = 0;
		FString What;
		double RangeM = 0.0, TtcS = 0.0;

		void Course(const FString& InWhat, double InRangeM, double InTtcS)
		{
			if (Level < 2 || InTtcS < TtcS)
			{
				Level = 2;
				What = InWhat;
				RangeM = InRangeM;
				TtcS = InTtcS;
			}
		}
		void Near(const FString& InWhat, double InRangeM)
		{
			if (Level == 0 || (Level == 1 && InRangeM < RangeM))
			{
				Level = 1;
				What = InWhat;
				RangeM = InRangeM;
				TtcS = 0.0;
			}
		}
	};

	/** The Falcon (Pos, Vel: the system frame) against a hull of solid cells in its own frame (ToSys: mesh frame to system frame; HullVel what it is doing): her course against it, and how near she lies. */
	void FcSolids(const FSolids& Sol, const FTransform& ToSys, const FVector& HullVel, const FVector& Pos, const FVector& Vel, const FString& Name, FFcCue& Cue)
	{
		const FTransform Inv = ToSys.Inverse();
		const FVector Rel = Vel - HullVel;
		const double Speed = Rel.Size();
		const FVector A = Inv.TransformPosition(Pos);
		if (Speed > 5.0)
		{
			const double PathM = FMath::Min(Speed * FcLookS, FcPathMaxM);
			const double T = Sol.FirstHit(A, Inv.TransformPosition(Pos + Rel * (PathM / Speed)));
			if (T > 0.0)                                                   // (0: she is in a cell already: the crash test has her)
			{
				Cue.Course(Name, PathM * T, PathM * T / Speed);
				return;
			}
		}
		const double D = Sol.ShellDistance(A, FcNearM);
		if (D > 0.0)
		{
			Cue.Near(Name, D);
		}
	}

	/** The same against an oriented box (Centre and Att: where it lies; Half: its half sizes, metres). */
	void FcBox(const FVector& Centre, const FQuat& Att, const FVector& Half, const FVector& HullVel, const FVector& Pos, const FVector& Vel, const FString& Name, FFcCue& Cue)
	{
		const FVector P = Att.UnrotateVector(Pos - Centre);
		const FVector V = Att.UnrotateVector(Vel - HullVel);
		const double Speed = V.Size();
		if (Speed > 5.0)
		{
			// the course against the box shrunk a little (a slab test): when she first is inside it, within the look-ahead
			double T0 = 0.0, T1 = FcLookS;
			bool bMiss = false;
			for (int32 k = 0; k < 3 && !bMiss; ++k)
			{
				const double H = (double)Half[k] * FcCrashK;
				if (FMath::Abs(V[k]) < 1.0e-6)
				{
					bMiss = FMath::Abs(P[k]) > H;
					continue;
				}
				double Ta = (-H - P[k]) / V[k], Tb = (H - P[k]) / V[k];
				if (Ta > Tb)
				{
					Swap(Ta, Tb);
				}
				T0 = FMath::Max(T0, Ta);
				T1 = FMath::Min(T1, Tb);
				bMiss = T0 > T1;
			}
			if (!bMiss && T0 > 0.0)                                         // (T0 0: she is in it already: the crash test has her)
			{
				Cue.Course(Name, Speed * T0, T0);
				return;
			}
		}
		const double D = (P.GetAbs() - Half).ComponentMax(FVector::ZeroVector).Size();
		if (D < FcNearM)
		{
			Cue.Near(Name, D);
		}
	}

	/** Where a turning part of a place is (the angle about its axis, as the drawing has it: DrawPlaces and PilotHit use the same clock and the same turn). */
	float FcPartAngle(const AstraSpace::FPart& D, float ClockS)
	{
		float Ang = D.Phase * 2.f * PI;
		if (D.SwingDeg > 0.f)
		{
			Ang += FMath::DegreesToRadians(D.SwingDeg) * FMath::Sin(ClockS * 2.f * PI / FMath::Max(1.f, FMath::Abs(D.PeriodS)));
		}
		else if (FMath::Abs(D.PeriodS) > 0.1f)
		{
			Ang += ClockS * 2.f * PI / D.PeriodS;
		}
		return Ang;
	}
}

// ------------------------------------------------------------------------------------------------------------------ what the Falcon's displays carry
void UAstraSpaceLife::FillPilotStatus(const FAstraBattleShip& Falcon, FAstraPilotStatus& Out) const
{
	if (!bLaidOut || !Owner || Owner->Ships.Num() == 0)
	{
		return;
	}
	const double Now = WreckClock();
	// ---- the lifepods near her
	{
		TArray<AstraSpace::FBeacon> Bs;
		Wrecks.Beacons(SystemName, Now, Sky, Falcon.Pos, FcPodKm, Bs, true);
		const double Reach = (double)CVarFcReach.GetValueOnGameThread();
		for (const AstraSpace::FBeacon& B : Bs)
		{
			if (Out.Pods.Num() >= FcPodsListed)
			{
				break;
			}
			FAstraPilotStatus::FPod P;
			P.World = Owner->ToWorld(B.Pos);
			P.RangeM = (float)FVector::Dist(B.Pos, Falcon.Pos);
			P.RelSpeedMps = (float)(B.Vel - Falcon.Vel).Size();
			P.Survivors = B.Survivors;
			P.AirMin = (float)(B.AirLeftS / 60.0);
			P.Faction = B.Faction;
			P.Of = FWrecks::BareName(B.Of);
			if (Out.PodInReach < 0 && P.RangeM <= Reach)
			{
				Out.PodInReach = Out.Pods.Num();
			}
			Out.Pods.Add(P);
		}
	}
	if (CVarFcCue.GetValueOnGameThread() == 0 || Owner->bPilotAuto)
	{
		return;                                       // (the deck is flying her in: she is meant to go close)
	}
	// ---- the hull she is flying at, or lies close to
	FFcCue Cue;
	const FVector& Pos = Falcon.Pos;
	const FVector& Vel = Falcon.Vel;
	const AstraSpace::FSolidData& Data = AstraSpace::SolidData();
	// the places (and what turns on them, where the drawing has it now)
	for (const FSpaceLifePlace& Pl : Places)
	{
		if (!Layout.Nodes.IsValidIndex(Pl.Node))
		{
			continue;
		}
		const AstraSpace::FNode& N = Layout.Nodes[Pl.Node];
		if (!N.Spec || N.Spec->Mesh.IsEmpty() || !Data.bLoaded)
		{
			continue;
		}
		const FAstraBattleShip* S = ShipOfPlace(Pl);
		if (!S || !S->bAlive || FVector::Dist(Pos, N.Pos) > (double)N.RadiusM * 1.6 + FcPathMaxM + FcNearM)
		{
			continue;
		}
		const FTransform Body(N.Att, N.Pos);
		if (const FSolids* Sol = Data.Find(N.Spec->Mesh))
		{
			FcSolids(*Sol, Body, FVector::ZeroVector, Pos, Vel, N.Name, Cue);
		}
		for (int32 k = 0; N.Mesh && k < N.Mesh->Parts.Num(); ++k)
		{
			const AstraSpace::FPart& D = N.Mesh->Parts[k];
			if (const FSolids* Part = Data.Find(D.Mesh))
			{
				FcSolids(*Part, FTransform(FQuat(D.Axis, FcPartAngle(D, Clock)), D.Pivot) * Body, FVector::ZeroVector, Pos, Vel, N.Name, Cue);
			}
		}
	}
	// the pieces of the wrecks, where their records have them now
	for (const AstraSpace::FSite& Si : Wrecks.Sites())
	{
		if (Si.System != SystemKey)
		{
			continue;
		}
		for (int32 pi = 0; pi < Si.Pieces.Num(); ++pi)
		{
			const AstraSpace::FPieceRec& Pc = Si.Pieces[pi];
			const FVector Pivot = Sky.ToSystem(FWrecks::PosAt(Pc, Now));
			if (FVector::Dist(Pos, Pivot) > (double)Pc.Radius * 2.2 + FcPathMaxM + FcNearM)
			{
				continue;
			}
			const FQuat Q = Sky.ToSystem(FWrecks::AttAt(Pc, Now));
			const FVector HullVel = Sky.DirToSystem(Pc.Vel);
			const FString Name = FWrecks::PieceName(Si, pi);
			if (const FSolids* Sol = Data.bLoaded ? Data.Find(FWrecks::PieceMesh(Si, pi)) : nullptr)
			{
				FcSolids(*Sol, FTransform(Q, Pivot - Q.RotateVector(Pc.PivotLocal)), HullVel, Pos, Vel, Name, Cue);
			}
			else
			{
				FcBox(Pivot, Q, FVector((double)Pc.Radius * 0.5), HullVel, Pos, Vel, Name, Cue);       // (a mesh with no solids: a box about her pivot, inside her outline)
			}
		}
	}
	// the warships, and the hulks and wrecks that are not pieces of the living space's
	for (const FAstraBattleShip& O : Owner->Ships)
	{
		if (!O.bAlive || O.bPlayer || O.bCraft || O.bFixture || O.bWreck || O.bGhost || O.Id == Falcon.Id || FVector::Dist(Pos, O.Pos) > (double)O.Radius + FcPathMaxM + FcNearM)
		{
			continue;
		}
		FVector Centre = O.Pos;
		FVector Half((double)O.Radius * 0.6);
		if (O.Box.Valid())
		{
			Centre = O.Pos + O.Att.RotateVector(FVector((double)O.Box.Mid, 0.0, 0.0));
			Half = FVector((double)O.Box.Hx, (double)O.Box.Hy, (double)O.Box.Hz);
		}
		FcBox(Centre, O.Att, Half, O.Vel, Pos, Vel, O.bIdentified ? O.Name : O.ContactId, Cue);
	}
	// the Aquila, but not at the mouth of her tube, nor on a course for it (a pilot coming home by eye flies at her bow for the last few kilometres: that is no collision course)
	{
		const FAstraBattleShip& A = Owner->Ships[0];
		const FVector Mouth = Owner->PilotMouth();
		const FVector RelA = Vel - A.Vel;
		const bool bHome = RelA.Size() > 5.0 && FMath::PointDistToSegment(Mouth, Pos, Pos + RelA * (FMath::Min(RelA.Size() * FcLookS, FcPathMaxM) / RelA.Size())) < FcHomeM;
		if (A.bAlive && !bHome && FVector::Dist(Pos, Mouth) > FcMouthM && FVector::Dist(Pos, A.Pos) <= (double)A.Radius + FcPathMaxM + FcNearM)
		{
			FVector Centre = A.Pos;
			FVector Half((double)A.Radius * 0.5);
			if (A.Box.Valid())
			{
				Centre = A.Pos + A.Att.RotateVector(FVector((double)A.Box.Mid, 0.0, 0.0));
				Half = FVector((double)A.Box.Hx, (double)A.Box.Hy, (double)A.Box.Hz);
			}
			FcBox(Centre, A.Att, Half, A.Vel, Pos, Vel, TEXT("the Aquila"), Cue);
		}
	}
	Out.CueLevel = Cue.Level;
	Out.CueWhat = Cue.What;
	Out.CueRangeM = (float)Cue.RangeM;
	Out.CueTtcS = (float)Cue.TtcS;
}

// ------------------------------------------------------------------------------------------------------------------ the pickup
double UAstraSpaceLife::PodReachM()
{
	return (double)CVarFcReach.GetValueOnGameThread();
}

AstraSpace::FRescued UAstraSpaceLife::PilotRescue(const FAstraBattleShip& Falcon)
{
	return RescueTake(Falcon.Pos, PodReachM(), TEXT("Eagle"));
}

AstraSpace::FRescued UAstraSpaceLife::PilotRescue(int32 PilotedShipId)
{
	const FAstraBattleShip* S = Owner && PilotedShipId >= 0 ? Owner->FindById(PilotedShipId) : nullptr;
	return S && S->bAlive ? PilotRescue(*S) : AstraSpace::FRescued();
}

// ------------------------------------------------------------------------------------------------------------------ the bench
bool UAstraSpaceLife::DebugFalcon(FString& OutDetail)
{
	const AstraSpace::FSolidData& Data = AstraSpace::SolidData();
	if (!bLaidOut || !Owner || Owner->Ships.Num() == 0)
	{
		OutDetail = TEXT("no living space laid out here");
		return false;
	}
	int32 Failed = 0, Checked = 0;
	FString Lines, Done;
	const auto Expect = [&](bool bOk, const FString& What)
	{
		++Checked;
		if (!bOk)
		{
			++Failed;
			Lines += FString::Printf(TEXT("FAIL %s; "), *What);
		}
	};
	// a Falcon that is nowhere in the plot: the status asks only where she is and how she goes
	FAstraBattleShip Fk;
	Fk.Id = -77;
	Fk.bAlive = true;
	Fk.bCraft = true;
	Fk.bPiloted = true;
	const auto Ask = [&](const FVector& At, const FVector& Going) -> FAstraPilotStatus
	{
		Fk.Pos = At;
		Fk.Vel = Going;
		FAstraPilotStatus St;
		FillPilotStatus(Fk, St);
		return St;
	};
	const double Now = WreckClock();
	if (CVarFcCue.GetValueOnGameThread() == 0)
	{
		Expect(false, TEXT("the cue is off (astra.space.falcon.cue 0)"));
	}
	// ---- a hull of solid cells, flown at from above and lain beside: the topmost cell of the mesh is the mark
	const auto TestSolids = [&](const FSolids& Sol, const FTransform& ToSys, const FVector& HullVel, const FString& Name, const TCHAR* Tag)
	{
		int32 BX = -1, BY = -1, BZ = -1;
		for (int32 X = 0; X < Sol.NX; X += 2)
		{
			for (int32 Y = 0; Y < Sol.NY; Y += 2)
			{
				for (int32 Z = Sol.NZ - 1; Z >= 0; --Z)
				{
					if (Sol.Bits[(X * Sol.NY + Y) * Sol.NZ + Z])
					{
						if (Z > BZ)
						{
							BX = X;
							BY = Y;
							BZ = Z;
						}
						break;
					}
				}
			}
		}
		if (BZ < 0)
		{
			return;
		}
		const FVector Top = Sol.Origin + FVector(BX + 0.5, BY + 0.5, BZ + 1.0) * (double)Sol.Cell;                // the top of that column, in the mesh frame
		const FVector Start = ToSys.TransformPosition(Top + FVector(0.0, 0.0, 1500.0));
		const FVector Down = ToSys.TransformVector(FVector(0.0, 0.0, -1.0));
		// flown at it at 400 m/s from 1.5 km: a course into a hull, in 3.75 s (a half cell of sampling on top)
		FAstraPilotStatus St = Ask(Start, HullVel + Down * 400.0);
		Expect(St.CueLevel == 2 && St.CueWhat == Name, FString::Printf(TEXT("%s: flown at from 1.5 km, the word is level %d of %s"), *Name, (int32)St.CueLevel, *St.CueWhat));
		Expect(FMath::Abs(St.CueTtcS - 3.75f) < 0.1f && FMath::Abs(St.CueRangeM - 1500.f) < Sol.Cell + 5.f, FString::Printf(TEXT("%s: the course is %.0f m, %.2f s away (1500 m, 3.75 s)"), *Name, St.CueRangeM, St.CueTtcS));
		// lain 100 m above it, at rest against it: close, not on a course
		St = Ask(ToSys.TransformPosition(Top + FVector(0.0, 0.0, 100.0)), HullVel);
		Expect(St.CueLevel == 1 && St.CueWhat == Name && St.CueRangeM > 0.f && St.CueRangeM <= 100.f + 1.5f * Sol.Cell, FString::Printf(TEXT("%s: lain 100 m above her, the word is level %d, %.0f m"), *Name, (int32)St.CueLevel, St.CueRangeM));
		// far off, nothing (and the same path flown AWAY from her)
		St = Ask(ToSys.TransformPosition(Top + FVector(0.0, 0.0, 30000.0)), HullVel + Down * 400.0);
		Expect(St.CueLevel == 0, FString::Printf(TEXT("%s: 30 km off, the word is level %d of %s"), *Name, (int32)St.CueLevel, *St.CueWhat));
		St = Ask(Start, HullVel - Down * 400.0);
		Expect(St.CueLevel == 0, FString::Printf(TEXT("%s: flown away from at 400 m/s the word is level %d of %s"), *Name, (int32)St.CueLevel, *St.CueWhat));
		Done += (Done.IsEmpty() ? FString() : FString(TEXT(", "))) + Tag + TEXT(" ") + Name;
	};
	for (const FSpaceLifePlace& Pl : Places)
	{
		if (!Layout.Nodes.IsValidIndex(Pl.Node) || !Layout.Nodes[Pl.Node].Spec)
		{
			continue;
		}
		const AstraSpace::FNode& N = Layout.Nodes[Pl.Node];
		const FAstraBattleShip* S = ShipOfPlace(Pl);
		if (!S || !S->bAlive)
		{
			continue;
		}
		if (const FSolids* Sol = Data.bLoaded ? Data.Find(N.Spec->Mesh) : nullptr)
		{
			TestSolids(*Sol, FTransform(N.Att, N.Pos), FVector::ZeroVector, N.Name, TEXT("place"));
			break;                                                       // (one place is enough: the same code serves them all)
		}
	}
	// ---- a piece of a wreck: the same, in her own frame and at her own pace
	int32 PiecesTried = 0;
	for (const AstraSpace::FSite& Si : Wrecks.Sites())
	{
		if (Si.System != SystemKey || PiecesTried >= 2)
		{
			continue;
		}
		for (int32 pi = 0; pi < Si.Pieces.Num() && PiecesTried < 2; ++pi)
		{
			const AstraSpace::FPieceRec& Pc = Si.Pieces[pi];
			const FSolids* Sol = Data.bLoaded ? Data.Find(FWrecks::PieceMesh(Si, pi)) : nullptr;
			if (!Sol)
			{
				continue;
			}
			const FQuat Q = Sky.ToSystem(FWrecks::AttAt(Pc, Now));
			const FVector Pivot = Sky.ToSystem(FWrecks::PosAt(Pc, Now));
			TestSolids(*Sol, FTransform(Q, Pivot - Q.RotateVector(Pc.PivotLocal)), Sky.DirToSystem(Pc.Vel), FWrecks::PieceName(Si, pi), TEXT("piece"));
			++PiecesTried;
		}
	}
	// ---- a ship: flown at along her length, and lain 100 m off her flank. The Falcon is put where no other hull is near, so that the answer can only be hers
	int32 ShipsTried = 0;
	for (const FAstraBattleShip& O : Owner->Ships)
	{
		if (ShipsTried >= 1)
		{
			break;
		}
		if (!O.bAlive || O.bPlayer || O.bCraft || O.bFixture || O.bWreck || O.bGhost || !O.Box.Valid())
		{
			continue;
		}
		const FVector Centre = O.Pos + O.Att.RotateVector(FVector((double)O.Box.Mid, 0.0, 0.0));
		bool bPlaced = false;
		for (int32 Dir = 0; Dir < 6 && !bPlaced; ++Dir)
		{
			const FVector Axis = Dir == 0 ? FVector::ForwardVector : (Dir == 1 ? -FVector::ForwardVector : (Dir == 2 ? FVector::RightVector : (Dir == 3 ? -FVector::RightVector : (Dir == 4 ? FVector::UpVector : -FVector::UpVector))));
			const double HalfAlong = FMath::Abs(Axis.X) * O.Box.Hx + FMath::Abs(Axis.Y) * O.Box.Hy + FMath::Abs(Axis.Z) * O.Box.Hz;
			const FVector Dir3 = O.Att.RotateVector(Axis);
			const FVector Far = Centre + Dir3 * (HalfAlong + 1000.0);
			const FVector Near = Centre + Dir3 * (HalfAlong + 100.0);
			bool bClear = true;
			for (const FAstraBattleShip& X : Owner->Ships)
			{
				if (&X != &O && X.bAlive && !X.bCraft && !X.bGhost && (FVector::Dist(X.Pos, Far) < (double)X.Radius + 3000.0 || FVector::Dist(X.Pos, Near) < (double)X.Radius + 3000.0))
				{
					bClear = false;
					break;
				}
			}
			for (const AstraSpace::FSite& Si : Wrecks.Sites())
			{
				for (const AstraSpace::FPieceRec& Pc : Si.Pieces)
				{
					bClear = bClear && FVector::Dist(Sky.ToSystem(FWrecks::PosAt(Pc, Now)), Far) > (double)Pc.Radius * 2.2 + 5000.0;
				}
			}
			for (const FSpaceLifePlace& Pl : Places)
			{
				bClear = bClear && (!Layout.Nodes.IsValidIndex(Pl.Node) || FVector::Dist(Layout.Nodes[Pl.Node].Pos, Far) > (double)Layout.Nodes[Pl.Node].RadiusM * 1.6 + 5000.0);
			}
			if (!bClear)
			{
				continue;
			}
			bPlaced = true;
			++ShipsTried;
			const FString Name = O.bIdentified ? O.Name : O.ContactId;
			// 1 km off along her axis at 400 m/s against her: a course into her box shrunk to 0.9 of its half length, 2.5 s and a little
			const double ToFace = 1000.0 + (1.0 - FcCrashK) * HalfAlong;
			FAstraPilotStatus St = Ask(Far, O.Vel - Dir3 * 400.0);
			Expect(St.CueLevel == 2 && St.CueWhat == Name, FString::Printf(TEXT("%s: flown at from 1 km, the word is level %d of %s"), *Name, (int32)St.CueLevel, *St.CueWhat));
			Expect(FMath::Abs(St.CueTtcS - (float)(ToFace / 400.0)) < 0.05f, FString::Printf(TEXT("%s: the course is %.2f s away (%.2f)"), *Name, St.CueTtcS, ToFace / 400.0));
			St = Ask(Near, O.Vel);
			Expect(St.CueLevel == 1 && St.CueWhat == Name && FMath::Abs(St.CueRangeM - 100.f) < 1.f, FString::Printf(TEXT("%s: lain 100 m off, the word is level %d, %.1f m"), *Name, (int32)St.CueLevel, St.CueRangeM));
			Done += (Done.IsEmpty() ? FString() : FString(TEXT(", "))) + TEXT("ship ") + Name;
		}
	}
	// ---- empty space: nothing, and the cost of asking near the Aquila (the war's busiest place)
	{
		const FVector Void = Owner->Ships[0].Pos + FVector(0.0, 0.0, 400.0 * FcKm);
		const FAstraPilotStatus St = Ask(Void, FVector(300.0, 0.0, 0.0));
		Expect(St.CueLevel == 0 && St.Pods.Num() == 0 && St.PodInReach < 0, FString::Printf(TEXT("400 km above the Aquila: level %d, %d pods"), (int32)St.CueLevel, St.Pods.Num()));
		const FVector Near = Owner->Ships[0].Pos + FVector(0.0, 2.0 * FcKm, 0.0);
		const int32 N = 2000;
		const double T0 = FPlatformTime::Seconds();
		for (int32 i = 0; i < N; ++i)
		{
			Ask(Near, FVector(200.0, 0.0, 0.0));
		}
		const double Us = (FPlatformTime::Seconds() - T0) * 1.0e6 / N;
		Done += FString::Printf(TEXT("%s%.1f us a status"), Done.IsEmpty() ? TEXT("") : TEXT(", "), Us);
		Expect(Us < 100.0, FString::Printf(TEXT("a status costs %.1f us"), Us));
	}
	// ---- the lifepods: listed from afar, in reach near, taken once by the Falcon that is there and never by the one that is not
	{
		TArray<AstraSpace::FBeacon> Bs;
		Wrecks.Beacons(SystemName, Now, Sky, FVector::ZeroVector, 0.0, Bs, true);
		if (Bs.Num() > 0)
		{
			const AstraSpace::FBeacon B = Bs[0];
			const double Reach = (double)CVarFcReach.GetValueOnGameThread();
			FAstraPilotStatus St = Ask(B.Pos + FVector(5.0 * FcKm, 0.0, 0.0), B.Vel);
			Expect(St.Pods.Num() >= 1 && St.PodInReach < 0 && FMath::Abs(St.Pods[0].RangeM - 5.0f * (float)FcKm) < 200.f, FString::Printf(TEXT("a pod seen from 5 km: %d listed, in reach %d"), St.Pods.Num(), St.PodInReach));
			Fk.Pos = B.Pos + FVector(5.0 * FcKm, 0.0, 0.0);
			Expect(PilotRescue(Fk).Pods == 0, TEXT("a Falcon 5 km from a pod took it aboard"));
			St = Ask(B.Pos + FVector(0.5 * Reach, 0.0, 0.0), B.Vel);
			Expect(St.PodInReach == 0 && St.Pods.Num() >= 1 && St.Pods[0].Survivors == B.Survivors && !St.Pods[0].Of.IsEmpty() && !St.Pods[0].Of.Contains(TEXT("(")),
			       FString::Printf(TEXT("a pod in reach: in reach %d, %d survivors of '%s'"), St.PodInReach, St.Pods.Num() ? St.Pods[0].Survivors : -1, St.Pods.Num() ? *St.Pods[0].Of : TEXT("")));
			Fk.Pos = B.Pos + FVector(0.5 * Reach, 0.0, 0.0);
			const AstraSpace::FRescued R = PilotRescue(Fk);
			Expect(R.Pods >= 1 && R.Survivors >= B.Survivors, FString::Printf(TEXT("the pickup took %d pods and %d people (a pod of %d)"), R.Pods, R.Survivors, B.Survivors));
			Expect(PilotRescue(Fk).Pods == 0, TEXT("the same pod was taken twice"));
			St = Ask(B.Pos + FVector(0.5 * Reach, 0.0, 0.0), B.Vel);
			Expect(St.PodInReach < 0 || St.Pods[St.PodInReach].Survivors != B.Survivors || FVector::Dist(St.Pods[St.PodInReach].World, Owner->ToWorld(B.Pos)) > 1.0, TEXT("the pod taken is still listed in reach"));
			Done += TEXT(", a lifepod");
		}
	}
	OutDetail = FString::Printf(TEXT("%d checks over %s: %s"), Checked, Done.IsEmpty() ? TEXT("(nothing near to fly at: only the empty-space ones)") : *Done, Failed ? *Lines : TEXT("the Falcon is told what is near her, and takes the pod that is in her reach"));
	return Failed == 0 && Checked > 0;
}

// ------------------------------------------------------------------------------------------------------------------ the console
namespace
{
	FAutoConsoleCommandWithWorld CmdSpaceFalconTest(TEXT("astra.space.falcon.test"), TEXT("The Captain's Falcon's word of what is near her, in this world: flown at a place, a wreck's piece, a ship; lain beside them; the lifepods listed, in reach, taken once"),
		FConsoleCommandWithWorldDelegate::CreateLambda([](UWorld* W)
		{
			UAstraBattleSubsystem* B = W ? W->GetSubsystem<UAstraBattleSubsystem>() : nullptr;
			UAstraSpaceLife* S = B ? B->GetSpace() : nullptr;
			if (!S) { UE_LOG(LogASTRA, Display, TEXT("[Space] none in this world")); return; }
			FString Detail;
			const bool bOk = S->DebugFalcon(Detail);
			UE_LOG(LogASTRA, Display, TEXT("[Space] falcon: %s %s"), *Detail, bOk ? TEXT("FALCON_OK") : TEXT("FALCON_FAILED"));
		}));
}
