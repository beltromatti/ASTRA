// ASTRA — VITA, the body of someone near the Captain: a pooled crew member (AAstraCrewMember: the same body, uniform, seated and
// lying poses, voice and earshot as the bridge officers, so the minds and the Captain's words treat it as one of them: station id
// "npc<roster number>") that is the person where the life simulation puts them. It walks the plan's route at the person's pace
// (doors open for it), stands at its post, sits at its table, lies in its bunk, and goes back to the pool when the Captain has moved
// away and nobody sees it. The person's progress is the simulation's: the body only carries it (AstraLifeSim.h).

#pragma once

#include "CoreMinimal.h"
#include "AstraCrewMember.h"
#include "AstraLiftRider.h"
#include "AstraLifeBody.generated.h"

class UAnimSequence;
class UAstraLifeSubsystem;
struct FAstraLifePerson;

UCLASS()
class ASTRA_API AAstraLifeBody : public AAstraCrewMember
{
	GENERATED_BODY()

public:
	AAstraLifeBody();

	/** The person this body is (an index into the simulation's people), or INDEX_NONE while it sits in the pool. */
	int32 Person() const { return PersonIdx; }
	bool InUse() const { return PersonIdx != INDEX_NONE; }

	/** Becomes the person: their name, uniform, sex and the pose of where they are (or the walk they are on). */
	void Bind(UAstraLifeSubsystem* InOwner, int32 InPerson);
	/** Back to the pool: hidden, silent, not ticking. */
	void Unbind();

	/** How many times the body has thought since it became this person (the tests). */
	int64 TicksRun() const { return Ticks; }
	/** Out on its feet, walking a route (not in a lift, not at its post): the pose where it must be where its person is. */
	bool IsWalking() const { return Mode == EMode::Walk; }
	/** In a real lift (ASCENSORI): at a landing waiting for the car, walking into it, riding it or walking out. */
	bool IsRiding() const { return Mode == EMode::Lift; }
	const FAstraLiftRider& LiftRider() const { return Rider; }
	/** The tests: is the body what its mode says it is (a mesh and a cycle on its feet; the seated pose's mesh at a table or in a bunk; nothing
	 *  showing in a lift or a tower)? OutWhy says what is wrong. */
	bool LooksRight(FString& OutWhy) const;
	/** A headless world does not tick its actors the way a game does: the tests drive the bodies themselves. */
	void TickForTest(float Dt) { Tick(Dt); }

	/** The assets every body needs (the two mannequins, the cycles, the uniforms), loaded now and given back to be kept: the first body to be
	 *  made would otherwise pay for them in the middle of a frame. */
	static void PreloadAssets(TArray<TObjectPtr<UObject>>& OutKeep);
	/** The sex of the mesh it wears (a body of the same sex as the next person is the cheaper one to give them). */
	bool IsFemaleBody() const { return bFemaleBody; }

	/** Seen by the camera lately (their own mesh or their seated pose). */
	bool SeenRecently(float Within = 0.5f) const;

protected:
	virtual void Tick(float DeltaSeconds) override;

private:
	enum class EMode : uint8 { Off, Walk, Stand, Sit, Lie, Shaft, Lift };

	TWeakObjectPtr<UAstraLifeSubsystem> Owner;
	int32 PersonIdx = INDEX_NONE;
	EMode Mode = EMode::Off;
	bool bJog = false;
	bool bShadows = true;
	float TimeAcc = 0.f;
	float Turn = 0.f;                 // the yaw they face (degrees, the way they look, not the mesh's)
	float FaceBlend = 0.f;            // 0 at their post, 1 turned to the Captain
	float SinceSpoke = 100.f;
	FVector2D Offset = FVector2D::ZeroVector;   // keeping right, stepping round the Captain and each other (cm)
	float BlockedS = 0.f;
	float ShaftT = 0.f;
	int64 Ticks = 0;
	bool bFresh = false;              // just bound: the first tick runs at once, whoever sees it
	FAstraLiftRider Rider;            // the ride on a real lift while the person's route is on one (AstraLiftRider.h); otherwise the abstract ride, hidden
	int32 RideSeg = INDEX_NONE;       // the route segment the last look for a ride was made at, and where it began
	FVector RideA = FVector::ZeroVector;
	bool bRideWalk = false;           // the walk cycle is the one playing (on its feet in the lobby or the doorway), not the idle one

	UPROPERTY() TObjectPtr<UAnimSequence> IdleAnim;
	UPROPERTY() TObjectPtr<UAnimSequence> WalkAnim;
	UPROPERTY() TObjectPtr<UAnimSequence> JogAnim;

	void SetMode(EMode M, const FAstraLifePerson& P);
	void Place(const FVector& At, float FacingYaw);
	float ActorYawFor(float FacingYaw) const;
	void TickWalk(float Dt, const FAstraLifePerson& P);
	void TickStand(float Dt, const FAstraLifePerson& P);
	/** The person's route is on a lift (the plan's, which the lift network knows): this body rides it for real. False when it is not, and the body goes on as before. */
	bool TickLift(float Dt, const FAstraLifePerson& P);
	/** The ride is over (arrived, or let go): the rider is released and the person is at the far end of the segment. */
	void EndLift(const FAstraLifePerson& P, bool bPutThere);
	void Shadows(bool bOn);
};
