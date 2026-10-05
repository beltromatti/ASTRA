#include "AstraBoardPlans.h"

#include "ASTRA.h"
#include "AstraBoardDress.h"
#include "AstraFleetPlan.h"
#include "Dom/JsonObject.h"
#include "HAL/FileManager.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Misc/ScopeLock.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

namespace
{
	FCriticalSection BpLock;
	TMap<FName, TSharedPtr<FBoardShipPlan>> BpCache;

	FVector BpMetres(const TArray<TSharedPtr<FJsonValue>>* A)
	{
		return A && A->Num() >= 3 ? FVector((*A)[0]->AsNumber(), (*A)[1]->AsNumber(), (*A)[2]->AsNumber()) * 100.0 : FVector::ZeroVector;
	}

	FVector BpUnit(const TArray<TSharedPtr<FJsonValue>>* A)
	{
		return A && A->Num() >= 3 ? FVector((*A)[0]->AsNumber(), (*A)[1]->AsNumber(), (*A)[2]->AsNumber()) : FVector::ZeroVector;
	}
}

int32 FBoardShipPlan::Objective(const TCHAR* Name, const TCHAR* Kind) const
{
	if (const int32* C = Objectives.Find(FName(Name)); C && Has(*C))
	{
		return *C;
	}
	if (Dmg.IsValid() && Kind && *Kind)
	{
		const FName K(Kind);
		for (int32 i = 0; i < Dmg->Comps.Num(); ++i)
		{
			if (Dmg->Comps[i].Kind == K && Has(i))
			{
				return i;
			}
		}
	}
	return INDEX_NONE;
}

int32 FBoardShipPlan::NumRooms() const
{
	if (Present.IsEmpty())
	{
		return Dmg.IsValid() ? Dmg->Comps.Num() : 0;
	}
	int32 N = 0;
	for (const uint8 P : Present)
	{
		N += P ? 1 : 0;
	}
	return N;
}

bool FBoardShipPlan::AtTornEnd(int32 Comp, float MarginCm) const
{
	if (Section > 2 || !Dmg.IsValid() || !Dmg->Comps.IsValidIndex(Comp) || !Dmg->Comps[Comp].Box.IsValid)
	{
		return false;
	}
	float Bow = CutBowCm, Stern = CutSternCm;
	if (Bow == 0.f && Stern == 0.f)
	{
		const FBox& H = Dmg->Hull;
		const float L = (float)(H.Max.X - H.Min.X);
		Bow = (float)H.Min.X + 0.66f * L;
		Stern = (float)H.Min.X + 0.33f * L;
	}
	const FBox& B = Dmg->Comps[Comp].Box;
	switch (Section)
	{
	case 0: return B.Min.X <= Bow + MarginCm;                                       // (the bow piece: her aft end is torn)
	case 1: return B.Max.X >= Bow - MarginCm || B.Min.X <= Stern + MarginCm;         // (the middle: both)
	default: return B.Max.X >= Stern - MarginCm;                                     // (the stern: her forward end)
	}
}

uint8 FBoardShipPlan::SectionOf(int32 Comp) const
{
	if (!Dmg.IsValid() || !Dmg->Comps.IsValidIndex(Comp))
	{
		return 255;
	}
	const float X = (float)Dmg->Comps[Comp].Box.GetCenter().X;
	if (CutBowCm == 0.f && CutSternCm == 0.f)
	{
		const FBox& B = Dmg->Hull;
		const float T = (X - (float)B.Min.X) / FMath::Max(1.f, (float)(B.Max.X - B.Min.X));
		return T > 0.66f ? 0 : (T < 0.33f ? 2 : 1);
	}
	return X > CutBowCm ? 0 : (X < CutSternCm ? 2 : 1);
}

int32 FBoardShipPlan::NearestDock(const FVector& HullM) const
{
	int32 Best = INDEX_NONE;
	double BestD = 1.0e18;
	for (int32 i = 0; i < Docks.Num(); ++i)
	{
		const double D = FVector::DistSquared(PlanToHullM(Docks[i].Pos), HullM);
		if (D < BestD)
		{
			BestD = D;
			Best = i;
		}
	}
	return Best;
}

