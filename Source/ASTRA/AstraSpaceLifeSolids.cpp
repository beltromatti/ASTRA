// ASTRA — the solid parts of the places' hulls: the data (data/space/solids.json), the lookups, the unit tests, and the hit test the battle's PilotCollision calls for the Captain's Falcon.
// What it is for and how the boxes are made: AstraSpaceLifeSolids.h.

#include "AstraSpaceLifeSolids.h"
#include "AstraSpaceLife.h"
#include "AstraBattleSubsystem.h"
#include "ASTRA.h"
#include "DrawDebugHelpers.h"
#include "Dom/JsonObject.h"
#include "Engine/World.h"
#include "HAL/PlatformTime.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

namespace AstraSpace
{
	// ------------------------------------------------------------------------------------------------------------------ lookups
	bool FSolids::Inside(const FVector& P) const
	{
		const double InvCell = 1.0 / (double)Cell;
		const int32 X = FMath::FloorToInt((P.X - Origin.X) * InvCell);
		const int32 Y = FMath::FloorToInt((P.Y - Origin.Y) * InvCell);
		const int32 Z = FMath::FloorToInt((P.Z - Origin.Z) * InvCell);
		if (X < 0 || Y < 0 || Z < 0 || X >= NX || Y >= NY || Z >= NZ)
		{
			return false;
		}
		return Bits[(X * NY + Y) * NZ + Z];
	}

	bool FSolids::Crosses(const FVector& A, const FVector& B) const
	{
		const double L = FVector::Dist(A, B);
		const int32 N = FMath::Clamp(FMath::CeilToInt(L / (0.5 * (double)Cell)), 1, 4000);
		for (int32 i = 0; i <= N; ++i)
		{
			if (Inside(FMath::Lerp(A, B, (double)i / (double)N)))
			{
				return true;
			}
		}
		return false;
	}

	double FSolids::FirstHit(const FVector& A, const FVector& B) const
	{
		const FVector D = B - A;
		const double L = D.Size();
		if (L < 1.0e-6)
		{
			return Inside(A) ? 0.0 : -1.0;
		}
		// the part of the path inside the extent of the boxes (a cell of margin): nothing outside it is solid, so nothing outside it is sampled
		double T0 = 0.0, T1 = 1.0;
		for (int32 k = 0; k < 3; ++k)
		{
			const double Lo = (double)Min[k] - Cell, Hi = (double)Max[k] + Cell;
			if (FMath::Abs(D[k]) < 1.0e-9)
			{
				if (A[k] < Lo || A[k] > Hi)
				{
					return -1.0;
				}
				continue;
			}
			double Ta = (Lo - A[k]) / D[k], Tb = (Hi - A[k]) / D[k];
			if (Ta > Tb)
			{
				Swap(Ta, Tb);
			}
			T0 = FMath::Max(T0, Ta);
			T1 = FMath::Min(T1, Tb);
			if (T0 > T1)
			{
				return -1.0;
			}
		}
		const int32 N = FMath::Clamp(FMath::CeilToInt((T1 - T0) * L / (0.5 * (double)Cell)), 1, 8000);
		for (int32 i = 0; i <= N; ++i)
		{
			const double T = T0 + (T1 - T0) * (double)i / (double)N;
			if (Inside(A + D * T))
			{
				return T;
			}
		}
		return -1.0;
	}

	double FSolids::ShellDistance(const FVector& P, double MaxM) const
	{
		if (Inside(P))
		{
			return 0.0;
		}
		for (int32 k = 0; k < 3; ++k)
		{
			if (P[k] < (double)Min[k] - MaxM || P[k] > (double)Max[k] + MaxM)
			{
				return -1.0;                                      // (farther from the boxes' extent than we look)
			}
		}
		static const FVector Dirs[14] =
		{
			FVector(1, 0, 0), FVector(-1, 0, 0), FVector(0, 1, 0), FVector(0, -1, 0), FVector(0, 0, 1), FVector(0, 0, -1),
			FVector(1, 1, 1).GetSafeNormal(), FVector(1, 1, -1).GetSafeNormal(), FVector(1, -1, 1).GetSafeNormal(), FVector(1, -1, -1).GetSafeNormal(),
			FVector(-1, 1, 1).GetSafeNormal(), FVector(-1, 1, -1).GetSafeNormal(), FVector(-1, -1, 1).GetSafeNormal(), FVector(-1, -1, -1).GetSafeNormal()
		};
		const double Step = FMath::Max(0.5 * (double)Cell, 1.5);
		double Best = -1.0;
		for (const FVector& Dir : Dirs)
		{
			const double Reach = Best > 0.0 ? Best : MaxM;       // (no use looking past what has been found)
			for (double T = Step; T <= Reach; T += Step)
			{
				if (Inside(P + Dir * T))
				{
					Best = Best < 0.0 ? T : FMath::Min(Best, T);
					break;
				}
			}
		}
		return Best;
	}

