// ASTRA — the adaptive score.

#include "AstraMusicSubsystem.h"

#include "ASTRA.h"
#include "AstraBattleSubsystem.h"
#include "AstraCrewMember.h"
#include "AstraShipSubsystem.h"
#include "Components/AudioComponent.h"
#include "EngineUtils.h"
#include "Kismet/GameplayStatics.h"
#include "Sound/SoundBase.h"

DECLARE_CYCLE_STAT(TEXT("Music"), STAT_AstraMusic, STATGROUP_Astra);

namespace
{
	float GMusicVolume = 0.34f;          // under the dialogue: the crew must always be heard
	int32 GForcedMood = -1;
	FAutoConsoleCommand CmdMusicVolume(TEXT("astra.music.volume"), TEXT("Music volume 0..1 (default 0.34)"),
		FConsoleCommandWithArgsDelegate::CreateLambda([](const TArray<FString>& A) { if (A.Num()) { GMusicVolume = FMath::Clamp(FCString::Atof(*A[0]), 0.f, 1.f); } }));
	FAutoConsoleCommand CmdMusicMood(TEXT("astra.music.mood"), TEXT("Force the music: silence|calm|tension|battle|aftermath|auto"),
		FConsoleCommandWithArgsDelegate::CreateLambda([](const TArray<FString>& A)
		{
			if (!A.Num()) { return; }
			const FString M = A[0].ToLower();
			GForcedMood = M == TEXT("silence") ? 0 : M == TEXT("calm") ? 1 : M == TEXT("tension") ? 2 : M == TEXT("battle") ? 3 : M == TEXT("aftermath") ? 4 : -1;
		}));

	const TCHAR* MoodName(EAstraMood M)
	{
		switch (M)
		{
		case EAstraMood::Calm: return TEXT("calm");
		case EAstraMood::Tension: return TEXT("tension");
		case EAstraMood::Battle: return TEXT("battle");
		case EAstraMood::Aftermath: return TEXT("aftermath");
		default: return TEXT("silence");
		}
	}
}

bool UAstraMusicSubsystem::ShouldCreateSubsystem(UObject* Outer) const
{
	const UWorld* World = Cast<UWorld>(Outer);
	return World && (World->WorldType == EWorldType::Game || World->WorldType == EWorldType::PIE);
}

void UAstraMusicSubsystem::OnWorldBeginPlay(UWorld& InWorld)
{
	Super::OnWorldBeginPlay(InWorld);
	auto Load = [](const TCHAR* Name) { return LoadObject<USoundBase>(nullptr, *FString::Printf(TEXT("/Game/ASTRA/Audio/Music/%s.%s"), Name, Name)); };
	Cues.Add(EAstraMood::Calm, Load(TEXT("MX_Aurelia")));
	Cues.Add(EAstraMood::Tension, Load(TEXT("MX_Tension")));
	Cues.Add(EAstraMood::Battle, Load(TEXT("MX_Battle")));
	Cues.Add(EAstraMood::Aftermath, Load(TEXT("MX_Aftermath")));
	TransitCue = Load(TEXT("MX_Transit"));
	Since = 0.f;
	EvalT = 6.f;   // a few seconds of the bridge's own sound before the music comes in
	UE_LOG(LogASTRA, Log, TEXT("[Music] score loaded: %d cues"), Cues.Num());
}

EAstraMood UAstraMusicSubsystem::Wanted(float Dt)
{
	if (GForcedMood >= 0)
	{
		return (EAstraMood)GForcedMood;
	}
	const UAstraBattleSubsystem* Battle = GetWorld()->GetSubsystem<UAstraBattleSubsystem>();
	const UAstraShipSubsystem* Ship = GetWorld()->GetSubsystem<UAstraShipSubsystem>();
	if (!Battle || !Ship)
	{
		return EAstraMood::Calm;
	}
	const int32 Near = Battle->HostilesFighting(35.0);
	const int32 Far = Battle->HostilesFighting(150.0);
	const int32 Inbound = Battle->GetFireControl().Inbound;
	const bool bShooting = !Battle->GetFireControl().Target.IsEmpty();
	if ((Battle->IsEngaged() && Near > 0) || Inbound > 0 || (bShooting && Near > 0))
	{
		BattleHold = 20.f;
	}
	BattleHold = FMath::Max(0.f, BattleHold - Dt);
	if (BattleHold > 0.f)
	{
		return EAstraMood::Battle;
	}
	if (Far > 0 || Ship->GetAlert() == EAstraAlert::Red)
	{
		return EAstraMood::Tension;
	}
	if (Battle->SecondsSinceEngagement() < 110.f)
	{
		return EAstraMood::Aftermath;
	}
	return EAstraMood::Calm;
}

