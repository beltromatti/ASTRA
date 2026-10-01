// ASTRA — the ship's lifts (see AstraLiftSubsystem.h).

#include "AstraLiftSubsystem.h"

#include "ASTRA.h"
#include "Async/Async.h"
#include "AstraCrewMember.h"
#include "AstraDeckStreaming.h"
#include "AstraDoor.h"
#include "AstraLiftCar.h"
#include "Camera/PlayerCameraManager.h"
#include "Components/CapsuleComponent.h"
#include "Engine/Engine.h"
#include "Dom/JsonValue.h"
#include "Engine/Font.h"
#include "GameFramework/Character.h"
#include "HAL/IConsoleManager.h"
#include "Kismet/GameplayStatics.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"

DECLARE_CYCLE_STAT(TEXT("Lifts"), STAT_AstraLifts, STATGROUP_AstraLifts);
DECLARE_CYCLE_STAT(TEXT("Lifts slow"), STAT_AstraLiftsSlow, STATGROUP_AstraLifts);
DECLARE_DWORD_COUNTER_STAT(TEXT("CarsMoving"), STAT_AstraLiftsMoving, STATGROUP_AstraLifts);
DECLARE_DWORD_COUNTER_STAT(TEXT("Lines"), STAT_AstraLiftsLines, STATGROUP_AstraLifts);

namespace
{
	TAutoConsoleVariable<FString> LiftCVarPlan(TEXT("astra.lifts.plan"), TEXT(""),
		TEXT("The plan the lifts are read from (a path; empty: the ship's own, staged with the game or in data/ship). A test plan: data/ship/test/lifts_fixture.json"));
	TAutoConsoleVariable<int32> LiftCVarEnabled(TEXT("astra.lifts"), 1, TEXT("0: no lifts are built (a world that needs none)"));

	int32 LiftParkingStop(const FAstraLiftLine& L)
	{
		// the main landing: the bridge's deck, else Crew Services (the Mess and the berths), else the middle of the line
		int32 I = L.FindStopByDeck(1);
		I = I != INDEX_NONE ? I : L.FindStopByDeck(4);
		return I != INDEX_NONE ? I : L.Stops.Num() / 2;
	}
}

// ================================================================================================================================ the world

bool UAstraLiftSubsystem::ShouldCreateSubsystem(UObject* Outer) const
{
	const UWorld* World = Cast<UWorld>(Outer);
	return World && (World->WorldType == EWorldType::Game || World->WorldType == EWorldType::PIE);
}

void UAstraLiftSubsystem::OnWorldBeginPlay(UWorld& InWorld)
{
	Super::OnWorldBeginPlay(InWorld);
	TitleFont = LoadObject<UFont>(nullptr, TEXT("/Game/ASTRA/UI/Fonts/F_ASTRA_Title.F_ASTRA_Title"), nullptr, LOAD_NoWarn | LOAD_Quiet);
	MonoFont = LoadObject<UFont>(nullptr, TEXT("/Game/ASTRA/UI/Fonts/F_ASTRA_Mono.F_ASTRA_Mono"), nullptr, LOAD_NoWarn | LOAD_Quiet);
	if (IsRunningCommandlet() || LiftCVarEnabled.GetValueOnGameThread() == 0 || State != EState::Idle)
	{
		return;                       // a bench builds its own lifts (LoadNetwork, BuildNow)
	}
	FString Path = LiftCVarPlan.GetValueOnGameThread();
	if (Path.IsEmpty())
	{
		Path = FAstraLiftNetwork::DefaultPlanFile();
	}
	else if (FPaths::IsRelative(Path))
	{
		Path = FPaths::Combine(FPaths::ProjectDir(), Path);
	}
	State = EState::Loading;
	NetFuture = Async(EAsyncExecution::ThreadPool, [Path]()
	{
		TSharedPtr<FAstraLiftNetwork> N = MakeShared<FAstraLiftNetwork>();
		if (!N->Load(Path))
		{
			N->Problems.Add(FString::Printf(TEXT("no plan at %s"), *Path));
		}
		return N;
	});
}

void UAstraLiftSubsystem::Deinitialize()
{
	if (State == EState::Loading && NetFuture.IsValid())
	{
		NetFuture.Wait();
	}
	Run.Reset();
	Super::Deinitialize();
}

bool UAstraLiftSubsystem::LoadNetwork(const FString& PlanFile)
{
	FAstraLiftNetwork N;
	const bool bOk = N.Load(PlanFile);
	SetNetwork(MoveTemp(N));
	return bOk;
}

void UAstraLiftSubsystem::SetNetwork(FAstraLiftNetwork&& InNet)
{
	Net = MoveTemp(InNet);
	State = EState::Ready;
	bBuilt = false;
	NextToBuild = 0;
	BuildOrder.Reset();
	for (int32 I = 0; I < Net.Lines.Num(); ++I)
	{
		BuildOrder.Add(I);
	}
	const FVector Where = Captain() ? Captain()->GetActorLocation() : FVector::ZeroVector;
	BuildOrder.Sort([this, Where](int32 A, int32 B)
	{
		return FVector::DistSquared(Net.Lines[A].ShaftCm, Where) < FVector::DistSquared(Net.Lines[B].ShaftCm, Where);
	});
	for (const FString& P : Net.Problems)
	{
		UE_LOG(LogASTRA, Warning, TEXT("[Lift] plan: %s"), *P);
	}
	UE_LOG(LogASTRA, Log, TEXT("[Lift] %s: %s"), *Net.Source, Net.Lines.Num() ? *FString::Join(Net.Notes, TEXT("; ")) : TEXT("no lifts of the second version of the plan yet"));
}

void UAstraLiftSubsystem::BuildNow()
{
	while (!bBuilt && State == EState::Ready)
	{
		BuildLine(BuildOrder.IsValidIndex(NextToBuild) ? BuildOrder[NextToBuild] : INDEX_NONE);
	}
}

