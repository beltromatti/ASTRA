#include "AstraBoardSimCommandlet.h"

#include "ASTRA.h"
#include "AstraBoardMap.h"
#include "AstraBoardSim.h"
#include "AstraDamageMap.h"
#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "HAL/PlatformTime.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"

using namespace AstraBoard;

namespace
{
	struct FBCheck
	{
		FString Name;
		bool bPass = true;
		FString Detail;
	};
	TArray<FBCheck> BChecks;
	TSharedRef<FJsonObject> BRecord = MakeShared<FJsonObject>();

	void BCheck(const ANSICHAR* Name, bool bPass, const FString& Detail)
	{
		BChecks.Add({FString(ANSI_TO_TCHAR(Name)), bPass, Detail});
		UE_LOG(LogASTRA, Display, TEXT("[Board] %s %-34s %s"), bPass ? TEXT("PASS") : TEXT("FAIL"), ANSI_TO_TCHAR(Name), *Detail);
	}

	void BNote(const FString& Text) { UE_LOG(LogASTRA, Display, TEXT("[Board]   %s"), *Text); }

	void ApplyTuning(FTuning& T, const FString& Spec)
	{
		TArray<FString> Items;
		Spec.ParseIntoArray(Items, TEXT(","));
		for (const FString& It : Items)
		{
			FString K, V;
			if (!It.Split(TEXT("="), &K, &V))
			{
				continue;
			}
			K = K.TrimStartAndEnd();
			const float F = FCString::Atof(*V);
#define BSET(Name) if (K.Equals(TEXT(#Name), ESearchCase::IgnoreCase)) { T.Name = F; continue; }
			BSET(MarineSkill) BSET(MandateSkill) BSET(LeaderSkill) BSET(MarineArmor) BSET(MandateArmor) BSET(AcquireMinS) BSET(AcquireMaxS) BSET(HideMinS) BSET(HideMaxS)
			BSET(PeekS) BSET(JogCmS) BSET(WalkCmS) BSET(CoverCmS) BSET(SuppressDecay) BSET(SuppressPerRound) BSET(SuppressMiss) BSET(CoverFactor) BSET(MoveFactor)
			BSET(RangeFullCm) BSET(RangeFarCm) BSET(RangeMaxCm) BSET(DownBleedMinS) BSET(DownBleedMaxS) BSET(MandateRetreatLoss) BSET(HoldS) BSET(HearCm) BSET(SensorDelayS) BSET(CutS)
#undef BSET
			if (K.Equals(TEXT("bFlank"), ESearchCase::IgnoreCase)) { T.bFlank = F > 0.5f; continue; }
			if (K.Equals(TEXT("bCover"), ESearchCase::IgnoreCase)) { T.bCover = F > 0.5f; continue; }
			UE_LOG(LogASTRA, Warning, TEXT("[Board] no tuning named %s"), *K);
		}
	}

	struct FRig
	{
		TSharedPtr<FAstraDamageMap> Src;
		TSharedPtr<FAstraBoardMap> Map;
		double BuildMs = 0.0;
		FTuning Tuning;

		bool Make()
		{
			const double T0 = FPlatformTime::Seconds();
			Src = MakeShared<FAstraDamageMap>();
			FString Err;
			if (!Src->Load(Err, true))
			{
				UE_LOG(LogASTRA, Error, TEXT("[Board] %s"), *Err);
				return false;
			}
			Map = MakeShared<FAstraBoardMap>();
			if (!Map->Build(Src.ToSharedRef()))
			{
				return false;
			}
			BuildMs = (FPlatformTime::Seconds() - T0) * 1000.0;
			return true;
		}
		int32 Comp(const TCHAR* Id) const { return Src->CompByName.FindRef(FName(Id), INDEX_NONE); }
	};

	bool GTrace = false;                    // -trace=1: one line per five seconds of every fight, and its events

	struct FRunResult
	{
		EOutcome Outcome = EOutcome::Running;
		double T = 0.0;
		FBook Book;
		int32 AquilaAble = 0, AquilaDown = 0, MandateAble = 0, MandateDown = 0;
		uint32 Hash = 0;
		double Ms = 0.0, MsMax = 0.0;
		int32 BadPos = 0;
		int32 Steps = 0;
		int32 Slow = 0;                      // steps over 3 ms
	};

	FRunResult RunSim(FAstraBoardSim& Sim, double Seconds, const TFunction<void(FAstraBoardSim&)>& PerSecond = nullptr)
	{
		FRunResult R;
		const FAstraBoardMap& Map = Sim.GetMap();
		double NextSec = 1.0;
		while (Sim.Time() < Seconds && !Sim.Over())
		{
			const double T0 = FPlatformTime::Seconds();
			Sim.Tick(0.1f);
			const double Ms = (FPlatformTime::Seconds() - T0) * 1000.0;
			R.Ms += Ms;
			R.MsMax = FMath::Max(R.MsMax, Ms);
			R.Slow += Ms > 3.0 ? 1 : 0;
			++R.Steps;
			if (Sim.Time() >= NextSec)
			{
				NextSec += 1.0;
				for (const FUnit& U : Sim.Units())
				{
					if (U.Able() && !U.bExternal && Map.CompAt(U.Pos + FVector(0, 0, 20), 90.f) == INDEX_NONE)
					{
						++R.BadPos;
					}
				}
				if (PerSecond)
				{
					PerSecond(Sim);
				}
				if (GTrace)
				{
					TArray<FBoardEvent> Evs;
					Sim.TakeEvents(Evs);
					for (const FBoardEvent& E : Evs)
					{
						if (E.Type == EEvent::Shot || E.Type == EEvent::Hit || E.Type == EEvent::Reload || E.Type == EEvent::Spawn)
						{
							continue;
						}
						static const TCHAR* Names[] = {TEXT("shot"), TEXT("hit"), TEXT("DOWN"), TEXT("DIED"), TEXT("RETREAT"), TEXT("EXIT"), TEXT("contact"), TEXT("rescue"), TEXT("reload"), TEXT("spawn"), TEXT("ORDER"), TEXT("OUTCOME")};
						const FUnit* U = Sim.Unit(E.Unit);
						const FUnit* T = Sim.Unit(E.Target);
						BNote(FString::Printf(TEXT("t=%5.1f %-7s %s%s%s %s"), E.T, Names[(int32)E.Type], U ? *U->Name : TEXT(""), T ? *FString::Printf(TEXT(" -> %s"), *T->Name) : TEXT(""),
						                      U ? *FString::Printf(TEXT(" @ %s"), *Map.Describe(U->Comp)) : TEXT(""), *E.Text));
					}
					if (FMath::FloorToInt(Sim.Time()) % 5 == 0)
					{
						for (const FSquad& Sq : Sim.Squads())
						{
							BNote(FString::Printf(TEXT("t=%5.1f   %s [%s] %s"), Sim.Time(), *Sim.DescribeSquad(Sq), Sq.Flankers[0] != INDEX_NONE ? TEXT("flank out") : TEXT(""), *Sq.Note));
							const FUnit* Ld = Sq.Leader != INDEX_NONE ? Sim.Unit(Sq.Leader) : nullptr;
							if (Ld && GTrace)
							{
								const FVector Nx = Ld->Path.IsValidIndex(Ld->PathI) ? Ld->Path[Ld->PathI] : FVector::ZeroVector;
								BNote(FString::Printf(TEXT("          leader at (%.0f, %.0f, %.0f) act %d speed %.0f path %d/%d next (%.0f, %.0f, %.0f) dest (%.0f, %.0f, %.0f) target (%.0f, %.0f)"), Ld->Pos.X / 100, Ld->Pos.Y / 100, Ld->Pos.Z / 100,
								                      (int32)Ld->Act, Ld->Speed, Ld->PathI, Ld->Path.Num(), Nx.X / 100, Nx.Y / 100, Nx.Z / 100, Ld->Dest.X / 100, Ld->Dest.Y / 100, Ld->Dest.Z / 100, Sq.TargetPos.X / 100, Sq.TargetPos.Y / 100));
							}
						}
					}
				}
			}
		}
		R.Outcome = Sim.Mission().Outcome;
		R.T = Sim.Time();
		R.Book = Sim.Book();
		R.AquilaAble = Sim.CountAble(ESide::Aquila);
		R.AquilaDown = Sim.CountDown(ESide::Aquila);
		R.MandateAble = Sim.CountAble(ESide::Mandate);
		R.MandateDown = Sim.CountDown(ESide::Mandate);
		uint32 H = 2166136261u;
		for (const FUnit& U : Sim.Units())
		{
			H = (H ^ (uint32)FMath::RoundToInt(U.Pos.X)) * 16777619u;
			H = (H ^ (uint32)FMath::RoundToInt(U.Pos.Y)) * 16777619u;
			H = (H ^ (uint32)U.Act) * 16777619u;
			H = (H ^ (uint32)FMath::RoundToInt(U.Hp)) * 16777619u;
		}
		R.Hash = H;
		return R;
	}

