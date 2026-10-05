#include "AstraWarStats.h"
#include "Algo/Sort.h"
#include "Dom/JsonValue.h"

namespace
{
	const TCHAR* const TypeNames[3] = {TEXT("kinetic"), TEXT("energy"), TEXT("explosive")};
	const TCHAR* const FacingNames[6] = {TEXT("bow"), TEXT("stern"), TEXT("port"), TEXT("starboard"), TEXT("dorsal"), TEXT("ventral")};
	const TCHAR* const SideNames[2] = {TEXT("astra"), TEXT("mandate")};
	const TCHAR* const CraftFateNames[4] = {TEXT("point_defence"), TEXT("craft_guns"), TEXT("missiles"), TEXT("other")};
	const TCHAR* const ShipFateNames[6] = {TEXT("alive"), TEXT("reactor_breach"), TEXT("breakup"), TEXT("disabled"), TEXT("destroyed"), TEXT("withdrew")};

	double Round(double V, double Scale = 100.0)
	{
		return FMath::RoundToDouble(V * Scale) / Scale;
	}

	const TCHAR* const WeaponNames[FAstraWarStats::NumWeapons] = {TEXT("rail"), TEXT("laser"), TEXT("missile"), TEXT("torpedo"), TEXT("rocket"), TEXT("cannon")};
	const double BucketKm[FAstraWarStats::NumRangeBuckets] = {0.0, 2.0, 5.0, 10.0, 15.0, 20.0, 30.0, 40.0, 50.0, 70.0};   // the lower edge of each range bucket
	constexpr int32 MaxFireBins = 7200;                 // two hours of battle
}

int32 FAstraWarStats::RangeBucket(double RangeM)
{
	const double Km = RangeM / 1000.0;
	int32 B = 0;
	for (int32 i = 1; i < NumRangeBuckets; ++i)
	{
		B = Km >= BucketKm[i] ? i : B;
	}
	return B;
}

int32 FAstraWarStats::WeaponOf(EAstraHitKind K)
{
	switch (K)
	{
	case EAstraHitKind::Rail: return WRail;
	case EAstraHitKind::Laser: return WLaser;
	case EAstraHitKind::Missile: return WMissile;
	case EAstraHitKind::Torpedo: return WTorpedo;
	case EAstraHitKind::Rocket: return WRocket;
	default: return WCannon;
	}
}

void FAstraWarStats::NoteFire(float Time, int32 SideIdx, int32 Weapon, double RangeM, bool bCapitalShooter)
{
	if (SideIdx < 0 || SideIdx > 1)
	{
		return;
	}
	++AccShots[SideIdx][Weapon][RangeBucket(RangeM)];
	if (bCapitalShooter)
	{
		const int32 Bin = (int32)FMath::Max(0.f, Time);
		if (Bin < MaxFireBins)
		{
			if (FireBins.Num() <= Bin)
			{
				FireBins.SetNumZeroed(Bin + 1);
			}
			FireBins[Bin] |= (uint8)(1 << SideIdx);
		}
	}
}

void FAstraWarStats::NoteHit(float Time, int32 ShooterSide, int32 VictimSide, int32 Weapon, double FireRangeM, float Damage)
{
	if (ShooterSide >= 0 && ShooterSide <= 1)
	{
		const int32 B = RangeBucket(FireRangeM);
		++AccHits[ShooterSide][Weapon][B];
		AccDamage[ShooterSide][Weapon][B] += Damage;
	}
	if (VictimSide >= 0 && VictimSide <= 1)
	{
		const int32 Bin = (int32)FMath::Max(0.f, Time);
		if (Bin < MaxFireBins)
		{
			if (FireBins.Num() <= Bin)
			{
				FireBins.SetNumZeroed(Bin + 1);
			}
			FireBins[Bin] |= (uint8)(4 << VictimSide);
		}
	}
}

void FAstraWarStats::NoteKill(const FKill& K)
{
	if (Kills.Num() < 1024)
	{
		Kills.Add(K);
	}
}

void FAstraWarStats::NoteRetreat(float Time, int32 SideIdx, const FString& What, int32 Ships)
{
	if (Retreats.Num() < 256)
	{
		FRetreat R;
		R.T = Time;
		R.Side = (int8)SideIdx;
		R.What = What;
		R.Ships = Ships;
		Retreats.Add(R);
	}
}

