// ASTRA — bench scenarios (docs/GUERRA.md, "Il banco"): a sandbox with no Aquila and no script, ships and wings spawned by
// class from the console or from data/war/scenarios/*.json, for the war bench (tools/war.py, AstraWarSim) and for tuning.
//
//   astra.war.sandbox                          clear the opening: the plot is empty, the Aquila is out of it, no script runs
//   astra.war.spawn <class> <astra|mandate|neutral> <x_km> <y_km> <z_km> [heading_deg] [mark=deg] [missiles=n] [id=X] [name=N]
//                   [static] [hold] [passive]
//                                              one ship (static: exactly on its mark and pointed as it is; hold: on its mark;
//                                              passive: a target dummy that does not fight)
//   astra.war.wing <carrier id> <fighter|bomber|drone> <n> <mission> [target id]
//                                              a flight group aboard a carrier (it launches at once)
//   astra.war.scenario <name> [aquila] [hold|speed=<m/s>|heading=<deg>|at=<x_km>,<y_km>,<z_km>]
//                                              data/war/scenarios/<name>.json (implies the sandbox); "aquila" (or "aquila": true in the
//                                              file) keeps the Aquila in it, with the ASTRA side, held at rest where the file puts her (the origin
//                                              unless it says "aquila": {"at_km": [x,y,z], "heading": deg, "speed": m/s}, or the command does:
//                                              at=), bow to +x: the lead's scale test from the bridge, the same every time
//
// The scenario file: {"mirror": true, "aquila": {...}, "astra": [group...], "mandate": [group...], "waves": [wave...]}; a group: {"name",
// "formation": line|wedge|column, "at_km": [x,y,z], "heading": deg, "spacing_km", "ships": [{"class", "n", "name"}], "wings": [{"carrier":
// index in the group's ships, "kind", "n", "mission", "delay"}]}. mirror: the Mandate side is the ASTRA side turned 180 degrees about
// the origin (the same forces, the same geometry: neither side has the better position). A wave is reinforcements that arrive in the
// battle: {"at_s": battle seconds, "side": "astra"|"mandate", "group": {a group}} (announced on the group-events line). "aquila": the
// Aquila is in the battle: {"at_km": [x,y,z], "heading": deg, "speed": m/s, "wings": [{"kind", "n", "mission", "delay"}]} (her own air group).

#include "AstraBattleSubsystem.h"
#include "AstraWarClasses.h"
#include "AstraShipSubsystem.h"
#include "AstraWarDraw.h"
#include "ASTRA.h"
#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

namespace
{
	TArray<TArray<FString>> GWarCommands;

	FAutoConsoleCommand CmdWarSandbox(TEXT("astra.war.sandbox"), TEXT("War bench: empty the plot, take the Aquila out of it, no script"),
		FConsoleCommandDelegate::CreateLambda([]() { GWarCommands.Add({TEXT("sandbox")}); }));
	FAutoConsoleCommand CmdWarSpawn(TEXT("astra.war.spawn"),
		TEXT("War bench: astra.war.spawn <class> <astra|mandate|neutral> <x_km> <y_km> <z_km> [heading_deg] [mark=deg] [missiles=n] [id=X] [name=N] [static] [hold] [passive]"),
		FConsoleCommandWithArgsDelegate::CreateLambda([](const TArray<FString>& A)
		{
			TArray<FString> C = {TEXT("spawn")};
			C.Append(A);
			GWarCommands.Add(C);
		}));
	FAutoConsoleCommand CmdWarWing(TEXT("astra.war.wing"), TEXT("War bench: astra.war.wing <carrier id> <fighter|bomber|drone> <n> <mission> [target id]"),
		FConsoleCommandWithArgsDelegate::CreateLambda([](const TArray<FString>& A)
		{
			TArray<FString> C = {TEXT("wing")};
			C.Append(A);
			GWarCommands.Add(C);
		}));
	FAutoConsoleCommand CmdWarFleet(TEXT("astra.war.fleet"), TEXT("War bench: astra.war.fleet <info|strike|hit|pound> <args> (FLOTTA-VIVA: astra.fleet.*, run in its turn after the spawns before it)"),
		FConsoleCommandWithArgsDelegate::CreateLambda([](const TArray<FString>& A)
		{
			TArray<FString> C = {TEXT("fleet")};
			C.Append(A);
			GWarCommands.Add(C);
		}));
	FAutoConsoleCommand CmdWarScenario(TEXT("astra.war.scenario"), TEXT("War bench: astra.war.scenario <name> (data/war/scenarios/<name>.json)"),
		FConsoleCommandWithArgsDelegate::CreateLambda([](const TArray<FString>& A)
		{
			TArray<FString> C = {TEXT("scenario")};
			C.Append(A);
			GWarCommands.Add(C);
		}));

