#include "AstraMindLaunchCommandlet.h"

#include "ASTRA.h"
#include "AstraMindLaunch.h"
#include "Containers/Ticker.h"
#include "HAL/FileManager.h"
#include "HAL/PlatformMisc.h"
#include "HAL/PlatformProcess.h"
#include "IWebSocket.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Modules/ModuleManager.h"
#include "WebSocketsModule.h"

using namespace AstraMindLaunch;

namespace
{
	int32 MlChecked = 0;
	int32 MlFailed = 0;

	void MlCheck(const TCHAR* Name, bool bPass, const FString& Detail = FString())
	{
		++MlChecked;
		MlFailed += bPass ? 0 : 1;
		UE_LOG(LogASTRA, Display, TEXT("[MindLaunch] %s %-64s %s"), bPass ? TEXT("PASS") : TEXT("FAIL"), Name, *Detail);
	}

	void MlCheckEq(const TCHAR* Name, const FString& Got, const FString& Want)
	{
		const bool bSame = Got.Equals(Want, ESearchCase::CaseSensitive);                         // (FString's own == ignores case)
		MlCheck(Name, bSame, bSame ? Got : FString::Printf(TEXT("got '%s', wanted '%s'"), *Got, *Want));
	}

	FString MlEnvOf(const FPlan& P, const TCHAR* Name)
	{
		for (const TPair<FString, FString>& V : P.Env)
		{
			if (V.Key == Name)
			{
				return V.Value;
			}
		}
		return FString();
	}

	bool MlHasEnv(const FPlan& P, const TCHAR* Name)
	{
		return P.Env.ContainsByPredicate([Name](const TPair<FString, FString>& V) { return V.Key == Name; });
	}

	const TCHAR* MlHostName(EHost Host)
	{
		switch (Host)
		{
		case EHost::Mac: return TEXT("Mac");
		case EHost::Windows: return TEXT("Windows");
		default: return TEXT("Linux");
		}
	}

	/** A made-up machine: its folders, its files, its environment. */
	struct FMlFake
	{
		EHost Host = EHost::Mac;
		FString ProjectDir, RootDir, ExeDir, SavedDir;
		TSet<FString> Files;
		TMap<FString, FString> Env;

		FMachine Make() const
		{
			FMachine M;
			M.Host = Host;
			M.ProjectDir = ProjectDir;
			M.RootDir = RootDir;
			M.ExeDir = ExeDir;
			M.SavedDir = SavedDir;
			M.Env = [this](const FString& Name) { const FString* V = Env.Find(Name); return V ? *V : FString(); };
			M.IsFile = [this](const FString& Path) { return Files.Contains(Path); };
			return M;
		}
	};

	// ----------------------------------------------------------------------------------------------------------------------------- the machines

	/** What a Mac developer runs: the editor on the repository, uv from Homebrew, a bare PATH (as a program started from a desktop has). */
	FMlFake MlMacCheckout()
	{
		FMlFake F;
		F.Host = EHost::Mac;
		F.ProjectDir = TEXT("/Users/me/ASTRA/");
		F.RootDir = TEXT("/Users/Shared/Epic Games/UE_5.8/");
		F.ExeDir = TEXT("/Users/Shared/Epic Games/UE_5.8/Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS");
		F.SavedDir = TEXT("/Users/me/ASTRA/Saved/");
		F.Files = {TEXT("/Users/me/ASTRA/mind/pyproject.toml"), TEXT("/opt/homebrew/bin/uv")};
		F.Env = {{TEXT("HOME"), TEXT("/Users/me")}, {TEXT("PATH"), TEXT("/usr/bin:/bin:/usr/sbin:/sbin")}};
		return F;
	}

	/** The packaged Mac app, in ~/Applications, uv from the uv installer's own folder. */
	FMlFake MlMacApp()
	{
		FMlFake F;
		F.Host = EHost::Mac;
		F.ProjectDir = TEXT("/Users/me/Applications/ASTRA.app/Contents/UE/ASTRA/");
		F.RootDir = TEXT("/Users/me/Applications/ASTRA.app/Contents/UE/");
		F.ExeDir = TEXT("/Users/me/Applications/ASTRA.app/Contents/MacOS");
		F.SavedDir = TEXT("/Users/me/Library/Application Support/Epic/ASTRA/Saved/");
		F.Files = {TEXT("/Users/me/Applications/ASTRA.app/Contents/Resources/mind/pyproject.toml"), TEXT("/Users/me/.local/bin/uv")};
		F.Env = {{TEXT("HOME"), TEXT("/Users/me")}, {TEXT("PATH"), TEXT("/usr/bin:/bin")}};
		return F;
	}

