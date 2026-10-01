// ASTRA — deck streaming.

#include "AstraDeckStreaming.h"

#include "ASTRA.h"
#include "AstraShipPlan.h"
#include "Engine/LevelStreaming.h"
#include "Engine/World.h"
#include "GameFramework/Character.h"
#include "Components/CapsuleComponent.h"
#include "HAL/IConsoleManager.h"
#include "Kismet/GameplayStatics.h"
#include "Misc/PackageName.h"

DECLARE_CYCLE_STAT(TEXT("Deck streaming"), STAT_AstraDeckStreaming, STATGROUP_Astra);

namespace
{
	TAutoConsoleVariable<float> CVarDeckUnloadDelay(TEXT("astra.decks.unload_delay"), 20.f,
		TEXT("Seconds a deck stays loaded after the Captain no longer needs it (the decks next to the one he is on are always loaded)"));
	TAutoConsoleVariable<int32> CVarDeckAll(TEXT("astra.decks.all"), 0,
		TEXT("1: every deck's sub-level is kept loaded (the editor's view of the whole ship, a memory test); 0: stream by the Captain's deck"));

	/** "L_Deck05" (or "UEDPIE_0_L_Deck05" in a PIE world) -> 5, else 0. */
	int32 DeckOfLevelName(const FString& Name)
	{
		const FString Short = FPackageName::GetShortName(Name);
		const int32 At = Short.Find(TEXT("L_Deck"), ESearchCase::IgnoreCase, ESearchDir::FromEnd);
		if (At == INDEX_NONE)
		{
			return 0;
		}
		return FCString::Atoi(*Short.Mid(At + 6));
	}
}

bool UAstraDeckStreaming::ShouldCreateSubsystem(UObject* Outer) const
{
	const UWorld* World = Cast<UWorld>(Outer);
	return World && (World->WorldType == EWorldType::Game || World->WorldType == EWorldType::PIE);
}

const UAstraShipPlan* UAstraDeckStreaming::Plan() const
{
	const UAstraShipPlan* P = GetWorld() ? GetWorld()->GetSubsystem<UAstraShipPlan>() : nullptr;
	return P && P->EnsureLoaded() ? P : nullptr;
}

void UAstraDeckStreaming::OnWorldBeginPlay(UWorld& InWorld)
{
	Super::OnWorldBeginPlay(InWorld);
	for (ULevelStreaming* LS : InWorld.GetStreamingLevels())
	{
		const int32 Deck = LS ? DeckOfLevelName(LS->GetWorldAssetPackageName()) : 0;
		if (Deck > 0)
		{
			Levels.FindOrAdd(Deck).Level = LS;
		}
	}
	FString Names;
	for (const int32 D : BuiltDecks())
	{
		Names += FString::Printf(TEXT(" %d"), D);
	}
	UE_LOG(LogASTRA, Log, TEXT("[Decks] %d deck sub-levels:%s"), Levels.Num(), *Names);
	Update(true);
}

TArray<int32> UAstraDeckStreaming::BuiltDecks() const
{
	TArray<int32> Out;
	Levels.GetKeys(Out);
	Out.Sort();
	return Out;
}

TArray<int32> UAstraDeckStreaming::DecksFor(const UAstraShipPlan& Plan, int32 Deck, bool bInHall)
{
	TArray<int32> Out;
	if (Deck <= 0)
	{
		return Out;
	}
	Out.Add(Deck);
	if (!bInHall)
	{
		for (const int32 N : Plan.StairNeighbours(Deck))
		{
			Out.AddUnique(N);
		}
	}
	return Out;
}

bool UAstraDeckStreaming::CaptainPosition(FVector& OutFeet) const
{
	if (bTestPos)
	{
		OutFeet = TestFeet;
		return true;
	}
	// only the Captain on foot is aboard in a deck: a Falcon in the void, a lifepod, the bridge's chair outside the plan: nothing to stream
	const ACharacter* C = Cast<ACharacter>(UGameplayStatics::GetPlayerPawn(this, 0));
	if (!C)
	{
		return false;
	}
	OutFeet = C->GetActorLocation() - FVector(0.f, 0.f, C->GetCapsuleComponent()->GetScaledCapsuleHalfHeight());
	return true;
}

