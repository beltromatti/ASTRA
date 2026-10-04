// ASTRA — the motion of the capital ships made readable: the jets, their allocation, the wake. See AstraSpaceLifeMotion.h. Plain C++ (the drawing is AstraSpaceLifeMotionDraw.cpp).

#include "AstraSpaceLifeMotion.h"
#include "ASTRA.h"
#include "Dom/JsonObject.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

namespace AstraSpace
{
	using namespace Motion;

	// ------------------------------------------------------------------------------------------------------------------ the jets of a class
	void FJetClass::Finish()
	{
		FVector TMax(0.02 * Len);                    // (the floor: an axis a class has no lever on must not have its noise made into a command)
		for (FJet& J : Jets)
		{
			J.D = J.D.GetSafeNormal();
			J.Push = -J.D;
			J.Turn = FVector::CrossProduct(J.P - Com, J.Push);
			TMax.X = FMath::Max(TMax.X, FMath::Abs(J.Turn.X));
			TMax.Y = FMath::Max(TMax.Y, FMath::Abs(J.Turn.Y));
			TMax.Z = FMath::Max(TMax.Z, FMath::Abs(J.Turn.Z));
		}
		for (FJet& J : Jets)
		{
			J.Turn = FVector(J.Turn.X / TMax.X, J.Turn.Y / TMax.Y, J.Turn.Z / TMax.Z);
		}
	}

	int32 FJetClass::Nearest(const FVector& P) const
	{
		int32 Best = INDEX_NONE;
		double BestD = 1.0e30;
		for (int32 i = 0; i < Jets.Num(); ++i)
		{
			const double D = FVector::DistSquared(Jets[i].P, P);
			if (D < BestD)
			{
				BestD = D;
				Best = i;
			}
		}
		return Best;
	}

	namespace
	{
		FVector MoVec(const TSharedPtr<FJsonObject>& O, const TCHAR* Field, const FVector& Def)
		{
			const TArray<TSharedPtr<FJsonValue>>* A = nullptr;
			if (O.IsValid() && O->TryGetArrayField(Field, A) && A->Num() >= 3)
			{
				return FVector((*A)[0]->AsNumber(), (*A)[1]->AsNumber(), (*A)[2]->AsNumber());
			}
			return Def;
		}

		uint8 MoKind(const FString& K)
		{
			return K == TEXT("yaw") ? 1 : (K == TEXT("pitch") ? 2 : (K == TEXT("brake") ? 3 : 0));
		}
	}

