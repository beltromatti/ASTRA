// ASTRA — the module's own tests of the motion made readable (AstraSpaceLifeMotion.h): the data of the jets, the allocation against physics (a push at the bow to starboard turns the nose to
// starboard), the reading of scripted manoeuvres (a turn, a brake, a boost, a slide, a jump), the wake, the pulse, a long random flight, the cost. Plain C++ on plain records: no world, no
// engine objects, a second or two (tools/space.py test runs it: the commandlet's -motiontest).

#include "AstraSpaceLifeMotion.h"
#include "ASTRA.h"
#include "HAL/PlatformTime.h"

namespace AstraSpace
{
	namespace
	{
		// the seven capital classes and the four craft (a fighter, a bomber, a drone, the Mandate's strike fighter: round two): the same laws for all
		const TCHAR* const MoClasses[] = {TEXT("aquila"), TEXT("praetorian"), TEXT("vigilant"), TEXT("acheron"), TEXT("styx"), TEXT("lethe"), TEXT("freighter"), TEXT("falcon"), TEXT("hammer"), TEXT("wasp"), TEXT("harpy")};
		const TCHAR* const MoCraftMeshes[] = {TEXT("SM_CRAFT_ASTRA_Falcon"), TEXT("SM_CRAFT_ASTRA_Hammer"), TEXT("SM_CRAFT_ASTRA_Wasp"), TEXT("SM_CRAFT_MANDATE_Harpy")};

		/** The push and the torque (about the ship's middle) of a set of burning jets. */
		void MoNet(const FJetClass& C, const TArray<float>& Level, FVector& OutPush, FVector& OutTorque, float& OutSum)
		{
			OutPush = OutTorque = FVector::ZeroVector;
			OutSum = 0.f;
			for (int32 i = 0; i < C.Jets.Num() && i < Level.Num(); ++i)
			{
				const float U = Level[i];
				if (U <= 0.f)
				{
					continue;
				}
				const FJet& J = C.Jets[i];
				OutPush += J.Push * U;
				OutTorque += FVector::CrossProduct(J.P - C.Com, J.Push) * U;
				OutSum += U;
			}
		}

		int32 MoLit(const TArray<float>& Level, float Over)
		{
			int32 N = 0;
			for (float U : Level)
			{
				N += U > Over ? 1 : 0;
			}
			return N;
		}

		FVector MoAxis(int32 K)
		{
			return K == 0 ? FVector(1.0, 0.0, 0.0) : (K == 1 ? FVector(0.0, 1.0, 0.0) : FVector(0.0, 0.0, 1.0));
		}

		/** One ship flown by a script: what the game does each frame (Observe at the battle's step, Fire at the screen's). */
		struct FMoRig
		{
			const FJetClass* C = nullptr;
			FMotion M;
			FVector Pos = FVector(5000.0, 0.0, 0.0), Vel = FVector::ZeroVector;
			FQuat Att = FQuat::Identity;
			float Acc = 15.f, Rate = 0.05f;
			void Step(float Dt)
			{
				Observe(M, *C, Pos, Vel, Att, Acc, Rate, Dt);
				Fire(M, *C, Dt);
			}
		};
	}

