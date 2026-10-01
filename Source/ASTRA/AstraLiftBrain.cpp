// ASTRA — the lifts' brain (see AstraLiftBrain.h).

#include "AstraLiftBrain.h"

// ====================================================================================================================== the path

void FAstraLiftPath::Build(const TArray<FVector>& InPts)
{
	Pts = InPts;
	Cum.Reset();
	Length = 0.f;
	for (int32 i = 0; i < Pts.Num(); ++i)
	{
		if (i > 0)
		{
			Length += (float)FVector::Dist(Pts[i - 1], Pts[i]);
		}
		Cum.Add(Length);
	}
}

namespace
{
	/** The segment an arc length falls in (the last one past the end). */
	int32 LiftSegmentAt(const TArray<float>& Cum, float S)
	{
		int32 I = 0;
		while (I + 2 < Cum.Num() && S > Cum[I + 1])
		{
			++I;
		}
		return I;
	}
}

FVector FAstraLiftPath::At(float S) const
{
	if (Pts.Num() == 0)
	{
		return FVector::ZeroVector;
	}
	if (Pts.Num() == 1)
	{
		return Pts[0];
	}
	S = FMath::Clamp(S, 0.f, Length);
	const int32 I = LiftSegmentAt(Cum, S);
	const float Len = Cum[I + 1] - Cum[I];
	return Len > KINDA_SMALL_NUMBER ? FMath::Lerp(Pts[I], Pts[I + 1], (S - Cum[I]) / Len) : Pts[I];
}

FVector FAstraLiftPath::Tangent(float S) const
{
	if (Pts.Num() < 2)
	{
		return FVector::UpVector;
	}
	const int32 I = LiftSegmentAt(Cum, FMath::Clamp(S, 0.f, Length));
	return (Pts[I + 1] - Pts[I]).GetSafeNormal();
}

float FAstraLiftPath::Project(const FVector& P) const
{
	float Best = 0.f;
	double BestD = TNumericLimits<double>::Max();
	for (int32 I = 0; I + 1 < Pts.Num(); ++I)
	{
		const FVector A = Pts[I], B = Pts[I + 1];
		const FVector AB = B - A;
		const double L2 = AB.SizeSquared();
		const double T = L2 > KINDA_SMALL_NUMBER ? FMath::Clamp(FVector::DotProduct(P - A, AB) / L2, 0.0, 1.0) : 0.0;
		const double D = FVector::DistSquared(P, A + AB * T);
		if (D < BestD)
		{
			BestD = D;
			Best = Cum[I] + (float)(T * FMath::Sqrt(L2));
		}
	}
	return Best;
}

// ================================================================================================================== the profile

FAstraLiftProfile FAstraLiftProfile::Make(float Dist, float Vmax, float Accel)
{
	FAstraLiftProfile P;
	P.D = FMath::Max(0.f, Dist);
	if (P.D < 0.01f || Vmax <= 0.f || Accel <= 0.f)
	{
		return P;
	}
	// a hop of a deck or two is made gently (the push is what the Captain feels there): the line's acceleration is the one for a run of sixteen metres or more
	Accel *= FMath::GetMappedRangeValueClamped(FVector2D(400.0, 1600.0), FVector2D(0.65, 1.0), P.D);
	// a smoothstep ramp from rest to the peak takes 1.5 Vc / A at the acceleration A (its steepest point) and covers Vc Ta / 2
	const float TaFull = 1.5f * Vmax / Accel;
	if (P.D >= Vmax * TaFull)
	{
		P.Vc = Vmax;
		P.Ta = TaFull;
		P.Tc = (P.D - Vmax * TaFull) / Vmax;
	}
	else
	{
		// a short hop never reaches the line's speed: the peak is what makes the two ramps cover the distance
		P.Vc = FMath::Sqrt(P.D * Accel / 1.5f);
		P.Ta = 1.5f * P.Vc / Accel;
		P.Tc = 0.f;
	}
	P.T = 2.f * P.Ta + P.Tc;
	return P;
}

namespace
{
	float LiftRampPos(float X)          // the area under a smoothstep, X in 0..1 (times Vc Ta)
	{
		return X * X * X - 0.5f * X * X * X * X;
	}
	float LiftRampVel(float X)          // the smoothstep (times Vc)
	{
		return X * X * (3.f - 2.f * X);
	}
	float LiftRampAcc(float X)          // its slope (times Vc / Ta)
	{
		return 6.f * X * (1.f - X);
	}
}

