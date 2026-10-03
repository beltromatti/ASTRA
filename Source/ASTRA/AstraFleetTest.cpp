// ASTRA — FLOTTA-VIVA: the checks of the insides of the other ships, on every class's plan, with no battle and no world (tools/fleet.py check, docs/FLOTTA-VIVA.md).
//
// For each class of data/war/classes.json that is not the Aquila's: its plan loads and agrees with the class (the mounts have their rooms, the garrison is the crew), an inside is
// made of it with the people it says, the officers, the damage parties; a barrage of blows is struck into its rooms and the model runs on for minutes of battle: the counts stay
// whole (every person is fit, wounded, dead or lost), what comes out stays in its range, nothing is not a number, every view builds; a section is gutted and its rooms and people
// are lost, and only those; the same seed and the same blows give the same books; and what it all costs is told.

#include "AstraFleetInterior.h"

#include "ASTRA.h"
#include "AstraWarClasses.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"

namespace
{
	struct FChecks
	{
		TArray<FString>& Out;
		int32 Passed = 0, Failed = 0;
		explicit FChecks(TArray<FString>& InOut) : Out(InOut) {}
		void Check(bool bOk, const FString& Name, const FString& Detail)
		{
			(bOk ? Passed : Failed) += 1;
			Out.Add(FString::Printf(TEXT("%s %s: %s"), bOk ? TEXT("PASS") : TEXT("FAIL"), *Name, *Detail));
		}
	};

	FString JsonText(const TSharedRef<FJsonObject>& J)
	{
		FString S;
		const TSharedRef<TJsonWriter<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>> W = TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&S);
		FJsonSerializer::Serialize(J, W);
		return S;
	}

	/** The people's three states and the ones lost with the ship add up to the crew. */
	bool CountsWhole(const FAstraShipInterior& I)
	{
		return I.CrewFit() + I.CrewWounded() + I.CrewDead() + I.CrewLostWithShip() == I.CrewTotal();
	}

	bool AllFinite(const FAstraShipInterior& I)
	{
		for (int32 c = 0; c < 6; ++c)
		{
			const float F = I.Factor((EAstraDmgCategory)c);
			if (!FMath::IsFinite(F) || F < 0.f || F > 1.001f)
			{
				return false;
			}
		}
		for (int32 s = 0; s < 6; ++s)
		{
			const float F = I.SysFit(s);
			if (!FMath::IsFinite(F) || F < 0.f || F > 1.001f)
			{
				return false;
			}
		}
		const float W = I.WeaponCrew();
		return FMath::IsFinite(W) && W >= 0.39f && W <= 1.001f && FMath::IsFinite(I.CrewStrength());
	}

	/** The same blows into the same rooms, on a ship of a fixed seed: the books it keeps as text. */
	FString BarrageBooks(const TSharedRef<const FFleetClassPlan>& Plan, int32 Seed, int32 Blows, float Energy, double* OutBuildMs, double* OutTickMs)
	{
		const double T0 = FPlatformTime::Seconds();
		FAstraShipInterior I(Plan, 1, TEXT("Test"), Seed);
		const double T1 = FPlatformTime::Seconds();
		FRandomStream R(Seed + 17);
		const int32 N = Plan->Map->Comps.Num();
		for (int32 b = 0; b < Blows; ++b)
		{
			I.Strike(R.RandRange(0, N - 1), Energy, (uint8)R.RandRange(0, 2), b % 3 == 0);
		}
		const double T2 = FPlatformTime::Seconds();
		for (int32 t = 0; t < 1800; ++t)                       // three minutes of battle at the commandlet's 0.1 s
		{
			I.Tick(0.1f);
		}
		const double T3 = FPlatformTime::Seconds();
		if (OutBuildMs) { *OutBuildMs = (T1 - T0) * 1000.0; }
		if (OutTickMs) { *OutTickMs = (T3 - T2) * 1000.0 / 1800.0; }
		return JsonText(I.BooksJson());
	}
}

