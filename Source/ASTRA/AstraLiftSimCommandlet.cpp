#include "AstraLiftSimCommandlet.h"

#include "ASTRA.h"
#include "AstraLiftBrain.h"
#include "AstraLiftCar.h"
#include "AstraLiftData.h"
#include "AstraLiftRider.h"
#include "AstraLiftSubsystem.h"
#include "AstraLiftTestRig.h"
#include "Components/CapsuleComponent.h"
#include "Dom/JsonObject.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/WorldSettings.h"
#include "HAL/PlatformProcess.h"
#include "CoreGlobals.h"
#include "HAL/PlatformTime.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Policies/CondensedJsonPrintPolicy.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "Tickable.h"

bool GAstraLiftTrace = false;

namespace
{
	struct FLiftCheck
	{
		FString Name;
		bool bPass = true;
	};
	TArray<FLiftCheck> LiftChecks;

	void LiftCheck(const TCHAR* Name, bool bPass, const FString& Detail)
	{
		LiftChecks.Add({Name, bPass});
		UE_LOG(LogASTRA, Display, TEXT("[Lift] %s %-40s %s"), bPass ? TEXT("PASS") : TEXT("FAIL"), Name, *Detail);
	}

	double LiftPercentile(TArray<double> V, double P)
	{
		if (V.Num() == 0)
		{
			return 0.0;
		}
		V.Sort();
		return V[FMath::Clamp((int32)(P * (V.Num() - 1) + 0.5), 0, V.Num() - 1)];
	}

	double LiftMean(const TArray<double>& V)
	{
		double S = 0.0;
		for (const double X : V)
		{
			S += X;
		}
		return V.Num() ? S / V.Num() : 0.0;
	}
}

UAstraLiftSimCommandlet::UAstraLiftSimCommandlet()
{
	IsClient = false;
	IsServer = false;
	IsEditor = true;                 // the editor's plugins assume an editor engine even here (as the other benches)
	LogToConsole = true;
	ShowErrorCount = true;
}

// ================================================================================================================================ the brain, alone

namespace
{
	/** A brain on its own clock, with the invariants a lift must never break checked at every step. */
	struct FLiftSim
	{
		FAstraLiftBrain B;
		TArray<float> LandingS;
		FAstraLiftBrain::FConfig Cfg;
		double T = 0.0;
		TArray<TPair<double, FAstraLiftEvent>> Log;
		TFunction<void(const FAstraLiftEvent&)> OnEvent;
		int32 Violations = 0;
		FString First;
		float PrevV = 0.f, MaxAccel = 0.f, MaxV = 0.f;
		float Dt = 0.02f;
		int32 MovingNowCalls = 0;

		void Init(const TArray<float>& S, int32 Start, FAstraLiftBrain::FHooks Hooks = FAstraLiftBrain::FHooks())
		{
			LandingS = S;
			B.Init(S, Start, Cfg, MoveTemp(Hooks));
			T = 0.0;
			Log.Reset();
			Violations = 0;
			PrevV = 0.f;
		}
		void Bad(const FString& Why)
		{
			if (Violations++ == 0)
			{
				First = FString::Printf(TEXT("at %.2f s: %s"), T, *Why);
			}
		}
		void Step()
		{
			B.Tick(Dt);
			T += Dt;
			for (const FAstraLiftEvent& E : B.Events())
			{
				Log.Add({T, E});
				if (OnEvent)
				{
					OnEvent(E);
				}
			}
			B.Events().Reset();
			using EState = FAstraLiftBrain::EState;
			if (B.DoorOpen() > 0.f)
			{
				const bool bOk = B.AtLanding() != INDEX_NONE && (B.State() == EState::Opening || B.State() == EState::Open || B.State() == EState::Closing) &&
				                 FMath::Abs(B.S() - LandingS[B.AtLanding()]) < 0.01f && FMath::Abs(B.V()) < 0.01f;
				if (!bOk)
				{
					Bad(FString::Printf(TEXT("the doors are %.2f open away from a stopped car at a landing (state %d, s %.1f, v %.1f)"), B.DoorOpen(), (int32)B.State(), B.S(), B.V()));
				}
			}
			if (B.State() == EState::Moving && (B.DoorOpen() > 0.f || B.AtLanding() != INDEX_NONE))
			{
				Bad(TEXT("the car moves with its doors not shut"));
			}
			MaxV = FMath::Max(MaxV, FMath::Abs(B.V()));
			if (FMath::Abs(B.V()) > Cfg.VmaxCmS * 1.001f)
			{
				Bad(FString::Printf(TEXT("speed %.1f over the line's %.1f"), B.V(), Cfg.VmaxCmS));
			}
			const float Acc = FMath::Abs(B.V() - PrevV) / Dt;
			MaxAccel = FMath::Max(MaxAccel, Acc);
			if (Acc > Cfg.AccelCmS2 * 1.03f + 1.f)
			{
				Bad(FString::Printf(TEXT("acceleration %.1f cm/s2 over the line's %.1f"), Acc, Cfg.AccelCmS2));
			}
			PrevV = B.V();
		}
		void Run(float Seconds)
		{
			const double End = T + Seconds;
			while (T < End - 1.0e-6)
			{
				Step();
			}
		}
		/** Until the car is quiet (nothing asked, doors shut) or the time is up; the seconds it took. */
		double RunQuiet(float MaxS)
		{
			const double T0 = T;
			while (T - T0 < MaxS && !B.Quiet())
			{
				Step();
			}
			return T - T0;
		}
		int32 Count(FAstraLiftEvent::EType Type) const
		{
			int32 N = 0;
			for (const auto& E : Log)
			{
				N += E.Value.Type == Type ? 1 : 0;
			}
			return N;
		}
		TArray<int32> Arrivals() const
		{
			TArray<int32> A;
			for (const auto& E : Log)
			{
				if (E.Value.Type == FAstraLiftEvent::EType::Arrive)
				{
					A.Add(E.Value.Landing);
				}
			}
			return A;
		}
	};

	/** The landings of a line of the test plan, as the brain is given them. */
	TArray<float> LiftStopsOf(const FAstraLiftLine& L)
	{
		TArray<float> S;
		for (const FAstraLiftStop& Stop : L.Stops)
		{
			S.Add(Stop.S);
		}
		return S;
	}

	FString LiftArrivalText(const TArray<int32>& A)
	{
		FString T;
		for (const int32 I : A)
		{
			T += FString::Printf(TEXT("%s%d"), T.IsEmpty() ? TEXT("") : TEXT(" "), I);
		}
		return T;
	}

	void LiftTestMotion()
	{
		const float Vmax = 800.f, A = 250.f;
		const float Metres[] = {4.f, 8.f, 16.f, 36.7f, 66.f, 78.f};
		int32 Bad = 0;
		FString Times;
		float WorstJerk = 0.f;
		for (const float M : Metres)
		{
			const FAstraLiftProfile P = FAstraLiftProfile::Make(M * 100.f, Vmax, A);
			Times += FString::Printf(TEXT("%.0f m %.1f s (peak %.1f m/s)  "), M, P.T, P.Vc / 100.f);
			float PrevPos = 0.f, PrevAcc = 0.f;
			const float H = 0.002f;
			for (float t = 0.f; t <= P.T + 0.0001f; t += H)
			{
				const float Pos = P.Pos(t), V = P.Vel(t), Ac = P.Acc(t);
				const float Numeric = (P.Pos(t + H) - P.Pos(FMath::Max(0.f, t - H))) / (t + H - FMath::Max(0.f, t - H));
				Bad += Pos + 0.01f < PrevPos ? 1 : 0;                                     // never back
				Bad += FMath::Abs(V - Numeric) > 2.f && t > H && t < P.T - H ? 1 : 0;      // the speed is the position's slope
				Bad += FMath::Abs(Ac) > A * 1.001f ? 1 : 0;
				Bad += V > Vmax * 1.001f ? 1 : 0;
				WorstJerk = FMath::Max(WorstJerk, FMath::Abs(Ac - PrevAcc) / H);
				PrevPos = Pos;
				PrevAcc = Ac;
			}
			Bad += FMath::Abs(P.Pos(P.T) - M * 100.f) > 0.01f ? 1 : 0;
			Bad += FMath::Abs(P.Pos(0.f)) > 0.001f || P.Vel(0.f) != 0.f || P.Vel(P.T) != 0.f || FMath::Abs(P.Acc(0.001f)) > 1.f ? 1 : 0;
		}
		LiftCheck(TEXT("motion: a smooth move, exact at both ends"), Bad == 0, FString::Printf(TEXT("%d breaks over 6 moves; %s; jerk at most %.1f m/s3"), Bad, *Times, WorstJerk / 100.f));
		// a stop asked for on the way: only while cruising, and only if the braking can still begin; the car does not notice
		FAstraLiftProfile P = FAstraLiftProfile::Make(6600.f, Vmax, A);
		const float T0 = P.Ta + 0.3f;
		const float Before = P.Pos(T0);
		const bool bOk = P.Retarget(T0, 5000.f, 0.4f);
		const bool bSame = FMath::Abs(P.Pos(T0) - Before) < 0.01f && FMath::Abs(P.Pos(P.T) - 5000.f) < 0.01f;
		FAstraLiftProfile Q = FAstraLiftProfile::Make(6600.f, Vmax, A);
		const bool bLate = !Q.Retarget(Q.Ta + 2.f, 5000.f, 0.4f);                // the braking would have had to begin already
		FAstraLiftProfile R = FAstraLiftProfile::Make(6600.f, Vmax, A);
		const bool bRamp = !R.Retarget(1.0f, 5000.f, 0.4f);                       // still accelerating: no
		LiftCheck(TEXT("motion: a stop on the way, in the cruise"), bOk && bSame && bLate && bRamp, FString::Printf(TEXT("accepted %d, position kept %d, refused when late %d and when accelerating %d"), bOk, bSame, bLate, bRamp));
	}

