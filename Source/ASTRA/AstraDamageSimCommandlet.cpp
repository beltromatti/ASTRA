#include "AstraDamageSimCommandlet.h"

#include "ASTRA.h"
#include "AstraDamageMap.h"
#include "AstraDamageModel.h"
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
			if (!Map->Load(Err))
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
