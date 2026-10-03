// ASTRA — FLOTTA-VIVA: the inside of a ship that is not the Aquila (see AstraFleetInterior.h and docs/FLOTTA-VIVA.md).

#include "AstraFleetInterior.h"

#include "ASTRA.h"
#include "AstraWarTypes.h"

namespace
{
	EFleetRole FleetRoleOf(const FName& N)
	{
		static const TMap<FName, EFleetRole> T = {
			{FName(TEXT("bridge")), EFleetRole::Bridge}, {FName(TEXT("control")), EFleetRole::Control}, {FName(TEXT("gunnery")), EFleetRole::Gunnery},
			{FName(TEXT("magazine")), EFleetRole::Magazine}, {FName(TEXT("engineering")), EFleetRole::Engineering}, {FName(TEXT("damage_control")), EFleetRole::DamageControl},
			{FName(TEXT("medical")), EFleetRole::Medical}, {FName(TEXT("flight")), EFleetRole::Flight}, {FName(TEXT("sensors")), EFleetRole::Sensors},
			{FName(TEXT("marines")), EFleetRole::Marine}, {FName(TEXT("marines_dock")), EFleetRole::MarineDock}, {FName(TEXT("reserve")), EFleetRole::Reserve}};
		const EFleetRole* R = T.Find(N);
		return R ? *R : EFleetRole::Reserve;
	}

	// The names of the people of the chain of command. The surnames of the Aquila's main cast and of the war's named commanders are not here.
	const TCHAR* const GAstraFirst[] = {TEXT("Alma"), TEXT("Idris"), TEXT("Noor"), TEXT("Tomasz"), TEXT("Liv"), TEXT("Marcus"), TEXT("Yara"), TEXT("Dmitri"), TEXT("Chen"), TEXT("Imani"),
	                                    TEXT("Rafael"), TEXT("Sunniva"), TEXT("Kenji"), TEXT("Ayesha"), TEXT("Luca"), TEXT("Mirela"), TEXT("Hassan"), TEXT("Greta"), TEXT("Joao"), TEXT("Anika"),
	                                    TEXT("Bram"), TEXT("Selma"), TEXT("Omar"), TEXT("Ingrid"), TEXT("Teodor"), TEXT("Leila"), TEXT("Piotr"), TEXT("Maren"), TEXT("Dario"), TEXT("Nadia")};
	const TCHAR* const GAstraLast[] = {TEXT("Abara"), TEXT("Brandt"), TEXT("Calloway"), TEXT("Dufresne"), TEXT("Eriksen"), TEXT("Falk"), TEXT("Gallo"), TEXT("Haldane"), TEXT("Ibarra"),
	                                   TEXT("Jansen"), TEXT("Kessler"), TEXT("Lindahl"), TEXT("Moreau"), TEXT("Navarro"), TEXT("Okafor"), TEXT("Petrov"), TEXT("Quist"), TEXT("Rinaldi"),
	                                   TEXT("Sorensen"), TEXT("Tavares"), TEXT("Ulloa"), TEXT("Vasquez"), TEXT("Weiss"), TEXT("Xiong"), TEXT("Yilmaz"), TEXT("Zielinski"), TEXT("Archer"),
	                                   TEXT("Bellamy"), TEXT("Crane"), TEXT("Dalton"), TEXT("Ellery"), TEXT("Fenwick"), TEXT("Garrity"), TEXT("Holloway"), TEXT("Ives"), TEXT("Jessup"),
	                                   TEXT("Keane"), TEXT("Lowry"), TEXT("Mercer"), TEXT("Nolan"), TEXT("Orlov"), TEXT("Pruitt"), TEXT("Quayle"), TEXT("Rowe"), TEXT("Sinclair"),
	                                   TEXT("Thorne"), TEXT("Underhill"), TEXT("Vance"), TEXT("Whitlock"), TEXT("Yates")};
	const TCHAR* const GMandateFirst[] = {TEXT("Cael"), TEXT("Ilse"), TEXT("Ansel"), TEXT("Maren"), TEXT("Corvin"), TEXT("Thessaly"), TEXT("Dorian"), TEXT("Ysolde"), TEXT("Garrick"),
	                                      TEXT("Neve"), TEXT("Orsin"), TEXT("Liora"), TEXT("Bastian"), TEXT("Tamsin"), TEXT("Evander"), TEXT("Sorrel"), TEXT("Casimir"), TEXT("Linnea"),
	                                      TEXT("Roark"), TEXT("Vesna"), TEXT("Halden"), TEXT("Isaura"), TEXT("Tobias"), TEXT("Merrin"), TEXT("Dagny"), TEXT("Joss"), TEXT("Kestrel"),
	                                      TEXT("Perrin"), TEXT("Wynn"), TEXT("Alder")};
	const TCHAR* const GMandateLast[] = {TEXT("Vane"), TEXT("Harrow"), TEXT("Ashby"), TEXT("Corbin"), TEXT("Dray"), TEXT("Ember"), TEXT("Fenn"), TEXT("Grieve"), TEXT("Kettering"),
	                                     TEXT("Larch"), TEXT("Marsh"), TEXT("Norwood"), TEXT("Orrin"), TEXT("Pike"), TEXT("Quill"), TEXT("Rook"), TEXT("Sable"), TEXT("Tarn"),
	                                     TEXT("Umber"), TEXT("Vesper"), TEXT("Wick"), TEXT("Yarrow"), TEXT("Blackwood"), TEXT("Crowe"), TEXT("Drummond"), TEXT("Eddowes"),
	                                     TEXT("Fallow"), TEXT("Gaunt"), TEXT("Hollis"), TEXT("Ironside"), TEXT("Jarrow"), TEXT("Kell"), TEXT("Lorne"), TEXT("Mourne"),
	                                     TEXT("Nettle"), TEXT("Oakes"), TEXT("Penhale"), TEXT("Ravel"), TEXT("Stroud")};

