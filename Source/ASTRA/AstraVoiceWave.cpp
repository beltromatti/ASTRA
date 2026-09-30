// ASTRA — a voice's wave.

#include "AstraVoiceWave.h"

void UAstraVoiceWave::Setup(int32 InRate)
{
	Rate = InRate;
	SetSampleRate(InRate);
	NumChannels = 1;
	Duration = INDEFINITELY_LOOPING_DURATION;
	SoundGroup = SOUNDGROUP_Voice;
	bLooping = false;
}

void UAstraVoiceWave::Queue(const uint8* Pcm, int32 NumBytes)
{
	NumBytes &= ~1;   // whole PCM16 samples
	if (NumBytes > 0)
	{
		QueueAudio(Pcm, NumBytes);
		Queued += NumBytes;
	}
}
