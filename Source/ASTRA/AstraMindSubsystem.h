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

	/** Launch `uv run astra-mind` automatically when nothing is listening. */
	UPROPERTY(config)
	bool bAutoLaunchMind = true;

private:
	TSharedPtr<IWebSocket> Socket;
	FTSTicker::FDelegateHandle TickHandle;
	double NextConnectTime = 0.0;
	double NextStateTime = 0.0;
	bool bLaunchedMind = false;
	FProcHandle MindProc;   // the mind this game started (a packaged game stops it when it quits)
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
	void TickVoices();
	void CancelVoice(int32 LineId, float FadeSeconds);
	void SendVoiceStatus(int32 LineId, const TCHAR* State, const FString& Detail);
	bool HeardOnRadio(const class AAstraCrewMember* Crew);
	FDelegateHandle ShipEventHandle;
	TWeakObjectPtr<UWorld> BoundWorld;

	bool Tick(float DeltaTime);
	void Connect();
	void LaunchMind();
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
	/** Someone not of the crew speaking now over a channel (the Archon, the Admiral, a controller): their name, else "". */
	const FString& GetExternalSpeaker() const { return ExternalSpeaker; }
	/** What they are saying (the line in flight). */
	const FString& GetExternalLine() const { return ExternalLine; }
	/** Someone has the floor (an officer or a voice on the radio speaks, or the Captain is speaking): the music steps
	 *  back. False from a mind that does not say (voice protocol 1): then the officers' own voices tell. */
	bool IsFloorTaken() const { return FloorState != TEXT("idle"); }
	bool SaysFloor() const { return VoiceProtocol >= 2 && IsConnected(); }

private:
	TArray<TPair<FString, FString>> HeardLines;
};