	constexpr float MedevacDelayS = 25.f;
}

const TCHAR* AstraFleetBilletWord(FName Role)
{
	static const TMap<FName, const TCHAR*> T = {
		{FName(TEXT("captain")), TEXT("captain")}, {FName(TEXT("executive_officer")), TEXT("executive officer")}, {FName(TEXT("tactical_officer")), TEXT("tactical officer")},
		{FName(TEXT("chief_engineer")), TEXT("chief engineer")}, {FName(TEXT("medical_officer")), TEXT("medical officer")}, {FName(TEXT("security_chief")), TEXT("security chief")},
		{FName(TEXT("flight_officer")), TEXT("flight officer")}};
	const TCHAR* const* W = T.Find(Role);
	return W ? *W : TEXT("officer");
}

// ====================================================================================================================== set up
FAstraShipInterior::FAstraShipInterior(TSharedRef<const FFleetClassPlan> InPlan, int32 InShipId, const FString& InShipName, int32 Seed)
	: Plan(InPlan), ShipId(InShipId), ShipName(InShipName), Rng(Seed)
{
	FAstraDmgHooks H;
	H.Event = [this](const FString& Text, bool bReport) { Note(Text, bReport); };
	H.PeopleIn = [this](const FAstraDmgComp& C, TArray<FAstraDmgPerson>& Out) { PeopleIn(C, Out); };
	H.Harm = [this](int32 Who, bool bKill, EAstraDmgHarm Cause) { return HarmPerson(Who, bKill, Cause); };
	H.SealDoor = [](FName, bool) {};                     // (no door of a ship that is not the Aquila is drawn: the model keeps which bulkheads are shut)
	H.PlanChanged = []() {};
	H.AddHeat = [](float) {};
	H.StructureBurn = [this](float Points) { BurnPending += Points; };
	H.Alert = []() { return 2; };                        // a ship that is being shot at is at action stations: the doors are shut
	Model.Init(Plan->Map.ToSharedRef(), H, Seed);
	Model.MaxIncidents = 10;
	Model.SetStep(0.5f);                                  // a coarser physics than the Aquila's 0.2 s: a lower resolution at a fraction of the cost
	BuildCrew();
}

