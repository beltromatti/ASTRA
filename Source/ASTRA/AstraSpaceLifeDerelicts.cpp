// ASTRA — the hulks left behind, in the game: a ship the war disabled (or a dead station or freighter a beat put in the system) is recorded when the Aquila leaves the system and when the campaign is saved, and
// made again in the plot where the arithmetic puts her when the Aquila comes back; the crew is told when she is found. The records and their rules are plain C++ (AstraDerelicts.*); what and why: docs/SPAZIO.md §3ter.

#include "AstraSpaceLife.h"
#include "AstraBattleSubsystem.h"
#include "AstraFleetInterior.h"
#include "ASTRA.h"
#include "Engine/World.h"
#include "HAL/IConsoleManager.h"

using AstraSpace::FDerelict;
using AstraSpace::FDerelicts;
using AstraSpace::FWrecks;

namespace
{
	constexpr double DrKm = 1000.0;

	TAutoConsoleVariable<float> CVarDrBrake(TEXT("astra.space.derelicts.brake"), (float)AstraSpace::FDerelicts::DefaultBrakeS,
		TEXT("How long a hulk left behind takes to be brought to rest by the system's traffic control (s: her velocity falls as e^(-t/this)); 0 leaves her the war's drift (a few hundred m/s: she is lost in minutes)"),
		FConsoleVariableDelegate::CreateLambda([](IConsoleVariable* V) { AstraSpace::FDerelicts::SetBrakeS(V->GetFloat()); }));
}

// ------------------------------------------------------------------------------------------------------------------ the plot's hulks, as records
void UAstraSpaceLife::CaptureDerelicts(TArray<FDerelict>& Out) const
{
	if (!bLaidOut || !Owner)
	{
		return;
	}
	const double Now = WreckClock();
	const FVector SpinAxisSystem = FVector(0.2, 0.3, 1.0).GetSafeNormal();                   // (the war's own: a hulk tumbles about this axis, AstraBattleSubsystem::TickAI)
	for (const FAstraBattleShip& S : Owner->Ships)
	{
		if (Out.Num() >= FDerelicts::MaxHulks)
		{
			break;
		}
		if (!S.bAlive || S.bPlayer || S.bCraft || S.bFixture || S.bWreck || S.bGhost || S.bPiloted || !(S.bDisabled || S.bDerelict))
		{
			continue;
		}
		FDerelict D;
		D.System = SystemKey;
		D.ShipId = S.Id;
		D.Name = S.Name;
		D.Class = S.Class;
		D.Contact = S.ContactId;
		D.Mesh = S.Mesh;
		D.ClassKey = S.ClassKey;
		D.Side = S.Side == EAstraSide::Astra ? 0 : (S.Side == EAstraSide::Mandate ? 1 : 2);
		D.bModel = S.Dmg.bModel;
		D.bHostile = S.bHostile;
		D.bFog = S.bFog;
		D.bIdentified = S.bIdentified;
		D.bClassified = S.bClassified;
		D.bDisabledShip = S.bDisabled;
		D.bToldBack = false;
		for (const FFoundHulk& Hk : FoundHulks)
		{
			D.bToldBack |= Hk.PlotId == S.Id && Hk.bTold;                                      // (the crew has already been told she is still here)
		}
		D.T0 = Now;
		D.Pos0 = Sky.FromSystem(S.Pos);
		D.Vel = Sky.DirFromSystem(S.Vel);
		D.Att0 = Sky.FromSystem(S.Att);
		D.SpinAxis = Sky.DirFromSystem(SpinAxisSystem);
		D.SpinRate = FMath::DegreesToRadians(S.SpinDeg);
		D.Radius = S.Radius;
		D.HullFrac = S.HullMax > 0.f ? FMath::Clamp(S.Hull / S.HullMax, 0.f, 1.f) : 1.f;
		D.Missiles = S.Missiles;
		D.Torpedoes = S.Torpedoes;
		if (S.Dmg.bModel)
		{
			for (int32 s = 0; s < AstraWar::NumSections; ++s)
			{
				D.Structure[s] = S.Dmg.StructureMax[s] > 0.f ? FMath::Clamp(S.Dmg.Structure[s] / S.Dmg.StructureMax[s], 0.f, 1.f) : 1.f;
				D.Gutted |= S.Dmg.GuttedT[s] >= 0.f ? (uint8)(1 << s) : (uint8)0;
				for (int32 f = 0; f < AstraWar::NumFacings; ++f)
				{
					D.Plates[s * AstraWar::NumFacings + f] = S.Dmg.PlateMax[s][f] > 0.f ? FMath::Clamp(S.Dmg.Plate[s][f] / S.Dmg.PlateMax[s][f], 0.f, 1.f) : 0.f;
				}
			}
			for (int32 i = 0; i < AstraWar::NumSystems; ++i)
			{
				D.Sys[i] = FMath::Clamp(S.Dmg.Sys[i], 0.f, 1.f);
			}
		}
		// what is aboard: her inside's own count where she had one (she was hit through her plating), else her class's roster, all alive; a dead hulk of a beat has nobody
		AstraSpace::FAboard& A = D.Aboard;
		const uint8 Faction = D.Side;
		if (const FAstraShipInterior* I = S.Interior.Get())
		{
			A.bInside = true;
			A.Complement = I->CrewTotal();
			A.Killed = I->CrewDead();
			A.Alive = I->CrewFit() + I->CrewWounded();
			AstraSpaceFillAboardRooms(*I, A);
		}
		else
		{
			A.Complement = FWrecks::ComplementOf(S.ClassKey, S.Radius, Faction);
			A.Alive = S.bDisabled ? A.Complement : 0;
		}
		Out.Add(MoveTemp(D));
	}
}