float FAstraLiftProfile::Pos(float t) const
{
	if (T <= 0.f)
	{
		return D;
	}
	t = FMath::Clamp(t, 0.f, T);
	if (t < Ta)
	{
		return Vc * Ta * LiftRampPos(t / Ta);
	}
	if (t < Ta + Tc)
	{
		return 0.5f * Vc * Ta + Vc * (t - Ta);
	}
	return D - Vc * Ta * LiftRampPos((T - t) / Ta);
}

float FAstraLiftProfile::Vel(float t) const
{
	if (T <= 0.f || t <= 0.f || t >= T)
	{
		return 0.f;
	}
	if (t < Ta)
	{
		return Vc * LiftRampVel(t / Ta);
	}
	if (t < Ta + Tc)
	{
		return Vc;
	}
	return Vc * LiftRampVel((T - t) / Ta);
}

float FAstraLiftProfile::Acc(float t) const
{
	if (T <= 0.f || t <= 0.f || t >= T)
	{
		return 0.f;
	}
	if (t < Ta)
	{
		return Vc / Ta * LiftRampAcc(t / Ta);
	}
	if (t < Ta + Tc)
	{
		return 0.f;
	}
	return -Vc / Ta * LiftRampAcc((T - t) / Ta);
}

bool FAstraLiftProfile::Retarget(float t, float NewD, float Guard)
{
	// only in the cruise: there the position is the same whatever the length of the move, so the car does not notice
	if (!Cruising(t) || NewD < Vc * Ta)
	{
		return false;
	}
	const float NewTc = (NewD - Vc * Ta) / Vc;
	if (Ta + NewTc < t + Guard)
	{
		return false;                      // the braking would have to begin now
	}
	D = NewD;
	Tc = NewTc;
	T = 2.f * Ta + Tc;
	return true;
}

// =================================================================================================================== the brain

void FAstraLiftBrain::Init(const TArray<float>& InLandingS, int32 StartLanding, const FConfig& InCfg, FHooks InHooks)
{
	LandingS = InLandingS;
	Cfg = InCfg;
	H = MoveTemp(InHooks);
	const int32 N = LandingS.Num();
	CarCalls.Init(false, N);
	HallUp.Init(false, N);
	HallDown.Init(false, N);
	HallAny.Init(false, N);
	CallAge.Init(0.0, N);
	Out.Reset();
	At = FMath::Clamp(StartLanding, 0, FMath::Max(0, N - 1));
	Pos = N ? LandingS[At] : 0.f;
	Vel = 0.f;
	Door = 0.f;
	Head = 0;
	Mode = EState::Idle;
	LegFrom = LegTo = INDEX_NONE;
	Timer = 0.f;
}

bool FAstraLiftBrain::RequestAt(int32 L) const
{
	return CarCalls.IsValidIndex(L) && (CarCalls[L] || HallUp[L] || HallDown[L] || HallAny[L]);
}

bool FAstraLiftBrain::AnyRequest() const
{
	for (int32 L = 0; L < CarCalls.Num(); ++L)
	{
		if (RequestAt(L))
		{
			return true;
		}
	}
	return false;
}

bool FAstraLiftBrain::HasHallCall(int32 L, int32 Dir) const
{
	if (!HallUp.IsValidIndex(L))
	{
		return false;
	}
	return HallAny[L] || (Dir >= 0 && HallUp[L]) || (Dir <= 0 && HallDown[L]);
}

bool FAstraLiftBrain::Takes(int32 L, bool bFull) const
{
	return CarCalls[L] || (!bFull && (HallUp[L] || HallDown[L] || HallAny[L]));
}

bool FAstraLiftBrain::Eligible(int32 L, int32 Dir, bool bFull) const
{
	return CarCalls[L] || (!bFull && (HallAny[L] || (Dir > 0 ? HallUp[L] : HallDown[L])));
}

bool FAstraLiftBrain::RequestAheadOf(float FromS, int32 Dir, bool bFull) const
{
	for (int32 L = 0; L < LandingS.Num(); ++L)
	{
		if ((LandingS[L] - FromS) * Dir > 1.f && Takes(L, bFull))
		{
			return true;
		}
	}
	return false;
}

