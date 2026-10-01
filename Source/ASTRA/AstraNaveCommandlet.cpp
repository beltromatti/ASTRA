#include "AstraNaveCommandlet.h"

#include "ASTRA.h"
#include "AstraDeckShell.h"
#include "AstraDeckStreaming.h"
#include "AstraDoor.h"
#include "AstraLampPool.h"
#include "AstraShipPlan.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Engine/Engine.h"
#include "Dom/JsonObject.h"
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshActor.h"
#include "PhysicsEngine/BodySetup.h"
#include "EngineUtils.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Engine/World.h"
#include "HAL/PlatformProcess.h"
#include "HAL/PlatformTime.h"
#include "UObject/UObjectGlobals.h"

namespace
{
	struct FCheck
	{
		FString Name;
		bool bPass = true;
	};
	TArray<FCheck> Checks;

	void Check(const TCHAR* Name, bool bPass, const FString& Detail)
	{
		Checks.Add({Name, bPass});
		UE_LOG(LogASTRA, Display, TEXT("[Nave] %s %-34s %s"), bPass ? TEXT("PASS") : TEXT("FAIL"), Name, *Detail);
	}
}

UAstraNaveCommandlet::UAstraNaveCommandlet()
{
	IsClient = false;
	IsServer = false;
	IsEditor = true;
	LogToConsole = true;
	ShowErrorCount = true;
}