	// ------------------------------------------------------------------------------------------------------------------ the data
	bool FSolidData::Parse(const FString& Json, FString& OutError)
	{
		Meshes.Reset();
		TSharedPtr<FJsonObject> Root;
		if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Json), Root) || !Root.IsValid())
		{
			OutError = TEXT("solids.json does not parse");
			return false;
		}
		const TSharedPtr<FJsonObject>* Ms = nullptr;
		if (!Root->TryGetObjectField(TEXT("meshes"), Ms))
		{
			OutError = TEXT("solids.json has no meshes");
			return false;
		}
		for (const TPair<FString, TSharedPtr<FJsonValue>>& KV : (*Ms)->Values)
		{
			const TSharedPtr<FJsonObject> O = KV.Value->AsObject();
			const TArray<TSharedPtr<FJsonValue>>* Bx = nullptr;
			const TArray<TSharedPtr<FJsonValue>>* Og = nullptr;
			if (!O.IsValid() || !O->TryGetArrayField(TEXT("boxes"), Bx) || !O->TryGetArrayField(TEXT("origin"), Og) || Og->Num() < 3)
			{
				continue;
			}
			FSolids S;
			S.Cell = (float)O->GetNumberField(TEXT("cell"));
			S.Origin = FVector((*Og)[0]->AsNumber(), (*Og)[1]->AsNumber(), (*Og)[2]->AsNumber());
			if (S.Cell < 0.5f)
			{
				continue;
			}
			struct FBoxC { int32 X, Y, Z, DX, DY, DZ; };
			TArray<FBoxC> Boxes;
			Boxes.Reserve(Bx->Num());
			int32 MaxX = 0, MaxY = 0, MaxZ = 0;
			for (const TSharedPtr<FJsonValue>& V : *Bx)
			{
				const TArray<TSharedPtr<FJsonValue>>& A = V->AsArray();
				if (A.Num() < 6)
				{
					continue;
				}
				FBoxC B{(int32)A[0]->AsNumber(), (int32)A[1]->AsNumber(), (int32)A[2]->AsNumber(), (int32)A[3]->AsNumber(), (int32)A[4]->AsNumber(), (int32)A[5]->AsNumber()};
				if (B.X < 0 || B.Y < 0 || B.Z < 0 || B.DX < 1 || B.DY < 1 || B.DZ < 1)
				{
					continue;
				}
				MaxX = FMath::Max(MaxX, B.X + B.DX);
				MaxY = FMath::Max(MaxY, B.Y + B.DY);
				MaxZ = FMath::Max(MaxZ, B.Z + B.DZ);
				Boxes.Add(B);
			}
			if (Boxes.Num() == 0 || (int64)MaxX * MaxY * MaxZ > 40'000'000)
			{
				continue;                                  // (nothing, or a grid that is no place's: 40 million cells is 5 MB)
			}
			S.NX = MaxX;
			S.NY = MaxY;
			S.NZ = MaxZ;
			S.Bits.Init(false, MaxX * MaxY * MaxZ);
			FIntVector Lo(MAX_int32), Hi(0);
			for (const FBoxC& B : Boxes)
			{
				for (int32 X = B.X; X < B.X + B.DX; ++X)
				{
					for (int32 Y = B.Y; Y < B.Y + B.DY; ++Y)
					{
						const int32 Row = (X * MaxY + Y) * MaxZ;
						for (int32 Z = B.Z; Z < B.Z + B.DZ; ++Z)
						{
							S.Bits[Row + Z] = true;
						}
					}
				}
				Lo = FIntVector(FMath::Min(Lo.X, B.X), FMath::Min(Lo.Y, B.Y), FMath::Min(Lo.Z, B.Z));
				Hi = FIntVector(FMath::Max(Hi.X, B.X + B.DX), FMath::Max(Hi.Y, B.Y + B.DY), FMath::Max(Hi.Z, B.Z + B.DZ));
			}
			for (int32 i = 0; i < S.Bits.Num(); ++i)
			{
				S.NumCells += S.Bits[i] ? 1 : 0;
			}
			S.NumBoxes = Boxes.Num();
			S.Min = S.Origin + FVector(Lo.X, Lo.Y, Lo.Z) * S.Cell;
			S.Max = S.Origin + FVector(Hi.X, Hi.Y, Hi.Z) * S.Cell;
			Meshes.Add(KV.Key, MoveTemp(S));
		}
		return Meshes.Num() > 0;
	}

	namespace
	{
		FSolidData GSolidData;

		void SoLoad()
		{
			GSolidData = FSolidData();
			const FString A = FPaths::Combine(FPaths::ProjectContentDir(), TEXT("ASTRA/Data/space"));
			const FString B = FPaths::Combine(FPaths::ProjectDir(), TEXT("data/space"));
			const FString* Dir = FPaths::FileExists(A / TEXT("solids.json")) ? &A : (FPaths::FileExists(B / TEXT("solids.json")) ? &B : nullptr);
			if (!Dir)
			{
				UE_LOG(LogASTRA, Warning, TEXT("[Space] data/space/solids.json is missing: the Captain's Falcon flies through the places' hulls as the war's boxes would have it (art/blender/space3_solids.py, then tools/space.py sync)"));
				return;
			}
			FString Text, Error;
			FFileHelper::LoadFileToString(Text, *(*Dir / TEXT("solids.json")));
			if (!GSolidData.Parse(Text, Error))
			{
				UE_LOG(LogASTRA, Warning, TEXT("[Space] %s (%s)"), *Error, **Dir);
				return;
			}
			GSolidData.bLoaded = true;
			GSolidData.Source = *Dir;
			int32 Cells = 0;
			for (const TPair<FString, FSolids>& KV : GSolidData.Meshes)
			{
				Cells += KV.Value.NumCells;
			}
			UE_LOG(LogASTRA, Log, TEXT("[Space] solids from %s: %d meshes, %d solid cells"), **Dir, GSolidData.Meshes.Num(), Cells);
		}
	}

	const FSolidData& SolidData()
	{
		static bool bDone = false;
		if (!bDone)
		{
			bDone = true;
			SoLoad();
		}
		return GSolidData;
	}

	void ReloadSolidData()
	{
		SoLoad();
	}

	// ------------------------------------------------------------------------------------------------------------------ tests
	bool RunSolidsTests(TArray<FString>& Fails, TArray<FString>& Notes)
	{
		auto Expect = [&Fails](bool bOk, const FString& What) { if (!bOk) { Fails.Add(What); } };
		const FSolidData& Data = SolidData();
		Expect(Data.bLoaded, TEXT("data/space/solids.json did not load (art/blender/space3_solids.py, then tools/space.py sync)"));
		if (!Data.bLoaded)
		{
			return false;
		}
		static const TCHAR* const Meshes[] = {TEXT("SM_PLACE_Keeper"), TEXT("SM_PLACE_KeeperRing"), TEXT("SM_PLACE_Arsenal"), TEXT("SM_PART_ArsenalCrane"), TEXT("SM_PLACE_Refinery"), TEXT("SM_PLACE_Mine")};
		FString Sizes;
		for (const TCHAR* Name : Meshes)
		{
			const FSolids* S = Data.Find(Name);
			Expect(S != nullptr, FString::Printf(TEXT("no solids for %s"), Name));
			if (!S)
			{
				continue;
			}
			Expect(S->NumBoxes >= 50 && S->NumBoxes <= 8000, FString::Printf(TEXT("%s has %d boxes"), Name, S->NumBoxes));
			Expect(S->Cell >= 2.9f && S->Cell <= 16.f, FString::Printf(TEXT("%s: a cell of %.1f m"), Name, S->Cell));
			const FVector Ext = S->Max - S->Min;
			const double Fill = (double)S->NumCells * S->Cell * S->Cell * S->Cell / FMath::Max(1.0, Ext.X * Ext.Y * Ext.Z);
			Expect(Fill > 0.0005 && Fill < 0.6, FString::Printf(TEXT("%s: the boxes fill %.4f of their extent"), Name, Fill));
			Sizes += FString::Printf(TEXT("%s %d boxes/%d cells of %.1f m (%.0fx%.0fx%.0f m, %.1f%% solid); "), Name, S->NumBoxes, S->NumCells, S->Cell, Ext.X, Ext.Y, Ext.Z, Fill * 100.0);
		}
		Notes.Add(Sizes);
		// ---- the Keeper's ring: a hub, four spokes on the diagonals, a rim; open between the spokes, and open round it
		if (const FSolids* R = Data.Find(TEXT("SM_PLACE_KeeperRing")))
		{
			const FVector Mid = (R->Min + R->Max) * 0.5;
			const double Rad = FMath::Min(R->Max.Y - R->Min.Y, R->Max.Z - R->Min.Z) * 0.5;
			const auto At = [&](double RFrac, double AngDeg, double X = 0.0) { return FVector(Mid.X + X, Mid.Y + FMath::Cos(FMath::DegreesToRadians(AngDeg)) * RFrac * Rad, Mid.Z + FMath::Sin(FMath::DegreesToRadians(AngDeg)) * RFrac * Rad); };
			Expect(R->Inside(Mid), TEXT("the ring's hub is not solid"));
			Expect(R->Inside(At(0.96, 0.0)) && R->Inside(At(0.96, 90.0)) && R->Inside(At(0.96, 200.0)), TEXT("the ring's rim is not solid"));
			Expect(!R->Inside(At(0.55, 0.0)) && !R->Inside(At(0.55, 90.0)) && !R->Inside(At(0.55, 180.0)) && !R->Inside(At(0.55, 270.0)), TEXT("the ring is solid between its spokes (a Falcon could not fly through)"));
			Expect(R->Inside(At(0.55, 45.0)) && R->Inside(At(0.55, 135.0)) && R->Inside(At(0.55, 225.0)) && R->Inside(At(0.55, 315.0)), TEXT("the ring's spokes are not on the diagonals, or are not solid"));
			Expect(!R->Inside(At(1.3, 0.0)) && !R->Inside(At(0.55, 0.0, 400.0)), TEXT("air round the ring is solid"));
			// a Falcon through the open quarter along the axis is free; through a spoke it is lost; round the outside it is free
			Expect(!R->Crosses(At(0.55, 0.0, -300.0), At(0.55, 0.0, 300.0)), TEXT("a path through the ring's open quarter hits it"));
			Expect(R->Crosses(At(0.55, 45.0, -300.0), At(0.55, 45.0, 300.0)), TEXT("a path through a spoke does not hit it"));
			Expect(!R->Crosses(At(1.3, 0.0, -300.0), At(1.3, 0.0, 300.0)), TEXT("a path outside the ring hits it"));
			// a path that ends a metre short of the rim is free, and one that ends a metre in it is not (the cell's resolution: a few metres)
			const FVector Dir(0.0, 1.0, 0.0);
			const double RimOuter = Mid.Y + Rad;
			Expect(!R->Crosses(FVector(Mid.X, RimOuter + 60.0, Mid.Z), FVector(Mid.X, RimOuter + R->Cell, Mid.Z)), TEXT("a path ending a cell outside the rim hits it"));
			Expect(R->Crosses(FVector(Mid.X, RimOuter + 60.0, Mid.Z), FVector(Mid.X, RimOuter - 2.0 * R->Cell, Mid.Z)), TEXT("a path ending in the rim does not hit it"));
			(void)Dir;
			// the Falcon's cue (AstraSpaceLifeFalcon.cpp): how soon along a path, how near a point. Through a spoke along the axis the first cell is where the ring's thickness begins; through the open quarter, none
			{
				const double Half = 0.5 * (R->Max.X - R->Min.X);
				const double TSpoke = R->FirstHit(At(0.55, 45.0, -300.0), At(0.55, 45.0, 300.0));
				Expect(TSpoke > 0.0 && TSpoke * 600.0 > 300.0 - Half - R->Cell && TSpoke * 600.0 < 300.0 + R->Cell, FString::Printf(TEXT("the first cell of a path through a spoke is %.1f m along it (the ring's thickness begins at %.1f)"), TSpoke * 600.0, 300.0 - Half));
				Expect(R->FirstHit(At(0.55, 0.0, -300.0), At(0.55, 0.0, 300.0)) < 0.0, TEXT("a path through the ring's open quarter has a first cell"));
				Expect(R->FirstHit(At(0.55, 45.0, -300.0), At(0.55, 45.0, -200.0)) < 0.0, TEXT("a path that stops short of the ring has a first cell"));
				Expect(FMath::IsNearlyEqual(R->FirstHit(At(0.55, 45.0, 0.0), At(0.55, 45.0, 100.0)), 0.0), TEXT("a path that begins in a cell has its first one anywhere but at its start"));
				// a point 50 m out from the rim: the nearest cell is 50 m away (a cell more or less); in a cell: 0; at 400 m: none within 250 m
				const double Out50 = R->ShellDistance(FVector(Mid.X, RimOuter + 50.0, Mid.Z), 250.0);
				Expect(Out50 > 50.0 - R->Cell && Out50 < 50.0 + 2.0 * R->Cell, FString::Printf(TEXT("a point 50 m outside the rim reads %.1f m from it"), Out50));
				Expect(R->ShellDistance(Mid, 250.0) == 0.0, TEXT("the hub's point is not in a cell"));
				Expect(R->ShellDistance(FVector(Mid.X, RimOuter + 400.0, Mid.Z), 250.0) < 0.0, TEXT("a point 400 m out finds a cell within 250 m"));
				// never nearer than the truth: a point in the open quarter midway between hub and rim, nothing nearer than the spokes' flanks, whatever the estimate
				const double Mid55 = R->ShellDistance(At(0.55, 0.0), 250.0);
				Expect(Mid55 > 0.0, FString::Printf(TEXT("a point in the open quarter reads %.1f m from a cell"), Mid55));
			}
		}
		// ---- the Arsenal and the rest are mostly air: a place's hull is a small part of its bounding box
		for (const TCHAR* Name : {TEXT("SM_PLACE_Arsenal"), TEXT("SM_PLACE_Keeper"), TEXT("SM_PLACE_Refinery"), TEXT("SM_PLACE_Mine")})
		{
			const FSolids* S = Data.Find(Name);
			if (!S)
			{
				continue;
			}
			FRandomStream Rng(5);
			int32 In = 0;
			const int32 N = 20000;
			for (int32 i = 0; i < N; ++i)
			{
				const FVector P(Rng.FRandRange((float)S->Min.X, (float)S->Max.X), Rng.FRandRange((float)S->Min.Y, (float)S->Max.Y), Rng.FRandRange((float)S->Min.Z, (float)S->Max.Z));
				In += S->Inside(P) ? 1 : 0;
			}
			const double Share = (double)In / N;
			const FVector Ext = S->Max - S->Min;
			const double Fill = (double)S->NumCells * S->Cell * S->Cell * S->Cell / FMath::Max(1.0, Ext.X * Ext.Y * Ext.Z);
			Expect(FMath::Abs(Share - Fill) < 0.02, FString::Printf(TEXT("%s: a random point is solid %.3f of the time, the cells say %.3f"), Name, Share, Fill));
		}
		// ---- the wrecks of the war: the ships' whole hulls and their three pieces, each as long as the war says her hull is (data/war/classes.json: hull_m.x, cuts_x_m), the pieces end to end along her length
		{
			const FString Path = FPaths::ProjectDir() / TEXT("data/war/classes.json");
			FString Text;
			TSharedPtr<FJsonObject> Root;
			const TArray<TSharedPtr<FJsonValue>>* List = nullptr;
			if (FFileHelper::LoadFileToString(Text, *Path) && FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Root) && Root.IsValid() && Root->TryGetArrayField(TEXT("classes"), List))
			{
				int32 Ships = 0, Pieces = 0;
				for (const TSharedPtr<FJsonValue>& V : *List)
				{
					const TSharedPtr<FJsonObject> O = V->AsObject();
					FString Key, Mesh;
					const TSharedPtr<FJsonObject>* Hull = nullptr;
					const TArray<TSharedPtr<FJsonValue>>* X = nullptr;
					if (!O.IsValid() || !O->TryGetStringField(TEXT("key"), Key) || !O->TryGetStringField(TEXT("mesh"), Mesh) || Mesh.IsEmpty() || Key == TEXT("aquila") || !O->TryGetObjectField(TEXT("hull_m"), Hull) || !(*Hull)->TryGetArrayField(TEXT("x"), X) || X->Num() < 2)
					{
						continue;
					}
					const double Len = (*X)[1]->AsNumber() - (*X)[0]->AsNumber();
					const FSolids* Whole = Data.Find(Mesh);
					Expect(Whole != nullptr, FString::Printf(TEXT("no solids for the hull of the %s (%s)"), *Key, *Mesh));
					if (!Whole)
					{
						continue;
					}
					++Ships;
					const double WholeLen = Whole->Max.X - Whole->Min.X;
					Expect(FMath::Abs(WholeLen - Len) < 4.0 * Whole->Cell + 0.03 * Len, FString::Printf(TEXT("the %s's solids are %.0f m long and her class says %.0f"), *Key, WholeLen, Len));
					Expect(Whole->NumBoxes >= 20 && Whole->NumBoxes <= 8000, FString::Printf(TEXT("%s has %d boxes"), *Mesh, Whole->NumBoxes));
					const TArray<TSharedPtr<FJsonValue>>* Cuts = nullptr;
					if (!O->TryGetArrayField(TEXT("cuts_x_m"), Cuts) || Cuts->Num() < 2 || ((*Cuts)[0]->AsNumber() == 0.0 && (*Cuts)[1]->AsNumber() == 0.0))
					{
						continue;                                       // (a station is not cut in three)
					}
					const FSolids* Sec[3] = {Data.Find(Mesh + TEXT("_SecBow")), Data.Find(Mesh + TEXT("_SecMid")), Data.Find(Mesh + TEXT("_SecStern"))};
					bool bAll = Sec[0] && Sec[1] && Sec[2];
					Expect(bAll, FString::Printf(TEXT("the %s's three pieces have no solids"), *Key));
					if (bAll)
					{
						Pieces += 3;
						// end to end: the bow's tip is the hull's, the stern's is the hull's, and the middle lies between them (the cut faces' recess makes them overlap a little)
						Expect(FMath::Abs(Sec[0]->Max.X - Whole->Max.X) < 3.0 * Whole->Cell && FMath::Abs(Sec[2]->Min.X - Whole->Min.X) < 3.0 * Whole->Cell, FString::Printf(TEXT("the %s's pieces do not reach the hull's ends"), *Key));
						Expect(Sec[1]->Min.X >= Sec[2]->Min.X && Sec[1]->Max.X <= Sec[0]->Max.X && Sec[0]->Min.X >= Sec[1]->Min.X && Sec[2]->Max.X <= Sec[1]->Max.X, FString::Printf(TEXT("the %s's pieces are not in order along her length"), *Key));
						Expect(Sec[0]->Min.X <= Sec[1]->Max.X + 2.0 * Whole->Cell && Sec[1]->Min.X <= Sec[2]->Max.X + 2.0 * Whole->Cell, FString::Printf(TEXT("the %s's pieces do not meet at the cuts"), *Key));
					}
				}
				Expect(Ships >= 6, FString::Printf(TEXT("only %d ships have solids (the Praetorian, Vigilant, Acheron, Styx, Lethe, the Guilds' freighter and the Watch station should)"), Ships));
				Notes.Add(FString::Printf(TEXT("the wrecks' hulls: %d ships, %d pieces, each as long as her class says"), Ships, Pieces));
			}
		}
		// ---- a lookup is cheap
		{
			const FSolids* S = Data.Find(TEXT("SM_PLACE_Arsenal"));
			FRandomStream Rng(3);
			int32 In = 0;
			const double T0 = FPlatformTime::Seconds();
			const int32 N = 400000;
			for (int32 i = 0; i < N; ++i)
			{
				const FVector P(Rng.FRandRange((float)S->Min.X, (float)S->Max.X), Rng.FRandRange((float)S->Min.Y, (float)S->Max.Y), Rng.FRandRange((float)S->Min.Z, (float)S->Max.Z));
				In += S->Inside(P) ? 1 : 0;
			}
			const double Ns = (FPlatformTime::Seconds() - T0) * 1.0e9 / N;
			Notes.Add(FString::Printf(TEXT("a lookup: %.0f ns (%d of %d random points solid)"), Ns, In, N));
			Expect(Ns < 400.0, FString::Printf(TEXT("a lookup costs %.0f ns"), Ns));
		}
		return Fails.Num() == 0;
	}
}

