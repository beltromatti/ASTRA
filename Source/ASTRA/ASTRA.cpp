// Copyright Epic Games, Inc. All Rights Reserved.

#include "ASTRA.h"
#include "AstraSettings.h"
#include "Modules/ModuleManager.h"
#include "Containers/Ticker.h"
#include "Engine/Engine.h"
#include "Engine/GameViewportClient.h"
#include "GameFramework/GameUserSettings.h"
#include "HAL/PlatformApplicationMisc.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "UnrealEngine.h"

bool GAstraDeterministic = false;

class FASTRAGameModule : public FDefaultGameModuleImpl
{
public:
	virtual void StartupModule() override
	{
// portable-ok: the Mac's own start-up problem; Windows starts in borderless full screen from Config/Windows/WindowsGameUserSettings.ini
#if !WITH_EDITOR && PLATFORM_MAC
		// The app opens in a window and goes full screen by itself once it is in front. When the engine creates a window
		// already full screen it waits, without a limit, for macOS to finish the transition, and macOS makes it only for
		// the active app: launched while another app kept the focus, the game never started. The saved setting stays
		// "windowed", so no start can hang; -windowed keeps the window; the green button leaves and re-enters full screen.
		if (!FParse::Param(FCommandLine::Get(), TEXT("windowed")))
		{
			FTSTicker::GetCoreTicker().AddTicker(FTickerDelegate::CreateLambda([](float) -> bool
			{
				if (!GEngine || !GEngine->GameViewport || !GEngine->GameViewport->Viewport || !FPlatformApplicationMisc::IsThisApplicationForeground())
				{
					return true;    // not yet
				}
				if (GSystemResolution.WindowMode == EWindowMode::Windowed && FAstraSettings::Get().Display != 2)   // (DISPLAY: WINDOW keeps the window)
				{
					const FIntPoint Desktop = GEngine->GetGameUserSettings() ? GEngine->GetGameUserSettings()->GetDesktopResolution() : FIntPoint::ZeroValue;
					if (Desktop.X > 0 && Desktop.Y > 0)
					{
						FSystemResolution::RequestResolutionChange(Desktop.X, Desktop.Y, EWindowMode::WindowedFullscreen);
					}
				}
				return false;       // once
			}), 0.25f);
		}
#endif
	}
};

IMPLEMENT_PRIMARY_GAME_MODULE(FASTRAGameModule, ASTRA, "ASTRA");

DEFINE_LOG_CATEGORY(LogASTRA)
