// ASTRA — FLOTTA-VIVA: the plan of a class of ship, as the war reads it (see AstraFleetPlan.h).

#include "AstraFleetPlan.h"

#include "ASTRA.h"
#include "Async/Async.h"
#include "Dom/JsonObject.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

namespace
{
	FCriticalSection GFleetLock;
	TMap<FName, TSharedPtr<const FFleetClassPlan>> GFleetPlans;                       // loaded (null: there is none)
	TMap<FName, TSharedFuture<TSharedPtr<const FFleetClassPlan>>> GFleetPending;       // being loaded on a worker

	bool FleetReadJson(const FString& Path, TSharedPtr<FJsonObject>& Out)
	{
		FString Text;
		if (!FFileHelper::LoadFileToString(Text, *Path))
		{
			return false;
		}
		return FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Out) && Out.IsValid();
	}

	FVector FleetVec(const TArray<TSharedPtr<FJsonValue>>* A, double Scale)
	{
		return A && A->Num() >= 3 ? FVector((*A)[0]->AsNumber(), (*A)[1]->AsNumber(), (*A)[2]->AsNumber()) * Scale : FVector::ZeroVector;
	}

	int32 FleetComp(const FAstraDamageMap& M, const FString& Id)
	{
		const int32* I = Id.IsEmpty() ? nullptr : M.CompByName.Find(FName(*Id));
		return I ? *I : INDEX_NONE;
	}

	/** Seconds for a damage party to run from a compartment to each of the others: the doors and the stairs of the plan, at a run (3.4 m/s), a
	 *  moment at each door, a longer one at a pressure bulkhead. */
	void FleetTravel(const FAstraDamageMap& M, int32 Home, TArray<float>& Out)
	{
		const int32 N = M.Comps.Num();
		TArray<float> Dist;
		Dist.Init(1.0e9f, N);
		TArray<uint8> Done;
		Done.Init(0, N);
		if (Home < 0 || Home >= N)
		{
			Out.Init(1.0e4f, N);
			return;
		}
		Dist[Home] = 0.f;
		for (int32 Step = 0; Step < N; ++Step)
		{
			int32 U = INDEX_NONE;
			float Best = 1.0e8f;
			for (int32 i = 0; i < N; ++i)
			{
				if (!Done[i] && Dist[i] < Best)
				{
					Best = Dist[i];
					U = i;
				}
			}
			if (U == INDEX_NONE)
			{
				break;
			}
			Done[U] = 1;
			const FVector Cu = M.Comps[U].Box.GetCenter();
			for (const FAstraDmgLink& L : M.Comps[U].Links)
			{
				const FVector Cv = M.Comps[L.To].Box.GetCenter();
				float Metres = (float)((FVector::Dist(Cu, L.AtCm) + FVector::Dist(L.AtCm, Cv)) / 100.0);
				switch (L.Kind)
				{
				case FAstraDmgLink::EKind::Door: Metres += 1.5f; break;
				case FAstraDmgLink::EKind::Blast: Metres += 6.f; break;
				case FAstraDmgLink::EKind::Stair: Metres += 4.f; break;
				case FAstraDmgLink::EKind::Lift: Metres += 1.0e5f; break;     // (soldiers and parties do not use lifts)
				default: break;
				}
				if (Dist[U] + Metres < Dist[L.To])
				{
					Dist[L.To] = Dist[U] + Metres;
				}
			}
		}
		Out.SetNumUninitialized(N);
		for (int32 i = 0; i < N; ++i)
		{
			Out[i] = Dist[i] >= 1.0e8f ? 1.0e4f : Dist[i] / 3.4f;
		}
	}
}

FString FAstraFleetPlans::PathFor(FName ClassKey)
{
	const FString Staged = FPaths::Combine(FPaths::ProjectContentDir(), TEXT("ASTRA/Data/plans"), ClassKey.ToString() + TEXT(".json"));
	if (FPaths::FileExists(Staged))
	{
		return Staged;
	}
	const FString Repo = FPaths::Combine(FPaths::ProjectDir(), TEXT("data/ship/plans"), ClassKey.ToString() + TEXT(".json"));
	return FPaths::FileExists(Repo) ? Repo : FString();
}

