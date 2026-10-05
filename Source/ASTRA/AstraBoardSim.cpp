// ASTRA — ABBORDAGGI: the fight inside a ship: the men, their senses, their guns (the squad drill is in AstraBoardAI.cpp). See AstraBoardSim.h.

#include "AstraBoardSim.h"

using namespace AstraBoard;

namespace
{
	constexpr float StepS = 0.1f;
	constexpr float DoorOpenCm = 260.f;
	constexpr float SeeConeDeg = 105.f;          // beyond a few metres a man sees what is in front of him
	constexpr float CloseSenseCm = 700.f;        // within this he knows what is round him
	constexpr float ForgetS = 9.f;
	constexpr double TimeLimitS = 1500.0;
	constexpr double PreLandingLimitS = 900.0;     // a boarding whose craft have not touched yet (they are still flying, or hold off a shield) is given this much longer

	const TCHAR* MandateFirst[] = {TEXT("Ilya"), TEXT("Rustam"), TEXT("Nadezhda"), TEXT("Imre"), TEXT("Katarina"), TEXT("Daro"), TEXT("Anselm"), TEXT("Marek"), TEXT("Isolde"),
	                               TEXT("Corvin"), TEXT("Tamsin"), TEXT("Bram"), TEXT("Odalys"), TEXT("Jurek"), TEXT("Vesna"), TEXT("Lazar"), TEXT("Mirela"), TEXT("Casimir"),
	                               TEXT("Yevgen"), TEXT("Halina"), TEXT("Orsolya"), TEXT("Teodor"), TEXT("Sibylle"), TEXT("Radomir"), TEXT("Ilse"), TEXT("Anatol"), TEXT("Dagny"), TEXT("Emeric")};
	const TCHAR* MandateLast[] = {TEXT("Vael"), TEXT("Korsak"), TEXT("Thane"), TEXT("Dremmer"), TEXT("Ashgrove"), TEXT("Pyrelli"), TEXT("Hollow"), TEXT("Ostrava"), TEXT("Brandt-Ketch"),
	                              TEXT("Nemetsky"), TEXT("Rook"), TEXT("Sable"), TEXT("Volk"), TEXT("Marrow"), TEXT("Kessen"), TEXT("Duvall"), TEXT("Strand"), TEXT("Orlic"), TEXT("Pellam"),
	                              TEXT("Crowe"), TEXT("Ashby"), TEXT("Lindorm"), TEXT("Kharsa"), TEXT("Verrin"), TEXT("Mourne"), TEXT("Tavish"), TEXT("Ketterly"), TEXT("Osgood")};

	float Yaw2D(const FVector& D) { return FMath::RadiansToDegrees(FMath::Atan2(D.Y, D.X)); }
	FVector YawVec(float Deg) { const float R = FMath::DegreesToRadians(Deg); return FVector(FMath::Cos(R), FMath::Sin(R), 0.f); }
	float AngleDiff(float A, float B) { return FMath::UnwindDegrees(A - B); }

	/** Distance from a point to a segment in the horizontal plane (cm). */
	double SegDist2D(const FVector& P, const FVector& A, const FVector& B)
	{
		const FVector2D PA(P.X - A.X, P.Y - A.Y), BA(B.X - A.X, B.Y - A.Y);
		const double L2 = BA.SizeSquared();
		const double T = L2 > 1.0 ? FMath::Clamp(FVector2D::DotProduct(PA, BA) / L2, 0.0, 1.0) : 0.0;
		return (PA - BA * T).Size();
	}
}

const TCHAR* AstraBoard::TaskName(ETask T)
{
	switch (T)
	{
	case ETask::Advance: return TEXT("advance");
	case ETask::Hold: return TEXT("hold");
	case ETask::Assault: return TEXT("assault");
	case ETask::FallBack: return TEXT("fall back");
	case ETask::Follow: return TEXT("with the Captain");
	case ETask::Rescue: return TEXT("recover the Captain");
	case ETask::Withdraw: return TEXT("withdraw");
	case ETask::Sweep: return TEXT("sweep");
	case ETask::Breach: return TEXT("breach");
	case ETask::Take: return TEXT("take");
	case ETask::Ambush: return TEXT("ambush");
	case ETask::Escort: return TEXT("escort the Captain");
	default: return TEXT("respond");
	}
}

const TCHAR* AstraBoard::ActName(EAct A)
{
	switch (A)
	{
	case EAct::Move: return TEXT("moving");
	case EAct::Cover: return TEXT("in cover");
	case EAct::Peek: return TEXT("firing");
	case EAct::Reload: return TEXT("reloading");
	case EAct::Down: return TEXT("down");
	case EAct::Dead: return TEXT("dead");
	case EAct::Gone: return TEXT("gone");
	case EAct::Waiting: return TEXT("coming in");
	default: return TEXT("standing");
	}
}

// ================================================================================================================== set up

void FAstraBoardSim::Init(TSharedRef<const FAstraBoardMap> InMap, int32 Seed)
{
	Map = InMap;
	Rng.Initialize(Seed);
	People.Reset();
	Teams.Reset();
	Events.Reset();
	DeadAboard.Reset();
	Pending.Reset();
	OpenNow.Reset();
	Doors.Init(Map->NumDoors());
	CutT.Init(0.f, Map->NumDoors());
	Cmd = FMarineCommand();
	AmbushIdx = INDEX_NONE;
	AmbushAge = -1.0e9;
	AmbPass = FAmbushPass();
	Mis = FMission();
	Stats = FBook();
	Clock = 0.0;
	Acc = 0.0;
	CaptainUnit = INDEX_NONE;
	SensorT = 0.f;
	SensorPicture[0].Reset();
	SensorPicture[1].Reset();
}

int32 FAstraBoardSim::AddSquad(ESide Side, const FString& Name)
{
	FSquad S;
	S.Id = Teams.Num();
	S.Side = Side;
	S.Name = Name;
	return Teams.Add(S);
}

FString FAstraBoardSim::MandateName(int32 N)
{
	const int32 F = (N * 7 + Rng.RandHelper(5)) % UE_ARRAY_COUNT(MandateFirst);
	const int32 L = (N * 11 + Rng.RandHelper(7)) % UE_ARRAY_COUNT(MandateLast);
	return FString::Printf(TEXT("%s %s"), MandateFirst[F], MandateLast[L]);
}

FUnit& FAstraBoardSim::Spawn(ESide Side, ERole Role, const FString& Name, const FVector& Pos, int32 SquadId)
{
	FUnit U;
	U.Id = People.Num();
	U.Side = Side;
	U.Role = Role;
	U.Name = Name;
	U.Squad = SquadId;
	U.Pos = Pos;
	U.Comp = Map->CompAt(Pos, 60.f);
	U.Yaw = Rng.FRandRange(-180.f, 180.f);
	U.Skill = (Role == ERole::Leader ? Tuning.LeaderSkill : (Side == ESide::Aquila ? Tuning.MarineSkill : Tuning.MandateSkill)) + Rng.FRandRange(-0.06f, 0.06f);
	U.Armor = Side == ESide::Aquila ? Tuning.MarineArmor : Tuning.MandateArmor;
	U.Act = EAct::Idle;
	U.Time0 = (float)Clock;
	U.PercT = Rng.FRandRange(0.f, 0.25f);
	People.Add(U);
	FUnit& R = People.Last();
	ArmUnit(R);
	if (Teams.IsValidIndex(SquadId))
	{
		Teams[SquadId].Members.Add(R.Id);
		if (Role == ERole::Leader || Teams[SquadId].Leader == INDEX_NONE)
		{
			Teams[SquadId].Leader = R.Id;
		}
		Teams[SquadId].StartStrength += 1.f;
	}
	++Stats.Spawned[(int32)Side];
	return R;
}

void FAstraBoardSim::ArmUnit(FUnit& U)
{
	FWeapon W;
	if (U.Role == ERole::Heavy)
	{
		W.Id = TEXT("heavy");
		W.Rps = 12.f;
		W.Mag = 90;
		W.ReloadS = 4.6f;
		W.Damage = 14.f;
		W.Suppress = 2.1f;
		W.Burst = 9;
		U.Skill *= 0.9f;
	}
	else
	{
		W.Id = U.Side == ESide::Aquila ? TEXT("ar181") : TEXT("ar727");
		W.Rps = 9.f;
		W.Mag = 30;
		W.ReloadS = 2.2f;
		W.Damage = 17.f;
		W.Burst = 4;
	}
	U.Weapon = W;
	U.Rounds = W.Mag;
	U.Reserve = W.Mag * 4;
}

TArray<int32> FAstraBoardSim::SpawnBoarders(int32 BreachComp, const FVector& BreachPos, int32 ObjectiveComp, int32 Count, float FirstAtS)
{
	return SpawnAttackers(ESide::Mandate, BreachComp, BreachPos, ObjectiveComp, Count, FirstAtS, 5);
}

void FAstraBoardSim::SetMission(ESide Attacker, int32 BreachComp, const FVector& BreachPos, int32 ObjectiveComp, bool bSweep)
{
	Mis.Attacker = Attacker;
	Mis.Breach = BreachComp;
	Mis.BreachPos = BreachPos;
	Mis.Objective = ObjectiveComp;
	Mis.bSweep = bSweep;
}

void FAstraBoardSim::BriefAttackers(int32 SquadId)
{
	if (!Teams.IsValidIndex(SquadId))
	{
		return;
	}
	FSquad& S = Teams[SquadId];
	S.Task = ETask::Advance;
	S.TargetComp = Mis.Objective;
	S.TargetPos = Mis.Objective != INDEX_NONE ? Map->CentreOf(Mis.Objective) : Mis.BreachPos;
	S.Note = TEXT("to the objective");
}

