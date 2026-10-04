// ASTRA — what the war leaves in a system: the records, their motion as arithmetic, the pods and their beacons, what the crew is told, the file. See AstraWrecks.h and docs/SPAZIO.md.

#include "AstraWrecks.h"
#include "ASTRA.h"
#include "Dom/JsonValue.h"

namespace AstraSpace
{
	namespace
	{
		constexpr double WkTwoPi = 6.283185307179586;

		/** A hash of three numbers: the chunks of a field are made from its seed and their index with it (nothing of them is kept, nothing of them is random per run). */
		uint32 WkHash(uint32 A, uint32 B, uint32 C)
		{
			uint32 H = A * 0x9E3779B1u ^ (B + 0x7F4A7C15u + (A << 6) + (A >> 2));
			H ^= C * 0x85EBCA6Bu + 0xC2B2AE35u;
			H ^= H >> 15; H *= 0x2C1B3C6Du; H ^= H >> 12; H *= 0x297A2D39u; H ^= H >> 15;
			return H;
		}
		float WkUnit(uint32 H) { return (float)(H & 0xFFFFFFu) / (float)0x1000000u; }

		/** The fraction of a turn an angle makes (a spin kept for hours must not lose its precision in a float). */
		double WkWrap(double Rad) { return FMath::Fmod(Rad, WkTwoPi); }

		FVector WkUnitVec(float U1, float U2)
		{
			const float Z = 2.f * U1 - 1.f;
			const float Ph = (float)WkTwoPi * U2;
			const float R = FMath::Sqrt(FMath::Max(0.f, 1.f - Z * Z));
			return FVector(R * FMath::Cos(Ph), R * FMath::Sin(Ph), Z);
		}

		// The file keeps every number as a whole number in a unit of its own (decimetres, ten-thousandths of a metre a second, milliseconds): a double is printed with seventeen digits,
		// and a rounded decimal never prints short, so a save of decimals is twice the size and does not read back to what it was.
		constexpr double KPos = 0.1, KVel = 1e-4, KQuat = 1e-4, KRate = 1e-6, KTime = 1e-3, KLen = 0.1, KLocal = 0.01, KScale = 1e-3, KSpeed = 0.01;

		void WkPut(TArray<TSharedPtr<FJsonValue>>& A, double V, double Unit)
		{
			A.Add(MakeShared<FJsonValueNumber>(FMath::RoundToDouble(V / Unit)));
		}

		void WkPutVec(TArray<TSharedPtr<FJsonValue>>& A, const FVector& V, double Unit)
		{
			WkPut(A, V.X, Unit);
			WkPut(A, V.Y, Unit);
			WkPut(A, V.Z, Unit);
		}

		void WkPutQuat(TArray<TSharedPtr<FJsonValue>>& A, const FQuat& Q)
		{
			WkPut(A, Q.X, KQuat);
			WkPut(A, Q.Y, KQuat);
			WkPut(A, Q.Z, KQuat);
			WkPut(A, Q.W, KQuat);
		}

		double WkGet(const TArray<TSharedPtr<FJsonValue>>& A, int32 I, double Unit)
		{
			return A.IsValidIndex(I) && A[I].IsValid() ? A[I]->AsNumber() * Unit : 0.0;
		}

		FVector WkVec(const TArray<TSharedPtr<FJsonValue>>& A, int32 I, double Unit)
		{
			return FVector(WkGet(A, I, Unit), WkGet(A, I + 1, Unit), WkGet(A, I + 2, Unit));
		}

		FQuat WkQuat(const TArray<TSharedPtr<FJsonValue>>& A, int32 I)
		{
			FQuat Q(WkGet(A, I, KQuat), WkGet(A, I + 1, KQuat), WkGet(A, I + 2, KQuat), WkGet(A, I + 3, KQuat));
			return Q.SizeSquared() > 1e-6 ? Q.GetNormalized() : FQuat::Identity;
		}

		FString WkWhere(const FVector& From, const FVector& P)
		{
			return FString::Printf(TEXT("bearing %03.0f, mark %+.0f, %.0f km"), BearingDegFromTo(From, P), MarkDegFromTo(From, P), FVector::Dist(From, P) / OneKm);
		}

		const TCHAR* WkWhose(uint8 Faction)
		{
			return Faction == 0 ? TEXT("ASTRA") : (Faction == 1 ? TEXT("Mandate") : TEXT("civilian"));
		}

		/** "2 h 40 min", "35 min", "50 s": how long a thing has been so, or has to go. */
		FString WkSpan(double Seconds)
		{
			const int32 S = FMath::Max(0, FMath::RoundToInt((float)Seconds));
			if (S >= 3600)
			{
				return FString::Printf(TEXT("%d h %02d min"), S / 3600, (S % 3600) / 60);
			}
			return S >= 90 ? FString::Printf(TEXT("%d min"), FMath::RoundToInt(S / 60.f)) : FString::Printf(TEXT("%d s"), FMath::Max(S, 5) / 5 * 5);
		}

		const TCHAR* WkSectionWord(uint8 Section)
		{
			static const TCHAR* const N[3] = {TEXT("bow section"), TEXT("middle section"), TEXT("stern section")};
			return Section < 3 ? N[Section] : TEXT("hull");
		}
	}

	// ------------------------------------------------------------------------------------------------------------------ small things
	const TCHAR* HowLostName(EHowLost H)
	{
		static const TCHAR* const N[(int32)EHowLost::Num] = {TEXT("breakup"), TEXT("reactor"), TEXT("destroyed")};
		return N[FMath::Clamp((int32)H, 0, (int32)EHowLost::Num - 1)];
	}

	EHowLost HowLostFromName(const FString& Name)
	{
		for (int32 i = 0; i < (int32)EHowLost::Num; ++i)
		{
			if (Name.Equals(HowLostName((EHowLost)i), ESearchCase::IgnoreCase))
			{
				return (EHowLost)i;
			}
		}
		return EHowLost::Destroyed;
	}

	double BearingDegFromTo(const FVector& From, const FVector& To)
	{
		const FVector D = To - From;
		return FMath::Fmod(FMath::RadiansToDegrees(FMath::Atan2(D.Y, D.X)) + 360.0, 360.0);
	}

	double MarkDegFromTo(const FVector& From, const FVector& To)
	{
		const FVector D = To - From;
		return FMath::RadiansToDegrees(FMath::Atan2(D.Z, FVector2D(D.X, D.Y).Size()));
	}

