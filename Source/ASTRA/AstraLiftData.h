// ASTRA — the lift network's data (docs/ASCENSORI.md): the shafts and the Spine shuttle of the ship's plan (`vertical[]` and `transit[]`,
// version 2: docs/brief/NAVE-3.md), read from the plan file or from a test plan (data/ship/test/lifts_fixture.json) by a worker thread, then
// handed to the subsystem that builds the lifts out of it.
//
// A "line" is one car on one path: a turbolift in its shaft (bottom to top) or the shuttle on its line (first stop to last). Its stops are
// the landings, sorted along the path. Everything here is world cm (the plan's metres times 100: same axes, the origin under the Captain's chair).

#pragma once

#include "CoreMinimal.h"
#include "AstraLiftBrain.h"

/** `stat Lifts`: where the game thread's time goes among the lifts. */
DECLARE_STATS_GROUP(TEXT("Lifts"), STATGROUP_AstraLifts, STATCAT_Advanced);

enum class EAstraLiftKind : uint8 { Turbolift, Bridge, Service, Cargo, Shuttle };

/** A landing of a shaft, or a stop of the shuttle. */
struct FAstraLiftStop
{
	int32 Deck = 0;                           // the lobby's deck (the plan's number); the shuttle's stops stand on Deck 5
	FString Id;                               // "d4"; the shuttle: "sec_a"
	FString Label;                            // what the panel says: "DECK 4", "SECTION A"
	FString DeckName;                         // "Crew Services"
	FString Section;                          // the shuttle's: "A"
	FVector DoorCm = FVector::ZeroVector;     // the middle of the opening, on the floor (world cm)
	float DoorYaw = 0.f;                      // the plan's yaw of the door (90: a door in a wall that runs along x)
	FVector Out = FVector::ForwardVector;     // the horizontal unit vector from the car into the lobby
	float WallCm = 0.f;                       // how far the door's plane stands out of the shaft's inside face: the lobby's wall the landing bridges (0: a door in the face)
	float S = 0.f;                            // cm along the path where the car stands for this stop
	float FloorZ = 0.f;                       // the floor of the lobby
	FString Lobby, NodeId;                    // the plan's compartment and graph node
	FVector NodeCm = FVector::ZeroVector;     // the node's place (where the crew waits); zero when the plan has none
	bool bNode = false;
	TArray<FString> Places;                   // the notable rooms of the deck, for the car's screen and the Captain's voice

	/** Where someone waits for the car: the plan's node, else 1.2 m in front of the door. */
	FVector WaitCm() const { return bNode ? NodeCm : DoorCm + Out * 120.f; }
};

struct FAstraLiftLine
{
	FString Id, Name;
	EAstraLiftKind Kind = EAstraLiftKind::Turbolift;
	bool bShuttle = false;
	FAstraLiftPath Path;                      // where the car's origin (the floor under its middle) goes
	FVector ShaftCm = FVector::ZeroVector;    // the shaft's middle (x, y; z the bottom landing)
	float ShaftW = 0.f, ShaftD = 0.f;         // inside the shaft (cm): W across the door, D along its normal
	float ZBottom = 0.f, ZTop = 0.f;          // the shaft's lowest and highest landing floors (world cm)
	float CarW = 240.f, CarD = 240.f, CarH = 260.f;
	float CarLength = 0.f;                    // the shuttle's car, along its line
	float CarFloor = 0.f;                     // the car's floor over the stop's (the shuttle's low step)
	float SpeedCmS = 800.f, AccelCmS2 = 250.f;
	FVector Front = FVector::ForwardVector;   // the car's door side: from the car into the lobby, the same at every stop
	float FrontYaw = 0.f;
	TArray<FAstraLiftStop> Stops;             // by distance along the path

	int32 FindStopByDeck(int32 Deck) const;
	int32 FindStopById(const FString& StopId) const;
	/** The car's origin when it stands at a stop. */
	FVector CarAt(int32 Stop) const { return Path.At(Stops[Stop].S); }
	/** The Captain's deck number of a point on the path: the stop it is at or has just left (a lift between two decks says the one below). */
	int32 StopBelow(float S) const;
	bool IsVertical() const { return !bShuttle; }
};

struct FAstraLiftNetwork
{
	TArray<FAstraLiftLine> Lines;
	TArray<FString> Problems;                 // what the plan got wrong: a door off its shaft's wall, a car that does not fit
	TArray<FString> Notes;
	FString Source;

	/** Reads the lifts out of a plan file (or the test fixture). False when the file is missing or does not parse; a plan with no lifts of
	 *  version 2 loads as an empty network (the older lift is not a shaft). */
	bool Load(const FString& Path);
	/** The plan the game uses: the one staged with it, else the repository's. */
	static FString DefaultPlanFile();

	int32 FindLine(const FString& Id) const;
	/** A walking route's two ends are the ends of a lift ride when they are the waiting places of two stops of one line. */
	bool FindRide(const FVector& A, const FVector& B, int32& OutLine, int32& OutFrom, int32& OutTo, float TolCm = 90.f) const;
};