TArray<int32> FAstraBoardSim::SpawnAttackers(ESide Side, int32 BreachComp, const FVector& BreachPos, int32 ObjectiveComp, int32 Count, float FirstAtS, int32 PerSquad)
{
	TArray<int32> Out;
	SetMission(Side, BreachComp, BreachPos, ObjectiveComp, Mis.bSweep);
	if (Count <= 0)
	{
		return Out;
	}
	PerSquad = FMath::Max(2, PerSquad);
	const int32 NumSquads = FMath::Max(1, FMath::DivideAndRoundUp(Count, PerSquad));
	static const TCHAR* MandateSquads[] = {TEXT("Ferry Guard Alpha"), TEXT("Ferry Guard Bravo"), TEXT("Ferry Guard Charlie"), TEXT("Ferry Guard Delta"), TEXT("Ferry Guard Echo"), TEXT("Ferry Guard Foxtrot")};
	static const TCHAR* MarineSquads[] = {TEXT("Boarding Alpha"), TEXT("Boarding Bravo"), TEXT("Boarding Charlie"), TEXT("Boarding Delta"), TEXT("Boarding Echo"), TEXT("Boarding Foxtrot")};
	int32 Made = 0;
	float At = FirstAtS;
	for (int32 s = 0; s < NumSquads && Made < Count; ++s)
	{
		const int32 Sq = AddSquad(Side, Side == ESide::Mandate ? MandateSquads[s % UE_ARRAY_COUNT(MandateSquads)] : MarineSquads[s % UE_ARRAY_COUNT(MarineSquads)]);
		Out.Add(Sq);
		const int32 Here = FMath::Min(PerSquad, Count - Made);
		for (int32 k = 0; k < Here; ++k)
		{
			const ERole Role = k == 0 ? ERole::Leader : (k == Here - 1 && Here >= 4 ? ERole::Heavy : ERole::Rifleman);
			FString Name;
			if (Side == ESide::Mandate)
			{
				Name = (Role == ERole::Leader ? FString(TEXT("Warden ")) : FString(TEXT("Oarsman "))) + MandateName(Made);
			}
			else
			{
				Name = FString::Printf(TEXT("%sMarine %d"), Role == ERole::Leader ? TEXT("Sgt. ") : TEXT(""), Made + 1);
			}
			// they come in a few steps apart from the cut in the wall
			const FVector Spot = Map->Inset(BreachComp, BreachPos + FVector(Rng.FRandRange(-120.f, 120.f), Rng.FRandRange(-120.f, 120.f), 0.f), 60.f);
			FUnit& U = Spawn(Side, Role, Name, Spot, Sq);
			U.Act = EAct::Waiting;
			Pending.Add({U.Id, At});
			At += 0.9f + Rng.FRand() * 0.5f;
			++Made;
		}
		BriefAttackers(Sq);
	}
	return Out;
}

TArray<int32> FAstraBoardSim::LandParty(ESide Side, int32 Party, const TArray<FArrival>& Men, int32 BreachComp, const FVector& BreachPos, float EtaS, int32 PerSquad, const FString& SquadBase)
{
	TArray<int32> Out;
	if (Men.IsEmpty() || !Map->GetComps().IsValidIndex(BreachComp))
	{
		return Out;
	}
	static const TCHAR* Letters[] = {TEXT("Alpha"), TEXT("Bravo"), TEXT("Charlie"), TEXT("Delta"), TEXT("Echo"), TEXT("Foxtrot"), TEXT("Golf"), TEXT("Hotel"), TEXT("India"), TEXT("Juliet")};
	const FString Base = SquadBase.IsEmpty() ? (Side == ESide::Mandate ? FString(TEXT("Ferry Guard")) : FString(TEXT("Boarding"))) : SquadBase;
	PerSquad = FMath::Max(2, PerSquad);
	int32 Lettered = 0;
	for (const FSquad& S : Teams)
	{
		Lettered += (S.Side == Side && S.Name.StartsWith(Base + TEXT(" "))) ? 1 : 0;      // the letters go on from the party before
	}
	const int32 Count = Men.Num();
	const int32 NumSquads = FMath::DivideAndRoundUp(Count, PerSquad);
	int32 Made = 0;
	float At = (float)Clock + FMath::Max(0.f, EtaS);
	for (int32 s = 0; s < NumSquads && Made < Count; ++s)
	{
		const int32 Sq = AddSquad(Side, FString::Printf(TEXT("%s %s"), *Base, Lettered < UE_ARRAY_COUNT(Letters) ? Letters[Lettered] : *FString::FromInt(Lettered + 1)));
		++Lettered;
		Out.Add(Sq);
		Teams[Sq].BreachComp = BreachComp;
		Teams[Sq].BreachPos = BreachPos;
		const int32 Here = FMath::Min(PerSquad, Count - Made);
		for (int32 k = 0; k < Here; ++k)
		{
			const FArrival& A = Men[Made];
			const ERole Role = k == 0 ? ERole::Leader : (k == Here - 1 && Here >= 4 ? ERole::Heavy : ERole::Rifleman);
			FString Name = A.Name;
			if (Name.IsEmpty())
			{
				Name = Side == ESide::Mandate ? (Role == ERole::Leader ? FString(TEXT("Warden ")) : FString(TEXT("Oarsman "))) + MandateName(Made + Party * 13)
				                              : FString::Printf(TEXT("%sMarine %d"), Role == ERole::Leader ? TEXT("Sgt. ") : TEXT(""), Made + 1 + Party * 20);
			}
			const FVector Spot = Map->Inset(BreachComp, BreachPos + FVector(Rng.FRandRange(-120.f, 120.f), Rng.FRandRange(-120.f, 120.f), 0.f), 60.f);
			FUnit& U = Spawn(Side, Role, Name, Spot, Sq);
			U.Roster = A.Roster;
			U.Party = Party;
			if (A.Skill > 0.f)
			{
				U.Skill = A.Skill;
			}
			U.Act = EAct::Waiting;
			Pending.Add({U.Id, At});
			At += 0.9f + Rng.FRand() * 0.5f;
			++Made;
		}
		BriefAttackers(Sq);
	}
	return Out;
}

void FAstraBoardSim::ReleaseParty(int32 Party, float DelayS)
{
	float At = (float)Clock + FMath::Max(0.f, DelayS);
	for (FPending& P : Pending)
	{
		if (People.IsValidIndex(P.Unit) && People[P.Unit].Party == Party)
		{
			P.At = At;
			At += 0.9f + Rng.FRand() * 0.5f;
		}
	}
}

int32 FAstraBoardSim::LoseParty(int32 Party, const FString& Cause)
{
	int32 N = 0;
	for (int32 i = Pending.Num() - 1; i >= 0; --i)
	{
		FUnit& U = People[Pending[i].Unit];
		if (U.Party != Party || U.Act != EAct::Waiting)
		{
			continue;
		}
		U.Act = EAct::Dead;
		U.Hp = 0.f;
		U.FellTo = Cause;
		++Stats.Killed[(int32)U.Side];
		if (Teams.IsValidIndex(U.Squad))
		{
			++Teams[U.Squad].Lost;
		}
		Pending.RemoveAt(i);
		++N;
	}
	return N;
}

int32 FAstraBoardSim::RecallParty(int32 Party)
{
	int32 N = 0;
	for (int32 i = Pending.Num() - 1; i >= 0; --i)
	{
		FUnit& U = People[Pending[i].Unit];
		if (U.Party != Party || U.Act != EAct::Waiting)
		{
			continue;
		}
		U.Act = EAct::Gone;
		Stats.Spawned[(int32)U.Side] = FMath::Max(0, Stats.Spawned[(int32)U.Side] - 1);       // never came aboard: not a man of this fight
		if (Teams.IsValidIndex(U.Squad))
		{
			Teams[U.Squad].StartStrength = FMath::Max(0.f, Teams[U.Squad].StartStrength - 1.f);
		}
		Pending.RemoveAt(i);
		++N;
	}
	return N;
}

int32 FAstraBoardSim::PartyWaiting(int32 Party) const
{
	int32 N = 0;
	for (const FPending& P : Pending)
	{
		N += (People.IsValidIndex(P.Unit) && People[P.Unit].Party == Party) ? 1 : 0;
	}
	return N;
}
int32 FAstraBoardSim::AddMarine(const FString& Name, int32 Roster, const FVector& Pos, bool bLeader, int32 SquadId, float Skill)
{
	FUnit& U = Spawn(ESide::Aquila, bLeader ? ERole::Leader : ERole::Rifleman, Name, Pos, SquadId);
	U.Roster = Roster;
	if (Skill > 0.f)
	{
		U.Skill = Skill;
	}
	return U.Id;
}

int32 FAstraBoardSim::AddUnit(ESide Side, ERole Role, const FString& Name, const FVector& Pos, int32 SquadId)
{
	return Spawn(Side, Role, Name, Pos, SquadId).Id;
}

int32 FAstraBoardSim::AddWounded(ESide Side, const FString& Name, const FVector& Pos)
{
	FUnit& U = Spawn(Side, ERole::Rifleman, Name, Pos, INDEX_NONE);
	U.Act = EAct::Down;
	U.Hp = 15.f;
	U.Bleed = 1800.f;                                                // his own medics have him: he does not die within the fight
	U.FellTo = TEXT("the war");
	U.Rounds = 0;
	U.Path.Reset();
	++Stats.Down[(int32)Side];
	return U.Id;
}

void FAstraBoardSim::DelayUnit(int32 UnitId, float Seconds)
{
	if (!People.IsValidIndex(UnitId))
	{
		return;
	}
	People[UnitId].Act = EAct::Waiting;
	Pending.Add({UnitId, (float)(Clock + Seconds)});
}

int32 FAstraBoardSim::FindSquad(const FString& Name) const
{
	for (const FSquad& S : Teams)
	{
		if (S.Name.Equals(Name, ESearchCase::IgnoreCase))
		{
			return S.Id;
		}
	}
	return INDEX_NONE;
}