	void LiftTestBrain(const FAstraLiftLine& L)
	{
		const TArray<float> S = LiftStopsOf(L);
		const int32 N = S.Num();
		const int32 Top = N - 1;      // the highest landing (Deck 1)
		FAstraLiftBrain::FConfig Cfg;
		Cfg.VmaxCmS = L.SpeedCmS;
		Cfg.AccelCmS2 = L.AccelCmS2;
		using ET = FAstraLiftEvent::EType;

		// a call from a landing: the car goes, stops, opens, waits, closes
		{
			FLiftSim Sim;
			Sim.Cfg = Cfg;
			Sim.Init(S, Top);
			const int32 Want = 5;
			Sim.B.HallCall(Want, 0);
			const double Took = Sim.RunQuiet(120.f);
			const float Leg = FAstraLiftProfile::Make(S[Top] - S[Want], Cfg.VmaxCmS, Cfg.AccelCmS2).T;
			const double Expect = Leg + 2.0 * Cfg.DoorS + Cfg.DwellS;
			LiftCheck(TEXT("brain: a call from a landing"), Sim.Violations == 0 && Sim.B.AtLanding() == Want && Sim.Count(ET::Arrive) == 1 && Sim.Count(ET::DoorsOpen) == 1 && Sim.Count(ET::DoorsClosed) == 1 &&
			      FMath::Abs(Took - Expect) < 0.3, FString::Printf(TEXT("arrives %d, %.1f s for a leg of %.1f s and the doors (%.1f expected), %d violations %s"), Sim.B.AtLanding(), Took, Leg, Expect, Sim.Violations, *Sim.First));
		}
		// a call at the landing the car is parked at: the doors open, the car does not move
		{
			FLiftSim Sim;
			Sim.Cfg = Cfg;
			Sim.Init(S, 3);
			Sim.B.HallCall(3, 0);
			Sim.RunQuiet(30.f);
			LiftCheck(TEXT("brain: a call where the car stands"), Sim.Violations == 0 && Sim.Count(ET::Depart) == 0 && Sim.Count(ET::DoorsOpen) == 1 && Sim.Count(ET::DoorsClosed) == 1,
			      FString::Printf(TEXT("%d departures, %d openings"), Sim.Count(ET::Depart), Sim.Count(ET::DoorsOpen)));
		}
		// the sweep: a car call to the bottom, a down call and an up call between: the down call is answered on the way down, the up call on the way back
		{
			FLiftSim Sim;
			Sim.Cfg = Cfg;
			Sim.Init(S, Top);
			Sim.B.CarCall(0);
			Sim.B.HallCall(4, -1);
			Sim.B.HallCall(6, +1);
			Sim.RunQuiet(400.f);
			const TArray<int32> A = Sim.Arrivals();
			const bool bOrder = A.Num() == 3 && A[0] == 4 && A[1] == 0 && A[2] == 6;
			LiftCheck(TEXT("brain: the sweep (stops for its own way first)"), Sim.Violations == 0 && bOrder && Sim.B.Quiet(), FString::Printf(TEXT("stops in order: %s (4 0 6 expected), %d violations %s"), *LiftArrivalText(A), Sim.Violations, *Sim.First));
		}
		// a stop asked for in the cruise is added when the braking can still begin, and left for the way back when not
		{
			FLiftSim Sim;
			Sim.Cfg = Cfg;
			Sim.Init(S, Top);
			Sim.B.CarCall(0);
			Sim.Run(0.1f);
			const FAstraLiftProfile P = FAstraLiftProfile::Make(S[Top] - S[0], Cfg.VmaxCmS, Cfg.AccelCmS2);
			Sim.Run(P.Ta + 0.3f);
			Sim.B.CarCall(2);
			Sim.RunQuiet(400.f);
			const TArray<int32> A = Sim.Arrivals();
			LiftCheck(TEXT("brain: a stop added in the cruise"), Sim.Violations == 0 && Sim.Count(ET::Retarget) == 1 && A.Num() == 2 && A[0] == 2 && A[1] == 0, FString::Printf(TEXT("%d retargets, stops %s (2 0 expected), %d violations %s"), Sim.Count(ET::Retarget), *LiftArrivalText(A), Sim.Violations, *Sim.First));
		}
		{
			FLiftSim Sim;
			Sim.Cfg = Cfg;
			Sim.Init(S, Top);
			Sim.B.CarCall(0);
			Sim.Run(0.1f);
			const FAstraLiftProfile P = FAstraLiftProfile::Make(S[Top] - S[0], Cfg.VmaxCmS, Cfg.AccelCmS2);
			Sim.Run(P.Ta + 2.2f);
			Sim.B.CarCall(2);
			Sim.RunQuiet(400.f);
			const TArray<int32> A = Sim.Arrivals();
			LiftCheck(TEXT("brain: a stop asked too late waits"), Sim.Violations == 0 && Sim.Count(ET::Retarget) == 0 && A.Num() == 2 && A[0] == 0 && A[1] == 2, FString::Printf(TEXT("%d retargets, stops %s (0 2 expected), %d violations %s"), Sim.Count(ET::Retarget), *LiftArrivalText(A), Sim.Violations, *Sim.First));
		}
		// the doors wait for a deck that is not there: shut at the landing, open when it is; made ready by force when it never comes
		{
			FLiftSim Sim;
			Sim.Cfg = Cfg;
			double ReadyAt = 1.0e9;
			int32 Forced = 0;
			FAstraLiftBrain::FHooks H;
			H.DeckReady = [&Sim, &ReadyAt](int32 L) { return L != 0 || Sim.T >= ReadyAt; };
			H.ForceDeck = [&Forced](int32) { ++Forced; };
			Sim.Init(S, Top, H);
			Sim.B.CarCall(0);
			ReadyAt = 4.0 + FAstraLiftProfile::Make(S[Top] - S[0], Cfg.VmaxCmS, Cfg.AccelCmS2).T;        // four seconds after the car stops
			Sim.RunQuiet(400.f);
			double Arrived = 0.0, Opened = 0.0;
			for (const auto& E : Sim.Log)
			{
				Arrived = E.Value.Type == ET::Arrive ? E.Key : Arrived;
				Opened = E.Value.Type == ET::DoorsOpening ? E.Key : Opened;
			}
			LiftCheck(TEXT("brain: the doors wait for the deck"), Sim.Violations == 0 && Sim.Count(ET::Held) == 1 && Forced == 0 && Opened >= ReadyAt - 0.1 && Opened - ReadyAt < 0.3,
			      FString::Printf(TEXT("arrived %.1f s, deck ready %.1f s, doors opened %.1f s, forced %d"), Arrived, ReadyAt, Opened, Forced));
			FLiftSim Never;
			Never.Cfg = Cfg;
			int32 Forced2 = 0;
			FAstraLiftBrain::FHooks H2;
			H2.DeckReady = [](int32 L) { return L != 0; };
			H2.ForceDeck = [&Forced2](int32) { ++Forced2; };
			Never.Init(S, Top, H2);
			Never.B.CarCall(0);
			Never.RunQuiet(400.f);
			double Arr = 0.0, Op = 0.0;
			for (const auto& E : Never.Log)
			{
				Arr = E.Value.Type == ET::Arrive ? E.Key : Arr;
				Op = E.Value.Type == ET::DoorsOpening ? E.Key : Op;
			}
			LiftCheck(TEXT("brain: the deck that never comes is forced"), Never.Violations == 0 && Forced2 == 1 && Never.Count(ET::Forced) == 1 && FMath::Abs((Op - Arr) - Cfg.HeldForceS) < 0.2,
			      FString::Printf(TEXT("forced %d time(s), the doors opened %.1f s after the car stopped (%.1f s wait)"), Forced2, Op - Arr, Cfg.HeldForceS));
		}
		// the doors never close on someone, and wait for them
		{
			FLiftSim Sim;
			Sim.Cfg = Cfg;
			bool bBusy = false;
			FAstraLiftBrain::FHooks H;
			H.DoorwayBusy = [&bBusy](int32) { return bBusy; };
			Sim.Init(S, 3, H);
			Sim.B.HallCall(3, 0);
			Sim.Run(Cfg.DoorS + 1.0f);                       // the doors are open, the dwell is running
			bBusy = true;
			Sim.Run(Cfg.DwellS + 6.f);                        // someone stands in the doorway: far longer than the dwell
			const bool bStillOpen = Sim.B.State() == FAstraLiftBrain::EState::Open && Sim.B.DoorOpen() >= 1.f;
			bBusy = false;
			// they step out; the doors begin to close; someone steps in
			while (Sim.B.State() != FAstraLiftBrain::EState::Closing && Sim.T < 100.0)
			{
				Sim.Step();
			}
			Sim.Run(0.4f);
			bBusy = true;
			Sim.Run(0.2f);
			const bool bReopen = Sim.Count(ET::DoorsReopen) >= 1;
			bBusy = false;
			Sim.RunQuiet(60.f);
			LiftCheck(TEXT("brain: the doors never close on someone"), Sim.Violations == 0 && bStillOpen && bReopen && Sim.B.Quiet(), FString::Printf(TEXT("held open %d, went back when someone stepped in %d, then closed %d"), bStillOpen, bReopen, Sim.B.Quiet()));
		}
	}

	// ============================================================================================================================ the rush hour

	struct FLiftRider
	{
		int32 Id = 0;
		double Born = 0.0;
		int32 From = 0, To = 0, Car = 0;
		enum class ESt : uint8 { Coming, Waiting, Boarding, Riding, Alighting, Done } St = ESt::Coming;
		double CalledAt = 0.0, BoardedAt = 0.0, DoneAt = 0.0, BusyUntil = 0.0;
	};

	struct FLiftRushResult
	{
		TArray<double> Waits, Rides, Totals;
		double Last = 0.0;
		int32 Done = 0, Violations = 0, Stops = 0, Starved = 0;
		double MaxIdleWithCalls = 0.0;
		FString First;
	};