	int32 FWrecks::ComplementOf(FName ClassKey, float RadiusM, uint8 Faction)
	{
		// the plans' rosters (data/ship/plans/<class>.json, roster.complement; tools/space.py test checks that these still agree)
		static const struct { const TCHAR* Key; int32 N; } Table[] = {{TEXT("praetorian"), 1020}, {TEXT("acheron"), 380}, {TEXT("styx"), 140}, {TEXT("vigilant"), 118},
		                                                              {TEXT("lethe"), 62}, {TEXT("station"), 48}, {TEXT("freighter"), 34}};
		const FString K = ClassKey.ToString().ToLower();
		for (const auto& T : Table)
		{
			if (K == T.Key)
			{
				return T.N;
			}
		}
		// a class with no plan: the way the rosters grow with the hull (118 at 140 m, 1020 at 460 m), the civilians' crews much smaller
		const double N = 118.0 * FMath::Pow(FMath::Max(RadiusM, 20.f) / 140.0, 1.7);
		return FMath::Clamp(FMath::RoundToInt((float)(Faction == 2 ? N * 0.3 : N)), 4, 1200);
	}

	int32 FWrecks::PodCountFor(EHowLost How, int32 Complement, int32 Alive, FRandomStream& Rng)
	{
		if (Alive <= 0)
		{
			return 0;
		}
		const float Base = FMath::Clamp((float)Complement / 22.f, 1.f, (float)MaxPods);
		int32 N = 0;
		switch (How)
		{
		case EHowLost::Breakup:
			N = FMath::RoundToInt(Base * (0.55f + 0.45f * Rng.FRand()));            // the sections that hold have time to launch before the one that lets go
			break;
		case EHowLost::Reactor:
			N = Rng.FRand() < 0.4f ? 1 + (Rng.FRand() < 0.4f ? 1 : 0) : 0;         // the blast takes most of what could have got away
			break;
		default:
			N = FMath::RoundToInt(Base * 0.35f * (0.5f + Rng.FRand()));
			break;
		}
		return FMath::Clamp(N, 0, FMath::Min(MaxPods, Alive));
	}

	int32 FWrecks::ChunkCountFor(float RadiusM, EHowLost How)
	{
		const float K = How == EHowLost::Reactor ? 0.55f : (How == EHowLost::Breakup ? 0.42f : 0.34f);
		return FMath::Clamp(FMath::RoundToInt(RadiusM * K), 20, MaxChunks);
	}

	FQuat FWrecks::AttAt(const FPieceRec& P, double Now)
	{
		return (FQuat(P.SpinAxis, WkWrap((double)P.SpinRate * (Now - P.T0))) * P.Att0).GetNormalized();
	}

	FQuat FWrecks::AttAt(const FPodRec& P, double Now)
	{
		return (FQuat(P.SpinAxis, WkWrap((double)P.SpinRate * (Now - P.T0))) * P.Att0).GetNormalized();
	}

	float FWrecks::FieldRadiusAt(const FFieldRec& F, double Now)
	{
		return F.R0 * 0.5f + F.Fast * (float)FMath::Max(0.0, Now - F.T0);
	}

	FVector FWrecks::Middle(const FSite& S, double Now) const
	{
		if (S.Pieces.Num() == 0)
		{
			return S.Pos0 + S.Vel * (Now - S.DiedAt);
		}
		FVector Sum = FVector::ZeroVector;
		for (const FPieceRec& P : S.Pieces)
		{
			Sum += PosAt(P, Now);
		}
		return Sum / (double)S.Pieces.Num();
	}

	void FWrecks::PodPose(uint32 SiteSeed, int32 Index, const FVector& Vel, FQuat& Att0, FVector& SpinAxis, float& SpinRate)
	{
		const auto U = [SiteSeed, Index](uint32 K) { return WkUnit(WkHash(SiteSeed, 0x5000u + (uint32)Index, K)); };
		SpinAxis = WkUnitVec(U(0), U(1));
		SpinRate = 0.01f + 0.07f * U(2);
		const FVector Fwd = Vel.SizeSquared() > 1e-6 ? Vel.GetSafeNormal() : WkUnitVec(U(5), U(6));
		Att0 = FRotationMatrix::MakeFromXZ(Fwd, WkUnitVec(U(3), U(4))).ToQuat();
	}

	// ------------------------------------------------------------------------------------------------------------------ the debris
	void FWrecks::MakeDefs(FSite& S)
	{
		const FFieldRec& F = S.Field;
		if (S.Defs.Num() == F.Count)
		{
			return;
		}
		S.Defs.SetNum(F.Count);
		for (int32 i = 0; i < F.Count; ++i)
		{
			const auto U = [&F, i](uint32 K) { return WkUnit(WkHash(F.Seed, (uint32)i, K)); };
			FChunkDef& D = S.Defs[i];
			D.Dir = FVector3f(WkUnitVec(U(0), U(1)));
			D.Speed = F.Slow + (F.Fast - F.Slow) * FMath::Pow(U(2), 2.2f);          // most are slow, a few fly
			D.Off = F.R0 * 0.5f * U(3);
			D.SpinAxis = FVector3f(WkUnitVec(U(4), U(5)));
			D.SpinRate = 0.02f + 0.6f * FMath::Pow(U(6), 1.6f);                    // 1 to 35 degrees a second
			const FVector A = WkUnitVec(U(7), U(8));
			D.Att0 = FQuat4f(FVector3f(A), U(9) * (float)WkTwoPi);
			D.Size = F.SizeK * FMath::Lerp(0.45f, 1.6f, FMath::Pow(U(10), 1.5f));
			const float Sh = U(11);
			D.Shape = Sh < 0.45f ? 0 : (Sh < 0.65f ? 1 : 2);                       // plates, a few girders, chunks
			D.Heat = U(12);
		}
	}

	FQuat FWrecks::ChunkAttitude(const FSite& S, int32 Index, double Now)
	{
		const FChunkDef& D = S.Defs[Index];
		return (FQuat(FVector(D.SpinAxis), WkWrap((double)D.SpinRate * (Now - S.Field.T0))) * FQuat(D.Att0)).GetNormalized();
	}

	bool FWrecks::ChunkAt(const FSite& S, int32 Index, double Now, FChunk& Out, bool bAtt)
	{
		const FFieldRec& F = S.Field;
		if (!S.Defs.IsValidIndex(Index) || Now < F.T0)
		{
			return false;
		}
		const double T = Now - F.T0;
		const FChunkDef& D = S.Defs[Index];
		Out.Pos = F.Pos0 + F.Vel * T + FVector(D.Dir) * ((double)D.Off + (double)D.Speed * T);
		if (bAtt)
		{
			Out.Att = ChunkAttitude(S, Index, Now);
		}
		Out.Size = D.Size;
		Out.Shape = D.Shape;
		const float E = D.Heat * (float)FMath::Exp(-T / (double)FMath::Max(1.f, F.EmberTauS));
		Out.Ember = E > 0.04f ? E : 0.f;
		return true;
	}

