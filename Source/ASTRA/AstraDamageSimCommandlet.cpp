#include "AstraDamageSimCommandlet.h"

#include "ASTRA.h"
#include "AstraDamageMap.h"
#include "AstraDamageFx.h"
#include "AstraDamageModel.h"
#include "AstraBattleSubsystem.h"
#include "AstraLifeSubsystem.h"
#include "AstraShipPlan.h"
#include "AstraShipSubsystem.h"
#include "Engine/Engine.h"
#include "Materials/Material.h"
#include "Engine/StaticMesh.h"
#include "AstraDoor.h"
#include "Engine/World.h"
#include "Tickable.h"
#include "AstraWarTypes.h"
#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "HAL/IConsoleManager.h"
#include "HAL/PlatformTime.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"

namespace
{
	struct FDmCheck
	{
		FString Name;
		bool bPass = true;
		FString Detail;
	};

	TArray<FDmCheck> DmChecks;
	TSharedRef<FJsonObject> DmRecord = MakeShared<FJsonObject>();

	void DmCheck(const TCHAR* Name, bool bPass, const FString& Detail)
	{
		DmChecks.Add({Name, bPass, Detail});
		UE_LOG(LogASTRA, Display, TEXT("[Damage] %s %-34s %s"), bPass ? TEXT("PASS") : TEXT("FAIL"), Name, *Detail);
	}

	void DmSet(const FString& Spec)
	{
		TArray<FString> Items;
		Spec.ParseIntoArray(Items, TEXT(","));
		for (const FString& It : Items)
		{
			FString K, V;
			if (It.Split(TEXT("="), &K, &V))
			{
				if (IConsoleVariable* Cv = IConsoleManager::Get().FindConsoleVariable(*K.TrimStartAndEnd()))
				{
					Cv->Set(*V.TrimStartAndEnd(), ECVF_SetByConsole);
				}
				else
				{
					UE_LOG(LogASTRA, Warning, TEXT("[Damage] no console variable %s"), *K);
				}
			}
		}
	}

	/** The model alone, on the real plan, with a made-up crowd: the physics' bench. */
	struct FDmRig
	{
		TSharedPtr<FAstraDamageMap> Map;
		FAstraDamageModel Model;
		TArray<FAstraDamage> Incidents;
		TArray<FString> Events;
		struct FFake { int32 Roster; FVector Pos; uint8 Status; };
		TArray<FFake> Crowd;
		int32 Killed = 0, Wounded = 0;
		int32 Alert = 2;
		TArray<FName> SealCalls;
		double T = 0.0;

		bool Make(int32 Seed)
		{
			Map = MakeShared<FAstraDamageMap>();
			FString Err;
			if (!Map->Load(Err, true))
			{
				UE_LOG(LogASTRA, Error, TEXT("[Damage] %s"), *Err);
				return false;
			}
			FAstraDmgHooks H;
			H.Event = [this](const FString& Text, bool bReport)
			{
				Events.Add(Text);
				UE_LOG(LogASTRA, Display, TEXT("[Damage] %7.1f %s%s"), T, bReport ? TEXT("REPORT ") : TEXT(""), *Text);
			};
			H.PeopleIn = [this](const FAstraDmgComp& C, TArray<FAstraDmgPerson>& Out)
			{
				for (const FFake& F : Crowd)
				{
					if (F.Status == 0 && C.Box.IsInsideOrOn(F.Pos + FVector(0, 0, 30)))
					{
						FAstraDmgPerson P;
						P.Roster = F.Roster;
						P.PosCm = F.Pos;
						Out.Add(P);
					}
				}
			};
			H.Harm = [this](int32 Roster, bool bKill, EAstraDmgHarm) -> FString
			{
				for (FFake& F : Crowd)
				{
					if (F.Roster == Roster && F.Status == 0)
					{
						F.Status = bKill ? 2 : 1;
						(bKill ? Killed : Wounded)++;
						return FString::Printf(TEXT("#%d %s"), Roster, bKill ? TEXT("killed") : TEXT("wounded"));
					}
				}
				return FString();
			};
			H.SealDoor = [this](FName Id, bool bSealed) { if (bSealed) { SealCalls.Add(Id); } };
			H.Alert = [this]() { return Alert; };
			Model.Init(Map.ToSharedRef(), H, Seed);
			return true;
		}

		int32 Comp(const TCHAR* Id) const { return Map->CompByName.FindRef(FName(Id), INDEX_NONE); }

		void Run(float Seconds, float Dt = 0.1f)
		{
			for (float t = 0.f; t < Seconds; t += Dt)
			{
				Model.Tick(Dt, Incidents);
				T += Dt;
			}
		}
		float Air(int32 C) const { const FAstraDmgState* S = Model.Find(C); return S ? S->Air : 1.f; }
	};

	/** The whole ship in a headless world: the ship, the plan, the life of the 560, the battle: what the people and survival benches run in. */
	struct FDmWorld
	{
		UWorld* World = nullptr;
		UAstraShipSubsystem* Ship = nullptr;
		UAstraLifeSubsystem* Life = nullptr;
		UAstraShipPlan* Plan = nullptr;
		UAstraBattleSubsystem* Battle = nullptr;
		double GameT = 0.0;
		TArray<FString> Reports;

		bool Make()
		{
			World = UWorld::CreateWorld(EWorldType::Game, false, TEXT("AstraDamageSim"));
			FWorldContext& Ctx = GEngine->CreateNewWorldContext(EWorldType::Game);
			Ctx.SetCurrentWorld(World);
			World->InitializeActorsForPlay(FURL());
			World->BeginPlay();
			Ship = World->GetSubsystem<UAstraShipSubsystem>();
			Life = World->GetSubsystem<UAstraLifeSubsystem>();
			Plan = World->GetSubsystem<UAstraShipPlan>();
			Battle = World->GetSubsystem<UAstraBattleSubsystem>();
			if (!Ship || !Life || !Plan || !Battle)
			{
				UE_LOG(LogASTRA, Error, TEXT("[Damage] the ship, its plan, the life or the battle are not in the world"));
				return false;
			}
			Ship->OnShipEvent.AddLambda([this](const FString& Text, bool bReport)
			{
				if (Reports.Num() < 4000)
				{
					Reports.Add(FString::Printf(TEXT("%.1f%s %s"), GameT, bReport ? TEXT(" R") : TEXT(""), *Text));
				}
			});
			// the plan and the tables load on a worker: give them a moment
			const double Wall0 = FPlatformTime::Seconds();
			for (int32 i = 0; i < 4000 && !(Life->IsRunning() && Ship->GetInterior().IsReady()) && FPlatformTime::Seconds() - Wall0 < 60.0; ++i)
			{
				Tick(0.05f);
				FPlatformProcess::Sleep(0.005f);
			}
			GameT = 0.0;
			return Life->IsRunning() && Ship->GetInterior().IsReady();
		}
		void Tick(float Dt)
		{
			const double Before = Life->IsRunning() ? Life->Sim().GameSeconds() : -1.0;
			World->Tick(LEVELTICK_All, Dt);
			const double After = Life->IsRunning() ? Life->Sim().GameSeconds() : -1.0;
			if (FMath::IsNearlyEqual(Before, After))
			{
				FTickableGameObject::TickObjects(World, LEVELTICK_All, false, Dt);       // the world tick did not reach the tickable subsystems
			}
			GameT += Dt;
		}
		void Run(float Seconds, float Dt = 0.1f)
		{
			for (float t = 0.f; t < Seconds; t += Dt)
			{
				Tick(Dt);
			}
		}
		void Command(const TCHAR* Name, std::initializer_list<TPair<const TCHAR*, FString>> Strs, std::initializer_list<TPair<const TCHAR*, double>> Nums = {})
		{
			TSharedRef<FJsonObject> O = MakeShared<FJsonObject>();
			for (const auto& P : Strs) { O->SetStringField(P.Key, P.Value); }
			for (const auto& N : Nums) { O->SetNumberField(N.Key, N.Value); }
			FString Detail;
			Ship->ApplyCommand(Name, O, Detail);
		}
		void Destroy()
		{
			if (World)
			{
				GEngine->DestroyWorldContext(World);
				World->DestroyWorld(false);
				World = nullptr;
			}
		}
	};