	EAstraSide SideOf(const FString& S)
	{
		return S.Equals(TEXT("astra"), ESearchCase::IgnoreCase) ? EAstraSide::Astra
		     : (S.Equals(TEXT("mandate"), ESearchCase::IgnoreCase) ? EAstraSide::Mandate : EAstraSide::Neutral);
	}

	FVector VecKm(const TArray<TSharedPtr<FJsonValue>>* A)
	{
		return A && A->Num() >= 3 ? FVector((*A)[0]->AsNumber(), (*A)[1]->AsNumber(), (*A)[2]->AsNumber()) * 1000.0 : FVector::ZeroVector;
	}
}

namespace AstraWar
{
	namespace
	{
		TMap<FString, float> GTune;
		int32 GTuneVersion = 0;
		FAutoConsoleCommand CmdWarTune(TEXT("astra.war.tune"), TEXT("War tuning: astra.war.tune <name> <value>; without arguments, the table"),
			FConsoleCommandWithArgsDelegate::CreateLambda([](const TArray<FString>& A)
			{
				if (A.Num() >= 2)
				{
					GTune.Add(A[0].ToLower(), FCString::Atof(*A[1]));
					++GTuneVersion;
				}
				for (const TPair<FString, float>& KV : GTune)
				{
					UE_LOG(LogASTRA, Display, TEXT("[War] tune %s = %g"), *KV.Key, KV.Value);
				}
			}));
	}

	int32& TuneVersion()
	{
		return GTuneVersion;
	}

	bool TuneLookup(const TCHAR* Name, float& Out)
	{
		if (const float* V = GTune.Find(FString(Name).ToLower()))
		{
			Out = *V;
			return true;
		}
		return false;
	}
}

