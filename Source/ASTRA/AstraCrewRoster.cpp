// ASTRA — the Aquila's company.

#include "AstraCrewRoster.h"

namespace
{
	// many peoples, one navy (names transliterated to English)
	const TCHAR* FirstNames[] = {
		TEXT("Amara"), TEXT("Jonas"), TEXT("Mei"), TEXT("Tomasz"), TEXT("Aisha"), TEXT("Diego"), TEXT("Ingrid"), TEXT("Kwame"),
		TEXT("Sofia"), TEXT("Ravi"), TEXT("Elin"), TEXT("Mateo"), TEXT("Yara"), TEXT("Hiroshi"), TEXT("Leila"), TEXT("Oskar"),
		TEXT("Nadia"), TEXT("Emeka"), TEXT("Chiara"), TEXT("Arjun"), TEXT("Freya"), TEXT("Tariq"), TEXT("Lucia"), TEXT("Sven"),
		TEXT("Zanele"), TEXT("Kai"), TEXT("Marisol"), TEXT("Dmitri"), TEXT("Anika"), TEXT("Bruno"), TEXT("Hana"), TEXT("Idris"),
		TEXT("Paloma"), TEXT("Nikolai"), TEXT("Priya"), TEXT("Lars"), TEXT("Fatima"), TEXT("Tiago"), TEXT("Astrid"), TEXT("Kofi"),
		TEXT("Giulia"), TEXT("Rohan"), TEXT("Maren"), TEXT("Salvador"), TEXT("Noor"), TEXT("Kenji"), TEXT("Imani"), TEXT("Pavel"),
		TEXT("Camila"), TEXT("Anders"), TEXT("Soraya"), TEXT("Obi"), TEXT("Elena"), TEXT("Wei"), TEXT("Adaeze"), TEXT("Matthias"),
		TEXT("Luana"), TEXT("Farid"), TEXT("Sigrid"), TEXT("Andres"), TEXT("Keiko"), TEXT("Yusuf"), TEXT("Ines"), TEXT("Bjorn"),
		TEXT("Thandiwe"), TEXT("Rafael"), TEXT("Aiko"), TEXT("Samir"), TEXT("Vera"), TEXT("Tobias"), TEXT("Esi"), TEXT("Marco"),
		TEXT("Linnea"), TEXT("Jamal"), TEXT("Rosa"), TEXT("Aleksander"), TEXT("Min-jun"), TEXT("Ayla"), TEXT("Pedro"), TEXT("Katya"),
		TEXT("Dario"), TEXT("Nia"), TEXT("Hugo"), TEXT("Sana"), TEXT("Emil"), TEXT("Olga"), TEXT("Ibrahim"), TEXT("Clara"),
		TEXT("Rustam"), TEXT("Tove"), TEXT("Ade"), TEXT("Beatriz"), TEXT("Ren"), TEXT("Halima"), TEXT("Stefan"), TEXT("Maya")};
	const TCHAR* LastNames[] = {
		TEXT("Diallo"), TEXT("Berg"), TEXT("Tanaka"), TEXT("Kowalski"), TEXT("Rahman"), TEXT("Alvarez"), TEXT("Lindgren"), TEXT("Mensah"),
		TEXT("Moretti"), TEXT("Iyer"), TEXT("Sandberg"), TEXT("Fuentes"), TEXT("Haddad"), TEXT("Sato"), TEXT("Karimi"), TEXT("Nystrom"),
		TEXT("Petrova"), TEXT("Okafor"), TEXT("Ricci"), TEXT("Patel"), TEXT("Halvorsen"), TEXT("Aziz"), TEXT("Navarro"), TEXT("Eriksen"),
		TEXT("Dlamini"), TEXT("Nakamura"), TEXT("Ortega"), TEXT("Volkov"), TEXT("Schreiber"), TEXT("Costa"), TEXT("Kimura"), TEXT("Bello"),
		TEXT("Serrano"), TEXT("Orlov"), TEXT("Sharma"), TEXT("Holm"), TEXT("El-Amin"), TEXT("Ferreira"), TEXT("Lund"), TEXT("Boateng"),
		TEXT("Romano"), TEXT("Mehta"), TEXT("Strand"), TEXT("Castillo"), TEXT("Hosseini"), TEXT("Watanabe"), TEXT("Nwosu"), TEXT("Novak"),
		TEXT("Reyes"), TEXT("Dahl"), TEXT("Farahani"), TEXT("Adeyemi"), TEXT("Marchetti"), TEXT("Zhang"), TEXT("Obi"), TEXT("Keller"),
		TEXT("Kahale"), TEXT("Nasser"), TEXT("Solberg"), TEXT("Medina"), TEXT("Ishikawa"), TEXT("Yilmaz"), TEXT("Barros"), TEXT("Voigt"),
		TEXT("Mokoena"), TEXT("Lopes"), TEXT("Hayashi"), TEXT("Qureshi"), TEXT("Ivanova"), TEXT("Brandt"), TEXT("Owusu"), TEXT("Conti"),
		TEXT("Wallin"), TEXT("Carter"), TEXT("Delgado"), TEXT("Sokolov"), TEXT("Park"), TEXT("Demir"), TEXT("Silva"), TEXT("Markovic"),
		TEXT("Vitale"), TEXT("Achebe"), TEXT("Laurent"), TEXT("Chaudhry"), TEXT("Engel"), TEXT("Kuznetsova"), TEXT("Suleiman"), TEXT("Moreau"),
		TEXT("Aliyev"), TEXT("Sjoberg"), TEXT("Adebayo"), TEXT("Rocha"), TEXT("Fujita"), TEXT("Abdi"), TEXT("Hartmann"), TEXT("Quinn"),
		TEXT("O'Rourke"), TEXT("Kaur"), TEXT("Mbeki"), TEXT("Bianchi"), TEXT("Vasquez"), TEXT("Jensen"), TEXT("Takahashi"), TEXT("Nkemelu")};
	// where they come from: mostly the March and the old Core; a few crossed over from the Outer Worlds
	const TCHAR* Homes[] = {
		TEXT("New Ravenna"), TEXT("New Ravenna"), TEXT("New Ravenna"), TEXT("New Ravenna"), TEXT("New Ravenna"),
		TEXT("Halcyon"), TEXT("Halcyon"), TEXT("Concord"), TEXT("Concord"), TEXT("Cassia Prime"), TEXT("Earth"), TEXT("Earth"),
		TEXT("Earth"), TEXT("Mars"), TEXT("Mars"), TEXT("Europa"), TEXT("Titan"), TEXT("Proxima"), TEXT("Sabel"), TEXT("Nemet")};
	const TCHAR* CallSigns[] = {
		TEXT("Rook"), TEXT("Vesper"), TEXT("Saint"), TEXT("Jinx"), TEXT("Halo"), TEXT("Moth"), TEXT("Tempest"), TEXT("Kestrel"),
		TEXT("Dagger"), TEXT("Lucky"), TEXT("Echo"), TEXT("Wick"), TEXT("Brick"), TEXT("Nova"), TEXT("Sparrow"), TEXT("Ghost"),
		TEXT("Ace"), TEXT("Rattle"), TEXT("Comet"), TEXT("Ember"), TEXT("Pike"), TEXT("Dusty"), TEXT("Viper"), TEXT("Boots"),
		TEXT("Fable"), TEXT("Anvil"), TEXT("Quill"), TEXT("Rogue"), TEXT("Stitch"), TEXT("Banshee"), TEXT("Flint"), TEXT("Juno")};

