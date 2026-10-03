#include "AstraFpsComponent.h"

#include "ASTRA.h"
#include "ASTRACharacter.h"
#include "ASTRAPlayerController.h"
#include "Animation/AnimSequence.h"
#include "AstraBoardSubsystem.h"
#include "AstraCombatFx.h"
#include "AstraCombatant.h"
#include "AstraFpsHud.h"
#include "AstraShipSubsystem.h"
#include "Camera/CameraComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/PoseableMeshComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/GameViewportClient.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "ReferenceSkeleton.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "InputActionValue.h"
#include "InputKeyEventArgs.h"
#include "HAL/IConsoleManager.h"
#include "Misc/OutputDevice.h"
#include "Kismet/GameplayStatics.h"

DECLARE_CYCLE_STAT(TEXT("Weapons"), STAT_AstraFps, STATGROUP_Astra);

namespace
{
	// the places of the weapon against the camera are the weapon table's (AstraWeapon.cpp: where the rear sight stands, hip, sights, lowered); these nudge them (cm), to tune them
	// in the game: astra.fps.hip_x 3 moves the hip place 3 cm further ahead (the arms are placed again at once)
	float GHipX = 0.f, GHipY = 0.f, GHipZ = 0.f;
	float GAdsX = 0.f, GAdsY = 0.f, GAdsZ = 0.f;
	float GLowX = 0.f, GLowY = 0.f, GLowZ = 0.f;
	int32 GArmsOn = 1;
	FAutoConsoleVariableRef FpsCvHipX(TEXT("astra.fps.hip_x"), GHipX, TEXT("Tuning: cm added to the weapon's hip place, ahead of the camera"));
	FAutoConsoleVariableRef FpsCvHipY(TEXT("astra.fps.hip_y"), GHipY, TEXT("Tuning: cm added to the weapon's hip place, to the right of the camera"));
	FAutoConsoleVariableRef FpsCvHipZ(TEXT("astra.fps.hip_z"), GHipZ, TEXT("Tuning: cm added to the weapon's hip place, above the camera (negative: below)"));
	FAutoConsoleVariableRef FpsCvAdsX(TEXT("astra.fps.ads_x"), GAdsX, TEXT("Tuning: cm added to where the rear sight stands through the sights, ahead of the camera"));
	FAutoConsoleVariableRef FpsCvAdsY(TEXT("astra.fps.ads_y"), GAdsY, TEXT("Tuning: cm added to where the rear sight stands through the sights, to the right"));
	FAutoConsoleVariableRef FpsCvAdsZ(TEXT("astra.fps.ads_z"), GAdsZ, TEXT("Tuning: cm added to where the rear sight stands through the sights, above the axis"));
	FAutoConsoleVariableRef FpsCvLowX(TEXT("astra.fps.low_x"), GLowX, TEXT("Tuning: cm added to the lowered weapon's place (running, putting it away), ahead of the camera"));
	FAutoConsoleVariableRef FpsCvLowY(TEXT("astra.fps.low_y"), GLowY, TEXT("Tuning: cm added to the lowered weapon's place, to the right of the camera"));
	FAutoConsoleVariableRef FpsCvLowZ(TEXT("astra.fps.low_z"), GLowZ, TEXT("Tuning: cm added to the lowered weapon's place, above the camera (negative: below)"));
	FAutoConsoleVariableRef FpsCvArms(TEXT("astra.fps.arms"), GArmsOn, TEXT("1: the mannequin's arms hold the weapon (applies when the weapon is next drawn); 0: the weapon alone (the fallback)"));
	// the shoulders' places are the weapon table's (ShoulderHipR/L: below the picture); these move them (cm; x ahead, y to the right for the right one and to the left for the left, z up)
	float GShoulderX = 0.f, GShoulderY = 0.f, GShoulderZ = 0.f;
	float GFpFov = 0.f;
	FAutoConsoleVariableRef FpsCvShX(TEXT("astra.fps.shoulder_x"), GShoulderX, TEXT("Tuning: cm added to how far ahead of the camera the shoulders stand: they decide how bent the arms are"));
	FAutoConsoleVariableRef FpsCvShY(TEXT("astra.fps.shoulder_y"), GShoulderY, TEXT("Tuning: cm added to how far each shoulder is from the middle (outwards)"));
	FAutoConsoleVariableRef FpsCvShZ(TEXT("astra.fps.shoulder_z"), GShoulderZ, TEXT("Tuning: cm added to the shoulders' height (negative: lower, further below the picture)"));
	FAutoConsoleVariableRef FpsCvFov(TEXT("astra.fps.fp_fov"), GFpFov, TEXT("Tuning: the first-person field of view while a weapon is in his hands (degrees; 0: the weapon table's)"));

	// the arms: the mannequin cut down to the lower half of the upper arm, the forearm and the hand (tools/ue_scripts/make_fp_arms.py)
	const TCHAR* const FpsArmsPath = TEXT("/Game/ASTRA/Weapons/SKM_ASTRA_Arms.SKM_ASTRA_Arms");

	// one number for all the console's nudges: when it changes the arms are placed again
	float FpsNudgeStamp()
	{
		return GHipX + 3.f * GHipY + 7.f * GHipZ + 11.f * GAdsX + 13.f * GAdsY + 17.f * GAdsZ + 19.f * GLowX + 23.f * GLowY + 29.f * GLowZ;
	}

	constexpr float FpsKeysShownS = 24.f;

	UAnimSequence* FpsLoadAnim(const TCHAR* Path)
	{
		return (Path && *Path) ? LoadObject<UAnimSequence>(nullptr, Path) : nullptr;
	}

	FQuat FpsPoseQuat(const FAstraWeaponDef& W)
	{
		// the pose's axes are read to two decimals: made a proper frame (Y forward, Z up, X their cross)
		const FVector Y = W.PoseGripY.GetSafeNormal();
		FVector Z = (W.PoseGripZ - Y * FVector::DotProduct(W.PoseGripZ, Y)).GetSafeNormal();
		const FVector X = FVector::CrossProduct(Y, Z).GetSafeNormal();
		return FMatrix(X, Y, Z, FVector::ZeroVector).ToQuat();
	}
}

UAstraFpsComponent::UAstraFpsComponent()
{
	PrimaryComponentTick.bCanEverTick = true;
	PrimaryComponentTick.TickGroup = TG_PostPhysics;
}

AASTRACharacter* UAstraFpsComponent::Owner() const
{
	return Cast<AASTRACharacter>(GetOwner());
}

UCameraComponent* UAstraFpsComponent::Camera() const
{
	return GetOwner() ? GetOwner()->FindComponentByClass<UCameraComponent>() : nullptr;
}

void UAstraFpsComponent::BeginPlay()
{
	Super::BeginPlay();
}

void UAstraFpsComponent::EndPlay(const EEndPlayReason::Type Reason)
{
	RestoreFov();
	RestoreFpFov();
	RemoveHud();
	Super::EndPlay(Reason);
}

// ================================================================================================================== the kit

void UAstraFpsComponent::SetKit(bool bTake)
{
	if (bTake)
	{
		if (bHasRifle && bHasPistol)
		{
			return;
		}
		GiveWeapon(EAstraWeapon::Pistol, true, false);
		GiveWeapon(EAstraWeapon::Rifle, true, true);              // (the rifle comes up, the sidearm is the one he changes to)
		Last = EAstraWeapon::Pistol;
	}
	else
	{
		GiveWeapon(EAstraWeapon::Rifle, false);
		GiveWeapon(EAstraWeapon::Pistol, false);
	}
}

void UAstraFpsComponent::GiveWeapon(EAstraWeapon W, bool bTake, bool bDraw)
{
	if (W == EAstraWeapon::None)
	{
		return;
	}
	bool& bHas = W == EAstraWeapon::Rifle ? bHasRifle : bHasPistol;
	if (bHas == bTake)
	{
		return;
	}
	bHas = bTake;
	bHasKit = bHasRifle || bHasPistol;
	if (bTake)
	{
		// from a rack or a locker a weapon comes loaded, with all its spare magazines
		const FAstraWeaponDef& D = AstraWeapons::Get(W);
		FAmmo& A = AmmoOf(W);
		A.Mag = D.Mag;
		A.Reserve = D.Mag * D.SpareMags;
		KeysT = FpsKeysShownS;
		KeysShownAt = GetWorld() ? GetWorld()->GetTimeSeconds() : 0.0;
		if (Last == EAstraWeapon::None || !Carries(Last))
		{
			Last = W;
		}
		if (bDraw && (State == EState::Holstered || State == EState::Holstering))
		{
			StartDraw(W);
		}
	}
	else
	{
		// back in its place: it is put away (its rounds stay with it)
		if (Cur == W)
		{
			State = EState::Holstered;
			Cur = EAstraWeapon::None;
			Next = EAstraWeapon::None;
			ShowArms(false);
			Ads = 0.f;
		}
		if (Next == W)
		{
			Next = EAstraWeapon::None;
		}
		if (Last == W)
		{
			Last = Carries(W == EAstraWeapon::Rifle ? EAstraWeapon::Pistol : EAstraWeapon::Rifle) ? (W == EAstraWeapon::Rifle ? EAstraWeapon::Pistol : EAstraWeapon::Rifle) : EAstraWeapon::None;
		}
		bFireHeld = false;
		bAimHeld = false;
	}
}