namespace
{
	/** The game thread's side of bringing a deck in (a headless world: no renderer, so no scene proxies and no GPU, but real actors, real components'
	 *  registration and the physics bodies of every instance): the deck's shell and doors are built in a world as the level's own load would, from the plan's
	 *  placements and the kit's meshes; timed in the three parts that cost: loading the meshes, registering the instances, spawning the doors. */
	void LoadTest(const TArray<FString>& Decks)
	{
		UWorld* World = UWorld::CreateWorld(EWorldType::Game, false, TEXT("AstraNaveLoad"));
		FWorldContext& Ctx = GEngine->CreateNewWorldContext(EWorldType::Game);
		Ctx.SetCurrentWorld(World);
		World->InitializeActorsForPlay(FURL());
		World->BeginPlay();
		FString Text;
		TSharedPtr<FJsonObject> Root;
		if (!FFileHelper::LoadFileToString(Text, *FPaths::Combine(FPaths::ProjectDir(), TEXT("data/ship/aquila_plan.json"))) ||
		    !FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Root) || !Root.IsValid())
		{
			Check(TEXT("load: the plan"), false, TEXT("data/ship/aquila_plan.json does not read"));
			return;
		}
		const TSharedPtr<FJsonObject>& Placements = Root->GetObjectField(TEXT("placements"));
		const TArray<TSharedPtr<FJsonValue>>& AllDoors = Root->GetArrayField(TEXT("doors"));
		for (const FString& D : Decks)
		{
			const int32 Deck = FCString::Atoi(*D);
			const TArray<TSharedPtr<FJsonValue>>* List = nullptr;
			if (!Placements->TryGetArrayField(FString::FromInt(Deck), List))
			{
				Check(TEXT("load: placements"), false, FString::Printf(TEXT("deck %d has none"), Deck));
				continue;
			}
			TMap<FString, TArray<FTransform>> ByMesh;
			for (const TSharedPtr<FJsonValue>& V : *List)
			{
				const TSharedPtr<FJsonObject> P = V->AsObject();
				const TArray<TSharedPtr<FJsonValue>>& Pos = P->GetArrayField(TEXT("pos"));
				ByMesh.FindOrAdd(P->GetStringField(TEXT("mesh"))).Add(FTransform(FRotator(0.f, (float)P->GetNumberField(TEXT("yaw")), 0.f),
					FVector(Pos[0]->AsNumber(), Pos[1]->AsNumber(), Pos[2]->AsNumber()) * 100.0));
			}
			const double T0 = FPlatformTime::Seconds();
			TMap<FString, UStaticMesh*> Meshes;
			for (const TPair<FString, TArray<FTransform>>& KV : ByMesh)
			{
				Meshes.Add(KV.Key, LoadObject<UStaticMesh>(nullptr, *FString::Printf(TEXT("/Game/ASTRA/Kit/Ship/%s.%s"), *KV.Key, *KV.Key)));
			}
			const double T1 = FPlatformTime::Seconds();
			AAstraDeckShell* Shell = World->SpawnActor<AAstraDeckShell>(FVector::ZeroVector, FRotator::ZeroRotator);
			Shell->Deck = Deck;
			int32 Missing = 0;
			double WorstAdd = 0.0;
			for (const TPair<FString, TArray<FTransform>>& KV : ByMesh)
			{
				UStaticMesh* M = Meshes[KV.Key];
				if (!M) { ++Missing; continue; }
				const double A0 = FPlatformTime::Seconds();
				Shell->AddInstancesChunked(M, KV.Value, 16000.f);
				WorstAdd = FMath::Max(WorstAdd, (FPlatformTime::Seconds() - A0) * 1000.0);
			}
			const double T2 = FPlatformTime::Seconds();
			int32 Doors = 0;
			for (const TSharedPtr<FJsonValue>& V : AllDoors)
			{
				const TSharedPtr<FJsonObject> O = V->AsObject();
				bool bFlag = false;
				if ((int32)O->GetNumberField(TEXT("deck")) != Deck || (O->TryGetBoolField(TEXT("existing"), bFlag) && bFlag) || (O->TryGetBoolField(TEXT("planned"), bFlag) && bFlag))
				{
					continue;
				}
				const TArray<TSharedPtr<FJsonValue>>& Pos = O->GetArrayField(TEXT("pos"));
				AAstraDoor* Door = World->SpawnActor<AAstraDoor>(FVector(Pos[0]->AsNumber(), Pos[1]->AsNumber(), Pos[2]->AsNumber()) * 100.0, FRotator(0.f, (float)O->GetNumberField(TEXT("yaw")), 0.f));
				Door->Width = (float)O->GetNumberField(TEXT("width")) * 100.f;
				Door->Height = (float)O->GetNumberField(TEXT("height")) * 100.f;
				++Doors;
			}
			const double T3 = FPlatformTime::Seconds();
			double WorstTick = 0.0;
			for (int32 i = 0; i < 30; ++i)
			{
				const double F0 = FPlatformTime::Seconds();
				World->Tick(LEVELTICK_All, 1.f / 60.f);
				WorstTick = FMath::Max(WorstTick, (FPlatformTime::Seconds() - F0) * 1000.0);
			}
			int32 Comps = Shell->NumInstanceComponents();
			// the floor under a corridor module must hold a capsule: a trace down from 1.5 m above the middle of the first straight module of the deck
			{
				FVector At = FVector::ZeroVector;
				for (const TSharedPtr<FJsonValue>& V : *List)
				{
					const TSharedPtr<FJsonObject> P = V->AsObject();
					if (P->GetStringField(TEXT("mesh")).StartsWith(TEXT("SM_SHIP_S_Straight")) && FMath::IsNearlyZero(P->GetNumberField(TEXT("yaw"))))
					{
						const TArray<TSharedPtr<FJsonValue>>& Pos = P->GetArrayField(TEXT("pos"));
						At = FVector(Pos[0]->AsNumber() + 2.0, Pos[1]->AsNumber(), Pos[2]->AsNumber()) * 100.0;
						break;
					}
				}
				FHitResult Hit;
				bool bHit = World->LineTraceSingleByChannel(Hit, At + FVector(0.f, 0.f, 150.f), At - FVector(0.f, 0.f, 100.f), ECC_Pawn);
				// the control: the same mesh as a static mesh actor, 50 m off, traced the same way. A headless world may make no physics at all (the commandlet
				// runs without a renderer): then neither the control nor the instances answer, and the check says so instead of failing
				bool bControl = false;
				if (UStaticMesh* Mod = LoadObject<UStaticMesh>(nullptr, TEXT("/Game/ASTRA/Kit/Ship/SM_SHIP_S_Straight_A.SM_SHIP_S_Straight_A")))
				{
					AStaticMeshActor* SMA = World->SpawnActor<AStaticMeshActor>(FVector(At.X, At.Y + 5000.f, At.Z), FRotator::ZeroRotator);
					SMA->GetStaticMeshComponent()->SetMobility(EComponentMobility::Movable);
					SMA->GetStaticMeshComponent()->SetStaticMesh(Mod);
					SMA->GetStaticMeshComponent()->SetMobility(EComponentMobility::Static);
					FHitResult H2;
					bControl = World->LineTraceSingleByChannel(H2, FVector(At.X, At.Y + 5000.f, At.Z + 150.f), FVector(At.X, At.Y + 5000.f, At.Z - 100.f), ECC_Pawn);
				}
				if (!bControl)
				{
					Check(TEXT("load: the floor holds (ISM collision)"), true, TEXT("skipped: this headless world makes no physics, not even for a plain static mesh actor"));
				}
				else
				{
					Check(TEXT("load: the floor holds (ISM collision)"), bHit && FMath::Abs(Hit.ImpactPoint.Z - At.Z) < 8.f,
					      FString::Printf(TEXT("deck %d: a trace down at (%.0f, %.0f) %s %s at z %.1f cm over the floor"), Deck, At.X, At.Y, bHit ? TEXT("hit") : TEXT("missed"),
					                      Hit.GetComponent() ? *Hit.GetComponent()->GetName() : TEXT("-"), bHit ? Hit.ImpactPoint.Z - At.Z : 0.f));
				}
			}
			// the physics bodies of the instances (a collision per instance: the Captain walks on them): made again on purpose, to time them
			double PhysMs = 0.0;
			{
				TArray<UInstancedStaticMeshComponent*> IC;
				Shell->GetComponents<UInstancedStaticMeshComponent>(IC);
				if (IC.Num())
				{
					const UInstancedStaticMeshComponent* C0 = IC[0];
					UE_LOG(LogASTRA, Display, TEXT("[Nave]   %s: collision %d, profile %s, registered %d, physics state %d, instance bodies %d, complex-as-simple %d"), *C0->GetName(),
					       (int32)C0->GetCollisionEnabled(), *C0->GetCollisionProfileName().ToString(), C0->IsRegistered(), C0->IsPhysicsStateCreated(), C0->GetInstanceBodies().Num(),
					       C0->GetStaticMesh() && C0->GetStaticMesh()->GetBodySetup() ? (int32)C0->GetStaticMesh()->GetBodySetup()->CollisionTraceFlag : -1);
				}
				const double P0 = FPlatformTime::Seconds();
				for (UInstancedStaticMeshComponent* C : IC) { C->RecreatePhysicsState(); }
				PhysMs = (FPlatformTime::Seconds() - P0) * 1000.0;
				UE_LOG(LogASTRA, Display, TEXT("[Nave]   physics scene %s: the instances' bodies made again in %.1f ms"), World->GetPhysicsScene() ? TEXT("present") : TEXT("ABSENT"), PhysMs);
			}
			Check(TEXT("load: a deck comes in under a second"), Missing == 0 && (T3 - T0) < 1.0,
			      FString::Printf(TEXT("deck %d: %.0f ms (meshes %.0f, %d instances in %d components %.0f ms - the longest component %.1f ms, %d doors %.0f ms); a frame after: %.1f ms; %d meshes missing"),
			                      Deck, (T3 - T0) * 1000.0, (T1 - T0) * 1000.0, Shell->NumInstances(), Comps, (T2 - T1) * 1000.0, WorstAdd, Doors, (T3 - T2) * 1000.0, WorstTick, Missing));
			// out again: the actors go, then a collection
			const double U0 = FPlatformTime::Seconds();
			Shell->Destroy();
			for (TActorIterator<AAstraDoor> It(World); It; ++It)
			{
				It->Destroy();
			}
			World->Tick(LEVELTICK_All, 1.f / 60.f);
			CollectGarbage(GARBAGE_COLLECTION_KEEPFLAGS);
			Check(TEXT("load: and out again"), true, FString::Printf(TEXT("deck %d: %.0f ms to destroy and collect"), Deck, (FPlatformTime::Seconds() - U0) * 1000.0));
		}
		GEngine->DestroyWorldContext(World);
		World->DestroyWorld(false);
	}
}

