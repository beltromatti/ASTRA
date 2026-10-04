// ASTRA — what the war leaves in a system (SPAZIO-VIVO, docs/SPAZIO.md): the pieces of the hulls that broke, the field of debris that spreads from each, the lifepods that
// get away with their beacons and their few hours of air. Each ship lost is one SITE: who she was (name, class, id, how she went, when), what was left aboard, her pieces, her field,
// her pods. A wreck stays where it died: its place and its motion are a point and a velocity, an attitude and a spin, so where it is now is arithmetic (no simulation, no tick per
// object), what is far costs nothing, and what is not in view is kept for when it is.
//
// Plain C++ like the traffic (AstraSpaceLifeTraffic.h): deterministic for a seed, no engine objects, so the bench (AstraSpaceLifeSimCommandlet) can lose a fleet and run hours of drift
// in a moment. The sites are kept in the frame of the system's Janus Gate (its position and its axis), not in the battle's frame of the moment: the battle's origin is wherever the
// Aquila came in, the Gate does not move, so a wreck is where it was when the Captain comes back to the system, hours or a campaign later (the campaign's save carries them: the
// battle's SaveJson/ResumeFrom, "space").
//
// What the crew learns of them is facts (an event with a bearing, a range, a name, a count): the beacons heard, a close look at a wreck; what they may do about it is the war's own
// (search and rescue is the flight network's `sar` mission, which flies to the pods through UAstraSpaceLife::RescueGoal and picks them up with RescueTake). ABBORDAGGI and
// FLOTTA-VIVA read the same sites through UAstraSpaceLife::GetWrecks(): her class key (the plan data/ship/plans/<class>.json), her ship id, her pieces by section (0 bow, 1 mid, 2
// stern: the plan's own cut), and what was left aboard (FAboard: the people, and the rooms of her plan that were not as built when she went).

#pragma once

#include "CoreMinimal.h"
#include "Dom/JsonObject.h"
#include "AstraSpaceLifeTraffic.h"

namespace AstraSpace
{
	/** The frame the sites are kept in: the system's Gate (where it stands, which way its axis points). Without a Gate, the frame of the Aquila's arrival. */
	struct FSkyFrame
	{
		FVector Origin = FVector::ZeroVector;
		FQuat Att = FQuat::Identity;
		FVector ToSystem(const FVector& P) const { return Origin + Att.RotateVector(P); }
		FVector FromSystem(const FVector& P) const { return Att.UnrotateVector(P - Origin); }
		FVector DirToSystem(const FVector& D) const { return Att.RotateVector(D); }
		FVector DirFromSystem(const FVector& D) const { return Att.UnrotateVector(D); }
		FQuat ToSystem(const FQuat& Q) const { return (Att * Q).GetNormalized(); }
		FQuat FromSystem(const FQuat& Q) const { return (Att.Inverse() * Q).GetNormalized(); }
	};

	/** How a ship was lost (the war's EAstraFate, the three that leave a wreck). */
	enum class EHowLost : uint8 { Breakup, Reactor, Destroyed, Num };
	ASTRA_API const TCHAR* HowLostName(EHowLost H);
	ASTRA_API EHowLost HowLostFromName(const FString& Name);

	// ------------------------------------------------------------------------------------------------------------------ what was left aboard
	/** A room of her class plan that was not as built when she went (FFleetSnapshot::FRoom, the plan's compartments by index): 0..1 each. */
	struct FAboardRoom
	{
		int32 Comp = INDEX_NONE;
		float Air = 1.f, Hole = 0.f, Fire = 0.f, Smoke = 0.f, Heat = 0.f, Power = 1.f, Wreck = 0.f;
		bool bGutted = false, bLocked = false;
	};

	/** What was left aboard: the people and the rooms. The numbers are her inside's (FLOTTA-VIVA) when she had one, else an estimate from her class. */
	struct FAboard
	{
		int32 Complement = 0;            // how many people her class carries (data/ship/plans/<class>.json: roster.complement)
		int32 Alive = 0;                 // alive aboard (fit or wounded) when she went
		int32 Killed = 0;                // killed by the blows before that: their bodies are where they fell
		int32 Lost = 0;                  // alive aboard when she went and not got away: lost with her
		int32 Escaped = 0;               // got away in the lifepods
		bool bInside = false;            // the numbers are her inside's, not an estimate
		TArray<FAboardRoom> Rooms;       // the rooms not as built (a room not listed is as built: full air, no fire, full power)
		TArray<FString> SealedDoors;     // the pressure bulkheads that were shut (door ids of the plan)
	};