	/** The Windows package: Packaged/Windows with the mind beside the engine folder, its own uv.exe in mind/bin. */
	FMlFake MlWindowsPackage()
	{
		FMlFake F;
		F.Host = EHost::Windows;
		F.ProjectDir = TEXT("C:/Games/ASTRA/Windows/ASTRA/");
		F.RootDir = TEXT("C:/Games/ASTRA/Windows/");
		F.ExeDir = TEXT("C:/Games/ASTRA/Windows/ASTRA/Binaries/Win64");
		F.SavedDir = TEXT("C:/Users/me/AppData/Local/ASTRA/Saved/");
		F.Files = {TEXT("C:/Games/ASTRA/Windows/mind/pyproject.toml"), TEXT("C:/Games/ASTRA/Windows/mind/bin/uv.exe")};
		F.Env = {{TEXT("LOCALAPPDATA"), TEXT("C:\\Users\\me\\AppData\\Local")}, {TEXT("USERPROFILE"), TEXT("C:\\Users\\me")},
		         {TEXT("PATH"), TEXT("C:\\Windows\\System32;C:\\Windows;C:\\Tools")}};
		return F;
	}

	// ----------------------------------------------------------------------------------------------------------------------------- the logic

	void MlMachineChecks()
	{
		// ---- a Mac developer: the repository's own mind. What the shell launch did, the plan says in the same words.
		{
			const FMlFake F = MlMacCheckout();
			const FPlan P = MakePlan(F.Make());
			MlCheck(TEXT("mac checkout: a plan"), P.IsValid(), P.Error);
			MlCheckEq(TEXT("mac checkout: the mind is the repository's"), P.MindDir, TEXT("/Users/me/ASTRA/mind"));
			MlCheck(TEXT("mac checkout: not packaged (its environment is mind/.venv)"), !P.bPackaged && !MlHasEnv(P, TEXT("ASTRA_HOME")) && !MlHasEnv(P, TEXT("UV_PROJECT_ENVIRONMENT")));
			MlCheckEq(TEXT("mac checkout: uv found where Homebrew puts it, off the bare PATH"), P.Uv, TEXT("/opt/homebrew/bin/uv"));
			MlCheckEq(TEXT("mac checkout: ASTRA_SAVED is the Saved folder, as before"), MlEnvOf(P, TEXT("ASTRA_SAVED")), TEXT("/Users/me/ASTRA/Saved/"));
			MlCheckEq(TEXT("mac checkout: the log is the same file as before"), MlEnvOf(P, TEXT("ASTRA_MIND_LOG")), TEXT("/Users/me/ASTRA/Saved/Logs/astra-mind.log"));
			MlCheck(TEXT("mac checkout: nothing Windows-only in its environment"), !MlHasEnv(P, TEXT("PYTHONUTF8")) && !MlHasEnv(P, TEXT("HF_HUB_DISABLE_SYMLINKS_WARNING")));
			MlCheckEq(TEXT("mac checkout: the PATH keeps what it had and gains the tool folders"), MlEnvOf(P, TEXT("PATH")),
			        TEXT("/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/Users/me/.local/bin:/Users/me/.cargo/bin"));
			MlCheckEq(TEXT("mac checkout: the arguments are the old ones"), P.Args, TEXT("run --frozen astra-mind"));
		}
		// ---- the same, from a terminal whose PATH already has Homebrew: nothing is added twice
		{
			FMlFake F = MlMacCheckout();
			F.Env.Add(TEXT("PATH"), TEXT("/opt/homebrew/bin:/usr/bin:/bin:/Users/me/.local/bin/"));
			const FPlan P = MakePlan(F.Make());
			MlCheckEq(TEXT("mac terminal: a folder already on the PATH is not added again (a slash at its end is the same folder)"), MlEnvOf(P, TEXT("PATH")),
			        TEXT("/opt/homebrew/bin:/usr/bin:/bin:/Users/me/.local/bin/:/opt/homebrew/sbin:/usr/local/bin:/Users/me/.cargo/bin"));
		}
		// ---- the Mac app: what the shell launch built, with the same words
		{
			const FMlFake F = MlMacApp();
			const FPlan P = MakePlan(F.Make());
			const FString OldHome = F.Env[TEXT("HOME")] / TEXT("Library/Application Support/ASTRA");        // (the formula of the shell launch)
			MlCheck(TEXT("mac app: a plan"), P.IsValid(), P.Error);
			MlCheckEq(TEXT("mac app: the mind is in the bundle's Resources"), P.MindDir, TEXT("/Users/me/Applications/ASTRA.app/Contents/Resources/mind"));
			MlCheck(TEXT("mac app: packaged"), P.bPackaged);
			MlCheckEq(TEXT("mac app: ASTRA_HOME is Application Support/ASTRA, as before"), MlEnvOf(P, TEXT("ASTRA_HOME")), OldHome);
			MlCheckEq(TEXT("mac app: the venv is in it, as before"), MlEnvOf(P, TEXT("UV_PROJECT_ENVIRONMENT")), OldHome + TEXT("/venv"));
			MlCheckEq(TEXT("mac app: Python's bytecode in the data folder, never in the signed bundle"), MlEnvOf(P, TEXT("PYTHONPYCACHEPREFIX")), OldHome + TEXT("/pycache"));
			MlCheckEq(TEXT("mac app: uv from the uv installer's folder"), P.Uv, TEXT("/Users/me/.local/bin/uv"));
			MlCheckEq(TEXT("mac app: ASTRA_SAVED"), MlEnvOf(P, TEXT("ASTRA_SAVED")), TEXT("/Users/me/Library/Application Support/Epic/ASTRA/Saved/"));
			MlCheck(TEXT("mac app: the data folder is where the shell launch had it"), P.DataDir == OldHome);
		}
		// ---- the Windows package: its own uv.exe wins, every path in the form Windows wants
		{
			const FMlFake F = MlWindowsPackage();
			const FPlan P = MakePlan(F.Make());
			MlCheck(TEXT("windows package: a plan"), P.IsValid(), P.Error);
			MlCheckEq(TEXT("windows package: the mind beside the engine folder"), P.MindDir, TEXT("C:\\Games\\ASTRA\\Windows\\mind"));
			MlCheckEq(TEXT("windows package: the shipped uv.exe, not one that happens to be on the PATH"), P.Uv, TEXT("C:\\Games\\ASTRA\\Windows\\mind\\bin\\uv.exe"));
			MlCheck(TEXT("windows package: packaged"), P.bPackaged);
			MlCheckEq(TEXT("windows package: data in %LOCALAPPDATA%\\ASTRA"), MlEnvOf(P, TEXT("ASTRA_HOME")), TEXT("C:\\Users\\me\\AppData\\Local\\ASTRA"));
			MlCheckEq(TEXT("windows package: the venv in it"), MlEnvOf(P, TEXT("UV_PROJECT_ENVIRONMENT")), TEXT("C:\\Users\\me\\AppData\\Local\\ASTRA\\venv"));
			MlCheckEq(TEXT("windows package: Python's bytecode in the data folder"), MlEnvOf(P, TEXT("PYTHONPYCACHEPREFIX")), TEXT("C:\\Users\\me\\AppData\\Local\\ASTRA\\pycache"));
			MlCheckEq(TEXT("windows package: ASTRA_SAVED"), MlEnvOf(P, TEXT("ASTRA_SAVED")), TEXT("C:\\Users\\me\\AppData\\Local\\ASTRA\\Saved\\"));
			MlCheckEq(TEXT("windows package: the log"), MlEnvOf(P, TEXT("ASTRA_MIND_LOG")), TEXT("C:\\Users\\me\\AppData\\Local\\ASTRA\\Saved\\Logs\\astra-mind.log"));
			MlCheckEq(TEXT("windows package: text is UTF-8 whatever the console's code page"), MlEnvOf(P, TEXT("PYTHONUTF8")), TEXT("1"));
			MlCheck(TEXT("windows package: the model cache's symlink warning is off"), MlEnvOf(P, TEXT("HF_HUB_DISABLE_SYMLINKS_WARNING")) == TEXT("1"));
			MlCheckEq(TEXT("windows package: PATH with ; and backslashes, the tool folders after what it had"), MlEnvOf(P, TEXT("PATH")),
			        TEXT("C:\\Windows\\System32;C:\\Windows;C:\\Tools;C:\\Users\\me\\.local\\bin;C:\\Users\\me\\.cargo\\bin;C:\\Users\\me\\AppData\\Local\\Microsoft\\WinGet\\Links"));
		}
		// ---- Windows: uv from the PATH, from the installer's folder, case and slashes of PATH entries
		{
			FMlFake F = MlWindowsPackage();
			F.Files.Remove(TEXT("C:/Games/ASTRA/Windows/mind/bin/uv.exe"));
			F.Files.Add(TEXT("C:/Tools/uv.exe"));
			MlCheckEq(TEXT("windows: uv on the PATH"), MakePlan(F.Make()).Uv, TEXT("C:\\Tools\\uv.exe"));
			F.Files.Remove(TEXT("C:/Tools/uv.exe"));
			F.Files.Add(TEXT("C:/Users/me/.local/bin/uv.exe"));
			MlCheckEq(TEXT("windows: uv in %USERPROFILE%\\.local\\bin, which is not on the PATH"), MakePlan(F.Make()).Uv, TEXT("C:\\Users\\me\\.local\\bin\\uv.exe"));
			F.Files.Remove(TEXT("C:/Users/me/.local/bin/uv.exe"));
			F.Files.Add(TEXT("C:/Users/me/AppData/Local/Microsoft/WinGet/Links/uv.exe"));
			MlCheckEq(TEXT("windows: uv in winget's links folder"), MakePlan(F.Make()).Uv, TEXT("C:\\Users\\me\\AppData\\Local\\Microsoft\\WinGet\\Links\\uv.exe"));
			F.Env.Add(TEXT("PATH"), TEXT("\"C:\\Program Files\\Things\";c:\\users\\ME\\.local\\bin\\;C:\\Windows"));
			const FPlan P = MakePlan(F.Make());
			MlCheckEq(TEXT("windows: a PATH entry in another case, with a slash and quotes around another, is not added again"), MlEnvOf(P, TEXT("PATH")),
			        TEXT("\"C:\\Program Files\\Things\";c:\\users\\ME\\.local\\bin\\;C:\\Windows;C:\\Users\\me\\.cargo\\bin;C:\\Users\\me\\AppData\\Local\\Microsoft\\WinGet\\Links"));
			F.Files.Remove(TEXT("C:/Users/me/AppData/Local/Microsoft/WinGet/Links/uv.exe"));
			const FPlan None = MakePlan(F.Make());
			MlCheck(TEXT("windows: no uv anywhere is said, with where to put one"), !None.IsValid() && None.Error.Contains(TEXT("uv.exe")) && None.Error.Contains(TEXT("C:\\Games\\ASTRA\\Windows\\mind\\bin")), None.Error);
		}
		// ---- Windows, a developer's checkout (the editor on a PC): the repository's mind, uv's default environment
		{
			FMlFake F;
			F.Host = EHost::Windows;
			F.ProjectDir = TEXT("D:\\ASTRA\\");
			F.RootDir = TEXT("C:\\Program Files\\Epic Games\\UE_5.8\\");
			F.ExeDir = TEXT("C:\\Program Files\\Epic Games\\UE_5.8\\Engine\\Binaries\\Win64");
			F.SavedDir = TEXT("D:\\ASTRA\\Saved\\");
			F.Files = {TEXT("D:/ASTRA/mind/pyproject.toml"), TEXT("C:/Users/me/AppData/Local/Programs/uv/uv.exe")};
			F.Env = {{TEXT("USERPROFILE"), TEXT("C:\\Users\\me")}, {TEXT("PATH"), TEXT("C:\\Windows;C:\\Users\\me\\AppData\\Local\\Programs\\uv")}};
			const FPlan P = MakePlan(F.Make());
			MlCheck(TEXT("windows checkout: a plan"), P.IsValid(), P.Error);
			MlCheckEq(TEXT("windows checkout: the repository's mind"), P.MindDir, TEXT("D:\\ASTRA\\mind"));
			MlCheck(TEXT("windows checkout: not packaged, still UTF-8"), !P.bPackaged && !MlHasEnv(P, TEXT("ASTRA_HOME")) && MlEnvOf(P, TEXT("PYTHONUTF8")) == TEXT("1"));
			MlCheckEq(TEXT("windows checkout: uv from a PATH that has it"), P.Uv, TEXT("C:\\Users\\me\\AppData\\Local\\Programs\\uv\\uv.exe"));
			MlCheckEq(TEXT("windows checkout: ASTRA_SAVED"), MlEnvOf(P, TEXT("ASTRA_SAVED")), TEXT("D:\\ASTRA\\Saved\\"));
		}
		// ---- Linux
		{
			FMlFake F;
			F.Host = EHost::Linux;
			F.ProjectDir = TEXT("/opt/astra/ASTRA/");
			F.RootDir = TEXT("/opt/astra/");
			F.ExeDir = TEXT("/opt/astra/ASTRA/Binaries/Linux");
			F.SavedDir = TEXT("/home/me/.config/Epic/ASTRA/Saved/");
			F.Files = {TEXT("/opt/astra/mind/pyproject.toml"), TEXT("/home/me/.local/bin/uv")};
			F.Env = {{TEXT("HOME"), TEXT("/home/me")}, {TEXT("PATH"), TEXT("/usr/bin:/bin")}};
			FPlan P = MakePlan(F.Make());
			MlCheck(TEXT("linux package: a plan"), P.IsValid(), P.Error);
			MlCheckEq(TEXT("linux package: data in ~/.local/share/ASTRA"), MlEnvOf(P, TEXT("ASTRA_HOME")), TEXT("/home/me/.local/share/ASTRA"));
			F.Env.Add(TEXT("XDG_DATA_HOME"), TEXT("/data/xdg"));
			MlCheckEq(TEXT("linux package: XDG_DATA_HOME is honoured"), MlEnvOf(MakePlan(F.Make()), TEXT("ASTRA_HOME")), TEXT("/data/xdg/ASTRA"));
			MlCheckEq(TEXT("linux package: uv in ~/.local/bin"), P.Uv, TEXT("/home/me/.local/bin/uv"));
		}
		// ---- what the user can say: another mind folder, another uv, another data folder
		{
			FMlFake F = MlMacApp();
			F.Files.Add(TEXT("/elsewhere/mind/pyproject.toml"));
			F.Files.Add(TEXT("/elsewhere/uv"));
			F.Env.Add(TEXT("ASTRA_MIND_DIR"), TEXT("/elsewhere/mind"));
			F.Env.Add(TEXT("ASTRA_UV"), TEXT("/elsewhere/uv"));
			F.Env.Add(TEXT("ASTRA_HOME"), TEXT("/elsewhere/data/"));
			const FPlan P = MakePlan(F.Make());
			MlCheckEq(TEXT("override: ASTRA_MIND_DIR"), P.MindDir, TEXT("/elsewhere/mind"));
			MlCheckEq(TEXT("override: ASTRA_UV"), P.Uv, TEXT("/elsewhere/uv"));
			MlCheck(TEXT("override: ASTRA_HOME, and a mind that is not the repository's is a packaged one"), P.bPackaged && MlEnvOf(P, TEXT("ASTRA_HOME")) == TEXT("/elsewhere/data")
			                                                                                             && MlEnvOf(P, TEXT("UV_PROJECT_ENVIRONMENT")) == TEXT("/elsewhere/data/venv"));
			F.Env.Add(TEXT("ASTRA_UV"), TEXT("/not/there/uv"));
			MlCheckEq(TEXT("override: an ASTRA_UV that is not there falls back to the search"), MakePlan(F.Make()).Uv, TEXT("/Users/me/.local/bin/uv"));
			FMlFake Repo = MlMacCheckout();
			Repo.Env.Add(TEXT("ASTRA_MIND_DIR"), TEXT("/Users/me/ASTRA/mind"));
			MlCheck(TEXT("override: ASTRA_MIND_DIR on the repository's own mind is not a packaged one"), !MakePlan(Repo.Make()).bPackaged);
		}
		// ---- no mind at all
		{
			FMlFake F = MlMacCheckout();
			F.Files.Remove(TEXT("/Users/me/ASTRA/mind/pyproject.toml"));
			const FPlan P = MakePlan(F.Make());
			MlCheck(TEXT("no mind: said, with where it looked"), !P.IsValid() && P.Error.Contains(TEXT("/Users/me/ASTRA/mind")) && P.Error.Contains(TEXT("Contents/Resources/mind")), P.Error);
		}
		// ---- the door
		{
			FMlFake F = MlMacCheckout();
			auto PortWith = [&F](const TCHAR* Value) { F.Env.Add(TEXT("ASTRA_MIND_PORT"), Value); return Port(F.Make()); };
			MlCheck(TEXT("port: 8765 unless told"), Port(F.Make()) == 8765);
			MlCheck(TEXT("port: ASTRA_MIND_PORT"), PortWith(TEXT("18765")) == 18765 && PortWith(TEXT(" 9000 ")) == 9000);
			bool bAllDefault = true;
			for (const TCHAR* Bad : {TEXT(""), TEXT("abc"), TEXT("0"), TEXT("80"), TEXT("70000"), TEXT("-5"), TEXT("8765.5"), TEXT("123456")})
			{
				bAllDefault &= PortWith(Bad) == 8765;
			}
			MlCheck(TEXT("port: anything that is not a usable port is 8765 (the mind's own rule: host.py)"), bAllDefault);
		}
		// ---- the pieces
		{
			MlCheckEq(TEXT("NativePath: backslashes on Windows"), NativePath(EHost::Windows, TEXT("C:/a/b c/d.exe")), TEXT("C:\\a\\b c\\d.exe"));
			MlCheckEq(TEXT("NativePath: as it is elsewhere"), NativePath(EHost::Mac, TEXT("/a/b c/d")), TEXT("/a/b c/d"));
			MlCheckEq(TEXT("ExtendPath: nothing to add, nothing changed"), ExtendPath(EHost::Mac, TEXT("/a:/b"), {TEXT("/a"), TEXT("/b/")}), TEXT("/a:/b"));
			MlCheckEq(TEXT("ExtendPath: an empty PATH gets the folders"), ExtendPath(EHost::Linux, FString(), {TEXT("/x"), TEXT("/y")}), TEXT("/x:/y"));
			MlCheckEq(TEXT("ExtendPath: a Windows PATH that ends in ; is not given a second"), ExtendPath(EHost::Windows, TEXT("C:\\a;"), {TEXT("D:/b")}), TEXT("C:\\a;D:\\b"));
			MlCheckEq(TEXT("ExtendPath: Windows folders are the same in any case"), ExtendPath(EHost::Windows, TEXT("C:\\A\\B"), {TEXT("c:/a/b"), TEXT("c:/c")}), TEXT("C:\\A\\B;c:\\c"));
			MlCheckEq(TEXT("ExtendPath: Linux folders are not"), ExtendPath(EHost::Linux, TEXT("/A"), {TEXT("/a")}), TEXT("/A:/a"));
			FMlFake F;
			F.Host = EHost::Windows;
			F.SavedDir = TEXT("C:/Games/Saved/");
			MlCheckEq(TEXT("DataDirFor: no home to speak of puts the data beside the saved files"), DataDirFor(F.Make()), TEXT("C:/Games/Saved/ASTRA"));
			F.Env.Add(TEXT("USERPROFILE"), TEXT("C:\\Users\\me"));
			MlCheckEq(TEXT("DataDirFor: Windows without LOCALAPPDATA falls back to the profile"), DataDirFor(F.Make()), TEXT("C:/Users/me/AppData/Local/ASTRA"));
		}
	}

