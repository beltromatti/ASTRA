#include "AstraBoardSubsystem.h"

#include "ASTRA.h"
#include "ASTRACharacter.h"
#include "AstraCombatFx.h"
#include "AstraCombatant.h"
#include "AstraCrewRoster.h"
#include "AstraFpsComponent.h"
#include "AstraLifeSubsystem.h"
#include "AstraShipSubsystem.h"
#include "Async/Async.h"
#include "Camera/PlayerCameraManager.h"
#include "Components/CapsuleComponent.h"
#include "Engine/World.h"
#include "GameFramework/Character.h"
#include "GameFramework/PlayerController.h"
#include "Kismet/GameplayStatics.h"
#include "Misc/App.h"

using namespace AstraBoard;

DECLARE_CYCLE_STAT(TEXT("Boarding"), STAT_AstraBoarding, STATGROUP_Astra);

namespace
{
	constexpr float BdCaptainArmor = 0.8f;        // the share of a round that goes through the Captain's vest
	constexpr float BdBodyReachCm = 6500.f;       // soldiers nearer than this (on the Captain's deck) get a body
	constexpr float BdBodyKeepCm = 8200.f;
	constexpr int32 BdMaxBodies = 22;
	constexpr float BdCleanUpS = 75.f;            // how long the fallen lie after the fight

	TAutoConsoleVariable<int32> BdCVarFriendlyFire(TEXT("astra.board.friendlyfire"), 0, TEXT("1: the Captain's rounds wound the marines too"));

	TSharedPtr<FJsonObject> BdArgs1(const TCHAR* K, const FString& V)
	{
		TSharedPtr<FJsonObject> A = MakeShared<FJsonObject>();
		A->SetStringField(K, V);
		return A;
	}
}

bool UAstraBoardSubsystem::ShouldCreateSubsystem(UObject* Outer) const
{
	const UWorld* World = Cast<UWorld>(Outer);
	return World && (World->WorldType == EWorldType::Game || World->WorldType == EWorldType::PIE);
}

UAstraShipSubsystem* UAstraBoardSubsystem::ShipSub() const
{
	return Ship.IsValid() ? Ship.Get() : (GetWorld() ? GetWorld()->GetSubsystem<UAstraShipSubsystem>() : nullptr);
}

UAstraLifeSubsystem* UAstraBoardSubsystem::LifeSub() const
{
	return Life.IsValid() ? Life.Get() : (GetWorld() ? GetWorld()->GetSubsystem<UAstraLifeSubsystem>() : nullptr);
}

UAstraCombatFx* UAstraBoardSubsystem::FxSub() const
{
	return Fx.IsValid() ? Fx.Get() : (GetWorld() ? GetWorld()->GetSubsystem<UAstraCombatFx>() : nullptr);
}

void UAstraBoardSubsystem::OnWorldBeginPlay(UWorld& InWorld)
{
	Super::OnWorldBeginPlay(InWorld);
	Phase = EPhase::Loading;
	Ship = InWorld.GetSubsystem<UAstraShipSubsystem>();
	Life = InWorld.GetSubsystem<UAstraLifeSubsystem>();
	Fx = InWorld.GetSubsystem<UAstraCombatFx>();
	// the plan's rooms and doors, and the soldiers' map of them, are made on a worker: the game does not wait for them (the first boarding comes minutes later)
	Dmg = MakeShared<FAstraDamageMap>();
	const TSharedPtr<FAstraDamageMap> D = Dmg;
	MapFuture = Async(EAsyncExecution::ThreadPool, [D]() -> TSharedPtr<FAstraBoardMap>
	{
		FString Err;
		if (!D->Load(Err))
		{
			UE_LOG(LogASTRA, Log, TEXT("[Board] %s: no fighting inside the hull"), *Err);
			return nullptr;
		}
		TSharedPtr<FAstraBoardMap> M = MakeShared<FAstraBoardMap>();
		if (!M->Build(D.ToSharedRef()))
		{
			UE_LOG(LogASTRA, Log, TEXT("[Board] the plan has no compartments: no fighting inside the hull"));
			return nullptr;
		}
		return M;
	});
}

void UAstraBoardSubsystem::Deinitialize()
{
	ClearBodies();
	if (Breach)
	{
		Breach->Destroy();
	}
	Breach = nullptr;
	Super::Deinitialize();
}

