// ASTRA — the hulks the Aquila leaves behind: the records, their motion as arithmetic (with the braking of a hulk nobody has in tow), the file, the unit tests. See AstraDerelicts.h and docs/SPAZIO.md §3ter.

#include "AstraDerelicts.h"
#include "ASTRA.h"
#include "Dom/JsonValue.h"
#include "Policies/CondensedJsonPrintPolicy.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"

namespace AstraSpace
{
	namespace
	{
		double GBrakeS = FDerelicts::DefaultBrakeS;
		constexpr double DrTwoPi = 6.283185307179586;

		// whole numbers in units of their own, as the wrecks' file keeps them (a decimal is printed with seventeen digits and does not read back to what it was)
		constexpr double KPos = 0.1, KVel = 1e-4, KQuat = 1e-4, KRate = 1e-6, KTime = 1e-3, KLen = 0.1, KFrac = 1e-3;

		void DrPut(TArray<TSharedPtr<FJsonValue>>& A, double V, double Unit)
		{
			A.Add(MakeShared<FJsonValueNumber>(FMath::RoundToDouble(V / Unit)));
		}

		void DrPutVec(TArray<TSharedPtr<FJsonValue>>& A, const FVector& V, double Unit)
		{
			DrPut(A, V.X, Unit);
			DrPut(A, V.Y, Unit);
			DrPut(A, V.Z, Unit);
		}

		double DrGet(const TArray<TSharedPtr<FJsonValue>>& A, int32 I, double Unit)
		{
			return A.IsValidIndex(I) && A[I].IsValid() ? A[I]->AsNumber() * Unit : 0.0;
		}

		FVector DrVec(const TArray<TSharedPtr<FJsonValue>>& A, int32 I, double Unit)
		{
			return FVector(DrGet(A, I, Unit), DrGet(A, I + 1, Unit), DrGet(A, I + 2, Unit));
		}

		TSharedRef<FJsonObject> HulkJson(const FDerelict& D)
		{
			TSharedRef<FJsonObject> J = MakeShared<FJsonObject>();
			J->SetNumberField(TEXT("id"), D.Id);
			J->SetStringField(TEXT("sys"), D.System);
			J->SetNumberField(TEXT("ship"), D.ShipId);
			J->SetStringField(TEXT("name"), D.Name);
			J->SetStringField(TEXT("cls"), D.Class);
			J->SetStringField(TEXT("key"), D.ClassKey.ToString());
			J->SetStringField(TEXT("contact"), D.Contact);
			J->SetStringField(TEXT("mesh"), D.Mesh);
			J->SetNumberField(TEXT("side"), D.Side);
			J->SetNumberField(TEXT("fl"), (D.bModel ? 1 : 0) | (D.bHostile ? 2 : 0) | (D.bFog ? 4 : 0) | (D.bIdentified ? 8 : 0) | (D.bClassified ? 16 : 0) | (D.bToldBack ? 32 : 0) | (D.bDisabledShip ? 64 : 0));
			J->SetNumberField(TEXT("t0"), FMath::RoundToDouble(D.T0 / KTime));
			J->SetNumberField(TEXT("r"), FMath::RoundToDouble(D.Radius / KLen));
			{
				TArray<TSharedPtr<FJsonValue>> A;
				DrPutVec(A, D.Pos0, KPos);
				DrPutVec(A, D.Vel, KVel);
				DrPut(A, D.Att0.X, KQuat);
				DrPut(A, D.Att0.Y, KQuat);
				DrPut(A, D.Att0.Z, KQuat);
				DrPut(A, D.Att0.W, KQuat);
				DrPutVec(A, D.SpinAxis, KQuat);
				DrPut(A, D.SpinRate, KRate);
				J->SetArrayField(TEXT("pv"), A);
			}
			{
				TArray<TSharedPtr<FJsonValue>> A;
				DrPut(A, D.HullFrac, KFrac);
				for (const float V : D.Structure)
				{
					DrPut(A, V, KFrac);
				}
				for (const float V : D.Sys)
				{
					DrPut(A, V, KFrac);
				}
				for (const float V : D.Plates)
				{
					DrPut(A, V, KFrac);
				}
				DrPut(A, D.Gutted, 1.0);
				DrPut(A, D.Missiles, 1.0);
				DrPut(A, D.Torpedoes, 1.0);
				J->SetArrayField(TEXT("st"), A);
			}
			J->SetObjectField(TEXT("ab"), FWrecks::AboardToJson(D.Aboard, true));
			return J;
		}

