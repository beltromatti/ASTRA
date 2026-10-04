// ASTRA — ABBORDAGGI: what the squad simulation's events become in the game: the rounds and the wounds seen and heard, the casualties of the roster, the reports of the
// bridge, the breach, the bulkheads cut through, the end of the fight.

#include "AstraBoardSubsystem.h"

#include "ASTRA.h"
#include "AstraCombatFx.h"
#include "AstraCombatant.h"
#include "AstraCrewRoster.h"
#include "AstraLifeSubsystem.h"
#include "AstraShipSubsystem.h"
#include "AstraWeapon.h"
#include "Camera/PlayerCameraManager.h"
#include "Components/PointLightComponent.h"
#include "Components/SceneComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "Kismet/GameplayStatics.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"

using namespace AstraBoard;

namespace
{
	constexpr float BdFxReachCm = 9500.f;          // what the Captain can see and hear of a fight: beyond this nothing is drawn
	const FLinearColor BdMarineTracer(1.f, 0.82f, 0.42f);
	const FLinearColor BdMandateTracer(1.f, 0.16f, 0.1f);
	TAutoConsoleVariable<int32> BdCVarTakeoverFatal(TEXT("astra.board.takeover_fatal"), 1, TEXT("1: when the boarders hold Main Engineering the reactor's containment fails (the abandon-ship chain); 0: the fight just ends"));
}

void UAstraBoardSubsystem::Tell(const FString& Text, bool bReport)
{
	Log.Add(FString::Printf(TEXT("%.0fs: %s"), Since, *Text));
	if (Log.Num() > 40)
	{
		Log.RemoveAt(0, 10);
	}
	UE_LOG(LogASTRA, Log, TEXT("[Board] %s"), *Text);
	if (UAstraShipSubsystem* S = ShipSub())
	{
		S->PublishEvent(FString::Printf(TEXT("boarding: %s"), *Text), bReport);
	}
}

void UAstraBoardSubsystem::OpenBreach()
{
	if (bBreachOpen || !Map.IsValid())
	{
		return;
	}
	bBreachOpen = true;
	const int32 C = Fight.Mission().Breach;
	const FBox& B = Map->GetComps()[C].Box;
	BreachNormal = FVector(0.0, B.Max.Y > 0.0 ? -1.0 : 1.0, 0.0);
	AAstraBoardBreach* Actor = Breaches.Num() ? Breaches[0].Get() : nullptr;
	if (!Actor && GetWorld())
	{
		FActorSpawnParameters P;
		P.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
		Actor = GetWorld()->SpawnActor<AAstraBoardBreach>(BreachAt, FRotator::ZeroRotator, P);
		if (Actor)
		{
			Breaches.Add(Actor);
		}
	}
	if (Actor)
	{
		Actor->Open(BreachAt, BreachNormal);
	}
	if (UAstraCombatFx* X = FxSub())
	{
		X->Impact(BreachAt + FVector(0.0, 0.0, 150.0), BreachNormal, UAstraCombatFx::ESurface::Metal);
		X->PlaySoundAt(TEXT("/Game/ASTRA/Audio/SW_Blast_Inside.SW_Blast_Inside"), BreachAt + FVector(0.0, 0.0, 150.0), 1.f, 1.f);
	}
	Tell(FString::Printf(TEXT("the hull is cut open at %s: boarders are coming through"), *BreachText), true);
}

