// ASTRA — the surface of any world, built at run time.

#include "AstraWorldSurface.h"

#include "ASTRA.h"
#include "Components/ExponentialHeightFogComponent.h"
#include "Components/PointLightComponent.h"
#include "Components/SkyAtmosphereComponent.h"
#include "Components/SkyLightComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Components/VolumetricCloudComponent.h"
#include "Engine/StaticMesh.h"
#include "Materials/MaterialInterface.h"
#include "Async/ParallelFor.h"
#include "ProceduralMeshComponent.h"

namespace
{
	constexpr double CoreHalf = 6000.0;     // m: the landing zone's detailed ground, 12 x 12 km
	constexpr double CoreStep = 24.0;
	constexpr int32 CoreTiles = 4;
	constexpr double FarHalf = 45000.0;     // m: the ground to the horizon, 90 x 90 km
	constexpr double FarStep = 300.0;
	constexpr double EdgeBlend = 7000.0;    // m: the far ground's outer band settles to one height, where the horizon rings begin
	constexpr double Blend = 400.0;         // the core's outer band that meets the far ground
	constexpr double PlanetRadius = 6.0e6;  // m: the worlds curve away like the sky atmosphere's planet (its BottomRadius)
	// the horizon rings (half-sizes, m): past the true horizon even from orbit altitude (sqrt(2 R h) = 410 km at 14 km)
	constexpr double RingHalves[] = {45000.0, 60000.0, 80000.0, 110000.0, 150000.0, 210000.0, 300000.0, 420000.0, 600000.0};

	/** How far the ground has fallen away below the flat zone at (x, y) m: nothing over the landing zone, then the
	 *  curve of a planet (C1 at the core's edge, so no crease). */
	double Drop(double X, double Y)
	{
		const double R = FMath::Max(0.0, FMath::Sqrt(X * X + Y * Y) - CoreHalf);
		return R * R / (2.0 * PlanetRadius);
	}

	/** The up of the curved surface at (x, y): tilted outward as the planet curves away. */
	FVector CurvedUp(double X, double Y)
	{
		const double D = FMath::Sqrt(X * X + Y * Y);
		const double Slope = D > CoreHalf ? (D - CoreHalf) / PlanetRadius / D : 0.0;
		return FVector(X * Slope, Y * Slope, 1.0).GetSafeNormal();
	}

	/** Concentric square rings from RingHalves[0] out to 600 km, S segments per side, at ZMetres over the curve. */
	void AddRings(TArray<FVector>& V, TArray<FVector>& N, TArray<FVector2D>& UV, TArray<int32>& Tri, float ZMetres, int32 S)
	{
		const int32 P = 4 * S;
		int32 Prev = -1;
		for (const double Half : RingHalves)
		{
			const int32 Base = V.Num();
			for (int32 k = 0; k < P; ++k)
			{
				const double T = double(k % S) / S;
				double X, Y;
				switch (k / S)
				{
				case 0: X = -Half + 2.0 * Half * T; Y = -Half; break;
				case 1: X = Half; Y = -Half + 2.0 * Half * T; break;
				case 2: X = Half - 2.0 * Half * T; Y = Half; break;
				default: X = -Half; Y = Half - 2.0 * Half * T; break;
				}
				V.Add(FVector(X, Y, ZMetres - Drop(X, Y)) * 100.0);
				N.Add(CurvedUp(X, Y));
				UV.Add(FVector2D(X / 100.0, Y / 100.0));
			}
			if (Prev >= 0)
			{
				for (int32 k = 0; k < P; ++k)
				{
					const int32 K1 = (k + 1) % P;
					Tri.Append({Prev + k, Prev + K1, Base + K1, Prev + k, Base + K1, Base + k});
				}
			}
			Prev = Base;
		}
	}