void UAstraLiftSubsystem::Reset()
{
	for (FAstraLiftRuntime& R : Run)
	{
		for (const TObjectPtr<AAstraLiftLanding>& L : R.Landings)
		{
			if (L)
			{
				L->Destroy();
			}
		}
		if (R.Car)
		{
			R.Car->Destroy();
		}
		if (R.Shaft)
		{
			R.Shaft->Destroy();
		}
	}
	Run.Reset();
	SlotOwner.Reset();
	bBuilt = false;
	NextToBuild = 0;
	BuildOrder.Reset();
	InLine = NearLine = NearStop = MenuLine = INDEX_NONE;
	State = EState::Idle;
	Test = FTestHooks();
}

void UAstraLiftSubsystem::BuildLine(int32 Line)
{
	if (Line == INDEX_NONE || !GetWorld())
	{
		bBuilt = true;
		SET_DWORD_STAT(STAT_AstraLiftsLines, Run.Num());
		return;
	}
	++NextToBuild;
	if (Run.Num() < Net.Lines.Num())
	{
		Run.SetNum(Net.Lines.Num());
		SlotOwner.SetNum(Net.Lines.Num());
	}
	const FAstraLiftLine& L = Net.Lines[Line];
	FAstraLiftRuntime& R = Run[Line];
	FActorSpawnParameters P;
	P.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	P.ObjectFlags |= RF_Transient;
	const FAstraLiftSpec Spec = FAstraLiftSpec::Make(L);
	R.Car = GetWorld()->SpawnActor<AAstraLiftCar>(FVector::ZeroVector, FRotator::ZeroRotator, P);
	if (!R.Car)
	{
		return;
	}
	R.Car->bQuiet = bBench;
	R.Car->Setup(this, Line, L, LiftParkingStop(L));
	SlotOwner[Line].Init(INDEX_NONE, R.Car->NumSlots());
	TArray<AAstraLiftLanding*> Landings;
	for (int32 S = 0; S < L.Stops.Num(); ++S)
	{
		AAstraLiftLanding* Landing = GetWorld()->SpawnActor<AAstraLiftLanding>(FVector::ZeroVector, FRotator::ZeroRotator, P);
		if (Landing)
		{
			Landing->bQuiet = bBench;
			Landing->Setup(L, S, Spec);
			Landing->SetSigns(L.Stops[S].Label, L.Stops[S].Deck);
		}
		R.Landings.Add(Landing);
		Landings.Add(Landing);
	}
	R.Car->SetLandings(Landings);
	// the car stands at its parking landing with the doors shut: those are in their places already
	if (!L.bShuttle)
	{
		R.Shaft = GetWorld()->SpawnActor<AAstraLiftShaft>(FVector::ZeroVector, FRotator::ZeroRotator, P);
		if (R.Shaft)
		{
			R.Shaft->Setup(L, Spec);
		}
	}
#if WITH_EDITOR
	R.Car->SetActorLabel(FString::Printf(TEXT("LiftCar_%s"), *L.Id));
	R.Car->SetFolderPath(TEXT("Interior/Lifts"));
	for (AAstraLiftLanding* Landing : Landings)
	{
		if (Landing)
		{
			Landing->SetFolderPath(TEXT("Interior/Lifts"));
		}
	}
	if (R.Shaft)
	{
		R.Shaft->SetFolderPath(TEXT("Interior/Lifts"));
	}
#endif
	if (NextToBuild >= BuildOrder.Num())
	{
		bBuilt = true;
		SET_DWORD_STAT(STAT_AstraLiftsLines, Run.Num());
		UE_LOG(LogASTRA, Log, TEXT("[Lift] %d lines built (%s)"), Run.Num(), *Describe().Left(200).Replace(TEXT("\n"), TEXT(" | ")));
	}
}

APawn* UAstraLiftSubsystem::Captain() const
{
	if (APawn* P = CaptainPawn.Get())
	{
		return P;
	}
	return GetWorld() ? UGameplayStatics::GetPlayerPawn(GetWorld(), 0) : nullptr;
}

// ================================================================================================================================ the tick

void UAstraLiftSubsystem::Tick(float DeltaTime)
{
	SCOPE_CYCLE_COUNTER(STAT_AstraLifts);
	const double T0 = FPlatformTime::Seconds();
	++Ticks;
	if (State == EState::Loading)
	{
		if (!NetFuture.IsReady())
		{
			return;
		}
		TSharedPtr<FAstraLiftNetwork> N = NetFuture.Get();
		SetNetwork(MoveTemp(*N));
	}
	if (State != EState::Ready)
	{
		return;
	}
	if (!bBuilt)
	{
		BuildLine(BuildOrder.IsValidIndex(NextToBuild) ? BuildOrder[NextToBuild] : INDEX_NONE);       // one line a frame: a hitch is a line's worth, not the network's
		return;
	}
	SlowT += DeltaTime;
	if (SlowT >= 0.2f)
	{
		Slow(SlowT);
		SlowT = 0.f;
	}
	if (InLine != INDEX_NONE)
	{
		RepaintScreen(InLine, false);                  // the Captain's car: its screen is painted when it is due
	}
	if (MenuLine != INDEX_NONE)
	{
		// the mouse: the row under the view's centre
		if (const APlayerCameraManager* Cam = UGameplayStatics::GetPlayerCameraManager(this, 0))
		{
			MenuPoint(Cam->GetCameraLocation(), Cam->GetCameraRotation().Vector());
		}
	}
	LastTickUs = (FPlatformTime::Seconds() - T0) * 1.0e6;
}

