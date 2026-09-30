// ASTRA — link to astra-mind.

#include "AstraMindSubsystem.h"
#include "AstraHarness.h"
#include "ASTRAPlayerController.h"

#include "Camera/PlayerCameraManager.h"

#include "ASTRA.h"
#include "AstraCrewMember.h"
#include "AstraShipSubsystem.h"
#include "Dom/JsonObject.h"
#include "Engine/Engine.h"
#include "Engine/GameInstance.h"
#include "Engine/World.h"
#include "HAL/IConsoleManager.h"
#include "HAL/FileManager.h"
#include "HAL/PlatformProcess.h"
#include "IWebSocket.h"
#include "Misc/Paths.h"
#include "Modules/ModuleManager.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "WebSocketsModule.h"
#include "Components/AudioComponent.h"
#include "Kismet/GameplayStatics.h"
#include "AstraSettings.h"
#include "AstraVoiceWave.h"

namespace
{
	const TCHAR* MindUrl = TEXT("ws://127.0.0.1:8765");
	UAstraMindSubsystem* GActiveMind = nullptr;

	FAutoConsoleCommand CmdSay(TEXT("astra.say"), TEXT("Speak to the bridge crew as the Captain (typed): astra.say <text>"),
		FConsoleCommandWithArgsDelegate::CreateLambda([](const TArray<FString>& Args)
		{
			if (GActiveMind)
			{
				GActiveMind->SayText(FString::Join(Args, TEXT(" ")));
			}
		}));
	FAutoConsoleCommand CmdPtt(TEXT("astra.ptt"), TEXT("Push-to-talk: astra.ptt 1 | astra.ptt 0"),
		FConsoleCommandWithArgsDelegate::CreateLambda([](const TArray<FString>& Args)
		{
			if (GActiveMind && Args.Num() > 0)
			{
				GActiveMind->PushToTalk(Args[0] == TEXT("1"));
			}
		}));

	/** A line the player should read (the Captain's own words, a system notice): the game's subtitles. */
	int32 GNoticeId = -1000;
	void Screen(const FString& S, const FColor& C, float Time = 6.f)
	{
		UWorld* W = GActiveMind ? GActiveMind->GameWorld() : nullptr;
		if (AASTRAPlayerController* PC = W ? Cast<AASTRAPlayerController>(UGameplayStatics::GetPlayerController(W, 0)) : nullptr)
		{
			FString Name, Text = S;
			S.Split(TEXT(": "), &Name, &Text);
			PC->Subtitle(--GNoticeId, Name.StartsWith(TEXT("Captain")) ? TEXT("captain") : TEXT("notice"), Name.IsEmpty() ? TEXT("SHIP") : Name, Text);
		}
	}
}

void UAstraMindSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);
	GActiveMind = this;
	FModuleManager::LoadModuleChecked<FWebSocketsModule>(TEXT("WebSockets"));
	TickHandle = FTSTicker::GetCoreTicker().AddTicker(FTickerDelegate::CreateUObject(this, &UAstraMindSubsystem::Tick), 0.0f);
	NextConnectTime = FPlatformTime::Seconds() + 0.5;
	if (FParse::Param(FCommandLine::Get(), TEXT("astra_nomind")))
	{
		// testing (performance runs): no mind, no connection, no credit spent
		bAutoLaunchMind = false;
		NextConnectTime = TNumericLimits<double>::Max();
	}
#if !WITH_EDITOR
	// the app draws nothing while it is in the background (battery, heat: a fanless Mac); a cheat cvar, so it is set
	// here rather than in an ini (the editor, driven from outside while in the background, must not idle)
	if (IConsoleVariable* Idle = IConsoleManager::Get().FindConsoleVariable(TEXT("t.IdleWhenNotForeground")))
	{
		Idle->Set(1, ECVF_SetByCode);
	}
#endif
}

void UAstraMindSubsystem::Deinitialize()
{
	FTSTicker::GetCoreTicker().RemoveTicker(TickHandle);
	if (Socket.IsValid())
	{
		Socket->Close();
		Socket.Reset();
	}
	if (GActiveMind == this)
	{
		GActiveMind = nullptr;
	}
#if !WITH_EDITOR
	// a packaged game takes its mind with it (in the editor it stays up between play sessions: its voices load slowly)
	if (MindProc.IsValid() && FPlatformProcess::IsProcRunning(MindProc))
	{
		FPlatformProcess::TerminateProc(MindProc, true);
	}
#endif
	Super::Deinitialize();
}

