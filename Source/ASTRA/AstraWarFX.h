// ASTRA — the war's visual effects (F2.4, "la guerra bella"): weapons, shields, explosions, break-ups, hull damage and drive plumes.
//
// The battle simulation (AstraBattleSubsystem.*, AstraWarDamage.cpp) says what happens; this draws it. Everything is drawn as
// instances of a few engine shapes (UInstancedStaticMeshComponent: one draw call per kind of effect, no actor per shot or per spark)
// and shaped by the materials (tools/ue_scripts/make_war_fx.py), which only ever use volumes with soft rims — spheres for flashes,
// fireballs, smoke and darts, tubes for beams and trails — so that nothing is a flat plate seen edge-on, and a flash that is a few
// pixels from the bridge is still a round glow when the main viewscreen's camera is zoomed on it (docs/VFX.md).
//
// The core (the particles, the shots, the shields' ripples, the pieces of a broken hull) is plain C++ in the system frame (metres,
// the Aquila's frame is applied when the instances are written); the bench (-nullrhi) runs it too, without the engine objects, so
// its cost is measured by tools/war.py like the rest of the war.

#pragma once

#include "CoreMinimal.h"
#include "UObject/Object.h"
#include "AstraWarTypes.h"
#include "AstraWarFX.generated.h"

class AActor;
class AStaticMeshActor;
class UAstraBattleSubsystem;
class UDecalComponent;
class UInstancedStaticMeshComponent;
class UMaterialInstanceDynamic;
class UMaterialInterface;
class UPointLightComponent;
class UStaticMesh;
class UTextureRenderTarget2D;
class UWorld;
struct FAstraBattleShip;
struct FAstraProjectile;
struct FAstraWreck;

/** What a beam or a tracer line is. */
enum class EAstraFxShot : uint8
{
	Laser,           // a capital ship's laser battery: a beam with a glow and heat where it lands
	Cannon,          // a fighter's cannon, the Captain's Falcon: a short, fast tracer
	PointDefence     // a point-defence mount's burst: a stream of tracers
};

/** What a flash stands for (the older call sites of AddFlash say which they mean). */
enum class EAstraFxFlash : uint8
{
	Spark,           // a small bright burst
	Flak,            // a point-defence kill: flash, puff of smoke, a few sparks
	Decoy,           // a flare or a chaff bloom that lingers
	Blast            // a big fireball (the Aquila's reactor, secondary blasts along her hull)
};

/** What one blow did, for the effects (filled by ApplyHitModel / ApplyHitLump). */
struct FAstraFxHit
{
	FVector Pos = FVector::ZeroVector;        // where it struck the hull (system frame)
	FVector Dir = FVector::ForwardVector;     // the way it was travelling (unit)
	EAstraHitKind Kind = EAstraHitKind::Rail;
	float Damage = 0.f;                       // what it carried
	float ShieldTook = 0.f;                   // what the shield sector stopped
	float Through = 0.f;                      // what got past the shield
	float Felt = 0.f;                         // what the hull felt of it (structure and a share of the plate)
	int32 Facing = 0;                         // the face it landed on (AstraWar::EFacing)
	int32 Section = 1;                        // the lengthwise section (AstraWar::ESection)
	FVector LocalOut = FVector::ForwardVector;// the outward direction of the struck point, ship frame
	float SectorFrac = 1.f;                   // what is left of that shield sector (0..1) after the blow
	bool bSectorFell = false;                 // this blow took the sector to nothing
	bool bOnSkin = false;                    // Pos has been put on the hull's skin (SnapToHull); the simulation's is on the face of its box
};

/** A number the look of the effects hangs on: its default, or what `astra.war.tune fx_<name> <value>` set since (the war's own live tuning table: no build, no restart). */
#define ASTRA_FX_TUNE(NAME, DEFAULT) ([]() -> float { static AstraWar::FTuneVar V(TEXT("fx_" NAME), (DEFAULT)); return V.Get(); }())

namespace AstraFx
{
	constexpr int32 Stride = 12;              // floats of per-instance custom data (colour 0-2, intensity 3, age 4, P1 5, P2 6, seed 7, width 8, length 9)

