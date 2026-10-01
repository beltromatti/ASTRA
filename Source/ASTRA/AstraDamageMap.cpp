// ASTRA — DISTRUZIONE: the plan as the damage model needs it (see AstraDamageMap.h).

#include "AstraDamageMap.h"

#include "ASTRA.h"
#include "Dom/JsonObject.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

namespace
{
	/** The kinds of room as the model's profiles name them (the order of DmProfileTable). */
	enum EDmClass : uint8
	{
		DmDefault, DmCorridor, DmShaft, DmCabin, DmSocial, DmGalley, DmOffice, DmMachinery, DmPower, DmStore, DmMagazine, DmArmoury, DmTank, DmHangar,
		DmWorkshop, DmMedical, DmCrawl, DmEngineering, DmBridge, DmClassNum
	};

	FAstraDmgProfile DmMake(float Ignite, float Fuel, float Hard, float Conduit, float Fill, float Traffic, bool bSuppress = false, bool bExplosive = false)
	{
		FAstraDmgProfile P;
		P.Ignite = Ignite;
		P.Fuel = Fuel;
		P.Hard = Hard;
		P.Conduit = Conduit;
		P.Fill = Fill;
		P.Traffic = Traffic;
		P.bSuppress = bSuppress;
		P.bExplosive = bExplosive;
		return P;
	}

	/** The numbers: how readily each kind of room burns, how long its load feeds a fire, how much it takes before it is wrecked, how thick the power
	 *  runs in it, how much of a blow it swallows, how busy its doors are. Corridors are bare (a fire in one starves unless something feeds it); a store
	 *  or a galley is all fuel; machinery and power rooms are thick with conduits and hard to wreck, and have fixed suppression. */
	FAstraDmgProfile DmProfileOf(EDmClass C)
	{
		switch (C)
		{
		case DmCorridor:    return DmMake(0.30f, 25.f, 90.f, 1.0f, 0.12f, 1.0f);
		case DmShaft:       return DmMake(0.25f, 20.f, 130.f, 0.4f, 0.12f, 1.0f);
		case DmCabin:       return DmMake(1.00f, 140.f, 120.f, 0.5f, 0.35f, 0.8f);
		case DmSocial:      return DmMake(0.90f, 120.f, 140.f, 0.6f, 0.35f, 1.6f);
		case DmGalley:      return DmMake(1.30f, 160.f, 130.f, 0.8f, 0.40f, 1.3f);
		case DmOffice:      return DmMake(0.80f, 90.f, 140.f, 1.4f, 0.38f, 1.0f);
		case DmMachinery:   return DmMake(0.90f, 110.f, 230.f, 1.6f, 0.55f, 0.5f, true);
		case DmPower:       return DmMake(0.80f, 90.f, 270.f, 2.0f, 0.55f, 0.5f, true);
		case DmStore:       return DmMake(1.20f, 200.f, 140.f, 0.3f, 0.55f, 0.6f);
		case DmMagazine:    return DmMake(0.90f, 120.f, 280.f, 0.8f, 0.60f, 0.4f, true, true);
		case DmArmoury:     return DmMake(0.90f, 120.f, 260.f, 0.8f, 0.55f, 0.5f, true);
		case DmTank:        return DmMake(0.70f, 160.f, 320.f, 0.3f, 0.70f, 0.3f, true);
		case DmHangar:      return DmMake(0.70f, 150.f, 900.f, 0.6f, 0.20f, 1.0f, true);
		case DmWorkshop:    return DmMake(1.00f, 130.f, 200.f, 1.2f, 0.50f, 0.8f);
		case DmMedical:     return DmMake(0.80f, 90.f, 150.f, 1.0f, 0.40f, 1.0f);
		case DmCrawl:       return DmMake(0.30f, 20.f, 80.f, 0.8f, 0.20f, 0.3f);
		case DmEngineering: return DmMake(0.90f, 160.f, 650.f, 2.0f, 0.35f, 0.8f, true);
		case DmBridge:      return DmMake(0.80f, 90.f, 260.f, 1.8f, 0.40f, 1.0f);
		default:            return DmMake(0.80f, 100.f, 150.f, 0.6f, 0.40f, 1.0f);
		}
	}