FString AstraBoardPlans::PathFor(FName ClassKey)
{
	const FString K = ClassKey.ToString().ToLower();
	if (K == TEXT("aquila"))
	{
		const FString Staged = FPaths::Combine(FPaths::ProjectContentDir(), TEXT("ASTRA/Data/aquila_plan.json"));
		return FPaths::FileExists(Staged) ? Staged : FPaths::Combine(FPaths::ProjectDir(), TEXT("data/ship/aquila_plan.json"));
	}
	return FAstraFleetPlans::PathFor(FName(*K));
}

TSharedPtr<FBoardShipPlan> AstraBoardPlans::LoadFile(const FString& Path, FName ClassKey, FString& OutWhy)
{
	const double T0 = FPlatformTime::Seconds();
	TSharedRef<FBoardShipPlan> P = MakeShared<FBoardShipPlan>();
	P->Class = ClassKey;
	P->Path = Path;
	P->Dmg = MakeShared<FAstraDamageMap>();
	if (!P->Dmg->Load(Path, OutWhy))
	{
		return nullptr;
	}
	P->Map = MakeShared<FAstraBoardMap>();
	if (!P->Map->Build(P->Dmg.ToSharedRef()))
	{
		OutWhy = TEXT("the plan has no compartments");
		return nullptr;
	}
	// what only boarding reads of the file
	FString Text;
	TSharedPtr<FJsonObject> Plan;
	if (FFileHelper::LoadFileToString(Text, *Path) && FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Plan) && Plan.IsValid())
	{
		Plan->TryGetStringField(TEXT("label"), P->Label);
		Plan->TryGetStringField(TEXT("style"), P->Style);
		// the class's cut planes (hull metres, the war's bow, middle and stern sections are what lies beyond them), in the plan's frame: FLOTTA-VIVA's reading of the same file
		const TSharedPtr<FJsonObject>* Hull = nullptr;
		if (Plan->TryGetObjectField(TEXT("hull"), Hull))
		{
			const TArray<TSharedPtr<FJsonValue>>* Cuts = nullptr;
			if ((*Hull)->TryGetArrayField(TEXT("cuts_x"), Cuts) && Cuts->Num() >= 2)
			{
				P->CutBowCm = (float)(((*Cuts)[0]->AsNumber() - P->Dmg->OriginInHullM.X) * 100.0);
				P->CutSternCm = (float)(((*Cuts)[1]->AsNumber() - P->Dmg->OriginInHullM.X) * 100.0);
			}
		}
		double Crew = 0.0;
		Plan->TryGetNumberField(TEXT("crew"), Crew);
		P->Crew = (int32)Crew;
		const TArray<TSharedPtr<FJsonValue>>* List = nullptr;
		if (Plan->TryGetArrayField(TEXT("docks"), List))
		{
			for (const TSharedPtr<FJsonValue>& V : *List)
			{
				const TSharedPtr<FJsonObject> O = V->AsObject();
				if (!O.IsValid())
				{
					continue;
				}
				FBoardShipPlan::FDock D;
				D.Id = FName(*O->GetStringField(TEXT("id")));
				FString CompId, Face, Kind;
				O->TryGetStringField(TEXT("comp"), CompId);
				O->TryGetStringField(TEXT("face"), Face);
				O->TryGetStringField(TEXT("kind"), Kind);
				D.Face = FName(*Face);
				D.Kind = Kind.IsEmpty() ? FName(TEXT("hatch")) : FName(*Kind.ToLower());
				if (const int32* C = P->Dmg->CompByName.Find(FName(*CompId)))
				{
					D.Comp = *C;
				}
				const TArray<TSharedPtr<FJsonValue>>* Pos = nullptr;
				const TArray<TSharedPtr<FJsonValue>>* Nor = nullptr;
				O->TryGetArrayField(TEXT("pos"), Pos);
				O->TryGetArrayField(TEXT("normal"), Nor);
				D.Pos = BpMetres(Pos);
				D.Normal = BpUnit(Nor);
				double Deck = 0.0;
				O->TryGetNumberField(TEXT("deck"), Deck);
				D.Deck = (int32)Deck;
				if (D.Comp != INDEX_NONE)
				{
					P->Docks.Add(D);
				}
			}
		}
		if (Plan->TryGetArrayField(TEXT("garrison"), List))
		{
			for (const TSharedPtr<FJsonValue>& V : *List)
			{
				const TSharedPtr<FJsonObject> O = V->AsObject();
				if (!O.IsValid())
				{
					continue;
				}
				FBoardShipPlan::FPost Post;
				FString CompId;
				O->TryGetStringField(TEXT("comp"), CompId);
				O->TryGetStringField(TEXT("role"), Post.Role);
				double N = 0.0;
				O->TryGetNumberField(TEXT("n"), N);
				Post.N = (int32)N;
				if (const int32* C = P->Dmg->CompByName.Find(FName(*CompId)))
				{
					Post.Comp = *C;
				}
				if (Post.Comp != INDEX_NONE && Post.N > 0)
				{
					P->Garrison.Add(Post);
				}
			}
		}
		const TSharedPtr<FJsonObject>* Obj = nullptr;
		if (Plan->TryGetObjectField(TEXT("objectives"), Obj))
		{
			for (const TPair<FString, TSharedPtr<FJsonValue>>& KV : (*Obj)->Values)
			{
				if (const int32* C = P->Dmg->CompByName.Find(FName(*KV.Value->AsString())))
				{
					P->Objectives.Add(FName(*KV.Key), *C);
				}
			}
		}
	}
	// what stands in her rooms: from the plan alone (nobody is placed in a crate: the map keeps the boxes)
	const double TLay = FPlatformTime::Seconds();
	P->Layout = AstraBoardDress::MakeLayout(*P);
	UE_LOG(LogASTRA, Log, TEXT("[Board] plan of the %s: %d compartments, %d portals, %d docks, %d posts, %d props (%.0f ms, %.0f of them for the props)"), *ClassKey.ToString(), P->Dmg->Comps.Num(), P->Map->GetPortals().Num(),
	       P->Docks.Num(), P->Garrison.Num(), P->Layout.IsValid() ? P->Layout->Props.Num() : 0, (FPlatformTime::Seconds() - T0) * 1000.0, (FPlatformTime::Seconds() - TLay) * 1000.0);
	return P;
}