		bool HulkFromJson(const TSharedPtr<FJsonObject>& J, FDerelict& D)
		{
			double N = 0.0;
			FString Str;
			if (!J.IsValid() || !J->TryGetNumberField(TEXT("id"), N))
			{
				return false;
			}
			D.Id = (int32)N;
			J->TryGetStringField(TEXT("sys"), D.System);
			D.System = D.System.ToLower();
			D.ShipId = J->TryGetNumberField(TEXT("ship"), N) ? (int32)N : -1;
			J->TryGetStringField(TEXT("name"), D.Name);
			J->TryGetStringField(TEXT("cls"), D.Class);
			if (J->TryGetStringField(TEXT("key"), Str) && !Str.IsEmpty() && Str != TEXT("None"))
			{
				D.ClassKey = FName(*Str);
			}
			J->TryGetStringField(TEXT("contact"), D.Contact);
			J->TryGetStringField(TEXT("mesh"), D.Mesh);
			D.Side = J->TryGetNumberField(TEXT("side"), N) ? (uint8)FMath::Clamp((int32)N, 0, 2) : 2;
			const int32 Fl = J->TryGetNumberField(TEXT("fl"), N) ? (int32)N : 0;
			D.bModel = (Fl & 1) != 0;
			D.bHostile = (Fl & 2) != 0;
			D.bFog = (Fl & 4) != 0;
			D.bIdentified = (Fl & 8) != 0;
			D.bClassified = (Fl & 16) != 0;
			D.bToldBack = (Fl & 32) != 0;
			D.bDisabledShip = (Fl & 64) != 0;
			D.T0 = J->TryGetNumberField(TEXT("t0"), N) ? N * KTime : 0.0;
			D.Radius = J->TryGetNumberField(TEXT("r"), N) ? (float)(N * KLen) : 150.f;
			const TArray<TSharedPtr<FJsonValue>>* A = nullptr;
			if (J->TryGetArrayField(TEXT("pv"), A))
			{
				D.Pos0 = DrVec(*A, 0, KPos);
				D.Vel = DrVec(*A, 3, KVel);
				const FQuat Q(DrGet(*A, 6, KQuat), DrGet(*A, 7, KQuat), DrGet(*A, 8, KQuat), DrGet(*A, 9, KQuat));
				D.Att0 = Q.SizeSquared() > 1e-6 ? Q.GetNormalized() : FQuat::Identity;
				const FVector Ax = DrVec(*A, 10, KQuat);
				D.SpinAxis = Ax.SizeSquared() > 1e-6 ? Ax.GetSafeNormal() : FVector::UpVector;
				D.SpinRate = (float)DrGet(*A, 13, KRate);
			}
			if (J->TryGetArrayField(TEXT("st"), A) && A->Num() >= 31)
			{
				D.HullFrac = (float)DrGet(*A, 0, KFrac);
				for (int32 i = 0; i < 3; ++i)
				{
					D.Structure[i] = (float)DrGet(*A, 1 + i, KFrac);
				}
				for (int32 i = 0; i < 6; ++i)
				{
					D.Sys[i] = (float)DrGet(*A, 4 + i, KFrac);
				}
				for (int32 i = 0; i < 18; ++i)
				{
					D.Plates[i] = (float)DrGet(*A, 10 + i, KFrac);
				}
				D.Gutted = (uint8)FMath::Clamp((int32)DrGet(*A, 28, 1.0), 0, 7);
				D.Missiles = (int32)DrGet(*A, 29, 1.0);
				D.Torpedoes = (int32)DrGet(*A, 30, 1.0);
			}
			const TSharedPtr<FJsonObject>* Ab = nullptr;
			if (J->TryGetObjectField(TEXT("ab"), Ab))
			{
				FWrecks::AboardFromJson(*Ab, D.Aboard);
			}
			return true;
		}
	}

