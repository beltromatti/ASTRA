// ASTRA — crew member.

#include "AstraCrewMember.h"

#include "ASTRA.h"
#include "Animation/AnimSequence.h"
#include "Components/AudioComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/TextRenderComponent.h"
#include "Engine/SkeletalMesh.h"
#include "Kismet/GameplayStatics.h"
#include "EngineUtils.h"
#include "Sound/SoundAttenuation.h"
#include "Sound/SoundWaveProcedural.h"

AAstraCrewMember::AAstraCrewMember()
{
	PrimaryActorTick.bCanEverTick = true;
	Body = CreateDefaultSubobject<USkeletalMeshComponent>(TEXT("Body"));
	RootComponent = Body;
	Body->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
	Voice = CreateDefaultSubobject<UAudioComponent>(TEXT("Voice"));
	Voice->SetupAttachment(Body);
	Voice->SetRelativeLocation(FVector(0.f, 0.f, 160.f));
	Voice->bAutoActivate = false;
	NameTag = CreateDefaultSubobject<UTextRenderComponent>(TEXT("NameTag"));
	NameTag->SetupAttachment(Body);
	NameTag->SetRelativeLocation(FVector(0.f, 0.f, 205.f));
	NameTag->SetHorizontalAlignment(EHTA_Center);
	NameTag->SetWorldSize(9.f);
	NameTag->SetTextRenderColor(FColor(150, 200, 255));
	NameTag->SetHiddenInGame(true);   // development aid only (no HUD in ASTRA)
}

void AAstraCrewMember::BeginPlay()
{
	Super::BeginPlay();
	RestRotation = GetActorRotation();
	if (!Body->GetSkeletalMeshAsset())
	{
		// placeholder body until the MetaHuman crew (M3): Epic's mannequin, idle loop
		const bool bFemale = StationId == TEXT("xo") || StationId == TEXT("ops") || StationId == TEXT("tactical") || StationId == TEXT("sensors");
		USkeletalMesh* Mesh = LoadObject<USkeletalMesh>(nullptr, bFemale
			? TEXT("/Game/Characters/Mannequins/Meshes/SKM_Quinn_Simple.SKM_Quinn_Simple")
			: TEXT("/Game/Characters/Mannequins/Meshes/SKM_Manny_Simple.SKM_Manny_Simple"));
		if (Mesh)
		{
			Body->SetSkeletalMeshAsset(Mesh);
			if (UAnimSequence* Idle = LoadObject<UAnimSequence>(nullptr, TEXT("/Game/Characters/Mannequins/Anims/Unarmed/MM_Idle.MM_Idle")))
			{
				Body->PlayAnimation(Idle, true);
				Body->SetPlayRate(FMath::FRandRange(0.85f, 1.1f));
			}
		}
	}
	// voice: spatialised, audible across the bridge, natural falloff
	USoundAttenuation* Att = NewObject<USoundAttenuation>(this);
	Att->Attenuation.bAttenuate = true;
	Att->Attenuation.bSpatialize = true;
	Att->Attenuation.AttenuationShape = EAttenuationShape::Sphere;
	Att->Attenuation.AttenuationShapeExtents = FVector(300.f);
	Att->Attenuation.FalloffDistance = 2500.f;
	Att->Attenuation.dBAttenuationAtMax = -18.f;
	Voice->AttenuationSettings = Att;
	NameTag->SetText(FText::FromString(DisplayName.IsEmpty() ? StationId : DisplayName));
}

void AAstraCrewMember::BeginLine(int32 LineId, int32 SampleRate)
{
	CurrentLine = LineId;
	CurrentWave = NewObject<USoundWaveProcedural>(this);
	CurrentWave->SetSampleRate(SampleRate);
	CurrentWave->NumChannels = 1;
	CurrentWave->Duration = INDEFINITELY_LOOPING_DURATION;
	CurrentWave->SoundGroup = SOUNDGROUP_Voice;
	CurrentWave->bLooping = false;
	Voice->SetSound(CurrentWave);
	Voice->Play();
	UE_LOG(LogASTRA, Log, TEXT("[Crew] %s speaking (line %d)"), *StationId, LineId);
}

void AAstraCrewMember::QueueVoice(int32 LineId, const uint8* Pcm, int32 NumBytes)
{
	if (LineId != CurrentLine || !CurrentWave)
	{
		return;
	}
	CurrentWave->QueueAudio(Pcm, NumBytes);
	// crude loudness for the (future) mouth/gesture layer
	const int16* S = reinterpret_cast<const int16*>(Pcm);
	const int32 N = NumBytes / 2;
	double Sum = 0.0;
	for (int32 i = 0; i < N; i += 8) { Sum += FMath::Abs((int32)S[i]); }
	SpeakingLevel = FMath::Max(SpeakingLevel, (float)(Sum / FMath::Max(1, N / 8) / 8000.0));
}

void AAstraCrewMember::EndLine(int32 LineId)
{
	// the procedural wave simply runs out of queued audio; nothing else to do yet
}

bool AAstraCrewMember::IsSpeaking() const
{
	return CurrentWave && CurrentWave->GetAvailableAudioByteCount() > 0;
}

void AAstraCrewMember::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	SpeakingLevel = FMath::FInterpTo(SpeakingLevel, 0.f, DeltaSeconds, 4.f);
	// when talking to the Captain, turn towards them (at most 70 degrees from the station), then drift back
	SinceSpoke = IsSpeaking() ? 0.f : SinceSpoke + DeltaSeconds;
	const float Target = SinceSpoke < 2.5f ? 1.f : 0.f;
	FacingBlend = FMath::FInterpTo(FacingBlend, Target, DeltaSeconds, 2.5f);
	if (FacingBlend > 0.001f)
	{
		if (const APlayerCameraManager* Cam = UGameplayStatics::GetPlayerCameraManager(this, 0))
		{
			const FVector To = Cam->GetCameraLocation() - GetActorLocation();
			// the mannequin mesh faces +Y in its local space: actor yaw = facing yaw - 90
			const float DesiredYaw = FMath::RadiansToDegrees(FMath::Atan2(To.Y, To.X)) - 90.f;
			const float Delta = FMath::Clamp(FMath::FindDeltaAngleDegrees(RestRotation.Yaw, DesiredYaw), -70.f, 70.f);
			SetActorRotation(FRotator(0.f, RestRotation.Yaw + Delta * FacingBlend, 0.f));
		}
	}
	else if (!GetActorRotation().Equals(RestRotation, 0.01f))
	{
		SetActorRotation(RestRotation);
	}
}

AAstraCrewMember* AAstraCrewMember::FindByStation(UWorld* World, const FString& Station)
{
	if (!World)
	{
		return nullptr;
	}
	for (TActorIterator<AAstraCrewMember> It(World); It; ++It)
	{
		if (It->StationId == Station)
		{
			return *It;
		}
	}
	return nullptr;
}
