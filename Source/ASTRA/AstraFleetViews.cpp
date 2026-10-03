// ASTRA — FLOTTA-VIVA: what is said of a ship's inside (see AstraFleetInterior.h): to the minds of her own side (everything her captain knows), to an
// observer's sensors (what a hull shows and what a track's emissions give away), to the holo table, and to the bench.

#include "AstraFleetInterior.h"

#include "ASTRA.h"

namespace
{
	TSharedRef<FJsonValueNumber> Num(double V) { return MakeShared<FJsonValueNumber>(V); }

	/** How a room stands: ok | damaged | lost. */
	const TCHAR* FleetRoomState(const FAstraDamageModel& M, int32 Comp)
	{
		const FAstraDmgState* S = Comp != INDEX_NONE ? M.Find(Comp) : nullptr;
		if (!S)
		{
			return TEXT("ok");
		}
		if (S->bGutted || S->Wreck >= 1.f)
		{
			return TEXT("lost");
		}
		return (S->Power < 0.5f || S->Wreck > 0.3f || S->Fire > 0.3f || S->Air < 0.5f || S->Hole >= 0.12f) ? TEXT("damaged") : TEXT("ok");
	}

	const TCHAR* FleetCategoryName(int32 C)
	{
		static const TCHAR* const N[] = {TEXT("shields"), TEXT("weapons"), TEXT("engines"), TEXT("sensors"), TEXT("life_support"), TEXT("flight_deck")};
		return N[FMath::Clamp(C, 0, 5)];
	}
}

void FAstraShipInterior::FillView(FAstraFleetView& Out, int32 Detail) const
{
	Out = FAstraFleetView();
	Out.Detail = Detail;
	if (Detail >= 2)
	{
		Out.CrewTotal = People.Num();
		Out.CrewFit = Fit;
		Out.CrewWounded = Wounded;
		Out.CrewDead = Dead;
	}
	const FAstraDamageMap& M = *Plan->Map;
	for (const auto& KV : Model.States())
	{
		const FAstraDmgState& S = KV.Value;
		if (S.Fire >= 0.10f)
		{
			++Out.Fires;
			Out.FireM.Add(FVector(S.FireAt.IsNearlyZero() ? M.Comps[KV.Key].Box.GetCenter() : S.FireAt) / 100.0 + M.OriginInHullM);
		}
		if (S.Hole >= 0.12f)
		{
			++Out.Breaches;
			Out.BreachM.Add(FVector(S.HoleAt.IsNearlyZero() ? M.Comps[KV.Key].Box.GetCenter() : S.HoleAt) / 100.0 + M.OriginInHullM);
		}
		Out.Dark += (S.Power < 0.5f || S.Wreck >= 1.f) ? 1 : 0;
	}
	if (Detail >= 3)
	{
		for (int32 c = 0; c < 6; ++c)
		{
			Out.Power[c] = Model.Power().Factor[c];
		}
		Out.Parties = Parties.Num();
		for (const FFleetPartyState& P : Parties)
		{
			Out.PartiesBusy += P.Incident != 0 ? 1 : 0;
		}
		Out.BulkheadsShut = Model.SealedDoors().Num();
		Out.bCaptainDown = CaptainState() == 1;
		Out.bCaptainDead = CaptainState() == 2;
		if (const FFleetNamed* C = Commander())
		{
			Out.Command = FString::Printf(TEXT("%s %s (%s)"), *C->Rank, *C->Name, AstraFleetBilletWord(C->Role));
		}
	}
}