	// ------------------------------------------------------------------------------------------------------------------ the life of the sites
	void FWrecks::Reset()
	{
		Items.Reset();
		JsonCache.Reset();
		NextId = 1;
		Losses = Told = Taken = Pruned = 0;
	}

	const FSite& FWrecks::AddLoss(const FString& System, const FLoss& Loss, const TArray<FPieceIn>& Pieces, double Now, uint32 Seed, const FSkyFrame& Frame)
	{
		Prune(Now);                                     // (room first: the new site stays where it is put)
		FRandomStream Rng((int32)(Seed & 0x7FFFFFFF));
		FSite S;
		S.Id = NextId++;
		S.System = System.ToLower();
		S.ShipId = Loss.ShipId;
		S.Name = Loss.Name;
		S.Class = Loss.Class;
		S.Contact = Loss.Contact;
		S.KnownAs = Loss.KnownAs.IsEmpty() ? Loss.Name : Loss.KnownAs;
		S.HullMesh = Loss.HullMesh;
		S.ClassKey = Loss.ClassKey;
		S.Faction = Loss.Faction;
		S.How = Loss.How;
		S.Section = Loss.Section;
		S.DiedAt = Now;
		S.Pos0 = Frame.FromSystem(Loss.Pos);
		S.Vel = Frame.DirFromSystem(Loss.Vel);
		S.Radius = Loss.Radius;
		S.Aboard = Loss.Aboard;
		FAboard& Ab = S.Aboard;
		if (Ab.Complement <= 0)
		{
			Ab.Complement = ComplementOf(Loss.ClassKey, Loss.Radius, Loss.Faction);
		}
		if (!Ab.bInside)
		{
			Ab.Alive = Ab.Complement;                    // a hull with no inside: all hands, as the class carries them
			Ab.Killed = 0;
		}
		// the pieces: those the war's effects made (they hold them as actors for the first minute: bInFx), else the whole hull, burnt dark, as the war's older explosion leaves it
		for (const FPieceIn& In : Pieces)
		{
			FPieceRec P;
			P.Section = In.Section;
			P.PivotLocal = In.PivotLocal;
			P.Pos0 = Frame.FromSystem(In.Pivot);
			P.Vel = Frame.DirFromSystem(In.Vel);
			P.Att0 = Frame.FromSystem(In.Att);
			P.SpinAxis = Frame.DirFromSystem(In.SpinAxis);
			P.SpinRate = In.SpinRate;
			P.T0 = Now;
			P.Radius = In.Radius;
			P.bBurnt = In.bReactor;
			P.bInFx = true;
			S.Pieces.Add(P);
		}
		if (Pieces.Num() == 0)
		{
			FPieceRec P;
			P.Section = 255;
			P.Pos0 = S.Pos0;
			P.Vel = S.Vel * 0.55 + Rng.GetUnitVector() * 4.0;
			P.Att0 = Frame.FromSystem(Loss.Att);
			P.SpinAxis = Rng.GetUnitVector();
			P.SpinRate = FMath::DegreesToRadians(Rng.FRandRange(1.5f, 4.5f));
			P.T0 = Now;
			P.Radius = Loss.Radius * 0.8f;
			P.bBurnt = true;
			P.bInFx = true;                              // (the war's own hulk actor stands for it, until the system is left)
			S.Pieces.Add(P);
		}
		// the field of debris
		{
			FFieldRec& F = S.Field;
			F.Count = ChunkCountFor(Loss.Radius, Loss.How);
			F.Seed = (uint32)Rng.GetUnsignedInt();
			F.Pos0 = Frame.FromSystem(Loss.BoxMid.IsZero() ? Loss.Pos : Loss.BoxMid);
			F.Vel = S.Vel * (Loss.How == EHowLost::Reactor ? 0.9 : 0.6);
			F.T0 = Now;
			F.R0 = Loss.Radius;
			F.Slow = Loss.How == EHowLost::Reactor ? 2.f : 0.6f;
			F.Fast = Loss.How == EHowLost::Reactor ? 55.f : (Loss.How == EHowLost::Breakup ? 14.f : 22.f);
			F.SizeK = FMath::Clamp(FMath::Pow(Loss.Radius / 150.f, 0.45f), 0.7f, 1.8f);
			F.EmberTauS = Loss.How == EHowLost::Reactor ? 140.f : 70.f;
		}
		// the lifepods: those who got away before she went, by the rule of how she went
		{
			const int32 Alive = Ab.Alive;
			int32 N = PodCountFor(Loss.How, Ab.Complement, Alive, Rng);
			const int32 Cap = FMath::Clamp(Ab.Complement / 16, 4, 12);
			int32 Left = FMath::Min(Alive, FMath::FloorToInt(Alive * 0.6f));             // never more than six in ten of the living
			const FVector Half = Loss.BoxHalf;
			for (int32 k = 0; k < N && Left > 0; ++k)
			{
				FPodRec P;
				P.Survivors = FMath::Min(Left, Rng.RandRange(FMath::Max(1, Cap / 2), Cap));
				Left -= P.Survivors;
				P.T0 = Now + 0.5 + 5.0 * Rng.FRand();
				// out of the hull, from a part that held: along her length, on the side of the box, in the way the lifepod's own motor pushes it (clear of the axis)
				float X = Rng.FRandRange(-1.f, 1.f);
				if (Loss.How == EHowLost::Breakup)
				{
					for (int32 Try = 0; Try < 6; ++Try)
					{
						const int32 Third = X > 0.33f ? 0 : (X < -0.33f ? 2 : 1);
						if (Third != (int32)Loss.Section)
						{
							break;
						}
						X = Rng.FRandRange(-1.f, 1.f);
					}
				}
				FVector Side = Rng.GetUnitVector();
				Side.X = 0.0;
				Side = Side.GetSafeNormal();
				if (Side.IsNearlyZero())
				{
					Side = FVector::UpVector;
				}
				const FVector Local(X * Half.X, Side.Y * Half.Y, Side.Z * Half.Z);
				const FVector HullPos = Loss.Pos + Loss.Vel * (P.T0 - Now);
				const FVector AtSystem = (Loss.BoxMid.IsZero() ? HullPos : Loss.BoxMid + Loss.Vel * (P.T0 - Now)) + Loss.Att.RotateVector(Local);
				const FVector Kick = (Loss.Att.RotateVector(Side + Rng.GetUnitVector() * 0.25)).GetSafeNormal();
				const float KickMps = Loss.How == EHowLost::Reactor ? Rng.FRandRange(35.f, 90.f) : (Loss.How == EHowLost::Breakup ? Rng.FRandRange(6.f, 16.f) : Rng.FRandRange(8.f, 20.f));
				P.Pos0 = Frame.FromSystem(AtSystem);
				P.Vel = Frame.DirFromSystem(Loss.Vel + Kick * KickMps);
				PodPose(S.Field.Seed, k, P.Vel, P.Att0, P.SpinAxis, P.SpinRate);
				P.BeaconDelayS = Rng.FRandRange(20.f, 60.f);
				P.AirS = (float)PodAirS * Rng.FRandRange(0.45f, 1.f);
				S.Pods.Add(P);
			}
			int32 Out = 0;
			for (const FPodRec& P : S.Pods)
			{
				Out += P.Survivors;
			}
			Ab.Escaped = Out;
			Ab.Lost = FMath::Max(0, Alive - Out);
		}
		++Losses;
		Items.Add(MoveTemp(S));
		return Items.Last();
	}

