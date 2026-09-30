// ASTRA — a voice's wave: the mind's PCM16 mono, queued as it arrives (docs/protocollo_voce.md §3.2).
#pragma once

#include "CoreMinimal.h"
#include "Sound/SoundWaveProcedural.h"
#include "AstraVoiceWave.generated.h"

/** The procedural wave a voice plays on (an officer's own voice, the radio). It counts what was queued, so the game can
 *  tell how much of a line has been heard: the audio renderer consumes the queue at listening pace. */
UCLASS()
class ASTRA_API UAstraVoiceWave : public USoundWaveProcedural
{
	GENERATED_BODY()

public:
	/** Mono PCM16 at Rate, the voice sound group, never looping. */
	void Setup(int32 InRate);
	void Queue(const uint8* Pcm, int32 NumBytes);
	int32 GetRate() const { return Rate; }
	/** Bytes queued since the wave was made, and how many of them have been played. */
	int64 GetQueued() const { return Queued; }
	int64 GetPlayed() { return Queued - GetAvailableAudioByteCount(); }

private:
	int64 Queued = 0;
	int32 Rate = 0;
};
