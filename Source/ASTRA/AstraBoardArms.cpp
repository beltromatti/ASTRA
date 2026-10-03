// ASTRA — ABBORDAGGI: the Captain's weapons: where they are kept, who sends them up, and what the crew knows of it.
//
// Two places hold them: the rack of the Marine Armory on Deck 8 (the AR-181 rifle and the M27S sidearm, on the aisle side of the armourer's issue counter) and a locker on the wall of the
// Captain's Ready Room on Deck 1, by the door to the port corridor (a sidearm). The stock of each is the ship's, kept here; the rack or the locker (AstraArmory.*) is its picture while the
// Captain is near, and its key: E takes what it holds that he does not carry, or puts back what it takes.
//
// An order to the armourer (`issue_weapon`: the crew's tool, or the console's) is a real delivery: the weapon leaves the armory's rack at once, a marine of the armory (the armourer of the
// roster) takes it up the ship, and after the time of the way, with a runner's pace and the minute it takes to sign it out, it is in the Captain's hands wherever he is on foot; if he
// has taken it himself in the meantime it goes back on the rack. The crew is told where the weapons are and what he carries (`arms` in the ship state).

#include "AstraBoardSubsystem.h"

#include "ASTRA.h"
#include "AstraArmory.h"
#include "AstraCombatFx.h"
#include "AstraCrewRoster.h"
#include "AstraFpsComponent.h"
#include "AstraLifeSubsystem.h"
#include "AstraShipSubsystem.h"
#include "AstraWeapon.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/Pawn.h"
#include "HAL/IConsoleManager.h"
#include "Kismet/GameplayStatics.h"

using namespace AstraBoard;

namespace
{
	constexpr float BaSpawnCm = 6000.f;            // a post's picture is made when the Captain is this near (on its deck) ...
	constexpr float BaKeepCm = 7800.f;             // ... and let go beyond this
	constexpr float BaSignOutS = 14.f;             // the armourer's minute: the weapon signed out and on its way
	constexpr float BaRunnerCmS = 300.f;           // a marine at a run, with a case in his hand
	constexpr float BaHandsGiveUpS = 240.f;        // how long a runner waits for him to be on foot again
	constexpr TCHAR BaKeys[] = TEXT("   ·   LMB fire   RMB aim   R reload   1 / 2 weapons   H holster");
	constexpr TCHAR BaKeysOne[] = TEXT("   ·   LMB fire   RMB aim   R reload   H holster");

	const TCHAR* BaWeaponWords(bool bRifle, bool bPistol)
	{
		return bRifle && bPistol ? TEXT("the rifle and the sidearm") : (bRifle ? TEXT("the rifle") : TEXT("the sidearm"));
	}
}

UAstraBoardSubsystem::FArmsPost* UAstraBoardSubsystem::FindPost(FName Id)
{
	return ArmsPosts.FindByPredicate([Id](const FArmsPost& P) { return P.Id == Id; });
}

const UAstraBoardSubsystem::FArmsPost* UAstraBoardSubsystem::FindPost(FName Id) const
{
	return ArmsPosts.FindByPredicate([Id](const FArmsPost& P) { return P.Id == Id; });
}

// ================================================================================================================== the posts

