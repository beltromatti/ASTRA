#include "AstraBoardSimCommandlet.h"

#include "ASTRA.h"
#include "ASTRACharacter.h"
#include "AstraArmsRig.h"
#include "AstraBoardDress.h"
#include "AstraBoardInterior.h"
#include "AstraBoardMap.h"
#include "AstraBoardPlans.h"
#include "AstraBoardScene.h"
#include "AstraBoardSim.h"
#include "AstraDamageMap.h"
#include "AstraFleetInterior.h"
#include "AstraFleetPlan.h"
#include "AstraWeapon.h"
#include "Animation/AnimSequence.h"
#include "Animation/AttributesRuntime.h"
#include "BonePose.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/SkeletalMeshSocket.h"
#if WITH_EDITORONLY_DATA
#include "Rendering/SkeletalMeshLODModel.h"
#include "Rendering/SkeletalMeshModel.h"
#endif
#include "HAL/IConsoleManager.h"
#include "ReferenceSkeleton.h"
#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "HAL/PlatformTime.h"
#include "Misc/FileHelper.h"
#include "Misc/MemStack.h"
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
			BSET(RangeFullCm) BSET(RangeFarCm) BSET(RangeMaxCm) BSET(DownBleedMinS) BSET(DownBleedMaxS) BSET(MandateRetreatLoss) BSET(MarineRetreatLoss) BSET(HoldS) BSET(HearCm) BSET(SensorDelayS) BSET(CutS)
			BSET(EvacPickupS) BSET(EvacCmS) BSET(EvacReachCm) BSET(EvacClearCm) BSET(EvacBleedBonusS)
