// ASTRA — FLOTTA-VIVA: where the war and the insides of its ships meet (docs/FLOTTA-VIVA.md).
//
// A warship that is not the Aquila gets, at the first blow that gets through its shield and its plating, an interior: its class's plan and the
// Aquila's damage model run on it (AstraFleetInterior.*). From then on every blow the war lands on it also enters the interior, where it struck, and
// the interior goes on beside the war's own model: what comes out is the power each allocation still carries (shields, weapons, engines, sensors,
// flight deck), what burns and vents (the war's sections' flags, which the effects draw), how many are left and who commands, and the news the
// ship's side is told.
//
// Here: the switch and the tuning (astra.fleet.*), the interior's birth and its tick, what it gives back, the views, the bench's counters and the console.

#include "AstraBattleSubsystem.h"

#include "ASTRA.h"
#include "AstraFleetInterior.h"
#include "AstraWarClasses.h"
#include "HAL/IConsoleManager.h"
#include "Misc/DefaultValueHelper.h"

namespace
{
	int32 GFleetInterior = 1;           // 1: the other ships have an inside; 0: they have not (the war's section model alone, as before FLOTTA-VIVA)
	float GFleetPowerK = 1.f;           // how much of what the inside loses goes back to the war: 1 all of it, 0 none (the war is as before, the inside is only read)
	float GFleetCrewDisable = 0.12f;    // the share of a crew that must be left to fight a ship: under it she is a hulk
	float GFleetNewsGap = 10.f;         // the war is told news of one ship at most every so many seconds

	FAutoConsoleVariableRef CVarFleetInterior(TEXT("astra.fleet.interior"), GFleetInterior, TEXT("FLOTTA-VIVA: 1 the other ships of the war have an inside (their class's plan, the Aquila's damage model), 0 they have not"));
	FAutoConsoleVariableRef CVarFleetPowerK(TEXT("astra.fleet.power_k"), GFleetPowerK, TEXT("FLOTTA-VIVA: how much of what a ship's inside loses of its power goes back into the war (1 all, 0 none)"));
	FAutoConsoleVariableRef CVarFleetCrew(TEXT("astra.fleet.crew_min"), GFleetCrewDisable, TEXT("FLOTTA-VIVA: the share of a crew (fit and half the wounded) under which a ship can no longer be fought"));
	FAutoConsoleVariableRef CVarFleetNews(TEXT("astra.fleet.news_gap"), GFleetNewsGap, TEXT("FLOTTA-VIVA: seconds between two pieces of news of one ship"));

