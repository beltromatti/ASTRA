#include "AstraSpaceLifeSimCommandlet.h"
#include "ASTRA.h"
#include "AstraBattleSubsystem.h"
#include "AstraShipSubsystem.h"
#include "AstraSpaceLife.h"
#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "HAL/FileManager.h"
#include "HAL/IConsoleManager.h"
#include "HAL/PlatformTime.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "Policies/CondensedJsonPrintPolicy.h"
#include "Tickable.h"

UAstraSpaceSimCommandlet::UAstraSpaceSimCommandlet()
{
	IsClient = false;
	IsServer = false;
	IsEditor = true;                 // the editor's plugins assume an editor engine even here
	LogToConsole = true;
	ShowErrorCount = true;
}

namespace
{
	using namespace AstraSpace;

	struct FSpaceCheck
	{
		FString Name;
		bool bPass = true;
		FString Detail;
	};

	/** The invariants of the traffic: what must hold at every moment whatever the war does. Returns the failures found (empty: all well). */
	void SpCheckInvariants(const UAstraSpaceLife& S, double Now, TArray<FSpaceCheck>& Fails, int32& OutVessels, int32& OutOverlaps)
	{
		const FLayout& L = S.GetLayout();
		const FTraffic& T = S.GetTraffic();
		const TArray<FVessel>& Vs = T.Vessels();
		OutVessels = Vs.Num();
		TMap<int32, const FVessel*> ById;
		for (const FVessel& V : Vs)
		{
			ById.Add(V.Id, &V);
			if (V.Pos.ContainsNaN() || V.Vel.ContainsNaN() || V.Att.ContainsNaN())
			{
				Fails.Add({TEXT("finite"), false, FString::Printf(TEXT("t=%.0f vessel %d (%s) has a NaN in its state"), Now, V.Id, *V.Name)});
			}
			if (V.State != EVState::Away && V.Pos.Size() > 600000.0)
			{
				Fails.Add({TEXT("bounds"), false, FString::Printf(TEXT("t=%.0f vessel %d (%s) is %.0f km out (state %s)"), Now, V.Id, *V.Name, V.Pos.Size() / 1000.0, StateName(V.State))});
			}
			const FHullDef* H = Data().Hull(V.Hull);
			if (H && V.State != EVState::Away && V.Vel.Size() > FMath::Max((double)H->Cruise * 1.8, 460.0))
			{
				Fails.Add({TEXT("speed"), false, FString::Printf(TEXT("t=%.0f vessel %d (%s) flies %.0f m/s in state %s (cruise %.0f)"), Now, V.Id, *V.Name, V.Vel.Size(), StateName(V.State), H->Cruise)});
			}
			if (V.State == EVState::Docked)
			{
				const bool bOk = L.Nodes.IsValidIndex(V.Node) && L.Nodes[V.Node].Slots.IsValidIndex(V.Slot) && L.Nodes[V.Node].Slots[V.Slot].Occupant == V.Id;
				if (!bOk)
				{
					Fails.Add({TEXT("berth"), false, FString::Printf(TEXT("t=%.0f vessel %d (%s) is docked but its berth does not say so"), Now, V.Id, *V.Name)});
				}
			}
		}
		// berths: every occupant exists, is docked there, and holds the berth; every reservation belongs to someone who is on the way
		for (int32 n = 0; n < L.Nodes.Num(); ++n)
		{
			const FNode& N = L.Nodes[n];
			for (int32 s = 0; s < N.Slots.Num(); ++s)
			{
				const FSlot& Sl = N.Slots[s];
				if (Sl.Occupant != INDEX_NONE)
				{
					const FVessel* V = ById.FindRef(Sl.Occupant);
					if (!V || V->Node != n || V->Slot != s || (V->State != EVState::Docked && V->State != EVState::Departing && V->State != EVState::Docking))
					{
						Fails.Add({TEXT("berth"), false, FString::Printf(TEXT("t=%.0f %s berth %d is held by vessel %d, which is not there"), Now, *N.Name, s, Sl.Occupant)});
					}
				}
				if (Sl.Reserved != INDEX_NONE)
				{
					const FVessel* V = ById.FindRef(Sl.Reserved);
					if (!V || V->Node != n || V->Slot != s)
					{
						Fails.Add({TEXT("reservation"), false, FString::Printf(TEXT("t=%.0f %s berth %d is reserved for vessel %d, which does not hold it"), Now, *N.Name, s, Sl.Reserved)});
					}
				}
			}
			for (int32 h = 0; h < N.HoldTaken.Num(); ++h)
			{
				if (N.HoldTaken[h] != INDEX_NONE)
				{
					const FVessel* V = ById.FindRef(N.HoldTaken[h]);
					if (!V || V->Node != n || V->Hold != h)
					{
						Fails.Add({TEXT("hold"), false, FString::Printf(TEXT("t=%.0f %s waiting point %d is taken by vessel %d, which does not wait there"), Now, *N.Name, h, N.HoldTaken[h])});
					}
				}
			}
		}
		// two hulls through each other (not counting berths, where they lie close by design)
		OutOverlaps = 0;
		for (int32 i = 0; i < Vs.Num(); ++i)
		{
			if (Vs[i].State == EVState::Away || Vs[i].State == EVState::Docked)
			{
				continue;
			}
			const FHullDef* Hi = Data().Hull(Vs[i].Hull);
			for (int32 j = i + 1; j < Vs.Num(); ++j)
			{
				if (Vs[j].State == EVState::Away || Vs[j].State == EVState::Docked)
				{
					continue;
				}
				const FHullDef* Hj = Data().Hull(Vs[j].Hull);
				if (Hi && Hj && FVector::Dist(Vs[i].Pos, Vs[j].Pos) < 0.5 * (Hi->Radius + Hj->Radius))
				{
					++OutOverlaps;
				}
			}
		}
	}

