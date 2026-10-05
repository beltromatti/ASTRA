// ASTRA — gunnery (docs/GUERRA.md, BATTAGLIA-3): how true a ship's guns shoot at the range a fight is really fought at.
//
// A railgun slug flies at 12 km/s: at 30 km it is three seconds on its way, and nothing steers it. So a shot is aimed in two steps:
//   1. the INTERCEPT: where the slug and the target meet if the target holds its velocity, solved in the shooter's own frame (the slug carries the shooter's
//      velocity too: a ship that fires across its own motion must lead for it, as the fire control of a real ship does);
//   2. the ERROR: what the fire control cannot know. It tracks its target with an angular error (milliradians: the class's sensors, worse with a damaged sensor
//      suite or a jammer on the target's side) and the miss that makes grows with the range; the error wanders (it settles on a target in a few seconds, drifts, and
//      starts again from a worse place on a new one), so a ship's salvos straddle together rather than scatter apart; and the guns themselves scatter a little.
// Where the slug really goes after that is plain physics against the hull's own box (HullSweep): a ship that shows its beam to the guns is a bigger target than one that
// shows its bow, a small ship is harder than a big one, and the accuracy falls with the range without a number saying so. Lasers are light: no flight, but the same
// tracking error against the box, and what they carry spreads with the range.
// The AI weighs a range by what its guns will land there (ExpectedHitFraction), and keeps its shots out of its own side's ships (LineOfFireFouled).

#include "AstraBattleSubsystem.h"
#include "AstraWarClasses.h"
#include "AstraShipSubsystem.h"
#include "Engine/World.h"
#include <cmath>

namespace
{
	/** A normal deviate (Box-Muller): the fire control's error is a Gaussian across the line of sight. */
	double WarGauss()
	{
		const double U1 = FMath::Max(1e-7, (double)FMath::FRand()), U2 = FMath::FRand();
		return FMath::Sqrt(-2.0 * FMath::Loge(U1)) * FMath::Cos(2.0 * UE_DOUBLE_PI * U2);
	}

	/** Two axes across the line of sight (one level, one up through it): the plane the fire control's error lives in. */
	void WarAcrossAxes(const FVector& Los, FVector& OutE1, FVector& OutE2)
	{
		OutE1 = FVector::CrossProduct(Los, FVector::UpVector);
		if (OutE1.SizeSquared() < 1e-6)
		{
			OutE1 = FVector::CrossProduct(Los, FVector::ForwardVector);
		}
		OutE1.Normalize();
		OutE2 = FVector::CrossProduct(Los, OutE1).GetSafeNormal();
	}
}

bool UAstraBattleSubsystem::SolveIntercept(const FAstraBattleShip& From, const FVector& TargetPos, const FVector& TargetVel, double Speed, FVector& OutDir, double& OutT) const
{
	// in the shooter's own frame the slug goes at Speed along its aim and the target moves with the relative velocity: |Rel + RelVel t| = Speed t
	const FVector Rel = TargetPos - From.Pos;
	const FVector RelVel = TargetVel - From.Vel;
	const double A = Speed * Speed - RelVel.SizeSquared();
	const double B = 2.0 * FVector::DotProduct(Rel, RelVel);
	const double C = Rel.SizeSquared();
	if (A < 1.0 || C < 1.0)
	{
		OutDir = Rel.GetSafeNormal();
		OutT = Rel.Size() / FMath::Max(Speed, 1.0);
		return false;                                                    // (nothing flies that fast; or it is on top of us)
	}
	OutT = (B + FMath::Sqrt(B * B + 4.0 * A * C)) / (2.0 * A);
	OutDir = (Rel + RelVel * OutT).GetSafeNormal();
	return true;
}