	// ------------------------------------------------------------------------------------------------------------------ what a loss brings in
	/** A piece of a broken hull as the war's effects have it at the moment of the break (system frame). */
	struct FPieceIn
	{
		uint8 Section = 0;                       // 0 bow, 1 mid, 2 stern
		FVector Pivot = FVector::ZeroVector;     // the piece's centre of mass (what it turns about)
		FVector PivotLocal = FVector::ZeroVector;// the same, in the section mesh's frame (m)
		FVector Vel = FVector::ZeroVector;
		FQuat Att = FQuat::Identity;
		FVector SpinAxis = FVector::UpVector;
		float SpinRate = 0.f;                    // rad/s
		float Radius = 50.f;
		bool bReactor = false;                   // thrown out by a reactor breach: charred
	};

	/** A ship lost, as this module needs to know it (the battle's death event in plain terms). Positions in the system frame. */
	struct FLoss
	{
		int32 ShipId = -1;
		FString Name, Class, Contact, KnownAs;   // "ASN Vigilant", "ASTRA destroyer", "T-02", and what the sensors called her at the end ("ASN Vigilant (T-02)", or "T-23")
		FString HullMesh;                        // her whole mesh (SM_SHIP_ASTRA_Vigilant): the sections are <HullMesh>_Sec<Bow|Mid|Stern>
		FName ClassKey;                          // the class of her plan: vigilant, praetorian, acheron...
		uint8 Faction = 0;                       // 0 ASTRA, 1 the Mandate, 2 anyone else (the Guilds)
		EHowLost How = EHowLost::Destroyed;
		uint8 Section = 1;                       // the section that let go (a break-up)
		FVector Pos = FVector::ZeroVector, Vel = FVector::ZeroVector;
		FQuat Att = FQuat::Identity;
		float Radius = 150.f;                    // m
		FVector BoxMid = FVector::ZeroVector;    // the hull box's centre (system frame), its half extents along her axes: where she is solid
		FVector BoxHalf = FVector(100.0, 20.0, 15.0);
		FAboard Aboard;
	};

	// ------------------------------------------------------------------------------------------------------------------ the records
	/** One piece of a hull: a section (or, when the war could not break her into sections, the whole hull burnt dark). It is where Pos0 puts it at T0 and moves as the arithmetic says. */
	struct FPieceRec
	{
		uint8 Section = 255;                     // 0 bow, 1 mid, 2 stern, 255 the whole hull
		FVector PivotLocal = FVector::ZeroVector;// m, the mesh's frame
		FVector Pos0 = FVector::ZeroVector;      // sky frame: the pivot at T0
		FVector Vel = FVector::ZeroVector;       // m/s
		FQuat Att0 = FQuat::Identity;            // sky frame: at T0
		FVector SpinAxis = FVector::UpVector;    // sky frame
		float SpinRate = 0.f;                    // rad/s
		double T0 = 0.0;                         // the wrecks' clock at which Pos0 and Att0 hold
		float Radius = 50.f;                     // m
		bool bBurnt = false;                     // charred by a reactor breach
		uint8 Seen = 0;                          // how much of what is aboard the crew has learned of this piece (saved: the minds remember it): 0 nothing, 1 the first look, 2 her rooms, 3 her dead
		bool bInFx = false;                      // (not saved) the war's effects still hold it as an actor, burning at the cut: this module draws it once they let go
		int32 SetIdx = -1;                       // (not saved) which set of instances draws it (-1 not asked yet, -2 its mesh is not there)
		int32 PlotId = -1;                       // (not saved) its contact on the plot (the battle's ship id), -1 while it is not on it: what is near the Aquila is a contact the crew can name and target
	};

