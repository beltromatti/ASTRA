// ASTRA — the lifts' brain (docs/ASCENSORI.md): pure code, no actors. A car on a path: a smooth motion profile, the doors' timing and the
// dispatch of the calls (collective control: the car keeps its heading while there is a stop ahead, stops for the calls that go its way and
// for the ones made from inside, turns round at the last one). The same brain runs a shaft in the game (AAstraLiftCar ticks it, so the car
// has moved before the Captain's own movement of the frame) and in the offline bench (AstraLiftSim), which runs an hour of rush hour in a
// second.
//
// Everything is in centimetres and seconds along a path (a shaft: bottom to top; the shuttle line: first stop to last).

#pragma once

#include "CoreMinimal.h"

/** A polyline in world cm and the distance along it. */
struct ASTRA_API FAstraLiftPath
{
	TArray<FVector> Pts;
	TArray<float> Cum;        // arc length at each point
	float Length = 0.f;

	void Build(const TArray<FVector>& InPts);
	bool IsValid() const { return Pts.Num() >= 2 && Length > 1.f; }
	/** The point and the direction of travel at an arc length (clamped to the path). */
	FVector At(float S) const;
	FVector Tangent(float S) const;
	/** The arc length of the point of the path nearest to P. */
	float Project(const FVector& P) const;
};

/** A smooth move from rest to rest over a distance: the speed rises with a smoothstep to the peak, holds it, and falls the same way, so the
 *  acceleration starts and ends at zero (nothing jerks: a soft push on leaving and on stopping, nothing in between). Closed form: the position
 *  at any time is exact, with no integration. The peak speed is the line's or, on a short hop, what the distance allows. */
struct ASTRA_API FAstraLiftProfile
{
	float D = 0.f;     // the whole move (cm)
	float Vc = 0.f;    // its peak speed (cm/s)
	float Ta = 0.f;    // the time of each ramp (s)
	float Tc = 0.f;    // the time at the peak speed (s)
	float T = 0.f;     // the whole time (s)

	static FAstraLiftProfile Make(float Dist, float Vmax, float Accel);
	float Pos(float t) const;
	float Vel(float t) const;
	float Acc(float t) const;
	bool Cruising(float t) const { return t >= Ta && t < Ta + Tc; }
	/** The move is over a different distance (a stop asked for on the way, a few metres sooner): possible only while cruising and with the
	 *  braking still to begin at least Guard seconds from now. False leaves the profile as it was. */
	bool Retarget(float t, float NewD, float Guard);
};

/** What happened in the brain since the owner last looked: sounds, streaming requests and notices hang on these. */
struct FAstraLiftEvent
{
	enum class EType : uint8
	{
		Depart,        // Landing -> Other (a leg begins)
		Retarget,      // the leg now ends at Landing (a stop asked for on the way)
		Arrive,        // the car stands at Landing
		Held,          // at Landing, the deck is not there yet: the doors wait shut
		Forced,        // the deck was made ready (blocking) at Landing
		DoorsOpening,
		DoorsOpen,
		DoorsClosing,
		DoorsReopen,   // someone stepped into the doorway: the doors go back
		DoorsClosed,
		Call,          // a hall call was made at Landing (Other: the direction)
		CarCall,       // a stop was chosen from inside (Landing)
	};
	EType Type = EType::Depart;
	int32 Landing = INDEX_NONE;
	int32 Other = 0;
};

class ASTRA_API FAstraLiftBrain
{
public:
	enum class EState : uint8 { Idle, Moving, Hold, Opening, Open, Closing };

	struct FConfig
	{
		float VmaxCmS = 800.f;       // peak speed
		float AccelCmS2 = 250.f;     // peak acceleration
		float DoorS = 1.1f;          // the doors' travel
		float DwellS = 3.5f;         // how long they stay open once open
		float BoardedDwellS = 1.2f;  // ... after somebody inside chose a stop
		float HeldForceS = 6.f;      // how long the doors wait for a deck that is not ready before it is made ready
		float RetargetGuardS = 0.4f; // a stop is not added on the way if the braking would have to begin sooner than this
	};

	/** The world around the car, as the owner gives it. Anything left unset is the empty answer (nobody in the doorway, every deck ready). */
	struct FHooks
	{
		TFunction<bool(int32)> DoorwayBusy;      // someone is in the doorway at this landing
		TFunction<bool(int32)> DeckReady;        // the deck behind this landing is in the world
		TFunction<void(int32)> WantDeck;         // a leg to this landing begins: its deck will be needed
		TFunction<void(int32)> ForceDeck;        // the last resort: the deck is loaded now
		TFunction<bool()> Full;                  // no room for anyone else aboard: the car passes the calls from the landings (the weight bypass of a real lift)
	};

