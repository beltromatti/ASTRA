// ASTRA — VITA: the plan's rooms and the tables of life (see AstraLifeData.h).

#include "AstraLifeData.h"

#include "ASTRA.h"
#include "Dom/JsonObject.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

const TCHAR* AstraLifeActName(EAstraLifeAct A)
{
	static const TCHAR* Names[] = {TEXT("asleep"), TEXT("on duty"), TEXT("at a meal"), TEXT("off duty"), TEXT("at their battle station"),
	                               TEXT("in a repair party"), TEXT("wounded"), TEXT("dead")};
	return Names[FMath::Min<int32>((int32)A, (int32)EAstraLifeAct::Count - 1)];
}

namespace
{
	bool ReadJson(const FString& Path, TSharedPtr<FJsonObject>& Out)
	{
		FString Text;
		if (!FFileHelper::LoadFileToString(Text, *Path))
		{
			return false;
		}
		return FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Out) && Out.IsValid();
	}

	FString FindData(const TCHAR* File)
	{
		// staged with the game (Content/ASTRA/Data, always packaged as a loose file), else the repository's copy
		const FString A = FPaths::Combine(FPaths::ProjectContentDir(), TEXT("ASTRA/Data"), File);
		if (FPaths::FileExists(A))
		{
			return A;
		}
		return FPaths::Combine(FPaths::ProjectDir(), TEXT("data/ship"), File);
	}

	FVector Metres(const TArray<TSharedPtr<FJsonValue>>* A)
	{
		return A && A->Num() >= 3 ? FVector((*A)[0]->AsNumber(), (*A)[1]->AsNumber(), (*A)[2]->AsNumber()) * 100.0 : FVector::ZeroVector;
	}

	EAstraPlaceKind PlaceKindOf(const FString& K)
	{
		if (K == TEXT("sit")) { return EAstraPlaceKind::Sit; }
		if (K == TEXT("stand")) { return EAstraPlaceKind::Stand; }
		if (K == TEXT("work")) { return EAstraPlaceKind::Work; }
		if (K == TEXT("eat")) { return EAstraPlaceKind::Eat; }
		if (K == TEXT("sleep")) { return EAstraPlaceKind::Sleep; }
		if (K == TEXT("watch")) { return EAstraPlaceKind::Watch; }
		return EAstraPlaceKind::Hub;
	}

	float DefaultHeight(EAstraPlaceKind K)
	{
		switch (K)
		{
		case EAstraPlaceKind::Sit:   return 50.f;    // a chair or a sofa's seat: the hip joint this high
		case EAstraPlaceKind::Eat:   return 52.f;    // a bench at the Mess tables (tools/ue_scripts/build_messhall.py)
		case EAstraPlaceKind::Sleep: return 60.f;    // the body on a lower bunk's mattress
		default:                     return 0.f;
		}
	}

	FVector2D Range(const TSharedPtr<FJsonObject>& O, const TCHAR* Field, const FVector2D& Default)
	{
		const TArray<TSharedPtr<FJsonValue>>* A = nullptr;
		if (O.IsValid() && O->TryGetArrayField(Field, A) && A->Num() >= 2)
		{
			return FVector2D((*A)[0]->AsNumber(), (*A)[1]->AsNumber());
		}
		return Default;
	}

	double Num(const TSharedPtr<FJsonObject>& O, const TCHAR* Field, double Default)
	{
		double V = Default;
		if (O.IsValid())
		{
			O->TryGetNumberField(Field, V);
		}
		return V;
	}

	TArray<FAstraLifeSelector> Selectors(const TSharedPtr<FJsonObject>& O, const TCHAR* Field)
	{
		TArray<FAstraLifeSelector> Out;
		const TArray<TSharedPtr<FJsonValue>>* A = nullptr;
		if (!O.IsValid() || !O->TryGetArrayField(Field, A))
		{
			return Out;
		}
		for (const TSharedPtr<FJsonValue>& V : *A)
		{
			const TSharedPtr<FJsonObject> S = V->AsObject();
			if (!S.IsValid())
			{
				continue;
			}
			FAstraLifeSelector Sel;
			const TArray<TSharedPtr<FJsonValue>>* K = nullptr;
			if (S->TryGetArrayField(TEXT("kinds"), K))
			{
				for (const TSharedPtr<FJsonValue>& KV : *K)
				{
					Sel.Kinds.Add(FName(*KV->AsString()));
				}
			}
			FString D;
			if (S->TryGetStringField(TEXT("dept"), D))
			{
				Sel.Dept = FName(*D);
			}
			const TArray<TSharedPtr<FJsonValue>>* Decks = nullptr;
			if (S->TryGetArrayField(TEXT("deck"), Decks))
			{
				for (const TSharedPtr<FJsonValue>& DV : *Decks)
				{
					Sel.Decks.Add((int32)DV->AsNumber());
				}
			}
			Sel.Weight = (float)Num(S, TEXT("weight"), 1.0);
			Out.Add(MoveTemp(Sel));
		}
		return Out;
	}
}