	struct FDept { const TCHAR* Name; int32 Count; int32 DeckLo; int32 DeckHi; int32 Kind; };   // 0 navy, 1 pilots, 2 marines
	const FDept Depts[] = {
		{TEXT("command staff"), 14, 2, 2, 0}, {TEXT("communications"), 10, 2, 2, 0}, {TEXT("sensors"), 12, 2, 3, 0},
		{TEXT("damage control"), 40, 2, 11, 0}, {TEXT("stewards and galley"), 28, 3, 3, 0}, {TEXT("flight deck"), 96, 4, 5, 0},
		{TEXT("Air Group pilots"), 60, 4, 4, 1}, {TEXT("medbay"), 18, 6, 6, 0}, {TEXT("weapons"), 76, 6, 7, 0},
		{TEXT("engineering"), 118, 8, 10, 0}, {TEXT("logistics"), 8, 12, 12, 0}, {TEXT("marines"), 80, 11, 11, 2}};

	FString RankFor(int32 Kind, FRandomStream& R)
	{
		const float X = R.FRand();
		if (Kind == 1) { return X < 0.4f ? TEXT("Ensign") : (X < 0.92f ? TEXT("Lieutenant") : TEXT("Lieutenant Commander")); }
		if (Kind == 2) { return X < 0.7f ? TEXT("Private") : (X < 0.95f ? TEXT("Sergeant") : TEXT("Captain")); }
		return X < 0.45f ? TEXT("Crewman") : X < 0.75f ? TEXT("Petty Officer") : X < 0.83f ? TEXT("Chief Petty Officer")
		     : X < 0.91f ? TEXT("Ensign") : X < 0.98f ? TEXT("Lieutenant") : TEXT("Lieutenant Commander");
	}