#undef BSET
			if (K.Equals(TEXT("bFlank"), ESearchCase::IgnoreCase)) { T.bFlank = F > 0.5f; continue; }
			if (K.Equals(TEXT("bEvacuate"), ESearchCase::IgnoreCase)) { T.bEvacuate = F > 0.5f; continue; }
			if (K.Equals(TEXT("LethalAquila"), ESearchCase::IgnoreCase)) { T.LethalScale[0] = F; continue; }
			if (K.Equals(TEXT("LethalMandate"), ESearchCase::IgnoreCase)) { T.LethalScale[1] = F; continue; }
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

	/** The room the bench's boarders cut into: the first plan's capacitor hall if it is there, else the outermost built room of Deck 7 in the middle sections (what UAstraBoardSubsystem::PickBreach does). */
	FString BenchBreach(const FRig& Rig)
	{
		if (Rig.Comp(TEXT("d7_capacitors_D2")) != INDEX_NONE)
		{
			return TEXT("d7_capacitors_D2");
		}
		float Best = -1.f;
		FName Id;
		for (const FAstraDmgComp& K : Rig.Src->Comps)
		{
			if (K.Deck != 7 || K.bCorridor || K.Status == 0 || K.Section < TEXT('C') || K.Section > TEXT('F') || K.Box.GetSize().X < 600.0)
			{
				continue;
			}
			const float Out = (float)FMath::Abs(0.5 * (K.Box.Min.Y + K.Box.Max.Y));
			if (Out > Best)
			{
				Best = Out;
				Id = K.Id;
			}
		}
		return Id.ToString();
	}

	/** The armory where the reaction team arms: the first plan's, else the first room of that kind on Deck 8. */
	FString BenchArmory(const FRig& Rig)
	{
		if (Rig.Comp(TEXT("d8_armory_C1")) != INDEX_NONE)
		{
			return TEXT("d8_armory_C1");
		}
		for (const FAstraDmgComp& K : Rig.Src->Comps)
		{
			if (K.Deck == 8 && K.Kind == FName(TEXT("armory")))
			{
				return K.Id.ToString();
			}
		}
		return FString();
	}

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
		TArray<FFleetCasualty> DefCas;       // (a scene's fight) what it did to the people of the side that held the ship: the books' casualties (AstraBoardScene::CasualtiesOf)
	};

	FRunResult RunSim(FAstraBoardSim& Sim, double Seconds, const TFunction<void(FAstraBoardSim&)>& PerSecond = nullptr, const TFunction<void(FAstraBoardSim&)>& PerStep = nullptr)
	{
		FRunResult R;
		const FAstraBoardMap& Map = Sim.GetMap();
		double NextSec = 1.0;
		while (Sim.Time() < Seconds && !Sim.Over())
		{
			if (PerStep)
			{
				PerStep(Sim);                                                  // (a scripted man, the Captain, moves every step)
			}
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
						static const TCHAR* Names[] = {TEXT("shot"), TEXT("hit"), TEXT("DOWN"), TEXT("DIED"), TEXT("RETREAT"), TEXT("EXIT"), TEXT("contact"), TEXT("rescue"), TEXT("reload"), TEXT("spawn"), TEXT("ORDER"), TEXT("OUTCOME"), TEXT("CUT"), TEXT("CARRIED"), TEXT("DRILL"), TEXT("SEALED")};
						const FUnit* U = Sim.Unit(E.Unit);
						const FUnit* T = Sim.Unit(E.Target);
						BNote(FString::Printf(TEXT("t=%5.1f %-7s %s%s%s %s"), E.T, Names[(int32)E.Type], U ? *U->Name : TEXT(""), T ? *FString::Printf(TEXT(" -> %s"), *T->Name) : TEXT(""),
						                      U ? *FString::Printf(TEXT(" @ %s"), *Map.Describe(U->Comp)) : TEXT(""), *E.Text));
					}
					for (const FSquad& Sq : Sim.Squads())
					{
						if (Sq.Task >= ETask::Sweep && Sq.Drill != EDrill::None && Sq.Drill != EDrill::Done && Sq.Drill != EDrill::Hold)
						{
							BNote(FString::Printf(TEXT("t=%5.1f   %s: drill %s (%.1f s)%s%s"), Sim.Time(), *Sq.Name, DrillName(Sq.Drill), Sq.DrillT, Sq.bStackReady ? TEXT(", stack ready") : TEXT(""),
							                      Sq.SyncGoAt >= 0.f ? *FString::Printf(TEXT(", sync go at %.1f"), Sq.SyncGoAt) : TEXT("")));
						}
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
		case EOutcome::DefenderHolds: return TEXT("the boarders were all put down");
		case EOutcome::AttackerRepelled: return TEXT("the boarders broke off and left");
		case EOutcome::AttackerTakes: return TEXT("the Mandate took the objective");
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
	BCheck("routes between rooms", Ok >= Tries * 9 / 10 && BadRoute <= Tries / 100 && MsMax < 25.0,
	       FString::Printf(TEXT("%d of %d found, %d with a point outside the ship, %d far from straight, %.3f ms avg %.2f max, %.0f m avg"), Ok, Tries, BadRoute, Crooked, Ms / Tries, MsMax, Ok ? Metres / Ok : 0.0));
	// the line of sight
	FLane Lane;
	bool bLos = false, bWall = true, bRoomToRoom = true;
	if (Lane.Find(Rig))
	{
		bLos = M.Visible(Lane.Start + FVector(0, 0, 150), Lane.End + FVector(0, 0, 150), nullptr);
	}
	// two rooms that share a wall (and have no door between them): neither sees the other, doors open or not
	bRoomToRoom = false;
	FBoardDoors Shut;
	Shut.Init(M.NumDoors());
	int32 Ra = INDEX_NONE, Rb = INDEX_NONE;
	for (int32 i = 0; i < M.GetComps().Num() && Rb == INDEX_NONE; ++i)
	{
		const FBoardComp& CA = M.GetComps()[i];
		if (CA.Deck != 8 || CA.Kind == TEXT("corridor") || CA.Box.GetSize().X < 600.0 || CA.Box.GetSize().Y < 500.0)
		{
			continue;
		}
		for (int32 j = i + 1; j < M.GetComps().Num(); ++j)
		{
			const FBoardComp& CB = M.GetComps()[j];
			if (CB.Deck != 8 || CB.Kind == TEXT("corridor") || CB.Box.GetSize().X < 600.0 || CB.Box.GetSize().Y < 500.0 || !CA.Box.ExpandBy(30.0).Intersect(CB.Box) || CA.Box.Intersect(CB.Box))
			{
				continue;
			}
			bool bDoorBetween = false;
			for (const int32 Pi : CA.Portals)
			{
				bDoorBetween |= M.GetPortals()[Pi].A == j || M.GetPortals()[Pi].B == j;
			}
			if (!bDoorBetween)
			{
				Ra = i;
				Rb = j;
				break;
			}
		}
	}
	if (Ra != INDEX_NONE && Rb != INDEX_NONE)
	{
		bRoomToRoom = M.Visible(M.CentreOf(Ra) + FVector(0, 0, 150), M.CentreOf(Rb) + FVector(0, 0, 150), nullptr);
		BNote(FString::Printf(TEXT("two rooms that share a wall: %s and %s"), *M.Describe(Ra), *M.Describe(Rb)));
	}
	// a room and the corridor beside it, every door shut: a wall (the first room of Deck 8 with a door to a corridor)
	int32 Kit = INDEX_NONE, Spine = INDEX_NONE;
	for (int32 i = 0; i < M.GetComps().Num() && Kit == INDEX_NONE; ++i)
	{
		const FBoardComp& CA = M.GetComps()[i];
		if (CA.Deck != 8 || CA.Kind == TEXT("corridor") || CA.Box.GetSize().X < 600.0)
		{
			continue;
		}
		for (const int32 Pi : CA.Portals)
		{
			const FBoardPortal& P = M.GetPortals()[Pi];
			const int32 O = P.A == i ? P.B : P.A;
			if (P.bDoor() && !P.bVertical() && M.GetComps()[O].Kind == TEXT("corridor") && M.GetComps()[O].Box.GetSize().GetMax() > 1500.0)
			{
				Kit = i;
				Spine = O;
				break;
			}
		}
	}
	if (Kit != INDEX_NONE && Spine != INDEX_NONE)
	{
		const FVector Inside = M.CentreOf(Kit) + FVector(0, 0, 150), Out = M.CentreOf(Spine) + FVector(0, 0, 150);
		const bool bDoorsOpen = M.Visible(Inside, Out, nullptr);
		bWall = !M.Visible(Inside, Out, &Shut);                            // every door shut: a wall
		BNote(FString::Printf(TEXT("%s sees %s with the doors open: %s, with them shut: %s"), *M.Describe(Kit), *M.Describe(Spine), bDoorsOpen ? TEXT("yes") : TEXT("no"), !bWall ? TEXT("yes") : TEXT("no")));
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
			const bool bM = R.Outcome == EOutcome::AttackerTakes || (R.MandateAble > 0 && R.AquilaAble == 0);
			const bool bA = R.Outcome == EOutcome::DefenderHolds || R.Outcome == EOutcome::AttackerRepelled;
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

static FBoardFight RunBoarding(FRig& Rig, int32 Seed, int32 Boarders, int32 Duty, int32 Qrf, const TCHAR* BreachId, const TCHAR* ObjectiveId, bool bSealed, float MusterS,
                               const TFunction<void(FAstraBoardSim&)>& PerSecond = nullptr, int32 CaptainComp = INDEX_NONE)
{
	FBoardFight F;
	const int32 Breach = Rig.Comp(BreachId), Obj = Rig.Comp(ObjectiveId);
	if (Breach == INDEX_NONE || Obj == INDEX_NONE || Rig.Comp(*BenchArmory(Rig)) == INDEX_NONE)
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
	const int32 Armory = Rig.Comp(*BenchArmory(Rig));
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
	if (CaptainComp != INDEX_NONE)
	{
		Sim.AddCaptain(M.CentreOf(CaptainComp));
	}
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
	F.R = RunSim(Sim, 600.0, PerSecond);
	F.FirstContact = F.R.Book.FirstContactT;
	return F;
}

static int32 GSetup = -1;
static int32 GBoarders = 0;                       // -boarders=N: the infantry-order scenarios run with this many Mandate boarders only (a trace's)

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
			const FBoardFight F = RunBoarding(Rig, Seed + s, Boarders > 0 && si == 0 ? Boarders : S.Boarders, S.Duty, S.Qrf, *BenchBreach(Rig), TEXT("engineering"), S.bSealed, S.Muster);
			if (!F.bFound)
			{
				continue;
			}
			++Found;
			Wins[F.R.Outcome == EOutcome::DefenderHolds ? 0 : F.R.Outcome == EOutcome::AttackerRepelled ? 1 : F.R.Outcome == EOutcome::AttackerTakes ? 2 : 3]++;
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

// ================================================================================================================== the marines' orders

/** What the commander's orders do to the fight (docs/ABBORDAGGI.md): the same boarding fought again, with the same seeds, under the orders the Major would give at the times he would give
 *  them. The drill alone is the baseline; an order is a tool, and a tool that makes the marines worse than the drill is a cost the mind must know. Also checks that every task runs: a
 *  hold, an advance, an assault, a fall back reach their places, 'follow' gathers the squads round the Captain, 'stand down' gives them back to the drill. */
static void BoardScenarioOrders(FRig& Rig, int32 Seed, int32 Seeds)
{
	const int32 Obj = Rig.Comp(TEXT("engineering")), Breach = Rig.Comp(*BenchBreach(Rig)), Armory = Rig.Comp(*BenchArmory(Rig)), Lane = Rig.Comp(TEXT("d8_sp1_C4"));
	if (Obj == INDEX_NONE || Breach == INDEX_NONE || Armory == INDEX_NONE || Lane == INDEX_NONE)
	{
		BCheck("orders", false, TEXT("rooms not found in the plan"));
		return;
	}
	const FAstraBoardMap& M = *Rig.Map;
	TArray<int32> In;                                          // the rooms that open onto Main Engineering: where a squad can hold the way in
	for (const FBoardPortal& P : M.GetPortals())
	{
		const int32 O = P.A == Obj ? P.B : (P.B == Obj ? P.A : INDEX_NONE);
		if (O != INDEX_NONE && !In.Contains(O))
		{
			In.Add(O);
		}
	}
	if (In.IsEmpty())
	{
		BCheck("orders", false, TEXT("Main Engineering has no way in"));
		return;
	}
	BNote(FString::Printf(TEXT("%d ways into Main Engineering; the breach is %s"), In.Num(), *M.Describe(Breach)));
	const auto Each = [](FAstraBoardSim& S, const TFunction<void(const FSquad&, int32 Index)>& F, bool bReactionOnly)
	{
		int32 I = 0;
		for (const FSquad& Sq : S.Squads())
		{
			if (Sq.Side == ESide::Aquila && (!bReactionOnly || Sq.Name.StartsWith(TEXT("Reaction"))))
			{
				F(Sq, I++);
			}
		}
	};
	const auto Give = [&M](FAstraBoardSim& S, const FSquad& Sq, ETask T, int32 Comp) { S.Order(Sq.Id, T, Comp, M.CentreOf(Comp), 800.f, TEXT("bench")); };
	struct FPlan
	{
		const TCHAR* Name;
		TFunction<void(FAstraBoardSim&, int32)> Act;         // every second of the fight, with the second
	};
	const FPlan Plans[] = {
		{TEXT("the drill alone"), nullptr},
		{TEXT("the reaction team holds the ways into Engineering (at 20 s)"), [&](FAstraBoardSim& S, int32 T)
			{
				if (T == 20) { Each(S, [&](const FSquad& Sq, int32 I) { Give(S, Sq, ETask::Hold, In[I % In.Num()]); }, true); }
			}},
		{TEXT("every squad holds the ways into Engineering (at 20 s)"), [&](FAstraBoardSim& S, int32 T)
			{
				if (T == 20) { Each(S, [&](const FSquad& Sq, int32 I) { Give(S, Sq, ETask::Hold, In[I % In.Num()]); }, false); }
			}},
		{TEXT("every squad advances on the breach (at 80 s)"), [&](FAstraBoardSim& S, int32 T)
			{
				if (T == 80) { Each(S, [&](const FSquad& Sq, int32) { Give(S, Sq, ETask::Advance, Breach); }, false); }
			}},
		{TEXT("every squad assaults the breach (at 80 s)"), [&](FAstraBoardSim& S, int32 T)
			{
				if (T == 80) { Each(S, [&](const FSquad& Sq, int32) { Give(S, Sq, ETask::Assault, Breach); }, false); }
			}},
		{TEXT("every squad falls back to the armory (at 100 s)"), [&](FAstraBoardSim& S, int32 T)
			{
				if (T == 100) { Each(S, [&](const FSquad& Sq, int32) { Give(S, Sq, ETask::FallBack, Armory); }, false); }
			}},
		{TEXT("held at the ways in at 20 s, given back to the drill at 70 s"), [&](FAstraBoardSim& S, int32 T)
			{
				if (T == 20) { Each(S, [&](const FSquad& Sq, int32 I) { Give(S, Sq, ETask::Hold, In[I % In.Num()]); }, false); }
				if (T == 70) { Each(S, [&](const FSquad& Sq, int32) { S.Respond(Sq.Id); }, false); }
			}},
	};
	TSharedRef<FJsonObject> Rec = MakeShared<FJsonObject>();
	int32 Bad = 0, Hung = 0;
	for (int32 Boarders : {10, 20})
	{
		BNote(FString::Printf(TEXT("%d boarders, sealed, the watch and the reaction team (the same %d seeds for every plan):"), Boarders, Seeds));
		for (int32 pi = 0; pi < UE_ARRAY_COUNT(Plans); ++pi)
		{
			int32 Wins[4] = {0, 0, 0, 0};
			double T = 0.0, LossA = 0.0, LossM = 0.0;
			for (int32 s = 0; s < Seeds; ++s)
			{
				const FPlan& P = Plans[pi];
				const TFunction<void(FAstraBoardSim&)> Hook = P.Act ? TFunction<void(FAstraBoardSim&)>([&P](FAstraBoardSim& S) { P.Act(S, FMath::RoundToInt(S.Time())); }) : nullptr;
				const FBoardFight F = RunBoarding(Rig, Seed + s, Boarders, 24, 12, *BenchBreach(Rig), TEXT("engineering"), true, 25.f, Hook);
				Wins[F.R.Outcome == EOutcome::DefenderHolds ? 0 : F.R.Outcome == EOutcome::AttackerRepelled ? 1 : F.R.Outcome == EOutcome::AttackerTakes ? 2 : 3]++;
				T += F.R.T;
				LossA += F.R.Book.Killed[0] + F.R.Book.Down[0];
				LossM += F.R.Book.Killed[1] + F.R.Book.Down[1];
				Bad += F.R.BadPos;
			}
			Hung += Wins[3];
			BNote(FString::Printf(TEXT("    %-66s the marines hold %2d, the Mandate break off %2d, the Mandate take Engineering %2d, no end %d; ends at %3.0f s; marines lost %4.1f, Mandate %4.1f"),
			                      Plans[pi].Name, Wins[0], Wins[1], Wins[2], Wins[3], T / Seeds, LossA / Seeds, LossM / Seeds));
			TSharedRef<FJsonObject> O = MakeShared<FJsonObject>();
			O->SetNumberField(TEXT("boarders"), Boarders);
			O->SetStringField(TEXT("plan"), Plans[pi].Name);
			O->SetNumberField(TEXT("holds"), Wins[0]);
			O->SetNumberField(TEXT("repelled"), Wins[1]);
			O->SetNumberField(TEXT("takes"), Wins[2]);
			O->SetNumberField(TEXT("end_s"), T / Seeds);
			O->SetNumberField(TEXT("loss_marines"), LossA / Seeds);
			Rec->SetObjectField(FString::Printf(TEXT("b%d_plan%d"), Boarders, pi), O);
		}
	}
	BCheck("orders: nobody leaves the plan", Bad == 0, FString::Printf(TEXT("%d positions off the plan under every order"), Bad));
	BCheck("orders: every fight ends", Hung == 0, FString::Printf(TEXT("%d fights with no end in 600 s under any order"), Hung));
	// 'follow': the squads gather round the Captain wherever he stands (a corridor on Deck 8), and a fight goes on round him
	{
		const int32 Marks[] = {30, 50, 70, 90};
		double Near[UE_ARRAY_COUNT(Marks)] = {0.0, 0.0, 0.0, 0.0}, All[UE_ARRAY_COUNT(Marks)] = {0.0, 0.0, 0.0, 0.0};
		for (int32 s = 0; s < FMath::Min(Seeds, 8); ++s)
		{
			const TFunction<void(FAstraBoardSim&)> Hook = [&](FAstraBoardSim& S)
			{
				const int32 T = FMath::RoundToInt(S.Time());
				if (T == 10)
				{
					Each(S, [&](const FSquad& Sq, int32) { S.Order(Sq.Id, ETask::Follow, INDEX_NONE, FVector::ZeroVector, 0.f, TEXT("bench")); }, false);
				}
				for (int32 k = 0; k < UE_ARRAY_COUNT(Marks); ++k)
				{
					if (T == Marks[k])
					{
						const FUnit* C = S.Unit(S.CaptainId());
						for (const FUnit& U : S.Units())
						{
							if (C && U.Side == ESide::Aquila && !U.bExternal && U.Able())
							{
								All[k] += 1.0;
								Near[k] += FVector::Dist2D(U.Pos, C->Pos) < 1500.0 ? 1.0 : 0.0;
							}
						}
					}
				}
			};
			RunBoarding(Rig, Seed + s, 4, 24, 12, *BenchBreach(Rig), TEXT("engineering"), true, 25.f, Hook, Lane);
		}
		FString Row;
		for (int32 k = 0; k < UE_ARRAY_COUNT(Marks); ++k)
		{
			Row += FString::Printf(TEXT("%s%.0f%% at %d s"), k ? TEXT(", ") : TEXT(""), All[k] > 0.0 ? 100.0 * Near[k] / All[k] : 0.0, Marks[k]);
		}
		BNote(FString::Printf(TEXT("follow, ordered at 10 s: the able marines within 15 m of the Captain: %s"), *Row));
		const int32 Last = UE_ARRAY_COUNT(Marks) - 1;
		BCheck("orders: follow gathers the squads", All[Last] > 0.0 && Near[Last] >= 0.8 * All[Last], FString::Printf(TEXT("%.0f of %.0f able marines within 15 m of the Captain %d s after the order"), Near[Last], All[Last], Marks[Last] - 10));
	}
	// a Captain who falls: the two squads nearest to him go to him by the drill alone (no order) and stay round him, and it is told once
	{
		const int32 Tries = FMath::Min(Seeds, 8);
		double Near = 0.0;
		int32 Told = 0;
		for (int32 s = 0; s < Tries; ++s)
		{
			double InCircle = 0.0;
			const TFunction<void(FAstraBoardSim&)> Hook = [&](FAstraBoardSim& S)
			{
				const int32 T = FMath::RoundToInt(S.Time());
				const FUnit* C = S.Unit(S.CaptainId());
				if (T == 25 && C)
				{
					S.SetCaptain(C->Pos, C->Yaw, true, 0.f, true);
				}
				if (T == 75 && C)
				{
					for (const FUnit& U : S.Units())
					{
						InCircle += (U.Side == ESide::Aquila && !U.bExternal && U.Able() && FVector::Dist2D(U.Pos, C->Pos) < 800.0) ? 1.0 : 0.0;
					}
				}
			};
			const FBoardFight F = RunBoarding(Rig, Seed + s, 4, 24, 12, *BenchBreach(Rig), TEXT("engineering"), true, 25.f, Hook, Lane);
			Near += InCircle;
			Told += F.R.Book.Rescues > 0 ? 1 : 0;
		}
		BNote(FString::Printf(TEXT("the Captain falls at 25 s: %.1f able marines within 8 m of him 50 s later, the rescue told in %d of %d fights"), Near / Tries, Told, Tries));
		BCheck("orders: a fallen Captain is reached", Near / Tries >= 6.0 && Told >= (Tries + 1) / 2, FString::Printf(TEXT("%.1f marines round him, told in %d of %d"), Near / Tries, Told, Tries));
	}
	BRecord->SetObjectField(TEXT("orders"), Rec);
}


// ================================================================================================================== the infantry orders (ABBORDAGGI-4)

namespace
{
	/** A room the drills are tried in: its doors, the compartment outside each, and a spot about eighteen metres of way from each door where a squad starts. */
	struct FArena
	{
		int32 Room = INDEX_NONE;
		TArray<int32> Doors;              // portal indices
		TArray<int32> Outside;            // compartments
		TArray<FVector> Starts;
	};

	/** About 18 m of way from a door, outside the room, through corridors only. */
	bool ArenaStart(const FAstraBoardMap& M, int32 DoorPortal, int32 Room, FVector& OutStart, float MinM = 14.f, float MaxM = 26.f)
	{
		const FBoardPortal& P = M.GetPortals()[DoorPortal];
		const int32 C0 = P.Other(Room);
		const FVector DoorPos = P.PosIn(C0);
		TArray<int32> Frontier;
		Frontier.Add(C0);
		TSet<int32> Seen;
		Seen.Add(C0);
		Seen.Add(Room);
		for (int32 Depth = 0; Depth < 6; ++Depth)
		{
			TArray<int32> Next;
			for (const int32 C : Frontier)
			{
				for (const int32 Pi : M.GetComps()[C].Portals)
				{
					const FBoardPortal& Q = M.GetPortals()[Pi];
					const int32 O = Q.Other(C);
					if (Q.bVertical() || Seen.Contains(O))
					{
						continue;
					}
					Seen.Add(O);
					Next.Add(O);
					const FVector At = M.Inset(O, M.CentreOf(O), 90.f);
					TArray<FVector> Pts;
					float Metres = 0.f;
					FBoardRouteOptions Opt;
					if (M.Route(At, DoorPos, Pts, Opt, &Metres) && Metres >= MinM && Metres <= MaxM && M.GetComps()[O].Deck == M.GetComps()[Room].Deck)
					{
						OutStart = At;
						return true;
					}
				}
			}
			Frontier = Next;
		}
		return false;
	}

	/** Rooms with exactly NumDoors doors (open portals and stairs do not count, nor does a bulkhead), at least 5 x 5 m, with a corridor outside each and room for a squad to start; the first MaxCount in the plan's order. */
	void FindArenas(const FAstraBoardMap& M, int32 NumDoors, int32 MaxCount, TArray<FArena>& Out)
	{
		Out.Reset();
		for (int32 R = 0; R < M.GetComps().Num() && Out.Num() < MaxCount; ++R)
		{
			const FBoardComp& C = M.GetComps()[R];
			if (C.bCorridor || C.Box.GetSize().X < 500.0 || C.Box.GetSize().Y < 500.0 || (NumDoors == 1 && (C.bHall || C.Box.GetSize().X > 1600.0 || C.Box.GetSize().Y > 1600.0)) || C.Box.GetSize().X > 4200.0 || C.Box.GetSize().Y > 4200.0)
			{
				continue;
			}
			FArena A;
			A.Room = R;
			bool bOk = true;
			for (const int32 Pi : C.Portals)
			{
				const FBoardPortal& P = M.GetPortals()[Pi];
				const int32 O = P.Other(R);
				if (P.Kind != FBoardPortal::EKind::Door || (!M.GetComps()[O].bCorridor && !M.GetComps()[O].bHall))
				{
					if (NumDoors == 1)
					{
						bOk = false;                          // one door and nothing else: an open side, a stair, a bulkhead is not that
						break;
					}
					continue;                                 // (a room with several ways in: the arena's doors are the doors to corridors)
				}
				if (NumDoors == 2 && A.Outside.Contains(O))
				{
					continue;                                 // (two doors onto two different corridors)
				}
				A.Doors.Add(Pi);
				A.Outside.Add(O);
			}
			if (!bOk || A.Doors.Num() < NumDoors)
			{
				continue;
			}
			A.Doors.SetNum(NumDoors);
			A.Outside.SetNum(NumDoors);
			for (int32 d = 0; d < A.Doors.Num() && bOk; ++d)
			{
				FVector S = FVector::ZeroVector;
				bOk = d == 0 ? ArenaStart(M, A.Doors[d], R, S) : ArenaStart(M, A.Doors[d], R, S, 32.f, 48.f);       // (the second squad is further from its door: the sync's reason)
				A.Starts.Add(S);
			}
			if (bOk && (NumDoors < 2 || FVector::Dist2D(A.Starts[0], A.Starts[1]) > 800.0))
			{
				Out.Add(A);
			}
		}
	}

	/** Men of a squad round a spot, a metre and a half apart (inside the compartment). */
	TArray<int32> MakeMen(FAstraBoardSim& Sim, const FAstraBoardMap& M, ESide Side, const FString& Squad, int32 N, const FVector& At, const TCHAR* Prefix, int32& Counter)
	{
		TArray<int32> Ids;
		const int32 Sq = Sim.AddSquad(Side, Squad);
		const int32 Comp = M.CompAt(At, 60.f);
		for (int32 k = 0; k < N; ++k)
		{
			const FVector P = M.Inset(Comp, At + FVector((k % 3) * 120.0 - 120.0, (k / 3) * 120.0 - 60.0, 0.0), 60.f);
			const ERole Role = k == 0 ? ERole::Leader : ERole::Rifleman;
			Ids.Add(Sim.AddUnit(Side, Role, FString::Printf(TEXT("%s %d"), Prefix, ++Counter), P, Sq));
		}
		return Ids;
	}

	struct FDrillResult
	{
		bool bTaken = false;
		double T = 0.0;
		int32 MarinesLost = 0, FoesLost = 0, MarinesAble = 0;
		int32 Rooms = 0, Entries = 0;
	};

	/** What a fight came to, for a table. */
	struct FDrillTable
	{
		int32 N = 0, Taken = 0;
		double T = 0.0, MarinesLost = 0.0, FoesLost = 0.0, Rooms = 0.0;
		void Add(const FDrillResult& R)
		{
			++N;
			Taken += R.bTaken ? 1 : 0;
			T += R.T;
			MarinesLost += R.MarinesLost;
			FoesLost += R.FoesLost;
			Rooms += R.Rooms;
		}
		FString Text() const
		{
			const double Nn = FMath::Max(1, N);
			return FString::Printf(TEXT("taken %2d of %2d, in %5.1f s, marines lost %4.1f, enemy lost %4.1f"), Taken, N, T / Nn, MarinesLost / Nn, FoesLost / Nn);
		}
	};

	TMap<FString, FDrillTable> GDrillTabs;                       // what the infantry orders' scenarios measured, by name (the checks at the end of each compare them)
	TMap<FString, double> GDrillNums;

	FDrillResult DrillResultOf(const FAstraBoardSim& Sim, const FRunResult& R)
	{
		FDrillResult D;
		D.bTaken = R.Outcome == EOutcome::AttackerTakes;
		D.T = R.T;
		D.MarinesLost = R.Book.Killed[0] + R.Book.Down[0];
		D.FoesLost = R.Book.Killed[1] + R.Book.Down[1];
		D.MarinesAble = R.AquilaAble;
		D.Rooms = R.Book.DrillRooms;
		D.Entries = R.Book.DrillEntries;
		(void)Sim;
		return D;
	}
}

/** Take: the marines (two squads of six, or one) take a room held by Mandate soldiers. The default drill walks in; the order stacks at the door and goes in together. Against guards who are at their posts
 *  (not alerted, spread about the room) and against guards who hold the door (alerted, in the corners beside it), with one door and with two (a sync: both squads in at the one moment). */
static void BoardScenarioTake(FRig& Rig, int32 Seed, int32 Seeds)
{
	TArray<FArena> One, Two;
	FindArenas(*Rig.Map, 1, 6, One);
	FindArenas(*Rig.Map, 2, 6, Two);
	if (One.IsEmpty() || Two.IsEmpty())
	{
		// what the rooms are like, for the arena's rule
		TMap<FString, int32> Hist;
		for (int32 R = 0; R < Rig.Map->GetComps().Num(); ++R)
		{
			const FBoardComp& C = Rig.Map->GetComps()[R];
			if (C.bCorridor || C.bHall || C.Box.GetSize().X < 500.0 || C.Box.GetSize().Y < 500.0)
			{
				continue;
			}
			int32 Doors = 0, Open = 0, Blast = 0, Vert = 0, Corr = 0;
			for (const int32 Pi : C.Portals)
			{
				const FBoardPortal& P = Rig.Map->GetPortals()[Pi];
				Doors += P.Kind == FBoardPortal::EKind::Door ? 1 : 0;
				Open += P.Kind == FBoardPortal::EKind::Open ? 1 : 0;
				Blast += P.Kind == FBoardPortal::EKind::Blast ? 1 : 0;
				Vert += P.bVertical() ? 1 : 0;
				Corr += (Rig.Map->GetComps()[P.Other(R)].bCorridor || Rig.Map->GetComps()[P.Other(R)].bHall) ? 1 : 0;
			}
			Hist.FindOrAdd(FString::Printf(TEXT("doors %d open %d blast %d vert %d, %d to corridors"), Doors, Open, Blast, Vert, Corr)) += 1;
		}
		Hist.ValueSort([](int32 A, int32 B) { return A > B; });
		int32 Shown = 0;
		for (const TPair<FString, int32>& KV : Hist)
		{
			BNote(FString::Printf(TEXT("%5d rooms: %s"), KV.Value, *KV.Key));
			if (++Shown >= 14)
			{
				break;
			}
		}
		BCheck("take: arenas", false, TEXT("no room with one door / with two doors found in the plan"));
		return;
	}
	BNote(FString::Printf(TEXT("%d rooms with one door, %d with two; the first of each: %s, %s"), One.Num(), Two.Num(), *Rig.Map->Describe(One[0].Room), *Rig.Map->Describe(Two[0].Room)));
	const FAstraBoardMap& M = *Rig.Map;
	struct FMode { const TCHAR* Name; int32 Kind; };                    // 0 the drill alone, 1 take, 2 take with a sync (two doors)
	const FMode Modes[] = {{TEXT("the drill alone (walks in)"), 0}, {TEXT("take: stack, in together"), 1}};
	for (const bool bPrepared : {false, true})
	{
		for (const int32 Doors : {1, 2})
		{
			const TArray<FArena>& Arenas = Doors == 1 ? One : Two;
			const int32 NGuards = Doors == 1 ? 6 : 10;
			BNote(FString::Printf(TEXT("%s guards (%s), %d door%s, %d marines against %d guards, %d rooms x %d seeds:"), bPrepared ? TEXT("alerted") : TEXT("unalerted"),
			                      bPrepared ? TEXT("in the corners beside the door") : TEXT("at their posts about the room"), Doors, Doors == 1 ? TEXT("") : TEXT("s"), Doors == 1 ? 6 : 12, NGuards, FMath::Min(Arenas.Num(), GTrace ? 1 : 4), Seeds));
			for (const FMode& Mode : Modes)
			{
				for (const int32 Sync : (Doors == 2 && Mode.Kind == 1) ? TArray<int32>({0, 1}) : TArray<int32>({0}))
				{
					FDrillTable Tab;
					for (int32 ai = 0; ai < FMath::Min(Arenas.Num(), GTrace ? 1 : 4); ++ai)
					{
						const FArena& A = Arenas[ai];
						for (int32 s = 0; s < Seeds; ++s)
						{
							FAstraBoardSim Sim;
							Sim.Init(Rig.Map.ToSharedRef(), Seed + s * 13 + ai);
							Sim.Tuning = Rig.Tuning;
							Sim.Tuning.bShipSensors = false;
							Sim.Tuning.HoldS = 5.f;
							FRandomStream Rng(Seed + s * 7 + ai * 101);
							const FVector Door0 = M.GetPortals()[A.Doors[0]].PosIn(A.Room);
							Sim.SetMission(ESide::Aquila, A.Outside[0], A.Starts[0], A.Room, false);
							// the guards: six men
							int32 Counter = 0;
							const int32 Gs = Sim.AddSquad(ESide::Mandate, TEXT("Guard"));
							TArray<int32> Guards;
							for (int32 k = 0; k < NGuards; ++k)
							{
								const FVector P = bPrepared ? M.Inset(A.Room, Door0, 90.f) : M.Inset(A.Room, M.CentreOf(A.Room) + FVector(Rng.FRandRange(-250.f, 250.f), Rng.FRandRange(-250.f, 250.f), 0.f), 80.f);
								Guards.Add(Sim.AddUnit(ESide::Mandate, k == 0 ? ERole::Leader : ERole::Rifleman, FString::Printf(TEXT("Guard %d"), ++Counter), P, Gs));
							}
							if (bPrepared)
							{
								FOrder O;
								O.Task = ETask::Hold;
								O.Comp = A.Room;
								O.Pos = M.CentreOf(A.Room);
								O.Radius = 400.f;
								O.bInside = true;
								Sim.OrderEx(Gs, O);
								Sim.Tuning.bShipSensors = false;
							}
							else
							{
								Sim.Order(Gs, ETask::Idle, A.Room, M.CentreOf(A.Room), 0.f, TEXT("at their posts"));
							}
							// the marines: six a door
							TArray<int32> Squads;
							for (int32 d = 0; d < Doors; ++d)
							{
								const int32 Before = Sim.Squads().Num();
								MakeMen(Sim, M, ESide::Aquila, FString::Printf(TEXT("Boarding %c"), TEXT('A') + d), 6, A.Starts[d], TEXT("Marine"), Counter);
								Squads.Add(Before);
							}
							for (const int32 Sq : Squads)
							{
								if (Mode.Kind == 0)
								{
									Sim.BriefAttackers(Sq);
								}
								else
								{
									FOrder O;
									O.Task = ETask::Take;
									O.Comp = A.Room;
									O.Pos = M.CentreOf(A.Room);
									O.Sync = Sync ? 1 : 0;
									O.Where = M.Describe(A.Room);
									Sim.OrderEx(Sq, O);
								}
							}
							const FRunResult R = RunSim(Sim, 150.0);
							Tab.Add(DrillResultOf(Sim, R));
						}
					}
					BNote(FString::Printf(TEXT("    %-34s %s"), Mode.Kind == 1 && Doors == 2 ? (Sync ? TEXT("take, both doors, one sync") : TEXT("take, each door by itself")) : Mode.Name, *Tab.Text()));
					GDrillTabs.Add(FString::Printf(TEXT("take/%d/%d/%d/%d"), bPrepared ? 1 : 0, Doors, Mode.Kind, Sync), Tab);
				}
			}
		}
	}
	// the order must be worth something: more rooms taken than by walking in, for no more marines lost
	const auto T = [](int32 Prep, int32 Dr, int32 Kind, int32 Sync) -> const FDrillTable* { return GDrillTabs.Find(FString::Printf(TEXT("take/%d/%d/%d/%d"), Prep, Dr, Kind, Sync)); };
	const FDrillTable *W0 = T(0, 1, 0, 0), *K0 = T(0, 1, 1, 0), *W1 = T(1, 1, 0, 0), *K1 = T(1, 1, 1, 0), *Wd = T(0, 2, 0, 0), *Kd = T(0, 2, 1, 0), *Ks = T(0, 2, 1, 1);
	if (W0 && K0 && W1 && K1 && Wd && Kd && Ks)
	{
		BCheck("take: stacking and going in together beats walking in (one door)", K0->Taken > W0->Taken && K1->Taken > W1->Taken && K0->MarinesLost <= W0->MarinesLost && K1->MarinesLost <= W1->MarinesLost,
		       FString::Printf(TEXT("unalerted guards: %d of %d against %d walking in, %.1f marines lost against %.1f; alerted: %d against %d, %.1f against %.1f"), K0->Taken, K0->N, W0->Taken, K0->MarinesLost / FMath::Max(1, K0->N),
		                       W0->MarinesLost / FMath::Max(1, W0->N), K1->Taken, W1->Taken, K1->MarinesLost / FMath::Max(1, K1->N), W1->MarinesLost / FMath::Max(1, W1->N)));
		BCheck("take: a sync takes the room with two doors at least as often as each door by itself, and more than walking in", Ks->Taken >= Kd->Taken && Kd->Taken > Wd->Taken,
		       FString::Printf(TEXT("two doors, unalerted guards: sync %d, each by itself %d, walking in %d of %d; %.0f s, %.0f s, %.0f s"), Ks->Taken, Kd->Taken, Wd->Taken, Ks->N, Ks->T / FMath::Max(1, Ks->N), Kd->T / FMath::Max(1, Kd->N), Wd->T / FMath::Max(1, Wd->N)));
	}
}

/** Breach: a sealed pressure bulkhead between the marines and four Mandate soldiers in the corridor beyond. The default drill waits at it while its men cut through with torches (CutS, quietly); the order
 *  stacks, sets a charge (nine seconds, and the men near the door beyond hear it and are stunned by it) and goes in. */
static void BoardScenarioBreach(FRig& Rig, int32 Seed, int32 Seeds)
{
	const FAstraBoardMap& M = *Rig.Map;
	TArray<int32> Blasts;
	for (int32 i = 0; i < M.GetPortals().Num() && Blasts.Num() < 4; ++i)
	{
		const FBoardPortal& P = M.GetPortals()[i];
		if (P.Kind == FBoardPortal::EKind::Blast && M.GetComps()[P.A].bCorridor && M.GetComps()[P.B].bCorridor && M.GetComps()[P.A].Deck == M.GetComps()[P.B].Deck
		    && M.GetComps()[P.A].Box.GetSize().GetMax() > 1200.0 && M.GetComps()[P.B].Box.GetSize().GetMax() > 1200.0)
		{
			Blasts.Add(i);
		}
	}
	if (Blasts.IsEmpty())
	{
		BCheck("breach: arenas", false, TEXT("no pressure bulkhead between two corridors in the plan"));
		return;
	}
	BNote(FString::Printf(TEXT("%d bulkheads between corridors; the first: %s | %s"), Blasts.Num(), *M.Describe(M.GetPortals()[Blasts[0]].A), *M.Describe(M.GetPortals()[Blasts[0]].B)));
	for (const bool bAlerted : {false, true})
	{
		BNote(FString::Printf(TEXT("a sealed bulkhead, six marines, four guards %s beyond it, %d bulkheads x %d seeds:"), bAlerted ? TEXT("alerted, in the corners") : TEXT("at their posts"), Blasts.Num(), Seeds));
		for (const int32 Mode : {0, 1})
		{
			FDrillTable Tab;
			double Through = 0.0;
			int32 Counted = 0;
			for (int32 bi = 0; bi < Blasts.Num(); ++bi)
			{
				const FBoardPortal& P = M.GetPortals()[Blasts[bi]];
				for (int32 s = 0; s < Seeds; ++s)
				{
					FAstraBoardSim Sim;
					Sim.Init(Rig.Map.ToSharedRef(), Seed + s * 17 + bi);
					Sim.Tuning = Rig.Tuning;
					Sim.Tuning.bShipSensors = false;
					Sim.Tuning.HoldS = 5.f;
					FRandomStream Rng(Seed + s * 5 + bi * 77);
					// the marines on side A (about 12 m from the door, along its corridor), the guards on side B (4 to 9 m beyond it)
					const FVector DoorA = P.PosIn(P.A), DoorB = P.PosIn(P.B);
					const FVector2D Away(-P.Normal.X, -P.Normal.Y);                    // from the door into A
					FVector Start = M.Inset(P.A, DoorA + FVector(Away.X, Away.Y, 0.0) * 1200.0, 80.f);
					Sim.SetMission(ESide::Aquila, P.A, Start, P.B, false);
					Sim.SealDoor(P.Door, true);
					int32 Counter = 0;
					const int32 Gs = Sim.AddSquad(ESide::Mandate, TEXT("Guard"));
					for (int32 k = 0; k < 4; ++k)
					{
						const FVector At = M.Inset(P.B, DoorB + FVector(-Away.X, -Away.Y, 0.0) * Rng.FRandRange(400.f, 900.f) + FVector(Rng.FRandRange(-60.f, 60.f), Rng.FRandRange(-60.f, 60.f), 0.0), 70.f);
						Sim.AddUnit(ESide::Mandate, k == 0 ? ERole::Leader : ERole::Rifleman, FString::Printf(TEXT("Guard %d"), ++Counter), At, Gs);
					}
					if (bAlerted)
					{
						FOrder O;
						O.Task = ETask::Hold;
						O.Comp = P.B;
						O.Pos = DoorB;
						O.Radius = 600.f;
						Sim.OrderEx(Gs, O);
					}
					else
					{
						Sim.Order(Gs, ETask::Idle, P.B, DoorB, 0.f, TEXT("at their posts"));
					}
					const int32 Sq = Sim.Squads().Num();
					MakeMen(Sim, M, ESide::Aquila, TEXT("Boarding A"), 6, Start, TEXT("Marine"), Counter);
					if (Mode == 0)
					{
						Sim.BriefAttackers(Sq);
					}
					else
					{
						FOrder O;
						O.Task = ETask::Breach;
						O.Comp = P.B;
						O.Pos = DoorB;
						O.Door = P.Door;
						O.Where = M.Describe(P.B);
						Sim.OrderEx(Sq, O);
					}
					double TCut = -1.0;
					const FRunResult R = RunSim(Sim, 120.0, [&](FAstraBoardSim& S)
					{
						if (TCut < 0.0 && !S.IsDoorSealed(P.Door))
						{
							TCut = S.Time();
						}
					});
					Tab.Add(DrillResultOf(Sim, R));
					if (TCut >= 0.0)
					{
						Through += TCut;
						++Counted;
					}
				}
			}
			BNote(FString::Printf(TEXT("    %-30s %s; the bulkhead open at %4.1f s"), Mode == 0 ? TEXT("the drill alone (torches)") : TEXT("breach: stack, charge, in"), *Tab.Text(), Counted ? Through / Counted : -1.0));
			GDrillTabs.Add(FString::Printf(TEXT("breach/%d/%d"), bAlerted ? 1 : 0, Mode), Tab);
			GDrillNums.Add(FString::Printf(TEXT("breach/%d/%d/open"), bAlerted ? 1 : 0, Mode), Counted ? Through / Counted : -1.0);
		}
	}
	const FDrillTable *Tw = GDrillTabs.Find(TEXT("breach/0/0")), *Tb = GDrillTabs.Find(TEXT("breach/0/1")), *Aw = GDrillTabs.Find(TEXT("breach/1/0")), *Ab = GDrillTabs.Find(TEXT("breach/1/1"));
	if (Tw && Tb && Aw && Ab)
	{
		const double OpenW = GDrillNums.FindRef(TEXT("breach/0/0/open")), OpenB = GDrillNums.FindRef(TEXT("breach/0/1/open"));
		BCheck("breach: a charge opens the bulkhead sooner than the torches and the room is taken in less time", OpenB > 0.0 && OpenB + 6.0 < OpenW && Tb->T < Tw->T && Ab->T < Aw->T && Tb->Taken >= Tw->Taken && Ab->Taken >= Aw->Taken,
		       FString::Printf(TEXT("open at %.0f s against %.0f s; room taken in %.0f s against %.0f s (alerted guards: %.0f against %.0f); %d against %d taken"), OpenB, OpenW, Tb->T / FMath::Max(1, Tb->N), Tw->T / FMath::Max(1, Tw->N),
		                       Ab->T / FMath::Max(1, Ab->N), Aw->T / FMath::Max(1, Aw->N), Tb->Taken, Tw->Taken));
	}
}

/** Sweep: a corridor with rooms off it (cabins, offices), two Mandate soldiers at their posts in each of four of them, six marines at one end. The default drill is told to go to the far end of the corridor: it
 *  walks past the doors (each opens as a man comes within two and a half metres) and the men in the rooms see the backs of the column. The order clears the four rooms one after the other (stack, in
 *  together, clear) and leaves nobody behind. */
static void BoardScenarioSweep(FRig& Rig, int32 Seed, int32 Seeds)
{
	const FAstraBoardMap& M = *Rig.Map;
	struct FRow { int32 Corridor; TArray<int32> Rooms; FVector Start, End; };
	TArray<FRow> Rows;
	TSet<int32> UsedRooms;
	for (int32 c = 0; c < M.GetComps().Num() && Rows.Num() < 6; ++c)
	{
		const FBoardComp& C = M.GetComps()[c];
		if (!C.bCorridor)
		{
			continue;
		}
		// the corridor as the men walk it: the chain of corridor compartments that run on from this one through open ways (a module at a time), up to ten of them
		TArray<int32> Chain;
		Chain.Add(c);
		for (int32 i = 0; i < Chain.Num() && Chain.Num() < 10; ++i)
		{
			for (const int32 Pi : M.GetComps()[Chain[i]].Portals)
			{
				const FBoardPortal& P = M.GetPortals()[Pi];
				const int32 O = P.Other(Chain[i]);
				if (P.Kind == FBoardPortal::EKind::Open && M.GetComps()[O].bCorridor && M.GetComps()[O].Deck == C.Deck && !Chain.Contains(O) && Chain.Num() < 10)
				{
					Chain.Add(O);
				}
			}
		}
		TArray<TPair<double, int32>> Rooms;
		for (const int32 Cc : Chain)
		{
			for (const int32 Pi : M.GetComps()[Cc].Portals)
			{
				const FBoardPortal& P = M.GetPortals()[Pi];
				const int32 O = P.Other(Cc);
				const FBoardComp& OC = M.GetComps()[O];
				if (P.Kind == FBoardPortal::EKind::Door && !OC.bCorridor && !OC.bHall && OC.Portals.Num() == 1 && OC.Box.GetSize().X > 350.0 && OC.Box.GetSize().Y > 350.0 && !UsedRooms.Contains(O))
				{
					Rooms.Emplace(FVector::Dist2D(M.CentreOf(c), P.Pos), O);
				}
			}
		}
		if (Rooms.Num() < 4)
		{
			continue;
		}
		Rooms.Sort([](const TPair<double, int32>& A, const TPair<double, int32>& B) { return A.Key < B.Key; });
		FRow Row;
		Row.Corridor = c;
		for (int32 i = 0; i < 4; ++i)
		{
			Row.Rooms.Add(Rooms[i].Value);
			UsedRooms.Add(Rooms[i].Value);
		}
		// start at the first corridor module, finish at the far end of the chain
		int32 Far = c;
		double FarD = 0.0;
		for (const int32 Cc : Chain)
		{
			const double D = FVector::Dist2D(M.CentreOf(Cc), M.CentreOf(c));
			if (D > FarD)
			{
				FarD = D;
				Far = Cc;
			}
		}
		Row.Start = M.Inset(c, M.CentreOf(c), 70.f);
		Row.End = M.Inset(Far, M.CentreOf(Far), 70.f);
		if (FarD > 1500.0)
		{
			Rows.Add(Row);
		}
	}
	if (Rows.IsEmpty())
	{
		BCheck("sweep: arenas", false, TEXT("no corridor with four rooms off it in the plan"));
		return;
	}
	BNote(FString::Printf(TEXT("%d corridors with four rooms off them; the first: %s"), Rows.Num(), *M.Describe(Rows[0].Corridor)));
	for (const int32 Mode : {0, 1})
	{
		FDrillTable Tab;
		double GuardsLeft = 0.0, RoomsClear = 0.0, Done = 0.0;
		int32 Runs = 0;
		for (int32 ri = 0; ri < Rows.Num(); ++ri)
		{
			const FRow& Row = Rows[ri];
			for (int32 s = 0; s < Seeds; ++s)
			{
				FAstraBoardSim Sim;
				Sim.Init(Rig.Map.ToSharedRef(), Seed + s * 19 + ri);
				Sim.Tuning = Rig.Tuning;
				Sim.Tuning.bShipSensors = false;
				FRandomStream Rng(Seed + s * 3 + ri * 61);
				Sim.SetMission(ESide::Aquila, Row.Corridor, Row.Start, Row.Rooms.Last(), false);
				int32 Counter = 0;
				TArray<int32> Guards;
				for (const int32 R : Row.Rooms)
				{
					const int32 Gs = Sim.AddSquad(ESide::Mandate, FString::Printf(TEXT("Post %d"), Guards.Num() / 2 + 1));
					for (int32 k = 0; k < 2; ++k)
					{
						Guards.Add(Sim.AddUnit(ESide::Mandate, k == 0 ? ERole::Leader : ERole::Rifleman, FString::Printf(TEXT("Guard %d"), ++Counter),
						                       M.Inset(R, M.CentreOf(R) + FVector(Rng.FRandRange(-120.f, 120.f), Rng.FRandRange(-120.f, 120.f), 0.0), 70.f), Gs));
					}
					Sim.Order(Gs, ETask::Idle, R, M.CentreOf(R), 0.f, TEXT("at their posts"));
				}
				const int32 Sq = Sim.Squads().Num();
				MakeMen(Sim, M, ESide::Aquila, TEXT("Boarding A"), 6, Row.Start, TEXT("Marine"), Counter);
				if (Mode == 0)
				{
					Sim.Order(Sq, ETask::Advance, Row.Corridor, Row.End, 0.f, TEXT("to the far end"));
				}
				else
				{
					FOrder O;
					O.Task = ETask::Sweep;
					O.Comp = Row.Rooms[0];
					O.Pos = M.CentreOf(Row.Rooms[0]);
					O.Sector = Row.Rooms;
					O.Where = TEXT("the four rooms");
					Sim.OrderEx(Sq, O);
				}
				const FSquad& Squad = Sim.Squads()[Sq];
				double TDone = -1.0;
				const FRunResult R = RunSim(Sim, 110.0, [&](FAstraBoardSim& S)
				{
					// the end: the sweep has swept, or the column has got to the far end (and a few seconds more: what is left behind it fires)
					if (TDone < 0.0 && ((Mode == 1 && Squad.Drill == EDrill::Done) || (Mode == 0 && Squad.Leader != INDEX_NONE && FVector::Dist2D(S.Units()[Squad.Leader].Pos, Row.End) < 600.0)))
					{
						TDone = S.Time();
					}
					if (TDone >= 0.0 && S.Time() > TDone + 8.0)
					{
						S.MissionMutable().Outcome = EOutcome::TimedOut;
					}
				});
				FDrillResult D = DrillResultOf(Sim, R);
				int32 Left = 0;
				for (const int32 G : Guards)
				{
					Left += Sim.Units()[G].Able() ? 1 : 0;
				}
				GuardsLeft += Left;
				RoomsClear += Squad.Cleared.Num();
				Done += TDone >= 0.0 ? TDone : R.T;
				D.bTaken = TDone >= 0.0 && D.MarinesAble >= 3;
				Tab.Add(D);
				++Runs;
			}
		}
		BNote(FString::Printf(TEXT("    %-26s done in %5.1f s with at least three marines on their feet %2d of %2d; marines lost %4.1f, guards put down %4.1f of 8, guards still on their feet behind them %4.1f, rooms cleared %.1f"),
		                      Mode == 0 ? TEXT("advance to the far end") : TEXT("sweep the four rooms"), Done / FMath::Max(1, Runs), Tab.Taken, Tab.N, Tab.MarinesLost / FMath::Max(1, Tab.N), Tab.FoesLost / FMath::Max(1, Tab.N), GuardsLeft / FMath::Max(1, Runs), RoomsClear / FMath::Max(1, Runs)));
		GDrillTabs.Add(FString::Printf(TEXT("sweep/%d"), Mode), Tab);
		GDrillNums.Add(FString::Printf(TEXT("sweep/%d/left"), Mode), GuardsLeft / FMath::Max(1, Runs));
		GDrillNums.Add(FString::Printf(TEXT("sweep/%d/rooms"), Mode), RoomsClear / FMath::Max(1, Runs));
		GDrillNums.Add(FString::Printf(TEXT("sweep/%d/s"), Mode), Done / FMath::Max(1, Runs));
	}
	const FDrillTable *Wk = GDrillTabs.Find(TEXT("sweep/0")), *Sw = GDrillTabs.Find(TEXT("sweep/1"));
	if (Wk && Sw)
	{
		BCheck("sweep: the four rooms are cleared, fewer guards are left behind and more marines stand at the end", GDrillNums.FindRef(TEXT("sweep/1/rooms")) >= 3.0 && GDrillNums.FindRef(TEXT("sweep/1/left")) < GDrillNums.FindRef(TEXT("sweep/0/left")) && Sw->Taken > Wk->Taken,
		       FString::Printf(TEXT("%.1f rooms cleared; guards left alive behind %.1f against %.1f; %d of %d with three on their feet against %d; %.0f s against %.0f s"), GDrillNums.FindRef(TEXT("sweep/1/rooms")), GDrillNums.FindRef(TEXT("sweep/1/left")),
		                       GDrillNums.FindRef(TEXT("sweep/0/left")), Sw->Taken, Sw->N, Wk->Taken, GDrillNums.FindRef(TEXT("sweep/1/s")), GDrillNums.FindRef(TEXT("sweep/0/s"))));
	}
}

/** Ambush: eight Mandate soldiers come in at the breach and go for Main Engineering by the way the plan gives them; six marines wait at a place on that way. Told to hold it, they take the corners and open
 *  fire on what they see (the drill); told to ambush it they hide in the corners with their fire held and open on the column all together when it is in the killing ground, or when they are found. */
static void BoardScenarioAmbush(FRig& Rig, int32 Seed, int32 Seeds)
{
	const FAstraBoardMap& M = *Rig.Map;
	const int32 Obj = Rig.Comp(TEXT("engineering")), Breach = Rig.Comp(*BenchBreach(Rig));
	if (Obj == INDEX_NONE || Breach == INDEX_NONE)
	{
		BCheck("ambush: arenas", false, TEXT("no Main Engineering or no breach room in the plan"));
		return;
	}
	const FBox& BB = M.GetComps()[Breach].Box;
	const FVector Cut(0.5 * (BB.Min.X + BB.Max.X), BB.Max.Y > 0 ? BB.Max.Y - 80.0 : BB.Min.Y + 80.0, BB.Min.Z);
	TArray<FVector> Pts;
	TArray<int32> Comps;
	float Metres = 0.f;
	FBoardRouteOptions Opt;
	Opt.bThroughSealed = true;
	if (!M.Route(Cut, M.CentreOf(Obj), Pts, Opt, &Metres, &Comps))
	{
		BCheck("ambush: arenas", false, TEXT("no way from the breach to Main Engineering"));
		return;
	}
	// the places: the compartments along the way with corners at their openings (a junction, a doorway), a third, a half and two thirds of the way
	TArray<int32> Places;
	for (const float Share : {0.3f, 0.45f, 0.6f})
	{
		for (int32 i = FMath::RoundToInt(Share * Comps.Num()); i < Comps.Num(); ++i)
		{
			const int32 C = Comps[i];
			if (M.GetComps()[C].Slots.Num() >= 2 && !Places.Contains(C))
			{
				Places.Add(C);
				break;
			}
		}
	}
	BNote(FString::Printf(TEXT("the way from the breach to Engineering is %.0f m through %d compartments; ambush places: %s"), Metres, Comps.Num(), *FString::JoinBy(Places, TEXT(" | "), [&](int32 C) { return M.Describe(C); })));
	for (const int32 Boarders : GTrace ? TArray<int32>({8}) : TArray<int32>({8, 12}))
	{
		for (const int32 Mode : {0, 1})
		{
			double Contact = 0.0, FirstDown = 0.0, LossA = 0.0, LossM = 0.0, T = 0.0;
			int32 Beaten = 0, Takes = 0, N = 0, Ambushes = 0;
			for (int32 pi = 0; pi < (GTrace ? FMath::Min(1, Places.Num()) : Places.Num()); ++pi)
			{
				for (int32 s = 0; s < Seeds; ++s)
				{
					FAstraBoardSim Sim;
					Sim.Init(Rig.Map.ToSharedRef(), Seed + s * 23 + pi);
					Sim.Tuning = Rig.Tuning;
					Sim.SpawnAttackers(ESide::Mandate, Breach, Cut, Obj, Boarders, 2.f, Boarders);
					int32 Counter = 0;
					for (int32 q = 0; q < 2; ++q)                                  // (two squads of six at the place, each given the order)
					{
						const int32 Sq = Sim.Squads().Num();
						MakeMen(Sim, M, ESide::Aquila, FString::Printf(TEXT("Reaction %d"), q + 1), 6, M.Inset(Places[pi], M.CentreOf(Places[pi]), 80.f), TEXT("Marine"), Counter);
						FOrder O;
						O.Task = Mode == 0 ? ETask::Hold : ETask::Ambush;
						O.Comp = Places[pi];
						O.Pos = M.CentreOf(Places[pi]);
						O.Radius = 700.f;
						O.Where = M.Describe(Places[pi]);
						Sim.OrderEx(Sq, O);
					}
					const FRunResult R = RunSim(Sim, 160.0);
					++N;
					Contact += R.Book.FirstContactT;
					LossA += R.Book.Killed[0] + R.Book.Down[0];
					LossM += R.Book.Killed[1] + R.Book.Down[1];
					T += R.T;
					Beaten += (R.Outcome == EOutcome::DefenderHolds || R.Outcome == EOutcome::AttackerRepelled) ? 1 : 0;
					Takes += R.Outcome == EOutcome::AttackerTakes ? 1 : 0;
					Ambushes += R.Book.DrillAmbushes;
				}
			}
			BNote(FString::Printf(TEXT("    %2d boarders, twelve marines at the place: %-9s the Mandate beaten %2d of %2d (take Engineering %d), first contact at %4.1f s, ends %5.1f s; marines lost %4.1f, Mandate lost %4.1f, ambushes sprung %d"),
			                      Boarders, Mode == 0 ? TEXT("hold") : TEXT("ambush"), Beaten, N, Takes, Contact / FMath::Max(1, N), T / FMath::Max(1, N), LossA / FMath::Max(1, N), LossM / FMath::Max(1, N), Ambushes));
			(void)FirstDown;
			GDrillNums.Add(FString::Printf(TEXT("ambush/%d/%d/beaten"), Boarders, Mode), Beaten);
			GDrillNums.Add(FString::Printf(TEXT("ambush/%d/%d/lost"), Boarders, Mode), LossA / FMath::Max(1, N));
			GDrillNums.Add(FString::Printf(TEXT("ambush/%d/%d/sprung"), Boarders, Mode), Ambushes);
		}
	}
	if (!GTrace && GDrillNums.Contains(TEXT("ambush/12/1/beaten")))
	{
		BCheck("ambush: against twelve boarders it beats the same marines holding with their fire free, for no more marines lost", GDrillNums.FindRef(TEXT("ambush/12/1/beaten")) > GDrillNums.FindRef(TEXT("ambush/12/0/beaten")) && GDrillNums.FindRef(TEXT("ambush/12/1/lost")) <= GDrillNums.FindRef(TEXT("ambush/12/0/lost")) && GDrillNums.FindRef(TEXT("ambush/12/1/sprung")) > 0.0,
		       FString::Printf(TEXT("beaten %.0f against %.0f, marines lost %.1f against %.1f, %.0f ambushes sprung"), GDrillNums.FindRef(TEXT("ambush/12/1/beaten")), GDrillNums.FindRef(TEXT("ambush/12/0/beaten")), GDrillNums.FindRef(TEXT("ambush/12/1/lost")),
		                       GDrillNums.FindRef(TEXT("ambush/12/0/lost")), GDrillNums.FindRef(TEXT("ambush/12/1/sprung"))));
	}
}

/** The outermost room of Deck 7 on the other side of the hull from the bench's breach (the Mandate's second craft). */
static FString BenchBreachOpposite(const FRig& Rig, const FString& First)
{
	const int32 C0 = Rig.Comp(*First);
	if (C0 == INDEX_NONE)
	{
		return FString();
	}
	const double Side0 = 0.5 * (Rig.Map->GetComps()[C0].Box.Min.Y + Rig.Map->GetComps()[C0].Box.Max.Y);
	float Best = -1.f;
	FName Id;
	for (const FAstraDmgComp& K : Rig.Src->Comps)
	{
		const double Y = 0.5 * (K.Box.Min.Y + K.Box.Max.Y);
		if (K.Deck != 7 || K.bCorridor || K.Status == 0 || K.Section < TEXT('C') || K.Section > TEXT('F') || K.Box.GetSize().X < 600.0 || Y * Side0 >= 0.0)
		{
			continue;
		}
		if ((float)FMath::Abs(Y) > Best)
		{
			Best = (float)FMath::Abs(Y);
			Id = K.Id;
		}
	}
	return Id.ToString();
}

/** Hold: twelve marines (two squads of six) are in Main Engineering when a Mandate boarding party comes in, at one breach or at two (half of them at each, the two sides of the hull). Without an order they go and meet what comes;
 *  told to hold the place they take the corners of Engineering and the doors round it (the order that wins); told to hold it wide, over the whole deck's section round it (what a "line" is, a man at each of the section's
 *  ways in), they are spread thin. (A drill that posts a man or a pair at every opening of a section was written and measured here: 0 to 1 fights of 8 won against eight or more boarders, twelve marines lost for one or
 *  two of theirs, against 8 of 8 for the place; it was taken out. The order of a line is `hold` with a wide place.) */
static void BoardScenarioHold(FRig& Rig, int32 Seed, int32 Seeds)
{
	const FAstraBoardMap& M = *Rig.Map;
	const FString BreachId = BenchBreach(Rig), BreachId2 = BenchBreachOpposite(Rig, BreachId);
	const int32 Obj = Rig.Comp(TEXT("engineering")), Breach = Rig.Comp(*BreachId), Breach2 = Rig.Comp(*BreachId2);
	if (Obj == INDEX_NONE || Breach == INDEX_NONE || Breach2 == INDEX_NONE)
	{
		BCheck("hold: arenas", false, TEXT("no Main Engineering or no breach rooms in the plan"));
		return;
	}
	const auto CutOf = [&M](int32 Room)
	{
		const FBox& BB = M.GetComps()[Room].Box;
		return FVector(0.5 * (BB.Min.X + BB.Max.X), BB.Max.Y > 0 ? BB.Max.Y - 80.0 : BB.Min.Y + 80.0, BB.Min.Z);
	};
	BNote(FString::Printf(TEXT("Main Engineering is %s; the two breaches: %s and %s"), *M.Describe(Obj), *M.Describe(Breach), *M.Describe(Breach2)));
	for (const int32 Craft : {1, 2})
	{
		for (const int32 Boarders : GBoarders > 0 ? TArray<int32>({GBoarders}) : GTrace ? TArray<int32>({12}) : TArray<int32>({4, 8, 12, 16}))
		{
			for (const int32 Mode : {0, 1, 2})
			{
				if (GSetup >= 0 && Mode != GSetup)
				{
					continue;                                                         // (-setup N: only the order N, for a trace)
				}
				double LossA = 0.0, LossM = 0.0, T = 0.0, Contact = 0.0;
				int32 Beaten = 0, Takes = 0, N = 0;
				for (int32 s = 0; s < Seeds; ++s)
				{
					FAstraBoardSim Sim;
					Sim.Init(Rig.Map.ToSharedRef(), Seed + s * 23);
					Sim.Tuning = Rig.Tuning;
					const auto Land = [&](int32 Room, int32 Count)
					{
						for (const int32 Sq : Sim.SpawnAttackers(ESide::Mandate, Room, CutOf(Room), Obj, Count, 2.f, Count))
						{
							Sim.SquadMutable(Sq)->BreachComp = Room;                      // (each craft's hatch is its squads' own)
							Sim.SquadMutable(Sq)->BreachPos = CutOf(Room);
						}
					};
					if (Craft == 1)
					{
						Land(Breach, Boarders);
					}
					else
					{
						Land(Breach, Boarders / 2);
						Land(Breach2, Boarders - Boarders / 2);
						Sim.SetMission(ESide::Mandate, Breach, CutOf(Breach), Obj);
					}
					int32 Counter = 0;
					for (int32 q = 0; q < 2; ++q)
					{
						const int32 Sq = Sim.Squads().Num();
						MakeMen(Sim, M, ESide::Aquila, FString::Printf(TEXT("Reaction %d"), q + 1), 6, M.Inset(Obj, M.CentreOf(Obj) + FVector(q ? 300.0 : -300.0, 0.0, 0.0), 80.f), TEXT("Marine"), Counter);
						if (Mode > 0)
						{
							FOrder O;
							O.Task = ETask::Hold;
							O.Comp = Obj;
							O.Pos = M.CentreOf(Obj);
							O.Radius = Mode == 1 ? 800.f : 2600.f;
							O.Where = M.Describe(Obj);
							Sim.OrderEx(Sq, O);
						}
					}
					const FRunResult R = RunSim(Sim, 200.0);
					++N;
					Contact += R.Book.FirstContactT;
					LossA += R.Book.Killed[0] + R.Book.Down[0];
					LossM += R.Book.Killed[1] + R.Book.Down[1];
					T += R.T;
					Beaten += (R.Outcome == EOutcome::DefenderHolds || R.Outcome == EOutcome::AttackerRepelled) ? 1 : 0;
					Takes += R.Outcome == EOutcome::AttackerTakes ? 1 : 0;
				}
				BNote(FString::Printf(TEXT("    %d craft, %2d boarders, twelve marines in Engineering: %-24s the Mandate beaten %2d of %2d (take Engineering %2d), first contact %4.1f s, ends %5.1f s; marines lost %4.1f, Mandate lost %4.1f"),
				                      Craft, Boarders, Mode == 0 ? TEXT("no order (meet them)") : Mode == 1 ? TEXT("hold the place") : TEXT("hold wide (a section)"), Beaten, N, Takes, Contact / FMath::Max(1, N), T / FMath::Max(1, N), LossA / FMath::Max(1, N), LossM / FMath::Max(1, N)));
				GDrillNums.Add(FString::Printf(TEXT("hold/%d/%d/%d/beaten"), Craft, Boarders, Mode), Beaten);
				GDrillNums.Add(FString::Printf(TEXT("hold/%d/%d/%d/lost"), Craft, Boarders, Mode), LossA / FMath::Max(1, N));
			}
		}
	}
	if (!GTrace && GBoarders == 0 && GSetup < 0)
	{
		bool bOk = true;
		FString Detail;
		for (const int32 Craft : {1, 2})
		{
			for (const int32 Boarders : {12, 16})
			{
				const double Place = GDrillNums.FindRef(FString::Printf(TEXT("hold/%d/%d/1/beaten"), Craft, Boarders)), Wide = GDrillNums.FindRef(FString::Printf(TEXT("hold/%d/%d/2/beaten"), Craft, Boarders)), None = GDrillNums.FindRef(FString::Printf(TEXT("hold/%d/%d/0/beaten"), Craft, Boarders));
				bOk &= Place > Wide && Place > None;
				Detail += FString::Printf(TEXT("%s%d craft, %d boarders: the place %.0f, wide %.0f, no order %.0f"), Detail.IsEmpty() ? TEXT("") : TEXT("; "), Craft, Boarders, Place, Wide, None);
			}
		}
		BCheck("hold: the place that matters beats a whole section and no order, against twelve boarders and more", bOk, Detail);
	}
}

/** Seal behind: a squad of six marines at the near side of a pressure bulkhead on the Mandate's way to Main Engineering, with the Mandate's boarding party (eight, twelve) coming in at the breach behind them. Told to fall back to Engineering they go on and the party
 *  follows them; told to fall back and seal behind, the last man stays at the console four seconds and shuts the bulkhead on the party: it must be cut open (twenty-two seconds of torch) and the marines are in their corners at Engineering when it comes through. */
static void BoardScenarioSeal(FRig& Rig, int32 Seed, int32 Seeds)
{
	const FAstraBoardMap& M = *Rig.Map;
	const int32 Obj = Rig.Comp(TEXT("engineering")), Breach = Rig.Comp(*BenchBreach(Rig));
	if (Obj == INDEX_NONE || Breach == INDEX_NONE)
	{
		BCheck("seal: arenas", false, TEXT("no Main Engineering or no breach room in the plan"));
		return;
	}
	const FBox& BB = M.GetComps()[Breach].Box;
	const FVector Cut(0.5 * (BB.Min.X + BB.Max.X), BB.Max.Y > 0 ? BB.Max.Y - 80.0 : BB.Min.Y + 80.0, BB.Min.Z);
	TArray<int32> Ps;
	FBoardRouteOptions Opt;
	Opt.bThroughSealed = true;
	if (!M.RoutePortals(Cut, M.CentreOf(Obj), Ps, Opt))
	{
		BCheck("seal: arenas", false, TEXT("no way from the breach to Main Engineering"));
		return;
	}
	// the first pressure bulkhead on the way, with ten metres of passage on the breach side of it
	int32 Door = INDEX_NONE;
	for (int32 i = 2; i < Ps.Num(); ++i)
	{
		if (M.GetPortals()[Ps[i]].Kind == FBoardPortal::EKind::Blast)
		{
			Door = Ps[i];
			break;
		}
	}
	if (Door == INDEX_NONE)
	{
		BCheck("seal: arenas", false, TEXT("no pressure bulkhead on the way from the breach to Main Engineering"));
		return;
	}
	const FBoardPortal& P = M.GetPortals()[Door];
	const int32 Near = FVector::DistSquared(M.CentreOf(P.A), Cut) <= FVector::DistSquared(M.CentreOf(P.B), Cut) ? P.A : P.B;
	const FVector Start = M.Inset(Near, P.PosIn(Near) + (P.PosIn(Near) - M.CentreOf(P.Other(Near))).GetSafeNormal2D() * 700.0, 60.f);
	BNote(FString::Printf(TEXT("the bulkhead is at %s (%d openings from the breach of %d to Main Engineering); the squad stands at %s"), *M.Describe(P.A), Ps.Find(Door) + 1, Ps.Num(), *M.Describe(M.CompAt(Start, 80.f))));
	for (const int32 Boarders : GBoarders > 0 ? TArray<int32>({GBoarders}) : TArray<int32>({8, 12}))
	{
		for (const int32 Mode : {0, 1})
		{
			if (GSetup >= 0 && Mode != GSetup)
			{
				continue;
			}
			double Contact = 0.0, LossA = 0.0, LossM = 0.0, T = 0.0, Seals = 0.0, Cuts = 0.0;
			int32 Beaten = 0, N = 0;
			for (int32 s = 0; s < Seeds; ++s)
			{
				FAstraBoardSim Sim;
				Sim.Init(Rig.Map.ToSharedRef(), Seed + s * 17);
				Sim.Tuning = Rig.Tuning;
				Sim.SpawnAttackers(ESide::Mandate, Breach, Cut, Obj, Boarders, 2.f, Boarders);
				int32 Counter = 0;
				const int32 Sq = Sim.Squads().Num();
				MakeMen(Sim, M, ESide::Aquila, TEXT("Reaction 1"), 6, Start, TEXT("Marine"), Counter);
				FOrder O;
				O.Task = ETask::FallBack;
				O.Comp = Obj;
				O.Pos = M.CentreOf(Obj);
				O.Radius = 800.f;
				O.bSealBehind = Mode == 1;
				O.Where = M.Describe(Obj);
				Sim.OrderEx(Sq, O);
				const FRunResult R = RunSim(Sim, 200.0);
				++N;
				Contact += R.Book.FirstContactT;
				LossA += R.Book.Killed[0] + R.Book.Down[0];
				LossM += R.Book.Killed[1] + R.Book.Down[1];
				T += R.T;
				Seals += R.Book.DrillSeals;
				Beaten += (R.Outcome == EOutcome::DefenderHolds || R.Outcome == EOutcome::AttackerRepelled) ? 1 : 0;
			}
			BNote(FString::Printf(TEXT("    %2d boarders, six marines fall back to Engineering: %-22s the Mandate beaten %2d of %2d, first contact %5.1f s, ends %5.1f s; marines lost %4.1f, Mandate lost %4.1f, bulkheads shut behind them %.1f"),
			                      Boarders, Mode ? TEXT("seal behind") : TEXT("no seal"), Beaten, N, Contact / FMath::Max(1, N), T / FMath::Max(1, N), LossA / FMath::Max(1, N), LossM / FMath::Max(1, N), Seals / FMath::Max(1, N)));
			(void)Cuts;
			GDrillNums.Add(FString::Printf(TEXT("seal/%d/%d/contact"), Boarders, Mode), Contact / FMath::Max(1, N));
			GDrillNums.Add(FString::Printf(TEXT("seal/%d/%d/seals"), Boarders, Mode), Seals / FMath::Max(1, N));
		}
	}
	if (GDrillNums.Contains(TEXT("seal/8/1/contact")))
	{
		BCheck("seal: bulkheads shut behind the squad put the pursuit on it much later", GDrillNums.FindRef(TEXT("seal/8/1/contact")) >= GDrillNums.FindRef(TEXT("seal/8/0/contact")) + 30.0 && GDrillNums.FindRef(TEXT("seal/8/1/seals")) >= 1.0 && GDrillNums.FindRef(TEXT("seal/8/0/seals")) == 0.0,
		       FString::Printf(TEXT("first contact at %.0f s against %.0f s, %.1f bulkheads shut"), GDrillNums.FindRef(TEXT("seal/8/1/contact")), GDrillNums.FindRef(TEXT("seal/8/0/contact")), GDrillNums.FindRef(TEXT("seal/8/1/seals"))));
	}
}


/** Escort: the Captain goes aboard a Mandate ship by a dock with the marines (two squads of six that go for her engineering hall, and a third of six) and walks to her bridge by the way the plan gives, at a walk, not stopping for anything (the worst of
 *  players: the Mandate lay their guns on the Captain before any other man). The third squad is told nothing and goes on with the others (the way squads go), or told to follow him (they gather round him wherever he stands), or to escort him (a man ahead,
 *  two at his sides, the rest behind); or there is no third squad. What each costs him in hits and the squad in men, against the crew of a hulk (a ship with sixty in a hundred of her posts manned, six roaming); and how well the squad keeps with him. */
static void BoardScenarioEscort(const FString& Class, int32 Seed, int32 Seeds, const FTuning& Tuning)
{
	FString Why;
	const TSharedPtr<FBoardShipPlan> P = AstraBoardPlans::Load(FName(*Class), Why);
	if (!P.IsValid())
	{
		BCheck("escort", false, FString::Printf(TEXT("%s: %s"), *Class, *Why));
		return;
	}
	const int32 Bridge = P->Objective(TEXT("bridge"), TEXT("bridge"));
	if (Bridge == INDEX_NONE)
	{
		BCheck("escort", false, FString::Printf(TEXT("%s has no bridge"), *Class));
		return;
	}
	const FAstraBoardMap& M = *P->Map;
	struct FRow { const TCHAR* Name; int32 Mode; };
	const FRow Rows[] = {{TEXT("the Captain with the two squads (12): no escort"), 0}, {TEXT("a third squad, no order (on to engineering)"), 1}, {TEXT("a third squad told to follow him"), 2}, {TEXT("a third squad told to escort him"), 3}};
	double HitsOf[4] = {0.0, 0.0, 0.0, 0.0}, FoesOf[4] = {0.0, 0.0, 0.0, 0.0}, CloseOf[4] = {0.0, 0.0, 0.0, 0.0};
	BNote(FString::Printf(TEXT("  the Captain walks at 2.8 m/s from the dock to %s, not stopping for anything:"), *M.Describe(Bridge)));
	for (const FRow& Row : Rows)
	{
		if (GSetup >= 0 && Row.Mode != GSetup)
		{
			continue;
		}
		double Hits = 0.0, LostThird = 0.0, LostAll = 0.0, FoesLost = 0.0, ArrivedS = 0.0, Left = 0.0, Close = 0.0, CloseN = 0.0;
		int32 Arrived = 0, Hit = 0, Ran = 0;
		for (int32 s = 0; s < Seeds; ++s)
		{
			FAstraBoardSim Sim;
			Sim.Init(P->Map.ToSharedRef(), Seed + s);
			Sim.Tuning = Tuning;
			AstraBoardScene::FSpec Spec;
			Spec.Attacker = ESide::Aquila;
			Spec.Attackers = Row.Mode == 0 ? 12 : 18;
			Spec.Objective = TEXT("engineering");
			Spec.PostShare = 0.6f;
			Spec.Roaming = 6;
			Spec.bSweep = false;
			Spec.SealedShare = 0.f;
			Spec.Seed = Seed + s;
			const AstraBoardScene::FResult Sc = AstraBoardScene::Build(Sim, *P, Spec);
			if (!Sc.bOk || Sc.AttackSquads.IsEmpty())
			{
				continue;
			}
			const FVector Start = Sc.BreachPos;
			TArray<FVector> Pts;
			float Metres = 0.f;
			FBoardRouteOptions Opt;
			Opt.bThroughSealed = true;
			if (!M.Route(Start, M.CentreOf(Bridge), Pts, Opt, &Metres) || Pts.Num() < 2)
			{
				continue;
			}
			Sim.AddCaptain(Start);
			const int32 Third = Row.Mode == 0 ? INDEX_NONE : Sc.AttackSquads.Last();
			if (Third != INDEX_NONE && Row.Mode >= 2)
			{
				if (Row.Mode == 2)
				{
					Sim.Order(Third, ETask::Follow, INDEX_NONE, FVector::ZeroVector, 0.f, TEXT("bench"));
				}
				else
				{
					FOrder O;
					O.Task = ETask::Escort;
					O.Where = TEXT("the Captain");
					Sim.OrderEx(Third, O);
				}
			}
			double Walked = 0.0, TotalCm = 0.0;
			for (int32 i = 1; i < Pts.Num(); ++i)
			{
				TotalCm += FVector::Dist(Pts[i - 1], Pts[i]);
			}
			double StartAt = -1.0, DoneAt = -1.0, NextLook = 0.0;
			FVector At = Start;
			float Yaw = 0.f;
			while (Sim.Time() < 300.0 && DoneAt < 0.0)
			{
				const FSquad* T3 = Third != INDEX_NONE ? Sim.Squad(Third) : nullptr;
				if (StartAt < 0.0)
				{
					bool bAboard = true;
					if (T3)
					{
						bAboard = false;
						for (const int32 Mn : T3->Members)
						{
							bAboard |= Sim.Unit(Mn) && Sim.Unit(Mn)->Act != EAct::Waiting;
						}
					}
					if (bAboard && Sim.Time() > 28.0)
					{
						StartAt = Sim.Time() + 3.0;                                   // (the Captain steps off three seconds after the third squad is through the hatch)
					}
				}
				if (StartAt >= 0.0 && Sim.Time() >= StartAt)
				{
					Walked = FMath::Min(TotalCm, Walked + 2.8 * 100.0 * 0.1);              // 2.8 m/s
					double Rest = Walked;
					for (int32 i = 1; i < Pts.Num(); ++i)
					{
						const double Seg = FVector::Dist(Pts[i - 1], Pts[i]);
						if (Rest <= Seg || i == Pts.Num() - 1)
						{
							At = FMath::Lerp(Pts[i - 1], Pts[i], FMath::Clamp(Rest / FMath::Max(1.0, Seg), 0.0, 1.0));
							Yaw = FMath::RadiansToDegrees(FMath::Atan2(Pts[i].Y - Pts[i - 1].Y, Pts[i].X - Pts[i - 1].X));
							break;
						}
						Rest -= Seg;
					}
					if (Walked >= TotalCm - 600.0)
					{
						DoneAt = Sim.Time();
					}
					if (T3 && Sim.Time() >= NextLook)
					{
						NextLook = Sim.Time() + 1.0;
						for (const int32 Mn : T3->Members)
						{
							const FUnit* U = Sim.Unit(Mn);
							if (U && U->Able())
							{
								Close += FVector::Dist2D(U->Pos, At) < 1000.0 ? 1.0 : 0.0;
								CloseN += 1.0;
							}
						}
					}
				}
				Sim.SetCaptain(At, Yaw, false, StartAt >= 0.0 ? 280.f : 0.f, false);
				Sim.Tick(0.1f);
			}
			++Ran;
			Arrived += DoneAt >= 0.0 ? 1 : 0;
			ArrivedS += DoneAt >= 0.0 ? DoneAt - StartAt : 0.0;
			Left += (TotalCm - Walked) / 100.0;
			Hits += Sim.Book().CaptainHits;
			Hit += Sim.Book().CaptainHits > 0 ? 1 : 0;
			FoesLost += Sim.Book().Killed[1] + Sim.Book().Down[1];
			LostAll += Sim.Book().Killed[0] + Sim.Book().Down[0];
			if (Third != INDEX_NONE)
			{
				for (const int32 Mn : Sim.Squad(Third)->Members)
				{
					const FUnit* U = Sim.Unit(Mn);
					LostThird += (U && (U->Act == EAct::Down || U->Act == EAct::Dead)) ? 1.0 : 0.0;
				}
			}
		}
		const double N = FMath::Max(1, Ran);
		HitsOf[Row.Mode] = Hits / N;
		FoesOf[Row.Mode] = FoesLost / N;
		CloseOf[Row.Mode] = CloseN > 0.0 ? 100.0 * Close / CloseN : 0.0;
		BNote(FString::Printf(TEXT("    %-46s at the bridge %2d of %2d (%3.0f s on foot); hits on him %5.1f (hit at all in %2d); marines lost %4.1f (the third squad %3.1f); defenders lost %4.1f; the third squad within 10 m of him %3.0f%% of the time"),
		                      Row.Name, Arrived, Ran, Arrived ? ArrivedS / Arrived : 0.0, HitsOf[Row.Mode], Hit, LostAll / N, LostThird / N, FoesOf[Row.Mode], CloseOf[Row.Mode]));
	}
	if (GSetup < 0)
	{
		BCheck("escort: the squad keeps with the Captain", CloseOf[3] >= 1.5 * CloseOf[1] && CloseOf[2] >= 1.5 * CloseOf[1], FString::Printf(TEXT("the third squad is within 10 m of him %.0f%% (escort), %.0f%% (follow) of the walk, %.0f%% with no order"), CloseOf[3], CloseOf[2], CloseOf[1]));
	}
}

// ================================================================================================================== the Captain's body: leaning out of cover, lying down, a head over a wall (ABBORDAGGI-4)

namespace
{
	/** One of the plan's corners: a place beside an opening where a man is out of the line through it (FBoardSlot), the enemy who stands in that line some metres beyond, and the way to lean into the opening. */
	struct FLeanCorner
	{
		int32 Slot = INDEX_NONE;
		FVector Foe = FVector::ZeroVector;          // his feet
		FVector In = FVector::ZeroVector;           // unit, on the floor: the way the Captain's eye goes when he leans out into the opening
		float FoeYaw = 0.f;                         // he looks at the corner
	};

	/** The Captain's body as the game tells the sim: where his eye is from his feet and whether he is low or lying. */
	struct FLeanPose
	{
		const TCHAR* Name;
		FVector Eye;
		bool bLow, bProne;
	};
}

static void BoardScenarioLean(FRig& Rig, int32 Seed, int32 Seeds)
{
	const FAstraBoardMap& M = *Rig.Map;
	const TArray<FBoardPortal>& Portals = M.GetPortals();
	constexpr double LeanCm = 34.0;                       // (the character's: ASTRACharacter.cpp, LeanOutCm)
	constexpr double StandEye = 152.0;

	// ---- the frame of a lean and its easing, as the character has them (pure)
	{
		float S0, D0, R0, S1, D1, R1, Sm, Dm, Rm, Sp, Dp, Rp;
		AASTRACharacter::LeanFrame(1.f, EAstraPosture::Standing, S1, D1, R1);
		AASTRACharacter::LeanFrame(-1.f, EAstraPosture::Standing, Sm, Dm, Rm);
		AASTRACharacter::LeanFrame(0.f, EAstraPosture::Standing, S0, D0, R0);
		AASTRACharacter::LeanFrame(1.f, EAstraPosture::Prone, Sp, Dp, Rp);
		const bool bFrame = FMath::IsNearlyEqual(S1, (float)LeanCm, 0.01f) && FMath::IsNearlyEqual(Sm, -S1, 0.01f) && FMath::IsNearlyEqual(Rm, -R1, 0.01f) && FMath::IsNearlyEqual(D1, Dm, 0.01f)
			&& S0 == 0.f && D0 == 0.f && R0 == 0.f && Sp < 0.7f * S1 && Sp > 0.4f * S1 && R1 > 5.f && R1 < 16.f && D1 > 0.f && D1 < 12.f;
		// the easing: at sixty frames a second out in a third of a second or so, back a little quicker, never past the target, and from one side to the other through the middle
		float L = 0.f;
		int32 Out95 = 0, Back05 = 0;
		bool bOver = false, bMono = true;
		for (int32 i = 1; i <= 300 && Out95 == 0; ++i)
		{
			const float Next = AASTRACharacter::LeanStep(L, 1.f, 1.f / 60.f);
			bOver |= Next > 1.f + 1.0e-4f;
			bMono &= Next >= L;
			L = Next;
			Out95 = L >= 0.95f ? i : 0;
		}
		for (int32 i = 1; i <= 300 && Back05 == 0; ++i)
		{
			const float Next = AASTRACharacter::LeanStep(L, 0.f, 1.f / 60.f);
			bOver |= Next < -1.0e-4f;
			bMono &= Next <= L;
			L = Next;
			Back05 = L <= 0.05f ? i : 0;
		}
		float X = 0.7f;
		bool bThrough = false;
		for (int32 i = 1; i <= 240; ++i)
		{
			const float Next = AASTRACharacter::LeanStep(X, -1.f, 1.f / 60.f);
			bThrough |= Next < 0.f && X >= 0.f;
			bOver |= Next < -1.f - 1.0e-4f;
			X = Next;
		}
		BCheck("lean: the frame and the easing", bFrame && Out95 >= 12 && Out95 <= 30 && Back05 > 0 && Back05 <= Out95 && !bOver && bMono && bThrough && X == -1.f,
		       FString::Printf(TEXT("a full lean puts the eyes %.0f cm out and %.0f cm down and rolls the picture %.0f degrees (lying: %.0f cm); out to 95%% in %.2f s, back to 5%% in %.2f s; no overshoot, monotone, and through the middle from one side to the other"),
		                       S1, D1, R1, Sp, Out95 / 60.f, Back05 / 60.f));
	}

	// ---- the corners: every slot of the plan with an enemy in the line through its opening, who does not see the slot
	FAstraBoardSim Probe;
	Probe.Init(Rig.Map.ToSharedRef(), Seed);
	TArray<FLeanCorner> Corners;
	int32 Hidden = 0, Shown = 0, AwayShown = 0;
	for (int32 si = 0; si < M.GetSlots().Num(); ++si)
	{
		const FBoardSlot& Sl = M.GetSlots()[si];
		const FBoardPortal& Po = Portals[Sl.Portal];
		const int32 Other = Po.Other(Sl.Comp);
		if (Po.Kind != FBoardPortal::EKind::Open || !M.GetComps().IsValidIndex(Other))
		{
			continue;                                          // (a door is shut until somebody opens it: that is another question; the open ways are the corners one leans round)
		}
		FLeanCorner C;
		C.Slot = si;
		bool bFoe = false;
		for (const double D : {800.0, 600.0, 400.0, 250.0})
		{
			const FVector P = FVector(Po.Pos.X, Po.Pos.Y, M.GetComps()[Other].FloorZ()) + FVector(Sl.Out.X, Sl.Out.Y, 0.0) * D;
			if (M.CompAt(P + FVector(0.0, 0.0, 20.0)) == Other)
			{
				C.Foe = P;
				bFoe = true;
				break;
			}
		}
		if (!bFoe)
		{
			continue;
		}
		const double Toward = (Po.Pos.X - Sl.Pos.X) * Po.Along.X + (Po.Pos.Y - Sl.Pos.Y) * Po.Along.Y;
		C.In = FVector(Po.Along.X, Po.Along.Y, 0.0) * (Toward >= 0.0 ? 1.0 : -1.0);
		C.FoeYaw = FMath::RadiansToDegrees(FMath::Atan2(Sl.Pos.Y - C.Foe.Y, Sl.Pos.X - C.Foe.X));
		const FVector FoeEye = C.Foe + FVector(0.0, 0.0, StandEye);
		const FVector Eye0 = Sl.Pos + FVector(0.0, 0.0, StandEye);
		if (Probe.Sees(FoeEye, Eye0))
		{
			continue;                                          // he sees the corner itself: not a corner for him
		}
		++Hidden;
		Shown += Probe.Sees(FoeEye, Eye0 + C.In * LeanCm) ? 1 : 0;
		AwayShown += Probe.Sees(FoeEye, Eye0 - C.In * LeanCm) ? 1 : 0;
		Corners.Add(C);
	}
	BNote(FString::Printf(TEXT("  corners: %d places beside an opening, hidden from an enemy in the line through it; the eye leaned %.0f cm into the opening is seen from %d of them (%.0f%%), leaned %.0f cm away from %d"), Hidden, LeanCm, Shown,
	                      Hidden ? 100.0 * Shown / Hidden : 0.0, LeanCm, AwayShown));
	BCheck("lean: the eye out of cover is seen", Hidden >= 20 && Shown >= 0.85 * Hidden && AwayShown <= 0.05 * Hidden,
	       FString::Printf(TEXT("%d corners: leaned into the opening the eye is seen from %d, leaned away from %d"), Hidden, Shown, AwayShown));

	// ---- the fight: one enemy holds the line through an opening, the Captain stands at the corner (never moving, never firing: what the enemy does about him is all that is measured)
	const auto Pose = [](int32 Mode) -> FLeanPose
	{
		switch (Mode)
		{
		case 1: return {TEXT("crouched"), FVector(0.0, 0.0, 105.0), true, false};
		case 2: return {TEXT("lying"), FVector(0.0, 0.0, 45.0), true, true};
		default: return {TEXT("standing"), FVector(0.0, 0.0, StandEye), false, false};
		}
	};
	struct FOutcome { int32 Runs = 0, Contacts = 0, Hits = 0, Shots = 0; };
	const auto Fight = [&](const FVector& CaptainAt, const FVector& Foe, float FoeYaw, const FVector& EyeRel, bool bLow, bool bProne, const TFunction<bool(const FVector&, const FVector&)>& Sight, int32 s, FOutcome& Out)
	{
		FAstraBoardSim Sim;
		Sim.Init(Rig.Map.ToSharedRef(), Seed + s);
		Sim.Tuning = Rig.Tuning;
		Sim.Tuning.bCover = false;
		const int32 Sq = Sim.AddSquad(ESide::Mandate, TEXT("Gun"));
		const int32 G = Sim.AddUnit(ESide::Mandate, ERole::Leader, TEXT("Gunner"), Foe, Sq);
		Sim.UnitMutable(G)->Yaw = FoeYaw;
		Sim.SquadMutable(Sq)->bStand = true;
		Sim.Order(Sq, ETask::Hold, Sim.Unit(G)->Comp, Foe, 150.f, TEXT("bench"));          // (he holds the line where he stands: he does not go to look)
		Sim.AddCaptain(CaptainAt);
		if (Sight)
		{
			Sim.SightOverride = Sight;
		}
		const float Yaw = FoeYaw + 180.f;
		while (Sim.Time() < 10.0)
		{
			Sim.SetCaptain(CaptainAt, Yaw, bLow, 0.f, false, EyeRel, bProne);
			Sim.Tick(0.1f);
		}
		++Out.Runs;
		Out.Contacts += Sim.Book().Contacts > 0 ? 1 : 0;
		Out.Hits += Sim.Book().CaptainHits;
		Out.Shots += Sim.Book().Shots;
	};
	FOutcome Behind, Leaned;
	const int32 Step = FMath::Max(1, Corners.Num() / 10);
	for (int32 ci = 0; ci < Corners.Num(); ci += Step)
	{
		const FLeanCorner& C = Corners[ci];
		const FVector At = M.GetSlots()[C.Slot].Pos;
		for (int32 s = 0; s < FMath::Max(2, Seeds / 4); ++s)
		{
			Fight(At, C.Foe, C.FoeYaw, FVector(0.0, 0.0, StandEye), false, false, nullptr, s, Behind);
			Fight(At, C.Foe, C.FoeYaw, FVector(C.In.X * LeanCm, C.In.Y * LeanCm, StandEye), false, false, nullptr, s, Leaned);
		}
	}
	BNote(FString::Printf(TEXT("  an enemy holds the line through the opening, 10 s, the Captain at the corner: behind it he is seen in %d of %d fights and hit %d times; with the eye leaned out he is seen in %d of %d and hit %d times (%.1f a fight)"),
	                      Behind.Contacts, Behind.Runs, Behind.Hits, Leaned.Contacts, Leaned.Runs, Leaned.Hits, Leaned.Runs ? (double)Leaned.Hits / Leaned.Runs : 0.0));
	BCheck("lean: what shows of him is what is shot at", Behind.Runs >= 20 && Behind.Contacts == 0 && Behind.Hits == 0 && Leaned.Contacts >= 0.85 * Leaned.Runs && Leaned.Hits >= Leaned.Runs,
	       FString::Printf(TEXT("behind the corner: seen in %d of %d fights, %d hits; leaned out: seen in %d of %d, %d hits"), Behind.Contacts, Behind.Runs, Behind.Hits, Leaned.Contacts, Leaned.Runs, Leaned.Hits));

	// ---- the open lane, ten metres: standing, crouched, lying (the hits taken in ten seconds), and then with a wall across it that is 135 cm high (in the game the level decides this: the sim asks the world whether
	//      a man and the Captain see each other, his eye and his chest; the bench stands a wall in for the level, in the same sight test)
	FLane Lane;
	if (!Lane.Find(Rig))
	{
		BCheck("lean: the lane", false, TEXT("no lane on Deck 8"));
		return;
	}
	const float Z = Lane.Start.Z;
	const FVector Gunner(-600.0, 0.0, Z), Captain(400.0, 0.0, Z);
	constexpr double WallX = -100.0, WallH = 135.0;
	const TFunction<bool(const FVector&, const FVector&)> Wall = [Z](const FVector& A, const FVector& B) -> bool
	{
		if ((A.X - WallX) * (B.X - WallX) > 0.0)
		{
			return true;                                       // both on one side of the wall: nothing between
		}
		const double T = FMath::Abs(B.X - A.X) < 1.0e-6 ? 0.0 : (WallX - A.X) / (B.X - A.X);
		return A.Z + T * (B.Z - A.Z) > Z + WallH;              // the ray clears the wall's top, or does not
	};
	FOutcome Open[3], Walled[3];
	for (int32 m = 0; m < 3; ++m)
	{
		const FLeanPose P = Pose(m);
		for (int32 s = 0; s < FMath::Max(12, Seeds * 2); ++s)
		{
			Fight(Captain, Gunner, 0.f, P.Eye, P.bLow, P.bProne, nullptr, s, Open[m]);
			Fight(Captain, Gunner, 0.f, P.Eye, P.bLow, P.bProne, Wall, s, Walled[m]);
		}
		BNote(FString::Printf(TEXT("  10 m, in the open, %-8s: seen in %d of %d fights, hit %5.1f times a fight   |   with a %.0f cm wall between: seen in %d of %d, hit %5.1f times a fight"), P.Name, Open[m].Contacts, Open[m].Runs,
		                      Open[m].Runs ? (double)Open[m].Hits / Open[m].Runs : 0.0, WallH, Walled[m].Contacts, Walled[m].Runs, Walled[m].Runs ? (double)Walled[m].Hits / Walled[m].Runs : 0.0));
	}
	BCheck("lean: a smaller target is hit less", Open[1].Hits < 0.93 * Open[0].Hits && Open[2].Hits < 0.78 * Open[0].Hits && Open[2].Hits < Open[1].Hits && Open[0].Hits > 0,
	       FString::Printf(TEXT("in ten seconds at 10 m: standing %d hits, crouched %d (%.0f%%), lying %d (%.0f%%)"), Open[0].Hits, Open[1].Hits, Open[0].Hits ? 100.0 * Open[1].Hits / Open[0].Hits : 0.0, Open[2].Hits,
	                       Open[0].Hits ? 100.0 * Open[2].Hits / Open[0].Hits : 0.0));
	BCheck("lean: cover is what the world's sight says", Walled[0].Contacts >= 0.9 * Walled[0].Runs && Walled[0].Hits > 0 && Walled[0].Hits < 0.75 * Open[0].Hits && Walled[1].Contacts == 0 && Walled[1].Hits == 0 && Walled[2].Contacts == 0 && Walled[2].Hits == 0,
	       FString::Printf(TEXT("behind a 135 cm wall: standing, his head over it, is seen and hit %d times (%.0f%% of the open); crouched and lying are not seen (%d, %d fights) and not hit"), Walled[0].Hits,
	                       Open[0].Hits ? 100.0 * Walled[0].Hits / Open[0].Hits : 0.0, Walled[1].Contacts, Walled[2].Contacts));
}

// ================================================================================================================== the Captain's arms on the weapon

namespace
{
	/** The animation's pose at a time on a mesh's skeleton: the local transforms of all its bones (the mannequin's own, as the game plays them). */
	bool FpsEvalPose(USkeletalMesh* Mesh, UAnimSequence* Anim, double Time, TArray<FTransform>& OutLocal)
	{
		FMemMark Mark(FMemStack::Get());	// the compact pose lives on the memory stack
		const FReferenceSkeleton& Ref = Mesh->GetRefSkeleton();
		TArray<FBoneIndexType> Required;
		for (int32 i = 0; i < Ref.GetNum(); ++i)
		{
			Required.Add((FBoneIndexType)i);
		}
		FBoneContainer Container;
		Container.InitializeTo(Required, UE::Anim::FCurveFilterSettings(UE::Anim::ECurveFilterMode::DisallowAll), *Mesh);
		FCompactPose Pose;
		Pose.SetBoneContainer(&Container);
		Pose.ResetToRefPose();
		FBlendedCurve Curve;
		Curve.InitFrom(Container);
		UE::Anim::FStackAttributeContainer Attributes;
		FAnimationPoseData Data(Pose, Curve, Attributes);
		Anim->GetAnimationPose(Data, FAnimExtractContext(Time, false));
		OutLocal.SetNum(Ref.GetNum());
		for (int32 i = 0; i < Ref.GetNum(); ++i)
		{
			OutLocal[i] = Pose[FCompactPoseBoneIndex(i)];
		}
		return true;
	}

	/** A socket of the mesh's skeleton in the mesh's space, given the pose (component space). */
	bool FpsSocket(USkeletalMesh* Mesh, const TArray<FTransform>& CS, const TCHAR* Name, FTransform& Out)
	{
		const USkeletalMeshSocket* S = Mesh->FindSocket(FName(Name));
		if (!S)
		{
			return false;
		}
		const int32 Bone = Mesh->GetRefSkeleton().FindBoneIndex(S->BoneName);
		if (Bone == INDEX_NONE)
		{
			return false;
		}
		Out = S->GetSocketLocalTransform() * CS[Bone];
		return true;
	}

	struct FFpsView { double HalfH, HalfV; };

	/** Where a point of the camera's space is in the view: degrees right and up, and whether the picture holds it. */
	FString FpsWhere(const FVector& C, const FFpsView& V, bool& bIn)
	{
		if (C.X < 1.0)
		{
			bIn = false;
			return FString::Printf(TEXT("behind the camera"));
		}
		bIn = FMath::Abs(C.Y / C.X) <= V.HalfH && FMath::Abs(C.Z / C.X) <= V.HalfV;
		return FString::Printf(TEXT("%5.1f right %5.1f up at %3.0f cm %s"), FMath::RadiansToDegrees(FMath::Atan2(C.Y, C.X)), FMath::RadiansToDegrees(FMath::Atan2(C.Z, C.X)), C.X, bIn ? TEXT("in view") : TEXT("out of view"));
	}

	/** How far (cm) a point of the camera's space stands outside the view volume of a picture (tangents of its half angles); negative inside it, and the near plane counts: the cut end of an arm
	 *  that is that far outside cannot show. */
	double FpsOutside(const FVector& P, double TanH, double TanV)
	{
		const double Near = 1.0 - P.X;
		const double Bottom = (-P.Z - P.X * TanV) / FMath::Sqrt(1.0 + TanV * TanV);
		const double Top = (P.Z - P.X * TanV) / FMath::Sqrt(1.0 + TanV * TanV);
		const double Side = (FMath::Abs(P.Y) - P.X * TanH) / FMath::Sqrt(1.0 + TanH * TanH);
		return FMath::Max(FMath::Max(Near, Bottom), FMath::Max(Top, Side));
	}

	/** One pose of the offline preview's file (Saved/scratch/vm.py): every bone's component-space transform and the hand sockets, as the engine evaluates the animation. */
	void FpsDumpPose(FString& Out, const FString& Key, double Time, USkeletalMesh* Mesh, const TArray<FTransform>& CS)
	{
		const FReferenceSkeleton& Ref = Mesh->GetRefSkeleton();
		const auto One = [](const FTransform& T)
		{
			const FVector L = T.GetLocation(), Sc = T.GetScale3D();
			const FQuat Q = T.GetRotation();
			return FString::Printf(TEXT("{\"t\":[%.4f,%.4f,%.4f],\"q\":[%.6f,%.6f,%.6f,%.6f],\"s\":[%.4f,%.4f,%.4f]}"), L.X, L.Y, L.Z, Q.X, Q.Y, Q.Z, Q.W, Sc.X, Sc.Y, Sc.Z);
		};
		Out += FString::Printf(TEXT("%s\"%s\":{\"time\":%.3f,\"bones\":{"), Out.IsEmpty() ? TEXT("") : TEXT(",\n"), *Key, Time);
		for (int32 i = 0; i < Ref.GetNum(); ++i)
		{
			Out += FString::Printf(TEXT("%s\"%s\":%s"), i ? TEXT(",") : TEXT(""), *Ref.GetBoneName(i).ToString(), *One(CS[i]));
		}
		Out += TEXT("},\"sockets\":{");
		bool bFirst = true;
		for (const TCHAR* Name : {TEXT("HandGrip_R"), TEXT("HandGrip_L"), TEXT("weapon_r_muzzle")})
		{
			FTransform T;
			if (FpsSocket(Mesh, CS, Name, T))
			{
				Out += FString::Printf(TEXT("%s\"%s\":%s"), bFirst ? TEXT("") : TEXT(","), Name, *One(T));
				bFirst = false;
			}
		}
		Out += TEXT("}}");
	}

	/** One state of the offline preview: where the arms' mesh stands against the camera and the six bones as the rig solved them (mesh space). */
	void FpsDumpState(FString& Out, const FString& Key, const FString& PoseKey, const FVector& Loc, const FQuat& Rot, const AstraArms::FBones& B, const FReferenceSkeleton& Ref, const FTransform* Solved, float Fov)
	{
		Out += FString::Printf(TEXT("%s\"%s\":{\"pose\":\"%s\",\"fov\":%.1f,\"loc\":[%.4f,%.4f,%.4f],\"q\":[%.6f,%.6f,%.6f,%.6f],\"solved\":{"), Out.IsEmpty() ? TEXT("") : TEXT(",\n"), *Key, *PoseKey, Fov, Loc.X, Loc.Y, Loc.Z, Rot.X, Rot.Y, Rot.Z, Rot.W);
		const int32 Index[6] = {B.Upper[0], B.Lower[0], B.Hand[0], B.Upper[1], B.Lower[1], B.Hand[1]};
		for (int32 i = 0; i < 6; ++i)
		{
			const FVector L = Solved[i].GetLocation();
			const FQuat Q = Solved[i].GetRotation();
			Out += FString::Printf(TEXT("%s\"%s\":{\"t\":[%.4f,%.4f,%.4f],\"q\":[%.6f,%.6f,%.6f,%.6f],\"s\":[1,1,1]}"), i ? TEXT(",") : TEXT(""), *Ref.GetBoneName(Index[i]).ToString(), L.X, L.Y, L.Z, Q.X, Q.Y, Q.Z, Q.W);
		}
		Out += TEXT("}}");
	}

	/** The tuning of a run, "rifle.hip=84,17,-10;shoulder_l=62,-20,-42": what a place or an anchor would be if it were changed, to try before the table takes it. */
	TMap<FString, FVector> FpsSetOf(const FString& Set)
	{
		TMap<FString, FVector> Out;
		TArray<FString> Items;
		Set.ParseIntoArray(Items, TEXT(";"));
		for (const FString& Item : Items)
		{
			FString K, V;
			if (!Item.Split(TEXT("="), &K, &V))
			{
				continue;
			}
			TArray<FString> N;
			V.ParseIntoArray(N, TEXT(","));
			FVector P(0.0);
			P.X = N.IsValidIndex(0) ? FCString::Atod(*N[0]) : 0.0;
			P.Y = N.IsValidIndex(1) ? FCString::Atod(*N[1]) : 0.0;
			P.Z = N.IsValidIndex(2) ? FCString::Atod(*N[2]) : 0.0;
			Out.Add(K.TrimStartAndEnd(), P);
		}
		return Out;
	}
}

static void BoardScenarioFps(const FString& DumpPath, const FString& SetText)
{
	FString Dump, StatesOut;
	const TMap<FString, FVector> Set = FpsSetOf(SetText);
	USkeletalMesh* Mesh = LoadObject<USkeletalMesh>(nullptr, TEXT("/Game/ASTRA/Weapons/SKM_ASTRA_Arms.SKM_ASTRA_Arms"));
	if (!Mesh)
	{
		BCheck("fps: the arms asset", false, TEXT("SKM_ASTRA_Arms is not in the project (tools/ue_scripts/make_fp_arms.py makes it from the mannequin)"));
		return;
	}
	const FReferenceSkeleton& Ref = Mesh->GetRefSkeleton();
	AstraArms::FBones Bones;
	BCheck("fps: the arm bones", AstraArms::FindBones(Ref, Bones), FString::Printf(TEXT("%d bones, upperarm/lowerarm/hand on both sides"), Ref.GetNum()));
	if (!Bones.IsValid())
	{
		return;
	}
#if WITH_EDITORONLY_DATA
	// the skin of the arms follows the arms' own bones alone (what the chest and the clavicles held would drag the vertices near the shoulder into spikes once the arms are moved away)
	if (const FSkeletalMeshModel* Model = Mesh->GetImportedModel())
	{
		int32 Vertices = 0, Foreign = 0;
		FString Which;
		if (Model->LODModels.Num() > 0)
		{
			for (const FSkelMeshSection& Sec : Model->LODModels[0].Sections)
			{
				for (const FSoftSkinVertex& V : Sec.SoftVertices)
				{
					++Vertices;
					for (int32 k = 0; k < MAX_TOTAL_INFLUENCES; ++k)
					{
						if (V.InfluenceWeights[k] > 0 && Sec.BoneMap.IsValidIndex(V.InfluenceBones[k]))
						{
							const FString Name = Ref.GetBoneName(Sec.BoneMap[V.InfluenceBones[k]]).ToString();
							if (!(Name.StartsWith(TEXT("upperarm")) || Name.StartsWith(TEXT("lowerarm")) || Name.StartsWith(TEXT("hand")) || Name.StartsWith(TEXT("index")) || Name.StartsWith(TEXT("middle")) || Name.StartsWith(TEXT("ring")) || Name.StartsWith(TEXT("pinky")) || Name.StartsWith(TEXT("thumb"))))
							{
								++Foreign;
								Which = Name;
							}
						}
					}
				}
			}
		}
		BCheck("fps: the arms' skin", Vertices > 0 && Foreign == 0, FString::Printf(TEXT("%d vertices, %d influences on bones that are not the arms' (%s): tools/ue_scripts/make_fp_arms.py gives their weight to the arm's own"), Vertices, Foreign, Which.IsEmpty() ? TEXT("none") : *Which));
	}
#endif
	const auto Cvar = [](const TCHAR* Name, float Default)
	{
		const IConsoleVariable* V = IConsoleManager::Get().FindConsoleVariable(Name);
		return V ? V->GetFloat() : Default;
	};
	const FVector ShoulderNudge(Cvar(TEXT("astra.fps.shoulder_x"), 0.f), Cvar(TEXT("astra.fps.shoulder_y"), 0.f), Cvar(TEXT("astra.fps.shoulder_z"), 0.f));
	for (const EAstraWeapon Id : {EAstraWeapon::Rifle, EAstraWeapon::Pistol})
	{
		FAstraWeaponDef W = AstraWeapons::Get(Id);
		const FString Who = Id == EAstraWeapon::Rifle ? TEXT("rifle") : TEXT("pistol");
		if (const FVector* P = Set.Find(Who + TEXT(".shoulder_r"))) { W.ShoulderHipR = *P; }
		if (const FVector* P = Set.Find(Who + TEXT(".shoulder_l"))) { W.ShoulderHipL = *P; }
		if (const FVector* P = Set.Find(Who + TEXT(".ads_shoulder_r"))) { W.ShoulderAdsR = *P; }
		if (const FVector* P = Set.Find(Who + TEXT(".ads_shoulder_l"))) { W.ShoulderAdsL = *P; }
		// the shoulders of a state: the hip's and the lowered's are the table's, the sights' too, and between them as the weapon comes up
		const auto ShouldersAt = [&](double Ads, FVector& R, FVector& L)
		{
			R = FMath::Lerp(W.ShoulderHipR, W.ShoulderAdsR, Ads) + ShoulderNudge;
			L = FMath::Lerp(W.ShoulderHipL, W.ShoulderAdsL, Ads) + FVector(ShoulderNudge.X, -ShoulderNudge.Y, ShoulderNudge.Z);
		};
		FVector ShoulderR, ShoulderL;
		ShouldersAt(0.0, ShoulderR, ShoulderL);
		if (const FVector* P = Set.Find(Who + TEXT(".hip"))) { W.HipPlace = *P; }
		if (const FVector* P = Set.Find(Who + TEXT(".hipturn"))) { W.HipTurn = FRotator(P->X, P->Y, P->Z); }
		if (const FVector* P = Set.Find(Who + TEXT(".ads"))) { W.AdsPlace = *P; }
		if (const FVector* P = Set.Find(Who + TEXT(".low"))) { W.LowPlace = *P; }
		if (const FVector* P = Set.Find(Who + TEXT(".lowturn"))) { W.LowTurn = FRotator(P->X, P->Y, P->Z); }
		if (const FVector* P = Set.Find(Who + TEXT(".gripl"))) { W.GripLHand = *P; }
		if (const FVector* P = Set.Find(Who + TEXT(".fov"))) { W.FpFov = P->X; }
		UAnimSequence* Idle = LoadObject<UAnimSequence>(nullptr, W.AnimIdle);
		if (!Idle)
		{
			BCheck("fps: the animations", false, FString::Printf(TEXT("%s: %s is not in the project"), W.Name, W.AnimIdle));
			continue;
		}
		TArray<FTransform> Local, CS;
		FpsEvalPose(Mesh, Idle, 0.0, Local);
		AstraArms::ComponentSpace(Ref, Local, CS);
		if (!DumpPath.IsEmpty())
		{
			FpsDumpPose(Dump, Who + TEXT("_idle@0.00"), 0.0, Mesh, CS);
		}
		FTransform SockR, SockL;
		if (!FpsSocket(Mesh, CS, TEXT("HandGrip_R"), SockR) || !FpsSocket(Mesh, CS, TEXT("HandGrip_L"), SockL))
		{
			BCheck("fps: the hand sockets", false, TEXT("HandGrip_R / HandGrip_L are not on the skeleton"));
			continue;
		}
		// the weapon table's measure of the ready pose against the asset's own
		const FVector TableY = W.PoseGripY.GetSafeNormal();
		const double LocErr = FVector::Dist(W.PoseGripLoc, SockR.GetLocation());
		const double AxisErr = FMath::RadiansToDegrees(FMath::Acos(FMath::Clamp(FVector::DotProduct(TableY, SockR.GetRotation().RotateVector(FVector(0, 1, 0))), -1.0, 1.0)));
		const FMatrix SockM = FRotationMatrix::Make(SockR.GetRotation());
		BCheck(Id == EAstraWeapon::Rifle ? "fps: the table's pose, rifle" : "fps: the table's pose, pistol", LocErr < 0.2 && AxisErr < 0.3,
			FString::Printf(TEXT("%s: the right-hand socket in the ready pose is %.2f cm and %.2f deg from the table's numbers (the engine's: loc (%.2f, %.2f, %.2f), X (%.4f, %.4f, %.4f), Y (%.4f, %.4f, %.4f), Z (%.4f, %.4f, %.4f))"), W.Name, LocErr, AxisErr,
				SockR.GetLocation().X, SockR.GetLocation().Y, SockR.GetLocation().Z, SockM.GetUnitAxis(EAxis::X).X, SockM.GetUnitAxis(EAxis::X).Y, SockM.GetUnitAxis(EAxis::X).Z,
				SockM.GetUnitAxis(EAxis::Y).X, SockM.GetUnitAxis(EAxis::Y).Y, SockM.GetUnitAxis(EAxis::Y).Z, SockM.GetUnitAxis(EAxis::Z).X, SockM.GetUnitAxis(EAxis::Z).Y, SockM.GetUnitAxis(EAxis::Z).Z));
		// the weapon's places: hip, sights, lowered
		struct FState { const TCHAR* Name; FVector Target; FRotator Turn; };
		const FState States[3] = {{TEXT("hip"), W.HipPlace, W.HipTurn}, {TEXT("sights"), W.AdsPlace, FRotator::ZeroRotator}, {TEXT("lowered"), W.LowPlace, W.LowTurn}};
		const FVector Wanted0 = SockR.TransformPosition(W.GripLHand);
		double WorstOutside = 1.0e9;                  // the shoulder joint that stands nearest to the picture, over every state and the way between the hip and the sights
		FString WorstWhere;
		for (const FState& St : States)
		{
			FVector Loc, SightMesh;
			FQuat Rot;
			AstraArms::PlaceWeapon(SockR.GetLocation(), SockR.GetRotation(), W.Sight, St.Target, St.Turn, Loc, Rot, SightMesh);
			const FVector SightCam = Rot.RotateVector(SightMesh) + Loc;
			AstraArms::FSetup Setup;
			ShouldersAt(St.Name[0] == 's' ? 1.0 : 0.0, Setup.Shoulder[AstraArms::Right], Setup.Shoulder[AstraArms::Left]);
			if (const FVector* P = Set.Find(TEXT("pole_l"))) { Setup.Pole[AstraArms::Left] = *P; }
			if (const FVector* P = Set.Find(TEXT("pole_r"))) { Setup.Pole[AstraArms::Right] = *P; }
			Setup.LeftHandDelta = Wanted0 - SockL.GetLocation();
			FTransform Solved[6];
			AstraArms::SolveBoth(Bones, CS, Rot, Loc, Setup, Solved);
			// the lengths of the bones are kept, the shoulders stand where they were put, the right hand is where the animation has it, the left grip is on the weapon's
			double LenErr = 0.0, ShErr = 0.0;
			FVector ShCam[2], WristCam[2];
			double Elbow[2], Reach[2];
			for (int32 Side = 0; Side < 2; ++Side)
			{
				const double L1a = FVector::Dist(CS[Bones.Upper[Side]].GetLocation(), CS[Bones.Lower[Side]].GetLocation());
				const double L2a = FVector::Dist(CS[Bones.Lower[Side]].GetLocation(), CS[Bones.Hand[Side]].GetLocation());
				const double L1b = FVector::Dist(Solved[Side * 3].GetLocation(), Solved[Side * 3 + 1].GetLocation());
				const double L2b = FVector::Dist(Solved[Side * 3 + 1].GetLocation(), Solved[Side * 3 + 2].GetLocation());
				LenErr = FMath::Max(LenErr, FMath::Max(FMath::Abs(L1a - L1b), FMath::Abs(L2a - L2b)));
				ShCam[Side] = Rot.RotateVector(Solved[Side * 3].GetLocation()) + Loc;
				WristCam[Side] = Rot.RotateVector(Solved[Side * 3 + 2].GetLocation()) + Loc;
				ShErr = FMath::Max(ShErr, FVector::Dist(ShCam[Side], Setup.Shoulder[Side]));
				Reach[Side] = FVector::Dist(ShCam[Side], WristCam[Side]);
				Elbow[Side] = FMath::RadiansToDegrees(FMath::Acos(FMath::Clamp((L1b * L1b + L2b * L2b - Reach[Side] * Reach[Side]) / (2.0 * L1b * L2b), -1.0, 1.0)));
			}
			const double RightErr = FVector::Dist(Solved[5].GetLocation(), CS[Bones.Hand[AstraArms::Right]].GetLocation());
			if (!DumpPath.IsEmpty())
			{
				FpsDumpState(StatesOut, Who + TEXT("|") + St.Name, Who + TEXT("_idle@0.00"), Loc, Rot, Bones, Ref, Solved, W.FpFov);
			}
			// the left grip socket follows its hand
			const FTransform HandAnim = CS[Bones.Hand[AstraArms::Left]];
			const FVector SockLNow = Solved[2].TransformPosition(HandAnim.InverseTransformPosition(SockL.GetLocation()));
			const double GripErr = FVector::Dist(SockLNow, Wanted0);
			const FString Tag = FString::Printf(TEXT("%s %s"), W.Name, St.Name);
			BCheck(Id == EAstraWeapon::Rifle ? (St.Name[0] == 'h' ? "fps: rifle at the hip" : (St.Name[0] == 's' ? "fps: rifle through the sights" : "fps: rifle lowered"))
			                                  : (St.Name[0] == 'h' ? "fps: pistol at the hip" : (St.Name[0] == 's' ? "fps: pistol through the sights" : "fps: pistol lowered")),
				FVector::Dist(SightCam, St.Target) < 0.01 && LenErr < 0.05 && RightErr < 0.01 && ShErr < 0.1 && GripErr < 1.5,
				FString::Printf(TEXT("%s: the sight is %.3f cm from where it is put, bones keep their lengths to %.3f cm, shoulders %.2f cm off, right wrist %.3f cm off, left palm %.2f cm from the grip"),
					*Tag, FVector::Dist(SightCam, St.Target), LenErr, ShErr, RightErr, GripErr));
			BNote(FString::Printf(TEXT("  %-14s elbows: left %3.0f deg (wrist %.0f cm from its shoulder at (%.0f, %.0f, %.0f)), right %3.0f deg (%.0f cm, shoulder at (%.0f, %.0f, %.0f))"), *Tag, Elbow[AstraArms::Left], Reach[AstraArms::Left],
				ShCam[AstraArms::Left].X, ShCam[AstraArms::Left].Y, ShCam[AstraArms::Left].Z, Elbow[AstraArms::Right], Reach[AstraArms::Right], ShCam[AstraArms::Right].X, ShCam[AstraArms::Right].Y, ShCam[AstraArms::Right].Z));
			// the cut ends of the arms must not show: a shoulder joint stands outside the picture (the taller 16:10 one) by more than what the mesh reaches beyond it and is across (11 cm)
			{
				const double TanH = FMath::Tan(FMath::DegreesToRadians(W.FpFov * 0.5)), TanV = TanH / 1.6;
				for (int32 Side = 0; Side < 2; ++Side)
				{
					const double Out = FpsOutside(ShCam[Side], TanH, TanV);
					if (Out < WorstOutside)
					{
						WorstOutside = Out;
						WorstWhere = FString::Printf(TEXT("%s, the %s one at (%.0f, %.0f, %.0f)"), St.Name, Side == AstraArms::Left ? TEXT("left") : TEXT("right"), ShCam[Side].X, ShCam[Side].Y, ShCam[Side].Z);
					}
				}
			}
			// what the picture holds, at 16:9 and at 16:10 (a laptop's own screen), with the first-person field of the weapon
			for (const double Aspect : {16.0 / 9.0, 16.0 / 10.0})
			{
				FFpsView V;
				V.HalfH = FMath::Tan(FMath::DegreesToRadians(W.FpFov * 0.5f));
				V.HalfV = V.HalfH / Aspect;
				bool bSight, bMuz, bGrip, bHandL, bHandR;
				const FString SightS = FpsWhere(SightCam, V, bSight);
				const FString MuzS = FpsWhere(Rot.RotateVector(SockR.TransformPosition(W.Muzzle)) + Loc, V, bMuz);
				const FString GripS = FpsWhere(Rot.RotateVector(SockLNow) + Loc, V, bGrip);
				const FString HandLS = FpsWhere(Rot.RotateVector(Solved[2].GetLocation()) + Loc, V, bHandL);
				const FString HandRS = FpsWhere(Rot.RotateVector(Solved[5].GetLocation()) + Loc, V, bHandR);
				if (Aspect > 1.7)
				{
					BNote(FString::Printf(TEXT("  %-14s rear sight %s; muzzle %s; left palm %s; left wrist %s; right wrist %s"), *Tag, *SightS, *MuzS, *GripS, *HandLS, *HandRS));
				}
				if (St.Name[0] == 'h')
				{
					BCheck(Aspect > 1.7 ? (Id == EAstraWeapon::Rifle ? "fps: rifle hip view 16:9" : "fps: pistol hip view 16:9") : (Id == EAstraWeapon::Rifle ? "fps: rifle hip view 16:10" : "fps: pistol hip view 16:10"),
						bSight && bMuz && bGrip && bHandR, FString::Printf(TEXT("%s at the hip, %.0f deg first-person field, %s screen: the sight, the muzzle, the left palm and the right wrist are in the picture (%s / %s / %s / %s)"), W.Name,
							W.FpFov, Aspect > 1.7 ? TEXT("16:9") : TEXT("16:10"), bSight ? TEXT("sight yes") : TEXT("sight NO"), bMuz ? TEXT("muzzle yes") : TEXT("muzzle NO"), bGrip ? TEXT("palm yes") : TEXT("palm NO"), bHandR ? TEXT("wrist yes") : TEXT("wrist NO")));
				}
			}
			if (St.Name[0] == 's')
			{
				// the sights: the rear sight's point on the camera's axis
				BCheck(Id == EAstraWeapon::Rifle ? "fps: rifle sight on the axis" : "fps: pistol sight on the axis", FMath::Abs(SightCam.Y) < 0.01 && FMath::Abs(SightCam.Z) < 0.01 && SightCam.X > 15.0,
					FString::Printf(TEXT("%s: rear sight at (%.2f, %.2f, %.2f) cm of the camera (0, 0 to the axis when aimed)"), W.Name, SightCam.X, SightCam.Y, SightCam.Z));
			}
		}
		// the way from the hip to the sights: the weapon's place and the shoulders slide together (as the component blends them); a shoulder must not pass through the picture on the way
		{
			FVector LocHip, LocAds, SightMesh;
			FQuat RotHip, RotAds;
			AstraArms::PlaceWeapon(SockR.GetLocation(), SockR.GetRotation(), W.Sight, W.HipPlace, W.HipTurn, LocHip, RotHip, SightMesh);
			AstraArms::PlaceWeapon(SockR.GetLocation(), SockR.GetRotation(), W.Sight, W.AdsPlace, FRotator::ZeroRotator, LocAds, RotAds, SightMesh);
			const double TanH = FMath::Tan(FMath::DegreesToRadians(W.FpFov * 0.5)), TanV = TanH / 1.6;
			for (int32 k = 1; k < 20; ++k)
			{
				const float A = k / 20.f;
				const FQuat Rot = FQuat::Slerp(RotHip, RotAds, A);
				const FVector Loc = FMath::Lerp(LocHip, LocAds, (double)A);
				AstraArms::FSetup Setup;
				ShouldersAt(A, Setup.Shoulder[AstraArms::Right], Setup.Shoulder[AstraArms::Left]);
				Setup.LeftHandDelta = Wanted0 - SockL.GetLocation();
				FTransform Solved[6];
				AstraArms::SolveBoth(Bones, CS, Rot, Loc, Setup, Solved);
				for (int32 Side = 0; Side < 2; ++Side)
				{
					const FVector Sh = Rot.RotateVector(Solved[Side * 3].GetLocation()) + Loc;
					const double Out = FpsOutside(Sh, TanH, TanV);
					if (Out < WorstOutside)
					{
						WorstOutside = Out;
						WorstWhere = FString::Printf(TEXT("%.0f %% of the way to the sights, the %s one at (%.0f, %.0f, %.0f)"), A * 100.f, Side == AstraArms::Left ? TEXT("left") : TEXT("right"), Sh.X, Sh.Y, Sh.Z);
					}
				}
			}
		}
		BCheck(Id == EAstraWeapon::Rifle ? "fps: rifle shoulders out of the picture" : "fps: pistol shoulders out of the picture", WorstOutside >= 11.0,
			FString::Printf(TEXT("%s: the nearest a shoulder joint comes to the picture (16:10, %.0f deg) in any state and on the way to the sights is %.1f cm outside it (at %s; the cut end of an arm reaches 11 cm from the joint)"), W.Name, W.FpFov, WorstOutside, *WorstWhere));
		// the animations that move the arms: drawing, reloading, the dry fire: the arms solved in every frame, nothing broken
		const struct { const TCHAR* Path; const TCHAR* Name; const TCHAR* Tag; } Moves[3] = {{W.AnimEquip, TEXT("draw"), TEXT("equip")}, {W.AnimReload, TEXT("reload"), TEXT("reload")}, {W.AnimDry, TEXT("dry fire"), TEXT("dry")}};
		for (const auto& M : Moves)
		{
			UAnimSequence* A = LoadObject<UAnimSequence>(nullptr, M.Path);
			if (!A)
			{
				continue;
			}
			int32 Frames = 0, Bad = 0, Short = 0;
			double Worst = 0.0;
			FVector Loc;
			FQuat Rot;
			FVector SightMesh;
			AstraArms::PlaceWeapon(SockR.GetLocation(), SockR.GetRotation(), W.Sight, W.HipPlace, W.HipTurn, Loc, Rot, SightMesh);
			for (int32 k = 0; k <= 12; ++k)
			{
				TArray<FTransform> L2, C2;
				FpsEvalPose(Mesh, A, A->GetPlayLength() * k / 12.0, L2);
				AstraArms::ComponentSpace(Ref, L2, C2);
				if (!DumpPath.IsEmpty())
				{
					FpsDumpPose(Dump, FString::Printf(TEXT("%s_%s@%.2f"), *Who, M.Tag, A->GetPlayLength() * k / 12.0), A->GetPlayLength() * k / 12.0, Mesh, C2);
				}
				AstraArms::FSetup Setup;
				Setup.Shoulder[AstraArms::Left] = ShoulderL;
				Setup.Shoulder[AstraArms::Right] = ShoulderR;
				if (const FVector* P = Set.Find(TEXT("pole_l"))) { Setup.Pole[AstraArms::Left] = *P; }
				if (const FVector* P = Set.Find(TEXT("pole_r"))) { Setup.Pole[AstraArms::Right] = *P; }
				FTransform Solved[6];
				AstraArms::SolveBoth(Bones, C2, Rot, Loc, Setup, Solved);
				if (!DumpPath.IsEmpty())
				{
					const FString PoseKey = FString::Printf(TEXT("%s_%s@%.2f"), *Who, M.Tag, A->GetPlayLength() * k / 12.0);
					FpsDumpState(StatesOut, Who + TEXT("|") + PoseKey, PoseKey, Loc, Rot, Bones, Ref, Solved, W.FpFov);
				}
				++Frames;
				bool bNan = false;
				for (const FTransform& T : Solved)
				{
					bNan |= T.ContainsNaN() || !T.IsRotationNormalized();
				}
				Bad += bNan ? 1 : 0;
				for (int32 Side = 0; Side < 2; ++Side)
				{
					const double Err = FVector::Dist(Solved[Side * 3 + 2].GetLocation(), C2[Bones.Hand[Side]].GetLocation());
					Worst = FMath::Max(Worst, Err);
					Short += Err > 1.0 ? 1 : 0;
				}
			}
			BCheck("fps: the arms through the animations", Bad == 0, FString::Printf(TEXT("%s %s: %d frames solved, %d broken, the hands come %d times of %d (worst %.1f cm) short of where the animation has them (the shoulders are fixed: the arms reach what they can)"),
				W.Name, M.Name, Frames, Bad, Short, Frames * 2, Worst));
		}
	}
	if (!DumpPath.IsEmpty())
	{
		FFileHelper::SaveStringToFile(TEXT("{\"poses\":{") + Dump + TEXT("},\n\"states\":{") + StatesOut + TEXT("}}"), *DumpPath);
		BNote(FString::Printf(TEXT("  the engine's poses written to %s"), *DumpPath));
	}
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
	// a boarding by boats carries its wounded out: a free comrade comes, gets him up (he stops bleeding), takes him to the hatch and the boat; the same man with nobody to come bled out above
	{
		FAstraBoardSim Sim;
		Sim.Init(Rig.Map.ToSharedRef(), Seed);
		Sim.Tuning = Rig.Tuning;
		Sim.Tuning.bEvacuate = true;
		const FVector Hatch(Lane.Start.X + 300.0, 0.0, Lane.Start.Z);
		Sim.SetMission(ESide::Aquila, Lane.FirstComp, Hatch, INDEX_NONE);
		const int32 Sq = Sim.AddSquad(ESide::Aquila, TEXT("A"));
		TArray<int32> Men;
		for (int32 k = 0; k < 8; ++k)
		{
			Men.Add(Sim.AddMarine(TEXT("M"), INDEX_NONE, FVector(Lane.Start.X + 600.0 + 120.0 * k, 0, Lane.Start.Z), k == 0, Sq));
		}
		int32 Fallen = INDEX_NONE;
		for (int32 k = 1; k < Men.Num() && Fallen == INDEX_NONE; ++k)
		{
			for (int32 h = 0; h < 9; ++h) { Sim.HitUnit(Men[k], 17.f, false); }
			Fallen = Sim.Unit(Men[k])->Act == EAct::Down ? Men[k] : INDEX_NONE;
		}
		double OutAt = -1.0;
		bool bDied = false;
		while (Fallen != INDEX_NONE && Sim.Time() < 240.0 && OutAt < 0.0)
		{
			Sim.Tick(0.5f);
			bDied |= Sim.Unit(Fallen)->Act == EAct::Dead;
			OutAt = Sim.Unit(Fallen)->Act == EAct::Gone ? Sim.Time() : -1.0;
		}
		BCheck("wounds: carried out", Fallen != INDEX_NONE && !bDied && OutAt > 0.0 && Sim.Book().Carried[0] == 1 && Sim.Book().Down[0] == 0,
		       FString::Printf(TEXT("a man down with comrades about was carried to the hatch and out in %.0f s (%d carried, %d still down)"), OutAt, Sim.Book().Carried[0], Sim.Book().Down[0]));
	}
	// a sealed bulkhead: the Mandate cut through it (a pressure bulkhead of Deck 8 with a room each side, every pressure bulkhead of the deck sealed: the nearest is the cheapest way through)
	{
		const FAstraBoardMap& M = *Rig.Map;
		int32 Blast = INDEX_NONE, A = INDEX_NONE, B = INDEX_NONE;
		for (const FBoardPortal& P : M.GetPortals())
		{
			if (P.Kind == FBoardPortal::EKind::Blast && !P.bVertical() && M.GetComps()[P.A].Deck == 8 && M.GetComps()[P.B].Deck == 8 && P.Door != INDEX_NONE)
			{
				Blast = P.Door;
				A = P.A;
				B = P.B;
				break;
			}
		}
		FBoardDoors Doors;
		Doors.Init(M.NumDoors());
		TArray<int32> Line;
		for (const FBoardPortal& Q : M.GetPortals())
		{
			if (Q.Kind == FBoardPortal::EKind::Blast && !Q.bVertical() && M.GetComps()[Q.A].Deck == 8 && Q.Door != INDEX_NONE)
			{
				Line.AddUnique(Q.Door);
				Doors.Sealed[Q.Door] = true;
			}
		}
		bool bStops = false, bCut = false;
		double CutT = -1.0;
		if (Blast != INDEX_NONE)
		{
			FBoardRouteOptions Opt;
			Opt.bStairs = false;
			Opt.Doors = &Doors;
			TArray<FVector> Pts;
			bStops = !M.Route(M.CentreOf(A), M.CentreOf(B), Pts, Opt);
			BNote(FString::Printf(TEXT("%d pressure bulkheads of Deck 8 sealed; from %s to %s without cutting: %s"), Line.Num(), *M.Describe(A), *M.Describe(B), bStops ? TEXT("no way") : TEXT("a way round (the plan has more than one)")));
			// the Mandate walk up to it and cut
			FAstraBoardSim Sim;
			Sim.Init(Rig.Map.ToSharedRef(), Seed);
			Sim.Tuning = Rig.Tuning;
			for (const int32 D : Line) { Sim.SealDoor(D, true); }
			const int32 SqM = Sim.AddSquad(ESide::Mandate, TEXT("M"));
			Sim.AddUnit(ESide::Mandate, ERole::Leader, TEXT("M"), M.CentreOf(A), SqM);
			Sim.Order(SqM, ETask::Advance, B, M.CentreOf(B), 100.f);
			Sim.SquadMutable(SqM)->bOrdered = true;
			while (Sim.Time() < 200.0 && !bCut)
			{
				Sim.Tick(0.5f);
				for (const int32 D : Line)
				{
					if (!Sim.IsDoorSealed(D))
					{
						bCut = true;
						CutT = Sim.Time();
						break;
					}
				}
			}
		}
		BCheck("bulkhead: sealed, then cut", Blast != INDEX_NONE && bCut && CutT > 8.0, FString::Printf(TEXT("the Mandate cut through a sealed pressure bulkhead after %.0f s"), CutT));
	}
	// determinism: the same fight twice
	{
		const FBoardFight A = RunBoarding(Rig, Seed, 10, 24, 12, *BenchBreach(Rig), TEXT("engineering"), false, 25.f);
		const FBoardFight B = RunBoarding(Rig, Seed, 10, 24, 12, *BenchBreach(Rig), TEXT("engineering"), false, 25.f);
		BCheck("deterministic from the seed", A.bFound && A.R.Hash == B.R.Hash && A.R.Outcome == B.R.Outcome, FString::Printf(TEXT("hash %08x and %08x, %s"), A.R.Hash, B.R.Hash, OutcomeName(A.R.Outcome)));
	}
}

// ================================================================================================================== the plans of other ships and the fights on them (F5.2)

static void BoardScenarioPlans(const FString& Only)
{
	TArray<FName> Classes;
	AstraBoardPlans::ClassesWithPlans(Classes);
	if (!Only.IsEmpty())
	{
		Classes = {FName(*Only)};
	}
	if (Classes.IsEmpty())
	{
		BCheck("plan of a class", false, TEXT("no plans in data/ship/plans (FLOTTA-VIVA's: art/blender/ship_class_plans.py)"));
		return;
	}
	for (const FName& K : Classes)
	{
		FString Why;
		const TSharedPtr<FBoardShipPlan> P = AstraBoardPlans::Load(K, Why);
		if (!P.IsValid())
		{
			BCheck("plan of a class", false, FString::Printf(TEXT("%s: %s"), *K.ToString(), *Why));
			continue;
		}
		const FAstraBoardMap& M = *P->Map;
		struct FPlace { const TCHAR* Name; const TCHAR* Kind; bool bNeeded; };
		const FPlace Places[] = {{TEXT("bridge"), TEXT("bridge"), true}, {TEXT("engineering"), TEXT("engineering"), true}, {TEXT("captain"), TEXT("quarters"), true}, {TEXT("armory"), TEXT("armory"), false},
		                         {TEXT("medbay"), TEXT("medbay"), false}, {TEXT("brig"), TEXT("brig"), false}, {TEXT("comms"), TEXT("comms"), false}, {TEXT("hangar"), TEXT("hangar"), false}};
		int32 Missing = 0, NoWay = 0, Routes = 0;
		double Metres = 0.0, MaxMetres = 0.0;
		FString Lines;
		for (const FPlace& Pl : Places)
		{
			const int32 C = P->Objective(Pl.Name, Pl.Kind);
			if (C == INDEX_NONE)
			{
				Missing += Pl.bNeeded ? 1 : 0;
				continue;
			}
			double Best = 1.0e9;
			for (const FBoardShipPlan::FDock& D : P->Docks)
			{
				TArray<FVector> Pts;
				float Len = 0.f;
				FBoardRouteOptions Opt;
				Opt.bThroughSealed = true;
				if (M.Route(M.Inset(D.Comp, D.Pos, 70.f), M.CentreOf(C), Pts, Opt, &Len))
				{
					++Routes;
					Metres += Len;
					MaxMetres = FMath::Max(MaxMetres, (double)Len);
					Best = FMath::Min(Best, (double)Len);
				}
				else
				{
					++NoWay;
				}
			}
			Lines += FString::Printf(TEXT(" %s %.0f m;"), Pl.Name, Best < 1.0e8 ? Best : -1.0);
		}
		int32 BadPortal = 0;
		for (const FBoardPortal& Po : M.GetPortals())
		{
			if (Po.bVertical())
			{
				continue;
			}
			const FBox A = M.GetComps()[Po.A].Box.ExpandBy(70.0), B = M.GetComps()[Po.B].Box.ExpandBy(70.0);
			BadPortal += (!A.IsInsideOrOn(Po.Pos + FVector(0, 0, 50)) || !B.IsInsideOrOn(Po.Pos + FVector(0, 0, 50))) ? 1 : 0;
		}
		const bool bOk = Missing == 0 && NoWay == 0 && P->Docks.Num() >= 2 && BadPortal <= M.GetPortals().Num() / 50;
		BCheck("plan of a class", bOk, FString::Printf(TEXT("%s: %d compartments, %d portals (%d off their faces), %d docks, %d posts, crew %d; shortest way from a dock:%s the longest %.0f m (%d missing, %d without a way)"),
			*K.ToString(), M.GetComps().Num(), M.GetPortals().Num(), BadPortal, P->Docks.Num(), P->Garrison.Num(), P->Crew, *Lines, MaxMetres, Missing, NoWay));
		(void)Metres;
		(void)Routes;
	}
}

// ================================================================================================================== the inside of a boarded ship as solid geometry (F5.2: the Captain goes along)

/** Every room of a class's plan made solid, and the simulation's own routes walked through it: a way a marine runs that meets a wall (a door whose gap is not where the plan puts it) is a fault of the builder. */
static void BoardScenarioInterior(const FString& Only, const FString& DumpDir, int32 Seed)
{
	TArray<FName> Classes;
	AstraBoardPlans::ClassesWithPlans(Classes);
	if (!Only.IsEmpty())
	{
		Classes = {FName(*Only)};
	}
	for (const FName& K : Classes)
	{
		FString Why;
		const TSharedPtr<FBoardShipPlan> P = AstraBoardPlans::Load(K, Why);
		if (!P.IsValid())
		{
			BCheck("interior of a class", false, FString::Printf(TEXT("%s: %s"), *K.ToString(), *Why));
			continue;
		}
		const FAstraBoardMap& M = *P->Map;
		const double T0 = FPlatformTime::Seconds();
		TArray<AstraBoardInterior::FSlab> Slabs;
		int32 PerKind[AstraBoardInterior::NumSlabKinds] = {0, 0, 0, 0, 0, 0, 0};
		for (int32 i = 0; i < M.GetComps().Num(); ++i)
		{
			AstraBoardInterior::BuildComp(M, i, Slabs);
		}
		for (const AstraBoardInterior::FSlab& S : Slabs)
		{
			++PerKind[(int32)S.Kind];
		}
		const double BuildMs = (FPlatformTime::Seconds() - T0) * 1000.0;
		TSet<int32> OpenDoors;                                         // the doors the fight opens or cuts: their leaves are not walls to a route that goes through them
		for (int32 d = 0; d < P->Dmg->Doors.Num(); ++d)
		{
			OpenDoors.Add(d);
		}
		// the ways: each portal of the plan, walked from the middle of one room through its middle to the middle of the other, at a man's knee and at his chest: a gap that is not where the
		// plan puts its door, or too narrow for a man, or a second wall in the way, shows here (the legs end on the doorway's own face: nothing along a wall is tried)
		int32 Ways = 0, Blocked = 0, Narrow = 0;
		FString First;
		for (const FBoardPortal& Po : M.GetPortals())
		{
			if (Po.bVertical())
			{
				continue;
			}
			++Ways;
			Narrow += Po.Half * 2.f < 90.f ? 1 : 0;
			const FVector Mid(Po.Pos.X, Po.Pos.Y, FMath::Max(M.GetComps()[Po.A].FloorZ(), M.GetComps()[Po.B].FloorZ()));
			// a point a step either side of the doorway, on the line through its middle along its normal
			const FVector2D N = Po.Normal;
			const FVector SideA = Mid - FVector(N.X, N.Y, 0.0) * 130.0, SideB = Mid + FVector(N.X, N.Y, 0.0) * 130.0;
			// a way through within the doorway's width: five lines side by side along it, one must be free at a man's knee and chest
			const FVector Al(Po.Along.X, Po.Along.Y, 0.0);
			bool bBlock = true;
			const AstraBoardInterior::FSlab* Hit = nullptr;
			for (int32 k = -2; k <= 2 && bBlock; ++k)
			{
				const FVector Shift = Al * (Po.Half * 0.9 * k / 2.0);
				bool bThis = false;
				for (const double Up : {40.0, 120.0})
				{
					bThis |= AstraBoardInterior::SegmentBlocked(Slabs, SideA + Shift + FVector(0, 0, Up), SideB + Shift + FVector(0, 0, Up), &OpenDoors, &Hit);
				}
				bBlock = bThis;
			}
			if (bBlock)
			{
				++Blocked;
				if (First.IsEmpty())
				{
					static const TCHAR* Kinds[] = {TEXT("wall"), TEXT("floor"), TEXT("ceiling"), TEXT("frame"), TEXT("bulkhead leaf"), TEXT("strip"), TEXT("mark")};
					First = FString::Printf(TEXT("the way between %s and %s at (%.0f, %.0f, %.0f), stopped by a %s of %s at (%.0f, %.0f, %.0f) half (%.0f, %.0f, %.0f)"), *M.Describe(Po.A), *M.Describe(Po.B), Po.Pos.X, Po.Pos.Y, Po.Pos.Z,
					                        Hit ? Kinds[(int32)Hit->Kind] : TEXT("?"), Hit ? *M.Describe(Hit->Comp) : TEXT("?"), Hit ? Hit->Centre.X : 0.0, Hit ? Hit->Centre.Y : 0.0, Hit ? Hit->Centre.Z : 0.0,
					                        Hit ? Hit->Half.X : 0.0, Hit ? Hit->Half.Y : 0.0, Hit ? Hit->Half.Z : 0.0);
				}
			}
		}
		// and a wall is a wall: from the middle of a room to a point outside its box through a side with no portal is stopped
		int32 Leaks = 0, Tried = 0;
		FRandomStream Rng(Seed);
		for (int32 n = 0; n < 400 && M.GetComps().Num() > 2; ++n)
		{
			const int32 Ci = Rng.RandHelper(M.GetComps().Num());
			const FBox& B = M.GetComps()[Ci].Box;
			if (B.GetSize().X < 200.0 || B.GetSize().Y < 200.0)
			{
				continue;
			}
			const int32 Side = Rng.RandHelper(4);
			const double Along = Rng.FRandRange(0.15f, 0.85f);
			const FVector C = B.GetCenter();
			FVector Out;
			bool bHasPortal = false;
			for (const int32 Pi : M.GetComps()[Ci].Portals)
			{
				const FBoardPortal& Po = M.GetPortals()[Pi];
				if (Po.bVertical())
				{
					continue;
				}
				const double Dx = Side < 2 ? FMath::Abs(Po.Pos.X - (Side == 0 ? B.Max.X : B.Min.X)) : 1.0e9, Dy = Side >= 2 ? FMath::Abs(Po.Pos.Y - (Side == 2 ? B.Max.Y : B.Min.Y)) : 1.0e9;
				bHasPortal |= FMath::Min(Dx, Dy) < 120.0;
			}
			if (bHasPortal)
			{
				continue;                                            // (a side with a doorway is not solid all along)
			}
			const FVector A(C.X, C.Y, B.Min.Z + 90.0);
			Out = Side < 2 ? FVector(Side == 0 ? B.Max.X + 60.0 : B.Min.X - 60.0, FMath::Lerp(B.Min.Y, B.Max.Y, Along), A.Z) : FVector(FMath::Lerp(B.Min.X, B.Max.X, Along), Side == 2 ? B.Max.Y + 60.0 : B.Min.Y - 60.0, A.Z);
			++Tried;
			Leaks += AstraBoardInterior::SegmentBlocked(Slabs, A, Out, &OpenDoors) ? 0 : 1;
		}
		BCheck("interior of a class", Blocked == 0 && Leaks == 0 && Ways > 20 && PerKind[(int32)AstraBoardInterior::ESlab::Wall] > M.GetComps().Num(),
		       FString::Printf(TEXT("%s: %d rooms made solid in %.0f ms: %d solids (%d walls, %d floors and ceilings, %d frames, %d bulkhead leaves, %d strips of light); %d doorways and openings walked through: %d meet a wall (%d too narrow for a man); %d walls tried: %d leak%s%s"),
		                       *K.ToString(), M.GetComps().Num(), BuildMs, Slabs.Num(), PerKind[0], PerKind[1] + PerKind[2], PerKind[3], PerKind[4], PerKind[5], Ways, Blocked, Narrow, Tried, Leaks,
		                       First.IsEmpty() ? TEXT("") : TEXT(": "), *First));
		if (!DumpDir.IsEmpty())
		{
			// the solids as numbers, for the offline view (Saved/scratch/interior_view.py): kind, centre, half sizes (cm)
			TArray<TSharedPtr<FJsonValue>> List;
			for (const AstraBoardInterior::FSlab& S : Slabs)
			{
				TArray<TSharedPtr<FJsonValue>> Row;
				Row.Add(MakeShared<FJsonValueNumber>((int32)S.Kind));
				for (const double V : {S.Centre.X, S.Centre.Y, S.Centre.Z, S.Half.X, S.Half.Y, S.Half.Z})
				{
					Row.Add(MakeShared<FJsonValueNumber>(FMath::RoundToInt(V * 10.0) / 10.0));
				}
				Row.Add(MakeShared<FJsonValueNumber>(S.Comp));
				List.Add(MakeShared<FJsonValueArray>(Row));
			}
			TSharedRef<FJsonObject> O = MakeShared<FJsonObject>();
			O->SetStringField(TEXT("class"), K.ToString());
			O->SetArrayField(TEXT("slabs"), List);
			TArray<TSharedPtr<FJsonValue>> Docks;
			for (const FBoardShipPlan::FDock& D : P->Docks)
			{
				// where the boarders come in: the hatch's point on the skin put inside its room (the same the scene does)
				FVector In = M.Inset(D.Comp, D.Pos, 70.f);
				In.Z = M.GetComps()[D.Comp].FloorZ();
				TArray<TSharedPtr<FJsonValue>> Row;
				for (const double V : {In.X, In.Y, In.Z})
				{
					Row.Add(MakeShared<FJsonValueNumber>(V));
				}
				Docks.Add(MakeShared<FJsonValueArray>(Row));
			}
			O->SetArrayField(TEXT("docks"), Docks);
			const FString Path = FPaths::IsRelative(DumpDir) ? FPaths::Combine(FPaths::ProjectDir(), DumpDir) : DumpDir;
			IFileManager::Get().MakeDirectory(*Path, true);
			FFileHelper::SaveStringToFile(Json(O), *FPaths::Combine(Path, FString::Printf(TEXT("interior_%s.json"), *K.ToString())));
		}
	}
}

// ================================================================================================================== the dressing of the decks (ABBORDAGGI-3)

namespace
{
	bool BDressSegHitsBox(const FVector2D& A, const FVector2D& B, const FBox2D& Box)
	{
		double T0 = 0.0, T1 = 1.0;
		const FVector2D D = B - A;
		for (int32 Axis = 0; Axis < 2; ++Axis)
		{
			const double Da = Axis == 0 ? D.X : D.Y, Aa = Axis == 0 ? A.X : A.Y, Lo = Axis == 0 ? Box.Min.X : Box.Min.Y, Hi = Axis == 0 ? Box.Max.X : Box.Max.Y;
			if (FMath::Abs(Da) < 1.0e-9)
			{
				if (Aa < Lo || Aa > Hi)
				{
					return false;
				}
				continue;
			}
			double Ta = (Lo - Aa) / Da, Tb = (Hi - Aa) / Da;
			if (Ta > Tb)
			{
				Swap(Ta, Tb);
			}
			T0 = FMath::Max(T0, Ta);
			T1 = FMath::Min(T1, Tb);
			if (T0 > T1)
			{
				return false;
			}
		}
		return true;
	}

	/** A rough hash of what a room's dressing is (positions to the centimetre, pieces, turns): two dressings of the same room must agree. */
	uint32 BDressHash(const AstraBoardDress::FRoomDress& R)
	{
		uint32 H = 17u;
		for (const AstraBoardDress::FPlacement& P : R.Pieces)
		{
			H = HashCombineFast(H, (uint32)P.Piece);
			H = HashCombineFast(H, (uint32)FMath::RoundToInt(P.Pos.X) * 31u + (uint32)FMath::RoundToInt(P.Pos.Y) * 17u + (uint32)FMath::RoundToInt(P.Pos.Z));
			H = HashCombineFast(H, (uint32)FMath::RoundToInt(P.Rot.Yaw * 4.f));
			H = HashCombineFast(H, (uint32)FMath::RoundToInt(P.Scale.X * 100.0) * 7u + (uint32)FMath::RoundToInt(P.Scale.Z * 100.0));
		}
		H = HashCombineFast(H, (uint32)R.Lamps.Num() * 131u + (uint32)R.Blocks.Num() * 17u + (uint32)R.Fx.Num());
		return H;
	}
}

/** Every room of a class dressed: what it costs (instances and triangles for the ship, for each deck and in the ring of rooms round a Captain, against the plain boxes of before), that the soldiers' ways are
 *  clear of every prop, that every door has its frame and its sign, that a room is always dressed the same, that nobody is placed in a prop. */
static void BoardScenarioDress(const FString& Only, const FString& DumpDir, const FString& Focus, bool bDumpHurt, int32 Seed)
{
	using namespace AstraBoardDress;
	const FString KitWhy = CheckKit();
	BCheck("dress: the kit and the catalog", KitWhy.IsEmpty(), KitWhy.IsEmpty() ? FString(TEXT("every piece of the kit is in the catalog, with its footprint and its mesh's name")) : KitWhy);
	TArray<int32> TrisOf;
	FString TrisWhy;
	const bool bTris = LoadKitTris(TrisOf, TrisWhy);
	BCheck("dress: the kit's triangles", bTris, bTris ? FString(TEXT("known: the instances' triangles are counted")) : TrisWhy);
	TArray<FName> Classes;
	AstraBoardPlans::ClassesWithPlans(Classes);
	if (!Only.IsEmpty())
	{
		Classes = {FName(*Only)};
	}
	for (const FName& K : Classes)
	{
		FString Why;
		const TSharedPtr<FBoardShipPlan> P = AstraBoardPlans::Load(K, Why);
		if (!P.IsValid() || !P->Layout.IsValid())
		{
			BCheck("dress of a class", false, FString::Printf(TEXT("%s: %s"), *K.ToString(), P.IsValid() ? TEXT("no layout of props") : *Why));
			continue;
		}
		const FAstraBoardMap& M = *P->Map;
		const FLayout& Lay = *P->Layout;
		const int32 N = M.GetComps().Num();
		FDressContext Ctx;
		Ctx.Plan = P.Get();
		Ctx.Side = SideOfStyle(P->Style);
		Ctx.Seed = SeedOf(P->Class);
		Ctx.Level = 2;
		// the war's picture of her: a third of the rooms dark, an eighth burning, a few gutted (deterministic)
		TMap<int32, FBoardRoomMood> Moods;
		FRandomStream Rng(Seed + 91);
		for (int32 c = 0; c < N; ++c)
		{
			const float R = Rng.FRand();
			FBoardRoomMood Mo;
			if (R < 0.05f)
			{
				Mo.bGutted = true;
				Mo.Power = 0.f;
				Mo.Smoke = 0.4f;
			}
			else if (R < 0.17f)
			{
				Mo.Fire = Rng.FRandRange(0.15f, 0.8f);
				Mo.Smoke = Rng.FRandRange(0.3f, 0.9f);
				Mo.Power = 0.5f;
			}
			else if (R < 0.4f)
			{
				Mo.Power = 0.2f;
			}
			else
			{
				continue;
			}
			Moods.Add(c, Mo);
		}
		FDressContext Hurt = Ctx;
		Hurt.Moods = &Moods;
		FDressContext Hulk = Ctx;
		Hulk.bHulk = true;
		// ---- every room dressed: as she is built, hurt by the war, a hulk
		const double T0 = FPlatformTime::Seconds();
		TArray<FRoomDress> Built, War, Cold;
		Built.SetNum(N);
		War.SetNum(N);
		Cold.SetNum(N);
		for (int32 c = 0; c < N; ++c)
		{
			DressRoom(Ctx, &Lay, c, Built[c]);
		}
		const double BuiltMs = (FPlatformTime::Seconds() - T0) * 1000.0;
		for (int32 c = 0; c < N; ++c)
		{
			DressRoom(Hurt, &Lay, c, War[c]);
			DressRoom(Hulk, &Lay, c, Cold[c]);
		}
		// ---- the plain boxes of before
		TArray<AstraBoardInterior::FSlab> Slabs;
		TArray<int32> SlabFirst;
		for (int32 c = 0; c < N; ++c)
		{
			SlabFirst.Add(Slabs.Num());
			AstraBoardInterior::BuildComp(M, c, Slabs);
		}
		SlabFirst.Add(Slabs.Num());
		const auto PlainRendered = [&](int32 C) -> int32               // boxes that are drawn without the kit: walls, floors, ceilings, frames, leaves, strips
		{
			return SlabFirst[C + 1] - SlabFirst[C];
		};
		const auto SlabsDrawnAfter = [&](int32 C) -> int32             // ... and with it: the frames, the leaves and the strips are not drawn
		{
			int32 Drawn = 0;
			for (int32 i = SlabFirst[C]; i < SlabFirst[C + 1]; ++i)
			{
				const AstraBoardInterior::ESlab Kd = Slabs[i].Kind;
				Drawn += (Kd == AstraBoardInterior::ESlab::Wall || Kd == AstraBoardInterior::ESlab::Floor || Kd == AstraBoardInterior::ESlab::Ceiling) ? 1 : 0;
			}
			return Drawn;
		};
		// ---- the totals, by deck
		FTally All, AllWar, AllCold;
		TMap<int32, FTally> ByDeck;
		TMap<int32, int32> PlainByDeck, SlabsByDeck;
		int32 Props = 0, Rooms = 0, Dressed = 0;
		for (int32 c = 0; c < N; ++c)
		{
			All.Add(Built[c], TrisOf);
			AllWar.Add(War[c], TrisOf);
			AllCold.Add(Cold[c], TrisOf);
			ByDeck.FindOrAdd(P->Dmg->Comps[c].Deck).Add(Built[c], TrisOf);
			PlainByDeck.FindOrAdd(P->Dmg->Comps[c].Deck) += PlainRendered(c);
			SlabsByDeck.FindOrAdd(P->Dmg->Comps[c].Deck) += SlabsDrawnAfter(c);
			Props += Lay.PropsOf(c).Num();
			Rooms += M.GetComps()[c].bCorridor ? 0 : 1;
			Dressed += Built[c].Pieces.Num() > 0 ? 1 : 0;
		}
		// ---- the ring round a Captain: the rooms EnsureAround would have built (the same deck, within 48 m), the worst and the mean over the ship's places
		struct FRing { int32 Rooms = 0, Instances = 0, Plain = 0, Boxes = 0; int64 Tris = 0; };
		FRing Worst, Sum;
		int32 Samples = 0;
		TArray<int32> Picks;
		for (int32 c = 0; c < N; c += FMath::Max(1, N / 48))
		{
			Picks.Add(c);
		}
		for (const int32 Pc : Picks)
		{
			const FVector At = M.CentreOf(Pc);
			FRing R;
			for (int32 c = 0; c < N; ++c)
			{
				const FBox& B = M.GetComps()[c].Box;
				if (FMath::Abs(B.Min.Z - At.Z) > 250.0 || FMath::Sqrt(B.ComputeSquaredDistanceToPoint(FVector(At.X, At.Y, B.GetCenter().Z))) >= 4800.0)
				{
					continue;
				}
				++R.Rooms;
				FTally T;
				T.Add(Built[c], TrisOf);
				R.Instances += T.TotalPieces() + SlabsDrawnAfter(c);
				R.Tris += T.Tris + 12LL * SlabsDrawnAfter(c);
				R.Plain += PlainRendered(c);
				R.Boxes += Built[c].Blocks.Num();
			}
			Sum.Rooms += R.Rooms;
			Sum.Instances += R.Instances;
			Sum.Tris += R.Tris;
			Sum.Plain += R.Plain;
			++Samples;
			if (R.Tris > Worst.Tris)
			{
				Worst = R;
			}
		}
		Samples = FMath::Max(1, Samples);
		// ---- the soldiers' ways: nothing the dressing puts in a room is on the way between its doors or to its middle, nor in a doorway's mouth, nor in a corner beside a doorway
		int32 LaneHits = 0, MouthHits = 0, SlotHits = 0, OutOfRoom = 0, Overlaps = 0, JambInProp = 0, BoxMismatch = 0;
		FString FirstFault;
		for (int32 c = 0; c < N; ++c)
		{
			const TArrayView<const FProp> Props2 = Lay.PropsOf(c);
			if (Props2.Num() == 0)
			{
				continue;
			}
			const FBoardComp& Cp = M.GetComps()[c];
			TArray<FVector2D> Pts;
			for (const int32 Pi : Cp.Portals)
			{
				const FBoardPortal& Po = M.GetPortals()[Pi];
				const FVector Q = Po.PosIn(c);
				Pts.Add(FVector2D(Q.X, Q.Y));
				for (const FProp& Pr : Props2)
				{
					if (Pr.Box.ExpandBy(55.0).IsInside(FVector2D(Q.X, Q.Y)))
					{
						++MouthHits;
						if (FirstFault.IsEmpty())
						{
							FirstFault = FString::Printf(TEXT("a %s stands in the mouth of the way at (%.0f, %.0f) of %s"), AstraBoardDress::Def(Pr.Piece).Key, Q.X, Q.Y, *M.Describe(c));
						}
					}
				}
			}
			const FVector Ctr = M.CentreOf(c);
			Pts.Add(FVector2D(Ctr.X, Ctr.Y));
			for (int32 i = 0; i < Pts.Num(); ++i)
			{
				for (int32 j = i + 1; j < Pts.Num(); ++j)
				{
					for (const FProp& Pr : Props2)
					{
						if (BDressSegHitsBox(Pts[i], Pts[j], Pr.Box.ExpandBy(45.0)))
						{
							++LaneHits;
							if (FirstFault.IsEmpty())
							{
								FirstFault = FString::Printf(TEXT("a %s is on the lane between (%.0f, %.0f) and (%.0f, %.0f) in %s"), AstraBoardDress::Def(Pr.Piece).Key, Pts[i].X, Pts[i].Y, Pts[j].X, Pts[j].Y, *M.Describe(c));
							}
						}
					}
				}
			}
			for (const int32 Si : Cp.Slots)
			{
				const FBoardSlot& S = M.GetSlots()[Si];
				for (const FProp& Pr : Props2)
				{
					SlotHits += (Pr.Box.ExpandBy(40.0).IsInside(FVector2D(S.Pos.X, S.Pos.Y)) || Pr.Box.ExpandBy(40.0).IsInside(FVector2D(S.Peek.X, S.Peek.Y))) ? 1 : 0;
				}
			}
			for (int32 i = 0; i < Props2.Num(); ++i)
			{
				const FBox& B = Cp.Box;
				const FBox2D& Bx = Props2[i].Box;
				OutOfRoom += (Bx.Min.X < B.Min.X + 12.0 || Bx.Min.Y < B.Min.Y + 12.0 || Bx.Max.X > B.Max.X - 12.0 || Bx.Max.Y > B.Max.Y - 12.0) ? 1 : 0;
				for (int32 j = i + 1; j < Props2.Num(); ++j)
				{
					Overlaps += Bx.Intersect(Props2[j].Box) ? 1 : 0;
				}
			}
			// the same boxes are in the map, for those who pick a spot in the room
			BoxMismatch += M.BlocksOf(c).Num() != Props2.Num() ? 1 : 0;
			for (const FPlacement& Pl : Built[c].Pieces)
			{
				if (Pl.Piece == EPiece::Jamb || Pl.Piece == EPiece::BlastJamb)
				{
					for (const FProp& Pr : Props2)
					{
						JambInProp += Pr.Box.ExpandBy(4.0).IsInside(FVector2D(Pl.Pos.X, Pl.Pos.Y)) ? 1 : 0;
					}
				}
			}
		}
		BCheck("dress: the soldiers' ways are clear", LaneHits == 0 && MouthHits == 0 && SlotHits == 0 && OutOfRoom == 0 && Overlaps == 0 && JambInProp == 0 && BoxMismatch == 0,
		       FString::Printf(TEXT("%s: %d props in %d rooms: %d on the lanes between doors, %d in a doorway's mouth, %d on a corner beside one, %d not inside their room's walls, %d on another, %d on a frame, %d rooms whose map boxes differ%s%s"),
		                       *K.ToString(), Props, Rooms, LaneHits, MouthHits, SlotHits, OutOfRoom, Overlaps, JambInProp, BoxMismatch, FirstFault.IsEmpty() ? TEXT("") : TEXT(": "), *FirstFault));
		// ---- nobody is placed in a prop: spots picked with Inset, and the fallen
		int32 InProp = 0, Tried = 0, FallenIn = 0, FallenOut = 0, Fell = 0;
		FString FirstIn;
		for (int32 n = 0; n < 4000; ++n)
		{
			const int32 c = Rng.RandHelper(N);
			if (M.BlocksOf(c).Num() == 0)
			{
				continue;
			}
			const FBox& B = M.GetComps()[c].Box;
			const FVector Raw(Rng.FRandRange(B.Min.X, B.Max.X), Rng.FRandRange(B.Min.Y, B.Max.Y), B.Min.Z);
			const FVector Q = M.Inset(c, Raw, 60.f);
			++Tried;
			for (const FBox2D& Bx : M.BlocksOf(c))
			{
				if (Bx.ExpandBy(-8.0).IsInside(FVector2D(Q.X, Q.Y)))
				{
					++InProp;
					if (FirstIn.IsEmpty())
					{
						FirstIn = FString::Printf(TEXT("%s: (%.0f, %.0f) went to (%.0f, %.0f) inside the box (%.0f, %.0f)-(%.0f, %.0f) of the room (%.0f, %.0f)-(%.0f, %.0f)"), *M.Describe(c), Raw.X, Raw.Y, Q.X, Q.Y, Bx.Min.X, Bx.Min.Y, Bx.Max.X, Bx.Max.Y,
						                          B.Min.X, B.Min.Y, B.Max.X, B.Max.Y);
					}
				}
			}
		}
		TArray<FFallen> Dead;
		for (int32 n = 0; n < 400; ++n)
		{
			const int32 c = Rng.RandHelper(N);
			const FBox& B = M.GetComps()[c].Box;
			Dead.Add({c, FVector(Rng.FRandRange(B.Min.X, B.Max.X), Rng.FRandRange(B.Min.Y, B.Max.Y), B.Min.Z), n});
		}
		TArray<FPlacement> Bodies;
		DressFallen(Ctx, Dead, Bodies);
		for (const FPlacement& Pl : Bodies)
		{
			const FBox& B = M.GetComps()[Pl.Comp].Box;
			FallenOut += (Pl.Pos.X < B.Min.X || Pl.Pos.X > B.Max.X || Pl.Pos.Y < B.Min.Y || Pl.Pos.Y > B.Max.Y) ? 1 : 0;
			for (const FBox2D& Bx : M.BlocksOf(Pl.Comp))
			{
				FallenIn += Bx.ExpandBy(-8.0).IsInside(FVector2D(Pl.Pos.X, Pl.Pos.Y)) ? 1 : 0;
			}
			++Fell;
		}
		BCheck("dress: nobody is placed in a prop", InProp == 0 && FallenIn == 0 && FallenOut == 0 && Fell == Dead.Num(),
		       FString::Printf(TEXT("%s: %d spots picked in dressed rooms (Inset): %d inside a prop; %d fallen laid: %d inside a prop, %d outside their room%s%s"), *K.ToString(), Tried, InProp, Fell, FallenIn, FallenOut,
		                       FirstIn.IsEmpty() ? TEXT("") : TEXT(": "), *FirstIn));
		// ---- the doors: a frame and a header over each door (the leaf in each bulkhead), and a sign in each room that gives on it
		int32 Doors = 0, Frameless = 0, Blasts = 0, NoLeaf = 0, SignsWanted = 0;
		for (const FBoardPortal& Po : M.GetPortals())
		{
			if (!Po.bDoor())
			{
				continue;
			}
			const bool bBlast = Po.Kind == FBoardPortal::EKind::Blast;
			++Doors;
			Blasts += bBlast ? 1 : 0;
			bool bFrame = false, bLeaf = false;
			for (const FPlacement& Pl : Built[Po.A].Pieces)
			{
				if ((Pl.Piece == (bBlast ? EPiece::BlastHeader : EPiece::DoorHeader)) && FVector2D::Distance(FVector2D(Pl.Pos.X, Pl.Pos.Y), FVector2D(Po.Pos.X, Po.Pos.Y)) < 160.0)
				{
					bFrame = true;
				}
				bLeaf |= Pl.Piece == EPiece::BlastLeaf && Pl.Door == Po.Door;
			}
			Frameless += bFrame ? 0 : 1;
			NoLeaf += (bBlast && !bLeaf) ? 1 : 0;
			SignsWanted += 2;
		}
		int32 Signs = 0;
		for (const FRoomDress& R : Built)
		{
			Signs += R.Signs.Num();
		}
		BCheck("dress: the doors", Frameless == 0 && NoLeaf == 0 && Signs >= SignsWanted * 9 / 10,
		       FString::Printf(TEXT("%s: %d doors (%d pressure bulkheads): %d without a frame, %d bulkheads without a leaf; %d signs for %d door faces"), *K.ToString(), Doors, Blasts, Frameless, NoLeaf, Signs, SignsWanted));
		// ---- the same room, the same dressing; every placement inside its room
		int32 Different = 0, Escaped = 0, Total = 0;
		for (int32 c = 0; c < N; ++c)
		{
			FRoomDress Again;
			DressRoom(Ctx, &Lay, c, Again);
			Different += BDressHash(Again) != BDressHash(Built[c]) ? 1 : 0;
			const FBox B = M.GetComps()[c].Box.ExpandBy(45.0);
			for (const FPlacement& Pl : Built[c].Pieces)
			{
				++Total;
				Escaped += (Pl.Pos.X < B.Min.X || Pl.Pos.Y < B.Min.Y || Pl.Pos.Z < B.Min.Z - 5.0 || Pl.Pos.X > B.Max.X || Pl.Pos.Y > B.Max.Y || Pl.Pos.Z > B.Max.Z + 5.0) ? 1 : 0;
			}
		}
		BCheck("dress: deterministic, and in its room", Different == 0 && Escaped == 0, FString::Printf(TEXT("%s: %d rooms dressed twice: %d differ; %d of %d pieces outside their room's box"), *K.ToString(), N, Different, Escaped, Total));
		// ---- the cost
		int32 PlainAll = 0, SlabAll = 0;
		for (int32 c = 0; c < N; ++c)
		{
			PlainAll += PlainRendered(c);
			SlabAll += SlabsDrawnAfter(c);
		}
		const int64 PlainTris = 12LL * PlainAll;
		FString Decks;
		for (const TPair<int32, FTally>& KV : ByDeck)
		{
			Decks += FString::Printf(TEXT("%sdeck %d %d+%d inst %.1fM tris (before %d inst %.2fM)"), Decks.IsEmpty() ? TEXT("") : TEXT("; "), KV.Key, KV.Value.TotalPieces(), SlabsByDeck.FindRef(KV.Key), (KV.Value.Tris + 12LL * SlabsByDeck.FindRef(KV.Key)) / 1.0e6,
			                          PlainByDeck.FindRef(KV.Key), 12.0 * PlainByDeck.FindRef(KV.Key) / 1.0e6);
		}
		BNote(FString::Printf(TEXT("%s (%s): %d rooms dressed in %.0f ms (%.2f ms a room); as built %d instances (%d walls and bays, %d ceiling, %d floor, %d opening, %d prop, %d fallen) + %d boxes drawn: %.2fM triangles; before: %d boxes, %.3fM"),
		                       *K.ToString(), Ctx.Side == AstraBoardDress::EDressSide::Mandate ? TEXT("Mandate") : (Ctx.Side == AstraBoardDress::EDressSide::Guild ? TEXT("Guild") : TEXT("Astra")), N, BuiltMs, BuiltMs / FMath::Max(1, N), All.TotalPieces(), All.Pieces[0], All.Pieces[1], All.Pieces[2], All.Pieces[3], All.Pieces[4], All.Pieces[5],
		                       SlabAll, (All.Tris + 12LL * SlabAll) / 1.0e6, PlainAll, PlainTris / 1.0e6));
		BNote(FString::Printf(TEXT("  hurt by the war: %d instances %.2fM tris (%d flames, smoke and sparks, %d lamps); a hulk: %d instances, %d lamps in the red; %d props (%d rooms with props), %d solid boxes, %d lamps, %d door signs"),
		                      AllWar.TotalPieces(), AllWar.Tris / 1.0e6, AllWar.Fx, AllWar.Lamps, AllCold.TotalPieces(), AllCold.Lamps, Props, Dressed, All.Blocks, All.Lamps, All.Signs));
		BNote(FString::Printf(TEXT("  in the ring round a Captain (the rooms within 48 m on his deck): %.0f instances and %.2fM triangles on average over %d places, the worst %d rooms %d instances %.2fM triangles (before: %.0f boxes, %.3fM); %d solid boxes at the worst"),
		                      (double)Sum.Instances / Samples, (double)Sum.Tris / Samples / 1.0e6, Samples, Worst.Rooms, Worst.Instances, Worst.Tris / 1.0e6, (double)Sum.Plain / Samples, 12.0 * Sum.Plain / Samples / 1.0e6, Worst.Boxes));
		BNote(FString::Printf(TEXT("  by deck: %s"), *Decks));
		// the budget a ring may cost on the target machine: the instances and triangles that a Nanite scene of small meshes takes without trouble
		BCheck("dress: the ring's budget", Worst.Instances <= 9000 && Worst.Tris <= 6000000,
		       FString::Printf(TEXT("%s: the worst place has %d rooms in its ring, %d instances (at most 9000) and %.2fM triangles (at most 6M)"), *K.ToString(), Worst.Rooms, Worst.Instances, Worst.Tris / 1.0e6));
		// ---- the dump for the offline view (art/blender/board_kit_view.py --dump): the dressing of the rooms round a place
		if (!DumpDir.IsEmpty())
		{
			FVector At = FVector::ZeroVector;
			TArray<FString> Xyz;
			if (Focus.ParseIntoArray(Xyz, TEXT(",")) == 3)
			{
				At = FVector(FCString::Atod(*Xyz[0]), FCString::Atod(*Xyz[1]), FCString::Atod(*Xyz[2]));
			}
			else if (P->Docks.Num() > 0)
			{
				At = M.CentreOf(P->Docks[0].Comp);
			}
			else
			{
				At = M.CentreOf(0);
			}
			TArray<TSharedPtr<FJsonValue>> RoomList, SlabList;
			for (int32 c = 0; c < N; ++c)
			{
				const FBox& B = M.GetComps()[c].Box;
				if (FMath::Abs(B.Min.Z - At.Z) > 250.0 || FMath::Sqrt(B.ComputeSquaredDistanceToPoint(FVector(At.X, At.Y, B.GetCenter().Z))) >= 2600.0)
				{
					continue;
				}
				const FRoomDress& R = bDumpHurt ? War[c] : Built[c];
				TSharedRef<FJsonObject> O = MakeShared<FJsonObject>();
				O->SetNumberField(TEXT("comp"), c);
				O->SetStringField(TEXT("name"), P->Dmg->Comps[c].Name);
				O->SetStringField(TEXT("kind"), M.GetComps()[c].Kind.ToString());
				TArray<TSharedPtr<FJsonValue>> Box, Pieces, Lamps;
				for (const double V : {B.Min.X, B.Min.Y, B.Min.Z, B.Max.X, B.Max.Y, B.Max.Z})
				{
					Box.Add(MakeShared<FJsonValueNumber>(FMath::RoundToInt(V * 10.0) / 10.0));
				}
				O->SetArrayField(TEXT("box"), Box);
				for (const FPlacement& Pl : R.Pieces)
				{
					TArray<TSharedPtr<FJsonValue>> Row;
					Row.Add(MakeShared<FJsonValueString>(AstraBoardDress::Def(Pl.Piece).Key));
					for (const double V : {Pl.Pos.X, Pl.Pos.Y, Pl.Pos.Z, (double)Pl.Rot.Pitch, (double)Pl.Rot.Yaw, (double)Pl.Rot.Roll, Pl.Scale.X, Pl.Scale.Y, Pl.Scale.Z})
					{
						Row.Add(MakeShared<FJsonValueNumber>(FMath::RoundToInt(V * 100.0) / 100.0));
					}
					Pieces.Add(MakeShared<FJsonValueArray>(Row));
				}
				O->SetArrayField(TEXT("pieces"), Pieces);
				for (const FLamp& L : R.Lamps)
				{
					TArray<TSharedPtr<FJsonValue>> Row;
					for (const double V : {L.Pos.X, L.Pos.Y, L.Pos.Z, (double)(int32)L.State})
					{
						Row.Add(MakeShared<FJsonValueNumber>(FMath::RoundToInt(V * 10.0) / 10.0));
					}
					Lamps.Add(MakeShared<FJsonValueArray>(Row));
				}
				O->SetArrayField(TEXT("lamps"), Lamps);
				RoomList.Add(MakeShared<FJsonValueObject>(O));
				for (int32 i = SlabFirst[c]; i < SlabFirst[c + 1]; ++i)
				{
					const AstraBoardInterior::FSlab& S = Slabs[i];
					TArray<TSharedPtr<FJsonValue>> Row;
					Row.Add(MakeShared<FJsonValueNumber>((int32)S.Kind));
					for (const double V : {S.Centre.X, S.Centre.Y, S.Centre.Z, S.Half.X, S.Half.Y, S.Half.Z})
					{
						Row.Add(MakeShared<FJsonValueNumber>(FMath::RoundToInt(V * 10.0) / 10.0));
					}
					SlabList.Add(MakeShared<FJsonValueArray>(Row));
				}
			}
			TSharedRef<FJsonObject> Root = MakeShared<FJsonObject>();
			Root->SetStringField(TEXT("class"), K.ToString());
			Root->SetStringField(TEXT("side"), Ctx.Side == AstraBoardDress::EDressSide::Mandate ? TEXT("mandate") : (Ctx.Side == AstraBoardDress::EDressSide::Guild ? TEXT("guild") : TEXT("astra")));
			Root->SetArrayField(TEXT("rooms"), RoomList);
			Root->SetArrayField(TEXT("slabs"), SlabList);
			TArray<TSharedPtr<FJsonValue>> Foc;
			for (const double V : {At.X, At.Y, At.Z})
			{
				Foc.Add(MakeShared<FJsonValueNumber>(V));
			}
			Root->SetArrayField(TEXT("focus"), Foc);
			const FString Path = FPaths::IsRelative(DumpDir) ? FPaths::Combine(FPaths::ProjectDir(), DumpDir) : DumpDir;
			IFileManager::Get().MakeDirectory(*Path, true);
			FFileHelper::SaveStringToFile(Json(Root), *FPaths::Combine(Path, FString::Printf(TEXT("dress_%s.json"), *K.ToString())));
		}
	}
}

/** One fight on a plan, from a scene's spec: the people placed, the fight run to its end. */
static FRunResult RunScene(const FBoardShipPlan& Plan, const FTuning& Tuning, const AstraBoardScene::FSpec& Spec, int32 Seed, AstraBoardScene::FResult* OutScene = nullptr)
{
	FAstraBoardSim Sim;
	Sim.Init(Plan.Map.ToSharedRef(), Seed);
	Sim.Tuning = Tuning;
	AstraBoardScene::FSpec S = Spec;
	S.Seed = Seed;
	const AstraBoardScene::FResult R = AstraBoardScene::Build(Sim, Plan, S);
	if (OutScene)
	{
		*OutScene = R;
	}
	FRunResult Out;
	if (!R.bOk)
	{
		return Out;
	}
	Out = RunSim(Sim, 900.0);
	AstraBoardScene::CasualtiesOf(Sim, Sim.Defender(), Out.DefCas);
	return Out;
}

static void BoardScenarioAttack(const FString& Class, int32 Seed, int32 Seeds, const FTuning& Tuning)
{
	FString Why;
	const TSharedPtr<FBoardShipPlan> P = AstraBoardPlans::Load(FName(*Class), Why);
	if (!P.IsValid())
	{
		BCheck("attack", false, FString::Printf(TEXT("%s: %s"), *Class, *Why));
		return;
	}
	struct FSetup { const TCHAR* Name; ESide Attacker; int32 Men; const TCHAR* Objective; float PostShare; int32 Roaming; bool bSweep; };
	const FSetup Setups[] = {
		{TEXT("two Kestrels (24 marines) for the commander's suite, the crew a hulk's"), ESide::Aquila, 24, TEXT("captain"), 0.6f, 6, true},
		{TEXT("two Kestrels for the bridge"), ESide::Aquila, 24, TEXT("bridge"), 0.6f, 6, true},
		{TEXT("two Kestrels for engineering"), ESide::Aquila, 24, TEXT("engineering"), 0.6f, 6, true},
		{TEXT("one Kestrel (12) for the commander's suite"), ESide::Aquila, 12, TEXT("captain"), 0.6f, 6, true},
		{TEXT("two Kestrels, the ship manned (every post, 16 roaming)"), ESide::Aquila, 24, TEXT("captain"), 1.f, 16, true},
		{TEXT("the same plan, the roles turned: 24 of the Mandate come aboard, the marines are the guard"), ESide::Mandate, 24, TEXT("captain"), 0.6f, 6, true},
	};
	TSharedRef<FJsonObject> Rec = MakeShared<FJsonObject>();
	for (int32 si = 0; si < UE_ARRAY_COUNT(Setups); ++si)
	{
		if (GSetup >= 0 && si != GSetup)
		{
			continue;
		}
		const FSetup& S = Setups[si];
		AstraBoardScene::FSpec Spec;
		Spec.Attacker = S.Attacker;
		Spec.Attackers = S.Men;
		Spec.Objective = S.Objective;
		Spec.PostShare = S.PostShare;
		Spec.Roaming = S.Roaming;
		Spec.bSweep = S.bSweep;
		int32 Wins[4] = {0, 0, 0, 0};             // the holders hold, the attackers repelled, take, timed out
		double T = 0.0, LossAtt = 0.0, LossDef = 0.0, DeadAtt = 0.0, Contact = 0.0, Flanks = 0.0, Ms = 0.0, MsMax = 0.0, Defenders = 0.0;
		int32 Ran = 0, Bad = 0;
		FString Failed, NoEnd;
		for (int32 s = 0; s < Seeds; ++s)
		{
			AstraBoardScene::FResult Scene;
			const FRunResult R = RunScene(*P, Tuning, Spec, Seed + s, &Scene);
			if (!Scene.bOk)
			{
				Failed = Scene.Why;
				break;
			}
			++Ran;
			const int32 A = (int32)S.Attacker, D = 1 - A;
			Wins[R.Outcome == EOutcome::DefenderHolds ? 0 : R.Outcome == EOutcome::AttackerRepelled ? 1 : R.Outcome == EOutcome::AttackerTakes ? 2 : 3]++;
			if (R.Outcome != EOutcome::DefenderHolds && R.Outcome != EOutcome::AttackerRepelled && R.Outcome != EOutcome::AttackerTakes)
			{
				NoEnd += FString::Printf(TEXT("%s%d"), NoEnd.IsEmpty() ? TEXT("") : TEXT(","), Seed + s);
			}
			T += R.T;
			LossAtt += R.Book.Killed[A] + R.Book.Down[A] + R.Book.Carried[A];
			DeadAtt += R.Book.Killed[A];
			LossDef += R.Book.Killed[D] + R.Book.Down[D] + R.Book.Carried[D];
			Contact += R.Book.FirstContactT;
			Flanks += R.Book.Flanks;
			Bad += R.BadPos;
			Ms += R.Ms / FMath::Max(1, R.Steps);
			MsMax = FMath::Max(MsMax, R.MsMax);
			Defenders += Scene.Defenders;
		}
		if (!Ran)
		{
			BCheck("attack", false, FString::Printf(TEXT("%s: %s"), *Class, *Failed));
			return;
		}
		const double N = Ran;
		BNote(FString::Printf(TEXT("%s: %d fights on the %s against %.0f defenders — attackers take it %d, defenders hold %d, attackers repelled %d, no end %d; ends at %.0f s, first contact %.0f s; attackers lost %.1f of %d (%.1f dead, %.1f wounded), defenders lost %.1f; flanks %.1f; %.3f ms a step (worst %.1f)%s%s"),
		                      S.Name, Ran, *Class, Defenders / N, Wins[2], Wins[0], Wins[1], Wins[3], T / N, Contact / N, LossAtt / N, S.Men, DeadAtt / N, (LossAtt - DeadAtt) / N, LossDef / N, Flanks / N, Ms / N, MsMax,
		                      NoEnd.IsEmpty() ? TEXT("") : TEXT("; no end at seeds "), *NoEnd));
		TSharedRef<FJsonObject> O = MakeShared<FJsonObject>();
		O->SetStringField(TEXT("setup"), S.Name);
		O->SetNumberField(TEXT("fights"), Ran);
		O->SetNumberField(TEXT("attackers_take"), Wins[2]);
		O->SetNumberField(TEXT("defenders_hold"), Wins[0]);
		O->SetNumberField(TEXT("repelled"), Wins[1]);
		O->SetNumberField(TEXT("timed_out"), Wins[3]);
		O->SetNumberField(TEXT("end_s"), T / N);
		O->SetNumberField(TEXT("loss_attackers"), LossAtt / N);
		O->SetNumberField(TEXT("dead_attackers"), DeadAtt / N);
		O->SetNumberField(TEXT("loss_defenders"), LossDef / N);
		Rec->SetObjectField(FString::Printf(TEXT("setup%d"), si), O);
		if (si == 0)
		{
			BCheck("attack: marines on a Mandate ship", Bad == 0 && Wins[3] == 0 && Wins[2] >= Ran / 2 && LossAtt / N < 12.0, FString::Printf(TEXT("%d fights: the marines take the suite in %d, are held in %d, break off in %d; %.1f lost of 24; %d men off the plan; %.3f ms a step"),
				Ran, Wins[2], Wins[0], Wins[1], LossAtt / N, Bad, Ms / N));
		}
	}
	BRecord->SetObjectField(TEXT("attack"), Rec);
}
// ================================================================================================================== orders given at random, on every class's plan (ABBORDAGGI-4: do the infantry orders hold on rooms they were not tuned on?)

/** The marines go aboard a class's ship (24 of them, two Kestrels' worth) and, every fifteen seconds, a squad of theirs is given an order at random: a task, a room or a section of the plan, and the things that go with it (fire held, doors
 *  shut behind, a place to cover, a sync number). What is checked is what must hold whatever is ordered: nobody off the plan, no number gone bad, the step as cheap as before, the same fight from the same seed. The numbers of the fights
 *  mean nothing (orders at random are bad orders): this is the robustness of the drills on the plans of all the classes, not their worth. */
static void BoardScenarioFuzz(const FString& Only, int32 Seed, int32 Seeds, const FTuning& Tuning)
{
	TArray<FName> Classes;
	AstraBoardPlans::ClassesWithPlans(Classes);
	if (!Only.IsEmpty())
	{
		Classes = {FName(*Only)};
	}
	if (Classes.IsEmpty())
	{
		BCheck("fuzz", false, TEXT("no plans in data/ship/plans"));
		return;
	}
	for (const FName& K : Classes)
	{
		FString Why;
		const TSharedPtr<FBoardShipPlan> P = AstraBoardPlans::Load(K, Why);
		if (!P.IsValid())
		{
			BCheck("fuzz", false, FString::Printf(TEXT("%s: %s"), *K.ToString(), *Why));
			continue;
		}
		const FAstraBoardMap& M = *P->Map;
		TArray<int32> Rooms;                                         // the rooms with a floor to stand on (the plan's planned-only ones have no box)
		for (int32 c = 0; c < M.GetComps().Num(); ++c)
		{
			const FBoardComp& C = M.GetComps()[c];
			if (C.Box.IsValid && C.Box.GetSize().X > 150.0 && C.Box.GetSize().Y > 150.0)
			{
				Rooms.Add(c);
			}
		}
		TArray<int32> Doors;                                         // the damage map's doors that join two rooms
		for (const FBoardPortal& Po : M.GetPortals())
		{
			if (Po.bDoor() && Po.Door != INDEX_NONE)
			{
				Doors.Add(Po.Door);
			}
		}
		struct FOne { uint32 Hash = 0; int32 Bad = 0, Nan = 0, Orders = 0, Steps = 0; double Ms = 0.0, MsMax = 0.0; bool bScene = false; double EndS = 0.0; };
		const auto RunOne = [&](int32 SeedOne) -> FOne
		{
			FOne Out;
			FAstraBoardSim Sim;
			Sim.Init(P->Map.ToSharedRef(), SeedOne);
			Sim.Tuning = Tuning;
			Sim.Tuning.bEvacuate = true;
			AstraBoardScene::FSpec Spec;
			Spec.Attacker = ESide::Aquila;
			Spec.Attackers = 24;
			Spec.Objective = (SeedOne % 3 == 0) ? TEXT("bridge") : ((SeedOne % 3 == 1) ? TEXT("engineering") : TEXT("captain"));
			Spec.PostShare = 0.6f;
			Spec.Roaming = 6;
			Spec.bSweep = true;
			Spec.Seed = SeedOne;
			const AstraBoardScene::FResult Sc = AstraBoardScene::Build(Sim, *P, Spec);
			if (!Sc.bOk || Sc.AttackSquads.IsEmpty() || Rooms.IsEmpty())
			{
				return Out;
			}
			Out.bScene = true;
			FRandomStream Rnd(SeedOne * 7919 + 17);
			double NextAt = 10.0;
			const auto Give = [&](FAstraBoardSim& S)
			{
				if (S.Time() < NextAt)
				{
					return;
				}
				NextAt = S.Time() + 15.0;
				const int32 Sq = Sc.AttackSquads[Rnd.RandRange(0, Sc.AttackSquads.Num() - 1)];
				const int32 Room = Rooms[Rnd.RandRange(0, Rooms.Num() - 1)];
				FOrder O;
				static const ETask Tasks[] = {ETask::Hold, ETask::Advance, ETask::Assault, ETask::FallBack, ETask::Withdraw, ETask::Sweep, ETask::Breach, ETask::Take, ETask::Ambush};
				O.Task = Tasks[Rnd.RandRange(0, UE_ARRAY_COUNT(Tasks) - 1)];
				O.Comp = Room;
				O.Pos = M.CentreOf(Room);
				O.Radius = Rnd.FRand() < 0.4f ? 0.f : (float)Rnd.RandRange(400, 2500);
				O.bFireHeld = Rnd.FRand() < 0.3f;
				O.bInside = Rnd.FRand() < 0.2f;
				O.bSealBehind = Rnd.FRand() < 0.3f;
				O.Sync = Rnd.FRand() < 0.4f ? Rnd.RandRange(1, 2) : 0;
				O.CoverComp = Rnd.FRand() < 0.3f ? Rooms[Rnd.RandRange(0, Rooms.Num() - 1)] : INDEX_NONE;
				if (O.Task == ETask::Breach && !Doors.IsEmpty())
				{
					O.Door = Doors[Rnd.RandRange(0, Doors.Num() - 1)];
				}
				if (O.Task == ETask::Sweep)
				{
					const FBoardComp& R0 = M.GetComps()[Room];
					for (int32 c : Rooms)
					{
						const FBoardComp& C = M.GetComps()[c];
						if (C.Deck == R0.Deck && C.Section == R0.Section)
						{
							O.Sector.Add(c);
						}
					}
				}
				O.Where = M.Describe(Room);
				S.OrderEx(Sq, O);
				++Out.Orders;
			};
			const FRunResult R = RunSim(Sim, 600.0, Give);
			Out.Hash = R.Hash;
			Out.Bad = R.BadPos;
			Out.Steps = R.Steps;
			Out.Ms = R.Ms;
			Out.MsMax = R.MsMax;
			Out.EndS = R.T;
			for (const FUnit& U : Sim.Units())
			{
				Out.Nan += (U.Pos.ContainsNaN() || !FMath::IsFinite(U.Hp) || !FMath::IsFinite(U.Yaw)) ? 1 : 0;
			}
			return Out;
		};
		int32 Ran = 0, Bad = 0, Nan = 0, Orders = 0, Differ = 0, Steps = 0;
		double Ms = 0.0, MsMax = 0.0, EndS = 0.0;
		for (int32 s = 0; s < Seeds; ++s)
		{
			const FOne A = RunOne(Seed + s);
			if (!A.bScene)
			{
				continue;
			}
			const FOne B = RunOne(Seed + s);                         // (the same seed, the same orders, the same fight)
			++Ran;
			Bad += A.Bad;
			Nan += A.Nan;
			Orders += A.Orders;
			Differ += A.Hash != B.Hash ? 1 : 0;
			Steps += A.Steps;
			Ms += A.Ms;
			MsMax = FMath::Max(MsMax, A.MsMax);
			EndS += A.EndS;
		}
		const double PerStep = Steps ? Ms / Steps : 0.0;
		BNote(FString::Printf(TEXT("  %-10s %d fights with %d orders at random (%.1f a fight), %.0f s on average: %d men off the plan, %d numbers gone bad, %d fights that differ from their twin; %.3f ms a step (worst %.1f)"), *K.ToString(), Ran, Orders,
		                      Ran ? (double)Orders / Ran : 0.0, Ran ? EndS / Ran : 0.0, Bad, Nan, Differ, PerStep, MsMax));
		BCheck(TCHAR_TO_ANSI(*FString::Printf(TEXT("fuzz: %s"), *K.ToString())), Ran > 0 && Bad == 0 && Nan == 0 && Differ == 0 && PerStep < 3.0 && MsMax < 80.0,
		       FString::Printf(TEXT("%d fights, %d orders at random: %d men off the plan, %d bad numbers, %d not repeatable; %.3f ms a step, worst %.1f"), Ran, Orders, Bad, Nan, Differ, PerStep, MsMax));
	}
}

// ================================================================================================================== a ship the war has shot at (FLOTTA-VIVA's inside, then the marines)

/** FLOTTA-VIVA's inside of a class's ship is shot at (so many blows, then a minute), its snapshot is taken as the host takes it, and the marines go aboard that ship: with the people the war left, where it
 *  left them. The more she has been hit, the fewer hold her and the cheaper she is; a ship that is shot to pieces has a handful of wounded. Also: the war's rooms are the plan's rooms. */
static void BoardScenarioWar(const FString& Class, int32 Seed, int32 Seeds, const FTuning& Tuning)
{
	FString Why;
	const TSharedPtr<FBoardShipPlan> P = AstraBoardPlans::Load(FName(*Class), Why);
	const TSharedPtr<const FFleetClassPlan> FP = FAstraFleetPlans::Find(FName(*Class), true);
	if (!P.IsValid() || !FP.IsValid())
	{
		BCheck("war: the ship", false, FString::Printf(TEXT("%s: %s"), *Class, P.IsValid() ? TEXT("FLOTTA-VIVA has no plan of it") : *Why));
		return;
	}
	bool bSame = FP->Map->Comps.Num() == P->Dmg->Comps.Num();
	for (int32 i = 0; bSame && i < FP->Map->Comps.Num(); ++i)
	{
		bSame = FP->Map->Comps[i].Id == P->Dmg->Comps[i].Id;
	}
	BCheck("war: the plans agree", bSame, FString::Printf(TEXT("%s: the war's rooms and the boarding's are the same %d rooms in the same order"), *Class, FP->Map->Comps.Num()));
	struct FState { const TCHAR* Name; int32 Blows; bool bDisabled; };
	const FState States[] = {{TEXT("not hit (a full crew at her stations)"), 0, false}, {TEXT("hit a few times"), 14, false}, {TEXT("battered"), 60, false}, {TEXT("shot to pieces"), 220, false},
	                         {TEXT("shot to pieces and disabled (no fight left in her)"), 220, true}};
	int32 PrevDefenders = 1 << 30;
	bool bFewer = true, bFits = true, bBooksOk = true;
	TSharedRef<FJsonObject> Rec = MakeShared<FJsonObject>();
	for (int32 si = 0; si < UE_ARRAY_COUNT(States); ++si)
	{
		if (GSetup >= 0 && si != GSetup)
		{
			continue;
		}
		const auto MakeInside = [&](int32 State) -> TSharedRef<FAstraShipInterior>
		{
			TSharedRef<FAstraShipInterior> In = MakeShared<FAstraShipInterior>(FP.ToSharedRef(), 7, TEXT("Test"), 4242);
			FRandomStream Shots(11);
			const int32 NC = FP->Map->Comps.Num();
			for (int32 b = 0; b < States[State].Blows; ++b)
			{
				In->Strike(Shots.RandRange(0, NC - 1), 60.f + 80.f * Shots.FRand(), (uint8)Shots.RandRange(0, 2), b % 4 == 0);
			}
			for (int32 k = 0; k < 600; ++k)
			{
				In->Tick(0.1f);
			}
			return In;
		};
		const TSharedRef<FAstraShipInterior> InsideRef = MakeInside(si);
		FAstraShipInterior& I = *InsideRef;
		FFleetSnapshot Snap;
		I.Snapshot(Snap);
		for (const FFleetSnapshot::FHand& H : Snap.Hands)
		{
			bFits &= H.Comp >= 0 && H.Comp < P->Dmg->Comps.Num();
		}
		AstraBoardScene::FSpec Spec;
		Spec.Attacker = ESide::Aquila;
		Spec.Attackers = 24;
		Spec.Objective = TEXT("captain");
		Spec.Inside = &Snap;
		Spec.bSweep = States[si].bDisabled;
		if (States[si].bDisabled)
		{
			AstraBoardScene::ForDisabledShip(Spec, true);        // (what the host does with a ship that has lost her power: UAstraBoardSubsystem::BeginRemoteScene)
		}
		int32 Wins[4] = {0, 0, 0, 0};
		double Def = 0.0, Wounded = 0.0, Unarmed = 0.0, Shut = 0.0, T = 0.0, LossAtt = 0.0, DeadAtt = 0.0, LossDef = 0.0;
		int32 Ran = 0;
		FString NoEnd;
		for (int32 s = 0; s < Seeds; ++s)
		{
			AstraBoardScene::FResult Scene;
			const FRunResult R = RunScene(*P, Tuning, Spec, Seed + s, &Scene);
			if (!Scene.bOk)
			{
				break;
			}
			++Ran;
			Wins[R.Outcome == EOutcome::DefenderHolds ? 0 : R.Outcome == EOutcome::AttackerRepelled ? 1 : R.Outcome == EOutcome::AttackerTakes ? 2 : 3]++;
			Def += Scene.Defenders;
			Wounded += Scene.Wounded;
			Unarmed += Scene.Unarmed;
			Shut += Scene.ShutBulkheads;
			T += R.T;
			LossAtt += R.Book.Killed[0] + R.Book.Down[0] + R.Book.Carried[0];
			DeadAtt += R.Book.Killed[0];
			LossDef += R.Book.Killed[1] + R.Book.Down[1] + R.Book.Carried[1];
			if (R.Outcome == EOutcome::TimedOut)
			{
				NoEnd += FString::Printf(TEXT("%s%d"), NoEnd.IsEmpty() ? TEXT("") : TEXT(","), Seed + s);
			}
		}
		if (!Ran)
		{
			BCheck("war: the scene", false, FString::Printf(TEXT("%s: the scene could not be made"), *Class));
			return;
		}
		const double N = Ran;
		BNote(FString::Printf(TEXT("%s, %s: the war left %d fit and %d wounded of %d (%d killed, %d fires, %d breaches, %d dark rooms, %d bulkheads shut); %d fights: %.0f under arms, %.0f at their stations, %.0f wounded lying; the marines take it %d, are held %d, no end %d; ends at %.0f s; marines lost %.1f of 24 (%.1f dead), her people lost %.1f%s%s"),
		                      *Class, States[si].Name, I.CrewFit(), I.CrewWounded(), I.CrewTotal(), I.CrewDead(), I.Fires(), I.Breaches(), I.DarkRooms(), Snap.SealedDoors.Num(), Ran, Def / N, Unarmed / N, Wounded / N, Wins[2], Wins[0], Wins[3], T / N,
		                      LossAtt / N, DeadAtt / N, LossDef / N, NoEnd.IsEmpty() ? TEXT("") : TEXT("; no end at seeds "), *NoEnd));
		if (!States[si].bDisabled)
		{
			bFewer &= Def / N <= PrevDefenders + 1.0;
			PrevDefenders = FMath::RoundToInt(Def / N);
		}
		// the landing's books: the dead and the hurt of one fight (the first seed's) written into a fresh copy of her inside (the same ship, the same blows)
		{
			AstraBoardScene::FResult Scene;
			const FRunResult R = RunScene(*P, Tuning, Spec, Seed, &Scene);
			const TSharedRef<FAstraShipInterior> Copy = MakeInside(si);
			FFleetSnapshot Before;
			Copy->Snapshot(Before);
			const int32 Total = Copy->CrewTotal(), Fit0 = Copy->CrewFit(), Hurt0 = Copy->CrewWounded(), Dead0 = Copy->CrewDead();
			int32 Killed = 0, Hurt = 0;
			for (const FFleetCasualty& C : R.DefCas)
			{
				++(C.bKilled ? Killed : Hurt);
			}
			const FFleetBoardingTally Tally = Copy->ApplyBoarding(R.DefCas);
			FFleetSnapshot After;
			Copy->Snapshot(After);
			bool bOk = Copy->CrewFit() + Copy->CrewWounded() + Copy->CrewDead() == Total;                        // nobody is lost or made up
			bOk &= Copy->CrewDead() == Dead0 + Tally.Killed && Copy->CrewWounded() == Hurt0 + Tally.Wounded;     // the counts are what the landing did
			bOk &= Copy->CrewFit() == Fit0 - Tally.Killed - Tally.Wounded;
			bOk &= Tally.Killed <= Killed && Tally.Killed + Tally.Wounded <= Killed + Hurt && Tally.Unmatched == 0;
			bOk &= After.Fallen.Num() == Copy->CrewDead();                                                       // every dead man lies somewhere on her decks
			// a man killed by the landing lies where he fell (and a man of the war's picture is the same person in the books)
			int32 Lie = 0, Placed = 0;
			for (const FFleetCasualty& C : R.DefCas)
			{
				if (!C.bKilled || !Copy->GetPeople().IsValidIndex(C.Person) || Copy->GetPeople()[C.Person].State != 2)
				{
					continue;
				}
				++Placed;
				Lie += Copy->GetPeople()[C.Person].Comp == C.Comp ? 1 : 0;
			}
			bOk &= Lie == Placed;
			const FFleetBoardingTally Again = Copy->ApplyBoarding(R.DefCas);                                   // a book is written once: the same men are not taken twice
			bOk &= Again.Killed == 0 && Again.Wounded == 0;
			if (Tally.bCaptainFell)
			{
				bOk &= Copy->CaptainState() != 0;
			}
			BNote(FString::Printf(TEXT("%s, %s: the landing's books: %d dead and %d hurt of her crew (%d fit, %d hurt, %d dead of %d before; %d fit, %d hurt, %d dead after); %d lie where they fell%s"), *Class, States[si].Name, Tally.Killed,
			                      Tally.Wounded, Fit0, Hurt0, Dead0, Total, Copy->CrewFit(), Copy->CrewWounded(), Copy->CrewDead(), Lie, Tally.bCaptainFell ? TEXT("; her captain fell") : TEXT("")));
			bBooksOk &= bOk;
		}
		TSharedRef<FJsonObject> O = MakeShared<FJsonObject>();
		O->SetStringField(TEXT("state"), States[si].Name);
		O->SetNumberField(TEXT("fit"), I.CrewFit());
		O->SetNumberField(TEXT("wounded"), I.CrewWounded());
		O->SetNumberField(TEXT("defenders"), Def / N);
		O->SetNumberField(TEXT("takes"), Wins[2]);
		O->SetNumberField(TEXT("loss_attackers"), LossAtt / N);
		Rec->SetObjectField(FString::Printf(TEXT("state%d"), si), O);
	}
	BCheck("war: the landing's books", bBooksOk, FString::Printf(TEXT("%s: the dead and the hurt of a landing go back into her crew's books: the counts add up, nobody is taken twice, the dead lie where they fell"), *Class));
	BCheck("war: the people are the war's", bFits && bFewer, FString::Printf(TEXT("%s: every person the war has is in a room of the plan; the more she has been hit, the fewer fight"), *Class));
	BRecord->SetObjectField(TEXT("war"), Rec);
}

int32 UAstraBoardSimCommandlet::Main(const FString& Params)
{
	FString Scenario = TEXT("all"), OutPath = TEXT("Saved/Boarding/run.json"), Set;
	int32 Seed = 1, Seeds = 20, Boarders = 0;
	FParse::Value(*Params, TEXT("-scenario="), Scenario);
	FParse::Value(*Params, TEXT("-seed="), Seed);
	FParse::Value(*Params, TEXT("-seeds="), Seeds);
	FParse::Value(*Params, TEXT("-boarders="), Boarders);
	GBoarders = Boarders;
	FParse::Value(*Params, TEXT("-out="), OutPath);
	FParse::Value(*Params, TEXT("-set="), Set, false);
	GTrace = FParse::Param(*Params, TEXT("trace"));
	FParse::Value(*Params, TEXT("-setup="), GSetup);
	Scenario = Scenario.ToLower();
	FRig Rig;
	if (Scenario == TEXT("plans") || Scenario == TEXT("attack") || Scenario == TEXT("interior") || Scenario == TEXT("war") || Scenario == TEXT("dress") || Scenario == TEXT("escort") || Scenario == TEXT("fuzz"))      // (on request only: other ships' plans, the marines going aboard one, the plans made solid and dressed; no plan of the Aquila needed)
	{
		FString Class;
		FParse::Value(*Params, TEXT("-class="), Class);
		FTuning T;
		T.bEvacuate = true;                                    // (a boarding by boats: the wounded are carried out to them, as the game does it)
		ApplyTuning(T, Set);
		if (Scenario == TEXT("plans"))
		{
			BoardScenarioPlans(Class);
		}
		else if (Scenario == TEXT("interior"))
		{
			FString Dump;
			FParse::Value(*Params, TEXT("-dump="), Dump);
			BoardScenarioInterior(Class, Dump, Seed);
		}
		else if (Scenario == TEXT("dress"))
		{
			FString Dump, Focus;
			FParse::Value(*Params, TEXT("-dump="), Dump);
			FParse::Value(*Params, TEXT("-focus="), Focus);
			BoardScenarioDress(Class, Dump, Focus, FParse::Param(*Params, TEXT("hurt")), Seed);
		}
		else if (Scenario == TEXT("war"))
		{
			BoardScenarioWar(Class.IsEmpty() ? FString(TEXT("acheron")) : Class, Seed, Seeds, T);
		}
		else if (Scenario == TEXT("escort"))
		{
			BoardScenarioEscort(Class.IsEmpty() ? FString(TEXT("acheron")) : Class, Seed, Seeds, T);
		}
		else if (Scenario == TEXT("fuzz"))
		{
			BoardScenarioFuzz(Class, Seed, Seeds, T);
		}
		else
		{
			BoardScenarioAttack(Class.IsEmpty() ? FString(TEXT("acheron")) : Class, Seed, Seeds, T);
		}
		int32 OtherFailed = 0;
		for (const FBCheck& C : BChecks)
		{
			OtherFailed += C.bPass ? 0 : 1;
		}
		UE_LOG(LogASTRA, Display, TEXT("[Board] VERDICT: %s (%d checks, %d failed)"), OtherFailed ? TEXT("FAIL") : TEXT("PASS"), BChecks.Num(), OtherFailed);
		return OtherFailed ? 1 : 0;
	}
	if (Scenario == TEXT("fps"))                       // (on request only: the Captain's arms against the mannequin's animations, no plan needed)
	{
		FString PosesPath, FpsSet;
		FParse::Value(*Params, TEXT("-fpsposes="), PosesPath);
		FParse::Value(*Params, TEXT("-fpsset="), FpsSet, false);
		BoardScenarioFps(PosesPath, FpsSet);
		int32 FpsFailed = 0;
		for (const FBCheck& C : BChecks)
		{
			FpsFailed += C.bPass ? 0 : 1;
		}
		UE_LOG(LogASTRA, Display, TEXT("[Board] VERDICT: %s (%d checks, %d failed)"), FpsFailed ? TEXT("FAIL") : TEXT("PASS"), BChecks.Num(), FpsFailed);
		return FpsFailed ? 1 : 0;
	}
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
	if (Scenario == TEXT("orders"))                    // (on request only: a fight for each plan and seed)
	{
		BoardScenarioOrders(Rig, Seed, Seeds);
	}
	if (Scenario == TEXT("lean"))                      // (on request only: the Captain's body in the fight: leaning out of cover, lying, a head over a wall)
	{
		BoardScenarioLean(Rig, Seed, Seeds);
	}
	if (Scenario == TEXT("take") || Scenario == TEXT("drills"))                    // (on request only: the infantry orders, each with and without, on the same rooms and seeds)
	{
		BoardScenarioTake(Rig, Seed, Seeds);
	}
	if (Scenario == TEXT("breach") || Scenario == TEXT("drills"))
	{
		BoardScenarioBreach(Rig, Seed, Seeds);
	}
	if (Scenario == TEXT("sweep") || Scenario == TEXT("drills"))
	{
		BoardScenarioSweep(Rig, Seed, Seeds);
	}
	if (Scenario == TEXT("ambush") || Scenario == TEXT("drills"))
	{
		BoardScenarioAmbush(Rig, Seed, Seeds);
	}
	if (Scenario == TEXT("hold") || Scenario == TEXT("drills"))
	{
		BoardScenarioHold(Rig, Seed, Seeds);
	}
	if (Scenario == TEXT("seal") || Scenario == TEXT("drills"))
	{
		BoardScenarioSeal(Rig, Seed, Seeds);
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