void UAstraBattleSubsystem::ProcessWarCommands()
{
	if (GWarCommands.Num() == 0)
	{
		return;
	}
	const TArray<TArray<FString>> Todo = MoveTemp(GWarCommands);
	GWarCommands.Reset();
	for (const TArray<FString>& A : Todo)
	{
		const FString& Cmd = A[0];
		if (Cmd == TEXT("sandbox"))
		{
			SandboxReset();
		}
		else if (Cmd == TEXT("scenario") && A.Num() >= 2)
		{
			FString Detail;
			TArray<FString> Options;                                 // with "aquila": hold, speed=<m/s>, heading=<deg>, at=<x_km>,<y_km>,<z_km>
			bool bAquila = false;
			for (int32 i = 2; i < A.Num(); ++i)
			{
				if (A[i].Equals(TEXT("aquila"), ESearchCase::IgnoreCase))
				{
					bAquila = true;
				}
				else
				{
					Options.Add(A[i]);
				}
			}
			const bool bOk = LoadScenario(A[1], Detail, bAquila, Options);
			UE_LOG(LogASTRA, Display, TEXT("[WarSim] scenario %s: %s%s"), *A[1], bOk ? TEXT("") : TEXT("FAILED — "), *Detail);
		}
		else if (Cmd == TEXT("spawn") && A.Num() >= 6)
		{
			if (!bSandbox)
			{
				SandboxReset();
			}
			FString Id, Name;
			float Heading = 0.f, Mark = 0.f;
			int32 Missiles = -1;
			bool bStatic = false, bHold = false, bPassive = false;
			for (int32 i = 6; i < A.Num(); ++i)
			{
				if (A[i].StartsWith(TEXT("id="))) { Id = A[i].Mid(3).ToUpper(); }
				else if (A[i].StartsWith(TEXT("name="))) { Name = A[i].Mid(5).Replace(TEXT("_"), TEXT(" ")); }
				else if (A[i].StartsWith(TEXT("mark="))) { Mark = FCString::Atof(*A[i].Mid(5)); }
				else if (A[i].StartsWith(TEXT("missiles="))) { Missiles = FCString::Atoi(*A[i].Mid(9)); }
				else if (A[i] == TEXT("static")) { bStatic = true; }
				else if (A[i] == TEXT("hold")) { bHold = true; }
				else if (A[i] == TEXT("passive")) { bPassive = true; }
				else { Heading = FCString::Atof(*A[i]); }
			}
			const FVector Pos(FCString::Atod(*A[3]) * 1000.0, FCString::Atod(*A[4]) * 1000.0, FCString::Atod(*A[5]) * 1000.0);
			const EAstraSide Side = SideOf(A[2]);
			if (Id.IsEmpty())
			{
				Id = FString::Printf(TEXT("%s-%02d"), Side == EAstraSide::Astra ? TEXT("A") : (Side == EAstraSide::Mandate ? TEXT("M") : TEXT("N")), NextContact++);
			}
			const int32 I = SpawnByKey(FName(*A[1].ToLower()), Side, Id, Name.IsEmpty() ? FString::Printf(TEXT("%s %s"), *A[1], *Id) : Name, Pos, Heading);
			if (I == INDEX_NONE)
			{
				UE_LOG(LogASTRA, Warning, TEXT("[WarSim] astra.war.spawn: no ship class '%s'"), *A[1]);
				continue;
			}
			Ships[I].Att = FRotator(Mark, Heading, 0.f).Quaternion();
			if (Missiles >= 0)
			{
				Ships[I].Missiles = Missiles;
			}
			Ships[I].bHoldStation = bStatic || bHold;
			Ships[I].bFixedAtt = bStatic;
			if (bPassive)
			{
				Ships[I].Mode = EAstraShipMode::Idle;
				Ships[I].bHoldStation = true;
			}
		}
		else if (Cmd == TEXT("fleet") && A.Num() >= 2)
		{
			TArray<FString> Rest;
			for (int32 i = 2; i < A.Num(); ++i)
			{
				Rest.Add(A[i]);
			}
			UE_LOG(LogASTRA, Display, TEXT("[Fleet] %s"), *FleetConsole(A[1], Rest));
		}
		else if (Cmd == TEXT("wing") && A.Num() >= 5)
		{
			const FAstraBattleShip* Carrier = FindByContact(A[1].ToUpper());
			if (!Carrier)
			{
				UE_LOG(LogASTRA, Warning, TEXT("[WarSim] astra.war.wing: no carrier '%s'"), *A[1]);
				continue;
			}
			const int32 CarrierIdx = UE_PTRDIFF_TO_INT32(Carrier - Ships.GetData());
			const int32 Kind = A[2].StartsWith(TEXT("b")) ? 1 : (A[2].StartsWith(TEXT("d")) ? 2 : 0);
			const int32 Q = AddWing(CarrierIdx, Kind, FCString::Atoi(*A[3]), A[4].ToLower(), 1.f);
			if (Q != INDEX_NONE && A.Num() >= 6)
			{
				if (const FAstraBattleShip* T = FindByContact(A[5].ToUpper()))
				{
					Squadrons[Q].TargetId = T->Id;
				}
			}
		}
	}
}