bool FAstraLifeMap::Load(FString& OutError)
{
	const double T0 = FPlatformTime::Seconds();
	TSharedPtr<FJsonObject> Plan;
	if (!ReadJson(FindData(TEXT("aquila_plan.json")), Plan))
	{
		OutError = TEXT("no ship's plan (aquila_plan.json)");
		return false;
	}
	// ---- the decks' floors
	const TArray<TSharedPtr<FJsonValue>>* List = nullptr;
	DeckFloorCm.Init(0.f, 13);
	if (Plan->TryGetArrayField(TEXT("decks"), List))
	{
		for (const TSharedPtr<FJsonValue>& V : *List)
		{
			const TSharedPtr<FJsonObject> D = V->AsObject();
			const int32 Id = D.IsValid() ? (int32)Num(D, TEXT("id"), 0) : 0;
			if (Id >= 1 && Id < DeckFloorCm.Num())
			{
				DeckFloorCm[Id] = (float)(Num(D, TEXT("z"), 0.0) * 100.0);
			}
		}
	}
	// ---- the doors: a room whose doors are all locked is walled off (planned rooms on a built deck)
	TMap<FString, bool> DoorLocked;
	if (Plan->TryGetArrayField(TEXT("doors"), List))
	{
		for (const TSharedPtr<FJsonValue>& V : *List)
		{
			const TSharedPtr<FJsonObject> D = V->AsObject();
			bool bLocked = false;
			if (D.IsValid())
			{
				D->TryGetBoolField(TEXT("locked"), bLocked);
				DoorLocked.Add(D->GetStringField(TEXT("id")), bLocked);
			}
		}
	}
	// ---- the rooms
	TArray<TSharedPtr<FJsonObject>> RoomJson;
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
			FAstraLifeComp C;
			C.Id = FName(*O->GetStringField(TEXT("id")));
			C.Kind = FName(*O->GetStringField(TEXT("kind")));
			O->TryGetStringField(TEXT("name"), C.Name);
			FString Sec;
			C.Section = O->TryGetStringField(TEXT("section"), Sec) && Sec.Len() ? Sec[0] : TEXT('A');
			C.Deck = (int16)Num(O, TEXT("deck"), 0);
			FString Dept;
			C.Dept = O->TryGetStringField(TEXT("dept"), Dept) ? FName(*Dept) : NAME_None;
			FString St;
			O->TryGetStringField(TEXT("status"), St);
			C.Status = St == TEXT("existing") ? EAstraRoomStatus::Existing : St == TEXT("built") ? EAstraRoomStatus::Built : EAstraRoomStatus::Planned;
			C.Slots = (int32)FMath::Max(Num(O, TEXT("crew_slots"), 0.0), Num(O, TEXT("capacity"), 0.0));
			C.Box = FBox(FVector((*B)[0]->AsNumber(), (*B)[1]->AsNumber(), (*Z)[0]->AsNumber()) * 100.0,
			             FVector((*B)[2]->AsNumber(), (*B)[3]->AsNumber(), (*Z)[1]->AsNumber()) * 100.0);
			C.bCorridor = C.Kind == TEXT("corridor") || C.Kind == TEXT("vestibule");
			C.DeckLo = C.DeckHi = C.Deck;
			const TArray<TSharedPtr<FJsonValue>>* Span = nullptr;
			if (O->TryGetArrayField(TEXT("spans_decks"), Span) && Span->Num())
			{
				C.DeckLo = (int16)(*Span)[0]->AsNumber();
				C.DeckHi = (int16)(*Span)[Span->Num() - 1]->AsNumber();
				C.bHall = true;
			}
			if (C.Kind == TEXT("engineering") || C.Kind == TEXT("hangar") || C.Kind == TEXT("mess"))
			{
				C.bHall = true;
			}
			const TArray<TSharedPtr<FJsonValue>>* Doors = nullptr;
			if (O->TryGetArrayField(TEXT("doors"), Doors) && Doors->Num())
			{
				bool bAll = true;
				for (const TSharedPtr<FJsonValue>& DV : *Doors)
				{
					const bool* L = DoorLocked.Find(DV->AsString());
					bAll &= L && *L;
				}
				C.bWalled = bAll;
			}
			const int32 Idx = Comps.Add(C);
			CompByName.Add(C.Id, Idx);
			CompsByKind.FindOrAdd(C.Kind).Add(Idx);
			RoomJson.Add(O);
		}
	}
	// ---- the graph's hearts: one per room (the node of kind "room"), and the stair wells
	const TSharedPtr<FJsonObject>* Graph = nullptr;
	if (Plan->TryGetObjectField(TEXT("graph"), Graph) && (*Graph)->TryGetArrayField(TEXT("nodes"), List))
	{
		TMap<FString, FVector> WellOf;
		for (const TSharedPtr<FJsonValue>& V : *List)
		{
			const TSharedPtr<FJsonObject> N = V->AsObject();
			if (!N.IsValid())
			{
				continue;
			}
			const FString Kind = N->GetStringField(TEXT("kind"));
			FString CompId;
			if (!N->TryGetStringField(TEXT("comp"), CompId))
			{
				continue;
			}
			const int32* CI = CompByName.Find(FName(*CompId));
			const TArray<TSharedPtr<FJsonValue>>* P = nullptr;
			if (!CI || !N->TryGetArrayField(TEXT("p"), P))
			{
				continue;
			}
			if (Kind == TEXT("room") && Comps[*CI].Hub == INDEX_NONE)
			{
				FAstraLifePlace H;
				H.Id = Comps[*CI].Id;
				H.Comp = *CI;
				H.Pos = Metres(P);
				H.Kind = EAstraPlaceKind::Hub;
				H.Deck = Comps[*CI].Deck;
				H.Capacity = (int16)FMath::Clamp(FMath::Max(1, Comps[*CI].Slots), 1, 400);
				Comps[*CI].Hub = Places.Add(H);
			}
			else if (Kind == TEXT("stair"))
			{
				WellOf.Add(CompId, Metres(P));
			}
		}
		// the towers (for walking the flights when both decks exist)
		for (int32 i = 0; i < Comps.Num(); ++i)
		{
			if (Comps[i].Kind != TEXT("stairs") || !RoomJson[i].IsValid())
			{
				continue;
			}
			FAstraLifeTower T;
			const TArray<TSharedPtr<FJsonValue>>* Pos = nullptr;
			if (!RoomJson[i]->TryGetArrayField(TEXT("pos"), Pos))
			{
				continue;
			}
			T.Origin = Metres(Pos);
			T.YawDeg = (float)Num(RoomJson[i], TEXT("yaw"), 0.0);
			T.Deck = Comps[i].Deck;
			T.bBuilt = Comps[i].Status != EAstraRoomStatus::Planned;
			const FVector* W = WellOf.Find(Comps[i].Id.ToString());
			T.Well = W ? *W : Comps[i].Box.GetCenter();
			Towers.Add(T);
		}
	}
	// a room the graph gave no heart: its centre
	for (int32 i = 0; i < Comps.Num(); ++i)
	{
		FAstraLifeComp& C = Comps[i];
		if (C.Hub == INDEX_NONE && !C.bCorridor)
		{
			FAstraLifePlace H;
			H.Id = C.Id;
			H.Comp = i;
			H.Pos = FVector(C.Box.GetCenter().X, C.Box.GetCenter().Y, C.Box.Min.Z);
			H.Deck = C.Deck;
			H.Capacity = (int16)FMath::Clamp(FMath::Max(1, C.Slots), 1, 400);
			C.Hub = Places.Add(H);
		}
	}
	// ---- the stations
	for (int32 i = 0; i < Comps.Num(); ++i)
	{
		AddStations(RoomJson[i], i);
	}
	// ---- the tables of life, and the halls' posts; the berthing's racks and the Mess's extra seats are baked into the life file
	TSharedPtr<FJsonObject> Life;
	if (ReadJson(FindData(TEXT("aquila_life.json")), Life))
	{
		LoadLife(Life);
		AddHalls(Life);
		const TSharedPtr<FJsonObject>* Ex = nullptr;
		if (Life->TryGetObjectField(TEXT("extras"), Ex))
		{
			auto AddList = [this](const TSharedPtr<FJsonObject>& Extras, const TCHAR* Field, const TCHAR* RoomId, EAstraPlaceKind Kind)
			{
				const TArray<TSharedPtr<FJsonValue>>* A = nullptr;
				const int32* CI = CompByName.Find(FName(RoomId));
				if (!CI || !Extras->TryGetArrayField(Field, A))
				{
					return;
				}
				for (const TSharedPtr<FJsonValue>& V : *A)
				{
					const TSharedPtr<FJsonObject> S = V->AsObject();
					if (!S.IsValid())
					{
						continue;
					}
					FAstraLifePlace P;
					P.Id = FName(*S->GetStringField(TEXT("id")));
					P.Comp = *CI;
					P.Pos = FVector(Num(S, TEXT("x"), 0.0), Num(S, TEXT("y"), 0.0), Num(S, TEXT("z"), 0.0)) * 100.0;
					P.Yaw = (float)Num(S, TEXT("yaw"), 0.0);
					P.Kind = Kind;
					P.Deck = Comps[*CI].Deck;
					P.Height = (float)Num(S, TEXT("height_cm"), DefaultHeight(Kind));
					FString Role, Ext;
					if (S->TryGetStringField(TEXT("role"), Role))
					{
						P.Role = FName(*Role);
					}
					if (S->TryGetStringField(TEXT("external"), Ext))
					{
						P.External = FName(*Ext);
					}
					Comps[*CI].Places.Add(Places.Add(P));
				}
			};
			AddList(*Ex, TEXT("racks"), TEXT("berths"), EAstraPlaceKind::Sleep);
			AddList(*Ex, TEXT("mess_seats"), TEXT("mess"), EAstraPlaceKind::Eat);
		}
	}
	else
	{
		UE_LOG(LogASTRA, Warning, TEXT("[Life] no life tables (aquila_life.json): defaults"));
	}
	for (int32 i = 0; i < Places.Num(); ++i)
	{
		PlaceByName.Add(Places[i].Id, i);
	}
	BuildGrid();
	UE_LOG(LogASTRA, Log, TEXT("[Life] map: %d rooms, %d places, %d towers, %d departments (%.0f ms)"), Comps.Num(), Places.Num(), Towers.Num(), Depts.Num(),
	       (FPlatformTime::Seconds() - T0) * 1000.0);
	return Comps.Num() > 0;
}