	EDmClass DmClassOfKind(const FString& K)
	{
		static const TMap<FString, EDmClass> Table = {
			{TEXT("corridor"), DmCorridor}, {TEXT("vestibule"), DmCorridor}, {TEXT("stairs"), DmShaft}, {TEXT("lift"), DmShaft},
			{TEXT("cabins"), DmCabin}, {TEXT("quarters"), DmCabin}, {TEXT("berthing"), DmCabin}, {TEXT("wardroom"), DmCabin},
			{TEXT("lounge"), DmSocial}, {TEXT("library"), DmSocial}, {TEXT("chapel"), DmSocial}, {TEXT("gym"), DmSocial}, {TEXT("observation"), DmSocial},
			{TEXT("concourse"), DmSocial}, {TEXT("mess"), DmSocial}, {TEXT("range"), DmSocial}, {TEXT("hydroponics"), DmSocial},
			{TEXT("galley"), DmGalley},
			{TEXT("offices"), DmOffice}, {TEXT("archive"), DmOffice}, {TEXT("lab"), DmOffice}, {TEXT("comms"), DmOffice}, {TEXT("sensors"), DmOffice},
			{TEXT("weapons_control"), DmOffice}, {TEXT("flight_ops"), DmOffice}, {TEXT("transporter"), DmOffice}, {TEXT("ready_room"), DmOffice}, {TEXT("briefing"), DmOffice},
			{TEXT("bridge"), DmBridge},
			{TEXT("machinery"), DmMachinery}, {TEXT("power"), DmPower},
			{TEXT("storage"), DmStore}, {TEXT("laundry"), DmStore}, {TEXT("heads"), DmStore}, {TEXT("damage_control"), DmStore},
			{TEXT("magazine"), DmMagazine}, {TEXT("armory"), DmArmoury}, {TEXT("weapons"), DmArmoury},
			{TEXT("tank"), DmTank}, {TEXT("hangar"), DmHangar}, {TEXT("workshop"), DmWorkshop}, {TEXT("fabrication"), DmWorkshop},
			{TEXT("medbay"), DmMedical}, {TEXT("surgery"), DmMedical}, {TEXT("pharmacy"), DmMedical}, {TEXT("quarantine"), DmMedical},
			{TEXT("crawlway"), DmCrawl}, {TEXT("engineering"), DmEngineering}};
		const EDmClass* C = Table.Find(K);
		return C ? *C : DmDefault;
	}

	int32 DmSystemOf(const FString& S)
	{
		static const TMap<FString, EAstraDmgSystem> Table = {
			{TEXT("reactor"), EAstraDmgSystem::Reactor}, {TEXT("coolant"), EAstraDmgSystem::Coolant}, {TEXT("weapons"), EAstraDmgSystem::Weapons},
			{TEXT("ordnance"), EAstraDmgSystem::Ordnance}, {TEXT("sensors"), EAstraDmgSystem::Sensors}, {TEXT("data_trunk"), EAstraDmgSystem::DataTrunk},
			{TEXT("life_support"), EAstraDmgSystem::LifeSupport}, {TEXT("catapults"), EAstraDmgSystem::Catapults}, {TEXT("launch_tubes"), EAstraDmgSystem::Catapults},
			{TEXT("power_bus"), EAstraDmgSystem::PowerBus}, {TEXT("engines"), EAstraDmgSystem::Engines}, {TEXT("damage_control"), EAstraDmgSystem::DamageControl}};
		const EAstraDmgSystem* E = Table.Find(S);
		return E ? (int32)*E : INDEX_NONE;
	}

	bool DmReadJson(const FString& Path, TSharedPtr<FJsonObject>& Out)
	{
		FString Text;
		if (!FFileHelper::LoadFileToString(Text, *Path))
		{
			return false;
		}
		return FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Out) && Out.IsValid();
	}

	FString DmFindPlan(bool bRepoFirst)
	{
		// staged with the game (Content/ASTRA/Data, always packaged as a loose file), else the repository's copy (the one the plan generator writes: the
		// bench reads it first, the staged copy is only as new as the last time the lead staged it)
		const FString Repo = FPaths::Combine(FPaths::ProjectDir(), TEXT("data/ship/aquila_plan.json"));
		const FString A = FPaths::Combine(FPaths::ProjectContentDir(), TEXT("ASTRA/Data/aquila_plan.json"));
		if (bRepoFirst && FPaths::FileExists(Repo))
		{
			return Repo;
		}
		return FPaths::FileExists(A) ? A : Repo;
	}

	FVector DmMetres(const TArray<TSharedPtr<FJsonValue>>* A)
	{
		return A && A->Num() >= 3 ? FVector((*A)[0]->AsNumber(), (*A)[1]->AsNumber(), (*A)[2]->AsNumber()) * 100.0 : FVector::ZeroVector;
	}

	double DmNum(const TSharedPtr<FJsonObject>& O, const TCHAR* Field, double Default)
	{
		double V = Default;
		if (O.IsValid())
		{
			O->TryGetNumberField(Field, V);
		}
		return V;
	}

	/** A compartment's name without the section the plan writes into a corridor's ("Port Passage · Section C" -> "Port Passage"). */
	FString DmPlaceName(const FString& Name)
	{
		const int32 Cut = Name.Find(TEXT(" · Section"));
		return Cut != INDEX_NONE ? Name.Left(Cut) : Name;
	}
}