	/** People who use the lifts as the crew does: they call from the landing for the way they go, wait, get in when the car is open and going their way, choose
	 *  their stop, get out where it opens. The cars are the brain alone, on a clock; a person in a doorway holds the doors for a second or two. */
	FLiftRushResult LiftRushHour(const FAstraLiftLine& L, int32 NumCars, int32 NumRiders, int32 Seed, double Spread)
	{
		FRandomStream R(Seed);
		const TArray<float> S = LiftStopsOf(L);
		const int32 N = S.Num();
		FAstraLiftBrain::FConfig Cfg;
		Cfg.VmaxCmS = L.SpeedCmS;
		Cfg.AccelCmS2 = L.AccelCmS2;
		TArray<FLiftRider> Riders;
		// the morning: most come from the top (the bridge's deck) and the middle (Crew Services), going anywhere
		for (int32 I = 0; I < NumRiders; ++I)
		{
			FLiftRider Rd;
			Rd.Id = I;
			Rd.Born = R.FRand() * Spread;
			const float P = R.FRand();
			Rd.From = P < 0.35f ? N - 1 : P < 0.7f ? FMath::Max(0, N - 4) : R.RandRange(0, N - 1);
			do { Rd.To = R.RandRange(0, N - 1); } while (Rd.To == Rd.From);
			Riders.Add(Rd);
		}
		Riders.Sort([](const FLiftRider& A, const FLiftRider& B) { return A.Born < B.Born; });
		struct FCarSim
		{
			FAstraLiftBrain B;
			TArray<int32> Aboard;
			double IdleSince = -1.0;
			float PrevV = 0.f;
		};
		TArray<FCarSim> Cars;
		Cars.SetNum(NumCars);
		double T = 0.0;
		FLiftRushResult Out;
		const int32 Capacity = 8;
		for (int32 C = 0; C < NumCars; ++C)
		{
			FAstraLiftBrain::FHooks H;
			H.DoorwayBusy = [&Riders, &T, C](int32 Landing)
			{
				for (const FLiftRider& Rd : Riders)
				{
					if (Rd.Car == C && Rd.BusyUntil > T && (Rd.St == FLiftRider::ESt::Boarding || Rd.St == FLiftRider::ESt::Alighting))
					{
						return true;
					}
				}
				return false;
			};
			H.Full = [&Cars, C, Capacity]() { return Cars[C].Aboard.Num() >= Capacity; };
			Cars[C].B.Init(S, C % 2 ? 0 : N - 1, Cfg, H);
		}
		const float Dt = 0.05f;
		using ES = FLiftRider::ESt;
		while (T < 1500.0 && Out.Done < NumRiders)
		{
			for (FLiftRider& Rd : Riders)
			{
				if (Rd.St == ES::Coming && Rd.Born <= T)
				{
					// the rider takes the car that will open at their landing soonest (two shafts of a bank: the one that comes first)
					int32 Best = 0;
					float BestEta = 1.0e9f;
					for (int32 C = 0; C < NumCars; ++C)
					{
						const float Eta = Cars[C].B.EstimateArrival(Rd.From, Rd.To > Rd.From ? 1 : -1);
						if (Eta < BestEta)
						{
							BestEta = Eta;
							Best = C;
						}
					}
					Rd.Car = Best;
					Rd.St = ES::Waiting;
					Rd.CalledAt = T;
					Cars[Best].B.HallCall(Rd.From, Rd.To > Rd.From ? 1 : -1);
				}
			}
			for (int32 C = 0; C < NumCars; ++C)
			{
				FCarSim& Car = Cars[C];
				FAstraLiftBrain& B = Car.B;
				B.Tick(Dt);
				for (const FAstraLiftEvent& E : B.Events())
				{
					Out.Stops += E.Type == FAstraLiftEvent::EType::Arrive ? 1 : 0;
					if (GAstraLiftTrace)
					{
						UE_LOG(LogASTRA, Display, TEXT("[Lift]   t=%.2f car %d event %d landing %d other %d (state %d, heading %d, doors %.2f)"), T, C, (int32)E.Type, E.Landing, E.Other, (int32)B.State(), B.Heading(), B.DoorOpen());
					}
				}
				B.Events().Reset();
				using EState = FAstraLiftBrain::EState;
				if (B.DoorOpen() > 0.f && (B.AtLanding() == INDEX_NONE || FMath::Abs(B.V()) > 0.01f || FMath::Abs(B.S() - S[B.AtLanding()]) > 0.01f))
				{
					Out.First = Out.Violations == 0 ? FString::Printf(TEXT("doors %.2f open away from a landing at %.1f s"), B.DoorOpen(), T) : Out.First;
					++Out.Violations;
				}
				if (B.State() == EState::Moving && B.DoorOpen() > 0.f)
				{
					Out.First = Out.Violations == 0 ? FString::Printf(TEXT("moving with open doors at %.1f s"), T) : Out.First;
					++Out.Violations;
				}
				// people: out where the car opens at their stop, in when it opens at theirs and goes their way (and has room)
				const bool bOpen = B.State() == EState::Open || (B.State() == EState::Opening && B.DoorOpen() > 0.6f);
				for (FLiftRider& Rd : Riders)
				{
					if (Rd.Car != C)
					{
						continue;
					}
					if (Rd.St == ES::Riding && bOpen && B.AtLanding() == Rd.To)
					{
						Rd.St = ES::Alighting;
						Rd.BusyUntil = T + 1.0 + R.FRand() * 0.6;
						Car.Aboard.Remove(Rd.Id);
					}
					else if (Rd.St == ES::Waiting && bOpen && B.AtLanding() == Rd.From && Car.Aboard.Num() + 0 < Capacity && (B.Heading() == 0 || B.Heading() == (Rd.To > Rd.From ? 1 : -1)))
					{
						Rd.St = ES::Boarding;
						Rd.BusyUntil = T + 1.2 + R.FRand() * 0.8;
						Rd.BoardedAt = T;
						Car.Aboard.Add(Rd.Id);
					}
					else if (Rd.St == ES::Boarding && Rd.BusyUntil <= T)
					{
						Rd.St = ES::Riding;
						B.CarCall(Rd.To);
					}
					else if (Rd.St == ES::Alighting && Rd.BusyUntil <= T)
					{
						Rd.St = ES::Done;
						Rd.DoneAt = T;
						++Out.Done;
						Out.Waits.Add(Rd.BoardedAt - Rd.CalledAt);
						Out.Rides.Add(Rd.DoneAt - Rd.BoardedAt);
						Out.Totals.Add(Rd.DoneAt - Rd.CalledAt);
						Out.Last = T;
					}
					else if (Rd.St == ES::Waiting && !B.HasHallCall(Rd.From, Rd.To > Rd.From ? 1 : -1) &&
					         !(B.AtLanding() == Rd.From && (B.State() == EState::Opening || B.State() == EState::Open || B.State() == EState::Closing)))
					{
						B.HallCall(Rd.From, Rd.To > Rd.From ? 1 : -1);             // the car left without them (full, or going the other way): they press again
					}
				}
				// a car must not stand idle, doors shut, with a call waiting
				if (B.State() == EState::Idle && B.AnyRequest())
				{
					Car.IdleSince = Car.IdleSince < 0.0 ? T : Car.IdleSince;
					Out.MaxIdleWithCalls = FMath::Max(Out.MaxIdleWithCalls, T - Car.IdleSince);
				}
				else
				{
					Car.IdleSince = -1.0;
				}
			}
			T += Dt;
		}
		Out.Starved = NumRiders - Out.Done;
		if (Out.Starved > 0)
		{
			// what is stuck, for whoever has to find out why
			for (int32 C = 0; C < NumCars; ++C)
			{
				const FAstraLiftBrain& B = Cars[C].B;
				Out.First += FString::Printf(TEXT(" [car %d: state %d at %d heading %d doors %.2f aboard %d any %d]"), C, (int32)B.State(), B.AtLanding(), B.Heading(), B.DoorOpen(), Cars[C].Aboard.Num(), B.AnyRequest());
			}
			int32 Shown = 0;
			for (const FLiftRider& Rd : Riders)
			{
				if (Rd.St != ES::Done && Shown++ < 4)
				{
					Out.First += FString::Printf(TEXT(" [rider %d: state %d %d->%d car %d]"), Rd.Id, (int32)Rd.St, Rd.From, Rd.To, Rd.Car);
				}
			}
		}
		return Out;
	}

	void LiftTestRush(const FAstraLiftLine& L, int32 Riders, int32 Seed)
	{
		for (const int32 Cars : {1, 2})
		{
			const FLiftRushResult R = LiftRushHour(L, Cars, Riders, Seed, 90.0);
			const double Worst = LiftPercentile(R.Waits, 1.0);
			LiftCheck(Cars == 1 ? TEXT("rush: 20 riders, one shaft") : TEXT("rush: 20 riders, a bank of two shafts"),
			      R.Done == Riders && R.Violations == 0 && R.MaxIdleWithCalls < 1.0 && Worst < (Cars == 1 ? 180.0 : 130.0),
			      FString::Printf(TEXT("%d of %d delivered in %.0f s; wait avg %.1f, median %.1f, p95 %.1f, worst %.1f s; ride avg %.1f s; %d stops; idle with calls at most %.2f s; %d violations %s"),
			                      R.Done, Riders, R.Last, LiftMean(R.Waits), LiftPercentile(R.Waits, 0.5), LiftPercentile(R.Waits, 0.95), Worst, LiftMean(R.Rides), R.Stops, R.MaxIdleWithCalls, R.Violations, *R.First));
		}
	}
}

// ============================================================================================================================ the world

namespace
{
	/** One headless world for every scenario that needs one (a world made and destroyed again for each of them leaves the garbage collector with the debris of the
	 *  last: what a scenario builds in it is taken out again when it is done). */
	struct FLiftWorldBench
	{
		UWorld* World = nullptr;
		UAstraLiftSubsystem* Lifts = nullptr;
		TArray<TWeakObjectPtr<AActor>> Spawned;          // what a scenario put in the world besides the lifts: the arena, the Captain
		int64 Frames = 0;
		double WorldMsSum = 0.0, WorldMsMax = 0.0;

		bool Create()
		{
			if (World)
			{
				Clear();
				return true;
			}
			World = UWorld::CreateWorld(EWorldType::Game, false, TEXT("AstraLiftSim"));
			FWorldContext& Ctx = GEngine->CreateNewWorldContext(EWorldType::Game);
			Ctx.SetCurrentWorld(World);
			World->InitializeActorsForPlay(FURL());
			World->BeginPlay();
			// (no game mode here to start play: without it nothing that is spawned begins play or ticks, a Captain's movement included)
			if (AWorldSettings* Settings = World->GetWorldSettings())
			{
				Settings->NotifyBeginPlay();
				Settings->NotifyMatchStarted();
			}
			Lifts = World->GetSubsystem<UAstraLiftSubsystem>();
			if (Lifts)
			{
				Lifts->bBench = true;
			}
			return Lifts != nullptr;
		}
		void Step(float Dt)
		{
			const double T0 = FPlatformTime::Seconds();
			const int64 Before = Lifts->TickCount();
			++GFrameCounter;                 // (a tick function runs once per engine frame: a bench that never ends a frame would run each of them once)
			World->Tick(LEVELTICK_All, Dt);
			if (Lifts->TickCount() == Before)
			{
				FTickableGameObject::TickObjects(World, LEVELTICK_All, false, Dt);       // (the world tick did not reach the tickable subsystems)
				if (Lifts->TickCount() == Before)
				{
					Lifts->Tick(Dt);
				}
			}
			const double Ms = (FPlatformTime::Seconds() - T0) * 1000.0;
			WorldMsSum += Ms;
			WorldMsMax = FMath::Max(WorldMsMax, Ms);
			++Frames;
		}
		void Run(float Seconds, float Dt = 1.f / 60.f)
		{
			for (float T = 0.f; T < Seconds; T += Dt)
			{
				Step(Dt);
			}
		}
		/** The world as a scenario wants it: the lifts of a network, an arena round them, nothing else. */
		void Build(const FAstraLiftNetwork& N)
		{
			Clear();
			FAstraLiftNetwork Copy = N;
			Lifts->SetNetwork(MoveTemp(Copy));
			Lifts->BuildNow();
			AActor* Arena = World->SpawnActor<AActor>();
			Arena->SetRootComponent(NewObject<USceneComponent>(Arena, TEXT("Root")));
			Arena->GetRootComponent()->RegisterComponent();
			AstraLiftArena::Build(Arena, Lifts->Network(), false);
			Spawned.Add(Arena);
			Run(0.3f);
		}
		void Clear()
		{
			Lifts->Reset();
			Lifts->bBench = true;
			for (const TWeakObjectPtr<AActor>& A : Spawned)
			{
				if (A.IsValid())
				{
					A->Destroy();
				}
			}
			Spawned.Reset();
			Step(1.f / 60.f);
		}
		/** A scenario is done with the world: its lifts, its arena and its Captain go. */
		void Destroy()
		{
			if (World)
			{
				Clear();
			}
		}
		/** The bench is done with it. */
		void Shutdown()
		{
			if (World)
			{
				Clear();
				// the world began play (see Create), so it must end it: every actor's EndPlay, then the world itself (a world cleaned up while it still believes it is
				// playing leaves the plugins' managers, the water's buoyancy manager among them, to be destroyed half made, and the engine crashes on its way out)
				TArray<AActor*> All;
				for (FActorIterator It(World); It; ++It)
				{
					All.Add(*It);
				}
				for (AActor* A : All)
				{
					if (IsValid(A) && A->HasActorBegunPlay())
					{
						A->RouteEndPlay(EEndPlayReason::Quit);
					}
				}
				World->SetBegunPlay(false);
				CollectGarbage(GARBAGE_COLLECTION_KEEPFLAGS);
				GEngine->DestroyWorldContext(World);
				World->DestroyWorld(false);
				World = nullptr;
			}
		}
	};

	FLiftWorldBench& LiftBench()
	{
		static FLiftWorldBench B;
		return B;
	}

	/** What a ride is checked for, frame by frame. */
	struct FLiftRideLog
	{
		float MaxDevCm = 0.f;
		int32 FallFrames = 0, UnbasedFrames = 0, DoorBreaks = 0, Frames = 0;
		float MaxSpeed = 0.f;
		FString First;
		FVector Rel0 = FVector::ZeroVector;
	};

	ACharacter* LiftSpawnCaptain(FLiftWorldBench& W, const FVector& FeetAt, const FRotator& Facing)
	{
		FActorSpawnParameters P;
		P.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
		ACharacter* C = W.World->SpawnActor<ACharacter>(ACharacter::StaticClass(), FeetAt + FVector(0.f, 0.f, 100.f), Facing, P);
		if (C)
		{
			C->GetCapsuleComponent()->SetCapsuleSize(34.f, 96.f);
			UCharacterMovementComponent* M = C->GetCharacterMovement();
			M->bRunPhysicsWithNoController = true;        // no controller in the bench: the movement runs by itself
			M->MaxWalkSpeed = 380.f;
			M->MaxAcceleration = 1800.f;
			M->BrakingDecelerationWalking = 2400.f;
			M->GroundFriction = 9.f;
			M->SetMovementMode(MOVE_Falling);
			W.Lifts->SetCaptain(C);
			W.Spawned.Add(C);
		}
		return C;
	}

