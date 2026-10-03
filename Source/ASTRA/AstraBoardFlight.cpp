// ASTRA — ABBORDAGGI-2: the flight of an assault craft (CraftKind 3), a member of UAstraBattleSubsystem called from TickCraft (AstraWarCraft.cpp). The rules and the data are in
// AstraBoardCraft.h / AstraBoardCraft.cpp.
//
//   leave      out of the boat bay of the carrier, along the bay's axis, clear of the hull
//   cross      to a point in front of the hatch it was given (the target's frame: it follows her if she turns), straight through whatever point defence the target has: it does not keep
//              out of an envelope, it has to pass it; round the target's hull, not through it
//   approach   down the hatch's axis, slowing, lining up (nose to the hull, the hull's up above it); the shield on that face must be down (or the ship dead): else it waits off the hull
//   latch      touching: it moves with the hull as a part of it; after the kind's time the way in is cut and the men go through (the host's event)
//   depart     the fight is over: it lets go, backs off, and goes home to the bay (the carrier's: it comes to the mouth along its axis, like a landing)

#include "AstraBattleSubsystem.h"
#include "AstraBoardCraft.h"
#include "ASTRA.h"

using namespace AstraBoardCraft;

namespace
{
	constexpr double BfHullMarginM = 70.0;        // how far off a hull it stays when it is not going to it
	constexpr float BfHoldGiveUpS = 18.f;         // how long it waits off a shield before it turns back
	constexpr float BfTransitLimitS = 300.f;
	constexpr float BfApproachLimitS = 110.f;

	/** The signed distance from a point of the target's frame to its hull (a box of the class's measures, a sphere without one): negative inside. */
	double BfHullSd(const FAstraBattleShip& T, const FVector& P, FVector* OutOut = nullptr)
	{
		if (T.Box.Valid())
		{
			const FVector Q = P - FVector(T.Box.Mid, 0.0, 0.0);
			const FVector D(FMath::Abs(Q.X) - T.Box.Hx, FMath::Abs(Q.Y) - T.Box.Hy, FMath::Abs(Q.Z) - T.Box.Hz);
			const FVector Pos(FMath::Max(D.X, 0.0), FMath::Max(D.Y, 0.0), FMath::Max(D.Z, 0.0));
			const double Out = Pos.Size();
			const double Sd = Out + FMath::Min(FMath::Max(D.X, FMath::Max(D.Y, D.Z)), 0.0);
			if (OutOut)
			{
				if (Out > 1.0e-6)
				{
					*OutOut = FVector(Pos.X * (Q.X < 0.0 ? -1.0 : 1.0), Pos.Y * (Q.Y < 0.0 ? -1.0 : 1.0), Pos.Z * (Q.Z < 0.0 ? -1.0 : 1.0)) / Out;
				}
				else if (D.X >= D.Y && D.X >= D.Z)
				{
					*OutOut = FVector(Q.X < 0.0 ? -1.0 : 1.0, 0.0, 0.0);
				}
				else
				{
					*OutOut = D.Y >= D.Z ? FVector(0.0, Q.Y < 0.0 ? -1.0 : 1.0, 0.0) : FVector(0.0, 0.0, Q.Z < 0.0 ? -1.0 : 1.0);
				}
			}
			return Sd;
		}
		const double R = FMath::Max(10.0, (double)T.Radius);
		const double D = P.Size();
		if (OutOut)
		{
			*OutOut = D > 1.0e-6 ? P / D : FVector(0.0, 1.0, 0.0);
		}
		return D - R;
	}

	/** The way round a hull: the wanted velocity of a craft, with what takes it into the hull taken out and a push (and a slide, to one side) out of the margin round it. */
	FVector BfWall(const FAstraBattleShip& T, const FVector& CraftPos, const FVector& Want, float Cruise, float Side)
	{
		const FVector Local = T.Att.UnrotateVector(CraftPos - T.Pos);
		FVector OutDir;
		const double Sd = BfHullSd(T, Local, &OutDir);
		if (Sd >= BfHullMarginM * 2.0)
		{
			return Want;
		}
		const FVector N = T.Att.RotateVector(OutDir).GetSafeNormal();
		FVector V = Want;
		const FVector Rel = V - T.Vel;
		const double In = FVector::DotProduct(Rel, N);
		if (In < 0.0)
		{
			V -= N * In;                                                  // no speed into the hull: it slides along it
		}
		const double Ease = FMath::Clamp(1.0 - Sd / (BfHullMarginM * 2.0), 0.0, 1.0);
		V += N * Ease * 160.0;
		// head-on to a face: slide to one side (the way it picked at launch), not to a stand-still
		const FVector Tan = (Want - N * FVector::DotProduct(Want, N));
		if (Tan.Size() < 0.25 * Cruise)
		{
			const FVector Across = FVector::CrossProduct(N, T.Att.GetUpVector()).GetSafeNormal();
			V += (Across.IsNearlyZero() ? T.Att.GetForwardVector() : Across) * (Side >= 0.f ? 1.0 : -1.0) * Cruise * 0.45 * Ease;
		}
		return V;
	}