	/** A lifepod. */
	struct FPodRec
	{
		FVector Pos0 = FVector::ZeroVector, Vel = FVector::ZeroVector;   // sky frame
		FQuat Att0 = FQuat::Identity;
		FVector SpinAxis = FVector::UpVector;
		float SpinRate = 0.f;                    // rad/s
		double T0 = 0.0;                         // launched
		float BeaconDelayS = 30.f;               // the beacon calls from T0 + this (it clears the wreck first)
		int32 Survivors = 0;
		float AirS = 0.f;                        // seconds of air from T0
		uint8 State = 0;                         // 0 adrift, 1 recovered, 2 the air ran out
		double EndedAt = 0.0;                    // when it was recovered
		FString By;                              // who recovered it ("the Wasps of the Aquila")
		int32 SetIdx = -1;                       // (not saved) which set of instances draws it (-1 not asked yet, -2 its mesh is not there)
	};

	/** The debris that spreads from where she went: chunks of hull in three shapes, each its own way and speed (deterministic for the seed: nothing of them is kept). */
	struct FFieldRec
	{
		int32 Count = 0;
		uint32 Seed = 0;
		FVector Pos0 = FVector::ZeroVector, Vel = FVector::ZeroVector;   // sky frame: where it began and how its middle drifts
		double T0 = 0.0;
		float R0 = 100.f;                        // the hull's radius at the start: the chunks begin inside it
		float Slow = 0.8f, Fast = 20.f;          // m/s: the slowest and the fastest chunk away from the middle
		float SizeK = 1.f;                       // the chunks' scale (1 = the meshes as made: 13 m a plate, 24 m a girder, 9 m a chunk)
		float EmberTauS = 70.f;                  // how fast the glow of the hot ones dies
		int32 SetIdx[3] = {-1, -1, -1};          // (not saved) which set of instances draws each shape (-1 not asked yet, -2 its mesh is not there)
	};

	/** A chunk of a field, evaluated: where it is, how it lies, how big, which shape (0 plate, 1 girder, 2 chunk), how much it still glows (0..1). */
	struct FChunk
	{
		FVector Pos = FVector::ZeroVector;       // sky frame
		FQuat Att = FQuat::Identity;
		float Size = 1.f;
		uint8 Shape = 0;
		float Ember = 0.f;
	};

	/** What a chunk is, fixed by the field's seed (made once, when a field comes near enough to be drawn). */
	struct FChunkDef
	{
		FVector3f Dir = FVector3f::ZeroVector;   // unit: the way it goes from the middle
		float Speed = 1.f;                       // m/s
		float Off = 0.f;                         // m: where in the hull it starts, along Dir
		FVector3f SpinAxis = FVector3f::UpVector;
		float SpinRate = 0.1f;
		FQuat4f Att0 = FQuat4f::Identity;
		float Size = 1.f;
		uint8 Shape = 0;
		float Heat = 0.f;                        // 0..1: how hot it began
	};

	/** One ship lost. */
	struct FSite
	{
		int32 Id = 0;
		FString System;                          // lower case
		int32 ShipId = -1;                       // the battle's id of the ship she was
		FString Name, Class, Contact, KnownAs, HullMesh;
		FName ClassKey;
		uint8 Faction = 0;
		EHowLost How = EHowLost::Destroyed;
		uint8 Section = 1;
		double DiedAt = 0.0;                     // the wrecks' clock when she went
		FVector Pos0 = FVector::ZeroVector, Vel = FVector::ZeroVector;   // sky frame: where she went and how she was going
		float Radius = 150.f;
		FAboard Aboard;
		TArray<FPieceRec> Pieces;
		FFieldRec Field;
		TArray<FPodRec> Pods;
		// what the crew has been told (saved: the minds remember it)
		bool bToldBeacon = false, bToldSilent = false, bToldClose = false;
		// not saved
		TArray<FChunkDef> Defs;                  // the field's chunks, made when it comes near
		bool bDirty = true;                      // its saved form is out of date
	};

	/** A lifepod's beacon as a rescuer wants it. */
	struct FBeacon
	{
		int32 Site = INDEX_NONE, Pod = INDEX_NONE;
		FVector Pos = FVector::ZeroVector, Vel = FVector::ZeroVector;   // system frame
		int32 Survivors = 0;
		double AirLeftS = 0.0;
		FString Of;                              // what the beacon says it is from ("ASN Vigilant")
		uint8 Faction = 0;
		bool bCalling = true;                    // its beacon is on (a pod just launched has not called yet: a pilot who is there sees it all the same)
	};

	/** What a rescue took aboard. */
	struct FRescued
	{
		int32 Pods = 0, Survivors = 0;
		FString Of;
		uint8 Faction = 0;
	};