// ------------------------------------------------------------------------------------------------------------------ the hit test (the battle's PilotCollision calls this)
bool UAstraSpaceLife::PilotHit(const FVector& Prev, const FVector& Now, FString& OutWhat) const
{
	if (!bLaidOut || !Owner)
	{
		return false;
	}
	const AstraSpace::FSolidData& Data = AstraSpace::SolidData();
	if (!Data.bLoaded)
	{
		return PilotHitWrecks(Prev, Now, OutWhat);          // (no boxes: the wrecks have their spheres)
	}
	for (const FSpaceLifePlace& P : Places)
	{
		if (!Layout.Nodes.IsValidIndex(P.Node))
		{
			continue;
		}
		const AstraSpace::FNode& N = Layout.Nodes[P.Node];
		if (!N.Spec || N.Spec->Mesh.IsEmpty())
		{
			continue;
		}
		const FAstraBattleShip* S = ShipOfPlace(P);
		if (!S || !S->bAlive)
		{
			continue;                                         // (a place that is no longer in the plot has no hull)
		}
		if (FMath::Min(FVector::Dist(Now, N.Pos), FVector::Dist(Prev, N.Pos)) > (double)N.RadiusM * 1.6 + 200.0)
		{
			continue;
		}
		const FVector A = N.Att.UnrotateVector(Prev - N.Pos), B = N.Att.UnrotateVector(Now - N.Pos);
		bool bHit = false;
		if (const AstraSpace::FSolids* Body = Data.Find(N.Spec->Mesh))
		{
			bHit = Body->Crosses(A, B);
		}
		// what turns on it, where the drawing has it now (the same clock, the same angle): the part's frame is its pivot and its turn
		for (int32 k = 0; N.Mesh && k < N.Mesh->Parts.Num() && !bHit; ++k)
		{
			const AstraSpace::FPart& D = N.Mesh->Parts[k];
			const AstraSpace::FSolids* Part = Data.Find(D.Mesh);
			if (!Part)
			{
				continue;
			}
			float Ang = D.Phase * 2.f * PI;
			if (D.SwingDeg > 0.f)
			{
				Ang += FMath::DegreesToRadians(D.SwingDeg) * FMath::Sin(Clock * 2.f * PI / FMath::Max(1.f, FMath::Abs(D.PeriodS)));
			}
			else if (FMath::Abs(D.PeriodS) > 0.1f)
			{
				Ang += Clock * 2.f * PI / D.PeriodS;
			}
			const FTransform PartXf(FQuat(D.Axis, Ang), D.Pivot);
			bHit = Part->Crosses(PartXf.InverseTransformPosition(A), PartXf.InverseTransformPosition(B));
		}
		if (bHit)
		{
			OutWhat = FString::Printf(TEXT("the hull of %s"), *N.Name);          // (as the war says it of a ship)
			return true;
		}
	}
	return PilotHitWrecks(Prev, Now, OutWhat);
}

