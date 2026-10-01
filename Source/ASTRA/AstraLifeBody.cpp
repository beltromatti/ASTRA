// ASTRA — VITA, the body of someone near the Captain (see AstraLifeBody.h).

#include "AstraLifeBody.h"

#include "ASTRA.h"
#include "Animation/AnimSequence.h"
#include "AstraDoor.h"
#include "AstraLifeSim.h"
#include "AstraLifeSubsystem.h"
#include "AstraLiftSubsystem.h"
#include "AstraShipSubsystem.h"
#include "Components/AudioComponent.h"
#include "Components/PoseableMeshComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/TextRenderComponent.h"
#include "GameFramework/Character.h"
#include "Kismet/GameplayStatics.h"

DECLARE_CYCLE_STAT(TEXT("LifeBody"), STAT_AstraLifeBody, STATGROUP_Astra);

namespace
{
	// the mannequin's walk cycle moves the feet at about this speed at rate 1 (AstraCrewMember walks its visitors at 140 cm/s with rate 0.95); the
	// jog likewise. Tunable in the game when a walk looks skating.
	TAutoConsoleVariable<float> CVarWalkNatural(TEXT("astra.life.walk_natural"), 147.f, TEXT("VITA: the walk cycle's own speed (cm/s) at play rate 1"));
	TAutoConsoleVariable<float> CVarJogNatural(TEXT("astra.life.jog_natural"), 344.f, TEXT("VITA: the jog cycle's own speed (cm/s) at play rate 1"));
	TAutoConsoleVariable<float> CVarLane(TEXT("astra.life.lane_cm"), 26.f, TEXT("VITA: how far to the right of the way people keep in a corridor (cm)"));
	TAutoConsoleVariable<float> CVarShadowM(TEXT("astra.life.shadow_m"), 14.f, TEXT("VITA: bodies farther than this from the camera cast no shadow (m)"));
	constexpr float JogFrom = 220.f;     // faster than this (cm/s) they jog
}

AAstraLifeBody::AAstraLifeBody()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.bStartWithTickEnabled = false;
	// a body in the pool is nobody: its meshes do not tick either (forty parked bodies were eighty ticks a frame for nothing)
	Body->PrimaryComponentTick.bStartWithTickEnabled = false;
	Seated->PrimaryComponentTick.bStartWithTickEnabled = false;
	SetActorHiddenInGame(true);
}

bool AAstraLifeBody::SeenRecently(float Within) const
{
	return (Body && Body->WasRecentlyRendered(Within)) || (Seated && Seated->WasRecentlyRendered(Within));
}

float AAstraLifeBody::ActorYawFor(float FacingYaw) const
{
	// the mannequin faces its own +Y: standing, the actor turns a quarter off; seated and lying poses carry their own turn
	return (Mode == EMode::Walk || Mode == EMode::Stand || Mode == EMode::Lift || Mode == EMode::Off) ? FacingYaw - 90.f : FacingYaw;
}

void AAstraLifeBody::Place(const FVector& At, float FacingYaw)
{
	Turn = FacingYaw;
	SetActorLocationAndRotation(At, FRotator(0.f, ActorYawFor(FacingYaw), 0.f), false, nullptr, ETeleportType::TeleportPhysics);
}