EAstraWeapon UAstraFpsComponent::DefaultWeapon() const
{
	if (Last != EAstraWeapon::None && Carries(Last))
	{
		return Last;
	}
	return bHasRifle ? EAstraWeapon::Rifle : (bHasPistol ? EAstraWeapon::Pistol : EAstraWeapon::None);
}

FString UAstraFpsComponent::StatusText() const
{
	if (!bHasKit)
	{
		return FString();
	}
	const FAstraWeaponDef& W = AstraWeapons::Get(Cur != EAstraWeapon::None ? Cur : DefaultWeapon());
	const FAmmo& A = AmmoOf(W.Id);
	FString Out = FString::Printf(TEXT("%s %s: %d in the magazine, %d spare%s"), W.Name, W.Role, A.Mag, A.Reserve, IsArmed() ? TEXT(", in his hands") : TEXT(", holstered"));
	if (bHasRifle && bHasPistol)
	{
		const FAstraWeaponDef& O = AstraWeapons::Get(W.Id == EAstraWeapon::Rifle ? EAstraWeapon::Pistol : EAstraWeapon::Rifle);
		Out += FString::Printf(TEXT("; and the %s %s (%d/%d)"), O.Name, O.Role, AmmoOf(O.Id).Mag, AmmoOf(O.Id).Reserve);
	}
	return Out;
}

bool UAstraFpsComponent::Locked() const
{
	const AASTRACharacter* C = Owner();
	if (!C)
	{
		return true;
	}
	const AASTRAPlayerController* PC = Cast<AASTRAPlayerController>(C->GetController());
	if (!PC)
	{
		return true;                                  // not the player's (or not possessed): nothing in the hands
	}
	if (PC->IsSeated() || PC->IsPadUp() || PC->IsMoveInputIgnored())       // (the lift's list on a car's screen holds the walking still: the clicks and the number keys are its own)
	{
		return true;
	}
	if (const UAstraShipSubsystem* Ship = GetWorld() ? GetWorld()->GetSubsystem<UAstraShipSubsystem>() : nullptr)
	{
		if (Ship->GetCaptainFate() != 0)
		{
			return true;                              // down, or dead
		}
	}
	return C->GetCharacterMovement() && C->GetCharacterMovement()->MovementMode == MOVE_None;
}

// ================================================================================================================== the controls

void UAstraFpsComponent::FirePressed()
{
	++FireEvents;
	bFireHeld = true;
	bTriggerLatched = false;
	// with nothing in the hands, the button draws the last weapon
	if (bHasKit && State == EState::Holstered && !Locked())
	{
		StartDraw(DefaultWeapon());
	}
}

void UAstraFpsComponent::FireReleased()
{
	bFireHeld = false;
	bTriggerLatched = false;
}

void UAstraFpsComponent::AimPressed()
{
	++AimEvents;
	bAimHeld = true;
	UE_LOG(LogASTRA, Log, TEXT("[Fps] aim: pressed (%s, %s)"), bHasKit ? (IsArmed() ? TEXT("weapon in hand") : TEXT("weapon holstered")) : TEXT("no kit"), Locked() ? TEXT("locked: seated, in a lift or down") : TEXT("free"));
}

void UAstraFpsComponent::AimReleased()
{
	bAimHeld = false;
	UE_LOG(LogASTRA, Log, TEXT("[Fps] aim: released"));
}

void UAstraFpsComponent::ReloadPressed()
{
	if (State == EState::Ready && !Locked())
	{
		StartReload();
	}
}

void UAstraFpsComponent::SelectWeapon(EAstraWeapon W)
{
	if (!bHasKit || Locked() || W == EAstraWeapon::None)
	{
		return;
	}
	if (!Carries(W))
	{
		Prompt(W == EAstraWeapon::Rifle ? TEXT("NO RIFLE: only the sidearm (the Marine Armory has one)") : TEXT("NO SIDEARM: only the rifle"), 2.2f);
		return;
	}
	if (State == EState::Holstered)
	{
		StartDraw(W);
	}
	else if (W == Cur && (State == EState::Ready || State == EState::Drawing))
	{
		StartHolster(EAstraWeapon::None);               // the same key twice: put it away
	}
	else if (W != Cur)
	{
		if (State == EState::Reloading)
		{
			CancelReload();
		}
		StartHolster(W);
	}
}

void UAstraFpsComponent::CycleWeapon(float Direction)
{
	if (!bHasKit || FMath::IsNearlyZero(Direction) || !(bHasRifle && bHasPistol))
	{
		return;                                       // (one weapon: nothing to change to)
	}
	SelectWeapon(Cur == EAstraWeapon::Rifle ? EAstraWeapon::Pistol : EAstraWeapon::Rifle);
}

void UAstraFpsComponent::QuickSwitch()
{
	if (!bHasKit)
	{
		return;
	}
	if (State == EState::Holstered)
	{
		SelectWeapon(DefaultWeapon());
	}
	else if (bHasRifle && bHasPistol)
	{
		SelectWeapon(Cur == EAstraWeapon::Rifle ? EAstraWeapon::Pistol : EAstraWeapon::Rifle);
	}
}

void UAstraFpsComponent::ToggleHolster()
{
	if (!bHasKit || Locked())
	{
		return;
	}
	if (State == EState::Holstered)
	{
		StartDraw(DefaultWeapon());
	}
	else if (State != EState::Holstering)
	{
		if (State == EState::Reloading)
		{
			CancelReload();
		}
		StartHolster(EAstraWeapon::None);
	}
}

void UAstraFpsComponent::WheelInput(const FInputActionValue& Value)
{
	// a notch of the wheel (a few come at once from a smooth one: the first counts, the others wait out the change)
	const float V = Value.Get<float>();
	if (FMath::Abs(V) > 0.5f && State != EState::Holstering && State != EState::Drawing)
	{
		CycleWeapon(V);
	}
}

float UAstraFpsComponent::MoveMultiplier() const
{
	if (!IsArmed())
	{
		return 1.f;
	}
	const FAstraWeaponDef& W = AstraWeapons::Get(Cur);
	float M = FMath::Lerp(W.MoveMul, W.AdsMoveMul, Ads);
	if (State == EState::Reloading)
	{
		M *= 0.88f;
	}
	return M;
}

float UAstraFpsComponent::LookMultiplier() const
{
	if (Ads <= 0.01f || Cur == EAstraWeapon::None)
	{
		return 1.f;
	}
	const float Zoom = AstraWeapons::Get(Cur).AdsFov / FMath::Max(30.f, BaseFov);
	return FMath::Lerp(1.f, Zoom, Ads);
}

// ================================================================================================================== the states

void UAstraFpsComponent::StartDraw(EAstraWeapon W)
{
	if (W == EAstraWeapon::None)
	{
		return;
	}
	const FAstraWeaponDef& D = AstraWeapons::Get(W);
	Cur = W;
	State = EState::Drawing;
	StateT = 0.f;
	StateLen = D.DrawS;
	bAutoReloadPending = false;
	Bloom = 0.f;
	DressArms(W);
	PlayArms(AnimEquip, false, AnimEquip && D.DrawS > 0.f ? D.EquipAnimS / D.DrawS : 1.f);
	Sound(D.DrawSound, 0.8f);
	// the card of keys comes up for a moment when he draws, unless it was up not long ago
	const double Now = GetWorld() ? GetWorld()->GetTimeSeconds() : 0.0;
	if (KeysT <= 0.f && KeysAlpha <= 0.f && Now - KeysShownAt > 90.0)
	{
		KeysT = 6.f;
		KeysShownAt = Now;
	}
}

void UAstraFpsComponent::StartHolster(EAstraWeapon Then)
{
	if (Cur == EAstraWeapon::None)
	{
		State = EState::Holstered;
		return;
	}
	const FAstraWeaponDef& D = AstraWeapons::Get(Cur);
	State = EState::Holstering;
	StateT = 0.f;
	StateLen = D.HolsterS;
	Next = Then;
	bFireHeld = false;
}

void UAstraFpsComponent::StartReload()
{
	if (Cur == EAstraWeapon::None)
	{
		return;
	}
	const FAstraWeaponDef& D = AstraWeapons::Get(Cur);
	FAmmo& A = AmmoOf(Cur);
	if (A.Mag >= D.Mag)
	{
		return;                                       // full
	}
	if (A.Reserve <= 0)
	{
		Prompt(TEXT("NO SPARE MAGAZINES"), 1.6f);
		return;
	}
	State = EState::Reloading;
	StateT = 0.f;
	StateLen = A.Mag > 0 ? D.ReloadS : D.ReloadEmptyS;
	bAutoReloadPending = false;
	PlayArms(AnimReload, false, AnimReload && StateLen > 0.f ? D.ReloadAnimS / StateLen : 1.f);
	Sound(D.ReloadSound, 0.85f);
}