	/** A tangent along +x (the textures' u) laid onto the surface: without one the normal maps break on the walls. */
	TArray<FProcMeshTangent> TangentsFor(const TArray<FVector>& Normals)
	{
		TArray<FProcMeshTangent> T;
		T.Reserve(Normals.Num());
		for (const FVector& N : Normals)
		{
			const FVector Axis = FMath::Abs(N.X) < 0.9 ? FVector::XAxisVector : FVector::YAxisVector;
			T.Add(FProcMeshTangent((Axis - N * FVector::DotProduct(N, Axis)).GetSafeNormal(), false));
		}
		return T;
	}

	UMaterialInterface* Mat(const FString& Name)
	{
		return LoadObject<UMaterialInterface>(nullptr, *FString::Printf(TEXT("/Game/ASTRA/Materials/Instances/%s.%s"), *Name, *Name));
	}

	const TCHAR* KindName(EAstraWorldKind K)
	{
		switch (K)
		{
		case EAstraWorldKind::Desert: return TEXT("Desert");
		case EAstraWorldKind::Ice: return TEXT("Ice");
		case EAstraWorldKind::Barren: return TEXT("Barren");
		case EAstraWorldKind::Lava: return TEXT("Lava");
		default: return TEXT("Ocean");
		}
	}
}

AAstraWorldSurface::AAstraWorldSurface()
{
	PrimaryActorTick.bCanEverTick = false;
	Root = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	Root->SetMobility(EComponentMobility::Static);   // the world never moves: its shadows can stay cached
	SetRootComponent(Root);
	Core = CreateDefaultSubobject<UProceduralMeshComponent>(TEXT("Core"));
	Core->SetupAttachment(Root);
	Core->SetMobility(EComponentMobility::Static);
	Core->bUseAsyncCooking = true;
	Core->bUseComplexAsSimpleCollision = true;
	Core->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
	Core->SetCollisionResponseToAllChannels(ECR_Block);
	Core->SetCastShadow(false);   // ShadowProxy casts the ground's shadows, at a quarter of the triangles
	ShadowProxy = CreateDefaultSubobject<UProceduralMeshComponent>(TEXT("ShadowProxy"));
	ShadowProxy->SetupAttachment(Root);
	ShadowProxy->SetMobility(EComponentMobility::Static);
	ShadowProxy->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	ShadowProxy->SetRenderInMainPass(false);
	ShadowProxy->SetRenderInDepthPass(false);
	ShadowProxy->SetCastShadow(true);
	ShadowProxy->bCastHiddenShadow = true;
	Far = CreateDefaultSubobject<UProceduralMeshComponent>(TEXT("Far"));
	Far->SetupAttachment(Root);
	Far->SetMobility(EComponentMobility::Static);
	Far->bUseAsyncCooking = true;
	Far->bUseComplexAsSimpleCollision = true;
	Far->SetCollisionEnabled(ECollisionEnabled::QueryOnly);   // no sea to catch a Falcon beyond the core on a dry world
	Far->SetCollisionResponseToAllChannels(ECR_Block);
	Far->SetCastShadow(false);
	Sea = CreateDefaultSubobject<UProceduralMeshComponent>(TEXT("Sea"));
	Sea->SetupAttachment(Root);
	Sea->SetMobility(EComponentMobility::Static);
	Sea->bUseAsyncCooking = true;
	Sea->bUseComplexAsSimpleCollision = true;
	Sea->SetCastShadow(false);
	Sea->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
	Sea->SetCollisionResponseToAllChannels(ECR_Block);
	Atmosphere = CreateDefaultSubobject<USkyAtmosphereComponent>(TEXT("Atmosphere"));
	Atmosphere->SetupAttachment(Root);
	Clouds = CreateDefaultSubobject<UVolumetricCloudComponent>(TEXT("Clouds"));
	Clouds->SetupAttachment(Root);
	Fog = CreateDefaultSubobject<UExponentialHeightFogComponent>(TEXT("Fog"));
	Fog->SetupAttachment(Root);
	SkyLight = CreateDefaultSubobject<USkyLightComponent>(TEXT("SkyLight"));
	SkyLight->SetupAttachment(Root);
	SkyLight->SetRelativeLocation(FVector(0.f, 0.f, 50000.f));
	SkyLight->SetMobility(EComponentMobility::Movable);
	SkyLight->SourceType = ESkyLightSourceType::SLS_CapturedScene;
	SkyLight->bRealTimeCapture = true;
	Beacon = CreateDefaultSubobject<UPointLightComponent>(TEXT("Beacon"));
	Beacon->SetupAttachment(Root);
	Beacon->SetCastShadows(false);
	Beacon->SetIntensityUnits(ELightUnits::Lumens);
}