bool UAstraMindSubsystem::IsConnected() const
{
	return Socket.IsValid() && Socket->IsConnected();
}

UWorld* UAstraMindSubsystem::GameWorld() const
{
	const UGameInstance* GI = GetGameInstance();
	return GI ? GI->GetWorld() : nullptr;
}

void UAstraMindSubsystem::Connect()
{
	Socket = FWebSocketsModule::Get().CreateWebSocket(MindUrl, TEXT(""));
	Socket->OnConnected().AddLambda([this]()
	{
		ConnectFailures = 0;
		UE_LOG(LogASTRA, Log, TEXT("[Mind] connected"));
		TSharedRef<FJsonObject> Hello = MakeShared<FJsonObject>();
		Hello->SetStringField(TEXT("type"), TEXT("hello"));
		Hello->SetStringField(TEXT("client"), TEXT("ue"));
		Send(Hello);
		NextStateTime = 0.0;
		if (!PendingCampaign.IsEmpty())
		{
			const FString Mode = PendingCampaign;
			PendingCampaign.Empty();
			SendCampaign(Mode);
		}
		if (PendingEvents.Num())
		{
			if (UWorld* W = GameWorld())
			{
				if (UAstraShipSubsystem* S = W->GetSubsystem<UAstraShipSubsystem>())
				{
					TSharedRef<FJsonObject> St = MakeShared<FJsonObject>();
					St->SetStringField(TEXT("type"), TEXT("ship_state"));
					St->SetObjectField(TEXT("state"), S->Snapshot());
					Send(St);
				}
			}
			for (const TSharedRef<FJsonObject>& E : PendingEvents)
			{
				Send(E);
			}
			PendingEvents.Reset();
		}
	});
	Socket->OnConnectionError().AddLambda([this](const FString& Error)
	{
		++ConnectFailures;
		UE_LOG(LogASTRA, Verbose, TEXT("[Mind] connection error: %s"), *Error);
		if (ConnectFailures == 2 && bAutoLaunchMind && !bLaunchedMind)
		{
			LaunchMind();
		}
		NextConnectTime = FPlatformTime::Seconds() + 2.0;
	});
	Socket->OnClosed().AddLambda([this](int32 Code, const FString& Reason, bool bClean)
	{
		UE_LOG(LogASTRA, Log, TEXT("[Mind] closed (%d) %s"), Code, *Reason);
		NextConnectTime = FPlatformTime::Seconds() + 2.0;
		// nobody has the floor any more (the music comes back), and the lines in flight will not be finished
		FloorState = TEXT("idle");
		VoiceProtocol = 1;
		for (TPair<int32, FVoiceLine>& P : Voices)
		{
			if (UAudioComponent* C = P.Value.Comp.Get())
			{
				C->FadeOut(0.3f, 0.f);
			}
		}
		Voices.Reset();
		ExternalLineId = -1;
		ExternalSpeaker.Reset();
		ExternalLine.Reset();
	});
	Socket->OnMessage().AddUObject(this, &UAstraMindSubsystem::OnText);
	Socket->OnRawMessage().AddUObject(this, &UAstraMindSubsystem::OnBinary);
	Socket->Connect();
}