void UAstraLiftSubsystem::Slow(float Dt)
{
	SCOPE_CYCLE_COUNTER(STAT_AstraLiftsSlow);
	UpdateCaptain();
	int32 Moving = 0;
	for (int32 L = 0; L < Run.Num(); ++L)
	{
		AAstraLiftCar* Car = Run[L].Car;
		if (!Car)
		{
			continue;
		}
		Moving += Car->Brain.State() == FAstraLiftBrain::EState::Moving ? 1 : 0;
		// the cabin's light and hum while the Captain is within earshot of it
		if (APawn* P = Captain())
		{
			Car->SetNear(FVector::DistSquared(P->GetActorLocation(), Car->GetActorLocation()) < FMath::Square(Net.Lines[L].bShuttle ? 3500.f : 2600.f));
		}
	}
	SET_DWORD_STAT(STAT_AstraLiftsMoving, Moving);
	// the list closes on its own when it is forgotten or the Captain has left the car
	if (MenuLine != INDEX_NONE && (MenuLine != InLine || (GetWorld() && GetWorld()->GetTimeSeconds() - MenuOpenedAt > 25.0)))
	{
		MenuClose();
	}
}

void UAstraLiftSubsystem::UpdateCaptain()
{
	const APawn* P = Captain();
	const int32 WasIn = InLine;
	InLine = INDEX_NONE;
	NearLine = INDEX_NONE;
	NearStop = INDEX_NONE;
	if (!P || !P->IsA<ACharacter>())
	{
		return;
	}
	const FVector At = P->GetActorLocation();
	const FVector Feet = At - FVector(0.f, 0.f, Cast<ACharacter>(P)->GetCapsuleComponent()->GetScaledCapsuleHalfHeight());
	float BestD = TNumericLimits<float>::Max();
	for (int32 L = 0; L < Run.Num(); ++L)
	{
		const AAstraLiftCar* Car = Run[L].Car;
		if (!Car)
		{
			continue;
		}
		if (Car->Contains(At))
		{
			InLine = L;
			break;
		}
	}
	if (InLine == INDEX_NONE)
	{
		for (int32 L = 0; L < Run.Num(); ++L)
		{
			for (int32 S = 0; S < Run[L].Landings.Num(); ++S)
			{
				const AAstraLiftLanding* Landing = Run[L].Landings[S];
				if (Landing && Landing->Reaches(Feet, 600.f))
				{
					const float D = (float)FVector::Dist2D(Feet, Landing->PanelCm());
					if (D < BestD)
					{
						BestD = D;
						NearLine = L;
						NearStop = S;
					}
				}
			}
		}
	}
	if (WasIn != InLine && WasIn != INDEX_NONE)
	{
		if (MenuLine == WasIn)
		{
			MenuClose();
		}
	}
}

// =================================================================================================================================== hooks

FAstraLiftBrain::FHooks UAstraLiftSubsystem::MakeHooks(int32 Line)
{
	FAstraLiftBrain::FHooks H;
	H.DoorwayBusy = [this, Line](int32 Stop) { return DoorwayBusy(Line, Stop); };
	H.DeckReady = [this, Line](int32 Stop) { return DeckReady(Line, Stop); };
	H.WantDeck = [this, Line](int32 Stop) { WantDeck(Line, Stop); };
	H.ForceDeck = [this, Line](int32 Stop) { ForceDeck(Line, Stop); };
	H.Full = [this, Line]() { return SlotOwner.IsValidIndex(Line) && SlotOwner[Line].Num() > 0 && !SlotOwner[Line].Contains(INDEX_NONE); };     // (a car with every place taken passes the calls from the landings)
	return H;
}

bool UAstraLiftSubsystem::InterestedIn(int32 Line) const
{
	// the deck behind a landing matters when the Captain is in the car or waits at one of its landings (anyone else's ride is nothing to wait a deck for)
	return InLine == Line || NearLine == Line || (Test.CaptainInterested && Test.CaptainInterested());
}

bool UAstraLiftSubsystem::DoorwayBusy(int32 Line, int32 Stop) const
{
	const AAstraLiftLanding* Landing = LandingOf(Line, Stop);
	if (!Landing)
	{
		return false;
	}
	if (Test.Occupied && Test.Occupied(Landing->DoorCm()))
	{
		return true;
	}
	// the Captain (a pawn on foot), the crew who walk in view and the officers on a visit
	const FVector Door = Landing->DoorCm();
	if (!Test.Occupied)
	{
		if (const APawn* P = Captain())
		{
			if (P->IsA<ACharacter>() && Landing->InDoorway(P->GetActorLocation()))
			{
				return true;
			}
		}
	}
	for (const TWeakObjectPtr<const AActor>& W : AstraDoors::Walkers())
	{
		if (const AActor* A = W.Get())
		{
			if (FVector::DistSquared2D(A->GetActorLocation(), Door) < FMath::Square(400.f) && Landing->InDoorway(A->GetActorLocation()))
			{
				return true;
			}
		}
	}
	for (const TWeakObjectPtr<AAstraCrewMember>& W : AAstraCrewMember::Walkers())
	{
		if (const AActor* A = W.Get())
		{
			if (FVector::DistSquared2D(A->GetActorLocation(), Door) < FMath::Square(400.f) && Landing->InDoorway(A->GetActorLocation()))
			{
				return true;
			}
		}
	}
	return false;
}

bool UAstraLiftSubsystem::DeckReady(int32 Line, int32 Stop) const
{
	if (!InterestedIn(Line) || !Net.Lines.IsValidIndex(Line) || !Net.Lines[Line].Stops.IsValidIndex(Stop))
	{
		return true;
	}
	const FAstraLiftStop& S = Net.Lines[Line].Stops[Stop];
	const FVector Lobby = S.DoorCm + S.Out * 150.f;
	if (Test.DeckReadyAt)
	{
		return Test.DeckReadyAt(Lobby);
	}
	const UAstraDeckStreaming* DS = GetWorld() ? GetWorld()->GetSubsystem<UAstraDeckStreaming>() : nullptr;
	return !DS || DS->IsReadyAt(Lobby);
}