void AAstraWorldSurface::Build(const FString& InWorldName, const FString& InPlanetType, const FString& InOwner)
{
	WorldName = InWorldName;
	PlanetType = InPlanetType;
	Owner = InOwner;
	const double T0 = FPlatformTime::Seconds();
	Gen = MakeUnique<FAstraWorldGen>(WorldName, FAstraWorldGen::KindFromPlanetType(PlanetType));
	BuildGround();
	BuildSky();
	BuildOutpost();
	UE_LOG(LogASTRA, Log, TEXT("[World] %s (%s) built in %.2f s: site (%.0f, %.0f) at %.0f m, sea %s"), *WorldName, *PlanetType,
	       FPlatformTime::Seconds() - T0, Gen->Site.X, Gen->Site.Y, Gen->SiteZ,
	       Gen->SeaLevel > -1.0e5f ? *FString::Printf(TEXT("at %.0f m"), Gen->SeaLevel) : TEXT("none"));
}

void AAstraWorldSurface::BuildGround()
{
	const FAstraWorldGen& G = *Gen;
	// --- the far ground, to the horizon (under the core it drops out of sight: the core's skirts close the gap)
	const int32 NF = int32(2 * FarHalf / FarStep) + 1;
	TArray<float> FarH;
	FarH.SetNumUninitialized(NF * NF);
	ParallelFor(NF, [&](int32 j)
	{
		for (int32 i = 0; i < NF; ++i)
		{
			FarH[j * NF + i] = G.Height(-FarHalf + i * FarStep, -FarHalf + j * FarStep, false);
		}
	});
	// the horizon: the far ground's rim settles to the mean height along it (under the sea on an ocean world, above the
	// lava elsewhere), and a plain at that height runs on beyond it, so the world never ends in a cliff at 45 km
	double RimSum = 0.0;
	for (int32 k = 0; k < NF; ++k)
	{
		RimSum += FarH[k] + FarH[(NF - 1) * NF + k] + FarH[k * NF] + FarH[k * NF + NF - 1];
	}
	HorizonZ = float(RimSum / (4.0 * NF));
	if (G.Kind == EAstraWorldKind::Ocean)
	{
		HorizonZ = FMath::Min(HorizonZ, G.SeaLevel - 30.f);
	}
	else if (G.SeaLevel > -1.0e5f)
	{
		HorizonZ = FMath::Max(HorizonZ, G.SeaLevel + 15.f);
	}
	for (int32 j = 0; j < NF; ++j)
	{
		for (int32 i = 0; i < NF; ++i)
		{
			const double Edge = FarHalf - FMath::Max(FMath::Abs(-FarHalf + i * FarStep), FMath::Abs(-FarHalf + j * FarStep));
			FarH[j * NF + i] = FMath::Lerp(HorizonZ, FarH[j * NF + i], FMath::SmoothStep(0.f, 1.f, float(Edge / EdgeBlend)));
		}
	}
	auto FarAt = [&](double X, double Y)
	{
		const double GX = FMath::Clamp((X + FarHalf) / FarStep, 0.0, NF - 1.001), GY = FMath::Clamp((Y + FarHalf) / FarStep, 0.0, NF - 1.001);
		const int32 X0 = FMath::FloorToInt(GX), Y0 = FMath::FloorToInt(GY);
		const float TX = float(GX - X0), TY = float(GY - Y0);
		return FMath::Lerp(FMath::Lerp(FarH[Y0 * NF + X0], FarH[Y0 * NF + X0 + 1], TX), FMath::Lerp(FarH[(Y0 + 1) * NF + X0], FarH[(Y0 + 1) * NF + X0 + 1], TX), TY);
	};
	// --- the core: detailed, softened by a little thermal erosion, blended into the far ground at its edge
	const int32 NC = int32(2 * CoreHalf / CoreStep) + 1;
	TArray<float> H;
	H.SetNumUninitialized(NC * NC);
	ParallelFor(NC, [&](int32 j)
	{
		for (int32 i = 0; i < NC; ++i)
		{
			H[j * NC + i] = G.Height(-CoreHalf + i * CoreStep, -CoreHalf + j * CoreStep, true);
		}
	});
	TArray<float> Moved;
	Moved.SetNumZeroed(NC * NC);
	for (int32 Iter = 0; Iter < 10; ++Iter)
	{
		FMemory::Memzero(Moved.GetData(), Moved.Num() * sizeof(float));
		for (int32 j = 1; j < NC - 1; ++j)
		{
			for (int32 i = 1; i < NC - 1; ++i)
			{
				const int32 K = j * NC + i;
				for (const int32 N : {K + 1, K - 1, K + NC, K - NC})
				{
					const float Diff = H[K] - H[N] - G.Talus * float(CoreStep);
					if (Diff > 0.f)
					{
						Moved[K] -= Diff * 0.1f;
						Moved[N] += Diff * 0.1f;
					}
				}
			}
		}
		for (int32 K = 0; K < H.Num(); ++K)
		{
			H[K] += Moved[K];
		}
	}
	// the landing pad stays level after the erosion
	for (int32 j = 0; j < NC; ++j)
	{
		for (int32 i = 0; i < NC; ++i)
		{
			const double X = -CoreHalf + i * CoreStep, Y = -CoreHalf + j * CoreStep;
			const float Q = FMath::Max(FMath::Abs(float(X - G.Site.X)), FMath::Abs(float(Y - G.Site.Y))) / G.SiteHalf;
			if (Q < 1.2f)
			{
				H[j * NC + i] = G.SiteZ;
			}
			const double Edge = FMath::Min(CoreHalf - FMath::Abs(X), CoreHalf - FMath::Abs(Y));
			const float W = FMath::SmoothStep(0.f, 1.f, float(Edge / Blend));
			H[j * NC + i] = FMath::Lerp(FarAt(X, Y), H[j * NC + i], W);
		}
	}
	auto NormalAt = [&](const TArray<float>& Hs, int32 N, double Step, int32 i, int32 j)
	{
		const float L = Hs[j * N + FMath::Max(i - 1, 0)], R = Hs[j * N + FMath::Min(i + 1, N - 1)];
		const float D = Hs[FMath::Max(j - 1, 0) * N + i], U = Hs[FMath::Min(j + 1, N - 1) * N + i];
		return FVector(-(R - L) / (2.0 * Step), -(U - D) / (2.0 * Step), 1.0).GetSafeNormal();
	};
	UMaterialInterface* Ground = Mat(FString::Printf(TEXT("MI_W_Terrain_%s"), KindName(G.Kind)));
	// core sections (4 x 4), with skirts along the core's outer edge
	const int32 PerTile = (NC - 1) / CoreTiles;
	int32 Section = 0;
	for (int32 tj = 0; tj < CoreTiles; ++tj)
	{
		for (int32 ti = 0; ti < CoreTiles; ++ti)
		{
			TArray<FVector> V;
			TArray<FVector> Nrm;
			TArray<FVector2D> UV;
			TArray<int32> Tri;
			const int32 I0 = ti * PerTile, J0 = tj * PerTile, NS = PerTile + 1;
			V.Reserve(NS * NS + 4 * NS * 2);
			for (int32 j = 0; j < NS; ++j)
			{
				for (int32 i = 0; i < NS; ++i)
				{
					const int32 GI = I0 + i, GJ = J0 + j;
					const double X = -CoreHalf + GI * CoreStep, Y = -CoreHalf + GJ * CoreStep;
					V.Add(FVector(X, Y, H[GJ * NC + GI] - Drop(X, Y)) * 100.0);
					Nrm.Add(NormalAt(H, NC, CoreStep, GI, GJ));
					UV.Add(FVector2D(X / 100.0, Y / 100.0));
				}
			}
			for (int32 j = 0; j < NS - 1; ++j)
			{
				for (int32 i = 0; i < NS - 1; ++i)
				{
					const int32 A = j * NS + i, B = A + 1, C = A + NS + 1, D = A + NS;
					Tri.Append({A, C, B, A, D, C});
				}
			}
			// skirts where this tile touches the core's outer edge (they hang 40 m, hiding any crack with the far ground)
			auto Skirt = [&](TArray<int32> Edge)
			{
				const int32 Base = V.Num();
				for (const int32 E : Edge)
				{
					// copies first: Add() must not take a reference into the array it may grow
					const FVector P = V[E] - FVector(0, 0, 4000.0), N = Nrm[E];
					const FVector2D T = UV[E];
					V.Add(P);
					Nrm.Add(N);
					UV.Add(T);
				}
				for (int32 k = 0; k + 1 < Edge.Num(); ++k)
				{
					Tri.Append({Edge[k], Base + k, Edge[k + 1], Edge[k + 1], Base + k, Base + k + 1});
					Tri.Append({Edge[k], Edge[k + 1], Base + k, Edge[k + 1], Base + k + 1, Base + k});   // both faces
				}
			};
			TArray<int32> E;
			if (tj == 0) { E.Reset(); for (int32 i = 0; i < NS; ++i) { E.Add(i); } Skirt(E); }
			if (tj == CoreTiles - 1) { E.Reset(); for (int32 i = 0; i < NS; ++i) { E.Add((NS - 1) * NS + i); } Skirt(E); }
			if (ti == 0) { E.Reset(); for (int32 j = 0; j < NS; ++j) { E.Add(j * NS); } Skirt(E); }
			if (ti == CoreTiles - 1) { E.Reset(); for (int32 j = 0; j < NS; ++j) { E.Add(j * NS + NS - 1); } Skirt(E); }
			Core->CreateMeshSection(Section, V, Tri, Nrm, UV, TArray<FColor>(), TangentsFor(Nrm), true);
			if (Ground)
			{
				Core->SetMaterial(Section, Ground);
			}
			++Section;
		}
	}
	// the shadow proxy: the core every other vertex (48 m), a metre and a half down so it never shades the ground it stands for
	{
		const int32 NP = (NC - 1) / 2 + 1;
		TArray<FVector> V, Nrm;
		TArray<FVector2D> UV;
		TArray<int32> Tri;
		V.Reserve(NP * NP);
		for (int32 j = 0; j < NP; ++j)
		{
			for (int32 i = 0; i < NP; ++i)
			{
				const double X = -CoreHalf + i * 2 * CoreStep, Y = -CoreHalf + j * 2 * CoreStep;
				V.Add(FVector(X, Y, H[(j * 2) * NC + i * 2] - 1.5f - Drop(X, Y)) * 100.0);
				Nrm.Add(FVector::UpVector);
				UV.Add(FVector2D::ZeroVector);
			}
		}
		for (int32 j = 0; j < NP - 1; ++j)
		{
			for (int32 i = 0; i < NP - 1; ++i)
			{
				const int32 A = j * NP + i;
				Tri.Append({A, A + NP + 1, A + 1, A, A + NP, A + NP + 1});
			}
		}
		ShadowProxy->CreateMeshSection(0, V, Tri, Nrm, UV, TArray<FColor>(), TArray<FProcMeshTangent>(), false);
		if (Ground)
		{
			ShadowProxy->SetMaterial(0, Ground);
		}
	}
	// the far ground (one section), dropped 25 m under the core
	{
		TArray<FVector> V;
		TArray<FVector> Nrm;
		TArray<FVector2D> UV;
		TArray<int32> Tri;
		for (int32 j = 0; j < NF; ++j)
		{
			for (int32 i = 0; i < NF; ++i)
			{
				const double X = -FarHalf + i * FarStep, Y = -FarHalf + j * FarStep;
				const bool bUnder = FMath::Abs(X) < CoreHalf - 50.0 && FMath::Abs(Y) < CoreHalf - 50.0;
				V.Add(FVector(X, Y, FarH[j * NF + i] - (bUnder ? 25.f : 0.f) - Drop(X, Y)) * 100.0);
				Nrm.Add((NormalAt(FarH, NF, FarStep, i, j) + CurvedUp(X, Y) - FVector::UpVector).GetSafeNormal());
				UV.Add(FVector2D(X / 100.0, Y / 100.0));
			}
		}
		for (int32 j = 0; j < NF - 1; ++j)
		{
			for (int32 i = 0; i < NF - 1; ++i)
			{
				const int32 A = j * NF + i;
				Tri.Append({A, A + NF + 1, A + 1, A, A + NF, A + NF + 1});
			}
		}
		Far->CreateMeshSection(0, V, Tri, Nrm, UV, TArray<FColor>(), TangentsFor(Nrm), true);
		if (Ground)
		{
			Far->SetMaterial(0, Ground);
		}
	}
	// the horizon: rings of ground beyond the far ground, curving away with the planet (dry worlds; the sea is the
	// horizon of an ocean world); no collision, nothing flies that low out there
	if (G.Kind != EAstraWorldKind::Ocean)
	{
		TArray<FVector> V, Nrm;
		TArray<FVector2D> UV;
		TArray<int32> Tri;
		AddRings(V, Nrm, UV, Tri, HorizonZ, NF - 1);
		Far->CreateMeshSection(1, V, Tri, Nrm, UV, TArray<FColor>(), TangentsFor(Nrm), false);
		if (Ground)
		{
			Far->SetMaterial(1, Ground);
		}
	}
	// the sea (water, or lava in the low ground; none on dry and frozen worlds): a grid over the far ground's square,
	// curving like the land, and on an ocean world the rings beyond it to the horizon
	if (G.SeaLevel > -1.0e5f)
	{
		constexpr double SeaStep = 1500.0;
		const int32 NS = int32(2 * FarHalf / SeaStep) + 1;
		TArray<FVector> V, Nrm;
		TArray<FVector2D> UV;
		TArray<int32> Tri;
		for (int32 j = 0; j < NS; ++j)
		{
			for (int32 i = 0; i < NS; ++i)
			{
				const double X = -FarHalf + i * SeaStep, Y = -FarHalf + j * SeaStep;
				V.Add(FVector(X, Y, G.SeaLevel - Drop(X, Y)) * 100.0);
				Nrm.Add(CurvedUp(X, Y));
				UV.Add(FVector2D(X / 100.0, Y / 100.0));
			}
		}
		for (int32 j = 0; j < NS - 1; ++j)
		{
			for (int32 i = 0; i < NS - 1; ++i)
			{
				const int32 A = j * NS + i;
				Tri.Append({A, A + NS + 1, A + 1, A, A + NS, A + NS + 1});
			}
		}
		if (G.Kind == EAstraWorldKind::Ocean)
		{
			AddRings(V, Nrm, UV, Tri, G.SeaLevel, NS - 1);
		}
		Sea->CreateMeshSection(0, V, Tri, Nrm, UV, TArray<FColor>(), TangentsFor(Nrm), true);
		Sea->SetMaterial(0, Mat(G.Kind == EAstraWorldKind::Lava ? TEXT("MI_W_Lava") : TEXT("MI_NR_Ocean")));
	}
	else
	{
		Sea->SetVisibility(false);
		Sea->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	}
}