void UAstraMindSubsystem::LaunchMind()
{
	bLaunchedMind = true;
	FString MindDir = FPaths::ConvertRelativePathToFull(FPaths::ProjectDir() / TEXT("mind"));
	const FString Saved = FPaths::ConvertRelativePathToFull(FPaths::ProjectSavedDir());
	const FString LogFile = Saved / TEXT("Logs/astra-mind.log");
	IFileManager::Get().MakeDirectory(*(Saved / TEXT("Logs")), true);
	// the game's Saved folder is where the campaign lives: the mind keeps the war and the story beside it
	FString Env = FString::Printf(TEXT("ASTRA_SAVED='%s' "), *Saved);
	if (!FPaths::FileExists(MindDir / TEXT("pyproject.toml")))
	{
		// a packaged game: the mind travels inside the app bundle (Contents/Resources/mind); its own data (the key, the
		// voice models, its Python environment, caches) lives in Application Support/ASTRA
		MindDir = FPaths::ConvertRelativePathToFull(FPaths::Combine(FPaths::GetPath(FString(FPlatformProcess::ExecutablePath())), TEXT("../Resources/mind")));
#if PLATFORM_MAC
		const FString Home = FPlatformMisc::GetEnvironmentVariable(TEXT("HOME")) / TEXT("Library/Application Support/ASTRA");
#else
		const FString Home = FPaths::ConvertRelativePathToFull(FPaths::Combine(FPlatformProcess::UserSettingsDir(), TEXT("ASTRA")));
#endif
		IFileManager::Get().MakeDirectory(*Home, true);
		Env += FString::Printf(TEXT("ASTRA_HOME='%s' UV_PROJECT_ENVIRONMENT='%s/venv' "), *Home, *Home);
	}
	const FString Cmd = FString::Printf(TEXT("-lc \"cd '%s' && %sexec uv run --frozen astra-mind >> '%s' 2>&1\""), *MindDir, *Env, *LogFile);
	UE_LOG(LogASTRA, Log, TEXT("[Mind] starting the mind from %s"), *MindDir);
	MindProc = FPlatformProcess::CreateProc(TEXT("/bin/zsh"), *Cmd, true, true, true, nullptr, 0, nullptr, nullptr);
	UE_LOG(LogASTRA, Log, TEXT("[Mind] launched astra-mind (%s)"), MindProc.IsValid() ? TEXT("ok") : TEXT("FAILED"));
}

namespace
{
	/** JSON has no NaN or infinity: a value gone bad somewhere in the ship (the serializer writes nan, inf) must not
	 *  cost the crew the whole message. Outside strings, those tokens become null. */
	FString NoNaN(const FString& In)
	{
		FString Out;
		Out.Reserve(In.Len());
		bool bInString = false;
		for (int32 i = 0; i < In.Len(); ++i)
		{
			const TCHAR C = In[i];
			if (bInString)
			{
				Out.AppendChar(C);
				if (C == TEXT('\\') && i + 1 < In.Len())
				{
					Out.AppendChar(In[++i]);
				}
				else if (C == TEXT('"'))
				{
					bInString = false;
				}
				continue;
			}
			if (C == TEXT('"'))
			{
				bInString = true;
				Out.AppendChar(C);
				continue;
			}
			bool bBad = false;
			for (const TCHAR* Token : {TEXT("-nan"), TEXT("nan"), TEXT("-inf"), TEXT("inf")})
			{
				const int32 N = FCString::Strlen(Token);
				if (FCString::Strncmp(*In + i, Token, N) == 0)
				{
					Out += TEXT("null");
					i += N - 1;
					bBad = true;
					break;
				}
			}
			if (!bBad)
			{
				Out.AppendChar(C);
			}
		}
		return Out;
	}
}

void UAstraMindSubsystem::Send(const TSharedRef<FJsonObject>& Msg)
{
	if (!IsConnected())
	{
		return;
	}
	FString Out;
	TSharedRef<TJsonWriter<>> W = TJsonWriterFactory<>::Create(&Out);
	FJsonSerializer::Serialize(Msg, W);
	Socket->Send(NoNaN(Out));
}

void UAstraMindSubsystem::SayText(const FString& Text)
{
	FAstraTimeline::Record(TEXT("captain"), Text);
	Screen(FString::Printf(TEXT("Captain: %s"), *Text), FColor(255, 214, 120));
	TSharedRef<FJsonObject> M = MakeShared<FJsonObject>();
	M->SetStringField(TEXT("type"), TEXT("player_text"));
	M->SetStringField(TEXT("text"), Text);
	AddContext(M);
	Send(M);
}

void UAstraMindSubsystem::AddContext(const TSharedRef<FJsonObject>& Msg) const
{
	// v2: where the Captain's words go — who hears them, who is being looked at, the open channel (ARCHITETTURA §3)
	const UWorld* World = GameWorld();
	if (const UAstraShipSubsystem* Ship = World ? World->GetSubsystem<UAstraShipSubsystem>() : nullptr)
	{
		Msg->SetObjectField(TEXT("context"), Ship->CaptainContext());
	}
}

void UAstraMindSubsystem::PushToTalk(bool bDown)
{
	bTalkKeyDown = bDown;
	TSharedRef<FJsonObject> M = MakeShared<FJsonObject>();
	M->SetStringField(TEXT("type"), TEXT("ptt"));
	M->SetBoolField(TEXT("down"), bDown);
	AddContext(M);
	Send(M);
}