void UAstraBoardSubsystem::BuildArmsPosts()
{
	ArmsPosts.Reset();
	bArmsBuilt = true;
	if (!Dmg.IsValid())
	{
		return;
	}
	const auto Find = [this](const TCHAR* Id, const TCHAR* Kind) -> int32
	{
		if (const int32* P = Dmg->CompByName.Find(FName(Id)))
		{
			return *P;
		}
		for (int32 i = 0; i < Dmg->Comps.Num(); ++i)
		{
			if (Dmg->Comps[i].Kind == FName(Kind))
			{
				return i;
			}
		}
		return INDEX_NONE;
	};
	// the Marine Armory (Deck 8): its mesh stands with its origin at the corner by the corridor (the plan's greatest x and y), turned half a circle, so that x runs aft and y to port from it; the
	// door is on the near wall 6 m in, straight in front of the issue counter (6 m in, 4.2 m across, 3.2 m long): the rack stands to the right of the counter, 3 m in and 3.6 m across, its back to
	// the cage's bars and its face to the room's door (the door's axis stays free)
	if (const int32 A = Find(TEXT("d8_armory_B1"), TEXT("armory")); A != INDEX_NONE)
	{
		const FBox& B = Dmg->Comps[A].Box;
		FArmsPost P;
		P.Id = FName(TEXT("armory"));
		P.Label = TEXT("the Marine Armory's rack");
		P.Where = TEXT("Marine Armory, Deck 8: the rack at the armourer's issue counter");
		P.Pos = FVector(B.Max.X - 300.0, B.Max.Y - 360.0, B.Min.Z);
		P.Yaw = 90.f;
		P.bRifle = P.bPistol = true;
		ArmsPosts.Add(P);
	}
	// the Ready Room (Deck 1): the locker is on the wall of the near side (the port wall) between the second framed chart and the door to the corridor (a 66 cm stretch of wall), its front into the room
	if (const int32 R = Find(TEXT("ready_room"), TEXT("ready_room")); R != INDEX_NONE)
	{
		const FBox& B = Dmg->Comps[R].Box;
		FArmsPost P;
		P.Id = FName(TEXT("ready_room"));
		P.Label = TEXT("the Ready Room's locker");
		P.Where = TEXT("Ready Room, Deck 1: the locker by the door to the corridor");
		P.Pos = FVector(B.Min.X + 365.0, B.Min.Y + 18.0, B.Min.Z);                 // (the actor's origin is the cabinet's front face: 18 cm off the wall's inner face)
		P.Yaw = 90.f;
		P.bLocker = true;
		P.bPistol = true;
		ArmsPosts.Add(P);
	}
	UE_LOG(LogASTRA, Log, TEXT("[Arms] %d places for the Captain's weapons"), ArmsPosts.Num());
}

