// ASTRA — a person's ride in a real lift car (see AstraLiftRider.h).

#include "AstraLiftRider.h"

#include "AstraDoor.h"
#include "AstraLiftCar.h"
#include "AstraLiftSubsystem.h"
#include "GameFramework/Actor.h"

namespace
{
	constexpr float RecallEveryS = 6.f;        // the call is pressed again now and then (a call that was served while nobody could board is not forgotten)
	constexpr float GiveUpWaitS = 360.f;       // nobody waits for a car for ever (a shuttle's round of the Spine is a few minutes): the owner puts them where their route says
	constexpr float BoardMaxS = 15.f;
	constexpr float InsideMaxS = 420.f;
	constexpr float AlightMaxS = 15.f;
	constexpr float StepSlackCm = 8.f;         // a step that would end this close to a point of the way ends at it (a body that steps a little long does not circle)
}

const TCHAR* FAstraLiftRider::StepName() const
{
	switch (Phase)
	{
	case EStep::Wait:   return TEXT("waiting");
	case EStep::Board:  return TEXT("boarding");
	case EStep::Inside: return TEXT("riding");
	case EStep::Alight: return TEXT("alighting");
	case EStep::Done:   return TEXT("done");
	case EStep::Failed: return TEXT("failed");
	default:            return TEXT("none");
	}
}

AAstraLiftCar* FAstraLiftRider::Car() const
{
	return Lifts ? Lifts->CarOf(LineIdx) : nullptr;
}

void FAstraLiftRider::SetStep(EStep S)
{
	Phase = S;
	InStep = 0.f;
}

void FAstraLiftRider::SetWalker(bool bOn)
{
	if (bOn == bWalker)
	{
		return;
	}
	bWalker = bOn;
	if (const AActor* A = Body.Get())
	{
		if (bOn)
		{
			AstraDoors::AddWalker(A);
		}
		else
		{
			AstraDoors::RemoveWalker(A);
		}
	}
}

void FAstraLiftRider::Attach(AAstraLiftCar* C)
{
	if (AActor* A = Body.Get(); A && C && !bAttached)
	{
		A->AttachToActor(C, FAttachmentTransformRules::KeepWorldTransform);
		bAttached = true;
	}
}

void FAstraLiftRider::Detach()
{
	if (AActor* A = Body.Get(); A && bAttached)
	{
		A->DetachFromActor(FDetachmentTransformRules::KeepWorldTransform);
	}
	bAttached = false;
}

bool FAstraLiftRider::Begin(UAstraLiftSubsystem* InLifts, AActor* InBody, int32 InWho, int32 InLine, int32 InFrom, int32 InTo, const FVector& InFinishCm)
{
	End();
	Phase = EStep::None;
	if (!InLifts || !InBody || InFrom == InTo || !InLifts->CarOf(InLine) || !InLifts->LandingOf(InLine, InFrom) || !InLifts->LandingOf(InLine, InTo))
	{
		return false;
	}
	Lifts = InLifts;
	Body = InBody;
	Who = InWho;
	LineIdx = InLine;
	FromStop = InFrom;
	ToStop = InTo;
	SlotIdx = INDEX_NONE;
	Finish = InFinishCm;
	WaitedAt = RodeFor = RecallT = 0.f;
	Way.Reset();
	WayAt = 0;
	const FVector Door = Lifts->LandingOf(LineIdx, FromStop)->DoorCm();
	const FVector Here = InBody->GetActorLocation();
	Yaw = FMath::RadiansToDegrees(FMath::Atan2(Door.Y - Here.Y, Door.X - Here.X));
	SetStep(EStep::Wait);
	Lifts->RiderCall(LineIdx, FromStop, ToStop);
	return true;
}

void FAstraLiftRider::End()
{
	Detach();
	SetWalker(false);
	if (Lifts && SlotIdx != INDEX_NONE)
	{
		Lifts->FreeSlot(LineIdx, SlotIdx);
	}
	SlotIdx = INDEX_NONE;
	if (Active())
	{
		Phase = EStep::None;
	}
}