void FAstraLifeMap::AddStations(const TSharedPtr<FJsonObject>& Room, int32 CompIdx)
{
	const TArray<TSharedPtr<FJsonValue>>* List = nullptr;
	if (!Room.IsValid() || !Room->TryGetArrayField(TEXT("stations"), List))
	{
		return;
	}
	for (const TSharedPtr<FJsonValue>& V : *List)
	{
		const TSharedPtr<FJsonObject> S = V->AsObject();
		const TArray<TSharedPtr<FJsonValue>>* P = nullptr;
		if (!S.IsValid() || !S->TryGetArrayField(TEXT("pos"), P))
		{
			continue;
		}
		FAstraLifePlace Pl;
		Pl.Id = FName(*S->GetStringField(TEXT("id")));
		Pl.Comp = CompIdx;
		Pl.Pos = Metres(P);
		Pl.Yaw = (float)Num(S, TEXT("yaw"), 0.0);
		Pl.Kind = PlaceKindOf(S->GetStringField(TEXT("kind")));
		Pl.Deck = Comps[CompIdx].Deck;
		Pl.Height = DefaultHeight(Pl.Kind);
		FString Ext, Role;
		if (S->TryGetStringField(TEXT("station"), Ext) && !Ext.IsEmpty())
		{
			Pl.External = FName(*Ext);
		}
		else if (Pl.Id.ToString().StartsWith(TEXT("medbay.bed")))
		{
			Pl.External = FName(*(TEXT("patient") + Pl.Id.ToString().Mid(10)));    // the ward's beds hold the roster's wounded (AAstraPatient)
		}
		if (S->TryGetStringField(TEXT("role"), Role))
		{
			Pl.Role = FName(*Role);
		}
		Comps[CompIdx].Places.Add(Places.Add(Pl));
	}
}