void UAstraFpsComponent::CancelReload()
{
	if (State == EState::Reloading)
	{
		State = EState::Ready;
		StateT = 0.f;
		PlayArms(AnimIdle, true);
	}
}

void UAstraFpsComponent::TickState(float Dt)
{
	StateT += Dt;
	switch (State)
	{
	case EState::Drawing:
		if (StateT >= StateLen)
		{
			State = EState::Ready;
			StateT = 0.f;
			PlayArms(AnimIdle, true);
		}
		break;
	case EState::Holstering:
		if (StateT >= StateLen)
		{
			Last = Cur;
			if (Next != EAstraWeapon::None)
			{
				const EAstraWeapon N = Next;
				Next = EAstraWeapon::None;
				StartDraw(N);
			}
			else
			{
				State = EState::Holstered;
				Cur = EAstraWeapon::None;
				ShowArms(false);
				Ads = 0.f;
				RestoreFov();
			}
		}
		break;
	case EState::Reloading:
		if (StateT >= StateLen)
		{
			const FAstraWeaponDef& D = AstraWeapons::Get(Cur);
			FAmmo& A = AmmoOf(Cur);
			const int32 Take = FMath::Min(D.Mag - A.Mag, A.Reserve);
			A.Mag += Take;
			A.Reserve -= Take;
			State = EState::Ready;
			StateT = 0.f;
			PlayArms(AnimIdle, true);
		}
		break;
	default:
		break;
	}
}

// ================================================================================================================== the rounds

float UAstraFpsComponent::SpreadDeg(const FAstraWeaponDef& W) const
{
	float S = FMath::Lerp(W.HipSpreadDeg, W.AdsSpreadDeg, Ads);
	const AASTRACharacter* C = Owner();
	if (C)
	{
		const EAstraPosture P = C->GetPosture();
		S *= P == EAstraPosture::Prone ? 0.55f : (P == EAstraPosture::Crouched ? 0.78f : 1.f);
		const float Speed = (float)C->GetVelocity().Size2D();
		S *= 1.f + FMath::Clamp(Speed / 380.f, 0.f, 1.6f) * FMath::Lerp(0.95f, 0.5f, Ads);
		if (C->GetCharacterMovement() && C->GetCharacterMovement()->IsFalling())
		{
			S *= 2.4f;
		}
	}
	return S + Bloom;
}

FVector UAstraFpsComponent::MuzzleGuess(const FVector& Eye, const FRotator& View) const
{
	// where the weapon's muzzle is seen from the Captain's eye: a little ahead, to the right and low from the hip, nearly on the axis through the sights
	const FVector Fwd = View.Vector(), Right = FRotationMatrix(View).GetScaledAxis(EAxis::Y), Up = FRotationMatrix(View).GetScaledAxis(EAxis::Z);
	const float Hip = 1.f - Ads;
	return Eye + Fwd * 62.f + Right * (13.f * Hip) + Up * (-12.f * Hip - 4.f * Ads);
}

void UAstraFpsComponent::Sound(const TCHAR* Path, float Volume, float Pitch)
{
	if (UAstraCombatFx* Fx = GetWorld() ? GetWorld()->GetSubsystem<UAstraCombatFx>() : nullptr)
	{
		if (const UCameraComponent* Cam = Camera())
		{
			Fx->PlaySoundAt(Path, Cam->GetComponentLocation() + Cam->GetForwardVector() * 30.f, Volume, Pitch);
		}
	}
}

bool UAstraFpsComponent::TryFire()
{
	const FAstraWeaponDef& W = AstraWeapons::Get(Cur);
	FAmmo& A = AmmoOf(Cur);
	const double Now = GetWorld()->GetTimeSeconds();
	if (Now < NextShotAt)
	{
		return false;
	}
	if (A.Mag <= 0)
	{
		// the click of an empty weapon (once a press), and it is reloaded for him when the button is let go of
		if (DryT <= 0.f)
		{
			DryT = 0.35f;
			Sound(W.DrySound, 0.7f);
			PlayArms(AnimDry, false, 1.4f);
			if (A.Reserve > 0)
			{
				bAutoReloadPending = true;
			}
			else
			{
				Prompt(TEXT("OUT OF AMMUNITION"), 1.6f);
			}
		}
		NextShotAt = Now + 0.25;
		return false;
	}
	--A.Mag;
	NextShotAt = Now + W.RoundIntervalS();
	FireRound(W);
	return true;
}

void UAstraFpsComponent::FireRound(const FAstraWeaponDef& W)
{
	UWorld* World = GetWorld();
	AASTRACharacter* C = Owner();
	const UCameraComponent* Cam = Camera();
	AController* PC = C ? C->GetController() : nullptr;
	if (!World || !C || !Cam || !PC)
	{
		return;
	}
	++NumShots;
	const FVector Eye = Cam->GetComponentLocation();
	const FRotator View = PC->GetControlRotation();
	const float Spread = SpreadDeg(W);
	const FVector Dir = FMath::VRandCone(View.Vector(), FMath::DegreesToRadians(Spread));
	const FVector End = Eye + Dir * 30000.f;
	FHitResult Hit;
	FCollisionQueryParams Q(SCENE_QUERY_STAT(AstraPlayerShot), true, C);
	const bool bHit = World->LineTraceSingleByChannel(Hit, Eye, End, ECC_Visibility, Q);
	const FVector Impact = bHit ? Hit.ImpactPoint : End;
	UAstraCombatFx* Fx = World->GetSubsystem<UAstraCombatFx>();
	UAstraBoardSubsystem* Board = World->GetSubsystem<UAstraBoardSubsystem>();
	const FVector Muzzle = MuzzleGuess(Eye, View);
	bool bCounted = false;
	if (bHit)
	{
		if (AAstraCombatant* Who = Cast<AAstraCombatant>(Hit.GetActor()))
		{
			AAstraCombatant::EZone Zone = AAstraCombatant::EZone::Body;
			if (Cast<USkeletalMeshComponent>(Hit.GetComponent()))
			{
				Zone = AAstraCombatant::ZoneOfBone(Hit.BoneName);
			}
			else
			{
				const float H = (float)(Impact.Z - Who->GetActorLocation().Z);
				Zone = H > 148.f ? AAstraCombatant::EZone::Head : (H < 70.f ? AAstraCombatant::EZone::Limb : AAstraCombatant::EZone::Body);
			}
			const bool bHead = Zone == AAstraCombatant::EZone::Head;
			const float Dmg = W.DamageAt((float)FVector::Dist(Eye, Impact)) * (bHead ? W.HeadMul : (Zone == AAstraCombatant::EZone::Limb ? W.LimbMul : 1.f));
			bCounted = Board && Board->PlayerHit(Who, Dmg, bHead, Eye);
			if (bCounted)
			{
				++NumHits;
				HitMark = 1.f;
				bHitWasHead = bHead;
			}
			else if (Fx)
			{
				Fx->Impact(Impact, -Dir, UAstraCombatFx::ESurface::Flesh);
			}
		}
		else if (Fx)
		{
			Fx->Impact(Impact, Hit.ImpactNormal, UAstraCombatFx::ESurface::Metal);
			if (UPrimitiveComponent* P = Hit.GetComponent(); P && P->IsSimulatingPhysics())
			{
				P->AddImpulseAtLocation(Dir * 18000.f, Impact);
			}
		}
	}
	if (Fx)
	{
		Fx->Tracer(Muzzle, Impact, FLinearColor(1.f, 0.9f, 0.55f), 90000.f, 240.f, 0.55f);
		Fx->MuzzleFlash(Muzzle, Dir, Ads > 0.5f ? 0.35f : 0.6f);
	}
	Sound(W.ShotSound, 1.f, FMath::FRandRange(0.97f, 1.04f));
	if (Board)
	{
		Board->NoteCaptainShot();
	}
	Recoil(W);
	Bloom = FMath::Min(W.BloomMaxDeg, Bloom + W.BloomPerShotDeg);
	SinceShot = 0.f;
}

void UAstraFpsComponent::Recoil(const FAstraWeaponDef& W)
{
	AController* PC = Owner() ? Owner()->GetController() : nullptr;
	if (PC)
	{
		const float Climb = W.KickPitchDeg * FMath::FRandRange(0.8f, 1.2f) * FMath::Lerp(1.f, 0.7f, Ads);
		FRotator R = PC->GetControlRotation();
		R.Pitch = FMath::ClampAngle(R.Pitch + Climb, -85.f, 85.f);
		R.Yaw += FMath::FRandRange(-W.KickYawDeg, W.KickYawDeg);
		PC->SetControlRotation(R);
		RecoilPitch += Climb;
	}
	// the weapon kicks on his shoulder: back, up, and the muzzle climbs (a spring that settles)
	const float S = Ads > 0.5f ? 0.55f : 1.f;
	KickVel += FVector(-75.f * S, FMath::FRandRange(-8.f, 8.f) * S, 22.f * S) * (W.Id == EAstraWeapon::Pistol ? 1.4f : 1.f);
	KickPitchVel += (W.Id == EAstraWeapon::Pistol ? 64.f : 42.f) * S;
}