TSharedPtr<FFleetClassPlan> FAstraFleetPlans::LoadFile(FName ClassKey, const FString& Path, FString& OutError)
{
	const double T0 = FPlatformTime::Seconds();
	TSharedRef<FFleetClassPlan> P = MakeShared<FFleetClassPlan>();
	P->Key = ClassKey;
	P->Map = MakeShared<FAstraDamageMap>();
	if (!P->Map->Load(Path, OutError))
	{
		return nullptr;
	}
	TSharedPtr<FJsonObject> Root;
	if (!FleetReadJson(Path, Root))
	{
		OutError = TEXT("the plan does not parse");
		return nullptr;
	}
	const FAstraDamageMap& M = *P->Map;
	Root->TryGetStringField(TEXT("style"), P->Style);
	Root->TryGetStringField(TEXT("label"), P->Label);
	P->bMandate = P->Style == TEXT("mandate");
	// the class's cut planes in the plan's frame (the war's bow, middle and stern sections are what lies beyond them)
	const TSharedPtr<FJsonObject>* Hull = nullptr;
	if (Root->TryGetObjectField(TEXT("hull"), Hull))
	{
		const TArray<TSharedPtr<FJsonValue>>* Cuts = nullptr;
		if ((*Hull)->TryGetArrayField(TEXT("cuts_x"), Cuts) && Cuts->Num() >= 2)
		{
			P->CutBowCm = (float)(((*Cuts)[0]->AsNumber() - M.OriginInHullM.X) * 100.0);
			P->CutSternCm = (float)(((*Cuts)[1]->AsNumber() - M.OriginInHullM.X) * 100.0);
		}
	}
	// the people
	const TSharedPtr<FJsonObject>* Crew = nullptr;       // ("crew" is the complement, a number, for the boarding module's reader; the roster is its own object)
	if (Root->TryGetObjectField(TEXT("roster"), Crew))
	{
		double V = 0.0;
		(*Crew)->TryGetNumberField(TEXT("complement"), V);
		P->Complement = (int32)V;
		V = 0.0;
		(*Crew)->TryGetNumberField(TEXT("marines"), V);
		P->Marines = (int32)V;
		V = 0.0;
		(*Crew)->TryGetNumberField(TEXT("officers"), V);
		P->Officers = (int32)V;
		const TSharedPtr<FJsonObject>* Ranks = nullptr;
		if ((*Crew)->TryGetObjectField(TEXT("ranks"), Ranks))
		{
			for (const auto& KV : (*Ranks)->Values)
			{
				P->Ranks.Add(FName(*KV.Key), KV.Value->AsString());
			}
		}
		const TArray<TSharedPtr<FJsonValue>>* Billets = nullptr;
		if ((*Crew)->TryGetArrayField(TEXT("billets"), Billets))
		{
			for (const TSharedPtr<FJsonValue>& BV : *Billets)
			{
				const TSharedPtr<FJsonObject> B = BV->AsObject();
				if (!B.IsValid())
				{
					continue;
				}
				FFleetBillet Bl;
				Bl.Role = FName(*B->GetStringField(TEXT("role")));
				B->TryGetStringField(TEXT("rank"), Bl.Rank);
				double Line = 0.0;
				B->TryGetNumberField(TEXT("line"), Line);
				Bl.Line = (int32)Line;
				Bl.Comp = FleetComp(M, B->GetStringField(TEXT("post")));
				const TArray<TSharedPtr<FJsonValue>>* Stands = nullptr;
				B->TryGetArrayField(TEXT("stands"), Stands);
				Bl.PostCm = FleetVec(Stands, 100.0);
				if (Bl.Comp != INDEX_NONE)
				{
					P->Billets.Add(Bl);
				}
			}
			P->Billets.Sort([](const FFleetBillet& A, const FFleetBillet& B) { return A.Line < B.Line; });
		}
	}
	const TArray<TSharedPtr<FJsonValue>>* Garrison = nullptr;
	if (Root->TryGetArrayField(TEXT("garrison"), Garrison))
	{
		for (const TSharedPtr<FJsonValue>& GV : *Garrison)
		{
			const TSharedPtr<FJsonObject> G = GV->AsObject();
			if (!G.IsValid())
			{
				continue;
			}
			FFleetGarrison E;
			E.Comp = FleetComp(M, G->GetStringField(TEXT("comp")));
			E.N = (int32)G->GetNumberField(TEXT("n"));
			E.Role = FName(*G->GetStringField(TEXT("role")));
			if (E.Comp != INDEX_NONE && E.N > 0)
			{
				P->Garrison.Add(E);
			}
		}
	}
	const TSharedPtr<FJsonObject>* Obj = nullptr;
	if (Root->TryGetObjectField(TEXT("objectives"), Obj))
	{
		for (const auto& KV : (*Obj)->Values)
		{
			FString Id;
			if (KV.Value.IsValid() && KV.Value->TryGetString(Id))
			{
				const int32 C = FleetComp(M, Id);
				if (C != INDEX_NONE)
				{
					P->Objectives.Add(FName(*KV.Key), C);
				}
			}
		}
	}
	// the roles the rooms play (the first room of each), and the room that serves each of the war's weapon mounts
	{
		const TArray<TSharedPtr<FJsonValue>>* Comps = nullptr;
		if (Root->TryGetArrayField(TEXT("compartments"), Comps))
		{
			for (const TSharedPtr<FJsonValue>& CV : *Comps)
			{
				const TSharedPtr<FJsonObject> Co = CV.IsValid() ? CV->AsObject() : nullptr;
				FString Role, Id;
				if (Co.IsValid() && Co->TryGetStringField(TEXT("role"), Role) && Co->TryGetStringField(TEXT("id"), Id) && Role != TEXT("spine") && Role != TEXT("passage") && Role != TEXT("cross"))
				{
					const int32 Ci = FleetComp(M, Id);
					if (Ci != INDEX_NONE && !P->Roles.Contains(FName(*Role)))
					{
						P->Roles.Add(FName(*Role), Ci);
					}
				}
			}
		}
		const TArray<TSharedPtr<FJsonValue>>* Mounts = nullptr;
		if (Root->TryGetArrayField(TEXT("mounts"), Mounts))
		{
			for (const TSharedPtr<FJsonValue>& MV : *Mounts)
			{
				const TSharedPtr<FJsonObject> Mo = MV.IsValid() ? MV->AsObject() : nullptr;
				FString CompId;
				P->MountComp.Add(Mo.IsValid() && Mo->TryGetStringField(TEXT("comp"), CompId) ? FleetComp(M, CompId) : INDEX_NONE);
			}
		}
	}
	const TSharedPtr<FJsonObject>* Dc = nullptr;
	if (Root->TryGetObjectField(TEXT("damage_control"), Dc))
	{
		FString Central;
		(*Dc)->TryGetStringField(TEXT("central"), Central);
		P->DcCentral = FleetComp(M, Central);
		const TArray<TSharedPtr<FJsonValue>>* Parties = nullptr;
		if ((*Dc)->TryGetArrayField(TEXT("parties"), Parties))
		{
			for (const TSharedPtr<FJsonValue>& PV : *Parties)
			{
				const TSharedPtr<FJsonObject> Pa = PV->AsObject();
				if (!Pa.IsValid())
				{
					continue;
				}
				FFleetParty F;
				F.Home = FleetComp(M, Pa->GetStringField(TEXT("home")));
				F.Size = FMath::Max(1, (int32)Pa->GetNumberField(TEXT("size")));
				if (F.Home != INDEX_NONE)
				{
					FleetTravel(M, F.Home, F.TravelS);
					P->Parties.Add(MoveTemp(F));
				}
			}
		}
	}
	const TArray<TSharedPtr<FJsonValue>>* Docks = nullptr;
	if (Root->TryGetArrayField(TEXT("docks"), Docks))
	{
		for (const TSharedPtr<FJsonValue>& DV : *Docks)
		{
			const TSharedPtr<FJsonObject> D = DV->AsObject();
			if (!D.IsValid())
			{
				continue;
			}
			FFleetDock K;
			K.Id = FName(*D->GetStringField(TEXT("id")));
			K.Comp = FleetComp(M, D->GetStringField(TEXT("comp")));
			K.Face = FName(*D->GetStringField(TEXT("face")));
			const TArray<TSharedPtr<FJsonValue>>* Pos = nullptr;
			const TArray<TSharedPtr<FJsonValue>>* Nrm = nullptr;
			D->TryGetArrayField(TEXT("pos"), Pos);
			D->TryGetArrayField(TEXT("normal"), Nrm);
			K.PosM = FleetVec(Pos, 1.0);
			K.NormalM = FleetVec(Nrm, 1.0);
			K.Deck = (int32)D->GetNumberField(TEXT("deck"));
			FString Kind;
			D->TryGetStringField(TEXT("kind"), Kind);
			K.Kind = FName(*Kind);
			P->Docks.Add(K);
		}
	}
	UE_LOG(LogASTRA, Log, TEXT("[Fleet] the plan of the %s: %d compartments, %d doors, crew %d (%d guards), %d billets, %d damage parties, %d docks (%.0f ms)"), *ClassKey.ToString(),
	       M.Comps.Num(), M.Doors.Num(), P->Complement, P->Marines, P->Billets.Num(), P->Parties.Num(), P->Docks.Num(), (FPlatformTime::Seconds() - T0) * 1000.0);
	return P;
}

