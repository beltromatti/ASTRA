// ASTRA — ABBORDAGGI-2: the Captain goes along (docs/brief/ABBORDAGGI-2.md §5, docs/ABBORDAGGI.md §13).
//
// He rides in the first Kestrel with his marines:
//   Out     the boat is out: the screen goes dark, he is in its troop bay (a small room of its own, a red lamp, the engines' note) with a line that says how long to the hull; he looks about, he does
//           not walk. If the boat is shot down he is in it.
//   Aboard  the boat has cut in: he stands in the boarding lock of the other ship, rifle in his hands, his marines about him; her decks are made solid round him a few rooms at a time (the plan is her
//           class's; AstraBoardInterior.*) in a zone of the world of their own, the simulation's rooms and doors are the walls he walks between, her bodies and rounds are seen and heard as on the
//           Aquila's decks. The stairs and lifts take him from deck to deck when he stands on their lit pad a moment. If he falls and the ship's chain carries him out he wakes in the Medbay and the
//           decks round him go; if he is lost it is the end the ship already knows.
//   Home    the fight is over (or called off): the decks go, he is in the troop bay again for the flight home, and in the boat bay on Deck 8 when the boat is home.
// Nothing here is a filter on what the minds say: the game moves him and shows him the facts.

#include "AstraBoardSubsystem.h"

#include "ASTRA.h"
#include "ASTRACharacter.h"
#include "AstraBattleSubsystem.h"
#include "AstraBoardInterior.h"
#include "AstraCombatant.h"
#include "AstraDeckStreaming.h"
#include "AstraFpsComponent.h"
#include "AstraLifeSubsystem.h"
#include "AstraShipSubsystem.h"
#include "Camera/PlayerCameraManager.h"
#include "Components/CapsuleComponent.h"
#include "Engine/World.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "HAL/IConsoleManager.h"
#include "Kismet/GameplayStatics.h"

using namespace AstraBoard;
using AstraBoardCraft::FShipFacts;

namespace
{
	constexpr float RdFadeS = 0.9f;
	constexpr float RdHomeLimitS = 420.f;                // a boat that does not come home in this time brings him back all the same
}

void UAstraBoardSubsystem::SetTestCaptain(bool bOn, const FVector& Feet, float Yaw)
{
	bTestCaptain = bOn;
	TestFeet = Feet;
	TestYaw = Yaw;
}

FString UAstraBoardSubsystem::CaptainWhereText() const
{
	const FLeg* L = Assault.Legs.IsValidIndex(RideLeg) ? &Assault.Legs[RideLeg] : nullptr;
	const FString Boat = L && !L->CraftName.IsEmpty() ? L->CraftName : FString(TEXT("a Kestrel"));
	switch (Ride)
	{
	case ERide::Out:
	{
		const int32 Eta = FMath::Max(0, FMath::RoundToInt(Assault.EtaS - (Assault.T - Assault.LaunchT)));
		return FString::Printf(TEXT("away from the ship with the marines, in the troop bay of %s, flying to %s (the hull in about %d s); the XO has the conn of the Aquila and the Captain speaks to the bridge over his comm"),
		                       *Boat, *Assault.TargetName, Eta);
	}
	case ERide::Aboard:
	{
		FString Room = TEXT("her boarding lock");
		if (Map.IsValid() && Fight.CaptainId() != INDEX_NONE)
		{
			if (const FUnit* C = Fight.Unit(Fight.CaptainId()))
			{
				Room = Map->Describe(C->Comp);
			}
		}
		return FString::Printf(TEXT("aboard %s with the marines, in %s, in the fight for %s: the Marine Detachment fights round him and Major Reyes has the net; the XO has the conn of the Aquila and the Captain speaks to the bridge over his comm"),
		                       *Assault.TargetName, *Room, Map.IsValid() ? *Map->Describe(Fight.Mission().Objective) : TEXT("her command deck"));
	}
	case ERide::Home:
		return FString::Printf(TEXT("away from the ship, in the troop bay of %s, coming home from %s; the XO has the conn of the Aquila and the Captain speaks to the bridge over his comm"), *Boat, *Assault.TargetName);
	default:
		return FString();
	}
}