	/** Capacity of each layer (instances) and of the particle lists: the budget of the effects. */
	constexpr int32 CapDarts = 2000, CapTubes = 2000, CapGlows = 900, CapFires = 200, CapSmokes = 220, CapPlumes = 220, CapDebris = 140;
	constexpr int32 CapPuffs = 900, CapSparks = 1800, CapBeams = 360, CapDebrisSim = CapDebris, CapPieces = 36, CapWakes = 160;
	constexpr int32 MaxLights = 8;
	constexpr float GlowK = 1.7f;             // a glow's soft falloff reaches ~0.6 of its sphere: spheres are drawn this much larger than the glow they stand for

	/** One layer of instances (one UInstancedStaticMeshComponent, one material): staged each frame, written once. */
	struct FLayer
	{
		TWeakObjectPtr<UInstancedStaticMeshComponent> Comp;   // (empty on the bench: the layer stages and counts, draws nothing)
		int32 Capacity = 0;
		int32 NumData = Stride;                // custom floats per instance (0: a lit mesh with no custom data)
		int32 Count = 0;                       // this frame
		int32 Prev = 0;                        // last frame (what must be hidden when it shrinks)
		int32 Peak = 0;
		int32 Dropped = 0;                     // asked for when full
		TArray<FTransform> Xf;
		TArray<float> Data;

		void Init(int32 InCapacity);
		void Begin() { Count = 0; }
		int32 Free() const { return Capacity - Count; }
		/** The next free instance (its transform and its custom data to fill), or null when the layer is full. */
		float* Next(FTransform*& OutXf);
		void Flush();
	};

	/** A soft round particle: a flash, a fireball, a puff of smoke, a lingering ember glow. */
	struct FPuff
	{
		FVector Pos = FVector::ZeroVector;     // system frame, m
		FVector Vel = FVector::ZeroVector;     // m/s
		float Age = 0.f, Life = 1.f;           // an Age below zero is a delay: not yet born
		float R0 = 10.f, R1 = 30.f;            // radius (m) at birth and at the end
		FLinearColor Col = FLinearColor::White;
		float Inten = 100.f;
		float Drag = 0.f;                      // 1/s: the drift bleeds away
		float Seed = 0.f;                      // 0..1: rotation and start frame of the flipbook
		float P1 = 0.f, P2 = 0.f;              // what the material takes (kind of glow, heat of a smoke puff...)
		uint8 Layer = 0;                       // see ELayer
	};

	/** A spark, a tracer, a chip of molten metal: a short bright streak along its way. */
	struct FSpark
	{
		FVector Pos = FVector::ZeroVector;
		FVector Vel = FVector::ZeroVector;
		float Age = 0.f, Life = 1.f;
		float Len = 10.f, Width = 0.6f;        // m
		FLinearColor Col = FLinearColor::White;
		float Inten = 200.f;
		float Drag = 0.f;
		float Seed = 0.f;
	};

	/** A beam or a tracer line from one point to another, riding on the ships at its ends while it lives. */
	struct FBeam
	{
		FVector A = FVector::ZeroVector, B = FVector::ZeroVector;     // system frame (used where no ship holds an end)
		int32 FromId = -1, ToId = -1;
		FVector FromLoc = FVector::ZeroVector, ToLoc = FVector::ZeroVector;   // ship-frame offsets (m)
		FVector RawToLoc = FVector::ZeroVector;                              // where the simulation ended it (the face of the target's box): what a shield's hit is matched with
		float Age = 0.f, Life = 0.3f, Width = 3.f;
		FLinearColor Col = FLinearColor::White;
		float Inten = 300.f;
		float Seed = 0.f;
		EAstraFxShot Kind = EAstraFxShot::Laser;
	};