int32 FAstraShipInterior::AddPerson(int32 Comp, EFleetRole Role)
{
	const FAstraDmgComp& C = Plan->Map->Comps[Comp];
	FFleetPerson P;
	P.Comp = Comp;
	P.Role = Role;
	const FVector Size = C.Box.GetSize();
	P.PosCm = FVector3f((float)(C.Box.Min.X + Rng.FRand() * Size.X), (float)(C.Box.Min.Y + Rng.FRand() * Size.Y), (float)C.Box.Min.Z);
	const int32 I = People.Add(P);
	ByComp.FindOrAdd(Comp).Add(I);
	return I;
}

void FAstraShipInterior::MovePerson(int32 Who, int32 ToComp)
{
	FFleetPerson& P = People[Who];
	if (P.Comp == ToComp || ToComp == INDEX_NONE)
	{
		return;
	}
	if (TArray<int32>* L = ByComp.Find(P.Comp))
	{
		L->RemoveSingleSwap(Who);
	}
	const FAstraDmgComp& C = Plan->Map->Comps[ToComp];
	const FVector Size = C.Box.GetSize();
	P.Comp = ToComp;
	P.PosCm = FVector3f((float)(C.Box.Min.X + Rng.FRand() * Size.X), (float)(C.Box.Min.Y + Rng.FRand() * Size.Y), (float)C.Box.Min.Z);
	ByComp.FindOrAdd(ToComp).Add(Who);
}

FString FAstraShipInterior::MakeName(bool bMandate)
{
	if (bMandate)
	{
		return FString::Printf(TEXT("%s %s"), GMandateFirst[Rng.RandHelper(UE_ARRAY_COUNT(GMandateFirst))], GMandateLast[Rng.RandHelper(UE_ARRAY_COUNT(GMandateLast))]);
	}
	return FString::Printf(TEXT("%s %s"), GAstraFirst[Rng.RandHelper(UE_ARRAY_COUNT(GAstraFirst))], GAstraLast[Rng.RandHelper(UE_ARRAY_COUNT(GAstraLast))]);
}

