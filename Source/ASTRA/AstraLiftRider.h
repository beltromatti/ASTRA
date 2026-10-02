// ASTRA — a person's ride in a real lift car (docs/ASCENSORI.md §5, the crew who use the lifts as the Captain does).
//
// A rider is a small state machine that takes any actor from one landing to another through a lift as a person would: it presses the call, waits for a car that
// stands there with its doors open and heads its way, takes a place in it (never the Captain's), walks in, rides with the floor, and walks out where the doors open at its
// stop. The actor is moved on its feet while it walks and attached to the car while it rides, so it travels with the car exactly, whatever its tick rate. The doors never
// close on a rider: while it walks it is a walker of the doors (AstraDoors), which the car's doorway check reads.
//
// It is the same code in the game (a body of the life simulation: AstraLifeBody.cpp) and in the offline bench (a stand-in actor: AstraLiftSim `riders`). It asks the lift
// subsystem for everything it needs (the rider API of UAstraLiftSubsystem) and does not know the simulation, the plan or the Captain.

#pragma once

#include "CoreMinimal.h"

class AActor;
class AAstraLiftCar;
class UAstraLiftSubsystem;

class ASTRA_API FAstraLiftRider
{
public:
	enum class EStep : uint8
	{
		None,          // not riding
		Wait,          // at the landing, the call pressed, standing
		Board,         // walking into the car (the doors are open)
		Inside,        // in the car, attached to it, standing
		Alight,        // the doors are open at their stop: walking out
		Done,          // at the landing they were going to
		Failed         // gave up (the car never came, the lift went away): the owner puts them where their route says
	};

	/** Starts a ride at the landing From of a line, to the landing To. The actor stands near the landing's waiting place; FinishCm is where it is going when it steps out (the
	 *  route's own point at the other end). False when the lift cannot be used now (no car there). */
	bool Begin(UAstraLiftSubsystem* InLifts, AActor* InBody, int32 InWho, int32 InLine, int32 InFrom, int32 InTo, const FVector& InFinishCm);
	/** Advances by Dt seconds: moves and attaches the actor. WalkCmS: how fast this person walks. */
	EStep Tick(float Dt, float WalkCmS);
	/** Lets go at once: the place freed, the actor detached and no longer a walker of the doors (the body returns to the pool, the plan changed, the person fell). */
	void End();
	/** End, and not riding any more (a finished or failed ride has been seen to). */
	void Clear() { End(); Phase = EStep::None; }

	EStep Step() const { return Phase; }
	bool Active() const { return Phase != EStep::None && Phase != EStep::Done && Phase != EStep::Failed; }
	/** On its feet and moving (the walk cycle), or standing (the idle one). */
	bool Walking() const { return Phase == EStep::Board || Phase == EStep::Alight; }
	/** The way they face (degrees, world): to the doors while they wait, the way they walk, the doors of the car while they ride. */
	float FacingYaw() const { return Yaw; }
	bool IsAttached() const { return bAttached; }
	int32 Line() const { return LineIdx; }
	int32 From() const { return FromStop; }
	int32 To() const { return ToStop; }
	int32 Slot() const { return SlotIdx; }
	/** Seconds spent at the landing before the doors opened for them, and in the car: for the bench's statistics. */
	float WaitedS() const { return WaitedAt; }
	float RodeS() const { return RodeFor; }
	const TCHAR* StepName() const;

private:
	UAstraLiftSubsystem* Lifts = nullptr;
	TWeakObjectPtr<AActor> Body;
	int32 Who = INDEX_NONE;
	int32 LineIdx = INDEX_NONE, FromStop = INDEX_NONE, ToStop = INDEX_NONE, SlotIdx = INDEX_NONE;
	EStep Phase = EStep::None;
	FVector Finish = FVector::ZeroVector;
	float Yaw = 0.f;
	float InStep = 0.f;                    // seconds in this step
	float RecallT = 0.f;                   // since the call (or the stop) was pressed last
	float WaitedAt = 0.f, RodeFor = 0.f;
	bool bAttached = false;
	bool bWalker = false;
	/** The way in or out: points in the car's frame (so that they follow the car), the next one to reach. */
	TArray<FVector, TInlineAllocator<4>> Way;
	int32 WayAt = 0;

	AAstraLiftCar* Car() const;
	void SetStep(EStep S);
	void Attach(AAstraLiftCar* C);
	void Detach();
	void SetWalker(bool bOn);
	void ArrangeBoarding(AAstraLiftCar* C);
	void ArrangeLeaving(AAstraLiftCar* C);
	/** One step of the walk toward a point (world), Z included. True when it is reached. */
	bool WalkTo(AActor* A, const FVector& Goal, float Dt, float WalkCmS);
};