void UAstraBattleSubsystem::SandboxReset(bool bKeepAquila)
{
	ClearSystem();
	ScenarioWaves.Reset();
	Ships.Reserve(512);
	FAstraBattleShip& P = Ships[0];
	if (!bKeepAquila)
	{
		P.bAlive = false;                   // the Aquila is not in it: the bench's forces are the two sides' own
		P.Mode = EAstraShipMode::Dead;
		P.Pos = FVector(0.0, 0.0, -1.0e9);  // far away: nothing measures against her
	}
	Squadrons.Reset();
	bSandbox = true;
	bStarted = true;
	if (WarDraw)
	{
		WarDraw->Prewarm();                 // the craft's kinds of hull ready before the first wing launches
	}
	bBriefed = true;
	StageDone = OpeningOver;
	bEngagementActive = false;
	bScenarioOver = false;
	bPlayerTracked = true;
	NextContact = 1;
	UE_LOG(LogASTRA, Display, TEXT("[WarSim] sandbox: the plot is empty%s"), bKeepAquila ? TEXT(" but for the Aquila") : TEXT(""));
}

int32 UAstraBattleSubsystem::SpawnByKey(FName Key, EAstraSide Side, const FString& Contact, const FString& Name, const FVector& Pos, float HeadingDeg)
{
	const AstraWar::FShipClass* C = AstraWar::FindClass(Key);
	if (!C)
	{
		return INDEX_NONE;
	}
	const int32 I = AddShip(Contact, Name, C->Label, C->Mesh, Side, Pos, HeadingDeg, 0.f, C->Radius, C->Hull, C->Shield);
	FAstraBattleShip& S = Ships[I];
	S.CruiseSpeed = C->Cruise;
	S.bHostile = Side == EAstraSide::Mandate;
	S.Mode = (S.RailDamage > 0.f || S.Missiles > 0) ? EAstraShipMode::Attack : EAstraShipMode::Idle;
	if (Side == EAstraSide::Neutral)
	{
		S.Mode = EAstraShipMode::Idle;
	}
	SpawnVisual(S);
	return I;
}

int32 UAstraBattleSubsystem::AddWing(int32 CarrierIdx, int32 Kind, int32 Count, const FString& Mission, float Delay)
{
	if (!Ships.IsValidIndex(CarrierIdx) || Count <= 0)
	{
		return INDEX_NONE;
	}
	const FAstraBattleShip& Carrier = Ships[CarrierIdx];
	const bool bAstra = Carrier.Side == EAstraSide::Astra;
	FAstraSquadron Q;
	Q.Kind = Kind;
	Q.Name = FString::Printf(TEXT("w%d-%d"), Carrier.Id, Kind);
	Q.CallSign = Kind == 1 ? (bAstra ? TEXT("Hammer") : TEXT("Talon")) : (Kind == 2 ? (bAstra ? TEXT("Wasp") : TEXT("Gnat")) : (bAstra ? TEXT("Falcon") : TEXT("Harpy")));
	Q.Mesh = bAstra ? (Kind == 1 ? TEXT("SM_CRAFT_ASTRA_Hammer") : (Kind == 2 ? TEXT("SM_CRAFT_ASTRA_Wasp") : TEXT("SM_CRAFT_ASTRA_Falcon"))) : TEXT("SM_CRAFT_MANDATE_Harpy");
	Q.Total = Q.OnDeck = Q.ToLaunch = Count;
	Q.LaunchT = Delay;
	Q.Side = Carrier.Side;
	Q.CarrierId = Carrier.Id;
	Q.Mission = Mission;
	Q.Rockets = Kind == 0 ? 4 : 0;                         // (the two sides' wings are alike in a bench scenario: the same load-out)
	Q.bAuto = true;                                        // a bench wing has no crew to give it targets
	Squadrons.Add(Q);
	return Squadrons.Num() - 1;
}