float FAstraDmgDeck::HalfWidthAt(float X) const
{
	for (int32 i = 0; i + 1 < HalfWidth.Num(); ++i)
	{
		const FVector2D& A = HalfWidth[i];
		const FVector2D& B = HalfWidth[i + 1];
		if (X <= FMath::Max(A.X, B.X) && X >= FMath::Min(A.X, B.X))
		{
			const double T = FMath::IsNearlyEqual(A.X, B.X) ? 0.0 : (X - A.X) / (B.X - A.X);
			return (float)FMath::Lerp(A.Y, B.Y, T);
		}
	}
	return 0.f;
}

bool FAstraDamageMap::Load(FString& OutError, bool bRepoFirst)
{
	const double T0 = FPlatformTime::Seconds();
	TSharedPtr<FJsonObject> Plan;
	if (!DmReadJson(DmFindPlan(bRepoFirst), Plan))
	{
		OutError = TEXT("no ship's plan (aquila_plan.json)");
		return false;
	}
	for (int32 c = 0; c < DmClassNum; ++c)
	{
		Profiles.Add(DmProfileOf((EDmClass)c));
	}
	const TArray<TSharedPtr<FJsonValue>>* List = nullptr;
	// ---- the decks
	if (Plan->TryGetArrayField(TEXT("decks"), List))
	{
		for (const TSharedPtr<FJsonValue>& V : *List)
		{
			const TSharedPtr<FJsonObject> O = V->AsObject();
			if (!O.IsValid())
			{
				continue;
			}
			FAstraDmgDeck D;
			D.Id = (int32)DmNum(O, TEXT("id"), 0);
			D.FloorCm = (float)(DmNum(O, TEXT("z"), 0.0) * 100.0);
			D.ClearCm = (float)(DmNum(O, TEXT("clear"), 3.8) * 100.0);
			const TSharedPtr<FJsonObject>* Env = nullptr;
			if (O->TryGetObjectField(TEXT("envelope"), Env))
			{
				D.XFwdCm = (float)(DmNum(*Env, TEXT("x_fwd"), 0.0) * 100.0);
				D.XAftCm = (float)(DmNum(*Env, TEXT("x_aft"), 0.0) * 100.0);
				const TArray<TSharedPtr<FJsonValue>>* HW = nullptr;
				if ((*Env)->TryGetArrayField(TEXT("half_width"), HW))
				{
					for (const TSharedPtr<FJsonValue>& PV : *HW)
					{
						const TArray<TSharedPtr<FJsonValue>>& Pair = PV->AsArray();
						if (Pair.Num() >= 2)
						{
							D.HalfWidth.Add(FVector2D(Pair[0]->AsNumber() * 100.0, Pair[1]->AsNumber() * 100.0));
						}
					}
				}
			}
			Decks.Add(D);
		}
		Decks.Sort([](const FAstraDmgDeck& A, const FAstraDmgDeck& B) { return A.Id < B.Id; });
	}
	// ---- the doors (a blast door's sides come from the graph, below)
	if (Plan->TryGetArrayField(TEXT("doors"), List))
	{
		for (const TSharedPtr<FJsonValue>& V : *List)
		{
			const TSharedPtr<FJsonObject> O = V->AsObject();
			if (!O.IsValid())
			{
				continue;
			}
			FAstraDmgDoor D;
			D.Id = FName(*O->GetStringField(TEXT("id")));
			FString K;
			O->TryGetStringField(TEXT("kind"), K);
			D.Kind = FName(*K);
			D.Deck = (int16)DmNum(O, TEXT("deck"), 0);
			const TArray<TSharedPtr<FJsonValue>>* P = nullptr;
			O->TryGetArrayField(TEXT("pos"), P);
			D.PosCm = DmMetres(P);
			D.Yaw = (float)DmNum(O, TEXT("yaw"), 0.0);
			D.WidthM = (float)DmNum(O, TEXT("width"), 1.6);
			D.HeightM = (float)DmNum(O, TEXT("height"), 2.4);
			O->TryGetBoolField(TEXT("blast"), D.bBlast);
			D.bBlast |= K == TEXT("blast");
			const TArray<TSharedPtr<FJsonValue>>* Boundary = nullptr;
			if (D.bBlast && O->TryGetArrayField(TEXT("boundary"), Boundary) && Boundary->Num() >= 2)
			{
				const FString Aft = (*Boundary)[0]->AsString(), Fwd = (*Boundary)[1]->AsString();
				D.SecAft = Aft.Len() ? Aft[0] : TEXT('A');
				D.SecFwd = Fwd.Len() ? Fwd[0] : TEXT('A');
			}
			const int32 DoorIdx = Doors.Add(D);
			DoorByName.Add(D.Id, DoorIdx);
			if (D.bBlast)
			{
				BlastDoors.Add(DoorIdx);
			}
		}
	}
	// ---- the compartments
	TSet<FName> Systems;
	if (Plan->TryGetArrayField(TEXT("compartments"), List))
	{
		Comps.Reserve(List->Num());
		for (const TSharedPtr<FJsonValue>& V : *List)
		{
			const TSharedPtr<FJsonObject> O = V->AsObject();
			const TArray<TSharedPtr<FJsonValue>>* B = nullptr;
			const TArray<TSharedPtr<FJsonValue>>* Z = nullptr;
			if (!O.IsValid() || !O->TryGetArrayField(TEXT("bounds"), B) || B->Num() < 4 || !O->TryGetArrayField(TEXT("z"), Z) || Z->Num() < 2)
			{
				continue;
			}
			FAstraDmgComp C;
			C.Id = FName(*O->GetStringField(TEXT("id")));
			FString Name, Kind, Sec, Dept, St;
			O->TryGetStringField(TEXT("name"), Name);
			C.Name = DmPlaceName(Name);
			O->TryGetStringField(TEXT("kind"), Kind);
			C.Kind = FName(*Kind);
			C.Section = O->TryGetStringField(TEXT("section"), Sec) && Sec.Len() ? Sec[0] : TEXT('A');
			C.Deck = (int16)DmNum(O, TEXT("deck"), 0);
			C.DeckLo = C.DeckHi = C.Deck;
			const TArray<TSharedPtr<FJsonValue>>* Span = nullptr;
			if (O->TryGetArrayField(TEXT("spans_decks"), Span) && Span->Num())
			{
				C.DeckLo = (int16)(*Span)[0]->AsNumber();
				C.DeckHi = (int16)(*Span)[Span->Num() - 1]->AsNumber();
				C.bHall = true;
			}
			C.bHall |= Kind == TEXT("engineering") || Kind == TEXT("hangar") || Kind == TEXT("mess");
			C.Dept = O->TryGetStringField(TEXT("dept"), Dept) ? FName(*Dept) : NAME_None;
			O->TryGetStringField(TEXT("status"), St);
			C.Status = St == TEXT("existing") ? 2 : (St == TEXT("built") ? 1 : 0);
			C.Box = FBox(FVector((*B)[0]->AsNumber(), (*B)[1]->AsNumber(), (*Z)[0]->AsNumber()) * 100.0,
			             FVector((*B)[2]->AsNumber(), (*B)[3]->AsNumber(), (*Z)[1]->AsNumber()) * 100.0);
			const FVector Ext = C.Box.GetSize() / 100.0;
			C.VolumeM3 = (float)FMath::Max(1.0, Ext.X * Ext.Y * Ext.Z);
			C.FloorM2 = (float)FMath::Max(1.0, Ext.X * Ext.Y);
			C.bCorridor = Kind == TEXT("corridor") || Kind == TEXT("vestibule");
			C.Profile = (uint8)DmClassOfKind(Kind);
			C.Crew = (int32)FMath::Max(DmNum(O, TEXT("crew_slots"), 0.0), DmNum(O, TEXT("capacity"), 0.0));
			const TArray<TSharedPtr<FJsonValue>>* Sys = nullptr;
			if (O->TryGetArrayField(TEXT("systems"), Sys))
			{
				for (const TSharedPtr<FJsonValue>& SV : *Sys)
				{
					const int32 S = DmSystemOf(SV->AsString());
					if (S != INDEX_NONE)
					{
						C.Systems.AddUnique((uint8)S);
					}
				}
			}
			Hull += C.Box;
			CompByName.Add(C.Id, Comps.Add(C));
		}
	}
	if (Comps.Num() == 0)
	{
		OutError = TEXT("the plan has no compartments");
		return false;
	}
	for (int32 i = 0; i < Comps.Num(); ++i)
	{
		for (const uint8 S : Comps[i].Systems)
		{
			Hosts[S].Add(i);
		}
	}
	// ---- the graph: which compartment opens into which, and how
	const TSharedPtr<FJsonObject>* Graph = nullptr;
	if (Plan->TryGetObjectField(TEXT("graph"), Graph))
	{
		TMap<FString, int32> NodeComp;
		TMap<FString, FVector> NodePos;
		if ((*Graph)->TryGetArrayField(TEXT("nodes"), List))
		{
			for (const TSharedPtr<FJsonValue>& V : *List)
			{
				const TSharedPtr<FJsonObject> N = V->AsObject();
				FString CompId;
				const TArray<TSharedPtr<FJsonValue>>* P = nullptr;
				if (!N.IsValid() || !N->TryGetStringField(TEXT("comp"), CompId) || !N->TryGetArrayField(TEXT("p"), P))
				{
					continue;
				}
				const FString Id = N->GetStringField(TEXT("id"));
				const int32* CI = CompByName.Find(FName(*CompId));
				NodeComp.Add(Id, CI ? *CI : INDEX_NONE);
				NodePos.Add(Id, DmMetres(P));
			}
		}
		TSet<uint64> Seen;
		if ((*Graph)->TryGetArrayField(TEXT("edges"), List))
		{
			for (const TSharedPtr<FJsonValue>& V : *List)
			{
				const TSharedPtr<FJsonObject> E = V->AsObject();
				if (!E.IsValid())
				{
					continue;
				}
				const FString Ea = E->GetStringField(TEXT("a")), Eb = E->GetStringField(TEXT("b"));
				const int32* Ca = NodeComp.Find(Ea);
				const int32* Cb = NodeComp.Find(Eb);
				if (!Ca || !Cb || *Ca == INDEX_NONE || *Cb == INDEX_NONE || *Ca == *Cb)
				{
					continue;
				}
				FString K, DoorId;
				E->TryGetStringField(TEXT("kind"), K);
				E->TryGetStringField(TEXT("door"), DoorId);
				bool bBlast = false;
				E->TryGetBoolField(TEXT("blast"), bBlast);
				FAstraDmgLink L;
				const int32* DI = DoorId.Len() ? DoorByName.Find(FName(*DoorId)) : nullptr;
				const double W = DmNum(E, TEXT("w"), 3.1);
				if (K == TEXT("door") && DI)
				{
					L.Door = *DI;
					L.Kind = (bBlast || Doors[*DI].bBlast) ? FAstraDmgLink::EKind::Blast : FAstraDmgLink::EKind::Door;
					L.AreaM2 = (float)(Doors[*DI].WidthM * Doors[*DI].HeightM);
					L.AtCm = Doors[*DI].PosCm;
				}
				else if (K == TEXT("stair"))
				{
					L.Kind = FAstraDmgLink::EKind::Stair;
					L.AreaM2 = 4.f;
				}
				else if (K == TEXT("lift"))
				{
					L.Kind = FAstraDmgLink::EKind::Lift;
					L.AreaM2 = 1.5f;
				}
				else
				{
					L.Kind = FAstraDmgLink::EKind::Open;
					L.AreaM2 = (float)(W * 3.4);
				}
				if (L.Kind != FAstraDmgLink::EKind::Door && L.Kind != FAstraDmgLink::EKind::Blast)
				{
					L.AtCm = 0.5 * (NodePos.FindRef(Ea) + NodePos.FindRef(Eb));
				}
				const uint64 Key = ((uint64)FMath::Min(*Ca, *Cb) << 32) | (uint32)FMath::Max(*Ca, *Cb);
				const uint64 KeyK = Key ^ ((uint64)(uint8)L.Kind << 60) ^ ((uint64)(uint32)(L.Door + 1) << 20);
				if (Seen.Contains(KeyK))
				{
					continue;
				}
				Seen.Add(KeyK);
				L.To = *Cb;
				Comps[*Ca].Links.Add(L);
				L.To = *Ca;
				Comps[*Cb].Links.Add(L);
				if (L.Door != INDEX_NONE)
				{
					FAstraDmgDoor& D = Doors[L.Door];
					if (D.A == INDEX_NONE) { D.A = *Ca; D.B = *Cb; }
				}
			}
		}
	}
	// the decks' extremes of the body (the bridge's island is not the body of the hull)
	TopCm = -1.0e9f;
	KeelFloorCm = 1.0e9f;
	for (const FAstraDmgDeck& D : Decks)
	{
		if (D.Id >= 2)
		{
			TopCm = FMath::Max(TopCm, D.FloorCm + D.ClearCm);
			KeelFloorCm = FMath::Min(KeelFloorCm, D.FloorCm);
		}
	}
	BuildGrid();
	int32 NumLinks = 0;
	for (const FAstraDmgComp& C : Comps)
	{
		NumLinks += C.Links.Num();
	}
	UE_LOG(LogASTRA, Log, TEXT("[Damage] the plan for the damage model: %d compartments, %d doors, %d links (%.0f ms)"), Comps.Num(), Doors.Num(), NumLinks / 2,
	       (FPlatformTime::Seconds() - T0) * 1000.0);
	return true;
}

