// ASTRA — a ship's navigation lights.

#include "AstraNavLights.h"

#include "ASTRA.h"
#include "Camera/PlayerCameraManager.h"
#include "Components/StaticMeshComponent.h"
#include "Dom/JsonObject.h"
#include "Engine/StaticMesh.h"
#include "Kismet/GameplayStatics.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

namespace
{
	/** data/ship/nav_lights.json, read once: for each hull, where its lights stand (cm, mesh space). */
	const TSharedPtr<FJsonObject>& NavData()
	{
		static TSharedPtr<FJsonObject> Data;
		static bool bLoaded = false;
		if (!bLoaded)
		{
			bLoaded = true;
			FString Text;
			// staged with the game (Content/ASTRA/Data, always packaged as a loose file: DefaultGame.ini); the repo's
			// data/ship copy is the source the extractor writes
			if (FFileHelper::LoadFileToString(Text, *FPaths::Combine(FPaths::ProjectContentDir(), TEXT("ASTRA/Data/nav_lights.json")))
			    || FFileHelper::LoadFileToString(Text, *FPaths::Combine(FPaths::ProjectDir(), TEXT("data/ship/nav_lights.json"))))
			{
				TSharedRef<TJsonReader<>> R = TJsonReaderFactory<>::Create(Text);
				FJsonSerializer::Deserialize(R, Data);
			}
			UE_LOG(LogASTRA, Log, TEXT("[Ships] navigation lights: %s"), Data.IsValid() ? TEXT("loaded") : TEXT("missing (data/ship/nav_lights.json)"));
		}
		return Data;
	}

	bool Point(const TSharedPtr<FJsonObject>& Ship, const TCHAR* Key, FVector& Out)
	{
		const TArray<TSharedPtr<FJsonValue>>* A = nullptr;
		if (!Ship.IsValid() || !Ship->TryGetArrayField(Key, A) || A->Num() < 3)
		{
			return false;
		}
		Out = FVector((*A)[0]->AsNumber(), (*A)[1]->AsNumber(), (*A)[2]->AsNumber());
		return true;
	}
}

UAstraNavLights::UAstraNavLights()
{
	PrimaryComponentTick.bCanEverTick = true;
	PrimaryComponentTick.TickInterval = 0.f;
	// it ticks only once it has a lamp (AddLamp): a station's module, a hull without lights in the data have nothing to blink, and
	// 1300 such components ticking for nothing cost the game thread a millisecond
	PrimaryComponentTick.bStartWithTickEnabled = false;
}

void UAstraNavLights::Setup(const FString& MeshName, bool bMandate, bool bNoTopStrobe)
{
	const TSharedPtr<FJsonObject>& Data = NavData();
	const TSharedPtr<FJsonObject>* ShipP = nullptr;
	if (!Data.IsValid() || !Data->TryGetObjectField(MeshName, ShipP))
	{
		return;
	}
	const TSharedPtr<FJsonObject>& Ship = *ShipP;
	const float Length = float(Ship->GetNumberField(TEXT("length_m")));
	const bool bSmall = Length < 40.f;                               // a fighter or a drone
	const float Out = bSmall ? 15.f : 60.f;                           // cm clear of the plating
	const float Lamp = bSmall ? 0.6f : FMath::Clamp(Length * 0.004f, 1.2f, 3.5f);   // m
	FVector P;
	if (bMandate)
	{
		// the Mandate runs dark: one slow red pulse on the highest point
		if (Point(Ship, TEXT("top"), P))
		{
			AddLamp(P + FVector(0, 0, Out), FLinearColor(1.f, 0.08f, 0.03f), Lamp * 1.2f, 420.f, 2);
		}
		return;
	}
	if (Point(Ship, TEXT("port"), P))
	{
		AddLamp(P - FVector(0, Out, 0), FLinearColor(1.f, 0.06f, 0.04f), Lamp, 160.f, 0);
	}
	if (Point(Ship, TEXT("starboard"), P))
	{
		AddLamp(P + FVector(0, Out, 0), FLinearColor(0.1f, 1.f, 0.35f), Lamp, 160.f, 0);
	}
	if (!bSmall && Point(Ship, TEXT("stern"), P))
	{
		AddLamp(P - FVector(Out, 0, 0), FLinearColor(1.f, 0.95f, 0.85f), Lamp, 120.f, 0);
	}
	if (!bNoTopStrobe && Point(Ship, TEXT("top"), P))
	{
		AddLamp(P + FVector(0, 0, Out), FLinearColor(1.f, 1.f, 1.f), Lamp * 1.1f, 900.f, 1);
	}
	if (!bSmall && Point(Ship, TEXT("belly"), P))
	{
		AddLamp(P - FVector(0, 0, Out), FLinearColor(1.f, 0.1f, 0.05f), Lamp, 500.f, 2);
	}
}

