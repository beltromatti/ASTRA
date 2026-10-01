// ASTRA — what a fleet battle costs in the game and what it holds, from the console (docs/SCALA.md): the lead's measure from the bridge, and the claim that a
// hundred and eighty ships and craft are a few components and not a few hundred.
//
//   astra.war.stat   what the instanced drawing holds (craft hulls, lamps), what the shared lists cost, the effects' counters, and what the world holds:
//                    actors, primitive components, text components, instanced components with their instances, decals, lights
//   astra.war.perf   what a battle tick has cost the game thread since the last call (simulation, moving the hulls, instanced drawing, effects), then starts again;
//                    call it before and after a stretch of play

#include "AstraBattleSubsystem.h"
#include "AstraWarFX.h"
#include "ASTRA.h"
#include "Components/DecalComponent.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Components/LightComponent.h"
#include "Components/PrimitiveComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Components/TextRenderComponent.h"
#include "EngineUtils.h"
#include "Engine/World.h"

namespace
{
	void WarStat(UWorld* World)
	{
		UAstraBattleSubsystem* B = World ? World->GetSubsystem<UAstraBattleSubsystem>() : nullptr;
		if (!B)
		{
			UE_LOG(LogASTRA, Display, TEXT("[WarStat] no battle in this world"));
			return;
		}
		UE_LOG(LogASTRA, Display, TEXT("[WarStat] draw: %s"), *B->DrawStats());
		UE_LOG(LogASTRA, Display, TEXT("[WarStat] plot: %s"), *B->PlotStats());
		UE_LOG(LogASTRA, Display, TEXT("[WarStat] %s"), *B->PerfReport(false));
		int32 Actors = 0, Prims = 0, MeshComps = 0, IsmComps = 0, IsmInstances = 0, Texts = 0, Decals = 0, Lights = 0, Ticking = 0, Hidden = 0;
		for (TActorIterator<AActor> It(World); It; ++It)
		{
			++Actors;
			TInlineComponentArray<UActorComponent*> Comps;
			It->GetComponents(Comps);
			for (UActorComponent* C : Comps)
			{
				Ticking += C->PrimaryComponentTick.IsTickFunctionEnabled() ? 1 : 0;
				if (const UPrimitiveComponent* P = Cast<UPrimitiveComponent>(C))
				{
					++Prims;
					Hidden += P->IsVisible() ? 0 : 1;
					if (const UInstancedStaticMeshComponent* I = Cast<UInstancedStaticMeshComponent>(P))
					{
						++IsmComps;
						IsmInstances += I->GetInstanceCount();
					}
					else if (Cast<UStaticMeshComponent>(P))
					{
						++MeshComps;
					}
					Texts += Cast<UTextRenderComponent>(P) ? 1 : 0;
					Decals += Cast<UDecalComponent>(P) ? 1 : 0;
				}
				Lights += Cast<ULightComponent>(C) ? 1 : 0;
			}
		}
		UE_LOG(LogASTRA, Display, TEXT("[WarStat] world: %d actors, %d primitive components (%d hidden: %d static meshes, %d instanced with %d instances, %d texts, %d decals), %d lights, %d components with a tick"),
		       Actors, Prims, Hidden, MeshComps, IsmComps, IsmInstances, Texts, Decals, Lights, Ticking);
	}

	void WarPerf(UWorld* World)
	{
		if (UAstraBattleSubsystem* B = World ? World->GetSubsystem<UAstraBattleSubsystem>() : nullptr)
		{
			UE_LOG(LogASTRA, Display, TEXT("[WarPerf] %s"), *B->PerfReport(true));
		}
	}

	FAutoConsoleCommandWithWorld CmdWarStat(TEXT("astra.war.stat"),
		TEXT("What the war's instanced drawing holds and costs, what the shared plot lists cost, and what the world holds (actors, components, instances)"),
		FConsoleCommandWithWorldDelegate::CreateStatic(&WarStat));
	FAutoConsoleCommandWithWorld CmdWarPerf(TEXT("astra.war.perf"),
		TEXT("What a battle tick has cost the game thread since the last call: simulation, moving the hulls, instanced drawing, effects (then it starts again)"),
		FConsoleCommandWithWorldDelegate::CreateStatic(&WarPerf));
}