int32 FAstraBoardSim::AddCaptain(const FVector& Pos)
{
	FUnit& U = Spawn(ESide::Aquila, ERole::Captain, TEXT("the Captain"), Pos, INDEX_NONE);
	U.bExternal = true;
	U.Armor = 1.f;
	CaptainUnit = U.Id;
	--Stats.Spawned[0];
	return U.Id;
}

void FAstraBoardSim::SetCaptain(const FVector& Pos, float Yaw, bool bLow, float Speed, bool bDown, const FVector& EyeRel, bool bProne)
{
	if (!People.IsValidIndex(CaptainUnit))
	{
		return;
	}
	FUnit& U = People[CaptainUnit];
	U.Pos = Pos;
	U.Yaw = Yaw;
	U.bLow = bLow || bProne;
	U.bProne = bProne;
	// his eye is where his camera is; a bench's Captain with no pawn has the posture's
	U.EyeRel = EyeRel.Z > 1.0 ? EyeRel : FVector(0.0, 0.0, bProne ? 45.0 : (bLow ? 105.0 : 152.0));
	U.Speed = Speed;
	U.Comp = Map->CompAt(Pos, 60.f);
	if (U.Act != EAct::Gone && U.Act != EAct::Dead)
	{
		U.Act = bDown ? EAct::Down : EAct::Idle;
		bCaptainRescueTold &= bDown;               // up again: the next fall is told afresh
	}
}

void FAstraBoardSim::SealDoor(int32 Door, bool bSealed)
{
	if (Doors.Sealed.IsValidIndex(Door))
	{
		Doors.Sealed[Door] = bSealed;
		Doors.ClosedBy[Door] = -1;                                // (a lockdown or a lifting of it, not a squad's door)
	}
}

// ================================================================================================================== stepping

void FAstraBoardSim::Tick(float Dt)
{
	Acc += Dt;
	int32 N = 0;
	while (Acc >= StepS && N < 30)
	{
		Step(StepS);
		Acc -= StepS;
		++N;
	}
	if (N == 30)
	{
		Acc = 0.0;
	}
}

void FAstraBoardSim::Emit(EEvent Type, int32 Unit, int32 Target, const FVector& Start, const FVector& End, float Dmg, bool bHit, const FString& Text)
{
	FBoardEvent E;
	E.Type = Type;
	E.T = (float)Clock;
	E.Unit = Unit;
	E.Target = Target;
	E.Start = Start;
	E.End = End;
	E.Dmg = Dmg;
	E.bHit = bHit;
	E.Text = Text;
	Events.Add(E);
	if (Events.Num() > 4000)
	{
		Events.RemoveAt(0, 1000);
	}
}

void FAstraBoardSim::Step(float Dt)
{
	Clock += Dt;
	// the men who are still coming in
	for (int32 i = Pending.Num() - 1; i >= 0; --i)
	{
		if (Clock >= Pending[i].At)
		{
			FUnit& U = People[Pending[i].Unit];
			U.Act = EAct::Idle;
			U.Pos = Map->Inset(U.Comp, U.Pos, 50.f);
			if (Mis.StartedS < 0.0 && U.Side == Mis.Attacker)
			{
				Mis.StartedS = Clock;
			}
			Emit(EEvent::Spawn, U.Id, INDEX_NONE, U.Pos, U.Pos, 0.f, false, U.Name);
			Pending.RemoveAt(i);
		}
	}
	double T0 = FPlatformTime::Seconds();
	const auto Lap = [this, &T0](int32 Part)
	{
		const double T1 = FPlatformTime::Seconds();
		const double Ms = (T1 - T0) * 1000.0;
		Stats.Ms[Part] += Ms;
		Stats.MsWorst[Part] = FMath::Max(Stats.MsWorst[Part], Ms);
		T0 = T1;
	};
	StepDoors();
	StepSensors(Dt);
	StepMarineCommand(Dt);
	StepAmbush();
	StepEvacuation(Dt);
	for (FUnit& U : People)
	{
		if (!U.bExternal && (U.Act != EAct::Dead && U.Act != EAct::Gone && U.Act != EAct::Waiting))
		{
			if (U.Act == EAct::Down)
			{
				if (U.CarriedBy == INDEX_NONE)
				{
					U.Bleed -= Dt;                                   // (a man on a bearer's shoulders has help: he does not bleed)
					if (U.Bleed <= 0.f)
					{
						Kill(U, INDEX_NONE, TEXT("bled out"));
					}
				}
				continue;
			}
			U.PercT += Dt;
			if (U.PercT >= 0.25f)
			{
				const float Since = U.PercT;
				U.PercT = 0.f;
				Perceive(U, Since);
			}
		}
	}
	Lap(0);
	for (FSquad& S : Teams)
	{
		StepSquad(S, Dt);
	}
	Lap(1);
	for (FUnit& U : People)
	{
		if (!U.bExternal && U.Act != EAct::Dead && U.Act != EAct::Gone && U.Act != EAct::Waiting && U.Act != EAct::Down)
		{
			StepUnit(U, Dt);
		}
	}
	StepMission(Dt);
	Lap(2);
}

void FAstraBoardSim::StepDoors()
{
	for (const int32 D : OpenNow)
	{
		if (Doors.Open.IsValidIndex(D))
		{
			Doors.Open[D] = false;
		}
	}
	OpenNow.Reset();
	TArray<int32, TInlineAllocator<8>> Cutting, Overriding, Reopening;
	for (const FUnit& U : People)
	{
		if (U.Act == EAct::Dead || U.Act == EAct::Gone || U.Act == EAct::Waiting || !Map->GetComps().IsValidIndex(U.Comp))
		{
			continue;
		}
		const FBoardComp& C = Map->GetComps()[U.Comp];
		for (const int32 Pi : C.Portals)
		{
			const FBoardPortal& P = Map->GetPortals()[Pi];
			if (!P.bDoor() || P.Door == U.HoldDoor)
			{
				continue;                                    // (a man stacked at a door holds it shut: it is not opened for him, nor cut, until his squad goes in)
			}
			const double D = FVector::Dist2D(U.Pos, P.Pos);
			if (Doors.IsSealed(P.Door))
			{
				const int32 By = Doors.ClosedBySide(P.Door);
				if (By >= 0)
				{
					// a door a squad shut behind it: the ones who are waiting to go through work at it (the side that shut it opens it again from its console, the ship's own people override it, the attackers cut it)
					if (U.WaitDoor == P.Door && U.Able() && D < 260.0)
					{
						(By == (int32)U.Side ? Reopening : IsAttacker(U.Side) ? Cutting : Overriding).AddUnique(P.Door);
					}
				}
				else if (IsAttacker(U.Side) && U.Able() && D < 260.0 && !Cutting.Contains(P.Door))
				{
					Cutting.Add(P.Door);                         // (the attackers at a sealed bulkhead cut through it)
				}
			}
			else if (D <= DoorOpenCm && !Doors.Open[P.Door])
			{
				Doors.Open[P.Door] = true;
				OpenNow.Add(P.Door);
			}
		}
	}
	for (int32 d = 0; d < CutT.Num(); ++d)
	{
		const bool bCut = Cutting.Contains(d), bOver = !bCut && Overriding.Contains(d), bAgain = !bCut && !bOver && Reopening.Contains(d);
		if (bCut || bOver || bAgain)
		{
			CutT[d] += StepS * (bCut ? 1.f : bOver ? Tuning.CutS / FMath::Max(1.f, Tuning.OverrideS) : Tuning.CutS / FMath::Max(1.f, Tuning.SealS));
			if (CutT[d] >= Tuning.CutS)
			{
				CutT[d] = 0.f;
				Doors.Sealed[d] = false;
				Doors.ClosedBy[d] = -1;
				const int32 Pi = Map->PortalOfDoor(d);
				const FString At = Pi != INDEX_NONE ? Map->Describe(Map->GetPortals()[Pi].A) : FString(TEXT("?"));
				Emit(EEvent::Cut, INDEX_NONE, d, Pi != INDEX_NONE ? Map->GetPortals()[Pi].Pos : FVector::ZeroVector, FVector::ZeroVector, 0.f, false,
				     bCut ? FString::Printf(TEXT("%s cut through the bulkhead at %s"), Mis.Attacker == ESide::Mandate ? TEXT("the Mandate") : TEXT("the marines"), *At)
				          : bOver ? FString::Printf(TEXT("%s overrode the bulkhead at %s"), Mis.Attacker == ESide::Mandate ? TEXT("the marines") : TEXT("the Mandate"), *At)
				                  : FString::Printf(TEXT("the bulkhead at %s was opened again"), *At));
			}
		}
		else if (CutT[d] > 0.f)
		{
			CutT[d] = FMath::Max(0.f, CutT[d] - StepS);
		}
	}
}

/** The attackers' wounded go home: a man who is down and not under fire is reached by a free man of his own side (nearest first, never the one man a squad cannot spare), who gets him up and
 *  carries him to the hatch the squad came in by, where the boat's people take him. While he is carried he does not bleed; if his bearer is hit he is put down where it happened. Nobody is called
 *  while an enemy who can see the casualty is near: the fight comes first, and a man who falls in the open of a fight that does not end may bleed out. */