	/** The car's door and its landing's, checked every frame: open only with the car stopped at that landing, and no other landing's open. */
	void LiftCheckDoors(FLiftWorldBench& W, int32 Line, FLiftRideLog& Log)
	{
		const AAstraLiftCar* Car = W.Lifts->CarOf(Line);
		const FAstraLiftLine& L = W.Lifts->Network().Lines[Line];
		const FAstraLiftBrain& B = Car->Brain;
		const int32 At = B.AtLanding();
		bool bOk = true;
		FString Why;
		if (B.DoorOpen() > 0.f)
		{
			const bool bStill = At != INDEX_NONE && FMath::Abs(B.V()) < 0.01f && FMath::Abs(Car->GetActorLocation().Z - L.Stops[At].FloorZ) < 0.2f;
			bOk &= bStill;
			Why = TEXT("the car's doors open while it is not stopped at a landing");
		}
		for (int32 S = 0; S < L.Stops.Num(); ++S)
		{
			const AAstraLiftLanding* Landing = W.Lifts->LandingOf(Line, S);
			if (Landing && Landing->GetOpen() > 0.001f && (S != At || B.DoorOpen() <= 0.f))
			{
				bOk = false;
				Why = FString::Printf(TEXT("the doors at stop %d are %.2f open and the car is not there with its own"), S, Landing->GetOpen());
			}
		}
		if (!bOk)
		{
			if (Log.DoorBreaks++ == 0)
			{
				Log.First = Why;
			}
		}
	}

	/** One frame of a ride's record: where the Captain is in the car, whether he is standing on it. */
	void LiftRecordRide(FLiftWorldBench& W, int32 Line, ACharacter* C, FLiftRideLog& Log)
	{
		const AAstraLiftCar* Car = W.Lifts->CarOf(Line);
		const FVector Rel = Car->ToLocal(C->GetActorLocation());
		Log.MaxDevCm = FMath::Max(Log.MaxDevCm, (float)(Rel - Log.Rel0).Size());
		UCharacterMovementComponent* M = C->GetCharacterMovement();
		if (M->MovementMode != MOVE_Walking && Log.FallFrames == 0)
		{
			UE_LOG(LogASTRA, Display, TEXT("[Lift]   he left the floor at s %.1f cm (v %.1f cm/s, doors %.2f, state %d): in the car at %s, mode %d"), Car->Brain.S(), Car->Brain.V(), Car->Brain.DoorOpen(), (int32)Car->Brain.State(),
			       *Rel.ToString(), (int32)M->MovementMode);
		}
		Log.FallFrames += M->MovementMode != MOVE_Walking ? 1 : 0;
		Log.UnbasedFrames += C->GetMovementBase() != Car->FloorComponent() ? 1 : 0;
		Log.MaxSpeed = FMath::Max(Log.MaxSpeed, (float)FMath::Abs(Car->Brain.V()));
		++Log.Frames;
		LiftCheckDoors(W, Line, Log);
	}

	/** Walks the Captain on a line (a unit vector on the floor) for up to Seconds, until Stop() says so. */
	template <typename F>
	bool LiftWalk(FLiftWorldBench& W, ACharacter* C, const FVector& Dir, float Seconds, F Stop, float Dt = 1.f / 60.f)
	{
		for (float T = 0.f; T < Seconds; T += Dt)
		{
			if (Stop())
			{
				return true;
			}
			C->AddMovementInput(Dir, 1.f);
			W.Step(Dt);
		}
		return Stop();
	}

	void LiftTestWorld(const FAstraLiftNetwork& Net, bool bAll, const FString& Which)
	{
		FLiftWorldBench& W = LiftBench();
		if (!W.Create())
		{
			LiftCheck(TEXT("world: the lifts' subsystem"), false, TEXT("the world has no UAstraLiftSubsystem"));
			return;
		}
		W.Build(Net);
		LiftCheck(TEXT("world: the lifts are built"), W.Lifts->IsBuilt() && W.Lifts->NumLines() == Net.Lines.Num(),
		      FString::Printf(TEXT("%d lines (%s)"), W.Lifts->NumLines(), *W.Lifts->Describe().Left(120).Replace(TEXT("\n"), TEXT(" | "))));
		const int32 Tl = Net.FindLine(TEXT("tl_a"));
		if (Tl == INDEX_NONE)
		{
			LiftCheck(TEXT("world: the test plan's turbolift"), false, TEXT("no line tl_a in the plan"));
			W.Destroy();
			return;
		}
		const FAstraLiftLine& L = Net.Lines[Tl];
		AAstraLiftCar* Car = W.Lifts->CarOf(Tl);
		const int32 Deck1 = L.FindStopByDeck(1), Deck9 = L.FindStopByDeck(9), Deck5 = L.FindStopByDeck(5);
		const FAstraLiftStop& S1 = L.Stops[Deck1];
		// the Captain on the lobby of Deck 1, two metres from the doors
		ACharacter* C = LiftSpawnCaptain(W, S1.DoorCm + S1.Out * 220.f, FRotator(0.f, L.FrontYaw + 180.f, 0.f));
		W.Run(0.8f);
		const UCharacterMovementComponent* M = C->GetCharacterMovement();
		LiftCheck(TEXT("world: the Captain stands on the lobby"), M->MovementMode == MOVE_Walking && FMath::Abs(C->GetActorLocation().Z - 96.f - S1.FloorZ) < 4.f,
		      FString::Printf(TEXT("movement mode %d, feet %.1f cm over the floor (a headless world with physics queries?)"), (int32)M->MovementMode, C->GetActorLocation().Z - 96.f - S1.FloorZ));
		if (M->MovementMode != MOVE_Walking)
		{
			W.Destroy();
			return;
		}
		auto FeetZ = [&C]() { return C->GetActorLocation().Z - C->GetCapsuleComponent()->GetScaledCapsuleHalfHeight(); };

		// ---- the call, and the doors
		FString Notice;
		const bool bCalled = W.Lifts->CallAt(Tl, Deck1, Notice);
		const bool bOpened = [&]() { for (float T = 0.f; T < 8.f; T += 1.f / 60.f) { W.Step(1.f / 60.f); if (Car->Brain.State() == FAstraLiftBrain::EState::Open) { return true; } } return false; }();
		LiftCheck(TEXT("world: a call opens the doors where the car is"), bCalled && bOpened && Car->Brain.DoorOpen() >= 1.f, FString::Printf(TEXT("%s; doors %.2f"), *Notice, Car->Brain.DoorOpen()));

		// ---- in
		const bool bIn = LiftWalk(W, C, -S1.Out, 5.f, [&]() { return Car->Contains(C->GetActorLocation(), 40.f); });
		W.Run(0.5f);
		LiftCheck(TEXT("world: the Captain walks into the car"), bIn && C->GetMovementBase() == Car->FloorComponent(), FString::Printf(TEXT("inside %d, based on the car's floor %d"), bIn, C->GetMovementBase() == Car->FloorComponent()));

		// ---- the ride, Deck 1 to Deck 9 (66 m down)
		FLiftRideLog Log;
		Log.Rel0 = Car->ToLocal(C->GetActorLocation());
		W.Run(0.4f);                               // (the subsystem notices he is in a car at its slow rate)
		FString Detail;
		const bool bGo = W.Lifts->GoToDeck(9, Detail);
		const double T0 = W.World->GetTimeSeconds();
		float Travel = 0.f;
		bool bArrived = false;
		for (float T = 0.f; T < 60.f; T += 1.f / 60.f)
		{
			W.Step(1.f / 60.f);
			LiftRecordRide(W, Tl, C, Log);
			if (Car->Brain.AtLanding() == Deck9 && Car->Brain.DoorOpen() >= 1.f)
			{
				bArrived = true;
				break;
			}
		}
		Travel = (float)(W.World->GetTimeSeconds() - T0);
		const FVector Rel1 = Car->ToLocal(C->GetActorLocation());
		const float EndDev = (float)(Rel1 - Log.Rel0).Size();
		LiftCheck(TEXT("world: Deck 1 to Deck 9: arrives with the car"), bGo && bArrived && EndDev < 2.f && FMath::Abs(Car->GetActorLocation().Z - L.Stops[Deck9].FloorZ) < 0.1f,
		      FString::Printf(TEXT("%s; %.1f s; %.1f cm from where he stood in the car (2 allowed), the car %.2f cm from the landing; peak %.1f m/s"), *Detail, Travel, EndDev,
		                      Car->GetActorLocation().Z - L.Stops[Deck9].FloorZ, Log.MaxSpeed / 100.f));
		LiftCheck(TEXT("world: never falls, never off the car's floor"), Log.FallFrames == 0 && Log.UnbasedFrames == 0 && Log.MaxDevCm < 2.f,
		      FString::Printf(TEXT("%d frames: %d falling, %d not on the car's floor, he drifted at most %.2f cm in the car"), Log.Frames, Log.FallFrames, Log.UnbasedFrames, Log.MaxDevCm));
		LiftCheck(TEXT("world: doors only at the landing, only with the car stopped"), Log.DoorBreaks == 0, FString::Printf(TEXT("%d frames broke it %s"), Log.DoorBreaks, *Log.First));

		// ---- out onto Deck 9's lobby
		const FAstraLiftStop& S9 = L.Stops[Deck9];
		const bool bOut = LiftWalk(W, C, S9.Out, 5.f, [&]() { return FVector::DotProduct(C->GetActorLocation() - S9.DoorCm, S9.Out) > 160.f; });
		W.Run(0.4f);
		LiftCheck(TEXT("world: out onto the lobby of Deck 9"), bOut && C->GetCharacterMovement()->MovementMode == MOVE_Walking && FMath::Abs(FeetZ() - S9.FloorZ) < 4.f && C->GetMovementBase() != Car->FloorComponent(),
		      FString::Printf(TEXT("out %d, feet %.2f cm from the floor, mode %d"), bOut, FeetZ() - S9.FloorZ, (int32)C->GetCharacterMovement()->MovementMode));

		// ---- the way back, up to Deck 5 (16 m), at thirty frames a second (a hitch is no reason to fall)
		FLiftRideLog Up;
		W.Lifts->CallAt(Tl, Deck9, Notice);
		LiftWalk(W, C, FVector::ZeroVector, 15.f, [&]() { return Car->Brain.AtLanding() == Deck9 && Car->Brain.DoorOpen() >= 1.f; }, 1.f / 30.f);
		const bool bBack = LiftWalk(W, C, -S9.Out, 5.f, [&]() { return Car->Contains(C->GetActorLocation(), 40.f); }, 1.f / 30.f);
		LiftWalk(W, C, FVector::ZeroVector, 0.6f, []() { return false; }, 1.f / 30.f);
		Up.Rel0 = Car->ToLocal(C->GetActorLocation());
		FString D2;
		const bool bGo2 = W.Lifts->GoToDeck(5, D2);
		bool bArr2 = false;
		for (float T = 0.f; T < 40.f; T += 1.f / 30.f)
		{
			W.Step(1.f / 30.f);
			LiftRecordRide(W, Tl, C, Up);
			if (Car->Brain.AtLanding() == Deck5 && Car->Brain.DoorOpen() >= 1.f)
			{
				bArr2 = true;
				break;
			}
		}
		const float EndDev2 = (float)(Car->ToLocal(C->GetActorLocation()) - Up.Rel0).Size();
		LiftCheck(TEXT("world: Deck 9 up to Deck 5, at 30 fps"), bBack && bGo2 && bArr2 && EndDev2 < 2.f && Up.FallFrames == 0 && Up.UnbasedFrames == 0 && Up.DoorBreaks == 0,
		      FString::Printf(TEXT("%s; %.2f cm at the end, drift at most %.2f cm, %d falling, %d off the floor, %d door breaks"), *D2, EndDev2, Up.MaxDevCm, Up.FallFrames, Up.UnbasedFrames, Up.DoorBreaks));

		if (bAll || Which == TEXT("doors"))
		{
			// ---- the doors do not close on the Captain: he stands in the doorway of Deck 5 while the dwell runs out
			const FAstraLiftStop& S5 = L.Stops[Deck5];
			const bool bOutAgain = LiftWalk(W, C, S5.Out, 5.f, [&]() { return FVector::DotProduct(C->GetActorLocation() - S5.DoorCm, S5.Out) > 10.f; }, 1.f / 60.f);
			LiftWalk(W, C, FVector::ZeroVector, 0.3f, []() { return false; });
			// he stands on the threshold (in the doorway) for twice the dwell
			W.Run(Car->Brain.Config().DwellS * 2.f + 2.f);
			const bool bHeld = Car->Brain.State() == FAstraLiftBrain::EState::Open && Car->Brain.DoorOpen() >= 1.f;
			LiftWalk(W, C, S5.Out, 3.f, [&]() { return FVector::DotProduct(C->GetActorLocation() - S5.DoorCm, S5.Out) > 200.f; });
			const bool bClosed = [&]() { for (float T = 0.f; T < 12.f; T += 1.f / 60.f) { W.Step(1.f / 60.f); if (Car->Brain.State() == FAstraLiftBrain::EState::Idle && Car->Brain.DoorOpen() <= 0.f) { return true; } } return false; }();
			LiftCheck(TEXT("world: the doors wait for the Captain in the doorway"), bOutAgain && bHeld && bClosed, FString::Printf(TEXT("held open while he stood there %d, closed after he stepped away %d"), bHeld, bClosed));
		}
	}