	/** What the effects keep of one projectile of the simulation: where it was drawn as it began, and its trail. */
	struct FTrack
	{
		static constexpr int32 TrailPts = 9;
		static constexpr int32 LongPts = 8;    // the long smoke of a missile: a point every half second
		int32 Frame = -1;                      // the last frame it was seen alive (a slot not seen is freed)
		float Age = 0.f;
		FVector Offset = FVector::ZeroVector;  // the muzzle's offset from the true path at birth (m), fading to zero
		float OffsetTau = 0.25f;
		FVector Last = FVector::ZeroVector;    // where it was drawn last (its head)
		FVector Start = FVector::ZeroVector;   // where its path began: the muzzle (system frame)
		FVector WakeTail = FVector::ZeroVector;// the far end of the wake it drew last (a slug's wake: Wake below), system frame
		float WakeKappa = 0.f;                 // and its decay
		float WakeWidth = 1.8f;                // and its width (m)
		bool bWake = false;                    // it has drawn a wake
		FVector Hist[TrailPts];                // where the trail has been (system frame), newest first
		int32 HistN = 0;
		float SampleAcc = 0.f;
		FVector LongHist[LongPts];             // where a missile has been, every half second (system frame), newest first: the long smoke behind the beads
		int32 LongN = 0;
		float LongAcc = 0.f;
		FVector PrevVel = FVector::ZeroVector; // its velocity a frame ago (the seeker's turns are read from it)
		bool bPrevVel = false;
		float RcsAcc = 0.f;                    // seconds since its last puff of attitude gas
		uint8 Style = 0;                       // 0 rail slug, 1 missile, 2 torpedo, 3 rocket
		FLinearColor Col = FLinearColor::White;
	};

	/** The trail a shot left when it ended (a hit, a kill by point defence, running out): it hangs there a moment, fading. */
	struct FGhost
	{
		FVector Pts[FTrack::TrailPts + 1];    // newest first (system frame)
		int32 N = 0;
		FVector Long[FTrack::LongPts + 1];    // the long smoke, newest first
		int32 LongN = 0;
		float Age = 0.f, Life = 1.4f;         // Life: the whole ghost's (the long smoke hangs longer than the beads)
		float BeadLife = 1.4f;                // the beads' own
		uint8 Style = 1;
		FLinearColor Col = FLinearColor::White;
		uint8 Seed = 0;
	};

	/** A big explosion, as the main viewscreen's director may want to know it (UAstraWarFX::GetBlasts). */
	struct FBlastView
	{
		FVector Pos = FVector::ZeroVector;     // system frame, m
		float Radius = 0.f;                    // m: the fireball's
		float Age = 0.f;                       // s since it went
		int32 ShipId = -1;
		bool bAstra = false;
		bool bReactor = false;                 // the reactor went (else the hull broke apart)
	};

	/** The wake a slug left when it ended (it struck, it missed, it ran out of life): the line it drew, hanging there and fading as it would have if the slug had gone on. */
	struct FWake
	{
		FVector Tail = FVector::ZeroVector, Head = FVector::ZeroVector;   // system frame
		float Age = 0.f;
		float Kappa = 2.f;                     // the decay along it: e^-Kappa at the tail against 1 at the head
		float Width = 1.8f;                    // m
		float Seed = 0.f;
		FLinearColor Col = FLinearColor::White;
	};

	/** One ripple of a shield: where a blow landed on it and how it spreads. */
	struct FRipple
	{
		FVector Dir = FVector::ForwardVector;  // unit, in the shield's own frame (the hull box's frame): where on the shell
		float Age = 0.f, Life = 1.f;
		float Strength = 1.f;                  // 0..1+
		float Radius = 20.f;                   // m
		float Stress = 0.f;                    // 0..1: how worn the sector is (the cells flicker, the edges crackle)
		float Seed = 0.f;
	};

	/** A ship's shield shell: an actor with a sphere of its own, drawn only while something ripples on it. */
	struct FShield
	{
		TWeakObjectPtr<AStaticMeshActor> Actor;
		TWeakObjectPtr<UMaterialInstanceDynamic> Mid;
		TArray<FRipple, TInlineAllocator<6>> Ripples;
		FVector CollapseDir = FVector::ForwardVector;   // shield frame: the sector that fell
		float CollapseAge = -1.f;               // seconds since it fell (-1: none)
		bool bShown = false;
		FVector Axes = FVector(100.f);          // the shell's semi-axes (m) as last set
	};