	const TCHAR* OutcomeName(EOutcome O)
	{
		switch (O)
		{
		case EOutcome::AquilaHolds: return TEXT("the boarders were all put down");
		case EOutcome::MandateRepelled: return TEXT("the boarders broke off and left");
		case EOutcome::MandateTakes: return TEXT("the Mandate took the objective");
		case EOutcome::TimedOut: return TEXT("no end in the time");
		default: return TEXT("running");
		}
	}

	FString Json(const TSharedRef<FJsonObject>& O)
	{
		FString Out;
		const TSharedRef<TJsonWriter<>> W = TJsonWriterFactory<>::Create(&Out);
		FJsonSerializer::Serialize(O, W);
		return Out;
	}

	/** The corridor of Deck 8 that runs straight for 80 m with no pressure bulkhead in it (x -60 .. 20 on the Spine): where the duels are fought. */
	struct FLane
	{
		int32 FirstComp = INDEX_NONE;
		FVector Start, End;
		bool Find(const FRig& Rig)
		{
			FirstComp = Rig.Comp(TEXT("d8_sp1_C4"));
			if (FirstComp == INDEX_NONE)
			{
				return false;
			}
			const float Z = Rig.Map->GetComps()[FirstComp].FloorZ();
			Start = FVector(-5500.0, 0.0, Z);
			End = FVector(1800.0, 0.0, Z);
			return true;
		}
	};
}

UAstraBoardSimCommandlet::UAstraBoardSimCommandlet()
{
	IsClient = false;
	IsServer = false;
	IsEditor = true;                 // the editor's plugins assume an editor engine even here (as the damage, life and war benches)
	LogToConsole = true;
	ShowErrorCount = true;
}

// ================================================================================================================== the map