void UAstraBoardSubsystem::TickArms(float Dt)
{
	UWorld* W = GetWorld();
	if (!bArmsBuilt || !W)
	{
		return;
	}
	// --- the armourer's delivery
	if (Delivery.bActive)
	{
		Delivery.T += Dt;
		if (Delivery.T >= Delivery.EtaS)
		{
			APawn* Me = UGameplayStatics::GetPlayerPawn(W, 0);
			UAstraFpsComponent* F = Me ? Me->FindComponentByClass<UAstraFpsComponent>() : nullptr;
			const bool bFree = F && F->HandsFree();
			// seated, in a lift, down or flying: the runner waits (twenty seconds for a Captain who is only seated: it is put in his hands and comes up when he stands)
			const bool bAbleToTake = F && (bFree || Delivery.HandsWaitS > 20.f);
			FArmsPost* Arm = FindPost(FName(TEXT("armory")));
			if (!bFree)
			{
				Delivery.HandsWaitS += Dt;
			}
			const bool bTooLong = Delivery.HandsWaitS > BaHandsGiveUpS;
			const bool bRifleNow = F && Delivery.bRifle && !F->Carries(EAstraWeapon::Rifle);
			const bool bPistolNow = F && Delivery.bPistol && !F->Carries(EAstraWeapon::Pistol);
			if (bTooLong || (F && !bRifleNow && !bPistolNow))
			{
				// he took it himself, or could not be found: it goes back on the rack
				if (Arm)
				{
					Arm->bRifle |= Delivery.bRifle;
					Arm->bPistol |= Delivery.bPistol;
				}
				if (UAstraShipSubsystem* S = ShipSub())
				{
					S->PublishEvent(bTooLong ? FString::Printf(TEXT("arms: %s could not find the Captain on foot and took the weapon back to the Marine Armory"), *Delivery.By)
					                         : FString::Printf(TEXT("arms: the Captain has what %s was bringing: it goes back to the Marine Armory"), *Delivery.By), false);
				}
				Delivery = FDelivery();
			}
			else if (bAbleToTake)
			{
				if (bRifleNow)
				{
					F->GiveWeapon(EAstraWeapon::Rifle, true, true);
				}
				if (bPistolNow)
				{
					F->GiveWeapon(EAstraWeapon::Pistol, true, !bRifleNow);
				}
				if (Arm)
				{
					Arm->bRifle |= Delivery.bRifle && !bRifleNow;     // (what he already had goes back)
					Arm->bPistol |= Delivery.bPistol && !bPistolNow;
				}
				F->Prompt(FString::Printf(TEXT("%s HANDS YOU %s%s"), *Delivery.By.ToUpper(), *FString(BaWeaponWords(bRifleNow, bPistolNow)).ToUpper(), F->Carries(EAstraWeapon::Rifle) && F->Carries(EAstraWeapon::Pistol) ? BaKeys : BaKeysOne), 7.f);
				if (UAstraCombatFx* Sfx = FxSub())
				{
					Sfx->PlaySoundAt(TEXT("/Game/ASTRA/Audio/SW_Gun_Draw.SW_Gun_Draw"), Me->GetActorLocation(), 0.8f, 1.f);
				}
				if (UAstraShipSubsystem* S = ShipSub())
				{
					S->PublishEvent(FString::Printf(TEXT("arms: %s has put %s in the Captain's hands"), *Delivery.By, BaWeaponWords(bRifleNow, bPistolNow)), false);
				}
				Delivery = FDelivery();
			}
		}
	}
	// --- the posts' pictures: made while the Captain is near, let go when he is not
	ArmsT -= Dt;
	if (ArmsT > 0.f)
	{
		return;
	}
	ArmsT = 0.5f;
	ArmourerT -= 0.5f;
	if (ArmourerT <= 0.f)
	{
		ArmourerT = 20.f;
		if (const FArmsPost* Arm = FindPost(FName(TEXT("armory"))))
		{
			Armourer = ArmourerName(Arm->Pos);
		}
	}
	const APawn* Me = UGameplayStatics::GetPlayerPawn(W, 0);
	for (FArmsPost& P : ArmsPosts)
	{
		const double D = Me ? FVector::Dist2D(Me->GetActorLocation(), P.Pos) : 1.0e9;
		const bool bSameDeck = Me && FMath::Abs(Me->GetActorLocation().Z - P.Pos.Z) < 420.0;
		const bool bHere = P.Actor.IsValid();
		if (!bHere && bSameDeck && D < BaSpawnCm)
		{
			bool bLevelHas = false;                              // the level may have placed a rack of its own where the kit has one: this one is not needed then
			if (!P.bLocker)
			{
				for (TActorIterator<AAstraArmoryRack> It(W); It; ++It)
				{
					bLevelHas |= It->GetPostId().IsNone() && FVector::Dist2D(It->GetActorLocation(), P.Pos) < 900.0;
				}
			}
			if (bLevelHas)
			{
				continue;
			}
			FActorSpawnParameters Sp;
			Sp.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
			const FName Id = P.Id;
			const bool bLocker = P.bLocker;
			Sp.CustomPreSpawnInitialization = [Id, bLocker](AActor* A)
			{
				if (AAstraArmoryRack* R = Cast<AAstraArmoryRack>(A))
				{
					R->MakePost(Id, bLocker ? AAstraArmoryRack::EKind::Locker : AAstraArmoryRack::EKind::Rack);
				}
			};
			P.Actor = W->SpawnActor<AAstraArmoryRack>(P.Pos, FRotator(0.f, P.Yaw, 0.f), Sp);
			if (P.Actor.IsValid())
			{
				UE_LOG(LogASTRA, Log, TEXT("[Arms] %s set up"), *P.Label);
			}
		}
		else if (bHere && (!bSameDeck || D > BaKeepCm))
		{
			P.Actor->Destroy();
			P.Actor.Reset();
		}
	}
}

// ================================================================================================================== E at a post