void UAstraLiftSubsystem::WantDeck(int32 Line, int32 Stop) const
{
	if (!InterestedIn(Line) || !Net.Lines.IsValidIndex(Line) || !Net.Lines[Line].Stops.IsValidIndex(Stop))
	{
		return;
	}
	const FAstraLiftStop& S = Net.Lines[Line].Stops[Stop];
	const FVector Lobby = S.DoorCm + S.Out * 150.f;
	if (Test.WantReadyAt)
	{
		Test.WantReadyAt(Lobby);
	}
	else if (UAstraDeckStreaming* DS = GetWorld() ? GetWorld()->GetSubsystem<UAstraDeckStreaming>() : nullptr)
	{
		DS->RequestAt(Lobby, 30.f);
	}
}

void UAstraLiftSubsystem::ForceDeck(int32 Line, int32 Stop) const
{
	if (!Net.Lines.IsValidIndex(Line) || !Net.Lines[Line].Stops.IsValidIndex(Stop))
	{
		return;
	}
	const FAstraLiftStop& S = Net.Lines[Line].Stops[Stop];
	const FVector Lobby = S.DoorCm + S.Out * 150.f;
	if (Test.ForceReadyAt)
	{
		Test.ForceReadyAt(Lobby);
	}
	else if (UAstraDeckStreaming* DS = GetWorld() ? GetWorld()->GetSubsystem<UAstraDeckStreaming>() : nullptr)
	{
		DS->ForceReadyAt(Lobby);
	}
}

void UAstraLiftSubsystem::OnCarEvent(int32 Line, const FAstraLiftEvent& E)
{
	if (!Net.Lines.IsValidIndex(Line))
	{
		return;
	}
	const FAstraLiftLine& L = Net.Lines[Line];
	auto Name = [&L](int32 S) { return L.Stops.IsValidIndex(S) ? L.Stops[S].Id : FString(TEXT("-")); };
	switch (E.Type)
	{
	case FAstraLiftEvent::EType::Depart:
		UE_LOG(LogASTRA, Verbose, TEXT("[Lift] %s leaves %s for %s"), *L.Id, *Name(E.Landing), *Name(E.Other));
		break;
	case FAstraLiftEvent::EType::Arrive:
		UE_LOG(LogASTRA, Verbose, TEXT("[Lift] %s arrives at %s"), *L.Id, *Name(E.Landing));
		break;
	case FAstraLiftEvent::EType::Held:
		UE_LOG(LogASTRA, Log, TEXT("[Lift] %s waits at %s with its doors shut: the deck is not there yet"), *L.Id, *Name(E.Landing));
		break;
	case FAstraLiftEvent::EType::Forced:
		UE_LOG(LogASTRA, Log, TEXT("[Lift] %s: the deck at %s was made ready at once"), *L.Id, *Name(E.Landing));
		break;
	default:
		break;
	}
	if (Line == InLine)
	{
		RepaintScreen(Line, true);
	}
}

// ============================================================================================================================= the Captain

FString UAstraLiftSubsystem::StopName(int32 Line, int32 Stop) const
{
	if (!Net.Lines.IsValidIndex(Line) || !Net.Lines[Line].Stops.IsValidIndex(Stop))
	{
		return FString();
	}
	const FAstraLiftStop& S = Net.Lines[Line].Stops[Stop];
	return S.DeckName.IsEmpty() || Net.Lines[Line].bShuttle ? S.Label : FString::Printf(TEXT("%s · %s"), *S.Label, *S.DeckName.ToUpper());
}

int32 UAstraLiftSubsystem::DisplayToStop(int32 Line, int32 Row) const
{
	if (!Net.Lines.IsValidIndex(Line))
	{
		return INDEX_NONE;
	}
	const FAstraLiftLine& L = Net.Lines[Line];
	if (Row < 0 || Row >= L.Stops.Num())
	{
		return INDEX_NONE;
	}
	return L.bShuttle ? Row : L.Stops.Num() - 1 - Row;       // a shaft lists its highest deck first; the shuttle its first stop
}

int32 UAstraLiftSubsystem::StopToRow(int32 Line, int32 Stop) const
{
	if (!Net.Lines.IsValidIndex(Line))
	{
		return INDEX_NONE;
	}
	return Net.Lines[Line].bShuttle ? Stop : Net.Lines[Line].Stops.Num() - 1 - Stop;
}

bool UAstraLiftSubsystem::CallAt(int32 Line, int32 Stop, FString& OutNotice)
{
	AAstraLiftCar* Car = CarOf(Line);
	AAstraLiftLanding* Landing = LandingOf(Line, Stop);
	if (!Car || !Landing)
	{
		return false;
	}
	FAstraLiftBrain& B = Car->Brain;
	const FString Name = Net.Lines[Line].Name;
	if (B.AtLanding() == Stop && (B.State() == FAstraLiftBrain::EState::Open || B.State() == FAstraLiftBrain::EState::Opening || B.State() == FAstraLiftBrain::EState::Closing))
	{
		B.HallCall(Stop, 0);
		Car->Wake();
		OutNotice = FString::Printf(TEXT("%s is here"), *Name);
		return true;
	}
	const float Eta = B.EstimateArrival(Stop, 0);
	B.HallCall(Stop, 0);
	Car->Wake();
	if (B.AtLanding() != Stop || B.State() != FAstraLiftBrain::EState::Idle)
	{
		Landing->SetCalled(true);
	}
	OutNotice = Eta < 1.5f ? FString::Printf(TEXT("%s: the doors are opening"), *Name) : FString::Printf(TEXT("%s called  ·  about %.0f s"), *Name, FMath::Max(2.f, FMath::RoundToFloat(Eta)));
	return true;
}