namespace
{
	TSharedPtr<const FFleetClassPlan> FleetLoadClass(FName Key)
	{
		const FString Path = FAstraFleetPlans::PathFor(Key);
		if (Path.IsEmpty())
		{
			return nullptr;
		}
		FString Err;
		TSharedPtr<FFleetClassPlan> P = FAstraFleetPlans::LoadFile(Key, Path, Err);
		if (!P.IsValid())
		{
			UE_LOG(LogASTRA, Warning, TEXT("[Fleet] the plan of the %s (%s): %s — its ships have no interior"), *Key.ToString(), *Path, *Err);
		}
		return P;
	}
}

void FAstraFleetPlans::Prefetch(FName ClassKey)
{
	FScopeLock Lock(&GFleetLock);
	if (ClassKey.IsNone() || GFleetPlans.Contains(ClassKey) || GFleetPending.Contains(ClassKey))
	{
		return;
	}
	GFleetPending.Add(ClassKey, Async(EAsyncExecution::ThreadPool, [ClassKey]() { return FleetLoadClass(ClassKey); }).Share());
}

TSharedPtr<const FFleetClassPlan> FAstraFleetPlans::Find(FName ClassKey, bool bWait)
{
	if (ClassKey.IsNone())
	{
		return nullptr;
	}
	TSharedFuture<TSharedPtr<const FFleetClassPlan>> Wait;
	{
		FScopeLock Lock(&GFleetLock);
		if (const TSharedPtr<const FFleetClassPlan>* P = GFleetPlans.Find(ClassKey))
		{
			return *P;
		}
		if (const TSharedFuture<TSharedPtr<const FFleetClassPlan>>* F = GFleetPending.Find(ClassKey))
		{
			Wait = *F;
		}
	}
	TSharedPtr<const FFleetClassPlan> Got;
	if (Wait.IsValid())
	{
		if (!bWait && !Wait.IsReady())
		{
			return nullptr;                                          // (the worker has not finished: not now, at the next blow)
		}
		Got = Wait.Get();
	}
	else if (!bWait)
	{
		Prefetch(ClassKey);
		return nullptr;
	}
	else
	{
		Got = FleetLoadClass(ClassKey);
	}
	FScopeLock Lock(&GFleetLock);
	GFleetPending.Remove(ClassKey);
	GFleetPlans.Add(ClassKey, Got);
	return Got;
}

void FAstraFleetPlans::Clear()
{
	FScopeLock Lock(&GFleetLock);
	GFleetPending.Reset();
	GFleetPlans.Reset();
}
