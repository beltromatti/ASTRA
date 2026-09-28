// ASTRA — the ground of any world.

#include "AstraWorldGen.h"

namespace
{
	uint32 HashU(uint32 X)
	{
		X ^= X >> 16; X *= 0x7feb352dU; X ^= X >> 15; X *= 0x846ca68bU; X ^= X >> 16;
		return X;
	}

	/** 0 below E0, 1 above E1 (reversed when E0 > E1), smooth between. */
	float Smooth(float E0, float E1, float X)
	{
		const float T = FMath::Clamp((X - E0) / (E1 - E0), 0.f, 1.f);
		return T * T * (3.f - 2.f * T);
	}

	constexpr double FeatureHalf = 46000.0;   // m: craters and cones are scattered this far out (the far ground reaches 45 km)
	constexpr double CellSize = 2000.0;       // the crater lookup grid
	constexpr int32 Cells = int32(2.0 * FeatureHalf / CellSize);
}

EAstraWorldKind FAstraWorldGen::KindFromPlanetType(const FString& T)
{
	return T == TEXT("desert") ? EAstraWorldKind::Desert : T == TEXT("ice") ? EAstraWorldKind::Ice : T == TEXT("lava") ? EAstraWorldKind::Lava
	     : T == TEXT("barren") ? EAstraWorldKind::Barren : EAstraWorldKind::Ocean;
}

bool FAstraWorldGen::HasSurface(const FString& PlanetType)
{
	return !PlanetType.IsEmpty() && PlanetType != TEXT("gas_giant");
}

FAstraWorldGen::FAstraWorldGen(const FString& WorldName, EAstraWorldKind InKind)
	: Kind(InKind)
{
	Seed = HashU(GetTypeHash(WorldName.ToLower()) ^ 0x9e3779b9U);
	FRandomStream R((int32)(Seed & 0x7fffffff));
	switch (Kind)
	{
	case EAstraWorldKind::Ocean: SeaLevel = 0.f; Talus = 0.9f; break;
	case EAstraWorldKind::Desert: Talus = 1.8f; break;            // mesa walls stand sheer
	case EAstraWorldKind::Ice: Talus = 1.2f; break;               // the frozen sea of an ice world is ground, not a sea
	case EAstraWorldKind::Barren: Talus = 1.0f; break;
	case EAstraWorldKind::Lava: SeaLevel = -40.f; Talus = 1.3f; break;   // lava in the channels and the low ground
	}
	if (Kind == EAstraWorldKind::Barren)
	{
		// craters of every size, the small ones by far the most (a power law), and one great crater in sight of the field
		const float A = R.FRandRange(0.f, 2.f * PI), D = R.FRandRange(4200.f, 5600.f), Big = R.FRandRange(1600.f, 2300.f);
		Craters.Add(FVector4f(FMath::Cos(A) * D, FMath::Sin(A) * D, Big, Big * 0.13f));
		for (int32 i = 0; i < 1100; ++i)
		{
			const float Rad = 45.f + 2500.f * FMath::Pow(R.FRand(), 5.f);
			const float Ratio = FMath::Lerp(0.2f, 0.11f, FMath::Clamp((Rad - 200.f) / 1500.f, 0.f, 1.f));   // small craters are deeper
			Craters.Add(FVector4f(R.FRandRange(-FeatureHalf, FeatureHalf), R.FRandRange(-FeatureHalf, FeatureHalf), Rad, Rad * Ratio * R.FRandRange(0.8f, 1.15f)));
		}
		CraterCells.SetNum(Cells * Cells);
		auto CellOf = [](double V) { return FMath::Clamp(int32((V + FeatureHalf) / CellSize), 0, Cells - 1); };
		for (int32 c = 0; c < Craters.Num(); ++c)
		{
			const FVector4f& C = Craters[c];
			const double Reach = C.Z * 2.2;
			for (int32 y = CellOf(C.Y - Reach); y <= CellOf(C.Y + Reach); ++y)
			{
				for (int32 x = CellOf(C.X - Reach); x <= CellOf(C.X + Reach); ++x)
				{
					CraterCells[y * Cells + x].Add(c);
				}
			}
		}
	}
	if (Kind == EAstraWorldKind::Lava)
	{
		// a great cone in sight of the field, more across the plains
		const float A = R.FRandRange(0.f, 2.f * PI), D = R.FRandRange(7500.f, 9500.f);
		Cones.Add(FVector4f(FMath::Cos(A) * D, FMath::Sin(A) * D, R.FRandRange(4500.f, 6000.f), R.FRandRange(1500.f, 2300.f)));
		for (int32 i = 0; i < 14; ++i)
		{
			Cones.Add(FVector4f(R.FRandRange(-40000.f, 40000.f), R.FRandRange(-40000.f, 40000.f), R.FRandRange(2000.f, 6500.f), R.FRandRange(400.f, 2000.f)));
		}
	}
	PlaceSite();
}