	/** A place where a hull has been hit hard: it glows there, on the hull, and cools. */
	struct FWound
	{
		FVector Lp = FVector::ZeroVector;     // the ship's frame, m
		float R = 6.f;                       // m: how far the glow reaches
		float Heat = 1.f;                    // 1 fresh, 0 cold (it is gone at 0.03)
		float Seed = 0.f;
	};

	/** The effects' state for one ship. */
	struct FShipFx
	{
		FVector PrevVel = FVector::ZeroVector;
		float PrevTime = -1.f;
		float Thrust = 0.f;                    // 0..1: how hard the drive is working (smoothed)
		float SpoolT = 0.f;                    // plume flicker clock
		float Emit[3] = {0.f, 0.f, 0.f};       // per section: fire/smoke emission accumulators
		float EmitVent[3] = {0.f, 0.f, 0.f};
		float BlastT[3] = {2.f, 4.f, 6.f};     // per section: seconds to the next secondary blast of a burning one
		bool bGutSeen[3] = {false, false, false};   // per section: its going has been drawn (the burst of the moment it is gutted)
		float BreakBlast = 0.f;                // secondary blasts while the hull is breaking
		FShield Shield;
		int32 Scars = 0;
		TArray<FWound> Wounds;                 // where it has been hit hard (a dozen at most: the oldest goes)
		const struct FShipTable* Table = nullptr;   // its drive bells and pieces (found once)
		bool bTableKnown = false;
		bool bDark = false;                    // its lights have been put out (disabled)
		float DarkT = 0.f;
		TWeakObjectPtr<UMaterialInstanceDynamic> LightsMid;   // the windows
		// the inside of a ship that has one (FLOTTA-VIVA): where it burns and vents, by section, in the hull's frame (m), refreshed a few times a second; how lit its windows are
		TArray<FVector> InFire[3], InVent[3];
		float InT = 0.f, InLit = 1.f;
	};

	/** A piece of a broken hull. */
	struct FPiece
	{
		TWeakObjectPtr<AStaticMeshActor> Actor;
		TWeakObjectPtr<UMaterialInstanceDynamic> CutMid;      // the burnt faces (Heat 1 -> 0)
		TWeakObjectPtr<UMaterialInstanceDynamic> LitMid;      // the windows (they go out)
		TArray<TWeakObjectPtr<UMaterialInstanceDynamic>> Chars; // hull slots darkened as it burns
		FVector Origin = FVector::ZeroVector;  // system frame, m: where the mesh's origin is
		FVector Pivot = FVector::ZeroVector;   // system frame, m: the piece's centre of mass (what it turns about)
		FVector PivotLocal = FVector::ZeroVector;   // the same, in the mesh frame (m)
		FVector Vel = FVector::ZeroVector;
		FQuat Att = FQuat::Identity;
		FVector SpinAxis = FVector::UpVector;
		float SpinRate = 0.f;                  // rad/s
		float Heat = 1.f;                      // the cut faces' glow
		float Age = 0.f;
		float Emit = 0.f;
		int32 ShipId = -1;
		int32 FaceFirst = 0, FaceCount = 0;    // its cut faces in the ship's table
		const struct FShipTable* Table = nullptr;
		uint8 Section = 0;
		float Radius = 50.f;
		bool bAstra = false;
		bool bReactor = false;                 // thrown out by a reactor breach: burns harder, and is charred
		// The main viewscreen takes the list of what it shows twice a second, so the pieces (new actors) would be missing from it for up to half a
		// second after the break. The bridge's eye sees the pieces from the first frame; the viewscreen goes on seeing the whole hull (driven here, on
		// its old path) until Hold runs out, and then the pieces too, and the hull goes.
		float Hold = 0.f;                      // seconds the viewscreen still sees the whole hull
		TWeakObjectPtr<AActor> HullActor;      // the whole hull (on one of the three pieces)
		FVector HullOrigin = FVector::ZeroVector, HullVel = FVector::ZeroVector;
		FQuat HullAtt = FQuat::Identity;
	};