static void BoardScenarioMap(FRig& Rig, int32 Seed)
{
	const FAstraBoardMap& M = *Rig.Map;
	int32 NPortal[5] = {0, 0, 0, 0, 0};
	for (const FBoardPortal& P : M.GetPortals())
	{
		++NPortal[(int32)P.Kind];
	}
	BCheck("map built", M.IsReady() && M.GetPortals().Num() > 2000 && M.GetSlots().Num() > 3000,
	       FString::Printf(TEXT("%d compartments, %d portals (open %d, door %d, blast %d, stair %d, lift %d), %d corner slots, built in %.0f ms"), M.GetComps().Num(), M.GetPortals().Num(),
	                       NPortal[0], NPortal[1], NPortal[2], NPortal[3], NPortal[4], M.GetSlots().Num(), Rig.BuildMs));
	// every portal's mouth is inside its two compartments (give or take the wall)
	int32 BadPortal = 0, BadDoor = 0;
	for (const FBoardPortal& P : M.GetPortals())
	{
		if (P.bVertical())
		{
			continue;
		}
		const FBox A = M.GetComps()[P.A].Box.ExpandBy(70.0), B = M.GetComps()[P.B].Box.ExpandBy(70.0);
		if (!A.IsInsideOrOn(P.Pos + FVector(0, 0, 50)) || !B.IsInsideOrOn(P.Pos + FVector(0, 0, 50)))
		{
			++BadPortal;
		}
		BadDoor += (P.bDoor() && P.Door == INDEX_NONE) ? 1 : 0;
	}
	BCheck("portals lie on the walls", BadPortal <= M.GetPortals().Num() / 100 && BadDoor == 0, FString::Printf(TEXT("%d of %d off their faces"), BadPortal, M.GetPortals().Num()));
	// slots
	int32 BadSlot = 0;
	for (const FBoardSlot& S : M.GetSlots())
	{
		if (M.CompAt(S.Pos + FVector(0, 0, 20), 5.f) != S.Comp || M.CompAt(S.Peek + FVector(0, 0, 20), 5.f) != S.Comp)
		{
			++BadSlot;
		}
	}
	BCheck("corner slots are in their rooms", BadSlot <= M.GetSlots().Num() / 50, FString::Printf(TEXT("%d of %d outside"), BadSlot, M.GetSlots().Num()));
	// routes between random rooms
	FRandomStream R(Seed);
	TArray<int32> Candidates;
	for (int32 i = 0; i < M.GetComps().Num(); ++i)
	{
		if (M.GetComps()[i].Deck >= 2 && M.GetComps()[i].Portals.Num() > 0)
		{
			Candidates.Add(i);
		}
	}
	int32 Ok = 0, BadRoute = 0, Crooked = 0;
	double Ms = 0.0, MsMax = 0.0, Metres = 0.0;
	const int32 Tries = 400;
	FBoardRouteOptions Opt;
	for (int32 k = 0; k < Tries; ++k)
	{
		const int32 A = Candidates[R.RandHelper(Candidates.Num())], B = Candidates[R.RandHelper(Candidates.Num())];
		TArray<FVector> Pts;
		float Len = 0.f;
		const double T0 = FPlatformTime::Seconds();
		const bool bOk = M.Route(M.CentreOf(A), M.CentreOf(B), Pts, Opt, &Len);
		const double D = (FPlatformTime::Seconds() - T0) * 1000.0;
		Ms += D;
		MsMax = FMath::Max(MsMax, D);
		if (!bOk)
		{
			continue;
		}
		++Ok;
		Metres += Len;
		for (const FVector& P : Pts)
		{
			if (M.CompAt(P + FVector(0, 0, 20), 120.f) == INDEX_NONE)
			{
				++BadRoute;
				break;
			}
		}
		const double Straight = FVector::Dist2D(M.CentreOf(A), M.CentreOf(B)) / 100.0;
		if (Pts.Num() > 2 && M.GetComps()[A].Deck == M.GetComps()[B].Deck && Len > 3.0 * Straight + 40.0)
		{
			++Crooked;
		}
	}
	BCheck("routes between rooms", Ok >= Tries * 9 / 10 && BadRoute == 0 && MsMax < 25.0,
	       FString::Printf(TEXT("%d of %d found, %d with a point outside the ship, %d far from straight, %.3f ms avg %.2f max, %.0f m avg"), Ok, Tries, BadRoute, Crooked, Ms / Tries, MsMax, Ok ? Metres / Ok : 0.0));
	// the line of sight
	FLane Lane;
	bool bLos = false, bWall = true, bRoomToRoom = true;
	if (Lane.Find(Rig))
	{
		bLos = M.Visible(Lane.Start + FVector(0, 0, 150), Lane.End + FVector(0, 0, 150), nullptr);
	}
	// two rooms that share a wall: neither sees the other, doors open or not
	const int32 Ra = Rig.Comp(TEXT("d8_kit_room_C1")), Rb = Rig.Comp(TEXT("d8_store_dry_C1"));
	if (Ra != INDEX_NONE && Rb != INDEX_NONE)
	{
		bRoomToRoom = M.Visible(M.CentreOf(Ra) + FVector(0, 0, 150), M.CentreOf(Rb) + FVector(0, 0, 150), nullptr);
	}
	FBoardDoors Shut;
	Shut.Init(M.NumDoors());
	const int32 Kit = Rig.Comp(TEXT("d8_kit_room_C1")), Spine = Rig.Comp(TEXT("d8_sp1_C1"));
	if (Kit != INDEX_NONE && Spine != INDEX_NONE)
	{
		const FVector Inside = M.CentreOf(Kit) + FVector(0, 0, 150), Out = M.CentreOf(Spine) + FVector(0, 0, 150);
		const bool bDoorsOpen = M.Visible(Inside, Out, nullptr);
		bWall = !M.Visible(Inside, Out, &Shut);                            // every door shut: a wall
		BNote(FString::Printf(TEXT("kit room sees the spine with the doors open: %s, with them shut: %s"), bDoorsOpen ? TEXT("yes") : TEXT("no"), !bWall ? TEXT("yes") : TEXT("no")));
	}
	BCheck("sight: a corridor is long, a wall is a wall", bLos && !bRoomToRoom && bWall,
	       FString::Printf(TEXT("80 m along the Spine: %s; room to the next room through the wall: %s; door shut: %s"), bLos ? TEXT("seen") : TEXT("BLOCKED"), bRoomToRoom ? TEXT("SEEN") : TEXT("not seen"), bWall ? TEXT("not seen") : TEXT("SEEN")));
	// corners hide a man from the line through the door and let him see through it from the step out
	int32 Tested = 0, Hidden = 0, Sees = 0;
	for (int32 k = 0; k < 600 && Tested < 300; ++k)
	{
		const FBoardSlot& S = M.GetSlots()[R.RandHelper(M.GetSlots().Num())];
		const FBoardPortal& P = M.GetPortals()[S.Portal];
		if (!P.bDoor())
		{
			continue;
		}
		const FVector2D Out2 = FVector2D(-S.Out.X, -S.Out.Y) * -1.0;      // from the slot through the opening
		const FVector Far = FVector(P.Pos.X + Out2.X * 600.0, P.Pos.Y + Out2.Y * 600.0, M.GetComps()[S.Comp].FloorZ() + 150.0);
		if (M.CompAt(Far - FVector(0, 0, 100), 5.f) == INDEX_NONE)
		{
			continue;
		}
		++Tested;
		Hidden += !M.Visible(S.Pos + FVector(0, 0, 150), Far, nullptr, INDEX_NONE) ? 1 : 0;
		Sees += M.Visible(S.Peek + FVector(0, 0, 150), Far, nullptr, P.Door) ? 1 : 0;
	}
	BCheck("corners hide and show", Tested > 100 && Hidden >= Tested * 6 / 10 && Sees >= Tested * 5 / 10,
	       FString::Printf(TEXT("%d doorways tried: the corner is hidden from the line through the door %d times, the step out sees through it %d times"), Tested, Hidden, Sees));
	TSharedRef<FJsonObject> O = MakeShared<FJsonObject>();
	O->SetNumberField(TEXT("portals"), M.GetPortals().Num());
	O->SetNumberField(TEXT("slots"), M.GetSlots().Num());
	O->SetNumberField(TEXT("route_ms"), Ms / Tries);
	BRecord->SetObjectField(TEXT("map"), O);
}

// ================================================================================================================== duels

static void SetupLaneDuel(FAstraBoardSim& Sim, const FRig& Rig, const FLane& Lane, float RangeCm, int32 N, int32 FaceOff)
{
	// N men a side, the two lines RangeCm apart on the Spine; the Mandate go for the Aquila's end
	const int32 SqA = Sim.AddSquad(ESide::Aquila, TEXT("Alpha"));
	const int32 SqM = Sim.AddSquad(ESide::Mandate, TEXT("Ferry Guard Alpha"));
	const float Mid = 0.5f * (float)(Lane.Start.X + Lane.End.X);
	const float XA = FMath::Min(Mid + RangeCm * 0.5f, (float)Lane.End.X), XM = XA - RangeCm;
	for (int32 i = 0; i < N; ++i)
	{
		const FVector PA(XA + i * 90.f, (i % 3 - 1) * 70.f, Lane.Start.Z), PM(XM - i * 90.f, (i % 3 - 1) * 70.f, Lane.Start.Z);
		Sim.AddUnit(ESide::Aquila, i == 0 ? ERole::Leader : ERole::Rifleman, FString::Printf(TEXT("Marine %d"), i + 1), PA, SqA);
		FUnit* M = Sim.UnitMutable(Sim.AddUnit(ESide::Mandate, i == 0 ? ERole::Leader : ERole::Rifleman, FString::Printf(TEXT("Oarsman %d"), i + 1), PM, SqM));
		M->Yaw = 0.f;
	}
	FSquad* A = Sim.SquadMutable(SqA);
	FSquad* Mm = Sim.SquadMutable(SqM);
	A->StartStrength = Mm->StartStrength = (float)N;
	A->Leader = A->Members.Num() ? A->Members[0] : INDEX_NONE;
	Mm->Leader = Mm->Members.Num() ? Mm->Members[0] : INDEX_NONE;
	Sim.Order(SqA, ETask::Hold, INDEX_NONE, FVector(XA, 0, Lane.Start.Z), 700.f, TEXT("hold the lane"));
	Mm->Task = ETask::Advance;
	Mm->TargetPos = FVector(XA, 0, Lane.Start.Z);
	Mm->TargetComp = Sim.GetMap().CompAt(Mm->TargetPos, 80.f);
	Sim.MissionMutable().Breach = Sim.GetMap().CompAt(FVector(XM, 0, Lane.Start.Z), 80.f);
	Sim.MissionMutable().BreachPos = FVector(XM - 400.f, 0, Lane.Start.Z);
	Sim.MissionMutable().Objective = INDEX_NONE;
	(void)Rig;
	(void)FaceOff;
}