int32 AstraFleetSelfTest(TArray<FString>& Lines)
{
	FChecks C(Lines);
	AstraWar::EnsureClassesLoaded();
	TArray<FName> Keys;
	AstraWar::ClassKeys(Keys);
	for (const FName& Key : Keys)
	{
		if (Key == FName(TEXT("aquila")))
		{
			continue;                                          // (her inside is the ship's own: DISTRUZIONE)
		}
		const AstraWar::FShipClass* Cls = AstraWar::FindClass(Key);
		const FString K = Key.ToString();
		const TSharedPtr<const FFleetClassPlan> PlanP = FAstraFleetPlans::Find(Key, true);
		C.Check(PlanP.IsValid(), K + " plan", PlanP.IsValid() ? FString::Printf(TEXT("%d rooms, %d doors, crew %d, %d billets, %d parties, %d docks"), PlanP->Map->Comps.Num(), PlanP->Map->Doors.Num(), PlanP->Complement, PlanP->Billets.Num(), PlanP->Parties.Num(), PlanP->Docks.Num()) : TEXT("no plan file: its ships have no inside"));
		if (!PlanP.IsValid() || !Cls)
		{
			continue;
		}
		const TSharedRef<const FFleetClassPlan> Plan = PlanP.ToSharedRef();
		// the plan and the class
		int32 GarrisonSum = 0;
		bool bGarrisonRooms = true;
		for (const FFleetGarrison& G : Plan->Garrison)
		{
			GarrisonSum += G.N;
			bGarrisonRooms &= Plan->Map->Comps.IsValidIndex(G.Comp);
		}
		C.Check(Plan->Complement > 0 && GarrisonSum == Plan->Complement && bGarrisonRooms, K + " garrison", FString::Printf(TEXT("%d posted of a crew of %d"), GarrisonSum, Plan->Complement));
		int32 MountsWithRoom = 0;
		for (const int32 M : Plan->MountComp)
		{
			MountsWithRoom += Plan->Map->Comps.IsValidIndex(M) ? 1 : 0;
		}
		C.Check(Plan->MountComp.Num() == Cls->Mounts.Num() && MountsWithRoom == Cls->Mounts.Num(), K + " mounts", FString::Printf(TEXT("%d of the class's %d weapons have the room that serves them"), MountsWithRoom, Cls->Mounts.Num()));
		const FBox& Hull = Plan->Map->Hull;
		const AstraWar::FHullBox& Box = Cls->Box;
		const bool bFits = Box.Valid() ? (Hull.GetExtent().X * 2.0 / 100.0 <= 2.0 * Box.Hx * 1.05 && Hull.GetExtent().Y * 2.0 / 100.0 <= 2.0 * Box.Hy * 1.15) : true;
		C.Check(bFits, K + " inside the hull", FString::Printf(TEXT("the plan is %.0f x %.0f m, the war's box %.0f x %.0f m"), Hull.GetExtent().X * 2.0 / 100.0, Hull.GetExtent().Y * 2.0 / 100.0, Box.Hx * 2.0, Box.Hy * 2.0));
		// an inside
		double BuildMs = 0.0, TickMs = 0.0;
		FAstraShipInterior I(Plan, 1, TEXT("Test ship"), 7001);
		C.Check(I.CrewTotal() >= Plan->Complement && I.CrewTotal() <= Plan->Complement + 8 && I.CrewFit() == I.CrewTotal() && CountsWhole(I), K + " crew", FString::Printf(TEXT("%d aboard, all fit"), I.CrewTotal()));
		bool bNamed = I.GetNamed().Num() == Plan->Billets.Num();
		for (const FFleetNamed& N : I.GetNamed())
		{
			bNamed &= I.GetPeople().IsValidIndex(N.Person) && I.GetPeople()[N.Person].State == 0 && !N.Name.IsEmpty();
		}
		C.Check(bNamed && (Plan->Billets.Num() == 0 || I.Commander() != nullptr), K + " officers", FString::Printf(TEXT("%d named, %s has the conn"), I.GetNamed().Num(), I.Commander() ? *I.Commander()->Name : TEXT("nobody")));
		bool bParties = I.PartiesCount() == Plan->Parties.Num();
		for (int32 p = 0; p < I.PartiesCount(); ++p)
		{
			bParties &= I.PartyMembersNow(p) >= 1 && Plan->Parties[p].TravelS.Num() == Plan->Map->Comps.Num();
		}
		C.Check(bParties, K + " damage parties", FString::Printf(TEXT("%d parties, %d hands in them"), I.PartiesCount(), [&I]() { int32 S = 0; for (int32 p = 0; p < I.PartiesCount(); ++p) { S += I.PartyMembersNow(p); } return S; }()));
		// every room of the plan is reached by some party in a time that means something
		float WorstS = 0.f;
		int32 Unreached = 0;
		for (int32 c = 0; c < Plan->Map->Comps.Num(); ++c)
		{
			float Best = 1.0e8f;
			for (const FFleetParty& P : Plan->Parties)
			{
				Best = FMath::Min(Best, P.TravelS.IsValidIndex(c) ? P.TravelS[c] : 1.0e8f);
			}
			if (Best >= 1.0e3f)
			{
				++Unreached;
			}
			else
			{
				WorstS = FMath::Max(WorstS, Best);
			}
		}
		C.Check(Unreached == 0 || Plan->Parties.Num() == 0, K + " party reach", FString::Printf(TEXT("%d rooms out of reach of every party; the farthest of the others %.0f s from the nearest"), Unreached, WorstS));
		// the views of a ship that has not been hit
		C.Check(I.BriefJson()->Values.Num() == 0 && I.SeenJson(2)->Values.Num() == 0, K + " calm views", TEXT("a ship not hit says nothing of her inside"));
		// a barrage, minutes of battle
		FRandomStream R(11);
		const int32 N = Plan->Map->Comps.Num();
		for (int32 b = 0; b < 60; ++b)
		{
			I.Strike(R.RandRange(0, N - 1), 60.f + 80.f * R.FRand(), (uint8)R.RandRange(0, 2), b % 4 == 0);
		}
		const double T0 = FPlatformTime::Seconds();
		bool bWhole = true, bFinite = true;
		for (int32 t = 0; t < 2400; ++t)                       // four minutes at 0.1 s
		{
			I.Tick(0.1f);
			if ((t % 100) == 0)
			{
				bWhole &= CountsWhole(I);
				bFinite &= AllFinite(I);
			}
		}
		TickMs = (FPlatformTime::Seconds() - T0) * 1000.0 / 2400.0;
		C.Check(bWhole && bFinite, K + " under fire", FString::Printf(TEXT("after 60 blows and 4 minutes: %d fit, %d wounded, %d dead of %d; %d fires, %d breaches, %d dark rooms; power shields %.2f weapons %.2f engines %.2f; weapons crew %.2f"),
		                                                                   I.CrewFit(), I.CrewWounded(), I.CrewDead(), I.CrewTotal(), I.Fires(), I.Breaches(), I.DarkRooms(), I.Factor(EAstraDmgCategory::Shields), I.Factor(EAstraDmgCategory::Weapons), I.Factor(EAstraDmgCategory::Engines), I.WeaponCrew()));
		C.Check(I.CrewDead() + I.CrewWounded() > 0, K + " the people are hurt", FString::Printf(TEXT("%d dead, %d wounded: the blows were struck where people stand"), I.CrewDead(), I.CrewWounded()));
		// every view builds, with the sense it should have
		const TSharedRef<FJsonObject> Brief = I.BriefJson();
		const TSharedRef<FJsonObject> Seen = I.SeenJson(2);
		FAstraFleetView View;
		I.FillView(View, 3);
		FFleetSnapshot Snap;
		I.Snapshot(Snap);
		FFleetFxPoints Fx;
		I.FxPoints(Fx);
		const FString Books = JsonText(I.BooksJson());
		C.Check(Brief->Values.Num() > 0 && Seen->Values.Num() > 0 && View.CrewTotal == I.CrewTotal() && Snap.Rooms.Num() > 0 && Snap.Hands.Num() == I.CrewFit() + I.CrewWounded() && FMath::IsFinite(Fx.Lit) && !Books.IsEmpty(),
		        K + " views", FString::Printf(TEXT("aboard %d keys, seen %d, snapshot %d rooms and %d hands, %d fire points, lit %.2f"), Brief->Values.Num(), Seen->Values.Num(), Snap.Rooms.Num(), Snap.Hands.Num(), Fx.Fire[0].Num() + Fx.Fire[1].Num() + Fx.Fire[2].Num(), Fx.Lit));
		TArray<FString> News1, News2;
		I.CollectNews(News1);
		I.CollectNews(News2);
		C.Check(News2.Num() == 0, K + " news", FString::Printf(TEXT("%d things to tell the war, each told once (the second asking: %d)"), News1.Num(), News2.Num()));
		// a section gutted: its rooms are lost, and the people in them; the rest is not
		FAstraShipInterior G(Plan, 2, TEXT("Gutted"), 7002);
		G.GutSection(0);
		int32 LostBow = 0, TotalBow = 0, LostElse = 0;
		for (int32 c = 0; c < N; ++c)
		{
			const FAstraDmgState* S = G.GetModel().Find(c);
			const bool bLost = S && (S->bGutted || S->Wreck >= 1.f);
			const float X = (float)Plan->Map->Comps[c].Box.GetCenter().X;
			const bool bBow = (Plan->CutBowCm != 0.f || Plan->CutSternCm != 0.f) ? X > Plan->CutBowCm : (X - (float)Plan->Map->Hull.Min.X) / FMath::Max(1.f, (float)(Plan->Map->Hull.Max.X - Plan->Map->Hull.Min.X)) > 0.66f;
			if (bBow)
			{
				++TotalBow;
				LostBow += bLost ? 1 : 0;
			}
			else
			{
				LostElse += bLost ? 1 : 0;
			}
		}
		const bool bOnlyBow = TotalBow > 0 && LostBow >= TotalBow * 0.95f && LostElse == 0;
		C.Check(bOnlyBow, K + " a section gutted", FString::Printf(TEXT("bow: %d of %d rooms lost; elsewhere %d; %d people killed"), LostBow, TotalBow, LostElse, G.CrewDead()));
		// the ship goes: everyone aboard is lost with her
		const int32 Aboard = I.CrewFit() + I.CrewWounded();
		const int32 Lost = I.LoseWithShip();
		C.Check(Lost == Aboard && I.CrewFit() == 0 && I.CrewWounded() == 0 && CountsWhole(I) && I.LoseWithShip() == 0, K + " lost with the ship", FString::Printf(TEXT("%d lost with her, none twice"), Lost));
		// deterministic: the same seed and the same blows, the same books; and the cost
		const FString A = BarrageBooks(Plan, 4242, 40, 90.f, &BuildMs, nullptr);
		const FString B = BarrageBooks(Plan, 4242, 40, 90.f, nullptr, &TickMs);
		C.Check(A == B && !A.IsEmpty(), K + " deterministic", TEXT("the same seed and the same blows give the same books"));
		C.Check(BuildMs < 50.0 && TickMs < 5.0, K + " cost", FString::Printf(TEXT("built in %.2f ms; %.3f ms a tick of 0.1 s while burning (a quarter of the rooms active at most)"), BuildMs, TickMs));
	}
	Lines.Add(FString::Printf(TEXT("VERDICT: %s (%d checks, %d failed)"), C.Failed == 0 ? TEXT("PASS") : TEXT("FAIL"), C.Passed + C.Failed, C.Failed));
	return C.Failed;
}
