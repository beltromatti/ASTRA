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
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
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

int32 UAstraWarSimCommandlet::Main(const FString& Params)
{
	float Seconds = 900.f, Jump = -1.f, Step = 0.1f, Every = 5.f;
	FParse::Value(*Params, TEXT("seconds="), Seconds);
	FParse::Value(*Params, TEXT("jump="), Jump);
	FParse::Value(*Params, TEXT("step="), Step);
	FParse::Value(*Params, TEXT("every="), Every);
	FString Out = FPaths::ProjectSavedDir() / TEXT("War/run.json");
	FParse::Value(*Params, TEXT("out="), Out);
	FString Exec;
	FParse::Value(*Params, TEXT("exec="), Exec, false);
	Step = FMath::Clamp(Step, 0.02f, 0.1f);
	int32 Seed = 1;
	FParse::Value(*Params, TEXT("seed="), Seed);
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
		return 1;
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

	const double Wall0 = FPlatformTime::Seconds();
	double NextFrame = 0.0;
	const int32 N = FMath::CeilToInt(Seconds / Step);
	TArray<float> WorldMs;                // what a whole world tick costs (the battle, the stations, the ship: everything that ticks)
	WorldMs.Reserve(N);
	for (int32 i = 0; i < N; ++i)
	{
		const float T0 = B->GetBattleTime();
		const double W0 = FPlatformTime::Seconds();
		World->Tick(LEVELTICK_All, Step);
		if (FMath::IsNearlyEqual(T0, B->GetBattleTime()))
		{
			// the world tick did not reach the tickable subsystems: tick them as the engine loop would
			FTickableGameObject::TickObjects(World, LEVELTICK_All, false, Step);
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
			Frames.Add(MakeShared<FJsonValueObject>(F));
		}
	}
	const double Wall = FPlatformTime::Seconds() - Wall0;
	TSharedRef<FJsonObject> Root = MakeShared<FJsonObject>();
	Root->SetStringField(TEXT("params"), Params);
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
	Root->SetObjectField(TEXT("stats"), Stats);
	FString Json;
	const TSharedRef<TJsonWriter<>> W = TJsonWriterFactory<>::Create(&Json);
	FJsonSerializer::Serialize(Root, W);
	IFileManager::Get().MakeDirectory(*FPaths::GetPath(Out), true);
	const bool bSaved = FFileHelper::SaveStringToFile(Json, *Out, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
	UE_LOG(LogASTRA, Display, TEXT("[WarSim] %.0f s of battle in %.1f s (x%.0f), %d events, %d frames -> %s%s"), B->GetBattleTime(), Wall,
	       B->GetBattleTime() / FMath::Max(Wall, 0.001), Events.Num(), Frames.Num(), *Out, bSaved ? TEXT("") : TEXT(" (NOT SAVED)"));
	GEngine->DestroyWorldContext(World);
	World->DestroyWorld(false);
	return bSaved ? 0 : 1;
}
