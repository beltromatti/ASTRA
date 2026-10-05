// ASTRA — how the game starts astra-mind on any platform (AstraMindLaunch.h).

#include "AstraMindLaunch.h"

#include "ASTRA.h"
#include "HAL/FileManager.h"
#include "HAL/PlatformMisc.h"
#include "Misc/DateTime.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"

#if !PLATFORM_WINDOWS
#include <stdlib.h>   // getenv, setenv: the environment of the systems where it is bytes (below)
#endif

namespace AstraMindLaunch
{
	namespace
	{
		constexpr int32 DefaultPort = 8765;

		const TCHAR* PathSeparator(EHost Host)
		{
			return Host == EHost::Windows ? TEXT(";") : TEXT(":");
		}

		FString UvName(EHost Host)
		{
			return Host == EHost::Windows ? TEXT("uv.exe") : TEXT("uv");
		}

		/** Slashes forward (a made-up Windows machine and the real one are then compared the same way), `..` folded, no slash at the end
		 *  (but a drive's own `C:/`). The machine's own spelling comes back with NativePath. */
		FString Clean(EHost Host, FString Path)
		{
			if (Host == EHost::Windows)
			{
				Path.ReplaceCharInline(TEXT('\\'), TEXT('/'));
			}
			FPaths::CollapseRelativeDirectories(Path);
			while (Path.Len() > 1 && Path.EndsWith(TEXT("/")) && !(Path.Len() == 3 && Path[1] == TEXT(':')))
			{
				Path.LeftChopInline(1, EAllowShrinking::No);
			}
			return Path;
		}

		/** The same folder? Windows and the Mac's usual file system do not tell capitals from small letters, Linux does (FString's own == does not either). */
		bool SamePath(EHost Host, const FString& A, const FString& B)
		{
			return A.Equals(B, Host == EHost::Linux ? ESearchCase::CaseSensitive : ESearchCase::IgnoreCase);
		}

		/** An environment variable's value. On the systems whose environment is bytes (macOS, Linux) it is read as UTF-8: FPlatformMisc reads it as Latin-1, and an accent in
		 *  a user's folder name came out as two wrong characters, so that no file of that home was found. Windows' is wide characters: the engine's call is right. */
		FString EnvGet(const FString& Name)
		{
#if PLATFORM_WINDOWS
			return FPlatformMisc::GetEnvironmentVariable(*Name);
#else
			const char* Raw = getenv(TCHAR_TO_UTF8(*Name));    // portable-ok: POSIX environment bytes, read as UTF-8; Windows takes the branch above
			return Raw ? FString(UTF8_TO_TCHAR(Raw)) : FString();
#endif
		}

		/** Sets one (an empty value unsets it), in UTF-8 where the environment is bytes: FPlatformMisc writes it as Latin-1 there and the child saw a `?` for the accent of a folder
		 *  name (the old launch put the paths in the command line, which the engine converts to UTF-8: it was right). */
		void EnvSet(const FString& Name, const FString& Value)
		{
#if PLATFORM_WINDOWS
			FPlatformMisc::SetEnvironmentVar(*Name, *Value);
#else
			if (Value.IsEmpty())
			{
				unsetenv(TCHAR_TO_UTF8(*Name));                // portable-ok: POSIX; Windows takes the branch above
			}
			else
			{
				setenv(TCHAR_TO_UTF8(*Name), TCHAR_TO_UTF8(*Value), 1);      // portable-ok: POSIX; Windows takes the branch above
			}
#endif
		}

		/** A set of variables in the game's own environment, for as long as this lives: the child inherits it (both CreateProcess and
		 *  posix_spawn do), and the game's own is as it was when the launch is over. */
		class FScopedEnvironment
		{
		public:
			explicit FScopedEnvironment(const TArray<TPair<FString, FString>>& Vars)
			{
				for (const TPair<FString, FString>& V : Vars)
				{
					Before.Emplace(V.Key, EnvGet(V.Key));
					EnvSet(V.Key, V.Value);
				}
			}
			~FScopedEnvironment()
			{
				for (int32 i = Before.Num() - 1; i >= 0; --i)
				{
					EnvSet(Before[i].Key, Before[i].Value);   // (an empty value unsets it, on every system)
				}
			}