// ------------------------------------------------------------------------------------------------------------------ made again
int32 UAstraSpaceLife::MakeDerelict(const FDerelict& D, double Now)
{
	const FVector Pos = Sky.ToSystem(FDerelicts::PosAt(D, Now));
	FString Contact = D.Contact;
	if (Contact.IsEmpty() || Owner->FindByContact(Contact))
	{
		Contact = FString::Printf(TEXT("T-%d"), Owner->NextContact++);                        // (her number is in use now: the plot gives her a new one)
	}
	const EAstraSide Side = D.Side == 0 ? EAstraSide::Astra : (D.Side == 1 ? EAstraSide::Mandate : EAstraSide::Neutral);
	int32 I = INDEX_NONE;
	const bool bShip = D.bModel && D.bDisabledShip && !D.ClassKey.IsNone();
	if (bShip)
	{
		I = Owner->SpawnByKey(D.ClassKey, Side, Contact, D.Name, Pos, 0.f);                   // the war's own model of her class (its sections, plates, systems, mounts) and her mesh
	}
	if (I == INDEX_NONE)
	{
		I = Owner->AddShip(Contact, D.Name, D.Class, D.Mesh, Side, Pos, 0.f, 0.f, D.Radius, 5000.f, 0.f);
		Owner->SpawnVisual(Owner->Ships[I]);
	}
	FAstraBattleShip& S = Owner->Ships[I];
	if (!D.Class.IsEmpty())
	{
		S.Class = D.Class;
	}
	S.Att = Sky.ToSystem(FDerelicts::AttAt(D, Now));
	S.Vel = Sky.DirToSystem(FDerelicts::VelAt(D, Now));
	S.SpinDeg = FMath::RadiansToDegrees(D.SpinRate);
	S.bHostile = D.bHostile;
	S.bFog = D.bFog;
	S.bIdentified = D.bIdentified;
	S.bClassified = D.bClassified;
	S.Track = D.bFog ? 0 : 2;                                                                // (a ship under the fog of war must be found again; the rest were always on the plot)
	S.TrackHold = 0.f;
	S.RailDamage = bShip ? S.RailDamage : 0.f;
	if (bShip)
	{
		// the war's model as it was when she was left: her structure by section, her plates, her systems, then what DisableShip does (no power: no shields, the reactor out, nothing aimed), without its news
		for (int32 s = 0; s < AstraWar::NumSections; ++s)
		{
			S.Dmg.Structure[s] = D.Structure[s] * S.Dmg.StructureMax[s];
			S.Dmg.GuttedT[s] = (D.Gutted & (1 << s)) ? 600.f : -1.f;
			S.Dmg.Burn[s] = 0.f;
			S.Dmg.Breach[s] = 0.f;
			for (int32 f = 0; f < AstraWar::NumFacings; ++f)
			{
				S.Dmg.Plate[s][f] = D.Plates[s * AstraWar::NumFacings + f] * S.Dmg.PlateMax[s][f];
			}
		}
		for (int32 i = 0; i < AstraWar::NumSystems; ++i)
		{
			S.Dmg.Sys[i] = D.Sys[i];
		}
		S.Dmg.Sys[AstraWar::SysReactor] = 0.f;
		for (int32 f = 0; f < AstraWar::NumFacings; ++f)
		{
			S.Dmg.Sector[f] = 0.f;
		}
		S.Dmg.Buffer = 0.f;
		S.Dmg.bBreakingUp = false;
		S.bDisabled = true;
		S.DeathHow = EAstraFate::Disabled;
		S.Mode = EAstraShipMode::Idle;
		S.bFleeing = false;
		S.TargetId = -1;
		S.OrderTarget = -1;
		S.bShieldsUp = false;
		S.Missiles = D.Missiles;
		S.Torpedoes = D.Torpedoes;
		Owner->SyncTotals(S);
	}
	else
	{
		// a dead station or a hulk a beat made: no power, no weapons, tumbling (the war's own state of such a thing: StartBeat's investigate)
		S.bDerelict = true;
		S.Missiles = 0;
		S.bShieldsUp = false;
		S.Mode = EAstraShipMode::Idle;
		S.Hull = S.HullMax * D.HullFrac;
	}
	FFoundHulk Hk;
	Hk.PlotId = S.Id;
	Hk.Name = D.Name;
	Hk.Contact = Contact;
	Hk.LeftAt = D.T0;
	Hk.RestoredAt = Now;
	Hk.bTold = D.bToldBack;
	FoundHulks.Add(Hk);
	return S.Id;
}