bool UAstraLiftSubsystem::IsNearPanel(const FVector& Feet) const
{
	for (int32 L = 0; L < Run.Num(); ++L)
	{
		for (const TObjectPtr<AAstraLiftLanding>& Landing : Run[L].Landings)
		{
			if (Landing && Landing->Reaches(Feet))
			{
				return true;
			}
		}
	}
	return false;
}

bool UAstraLiftSubsystem::RideFeet(FVector& OutFeetCm) const
{
	if (InLine == INDEX_NONE || !Run.IsValidIndex(InLine) || !Run[InLine].Car)
	{
		return false;
	}
	const FAstraLiftBrain& B = Run[InLine].Car->Brain;
	const int32 Stop = B.State() == FAstraLiftBrain::EState::Moving ? B.LegTarget() : (B.State() == FAstraLiftBrain::EState::Hold ? B.AtLanding() : INDEX_NONE);
	if (!Net.Lines[InLine].Stops.IsValidIndex(Stop))
	{
		return false;
	}
	const FAstraLiftStop& S = Net.Lines[InLine].Stops[Stop];
	OutFeetCm = S.DoorCm + S.Out * 150.f;
	return true;
}

bool UAstraLiftSubsystem::Use(APawn* Pawn, FString& OutNotice)
{
	if (!bBuilt || !Pawn)
	{
		return false;
	}
	UpdateCaptain();
	if (InLine != INDEX_NONE)
	{
		if (MenuLine == INDEX_NONE)
		{
			MenuLine = InLine;
			MenuOpenedAt = GetWorld() ? GetWorld()->GetTimeSeconds() : 0.0;
			// the mark starts on the deck the car is at (a list opens where you are), or on the first row that is somewhere else
			const int32 Here = Run[InLine].Car ? Run[InLine].Car->CurrentStop() : INDEX_NONE;
			MenuSel = FMath::Max(0, StopToRow(InLine, Here));
			HoverRow = INDEX_NONE;
			RepaintScreen(InLine, true);
			OutNotice = TEXT("W / S or the mouse to choose  ·  E to go  ·  Esc to close");
			return true;
		}
		return MenuChoose(OutNotice);
	}
	// outside: the panel at a landing within reach
	const FVector Feet = Pawn->GetActorLocation() - FVector(0.f, 0.f, Pawn->IsA<ACharacter>() ? Cast<ACharacter>(Pawn)->GetCapsuleComponent()->GetScaledCapsuleHalfHeight() : 90.f);
	int32 BestLine = INDEX_NONE, BestStop = INDEX_NONE;
	float BestD = TNumericLimits<float>::Max();
	for (int32 L = 0; L < Run.Num(); ++L)
	{
		for (int32 S = 0; S < Run[L].Landings.Num(); ++S)
		{
			const AAstraLiftLanding* Landing = Run[L].Landings[S];
			if (Landing && Landing->Reaches(Feet))
			{
				const float D = (float)FVector::Dist2D(Feet, Landing->PanelCm());
				if (D < BestD)
				{
					BestD = D;
					BestLine = L;
					BestStop = S;
				}
			}
		}
	}
	return BestLine != INDEX_NONE && CallAt(BestLine, BestStop, OutNotice);
}

void UAstraLiftSubsystem::MenuMove(int32 Delta)
{
	if (MenuLine == INDEX_NONE || !Net.Lines.IsValidIndex(MenuLine))
	{
		return;
	}
	const int32 N = Net.Lines[MenuLine].Stops.Num();
	MenuSel = (MenuSel + Delta % N + N) % N;
	MenuOpenedAt = GetWorld() ? GetWorld()->GetTimeSeconds() : 0.0;
	RepaintScreen(MenuLine, true);
}

void UAstraLiftSubsystem::MenuClose()
{
	if (MenuLine != INDEX_NONE)
	{
		const int32 L = MenuLine;
		MenuLine = INDEX_NONE;
		HoverRow = INDEX_NONE;
		RepaintScreen(L, true);
	}
}

bool UAstraLiftSubsystem::StartRide(int32 Line, int32 Stop, FString& Detail)
{
	AAstraLiftCar* Car = CarOf(Line);
	if (!Car || !Net.Lines[Line].Stops.IsValidIndex(Stop))
	{
		Detail = TEXT("no such stop");
		return false;
	}
	const FAstraLiftLine& L = Net.Lines[Line];
	if (Car->Brain.AtLanding() == Stop && Car->Brain.State() != FAstraLiftBrain::EState::Moving)
	{
		Detail = FString::Printf(TEXT("the car is already at %s"), *StopName(Line, Stop));
		return true;
	}
	const float Eta = Car->Brain.EstimateArrival(Stop, 0);
	Car->Brain.CarCall(Stop);
	Car->Wake();
	Detail = FString::Printf(TEXT("%s is going to %s (about %.0f s)"), *L.Name, *StopName(Line, Stop), FMath::Max(2.f, FMath::RoundToFloat(Eta)));
	return true;
}

bool UAstraLiftSubsystem::MenuChoose(FString& OutNotice)
{
	if (MenuLine == INDEX_NONE)
	{
		return false;
	}
	const int32 Line = MenuLine;
	const int32 Stop = DisplayToStop(Line, HoverRow != INDEX_NONE ? HoverRow : MenuSel);
	MenuClose();
	return StartRide(Line, Stop, OutNotice);
}