void AAstraLifeBody::PreloadAssets(TArray<TObjectPtr<UObject>>& OutKeep)
{
	static const TCHAR* Paths[] = {
		TEXT("/Game/Characters/Mannequins/Meshes/SKM_Quinn_Simple.SKM_Quinn_Simple"),
		TEXT("/Game/Characters/Mannequins/Meshes/SKM_Manny_Simple.SKM_Manny_Simple"),
		TEXT("/Game/Characters/Mannequins/Anims/Unarmed/MM_Idle.MM_Idle"),
		TEXT("/Game/Characters/Mannequins/Anims/Unarmed/Walk/MF_Unarmed_Walk_Fwd.MF_Unarmed_Walk_Fwd"),
		TEXT("/Game/Characters/Mannequins/Anims/Unarmed/Jog/MF_Unarmed_Jog_Fwd.MF_Unarmed_Jog_Fwd"),
		TEXT("/Game/ASTRA/Crew/Materials/MI_Crew_Uniform.MI_Crew_Uniform"),
		TEXT("/Game/ASTRA/Crew/Materials/MI_Crew_Dept_Command.MI_Crew_Dept_Command"),
		TEXT("/Game/ASTRA/Crew/Materials/MI_Crew_Dept_Engineering.MI_Crew_Dept_Engineering"),
		TEXT("/Game/ASTRA/Crew/Materials/MI_Crew_Dept_Flight.MI_Crew_Dept_Flight"),
		TEXT("/Game/ASTRA/Crew/Materials/MI_Crew_Dept_Medical.MI_Crew_Dept_Medical"),
		TEXT("/Game/ASTRA/Crew/Materials/MI_Crew_Dept_Science.MI_Crew_Dept_Science"),
		TEXT("/Game/ASTRA/Crew/Materials/MI_Crew_Dept_Security.MI_Crew_Dept_Security")};
	for (const TCHAR* Path : Paths)
	{
		if (UObject* O = StaticLoadObject(UObject::StaticClass(), nullptr, Path))
		{
			OutKeep.Add(O);
		}
	}
}

bool AAstraLifeBody::LooksRight(FString& OutWhy) const
{
	switch (Mode)
	{
	case EMode::Walk:
	case EMode::Stand:
	case EMode::Lift:
		if (IsHidden())                        { OutWhy = TEXT("on its feet but hidden"); return false; }
		if (!Body->GetSkeletalMeshAsset())     { OutWhy = TEXT("on its feet with no mesh"); return false; }
		if (!Body->IsVisible())                { OutWhy = TEXT("on its feet but its mesh is not visible"); return false; }
		if (!Body->IsPlaying())                { OutWhy = TEXT("on its feet with no animation"); return false; }
		if (Seated->IsVisible())               { OutWhy = TEXT("on its feet with the seated mesh showing"); return false; }
		return true;
	case EMode::Sit:
	case EMode::Lie:
		if (IsHidden())                        { OutWhy = TEXT("seated or lying but hidden"); return false; }
		if (!Seated->GetSkinnedAsset())        { OutWhy = TEXT("seated or lying with no mesh"); return false; }
		if (!Seated->IsVisible())              { OutWhy = TEXT("seated or lying but the pose's mesh is not visible"); return false; }
		if (Body->IsVisible())                 { OutWhy = TEXT("seated or lying with the standing mesh showing"); return false; }
		return true;
	case EMode::Shaft:
		if (!IsHidden())                       { OutWhy = TEXT("in a lift or a tower but showing"); return false; }
		return true;
	default:
		OutWhy = TEXT("bound but not set");
		return false;
	}
}

void AAstraLifeBody::Shadows(bool bOn)
{
	if (bOn != bShadows)
	{
		bShadows = bOn;
		Body->SetCastShadow(bOn);
		Seated->SetCastShadow(bOn);
	}
}