	void FWrecks::Settle(double Now)
	{
		for (FSite& S : Items)
		{
			for (FPodRec& P : S.Pods)
			{
				if (P.State == 0 && Now >= P.T0 + P.AirS)
				{
					P.State = 2;
					P.EndedAt = P.T0 + P.AirS;
					S.bDirty = true;
				}
			}
		}
	}

	void FWrecks::ReAnchor(FSite& Site, FPieceRec& P, double Now, const FSkyFrame& Frame, const FVector& Pivot, const FVector& Vel, const FQuat& Att, const FVector& SpinAxis, float SpinRate)
	{
		P.Pos0 = Frame.FromSystem(Pivot);
		P.Vel = Frame.DirFromSystem(Vel);
		P.Att0 = Frame.FromSystem(Att);
		P.SpinAxis = Frame.DirFromSystem(SpinAxis);
		P.SpinRate = SpinRate;
		P.T0 = Now;
		P.bInFx = false;
		Site.bDirty = true;
	}

	// ------------------------------------------------------------------------------------------------------------------ what the crew is told
	void FWrecks::Think(const FString& System, double Now, const FSkyFrame& Frame, const FVector& Aquila, const FVector* Falcon, bool bFight, TArray<FEvent>& Out)
	{
		const FString Sys = System.ToLower();
		struct FDue { int32 Site; double Km; FVector At; };
		TArray<FDue> Due;
		for (int32 si = 0; si < Items.Num(); ++si)
		{
			FSite& S = Items[si];
			if (S.System != Sys)
			{
				continue;
			}
			// the air that runs out
			bool bAnyAdrift = false, bAnyBeacon = false, bAnyEnded = false, bAllCalling = true;
			double Nearest = 1e18;
			FVector NearestAt = FVector::ZeroVector;
			for (FPodRec& P : S.Pods)
			{
				if (P.State == 0 && Now >= P.T0 + P.AirS)
				{
					P.State = 2;
					P.EndedAt = P.T0 + P.AirS;
					S.bDirty = true;
				}
				bAnyAdrift |= P.State == 0;
				bAnyEnded |= P.State == 2;
				bAllCalling &= !(P.State == 0 && Now < P.T0 + P.BeaconDelayS);       // (a lifepod clears the wreck before its beacon starts)
				if (BeaconOn(P, Now))
				{
					bAnyBeacon = true;
					const FVector At = Frame.ToSystem(PosAt(P, Now));
					const double D = FVector::Dist(At, Aquila);
					if (D < Nearest)
					{
						Nearest = D;
						NearestAt = At;
					}
				}
			}
			// the beacons of a wreck are told once all of them are calling (they start over the first minute): one report says how many
			if (bAnyBeacon && bAllCalling && !S.bToldBeacon && Nearest < BeaconKm * OneKm)
			{
				Due.Add({si, Nearest, NearestAt});
			}
			if (S.bToldBeacon && !S.bToldSilent && !bAnyAdrift && bAnyEnded)
			{
				S.bToldSilent = true;
				S.bDirty = true;
				int32 Lost = 0;
				for (const FPodRec& P : S.Pods)
				{
					Lost += P.State == 2 ? P.Survivors : 0;
				}
				FEvent E;
				E.Kind = EEventKind::BeaconSilent;
				E.bReport = true;
				E.At = Frame.ToSystem(Middle(S, Now));
				E.Text = FString::Printf(TEXT("sensors: the lifepod beacons of %s have gone silent — the air ran out %s after she was lost; %d survivor%s were reported in them"),
				                         *S.KnownAs, *WkSpan(Now - S.DiedAt), Lost, Lost == 1 ? TEXT("") : TEXT("s"));
				Out.Add(E);
			}
			// a close look: a piece within a few kilometres of the Aquila (or of the Captain's Falcon)
			if (!S.bToldClose)
			{
				int32 Close = INDEX_NONE;
				double Best = CloseKm * OneKm;
				FVector CloseAt = FVector::ZeroVector;
				for (int32 pi = 0; pi < S.Pieces.Num(); ++pi)
				{
					const FVector At = Frame.ToSystem(PosAt(S.Pieces[pi], Now));
					double D = FVector::Dist(At, Aquila);
					if (Falcon)
					{
						D = FMath::Min(D, FVector::Dist(At, *Falcon));
					}
					if (D < Best)
					{
						Best = D;
						Close = pi;
						CloseAt = At;
					}
				}
				if (Close != INDEX_NONE && Now - S.DiedAt > 20.0)
				{
					S.bToldClose = true;
					S.bDirty = true;
					++Told;
					FEvent E;
					E.Kind = EEventKind::WreckLook;
					E.bReport = !bFight;
					E.At = CloseAt;
					E.Text = FString::Printf(TEXT("sensors: a close look at the %s — %s"), *Describe(S, Close, Now), *WkWhere(Aquila, CloseAt));
					Out.Add(E);
				}
			}
		}
		if (Due.Num())
		{
			// the nearest first, in one call (the comms' watch is not a switchboard): up to three wrecks in the line, the rest counted
			Due.Sort([](const FDue& A, const FDue& B) { return A.Km < B.Km; });
			TArray<FString> Parts;
			int32 Pods = 0, People = 0;
			for (int32 i = 0; i < Due.Num(); ++i)
			{
				FSite& S = Items[Due[i].Site];
				S.bToldBeacon = true;
				S.bDirty = true;
				int32 N = 0, Surv = 0;
				double Air = 1e18;
				for (const FPodRec& P : S.Pods)
				{
					if (BeaconOn(P, Now))
					{
						++N;
						Surv += P.Survivors;
						Air = FMath::Min(Air, AirLeft(P, Now));             // (the one that matters to a rescue is the first to run out)
					}
				}
				Pods += N;
				People += Surv;
				if (i < 3)
				{
					Parts.Add(FString::Printf(TEXT("%d %s lifepod%s of %s (%d survivor%s, air for %s at the least), the nearest %s"), N, WkWhose(S.Faction), N == 1 ? TEXT("") : TEXT("s"), *S.KnownAs, Surv,
					                          Surv == 1 ? TEXT("") : TEXT("s"), *WkSpan(Air), *WkWhere(Aquila, Due[i].At)));
				}
			}
			++Told;
			FEvent E;
			E.Kind = EEventKind::Beacon;
			E.bReport = !bFight;
			E.At = Due[0].At;
			E.Text = FString::Printf(TEXT("sensors: distress beacons — %s%s"), *FString::Join(Parts, TEXT("; ")),
			                         Due.Num() > 3 ? *FString::Printf(TEXT("; %d more wrecks are calling too (%d lifepods and %d survivors in all)"), Due.Num() - 3, Pods, People) : TEXT(""));
			Out.Add(E);
		}
	}

