// ASTRA — the lifepods.

#include "AstraLifepod.h"

#include "ASTRA.h"
#include "Camera/CameraComponent.h"
#include "Components/AudioComponent.h"
#include "Components/InputComponent.h"
#include "Components/PointLightComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Kismet/GameplayStatics.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Sound/SoundBase.h"
#include "UObject/ConstructorHelpers.h"

// ------------------------------------------------------------------------------------------------------ the hatch
AAstraLifepodHatch::AAstraLifepodHatch()
{
	PrimaryActorTick.bCanEverTick = true;
	Mesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Mesh"));
	SetRootComponent(Mesh);
	static ConstructorHelpers::FObjectFinder<UStaticMesh> M(TEXT("/Game/ASTRA/Kit/Lifepod/SM_POD_Hatch.SM_POD_Hatch"));
	if (M.Succeeded())
	{
		Mesh->SetStaticMesh(M.Object);
	}
	Mesh->SetMobility(EComponentMobility::Static);
}

void AAstraLifepodHatch::BeginPlay()
{
	Super::BeginPlay();
	const int32 Slot = Mesh->GetMaterialIndex(TEXT("MI_POD_Status"));
	if (Slot != INDEX_NONE)
	{
		Lamp = Mesh->CreateDynamicMaterialInstance(Slot);
	}
	SetState(EState::Ready);
}

void AAstraLifepodHatch::SetState(EState S)
{
	State = S;
	Blink = 0.f;
	if (Lamp)
	{
		const FLinearColor C = S == EState::Ready ? FLinearColor(0.1f, 1.f, 0.3f) : S == EState::Boarding ? FLinearColor(1.f, 0.55f, 0.05f)
		                                                                          : FLinearColor(1.f, 0.06f, 0.03f);
		Lamp->SetVectorParameterValue(TEXT("EmissiveColor"), C);
		Lamp->SetScalarParameterValue(TEXT("Intensity"), S == EState::Ready ? 6.f : 30.f);
	}
}

void AAstraLifepodHatch::Tick(float DeltaTime)
{
	Super::Tick(DeltaTime);
	if (State == EState::Boarding && Lamp)
	{
		// boarding: the amber lamp flashes (twice a second)
		Blink += DeltaTime;
		Lamp->SetScalarParameterValue(TEXT("Intensity"), FMath::Fmod(Blink, 0.5f) < 0.28f ? 40.f : 2.f);
	}
}

bool AAstraLifepodHatch::IsWithinReach(const APawn* Pawn) const
{
	if (!Pawn)
	{
		return false;
	}
	const FVector Front = GetActorLocation() + GetActorForwardVector() * 70.f;
	const FVector D = Pawn->GetActorLocation() - Front;
	return FVector2D(D.X, D.Y).Size() < 170.f && FMath::Abs(D.Z - 100.f) < 200.f;
}

FVector AAstraLifepodHatch::PodStart() const
{
	// outside the hull behind the hatch, at the height of a seated eye
	return GetActorLocation() - GetActorForwardVector() * 320.f + FVector(0.f, 0.f, 130.f);
}

// ------------------------------------------------------------------------------------------------------ the pod
AAstraLifepod::AAstraLifepod()
{
	PrimaryActorTick.bCanEverTick = true;
	Root = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	SetRootComponent(Root);
	Interior = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Interior"));
	Interior->SetupAttachment(Root);
	Interior->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Interior->bCastShadowAsTwoSided = true;              // a closed shell: the sun gets in only through the porthole
	static ConstructorHelpers::FObjectFinder<UStaticMesh> M(TEXT("/Game/ASTRA/Kit/Lifepod/SM_POD_Interior.SM_POD_Interior"));
	if (M.Succeeded())
	{
		Interior->SetStaticMesh(M.Object);
	}
	Camera = CreateDefaultSubobject<UCameraComponent>(TEXT("Camera"));
	Camera->SetupAttachment(Root);                        // the Captain's eye is the pod's origin
	Camera->SetFieldOfView(88.f);
	RedLight = CreateDefaultSubobject<UPointLightComponent>(TEXT("RedLight"));
	RedLight->SetupAttachment(Root);
	RedLight->SetRelativeLocation(FVector(-90.f, 0.f, 95.f));   // the emergency strip along the crown
	RedLight->SetIntensityUnits(ELightUnits::Candelas);
	RedLight->SetIntensity(110.f);
	RedLight->SetLightColor(FLinearColor(1.f, 0.14f, 0.06f));
	RedLight->SetAttenuationRadius(420.f);
	RedLight->SetCastShadows(false);
	PanelGlow = CreateDefaultSubobject<UPointLightComponent>(TEXT("PanelGlow"));
	PanelGlow->SetupAttachment(Root);
	PanelGlow->SetRelativeLocation(FVector(40.f, 0.f, -30.f));   // the console's displays on the Captain's hands
	PanelGlow->SetIntensityUnits(ELightUnits::Candelas);
	PanelGlow->SetIntensity(16.f);
	PanelGlow->SetLightColor(FLinearColor(0.55f, 0.75f, 1.f));
	PanelGlow->SetAttenuationRadius(160.f);
	PanelGlow->SetCastShadows(false);
	Hum = CreateDefaultSubobject<UAudioComponent>(TEXT("Hum"));
	Hum->SetupAttachment(Root);
	Hum->bAutoActivate = false;
	static ConstructorHelpers::FObjectFinder<USoundBase> S(TEXT("/Game/ASTRA/Audio/SW_Pod_Hum.SW_Pod_Hum"));
	if (S.Succeeded())
	{
		Hum->SetSound(S.Object);
	}
	AutoPossessPlayer = EAutoReceiveInput::Disabled;
}