void UAstraBoardSubsystem::ProcessEvents(float Dt)
{
	TArray<FBoardEvent> Evs;
	Fight.TakeEvents(Evs);
	if (LastShotSound.Num() < Fight.Units().Num())
	{
		LastShotSound.SetNumZeroed(Fight.Units().Num() + 16);
	}
	const bool bObserved = Mode == EMode::Observed || bCaptainAboard;      // the Captain is in the fight (on the Aquila's decks, or on another ship with his marines): rounds, wounds and breaches are seen and heard (else only told)
	const bool bWeAttack = Fight.IsAttacker(ESide::Aquila);
	for (const FBoardEvent& E : Evs)
	{
		switch (E.Type)
		{
		case EEvent::Shot:
			if (bObserved)
			{
				OnShot(E);
			}
			break;
		case EEvent::Hit:
			if (bObserved)
			{
				OnHit(E);
			}
			break;
		case EEvent::Down:
			OnFall(E, false);
			break;
		case EEvent::Died:
			OnFall(E, true);
			break;
		case EEvent::Spawn:
		{
			const FUnit* U = Fight.Unit(E.Unit);
			if (U && U->Side == ESide::Mandate && bObserved && !Assault.bOn)
			{
				OpenBreach();                                  // (a boarding by boats opens each hatch as its boat cuts in: AstraBoardAssault.cpp)
			}
			break;
		}
		case EEvent::Contact:
		{
			const FUnit* Seer = Fight.Unit(E.Unit);
			const FUnit* Seen = Fight.Unit(E.Target);
			if (!bToldContact && Seer && Seen && Seer->Side == ESide::Aquila && Seen->Side == ESide::Mandate)
			{
				bToldContact = true;
				Tell(FString::Printf(TEXT("contact: %s sees %s at %s"), *Seer->Name, bWeAttack ? TEXT("the ship's defenders") : TEXT("the boarders"), *PlaceOf(*Seen)), true);
			}
			break;
		}
		case EEvent::Retreat:
		{
			const FUnit* U = Fight.Unit(E.Unit);
			if (U && (U->Side == ESide::Mandate || bWeAttack))
			{
				Tell(FString::Printf(TEXT("%s is breaking off and falling back to the breach"), *E.Text), false);
			}
			break;
		}
		case EEvent::Rescue:
			Tell(TEXT("the marines have reached the Captain and are covering him"), false);
			break;
		case EEvent::Reload:
			break;
		case EEvent::Order:
		{
			const FUnit* U = Fight.Unit(E.Unit);
			if (!U || U->Side == ESide::Aquila)
			{
				Log.Add(FString::Printf(TEXT("%.0fs: %s"), Since, *E.Text));
			}
			break;
		}
		case EEvent::Cut:
		{
			// the boarders cut through a pressure bulkhead: it opens (the game's door and the damage model's seal), with a shower of sparks
			const int32 Door = E.Target;
			if (Dmg.IsValid() && Dmg->Doors.IsValidIndex(Door))
			{
				SealDoor(Door, false);
			}
			if (UAstraCombatFx* X = bObserved ? FxSub() : nullptr)
			{
				X->Impact(E.Start + FVector(0.0, 0.0, 110.0), FVector(0.0, 0.0, 1.0), UAstraCombatFx::ESurface::Metal);
				X->PlaySoundAt(TEXT("/Game/ASTRA/Audio/SW_Sparks.SW_Sparks"), E.Start + FVector(0.0, 0.0, 110.0), 1.f, 0.9f);
			}
			Tell(E.Text, true);
			break;
		}
		case EEvent::Carried:
		{
			// a wounded man has been carried out to his boat: alive, off the ship (his bearer has gone back to the fight)
			const FUnit* U = Fight.Unit(E.Unit);
			const FUnit* Bearer = Fight.Unit(E.Target);
			if (U && U->Side == ESide::Aquila)
			{
				if (const int32* R = RosterOfUnit.Find(E.Unit))
				{
					UAstraShipSubsystem* S = ShipSub();
					if (S && !HarmTold.Contains(*R))
					{
						HarmTold.Add(*R);
						S->HarmPerson(*R, false, TEXT("gunfire"));
					}
				}
				Tell(FString::Printf(TEXT("%s, wounded, has been carried back to the boat by %s"), *U->Name, Bearer ? *Bearer->Name : TEXT("his comrades")), false);
			}
			ReleaseBody(E.Unit);
			break;
		}
		case EEvent::Exit:
		case EEvent::Outcome:
		default:
			break;
		}
	}
	// the casualties, told every little while when they have moved
	CasualtyT += Dt;
	if (CasualtyT > 14.f)
	{
		CasualtyT = 0.f;
		const FBook& B = Fight.Book();
		const int32 Lost = B.Killed[0] + B.Down[0], Hostile = B.Killed[1] + B.Down[1];
		if (Lost != ToldMarinesLost || Hostile != ToldMandateLost)
		{
			ToldMarinesLost = Lost;
			ToldMandateLost = Hostile;
			Tell(FString::Printf(TEXT("marines: %d dead, %d down; %s: %d dead or down, %d still fighting"), B.Killed[0], B.Down[0], bWeAttack ? TEXT("her crew") : TEXT("boarders"), Hostile,
			                     Fight.CountAble(ESide::Mandate)), false);
		}
	}
}

