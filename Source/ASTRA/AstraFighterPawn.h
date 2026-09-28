// ASTRA — the Captain at the stick of a Falcon (first person). Boarded on the flight deck: the Falcon sits on Alpha's
// catapult; throttle up and the catapult throws it down the port tube and out of the Aquila's bow. From there the battle
// simulation flies it with the pilot's input (the same frame as every ship: the pawn is moved by the battle), until it is
// recovered through the tube again (F near the mouth) or shot down (the Captain ejects and the pod is brought home).

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Pawn.h"
#include "AstraBattleSubsystem.h"
#include "AstraFighterPawn.generated.h"

class UCameraComponent;
class UStaticMeshComponent;
class SAstraFlightHud;
class AAstraHangar;

UCLASS()
class ASTRA_API AAstraFighterPawn : public APawn
{
	GENERATED_BODY()

public:
	AAstraFighterPawn();
	virtual void Tick(float DeltaTime) override;
	virtual void SetupPlayerInputComponent(UInputComponent* PlayerInputComponent) override;
	virtual void EndPlay(const EEndPlayReason::Type Reason) override;

	/** Placed on the catapult of the given hangar (the walker who boarded is kept to come back to). */
	void BeginOnCatapult(AAstraHangar* InHangar, APawn* InWalker);
	/** E on the catapult: the Captain climbs out again (false once launched). */
	bool ClimbOut();
	/** Console (testing): the lever 0..1; the stick (x yaw, y pitch, roll -1..1); guns and missile; recovery. */
	UFUNCTION(Exec) void AstraThrottle(float V) { In.Throttle = FMath::Clamp(V, 0.f, 1.f); }
	UFUNCTION(Exec) void AstraStick(float X, float Y, float R) { Stick = FVector2D(X, Y); TestRoll = R; }
	UFUNCTION(Exec) void AstraGuns(int32 On) { In.bGuns = On != 0; }
	UFUNCTION(Exec) void AstraMissile() { In.bMissile = true; MissilePulse = 0.2f; }
	UFUNCTION(Exec) void AstraLand() { Land(); }
	UFUNCTION(Exec) void AstraDescend() { Descend(); }
	/** Testing: over New Ravenna, point the nose at a spot of the zone (metres; default: 300 m over Port Aurelius Field). */
	UFUNCTION(Exec) void AstraFacePlanet(float X = 1800.f, float Y = -1400.f, float Z = 491.f);
	/** The walker the Captain was before boarding (restored when the flight ends). */
	APawn* GetWalker() const { return Walker.Get(); }
	/** Parked on New Ravenna with the Captain outside: E beside it climbs back in. */
	bool IsParkedPlanetside() const { return Phase == EPhase::Parked; }
	void Reboard(APawn* InWalker);

private:
	UPROPERTY(VisibleAnywhere) TObjectPtr<USceneComponent> Root;
	UPROPERTY(VisibleAnywhere) TObjectPtr<UStaticMeshComponent> Cockpit;
	UPROPERTY(VisibleAnywhere) TObjectPtr<UCameraComponent> Camera;

	// Catapult, Launching, Flying (space, the battle flies it), Ending (recovery / ejection),
	// Entry (through the atmosphere), Atmosphere (flying over New Ravenna), Settling (touching down), Landed,
	// Parked (the Captain outside), Exit (climbing back to orbit)
	enum class EPhase : uint8 { Catapult, Launching, Flying, Ending, Entry, Atmosphere, Settling, Landed, Parked, Exit };
	EPhase Phase = EPhase::Catapult;
	TWeakObjectPtr<AAstraHangar> Hangar;
	TWeakObjectPtr<APawn> Walker;
	float PhaseT = 0.f;
	bool bLandedEnd = false;

	// the pilot's hands
	FAstraPilotInput In;
	FVector2D Stick = FVector2D::ZeroVector;   // the virtual stick the mouse moves (-1..1)
	bool bThrUp = false, bThrDown = false, bRollL = false, bRollR = false;
	bool bLeft = false, bRight = false, bUp = false, bDown = false;
	float LookYaw = 0.f, LookPitch = 0.f;      // free look (Alt held) — the head turns, not the ship
	float TestRoll = 0.f;                      // console roll (testing)
	float LastHS = -1.f;                       // hull + shields last frame (a drop is a hit)
	float HitJolt = 0.f;
	float MissilePulse = 0.f;
	bool bFreeLook = false;

	// the cockpit's sounds: the engines through the airframe, the seeker's tones, the missile warning
	UPROPERTY() TObjectPtr<class UAudioComponent> EngineAudio;
	UPROPERTY() TObjectPtr<class UAudioComponent> LockAudio;
	UPROPERTY() TObjectPtr<class UAudioComponent> WarnAudio;
	float BeepT = 0.f;
	void StartSounds();
	void StopSounds();
	void UpdateSounds(const FAstraPilotStatus& St, float Dt);

	TSharedPtr<SAstraFlightHud> Hud;
	void ShowHud(bool bShow);
	void UpdateHud(const FAstraPilotStatus& St);
	void FinishFlight();

	void MouseX(float V);
	void MouseY(float V);
	void Land();
	// the gamepad
	FVector PadAxes = FVector::ZeroVector;     // roll, pitch, yaw
	FVector2D PadThr = FVector2D::ZeroVector;  // right trigger up, left trigger down
	float PadLiftV = 0.f;
	void PadRoll(float V);
	void PadPitch(float V);
	void PadYaw(float V);
	void PadLift(float V);
	void PadThrottleUp(float V);
	void PadThrottleDown(float V);

	// --- New Ravenna: the Falcon flies itself in the planet's zone (the battle is up in space)
	FVector AirVel = FVector::ZeroVector;      // cm/s, world
	float Plasma = 0.f;                        // the entry's glow (0..1)
	bool bSwitched = false;                    // the zone swap happened during this entry / exit
	FVector SettleFrom = FVector::ZeroVector, SettleTo = FVector::ZeroVector;
	FRotator SettleRot = FRotator::ZeroRotator;
	float GroundAGL = 1e6f;                    // metres above what is under the Falcon
	UPROPERTY() TObjectPtr<class UAudioComponent> PlasmaAudio;
	void Descend();
	bool CanDescend() const;
	void TickAtmosphere(float Dt);
	void TickEntryExit(float Dt, bool bEntry);
	void ClimbOutPlanetside();
	void Crash();
	float TraceAGL(FVector* OutGround = nullptr) const;
	FAstraPilotStatus PlanetStatus() const;
};