	/** A chunk of debris (a cube with the faction's hull material). */
	struct FDebris
	{
		FVector Pos = FVector::ZeroVector, Vel = FVector::ZeroVector;
		FQuat Att = FQuat::Identity;
		FVector SpinAxis = FVector::UpVector;
		float SpinRate = 0.f;
		FVector Size = FVector(2.f);           // m
		float Age = 0.f, Life = 20.f;
		bool bAstra = false;
		float Glow = 0.f;                      // seconds of ember glow left (a spark trail while it is hot)
	};

	/** A light that flares and dies (pooled: a few at a time). */
	struct FFlashLight
	{
		FVector Pos = FVector::ZeroVector;
		FVector Vel = FVector::ZeroVector;
		float Age = 0.f, Life = 0.4f;
		float Inten = 1.e7f;                   // candela at the peak
		float Radius = 300.f;                  // m
		FLinearColor Col = FLinearColor::White;
	};

	/** A scar on a hull: a decal that cools. */
	struct FScar
	{
		TWeakObjectPtr<UDecalComponent> Decal;
		TWeakObjectPtr<UMaterialInstanceDynamic> Mid;
		TWeakObjectPtr<AActor> On;
		float Heat = 1.f, Shown = 1.f;
	};

	enum ELayer : uint8 { LGlow = 0, LFire = 1, LSmoke = 2, LShock = 3 };

	/** The per-instance custom data every material reads: colour, intensity, age, two parameters, a seed, the size in metres. */
	FORCEINLINE void Fill(float* D, const FLinearColor& C, float Inten, float Age, float P1, float P2, float Seed, float WidthM, float LenM)
	{
		D[0] = C.R; D[1] = C.G; D[2] = C.B; D[3] = Inten; D[4] = Age; D[5] = P1; D[6] = P2; D[7] = Seed; D[8] = WidthM; D[9] = LenM; D[10] = 0.f; D[11] = 0.f;
	}
	FORCEINLINE FLinearColor Mix(const FLinearColor& A, const FLinearColor& B, float T) { return A + (B - A) * T; }
	/** Smooth ramp 0..1. */
	FORCEINLINE float Ease(float X) { X = FMath::Clamp(X, 0.f, 1.f); return X * X * (3.f - 2.f * X); }
	/** A fast start that slows: 1 - (1-x)^2. */
	FORCEINLINE float Out(float X) { X = FMath::Clamp(X, 0.f, 1.f); return 1.f - (1.f - X) * (1.f - X); }
}

/**
 * The war's effects. Owned by the battle subsystem (which calls its hooks), it makes its own host actor with the instance layers,
 * a pool of lights and the shells and pieces it needs, and draws the shots, the sparks, the shields, the explosions, the breaking
 * hulls and the drives. Never the simulation's truth: nothing here is read back by the war.
 */
UCLASS()
class ASTRA_API UAstraWarFX : public UObject
{
	GENERATED_BODY()

public:
	/** Set up for this battle (OnWorldBeginPlay): loads the materials and meshes, makes the layers. */
	void Init(UAstraBattleSubsystem* InOwner);
	/** The effects are being drawn (assets found), or run without drawing on the bench (and not switched off: astra.fx.enable). */
	bool IsActive() const;
	/** The materials were found and the game draws. */
	bool IsLive() const { return bLive; }
	/** Everything goes (a transit, a new system). */
	void Reset();

	/** Once a frame, after the ships and the shots have moved (Dt: real seconds). */
	void Tick(float Dt);