void UAstraFpsComponent::TickRecoil(float Dt)
{
	SinceShot += Dt;
	const FAstraWeaponDef& W = AstraWeapons::Get(Cur != EAstraWeapon::None ? Cur : EAstraWeapon::Rifle);
	if (SinceShot > 0.09f)
	{
		Bloom = FMath::Max(0.f, Bloom - W.BloomRecoverDegS * Dt);
		// the sights come back down a part of the way they climbed
		AController* PC = Owner() ? Owner()->GetController() : nullptr;
		if (PC && RecoilPitch > 0.02f)
		{
			const float Take = FMath::Min(RecoilPitch, RecoilPitch * Dt * 3.5f + 0.4f * Dt);
			FRotator R = PC->GetControlRotation();
			R.Pitch = FMath::ClampAngle(R.Pitch - Take * 0.6f, -85.f, 85.f);
			PC->SetControlRotation(R);
			RecoilPitch -= Take;
		}
	}
	// the weapon's spring
	const float K = 430.f, Cd = 27.f;
	KickVel += (-KickPos * K - KickVel * Cd) * Dt;
	KickPos += KickVel * Dt;
	KickPitchVel += (-KickPitch * K - KickPitchVel * Cd) * Dt;
	KickPitch += KickPitchVel * Dt;
	DryT = FMath::Max(0.f, DryT - Dt);
}

void UAstraFpsComponent::OnHurt(const FVector& From, float Amount)
{
	HurtAlpha = FMath::Min(1.f, HurtAlpha + 0.28f + Amount / 70.f);
	const UCameraComponent* Cam = Camera();
	AController* PC = Owner() ? Owner()->GetController() : nullptr;
	if (Cam)
	{
		const FVector To = From - Cam->GetComponentLocation();
		const float Rel = FMath::UnwindDegrees(FMath::RadiansToDegrees(FMath::Atan2(To.Y, To.X)) - Cam->GetComponentRotation().Yaw);
		FArc* Near = Arcs.FindByPredicate([Rel](const FArc& A) { return FMath::Abs(FMath::UnwindDegrees(A.Yaw - Rel)) < 22.f; });
		if (Near)
		{
			Near->Alpha = 1.f;
			Near->Yaw = Rel;
		}
		else
		{
			FArc A;
			A.Yaw = Rel;
			A.Alpha = 1.f;
			Arcs.Add(A);
		}
	}
	// the blow turns him a little
	if (PC)
	{
		FRotator R = PC->GetControlRotation();
		R.Pitch = FMath::ClampAngle(R.Pitch + FMath::FRandRange(0.4f, 1.4f), -85.f, 85.f);
		R.Yaw += FMath::FRandRange(-1.6f, 1.6f);
		PC->SetControlRotation(R);
	}
	KickVel += FVector(-30.f, FMath::FRandRange(-30.f, 30.f), -20.f);
	KickPitchVel += 30.f;
}

void UAstraFpsComponent::Prompt(const FString& Text, float Seconds)
{
	PromptText = Text;
	PromptT = Seconds;
}

// ================================================================================================================== the arms

void UAstraFpsComponent::EnsureArms()
{
	if (Gun)
	{
		return;
	}
	AASTRACharacter* C = Owner();
	UCameraComponent* Cam = Camera();
	if (!C || !Cam)
	{
		return;
	}
	const auto Common = [this](UPrimitiveComponent* P)
	{
		P->SetOnlyOwnerSee(true);
		P->SetCastShadow(false);
		P->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		P->SetGenerateOverlapEvents(false);
		P->FirstPersonPrimitiveType = EFirstPersonPrimitiveType::FirstPerson;
		P->SetCanEverAffectNavigation(false);
	};
	// the arms: the mannequin cut down to its arms (the weapon code places them against the camera, where the head and the chest of a whole body would fill the view); when that
	// asset is not there, the mesh of the character's own first-person arms with the head and neck taken off
	USkeletalMesh* Mesh = LoadObject<USkeletalMesh>(nullptr, FpsArmsPath);
	bArmsOnly = Mesh != nullptr;
	if (!Mesh)
	{
		Mesh = C->GetFirstPersonMesh() ? C->GetFirstPersonMesh()->GetSkeletalMeshAsset() : nullptr;
	}
	if (!Mesh)
	{
		Mesh = LoadObject<USkeletalMesh>(nullptr, TEXT("/Game/Characters/Mannequins/Meshes/SKM_Manny_Simple.SKM_Manny_Simple"));
	}
	if (Mesh && GArmsOn)
	{
		// the animation plays on a mesh nobody sees (the weapon rides its right-hand socket); the arms that are seen are a poseable copy of it, solved to the weapon every frame
		Arms = NewObject<USkeletalMeshComponent>(C, TEXT("WeaponArms"));
		Arms->SetupAttachment(Cam);
		Arms->SetSkeletalMeshAsset(Mesh);
		Arms->SetAnimationMode(EAnimationMode::AnimationSingleNode);
		Arms->VisibilityBasedAnimTickOption = EVisibilityBasedAnimTickOption::AlwaysTickPoseAndRefreshBones;
		Arms->bEnableUpdateRateOptimizations = false;
		Arms->SetReceivesDecals(false);
		Arms->SetBoundsScale(4.f);
		Common(Arms);
		Arms->RegisterComponent();
		Arms->SetVisibility(false);
		Pose = NewObject<UPoseableMeshComponent>(C, TEXT("WeaponArmsPose"));
		Pose->SetupAttachment(Cam);
		Pose->SetSkinnedAssetAndUpdate(Mesh);
		Pose->SetReceivesDecals(false);
		Pose->SetBoundsScale(4.f);                    // the pose stands far from where the mesh does (the weapon code moves it): never culled
		Common(Pose);
		if (C->GetFirstPersonMesh())
		{
			// the mesh's own materials follow the character's arms (its colourway)
			for (int32 i = 0; i < C->GetFirstPersonMesh()->GetNumMaterials() && i < Pose->GetNumMaterials(); ++i)
			{
				Pose->SetMaterial(i, C->GetFirstPersonMesh()->GetMaterial(i));
			}
		}
		Pose->RegisterComponent();
		if (!bArmsOnly)
		{
			Pose->HideBoneByName(TEXT("neck_01"), EPhysBodyOp::PBO_None);     // (the head would sit at the camera)
		}
		Pose->SetVisibility(false);
		AstraArms::FindBones(Mesh->GetRefSkeleton(), ArmBones);
		AddTickPrerequisiteComponent(Arms);           // the pose is read after the animation has made it
	}
	Gun = NewObject<UStaticMeshComponent>(C, TEXT("WeaponGun"));
	Mag = NewObject<UStaticMeshComponent>(C, TEXT("WeaponMag"));
	for (UStaticMeshComponent* G : {Gun.Get(), Mag.Get()})
	{
		G->SetupAttachment(Cam);
		Common(G);
		G->RegisterComponent();
		G->SetVisibility(false);
	}
}

void UAstraFpsComponent::ShowArms(bool bOn)
{
	if (bShown == bOn && Gun)
	{
		return;
	}
	bShown = bOn;
	if (!bOn)
	{
		RestoreFpFov();
	}
	EnsureArms();
	AASTRACharacter* C = Owner();
	if (Pose)
	{
		Pose->SetVisibility(bOn);
	}
	if (Gun)
	{
		Gun->SetVisibility(bOn);
	}
	if (Mag)
	{
		Mag->SetVisibility(bOn && Mag->GetStaticMesh() != nullptr);
	}
	// the character's own arms (empty hands) rest while the weapon is out
	if (C && C->GetFirstPersonMesh())
	{
		C->GetFirstPersonMesh()->SetVisibility(!(bOn && Pose));
	}
}