	FString FWrecks::Describe(const FSite& S, int32 Piece, double Now) const
	{
		const double Ago = Now - S.DiedAt;
		FString What;
		if (Piece >= 0 && S.Pieces.IsValidIndex(Piece) && S.Pieces[Piece].Section < 3)
		{
			What = FString::Printf(TEXT("%s of %s"), WkSectionWord(S.Pieces[Piece].Section), *S.Name);
		}
		else
		{
			What = FString::Printf(TEXT("wreck of %s"), *S.Name);
		}
		FString Text = FString::Printf(TEXT("%s (%s%s)"), *What, S.Contact.IsEmpty() ? TEXT("") : *FString::Printf(TEXT("%s, "), *S.Contact), *S.Class);
		Text += FString::Printf(TEXT(", lost %s ago when %s"), *WkSpan(Ago),
		                        S.How == EHowLost::Reactor ? TEXT("her reactor breached") : (S.How == EHowLost::Breakup ? TEXT("her hull broke apart") : TEXT("she was destroyed")));
		if (Piece >= 0 && S.Pieces.IsValidIndex(Piece))
		{
			const FPieceRec& P = S.Pieces[Piece];
			Text += FString::Printf(TEXT(": no power, no transponder, no life signs; tumbling at about %.1f deg/s%s"), FMath::RadiansToDegrees(P.SpinRate), P.bBurnt ? TEXT(", the hull charred by the blast") : TEXT(""));
			if (Ago < 70.0)
			{
				Text += TEXT(", the torn ends still glowing");
			}
		}
		const int32 Pods = S.Pods.Num();
		if (Pods)
		{
			Text += FString::Printf(TEXT("; %d lifepod%s got away"), Pods, Pods == 1 ? TEXT("") : TEXT("s"));
		}
		if (S.Field.Count)
		{
			Text += FString::Printf(TEXT("; some %d pieces of wreckage spread over %.1f km"), S.Field.Count, 2.0 * FieldRadiusAt(S.Field, Now) / OneKm);
		}
		return Text;
	}

	// ------------------------------------------------------------------------------------------------------------------ queries
	const FSite* FWrecks::FindById(int32 Id) const
	{
		return Items.FindByPredicate([Id](const FSite& S) { return S.Id == Id; });
	}

	const FSite* FWrecks::FindByShip(int32 ShipId, const FString& System) const
	{
		const FString Sys = System.ToLower();
		for (int32 i = Items.Num() - 1; i >= 0; --i)
		{
			if (Items[i].ShipId == ShipId && (Sys.IsEmpty() || Items[i].System == Sys))
			{
				return &Items[i];
			}
		}
		return nullptr;
	}

	const FSite* FWrecks::FindByContact(const FString& Contact, const FString& System) const
	{
		const FString Sys = System.ToLower();
		for (int32 i = Items.Num() - 1; i >= 0; --i)
		{
			if (Items[i].Contact.Equals(Contact, ESearchCase::IgnoreCase) && (Sys.IsEmpty() || Items[i].System == Sys))
			{
				return &Items[i];
			}
		}
		return nullptr;
	}

	void FWrecks::Of(const FString& System, TArray<int32>& Out) const
	{
		const FString Sys = System.ToLower();
		for (int32 i = 0; i < Items.Num(); ++i)
		{
			if (Items[i].System == Sys)
			{
				Out.Add(i);
			}
		}
	}

	void FWrecks::Beacons(const FString& System, double Now, const FSkyFrame& Frame, const FVector& From, double RangeKm, TArray<FBeacon>& Out) const
	{
		const FString Sys = System.ToLower();
		for (const FSite& S : Items)
		{
			if (S.System != Sys)
			{
				continue;
			}
			for (int32 pi = 0; pi < S.Pods.Num(); ++pi)
			{
				const FPodRec& P = S.Pods[pi];
				if (!BeaconOn(P, Now))
				{
					continue;
				}
				FBeacon B;
				B.Site = S.Id;
				B.Pod = pi;
				B.Pos = Frame.ToSystem(PosAt(P, Now));
				B.Vel = Frame.DirToSystem(P.Vel);
				if (RangeKm > 0.0 && FVector::Dist(B.Pos, From) > RangeKm * OneKm)
				{
					continue;
				}
				B.Survivors = P.Survivors;
				B.AirLeftS = AirLeft(P, Now);
				B.Of = S.KnownAs;
				B.Faction = S.Faction;
				Out.Add(B);
			}
		}
		Out.Sort([&From](const FBeacon& A, const FBeacon& B) { return FVector::DistSquared(A.Pos, From) < FVector::DistSquared(B.Pos, From); });
	}

	FRescued FWrecks::Recover(const FString& System, double Now, const FSkyFrame& Frame, const FVector& AtSystem, double RadiusM, const FString& By)
	{
		const FString Sys = System.ToLower();
		FRescued R;
		for (FSite& S : Items)
		{
			if (S.System != Sys)
			{
				continue;
			}
			for (FPodRec& P : S.Pods)
			{
				if (P.State != 0 || Now >= P.T0 + P.AirS || Now < P.T0)
				{
					continue;
				}
				if (FVector::Dist(Frame.ToSystem(PosAt(P, Now)), AtSystem) > RadiusM)
				{
					continue;
				}
				P.State = 1;
				P.EndedAt = Now;
				P.By = By;
				S.bDirty = true;
				R.Survivors += P.Survivors;
				++R.Pods;
				R.Of = S.KnownAs;
				R.Faction = S.Faction;
				Taken += P.Survivors;
			}
		}
		return R;
	}