bool FAstraLiftRider::WalkTo(AActor* A, const FVector& Goal, float Dt, float WalkCmS)
{
	const FVector P = A->GetActorLocation();
	const FVector D = Goal - P;
	const float Dist = (float)D.Size();
	const float Step = FMath::Max(WalkCmS, 30.f) * Dt;
	if (Dist <= Step + StepSlackCm)
	{
		A->SetActorLocation(Goal, false, nullptr, ETeleportType::None);
		return true;
	}
	const FVector N = D / Dist;
	A->SetActorLocation(P + N * Step, false, nullptr, ETeleportType::None);
	if (N.X * N.X + N.Y * N.Y > 0.04f)
	{
		Yaw = FMath::RadiansToDegrees(FMath::Atan2(N.Y, N.X));
	}
	return false;
}

namespace
{
	/** The way through a car's door at a lane across the opening that is nearest a place on the floor: the lane's Y (car frame), the opening's Y +/- its half width less the shoulders. */
	float LiftLane(const FAstraLiftSpec& S, float WantY)
	{
		const FAstraLiftSpec::FOpening* Best = nullptr;
		for (const FAstraLiftSpec::FOpening& O : S.Openings)
		{
			if (!Best || FMath::Abs(O.Y - WantY) < FMath::Abs(Best->Y - WantY))
			{
				Best = &O;
			}
		}
		if (!Best)
		{
			return 0.f;
		}
		const float Reach = FMath::Max(0.f, Best->Width * 0.5f - 38.f);
		return FMath::Clamp(WantY, Best->Y - Reach, Best->Y + Reach);
	}
}

void FAstraLiftRider::ArrangeBoarding(AAstraLiftCar* C)
{
	const FAstraLiftSpec& S = C->Spec();
	const FVector Slot = C->SlotLocal(SlotIdx);
	const float Y = LiftLane(S, Slot.Y);
	Way.Reset();
	Way.Add(FVector(S.D * 0.5f + 45.f, Y, Slot.Z));        // in the lobby, in front of their lane of the doors
	Way.Add(FVector(S.D * 0.5f - 25.f, Y, Slot.Z));        // over the sill: from here the car carries them
	Way.Add(Slot);
	WayAt = 0;
}

void FAstraLiftRider::ArrangeLeaving(AAstraLiftCar* C)
{
	const FAstraLiftSpec& S = C->Spec();
	const FVector Now = C->ToLocal(Body.IsValid() ? Body->GetActorLocation() : C->GetActorLocation());
	const float Z = C->SlotLocal(SlotIdx != INDEX_NONE ? SlotIdx : 0).Z;
	const float Y = LiftLane(S, Now.Y);
	Way.Reset();
	Way.Add(FVector(S.D * 0.5f - 25.f, Y, Z));
	Way.Add(FVector(S.D * 0.5f + 45.f, Y, Z));
	WayAt = 0;
}