APawn* UAstraBoardSubsystem::CaptainPawn() const
{
	APlayerController* PC = GetWorld() ? UGameplayStatics::GetPlayerController(GetWorld(), 0) : nullptr;
	return PC ? PC->GetPawn() : nullptr;
}

bool UAstraBoardSubsystem::CaptainOnFoot() const
{
	if (bTestCaptain)
	{
		return true;
	}
	const ACharacter* Walker = Cast<ACharacter>(CaptainPawn());
	if (!Walker)
	{
		return false;                                    // in a Falcon, in a pod
	}
	const UAstraShipSubsystem* S = ShipSub();
	return !S || (!S->IsPlanetside() && !S->IsAbandoning() && S->GetCaptainFate() == 0);
}

void UAstraBoardSubsystem::TeleportCaptain(const FVector& FeetWorld, float Yaw, bool bFloat)
{
	if (bTestCaptain)
	{
		TestFeet = FeetWorld;
		TestYaw = Yaw;
		return;
	}
	APlayerController* PC = GetWorld() ? UGameplayStatics::GetPlayerController(GetWorld(), 0) : nullptr;
	ACharacter* Ch = PC ? Cast<ACharacter>(PC->GetPawn()) : nullptr;
	if (!Ch || !Ch->GetCapsuleComponent())
	{
		return;
	}
	const float Half = Ch->GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
	Ch->SetActorLocation(FeetWorld + FVector(0.0, 0.0, Half + 4.0), false, nullptr, ETeleportType::TeleportPhysics);
	if (UCharacterMovementComponent* M = Ch->GetCharacterMovement())
	{
		M->StopMovementImmediately();
		M->SetMovementMode(bFloat ? MOVE_Flying : MOVE_Walking);
	}
	PC->SetControlRotation(FRotator(0.f, Yaw, 0.f));
}

void UAstraBoardSubsystem::FadeCaptain(bool bToBlack, float Seconds)
{
	APlayerController* PC = GetWorld() ? UGameplayStatics::GetPlayerController(GetWorld(), 0) : nullptr;
	APlayerCameraManager* Cam = PC ? PC->PlayerCameraManager.Get() : nullptr;
	if (!Cam || bTestCaptain)
	{
		return;
	}
	Cam->StartCameraFade(bToBlack ? 0.f : 1.f, bToBlack ? 1.f : 0.f, Seconds, FLinearColor::Black, false, bToBlack);
}

void UAstraBoardSubsystem::LockCaptain(bool bMove, bool bLook)
{
	APlayerController* PC = GetWorld() ? UGameplayStatics::GetPlayerController(GetWorld(), 0) : nullptr;
	if (!PC || bTestCaptain)
	{
		return;
	}
	if (bMove != bMoveLocked)
	{
		if (bMove)
		{
			PC->SetIgnoreMoveInput(true);
		}
		else
		{
			PC->ResetIgnoreMoveInput();
		}
		bMoveLocked = bMove;
	}
	if (bLook != bLookLocked)
	{
		if (bLook)
		{
			PC->SetIgnoreLookInput(true);
		}
		else
		{
			PC->ResetIgnoreLookInput();
		}
		bLookLocked = bLook;
	}
}

void UAstraBoardSubsystem::CaptainPrompt(const FString& Text, float Seconds)
{
	if (APawn* P = CaptainPawn())
	{
		if (UAstraFpsComponent* F = P->FindComponentByClass<UAstraFpsComponent>())
		{
			F->Prompt(Text, Seconds);
		}
	}
}

void UAstraBoardSubsystem::MakeCabin()
{
	UWorld* W = GetWorld();
	if (!W)
	{
		return;
	}
	if (!Cabin)
	{
		FActorSpawnParameters P;
		P.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
		Cabin = W->SpawnActor<AAstraBoardInterior>(FVector::ZeroVector, FRotator::ZeroRotator, P);
	}
	if (Cabin)
	{
		CabinSpot = Cabin->BuildCabin();
	}
}

