#include "AstraWarSimCommandlet.h"
#include "ASTRA.h"
#include "AstraBattleSubsystem.h"
#include "AstraShipSubsystem.h"
#include "AstraStations.h"
#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "HAL/PlatformTime.h"
#include "HAL/FileManager.h"
#include "HAL/PlatformProcess.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "Tickable.h"

UAstraWarSimCommandlet::UAstraWarSimCommandlet()
{
	IsClient = false;
	IsServer = false;
	IsEditor = true;                 // the editor's plugins (MetaHuman capture) assume an editor engine even here
	LogToConsole = true;
	ShowErrorCount = true;
}

namespace
{
	/** The minds in the loop (docs/GUERRA.md §8): the battle stops every `Dt` battle seconds, writes what the two sides' minds are given (the
	 *  same JSON the game's snapshot carries: `_mandate`, `_astra_groups`, the Aquila's contacts) to <dir>/s_<k>.json, and waits for
	 *  <dir>/r_<k>.json: the commands the minds gave since the last exchange (run here with the game's own `ApplyCommand`; their results
	 *  come back in the next state) and whether any mind is still thinking. While one is, the battle runs at real time (x`Speed`): the
	 *  world does not wait for a model that takes seconds to answer, as in the game; otherwise it runs as fast as it can. */
	struct FMindLink
	{
		FString Dir;
		float Dt = 1.f;
		float Speed = 1.f;
		float TimeoutS = 900.f;
		double NextAt = 0.0;
		int32 K = 0;
		bool bThinking = false;
		bool bStop = false;
		double PaceWall0 = 0.0;
		double PaceBattle0 = 0.0;
		int32 EventsSent = 0;
		TArray<TSharedPtr<FJsonValue>> Results;                      // the commands run at the last exchange: handed over with the next state
		bool Active() const { return !Dir.IsEmpty(); }
	};

	/** Warships and craft still flying, per side (the driver ends a battle that is decided). */
	TSharedRef<FJsonObject> FleetCounts(const TSharedRef<FJsonObject>& Debug)
	{
		int32 Warships[2] = {0, 0}, Craft[2] = {0, 0};
		for (const TSharedPtr<FJsonValue>& V : Debug->GetArrayField(TEXT("ships")))
		{
			const TSharedPtr<FJsonObject> S = V->AsObject();
			if (!S.IsValid() || !S->GetBoolField(TEXT("alive")))
			{
				continue;
			}
			const FString Side = S->GetStringField(TEXT("side"));
			const int32 I = Side == TEXT("astra") ? 0 : (Side == TEXT("mandate") ? 1 : -1);
			if (I < 0 || S->GetStringField(TEXT("fate")) != TEXT("alive"))
			{
				continue;
			}
			(S->GetBoolField(TEXT("craft")) ? Craft : Warships)[I] += 1;
		}
		TSharedRef<FJsonObject> R = MakeShared<FJsonObject>();
		for (int32 I = 0; I < 2; ++I)
		{
			TSharedRef<FJsonObject> J = MakeShared<FJsonObject>();
			J->SetNumberField(TEXT("warships"), Warships[I]);
			J->SetNumberField(TEXT("craft"), Craft[I]);
			R->SetObjectField(I == 0 ? TEXT("astra") : TEXT("mandate"), J);
		}
		return R;
	}