float FAstraWorldGen::Noise(double X, double Y) const
{
	const int64 IX = FMath::FloorToInt64(X), IY = FMath::FloorToInt64(Y);
	const float FX = (float)(X - IX), FY = (float)(Y - IY);
	const float UX = FX * FX * FX * (FX * (FX * 6.f - 15.f) + 10.f);
	const float UY = FY * FY * FY * (FY * (FY * 6.f - 15.f) + 10.f);
	auto H = [this](int64 A, int64 B)
	{
		return (HashU((uint32)A * 73856093U ^ (uint32)B * 19349663U ^ Seed) & 0xffffff) / float(0xffffff);
	};
	const float A = H(IX, IY), B = H(IX + 1, IY), C = H(IX, IY + 1), D = H(IX + 1, IY + 1);
	return FMath::Lerp(FMath::Lerp(A, B, UX), FMath::Lerp(C, D, UX), UY);
}

float FAstraWorldGen::Fbm(double X, double Y, int32 Octaves) const
{
	float V = 0.f, Amp = 0.5f, Norm = 0.f;
	for (int32 i = 0; i < Octaves; ++i)
	{
		V += Amp * Noise(X, Y);
		Norm += Amp;
		X = X * 2.03 + 17.1;
		Y = Y * 2.03 + 3.7;
		Amp *= 0.5f;
	}
	return V / Norm;
}

float FAstraWorldGen::Ridged(double X, double Y, int32 Octaves) const
{
	float V = 0.f, Amp = 0.5f, Norm = 0.f, Prev = 1.f;
	for (int32 i = 0; i < Octaves; ++i)
	{
		float N = 1.f - FMath::Abs(Noise(X, Y) * 2.f - 1.f);
		N = N * N * Prev;
		Prev = N;
		V += Amp * N;
		Norm += Amp;
		X = X * 2.07 + 11.3;
		Y = Y * 2.07 + 5.9;
		Amp *= 0.5f;
	}
	return V / Norm;
}

float FAstraWorldGen::CraterSum(double X, double Y) const
{
	if (CraterCells.Num() == 0)
	{
		return 0.f;
	}
	const int32 CX = FMath::Clamp(int32((X + FeatureHalf) / CellSize), 0, Cells - 1);
	const int32 CY = FMath::Clamp(int32((Y + FeatureHalf) / CellSize), 0, Cells - 1);
	float H = 0.f;
	for (const int32 c : CraterCells[CY * Cells + CX])
	{
		const FVector4f& C = Craters[c];
		const float D = FMath::Sqrt(float(FMath::Square(X - C.X) + FMath::Square(Y - C.Y))) / C.Z;
		if (D >= 2.2f)
		{
			continue;
		}
		// a bowl (flat-floored when large), a raised rim, the ejecta blanket beyond it, a central peak in the great ones
		const float Bowl = D < 1.f ? -C.W * FMath::Min(1.f, (1.f - D * D) * (C.Z > 900.f ? 1.6f : 1.f)) : 0.f;
		const float Rim = C.W * 0.32f * FMath::Exp(-FMath::Square((D - 1.f) / 0.16f));
		const float Ejecta = D > 1.f ? C.W * 0.08f * FMath::Square(1.f - (D - 1.f) / 1.2f) : 0.f;
		const float Peak = C.Z > 1200.f ? C.W * 0.45f * FMath::Exp(-FMath::Square(D / 0.16f)) : 0.f;
		H += Bowl + Rim + Ejecta + Peak;
	}
	return H;
}