void UAstraMusicSubsystem::Play(EAstraMood NewMood, float Fade)
{
	if (Current)
	{
		Current->FadeOut(Fade, 0.f);
		Current = nullptr;
	}
	Mood = NewMood;
	Since = 0.f;
	USoundBase* S = Cues.FindRef(NewMood);
	if (!S)
	{
		return;
	}
	Current = UGameplayStatics::CreateSound2D(GetWorld(), S, 1.f, 1.f, 0.f, nullptr, false, true);
	if (Current)
	{
		Current->bIsUISound = false;
		Current->SetVolumeMultiplier(GMusicVolume * Duck);
		// a battle starts at the top (the drums); the others at a random place, so the calm never sounds the same
		const float Start = NewMood == EAstraMood::Battle ? 0.f : FMath::FRandRange(0.f, FMath::Max(0.f, S->GetDuration() - 30.f));
		Current->FadeIn(NewMood == EAstraMood::Battle ? FMath::Min(Fade, 1.5f) : Fade, 1.f, Start);
	}
	UE_LOG(LogASTRA, Log, TEXT("[Music] %s"), MoodName(NewMood));
}

void UAstraMusicSubsystem::Tick(float DeltaTime)
{
	SCOPE_CYCLE_COUNTER(STAT_AstraMusic);
	Since += DeltaTime;
	// the officers must be understood: the music steps back while any of them speaks
	bool bSpeaking = false;
	for (TActorIterator<AAstraCrewMember> It(GetWorld()); It && !bSpeaking; ++It)
	{
		bSpeaking = It->IsSpeaking();
	}
	Duck = FMath::FInterpTo(Duck, bSpeaking ? 0.55f : 1.f, DeltaTime, bSpeaking ? 6.f : 1.2f);
	if (Current)
	{
		Current->SetVolumeMultiplier(GMusicVolume * Duck);
	}
	// the Janus lane: the swell is timed so that its hit lands on the crossing
	const UAstraBattleSubsystem* Battle = GetWorld()->GetSubsystem<UAstraBattleSubsystem>();
	const float LaneLeft = Battle ? Battle->LaneSecondsLeft() : -1.f;
	if (LaneLeft >= 0.f)
	{
		if (!bTransitPlayed && TransitCue && LaneLeft <= 8.f)
		{
			bTransitPlayed = true;
			if (Current)
			{
				Current->FadeOut(2.5f, 0.f);
				Current = nullptr;
			}
			Mood = EAstraMood::Silence;
			Stinger = UGameplayStatics::CreateSound2D(GetWorld(), TransitCue, 1.f, 1.f, 0.f, nullptr, false, true);
			if (Stinger)
			{
				Stinger->SetVolumeMultiplier(FMath::Min(1.f, GMusicVolume * 1.8f));
				Stinger->Play(FMath::Max(0.f, 8.f - LaneLeft));
			}
		}
		return;
	}
	if (bTransitPlayed)
	{
		bTransitPlayed = false;
		AfterTransit = 0.f;
	}
	if (AfterTransit >= 0.f)
	{
		AfterTransit += DeltaTime;
		if (AfterTransit < 7.f)
		{
			return;   // the stinger's tail and the arrival, then the new system's music
		}
		AfterTransit = -1.f;
		EvalT = 0.f;
	}
	if ((EvalT -= DeltaTime) > 0.f)
	{
		return;
	}
	EvalT = 1.f;
	const EAstraMood Want = Wanted(1.f);
	// change when it matters: battle at once, the rest after the current mood has had its time
	if (Want != Mood && (Want == EAstraMood::Battle || Mood == EAstraMood::Silence || Since > 12.f))
	{
		Play(Want, Want == EAstraMood::Battle ? 1.2f : (Mood == EAstraMood::Battle ? 5.f : 4.f));
	}
}