bool UAstraBoardSubsystem::UseArmsPost(FName Id, APawn* Me, FString& OutNotice)
{
	FArmsPost* P = FindPost(Id);
	UAstraFpsComponent* F = Me ? Me->FindComponentByClass<UAstraFpsComponent>() : nullptr;
	if (!P || !F)
	{
		return false;
	}
	const bool bTakeRifle = P->bRifle && !F->Carries(EAstraWeapon::Rifle);
	const bool bTakePistol = P->bPistol && !F->Carries(EAstraWeapon::Pistol);
	if (bTakeRifle || bTakePistol)
	{
		if (bTakeRifle)
		{
			F->GiveWeapon(EAstraWeapon::Rifle, true, true);
			P->bRifle = false;
		}
		if (bTakePistol)
		{
			F->GiveWeapon(EAstraWeapon::Pistol, true, !bTakeRifle);
			P->bPistol = false;
		}
		OutNotice = FString::Printf(TEXT("%s TAKEN%s"), *FString(BaWeaponWords(bTakeRifle, bTakePistol)).ToUpper(), F->Carries(EAstraWeapon::Rifle) && F->Carries(EAstraWeapon::Pistol) ? BaKeys : BaKeysOne);
		return true;
	}
	// nothing there that he lacks: what the post takes back and he carries goes on it
	const bool bPutRifle = !P->bLocker && !P->bRifle && F->Carries(EAstraWeapon::Rifle);
	const bool bPutPistol = !P->bPistol && F->Carries(EAstraWeapon::Pistol);
	if (bPutRifle || bPutPistol)
	{
		if (bPutRifle)
		{
			F->GiveWeapon(EAstraWeapon::Rifle, false);
			P->bRifle = true;
		}
		if (bPutPistol)
		{
			F->GiveWeapon(EAstraWeapon::Pistol, false);
			P->bPistol = true;
		}
		OutNotice = P->bLocker ? FString(TEXT("THE SIDEARM IS BACK IN THE LOCKER")) : (bPutRifle && bPutPistol ? FString(TEXT("WEAPONS RETURNED TO THE RACK")) : FString::Printf(TEXT("%s RETURNED TO THE RACK"), *FString(BaWeaponWords(bPutRifle, bPutPistol)).ToUpper()));
		return true;
	}
	return false;
}

bool UAstraBoardSubsystem::ArmsPostView(FName Id, const UAstraFpsComponent* F, bool& bOutRifle, bool& bOutPistol, FString& OutPrompt) const
{
	const FArmsPost* P = FindPost(Id);
	if (!P)
	{
		return false;
	}
	bOutRifle = P->bRifle;
	bOutPistol = P->bPistol;
	OutPrompt.Reset();
	if (!F)
	{
		return true;
	}
	const bool bTakeRifle = P->bRifle && !F->Carries(EAstraWeapon::Rifle);
	const bool bTakePistol = P->bPistol && !F->Carries(EAstraWeapon::Pistol);
	if (bTakeRifle || bTakePistol)
	{
		OutPrompt = FString::Printf(TEXT("E   TAKE %s"), *FString(BaWeaponWords(bTakeRifle, bTakePistol)).ToUpper());
	}
	else if ((!P->bLocker && !P->bRifle && F->Carries(EAstraWeapon::Rifle)) || (!P->bPistol && F->Carries(EAstraWeapon::Pistol)))
	{
		OutPrompt = P->bLocker ? FString(TEXT("E   PUT THE SIDEARM BACK")) : FString(TEXT("E   PUT THE WEAPONS BACK"));
	}
	return true;
}

// ================================================================================================================== the armourer

FString UAstraBoardSubsystem::ArmourerName(const FVector& Near) const
{
	// the armourer of the roster: a fit marine whose job is the armory's (the one nearest the armory), else whoever of the marines stands there
	const UAstraLifeSubsystem* L = LifeSub();
	const UAstraShipSubsystem* S = ShipSub();
	if (!L || !L->IsRunning() || !S)
	{
		return FString(TEXT("the armourer"));
	}
	const FAstraLifeSim& LS = L->Sim();
	const TArray<FAstraCrewman>& Crew = S->GetRoster().Get();
	int32 Best = INDEX_NONE;
	double BestD = 1.0e18;
	for (int32 p = 0; p < LS.NumPeople(); ++p)
	{
		const FAstraLifePerson& P = LS.Person(p);
		if (P.Status != 0 || P.bAway || P.bTransit || !Crew.IsValidIndex(P.Roster) || !Crew[P.Roster].Dept.Equals(TEXT("marines"), ESearchCase::IgnoreCase))
		{
			continue;
		}
		const bool bArmourer = P.Job.Contains(TEXT("armo"), ESearchCase::IgnoreCase) || P.Job.Contains(TEXT("ordnance"), ESearchCase::IgnoreCase);
		const double D = FVector::Dist(P.Pos, Near) + (bArmourer ? 0.0 : 1.0e6);
		if (D < BestD)
		{
			BestD = D;
			Best = p;
		}
	}
	if (Best == INDEX_NONE)
	{
		return FString(TEXT("the armourer"));
	}
	return Crew[LS.Person(Best).Roster].Name();
}

