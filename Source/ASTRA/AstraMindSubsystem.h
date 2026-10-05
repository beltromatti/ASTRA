// ASTRA — link to astra-mind (the crew's minds and voices, mind/): WebSocket client, command routing, voice routing.
#pragma once

#include "CoreMinimal.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "Containers/Ticker.h"
#include "HAL/PlatformProcess.h"
#include "AstraMindSubsystem.generated.h"

class IWebSocket;
class FJsonObject;

UCLASS(config = Game)
class ASTRA_API UAstraMindSubsystem : public UGameInstanceSubsystem
{
	GENERATED_BODY()

public:
	virtual void Initialize(FSubsystemCollectionBase& Collection) override;
	virtual void Deinitialize() override;

	/** Typed words from the Captain (also: console `astra.say <text>`). */
	void SayText(const FString& Text);

	/** Push-to-talk: the mind records the microphone while down. */
	void PushToTalk(bool bDown);

	bool IsConnected() const;

	/** The Captain chose: a new campaign or the saved one ("new" | "continue"); the mind resets or loads the war. */
	void SendCampaign(const FString& Mode);

	/** The LANGUAGE settings changed: the crew's language and whether it follows the Captain's voice. */
	void SendSettings();
	/** The player entered or replaced the OpenRouter key (AstraApiKey.h): the mind reads its .env again. */
	void SendKeyChanged();
	/** What the mind last said of OpenRouter: "ok" · "invalid_key" · "no_credit" · "rate_limited" · "offline". */
	const FString& GetAiState() const { return AiState; }

	/** Launch `uv run astra-mind` automatically when nothing is listening (AstraMindLaunch.h: macOS, Windows, Linux). */
	UPROPERTY(config)
	bool bAutoLaunchMind = true;

private:
	FString AiState = TEXT("ok");
	double AiNoticeAt = -1e9;
	void ShowAiState(const FString& State, const FString& Detail);
	TSharedPtr<IWebSocket> Socket;
	FTSTicker::FDelegateHandle TickHandle;
	double NextConnectTime = 0.0;
	double NextStateTime = 0.0;
	bool bLaunchedMind = false;
	FProcHandle MindProc;   // the mind this game started (a packaged game stops it when it quits)
	FString MindUrl;        // ws://127.0.0.1:<port>: 8765 unless ASTRA_MIND_PORT says another (AstraMindLaunch.h)
	FString MindLogFile;    // the file the mind writes its log to (the game adds a line to it when the mind it started is gone)
	double MindLaunchedAt = 0.0;
	double NextProcCheckTime = 0.0;
	bool bMindExitReported = false;   // the mind this game started is gone, and the player was told where its log is
	FString PendingCampaign;   // sent once connected
	double LastStateSent = 0.0;
	TArray<TSharedRef<FJsonObject>> PendingEvents;   // reports raised before the mind was reachable
	int32 ConnectFailures = 0;
	TArray<uint8> BinaryBuffer;
	FString ExternalSpeaker, ExternalLine;
	int32 ExternalLineId = -1;
	/** The radio: every voice that is not an officer heard in person (the enemy, the Admiral, a controller, an officer
	 *  far away or behind a wall), 2D and band-limited like a comms channel. */
	UPROPERTY() TObjectPtr<class UAudioComponent> ChannelAudio;
	UPROPERTY() TObjectPtr<class UAstraVoiceWave> ChannelWave;
	class UAstraVoiceWave* BeginChannelLine(int32 LineId, int32 Rate);
	/** The ship's computer (the lift cars: docs/ASCENSORI.md) speaks clean, all round, not over a radio band. */
	UPROPERTY() TObjectPtr<class UAudioComponent> ComputerAudio;
	UPROPERTY() TObjectPtr<class UAstraVoiceWave> ComputerWave;
	class UAstraVoiceWave* BeginComputerLine(int32 LineId, int32 Rate);
	/** The narrator of the story's cards (the end of a chapter, the loss of the ship, the introduction): clean, a little closer, and heard with the
	 *  game paused (a UI sound). Its words are on the card: no subtitle. */
	UPROPERTY() TObjectPtr<class UAudioComponent> NarratorAudio;
	UPROPERTY() TObjectPtr<class UAstraVoiceWave> NarratorWave;
	class UAstraVoiceWave* BeginNarratorLine(int32 LineId, int32 Rate);