void AAstraLifeBody::Bind(UAstraLifeSubsystem* InOwner, int32 InPerson)
{
	Owner = InOwner;
	PersonIdx = InPerson;
	const FAstraLifePerson& P = InOwner->Sim().Person(InPerson);
	const UAstraShipSubsystem* Ship = GetWorld() ? GetWorld()->GetSubsystem<UAstraShipSubsystem>() : nullptr;
	if (Ship && Ship->GetRoster().Get().IsValidIndex(P.Roster))
	{
		const FAstraCrewman& R = Ship->GetRoster().Get()[P.Roster];
		DisplayName = R.Name();
		SetUniformDept(R.Dept);
	}
	StationId = FString::Printf(TEXT("npc%d"), P.Roster);
	NameTag->SetText(FText::FromString(DisplayName));
	bFemaleBody = P.bFemale;
	if (!IdleAnim)
	{
		IdleAnim = LoadObject<UAnimSequence>(nullptr, TEXT("/Game/Characters/Mannequins/Anims/Unarmed/MM_Idle.MM_Idle"));
		WalkAnim = LoadObject<UAnimSequence>(nullptr, TEXT("/Game/Characters/Mannequins/Anims/Unarmed/Walk/MF_Unarmed_Walk_Fwd.MF_Unarmed_Walk_Fwd"));
		JogAnim = LoadObject<UAnimSequence>(nullptr, TEXT("/Game/Characters/Mannequins/Anims/Unarmed/Jog/MF_Unarmed_Jog_Fwd.MF_Unarmed_Jog_Fwd"));
	}
	Mode = EMode::Off;
	Rider.Clear();
	RideSeg = INDEX_NONE;
	bRideWalk = false;
	Offset = FVector2D::ZeroVector;
	BlockedS = 0.f;
	FaceBlend = 0.f;
	SinceSpoke = 100.f;
	TimeAcc = 0.f;
	Ticks = 0;
	bFresh = true;
	InOwner->Sim().SetBodied(InPerson, true);
	Body->SetComponentTickEnabled(true);
	Seated->SetComponentTickEnabled(true);
	SetActorTickEnabled(true);
	SetActorTickInterval(0.f);
	// the first pose, from where the person is now
	Place(P.Pos, P.Phase == FAstraLifePerson::EPhase::Walking ? FMath::RadiansToDegrees(FMath::Atan2(P.Route.Heading().Y, P.Route.Heading().X)) : P.TargetYaw);
	Tick(0.f);
}

void AAstraLifeBody::Unbind()
{
	if (UAstraLifeSubsystem* L = Owner.Get())
	{
		if (PersonIdx != INDEX_NONE)
		{
			L->Sim().SetBodied(PersonIdx, false);
		}
	}
	Rider.Clear();                                        // (out of the car it rides, and its place in it given back)
	AstraDoors::RemoveWalker(this);
	if (IsSpeaking())
	{
		CancelLine(0.25f);
	}
	PersonIdx = INDEX_NONE;
	Mode = EMode::Off;
	StationId.Reset();
	SetActorHiddenInGame(true);
	SetActorTickEnabled(false);
	Body->Stop();
	Body->SetVisibility(false);
	Seated->SetVisibility(false);
	Body->SetComponentTickEnabled(false);
	Seated->SetComponentTickEnabled(false);
}

void AAstraLifeBody::SetMode(EMode M, const FAstraLifePerson& P)
{
	const EMode Old = Mode;
	if (M == Old)
	{
		return;
	}
	if (M == EMode::Walk)
	{
		AstraDoors::AddWalker(this);
	}
	else if (Old == EMode::Walk)
	{
		AstraDoors::RemoveWalker(this);
	}
	Mode = M;
	FRandomStream R(PersonIdx * 7919 + (int32)M);
	switch (M)
	{
	case EMode::Shaft:
		SetActorHiddenInGame(true);                      // in a lift or a stair tower: nobody sees them
		ShaftT = 0.f;
		return;
	case EMode::Walk:
	case EMode::Stand:
	case EMode::Lift:
	{
		SetActorHiddenInGame(false);
		if (Old != EMode::Walk && Old != EMode::Stand && Old != EMode::Lift)
		{
			Posture = EAstraCrewPosture::Standing;
			ReclineDeg = 20.f;
			Seated->SetVisibility(false);
			SetBody(bFemaleBody);                        // the standing mesh, its uniform, the idle cycle
			Body->SetVisibility(true);
			Voice->SetRelativeLocation(FVector(0.f, 0.f, 160.f));
		}
		if (M == EMode::Walk)
		{
			bJog = false;                                 // (chosen in TickWalk by the pace)
			if (WalkAnim)
			{
				Body->PlayAnimation(WalkAnim, true);
			}
		}
		else if (IdleAnim)
		{
			Body->PlayAnimation(IdleAnim, true);
			Body->SetPlayRate(0.85f + 0.25f * R.FRand());
			Body->SetPosition(R.FRand() * IdleAnim->GetPlayLength(), false);
		}
		return;
	}
	case EMode::Sit:
	case EMode::Lie:
	{
		SetActorHiddenInGame(false);
		Body->Stop();
		Body->SetVisibility(false);
		if (M == EMode::Sit)
		{
			Posture = (P.TargetKind == EAstraPlaceKind::Eat || P.TargetKind == EAstraPlaceKind::Work) ? EAstraCrewPosture::SeatedConsole : EAstraCrewPosture::SeatedArmchair;
			SeatHipHeight = P.TargetHeight > 0.f ? P.TargetHeight : 50.f;
			Voice->SetRelativeLocation(FVector(0.f, 0.f, 160.f));
		}
		else
		{
			Posture = EAstraCrewPosture::Lying;
			ReclineDeg = 0.f;                            // flat on their back, as the Red watch's sleepers in the berthing
		}
		SetBody(bFemaleBody);                            // the seated pose's mesh, uniform and skeleton
		Seated->SetVisibility(true);
		return;
	}
	default:
		return;
	}
}

