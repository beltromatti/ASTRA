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
		return false;
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
	OutDetail = NumPlaces ? FString::Printf(TEXT("%d runs of solid cells within %.0f m of the eye drawn (orange) for %.0f s, in %d place(s): the Falcon is lost inside them%s"), Drawn, RadiusM, Seconds, NumPlaces, Drawn >= 3000 ? TEXT(" (the first 3000; ask for a smaller radius)") : TEXT(""))
	                   : FString(TEXT("no place within reach of the eye (astra.space.look keeper 4)"));
	return NumPlaces > 0;
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
	OutDetail = FString::Printf(TEXT("%d checks over %s%s: %s"), Checked, *Names, bRing ? TEXT(" (the turning ring too)") : TEXT(""), Failed ? *Lines : TEXT("every hull is where it is drawn"));
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