static void BoardScenarioDuel(FRig& Rig, int32 Seed, int32 Seeds)
{
	FLane Lane;
	if (!Lane.Find(Rig))
	{
		BCheck("duel lane", false, TEXT("no lane on Deck 8"));
		return;
	}
	TSharedRef<FJsonObject> Rec = MakeShared<FJsonObject>();
	const float Ranges[] = {500.f, 1000.f, 2000.f, 3000.f};
	double TtkAt10 = 0.0;
	float WinAt10 = 0.f;
	for (const float Range : Ranges)
	{
		int32 AquilaWins = 0, Decided = 0, Both = 0;
		double Ttk = 0.0;
		int32 Killed = 0, Down = 0;
		for (int32 s = 0; s < Seeds; ++s)
		{
			FAstraBoardSim Sim;
			Sim.Init(Rig.Map.ToSharedRef(), Seed + s);
			Sim.Tuning = Rig.Tuning;
			Sim.Tuning.MandateSkill = Sim.Tuning.MarineSkill;
			Sim.Tuning.MandateArmor = Sim.Tuning.MarineArmor;
			// one man a side
			const int32 SqA = Sim.AddSquad(ESide::Aquila, TEXT("A")), SqM = Sim.AddSquad(ESide::Mandate, TEXT("M"));
			const float XA = 400.f, XM = XA - Range;
			const int32 A = Sim.AddUnit(ESide::Aquila, ERole::Leader, TEXT("A"), FVector(XA, 0, Lane.Start.Z), SqA);
			const int32 M = Sim.AddUnit(ESide::Mandate, ERole::Leader, TEXT("M"), FVector(XM, 0, Lane.Start.Z), SqM);
			Sim.UnitMutable(A)->Yaw = 180.f;
			Sim.UnitMutable(M)->Yaw = 0.f;
			// they face each other, and stay where they are (no cover in this one)
			Sim.Tuning.bCover = false;
			Sim.SquadMutable(SqA)->bStand = Sim.SquadMutable(SqM)->bStand = true;
			double Ended = -1.0;
			while (Sim.Time() < 30.0)
			{
				Sim.Tick(0.1f);
				if (!Sim.Units()[A].Able() || !Sim.Units()[M].Able())
				{
					Ended = Sim.Time();
					break;
				}
			}
			if (Ended > 0.0)
			{
				++Decided;
				Ttk += Ended;
				AquilaWins += Sim.Units()[M].Able() ? 0 : 1;
				Both += (!Sim.Units()[A].Able() && !Sim.Units()[M].Able()) ? 1 : 0;
				Killed += (Sim.Units()[A].Act == EAct::Dead ? 1 : 0) + (Sim.Units()[M].Act == EAct::Dead ? 1 : 0);
				Down += (Sim.Units()[A].Act == EAct::Down ? 1 : 0) + (Sim.Units()[M].Act == EAct::Down ? 1 : 0);
			}
		}
		const double Mean = Decided ? Ttk / Decided : 0.0;
		BNote(FString::Printf(TEXT("%.0f m, one on one, no cover: %d of %d decided, the first man fell after %.1f s on average; the marine won %d (%.0f%%); killed %d, down %d"), Range / 100.0,
		                      Decided, Seeds, Mean, AquilaWins, Decided ? 100.0 * AquilaWins / Decided : 0.0, Killed, Down));
		if (FMath::IsNearlyEqual(Range, 1000.f))
		{
			TtkAt10 = Mean;
			WinAt10 = Decided ? (float)AquilaWins / Decided : 0.f;
		}
		TSharedRef<FJsonObject> O = MakeShared<FJsonObject>();
		O->SetNumberField(TEXT("decided"), Decided);
		O->SetNumberField(TEXT("ttk_s"), Mean);
		O->SetNumberField(TEXT("aquila_wins"), AquilaWins);
		Rec->SetObjectField(FString::Printf(TEXT("r%.0f"), Range / 100.0), O);
	}
	BCheck("duel at 10 m", TtkAt10 > 0.7 && TtkAt10 < 6.0 && WinAt10 > 0.38 && WinAt10 < 0.62,
	       FString::Printf(TEXT("the first man falls after %.1f s; the equal men win %.0f%% each (fair: 50)"), TtkAt10, 100.0 * WinAt10));
	BRecord->SetObjectField(TEXT("duel"), Rec);
}

// ================================================================================================================== a squad fight in the lane