bool UAstraSpaceLife::PilotHitWrecks(const FVector& Prev, const FVector& Now, FString& OutWhat) const
{
	if (Wrecks.Sites().Num() == 0)
	{
		return false;
	}
	const AstraSpace::FSolidData& Data = AstraSpace::SolidData();
	const double Clk = WreckClock();
	for (const AstraSpace::FSite& Si : Wrecks.Sites())
	{
		if (Si.System != SystemKey)
		{
			continue;
		}
		for (int32 pi = 0; pi < Si.Pieces.Num(); ++pi)
		{
			// a piece of a broken ship (or her whole hull, burnt dark) where her record has her now: the solids of her own mesh, in her own frame, turned as she is drawn
			const AstraSpace::FPieceRec& P = Si.Pieces[pi];
			const FVector Pivot = Sky.ToSystem(AstraSpace::FWrecks::PosAt(P, Clk));
			if (FMath::Min(FVector::Dist(Now, Pivot), FVector::Dist(Prev, Pivot)) > (double)P.Radius * 2.2 + 200.0)
			{
				continue;
			}
			bool bHit = false;
			if (const AstraSpace::FSolids* Sol = Data.bLoaded ? Data.Find(AstraSpace::FWrecks::PieceMesh(Si, pi)) : nullptr)
			{
				const FQuat Q = Sky.ToSystem(AstraSpace::FWrecks::AttAt(P, Clk));
				const FVector Origin = Pivot - Q.RotateVector(P.PivotLocal);
				bHit = Sol->Crosses(Q.UnrotateVector(Prev - Origin), Q.UnrotateVector(Now - Origin));
			}
			else
			{
				bHit = FMath::PointDistToSegment(Pivot, Prev, Now) < (double)P.Radius * 0.5;       // (a mesh with no solids: a sphere about her pivot, inside her outline)
			}
			if (bHit)
			{
				OutWhat = FString::Printf(TEXT("the %s"), *AstraSpace::FWrecks::PieceName(Si, pi));
				return true;
			}
		}
	}
	return false;
}