int32 UAstraBattleSubsystem::SpawnScenarioGroup(const TSharedPtr<FJsonObject>& G, EAstraSide Side, int32 SideIdx, bool bRotated, int32& Spawned, int32& Wings,
                                                FString& OutName, FString& OutProtects)
{
	FString GName = TEXT("Group"), Formation = TEXT("line"), Protects;
	G->TryGetStringField(TEXT("name"), GName);
	G->TryGetStringField(TEXT("formation"), Formation);
	G->TryGetStringField(TEXT("protects"), Protects);
	const TArray<TSharedPtr<FJsonValue>>* Obj = nullptr;
	G->TryGetArrayField(TEXT("objective_km"), Obj);
	const TArray<TSharedPtr<FJsonValue>>* At = nullptr;
	G->TryGetArrayField(TEXT("at_km"), At);
	FVector Origin = VecKm(At);
	double Heading = 0.0, Spacing = 1.5;
	G->TryGetNumberField(TEXT("heading"), Heading);
	G->TryGetNumberField(TEXT("spacing_km"), Spacing);
	if (bRotated)
	{
		Origin = FVector(-Origin.X, -Origin.Y, Origin.Z);
		Heading += 180.0;
	}
	// the ships of the group, in order
	struct FPlan { FName Key; FString Name; bool bHold; };
	TArray<FPlan> Plan;
	const TArray<TSharedPtr<FJsonValue>>* Ships_ = nullptr;
	if (G->TryGetArrayField(TEXT("ships"), Ships_))
	{
		for (const TSharedPtr<FJsonValue>& SV : *Ships_)
		{
			const TSharedPtr<FJsonObject> SO = SV->AsObject();
			FString Class, SName;
			double N = 1.0;
			if (!SO.IsValid() || !SO->TryGetStringField(TEXT("class"), Class))
			{
				continue;
			}
			SO->TryGetNumberField(TEXT("n"), N);
			SO->TryGetStringField(TEXT("name"), SName);
			bool bHold = false;
			SO->TryGetBoolField(TEXT("hold"), bHold);
			for (int32 k = 0; k < (int32)N; ++k)
			{
				Plan.Add({FName(*Class.ToLower()), SName.IsEmpty() ? FString() : (N > 1.0 ? FString::Printf(TEXT("%s %d"), *SName, k + 1) : SName), bHold});
			}
		}
	}
	const FVector Fwd = FRotator(0.0, Heading, 0.0).RotateVector(FVector::ForwardVector);
	const FVector Right = FRotator(0.0, Heading, 0.0).RotateVector(FVector::RightVector);
	FVector Objective = Obj ? VecKm(Obj) : FVector::ZeroVector;
	if (bRotated && Obj)
	{
		Objective = FVector(-Objective.X, -Objective.Y, Objective.Z);
	}
	TArray<int32> Made;
	for (int32 k = 0; k < Plan.Num(); ++k)
	{
		// slots: line abreast, a wedge (the first ship at the point), or a column
		FVector Slot = Origin;
		const double Sp = Spacing * 1000.0;
		if (Formation == TEXT("column"))
		{
			Slot += Fwd * (-Sp * k);
		}
		else if (Formation == TEXT("wedge"))
		{
			const int32 Rank = (k + 1) / 2;
			Slot += Right * ((k % 2 ? 1.0 : -1.0) * Rank * Sp) + Fwd * (-Sp * 0.8 * Rank);
		}
		else
		{
			Slot += Right * ((k - (Plan.Num() - 1) * 0.5) * Sp);
		}
		const FString Id = FString::Printf(TEXT("%s-%02d"), Side == EAstraSide::Astra ? TEXT("A") : TEXT("M"), ScenarioCounter[SideIdx]++);
		const int32 I = SpawnByKey(Plan[k].Key, Side, Id, Plan[k].Name.IsEmpty() ? FString::Printf(TEXT("%s %s"), *Plan[k].Key.ToString(), *Id) : Plan[k].Name, Slot, (float)Heading);
		if (I != INDEX_NONE)
		{
			Ships[I].bHoldStation = Plan[k].bHold;
			Made.Add(I);
			++Spawned;
		}
	}
	const int32 Gid = NoteGroupSpawn(Side, bRotated ? GName + TEXT(" (mirror)") : GName, Formation, Made, INDEX_NONE);
	if (FAstraBattleGroup* NG = FindGroup(Gid))
	{
		NG->Objective = Objective;                       // where it goes when it sees nothing (the origin unless the file says)
		NG->bHasObjective = true;
	}
	const TArray<TSharedPtr<FJsonValue>>* Ws = nullptr;
	if (G->TryGetArrayField(TEXT("wings"), Ws))
	{
		Wings += AddScenarioWings(*Ws, Made);
	}
	OutName = GName;
	OutProtects = Protects;
	return Gid;
}