	int32 FWrecks::SurvivorsAdrift(const FString& System, double Now) const
	{
		const FString Sys = System.ToLower();
		int32 N = 0;
		for (const FSite& S : Items)
		{
			if (S.System == Sys)
			{
				for (const FPodRec& P : S.Pods)
				{
					N += Alive(P, Now) ? P.Survivors : 0;
				}
			}
		}
		return N;
	}

	FWreckStats FWrecks::Stats(const FString& System, double Now) const
	{
		const FString Sys = System.ToLower();
		FWreckStats St;
		St.Sites = Items.Num();
		St.Losses = Losses;
		St.Told = Told;
		St.Pruned = Pruned;
		St.Rescued = Taken;
		for (const FSite& S : Items)
		{
			St.SitesHere += S.System == Sys ? 1 : 0;
			St.Pieces += S.Pieces.Num();
			St.Chunks += S.Field.Count;
			St.Pods += S.Pods.Num();
			for (const FPodRec& P : S.Pods)
			{
				St.PodsAdrift += Alive(P, Now) ? 1 : 0;
				St.PodsRecovered += P.State == 1 ? 1 : 0;
				St.PodsLost += (P.State == 2 || (P.State == 0 && Now >= P.T0 + P.AirS)) ? 1 : 0;
				St.Survivors += Alive(P, Now) ? P.Survivors : 0;
			}
		}
		return St;
	}

	void FWrecks::Prune(double Now)
	{
		// what has drifted out of any system's reach (a million kilometres from the Gate: nothing will ever come near it) and is old: gone
		for (int32 i = Items.Num() - 1; i >= 0; --i)
		{
			if (Now - Items[i].DiedAt > 6.0 * 3600.0 && Middle(Items[i], Now).Size() > 1.0e6)
			{
				JsonCache.Remove(Items[i].Id);
				Items.RemoveAt(i);
				++Pruned;
			}
		}
		// and when there are too many, the oldest of those with no pod still calling; failing that the oldest
		while (Items.Num() >= MaxSites)
		{
			int32 Pick = INDEX_NONE;
			double Best = 1e300;
			for (int32 i = 0; i < Items.Num(); ++i)
			{
				bool bLiving = false;
				for (const FPodRec& P : Items[i].Pods)
				{
					bLiving |= Alive(P, Now);
				}
				const double Score = Items[i].DiedAt + (bLiving ? 1.0e9 : 0.0);
				if (Score < Best)
				{
					Best = Score;
					Pick = i;
				}
			}
			if (Pick == INDEX_NONE)
			{
				break;
			}
			JsonCache.Remove(Items[Pick].Id);
			Items.RemoveAt(Pick);
			++Pruned;
		}
	}

	// ------------------------------------------------------------------------------------------------------------------ the file
	TSharedRef<FJsonObject> FWrecks::SiteJson(FSite& S, bool bRooms) const
	{
		TSharedRef<FJsonObject> J = MakeShared<FJsonObject>();
		J->SetNumberField(TEXT("id"), S.Id);
		J->SetStringField(TEXT("sys"), S.System);
		J->SetNumberField(TEXT("ship"), S.ShipId);
		J->SetStringField(TEXT("name"), S.Name);
		J->SetStringField(TEXT("cls"), S.Class);
		J->SetStringField(TEXT("key"), S.ClassKey.ToString());
		J->SetStringField(TEXT("contact"), S.Contact);
		J->SetStringField(TEXT("known"), S.KnownAs);
		J->SetStringField(TEXT("mesh"), S.HullMesh);
		J->SetNumberField(TEXT("fac"), S.Faction);
		J->SetStringField(TEXT("how"), HowLostName(S.How));
		J->SetNumberField(TEXT("sec"), S.Section);
		J->SetNumberField(TEXT("died"), FMath::RoundToDouble(S.DiedAt / KTime));
		J->SetNumberField(TEXT("r"), FMath::RoundToDouble(S.Radius / KLen));
		{
			TArray<TSharedPtr<FJsonValue>> A;
			WkPutVec(A, S.Pos0, KPos);
			WkPutVec(A, S.Vel, KVel);
			J->SetArrayField(TEXT("pv"), A);
		}
		{
			const FAboard& Ab = S.Aboard;
			TSharedRef<FJsonObject> O = MakeShared<FJsonObject>();
			O->SetNumberField(TEXT("n"), Ab.Complement);
			O->SetNumberField(TEXT("alive"), Ab.Alive);
			O->SetNumberField(TEXT("killed"), Ab.Killed);
			O->SetNumberField(TEXT("lost"), Ab.Lost);
			O->SetNumberField(TEXT("escaped"), Ab.Escaped);
			O->SetBoolField(TEXT("inside"), Ab.bInside);
			if (bRooms && Ab.Rooms.Num())
			{
				TArray<TSharedPtr<FJsonValue>> Rooms;
				for (const FAboardRoom& R : Ab.Rooms)
				{
					TArray<TSharedPtr<FJsonValue>> A;
					A.Add(MakeShared<FJsonValueNumber>(R.Comp));
					for (const float V : {R.Air, R.Hole, R.Fire, R.Smoke, R.Heat, R.Power, R.Wreck})
					{
						A.Add(MakeShared<FJsonValueNumber>(FMath::RoundToInt(V * 100.f)));
					}
					A.Add(MakeShared<FJsonValueNumber>((R.bGutted ? 1 : 0) | (R.bLocked ? 2 : 0)));
					Rooms.Add(MakeShared<FJsonValueArray>(A));
				}
				O->SetArrayField(TEXT("rooms"), Rooms);
			}
			if (bRooms && Ab.SealedDoors.Num())
			{
				TArray<TSharedPtr<FJsonValue>> D;
				for (const FString& Id : Ab.SealedDoors)
				{
					D.Add(MakeShared<FJsonValueString>(Id));
				}
				O->SetArrayField(TEXT("doors"), D);
			}
			J->SetObjectField(TEXT("ab"), O);
		}
		{
			TArray<TSharedPtr<FJsonValue>> Pcs;
			for (const FPieceRec& P : S.Pieces)
			{
				TArray<TSharedPtr<FJsonValue>> A;
				WkPut(A, P.Section, 1.0);
				WkPut(A, P.T0, KTime);
				WkPutVec(A, P.Pos0, KPos);
				WkPutVec(A, P.Vel, KVel);
				WkPutQuat(A, P.Att0);
				WkPutVec(A, P.SpinAxis, KQuat);
				WkPut(A, P.SpinRate, KRate);
				WkPut(A, P.Radius, KLen);
				WkPut(A, P.bBurnt ? 1.0 : 0.0, 1.0);
				WkPutVec(A, P.PivotLocal, KLocal);
				Pcs.Add(MakeShared<FJsonValueArray>(A));
			}
			J->SetArrayField(TEXT("pc"), Pcs);
		}
		{
			const FFieldRec& F = S.Field;
			TArray<TSharedPtr<FJsonValue>> A;
			WkPut(A, F.Count, 1.0);
			WkPut(A, (double)F.Seed, 1.0);
			WkPutVec(A, F.Pos0, KPos);
			WkPutVec(A, F.Vel, KVel);
			WkPut(A, F.T0, KTime);
			WkPut(A, F.R0, KLen);
			WkPut(A, F.Slow, KSpeed);
			WkPut(A, F.Fast, KSpeed);
			WkPut(A, F.SizeK, KScale);
			WkPut(A, F.EmberTauS, KLen);
			J->SetArrayField(TEXT("fd"), A);
		}
		{
			TArray<TSharedPtr<FJsonValue>> Pds;
			for (const FPodRec& P : S.Pods)
			{
				TArray<TSharedPtr<FJsonValue>> A;
				WkPut(A, P.T0, KTime);
				WkPut(A, P.BeaconDelayS, KLen);
				WkPut(A, P.Survivors, 1.0);
				WkPut(A, P.AirS, 1.0);
				WkPut(A, P.State, 1.0);
				WkPut(A, P.EndedAt, KTime);
				WkPutVec(A, P.Pos0, KPos);
				WkPutVec(A, P.Vel, KVel);
				A.Add(MakeShared<FJsonValueString>(P.By));                       // (how it lies and turns is not saved: PodPose makes it again from the site's seed)
				Pds.Add(MakeShared<FJsonValueArray>(A));
			}
			J->SetArrayField(TEXT("pd"), Pds);
		}
		J->SetNumberField(TEXT("told"), (S.bToldBeacon ? 1 : 0) | (S.bToldSilent ? 2 : 0) | (S.bToldClose ? 4 : 0));
		return J;
	}