void UAstraBoardSubsystem::OnShot(const FBoardEvent& E)
{
	UAstraCombatFx* X = FxSub();
	const FUnit* Shooter = Fight.Unit(E.Unit);
	UWorld* W = GetWorld();
	const APlayerCameraManager* Cam = W ? UGameplayStatics::GetPlayerCameraManager(W, 0) : nullptr;
	if (!X || !Shooter || !Cam)
	{
		return;
	}
	const FVector Eye = Cam->GetCameraLocation();
	const FVector Off = WorldOffset();
	const FVector At = Shooter->Pos + Off;
	if (FVector::Dist(At, Eye) > BdFxReachCm || FMath::Abs(At.Z - Eye.Z) > 800.f)
	{
		return;                                       // out of sight and out of hearing
	}
	AAstraCombatant* B = BodyOf.FindRef(E.Unit);
	const FVector Muzzle = B ? B->MuzzleAt() : E.Start + Off;
	const FVector End = E.End + Off;
	const FVector Dir = (End - Muzzle).GetSafeNormal();
	X->Tracer(Muzzle, End, Shooter->Side == ESide::Mandate ? BdMandateTracer : BdMarineTracer);
	X->MuzzleFlash(Muzzle, Dir, B ? 1.f : 0.7f);
	X->Whiz(Muzzle, End);
	if (B)
	{
		B->NoteShot();
	}
	// a sound a burst, not a sound a round (the sim's rounds come at nine a second a man): at most one a unit every ninth of a second, and a budget for the room
	if (LastShotSound.IsValidIndex(E.Unit) && GetWorld()->GetTimeSeconds() - LastShotSound[E.Unit] > 0.11 && SoundBudget >= 1.f)
	{
		LastShotSound[E.Unit] = GetWorld()->GetTimeSeconds();
		SoundBudget -= 1.f;
		X->PlaySoundAt(AstraWeapons::Get(EAstraWeapon::Rifle).ShotSound, Muzzle, Shooter->Side == ESide::Mandate ? 0.95f : 0.85f, FMath::FRandRange(0.94f, 1.08f));
	}
	// a round that missed: where it struck (a wall, a bulkhead, a console), found with a real trace
	if (!E.bHit && TracesLeft > 0)
	{
		--TracesLeft;
		FHitResult H;
		FCollisionQueryParams Q(SCENE_QUERY_STAT(AstraBoardMiss), false);
		if (W->LineTraceSingleByChannel(H, Muzzle, End + Dir * 400.f, ECC_Camera, Q))
		{
			X->Impact(H.Location, H.ImpactNormal, UAstraCombatFx::ESurface::Metal);
		}
		else if (FVector::Dist(End, Muzzle) < 6000.0)
		{
			X->Impact(End, -Dir, UAstraCombatFx::ESurface::Metal);
		}
	}
}