int32 UAstraBattleSubsystem::AddScenarioWings(const TArray<TSharedPtr<FJsonValue>>& List, const TArray<int32>& Made)
{
	int32 Added = 0;
	for (const TSharedPtr<FJsonValue>& WV : List)
	{
		const TSharedPtr<FJsonObject> WO = WV->AsObject();
		if (!WO.IsValid())
		{
			continue;
		}
		double CarrierK = 0.0, N = 8.0, Delay = 20.0;
		FString KindS = TEXT("fighter"), Mission = TEXT("cap");
		WO->TryGetNumberField(TEXT("carrier"), CarrierK);
		WO->TryGetNumberField(TEXT("n"), N);
		WO->TryGetNumberField(TEXT("delay"), Delay);
		WO->TryGetStringField(TEXT("kind"), KindS);
		WO->TryGetStringField(TEXT("mission"), Mission);
		if (Made.IsValidIndex((int32)CarrierK))
		{
			const int32 Kind = KindS.StartsWith(TEXT("b")) ? 1 : (KindS.StartsWith(TEXT("d")) ? 2 : 0);
			if (AddWing(Made[(int32)CarrierK], Kind, (int32)N, Mission.ToLower(), (float)Delay) != INDEX_NONE)
			{
				++Added;
			}
		}
	}
	return Added;
}