	TSharedRef<FJsonObject> FWrecks::ToJson(double Now)
	{
		TSharedRef<FJsonObject> O = MakeShared<FJsonObject>();
		O->SetNumberField(TEXT("version"), 1);
		O->SetNumberField(TEXT("clock"), FMath::RoundToDouble(Now / KTime));
		O->SetNumberField(TEXT("next"), NextId);
		O->SetNumberField(TEXT("losses"), Losses);
		O->SetNumberField(TEXT("taken"), Taken);
		// the rooms of her plan only for the newest losses (what a boarding of a wreck would use); the rest keep their counts
		TArray<int32> Order;
		for (int32 i = 0; i < Items.Num(); ++i)
		{
			Order.Add(i);
		}
		Order.Sort([this](int32 A, int32 B) { return Items[A].DiedAt > Items[B].DiedAt; });
		TSet<int32> WithRooms;
		for (int32 k = 0; k < FMath::Min(Order.Num(), FWrecks::RoomSites); ++k)
		{
			WithRooms.Add(Items[Order[k]].Id);
		}
		TArray<TSharedPtr<FJsonValue>> Sites;
		for (FSite& S : Items)
		{
			FSaved* Cached = JsonCache.Find(S.Id);
			const bool bRooms = WithRooms.Contains(S.Id);
			if (!Cached || S.bDirty || Cached->bRooms != bRooms)
			{
				FSaved N;
				N.Json = SiteJson(S, bRooms);
				N.bRooms = bRooms;
				Cached = &JsonCache.Add(S.Id, N);
				S.bDirty = false;
			}
			Sites.Add(MakeShared<FJsonValueObject>(Cached->Json));
		}
		O->SetArrayField(TEXT("sites"), Sites);
		return O;
	}