void FAstraWarStats::NoteFocus(int32 SideIdx, int32 TargetId, double Damage)
{
	if (SideIdx < 0 || SideIdx > 1)
	{
		return;
	}
	int32 Slot = INDEX_NONE;
	for (int32 i = 0; i < WinCount[SideIdx]; ++i)
	{
		if (WinTarget[SideIdx][i] == TargetId)
		{
			Slot = i;
			break;
		}
	}
	if (Slot == INDEX_NONE && WinCount[SideIdx] < 48)
	{
		Slot = WinCount[SideIdx]++;
		WinTarget[SideIdx][Slot] = TargetId;
		WinDmg[SideIdx][Slot] = 0.0;
	}
	if (Slot != INDEX_NONE)
	{
		WinDmg[SideIdx][Slot] += Damage;
		WinTotal[SideIdx] += Damage;
	}
}

void FAstraWarStats::CloseWindow(int32 SideIdx)
{
	if (SideIdx < 0 || SideIdx > 1)
	{
		return;
	}
	if (WinTotal[SideIdx] >= 150.0 && WinCount[SideIdx] > 0)
	{
		double Best = 0.0;
		for (int32 i = 0; i < WinCount[SideIdx]; ++i)
		{
			Best = FMath::Max(Best, WinDmg[SideIdx][i]);
		}
		FocusSum[SideIdx] += Best / WinTotal[SideIdx];
		++FocusWindows[SideIdx];
	}
	WinCount[SideIdx] = 0;
	WinTotal[SideIdx] = 0.0;
}