void UAstraFpsComponent::DressArms(EAstraWeapon W)
{
	EnsureArms();
	if (!Gun)
	{
		return;
	}
	const FAstraWeaponDef& D = AstraWeapons::Get(W);
	if (ArmsFor != W)
	{
		ArmsFor = W;
		UStaticMesh* GM = LoadObject<UStaticMesh>(nullptr, D.MeshPath);
		if (!GM)
		{
			// the model is not imported yet: a bar the size of the weapon
			GM = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cube.Cube"));
			Gun->SetRelativeScale3D(FVector(0.07f, 0.6f, 0.17f) * (W == EAstraWeapon::Pistol ? 0.3f : 1.f));
		}
		else
		{
			Gun->SetRelativeScale3D(FVector::OneVector);
		}
		Gun->SetStaticMesh(GM);
		UStaticMesh* MM = (D.MagPath && *D.MagPath) ? LoadObject<UStaticMesh>(nullptr, D.MagPath) : nullptr;
		Mag->SetStaticMesh(MM);
		AnimIdle = FpsLoadAnim(D.AnimIdle);
		AnimEquip = FpsLoadAnim(D.AnimEquip);
		AnimReload = FpsLoadAnim(D.AnimReload);
		AnimDry = FpsLoadAnim(D.AnimDry);
		// the arms' and the weapon's attachment: the gun in the hand's socket, the magazine on the gun (same origin)
		if (Arms && Arms->DoesSocketExist(TEXT("HandGrip_R")))
		{
			Gun->AttachToComponent(Arms, FAttachmentTransformRules::SnapToTargetNotIncludingScale, FName(TEXT("HandGrip_R")));
		}
		else
		{
			Gun->AttachToComponent(Camera(), FAttachmentTransformRules::KeepRelativeTransform);
		}
		Mag->AttachToComponent(Gun, FAttachmentTransformRules::SnapToTargetNotIncludingScale);
		Calibrate(D);
	}
	ShowArms(true);
}

void UAstraFpsComponent::Calibrate(const FAstraWeaponDef& W)
{
	// Where the arms (or the weapon alone) stand against the camera so that the weapon's rear sight is at a chosen place and the weapon is turned as chosen. The ready pose's
	// right-hand socket is known (the probe's numbers in the weapon table): the weapon's own frame (barrel +Y, top +Z, its left +X) in the arms' mesh space is that socket; the
	// camera's frame is x ahead, y right, z up, so a vector at (barrel, -left, top) of the weapon is at (x, y, z) of the camera. The places are the weapon table's (hip, sights,
	// lowered), moved by what the console has added to them.
	FVector SocketLoc = FVector::ZeroVector;
	FQuat SocketQ = FQuat::Identity;
	if (Arms)
	{
		SocketLoc = W.PoseGripLoc;
		SocketQ = FpsPoseQuat(W);
	}
	FVector LocHip, LocAds, LocLow;
	FQuat RotHip, RotAds, RotLow;
	AstraArms::PlaceWeapon(SocketLoc, SocketQ, W.Sight, W.HipPlace + FVector(GHipX, GHipY, GHipZ), W.HipTurn, LocHip, RotHip, SightInMesh);
	AstraArms::PlaceWeapon(SocketLoc, SocketQ, W.Sight, W.AdsPlace + FVector(GAdsX, GAdsY, GAdsZ), FRotator::ZeroRotator, LocAds, RotAds, SightInMesh);
	AstraArms::PlaceWeapon(SocketLoc, SocketQ, W.Sight, W.LowPlace + FVector(GLowX, GLowY, GLowZ), W.LowTurn, LocLow, RotLow, SightInMesh);
	HipLoc = LocHip;
	HipRot = RotHip;
	AdsLoc = LocAds;
	AdsRot = RotAds;
	LowLoc = LocLow;
	LowRot = RotLow;
	TuneStamp = FpsNudgeStamp();
	bCalibrated = true;
	UE_LOG(LogASTRA, Log, TEXT("[Fps] %s: the arms' place at the hip %s, through the sights %s, lowered %s (%s)"), W.Name, *HipLoc.ToString(), *AdsLoc.ToString(), *LowLoc.ToString(),
		Arms ? (bArmsOnly ? TEXT("on the arms-only mesh") : TEXT("on the whole mannequin, head off")) : TEXT("the weapon alone"));
}

void UAstraFpsComponent::ApplyNudges()
{
	// the console's nudges of the places (astra.fps.hip_x ...) take effect at once
	if (bCalibrated && Cur != EAstraWeapon::None && !FMath::IsNearlyEqual(FpsNudgeStamp(), TuneStamp, 1e-4f))
	{
		Calibrate(AstraWeapons::Get(Cur));
	}
}

void UAstraFpsComponent::PlayArms(UAnimSequence* A, bool bLoop, float Rate)
{
	if (Arms && A)
	{
		Arms->PlayAnimation(A, bLoop);
		// the ready pose is held at its first frame: the sights stay where the weapon table puts them (the loop's breathing moved them by up to a centimetre and a half); the weapon's
		// own life is the bob, the sway and the kick
		Arms->SetPlayRate(A == AnimIdle ? 0.f : FMath::Clamp(Rate, 0.2f, 4.f));
	}
}

void UAstraFpsComponent::TickArms(float Dt)
{
	if (!bShown || !Gun || !bCalibrated || Cur == EAstraWeapon::None)
	{
		return;
	}
	ApplyNudges();
	const FAstraWeaponDef& W = AstraWeapons::Get(Cur);
	AASTRACharacter* C = Owner();
	const float Speed = C ? (float)C->GetVelocity().Size2D() : 0.f;
	const bool bGround = C && C->GetCharacterMovement() && C->GetCharacterMovement()->IsMovingOnGround();
	// the aim: through the sights when the button is held and nothing prevents it; the sights are for standing, crouching and lying, not for running
	const bool bCanAim = bAimHeld && (State == EState::Ready || State == EState::Drawing) && !bSprint;
	Ads = FMath::FInterpConstantTo(Ads, bCanAim ? 1.f : 0.f, Dt, 1.f / FMath::Max(0.05f, W.AdsTimeS));
	const float LowTarget = State == EState::Holstering ? 1.f : (bSprint && State != EState::Reloading ? 1.f : 0.f);
	SprintAlpha = FMath::FInterpTo(SprintAlpha, LowTarget, Dt, State == EState::Holstering ? 14.f : 9.f);
	// the pose: hip and sights, and lowered
	const float A = FMath::InterpEaseInOut(0.f, 1.f, Ads, 2.f);
	FQuat Q = FQuat::Slerp(HipRot, AdsRot, A);
	FVector L = FMath::Lerp(HipLoc, AdsLoc, A);
	if (SprintAlpha > 0.001f)
	{
		Q = FQuat::Slerp(Q, LowRot, SprintAlpha);
		L = FMath::Lerp(L, LowLoc, SprintAlpha);
	}
	// walking bobs the weapon, a turn drags it, a shot kicks it
	const float Amp = FMath::Clamp(Speed / 380.f, 0.f, 1.5f) * (bGround ? 1.f : 0.f) * FMath::Lerp(1.f, 0.12f, Ads);
	BobT += Dt * (5.5f + Speed / 70.f);
	FVector Bob(0.f, FMath::Sin(BobT) * 0.5f * Amp, -FMath::Abs(FMath::Cos(BobT)) * 0.75f * Amp);
	AController* PC = C ? C->GetController() : nullptr;
	if (PC && Dt > 0.f)
	{
		const FRotator Now = PC->GetControlRotation();
		const FVector2D Rate(FMath::UnwindDegrees(Now.Yaw - LastControl.Yaw) / Dt, FMath::UnwindDegrees(Now.Pitch - LastControl.Pitch) / Dt);
		LastControl = Now;
		LookRate = FMath::Vector2DInterpTo(LookRate, Rate, Dt, 14.f);
	}
	const float SwayK = FMath::Lerp(0.045f, 0.012f, Ads);
	const FVector2D SwayWant(FMath::Clamp(-LookRate.X * SwayK, -3.f, 3.f), FMath::Clamp(-LookRate.Y * SwayK, -2.2f, 2.2f));
	Sway = FMath::Vector2DInterpTo(Sway, SwayWant, Dt, 11.f);
	const FVector Off = Bob + FVector(0.f, Sway.X, Sway.Y) + KickPos;
	const FQuat Kick = FQuat(FRotator(KickPitch, 0.f, 0.f));
	const FQuat QF = Kick * Q;
	const FVector LF = L + Off - (QF.RotateVector(SightInMesh) - Q.RotateVector(SightInMesh));      // the kick turns the weapon about its sight
	USceneComponent* Root = Arms ? static_cast<USceneComponent*>(Arms) : static_cast<USceneComponent*>(Gun);
	Root->SetRelativeLocationAndRotation(LF, QF);
	MeshQ = QF;
	MeshLoc = LF;
	if (Pose)
	{
		Pose->SetRelativeLocationAndRotation(LF, QF);
		SolveArms(W, Dt);
	}
	TickFpFov(Dt);
	// the magazine rides the weapon (a hand's reload takes it away; the animation shows the hand, the magazine drops and returns with it)
	if (Mag && Mag->GetStaticMesh())
	{
		float Drop = 0.f;
		if (State == EState::Reloading && StateLen > 0.f)
		{
			const float T = StateT / StateLen;
			Drop = T < 0.18f ? FMath::InterpEaseOut(0.f, 1.f, T / 0.18f, 2.f) : (T < 0.5f ? 1.f : (T < 0.68f ? 1.f - FMath::InterpEaseIn(0.f, 1.f, (T - 0.5f) / 0.18f, 2.f) : 0.f));
		}
		Mag->SetRelativeLocation(FVector(0.f, 0.f, -Drop * 26.f));
		Mag->SetVisibility(bShown && Drop < 0.97f);
	}
	// the field of view narrows through the sights
	if (UCameraComponent* Cam = Camera())
	{
		if (Ads > 0.001f)
		{
			if (!bFovTaken)
			{
				BaseFov = Cam->FieldOfView;
				bFovTaken = true;
			}
			Cam->SetFieldOfView(FMath::Lerp(BaseFov, W.AdsFov, A));
		}
		else
		{
			RestoreFov();
		}
	}
}

