// ASTRA — the living space of a system, in the game (SPAZIO-VIVO, docs/SPAZIO.md): the places of the system as the plot's own contacts (Keeper Station, the Arsenal, the
// refineries of Tiberius), the civilian traffic that flies between them (AstraSpaceLifeTraffic.*), the Ceres Belt and the route buoys, what the war leaves behind
// (AstraWrecks.*), the motion of the capital ships made readable (manoeuvring jets and engine wakes: AstraSpaceLifeMotion.*), and the drawing of all of it as instances, so that the cost
// grows with what is seen and not with what there is.
//
// Owned by the battle subsystem like the war's effects (UAstraWarFX) and the instanced craft (UAstraWarDraw): it reads the battle's state (where the Aquila is, who is
// hostile, where the Gate stands), calls the battle's hooks for the little it must put in the plot, and is called by the battle's named hooks (Tick, ClearSystem, a
// system entered, a ship's end). It never changes the rules of the war: places are fixtures nobody fights over, traffic is not in the plot at all.
//
// Console: astra.space.stat / where / look <place> [km] / density <x> / skip <s> / alert / reload / lose / jets. Cvars: astra.space.enable, astra.space.draw, astra.space.density,
// astra.space.rocks, astra.space.motion, astra.space.jets.gain, astra.space.wakes, astra.space.wakes.gain.

#pragma once

#include "CoreMinimal.h"
#include "UObject/Object.h"
#include "Dom/JsonObject.h"
#include "AstraSpaceLifeData.h"
#include "AstraSpaceLifeTraffic.h"
#include "AstraSpaceLifeMotion.h"
#include "AstraWrecks.h"
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
struct FAstraDeathEvent;

namespace AstraSpaceDraw
{
	constexpr int32 CapLamps = 3200;               // lamps in the one layer of them
	constexpr int32 CapPlumes = 200;
	constexpr int32 CapGlints = 400;
	constexpr int32 CapJets = 192;                  // manoeuvring jets (a plume each; their glows are lamps)
	constexpr int32 CapWake = 640;                  // pieces of engine wakes
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
		uint8 Variant = 0;                                   // 0 as made; 1 a wreck's (dark windows, cold cut faces, no running lights); 2 charred by a reactor breach too
		bool bRooted = false;                                // its pages hang under the system's frame (transforms in the system frame, moved by one transform a frame): what drifts slowly, not what flies
		TArray<uint8> Dirty;                                 // by page: something in it moved, came or went since it was last sent (a page nothing touched is not sent again)
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

	// ---- what the war leaves (AstraSpaceLifeWrecks.cpp; the records and their rules: AstraWrecks.h)
	/** A ship is lost (the battle's Destroy, after the effects have drawn her): her site is recorded in the Gate's frame, with her pieces, her field of debris, her lifepods and what was left aboard.
	 *  bFxPieces: the effects made her pieces (they burn them as actors for a minute, then this module draws them). */
	void OnShipLost(const FAstraBattleShip& S, const FAstraDeathEvent& E, bool bFxPieces);
	/** The sites of every system visited: ABBORDAGGI and FLOTTA-VIVA read a wreck's class, her id, her pieces and what was left aboard from here. */
	const AstraSpace::FWrecks& GetWrecks() const { return Wrecks; }
	/** The wrecks' clock (s): the battle's, kept running through a save and a transit. */
	double WreckClock() const;
	/** The frame the sites are kept in for this system (its Janus Gate's). */
	AstraSpace::FSkyFrame SkyFrame() const;
	/** The campaign's save of the sites (the battle's SaveJson) and their return (its ResumeFrom, before the system is laid out); a new campaign starts with none. */
	TSharedRef<FJsonObject> SaveJson();
	void LoadSaved(const TSharedPtr<FJsonObject>& J);
	void NewCampaign();
	/** Time passes with the Aquila elsewhere or at rest (a campaign's jump of hours): the wrecks drift on, the lifepods' air goes. */
	void AdvanceWrecks(double Seconds);
	/** A rescue order (the flight network's sar mission): the beacon a craft should fly to (the Rank-th nearest the Aquila hears, so each craft of a flight has its own), where it is and how it moves;
	 *  false when none calls. */
	bool RescueGoal(int32 Rank, FVector& OutPos, FVector& OutVel, FString& OutOf, int32& OutSurvivors) const;
	/** Takes aboard the lifepods within RadiusM of a point (a craft that has reached its beacon); By: who ("the Wasps of the Aquila"). Tells the crew what was taken. */
	AstraSpace::FRescued RescueTake(const FVector& At, double RadiusM, const FString& By);
	/** Some beacon calls within the Aquila's hearing: a rescue order has someone to look for. */
	bool HasBeacons() const;
	/** Testing: loses a warship the way the war would (astra.space.lose): by contact id or "nearest"; How breakup|reactor|destroyed; Section the one that lets go (0 bow, 1 mid, 2 stern). */
	bool DebugLose(const FString& Which, const FString& How, int32 Section, FString& OutDetail);
	/** What the war has left, in a line: the sites, the lifepods, what is drawn and what it costs. */
	FString WreckStat() const;
	/** Testing: a real resume of the campaign from the battle's own save (the plot is cleared, the Gate stands in a new place, the system is laid out afresh); once it is, the log says whether every
	 *  wreck is where it was relative to the Gate (astra.space.wrecks.resume). */
	bool DebugResume(FString& OutDetail);
	/** Writes a wreck site as the records place it AfterS seconds after she went (SiteId 0: the first with pieces here): her pieces, chunks, lifepods, relative to her middle, in the sky frame's axes
	 *  (the Unreal frame, metres): what art/blender/space3_wreck_scene.py renders (astra.space.wrecks.dump). */
	bool DebugDump(const FString& Path, int32 SiteId, double AfterS, FString& OutDetail);