bool UAstraBoardSubsystem::EnsureEnemyDecks(const FVector& NearPlanCm, int32 MaxRooms)
{
	UWorld* W = GetWorld();
	if (!W || !ScenePlan.IsValid())
	{
		return false;
	}
	if (!Interior)
	{
		FActorSpawnParameters P;
		P.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
		Interior = W->SpawnActor<AAstraBoardInterior>(FVector::ZeroVector, FRotator::ZeroRotator, P);
	}
	if (!Interior)
	{
		return false;
	}
	RemoteOffset = AAstraBoardInterior::ZoneOrigin();
	if (!Interior->IsBegun())
	{
		FShipFacts T;
		const UAstraBattleSubsystem* B = Battle();
		bool bHulk = !B || !B->ShipFacts(Assault.TargetId, T) || T.bDisabled;
		if (Assault.bFromWar && ScenePlan->Dmg.IsValid())
		{
			// the war's picture of her rooms: the strips of the rooms with no power are the red of the emergency lighting, and the whole is lit as the ship is (more than half her rooms dark: a hulk)
			int32 Dark = 0;
			for (const TPair<int32, FBoardRoomMood>& KV : Assault.Moods)
			{
				Dark += KV.Value.Dark() ? 1 : 0;
			}
			bHulk = Dark * 2 > ScenePlan->Dmg->Comps.Num();
		}
		Interior->Begin(ScenePlan, RemoteOffset, bHulk ? EAstraInteriorStyle::Emergency : EAstraInteriorStyle::Lit, Assault.bFromWar ? &Assault.Moods : nullptr, Assault.bFromWar ? &Assault.Fallen : nullptr);
	}
	Interior->EnsureAround(NearPlanCm, MaxRooms);
	return true;
}

void UAstraBoardSubsystem::EndEnemyDecks()
{
	if (Interior)
	{
		Interior->End();
	}
}

FVector UAstraBoardSubsystem::HomeSpot() const
{
	// the boat bay of Deck 8 (feet on its floor): where the Kestrels set him down
	if (AqDmg.IsValid() && AqMap.IsValid())
	{
		if (const int32* C = AqDmg->CompByName.Find(FName(TEXT("d8_shuttle_bay_B1"))))
		{
			return AqMap->CentreOf(*C);
		}
	}
	return FVector::ZeroVector;
}

// ================================================================================================================== the ride

void UAstraBoardSubsystem::RideBegin(FLeg& L)
{
	if (Ride != ERide::None)
	{
		return;
	}
	Ride = ERide::Out;
	RideT = 0.f;
	RideStep = 0;
	RideLeg = L.Index;
	RidePromptT = 0.f;
	// a rifle for the fight (the boat's locker) if he has none, and the screen goes dark
	if (APawn* P = CaptainPawn())
	{
		if (UAstraFpsComponent* F = P->FindComponentByClass<UAstraFpsComponent>())
		{
			if (!F->Carries(EAstraWeapon::Rifle))
			{
				F->SetKit(true);
			}
		}
	}
	LockCaptain(true, false);
	FadeCaptain(true, RdFadeS);
	Tell(FString::Printf(TEXT("the Captain rides with the marines in %s"), L.CraftName.IsEmpty() ? TEXT("the first Kestrel") : *L.CraftName), false);
}

void UAstraBoardSubsystem::RideArrive(FLeg& L)
{
	if (Ride != ERide::Out || RideLeg != L.Index)
	{
		return;
	}
	RideStep = 20;                                       // (the boat has cut in: a quick fade, then the other ship's decks)
	RideT = 0.f;
	FadeCaptain(true, 0.6f);
}

void UAstraBoardSubsystem::CaptainLostInBoat(const FString& Cause)
{
	Ride = ERide::None;
	LockCaptain(false, false);
	if (Cabin)
	{
		Cabin->End();
	}
	if (UAstraShipSubsystem* S = ShipSub())
	{
		S->GetInterior().CaptainDied(FString::Printf(TEXT("lost with the Kestrel: %s"), *Cause));
	}
	Tell(FString::Printf(TEXT("the Captain was in the boat: it was destroyed (%s)"), *Cause), true);
}