void UAstraBoardSubsystem::OnHit(const FBoardEvent& E)
{
	const FUnit* Victim = Fight.Unit(E.Unit);
	if (!Victim)
	{
		return;
	}
	if (Victim->bExternal)
	{
		OnCaptainHit(E);
		return;
	}
	const FUnit* Shooter = Fight.Unit(E.Target);
	const FVector Off = WorldOffset();
	if (AAstraCombatant* B = BodyOf.FindRef(E.Unit))
	{
		B->NoteHit(Shooter ? Shooter->Pos + Off : E.End + Off);
	}
	if (UAstraCombatFx* X = FxSub())
	{
		const APlayerCameraManager* Cam = GetWorld() ? UGameplayStatics::GetPlayerCameraManager(GetWorld(), 0) : nullptr;
		if (Cam && FVector::Dist(E.End + Off, Cam->GetCameraLocation()) < BdFxReachCm)
		{
			const FVector N = Shooter ? (Shooter->Pos - E.End).GetSafeNormal() : FVector::UpVector;
			X->Impact(E.End + Off, N, UAstraCombatFx::ESurface::Flesh);
		}
	}
}

void UAstraBoardSubsystem::OnFall(const FBoardEvent& E, bool bDied)
{
	const FUnit* U = Fight.Unit(E.Unit);
	if (!U || U->bExternal)
	{
		return;
	}
	UAstraShipSubsystem* S = ShipSub();
	const int32* R = RosterOfUnit.Find(E.Unit);
	if (U->Side == ESide::Aquila && R)
	{
		if (bDied)
		{
			if (S && !HarmTold.Contains(*R))
			{
				HarmTold.Add(*R);
				S->HarmPerson(*R, true, TEXT("gunfire"));
			}
			Tell(FString::Printf(TEXT("%s is dead at %s%s%s"), *U->Name, *PlaceOf(*U), U->FellTo.IsEmpty() ? TEXT("") : TEXT(", killed by "), *U->FellTo), true);
		}
		else if (!ToldDown.Contains(E.Unit))
		{
			ToldDown.Add(E.Unit);
			Tell(FString::Printf(TEXT("%s is down, wounded, at %s"), *U->Name, *PlaceOf(*U)), false);
		}
	}
}

void UAstraBoardSubsystem::OnOutcome()
{
	const FMission& M = Fight.Mission();
	const FBook& B = Fight.Book();
	const FString Tally = FString::Printf(TEXT("marines: %d dead, %d wounded; boarders: %d dead, %d wounded, %d got away"), B.Killed[0], B.Down[0] + B.Carried[0], B.Killed[1], B.Down[1] + B.Carried[1], B.Exited[1]);
	switch (M.Outcome)
	{
	case EOutcome::DefenderHolds:
		Tell(FString::Printf(TEXT("the boarders are beaten: Main Engineering is secure and the deck is ours. %s"), *Tally), true);
		break;
	case EOutcome::AttackerRepelled:
		Tell(FString::Printf(TEXT("the boarders have broken off and gone back through the breach; the deck is ours. %s"), *Tally), true);
		break;
	case EOutcome::AttackerTakes:
		bToldTakeover = true;
		if (BdCVarTakeoverFatal.GetValueOnGameThread() != 0)
		{
			Tell(FString::Printf(TEXT("the boarders hold Main Engineering and are working on the reactor: its containment will fail in about half a minute. %s"), *Tally), true);
			TakeoverFuse = 28.f;
		}
		else
		{
			Tell(FString::Printf(TEXT("the boarders hold Main Engineering. %s"), *Tally), true);
		}
		break;
	case EOutcome::TimedOut:
		Tell(FString::Printf(TEXT("the fight has gone quiet: the boarders are pinned down short of Main Engineering. %s"), *Tally), true);
		break;
	default:
		break;
	}
	Finish(TEXT("the fight is decided"));
}

// ================================================================================================================== the breach

AAstraBoardBreach::AAstraBoardBreach()
{
	PrimaryActorTick.bCanEverTick = true;
	SetRootComponent(CreateDefaultSubobject<USceneComponent>(TEXT("Root")));
	SetActorTickEnabled(false);
}

