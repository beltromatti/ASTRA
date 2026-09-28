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
	/** The walker the Captain was before boarding (restored when the flight ends). */
	APawn* GetWalker() const { return Walker.Get(); }

private:
	UPROPERTY(VisibleAnywhere) TObjectPtr<USceneComponent> Root;
	UPROPERTY(VisibleAnywhere) TObjectPtr<UStaticMeshComponent> Cockpit;
	UPROPERTY(VisibleAnywhere) TObjectPtr<UCameraComponent> Camera;

	enum class EPhase : uint8 { Catapult, Launching, Flying, Ending };
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
};