TSharedPtr<FBoardShipPlan> AstraBoardPlans::Load(FName ClassKey, FString& OutWhy)
{
	const FName Key(*ClassKey.ToString().ToLower());
	{
		FScopeLock Lock(&BpLock);
		if (const TSharedPtr<FBoardShipPlan>* Hit = BpCache.Find(Key))
		{
			return *Hit;
		}
	}
	const FString Path = PathFor(Key);
	if (Path.IsEmpty())
	{
		OutWhy = FString::Printf(TEXT("no plan of the %s class (data/ship/plans/%s.json)"), *Key.ToString(), *Key.ToString());
		return nullptr;
	}
	TSharedPtr<FBoardShipPlan> P = LoadFile(Path, Key, OutWhy);
	if (P.IsValid())
	{
		FScopeLock Lock(&BpLock);
		BpCache.Add(Key, P);
	}
	return P;
}

TSharedPtr<FBoardShipPlan> AstraBoardPlans::Peek(FName ClassKey)
{
	FScopeLock Lock(&BpLock);
	const TSharedPtr<FBoardShipPlan>* Hit = BpCache.Find(FName(*ClassKey.ToString().ToLower()));
	return Hit ? *Hit : nullptr;
}

FName AstraBoardPlans::KeyOfPiece(FName ClassKey, uint8 Section)
{
	const FString K = ClassKey.ToString().ToLower();
	return Section > 2 ? FName(*K) : FName(*FString::Printf(TEXT("%s#%d"), *K, (int32)Section));
}