void FAstraShipInterior::BuildCrew()
{
	People.Reset();
	ByComp.Reset();
	People.Reserve(Plan->Complement + 8);
	for (const FFleetGarrison& G : Plan->Garrison)
	{
		const EFleetRole R = FleetRoleOf(G.Role);
		for (int32 k = 0; k < G.N; ++k)
		{
			AddPerson(G.Comp, R);
		}
	}
	// the damage parties: their members are damage-control hands, brought to the party's muster room
	Parties.Reset();
	for (const FFleetParty& FP : Plan->Parties)
	{
		FFleetPartyState S;
		S.Home = FP.Home;
		S.Comp = FP.Home;
		S.Size0 = FP.Size;
		const int32 PartyIdx = Parties.Num();
		TArray<int32> Hands;
		for (int32 i = 0; i < People.Num(); ++i)
		{
			if (People[i].Role == EFleetRole::DamageControl && People[i].Party < 0)
			{
				Hands.Add(i);
			}
		}
		const FVector Home = Plan->Map->Comps[FP.Home].Box.GetCenter();
		Hands.Sort([this, &Home](int32 A, int32 B) { return FVector::DistSquared(Plan->Map->Comps[People[A].Comp].Box.GetCenter(), Home) < FVector::DistSquared(Plan->Map->Comps[People[B].Comp].Box.GetCenter(), Home); });
		for (int32 k = 0; k < FMath::Min(FP.Size, Hands.Num()); ++k)
		{
			People[Hands[k]].Party = (int8)PartyIdx;
			MovePerson(Hands[k], FP.Home);
			S.Members.Add(Hands[k]);
		}
		Parties.Add(S);
	}
	// the officers who matter: each at the post the plan gives (a hand from the reserve is brought there if no one stands in it)
	for (const FFleetBillet& B : Plan->Billets)
	{
		int32 Who = INDEX_NONE;
		if (const TArray<int32>* L = ByComp.Find(B.Comp))
		{
			for (const int32 I : *L)
			{
				if (People[I].Named < 0 && People[I].Party < 0)
				{
					Who = I;
					break;
				}
			}
		}
		if (Who == INDEX_NONE)
		{
			for (int32 i = 0; i < People.Num(); ++i)
			{
				if (People[i].Role == EFleetRole::Reserve && People[i].Named < 0 && People[i].Party < 0)
				{
					Who = i;
					break;
				}
			}
			if (Who == INDEX_NONE)
			{
				Who = AddPerson(B.Comp, EFleetRole::Control);
			}
			MovePerson(Who, B.Comp);
		}
		FFleetNamed N;
		N.Role = B.Role;
		const FString* Rank = Plan->Ranks.Find(B.Role);
		N.Rank = Rank ? *Rank : B.Rank;
		N.Name = MakeName(Plan->bMandate);
		N.Line = B.Line;
		N.Person = Who;
		People[Who].Named = (int16)Named.Add(N);
		People[Who].PosCm = FVector3f(B.PostCm);
		if (B.Role == FName(TEXT("captain")))
		{
			People[Who].Role = EFleetRole::Bridge;
		}
	}
	Fit = People.Num();
	Wounded = Dead = 0;
	for (const FFleetPerson& P : People)
	{
		++RoleTotal[(int32)P.Role];
		++RoleFit[(int32)P.Role];
	}
}

// ====================================================================================================================== the model's world
void FAstraShipInterior::Note(const FString& Text, bool bGrave)
{
	FFleetEvent E;
	E.T = Clock;
	E.Text = Text;
	E.bGrave = bGrave;
	Log.Add(E);
	if (Log.Num() > 24)
	{
		Log.RemoveAt(0);
	}
	if (bGrave)
	{
		Outbox.Add(E);
		if (Outbox.Num() > 12)
		{
			Outbox.RemoveAt(0);
		}
	}
}

void FAstraShipInterior::PeopleIn(const FAstraDmgComp& C, TArray<FAstraDmgPerson>& Out) const
{
	const int32* Ci = Plan->Map->CompByName.Find(C.Id);
	const TArray<int32>* L = Ci ? ByComp.Find(*Ci) : nullptr;
	if (!L)
	{
		return;
	}
	for (const int32 I : *L)
	{
		const FFleetPerson& P = People[I];
		if (P.State != 0)
		{
			continue;
		}
		FAstraDmgPerson X;
		X.Roster = I;
		X.PosCm = FVector(P.PosCm);
		X.bSuited = P.Party >= 0 && Parties.IsValidIndex(P.Party) && Parties[P.Party].bOnScene;     // a damage party at work wears suits
		X.bAtPost = P.Role != EFleetRole::Reserve && !X.bSuited;
		Out.Add(X);
	}
}

FString FAstraShipInterior::HarmPerson(int32 Who, bool bKill, EAstraDmgHarm Cause)
{
	if (!People.IsValidIndex(Who) || People[Who].State != 0)
	{
		return FString();                                // hurt or fallen already: nobody else is taken in their place
	}
	FFleetPerson& P = People[Who];
	P.State = bKill ? 2 : 1;
	P.Cause = (uint8)Cause;
	P.HarmAt = Clock;
	--RoleFit[(int32)P.Role];
	if (!bKill)
	{
		++RoleHurt[(int32)P.Role];
	}
	--Fit;
	if (bKill)
	{
		++Dead;
	}
	else
	{
		++Wounded;
		WoundedWaiting.Add(Who);
	}
	if (P.Named >= 0)
	{
		const FFleetNamed& N = Named[P.Named];
		return FString::Printf(TEXT("%s %s (%s)"), *N.Rank, *N.Name, AstraFleetBilletWord(N.Role));
	}
	return TEXT("crew");
}