	// ---- hooks: the battle says what happens
	/** A shot leaves a gun: the muzzle's flash, and where the slug is drawn from (it returns the projectile's track). */
	int32 OnProjectile(const FAstraBattleShip& From, const FAstraBattleShip& To, const FAstraProjectile& Pr);
	/** A beam or a tracer line (a laser pulse, a burst of cannon fire, a point-defence stream). From and To are ship ids, -1 for none. */
	void OnBeam(EAstraFxShot Kind, const FVector& A, const FVector& B, float Life, const FLinearColor& Col, int32 FromId = -1, int32 ToId = -1);
	/** A flash the older call sites ask for. */
	void OnFlash(EAstraFxFlash Kind, const FVector& Pos, float Size, float Life, const FLinearColor& Col, float Inten,
	             const FVector& Vel = FVector::ZeroVector, float Delay = 0.f);
	/** A blow lands on a warship (or a craft). */
	void OnHit(const FAstraBattleShip& To, const FAstraFxHit& Hit);
	/** A fighter, a bomber or a drone dies. */
	void OnCraftDestroyed(const FAstraBattleShip& S);
	/** A warship dies; the hull's actor is taken over (S.Actor is left null). False: not handled, the old explosion stands. */
	bool OnShipDestroyed(FAstraBattleShip& S, const FAstraDeathEvent& E);
	/** A warship loses power (no explosion): its lights go out, its drive dies. */
	void OnShipDisabled(const FAstraBattleShip& S);
	/** The Aquila's end: a reactor breach at a point (system frame), a chain of blasts along her hull. */
	void OnAquilaBreach(const FVector& ReactorPos, float Radius, const FVector& Vel);
	/** How hard the drive of a ship works (0..1), for the old drive flare and the plumes. */
	float Throttle(const FAstraBattleShip& S) const;
	/** A transit or a resumed campaign: the old system's effects are gone. */
	void ClearAll();

	// ---- hooks for what the war leaves behind (SPAZIO-VIVO, AstraWrecks.h)
	/** The pieces of broken hulls the effects hold now (as actors, burning at the cut): the wrecks module records them as they are made, and takes them over when they have cooled. */
	const TArray<AstraFx::FPiece>& GetPieces() const { return Pieces; }
	/** Lets one ship's piece go (its actor is destroyed): the wrecks module draws it from its own record from this frame on. Nothing happens if the effects no longer hold it. */
	void ReleasePiece(int32 ShipId, uint8 Section);

	// ---- for the main viewscreen's director (read only)
	/** The big explosions of the last seconds (a ship's death: the reactor going, the hull breaking): where, how big, how long ago. A shot that cuts to a death can frame the fireball (the
	 *  camera that zooms on a piece inside a fireball sees only the cloud) and hold on it for as long as it burns. Nothing in the war reads them. */
	void GetBlasts(TArray<AstraFx::FBlastView>& Out) const { Out = Blasts; }

	// ---- the console (AstraWarFXTest.cpp)
	void Stats(FString& Out) const;
	/** Runs what astra.fx.* asked for since the last frame. */
	void RunTests();

private:
	friend class UAstraBattleSubsystem;
	friend struct FAstraWarFXTest;

	UPROPERTY() TObjectPtr<UAstraBattleSubsystem> Owner;
	UPROPERTY() TObjectPtr<AActor> Host;
	UPROPERTY() TObjectPtr<AActor> TestCamera;                 // astra.fx.cam: a free camera for the tests (AstraWarFXTest.cpp)
	int32 TestScarKind = -1;                                   // astra.fx.scar: the kind of mark to leave (-1: as the blow says)
	UPROPERTY() TObjectPtr<UTextureRenderTarget2D> TestTarget;
	UPROPERTY() TObjectPtr<UStaticMesh> SphereMesh;
	UPROPERTY() TObjectPtr<UStaticMesh> BallMesh;          // a smoother sphere for the shields (if the project has it)
	UPROPERTY() TObjectPtr<UStaticMesh> CylinderMesh;
	UPROPERTY() TObjectPtr<UStaticMesh> CubeMesh;
	UPROPERTY() TObjectPtr<UMaterialInterface> MatDart;
	UPROPERTY() TObjectPtr<UMaterialInterface> MatTube;
	UPROPERTY() TObjectPtr<UMaterialInterface> MatGlow;
	UPROPERTY() TObjectPtr<UMaterialInterface> MatFire;
	UPROPERTY() TObjectPtr<UMaterialInterface> MatSmoke;
	UPROPERTY() TObjectPtr<UMaterialInterface> MatPlume;
	UPROPERTY() TObjectPtr<UMaterialInterface> MatShield;
	UPROPERTY() TObjectPtr<UMaterialInterface> MatDebris;   // lit chunks of metal (M_WAR_Debris; the engine's basic material until it exists)
	UPROPERTY() TArray<TObjectPtr<UPointLightComponent>> Lights;
	UPROPERTY() TArray<TObjectPtr<UMaterialInterface>> DamageMats;   // MI_ShipDamage_<Burn|Hole|Torn|Impact|Strafe|Melt|Gouge|Blast>