int32 UAstraNaveCommandlet::Main(const FString& Params)
{
	float StepCm = 200.f;
	int32 MaxLit = 10;
	FParse::Value(*Params, TEXT("step="), StepCm);
	FParse::Value(*Params, TEXT("max="), MaxLit);
	const bool bVerbose = FParse::Param(*Params, TEXT("verbose"));
	Checks.Reset();
	FString LoadList;
	if (FParse::Value(*Params, TEXT("load="), LoadList, false))
	{
		TArray<FString> Decks;
		LoadList.ParseIntoArray(Decks, TEXT(","));
		LoadTest(Decks);
		int32 Failed = 0;
		for (const FCheck& C : Checks) { Failed += C.bPass ? 0 : 1; }
		return Failed ? 1 : 0;
	}
	UAstraShipPlan* Plan = NewObject<UAstraShipPlan>(GetTransientPackage());
	if (!Plan->EnsureLoaded())
	{
		UE_LOG(LogASTRA, Error, TEXT("[Nave] no ship's plan"));
		return 1;
	}
	const TArray<FAstraPlanCompartment>& Comps = Plan->GetCompartments();
	const TArray<FAstraPlanLamp>& Lamps = Plan->GetLamps();

	// ---- 1. the lamps are in the plan, inside their compartments, on every built deck
	int32 Outside = 0, Dark = 0;
	TMap<int32, int32> PerDeck;
	for (const FAstraPlanCompartment& C : Comps)
	{
		for (int32 l = C.FirstLamp; l < C.FirstLamp + C.NumLamps; ++l)
		{
			const FAstraPlanLamp& L = Lamps[l];
			const FBox Box = C.Box.ExpandBy(FVector(15.f, 15.f, 40.f));
			Outside += Box.IsInsideOrOn(L.Pos) ? 0 : 1;
			Dark += L.Lumens > 0.f && L.RadiusCm > 0.f ? 0 : 1;
			PerDeck.FindOrAdd(C.Deck)++;
		}
	}
	FString PerDeckText;
	TArray<int32> LitDecks;
	PerDeck.GetKeys(LitDecks);
	LitDecks.Sort();
	for (const int32 D : LitDecks)
	{
		PerDeckText += FString::Printf(TEXT(" d%d:%d"), D, PerDeck[D]);
	}
	Check(TEXT("lamps in the plan"), Lamps.Num() > 0, FString::Printf(TEXT("%d lamps (%s )"), Lamps.Num(), *PerDeckText));
	Check(TEXT("every lamp inside its room"), Outside == 0, FString::Printf(TEXT("%d outside"), Outside));
	Check(TEXT("every lamp has light and reach"), Dark == 0, FString::Printf(TEXT("%d without"), Dark));

	// ---- 2. a Captain walks the Spine of every deck that has lamps
	double WorstChanges = 0.0, SumChanges = 0.0, SumNearChanges = 0.0, SumLit = 0.0, WorstMs = 0.0, SumMs = 0.0;
	int32 Steps = 0, Counted = 0, Starved = 0, OffDeck = 0;
	for (const int32 Deck : LitDecks)
	{
		// the Spine: the deck's corridor places near y = 0 from the bow to the stern, walked from one to the next where they are within 6 m
		TArray<FVector> Spine;
		for (int32 i = 0; i < Plan->NumNodes(); ++i)
		{
			const FAstraPlanNode* N = Plan->Node(i);
			if (N->Deck == Deck && N->Kind == TEXT("corridor") && FMath::Abs(N->Pos.Y) < 150.f)
			{
				Spine.Add(N->Pos);
			}
		}
		Spine.Sort([](const FVector& A, const FVector& B) { return A.X > B.X; });
		TSet<int32> Lit;
		TSet<int32> Prev;
		bool bFirstOfRun = true;
		for (int32 p = 1; p < Spine.Num(); ++p)
		{
			const FVector A = Spine[p - 1], B = Spine[p];
			if (FVector::Dist(A, B) > 600.f)
			{
				bFirstOfRun = true;
				continue;
			}
			const int32 N = FMath::Max(1, FMath::CeilToInt(FVector::Dist(A, B) / StepCm));
			for (int32 s = 0; s < N; ++s)
			{
				const FVector Feet = FMath::Lerp(A, B, (float)s / N);
				const FVector Eye = Feet + FVector(0.f, 0.f, 160.f);
				TArray<int32> Want;
				const double T0 = FPlatformTime::Seconds();
				FAstraLampPicker::Pick(*Plan, Eye, Feet, MaxLit, 3000.f, Lit, Want);
				const double Ms = (FPlatformTime::Seconds() - T0) * 1000.0;
				if (bVerbose && (Steps % 10 == 0))
				{
					FString Names;
					for (const int32 W : Want) { Names += FString::Printf(TEXT(" %s"), *Comps[Lamps[W].Comp].Id); }
					UE_LOG(LogASTRA, Display, TEXT("[Nave]   d%d (%.0f, %.0f): %d lamps:%s"), Deck, Feet.X / 100.f, Feet.Y / 100.f, Want.Num(), *Names);
				}
				WorstMs = FMath::Max(WorstMs, Ms);
				SumMs += Ms;
				const TSet<int32> Now(Want);
				if (!bFirstOfRun)
				{
					int32 Changed = 0, Near = 0;
					for (const int32 W : Now) { if (!Prev.Contains(W)) { ++Changed; Near += FVector::Dist(Eye, Lamps[W].Pos) < 1000.f ? 1 : 0; } }
					for (const int32 W : Prev) { if (!Now.Contains(W)) { ++Changed; Near += FVector::Dist(Eye, Lamps[W].Pos) < 1000.f ? 1 : 0; } }
					SumChanges += Changed;
					SumNearChanges += Near;
					WorstChanges = FMath::Max(WorstChanges, (double)Changed);
					++Counted;
				}
				bFirstOfRun = false;
				SumLit += Now.Num();
				Starved += Now.Num() < 2 ? 1 : 0;
				for (const int32 W : Now)
				{
					OffDeck += FMath::Abs(Lamps[W].Pos.Z - Eye.Z) > 600.f ? 1 : 0;
				}
				Prev = Now;
				Lit = Now;
				++Steps;
			}
		}
	}
	Check(TEXT("walk: lamps near the Captain"), Steps > 0 && Starved == 0, FString::Printf(TEXT("%d steps, avg %.1f lit, %d with fewer than 2"), Steps, Steps ? SumLit / Steps : 0.0, Starved));
	// the lamps at the edge of his reach come and go as he walks (they fade); the ones within 10 m of him must hold their place
	Check(TEXT("walk: no flicker"), Counted > 0 && SumNearChanges / FMath::Max(1, Counted) < 0.3,
	      FString::Printf(TEXT("%.2f lamp changes a step of %.1f m, %.2f of them within 10 m (worst step %.0f)"), SumChanges / FMath::Max(1, Counted), StepCm / 100.f,
	                      SumNearChanges / FMath::Max(1, Counted), WorstChanges));
	Check(TEXT("walk: only his deck"), OffDeck == 0, FString::Printf(TEXT("%d lamps off his deck"), OffDeck));
	Check(TEXT("walk: cheap"), WorstMs < 2.0, FString::Printf(TEXT("%.3f ms average, %.3f ms worst per pick (the pool picks 5 times a second)"), Steps ? SumMs / Steps : 0.0, WorstMs));

	// ---- 3. a room behind a closed door stays dark: stand in the middle of a built room and then at its door
	int32 RoomTests = 0, RoomLeaks = 0, DoorLights = 0, DoorTests = 0;
	for (int32 ci = 0; ci < Comps.Num(); ++ci)
	{
		const FAstraPlanCompartment& C = Comps[ci];
		if (C.bExisting || !C.bBuilt || C.NumLamps == 0 || C.Kind == TEXT("corridor") || C.Kind == TEXT("vestibule") || RoomTests >= 60)
		{
			continue;
		}
		const FVector Mid = C.Box.GetCenter();
		const FVector Feet(Mid.X, Mid.Y, C.Box.Min.Z);
		TArray<int32> Want;
		int32 Here = INDEX_NONE;
		FAstraLampPicker::Pick(*Plan, Feet + FVector(0.f, 0.f, 160.f), Feet, MaxLit, 3000.f, TSet<int32>(), Want, &Here);
		++RoomTests;
		// in the middle of the room the lamps are the room's own and the corridor sections open to its doors only when he is near them
		for (const int32 W : Want)
		{
			if (Lamps[W].Comp != ci && FVector::Dist(Feet, Lamps[W].Pos) > 1500.f)
			{
				// a lamp of another compartment that far away would be a leak through the wall (the corridor is within the room's reach only at its door)
				bool bAtADoor = false;
				for (const FAstraPlanLink& L : Plan->CompLinks(ci))
				{
					// a door he is at, or a way that is open (the Spine runs into the Concourse and the bow observation deck)
					bAtADoor |= L.bDoor ? FVector::Dist(Feet + FVector(0.f, 0.f, 160.f), L.DoorCm) <= FAstraLampPicker::DoorSeeCm : L.Comp == Lamps[W].Comp;
				}
				RoomLeaks += bAtADoor ? 0 : 1;
				if (!bAtADoor && bVerbose)
				{
					UE_LOG(LogASTRA, Display, TEXT("[Nave]   leak: standing in %s (%s) lights %s at %.1f m"), *C.Id, *C.Kind, *Comps[Lamps[W].Comp].Id, FVector::Dist(Feet, Lamps[W].Pos) / 100.f);
				}
			}
		}
		// at the door (1.5 m inside): the corridor's lamps may join
		for (const FAstraPlanLink& L : Plan->CompLinks(ci))
		{
			if (!L.bDoor)
			{
				continue;
			}
			const FVector ToMid = (Mid - L.DoorCm).GetSafeNormal2D();
			const FVector AtDoor = L.DoorCm + ToMid * 150.f;
			TArray<int32> Near;
			FAstraLampPicker::Pick(*Plan, AtDoor + FVector(0.f, 0.f, 160.f), FVector(AtDoor.X, AtDoor.Y, C.Box.Min.Z), MaxLit, 3000.f, TSet<int32>(), Near);
			++DoorTests;
			bool bCorridor = false;
			for (const int32 W : Near)
			{
				bCorridor |= Lamps[W].Comp != ci;
			}
			DoorLights += bCorridor ? 1 : 0;
			break;
		}
	}
	Check(TEXT("room: closed door keeps the next dark"), RoomTests > 0 && RoomLeaks == 0, FString::Printf(TEXT("%d rooms from their middle: %d lamps through a wall"), RoomTests, RoomLeaks));
	Check(TEXT("room: at its door the corridor lights"), DoorTests > 0 && DoorLights >= DoorTests * 9 / 10, FString::Printf(TEXT("%d of %d rooms"), DoorLights, DoorTests));

	// ---- 4. the decks wanted around the Captain
	auto Has = [](const TArray<int32>& A, std::initializer_list<int32> Want)
	{
		if (A.Num() != (int32)Want.size())
		{
			return false;
		}
		for (const int32 W : Want) { if (!A.Contains(W)) { return false; } }
		return true;
	};
	const TArray<int32> D5 = UAstraDeckStreaming::DecksFor(*Plan, 5, false);
	const TArray<int32> D2 = UAstraDeckStreaming::DecksFor(*Plan, 2, false);
	const TArray<int32> D12 = UAstraDeckStreaming::DecksFor(*Plan, 12, false);
	const TArray<int32> D9H = UAstraDeckStreaming::DecksFor(*Plan, 9, true);
	const TArray<int32> D1 = UAstraDeckStreaming::DecksFor(*Plan, 1, false);
	Check(TEXT("decks: a middle deck"), Has(D5, {4, 5, 6}), FString::Printf(TEXT("deck 5 wants %d decks"), D5.Num()));
	Check(TEXT("decks: the top of the stairs"), Has(D2, {2, 3}), FString::Printf(TEXT("deck 2 wants %d decks"), D2.Num()));
	Check(TEXT("decks: the keel"), Has(D12, {11, 12}), FString::Printf(TEXT("deck 12 wants %d decks"), D12.Num()));
	Check(TEXT("decks: in a hall only its own"), Has(D9H, {9}), TEXT("the Flight Deck's hall wants deck 9"));
	Check(TEXT("decks: the bridge has no stairs"), Has(D1, {1}), TEXT("deck 1 wants itself"));
	// the Flight Deck stands on the Deck 9 plane although its floor is 6.8 m lower and its hall crosses six decks
	const FAstraPlanCompartment* Hangar = nullptr;
	for (const FAstraPlanCompartment& C : Comps)
	{
		if (C.Id == TEXT("flight_deck"))
		{
			Hangar = &C;
		}
	}
	if (Hangar)
	{
		const int32 DeckInHall = Plan->DeckOfPoint(Hangar->Box.GetCenter());
		Check(TEXT("decks: the hall's own plane"), DeckInHall == Hangar->Plane, FString::Printf(TEXT("the Flight Deck's centre is on plane %d (compartment plane %d)"), DeckInHall, Hangar->Plane));
	}

	int32 Failed = 0;
	for (const FCheck& C : Checks)
	{
		Failed += C.bPass ? 0 : 1;
	}
	UE_LOG(LogASTRA, Display, TEXT("[Nave] %d checks, %d failed"), Checks.Num(), Failed);
	return Failed ? 1 : 0;
}