	bool RunMotionTests(TArray<FString>& Fails, TArray<FString>& Notes)
	{
		auto Expect = [&Fails](bool bOk, const FString& What) { if (!bOk) { Fails.Add(What); } };
		const FJetData& Data = JetData();
		Expect(Data.bLoaded, TEXT("data/space/thrusters.json did not load (art/blender/space3_thrusters.py, then tools/space.py sync)"));
		if (!Data.bLoaded)
		{
			return false;
		}
		constexpr float Dt = 1.f / 60.f;

		// ---- the data: every class there, its nozzles in the hull and unit exhausts, each axis' best nozzle at 1
		for (const TCHAR* Key : MoClasses)
		{
			const FJetClass* C = Data.Find(FName(Key));
			Expect(C != nullptr, FString::Printf(TEXT("no jets for the class %s"), Key));
			if (!C)
			{
				continue;
			}
			Expect(C->Jets.Num() >= 14 && C->Jets.Num() <= 40, FString::Printf(TEXT("%s has %d jets"), Key, C->Jets.Num()));
			if (C->IsCraft())
			{
				Expect(C->Len > 5.f && C->DriveR > 0.1f && C->DriveR < 2.f, FString::Printf(TEXT("%s (a craft): length %.1f, bell %.2f"), Key, C->Len, C->DriveR));
			}
			else
			{
				Expect(C->Len > 100.f && C->DriveW > 5.f && C->DriveR > 1.f, FString::Printf(TEXT("%s: length %.0f, drive width %.0f, bell %.1f"), Key, C->Len, C->DriveW, C->DriveR));
			}
			FVector Best(0.0);
			for (const FJet& J : C->Jets)
			{
				Expect(FMath::Abs(J.D.Size() - 1.0) < 1.0e-3, FString::Printf(TEXT("%s: an exhaust that is not a unit vector (%.4f)"), Key, J.D.Size()));
				const FVector Off = J.P - C->Com;
				Expect(FMath::Abs(Off.X) < C->Box.X * 1.06 + 4.0 && FMath::Abs(Off.Y) < C->Box.Y * 1.06 + 4.0 && FMath::Abs(Off.Z) < C->Box.Z * 1.06 + 4.0,
				       FString::Printf(TEXT("%s: a nozzle outside the hull's box at (%.0f, %.0f, %.0f)"), Key, J.P.X, J.P.Y, J.P.Z));
				Expect(!J.P.ContainsNaN() && !J.Turn.ContainsNaN() && FMath::Abs(J.Turn.X) < 1.0001 && FMath::Abs(J.Turn.Y) < 1.0001 && FMath::Abs(J.Turn.Z) < 1.0001, FString::Printf(TEXT("%s: a jet's torque share is out of range"), Key));
				Best = FVector(FMath::Max(Best.X, FMath::Abs(J.Turn.X)), FMath::Max(Best.Y, FMath::Abs(J.Turn.Y)), FMath::Max(Best.Z, FMath::Abs(J.Turn.Z)));
			}
			Expect(Best.X > 0.99 && Best.Y > 0.99 && Best.Z > 0.99, FString::Printf(TEXT("%s: an axis has no best nozzle at 1 (%.2f %.2f %.2f)"), Key, Best.X, Best.Y, Best.Z));
			// every push and every turn a ship can ask of her jets has jets that give it
			static const double Dirs[11][3] = {{-1, 0, 0}, {0, 1, 0}, {0, -1, 0}, {0, 0, 1}, {0, 0, -1}, {1, 0, 0}, {-1, 0, 0}, {0, 1, 0}, {0, -1, 0}, {0, 0, 1}, {0, 0, -1}};
			static const TCHAR* const Names[11] = {TEXT("brake"), TEXT("push +y"), TEXT("push -y"), TEXT("push +z"), TEXT("push -z"), TEXT("roll +"), TEXT("roll -"), TEXT("pitch +"), TEXT("pitch -"), TEXT("yaw +"), TEXT("yaw -")};
			for (int32 d = 0; d < 11; ++d)
			{
				const FVector Dir(Dirs[d][0], Dirs[d][1], Dirs[d][2]);
				bool bHas = false;
				for (const FJet& J : C->Jets)
				{
					bHas |= d < 5 ? FVector::DotProduct(J.Push, Dir) > 0.25 : FVector::DotProduct(J.Turn, Dir) > 0.25;
				}
				Expect(bHas, FString::Printf(TEXT("%s has no jet for %s"), Key, Names[d]));
			}
		}

		// ---- a craft is found by her mesh (the war gives a fighter no class key), a capital ship too; she is small, a capital ship is not
		for (const TCHAR* Mesh : MoCraftMeshes)
		{
			const FJetClass* C = Data.FindMesh(Mesh);
			Expect(C != nullptr && C->IsCraft() && C->Mesh == Mesh, FString::Printf(TEXT("%s is not found as a craft by her mesh"), Mesh));
		}
		{
			const FJetClass* Capital = Data.FindMesh(TEXT("SM_SHIP_ASTRA_Aquila"));
			Expect(Capital != nullptr && !Capital->IsCraft() && Capital->Key == FName(TEXT("aquila")), TEXT("the Aquila is not found by her mesh, or is taken for a craft"));
			Expect(Data.FindMesh(TEXT("SM_NO_SUCH_MESH")) == nullptr && Data.FindMesh(FString()) == nullptr, TEXT("a mesh that is no class's is found"));
		}

		// ---- the allocation against physics: what fires for a demand pushes and turns the ship that way
		{
			int32 Checked = 0;
			double WorstCross = 0.0;
			for (const TCHAR* Key : MoClasses)
			{
				const FJetClass& C = *Data.Find(FName(Key));
				TArray<float> Out;
				Out.Init(0.f, C.Jets.Num());
				for (int32 K = 0; K < 3; ++K)
				{
					for (double Sg : {1.0, -1.0})
					{
						// a turn about one axis: the jets that fire turn the ship about it, the right way, and mostly about it
						FDemand D;
						D.Turn = MoAxis(K) * Sg;
						Allocate(C, D, Out.GetData());
						FVector P, T;
						float Sum;
						MoNet(C, Out, P, T, Sum);
						const double Along = T.X * MoAxis(K).X * Sg + T.Y * MoAxis(K).Y * Sg + T.Z * MoAxis(K).Z * Sg;
						Expect(Sum > 0.f && Along > 0.0, FString::Printf(TEXT("%s: a turn %s about %c is not given by the jets that fire (torque along it %.1f, %.1f jets' worth)"), Key, Sg > 0 ? TEXT("+") : TEXT("-"), TEXT("xyz")[K], Along, Sum));
						// (the part of the torque about the other two axes, against what is given about the one asked for)
						double Cross = 0.0;
						for (int32 O = 0; O < 3; ++O)
						{
							if (O != K)
							{
								Cross = FMath::Max(Cross, FMath::Abs(O == 0 ? T.X : (O == 1 ? T.Y : T.Z)));
							}
						}
						if (K > 0)
						{
							WorstCross = FMath::Max(WorstCross, Cross / FMath::Max(Along, 1.0));     // (a roll has the shortest lever and so the most to cancel: it is not held to this)
						}
						++Checked;
						// a push along one axis (not forward: that is the main drive's)
						if (!(K == 0 && Sg > 0.0))
						{
							FDemand Q;
							Q.Push = MoAxis(K) * Sg;
							Allocate(C, Q, Out.GetData());
							MoNet(C, Out, P, T, Sum);
							const double Pushed = P.X * Q.Push.X + P.Y * Q.Push.Y + P.Z * Q.Push.Z;
							Expect(Sum > 0.f && Pushed > 0.7 * P.Size(), FString::Printf(TEXT("%s: a push %s along %c is not what the jets that fire give (%.2f of %.2f)"), Key, Sg > 0 ? TEXT("+") : TEXT("-"), TEXT("xyz")[K], Pushed, P.Size()));
							++Checked;
						}
					}
				}
				// the main drive's push ahead is not asked of the jets, and an idle demand fires nothing
				FDemand Boost;
				Boost.Push = FVector(1.0, 0.0, 0.0);
				Allocate(C, Boost, Out.GetData());
				Expect(MoLit(Out, 0.f) == 0, FString::Printf(TEXT("%s: the jets fire for the main drive's push ahead"), Key));
				Allocate(C, FDemand(), Out.GetData());
				Expect(MoLit(Out, 0.f) == 0, FString::Printf(TEXT("%s: the jets fire for nothing"), Key));
			}
			Notes.Add(FString::Printf(TEXT("allocation: %d demands over %d classes give the right push or torque (the worst torque about the other axes of a yaw or a pitch: %.2f of what it gives about the one asked)"), Checked, (int32)UE_ARRAY_COUNT(MoClasses), WorstCross));
		}

		// ---- scripted turns, in all six directions: the jets that start it, the trim that holds it, the jets that stop it, then quiet
		{
			int32 Runs = 0;
			double SumOnset = 0.0, SumHold = 0.0;
			for (const TCHAR* Key : MoClasses)
			{
				const FJetClass& C = *Data.Find(FName(Key));
				for (int32 K = 0; K < 3; ++K)
				{
					for (double Sg : {1.0, -1.0})
					{
						FMoRig R;
						R.C = &C;
						R.Vel = FVector(150.0, 0.0, 0.0);
						const FVector Axis = MoAxis(K);
						const auto Ang = [&](double T) { return Sg * R.Rate * FMath::Clamp(T - 1.0, 0.0, 6.0); };
						float PeakBefore = 0.f, PeakOnset = 0.f, PeakHold = 1.f, PeakEnd = 0.f, PeakAfter = 1.f, HoldMin = 1.f;
						double TorqueOnset = 0.0, TorqueHold = 0.0, TorqueEnd = 0.0;
						for (int32 Step = 1; Step <= 15 * 60; ++Step)
						{
							const double T = Step * Dt;
							R.Att = FQuat(Axis, Ang(T));
							R.Pos += R.Vel * Dt;
							R.Step(Dt);
							FVector P, Tq;
							float Sum;
							if (Step == 55)
							{
								PeakBefore = R.M.Peak;
							}
							else if (Step == 66)               // a tenth of a second after the turn began
							{
								PeakOnset = R.M.Peak;
								MoNet(C, R.M.Burn, P, Tq, Sum);
								TorqueOnset = Tq.X * Axis.X * Sg + Tq.Y * Axis.Y * Sg + Tq.Z * Axis.Z * Sg;
							}
							else if (Step == 240)              // three seconds in
							{
								PeakHold = R.M.Peak;
								MoNet(C, R.M.Burn, P, Tq, Sum);
								TorqueHold = Tq.X * Axis.X * Sg + Tq.Y * Axis.Y * Sg + Tq.Z * Axis.Z * Sg;
							}
							else if (Step == 426)              // a tenth of a second after it ended (at 7 s)
							{
								PeakEnd = R.M.Peak;
								MoNet(C, R.M.Burn, P, Tq, Sum);
								TorqueEnd = Tq.X * Axis.X * Sg + Tq.Y * Axis.Y * Sg + Tq.Z * Axis.Z * Sg;
							}
							else if (Step == 14 * 60)
							{
								PeakAfter = R.M.Peak;
							}
						}
						const FString Tag = FString::Printf(TEXT("%s turning %s about %c"), Key, Sg > 0 ? TEXT("+") : TEXT("-"), TEXT("xyz")[K]);
						Expect(PeakBefore == 0.f, FString::Printf(TEXT("%s: jets burn before the turn begins (%.2f)"), *Tag, PeakBefore));
						Expect(PeakOnset > 0.5f, FString::Printf(TEXT("%s: no burst as it begins (%.2f)"), *Tag, PeakOnset));
						Expect(TorqueOnset > 0.0, FString::Printf(TEXT("%s: the jets that burn as it begins do not turn her that way (%.1f)"), *Tag, TorqueOnset));
						Expect(PeakHold > 0.04f && PeakHold < 0.7f, FString::Printf(TEXT("%s: the trim while it is held is %.2f"), *Tag, PeakHold));
						Expect(TorqueHold > 0.0, FString::Printf(TEXT("%s: the trim does not turn her the way she turns (%.1f)"), *Tag, TorqueHold));
						Expect(PeakEnd > 0.5f, FString::Printf(TEXT("%s: no burst as it ends (%.2f)"), *Tag, PeakEnd));
						Expect(TorqueEnd < 0.0, FString::Printf(TEXT("%s: the jets that burn as it ends do not stop her (%.1f)"), *Tag, TorqueEnd));
						Expect(PeakAfter == 0.f, FString::Printf(TEXT("%s: jets still burn seven seconds after it ended (%.3f)"), *Tag, PeakAfter));
						SumOnset += PeakOnset;
						SumHold += PeakHold;
						++Runs;
					}
				}
			}
			Notes.Add(FString::Printf(TEXT("turns: %d scripted turns (%d classes, 3 axes, both ways): burst %.2f, trim %.2f of the strongest jet, quiet after seven seconds"), Runs, (int32)UE_ARRAY_COUNT(MoClasses), SumOnset / Runs, SumHold / Runs));
		}

		// ---- a brake, a boost, a slide to each side, a lift
		{
			for (const TCHAR* Key : MoClasses)
			{
				const FJetClass& C = *Data.Find(FName(Key));
				// the brake: her velocity falls at the class's full acceleration along her heading
				{
					FMoRig R;
					R.C = &C;
					R.Vel = FVector(300.0, 0.0, 0.0);
					for (int32 Step = 1; Step <= 3 * 60; ++Step)
					{
						R.Vel.X -= R.Acc * Dt;
						R.Pos += R.Vel * Dt;
						R.Step(Dt);
					}
					FVector P, Tq;
					float Sum;
					MoNet(C, R.M.Burn, P, Tq, Sum);
					int32 Wrong = 0;
					for (int32 i = 0; i < C.Jets.Num(); ++i)
					{
						Wrong += (R.M.Burn[i] > 0.05f && C.Jets[i].Push.X > -0.1) ? 1 : 0;
					}
					Expect(R.M.Peak > 0.5f && MoLit(R.M.Burn, 0.3f) >= 2, FString::Printf(TEXT("%s: braking at full acceleration lights %d jets (peak %.2f)"), Key, MoLit(R.M.Burn, 0.3f), R.M.Peak));
					Expect(Wrong == 0, FString::Printf(TEXT("%s: %d jets that do not slow her burn while she brakes"), Key, Wrong));
					Expect(P.X < 0.0 && FMath::Abs(P.X) > 0.6 * P.Size(), FString::Printf(TEXT("%s: the brake's push is not backward (%.2f of %.2f)"), Key, P.X, P.Size()));
				}
				// the boost: her velocity rises along her heading: the main drive's work, no jet fires
				{
					FMoRig R;
					R.C = &C;
					R.Vel = FVector(100.0, 0.0, 0.0);
					for (int32 Step = 1; Step <= 3 * 60; ++Step)
					{
						R.Vel.X += R.Acc * Dt;
						R.Pos += R.Vel * Dt;
						R.Step(Dt);
					}
					Expect(R.M.Peak == 0.f, FString::Printf(TEXT("%s: jets fire for a boost (%.2f)"), Key, R.M.Peak));
				}
				// slides and lifts: across her heading
				for (int32 K = 1; K < 3; ++K)
				{
					for (double Sg : {1.0, -1.0})
					{
						FMoRig R;
						R.C = &C;
						R.Vel = FVector(200.0, 0.0, 0.0);
						for (int32 Step = 1; Step <= 3 * 60; ++Step)
						{
							R.Vel += MoAxis(K) * (Sg * 0.7 * R.Acc * Dt);
							R.Pos += R.Vel * Dt;
							R.Step(Dt);
						}
						FVector P, Tq;
						float Sum;
						MoNet(C, R.M.Burn, P, Tq, Sum);
						const double Pushed = P.X * MoAxis(K).X * Sg + P.Y * MoAxis(K).Y * Sg + P.Z * MoAxis(K).Z * Sg;
						Expect(R.M.Peak > 0.3f && Pushed > 0.6 * P.Size(), FString::Printf(TEXT("%s: a slide %s along %c: peak %.2f, push along it %.2f of %.2f"), Key, Sg > 0 ? TEXT("+") : TEXT("-"), TEXT("xyz")[K], R.M.Peak, Pushed, P.Size()));
					}
				}
			}
			Notes.Add(TEXT("brake, boost, slides and lifts: the brake fires only jets that slow her, a boost fires none, a slide fires the ones that push her across"));
		}

		// ---- a jump (a transit, the console putting the Aquila beside a place) is no manoeuvre
		{
			const FJetClass& C = *Data.Find(FName(TEXT("aquila")));
			FMoRig R;
			R.C = &C;
			R.Vel = FVector(150.0, 0.0, 0.0);
			float Before = 0.f;
			for (int32 Step = 1; Step <= 5 * 60; ++Step)
			{
				R.Att = FQuat(FVector::ZAxisVector, R.Rate * FMath::Clamp(Step * Dt - 1.0, 0.0, 6.0));
				R.Pos += R.Vel * Dt;
				R.Step(Dt);
				if (Step == 5 * 60 - 1)
				{
					Before = R.M.Peak;
				}
			}
			R.Pos += FVector(80000.0, 0.0, 0.0);
			R.Att = FQuat(FVector::XAxisVector, 1.0) * R.Att;
			R.Step(Dt);
			Expect(R.M.Kick.IsNearlyZero(1.0e-6) && R.M.Wake.Num == 0, TEXT("a jump of 80 km and of a radian left a kick or a wake behind"));
			for (int32 Step = 0; Step < 120; ++Step)
			{
				R.Pos += R.Vel * Dt;
				R.Step(Dt);
			}
			Expect(R.M.Peak < FMath::Max(Before, 0.4f), FString::Printf(TEXT("after a jump the jets burn harder than before it (%.2f against %.2f)"), R.M.Peak, Before));
		}

		// ---- time stopped: nothing changes, nothing is read (no division by zero)
		{
			const FJetClass& C = *Data.Find(FName(TEXT("styx")));
			FMoRig R;
			R.C = &C;
			R.Step(Dt);
			bool bFinite = true;
			for (int32 Step = 0; Step < 120; ++Step)
			{
				Observe(R.M, C, R.Pos, R.Vel, R.Att, R.Acc, R.Rate, 0.f);
				Fire(R.M, C, Dt);
				bFinite &= !R.M.Kick.ContainsNaN() && !R.M.Lin.ContainsNaN() && R.M.Peak == 0.f;
			}
			Expect(bFinite, TEXT("a stopped battle (no step) made a NaN or fired a jet"));
		}

		// ---- the wake: its notes at their cadence, the ring's limit, the pieces in order and in one piece
		{
			const FJetClass& C = *Data.Find(FName(TEXT("praetorian")));
			FWake W;
			FVector P(0.0, 0.0, 0.0);
			const FVector V(300.0, 0.0, 0.0);
			double Now = 0.0;
			int32 Added = 0;
			for (int32 Step = 0; Step < 60 * 60; ++Step)
			{
				Now += Dt;
				P += V * Dt;
				Added += W.Offer(P, Now, 0.8f, 50.0) ? 1 : 0;
			}
			Expect(W.Num == Motion::WakeCap, FString::Printf(TEXT("a wake of a minute holds %d notes, not %d"), W.Num, Motion::WakeCap));
			Expect(FMath::Abs((double)Added - 60.0 / Motion::WakeStepS) < 2.0, FString::Printf(TEXT("a minute of flight noted %d points, %.0f expected"), Added, 60.0 / Motion::WakeStepS));
			const double Life = WakeLifeFor(C.Len);
			FWakeSeg Seg[Motion::WakeCap];
			const int32 N = WakeSegments(W, P, Now, (float)Life, 1, Seg, Motion::WakeCap);
			bool bOk = N >= 10;
			for (int32 i = 0; i < N; ++i)
			{
				bOk &= Seg[i].AgeA >= 0.f && Seg[i].AgeB < 1.f && Seg[i].AgeB >= Seg[i].AgeA && (i == 0 || (Seg[i].A - Seg[i - 1].B).IsNearlyZero(1.0e-6) && Seg[i].AgeA == Seg[i - 1].AgeB);
			}
			Expect(bOk && (N == 0 || Seg[0].A.Equals(P) && Seg[0].AgeA == 0.f), TEXT("the wake's pieces are not in order of age, or not in one piece, or do not start at the ship"));
			Expect(FMath::Abs((double)N - Life / Motion::WakeStepS) < 3.0, FString::Printf(TEXT("a wake that lasts %.0f s has %d pieces, %.0f expected"), Life, N, Life / Motion::WakeStepS));
			FWakeSeg Thin[Motion::WakeCap];
			const int32 N2 = WakeSegments(W, P, Now, (float)Life, 2, Thin, Motion::WakeCap);
			Expect(N2 >= N / 2 && N2 <= N / 2 + 1 && (N2 == 0 || Thin[N2 - 1].B.Equals(Seg[FMath::Min(N - 1, 2 * N2 - 1)].B, 1.0)), FString::Printf(TEXT("a stride of two gives %d pieces of %d"), N2, N));
			// at rest it adds one note and no more; slowly it notes by distance, not by time
			FWake Still;
			int32 AddedStill = 0;
			for (int32 Step = 0; Step < 600; ++Step)
			{
				AddedStill += Still.Offer(FVector(10.0, 0.0, 0.0), Step * Dt, 0.5f, 50.0) ? 1 : 0;
			}
			Expect(AddedStill == 1, FString::Printf(TEXT("a ship at rest left %d notes"), AddedStill));
			FWake Slow;
			int32 AddedSlow = 0;
			FVector Q(0.0);
			for (int32 Step = 0; Step < 600; ++Step)
			{
				Q.X += 30.0 * Dt;
				AddedSlow += Slow.Offer(Q, Step * Dt, 0.5f, 50.0) ? 1 : 0;
			}
			Expect(AddedSlow >= 5 && AddedSlow <= 7, FString::Printf(TEXT("a ship at 30 m/s over ten seconds left %d notes (one per 50 m: six)"), AddedSlow));
			// a wake with nothing in it, and a wake that has all aged
			FWake None;
			Expect(WakeSegments(None, P, Now, 20.f, 1, Seg, Motion::WakeCap) == 0, TEXT("an empty wake has pieces"));
			Expect(WakeSegments(W, P, Now + 1000.0, 20.f, 1, Seg, Motion::WakeCap) == 0, TEXT("a wake of a long time ago is still there"));
			Notes.Add(FString::Printf(TEXT("wake: %d notes in a minute at 300 m/s (every %.2f s), %d pieces of a %.0f s wake for a ship %.0f m long"), Added, Motion::WakeStepS, N, Life, C.Len));
		}

		// ---- the pulse: a faint jet blinks, a hard one burns steadily, the duty follows the burn
		{
			double WorstErr = 0.0;
			for (float Level : {0.05f, 0.2f, 0.4f, 0.6f, 0.8f, 0.9f, 1.f})
			{
				int32 On = 0;
				const int32 Samples = 6000;
				for (int32 i = 0; i < Samples; ++i)
				{
					On += PulseOn(Level, i / 600.f, 0.31f) ? 1 : 0;
				}
				const double Duty = (double)On / Samples;
				const double Want = Level >= 0.82f ? 1.0 : FMath::Clamp(0.18 + Level * 0.9, 0.0, 1.0);
				WorstErr = FMath::Max(WorstErr, FMath::Abs(Duty - Want));
			}
			Expect(WorstErr < 0.03, FString::Printf(TEXT("a jet's duty is off by %.3f from its burn"), WorstErr));
			Notes.Add(FString::Printf(TEXT("pulse: the duty follows the burn to %.3f"), WorstErr));
		}

		// ---- a long flight with the AI's habits: random pushes and turns on every class: nothing leaves its range, nothing is a NaN; and the cost
		{
			double Steps = 0.0;
			bool bFinite = true, bRange = true;
			float PeakSeen = 0.f;
			int32 MostLit = 0;
			const double T0 = FPlatformTime::Seconds();
			for (const TCHAR* Key : MoClasses)
			{
				const FJetClass& C = *Data.Find(FName(Key));
				FRandomStream Rng(11);
				FMoRig R;
				R.C = &C;
				R.Vel = FVector(200.0, 0.0, 0.0);
				FVector Acc(0.0), Spin(0.0);
				for (int32 Step = 1; Step <= 300 * 60; ++Step)
				{
					if (Step % 90 == 0)
					{
						Acc = Rng.FRand() < 0.4f ? FVector::ZeroVector : Rng.GetUnitVector() * (R.Acc * Rng.FRandRange(0.f, 1.f));
						Spin = Rng.FRand() < 0.4f ? FVector::ZeroVector : Rng.GetUnitVector() * (R.Rate * Rng.FRandRange(0.f, 1.f));
					}
					R.Vel += Acc * Dt;
					R.Pos += R.Vel * Dt;
					R.Att = (FQuat(Spin.GetSafeNormal(), Spin.Size() * Dt) * R.Att).GetNormalized();
					R.Step(Dt);
					Steps += 1.0;
					bFinite &= !R.M.Kick.ContainsNaN() && !R.M.Lin.ContainsNaN() && !R.M.Omega.ContainsNaN();
					for (float B : R.M.Burn)
					{
						bFinite &= FMath::IsFinite(B);
						bRange &= B >= 0.f && B <= 1.0001f;
						PeakSeen = FMath::Max(PeakSeen, B);
					}
					MostLit = FMath::Max(MostLit, MoLit(R.M.Burn, 0.05f));
				}
			}
			const double Us = (FPlatformTime::Seconds() - T0) * 1.0e6 / Steps;
			Expect(bFinite, TEXT("a NaN in the motion of a ship flown at random"));
			Expect(bRange, TEXT("a jet's burn left 0..1 in a random flight"));
			Notes.Add(FString::Printf(TEXT("random flights: %.0f ship-steps over %d classes, the strongest burn %.2f, most jets lit at once %d, %.2f microseconds a ship a step (Observe + Fire)"), Steps, (int32)UE_ARRAY_COUNT(MoClasses), PeakSeen, MostLit, Us));
			Expect(Us < 40.0, FString::Printf(TEXT("a ship's step costs %.1f microseconds"), Us));
		}
		return Fails.Num() == 0;
	}
}