void FAstraLifeMap::AddHalls(const TSharedPtr<FJsonObject>& Life)
{
	const TSharedPtr<FJsonObject>* Halls = nullptr;
	if (!Life->TryGetObjectField(TEXT("halls"), Halls))
	{
		return;
	}
	static const TCHAR* Rooms[][2] = {{TEXT("engineering"), TEXT("engineering")}, {TEXT("flight_deck"), TEXT("flight_deck")},
	                                  {TEXT("medbay"), TEXT("medbay")}, {TEXT("mess"), TEXT("mess")}};
	for (const auto& R : Rooms)
	{
		const TArray<TSharedPtr<FJsonValue>>* Posts = nullptr;
		const int32* CI = CompByName.Find(FName(R[1]));
		if (!CI || !(*Halls)->TryGetArrayField(R[0], Posts))
		{
			continue;
		}
		int32 N = 0;
		for (const TSharedPtr<FJsonValue>& V : *Posts)
		{
			const TSharedPtr<FJsonObject> S = V->AsObject();
			if (!S.IsValid())
			{
				continue;
			}
			FAstraLifePlace P;
			P.Id = FName(*FString::Printf(TEXT("%s.post%d"), R[1], N++));
			P.Comp = *CI;
			// on the hall's floor (its box reaches a little below it: the slab)
			const double Floor = Comps[*CI].Hub != INDEX_NONE ? Places[Comps[*CI].Hub].Pos.Z : Comps[*CI].Box.Min.Z;
			P.Pos = FVector(Num(S, TEXT("x"), 0.0) * 100.0, Num(S, TEXT("y"), 0.0) * 100.0, Floor);
			P.Yaw = (float)Num(S, TEXT("yaw"), 0.0);
			P.Kind = PlaceKindOf(S->GetStringField(TEXT("kind")));
			P.Deck = Comps[*CI].Deck;
			FString Role;
			if (S->TryGetStringField(TEXT("role"), Role))
			{
				P.Role = FName(*Role);
			}
			Comps[*CI].Places.Add(Places.Add(P));
		}
	}
}