static void BoardScenarioSquad(FRig& Rig, int32 Seed, int32 Seeds)
{
	FLane Lane;
	if (!Lane.Find(Rig))
	{
		return;
	}
	TSharedRef<FJsonObject> Rec = MakeShared<FJsonObject>();
	for (int32 Mode = 0; Mode < 2; ++Mode)
	{
		const bool bCover = Mode == 1;
		int32 AquilaWins = 0, Decided = 0, BadPos = 0;
		double Ttk = 0.0, LossA = 0.0, LossM = 0.0, Ms = 0.0;
		for (int32 s = 0; s < Seeds; ++s)
		{
			FAstraBoardSim Sim;
			Sim.Init(Rig.Map.ToSharedRef(), Seed + s);
			Sim.Tuning = Rig.Tuning;
			Sim.Tuning.bCover = bCover;
			SetupLaneDuel(Sim, Rig, Lane, 4500.f, 5, 0);
			const FRunResult R = RunSim(Sim, 120.0);
			const int32 MandateGone = Sim.CountAble(ESide::Mandate);
			const bool bAquilaWon = MandateGone == 0 && Sim.CountAble(ESide::Aquila) > 0;
			const bool bMandateWon = Sim.CountAble(ESide::Aquila) == 0 && MandateGone > 0;
			if (bAquilaWon || bMandateWon)
			{
				++Decided;
				Ttk += R.T;
				AquilaWins += bAquilaWon ? 1 : 0;
			}
			LossA += R.Book.Killed[0] + R.Book.Down[0];
			LossM += R.Book.Killed[1] + R.Book.Down[1];
			BadPos += R.BadPos;
			Ms += R.Ms / FMath::Max(1, R.Steps);
		}
		BNote(FString::Printf(TEXT("5 marines hold the lane against 5 of the Mandate coming 45 m, %s: decided %d of %d in %.0f s, the marines won %d; lost per side %.1f / %.1f; %.3f ms a step"),
		                      bCover ? TEXT("with corners") : TEXT("in the open"), Decided, Seeds, Decided ? Ttk / Decided : 0.0, AquilaWins, LossA / Seeds, LossM / Seeds, Ms / Seeds));
		BCheck(bCover ? "squad fight with corners" : "squad fight in the open", Decided >= Seeds / 2 && BadPos == 0 && Ms / Seeds < 0.5,
		       FString::Printf(TEXT("decided %d of %d, %d men off the plan, %.3f ms a step"), Decided, Seeds, BadPos, Ms / Seeds));
		TSharedRef<FJsonObject> O = MakeShared<FJsonObject>();
		O->SetNumberField(TEXT("decided"), Decided);
		O->SetNumberField(TEXT("aquila_wins"), AquilaWins);
		O->SetNumberField(TEXT("loss_aquila"), LossA / Seeds);
		O->SetNumberField(TEXT("loss_mandate"), LossM / Seeds);
		Rec->SetObjectField(bCover ? TEXT("cover") : TEXT("open"), O);
	}
	BRecord->SetObjectField(TEXT("squad"), Rec);
}

// ================================================================================================================== the flank

static void BoardScenarioFlank(FRig& Rig, int32 Seed, int32 Seeds)
{
	const int32 Obj = Rig.Comp(TEXT("d8_sp1_C0"));
	const int32 Start = Rig.Comp(TEXT("d8_sp1_C4"));
	if (Obj == INDEX_NONE || Start == INDEX_NONE)
	{
		BCheck("flank scenario", false, TEXT("rooms not found"));
		return;
	}
	TSharedRef<FJsonObject> Rec = MakeShared<FJsonObject>();
	double WinFlank[2] = {0, 0};
	int32 TotalFlanks = 0;
	for (int32 Mode = 0; Mode < 2; ++Mode)
	{
		int32 MandateWins = 0, Decided = 0, Flanks = 0;
		double LossA = 0.0, LossM = 0.0;
		for (int32 s = 0; s < Seeds; ++s)
		{
			FAstraBoardSim Sim;
			Sim.Init(Rig.Map.ToSharedRef(), Seed + s);
			Sim.Tuning = Rig.Tuning;
			Sim.Tuning.bFlank = Mode == 1;
			Sim.Tuning.HoldS = 40.f;
			const FVector Spawn = Rig.Map->CentreOf(Start);
			// 10 of the Mandate come in at the far end of the Spine; 8 marines hold the junction at the other
			const TArray<int32> Sq = Sim.SpawnBoarders(Start, Spawn, Obj, 10, 0.f);
			const int32 SqA = Sim.AddSquad(ESide::Aquila, TEXT("Alpha")), SqB = Sim.AddSquad(ESide::Aquila, TEXT("Bravo"));
			const FVector At = Rig.Map->CentreOf(Obj);
			for (int32 i = 0; i < 8; ++i)
			{
				const FVector P = Rig.Map->Inset(Obj, At + FVector((i % 4) * 160.f - 240.f, (i / 4) * 140.f - 70.f, 0.f), 60.f);
				Sim.AddMarine(FString::Printf(TEXT("Marine %d"), i + 1), INDEX_NONE, P, i % 4 == 0, i < 4 ? SqA : SqB);
			}
			Sim.Order(SqA, ETask::Hold, Obj, At, 800.f, TEXT("hold the junction"));
			Sim.Order(SqB, ETask::Hold, Obj, At, 800.f, TEXT("hold the junction"));
			const FRunResult R = RunSim(Sim, 240.0);
			const bool bM = R.Outcome == EOutcome::MandateTakes || (R.MandateAble > 0 && R.AquilaAble == 0);
			const bool bA = R.Outcome == EOutcome::AquilaHolds || R.Outcome == EOutcome::MandateRepelled;
			if (bM || bA)
			{
				++Decided;
				MandateWins += bM ? 1 : 0;
			}
			Flanks += R.Book.Flanks;
			if (Mode == 1)
			{
				TotalFlanks += R.Book.Flanks;
			}
			LossA += R.Book.Killed[0] + R.Book.Down[0];
			LossM += R.Book.Killed[1] + R.Book.Down[1];
		}
		WinFlank[Mode] = Decided ? (double)MandateWins / Decided : 0.0;
		BNote(FString::Printf(TEXT("10 Mandate against 8 marines holding a junction, flank %s: the Mandate won %d of %d decided (%.0f%%), %d flanks tried; lost per side %.1f / %.1f"),
		                      Mode ? TEXT("on") : TEXT("off"), MandateWins, Decided, 100.0 * WinFlank[Mode], Flanks, LossA / Seeds, LossM / Seeds));
		TSharedRef<FJsonObject> O = MakeShared<FJsonObject>();
		O->SetNumberField(TEXT("decided"), Decided);
		O->SetNumberField(TEXT("mandate_wins"), MandateWins);
		O->SetNumberField(TEXT("flanks"), Flanks);
		Rec->SetObjectField(Mode ? TEXT("flank_on") : TEXT("flank_off"), O);
	}
	// the sample is small: the flank is only asked to be tried and to be no worse than none beyond the noise of the count (two standard errors of the difference)
	const double Se = FMath::Sqrt(2.0 * 0.25 / FMath::Max(1, Seeds));
	BCheck("the flank is tried and costs nothing", TotalFlanks > 0 && WinFlank[1] <= WinFlank[0] + 2.0 * Se,
	       FString::Printf(TEXT("the Mandate win %.0f%% with it, %.0f%% without (noise %.0f%%), %d flanks tried"), 100.0 * WinFlank[1], 100.0 * WinFlank[0], 100.0 * Se, TotalFlanks));
	BRecord->SetObjectField(TEXT("flank"), Rec);
}

// ================================================================================================================== a boarding of the real ship

struct FBoardFight
{
	FRunResult R;
	bool bFound = false;
	int32 Marines = 0;
	double FirstContact = -1.0;
};