	// what a hit does to the people in the compartment (the doctors' words): the injury and how bad it usually is
	struct FRosterInjury { const TCHAR* Text; uint8 Severity; };
	const FRosterInjury InjBreach[] = {
		{TEXT("decompression injuries: a collapsed lung, on oxygen"), 2},
		{TEXT("barotrauma from the breach: burst eardrums and bruised lungs"), 1},
		{TEXT("struck by debris when the bulkhead failed: a broken leg"), 1},
		{TEXT("hypoxia from the decompression, now breathing on their own"), 0},
		{TEXT("a deep scalp wound and a concussion from the blast"), 1},
		{TEXT("frostbite on both hands from the exposed hull"), 0},
		{TEXT("thrown against a bulkhead: cracked ribs and internal bleeding"), 2},
		{TEXT("a crushed hand, caught in a closing pressure door"), 1}};
	const FRosterInjury InjFire[] = {
		{TEXT("second-degree burns on the arms and hands"), 1},
		{TEXT("smoke inhalation and burns to the face"), 1},
		{TEXT("burns across the back from a burning conduit"), 2},
		{TEXT("a burned hand and smoke in the lungs"), 0},
		{TEXT("third-degree burns on both legs"), 2},
		{TEXT("smoke inhalation, found unconscious at a hatch"), 1}};
	const FRosterInjury InjConduit[] = {
		{TEXT("an electrical burn from a shorted conduit"), 0},
		{TEXT("a heart arrhythmia after a power surge, on the monitor"), 1},
		{TEXT("coolant burns on the hands and forearms"), 0},
		{TEXT("a broken wrist, thrown by an arcing conduit"), 0}};
	const FRosterInjury InjEjection[] = {
		{TEXT("ejected under fire: a broken arm and cold exposure"), 1},
		{TEXT("ejected: two compressed vertebrae from the seat, and a concussion"), 1},
		{TEXT("ejected from a burning cockpit: burns on the neck and a dislocated shoulder"), 1},
		{TEXT("picked up after an hour adrift: hypothermia and a broken ankle"), 0},
		{TEXT("ejected at high speed: a fractured pelvis"), 2}};
	const FRosterInjury InjOther[] = {
		{TEXT("shrapnel wounds in the side"), 1},
		{TEXT("a broken arm and heavy bruising"), 0},
		{TEXT("a concussion and a cut above the eye"), 0}};

	template <int32 N>
	const FRosterInjury& RosterPickInjury(const FRosterInjury (&Table)[N], FRandomStream& R) { return Table[R.RandHelper(N)]; }

	uint8 RosterConditionFor(uint8 Severity, FRandomStream& R)
	{
		int32 C = Severity;
		const float X = R.FRand();
		C += X < 0.2f ? 1 : (X > 0.75f ? -1 : 0);
		return (uint8)FMath::Clamp(C, 0, 2);
	}
}

