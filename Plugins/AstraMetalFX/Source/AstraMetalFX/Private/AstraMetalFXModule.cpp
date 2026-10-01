// Copyright ASTRA.

#include "AstraMetalFXModule.h"
#include "AstraMetalFXManager.h"
#include "Engine/Engine.h"
#include "Misc/CoreDelegates.h"
#include "Modules/ModuleManager.h"

IMPLEMENT_MODULE(FAstraMetalFXModule, AstraMetalFX)

static FDelegateHandle GPostEngineInitHandle;

FAstraMetalFXModule* FAstraMetalFXModule::Get()
{
	return FModuleManager::GetModulePtr<FAstraMetalFXModule>(TEXT("AstraMetalFX"));
}

void FAstraMetalFXModule::StartupModule()
{
	// The RHI and the scene view extension registry only exist once the engine is up (the descriptor asks for PostEngineInit;
	// the delegate covers a module loaded earlier by some other route).
	if (GEngine)
	{
		FAstraMetalFXManager::Get().Startup();
	}
	else
	{
		GPostEngineInitHandle = FCoreDelegates::GetOnPostEngineInit().AddLambda([]()
		{
			FAstraMetalFXManager::Get().Startup();
		});
	}
}

void FAstraMetalFXModule::ShutdownModule()
{
	if (GPostEngineInitHandle.IsValid())
	{
		FCoreDelegates::GetOnPostEngineInit().Remove(GPostEngineInitHandle);
		GPostEngineInitHandle.Reset();
	}
	FAstraMetalFXManager::Get().Shutdown();
}

FAstraMetalFXStatus FAstraMetalFXModule::GetStatus() const
{
	return FAstraMetalFXManager::Get().GetStatus();
}