void UAstraMindSubsystem::BindShipEvents()
{
	UWorld* World = GameWorld();
	if (!World || BoundWorld.Get() == World)
	{
		return;
	}
	if (UAstraShipSubsystem* Ship = World->GetSubsystem<UAstraShipSubsystem>())
	{
		BoundWorld = World;
		ShipEventHandle = Ship->OnShipEvent.AddLambda([this](const FString& Text, bool bReport)
		{
			// a report makes the crew speak: they must see the ship as it is now, not as it was up to a second ago
			const double Now = FPlatformTime::Seconds();
			if (bReport && Now - LastStateSent > 0.1)
			{
				if (UWorld* W = GameWorld())
				{
					if (UAstraShipSubsystem* S = W->GetSubsystem<UAstraShipSubsystem>())
					{
						TSharedRef<FJsonObject> St = MakeShared<FJsonObject>();
						St->SetStringField(TEXT("type"), TEXT("ship_state"));
						St->SetObjectField(TEXT("state"), S->Snapshot());
						Send(St);
						LastStateSent = Now;
						NextStateTime = Now + 1.0;
					}
				}
			}
			TSharedRef<FJsonObject> M = MakeShared<FJsonObject>();
			M->SetStringField(TEXT("type"), TEXT("event"));
			M->SetStringField(TEXT("text"), Text);
			M->SetBoolField(TEXT("report"), bReport);
			if (!IsConnected())
			{
				// the mind is still starting: keep what the crew must hear, deliver it once connected
				if (bReport && PendingEvents.Num() < 24)
				{
					PendingEvents.Add(M);
				}
				return;
			}
			Send(M);
		});
	}
}

bool UAstraMindSubsystem::Tick(float DeltaTime)
{
	const double Now = FPlatformTime::Seconds();
	BindShipEvents();   // even before the mind answers: the reports raised meanwhile are queued
	TickVoices();
	if (!Socket.IsValid() || (!Socket->IsConnected() && Now >= NextConnectTime))
	{
		if (Now >= NextConnectTime)
		{
			NextConnectTime = Now + 2.0;
			Connect();
		}
		return true;
	}
	if (IsConnected() && Now >= NextStateTime)
	{
		NextStateTime = Now + 1.0;
		LastStateSent = Now;
		if (UWorld* World = GameWorld())
		{
			if (UAstraShipSubsystem* Ship = World->GetSubsystem<UAstraShipSubsystem>())
			{
				TSharedRef<FJsonObject> M = MakeShared<FJsonObject>();
				M->SetStringField(TEXT("type"), TEXT("ship_state"));
				M->SetObjectField(TEXT("state"), Ship->Snapshot());
				Send(M);
			}
		}
	}
	return true;
}

void UAstraMindSubsystem::SendCampaign(const FString& Mode)
{
	if (!IsConnected())
	{
		PendingCampaign = Mode;
		return;
	}
	TSharedRef<FJsonObject> M = MakeShared<FJsonObject>();
	M->SetStringField(TEXT("type"), TEXT("campaign"));
	M->SetStringField(TEXT("mode"), Mode);
	Send(M);
}