void UAstraBoardSubsystem::TryFinishLoading()
{
	if (!MapFuture.IsValid() || !MapFuture.IsReady())
	{
		return;
	}
	Map = MapFuture.Get();
	MapFuture = TFuture<TSharedPtr<FAstraBoardMap>>();
	if (!Map.IsValid())
	{
		Phase = EPhase::Failed;
		return;
	}
	Phase = EPhase::Idle;
	UE_LOG(LogASTRA, Log, TEXT("[Board] ready: %d compartments, %d portals, %d corner slots"), Map->GetComps().Num(), Map->GetPortals().Num(), Map->GetSlots().Num());
}

int32 UAstraBoardSubsystem::NumBodies() const
{
	return BodyOf.Num();
}

double UAstraBoardSubsystem::SinceCaptainHurt() const
{
	return GetWorld() ? GetWorld()->GetTimeSeconds() - CapHurtAt : 1.0e9;
}

// ================================================================================================================== the beginning

bool UAstraBoardSubsystem::PickBreach(const FString& Id, int32& OutComp, FVector& OutAt, FString& OutWhy) const
{
	if (!Dmg.IsValid() || !Map.IsValid())
	{
		OutWhy = TEXT("the ship's plan is not read yet");
		return false;
	}
	const FAstraDamageMap& D = *Dmg;
	int32 C = INDEX_NONE;
	if (!Id.IsEmpty())
	{
		const int32* P = D.CompByName.Find(FName(*Id));
		if (!P)
		{
			OutWhy = FString::Printf(TEXT("the plan has no compartment '%s'"), *Id);
			return false;
		}
		C = *P;
	}
	else
	{
		// the default: Deck 7's capacitor hall on the port side (the bench's), else the outermost room of Deck 7 in the middle sections
		if (const int32* P = D.CompByName.Find(FName(TEXT("d7_capacitors_D2"))))
		{
			C = *P;
		}
		else
		{
			float Best = -1.f;
			for (int32 i = 0; i < D.Comps.Num(); ++i)
			{
				const FAstraDmgComp& K = D.Comps[i];
				if (K.Deck != 7 || K.bCorridor || K.Status == 0 || K.Section < TEXT('C') || K.Section > TEXT('F') || K.Box.GetSize().X < 600.0)
				{
					continue;
				}
				const float Out = (float)FMath::Abs(0.5 * (K.Box.Min.Y + K.Box.Max.Y));
				if (Out > Best)
				{
					Best = Out;
					C = i;
				}
			}
		}
	}
	if (!Map->GetComps().IsValidIndex(C))
	{
		OutWhy = TEXT("no room to cut into");
		return false;
	}
	const FBox& B = Map->GetComps()[C].Box;
	OutComp = C;
	OutAt = FVector(0.5 * (B.Min.X + B.Max.X), B.Max.Y > 0.0 ? B.Max.Y - 80.0 : B.Min.Y + 80.0, B.Min.Z);
	return true;
}

void UAstraBoardSubsystem::SealDoor(int32 Door, bool bSealed)
{
	if (!Dmg.IsValid() || !Dmg->Doors.IsValidIndex(Door))
	{
		return;
	}
	Fight.SealDoor(Door, bSealed);
	if (UAstraShipSubsystem* S = ShipSub())
	{
		S->SealBulkhead(Dmg->Doors[Door].Id, bSealed);
	}
	if (bSealed)
	{
		SealedByUs.Add(Door);
	}
	else
	{
		SealedByUs.Remove(Door);
	}
}

void UAstraBoardSubsystem::SealSections(int32 BreachComp, const FVector& At)
{
	if (!Map.IsValid())
	{
		return;
	}
	const int32 Deck = Map->GetComps()[BreachComp].Deck;
	int32 N = 0;
	for (const FBoardPortal& P : Map->GetPortals())
	{
		if (P.Kind == FBoardPortal::EKind::Blast && Map->GetComps()[P.A].Deck == Deck && FVector::Dist2D(P.Pos, At) < 9000.0 && !Fight.IsDoorSealed(P.Door))
		{
			SealDoor(P.Door, true);
			++N;
		}
	}
	UE_LOG(LogASTRA, Log, TEXT("[Board] %d pressure bulkheads of deck %d sealed round the breach"), N, Deck);
}

void UAstraBoardSubsystem::OpenSections()
{
	const TArray<int32> Doors = SealedByUs.Array();
	for (const int32 D : Doors)
	{
		SealDoor(D, false);
	}
}

void UAstraBoardSubsystem::MakeSightOverride()
{
	// a round that reaches the Captain flies through the real level: the sim asks the world whether a man and the Captain see each other (a locker, a console is cover
	// too); the bodies of the soldiers block the player's rounds (visibility) but not this (the camera channel)
	Fight.SightOverride = [this](const FVector& A, const FVector& B) -> bool
	{
		UWorld* W = GetWorld();
		if (!W)
		{
			return true;
		}
		FCollisionQueryParams Q(SCENE_QUERY_STAT(AstraBoardSight), false);
		return !W->LineTraceTestByChannel(A, B, ECC_Camera, Q);
	};
}