void FAstraLifeMap::LoadLife(const TSharedPtr<FJsonObject>& Life)
{
	if (const TSharedPtr<FJsonObject>* Clock = nullptr; Life->TryGetObjectField(TEXT("clock"), Clock))
	{
		TimeScale = (float)Num(*Clock, TEXT("time_scale"), TimeScale);
		StartHour = (float)Num(*Clock, TEXT("start_hour"), StartHour);
	}
	const TArray<TSharedPtr<FJsonValue>>* List = nullptr;
	if (Life->TryGetArrayField(TEXT("watches"), List))
	{
		for (const TSharedPtr<FJsonValue>& V : *List)
		{
			const TSharedPtr<FJsonObject> W = V->AsObject();
			if (W.IsValid())
			{
				Watches.Add({W->GetStringField(TEXT("name")), (float)Num(W, TEXT("start"), 0.0)});
			}
		}
	}
	if (Watches.Num() == 0)
	{
		Watches = {{TEXT("Red"), 0.f}, {TEXT("Gold"), 8.f}, {TEXT("Blue"), 16.f}};
	}
	if (const TSharedPtr<FJsonObject>* D = nullptr; Life->TryGetObjectField(TEXT("day"), D))
	{
		Day.DutyFirst = (float)Num(*D, TEXT("duty_first"), Day.DutyFirst);
		Day.MealLen = (float)Num(*D, TEXT("meal_len"), Day.MealLen);
		Day.WindDown = (float)Num(*D, TEXT("wind_down"), Day.WindDown);
		Day.SleepStart = (float)Num(*D, TEXT("sleep_start"), Day.SleepStart);
		Day.SleepLen = (float)Num(*D, TEXT("sleep_len"), Day.SleepLen);
		Day.MealBefore = (float)Num(*D, TEXT("meal_before"), Day.MealBefore);
		if (const TSharedPtr<FJsonObject>* J = nullptr; (*D)->TryGetObjectField(TEXT("jitter"), J))
		{
			Day.J1 = Range(*J, TEXT("j1"), Day.J1);
			Day.J2 = Range(*J, TEXT("j2"), Day.J2);
			Day.J3 = Range(*J, TEXT("j3"), Day.J3);
			Day.J4 = Range(*J, TEXT("j4"), Day.J4);
			Day.JSleep = Range(*J, TEXT("sleep_len"), Day.JSleep);
		}
		Day.WakeDelayS = Range(*D, TEXT("wake_delay_s"), Day.WakeDelayS);
	}
	if (const TSharedPtr<FJsonObject>* S = nullptr; Life->TryGetObjectField(TEXT("speed"), S))
	{
		Speed.WalkCmS = (float)Num(*S, TEXT("walk_cm_s"), Speed.WalkCmS);
		Speed.HurryCmS = (float)Num(*S, TEXT("hurry_cm_s"), Speed.HurryCmS);
		Speed.Spread = (float)Num(*S, TEXT("spread"), Speed.Spread);
		Speed.StairsS = (float)Num(*S, TEXT("stairs_s"), Speed.StairsS);
		Speed.LiftS = (float)Num(*S, TEXT("lift_s"), Speed.LiftS);
	}
	if (const TSharedPtr<FJsonObject>* V = nullptr; Life->TryGetObjectField(TEXT("visibility"), V))
	{
		Vis.MaxBodies = (int32)Num(*V, TEXT("max_bodies"), Vis.MaxBodies);
		Vis.SpawnM = (float)Num(*V, TEXT("spawn_m"), Vis.SpawnM);
		Vis.DespawnM = (float)Num(*V, TEXT("despawn_m"), Vis.DespawnM);
		Vis.DeckBandCm = (float)Num(*V, TEXT("deck_band_cm"), Vis.DeckBandCm);
	}
	if (const TSharedPtr<FJsonObject>* W = nullptr; Life->TryGetObjectField(TEXT("room_weights"), W))
	{
		StatusWeight[0] = (float)Num(*W, TEXT("planned"), StatusWeight[0]);
		StatusWeight[1] = (float)Num(*W, TEXT("built"), StatusWeight[1]);
		StatusWeight[2] = (float)Num(*W, TEXT("existing"), StatusWeight[2]);
	}
	if (const TSharedPtr<FJsonObject>* Jobs = nullptr; Life->TryGetObjectField(TEXT("jobs"), Jobs))
	{
		if (const TSharedPtr<FJsonObject>* By = nullptr; (*Jobs)->TryGetObjectField(TEXT("by_room"), By))
		{
			for (const auto& KV : (*By)->Values)
			{
				JobByRoom.Add(FName(*KV.Key), KV.Value->AsString());
			}
		}
	}
	if (const TSharedPtr<FJsonObject>* Ds = nullptr; Life->TryGetObjectField(TEXT("departments"), Ds))
	{
		for (const auto& KV : (*Ds)->Values)
		{
			const TSharedPtr<FJsonObject> O = KV.Value->AsObject();
			if (!O.IsValid())
			{
				continue;
			}
			FAstraLifeDept D;
			const FString DeptKey(*KV.Key);
			D.Name = DeptKey;
			FString S;
			D.PlanDept = O->TryGetStringField(TEXT("plan_dept"), S) ? FName(*S) : NAME_None;
			const FString Cls = O->TryGetStringField(TEXT("class"), S) ? S : FString(TEXT("rating"));
			D.Class = Cls == TEXT("officer") ? EAstraLifeClass::Officer : Cls == TEXT("marine") ? EAstraLifeClass::Marine : EAstraLifeClass::Rating;
			O->TryGetStringField(TEXT("job"), D.Job);
			D.Duty = Selectors(O, TEXT("duty"));
			D.Battle = Selectors(O, TEXT("battle"));
			O->TryGetBoolField(TEXT("yellow"), D.bYellow);
			Depts.Add(DeptKey, MoveTemp(D));
		}
	}
	if (const TSharedPtr<FJsonObject>* Hm = nullptr; Life->TryGetObjectField(TEXT("homes"), Hm))
	{
		HomeMarine = Selectors(*Hm, TEXT("marine"));
		HomeOfficer = Selectors(*Hm, TEXT("officer"));
		HomeRating = Selectors(*Hm, TEXT("rating"));
	}
	if (const TSharedPtr<FJsonObject>* Lz = nullptr; Life->TryGetObjectField(TEXT("leisure"), Lz))
	{
		if ((*Lz)->TryGetArrayField(TEXT("kinds"), List))
		{
			for (const TSharedPtr<FJsonValue>& V : *List)
			{
				const TSharedPtr<FJsonObject> O = V->AsObject();
				if (!O.IsValid())
				{
					continue;
				}
				FAstraLifeLeisure L;
				L.Id = FName(*O->GetStringField(TEXT("id")));
				const TArray<TSharedPtr<FJsonValue>>* K = nullptr;
				if (O->TryGetArrayField(TEXT("kinds"), K))
				{
					for (const TSharedPtr<FJsonValue>& KV : *K)
					{
						L.Kinds.Add(FName(*KV->AsString()));
					}
				}
				L.Taste = Range(O, TEXT("taste"), L.Taste);
				O->TryGetStringField(TEXT("label"), L.Label);
				Leisure.Add(MoveTemp(L));
			}
		}
	}
	if (const TSharedPtr<FJsonObject>* M = nullptr; Life->TryGetObjectField(TEXT("meals"), M))
	{
		const TArray<TSharedPtr<FJsonValue>>* K = nullptr;
		if ((*M)->TryGetArrayField(TEXT("kinds"), K))
		{
			for (const TSharedPtr<FJsonValue>& KV : *K)
			{
				MealKinds.Add(FName(*KV->AsString()));
			}
		}
		(*M)->TryGetStringField(TEXT("menu"), Menu);
	}
	if (const TSharedPtr<FJsonObject>* C = nullptr; Life->TryGetObjectField(TEXT("casualty"), C))
	{
		const TArray<TSharedPtr<FJsonValue>>* K = nullptr;
		if ((*C)->TryGetArrayField(TEXT("medbay_kinds"), K))
		{
			for (const TSharedPtr<FJsonValue>& KV : *K)
			{
				MedbayKinds.Add(FName(*KV->AsString()));
			}
		}
	}
	if (const TSharedPtr<FJsonObject>* T = nullptr; Life->TryGetObjectField(TEXT("teams"), T))
	{
		Teams.Count = (int32)Num(*T, TEXT("count"), Teams.Count);
		Teams.Size = (int32)Num(*T, TEXT("size"), Teams.Size);
		Teams.Min = (int32)Num(*T, TEXT("min"), Teams.Min);
		Teams.JogCmS = (float)Num(*T, TEXT("jog_cm_s"), Teams.JogCmS);
		(*T)->TryGetStringField(TEXT("dept"), Teams.Dept);
		(*T)->TryGetStringField(TEXT("backup_dept"), Teams.BackupDept);
		const TArray<TSharedPtr<FJsonValue>>* K = nullptr;
		if ((*T)->TryGetArrayField(TEXT("locker_kinds"), K))
		{
			for (const TSharedPtr<FJsonValue>& KV : *K)
			{
				Teams.LockerKinds.Add(FName(*KV->AsString()));
			}
		}
	}
	if (MealKinds.Num() == 0)
	{
		MealKinds = {FName(TEXT("mess"))};
	}
	if (MedbayKinds.Num() == 0)
	{
		MedbayKinds = {FName(TEXT("medbay"))};
	}
	if (Teams.LockerKinds.Num() == 0)
	{
		Teams.LockerKinds = {FName(TEXT("damage_control"))};
	}
}