	/** One exchange with the driver: the state out, the commands in. */
	void MindExchange(FMindLink& L, UAstraBattleSubsystem* B, UAstraShipSubsystem* Ship, const TArray<TSharedPtr<FJsonValue>>& Events)
	{
		const double Wall0 = FPlatformTime::Seconds();
		TSharedRef<FJsonObject> Root = MakeShared<FJsonObject>();
		Root->SetNumberField(TEXT("k"), L.K);
		Root->SetNumberField(TEXT("t"), B->GetBattleTime());
		Root->SetArrayField(TEXT("results"), L.Results);
		L.Results.Reset();
		TSharedRef<FJsonObject> State = MakeShared<FJsonObject>();
		State->SetObjectField(TEXT("_mandate"), B->MandateViewJson());
		State->SetObjectField(TEXT("_astra_groups"), B->SideGroupsJson(0));
		State->SetArrayField(TEXT("contacts"), B->ContactsJson());
		State->SetNumberField(TEXT("hull_pct"), FMath::RoundToInt(100.f * B->PlayerHullFraction()));
		TSharedRef<FJsonObject> Shields = MakeShared<FJsonObject>();               // (the same field the game's snapshot has: the allied captains watch her protection)
		Shields->SetNumberField(TEXT("strength_pct"), FMath::RoundToInt(100.f * B->PlayerShieldFraction()));
		State->SetObjectField(TEXT("shields"), Shields);
		State->SetNumberField(TEXT("sim_time_s"), B->GetBattleTime());
		Root->SetObjectField(TEXT("state"), State);
		Root->SetObjectField(TEXT("counts"), FleetCounts(B->DebugState()));
		TArray<TSharedPtr<FJsonValue>> NewEvents;
		for (int32 i = L.EventsSent; i < Events.Num(); ++i)
		{
			NewEvents.Add(Events[i]);
		}
		L.EventsSent = Events.Num();
		Root->SetArrayField(TEXT("events"), NewEvents);
		FString Json;
		const TSharedRef<TJsonWriter<>> W = TJsonWriterFactory<>::Create(&Json);
		FJsonSerializer::Serialize(Root, W);
		const FString Base = L.Dir / FString::Printf(TEXT("s_%d.json"), L.K);
		FFileHelper::SaveStringToFile(Json, *(Base + TEXT(".tmp")), FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
		IFileManager::Get().Move(*Base, *(Base + TEXT(".tmp")), true);
		// the commands of the minds come back in r_<k>.json
		const FString Reply = L.Dir / FString::Printf(TEXT("r_%d.json"), L.K);
		while (!IFileManager::Get().FileExists(*Reply))
		{
			if (FPlatformTime::Seconds() - Wall0 > L.TimeoutS)
			{
				UE_LOG(LogASTRA, Warning, TEXT("[WarSim] the mind driver did not answer exchange %d in %.0f s: the battle stops"), L.K, L.TimeoutS);
				L.bStop = true;
				return;
			}
			FPlatformProcess::Sleep(0.002f);
		}
		FString Text;
		FFileHelper::LoadFileToString(Text, *Reply);
		IFileManager::Get().Delete(*Reply, false, true, true);
		TSharedPtr<FJsonObject> R;
		if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), R) || !R.IsValid())
		{
			UE_LOG(LogASTRA, Warning, TEXT("[WarSim] exchange %d: the reply does not parse"), L.K);
			++L.K;
			return;
		}
		const TArray<TSharedPtr<FJsonValue>>* Cmds = nullptr;
		if (R->TryGetArrayField(TEXT("commands"), Cmds))
		{
			for (const TSharedPtr<FJsonValue>& V : *Cmds)
			{
				const TSharedPtr<FJsonObject> C = V->AsObject();
				if (!C.IsValid())
				{
					continue;
				}
				const TSharedPtr<FJsonObject>* Args = nullptr;
				C->TryGetObjectField(TEXT("args"), Args);
				FString Detail;
				const bool bOk = Ship->ApplyCommand(C->GetStringField(TEXT("name")), Args ? *Args : MakeShared<FJsonObject>(), Detail);
				UE_LOG(LogASTRA, Display, TEXT("[WarSim] %7.1f mind command %s %s: %s"), B->GetBattleTime(), *C->GetStringField(TEXT("name")), bOk ? TEXT("ok") : TEXT("FAILED"), *Detail);
				TSharedRef<FJsonObject> Res = MakeShared<FJsonObject>();
				Res->SetStringField(TEXT("id"), C->GetStringField(TEXT("id")));
				Res->SetBoolField(TEXT("ok"), bOk);
				Res->SetStringField(TEXT("detail"), Detail);
				L.Results.Add(MakeShared<FJsonValueObject>(Res));
			}
		}
		bool bThink = false, bEnd = false;
		R->TryGetBoolField(TEXT("thinking"), bThink);
		R->TryGetBoolField(TEXT("stop"), bEnd);
		L.bThinking = bThink;
		L.bStop = bEnd;
		L.PaceWall0 = FPlatformTime::Seconds();
		L.PaceBattle0 = B->GetBattleTime();
		++L.K;
	}
}