void FAstraBoardSim::StepEvacuation(float Dt)
{
	if (!Tuning.bEvacuate)
	{
		return;
	}
	EvacT += Dt;
	const bool bLook = EvacT >= 0.5f;
	if (bLook)
	{
		EvacT = 0.f;
	}
	for (FUnit& C : People)
	{
		if (C.Act != EAct::Down || C.bExternal || !IsAttacker(C.Side))
		{
			continue;
		}
		if (C.CarriedBy != INDEX_NONE)
		{
			FUnit& B = People[C.CarriedBy];
			if (B.Carrying != C.Id || !B.Able())
			{
				C.CarriedBy = INDEX_NONE;                                // his bearer fell: he is put down where it happened
				C.Bearer = INDEX_NONE;
				C.Pos = B.Pos;
				if (B.Carrying == C.Id)
				{
					B.Carrying = INDEX_NONE;
				}
			}
			continue;
		}
		if (C.Bearer != INDEX_NONE && (!People[C.Bearer].Able() || People[C.Bearer].Carrying != C.Id))
		{
			C.Bearer = INDEX_NONE;                                       // the man called to him is down or has other work: another is called
		}
		if (!bLook || C.Bearer != INDEX_NONE)
		{
			continue;
		}
		bool bHot = false;
		for (const FUnit& E : People)
		{
			if (E.Side != C.Side && E.Able() && FMath::Abs(E.Pos.Z - C.Pos.Z) < 300.f && FVector::Dist(E.Pos, C.Pos) < Tuning.EvacClearCm && Map->Visible(E.Eye(), C.Eye(), &Doors))
			{
				bHot = true;
				break;
			}
		}
		if (bHot)
		{
			continue;
		}
		int32 Best = INDEX_NONE;
		float BestD = Tuning.EvacReachCm;
		for (const FUnit& F : People)
		{
			if (F.Side != C.Side || F.Id == C.Id || F.bExternal || !F.Able() || F.Carrying != INDEX_NONE || F.Act == EAct::Reload || FMath::Abs(F.Pos.Z - C.Pos.Z) > 300.f)
			{
				continue;
			}
			const FSquad* Sq = Teams.IsValidIndex(F.Squad) ? &Teams[F.Squad] : nullptr;
			if (Sq && Sq->Leader == F.Id)
			{
				continue;                                                // (the leader leads)
			}
			if (Sq)
			{
				int32 Free = 0;
				for (const int32 M : Sq->Members)
				{
					Free += (People[M].Able() && People[M].Carrying == INDEX_NONE) ? 1 : 0;
				}
				if (Free < 4)
				{
					continue;                                            // a squad does not give up a man when it would be left with fewer than three
				}
			}
			const float D = (float)FVector::Dist(F.Pos, C.Pos);
			if (D < BestD)
			{
				BestD = D;
				Best = F.Id;
			}
		}
		if (Best != INDEX_NONE)
		{
			FUnit& B = People[Best];
			B.Carrying = C.Id;
			B.CarryT = 0.f;
			B.Path.Reset();
			B.Slot = INDEX_NONE;
			C.Bearer = Best;
		}
	}
}

void FAstraBoardSim::StepCarry(FUnit& B, float Dt)
{
	FUnit& C = People[B.Carrying];
	if (C.Act != EAct::Down || (C.CarriedBy != INDEX_NONE && C.CarriedBy != B.Id))
	{
		B.Carrying = INDEX_NONE;                                         // he bled out, or someone else has him
		B.Path.Reset();
		return;
	}
	if (C.CarriedBy == INDEX_NONE)
	{
		// on his way to him, then down on a knee, then up with him
		if (FVector::Dist(B.Pos, C.Pos) > 110.f)
		{
			if (B.Path.IsEmpty() || FVector::Dist(B.Dest, C.Pos) > 150.f)
			{
				GoTo(B, C.Pos, Tuning.JogCmS, true);
				if (B.Path.IsEmpty())
				{
					B.Carrying = INDEX_NONE;                             // no way to him
					C.Bearer = INDEX_NONE;
					return;
				}
			}
			Move(B, Dt);
			return;
		}
		B.Path.Reset();
		B.Speed = 0.f;
		B.bLow = true;
		B.CarryT += Dt;
		if (B.CarryT >= Tuning.EvacPickupS)
		{
			B.CarryT = 0.f;
			B.bLow = false;
			C.CarriedBy = B.Id;
			C.Bleed += Tuning.EvacBleedBonusS;
		}
		return;
	}
	// on his shoulders: out to the hatch his squad came in by
	const FSquad* Sq = Teams.IsValidIndex(B.Squad) ? &Teams[B.Squad] : nullptr;
	const FVector Out = Sq ? BreachPosOf(*Sq) : Mis.BreachPos;
	const int32 OutComp = Sq ? BreachCompOf(*Sq) : Mis.Breach;
	if (B.Comp == OutComp && FVector::Dist2D(B.Pos, Out) < 320.f)
	{
		const int32 Side = (int32)C.Side;
		C.Act = EAct::Gone;
		C.CarriedBy = INDEX_NONE;
		C.Bearer = INDEX_NONE;
		C.Pos = B.Pos;
		Stats.Down[Side] = FMath::Max(0, Stats.Down[Side] - 1);
		++Stats.Carried[Side];
		Emit(EEvent::Carried, C.Id, B.Id, B.Pos, B.Pos, 0.f, false, B.Name);
		B.Carrying = INDEX_NONE;
		B.Path.Reset();
		B.Speed = 0.f;
		B.Act = EAct::Idle;
		return;
	}
	if (B.Path.IsEmpty() || FVector::Dist(B.Dest, Out) > 200.f)
	{
		GoTo(B, Out, Tuning.EvacCmS, true);
		if (B.Path.IsEmpty())
		{
			C.CarriedBy = INDEX_NONE;                                    // no way out: he is put down here
			C.Bearer = INDEX_NONE;
			B.Carrying = INDEX_NONE;
			return;
		}
	}
	Move(B, Dt);
	C.Pos = B.Pos;
	C.Comp = B.Comp;
}

int32 FAstraBoardSim::CountAble(ESide S) const
{
	int32 N = 0;
	for (const FUnit& U : People)
	{
		N += (U.Side == S && !U.bExternal && U.Able()) ? 1 : 0;
	}
	return N;
}

int32 FAstraBoardSim::CountDown(ESide S) const
{
	int32 N = 0;
	for (const FUnit& U : People)
	{
		N += (U.Side == S && !U.bExternal && U.Act == EAct::Down) ? 1 : 0;
	}
	return N;
}

float FAstraBoardSim::Strength(const FSquad& S) const
{
	int32 Able = 0;
	for (const int32 M : S.Members)
	{
		Able += People[M].Able() ? 1 : 0;
	}
	return S.StartStrength > 0.f ? Able / S.StartStrength : 0.f;
}

// ================================================================================================================== the ship's own eyes

/** The internal sensors of a ship that has power see the corridors and the halls (not the rooms): its people's picture of the boarders, a couple of seconds stale. */
void FAstraBoardSim::StepSensors(float Dt)
{
	SensorT += Dt;
	if (SensorT < 1.0f)
	{
		return;
	}
	SensorT = 0.f;
	if (!Tuning.bShipSensors)
	{
		return;                                                // a dead ship: nobody sees through its walls
	}
	TArray<FSeen>& Pic = SensorPicture[(int32)Defender()];
	for (FSeen& S : Pic)
	{
		S.AgeS += 1.f;
	}
	for (const FUnit& U : People)
	{
		if (!IsAttacker(U.Side) || !U.Able() || !Map->GetComps().IsValidIndex(U.Comp))
		{
			continue;
		}
		const FBoardComp& C = Map->GetComps()[U.Comp];
		if (!C.bCorridor && !C.bHall)
		{
			continue;
		}
		FSeen* Old = Pic.FindByPredicate([&U](const FSeen& S) { return S.Unit == U.Id; });
		if (!Old)
		{
			Old = &Pic.AddDefaulted_GetRef();
			Old->Unit = U.Id;
		}
		Old->Pos = U.Pos;
		Old->AgeS = Tuning.SensorDelayS;
		Old->bVisibleNow = true;
	}
	Pic.RemoveAll([](const FSeen& S) { return S.AgeS > 12.f; });
}

void FAstraBoardSim::Intel(ESide Side, TArray<FSeen>& Out) const
{
	Out.Reset();
	const ESide Enemy = Side == ESide::Aquila ? ESide::Mandate : ESide::Aquila;
	if (Side == Defender() && Tuning.bShipSensors)
	{
		for (const FSeen& S : SensorPicture[(int32)Side])
		{
			if (People.IsValidIndex(S.Unit) && People[S.Unit].Able())
			{
				Out.Add(S);
			}
		}
	}
	for (const FUnit& U : People)
	{
		if (U.Side != Side || !U.Able())
		{
			continue;
		}
		for (const FSeen& S : U.Seen)
		{
			if (People.IsValidIndex(S.Unit) && People[S.Unit].Side == Enemy && People[S.Unit].Able() && !Out.ContainsByPredicate([&S](const FSeen& O) { return O.Unit == S.Unit; }))
			{
				Out.Add(S);
			}
		}
	}
}

// ================================================================================================================== senses