void FAstraLifeMap::BuildGrid()
{
	FBox All(ForceInit);
	for (const FAstraLifeComp& C : Comps)
	{
		All += C.Box;
	}
	if (!All.IsValid)
	{
		return;
	}
	GridX0 = FMath::FloorToInt(All.Min.X / CellCm);
	GridY0 = FMath::FloorToInt(All.Min.Y / CellCm);
	GridNX = FMath::FloorToInt(All.Max.X / CellCm) - GridX0 + 1;
	GridNY = FMath::FloorToInt(All.Max.Y / CellCm) - GridY0 + 1;
	Grid.SetNum(GridNX * GridNY);
	for (int32 i = 0; i < Comps.Num(); ++i)
	{
		const FBox& B = Comps[i].Box;
		const int32 X0 = FMath::FloorToInt(B.Min.X / CellCm) - GridX0, X1 = FMath::FloorToInt(B.Max.X / CellCm) - GridX0;
		const int32 Y0 = FMath::FloorToInt(B.Min.Y / CellCm) - GridY0, Y1 = FMath::FloorToInt(B.Max.Y / CellCm) - GridY0;
		for (int32 X = X0; X <= X1; ++X)
		{
			for (int32 Y = Y0; Y <= Y1; ++Y)
			{
				Grid[Y * GridNX + X].Add(i);
			}
		}
	}
}