void UAstraBattleSubsystem::FireSolutionOf(const FAstraBattleShip& From, const FAstraBattleShip& To, FVector& OutPos, FVector& OutVel) const
{
	// what the shooter's side holds of the target: the truth while its track is firm, a dead reckoning from the last sighting when it was lost a moment ago
	const int32 Me = AstraSideIdx(From.Side);
	FVector Centre = To.Pos;
	OutVel = To.Vel;
	if (Me >= 0 && !From.bPlayer && AstraSideIdx(To.Side) == 1 - Me)
	{
		const float Age = Time - To.SeenT[Me];
		if (Age > 0.6f && Age < 25.f)
		{
			Centre = To.SeenPos[Me] + To.SeenVel[Me] * Age;
			OutVel = To.SeenVel[Me];
		}
	}
	// the gunner aims at the middle of the hull: the box's centre, which is not quite the mesh's origin
	OutPos = To.Box.Valid() ? Centre + To.Att.RotateVector(FVector(To.Box.Mid, 0.0, 0.0)) : Centre;
}

float UAstraBattleSubsystem::TrackSigmaM(const FAstraBattleShip& From, double RangeM) const
{
	static AstraWar::FTuneVar KTrack(TEXT("track_scale"), 1.f);
	float Mrad = From.TrackMrad * KTrack.Get();
	if (From.Dmg.bModel)
	{
		Mrad /= FMath::Clamp(SensorFactor(From), 0.34f, 1.f);            // a hurt sensor suite tracks worse (up to three times)
	}
	if (From.bPlayer)
	{
		if (const UAstraShipSubsystem* Ship = GetWorld() ? GetWorld()->GetSubsystem<UAstraShipSubsystem>() : nullptr)
		{
			Mrad /= FMath::Clamp(0.55f + 0.45f * Ship->PowerFactor(TEXT("sensors")), 0.4f, 1.3f);   // the Aquila's sensor power
		}
	}
	if (From.bJammed)
	{
		Mrad *= 2.f;                                                       // an EW drone on its fire control
	}
	return Mrad * 1e-3f * (float)RangeM;
}

void UAstraBattleSubsystem::TickAimError(FAstraBattleShip& S, const FAstraBattleShip* T, float Dt)
{
	if (!T || !T->bAlive)
	{
		S.AimTarget = -1;
		S.AimErr = FVector::ZeroVector;
		S.AimAge = 0.f;
		return;
	}
	const FVector Rel = T->Pos - S.Pos;
	const double R = Rel.Size();
	const FVector Los = Rel / FMath::Max(R, 1.0);
	FVector E1, E2;
	WarAcrossAxes(Los, E1, E2);
	// the tracking settles on a target in a few seconds: a new one is tracked at first two and a half times worse
	const double Settle = 1.0 + 1.5 * FMath::Exp(-S.AimAge / 4.0);
	const double Sigma = TrackSigmaM(S, R) * Settle;
	if (S.AimTarget != T->Id)
	{
		S.AimTarget = T->Id;
		S.AimAge = 0.f;
		S.AimErr = (E1 * WarGauss() + E2 * WarGauss()) * (TrackSigmaM(S, R) * 2.5);        // the first solution on a new target: far out
	}
	else
	{
		// a wander that keeps its standard deviation at the range's: Ornstein-Uhlenbeck, forgetting in about five seconds
		const double K = FMath::Exp(-(double)Dt / 5.0);
		const double Sd = Sigma * FMath::Sqrt(FMath::Max(0.0, 1.0 - K * K));
		FVector Err = S.AimErr - Los * FVector::DotProduct(S.AimErr, Los);
		S.AimErr = Err * K + E1 * (WarGauss() * Sd) + E2 * (WarGauss() * Sd);
		S.AimAge += Dt;
	}
}