void UAstraBoardSubsystem::MobiliseMarines()
{
	UAstraLifeSubsystem* L = LifeSub();
	UAstraShipSubsystem* S = ShipSub();
	MarineUnits.Reset();
	RosterOfUnit.Reset();
	PersonOfUnit.Reset();
	if (!L || !L->IsRunning() || !S || !Map.IsValid())
	{
		return;                                       // no life aboard (a bench world): the Captain and the Mandate alone
	}
	FAstraLifeSim& LS = L->Sim();
	const TArray<FAstraCrewman>& Crew = S->GetRoster().Get();
	struct FMarine { int32 Roster, Person; FVector Pos; EAstraLifeAct Act; int32 Rank; float Wake; };
	TArray<FMarine> Awake, Roused;
	for (int32 p = 0; p < LS.NumPeople(); ++p)
	{
		const FAstraLifePerson& P = LS.Person(p);
		if (P.Status != 0 || P.Act == EAstraLifeAct::Dead || P.Act == EAstraLifeAct::Patient || P.Act == EAstraLifeAct::Repair)
		{
			continue;
		}
		if (!Crew.IsValidIndex(P.Roster) || !Crew[P.Roster].Dept.Equals(TEXT("marines"), ESearchCase::IgnoreCase))
		{
			continue;
		}
		if (Map->CompAt(P.Pos) == INDEX_NONE)
		{
			continue;                                 // somewhere the plan does not hold (a deck not modelled): not in this fight
		}
		FMarine M;
		M.Roster = P.Roster;
		M.Person = p;
		M.Pos = P.Pos;
		M.Act = P.Act;
		const FString& R = Crew[P.Roster].Rank;
		M.Rank = R.Equals(TEXT("Captain")) ? 2 : (R.Equals(TEXT("Sergeant")) ? 1 : 0);
		// the watch that is on its feet at its post goes now; whoever is awake off duty arms first; whoever is asleep wakes, dresses, arms
		const bool bPost = P.Act == EAstraLifeAct::Duty || P.Act == EAstraLifeAct::Battle;
		M.Wake = bPost ? 0.f : (P.Act == EAstraLifeAct::Sleep ? P.WakeDelayS + FMath::FRandRange(35.f, 70.f) : FMath::FRandRange(18.f, 40.f));
		(M.Wake <= 0.f ? Awake : Roused).Add(M);
	}
	// the armory: where the reaction team arms itself
	FVector Armory = FVector::ZeroVector;
	bool bArmory = false;
	for (int32 i = 0; i < Map->GetComps().Num() && !bArmory; ++i)
	{
		if (Map->GetComps()[i].Kind == TEXT("armory"))
		{
			Armory = Map->CentreOf(i);
			bArmory = true;
		}
	}
	const auto Metric = [&](const FVector& P) { return bArmory ? FVector::Dist(P, Armory) + FMath::Abs(P.Z - Armory.Z) * 3.0 : 0.0; };
	Awake.Sort([&](const FMarine& A, const FMarine& B) { return Metric(A.Pos) < Metric(B.Pos); });
	int32 SquadNo = 0;
	const auto MakeSquad = [&](TArray<FMarine>& Group, const FString& Name, bool bQuick, float MusterS)
	{
		if (Group.IsEmpty())
		{
			return;
		}
		const int32 Sq = Fight.AddSquad(ESide::Aquila, Name);
		if (bQuick)
		{
			Fight.SquadMutable(Sq)->bQuickReaction = true;
			Fight.SquadMutable(Sq)->MusterT = MusterS;
		}
		// the leader: the highest rank, the nearest to the armory among them
		int32 Lead = 0;
		for (int32 i = 1; i < Group.Num(); ++i)
		{
			if (Group[i].Rank > Group[Lead].Rank)
			{
				Lead = i;
			}
		}
		for (int32 i = 0; i < Group.Num(); ++i)
		{
			const FMarine& M = Group[i];
			const int32 U = Fight.AddMarine(Crew[M.Roster].Name(), M.Roster, M.Pos, i == Lead, Sq);
			MarineUnits.Add(U);
			RosterOfUnit.Add(U, M.Roster);
			PersonOfUnit.Add(U, M.Person);
			if (M.Wake > 0.f)
			{
				Fight.DelayUnit(U, M.Wake);
			}
			L->ReleaseBodyOf(M.Person);               // the life's body of this marine goes back to its pool: the fight makes its own
			LS.Commandeer(M.Person, true, M.Pos);
		}
	};
	// the reaction team: the twelve awake nearest the armory, in two squads of six, who arm for twenty-five seconds; the rest of the watch in fours
	TArray<FMarine> Quick;
	const int32 NQuick = FMath::Min(12, Awake.Num());
	for (int32 i = 0; i < NQuick; ++i)
	{
		Quick.Add(Awake[i]);
	}
	Awake.RemoveAt(0, NQuick);
	for (int32 g = 0; g < Quick.Num(); g += 6)
	{
		TArray<FMarine> G;
		for (int32 i = g; i < FMath::Min(g + 6, Quick.Num()); ++i)
		{
			G.Add(Quick[i]);
		}
		MakeSquad(G, FString::Printf(TEXT("Reaction %d"), g / 6 + 1), true, 25.f);
	}
	// the watch, by where they are (the same deck, the same stretch of the ship)
	Awake.Sort([](const FMarine& A, const FMarine& B) { return FMath::RoundToInt(A.Pos.Z / 400.0) != FMath::RoundToInt(B.Pos.Z / 400.0) ? A.Pos.Z < B.Pos.Z : A.Pos.X < B.Pos.X; });
	for (int32 g = 0; g < Awake.Num(); g += 4)
	{
		TArray<FMarine> G;
		for (int32 i = g; i < FMath::Min(g + 4, Awake.Num()); ++i)
		{
			G.Add(Awake[i]);
		}
		MakeSquad(G, FString::Printf(TEXT("Watch %d"), ++SquadNo), false, 0.f);
	}
	// the ones who have to arm or wake first (they come in as their time goes)
	Roused.Sort([](const FMarine& A, const FMarine& B) { return FMath::RoundToInt(A.Pos.Z / 400.0) != FMath::RoundToInt(B.Pos.Z / 400.0) ? A.Pos.Z < B.Pos.Z : A.Pos.X < B.Pos.X; });
	int32 Reserve = 0;
	for (int32 g = 0; g < Roused.Num(); g += 5)
	{
		TArray<FMarine> G;
		for (int32 i = g; i < FMath::Min(g + 5, Roused.Num()); ++i)
		{
			G.Add(Roused[i]);
		}
		MakeSquad(G, FString::Printf(TEXT("Reserve %d"), ++Reserve), false, 0.f);
	}
	UE_LOG(LogASTRA, Log, TEXT("[Board] %d marines called: %d in the reaction team, %d on their feet, %d to wake or arm"), MarineUnits.Num(), Quick.Num(), Awake.Num(), Roused.Num());
}