void UAstraFpsComponent::RestoreFov()
{
	if (bFovTaken)
	{
		if (UCameraComponent* Cam = Camera())
		{
			Cam->SetFieldOfView(BaseFov);
		}
		bFovTaken = false;
	}
}

void UAstraFpsComponent::SolveArms(const FAstraWeaponDef& W, float Dt)
{
	if (!Pose || !Arms || !ArmBones.IsValid() || !Arms->GetSkeletalMeshAsset())
	{
		return;
	}
	const FReferenceSkeleton& Ref = Arms->GetSkeletalMeshAsset()->GetRefSkeleton();
	const TArray<FTransform>& Local = Arms->GetBoneSpaceTransforms();
	if (Local.Num() != Ref.GetNum() || Pose->GetNumComponentSpaceTransforms() != Ref.GetNum())
	{
		return;
	}
	// the animation's pose, copied; the arms are solved over it
	Pose->CopyPoseFromSkeletalComponent(Arms);
	TArray<FTransform> CS;
	AstraArms::ComponentSpace(Ref, Local, CS);
	// the left hand: the animation's left grip socket goes to the weapon's own, as far as it is on the weapon (not while the animation changes the magazine or draws it)
	const bool bOnWeapon = State == EState::Ready || State == EState::Holstering;
	LeftIk = FMath::FInterpConstantTo(LeftIk, bOnWeapon ? 1.f : 0.f, Dt, 4.f);
	FVector LeftDelta = FVector::ZeroVector;
	if (LeftIk > 0.001f && Arms->DoesSocketExist(TEXT("HandGrip_R")) && Arms->DoesSocketExist(TEXT("HandGrip_L")))
	{
		const FTransform SockR = Arms->GetSocketTransform(TEXT("HandGrip_R"), RTS_Component);      // the weapon's frame: the gun's origin is on it
		const FTransform SockL = Arms->GetSocketTransform(TEXT("HandGrip_L"), RTS_Component);
		LeftDelta = (SockR.TransformPosition(W.GripLHand) - SockL.GetLocation()) * LeftIk;
	}
	// the shoulders: where the table puts them at the hip (and carried low) and through the sights, and between them as the weapon comes up (the same ease as its place)
	const float AdsEase = FMath::InterpEaseInOut(0.f, 1.f, Ads, 2.f);
	AstraArms::FSetup Setup;
	Setup.Shoulder[AstraArms::Left] = FMath::Lerp(W.ShoulderHipL, W.ShoulderAdsL, (double)AdsEase) + FVector(GShoulderX, -GShoulderY, GShoulderZ);
	Setup.Shoulder[AstraArms::Right] = FMath::Lerp(W.ShoulderHipR, W.ShoulderAdsR, (double)AdsEase) + FVector(GShoulderX, GShoulderY, GShoulderZ);
	Setup.LeftHandDelta = LeftDelta;
	FTransform Solved[6];
	AstraArms::SolveBoth(ArmBones, CS, MeshQ, MeshLoc, Setup, Solved);
	for (int32 Side = 0; Side < 2; ++Side)
	{
		Pose->SetBoneTransformByName(Ref.GetBoneName(ArmBones.Upper[Side]), Solved[Side * 3 + 0], EBoneSpaces::ComponentSpace);
		Pose->SetBoneTransformByName(Ref.GetBoneName(ArmBones.Lower[Side]), Solved[Side * 3 + 1], EBoneSpaces::ComponentSpace);
		Pose->SetBoneTransformByName(Ref.GetBoneName(ArmBones.Hand[Side]), Solved[Side * 3 + 2], EBoneSpaces::ComponentSpace);
	}
	Pose->RefreshBoneTransforms(nullptr);
}

void UAstraFpsComponent::TickFpFov(float Dt)
{
	// with a weapon in his hands the arms and the weapon are drawn with a wider first-person field than the empty hands': the weapon is held far enough for the arms that hold it to show
	UCameraComponent* Cam = Camera();
	if (!Cam)
	{
		return;
	}
	const FAstraWeaponDef& W = AstraWeapons::Get(Cur);
	const float Want = GFpFov > 1.f ? GFpFov : W.FpFov;
	if (!bFpFovTaken)
	{
		BaseFpFov = Cam->FirstPersonFieldOfView;
		bFpFovTaken = true;
	}
	Cam->FirstPersonFieldOfView = FMath::FInterpTo(Cam->FirstPersonFieldOfView, Want, Dt, 10.f);
}

void UAstraFpsComponent::RestoreFpFov()
{
	if (bFpFovTaken)
	{
		if (UCameraComponent* Cam = Camera())
		{
			Cam->FirstPersonFieldOfView = BaseFpFov;
		}
		bFpFovTaken = false;
	}
}

// ================================================================================================================== the tick and the screen

void UAstraFpsComponent::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
	SCOPE_CYCLE_COUNTER(STAT_AstraFps);
	Super::TickComponent(DeltaTime, TickType, ThisTickFunction);
	const float Dt = FMath::Min(DeltaTime, 0.1f);
	AASTRACharacter* C = Owner();
	if (!C || !C->IsLocallyControlled())
	{
		return;
	}
	const bool bLockedNow = Locked();
	bSprint = C->IsSprinting() && C->GetVelocity().Size2D() > 120.f;
	if (bHasKit && !bLockedNow)
	{
		if (IsArmed())
		{
			if (!bShown)
			{
				ShowArms(true);
			}
			TickState(Dt);
			// sprinting puts the weapon down: a reload stops, the sights drop
			if (bSprint && State == EState::Reloading)
			{
				CancelReload();
			}
			if (State == EState::Ready)
			{
				if (bFireHeld && !bSprint)
				{
					const FAstraWeaponDef& W = AstraWeapons::Get(Cur);
					if (W.bAuto || !bTriggerLatched)
					{
						if (TryFire() && !W.bAuto)
						{
							bTriggerLatched = true;
						}
					}
				}
				else if (bAutoReloadPending && !bFireHeld)
				{
					bAutoReloadPending = false;
					StartReload();
				}
			}
			TickRecoil(Dt);
			TickArms(Dt);
		}
	}
	else if (bShown)
	{
		ShowArms(false);                              // seated, in a lift, down: nothing in the hands (the state waits)
		Ads = 0.f;
		RestoreFov();
	}
	// the screen
	HurtAlpha = FMath::Max(0.f, HurtAlpha - Dt * 0.55f);
	for (FArc& A : Arcs)
	{
		A.Alpha = FMath::Max(0.f, A.Alpha - Dt * 0.7f);
	}
	Arcs.RemoveAll([](const FArc& A) { return A.Alpha <= 0.f; });
	HitMark = FMath::Max(0.f, HitMark - Dt * 4.5f);
	PromptT = FMath::Max(0.f, PromptT - Dt);
	KeysT = FMath::Max(0.f, KeysT - Dt);
	KeysAlpha = FMath::FInterpConstantTo(KeysAlpha, (KeysT > 0.f && IsArmed() && !bLockedNow) ? 1.f : 0.f, Dt, 1.2f);
	TickHud(Dt);
}