	bool FWrecks::SiteFromJson(const TSharedPtr<FJsonObject>& J, FSite& S)
	{
		if (!J.IsValid())
		{
			return false;
		}
		double D = 0.0;
		FString Str;
		if (!J->TryGetNumberField(TEXT("id"), D))
		{
			return false;
		}
		S.Id = (int32)D;
		J->TryGetStringField(TEXT("sys"), S.System);
		S.System = S.System.ToLower();
		S.ShipId = J->TryGetNumberField(TEXT("ship"), D) ? (int32)D : -1;
		J->TryGetStringField(TEXT("name"), S.Name);
		J->TryGetStringField(TEXT("cls"), S.Class);
		if (J->TryGetStringField(TEXT("key"), Str))
		{
			S.ClassKey = FName(*Str);
		}
		J->TryGetStringField(TEXT("contact"), S.Contact);
		J->TryGetStringField(TEXT("known"), S.KnownAs);
		J->TryGetStringField(TEXT("mesh"), S.HullMesh);
		S.Faction = J->TryGetNumberField(TEXT("fac"), D) ? (uint8)D : 0;
		S.How = J->TryGetStringField(TEXT("how"), Str) ? HowLostFromName(Str) : EHowLost::Destroyed;
		S.Section = J->TryGetNumberField(TEXT("sec"), D) ? (uint8)D : 1;
		S.DiedAt = J->TryGetNumberField(TEXT("died"), D) ? D * KTime : 0.0;
		S.Radius = J->TryGetNumberField(TEXT("r"), D) ? (float)(D * KLen) : 150.f;
		const TArray<TSharedPtr<FJsonValue>>* A = nullptr;
		if (J->TryGetArrayField(TEXT("pv"), A))
		{
			S.Pos0 = WkVec(*A, 0, KPos);
			S.Vel = WkVec(*A, 3, KVel);
		}
		const TSharedPtr<FJsonObject>* O = nullptr;
		if (J->TryGetObjectField(TEXT("ab"), O))
		{
			FAboard& Ab = S.Aboard;
			Ab.Complement = (*O)->TryGetNumberField(TEXT("n"), D) ? (int32)D : 0;
			Ab.Alive = (*O)->TryGetNumberField(TEXT("alive"), D) ? (int32)D : 0;
			Ab.Killed = (*O)->TryGetNumberField(TEXT("killed"), D) ? (int32)D : 0;
			Ab.Lost = (*O)->TryGetNumberField(TEXT("lost"), D) ? (int32)D : 0;
			Ab.Escaped = (*O)->TryGetNumberField(TEXT("escaped"), D) ? (int32)D : 0;
			(*O)->TryGetBoolField(TEXT("inside"), Ab.bInside);
			const TArray<TSharedPtr<FJsonValue>>* Rooms = nullptr;
			if ((*O)->TryGetArrayField(TEXT("rooms"), Rooms))
			{
				for (const TSharedPtr<FJsonValue>& V : *Rooms)
				{
					const TArray<TSharedPtr<FJsonValue>>* R = nullptr;
					if (V.IsValid() && V->TryGetArray(R) && R->Num() >= 9)
					{
						FAboardRoom Room;
						Room.Comp = (int32)(*R)[0]->AsNumber();
						Room.Air = (float)(*R)[1]->AsNumber() * 0.01f;
						Room.Hole = (float)(*R)[2]->AsNumber() * 0.01f;
						Room.Fire = (float)(*R)[3]->AsNumber() * 0.01f;
						Room.Smoke = (float)(*R)[4]->AsNumber() * 0.01f;
						Room.Heat = (float)(*R)[5]->AsNumber() * 0.01f;
						Room.Power = (float)(*R)[6]->AsNumber() * 0.01f;
						Room.Wreck = (float)(*R)[7]->AsNumber() * 0.01f;
						const int32 Fl = (int32)(*R)[8]->AsNumber();
						Room.bGutted = (Fl & 1) != 0;
						Room.bLocked = (Fl & 2) != 0;
						Ab.Rooms.Add(Room);
					}
				}
			}
			const TArray<TSharedPtr<FJsonValue>>* Doors = nullptr;
			if ((*O)->TryGetArrayField(TEXT("doors"), Doors))
			{
				for (const TSharedPtr<FJsonValue>& V : *Doors)
				{
					Ab.SealedDoors.Add(V->AsString());
				}
			}
		}
		const TArray<TSharedPtr<FJsonValue>>* Pcs = nullptr;
		if (J->TryGetArrayField(TEXT("pc"), Pcs))
		{
			for (const TSharedPtr<FJsonValue>& V : *Pcs)
			{
				const TArray<TSharedPtr<FJsonValue>>* P = nullptr;
				if (V.IsValid() && V->TryGetArray(P) && P->Num() >= 21)
				{
					FPieceRec R;
					R.Section = (uint8)(*P)[0]->AsNumber();
					R.T0 = WkGet(*P, 1, KTime);
					R.Pos0 = WkVec(*P, 2, KPos);
					R.Vel = WkVec(*P, 5, KVel);
					R.Att0 = WkQuat(*P, 8);
					R.SpinAxis = WkVec(*P, 12, KQuat).GetSafeNormal();
					R.SpinRate = (float)WkGet(*P, 15, KRate);
					R.Radius = (float)WkGet(*P, 16, KLen);
					R.bBurnt = (*P)[17]->AsNumber() > 0.5;
					R.PivotLocal = WkVec(*P, 18, KLocal);
					S.Pieces.Add(R);
				}
			}
		}
		if (J->TryGetArrayField(TEXT("fd"), A) && A->Num() >= 14)
		{
			FFieldRec& F = S.Field;
			F.Count = FMath::Clamp((int32)(*A)[0]->AsNumber(), 0, MaxChunks);
			F.Seed = (uint32)(*A)[1]->AsNumber();
			F.Pos0 = WkVec(*A, 2, KPos);
			F.Vel = WkVec(*A, 5, KVel);
			F.T0 = WkGet(*A, 8, KTime);
			F.R0 = (float)WkGet(*A, 9, KLen);
			F.Slow = (float)WkGet(*A, 10, KSpeed);
			F.Fast = (float)WkGet(*A, 11, KSpeed);
			F.SizeK = (float)WkGet(*A, 12, KScale);
			F.EmberTauS = (float)WkGet(*A, 13, KLen);
		}
		const TArray<TSharedPtr<FJsonValue>>* Pds = nullptr;
		if (J->TryGetArrayField(TEXT("pd"), Pds))
		{
			for (const TSharedPtr<FJsonValue>& V : *Pds)
			{
				const TArray<TSharedPtr<FJsonValue>>* P = nullptr;
				if (V.IsValid() && V->TryGetArray(P) && P->Num() >= 13 && S.Pods.Num() < MaxPods)
				{
					FPodRec R;
					R.T0 = WkGet(*P, 0, KTime);
					R.BeaconDelayS = (float)WkGet(*P, 1, KLen);
					R.Survivors = (int32)(*P)[2]->AsNumber();
					R.AirS = (float)(*P)[3]->AsNumber();
					R.State = (uint8)(*P)[4]->AsNumber();
					R.EndedAt = WkGet(*P, 5, KTime);
					R.Pos0 = WkVec(*P, 6, KPos);
					R.Vel = WkVec(*P, 9, KVel);
					R.By = (*P)[12]->AsString();
					PodPose(S.Field.Seed, S.Pods.Num(), R.Vel, R.Att0, R.SpinAxis, R.SpinRate);
					S.Pods.Add(R);
				}
			}
		}
		const int32 Told = J->TryGetNumberField(TEXT("told"), D) ? (int32)D : 0;
		S.bToldBeacon = (Told & 1) != 0;
		S.bToldSilent = (Told & 2) != 0;
		S.bToldClose = (Told & 4) != 0;
		return true;
	}

	bool FWrecks::FromJson(const TSharedPtr<FJsonObject>& J, double& OutClock)
	{
		if (!J.IsValid())
		{
			return false;
		}
		double V = 0.0;
		const TArray<TSharedPtr<FJsonValue>>* Sites = nullptr;
		if (!J->TryGetNumberField(TEXT("version"), V) || !J->TryGetArrayField(TEXT("sites"), Sites))
		{
			return false;
		}
		Reset();
		OutClock = J->TryGetNumberField(TEXT("clock"), V) ? V * KTime : 0.0;
		for (const TSharedPtr<FJsonValue>& SV : *Sites)
		{
			FSite S;
			if (SV.IsValid() && SiteFromJson(SV->AsObject(), S) && Items.Num() < MaxSites)
			{
				NextId = FMath::Max(NextId, S.Id + 1);
				Items.Add(MoveTemp(S));
			}
		}
		NextId = FMath::Max(NextId, J->TryGetNumberField(TEXT("next"), V) ? (int32)V : 1);
		Losses = J->TryGetNumberField(TEXT("losses"), V) ? (int32)V : Items.Num();
		Taken = J->TryGetNumberField(TEXT("taken"), V) ? (int32)V : 0;
		return true;
	}
}