	/** A line being heard (voice protocol 2, docs/protocollo_voce.md): where its audio goes and how much of it has been
	 *  played, so the game can tell the mind that a voice started, stalled, failed or finished. */
	struct FVoiceLine
	{
		TWeakObjectPtr<class UAstraVoiceWave> Wave;
		TWeakObjectPtr<class UAudioComponent> Comp;
		TWeakObjectPtr<class AAstraCrewMember> Crew;   // at the officer's place; unset: the radio
		int64 From = 0;           // the wave's bytes queued before this line
		int64 Bytes = 0;          // this line's bytes queued
		double FirstBytesAt = -1.0;
		double EmptySince = -1.0;
		bool bStarted = false;
		bool bEnded = false;      // audio_end came: all of it is queued
		bool bStallSaid = false;
	};
	TMap<int32, FVoiceLine> Voices;
	TMap<FString, bool> OnRadio;   // officer -> heard over the intercom (decided a line at a time, with hysteresis)
	int32 VoiceProtocol = 1;       // the mind's (status.voice)
	FString FloorState = TEXT("idle");   // who has the floor: idle | crew | captain (the mind's floor message)
	bool bVoicesPaused = false;
	bool bTalkKeyDown = false;
	void TickVoices();
	void CancelVoice(int32 LineId, float FadeSeconds);
	void SendVoiceStatus(int32 LineId, const TCHAR* State, const FString& Detail);
	bool HeardOnRadio(const class AAstraCrewMember* Crew);
	FDelegateHandle ShipEventHandle;
	TWeakObjectPtr<UWorld> BoundWorld;

	bool Tick(float DeltaTime);
	void Connect();
	void LaunchMind();
	/** Is the mind this game started still running? When it is not, the log and the player say where its own log is. */
	void WatchMindProcess(double Now);
	void Send(const TSharedRef<FJsonObject>& Msg);
	/** The Captain's context (protocol v2) on a player_text or ptt message. */
	void AddContext(const TSharedRef<FJsonObject>& Msg) const;
	void OnText(const FString& Text);
	void OnBinary(const void* Data, SIZE_T Size, SIZE_T BytesRemaining);
	void HandleCommand(const TSharedPtr<FJsonObject>& Msg);
	void BindShipEvents();
	TMap<int32, TPair<FString, FString>> LineTexts;   // line id -> (name, text): shown when its voice begins

public:
	UWorld* GameWorld() const;
	/** The last lines the crew spoke (name, text), as heard: the Captain's datapad keeps a comms log. */
	const TArray<TPair<FString, FString>>& GetHeardLines() const { return HeardLines; }
	/** A line of the radio nets' traffic (what Fleet, the allied captains, the flight net and the marines said: the Captain hears only what is addressed to him, or a net he asked for,
	 *  and reads the rest here) or a line an officer wrote on a console's log with the silent `console_log` tool (docs/protocollo_voce.md §5ter). The mind sends them; the comms and
	 *  flight consoles, the control surfaces and the datapad's log page show them. */
	struct FNetLine
	{
		FString Net;           // fleet | flight | marines; empty for a console log line
		FString Station;       // the console it belongs to: comms (the fleet net), flight (the flight net), xo (the marines), or the officer's own for a log line
		FString Who;           // who said it (a name), or the officer who wrote the log line
		FString Text;
		bool bUrgent = false;  // the sender said danger now
		bool bAloud = false;   // it was heard on the bridge's speaker (an answer to the Captain, a call to him, a net on the speaker)
		bool bNotice = false;  // a log line worth a glance
		double Time = 0.0;     // FPlatformTime::Seconds() when it came
	};
	/** Everything the nets and the logs said lately, oldest first. */
	const TArray<FNetLine>& GetNetLines() const { return NetLines; }
	/** The newest `Max` lines of one console (its own log lines and the traffic of the net it has the watch on), oldest first. */
	void GetConsoleLines(const FString& Station, int32 Max, TArray<FNetLine>& Out) const;
	/** The Captain asked to hear this net on the bridge's speaker (fleet | flight | marines). */
	bool IsNetOnSpeaker(const FString& Net) const { return NetsOnSpeaker.Contains(Net); }

	/** Someone not of the crew speaking now over a channel (the Archon, the Admiral, a controller): their name, else "". */
	const FString& GetExternalSpeaker() const { return ExternalSpeaker; }
	/** What they are saying (the line in flight). */
	const FString& GetExternalLine() const { return ExternalLine; }
	/** Someone has the floor (an officer or a voice on the radio speaks, or the Captain is speaking): the music steps
	 *  back. False from a mind that does not say (voice protocol 1): then the officers' own voices tell. */
	bool IsFloorTaken() const { return FloorState != TEXT("idle"); }
	bool SaysFloor() const { return VoiceProtocol >= 2 && IsConnected(); }
	/** The Captain holds the talk key (the game's own sound steps back so less of it reaches the microphone). */
	bool IsCaptainTalking() const { return bTalkKeyDown; }
	/** The Captain's words are with the crew: from the key going down until the answer begins (the mind's floor). */
	bool IsCaptainHeard() const { return bTalkKeyDown || (SaysFloor() && FloorState == TEXT("captain")); }

private:
	TArray<TPair<FString, FString>> HeardLines;
	TArray<FNetLine> NetLines;       // the nets' traffic and the consoles' log lines the mind sent (capped; cleared with each new session)
	TSet<FString> NetsOnSpeaker;     // the nets the Captain asked to hear
};