void UAstraDeckStreaming::Tick(float DeltaTime)
{
	SCOPE_CYCLE_COUNTER(STAT_AstraDeckStreaming);
	Accum += DeltaTime;
	if (Levels.Num() == 0 || Accum < 0.25f)
	{
		return;
	}
	Accum = 0.f;
	Update(false);
}

void UAstraDeckStreaming::Want(int32 Deck, bool bUrgent)
{
	FDeckLevel* D = Levels.Find(Deck);
	ULevelStreaming* LS = D ? D->Level.Get() : nullptr;
	if (!LS)
	{
		return;
	}
	D->LastWanted = GetWorld()->GetTimeSeconds();
	if (!LS->ShouldBeLoaded())
	{
		LS->SetShouldBeLoaded(true);
		UE_LOG(LogASTRA, Log, TEXT("[Decks] loading deck %d"), Deck);
	}
	if (!LS->GetShouldBeVisibleFlag())
	{
		LS->SetShouldBeVisible(true);
	}
	LS->SetPriority(bUrgent ? 100 : 50);
}

void UAstraDeckStreaming::Drop(FDeckLevel& D)
{
	ULevelStreaming* LS = D.Level.Get();
	if (LS && (LS->ShouldBeLoaded() || LS->GetShouldBeVisibleFlag()))
	{
		LS->SetShouldBeVisible(false);
		LS->SetShouldBeLoaded(false);
		UE_LOG(LogASTRA, Log, TEXT("[Decks] unloading %s"), *LS->GetWorldAssetPackageName());
	}
}

void UAstraDeckStreaming::Update(bool bFirst)
{
	const UWorld* World = GetWorld();
	if (!World || Levels.Num() == 0)
	{
		return;
	}
	const double Now = World->GetTimeSeconds();
	TSet<int32> Wanted;
	int32 Own = 0;
	FVector Feet;
	if (CVarDeckAll.GetValueOnGameThread() != 0)
	{
		for (const TPair<int32, FDeckLevel>& KV : Levels)
		{
			Wanted.Add(KV.Key);
		}
	}
	else if (CaptainPosition(Feet))
	{
		if (const UAstraShipPlan* P = Plan())
		{
			const FVector Chest = Feet + FVector(0.f, 0.f, 60.f);
			const int32 CI = P->CompartmentIndexAt(Chest);
			const bool bHall = CI != INDEX_NONE && P->GetCompartments()[CI].bExisting;     // a hall of its own: what is beyond its doors is the deck's
			Own = P->DeckOfPoint(Chest);
			for (const int32 D : DecksFor(*P, Own, bHall))
			{
				Wanted.Add(D);
			}
		}
	}
	const float Delay = FMath::Max(1.f, CVarDeckUnloadDelay.GetValueOnGameThread());
	for (TPair<int32, FDeckLevel>& KV : Levels)
	{
		FDeckLevel& D = KV.Value;
		if (Wanted.Contains(KV.Key) || D.bPinned || D.HoldUntil > Now)
		{
			Want(KV.Key, KV.Key == Own || D.HoldUntil > Now);
		}
		else if (Now - D.LastWanted > Delay)
		{
			Drop(D);
		}
	}
	if (bFirst && Own > 0)
	{
		UE_LOG(LogASTRA, Log, TEXT("[Decks] the Captain starts on deck %d"), Own);
	}
}

void UAstraDeckStreaming::RequestDeck(int32 Deck, float HoldS)
{
	if (FDeckLevel* D = Levels.Find(Deck))
	{
		D->HoldUntil = FMath::Max(D->HoldUntil, GetWorld()->GetTimeSeconds() + (double)HoldS);
		Want(Deck, true);
	}
}

void UAstraDeckStreaming::RequestAt(const FVector& WorldCm, float HoldS)
{
	if (const UAstraShipPlan* P = Plan())
	{
		RequestDeck(P->DeckOfPoint(WorldCm + FVector(0.f, 0.f, 60.f)), HoldS);
	}
}

bool UAstraDeckStreaming::IsDeckReady(int32 Deck) const
{
	const FDeckLevel* D = Levels.Find(Deck);
	const ULevelStreaming* LS = D ? D->Level.Get() : nullptr;
	return !LS || (LS->IsLevelVisible() && !LS->IsStreamingStatePending());
}

