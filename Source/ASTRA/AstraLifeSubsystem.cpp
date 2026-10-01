// ASTRA — VITA in the world (see AstraLifeSubsystem.h).

#include "AstraLifeSubsystem.h"

#include "ASTRA.h"
#include "Async/Async.h"
#include "AstraLifeBody.h"
#include "AstraShipPlan.h"
#include "AstraShipSubsystem.h"
#include "Camera/PlayerCameraManager.h"
#include "Engine/World.h"
#include "GameFramework/Character.h"
#include "GameFramework/PlayerController.h"
#include "HAL/IConsoleManager.h"
#include "Kismet/GameplayStatics.h"
#include "Misc/App.h"

DECLARE_CYCLE_STAT(TEXT("Life"), STAT_AstraLife, STATGROUP_Astra);
DECLARE_CYCLE_STAT(TEXT("LifeBodies"), STAT_AstraLifeBodies, STATGROUP_Astra);
DECLARE_DWORD_COUNTER_STAT(TEXT("LifeBodyCount"), STAT_AstraLifeBodyCount, STATGROUP_Astra);
DECLARE_DWORD_COUNTER_STAT(TEXT("LifeWalking"), STAT_AstraLifeWalking, STATGROUP_Astra);

namespace
{
	constexpr int32 LifeSeed = 2491;      // the roster's: the same people serve in every game

	UAstraLifeSubsystem* LifeOf(UWorld* W) { return W ? W->GetSubsystem<UAstraLifeSubsystem>() : nullptr; }