	// ============================================================================================================================ the crew's riders

	/** A person of the bench: an actor with nothing but a place, and a rider that takes it from a landing to another (the same code that carries the life simulation's bodies). */
	struct FLiftWalker
	{
		AActor* A = nullptr;
		FAstraLiftRider R;
		int32 From = INDEX_NONE, To = INDEX_NONE;
		double BornAt = 0.0, DoneAt = -1.0;
		bool bBegun = false;
	};

	AActor* LiftSpawnWalker(FLiftWorldBench& W, const FVector& Feet)
	{
		AActor* A = W.World->SpawnActor<AActor>();
		USceneComponent* Root = NewObject<USceneComponent>(A, TEXT("Root"));
		Root->SetMobility(EComponentMobility::Movable);
		A->SetRootComponent(Root);
		Root->RegisterComponent();
		A->SetActorLocation(Feet);
		W.Spawned.Add(A);
		return A;
	}

	struct FLiftWalkResult
	{
		int32 Done = 0, Failed = 0, DoorViol = 0, InsideViol = 0, MovedInDoorway = 0, SharedSlots = 0, Frames = 0;
		float MinApart = 1.0e9f, MinFromCaptain = 1.0e9f, Last = 0.f;
		TArray<double> Waits, Rides, Totals;
		FString First;
		int32 CaptainFalls = 0, CaptainUnbased = 0;
	};

	/** The people go from a landing to another, each at its own time, and the world runs. Optionally with the Captain standing in the car at a place of its own. */
	FLiftWalkResult LiftRunWalkers(FLiftWorldBench& W, int32 Line, int32 Num, int32 Seed, double Spread, ACharacter* Captain, float MaxSeconds)
	{
		FLiftWalkResult Out;
		const FAstraLiftLine& L = W.Lifts->Network().Lines[Line];
		AAstraLiftCar* Car = W.Lifts->CarOf(Line);
		FRandomStream Rand(Seed);
		TArray<FLiftWalker> People;
		People.SetNum(Num);
		const int32 NumStops = L.Stops.Num();
		for (FLiftWalker& P : People)
		{
			P.From = Rand.RandRange(0, NumStops - 1);
			do { P.To = Rand.RandRange(0, NumStops - 1); } while (P.To == P.From);
			P.BornAt = Rand.FRand() * Spread;
		}
		const float Dt = 1.f / 60.f;
		const float Walk = 125.f;
		FString Fall;
		for (float T = 0.f; T < MaxSeconds; T += Dt)
		{
			for (int32 I = 0; I < People.Num(); ++I)
			{
				FLiftWalker& P = People[I];
				if (!P.bBegun && T >= P.BornAt)
				{
					const FAstraLiftStop& S = L.Stops[P.From];
					const FVector Side = FVector::CrossProduct(S.Out, FVector::UpVector).GetSafeNormal();
					P.A = LiftSpawnWalker(W, S.WaitCm() + Side * Rand.FRandRange(-45.f, 45.f) + S.Out * Rand.FRandRange(-20.f, 60.f));
					P.bBegun = P.R.Begin(W.Lifts, P.A, 1000 + I, Line, P.From, P.To, L.Stops[P.To].WaitCm());
					if (!P.bBegun)
					{
						++Out.Failed;
						P.DoneAt = T;
					}
				}
			}
			W.Step(Dt);
			int32 Active = 0;
			for (FLiftWalker& P : People)
			{
				if (!P.bBegun || P.DoneAt >= 0.0)
				{
					Active += (!P.bBegun && P.DoneAt < 0.0) ? 1 : 0;
					continue;
				}
				const FAstraLiftRider::EStep S = P.R.Tick(Dt, Walk);
				const FVector Feet = P.A->GetActorLocation();
				if (P.R.Walking())
				{
					// the doors never close on someone: a walker in a doorway has it open, and the car does not move
					const AAstraLiftLanding* Landing = W.Lifts->LandingOf(Line, P.R.Step() == FAstraLiftRider::EStep::Board ? P.From : P.To);
					if (Landing && Landing->InDoorway(Feet, 20.f))
					{
						if (Landing->GetOpen() < 0.2f)
						{
							if (Out.DoorViol++ == 0)
							{
								Out.First = FString::Printf(TEXT("t %.1f s: a walker is in the doorway of stop %d with the doors %.2f open (%s)"), T, P.R.Step() == FAstraLiftRider::EStep::Board ? P.From : P.To, Landing->GetOpen(), P.R.StepName());
							}
						}
						if (FMath::Abs(Car->Brain.V()) > 0.5f)
						{
							++Out.MovedInDoorway;
						}
					}
				}
				if (P.R.Step() == FAstraLiftRider::EStep::Inside && P.R.IsAttached() && !Car->Contains(Feet, 10.f))
				{
					if (Out.InsideViol++ == 0)
					{
						Out.First = FString::Printf(TEXT("t %.1f s: a rider 'inside' stands outside the car at %s (car at s %.0f)"), T, *Car->ToLocal(Feet).ToString(), Car->Brain.S());
					}
				}
				if (S == FAstraLiftRider::EStep::Done || S == FAstraLiftRider::EStep::Failed)
				{
					P.DoneAt = T;
					Out.Done += S == FAstraLiftRider::EStep::Done ? 1 : 0;
					Out.Failed += S == FAstraLiftRider::EStep::Failed ? 1 : 0;
					if (S == FAstraLiftRider::EStep::Done)
					{
						Out.Waits.Add(P.R.WaitedS());
						Out.Rides.Add(P.R.RodeS());
						Out.Totals.Add(T - P.BornAt);
						if (FVector::Dist2D(Feet, L.Stops[P.To].WaitCm()) > 40.f && Out.First.IsEmpty())
						{
							Out.First = FString::Printf(TEXT("a rider finished %.0f cm from where its route goes"), FVector::Dist2D(Feet, L.Stops[P.To].WaitCm()));
						}
					}
					else if (Out.First.IsEmpty())
					{
						Out.First = FString::Printf(TEXT("a rider from stop %d to %d gave up (%s) after %.0f s"), P.From, P.To, P.R.StepName(), T - P.BornAt);
					}
					continue;
				}
				++Active;
			}
			// the people in the car keep their distance from each other and from the Captain
			for (int32 I = 0; I < People.Num(); ++I)
			{
				const FLiftWalker& A = People[I];
				if (!A.bBegun || A.DoneAt >= 0.0 || !A.R.IsAttached() || A.R.Step() != FAstraLiftRider::EStep::Inside)
				{
					continue;
				}
				if (Captain && Car->Contains(Captain->GetActorLocation(), 0.f))
				{
					Out.MinFromCaptain = FMath::Min(Out.MinFromCaptain, FVector::Dist2D(A.A->GetActorLocation(), Captain->GetActorLocation()));
				}
				for (int32 J = I + 1; J < People.Num(); ++J)
				{
					const FLiftWalker& B = People[J];
					if (B.bBegun && B.DoneAt < 0.0 && B.R.IsAttached() && B.R.Step() == FAstraLiftRider::EStep::Inside)
					{
						const float D = FVector::Dist2D(A.A->GetActorLocation(), B.A->GetActorLocation());
						Out.MinApart = FMath::Min(Out.MinApart, D);
						Out.SharedSlots += D < 12.f ? 1 : 0;
					}
				}
			}
			if (Captain)
			{
				UCharacterMovementComponent* M = Captain->GetCharacterMovement();
				Out.CaptainFalls += M->MovementMode != MOVE_Walking ? 1 : 0;
				Out.CaptainUnbased += Captain->GetMovementBase() != Car->FloorComponent() ? 1 : 0;
			}
			++Out.Frames;
			if (Active == 0)
			{
				Out.Last = T;
				break;
			}
			Out.Last = T;
		}
		for (FLiftWalker& P : People)
		{
			P.R.Clear();
		}
		return Out;
	}