bool UAstraBoardSubsystem::StartBoarding(const FSpec& Spec, FString& OutDetail)
{
	if (!IsReady() || !Map.IsValid())
	{
		OutDetail = TEXT("the ship's plan is not read yet");
		return false;
	}
	if (Phase == EPhase::Active)
	{
		OutDetail = TEXT("a boarding is already on");
		return false;
	}
	int32 BreachComp = INDEX_NONE;
	FVector At;
	FString Why;
	if (!PickBreach(Spec.Breach, BreachComp, At, Why))
	{
		OutDetail = Why;
		return false;
	}
	const int32* Obj = Dmg->CompByName.Find(FName(TEXT("engineering")));
	if (!Obj)
	{
		OutDetail = TEXT("the plan has no Main Engineering for the boarders to go for");
		return false;
	}
	// a clean slate (the last boarding's bodies, seals, marines)
	if (Phase == EPhase::Over)
	{
		Finish(TEXT("a new boarding begins"));
	}
	ClearBodies();
	Fight.Init(Map.ToSharedRef(), GAstraDeterministic ? 7001 : (int32)(FDateTime::Now().GetTicks() & 0x7fffffff));
	const int32 Count = FMath::Clamp(Spec.Boarders > 0 ? Spec.Boarders : FMath::Max(1, Spec.Skiffs) * 10, 4, 40);
	Fight.SpawnBoarders(BreachComp, At, *Obj, Count, FMath::Max(5.f, Spec.WarnS));
	MobiliseMarines();
	FVector Feet;
	float Yaw = 0.f, Speed = 0.f;
	bool bLow = false;
	if (!CaptainFeet(Feet, Yaw, bLow, Speed))
	{
		Feet = FVector(0.0, 0.0, -1.0e7);
	}
	Fight.AddCaptain(Feet);
	MakeSightOverride();
	Source = Spec.Source;
	BreachAt = At;
	BreachText = Map->Describe(BreachComp);
	Since = 0.f;
	AfterEnd = 0.f;
	bBreachOpen = false;
	WarnLeft = FMath::Max(5.f, Spec.WarnS);
	CapHp = 100.f;
	bCapDown = false;
	bChainDown = false;
	CapBleedS = 0.f;
	ThreatCm = -1.f;
	bToldContact = false;
	bToldTakeover = false;
	TakeoverFuse = -1.f;
	CasualtyT = 0.f;
	ToldMarinesLost = ToldMandateLost = 0;
	HarmTold.Reset();
	ToldDown.Reset();
	Log.Reset();
	LastShotSound.Reset();
	SoundBudget = 12.f;
	if (!bWarmed)
	{
		bWarmed = true;
		AAstraCombatant::PreloadAssets(Warm);
	}
	if (Spec.bLockdown)
	{
		SealSections(BreachComp, At);
	}
	// the ship goes to general quarters
	UAstraShipSubsystem* S = ShipSub();
	if (S)
	{
		PriorAlert = (int32)S->GetAlert();
		if (S->GetAlert() != EAstraAlert::Red)
		{
			FString D;
			S->ApplyCommand(TEXT("set_alert"), BdArgs1(TEXT("level"), TEXT("red")), D);
			bRaisedAlert = true;
		}
		else
		{
			bRaisedAlert = false;
		}
	}
	const int32 Skiffs = FMath::Max(1, FMath::DivideAndRoundUp(Count, 10));
	Phase = EPhase::Active;
	Tell(FString::Printf(TEXT("%s has docked %d assault craft on the hull at %s: about %d boarders, going for Main Engineering; the section bulkheads are %s and the marines are being called to arms"),
	                     Source.IsEmpty() ? TEXT("an enemy ship") : *Source, Skiffs, *BreachText, Count, Spec.bLockdown ? TEXT("closing") : TEXT("open")), true);
	OutDetail = FString::Printf(TEXT("boarding: %d boarders at %s, the marines called (%d)"), Count, *BreachText, MarineUnits.Num());
	UE_LOG(LogASTRA, Log, TEXT("[Board] %s"), *OutDetail);
	return true;
}

