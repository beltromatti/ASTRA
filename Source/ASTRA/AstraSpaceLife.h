// ASTRA — the living space of a system, in the game (SPAZIO-VIVO, docs/SPAZIO.md): the places of the system as the plot's own contacts (Keeper Station, the Arsenal, the
// refineries of Tiberius), the civilian traffic that flies between them (AstraSpaceLifeTraffic.*), the Ceres Belt and the route buoys, what the war leaves behind
// (AstraWrecks.*), and the drawing of all of it as instances, so that the cost grows with what is seen and not with what there is.
//
// Owned by the battle subsystem like the war's effects (UAstraWarFX) and the instanced craft (UAstraWarDraw): it reads the battle's state (where the Aquila is, who is
// hostile, where the Gate stands), calls the battle's hooks for the little it must put in the plot, and is called by the battle's named hooks (Tick, ClearSystem, a
// system entered, a ship's end). It never changes the rules of the war: places are fixtures nobody fights over, traffic is not in the plot at all.
//
// Console: astra.space.stat / where / look <place> [km] / density <x> / skip <s> / alert / reload. Cvars: astra.space.enable, astra.space.draw, astra.space.density,
// astra.space.rocks.

#pragma once

#include "CoreMinimal.h"
#include "UObject/Object.h"
#include "Dom/JsonObject.h"
#include "AstraSpaceLifeData.h"
#include "AstraSpaceLifeTraffic.h"
#include "AstraWarFX.h"
#include "AstraWarDraw.h"
#include "AstraSpaceLife.generated.h"

class AActor;
class AStaticMeshActor;
class UAstraBattleSubsystem;
class UInstancedStaticMeshComponent;
class UMaterialInterface;
class USceneComponent;
class UStaticMesh;
class UStaticMeshComponent;
struct FAstraBattleShip;

namespace AstraSpaceDraw
{
	constexpr int32 CapLamps = 3200;               // lamps in the one layer of them
	constexpr int32 CapPlumes = 200;
	constexpr int32 CapGlints = 400;
	constexpr int32 PageSize = AstraDraw::PageSize;   // instances in one component of a hull layer (a busier system grows another page)

	/** The instances of one mesh whose objects keep their slots (the temporal upscaler needs true motion vectors for a hull that moves): a key (a vessel's id) holds its
	 *  slot while it is drawn. The same pages as the war's craft (AstraDraw::FSet): one instanced component per page. */
	struct FInstSet
	{
		FString Mesh;
		TObjectPtr<UStaticMesh> StaticMesh;
		AstraDraw::FSet Set;
		TMap<int32, AstraDraw::FRef> Where;                  // key -> where it is among the pages
		bool bFailed = false;                                // its mesh did not load (or its materials are not flagged for instancing): it is not drawn
	};
}

/** A place of the system that stands in the plot: its fixture ship in the battle, its actor and what turns on it. */
struct FSpaceLifePlace
{
	FName Id;
	int32 Node = INDEX_NONE;                        // in the layout
	int32 ShipId = -1;                              // its fixture in the battle's plot (-1: none: an orbit, a belt)
	TWeakObjectPtr<AStaticMeshActor> Actor;
	struct FTurning
	{
		TWeakObjectPtr<UStaticMeshComponent> Comp;
		AstraSpace::FPart Def;
	};
	TArray<FTurning> Parts;
};

UCLASS()
class ASTRA_API UAstraSpaceLife : public UObject
{
	GENERATED_BODY()

public:
	/** Set up for this world (the battle's OnWorldBeginPlay): finds the assets, makes the instance layers. Nothing is in the sky yet: Arrive does that. */
	void Init(UAstraBattleSubsystem* InOwner);
	/** On: not switched off (astra.space.enable), the data is in, and it is not a bench world that did not ask for it. */
	bool IsActive() const;
	/** Once a frame, after the ships have moved (SimDt: the battle's step, scaled by its time control; RealDt: real seconds, for the lamps). */
	void Tick(float SimDt, float RealDt);
	/** The Aquila comes into a system (a new campaign, a resumed one, the far side of a Janus transit): its places, its traffic, its belt are made once the sky is known. */
	void Arrive(const FString& SystemName);
	/** The system is left behind (ClearSystem has taken the plot's ships and the Gate): everything of it goes. */
	void Leave();

	// ---- what the rest of the game may ask
	/** A short account for the console and the bench. */
	FString Stat() const;
	FString WhereText() const;
	/** The facts for the crew (ship_state.state.space): the places with bearing and range, the traffic at a glance, the alert, the wrecks. Small on purpose. */
	TSharedRef<FJsonObject> SummaryJson() const;
	/** The system's traffic as the bench reads it. */
	TSharedRef<FJsonObject> BenchJson() const;
	/** The Aquila to a place: heading for it, `Km` out on the side she is on (the console's astra.space.look). False when there is no such place. */
	bool LookAt(const FString& Key, double Km, FString& OutDetail);
	/** Runs the traffic ahead (seconds). */
	void Skip(double Seconds);
	/** A hostile set by hand for the console's alert test (positions in the system frame): clears when empty. */
	void SetTestHostile(bool bOn, const FVector& Pos);