void AAstraWorldSurface::BuildSky()
{
	const EAstraWorldKind K = Gen->Kind;
	// the air: Earth-like over the sea, thin and blue on ice, dusty on sand, almost none on a dead rock, ash over lava
	Atmosphere->TransformMode = ESkyAtmosphereTransformMode::PlanetTopAtComponentTransform;
	Atmosphere->BottomRadius = 6000.f;
	Atmosphere->AtmosphereHeight = K == EAstraWorldKind::Barren ? 40.f : 100.f;
	float Rayleigh = 0.0331f, Mie = 0.003996f, MieAbs = 0.000444f;
	FLinearColor MieCol(0.577f, 0.577f, 0.577f), Ray(0.175287f, 0.409607f, 1.f);
	FLinearColor FogCol(0.35f, 0.5f, 0.75f);
	float FogDensity = 0.0012f;
	bool bClouds = true;
	switch (K)
	{
	case EAstraWorldKind::Desert:
		Rayleigh = 0.02f; Mie = 0.012f; MieCol = FLinearColor(0.95f, 0.72f, 0.5f); FogCol = FLinearColor(0.75f, 0.6f, 0.45f); FogDensity = 0.0016f; bClouds = false;
		break;
	case EAstraWorldKind::Ice:
		Rayleigh = 0.045f; Mie = 0.002f; FogCol = FLinearColor(0.6f, 0.72f, 0.9f); FogDensity = 0.0009f;
		break;
	case EAstraWorldKind::Barren:
		Rayleigh = 0.0015f; Mie = 0.0003f; FogDensity = 0.f; bClouds = false;
		break;
	case EAstraWorldKind::Lava:
		Rayleigh = 0.012f; Mie = 0.02f; MieAbs = 0.006f; MieCol = FLinearColor(0.6f, 0.35f, 0.25f); FogCol = FLinearColor(0.3f, 0.18f, 0.12f); FogDensity = 0.003f;
		break;
	default:
		break;
	}
	Atmosphere->SetRayleighScatteringScale(Rayleigh);
	Atmosphere->SetRayleighScattering(Ray);
	Atmosphere->SetMieScatteringScale(Mie);
	Atmosphere->SetMieScattering(MieCol);
	Atmosphere->SetMieAbsorptionScale(MieAbs);
	Fog->SetFogDensity(FogDensity);
	Fog->SetFogHeightFalloff(0.12f);
	Fog->SetFogInscatteringColor(FogCol);
	Fog->SetVisibility(FogDensity > 0.f);
	if (bClouds)
	{
		Clouds->SetLayerBottomAltitude(K == EAstraWorldKind::Lava ? 3.0f : 2.0f);
		Clouds->SetLayerHeight(K == EAstraWorldKind::Ice ? 3.0f : 6.0f);
		Clouds->SetViewSampleCountScale(0.5f);   // half the samples: TSR smooths the rest, and it saves ~2 ms
		Clouds->SetShadowViewSampleCountScale(0.5f);
		Clouds->SetReflectionViewSampleCountScale(0.5f);
		if (UMaterialInterface* CM = LoadObject<UMaterialInterface>(nullptr, TEXT("/Engine/EngineSky/VolumetricClouds/m_SimpleVolumetricCloud_Inst.m_SimpleVolumetricCloud_Inst")))
		{
			Clouds->SetMaterial(CM);
		}
	}
	else
	{
		Clouds->SetVisibility(false);
	}
	SkyLight->SetIntensity(K == EAstraWorldKind::Barren ? 0.3f : 1.f);
}