void UAstraBoardSubsystem::EndBoarding(const TCHAR* Why)
{
	if (Phase == EPhase::Active)
	{
		Tell(FString::Printf(TEXT("the boarding is called off (%s)"), Why), false);
		Finish(Why);
	}
}

void UAstraBoardSubsystem::Finish(const TCHAR* Why)
{
	if (Phase == EPhase::Idle || Phase == EPhase::Loading || Phase == EPhase::Failed)
	{
		return;
	}
	UE_LOG(LogASTRA, Log, TEXT("[Board] over: %s"), Why);
	UAstraLifeSubsystem* L = LifeSub();
	UAstraShipSubsystem* S = ShipSub();
	// the wounded who are still alive are carried to the Medbay; the able go back to their duty; the fallen are told
	for (const int32 U : MarineUnits)
	{
		const FUnit* Un = Fight.Unit(U);
		const int32* R = RosterOfUnit.Find(U);
		const int32* P = PersonOfUnit.Find(U);
		if (!Un || !R)
		{
			continue;
		}
		if (Un->Act == EAct::Down && !HarmTold.Contains(*R))
		{
			Fight.CarryOut(U);
			if (S)
			{
				S->HarmPerson(*R, false, TEXT("gunfire"));
			}
			HarmTold.Add(*R);
		}
		if (L && P)
		{
			L->Sim().Commandeer(*P, false, Un->Pos);
		}
	}
	if (Phase == EPhase::Active)
	{
		OpenSections();
	}
	if (S && bRaisedAlert && S->GetAlert() == EAstraAlert::Red)
	{
		FString D;
		S->ApplyCommand(TEXT("set_alert"), BdArgs1(TEXT("level"), PriorAlert == (int32)EAstraAlert::Green ? TEXT("green") : TEXT("yellow")), D);
	}
	bRaisedAlert = false;
	if (Breach && Breach->IsOpen())
	{
		Breach->Close();
	}
	// the Captain is whole again for the next one (the wound he carried is the damage model's; the weapon's screen has nothing to say)
	CapHp = FMath::Max(CapHp, 35.f);
	Phase = EPhase::Over;
	AfterEnd = 0.f;
}

void UAstraBoardSubsystem::ClearBodies()
{
	TArray<int32> Units;
	BodyOf.GetKeys(Units);
	for (const int32 U : Units)
	{
		ReleaseBody(U);
	}
	BodyOf.Reset();
}