namespace
{
	/** The two cut planes of a plan along the hull (plan cm): the class's, or with none the hull's thirds (FLOTTA-VIVA's rule). */
	void BpCuts(const FBoardShipPlan& P, float& OutBow, float& OutStern)
	{
		OutBow = P.CutBowCm;
		OutStern = P.CutSternCm;
		if (OutBow == 0.f && OutStern == 0.f && P.Dmg.IsValid())
		{
			const FBox& H = P.Dmg->Hull;
			const float L = (float)(H.Max.X - H.Min.X);
			OutBow = (float)H.Min.X + 0.66f * L;
			OutStern = (float)H.Min.X + 0.33f * L;
		}
	}

	/** A torn end of a piece: the room that stands at the cut and the point of its end wall where a boat latches (the boarders cut in at that wall). */
	void BpAddTornEnds(FBoardShipPlan& P)
	{
		const FAstraDamageMap& D = *P.Dmg;
		float Bow = 0.f, Stern = 0.f;
		BpCuts(P, Bow, Stern);
		struct FEnd { float X; double Dir; const TCHAR* Id; const TCHAR* Face; };      // Dir: +1 the end looks forward (the piece lies aft of the cut), -1 aft
		TArray<FEnd, TInlineAllocator<2>> Ends;
		if (P.Section == 0)
		{
			Ends.Add({Bow, -1.0, TEXT("tear_aft"), TEXT("stern")});
		}
		else if (P.Section == 1)
		{
			Ends.Add({Bow, 1.0, TEXT("tear_fwd"), TEXT("bow")});
			Ends.Add({Stern, -1.0, TEXT("tear_aft"), TEXT("stern")});
		}
		else if (P.Section == 2)
		{
			Ends.Add({Stern, 1.0, TEXT("tear_fwd"), TEXT("bow")});
		}
		for (const FEnd& E : Ends)
		{
			int32 Best = INDEX_NONE;
			double BestScore = -1.0e18;
			for (int32 i = 0; i < D.Comps.Num(); ++i)
			{
				const FAstraDmgComp& C = D.Comps[i];
				if (!P.Has(i) || !C.Box.IsValid || C.Box.GetSize().X < 150.0 || C.Box.GetSize().Y < 150.0)
				{
					continue;
				}
				const double Gap = E.Dir > 0.0 ? E.X - C.Box.Max.X : C.Box.Min.X - E.X;         // how far its end wall stands from the cut, inside the piece (negative: it crosses it)
				if (Gap > 300.0)
				{
					continue;
				}
				// a way in that a column can use: a corridor or a hall on the centreline, then the biggest room
				const double Score = ((C.bCorridor || C.bHall) ? 4.0e6 : 0.0) - 2000.0 * FMath::Abs(C.Box.GetCenter().Y) + FMath::Min(C.Box.GetSize().X * C.Box.GetSize().Y, 2.0e6) * 0.5 - 4000.0 * FMath::Max(0.0, Gap);
				if (Score > BestScore)
				{
					BestScore = Score;
					Best = i;
				}
			}
			if (Best == INDEX_NONE)
			{
				continue;
			}
			const FAstraDmgComp& C = D.Comps[Best];
			FBoardShipPlan::FDock Dk;
			Dk.Id = E.Id;
			Dk.Comp = Best;
			Dk.Face = FName(E.Face);
			Dk.Kind = FName(TEXT("hatch"));
			Dk.Pos = FVector(E.Dir > 0.0 ? C.Box.Max.X : C.Box.Min.X, C.Box.GetCenter().Y, C.Box.Min.Z + 140.0);
			Dk.Normal = FVector(E.Dir, 0.0, 0.0);
			Dk.Deck = C.Deck;
			P.Docks.Add(Dk);
		}
	}
}