		private:
			TArray<TPair<FString, FString>> Before;
		};
	}

	FMachine FMachine::Live()
	{
		FMachine M;
		M.Host = ThisHost();
		M.ProjectDir = FPaths::ConvertRelativePathToFull(FPaths::ProjectDir());
		M.RootDir = FPaths::ConvertRelativePathToFull(FPaths::RootDir());
		M.ExeDir = FPaths::ConvertRelativePathToFull(FPaths::GetPath(FString(FPlatformProcess::ExecutablePath())));
		M.SavedDir = FPaths::ConvertRelativePathToFull(FPaths::ProjectSavedDir());
		M.Env = [](const FString& Name) { return EnvGet(Name); };
		M.IsFile = [](const FString& Path) { return IFileManager::Get().FileExists(*Path); };
		return M;
	}

	FString NativePath(EHost Host, const FString& Path)
	{
		FString Out = Path;
		if (Host == EHost::Windows)
		{
			Out.ReplaceCharInline(TEXT('/'), TEXT('\\'));
		}
		return Out;
	}

	int32 Port(const FMachine& M)
	{
		const FString S = M.Env(TEXT("ASTRA_MIND_PORT")).TrimStartAndEnd();
		bool bDigits = S.Len() > 0 && S.Len() <= 5;
		for (int32 i = 0; i < S.Len(); ++i)
		{
			bDigits &= (S[i] >= TEXT('0') && S[i] <= TEXT('9'));
		}
		const int32 Wanted = bDigits ? FCString::Atoi(*S) : 0;
		return Wanted >= 1024 && Wanted <= 65535 ? Wanted : DefaultPort;
	}

	FString DataDirFor(const FMachine& M)
	{
		const FString Chosen = M.Env(TEXT("ASTRA_HOME"));
		if (!Chosen.IsEmpty())
		{
			return Clean(M.Host, Chosen);
		}
		auto Under = [&](const TCHAR* Var, const TCHAR* Rest) -> FString
		{
			const FString Base = M.Env(Var);
			return Base.IsEmpty() ? FString() : Clean(M.Host, Base) / Rest;
		};
		FString Dir;
		switch (M.Host)
		{
		case EHost::Mac:
			Dir = Under(TEXT("HOME"), TEXT("Library/Application Support/ASTRA"));
			break;
		case EHost::Windows:
			Dir = Under(TEXT("LOCALAPPDATA"), TEXT("ASTRA"));
			if (Dir.IsEmpty())
			{
				Dir = Under(TEXT("USERPROFILE"), TEXT("AppData/Local/ASTRA"));
			}
			break;
		case EHost::Linux:
			Dir = Under(TEXT("XDG_DATA_HOME"), TEXT("ASTRA"));
			if (Dir.IsEmpty())
			{
				Dir = Under(TEXT("HOME"), TEXT(".local/share/ASTRA"));
			}
			break;
		}
		return Dir.IsEmpty() ? Clean(M.Host, M.SavedDir) / TEXT("ASTRA") : Dir;    // (no home to speak of: beside the game's own saved files)
	}

	TArray<FString> ToolDirs(const FMachine& M)
	{
		TArray<FString> Dirs;
		auto Under = [&](const TCHAR* Var, const TCHAR* Rest)
		{
			const FString Base = M.Env(Var);
			if (!Base.IsEmpty())
			{
				Dirs.Add(Clean(M.Host, Base) / Rest);
			}
		};
		switch (M.Host)
		{
		case EHost::Mac:
			Dirs.Add(TEXT("/opt/homebrew/bin"));
			Dirs.Add(TEXT("/opt/homebrew/sbin"));
			Dirs.Add(TEXT("/usr/local/bin"));
			Under(TEXT("HOME"), TEXT(".local/bin"));
			Under(TEXT("HOME"), TEXT(".cargo/bin"));
			break;
		case EHost::Windows:
			Under(TEXT("USERPROFILE"), TEXT(".local/bin"));                       // where the uv installer puts it
			Under(TEXT("USERPROFILE"), TEXT(".cargo/bin"));
			Under(TEXT("LOCALAPPDATA"), TEXT("Microsoft/WinGet/Links"));          // winget install astral-sh.uv
			break;
		case EHost::Linux:
			Under(TEXT("HOME"), TEXT(".local/bin"));
			Under(TEXT("HOME"), TEXT(".cargo/bin"));
			Dirs.Add(TEXT("/usr/local/bin"));
			break;
		}
		return Dirs;
	}