// ================================================================================================================== the Captain

bool UAstraBoardSubsystem::CaptainFeet(FVector& OutFeet, float& OutYaw, bool& bOutLow, float& OutSpeed) const
{
	APlayerController* PC = GetWorld() ? UGameplayStatics::GetPlayerController(GetWorld(), 0) : nullptr;
	const ACharacter* Walker = PC ? Cast<ACharacter>(PC->GetPawn()) : nullptr;
	if (!Walker || !Walker->GetCapsuleComponent())
	{
		return false;                                 // in a Falcon, in a pod: out of the fight
	}
	OutFeet = Walker->GetActorLocation() - FVector(0.0, 0.0, Walker->GetCapsuleComponent()->GetScaledCapsuleHalfHeight());
	OutYaw = PC->GetControlRotation().Yaw;
	const AASTRACharacter* AC = Cast<AASTRACharacter>(Walker);
	bOutLow = AC && AC->GetPosture() != EAstraPosture::Standing;
	OutSpeed = (float)Walker->GetVelocity().Size2D();
	return true;
}

void UAstraBoardSubsystem::SyncCaptain(float Dt)
{
	FVector Feet;
	float Yaw = 0.f, Speed = 0.f;
	bool bLow = false;
	bCaptainIn = CaptainFeet(Feet, Yaw, bLow, Speed);
	if (!bCaptainIn)
	{
		Fight.SetCaptain(FVector(0.0, 0.0, -1.0e7), 0.f, false, 0.f, bCapDown);
		ThreatCm = -1.f;
		return;
	}
	Fight.SetCaptain(Feet, Yaw, bLow, Speed, bCapDown);
	// the nearest able boarder who sees the Captain (every quarter second)
	ThreatT -= Dt;
	if (ThreatT <= 0.f)
	{
		ThreatT = 0.25f;
		const FUnit* C = Fight.Unit(Fight.CaptainId());
		float Best = -1.f;
		if (C)
		{
			for (const FUnit& U : Fight.Units())
			{
				if (U.Side != ESide::Mandate || !U.Able() || U.bExternal || FMath::Abs(U.Pos.Z - C->Pos.Z) > 300.f)
				{
					continue;
				}
				const float D = (float)FVector::Dist(U.Pos, C->Pos);
				if (D < 4500.f && (Best < 0.f || D < Best) && Fight.Sees(U.Eye(), C->Eye()))
				{
					Best = D;
				}
			}
		}
		ThreatCm = Best;
	}
}

void UAstraBoardSubsystem::OnCaptainHit(const FBoardEvent& E)
{
	if (bCapDown)
	{
		return;
	}
	const float Real = E.Dmg * BdCaptainArmor;
	CapHp -= Real;
	CapHurtAt = GetWorld() ? GetWorld()->GetTimeSeconds() : 0.0;
	CapHurtAmount = Real;
	if (const FUnit* Shooter = Fight.Unit(E.Target))
	{
		CapHurtFrom = Shooter->Pos + FVector(0.f, 0.f, 150.f);
	}
	if (const APlayerController* PC = GetWorld() ? UGameplayStatics::GetPlayerController(GetWorld(), 0) : nullptr)
	{
		if (UAstraFpsComponent* F = PC->GetPawn() ? PC->GetPawn()->FindComponentByClass<UAstraFpsComponent>() : nullptr)
		{
			F->OnHurt(CapHurtFrom, Real);
		}
	}
	if (UAstraCombatFx* X = FxSub())
	{
		X->PlaySoundAt(TEXT("/Game/ASTRA/Audio/SW_Body_Hit.SW_Body_Hit"), CapHurtFrom, 0.9f, FMath::FRandRange(0.8f, 0.95f));
	}
}