	/** The numbers the bench and the console read. */
	struct FWreckStats
	{
		int32 Sites = 0, SitesHere = 0, Pieces = 0, Chunks = 0, Pods = 0, PodsAdrift = 0, PodsRecovered = 0, PodsLost = 0, Survivors = 0, Rescued = 0;
		int32 Losses = 0, Told = 0, Pruned = 0;
	};

	class ASTRA_API FWrecks
	{
	public:
		// ---- tuning (the module's own: nothing of the war's rules)
		static constexpr double BeaconKm = 90.0;                 // how far a beacon's call carries to the sensors
		static constexpr double CloseKm = 10.0;                  // how near the Aquila has to come to look at a wreck
		static constexpr double FieldKm = 3.0;                   // and to be said to be passing through a field
		static constexpr double HandOverS = 80.0;                // the war's effects burn a piece for about a minute (the cut faces cool in 60 s); after this it is a plain wreck
		static constexpr double PodAirS = 3.0 * 3600.0;          // what a lifepod's air lasts at best
		static constexpr int32 MaxSites = 72;                    // the most sites kept (all systems): the oldest without living pods go first
		static constexpr int32 RoomSites = 12;                   // the newest this many keep the rooms of their plan in the file (what a boarding of a wreck would use); the rest keep their counts
		static constexpr int32 MaxPods = 9;
		static constexpr int32 MaxChunks = 240;
		static constexpr double ContactKm = 60.0;                // a piece within this of the Aquila is a contact on the plot (and stays one to +10 km: no flicker at the edge)
		static constexpr int32 MaxContacts = 16;                 // the most wreck contacts on the plot at once, the nearest first (the plot's lists are read every frame by a dozen readers)
		static constexpr int32 ListedContacts = 4;               // and the most the crew's own state lists (the nearest, within ListedKm: the rest are on the plot for the screens)
		static constexpr double ListedKm = 40.0;

		// ---- the life of the sites
		void Reset();
		/** A ship is lost: her pieces (from the effects' own: none when the war could not break her), her field and her lifepods are recorded in the Gate's frame. Returns the site. */
		const FSite& AddLoss(const FString& System, const FLoss& Loss, const TArray<FPieceIn>& Pieces, double Now, uint32 Seed, const FSkyFrame& Frame);
		/** The sites of a system seen from the Aquila (and from the Captain's Falcon when it flies: pass its position, else null): what the crew is told (beacons heard, the air that ran out,
		 *  a close look), the pods whose air has run out. One pass over the sites. bFight: the Aquila is in an engagement: what is told is told as news and not as a report (it does not take the
		 *  crew's turn from the fight; the silence of a beacon and a rescue always do). */
		void Think(const FString& System, double Now, const FSkyFrame& Frame, const FVector& Aquila, const FVector* Falcon, bool bFight, TArray<FEvent>& Out);
		/** A piece's effects have let go: from now on its own arithmetic carries it (system frame state taken from the effects' piece). */
		void ReAnchor(FSite& Site, FPieceRec& P, double Now, const FSkyFrame& Frame, const FVector& Pivot, const FVector& Vel, const FQuat& Att, const FVector& SpinAxis, float SpinRate);
		/** Everything of the sites in the system is as the clock says: the pods whose air has run out are silent. (Think does it for what it reads; this for a system just entered.) */
		void Settle(double Now);