void UAstraNavLights::AddLamp(const FVector& Local, const FLinearColor& Color, float SizeM, float Intensity, uint8 InPattern)
{
	UStaticMesh* Sphere = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Sphere.Sphere"));
	UMaterialInterface* Mat = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/ASTRA/Materials/M_FX_Flare.M_FX_Flare"));
	AActor* Owner = GetOwner();
	if (!Sphere || !Mat || !Owner)
	{
		return;
	}
	UStaticMeshComponent* C = NewObject<UStaticMeshComponent>(Owner);
	C->SetMobility(EComponentMobility::Movable);
	C->SetStaticMesh(Sphere);
	C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	C->SetCastShadow(false);
	C->SetupAttachment(this);
	C->SetUsingAbsoluteScale(true);          // the hull may be scaled; a lamp keeps its own size
	C->SetRelativeLocation(Local);
	C->RegisterComponent();
	UMaterialInstanceDynamic* M = C->CreateAndSetMaterialInstanceDynamicFromMaterial(0, Mat);
	M->SetVectorParameterValue(TEXT("Color"), Color);
	M->SetScalarParameterValue(TEXT("Intensity"), InPattern == 0 ? Intensity : 0.f);
	Lamps.Add(C);
	SetComponentTickEnabled(true);
	Mids.Add(M);
	Size.Add(SizeM);
	Glow.Add(Intensity);
	Pattern.Add(InPattern);
	Phase.Add(FMath::FRandRange(0.f, 2.f));   // no two ships blink together
}

void UAstraNavLights::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
	Super::TickComponent(DeltaTime, TickType, ThisTickFunction);
	T += DeltaTime;
	const APlayerCameraManager* Cam = UGameplayStatics::GetPlayerCameraManager(this, 0);
	const FVector Eye = Cam ? Cam->GetCameraLocation() : FVector::ZeroVector;
	for (int32 i = 0; i < Lamps.Num(); ++i)
	{
		UStaticMeshComponent* C = Lamps[i];
		if (!C)
		{
			continue;
		}
		// a few pixels however far: up close its own size, far off a fixed share of the distance
		const float Dist = float(FVector::Dist(C->GetComponentLocation(), Eye)) / 100.f;
		C->SetWorldScale3D(FVector(FMath::Max(Size[i], Dist * 0.0012f)));
		if (Pattern[i] == 0)
		{
			continue;
		}
		float On = 0.f;
		if (Pattern[i] == 1)
		{
			// the white strobe: two quick flashes every second and a half
			const float Tt = FMath::Fmod(T + Phase[i], 1.5f);
			On = (Tt < 0.07f || (Tt > 0.2f && Tt < 0.27f)) ? 1.f : 0.f;
		}
		else
		{
			// the red pulse: a soft beat every two seconds and a bit
			const float Tt = FMath::Fmod(T + Phase[i], 2.2f);
			On = Tt < 0.5f ? FMath::Sin(Tt / 0.5f * PI) : 0.f;
		}
		Mids[i]->SetScalarParameterValue(TEXT("Intensity"), Glow[i] * On);
	}
}