	/** A hit as the war model would give it: a point on the hull's box, a direction, the energy that got through. */
	FAstraHullHit DmMakeHit(FRandomStream& R, float Felt, uint8 Type, int32 Face = -1)
	{
		const double Mid = -7.53, Hx = 399.73, Hy = 69.857, Hz = 46.2;
		// the faces by area: flanks 800 x 92, top and bottom 800 x 140, ends 140 x 92
		const float W[6] = {140.f * 92.f, 140.f * 92.f, 800.f * 92.f, 800.f * 92.f, 800.f * 140.f, 800.f * 140.f};
		float Sum = 0.f;
		for (const float X : W) { Sum += X; }
		int32 F = Face;
		if (F < 0)
		{
			float U = R.FRand() * Sum;
			for (F = 0; F < 5 && U > W[F]; ++F) { U -= W[F]; }
		}
		FVector B(R.FRandRange(-1.f, 1.f), R.FRandRange(-1.f, 1.f), R.FRandRange(-1.f, 1.f));
		FVector N = FVector::ZeroVector;
		switch (F)
		{
		case 0: B.X = 1.f; N = FVector(1, 0, 0); break;
		case 1: B.X = -1.f; N = FVector(-1, 0, 0); break;
		case 2: B.Y = -1.f; N = FVector(0, -1, 0); break;
		case 3: B.Y = 1.f; N = FVector(0, 1, 0); break;
		case 4: B.Z = 1.f; N = FVector(0, 0, 1); break;
		default: B.Z = -1.f; N = FVector(0, 0, -1); break;
		}
		FAstraHullHit H;
		H.Box = B;
		H.HullM = FVector(Mid + B.X * Hx, B.Y * Hy, B.Z * Hz);
		FVector D = (-N + FMath::VRand() * 0.6).GetSafeNormal();
		H.Dir = D;
		H.Facing = F;
		H.Type = Type;
		H.Felt = Felt;
		H.Damage = Felt * 2.f;
		H.StructTook = Felt;
		return H;
	}
}

UAstraDamageSimCommandlet::UAstraDamageSimCommandlet()
{
	IsClient = false;
	IsServer = false;
	IsEditor = true;                 // the editor's plugins assume an editor engine even here (as the war and life benches)
	LogToConsole = true;
	ShowErrorCount = true;
}