void FAstraBoardSim::Perceive(FUnit& U, float Dt)
{
	// what he knew goes stale
	for (FSeen& S : U.Seen)
	{
		S.AgeS += Dt;
		S.bVisibleNow = false;
	}
	U.Seen.RemoveAll([this](const FSeen& S) { return S.AgeS > ForgetS || !People.IsValidIndex(S.Unit) || !People[S.Unit].Able(); });
	U.Suppression = FMath::Max(0.f, U.Suppression - Tuning.SuppressDecay * Dt);
	const FVector MyEye = U.Eye();
	for (const FUnit& E : People)
	{
		if (E.Side == U.Side || !E.Able() || E.Act == EAct::Waiting)
		{
			continue;
		}
		const float D = (float)FVector::Dist2D(U.Pos, E.Pos);
		if (D > Tuning.RangeMaxCm + 600.f || FMath::Abs(U.Pos.Z - E.Pos.Z) > 300.f)
		{
			continue;
		}
		// in front of him, or close enough to feel
		if (D > CloseSenseCm)
		{
			const float Off = FMath::Abs(AngleDiff(Yaw2D(E.Pos - U.Pos), U.Yaw));
			if (Off > SeeConeDeg)
			{
				continue;
			}
		}
		if (E.bHidden && D > Tuning.HiddenSeeCm)
		{
			continue;                                        // a man in a corner with his fire held is seen only from close
		}
		bool bSee = SightOverride && (E.bExternal || U.bExternal) ? SightOverride(MyEye, E.Eye()) : Map->Visible(MyEye, E.Eye(), &Doors);
		if (!bSee)
		{
			continue;
		}
		if (Teams.IsValidIndex(E.Squad) && Teams[E.Squad].bFireHeld)
		{
			Teams[E.Squad].bSpotted = true;                  // a man of a squad that holds its fire is seen: it is found, and opens fire
		}
		FSeen* S = U.Seen.FindByPredicate([&E](const FSeen& X) { return X.Unit == E.Id; });
		if (!S)
		{
			if (U.Seen.Num() >= 8)
			{
				continue;
			}
			S = &U.Seen.AddDefaulted_GetRef();
			S->Unit = E.Id;
			// the first sight of an enemy who has just come through a door (in a drill), by a man who was not alerted: he is startled
			if (E.EntryT > 0.f && U.AlertT > 8.f)
			{
				U.StartleT = FMath::Max(U.StartleT, Tuning.StartleS);
			}
			U.AlertT = 0.f;
			Emit(EEvent::Contact, U.Id, E.Id, U.Pos, E.Pos);
			if (Stats.FirstContactT < 0.0)
			{
				Stats.FirstContactT = Clock;
			}
			++Stats.Contacts;
		}
		S->Pos = E.Pos;
		S->AgeS = 0.f;
		S->bVisibleNow = true;
		// the Captain's body: his eye is seen through the real level; if his chest is not, what shows of him is a head over cover or an eye round an edge (the game's sight: a console, a pillar)
		S->bCovered = false;
		if (E.bExternal && SightOverride)
		{
			S->bCovered = !SightOverride(MyEye, E.Pos + FVector(0.0, 0.0, E.bProne ? 22.0 : (E.bLow ? 70.0 : 110.0)));
		}
		U.AlertT = 0.f;
	}
}

/** A shot is heard through the open ways: the other side learns where it came from, roughly. */
void FAstraBoardSim::Hear(const FUnit& Shooter)
{
	for (FUnit& E : People)
	{
		if (E.Side == Shooter.Side || !E.Able() || E.bExternal || E.Act == EAct::Waiting)
		{
			continue;
		}
		const float D = (float)FVector::Dist(E.Pos, Shooter.Pos);
		if (D > Tuning.HearCm || FMath::Abs(E.Pos.Z - Shooter.Pos.Z) > 400.f)
		{
			continue;
		}
		E.AlertT = 0.f;                                        // a shot he hears: he is alerted
		FSeen* S = E.Seen.FindByPredicate([&Shooter](const FSeen& X) { return X.Unit == Shooter.Id; });
		if (S && S->bVisibleNow)
		{
			continue;
		}
		// he does not see him, but he knows where the sound came from, within a few metres
		if (!S && E.Seen.Num() < 8)
		{
			S = &E.Seen.AddDefaulted_GetRef();
			S->Unit = Shooter.Id;
		}
		if (S)
		{
			S->Pos = Shooter.Pos + FVector(Rng.FRandRange(-300.f, 300.f), Rng.FRandRange(-300.f, 300.f), 0.f);
			S->AgeS = FMath::Min(S->AgeS, 1.5f);
		}
	}
}

// ================================================================================================================== the unit

void FAstraBoardSim::Face(FUnit& U, const FVector& At, float Dt)
{
	const float Want = Yaw2D(At - U.Pos);
	const float D = AngleDiff(Want, U.Yaw);
	const float Max = 520.f * Dt;
	U.Yaw = FMath::UnwindDegrees(U.Yaw + FMath::Clamp(D, -Max, Max));
}

void FAstraBoardSim::StepUnit(FUnit& U, float Dt)
{
	U.FireT = FMath::Max(0.f, U.FireT - Dt);
	U.AcquireT = FMath::Max(0.f, U.AcquireT - Dt);
	U.CoverT = FMath::Max(0.f, U.CoverT - Dt);
	U.EntryT = FMath::Max(0.f, U.EntryT - Dt);
	U.StartleT = FMath::Max(0.f, U.StartleT - Dt);
	U.AlertT = FMath::Min(999.f, U.AlertT + Dt);
	if (U.Carrying != INDEX_NONE)
	{
		StepCarry(U, Dt);                                            // (called to a casualty, or carrying him out: the squad's drill does not move him, he does not shoot)
		return;
	}
	if (U.Act == EAct::Reload)
	{
		U.ReloadT -= Dt;
		if (U.ReloadT <= 0.f)
		{
			const int32 Take = FMath::Min(U.Weapon.Mag - U.Rounds, U.Reserve);
			U.Rounds += Take;
			U.Reserve -= Take;
			U.Act = EAct::Idle;
			U.bAtPeek = false;
		}
		else
		{
			if (U.Path.Num() && U.PathI < U.Path.Num())
			{
				Move(U, Dt);
			}
			return;
		}
	}
	Fight(U, Dt);
}

bool FAstraBoardSim::ChooseTarget(FUnit& U)
{
	int32 Best = INDEX_NONE;
	float BestCost = 1.0e9f;
	for (const FSeen& S : U.Seen)
	{
		if (!S.bVisibleNow || !People.IsValidIndex(S.Unit) || !People[S.Unit].Able())
		{
			continue;
		}
		const FUnit& E = People[S.Unit];
		const float D = (float)FVector::Dist(U.Pos, E.Pos);
		if (D > U.Weapon.RangeCm)
		{
			continue;
		}
		float Cost = D;
		if (S.Unit == U.Target)
		{
			Cost -= 250.f;                                   // he keeps to the one he is on
		}
		if (E.Role == ERole::Leader)
		{
			Cost -= 120.f;
		}
		if (E.bExternal)
		{
			Cost -= 150.f;                                   // the Captain is what the Mandate came for
		}
		if (Cost < BestCost)
		{
			BestCost = Cost;
			Best = S.Unit;
		}
	}
	if (Best != U.Target)
	{
		U.Target = Best;
		if (Best != INDEX_NONE)
		{
			U.AcquireT = Rng.FRandRange(Tuning.AcquireMinS, Tuning.AcquireMaxS) * (1.f + U.Suppression) * (U.Role == ERole::Leader ? 0.8f : 1.f)
			             * (U.StartleT > 0.f ? Tuning.StartleMul : 1.f) * (U.EntryT > 0.f ? Tuning.EntryMul : 1.f);              // (startled: slow; through a door in a drill: quick)
		}
	}
	return Best != INDEX_NONE;
}

float FAstraBoardSim::HitChance(const FUnit& Shooter, const FUnit& Target, float DistCm) const
{
	float Range;
	if (DistCm <= Tuning.RangeFullCm)
	{
		Range = 1.f;
	}
	else if (DistCm <= Tuning.RangeFarCm)
	{
		Range = FMath::Lerp(1.f, 0.34f, (DistCm - Tuning.RangeFullCm) / (Tuning.RangeFarCm - Tuning.RangeFullCm));
	}
	else if (DistCm <= Tuning.RangeMaxCm)
	{
		Range = FMath::Lerp(0.34f, 0.10f, (DistCm - Tuning.RangeFarCm) / (Tuning.RangeMaxCm - Tuning.RangeFarCm));
	}
	else
	{
		Range = 0.04f;
	}
	float P = Shooter.Skill * Range;
	// a man behind a corner's edge shows little of himself; one who is low shows less; one who runs is hard to lay a gun on
	if (Target.Act == EAct::Peek && Target.Slot != INDEX_NONE)
	{
		P *= Tuning.CoverFactor + 0.2f;
	}
	if (Target.bExternal)
	{
		const FSeen* Seen = Shooter.Seen.FindByPredicate([&Target](const FSeen& S) { return S.Unit == Target.Id; });
		if (Seen && Seen->bCovered)
		{
			P *= Tuning.CoverFactor;                             // all he shows is a head over the cover: a small mark
		}
	}
	if (Target.bProne)
	{
		P *= 0.6f;                                           // lying down: all there is to hit is a back and a head
	}
	else if (Target.bLow)
	{
		P *= 0.8f;
	}
	if (Target.Speed > (Target.bProne ? 130.f : 60.f))       // (a man crawling is not running)
	{
		P *= Tuning.MoveFactor;
	}
	P *= 1.f - 0.45f * Shooter.Suppression;
	if (Shooter.Hp < 45.f)
	{
		P *= 0.8f;
	}
	if (Shooter.Speed > 60.f)
	{
		P *= 0.7f;                                           // firing on the move
	}
	// the infantry orders: a man through a door in a drill is quick and trained to it; a sprung ambush's first volley was laid on its targets; and a man who holds a corner on a door, alerted, finds the one who comes through it in a fatal funnel
	if (Shooter.EntryT > 0.f)
	{
		P *= Tuning.EntryHit;
	}
	if (Teams.IsValidIndex(Shooter.Squad) && Teams[Shooter.Squad].FirstVolleyT > 0.f)
	{
		P *= Tuning.AmbushFirstHit;
	}
	if (Target.EntryT > 0.f && Shooter.Slot != INDEX_NONE && (Shooter.Act == EAct::Cover || Shooter.Act == EAct::Peek) && Shooter.AlertT < 6.f)
	{
		P *= Tuning.FunnelBonus;
	}
	return FMath::Clamp(P, 0.02f, 0.88f);
}

void FAstraBoardSim::Suppress(const FVector& From, const FVector& To, ESide ShooterSide, float Amount, int32 Except)
{
	for (FUnit& E : People)
	{
		if (E.Side == ShooterSide || E.Id == Except || !E.Able() || E.bExternal)
		{
			continue;
		}
		if (FMath::Abs(E.Pos.Z - From.Z) > 300.f)
		{
			continue;
		}
		if (SegDist2D(E.Pos, From, To) < Tuning.SuppressMiss)
		{
			const float Before = E.Suppression;
			E.Suppression = FMath::Min(1.f, E.Suppression + Amount);
			if (Before < 0.6f && E.Suppression >= 0.6f)
			{
				++Stats.Suppressed;
			}
		}
	}
}