bool UAstraBattleSubsystem::LoadScenario(const FString& Name, FString& OutDetail, bool bWithAquila, const TArray<FString>& Options)
{
	FString Text;
	const FString Path = FPaths::Combine(FPaths::ProjectDir(), TEXT("data/war/scenarios"), Name + TEXT(".json"));
	if (!FFileHelper::LoadFileToString(Text, *Path))
	{
		OutDetail = FString::Printf(TEXT("no such file: %s"), *Path);
		return false;
	}
	TSharedPtr<FJsonObject> Root;
	if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Root) || !Root.IsValid())
	{
		OutDetail = TEXT("it does not parse");
		return false;
	}
	// "aquila": true (or an object: where she is, which way she points, how fast she goes) keeps the Aquila in it
	const TSharedPtr<FJsonObject>* AquilaObj = nullptr;
	Root->TryGetBoolField(TEXT("aquila"), bWithAquila);
	if (Root->TryGetObjectField(TEXT("aquila"), AquilaObj))
	{
		bWithAquila = true;
	}
	SandboxReset(bWithAquila);
	ScenarioCounter[0] = ScenarioCounter[1] = 1;
	ScenarioWaves.Reset();
	bool bMirror = false;
	Root->TryGetBoolField(TEXT("mirror"), bMirror);
	FString First;
	Root->TryGetStringField(TEXT("first"), First);          // which side is spawned first (the order of the ships in the arrays): "mandate" swaps it
	int32 Spawned = 0, Wings = 0;
	TMap<FString, int32> GroupByName[2];              // to resolve "protects" once every group exists
	TArray<TTuple<int32, int32, FString>> Protect;    // group id, side, the name of the group it screens
	const bool bMandateFirst = First.Equals(TEXT("mandate"), ESearchCase::IgnoreCase);
	for (const int32 Pass : {0, 1})
	{
		const int32 SideIdx = bMandateFirst ? 1 - Pass : Pass;
		const EAstraSide Side = SideIdx == 0 ? EAstraSide::Astra : EAstraSide::Mandate;
		const TArray<TSharedPtr<FJsonValue>>* SideGroups = nullptr;
		bool bRotated = false;
		if (!Root->TryGetArrayField(SideIdx == 0 ? TEXT("astra") : TEXT("mandate"), SideGroups))
		{
			if (SideIdx == 1 && bMirror && Root->TryGetArrayField(TEXT("astra"), SideGroups))
			{
				bRotated = true;                            // the ASTRA groups, turned half a circle about the origin
			}
			else
			{
				continue;
			}
		}
		for (const TSharedPtr<FJsonValue>& GV : *SideGroups)
		{
			const TSharedPtr<FJsonObject> G = GV->AsObject();
			if (!G.IsValid())
			{
				continue;
			}
			FString GName, Protects;
			const int32 Gid = SpawnScenarioGroup(G, Side, SideIdx, bRotated, Spawned, Wings, GName, Protects);
			if (FindGroup(Gid))
			{
				GroupByName[SideIdx].Add(GName, Gid);
				if (!Protects.IsEmpty())
				{
					Protect.Add(MakeTuple(Gid, SideIdx, Protects));
				}
			}
		}
	}
	for (const TTuple<int32, int32, FString>& P : Protect)
	{
		const int32* Other = GroupByName[P.Get<1>()].Find(P.Get<2>());
		const FAstraBattleGroup* OG = Other ? FindGroup(*Other) : nullptr;
		if (FAstraBattleGroup* G = FindGroup(P.Get<0>()); G && OG && OG->LeaderId >= 0)
		{
			G->ProtecteeId = OG->LeaderId;                    // it screens the other group's leader (a carrier, a flagship)
			G->Formation = EAstraFormation::Screen;
		}
	}
	// "waves": groups that arrive later (reinforcements: {"at_s": 120, "side": "astra"|"mandate", "group": {the same as a group of the sides}}), as a fleet battle of a campaign has them
	int32 NumWaves = 0;
	const TArray<TSharedPtr<FJsonValue>>* WaveList = nullptr;
	if (Root->TryGetArrayField(TEXT("waves"), WaveList))
	{
		for (const TSharedPtr<FJsonValue>& WV : *WaveList)
		{
			const TSharedPtr<FJsonObject> WO = WV->AsObject();
			if (!WO.IsValid())
			{
				continue;
			}
			FScenarioWave W;
			double At = 0.0;
			FString SideS = TEXT("astra");
			WO->TryGetNumberField(TEXT("at_s"), At);
			WO->TryGetStringField(TEXT("side"), SideS);
			W.At = (float)At;
			W.Side = SideOf(SideS);
			const TSharedPtr<FJsonObject>* GObj = nullptr;
			W.Group = WO->TryGetObjectField(TEXT("group"), GObj) ? *GObj : WO;
			if (AstraSideIdx(W.Side) >= 0)
			{
				ScenarioWaves.Add(W);
				++NumWaves;
			}
		}
	}
	// the Aquila: at the origin with the ASTRA side unless the file or the command says otherwise, held where she is (the helm at rest) so that a test is the same every time;
	// speed=<m/s> and heading=<deg> on the command line (or in the file) set her going
	if (bWithAquila && Ships.Num())
	{
		FVector At = FVector::ZeroVector;
		double Heading = 0.0, Speed = 0.0;
		if (AquilaObj)
		{
			const TArray<TSharedPtr<FJsonValue>>* AtKm = nullptr;
			if ((*AquilaObj)->TryGetArrayField(TEXT("at_km"), AtKm))
			{
				At = VecKm(AtKm);
			}
			(*AquilaObj)->TryGetNumberField(TEXT("heading"), Heading);
			(*AquilaObj)->TryGetNumberField(TEXT("speed"), Speed);
			// her own air group: wings aboard the Aquila herself (they leave through her bow tubes, as they do in the game)
			const TArray<TSharedPtr<FJsonValue>>* AirGroup = nullptr;
			if ((*AquilaObj)->TryGetArrayField(TEXT("wings"), AirGroup))
			{
				const TArray<int32> Herself = {0};
				Wings += AddScenarioWings(*AirGroup, Herself);
			}
		}
		for (const FString& O : Options)
		{
			if (O.StartsWith(TEXT("speed="))) { Speed = FCString::Atod(*O.Mid(6)); }
			else if (O.StartsWith(TEXT("heading="))) { Heading = FCString::Atod(*O.Mid(8)); }
			else if (O.Equals(TEXT("hold"), ESearchCase::IgnoreCase)) { Speed = 0.0; }
			else if (O.StartsWith(TEXT("at=")))
			{
				TArray<FString> Km;                                 // at=<x_km>,<y_km>,<z_km>
				O.Mid(3).ParseIntoArray(Km, TEXT(","));
				if (Km.Num() >= 2)
				{
					At = FVector(FCString::Atod(*Km[0]), FCString::Atod(*Km[1]), Km.Num() >= 3 ? FCString::Atod(*Km[2]) : 0.0) * 1000.0;
				}
			}
		}
		Ships[0].Pos = At;
		Ships[0].Att = FRotator(0.0, Heading, 0.0).Quaternion();
		Ships[0].Vel = Ships[0].Att.GetForwardVector() * Speed;
		if (UAstraShipSubsystem* Ship = GetWorld() ? GetWorld()->GetSubsystem<UAstraShipSubsystem>() : nullptr)
		{
			Ship->DriveExternally((float)Heading, 0.f, (float)Speed);
			Ship->SetThrottle(Speed > 1.0 ? (float)(Speed / 4.8) : 0.f);          // (her speed follows the throttle: at rest she stays so)
		}
	}
	OutDetail = FString::Printf(TEXT("%d ships, %d flight groups%s%s"), Spawned, Wings, NumWaves ? *FString::Printf(TEXT(", %d waves to come"), NumWaves) : TEXT(""),
	                            bWithAquila ? TEXT(", the Aquila in it") : TEXT(""));
	return true;
}