	/** The landings' distances along the path, ascending; the car begins at StartLanding with the doors shut. */
	void Init(const TArray<float>& InLandingS, int32 StartLanding, const FConfig& InCfg, FHooks InHooks);
	bool IsReady() const { return LandingS.Num() >= 2; }

	/** The car's own time. Dt is cut into steps of at most 0.05 s, so a hitch of a frame does not skip a state. */
	void Tick(float Dt);

	/** A button: from a landing (Dir +1 up the path, -1 down it, 0 either) and from inside the car. */
	void HallCall(int32 Landing, int32 Dir);
	void CarCall(int32 Landing);
	/** Forget every call (a car taken out of service, a test). */
	void ClearCalls();

	// ---- what the car is doing
	EState State() const { return Mode; }
	float S() const { return Pos; }
	float V() const { return Vel; }
	float DoorOpen() const { return Door; }
	/** The landing the car stands at (doors may be open, opening or shut), INDEX_NONE while it moves. */
	int32 AtLanding() const { return At; }
	/** +1 up the path, -1 down it, 0 while nothing is asked of the car. */
	int32 Heading() const { return Head; }
	/** The end of the leg in progress (INDEX_NONE when not moving). */
	int32 LegTarget() const { return LegTo; }
	float LegRemainingS() const { return Mode == EState::Moving ? FMath::Max(0.f, Leg.T - LegT) : 0.f; }
	/** Nothing to do and nothing to animate: parked, the doors shut, no call: the owner may stop ticking it. */
	bool Quiet() const { return Mode == EState::Idle && !AnyRequest(); }
	bool AnyRequest() const;
	bool HasCarCall(int32 L) const { return CarCalls.IsValidIndex(L) && CarCalls[L]; }
	bool HasHallCall(int32 L, int32 Dir) const;
	int32 NumLandings() const { return LandingS.Num(); }
	float LandingPos(int32 L) const { return LandingS[L]; }
	const FConfig& Config() const { return Cfg; }
	/** Roughly when a car will open at a landing for a call going Dir (seconds from now): the number a panel can show. */
	float EstimateArrival(int32 Landing, int32 Dir) const;
	/** The seconds a ride between two landings takes, with the car standing there and ready: the doors, the move, the doors. */
	float RideSeconds(int32 From, int32 To) const;

	TArray<FAstraLiftEvent>& Events() { return Out; }

	/** The hooks' answers are the owner's: it may swap them (the bench's riders). */
	FHooks& Hooks() { return H; }

private:
	TArray<float> LandingS;
	FConfig Cfg;
	FHooks H;

	EState Mode = EState::Idle;
	float Pos = 0.f, Vel = 0.f, Door = 0.f;
	int32 At = INDEX_NONE;
	int32 Head = 0;
	// the leg
	int32 LegFrom = INDEX_NONE, LegTo = INDEX_NONE;
	float LegS0 = 0.f, LegT = 0.f;
	int32 LegDir = 0;
	FAstraLiftProfile Leg;
	float Timer = 0.f;                 // the dwell (Open), the wait for a deck (Hold)
	// the calls
	TArray<bool> CarCalls;
	TArray<bool> HallUp, HallDown, HallAny;
	TArray<double> CallAge;            // per landing: how long its oldest call has waited (the tie-break of an idle car)
	TArray<FAstraLiftEvent> Out;

	void Step(float Dt);
	void Decide();
	void StartLeg(int32 Next);
	void BeginServe();
	void Arrive();
	bool RequestAt(int32 L) const;
	/** A call the car takes: one from inside, or from a landing when there is room. */
	bool Takes(int32 L, bool bFull) const;
	bool RequestAheadOf(float FromS, int32 Dir, bool bFull) const;
	bool Eligible(int32 L, int32 Dir, bool bFull) const;
	int32 NextStop(float FromS, int32 Dir, bool bFull) const;
	bool FullNow() const { return H.Full && H.Full(); }
	/** The calls of the landing the car has opened at, answered: all the ones for the way it goes (the others too when it turns here). */
	void ClearServed(int32 L, bool bFull);
	void Emit(FAstraLiftEvent::EType T, int32 Landing = INDEX_NONE, int32 Other = 0) { Out.Add({T, Landing, Other}); }
	bool Busy(int32 L) const { return H.DoorwayBusy && H.DoorwayBusy(L); }
	bool Ready(int32 L) const { return !H.DeckReady || H.DeckReady(L); }
};