	FAutoConsoleCommandWithWorldAndArgs CmdFleetInfo(TEXT("astra.fleet.info"), TEXT("FLOTTA-VIVA: a ship's inside in a line (astra.fleet.info [contact id]), or every ship that has one"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (UAstraBattleSubsystem* B = World ? World->GetSubsystem<UAstraBattleSubsystem>() : nullptr)
			{
				UE_LOG(LogASTRA, Display, TEXT("%s"), *B->FleetConsole(TEXT("info"), Args));
			}
		}));
	FAutoConsoleCommandWithWorldAndArgs CmdFleetStrike(TEXT("astra.fleet.strike"), TEXT("FLOTTA-VIVA: a blow into a room of a ship (astra.fleet.strike <contact id> <room id or part of a name> [energy 40] [kinetic|energy|explosive])"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (UAstraBattleSubsystem* B = World ? World->GetSubsystem<UAstraBattleSubsystem>() : nullptr)
			{
				UE_LOG(LogASTRA, Display, TEXT("%s"), *B->FleetConsole(TEXT("strike"), Args));
			}
		}));
	FAutoConsoleCommandWithWorldAndArgs CmdFleetPound(TEXT("astra.fleet.pound"), TEXT("FLOTTA-VIVA: many blows on a face of a ship (astra.fleet.pound <contact id> <face> [damage 150] [count 20] [rail|laser|missile]): the bench's way to break a ship at a section"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (UAstraBattleSubsystem* B = World ? World->GetSubsystem<UAstraBattleSubsystem>() : nullptr)
			{
				UE_LOG(LogASTRA, Display, TEXT("%s"), *B->FleetConsole(TEXT("pound"), Args));
			}
		}));
	FAutoConsoleCommandWithWorldAndArgs CmdFleetSnapshot(TEXT("astra.fleet.snapshot"), TEXT("FLOTTA-VIVA: what a boarding would be given of a ship's inside, in a line of counts (astra.fleet.snapshot <contact id>)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (UAstraBattleSubsystem* B = World ? World->GetSubsystem<UAstraBattleSubsystem>() : nullptr)
			{
				UE_LOG(LogASTRA, Display, TEXT("%s"), *B->FleetConsole(TEXT("snapshot"), Args));
			}
		}));
	FAutoConsoleCommandWithWorldAndArgs CmdFleetCaptain(TEXT("astra.fleet.captain"), TEXT("FLOTTA-VIVA: who commands a ship, by the name and the rank the minds know them by (astra.fleet.captain <contact id> <rank> <name>, underscores for spaces)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (UAstraBattleSubsystem* B = World ? World->GetSubsystem<UAstraBattleSubsystem>() : nullptr)
			{
				UE_LOG(LogASTRA, Display, TEXT("%s"), *B->FleetConsole(TEXT("captain"), Args));
			}
		}));
	FAutoConsoleCommandWithWorldAndArgs CmdFleetHit(TEXT("astra.fleet.hit"), TEXT("FLOTTA-VIVA: a blow on a face of a ship, through the war's own path (astra.fleet.hit <contact id> <bow|stern|port|starboard|dorsal|ventral> [damage 120] [rail|laser|missile])"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (UAstraBattleSubsystem* B = World ? World->GetSubsystem<UAstraBattleSubsystem>() : nullptr)
			{
				UE_LOG(LogASTRA, Display, TEXT("%s"), *B->FleetConsole(TEXT("hit"), Args));
			}
		}));

	/** A class's key as the war names it ("praetorian"), or none (craft, decoys, the Aquila). */
	bool FleetClassHasInterior(const FAstraBattleShip& S)
	{
		return !S.bPlayer && !S.bCraft && !S.bGhost && S.Dmg.bModel && !S.ClassKey.IsNone() && S.ClassKey != FName(TEXT("aquila"));
	}
}

bool UAstraBattleSubsystem::FleetOn() const
{
	return GFleetInterior != 0;
}

FAstraShipInterior* UAstraBattleSubsystem::FleetInterior(int32 ShipId) const
{
	const FAstraBattleShip* S = FindById(ShipId);
	return S ? S->Interior.Get() : nullptr;
}

FAstraShipInterior* UAstraBattleSubsystem::FleetEnsure(FAstraBattleShip& S)
{
	if (S.Interior.IsValid())
	{
		return S.Interior.Get();
	}
	if (!FleetOn() || !FleetClassHasInterior(S))
	{
		return nullptr;
	}
	const double T0 = FPlatformTime::Seconds();
	// (the plan was read on a worker when the first ship of the class was born: in play it is long ready, and a blow never waits for it; a bench, which fights a battle in a second and must
	// give the same answer every time, waits)
	TSharedPtr<const FFleetClassPlan> Plan = FAstraFleetPlans::Find(S.ClassKey, GAstraDeterministic);
	if (!Plan.IsValid())
	{
		return nullptr;
	}
	const double T1 = FPlatformTime::Seconds();
	S.Interior = MakeShared<FAstraShipInterior>(Plan.ToSharedRef(), S.Id, S.Name, 7001 + S.Id * 7919 + (GAstraDeterministic ? 0 : (int32)(FPlatformTime::Cycles64() & 0xffff)));
	if (!S.CaptainName.IsEmpty())
	{
		S.Interior->SetCaptain(S.CaptainRank, S.CaptainName);
	}
	const double T2 = FPlatformTime::Seconds();
	++FleetMade;
	FleetWaitMsMax = FMath::Max(FleetWaitMsMax, (T1 - T0) * 1000.0);
	FleetMakeMsMax = FMath::Max(FleetMakeMsMax, (T2 - T1) * 1000.0);
	return S.Interior.Get();
}