bool UAstraBoardSubsystem::IssueWeapon(const FString& KindIn, const FString& Who, FString& OutDetail)
{
	(void)Who;                                                      // (the tool's schema has one person who is issued a weapon: the Captain)
	UWorld* W = GetWorld();
	if (!bArmsBuilt || !W)
	{
		OutDetail = TEXT("the armoury is not answering yet");
		return false;
	}
	const FString K = KindIn.TrimStartAndEnd().ToLower();
	bool bWantRifle = false, bWantPistol = false;
	if (K == TEXT("rifle"))
	{
		bWantRifle = true;
	}
	else if (K == TEXT("pistol") || K == TEXT("sidearm"))
	{
		bWantPistol = true;
	}
	else if (K == TEXT("kit") || K == TEXT("both") || K.IsEmpty())
	{
		bWantRifle = bWantPistol = true;
	}
	else
	{
		OutDetail = FString::Printf(TEXT("the armoury has a rifle (AR-181) and a sidearm (M27S): kind is rifle, pistol or kit, not '%s'"), *KindIn);
		return false;
	}
	APawn* Me = UGameplayStatics::GetPlayerPawn(W, 0);
	UAstraFpsComponent* F = Me ? Me->FindComponentByClass<UAstraFpsComponent>() : nullptr;
	if (!F)
	{
		OutDetail = TEXT("the Captain is not on foot (he is flying a Falcon or in a pod): nobody can put a weapon in his hands now");
		return false;
	}
	if (Delivery.bActive)
	{
		OutDetail = FString::Printf(TEXT("%s is already on the way with %s: about %.0f s"), *Delivery.By, BaWeaponWords(Delivery.bRifle, Delivery.bPistol), FMath::Max(0.f, Delivery.EtaS - Delivery.T));
		return false;
	}
	const bool bLackRifle = bWantRifle && !F->Carries(EAstraWeapon::Rifle);
	const bool bLackPistol = bWantPistol && !F->Carries(EAstraWeapon::Pistol);
	if (!bLackRifle && !bLackPistol)
	{
		OutDetail = TEXT("the Captain already carries it");
		return false;
	}
	FArmsPost* Arm = FindPost(FName(TEXT("armory")));
	if (!Arm)
	{
		OutDetail = TEXT("the ship's plan has no armoury to send from");
		return false;
	}
	const bool bGiveRifle = bLackRifle && Arm->bRifle;
	const bool bGivePistol = bLackPistol && Arm->bPistol;
	if (!bGiveRifle && !bGivePistol)
	{
		OutDetail = FString::Printf(TEXT("the armoury's rack has no %s on it now (it was taken: the Captain's, or it is in the Ready Room's locker)"), bLackRifle && bLackPistol ? TEXT("rifle or sidearm") : (bLackRifle ? TEXT("rifle") : TEXT("sidearm")));
		return false;
	}
	if (FVector::Dist2D(Me->GetActorLocation(), Arm->Pos) < 650.0 && FMath::Abs(Me->GetActorLocation().Z - Arm->Pos.Z) < 420.0)
	{
		OutDetail = TEXT("the Captain is in the Marine Armory, at the rack: he takes it himself with E");
		return false;
	}
	// the way from the armory to where he stands, at a runner's pace after the minute the armourer takes to sign it out
	float Metres = 0.f;
	if (Map.IsValid())
	{
		TArray<FVector> Pts;
		FBoardRouteOptions Opt;
		Opt.bThroughSealed = true;
		const FVector Feet = Me->GetActorLocation() - FVector(0.0, 0.0, Me->GetSimpleCollisionHalfHeight());
		if (Map->CompAt(Feet) == INDEX_NONE || !Map->Route(Arm->Pos, Feet, Pts, Opt, &Metres))
		{
			Metres = (float)(FVector::Dist(Arm->Pos, Feet) / 100.0) * 1.5f;                // (a place the plan does not hold: the straight line, and a half again)
		}
	}
	else
	{
		Metres = (float)(FVector::Dist(Arm->Pos, Me->GetActorLocation()) / 100.0) * 1.5f;
	}
	Delivery = FDelivery();
	Delivery.bActive = true;
	Delivery.bRifle = bGiveRifle;
	Delivery.bPistol = bGivePistol;
	Delivery.EtaS = FMath::Clamp(BaSignOutS + Metres * 100.f / BaRunnerCmS, 18.f, 200.f);
	Armourer = ArmourerName(Arm->Pos);
	ArmourerT = 20.f;
	Delivery.By = Armourer;
	Arm->bRifle &= !bGiveRifle;                                     // it leaves the rack with the armourer
	Arm->bPistol &= !bGivePistol;
	OutDetail = FString::Printf(TEXT("%s is bringing %s from the Marine Armory on Deck 8: about %.0f s, and it will be put in the Captain's hands where he stands"), *Delivery.By, BaWeaponWords(bGiveRifle, bGivePistol), Delivery.EtaS);
	if (UAstraShipSubsystem* S = ShipSub())
	{
		S->PublishEvent(FString::Printf(TEXT("arms: %s is bringing %s from the Marine Armory to the Captain (about %.0f s)"), *Delivery.By, BaWeaponWords(bGiveRifle, bGivePistol), Delivery.EtaS), false);
	}
	UE_LOG(LogASTRA, Log, TEXT("[Arms] %s"), *OutDetail);
	return true;
}