bool UAstraSpaceLife::DebugSolids(float Seconds, double RadiusM, FString& OutDetail)
{
	if (!bLaidOut || !Owner || Owner->Ships.Num() == 0 || !Owner->GetWorld())
	{
		OutDetail = TEXT("no living space laid out here");
		return false;
	}
	const AstraSpace::FSolidData& Data = AstraSpace::SolidData();
	if (!Data.bLoaded)
	{
		OutDetail = TEXT("data/space/solids.json is missing");
		return false;
	}
	const FVector Eye = Owner->PlayerPos();
	int32 Drawn = 0, NumPlaces = 0;
	const auto Draw = [&](const AstraSpace::FSolids& S, const FTransform& ToSystem)
	{
		// the cells near the eye, as runs along x (the file's boxes are not kept: the bitmap is what the game tests, so that is what is drawn)
		const FTransform Inv = ToSystem.Inverse();
		const FVector Centre = Inv.TransformPosition(Eye);
		const double Cell = S.Cell;
		const int32 R = FMath::CeilToInt(RadiusM / Cell);
		const int32 CX = FMath::FloorToInt((Centre.X - S.Origin.X) / Cell), CY = FMath::FloorToInt((Centre.Y - S.Origin.Y) / Cell), CZ = FMath::FloorToInt((Centre.Z - S.Origin.Z) / Cell);
		for (int32 X = FMath::Max(0, CX - R); X < FMath::Min(S.NX, CX + R + 1); ++X)
		{
			for (int32 Y = FMath::Max(0, CY - R); Y < FMath::Min(S.NY, CY + R + 1); ++Y)
			{
				int32 Run = -1;
				for (int32 Z = FMath::Max(0, CZ - R); Z <= FMath::Min(S.NZ, CZ + R + 1); ++Z)
				{
					const bool bSolid = Z < S.NZ && S.Bits[(X * S.NY + Y) * S.NZ + Z];
					if (bSolid && Run < 0)
					{
						Run = Z;
					}
					else if (!bSolid && Run >= 0)
					{
						if (Drawn < 3000)
						{
							const FVector Lo = S.Origin + FVector(X, Y, Run) * Cell, Hi = S.Origin + FVector(X + 1, Y + 1, Z) * Cell;
							const FVector C = ToSystem.TransformPosition((Lo + Hi) * 0.5);
							DrawDebugBox(Owner->GetWorld(), Owner->ToWorld(C), (Hi - Lo) * 50.0, Owner->ToWorldRot(ToSystem.GetRotation()), FColor(255, 160, 40), false, Seconds, 0, 6.f);
							++Drawn;
						}
						Run = -1;
					}
				}
			}
		}
	};
	for (const FSpaceLifePlace& P : Places)
	{
		if (!Layout.Nodes.IsValidIndex(P.Node))
		{
			continue;
		}
		const AstraSpace::FNode& N = Layout.Nodes[P.Node];
		if (!N.Spec || FVector::Dist(Eye, N.Pos) > (double)N.RadiusM * 1.6 + RadiusM)
		{
			continue;
		}
		++NumPlaces;
		if (const AstraSpace::FSolids* Body = Data.Find(N.Spec->Mesh))
		{
			Draw(*Body, FTransform(N.Att, N.Pos));
		}
		for (int32 k = 0; N.Mesh && k < N.Mesh->Parts.Num(); ++k)
		{
			const AstraSpace::FPart& D = N.Mesh->Parts[k];
			if (const AstraSpace::FSolids* Part = Data.Find(D.Mesh))
			{
				float Ang = D.Phase * 2.f * PI;
				Ang += D.SwingDeg > 0.f ? FMath::DegreesToRadians(D.SwingDeg) * FMath::Sin(Clock * 2.f * PI / FMath::Max(1.f, FMath::Abs(D.PeriodS))) : (FMath::Abs(D.PeriodS) > 0.1f ? Clock * 2.f * PI / D.PeriodS : 0.f);
				Draw(*Part, FTransform(FQuat(D.Axis, Ang), D.Pivot) * FTransform(N.Att, N.Pos));
			}
		}
	}
	// the pieces of the ships the war broke, where their records have them now
	int32 NumPieces = 0;
	const double Clk = WreckClock();
	for (const AstraSpace::FSite& Si : Wrecks.Sites())
	{
		if (Si.System != SystemKey)
		{
			continue;
		}
		for (int32 pi = 0; pi < Si.Pieces.Num(); ++pi)
		{
			const AstraSpace::FPieceRec& P = Si.Pieces[pi];
			const FVector Pivot = Sky.ToSystem(AstraSpace::FWrecks::PosAt(P, Clk));
			if (FVector::Dist(Eye, Pivot) > (double)P.Radius * 2.2 + RadiusM)
			{
				continue;
			}
			if (const AstraSpace::FSolids* Sol = Data.Find(AstraSpace::FWrecks::PieceMesh(Si, pi)))
			{
				const FQuat Q = Sky.ToSystem(AstraSpace::FWrecks::AttAt(P, Clk));
				Draw(*Sol, FTransform(Q, Pivot - Q.RotateVector(P.PivotLocal)));
				++NumPieces;
			}
		}
	}
	OutDetail = NumPlaces + NumPieces ? FString::Printf(TEXT("%d runs of solid cells within %.0f m of the eye drawn (orange) for %.0f s, in %d place(s) and %d wreck piece(s): the Falcon is lost inside them%s"), Drawn, RadiusM, Seconds, NumPlaces, NumPieces,
	                                                  Drawn >= 3000 ? TEXT(" (the first 3000; ask for a smaller radius)") : TEXT(""))
	                                  : FString(TEXT("no place or wreck within reach of the eye (astra.space.look keeper 4, astra.space.look wreck 1)"));
	return NumPlaces + NumPieces > 0;
}