float FAstraWorldGen::Raw(double X, double Y, bool bDetail) const
{
	const int32 O = bDetail ? 6 : 4;
	// a little domain warp keeps every shape from looking like noise
	const double WX = X + 900.0 * (Fbm(X / 9000.0, Y / 9000.0 + 3.0, 3) - 0.5);
	const double WY = Y + 900.0 * (Fbm(X / 9000.0 + 7.0, Y / 9000.0, 3) - 0.5);
	float H = 0.f;
	switch (Kind)
	{
	case EAstraWorldKind::Ocean:
	{
		// islands: the land rises where the broad noise is high (always one by the field); ridged mountains on the larger
		// ones; cliffs where some headlands meet the sea
		const float Land = Fbm(WX / 14000.0, WY / 14000.0, 4) - 0.47f + 0.12f * FMath::Exp(-float((X * X + Y * Y) / (6000.0 * 6000.0)));
		H = 900.f * Land + 800.f * Smooth(0.02f, 0.25f, Land) * Ridged(WX / 5000.0 + 4.0, WY / 5000.0, O)
		  + 90.f * (Fbm(WX / 1800.0, WY / 1800.0, O) - 0.5f);
		const float Cliff = Smooth(0.56f, 0.64f, Fbm(WX / 4000.0 + 13.0, WY / 4000.0, 3));
		H = H > 0.f ? H * Smooth(0.f, 40.f, H) + 1.5f + 30.f * Cliff * Smooth(0.f, 5.f, H) : H * 0.6f - 6.f;   // beaches, then a shelving sea floor
		break;
	}
	case EAstraWorldKind::Desert:
	{
		// mesas and buttes: a plateau field cut into tiers, sheer walls over talus aprons
		const float M = Fbm(WX / 3400.0 + 9.0, WY / 3400.0, O);
		const float Mesa = 30.f * Smooth(0.52f, 0.56f, M) + 120.f * Smooth(0.56f, 0.567f, M) + 70.f * Smooth(0.635f, 0.642f, M);
		// dune seas in the open ground, in long rows across the wind
		const float Open = 1.f - Smooth(0.47f, 0.53f, M);
		const double Along = WX * 0.8 + WY * 0.6;
		const float DuneMask = Open * Smooth(0.4f, 0.6f, Fbm(WX / 6000.0 + 2.0, WY / 6000.0, 3));
		const float Dunes = DuneMask * (14.f + 22.f * Fbm(WX / 2000.0, WY / 2000.0, 2))
		                  * FMath::Pow(FMath::Abs(FMath::Sin(float(Along / 380.0 + 6.0 * Fbm(WX / 2600.0, WY / 2600.0, 3)))), 1.5f);
		// and a canyon winding through it all
		const float Canyon = 1.f - Smooth(0.0f, 0.03f, FMath::Abs(Fbm(WX / 12000.0 + 5.0, WY / 12000.0, 4) - 0.5f));
		H = 40.f + 60.f * Fbm(WX / 6000.0, WY / 6000.0, O) + Mesa + Dunes - 90.f * Canyon;
		break;
	}
	case EAstraWorldKind::Ice:
	{
		// an ice sheet rising from a frozen sea to the south: pressure ridges, nunataks breaking through, mountains inland
		const float Coast = float(WY / 1000.0) + 6.f * (Fbm(WX / 12000.0, WY / 12000.0, 4) - 0.5f) + 2.f;   // km inland
		const float Inland = Smooth(-0.3f, 3.f, Coast);
		const float Nunatak = Smooth(0.6f, 0.72f, Fbm(WX / 1900.0 + 11.0, WY / 1900.0, bDetail ? 5 : 3));
		H = Inland * (30.f + 120.f * Fbm(WX / 7000.0, WY / 7000.0, 4)) + 10.f * Inland * Ridged(WX / 900.0, WY / 900.0, 3)
		  + 260.f * Inland * Nunatak * (0.6f + 0.4f * Ridged(WX / 700.0, WY / 700.0, 3))
		  + 1400.f * Smooth(2.5f, 10.f, Coast) * FMath::Pow(Ridged(WX / 6000.0 + 3.0, WY / 6000.0, O), 1.3f)
		  + (bDetail ? 6.f * (Fbm(WX / 500.0, WY / 500.0, 3) - 0.5f) : 0.f);
		H = Coast > 0.f ? FMath::Max(H, 1.f) + 30.f * Smooth(0.f, 0.25f, Coast)          // an ice cliff at the shore
		                : 0.3f + (bDetail ? 0.5f * Ridged(WX / 300.0, WY / 300.0, 2) : 0.2f);   // pack ice beyond it
		break;
	}
	case EAstraWorldKind::Barren:
	{
		// old highlands and plains, then the craters on top of everything
		H = 160.f * Fbm(WX / 6000.0, WY / 6000.0, O) + 30.f * Fbm(WX / 1200.0, WY / 1200.0, 3)
		  + 700.f * Ridged(WX / 11000.0, WY / 11000.0, 5) * Smooth(0.42f, 0.7f, Fbm(WX / 20000.0, WY / 20000.0, 3));
		H += CraterSum(X, Y);
		break;
	}
	case EAstraWorldKind::Lava:
	{
		// basalt plains, lava in the winding channels and the basins, the cones over it all
		H = 30.f + 100.f * Fbm(WX / 5000.0, WY / 5000.0, O) - 170.f * Smooth(0.45f, 0.36f, Fbm(WX / 7000.0 + 3.0, WY / 7000.0, 4));
		const float Channel = 1.f - Smooth(0.006f, 0.024f, FMath::Abs(Fbm(WX / 5500.0 + 1.0, WY / 5500.0 + 4.0, 4) - 0.5f));
		H = FMath::Lerp(H, FMath::Min(H, SeaLevel - 12.f), Channel);
		if (bDetail)
		{
			H += 5.f * Ridged(WX / 220.0, WY / 220.0, 3);   // ropy, broken flows (too fine for the far ground: it would alias)
		}
		for (const FVector4f& C : Cones)
		{
			const float D = FMath::Sqrt(float(FMath::Square(X - C.X) + FMath::Square(Y - C.Y))) / C.Z;
			if (D < 1.f)
			{
				const float Cone = C.W * FMath::Pow(1.f - D, 1.8f) * (0.85f + 0.3f * Fbm(X / 900.0, Y / 900.0, 3));
				H = FMath::Max(H, Cone - (D < 0.12f ? C.W * 0.25f * (1.f - D / 0.12f) : 0.f));   // a crater at the top
			}
		}
		break;
	}
	}
	if (bDetail)
	{
		H += 2.5f * (Fbm(X / 90.0, Y / 90.0, 3) - 0.5f);
	}
	return H;
}