// ================================================================================================================== what the crew knows

TSharedRef<FJsonObject> UAstraBoardSubsystem::ArmsJson() const
{
	TSharedRef<FJsonObject> J = MakeShared<FJsonObject>();
	if (!bArmsBuilt)
	{
		return J;
	}
	const APawn* Me = GetWorld() ? UGameplayStatics::GetPlayerPawn(GetWorld(), 0) : nullptr;
	const UAstraFpsComponent* F = Me ? Me->FindComponentByClass<UAstraFpsComponent>() : nullptr;
	J->SetStringField(TEXT("captain_carries"), F ? (F->HasKit() ? F->StatusText() : FString(TEXT("nothing"))) : FString(TEXT("nothing (he is not on foot)")));
	TArray<TSharedPtr<FJsonValue>> Where;
	for (const FArmsPost& P : ArmsPosts)
	{
		TSharedRef<FJsonObject> O = MakeShared<FJsonObject>();
		O->SetStringField(TEXT("where"), P.Where);
		FString Holds;
		if (P.bRifle)
		{
			Holds = TEXT("an AR-181 service rifle");
		}
		if (P.bPistol)
		{
			Holds += (Holds.IsEmpty() ? TEXT("") : TEXT(" and ")) + FString(TEXT("an M27S sidearm"));
		}
		O->SetStringField(TEXT("holds"), Holds.IsEmpty() ? FString(TEXT("nothing now")) : Holds);
		Where.Add(MakeShared<FJsonValueObject>(O));
	}
	J->SetArrayField(TEXT("kept"), Where);
	if (!Armourer.IsEmpty())
	{
		J->SetStringField(TEXT("armourer"), Armourer + TEXT(" (Marine Armory)"));
	}
	if (Delivery.bActive)
	{
		J->SetStringField(TEXT("on_the_way"), FString::Printf(TEXT("%s is bringing %s to the Captain: about %.0f s"), *Delivery.By, BaWeaponWords(Delivery.bRifle, Delivery.bPistol), FMath::Max(0.f, Delivery.EtaS - Delivery.T)));
	}
	return J;
}

namespace
{
	FAutoConsoleCommandWithWorldAndArgs BaCmdIssue(TEXT("astra.arms.issue"), TEXT("Testing: the armourer brings the Captain a weapon: astra.arms.issue [rifle|pistol|kit]"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& A, UWorld* W)
		{
			if (UAstraBoardSubsystem* B = W ? W->GetSubsystem<UAstraBoardSubsystem>() : nullptr)
			{
				FString D;
				const bool bOk = B->IssueWeapon(A.Num() ? A[0] : FString(TEXT("kit")), FString(), D);
				UE_LOG(LogASTRA, Log, TEXT("[Arms] %s: %s"), bOk ? TEXT("ordered") : TEXT("refused"), *D);
				if (GEngine) { GEngine->AddOnScreenDebugMessage(-1, 6.f, bOk ? FColor::Green : FColor::Red, D); }
			}
		}));
}