	FString ExtendPath(EHost Host, const FString& Path, const TArray<FString>& Extra)
	{
		const TCHAR* Sep = PathSeparator(Host);
		TArray<FString> Have;
		Path.ParseIntoArray(Have, Sep, true);
		auto Same = [Host](const FString& A, const FString& B) { return SamePath(Host, Clean(Host, A.TrimQuotes()), Clean(Host, B.TrimQuotes())); };
		FString Out = Path;
		for (const FString& Dir : Extra)
		{
			if (Dir.IsEmpty() || Have.ContainsByPredicate([&](const FString& H) { return Same(H, Dir); }))
			{
				continue;
			}
			if (!Out.IsEmpty() && !Out.EndsWith(Sep))
			{
				Out += Sep;
			}
			Out += NativePath(Host, Dir);
			Have.Add(Dir);
		}
		return Out;
	}

	FString FindUv(const FMachine& M, const FString& MindDir)
	{
		const FString Chosen = M.Env(TEXT("ASTRA_UV"));
		if (!Chosen.IsEmpty() && M.IsFile(Clean(M.Host, Chosen)))
		{
			return Clean(M.Host, Chosen);
		}
		TArray<FString> Dirs;
		Dirs.Add(Clean(M.Host, MindDir) / TEXT("bin"));                          // the one that travels with the game
		TArray<FString> OnPath;
		M.Env(TEXT("PATH")).ParseIntoArray(OnPath, PathSeparator(M.Host), true);
		for (const FString& D : OnPath)
		{
			Dirs.Add(Clean(M.Host, D.TrimQuotes()));
		}
		Dirs.Append(ToolDirs(M));
		const FString Name = UvName(M.Host);
		for (const FString& D : Dirs)
		{
			if (M.IsFile(D / Name))
			{
				return D / Name;
			}
		}
		return FString();
	}