	TWeakObjectPtr<AActor> AquilaHull;   // the level's own hull of the Aquila (where her scars are painted)
	bool bLive = false;           // the game draws
	bool bSim = false;            // the bench: the same simulation of effects, nothing drawn
	bool bInitDone = false;

	// ---- the layers
	AstraFx::FLayer Darts, Tubes, Glows, Fires, Smokes, Plumes, DebrisL;

	// ---- the state
	TArray<AstraFx::FPuff> Puffs;
	TArray<AstraFx::FSpark> Sparks;
	TArray<AstraFx::FBeam> Beams;
	TArray<AstraFx::FTrack> Tracks;
	TArray<int32> FreeTracks;
	TArray<AstraFx::FGhost> Ghosts;
	TArray<AstraFx::FWake> Wakes;
	TArray<AstraFx::FBlastView> Blasts;
	TMap<int32, AstraFx::FShipFx> ShipFx;
	TArray<AstraFx::FPiece> Pieces;
	TArray<AstraFx::FDebris> Debris;
	TArray<AstraFx::FFlashLight> FlashLights;
	TArray<AstraFx::FScar> Scars;
	int32 Frame = 0;
	float Clock = 0.f;            // the effects' own time (real seconds)
	float StatClock = 0.f;
	double TickMs = 0.0, TickMsMax = 0.0;
	int32 TickCount = 0;

	// ---- the frame (set at the start of each Tick)
	struct FFrame
	{
		FVector Origin = FVector::ZeroVector;       // the Aquila, system frame
		FQuat InvAtt = FQuat::Identity;
		FQuat Att = FQuat::Identity;
		FVector Vel = FVector::ZeroVector;
		FVector Bridge = FVector::ZeroVector;       // the bridge in the hull frame (m)
		FVector ToWorld(const FVector& P) const { return (InvAtt.RotateVector(P - Origin) - Bridge) * 100.0; }
		FQuat ToWorldRot(const FQuat& Q) const { return InvAtt * Q; }
		FVector DirToWorld(const FVector& D) const { return InvAtt.RotateVector(D); }
	} F;
	float Dt = 0.f;

	// ---- tuning (cvars read once a frame)
	float Intensity = 1.f;        // astra.fx.intensity
	float Density = 1.f;          // astra.fx.density: how many particles (0.25..2)
	float LightScale = 1.f;       // astra.fx.lights
	float WakeGain = 1.f;         // astra.fx.wake: the brightness of the line a slug draws behind it (0 none)
	float MuzzleGain = 1.f;       // astra.fx.muzzle: the size of the flash at a gun's mouth

	// ---- internals (AstraWarFX.cpp)
	bool LoadAssets();
	void MakeLayer(AstraFx::FLayer& L, const TCHAR* Name, UStaticMesh* Mesh, UMaterialInterface* Mat, int32 Capacity, int32 SortPriority, bool bLit, int32 NumData);
	void BeginFrame();
	void EndFrame();
	void DrawShots();
	void DrawBeams();
	void DrawPuffs();
	void DrawSparks();
	void DrawDebris();
	void DrawDrives();
	void TickLights();
	void TickShips();
	void TickPieces();
	void TickScars();
	void TickShields();
	AstraFx::FShipFx& ShipOf(int32 Id);
	FVector PlayerEye() const;

	// ---- the budget: how much room is left in what the effects draw (1 plenty .. 0 full): what throws particles asks it, so the biggest blast of a
	// battle does not push the sparks of the rest out and a long fire does not fill the sky with smoke
	int32 PuffLive[4] = {0, 0, 0, 0};
	float Room(uint8 Layer) const;
	float RoomSparks() const;