void AAstraLifepod::Launch(const FVector& Start, const FVector& InDir, const FVector& LookAt, const FString& Name)
{
	PodName = Name;
	Dir = InDir.GetSafeNormal();
	SetActorLocation(Start);
	LookAtPoint = LookAt;
	BaseRot = (LookAt - Start).ToOrientationQuat();
	SetActorRotation(BaseRot);
	Vel = Dir * 600.f;                                   // the launch rail's kick
	Age = 0.f;
	Shake = 0.9f;
	Hum->Play();
	if (USoundBase* L = LoadObject<USoundBase>(nullptr, TEXT("/Game/ASTRA/Audio/SW_Pod_Launch.SW_Pod_Launch")))
	{
		UGameplayStatics::PlaySound2D(this, L, 0.9f);
	}
	UE_LOG(LogASTRA, Log, TEXT("[Lifepod] %s away"), *PodName);
}

void AAstraLifepod::FeelBreach(float Strength)
{
	Shake = FMath::Max(Shake, Strength);
	if (USoundBase* B = LoadObject<USoundBase>(nullptr, TEXT("/Game/ASTRA/Audio/SW_Breach_Felt.SW_Breach_Felt")))
	{
		UGameplayStatics::PlaySound2D(this, B, FMath::Clamp(Strength, 0.4f, 1.f));
	}
}

void AAstraLifepod::Tick(float DeltaTime)
{
	Super::Tick(DeltaTime);
	if (Age < 0.f)
	{
		return;
	}
	Age += DeltaTime;
	// the motor burns for four seconds (to ~26 m/s), then the pod coasts: two or three kilometres off when she goes
	if (Age < 4.f)
	{
		Vel += Dir * 500.f * DeltaTime;
		Shake = FMath::Max(Shake, 0.25f);
	}
	SetActorLocation(GetActorLocation() + Vel * DeltaTime);
	Shake = FMath::FInterpTo(Shake, 0.f, DeltaTime, 1.2f);
	// the porthole stays on the ship (the pod's little gyros), a slow sway on top
	BaseRot = FQuat::Slerp(BaseRot, (LookAtPoint - GetActorLocation()).ToOrientationQuat(), FMath::Min(1.f, DeltaTime * 0.8f));
	const FRotator Sway(FMath::Sin(Age * 0.37f) * 2.5f, FMath::Sin(Age * 0.23f + 1.f) * 3.f, FMath::Sin(Age * 0.29f + 2.f) * 4.f);
	SetActorRotation(BaseRot * Sway.Quaternion());
	const float J = Shake * Shake;
	Camera->SetRelativeRotation(FRotator(LookPitch + FMath::FRandRange(-2.f, 2.f) * J, LookYaw + FMath::FRandRange(-2.f, 2.f) * J,
	                                     FMath::FRandRange(-1.f, 1.f) * J));
	RedLight->SetIntensity(110.f * (0.85f + 0.15f * FMath::Sin(Age * 2.1f)));   // the emergency strip breathes
}

void AAstraLifepod::SetupPlayerInputComponent(UInputComponent* IC)
{
	Super::SetupPlayerInputComponent(IC);
	IC->BindAxisKey(EKeys::MouseX, this, &AAstraLifepod::MouseX);
	IC->BindAxisKey(EKeys::MouseY, this, &AAstraLifepod::MouseY);
}

void AAstraLifepod::MouseX(float V)
{
	LookYaw = FMath::Clamp(LookYaw + V * 1.2f, -115.f, 115.f);
}

void AAstraLifepod::MouseY(float V)
{
	LookPitch = FMath::Clamp(LookPitch + V * 1.2f, -60.f, 70.f);
}