int32 UAstraDamageSimCommandlet::Main(const FString& Params)
{
	FString Scenario = TEXT("all"), Set;
	int32 Seed = 1;
	FParse::Value(*Params, TEXT("scenario="), Scenario);
	FParse::Value(*Params, TEXT("seed="), Seed);
	FParse::Value(*Params, TEXT("set="), Set, false);
	FString Out = FPaths::ProjectSavedDir() / TEXT("Damage/run.json");
	FParse::Value(*Params, TEXT("out="), Out);
	FMath::RandInit(Seed);
	FMath::SRandInit(Seed);
	DmChecks.Reset();
	DmSet(Set);
	const bool bAll = Scenario == TEXT("all");
	const double Wall0 = FPlatformTime::Seconds();

	// ======================================================================================================== where the blows go
	if (bAll || Scenario == TEXT("trace"))
	{
		FDmRig Rig;
		if (!Rig.Make(Seed))
		{
			return 1;
		}
		const FAstraDamageMap& Map = *Rig.Map;
		FRandomStream R(Seed);
		const int32 N = 6000;
		int32 Inside = 0, Cells = 0;
		TMap<int32, int32> ByDeck, ByFace, InByFace;
		TMap<FName, int32> ByKind;
		TSet<int32> Distinct;
		TArray<float> Gap;
		for (int32 i = 0; i < N; ++i)
		{
			const FAstraHullHit H = DmMakeHit(R, 30.f, 0);
			FVector At;
			TArray<int32> Comps;
			float E = 0.f;
			++ByFace.FindOrAdd(H.Facing);
			if (Rig.Model.Trace(H, At, Comps, &E))
			{
				++Inside;
				++InByFace.FindOrAdd(H.Facing);
				Cells += Comps.Num();
				++ByDeck.FindOrAdd(Map.Comps[Comps[0]].Deck);
				++ByKind.FindOrAdd(Map.Comps[Comps[0]].Kind);
				Distinct.Add(Comps[0]);
				Gap.Add(E);
			}
		}
		FString FaceText;
		for (int32 f = 0; f < 6; ++f)
		{
			FaceText += FString::Printf(TEXT("%s %d/%d  "), AstraWar::FacingName(f), InByFace.FindRef(f), ByFace.FindRef(f));
		}
		DmCheck(TEXT("blows reach the interior"), Inside > N * 0.55f, FString::Printf(TEXT("%d of %d blows of 30 (any face, any way) reached a compartment (%s)"), Inside, N, *FaceText));
		FString DeckText;
		for (int32 d = 1; d <= 12; ++d)
		{
			DeckText += FString::Printf(TEXT("%d:%d "), d, ByDeck.FindRef(d));
		}
		TArray<TPair<int32, FName>> Kinds;
		for (const auto& KV : ByKind) { Kinds.Add({KV.Value, KV.Key}); }
		Kinds.Sort([](const TPair<int32, FName>& A, const TPair<int32, FName>& B) { return A.Key > B.Key; });
		FString KindText;
		for (int32 i = 0; i < FMath::Min(8, Kinds.Num()); ++i) { KindText += FString::Printf(TEXT("%s %d  "), *Kinds[i].Value.ToString(), Kinds[i].Key); }
		DmCheck(TEXT("blows spread over the ship"), Distinct.Num() > 300 && ByDeck.Num() >= 9, FString::Printf(TEXT("%d different first compartments; by deck %s; by kind %s; mean %.1f compartments crossed"), Distinct.Num(), *DeckText, *KindText,
		                                                                                                  Inside ? (double)Cells / Inside : 0.0));
		Gap.Sort();
		DmCheck(TEXT("the plating takes its share"), Gap.Num() && Gap[Gap.Num() / 2] < 28.f && Gap[Gap.Num() / 2] > 5.f, FString::Printf(TEXT("of 30, what reaches the first room: median %.1f, p10 %.1f, p90 %.1f"),
		                                                                                    Gap.Num() ? Gap[Gap.Num() / 2] : 0.f, Gap.Num() ? Gap[Gap.Num() / 10] : 0.f, Gap.Num() ? Gap[Gap.Num() * 9 / 10] : 0.f));
	}

	// ======================================================================================================== the air
	if (bAll || Scenario == TEXT("air"))
	{
		// a room opened to space with no field: the pressure falls the way the physics says (V / (c A)), the doors lock it in
		{
			DmSet(TEXT("astra.damage.fields=0"));
			FDmRig Rig;
			if (!Rig.Make(Seed))
			{
				return 1;
			}
			const int32 C = Rig.Comp(TEXT("d4_games_D2"));
			FAstraImpactResult Res;
			Rig.Model.Strike(C, 40.f, 0, Rig.Map->Comps[C].Box.GetCenter(), true, Res);
			const float A = Rig.Model.Find(C)->Hole;
			const float V = Rig.Map->Comps[C].VolumeM3;
			const float K = 60.f * A / V;
			Rig.Run(20.f);
			const float P20 = Rig.Air(C);
			Rig.Run(20.f);
			const float P40 = Rig.Air(C);
			DmCheck(TEXT("a room vents as the physics says"), FMath::Abs(P20 - FMath::Exp(-K * 20.f)) < 0.04f && FMath::Abs(P40 - FMath::Exp(-K * 40.f)) < 0.04f,
			        FString::Printf(TEXT("%s, %.0f m3, hole %.2f m2: pressure %.2f after 20 s (expected %.2f) and %.2f after 40 s (expected %.2f)"), *Rig.Map->Comps[C].Name, V, A, P20, FMath::Exp(-K * 20.f), P40, FMath::Exp(-K * 40.f)));
			bool bClosed = true;
			for (const FAstraDmgLink& L : Rig.Map->Comps[C].Links)
			{
				bClosed &= Rig.Air(L.To) > 0.98f;
			}
			DmCheck(TEXT("its doors hold the air in"), bClosed && Rig.Model.Find(C)->bLocked, FString::Printf(TEXT("the rooms and corridors it opens on kept their air (all above 0.98); locked down: %s"), Rig.Model.Find(C)->bLocked ? TEXT("yes") : TEXT("no")));
			DmSet(TEXT("astra.damage.fields=1"));
		}
		// the same room with its field: it holds, strains under another blow, gives way, forms again
		{
			FDmRig Rig;
			if (!Rig.Make(Seed))
			{
				return 1;
			}
			const int32 C = Rig.Comp(TEXT("d4_store_dry_C1"));
			FAstraImpactResult Res;
			Rig.Model.Strike(C, 18.f, 0, Rig.Map->Comps[C].Box.GetCenter(), true, Res);
			Rig.Run(12.f);
			const FAstraDmgState* S = Rig.Model.Find(C);
			const bool bHolding = S && S->Field == FAstraDmgState::EField::Holding;
			DmCheck(TEXT("a containment field holds the hole"), bHolding && Rig.Air(C) > 0.9f, FString::Printf(TEXT("after 12 s: field %s, pressure %.2f (it vented while it formed), the fields cost %.1f %% of the life support"),
			        bHolding ? TEXT("holding") : TEXT("not up"), Rig.Air(C), 100.f * Rig.Model.Power().FieldLoad));
			Rig.Model.Strike(C, 90.f, 0, Rig.Map->Comps[C].Box.GetCenter(), false, Res);          // another blow into the room: the field takes the shock
			Rig.Run(1.f);
			S = Rig.Model.Find(C);
			const bool bFailed = Rig.Model.Books().FieldsFailed >= 1;
			const float Before = Rig.Air(C);
			Rig.Run(4.f);
			const float After = Rig.Air(C);
			DmCheck(TEXT("a field can give way"), bFailed && After < Before, FString::Printf(TEXT("another blow of 90 into the room: fields failed %d; pressure %.3f -> %.3f in the next 4 s (venting again)"), Rig.Model.Books().FieldsFailed, Before, After));
			Rig.Run(12.f);
			S = Rig.Model.Find(C);
			DmCheck(TEXT("and forms again"), S && (S->Field == FAstraDmgState::EField::Holding || S->Field == FAstraDmgState::EField::Forming), FString::Printf(TEXT("12 s later the field is %s"), S && S->Field == FAstraDmgState::EField::Holding ? TEXT("holding again") : TEXT("not up")));
		}
		// a corridor opened to space: the whole section's corridors empty, the pressure bulkheads close behind it, the next section keeps its air
		{
			DmSet(TEXT("astra.damage.fields=0"));
			FDmRig Rig;
			if (!Rig.Make(Seed))
			{
				return 1;
			}
			const int32 C = Rig.Comp(TEXT("d4_spm_D3"));
			FAstraImpactResult Res;
			Rig.Model.Strike(C, 55.f, 0, Rig.Map->Comps[C].Box.GetCenter(), true, Res);
			Rig.Run(10.f);
			{
				FString Dump;
				for (const auto& KV : Rig.Model.States())
				{
					Dump += FString::Printf(TEXT(" %s %.2f"), *Rig.Map->Comps[KV.Key].Id.ToString(), KV.Value.Air);
				}
				UE_LOG(LogASTRA, Display, TEXT("[Damage] after 10 s (hole %.2f):%s"), Rig.Model.Find(C) ? Rig.Model.Find(C)->Hole : -1.f, *Dump);
			}
			Rig.Run(20.f);
			{
				const FAstraDmgState* B = Rig.Model.Find(C);
				UE_LOG(LogASTRA, Display, TEXT("[Damage] after 30 s: breached tract air %.3f hole %.2f field %d locked %d wreck %.2f; sealed %d"), B ? B->Air : -1.f, B ? B->Hole : -1.f, B ? (int32)B->Field : -1, B ? (int32)B->bLocked : -1, B ? B->Wreck : -1.f, Rig.Model.SealedDoors().Num());
			}
			Rig.Run(30.f);
			{
				FString Dump;
				for (const auto& KV : Rig.Model.States())
				{
					Dump += FString::Printf(TEXT(" %s %.2f(%.0f)"), *Rig.Map->Comps[KV.Key].Id.ToString(), KV.Value.Air, Rig.Map->Comps[KV.Key].VolumeM3);
				}
				UE_LOG(LogASTRA, Display, TEXT("[Damage] after 60 s:%s"), *Dump);
			}
			// the section's own corridors, and the neighbours across the bulkheads
			int32 InSec = 0, Across = 0, AcrossFull = 0;
			double SumIn = 0.0;
			for (int32 i = 0; i < Rig.Map->Comps.Num(); ++i)
			{
				const FAstraDmgComp& X = Rig.Map->Comps[i];
				if (X.Deck != 4 || !X.bCorridor)
				{
					continue;
				}
				if (X.Section == TEXT('D'))
				{
					++InSec;
					SumIn += Rig.Air(i);
				}
				else if (X.Section == TEXT('C') || X.Section == TEXT('E'))
				{
					++Across;
					AcrossFull += Rig.Air(i) > 0.97f ? 1 : 0;
				}
			}
			DmCheck(TEXT("the pressure bulkheads close"), Rig.Model.SealedDoors().Num() >= 4, FString::Printf(TEXT("%d pressure bulkheads shut at the section's ends (%s)"), Rig.Model.SealedDoors().Num(), *FString::JoinBy(Rig.SealCalls, TEXT(", "), [](const FName& N) { return N.ToString(); })));
			DmCheck(TEXT("the air stops at the bulkheads"), InSec > 0 && Rig.Air(C) < 0.6f && SumIn / InSec < 0.85 && AcrossFull == Across, FString::Printf(TEXT("after 60 s the breached tract holds %.2f of its air and the corridors of section D %.2f on average (%d tracts); %d of the %d tracts of sections C and E kept all theirs"), Rig.Air(C), InSec ? SumIn / InSec : 1.0, InSec, AcrossFull, Across));
			// the teams work the incidents (the breach first), one after another: the air comes back and the bulkheads open
			bool bBreachDone = false;
			float Worked = 0.f, BreachWork = 0.f, BreachWorked = 0.f;
			for (int32 Guard = 0; Guard < 12 && Rig.Incidents.Num(); ++Guard)
			{
				FAstraDamage* D = Rig.Incidents.FindByPredicate([](const FAstraDamage& X) { return X.Kind == TEXT("hull breach"); });
				if (!D) { D = &Rig.Incidents[0]; }
				const FString Kind = D->Kind;
				const int32 Id = D->Id;
				D->Team = 0;
				D->Work = Rig.Model.WorkSeconds(*D);
				const float Work = D->Work;
				float This = 0.f;
				for (bool bDone = false; This < 150.f && !bDone; This += 0.1f)
				{
					FAstraDamage* Cur = Rig.Incidents.FindByPredicate([Id](const FAstraDamage& X) { return X.Id == Id; });
					if (!Cur) { break; }
					bDone = Rig.Model.Work(*Cur, 0.1f, Rig.Incidents);
					Rig.Model.Tick(0.1f, Rig.Incidents);
					Rig.T += 0.1;
				}
				Worked += This;
				if (Kind == TEXT("hull breach")) { bBreachDone = true; BreachWork = Work; BreachWorked = This; }
			}
			DmCheck(TEXT("a team seals the breach"), bBreachDone && BreachWorked < BreachWork * 1.3f + 1.f, FString::Printf(TEXT("the breach took %.0f s of work (estimated %.0f s); all the incidents of the hit took %.0f s in turn, %d left"), BreachWorked, BreachWork, Worked, Rig.Incidents.Num()));
			Rig.Run(150.f);
			DmCheck(TEXT("the air comes back"), Rig.Air(C) > 0.9f && Rig.Model.SealedDoors().Num() == 0, FString::Printf(TEXT("150 s after the last repair: pressure %.2f in the breached tract, %d bulkheads still shut, %d incidents open"), Rig.Air(C), Rig.Model.SealedDoors().Num(), Rig.Incidents.Num()));
			DmSet(TEXT("astra.damage.fields=1"));
		}
	}

	// ======================================================================================================== the fire
	if (bAll || Scenario == TEXT("fire"))
	{
		{
			DmSet(TEXT("astra.damage.doors=6"));          // doors that stand open (a ship at peace, a door propped): the fire has ways
			FDmRig Rig;
			if (!Rig.Make(Seed))
			{
				return 1;
			}
			Rig.Alert = 0;
			const int32 C = Rig.Comp(TEXT("d4_store_dry_C1"));
			FAstraImpactResult Res;
			Rig.Model.Strike(C, 80.f, 1, Rig.Map->Comps[C].Box.GetCenter(), false, Res);       // a heavy blow: it buckles the room's doors, and the fire has ways
			Rig.Run(10.f);
			{
				FString Dump;
				for (const auto& KV : Rig.Model.States())
				{
					Dump += FString::Printf(TEXT(" %s F%.2f S%.2f W%.2f L%d"), *Rig.Map->Comps[KV.Key].Id.ToString(), KV.Value.Fire, KV.Value.Smoke, KV.Value.Wreck, (int32)KV.Value.bLocked);
				}
				UE_LOG(LogASTRA, Display, TEXT("[Damage] fire test at 10 s:%s; links of the room: %d"), *Dump, Rig.Map->Comps[C].Links.Num());
			}
			Rig.Run(50.f);
			const float F60 = Rig.Model.Find(C) ? Rig.Model.Find(C)->Fire : 0.f;
			Rig.Run(120.f);
			int32 Burning = 0;
			for (const auto& KV : Rig.Model.States())
			{
				Burning += KV.Value.Fire >= 0.1f ? 1 : 0;
			}
			DmCheck(TEXT("a fire grows and spreads"), F60 > 0.4f && Rig.Model.Books().Fires >= 2, FString::Printf(TEXT("%s: fire %.2f after 60 s; %d compartments have caught fire so far, %d burning at 180 s"), *Rig.Map->Comps[C].Name, F60, Rig.Model.Books().Fires, Burning));
			Rig.Run(500.f);
			int32 Still = 0;
			for (const auto& KV : Rig.Model.States())
			{
				Still += KV.Value.Fire >= 0.05f ? 1 : 0;
			}
			DmCheck(TEXT("a fire burns out"), Still == 0, FString::Printf(TEXT("after 680 s with nobody fighting it: %d compartments still burning (it ran out of what there was to burn); %d fires in all"), Still, Rig.Model.Books().Fires));
			DmSet(TEXT("astra.damage.doors=1"));
		}
		{
			FDmRig Rig;
			if (!Rig.Make(Seed))
			{
				return 1;
			}
			Rig.Alert = 2;
			const int32 C = Rig.Comp(TEXT("d4_store_dry_C1"));
			FAstraImpactResult Res;
			Rig.Model.Strike(C, 30.f, 1, Rig.Map->Comps[C].Box.GetCenter(), false, Res);
			Rig.Run(30.f);
			FAstraDamage* D = Rig.Incidents.FindByPredicate([](const FAstraDamage& X) { return X.Kind == TEXT("fire"); });
			bool bDone = false;
			float Worked = 0.f, Work = 0.f;
			if (D)
			{
				D->Team = 1;
				D->Work = Work = Rig.Model.WorkSeconds(*D);
				for (; Worked < 200.f && !bDone; Worked += 0.1f)
				{
					FAstraDamage* Cur = Rig.Incidents.FindByPredicate([](const FAstraDamage& X) { return X.Kind == TEXT("fire"); });
					if (!Cur) { bDone = true; break; }
					bDone = Rig.Model.Work(*Cur, 0.1f, Rig.Incidents);
					Rig.Model.Tick(0.1f, Rig.Incidents);
					Rig.T += 0.1;
					if (FMath::Fmod(Worked, 10.f) < 0.05f)
					{
						const FAstraDmgState* Fs = Rig.Model.Find(C);
						UE_LOG(LogASTRA, Display, TEXT("[Damage]   fire at %.0f s of work: %.3f (team fire %.3f, team t %.1f, fuel %.2f, air %.2f)"), Worked, Fs ? Fs->Fire : -1.f, Fs ? Fs->TeamFire : -1.f, Fs ? Fs->TeamT : -1.f, Fs ? Fs->Fuel : -1.f, Fs ? Fs->Air : -1.f);
					}
				}
			}
			DmCheck(TEXT("a team puts the fire out"), bDone && Worked < Work * 1.3f + 1.f, FString::Printf(TEXT("out after %.0f s of work (estimated %.0f s)"), Worked, Work));
		}
		{
			// a magazine on fire with no power for its suppression goes up; with power, the suppression puts it out
			FDmRig Rig;
			if (!Rig.Make(Seed))
			{
				return 1;
			}
			Rig.Alert = 2;
			int32 Mag = INDEX_NONE;
			for (int32 i = 0; i < Rig.Map->Comps.Num() && Mag == INDEX_NONE; ++i)
			{
				if (Rig.Map->Comps[i].Kind == TEXT("magazine")) { Mag = i; }
			}
			FAstraImpactResult Res;
			Rig.Model.Strike(Mag, 30.f, 1, Rig.Map->Comps[Mag].Box.GetCenter(), false, Res);
			Rig.Run(120.f);
			DmCheck(TEXT("suppression saves a magazine"), Rig.Model.Books().Suppressions >= 1 && Rig.Model.Books().Explosions == 0, FString::Printf(TEXT("%s on fire with power: suppression discharged %d time(s), %d explosions"), *Rig.Map->Comps[Mag].Name, Rig.Model.Books().Suppressions, Rig.Model.Books().Explosions));
			FDmRig Dark;
			Dark.Make(Seed);
			Dark.Alert = 2;
			Dark.Model.Strike(Mag, 70.f, 1, Dark.Map->Comps[Mag].Box.GetCenter(), false, Res);     // a blow that cuts its power and lights it
			Dark.Run(150.f);
			DmCheck(TEXT("without power it goes up"), Dark.Model.Books().Explosions >= 1, FString::Printf(TEXT("a blow of 70 (power %.2f left in it): %d explosion(s), %d wrecked compartments"), Dark.Model.Find(Mag) ? Dark.Model.Find(Mag)->Power : 1.f, Dark.Model.Books().Explosions, Dark.Model.NumWrecked()));
		}
	}

	// ======================================================================================================== the people
	if (bAll || Scenario == TEXT("people"))
	{
		FDmWorld W;
		if (!W.Make())
		{
			return 1;
		}
		FAstraLifeSim& Sim = W.Life->Sim();
		const FAstraLifeMap& LMap = Sim.GetMap();
		W.Command(TEXT("set_alert"), {{TEXT("level"), TEXT("red")}});
		W.Run(240.f, 0.25f);                                   // general quarters: everyone to their battle stations
		// the busiest rooms: who is in them now
		TArray<TPair<int32, int32>> Busy;
		for (int32 c = 0; c < LMap.Comps.Num(); ++c)
		{
			TArray<int32> There;
			Sim.PeopleInComp(c, There);
			if (There.Num() >= 4 && !LMap.Comps[c].bCorridor)
			{
				Busy.Add({There.Num(), c});
			}
		}
		Busy.Sort([](const TPair<int32, int32>& A, const TPair<int32, int32>& B) { return A.Key > B.Key; });
		DmCheck(TEXT("people are at their stations"), Busy.Num() >= 5, FString::Printf(TEXT("%d rooms hold four or more of them (the busiest: %s, %d)"), Busy.Num(), Busy.Num() ? *LMap.Comps[Busy[0].Value].Name : TEXT("-"), Busy.Num() ? Busy[0].Key : 0));
		const FAstraCrewRoster& Roster = W.Ship->GetRoster();
		DmSet(TEXT("astra.damage.fields=0"));
		int32 Hurt = 0, Outside = 0, TotalKilled = 0, TotalWounded = 0, TotalPresent = 0;
		TArray<FString> Notes;
		for (int32 k = 0; k < FMath::Min(3, Busy.Num()); ++k)
		{
			const int32 LC = Busy[k].Value;
			const int32 MC = W.Ship->GetInterior().GetMap().CompByName.FindRef(LMap.Comps[LC].Id, INDEX_NONE);
			if (MC == INDEX_NONE)
			{
				continue;
			}
			TArray<int32> There;
			Sim.PeopleInComp(LC, There);
			TSet<int32> Present;
			for (const int32 P : There) { Present.Add(Sim.Person(P).Roster); }
			int32 Fit0 = 0;
			for (const FAstraCrewman& P : Roster.Get()) { Fit0 += P.Status == 0 ? 1 : 0; }
			FAstraImpactResult Res;
			W.Ship->GetInterior().Strike(MC, 60.f, 0, W.Ship->GetInterior().GetMap().Comps[MC].Box.GetCenter(), true, Res);
			int32 Fit1 = 0;
			for (const FAstraCrewman& P : Roster.Get()) { Fit1 += P.Status == 0 ? 1 : 0; }
			TotalPresent += Present.Num();
			TotalKilled += Res.Killed;
			TotalWounded += Res.Wounded;
			Hurt += Fit0 - Fit1;
			Notes.Add(FString::Printf(TEXT("%s: %d there, a blow of 60 hurt %d (%d killed, %d wounded)"), *LMap.Comps[LC].Name, Present.Num(), Fit0 - Fit1, Res.Killed, Res.Wounded));
			// who the report names must have been in the room
			for (const FString& Who : Res.People)
			{
				bool bFound = false;
				for (const int32 R : Present)
				{
					bFound |= Who.Contains(Roster.Get()[R].Last);
				}
				Outside += bFound ? 0 : 1;
			}
		}
		DmCheck(TEXT("a blow hurts who stood there"), Outside == 0 && TotalPresent > 0, FString::Printf(TEXT("%s; %d people named who were not in the room"), *FString::Join(Notes, TEXT("; ")), Outside));
		DmCheck(TEXT("not a massacre"), Hurt <= TotalPresent * 6 / 10 + 1, FString::Printf(TEXT("%d hurt of %d who were in the three rooms struck (%d killed, %d wounded)"), Hurt, TotalPresent, TotalKilled, TotalWounded));
		// the rooms are open to space (no field): who gets out, who is carried out, who is lost, in the next three minutes
		const int32 Killed0 = Roster.NumKilled();
		W.Run(180.f, 0.25f);
		const FAstraDamageModel::FBooks& B = W.Ship->GetInterior().Books();
		DmCheck(TEXT("the open rooms empty their people"), B.Escaped + B.Rescued + B.Killed > 0, FString::Printf(TEXT("in 180 s: %d got out in time, %d were carried out alive, %d died in vacuum (killed so far %d, wounded %d)"), B.Escaped, B.Rescued, Roster.NumKilled() - Killed0, Roster.NumKilled(), Roster.NumWounded()));
		DmSet(TEXT("astra.damage.fields=1"));
		// the wounded walk to the Medbay (some have a long way: from the Flight Deck or the stern it is minutes by the lifts and stairs)
		auto CountWounded = [&Sim](int32& OutWounded, int32& OutSettled, int32& OutSent)
		{
			OutWounded = OutSettled = OutSent = 0;
			for (int32 i = 0; i < Sim.NumPeople(); ++i)
			{
				const FAstraLifePerson& P = Sim.Person(i);
				if (P.Status == 1)
				{
					++OutWounded;
					OutSent += P.Act == EAstraLifeAct::Patient ? 1 : 0;
					OutSettled += (P.Act == EAstraLifeAct::Patient && P.Phase == FAstraLifePerson::EPhase::Settled) ? 1 : 0;
				}
			}
		};
		W.Run(240.f, 0.25f);
		int32 Wounded = 0, InMedbay = 0, Sent = 0;
		CountWounded(Wounded, InMedbay, Sent);
		DmCheck(TEXT("the wounded reach the Medbay"), Wounded > 0 && Sent == Wounded && InMedbay * 10 >= Wounded * 6,
		        FString::Printf(TEXT("%d wounded, all sent to the Medbay; %d of them are in it 4 game minutes after (the others are on the way: from the Flight Deck or the stern it is minutes by the lifts and stairs)"), Wounded, InMedbay));
		// a section the war has gutted takes who lived in it, and only them
		{
			int32 InStern = 0, Elsewhere = 0;
			TSet<int32> SternRoster;
			for (int32 i = 0; i < Sim.NumPeople(); ++i)
			{
				const FAstraLifePerson& P = Sim.Person(i);
				if (P.Status == 0 && P.Act != EAstraLifeAct::Patient)
				{
					const bool bStern = P.Pos.X < -27700.f && Sim.CompOf(i) != INDEX_NONE && LMap.Comps[Sim.CompOf(i)].Deck >= 2;
					InStern += bStern ? 1 : 0;
					Elsewhere += bStern ? 0 : 1;
					if (bStern) { SternRoster.Add(P.Roster); }
				}
			}
			const int32 K0 = Roster.NumKilled(), Fit0 = Elsewhere;
			FAstraImpactResult R;
			W.Ship->GetInterior().GutSection(-1.0e7f, -27700.f, TEXT("stern"), R);
			int32 StillFitElsewhere = 0;
			for (const FAstraCrewman& P : Roster.Get()) { StillFitElsewhere += P.Status == 0 ? 1 : 0; }
			int32 FitStern = 0;
			for (const int32 Ro : SternRoster) { FitStern += Roster.Get()[Ro].Status == 0 ? 1 : 0; }
			DmCheck(TEXT("a gutted section takes its people"), InStern > 20 && R.Killed >= InStern * 4 / 10 && R.Killed + R.Wounded >= InStern * 6 / 10 && FitStern <= InStern * 5 / 10, FString::Printf(TEXT("%d people were in the stern section: %d killed, %d wounded, %d left fit there; killed in all %d -> %d"), InStern, R.Killed, R.Wounded, FitStern, K0, Roster.NumKilled()));
			(void)Fit0; (void)StillFitElsewhere;
		}
		W.Destroy();
	}

	// ======================================================================================================== the Captain
	if (bAll || Scenario == TEXT("captain"))
	{
		DmSet(TEXT("astra.damage.fields=0"));
		for (int32 Rescue = 0; Rescue < 2; ++Rescue)
		{
			FDmWorld W;
			if (!W.Make())
			{
				return 1;
			}
			W.Command(TEXT("set_alert"), {{TEXT("level"), TEXT("red")}});
			const int32 MC = W.Ship->GetInterior().GetMap().CompByName.FindRef(FName(TEXT("d4_games_D1")), INDEX_NONE);
			const FAstraDmgComp& Room = W.Ship->GetInterior().GetMap().Comps[MC];
			const FVector Feet = Room.Box.GetCenter();
			W.Ship->SetTestCaptain(true, FVector(Room.Box.Min.X + 150.f, Room.Box.Min.Y + 150.f, Room.Box.Min.Z + 90.f));       // at the far end of the room from where the blow comes in
			W.Run(2.f);
			FAstraImpactResult Res;
			W.Ship->GetInterior().Strike(MC, 40.f, 0, Feet, true, Res);
			const float Hole = W.Ship->GetInterior().Find(MC) ? W.Ship->GetInterior().Find(MC)->Hole : 0.f;
			float Impaired = -1.f, Down = -1.f, Dead = -1.f, Woke = -1.f;
			bool bDispatched = false;
			for (float t = 0.f; t < 400.f && Dead < 0.f && Woke < 0.f; t += 0.25f)
			{
				W.Tick(0.25f);
				const FAstraDmgCaptain& C = W.Ship->GetCaptainHealth();
				if (Impaired < 0.f && C.State != FAstraDmgCaptain::EState::Well) { Impaired = t; }
				if (Down < 0.f && C.State == FAstraDmgCaptain::EState::Down) { Down = t; }
				if (Dead < 0.f && C.State == FAstraDmgCaptain::EState::Dead) { Dead = t; }
				if (Down >= 0.f && W.Ship->GetCaptainFate() == 0 && C.State == FAstraDmgCaptain::EState::Well) { Woke = t; }
				if (Rescue == 1 && !bDispatched && t >= 3.f)
				{
					bDispatched = true;                         // ops sends a team at once (the incident is on the board a second after the blow)
					for (const FAstraDamage& D : W.Ship->GetDamage())
					{
						if (D.Kind == TEXT("hull breach"))
						{
							W.Command(TEXT("dispatch_damage_control"), {{TEXT("section"), FString(1, &D.Section)}, {TEXT("priority"), TEXT("critical")}}, {{TEXT("deck"), (double)D.Deck}, {TEXT("id"), (double)D.Id}});
							break;
						}
					}
				}
			}
			if (Rescue == 0)
			{
				DmCheck(TEXT("the Captain faints in thin air"), Impaired > 0.f && Down > Impaired && Down < 90.f, FString::Printf(TEXT("a breach of %.1f m2 into a %.0f m3 room: the sight closes in after %.0f s, the Captain is down after %.0f s"), Hole, Room.VolumeM3, Impaired, Down));
				DmCheck(TEXT("and dies if nobody comes"), Dead > Down + 40.f && Dead < 400.f, FString::Printf(TEXT("dead after %.0f s (%.0f s after falling): %s"), Dead, Dead - Down, *W.Ship->GetInterior().Captain().Why));
			}
			else
			{
				DmCheck(TEXT("a team carries the Captain out"), Down > 0.f && Woke > Down, FString::Printf(TEXT("down after %.0f s; a team sent at once; awake again after %.0f s (dead: %s)"), Down, Woke, Dead >= 0.f ? TEXT("YES") : TEXT("no")));
			}
			W.Destroy();
		}
		DmSet(TEXT("astra.damage.fields=1"));
	}

	// ======================================================================================================== what the Captain sees and the lights
	if (bAll || Scenario == TEXT("fx"))
	{
		FDmRig Rig;
		if (!Rig.Make(Seed))
		{
			return 1;
		}
		const FAstraDamageMap& Map = *Rig.Map;
		FAstraFxBudget Budget;
		FAstraFxPlan Plan;
		// a room with a hole and a fire (a warhead): what the effects ask for with the Captain in it, far from it, and with its deck not in the world
		const int32 C = Rig.Comp(TEXT("d4_games_D2"));
		FAstraImpactResult Res;
		Rig.Model.Strike(C, 70.f, 2, Map.Comps[C].Box.GetCenter(), true, Res);
		Rig.Run(3.f);
		const FBox Box = Map.Comps[C].Box;
		const FVector InRoom = Box.GetCenter() + FVector(0.f, 0.f, 100.f);
		FAstraFxPlanner::Plan(Rig.Model, InRoom, Budget, nullptr, Plan);
		const FAstraDmgState* St = Rig.Model.Find(C);
		const bool bVentFound = Plan.Vents.Num() >= 1 && Plan.Vents[0].Comp == C;
		const float WallGap = bVentFound ? (float)FMath::Sqrt(Box.ComputeSquaredDistanceToPoint(Plan.Vents[0].At)) : 1.0e9f;
		const float Outward = bVentFound ? (float)FVector::DotProduct(Plan.Vents[0].Normal, (Plan.Vents[0].At - Box.GetCenter()).GetSafeNormal()) : -1.f;
		DmCheck(TEXT("the effects find the hole"), bVentFound && WallGap < 1.f && Outward > 0.2f && FMath::Abs(Plan.Vents[0].Normal.Size() - 1.0) < 1e-3,
		        FString::Printf(TEXT("%s: hole %.2f m2, on the wall (%.1f cm off it), normal out of the room (dot %.2f), field %d; fire %.2f -> %d fires in the plan, %d hazes"), *Map.Comps[C].Name,
		                        St ? St->Hole : 0.f, WallGap, Outward, bVentFound ? (int32)Plan.Vents[0].Field : -1, St ? St->Fire : 0.f, Plan.Fires.Num(), Plan.Hazes.Num()));
		DmCheck(TEXT("a fire gets flames"), St && St->Fire >= 0.05f ? Plan.Fires.Num() == 1 && Plan.Fires[0].Comp == C : true, FString::Printf(TEXT("fire %.2f in the room: %d fire sites"), St ? St->Fire : 0.f, Plan.Fires.Num()));
		FAstraFxPlan Far;
		FAstraFxPlanner::Plan(Rig.Model, InRoom + FVector(6000.f, 0.f, 0.f), Budget, nullptr, Far);
		FAstraFxPlan Unloaded;
		FAstraFxPlanner::Plan(Rig.Model, InRoom, Budget, [](const FVector&) { return false; }, Unloaded);
		DmCheck(TEXT("nothing out of reach or unloaded"), Far.Total() == 0 && Unloaded.Total() == 0, FString::Printf(TEXT("the Captain 60 m off: %d effects; his deck not in the world: %d"), Far.Total(), Unloaded.Total()));
		bool bInside = true, bSame = true;
		FAstraFxPlan::FFire Fire;
		Fire.Comp = C;
		Fire.Level = 0.9f;
		Fire.Box = Box;
		Fire.Anchor = Box.GetCenter();
		for (int32 k = 0; k < 3; ++k)
		{
			const FVector P = FAstraFxPlanner::FlameSpot(Fire, k, 3);
			bInside &= Box.IsInsideOrOn(P + FVector(0.f, 0.f, 20.f));
			bSame &= P.Equals(FAstraFxPlanner::FlameSpot(Fire, k, 3), 0.01f);
		}
		DmCheck(TEXT("flames stand in the room, the same each time"), bInside && bSame, FString::Printf(TEXT("three flames at a fire of 0.9: inside %s, repeatable %s"), bInside ? TEXT("yes") : TEXT("NO"), bSame ? TEXT("yes") : TEXT("NO")));
		// a deck full of fire: the budget holds and the nearest come first
		{
			FDmRig Many;
			if (!Many.Make(Seed))
			{
				return 1;
			}
			TArray<int32> Rooms;
			for (int32 i = 0; i < Many.Map->Comps.Num() && Rooms.Num() < 16; ++i)
			{
				const FAstraDmgComp& Cm = Many.Map->Comps[i];
				if (Cm.Deck == 4 && Cm.Status != 0 && !Cm.bCorridor && Cm.VolumeM3 < 400.f)
				{
					Rooms.Add(i);
				}
			}
			for (const int32 R : Rooms)
			{
				FAstraImpactResult R2;
				Many.Model.Strike(R, 60.f, 2, Many.Map->Comps[R].Box.GetCenter(), true, R2);
			}
			Many.Run(4.f);
			FAstraFxBudget Wide;
			Wide.ReachCm = 100000.f;
			FAstraFxPlan Big;
			const double T0 = FPlatformTime::Seconds();
			for (int32 i = 0; i < 400; ++i)
			{
				FAstraFxPlanner::Plan(Many.Model, Many.Map->Comps[Rooms[0]].Box.GetCenter(), Wide, nullptr, Big);
			}
			const double PlanMs = (FPlatformTime::Seconds() - T0) * 1000.0 / 400.0;
			bool bSorted = true;
			for (int32 i = 1; i < Big.Fires.Num(); ++i) { bSorted &= Big.Fires[i - 1].Dist <= Big.Fires[i].Dist; }
			for (int32 i = 1; i < Big.Vents.Num(); ++i) { bSorted &= Big.Vents[i - 1].Dist <= Big.Vents[i].Dist; }
			DmCheck(TEXT("the budget holds"), Big.Fires.Num() <= Wide.Fires && Big.Vents.Num() <= Wide.Vents && Big.Hazes.Num() <= Wide.Hazes + Wide.Mists && Big.Sparks.Num() <= Wide.Sparks && bSorted && Big.Vents.Num() == Wide.Vents,
			        FString::Printf(TEXT("%d rooms struck (%d hazards in the model): %d fires (of %d), %d holes (of %d), %d hazes (of %d), %d spark rooms (of %d), nearest first %s; a plan costs %.4f ms"), Rooms.Num(), Many.Model.NumHazards(),
			                        Big.Fires.Num(), Wide.Fires, Big.Vents.Num(), Wide.Vents, Big.Hazes.Num(), Wide.Hazes, Big.Sparks.Num(), Wide.Sparks, bSorted ? TEXT("yes") : TEXT("NO"), PlanMs));
			DmCheck(TEXT("planning is cheap"), PlanMs < 0.25, FString::Printf(TEXT("%.4f ms for a plan over %d states (it runs four times a second)"), PlanMs, Many.Model.States().Num()));
		}
		// the lights: a room that lost its power burns the red strips, a lost room is dark, a calm one burns as built
		{
			FDmRig L;
			if (!L.Make(Seed))
			{
				return 1;
			}
			const int32 Dark = L.Comp(TEXT("d4_games_D2")), Half = L.Comp(TEXT("d4_games_D1")), Lost = L.Comp(TEXT("d4_store_dry_C1")), Calm = L.Comp(TEXT("d4_spm_D3"));
			FAstraImpactResult R3;
			L.Model.Overload(Dark, 0.95f, R3);
			L.Model.Overload(Half, 0.4f, R3);
			L.Model.Strike(Lost, 600.f, 0, L.Map->Comps[Lost].Box.GetCenter(), false, R3);
			const FAstraDmgLight NoPower = L.Model.LightOf(Dark), Failing = L.Model.LightOf(Half), Gone = L.Model.LightOf(Lost), Whole = L.Model.LightOf(Calm);
			const FAstraDmgState* LS = L.Model.Find(Lost);
			DmCheck(TEXT("the lights follow the damage"), NoPower.Mains < 0.05f && NoPower.Strips > 0.1f && NoPower.Mix > 0.8f && NoPower.Flicker <= 0.f && Failing.Mains > 0.2f && Failing.Mains < 1.f && Failing.Flicker > 0.3f
			        && Whole.Calm() && (LS && LS->Wreck >= 1.f ? Gone.Mains <= 0.f && Gone.Strips <= 0.f : true),
			        FString::Printf(TEXT("no power: mains %.2f, strips %.2f, red %.2f, steady (flicker %.2f); a failing supply (60 %%): mains %.2f, flicker %.2f; a lost room (wreck %.2f): mains %.2f strips %.2f; an untouched one calm: %s"),
			                        NoPower.Mains, NoPower.Strips, NoPower.Mix, NoPower.Flicker, Failing.Mains, Failing.Flicker, LS ? LS->Wreck : 0.f, Gone.Mains, Gone.Strips, Whole.Calm() ? TEXT("yes") : TEXT("NO")));
		}
		// the plan's doors by where they stand (how a door actor of the level is matched to its door)
		{
			int32 Hit = 0, Tried = 0;
			for (int32 i = 0; i < Map.Doors.Num(); i += FMath::Max(1, Map.Doors.Num() / 300))
			{
				++Tried;
				const int32 D = Map.DoorNear(Map.Doors[i].PosCm + FVector(12.f, -9.f, 5.f), 40.f);
				Hit += D != INDEX_NONE && FVector::Dist(Map.Doors[D].PosCm, Map.Doors[i].PosCm + FVector(12.f, -9.f, 5.f)) <= FVector::Dist(Map.Doors[i].PosCm, Map.Doors[i].PosCm + FVector(12.f, -9.f, 5.f)) + 0.01 ? 1 : 0;
			}
			DmCheck(TEXT("doors are found by where they stand"), Hit == Tried && Tried > 100 && Map.DoorNear(FVector(1.0e7f, 0.f, 0.f), 40.f) == INDEX_NONE, FString::Printf(TEXT("%d of %d doors found from 15 cm off; none far away"), Hit, Tried));
		}
	}

	// ======================================================================================================== the effects, made and moved in a world (with the engine's own meshes and material)
	if (bAll || Scenario == TEXT("fxlive"))
	{
		DmSet(TEXT("astra.damage.fields=0"));
		GAstraDamageFxInBench = true;
		FDmWorld W;
		const bool bMade = W.Make();
		GAstraDamageFxInBench = false;
		if (!bMade)
		{
			return 1;
		}
		UAstraDamageFx* Fx = W.World->GetSubsystem<UAstraDamageFx>();
		DmCheck(TEXT("the effects are in the world"), Fx != nullptr, Fx ? TEXT("yes") : TEXT("the subsystem was not made"));
		if (Fx)
		{
			Fx->SetTestAssets(LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Sphere.Sphere")), LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cube.Cube")), UMaterial::GetDefaultMaterial(MD_Surface));
			FAstraDamageModel& In = W.Ship->GetInterior();
			const FAstraDamageMap& Map = In.GetMap();
			const int32 Room = Map.CompByName.FindRef(FName(TEXT("d4_games_D2")), INDEX_NONE), Next = Map.CompByName.FindRef(FName(TEXT("d4_games_D1")), INDEX_NONE);
			const FVector Eye = Map.Comps[Room].Box.GetCenter() + FVector(0.f, 0.f, 100.f);
			Fx->SetTestEye(Eye);
			FAstraImpactResult Res;
			In.Strike(Room, 70.f, 2, Map.Comps[Room].Box.GetCenter(), true, Res);
			In.Strike(Next, 30.f, 1, Map.Comps[Next].Box.GetCenter(), false, Res);
			Fx->OnBlow(Res, 70.f);
			// a deck on fire: every room near him that is built is struck by a warhead (more hazards than the effects can show)
			int32 Struck = 0;
			for (int32 i = 0; i < Map.Comps.Num() && Struck < 12; ++i)
			{
				const FAstraDmgComp& Cm = Map.Comps[i];
				if (i != Room && i != Next && Cm.Deck == 4 && Cm.Status != 0 && !Cm.bCorridor && Cm.Box.ComputeSquaredDistanceToPoint(Eye) < FMath::Square(3000.0))
				{
					FAstraImpactResult R1;
					In.Strike(i, 60.f, 2, Cm.Box.GetCenter(), true, R1);
					++Struck;
				}
			}
			W.Run(10.f, 0.05f);
			UAstraDamageFx::FStats A = Fx->GetStats();
			UE_LOG(LogASTRA, Display, TEXT("[Damage] effects after 10 s (%d rooms struck besides the first two): %s"), Struck, *Fx->Describe());
			DmCheck(TEXT("a burning deck gets its effects"), A.Flames >= 3 && A.Smoke >= 3 && A.Fields + A.Streaks >= 1 && A.Lights >= 1 && A.Scars >= 1, FString::Printf(TEXT("%d flames, %d smoke, %d fields, %d streaks, %d lights, %d scars; %d parts"), A.Flames, A.Smoke, A.Fields, A.Streaks, A.Lights, A.Scars, Fx->NumParts()));
			DmCheck(TEXT("and no more than its budget"), A.Flames <= 12 && A.Smoke + A.Mist <= 20 && A.Fields <= 4 && A.Streaks <= 40 && A.Lights <= 2 && A.Scars <= 3 && A.Flames <= 9, FString::Printf(TEXT("%d flames (3 fires, 3 each at most), %d smoke, %d mist, %d fields, %d streaks, %d lights, %d scars"), A.Flames, A.Smoke, A.Mist, A.Fields, A.Streaks, A.Lights, A.Scars));
			const float Ms = Fx->GetCostMs();
			DmCheck(TEXT("it costs little"), Ms < 0.6f, FString::Printf(TEXT("%.3f ms a frame on average in the game thread with %d parts on (the world is ticked at 20 Hz here, so a frame of the game has half this)"), Ms, Fx->NumParts()));
			// a collection of garbage in the middle of it (a part someone forgot to keep alive would show now), then on
			CollectGarbage(GARBAGE_COLLECTION_KEEPFLAGS);
			W.Run(3.f, 0.05f);
			A = Fx->GetStats();
			DmCheck(TEXT("it goes on after a collection of garbage"), A.Flames + A.Smoke + A.Streaks > 0, FString::Printf(TEXT("3 s later: %d flames, %d smoke, %d streaks; %d parts"), A.Flames, A.Smoke, A.Streaks, Fx->NumParts()));
			W.Run(20.f, 0.05f);
			Fx->SetTestEye(Eye + FVector(8000.f, 0.f, 0.f));
			W.Run(6.f, 0.05f);
			DmCheck(TEXT("it lets go when the Captain is far"), Fx->NumParts() == 0, FString::Printf(TEXT("the Captain 80 m away: %d parts still on"), Fx->NumParts()));
			// the pressure bulkheads and the doors of decks that load late
			W.Ship->ResetInterior();
			Fx->SetTestEye(Eye);
			const int32 Tract = Map.CompByName.FindRef(FName(TEXT("d4_spm_D3")), INDEX_NONE);
			FAstraImpactResult R2;
			In.Strike(Tract, 55.f, 0, Map.Comps[Tract].Box.GetCenter(), true, R2);
			W.Run(15.f, 0.05f);
			TArray<int32> Sealed = In.SealedDoors().Array();
			DmCheck(TEXT("a breached corridor seals its section"), Sealed.Num() >= 2, FString::Printf(TEXT("%d pressure bulkheads shut"), Sealed.Num()));
			if (Sealed.Num() >= 2)
			{
				// a deck streams in after the seal: its doors begin play now (one at a sealed bulkhead, one at a door that is not)
				FActorSpawnParameters SP;
				SP.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
				AAstraDoor* Late = W.World->SpawnActor<AAstraDoor>(Map.Doors[Sealed[0]].PosCm, FRotator(0.f, Map.Doors[Sealed[0]].Yaw, 0.f), SP);
				int32 Plain = INDEX_NONE;
				for (int32 i = 0; i < Map.Doors.Num() && Plain == INDEX_NONE; ++i) { Plain = !Map.Doors[i].bBlast && Map.Doors[i].Deck == 4 ? i : INDEX_NONE; }
				AAstraDoor* Ordinary = W.World->SpawnActor<AAstraDoor>(Map.Doors[Plain].PosCm, FRotator::ZeroRotator, SP);
				for (AAstraDoor* D : {Late, Ordinary})
				{
					if (D && !D->HasActorBegunPlay())
					{
						D->DispatchBeginPlay();                    // (the bench's world does not begin play for what is spawned in it: the streamed-in deck's doors do)
					}
				}
				W.Run(1.f, 0.05f);
				UE_LOG(LogASTRA, Display, TEXT("[Damage] doors: late %s (begun play %d, at %s), loaded %d, plan door %d at %s, near %d, sealed contains %d"), Late ? *Late->GetName() : TEXT("null"), Late ? (int32)Late->HasActorBegunPlay() : -1,
				       Late ? *Late->GetActorLocation().ToString() : TEXT("-"), AstraDoors::Loaded().Num(), Sealed[0], *Map.Doors[Sealed[0]].PosCm.ToString(), Late ? Map.DoorNear(Late->GetActorLocation(), 40.f) : -2, (int32)In.SealedDoors().Contains(Sealed[0]));
				DmCheck(TEXT("a door loaded after the seal is shut"), Late && Late->bLocked && Ordinary && !Ordinary->bLocked && W.Ship->DoorActorOf(Map.Doors[Sealed[0]].Id) == Late,
				        FString::Printf(TEXT("the sealed bulkhead's door: %s; an ordinary door: %s; found by where it stands: %s; signs on: %d"), Late && Late->bLocked ? TEXT("shut") : TEXT("OPEN"), Ordinary && !Ordinary->bLocked ? TEXT("free") : TEXT("LOCKED"),
				                        W.Ship->DoorActorOf(Map.Doors[Sealed[0]].Id) == Late ? TEXT("yes") : TEXT("NO"), Fx->GetStats().Signs));
				const bool bSigned = Fx->GetStats().Signs >= 1;
				W.Ship->ResetInterior();
				W.Run(1.f, 0.05f);
				DmCheck(TEXT("and opens again with the bulkhead"), Late && !Late->bLocked && Fx->GetStats().Signs == 0 && bSigned, FString::Printf(TEXT("after the bulkheads open: the door is %s, signs on %d (it wore one: %s)"), Late && Late->bLocked ? TEXT("STILL SHUT") : TEXT("free"), Fx->GetStats().Signs, bSigned ? TEXT("yes") : TEXT("NO")));
				In.Strike(Tract, 55.f, 0, Map.Comps[Tract].Box.GetCenter(), true, R2);
				W.Run(15.f, 0.05f);
				DmCheck(TEXT("it shuts again when the section is sealed again"), Late && Late->bLocked && Fx->GetStats().Signs >= 1, FString::Printf(TEXT("the door is %s, signs on %d"), Late && Late->bLocked ? TEXT("shut") : TEXT("OPEN"), Fx->GetStats().Signs));
			}
		}
		W.Destroy();
		DmSet(TEXT("astra.damage.fields=1"));
	}

	// ======================================================================================================== the Aquila under the strike group's fire
	if (bAll || Scenario == TEXT("survive"))
	{
		float Seconds = 600.f;
		FParse::Value(*Params, TEXT("seconds="), Seconds);
		FDmWorld W;
		if (!W.Make())
		{
			return 1;
		}
		GEngine->Exec(W.World, TEXT("astra.battle.time 170"));
		W.Battle->StartCampaign();
		W.Command(TEXT("set_alert"), {{TEXT("level"), TEXT("red")}});
		struct FRow { float T, Hull, Shield, Heat, PShield, PWeapon; int32 Incidents, Active, Wrecked, Fields, Sealed, Killed, Wounded; };
		TArray<FRow> Rows;
		float T50 = -1.f, T20 = -1.f, T5 = -1.f, TLost = -1.f;
		bool bTactics = false;
		const double BattleWall0 = FPlatformTime::Seconds();
		const float Step = 0.1f;
		double CostSum = 0.0, CostMax = 0.0;
		int64 CostN = 0;
		for (float t = 0.f; t < Seconds + 15.f; t += Step)
		{
			const float BT = W.Battle->GetBattleTime();
			if (!bTactics && BT >= 185.f)
			{
				bTactics = true;
				W.Command(TEXT("mandate_tactics"), {{TEXT("focus"), TEXT("AQUILA")}, {TEXT("stance"), TEXT("flank")}, {TEXT("missiles"), TEXT("salvo")}, {TEXT("ew"), TEXT("jam")}});
			}
			const double C0 = FPlatformTime::Seconds();
			W.Tick(Step);
			const double C1 = (FPlatformTime::Seconds() - C0) * 1000.0;
			CostSum += C1;
			CostMax = FMath::Max(CostMax, C1);
			++CostN;
			const float Hull = W.Battle->PlayerHullFraction();
			if (T50 < 0.f && Hull <= 0.5f) { T50 = BT - 180.f; }
			if (T20 < 0.f && Hull <= 0.2f) { T20 = BT - 180.f; }
			if (T5 < 0.f && Hull <= 0.05f) { T5 = BT - 180.f; }
			if (TLost < 0.f && W.Ship->IsAbandoning()) { TLost = BT - 180.f; }
			if (FMath::Fmod(BT, 10.f) < Step * 0.5f && (Rows.Num() == 0 || BT - Rows.Last().T >= 9.9f))
			{
				const FAstraDamageModel& I = W.Ship->GetInterior();
				Rows.Add({BT, Hull, W.Battle->PlayerShieldFraction(), W.Ship->GetHeatPct(), W.Ship->PowerFactor(TEXT("shields")), W.Ship->PowerFactor(TEXT("weapons")), W.Ship->GetDamage().Num(),
				          I.States().Num(), I.NumWrecked(), I.Power().Fields, I.SealedDoors().Num(), W.Ship->GetRoster().NumKilled(), W.Ship->GetRoster().NumWounded()});
			}
			if (BT - 180.f > Seconds || W.Ship->IsShipLost())
			{
				break;
			}
		}
		const FAstraDamageModel& I = W.Ship->GetInterior();
		const FAstraDamageModel::FBooks& B = I.Books();
		for (const FRow& R : Rows)
		{
			UE_LOG(LogASTRA, Display, TEXT("[Damage] t=%5.0f hull %3.0f%% shields %3.0f%% heat %3.0f%% | power shields %.2f weapons %.2f | incidents %2d, %3d compartments in play (%d gutted), %d fields, %d bulkheads shut | killed %d wounded %d"),
			       R.T, 100.f * R.Hull, 100.f * R.Shield, R.Heat, R.PShield, R.PWeapon, R.Incidents, R.Active, R.Wrecked, R.Fields, R.Sealed, R.Killed, R.Wounded);
		}
		UE_LOG(LogASTRA, Display, TEXT("[Damage] survival after the group's arrival (t=180): hull <= 50%% at %.0f s, <= 20%% at %.0f s, <= 5%% at %.0f s, abandon ship at %.0f s (-1: not reached)"), T50, T20, T5, TLost);
		UE_LOG(LogASTRA, Display, TEXT("[Damage] books: %d blows (%d reached the interior, %.0f energy of %.0f), %d holes, %d fires, %d conduits, %d gutted, %d fields failed, %d bulkheads sealed, %d explosions, %d suppressions; %d killed, %d wounded, %d got out, %d carried out; structure burnt %.0f; most compartments in play %d, most incidents %d"),
		       B.Hits, B.HitsInside, B.EnergyInside, B.Energy, B.Holes, B.Fires, B.Conduits, B.Wrecks, B.FieldsFailed, B.DoorsSealed, B.Explosions, B.Suppressions, B.Killed, B.Wounded, B.Escaped, B.Rescued, B.StructureBurnt, B.MaxActive, B.MaxIncidents);
		{
			// what is still in the books at the end: small holes, partial wrecks, lost power (what the teams do not have an incident for)
			int32 Small = 0, BigHole = 0, Partial = 0, Lost = 0, Dim = 0, Smoky = 0, Locked = 0, Other = 0;
			for (const auto& KV : I.States())
			{
				const FAstraDmgState& S = KV.Value;
				Small += (S.Hole >= 0.005f && S.Hole < 0.12f) ? 1 : 0;
				BigHole += S.Hole >= 0.12f ? 1 : 0;
				Partial += (S.Wreck > 0.005f && S.Wreck < 1.f) ? 1 : 0;
				Lost += S.Wreck >= 1.f ? 1 : 0;
				Dim += S.Power < 0.995f ? 1 : 0;
				Smoky += (S.Smoke >= 0.02f || S.Fire >= 0.02f) ? 1 : 0;
				Locked += S.bLocked ? 1 : 0;
				Other += (S.People.Num() > 0 || S.Air < 0.995f) ? 1 : 0;
			}
			UE_LOG(LogASTRA, Display, TEXT("[Damage] left in the books: %s | small holes %d, big holes %d, partial wrecks %d, lost %d, short of power %d, smoke or fire %d, locked down %d, short of air or with people exposed %d"), *I.InfoText(), Small, BigHole, Partial, Lost, Dim, Smoky, Locked, Other);
		}
		UE_LOG(LogASTRA, Display, TEXT("[Damage] people: %d of the %d blows that reached the interior crossed a room with someone in it; %d people were in the rooms they crossed"), B.OccupiedBlows, B.HitsInside, B.PeopleNear);
		TSharedRef<FJsonObject> Sv = MakeShared<FJsonObject>();
		float ModelAvg = 0.f, ModelMax = 0.f;
		W.Ship->InteriorCost(ModelAvg, ModelMax);
		UE_LOG(LogASTRA, Display, TEXT("[Damage] cost: the whole world tick %.3f ms on average, %.1f ms at worst (%lld ticks, %.0f s of battle in %.0f s); the damage model's own tick (the physics steps at 5 Hz, the teams, the screens' list) %.3f ms on average, %.2f ms at worst"), CostN ? CostSum / CostN : 0.0, CostMax, CostN, W.Battle->GetBattleTime() - 170.f, FPlatformTime::Seconds() - BattleWall0, ModelAvg, ModelMax);
		Sv->SetNumberField(TEXT("model_ms"), ModelAvg);
		Sv->SetNumberField(TEXT("model_ms_max"), ModelMax);
		Sv->SetNumberField(TEXT("t_hull_50"), T50);
		Sv->SetNumberField(TEXT("t_hull_20"), T20);
		Sv->SetNumberField(TEXT("t_hull_5"), T5);
		Sv->SetNumberField(TEXT("t_abandon"), TLost);
		Sv->SetNumberField(TEXT("hits"), B.Hits);
		Sv->SetNumberField(TEXT("hits_inside"), B.HitsInside);
		Sv->SetNumberField(TEXT("holes"), B.Holes);
		Sv->SetNumberField(TEXT("fires"), B.Fires);
		Sv->SetNumberField(TEXT("killed"), W.Ship->GetRoster().NumKilled());
		Sv->SetNumberField(TEXT("wounded_now"), W.Ship->GetRoster().NumWounded());
		Sv->SetNumberField(TEXT("max_active"), B.MaxActive);
		Sv->SetNumberField(TEXT("max_incidents"), B.MaxIncidents);
		Sv->SetNumberField(TEXT("hull_end"), 100.0 * W.Battle->PlayerHullFraction());
		Sv->SetNumberField(TEXT("occupied_blows"), B.OccupiedBlows);
		Sv->SetNumberField(TEXT("people_near"), B.PeopleNear);
		Sv->SetNumberField(TEXT("wounded_total"), B.Wounded);
		Sv->SetNumberField(TEXT("killed_total"), B.Killed);
		Sv->SetNumberField(TEXT("tick_ms"), CostN ? CostSum / CostN : 0.0);
		DmRecord->SetObjectField(TEXT("survive"), Sv);
		TArray<TSharedPtr<FJsonValue>> Ev;
		for (const FString& R : W.Reports) { Ev.Add(MakeShared<FJsonValueString>(R)); }
		DmRecord->SetArrayField(TEXT("reports"), Ev);
		DmCheck(TEXT("the Aquila lasts"), T5 < 0.f || T5 >= 270.f, FString::Printf(TEXT("under the group's focused fire: half the hull at %.0f s, a fifth at %.0f s, a twentieth at %.0f s after its arrival"), T50, T20, T5));
		W.Destroy();
	}

	int32 NumFailed = 0;
	for (const FDmCheck& C : DmChecks) { NumFailed += C.bPass ? 0 : 1; }
	const double Wall = FPlatformTime::Seconds() - Wall0;
	UE_LOG(LogASTRA, Display, TEXT("[Damage] %d checks, %d failed, %.1f s"), DmChecks.Num(), NumFailed, Wall);
	UE_LOG(LogASTRA, Display, TEXT("[Damage] VERDICT: %s"), NumFailed == 0 ? TEXT("PASS") : TEXT("FAIL"));
	TArray<TSharedPtr<FJsonValue>> Cs;
	for (const FDmCheck& C : DmChecks)
	{
		TSharedRef<FJsonObject> O = MakeShared<FJsonObject>();
		O->SetStringField(TEXT("name"), C.Name);
		O->SetBoolField(TEXT("pass"), C.bPass);
		O->SetStringField(TEXT("detail"), C.Detail);
		Cs.Add(MakeShared<FJsonValueObject>(O));
	}
	DmRecord->SetStringField(TEXT("verdict"), NumFailed == 0 ? TEXT("PASS") : TEXT("FAIL"));
	DmRecord->SetArrayField(TEXT("checks"), Cs);
	FString Json;
	const TSharedRef<TJsonWriter<>> W = TJsonWriterFactory<>::Create(&Json);
	FJsonSerializer::Serialize(DmRecord, W);
	IFileManager::Get().MakeDirectory(*FPaths::GetPath(Out), true);
	FFileHelper::SaveStringToFile(Json, *Out, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
	return NumFailed == 0 ? 0 : 1;
}