TSharedPtr<FBoardShipPlan> AstraBoardPlans::LoadPiece(FName ClassKey, uint8 Section, FString& OutWhy)
{
	if (Section > 2)
	{
		return Load(ClassKey, OutWhy);
	}
	const FName Key = KeyOfPiece(ClassKey, Section);
	{
		FScopeLock Lock(&BpLock);
		if (const TSharedPtr<FBoardShipPlan>* Hit = BpCache.Find(Key))
		{
			return *Hit;
		}
	}
	const TSharedPtr<FBoardShipPlan> Whole = Load(ClassKey, OutWhy);
	if (!Whole.IsValid())
	{
		return nullptr;
	}
	TSharedRef<FBoardShipPlan> P = MakeShared<FBoardShipPlan>(*Whole);
	P->Section = Section;
	const FAstraDamageMap& W = *Whole->Dmg;
	const int32 N = W.Comps.Num();
	// the piece's stretch of the hull, and the rooms that are in it: every room whose middle is, and a long room (a corridor) that runs across a cut is in both pieces it reaches, clipped at the cut (her end is torn off there)
	float Bow = 0.f, Stern = 0.f;
	BpCuts(*Whole, Bow, Stern);
	const float Lo = Section == 0 ? Bow : (Section == 1 ? Stern : -1.0e9f);
	const float Hi = Section == 0 ? 1.0e9f : (Section == 1 ? Bow : Stern);
	TSharedRef<FAstraDamageMap> D = MakeShared<FAstraDamageMap>(W);
	P->Present.Init(0, N);
	for (int32 i = 0; i < N; ++i)
	{
		FBox& B = D->Comps[i].Box;
		const double Len = B.IsValid ? B.Max.X - B.Min.X : 0.0;
		bool bIn = Whole->SectionOf(i) == Section;
		if (!bIn && Len > 1.0)
		{
			const double Over = FMath::Min((double)B.Max.X, (double)Hi) - FMath::Max((double)B.Min.X, (double)Lo);
			bIn = Over >= FMath::Min(150.0, 0.5 * Len);
		}
		P->Present[i] = bIn ? 1 : 0;
		if (bIn && Len > 1.0)
		{
			B.Min.X = FMath::Max((double)B.Min.X, (double)Lo);
			B.Max.X = FMath::Min((double)B.Max.X, (double)Hi);
		}
	}
	if (P->NumRooms() == 0)
	{
		OutWhy = FString::Printf(TEXT("the %s has no rooms in her %s section"), *ClassKey.ToString(), Section == 0 ? TEXT("bow") : (Section == 1 ? TEXT("middle") : TEXT("stern")));
		return nullptr;
	}
	// no way across the cuts: a room of the piece opens on no room of the rest (the rest are islands nobody can reach, and her walls stand where her ways crossed)
	for (int32 a = 0; a < N; ++a)
	{
		D->Comps[a].Links.RemoveAll([&D, &P, a](const FAstraDmgLink& L) { return !D->Comps.IsValidIndex(L.To) || P->Present[L.To] != P->Present[a]; });
	}
	P->Dmg = D;
	P->Map = MakeShared<FAstraBoardMap>();
	if (!P->Map->Build(D))
	{
		OutWhy = TEXT("the piece has no compartments");
		return nullptr;
	}
	// the piece is one place: the largest set of her rooms that are joined by ways. A room or a few the cuts left with no way to the rest (their only doors led across the cut) are not hers to board: nobody can reach them
	{
		const FAstraBoardMap& M = *P->Map;
		TArray<int32> Group;
		Group.Init(-1, N);
		int32 Best = -1, BestN = 0, Groups = 0;
		for (int32 i = 0; i < N; ++i)
		{
			if (!P->Present[i] || Group[i] >= 0)
			{
				continue;
			}
			int32 Count = 0;
			TArray<int32> Stack;
			Stack.Add(i);
			Group[i] = Groups;
			while (Stack.Num())
			{
				const int32 C = Stack.Pop();
				++Count;
				for (const int32 Pi : M.GetComps()[C].Portals)
				{
					const int32 O = M.GetPortals()[Pi].Other(C);
					if (P->Present.IsValidIndex(O) && P->Present[O] && Group[O] < 0)
					{
						Group[O] = Groups;
						Stack.Add(O);
					}
				}
			}
			if (Count > BestN)
			{
				BestN = Count;
				Best = Groups;
			}
			++Groups;
		}
		for (int32 i = 0; i < N; ++i)
		{
			if (P->Present[i] && Group[i] != Best)
			{
				P->Present[i] = 0;
			}
		}
	}
	// what she still has: her hatches, her posts, her places; and a torn end at each cut face
	P->Docks.RemoveAll([&P](const FBoardShipPlan::FDock& K) { return !P->Has(K.Comp); });
	P->Garrison.RemoveAll([&P](const FBoardShipPlan::FPost& K) { return !P->Has(K.Comp); });
	for (auto It = P->Objectives.CreateIterator(); It; ++It)
	{
		if (!P->Has(It.Value()))
		{
			It.RemoveCurrent();
		}
	}
	const double Crew = (double)Whole->Crew * (double)P->NumRooms() / FMath::Max(1, N);
	P->Crew = FMath::RoundToInt(Crew);
	BpAddTornEnds(*P);
	P->Label = FString::Printf(TEXT("%s (%s section)"), *Whole->Label, Section == 0 ? TEXT("bow") : (Section == 1 ? TEXT("middle") : TEXT("stern")));
	UE_LOG(LogASTRA, Log, TEXT("[Board] piece of the %s, %s section: %d of %d rooms, %d portals, %d docks (%d torn ends)"), *ClassKey.ToString(), Section == 0 ? TEXT("bow") : (Section == 1 ? TEXT("middle") : TEXT("stern")), P->NumRooms(), N,
	       P->Map->GetPortals().Num(), P->Docks.Num(), P->Docks.FilterByPredicate([](const FBoardShipPlan::FDock& K) { return K.Id.ToString().StartsWith(TEXT("tear_")); }).Num());
	FScopeLock Lock(&BpLock);
	BpCache.Add(Key, P);
	return P;
}

