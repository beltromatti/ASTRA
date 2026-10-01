#include "AstraLifeSimCommandlet.h"

#include "ASTRA.h"
#include "AstraBattleSubsystem.h"
#include "AstraDoor.h"
#include "AstraLifeBody.h"
#include "AstraLifeSim.h"
#include "AstraLifeSubsystem.h"
#include "AstraShipPlan.h"
#include "AstraShipSubsystem.h"
#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "Engine/Engine.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/World.h"
#include "HAL/PlatformTime.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Policies/CondensedJsonPrintPolicy.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "Tickable.h"

namespace
{
	struct FCheck
	{
		FString Name;
		bool bPass = true;
		FString Detail;
	};

	TArray<FCheck> Checks;

	void Check(const TCHAR* Name, bool bPass, const FString& Detail)
	{
		Checks.Add({Name, bPass, Detail});
		UE_LOG(LogASTRA, Display, TEXT("[Life] %s %-28s %s"), bPass ? TEXT("PASS") : TEXT("FAIL"), Name, *Detail);
	}

	/** A hash of where everyone is and what they are doing: two runs from the same seed must agree on it. */
	uint32 StateHash(const FAstraLifeSim& S)
	{
		uint32 H = 17;
		for (int32 i = 0; i < S.NumPeople(); ++i)
		{
			const FAstraLifePerson& P = S.Person(i);
			H = HashCombineFast(H, (uint32)(P.Act) * 31u + (uint32)P.Phase * 7u + (uint32)FMath::RoundToInt(P.Pos.X) * 3u + (uint32)FMath::RoundToInt(P.Pos.Y) * 5u + (uint32)P.Place);
		}
		return H;
	}

	TSharedRef<FJsonObject> Args(std::initializer_list<TPair<const TCHAR*, FString>> Strs, std::initializer_list<TPair<const TCHAR*, double>> Nums = {})
	{
		TSharedRef<FJsonObject> O = MakeShared<FJsonObject>();
		for (const auto& S : Strs) { O->SetStringField(S.Key, S.Value); }
		for (const auto& N : Nums) { O->SetNumberField(N.Key, N.Value); }
		return O;
	}

	double Percentile(TArray<double>& V, double P)
	{
		if (V.Num() == 0)
		{
			return 0.0;
		}
		V.Sort();
		return V[FMath::Clamp((int32)(P * (V.Num() - 1)), 0, V.Num() - 1)];
	}
}

UAstraLifeSimCommandlet::UAstraLifeSimCommandlet()
{
	IsClient = false;
	IsServer = false;
	IsEditor = true;                 // the editor's plugins assume an editor engine even here (as the war bench)
	LogToConsole = true;
	ShowErrorCount = true;
}