void FAstraDamageMap::BuildGrid()
{
	FBox All(ForceInit);
	for (const FAstraDmgComp& C : Comps)
	{
		All += C.Box;
	}
	GridX0 = FMath::FloorToInt(All.Min.X / CellCm);
	GridY0 = FMath::FloorToInt(All.Min.Y / CellCm);
	GridNX = FMath::FloorToInt(All.Max.X / CellCm) - GridX0 + 1;
	GridNY = FMath::FloorToInt(All.Max.Y / CellCm) - GridY0 + 1;
	Grid.Reset();
	Grid.SetNum(GridNX * GridNY);
	for (int32 i = 0; i < Comps.Num(); ++i)
	{
		const FBox& B = Comps[i].Box;
		const int32 X0 = FMath::FloorToInt(B.Min.X / CellCm) - GridX0, X1 = FMath::FloorToInt(B.Max.X / CellCm) - GridX0;
		const int32 Y0 = FMath::FloorToInt(B.Min.Y / CellCm) - GridY0, Y1 = FMath::FloorToInt(B.Max.Y / CellCm) - GridY0;
		for (int32 x = X0; x <= X1; ++x)
		{
			for (int32 y = Y0; y <= Y1; ++y)
			{
				Grid[y * GridNX + x].Add(i);
			}
		}
	}
}

