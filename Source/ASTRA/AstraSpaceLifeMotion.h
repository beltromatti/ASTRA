// ASTRA — the motion of the capital ships made readable (SPAZIO-VIVO, docs/SPAZIO.md): the manoeuvring jets that fire when a ship turns, brakes or slides sideways, and the wake a drive
// leaves where the ship has been. Nothing here moves a ship: the war's rules of motion (omnidirectional acceleration clamped to the class's, a turn at the class's rate) are read, a frame
// at a time, from where the ship is, how fast, which way she points; what is drawn follows from that and goes nowhere (nothing in the war reads it).
//
// The jets. A ship is asked to do things by her motion: her heading changes (a turn begins, holds, ends), her velocity changes across her heading (a brake, a slide). Each is an
// ACCELERATION (the change of rate of her turn; the push on her), and a ship's jets are where an acceleration comes from: a jet fires when the push it gives, and the torque it gives
// about the ship's middle, are along what is being asked. So there is no script per manoeuvre: the nozzles are where the hull has them (data/space/thrusters.json: the ship
// generators' own thruster blocks where a class has them, a standard pack on the hull's surface where it does not: art/blender/space3_thrusters.py) and the same few lines of
// allocation fire the right ones for a turn to starboard, a pitch, a roll, a brake, a slide, or any mixture. The war's sim turns at a constant rate (the rate steps at the start
// and the end of a turn), so what the burn follows is the CHANGE of rate: a burst of the jets that start the turn, a faint trim while it is held, a burst of the opposite ones to stop
// it; what a ship does with the main drive (boost) is the war effects' own plume (UAstraWarFX::DrawDrives), left alone.
//
// The wake. While a drive works (UAstraWarFX::Throttle) the point of the stern it burns from is noted every few tenths of a second, in the system frame; the notes are a ribbon
// that stays where the ship has been and fades over a few tens of seconds, wider and dimmer as it ages (an ion trail dispersing). Seen from a bridge in the dark it is the one thing
// that shows where a ship is heading and has been, and so a turn of a capital that is slow to the eye.
//
// Plain C++ like the wrecks and the traffic: no engine objects, so the bench runs it on every ship of a fleet and the unit tests (RunMotionTests) can check the allocation against physics
// (a push at the bow to starboard turns the nose to starboard) and the wake against arithmetic. The drawing is UAstraSpaceLife's (AstraSpaceLifeMotionDraw.cpp).

#pragma once

#include "CoreMinimal.h"

namespace AstraSpace
{
	namespace Motion
	{
		constexpr float TauKick = 0.62f;         // s: how long the burst at the start or the end of a turn takes to die away (e^-1)
		constexpr float TrimK = 0.42f;           // the faint fire of the jets that turn a ship while she holds the turn (1 = a full burst; past the dead band it comes to a third of one)
		constexpr float DeadBand = 0.15f;        // what a jet's share of a demand must come to before it fires at all (a nozzle that only turns the ship a little must not twinkle)
		constexpr float AttackS = 0.04f;         // s: how fast a jet comes up
		constexpr float ReleaseS = 0.16f;        // s: and goes out
		constexpr float LinAttackS = 0.18f;      // s: the push demand's own smoothing (a brake is a few seconds, not a frame)
		constexpr float LinReleaseS = 0.45f;
		constexpr float PushDead = 0.10f;        // of the class's full acceleration: less is the AI's noise (its steering never quite rests)
		constexpr int32 WakeCap = 32;            // notes in a wake
		constexpr float WakeStepS = 0.75f;       // s between notes
		constexpr float CraftLenM = 40.f;        // a hull shorter than this is a craft (a fighter, a bomber, a drone): her jets are drawn as a craft's, she leaves no wake, she is read only near an eye
	}

	// ------------------------------------------------------------------------------------------------------------------ the jets of a class
	/** One nozzle: where it is in the ship's frame (x forward, y starboard, z up: metres from the mesh's origin) and which way its exhaust leaves. */
	struct FJet
	{
		FVector P = FVector::ZeroVector;
		FVector D = FVector::ForwardVector;      // the exhaust's direction (unit)
		float R = 0.5f;                          // the nozzle's radius (m)
		uint8 Kind = 0;                          // 0 a thruster block of the hull (the generators'), 1 yaw, 2 pitch/roll, 3 brake: the standard pack's
		// what it does when it fires, worked out once (FJetClass::Finish)
		FVector Push = FVector::ZeroVector;      // the way it pushes the ship: -D
		FVector Turn = FVector::ZeroVector;      // its torque about the ship's middle, each axis as a share (-1..1) of the best nozzle's on that axis
	};

