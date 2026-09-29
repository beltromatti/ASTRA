// ASTRA — link to astra-mind.

#include "AstraMindSubsystem.h"
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
#include "Sound/SoundWaveProcedural.h"

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
	Screen(FString::Printf(TEXT("Captain: %s"), *Text), FColor(255, 214, 120));
	TSharedRef<FJsonObject> M = MakeShared<FJsonObject>();
	M->SetStringField(TEXT("type"), TEXT("player_text"));
	M->SetStringField(TEXT("text"), Text);
	Send(M);
}

void UAstraMindSubsystem::PushToTalk(bool bDown)
{
	TSharedRef<FJsonObject> M = MakeShared<FJsonObject>();
	M->SetStringField(TEXT("type"), TEXT("ptt"));
	M->SetBoolField(TEXT("down"), bDown);
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
		const FString Speaker = Msg->GetStringField(TEXT("speaker"));
		LineSpeakers.Add(Id, Speaker);
		LineTexts.Add(Id, TPair<FString, FString>(Msg->GetStringField(TEXT("name")), Msg->GetStringField(TEXT("text"))));
		UE_LOG(LogASTRA, Log, TEXT("[Crew] %s: %s"), *Speaker, *Msg->GetStringField(TEXT("text")));
	}
	else if (Type == TEXT("audio_begin"))
	{
		const int32 Id = (int32)Msg->GetNumberField(TEXT("line"));
		// the subtitle comes up with the voice
		if (const TPair<FString, FString>* T = LineTexts.Find(Id))
		{
			if (AASTRAPlayerController* PC = Cast<AASTRAPlayerController>(UGameplayStatics::GetPlayerController(GameWorld(), 0)))
			{
				PC->Subtitle(Id, Msg->GetStringField(TEXT("speaker")), T->Key, T->Value);
			}
			HeardLines.Add(*T);
			if (HeardLines.Num() > 12)
			{
				HeardLines.RemoveAt(0);
			}
			LineTexts.Remove(Id);
		}
		AAstraCrewMember* Crew = AAstraCrewMember::FindByStation(GameWorld(), Msg->GetStringField(TEXT("speaker")));
		// an officer the Captain can hear in person speaks from their station; one far away (the Captain on the flight
		// deck, in a Falcon, down on New Ravenna) comes over the intercom or the radio
		bool bNear = false;
		if (Crew)
		{
			if (const APlayerCameraManager* Cam = UGameplayStatics::GetPlayerCameraManager(GameWorld(), 0))
			{
				bNear = FVector::Dist(Cam->GetCameraLocation(), Crew->GetActorLocation()) < 2500.f;
			}
			// the people in the Medbay and the Mess Hall speak only while the Captain is there: always in person, from
			// their place (a far table is simply quieter, never a voice on the radio)
			bNear |= Crew->StationId.StartsWith(TEXT("mess")) || Crew->StationId.StartsWith(TEXT("patient"));
		}
		if (Crew && bNear)
		{
			Crew->BeginLine(Id, (int32)Msg->GetNumberField(TEXT("rate")));
		}
		else
		{
			if (Crew)
			{
				LineSpeakers.Remove(Id);   // not a spoken line at the station: its audio goes to the radio
			}
			BeginChannelLine(Id, (int32)Msg->GetNumberField(TEXT("rate")));
		}
	}
	else if (Type == TEXT("audio_end"))
	{
		const int32 Id = (int32)Msg->GetNumberField(TEXT("line"));
		if (AASTRAPlayerController* PC = Cast<AASTRAPlayerController>(UGameplayStatics::GetPlayerController(GameWorld(), 0)))
		{
			PC->SubtitleEnd(Id);
		}
		if (const FString* Sp = LineSpeakers.Find(Id))
		{
			if (AAstraCrewMember* Crew = AAstraCrewMember::FindByStation(GameWorld(), *Sp))
			{
				Crew->EndLine(Id);
			}
		}
	}
	else if (Type == TEXT("transcript"))
	{
		Screen(FString::Printf(TEXT("Captain (%s): %s"), *Msg->GetStringField(TEXT("lang")), *Msg->GetStringField(TEXT("text"))), FColor(255, 214, 120));
	}
	else if (Type == TEXT("status"))
	{
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
	if (LineId == ChannelLine && ChannelWave)
	{
		ChannelWave->QueueAudio(BinaryBuffer.GetData() + 4, BinaryBuffer.Num() - 4);
	}
	else if (const FString* Sp = LineSpeakers.Find(LineId))
	{
		if (AAstraCrewMember* Crew = AAstraCrewMember::FindByStation(GameWorld(), *Sp))
		{
			Crew->QueueVoice(LineId, BinaryBuffer.GetData() + 4, BinaryBuffer.Num() - 4);
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

void UAstraMindSubsystem::BeginChannelLine(int32 LineId, int32 Rate)
{
	UWorld* World = GameWorld();
	if (!World)
	{
		return;
	}
	if (!ChannelAudio || !IsValid(ChannelAudio))
	{
		// a 2D "radio": band-limited like a comms channel (the Interpreter's translation of the enemy's voice)
		ChannelAudio = UGameplayStatics::CreateSound2D(World, nullptr, 1.f, 1.f, 0.f, nullptr, true, false);
		if (ChannelAudio)
		{
			ChannelAudio->SetLowPassFilterEnabled(true);
			ChannelAudio->SetLowPassFilterFrequency(3600.f);
			ChannelAudio->SetHighPassFilterEnabled(true);
			ChannelAudio->SetHighPassFilterFrequency(320.f);
		}
	}
	if (!ChannelAudio)
	{
		return;
	}
	ChannelLine = LineId;
	ChannelWave = NewObject<USoundWaveProcedural>(this);
	ChannelWave->SetSampleRate(Rate);
	ChannelWave->NumChannels = 1;
	ChannelWave->Duration = INDEFINITELY_LOOPING_DURATION;
	ChannelWave->SoundGroup = SOUNDGROUP_Voice;
	ChannelWave->bLooping = false;
	ChannelAudio->SetSound(ChannelWave);
	ChannelAudio->Play();
	UE_LOG(LogASTRA, Log, TEXT("[Mind] channel voice (line %d)"), LineId);
}