int32 FAstraLifeMap::CompartmentAt(const FVector& Cm) const
{
	const int32 X = FMath::FloorToInt(Cm.X / CellCm) - GridX0, Y = FMath::FloorToInt(Cm.Y / CellCm) - GridY0;
	if (X < 0 || Y < 0 || X >= GridNX || Y >= GridNY)
	{
		return INDEX_NONE;
	}
	int32 Best = INDEX_NONE;
	double BestV = TNumericLimits<double>::Max();
	for (const int32 i : Grid[Y * GridNX + X])
	{
		if (Comps[i].Box.IsInsideOrOn(Cm))
		{
			const double V = Comps[i].Box.GetVolume();
			if (V < BestV)
			{
				BestV = V;
				Best = i;
			}
		}
	}
	return Best;
}

int32 FAstraLifeMap::DeckAt(const FVector& Cm) const
{
	const int32 C = CompartmentAt(Cm);
	if (C != INDEX_NONE)
	{
		return Comps[C].Deck;
	}
	int32 Best = 1;
	for (int32 D = 1; D < DeckFloorCm.Num(); ++D)
	{
		if (DeckFloorCm[D] <= Cm.Z + 120.f && (DeckFloorCm[D] > DeckFloorCm[Best] || DeckFloorCm[Best] > Cm.Z + 120.f))
		{
			Best = D;
		}
	}
	return Best;
}

FString FAstraLifeMap::Describe(int32 CompIdx) const
{
	if (!Comps.IsValidIndex(CompIdx))
	{
		return TEXT("somewhere aboard");
	}
	const FAstraLifeComp& C = Comps[CompIdx];
	return FString::Printf(TEXT("Deck %d · Section %c · %s"), C.Deck, C.Section, C.Name.IsEmpty() ? *C.Kind.ToString() : *C.Name);
}
