// ASTRA — the hulks the Aquila leaves behind (SPAZIO-VIVO, docs/SPAZIO.md §3ter): a ship the war disabled (no power, drifting: a derelict that a boarding could take) or a dead station or freighter a beat put
// in the system. When the Aquila leaves a system they are recorded where they were and as they were, in the frame of the system's Janus Gate (like the wrecks: AstraWrecks.h); when she comes back the plot
// makes them again from the records, and the crew finds them where they were left. The campaign's save carries the records with the wrecks.
//
// What a record keeps is what the war needs to make her again: who she was (her name, her class, her contact number), her side and what the Aquila's sensors knew of her, where she lay and how she turned,
// and, for a warship, what was left of her (her structure by section, her plates, her systems: the war's own model, so that she comes back as hurt as she went) and of the people aboard (what FLOTTA-VIVA
// counted when she was left: the dead where they fell, the rooms as they were: what a boarding would find).
//
// A hulk with way on her does not drift for ever. The war leaves a disabled ship the speed she had (a few hundred metres a second) and, left to the arithmetic, she would be a thousand kilometres away within the
// hour and no Aquila would ever find her again. What a system does with a hulk nobody has in tow is its own traffic's business: the tugs of Keeper Station and the Gate's field catch her and park her. The record says
// so as arithmetic: her velocity falls away as e^(-t/BrakeS), so she comes to rest at most her way times BrakeS from where she was left (150 s: 45 km for the fastest). While the Aquila is in the system the war's
// own rules carry her, unchanged: the braking is only what is told of the time the Aquila was away. BrakeS 0 gives the war's drift.
//
// Plain C++ like the wrecks and the traffic: no engine objects, deterministic, so the bench and the unit tests (RunDerelictTests) can ask of it.

#pragma once

#include "CoreMinimal.h"
#include "Dom/JsonObject.h"
#include "AstraWrecks.h"

namespace AstraSpace
{
	/** One hulk, recorded. */
	struct FDerelict
	{
		int32 Id = 0;
		FString System;                          // lower case
		int32 ShipId = -1;                       // the battle's id she had (a ship made again has a new one; her contact number is kept when it is free)
		FString Name, Class, Contact, Mesh;      // Class is the war's own text ("Kharon Mandate frigate, Lethe class"); Mesh her hull's (SM_SHIP_MANDATE_Lethe)
		FName ClassKey;                          // the war's model of her class (none for a hulk the war made no model of: a listening post, a freighter's shell)
		uint8 Side = 2;                          // 0 ASTRA, 1 the Mandate, 2 neither (the war's EAstraSide order)
		bool bModel = false;                     // the war had a model of her: she comes back with her sections, plates and systems as they were
		bool bHostile = false;
		bool bFog = false;                       // the Aquila's sensors had to find her (a Mandate ship under the fog of war): she must be found again; not: she is on the plot as she was, always
		bool bIdentified = true, bClassified = true;
		bool bToldBack = false;                  // the crew has been told she is still here (saved: the minds remember it)
		bool bDisabledShip = true;               // the war's disabled ship (no power: DisableShip); not: a beat's dead hulk (bDerelict)
		double T0 = 0.0;                         // the wrecks' clock when she was recorded
		FVector Pos0 = FVector::ZeroVector, Vel = FVector::ZeroVector;   // the Gate's frame
		FQuat Att0 = FQuat::Identity;
		FVector SpinAxis = FVector::UpVector;    // the Gate's frame
		float SpinRate = 0.f;                    // rad/s
		float Radius = 150.f;
		float HullFrac = 1.f;                    // what is left of her hull (a hulk the war made no model of)
		float Structure[3] = {1.f, 1.f, 1.f};    // by section, 0..1
		float Plates[18] = {};                   // by section and facing (3 x 6), 0..1
		float Sys[6] = {1.f, 1.f, 1.f, 1.f, 1.f, 1.f};
		uint8 Gutted = 0;                        // a bit for each section that had been gutted
		int32 Missiles = 0, Torpedoes = 0;
		FAboard Aboard;                          // what was left aboard when she was recorded: the living and the dead, the rooms as they were
		bool bFound = false;                     // (not saved) she was made again in this visit
	};

	/** The records of the hulks left in every system. */
	class ASTRA_API FDerelicts
	{
	public:
		static constexpr int32 MaxHulks = 24;                    // the most kept (all systems): the oldest go first
		static constexpr double DefaultBrakeS = 150.0;

		/** The time a hulk with way on her takes to be brought to rest (s); 0 leaves her the war's drift. */
		static double BrakeS();
		static void SetBrakeS(double Seconds);
		static FVector PosAt(const FDerelict& D, double Now);
		static FVector VelAt(const FDerelict& D, double Now);
		static FQuat AttAt(const FDerelict& D, double Now);

		void Reset();
		/** Adds a record (it takes the next id); the oldest go if there are too many. */
		const FDerelict& Add(const FDerelict& D);
		/** Takes the records of a system out and gives them back: the plot makes them again, so the plot, not the record, holds them from then on. */
		void Take(const FString& System, TArray<FDerelict>& Out);
		/** What is recorded of a system becomes these (the hulks the plot holds as the Aquila leaves, or as the campaign is saved). */
		void Replace(const FString& System, const TArray<FDerelict>& Hulks);
		const TArray<FDerelict>& All() const { return Items; }
		int32 CountOf(const FString& System) const;

		/** The records as the campaign's save keeps them (a compact form: whole numbers in units of their own), and back; false when the object is not a record of hulks. */
		TSharedRef<FJsonObject> ToJson() const;
		bool FromJson(const TSharedPtr<FJsonObject>& J);

	private:
		TArray<FDerelict> Items;
		int32 NextId = 1;
	};

	/** The module's own tests of the records (AstraDerelicts.cpp, run with the wreck tests): the braking arithmetic, the file, the limits. True when nothing failed. */
	ASTRA_API bool RunDerelictTests(TArray<FString>& Fails, TArray<FString>& Notes);
}
