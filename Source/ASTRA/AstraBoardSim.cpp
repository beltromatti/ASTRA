// ASTRA — ABBORDAGGI: the fight inside the Aquila: the men, their senses, their guns (the squad drill is in AstraBoardAI.cpp). See AstraBoardSim.h.

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
	Pending.Reset();
	OpenNow.Reset();
	Doors.Init(Map->NumDoors());
	CutT.Init(0.f, Map->NumDoors());
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
	TArray<int32> Out;
	Mis.Objective = ObjectiveComp;
	Mis.Breach = BreachComp;
	Mis.BreachPos = BreachPos;
	const int32 PerSquad = 5;
	const int32 NumSquads = FMath::Max(1, FMath::DivideAndRoundUp(Count, PerSquad));
	static const TCHAR* Names[] = {TEXT("Ferry Guard Alpha"), TEXT("Ferry Guard Bravo"), TEXT("Ferry Guard Charlie"), TEXT("Ferry Guard Delta"), TEXT("Ferry Guard Echo"), TEXT("Ferry Guard Foxtrot")};
	int32 Made = 0;
	float At = FirstAtS;
	for (int32 s = 0; s < NumSquads && Made < Count; ++s)
	{
		const int32 Sq = AddSquad(ESide::Mandate, Names[s % UE_ARRAY_COUNT(Names)]);
		Out.Add(Sq);
		const int32 Here = FMath::Min(PerSquad, Count - Made);
		for (int32 k = 0; k < Here; ++k)
		{
			const ERole Role = k == 0 ? ERole::Leader : (k == Here - 1 && Here >= 4 ? ERole::Heavy : ERole::Rifleman);
			FString Name = MandateName(Made);
			if (Role == ERole::Leader)
			{
				Name = TEXT("Warden ") + Name;
			}
			else
			{
				Name = TEXT("Oarsman ") + Name;
			}
			// they come in a few steps apart from the cut in the wall
			const FVector Spot = Map->Inset(BreachComp, BreachPos + FVector(Rng.FRandRange(-120.f, 120.f), Rng.FRandRange(-120.f, 120.f), 0.f), 60.f);
			FUnit& U = Spawn(ESide::Mandate, Role, Name, Spot, Sq);
			U.Act = EAct::Waiting;
			Pending.Add({U.Id, At});
			At += 0.9f + Rng.FRand() * 0.5f;
			++Made;
		}
		FSquad& S = Teams[Sq];
		S.Task = ETask::Advance;
		S.TargetComp = ObjectiveComp;
		S.TargetPos = Map->CentreOf(ObjectiveComp);
		S.Note = TEXT("to the objective");
	}
	return Out;
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

int32 FAstraBoardSim::AddCaptain(const FVector& Pos)
{
	FUnit& U = Spawn(ESide::Aquila, ERole::Captain, TEXT("the Captain"), Pos, INDEX_NONE);
	U.bExternal = true;
	U.Armor = 1.f;
	CaptainUnit = U.Id;
	--Stats.Spawned[0];
	return U.Id;
}

void FAstraBoardSim::SetCaptain(const FVector& Pos, float Yaw, bool bLow, float Speed, bool bDown)
{
	if (!People.IsValidIndex(CaptainUnit))
	{
		return;
	}
	FUnit& U = People[CaptainUnit];
	U.Pos = Pos;
	U.Yaw = Yaw;
	U.bLow = bLow;
	U.Speed = Speed;
	U.Comp = Map->CompAt(Pos, 60.f);
	if (U.Act != EAct::Gone && U.Act != EAct::Dead)
	{
		U.Act = bDown ? EAct::Down : EAct::Idle;
	}
}