	// ------------------------------------------------------------------------------------------------------------------ motion
	double FDerelicts::BrakeS()
	{
		return GBrakeS;
	}

	void FDerelicts::SetBrakeS(double Seconds)
	{
		GBrakeS = FMath::Clamp(Seconds, 0.0, 86400.0);
	}

	FVector FDerelicts::PosAt(const FDerelict& D, double Now)
	{
		const double T = FMath::Max(0.0, Now - D.T0);
		const double B = GBrakeS;
		return D.Pos0 + D.Vel * (B > 0.01 ? B * (1.0 - FMath::Exp(-T / B)) : T);
	}

	FVector FDerelicts::VelAt(const FDerelict& D, double Now)
	{
		const double T = FMath::Max(0.0, Now - D.T0);
		const double B = GBrakeS;
		return D.Vel * (B > 0.01 ? FMath::Exp(-T / B) : 1.0);
	}

	FQuat FDerelicts::AttAt(const FDerelict& D, double Now)
	{
		const double T = FMath::Max(0.0, Now - D.T0);
		const FVector Axis = D.SpinAxis.SizeSquared() > 1e-6 ? D.SpinAxis.GetSafeNormal() : FVector::UpVector;
		return (FQuat(Axis, FMath::Fmod((double)D.SpinRate * T, DrTwoPi)) * D.Att0).GetNormalized();
	}

	// ------------------------------------------------------------------------------------------------------------------ the records
	void FDerelicts::Reset()
	{
		Items.Reset();
		NextId = 1;
	}

	const FDerelict& FDerelicts::Add(const FDerelict& In)
	{
		FDerelict D = In;
		D.Id = NextId++;
		D.System = D.System.ToLower();
		while (Items.Num() >= MaxHulks)
		{
			int32 Oldest = 0;
			for (int32 i = 1; i < Items.Num(); ++i)
			{
				Oldest = Items[i].T0 < Items[Oldest].T0 ? i : Oldest;
			}
			Items.RemoveAt(Oldest);
		}
		Items.Add(MoveTemp(D));
		return Items.Last();
	}

	void FDerelicts::Take(const FString& System, TArray<FDerelict>& Out)
	{
		const FString Sys = System.ToLower();
		for (int32 i = 0; i < Items.Num();)
		{
			if (Items[i].System == Sys)
			{
				Out.Add(MoveTemp(Items[i]));
				Items.RemoveAt(i);
			}
			else
			{
				++i;
			}
		}
	}

	void FDerelicts::Replace(const FString& System, const TArray<FDerelict>& Hulks)
	{
		TArray<FDerelict> Old;
		Take(System, Old);
		for (const FDerelict& D : Hulks)
		{
			FDerelict N = D;
			N.System = System;
			Add(N);
		}
	}

	int32 FDerelicts::CountOf(const FString& System) const
	{
		const FString Sys = System.ToLower();
		int32 N = 0;
		for (const FDerelict& D : Items)
		{
			N += D.System == Sys ? 1 : 0;
		}
		return N;
	}

	// ------------------------------------------------------------------------------------------------------------------ the file
	TSharedRef<FJsonObject> FDerelicts::ToJson() const
	{
		TSharedRef<FJsonObject> O = MakeShared<FJsonObject>();
		O->SetNumberField(TEXT("version"), 1);
		O->SetNumberField(TEXT("next"), NextId);
		TArray<TSharedPtr<FJsonValue>> Hulks;
		for (const FDerelict& D : Items)
		{
			Hulks.Add(MakeShared<FJsonValueObject>(HulkJson(D)));
		}
		O->SetArrayField(TEXT("hulks"), Hulks);
		return O;
	}