	/** The invariants of what the war leaves: what must hold of the sites at every moment whatever the war does. */
	void SpCheckWrecks(const UAstraSpaceLife& S, double Now, TArray<FSpaceCheck>& Fails)
	{
		for (const FSite& Si : S.GetWrecks().Sites())
		{
			if (Si.System != S.GetSystem().ToLower())
			{
				continue;
			}
			int32 Sum = 0;
			for (const FPodRec& P : Si.Pods)
			{
				Sum += P.Survivors;
				if (P.Pos0.ContainsNaN() || P.Vel.ContainsNaN())
				{
					Fails.Add({TEXT("wreck_finite"), false, FString::Printf(TEXT("t=%.0f site %d has a lifepod with a NaN"), Now, Si.Id)});
				}
				if (P.State == 1 && P.By.IsEmpty())
				{
					Fails.Add({TEXT("wreck_rescue"), false, FString::Printf(TEXT("t=%.0f site %d: a lifepod recovered by nobody"), Now, Si.Id)});
				}
			}
			if (Sum != Si.Aboard.Escaped || Si.Aboard.Escaped + Si.Aboard.Lost != Si.Aboard.Alive)
			{
				Fails.Add({TEXT("wreck_people"), false, FString::Printf(TEXT("t=%.0f site %d (%s): %d in the pods, %d escaped, %d lost, %d alive"), Now, Si.Id, *Si.Name, Sum, Si.Aboard.Escaped, Si.Aboard.Lost, Si.Aboard.Alive)});
			}
			for (const FPieceRec& P : Si.Pieces)
			{
				const FVector Pos = FWrecks::PosAt(P, Now);
				if (Pos.ContainsNaN() || FWrecks::AttAt(P, Now).ContainsNaN())
				{
					Fails.Add({TEXT("wreck_finite"), false, FString::Printf(TEXT("t=%.0f site %d has a piece with a NaN"), Now, Si.Id)});
				}
				if (P.bInFx && P.Section < 3 && Now - Si.DiedAt > FWrecks::HandOverS + 3.0)
				{
					Fails.Add({TEXT("wreck_handover"), false, FString::Printf(TEXT("t=%.0f site %d (%s): the effects still hold a piece %.0f s after she went"), Now, Si.Id, *Si.Name, Now - Si.DiedAt)});
				}
			}
		}
	}

	TSharedRef<FJsonObject> SpNodeJson(const FNode& N)
	{
		TSharedRef<FJsonObject> J = MakeShared<FJsonObject>();
		J->SetStringField(TEXT("id"), N.Id.ToString());
		J->SetStringField(TEXT("name"), N.Name);
		J->SetStringField(TEXT("kind"), PlaceKindName(N.Kind));
		J->SetArrayField(TEXT("km"), {MakeShared<FJsonValueNumber>(N.Pos.X / 1000.0), MakeShared<FJsonValueNumber>(N.Pos.Y / 1000.0), MakeShared<FJsonValueNumber>(N.Pos.Z / 1000.0)});
		J->SetNumberField(TEXT("slots"), N.Slots.Num());
		J->SetNumberField(TEXT("holds"), N.Holds.Num());
		return J;
	}
}