void AAstraLifeBody::TickWalk(float Dt, const FAstraLifePerson& P)
{
	UAstraLifeSubsystem* L = Owner.Get();
	FAstraLifeSim& Sim = L->Sim();
	const float Speed = Sim.WalkSpeed(P);
	const FVector2D Dir = P.Route.Heading();
	const FVector Me = GetActorLocation();
	// the way ahead: the Captain (a pawn on foot) and the others: slow down and step round instead of walking through them
	float Slow = 1.f;
	FVector2D Push = FVector2D::ZeroVector;
	auto Avoid = [&](const FVector& Other, float Radius, float Weight)
	{
		const FVector2D Rel(Other.X - Me.X, Other.Y - Me.Y);
		const float D = Rel.Size();
		if (D < Radius && D > 1.f && FMath::Abs(Other.Z - Me.Z) < 170.f)
		{
			const FVector2D Away = -Rel / D;
			Push += Away * (Radius - D) * Weight;
			if (!Dir.IsNearlyZero() && FVector2D::DotProduct(Rel / D, Dir) > 0.35f)
			{
				Slow = FMath::Min(Slow, FMath::Clamp((D - 45.f) / (Radius - 45.f), 0.f, 1.f));
			}
		}
	};
	if (const APawn* Pawn = UGameplayStatics::GetPlayerPawn(this, 0))
	{
		if (Pawn->IsA<ACharacter>())
		{
			Avoid(Pawn->GetActorLocation(), 120.f, 0.9f);
		}
	}
	for (const TObjectPtr<AAstraLifeBody>& B : L->PoolView())
	{
		if (B && B != this && B->InUse() && B->Mode != EMode::Shaft && B->Mode != EMode::Off)
		{
			Avoid(B->GetActorLocation(), 85.f, 0.5f);
		}
	}
	BlockedS = Slow < 0.2f ? BlockedS + Dt : 0.f;
	// a body that has waited a while for the way to clear goes on at a crawl (nobody stands in a corridor for ever)
	const float Go = BlockedS > 2.5f ? 0.35f : Slow;
	Sim.MoveBody(PersonIdx, Dt * Go, Speed);
	// the walk cycle follows the pace
	const bool bWantJog = Speed > JogFrom;
	if (bWantJog != bJog && (bWantJog ? JogAnim : WalkAnim))
	{
		bJog = bWantJog;
		Body->PlayAnimation(bJog ? JogAnim : WalkAnim, true);
	}
	Body->SetPlayRate(FMath::Clamp(Speed / (bJog ? CVarJogNatural.GetValueOnGameThread() : CVarWalkNatural.GetValueOnGameThread()) * FMath::Max(Go, 0.f), 0.f, 1.5f));
	// the floor plane position: the route, a step to the right of it, and round whoever is in the way
	const FVector Base = P.Pos;
	const FVector2D Right = FVector2D(-Dir.Y, Dir.X);
	const FVector2D Want = Right * CVarLane.GetValueOnGameThread() + Push.GetClampedToMaxSize(70.f);
	Offset = FMath::Vector2DInterpTo(Offset, Want, Dt, 6.f);
	const FVector At(Base.X + Offset.X, Base.Y + Offset.Y, Base.Z);
	const float WantYaw = Dir.IsNearlyZero() ? Turn : FMath::RadiansToDegrees(FMath::Atan2(Dir.Y, Dir.X));
	Turn = FMath::FixedTurn(Turn, WantYaw, 420.f * Dt);
	SetActorLocationAndRotation(At, FRotator(0.f, ActorYawFor(Turn), 0.f), false, nullptr, ETeleportType::None);
}