float FAstraWorldGen::Height(double X, double Y, bool bDetail) const
{
	const float H = Raw(X, Y, bDetail);
	// the landing site, levelled, blending out over twice its size
	const float Q = FMath::Max(FMath::Abs(float(X - Site.X)), FMath::Abs(float(Y - Site.Y))) / SiteHalf;
	const float W = Smooth(1.f, 2.2f, Q);
	return H * W + SiteZ * (1.f - W);
}

void FAstraWorldGen::PlaceSite()
{
	// the flattest dry spot within 3.5 km of the origin, not too high (on an ice world: on the ice sheet, not the sea ice)
	const float MinZ = Kind == EAstraWorldKind::Ice ? 12.f : SeaLevel + 8.f;
	float Best = 1e9f;
	FVector2D BestP(0.f, 0.f);
	float BestZ = FMath::Max(MinZ, 0.f);
	for (int32 i = -7; i <= 7; ++i)
	{
		for (int32 j = -7; j <= 7; ++j)
		{
			const double X = i * 500.0, Y = j * 500.0;
			const float H = Raw(X, Y, false);
			if (H < MinZ)
			{
				continue;
			}
			float Slope = 0.f;
			for (const FVector2D& D : {FVector2D(120, 0), FVector2D(-120, 0), FVector2D(0, 120), FVector2D(0, -120)})
			{
				Slope = FMath::Max(Slope, FMath::Abs(Raw(X + D.X, Y + D.Y, false) - H));
			}
			const float Score = Slope + 0.002f * FMath::Sqrt(float(X * X + Y * Y)) + 0.02f * FMath::Max(0.f, H - 300.f);
			if (Score < Best)
			{
				Best = Score;
				BestP = FVector2D(X, Y);
				BestZ = H;
			}
		}
	}
	Site = BestP;
	SiteZ = BestZ;
}