int32 FAstraShipInterior::LoseWithShip()
{
	if (Lost > 0)
	{
		return 0;
	}
	Lost = Fit + Wounded;
	for (FFleetPerson& P : People)
	{
		P.State = 2;
	}
	Fit = Wounded = 0;
	WoundedWaiting.Reset();
	for (int32 r = 0; r < (int32)EFleetRole::Num; ++r)
	{
		RoleFit[r] = RoleHurt[r] = 0;
	}
	Note(FString::Printf(TEXT("%s: lost with all hands (%d aboard)"), *ShipName, Lost), true);
	return Lost;
}

int32 FAstraShipInterior::WarSectionOf(int32 Comp) const
{
	const float X = (float)Plan->Map->Comps[Comp].Box.GetCenter().X;
	if (Plan->CutBowCm == 0.f && Plan->CutSternCm == 0.f)
	{
		const FBox& B = Plan->Map->Hull;
		const float T = (X - (float)B.Min.X) / FMath::Max(1.f, (float)(B.Max.X - B.Min.X));
		return T > 0.66f ? 0 : (T < 0.33f ? 2 : 1);
	}
	return X > Plan->CutBowCm ? 0 : (X < Plan->CutSternCm ? 2 : 1);
}

FString FAstraShipInterior::RoomWord(int32 Comp) const
{
	return Plan->Map->Describe(Comp);
}

// ====================================================================================================================== what the war does to it
void FAstraShipInterior::Impact(const FAstraHullHit& Hit)
{
	FAstraImpactResult R;
	Model.Impact(Hit, R);
	++Hits;
	bCalm = false;
	if (R.Comps.Num() == 0)
	{
		return;
	}
	++HitsInside;
	LastEntryCm = R.EntryCm;
	if (bTrace)
	{
		FString Path;
		for (const int32 Ci : R.Comps)
		{
			Path += (Path.IsEmpty() ? TEXT("") : TEXT(" -> ")) + RoomWord(Ci);
		}
		LastTrace = FString::Printf(TEXT("%s: a blow of %.0f at the hull (%s face, %s, %.0f m from the plan's origin) entered at %s and spent itself in %d rooms: %s | %d killed, %d wounded%s%s%s%s | %s"),
		                            *ShipName, Hit.Damage, Hit.Facing == 0 ? TEXT("bow") : (Hit.Facing == 1 ? TEXT("stern") : (Hit.Facing == 2 ? TEXT("port") : (Hit.Facing == 3 ? TEXT("starboard") : (Hit.Facing == 4 ? TEXT("dorsal") : TEXT("ventral"))))),
		                            Hit.Section == 0 ? TEXT("bow section") : (Hit.Section == 1 ? TEXT("mid section") : TEXT("stern section")), FVector(R.EntryCm).Size() / 100.0, *RoomWord(R.Comps[0]), R.Comps.Num(), *Path,
		                            R.Killed, R.Wounded, R.bBreach ? TEXT(", a breach") : TEXT(""), R.bFire ? TEXT(", a fire") : TEXT(""), R.bPower ? TEXT(", a conduit cut") : TEXT(""), R.bWreck ? TEXT(", a room wrecked") : TEXT(""),
		                            *FString::Join(R.Lines, TEXT("; ")));
	}
	// what it did, in the ship's own words: told when it hurts (people, a breach, a fire, a room lost)
	if (R.Killed || R.Wounded || R.bBreach || R.bFire || R.bWreck || R.bPower)
	{
		FString Text = FString::Printf(TEXT("%s: hit"), *ShipName);
		FString What;
		for (const FString& L : R.Lines)
		{
			What += (What.IsEmpty() ? TEXT("") : TEXT("; ")) + L;
		}
		if (!What.IsEmpty())
		{
			Text += TEXT(" — ") + What;
		}
		if (R.Killed || R.Wounded)
		{
			Text += FString::Printf(TEXT("; %d killed, %d wounded"), R.Killed, R.Wounded);
		}
		Note(Text, R.Killed >= 2 || R.bBreach || R.bFire || R.bWreck);
	}
}