static FBoardFight RunBoarding(FRig& Rig, int32 Seed, int32 Boarders, int32 Duty, int32 Qrf, const TCHAR* BreachId, const TCHAR* ObjectiveId, bool bSealed, float MusterS)
{
	FBoardFight F;
	const int32 Breach = Rig.Comp(BreachId), Obj = Rig.Comp(ObjectiveId);
	if (Breach == INDEX_NONE || Obj == INDEX_NONE)
	{
		return F;
	}
	F.bFound = true;
	FAstraBoardSim Sim;
	Sim.Init(Rig.Map.ToSharedRef(), Seed);
	Sim.Tuning = Rig.Tuning;
	const FAstraBoardMap& M = *Rig.Map;
	FRandomStream R(Seed * 31 + 7);
	// the breach: a cut in the hull wall of an outer room
	const FBox& BB = M.GetComps()[Breach].Box;
	const FVector Cut(0.5 * (BB.Min.X + BB.Max.X), BB.Max.Y > 0 ? BB.Max.Y - 80.0 : BB.Min.Y + 80.0, BB.Min.Z);
	Sim.SpawnBoarders(Breach, Cut, Obj, Boarders, 45.f);       // the boarding craft was seen closing 45 s before it cut in: the alarm is on, the marines are moving
	// the marines on watch: in the rooms of Deck 8 where the department works
	TArray<int32> Posts;
	for (int32 i = 0; i < M.GetComps().Num(); ++i)
	{
		const FBoardComp& C = M.GetComps()[i];
		if (C.Deck == 8 && (C.Kind == TEXT("armory") || C.Kind == TEXT("range") || C.Kind == TEXT("cabins") || C.Kind == TEXT("hangar")))
		{
			Posts.Add(i);
		}
	}
	const int32 PerSquad = 4;
	int32 Made = 0;
	int32 Sq = INDEX_NONE;
	TArray<FVector> Spots;
	for (int32 i = 0; i < Duty; ++i)
	{
		const int32 C = Posts[R.RandHelper(Posts.Num())];
		Spots.Add(M.Inset(C, M.CentreOf(C) + FVector(R.FRandRange(-500.f, 500.f), R.FRandRange(-300.f, 300.f), 0.f), 60.f));
	}
	Spots.Sort([](const FVector& A, const FVector& B) { return A.X < B.X; });
	for (int32 i = 0; i < Duty; ++i)
	{
		if (i % PerSquad == 0)
		{
			Sq = Sim.AddSquad(ESide::Aquila, FString::Printf(TEXT("Watch %d"), i / PerSquad + 1));
		}
		Sim.AddMarine(FString::Printf(TEXT("Marine %d"), ++Made), INDEX_NONE, Spots[i], i % PerSquad == 0, Sq);
	}
	// the reaction team musters at the armory
	const int32 Armory = Rig.Comp(TEXT("d8_armory_C1"));
	for (int32 i = 0; i < Qrf; ++i)
	{
		if (i % 6 == 0)
		{
			Sq = Sim.AddSquad(ESide::Aquila, FString::Printf(TEXT("Reaction %d"), i / 6 + 1));
			Sim.SquadMutable(Sq)->bQuickReaction = true;
			Sim.SquadMutable(Sq)->MusterT = MusterS;
		}
		Sim.AddMarine(FString::Printf(TEXT("Marine %d"), ++Made), INDEX_NONE, M.Inset(Armory, M.CentreOf(Armory) + FVector(R.FRandRange(-500.f, 500.f), R.FRandRange(-300.f, 300.f), 0.f), 60.f), i % 6 == 0, Sq);
	}
	F.Marines = Made;
	if (bSealed)
	{
		// the section bulkheads round the breach are shut
		for (const FBoardPortal& P : M.GetPortals())
		{
			if (P.Kind == FBoardPortal::EKind::Blast && M.GetComps()[P.A].Deck == M.GetComps()[Breach].Deck && FVector::Dist2D(P.Pos, Cut) < 9000.0)
			{
				Sim.SealDoor(P.Door, true);
			}
		}
	}
	F.R = RunSim(Sim, 600.0);
	F.FirstContact = F.R.Book.FirstContactT;
	return F;
}

static int32 GSetup = -1;