	void LiftTestRiders(const FAstraLiftNetwork& Net, int32 Num, int32 Seed)
	{
		FLiftWorldBench& W = LiftBench();
		if (!W.Create())
		{
			LiftCheck(TEXT("riders: the lifts' subsystem"), false, TEXT("the world has no UAstraLiftSubsystem"));
			return;
		}
		const int32 Tl = Net.FindLine(TEXT("tl_a"));
		if (Tl == INDEX_NONE)
		{
			LiftCheck(TEXT("riders: the test plan's turbolift"), false, TEXT("no line tl_a in the plan"));
			return;
		}
		// ---- the rush: the crew come to the landings at their own times and ride, with the car taking them where they go
		W.Build(Net);
		const FLiftWalkResult A = LiftRunWalkers(W, Tl, Num, Seed, 90.0, nullptr, 480.f);
		const AAstraLiftCar* Car = W.Lifts->CarOf(Tl);
		bool bFree = true;
		for (int32 I = 0; I < Car->NumSlots(); ++I)
		{
			bFree &= W.Lifts->SlotFree(Tl, I);
		}
		const double Worst = A.Totals.Num() ? FMath::Max(A.Totals) : 0.0;
		LiftCheck(TEXT("riders: the crew ride the real car"), A.Done == Num && A.Failed == 0 && A.InsideViol == 0 && Worst < 240.0 && bFree,
		      FString::Printf(TEXT("%d of %d delivered in %.0f s; wait avg %.1f, p95 %.1f s; ride avg %.1f s; worst door to door %.0f s; %d failed; the car's places all free again %d %s"),
		                      A.Done, Num, A.Last, LiftMean(A.Waits), LiftPercentile(A.Waits, 0.95), LiftMean(A.Rides), Worst, A.Failed, bFree, *A.First));
		LiftCheck(TEXT("riders: the doors never close on a walker"), A.DoorViol == 0 && A.MovedInDoorway == 0,
		      FString::Printf(TEXT("%d frames with a walker in a doorway and the doors shut, %d with the car moving %s"), A.DoorViol, A.MovedInDoorway, *A.First));
		LiftCheck(TEXT("riders: nobody stands through anybody in the car"), A.SharedSlots == 0 && A.MinApart > 30.f,
		      FString::Printf(TEXT("the closest two riders came to %.0f cm, %d frames on the same spot"), A.MinApart > 1.0e8f ? 0.f : A.MinApart, A.SharedSlots));

		// ---- with the Captain in the car, at the place a body would take first: nobody takes it
		W.Build(Net);
		const FAstraLiftLine& L = Net.Lines[Tl];
		AAstraLiftCar* C2 = W.Lifts->CarOf(Tl);
		const int32 Deck1 = L.FindStopByDeck(1);
		const FAstraLiftStop& S1 = L.Stops[Deck1];
		ACharacter* Cap = LiftSpawnCaptain(W, S1.DoorCm + S1.Out * 220.f, FRotator(0.f, L.FrontYaw + 180.f, 0.f));
		W.Run(0.8f);
		FString Notice;
		W.Lifts->CallAt(Tl, Deck1, Notice);
		LiftWalk(W, Cap, -S1.Out, 12.f, [&]() { return C2->Contains(Cap->GetActorLocation(), 40.f) && C2->Brain.DoorOpen() >= 1.f; });
		// he walks to the back of the car (where the first place is) and stands there
		const FVector Back = C2->ToWorld(C2->SlotLocal(0));
		LiftWalk(W, Cap, (Back - Cap->GetActorLocation()).GetSafeNormal2D(), 6.f, [&]() { return FVector::Dist2D(Back, Cap->GetActorLocation()) < 25.f; });
		W.Run(0.5f);
		const FString Before = W.Lifts->Describe().Left(160).Replace(TEXT("\n"), TEXT(" | "));
		const FLiftWalkResult B = LiftRunWalkers(W, Tl, 6, Seed + 1, 20.0, Cap, 300.f);
		if (B.Done != 6)
		{
			int32 Free = 0;
			for (int32 I = 0; I < C2->NumSlots(); ++I)
			{
				Free += W.Lifts->SlotFree(Tl, I) ? 1 : 0;
			}
			UE_LOG(LogASTRA, Display, TEXT("[Lift]   the Captain's car before: %s; after: %s; he stands at %s in it (inside %d, in line %d); %d of %d places free, full %d"), *Before,
			       *W.Lifts->Describe().Left(160).Replace(TEXT("\n"), TEXT(" | ")), *C2->ToLocal(Cap->GetActorLocation()).ToString(), C2->Contains(Cap->GetActorLocation()), W.Lifts->PlayerLine(),
			       Free, C2->NumSlots(), !W.Lifts->HasFreeSlot(Tl));
		}
		LiftCheck(TEXT("riders: nobody takes the Captain's place"), B.Done == 6 && B.Failed == 0 && B.MinFromCaptain > 45.f && B.CaptainFalls == 0 && B.CaptainUnbased == 0,
		      FString::Printf(TEXT("%d of 6 delivered; the nearest came within %.0f cm of him (45 needed); he fell %d frames, left the car's floor %d; %d frames on %.0f s %s"),
		                      B.Done, B.MinFromCaptain > 1.0e8f ? 0.f : B.MinFromCaptain, B.CaptainFalls, B.CaptainUnbased, B.Frames, B.Last, *B.First));

		// ---- the Spine shuttle: the same people on the line along the Spine (its car runs level, with doors along its side)
		const int32 Sh = Net.FindLine(TEXT("spine_shuttle"));
		if (Sh != INDEX_NONE)
		{
			W.Build(Net);
			const FLiftWalkResult S = LiftRunWalkers(W, Sh, 8, Seed + 2, 60.0, nullptr, 900.f);
			LiftCheck(TEXT("riders: the crew ride the Spine shuttle"), S.Done == 8 && S.Failed == 0 && S.InsideViol == 0 && S.DoorViol == 0 && S.MovedInDoorway == 0,
			      FString::Printf(TEXT("%d of 8 delivered in %.0f s; wait avg %.1f, worst %.1f s; ride avg %.1f s; %d failed; doors shut on a walker %d, car moving with one in a doorway %d, 'inside' outside %d %s"),
			                      S.Done, S.Last, LiftMean(S.Waits), S.Waits.Num() ? FMath::Max(S.Waits) : 0.0, LiftMean(S.Rides), S.Failed, S.DoorViol, S.MovedInDoorway, S.InsideViol, *S.First));
		}
		W.Destroy();
	}

	// ============================================================================================================================ the Captain's keys

	/** What the controller does with E, W, S and Esc, as the subsystem sees it: E at a landing's panel calls the car; E inside opens the list on the car's screen, W and S move the
	 *  mark, E chooses it; Esc closes the list. (The key bindings are the controller's; what they call is checked here, in a world that ticks.) */
	void LiftTestUse(const FAstraLiftNetwork& Net)
	{
		FLiftWorldBench& W = LiftBench();
		if (!W.Create())
		{
			LiftCheck(TEXT("use: the lifts' subsystem"), false, TEXT("the world has no UAstraLiftSubsystem"));
			return;
		}
		const int32 Tl = Net.FindLine(TEXT("tl_a"));
		if (Tl == INDEX_NONE)
		{
			LiftCheck(TEXT("use: the test plan's turbolift"), false, TEXT("no line tl_a in the plan"));
			return;
		}
		W.Build(Net);
		const FAstraLiftLine& L = Net.Lines[Tl];
		AAstraLiftCar* Car = W.Lifts->CarOf(Tl);
		const int32 Deck5 = L.FindStopByDeck(5), Deck8 = L.FindStopByDeck(8);
		const FAstraLiftStop& S5 = L.Stops[Deck5];
		// ---- E at the panel of Deck 5's landing (the car is at Deck 1): it calls the car
		const FVector Panel = W.Lifts->LandingOf(Tl, Deck5)->PanelCm();
		const FVector Feet = FVector(Panel.X, Panel.Y, S5.FloorZ) + S5.Out * 70.f;
		ACharacter* C = LiftSpawnCaptain(W, Feet, FRotator(0.f, L.FrontYaw + 180.f, 0.f));
		W.Run(0.8f);
		const bool bNear = W.Lifts->IsNearPanel(Feet);
		FString Notice;
		const bool bCalled = W.Lifts->Use(C, Notice);
		const bool bCame = LiftWalk(W, C, FVector::ZeroVector, 50.f, [&]() { return Car->Brain.AtLanding() == Deck5 && Car->Brain.DoorOpen() >= 1.f; });
		LiftCheck(TEXT("use: E at a landing's panel calls the car"), bNear && bCalled && bCame, FString::Printf(TEXT("near the panel %d, E took the call (%s) %d, the car came with its doors open %d"), bNear, *Notice, bCalled, bCame));
		// ---- inside: E opens the list (the mark on the deck the car is at), S moves it down three decks, E goes there, the list closes
		// (the panel is beside the opening: along the wall to the middle of the doors first, then in)
		const FVector InFront = FVector(S5.DoorCm.X, S5.DoorCm.Y, 0.f) + S5.Out * 90.f;
		LiftWalk(W, C, (FVector(InFront.X, InFront.Y, 0.f) - FVector(C->GetActorLocation().X, C->GetActorLocation().Y, 0.f)).GetSafeNormal(), 6.f,
		         [&]() { return FVector::Dist2D(C->GetActorLocation(), InFront) < 25.f; });
		const bool bIn = LiftWalk(W, C, -S5.Out, 6.f, [&]() { return Car->Contains(C->GetActorLocation(), 40.f); });
		W.Run(0.6f);
		const int32 Rows = L.Stops.Num();
		const int32 RowOf5 = Rows - 1 - Deck5, RowOf8 = Rows - 1 - Deck8;                       // a shaft's list runs from its highest deck down
		const bool bOpened = W.Lifts->Use(C, Notice) && W.Lifts->IsMenuOpen() && W.Lifts->PlayerLine() == Tl;
		const int32 Sel0 = W.Lifts->MenuSelected();
		W.Lifts->MenuMove(RowOf8 - RowOf5);
		const int32 Sel1 = W.Lifts->MenuSelected();
		TArray<UAstraLiftSubsystem::FRow> List;
		W.Lifts->MenuRows(Tl, List);
		const bool bRows = List.Num() == Rows && List.IsValidIndex(Sel1) && List[Sel1].Stop == Deck8 && List[Sel0].bHere && List[0].Label == TEXT("1") && !List[Sel1].Places.IsEmpty();
		const bool bWent = W.Lifts->Use(C, Notice) && !W.Lifts->IsMenuOpen();
		const bool bArrived = LiftWalk(W, C, FVector::ZeroVector, 40.f, [&]() { return Car->Brain.AtLanding() == Deck8 && Car->Brain.DoorOpen() >= 1.f; });
		LiftCheck(TEXT("use: E inside opens the list, S moves the mark, E goes"), bIn && bOpened && Sel0 == RowOf5 && Sel1 == RowOf8 && bRows && bWent && bArrived,
		      FString::Printf(TEXT("in %d, opened %d, the mark on row %d (the car's deck %d) then %d (Deck 8 %d), the rows read right %d (%d of them), E went and the list closed %d, there %d"), bIn, bOpened,
		                      Sel0, RowOf5, Sel1, RowOf8, bRows, List.Num(), bWent, bArrived));
		// ---- Esc closes the list without going anywhere, and the mark wraps round the ends
		W.Lifts->Use(C, Notice);
		W.Lifts->MenuMove(-100);
		const int32 Wrapped = W.Lifts->MenuSelected();
		W.Lifts->MenuClose();
		W.Run(0.4f);
		LiftCheck(TEXT("use: Esc closes the list and nothing moves"), !W.Lifts->IsMenuOpen() && Wrapped >= 0 && Wrapped < Rows && Car->Brain.AtLanding() == Deck8,
		      FString::Printf(TEXT("closed %d, the mark stayed on a row (%d) %d, the car stayed at Deck 8 %d"), !W.Lifts->IsMenuOpen(), Wrapped, Wrapped >= 0 && Wrapped < Rows, Car->Brain.AtLanding() == Deck8));
		W.Destroy();
	}

