// ASTRA — link to astra-mind (the crew's minds and voices, mind/): WebSocket client, command routing, voice routing.

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "Containers/Ticker.h"
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

	/** Launch `uv run astra-mind` automatically when nothing is listening. */
	UPROPERTY(config)
	bool bAutoLaunchMind = true;

private:
	TSharedPtr<IWebSocket> Socket;
	FTSTicker::FDelegateHandle TickHandle;
	double NextConnectTime = 0.0;
	double NextStateTime = 0.0;
	bool bLaunchedMind = false;
	int32 ConnectFailures = 0;
	TArray<uint8> BinaryBuffer;
	TMap<int32, FString> LineSpeakers;
	UPROPERTY() TObjectPtr<class UAudioComponent> ChannelAudio;
	UPROPERTY() TObjectPtr<class USoundWaveProcedural> ChannelWave;
	int32 ChannelLine = -1;
	void BeginChannelLine(int32 LineId, int32 Rate);
	FDelegateHandle ShipEventHandle;
	TWeakObjectPtr<UWorld> BoundWorld;

	bool Tick(float DeltaTime);
	void Connect();
	void LaunchMind();
	void Send(const TSharedRef<FJsonObject>& Msg);
	void OnText(const FString& Text);
	void OnBinary(const void* Data, SIZE_T Size, SIZE_T BytesRemaining);
	void HandleCommand(const TSharedPtr<FJsonObject>& Msg);
	void BindShipEvents();
	UWorld* GameWorld() const;
};
