// ASTRA — how the game starts astra-mind (the Python service in mind/) on any platform: where its sources are, where its data lives,
// which `uv` runs it, what the child process sees. Nothing here is a shell command: the game starts `uv` itself, with arguments, a working
// folder and an environment (docs/WINDOWS.md).
//
// Everything that differs between the operating systems is data in this unit (names, folders, separators), asked of a FMachine that the
// real game fills from the OS and the self-test (-run=AstraMindLaunch, AstraMindLaunchCommandlet.cpp) fills with made-up Windows, Linux and
// Mac machines: the logic of every system is therefore checked on whichever one the developer has. Only Start() touches the OS, and it
// does so with the engine's own portable calls.
#pragma once

#include "CoreMinimal.h"
#include "HAL/PlatformProcess.h"

namespace AstraMindLaunch
{
	/** The operating systems the mind is started on. */
	enum class EHost : uint8 { Mac, Windows, Linux };

	constexpr EHost ThisHost()
	{
#if PLATFORM_WINDOWS
		return EHost::Windows;
#elif PLATFORM_MAC
		return EHost::Mac;
#else
		return EHost::Linux;
#endif
	}

	/** What the launcher asks of the machine: its folders, its environment, its files. Paths are absolute; any slash will do. */
	struct FMachine
	{
		EHost Host = ThisHost();
		FString ProjectDir;                        // the game's project folder: the repository itself when the game runs from it
		FString RootDir;                           // the folder that holds the engine and the project in a packaged game
		FString ExeDir;                            // the folder of the running executable
		FString SavedDir;                          // the game's Saved folder (the campaign lives there)
		TFunction<FString(const FString&)> Env;    // an environment variable, "" when it is not set
		TFunction<bool(const FString&)> IsFile;

		/** This machine, as the OS tells it. */
		static FMachine Live();
	};

	/** What to start and how. Paths in it are in the form the OS wants (backslashes on Windows). */
	struct FPlan
	{
		FString MindDir;                           // where pyproject.toml lives: the working folder of the child
		bool bPackaged = false;                    // the mind travels with the game: its own data folder and Python environment
		FString DataDir;                           // ASTRA_HOME, for a packaged mind: the key, the voice models, the caches, the venv
		FString Uv;                                // the executable that runs it
		FString Args = TEXT("run --frozen astra-mind");
		FString LogFile;                           // the mind writes its own log here (ASTRA_MIND_LOG)
		TArray<TPair<FString, FString>> Env;       // what the child sees on top of the game's own environment
		FString Error;                             // why it cannot be started (empty: it can)

		bool IsValid() const { return Error.IsEmpty(); }
		/** One line for the log. */
		FString Describe() const;
	};

	/** The port the mind listens on and the game connects to: ASTRA_MIND_PORT when it is a usable port, else 8765 (the same rule as host.py). */
	int32 Port(const FMachine& M);

	/** Where the mind lives, which uv starts it, and what the child sees. */
	FPlan MakePlan(const FMachine& M);

	/** One line of what the game did, in the mind's own log file and the mind's format (`2026-10-04 04:55:51,959 astra.game text`): the story of a start that
	 *  failed before Python could write anything (no network for uv, a bad lock) is then in one place. Best effort; on Windows only while the mind is not running
	 *  (the mind holds the file open without sharing it for writing: the line is written just before the mind starts and after it has stopped). */
	void AppendLog(const FString& LogFile, const FString& Text);

	/** Start it: `uv` with its arguments in the mind's folder, hidden, detached, its environment set for the instant of the launch and given back
	 *  (the game's own is left as it was). False with a reason in `OutError` when the plan is not valid or the OS refuses. */
	bool Start(const FPlan& Plan, FProcHandle& OutProc, FString& OutError);

	// ---- the pieces, public for the self-test

	/** The folder of a packaged mind's own data: ASTRA_HOME if the environment has it, else Application Support/ASTRA on the Mac,
	 *  %LOCALAPPDATA%\ASTRA on Windows, ~/.local/share/ASTRA on Linux. */
	FString DataDirFor(const FMachine& M);

	/** The folders a program of ours is usually installed in without being on the PATH of a program started from a desktop (Homebrew, the
	 *  uv installer's folder): added to the child's PATH, after what it has. */
	TArray<FString> ToolDirs(const FMachine& M);

	/** The uv to run: ASTRA_UV; the one shipped in <mind>/bin; one on the PATH; one in the usual folders. "" when there is none. */
	FString FindUv(const FMachine& M, const FString& MindDir);

	/** `Path` in the form the OS wants: backslashes on Windows, as it is elsewhere. */
	FString NativePath(EHost Host, const FString& Path);

	/** A PATH with the folders of `Extra` that it lacks added at its end, separator and case rules of the system. Unchanged when it lacks none. */
	FString ExtendPath(EHost Host, const FString& Path, const TArray<FString>& Extra);
}