void UAstraFpsComponent::TickHud(float Dt)
{
	UWorld* W = GetWorld();
	UGameViewportClient* VC = W ? W->GetGameViewport() : nullptr;
	const AASTRACharacter* C = Owner();
	const UAstraBoardSubsystem* Board = W ? W->GetSubsystem<UAstraBoardSubsystem>() : nullptr;
	if (!VC || !C)
	{
		return;
	}
	const bool bBoarding = Board && Board->IsActive();
	const float Strength = Board ? Board->CaptainStrength() : 1.f;
	const bool bArmed = IsArmed() && !Locked();
	const bool bShowStrength = bBoarding || Strength < 0.995f;
	const bool bShow = bArmed || HurtAlpha > 0.01f || PromptT > 0.f || bShowStrength || !Arcs.IsEmpty();
	if (!bShow)
	{
		RemoveHud();
		return;
	}
	if (!Hud.IsValid())
	{
		Hud = SNew(SAstraCombatHud);
		VC->AddViewportWidgetContent(Hud.ToSharedRef(), 12);
	}
	FAstraFpsHudState& S = Hud->State;
	S.bShow = true;
	S.bCrosshair = bArmed && State != EState::Holstering;
	S.bAds = Ads > 0.6f;
	const FAstraWeaponDef& D = AstraWeapons::Get(Cur != EAstraWeapon::None ? Cur : EAstraWeapon::Rifle);
	FVector2D VP(1920.f, 1080.f);
	VC->GetViewportSize(VP);
	// the cone's width on the screen: the angle against the camera's field of view
	const UCameraComponent* Cam = Camera();
	const float Fov = Cam ? Cam->FieldOfView : 90.f;
	S.SpreadPx = FMath::Clamp((float)(FMath::Tan(FMath::DegreesToRadians(SpreadDeg(D))) / FMath::Tan(FMath::DegreesToRadians(Fov * 0.5f)) * 540.f), 4.f, 120.f);
	S.WeaponName = bArmed ? FString(D.Name) : FString();
	S.bRifle = bHasRifle;
	const FAmmo& A = AmmoOf(D.Id);
	S.Mag = A.Mag;
	S.Reserve = A.Reserve;
	S.MagSize = D.Mag;
	S.bReloading = State == EState::Reloading;
	S.ReloadAlpha = StateLen > 0.f ? StateT / StateLen : 0.f;
	S.Strength = Strength;
	S.bShowStrength = bShowStrength;
	S.bDown = Board && Board->IsCaptainDown();
	S.HurtAlpha = HurtAlpha;
	S.Arcs.Reset();
	for (const FArc& Ar : Arcs)
	{
		FAstraFpsHudState::FArc X;
		X.Yaw = Ar.Yaw;
		X.Alpha = Ar.Alpha;
		S.Arcs.Add(X);
	}
	S.HitMark = HitMark;
	S.bHitHead = bHitWasHead;
	S.Prompt = PromptText;
	S.PromptAlpha = FMath::Clamp(PromptT / 0.4f, 0.f, 1.f);
	S.KeysAlpha = KeysAlpha;
	S.bLowHint = bArmed && State == EState::Ready && A.Mag <= FMath::Max(2, D.Mag / 6) && A.Reserve > 0 && FMath::Frac(GetWorld()->GetTimeSeconds() * 1.6) < 0.7;
}

void UAstraFpsComponent::RemoveHud()
{
	UGameViewportClient* VC = GetWorld() ? GetWorld()->GetGameViewport() : nullptr;
	if (Hud.IsValid() && VC)
	{
		VC->RemoveViewportWidgetContent(Hud.ToSharedRef());
	}
	Hud.Reset();
}

// ================================================================================================================== the console

void UAstraFpsComponent::SimulateKey(const FKey& Key, bool bDown)
{
	// the key goes into the player's input as the viewport hands one over: through the mapping context, the action and the character's binding, like the mouse's
	const AASTRACharacter* C = Owner();
	APlayerController* PC = C ? Cast<APlayerController>(C->GetController()) : nullptr;
	if (PC)
	{
		PC->InputKey(FInputKeyEventArgs::CreateSimulated(Key, bDown ? IE_Pressed : IE_Released, bDown ? 1.f : 0.f));
	}
}

void UAstraFpsComponent::Describe(FOutputDevice& Ar) const
{
	static const TCHAR* const StateName[] = { TEXT("holstered"), TEXT("drawing"), TEXT("ready"), TEXT("reloading"), TEXT("holstering") };
	const AASTRACharacter* C = Owner();
	const AASTRAPlayerController* PC = C ? Cast<AASTRAPlayerController>(C->GetController()) : nullptr;
	const UAstraShipSubsystem* Ship = GetWorld() ? GetWorld()->GetSubsystem<UAstraShipSubsystem>() : nullptr;
	Ar.Logf(TEXT("kit %s (rifle %d, sidearm %d), %s, weapon %s, rounds %d in the magazine and %d spare"), bHasKit ? TEXT("yes") : TEXT("no"), bHasRifle ? 1 : 0, bHasPistol ? 1 : 0, StateName[(int32)State], Cur != EAstraWeapon::None ? AstraWeapons::Get(Cur).Name : TEXT("none"),
		Cur != EAstraWeapon::None ? AmmoOf(Cur).Mag : 0, Cur != EAstraWeapon::None ? AmmoOf(Cur).Reserve : 0);
	Ar.Logf(TEXT("aim held %d (the action arrived %d times), through the sights %.2f, trigger held %d (arrived %d times), running %d"), bAimHeld ? 1 : 0, AimEvents, Ads, bFireHeld ? 1 : 0, FireEvents, bSprint ? 1 : 0);
	Ar.Logf(TEXT("locked %d: seated %d, datapad up %d, movement ignored %d, captain's fate %d"), Locked() ? 1 : 0, PC && PC->IsSeated() ? 1 : 0, PC && PC->IsPadUp() ? 1 : 0, PC && PC->IsMoveInputIgnored() ? 1 : 0, Ship ? Ship->GetCaptainFate() : -1);
	const UCameraComponent* Cam = Camera();
	Ar.Logf(TEXT("camera: field of view %.0f, first-person %.0f (scale %.2f)"), Cam ? Cam->FieldOfView : 0.f, Cam ? Cam->FirstPersonFieldOfView : 0.f, Cam ? Cam->FirstPersonScale : 0.f);
	Ar.Logf(TEXT("arms: %s, shown %d, gun %s"), Arms ? (bArmsOnly ? TEXT("the arms-only mesh") : TEXT("the whole mannequin, head off")) : TEXT("none (the weapon alone)"), bShown ? 1 : 0, Gun && Gun->GetStaticMesh() ? *Gun->GetStaticMesh()->GetName() : TEXT("none"));
	if (!Cam || !bShown || !Gun || Cur == EAstraWeapon::None)
	{
		return;
	}
	// where the parts of it stand in the first-person view: the angles from the camera's axis (degrees right and up) and whether the picture holds them (its field is the first-person one)
	FVector2D VP(1920.f, 1080.f);
	if (const UGameViewportClient* VC = GetWorld() ? GetWorld()->GetGameViewport() : nullptr)
	{
		VC->GetViewportSize(VP);
	}
	const float HalfH = FMath::Tan(FMath::DegreesToRadians(Cam->FirstPersonFieldOfView * 0.5f));       // horizontal half-tangent
	const float HalfV = HalfH * VP.Y / FMath::Max(1.f, VP.X);
	const FAstraWeaponDef& W = AstraWeapons::Get(Cur);
	const FTransform CamT = Cam->GetComponentTransform();
	const auto Where = [&](const TCHAR* Label, const FVector& World)
	{
		const FVector L = CamT.InverseTransformPosition(World);
		if (L.X < 1.f)
		{
			Ar.Logf(TEXT("  %-10s behind the camera (%.0f, %.0f, %.0f)"), Label, L.X, L.Y, L.Z);
			return;
		}
		const bool bIn = FMath::Abs(L.Y / L.X) <= HalfH && FMath::Abs(L.Z / L.X) <= HalfV;
		Ar.Logf(TEXT("  %-10s %5.1f right %5.1f up  at %3.0f cm   %s"), Label, FMath::RadiansToDegrees(FMath::Atan2(L.Y, L.X)), FMath::RadiansToDegrees(FMath::Atan2(L.Z, L.X)), L.X, bIn ? TEXT("IN VIEW") : TEXT("out of view"));
	};
	Ar.Logf(TEXT("the view (%.0fx%.0f, first-person field %.0f degrees) holds up to %.1f right and %.1f up:"), VP.X, VP.Y, Cam->FirstPersonFieldOfView, FMath::RadiansToDegrees(FMath::Atan(HalfH)), FMath::RadiansToDegrees(FMath::Atan(HalfV)));
	const FTransform GunT = Gun->GetComponentTransform();
	Where(TEXT("rear sight"), GunT.TransformPosition(W.Sight));
	Where(TEXT("muzzle"), GunT.TransformPosition(W.Muzzle));
	Where(TEXT("left palm"), GunT.TransformPosition(W.GripLHand));       // (where the left hand is asked to go on the weapon)
	if (Pose)
	{
		Where(TEXT("hand_r"), Pose->GetBoneLocationByName(TEXT("hand_r"), EBoneSpaces::WorldSpace));
		Where(TEXT("hand_l"), Pose->GetBoneLocationByName(TEXT("hand_l"), EBoneSpaces::WorldSpace));
		Where(TEXT("lowerarm_r"), Pose->GetBoneLocationByName(TEXT("lowerarm_r"), EBoneSpaces::WorldSpace));
		Where(TEXT("lowerarm_l"), Pose->GetBoneLocationByName(TEXT("lowerarm_l"), EBoneSpaces::WorldSpace));
		Where(TEXT("upperarm_r"), Pose->GetBoneLocationByName(TEXT("upperarm_r"), EBoneSpaces::WorldSpace));
		Where(TEXT("upperarm_l"), Pose->GetBoneLocationByName(TEXT("upperarm_l"), EBoneSpaces::WorldSpace));
		// how well the hands hold it: the grip sockets of the hands (the animation's, on the solved arms) against the weapon's own places (the left one's hold is LeftIk)
		if (Arms && Arms->DoesSocketExist(TEXT("HandGrip_R")) && Arms->DoesSocketExist(TEXT("HandGrip_L")) && Pose->GetNumComponentSpaceTransforms() > 0)
		{
			// the socket of the animation's mesh, moved with the hand it is on in the solved pose: the offset of the hand's grip from the weapon's
			const FTransform GunNow = Gun->GetComponentTransform();
			const FTransform HandL = Pose->GetBoneTransformByName(TEXT("hand_l"), EBoneSpaces::WorldSpace);
			const FTransform HandLAnim = Arms->GetSocketTransform(TEXT("hand_l"), RTS_World);
			const FTransform SockLAnim = Arms->GetSocketTransform(TEXT("HandGrip_L"), RTS_World);
			const FVector SockLNow = HandL.TransformPosition(HandLAnim.InverseTransformPosition(SockLAnim.GetLocation()));
			const FVector Wanted = GunNow.TransformPosition(W.GripLHand);
			Ar.Logf(TEXT("the left hand's grip is %.1f cm from the weapon's (held %.0f%%); the right hand's grip is on the weapon's origin (%.1f cm)"), (float)FVector::Dist(SockLNow, Wanted), LeftIk * 100.f,
				(float)FVector::Dist(Pose->GetBoneLocationByName(TEXT("hand_r"), EBoneSpaces::WorldSpace), Arms->GetBoneLocation(TEXT("hand_r"), EBoneSpaces::WorldSpace)));
			// the ready pose is held at its first frame: the right-hand socket must be where the weapon table says (the sights are placed from it)
			if (State == EState::Ready)
			{
				const FVector Live = Arms->GetSocketTransform(TEXT("HandGrip_R"), RTS_Component).GetLocation();
				Ar.Logf(TEXT("the right-hand socket in the ready pose is %.2f cm from the weapon table's (0: the weapon stands where the table puts it)"), (float)FVector::Dist(Live, W.PoseGripLoc));
			}
		}
	}
}