	// ----------------------------------------------------------------------------------------------------------------------------- this machine

	/** The plan this machine would make, the game's own environment left as it is by a launch that only writes down what it was given. */
	void MlProbeLaunch(const FMachine& Live, const FString& Scratch)
	{
		FMachine M = Live;
		M.SavedDir = Scratch / TEXT("ProbeSaved/");                                                      // (its log is the test's, not the game's)
		FPlan P = MakePlan(M);
		if (!P.IsValid())
		{
			MlCheck(TEXT("probe: a plan"), false, P.Error);
			return;
		}
		const FString Out = Scratch / TEXT("probe_env.txt");
		IFileManager::Get().Delete(*Out, false, true);
		if (M.Host == EHost::Windows)
		{
			P.Uv = TEXT("C:\\Windows\\System32\\cmd.exe");
			P.Args = FString::Printf(TEXT("/c set > \"%s\""), *NativePath(M.Host, Out));
		}
		else
		{
			P.Uv = TEXT("/bin/sh");
			P.Args = FString::Printf(TEXT("-c \"env | sort > '%s'\""), *Out);
		}
		const FString SavedBefore = FPlatformMisc::GetEnvironmentVariable(TEXT("ASTRA_SAVED"));
		const FString LogBefore = FPlatformMisc::GetEnvironmentVariable(TEXT("ASTRA_MIND_LOG"));
		const FString PathBefore = FPlatformMisc::GetEnvironmentVariable(TEXT("PATH"));
		FProcHandle Proc;
		FString Error;
		MlCheck(TEXT("probe: the program starts"), Start(P, Proc, Error), Error);
		FString GameLine;
		FFileHelper::LoadFileToString(GameLine, *P.LogFile);
		MlCheck(TEXT("probe: the game wrote its own line in the mind's log before the start"), GameLine.Contains(TEXT(" astra.game starting the mind: ")) && GameLine.EndsWith(TEXT("\n")), P.LogFile);
		MlCheck(TEXT("probe: the game's own environment is as it was"), FPlatformMisc::GetEnvironmentVariable(TEXT("ASTRA_SAVED")) == SavedBefore
		                                                            && FPlatformMisc::GetEnvironmentVariable(TEXT("ASTRA_MIND_LOG")) == LogBefore
		                                                            && FPlatformMisc::GetEnvironmentVariable(TEXT("PATH")) == PathBefore);
		const double T0 = FPlatformTime::Seconds();
		while (Proc.IsValid() && FPlatformProcess::IsProcRunning(Proc) && FPlatformTime::Seconds() - T0 < 20.0)
		{
			FPlatformProcess::Sleep(0.05f);
		}
		FPlatformProcess::CloseProc(Proc);
		FString Text;
		FFileHelper::LoadFileToString(Text, *Out);
		MlCheck(TEXT("probe: the child wrote its environment"), !Text.IsEmpty(), Out);
		for (const TPair<FString, FString>& V : P.Env)
		{
			const FString Name = FString::Printf(TEXT("probe: the child sees %s"), *V.Key);
			MlCheck(*Name, Text.Contains(FString::Printf(TEXT("%s=%s"), *V.Key, *V.Value)), V.Key == TEXT("PATH") ? FString() : V.Value);
		}
		UE_LOG(LogASTRA, Display, TEXT("[MindLaunch] the environment the child saw is in %s"), *Out);
	}