void UAstraMindSubsystem::OnText(const FString& Text)
{
	TSharedPtr<FJsonObject> Msg;
	if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Msg) || !Msg.IsValid())
	{
		return;
	}
	const FString Type = Msg->GetStringField(TEXT("type"));
	if (Type == TEXT("command"))
	{
		HandleCommand(Msg);
	}
	else if (Type == TEXT("line"))
	{
		const int32 Id = (int32)Msg->GetNumberField(TEXT("id"));
		LineTexts.Add(Id, TPair<FString, FString>(Msg->GetStringField(TEXT("name")), Msg->GetStringField(TEXT("text"))));
		UE_LOG(LogASTRA, Log, TEXT("[Crew] %s: %s"), *Msg->GetStringField(TEXT("speaker")), *Msg->GetStringField(TEXT("text")));
	}
	else if (Type == TEXT("audio_begin"))
	{
		const int32 Id = (int32)Msg->GetNumberField(TEXT("line"));
		const FString Speaker = Msg->GetStringField(TEXT("speaker"));
		const int32 Rate = (int32)Msg->GetNumberField(TEXT("rate"));
		// the subtitle comes up with the voice and stays as long as the audio and a second, or as long as reading it
		// takes, whichever is longer (protocollo_voce §3.1: the mind says how long)
		if (const TPair<FString, FString>* T = LineTexts.Find(Id))
		{
			double EstS = 0.0, HoldS = 0.0;
			Msg->TryGetNumberField(TEXT("est_s"), EstS);
			if (!Msg->TryGetNumberField(TEXT("hold_s"), HoldS) || HoldS <= 0.0)
			{
				HoldS = FMath::Min(12.0, FMath::Max(EstS + 1.0, 1.4 + T->Value.Len() / 17.0));
			}
			if (AASTRAPlayerController* PC = Cast<AASTRAPlayerController>(UGameplayStatics::GetPlayerController(GameWorld(), 0)))
			{
				PC->Subtitle(Id, Speaker, T->Key, T->Value, (float)HoldS, true);
			}
			HeardLines.Add(*T);
			if (HeardLines.Num() > 12)
			{
				HeardLines.RemoveAt(0);
			}
			LineTexts.Remove(Id);
		}
		AAstraCrewMember* Crew = AAstraCrewMember::FindByStation(GameWorld(), Speaker);
		if (!Crew)
		{
			// not one of ours: a voice over a channel (the main viewscreen shows who is speaking)
			ExternalLineId = Id;
			if (const TPair<FString, FString>* T = HeardLines.Num() ? &HeardLines.Last() : nullptr)
			{
				ExternalSpeaker = T->Key;
				ExternalLine = T->Value;
			}
		}
		// an officer the Captain can hear in person speaks from their station; one far away or behind a wall (the Chief
		// in Engineering, anyone while the Captain is on the flight deck, in a Falcon, down on New Ravenna) comes over the
		// intercom or the radio
		const bool bInPerson = Crew && !HeardOnRadio(Crew);
		FVoiceLine V;
		UAstraVoiceWave* Wave = nullptr;
		if (bInPerson)
		{
			Wave = Crew->BeginLine(Id, Rate);
			V.Crew = Crew;
			V.Comp = Crew->GetVoice();
		}
		else
		{
			Wave = BeginChannelLine(Id, Rate);
			V.Comp = ChannelAudio;
		}
		if (!Wave)
		{
			SendVoiceStatus(Id, TEXT("failed"), bInPerson ? TEXT("the officer's voice did not start (Play)") : TEXT("the radio did not start (no audio component or Play)"));
		}
		else
		{
			V.Wave = Wave;
			V.From = Wave->GetQueued();
			Voices.Add(Id, V);
		}
	}
	else if (Type == TEXT("audio_end"))
	{
		const int32 Id = (int32)Msg->GetNumberField(TEXT("line"));
		FString Reason;
		Msg->TryGetStringField(TEXT("reason"), Reason);
		if (Reason == TEXT("cut"))
		{
			CancelVoice(Id, 0.14f);   // follows a cancel (already done); without one, it is one
			return;
		}
		if (FVoiceLine* V = Voices.Find(Id))
		{
			V->bEnded = true;
		}
		if (Id == ExternalLineId)
		{
			ExternalLineId = -1;
			ExternalSpeaker.Reset();
			ExternalLine.Reset();
		}
		if (AASTRAPlayerController* PC = Cast<AASTRAPlayerController>(UGameplayStatics::GetPlayerController(GameWorld(), 0)))
		{
			PC->SubtitleEnd(Id);
		}
	}
	else if (Type == TEXT("cancel"))
	{
		// stop this line now: the Captain took the floor, an answer or a warning comes first (protocollo_voce §3.2)
		double FadeMs = 140.0;
		Msg->TryGetNumberField(TEXT("fade_ms"), FadeMs);
		CancelVoice((int32)Msg->GetNumberField(TEXT("line")), (float)(FadeMs / 1000.0));
	}
	else if (Type == TEXT("floor"))
	{
		Msg->TryGetStringField(TEXT("state"), FloorState);
	}
	else if (Type == TEXT("line_dropped"))
	{
		UE_LOG(LogASTRA, Verbose, TEXT("[Mind] line %d dropped (%s): %s"), (int32)Msg->GetNumberField(TEXT("id")),
		       *Msg->GetStringField(TEXT("reason")), *Msg->GetStringField(TEXT("text")));
	}
	else if (Type == TEXT("transcript"))
	{
		FAstraTimeline::Record(TEXT("heard"), FString::Printf(TEXT("[%s] %s"), *Msg->GetStringField(TEXT("lang")), *Msg->GetStringField(TEXT("text"))));
		Screen(FString::Printf(TEXT("Captain (%s): %s"), *Msg->GetStringField(TEXT("lang")), *Msg->GetStringField(TEXT("text"))), FColor(255, 214, 120));
	}
	else if (Type == TEXT("status"))
	{
		double Voice = 0.0;
		if (Msg->TryGetNumberField(TEXT("voice"), Voice))
		{
			VoiceProtocol = (int32)Voice;
		}
		FString Mic;
		if (Msg->TryGetStringField(TEXT("mic"), Mic))
		{
			Screen(FString::Printf(TEXT("Microphone %s (allow microphone access for the game in System Settings)"), *Mic), FColor::Orange, 10.f);
		}
	}
}