void FAstraBoardSim::FireRounds(FUnit& U, float Dt)
{
	if (U.BurstLeft <= 0)
	{
		return;
	}
	U.bHidden = false;                                         // a man who fires is no longer hidden
	U.RoundT -= Dt;
	while (U.RoundT <= 0.f && U.BurstLeft > 0 && U.Rounds > 0)
	{
		if (!People.IsValidIndex(U.Target) || !People[U.Target].Able())
		{
			U.BurstLeft = 0;
			break;
		}
		FUnit& T = People[U.Target];
		const float D = (float)FVector::Dist(U.Pos, T.Pos);
		const float P = HitChance(U, T, D);
		const bool bHit = Rng.FRand() < P;
		const bool bHead = bHit && Rng.FRand() < 0.07f;
		--U.Rounds;
		--U.BurstLeft;
		++Stats.Shots;
		if (U.Side == ESide::Aquila)
		{
			Stats.MarineRoundsFired += 1.f;
		}
		U.RoundT += 1.f / U.Weapon.Rps;
		const FVector Muzzle = U.Pos + FVector(0.f, 0.f, U.bLow ? 90.f : 138.f) + YawVec(U.Yaw) * 60.f;
		FVector End;
		if (bHit)
		{
			End = T.Pos + FVector(Rng.FRandRange(-12.f, 12.f), Rng.FRandRange(-12.f, 12.f), bHead ? (T.bProne ? 40.f : (T.bLow ? 95.f : 160.f)) : (T.bProne ? 22.f : (T.bLow ? 70.f : Rng.FRandRange(85.f, 135.f))));
			++Stats.Hits;
		}
		else
		{
			const FVector Dir = (T.Pos - U.Pos).GetSafeNormal2D();
			const FVector Side(-Dir.Y, Dir.X, 0.f);
			const float Beyond = Rng.FRandRange(100.f, 600.f);
			End = T.Pos + Dir * Beyond + Side * Rng.FRandRange(-90.f, 90.f) + FVector(0.f, 0.f, Rng.FRandRange(40.f, 170.f));
			++Stats.Misses;
		}
		Emit(EEvent::Shot, U.Id, T.Id, Muzzle, End, bHit ? U.Weapon.Damage : 0.f, bHit, FString());
		if (bHit)
		{
			Damage(T, U.Weapon.Damage * Rng.FRandRange(0.8f, 1.25f) * (bHead ? 2.4f : 1.f), bHead, U.Id, End, U.Name);
		}
		Suppress(Muzzle, End, U.Side, Tuning.SuppressPerRound * U.Weapon.Suppress, bHit ? T.Id : INDEX_NONE);
		if (T.Id != INDEX_NONE && !bHit)
		{
			T.Suppression = FMath::Min(1.f, T.Suppression + Tuning.SuppressPerRound * U.Weapon.Suppress * 1.4f);
		}
		if (U.BurstLeft == 0 || (Stats.Shots & 3) == 0)
		{
			Hear(U);
		}
	}
	if (U.BurstLeft <= 0 || U.Rounds <= 0)
	{
		U.BurstLeft = 0;
		U.FireT = Rng.FRandRange(0.12f, 0.4f) * (1.f + U.Suppression);
	}
}

void FAstraBoardSim::Damage(FUnit& T, float Dmg, bool bHead, int32 ByUnit, const FVector& At, const FString& By)
{
	if (T.bExternal)
	{
		// the Captain: the game turns it into his wound (the model's trauma); the hit is counted here
		++Stats.CaptainHits;
		++T.HitsTaken;
		Emit(EEvent::Hit, T.Id, ByUnit, At, At, Dmg, true, By);
		return;
	}
	if (!T.Able())
	{
		return;
	}
	T.AlertT = 0.f;
	if (Teams.IsValidIndex(T.Squad) && Teams[T.Squad].bFireHeld)
	{
		Teams[T.Squad].bSpotted = true;                          // shot at with his fire held: the squad opens fire
	}
	const float Real = Dmg * T.Armor;
	T.Hp -= Real;
	++T.HitsTaken;
	T.Suppression = FMath::Min(1.f, T.Suppression + 0.12f);
	Emit(EEvent::Hit, T.Id, ByUnit, At, At, Real, true, By);
	if (Stats.FirstBloodT < 0.0)
	{
		Stats.FirstBloodT = Clock;
	}
	if (T.Hp > 0.f)
	{
		return;
	}
	// beaten: dead, or down and alive (a wound that keeps him out of the fight and may be the end of him if nobody comes)
	const float Over = FMath::Clamp(-T.Hp / 35.f, 0.f, 1.f);
	const float Lethal = (bHead ? 0.8f : 0.26f + 0.5f * Over) * Tuning.LethalScale[(int32)T.Side];
	if (Rng.FRand() < Lethal)
	{
		Kill(T, ByUnit, By);
	}
	else
	{
		T.Act = EAct::Down;
		T.Bleed = Rng.FRandRange(Tuning.DownBleedMinS, Tuning.DownBleedMaxS);
		T.FellTo = By;
		T.Path.Reset();
		T.Speed = 0.f;
		T.Target = INDEX_NONE;
		T.BurstLeft = 0;
		++Stats.Down[(int32)T.Side];                      // (Down is who is down now: a man who bleeds out moves to Killed)
		if (Teams.IsValidIndex(T.Squad))
		{
			++Teams[T.Squad].Lost;
		}
		if (People.IsValidIndex(ByUnit))
		{
			++People[ByUnit].Kills;
		}
		Emit(EEvent::Down, T.Id, ByUnit, T.Pos, T.Pos, 0.f, false, By);
	}
}

void FAstraBoardSim::Kill(FUnit& U, int32 ByUnit, const FString& By)
{
	if (U.Act == EAct::Dead)
	{
		return;
	}
	const bool bWasDown = U.Act == EAct::Down;
	U.Act = EAct::Dead;
	U.Hp = 0.f;
	U.FellTo = By;
	U.Path.Reset();
	U.Speed = 0.f;
	U.BurstLeft = 0;
	++Stats.Killed[(int32)U.Side];
	if (bWasDown)
	{
		Stats.Down[(int32)U.Side] = FMath::Max(0, Stats.Down[(int32)U.Side] - 1);      // he was counted down: now he is counted dead
	}
	if (!bWasDown && Teams.IsValidIndex(U.Squad))
	{
		++Teams[U.Squad].Lost;
	}
	if (People.IsValidIndex(ByUnit) && !bWasDown)
	{
		++People[ByUnit].Kills;
	}
	// the squad feels it
	if (Teams.IsValidIndex(U.Squad))
	{
		for (const int32 M : Teams[U.Squad].Members)
		{
			People[M].Morale = FMath::Max(0.f, People[M].Morale - 0.1f);
		}
	}
	Emit(EEvent::Died, U.Id, ByUnit, U.Pos, U.Pos, 0.f, false, By);
}

void FAstraBoardSim::HitUnit(int32 UnitId, float Dmg, bool bHead, const FString& By)
{
	if (!People.IsValidIndex(UnitId))
	{
		return;
	}
	FUnit& T = People[UnitId];
	if (T.Side == ESide::Mandate || T.Side == ESide::Aquila)
	{
		Damage(T, Dmg, bHead, CaptainUnit, T.Pos + FVector(0, 0, 120), By.IsEmpty() ? FString(TEXT("the Captain")) : By);
	}
}

void FAstraBoardSim::CaptainFired()
{
	if (People.IsValidIndex(CaptainUnit))
	{
		Hear(People[CaptainUnit]);
	}
}

void FAstraBoardSim::CarryOut(int32 UnitId)
{
	if (People.IsValidIndex(UnitId) && People[UnitId].Act == EAct::Down)
	{
		People[UnitId].Act = EAct::Gone;
		Stats.Down[(int32)People[UnitId].Side] = FMath::Max(0, Stats.Down[(int32)People[UnitId].Side] - 1);
		++Stats.Carried[(int32)People[UnitId].Side];
		++Stats.Rescues;
	}
}

void FAstraBoardSim::LeaveShip(int32 UnitId)
{
	if (!People.IsValidIndex(UnitId))
	{
		return;
	}
	FUnit& U = People[UnitId];
	if (U.Act == EAct::Dead || U.Act == EAct::Gone)
	{
		return;
	}
	if (U.Act == EAct::Down)
	{
		CarryOut(UnitId);
		return;
	}
	if (U.Carrying != INDEX_NONE && People.IsValidIndex(U.Carrying))
	{
		People[U.Carrying].CarriedBy = INDEX_NONE;                   // (the man he was carrying is put down where he stands)
		People[U.Carrying].Bearer = INDEX_NONE;
		People[U.Carrying].Pos = U.Pos;
	}
	U.Carrying = INDEX_NONE;
	if (U.Act == EAct::Waiting)
	{
		for (int32 i = Pending.Num() - 1; i >= 0; --i)
		{
			if (Pending[i].Unit == UnitId)
			{
				Pending.RemoveAt(i);
			}
		}
		Stats.Spawned[(int32)U.Side] = FMath::Max(0, Stats.Spawned[(int32)U.Side] - 1);      // he was not in yet: not a man of this fight
		if (Teams.IsValidIndex(U.Squad))
		{
			Teams[U.Squad].StartStrength = FMath::Max(0.f, Teams[U.Squad].StartStrength - 1.f);
		}
		U.Act = EAct::Gone;
		return;
	}
	U.Act = EAct::Gone;
	U.Path.Reset();
	U.Speed = 0.f;
	++Stats.Exited[(int32)U.Side];
	Emit(EEvent::Exit, U.Id, INDEX_NONE, U.Pos, U.Pos, 0.f, false, U.Name);
}

// ================================================================================================================== fighting