	// ---- the motion of the capital ships (AstraSpaceLifeMotionDraw.cpp; the rules: AstraSpaceLifeMotion.h)
	/** What the jets and the wakes hold and what they cost, in a line; and, ship by ship, what her motion asks of her jets now. */
	FString MotionStat() const;
	FString MotionTable() const;
	/** Testing: fires a ship's jets by hand to see where they are and what they look like (astra.space.jets): Which a contact id, a class key or "nearest" (the nearest warship but the Aquila, or the
	 *  Aquila when she is alone); What yaw+ yaw- pitch+ pitch- roll+ roll- brake left right up down all; Seconds how long it is held. */
	bool DebugJets(const FString& Which, const FString& What, float Seconds, FString& OutDetail);

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
	UPROPERTY() TObjectPtr<UMaterialInterface> MatDart;
	UPROPERTY() TArray<TObjectPtr<UStaticMesh>> KeepMeshes;
	TArray<FSpaceLifePlace> Places;

	bool bLive = false;                           // the game draws (assets found)
	bool bSim = false;                            // the bench: staged and counted, not drawn
	bool bInitDone = false;
	bool bPending = false;                        // an arrival waits for the sky
	FString PendingSystem;
	FString SystemName;
	FString SystemKey;                            // SystemName in lower case: what the wrecks are kept under
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
	AstraFx::FLayer Lamps, Plumes, Glints, Jets, Wakes;
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

	// ---- what the war leaves
	AstraSpace::FWrecks Wrecks;
	double ClockBase = 0.0;                       // the wrecks' clock is the battle's plus this (a resumed campaign carries on from its save)
	AstraSpace::FSkyFrame Sky;                    // the Gate's frame of this system (set when it is laid out)
	float WreckThinkT = 0.f, WreckPruneT = 30.f;
	int32 WreckHullsNow = 0, ChunksNow = 0, PodsNow = 0, EmbersNow = 0, WreckHullsPeak = 0, ChunksPeak = 0;
	double WrecksMs = 0.0;
	bool bResumeProbe = false;                    // a resume is under way (DebugResume): the wrecks as they were, in the Gate's frame, to be compared once the system is laid out again
	TArray<TPair<int32, FVector>> ResumeProbe;    // (site id and piece index folded in: one entry for each piece and pod)
	double ResumeClock = 0.0;

	// ---- the motion of the capitals: what is read of each (by ship id; a ship that is gone keeps its wake until it has faded), what it costs
	TMap<int32, AstraSpace::FMotion> Motions;
	double MotionClock = 0.0;                      // the battle's own time, summed here (s): the wakes' clock
	float MotionSweepT = 0.f;
	int32 MotionShips = 0, JetsNow = 0, JetsPeak = 0, JetsLitNow = 0, WakeNow = 0, WakePeak = 0, JetsDropped = 0, WakeDropped = 0;
	double MotionMs = 0.0;
	int32 MotionTicks = 0;

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
	/** The hull of a key is still where it was last sent (a slow thing far away is moved every few frames, not every one): it keeps its slot this frame. False when it has none (stage it). */
	bool KeepHull(int32 SetIdx, int32 Key);
	void FlushSets();
	void HideSets();
	void DrawPlaces();
	void DrawVessels();
	void DrawPatrols();
	void DrawLamps(const TArray<AstraSpace::FLamp>& Set, const FVector& Pos, const FQuat& Att, uint32 Hash, double Dist2, float Fade, bool bShipLamps);
	void AddPlume(const FVector& Lip, const FVector& Dir, float RadiusM, float Thrust, bool bAmber, float Salt);
	int32 RigidFor(const FString& Mesh);
	/** A wreck's look for the instances of a mesh (dark windows, cold cut faces, no running lights; charred for a reactor's): a dynamic material on each slot of the component. */
	void ApplyWreckLook(UInstancedStaticMeshComponent* C, uint8 Variant);
	// ---- the motion of the capitals (AstraSpaceLifeMotionDraw.cpp)
	void TickMotion(float SimDt);
	void DrawMotion();
	void AddJet(const AstraSpace::FMotion& M, const AstraSpace::FJet& J, float Level, float Len, float Km);
	// ---- what the war leaves (AstraSpaceLifeWrecks.cpp)
	void TickWrecks(float SimDt);
	void HandOver(double Now);
	void DrawWrecks(double Now);
	/** The wrecks the crew's eyes and sensors can pick out, and the lifepod beacons they hear (a small object for ship_state.state.space). */
	TSharedRef<FJsonObject> WreckSummaryJson() const;
};