void AAstraWorldSurface::BuildOutpost()
{
	// a pad, a shed and a mast with a beacon, reusing Port Aurelius's pieces (built by tools/ue_scripts/build_newravenna.py)
	const FVector Site(Gen->Site.X * 100.0, Gen->Site.Y * 100.0, Gen->SiteZ * 100.0);
	struct FPiece { const TCHAR* Mesh; FVector Offset; float Yaw; FVector Scale; };
	const FPiece Pieces[] = {
		{TEXT("SM_NR_Pad"), FVector(0, 0, 0), 0.f, FVector(1.f)},
		{TEXT("SM_NR_Hangar"), FVector(-9000, 7000, 0), 90.f, FVector(0.6f)},
		{TEXT("SM_NR_Tower"), FVector(8000, 8000, 0), -90.f, FVector(0.55f)}};
	for (const FPiece& P : Pieces)
	{
		UStaticMesh* M = LoadObject<UStaticMesh>(nullptr, *FString::Printf(TEXT("/Game/ASTRA/Planet/NewRavenna/Port/%s.%s"), P.Mesh, P.Mesh));
		if (!M)
		{
			continue;
		}
		UStaticMeshComponent* C = NewObject<UStaticMeshComponent>(this);
		C->SetMobility(EComponentMobility::Static);
		C->SetStaticMesh(M);
		C->SetupAttachment(Root);
		C->SetRelativeLocation(Site + P.Offset);
		C->SetRelativeRotation(FRotator(0.f, P.Yaw, 0.f));
		C->SetRelativeScale3D(P.Scale);
		C->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
		C->RegisterComponent();
		Outpost.Add(C);
	}
	Beacon->SetRelativeLocation(Site + FVector(8000, 8000, 3600));
	Beacon->SetIntensity(Owner == TEXT("silent") ? 0.f : 60000.f);   // a world gone silent shows no light
	Beacon->SetAttenuationRadius(6000.f);
	Beacon->SetLightColor(FLinearColor(1.f, 0.3f, 0.2f));
}