static void BoardScenarioBoard(FRig& Rig, int32 Seed, int32 Seeds, int32 Boarders)
{
	TSharedRef<FJsonObject> Rec = MakeShared<FJsonObject>();
	struct FSetup { const TCHAR* Name; int32 Boarders; int32 Duty; int32 Qrf; bool bSealed; float Muster; };
	const FSetup Setups[] = {
		{TEXT("one skiff: the marines on watch and the reaction team, the section bulkheads sealed"), 10, 24, 12, true, 25.f},
		{TEXT("one skiff: the same, the bulkheads not sealed"), 10, 24, 12, false, 25.f},
		{TEXT("two skiffs, sealed"), 20, 24, 12, true, 25.f},
		{TEXT("three skiffs, sealed"), 30, 24, 12, true, 25.f},
		{TEXT("one skiff: only the reaction team, sealed"), 10, 0, 12, true, 25.f},
		{TEXT("one skiff: nobody armed (the marines asleep), sealed"), 10, 0, 0, true, 25.f},
	};
	for (int32 si = 0; si < UE_ARRAY_COUNT(Setups); ++si)
	{
		if (GSetup >= 0 && si != GSetup)
		{
			continue;
		}
		const FSetup& S = Setups[si];
		if (Boarders > 0 && si > 0 && Boarders != S.Boarders && si != 1)
		{
			// -boarders=N asks for one setup with N: the first is rerun with it
		}
		int32 Wins[4] = {0, 0, 0, 0};            // holds, repelled, takes, timed out
		double T = 0.0, LossA = 0.0, LossM = 0.0, DownA = 0.0, Contact = 0.0, Held = 0.0;
		int32 Found = 0, Bad = 0, Flanks = 0, Retreats = 0, Cuts = 0;
		double Ms = 0.0, MsMax = 0.0;
		double PartMs[3] = {0.0, 0.0, 0.0}, PartWorst[3] = {0.0, 0.0, 0.0};
		int32 SlowSteps = 0, AllSteps = 0;
		for (int32 s = 0; s < Seeds; ++s)
		{
			const FBoardFight F = RunBoarding(Rig, Seed + s, Boarders > 0 && si == 0 ? Boarders : S.Boarders, S.Duty, S.Qrf, TEXT("d7_capacitors_D2"), TEXT("engineering"), S.bSealed, S.Muster);
			if (!F.bFound)
			{
				continue;
			}
			++Found;
			Wins[F.R.Outcome == EOutcome::AquilaHolds ? 0 : F.R.Outcome == EOutcome::MandateRepelled ? 1 : F.R.Outcome == EOutcome::MandateTakes ? 2 : 3]++;
			T += F.R.T;
			LossA += F.R.Book.Killed[0] + F.R.Book.Down[0];
			DownA += F.R.Book.Down[0];
			LossM += F.R.Book.Killed[1] + F.R.Book.Down[1];
			Contact += F.R.Book.FirstContactT;
			Flanks += F.R.Book.Flanks;
			Retreats += F.R.Book.Retreats;
			Bad += F.R.BadPos;
			Ms += F.R.Ms / FMath::Max(1, F.R.Steps);
			SlowSteps += F.R.Slow;
			AllSteps += F.R.Steps;
			MsMax = FMath::Max(MsMax, F.R.MsMax);
			for (int32 k = 0; k < 3; ++k)
			{
				PartMs[k] += F.R.Book.Ms[k] / FMath::Max(1, F.R.Steps);
				PartWorst[k] = FMath::Max(PartWorst[k], F.R.Book.MsWorst[k]);
			}
			(void)Held;
			(void)Cuts;
		}
		if (!Found)
		{
			BCheck("boarding", false, TEXT("rooms not found in the plan"));
			return;
		}
		const double N = Found;
		BNote(FString::Printf(TEXT("%s: %d fights — marines hold %d, the Mandate break off %d, the Mandate take Main Engineering %d, no end %d; ends at %.0f s, first contact %.0f s; marines lost %.1f (down %.1f), "
		                           "Mandate lost %.1f; flanks %.1f, retreats %.1f; %.3f ms a step (worst %.1f)"),
		                      S.Name, Found, Wins[0], Wins[1], Wins[2], Wins[3], T / N, Contact / N, LossA / N, DownA / N, LossM / N, Flanks / N, Retreats / N, Ms / N, MsMax));
		BNote(FString::Printf(TEXT("    a step costs on average %.3f ms sensing, %.3f ms the squads' plans, %.3f ms the men; worst step %.1f / %.1f / %.1f ms"), PartMs[0] / N, PartMs[1] / N, PartMs[2] / N, PartWorst[0], PartWorst[1], PartWorst[2]));
		BNote(FString::Printf(TEXT("    %d of %d steps took over 3 ms (%.2f%%)"), SlowSteps, AllSteps, 100.0 * SlowSteps / FMath::Max(1, AllSteps)));
		TSharedRef<FJsonObject> O = MakeShared<FJsonObject>();
		O->SetStringField(TEXT("setup"), S.Name);
		O->SetNumberField(TEXT("fights"), Found);
		O->SetNumberField(TEXT("holds"), Wins[0]);
		O->SetNumberField(TEXT("repelled"), Wins[1]);
		O->SetNumberField(TEXT("takes"), Wins[2]);
		O->SetNumberField(TEXT("timed_out"), Wins[3]);
		O->SetNumberField(TEXT("end_s"), T / N);
		O->SetNumberField(TEXT("loss_marines"), LossA / N);
		O->SetNumberField(TEXT("loss_mandate"), LossM / N);
		Rec->SetObjectField(FString::Printf(TEXT("setup%d"), si), O);
		if (si == 0)
		{
			BCheck("boarding: the ship defends itself", Bad == 0 && Wins[2] <= Found / 2 && Wins[3] == 0 && (Ms / N) < 1.0,
			       FString::Printf(TEXT("%d fights: the Mandate take the objective in %d; %d men off the plan; %.3f ms a step"), Found, Wins[2], Bad, Ms / N));
		}
		if (si == 5)
		{
			BCheck("boarding: unarmed, the ship is taken", Wins[2] >= Found * 8 / 10, FString::Printf(TEXT("%d of %d"), Wins[2], Found));
		}
	}
	BRecord->SetObjectField(TEXT("board"), Rec);
}

// ================================================================================================================== the rules