float UAstraBattleSubsystem::FleetFactor(const FAstraBattleShip& S, int32 Category) const
{
	return S.Interior.IsValid() && FleetOn() ? 1.f - GFleetPowerK * (1.f - S.Interior->Factor((EAstraDmgCategory)Category)) : 1.f;
}

float UAstraBattleSubsystem::FleetSys(const FAstraBattleShip& S, int32 WarSystem) const
{
	return S.Interior.IsValid() && FleetOn() ? 1.f - GFleetPowerK * (1.f - S.Interior->SysFit(WarSystem)) : 1.f;
}

void UAstraBattleSubsystem::FleetOnHit(FAstraBattleShip& To, const FAstraHullHit& Hit)
{
	FAstraShipInterior* I = FleetOn() ? FleetEnsure(To) : nullptr;
	if (!I)
	{
		return;
	}
	const double T0 = FPlatformTime::Seconds();
	I->Impact(Hit);
	++FleetBlows;
	const double Ms = (FPlatformTime::Seconds() - T0) * 1000.0;
	FleetMs += Ms;
	FleetMsMax = FMath::Max(FleetMsMax, Ms);
}

bool UAstraBattleSubsystem::FleetSetCaptain(const FString& ContactId, const FString& Rank, const FString& Name)
{
	FAstraBattleShip* S = FindByContact(ContactId.ToUpper());
	if (!S || Name.IsEmpty())
	{
		return false;
	}
	S->CaptainRank = Rank;
	S->CaptainName = Name;
	if (S->Interior.IsValid())
	{
		S->Interior->SetCaptain(Rank, Name);
	}
	return true;
}

bool UAstraBattleSubsystem::FleetSnapshot(int32 ShipId, FFleetSnapshot& Out) const
{
	if (const FAstraShipInterior* I = FleetInterior(ShipId))
	{
		I->Snapshot(Out);
		return true;
	}
	return false;
}

void UAstraBattleSubsystem::FleetOnDestroyed(FAstraBattleShip& S)
{
	if (FAstraShipInterior* I = S.Interior.Get())
	{
		I->LoseWithShip();
	}
}

void UAstraBattleSubsystem::FleetOnGutted(FAstraBattleShip& S, int32 Section)
{
	if (FAstraShipInterior* I = S.Interior.Get())
	{
		I->GutSection(Section);
	}
}