void AAstraWorldSurface::Show(bool bShow)
{
	SetActorHiddenInGame(!bShow);
	for (UActorComponent* C : GetComponents())
	{
		if (USceneComponent* S = Cast<USceneComponent>(C))
		{
			const bool bOptionalOff = (S == Sea && Gen && Gen->SeaLevel < -1.0e5f) || (S == Fog && Fog->FogDensity <= 0.f)
			                        || (S == Clouds && Gen && (Gen->Kind == EAstraWorldKind::Desert || Gen->Kind == EAstraWorldKind::Barren));
			S->SetVisibility(bShow && !bOptionalOff);
		}
	}
	Core->SetCollisionEnabled(bShow ? ECollisionEnabled::QueryOnly : ECollisionEnabled::NoCollision);
	Far->SetCollisionEnabled(bShow ? ECollisionEnabled::QueryOnly : ECollisionEnabled::NoCollision);
	Sea->SetCollisionEnabled(bShow && Gen && Gen->SeaLevel > -1.0e5f ? ECollisionEnabled::QueryOnly : ECollisionEnabled::NoCollision);
	if (bShow)
	{
		SkyLight->RecaptureSky();
	}
}

FVector AAstraWorldSurface::SiteWorld() const
{
	return Gen ? GetActorTransform().TransformPosition(FVector(Gen->Site.X * 100.0, Gen->Site.Y * 100.0, Gen->SiteZ * 100.0)) : GetActorLocation();
}

float AAstraWorldSurface::SeaWorldZ() const
{
	return Gen && Gen->SeaLevel > -1.0e5f ? float(GetActorLocation().Z + Gen->SeaLevel * 100.0) : -1.0e12f;
}

FString AAstraWorldSurface::SiteName() const
{
	return Owner == TEXT("silent") ? FString::Printf(TEXT("the dark landing field on %s"), *WorldName)
	                               : FString::Printf(TEXT("the landing field on %s"), *WorldName);
}