void UAstraMindSubsystem::OnBinary(const void* Data, SIZE_T Size, SIZE_T BytesRemaining)
{
	BinaryBuffer.Append(static_cast<const uint8*>(Data), (int32)Size);
	if (BytesRemaining > 0 || BinaryBuffer.Num() < 4)
	{
		return;
	}
	int32 LineId = 0;
	FMemory::Memcpy(&LineId, BinaryBuffer.GetData(), 4);
	// a line's audio: uint32 id + PCM16 mono, at listening pace (a line stopped by a cancel has no record: dropped)
	if (FVoiceLine* V = Voices.Find(LineId))
	{
		if (UAstraVoiceWave* Wave = V->Wave.Get())
		{
			const uint8* Pcm = BinaryBuffer.GetData() + 4;
			const int32 N = (BinaryBuffer.Num() - 4) & ~1;
			Wave->Queue(Pcm, N);
			V->Bytes += N;
			if (V->FirstBytesAt < 0.0)
			{
				V->FirstBytesAt = FPlatformTime::Seconds();
			}
			if (AAstraCrewMember* Crew = V->Crew.Get())
			{
				Crew->HearVoice(Pcm, N);
			}
		}
	}
	BinaryBuffer.Reset();
}

void UAstraMindSubsystem::HandleCommand(const TSharedPtr<FJsonObject>& Msg)
{
	const FString Id = Msg->GetStringField(TEXT("id"));
	const FString Name = Msg->GetStringField(TEXT("name"));
	const TSharedPtr<FJsonObject>* Args = nullptr;
	Msg->TryGetObjectField(TEXT("args"), Args);
	bool bOk = false;
	FString Detail = TEXT("ship systems unavailable");
	if (UWorld* World = GameWorld())
	{
		if (UAstraShipSubsystem* Ship = World->GetSubsystem<UAstraShipSubsystem>())
		{
			bOk = Ship->ApplyCommand(Name, Args ? *Args : nullptr, Detail);
		}
	}
	UE_LOG(LogASTRA, Log, TEXT("[Ship] %s -> %s: %s"), *Name, bOk ? TEXT("ok") : TEXT("FAILED"), *Detail);
	FString By;
	if (bOk && Msg->TryGetStringField(TEXT("by"), By))
	{
		// the officer's console acknowledges the input (a soft chirp at the station)
		if (AAstraCrewMember* Crew = AAstraCrewMember::FindByStation(GameWorld(), By))
		{
			if (USoundBase* Chirp = LoadObject<USoundBase>(nullptr, TEXT("/Game/ASTRA/Audio/SW_Console_Chirp.SW_Console_Chirp")))
			{
				UGameplayStatics::PlaySoundAtLocation(Crew, Chirp, Crew->GetActorLocation() + Crew->GetActorForwardVector() * 60.f + FVector(0, 0, 80.f), 0.45f,
				                                      FMath::FRandRange(0.97f, 1.03f));
			}
		}
	}
	TSharedRef<FJsonObject> R = MakeShared<FJsonObject>();
	R->SetStringField(TEXT("type"), TEXT("command_result"));
	R->SetStringField(TEXT("id"), Id);
	R->SetBoolField(TEXT("ok"), bOk);
	R->SetStringField(TEXT("detail"), Detail);
	Send(R);
}