void FAstraBoardSim::SealDoor(int32 Door, bool bSealed)
{
	if (Doors.Sealed.IsValidIndex(Door))
	{
		Doors.Sealed[Door] = bSealed;
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
			Emit(EEvent::Spawn, U.Id, INDEX_NONE, U.Pos, U.Pos, 0.f, false, U.Name);
			Pending.RemoveAt(i);
		}
	}
	StepDoors();
	StepSensors(Dt);
	for (FUnit& U : People)
	{
		if (!U.bExternal && (U.Act != EAct::Dead && U.Act != EAct::Gone && U.Act != EAct::Waiting))
		{
			if (U.Act == EAct::Down)
			{
				U.Bleed -= Dt;
				if (U.Bleed <= 0.f)
				{
					Kill(U, INDEX_NONE, TEXT("bled out"));
				}
				continue;
			}
			Perceive(U, Dt);
		}
	}
	for (FSquad& S : Teams)
	{
		StepSquad(S, Dt);
	}
	for (FUnit& U : People)
	{
		if (!U.bExternal && U.Act != EAct::Dead && U.Act != EAct::Gone && U.Act != EAct::Waiting && U.Act != EAct::Down)
		{
			StepUnit(U, Dt);
		}
	}
	StepMission(Dt);
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
	TArray<int32, TInlineAllocator<8>> Cutting;
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
			if (!P.bDoor())
			{
				continue;
			}
			const double D = FVector::Dist2D(U.Pos, P.Pos);
			if (Doors.IsSealed(P.Door))
			{
				// the Mandate at a sealed bulkhead cut through it
				if (U.Side == ESide::Mandate && U.Able() && D < 260.0 && !Cutting.Contains(P.Door))
				{
					Cutting.Add(P.Door);
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
		if (Cutting.Contains(d))
		{
			CutT[d] += StepS;
			if (CutT[d] >= Tuning.CutS)
			{
				CutT[d] = 0.f;
				Doors.Sealed[d] = false;
				const int32 Pi = Map->PortalOfDoor(d);
				Emit(EEvent::Order, INDEX_NONE, INDEX_NONE, Pi != INDEX_NONE ? Map->GetPortals()[Pi].Pos : FVector::ZeroVector, FVector::ZeroVector, 0.f, false,
				     FString::Printf(TEXT("the Mandate cut through the bulkhead at %s"), Pi != INDEX_NONE ? *Map->Describe(Map->GetPortals()[Pi].A) : TEXT("?")));
			}
		}
		else if (CutT[d] > 0.f)
		{
			CutT[d] = FMath::Max(0.f, CutT[d] - StepS);
		}
	}
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

/** The internal sensors of the ship see the corridors and the halls (not the rooms): the marines' picture of the Mandate's men, a couple of seconds stale. */
void FAstraBoardSim::StepSensors(float Dt)
{
	SensorT += Dt;
	if (SensorT < 1.0f)
	{
		return;
	}
	SensorT = 0.f;
	TArray<FSeen>& Pic = SensorPicture[(int32)ESide::Aquila];
	for (FSeen& S : Pic)
	{
		S.AgeS += 1.f;
	}
	for (const FUnit& U : People)
	{
		if (U.Side != ESide::Mandate || !U.Able() || !Map->GetComps().IsValidIndex(U.Comp))
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
	if (Side == ESide::Aquila)
	{
		for (const FSeen& S : SensorPicture[(int32)ESide::Aquila])
		{
			if (People.IsValidIndex(S.Unit) && People[S.Unit].Able())
			{
				Out.Add(S);
			}
		}
		for (const FUnit& U : People)
		{
			if (U.Side != ESide::Aquila || !U.Able())
			{
				continue;
			}
			for (const FSeen& S : U.Seen)
			{
				if (People.IsValidIndex(S.Unit) && People[S.Unit].Side == ESide::Mandate && People[S.Unit].Able() && !Out.ContainsByPredicate([&S](const FSeen& O) { return O.Unit == S.Unit; }))
				{
					Out.Add(S);
				}
			}
		}
	}
	else
	{
		for (const FUnit& U : People)
		{
			if (U.Side != ESide::Mandate || !U.Able())
			{
				continue;
			}
			for (const FSeen& S : U.Seen)
			{
				if (People.IsValidIndex(S.Unit) && People[S.Unit].Side == ESide::Aquila && People[S.Unit].Able() && !Out.ContainsByPredicate([&S](const FSeen& O) { return O.Unit == S.Unit; }))
				{
					Out.Add(S);
				}
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
		bool bSee = SightOverride && (E.bExternal || U.bExternal) ? SightOverride(MyEye, E.Eye()) : Map->Visible(MyEye, E.Eye(), &Doors);
		if (!bSee)
		{
			continue;
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
			U.AcquireT = Rng.FRandRange(Tuning.AcquireMinS, Tuning.AcquireMaxS) * (1.f + U.Suppression) * (U.Role == ERole::Leader ? 0.8f : 1.f);
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
	if (Target.bLow)
	{
		P *= 0.8f;
	}
	if (Target.Speed > 60.f)
	{
		P *= Tuning.MoveFactor;
	}
	P *= 1.f - 0.55f * Shooter.Suppression;
	if (Shooter.Hp < 45.f)
	{
		P *= 0.8f;
	}
	if (Shooter.Speed > 60.f)
	{
		P *= 0.7f;                                           // firing on the move
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
			End = T.Pos + FVector(Rng.FRandRange(-12.f, 12.f), Rng.FRandRange(-12.f, 12.f), bHead ? (T.bLow ? 95.f : 160.f) : (T.bLow ? 70.f : Rng.FRandRange(85.f, 135.f)));
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
	const float Real = Dmg * T.Armor;
	T.Hp -= Real;
	++T.HitsTaken;
	T.Suppression = FMath::Min(1.f, T.Suppression + 0.22f);
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
	const float Lethal = bHead ? 0.8f : 0.26f + 0.5f * Over;
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
		++Stats.Down[(int32)T.Side];
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

void FAstraBoardSim::CarryOut(int32 UnitId)
{
	if (People.IsValidIndex(UnitId) && People[UnitId].Act == EAct::Down)
	{
		People[UnitId].Act = EAct::Gone;
		++Stats.Rescues;
	}
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
				// at his corner, waiting for the enemy to show
				const FBoardSlot& S = Map->GetSlots()[U.Slot];
				if (FVector::Dist2D(U.Pos, S.Pos) > 40.f)
				{
					GoTo(U, S.Pos, Tuning.CoverCmS);
				}
				U.Act = EAct::Cover;
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
	// dry: reload where he is hidden, or get hidden first
	if (U.Rounds <= 0 && U.Reserve > 0)
	{
		const bool bHidden = U.Slot != INDEX_NONE && FVector::Dist2D(U.Pos, Map->GetSlots()[U.Slot].Pos) < 40.f;
		if (bHidden || Dist > 1800.f || !TakeCover(U, T.Pos))
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
	if (U.Slot == INDEX_NONE && Dist > 500.f && U.Speed < 1.f)
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
		// a squad on the move that sees the enemy stops to shoot (the leader's plan will move it again)
		if (Dist < 1800.f || U.Role == ERole::Heavy)
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
	Opt.bThroughSealed = bThroughSealed || U.Side == ESide::Mandate;     // the Mandate cut through what is shut; the marines go the way that is open
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
	float Left = U.Speed * Dt * (U.Hp < 30.f ? 0.7f : 1.f);
	U.bLow = false;
	while (Left > 0.f && U.PathI < U.Path.Num())
	{
		const FVector Next = U.Path[U.PathI];
		// a sealed bulkhead ahead: they wait at it (the Mandate are cutting through)
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
	int32 Mandate = 0, Aquila = 0, Still = 0;
	for (const FUnit& U : People)
	{
		if (U.bExternal)
		{
			continue;
		}
		if (U.Side == ESide::Mandate)
		{
			Still += (U.Able() || U.Act == EAct::Waiting) ? 1 : 0;
			Mandate += (U.Able() && U.Comp == Mis.Objective) ? 1 : 0;
		}
		else
		{
			Aquila += (U.Able() && U.Comp == Mis.Objective) ? 1 : 0;
		}
	}
	const bool bCaptainThere = People.IsValidIndex(CaptainUnit) && People[CaptainUnit].Comp == Mis.Objective && People[CaptainUnit].Act != EAct::Down && People[CaptainUnit].Act != EAct::Gone;
	if (Mis.Objective != INDEX_NONE && Mandate >= 2 && Aquila == 0 && !bCaptainThere)
	{
		Mis.HeldS += Dt;
	}
	else
	{
		Mis.HeldS = FMath::Max(0.f, Mis.HeldS - 2.f * Dt);
	}
	if (Mis.HeldS >= Tuning.HoldS)
	{
		Mis.Outcome = EOutcome::MandateTakes;
	}
	else if (Still == 0 && Pending.Num() == 0 && Stats.Spawned[1] > 0)
	{
		Mis.Outcome = Stats.Exited[1] > 0 && Stats.Killed[1] + Stats.Down[1] < Stats.Spawned[1] ? EOutcome::MandateRepelled : EOutcome::AquilaHolds;
	}
	else if (Clock > TimeLimitS)
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
	Intel(ESide::Aquila, Seen);
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