int32 UAstraSpaceSimCommandlet::Main(const FString& Params)
{
	float Seconds = 1800.f, Step = 0.1f, Every = 10.f;
	int32 Seed = 1;
	FParse::Value(*Params, TEXT("seconds="), Seconds);
	FParse::Value(*Params, TEXT("step="), Step);
	FParse::Value(*Params, TEXT("every="), Every);
	FParse::Value(*Params, TEXT("seed="), Seed);
	FString Out = FPaths::ProjectSavedDir() / TEXT("Space/run.json"), System = TEXT("Aurelia"), Exec, At;
	FParse::Value(*Params, TEXT("out="), Out);
	FParse::Value(*Params, TEXT("system="), System);
	FParse::Value(*Params, TEXT("exec="), Exec, false);
	FParse::Value(*Params, TEXT("at="), At, false);
	const bool bSelfTest = FParse::Param(*Params, TEXT("selftest"));
	if (FParse::Param(*Params, TEXT("wrecktest")))
	{
		// the records of what the war leaves, on their own (no world): AstraWrecksTest.cpp
		TArray<FString> TestFails, TestNotes;
		const double W0 = FPlatformTime::Seconds();
		const bool bOk = AstraSpace::RunWreckTests(TestFails, TestNotes);
		for (const FString& N : TestNotes)
		{
			UE_LOG(LogASTRA, Display, TEXT("[WreckTest] %s"), *N);
		}
		for (const FString& F : TestFails)
		{
			UE_LOG(LogASTRA, Display, TEXT("[WreckTest] FAIL %s"), *F);
		}
		UE_LOG(LogASTRA, Display, TEXT("%s (%d failures, %.2f s)"), bOk ? TEXT("WRECKS_SELFTEST_OK") : TEXT("WRECKS_SELFTEST_FAILED"), TestFails.Num(), FPlatformTime::Seconds() - W0);
		return bOk ? 0 : 1;
	}
	Step = FMath::Clamp(Step, 0.02f, 0.25f);
	FMath::RandInit(Seed);
	FMath::SRandInit(Seed);
	GAstraDeterministic = true;
	if (IConsoleVariable* V = IConsoleManager::Get().FindConsoleVariable(TEXT("astra.space.bench")))
	{
		V->Set(1);                                         // (a deterministic world has no living space unless it is asked for)
	}
	UWorld* World = UWorld::CreateWorld(EWorldType::Game, false, TEXT("AstraSpaceSim"));
	FWorldContext& Ctx = GEngine->CreateNewWorldContext(EWorldType::Game);
	Ctx.SetCurrentWorld(World);
	World->InitializeActorsForPlay(FURL());
	World->BeginPlay();
	UAstraBattleSubsystem* B = World->GetSubsystem<UAstraBattleSubsystem>();
	UAstraShipSubsystem* Ship = World->GetSubsystem<UAstraShipSubsystem>();
	UAstraSpaceLife* S = B ? B->GetSpace() : nullptr;
	if (!B || !Ship || !S)
	{
		UE_LOG(LogASTRA, Error, TEXT("[SpaceSim] no living space in the world"));
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
		UE_LOG(LogASTRA, Display, TEXT("[SpaceSim] %7.1f %s%s"), B->GetBattleTime(), bReport ? TEXT("REPORT ") : TEXT(""), *Text);
	});
	TArray<FString> Cmds;
	Exec.ParseIntoArray(Cmds, TEXT(";"));
	for (const FString& C : Cmds)
	{
		GEngine->Exec(World, *C.TrimStartAndEnd());
	}
	B->StartCampaign();
	if (!FParse::Param(*Params, TEXT("free")))
	{
		// the Aquila stays where she comes in (her default course would carry her out of the traffic in ten minutes): -free lets her go
		Ship->SetThrottle(0.f);
		Ship->SetSpeedMps(0.f);
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
	bool bArrived = false;
	TArray<FSpaceCheck> Fails;
	TMap<FString, int32> FailCount;
	int32 ChecksRun = 0, MaxOverlaps = 0, OverlapSamples = 0;
	double OverlapSum = 0.0;
	const double Wall0 = FPlatformTime::Seconds();
	double NextFrame = 0.0, NextCheck = 0.0;
	const int32 N = FMath::CeilToInt(Seconds / Step);
	TArray<float> WorldMs;
	WorldMs.Reserve(N);
	for (int32 i = 0; i < N; ++i)
	{
		while (NextTimed < Timed.Num() && B->GetBattleTime() >= Timed[NextTimed].Key)
		{
			GEngine->Exec(World, *Timed[NextTimed].Value);
			++NextTimed;
		}
		const float T0 = B->GetBattleTime();
		const double W0 = FPlatformTime::Seconds();
		World->Tick(LEVELTICK_All, Step);
		if (FMath::IsNearlyEqual(T0, B->GetBattleTime()))
		{
			FTickableGameObject::TickObjects(World, LEVELTICK_All, false, Step);
		}
		WorldMs.Add((float)((FPlatformTime::Seconds() - W0) * 1000.0));
		if (!bArrived && S->IsLaidOut())
		{
			bArrived = true;
			if (System != S->GetSystem())
			{
				S->Arrive(System);                         // another system than the home one: lay it out (the next tick)
				bArrived = false;
			}
		}
		if (!bArrived)
		{
			continue;
		}
		const double Now = B->GetBattleTime();
		if (Now >= NextCheck)
		{
			NextCheck = Now + 5.0;
			int32 Vessels = 0, Overlaps = 0;
			TArray<FSpaceCheck> Found;
			SpCheckInvariants(*S, Now, Found, Vessels, Overlaps);
			SpCheckWrecks(*S, S->WreckClock(), Found);
			++ChecksRun;
			MaxOverlaps = FMath::Max(MaxOverlaps, Overlaps);
			OverlapSum += Overlaps;
			++OverlapSamples;
			for (FSpaceCheck& F : Found)
			{
				int32& C = FailCount.FindOrAdd(F.Name);
				if (++C <= 3)
				{
					Fails.Add(F);
				}
			}
		}
		if (Now >= NextFrame)
		{
			NextFrame = Now + Every;
			TSharedRef<FJsonObject> F = S->BenchJson();
			F->SetNumberField(TEXT("t"), Now);
			// how many vessels are near the Aquila, to look at from her window (30, 60 and 100 km)
			{
				int32 N30 = 0, N60 = 0, N100 = 0;
				for (const FVessel& V : S->GetTraffic().Vessels())
				{
					if (V.State == EVState::Away)
					{
						continue;
					}
					const double D = FVector::Dist(V.Pos, B->PlayerPos()) / 1000.0;
					N30 += D < 30.0 ? 1 : 0;
					N60 += D < 60.0 ? 1 : 0;
					N100 += D < 100.0 ? 1 : 0;
				}
				F->SetNumberField(TEXT("near30"), N30);
				F->SetNumberField(TEXT("near60"), N60);
				F->SetNumberField(TEXT("near100"), N100);
			}
			TArray<TSharedPtr<FJsonValue>> Vs;
			for (const FVessel& V : S->GetTraffic().Vessels())
			{
				if (V.State == EVState::Away)
				{
					continue;
				}
				Vs.Add(MakeShared<FJsonValueArray>(TArray<TSharedPtr<FJsonValue>>{
					MakeShared<FJsonValueNumber>(V.Id), MakeShared<FJsonValueString>(StateName(V.State)),
					MakeShared<FJsonValueNumber>(FMath::RoundToDouble(V.Pos.X / 10.0) / 100.0), MakeShared<FJsonValueNumber>(FMath::RoundToDouble(V.Pos.Y / 10.0) / 100.0),
					MakeShared<FJsonValueNumber>(FMath::RoundToDouble(V.Pos.Z / 10.0) / 100.0), MakeShared<FJsonValueNumber>(FMath::RoundToDouble(V.Vel.Size())),
					MakeShared<FJsonValueNumber>(V.Alert)}));
			}
			F->SetArrayField(TEXT("v"), Vs);
			TArray<TSharedPtr<FJsonValue>> Ps;
			for (const FPatrol& P : S->GetTraffic().Patrols())
			{
				for (const FPatrolCraft& C : P.Craft)
				{
					Ps.Add(MakeShared<FJsonValueArray>(TArray<TSharedPtr<FJsonValue>>{MakeShared<FJsonValueNumber>(P.Id), MakeShared<FJsonValueNumber>(P.State),
						MakeShared<FJsonValueNumber>(FMath::RoundToDouble(C.Pos.X / 10.0) / 100.0), MakeShared<FJsonValueNumber>(FMath::RoundToDouble(C.Pos.Y / 10.0) / 100.0),
						MakeShared<FJsonValueNumber>(FMath::RoundToDouble(C.Pos.Z / 10.0) / 100.0)}));
				}
			}
			F->SetArrayField(TEXT("p"), Ps);
			Frames.Add(MakeShared<FJsonValueObject>(F));
		}
	}
	const double Wall = FPlatformTime::Seconds() - Wall0;
	TSharedRef<FJsonObject> Root = MakeShared<FJsonObject>();
	Root->SetStringField(TEXT("params"), Params);
	Root->SetNumberField(TEXT("seed"), Seed);
	Root->SetStringField(TEXT("system"), S->GetSystem());
	Root->SetNumberField(TEXT("battle_seconds"), B->GetBattleTime());
	Root->SetNumberField(TEXT("wall_seconds"), Wall);
	{
		TSharedRef<FJsonObject> Lay = MakeShared<FJsonObject>();
		TArray<TSharedPtr<FJsonValue>> Nodes, Lanes;
		for (const FNode& Nd : S->GetLayout().Nodes)
		{
			Nodes.Add(MakeShared<FJsonValueObject>(SpNodeJson(Nd)));
		}
		for (const FLane& Ln : S->GetLayout().Lanes)
		{
			TSharedRef<FJsonObject> J = MakeShared<FJsonObject>();
			J->SetStringField(TEXT("id"), Ln.Id.ToString());
			J->SetNumberField(TEXT("length_km"), Ln.LengthM / 1000.0);
			J->SetNumberField(TEXT("buoys"), Ln.Buoys.Num());
			TArray<TSharedPtr<FJsonValue>> Pts;
			for (const FVector& P : Ln.Pts)
			{
				Pts.Add(MakeShared<FJsonValueArray>(TArray<TSharedPtr<FJsonValue>>{MakeShared<FJsonValueNumber>(P.X / 1000.0), MakeShared<FJsonValueNumber>(P.Y / 1000.0), MakeShared<FJsonValueNumber>(P.Z / 1000.0)}));
			}
			J->SetArrayField(TEXT("km"), Pts);
			Lanes.Add(MakeShared<FJsonValueObject>(J));
		}
		Lay->SetArrayField(TEXT("nodes"), Nodes);
		Lay->SetArrayField(TEXT("lanes"), Lanes);
		Lay->SetNumberField(TEXT("rocks"), S->GetLayout().Rocks.Num());
		Root->SetObjectField(TEXT("layout"), Lay);
	}
	Root->SetArrayField(TEXT("events"), Events);
	Root->SetArrayField(TEXT("frames"), Frames);
	Root->SetObjectField(TEXT("final"), S->BenchJson());
	if (S->GetWrecks().Sites().Num())
	{
		// where the war's leavings are at the end (km, the system frame): for the map tools/art/wrecks_plot.py draws
		const FSkyFrame Sky = S->SkyFrame();
		const double Clock = S->WreckClock();
		const auto Km = [](const FVector& V) { return TArray<TSharedPtr<FJsonValue>>({MakeShared<FJsonValueNumber>(FMath::RoundToDouble(V.X / 10.0) / 100.0), MakeShared<FJsonValueNumber>(FMath::RoundToDouble(V.Y / 10.0) / 100.0),
		                                                                           MakeShared<FJsonValueNumber>(FMath::RoundToDouble(V.Z / 10.0) / 100.0)}); };
		TSharedRef<FJsonObject> WJ = MakeShared<FJsonObject>();
		WJ->SetNumberField(TEXT("clock"), Clock);
		WJ->SetArrayField(TEXT("aquila_km"), Km(B->PlayerPos()));
		WJ->SetArrayField(TEXT("gate_km"), Km(Sky.Origin));
		WJ->SetNumberField(TEXT("beacon_km"), FWrecks::BeaconKm);
		TArray<TSharedPtr<FJsonValue>> Sites;
		for (const FSite& Si : S->GetWrecks().Sites())
		{
			TSharedRef<FJsonObject> J = MakeShared<FJsonObject>();
			J->SetNumberField(TEXT("id"), Si.Id);
			J->SetStringField(TEXT("name"), Si.Name);
			J->SetStringField(TEXT("how"), HowLostName(Si.How));
			J->SetNumberField(TEXT("faction"), Si.Faction);
			J->SetNumberField(TEXT("died"), Si.DiedAt);
			TArray<TSharedPtr<FJsonValue>> Pc, Pd;
			for (const FPieceRec& P : Si.Pieces)
			{
				Pc.Add(MakeShared<FJsonValueArray>(Km(Sky.ToSystem(FWrecks::PosAt(P, Clock)))));
			}
			for (const FPodRec& P : Si.Pods)
			{
				TSharedRef<FJsonObject> Q = MakeShared<FJsonObject>();
				Q->SetArrayField(TEXT("p"), Km(Sky.ToSystem(FWrecks::PosAt(P, Clock))));
				Q->SetBoolField(TEXT("beacon"), FWrecks::BeaconOn(P, Clock));
				Q->SetNumberField(TEXT("state"), P.State);
				Q->SetNumberField(TEXT("n"), P.Survivors);
				Pd.Add(MakeShared<FJsonValueObject>(Q));
			}
			J->SetArrayField(TEXT("pieces"), Pc);
			J->SetArrayField(TEXT("pods"), Pd);
			J->SetArrayField(TEXT("field_mid"), Km(Sky.ToSystem(Si.Field.Pos0 + Si.Field.Vel * (Clock - Si.Field.T0))));
			J->SetNumberField(TEXT("field_km"), FWrecks::FieldRadiusAt(Si.Field, Clock) / 1000.0);
			Sites.Add(MakeShared<FJsonValueObject>(J));
		}
		WJ->SetArrayField(TEXT("sites"), Sites);
		Root->SetObjectField(TEXT("wrecks"), WJ);
	}
	if (WorldMs.Num())
	{
		WorldMs.Sort();
		double Sum = 0.0;
		for (const float M : WorldMs) { Sum += M; }
		TSharedRef<FJsonObject> WJ = MakeShared<FJsonObject>();
		WJ->SetNumberField(TEXT("ms_avg"), FMath::RoundToDouble(Sum / WorldMs.Num() * 1000.0) / 1000.0);
		WJ->SetNumberField(TEXT("ms_p95"), FMath::RoundToDouble(WorldMs[FMath::Min(WorldMs.Num() - 1, (int32)(WorldMs.Num() * 0.95))] * 1000.0) / 1000.0);
		WJ->SetNumberField(TEXT("ms_max"), FMath::RoundToDouble(WorldMs.Last() * 1000.0) / 1000.0);
		Root->SetObjectField(TEXT("world_tick"), WJ);
	}
	Root->SetNumberField(TEXT("checks_run"), ChecksRun);
	Root->SetNumberField(TEXT("overlap_max"), MaxOverlaps);
	Root->SetNumberField(TEXT("overlap_avg"), OverlapSamples ? OverlapSum / OverlapSamples : 0.0);
	TArray<TSharedPtr<FJsonValue>> FailJson;
	for (const FSpaceCheck& F : Fails)
	{
		TSharedRef<FJsonObject> J = MakeShared<FJsonObject>();
		J->SetStringField(TEXT("check"), F.Name);
		J->SetStringField(TEXT("detail"), F.Detail);
		FailJson.Add(MakeShared<FJsonValueObject>(J));
	}
	Root->SetArrayField(TEXT("failures"), FailJson);
	FString Json;
	const TSharedRef<TJsonWriter<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>> W = TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&Json);
	FJsonSerializer::Serialize(Root, W);
	IFileManager::Get().MakeDirectory(*FPaths::GetPath(Out), true);
	const bool bSaved = FFileHelper::SaveStringToFile(Json, *Out, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
	UE_LOG(LogASTRA, Display, TEXT("[SpaceSim] %.0f s of %s in %.1f s (x%.0f): %s -> %s%s"), B->GetBattleTime(), *S->GetSystem(), Wall, B->GetBattleTime() / FMath::Max(Wall, 0.001), *S->GetTraffic().Describe(), *Out,
	       bSaved ? TEXT("") : TEXT(" (NOT SAVED)"));
	UE_LOG(LogASTRA, Display, TEXT("[SpaceSim] %s"), *S->Stat());
	for (const FSpaceCheck& F : Fails)
	{
		UE_LOG(LogASTRA, Display, TEXT("[SpaceSim] FAIL %s: %s"), *F.Name, *F.Detail);
	}
	GEngine->DestroyWorldContext(World);
	World->DestroyWorld(false);
	if (bSelfTest)
	{
		if (Fails.Num() == 0 && ChecksRun > 0)
		{
			UE_LOG(LogASTRA, Display, TEXT("SPACE_SELFTEST_OK (%d checks of the invariants)"), ChecksRun);
			return 0;
		}
		UE_LOG(LogASTRA, Display, TEXT("SPACE_SELFTEST_FAILED (%d failures in %d checks)"), Fails.Num(), ChecksRun);
		return 1;
	}
	return bSaved ? 0 : 1;
}