	FQuat BfFace(const FVector& Forward, const FVector& UpHint)
	{
		const FVector F = Forward.GetSafeNormal();
		const FVector Up = UpHint - F * FVector::DotProduct(UpHint, F);
		if (Up.SizeSquared() < 0.01)
		{
			return FRotationMatrix::MakeFromX(F).ToQuat();
		}
		return FRotationMatrix::MakeFromXZ(F, Up.GetSafeNormal()).ToQuat();
	}
}

void UAstraBattleSubsystem::TickBoardingCraft(FAstraBattleShip& S, float Dt)
{
	FFlight& B = S.Board;
	const FKind* K = KindByKey(B.Kind);
	if (!K)
	{
		RemoveBoardingCraft(S);
		return;
	}
	B.T += Dt;
	B.AliveT += Dt;
	FAstraBattleShip* T = FindById(B.TargetId);
	FAstraBattleShip* Cr = FindById(B.CarrierId);
	if (T && !T->bAlive)
	{
		T = nullptr;
	}
	if (Cr && !Cr->bAlive)
	{
		Cr = nullptr;
	}
	const auto SetPhase = [&B](EPhase P) { B.Phase = P; B.T = 0.f; };
	const auto Steer = [&](const FVector& WantVel, const FVector& Facing, const FVector& UpHint, float MaxAccel, float TurnDeg)
	{
		const FVector DV = (WantVel - S.Vel).GetClampedToMaxSize(MaxAccel * Dt);
		S.Vel += DV;
		const FVector Fwd = Facing.IsNearlyZero() ? (S.Vel.IsNearlyZero() ? S.Att.GetForwardVector() : S.Vel.GetSafeNormal()) : Facing;
		const FQuat Want = BfFace(Fwd, UpHint);
		const float MaxStep = FMath::DegreesToRadians(TurnDeg * Dt);
		const float Ang = S.Att.AngularDistance(Want);
		S.Att = Ang <= MaxStep ? Want : FQuat::Slerp(S.Att, Want, MaxStep / Ang);
		S.Pos += S.Vel * Dt;
	};
	const bool bFlying = B.Phase == EPhase::Idle || B.Phase == EPhase::Leaving || B.Phase == EPhase::Transit || B.Phase == EPhase::Approach || B.Phase == EPhase::Hold;
	const bool bOnHull = B.Phase == EPhase::Latching || B.Phase == EPhase::Docked || B.Phase == EPhase::Undocking;
	const auto Away = [&](const TCHAR* Why)
	{
		// the craft is out of the order: it turns for home (the event tells the host why)
		B.bHome = true;
		B.bAbort = false;
		EmitBoardEvent(EEventKind::Aborted, S, Why);
		if (B.Phase != EPhase::Leaving && B.Phase != EPhase::Idle)
		{
			SetPhase(EPhase::Transit);
		}
	};
	const auto GiveUpBay = [&]()
	{
		if (FBay* Bay = BoardBays.Find(B.CarrierId))
		{
			Bay->Away = FMath::Max(0, Bay->Away - 1);
			++Bay->Lost;
		}
	};
	// the target is gone: latched, the craft goes with her; flying, it turns for home
	if (!T && !B.bHome)
	{
		if (bOnHull)
		{
			Destroy(S, EAstraHitKind::Internal, EAstraFate::Destroyed);
			return;
		}
		Away(TEXT("the target is gone"));
	}
	// ordered back (the order was withdrawn): it turns for home from where it is (the event was told by the order)
	if (B.bAbort && !B.bHome && bFlying)
	{
		B.bHome = true;
		B.bAbort = false;
		if (B.Phase != EPhase::Leaving && B.Phase != EPhase::Idle)
		{
			SetPhase(EPhase::Transit);
		}
	}
	// ---- on the hull: it moves with her
	if (B.Phase == EPhase::Latching || B.Phase == EPhase::Docked)
	{
		B.bAllowPd = false;                                        // on the hull the point defence cannot bear on it
		const FVector HatchW = T->Pos + T->Att.RotateVector(B.Dock);
		const FVector NW = T->Att.RotateVector(B.DockNormal).GetSafeNormal();
		const FVector Prev = B.DockWorldPrev.IsNearlyZero() ? HatchW : B.DockWorldPrev;
		B.DockWorldPrev = HatchW;
		S.Pos = HatchW + NW * (K->HalfLength + 0.4);
		S.Vel = (HatchW - Prev) / FMath::Max(Dt, 1.0e-3f);
		S.Att = BfFace(-NW, T->Att.GetUpVector());
		if (B.Phase == EPhase::Latching)
		{
			if (B.T >= K->LatchS)
			{
				SetPhase(EPhase::Docked);
				EmitBoardEvent(EEventKind::Docked, S, FString());
				B.bUnloaded = true;                                // (the event told the men aboard: they are through now)
				if (S.Side == EAstraSide::Astra || T->bPlayer)
				{
					HullSound(TEXT("SW_Impact"), 0.4f, 0.5f);
				}
			}
		}
		else if (B.bDepart)
		{
			B.bDepart = false;
			B.bHome = true;
			SetPhase(EPhase::Undocking);
			EmitBoardEvent(EEventKind::Departed, S, FString());
		}
		return;
	}
	if (B.Phase == EPhase::Undocking)
	{
		B.bAllowPd = true;
		const FVector NW = T ? T->Att.RotateVector(B.DockNormal).GetSafeNormal() : (Cr ? (S.Pos - Cr->Pos).GetSafeNormal() : -S.Att.GetForwardVector());
		const FVector Base = T ? T->Vel : S.Vel;
		Steer(Base + NW * (6.0 + 5.0 * B.T), -NW, T ? T->Att.GetUpVector() : FVector::UpVector, K->Accel, 40.f);
		if (B.T > 6.f)
		{
			SetPhase(EPhase::Transit);
		}
		return;
	}
	// ---- flying: to the target's hatch, or home to the carrier's bay
	const bool bHome = B.bHome;
	const FAstraBattleShip* Anchor = bHome ? Cr : T;
	if (!Anchor)
	{
		// no ship to come home to: it drifts away from where it was, and is gone after a while
		B.bAllowPd = true;
		B.GoneT += Dt;
		const FVector Out = T ? (S.Pos - T->Pos).GetSafeNormal() : S.Att.GetForwardVector();
		Steer(Out * K->Cruise * 0.6, FVector::ZeroVector, FVector::UpVector, K->Accel, 20.f);
		if (B.GoneT > 40.f)
		{
			EmitBoardEvent(EEventKind::Lost, S, TEXT("she has no ship to come home to"));
			GiveUpBay();
			RemoveBoardingCraft(S);
		}
		return;
	}
	const FVector Local = bHome ? B.Bay : B.Dock;
	const FVector LocalN = (bHome ? B.BayNormal : B.DockNormal).GetSafeNormal();
	const auto HatchWorld = [&]() { return Anchor->Pos + Anchor->Att.RotateVector(Local); };
	const auto NormalWorld = [&]() { return Anchor->Att.RotateVector(LocalN).GetSafeNormal(); };
	B.bAllowPd = true;
	switch (B.Phase)
	{
	case EPhase::Idle:
	case EPhase::Leaving:
	{
		if (B.Phase == EPhase::Idle)
		{
			SetPhase(EPhase::Leaving);
		}
		// along the bay's axis until clear of the hull, then round to the target
		const FVector NW = Cr ? Cr->Att.RotateVector(B.BayNormal).GetSafeNormal() : S.Att.GetForwardVector();
		const FVector Base = Cr ? Cr->Vel : FVector::ZeroVector;
		const double Out = Cr ? FVector::DotProduct(S.Pos - (Cr->Pos + Cr->Att.RotateVector(B.Bay)), NW) : 100.0;
		Steer(Base + NW * 75.0, NW, Cr ? Cr->Att.GetUpVector() : FVector::UpVector, K->Accel, 70.f);
		if (B.T > 7.f || Out > 130.0)
		{
			SetPhase(EPhase::Transit);
		}
		return;
	}
	case EPhase::Transit:
	{
		const FVector HatchW = HatchWorld();
		const FVector NW = NormalWorld();
		const FVector Stage = HatchW + NW * StageM;
		const FVector Rel = Stage - S.Pos;
		const double Dist = Rel.Size();
		const FVector Dir = Dist > 1.0 ? Rel / Dist : NW;
		const double VDes = FMath::Min((double)K->Cruise, FMath::Sqrt(2.0 * 0.55 * K->Accel * FMath::Max(0.0, Dist - 25.0)) + 8.0);
		FVector Want = Anchor->Vel + Dir * VDes;
		Want = BfWall(*Anchor, S.Pos, Want, K->Cruise, B.Side);
		Steer(Want, FVector::ZeroVector, Anchor->Att.GetUpVector(), K->Accel, 70.f);
		B.DockWorldPrev = FVector::ZeroVector;
		if (Dist < 70.0)
		{
			SetPhase(EPhase::Approach);
		}
		else if (B.T > BfTransitLimitS)
		{
			if (!bHome)
			{
				Away(TEXT("it could not reach the hatch"));
			}
			else
			{
				EmitBoardEvent(EEventKind::Lost, S, TEXT("it could not get home"));
				GiveUpBay();
				RemoveBoardingCraft(S);
			}
		}
		return;
	}
	case EPhase::Approach:
	case EPhase::Hold:
	{
		const FVector HatchW = HatchWorld();
		const FVector NW = NormalWorld();
		const FVector HatchVel = B.DockWorldPrev.IsNearlyZero() ? Anchor->Vel : (HatchW - B.DockWorldPrev) / FMath::Max(Dt, 1.0e-3f);
		B.DockWorldPrev = HatchW;
		const FVector Touch = HatchW + NW * (K->HalfLength + 0.4);
		const FVector Rel = S.Pos - Touch;
		const double Along = FVector::DotProduct(Rel, NW);
		const FVector Lat = Rel - NW * Along;
		// the shield on the hatch's face: it does not let a craft through while it is up; the craft waits off the hull (and the point defence keeps shooting at it)
		float Frac = 0.f;
		const bool bOpen = bHome || BoardingDockOpen(*T, B.DockNormal.GetSafeNormal(), &Frac);
		if (!bOpen && Along < 260.0)
		{
			if (B.Phase != EPhase::Hold)
			{
				SetPhase(EPhase::Hold);
				B.HoldT = 0.f;
			}
		}
		else if (B.Phase == EPhase::Hold && bOpen)
		{
			SetPhase(EPhase::Approach);
		}
		if (B.Phase == EPhase::Hold)
		{
			B.HoldT += Dt;
			const FVector Want = HatchVel - NW * FMath::Clamp((Along - 170.0) * 0.4, -25.0, 25.0) - Lat * 0.8;
			Steer(Want, -NW, Anchor->Att.GetUpVector(), K->Accel, 60.f);
			if (B.HoldT > BfHoldGiveUpS)
			{
				Away(*FString::Printf(TEXT("the shield on her %s face held (%.0f%%): the craft cannot dock through it"), AstraWar::FacingName(FacingOfNormal(B.DockNormal)), Frac * 100.f));
			}
			return;
		}
		const double Close = FMath::Clamp(0.30 * Along, 2.5, 55.0);
		const FVector Want = HatchVel - NW * Close - Lat.GetClampedToMaxSize(300.0) * 0.9;
		Steer(Want, -NW, Anchor->Att.GetUpVector(), K->Accel, 70.f);
		const double Speed = (S.Vel - HatchVel).Size();
		if (Along < 2.2 && Lat.Size() < 3.5 && Speed < 7.0)
		{
			if (bHome)
			{
				// home: through the mouth and aboard
				if (FBay* Bay = BoardBays.Find(B.CarrierId))
				{
					Bay->Away = FMath::Max(0, Bay->Away - 1);
				}
				EmitBoardEvent(EEventKind::Recovered, S, FString());
				RemoveBoardingCraft(S);
				return;
			}
			SetPhase(EPhase::Latching);
			B.bAllowPd = false;
			S.Pos = Touch;
			S.Vel = HatchVel;
			B.DockWorldPrev = HatchW;
			if (S.Side == EAstraSide::Astra || T->bPlayer)
			{
				HullSound(TEXT("SW_Impact"), 0.3f, 0.5f);
			}
		}
		else if (B.T > BfApproachLimitS)
		{
			if (!bHome)
			{
				Away(TEXT("it could not line up with the hatch"));
			}
			else
			{
				EmitBoardEvent(EEventKind::Lost, S, TEXT("it could not get into the bay"));
				GiveUpBay();
				RemoveBoardingCraft(S);
			}
		}
		return;
	}
	default:
		return;
	}
}