UAstraVoiceWave* UAstraMindSubsystem::BeginChannelLine(int32 LineId, int32 Rate)
{
	UWorld* World = GameWorld();
	if (!World)
	{
		return nullptr;
	}
	if (ChannelAudio && (!IsValid(ChannelAudio) || ChannelAudio->GetWorld() != World))
	{
		ChannelAudio = nullptr;   // another world
		ChannelWave = nullptr;
	}
	if (ChannelAudio && ChannelWave && ChannelWave->GetRate() == Rate && ChannelAudio->IsPlaying() && ChannelWave->GetAvailableAudioByteCount() > 0)
	{
		// the last line is still sounding (the game fell behind the mind's clock): this one follows it, never cuts it
		UE_LOG(LogASTRA, Log, TEXT("[Mind] channel voice (line %d, after the last one)"), LineId);
		return ChannelWave;
	}
	ChannelWave = NewObject<UAstraVoiceWave>(this);
	ChannelWave->Setup(Rate);
	if (!ChannelAudio)
	{
		// a 2D "radio": band-limited like a comms channel (the Interpreter's translation of the enemy's voice); the
		// engine makes no component for a null sound, so the wave comes first
		ChannelAudio = UGameplayStatics::CreateSound2D(World, ChannelWave, 1.f, 1.f, 0.f, nullptr, true, false);
		if (ChannelAudio)
		{
			ChannelAudio->SetLowPassFilterEnabled(true);
			ChannelAudio->SetLowPassFilterFrequency(3600.f);
			ChannelAudio->SetHighPassFilterEnabled(true);
			ChannelAudio->SetHighPassFilterFrequency(320.f);
			ChannelAudio->bOverridePriority = true;
			ChannelAudio->Priority = 4.f;
			ChannelAudio->bIsUISound = false;
		}
	}
	else
	{
		ChannelAudio->SetSound(ChannelWave);
	}
	if (!ChannelAudio)
	{
		return nullptr;
	}
	// the band takes ~3.5 dB of loudness away: the radio must not sound quieter than a voice in the room (§4.1)
	ChannelAudio->SetVolumeMultiplier(1.5f * FAstraSettings::Get().Voices);
	ChannelAudio->Play();
	UE_LOG(LogASTRA, Log, TEXT("[Mind] channel voice (line %d)"), LineId);
	return ChannelAudio->IsPlaying() ? ChannelWave.Get() : nullptr;
}

bool UAstraMindSubsystem::HeardOnRadio(const AAstraCrewMember* Crew)
{
	// the people in the Medbay and the Mess Hall speak only while the Captain is there: always in person, from their
	// place (a far table is simply quieter, never a voice on the radio)
	if (Crew->StationId.StartsWith(TEXT("mess")) || Crew->StationId.StartsWith(TEXT("patient")))
	{
		return false;
	}
	const APlayerCameraManager* Cam = UGameplayStatics::GetPlayerCameraManager(GameWorld(), 0);
	if (!Cam)
	{
		return false;
	}
	const FVector Eye = Cam->GetCameraLocation();
	const float Dist = FVector::Dist(Eye, Crew->GetActorLocation());
	// one decision per officer, a line at a time (never mid-line): to the intercom beyond 28 m, back in the room under
	// 22 m (protocollo_voce §4.3) — a Captain standing about 25 m away does not hear the same officer swap from the
	// room to the radio and back from one line to the next
	bool* Radio = OnRadio.Find(Crew->StationId);
	if (!Radio)
	{
		Radio = &OnRadio.Add(Crew->StationId, Dist > 2500.f);
	}
	if (*Radio && Dist < 2200.f)
	{
		*Radio = false;
	}
	else if (!*Radio && Dist > 2800.f)
	{
		*Radio = true;
	}
	// a wall, a bulkhead or a closed door between them: the intercom, however near
	return *Radio || !Crew->CanBeHeardFrom(Eye, UGameplayStatics::GetPlayerPawn(GameWorld(), 0));
}