int32 UAstraLiftSubsystem::MenuPoint(const FVector& EyeCm, const FVector& Dir)
{
	if (MenuLine == INDEX_NONE || !Run.IsValidIndex(MenuLine) || !Run[MenuLine].Car)
	{
		return INDEX_NONE;
	}
	const UStaticMeshComponent* Scr = Run[MenuLine].Car->ScreenComponent();
	if (!Scr)
	{
		return INDEX_NONE;
	}
	// the ray against the screen's plane, in the screen's own frame (it faces +X, 1 m square scaled to its size)
	const FTransform T = Scr->GetComponentTransform();
	const FVector O = T.InverseTransformPosition(EyeCm);
	const FVector D = T.InverseTransformVector(Dir);
	if (D.X > -0.05f || O.X < 0.f)
	{
		return INDEX_NONE;                         // looking away from it, or from behind
	}
	const float Tt = -O.X / D.X;
	const FVector Hit = O + D * Tt;                // in the unit quad's local space: y to the viewer's left, z up, each -50..50 cm
	const float U = 0.5f - Hit.Y / 100.f, V = 0.5f - Hit.Z / 100.f;     // the viewer's right is -Y; the picture's top is +Z
	if (U < 0.f || U > 1.f || V < 0.f || V > 1.f)
	{
		return INDEX_NONE;
	}
	TArray<FRow> Rows;
	MenuRows(MenuLine, Rows);
	const float Top = 90.f, Bottom = 560.f;
	const float Py = V * 640.f;
	if (Py < Top || Py >= Bottom || Rows.Num() == 0)
	{
		return INDEX_NONE;
	}
	const float RowH = FMath::Min(52.f, (Bottom - Top) / Rows.Num());
	const int32 Row = FMath::FloorToInt((Py - Top) / RowH);
	if (Row < 0 || Row >= Rows.Num())
	{
		return INDEX_NONE;
	}
	if (Row != HoverRow)
	{
		HoverRow = Row;
		MenuSel = Row;                              // the mark follows the pointer when it moves to another row (W and S move it again)
		RepaintScreen(MenuLine, true);
	}
	return Row;
}

bool UAstraLiftSubsystem::GoToDeck(int32 Deck, FString& Detail)
{
	const int32 Line = InLine;
	if (Line == INDEX_NONE)
	{
		Detail = TEXT("the Captain is not in a lift");
		return false;
	}
	const int32 Stop = Net.Lines[Line].FindStopByDeck(Deck);
	if (Stop == INDEX_NONE)
	{
		Detail = FString::Printf(TEXT("%s does not serve deck %d"), *Net.Lines[Line].Name, Deck);
		return false;
	}
	MenuClose();
	return StartRide(Line, Stop, Detail);
}

bool UAstraLiftSubsystem::GoByVoice(const TSharedPtr<FJsonObject>& Args, FString& Detail)
{
	UpdateCaptain();
	const int32 Line = InLine;
	if (Line == INDEX_NONE || !Args.IsValid())
	{
		Detail = TEXT("the Captain is not in a lift car: the lifts take orders from inside a car");
		return false;
	}
	const FAstraLiftLine& L = Net.Lines[Line];
	int32 Stop = INDEX_NONE;
	FString Id, Place;
	double DeckNum = 0.0;
	if (Args->TryGetStringField(TEXT("destination"), Id) || Args->TryGetStringField(TEXT("stop"), Id))
	{
		Stop = L.FindStopById(Id.TrimStartAndEnd());
	}
	if (Stop == INDEX_NONE && Args->TryGetNumberField(TEXT("deck"), DeckNum))
	{
		Stop = L.FindStopByDeck((int32)DeckNum);
	}
	if (Stop == INDEX_NONE && Args->TryGetStringField(TEXT("place"), Place) && !Place.IsEmpty())
	{
		// a place by the name the car's list gives it
		for (int32 I = 0; I < L.Stops.Num() && Stop == INDEX_NONE; ++I)
		{
			for (const FString& P : L.Stops[I].Places)
			{
				if (P.Equals(Place.TrimStartAndEnd(), ESearchCase::IgnoreCase))
				{
					Stop = I;
					break;
				}
			}
		}
	}
	if (Stop == INDEX_NONE)
	{
		FString Served;
		for (const FAstraLiftStop& S : L.Stops)
		{
			Served += (Served.IsEmpty() ? TEXT("") : TEXT(", ")) + S.Id;
		}
		Detail = FString::Printf(TEXT("%s does not serve that: its stops are %s"), *L.Name, *Served);
		return false;
	}
	MenuClose();
	return StartRide(Line, Stop, Detail);
}

TSharedPtr<FJsonObject> UAstraLiftSubsystem::ContextJson() const
{
	if (InLine == INDEX_NONE || !Net.Lines.IsValidIndex(InLine) || !Run[InLine].Car)
	{
		return nullptr;
	}
	const FAstraLiftLine& L = Net.Lines[InLine];
	const AAstraLiftCar* Car = Run[InLine].Car;
	TSharedRef<FJsonObject> J = MakeShared<FJsonObject>();
	J->SetStringField(TEXT("car"), L.Id);
	J->SetStringField(TEXT("name"), L.Name);
	J->SetStringField(TEXT("kind"), L.bShuttle ? TEXT("shuttle") : L.Kind == EAstraLiftKind::Service ? TEXT("service") : L.Kind == EAstraLiftKind::Cargo ? TEXT("cargo") : TEXT("turbolift"));
	const int32 Here = Car->CurrentStop();
	const bool bMoving = Car->Brain.State() == FAstraLiftBrain::EState::Moving;
	J->SetStringField(TEXT("at"), L.Stops.IsValidIndex(Here) ? L.Stops[Here].Id : FString());
	J->SetBoolField(TEXT("moving"), bMoving);
	if (bMoving && L.Stops.IsValidIndex(Car->Brain.LegTarget()))
	{
		J->SetStringField(TEXT("going_to"), L.Stops[Car->Brain.LegTarget()].Id);
	}
	TArray<TSharedPtr<FJsonValue>> Stops;
	for (int32 Row = 0; Row < L.Stops.Num(); ++Row)
	{
		const FAstraLiftStop& S = L.Stops[DisplayToStop(InLine, Row)];
		TSharedRef<FJsonObject> O = MakeShared<FJsonObject>();
		O->SetStringField(TEXT("id"), S.Id);
		O->SetStringField(TEXT("label"), S.Label);
		if (!S.DeckName.IsEmpty())
		{
			O->SetStringField(TEXT("deck_name"), S.DeckName);
		}
		TArray<TSharedPtr<FJsonValue>> Places;
		for (const FString& P : S.Places)
		{
			Places.Add(MakeShared<FJsonValueString>(P));
		}
		O->SetArrayField(TEXT("places"), Places);
		Stops.Add(MakeShared<FJsonValueObject>(O));
	}
	J->SetArrayField(TEXT("stops"), Stops);
	return J;
}