void UAstraBattleSubsystem::TickScenarioWaves()
{
	for (FScenarioWave& W : ScenarioWaves)
	{
		if (W.bDone || Time < W.At)
		{
			continue;
		}
		W.bDone = true;
		const int32 SideIdx = AstraSideIdx(W.Side);
		int32 Spawned = 0, Wings = 0;
		FString GName, Protects;
		const int32 Gid = SpawnScenarioGroup(W.Group, W.Side, SideIdx, false, Spawned, Wings, GName, Protects);
		const FAstraBattleGroup* G = FindGroup(Gid);
		if (!G)
		{
			continue;
		}
		if (!Protects.IsEmpty())
		{
			// the group it screens is one of this side's that is already in the battle
			for (const FAstraBattleGroup& O : Groups)
			{
				if (O.Side == W.Side && O.Id != Gid && O.Name.Equals(Protects, ESearchCase::IgnoreCase) && O.LeaderId >= 0)
				{
					if (FAstraBattleGroup* M = FindGroup(Gid))
					{
						M->ProtecteeId = O.LeaderId;
						M->Formation = EAstraFormation::Screen;
					}
					break;
				}
			}
		}
		TArray<FString> Ids;
		for (const int32 Id : G->Members)
		{
			if (const FAstraBattleShip* S = FindById(Id))
			{
				Ids.Add(FString::Printf(TEXT("%s (%s)"), *S->ContactId, *S->ClassKey.ToString()));
			}
		}
		NoteGroupEvent(SideIdx, FString::Printf(TEXT("%s: reinforcements arriving: %s"), *GName, *FString::Join(Ids, TEXT(", "))));
		UE_LOG(LogASTRA, Display, TEXT("[WarSim] %.0f s: wave %s (%s): %d ships, %d flight groups"), Time, *GName, SideIdx == 0 ? TEXT("ASTRA") : TEXT("Mandate"), Spawned, Wings);
	}
}