TSharedRef<FJsonObject> FAstraShipInterior::BriefJson() const
{
	TSharedRef<FJsonObject> J = MakeShared<FJsonObject>();
	const FAstraDamageMap& M = *Plan->Map;
	if (Dead || Wounded)
	{
		TSharedRef<FJsonObject> C = MakeShared<FJsonObject>();
		C->SetNumberField(TEXT("fit"), Fit);
		C->SetNumberField(TEXT("wounded"), Wounded);
		C->SetNumberField(TEXT("killed"), Dead);
		C->SetNumberField(TEXT("of"), People.Num());
		J->SetObjectField(TEXT("crew"), C);
	}
	// who commands: said only when the captain is not fit (the chain of command passes down the ship's own billets)
	const int32 Cap = CaptainState();
	if (Cap != 0)
	{
		const FFleetNamed* Now = Commander();
		FString Text = Cap == 2 ? TEXT("the captain is dead") : TEXT("the captain is wounded");
		for (const FFleetNamed& N : Named)
		{
			if (N.Role == FName(TEXT("captain")))
			{
				Text = FString::Printf(TEXT("%s %s is %s"), *N.Rank, *N.Name, Cap == 2 ? TEXT("dead") : TEXT("down, wounded"));
			}
		}
		Text += Now ? FString::Printf(TEXT("; %s %s (%s) has the conn"), *Now->Rank, *Now->Name, AstraFleetBilletWord(Now->Role)) : FString(TEXT("; no officer of the chain is fit"));
		J->SetStringField(TEXT("command"), Text);
	}
	const int32 NFire = Fires(), NHole = Breaches(), NDark = DarkRooms();
	if (NFire)
	{
		J->SetNumberField(TEXT("fires"), NFire);
	}
	if (NHole)
	{
		J->SetNumberField(TEXT("breaches"), NHole);
	}
	if (NDark)
	{
		J->SetNumberField(TEXT("rooms_without_power"), NDark);
	}
	// the allocations the ship's distribution no longer carries in full
	TSharedRef<FJsonObject> Pw = MakeShared<FJsonObject>();
	bool bPower = false;
	for (int32 c = 0; c < 6; ++c)
	{
		const float F = Model.Power().Factor[c];
		if (F < 0.95f && c != (int32)EAstraDmgCategory::LifeSupport)
		{
			Pw->SetNumberField(FleetCategoryName(c), FMath::RoundToInt(100.f * F));
			bPower = true;
		}
	}
	if (bPower)
	{
		J->SetObjectField(TEXT("power_pct"), Pw);
	}
	if (Model.SealedDoors().Num())
	{
		J->SetNumberField(TEXT("pressure_bulkheads_shut"), Model.SealedDoors().Num());
	}
	// damage control: the worst of what is going on, and who is on it
	if (Incidents.Num())
	{
		TArray<const FAstraDamage*> Sorted;
		for (const FAstraDamage& D : Incidents)
		{
			Sorted.Add(&D);
		}
		Sorted.Sort([](const FAstraDamage& A, const FAstraDamage& B) { return A.Severity > B.Severity; });
		TArray<TSharedPtr<FJsonValue>> Worst;
		for (int32 i = 0; i < FMath::Min(3, Sorted.Num()); ++i)
		{
			const FAstraDamage& D = *Sorted[i];
			FString Team = D.Team < 0 ? FString(TEXT("no party free")) : (D.Travel > 0.f ? FString::Printf(TEXT("a party on its way, %.0f s"), D.Travel) : FString(TEXT("a party working it")));
			Worst.Add(MakeShared<FJsonValueString>(FString::Printf(TEXT("%s in the %s (%s): %s"), *D.Kind, *D.Place, *D.Note, *Team)));
		}
		J->SetArrayField(TEXT("worst"), Worst);
		int32 Busy = 0;
		for (const FFleetPartyState& P : Parties)
		{
			Busy += P.Incident != 0 ? 1 : 0;
		}
		J->SetStringField(TEXT("damage_parties"), FString::Printf(TEXT("%d of %d at work"), Busy, Parties.Num()));
	}
	// the rooms a ship is fought from: only the ones that are not as they were
	TSharedRef<FJsonObject> Ob = MakeShared<FJsonObject>();
	bool bOb = false;
	for (const TCHAR* Key : {TEXT("bridge"), TEXT("engineering"), TEXT("armory"), TEXT("medbay"), TEXT("comms"), TEXT("hangar")})
	{
		const TCHAR* St = FleetRoomState(Model, Plan->Objective(Key));
		if (FCString::Strcmp(St, TEXT("ok")) != 0)
		{
			Ob->SetStringField(Key, St);
			bOb = true;
		}
	}
	if (bOb)
	{
		J->SetObjectField(TEXT("rooms"), Ob);
	}
	(void)M;
	return J;
}