	const AstraSpace::FLayout& GetLayout() const { return Layout; }
	const AstraSpace::FTraffic& GetTraffic() const { return Traffic; }
	const FString& GetSystem() const { return SystemName; }
	bool IsLaidOut() const { return bLaidOut; }

private:
	friend struct FAstraSpaceTest;

	UPROPERTY() TObjectPtr<UAstraBattleSubsystem> Owner;
	UPROPERTY() TObjectPtr<AActor> Host;
	UPROPERTY() TObjectPtr<USceneComponent> SystemRoot;          // what is still in the system frame (the rocks, the buoys) hangs under it: one transform a frame moves them all
	UPROPERTY() TObjectPtr<UStaticMesh> SphereMesh;
	UPROPERTY() TObjectPtr<UStaticMesh> CylinderMesh;
	UPROPERTY() TObjectPtr<UMaterialInterface> MatGlow;
	UPROPERTY() TObjectPtr<UMaterialInterface> MatPlume;
	UPROPERTY() TArray<TObjectPtr<UStaticMesh>> KeepMeshes;
	TArray<FSpaceLifePlace> Places;

	bool bLive = false;                           // the game draws (assets found)
	bool bSim = false;                            // the bench: staged and counted, not drawn
	bool bInitDone = false;
	bool bPending = false;                        // an arrival waits for the sky
	FString PendingSystem;
	FString SystemName;
	bool bLaidOut = false;
	uint32 Seed = 1;

	AstraSpace::FLayout Layout;
	AstraSpace::FTraffic Traffic;
	TArray<AstraSpace::FEvent> Events;
	bool bTestHostile = false;
	FVector TestHostile = FVector::ZeroVector;
	float EventAcc = 0.f;
	double HostileScanT = 0.0;
	AstraSpace::FWorldView View;

	// ---- the frame (set at the start of each Tick)
	struct FFrame
	{
		FVector Origin = FVector::ZeroVector;
		FQuat InvAtt = FQuat::Identity;
		FVector Bridge = FVector::ZeroVector;
		FVector ToWorld(const FVector& P) const { return (InvAtt.RotateVector(P - Origin) - Bridge) * 100.0; }
		FQuat ToWorldRot(const FQuat& Q) const { FQuat R = InvAtt * Q; R.Normalize(); return R; }
	} F;
	float Dt = 0.f;
	float Clock = 0.f;                            // the lamps' own time (real seconds)
	uint32 Frame = 0;
	float LampGain = 1.f;

	// ---- the layers: lamps, plumes and glints are written afresh every frame; hulls keep their slots
	AstraFx::FLayer Lamps, Plumes, Glints;
	TArray<AstraSpaceDraw::FInstSet> Sets;
	TMap<FString, int32> SetByMesh;
	TMap<FString, TArray<AstraSpace::FLamp>> NavLampCache;       // the ships' own lamp tables (data/ship/nav_lights.json) in this module's units, by mesh
	struct FRigid
	{
		FString Mesh;
		TWeakObjectPtr<UInstancedStaticMeshComponent> Comp;
		int32 Count = 0;
	};
	TArray<FRigid> Rigids;                        // groups static in the system frame (rocks, buoys), under SystemRoot
	int32 BuoyRigid = INDEX_NONE;

	// ---- cost
	double TickMs = 0.0, TickMsMax = 0.0;
	int32 TickCount = 0;
	int32 HullsNow = 0, HullsPeak = 0, LampsNow = 0, LampsPeak = 0, LampsDropped = 0, PlumesNow = 0;
	double TrafficMs = 0.0, DrawMs = 0.0;

	// ---- internals (AstraSpaceLife.cpp)
	bool LoadAssets();
	void MakeLayer(AstraFx::FLayer& L, const TCHAR* Name, UStaticMesh* Mesh, UMaterialInterface* Mat, int32 Capacity, int32 Sort);
	void DoArrive(const FString& SystemName);
	void ClearScene();
	void MakePlaces();
	void MakeRocksAndBuoys();
	void ReadWorld();
	void FlushEvents();
	AstraSpace::FAnchors ReadAnchors() const;
	FAstraBattleShip* ShipOfPlace(const FSpaceLifePlace& P) const;
	// ---- drawing (AstraSpaceLifeDraw.cpp)
	int32 SetFor(const FString& Mesh);
	AstraDraw::FPage* MakePage(int32 SetIdx);
	void StageHull(int32 SetIdx, int32 Key, const FTransform& Now);
	void FlushSets();
	void HideSets();
	void DrawPlaces();
	void DrawVessels();
	void DrawPatrols();
	void DrawLamps(const TArray<AstraSpace::FLamp>& Set, const FVector& Pos, const FQuat& Att, uint32 Hash, double Dist2, float Fade, bool bShipLamps);
	void AddPlume(const FVector& Lip, const FVector& Dir, float RadiusM, float Thrust, bool bAmber, float Salt);
	int32 RigidFor(const FString& Mesh);
};