void UAstraSpaceLife::RestoreDerelicts(double Now)
{
	TArray<FDerelict> Hulks;
	Derelicts.Take(SystemKey, Hulks);
	for (const FDerelict& D : Hulks)
	{
		MakeDerelict(D, Now);
	}
	if (Hulks.Num())
	{
		UE_LOG(LogASTRA, Log, TEXT("[Space] %s: %d hulk%s left behind found again (the first: %s, left %s ago)"), *SystemName, Hulks.Num(), Hulks.Num() == 1 ? TEXT("") : TEXT("s"), *Hulks[0].Name, *FWrecks::Span(Now - Hulks[0].T0));
	}
}

void UAstraSpaceLife::TickDerelicts(double Now, float SimDt)
{
	if (FoundHulks.Num() == 0 || !Owner || Owner->Ships.Num() == 0)
	{
		return;
	}
	if ((DerelictT -= SimDt) > 0.f)
	{
		return;
	}
	DerelictT = 0.5f;
	const FVector Me = Owner->Ships[0].Pos;
	for (int32 i = FoundHulks.Num() - 1; i >= 0; --i)
	{
		FFoundHulk& Hk = FoundHulks[i];
		const FAstraBattleShip* S = Owner->FindById(Hk.PlotId);
		if (!S || !S->bAlive)
		{
			FoundHulks.RemoveAt(i);                                                              // (destroyed, or gone: she is the war's again)
			continue;
		}
		if (Hk.bTold || S->Track < 2 || FVector::Dist(S->Pos, Me) > 90.0 * DrKm)
		{
			continue;
		}
		Hk.bTold = true;
		AstraSpace::FEvent E;
		E.Kind = AstraSpace::EEventKind::Derelict;
		E.bReport = !Owner->bEngagementActive;
		E.At = S->Pos;
		E.Text = FString::Printf(TEXT("sensors: found again — %s (%s), the hulk we left here %s ago: no power, no transponder, %s at %.0f m/s, tumbling at %.1f deg/s; bearing %03.0f, mark %+.0f, %.0f km"),
		                         *Hk.Name, *S->ContactId, *FWrecks::Span(Now - Hk.LeftAt), S->Vel.Size() < 3.0 ? TEXT("at rest") : TEXT("drifting"), S->Vel.Size(), S->SpinDeg, Owner->BearingTo(S->Pos), Owner->MarkTo(S->Pos),
		                         FVector::Dist(S->Pos, Me) / DrKm);
		Events.Add(E);
	}
}