	bool FDerelicts::FromJson(const TSharedPtr<FJsonObject>& J)
	{
		double V = 0.0;
		const TArray<TSharedPtr<FJsonValue>>* Hulks = nullptr;
		if (!J.IsValid() || !J->TryGetNumberField(TEXT("version"), V) || !J->TryGetArrayField(TEXT("hulks"), Hulks))
		{
			return false;
		}
		Reset();
		for (const TSharedPtr<FJsonValue>& HV : *Hulks)
		{
			FDerelict D;
			if (HV.IsValid() && HulkFromJson(HV->AsObject(), D) && Items.Num() < MaxHulks)
			{
				NextId = FMath::Max(NextId, D.Id + 1);
				Items.Add(MoveTemp(D));
			}
		}
		NextId = FMath::Max(NextId, J->TryGetNumberField(TEXT("next"), V) ? (int32)V : 1);
		return true;
	}

	// ------------------------------------------------------------------------------------------------------------------ the tests
	bool RunDerelictTests(TArray<FString>& Fails, TArray<FString>& Notes)
	{
		auto Expect = [&Fails](bool bOk, const FString& What) { if (!bOk) { Fails.Add(What); } };
		const double Saved = FDerelicts::BrakeS();
		FRandomStream Rng(17);
		const auto Make = [&Rng](int32 K, const TCHAR* System, double T0) -> FDerelict
		{
			FDerelict D;
			D.System = System;
			D.ShipId = 100 + K;
			D.Name = FString::Printf(TEXT("KMS Hulk %d"), K);
			D.Class = TEXT("Kharon Mandate frigate, Lethe class");
			D.Contact = FString::Printf(TEXT("T-%d"), 20 + K);
			D.Mesh = TEXT("SM_SHIP_MANDATE_Lethe");
			D.ClassKey = FName(TEXT("lethe"));
			D.Side = (uint8)(K % 3);
			D.bModel = (K % 4) != 3;
			D.bHostile = D.Side == 1;
			D.bFog = D.Side == 1;
			D.bIdentified = (K % 5) != 0;
			D.bClassified = true;
			D.bToldBack = (K % 6) == 0;
			D.bDisabledShip = (K % 4) != 3;
			D.T0 = T0;
			D.Pos0 = Rng.GetUnitVector() * Rng.FRandRange(1000.f, 90000.f);
			D.Vel = Rng.GetUnitVector() * Rng.FRandRange(0.f, 420.f);
			D.Att0 = FQuat(Rng.GetUnitVector(), Rng.FRandRange(0.f, 6.f));
			D.SpinAxis = Rng.GetUnitVector();
			D.SpinRate = FMath::DegreesToRadians(Rng.FRandRange(0.3f, 1.0f));
			D.Radius = Rng.FRandRange(60.f, 480.f);
			D.HullFrac = Rng.FRand();
			for (float& S : D.Structure) { S = Rng.FRand(); }
			for (float& P : D.Plates) { P = Rng.FRand(); }
			for (float& S : D.Sys) { S = Rng.FRand(); }
			D.Sys[4] = 0.f;
			D.Gutted = (uint8)Rng.RandRange(0, 7);
			D.Missiles = Rng.RandRange(0, 32);
			D.Torpedoes = Rng.RandRange(0, 4);
			D.Aboard.Complement = 62;
			D.Aboard.Alive = 41;
			D.Aboard.Killed = 21;
			D.Aboard.bInside = true;
			for (int32 r = 0; r < 4; ++r)
			{
				FAboardRoom R;
				R.Comp = r * 7;
				R.Air = Rng.FRand();
				R.Fire = r == 2 ? 0.4f : 0.f;
				R.bGutted = r == 1;
				R.bLocked = r == 3;
				D.Aboard.Rooms.Add(R);
			}
			D.Aboard.SealedDoors = {TEXT("door_a"), TEXT("door_b")};
			return D;
		};

		// ---- the arithmetic: her velocity falls away as e^(-t/B) and her place with it; she comes to rest at most her way times B from where she was left; BrakeS 0 is the war's drift
		{
			FDerelicts::SetBrakeS(150.0);
			FDerelict D = Make(1, TEXT("aurelia"), 100.0);
			D.Vel = FVector(300.0, 0.0, 0.0);
			D.Pos0 = FVector(1000.0, 2000.0, 3000.0);
			Expect((FDerelicts::PosAt(D, 100.0) - D.Pos0).Size() < 1e-9 && (FDerelicts::VelAt(D, 100.0) - D.Vel).Size() < 1e-9, TEXT("a hulk is not where and as she was recorded at the moment of the record"));
			Expect((FDerelicts::PosAt(D, 1.0e9) - (D.Pos0 + D.Vel * 150.0)).Size() < 1e-6, TEXT("a hulk does not come to rest at her way times the braking time"));
			Expect((FDerelicts::VelAt(D, 250.0) - D.Vel * FMath::Exp(-1.0)).Size() < 1e-9, TEXT("her velocity after one braking time is not 1/e"));
			double MaxErr = 0.0, Last = -1.0;
			bool bMonotone = true;
			for (double T = 101.0; T < 2000.0; T += 7.3)
			{
				const FVector Num = (FDerelicts::PosAt(D, T + 0.01) - FDerelicts::PosAt(D, T - 0.01)) / 0.02;
				MaxErr = FMath::Max(MaxErr, (Num - FDerelicts::VelAt(D, T)).Size());
				const double Run = (FDerelicts::PosAt(D, T) - D.Pos0).Size();
				bMonotone &= Run >= Last - 1e-9;
				Last = Run;
			}
			Expect(MaxErr < 0.05, FString::Printf(TEXT("her velocity is not the derivative of her place (%.3f m/s off)"), MaxErr));
			Expect(bMonotone, TEXT("a hulk went back on her way"));
			Expect(FDerelicts::PosAt(D, 50.0) == D.Pos0, TEXT("a hulk is somewhere before she was recorded"));
			// turning: the angle she has turned is her rate times the time (a spin kept for hours loses no precision), her attitude stays a unit
			D.SpinRate = FMath::DegreesToRadians(0.5f);
			const FQuat A0 = FDerelicts::AttAt(D, 100.0), A1 = FDerelicts::AttAt(D, 100.0 + 90.0);
			Expect(FMath::Abs(A0.AngularDistance(A1) - FMath::DegreesToRadians(45.f)) < 1e-4, FString::Printf(TEXT("she turned %.3f deg in 90 s at 0.5 deg/s"), FMath::RadiansToDegrees(A0.AngularDistance(A1))));
			Expect(FMath::Abs(FDerelicts::AttAt(D, 100.0 + 4.0 * 86400.0).Size() - 1.0) < 1e-9, TEXT("her attitude after four days is not a unit"));
			FDerelicts::SetBrakeS(0.0);
			Expect((FDerelicts::PosAt(D, 200.0) - (D.Pos0 + D.Vel * 100.0)).Size() < 1e-9 && (FDerelicts::VelAt(D, 5000.0) - D.Vel).Size() < 1e-9, TEXT("BrakeS 0 does not leave her the war's drift"));
			Notes.Add(FString::Printf(TEXT("a hulk left at 300 m/s rests %.0f km from where she was left (braking %.0f s); after ten minutes she is %.0f km out"), 300.0 * 150.0 / 1000.0, 150.0,
			                          (300.0 * 150.0 * (1.0 - FMath::Exp(-600.0 / 150.0))) / 1000.0));
		}

		// ---- the records: ids, the limit, taking a system's, replacing it
		FDerelicts::SetBrakeS(150.0);
		{
			FDerelicts R;
			for (int32 i = 0; i < 40; ++i)
			{
				R.Add(Make(i, i % 3 == 0 ? TEXT("Aurelia") : (i % 3 == 1 ? TEXT("THULE") : TEXT("Vesper")), 1000.0 + i));
			}
			Expect(R.All().Num() == FDerelicts::MaxHulks, FString::Printf(TEXT("%d records kept, the most is %d"), R.All().Num(), FDerelicts::MaxHulks));
			TSet<int32> Ids;
			bool bNewest = true;
			for (const FDerelict& D : R.All())
			{
				Ids.Add(D.Id);
				bNewest &= D.T0 >= 1000.0 + (40 - FDerelicts::MaxHulks) - 1e-9;       // (the oldest went)
			}
			Expect(Ids.Num() == R.All().Num(), TEXT("two records have the same id"));
			Expect(bNewest, TEXT("a record that is not among the newest was kept when the limit was reached"));
			const int32 InThule = R.CountOf(TEXT("thule"));
			Expect(InThule > 0 && R.CountOf(TEXT("THULE")) == InThule, TEXT("a system is told apart by its case"));
			TArray<FDerelict> Taken;
			R.Take(TEXT("Thule"), Taken);
			Expect(Taken.Num() == InThule && R.CountOf(TEXT("thule")) == 0 && R.All().Num() == FDerelicts::MaxHulks - InThule, TEXT("taking a system's records does not take exactly them"));
			TArray<FDerelict> Again;
			R.Take(TEXT("Thule"), Again);
			Expect(Again.Num() == 0, TEXT("a record was taken twice"));
			const int32 Before = R.CountOf(TEXT("aurelia"));
			TArray<FDerelict> Now;
			Now.Add(Make(90, TEXT("x"), 5000.0));
			Now.Add(Make(91, TEXT("x"), 5000.0));
			R.Replace(TEXT("Aurelia"), Now);
			Expect(R.CountOf(TEXT("aurelia")) == 2 && Before != 2, FString::Printf(TEXT("replacing a system's records leaves %d of them (there were %d)"), R.CountOf(TEXT("aurelia")), Before));
			Expect(R.CountOf(TEXT("vesper")) > 0, TEXT("replacing a system's records touched another's"));
		}

		// ---- the file: every number comes back as it was within the file's own unit, and a second writing is the first
		{
			FDerelicts R;
			for (int32 i = 0; i < 12; ++i)
			{
				R.Add(Make(i, i % 2 ? TEXT("aurelia") : TEXT("thule"), 500.0 * i + 0.4375));
			}
			const auto Text = [](const FDerelicts& X)
			{
				FString S;
				const TSharedRef<TJsonWriter<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>> W = TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&S);
				FJsonSerializer::Serialize(X.ToJson(), W);
				return S;
			};
			const FString A = Text(R);
			TSharedPtr<FJsonObject> Back;
			FDerelicts R2;
			Expect(FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(A), Back) && R2.FromJson(Back), TEXT("the hulks' file does not read back"));
			Expect(R2.All().Num() == R.All().Num(), FString::Printf(TEXT("%d hulks came back of %d"), R2.All().Num(), R.All().Num()));
			double Worst = 0.0, WorstV = 0.0, WorstQ = 0.0, WorstF = 0.0;
			for (int32 i = 0; i < FMath::Min(R.All().Num(), R2.All().Num()); ++i)
			{
				const FDerelict& X = R.All()[i];
				const FDerelict& Y = R2.All()[i];
				Worst = FMath::Max(Worst, (double)FVector::Dist(X.Pos0, Y.Pos0));
				WorstV = FMath::Max(WorstV, (double)FVector::Dist(X.Vel, Y.Vel));
				WorstQ = FMath::Max(WorstQ, (double)X.Att0.AngularDistance(Y.Att0));
				for (int32 k = 0; k < 18; ++k) { WorstF = FMath::Max(WorstF, (double)FMath::Abs(X.Plates[k] - Y.Plates[k])); }
				for (int32 k = 0; k < 3; ++k) { WorstF = FMath::Max(WorstF, (double)FMath::Abs(X.Structure[k] - Y.Structure[k])); }
				for (int32 k = 0; k < 6; ++k) { WorstF = FMath::Max(WorstF, (double)FMath::Abs(X.Sys[k] - Y.Sys[k])); }
				Expect(X.Id == Y.Id && X.System == Y.System && X.ShipId == Y.ShipId && X.Name == Y.Name && X.Class == Y.Class && X.Contact == Y.Contact && X.Mesh == Y.Mesh && X.ClassKey == Y.ClassKey && X.Side == Y.Side,
				       FString::Printf(TEXT("hulk %d: who she was came back as someone else"), X.Id));
				Expect(X.bModel == Y.bModel && X.bHostile == Y.bHostile && X.bFog == Y.bFog && X.bIdentified == Y.bIdentified && X.bClassified == Y.bClassified && X.bToldBack == Y.bToldBack && X.bDisabledShip == Y.bDisabledShip, FString::Printf(TEXT("hulk %d: her flags came back different"), X.Id));
				Expect(FMath::Abs(X.T0 - Y.T0) < 0.0006 && FMath::Abs(X.Radius - Y.Radius) < 0.06f && X.Gutted == Y.Gutted && X.Missiles == Y.Missiles && X.Torpedoes == Y.Torpedoes && FMath::Abs(X.SpinRate - Y.SpinRate) < 1e-6f && FMath::Abs(X.HullFrac - Y.HullFrac) < 0.0006f,
				       FString::Printf(TEXT("hulk %d: her numbers came back different"), X.Id));
				Expect(X.Aboard.Complement == Y.Aboard.Complement && X.Aboard.Alive == Y.Aboard.Alive && X.Aboard.Killed == Y.Aboard.Killed && X.Aboard.bInside == Y.Aboard.bInside && X.Aboard.Rooms.Num() == Y.Aboard.Rooms.Num() && X.Aboard.SealedDoors == Y.Aboard.SealedDoors,
				       FString::Printf(TEXT("hulk %d: what was left aboard came back different"), X.Id));
				for (int32 k = 0; k < FMath::Min(X.Aboard.Rooms.Num(), Y.Aboard.Rooms.Num()); ++k)
				{
					Expect(X.Aboard.Rooms[k].Comp == Y.Aboard.Rooms[k].Comp && X.Aboard.Rooms[k].bGutted == Y.Aboard.Rooms[k].bGutted && X.Aboard.Rooms[k].bLocked == Y.Aboard.Rooms[k].bLocked && FMath::Abs(X.Aboard.Rooms[k].Air - Y.Aboard.Rooms[k].Air) < 0.006f,
					       FString::Printf(TEXT("hulk %d: room %d came back different"), X.Id, k));
				}
			}
			Expect(Worst < 0.09 && WorstV < 1.0e-4 && WorstQ < 1.0e-3 && WorstF < 0.0006, FString::Printf(TEXT("the file is not as exact as its units: %.3f m, %.5f m/s, %.5f rad, %.5f"), Worst, WorstV, WorstQ, WorstF));
			TSharedPtr<FJsonObject> Empty = MakeShared<FJsonObject>();
			FDerelicts R3;
			Expect(!R3.FromJson(nullptr) && !R3.FromJson(Empty), TEXT("something that is no record of hulks was read as one"));
			Notes.Add(FString::Printf(TEXT("hulks: %d records = %.1f KB (%.0f bytes each, her rooms included); the file's units hold to %.3f m, %.5f m/s"), R.All().Num(), A.Len() / 1024.0, (double)A.Len() / FMath::Max(1, R.All().Num()), Worst, WorstV));
		}
		FDerelicts::SetBrakeS(Saved);
		return Fails.Num() == 0;
	}
}
