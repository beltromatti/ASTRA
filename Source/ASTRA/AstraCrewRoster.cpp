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
}

void FAstraCrewRoster::Generate(int32 Seed)
{
	People.Reset();
	Fallen.Reset();
	Hurt.Reset();
	FRandomStream R(Seed);
	TSet<FString> Used;
	int32 Call = 0;
	for (const FDept& D : Depts)
	{
		for (int32 n = 0; n < D.Count; ++n)
		{
			FAstraCrewman P;
			for (int32 Try = 0; Try < 20; ++Try)
			{
				P.First = FirstNames[R.RandHelper(UE_ARRAY_COUNT(FirstNames))];
				P.Last = LastNames[R.RandHelper(UE_ARRAY_COUNT(LastNames))];
				if (!Used.Contains(P.First + P.Last))
				{
					break;
				}
			}
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

FString FAstraCrewRoster::Casualties(int32 Deck, int32 W, int32 K, FRandomStream& R)
{
	TArray<FString> Dead, Injured;
	auto Pick = [&](int32 Want, uint8 NewStatus, TArray<FString>& Out, TArray<int32>& List)
	{
		for (int32 n = 0; n < Want; ++n)
		{
			for (int32 Dist = 0; Dist < 12; ++Dist)   // that deck first, then the nearest ones
			{
				TArray<int32> Cand;
				for (int32 i = 0; i < People.Num(); ++i)
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
					People[i].Status = NewStatus;
					List.Add(i);
					Out.Add(FString::Printf(TEXT("%s (%s, from %s)"), *People[i].Name(), *People[i].Dept, *People[i].Home));
					break;
				}
			}
		}
	};
	Pick(K, 2, Dead, Fallen);
	Pick(W, 1, Injured, Hurt);
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
	People[i].Status = bKilled ? 2 : 1;
	(bKilled ? Fallen : Hurt).Add(i);
	return FString::Printf(TEXT("%s %s"), *People[i].Name(), bKilled ? TEXT("killed") : TEXT("ejected, recovered wounded by search and rescue"));
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
	FString Out = FString::Printf(TEXT("%d wounded in the medbay, %d killed"), NumWounded(), NumKilled());
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