void UAstraBoardSubsystem::CaptainFate(float Dt)
{
	UAstraShipSubsystem* S = ShipSub();
	if (!S || !bCaptainIn)
	{
		return;
	}
	FAstraDamageModel& M = S->GetInterior();
	const int32 Fate = S->GetCaptainFate();
	if (!bCapDown)
	{
		// the wound is the damage model's trauma: the screen's tunnel and the faint come from it; and a Captain who has not been hit for a while recovers a little
		if (SinceCaptainHurt() > 25.0 && CapHp < 100.f && Fate == 0)
		{
			CapHp = FMath::Min(100.f, CapHp + 0.12f * Dt);
		}
		if (CapHp < 100.f)
		{
			M.CaptainWounded(12.f * (1.f - FMath::Clamp(CapHp, 0.f, 100.f) / 100.f), TEXT("gunfire"));
		}
		if (CapHp <= 0.f)
		{
			bCapDown = true;
			CapBleedS = FMath::FRandRange(85.f, 135.f);
			M.CaptainWounded(14.f, TEXT("gunfire"));
			Tell(TEXT("the Captain is down"), true);
		}
		return;
	}
	// down: the chain of the ship carries the Captain out when it is safe to (the damage model's: a team reaches them) or the boarders' fire kills them
	const bool bThreat = ThreatCm >= 0.f && ThreatCm < 3200.f;
	M.CaptainContested(bThreat);
	bChainDown |= Fate == 1;
	if (bChainDown && Fate == 0)
	{
		bCapDown = false;                              // carried out and awake in the Medbay: winded, hurt
		bChainDown = false;
		CapHp = 35.f;
		M.CaptainWounded(12.f * (1.f - CapHp / 100.f), TEXT("gunfire"));
		Tell(TEXT("the Captain was carried out alive"), false);
		return;
	}
	if (Fate == 2)
	{
		return;                                        // the end is the chain's (THE CAPTAIN IS LOST)
	}
	if ((CapBleedS -= Dt) <= 0.f)
	{
		M.CaptainDied(FString::Printf(TEXT("bled out from gunshot wounds in %s"), Map.IsValid() ? *Map->Describe(Map->CompAt(Fight.Unit(Fight.CaptainId()) ? Fight.Unit(Fight.CaptainId())->Pos : FVector::ZeroVector)) : TEXT("the corridor")));
	}
}

// ================================================================================================================== the step

void UAstraBoardSubsystem::Tick(float DeltaTime)
{
	SCOPE_CYCLE_COUNTER(STAT_AstraBoarding);
	Super::Tick(DeltaTime);
	if (Phase == EPhase::Loading)
	{
		TryFinishLoading();
		return;
	}
	if (Phase != EPhase::Active && Phase != EPhase::Over)
	{
		return;
	}
	const float Dt = FMath::Min(DeltaTime, 0.1f);
	TracesLeft = 6;
	SoundBudget = FMath::Min(20.f, SoundBudget + Dt * 30.f);
	if (TakeoverFuse >= 0.f)
	{
		TakeoverFuse -= Dt;
		if (TakeoverFuse < 0.f)
		{
			Tell(TEXT("Main Engineering is lost: the reactor's containment is failing"), true);
			if (UAstraShipSubsystem* S = ShipSub())
			{
				S->ReactorFailing();
			}
		}
	}
	DrawDebug();
	if (Phase == EPhase::Active)
	{
		Step(Dt);
	}
	else
	{
		AfterEnd += Dt;
		// the bodies of the fallen stay a while, then the deck is cleared
		for (const auto& KV : BodyOf)
		{
			if (const FUnit* U = Fight.Unit(KV.Key))
			{
				KV.Value->Drive(*U, Dt);
			}
		}
		ManageBodies(Dt);
		if (AfterEnd > BdCleanUpS)
		{
			ClearBodies();
			Phase = EPhase::Idle;
		}
	}
}

void UAstraBoardSubsystem::Step(float Dt)
{
	Since += Dt;
	SyncCaptain(Dt);
	Fight.Tick(Dt);
	SyncLife();
	ProcessEvents(Dt);
	CaptainFate(Dt);
	for (const auto& KV : BodyOf)
	{
		if (const FUnit* U = Fight.Unit(KV.Key))
		{
			KV.Value->Drive(*U, Dt);
		}
	}
	ManageBodies(Dt);
	if (Fight.Over())
	{
		OnOutcome();
	}
}

void UAstraBoardSubsystem::SyncLife()
{
	// the marines' places go back to VITA's people, so that what the damage model asks of them (who stands in a room that burns) and what a hit finds is true
	UAstraLifeSubsystem* L = LifeSub();
	if (!L || !L->IsRunning())
	{
		return;
	}
	for (const int32 U : MarineUnits)
	{
		const FUnit* Un = Fight.Unit(U);
		const int32* P = PersonOfUnit.Find(U);
		if (Un && P && Un->Act != EAct::Waiting && Un->Act != EAct::Gone)
		{
			L->Sim().Commandeer(*P, true, Un->Pos);
		}
	}
}