	FPlan MakePlan(const FMachine& M)
	{
		FPlan P;
		const EHost H = M.Host;

		// where the mind is: ASTRA_MIND_DIR; the repository the game runs from; a Mac app's Contents/Resources/mind; a Windows or Linux package's mind/
		// next to the engine folder. The repository's own is the only one that is not "packaged" (its Python environment is mind/.venv, uv's default)
		const FString Checkout = Clean(H, Clean(H, M.ProjectDir) / TEXT("mind"));
		TArray<FString> Candidates;
		const FString Chosen = M.Env(TEXT("ASTRA_MIND_DIR"));
		if (!Chosen.IsEmpty())
		{
			Candidates.Add(Clean(H, Chosen));
		}
		Candidates.Add(Checkout);
		Candidates.Add(Clean(H, M.ExeDir / TEXT("../Resources/mind")));
		Candidates.Add(Clean(H, Clean(H, M.RootDir) / TEXT("mind")));
		FString MindDir;
		for (const FString& C : Candidates)
		{
			if (M.IsFile(C / TEXT("pyproject.toml")))
			{
				MindDir = C;
				break;
			}
		}
		if (MindDir.IsEmpty())
		{
			P.Error = FString::Printf(TEXT("the mind's folder (the one with pyproject.toml) is not in any of: %s"), *FString::Join(Candidates, TEXT(", ")));
			return P;
		}
		P.bPackaged = !SamePath(H, MindDir, Checkout);

		const FString Uv = FindUv(M, MindDir);
		if (Uv.IsEmpty())
		{
			P.Error = FString::Printf(TEXT("uv (the program that runs the mind) was not found: install it (https://docs.astral.sh/uv/), or put %s in %s"), *UvName(H),
			                          *NativePath(H, MindDir / TEXT("bin")));
			return P;
		}

		P.MindDir = NativePath(H, MindDir);
		P.Uv = NativePath(H, Uv);
		const FString Logs = Clean(H, M.SavedDir) / TEXT("Logs");
		P.LogFile = NativePath(H, Logs / TEXT("astra-mind.log"));

		// what the child sees: the game's Saved folder (the campaign lives there: the mind keeps the war and the story beside it), its own log, and
		// for a packaged mind its own data folder (the key, the voice models, the caches) with its Python environment in it
		P.Env.Emplace(TEXT("ASTRA_SAVED"), NativePath(H, M.SavedDir));
		P.Env.Emplace(TEXT("ASTRA_MIND_LOG"), P.LogFile);
		if (P.bPackaged)
		{
			const FString Data = DataDirFor(M);
			P.DataDir = NativePath(H, Data);
			P.Env.Emplace(TEXT("ASTRA_HOME"), P.DataDir);
			P.Env.Emplace(TEXT("UV_PROJECT_ENVIRONMENT"), NativePath(H, Data / TEXT("venv")));
			// the mind's sources are inside the signed app (or a folder the player may not write): Python keeps their compiled bytecode in the
			// data folder, never beside them (a file written into a signed bundle breaks its seal)
			P.Env.Emplace(TEXT("PYTHONPYCACHEPREFIX"), NativePath(H, Data / TEXT("pycache")));
		}
		if (H != EHost::Mac)
		{
			P.Env.Emplace(TEXT("PYTHONUTF8"), TEXT("1"));                          // text files are UTF-8 whatever the console's code page is
		}
		if (H == EHost::Windows)
		{
			P.Env.Emplace(TEXT("HF_HUB_DISABLE_SYMLINKS_WARNING"), TEXT("1"));     // (the model cache copies where it may not link: said once in the log is enough)
		}
		// a program started from the desktop has the bare PATH of the desktop: the places our tools are installed in are added at its end
		const FString PathNow = M.Env(TEXT("PATH"));
		const FString PathNew = ExtendPath(H, PathNow, ToolDirs(M));
		if (PathNew != PathNow)
		{
			P.Env.Emplace(TEXT("PATH"), PathNew);
		}
		return P;
	}

	FString FPlan::Describe() const
	{
		if (!IsValid())
		{
			return Error;
		}
		return FString::Printf(TEXT("%s %s in %s (%s%s), log %s"), *Uv, *Args, *MindDir, bPackaged ? TEXT("packaged, data ") : TEXT("repository"),
		                       bPackaged ? *DataDir : TEXT(""), *LogFile);
	}

	void AppendLog(const FString& LogFile, const FString& Text)
	{
		const FString Line = FString::Printf(TEXT("%s astra.game %s\n"), *FDateTime::Now().ToString(TEXT("%Y-%m-%d %H:%M:%S,%s")), *Text);
		FFileHelper::SaveStringToFile(Line, *LogFile, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM, &IFileManager::Get(), FILEWRITE_Append);
	}

	bool Start(const FPlan& Plan, FProcHandle& OutProc, FString& OutError)
	{
		if (!Plan.IsValid())
		{
			OutError = Plan.Error;
			return false;
		}
		IFileManager::Get().MakeDirectory(*FPaths::GetPath(Plan.LogFile), true);
		if (Plan.bPackaged)
		{
			IFileManager::Get().MakeDirectory(*Plan.DataDir, true);
		}
		AppendLog(Plan.LogFile, FString::Printf(TEXT("starting the mind: %s"), *Plan.Describe()));
		FScopedEnvironment Environment(Plan.Env);
		uint32 ProcessId = 0;
		// detached and hidden (no console window on Windows, no terminal's signals on a Mac), in the mind's folder: uv finds its project there
		OutProc = FPlatformProcess::CreateProc(*Plan.Uv, *Plan.Args, true, true, true, &ProcessId, 0, *Plan.MindDir, nullptr, nullptr);
		if (!OutProc.IsValid())
		{
			OutError = FString::Printf(TEXT("the system would not start %s"), *Plan.Uv);
			AppendLog(Plan.LogFile, FString::Printf(TEXT("the mind failed to start: %s"), *OutError));
			return false;
		}
		UE_LOG(LogASTRA, Verbose, TEXT("[Mind] process %u"), ProcessId);
		return true;
	}
}