void AAstraLifeBody::TickStand(float Dt, const FAstraLifePerson& P)
{
	// at their post: slip into place, face the way the plan says, and turn to the Captain while speaking to them
	FVector At = GetActorLocation();
	const FVector Goal = P.Target;
	// the Captain walking into someone who stands: they give way a step (nobody is walked through) and come back when the way is clear
	FVector2D Push = FVector2D::ZeroVector;
	if (const APawn* Pawn = UGameplayStatics::GetPlayerPawn(this, 0); Pawn && Pawn->IsA<ACharacter>())
	{
		const FVector PawnAt = Pawn->GetActorLocation();
		const FVector2D Rel(Goal.X - PawnAt.X, Goal.Y - PawnAt.Y);
		const float D = Rel.Size();
		if (D < 100.f && FMath::Abs(Goal.Z - PawnAt.Z) < 170.f)
		{
			Push = (D > 1.f ? Rel / D : FVector2D(1.f, 0.f)) * (100.f - D);
		}
	}
	Offset = FMath::Vector2DInterpTo(Offset, Push.GetClampedToMaxSize(60.f), Dt, 7.f);
	At = FMath::VInterpConstantTo(At, FVector(Goal.X + Offset.X, Goal.Y + Offset.Y, Goal.Z), Dt, 130.f);
	SinceSpoke = IsSpeaking() ? 0.f : SinceSpoke + Dt;
	FaceBlend = FMath::FInterpTo(FaceBlend, SinceSpoke < 2.5f ? 1.f : 0.f, Dt, 2.5f);
	float Want = P.TargetYaw;
	if (FaceBlend > 0.001f)
	{
		if (const APlayerCameraManager* Cam = UGameplayStatics::GetPlayerCameraManager(this, 0))
		{
			const FVector To = Cam->GetCameraLocation() - At;
			const float ToCam = FMath::RadiansToDegrees(FMath::Atan2(To.Y, To.X));
			Want = P.TargetYaw + FMath::Clamp(FMath::FindDeltaAngleDegrees(P.TargetYaw, ToCam), -70.f, 70.f) * FaceBlend;
		}
	}
	Turn = FMath::FixedTurn(Turn, Want, 240.f * Dt);
	SetActorLocationAndRotation(At, FRotator(0.f, ActorYawFor(Turn), 0.f), false, nullptr, ETeleportType::None);
}