int32 FAstraLiftBrain::NextStop(float FromS, int32 Dir, bool bFull) const
{
	// the nearest stop that is for a car going this way (a stop asked for inside, a call for this direction or for either); when there is none, the
	// farthest of the others: the car goes to the last call of its sweep and turns there
	int32 Farthest = INDEX_NONE;
	const int32 N = LandingS.Num();
	for (int32 K = 0; K < N; ++K)
	{
		const int32 L = Dir > 0 ? K : N - 1 - K;
		if ((LandingS[L] - FromS) * Dir <= 1.f || !Takes(L, bFull))
		{
			continue;
		}
		if (Eligible(L, Dir, bFull))
		{
			return L;
		}
		Farthest = L;
	}
	return Farthest;
}

void FAstraLiftBrain::StartLeg(int32 Next)
{
	LegFrom = At;
	LegTo = Next;
	LegS0 = Pos;
	LegDir = LandingS[Next] > Pos ? 1 : -1;
	LegT = 0.f;
	Leg = FAstraLiftProfile::Make(FMath::Abs(LandingS[Next] - Pos), Cfg.VmaxCmS, Cfg.AccelCmS2);
	Mode = EState::Moving;
	At = INDEX_NONE;
	Vel = 0.f;
	Emit(FAstraLiftEvent::EType::Depart, LegFrom, LegTo);
	if (H.WantDeck)
	{
		H.WantDeck(LegTo);
	}
}

void FAstraLiftBrain::Decide()
{
	const bool bFull = FullNow();
	bool bAny = false;
	for (int32 L = 0; L < LandingS.Num() && !bAny; ++L)
	{
		bAny = Takes(L, bFull);
	}
	if (!bAny)
	{
		if (!AnyRequest())
		{
			Head = 0;
		}
		return;                                // (a full car with only calls from landings waits for someone aboard to choose a stop)
	}
	// a call at the landing the car stands at: the doors open for it when it is for the way the car goes, or the car has no way to go (a call the other way
	// waits: the car leaves, and comes back for it)
	if (At != INDEX_NONE && Takes(At, bFull) && (Head == 0 || Eligible(At, Head, bFull) || !RequestAheadOf(Pos, Head, bFull)))
	{
		BeginServe();
		return;
	}
	int32 Dir = Head;
	int32 Next = Dir != 0 ? NextStop(Pos, Dir, bFull) : INDEX_NONE;
	if (Next == INDEX_NONE)
	{
		// nothing ahead on this heading: an idle car goes to the nearest call (the oldest first when two are as near)
		int32 Best = INDEX_NONE;
		float BestD = TNumericLimits<float>::Max();
		for (int32 L = 0; L < LandingS.Num(); ++L)
		{
			if (!Takes(L, bFull))
			{
				continue;
			}
			const float D = FMath::Abs(LandingS[L] - Pos) - (float)FMath::Min(CallAge[L], 60.0) * 2.f;     // two cm of nearness for each second a call waited
			if (D < BestD)
			{
				BestD = D;
				Best = L;
			}
		}
		if (Best == INDEX_NONE)
		{
			return;
		}
		if (Best == At)
		{
			BeginServe();                       // (the only call there is, is here, and for the way back)
			return;
		}
		Dir = LandingS[Best] > Pos ? 1 : -1;
		Next = NextStop(Pos, Dir, bFull);
		if (Next == INDEX_NONE)
		{
			Next = Best;
		}
	}
	Head = Dir;
	StartLeg(Next);
}

void FAstraLiftBrain::ClearServed(int32 L, bool bFull)
{
	CarCalls[L] = false;
	if (bFull)
	{
		return;                                // nobody can get in: the calls from this landing stand
	}
	const bool bUp = HallUp[L], bDown = HallDown[L];
	HallAny[L] = false;
	if (Head == 0)
	{
		// an idle car answering a call at its own landing, or one that arrived with nothing ahead: both buttons are answered, and the direction asked sets the heading
		if (bUp != bDown)
		{
			Head = bUp ? 1 : -1;
		}
		HallUp[L] = HallDown[L] = false;
	}
	else
	{
		(Head > 0 ? HallUp : HallDown)[L] = false;
		if (!RequestAheadOf(Pos, Head, false))
		{
			// the last stop of the sweep: whoever called the other way gets in, and the car turns
			const bool bOther = Head > 0 ? HallDown[L] : HallUp[L];
			HallUp[L] = HallDown[L] = false;
			if (bOther)
			{
				Head = -Head;
			}
		}
	}
}