void FAstraBoardSim::Fight(FUnit& U, float Dt)
{
	const bool bSeen = ChooseTarget(U);
	// nothing to shoot at: the squad's drill moves him
	if (!bSeen)
	{
		U.BurstLeft = 0;
		if (U.Path.Num() && U.PathI < U.Path.Num())
		{
			Move(U, Dt);
		}
		else
		{
			U.Speed = 0.f;
			if (U.Slot != INDEX_NONE)
			{
				// at his corner, waiting for the enemy to show; a man who knows the enemy is near (what he has is stale) steps out to look from time to time
				const FBoardSlot& S = Map->GetSlots()[U.Slot];
				bool bSuspect = false;
				for (const FSeen& X : U.Seen)
				{
					bSuspect |= X.AgeS < 12.f && People.IsValidIndex(X.Unit) && People[X.Unit].Able();
				}
				if (bSuspect && Tuning.bCover && U.Suppression < 0.6f && !Held(U))
				{
					U.CycleT -= Dt;
					if (U.bAtPeek)
					{
						U.Act = EAct::Peek;
						if (U.CycleT <= 0.f)
						{
							U.bAtPeek = false;
							U.CycleT = Rng.FRandRange(2.5f, 6.f);
							GoTo(U, S.Pos, Tuning.CoverCmS);
						}
					}
					else if (FVector::Dist2D(U.Pos, S.Pos) > 40.f)
					{
						GoTo(U, S.Pos, Tuning.CoverCmS);
					}
					else
					{
						U.Act = EAct::Cover;
						if (U.CycleT <= 0.f)
						{
							U.bAtPeek = true;
							U.CycleT = Tuning.PeekS * 1.5f;
							GoTo(U, S.Peek, Tuning.CoverCmS);
						}
					}
				}
				else
				{
					const FVector Spot = Held(U) ? S.Peek : S.Pos;           // (an ambush waits at the step-out, ready: nobody sees it from beyond HiddenSeeCm)
					if (FVector::Dist2D(U.Pos, Spot) > 40.f)
					{
						GoTo(U, Spot, Tuning.CoverCmS);
					}
					U.Act = Held(U) ? EAct::Peek : EAct::Cover;
				}
			}
			else
			{
				U.Act = EAct::Idle;
			}
		}
		if (U.Rounds < U.Weapon.Mag / 3 && U.Reserve > 0 && U.Act != EAct::Move)
		{
			U.Act = EAct::Reload;
			U.ReloadT = U.Weapon.ReloadS;
			++Stats.Reloads;
			Emit(EEvent::Reload, U.Id);
		}
		return;
	}
	const FUnit& T = People[U.Target];
	const float Dist = (float)FVector::Dist(U.Pos, T.Pos);
	Face(U, T.Pos, Dt);
	const bool bStand = Teams.IsValidIndex(U.Squad) && Teams[U.Squad].bStand;
	// his fire is held (an ambush): he keeps his corner, faces them and does not shoot until the squad is given the word or is found
	if (Held(U))
	{
		U.BurstLeft = 0;
		U.bAtPeek = false;
		if (U.Path.Num() && U.PathI < U.Path.Num() && U.Speed > 1.f)
		{
			Move(U, Dt);                                          // (still on his way to his corner)
		}
		else
		{
			U.Speed = 0.f;
			U.Act = EAct::Peek;
			if (U.Slot != INDEX_NONE && FVector::Dist2D(U.Pos, Map->GetSlots()[U.Slot].Peek) > 45.f)
			{
				GoTo(U, Map->GetSlots()[U.Slot].Peek, Tuning.CoverCmS);      // (waiting at the step-out)
			}
		}
		return;
	}
	// dry: reload where he is hidden, or get hidden first
	if (U.Rounds <= 0 && U.Reserve > 0)
	{
		const bool bHidden = U.Slot != INDEX_NONE && FVector::Dist2D(U.Pos, Map->GetSlots()[U.Slot].Pos) < 40.f;
		if (bStand || bHidden || Dist > 1800.f || !TakeCover(U, T.Pos))
		{
			U.Act = EAct::Reload;
			U.ReloadT = U.Weapon.ReloadS;
			++Stats.Reloads;
			Emit(EEvent::Reload, U.Id);
			return;
		}
	}
	// frightened men keep their heads down
	const bool bPinned = U.Suppression > 0.75f && U.Role != ERole::Leader;
	if (U.Slot == INDEX_NONE && Dist > 500.f && U.Speed < 1.f && !bStand && !U.bMoveFire)
	{
		// in the open and not too close: find a corner first
		TakeCover(U, T.Pos);
	}
	if (U.Slot != INDEX_NONE)
	{
		const FBoardSlot& S = Map->GetSlots()[U.Slot];
		const float ToSlot = (float)FVector::Dist2D(U.Pos, S.Pos);
		const float ToPeek = (float)FVector::Dist2D(U.Pos, S.Peek);
		if (U.Path.Num() && U.PathI < U.Path.Num() && U.Speed > 1.f)
		{
			Move(U, Dt);                                    // on his way to the corner or the step out
			if (U.BurstLeft > 0) { FireRounds(U, Dt); }
			return;
		}
		if (!U.bAtPeek)
		{
			U.Act = EAct::Cover;
			U.CycleT -= Dt;
			if (ToSlot > 45.f)
			{
				GoTo(U, S.Pos, Tuning.CoverCmS);
				return;
			}
			if (U.CycleT <= 0.f && !bPinned)
			{
				U.bAtPeek = true;
				U.CycleT = Tuning.PeekS;
				GoTo(U, S.Peek, Tuning.CoverCmS);
			}
			return;
		}
		// at the step out: shoot, then back
		U.Act = EAct::Peek;
		U.CycleT -= Dt;
		if (ToPeek > 40.f && U.Path.Num() && U.PathI < U.Path.Num())
		{
			Move(U, Dt);
			return;
		}
		U.Speed = 0.f;
		if (U.BurstLeft <= 0 && U.FireT <= 0.f && U.AcquireT <= 0.f && U.Rounds > 0 && U.ReloadT <= 0.f)
		{
			U.BurstLeft = FMath::Min(U.Weapon.Burst, U.Rounds);
			U.RoundT = 0.f;
		}
		FireRounds(U, Dt);
		if ((U.CycleT <= 0.f && U.BurstLeft <= 0) || bPinned)
		{
			U.bAtPeek = false;
			U.CycleT = Rng.FRandRange(Tuning.HideMinS, Tuning.HideMaxS) * (1.f + U.Suppression * 1.2f);
			GoTo(U, S.Pos, Tuning.CoverCmS);
		}
		return;
	}
	// in the open: he stands and shoots, and slips behind something when he can
	U.Act = EAct::Peek;
	if (U.Path.Num() && U.PathI < U.Path.Num() && U.Speed > 1.f)
	{
		// a squad on the move that sees the enemy stops to shoot (the leader's plan will move it again); a man going through a door in a drill goes on to his corner and fires as he goes
		if ((Dist < 1800.f || U.Role == ERole::Heavy) && U.EntryT <= 0.f && !U.bMoveFire)
		{
			U.Path.Reset();
			U.Speed = 0.f;
		}
		else
		{
			Move(U, Dt);
		}
	}
	else
	{
		U.Speed = 0.f;
	}
	if (U.BurstLeft <= 0 && U.FireT <= 0.f && U.AcquireT <= 0.f && U.Rounds > 0 && !bPinned)
	{
		U.BurstLeft = FMath::Min(U.Weapon.Burst, U.Rounds);
		U.RoundT = 0.f;
	}
	FireRounds(U, Dt);
}

bool FAstraBoardSim::TakeCover(FUnit& U, const FVector& EnemyFeet)
{
	if (!Tuning.bCover || !Map->GetComps().IsValidIndex(U.Comp) || U.CoverT > 0.f)
	{
		return false;
	}
	const FVector Enemy = EnemyFeet + FVector(0, 0, 150);
	// his own compartment's corners, and the ones across the nearest doorways
	TArray<int32> Comps;
	Comps.Add(U.Comp);
	for (const int32 Pi : Map->GetComps()[U.Comp].Portals)
	{
		const FBoardPortal& P = Map->GetPortals()[Pi];
		if (!P.bVertical() && FVector::Dist2D(P.Pos, U.Pos) < 900.f)
		{
			Comps.AddUnique(P.Other(U.Comp));
		}
	}
	TArray<int32> Good, Mine;
	for (const int32 C : Comps)
	{
		Map->FightingSlots(C, Enemy, U.Pos, &Doors, Good);
		for (const int32 S : Good)
		{
			if (FVector::Dist2D(Map->GetSlots()[S].Pos, U.Pos) < 1100.f)
			{
				Mine.Add(S);
			}
		}
	}
	if (Mine.IsEmpty())
	{
		U.CoverT = 1.6f;
		return false;
	}
	// a corner nobody else of his squad has
	const FSquad* Sq = Teams.IsValidIndex(U.Squad) ? &Teams[U.Squad] : nullptr;
	int32 Pick = INDEX_NONE;
	float BestD = 1.0e9f;
	for (const int32 S : Mine)
	{
		bool bTaken = false;
		if (Sq)
		{
			for (const int32 M : Sq->Members)
			{
				bTaken |= M != U.Id && People[M].Slot == S && People[M].Able();
			}
		}
		if (bTaken)
		{
			continue;
		}
		const float D = (float)FVector::Dist2D(Map->GetSlots()[S].Pos, U.Pos);
		if (D < BestD)
		{
			BestD = D;
			Pick = S;
		}
	}
	if (Pick == INDEX_NONE)
	{
		U.CoverT = 1.6f;
		return false;
	}
	U.Slot = Pick;
	U.bAtPeek = false;
	U.CycleT = Rng.FRandRange(0.2f, 0.7f);
	GoTo(U, Map->GetSlots()[Pick].Pos, Tuning.CoverCmS);
	return true;
}

// ================================================================================================================== moving