bool AAstraLifeBody::TickLift(float Dt, const FAstraLifePerson& P)
{
	UAstraLifeSubsystem* L = Owner.Get();
	UWorld* W = GetWorld();
	UAstraLiftSubsystem* Lifts = W ? W->GetSubsystem<UAstraLiftSubsystem>() : nullptr;
	const FAstraLifeRoute& R = P.Route;
	if (!Rider.Active())
	{
		if (!L || !Lifts || !Lifts->IsBuilt() || P.Phase != FAstraLifePerson::EPhase::Walking || R.Done())
		{
			return false;
		}
		const FVector A(R.Pts[R.Seg]);
		if (R.Seg == RideSeg && A.Equals(RideA, 1.f))
		{
			return false;                                    // this stretch of the route has been looked at: it is not a ride, or it has been ridden
		}
		RideSeg = R.Seg;
		RideA = A;
		const FVector B(R.Pts[R.Seg + 1]);
		int32 Line = INDEX_NONE, From = INDEX_NONE, To = INDEX_NONE;
		// (a body made in the middle of a ride, or away from its landing, leaves it to the abstract clock)
		if (R.F > 0.1f || FVector::Dist2D(GetActorLocation(), A) > 300.f || !Lifts->FindRide(A, B, Line, From, To) || !Rider.Begin(Lifts, this, PersonIdx, Line, From, To, B))
		{
			return false;
		}
		SetMode(EMode::Lift, P);
		bRideWalk = false;
	}
	else if (!L || !Lifts || P.Phase != FAstraLifePerson::EPhase::Walking || R.Done() || R.Seg != RideSeg || !FVector(R.Pts[R.Seg]).Equals(RideA, 1.f))
	{
		EndLift(P, true);                                    // the plan changed under them (an alarm, a damaged door): they are where the person is now
		return false;
	}
	const float Speed = L->Sim().WalkSpeed(P) * 0.85f;       // (a little slower than in a corridor: a lobby, a doorway, a car)
	const FAstraLiftRider::EStep Step = Rider.Tick(Dt, Speed);
	if (Rider.Walking() != bRideWalk)
	{
		bRideWalk = Rider.Walking();
		if (UAnimSequence* Anim = bRideWalk ? WalkAnim : IdleAnim)
		{
			Body->PlayAnimation(Anim, true);
			Body->SetPlayRate(bRideWalk ? 1.f : 0.9f);
		}
	}
	if (bRideWalk)
	{
		Body->SetPlayRate(FMath::Clamp(Speed / CVarWalkNatural.GetValueOnGameThread(), 0.f, 1.5f));
	}
	Turn = FMath::FixedTurn(Turn, Rider.FacingYaw(), 360.f * Dt);
	SetActorRotation(FRotator(0.f, ActorYawFor(Turn), 0.f));
	if (Step == FAstraLiftRider::EStep::Done || Step == FAstraLiftRider::EStep::Failed)
	{
		EndLift(P, Step == FAstraLiftRider::EStep::Failed);
		return false;
	}
	return true;
}

void AAstraLifeBody::EndLift(const FAstraLifePerson& P, bool bPutThere)
{
	Rider.Clear();                                           // (detached from the car, its place given back, no longer a walker of the doors)
	bRideWalk = false;
	Offset = FVector2D::ZeroVector;
	UAstraLifeSubsystem* L = Owner.Get();
	if (!L)
	{
		return;
	}
	FAstraLifeSim& Sim = L->Sim();
	const FAstraLifeRoute& R = P.Route;
	if (!R.Done() && R.Seg == RideSeg && FVector(R.Pts[R.Seg]).Equals(RideA, 1.f))
	{
		// the person comes out at the far end of the stretch: what the rider lived is the time the abstract ride would have taken
		const float Speed = Sim.WalkSpeed(P);
		Sim.MoveBody(PersonIdx, (1.f - R.F) * R.SegSeconds(R.Seg, Speed, Sim.GetMap().Speed) + 0.02f, Speed);
	}
	if (bPutThere)
	{
		Place(P.Pos, P.Phase == FAstraLifePerson::EPhase::Walking ? FMath::RadiansToDegrees(FMath::Atan2(P.Route.Heading().Y, P.Route.Heading().X)) : P.TargetYaw);
	}
}