void FAstraCrewRoster::Generate(int32 Seed)
{
	People.Reset();
	Fallen.Reset();
	Hurt.Reset();
	++Rev;
	FRandomStream R(Seed);
	TSet<FString> Used;
	int32 Call = 0;
	for (const FDept& D : Depts)
	{
		for (int32 n = 0; n < D.Count; ++n)
		{
			FAstraCrewman P;
			int32 FirstIdx = 0;
			for (int32 Try = 0; Try < 20; ++Try)
			{
				FirstIdx = R.RandHelper(UE_ARRAY_COUNT(FirstNames));
				P.First = FirstNames[FirstIdx];
				P.Last = LastNames[R.RandHelper(UE_ARRAY_COUNT(LastNames))];
				if (!Used.Contains(P.First + P.Last))
				{
					break;
				}
			}
			// the first names alternate women's and men's (from "Min-jun", index 76, men's first)
			P.bFemale = (FirstIdx < 76) == (FirstIdx % 2 == 0);
			Used.Add(P.First + P.Last);
			P.Rank = RankFor(D.Kind, R);
			P.Dept = D.Name;
			P.Home = Homes[R.RandHelper(UE_ARRAY_COUNT(Homes))];
			P.Deck = R.RandRange(D.DeckLo, D.DeckHi);
			if (D.Kind == 1)
			{
				P.Last += FString::Printf(TEXT(" (call sign %s)"), CallSigns[Call++ % UE_ARRAY_COUNT(CallSigns)]);
			}
			People.Add(P);
		}
	}
}

int32 FAstraCrewRoster::FreeBed() const
{
	for (int32 B = 0; B < NumBeds; ++B)
	{
		if (InBed(B) < 0)
		{
			return B;
		}
	}
	return -1;
}

int32 FAstraCrewRoster::InBed(int32 Bed) const
{
	for (const int32 i : Hurt)
	{
		if (People[i].Status == 1 && People[i].Bed == Bed)
		{
			return i;
		}
	}
	return -1;
}

void FAstraCrewRoster::Admit(int32 Index, const FString& Injury, uint8 Condition)
{
	FAstraCrewman& P = People[Index];
	P.Status = 1;
	P.Injury = Injury;
	P.Condition = Condition;
	P.CareMinutes = 0.f;
	P.Bed = FreeBed();
	Hurt.AddUnique(Index);
	++Rev;
}

void FAstraCrewRoster::Leave(int32 Index)
{
	FAstraCrewman& P = People[Index];
	const int32 Freed = P.Bed;
	P.Bed = -1;
	Hurt.Remove(Index);
	if (Freed >= 0)   // the first one on a cot in the passage gets the bed
	{
		for (const int32 j : Hurt)
		{
			if (People[j].Status == 1 && People[j].Bed < 0)
			{
				People[j].Bed = Freed;
				break;
			}
		}
	}
	++Rev;
}

FString FAstraCrewRoster::Casualties(int32 Deck, int32 W, int32 K, FRandomStream& R, const FString& Cause, const TArray<int32>* Present)
{
	TArray<FString> Dead, Injured;
	auto Pick = [&](int32 Want, uint8 NewStatus, TArray<FString>& Out)
	{
		for (int32 n = 0; n < Want; ++n)
		{
			for (int32 Dist = -1; Dist < 12; ++Dist)   // who was there, then that deck, then the nearest ones
			{
				TArray<int32> Cand;
				if (Dist < 0)
				{
					for (const int32 i : Present ? *Present : TArray<int32>())
					{
						if (People.IsValidIndex(i) && People[i].Status == 0)
						{
							Cand.Add(i);
						}
					}
				}
				else for (int32 i = 0; i < People.Num(); ++i)
				{
					const FAstraCrewman& P = People[i];
					if (P.Status == 0 && P.Dept != TEXT("Air Group pilots") && FMath::Abs(P.Deck - Deck) == Dist)
					{
						Cand.Add(i);
					}
				}
				if (Cand.Num())
				{
					const int32 i = Cand[R.RandHelper(Cand.Num())];
					if (NewStatus == 2)
					{
						People[i].Status = 2;
						Fallen.Add(i);
						++Rev;
					}
					else
					{
						const FRosterInjury& J = Cause == TEXT("hull breach") ? RosterPickInjury(InjBreach, R) : Cause == TEXT("fire") ? RosterPickInjury(InjFire, R)
						                 : Cause == TEXT("conduit damage") ? RosterPickInjury(InjConduit, R) : RosterPickInjury(InjOther, R);
						Admit(i, J.Text, RosterConditionFor(J.Severity, R));
					}
					Out.Add(FString::Printf(TEXT("%s (%s, from %s)"), *People[i].Name(), *People[i].Dept, *People[i].Home));
					break;
				}
			}
		}
	};
	Pick(K, 2, Dead);
	Pick(W, 1, Injured);
	TArray<FString> Parts;
	if (Dead.Num())
	{
		Parts.Add(FString::Join(Dead, TEXT(" and ")) + TEXT(" killed"));
	}
	if (Injured.Num())
	{
		Parts.Add(FString::Join(Injured, TEXT(" and ")) + TEXT(" wounded, taken to the medbay"));
	}
	return FString::Join(Parts, TEXT("; "));
}