namespace
{
	/** One battle from one seed: a fresh world, the variant's commands, the ticks, the record. */
	bool RunOneBattle(const FString& Params, int32 Seed, const FString& Out)
	{
		float Seconds = 900.f, Jump = -1.f, Step = 0.1f, Every = 5.f;
		FParse::Value(*Params, TEXT("seconds="), Seconds);
		FParse::Value(*Params, TEXT("jump="), Jump);
		FParse::Value(*Params, TEXT("step="), Step);
		FParse::Value(*Params, TEXT("every="), Every);
		FString Exec, Scenario, At;
		FParse::Value(*Params, TEXT("exec="), Exec, false);
		FParse::Value(*Params, TEXT("at="), At, false);            // "200=astra.cmd ...|300=...": commands at battle times (a mind's orders, scripted)
		FParse::Value(*Params, TEXT("scenario="), Scenario);
		const bool bViews = FParse::Param(*Params, TEXT("views"));
		FMindLink Mind;                                            // the minds in the loop (-mind=<dir>)
		FParse::Value(*Params, TEXT("mind="), Mind.Dir, false);
		FParse::Value(*Params, TEXT("mind_dt="), Mind.Dt);
		FParse::Value(*Params, TEXT("mind_speed="), Mind.Speed);
		FParse::Value(*Params, TEXT("mind_timeout="), Mind.TimeoutS);
		Mind.Dt = FMath::Clamp(Mind.Dt, 0.2f, 10.f);
		if (Mind.Active())
		{
			IFileManager::Get().MakeDirectory(*Mind.Dir, true);
		}
		Step = FMath::Clamp(Step, 0.02f, 0.1f);
		FMath::RandInit(Seed);           // the same seed, the same battle: comparisons change one thing at a time
		FMath::SRandInit(Seed);
		GAstraDeterministic = true;

		// a game world with its subsystems and no level: the battle needs no content (meshes that do not load are skipped)
		UWorld* World = UWorld::CreateWorld(EWorldType::Game, false, TEXT("AstraWarSim"));
		FWorldContext& Ctx = GEngine->CreateNewWorldContext(EWorldType::Game);
		Ctx.SetCurrentWorld(World);
		World->InitializeActorsForPlay(FURL());
		World->BeginPlay();
		UAstraBattleSubsystem* B = World->GetSubsystem<UAstraBattleSubsystem>();
		UAstraShipSubsystem* Ship = World->GetSubsystem<UAstraShipSubsystem>();
		UAstraStationsSubsystem* St = World->GetSubsystem<UAstraStationsSubsystem>();
		if (!B || !Ship)
		{
			UE_LOG(LogASTRA, Error, TEXT("[WarSim] no battle in the world"));
			return false;
		}
		TArray<TSharedPtr<FJsonValue>> Events, Frames;
		Ship->OnShipEvent.AddLambda([&Events, B](const FString& Text, bool bReport)
		{
			TSharedRef<FJsonObject> E = MakeShared<FJsonObject>();
			E->SetNumberField(TEXT("t"), FMath::RoundToDouble(B->GetBattleTime() * 10.0) / 10.0);
			E->SetStringField(TEXT("text"), Text);
			E->SetBoolField(TEXT("report"), bReport);
			Events.Add(MakeShared<FJsonValueObject>(E));
			UE_LOG(LogASTRA, Display, TEXT("[WarSim] %7.1f %s%s"), B->GetBattleTime(), bReport ? TEXT("REPORT ") : TEXT(""), *Text);
		});
		// the variant's commands first (console variables, spawns, station modes), before the first tick
		if (!Scenario.IsEmpty())
		{
			// data/war/scenarios/<name>.json; -aquila keeps the Aquila in it (at the origin, with the ASTRA side), as the game's scale test from the bridge does
			GEngine->Exec(World, *FString::Printf(TEXT("astra.war.scenario %s%s"), *Scenario, FParse::Param(*Params, TEXT("aquila")) ? TEXT(" aquila") : TEXT("")));
		}
		TArray<FString> Cmds;
		Exec.ParseIntoArray(Cmds, TEXT(";"));
		for (const FString& C : Cmds)
		{
			GEngine->Exec(World, *C.TrimStartAndEnd());   // astra.cmd: single quotes stand for double quotes
		}
		B->StartCampaign();
		if (Jump >= 0.f)
		{
			GEngine->Exec(World, *FString::Printf(TEXT("astra.battle.time %f"), Jump));
		}
		TArray<TPair<float, FString>> Timed;
		{
			TArray<FString> Items;
			At.ParseIntoArray(Items, TEXT("|"));
			for (const FString& It : Items)
			{
				FString T, C;
				if (It.Split(TEXT("="), &T, &C))
				{
					Timed.Add(TPair<float, FString>(FCString::Atof(*T), C.TrimStartAndEnd()));
				}
			}
		}
		int32 NextTimed = 0;

		const double Wall0 = FPlatformTime::Seconds();
		double NextFrame = 0.0;
		const int32 N = FMath::CeilToInt(Seconds / Step);
		TArray<float> WorldMs;                // what a whole world tick costs (the battle, the stations, the ship: everything that ticks)
		WorldMs.Reserve(N);
		for (int32 i = 0; i < N && !Mind.bStop; ++i)
		{
			while (NextTimed < Timed.Num() && B->GetBattleTime() >= Timed[NextTimed].Key)
			{
				GEngine->Exec(World, *Timed[NextTimed].Value);
				++NextTimed;
			}
			if (Mind.Active() && B->GetBattleTime() >= Mind.NextAt)
			{
				MindExchange(Mind, B, Ship, Events);
				Mind.NextAt = B->GetBattleTime() + Mind.Dt;
				if (Mind.bStop)
				{
					break;
				}
			}
			const float T0 = B->GetBattleTime();
			const double W0 = FPlatformTime::Seconds();
			World->Tick(LEVELTICK_All, Step);
			if (FMath::IsNearlyEqual(T0, B->GetBattleTime()))
			{
				// the world tick did not reach the tickable subsystems: tick them as the engine loop would
				FTickableGameObject::TickObjects(World, LEVELTICK_All, false, Step);
			}
			if (Mind.Active() && Mind.bThinking && Mind.Speed > 0.f)
			{
				// a mind is thinking: the world does not wait for it (the pace of the game, or Speed times it)
				const double WantWall = Mind.PaceWall0 + (B->GetBattleTime() - Mind.PaceBattle0) / Mind.Speed;
				const double Now = FPlatformTime::Seconds();
				if (WantWall > Now)
				{
					FPlatformProcess::Sleep((float)(WantWall - Now));
				}
			}
			WorldMs.Add((float)((FPlatformTime::Seconds() - W0) * 1000.0));
			if (B->GetBattleTime() >= NextFrame)
			{
				NextFrame = B->GetBattleTime() + Every;
				TSharedRef<FJsonObject> F = B->DebugState();
				if (St)
				{
					F->SetObjectField(TEXT("stations"), St->StationsJson());
				}
				if (bViews)
				{
					// what each side's mind is given of its groups (docs/GUERRA.md): to read the contract, and to measure its size
					TSharedRef<FJsonObject> V = MakeShared<FJsonObject>();
					V->SetObjectField(TEXT("astra"), B->SideGroupsJson(0));
					V->SetObjectField(TEXT("mandate"), B->SideGroupsJson(1));
					F->SetObjectField(TEXT("views"), V);
				}
				Frames.Add(MakeShared<FJsonValueObject>(F));
			}
		}
		const double Wall = FPlatformTime::Seconds() - Wall0;
		TSharedRef<FJsonObject> Root = MakeShared<FJsonObject>();
		Root->SetStringField(TEXT("params"), Params);
		Root->SetNumberField(TEXT("seed"), Seed);
		Root->SetNumberField(TEXT("battle_seconds"), B->GetBattleTime());
		Root->SetNumberField(TEXT("wall_seconds"), Wall);
		Root->SetArrayField(TEXT("events"), Events);
		Root->SetArrayField(TEXT("frames"), Frames);
		Root->SetObjectField(TEXT("final"), B->DebugState());
		TSharedRef<FJsonObject> Stats = B->WarStatsJson();
		if (WorldMs.Num())
		{
			WorldMs.Sort();
			double Sum = 0.0;
			for (const float M : WorldMs) { Sum += M; }
			TSharedRef<FJsonObject> WJ = MakeShared<FJsonObject>();
			WJ->SetNumberField(TEXT("ms_avg"), FMath::RoundToDouble(Sum / WorldMs.Num() * 1000.0) / 1000.0);
			WJ->SetNumberField(TEXT("ms_p50"), FMath::RoundToDouble(WorldMs[WorldMs.Num() / 2] * 1000.0) / 1000.0);
			WJ->SetNumberField(TEXT("ms_p95"), FMath::RoundToDouble(WorldMs[FMath::Min(WorldMs.Num() - 1, (int32)(WorldMs.Num() * 0.95))] * 1000.0) / 1000.0);
			WJ->SetNumberField(TEXT("ms_max"), FMath::RoundToDouble(WorldMs.Last() * 1000.0) / 1000.0);
			Stats->SetObjectField(TEXT("world_tick"), WJ);
		}
		Stats->SetObjectField(TEXT("draw"), B->DrawStatsJson());      // the craft and lamps staged as instances: what it costs, what it would have been as actors (docs/SCALA.md)
		Root->SetObjectField(TEXT("stats"), Stats);
		FString Json;
		const TSharedRef<TJsonWriter<>> W = TJsonWriterFactory<>::Create(&Json);
		FJsonSerializer::Serialize(Root, W);
		IFileManager::Get().MakeDirectory(*FPaths::GetPath(Out), true);
		const bool bSaved = FFileHelper::SaveStringToFile(Json, *Out, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
		UE_LOG(LogASTRA, Display, TEXT("[WarSim] seed %d: %.0f s of battle in %.1f s (x%.0f), %d events, %d frames -> %s%s"), Seed, B->GetBattleTime(), Wall,
		       B->GetBattleTime() / FMath::Max(Wall, 0.001), Events.Num(), Frames.Num(), *Out, bSaved ? TEXT("") : TEXT(" (NOT SAVED)"));
		GEngine->DestroyWorldContext(World);
		World->DestroyWorld(false);
		return bSaved;
	}
}

int32 UAstraWarSimCommandlet::Main(const FString& Params)
{
	FString Out = FPaths::ProjectSavedDir() / TEXT("War/run.json");
	FParse::Value(*Params, TEXT("out="), Out);
	int32 Seed = 1, Seeds = 1;
	FParse::Value(*Params, TEXT("seed="), Seed);
	FParse::Value(*Params, TEXT("seeds="), Seeds);            // several battles in one process: the start-up is most of a run
	Seeds = FMath::Max(1, Seeds);
	bool bAll = true;
	for (int32 k = 0; k < Seeds; ++k)
	{
		const int32 S = Seed + k;
		FString Path = Out;
		if (Path.Contains(TEXT("{seed}")))
		{
			Path = Path.Replace(TEXT("{seed}"), *FString::FromInt(S));
		}
		else if (Seeds > 1)
		{
			Path = FPaths::GetBaseFilename(Out, false) + FString::Printf(TEXT("_%d."), S) + FPaths::GetExtension(Out);
		}
		bAll &= RunOneBattle(Params, S, Path);
		if (Seeds > 1)
		{
			GEngine->ForceGarbageCollection(true);
		}
	}
	return bAll ? 0 : 1;
}