AAstraCombatant* UAstraBoardSubsystem::TakeBody(int32 Side)
{
	for (AAstraCombatant* B : PoolOf(Side))
	{
		if (B && !B->InUse())
		{
			return B;
		}
	}
	if (PoolOf(Side).Num() >= 30 || !GetWorld())
	{
		return nullptr;
	}
	FActorSpawnParameters P;
	P.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	AAstraCombatant* B = GetWorld()->SpawnActor<AAstraCombatant>(FVector(0.0, 0.0, -1.0e6), FRotator::ZeroRotator, P);
	if (B)
	{
		PoolOf(Side).Add(B);
	}
	return B;
}

void UAstraBoardSubsystem::ReleaseBody(int32 Unit)
{
	if (TObjectPtr<AAstraCombatant>* B = BodyOf.Find(Unit))
	{
		if (*B)
		{
			(*B)->Unbind();
		}
		BodyOf.Remove(Unit);
	}
}

void UAstraBoardSubsystem::ManageBodies(float Dt)
{
	BodyT -= Dt;
	if (BodyT > 0.f)
	{
		return;
	}
	BodyT = 0.25f;
	UWorld* W = GetWorld();
	if (!W || !FApp::CanEverRender())
	{
		return;
	}
	const APlayerCameraManager* Cam = UGameplayStatics::GetPlayerCameraManager(W, 0);
	if (!Cam)
	{
		return;
	}
	const FVector Eye = Cam->GetCameraLocation();
	struct FCand { int32 U; float Score; };
	TArray<FCand> Cand;
	for (const FUnit& U : Fight.Units())
	{
		if (U.bExternal || U.Act == EAct::Waiting || U.Act == EAct::Gone)
		{
			continue;
		}
		if (FMath::Abs(U.Pos.Z + 90.f - Eye.Z) > 520.f)
		{
			continue;                                  // another deck
		}
		const float D = (float)FVector::Dist2D(U.Pos, Eye);
		const bool bHas = BodyOf.Contains(U.Id);
		if (D > (bHas ? BdBodyKeepCm : BdBodyReachCm) || ((U.Act == EAct::Dead || U.Act == EAct::Down) && D > 3800.f && !bHas))
		{
			continue;
		}
		Cand.Add({U.Id, bHas ? D * 0.7f : D});
	}
	Cand.Sort([](const FCand& A, const FCand& B) { return A.Score < B.Score; });
	TSet<int32> Want;
	for (int32 i = 0; i < Cand.Num() && i < BdMaxBodies; ++i)
	{
		Want.Add(Cand[i].U);
	}
	TArray<int32> Drop;
	for (const auto& KV : BodyOf)
	{
		if (!Want.Contains(KV.Key))
		{
			Drop.Add(KV.Key);
		}
	}
	for (const int32 U : Drop)
	{
		ReleaseBody(U);
	}
	int32 Made = 0;
	for (const int32 Id : Want)
	{
		if (BodyOf.Contains(Id) || Made >= 4)
		{
			continue;
		}
		const FUnit* U = Fight.Unit(Id);
		if (!U)
		{
			continue;
		}
		AAstraCombatant* B = TakeBody(U->Side == ESide::Mandate ? 1 : 0);
		if (!B)
		{
			continue;
		}
		bool bFemale = false;
		if (U->Roster != INDEX_NONE && ShipSub() && ShipSub()->GetRoster().Get().IsValidIndex(U->Roster))
		{
			bFemale = ShipSub()->GetRoster().Get()[U->Roster].bFemale;
		}
		else
		{
			bFemale = (Id % 5) == 2;                  // a few of the boarders are women
		}
		B->Bind(Id, U->Side == ESide::Mandate, U->Name, bFemale, U->Roster, U->Pos, U->Yaw);
		BodyOf.Add(Id, B);
		B->Drive(*U, 0.f);
		++Made;
	}
}

FString UAstraBoardSubsystem::NameOf(const FUnit& U) const
{
	return U.Name;
}

FString UAstraBoardSubsystem::PlaceOf(const FUnit& U) const
{
	return Map.IsValid() ? Map->Describe(U.Comp) : FString(TEXT("somewhere aboard"));
}

bool UAstraBoardSubsystem::PlayerHit(AAstraCombatant* Who, float Damage, bool bHead, const FVector& From)
{
	if (!Who || Phase != EPhase::Active || Who->UnitId() == INDEX_NONE)
	{
		return false;
	}
	const FUnit* U = Fight.Unit(Who->UnitId());
	if (!U || !U->Able())
	{
		return false;
	}
	if (U->Side == ESide::Aquila && BdCVarFriendlyFire.GetValueOnGameThread() == 0)
	{
		return false;
	}
	Fight.HitUnit(Who->UnitId(), Damage, bHead, TEXT("the Captain"));
	Who->NoteHit(From);
	return true;
}