FString FAstraCrewRoster::AircrewLost(FRandomStream& R)
{
	TArray<int32> Cand;
	for (int32 i = 0; i < People.Num(); ++i)
	{
		if (People[i].Status == 0 && People[i].Dept == TEXT("Air Group pilots"))
		{
			Cand.Add(i);
		}
	}
	if (Cand.Num() == 0)
	{
		return FString();
	}
	const int32 i = Cand[R.RandHelper(Cand.Num())];
	const bool bKilled = R.FRand() < 0.55f;
	if (bKilled)
	{
		People[i].Status = 2;
		Fallen.Add(i);
		++Rev;
	}
	else
	{
		const FRosterInjury& J = RosterPickInjury(InjEjection, R);
		Admit(i, J.Text, RosterConditionFor(J.Severity, R));
	}
	return FString::Printf(TEXT("%s %s"), *People[i].Name(), bKilled ? TEXT("killed") : TEXT("ejected, recovered wounded by search and rescue"));
}

FString FAstraCrewRoster::LostWithShip(int32 K, FRandomStream& R)
{
	TArray<int32> Order;
	for (const int32 i : Hurt)
	{
		if (People[i].Status == 1 && People[i].Condition >= 2)
		{
			Order.Add(i);                                    // the critical: no time to move them
		}
	}
	TArray<int32> Eng, Rest;
	for (int32 i = 0; i < People.Num(); ++i)
	{
		const FAstraCrewman& P = People[i];
		if (P.Status == 0 && P.Dept != TEXT("Air Group pilots"))
		{
			(P.Deck == 7 ? Eng : Rest).Add(i);
		}
	}
	for (int32 n = Eng.Num() - 1; n > 0; --n) { Eng.Swap(n, R.RandHelper(n + 1)); }
	for (int32 n = Rest.Num() - 1; n > 0; --n) { Rest.Swap(n, R.RandHelper(n + 1)); }
	Order.Append(Eng.GetData(), FMath::Min(Eng.Num(), FMath::Max(0, K / 3)));   // a third of them in Main Engineering
	Order.Append(Rest);
	TArray<FString> Names;
	int32 Lost = 0;
	for (const int32 i : Order)
	{
		if (Lost >= K)
		{
			break;
		}
		if (People[i].Status == 2)
		{
			continue;
		}
		if (People[i].Status == 1)
		{
			Leave(i);
		}
		People[i].Status = 2;
		Fallen.AddUnique(i);
		if (Names.Num() < 3)
		{
			Names.Add(FString::Printf(TEXT("%s (%s)"), *People[i].Name(), *People[i].Dept));
		}
		++Lost;
	}
	++Rev;
	if (Lost == 0)
	{
		return FString();
	}
	return Lost > Names.Num() ? FString::Printf(TEXT("%s and %d others"), *FString::Join(Names, TEXT(", ")), Lost - Names.Num())
	                          : FString::Join(Names, TEXT(", "));
}