// ------------------------------------------------------------------------------------------------------------------ the console and the bench
FString UAstraSpaceLife::DerelictList() const
{
	const double Now = WreckClock();
	FString Out = FString::Printf(TEXT("hulks left behind: %d recorded (braking %.0f s)"), Derelicts.All().Num(), FDerelicts::BrakeS());
	for (const FDerelict& D : Derelicts.All())
	{
		const FVector At = Sky.ToSystem(FDerelicts::PosAt(D, Now));
		Out += FString::Printf(TEXT("\n  #%d %-12s %-22s %s%s left %s ago, %.1f km from the Aquila, %.0f m/s now; structure %.0f/%.0f/%.0f%%, %d aboard (%d dead)"), D.Id, *D.System, *D.Name, D.bModel ? TEXT("warship") : TEXT("hulk"),
		                       D.bToldBack ? TEXT(", told") : TEXT(""), *FWrecks::Span(Now - D.T0), Owner && Owner->Ships.Num() ? FVector::Dist(At, Owner->Ships[0].Pos) / DrKm : -1.0, FDerelicts::VelAt(D, Now).Size(),
		                       D.Structure[0] * 100.f, D.Structure[1] * 100.f, D.Structure[2] * 100.f, D.Aboard.Alive, D.Aboard.Killed);
	}
	for (const FFoundHulk& Hk : FoundHulks)
	{
		const FAstraBattleShip* S = Owner ? Owner->FindById(Hk.PlotId) : nullptr;
		Out += FString::Printf(TEXT("\n  in the plot: %s (%s), left %s ago%s%s"), *Hk.Name, *Hk.Contact, *FWrecks::Span(Now - Hk.LeftAt), Hk.bTold ? TEXT(", the crew told") : TEXT(", not yet found"), S ? TEXT("") : TEXT(" (gone)"));
	}
	return Out;
}

void UAstraSpaceLife::DebugDerelictMark()
{
	HulkMarks.Reset();
	if (!bLaidOut || !Owner)
	{
		return;
	}
	const double Now = WreckClock();
	for (const FAstraBattleShip& S : Owner->Ships)
	{
		if (!S.bAlive || S.bPlayer || S.bCraft || S.bFixture || S.bWreck || S.bGhost || !(S.bDisabled || S.bDerelict))
		{
			continue;
		}
		FHulkMark M;
		M.Name = S.Name;
		M.Contact = S.ContactId;
		M.Gate = Sky.FromSystem(S.Pos);
		M.GateVel = Sky.DirFromSystem(S.Vel);
		for (int32 s = 0; s < 3; ++s)
		{
			M.Structure[s] = S.Dmg.bModel && S.Dmg.StructureMax[s] > 0.f ? S.Dmg.Structure[s] / S.Dmg.StructureMax[s] : 1.f;
		}
		M.bDisabled = S.bDisabled;
		M.bModel = S.Dmg.bModel;
		M.Side = S.Side == EAstraSide::Astra ? 0 : (S.Side == EAstraSide::Mandate ? 1 : 2);
		M.At = Now;
		HulkMarks.Add(M);
	}
	UE_LOG(LogASTRA, Display, TEXT("[Space] derelicts noted: %d hulks in the plot"), HulkMarks.Num());
}