void AAstraLifeBody::Tick(float DeltaSeconds)
{
	SCOPE_CYCLE_COUNTER(STAT_AstraLifeBody);
	UAstraLifeSubsystem* L = Owner.Get();
	if (!L || PersonIdx == INDEX_NONE)
	{
		return;
	}
	const FAstraLifePerson& P = L->Sim().Person(PersonIdx);
	if (P.Status == 2 || P.Act == EAstraLifeAct::Dead)
	{
		Rider.Clear();
		SetMode(EMode::Shaft, P);
		return;
	}
	// a body nobody sees ticks rarely (its feet still move); one close or seen, every frame
	const bool bSeen = SeenRecently(0.4f) || IsSpeaking();
	TimeAcc += DeltaSeconds;
	const float Dist = FVector::Dist(GetActorLocation(), L->Eye());
	const float Interval = bSeen ? 0.f : (Dist < 2500.f ? 0.1f : 0.25f);
	if (!bFresh && TimeAcc < Interval)
	{
		return;
	}
	const float Dt = bFresh ? 0.f : TimeAcc;
	bFresh = false;
	TimeAcc = 0.f;
	++Ticks;
	Shadows(Dist < CVarShadowM.GetValueOnGameThread() * 100.f);

	// a ride in a real lift (ASCENSORI): the person's route is on one, and the body calls it, boards it, rides it and steps out; otherwise (no lift built there, a stair, a ride
	// that was already under way when the body was made) the ride is the abstract one below: hidden for the seconds the simulation gives it
	if (TickLift(Dt, P))
	{
		SetActorTickInterval(bSeen ? 0.f : 0.1f);
		return;
	}

	// what they are doing now: the walk the person is on, or the pose of the place they are at
	EMode Want;
	if (P.Phase == FAstraLifePerson::EPhase::Walking)
	{
		Want = P.Route.InShaft() ? EMode::Shaft : EMode::Walk;
	}
	else if (P.Phase == FAstraLifePerson::EPhase::WaitRoute)
	{
		Want = (Mode == EMode::Sit || Mode == EMode::Lie || Mode == EMode::Off || Mode == EMode::Shaft) ? EMode::Stand : Mode;
	}
	else
	{
		switch (P.TargetKind)
		{
		case EAstraPlaceKind::Sit:
		case EAstraPlaceKind::Eat:   Want = EMode::Sit; break;
		case EAstraPlaceKind::Sleep: Want = EMode::Lie; break;
		default:                     Want = EMode::Stand; break;
		}
	}
	const EMode Was = Mode;
	SetMode(Want, P);
	if (Want == EMode::Shaft)
	{
		SetActorTickInterval(0.2f);                          // in a lift or a tower: nobody sees them
		return;
	}
	if (Was == EMode::Shaft || Was == EMode::Off)
	{
		Place(P.Pos, P.Phase == FAstraLifePerson::EPhase::Walking ? FMath::RadiansToDegrees(FMath::Atan2(P.Route.Heading().Y, P.Route.Heading().X)) : P.TargetYaw);
	}
	switch (Mode)
	{
	case EMode::Walk:
		TickWalk(Dt, P);
		break;
	case EMode::Stand:
		TickStand(Dt, P);
		break;
	case EMode::Sit:
	case EMode::Lie:
	{
		// placed where the plan puts the seat or the bunk; the pose's own life (breathing, the head turning to the Captain) is the crew member's
		const FVector Goal = Mode == EMode::Lie ? P.Target + FVector(0.f, 0.f, P.TargetHeight) : P.Target;
		if (Was != Mode || !GetActorLocation().Equals(Goal, 2.f))
		{
			Place(Goal, P.TargetYaw);
		}
		Super::Tick(Dt);
		break;
	}
	default:
		break;
	}
	// How often to think next: every frame while anyone could see them, rarely when nobody can. The seated pose is the crew member's own
	// (its base class would leave a half-second heartbeat behind, which a walk must not inherit) and is the dearest of them (a pose of ~80
	// bones rebuilt): within eight metres every frame, farther the breathing and the head are too small to tell apart at a lower rate.
	const bool bWatched = SeenRecently(0.4f) || IsSpeaking();
	if (Mode == EMode::Sit || Mode == EMode::Lie)
	{
		SetActorTickInterval(IsSpeaking() ? 0.f : !bWatched ? 0.5f : Dist < 800.f ? 0.f : Dist < 2000.f ? 0.07f : 0.15f);
	}
	else
	{
		SetActorTickInterval(bWatched ? 0.f : 0.1f);
	}
}