// ================================================================================================================================ the crew

float UAstraLiftSubsystem::RideSeconds(int32 Line, int32 From, int32 To) const
{
	if (!Net.Lines.IsValidIndex(Line) || !Net.Lines[Line].Stops.IsValidIndex(From) || !Net.Lines[Line].Stops.IsValidIndex(To) || From == To)
	{
		return 0.f;
	}
	const FAstraLiftLine& L = Net.Lines[Line];
	const FAstraLiftBrain::FConfig C;
	// the wait for the car (half a cycle of an idle shaft is a few seconds), the doors, the move, the doors
	return 5.f + C.DoorS + C.BoardedDwellS + C.DoorS + FAstraLiftProfile::Make(FMath::Abs(L.Stops[To].S - L.Stops[From].S), L.SpeedCmS, L.AccelCmS2).T + C.DoorS;
}

float UAstraLiftSubsystem::AverageRideSeconds() const
{
	double Sum = 0.0;
	int32 N = 0;
	for (int32 L = 0; L < Net.Lines.Num(); ++L)
	{
		if (Net.Lines[L].bShuttle)
		{
			continue;
		}
		const int32 S = Net.Lines[L].Stops.Num();
		for (int32 A = 0; A < S; ++A)
		{
			for (int32 B = A + 1; B < S; ++B)
			{
				Sum += RideSeconds(L, A, B);
				++N;
			}
		}
	}
	return N ? (float)(Sum / N) : 0.f;
}

void UAstraLiftSubsystem::RiderCall(int32 Line, int32 From, int32 To)
{
	AAstraLiftCar* Car = CarOf(Line);
	if (!Car || From == To)
	{
		return;
	}
	Car->Brain.HallCall(From, To > From ? 1 : -1);
	Car->Wake();
	if (AAstraLiftLanding* Landing = LandingOf(Line, From))
	{
		if (Car->Brain.AtLanding() != From || Car->Brain.State() == FAstraLiftBrain::EState::Moving)
		{
			Landing->SetCalled(true);
		}
	}
}

bool UAstraLiftSubsystem::CanBoard(int32 Line, int32 From, int32 To) const
{
	const AAstraLiftCar* Car = CarOf(Line);
	if (!Car || From == To)
	{
		return false;
	}
	const FAstraLiftBrain& B = Car->Brain;
	const bool bOpen = B.State() == FAstraLiftBrain::EState::Open || (B.State() == FAstraLiftBrain::EState::Opening && B.DoorOpen() > 0.6f);
	const int32 Dir = To > From ? 1 : -1;
	if (!bOpen || B.AtLanding() != From || (B.Heading() != 0 && B.Heading() != Dir) || !SlotOwner.IsValidIndex(Line))
	{
		return false;
	}
	return HasFreeSlot(Line);
}

bool UAstraLiftSubsystem::HasFreeSlot(int32 Line) const
{
	if (SlotOwner.IsValidIndex(Line))
	{
		for (int32 I = 0; I < SlotOwner[Line].Num(); ++I)
		{
			if (SlotFree(Line, I))
			{
				return true;
			}
		}
	}
	return false;
}

bool UAstraLiftSubsystem::SlotFree(int32 Line, int32 Slot) const
{
	const AAstraLiftCar* Car = CarOf(Line);
	if (!Car || !SlotOwner.IsValidIndex(Line) || !SlotOwner[Line].IsValidIndex(Slot) || SlotOwner[Line][Slot] != INDEX_NONE)
	{
		return false;
	}
	if (const APawn* P = Captain(); P && P->IsA<ACharacter>() && Car->Contains(P->GetActorLocation(), 0.f))
	{
		return FVector::Dist2D(Car->ToWorld(Car->SlotLocal(Slot)), P->GetActorLocation()) > 50.f;
	}
	return true;
}

int32 UAstraLiftSubsystem::TakeSlot(int32 Line, int32 Who)
{
	if (!SlotOwner.IsValidIndex(Line))
	{
		return INDEX_NONE;
	}
	for (int32 I = 0; I < SlotOwner[Line].Num(); ++I)
	{
		if (SlotFree(Line, I))
		{
			SlotOwner[Line][I] = Who;
			return I;
		}
	}
	return INDEX_NONE;
}

void UAstraLiftSubsystem::FreeSlot(int32 Line, int32 Slot)
{
	if (SlotOwner.IsValidIndex(Line) && SlotOwner[Line].IsValidIndex(Slot))
	{
		SlotOwner[Line][Slot] = INDEX_NONE;
	}
}

void UAstraLiftSubsystem::RiderChoose(int32 Line, int32 To)
{
	if (AAstraLiftCar* Car = CarOf(Line))
	{
		Car->Brain.CarCall(To);
		Car->Wake();
	}
}