bool UAstraDeckStreaming::IsReadyAt(const FVector& WorldCm) const
{
	const UAstraShipPlan* P = Plan();
	return !P || IsDeckReady(P->DeckOfPoint(WorldCm + FVector(0.f, 0.f, 60.f)));
}

bool UAstraDeckStreaming::ForceReadyAt(const FVector& WorldCm)
{
	const UAstraShipPlan* P = Plan();
	if (!P)
	{
		return true;
	}
	const int32 Deck = P->DeckOfPoint(WorldCm + FVector(0.f, 0.f, 60.f));
	FDeckLevel* D = Levels.Find(Deck);
	ULevelStreaming* LS = D ? D->Level.Get() : nullptr;
	if (!LS || IsDeckReady(Deck))
	{
		return true;
	}
	const double T0 = FPlatformTime::Seconds();
	RequestDeck(Deck, 30.f);
	LS->bShouldBlockOnLoad = true;
	GetWorld()->FlushLevelStreaming(EFlushLevelStreamingType::Visibility);
	LS->bShouldBlockOnLoad = false;
	UE_LOG(LogASTRA, Log, TEXT("[Decks] deck %d forced in %.0f ms"), Deck, (FPlatformTime::Seconds() - T0) * 1000.0);
	return IsDeckReady(Deck);
}

FString UAstraDeckStreaming::Describe() const
{
	FString Out;
	const double Now = GetWorld() ? GetWorld()->GetTimeSeconds() : 0.0;
	for (const int32 Deck : BuiltDecks())
	{
		const FDeckLevel& D = Levels[Deck];
		const ULevelStreaming* LS = D.Level.Get();
		Out += FString::Printf(TEXT("deck %2d  %-16s %s%s%s\n"), Deck, LS ? EnumToString(LS->GetLevelStreamingState()) : TEXT("(gone)"),
		                       LS && LS->ShouldBeLoaded() ? TEXT("wanted") : TEXT("dropped"), D.bPinned ? TEXT(" pinned") : TEXT(""),
		                       D.HoldUntil > Now ? *FString::Printf(TEXT(" held %.0f s"), D.HoldUntil - Now) : TEXT(""));
	}
	return Out.IsEmpty() ? TEXT("no deck sub-levels") : Out;
}

// ------------------------------------------------------------------------------------------------------------------------------ console
struct FAstraDeckStreamingConsole
{
	static UAstraDeckStreaming* Get(UWorld* World) { return World ? World->GetSubsystem<UAstraDeckStreaming>() : nullptr; }

	static void Info(UWorld* World)
	{
		if (const UAstraDeckStreaming* S = Get(World))
		{
			UE_LOG(LogASTRA, Log, TEXT("[Decks]\n%s"), *S->Describe());
		}
	}

	static void Pin(const TArray<FString>& A, UWorld* World)
	{
		UAstraDeckStreaming* S = Get(World);
		if (!S || A.Num() < 1)
		{
			UE_LOG(LogASTRA, Warning, TEXT("[Decks] usage: astra.decks.pin <deck> [0|1]"));
			return;
		}
		const int32 Deck = FCString::Atoi(*A[0]);
		if (UAstraDeckStreaming::FDeckLevel* D = S->Levels.Find(Deck))
		{
			D->bPinned = A.Num() < 2 || FCString::Atoi(*A[1]) != 0;
			UE_LOG(LogASTRA, Log, TEXT("[Decks] deck %d %s"), Deck, D->bPinned ? TEXT("pinned: kept loaded") : TEXT("released"));
			S->Update(false);
		}
	}
};

namespace
{
	FAutoConsoleCommandWithWorld CmdDecks(TEXT("astra.decks"), TEXT("The decks' sub-levels: which are in the world, which the Captain's deck wants"),
		FConsoleCommandWithWorldDelegate::CreateStatic(&FAstraDeckStreamingConsole::Info));
	FAutoConsoleCommandWithWorldAndArgs CmdDecksPin(TEXT("astra.decks.pin"), TEXT("astra.decks.pin <deck> [0|1]: keep a deck's sub-level loaded (or release it)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateStatic(&FAstraDeckStreamingConsole::Pin));
}