void UAstraBoardSubsystem::CaptainLeftScene(const TCHAR* Why)
{
	if (!bCaptainAboard)
	{
		return;
	}
	bCaptainAboard = false;
	bBeamed = false;
	bCaptainInBeam = false;
	Fight.SetCaptain(FVector(0.0, 0.0, -1.0e7), 0.f, false, 0.f, false);          // (out of the fight: the simulation has no one of his there)
	EndEnemyDecks();
	Ride = ERide::None;
	LockCaptain(false, false);
	bCapDown = false;
	bChainDown = false;
	for (const auto& KV : BodyOf)
	{
		if (KV.Value)
		{
			KV.Value->SetWorldOffset(FVector::ZeroVector);
		}
	}
	ClearBodies();
	Tell(FString::Printf(TEXT("the Captain is off the other ship's decks (%s): the marines fight on without him"), Why), false);
}

void UAstraBoardSubsystem::RideHome(const TCHAR* Why)
{
	if (Ride != ERide::Aboard)
	{
		return;
	}
	Tell(FString::Printf(TEXT("the Captain is called back to the boat (%s)"), Why), false);
	Ride = ERide::Home;
	RideT = 0.f;
	RideStep = 30;
	FadeCaptain(true, RdFadeS);
	LockCaptain(true, true);
}

void UAstraBoardSubsystem::RideLanded()
{
	if (Ride == ERide::None)
	{
		return;
	}
	Ride = ERide::Home;
	RideStep = 40;                                       // (home: dark, then the boat bay)
	RideT = 0.f;
	FadeCaptain(true, 0.6f);
	LockCaptain(true, true);
}

