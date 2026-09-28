// ASTRA — crew member.

#include "AstraCrewMember.h"

#include "ASTRA.h"
#include "Animation/AnimSequence.h"
#include "Components/AudioComponent.h"
#include "Components/PoseableMeshComponent.h"
#include "Materials/MaterialInterface.h"
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
	Seated = CreateDefaultSubobject<UPoseableMeshComponent>(TEXT("Seated"));
	Seated->SetupAttachment(Body);
	Seated->SetVisibility(false);
	Seated->SetCollisionEnabled(ECollisionEnabled::NoCollision);
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
	Phase = FMath::FRand() * 10.f;
	if (!Body->GetSkeletalMeshAsset())
	{
		// placeholder body until the MetaHuman crew (M3): Epic's mannequin
		SetBody(bFemaleBody || StationId == TEXT("xo") || StationId == TEXT("ops") || StationId == TEXT("tactical") || StationId == TEXT("sensors"));
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

void AAstraCrewMember::SetBody(bool bFemale)
{
	USkeletalMesh* Mesh = LoadObject<USkeletalMesh>(nullptr, bFemale
		? TEXT("/Game/Characters/Mannequins/Meshes/SKM_Quinn_Simple.SKM_Quinn_Simple")
		: TEXT("/Game/Characters/Mannequins/Meshes/SKM_Manny_Simple.SKM_Manny_Simple"));
	if (!Mesh)
	{
		return;
	}
	bBodyFemale = bFemale;
	if (Posture != EAstraCrewPosture::Standing)
	{
		Seated->SetSkinnedAssetAndUpdate(Mesh);
		Seated->SetVisibility(true);
		if (Posture == EAstraCrewPosture::Lying)
		{
			// the body's own frame (head +Z, face +Y) laid on the bed: head towards the actor's +X, face up, then the
			// backrest raises the head end about the hinge (the actor's origin)
			const FQuat Lay = FMatrix(FPlane(0, 1, 0, 0), FPlane(0, 0, 1, 0), FPlane(1, 0, 0, 0), FPlane(0, 0, 0, 1)).ToQuat();
			Seated->SetRelativeRotation(FQuat(FRotator(ReclineDeg, 0.f, 0.f)) * Lay);
			Seated->SetRelativeLocation(FVector::ZeroVector);
			Voice->SetRelativeLocation(FVector(62.f, 0.f, 42.f));   // from the pillow
		}
		else
		{
			// seated crew face the actor's +X; the mannequin faces its own +Y, hence the -90 degrees
			Seated->SetRelativeRotation(FRotator(0.f, -90.f, 0.f));
		}
		InitSeated();
	}
	else
	{
		Body->SetSkeletalMeshAsset(Mesh);
		if (UAnimSequence* Idle = LoadObject<UAnimSequence>(nullptr, TEXT("/Game/Characters/Mannequins/Anims/Unarmed/MM_Idle.MM_Idle")))
		{
			Body->PlayAnimation(Idle, true);
			Body->SetPlayRate(FMath::FRandRange(0.85f, 1.1f));
		}
	}
	ApplyUniform();
}

void AAstraCrewMember::ApplyUniform()
{
	// uniforms on the placeholder bodies: navy trousers, the jacket in the department's colour (docs/STILE.md §3); the
	// wounded in the medbay wear a hospital gown
	const FString Dept = !UniformDept.IsEmpty() ? UniformDept
	                   : StationId == TEXT("tactical") ? TEXT("Security") : StationId == TEXT("sensors") ? TEXT("Science")
	                   : (StationId == TEXT("engineering") || StationId == TEXT("chief") || StationId.StartsWith(TEXT("eng_"))) ? TEXT("Engineering")
	                   : StationId == TEXT("flight") ? TEXT("Flight")
	                   : (StationId == TEXT("doctor") || StationId.StartsWith(TEXT("med_"))) ? TEXT("Medical") : TEXT("Command");
	UMaterialInterface* Uniform = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/ASTRA/Crew/Materials/MI_Crew_Uniform.MI_Crew_Uniform"));
	UMaterialInterface* Jacket = StationId.StartsWith(TEXT("patient"))
		? LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/ASTRA/Crew/Materials/MI_Crew_Gown.MI_Crew_Gown"))
		: LoadObject<UMaterialInterface>(nullptr, *FString::Printf(TEXT("/Game/ASTRA/Crew/Materials/MI_Crew_Dept_%s.MI_Crew_Dept_%s"), *Dept, *Dept));
	for (USkinnedMeshComponent* C : {static_cast<USkinnedMeshComponent*>(Body), static_cast<USkinnedMeshComponent*>(Seated)})
	{
		if (C && C->GetSkinnedAsset() && Uniform && Jacket && C->GetNumMaterials() >= 2)
		{
			C->SetMaterial(0, Uniform);   // head and legs
			C->SetMaterial(1, Jacket);    // torso and arms
		}
	}
}

void AAstraCrewMember::SetUniformDept(const FString& RosterDept)
{
	const FString D = RosterDept.ToLower();
	const FString U = D.Contains(TEXT("engineering")) || D.Contains(TEXT("damage")) ? TEXT("Engineering")
	                : D.Contains(TEXT("flight")) || D.Contains(TEXT("pilot")) ? TEXT("Flight")
	                : D.Contains(TEXT("med")) ? TEXT("Medical")
	                : D.Contains(TEXT("sensor")) || D.Contains(TEXT("science")) ? TEXT("Science")
	                : D.Contains(TEXT("weapon")) || D.Contains(TEXT("marine")) || D.Contains(TEXT("security")) ? TEXT("Security")
	                : TEXT("Command");
	if (U != UniformDept)
	{
		UniformDept = U;
		ApplyUniform();
	}
}

namespace
{
	TArray<TWeakObjectPtr<AAstraCrewMember>> GWalkers;
	constexpr float VisitSpeed = 140.f;   // cm/s, an unhurried walk
	constexpr float HurrySpeed = 310.f;   // back to their station at a jog (action stations)
}

const TArray<TWeakObjectPtr<AAstraCrewMember>>& AAstraCrewMember::Walkers()
{
	GWalkers.RemoveAll([](const TWeakObjectPtr<AAstraCrewMember>& W) { return !W.IsValid() || !W->IsWalking(); });
	return GWalkers;
}

void AAstraCrewMember::StandingBody(bool bWalk)
{
	if (USkeletalMesh* Mesh = LoadObject<USkeletalMesh>(nullptr, bBodyFemale
		? TEXT("/Game/Characters/Mannequins/Meshes/SKM_Quinn_Simple.SKM_Quinn_Simple")
		: TEXT("/Game/Characters/Mannequins/Meshes/SKM_Manny_Simple.SKM_Manny_Simple")))
	{
		if (Body->GetSkeletalMeshAsset() != Mesh)
		{
			Body->SetSkeletalMeshAsset(Mesh);
		}
	}
	Body->SetVisibility(true);
	Seated->SetVisibility(false);
	const bool bJog = bWalk && VisitSpeedNow > VisitSpeed;
	if (UAnimSequence* A = LoadObject<UAnimSequence>(nullptr, bJog
		? TEXT("/Game/Characters/Mannequins/Anims/Unarmed/Jog/MF_Unarmed_Jog_Fwd.MF_Unarmed_Jog_Fwd")
		: bWalk ? TEXT("/Game/Characters/Mannequins/Anims/Unarmed/Walk/MF_Unarmed_Walk_Fwd.MF_Unarmed_Walk_Fwd")
		: TEXT("/Game/Characters/Mannequins/Anims/Unarmed/MM_Idle.MM_Idle")))
	{
		Body->PlayAnimation(A, true);
		Body->SetPlayRate(bJog ? 0.9f : bWalk ? 0.95f : 1.f);
	}
	ApplyUniform();
}

void AAstraCrewMember::Visit(const TArray<FVector>& Route, int32 WaitAt, float WaitSeconds)
{
	if (Route.Num() < 2 || VisitPhase != 0)
	{
		return;
	}
	HomeXf = GetActorTransform();
	HomePosture = Posture;
	Posture = EAstraCrewPosture::Standing;
	VisitRoute = Route;
	VisitNext = 1;
	VisitPhase = 1;
	VisitWaitAt = WaitAt;
	VisitWaitS = WaitSeconds;
	VisitWaitLeft = 0.f;
	VisitSpeedNow = VisitSpeed;
	SetActorLocation(Route[0]);
	StandingBody(true);
	GWalkers.AddUnique(this);
	UE_LOG(LogASTRA, Log, TEXT("[Crew] %s leaves their place on a visit"), *StationId);
}

void AAstraCrewMember::Leave(bool bHurry)
{
	if (VisitPhase != 1 && VisitPhase != 2)
	{
		return;
	}
	// back the way they came, from where they stand (walking there: from the last point they passed)
	TArray<FVector> Back;
	Back.Add(GetActorLocation());
	for (int32 i = FMath::Min(VisitNext - 1, VisitRoute.Num() - 1); i >= 0; --i)
	{
		Back.Add(VisitRoute[i]);
	}
	VisitRoute = Back;
	VisitNext = 1;
	VisitPhase = 3;
	VisitWaitLeft = 0.f;
	VisitSpeedNow = bHurry ? HurrySpeed : VisitSpeed;
	StandingBody(true);
	GWalkers.AddUnique(this);
}

void AAstraCrewMember::TickVisit(float DeltaSeconds)
{
	if (VisitPhase == 2)
	{
		return;
	}
	if (!VisitRoute.IsValidIndex(VisitNext))
	{
		if (VisitPhase == 1)
		{
			VisitPhase = 2;              // arrived: stand, and face the Captain
			StandingBody(false);
			if (const APawn* P = UGameplayStatics::GetPlayerPawn(this, 0))
			{
				const FVector To = (P->GetActorLocation() - GetActorLocation()) * FVector(1, 1, 0);
				SetActorRotation(FRotator(0.f, To.Rotation().Yaw - 90.f, 0.f));   // the mannequin faces its +Y
			}
			RestRotation = GetActorRotation();
		}
		else
		{
			VisitPhase = 0;              // home: back to their place and posture
			SetActorTransform(HomeXf);
			RestRotation = HomeXf.Rotator();
			Posture = HomePosture;
			if (Posture != EAstraCrewPosture::Standing)
			{
				Body->SetVisibility(false);
			}
			SetBody(bBodyFemale);
			UE_LOG(LogASTRA, Log, TEXT("[Crew] %s is back at their place"), *StationId);
		}
		return;
	}
	if (VisitWaitLeft > 0.f)
	{
		// at the door: a moment's wait (the chime), then on
		if ((VisitWaitLeft -= DeltaSeconds) <= 0.f)
		{
			StandingBody(true);
		}
		return;
	}
	const FVector From = VisitRoute[VisitNext - 1];
	const FVector Target = VisitRoute[VisitNext];
	FVector To = Target - GetActorLocation();
	To.Z = 0.f;
	const float Step = VisitSpeedNow * DeltaSeconds;
	if (To.Size() <= Step)
	{
		SetActorLocation(Target);
		if (VisitPhase == 1 && VisitNext == VisitWaitAt && VisitWaitS > 0.f)
		{
			VisitWaitLeft = VisitWaitS;
			StandingBody(false);
		}
		++VisitNext;
		return;
	}
	const FVector Dir = To.GetSafeNormal();
	FVector Next = GetActorLocation() + Dir * Step;
	// the deck's height along the way: down the well's stairs, off the dais (a ramp between the points)
	const float Seg = FVector::Dist2D(From, Target);
	Next.Z = Seg > 1.f ? FMath::Lerp(Target.Z, From.Z, FMath::Clamp(FVector::Dist2D(Next, Target) / Seg, 0.f, 1.f)) : Target.Z;
	SetActorLocation(Next);
	// turn towards where they are going (the mannequin faces its own +Y)
	const float WantYaw = Dir.Rotation().Yaw - 90.f;
	SetActorRotation(FRotator(0.f, FMath::FixedTurn(GetActorRotation().Yaw, WantYaw, 300.f * DeltaSeconds), 0.f));
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
	if (VisitPhase == 1 || VisitPhase == 3)
	{
		TickVisit(DeltaSeconds);
		return;
	}

	SpeakingLevel = FMath::FInterpTo(SpeakingLevel, 0.f, DeltaSeconds, 4.f);
	// when talking to the Captain, turn towards them (at most 70 degrees from the station), then drift back
	SinceSpoke = IsSpeaking() ? 0.f : SinceSpoke + DeltaSeconds;
	const float Target = SinceSpoke < 2.5f ? 1.f : 0.f;
	FacingBlend = FMath::FInterpTo(FacingBlend, Target, DeltaSeconds, 2.5f);
	LifeTime += DeltaSeconds;
	if (Posture != EAstraCrewPosture::Standing && RefCS.Num())
	{
		UpdateSeated(DeltaSeconds);   // seated: the head and shoulders turn, not the whole body
		return;
	}
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

// ------------------------------------------------------------------------------------------ procedural seated pose
int32 AAstraCrewMember::Bone(const TCHAR* Name) const
{
	const USkinnedAsset* Asset = Seated ? Seated->GetSkinnedAsset() : nullptr;
	return Asset ? Asset->GetRefSkeleton().FindBoneIndex(FName(Name)) : INDEX_NONE;
}

void AAstraCrewMember::InitSeated()
{
	const FReferenceSkeleton& Ref = Seated->GetSkinnedAsset()->GetRefSkeleton();
	const int32 N = Ref.GetNum();
	RefLocal = Ref.GetRefBonePose();
	RefCS.SetNum(N);
	Parent.SetNum(N);
	for (int32 i = 0; i < N; ++i)
	{
		Parent[i] = Ref.GetParentIndex(i);
		RefCS[i] = Parent[i] >= 0 ? RefLocal[i] * RefCS[Parent[i]] : RefLocal[i];
	}
	// the body's own basis, read from the skeleton (robust to the mannequin's axis conventions)
	const int32 Foot = Bone(TEXT("foot_r")), Ball = Bone(TEXT("ball_r")), UpL = Bone(TEXT("upperarm_l")), UpR = Bone(TEXT("upperarm_r"));
	if (Foot != INDEX_NONE && Ball != INDEX_NONE)
	{
		Fwd = (RefCS[Ball].GetLocation() - RefCS[Foot].GetLocation()) * FVector(1, 1, 0);
		Fwd.Normalize();
	}
	if (UpL != INDEX_NONE && UpR != INDEX_NONE)
	{
		Right = (RefCS[UpR].GetLocation() - RefCS[UpL].GetLocation()) * FVector(1, 1, 0);
		Right.Normalize();
	}
	UpdateSeated(0.f);
}

void AAstraCrewMember::Startle(float Strength)
{
	StartleT = 1.f;
	StartleStrength = FMath::Clamp(Strength, 0.3f, 1.f);
}

void AAstraCrewMember::UpdateSeated(float DeltaSeconds)
{
	StartleT = FMath::Max(0.f, StartleT - DeltaSeconds / 1.6f);
	// recoil envelope: a jolt in a tenth of a second, a slow return to the console
	const float Recoil = StartleStrength * FMath::Min(1.f, (1.f - StartleT) * 10.f) * FMath::SmoothStep(0.f, 0.6f, StartleT);
	const int32 N = RefCS.Num();
	const FVector Up = FVector::UpVector;
	const float T = LifeTime + Phase;
	const bool bConsole = Posture == EAstraCrewPosture::SeatedConsole;
	TMap<int32, FQuat> Rot;         // absolute component-space rotations
	auto Aim = [&](const TCHAR* BoneName, const TCHAR* ChildName, FVector Dir)
	{
		const int32 B = Bone(BoneName), C = Bone(ChildName);
		if (B == INDEX_NONE || C == INDEX_NONE)
		{
			return;
		}
		const FVector D0 = (RefCS[C].GetLocation() - RefCS[B].GetLocation()).GetSafeNormal();
		Rot.Add(B, FQuat::FindBetweenNormals(D0, Dir.GetSafeNormal()) * RefCS[B].GetRotation());
	};
	auto Turn = [&](const TCHAR* BoneName, const FVector& Axis, float Deg)
	{
		const int32 B = Bone(BoneName);
		if (B != INDEX_NONE)
		{
			Rot.Add(B, FQuat(Axis, FMath::DegreesToRadians(Deg)) * RefCS[B].GetRotation());
		}
	};
	// the Captain's direction, for the head turn while speaking
	float LookYaw = 3.f * FMath::Sin(T * 0.9f) + 2.f * FMath::Sin(T * 0.37f);
	if (FacingBlend > 0.001f)
	{
		if (const APlayerCameraManager* Cam = UGameplayStatics::GetPlayerCameraManager(this, 0))
		{
			const FVector L = Seated->GetComponentTransform().InverseTransformPosition(Cam->GetCameraLocation());
			const FVector H(L.X, L.Y, 0.f);
			const float Yaw = FMath::RadiansToDegrees(FMath::Atan2(FVector::DotProduct(H, Right), FVector::DotProduct(H, Fwd)));
			LookYaw = FMath::Lerp(LookYaw, FMath::Clamp(Yaw, -75.f, 75.f), FacingBlend);
		}
	}
	const FVector Side = FVector::CrossProduct(Up, Fwd).GetSafeNormal();   // lean axis (pitch forward)
	const float Sgn = FVector::DotProduct(Side, Right) >= 0.f ? 1.f : -1.f;
	const FVector PitchAxis = Right * Sgn;                                  // positive angle = forward
	FVector PelvisLoc;
	if (Posture == EAstraCrewPosture::Lying)
	{
		// in a medbay bed: the torso on the backrest (the component carries the recline), the hips flexed by as much so
		// the legs lie flat, the arms on the blanket, slow deep breathing; the head on the pillow turns to the Captain
		const float Breath = 1.1f * FMath::Sin(T * 2.f * PI / 5.2f);
		const float Recl = FMath::DegreesToRadians(ReclineDeg);
		Turn(TEXT("spine_03"), PitchAxis, Breath);
		Turn(TEXT("spine_04"), PitchAxis, 0.5f * Breath);
		float LookDown = 8.f;   // the pillow tips the chin down a little
		if (FacingBlend > 0.001f)
		{
			if (const APlayerCameraManager* Cam = UGameplayStatics::GetPlayerCameraManager(this, 0))
			{
				const int32 HeadB = Bone(TEXT("head")), PelvisB = Bone(TEXT("pelvis"));
				const FVector HeadCS = (HeadB != INDEX_NONE && PelvisB != INDEX_NONE)
					? RefCS[HeadB].GetLocation() - RefCS[PelvisB].GetLocation() + Fwd * 11.f : Up * 65.f;
				const FVector D = Seated->GetComponentTransform().InverseTransformPosition(Cam->GetCameraLocation()) - HeadCS;
				const float Down = FMath::RadiansToDegrees(FMath::Atan2(-FVector::DotProduct(D, Up), FMath::Max(1.f, FVector::DotProduct(D, Fwd))));
				LookDown = FMath::Lerp(LookDown, FMath::Clamp(Down, 0.f, 38.f), FacingBlend);
			}
		}
		if (const int32 B = Bone(TEXT("neck_01")); B != INDEX_NONE)
		{
			Rot.Add(B, FQuat(Up, FMath::DegreesToRadians(LookYaw * 0.5f)) * FQuat(PitchAxis, FMath::DegreesToRadians(LookDown * 0.45f)) * RefCS[B].GetRotation());
		}
		if (const int32 B = Bone(TEXT("head")); B != INDEX_NONE)
		{
			Rot.Add(B, FQuat(Up, FMath::DegreesToRadians(LookYaw)) * FQuat(PitchAxis, FMath::DegreesToRadians(LookDown)) * RefCS[B].GetRotation());
		}
		const bool bHandsOnBelly = FMath::Frac(Phase * 0.37f) < 0.6f;
		for (int32 k = 0; k < 2; ++k)
		{
			const float S = k ? 1.f : -1.f;   // right : left
			const FVector Leg = -Up * FMath::Cos(Recl) + Fwd * FMath::Sin(Recl) + Right * (0.045f * S);
			Aim(k ? TEXT("thigh_r") : TEXT("thigh_l"), k ? TEXT("calf_r") : TEXT("calf_l"), Leg);
			Aim(k ? TEXT("calf_r") : TEXT("calf_l"), k ? TEXT("foot_r") : TEXT("foot_l"), Leg + Fwd * 0.03f);
			if (const int32 B = Bone(k ? TEXT("foot_r") : TEXT("foot_l")); B != INDEX_NONE)
			{
				Rot.Add(B, RefCS[B].GetRotation());   // toes up (the recline tips them towards the foot of the bed)
			}
			const TCHAR* UpperArm = k ? TEXT("upperarm_r") : TEXT("upperarm_l");
			const TCHAR* LowerArm = k ? TEXT("lowerarm_r") : TEXT("lowerarm_l");
			const TCHAR* Hand = k ? TEXT("hand_r") : TEXT("hand_l");
			const TCHAR* Finger = Bone(k ? TEXT("middle_metacarpal_r") : TEXT("middle_metacarpal_l")) != INDEX_NONE
				? (k ? TEXT("middle_metacarpal_r") : TEXT("middle_metacarpal_l")) : (k ? TEXT("middle_01_r") : TEXT("middle_01_l"));
			Aim(UpperArm, LowerArm, -Up * 0.93f + Right * (0.28f * S) + Fwd * 0.1f);
			if (bHandsOnBelly)
			{
				Aim(LowerArm, Hand, -Right * (0.85f * S) + Fwd * 0.35f + Up * 0.1f);
				Aim(Hand, Finger, -Right * (0.85f * S) + Fwd * 0.12f - Up * 0.1f);
			}
			else
			{
				Aim(LowerArm, Hand, -Up * 0.92f + Fwd * 0.3f + Right * (0.04f * S));
				Aim(Hand, Finger, -Up * 0.85f + Fwd * 0.05f);
			}
		}
		PelvisLoc = Fwd * 11.f;   // the back on the mattress
	}
	else
	{
		// spine: a slight lean towards the console, breathing on top
		const float Lean = (bConsole ? 1.f : 0.45f) - 1.6f * Recoil;
		const float Breath = 0.9f * FMath::Sin(T * 2.f * PI / 4.3f);
		Turn(TEXT("spine_01"), PitchAxis, 3.f * Lean);
		Turn(TEXT("spine_02"), PitchAxis, 6.f * Lean);
		Turn(TEXT("spine_03"), PitchAxis, 9.f * Lean + Breath);
		const FQuat ShoulderTurn(Up, FMath::DegreesToRadians(LookYaw * 0.25f));
		if (const int32 B = Bone(TEXT("spine_04")); B != INDEX_NONE)
		{
			Rot.Add(B, ShoulderTurn * FQuat(PitchAxis, FMath::DegreesToRadians(11.f * Lean + Breath * 0.6f)) * RefCS[B].GetRotation());
		}
		if (const int32 B = Bone(TEXT("spine_05")); B != INDEX_NONE)
		{
			Rot.Add(B, ShoulderTurn * FQuat(PitchAxis, FMath::DegreesToRadians(12.f * Lean)) * RefCS[B].GetRotation());
		}
		LookYaw += 38.f * Recoil * (FMath::Sin(Phase * 7.f) >= 0.f ? 1.f : -1.f);   // turn the face away from the burst
		const FQuat HeadTurn(Up, FMath::DegreesToRadians(LookYaw));
		if (const int32 B = Bone(TEXT("neck_01")); B != INDEX_NONE)
		{
			Rot.Add(B, FQuat(Up, FMath::DegreesToRadians(LookYaw * 0.55f)) * FQuat(PitchAxis, FMath::DegreesToRadians(4.f * Lean)) * RefCS[B].GetRotation());
		}
		if (const int32 B = Bone(TEXT("head")); B != INDEX_NONE)
		{
			Rot.Add(B, HeadTurn * FQuat(PitchAxis, FMath::DegreesToRadians(-2.f + 1.5f * FMath::Sin(T * 0.53f))) * RefCS[B].GetRotation());
		}
		// legs: thighs forward and a little down and apart, shins down, feet flat
		for (int32 k = 0; k < 2; ++k)
		{
			const float S = k ? 1.f : -1.f;   // right : left
			const TCHAR* Thigh = k ? TEXT("thigh_r") : TEXT("thigh_l");
			const TCHAR* Calf = k ? TEXT("calf_r") : TEXT("calf_l");
			const TCHAR* Foot = k ? TEXT("foot_r") : TEXT("foot_l");
			Aim(Thigh, Calf, Fwd * 0.96f - Up * 0.2f + Right * (0.11f * S));
			Aim(Calf, Foot, -Up * 0.97f + Fwd * 0.14f + Right * (0.03f * S));
			if (const int32 B = Bone(Foot); B != INDEX_NONE)
			{
				Rot.Add(B, RefCS[B].GetRotation());
			}
			// arms: to the console (hands working on the desk) or resting on the armrests
			const TCHAR* UpperArm = k ? TEXT("upperarm_r") : TEXT("upperarm_l");
			const TCHAR* LowerArm = k ? TEXT("lowerarm_r") : TEXT("lowerarm_l");
			const TCHAR* Hand = k ? TEXT("hand_r") : TEXT("hand_l");
			const TCHAR* Finger = k ? TEXT("middle_metacarpal_r") : TEXT("middle_metacarpal_l");
			const float Work = bConsole ? (1.f - 0.7f * FacingBlend) : 0.f;
			const float Tap = Work * (2.5f * FMath::Sin(T * 4.1f + k * 1.7f) * FMath::Max(0.f, FMath::Sin(T * 0.8f + k)));
			const bool bShield = Recoil > 0.01f && (k == 1) == (FMath::Sin(Phase * 7.f) >= 0.f);
			if (bShield)
			{
				// forearm up across the face
				Aim(UpperArm, LowerArm, FMath::Lerp(Fwd * 0.45f - Up * 0.85f + Right * (0.16f * S), Fwd * 0.75f + Up * 0.25f + Right * (0.25f * S), Recoil));
				Aim(LowerArm, Hand, FMath::Lerp(Fwd * 0.97f - Right * (0.26f * S), Up * 0.85f - Right * (0.55f * S) + Fwd * 0.1f, Recoil));
			}
			else if (bConsole)
			{
				Aim(UpperArm, LowerArm, Fwd * 0.45f - Up * 0.85f + Right * (0.16f * S));
				Aim(LowerArm, Hand, Fwd * 0.97f + Up * (-0.05f + Tap * 0.01f) - Right * (0.26f * S));
				Aim(Hand, Bone(Finger) != INDEX_NONE ? Finger : (k ? TEXT("middle_01_r") : TEXT("middle_01_l")), Fwd * 0.9f - Up * 0.4f - Right * (0.05f * S));
			}
			else
			{
				Aim(UpperArm, LowerArm, Fwd * 0.18f - Up * 0.97f + Right * (0.2f * S));
				Aim(LowerArm, Hand, Fwd * 0.93f - Up * 0.22f + Right * (0.08f * S));
				Aim(Hand, Bone(Finger) != INDEX_NONE ? Finger : (k ? TEXT("middle_01_r") : TEXT("middle_01_l")), Fwd * 0.85f - Up * 0.5f);
			}
		}
		PelvisLoc = Fwd * 4.f + Up * (SeatHipHeight + 0.4f * Breath);
	}
	// assemble the component-space pose (bones are ordered parent first) and write it back as local transforms
	const int32 Pelvis = Bone(TEXT("pelvis"));
	TArray<FTransform> CS;
	CS.SetNum(N);
	TArray<FTransform>& Local = Seated->BoneSpaceTransforms;
	if (Local.Num() != N)
	{
		return;
	}
	for (int32 i = 0; i < N; ++i)
	{
		CS[i] = Parent[i] >= 0 ? RefLocal[i] * CS[Parent[i]] : RefLocal[i];
		if (i == Pelvis)
		{
			CS[i].SetLocation(PelvisLoc);
		}
		if (const FQuat* Q = Rot.Find(i))
		{
			CS[i].SetRotation(*Q);
		}
		Local[i] = Parent[i] >= 0 ? CS[i].GetRelativeTransform(CS[Parent[i]]) : CS[i];
	}
	Seated->RefreshBoneTransforms();
}