		// ---- where things are (all in the sky frame: Frame.ToSystem to draw)
		static FVector PosAt(const FPieceRec& P, double Now) { return P.Pos0 + P.Vel * (Now - P.T0); }
		static FQuat AttAt(const FPieceRec& P, double Now);
		static FVector PosAt(const FPodRec& P, double Now) { return P.Pos0 + P.Vel * (Now - P.T0); }
		static FQuat AttAt(const FPodRec& P, double Now);
		/** Where a site is, as a point: her middle (pieces' mean), for the crew's account. */
		FVector Middle(const FSite& S, double Now) const;
		/** A field's radius at a time: how far its farthest chunk has got from its middle. */
		static float FieldRadiusAt(const FFieldRec& F, double Now);
		/** How a lifepod lies and turns is a thing of its site's seed and its index (nothing of it is saved): its nose along its way, a slow tumble. */
		static void PodPose(uint32 SiteSeed, int32 Index, const FVector& Vel, FQuat& Att0, FVector& SpinAxis, float& SpinRate);
		/** Makes a site's chunk definitions (once). */
		static void MakeDefs(FSite& S);
		/** One chunk (deterministic for the seed): false for an index out of range or a field not yet begun. MakeDefs first. bAtt false leaves Att alone (how it lies is the dearer half of it:
		 *  the drawing asks for it only for the chunks it is about to send). */
		static bool ChunkAt(const FSite& S, int32 Index, double Now, FChunk& Out, bool bAtt = true);
		static FQuat ChunkAttitude(const FSite& S, int32 Index, double Now);
		/** A lifepod's beacon calls: launched, its beacon started, air left, not recovered. */
		static bool BeaconOn(const FPodRec& P, double Now) { return P.State == 0 && Now >= P.T0 + P.BeaconDelayS && Now < P.T0 + P.AirS; }
		static double AirLeft(const FPodRec& P, double Now) { return FMath::Max(0.0, P.T0 + P.AirS - Now); }
		/** True while a lifepod is adrift with air left (whether or not its beacon calls yet). */
		static bool Alive(const FPodRec& P, double Now) { return P.State == 0 && Now < P.T0 + P.AirS; }

		// ---- the records
		const TArray<FSite>& Sites() const { return Items; }
		TArray<FSite>& SitesMutable() { return Items; }
		const FSite* FindById(int32 Id) const;
		/** A site by the battle's id of the ship she was (the latest, if the ids were reused: a new campaign), or by her contact id in a system. */
		const FSite* FindByShip(int32 ShipId, const FString& System = FString()) const;
		const FSite* FindByContact(const FString& Contact, const FString& System = FString()) const;
		/** The sites of a system. */
		void Of(const FString& System, TArray<int32>& OutIndices) const;
		/** What a loss was, in the crew's words (facts only): what it was, how it went, how long ago, what is known of it now. Piece: an index into the site's pieces, or -1 for the site as a whole. */
		FString Describe(const FSite& S, int32 Piece, double Now) const;
		// ---- a piece as a contact of the plot (docs/SPAZIO.md §3bis): what the crew calls it, its number, the mesh that is drawn for it
		/** "stern section of ASN Vigilant", "wreck of ASN Vigilant": what the crew names (the name she was known by when she went, without the contact number). */
		static FString PieceName(const FSite& S, int32 Piece);
		/** "W-02S": the dead ship's own number (T-02) with a W for the wreck and a letter for the piece (B bow, M middle, S stern; none for a whole hull). A ship that had no number: "W-<site>". */
		static FString PieceContactId(const FSite& S, int32 Piece);
		/** The mesh a piece is drawn as (SM_SHIP_ASTRA_Vigilant_SecStern; her whole hull for a piece that is not a section): its solids (art/blender/space3_solids.py) are under the same name. */
		static FString PieceMesh(const FSite& S, int32 Piece);
		/** How much of what is inside a piece a look from this range can make out: 0 nothing, 1 the hull (the first look), 2 the rooms (4 km), 3 the dead (800 m: alongside). */
		static int32 StageForRange(double RangeM);
		/** What an investigation of a piece learns at a stage (1..3), in the crew's words (facts only: what was aboard when she went, from her inside's own books where she had one). Stage 1 is Describe's
		 *  account of the piece; 2 and 3 carry no name (the caller says whose they are). */
		FString Findings(const FSite& S, int32 Piece, int32 Stage, double Now) const;
		/** The same for several pieces of one wreck seen together (a flight that comes up on her bow, her middle and her stern): one account, the hull's torn ends, her rooms (all of her: the pieces are together about so much
		 *  of her), her dead (about so many of them in these pieces). One piece: Findings. */
		FString FindingsOfPieces(const FSite& S, const TArray<int32>& Pieces, int32 Stage, double Now) const;
		/** "the bow, middle and stern sections of ASN Vigilant": what the crew names several pieces of one wreck together (one piece: "the stern section of ASN Vigilant"). */
		static FString PieceList(const FSite& S, const TArray<int32>& Pieces);
		/** A piece's status for the crew's list of contacts: lost when and how, no power, tumbling, how much has been looked into. */
		FString Status(const FSite& S, int32 Piece, double Now) const;
		/** The share of a class's structure that is in a section (0 bow, 1 middle, 2 stern): about the share of her people and rooms that were in that piece of her (data/war/classes.json: sections). */
		static float SectionShare(FName ClassKey, uint8 Section);
		/** "2 h 40 min", "35 min", "50 s": how long a thing has been so, or has to go (the crew's way of saying it). */
		static FString Span(double Seconds);
		/** The beacons that call in a system now (the sensors' reach is the caller's: From and RangeKm; RangeKm <= 0: all). Nearest first. bAdrift: every pod that is adrift with air, whether its beacon has
		 *  begun to call or not (what the Captain's Falcon sees with her own eyes; FBeacon::bCalling says which). */
		void Beacons(const FString& System, double Now, const FSkyFrame& Frame, const FVector& From, double RangeKm, TArray<FBeacon>& Out, bool bAdrift = false) const;
		/** "ASN Vigilant" from "ASN Vigilant (T-02)": how the sensors called a ship at the end is not how the crew names her. */
		static FString BareName(const FString& KnownAs);
		/** Lifepods within RadiusM of a point (system frame) that are adrift are taken aboard by `By`. Returns what was taken. */
		FRescued Recover(const FString& System, double Now, const FSkyFrame& Frame, const FVector& AtSystem, double RadiusM, const FString& By);
		/** People in lifepods that still have air, in a system (the Captain's duty to know). */
		int32 SurvivorsAdrift(const FString& System, double Now) const;
		FWreckStats Stats(const FString& System, double Now) const;
		/** The most that can be held: drops the oldest sites without living pods, and those that have drifted out of any system's reach (see the .cpp). */
		void Prune(double Now);