static void BoardScenarioRules(FRig& Rig, int32 Seed)
{
	FLane Lane;
	Lane.Find(Rig);
	// the wounded and the dead: hits on armoured men
	int32 Killed = 0, Down = 0, Standing = 0;
	for (int32 s = 0; s < 400; ++s)
	{
		FAstraBoardSim Sim;
		Sim.Init(Rig.Map.ToSharedRef(), Seed + s);
		Sim.Tuning = Rig.Tuning;
		const int32 Sq = Sim.AddSquad(ESide::Aquila, TEXT("A"));
		const int32 U = Sim.AddMarine(TEXT("M"), INDEX_NONE, FVector(0, 0, Lane.Start.Z), true, Sq);
		for (int32 h = 0; h < 9; ++h)
		{
			Sim.HitUnit(U, 17.f, false);
		}
		const FUnit* P = Sim.Unit(U);
		Killed += P->Act == EAct::Dead ? 1 : 0;
		Down += P->Act == EAct::Down ? 1 : 0;
		Standing += P->Able() ? 1 : 0;
	}
	BCheck("wounds: nine hits", Killed + Down >= 380 && Down > 60 && Killed > 60, FString::Printf(TEXT("of 400 marines hit nine times: %d killed, %d down and alive, %d standing"), Killed, Down, Standing));
	// the man who is down bleeds out if nobody comes
	{
		FAstraBoardSim Sim;
		Sim.Init(Rig.Map.ToSharedRef(), Seed);
		Sim.Tuning = Rig.Tuning;
		const int32 Sq = Sim.AddSquad(ESide::Aquila, TEXT("A"));
		int32 Fallen = INDEX_NONE;
		for (int32 k = 0; k < 40 && Fallen == INDEX_NONE; ++k)
		{
			const int32 U = Sim.AddMarine(TEXT("M"), INDEX_NONE, FVector(100.0 * k, 0, Lane.Start.Z), false, Sq);
			for (int32 h = 0; h < 9; ++h) { Sim.HitUnit(U, 17.f, false); }
			if (Sim.Unit(U)->Act == EAct::Down)
			{
				Fallen = U;
			}
		}
		double DiedAt = -1.0;
		while (Fallen != INDEX_NONE && Sim.Time() < 200.0)
		{
			Sim.Tick(0.5f);
			if (Sim.Unit(Fallen)->Act == EAct::Dead)
			{
				DiedAt = Sim.Time();
				break;
			}
		}
		BCheck("wounds: bleeding", Fallen != INDEX_NONE && DiedAt > 60.0 && DiedAt < 140.0, FString::Printf(TEXT("a man down and alone died after %.0f s"), DiedAt));
	}
	// a sealed bulkhead stops a route, and the Mandate cut through it
	{
		const int32 A = Rig.Comp(TEXT("d8_sp1_C4")), B = Rig.Comp(TEXT("d8_sp1_B3"));
		int32 Blast = INDEX_NONE;
		FBoardRouteOptions Opt;
		Opt.bStairs = false;
		FBoardDoors Doors;
		Doors.Init(Rig.Map->NumDoors());
		TArray<int32> Boundary;
		TArray<int32> Ps;
		if (A != INDEX_NONE && B != INDEX_NONE && Rig.Map->RoutePortals(Rig.Map->CentreOf(A), Rig.Map->CentreOf(B), Ps, Opt))
		{
			for (const int32 P : Ps)
			{
				if (Rig.Map->GetPortals()[P].Kind == FBoardPortal::EKind::Blast)
				{
					Blast = Rig.Map->GetPortals()[P].Door;
					// every pressure bulkhead on the same line across the deck (the Spine and the two passages)
					for (const FBoardPortal& Q : Rig.Map->GetPortals())
					{
						if (Q.Kind == FBoardPortal::EKind::Blast && FMath::Abs(Q.Pos.X - Rig.Map->GetPortals()[P].Pos.X) < 450.0 && FMath::Abs(Q.Pos.Z - Rig.Map->GetPortals()[P].Pos.Z) < 200.0)
						{
							Boundary.Add(Q.Door);
						}
					}
					break;
				}
			}
		}
		bool bStops = false, bCut = false;
		double CutT = -1.0;
		if (Blast != INDEX_NONE)
		{
			for (const int32 D : Boundary) { Doors.Sealed[D] = true; }
			Opt.Doors = &Doors;
			TArray<FVector> Pts;
			bStops = !Rig.Map->Route(Rig.Map->CentreOf(A), Rig.Map->CentreOf(B), Pts, Opt);
			BNote(FString::Printf(TEXT("%d bulkheads sealed on the line x=%.0f; route without them: %d portals; with them sealed: %s (%d points)"), Boundary.Num(),
			                      Rig.Map->GetPortals()[Rig.Map->PortalOfDoor(Blast)].Pos.X, Ps.Num(), bStops ? TEXT("none") : TEXT("still one"), Pts.Num()));
			// the Mandate walk up to it and cut
			FAstraBoardSim Sim;
			Sim.Init(Rig.Map.ToSharedRef(), Seed);
			Sim.Tuning = Rig.Tuning;
			for (const int32 D : Boundary) { Sim.SealDoor(D, true); }
			const int32 SqM = Sim.AddSquad(ESide::Mandate, TEXT("M"));
			Sim.AddUnit(ESide::Mandate, ERole::Leader, TEXT("M"), Rig.Map->CentreOf(A), SqM);
			Sim.Order(SqM, ETask::Advance, B, Rig.Map->CentreOf(B), 100.f);
			Sim.SquadMutable(SqM)->bOrdered = true;
			while (Sim.Time() < 200.0)
			{
				Sim.Tick(0.5f);
				if (!Sim.IsDoorSealed(Blast))
				{
					bCut = true;
					CutT = Sim.Time();
					break;
				}
			}
		}
		BCheck("bulkhead: sealed, then cut", Blast != INDEX_NONE && bStops && bCut, FString::Printf(TEXT("a sealed section bulkhead: the route stops %s, the Mandate cut through after %.0f s"), bStops ? TEXT("yes") : TEXT("NO"), CutT));
	}
	// determinism: the same fight twice
	{
		const FBoardFight A = RunBoarding(Rig, Seed, 10, 24, 12, TEXT("d7_capacitors_D2"), TEXT("engineering"), false, 25.f);
		const FBoardFight B = RunBoarding(Rig, Seed, 10, 24, 12, TEXT("d7_capacitors_D2"), TEXT("engineering"), false, 25.f);
		BCheck("deterministic from the seed", A.bFound && A.R.Hash == B.R.Hash && A.R.Outcome == B.R.Outcome, FString::Printf(TEXT("hash %08x and %08x, %s"), A.R.Hash, B.R.Hash, OutcomeName(A.R.Outcome)));
	}
}

int32 UAstraBoardSimCommandlet::Main(const FString& Params)
{
	FString Scenario = TEXT("all"), OutPath = TEXT("Saved/Boarding/run.json"), Set;
	int32 Seed = 1, Seeds = 20, Boarders = 0;
	FParse::Value(*Params, TEXT("-scenario="), Scenario);
	FParse::Value(*Params, TEXT("-seed="), Seed);
	FParse::Value(*Params, TEXT("-seeds="), Seeds);
	FParse::Value(*Params, TEXT("-boarders="), Boarders);
	FParse::Value(*Params, TEXT("-out="), OutPath);
	FParse::Value(*Params, TEXT("-set="), Set);
	GTrace = FParse::Param(*Params, TEXT("trace"));
	FParse::Value(*Params, TEXT("-setup="), GSetup);
	Scenario = Scenario.ToLower();
	FRig Rig;
	if (!Rig.Make())
	{
		BCheck("plan", false, TEXT("the plan did not load"));
		return 1;
	}
	ApplyTuning(Rig.Tuning, Set);
	auto Want = [&](const TCHAR* Name) { return Scenario == TEXT("all") || Scenario == Name; };
	if (Want(TEXT("map")))
	{
		BoardScenarioMap(Rig, Seed);
	}
	if (Want(TEXT("rules")))
	{
		BoardScenarioRules(Rig, Seed);
	}
	if (Want(TEXT("duel")))
	{
		BoardScenarioDuel(Rig, Seed, FMath::Max(40, Seeds * 4));
	}
	if (Want(TEXT("squad")))
	{
		BoardScenarioSquad(Rig, Seed, Seeds);
	}
	if (Want(TEXT("flank")))
	{
		BoardScenarioFlank(Rig, Seed, Seeds);
	}
	if (Want(TEXT("board")))
	{
		BoardScenarioBoard(Rig, Seed, Seeds, Boarders);
	}
	int32 Failed = 0;
	for (const FBCheck& C : BChecks)
	{
		Failed += C.bPass ? 0 : 1;
	}
	BRecord->SetStringField(TEXT("verdict"), Failed ? TEXT("FAIL") : TEXT("PASS"));
	BRecord->SetNumberField(TEXT("checks"), BChecks.Num());
	BRecord->SetNumberField(TEXT("failed"), Failed);
	TArray<TSharedPtr<FJsonValue>> Cs;
	for (const FBCheck& C : BChecks)
	{
		TSharedRef<FJsonObject> O = MakeShared<FJsonObject>();
		O->SetStringField(TEXT("name"), C.Name);
		O->SetBoolField(TEXT("pass"), C.bPass);
		O->SetStringField(TEXT("detail"), C.Detail);
		Cs.Add(MakeShared<FJsonValueObject>(O));
	}
	BRecord->SetArrayField(TEXT("list"), Cs);
	const FString Full = FPaths::IsRelative(OutPath) ? FPaths::Combine(FPaths::ProjectDir(), OutPath) : OutPath;
	IFileManager::Get().MakeDirectory(*FPaths::GetPath(Full), true);
	FFileHelper::SaveStringToFile(Json(BRecord), *Full);
	UE_LOG(LogASTRA, Display, TEXT("[Board] VERDICT: %s (%d checks, %d failed)"), Failed ? TEXT("FAIL") : TEXT("PASS"), BChecks.Num(), Failed);
	return Failed ? 1 : 0;
}
