// ASTRA — the war's ships and craft drawn as instances (F2.3, "la scala": docs/SCALA.md).
//
// A fleet of thirty capital ships and a hundred and fifty fighters, bombers and drones used to be a hundred and eighty actors, each with its
// mesh, its running-light component and the three to five lamps (a component, a dynamic material and a tick each), moved every frame:
// the game thread's end-of-frame updates and the render thread's primitive updates scaled with the number of things in the sky, not with
// what was seen. Here the craft are instances of a few meshes (one instanced component per kind of hull; stable slots, so that the
// temporal upscaler gets true motion vectors) and every ship's lamps, craft and capital ships alike, are instances of the war's glow
// (M_WAR_Glow, the layer of AstraWarFX's own: colour, strength and size per instance). The capital ships' hulls stay actors: there are few of
// them, and the effects take their meshes over (the break-up pieces, the lights going out, the scars).
//
// Levels of detail by distance from the Aquila (the same everywhere, nothing pops: strengths fade over a band): a craft's hull is drawn out to
// the range where it is still a speck of a pixel; its lamps thin out with the distance (port and starboard first, then the strobe); a
// capital ship keeps its lamps to the edge of the system.
//
// Like the effects it is plain C++ in the system frame (metres) and writes the instances in the Aquila's frame once a frame; on the bench
// (-nullrhi) it stages and counts without drawing, so its cost is part of the war's (tools/war.py).

#pragma once

#include "CoreMinimal.h"
#include "UObject/Object.h"
#include "AstraNavLights.h"
#include "AstraWarFX.h"
#include "AstraWarDraw.generated.h"

class AActor;
class UAstraBattleSubsystem;
class UInstancedStaticMeshComponent;
class UMaterialInterface;
class UPrimitiveComponent;
class UStaticMesh;
struct FAstraBattleShip;

namespace AstraDraw
{
	constexpr int32 PageSize = 96;          // instances in one component of a hull layer (a bigger battle grows more pages)
	constexpr int32 CapLamps = 1400;        // lamps in the one layer of them

	/** One instanced component of a hull layer: stable slots (a craft keeps its slot while it flies, so the upscaler's motion vectors are true). */
	struct FPage
	{
		TWeakObjectPtr<UInstancedStaticMeshComponent> Comp;     // (empty on the bench: staged and counted, not drawn)
		TArray<FTransform> Xf;                                  // PageSize
		TArray<int32> Owner;                                    // the ship id in each slot (-1 free)
		int32 High = 0;                                         // 1 + the highest slot in use: what is written
		int32 Live = 0;
		bool bWritten = false;                                  // the last flush left live instances (an empty page is written once, hidden, and then let be)
	};

	/** All the pages of one set of one kind of hull. Set 1 holds our own craft that the main viewscreen's camera must not see (they cross its lens). */
	struct FSet
	{
		TArray<FPage> Pages;
		TArray<int32> FreeSlots;                                // slots given back (page * PageSize + i)
		int32 NextSlot = 0;                                     // the next never-used slot
		int32 Live = 0, Peak = 0;
	};

	/** A kind of craft hull: its mesh and its two sets of pages. */
	struct FKind
	{
		FString Mesh;
		TObjectPtr<UStaticMesh> StaticMesh;
		FSet Sets[2];
		bool bFailed = false;                                   // its mesh did not load: its craft are drawn as actors
	};

	/** Where a ship's hull is among the instances. */
	struct FRef
	{
		int16 Kind = -1;
		uint8 Set = 0;
		int32 Slot = -1;
		uint32 Frame = 0;                                       // the last frame it was staged: a ship not staged is gone
	};
}

/**
 * The instanced drawing of the war's hulls (craft) and lamps (every ship's running lights). Owned by the battle subsystem, which asks it to claim a
 * craft as it is born (no actor is made for one it claims) and ticks it once a frame after the ships have moved.
 */
UCLASS()
class ASTRA_API UAstraWarDraw : public UObject
{
	GENERATED_BODY()

public:
	void Init(UAstraBattleSubsystem* InOwner);
	/** Instanced drawing is on (the assets are in, or it is the bench) and not switched off (astra.war.draw 0). */
	bool IsActive() const;
	/** The materials were found and the game draws. */
	bool IsLive() const { return bLive; }
	/** Makes the kinds of hull the Aquila's craft and the Mandate's wings use ready (the battle starts: no stall when the first wing launches). */
	void Prewarm();
	/** A ship is born (SpawnVisual). True: its hull is drawn here (craft) and it needs no actor. Either way its lamps may be ours
	 *  (S.bDrawLamps): then it must not be given a running-light component. */
	bool Claim(FAstraBattleShip& S);
	/** Once a frame, after the ships and the shots have moved (Dt: real seconds). */
	void Tick(float Dt);
	/** Everything goes (a transit, a new system). */
	void ClearAll();