void UAstraBattleSubsystem::FleetTick(FAstraBattleShip& S, float Dt)
{
	FAstraShipInterior* I = S.Interior.Get();
	if (!I)
	{
		return;
	}
	if (!FleetOn())
	{
		// switched off in the middle of a battle: the war goes back to what it was (the inside stays as it is, silent, for when it is switched on again)
		S.ShieldPower = 1.f;
		S.WeaponPower = 1.f;
		for (FAstraMount& M : S.Mounts)
		{
			M.Feed = 1.f;
		}
		return;
	}
	const double T0 = FPlatformTime::Seconds();
	I->Tick(Dt);
	// what comes out of it, into the war's own fields: the power each allocation still carries (as the Aquila's does through the ship subsystem), and the people who work the guns
	S.ShieldPower = FleetFactor(S, (int32)EAstraDmgCategory::Shields);
	S.WeaponPower = FleetFactor(S, (int32)EAstraDmgCategory::Weapons) * (1.f - GFleetPowerK * (1.f - I->WeaponCrew()));
	// each weapon mount is served by a room of the plan: its barbette, its magazine; what that room gives (fabric and power) is the mount's feed
	for (int32 m = 0; m < S.Mounts.Num(); ++m)
	{
		S.Mounts[m].Feed = 1.f - GFleetPowerK * (1.f - I->MountFit(m));
	}
	// what burns and vents sets the war's sections' flags (the effects draw them); the structure the fires eat is the model's (as the Aquila's: the war's own flat rate is not applied to a ship with an inside)
	FAstraShipDamage& D = S.Dmg;
	for (int32 Sec = 0; Sec < AstraWar::NumSections; ++Sec)
	{
		if (I->SectionBurning(Sec))
		{
			D.Burn[Sec] = FMath::Max(D.Burn[Sec], 3.f);
		}
		if (I->SectionVenting(Sec))
		{
			D.Breach[Sec] = FMath::Max(D.Breach[Sec], 3.f);
		}
	}
	if (const float Burnt = I->TakeBurn(); Burnt > 0.f && !S.bDisabled)
	{
		AddHullDelta(S, -Burnt);
	}
	// a ship with nobody left to fight her is a hulk
	if (S.bAlive && !S.bDisabled && I->CrewTotal() >= 6 && I->CrewStrength() < GFleetCrewDisable)
	{
		DisableShip(S, TEXT("her crew is dead"));
	}
	// the news, to the ship's own side (the Mandate's stays private to its minds, as the war's other group events do)
	TArray<FString> News;
	I->CollectNews(News);
	if (News.Num() && Time - S.FleetNewsT >= GFleetNewsGap && !S.bCraft)
	{
		S.FleetNewsT = Time;
		const int32 Side = AstraSideIdx(S.Side);
		for (const FString& N : News)
		{
			NoteGroupEvent(Side, N);
		}
	}
	const double Ms = (FPlatformTime::Seconds() - T0) * 1000.0;
	FleetMs += Ms;
	FleetMsMax = FMath::Max(FleetMsMax, Ms);
	++FleetTicks;
}

void UAstraBattleSubsystem::FleetBriefInto(const FAstraBattleShip& S, const TSharedRef<FJsonObject>& Into, bool bOwn, int32 Detail) const
{
	const FAstraShipInterior* I = S.Interior.Get();
	if (!I)
	{
		return;
	}
	TSharedRef<FJsonObject> J = bOwn ? I->BriefJson() : I->SeenJson(Detail);
	if (J->Values.Num())
	{
		Into->SetObjectField(bOwn ? TEXT("aboard") : TEXT("seen_aboard"), J);
	}
}