void FAstraCrewRoster::Care(float Minutes, FRandomStream& R, TArray<FNews>& OutNews)
{
	const TArray<int32> Ward = Hurt;
	for (const int32 i : Ward)
	{
		FAstraCrewman& P = People[i];
		if (P.Status != 1)
		{
			continue;
		}
		P.CareMinutes += Minutes;
		const float X = R.FRand();
		const FString Who = FString::Printf(TEXT("%s (%s, from %s)"), *P.Name(), *P.Dept, *P.Home);
		if (P.Condition >= 2 && P.CareMinutes >= 3.f)
		{
			if (X < 0.05f * Minutes)
			{
				P.Status = 2;
				Fallen.Add(i);
				Leave(i);
				OutNews.Add({FString::Printf(TEXT("medbay: %s has died of wounds (%s), despite everything the medical team did"), *Who, *P.Injury), true});
			}
			else if (X < 0.27f * Minutes)
			{
				P.Condition = 1;
				P.CareMinutes = 0.f;
				++Rev;
				OutNews.Add({FString::Printf(TEXT("medbay: %s is out of danger, now serious but stable"), *Who), false});
			}
		}
		else if (P.Condition == 1 && P.CareMinutes >= 4.f && X < 0.25f * Minutes)
		{
			P.Condition = 0;
			P.CareMinutes = 0.f;
			++Rev;
			OutNews.Add({FString::Printf(TEXT("medbay: %s is stable and recovering"), *Who), false});
		}
		else if (P.Condition == 0 && P.CareMinutes >= 5.f && X < 0.2f * Minutes)
		{
			P.Status = 0;
			P.Injury.Empty();
			Leave(i);
			OutNews.Add({FString::Printf(TEXT("medbay: %s discharged, back to duty"), *Who), false});
		}
	}
}

void FAstraCrewRoster::Restore(const TArray<int32>& InFallen, const TArray<int32>& InHurt)
{
	for (FAstraCrewman& P : People)
	{
		P.Status = 0;
		P.Bed = -1;
		P.Injury.Empty();
		P.Condition = 0;
		P.CareMinutes = 0.f;
	}
	Fallen.Reset();
	Hurt.Reset();
	for (const int32 i : InFallen)
	{
		if (People.IsValidIndex(i))
		{
			People[i].Status = 2;
			Fallen.Add(i);
		}
	}
	for (const int32 i : InHurt)
	{
		if (People.IsValidIndex(i) && People[i].Status == 0)
		{
			Admit(i, TEXT("wounds from the last battle"), 1);
		}
	}
	++Rev;
}

void FAstraCrewRoster::RestoreCare(int32 Index, const FString& Injury, uint8 Condition, int32 Bed)
{
	if (!People.IsValidIndex(Index) || People[Index].Status != 1)
	{
		return;
	}
	FAstraCrewman& P = People[Index];
	if (!Injury.IsEmpty())
	{
		P.Injury = Injury;
	}
	P.Condition = (uint8)FMath::Clamp((int32)Condition, 0, 2);
	if (Bed >= 0 && Bed < NumBeds && Bed != P.Bed)
	{
		const int32 Other = InBed(Bed);   // swap with whoever the order of admission put there
		if (Other >= 0)
		{
			People[Other].Bed = P.Bed;
		}
		P.Bed = Bed;
	}
	++Rev;
}

int32 FAstraCrewRoster::NumWounded() const
{
	return Hurt.FilterByPredicate([this](int32 i) { return People[i].Status == 1; }).Num();
}

int32 FAstraCrewRoster::NumKilled() const
{
	return Fallen.Num();
}

FString FAstraCrewRoster::Summary() const
{
	if (Fallen.Num() == 0 && Hurt.Num() == 0)
	{
		return TEXT("none");
	}
	int32 ByCond[3] = {0, 0, 0};
	for (const int32 i : Hurt)
	{
		++ByCond[FMath::Min<int32>(People[i].Condition, 2)];
	}
	FString Out = FString::Printf(TEXT("%d wounded in the medbay (%d critical, %d serious, %d stable), %d killed"),
	                              NumWounded(), ByCond[2], ByCond[1], ByCond[0], NumKilled());
	if (Fallen.Num())
	{
		TArray<FString> Names;
		for (int32 k = Fallen.Num() - 1; k >= 0 && Names.Num() < 8; --k)
		{
			const FAstraCrewman& P = People[Fallen[k]];
			Names.Add(FString::Printf(TEXT("%s (%s)"), *P.Name(), *P.Dept));
		}
		Out += TEXT(" — the fallen: ") + FString::Join(Names, TEXT(", "));
	}
	return Out;
}