void FAstraLiftBrain::BeginServe()
{
	// the calls of this landing are answered; who boards is told by the heading the car leaves with
	ClearServed(At, FullNow());
	CallAge[At] = 0.0;
	Mode = EState::Opening;
	Emit(FAstraLiftEvent::EType::DoorsOpening, At);
}

void FAstraLiftBrain::Arrive()
{
	At = LegTo;
	Pos = LandingS[At];
	Vel = 0.f;
	LegTo = INDEX_NONE;
	Emit(FAstraLiftEvent::EType::Arrive, At);
	if (Ready(At))
	{
		BeginServe();
	}
	else
	{
		Mode = EState::Hold;               // the deck behind these doors is not in the world yet: they stay shut
		Timer = 0.f;
		Emit(FAstraLiftEvent::EType::Held, At);
	}
}

void FAstraLiftBrain::Step(float Dt)
{
	for (int32 L = 0; L < LandingS.Num(); ++L)
	{
		if (RequestAt(L))
		{
			CallAge[L] += Dt;
		}
	}
	switch (Mode)
	{
	case EState::Idle:
		Decide();
		break;
	case EState::Moving:
		LegT += Dt;
		if (LegT >= Leg.T)
		{
			Pos = LandingS[LegTo];
			Vel = 0.f;
			Arrive();
		}
		else
		{
			Pos = LegS0 + LegDir * Leg.Pos(LegT);
			Vel = LegDir * Leg.Vel(LegT);
		}
		break;
	case EState::Hold:
		Timer += Dt;
		if (Ready(At))
		{
			BeginServe();
		}
		else if (Timer >= Cfg.HeldForceS)
		{
			if (H.ForceDeck)
			{
				H.ForceDeck(At);
			}
			Emit(FAstraLiftEvent::EType::Forced, At);
			BeginServe();
		}
		break;
	case EState::Opening:
		Door = FMath::Min(1.f, Door + Dt / Cfg.DoorS);
		if (Door >= 1.f)
		{
			Mode = EState::Open;
			Timer = Cfg.DwellS;
			Emit(FAstraLiftEvent::EType::DoorsOpen, At);
		}
		break;
	case EState::Open:
		Timer -= Dt;
		if (HallUp[At] || HallDown[At] || HallAny[At])
		{
			ClearServed(At, FullNow());              // room was made (someone got out): whoever waited at this landing can get in now
		}
		if (Busy(At))
		{
			Timer = FMath::Max(Timer, 1.0f);       // someone is in the doorway: the doors wait for them, however long it takes
		}
		if (Timer <= 0.f)
		{
			Mode = EState::Closing;
			Emit(FAstraLiftEvent::EType::DoorsClosing, At);
		}
		break;
	case EState::Closing:
		if (Busy(At))
		{
			Mode = EState::Opening;                // never on someone who steps in: back they go
			Emit(FAstraLiftEvent::EType::DoorsReopen, At);
			break;
		}
		Door = FMath::Max(0.f, Door - Dt / Cfg.DoorS);
		if (Door <= 0.f)
		{
			Mode = EState::Idle;
			Emit(FAstraLiftEvent::EType::DoorsClosed, At);
		}
		break;
	}
}

void FAstraLiftBrain::Tick(float Dt)
{
	if (!IsReady())
	{
		return;
	}
	while (Dt > 0.f)
	{
		const float S = FMath::Min(Dt, 0.05f);
		Step(S);
		Dt -= S;
	}
}

void FAstraLiftBrain::ClearCalls()
{
	for (int32 L = 0; L < LandingS.Num(); ++L)
	{
		CarCalls[L] = HallUp[L] = HallDown[L] = HallAny[L] = false;
		CallAge[L] = 0.0;
	}
}