bool UAstraSpaceLife::DebugSolidsTest(FString& OutDetail)
{
	const AstraSpace::FSolidData& Data = AstraSpace::SolidData();
	if (!bLaidOut || !Data.bLoaded)
	{
		OutDetail = TEXT("no living space laid out here, or no solids");
		return false;
	}
	int32 Failed = 0, Checked = 0;
	FString Lines, Names;
	const auto Expect = [&](bool bOk, const FString& What)
	{
		++Checked;
		if (!bOk)
		{
			++Failed;
			Lines += FString::Printf(TEXT("FAIL %s; "), *What);
		}
	};
	bool bRing = false;
	for (const FSpaceLifePlace& P : Places)
	{
		if (!Layout.Nodes.IsValidIndex(P.Node) || !Layout.Nodes[P.Node].Spec)
		{
			continue;
		}
		const AstraSpace::FNode& N = Layout.Nodes[P.Node];
		const AstraSpace::FSolids* Body = Data.Find(N.Spec->Mesh);
		if (!Body)
		{
			continue;
		}
		Names += (Names.IsEmpty() ? TEXT("") : TEXT(", ")) + N.Name;
		const auto Hit = [&](const FVector& InPlace)
		{
			const FVector Sys = N.Pos + N.Att.RotateVector(InPlace);
			FString What;
			return PilotHit(Sys, Sys, What);
		};
		// the body: a solid cell is hit (and the place is named as a ship would be), the air far off is not
		bool bFound = false;
		for (int32 X = 0; X < Body->NX && !bFound; X += 3)
		{
			for (int32 Y = 0; Y < Body->NY && !bFound; ++Y)
			{
				for (int32 Z = 0; Z < Body->NZ && !bFound; ++Z)
				{
					if (Body->Bits[(X * Body->NY + Y) * Body->NZ + Z])
					{
						const FVector In = Body->Origin + FVector(X + 0.5, Y + 0.5, Z + 0.5) * Body->Cell;
						FString What;
						const FVector Sys = N.Pos + N.Att.RotateVector(In);
						Expect(PilotHit(Sys - FVector(1.0, 0.0, 0.0), Sys, What) && What == FString::Printf(TEXT("the hull of %s"), *N.Name), FString::Printf(TEXT("%s: a solid cell is not hit (%s)"), *N.Name, *What));
						bFound = true;
					}
				}
			}
		}
		Expect(!Hit(FVector(0.0, 0.0, 40000.0)), FString::Printf(TEXT("%s: air 40 km off is hit"), *N.Name));
		// the turning part that is a ring: the open quarters and the spokes where the turn puts them, at three clocks
		for (int32 k = 0; N.Mesh && k < N.Mesh->Parts.Num(); ++k)
		{
			const AstraSpace::FPart& D = N.Mesh->Parts[k];
			const AstraSpace::FSolids* Ring = Data.Find(D.Mesh);
			if (!Ring || FMath::Abs(D.PeriodS) < 5.f || D.SwingDeg > 0.f || !D.Axis.Equals(FVector(1.0, 0.0, 0.0), 1.0e-3))
			{
				continue;
			}
			bRing = true;
			const double Rad = 0.5 * FMath::Min(Ring->Max.Y - Ring->Min.Y, Ring->Max.Z - Ring->Min.Z) * 0.55;
			const auto Pt = [&](double Deg) { return D.Pivot + FVector(0.0, FMath::Cos(FMath::DegreesToRadians(Deg)) * Rad, FMath::Sin(FMath::DegreesToRadians(Deg)) * Rad); };
			const float Saved = Clock;
			const double Period = FMath::Abs(D.PeriodS);
			const double Turned = D.Phase * 360.0;                  // where the ring is at clock 0 (degrees); the spokes are on the diagonals of her own frame
			const double Sign = D.PeriodS > 0.f ? 1.0 : -1.0;
			for (const double Quarter : {0.0, 1.0 / 16.0, 1.0 / 8.0})
			{
				Clock = (float)(Quarter * Period);
				const double Ang = Turned + Sign * Quarter * 360.0;     // degrees the ring has turned
				Expect(!Hit(Pt(Ang)), FString::Printf(TEXT("%s: the ring's open quarter at %.1f deg is hit"), *N.Name, Ang));
				Expect(Hit(Pt(Ang + 45.0)) && Hit(Pt(Ang + 135.0)), FString::Printf(TEXT("%s: the ring's spokes are not at %.1f deg"), *N.Name, Ang + 45.0));
			}
			Clock = Saved;
		}
	}
	// the pieces of the ships the war broke: a solid cell of a piece's own mesh is hit where her record has her now, and named as the war names a ship's hull; the air 5 km off is not; the pivot the effects
	// gave her lies inside her own mesh (a frame that was mirrored or shifted would put it outside)
	int32 Pieces = 0, WithSolids = 0;
	{
		const double Clk = WreckClock();
		for (const AstraSpace::FSite& Si : Wrecks.Sites())
		{
			if (Si.System != SystemKey)
			{
				continue;
			}
			for (int32 pi = 0; pi < Si.Pieces.Num() && Pieces < 16; ++pi)
			{
				const AstraSpace::FPieceRec& P = Si.Pieces[pi];
				++Pieces;
				const AstraSpace::FSolids* Sol = Data.Find(AstraSpace::FWrecks::PieceMesh(Si, pi));
				if (!Sol)
				{
					continue;
				}
				++WithSolids;
				const FVector Pivot = Sky.ToSystem(AstraSpace::FWrecks::PosAt(P, Clk));
				const FQuat Q = Sky.ToSystem(AstraSpace::FWrecks::AttAt(P, Clk));
				const FVector Origin = Pivot - Q.RotateVector(P.PivotLocal);
				const FString Mesh = AstraSpace::FWrecks::PieceMesh(Si, pi);
				const FVector Slack(Sol->Cell * 2.0);
				Expect(P.PivotLocal.X >= Sol->Min.X - Slack.X && P.PivotLocal.X <= Sol->Max.X + Slack.X && P.PivotLocal.Y >= Sol->Min.Y - Slack.Y && P.PivotLocal.Y <= Sol->Max.Y + Slack.Y
				       && P.PivotLocal.Z >= Sol->Min.Z - Slack.Z && P.PivotLocal.Z <= Sol->Max.Z + Slack.Z,
				       FString::Printf(TEXT("%s: the pivot %s lies outside her mesh (%s to %s)"), *Mesh, *P.PivotLocal.ToString(), *Sol->Min.ToString(), *Sol->Max.ToString()));
				bool bFound = false;
				for (int32 X = Sol->NX / 2; X < Sol->NX && !bFound; ++X)
				{
					for (int32 Y = 0; Y < Sol->NY && !bFound; ++Y)
					{
						for (int32 Z = 0; Z < Sol->NZ && !bFound; ++Z)
						{
							if (Sol->Bits[(X * Sol->NY + Y) * Sol->NZ + Z])
							{
								const FVector In = Sol->Origin + FVector(X + 0.5, Y + 0.5, Z + 0.5) * Sol->Cell;
								const FVector Sys = Origin + Q.RotateVector(In);
								FString What;
								Expect(PilotHit(Sys - Q.GetForwardVector() * 1.0, Sys, What) && What == FString::Printf(TEXT("the %s"), *AstraSpace::FWrecks::PieceName(Si, pi)), FString::Printf(TEXT("%s: a solid cell of her is not hit (%s)"), *Mesh, *What));
								bFound = true;
							}
						}
					}
				}
				FString Air;
				const FVector Off = Pivot + FVector(0.0, 0.0, 5000.0);
				Expect(!PilotHit(Off, Off, Air), FString::Printf(TEXT("%s: air 5 km above her is hit (%s)"), *Mesh, *Air));
			}
		}
		if (Pieces > 0)
		{
			Expect(WithSolids > 0, FString::Printf(TEXT("%d wreck pieces here and not one has solids (art/blender/space3_solids.py --ships, then tools/space.py sync)"), Pieces));
		}
	}
	OutDetail = FString::Printf(TEXT("%d checks over %s%s%s: %s"), Checked, *Names, bRing ? TEXT(" (the turning ring too)") : TEXT(""), Pieces ? *FString::Printf(TEXT(" and %d wreck piece(s)"), Pieces) : TEXT(""),
	                            Failed ? *Lines : TEXT("every hull is where it is drawn"));
	return Failed == 0 && Checked > 0;
}