	/** The real mind, started by Start(), met by a WebSocket client like the game's, then stopped. */
	void MlRealLaunch(const FString& Mode, const FString& Scratch)
	{
		FMachine M = FMachine::Live();
		TMap<FString, FString> Over;
		const int32 TestPort = 18000 + (int32)(FPlatformTime::Cycles64() % 900);                      // (never the 8765 of a game that may be running)
		Over.Add(TEXT("ASTRA_MIND_PORT"), FString::FromInt(TestPort));
		M.SavedDir = Scratch / TEXT("Saved/");
		const FString RealMind = MakePlan(FMachine::Live()).MindDir;
		if (Mode == TEXT("packaged"))
		{
			// a copy of the mind laid out like a package, with a data folder of its own: what a first start on a new machine does
			FString PackRoot, PackMind;
			if (M.Host == EHost::Mac)     // (not ThisHost(): MSVC may call the branch a constant rules out unreachable code (C4702), an error in this project)
			{
				PackRoot = Scratch / TEXT("ASTRA.app/Contents");
				PackMind = PackRoot / TEXT("Resources/mind");
				M.ExeDir = PackRoot / TEXT("MacOS");
				M.ProjectDir = PackRoot / TEXT("UE/ASTRA/");
				M.RootDir = PackRoot / TEXT("UE/");
			}
			else
			{
				PackRoot = Scratch / TEXT("Windows");
				PackMind = PackRoot / TEXT("mind");
				M.ExeDir = PackRoot / TEXT("ASTRA/Binaries/Win64");
				M.ProjectDir = PackRoot / TEXT("ASTRA/");
				M.RootDir = PackRoot;
			}
			TArray<FString> Files;
			IFileManager::Get().FindFilesRecursive(Files, *RealMind, TEXT("*"), true, false);
			int32 Copied = 0;
			for (const FString& F : Files)
			{
				const FString Rel = F.RightChop(RealMind.Len() + 1);                                           // (FindFilesRecursive gives the folder's own prefix)
				if (Rel.StartsWith(TEXT(".venv")) || Rel.StartsWith(TEXT(".cache")) || Rel.StartsWith(TEXT("stt_server")) || Rel.StartsWith(TEXT("bench"))
				    || Rel.Contains(TEXT("__pycache__")) || Rel.StartsWith(TEXT(".ruff_cache")) || Rel.EndsWith(TEXT(".DS_Store")))
				{
					continue;
				}
				IFileManager::Get().MakeDirectory(*FPaths::GetPath(PackMind / Rel), true);
				IFileManager::Get().Copy(*(PackMind / Rel), *F);
				++Copied;
			}
			MlCheck(TEXT("launch: the mind's sources are copied into a package layout"), Copied > 40 && IFileManager::Get().FileExists(*(PackMind / TEXT("pyproject.toml"))),
			      FString::Printf(TEXT("%d files into %s"), Copied, *PackMind));
			Over.Add(TEXT("ASTRA_HOME"), Scratch / TEXT("Data"));
		}
		const FMachine Live = M;
		M.Env = [Over, Live](const FString& Name) { const FString* V = Over.Find(Name); return V ? *V : Live.Env(Name); };
		FPlan Plan = MakePlan(M);
		MlCheck(TEXT("launch: a plan"), Plan.IsValid(), Plan.Error);
		if (!Plan.IsValid())
		{
			return;
		}
		MlCheck(TEXT("launch: the plan is packaged exactly when asked"), Plan.bPackaged == (Mode == TEXT("packaged")));
		UE_LOG(LogASTRA, Display, TEXT("[MindLaunch] %s"), *Plan.Describe());
		// what only a test adds: no models (the voices and the recogniser are not loaded), a key that is no key (the mind wants one to be built),
		// the test's own port
		Plan.Env.Emplace(TEXT("ASTRA_MIND_PORT"), FString::FromInt(TestPort));
		Plan.Env.Emplace(TEXT("ASTRA_STT"), TEXT("off"));
		Plan.Env.Emplace(TEXT("ASTRA_TTS_WARM"), TEXT("0"));
		Plan.Env.Emplace(TEXT("OPENROUTER_API_KEY"), TEXT("test-only-not-a-key"));
		FProcHandle Proc;
		FString Error;
		const double T0 = FPlatformTime::Seconds();
		const bool bStarted = Start(Plan, Proc, Error);
		MlCheck(TEXT("launch: the process starts"), bStarted, Error);
		if (!bStarted)
		{
			return;
		}

		// a client like the game's, trying every two seconds until the mind has its door open (a first start makes the Python environment first)
		FModuleManager::LoadModuleChecked<FWebSocketsModule>(TEXT("WebSockets"));
		TSharedPtr<IWebSocket> Socket;
		bool bConnected = false, bStatus = false, bFailed = false;
		double NextTry = 0.0;
		while (!bStatus && FPlatformTime::Seconds() - T0 < 240.0 && FPlatformProcess::IsProcRunning(Proc))
		{
			const double Now = FPlatformTime::Seconds();
			if ((!Socket.IsValid() || bFailed) && Now >= NextTry)
			{
				NextTry = Now + 2.0;
				bFailed = false;
				Socket = FWebSocketsModule::Get().CreateWebSocket(FString::Printf(TEXT("ws://127.0.0.1:%d"), Port(M)), TEXT(""));
				Socket->OnConnected().AddLambda([&bConnected]() { bConnected = true; });
				Socket->OnConnectionError().AddLambda([&bFailed](const FString&) { bFailed = true; });
				Socket->OnMessage().AddLambda([&bStatus](const FString& Text) { bStatus |= Text.Contains(TEXT("\"status\"")); });
				Socket->Connect();
			}
			FTSTicker::GetCoreTicker().Tick(0.05f);
			FPlatformProcess::Sleep(0.05f);
		}
		const double UpAfter = FPlatformTime::Seconds() - T0;
		MlCheck(TEXT("launch: the game's client connects to the mind it started"), bConnected, FString::Printf(TEXT("after %.1f s"), UpAfter));
		MlCheck(TEXT("launch: and the mind speaks first (its status message)"), bStatus);
		if (Socket.IsValid())
		{
			Socket->Close();
			for (int32 i = 0; i < 10; ++i)
			{
				FTSTicker::GetCoreTicker().Tick(0.05f);
				FPlatformProcess::Sleep(0.05f);
			}
		}
		FPlatformProcess::Sleep(0.5f);                                                                          // (its log line for the connection)
		FString Log;
		FFileHelper::LoadFileToString(Log, *Plan.LogFile);
		MlCheck(TEXT("launch: the mind wrote its own log where the plan said"), Log.Contains(FString::Printf(TEXT("astra-mind listening on ws://127.0.0.1:%d"), TestPort)), Plan.LogFile);
		MlCheck(TEXT("launch: ... including that the game connected"), Log.Contains(TEXT("game connected")));
		MlCheck(TEXT("launch: the mind did not stop by itself"), FPlatformProcess::IsProcRunning(Proc));
		if (Mode == TEXT("packaged"))
		{
			MlCheck(TEXT("launch: its Python environment was made in its data folder"), IFileManager::Get().DirectoryExists(*(Plan.DataDir / TEXT("venv"))), Plan.DataDir);
		}
		else
		{
			MlCheck(TEXT("launch: the repository's own environment (mind/.venv) is the one that ran it"), IFileManager::Get().DirectoryExists(*(Plan.MindDir / TEXT(".venv"))));
		}
		// stopped as the packaged game stops it when it quits
		FPlatformProcess::TerminateProc(Proc, true);
		const double T1 = FPlatformTime::Seconds();
		while (FPlatformProcess::IsProcRunning(Proc) && FPlatformTime::Seconds() - T1 < 15.0)
		{
			FPlatformProcess::Sleep(0.05f);
		}
		MlCheck(TEXT("launch: and it stops when the game stops it"), !FPlatformProcess::IsProcRunning(Proc));
		FPlatformProcess::CloseProc(Proc);
		if (!Log.IsEmpty())
		{
			UE_LOG(LogASTRA, Display, TEXT("[MindLaunch] the mind's own log (%s), its last lines:"), *Plan.LogFile);
			TArray<FString> Lines;
			Log.ParseIntoArrayLines(Lines);
			for (int32 i = FMath::Max(0, Lines.Num() - 8); i < Lines.Num(); ++i)
			{
				UE_LOG(LogASTRA, Display, TEXT("[MindLaunch]    %s"), *Lines[i]);
			}
		}
	}
}