	/** What the data says of a class: its jets, how long she is, the middle she turns about, where her drive burns. */
	struct FJetClass
	{
		FName Key;
		FString Mesh;
		float Len = 100.f;                       // the hull's length (m)
		FVector Com = FVector::ZeroVector;       // the middle a ship turns about (ship frame, m)
		FVector Box = FVector(50.0);             // the hull's half sizes (m)
		FVector DriveP = FVector::ZeroVector;    // the main drive's centre (ship frame, m): where the wake starts
		float DriveW = 20.f;                     // its width (m)
		float DriveR = 3.f;                      // its bells' radius
		TArray<FJet> Jets;

		/** A fighter, a bomber or a drone (not a capital ship): what is drawn of her is made for the few hundred metres to few kilometres she is seen from. */
		bool IsCraft() const { return Len < Motion::CraftLenM; }
		void Finish();
		/** The index of the jet nearest a point of the ship's frame, or INDEX_NONE. */
		int32 Nearest(const FVector& P) const;
	};

	struct FJetData
	{
		TMap<FName, FJetClass> Classes;
		TMap<FString, FName> KeyOfMesh;          // a craft is known by her mesh (the war gives a fighter no class key): "SM_CRAFT_ASTRA_Falcon" -> falcon
		bool bLoaded = false;
		FString Source;
		const FJetClass* Find(FName Key) const { return Classes.Find(Key); }
		const FJetClass* FindMesh(const FString& Mesh) const { const FName* K = KeyOfMesh.Find(Mesh); return K ? Classes.Find(*K) : nullptr; }
		bool Parse(const FString& Json, FString& OutError);
	};

	/** The game's table of jets, loaded once from Content/ASTRA/Data/space/thrusters.json (the staged copy) or data/space (the source). */
	ASTRA_API const FJetData& JetData();
	ASTRA_API void ReloadJetData();

	// ------------------------------------------------------------------------------------------------------------------ the demand and the allocation
	/** What a ship is asked to do, in her own frame. Turn: each axis the change of rate asked, 1 = the start of a turn at the class's full rate (x roll, y pitch, z yaw: the right-hand
	 *  rule of the component cross product, the one a quaternion's axis follows). Push: each axis the share of the class's full acceleration asked; +x is the main drive's. */
	struct FDemand
	{
		FVector Turn = FVector::ZeroVector;
		FVector Push = FVector::ZeroVector;
		bool IsIdle() const { return Turn.IsNearlyZero(0.02) && Push.IsNearlyZero(0.02); }
	};

	/** How hard each jet fires (0..1) for a demand: the share of what it gives along what is asked, past the dead band. Out has one entry per jet. */
	ASTRA_API void Allocate(const FJetClass& C, const FDemand& D, float* Out);

	// ------------------------------------------------------------------------------------------------------------------ the wake
	struct FWakePoint
	{
		FVector P = FVector::ZeroVector;         // the system frame
		float T = 0.f;                           // the motion clock (s) when it was noted
		float Str = 0.f;                         // how hard the drive worked then (0..1)
	};

	/** The ribbon behind a ship under way: a ring of notes, the newest first. */
	struct FWake
	{
		FWakePoint Pts[Motion::WakeCap];
		int32 Next = 0;                          // where the next note goes
		int32 Num = 0;
		double LastT = -1.0e30;
		FVector LastP = FVector::ZeroVector;

		void Reset() { Next = 0; Num = 0; LastT = -1.0e30; }
		/** Offers the drive's point now: noted when the step has passed and the ship has moved at least MinMove metres since the last note. True if it was. */
		bool Offer(const FVector& P, double T, float Str, double MinMove);
		/** The I-th note, 0 the newest. */
		const FWakePoint& At(int32 I) const { return Pts[(Next - 1 - I + Motion::WakeCap * 2) % Motion::WakeCap]; }
	};

