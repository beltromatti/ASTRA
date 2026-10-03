#include "AstraBoardPlans.h"

#include "ASTRA.h"
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
	if (const int32* C = Objectives.Find(FName(Name)))
	{
		return *C;
	}
	if (Dmg.IsValid() && Kind && *Kind)
	{
		const FName K(Kind);
		for (int32 i = 0; i < Dmg->Comps.Num(); ++i)
		{
			if (Dmg->Comps[i].Kind == K)
			{
				return i;
			}
		}
	}
	return INDEX_NONE;
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

FString AstraBoardPlans::PathFor(FName ClassKey, bool& bOutStopgap)
{
	bOutStopgap = false;
	const FString K = ClassKey.ToString().ToLower();
	if (K == TEXT("aquila"))
	{
		const FString Staged = FPaths::Combine(FPaths::ProjectContentDir(), TEXT("ASTRA/Data/aquila_plan.json"));
		return FPaths::FileExists(Staged) ? Staged : FPaths::Combine(FPaths::ProjectDir(), TEXT("data/ship/aquila_plan.json"));
	}
	const FString Staged = FPaths::Combine(FPaths::ProjectContentDir(), FString::Printf(TEXT("ASTRA/Data/plans/%s.json"), *K));
	const FString Repo = FPaths::Combine(FPaths::ProjectDir(), FString::Printf(TEXT("data/ship/plans/%s.json"), *K));
	const FString Stop = FPaths::Combine(FPaths::ProjectDir(), FString::Printf(TEXT("data/ship/plans/stopgap/%s.json"), *K));
	if (FPaths::FileExists(Staged))
	{
		return Staged;
	}
	if (FPaths::FileExists(Repo))
	{
		return Repo;
	}
	if (FPaths::FileExists(Stop))
	{
		bOutStopgap = true;
		return Stop;
	}
	return FString();
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
		Plan->TryGetBoolField(TEXT("stopgap"), P->bStopgap);
		Plan->TryGetStringField(TEXT("label"), P->Label);
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
				FString CompId, Face;
				O->TryGetStringField(TEXT("comp"), CompId);
				O->TryGetStringField(TEXT("face"), Face);
				D.Face = FName(*Face);
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
	UE_LOG(LogASTRA, Log, TEXT("[Board] plan of the %s%s: %d compartments, %d portals, %d docks, %d posts (%.0f ms)"), *ClassKey.ToString(), P->bStopgap ? TEXT(" (a stopgap)") : TEXT(""), P->Dmg->Comps.Num(),
	       P->Map->GetPortals().Num(), P->Docks.Num(), P->Garrison.Num(), (FPlatformTime::Seconds() - T0) * 1000.0);
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
	bool bStop = false;
	const FString Path = PathFor(Key, bStop);
	if (Path.IsEmpty())
	{
		OutWhy = FString::Printf(TEXT("no plan of the %s class (data/ship/plans/%s.json)"), *Key.ToString(), *Key.ToString());
		return nullptr;
	}
	TSharedPtr<FBoardShipPlan> P = LoadFile(Path, Key, OutWhy);
	if (P.IsValid())
	{
		P->bStopgap |= bStop;
		FScopeLock Lock(&BpLock);
		BpCache.Add(Key, P);
	}
	return P;
}

void AstraBoardPlans::ClassesWithPlans(TArray<FName>& Out)
{
	Out.Reset();
	for (const FString& Dir : {FPaths::Combine(FPaths::ProjectDir(), TEXT("data/ship/plans")), FPaths::Combine(FPaths::ProjectDir(), TEXT("data/ship/plans/stopgap"))})
	{
		TArray<FString> Files;
		IFileManager::Get().FindFiles(Files, *FPaths::Combine(Dir, TEXT("*.json")), true, false);
		for (const FString& F : Files)
		{
			Out.AddUnique(FName(*FPaths::GetBaseFilename(F)));
		}
	}
}