void AAstraBoardBreach::Build()
{
	if (Ring.Num())
	{
		return;
	}
	LineMesh = LoadObject<UStaticMesh>(nullptr, TEXT("/Game/ASTRA/Holo/SM_HOLO_Line.SM_HOLO_Line"));
	GlowMat = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/ASTRA/Materials/M_FX_Glow.M_FX_Glow"));
	if (LineMesh && GlowMat)
	{
		for (int32 i = 0; i < 14; ++i)
		{
			UStaticMeshComponent* C = NewObject<UStaticMeshComponent>(this);
			C->SetupAttachment(GetRootComponent());
			C->SetMobility(EComponentMobility::Movable);
			C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
			C->SetCastShadow(false);
			C->RegisterComponent();
			C->SetStaticMesh(LineMesh);
			RingMIDs.Add(C->CreateDynamicMaterialInstance(0, GlowMat));
			Ring.Add(C);
		}
	}
	Glow = NewObject<UPointLightComponent>(this);
	Glow->SetupAttachment(GetRootComponent());
	Glow->RegisterComponent();
	Glow->SetMobility(EComponentMobility::Movable);
	Glow->SetIntensityUnits(ELightUnits::Lumens);
	Glow->SetIntensity(0.f);
	Glow->SetLightColor(FLinearColor(1.f, 0.38f, 0.14f));
	Glow->SetAttenuationRadius(900.f);
	Glow->SetCastShadows(false);
	Glow->SetVisibility(false);
}

void AAstraBoardBreach::Open(const FVector& At, const FVector& IntoRoom)
{
	Build();
	Centre = At + FVector(0.f, 0.f, 135.f);
	Normal = IntoRoom.GetSafeNormal();
	SetActorLocation(Centre);
	bOpen = true;
	Age = 0.f;
	SetActorTickEnabled(true);
	if (Glow)
	{
		Glow->SetVisibility(true);
		Glow->SetWorldLocation(Centre + Normal * 60.f);
	}
	// the cut: a ring in the wall, 2.2 m across and about as high (a circle on the wall's plane)
	const FVector Up = FVector::UpVector;
	const FVector Along = FVector::CrossProduct(Normal, Up).GetSafeNormal();
	const int32 N = Ring.Num();
	for (int32 i = 0; i < N; ++i)
	{
		const float A0 = 2.f * PI * i / N, A1 = 2.f * PI * (i + 1) / N;
		const float R = 105.f;
		const FVector P0 = Centre + Along * FMath::Cos(A0) * R + Up * FMath::Sin(A0) * R;
		const FVector P1 = Centre + Along * FMath::Cos(A1) * R + Up * FMath::Sin(A1) * R;
		const FVector D = (P1 - P0);
		const float Len = (float)D.Size();
		Ring[i]->SetWorldLocationAndRotation(P0, D.Rotation());
		Ring[i]->SetWorldScale3D(FVector(Len / 100.f * 1.05f, 1.6f, 1.6f));
		Ring[i]->SetVisibility(true);
	}
}

void AAstraBoardBreach::Close()
{
	bOpen = false;
	for (UStaticMeshComponent* C : Ring)
	{
		if (C)
		{
			C->SetVisibility(false);
		}
	}
	if (Glow)
	{
		Glow->SetIntensity(0.f);
		Glow->SetVisibility(false);
	}
	SetActorTickEnabled(false);
}

void AAstraBoardBreach::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	if (!bOpen)
	{
		return;
	}
	Age += DeltaSeconds;
	// the cut cools from white to a dull red, and the light of it flickers
	const float Heat = FMath::Clamp(1.f - Age / 70.f, 0.15f, 1.f);
	const FLinearColor Col = FMath::Lerp(FLinearColor(0.9f, 0.1f, 0.03f), FLinearColor(1.f, 0.78f, 0.45f), Heat);
	for (int32 i = 0; i < RingMIDs.Num(); ++i)
	{
		if (RingMIDs[i])
		{
			RingMIDs[i]->SetVectorParameterValue(TEXT("Color"), Col);
			RingMIDs[i]->SetScalarParameterValue(TEXT("Intensity"), 160.f * Heat * FMath::FRandRange(0.8f, 1.15f) + 12.f);
		}
	}
	if (Glow)
	{
		Glow->SetIntensity(5200.f * Heat * FMath::FRandRange(0.7f, 1.1f) + 300.f);
	}
}