int32 FAstraDamageMap::CompartmentAt(const FVector& Cm, float SlackCm) const
{
	const int32 X = FMath::FloorToInt(Cm.X / CellCm) - GridX0, Y = FMath::FloorToInt(Cm.Y / CellCm) - GridY0;
	if (X < 0 || Y < 0 || X >= GridNX || Y >= GridNY)
	{
		return INDEX_NONE;
	}
	int32 Best = INDEX_NONE;
	float BestVol = TNumericLimits<float>::Max();
	const FVector Slack(SlackCm);
	for (const int32 I : Grid[Y * GridNX + X])
	{
		const FAstraDmgComp& C = Comps[I];
		if (C.Box.ExpandBy(Slack).IsInsideOrOn(Cm) && C.VolumeM3 < BestVol)
		{
			BestVol = C.VolumeM3;
			Best = I;
		}
	}
	return Best;
}

int32 FAstraDamageMap::DeckAtZ(float ZCm) const
{
	int32 Best = 0;
	float BestFloor = -1.0e9f;
	for (const FAstraDmgDeck& D : Decks)
	{
		if (ZCm >= D.FloorCm - 100.f && ZCm < D.FloorCm + 400.f && D.FloorCm > BestFloor)
		{
			Best = D.Id;
			BestFloor = D.FloorCm;
		}
	}
	return Best;
}

FString FAstraDamageMap::Describe(int32 Comp) const
{
	if (!Comps.IsValidIndex(Comp))
	{
		return TEXT("somewhere aboard");
	}
	const FAstraDmgComp& C = Comps[Comp];
	return FString::Printf(TEXT("deck %d section %c (%s)"), C.Deck, C.Section, *C.Name);
}

const TCHAR* FAstraDamageMap::CategoryName(EAstraDmgCategory C) const
{
	static const TCHAR* const N[] = {TEXT("shields"), TEXT("weapons"), TEXT("engines"), TEXT("sensors"), TEXT("life_support"), TEXT("flight_deck")};
	return N[FMath::Clamp((int32)C, 0, (int32)EAstraDmgCategory::Num - 1)];
}