// ------------------------------------------------------------------------------------------------------------------ the console
namespace
{
	FAutoConsoleCommandWithWorld CmdSpaceSolidsTest(TEXT("astra.space.solids.test"), TEXT("The places' hull boxes in this world: hit where they are drawn, the turning ring's spokes where the turn puts them"),
		FConsoleCommandWithWorldDelegate::CreateLambda([](UWorld* W)
		{
			UAstraBattleSubsystem* B = W ? W->GetSubsystem<UAstraBattleSubsystem>() : nullptr;
			UAstraSpaceLife* S = B ? B->GetSpace() : nullptr;
			if (!S) { UE_LOG(LogASTRA, Display, TEXT("[Space] none in this world")); return; }
			FString Detail;
			const bool bOk = S->DebugSolidsTest(Detail);
			UE_LOG(LogASTRA, Display, TEXT("[Space] solids in the world: %s %s"), *Detail, bOk ? TEXT("SOLIDS_WORLD_OK") : TEXT("SOLIDS_WORLD_FAILED"));
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdSpaceSolids(TEXT("astra.space.solids"), TEXT("Draw the hull boxes of the places near the eye, where the Captain's Falcon is lost if she flies in: astra.space.solids [radius m, default 300] [seconds, default 20]"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& A, UWorld* W)
		{
			UAstraBattleSubsystem* B = W ? W->GetSubsystem<UAstraBattleSubsystem>() : nullptr;
			UAstraSpaceLife* S = B ? B->GetSpace() : nullptr;
			if (!S) { UE_LOG(LogASTRA, Display, TEXT("[Space] none in this world")); return; }
			FString Detail;
			S->DebugSolids(A.Num() > 1 ? (float)FCString::Atod(*A[1]) : 20.f, A.Num() > 0 ? FCString::Atod(*A[0]) : 300.0, Detail);
			UE_LOG(LogASTRA, Display, TEXT("[Space] %s"), *Detail);
		}));
}
