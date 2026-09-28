// ASTRA — the ground of any world, from its name and its kind: an infinite, seeded universe needs no hand-made
// terrain. Pure functions (no engine objects): the height of the ground in metres at any point of a world's landing
// zone, the level of its sea (water, lava or ice), and where a ship can set down.

#pragma once

#include "CoreMinimal.h"

enum class EAstraWorldKind : uint8
{
	Ocean,     // islands in a sea
	Desert,    // mesas and buttes, dune seas, a canyon
	Ice,       // an ice sheet, pressure ridges, nunataks, mountains inland, a frozen sea
	Barren,    // craters of every size, highlands, no air to speak of
	Lava       // basalt plains, volcanic cones, lava in the channels and the low ground
};

struct ASTRA_API FAstraWorldGen
{
	FAstraWorldGen(const FString& WorldName, EAstraWorldKind InKind);

	static EAstraWorldKind KindFromPlanetType(const FString& PlanetType);   // "ocean", "desert", "ice", "lava", "barren"
	static bool HasSurface(const FString& PlanetType);                      // not a gas giant

	EAstraWorldKind Kind;
	uint32 Seed = 0;
	/** The sea (water, or lava in the low ground) is at this height (m); -1e6 when there is none. */
	float SeaLevel = -1.0e6f;
	/** Where ships set down (m, zone frame): a flat pad the generator levels, and its height. */
	FVector2D Site = FVector2D::ZeroVector;
	float SiteZ = 0.f;
	float SiteHalf = 180.f;
	/** The steepest slope (rise over run) the ground keeps after weathering: sheer on mesas, gentle on grassland. */
	float Talus = 0.9f;

	/** The ground at (x, y) metres. bDetail = false: the far terrain's gentler surface. */
	float Height(double X, double Y, bool bDetail = true) const;

private:
	/** Chooses and levels the landing site near the zone's origin (the constructor calls it). */
	void PlaceSite();

	float Noise(double X, double Y) const;          // value noise, 0..1
	float Fbm(double X, double Y, int32 Octaves) const;
	float Ridged(double X, double Y, int32 Octaves) const;
	float Raw(double X, double Y, bool bDetail) const;
	float CraterSum(double X, double Y) const;

	TArray<FVector4f> Craters;                     // x, y, radius, depth (airless worlds)
	TArray<TArray<int32>> CraterCells;             // the craters that reach each cell of a coarse grid
	TArray<FVector4f> Cones;                       // x, y, radius, height (volcanic worlds)
};