TSharedRef<FJsonObject> FAstraWarStats::ToJson() const
{
	TSharedRef<FJsonObject> R = MakeShared<FJsonObject>();
	// damage
	TSharedRef<FJsonObject> D = MakeShared<FJsonObject>();
	for (int32 t = 0; t < 3; ++t)
	{
		TSharedRef<FJsonObject> T = MakeShared<FJsonObject>();
		T->SetNumberField(TEXT("in"), Round(DmgIn[t], 10.0));
		T->SetNumberField(TEXT("shield"), Round(DmgShield[t], 10.0));
		T->SetNumberField(TEXT("plate"), Round(DmgPlate[t], 10.0));
		T->SetNumberField(TEXT("structure"), Round(DmgStructure[t], 10.0));
		T->SetNumberField(TEXT("hits"), Hits[t]);
		TSharedRef<FJsonObject> F = MakeShared<FJsonObject>();
		for (int32 f = 0; f < 6; ++f)
		{
			F->SetNumberField(FacingNames[f], Round(DmgFacing[t][f], 10.0));
		}
		T->SetObjectField(TEXT("by_facing"), F);
		D->SetObjectField(TypeNames[t], T);
	}
	D->SetNumberField(TEXT("sectors_collapsed"), SectorsCollapsed);
	R->SetObjectField(TEXT("damage"), D);
	// craft
	TSharedRef<FJsonObject> C = MakeShared<FJsonObject>();
	for (int32 s = 0; s < 2; ++s)
	{
		TSharedRef<FJsonObject> S = MakeShared<FJsonObject>();
		S->SetNumberField(TEXT("launched"), CraftLaunched[s]);
		S->SetNumberField(TEXT("recovered"), CraftRecovered[s]);
		int32 Lost = 0;
		for (int32 k = 0; k < 4; ++k)
		{
			S->SetNumberField(FString::Printf(TEXT("lost_%s"), CraftFateNames[k]), CraftLost[s][k]);
			Lost += CraftLost[s][k];
		}
		S->SetNumberField(TEXT("lost"), Lost);
		C->SetObjectField(SideNames[s], S);
	}
	R->SetObjectField(TEXT("craft"), C);
	// warships
	TSharedRef<FJsonObject> W = MakeShared<FJsonObject>();
	for (int32 s = 0; s < 2; ++s)
	{
		TSharedRef<FJsonObject> S = MakeShared<FJsonObject>();
		for (int32 k = 1; k < 6; ++k)
		{
			S->SetNumberField(ShipFateNames[k], ShipFate[s][k]);
		}
		S->SetNumberField(TEXT("lost_while_retreating"), LostWhileRetreating[s]);
		W->SetObjectField(SideNames[s], S);
	}
	R->SetObjectField(TEXT("ships"), W);
	// missiles
	TSharedRef<FJsonObject> M = MakeShared<FJsonObject>();
	for (int32 s = 0; s < 2; ++s)
	{
		TSharedRef<FJsonObject> S = MakeShared<FJsonObject>();
		S->SetNumberField(TEXT("fired"), MissilesFired[s]);
		S->SetNumberField(TEXT("shot_down"), MissilesShot[s]);
		S->SetNumberField(TEXT("decoyed"), MissilesDecoyed[s]);
		M->SetObjectField(SideNames[s], S);
	}
	R->SetObjectField(TEXT("missiles"), M);
	// focus of fire
	TSharedRef<FJsonObject> Fo = MakeShared<FJsonObject>();
	for (int32 s = 0; s < 2; ++s)
	{
		Fo->SetNumberField(SideNames[s], FocusWindows[s] ? Round(FocusSum[s] / FocusWindows[s], 1000.0) : -1.0);
		Fo->SetNumberField(FString::Printf(TEXT("%s_windows"), SideNames[s]), FocusWindows[s]);
	}
	R->SetObjectField(TEXT("focus"), Fo);
	// the fight log: the chart of the fire second by second, the accuracy at each range, who killed whom, who broke off
	{
		TSharedRef<FJsonObject> F = MakeShared<FJsonObject>();
		FString Bins;
		Bins.Reserve(FireBins.Num());
		for (const uint8 B : FireBins)
		{
			Bins.AppendChar(TEXT("0123456789abcdef")[B & 15]);
		}
		F->SetStringField(TEXT("bins"), Bins);
		TArray<TSharedPtr<FJsonValue>> Edges;
		for (int32 b = 0; b < NumRangeBuckets; ++b)
		{
			Edges.Add(MakeShared<FJsonValueNumber>(BucketKm[b]));
		}
		F->SetArrayField(TEXT("range_buckets_km"), Edges);
		TSharedRef<FJsonObject> Acc = MakeShared<FJsonObject>();
		for (int32 s = 0; s < 2; ++s)
		{
			TSharedRef<FJsonObject> Side = MakeShared<FJsonObject>();
			for (int32 w = 0; w < NumWeapons; ++w)
			{
				TArray<TSharedPtr<FJsonValue>> Sh, Hi, Da;
				int32 Total = 0;
				for (int32 b = 0; b < NumRangeBuckets; ++b)
				{
					Sh.Add(MakeShared<FJsonValueNumber>(AccShots[s][w][b]));
					Hi.Add(MakeShared<FJsonValueNumber>(AccHits[s][w][b]));
					Da.Add(MakeShared<FJsonValueNumber>(Round(AccDamage[s][w][b], 10.0)));
					Total += AccShots[s][w][b];
				}
				if (Total > 0)
				{
					TSharedRef<FJsonObject> Wp = MakeShared<FJsonObject>();
					Wp->SetArrayField(TEXT("shots"), Sh);
					Wp->SetArrayField(TEXT("hits"), Hi);
					Wp->SetArrayField(TEXT("damage"), Da);
					Side->SetObjectField(WeaponNames[w], Wp);
				}
			}
			Acc->SetObjectField(SideNames[s], Side);
		}
		F->SetObjectField(TEXT("accuracy"), Acc);
		F->SetNumberField(TEXT("friendly_hits_astra"), FriendlyHits[0]);
		F->SetNumberField(TEXT("friendly_hits_mandate"), FriendlyHits[1]);
		TArray<TSharedPtr<FJsonValue>> Ks;
		for (const FKill& K : Kills)
		{
			TSharedRef<FJsonObject> J = MakeShared<FJsonObject>();
			J->SetNumberField(TEXT("t"), Round(K.T, 10.0));
			J->SetStringField(TEXT("victim_side"), K.VictimSide == 0 ? TEXT("astra") : TEXT("mandate"));
			J->SetStringField(TEXT("victim"), K.VictimClass.ToString());
			J->SetNumberField(TEXT("victim_tier"), K.VictimTier);
			J->SetBoolField(TEXT("victim_craft"), K.bVictimCraft);
			J->SetStringField(TEXT("killer_side"), K.KillerSide == 0 ? TEXT("astra") : (K.KillerSide == 1 ? TEXT("mandate") : TEXT("none")));
			J->SetStringField(TEXT("killer"), K.bKillerAquila ? FString(TEXT("aquila")) : K.KillerClass.ToString());
			J->SetBoolField(TEXT("killer_aquila"), K.bKillerAquila);
			J->SetBoolField(TEXT("killer_craft"), K.bKillerCraft);
			J->SetBoolField(TEXT("fleeing"), K.bFleeing);
			J->SetStringField(TEXT("weapon"), WeaponNames[FMath::Clamp<int32>(K.Weapon, 0, NumWeapons - 1)]);
			J->SetStringField(TEXT("how"), ShipFateNames[FMath::Clamp<int32>(K.How, 0, 5)]);
			J->SetNumberField(TEXT("range_km"), Round(K.KillRangeKm, 10.0));
			Ks.Add(MakeShared<FJsonValueObject>(J));
		}
		F->SetArrayField(TEXT("kills"), Ks);
		TArray<TSharedPtr<FJsonValue>> Rs;
		for (const FRetreat& Rt : Retreats)
		{
			TSharedRef<FJsonObject> J = MakeShared<FJsonObject>();
			J->SetNumberField(TEXT("t"), Round(Rt.T, 10.0));
			J->SetStringField(TEXT("side"), Rt.Side == 0 ? TEXT("astra") : TEXT("mandate"));
			J->SetStringField(TEXT("what"), Rt.What);
			J->SetNumberField(TEXT("ships"), Rt.Ships);
			Rs.Add(MakeShared<FJsonValueObject>(J));
		}
		F->SetArrayField(TEXT("retreats"), Rs);
		R->SetObjectField(TEXT("fight"), F);
	}
	// what the simulation costs
	TSharedRef<FJsonObject> P = MakeShared<FJsonObject>();
	P->SetNumberField(TEXT("ticks"), Ticks);
	P->SetNumberField(TEXT("ms_avg"), Ticks ? Round(TickMsSum / Ticks, 1000.0) : 0.0);
	P->SetNumberField(TEXT("ms_max"), Round(TickMsMax, 1000.0));
	if (TickMsSamples.Num())
	{
		TArray<float> Sorted = TickMsSamples;
		Algo::Sort(Sorted);
		auto Pct = [&Sorted](double Q) { return Sorted[FMath::Clamp((int32)(Q * (Sorted.Num() - 1)), 0, Sorted.Num() - 1)]; };
		P->SetNumberField(TEXT("ms_p50"), Round(Pct(0.5), 1000.0));
		P->SetNumberField(TEXT("ms_p95"), Round(Pct(0.95), 1000.0));
		P->SetNumberField(TEXT("ms_p99"), Round(Pct(0.99), 1000.0));
	}
	{
		static const TCHAR* const Names[NumPhases] = {TEXT("knowledge_grid"), TEXT("groups"), TEXT("squadrons"), TEXT("ships"), TEXT("craft"), TEXT("projectiles_effects")};
		TSharedRef<FJsonObject> Ph = MakeShared<FJsonObject>();
		for (int32 p = 0; p < NumPhases; ++p)
		{
			TSharedRef<FJsonObject> One = MakeShared<FJsonObject>();
			One->SetNumberField(TEXT("ms_avg"), Ticks ? Round(PhaseSum[p] / Ticks, 1000.0) : 0.0);
			One->SetNumberField(TEXT("ms_max"), Round(PhaseMax[p], 1000.0));
			Ph->SetObjectField(Names[p], One);
		}
		P->SetObjectField(TEXT("phases"), Ph);
	}
	P->SetNumberField(TEXT("peak_ships"), PeakShips);
	P->SetNumberField(TEXT("peak_craft"), PeakCraft);
	P->SetNumberField(TEXT("peak_projectiles"), PeakProjectiles);
	R->SetObjectField(TEXT("perf"), P);
	return R;
}