	/** One piece of the ribbon to draw: from A (the newer end) to B, the ages at each end as a share of the wake's life (0 now, 1 gone), and how hard the drive worked at A. */
	struct FWakeSeg
	{
		FVector A = FVector::ZeroVector, B = FVector::ZeroVector;
		float AgeA = 0.f, AgeB = 0.f;
		float Str = 0.f;
	};

	/** The wake's pieces: from where the drive burns now (Head) back through the notes, none older than LifeS. Stride takes every second or fourth note (a far wake needs no more). Returns how many. */
	ASTRA_API int32 WakeSegments(const FWake& W, const FVector& Head, double Now, float LifeS, int32 Stride, FWakeSeg* Out, int32 Max);
	/** How long a ship's wake lasts (s): a larger ship's drive leaves more. */
	ASTRA_API float WakeLifeFor(float LenM);

	// ------------------------------------------------------------------------------------------------------------------ one ship's motion
	/** What the module keeps of a ship between frames: where she was (to read what she is doing), the demand's smoothed parts, how hard each jet burns, her wake. */
	struct FMotion
	{
		const FJetClass* Class = nullptr;
		bool bKnown = false;
		FVector PrevPos = FVector::ZeroVector, PrevVel = FVector::ZeroVector;
		FQuat PrevAtt = FQuat::Identity;
		FVector PrevOmega = FVector::ZeroVector;     // her turn's rate in her own frame (rad/s)
		FVector Kick = FVector::ZeroVector;          // the changes of rate not yet worked off (in units of the class's full rate), dying away
		FVector Omega = FVector::ZeroVector;         // her turn's rate now over the class's full rate (the trim follows it)
		FVector Lin = FVector::ZeroVector;           // the push asked, smoothed (share of the full acceleration)
		TArray<float> Burn;                          // by jet: how hard it burns now (what is drawn)
		TArray<float> Raw;                           // by jet: scratch for the allocation
		float Peak = 0.f;                            // the strongest jet now
		float Seed = 0.f;                            // 0..1: tells this ship's pulses from the next's
		float TestLeft = 0.f;                        // the console's test: seconds left of a demand held by hand
		FDemand Test;
		bool bTestAll = false;                       // ... or of every jet burning at once (to see where they are)
		FWake Wake;
		// what the drawing needs of her without asking the war again (set by the module each frame it reads her)
		int32 ShipId = -1;
		uint8 Faction = 0;                           // 0 ASTRA, 1 the Mandate, 2 the rest: the colour of her drive
		bool bPowered = true;                        // her jets and drive have power (a disabled ship is dark)
		uint32 Seen = 0;                             // the frame she was last read in: a ship no longer read is gone, and her wake fades where it is
		float Thrust = 0.f;                          // how hard her main drive works now (0..1)

		void Reset();
		bool Bind(const FJetClass* C);
	};

	/** Reads a ship's motion for one step of the battle (SimDt, s) and works the demand's parts. Pos/Vel/Att: the war's, system frame. MaxAccel (m/s^2) and MaxTurnRad (rad/s): the class's.
	 *  A jump in position or heading (a transit, the console putting the Aquila beside a place) is no manoeuvre: the memory is cleared. */
	ASTRA_API void Observe(FMotion& M, const FJetClass& C, const FVector& Pos, const FVector& Vel, const FQuat& Att, float MaxAccel, float MaxTurnRad, float SimDt);
	/** Fires what the demand asks (RealDt, s, real: the jets live on the screen's time even when the battle's is slowed): the kicks die away, the allocation is made, each jet comes up and goes out. */
	ASTRA_API void Fire(FMotion& M, const FJetClass& C, float RealDt);
	/** The demand now: the kick of a change of rate, the trim of a turn held, the push asked (what the main drive gives is not asked of the jets). */
	ASTRA_API FDemand DemandOf(const FMotion& M);
	/** Whether a jet is lit at this instant: a jet is pulsed (a thruster fires in bursts: the duty is its burn) so that a faint one blinks and a hard one burns steadily. Clock: real seconds. */
	ASTRA_API bool PulseOn(float Level, float Clock, float Phase);

	// ------------------------------------------------------------------------------------------------------------------ tests
	/** The unit tests (the bench's -motiontest and tools/space.py test): the allocation against physics, the observation of scripted manoeuvres, the wake, the data. True when all pass;
	 *  Fails says what did not, Notes what was measured. */
	ASTRA_API bool RunMotionTests(TArray<FString>& Fails, TArray<FString>& Notes);
}