TSharedRef<FJsonObject> UAstraBattleSubsystem::FleetStatsJson() const
{
	TSharedRef<FJsonObject> J = MakeShared<FJsonObject>();
	int32 With[2] = {0, 0}, Killed[2] = {0, 0}, Wounded[2] = {0, 0}, Crew[2] = {0, 0}, LostShip[2] = {0, 0}, Calm = 0;
	for (const FAstraBattleShip& S : Ships)
	{
		const FAstraShipInterior* I = S.Interior.Get();
		const int32 Side = AstraSideIdx(S.Side);
		if (!I || Side < 0)
		{
			continue;
		}
		++With[Side];
		Killed[Side] += I->CrewDead();
		LostShip[Side] += I->CrewLostWithShip();
		Wounded[Side] += I->CrewWounded();
		Crew[Side] += I->CrewTotal();
		Calm += I->IsCalm() ? 1 : 0;
	}
	J->SetBoolField(TEXT("on"), FleetOn());
	J->SetNumberField(TEXT("ships_with_interior_astra"), With[0]);
	J->SetNumberField(TEXT("ships_with_interior_mandate"), With[1]);
	J->SetNumberField(TEXT("calm_now"), Calm);
	J->SetNumberField(TEXT("killed_astra"), Killed[0]);
	J->SetNumberField(TEXT("killed_mandate"), Killed[1]);
	J->SetNumberField(TEXT("lost_with_ships_astra"), LostShip[0]);
	J->SetNumberField(TEXT("lost_with_ships_mandate"), LostShip[1]);
	J->SetNumberField(TEXT("wounded_astra"), Wounded[0]);
	J->SetNumberField(TEXT("wounded_mandate"), Wounded[1]);
	J->SetNumberField(TEXT("crew_astra"), Crew[0]);
	J->SetNumberField(TEXT("crew_mandate"), Crew[1]);
	J->SetNumberField(TEXT("made"), FleetMade);                                                               // the insides built (one at the first blow through a ship's plating)
	J->SetNumberField(TEXT("make_ms_max"), FMath::RoundToDouble(FleetMakeMsMax * 1000.0) / 1000.0);         // the dearest one: the crew, the model
	J->SetNumberField(TEXT("plan_wait_ms_max"), FMath::RoundToDouble(FleetWaitMsMax * 1000.0) / 1000.0);    // the wait for a class's plan (a worker reads it when the first ship of the class is born: in real time it is long ready)
	J->SetNumberField(TEXT("blows"), FleetBlows);
	J->SetNumberField(TEXT("ticks"), FleetTicks);
	J->SetNumberField(TEXT("ms_total"), FMath::RoundToDouble(FleetMs * 1000.0) / 1000.0);
	J->SetNumberField(TEXT("ms_worst_call"), FMath::RoundToDouble(FleetMsMax * 1000.0) / 1000.0);
	return J;
}

FString UAstraBattleSubsystem::FleetInfo(const FString& ContactId) const
{
	const FAstraBattleShip* S = FindByContact(ContactId.ToUpper());
	if (!S)
	{
		return FString::Printf(TEXT("no ship %s"), *ContactId);
	}
	return S->Interior.IsValid() ? S->Interior->InfoText() : FString::Printf(TEXT("%s (%s): no inside yet (not hit through the plating, or its class has no plan)"), *S->Name, *S->ClassKey.ToString());
}