void FAstraShipInterior::GutSection(int32 WarSection)
{
	static const TCHAR* const Names[3] = {TEXT("bow"), TEXT("mid"), TEXT("stern")};
	const float Bow = Plan->CutBowCm, Stern = Plan->CutSternCm;
	float X0 = -1.0e7f, X1 = 1.0e7f;
	if (Bow != 0.f || Stern != 0.f)
	{
		X0 = WarSection == 0 ? Bow : (WarSection == 1 ? Stern : -1.0e7f);
		X1 = WarSection == 0 ? 1.0e7f : (WarSection == 1 ? Bow : Stern);
	}
	else
	{
		const FBox& B = Plan->Map->Hull;
		const float L = (float)(B.Max.X - B.Min.X);
		X0 = (float)B.Min.X + L * (WarSection == 2 ? -1.f : (WarSection == 1 ? 0.33f : 0.66f));
		X1 = WarSection == 0 ? 1.0e7f : (float)B.Min.X + L * (WarSection == 2 ? 0.33f : 0.66f);
	}
	FAstraImpactResult R;
	Model.GutSection(X0, X1, Names[FMath::Clamp(WarSection, 0, 2)], R);
	bCalm = false;
}

void FAstraShipInterior::Strike(int32 Comp, float Energy, uint8 Type, bool bHole)
{
	FAstraImpactResult R;
	Model.Strike(Comp, Energy, Type, Plan->Map->Comps[Comp].Box.GetCenter(), bHole, R);
	bCalm = false;
}

void FAstraShipInterior::Tick(float Dt)
{
	Clock += Dt;
	bool bBusy = Model.States().Num() > 0 || Incidents.Num() > 0 || WoundedWaiting.Num() > 0;
	for (const FFleetPartyState& P : Parties)
	{
		bBusy |= P.Incident != 0;
	}
	if (!bBusy)
	{
		if (bFlush)
		{
			Model.Tick(0.6f, Incidents);                   // (the distribution's last accounts: the allocations come back to what they were)
			RefreshFit();
			bFlush = false;
		}
		bCalm = true;
		return;
	}
	bCalm = false;
	bFlush = true;
	Model.Tick(Dt, Incidents);
	TickParties(Dt);
	SlowT += Dt;
	if (SlowT >= 1.f)
	{
		TickMedevac(SlowT);
		RefreshFit();
		SlowT = 0.f;
	}
}

float FAstraShipInterior::RoomFit(int32 Comp) const
{
	const FAstraDmgState* S = Comp != INDEX_NONE ? Model.Find(Comp) : nullptr;
	if (!S)
	{
		return 1.f;
	}
	if (S->bGutted || S->Wreck >= 1.f)
	{
		return 0.f;
	}
	return (1.f - S->Wreck) * FMath::SmoothStep(0.10f, 0.55f, S->Power);
}

float FAstraShipInterior::MountFit(int32 MountIndex) const
{
	return Plan->MountComp.IsValidIndex(MountIndex) && Plan->MountComp[MountIndex] != INDEX_NONE ? RoomFit(Plan->MountComp[MountIndex]) : 1.f;
}

