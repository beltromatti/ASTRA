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
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/GameViewportClient.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "InputActionValue.h"
#include "HAL/IConsoleManager.h"
#include "Kismet/GameplayStatics.h"

DECLARE_CYCLE_STAT(TEXT("Weapons"), STAT_AstraFps, STATGROUP_Astra);

namespace
{
	// where the sight of the weapon is against the camera (cm; x ahead, y right, z up), from the hip and through the sights: the numbers to tune in the game
	float GHipX = 30.f, GHipY = 15.f, GHipZ = -14.f;
	float GAdsX = 13.f, GAdsY = 0.f, GAdsZ = 0.f;
	float GLowX = 8.f, GLowY = 14.f, GLowZ = -40.f;                       // lowered (running, putting it away)
	int32 GArmsOn = 1;
	FAutoConsoleVariableRef FpsCvHipX(TEXT("astra.fps.hip_x"), GHipX, TEXT("The weapon's sight from the hip, cm ahead of the camera"));
	FAutoConsoleVariableRef FpsCvHipY(TEXT("astra.fps.hip_y"), GHipY, TEXT("The weapon's sight from the hip, cm to the right of the camera"));
	FAutoConsoleVariableRef FpsCvHipZ(TEXT("astra.fps.hip_z"), GHipZ, TEXT("The weapon's sight from the hip, cm above the camera (negative: below)"));
	FAutoConsoleVariableRef FpsCvAdsX(TEXT("astra.fps.ads_x"), GAdsX, TEXT("The weapon's rear sight through the sights, cm ahead of the camera"));
	FAutoConsoleVariableRef FpsCvAdsY(TEXT("astra.fps.ads_y"), GAdsY, TEXT("The weapon's rear sight through the sights, cm to the right of the camera"));
	FAutoConsoleVariableRef FpsCvAdsZ(TEXT("astra.fps.ads_z"), GAdsZ, TEXT("The weapon's rear sight through the sights, cm above the camera"));
	FAutoConsoleVariableRef FpsCvArms(TEXT("astra.fps.arms"), GArmsOn, TEXT("1: the mannequin's arms hold the weapon; 0: the weapon alone (the fallback)"));

	constexpr float FpsKeysShownS = 24.f;
	const TCHAR* const FpsKeysLine = TEXT("LMB fire   RMB aim   R reload   1 rifle   2 sidearm   Q last weapon   H holster   Shift run   C crouch · hold C: prone   F1 all keys");

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
	RemoveHud();
	Super::EndPlay(Reason);
}

// ================================================================================================================== the kit

void UAstraFpsComponent::SetKit(bool bTake)
{
	if (bTake == bHasKit)
	{
		return;
	}
	bHasKit = bTake;
	if (bTake)
	{
		const FAstraWeaponDef& R = AstraWeapons::Get(EAstraWeapon::Rifle);
		const FAstraWeaponDef& P = AstraWeapons::Get(EAstraWeapon::Pistol);
		Rifle.Mag = R.Mag;
		Rifle.Reserve = R.Mag * R.SpareMags;
		Pistol.Mag = P.Mag;
		Pistol.Reserve = P.Mag * P.SpareMags;
		KeysT = FpsKeysShownS;
		Last = EAstraWeapon::Pistol;
		StartDraw(EAstraWeapon::Rifle);
	}
	else
	{
		// back in the rack: the weapons are put away (their rounds stay with them)
		if (State != EState::Holstered)
		{
			State = EState::Holstered;
			Cur = EAstraWeapon::None;
			ShowArms(false);
		}
		bFireHeld = false;
		bAimHeld = false;
	}
}

FString UAstraFpsComponent::StatusText() const
{
	if (!bHasKit)
	{
		return FString();
	}
	const FAstraWeaponDef& W = AstraWeapons::Get(Cur != EAstraWeapon::None ? Cur : EAstraWeapon::Rifle);
	const FAmmo& A = AmmoOf(W.Id);
	return FString::Printf(TEXT("%s %s: %d in the magazine, %d spare%s"), W.Name, W.Role, A.Mag, A.Reserve, IsArmed() ? TEXT(", in his hands") : TEXT(", holstered"));
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
	bFireHeld = true;
	bTriggerLatched = false;
	// with nothing in the hands, the button draws the last weapon
	if (bHasKit && State == EState::Holstered && !Locked())
	{
		StartDraw(Last != EAstraWeapon::None ? Last : EAstraWeapon::Rifle);
	}
}

void UAstraFpsComponent::FireReleased()
{
	bFireHeld = false;
	bTriggerLatched = false;
}

void UAstraFpsComponent::AimPressed()
{
	bAimHeld = true;
}