TSharedRef<FJsonObject> FAstraShipInterior::SeenJson(int32 Detail) const
{
	TSharedRef<FJsonObject> J = MakeShared<FJsonObject>();
	if (Detail <= 0)
	{
		return J;
	}
	// what the eye sees of a hull: the atmosphere streaming out of a breach, windows gone dark
	const int32 NHole = Breaches();
	if (NHole)
	{
		J->SetNumberField(TEXT("breaches_venting"), NHole);
	}
	TSet<int32> DarkSec;
	for (const auto& KV : Model.States())
	{
		if (KV.Value.Power < 0.3f || KV.Value.Wreck >= 1.f || KV.Value.bGutted)
		{
			DarkSec.Add(WarSectionOf(KV.Key));
		}
	}
	if (DarkSec.Num())
	{
		static const TCHAR* const Names[3] = {TEXT("bow"), TEXT("mid"), TEXT("stern")};
		FString L;
		for (int32 s = 0; s < 3; ++s)
		{
			if (DarkSec.Contains(s))
			{
				L += (L.IsEmpty() ? TEXT("") : TEXT(", ")) + FString(Names[s]);
			}
		}
		J->SetStringField(TEXT("windows_dark_in"), L);
	}
	if (Detail >= 2)
	{
		// what a classified track's emissions give away: hot spots, the life signs (to the nearest five per cent), how much of the power is gone
		if (Fires())
		{
			J->SetNumberField(TEXT("fires_aboard"), Fires());
		}
		if (People.Num() && (Dead || Wounded))
		{
			J->SetNumberField(TEXT("life_signs_pct"), 5 * FMath::RoundToInt(100.f * (float)(Fit + Wounded) / (float)People.Num() / 5.f));
		}
		bool bPower = false;
		TSharedRef<FJsonObject> Pw = MakeShared<FJsonObject>();
		for (int32 c = 0; c < 6; ++c)
		{
			if (c == (int32)EAstraDmgCategory::LifeSupport)
			{
				continue;
			}
			const float F = Model.Power().Factor[c];
			if (F < 0.8f)
			{
				Pw->SetNumberField(FleetCategoryName(c), 10 * FMath::RoundToInt(10.f * F));
				bPower = true;
			}
		}
		if (bPower)
		{
			J->SetObjectField(TEXT("power_pct"), Pw);
		}
	}
	return J;
}