	// ---- spawning (AstraWarFX.cpp, AstraWarFXEvents.cpp)
	AstraFx::FPuff* AddPuff(const FVector& Pos, const FVector& Vel, float Life, float R0, float R1, const FLinearColor& Col, float Inten, uint8 Layer, float Delay = 0.f);
	AstraFx::FSpark* AddSpark(const FVector& Pos, const FVector& Vel, float Life, float Len, float Width, const FLinearColor& Col, float Inten, float Drag = 0.f);
	void SparkBurst(const FVector& Pos, const FVector& Dir, float Spread, int32 N, float SpeedLo, float SpeedHi, float LifeLo, float LifeHi,
	                float Len, const FLinearColor& Col, float Inten, const FVector& BaseVel);
	void AddLight(const FVector& Pos, float Life, float Radius, float Candela, const FLinearColor& Col, const FVector& Vel, float Delay = 0.f);
	void AddDebris(const FVector& Pos, const FVector& Vel, float SizeM, bool bAstra, float Life);
	void Explosion(const FVector& Pos, const FVector& Vel, float Radius, bool bAstra, float Power, float Delay = 0.f);
	void Smoke(const FVector& Pos, const FVector& Vel, float Radius, float Life, float Dark, float Delay = 0.f);
	void Shockwave(const FVector& Pos, const FVector& Vel, float Radius, float Life, const FLinearColor& Col, float Delay = 0.f);

	// ---- shields (AstraWarFXEvents.cpp)
	void ShieldHit(const FAstraBattleShip& To, const FAstraFxHit& Hit);
	FVector ShieldAxes(const FAstraBattleShip& S) const;
	FVector ShieldPoint(const FAstraBattleShip& S, const FVector& HitPos, FVector& OutDir) const;

	// ---- hulls (AstraWarFXHull.cpp)
	void AddScar(const FAstraBattleShip& S, const FAstraFxHit& Hit);
	/** A hard blow leaves a glow on the hull where it fell (a decal is a dark patch: it cannot be seen from far, and the glow can). */
	void AddWound(const FAstraBattleShip& S, const FAstraFxHit& Hit);
	void DrawWounds(const FAstraBattleShip& S, AstraFx::FShipFx& Fx);
	void HullEmitters(const FAstraBattleShip& S, AstraFx::FShipFx& Fx);
	/** A point on the face of a ship's box (its frame, m) put on the hull's skin under it: the box is a plane and the hull is not (a cruiser's deck is forty metres below the top of its box). False
	 *  when the ship has no skin table, the point is then as it was. */
	bool SnapToHull(const FAstraBattleShip& S, int32 Facing, FVector& Local) const;
	/** A section of a warship has just been gutted (it went to zero): the burst of its going. */
	void GutBurst(const FAstraBattleShip& S, int32 Section);
	void PowerDown(const FAstraBattleShip& S, AstraFx::FShipFx& Fx);
	/** The inside of a ship that has one (FLOTTA-VIVA): where it burns and vents, and how lit its windows are (refreshed a few times a second). */
	void FleetFxRefresh(const FAstraBattleShip& S, AstraFx::FShipFx& Fx);
	/** A point on the hull where one of the inside's fires or breaches shows (the face of the hull's box nearest the point), in the war's space. */
	FVector FleetFxPoint(const FAstraBattleShip& S, const TArray<FVector>& Points) const;
	bool MakePieces(FAstraBattleShip& S, const FAstraDeathEvent& E, AActor* Hull, bool bReactor);
	FVector HullPoint(const FAstraBattleShip& S, int32 Section, float Along, float SideA, float SideB, bool bSurface) const;
	FVector MuzzleOf(const FAstraBattleShip& S, EAstraMountKind Kind, const FVector& AimDir, int32 Salt);
	uint32 NextMount[2] = {0, 0};
};

/** The effects' colours by faction and by weapon. */
namespace AstraFx
{
	/** The per-ship data of the effects (drive bells, pieces, cut faces: AstraWarFXData.inl), by the ship's mesh name. */
	const struct FShipTable* FindTable(const FString& MeshName);
	FLinearColor ShotColor(bool bAstra, EAstraHitKind Kind);
	FLinearColor ShotHalo(bool bAstra, EAstraHitKind Kind);
	FLinearColor ShieldColor(bool bAstra);
}