	void LiftTestVoice(const FAstraLiftNetwork& Net)
	{
		FLiftWorldBench& W = LiftBench();
		if (!W.Create())
		{
			return;
		}
		W.Build(Net);
		const int32 Tl = Net.FindLine(TEXT("tl_a"));
		const FAstraLiftLine& L = Net.Lines[Tl];
		AAstraLiftCar* Car = W.Lifts->CarOf(Tl);
		const FAstraLiftStop& S1 = L.Stops[L.FindStopByDeck(1)];
		TSharedRef<FJsonObject> Args = MakeShared<FJsonObject>();
		Args->SetStringField(TEXT("destination"), TEXT("d7"));
		FString Detail;
		// outside a car the lifts take no orders
		const bool bOutside = !W.Lifts->GoByVoice(Args, Detail);
		const FString Refusal = Detail;
		ACharacter* C = LiftSpawnCaptain(W, S1.DoorCm - S1.Out * 100.f + FVector(0.f, 0.f, 0.f), FRotator(0.f, L.FrontYaw + 180.f, 0.f));
		FString Notice;
		W.Run(0.5f);
		W.Lifts->CallAt(Tl, L.FindStopByDeck(1), Notice);
		W.Run(2.5f);
		LiftWalk(W, C, -S1.Out, 4.f, [&]() { return Car->Contains(C->GetActorLocation(), 40.f); });
		W.Run(1.f);
		const TSharedPtr<FJsonObject> Ctx = W.Lifts->ContextJson();
		const TArray<TSharedPtr<FJsonValue>>* Stops = nullptr;
		bool bPlaces = false;
		int32 NStops = 0;
		if (Ctx.IsValid() && Ctx->TryGetArrayField(TEXT("stops"), Stops))
		{
			NStops = Stops->Num();
			for (const TSharedPtr<FJsonValue>& V : *Stops)
			{
				const TSharedPtr<FJsonObject> O = V->AsObject();
				const TArray<TSharedPtr<FJsonValue>>* Places = nullptr;
				if (O->GetStringField(TEXT("id")) == TEXT("d7") && O->TryGetArrayField(TEXT("places"), Places))
				{
					for (const TSharedPtr<FJsonValue>& P : *Places)
					{
						bPlaces |= P->AsString() == TEXT("Main Engineering");
					}
				}
			}
		}
		if (Ctx.IsValid())
		{
			// the context as the mind reads it (the row mind/bench/lift_unit.py holds as its sample)
			FString Text;
			const TSharedRef<TJsonWriter<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>> Writer = TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&Text);
			FJsonSerializer::Serialize(Ctx.ToSharedRef(), Writer);
			UE_LOG(LogASTRA, Display, TEXT("[Lift]   context.lift: %s"), *Text);
		}
		LiftCheck(TEXT("voice: the context says where the car goes"), bOutside && Ctx.IsValid() && NStops == L.Stops.Num() && bPlaces && Ctx->GetStringField(TEXT("car")) == TEXT("tl_a"),
		      FString::Printf(TEXT("outside a car: refused (%s); inside: %d stops, deck 7 lists Main Engineering %d"), *Refusal.Left(60), NStops, bPlaces));
		const bool bGo = W.Lifts->GoByVoice(Args, Detail);
		const FString Said = Detail;
		const double T0 = W.World->GetTimeSeconds();
		bool bThere = false;
		const int32 D7 = L.FindStopByDeck(7);
		for (float T = 0.f; T < 40.f; T += 1.f / 60.f)
		{
			W.Step(1.f / 60.f);
			if (Car->Brain.AtLanding() == D7 && Car->Brain.DoorOpen() >= 1.f)
			{
				bThere = true;
				break;
			}
		}
		// the wrong words get an answer a model can use; a deck the lift does not serve too
		TSharedRef<FJsonObject> Bad = MakeShared<FJsonObject>();
		Bad->SetStringField(TEXT("destination"), TEXT("d12"));
		FString BadDetail;
		const bool bBad = !W.Lifts->GoByVoice(Bad, BadDetail);
		TSharedRef<FJsonObject> ByDeck = MakeShared<FJsonObject>();
		ByDeck->SetNumberField(TEXT("deck"), 3);
		FString DeckDetail;
		const bool bDeck = W.Lifts->GoByVoice(ByDeck, DeckDetail);
		LiftCheck(TEXT("voice: lift_go takes the car to a stop"), bGo && bThere && bBad && bDeck && BadDetail.Contains(TEXT("d9")),
		      FString::Printf(TEXT("%s; there in %.1f s; the wrong stop: %s"), *Said, W.World->GetTimeSeconds() - T0, *BadDetail.Left(80)));
		W.Destroy();
	}

	void LiftTestStreaming(const FAstraLiftNetwork& Net)
	{
		FLiftWorldBench& W = LiftBench();
		if (!W.Create())
		{
			return;
		}
		W.Build(Net);
		const int32 Tl = Net.FindLine(TEXT("tl_a"));
		const FAstraLiftLine& L = Net.Lines[Tl];
		AAstraLiftCar* Car = W.Lifts->CarOf(Tl);
		const int32 D1 = L.FindStopByDeck(1), D7 = L.FindStopByDeck(7);
		const FAstraLiftStop& S1 = L.Stops[D1];
		ACharacter* C = LiftSpawnCaptain(W, S1.DoorCm + S1.Out * 220.f, FRotator(0.f, L.FrontYaw + 180.f, 0.f));
		W.Run(0.6f);
		FString Notice;
		W.Lifts->CallAt(Tl, D1, Notice);
		W.Run(2.5f);
		LiftWalk(W, C, -S1.Out, 4.f, [&]() { return Car->Contains(C->GetActorLocation(), 40.f); });
		W.Run(1.f);
		double ReadyAt = 1.0e9;
		int32 Wanted = 0, Forced = 0;
		W.Lifts->Test.DeckReadyAt = [&](const FVector& Cm) { return !(FMath::Abs(Cm.Z - L.Stops[D7].FloorZ) < 100.f) || W.World->GetTimeSeconds() >= ReadyAt; };
		W.Lifts->Test.WantReadyAt = [&](const FVector& Cm) { Wanted += FMath::Abs(Cm.Z - L.Stops[D7].FloorZ) < 100.f ? 1 : 0; };
		W.Lifts->Test.ForceReadyAt = [&](const FVector& Cm) { Forced += FMath::Abs(Cm.Z - L.Stops[D7].FloorZ) < 100.f ? 1 : 0; ReadyAt = 0.0; };
		// the deck comes in ten seconds late
		FString D;
		W.Lifts->GoToDeck(7, D);
		const double T0 = W.World->GetTimeSeconds();
		ReadyAt = T0 + 5.0 + FAstraLiftProfile::Make(L.Stops[D7].S - S1.S < 0 ? S1.S - L.Stops[D7].S : L.Stops[D7].S - S1.S, L.SpeedCmS, L.AccelCmS2).T;
		bool bHeldShut = false;
		double OpenedAt = 0.0;
		for (float T = 0.f; T < 40.f; T += 1.f / 60.f)
		{
			W.Step(1.f / 60.f);
			if (Car->Brain.State() == FAstraLiftBrain::EState::Hold)
			{
				bHeldShut |= Car->Brain.DoorOpen() <= 0.f;
			}
			if (Car->Brain.AtLanding() == D7 && Car->Brain.DoorOpen() > 0.f)
			{
				OpenedAt = W.World->GetTimeSeconds();
				break;
			}
		}
		LiftCheck(TEXT("stream: the car waits for the deck, doors shut"), Wanted >= 1 && bHeldShut && Forced == 0 && OpenedAt >= ReadyAt - 0.1 && OpenedAt - ReadyAt < 0.5,
		      FString::Printf(TEXT("the deck was asked for %d time(s) at departure; held with the doors shut %d; the deck ready at %.1f s, the doors opened at %.1f s; forced %d"), Wanted, bHeldShut, ReadyAt - T0, OpenedAt - T0, Forced));
		// and one that never comes is made ready, once, after the wait
		W.Run(Car->Brain.Config().DwellS + 4.f);
		ReadyAt = 1.0e9;
		const int32 D3 = L.FindStopByDeck(3);
		W.Lifts->Test.DeckReadyAt = [&](const FVector& Cm) { return !(FMath::Abs(Cm.Z - L.Stops[D3].FloorZ) < 100.f) || W.World->GetTimeSeconds() >= ReadyAt; };
		W.Lifts->Test.ForceReadyAt = [&](const FVector& Cm) { Forced += FMath::Abs(Cm.Z - L.Stops[D3].FloorZ) < 100.f ? 1 : 0; ReadyAt = 0.0; };
		Forced = 0;
		W.Lifts->GoToDeck(3, D);
		double Stopped = 0.0, Opened2 = 0.0;
		for (float T = 0.f; T < 60.f; T += 1.f / 60.f)
		{
			W.Step(1.f / 60.f);
			if (Stopped == 0.0 && Car->Brain.AtLanding() == D3)
			{
				Stopped = W.World->GetTimeSeconds();
			}
			if (Car->Brain.AtLanding() == D3 && Car->Brain.DoorOpen() > 0.f)
			{
				Opened2 = W.World->GetTimeSeconds();
				break;
			}
		}
		LiftCheck(TEXT("stream: a deck that never comes is forced, last"), Forced == 1 && Opened2 > Stopped && FMath::Abs((Opened2 - Stopped) - Car->Brain.Config().HeldForceS) < 0.3,
		      FString::Printf(TEXT("forced %d time(s), the doors opened %.1f s after the car stopped"), Forced, Opened2 - Stopped));
		W.Destroy();
	}

	void LiftTestShuttle(const FAstraLiftNetwork& Net)
	{
		const int32 Sh = Net.FindLine(TEXT("spine_shuttle"));
		if (Sh == INDEX_NONE)
		{
			LiftCheck(TEXT("shuttle: the line is in the plan"), false, TEXT("no spine_shuttle in the plan"));
			return;
		}
		FLiftWorldBench& W = LiftBench();
		if (!W.Create())
		{
			return;
		}
		W.Build(Net);
		const FAstraLiftLine& L = Net.Lines[Sh];
		AAstraLiftCar* Car = W.Lifts->CarOf(Sh);
		// the stops A (forward) and C: the car comes to A, the Captain gets in by the middle door and rides to C
		const int32 A = L.FindStopById(TEXT("sec_a")), Cc = L.FindStopById(TEXT("sec_c"));
		const FAstraLiftStop& SA = L.Stops[A];
		ACharacter* C = LiftSpawnCaptain(W, FVector(SA.DoorCm.X, SA.DoorCm.Y, SA.FloorZ) + SA.Out * 200.f, FRotator(0.f, L.FrontYaw + 180.f, 0.f));
		W.Run(0.8f);
		FString Notice;
		W.Lifts->CallAt(Sh, A, Notice);
		const bool bCome = LiftWalk(W, C, FVector::ZeroVector, 80.f, [&]() { return Car->Brain.AtLanding() == A && Car->Brain.DoorOpen() >= 1.f; });
		const bool bIn = LiftWalk(W, C, -SA.Out, 6.f, [&]() { return Car->Contains(C->GetActorLocation(), 40.f); });
		W.Run(0.6f);
		FLiftRideLog Log;
		Log.Rel0 = Car->ToLocal(C->GetActorLocation());
		W.Lifts->Tick(0.3f);
		// the shuttle's own list: the Captain chooses from inside (the console twin of the voice)
		TSharedRef<FJsonObject> Args = MakeShared<FJsonObject>();
		Args->SetStringField(TEXT("destination"), TEXT("sec_c"));
		FString Detail;
		W.Run(0.4f);
		const bool bGo = W.Lifts->GoByVoice(Args, Detail);
		bool bArr = false;
		const double T0 = W.World->GetTimeSeconds();
		for (float T = 0.f; T < 120.f; T += 1.f / 60.f)
		{
			W.Step(1.f / 60.f);
			LiftRecordRide(W, Sh, C, Log);
			if (Car->Brain.AtLanding() == Cc && Car->Brain.DoorOpen() >= 1.f)
			{
				bArr = true;
				break;
			}
		}
		const float EndDev = (float)(Car->ToLocal(C->GetActorLocation()) - Log.Rel0).Size();
		LiftCheck(TEXT("shuttle: Section A to Section C, 208 m, aboard"), bCome && bIn && bGo && bArr && EndDev < 2.f && Log.FallFrames == 0 && Log.UnbasedFrames == 0 && Log.DoorBreaks == 0,
		      FString::Printf(TEXT("%s; %.1f s; peak %.1f m/s; %.2f cm from his place at the end, drift %.2f cm, %d falling, %d off the floor, %d door breaks %s"), *Detail, W.World->GetTimeSeconds() - T0,
		                      Log.MaxSpeed / 100.f, EndDev, Log.MaxDevCm, Log.FallFrames, Log.UnbasedFrames, Log.DoorBreaks, *Log.First));
		W.Destroy();
	}

	/** Twelve cars standing at their landings: what the lifts cost a frame (the subsystem's own tick, 5 Hz slow part included), then the same with all twelve on the move. */
	void LiftTestPerf(const FAstraLiftNetwork& Net)
	{
		FAstraLiftNetwork Big;
		Big.Source = Net.Source;
		const int32 Tl = Net.FindLine(TEXT("tl_a"));
		for (int32 I = 0; I < 12; ++I)
		{
			FAstraLiftLine L = Net.Lines[Tl];
			L.Id = FString::Printf(TEXT("tl_%d"), I);
			L.Name = FString::Printf(TEXT("Turbolift %d"), I + 1);
			const FVector Shift(-I * 400.f, 0.f, 0.f);
			L.ShaftCm += Shift;
			TArray<FVector> P = L.Path.Pts;
			for (FVector& V : P) { V += Shift; }
			L.Path.Build(P);
			for (FAstraLiftStop& S : L.Stops) { S.DoorCm += Shift; S.NodeCm += Shift; }
			Big.Lines.Add(L);
		}
		FLiftWorldBench& W = LiftBench();
		if (!W.Create())
		{
			return;
		}
		W.Build(Big);
		W.Run(1.0f);
		const int32 Frames = 3000;
		double SumUs = 0.0, MaxUs = 0.0;
		W.WorldMsSum = 0.0;
		W.WorldMsMax = 0.0;
		W.Frames = 0;
		for (int32 I = 0; I < Frames; ++I)
		{
			W.Step(1.f / 60.f);
			SumUs += W.Lifts->TickMicros();
			MaxUs = FMath::Max(MaxUs, W.Lifts->TickMicros());
		}
		const double BaseWorldMs = W.WorldMsSum / FMath::Max<int64>(1, W.Frames);
		LiftCheck(TEXT("perf: 12 cars standing"), SumUs / Frames <= 50.0, FString::Printf(TEXT("%.2f us a frame on average, %.1f us the worst frame of %d (the limit is 50 us); the whole world tick %.3f ms"), SumUs / Frames, MaxUs, Frames, BaseWorldMs));
		// all twelve called at once: the cost of cars in motion
		for (int32 I = 0; I < 12; ++I)
		{
			FString N;
			W.Lifts->CallAt(I, I % 2 ? 0 : Big.Lines[I].Stops.Num() - 1, N);
			W.Lifts->CarOf(I)->Brain.CarCall(I % 3 ? 0 : Big.Lines[I].Stops.Num() - 1);
			W.Lifts->CarOf(I)->Wake();
		}
		W.WorldMsSum = 0.0;
		W.WorldMsMax = 0.0;
		W.Frames = 0;
		SumUs = 0.0;
		int32 MovingFrames = 0;
		for (int32 I = 0; I < 1800; ++I)
		{
			W.Step(1.f / 60.f);
			SumUs += W.Lifts->TickMicros();
			bool bAny = false;
			for (int32 K = 0; K < 12; ++K)
			{
				bAny |= W.Lifts->CarOf(K)->Brain.State() == FAstraLiftBrain::EState::Moving;
			}
			MovingFrames += bAny ? 1 : 0;
		}
		const double MovingWorldMs = W.WorldMsSum / FMath::Max<int64>(1, W.Frames);
		LiftCheck(TEXT("perf: 12 cars on the move (reported)"), true, FString::Printf(TEXT("the whole world tick %.3f ms with cars moving in %d of 1800 frames (%.3f ms before): the cars cost about %.3f ms a frame while they move; the subsystem alone %.1f us"),
		                                                MovingWorldMs, MovingFrames, BaseWorldMs, FMath::Max(0.0, MovingWorldMs - BaseWorldMs), SumUs / 1800.0));
		W.Destroy();
	}

	void LiftTestPlan(const FAstraLiftNetwork& Net)
	{
		int32 Stops = 0, Shafts = 0, Shuttles = 0, Bad = 0;
		for (const FAstraLiftLine& L : Net.Lines)
		{
			Stops += L.Stops.Num();
			Shafts += L.bShuttle ? 0 : 1;
			Shuttles += L.bShuttle ? 1 : 0;
			Bad += L.Path.IsValid() ? 0 : 1;
			for (const FAstraLiftStop& S : L.Stops)
			{
				Bad += S.Out.IsNearlyZero() || !FMath::IsNearlyEqual((float)S.Out.Size(), 1.f, 0.01f) ? 1 : 0;
				Bad += S.bNode ? 0 : 1;
			}
		}
		LiftCheck(TEXT("plan: the lifts of the test plan"), Net.Problems.Num() == 0 && Shafts == 3 && Shuttles == 1 && Stops == 9 + 9 + 9 + 7 && Bad == 0,
		      FString::Printf(TEXT("%d shafts, %d shuttle line, %d stops; %d problems %s"), Shafts, Shuttles, Stops, Net.Problems.Num(), Net.Problems.Num() ? *Net.Problems[0] : TEXT("")));
		// a person's route is on a lift when its two ends are the waiting places of two stops of a line (what the life simulation's bodies ask: FindRide)
		{
			const int32 Tl = Net.FindLine(TEXT("tl_a")), Tl2 = Net.FindLine(TEXT("tl_a2")), Sh = Net.FindLine(TEXT("spine_shuttle"));
			int32 Line = INDEX_NONE, From = INDEX_NONE, To = INDEX_NONE;
			bool bShaft = false, bPair = false, bShuttle = false, bNot = true;
			if (Tl != INDEX_NONE && Net.Lines[Tl].Stops.Num() > 5)
			{
				bShaft = Net.FindRide(Net.Lines[Tl].Stops[1].WaitCm(), Net.Lines[Tl].Stops[5].WaitCm(), Line, From, To) && Line == Tl && From == 1 && To == 5;
			}
			if (Tl2 != INDEX_NONE && Net.Lines[Tl2].Stops.Num() > 3)
			{
				bPair = Net.FindRide(Net.Lines[Tl2].Stops[3].WaitCm() + FVector(30.f, 20.f, 0.f), Net.Lines[Tl2].Stops[0].WaitCm(), Line, From, To) && Line == Tl2 && From == 3 && To == 0;
			}
			if (Sh != INDEX_NONE && Net.Lines[Sh].Stops.Num() > 3)
			{
				bShuttle = Net.FindRide(Net.Lines[Sh].Stops[0].WaitCm(), Net.Lines[Sh].Stops[3].WaitCm(), Line, From, To) && Line == Sh && From == 0 && To == 3;
			}
			if (Tl != INDEX_NONE)
			{
				// a corridor walk that only passes by a landing, and a hop of a few centimetres on the same deck: neither is a ride
				bNot = !Net.FindRide(Net.Lines[Tl].Stops[1].WaitCm() + FVector(400.f, 0.f, 0.f), Net.Lines[Tl].Stops[5].WaitCm(), Line, From, To)
				    && !Net.FindRide(Net.Lines[Tl].Stops[1].WaitCm(), Net.Lines[Tl].Stops[1].WaitCm() + FVector(0.f, 0.f, 3.f), Line, From, To);
			}
			LiftCheck(TEXT("plan: a route on a lift is found"), bShaft && bPair && bShuttle && bNot,
			      FString::Printf(TEXT("a shaft's ride %d, the pair's (a step off the node) %d, the shuttle's %d, a walk that only passes by is not one %d"), bShaft, bPair, bShuttle, bNot));
		}
		// a plan that breaks the contract is told so: a door off its shaft's wall, a car that does not fit, a stop twice
		const FString Bad1 = TEXT("{\"version\":2,\"vertical\":[{\"id\":\"bad\",\"kind\":\"turbolift\",\"shaft\":{\"x\":0,\"y\":0,\"w\":2.8,\"d\":2.8,\"z\":[-10,0]},\"car\":{\"w\":3.0,\"d\":2.4,\"h\":2.6},"
		                         "\"landings\":[{\"deck\":1,\"z\":0,\"door\":[0,3.5,0],\"yaw\":90},{\"deck\":2,\"z\":-4,\"door\":[0,1.4,-4],\"yaw\":90},{\"deck\":2,\"z\":-8,\"door\":[0,1.4,-8],\"yaw\":90}]}]}");
		const FString Path = FPaths::ProjectSavedDir() / TEXT("Lift/bad_plan.json");
		FFileHelper::SaveStringToFile(Bad1, *Path);
		FAstraLiftNetwork N2;
		N2.Load(Path);
		bool bCar = false, bDoor = false, bTwice = false;
		for (const FString& P : N2.Problems)
		{
			bCar |= P.Contains(TEXT("does not fit"));
			bDoor |= P.Contains(TEXT("from the shaft's middle"));
			bTwice |= P.Contains(TEXT("listed twice"));
		}
		LiftCheck(TEXT("plan: a plan that breaks the contract is told so"), bCar && bDoor && bTwice, FString::Printf(TEXT("car too big %d, door off the wall %d, deck twice %d (%d problems)"), bCar, bDoor, bTwice, N2.Problems.Num()));
	}
}

