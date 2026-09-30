#include "AstraZoneLights.h"
#include "ASTRA.h"
#include "Camera/PlayerCameraManager.h"
#include "Components/LightComponent.h"
#include "EngineUtils.h"
#include "Kismet/GameplayStatics.h"

namespace
{
	TAutoConsoleVariable<int32> CVarZoneMax(TEXT("astra.zonelights.max"), 8, TEXT("Interior zone lights lit at once, nearest to the Captain first"));
	TAutoConsoleVariable<float> CVarZoneReach(TEXT("astra.zonelights.reach"), 30.f, TEXT("Reach of the interior zone lights around the Captain (m)"));
}

bool UAstraZoneLights::ShouldCreateSubsystem(UObject* Outer) const
{
	const UWorld* World = Cast<UWorld>(Outer);
	return World && (World->WorldType == EWorldType::Game || World->WorldType == EWorldType::PIE);
}

void UAstraZoneLights::OnWorldBeginPlay(UWorld& InWorld)
{
	Super::OnWorldBeginPlay(InWorld);
	static const FString Prefix(TEXT("ASTRA.ZoneLight."));
	for (TActorIterator<AActor> It(&InWorld); It; ++It)
	{
		FString Zone;
		for (const FName& T : It->Tags)
		{
			const FString S = T.ToString();
			if (S.StartsWith(Prefix))
			{
				Zone = S.Mid(Prefix.Len());
				break;
			}
		}
		if (Zone.IsEmpty())
		{
			continue;
		}
		TArray<ULightComponent*> Comps;
		It->GetComponents<ULightComponent>(Comps);
		for (ULightComponent* L : Comps)
		{
			Lights.Add({L, Zone, true});
		}
	}
	UE_LOG(LogASTRA, Log, TEXT("[ZoneLights] %d interior lights under zone control"), Lights.Num());
}

void UAstraZoneLights::Tick(float DeltaTime)
{
	Accum += DeltaTime;
	if (Lights.Num() == 0 || Accum < 0.25f)
	{
		return;
	}
	Accum = 0.f;
	const APlayerCameraManager* Cam = UGameplayStatics::GetPlayerCameraManager(this, 0);
	if (!Cam)
	{
		return;
	}
	const FVector Eye = Cam->GetCameraLocation();
	const double Reach = FMath::Max(1.f, CVarZoneReach.GetValueOnGameThread()) * 100.0;
	const int32 Max = FMath::Max(0, CVarZoneMax.GetValueOnGameThread());
	// the nearest within reach, a deck above or below at most (the floors between hide the rest)
	TArray<TPair<double, int32>> Near;
	for (int32 i = 0; i < Lights.Num(); ++i)
	{
		const ULightComponent* L = Lights[i].Light.Get();
		if (!L)
		{
			continue;
		}
		const FVector D = L->GetComponentLocation() - Eye;
		if (D.SizeSquared() < Reach * Reach && FMath::Abs(D.Z) < 600.0)
		{
			Near.Add({D.SizeSquared(), i});
		}
	}
	Near.Sort([](const TPair<double, int32>& A, const TPair<double, int32>& B) { return A.Key < B.Key; });
	TSet<int32> On;
	for (int32 k = 0; k < FMath::Min(Max, Near.Num()); ++k)
	{
		On.Add(Near[k].Value);
	}
	for (int32 i = 0; i < Lights.Num(); ++i)
	{
		ULightComponent* L = Lights[i].Light.Get();
		const bool bWant = On.Contains(i);
		if (L && bWant != Lights[i].bOn)
		{
			L->SetVisibility(bWant);
			Lights[i].bOn = bWant;
		}
	}
}