void UAstraFpsComponent::AimReleased()
{
	bAimHeld = false;
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
	if (!bHasKit || FMath::IsNearlyZero(Direction))
	{
		return;
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
		SelectWeapon(Last != EAstraWeapon::None ? Last : EAstraWeapon::Rifle);
	}
	else
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
		StartDraw(Last != EAstraWeapon::None ? Last : EAstraWeapon::Rifle);
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
	if (KeysT <= 0.f && KeysAlpha <= 0.f)
	{
		KeysT = 6.f;
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
	// the arms: the same body as the first-person arms of the character (so the colourway matches), on a mesh of their own that plays the mannequin's rifle animations
	USkeletalMesh* Mesh = C->GetFirstPersonMesh() ? C->GetFirstPersonMesh()->GetSkeletalMeshAsset() : nullptr;
	if (!Mesh)
	{
		Mesh = LoadObject<USkeletalMesh>(nullptr, TEXT("/Game/Characters/Mannequins/Meshes/SKM_Manny_Simple.SKM_Manny_Simple"));
	}
	if (Mesh && GArmsOn)
	{
		Arms = NewObject<USkeletalMeshComponent>(C, TEXT("WeaponArms"));
		Arms->SetupAttachment(Cam);
		Arms->SetSkeletalMeshAsset(Mesh);
		Arms->SetAnimationMode(EAnimationMode::AnimationSingleNode);
		Arms->VisibilityBasedAnimTickOption = EVisibilityBasedAnimTickOption::AlwaysTickPoseAndRefreshBones;
		Arms->bEnableUpdateRateOptimizations = false;
		Arms->SetReceivesDecals(false);
		Common(Arms);
		if (C->GetFirstPersonMesh())
		{
			// the mesh's own materials follow the character's arms (its colourway)
			for (int32 i = 0; i < C->GetFirstPersonMesh()->GetNumMaterials() && i < Arms->GetNumMaterials(); ++i)
			{
				Arms->SetMaterial(i, C->GetFirstPersonMesh()->GetMaterial(i));
			}
		}
		Arms->RegisterComponent();
		Arms->SetVisibility(false);
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
	EnsureArms();
	AASTRACharacter* C = Owner();
	if (Arms)
	{
		Arms->SetVisibility(bOn);
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
		C->GetFirstPersonMesh()->SetVisibility(!(bOn && Arms));
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
	// Where the arms (or the weapon alone) stand against the camera so that the weapon's sight is at a chosen place and the weapon points where the camera looks. The ready
	// pose's right-hand socket is known (the probe's numbers in the weapon table): the weapon's own frame (barrel +Y, top +Z, its left +X) in the arms' mesh space is
	// that socket; the camera's frame is x ahead, y right, z up, so a vector at (barrel, -left, top) of the weapon is at (x, y, z) of the camera.
	FVector SocketLoc = FVector::ZeroVector;
	FQuat SocketQ = FQuat::Identity;
	if (Arms)
	{
		SocketLoc = W.PoseGripLoc;
		SocketQ = FpsPoseQuat(W);
	}
	const FVector B = SocketQ.RotateVector(FVector(0, 1, 0)), U = SocketQ.RotateVector(FVector(0, 0, 1)), Ex = SocketQ.RotateVector(FVector(1, 0, 0));
	const FQuat Inv = FMatrix(B, -Ex, U, FVector::ZeroVector).ToQuat();       // columns: where the camera's x, y, z go in the mesh
	const FQuat Base = Inv.Inverse();
	SightInMesh = SocketLoc + SocketQ.RotateVector(W.Sight);
	const auto Place = [&](const FVector& Target, const FRotator& Extra, FVector& OutLoc, FQuat& OutRot)
	{
		OutRot = FQuat(Extra) * Base;
		OutLoc = Target - OutRot.RotateVector(SightInMesh);
	};
	Place(FVector(GHipX, GHipY, GHipZ), FRotator(-1.5f, -2.5f, 0.f), HipLoc, HipRot);
	Place(FVector(GAdsX, GAdsY, GAdsZ), FRotator::ZeroRotator, AdsLoc, AdsRot);
	bCalibrated = true;
	UE_LOG(LogASTRA, Log, TEXT("[Fps] %s: the arms' hip place %s, sights %s (%s)"), W.Name, *HipLoc.ToString(), *AdsLoc.ToString(), Arms ? TEXT("on the mannequin's arms") : TEXT("the weapon alone"));
}

void UAstraFpsComponent::PlayArms(UAnimSequence* A, bool bLoop, float Rate)
{
	if (Arms && A)
	{
		Arms->PlayAnimation(A, bLoop);
		Arms->SetPlayRate(FMath::Clamp(Rate, 0.2f, 4.f));
	}
}

void UAstraFpsComponent::TickArms(float Dt)
{
	if (!bShown || !Gun || !bCalibrated || Cur == EAstraWeapon::None)
	{
		return;
	}
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
		const FQuat LowBase = FQuat(FRotator(-34.f, 26.f, -8.f)) * AdsRot;
		const FVector LowLoc = FVector(GLowX, GLowY, GLowZ) - LowBase.RotateVector(SightInMesh);
		Q = FQuat::Slerp(Q, LowBase, SprintAlpha);
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
	S.Keys = FpsKeysLine;
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

namespace
{
	UAstraFpsComponent* FpsPlayer(UWorld* W)
	{
		const APawn* P = W ? UGameplayStatics::GetPlayerPawn(W, 0) : nullptr;
		return P ? P->FindComponentByClass<UAstraFpsComponent>() : nullptr;
	}

	FAutoConsoleCommandWithWorld FpsCmdGive(TEXT("astra.weapons.give"), TEXT("Testing: the Captain takes the rifle and the sidearm from the armory (wherever he is)"),
		FConsoleCommandWithWorldDelegate::CreateLambda([](UWorld* W) { if (UAstraFpsComponent* F = FpsPlayer(W)) { F->SetKit(true); } }));
	FAutoConsoleCommandWithWorld FpsCmdStow(TEXT("astra.weapons.stow"), TEXT("Testing: the Captain puts the weapons back"),
		FConsoleCommandWithWorldDelegate::CreateLambda([](UWorld* W) { if (UAstraFpsComponent* F = FpsPlayer(W)) { F->SetKit(false); } }));
}