int32 UAstraLiftSimCommandlet::Main(const FString& Params)
{
	FString Scenario = TEXT("all"), PlanFile;
	int32 Seed = 7, Riders = 20;
	FParse::Value(*Params, TEXT("scenario="), Scenario);
	FParse::Value(*Params, TEXT("plan="), PlanFile);
	FParse::Value(*Params, TEXT("seed="), Seed);
	FParse::Value(*Params, TEXT("riders="), Riders);
	if (PlanFile.IsEmpty())
	{
		PlanFile = FPaths::Combine(FPaths::ProjectDir(), TEXT("data/ship/test/lifts_fixture.json"));
	}
	GAstraLiftTrace = FParse::Param(*Params, TEXT("trace"));
	const bool bAll = Scenario == TEXT("all");
	LiftChecks.Reset();
	FAstraLiftNetwork Net;
	if (!Net.Load(PlanFile))
	{
		UE_LOG(LogASTRA, Error, TEXT("[Lift] cannot read %s"), *PlanFile);
		return 1;
	}
	UE_LOG(LogASTRA, Display, TEXT("[Lift] %s: %s"), *PlanFile, *FString::Join(Net.Notes, TEXT("; ")));
	const int32 Tl = Net.FindLine(TEXT("tl_a"));
	if (bAll || Scenario == TEXT("plan"))
	{
		LiftTestPlan(Net);
	}
	if (bAll || Scenario == TEXT("motion"))
	{
		LiftTestMotion();
	}
	if (Tl != INDEX_NONE && (bAll || Scenario == TEXT("brain")))
	{
		LiftTestBrain(Net.Lines[Tl]);
	}
	if (Tl != INDEX_NONE && (bAll || Scenario == TEXT("rush")))
	{
		LiftTestRush(Net.Lines[Tl], Riders, Seed);
	}
	if (bAll || Scenario == TEXT("ride") || Scenario == TEXT("doors"))
	{
		LiftTestWorld(Net, bAll, Scenario);
	}
	if (bAll || Scenario == TEXT("riders"))
	{
		LiftTestRiders(Net, Riders, Seed);
	}
	if (bAll || Scenario == TEXT("use"))
	{
		LiftTestUse(Net);
	}
	if (bAll || Scenario == TEXT("voice"))
	{
		LiftTestVoice(Net);
	}
	if (bAll || Scenario == TEXT("stream"))
	{
		LiftTestStreaming(Net);
	}
	if (bAll || Scenario == TEXT("shuttle"))
	{
		LiftTestShuttle(Net);
	}
	if (bAll || Scenario == TEXT("perf"))
	{
		LiftTestPerf(Net);
	}
	LiftBench().Shutdown();
	int32 Failed = 0;
	for (const FLiftCheck& C : LiftChecks)
	{
		Failed += C.bPass ? 0 : 1;
	}
	UE_LOG(LogASTRA, Display, TEXT("[Lift] %d checks, %d failed"), LiftChecks.Num(), Failed);
	return Failed ? 1 : 0;
}