int32 AstraBoardPlans::PieceObjective(const FBoardShipPlan& Plan, int32 CutInComp)
{
	if (!Plan.Map.IsValid() || !Plan.Dmg.IsValid())
	{
		return INDEX_NONE;
	}
	struct FPlace { const TCHAR* Name; const TCHAR* Kind; };
	static const FPlace Places[] = {{TEXT("bridge"), TEXT("bridge")}, {TEXT("engineering"), TEXT("engineering")}, {TEXT("captain"), TEXT("quarters")}};
	for (const FPlace& K : Places)
	{
		const int32 C = Plan.Objective(K.Name, K.Kind);
		if (C != INDEX_NONE)
		{
			return C;
		}
	}
	// else a walk through her: the rooms she has, the furthest first, the first one that can be reached from where they cut in
	const FAstraBoardMap& M = *Plan.Map;
	if (!M.GetComps().IsValidIndex(CutInComp))
	{
		return INDEX_NONE;
	}
	const FVector From = M.CentreOf(CutInComp);
	TArray<TPair<double, int32>> Far;
	for (int32 i = 0; i < M.GetComps().Num(); ++i)
	{
		const FBoardComp& C = M.GetComps()[i];
		if (!Plan.Has(i) || i == CutInComp || C.bCorridor || !C.Box.IsValid || C.Box.GetSize().X < 250.0 || C.Box.GetSize().Y < 250.0)
		{
			continue;
		}
		Far.Emplace(-FVector::Dist(From, M.CentreOf(i)), i);
	}
	Far.Sort([](const TPair<double, int32>& A, const TPair<double, int32>& B) { return A.Key < B.Key; });
	for (int32 k = 0; k < FMath::Min(Far.Num(), 12); ++k)
	{
		TArray<FVector> Pts;
		float Len = 0.f;
		FBoardRouteOptions Opt;
		Opt.bThroughSealed = true;
		if (M.Route(M.Inset(CutInComp, From, 70.f), M.CentreOf(Far[k].Value), Pts, Opt, &Len))
		{
			return Far[k].Value;
		}
	}
	return CutInComp;
}

void AstraBoardPlans::ClassesWithPlans(TArray<FName>& Out)
{
	Out.Reset();
	TArray<FString> Files;
	IFileManager::Get().FindFiles(Files, *FPaths::Combine(FPaths::ProjectDir(), TEXT("data/ship/plans/*.json")), true, false);
	for (const FString& F : Files)
	{
		Out.AddUnique(FName(*FPaths::GetBaseFilename(F)));
	}
}