		// ---- the file
		/** The people and the rooms aboard in the file's form (the rooms of her plan only when bRooms), and back: what a site keeps of her inside, shared with the hulks left behind (AstraDerelicts.h). */
		static TSharedRef<FJsonObject> AboardToJson(const FAboard& Ab, bool bRooms);
		static void AboardFromJson(const TSharedPtr<FJsonObject>& O, FAboard& Ab);
		/** The sites as the campaign's save keeps them (a compact form: arrays of numbers, see docs/SPAZIO.md); Now is saved as the clock. */
		TSharedRef<FJsonObject> ToJson(double Now);
		/** Reads them back. OutClock: the clock at the save. False when the object is not a wrecks save. */
		bool FromJson(const TSharedPtr<FJsonObject>& J, double& OutClock);

		/** The rules for how many pods get away and how many chunks of debris a hull leaves. */
		static int32 PodCountFor(EHowLost How, int32 Complement, int32 Alive, FRandomStream& Rng);
		static int32 ChunkCountFor(float RadiusM, EHowLost How);
		/** What a class carries when her inside cannot say (the table of the plans' rosters). */
		static int32 ComplementOf(FName ClassKey, float RadiusM, uint8 Faction);

	private:
		TArray<FSite> Items;
		int32 NextId = 1;
		int32 Losses = 0;
		int32 Told = 0;
		int32 Taken = 0;
		int32 Pruned = 0;
		/** The saved form of each site is kept until the site changes (a save every minute does not remake what has not moved). */
		struct FSaved
		{
			TSharedPtr<FJsonObject> Json;
			bool bRooms = false;                                 // the rooms of her plan are in it
		};
		TMap<int32, FSaved> JsonCache;
		TSharedRef<FJsonObject> SiteJson(FSite& S, bool bRooms) const;
		static bool SiteFromJson(const TSharedPtr<FJsonObject>& J, FSite& Out);
	};

	/** The bearing (degrees about +Z from +X) and the mark (up from the plane) from a point to another, as the helm and the sensors give them. */
	ASTRA_API double BearingDegFromTo(const FVector& From, const FVector& To);
	ASTRA_API double MarkDegFromTo(const FVector& From, const FVector& To);

	/** The module's own tests of the records (AstraWrecksTest.cpp): the accounting of survivors, determinism, motion, the file, the limits, what the crew is told, the rescue, the hand-over, and the
	 *  tables that must agree with the plans. Fails and Notes get what went wrong and what was measured; true when nothing did. The commandlet's -wrecktest. */
	ASTRA_API bool RunWreckTests(TArray<FString>& Fails, TArray<FString>& Notes);
}