void FAstraShipInterior::CollectNews(TArray<FString>& Out)
{
	// the crew falling away: told as it crosses three quarters, a half and a quarter
	const float S = CrewStrength();
	const int32 Band = S >= 0.75f ? 0 : (S >= 0.5f ? 1 : (S >= 0.25f ? 2 : 3));
	if (Band > ToldCrewBand)
	{
		ToldCrewBand = Band;
		Out.Add(FString::Printf(TEXT("%s: crew down to %d%% (%d killed, %d wounded of %d)"), *ShipName, FMath::RoundToInt(100.f * S), Dead, Wounded, People.Num()));
	}
	// the captain, and who has the conn
	const int32 Cap = CaptainState();
	if (Cap > ToldCaptain)
	{
		ToldCaptain = Cap;
		FString Who = TEXT("the captain");
		for (const FFleetNamed& N : Named)
		{
			if (N.Role == FName(TEXT("captain")))
			{
				Who = FString::Printf(TEXT("%s %s"), *N.Rank, *N.Name);
			}
		}
		const FFleetNamed* Now = Commander();
		Out.Add(FString::Printf(TEXT("%s: %s is %s%s"), *ShipName, *Who, Cap == 2 ? TEXT("dead") : TEXT("down, wounded"),
		                        Now ? *FString::Printf(TEXT("; %s %s (%s) has the conn"), *Now->Rank, *Now->Name, AstraFleetBilletWord(Now->Role)) : TEXT("; no officer of the chain is fit")));
	}
	// the guns and the drive losing a fifth of their power
	const float W = Model.Power().Factor[(int32)EAstraDmgCategory::Weapons], E = Model.Power().Factor[(int32)EAstraDmgCategory::Engines];
	if (W < 0.8f && !bToldWeapons)
	{
		bToldWeapons = true;
		Out.Add(FString::Printf(TEXT("%s: weapons power down to %d%%"), *ShipName, FMath::RoundToInt(100.f * W)));
	}
	else if (W >= 0.95f)
	{
		bToldWeapons = false;
	}
	if (E < 0.8f && !bToldEngines)
	{
		bToldEngines = true;
		Out.Add(FString::Printf(TEXT("%s: engine power down to %d%%"), *ShipName, FMath::RoundToInt(100.f * E)));
	}
	else if (E >= 0.95f)
	{
		bToldEngines = false;
	}
	// a fire where the ammunition is: the one thing aboard that can take the ship
	if (Clock - ToldMagazineAt > 40.f)
	{
		for (const auto& KV : Model.States())
		{
			if (KV.Value.Fire >= 0.25f && Plan->Map->Comps[KV.Key].Systems.Contains((uint8)EAstraDmgSystem::Ordnance))
			{
				ToldMagazineAt = Clock;
				Out.Add(FString::Printf(TEXT("%s: fire in a magazine (%s)"), *ShipName, *RoomWord(KV.Key)));
				break;
			}
		}
	}
}

FString FAstraShipInterior::InfoText() const
{
	return FString::Printf(TEXT("%s (%s): crew %d fit %d wounded %d dead of %d; %d fires, %d breaches, %d dark rooms; %s | %s"), *ShipName, *Plan->Key.ToString(), Fit, Wounded, Dead, People.Num(),
	                       Fires(), Breaches(), DarkRooms(), Incidents.Num() ? *FString::Printf(TEXT("%d incidents"), Incidents.Num()) : TEXT("calm"), *Model.InfoText());
}

TSharedRef<FJsonObject> FAstraShipInterior::BooksJson() const
{
	const FAstraDamageModel::FBooks& B = Model.Books();
	TSharedRef<FJsonObject> J = MakeShared<FJsonObject>();
	J->SetNumberField(TEXT("hits"), Hits);
	J->SetNumberField(TEXT("inside"), HitsInside);
	J->SetNumberField(TEXT("holes"), B.Holes);
	J->SetNumberField(TEXT("fires"), B.Fires);
	J->SetNumberField(TEXT("conduits"), B.Conduits);
	J->SetNumberField(TEXT("wrecks"), B.Wrecks);
	J->SetNumberField(TEXT("doors_sealed"), B.DoorsSealed);
	J->SetNumberField(TEXT("explosions"), B.Explosions);
	J->SetNumberField(TEXT("fields_failed"), B.FieldsFailed);
	J->SetNumberField(TEXT("crew"), People.Num());
	J->SetNumberField(TEXT("fit"), Fit);
	J->SetNumberField(TEXT("wounded"), Wounded);
	J->SetNumberField(TEXT("killed"), Dead);
	J->SetNumberField(TEXT("rescued"), B.Rescued);
	J->SetNumberField(TEXT("active_rooms"), Model.States().Num());
	J->SetNumberField(TEXT("max_active_rooms"), B.MaxActive);
	J->SetNumberField(TEXT("incidents"), Incidents.Num());
	J->SetNumberField(TEXT("max_incidents"), B.MaxIncidents);
	J->SetNumberField(TEXT("burn"), B.StructureBurnt);
	for (int32 c = 0; c < 6; ++c)
	{
		J->SetNumberField(FString::Printf(TEXT("factor_%s"), FleetCategoryName(c)), FMath::RoundToDouble(Model.Power().Factor[c] * 1000.0) / 1000.0);
	}
	J->SetBoolField(TEXT("captain_down"), CaptainState() == 1);
	J->SetBoolField(TEXT("captain_dead"), CaptainState() == 2);
	return J;
}