bool UAstraLiftSubsystem::DoorsOpenAt(int32 Line, int32 Stop) const
{
	const AAstraLiftCar* Car = CarOf(Line);
	if (!Car)
	{
		return false;
	}
	const FAstraLiftBrain& B = Car->Brain;
	return B.AtLanding() == Stop && (B.State() == FAstraLiftBrain::EState::Open || (B.State() == FAstraLiftBrain::EState::Opening && B.DoorOpen() > 0.6f));
}

// ================================================================================================================================== report

FString UAstraLiftSubsystem::Describe() const
{
	FString Out;
	static const TCHAR* const StateName[] = {TEXT("parked"), TEXT("moving"), TEXT("held"), TEXT("opening"), TEXT("open"), TEXT("closing")};
	for (int32 L = 0; L < Run.Num(); ++L)
	{
		const AAstraLiftCar* Car = Run[L].Car;
		if (!Car)
		{
			continue;
		}
		const FAstraLiftBrain& B = Car->Brain;
		const FAstraLiftLine& Line = Net.Lines[L];
		Out += FString::Printf(TEXT("%-9s %-14s %-8s at %-7s doors %.2f  s %.1f m  v %.1f m/s  heading %+d  %s\n"), *Line.Id, *Line.Name, StateName[(int32)B.State()],
		                       Line.Stops.IsValidIndex(Car->CurrentStop()) ? *Line.Stops[Car->CurrentStop()].Id : TEXT("-"), B.DoorOpen(), B.S() / 100.f, B.V() / 100.f, B.Heading(),
		                       L == InLine ? TEXT("<- the Captain") : TEXT(""));
	}
	return Out.IsEmpty() ? FString(TEXT("no lifts built")) : Out;
}

// ================================================================================================================================ console

struct FAstraLiftConsole
{
	static UAstraLiftSubsystem* Get(UWorld* W) { return W ? W->GetSubsystem<UAstraLiftSubsystem>() : nullptr; }

	static void Info(UWorld* W)
	{
		if (UAstraLiftSubsystem* S = Get(W))
		{
			UE_LOG(LogASTRA, Log, TEXT("[Lift]\n%s"), *S->Describe());
		}
	}

	/** astra.lifts.call <line> <deck|stop id>: a hall call (test), as if someone pressed the panel there. */
	static void Call(const TArray<FString>& A, UWorld* W)
	{
		UAstraLiftSubsystem* S = Get(W);
		if (!S || A.Num() < 2)
		{
			UE_LOG(LogASTRA, Warning, TEXT("[Lift] usage: astra.lifts.call <line> <deck or stop id>"));
			return;
		}
		const int32 L = S->Net.FindLine(A[0]);
		if (L == INDEX_NONE)
		{
			UE_LOG(LogASTRA, Warning, TEXT("[Lift] no line %s"), *A[0]);
			return;
		}
		int32 Stop = S->Net.Lines[L].FindStopById(A[1]);
		Stop = Stop != INDEX_NONE ? Stop : S->Net.Lines[L].FindStopByDeck(FCString::Atoi(*A[1]));
		FString Notice;
		UE_LOG(LogASTRA, Log, TEXT("[Lift] %s"), Stop != INDEX_NONE && S->CallAt(L, Stop, Notice) ? *Notice : TEXT("no such stop"));
	}

	/** astra.lifts.go <deck|stop id>: the car the Captain is in goes there (what the voice does). */
	static void Go(const TArray<FString>& A, UWorld* W)
	{
		UAstraLiftSubsystem* S = Get(W);
		if (!S || A.Num() < 1)
		{
			UE_LOG(LogASTRA, Warning, TEXT("[Lift] usage: astra.lifts.go <deck or stop id>"));
			return;
		}
		TSharedRef<FJsonObject> Args = MakeShared<FJsonObject>();
		Args->SetStringField(TEXT("destination"), A[0]);
		Args->SetNumberField(TEXT("deck"), FCString::Atoi(*A[0]));
		FString Detail;
		const bool bOk = S->GoByVoice(Args, Detail);
		UE_LOG(LogASTRA, Log, TEXT("[Lift] %s: %s"), bOk ? TEXT("ok") : TEXT("failed"), *Detail);
	}

	static void Context(UWorld* W)
	{
		UAstraLiftSubsystem* S = Get(W);
		const TSharedPtr<FJsonObject> J = S ? S->ContextJson() : nullptr;
		FString Text;
		if (J.IsValid())
		{
			const TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&Text);
			FJsonSerializer::Serialize(J.ToSharedRef(), Writer);
		}
		UE_LOG(LogASTRA, Log, TEXT("[Lift] context: %s"), J.IsValid() ? *Text : TEXT("(the Captain is not in a lift)"));
	}
};

namespace
{
	FAutoConsoleCommandWithWorld CmdLifts(TEXT("astra.lifts.info"), TEXT("Every lift: where it is, what it does, whether the Captain is in it"), FConsoleCommandWithWorldDelegate::CreateStatic(&FAstraLiftConsole::Info));
	FAutoConsoleCommandWithWorldAndArgs CmdLiftCall(TEXT("astra.lifts.call"), TEXT("astra.lifts.call <line> <deck or stop id>: call that lift to a landing"), FConsoleCommandWithWorldAndArgsDelegate::CreateStatic(&FAstraLiftConsole::Call));
	FAutoConsoleCommandWithWorldAndArgs CmdLiftGo(TEXT("astra.lifts.go"), TEXT("astra.lifts.go <deck or stop id>: the lift the Captain is in goes there"), FConsoleCommandWithWorldAndArgsDelegate::CreateStatic(&FAstraLiftConsole::Go));
	FAutoConsoleCommandWithWorld CmdLiftContext(TEXT("astra.lifts.context"), TEXT("What the crew's mind is told when the Captain speaks in a lift"), FConsoleCommandWithWorldDelegate::CreateStatic(&FAstraLiftConsole::Context));
}