namespace
{
	UAstraFpsComponent* FpsPlayer(UWorld* W)
	{
		const APawn* P = W ? UGameplayStatics::GetPlayerPawn(W, 0) : nullptr;
		return P ? P->FindComponentByClass<UAstraFpsComponent>() : nullptr;
	}

	// "1" or "0" (hold or let go), then "direct" to skip the input system
	bool FpsParseHold(const TArray<FString>& Args, bool& bDown, bool& bDirect)
	{
		bDirect = Args.ContainsByPredicate([](const FString& A) { return A.Equals(TEXT("direct"), ESearchCase::IgnoreCase); });
		for (const FString& A : Args)
		{
			if (A == TEXT("1") || A.Equals(TEXT("on"), ESearchCase::IgnoreCase) || A.Equals(TEXT("down"), ESearchCase::IgnoreCase))
			{
				bDown = true;
				return true;
			}
			if (A == TEXT("0") || A.Equals(TEXT("off"), ESearchCase::IgnoreCase) || A.Equals(TEXT("up"), ESearchCase::IgnoreCase))
			{
				bDown = false;
				return true;
			}
		}
		return false;
	}

	FAutoConsoleCommandWithWorld FpsCmdGive(TEXT("astra.weapons.give"), TEXT("Testing: the Captain takes the rifle and the sidearm from the armory (wherever he is)"),
		FConsoleCommandWithWorldDelegate::CreateLambda([](UWorld* W) { if (UAstraFpsComponent* F = FpsPlayer(W)) { F->SetKit(true); } }));
	FAutoConsoleCommandWithWorld FpsCmdStow(TEXT("astra.weapons.stow"), TEXT("Testing: the Captain puts the weapons back"),
		FConsoleCommandWithWorldDelegate::CreateLambda([](UWorld* W) { if (UAstraFpsComponent* F = FpsPlayer(W)) { F->SetKit(false); } }));
	FAutoConsoleCommandWithWorldAndArgs FpsCmdGiveOne(TEXT("astra.weapons.givepistol"), TEXT("Testing: the Captain takes the sidearm only (as from the ready room's locker): astra.weapons.givepistol [0 to put it back]"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& A, UWorld* W) { if (UAstraFpsComponent* F = FpsPlayer(W)) { F->GiveWeapon(EAstraWeapon::Pistol, A.Num() == 0 || A[0] != TEXT("0")); } }));

	FAutoConsoleCommandWithWorldArgsAndOutputDevice FpsCmdAim(TEXT("astra.fps.aim"),
		TEXT("Testing: astra.fps.aim 1 holds the right mouse button down (through the input system, the road of the real one: mapping, action, binding), 0 lets it go; add 'direct' to set the sights without the input system"),
		FConsoleCommandWithWorldArgsAndOutputDeviceDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* W, FOutputDevice& Ar)
		{
			UAstraFpsComponent* F = FpsPlayer(W);
			bool bDown = false, bDirect = false;
			if (!F || !FpsParseHold(Args, bDown, bDirect))
			{
				Ar.Logf(TEXT("astra.fps.aim 1|0 [direct]%s"), F ? TEXT("") : TEXT("  (no Captain on foot)"));
				return;
			}
			if (bDirect)
			{
				bDown ? F->AimPressed() : F->AimReleased();
			}
			else
			{
				F->SimulateKey(EKeys::RightMouseButton, bDown);
			}
			Ar.Logf(TEXT("aim %s%s: see astra.fps.info next frame (the action counter says whether it arrived)"), bDown ? TEXT("held") : TEXT("let go"), bDirect ? TEXT(", direct") : TEXT(", through the input"));
		}));
	FAutoConsoleCommandWithWorldArgsAndOutputDevice FpsCmdFire(TEXT("astra.fps.fire"),
		TEXT("Testing: astra.fps.fire 1 holds the left mouse button down (through the input system), 0 lets it go; add 'direct' to pull the trigger without the input system"),
		FConsoleCommandWithWorldArgsAndOutputDeviceDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* W, FOutputDevice& Ar)
		{
			UAstraFpsComponent* F = FpsPlayer(W);
			bool bDown = false, bDirect = false;
			if (!F || !FpsParseHold(Args, bDown, bDirect))
			{
				Ar.Logf(TEXT("astra.fps.fire 1|0 [direct]%s"), F ? TEXT("") : TEXT("  (no Captain on foot)"));
				return;
			}
			if (bDirect)
			{
				bDown ? F->FirePressed() : F->FireReleased();
			}
			else
			{
				F->SimulateKey(EKeys::LeftMouseButton, bDown);
			}
			Ar.Logf(TEXT("trigger %s%s"), bDown ? TEXT("held") : TEXT("let go"), bDirect ? TEXT(", direct") : TEXT(", through the input"));
		}));
	FAutoConsoleCommandWithWorldArgsAndOutputDevice FpsCmdReload(TEXT("astra.fps.reload"), TEXT("Testing: the Captain reloads the weapon in his hands"),
		FConsoleCommandWithWorldArgsAndOutputDeviceDelegate::CreateLambda([](const TArray<FString>&, UWorld* W, FOutputDevice& Ar)
		{
			if (UAstraFpsComponent* F = FpsPlayer(W))
			{
				F->ReloadPressed();
				Ar.Logf(TEXT("reload"));
			}
		}));
	FAutoConsoleCommandWithWorldArgsAndOutputDevice FpsCmdWeapon(TEXT("astra.fps.weapon"), TEXT("Testing: astra.fps.weapon rifle|pistol|holster|switch: draws a weapon, puts it away, or changes to the other"),
		FConsoleCommandWithWorldArgsAndOutputDeviceDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* W, FOutputDevice& Ar)
		{
			UAstraFpsComponent* F = FpsPlayer(W);
			if (!F || Args.IsEmpty())
			{
				Ar.Logf(TEXT("astra.fps.weapon rifle|pistol|holster|switch"));
				return;
			}
			if (Args[0].Equals(TEXT("holster"), ESearchCase::IgnoreCase))
			{
				F->ToggleHolster();
			}
			else if (Args[0].Equals(TEXT("switch"), ESearchCase::IgnoreCase))
			{
				F->QuickSwitch();
			}
			else
			{
				F->SelectWeapon(AstraWeapons::FromKey(Args[0]));
			}
			Ar.Logf(TEXT("%s"), *F->StatusText());
		}));
	FAutoConsoleCommandWithWorldArgsAndOutputDevice FpsCmdInfo(TEXT("astra.fps.info"), TEXT("Testing: the weapon's state, the actions that arrived, the arms, and where the weapon and the hands stand in the first-person view"),
		FConsoleCommandWithWorldArgsAndOutputDeviceDelegate::CreateLambda([](const TArray<FString>&, UWorld* W, FOutputDevice& Ar)
		{
			if (const UAstraFpsComponent* F = FpsPlayer(W))
			{
				F->Describe(Ar);
			}
			else
			{
				Ar.Logf(TEXT("no Captain on foot"));
			}
		}));
}