void FAstraShipInterior::RefreshFit()
{
	using namespace AstraWar;
	const FAstraDamageMap& M = *Plan->Map;
	auto RoomOrOne = [this](const TCHAR* Role, bool bFabricOnly) -> float
	{
		const int32 C = Plan->Role(Role);
		if (C == INDEX_NONE)
		{
			return 1.f;
		}
		const FAstraDmgState* S = Model.Find(C);
		if (!S)
		{
			return 1.f;
		}
		return bFabricOnly ? ((S->bGutted || S->Wreck >= 1.f) ? 0.f : 1.f - S->Wreck) : RoomFit(C);
	};
	// the drives and their plant, the sensors' room, the hangar: fabric and power; the reactor and the bridge: the fabric alone (a conduit cut leaves them running on their own supply)
	const float Eng = RoleStrength(EFleetRole::Engineering), Brg = RoleStrength(EFleetRole::Bridge), Fly = RoleStrength(EFleetRole::Flight), Sns = RoleStrength(EFleetRole::Sensors);
	SysFitV[SysEngines] = RoomOrOne(TEXT("drives"), false) * (0.7f + 0.3f * Eng);
	SysFitV[SysSensors] = RoomOrOne(TEXT("sensors"), false) * (0.5f + 0.5f * Sns);
	SysFitV[SysHangar] = RoomOrOne(TEXT("hangar"), false) * (0.5f + 0.5f * Fly);
	SysFitV[SysBridge] = RoomOrOne(TEXT("bridge"), true) * (0.35f + 0.65f * Brg);
	SysFitV[SysReactor] = RoomOrOne(TEXT("engineering"), true) * (0.6f + 0.4f * Eng);
	SysFitV[SysPointDefence] = 1.f;
	WeaponCrewV = 0.4f + 0.6f * FMath::Sqrt(0.5f * (RoleStrength(EFleetRole::Gunnery) + RoleStrength(EFleetRole::Magazine)));
	(void)M;
}

void FAstraShipInterior::TickMedevac(float)
{
	// the hurt are carried to the medbay (the Aquila's are, by VITA): a while after the blow, when the ship has one and it still stands
	const int32 Bay = Plan->Objective(TEXT("medbay"));
	for (int32 i = WoundedWaiting.Num() - 1; i >= 0; --i)
	{
		const FFleetPerson& P = People[WoundedWaiting[i]];
		if (Clock - P.HarmAt < MedevacDelayS)
		{
			continue;
		}
		const FAstraDmgState* S = Bay != INDEX_NONE ? Model.Find(Bay) : nullptr;
		if (Bay != INDEX_NONE && !(S && (S->Wreck >= 1.f || S->bGutted)))
		{
			MovePerson(WoundedWaiting[i], Bay);
		}
		WoundedWaiting.RemoveAtSwap(i);
	}
}

