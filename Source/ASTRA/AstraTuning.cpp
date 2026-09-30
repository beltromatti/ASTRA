// ASTRA — console commands for tuning the frame by A/B tests in the running game (docs/STATO.md, "Prestazioni"): change one
// thing, measure (tools/play.py perf), change it back. Nothing here is saved; the level and the data stay the source.

#include "ASTRA.h"
#include "Components/LocalLightComponent.h"
#include "EngineUtils.h"
#include "Engine/World.h"
#include "GameFramework/Actor.h"
#include "HAL/IConsoleManager.h"

namespace
{
	/** The bridge's own lights: tagged ASTRA.ShipLight and within this distance of the Captain's chair (cm). */
	constexpr float BridgeReach = 2500.f;

	TMap<TWeakObjectPtr<ULocalLightComponent>, float> GOriginalRadius;
	TMap<TWeakObjectPtr<ULocalLightComponent>, bool> GOriginalShadows;

	template <typename Fn>
	int32 ForBridgeLights(UWorld* World, Fn&& Do)
	{
		int32 N = 0;
		for (TActorIterator<AActor> It(World); It; ++It)
		{
			if (!It->ActorHasTag(TEXT("ASTRA.ShipLight")))
			{
				continue;
			}
			TArray<ULocalLightComponent*> Lights;
			It->GetComponents(Lights);
			for (ULocalLightComponent* L : Lights)
			{
				if (L && L->GetComponentLocation().Size() < BridgeReach)
				{
					Do(L);
					++N;
				}
			}
		}
		return N;
	}

	FAutoConsoleCommandWithWorldAndArgs CmdRadius(TEXT("astra.lights.radius"),
		TEXT("Tuning: scale the bridge lights' attenuation radius (1 = as built; e.g. astra.lights.radius 0.7)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			const float Scale = Args.Num() ? FMath::Clamp(FCString::Atof(*Args[0]), 0.1f, 4.f) : 1.f;
			const int32 N = ForBridgeLights(World, [Scale](ULocalLightComponent* L)
			{
				const float R0 = GOriginalRadius.FindOrAdd(L, L->AttenuationRadius);
				L->SetAttenuationRadius(R0 * Scale);
			});
			UE_LOG(LogASTRA, Log, TEXT("[Tuning] %d bridge lights at %.2fx their radius"), N, Scale);
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdShadows(TEXT("astra.lights.shadows"),
		TEXT("Tuning: 0 turns off the bridge lights' shadows, 1 puts back what was built"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			const bool bOn = !Args.Num() || FCString::Atoi(*Args[0]) != 0;
			int32 Shadowed = 0;
			ForBridgeLights(World, [bOn, &Shadowed](ULocalLightComponent* L)
			{
				const bool bBuilt = GOriginalShadows.FindOrAdd(L, L->CastShadows);
				L->SetCastShadows(bOn && bBuilt);
				Shadowed += bBuilt ? 1 : 0;
			});
			UE_LOG(LogASTRA, Log, TEXT("[Tuning] bridge light shadows %s (%d built with shadows)"), bOn ? TEXT("as built") : TEXT("off"), Shadowed);
		}));
}