	bool FJetData::Parse(const FString& Json, FString& OutError)
	{
		Classes.Reset();
		TSharedPtr<FJsonObject> Root;
		if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Json), Root) || !Root.IsValid())
		{
			OutError = TEXT("thrusters.json does not parse");
			return false;
		}
		const TSharedPtr<FJsonObject>* Cs = nullptr;
		if (!Root->TryGetObjectField(TEXT("classes"), Cs))
		{
			OutError = TEXT("thrusters.json has no classes");
			return false;
		}
		for (const TPair<FString, TSharedPtr<FJsonValue>>& KV : (*Cs)->Values)
		{
			const TSharedPtr<FJsonObject> O = KV.Value->AsObject();
			if (!O.IsValid())
			{
				continue;
			}
			FJetClass C;
			C.Key = FName(*KV.Key);
			O->TryGetStringField(TEXT("mesh"), C.Mesh);
			C.Len = (float)O->GetNumberField(TEXT("len"));
			C.Com = MoVec(O, TEXT("com"), FVector::ZeroVector);
			C.Box = MoVec(O, TEXT("box"), FVector(C.Len * 0.5, C.Len * 0.1, C.Len * 0.1));
			const TSharedPtr<FJsonObject>* Dr = nullptr;
			if (O->TryGetObjectField(TEXT("drive"), Dr))
			{
				C.DriveP = MoVec(*Dr, TEXT("p"), FVector(-C.Len * 0.5, 0.0, 0.0));
				C.DriveW = (float)(*Dr)->GetNumberField(TEXT("w"));
				C.DriveR = (float)(*Dr)->GetNumberField(TEXT("r"));
			}
			const TArray<TSharedPtr<FJsonValue>>* Ns = nullptr;
			if (O->TryGetArrayField(TEXT("nozzles"), Ns))
			{
				for (const TSharedPtr<FJsonValue>& V : *Ns)
				{
					const TSharedPtr<FJsonObject> N = V->AsObject();
					if (!N.IsValid())
					{
						continue;
					}
					FJet J;
					J.P = MoVec(N, TEXT("p"), FVector::ZeroVector);
					J.D = MoVec(N, TEXT("d"), FVector::ForwardVector);
					J.R = (float)N->GetNumberField(TEXT("r"));
					FString K;
					N->TryGetStringField(TEXT("k"), K);
					J.Kind = MoKind(K);
					C.Jets.Add(J);
				}
			}
			C.Finish();
			Classes.Add(C.Key, MoveTemp(C));
		}
		return Classes.Num() > 0;
	}

	namespace
	{
		FJetData GJetData;

		void MoLoad()
		{
			GJetData = FJetData();
			const FString A = FPaths::Combine(FPaths::ProjectContentDir(), TEXT("ASTRA/Data/space"));
			const FString B = FPaths::Combine(FPaths::ProjectDir(), TEXT("data/space"));
			const FString* Dir = FPaths::FileExists(A / TEXT("thrusters.json")) ? &A : (FPaths::FileExists(B / TEXT("thrusters.json")) ? &B : nullptr);
			if (!Dir)
			{
				UE_LOG(LogASTRA, Warning, TEXT("[Space] data/space/thrusters.json is missing: no manoeuvring jets (art/blender/space3_thrusters.py, then tools/space.py sync)"));
				return;
			}
			FString Text, Error;
			FFileHelper::LoadFileToString(Text, *(*Dir / TEXT("thrusters.json")));
			if (!GJetData.Parse(Text, Error))
			{
				UE_LOG(LogASTRA, Warning, TEXT("[Space] %s (%s)"), *Error, **Dir);
				return;
			}
			GJetData.bLoaded = true;
			GJetData.Source = *Dir;
			int32 N = 0;
			for (const TPair<FName, FJetClass>& KV : GJetData.Classes)
			{
				N += KV.Value.Jets.Num();
			}
			UE_LOG(LogASTRA, Log, TEXT("[Space] jets from %s: %d classes, %d nozzles"), **Dir, GJetData.Classes.Num(), N);
		}
	}

	const FJetData& JetData()
	{
		static bool bDone = false;
		if (!bDone)
		{
			bDone = true;
			MoLoad();
		}
		return GJetData;
	}

	void ReloadJetData()
	{
		MoLoad();
	}

	// ------------------------------------------------------------------------------------------------------------------ the allocation
	void Allocate(const FJetClass& C, const FDemand& D, float* Out)
	{
		const FVector Push(FMath::Min(D.Push.X, 0.0), D.Push.Y, D.Push.Z);          // the push ahead is the main drive's
		for (int32 i = 0; i < C.Jets.Num(); ++i)
		{
			const FJet& J = C.Jets[i];
			const float U = (float)(FVector::DotProduct(J.Turn, D.Turn) + FVector::DotProduct(J.Push, Push));
			Out[i] = U <= DeadBand ? 0.f : FMath::Min(1.f, (U - DeadBand) / (1.f - DeadBand));
		}
	}

	// ------------------------------------------------------------------------------------------------------------------ the wake
	bool FWake::Offer(const FVector& P, double T, float Str, double MinMove)
	{
		if (Num > 0)
		{
			if (T - LastT < WakeStepS || FVector::DistSquared(P, LastP) < MinMove * MinMove)
			{
				return false;
			}
		}
		FWakePoint& W = Pts[Next];
		W.P = P;
		W.T = (float)T;
		W.Str = Str;
		Next = (Next + 1) % WakeCap;
		Num = FMath::Min(Num + 1, WakeCap);
		LastT = T;
		LastP = P;
		return true;
	}

	int32 WakeSegments(const FWake& W, const FVector& Head, double Now, float LifeS, int32 Stride, FWakeSeg* Out, int32 Max)
	{
		int32 N = 0;
		if (W.Num == 0 || LifeS <= 0.f)
		{
			return 0;
		}
		Stride = FMath::Max(1, Stride);
		FVector Newer = Head;
		float AgeNewer = 0.f, StrNewer = W.At(0).Str;
		int32 I = 0;
		while (I < W.Num && N < Max)
		{
			const int32 J = FMath::Min(I + Stride - 1, W.Num - 1);
			const FWakePoint& Pt = W.At(J);
			const float Age = (float)((Now - (double)Pt.T) / (double)LifeS);
			if (Age >= 1.f)
			{
				break;                                // (the notes are in order of time: the rest are older)
			}
			FWakeSeg& S = Out[N++];
			S.A = Newer;
			S.B = Pt.P;
			S.AgeA = AgeNewer;
			S.AgeB = FMath::Max(Age, AgeNewer);
			S.Str = StrNewer;
			Newer = Pt.P;
			AgeNewer = S.AgeB;
			StrNewer = Pt.Str;
			I = J + 1;
		}
		return N;
	}

	float WakeLifeFor(float LenM)
	{
		return FMath::Clamp(9.f + 0.016f * LenM, 10.f, 24.f);
	}

	// ------------------------------------------------------------------------------------------------------------------ one ship's motion
	void FMotion::Reset()
	{
		bKnown = false;
		PrevPos = PrevVel = PrevOmega = Kick = Omega = Lin = FVector::ZeroVector;
		PrevAtt = FQuat::Identity;
		Burn.Reset();
		Raw.Reset();
		Peak = 0.f;
		TestLeft = 0.f;
		Test = FDemand();
		bTestAll = false;
		Wake.Reset();
		Class = nullptr;
		ShipId = -1;
		Faction = 0;
		bPowered = true;
		Seen = 0;
		Thrust = 0.f;
	}

	bool FMotion::Bind(const FJetClass* C)
	{
		if (Class == C && Burn.Num() == C->Jets.Num())
		{
			return false;
		}
		Class = C;
		Burn.Init(0.f, C->Jets.Num());
		Raw.Init(0.f, C->Jets.Num());
		return true;
	}

	namespace
	{
		FORCEINLINE FVector MoClampV(const FVector& V, double Lim) { return FVector(FMath::Clamp(V.X, -Lim, Lim), FMath::Clamp(V.Y, -Lim, Lim), FMath::Clamp(V.Z, -Lim, Lim)); }
	}

	void Observe(FMotion& M, const FJetClass& C, const FVector& Pos, const FVector& Vel, const FQuat& Att, float MaxAccel, float MaxTurnRad, float SimDt)
	{
		if (M.Class != &C || M.Burn.Num() != C.Jets.Num())
		{
			M.Bind(&C);
			M.bKnown = false;
		}
		if (M.Seed == 0.f)
		{
			M.Seed = FMath::Frac((float)(GetTypeHash(Pos.X + Pos.Y * 7.0 + Pos.Z * 13.0) & 1023u) / 1023.f + 0.37f);
		}
		bool bJump = !M.bKnown;
		if (M.bKnown)
		{
			const double Step = (Vel.Size() + M.PrevVel.Size()) * 0.5 * FMath::Max(SimDt, 0.f) * 3.0 + 300.0;
			const double Angle = M.PrevAtt.AngularDistance(Att);
			bJump = FVector::DistSquared(Pos, M.PrevPos) > Step * Step || Angle > 0.45 || SimDt > 2.f;
		}
		if (bJump)
		{
			M.bKnown = true;
			M.PrevPos = Pos;
			M.PrevVel = Vel;
			M.PrevAtt = Att;
			M.PrevOmega = M.Kick = M.Omega = M.Lin = FVector::ZeroVector;
			M.Wake.Reset();
			return;
		}
		if (SimDt < 1.0e-4f)
		{
			return;                                   // the battle is stopped: nothing has changed
		}
		const FVector AccBody = Att.UnrotateVector((Vel - M.PrevVel) / SimDt);
		FQuat Dq = Att * M.PrevAtt.Inverse();
		Dq.Normalize();
		if (Dq.W < 0.0)
		{
			Dq = FQuat(-Dq.X, -Dq.Y, -Dq.Z, -Dq.W);
		}
		FVector Axis;
		double Angle;
		Dq.ToAxisAndAngle(Axis, Angle);
		const FVector OmegaBody = Angle > 1.0e-7 ? Att.UnrotateVector(Axis * (Angle / (double)SimDt)) : FVector::ZeroVector;
		const double InvTurn = 1.0 / FMath::Max(MaxTurnRad, 1.0e-3f);
		M.Kick = MoClampV(M.Kick + MoClampV((OmegaBody - M.PrevOmega) * InvTurn, 1.6), 2.0);
		M.Omega = MoClampV(OmegaBody * InvTurn, 1.5);
		M.PrevOmega = OmegaBody;
		const FVector Want = MoClampV(AccBody / (double)FMath::Max(MaxAccel, 0.1f), 1.5);
		const auto Smooth = [SimDt](double Cur, double To)
		{
			const float Tc = FMath::Abs(To) > FMath::Abs(Cur) ? LinAttackS : LinReleaseS;
			return Cur + (To - Cur) * (1.0 - FMath::Exp(-SimDt / Tc));
		};
		M.Lin = FVector(Smooth(M.Lin.X, Want.X), Smooth(M.Lin.Y, Want.Y), Smooth(M.Lin.Z, Want.Z));
		M.PrevPos = Pos;
		M.PrevVel = Vel;
		M.PrevAtt = Att;
	}

	FDemand DemandOf(const FMotion& M)
	{
		FDemand D;
		D.Turn = M.Kick + M.Omega * TrimK;
		const auto Dead = [](double X) { const double A = FMath::Abs(X); return A <= PushDead ? 0.0 : FMath::Sign(X) * (A - PushDead) / (1.0 - PushDead); };
		D.Push = FVector(Dead(M.Lin.X), Dead(M.Lin.Y), Dead(M.Lin.Z));
		if (M.TestLeft > 0.f)
		{
			D.Turn += M.Test.Turn;
			D.Push += M.Test.Push;
		}
		return D;
	}

	void Fire(FMotion& M, const FJetClass& C, float RealDt)
	{
		const int32 N = C.Jets.Num();
		if (M.Burn.Num() != N)
		{
			M.Bind(&C);
		}
		const float Dt = FMath::Clamp(RealDt, 0.f, 0.25f);
		M.Kick *= (double)FMath::Exp(-Dt / TauKick);
		if (M.TestLeft > 0.f)
		{
			M.TestLeft -= Dt;
			if (M.TestLeft <= 0.f)
			{
				M.bTestAll = false;
			}
		}
		const FDemand D = DemandOf(M);
		const bool bAll = M.TestLeft > 0.f && M.bTestAll;
		if (!bAll && D.IsIdle() && M.Peak <= 0.f)
		{
			return;                                   // nothing asked and nothing burning: no work
		}
		if (bAll)
		{
			for (int32 i = 0; i < N; ++i)
			{
				M.Raw[i] = 1.f;
			}
		}
		else if (D.IsIdle())
		{
			FMemory::Memzero(M.Raw.GetData(), sizeof(float) * N);
		}
		else
		{
			Allocate(C, D, M.Raw.GetData());
		}
		float Peak = 0.f;
		const float KUp = 1.f - FMath::Exp(-Dt / AttackS), KDown = 1.f - FMath::Exp(-Dt / ReleaseS);
		for (int32 i = 0; i < N; ++i)
		{
			float& B = M.Burn[i];
			const float Want = M.Raw[i];
			B += (Want - B) * (Want > B ? KUp : KDown);
			if (B < 0.004f)
			{
				B = 0.f;
			}
			Peak = FMath::Max(Peak, B);
		}
		M.Peak = Peak;
	}

	bool PulseOn(float Level, float Clock, float Phase)
	{
		if (Level >= 0.82f)
		{
			return true;
		}
		const float Duty = FMath::Clamp(0.18f + Level * 0.9f, 0.f, 1.f);
		return FMath::Frac(Clock * 8.f + Phase) < Duty;
	}
}