void UAstraBoardSubsystem::TickRide(float Dt)
{
	if (Ride == ERide::None)
	{
		return;
	}
	RideT += Dt;
	FLeg* Leg = LegOf(RideLeg);
	// the assault is gone (closed, the world torn down): he is where he is; the ride ends
	if (!Assault.bOn && Ride != ERide::Aboard && RideStep < 40)
	{
		Ride = ERide::Home;
		RideStep = 40;
		RideT = 0.f;
		FadeCaptain(true, 0.4f);
		LockCaptain(true, true);
	}
	switch (Ride)
	{
	case ERide::Out:
	{
		if (RideStep == 0 && RideT >= RdFadeS + 0.2f)
		{
			MakeCabin();
			TeleportCaptain(CabinSpot, 0.f, false);
			LockCaptain(true, false);
			FadeCaptain(false, RdFadeS);
			RideStep = 1;
		}
		else if (RideStep >= 1 && RideStep < 20)
		{
			RidePromptT -= Dt;
			if (RidePromptT <= 0.f && Leg)
			{
				RidePromptT = 1.f;
				const float Eta = FMath::Max(0.f, Assault.EtaS - (Assault.T - Assault.LaunchT));
				CaptainPrompt(FString::Printf(TEXT("%s  ·  %d MARINES  ·  %s"), *Leg->CraftName.ToUpper(), Leg->Men, Eta > 1.f ? *FString::Printf(TEXT("THE HULL IN %d:%02d"), (int32)Eta / 60, (int32)Eta % 60) : TEXT("CLOSING ON THE HATCH")), 1.4f);
			}
		}
		else if (RideStep == 20 && RideT >= 0.7f)
		{
			// the boat has cut in: the other ship's decks, made solid round the lock he comes out of
			if (!Leg || Mode != EMode::Remote || !ScenePlan.IsValid() || Phase != EPhase::Active)
			{
				Ride = ERide::Home;                        // (the fight is not there to go into: he stays in the troop bay for the flight home)
				RideStep = 31;
				RideT = 0.f;
				FadeCaptain(false, 0.5f);
				break;
			}
			if (!EnsureEnemyDecks(Leg->InCm, 60))
			{
				Ride = ERide::Home;
				RideStep = 31;
				RideT = 0.f;
				FadeCaptain(false, 0.5f);
				break;
			}
			if (Cabin)
			{
				Cabin->End();
			}
			if (Fight.CaptainId() == INDEX_NONE)
			{
				Fight.AddCaptain(Leg->InCm);
			}
			bCaptainAboard = true;
			bCapDown = false;
			bChainDown = false;
			MakeSightOverride();
			const float Yaw = FMath::RadiansToDegrees(FMath::Atan2(Leg->Into.Y, Leg->Into.X));
			TeleportCaptain(Leg->InCm + RemoteOffset, Yaw, true);
			FadeCaptain(false, 1.1f);
			Ride = ERide::Aboard;
			RideT = 0.f;
			RideStep = 0;
			bPadArmed = false;
			PadDwellS = 0.f;
			bHomeHintShown = false;
			Tell(FString::Printf(TEXT("the Captain is aboard %s with the marines, in %s: going for %s"), *Assault.TargetName, *Leg->PlaceText, *Map->Describe(Fight.Mission().Objective)), true);
			CaptainPrompt(FString::Printf(TEXT("ABOARD %s  ·  %s"), *Assault.TargetName.ToUpper(), *Map->Describe(Fight.Mission().Objective).ToUpper()), 6.f);
		}
		break;
	}
	case ERide::Aboard:
		TickAboard(Dt);
		break;
	case ERide::Home:
	{
		if (RideStep == 30 && RideT >= RdFadeS + 0.15f)
		{
			// the decks go; the troop bay again
			bCaptainAboard = false;
			bBeamed = false;
			Fight.SetCaptain(FVector(0.0, 0.0, -1.0e7), 0.f, false, 0.f, false);
			ClearBodies();
			EndEnemyDecks();
			MakeCabin();
			TeleportCaptain(CabinSpot, 0.f, false);
			LockCaptain(true, false);
			FadeCaptain(false, RdFadeS);
			RideStep = 31;
			RideT = 0.f;
		}
		else if (RideStep == 31)
		{
			RidePromptT -= Dt;
			if (RidePromptT <= 0.f)
			{
				RidePromptT = 1.f;
				CaptainPrompt(Leg && Leg->State == FLeg::EState::Home ? TEXT("HOME") : TEXT("THE KESTREL IS TAKING YOU HOME"), 1.4f);
				if (UAstraDeckStreaming* DS = GetWorld() ? GetWorld()->GetSubsystem<UAstraDeckStreaming>() : nullptr)
				{
					DS->RequestAt(HomeSpot(), 60.f);                   // (the deck of the bay may have been let go while he was away: it loads while the boat flies)
				}
			}
			if (RideT > RdHomeLimitS || (Leg && Leg->State == FLeg::EState::Home))
			{
				RideLanded();
			}
		}
		else if (RideStep == 40 && RideT >= 0.7f)
		{
			// the boat bay of Deck 8
			const FVector Bay = HomeSpot();
			if (UAstraDeckStreaming* DS = GetWorld() ? GetWorld()->GetSubsystem<UAstraDeckStreaming>() : nullptr; DS && !bTestCaptain && !DS->IsReadyAt(Bay + FVector(0.0, 0.0, 100.0)))
			{
				// the screen is dark and the deck is not in the world yet: he waits for it in the troop bay (a few seconds), then it is loaded at once; he is not set down over a floor that is not there
				DS->RequestAt(Bay, 90.f);
				if (RideT < 0.7f + 6.f)
				{
					break;
				}
				DS->ForceReadyAt(Bay);
			}
			if (Cabin)
			{
				Cabin->End();
			}
			EndEnemyDecks();
			bCaptainAboard = false;
			TeleportCaptain(Bay, 90.f, false);
			LockCaptain(false, false);
			FadeCaptain(false, RdFadeS);
			CaptainPrompt(TEXT("BACK ABOARD THE AQUILA  ·  THE BOAT BAY, DECK 8"), 5.f);
			Tell(TEXT("the Captain is back aboard the Aquila: the boat bay on Deck 8"), false);
			Ride = ERide::None;
			RideStep = 0;
		}
		break;
	}
	default:
		break;
	}
}