UAstraMindLaunchCommandlet::UAstraMindLaunchCommandlet()
{
	IsClient = false;
	IsServer = false;
	IsEditor = true;                 // the editor's plugins assume an editor engine even here (as the other benches)
	LogToConsole = true;
	ShowErrorCount = true;
}

int32 UAstraMindLaunchCommandlet::Main(const FString& Params)
{
	MlChecked = MlFailed = 0;
	const double Wall0 = FPlatformTime::Seconds();
	MlMachineChecks();

	const FMachine Live = FMachine::Live();
	const FPlan Mine = MakePlan(Live);
	UE_LOG(LogASTRA, Display, TEXT("[MindLaunch] this machine (%s): %s"), MlHostName(Live.Host), *Mine.Describe());
	UE_LOG(LogASTRA, Display, TEXT("[MindLaunch] its door: port %d"), Port(Live));
	MlCheck(TEXT("this machine: a plan (a mind folder and a uv)"), Mine.IsValid(), Mine.Error);

	FString LaunchMode;
	FParse::Value(*Params, TEXT("launch="), LaunchMode);
	const bool bProbe = FParse::Param(*Params, TEXT("probe"));
	if (bProbe || !LaunchMode.IsEmpty())
	{
		// (a folder with a space and an accented letter in its name, like the profile of a user with a first and a last name: every path of the test goes through them)
		const FString Scratch = FPaths::ConvertRelativePathToFull(FPaths::ProjectSavedDir()) / TEXT("Mind Launch Prova \u00e8");
		IFileManager::Get().DeleteDirectory(*Scratch, false, true);
		IFileManager::Get().MakeDirectory(*Scratch, true);
		if (bProbe)
		{
			MlProbeLaunch(Live, Scratch);
		}
		if (LaunchMode == TEXT("dev") || LaunchMode == TEXT("packaged"))
		{
			MlRealLaunch(LaunchMode, Scratch);
		}
	}
	UE_LOG(LogASTRA, Display, TEXT("[MindLaunch] %d checks, %d failed in %.1f s. VERDICT: %s"), MlChecked, MlFailed, FPlatformTime::Seconds() - Wall0, MlFailed == 0 ? TEXT("PASS") : TEXT("FAIL"));
	return MlFailed;
}