	/** The main viewscreen's camera is zoomed far out on a target: our own craft nearer than this (km) to the Aquila would cross its lens as huge blurred
	 *  shapes, so they are drawn in a set the camera is told to leave out (GetNearLensComponents). The craft ExemptId (the one it shows) is not. */
	void SetLensHint(bool bActive, double WithinKm, int32 ExemptId);
	void GetNearLensComponents(TArray<UPrimitiveComponent*>& Out) const;

	/** What it holds and what it costs (astra.war.stat), and the same as JSON for the bench's record. */
	void Stats(FString& Out) const;
	TSharedRef<class FJsonObject> StatsJson() const;

private:
	friend class UAstraBattleSubsystem;

	UPROPERTY() TObjectPtr<UAstraBattleSubsystem> Owner;
	UPROPERTY() TObjectPtr<AActor> Host;
	UPROPERTY() TObjectPtr<UStaticMesh> SphereMesh;
	UPROPERTY() TObjectPtr<UMaterialInterface> MatGlow;
	UPROPERTY() TArray<TObjectPtr<UStaticMesh>> Meshes;       // what the kinds point at (kept alive)

	bool bLive = false;                  // the game draws
	bool bSim = false;                   // the bench: staged and counted, not drawn
	bool bInitDone = false;

	TArray<AstraDraw::FKind> Kinds;
	TMap<FString, int32> KindByMesh;
	TMap<int32, AstraDraw::FRef> Where;                      // ship id -> its hull's place
	AstraFx::FLayer Lamps;                                   // every ship's lamps: packed afresh each frame (additive glows: no motion vectors to keep)
	TArray<TArray<FAstraNavLamp>> LampSets;                  // by (mesh, side)
	TMap<FString, int32> LampSetByKey;

	// ---- the lens hint (the main viewscreen)
	bool bLens = false;
	double LensKm = 0.0;
	int32 LensExempt = -1;

	// ---- the frame
	struct FFrame
	{
		FVector Origin = FVector::ZeroVector;       // the Aquila, system frame
		FQuat InvAtt = FQuat::Identity;
		FVector Bridge = FVector::ZeroVector;       // the bridge in the hull frame (m)
		FVector ToWorld(const FVector& P) const { return (InvAtt.RotateVector(P - Origin) - Bridge) * 100.0; }
		FQuat ToWorldRot(const FQuat& Q) const { FQuat R = InvAtt * Q; R.Normalize(); return R; }
	} F;
	float Dt = 0.f;
	float Clock = 0.f;                   // the lamps' own time (real seconds)
	uint32 Frame = 0;
	float LampGain = 1.f;                // astra.war.lamps (× astra.fx.intensity)
	double HullKm2 = 0.0;                // the range beyond which a craft's hull is not drawn (squared, in km²)
	double CraftLampKm = 0.0;

	// ---- what it costs and what it holds
	double TickMs = 0.0, TickMsMax = 0.0;
	int32 TickCount = 0;
	int32 Hulls = 0, HullsPeak = 0, LampsNow = 0, LampsPeak = 0, LampsDropped = 0;
	int32 NearNow = 0;
	int32 LegacyActors = 0, LegacyComps = 0, LegacyActorsPeak = 0, LegacyCompsPeak = 0;   // what the actor path would have made of the same ships (the bench's "before")

	// ---- internals (AstraWarDraw.cpp)
	bool LoadAssets();
	int32 KindFor(const FString& Mesh);
	int32 LampSetFor(const FAstraBattleShip& S);
	AstraDraw::FPage* MakePage(int32 KindIdx, int32 SetIdx);
	void StageHull(FAstraBattleShip& S, double Dist2);
	void StageLamps(const FAstraBattleShip& S, double Dist2);
	bool Alloc(int32 KindIdx, int32 SetIdx, int32 ShipId, AstraDraw::FRef& OutRef);
	void Release(const AstraDraw::FRef& R);
	void Sweep();
	void Flush();
	void HideAll();
};