FString UAstraBattleSubsystem::FleetConsole(const FString& What, const TArray<FString>& Args)
{
	if (What == TEXT("info"))
	{
		if (Args.Num())
		{
			return FleetInfo(Args[0]);
		}
		int32 N = 0;
		for (const FAstraBattleShip& S : Ships)
		{
			if (S.Interior.IsValid())
			{
				UE_LOG(LogASTRA, Display, TEXT("  %s %s"), *S.ContactId, *S.Interior->InfoText());
				++N;
			}
		}
		return FString::Printf(TEXT("fleet interiors (%s): %d ships have one; %d blows, %.2f ms in all (worst call %.2f ms)"), FleetOn() ? TEXT("on") : TEXT("off"), N, FleetBlows, FleetMs, FleetMsMax);
	}
	if (What == TEXT("captain"))
	{
		// astra.fleet.captain <contact> <rank> <name>: underscores stand for spaces ("Lieutenant_Commander", "Rhea_Castellan")
		if (Args.Num() < 3)
		{
			return TEXT("astra.fleet.captain <contact id> <rank> <name>  (underscores for spaces)");
		}
		return FleetSetCaptain(Args[0], Args[1].Replace(TEXT("_"), TEXT(" ")), Args[2].Replace(TEXT("_"), TEXT(" "))) ? FString::Printf(TEXT("%s: captain %s %s"), *Args[0].ToUpper(), *Args[1], *Args[2]) : FString::Printf(TEXT("no ship %s"), *Args[0]);
	}
	if (What == TEXT("selftest"))
	{
		TArray<FString> Lines;
		const int32 Failed = AstraFleetSelfTest(Lines);
		for (const FString& L : Lines)
		{
			UE_LOG(LogASTRA, Display, TEXT("[FleetTest] %s"), *L);
		}
		return FString::Printf(TEXT("the checks of the insides: %s"), Failed == 0 ? TEXT("PASS") : TEXT("FAIL"));
	}
	if (Args.Num() < (What == TEXT("snapshot") ? 1 : 2))
	{
		return TEXT("astra.fleet.strike <contact> <room> [energy] [type] | astra.fleet.hit <contact> <face> [damage] [rail|laser|missile] | astra.fleet.pound <contact> <face> [damage] [count] [kind] | snapshot <contact>");
	}
	FAstraBattleShip* S = FindByContact(Args[0].ToUpper());
	if (!S || !S->bAlive)
	{
		return FString::Printf(TEXT("no live ship %s"), *Args[0]);
	}
	if (What == TEXT("strike"))
	{
		FAstraShipInterior* I = FleetEnsure(*S);
		if (!I)
		{
			return TEXT("that ship has no plan");
		}
		const FAstraDamageMap& M = I->GetPlan().Map.ToSharedRef().Get();
		int32 Comp = INDEX_NONE;
		if (const int32* Exact = M.CompByName.Find(FName(*Args[1])))
		{
			Comp = *Exact;
		}
		else
		{
			for (int32 i = 0; i < M.Comps.Num() && Comp == INDEX_NONE; ++i)
			{
				if (M.Comps[i].Name.Contains(Args[1]) || M.Comps[i].Kind.ToString().Contains(Args[1]))
				{
					Comp = i;
				}
			}
		}
		if (Comp == INDEX_NONE)
		{
			return FString::Printf(TEXT("no room like %s"), *Args[1]);
		}
		const float Energy = Args.IsValidIndex(2) ? FCString::Atof(*Args[2]) : 40.f;
		const uint8 Type = Args.IsValidIndex(3) ? (Args[3].StartsWith(TEXT("e")) ? 1 : (Args[3].StartsWith(TEXT("x")) ? 2 : 0)) : 0;
		I->Strike(Comp, Energy, Type, true);
		return FString::Printf(TEXT("struck %s in %s: %s"), *S->ContactId, *M.Describe(Comp), *I->InfoText());
	}
	if (What == TEXT("snapshot"))
	{
		// what a boarding would be given of her inside (ABBORDAGGI): a line of counts
		FFleetSnapshot Snap;
		if (!FleetSnapshot(S->Id, Snap))
		{
			return FString::Printf(TEXT("%s: no inside (yet)"), *S->ContactId);
		}
		int32 Gutted = 0, Burning = 0, Venting = 0, Dark = 0, Locked = 0, Wounded = 0, Named = 0;
		for (const FFleetSnapshot::FRoom& R : Snap.Rooms)
		{
			Gutted += R.bGutted ? 1 : 0;
			Burning += R.Fire >= 0.10f ? 1 : 0;
			Venting += R.Hole >= 0.12f ? 1 : 0;
			Dark += R.Power < 0.5f ? 1 : 0;
			Locked += R.bLocked ? 1 : 0;
		}
		for (const FFleetSnapshot::FHand& H : Snap.Hands)
		{
			Wounded += H.bWounded ? 1 : 0;
			Named += H.Billet.IsEmpty() ? 0 : 1;
		}
		return FString::Printf(TEXT("%s snapshot: %d rooms not as built (%d gutted, %d burning, %d venting, %d dark, %d locked down), %d pressure bulkheads shut, %d alive (%d wounded, %d named), %d killed, %d lost with the ship; command: %s"),
		                       *S->ContactId, Snap.Rooms.Num(), Gutted, Burning, Venting, Dark, Locked, Snap.SealedDoors.Num(), Snap.Hands.Num(), Wounded, Named, Snap.Killed, Snap.LostWithShip, Snap.Command.IsEmpty() ? TEXT("none") : *Snap.Command);
	}
	if (What == TEXT("hit") || What == TEXT("pound"))
	{
		// blows on a face of the box, aimed about the middle of the ship: through the war's own path (shield, plate, structure, then the inside)
		const bool bPound = What == TEXT("pound");
		const FString Face = Args[1].ToLower();
		int32 F = AstraWar::Ventral;
		if (Face.StartsWith(TEXT("bow"))) { F = AstraWar::Bow; }
		else if (Face.StartsWith(TEXT("stern"))) { F = AstraWar::Stern; }
		else if (Face.StartsWith(TEXT("port"))) { F = AstraWar::Port; }
		else if (Face.StartsWith(TEXT("star"))) { F = AstraWar::Starboard; }
		else if (Face.StartsWith(TEXT("dor"))) { F = AstraWar::Dorsal; }
		const FVector Out = AstraWar::FacingVector(F);
		if (!S->Box.Valid())
		{
			return TEXT("that ship has no hull box");
		}
		const float Damage = Args.IsValidIndex(2) ? FCString::Atof(*Args[2]) : (bPound ? 150.f : 120.f);
		const int32 Count = bPound ? FMath::Clamp(Args.IsValidIndex(3) ? FCString::Atoi(*Args[3]) : 20, 1, 5000) : 1;
		const int32 KindArg = bPound ? 4 : 3;
		const EAstraHitKind Kind = Args.IsValidIndex(KindArg) ? (Args[KindArg].StartsWith(TEXT("m")) ? EAstraHitKind::Missile : (Args[KindArg].StartsWith(TEXT("l")) ? EAstraHitKind::Laser : EAstraHitKind::Rail)) : EAstraHitKind::Rail;
		if (FAstraShipInterior* I = FleetEnsure(*S))
		{
			I->KeepTrace(!bPound);
		}
		const AstraWar::FHullBox& Bx = S->Box;
		int32 Landed = 0;
		for (int32 n = 0; n < Count && S->bAlive; ++n)
		{
			const double R1 = FMath::FRandRange(-0.6f, 0.6f), R2 = FMath::FRandRange(-0.6f, 0.6f);
			FVector LocalPoint = F <= AstraWar::Stern ? FVector(Out.X * Bx.Hx, R1 * Bx.Hy, R2 * Bx.Hz) : (F <= AstraWar::Starboard ? FVector(R1 * Bx.Hx, Out.Y * Bx.Hy, R2 * Bx.Hz) : FVector(R1 * Bx.Hx, R2 * Bx.Hy, Out.Z * Bx.Hz));
			LocalPoint.X += Bx.Mid;
			const FVector Pos = S->Pos + S->Att.RotateVector(LocalPoint);
			const FVector Dir = S->Att.RotateVector(-Out);
			ApplyHit(*S, Dir, Damage, Pos, Kind, -1);
			++Landed;
		}
		FString Text;
		if (!bPound && S->Interior.IsValid() && !S->Interior->TraceText().IsEmpty())
		{
			Text = S->Interior->TraceText();
		}
		else if (S->Interior.IsValid())
		{
			Text = S->Interior->InfoText();
		}
		else
		{
			Text = FString::Printf(TEXT("%s: no inside (yet)"), *S->ContactId);
		}
		if (bPound)
		{
			const FAstraShipDamage& D = S->Dmg;
			Text = FString::Printf(TEXT("%d blows of %.0f on the %s of %s: hull %.0f%%, structure bow/mid/stern %.0f/%.0f/%.0f%%, %s | %s"), Landed, Damage, *Face, *S->ContactId, 100.f * S->Hull / FMath::Max(1.f, S->HullMax),
			                       100.f * D.Structure[0] / FMath::Max(1.f, D.StructureMax[0]), 100.f * D.Structure[1] / FMath::Max(1.f, D.StructureMax[1]), 100.f * D.Structure[2] / FMath::Max(1.f, D.StructureMax[2]),
			                       S->bAlive ? TEXT("alive") : TEXT("destroyed"), *Text);
		}
		return Text;
	}
	return TEXT("astra.fleet.info | strike | hit | pound | snapshot");
}
