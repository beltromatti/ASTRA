// ASTRA — DISTRUZIONE: the few types the ship, the damage model, the screens and the life simulation share (docs/DISTRUZIONE.md):
// an incident inside the hull and the blow that caused it. Kept apart from the ship subsystem so the model, which the ship owns,
// can name them without including it.

#pragma once

#include "CoreMinimal.h"

/** One incident inside the hull, as damage control and the crew's screens see it: a hazard in one compartment of the ship's plan (a
 *  hole open to space, a fire, power lost) and the team working on it. The damage model (AstraDamageModel.*) owns the physics and keeps the
 *  list; the ship subsystem moves the teams (travel, work). Deck and section are the compartment's own (the crew still says "deck 4,
 *  section B"); Place is its name. */
struct FAstraDamage
{
	int32 Id = 0;
	int32 Deck = 1;
	TCHAR Section = TEXT('A');
	FString Kind;               // "hull breach" | "fire" | "conduit damage" | "radiator damage"
	FString System;             // conduit damage: the systems that lose power through it ("shields, weapons")
	int32 Team = -1;            // damage-control team on it (0..3), -1 = unattended
	float Travel = 0.f;         // s until the team is on scene
	float Travel0 = 0.f;        // s the walk took from the teams' station (Deck 6) when it was sent: the holo table moves it
	float Work = 30.f;          // s of work on scene
	float Progress = 0.f;       // 0..1
	float SpreadT = 25.f;       // (kept for the old layer's callers: unused)
	// --- DISTRUZIONE: where it is, how bad it is
	int32 Comp = INDEX_NONE;    // the compartment in the damage model's map (INDEX_NONE: an incident of the old kind, a deck and section only)
	FName CompId;               // the plan's id of that compartment ("d4_galley_B1"): the party's destination
	FString Place;              // its name ("Main Galley")
	float Severity = 0.f;       // 0..1: the hole's size, the fire's strength, the share of power lost (the damage list's order and the work's length)
	float Baseline = 0.f;       // what it was when the team arrived (the progress is measured against it)
	FString Note;               // a few words on how it stands now ("containment field holding", "venting", "spreading")
	FString Where() const
	{
		return Place.IsEmpty() ? FString::Printf(TEXT("deck %d section %c"), Deck, Section)
		                       : FString::Printf(TEXT("deck %d section %c (%s)"), Deck, Section, *Place);
	}
};

/** A blow on the Aquila's hull, as the war model hands it to the ship (ApplyHitModel): where it struck, which way it came, what the
 *  shields, the plate and the structure took, and what is left of it for what lives behind the plating. The ship's frame is the hull
 *  mesh's own (metres, X to the bow, Y to starboard, Z up, the mesh's origin). */
struct FAstraHullHit
{
	FVector HullM = FVector::ZeroVector;      // where it struck
	FVector Box = FVector::ZeroVector;        // the same point on the hull's box, -1..1 along each axis (the face struck is the axis at +-1)
	FVector Dir = FVector::ForwardVector;     // the way it travelled (unit)
	int32 Facing = 0;                         // AstraWar::EFacing: bow, stern, port, starboard, dorsal, ventral
	int32 Section = 1;                        // AstraWar::ESection: bow, mid, stern (the war's: the structure that took it)
	uint8 Type = 0;                           // EAstraDamageType: 0 kinetic, 1 energy, 2 explosive
	uint8 Kind = 0;                           // EAstraHitKind
	float Damage = 0.f;                       // the blow
	float ShieldTook = 0.f, PlateTook = 0.f, StructTook = 0.f;
	float Felt = 0.f;                         // what the hull felt of it: the structure's share and a quarter of the plate's
};