	FAutoConsoleCommandWithWorld CmdInfo(TEXT("astra.life.info"), TEXT("VITA: the clock, who is doing what, the bodies, what the simulation costs"),
		FConsoleCommandWithWorldDelegate::CreateLambda([](UWorld* W)
		{
			if (UAstraLifeSubsystem* L = LifeOf(W))
			{
				UE_LOG(LogASTRA, Log, TEXT("[Life] %s"), *L->InfoText());
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdWho(TEXT("astra.life.who"), TEXT("VITA: astra.life.who <roster number | part of a name>: one person, what they do and remember"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& A, UWorld* W)
		{
			UAstraLifeSubsystem* L = LifeOf(W);
			const UAstraShipSubsystem* Ship = W ? W->GetSubsystem<UAstraShipSubsystem>() : nullptr;
			if (!L || !L->IsRunning() || !Ship || A.Num() == 0)
			{
				return;
			}
			const FString Q = FString::Join(A, TEXT(" "));
			for (int32 i = 0; i < L->Sim().NumPeople(); ++i)
			{
				const FAstraCrewman& R = Ship->GetRoster().Get()[L->Sim().Person(i).Roster];
				if (FCString::Atoi(*Q) == i && Q.IsNumeric() || R.Name().Contains(Q, ESearchCase::IgnoreCase))
				{
					const FAstraLifePerson& P = L->Sim().Person(i);
					UE_LOG(LogASTRA, Log, TEXT("[Life] #%d %s (%s, %s watch): %s; at %s%s"), i, *R.Name(), *R.Dept, L->Sim().WatchName(P.Watch), *L->Sim().Doing(i),
					       *L->Sim().Where(i), L->BodyOfRoster(P.Roster) ? TEXT(" [has a body]") : TEXT(""));
					for (const FAstraLifeMemory& M : P.Mem)
					{
						UE_LOG(LogASTRA, Log, TEXT("[Life]    remembers: %s"), *L->Sim().MemoryLine(M));
					}
				}
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdHour(TEXT("astra.life.hour"), TEXT("VITA: astra.life.hour <0..24>: the ship's hour (everyone goes where the schedule puts them)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& A, UWorld* W)
		{
			if (UAstraLifeSubsystem* L = LifeOf(W); L && L->IsRunning() && A.Num())
			{
				L->SetShipHour(FCString::Atof(*A[0]));
				UE_LOG(LogASTRA, Log, TEXT("[Life] %s"), *L->InfoText());
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdScale(TEXT("astra.life.scale"), TEXT("VITA: astra.life.scale <ship seconds per second>: how fast the ship's day goes"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& A, UWorld* W)
		{
			if (UAstraLifeSubsystem* L = LifeOf(W); L && A.Num())
			{
				L->SetTimeScale(FCString::Atof(*A[0]));
			}
		}));
}

bool UAstraLifeSubsystem::ShouldCreateSubsystem(UObject* Outer) const
{
	const UWorld* World = Cast<UWorld>(Outer);
	return World && (World->WorldType == EWorldType::Game || World->WorldType == EWorldType::PIE);
}

void UAstraLifeSubsystem::OnWorldBeginPlay(UWorld& InWorld)
{
	Super::OnWorldBeginPlay(InWorld);
	State = EState::Loading;
	// the plan's rooms and the tables of life are read on a worker: the game does not wait for them
	MapFuture = Async(EAsyncExecution::ThreadPool, []() -> TSharedPtr<FAstraLifeMap>
	{
		TSharedPtr<FAstraLifeMap> M = MakeShared<FAstraLifeMap>();
		FString Err;
		if (!M->Load(Err))
		{
			UE_LOG(LogASTRA, Log, TEXT("[Life] %s: nobody walks the ship"), *Err);
			return nullptr;
		}
		return M;
	});
}

void UAstraLifeSubsystem::Deinitialize()
{
	if (State == EState::Loading)
	{
		MapFuture.Wait();
	}
	ReleaseAllBodies();
	Pool.Reset();
	Super::Deinitialize();
}

void UAstraLifeSubsystem::TryStart()
{
	UWorld* W = GetWorld();
	Ship = W ? W->GetSubsystem<UAstraShipSubsystem>() : nullptr;
	Plan = W ? W->GetSubsystem<UAstraShipPlan>() : nullptr;
	if (!Ship.IsValid() || !Plan.IsValid() || Ship->GetRoster().Get().Num() == 0)
	{
		return;                                     // the ship is not up yet: next frame
	}
	if (!Plan->EnsureLoaded())
	{
		UE_LOG(LogASTRA, Log, TEXT("[Life] no ship's plan: nobody walks the ship"));
		State = EState::Failed;
		return;
	}
	TimeScale = MapPtr->TimeScale;
	Life.Init(MapPtr.ToSharedRef(), Ship->GetRoster(), LifeSeed, MapPtr->StartHour);
	Life.SetRouter([PlanRef = Plan](const FVector& From, const FVector& To, TArray<FVector>& Out)
	{
		const UAstraShipPlan* P = PlanRef.Get();
		return P && P->FindRoute(From, To, Out);
	});
	Life.SyncRoster(Ship->GetRoster());
	Life.SyncDamage(Ship->GetDamage());
	Life.SetAlert(Ship->GetAlert() == EAstraAlert::Red ? 2 : Ship->GetAlert() == EAstraAlert::Yellow ? 1 : 0);
	State = EState::Running;
	UE_LOG(LogASTRA, Log, TEXT("[Life] %d people aboard; the ship's clock %s, %s watch on duty, one ship hour every %.0f s"), Life.NumPeople(), *ClockText(), *WatchOnDuty(), 3600.f / FMath::Max(TimeScale, 0.01f));
}

void UAstraLifeSubsystem::Tick(float DeltaTime)
{
	SCOPE_CYCLE_COUNTER(STAT_AstraLife);
	if (State == EState::Loading)
	{
		if (!MapFuture.IsReady())
		{
			return;
		}
		MapPtr = MapFuture.Get();
		State = MapPtr.IsValid() ? EState::WaitRoster : EState::Failed;
	}
	if (State == EState::WaitRoster)
	{
		TryStart();
	}
	if (State != EState::Running)
	{
		return;
	}
	const double T0 = FPlatformTime::Seconds();
	// the ship speaks: the alarm at once, the wounded and the incidents twice a second
	UAstraShipSubsystem* S = Ship.Get();
	if (S)
	{
		const uint8 Level = S->GetAlert() == EAstraAlert::Red ? 2 : S->GetAlert() == EAstraAlert::Yellow ? 1 : 0;
		Life.SetAlert(Level);
		if ((PollT -= DeltaTime) <= 0.f)
		{
			PollT = 0.5f;
			Life.SyncRoster(S->GetRoster());
			if (bFeed)
			{
				Life.SyncDamage(S->GetDamage());
			}
		}
	}
	FVector Focus = FVector::ZeroVector;
	if (bTestCaptain)
	{
		Focus = TestFeet;
		EyeCm = TestEye;
		LookDir = TestLook;
	}
	else
	{
		if (const APawn* Pawn = UGameplayStatics::GetPlayerPawn(this, 0))
		{
			Focus = Pawn->GetActorLocation();
		}
		if (const APlayerCameraManager* Cam = UGameplayStatics::GetPlayerCameraManager(this, 0))
		{
			EyeCm = Cam->GetCameraLocation();
			LookDir = Cam->GetCameraRotation().Vector();
		}
	}
	Life.Tick(DeltaTime, TimeScale, RouteBudgetS, Focus);
	const double SimMs = (FPlatformTime::Seconds() - T0) * 1000.0;
	Cost.SimMs = SimMs;
	Cost.SimMsAvg = Cost.SimMsAvg * 0.98 + SimMs * 0.02;
	Cost.SimMsMax = FMath::Max(Cost.SimMsMax * 0.9995, SimMs);
	++Cost.Ticks;
	if ((BodyT -= DeltaTime) <= 0.f)
	{
		BodyT = 0.25f;
		const double B0 = FPlatformTime::Seconds();
		ManageBodies();
		Cost.BodiesMs = (FPlatformTime::Seconds() - B0) * 1000.0;
		Cost.BodiesMsMax = FMath::Max(Cost.BodiesMsMax * 0.998, Cost.BodiesMs);
	}
	PrewarmPool(DeltaTime);
	SET_DWORD_STAT(STAT_AstraLifeBodyCount, NumActiveBodies);
}

void UAstraLifeSubsystem::PrewarmPool(float DeltaTime)
{
	// The pool is made one body at a time, a few times a second, while the Captain is still on the bridge: nobody sees a body being spawned,
	// no frame carries more than one, and a lift's arrival finds them ready. A frame that is already long (a level streaming, a hitch) waits.
	if (!MapPtr.IsValid() || (!FApp::CanEverRender() && !bTestCaptain) || Pool.Num() >= MapPtr->Vis.MaxBodies || !GetWorld())
	{
		return;
	}
	if ((PrewarmT -= DeltaTime) > 0.f || DeltaTime > 0.04f)
	{
		return;
	}
	PrewarmT = 0.12f;
	if (!bWarmed)
	{
		bWarmed = true;
		AAstraLifeBody::PreloadAssets(Warm);                 // (most are in memory already: the bridge's officers wear the same)
		return;
	}
	FActorSpawnParameters P;
	P.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	P.ObjectFlags |= RF_Transient;
	if (AAstraLifeBody* B = GetWorld()->SpawnActor<AAstraLifeBody>(FVector(0.f, 0.f, -2.0e5), FRotator::ZeroRotator, P))
	{
		B->SetActorHiddenInGame(true);
		Pool.Add(B);
	}
}

// ====================================================================================================== the clock

FString UAstraLifeSubsystem::ClockText() const
{
	return IsRunning() ? FString::Printf(TEXT("day %d %s"), Life.DayNumber() + 1, *FAstraLifeSim::HourText(Life.ShipSeconds())) : FString(TEXT("(no life yet)"));
}

FString UAstraLifeSubsystem::WatchOnDuty() const
{
	if (!IsRunning())
	{
		return FString();
	}
	// the watch whose duty block began last (they are at their posts now)
	const float H = Life.Hour();
	int32 Best = 0;
	float BestAge = 100.f;
	for (int32 W = 0; W < MapPtr->Watches.Num(); ++W)
	{
		const float Age = FMath::Fmod(H - MapPtr->Watches[W].Start + 24.f, 24.f);
		if (Age < 8.f && Age < BestAge)
		{
			BestAge = Age;
			Best = W;
		}
	}
	return MapPtr->Watches.IsValidIndex(Best) ? MapPtr->Watches[Best].Name : FString();
}

void UAstraLifeSubsystem::SetShipHour(float Hour)
{
	if (IsRunning())
	{
		ReleaseAllBodies();
		Life.SetHour(FMath::Fmod(Hour, 24.f));
	}
}

// ====================================================================================================== the minds

TSharedRef<FJsonObject> UAstraLifeSubsystem::PersonJson(int32 Person) const
{
	TSharedRef<FJsonObject> O = MakeShared<FJsonObject>();
	const UAstraShipSubsystem* S = Ship.Get();
	if (!IsRunning() || !S || !Life.NumPeople() || Person < 0 || Person >= Life.NumPeople())
	{
		return O;
	}
	const FAstraLifePerson& P = Life.Person(Person);
	const FAstraCrewman& R = S->GetRoster().Get()[P.Roster];
	O->SetStringField(TEXT("id"), FString::Printf(TEXT("npc%d"), P.Roster));
	O->SetStringField(TEXT("name"), R.Name());
	O->SetStringField(TEXT("rank"), R.Rank);
	O->SetStringField(TEXT("gender"), R.bFemale ? TEXT("f") : TEXT("m"));
	O->SetStringField(TEXT("dept"), R.Dept);
	O->SetStringField(TEXT("home"), R.Home);
	O->SetStringField(TEXT("job"), P.Job);
	O->SetStringField(TEXT("watch"), Life.WatchName(P.Watch));
	O->SetStringField(TEXT("doing"), Life.Doing(Person));
	O->SetStringField(TEXT("place"), Life.Where(Person));
	TArray<TSharedPtr<FJsonValue>> Mem;
	for (int32 i = P.Mem.Num() - 1; i >= 0 && Mem.Num() < 6; --i)
	{
		Mem.Add(MakeShared<FJsonValueString>(Life.MemoryLine(P.Mem[i])));
	}
	O->SetArrayField(TEXT("memory"), Mem);
	TArray<TSharedPtr<FJsonValue>> Friends;
	for (const int32 F : P.Friends)
	{
		if (F != INDEX_NONE && Life.Person(F).Status != 2)
		{
			Friends.Add(MakeShared<FJsonValueString>(S->GetRoster().Get()[Life.Person(F).Roster].Name()));
		}
	}
	O->SetArrayField(TEXT("friends"), Friends);
	return O;
}

TArray<TSharedPtr<FJsonValue>> UAstraLifeSubsystem::ListenersJson(const FVector& Eye, const FVector& Look, int32 Max) const
{
	struct FHeard { float Score; float Dist; float Angle; const AAstraLifeBody* B; };
	TArray<FHeard> Heard;
	const APawn* Pawn = UGameplayStatics::GetPlayerPawn(this, 0);
	for (const TObjectPtr<AAstraLifeBody>& B : Pool)
	{
		if (!B || !B->InUse() || B->IsHidden())
		{
			continue;
		}
		const FVector Head = B->GetActorLocation() + FVector(0.f, 0.f, B->Posture == EAstraCrewPosture::Standing ? 70.f : 30.f);
		const float Dist = FVector::Dist(Eye, Head);
		if (Dist > 1600.f || !B->CanBeHeardFrom(Eye, Pawn))
		{
			continue;
		}
		const float Angle = FMath::RadiansToDegrees(FMath::Acos(FMath::Clamp(FVector::DotProduct(Look, (Head - Eye).GetSafeNormal()), -1.f, 1.f)));
		Heard.Add({Dist + Angle * 12.f, Dist, Angle, B});
	}
	Heard.Sort([](const FHeard& A, const FHeard& B) { return A.Score < B.Score; });
	TArray<TSharedPtr<FJsonValue>> Out;
	for (const FHeard& H : Heard)
	{
		if (Out.Num() >= Max)
		{
			break;
		}
		TSharedRef<FJsonObject> O = PersonJson(H.B->Person());
		O->SetNumberField(TEXT("dist_m"), FMath::RoundToInt(H.Dist / 10.f) / 10.0);
		O->SetNumberField(TEXT("angle_deg"), FMath::RoundToInt(H.Angle));
		O->SetBoolField(TEXT("facing"), H.Dist < 1000.f && H.Angle < 22.f);
		Out.Add(MakeShared<FJsonValueObject>(O));
	}
	return Out;
}

TSharedRef<FJsonObject> UAstraLifeSubsystem::SnapshotJson() const
{
	TSharedRef<FJsonObject> O = MakeShared<FJsonObject>();
	if (!IsRunning())
	{
		return O;
	}
	O->SetStringField(TEXT("clock"), FAstraLifeSim::HourText(Life.ShipSeconds()));
	O->SetNumberField(TEXT("day"), Life.DayNumber() + 1);
	O->SetStringField(TEXT("watch_on_duty"), WatchOnDuty());
	FAstraLifeStats St;
	Life.Stats(St);
	TSharedRef<FJsonObject> Co = MakeShared<FJsonObject>();
	Co->SetNumberField(TEXT("asleep"), St.PerAct[(int32)EAstraLifeAct::Sleep]);
	Co->SetNumberField(TEXT("on_duty"), St.PerAct[(int32)EAstraLifeAct::Duty]);
	Co->SetNumberField(TEXT("at_meals"), St.PerAct[(int32)EAstraLifeAct::Meal]);
	Co->SetNumberField(TEXT("off_duty"), St.PerAct[(int32)EAstraLifeAct::Leisure]);
	Co->SetNumberField(TEXT("at_battle_stations"), St.PerAct[(int32)EAstraLifeAct::Battle]);
	Co->SetNumberField(TEXT("in_repair_parties"), St.PerAct[(int32)EAstraLifeAct::Repair]);
	Co->SetNumberField(TEXT("wounded"), St.PerAct[(int32)EAstraLifeAct::Patient]);
	O->SetObjectField(TEXT("company"), Co);
	// the damage-control parties: where they are and what they are doing (the ship's own model says how the repair goes)
	TArray<TSharedPtr<FJsonValue>> Parties;
	const UAstraShipSubsystem* S = Ship.Get();
	for (const FAstraLifeParty& Pt : Life.Parties())
	{
		TSharedRef<FJsonObject> P = MakeShared<FJsonObject>();
		P->SetNumberField(TEXT("incident"), Pt.Incident);
		P->SetNumberField(TEXT("team"), Pt.ShipTeam + 1);
		P->SetStringField(TEXT("kind"), Pt.Kind);
		P->SetStringField(TEXT("where"), Life.GetMap().Describe(Pt.SiteComp));
		P->SetStringField(TEXT("state"), Pt.State == FAstraLifeParty::EState::Working ? TEXT("working") : Pt.State == FAstraLifeParty::EState::EnRoute ? TEXT("on the way") : TEXT("mustering"));
		P->SetNumberField(TEXT("members"), Pt.Members.Num());
		if (Pt.Members.Num() && S)
		{
			FVector C = FVector::ZeroVector;
			for (const int32 M : Pt.Members)
			{
				C += Life.Person(M).Pos;
			}
			C /= Pt.Members.Num();
			P->SetStringField(TEXT("now"), Life.GetMap().Describe(Life.GetMap().CompartmentAt(C + FVector(0, 0, 30))));
			P->SetStringField(TEXT("leader"), S->GetRoster().Get()[Life.Person(Pt.Members[0]).Roster].Name());
		}
		Parties.Add(MakeShared<FJsonValueObject>(P));
	}
	O->SetArrayField(TEXT("repair_parties"), Parties);
	// the people within earshot of the Captain
	if (const APlayerCameraManager* Cam = UGameplayStatics::GetPlayerCameraManager(this, 0))
	{
		O->SetArrayField(TEXT("people_near"), ListenersJson(Cam->GetCameraLocation(), Cam->GetCameraRotation().Vector(), 6));
	}
	return O;
}

TArray<int32> UAstraLifeSubsystem::RosterIn(int32 Deck, TCHAR Section) const
{
	TArray<int32> Out, People;
	if (IsRunning())
	{
		Life.PeopleIn(Deck, Section, People);
		for (const int32 P : People)
		{
			Out.Add(Life.Person(P).Roster);
		}
	}
	return Out;
}

FString UAstraLifeSubsystem::InfoText() const
{
	if (!IsRunning())
	{
		return FString::Printf(TEXT("not running (%s)"), State == EState::Loading ? TEXT("loading the plan") : State == EState::WaitRoster ? TEXT("waiting for the roster") : TEXT("failed or idle"));
	}
	FAstraLifeStats St;
	Life.Stats(St);
	return FString::Printf(TEXT("%s (%s watch on duty, %.0f ship s per s) | %d asleep, %d on duty, %d at meals, %d off duty, %d at battle stations, %d repairing, %d wounded | %d walking, %d waiting for a route | "
	                            "routes %d (%d failed, %.3f ms avg, %.2f max) | %d bodies | sim %.3f ms avg (max %.2f), bodies' manager %.3f ms"),
	                       *ClockText(), *WatchOnDuty(), TimeScale, St.PerAct[(int32)EAstraLifeAct::Sleep], St.PerAct[(int32)EAstraLifeAct::Duty], St.PerAct[(int32)EAstraLifeAct::Meal],
	                       St.PerAct[(int32)EAstraLifeAct::Leisure], St.PerAct[(int32)EAstraLifeAct::Battle], St.PerAct[(int32)EAstraLifeAct::Repair], St.PerAct[(int32)EAstraLifeAct::Patient],
	                       St.Walking, St.Waiting, St.Routes, St.RouteFails, St.Routes ? St.RouteMs / St.Routes : 0.0, St.RouteMsMax, NumActiveBodies, Cost.SimMsAvg, Cost.SimMsMax, Cost.BodiesMs);
}

// ====================================================================================================== the bodies

AAstraLifeBody* UAstraLifeSubsystem::BodyOfPerson(int32 Person) const
{
	const int32* I = BodyOf.Find(Person);
	return I && Pool.IsValidIndex(*I) ? Pool[*I].Get() : nullptr;
}

AAstraLifeBody* UAstraLifeSubsystem::BodyOfRoster(int32 RosterIdx) const
{
	const int32 P = Life.PersonOfRoster(RosterIdx);
	const int32* I = BodyOf.Find(P);
	return I && Pool.IsValidIndex(*I) ? Pool[*I].Get() : nullptr;
}

void UAstraLifeSubsystem::ReleaseBody(int32 Person)
{
	if (const int32* I = BodyOf.Find(Person))
	{
		if (Pool.IsValidIndex(*I) && Pool[*I])
		{
			Pool[*I]->Unbind();
		}
		BodyOf.Remove(Person);
		NumActiveBodies = BodyOf.Num();
	}
}

void UAstraLifeSubsystem::ReleaseAllBodies()
{
	for (const TObjectPtr<AAstraLifeBody>& B : Pool)
	{
		if (B && B->InUse())
		{
			B->Unbind();
		}
	}
	BodyOf.Reset();
	NumActiveBodies = 0;
}

AAstraLifeBody* UAstraLifeSubsystem::TakeBody(bool bFemale)
{
	// a free body that already wears the right mannequin first (changing a mesh is the costly part of becoming someone)
	AAstraLifeBody* Any = nullptr;
	for (const TObjectPtr<AAstraLifeBody>& B : Pool)
	{
		if (B && !B->InUse())
		{
			if (B->IsFemaleBody() == bFemale)
			{
				return B;
			}
			Any = Any ? Any : B.Get();
		}
	}
	if (Any)
	{
		return Any;
	}
	if (Pool.Num() >= MapPtr->Vis.MaxBodies + 4 || !GetWorld())
	{
		return nullptr;
	}
	FActorSpawnParameters P;
	P.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	P.ObjectFlags |= RF_Transient;
	AAstraLifeBody* B = GetWorld()->SpawnActor<AAstraLifeBody>(FVector(0.f, 0.f, -2.0e5), FRotator::ZeroRotator, P);
	if (B)
	{
		Pool.Add(B);
		B->SetActorHiddenInGame(true);
	}
	return B;
}

bool UAstraLifeSubsystem::CanAppearUnseen(const FVector& At) const
{
	// nobody pops into view: a body is made where the Captain is not looking (outside the frustum's width), or cannot see (a wall, a bulkhead),
	// or cannot make out (beyond 45 m); the people who are in plain view keep waiting until they are not
	const FVector Head = At + FVector(0.f, 0.f, 150.f);
	const FVector To = Head - EyeCm;
	const float D = (float)To.Size();
	if (D > 4500.f)
	{
		return true;
	}
	const FVector2D L(LookDir.X, LookDir.Y), T2(To.X, To.Y);
	if (!L.IsNearlyZero() && !T2.IsNearlyZero() && FVector2D::DotProduct(L.GetSafeNormal(), T2.GetSafeNormal()) < 0.42f)     // more than 65 degrees off the line of sight
	{
		return true;
	}
	if (UWorld* W = GetWorld())
	{
		FCollisionQueryParams Q(SCENE_QUERY_STAT(AstraLifeAppear), false);
		if (const APawn* Pawn = UGameplayStatics::GetPlayerPawn(this, 0))
		{
			Q.AddIgnoredActor(Pawn);
		}
		FHitResult Hit;
		return W->LineTraceSingleByChannel(Hit, EyeCm, Head, ECC_Visibility, Q);
	}
	return false;
}

void UAstraLifeSubsystem::ManageBodies()
{
	SCOPE_CYCLE_COUNTER(STAT_AstraLifeBodies);
	if ((!FApp::CanEverRender() && !bTestCaptain) || !MapPtr.IsValid())
	{
		return;
	}
	FVector Feet = TestFeet;
	if (!bTestCaptain)
	{
		const APawn* Pawn = UGameplayStatics::GetPlayerPawn(this, 0);
		const APlayerCameraManager* Cam = UGameplayStatics::GetPlayerCameraManager(this, 0);
		if (!Pawn || !Cam || !Pawn->IsA<ACharacter>())
		{
			ReleaseAllBodies();                          // the Captain is in a Falcon, a pod: nobody walks for them
			bCaptainSeen = false;
			return;
		}
		Feet = Pawn->GetActorLocation() - FVector(0.f, 0.f, Pawn->GetDefaultHalfHeight());
	}
	const FAstraLifeMap& Map = *MapPtr;
	if (!bCaptainSeen || FVector::Dist(Feet, LastCaptain) > 1500.f)
	{
		JumpGraceS = 1.6f;                               // a lift, a fade: nobody may be missing when the picture returns
	}
	const bool bJump = JumpGraceS > 0.f;
	JumpGraceS = FMath::Max(0.f, JumpGraceS - 0.25f);
	bCaptainSeen = true;
	LastCaptain = Feet;
	// the vertical band: a deck, or the whole height of a hall the Captain stands in
	float Band = Map.Vis.DeckBandCm;
	const int32 Here = Map.CompartmentAt(Feet + FVector(0.f, 0.f, 30.f));
	if (Map.Comps.IsValidIndex(Here) && Map.Comps[Here].bHall)
	{
		Band = FMath::Max(Band, Map.Comps[Here].Box.Max.Z - Map.Comps[Here].Box.Min.Z + 100.f);
	}
	const float Spawn2 = FMath::Square(Map.Vis.SpawnM * 100.f), Keep2 = FMath::Square(Map.Vis.DespawnM * 100.f);
	struct FCand { int32 P; float D2; float Score; };
	TArray<FCand> Cand;
	const FVector2D Look2(LookDir.X, LookDir.Y);
	const FVector2D LookN = Look2.GetSafeNormal();
	for (int32 i = 0; i < Life.NumPeople(); ++i)
	{
		const FAstraLifePerson& P = Life.Person(i);
		if (P.Status != 0 || P.Act == EAstraLifeAct::Dead)
		{
			continue;
		}
		const bool bSettled = P.Phase == FAstraLifePerson::EPhase::Settled;
		if (bSettled && (P.Act == EAstraLifeAct::Patient || (P.Place != INDEX_NONE && Map.Places[P.Place].External != NAME_None)))
		{
			continue;                                    // a pre-placed actor of the level is them (a Mess seat, a rack, a bed)
		}
		if (FMath::Abs(P.Pos.Z - Feet.Z) > Band)
		{
			continue;
		}
		const float D2 = (float)FVector::DistSquared2D(P.Pos, Feet);
		const bool bHas = BodyOf.Contains(i);
		if (D2 <= (bHas ? Keep2 : Spawn2))
		{
			// who has a body when there are more people than bodies: the nearest, but those who are in front of the Captain before those behind
			// (beyond a few metres), and whoever has one keeps it unless somebody is well nearer (nobody flickers at the edge of the cap)
			float Score = FMath::Sqrt(D2);
			if (Score > 600.f && !LookN.IsNearlyZero())
			{
				const FVector2D To = FVector2D(P.Pos.X - Feet.X, P.Pos.Y - Feet.Y).GetSafeNormal();
				if (FVector2D::DotProduct(To, LookN) < 0.35f)
				{
					Score *= 1.4f;
				}
			}
			Cand.Add({i, D2, bHas ? Score * 0.7f : Score});
		}
	}
	Cand.Sort([](const FCand& A, const FCand& B) { return A.Score < B.Score; });
	// the nearest that stand where the ship has been built (a person in a deck not yet modelled has nothing to stand on); one who has no body yet
	// waits while the Captain can see the place they stand (unless the Captain has just arrived: the fade covers it)
	TSet<int32> Want;
	int32 Traced = 0;
	for (const FCand& C : Cand)
	{
		if (Want.Num() >= Map.Vis.MaxBodies)
		{
			break;
		}
		const FAstraLifePerson& P = Life.Person(C.P);
		const int32 Room = Map.CompartmentAt(P.Pos + FVector(0.f, 0.f, 30.f));
		if (Room != INDEX_NONE && Map.Comps[Room].Status == EAstraRoomStatus::Planned)
		{
			continue;
		}
		if (!bJump && !BodyOf.Contains(C.P))
		{
			// (a few traces a call: the rest wait for the next)
			if (Traced >= 12 || !CanAppearUnseen(P.Pos))
			{
				++Traced;
				continue;
			}
			++Traced;
		}
		Want.Add(C.P);
	}
	// bodies whose people are no longer wanted go back to the pool, out of sight (one still in view stays until it is not)
	TArray<int32> Drop;
	for (const auto& KV : BodyOf)
	{
		const AAstraLifeBody* B = Pool.IsValidIndex(KV.Value) ? Pool[KV.Value].Get() : nullptr;
		if (!B || Life.Person(KV.Key).Status != 0)
		{
			Drop.Add(KV.Key);
		}
		else if (!Want.Contains(KV.Key) && (!B->SeenRecently(0.6f) || FVector::DistSquared2D(Life.Person(KV.Key).Pos, Feet) > Keep2 * 1.6f))
		{
			Drop.Add(KV.Key);
		}
	}
	for (const int32 P : Drop)
	{
		ReleaseBody(P);
	}
	// the new ones, nearest first; a few at a time unless the Captain has just arrived somewhere
	int32 Made = 0;
	for (const FCand& C : Cand)
	{
		if (!Want.Contains(C.P) || BodyOf.Contains(C.P))
		{
			continue;
		}
		if (Made >= (bJump ? 8 : 3))                     // (a body's making is a part of a frame: a few at a time, the nearest first)
		{
			break;
		}
		AAstraLifeBody* B = TakeBody(Life.Person(C.P).bFemale);
		if (!B)
		{
			break;
		}
		B->Bind(this, C.P);
		BodyOf.Add(C.P, Pool.IndexOfByKey(B));
		++Made;
	}
	NumActiveBodies = BodyOf.Num();
	int32 Walking = 0;
	for (const auto& KV : BodyOf)
	{
		Walking += Life.Person(KV.Key).Phase == FAstraLifePerson::EPhase::Walking ? 1 : 0;
	}
	SET_DWORD_STAT(STAT_AstraLifeWalking, Walking);
}