bool UAstraBattleSubsystem::AimShot(FAstraBattleShip& From, const FAstraBattleShip& To, double Speed, float ExtraSpread, FVector& OutDir, double& OutT)
{
	FVector TPos, TVel;
	FireSolutionOf(From, To, TPos, TVel);
	FVector Clean;
	double T0 = 0.0;
	SolveIntercept(From, TPos, TVel, Speed, Clean, T0);
	const FVector Rel = TPos - From.Pos;
	const double R = Rel.Size();
	const FVector Los = Rel / FMath::Max(R, 1.0);
	FVector X = Rel + (TVel - From.Vel) * T0;                               // where they meet, from the shooter
	// what the fire control gets wrong, and what the guns scatter
	FVector E1, E2;
	WarAcrossAxes(Los, E1, E2);
	FVector Err = (From.AimTarget == To.Id) ? From.AimErr - Los * FVector::DotProduct(From.AimErr, Los) : FVector::ZeroVector;
	if (From.AimTarget != To.Id)
	{
		Err = (E1 * WarGauss() + E2 * WarGauss()) * TrackSigmaM(From, R) * 2.0;     // (fired at something it was not tracking: a snap shot)
	}
	const double Scatter = R * (From.DispMrad * 1e-3 + ExtraSpread);
	Err += E1 * (WarGauss() * Scatter) + E2 * (WarGauss() * Scatter);
	X += Err;
	const double Len = FMath::Max(X.Size(), 1.0);
	OutDir = X / Len;
	OutT = Len / FMath::Max(Speed, 1.0);
	return true;
}

float UAstraBattleSubsystem::ExpectedHitFraction(const FAstraBattleShip& From, const FAstraBattleShip& To, double RangeM) const
{
	const double Sd = FMath::Max(1.0, (double)FMath::Sqrt(FMath::Square(TrackSigmaM(From, RangeM)) + FMath::Square(RangeM * From.DispMrad * 1e-3)));
	const double Rt2 = 1.0 / (Sd * UE_DOUBLE_SQRT_2);
	if (!To.Box.Valid())
	{
		return (float)(1.0 - FMath::Exp(-FMath::Square((double)To.Radius) / (2.0 * Sd * Sd)));
	}
	// the cross-section the target shows to the guns: the half-extents of its box seen along the line of fire, level and up through it
	const FVector Los = (To.Pos - From.Pos).GetSafeNormal();
	FVector E1, E2;
	WarAcrossAxes(Los, E1, E2);
	const FVector Ax = To.Att.GetForwardVector(), Ay = To.Att.GetRightVector(), Az = To.Att.GetUpVector();
	auto Half = [&](const FVector& E)
	{
		return FMath::Abs(FVector::DotProduct(E, Ax)) * To.Box.Hx + FMath::Abs(FVector::DotProduct(E, Ay)) * To.Box.Hy + FMath::Abs(FVector::DotProduct(E, Az)) * To.Box.Hz;
	};
	return (float)(std::erf(Half(E1) * Rt2) * std::erf(Half(E2) * Rt2));
}

float UAstraBattleSubsystem::ReferenceHitFraction(const FAstraBattleShip& From, double RangeM) const
{
	// a ship of the middle size seen three-quarters on (100 m across, 60 m up): what a range is worth when the target is not known yet
	const double Sd = FMath::Max(1.0, (double)FMath::Sqrt(FMath::Square(TrackSigmaM(From, RangeM)) + FMath::Square(RangeM * From.DispMrad * 1e-3)));
	const double Rt2 = 1.0 / (Sd * UE_DOUBLE_SQRT_2);
	return (float)(std::erf(100.0 * Rt2) * std::erf(60.0 * Rt2));
}

bool UAstraBattleSubsystem::LineOfFireFouled(const FAstraBattleShip& From, const FVector& AimPos) const
{
	const int32 Me = AstraSideIdx(From.Side);
	if (Me < 0)
	{
		return false;
	}
	const FVector Seg = AimPos - From.Pos;
	const double L2 = Seg.SizeSquared();
	if (L2 < 1.0)
	{
		return false;
	}
	for (const int32 I : CapIdx)
	{
		const FAstraBattleShip& F = Ships[I];
		if (F.Id == From.Id || AstraSideIdx(F.Side) != Me || !F.bAlive)
		{
			continue;
		}
		const double U = FVector::DotProduct(F.Pos - From.Pos, Seg) / L2;       // how far along the line (0 the muzzle, 1 the aim point)
		if (U < 0.0 || U > 1.0)
		{
			continue;
		}
		const double Off2 = FVector::DistSquared(F.Pos, From.Pos + Seg * U);
		const double Clear = F.Radius * 0.85 + 40.0;
		if (Off2 < Clear * Clear)
		{
			return true;
		}
	}
	return false;
}