int32 UAstraLifeSimCommandlet::Main(const FString& Params)
{
	float Hours = 24.f, StartHour = 0.f, Step = 0.25f;
	int32 Seed = 1;
	FString Scenario = TEXT("day");
	FParse::Value(*Params, TEXT("hours="), Hours);
	FParse::Value(*Params, TEXT("hour="), StartHour);
	FParse::Value(*Params, TEXT("step="), Step);
	FParse::Value(*Params, TEXT("seed="), Seed);
	FParse::Value(*Params, TEXT("scenario="), Scenario);
	FString Out = FPaths::ProjectSavedDir() / TEXT("Life/run.json");
	FParse::Value(*Params, TEXT("out="), Out);
	Step = FMath::Clamp(Step, 0.008f, 0.5f);
	FMath::RandInit(Seed);
	FMath::SRandInit(Seed);
	GAstraDeterministic = true;
	Checks.Reset();
	const bool bDay = Scenario == TEXT("day");

	UWorld* World = UWorld::CreateWorld(EWorldType::Game, false, TEXT("AstraLifeSim"));
	FWorldContext& Ctx = GEngine->CreateNewWorldContext(EWorldType::Game);
	Ctx.SetCurrentWorld(World);
	World->InitializeActorsForPlay(FURL());
	World->BeginPlay();
	UAstraShipSubsystem* Ship = World->GetSubsystem<UAstraShipSubsystem>();
	UAstraLifeSubsystem* Life = World->GetSubsystem<UAstraLifeSubsystem>();
	UAstraShipPlan* Plan = World->GetSubsystem<UAstraShipPlan>();
	if (!Ship || !Life || !Plan)
	{
		UE_LOG(LogASTRA, Error, TEXT("[Life] the ship, its plan or the life are not in the world"));
		return 1;
	}
	auto TickWorld = [&](float Dt)
	{
		const double Before = Life->IsRunning() ? Life->Sim().GameSeconds() : -1.0;
		World->Tick(LEVELTICK_All, Dt);
		const double After = Life->IsRunning() ? Life->Sim().GameSeconds() : -1.0;
		if (FMath::IsNearlyEqual(Before, After))
		{
			FTickableGameObject::TickObjects(World, LEVELTICK_All, false, Dt);       // the world tick did not reach the tickable subsystems
		}
	};
	// the plan and the tables load on a worker: give them a moment
	const double Wall0 = FPlatformTime::Seconds();
	for (int32 i = 0; i < 4000 && !Life->IsRunning() && FPlatformTime::Seconds() - Wall0 < 60.0; ++i)
	{
		TickWorld(0.05f);
		FPlatformProcess::Sleep(0.005f);
	}
	if (!Life->IsRunning())
	{
		UE_LOG(LogASTRA, Error, TEXT("[Life] the life did not start (no plan? data/ship/aquila_plan.json)"));
		return 1;
	}
	Life->SetShipHour(StartHour);
	FAstraLifeSim& Sim = Life->Sim();
	const FAstraLifeMap& Map = Sim.GetMap();
	const int32 N = Sim.NumPeople();
	const int32 NW = Map.Watches.Num();
	UE_LOG(LogASTRA, Display, TEXT("[Life] %d people, %d rooms, %d places; %d ship s per s; day starts at %.1f; scenario %s, %.1f ship hours, step %.2f s"), N, Map.Comps.Num(), Map.Places.Num(),
	       (int32)Life->GetTimeScale(), StartHour, *Scenario, Hours, Step);

	// ======================================================================================================== the set-up
	{
		int32 NoHome = 0, NoDuty = 0, NoBattle = 0;
		TArray<int32> PerWatch;
		PerWatch.Init(0, NW);
		TMap<FString, TArray<int32>> DeptWatch;
		for (int32 i = 0; i < N; ++i)
		{
			const FAstraLifePerson& P = Sim.Person(i);
			NoHome += P.Home == INDEX_NONE ? 1 : 0;
			NoDuty += P.Duty == INDEX_NONE ? 1 : 0;
			NoBattle += P.Battle == INDEX_NONE ? 1 : 0;
			++PerWatch[P.Watch];
			TArray<int32>& D = DeptWatch.FindOrAdd(P.Dept->Name);
			D.SetNumZeroed(NW);
			++D[P.Watch];
		}
		Check(TEXT("everyone has a place"), NoHome + NoDuty + NoBattle == 0, FString::Printf(TEXT("no home %d, no post %d, no battle station %d"), NoHome, NoDuty, NoBattle));
		int32 MaxSkew = 0;
		for (const auto& KV : DeptWatch)
		{
			MaxSkew = FMath::Max(MaxSkew, FMath::Max(KV.Value) - FMath::Min(KV.Value));
		}
		FString Split;
		for (int32 w = 0; w < NW; ++w) { Split += FString::Printf(TEXT("%s%s %d"), w ? TEXT(", ") : TEXT(""), *Map.Watches[w].Name, PerWatch[w]); }
		Check(TEXT("watches are balanced"), MaxSkew <= 1 && FMath::Max(PerWatch) - FMath::Min(PerWatch) <= 3, FString::Printf(TEXT("%s; the most a department is uneven: %d"), *Split, MaxSkew));
		// every walk the day needs can be walked: home to post, post to battle station, post to the Mess and to the Medbay
		int32 Tried = 0, Failed = 0;
		TArray<FVector> R;
		const FVector MedHub = Map.CompByName.Contains(FName(TEXT("medbay"))) ? Map.Places[Map.Comps[Map.CompByName[FName(TEXT("medbay"))]].Hub].Pos : FVector::ZeroVector;
		const FVector MessHub = Map.CompByName.Contains(FName(TEXT("mess"))) ? Map.Places[Map.Comps[Map.CompByName[FName(TEXT("mess"))]].Hub].Pos : FVector::ZeroVector;
		FString FirstFail;
		for (int32 i = 0; i < N; ++i)
		{
			const FAstraLifePerson& P = Sim.Person(i);
			if (P.Home == INDEX_NONE || P.Duty == INDEX_NONE || P.Battle == INDEX_NONE)
			{
				continue;
			}
			const FVector Hm = Map.Places[Map.Comps[P.Home].Hub].Pos, Du = Map.Places[P.Duty].Pos, Ba = Map.Places[P.Battle].Pos;
			const FVector Pairs[4][2] = {{Hm, Du}, {Du, Ba}, {Du, MessHub}, {Ba, MedHub}};
			for (const auto& Pr : Pairs)
			{
				++Tried;
				if (!Plan->FindRoute(Pr[0], Pr[1], R))
				{
					++Failed;
					if (FirstFail.IsEmpty())
					{
						FirstFail = FString::Printf(TEXT("person %d (%s): (%.0f,%.0f,%.0f) -> (%.0f,%.0f,%.0f)"), i, *P.Dept->Name, Pr[0].X / 100, Pr[0].Y / 100, Pr[0].Z / 100, Pr[1].X / 100, Pr[1].Y / 100, Pr[1].Z / 100);
					}
				}
			}
		}
		Check(TEXT("everyone can get everywhere"), Failed == 0, FString::Printf(TEXT("%d routes tried, %d without a way%s"), Tried, Failed, Failed ? *(TEXT("; first: ") + FirstFail) : TEXT("")));
	}

	// ======================================================================================================== the Captain's walk (bodies, headless)
	if (Scenario == TEXT("walk"))
	{
		// A Captain of the test's own walks the ship (Deck 4: the Mess, the Concourse, the Berthing; lifts to the Medbay, Main Engineering,
		// the Flight Deck) while the ship lives. Without a renderer the bodies have no meshes, but everything else of them is real: the
		// pool, the people they carry, their walks, their doors. Checked: the pool's cap, that bodies appear where the people are, that
		// nobody is made in front of the Captain's eyes except where a lift opens, that a body is where its person is.
		struct FLeg { FString Name; FVector From, To; bool bJump; };
		const FLeg Legs[] = {
			{TEXT("the Mess Hall"), FVector(-12460, 0, -4600), FVector(-14000, 0, -4600), true},
			{TEXT("across the Concourse"), FVector(-14000, 0, -4600), FVector(-11910, 900, -4600), false},
			{TEXT("aft to the Berthing"), FVector(-11910, 900, -4600), FVector(-17200, 0, -4600), false},
			{TEXT("the Medbay"), FVector(-23460, 0, -5400), FVector(-24500, 0, -5400), true},
			{TEXT("Main Engineering"), FVector(-33260, 0, -5800), FVector(-35000, 0, -5800), true},
			{TEXT("the Flight Deck"), FVector(6250, 0, -7280), FVector(12000, 0, -7280), true}};
		struct FSpawnLog { int32 Person; float DistM; bool bLift; bool bFront; bool bSettle; bool bDoor; };
		TArray<FSpawnLog> Spawns;
		TArray<bool> HadBody;
		HadBody.Init(false, N);
		TArray<bool> WasInShaft;
		WasInShaft.Init(false, N);
		int32 MaxBodies = 0, TotalSpawns = 0, TotalDrops = 0, DoorMax = 0;
		double TickRateSum = 0.0;
		int32 TickBodies = 0;
		float SinceJump = 0.f;
		float WalkClock = 0.f;
		TArray<float> BornAt;
		BornAt.Init(0.f, N);
		TArray<FVector> PrevPos;
		PrevPos.Init(FVector::ZeroVector, N);
		float WorstSpread = 0.f;
		double ThoughtSec = 0.0;
		int64 Thoughts = 0;
		int32 Looked = 0, Wrong = 0;
		int32 HeardRows = 0, BadRows = 0;
		FString BadWhy;
		FVector LastLook = FVector::ForwardVector;
		TMap<FString, int32> WrongWhy;
		const bool bAssets = LoadObject<USkeletalMesh>(nullptr, TEXT("/Game/Characters/Mannequins/Meshes/SKM_Manny_Simple.SKM_Manny_Simple")) != nullptr;
		double BodiesMsSum = 0.0, BodiesMsMax = 0.0;
		int64 BodyTicks = 0;
		const float StepW = FMath::Min(Step, 0.0333f);
		FVector Feet = Legs[0].From;
		// The game begins on the bridge, where nobody walks: the pool is warmed there, a body at a time, before the Captain takes a lift.
		for (float Warm = 0.f; Warm < 7.f; Warm += StepW)
		{
			Life->SetTestCaptain(FVector(8000.f, 0.f, 0.f), FVector(8000.f, 0.f, 160.f), FVector::ForwardVector);
			TickWorld(StepW);
		}
		UE_LOG(LogASTRA, Display, TEXT("[Life] walk: %d bodies in the pool before anyone walks"), Life->PoolView().Num());
		for (const FLeg& Leg : Legs)
		{
			TArray<FVector> Route;
			if (Leg.bJump)
			{
				Feet = Leg.From;                                 // a lift: the screen fades, the Captain is somewhere else
				SinceJump = 0.f;
			}
			if (!Plan->FindRoute(Feet, Leg.To, Route) || Route.Num() < 2)
			{
				Route = {Feet, Leg.To};
			}
			int32 Seg = 0;
			float F = 0.f;
			float Dwell = 40.f;                                  // and then a look around before the next leg
			int32 BodiesHere = 0, MaxHere = 0, SpawnsHere = 0;
			float Elapsed = 0.f;
			while (Elapsed < 240.f && (Seg + 1 < Route.Num() || Dwell > 0.f))
			{
				if (Seg + 1 < Route.Num())
				{
					const float Len = (float)FVector::Dist(Route[Seg], Route[Seg + 1]);
					F += Len > 1.f ? (135.f * StepW) / Len : 1.f;
					if (F >= 1.f) { ++Seg; F = 0.f; }
					Feet = Seg + 1 < Route.Num() ? FMath::Lerp(Route[Seg], Route[Seg + 1], F) : Route.Last();
				}
				else
				{
					Dwell -= StepW;
				}
				const FVector Look = Seg + 1 < Route.Num() ? (Route[Seg + 1] - Route[Seg]).GetSafeNormal() : FVector::ForwardVector;
				LastLook = Look;
				Life->SetTestCaptain(Feet, Feet + FVector(0, 0, 160), Look);
				TickWorld(StepW);
				// (a headless world does not tick its actors: the bodies think when the test says; what a thought costs is measured here)
				const double TT0 = FPlatformTime::Seconds();
				int64 ThoughtsBefore = 0, ThoughtsAfter = 0;
				for (int32 i = 0; i < N; ++i)
				{
					if (AAstraLifeBody* Bd = Life->BodyOfPerson(i)) { ThoughtsBefore += Bd->TicksRun(); Bd->TickForTest(StepW); ThoughtsAfter += Bd->TicksRun(); }
				}
				ThoughtSec += FPlatformTime::Seconds() - TT0;
				Thoughts += ThoughtsAfter - ThoughtsBefore;
				Elapsed += StepW;
				SinceJump += StepW;
				WalkClock += StepW;
				int32 NowBodies = 0;
				for (int32 i = 0; i < N; ++i)
				{
					const AAstraLifeBody* B = Life->BodyOfPerson(i);
					const FAstraLifePerson& P = Sim.Person(i);
					const bool bHas = B != nullptr;
					if (bHas)
					{
						++NowBodies;
						const float Spread = (float)FVector::Dist2D(B->GetActorLocation(), P.Pos);
						// a body stands where its person does (a step to the right of the route, a step round somebody)
						if (B->IsWalking() && P.Phase == FAstraLifePerson::EPhase::Walking && !P.Route.InShaft()) { WorstSpread = FMath::Max(WorstSpread, Spread); }
					}
					if (bHas && !HadBody[i])
					{
						++TotalSpawns;
						++SpawnsHere;
						const FVector2D To = FVector2D(P.Pos.X - Feet.X, P.Pos.Y - Feet.Y).GetSafeNormal();
						const bool bFront = FVector2D::DotProduct(To, FVector2D(Look.X, Look.Y).GetSafeNormal()) > 0.5f;    // within 60 degrees of where the Captain looks
						// out of a room the ship has not built (nothing to see there): they step through its door into the place that is built
						const int32 Before = Map.CompartmentAt(PrevPos[i] + FVector(0, 0, 30));
						const bool bDoor = Before != INDEX_NONE && Map.Comps[Before].Status == EAstraRoomStatus::Planned;
						BornAt[i] = WalkClock;
						Spawns.Add({i, (float)FVector::Dist2D(P.Pos, Feet) / 100.f, WasInShaft[i], bFront, SinceJump < 3.f, bDoor});
					}
					else if (!bHas && HadBody[i])
					{
						++TotalDrops;
					}
					HadBody[i] = bHas;
					PrevPos[i] = P.Pos;
					WasInShaft[i] = P.Phase == FAstraLifePerson::EPhase::Walking && P.Route.InShaft();
				}
				MaxBodies = FMath::Max(MaxBodies, NowBodies);
				MaxHere = FMath::Max(MaxHere, NowBodies);
				BodiesHere = NowBodies;
				int32 DoorWalkers = 0;
				for (const TWeakObjectPtr<const AActor>& W : AstraDoors::Walkers()) { DoorWalkers += W.IsValid() ? 1 : 0; }
				DoorMax = FMath::Max(DoorMax, DoorWalkers);
				BodiesMsSum += Life->GetCost().BodiesMs;
				BodiesMsMax = FMath::Max(BodiesMsMax, Life->GetCost().BodiesMs);
				++BodyTicks;
			}
			// what the minds are told of the people within earshot (the context that goes with the Captain's words): every row has what
			// mind/astra_mind/npc.py reads
			for (const TSharedPtr<FJsonValue>& V : Life->ListenersJson(Feet + FVector(0, 0, 160), LastLook, 6))
			{
				const TSharedPtr<FJsonObject>& O = V->AsObject();
				++HeardRows;
				if (HeardRows == 1)
				{
					FString Sample;
					TSharedRef<TJsonWriter<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>> Writer = TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&Sample);
					FJsonSerializer::Serialize(O.ToSharedRef(), Writer);
					UE_LOG(LogASTRA, Display, TEXT("[Life] a row of context.people, as the mind gets it: %s"), *Sample);
				}
				FString Missing;
				for (const TCHAR* K : {TEXT("id"), TEXT("name"), TEXT("rank"), TEXT("gender"), TEXT("dept"), TEXT("job"), TEXT("watch"), TEXT("doing"), TEXT("place"), TEXT("dist_m"), TEXT("facing"), TEXT("memory"), TEXT("friends")})
				{
					if (!O->HasField(K)) { Missing += FString(K) + TEXT(" "); }
				}
				FString Id;
				O->TryGetStringField(TEXT("id"), Id);
				FString Name;
				O->TryGetStringField(TEXT("name"), Name);
				if (!Id.StartsWith(TEXT("npc")) || Name.IsEmpty()) { Missing += TEXT("(id or name) "); }
				if (!Missing.IsEmpty()) { ++BadRows; BadWhy = Missing; }
			}
			// what the bodies are made of (needs the mannequins' content: without it the check is skipped)
			for (int32 i = 0; i < N; ++i)
			{
				if (const AAstraLifeBody* B = Life->BodyOfPerson(i))
				{
					FString Why;
					++Looked;
					if (!B->LooksRight(Why)) { ++Wrong; ++WrongWhy.FindOrAdd(Why); }
				}
			}
			UE_LOG(LogASTRA, Display, TEXT("[Life] walk %s: %d bodies at the end (most %d), %d made on the way"), *Leg.Name, BodiesHere, MaxHere, SpawnsHere);
		}
		for (int32 i = 0; i < N; ++i)
		{
			if (const AAstraLifeBody* B = Life->BodyOfPerson(i))
			{
				const float Lived = WalkClock - BornAt[i];
				if (Lived > 20.f) { TickRateSum += B->TicksRun() / Lived; ++TickBodies; }
			}
		}
		Life->ClearTestCaptain();
		const int32 Cap = Map.Vis.MaxBodies + 4;
		Check(TEXT("the pool keeps its cap"), MaxBodies <= Cap && MaxBodies > 0, FString::Printf(TEXT("at most %d bodies at once (the cap is %d plus a few still in view)"), MaxBodies, Map.Vis.MaxBodies));
		int32 Pops = 0, Lifts = 0, Settling = 0, Doors = 0;
		float Nearest = 1.0e9f;
		for (const FSpawnLog& S : Spawns)
		{
			if (S.bLift) { ++Lifts; continue; }
			if (S.bSettle) { ++Settling; continue; }                    // the first moments after a jump: the picture is still fading in
			if (S.bDoor) { ++Doors; continue; }
			if (S.DistM < 40.f && S.bFront) { ++Pops; Nearest = FMath::Min(Nearest, S.DistM); }
		}
		Check(TEXT("nobody appears in front of the Captain"), Pops <= 5,
		      FString::Printf(TEXT("%d bodies made, %d released, %d at a jump, %d out of a lift, %d out of a room not built; %d made within 40 m and in front of the Captain (nearest %.0f m)"),
		                      TotalSpawns, TotalDrops, Settling, Lifts, Doors, Pops, Nearest < 1.0e8f ? Nearest : 0.f));
		Check(TEXT("the bodies think"), TickBodies > 0 && TickRateSum / TickBodies > 1.5, FString::Printf(TEXT("%.1f thoughts a second on average for the %d bodies alive for more than 20 s (nobody sees them here: every tenth or half second)"), TickBodies ? TickRateSum / TickBodies : 0.0, TickBodies));
		{
			// what one body's thought costs (its walk, its pose, its place), and so what a full pool seen at every frame would cost
			const double UsPerThought = Thoughts ? ThoughtSec * 1.0e6 / (double)Thoughts : 0.0;
			Check(TEXT("a body's thought is cheap"), Thoughts > 0 && UsPerThought * Map.Vis.MaxBodies < 500.0,
			      FString::Printf(TEXT("%.1f microseconds a thought (%lld thoughts): all %d bodies seen at every frame would cost %.2f ms"), UsPerThought, Thoughts, Map.Vis.MaxBodies, UsPerThought * Map.Vis.MaxBodies / 1000.0));
		}
		Check(TEXT("the minds are told who is near"), HeardRows > 0 && BadRows == 0,
		      FString::Printf(TEXT("%d rows of people within earshot over the legs, %d without what the mind reads%s"), HeardRows, BadRows, BadWhy.IsEmpty() ? TEXT("") : *(FString(TEXT(" (missing: ")) + BadWhy + TEXT(")"))));
		if (bAssets)
		{
			FString Reasons;
			for (const TPair<FString, int32>& KV : WrongWhy) { Reasons += FString::Printf(TEXT(" [%d %s]"), KV.Value, *KV.Key); }
			Check(TEXT("the bodies are made right"), Looked > 0 && Wrong == 0, FString::Printf(TEXT("%d bodies looked at the end of the legs, %d wrong%s"), Looked, Wrong, *Reasons));
		}
		else
		{
			UE_LOG(LogASTRA, Display, TEXT("[Life] SKIP the bodies are made right: the mannequins' content (Content/Characters) is not here"));
		}
		Check(TEXT("a body is where its person is"), WorstSpread < 200.f, FString::Printf(TEXT("the widest a walking body strayed from the route: %.0f cm"), WorstSpread));
		Check(TEXT("the doors know the walkers"), DoorMax <= Cap, FString::Printf(TEXT("%d walkers on the doors' list at most"), DoorMax));
		Check(TEXT("the bodies' manager is cheap"), BodiesMsSum / FMath::Max<int64>(1, BodyTicks) < 0.3,
		      FString::Printf(TEXT("%.3f ms a frame on average (it runs four times a second, %.2f ms at worst)"), BodiesMsSum / FMath::Max<int64>(1, BodyTicks), BodiesMsMax));
		bool bAllW = true;
		int32 Failed = 0;
		for (const FCheck& C : Checks) { bAllW &= C.bPass; Failed += C.bPass ? 0 : 1; }
		UE_LOG(LogASTRA, Display, TEXT("[Life] walk: %d checks, %d failed"), Checks.Num(), Failed);
		UE_LOG(LogASTRA, Display, TEXT("[Life] VERDICT: %s"), bAllW ? TEXT("PASS") : TEXT("FAIL"));
		Life->ReleaseAllBodies();
		GEngine->DestroyWorldContext(World);
		World->DestroyWorld(false);
		return bAllW ? 0 : 1;
	}

	// ======================================================================================================== the day
	struct FEvent { double Hour; FString What; bool bDone = false; };
	TArray<FEvent> Events;
	if (bDay)
	{
		Events = {{2.5, TEXT("red")}, {3.6, TEXT("green")}, {5.0, TEXT("hit1")}, {8.0, TEXT("admit")}, {11.0, TEXT("hit2")}, {14.0, TEXT("care")}, {17.0, TEXT("hit3")}, {19.0, TEXT("synth")}};
	}
	const double Sec0 = Sim.ShipSeconds();
	const double SecEnd = Sec0 + Hours * 3600.0;
	TArray<double> WaitSince, WalkSince;
	WaitSince.Init(-1.0, N);
	WalkSince.Init(-1.0, N);
	double MaxWait = 0.0, MaxWalk = 0.0;
	int32 LongWaits = 0;
	TArray<TSet<int32>> MealEpisodes;
	MealEpisodes.SetNum(N);
	TArray<uint8> MealBlocks;
	MealBlocks.Init(0, N);
	int32 MessPeak = 0;
	double MessSum = 0.0;
	int32 MessSamples = 0;
	int64 DinerSamples = 0, StandingSamples = 0;       // diners seen (one per person per sample) and those of them who ate standing in a hall
	struct FSample { float Hour; int32 Acts[(int32)EAstraLifeAct::Count]; int32 Walking; int32 Mess; int32 Diners, Standing, Benches; int32 NearMess, NearMed, NearEng, NearHangar, NearCorridor; };
	TArray<FSample> Samples;
	const double SampleEvery = 300.0;          // ship seconds
	double NextSample = Sec0;
	TArray<double> TickMs;
	TickMs.Reserve((int32)(Hours * 3600.0 / Life->GetTimeScale() / Step) + 16);
	const FName MessName(TEXT("mess"));
	const int32 MessComp = Map.CompByName.FindRef(MessName, INDEX_NONE);
	auto CompOfPerson = [&](int32 i) { return Sim.CompOf(i); };
	auto NearCount = [&](const FVector& At, float Radius, float Band)
	{
		int32 C = 0;
		for (int32 i = 0; i < N; ++i)
		{
			const FAstraLifePerson& P = Sim.Person(i);
			C += (P.Status == 0 && FMath::Abs(P.Pos.Z - At.Z) < Band && FVector::Dist2D(P.Pos, At) < Radius && !(P.Phase == FAstraLifePerson::EPhase::Settled && P.Place != INDEX_NONE && Map.Places[P.Place].External != NAME_None)) ? 1 : 0;
		}
		return C;
	};
	// the watch checks: once, a while after each watch begins, and once deep into each one's sleep
	struct FWatchCheck { int32 Watch; double At; bool bDone = false; bool bSleep = false; };
	TArray<FWatchCheck> WatchChecks;
	for (int32 w = 0; w < NW; ++w)
	{
		for (double T = FMath::CeilToDouble((Sec0 / 3600.0 - Map.Watches[w].Start) / 24.0) * 24.0 + Map.Watches[w].Start; T < SecEnd / 3600.0; T += 24.0)
		{
			WatchChecks.Add({w, (T + 1.8) * 3600.0});
			WatchChecks.Add({w, (T + 16.0) * 3600.0, false, true});
		}
	}
	// the emergencies the day puts to the ship
	struct FIncidentTrack { int32 Id; double Seen; double Dispatched = -1.0; double Arrived = -1.0; double Closed = -1.0; bool bFormed = false; int32 Members = 0; float EtaGuess = 0.f; FString Kind; };
	TMap<int32, FIncidentTrack> Incidents;
	TSet<int32> DispatchPending;
	TMap<int32, double> DispatchAt;
	TArray<int32> Wounded;
	double WoundedAt = -1.0, CareAt = -1.0;
	TArray<int32> Healed;
	double GqAt = -1.0;
	float GqFraction = -1.f;
	int32 GqFit = 0;
	double GameT = 0.0;
	int32 CaseIds = 0;

	// three incidents of the test's own, in the ship's own terms, but with the time a party really needs (the ship's "on scene in" is a formula)
	struct FSynth { FAstraDamage D; double Eta = 0.0; double Arrived = -1.0; FVector Site = FVector::ZeroVector; };
	TArray<FSynth> Synths;
	double SynthEnd = -1.0;
	auto OnEvent = [&](FEvent& E)
	{
		E.bDone = true;
		if (E.What == TEXT("red") || E.What == TEXT("green"))
		{
			FString D;
			Ship->ApplyCommand(TEXT("set_alert"), Args({{TEXT("level"), E.What}}), D);
			if (E.What == TEXT("red")) { GqAt = GameT + 300.0; }
		}
		else if (E.What.StartsWith(TEXT("hit")))
		{
			const int32 Hits = E.What == TEXT("hit2") ? 2 : 1;
			for (int32 k = 0; k < Hits; ++k) { Ship->OnHullHit(40.f, 0.f, FMath::VRand()); }
		}
		else if (E.What == TEXT("synth"))
		{
			Life->SetShipFeed(false);
			const int32 Decks[3] = {4, 9, 11};
			const TCHAR Secs[3] = {TEXT('B'), TEXT('F'), TEXT('A')};
			for (int32 k = 0; k < 3; ++k)
			{
				FSynth S;
				S.D.Id = 9001 + k;
				S.D.Deck = Decks[k];
				S.D.Section = Secs[k];
				S.D.Kind = k == 1 ? TEXT("hull breach") : TEXT("fire");
				S.D.Team = k;
				S.Eta = Life->RepairEtaSeconds(S.D.Deck, S.D.Section, S.D.Id);
				S.D.Travel = (float)S.Eta;
				S.D.Work = 400.f;                                // long: what is measured is when the party gets there, not the ship's repair
				Synths.Add(S);
				UE_LOG(LogASTRA, Display, TEXT("[Life] %8.1f s  test incident %d: %s at deck %d section %c, the party's own estimate %.0f s"), GameT, S.D.Id, *S.D.Kind, S.D.Deck, S.D.Section, S.Eta);
			}
			SynthEnd = GameT + 600.0;
		}
		else if (E.What == TEXT("admit"))
		{
			Ship->TestMedbay(TEXT("admit"), 5);
			WoundedAt = GameT + 600.0;
			Wounded.Reset();
			for (int32 i = 0; i < N; ++i)
			{
				if (Ship->GetRoster().Get()[Sim.Person(i).Roster].Status == 1) { Wounded.Add(i); }
			}
		}
		else if (E.What == TEXT("care"))
		{
			TSet<int32> Before;
			for (int32 i = 0; i < N; ++i) { if (Ship->GetRoster().Get()[Sim.Person(i).Roster].Status == 1) { Before.Add(i); } }
			Ship->TestMedbay(TEXT("care"), 14);
			for (const int32 i : Before) { if (Ship->GetRoster().Get()[Sim.Person(i).Roster].Status == 0) { Healed.Add(i); } }
			CareAt = GameT + 40.0;
		}
	};

	const double RunWall0 = FPlatformTime::Seconds();
	int64 Tick = 0;
	while (Sim.ShipSeconds() < SecEnd)
	{
		for (FEvent& E : Events)
		{
			if (!E.bDone && Sim.ShipSeconds() >= Sec0 + E.Hour * 3600.0)
			{
				OnEvent(E);
			}
		}
		TickWorld(Step);
		GameT += Step;
		++Tick;
		TickMs.Add(Life->GetCost().SimMs);
		// new incidents are dispatched a few seconds after they are reported (what ops does)
		for (const FAstraDamage& D : Ship->GetDamage())
		{
			if (!Incidents.Contains(D.Id))
			{
				FIncidentTrack T;
				T.Id = D.Id;
				T.Seen = GameT;
				T.Kind = D.Kind;
				Incidents.Add(D.Id, T);
				DispatchAt.Add(D.Id, GameT + 6.0);
				UE_LOG(LogASTRA, Display, TEXT("[Life] %8.1f s  incident %d: %s at %s"), GameT, D.Id, *D.Kind, *D.Where());
			}
		}
		for (auto It = DispatchAt.CreateIterator(); It; ++It)
		{
			if (GameT >= It.Value())
			{
				const FAstraDamage* D = Ship->GetDamage().FindByPredicate([Id = It.Key()](const FAstraDamage& X) { return X.Id == Id; });
				if (D)
				{
					FString Detail;
					const bool bOk = Ship->ApplyCommand(TEXT("dispatch_damage_control"), Args({{TEXT("section"), FString(1, &D->Section)}}, {{TEXT("deck"), (double)D->Deck}, {TEXT("id"), (double)D->Id}}), Detail);
					if (bOk)
					{
						Incidents[It.Key()].Dispatched = GameT;
						Incidents[It.Key()].EtaGuess = D->Travel;
						UE_LOG(LogASTRA, Display, TEXT("[Life] %8.1f s  dispatched: %s"), GameT, *Detail);
					}
				}
				It.RemoveCurrent();
			}
		}
		for (const FAstraLifeParty& Pt : Sim.Parties())
		{
			if (FIncidentTrack* T = Incidents.Find(Pt.Incident))
			{
				T->bFormed = true;
				T->Members = Pt.Members.Num();
				if (T->Arrived < 0.0 && Pt.State == FAstraLifeParty::EState::Working)
				{
					T->Arrived = GameT;
					UE_LOG(LogASTRA, Display, TEXT("[Life] %8.1f s  the party of %d is at the %s (%s): %.0f s after the dispatch"), GameT, Pt.Members.Num(), *Pt.Kind, *Map.Describe(Pt.SiteComp), GameT - T->Dispatched);
				}
			}
		}
		for (auto& KV : Incidents)
		{
			if (KV.Value.Closed < 0.0 && KV.Value.bFormed && !Sim.Parties().ContainsByPredicate([Id = KV.Key](const FAstraLifeParty& P) { return P.Incident == Id; }))
			{
				KV.Value.Closed = GameT;
			}
		}
		if (Synths.Num())
		{
			TArray<FAstraDamage> List;
			for (FSynth& S : Synths)
			{
				if (S.D.Progress >= 1.f) { continue; }
				if (S.D.Travel > 0.f) { S.D.Travel -= Step; }
				else { S.D.Progress += Step / S.D.Work; }
				if (S.D.Progress < 1.f) { List.Add(S.D); }
			}
			if ((Tick % 2) == 0)
			{
				Sim.SyncDamage(List);
			}
			for (FSynth& S : Synths)
			{
				if (S.Arrived < 0.0)
				{
					for (const FAstraLifeParty& Pt : Sim.Parties())
					{
						if (Pt.Incident == S.D.Id && Pt.State == FAstraLifeParty::EState::Working) { S.Arrived = GameT; }
					}
				}
			}
			bool bAllThere = true;
			for (const FSynth& S : Synths) { bAllThere &= S.Arrived >= 0.0; }
			if (GameT >= SynthEnd || List.Num() == 0 || bAllThere)
			{
				Sim.SyncDamage(TArray<FAstraDamage>());
				Life->SetShipFeed(true);
				for (const FSynth& S : Synths)
				{
					const double Since = S.Arrived < 0.0 ? -1.0 : S.Arrived - (SynthEnd - 600.0);
					Check(*FString::Printf(TEXT("party reaches test incident %d"), S.D.Id), S.Arrived >= 0.0 && Since <= 1.3 * S.Eta + 15.0,
					      FString::Printf(TEXT("%s at deck %d section %c: estimated %.0f s, on scene after %.0f s"), *S.D.Kind, S.D.Deck, S.D.Section, S.Eta, Since));
				}
				Synths.Reset();
			}
		}
		// the watching of everyone, every tick: nobody waits for ever, nobody walks for ever
		for (int32 i = 0; i < N; ++i)
		{
			const FAstraLifePerson& P = Sim.Person(i);
			const bool bWait = P.Phase == FAstraLifePerson::EPhase::WaitRoute, bWalk = P.Phase == FAstraLifePerson::EPhase::Walking;
			if (bWait)
			{
				if (WaitSince[i] < 0.0) { WaitSince[i] = GameT; }
				const double W = GameT - WaitSince[i];
				if (W > MaxWait) { MaxWait = W; }
			}
			else if (WaitSince[i] >= 0.0)
			{
				WaitSince[i] = -1.0;
			}
			if (bWalk)
			{
				if (WalkSince[i] < 0.0) { WalkSince[i] = GameT; }
				MaxWalk = FMath::Max(MaxWalk, GameT - WalkSince[i]);
			}
			else if (WalkSince[i] >= 0.0)
			{
				WalkSince[i] = -1.0;
			}
		}
		if (GqAt > 0.0 && GameT >= GqAt)
		{
			int32 There = 0;
			GqFit = 0;
			for (int32 i = 0; i < N; ++i)
			{
				const FAstraLifePerson& P = Sim.Person(i);
				if (P.Status == 0 && P.Party == INDEX_NONE)
				{
					++GqFit;
					There += (P.Act == EAstraLifeAct::Battle && P.Phase == FAstraLifePerson::EPhase::Settled) ? 1 : 0;
				}
			}
			GqFraction = GqFit ? (float)There / GqFit : 0.f;
			UE_LOG(LogASTRA, Display, TEXT("[Life] %8.1f s  %d of %d at their battle stations, 5 game minutes after general quarters"), GameT, There, GqFit);
			GqAt = -1.0;
		}
		if (WoundedAt > 0.0 && GameT >= WoundedAt)
		{
			int32 In = 0, Still = 0, Gone = 0;
			FString Late;
			for (const int32 i : Wounded)
			{
				const FAstraLifePerson& P = Sim.Person(i);
				if (Ship->GetRoster().Get()[P.Roster].Status != 1)
				{
					++Gone;                                  // the doctors have already discharged (or lost) them
					continue;
				}
				++Still;
				const bool bIn = P.Act == EAstraLifeAct::Patient && P.Phase == FAstraLifePerson::EPhase::Settled;
				In += bIn ? 1 : 0;
				if (!bIn) { Late += FString::Printf(TEXT(" [person %d: %s, %s, %.0f m to go]"), i, AstraLifeActName(P.Act), P.Phase == FAstraLifePerson::EPhase::Walking ? TEXT("walking") : TEXT("waiting"), P.Route.RemainingCm() / 100.f); }
			}
			Check(TEXT("the wounded reach the Medbay"), Wounded.Num() > 0 && In == Still, FString::Printf(TEXT("%d of the %d still wounded are in the Medbay 10 game minutes after they were hurt (%d were already discharged)%s"), In, Still, Gone, *Late));
			WoundedAt = -1.0;
		}
		if (CareAt > 0.0 && GameT >= CareAt)
		{
			int32 Left = 0;
			for (const int32 i : Healed) { Left += Sim.Person(i).Act == EAstraLifeAct::Patient ? 1 : 0; }
			Check(TEXT("the healed go back to work"), Healed.Num() > 0 && Left == 0, FString::Printf(TEXT("%d discharged, %d still counted as patients 40 s later"), Healed.Num(), Left));
			CareAt = -1.0;
		}
		for (FWatchCheck& W : WatchChecks)
		{
			if (W.bDone || Sim.ShipSeconds() < W.At) { continue; }
			W.bDone = true;
			if (Sim.Alert() != 0) { continue; }
			int32 Mine = 0, Duty = 0, Others = 0, Sleep = 0, Fit = 0;
			for (int32 i = 0; i < N; ++i)
			{
				const FAstraLifePerson& P = Sim.Person(i);
				if (P.Status != 0 || P.Party != INDEX_NONE) { continue; }
				if (P.Watch == W.Watch)
				{
					++Mine;
					Duty += P.Act == EAstraLifeAct::Duty ? 1 : 0;
					Sleep += (P.Act == EAstraLifeAct::Sleep && P.Phase == FAstraLifePerson::EPhase::Settled) ? 1 : 0;
				}
				else
				{
					Others += P.Act == EAstraLifeAct::Duty ? 1 : 0;
					++Fit;
				}
			}
			if (!W.bSleep)
			{
				const float Frac = Mine ? (float)Duty / Mine : 0.f;
				Check(*FString::Printf(TEXT("watch %s takes the deck"), *Map.Watches[W.Watch].Name), Frac >= 0.78f && Others == 0,
				      FString::Printf(TEXT("ship time %s: %d of %d of the watch on duty (the rest at a meal or on the way); on duty from the other watches: %d"), *FAstraLifeSim::HourText(Sim.ShipSeconds()), Duty, Mine, Others));
			}
			else
			{
				const float Frac = Mine ? (float)Sleep / Mine : 0.f;
				Check(*FString::Printf(TEXT("watch %s sleeps"), *Map.Watches[W.Watch].Name), Frac >= 0.80f, FString::Printf(TEXT("ship time %s: %d of %d in their bunks"), *FAstraLifeSim::HourText(Sim.ShipSeconds()), Sleep, Mine));
			}
		}
		if (Sim.ShipSeconds() >= NextSample)
		{
			NextSample += SampleEvery;
			FSample S = {};
			S.Hour = Sim.Hour();
			int32 Mess = 0, Diners = 0, Standing = 0, Benches = 0;
			for (int32 i = 0; i < N; ++i)
			{
				const FAstraLifePerson& P = Sim.Person(i);
				++S.Acts[(int32)P.Act];
				S.Walking += P.Phase == FAstraLifePerson::EPhase::Walking ? 1 : 0;
				if (P.Act == EAstraLifeAct::Meal && P.Phase == FAstraLifePerson::EPhase::Settled)
				{
					MealEpisodes[i].Add(P.Episode);
					++DinerSamples;
					++Diners;
					StandingSamples += P.TargetKind == EAstraPlaceKind::Hub ? 1 : 0;
					Standing += P.TargetKind == EAstraPlaceKind::Hub ? 1 : 0;
					Benches += P.TargetKind == EAstraPlaceKind::Sit ? 1 : 0;
					if (P.Episode >= 0 || P.Episode < 0) { const int32 B = ((P.Episode % 16) + 16) % 16; MealBlocks[i] |= (uint8)(B == 1 ? 1 : B == 4 ? 2 : B == 8 ? 4 : 0); }
					if (MessComp != INDEX_NONE && P.Place != INDEX_NONE && Map.Places[P.Place].Comp == MessComp) { ++Mess; }
				}
			}
			S.Mess = Mess;
			S.Diners = Diners;
			S.Standing = Standing;
			S.Benches = Benches;
			MessPeak = FMath::Max(MessPeak, Mess);
			MessSum += Mess;
			++MessSamples;
			// how many would have bodies if the Captain stood in the Mess, the Medbay, Engineering, the Flight Deck, the forward corridors
			S.NearMess = NearCount(FVector(-14000.f, 0.f, -4600.f), 4500.f, 420.f);
			S.NearMed = NearCount(FVector(-24500.f, 0.f, -5400.f), 4500.f, 420.f);
			S.NearEng = NearCount(FVector(-35000.f, 0.f, -5800.f), 4500.f, 1500.f);
			S.NearHangar = NearCount(FVector(14000.f, 0.f, -7300.f), 9000.f, 2200.f);
			S.NearCorridor = NearCount(FVector(-9000.f, 0.f, -4600.f), 4500.f, 420.f);
			Samples.Add(S);
		}
	}
	const double RunWall = FPlatformTime::Seconds() - RunWall0;

	// ======================================================================================================== the verdicts
	if (GqFraction >= 0.f)
	{
		Check(TEXT("general quarters is answered"), GqFraction >= 0.95f, FString::Printf(TEXT("%.1f %% of %d fit people at their battle stations after 5 game minutes"), GqFraction * 100.f, GqFit));
	}
	else if (bDay)
	{
		Check(TEXT("general quarters is answered"), false, TEXT("the alarm was never measured"));
	}
	{
		// everybody eats three times a day: every one of the three meals of the day template is seen in a person's own cycle (a run of 30 hours
		// holds each of them whole at least once whatever the watch; a shorter one cuts them at its ends and only reports)
		int32 Fit = 0, Short = 0, Total = 0, Miss[3] = {0, 0, 0};
		for (int32 i = 0; i < N; ++i)
		{
			if (Sim.Person(i).Status == 2) { continue; }
			++Fit;
			Short += (Hours >= 30.f && MealBlocks[i] != 7) ? 1 : 0;
			Total += MealEpisodes[i].Num();
			for (int32 b = 0; b < 3; ++b) { Miss[b] += (MealBlocks[i] & (1 << b)) ? 0 : 1; }
		}
		Check(TEXT("everyone eats"), Short <= (bDay ? Fit * 22 / 100 : Fit / 50), FString::Printf(TEXT("%d of %d had fewer than three meals in %.0f hours (an alarm or a hit may take one; %.2f meals a person seen); missed: mid-watch %d, after the watch %d, before the watch %d"),
		      Short, Fit, Hours, Fit ? (double)Total / Fit : 0.0, Miss[0], Miss[1], Miss[2]));
	}
	int32 MessSeats = 0;
	if (MessComp != INDEX_NONE) { for (const int32 P : Map.Comps[MessComp].Places) { MessSeats += Map.Places[P].Kind == EAstraPlaceKind::Eat ? 1 : 0; } }
	{
		// the Mess seats what it seats; when it is full a diner takes a lounge table, and only when those are full too a plate standing in the hall
		const double StandPct = DinerSamples ? 100.0 * StandingSamples / DinerSamples : 0.0;
		Check(TEXT("the diners have a seat"), StandPct <= 5.0, FString::Printf(TEXT("%.1f %% of the diners ate standing in a hall at the busiest shift changes (the Mess has %d seats and at most %d people in it; average %.1f over the day)"), StandPct, MessSeats, MessPeak, MessSamples ? MessSum / MessSamples : 0.0));
	}
	Check(TEXT("nobody is stuck"), Sim.Counters.RouteFails == 0 && MaxWait < 300.0 && MaxWalk < 1500.0,
	      FString::Printf(TEXT("%d routes failed; longest wait for a route %.0f s; longest walk %.0f s (%d routes made, %.3f ms each on average, %.2f ms at most)"), Sim.Counters.RouteFails, MaxWait, MaxWalk,
	                      Sim.Counters.Routes, Sim.Counters.Routes ? Sim.Counters.RouteMs / Sim.Counters.Routes : 0.0, Sim.Counters.RouteMsMax));
	for (const FString& F : Sim.FailLog())
	{
		UE_LOG(LogASTRA, Display, TEXT("[Life]    no way: %s"), *F);
	}
	for (auto& KV : Incidents)
	{
		const FIncidentTrack& T = KV.Value;
		if (T.Dispatched < 0.0)
		{
			continue;
		}
		const double Took = T.Arrived < 0.0 ? -1.0 : T.Arrived - T.Dispatched;
		Check(*FString::Printf(TEXT("party sent to incident %d"), T.Id), T.bFormed && T.Members >= Map.Teams.Min && T.Closed >= 0.0,
		      FString::Printf(TEXT("%s: %d people sent%s; the ship had it done in %.0f s; the party released %s"), *T.Kind, T.Members,
		                      Took >= 0.0 ? *FString::Printf(TEXT(", on scene %.0f s after the dispatch"), Took) : TEXT(", not yet there when it was done (the ship's own 'on scene in' is a formula)"),
		                      T.Closed - T.Dispatched, T.Closed >= 0.0 ? TEXT("when it was done") : TEXT("NEVER")));
	}
	int32 Stuck = 0;
	for (int32 i = 0; i < N; ++i) { Stuck += Sim.Person(i).Party != INDEX_NONE && Sim.Parties().Num() == 0 ? 1 : 0; }
	Check(TEXT("no one left in a party"), Stuck == 0, FString::Printf(TEXT("%d people still tied to a party that is gone"), Stuck));
	TArray<double> Sorted = TickMs;
	double Sum = 0.0;
	for (const double M : TickMs) { Sum += M; }
	const double Avg = TickMs.Num() ? Sum / TickMs.Num() : 0.0, P99 = Percentile(Sorted, 0.99), P999 = Percentile(Sorted, 0.999), Mx = Percentile(Sorted, 1.0);
	Check(TEXT("the whole ship costs < 0.3 ms"), Avg < 0.3, FString::Printf(TEXT("%d people, %lld ticks: average %.4f ms, p99 %.3f, p99.9 %.3f, worst %.3f ms (the routes included)"), N, (int64)TickMs.Num(), Avg, P99, P999, Mx));

	// ---- the same seed, the same day (a bare simulation with straight-line routes: nothing else in the room)
	{
		TSharedRef<FAstraLifeMap> M = MakeShared<FAstraLifeMap>();
		FString Err;
		FAstraCrewRoster Roster;
		Roster.Generate();
		const bool bLoaded = M->Load(Err);
		uint32 A = 0, B = 0;
		if (bLoaded)
		{
			FAstraLifeSim S1, S2;
			S1.Init(M, Roster, 2491, 5.f);
			S2.Init(M, Roster, 2491, 5.f);
			for (int32 t = 0; t < 4800; ++t)                   // six ship hours
			{
				S1.Tick(0.25f, 12.f, 0.001, FVector::ZeroVector);
				S2.Tick(0.25f, 12.f, 0.001, FVector::ZeroVector);
			}
			A = StateHash(S1);
			B = StateHash(S2);
		}
		Check(TEXT("same seed, same day"), bLoaded && A == B, FString::Printf(TEXT("state hashes %08x and %08x after six ship hours"), A, B));
	}

	bool bAll = true;
	int32 NumFailed = 0;
	for (const FCheck& C : Checks) { bAll &= C.bPass; NumFailed += C.bPass ? 0 : 1; }
	UE_LOG(LogASTRA, Display, TEXT("[Life] %.0f ship hours (%lld ticks) in %.1f s; %d checks, %d failed"), Hours, Tick, RunWall, Checks.Num(), NumFailed);
	UE_LOG(LogASTRA, Display, TEXT("[Life] VERDICT: %s"), bAll ? TEXT("PASS") : TEXT("FAIL"));

	// the record
	TSharedRef<FJsonObject> Root = MakeShared<FJsonObject>();
	TSharedRef<FJsonObject> Sum2 = MakeShared<FJsonObject>();
	Sum2->SetStringField(TEXT("verdict"), bAll ? TEXT("PASS") : TEXT("FAIL"));
	Sum2->SetNumberField(TEXT("people"), N);
	Sum2->SetNumberField(TEXT("ship_hours"), Hours);
	Sum2->SetNumberField(TEXT("wall_s"), RunWall);
	Sum2->SetNumberField(TEXT("tick_ms_avg"), Avg);
	Sum2->SetNumberField(TEXT("tick_ms_p99"), P99);
	Sum2->SetNumberField(TEXT("tick_ms_max"), Mx);
	Sum2->SetNumberField(TEXT("routes"), Sim.Counters.Routes);
	Sum2->SetNumberField(TEXT("route_ms_avg"), Sim.Counters.Routes ? Sim.Counters.RouteMs / Sim.Counters.Routes : 0.0);
	Sum2->SetNumberField(TEXT("route_ms_max"), Sim.Counters.RouteMsMax);
	Sum2->SetNumberField(TEXT("mess_peak"), MessPeak);
	TArray<TSharedPtr<FJsonValue>> Cs;
	for (const FCheck& C : Checks)
	{
		TSharedRef<FJsonObject> O = MakeShared<FJsonObject>();
		O->SetStringField(TEXT("name"), C.Name);
		O->SetBoolField(TEXT("pass"), C.bPass);
		O->SetStringField(TEXT("detail"), C.Detail);
		Cs.Add(MakeShared<FJsonValueObject>(O));
	}
	Sum2->SetArrayField(TEXT("checks"), Cs);
	Root->SetObjectField(TEXT("summary"), Sum2);
	TArray<TSharedPtr<FJsonValue>> Ss;
	for (const FSample& S : Samples)
	{
		TSharedRef<FJsonObject> O = MakeShared<FJsonObject>();
		O->SetNumberField(TEXT("hour"), FMath::RoundToInt(S.Hour * 100.f) / 100.0);
		TSharedRef<FJsonObject> A = MakeShared<FJsonObject>();
		for (int32 a = 0; a < (int32)EAstraLifeAct::Count; ++a) { A->SetNumberField(AstraLifeActName((EAstraLifeAct)a), S.Acts[a]); }
		O->SetObjectField(TEXT("acts"), A);
		O->SetNumberField(TEXT("walking"), S.Walking);
		O->SetNumberField(TEXT("mess"), S.Mess);
		O->SetNumberField(TEXT("diners"), S.Diners);
		O->SetNumberField(TEXT("standing"), S.Standing);
		O->SetNumberField(TEXT("on_benches"), S.Benches);
		O->SetNumberField(TEXT("near_mess"), S.NearMess);
		O->SetNumberField(TEXT("near_medbay"), S.NearMed);
		O->SetNumberField(TEXT("near_engineering"), S.NearEng);
		O->SetNumberField(TEXT("near_hangar"), S.NearHangar);
		O->SetNumberField(TEXT("near_corridor_fwd"), S.NearCorridor);
		Ss.Add(MakeShared<FJsonValueObject>(O));
	}
	Root->SetArrayField(TEXT("samples"), Ss);
	FString Json;
	const TSharedRef<TJsonWriter<>> W = TJsonWriterFactory<>::Create(&Json);
	FJsonSerializer::Serialize(Root, W);
	IFileManager::Get().MakeDirectory(*FPaths::GetPath(Out), true);
	FFileHelper::SaveStringToFile(Json, *Out, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
	GEngine->DestroyWorldContext(World);
	World->DestroyWorld(false);
	return bAll ? 0 : 1;
}