bool UAstraSpaceLife::DebugDerelictTest(FString& OutDetail)
{
	if (!bLaidOut || !Owner || Owner->Ships.Num() == 0)
	{
		OutDetail = TEXT("no living space laid out here");
		return false;
	}
	int32 Checked = 0, Failed = 0;
	FString Lines;
	const auto Expect = [&](bool bOk, const FString& What)
	{
		++Checked;
		if (!bOk)
		{
			++Failed;
			if (Failed <= 6)
			{
				Lines += FString::Printf(TEXT("FAIL %s; "), *What);
			}
		}
	};
	const double Now = WreckClock();
	Expect(HulkMarks.Num() > 0, TEXT("no hulk was noted before (astra.space.derelicts.mark)"));
	double Worst = 0.0;
	int32 Back = 0;
	for (const FHulkMark& M : HulkMarks)
	{
		const FAstraBattleShip* S = nullptr;
		for (const FAstraBattleShip& X : Owner->Ships)
		{
			if (X.bAlive && X.Name == M.Name && (X.bDisabled || X.bDerelict))
			{
				S = &X;
				break;
			}
		}
		Expect(S != nullptr, FString::Printf(TEXT("%s was left behind and is not in the plot"), *M.Name));
		if (!S)
		{
			continue;
		}
		++Back;
		const FFoundHulk* Fh = FoundHulks.FindByPredicate([S](const FFoundHulk& X) { return X.PlotId == S->Id; });
		Expect(Fh != nullptr, FString::Printf(TEXT("%s is in the plot but not as a hulk found again"), *M.Name));
		// where she should be: the war's drift from the mark until the Aquila left, then the braking of the record (the plot has carried her on from where she was made again, by the war's own rules: a few metres of curve)
		const double LeftAt = Fh ? Fh->LeftAt : M.At;
		const double Tr = Fh ? Fh->RestoredAt : Now;                                         // (from the moment she was made again the war's own rules carry her: her velocity then, held)
		const double B = FDerelicts::BrakeS();
		const double RunR = B > 0.01 ? B * (1.0 - FMath::Exp(-(Tr - LeftAt) / B)) : (Tr - LeftAt);
		const FVector VelR = M.GateVel * (B > 0.01 ? FMath::Exp(-(Tr - LeftAt) / B) : 1.0);
		const FVector Expected = M.Gate + M.GateVel * (LeftAt - M.At) + M.GateVel * RunR + VelR * (Now - Tr);
		const double Err = FVector::Dist(Sky.FromSystem(S->Pos), Expected);
		Worst = FMath::Max(Worst, Err);
		Expect(Err < 40.0, FString::Printf(TEXT("%s is %.0f m from where the arithmetic puts her"), *M.Name, Err));
		Expect(S->bDisabled == M.bDisabled && S->Dmg.bModel == M.bModel && S->Side == (M.Side == 0 ? EAstraSide::Astra : (M.Side == 1 ? EAstraSide::Mandate : EAstraSide::Neutral)), FString::Printf(TEXT("%s came back as another kind of ship"), *M.Name));
		for (int32 s = 0; s < 3 && S->Dmg.bModel; ++s)
		{
			const float Frac = S->Dmg.StructureMax[s] > 0.f ? S->Dmg.Structure[s] / S->Dmg.StructureMax[s] : 1.f;
			Expect(FMath::Abs(Frac - M.Structure[s]) < 0.02f, FString::Printf(TEXT("%s's section %d is %.0f%% (it was %.0f%% when she was left)"), *M.Name, s, Frac * 100.f, M.Structure[s] * 100.f));
		}
		Expect(!S->bWreck && !S->bFixture && !S->bPlayer, FString::Printf(TEXT("%s came back as a place or a wreck"), *M.Name));
		if (S->bDisabled)
		{
			Expect(S->Mode == EAstraShipMode::Idle && !S->bShieldsUp && S->Shield <= 0.01f && S->DeathHow == EAstraFate::Disabled, FString::Printf(TEXT("%s is not dark and dead in the water"), *M.Name));
		}
	}
	OutDetail = FString::Printf(TEXT("%d checks: %d of %d hulks noted are back in the plot, the farthest %.0f m from the arithmetic%s"), Checked, Back, HulkMarks.Num(), Worst, Failed ? *(FString(TEXT("; ")) + Lines) : TEXT(""));
	return Failed == 0 && Checked > 0;
}

namespace
{
	UAstraSpaceLife* DrSpaceOf(UWorld* World)
	{
		UAstraBattleSubsystem* B = World ? World->GetSubsystem<UAstraBattleSubsystem>() : nullptr;
		return B ? B->GetSpace() : nullptr;
	}

	FAutoConsoleCommandWithWorld CmdSpaceDerelicts(TEXT("astra.space.derelicts"), TEXT("The hulks left behind: what is recorded of each, and the ones in the plot that were made again from a record"),
		FConsoleCommandWithWorldDelegate::CreateLambda([](UWorld* W)
		{
			UAstraSpaceLife* S = DrSpaceOf(W);
			if (!S) { UE_LOG(LogASTRA, Display, TEXT("[Space] none in this world")); return; }
			UE_LOG(LogASTRA, Display, TEXT("[Space] %s"), *S->DerelictList());
		}));

	FAutoConsoleCommandWithWorld CmdSpaceDerelictMark(TEXT("astra.space.derelicts.mark"), TEXT("TESTING: note the hulks of the plot (where they are, how hurt), to be found again after the Aquila has been away (astra.space.derelicts.test)"),
		FConsoleCommandWithWorldDelegate::CreateLambda([](UWorld* W) { if (UAstraSpaceLife* S = DrSpaceOf(W)) { S->DebugDerelictMark(); } }));

	FAutoConsoleCommandWithWorld CmdSpaceDerelictTest(TEXT("astra.space.derelicts.test"), TEXT("TESTING: the hulks noted (astra.space.derelicts.mark) are in the plot again, where the arithmetic puts them, as hurt as they were"),
		FConsoleCommandWithWorldDelegate::CreateLambda([](UWorld* W)
		{
			UAstraSpaceLife* S = DrSpaceOf(W);
			if (!S) { UE_LOG(LogASTRA, Display, TEXT("[Space] none in this world")); return; }
			FString Detail;
			const bool bOk = S->DebugDerelictTest(Detail);
			UE_LOG(LogASTRA, Display, TEXT("[Space] derelicts: %s %s"), *Detail, bOk ? TEXT("DERELICTS_OK") : TEXT("DERELICTS_FAILED"));
		}));
}