FString UAstraBattleSubsystem::AdviseTarget(const FString& Current, bool bOnlyFiringAtUs, double MaxKm) const
{
	if (Ships.Num() == 0 || !Ships[0].bAlive)
	{
		return FString();
	}
	const FAstraBattleShip& P = Ships[0];
	const double RailR = P.RailRange > 0.f ? (double)P.RailRange : 8000.0;
	const double MissR = FMath::Max((double)P.MissileRange, RailR);
	const double Cap = MaxKm > 0.0 ? MaxKm * 1000.0 : MissR;
	// the ships the fleet's groups beside her are concentrating on: fire joined to theirs is worth more than fire on its own
	TArray<int32, TInlineAllocator<8>> Focus;
	for (const FAstraBattleGroup& G : Groups)
	{
		if (G.Side == EAstraSide::Astra && G.State == EAstraGroupState::Engage && G.FocusTarget >= 0 && FVector::DistSquared(G.Centroid, P.Pos) < FMath::Square(40000.0))
		{
			Focus.AddUnique(G.FocusTarget);
		}
	}
	const FAstraBattleShip* Best = nullptr;
	double BestScore = -1.0;
	for (const FAstraBattleShip& X : Ships)
	{
		if (!X.bAlive || X.bCraft || X.bGhost || X.bDisabled || X.bDerelict || X.bWreck || X.bFixture || X.Side != EAstraSide::Mandate || X.ContactId.IsEmpty())
		{
			continue;
		}
		FVector Seen;
		if (!OnPlot(0, X, Seen) || (X.bFog && X.Track < 2))
		{
			continue;                                                          // (no firm track: no firing solution)
		}
		const double D = FVector::Dist(P.Pos, X.Pos);
		if (D > Cap)
		{
			continue;
		}
		const bool bFiring = X.TargetId == P.Id && !X.bHoldFire;
		if (bOnlyFiringAtUs && !bFiring)
		{
			continue;
		}
		const float HullF = X.Hull / FMath::Max(1.f, X.HullMax);
		float ShieldF = 0.5f;
		if (X.Dmg.bModel && X.Dmg.Pool > 0.f)
		{
			const int32 Face = AstraFacingOf(X.Att.UnrotateVector((P.Pos - X.Pos).GetSafeNormal()));      // the face it shows her
			ShieldF = X.Dmg.SectorMax[Face] > 0.f ? X.Dmg.Sector[Face] / X.Dmg.SectorMax[Face] : 0.f;
		}
		const double Vuln = FMath::Clamp(1.15 - 0.55 * HullF - 0.35 * ShieldF, 0.2, 1.3);
		const double Reach = D < RailR ? 1.0 : (D < MissR ? 0.35 : 0.1);       // (the rails are her weapon: what only the cells reach counts for little, what neither does for less)
		const double Hit = P.Dmg.bModel ? (double)ExpectedHitFraction(P, X, D) : 0.5;
		double Score = (double)X.CombatValue * (X.bLeader ? 1.15 : 1.0) * (0.5 + Vuln) * (0.25 + Hit) * Reach * (bFiring ? 1.3 : 1.0) * (Focus.Contains(X.Id) ? 1.4 : 1.0)
		             * (X.ContactId == Current ? 1.5 : 1.0);
		if (X.bFleeing)
		{
			Score *= HullF < 0.35f ? 1.2 : 0.7;                                // a ship breaking off is worth less than one coming on, unless it is nearly done
		}
		if (Score > BestScore)
		{
			BestScore = Score;
			Best = &X;
		}
	}
	return Best ? Best->ContactId : FString();
}

int32 UAstraBattleSubsystem::MissilesToSaturate(const FString& ContactId) const
{
	const FAstraBattleShip* X = ContactId.IsEmpty() ? nullptr : FindByContact(ContactId);
	if (!X || X->bCraft || (X->bFog ? !X->bClassified : !X->bIdentified))
	{
		return 6;
	}
	const float Channels = (float)X->PDChannels * (X->Dmg.bModel ? X->Dmg.Sys[AstraWar::SysPointDefence] : 1.f);
	return FMath::Clamp(FMath::CeilToInt(2.f + 1.6f * Channels), 3, 8);
}