void FAstraBoardSim::GoTo(FUnit& U, const FVector& To, float Speed, bool bThroughSealed)
{
	FBoardRouteOptions Opt;
	Opt.Doors = &Doors;
	Opt.bThroughSealed = bThroughSealed || IsAttacker(U.Side);           // the attackers cut through what is shut; the holders go the way that is open
	Opt.bThroughClosed = true;                                           // (a door a squad shut behind it is a delay, not a wall: every side goes by it, working at it)
	TArray<FVector> Pts;
	if (!Map->Route(U.Pos, To, Pts, Opt) || Pts.Num() < 2)
	{
		U.Path.Reset();
		U.PathI = 0;
		U.Speed = 0.f;
		return;
	}
	// his place across a corridor: the interior points shift sideways a little, within the doors' width
	if (U.Lane != 0.f && Pts.Num() > 2)
	{
		for (int32 i = 1; i + 1 < Pts.Num(); ++i)
		{
			const FVector D = (Pts[i + 1] - Pts[i - 1]).GetSafeNormal2D();
			const FVector Side(-D.Y, D.X, 0.f);
			Pts[i] += Side * FMath::Clamp(U.Lane, -60.f, 60.f);
		}
	}
	U.Path = MoveTemp(Pts);
	U.PathI = 1;
	U.Dest = To;
	U.Speed = Speed;
	U.Cruise = Speed;
	if (U.Act != EAct::Reload && U.Act != EAct::Down)
	{
		U.Act = EAct::Move;
	}
}

void FAstraBoardSim::Move(FUnit& U, float Dt)
{
	if (U.Path.Num() == 0 || U.PathI >= U.Path.Num())
	{
		U.Speed = 0.f;
		return;
	}
	U.Speed = U.Cruise;
	U.WaitDoor = INDEX_NONE;
	float Left = U.Cruise * Dt * (U.Hp < 30.f ? 0.7f : 1.f);
	U.bLow = false;
	while (Left > 0.f && U.PathI < U.Path.Num())
	{
		const FVector Next = U.Path[U.PathI];
		// a sealed bulkhead ahead: they wait at it (the attackers are cutting through)
		if (Map->GetComps().IsValidIndex(U.Comp))
		{
			bool bShut = false;
			for (const int32 Pi : Map->GetComps()[U.Comp].Portals)
			{
				const FBoardPortal& P = Map->GetPortals()[Pi];
				if (P.bDoor() && Doors.IsSealed(P.Door) && FVector::Dist2D(Next, P.Pos) < 170.0 && FVector::Dist2D(U.Pos, P.Pos) < 190.0)
				{
					bShut = true;
					break;
				}
			}
			if (bShut)
			{
				U.Speed = 0.f;
				U.Act = EAct::Idle;
				for (const int32 Pi : Map->GetComps()[U.Comp].Portals)
				{
					const FBoardPortal& P = Map->GetPortals()[Pi];
					if (P.bDoor() && Doors.IsSealed(P.Door) && FVector::Dist2D(Next, P.Pos) < 170.0 && FVector::Dist2D(U.Pos, P.Pos) < 190.0)
					{
						U.WaitDoor = P.Door;                  // (the door he is waiting at: who works at a door a squad has shut)
						break;
					}
				}
				return;
			}
		}
		if (FMath::Abs(Next.Z - U.Pos.Z) > 120.f)
		{
			// stairs take time, not distance
			U.StairT += Dt;
			Left = 0.f;
			if (U.StairT >= 6.f)
			{
				U.StairT = 0.f;
				U.Pos = Next;
				++U.PathI;
			}
			break;
		}
		const double D = FVector::Dist2D(U.Pos, Next);
		if (D <= Left)
		{
			U.Pos = Next;
			Left -= (float)D;
			++U.PathI;
		}
		else
		{
			const FVector Dir = (Next - U.Pos).GetSafeNormal2D();
			U.Pos += Dir * Left;
			Left = 0.f;
		}
	}
	if (U.PathI < U.Path.Num() && U.Target == INDEX_NONE)
	{
		const FVector Dir = (U.Path[FMath::Min(U.PathI, U.Path.Num() - 1)] - U.Pos);
		if (!Dir.IsNearlyZero())
		{
			U.Yaw = FMath::UnwindDegrees(FMath::FInterpTo(U.Yaw, Yaw2D(Dir), 0.1f, 14.f));
		}
	}
	const int32 C = Map->CompAt(U.Pos, 50.f);
	if (C != INDEX_NONE)
	{
		U.Comp = C;
	}
	if (U.PathI >= U.Path.Num())
	{
		U.Path.Reset();
		U.PathI = 0;
		U.Speed = 0.f;
		if (U.Act == EAct::Move)
		{
			U.Act = U.Slot != INDEX_NONE && FVector::Dist2D(U.Pos, Map->GetSlots()[U.Slot].Pos) < 60.f ? EAct::Cover : EAct::Idle;
		}
	}
}

// ================================================================================================================== the objective

void FAstraBoardSim::StepMission(float Dt)
{
	if (Mis.Outcome != EOutcome::Running)
	{
		return;
	}
	const ESide Att = Mis.Attacker;
	int32 AttAtObjective = 0, DefAtObjective = 0, AttStill = 0, DefAble = 0;
	for (const FUnit& U : People)
	{
		if (U.bExternal)
		{
			continue;
		}
		if (U.Side == Att)
		{
			AttStill += (U.Able() || U.Act == EAct::Waiting) ? 1 : 0;
			AttAtObjective += (U.Able() && U.Comp == Mis.Objective) ? 1 : 0;
		}
		else
		{
			DefAtObjective += (U.Able() && U.Comp == Mis.Objective) ? 1 : 0;
			DefAble += U.Able() ? 1 : 0;
		}
	}
	// the Captain stands with his own side: in the objective he holds it against the Mandate's boarders, and with his marines he helps take it
	const bool bCaptainThere = People.IsValidIndex(CaptainUnit) && People[CaptainUnit].Comp == Mis.Objective && People[CaptainUnit].Act != EAct::Down && People[CaptainUnit].Act != EAct::Gone && People[CaptainUnit].Act != EAct::Dead;
	if (bCaptainThere)
	{
		if (Att == ESide::Aquila)
		{
			++AttAtObjective;
		}
		else
		{
			++DefAtObjective;
		}
	}
	// two men hold a place (the last man of a party that has lost the rest holds it alone: nobody else is left to come)
	if (Mis.Objective != INDEX_NONE && AttAtObjective >= FMath::Clamp(AttStill, 1, 2) && DefAtObjective == 0)
	{
		Mis.HeldS += Dt;
	}
	else
	{
		Mis.HeldS = FMath::Max(0.f, Mis.HeldS - 2.f * Dt);
	}
	if (Mis.HeldS >= Tuning.HoldS)
	{
		Mis.Outcome = EOutcome::AttackerTakes;
	}
	else if (Mis.bSweep && DefAble == 0 && Stats.Spawned[(int32)Defender()] > 0 && AttAtObjective + AttStill > 0 && Mis.StartedS >= 0.0 && Clock - Mis.StartedS > 20.0)
	{
		Mis.Outcome = EOutcome::AttackerTakes;                   // nobody is left to hold the ship
	}
	else if (AttStill == 0 && Pending.Num() == 0 && Stats.Spawned[(int32)Att] > 0)
	{
		Mis.Outcome = Stats.Exited[(int32)Att] > 0 && Stats.Killed[(int32)Att] + Stats.Down[(int32)Att] < Stats.Spawned[(int32)Att] ? EOutcome::AttackerRepelled : EOutcome::DefenderHolds;
	}
	else if (Mis.StartedS >= 0.0 ? Clock - Mis.StartedS > TimeLimitS : Clock > TimeLimitS + PreLandingLimitS)
	{
		Mis.Outcome = EOutcome::TimedOut;
	}
	if (Mis.Outcome != EOutcome::Running)
	{
		Stats.EndT = Clock;
		Emit(EEvent::Outcome, INDEX_NONE, INDEX_NONE, FVector::ZeroVector, FVector::ZeroVector, 0.f, false, FString::FromInt((int32)Mis.Outcome));
	}
}

FString FAstraBoardSim::HostileSummary() const
{
	TArray<FSeen> Seen;
	Intel(Defender(), Seen);
	if (Seen.IsEmpty())
	{
		return TEXT("no hostile contact on the internal sensors");
	}
	TMap<FString, int32> By;
	for (const FSeen& S : Seen)
	{
		By.FindOrAdd(Map->Describe(Map->CompAt(S.Pos, 80.f)))++;
	}
	TArray<FString> Parts;
	for (const TPair<FString, int32>& KV : By)
	{
		Parts.Add(FString::Printf(TEXT("%d at %s"), KV.Value, *KV.Key));
	}
	return FString::Join(Parts, TEXT("; "));
}

bool FAstraBoardSim::Known(const FUnit& U, int32 Enemy, FVector& OutPos, float& OutAge) const
{
	for (const FSeen& S : U.Seen)
	{
		if (S.Unit == Enemy)
		{
			OutPos = S.Pos;
			OutAge = S.AgeS;
			return true;
		}
	}
	return false;
}

FString FAstraBoardSim::DescribeSquad(const FSquad& S) const
{
	int32 Able = 0, Down = 0, Dead = 0, Gone = 0;
	for (const int32 M : S.Members)
	{
		switch (People[M].Act)
		{
		case EAct::Down: ++Down; break;
		case EAct::Dead: ++Dead; break;
		case EAct::Gone: ++Gone; break;
		default: ++Able; break;
		}
	}
	FString Where = TEXT("nowhere");
	if (S.Leader != INDEX_NONE && People.IsValidIndex(S.Leader))
	{
		Where = Map->Describe(People[S.Leader].Comp);
	}
	return FString::Printf(TEXT("%s: %d able, %d down, %d dead%s — %s, %s%s"), *S.Name, Able, Down, Dead, Gone ? *FString::Printf(TEXT(", %d off the ship"), Gone) : TEXT(""),
	                       TaskName(S.Task), *Where, S.bContact ? TEXT(", in contact") : TEXT(""));
}