FAstraLiftRider::EStep FAstraLiftRider::Tick(float Dt, float WalkCmS)
{
	if (!Active())
	{
		return Phase;
	}
	AActor* A = Body.Get();
	AAstraLiftCar* C = Car();
	if (!A || !Lifts || !C)
	{
		End();
		Phase = EStep::Failed;                               // the lift went away (the network was rebuilt), or the actor did
		return Phase;
	}
	InStep += Dt;
	switch (Phase)
	{
	case EStep::Wait:
	{
		WaitedAt += Dt;
		RecallT += Dt;
		if (RecallT >= RecallEveryS)
		{
			Lifts->RiderCall(LineIdx, FromStop, ToStop);
			RecallT = 0.f;
		}
		if (const AAstraLiftLanding* L = Lifts->LandingOf(LineIdx, FromStop))
		{
			const FVector Here = A->GetActorLocation();
			Yaw = FMath::RadiansToDegrees(FMath::Atan2(L->DoorCm().Y - Here.Y, L->DoorCm().X - Here.X));
		}
		if (Lifts->CanBoard(LineIdx, FromStop, ToStop))
		{
			SlotIdx = Lifts->TakeSlot(LineIdx, Who);
			if (SlotIdx != INDEX_NONE)
			{
				ArrangeBoarding(C);
				SetWalker(true);
				SetStep(EStep::Board);
			}
		}
		else if (WaitedAt > GiveUpWaitS)
		{
			End();
			Phase = EStep::Failed;
		}
		break;
	}
	case EStep::Board:
	{
		if (!bAttached && !Lifts->CanAlight(LineIdx, FromStop))
		{
			// the doors are no longer open at their stop and they are still outside: the car goes without them, and the call is pressed again
			Lifts->FreeSlot(LineIdx, SlotIdx);
			SlotIdx = INDEX_NONE;
			SetWalker(false);
			Lifts->RiderCall(LineIdx, FromStop, ToStop);
			RecallT = 0.f;
			SetStep(EStep::Wait);
			break;
		}
		if (Way.IsValidIndex(WayAt) && WalkTo(A, C->ToWorld(Way[WayAt]), Dt, WalkCmS))
		{
			++WayAt;
		}
		// over the sill the car carries them (their next steps are in the car's frame)
		if (!bAttached && C->ToLocal(A->GetActorLocation()).X < C->Spec().D * 0.5f - 5.f)
		{
			Attach(C);
		}
		if (WayAt >= Way.Num())
		{
			Attach(C);
			SetWalker(false);
			Yaw = FMath::RadiansToDegrees(FMath::Atan2(C->GetActorTransform().TransformVector(FVector::XAxisVector).Y, C->GetActorTransform().TransformVector(FVector::XAxisVector).X));
			Lifts->RiderChoose(LineIdx, ToStop);
			RecallT = 0.f;
			SetStep(EStep::Inside);
		}
		else if (InStep > BoardMaxS)
		{
			End();
			Phase = EStep::Failed;
		}
		break;
	}
	case EStep::Inside:
	{
		RodeFor += Dt;
		RecallT += Dt;
		if (RecallT >= RecallEveryS)
		{
			Lifts->RiderChoose(LineIdx, ToStop);              // (pressed again: a stop that was dropped when the car was full of people is not lost)
			RecallT = 0.f;
		}
		if (Lifts->CanAlight(LineIdx, ToStop))
		{
			ArrangeLeaving(C);
			SetWalker(true);
			SetStep(EStep::Alight);
		}
		else if (RodeFor > InsideMaxS)
		{
			End();
			Phase = EStep::Failed;
		}
		break;
	}
	case EStep::Alight:
	{
		if (bAttached)
		{
			if (!Lifts->CanAlight(LineIdx, ToStop))
			{
				// the doors are closing and they are still in the car: it takes them on, and they press their stop again
				SetWalker(false);
				Lifts->RiderChoose(LineIdx, ToStop);
				RecallT = 0.f;
				SetStep(EStep::Inside);
				break;
			}
			if (Way.IsValidIndex(WayAt) && WalkTo(A, C->ToWorld(Way[WayAt]), Dt, WalkCmS))
			{
				++WayAt;
			}
			if (WayAt >= Way.Num() || C->ToLocal(A->GetActorLocation()).X > C->Spec().D * 0.5f + 12.f)
			{
				Detach();
				if (SlotIdx != INDEX_NONE)
				{
					Lifts->FreeSlot(LineIdx, SlotIdx);
					SlotIdx = INDEX_NONE;
				}
			}
		}
		else if (WalkTo(A, Finish, Dt, WalkCmS))
		{
			SetWalker(false);
			SetStep(EStep::Done);
			break;
		}
		if (InStep > AlightMaxS)
		{
			End();
			Phase = EStep::Failed;
		}
		break;
	}
	default:
		break;
	}
	return Phase;
}