void UAstraMindSubsystem::CancelVoice(int32 LineId, float FadeSeconds)
{
	if (FVoiceLine* V = Voices.Find(LineId))
	{
		UE_LOG(LogASTRA, Log, TEXT("[Mind] voice of line %d: stopped (fade %.2f s)"), LineId, FadeSeconds);
		const TWeakObjectPtr<UAstraVoiceWave> Wave = V->Wave;
		if (AAstraCrewMember* Crew = V->Crew.Get())
		{
			Crew->CancelLine(FadeSeconds);
		}
		else if (ChannelAudio && Wave.Get() == ChannelWave)
		{
			ChannelAudio->FadeOut(FMath::Max(FadeSeconds, 0.02f), 0.f);
			ChannelWave = nullptr;   // the next line starts on a new wave
		}
		// the line stops here, and with it any earlier line still sounding on the same wave
		for (auto It = Voices.CreateIterator(); It; ++It)
		{
			if (It.Value().Wave == Wave)
			{
				It.RemoveCurrent();
			}
		}
	}
	LineTexts.Remove(LineId);
	if (LineId == ExternalLineId)
	{
		ExternalLineId = -1;
		ExternalSpeaker.Reset();
		ExternalLine.Reset();
	}
	if (AASTRAPlayerController* PC = Cast<AASTRAPlayerController>(UGameplayStatics::GetPlayerController(GameWorld(), 0)))
	{
		PC->SubtitleCancel(LineId);
	}
}

void UAstraMindSubsystem::SendVoiceStatus(int32 LineId, const TCHAR* State, const FString& Detail)
{
	UE_LOG(LogASTRA, Log, TEXT("[Mind] voice of line %d: %s %s"), LineId, State, *Detail);
	if (VoiceProtocol < 2)
	{
		return;
	}
	TSharedRef<FJsonObject> M = MakeShared<FJsonObject>();
	M->SetStringField(TEXT("type"), TEXT("voice_status"));
	M->SetNumberField(TEXT("line"), LineId);
	M->SetStringField(TEXT("state"), State);
	M->SetStringField(TEXT("detail"), Detail);
	Send(M);
}

void UAstraMindSubsystem::TickVoices()
{
	if (!Voices.Num())
	{
		return;
	}
	const double Now = FPlatformTime::Seconds();
	// a paused game pauses its voices: nothing is played, and that is neither a stall nor a failure
	const UWorld* World = GameWorld();
	const bool bPaused = World && World->IsPaused();
	if (bPaused || bVoicesPaused)
	{
		bVoicesPaused = bPaused;
		for (TPair<int32, FVoiceLine>& P : Voices)
		{
			P.Value.FirstBytesAt = P.Value.FirstBytesAt < 0.0 ? -1.0 : Now;
			P.Value.EmptySince = -1.0;
		}
		return;
	}
	for (auto It = Voices.CreateIterator(); It; ++It)
	{
		FVoiceLine& V = It.Value();
		UAstraVoiceWave* Wave = V.Wave.Get();
		if (!Wave)
		{
			It.RemoveCurrent();   // the world went away
			continue;
		}
		const int64 Played = Wave->GetPlayed();
		if (!V.bStarted)
		{
			if (Played > V.From)
			{
				V.bStarted = true;
				SendVoiceStatus(It.Key(), TEXT("started"), FString());
			}
			else if (V.FirstBytesAt >= 0.0 && Now - V.FirstBytesAt > 2.0)
			{
				// its audio came and none of it was played: the voice is not sounding (a component out of the mix?)
				SendVoiceStatus(It.Key(), TEXT("failed"), FString::Printf(TEXT("nothing played in 2 s (%s)"), V.Crew.IsValid() ? TEXT("in person") : TEXT("radio")));
				It.RemoveCurrent();
				continue;
			}
			else
			{
				continue;
			}
		}
		const bool bDrained = Played >= V.From + V.Bytes;
		if (V.bEnded && bDrained)
		{
			SendVoiceStatus(It.Key(), TEXT("finished"), FString());
			// heard to its end: the voice lets go of its audio channel, unless the next line already follows on the wave
			bool bNext = false;
			for (const TPair<int32, FVoiceLine>& O : Voices)
			{
				bNext |= O.Key != It.Key() && O.Value.Wave == V.Wave;
			}
			UAudioComponent* Comp = V.Comp.Get();
			if (!bNext && Comp && Comp->Sound == Wave)
			{
				Comp->Stop();
			}
			It.RemoveCurrent();
			continue;
		}
		if (!V.bEnded && bDrained)
		{
			// the queue ran dry before the line's end (a long frame of the game, a slow link): heard as a gap
			if (V.EmptySince < 0.0)
			{
				V.EmptySince = Now;
			}
			else if (!V.bStallSaid && Now - V.EmptySince > 0.25)
			{
				V.bStallSaid = true;
				SendVoiceStatus(It.Key(), TEXT("stalled"), TEXT("the audio queue ran dry for more than 250 ms"));
			}
		}
		else
		{
			V.EmptySince = -1.0;
		}
	}
}