void FAstraLiftBrain::HallCall(int32 L, int32 Dir)
{
	if (!CarCalls.IsValidIndex(L))
	{
		return;
	}
	Dir = FMath::Clamp(Dir, -1, 1);
	Emit(FAstraLiftEvent::EType::Call, L, Dir);
	// at the landing the car stands at with its doors going or open: it answers at once if it is a call for the way it will go (or it has nowhere to go)
	if (At == L && (Mode == EState::Opening || Mode == EState::Open || Mode == EState::Closing))
	{
		const bool bFree = Head == 0 || !RequestAheadOf(Pos, Head, FullNow());
		if (!FullNow() && (Dir == 0 || bFree || Dir == Head))
		{
			if (Dir != 0 && bFree)
			{
				Head = Dir;
			}
			if (Mode == EState::Open)
			{
				Timer = Cfg.DwellS;
			}
			else if (Mode == EState::Closing)
			{
				Mode = EState::Opening;
				Emit(FAstraLiftEvent::EType::DoorsReopen, L);
			}
			return;
		}
	}
	if (Dir == 0)
	{
		HallAny[L] = true;
	}
	else if (Dir > 0)
	{
		HallUp[L] = true;
	}
	else
	{
		HallDown[L] = true;
	}
	// a stop on the way: the car is cruising towards a farther one and this is for it
	if (Mode == EState::Moving && L != LegTo && (Dir == 0 || Dir == LegDir))
	{
		const float D = (LandingS[L] - Pos) * LegDir, DT = (LandingS[LegTo] - Pos) * LegDir;
		if (D > 0.f && D < DT && Leg.Retarget(LegT, FMath::Abs(LandingS[L] - LegS0), Cfg.RetargetGuardS))
		{
			LegTo = L;
			Emit(FAstraLiftEvent::EType::Retarget, L);
		}
	}
}

void FAstraLiftBrain::CarCall(int32 L)
{
	if (!CarCalls.IsValidIndex(L))
	{
		return;
	}
	if (At == L && Mode != EState::Moving)
	{
		return;                              // already here
	}
	CarCalls[L] = true;
	Emit(FAstraLiftEvent::EType::CarCall, L);
	if (Mode == EState::Open)
	{
		Timer = FMath::Min(Timer, Cfg.BoardedDwellS);    // somebody inside chose: the doors do not wait the whole dwell
	}
	if (Mode == EState::Moving && L != LegTo)
	{
		const float D = (LandingS[L] - Pos) * LegDir, DT = (LandingS[LegTo] - Pos) * LegDir;
		if (D > 0.f && D < DT && Leg.Retarget(LegT, FMath::Abs(LandingS[L] - LegS0), Cfg.RetargetGuardS))
		{
			LegTo = L;
			Emit(FAstraLiftEvent::EType::Retarget, L);
		}
	}
}

float FAstraLiftBrain::RideSeconds(int32 From, int32 To) const
{
	if (!LandingS.IsValidIndex(From) || !LandingS.IsValidIndex(To) || From == To)
	{
		return 0.f;
	}
	return Cfg.DoorS + Cfg.BoardedDwellS + Cfg.DoorS + FAstraLiftProfile::Make(FMath::Abs(LandingS[To] - LandingS[From]), Cfg.VmaxCmS, Cfg.AccelCmS2).T + Cfg.DoorS;
}

float FAstraLiftBrain::EstimateArrival(int32 L, int32 Dir) const
{
	if (!LandingS.IsValidIndex(L))
	{
		return 0.f;
	}
	if (At == L && Mode != EState::Moving)
	{
		return 0.f;
	}
	float T = 0.f, From = Pos;
	switch (Mode)
	{
	case EState::Moving:
		T += LegRemainingS() + 2.f * Cfg.DoorS + Cfg.DwellS;
		From = LandingS[LegTo];
		break;
	case EState::Opening:
	case EState::Open:
	case EState::Closing:
	case EState::Hold:
		T += 2.f * Cfg.DoorS + Cfg.BoardedDwellS;
		break;
	default:
		break;
	}
	// the stops the car makes on the way, each the doors twice and a dwell
	const float Lo = FMath::Min(From, LandingS[L]), Hi = FMath::Max(From, LandingS[L]);
	for (int32 K = 0; K < LandingS.Num(); ++K)
	{
		if (K != L && LandingS[K] > Lo + 1.f && LandingS[K] < Hi - 1.f && RequestAt(K))
		{
			T += 2.f * Cfg.DoorS + Cfg.DwellS;
		}
	}
	return T + FAstraLiftProfile::Make(FMath::Abs(LandingS[L] - From), Cfg.VmaxCmS, Cfg.AccelCmS2).T + Cfg.DoorS;
}