void FAstraShipInterior::TickParties(float Dt)
{
	// the fallen leave their parties; a party whose incident is over (out, sealed, mended) is free again and goes home
	for (FFleetPartyState& P : Parties)
	{
		P.Members.RemoveAll([this](int32 I) { return People[I].State != 0; });
		if (P.Incident != 0 && !Incidents.ContainsByPredicate([&P](const FAstraDamage& D) { return D.Id == P.Incident; }))
		{
			for (const int32 I : P.Members)
			{
				MovePerson(I, P.Home);
			}
			P.Incident = 0;
			P.bOnScene = false;
			P.Comp = P.Home;
		}
	}
	// the unattended incidents, the worst first, each to the party that is nearest and free
	TArray<int32, TInlineAllocator<12>> Order;
	for (int32 i = 0; i < Incidents.Num(); ++i)
	{
		if (Incidents[i].Team < 0 && Incidents[i].Comp != INDEX_NONE)
		{
			Order.Add(i);
		}
	}
	Order.Sort([this](int32 A, int32 B) { return Incidents[A].Severity > Incidents[B].Severity; });
	for (const int32 Ix : Order)
	{
		FAstraDamage& D = Incidents[Ix];
		int32 Best = INDEX_NONE;
		float BestT = 1.0e8f;
		for (int32 p = 0; p < Parties.Num(); ++p)
		{
			const FFleetPartyState& P = Parties[p];
			if (P.Incident != 0 || P.Members.Num() == 0)
			{
				continue;
			}
			const TArray<float>& Tr = Plan->Parties[p].TravelS;
			const float T = Tr.IsValidIndex(D.Comp) ? Tr[D.Comp] : 1.0e8f;
			if (T < BestT)
			{
				BestT = T;
				Best = p;
			}
		}
		if (Best == INDEX_NONE || BestT >= 1.0e3f)
		{
			continue;
		}
		FFleetPartyState& P = Parties[Best];
		D.Team = Best;
		D.Travel = D.Travel0 = BestT;
		D.Work = Model.WorkSeconds(D) * FMath::Clamp((float)P.Size0 / (float)P.Members.Num(), 1.f, 3.f);   // a party that has lost people takes longer
		P.Incident = D.Id;
		P.bOnScene = false;
	}
	// the work: they run (the plan's own doors and stairs), then work the hazard down through the model
	for (int32 i = Incidents.Num() - 1; i >= 0; --i)
	{
		if (i >= Incidents.Num() || Incidents[i].Team < 0 || !Parties.IsValidIndex(Incidents[i].Team))
		{
			continue;
		}
		FAstraDamage& D = Incidents[i];
		FFleetPartyState& P = Parties[D.Team];
		if (D.Travel > 0.f)
		{
			D.Travel -= Dt;
			if (D.Travel <= 0.f)
			{
				P.bOnScene = true;
				P.Comp = D.Comp;
				for (const int32 I : P.Members)
				{
					MovePerson(I, D.Comp);
				}
			}
			continue;
		}
		const int32 PartyIdx = D.Team;
		if (Model.Work(D, Dt, Incidents))
		{
			FFleetPartyState& Q = Parties[PartyIdx];      // (the incident is gone from the list: the party is free and goes home)
			for (const int32 I : Q.Members)
			{
				MovePerson(I, Q.Home);
			}
			Q.Incident = 0;
			Q.bOnScene = false;
			Q.Comp = Q.Home;
		}
	}
}

// ====================================================================================================================== what comes out
int32 FAstraShipInterior::Fires() const
{
	int32 N = 0;
	for (const auto& KV : Model.States())
	{
		N += KV.Value.Fire >= 0.10f ? 1 : 0;
	}
	return N;
}

int32 FAstraShipInterior::Breaches() const
{
	int32 N = 0;
	for (const auto& KV : Model.States())
	{
		N += KV.Value.Hole >= 0.12f ? 1 : 0;
	}
	return N;
}

int32 FAstraShipInterior::DarkRooms() const
{
	int32 N = 0;
	for (const auto& KV : Model.States())
	{
		N += (KV.Value.Power < 0.5f || KV.Value.Wreck >= 1.f) ? 1 : 0;
	}
	return N;
}

bool FAstraShipInterior::SectionBurning(int32 WarSection) const
{
	for (const auto& KV : Model.States())
	{
		if (KV.Value.Fire >= 0.10f && WarSectionOf(KV.Key) == WarSection)
		{
			return true;
		}
	}
	return false;
}

bool FAstraShipInterior::SectionVenting(int32 WarSection) const
{
	for (const auto& KV : Model.States())
	{
		if (KV.Value.Hole >= 0.05f && !KV.Value.bGutted && WarSectionOf(KV.Key) == WarSection)
		{
			return true;
		}
	}
	return false;
}

int32 FAstraShipInterior::CaptainState() const
{
	for (const FFleetNamed& N : Named)
	{
		if (N.Role == FName(TEXT("captain")))
		{
			return People[N.Person].State;
		}
	}
	return 0;
}

const FFleetNamed* FAstraShipInterior::Commander() const
{
	const FFleetNamed* Best = nullptr;
	for (const FFleetNamed& N : Named)
	{
		if (People[N.Person].State == 0 && (!Best || N.Line < Best->Line))
		{
			Best = &N;
		}
	}
	return Best;
}