void UAstraBoardSubsystem::TickAboard(float Dt)
{
	if (Phase != EPhase::Active || Mode != EMode::Remote)
	{
		RideHome(TEXT("the fight is over"));
		return;
	}
	if (!bCaptainIn)
	{
		if (bCaptainInBeam)
		{
			return;                                      // (his pattern is in the transporter's buffer: out of the fight; the decks stay until it is set down)
		}
		// the ship's own chain carried him out (the Medbay) or the world has him elsewhere: the decks round him go
		CaptainLeftScene(TEXT("carried out"));
		return;
	}
	if (!bHomeHintShown && RideT > 7.f)
	{
		bHomeHintShown = true;                           // (the first thing he reads is where he is; then how he gets out)
		CaptainPrompt(TEXT("TO COME HOME: ASK THE CHIEF TO BEAM YOU UP, OR TELL THE XO TO CALL OFF THE BOARDING  ·  THE BOAT WAITS AT THE HATCH"), 7.f);
	}
	if (RideT > 0.6f && RideStep == 0)
	{
		RideStep = 1;
		LockCaptain(false, false);
		if (APawn* P = CaptainPawn())
		{
			if (ACharacter* Ch = Cast<ACharacter>(P))
			{
				if (UCharacterMovementComponent* M = Ch->GetCharacterMovement())
				{
					M->SetMovementMode(MOVE_Walking);
				}
			}
		}
	}
	FVector Feet;
	float Yaw = 0.f, Speed = 0.f;
	bool bLow = false;
	if (!CaptainFeet(Feet, Yaw, bLow, Speed) || !Interior)
	{
		return;
	}
	const FVector FeetPlan = Feet - RemoteOffset;
	// the lamp and the lights follow his eye
	{
		const APlayerCameraManager* Cam = GetWorld() ? UGameplayStatics::GetPlayerCameraManager(GetWorld(), 0) : nullptr;
		if (Cam)
		{
			Interior->Follow(Cam->GetCameraLocation(), Cam->GetActorForwardVector());
		}
	}
	RideProbeT -= Dt;
	if (RideProbeT <= 0.f)
	{
		RideProbeT = 0.25f;
		Interior->EnsureAround(FeetPlan, 4);
		TSet<int32> Shut;
		for (const FBoardPortal& P : Map->GetPortals())
		{
			if (P.Kind == FBoardPortal::EKind::Blast && Fight.IsDoorSealed(P.Door))
			{
				Shut.Add(P.Door);
			}
		}
		Interior->SetShut(Shut);
	}
	// stairs and lifts: a moment on the lit pad takes him to the other deck
	FVector To;
	FString Text;
	const int32 Pad = Interior->PadNear(FeetPlan, 110.f, To, Text);
	if (Pad == INDEX_NONE)
	{
		bPadArmed = true;
		PadDwellS = 0.f;
		return;
	}
	if (!bPadArmed)
	{
		return;
	}
	PadDwellS += Dt;
	CaptainPrompt(Text + TEXT("  —  STAND ON THE PAD"), 0.3f);
	if (PadDwellS > 1.1f)
	{
		PadDwellS = 0.f;
		bPadArmed = false;
		Interior->EnsureAround(To, 14);
		float Y = bTestCaptain ? TestYaw : 0.f;
		if (const APlayerController* PC = bTestCaptain || !GetWorld() ? nullptr : UGameplayStatics::GetPlayerController(GetWorld(), 0))
		{
			Y = PC->GetControlRotation().Yaw;
		}
		TeleportCaptain(To + RemoteOffset, Y, false);
	}
}

// ================================================================================================================== the console

namespace
{
	UAstraBoardSubsystem* RdBoard(UWorld* W) { return W ? W->GetSubsystem<UAstraBoardSubsystem>() : nullptr; }

	FAutoConsoleCommandWithWorldAndArgs RdCmdTestCaptain(TEXT("astra.board.testcaptain"), TEXT("Testing: a Captain with no pawn (the war bench): astra.board.testcaptain <x> <y> <z> [yaw]   (cm on the Aquila's plan, feet); astra.board.testcaptain off"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& A, UWorld* W)
		{
			UAstraBoardSubsystem* B = RdBoard(W);
			if (!B)
			{
				return;
			}
			if (A.Num() >= 1 && A[0].Equals(TEXT("off")))
			{
				B->SetTestCaptain(false);
				return;
			}
			B->SetTestCaptain(true, A.Num() >= 3 ? FVector(FCString::Atod(*A[0]), FCString::Atod(*A[1]), FCString::Atod(*A[2])) : FVector::ZeroVector, A.Num() >= 4 ? FCString::Atof(*A[3]) : 0.f);
		}));
}
