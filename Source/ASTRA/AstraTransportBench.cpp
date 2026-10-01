// TELETRASPORTO's bench, the whole subsystem in a headless world (AstraTransportCommandlet, scenario `world`): the real plan, VITA's 560 people, the damage model, the battle with an
// allied and a Mandate squadron on the plot. The orders are the minds' own (the `transport` commands), the ship ticks as in the game, and each check reads what the world did.
// The rules' scripted cases are in AstraTransportCommandlet.cpp; this is what they do when they meet the ship.

#include "AstraTransportBench.h"

#include "ASTRA.h"
#include "AstraBattleSubsystem.h"
#include "AstraDamageModel.h"
#include "AstraLifeSubsystem.h"
#include "AstraShipPlan.h"
#include "AstraShipSubsystem.h"
#include "AstraStations.h"
#include "AstraTransporterSubsystem.h"
#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "HAL/PlatformProcess.h"
#include "HAL/PlatformTime.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"

using namespace AstraXport;

namespace
{
	/** The whole ship in a headless world. */
	struct FXWorld
	{
		UWorld* World = nullptr;
		UAstraShipSubsystem* Ship = nullptr;
		UAstraLifeSubsystem* Life = nullptr;
		UAstraShipPlan* Plan = nullptr;
		UAstraBattleSubsystem* Battle = nullptr;
		UAstraTransporterSubsystem* Xp = nullptr;
		double T = 0.0;
		TArray<FString> Events;

		bool Make()
		{
			World = UWorld::CreateWorld(EWorldType::Game, false, TEXT("AstraTransportBench"));
			FWorldContext& Ctx = GEngine->CreateNewWorldContext(EWorldType::Game);
			Ctx.SetCurrentWorld(World);
			World->InitializeActorsForPlay(FURL());
			World->BeginPlay();
			Ship = World->GetSubsystem<UAstraShipSubsystem>();
			Life = World->GetSubsystem<UAstraLifeSubsystem>();
			Plan = World->GetSubsystem<UAstraShipPlan>();
			Battle = World->GetSubsystem<UAstraBattleSubsystem>();
			Xp = World->GetSubsystem<UAstraTransporterSubsystem>();
			if (!Ship || !Life || !Plan || !Battle || !Xp)
			{
				UE_LOG(LogASTRA, Error, TEXT("[Transport] the ship, her plan, the life, the battle or the transporter are not in the world"));
				return false;
			}
			Ship->OnShipEvent.AddLambda([this](const FString& Text, bool bReport)
			{
				if (Events.Num() < 2000)
				{
					Events.Add(FString::Printf(TEXT("%.1f%s %s"), T, bReport ? TEXT(" R") : TEXT(""), *Text));
				}
			});
			const double Wall0 = FPlatformTime::Seconds();
			for (int32 i = 0; i < 4000 && !(Life->IsRunning() && Ship->GetInterior().IsReady() && Xp->IsReady()) && FPlatformTime::Seconds() - Wall0 < 90.0; ++i)
			{
				Tick(0.05f);
				FPlatformProcess::Sleep(0.005f);
			}
			T = 0.0;
			return Life->IsRunning() && Ship->GetInterior().IsReady() && Xp->IsReady();
		}

		void Tick(float Dt)
		{
			const double Before = Life->IsRunning() ? Life->Sim().GameSeconds() : -1.0;
			World->Tick(LEVELTICK_All, Dt);
			const double After = Life->IsRunning() ? Life->Sim().GameSeconds() : -1.0;
			if (FMath::IsNearlyEqual(Before, After))
			{
				FTickableGameObject::TickObjects(World, LEVELTICK_All, false, Dt);       // the world tick did not reach the tickable subsystems
			}
			T += Dt;
		}

		void Run(float Seconds, float Dt = 0.1f)
		{
			for (float t = 0.f; t < Seconds; t += Dt)
			{
				Tick(Dt);
			}
		}

		/** Ticks until the predicate holds (seconds at most); true when it did. */
		bool RunUntil(TFunctionRef<bool()> Pred, float Max, float Dt = 0.1f)
		{
			for (float t = 0.f; t < Max; t += Dt)
			{
				if (Pred())
				{
					return true;
				}
				Tick(Dt);
			}
			return Pred();
		}

		void Destroy()
		{
			if (World)
			{
				GEngine->DestroyWorldContext(World);
				World->DestroyWorld(false);
				World = nullptr;
			}
		}

		// ------------------------------------------------------------------------------------------------ helpers
		FVector FloorOf(const TCHAR* Needle, FString* OutName = nullptr) const
		{
			const FAstraLifeMap& Map = Life->Sim().GetMap();
			for (const FAstraLifeComp& C : Map.Comps)
			{
				if (C.Status != EAstraRoomStatus::Planned && (C.Name.Contains(Needle) || C.Id.ToString() == Needle))
				{
					if (OutName)
					{
						*OutName = C.Name;
					}
					const FVector Mid = C.Box.GetCenter();
					return FVector(Mid.X, Mid.Y, C.Box.Min.Z);
				}
			}
			return FVector::ZeroVector;
		}

		FString RoomAt(const FVector& Cm) const
		{
			const FAstraLifeMap& Map = Life->Sim().GetMap();
			const int32 C = Map.CompartmentAt(Cm + FVector(0, 0, 40));
			return Map.Comps.IsValidIndex(C) ? Map.Comps[C].Id.ToString() : FString(TEXT("(nowhere)"));
		}

		bool Send(const TArray<FString>& Who, const FString& To, FString& Detail, const TArray<FString>& Flags = TArray<FString>(), const FString& From = FString())
		{
			const TSharedPtr<FJsonObject> A = MakeShared<FJsonObject>();
			TArray<TSharedPtr<FJsonValue>> W;
			for (const FString& S : Who)
			{
				W.Add(MakeShared<FJsonValueString>(S));
			}
			A->SetArrayField(TEXT("who"), W);
			A->SetStringField(TEXT("to"), To);
			A->SetStringField(TEXT("by"), TEXT("bench"));
			if (!From.IsEmpty())
			{
				A->SetStringField(TEXT("from"), From);
			}
			TArray<TSharedPtr<FJsonValue>> Over;
			for (const FString& F : Flags)
			{
				if (F == TEXT("hold"))
				{
					A->SetStringField(TEXT("energize"), TEXT("hold"));
				}
				else if (F == TEXT("window"))
				{
					A->SetBoolField(TEXT("shield_window"), true);
				}
				else if (F == TEXT("hazard"))
				{
					Over.Add(MakeShared<FJsonValueString>(TEXT("hazard")));
				}
				else if (F == TEXT("weak"))
				{
					Over.Add(MakeShared<FJsonValueString>(TEXT("weak_lock")));
				}
			}
			if (Over.Num())
			{
				A->SetArrayField(TEXT("override"), Over);
			}
			return Xp->ApplyCommand(TEXT("transport"), A, Detail);
		}

		const FAstraXportJob* Job(const FString& Tag) const { return Xp->FindJobConst(Tag); }

		/** The transport's tag out of "X3 accepted: ...". */
		static FString TagOf(const FString& Detail)
		{
			FString Tag;
			Detail.Split(TEXT(" "), &Tag, nullptr);
			return Tag;
		}

		/** Runs until the transport is over (done, failed, aborted, lost), noting every phase it went through. */
		bool Finish(const FString& Tag, float Max, TSet<uint8>& Seen)
		{
			for (float t = 0.f; t < Max; t += 0.1f)
			{
				if (const FAstraXportJob* J = Job(Tag))
				{
					Seen.Add((uint8)J->Phase);
					if (!AstraXportLive(J->Phase))
					{
						return true;
					}
				}
				Tick(0.1f);
			}
			return false;
		}

		FString CardText() const
		{
			FString Json;
			const TSharedRef<TJsonWriter<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>> W = TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&Json);
			FJsonSerializer::Serialize(Xp->SnapshotJson(), W);
			return Json;
		}

		int32 PersonOfDept(const TCHAR* Dept, int32 Skip = 0) const
		{
			const TArray<FAstraCrewman>& R = Ship->GetRoster().Get();
			for (int32 i = 0; i < Life->Sim().NumPeople(); ++i)
			{
				const FAstraLifePerson& P = Life->Sim().Person(i);
				if (P.Status == 0 && !P.bAway && !P.bTransit && R[P.Roster].Dept == Dept && P.Act != EAstraLifeAct::Sleep && P.Place != INDEX_NONE && Life->Sim().GetMap().Places[P.Place].External == NAME_None)
				{
					if (Skip-- <= 0)
					{
						return i;
					}
				}
			}
			return INDEX_NONE;
		}

		FString NpcId(int32 Person) const { return FString::Printf(TEXT("npc%d"), Life->Sim().Person(Person).Roster); }

		void Save(const FString& Dir, const TCHAR* Name) const
		{
			IFileManager::Get().MakeDirectory(*Dir, true);
			FFileHelper::SaveStringToFile(CardText(), *(Dir / Name));
		}
	};

	FString Phases(const TSet<uint8>& Seen)
	{
		FString Out;
		for (uint8 P = 0; P <= (uint8)EAstraXportPhase::Lost; ++P)
		{
			if (Seen.Contains(P))
			{
				Out += FString::Printf(TEXT("%s "), AstraXportPhaseName((EAstraXportPhase)P));
			}
		}
		return Out.TrimEnd();
	}
}

void AstraXportRunWorldBench(const FString& Fixtures)
{
	FXWorld W;
	if (!W.Make())
	{
		AstraXportBenchCheck(TEXT("world: the ship, her plan and the room come up"), false, TEXT("the world did not come up: no life, no damage model or no Transporter Room within 90 s"));
		W.Destroy();
		return;
	}
	UAstraTransporterSubsystem* X = W.Xp;
	X->SetTestSurface(true);
	AstraXportBenchCheck(TEXT("world: the room is found on the plan"), X->IsReady() && X->GetPads().Num() == 9,
	                     FString::Printf(TEXT("%d pads (six, the cargo pad, two emergency)"), X->GetPads().Num()));
	// the pads stand where the plan's own visitor stations stand (d5_transporter_B1.s6 and .s7 are on pads 1 and 4, by design)
	{
		const TArray<FAstraXportPad>& P = X->GetPads();
		const FVector P1(-100.0, 1060.0, -4968.8), P4(-500.0, 1060.0, -4968.8);
		AstraXportBenchCheck(TEXT("world: the pads stand where the kit puts them"), P.Num() >= 4 && P[0].PosCm.Equals(P1, 3.0) && P[3].PosCm.Equals(P4, 3.0),
		                     FString::Printf(TEXT("pad 1 at (%.0f, %.0f, %.1f) cm, pad 4 at (%.0f, %.0f, %.1f)"), P[0].PosCm.X, P[0].PosCm.Y, P[0].PosCm.Z, P[3].PosCm.X, P[3].PosCm.Y, P[3].PosCm.Z));
	}

	// ======================================================================================================== the Captain, the people, the ship
	FString RoomName;
	const FVector Bridge = W.FloorOf(TEXT("bridge"), &RoomName);
	const FVector Engineering = W.FloorOf(TEXT("Main Engineering"), &RoomName);
	const FVector Pad2 = X->GetPads()[1].PosCm;
	X->SetTestCaptain(true, Bridge + FVector(150.0, 100.0, 0.0));
	W.Run(2.f);

	// the card, before anything happens
	{
		const FString Card = W.CardText();
		W.Save(Fixtures, TEXT("card_idle.json"));
		AstraXportBenchCheck(TEXT("card: the console answers in plain numbers"), Card.Contains(TEXT("\"room\"")) && Card.Contains(TEXT("\"options\"")) && Card.Contains(TEXT("\"state\":\"ready\"")),
		                     FString::Printf(TEXT("%d characters"), Card.Len()));
	}

	// ---- a refusal says why, in words
	{
		FString D;
		const bool bNowhere = W.Send({TEXT("captain")}, TEXT("Atlantis"), D);
		const bool bNobody = W.Send({TEXT("Lieutenant Nobody")}, TEXT("pad 2"), D);
		FString D2;
		const bool bPads = W.Send({TEXT("captain")}, TEXT("pad 9"), D2);
		AstraXportBenchCheck(TEXT("order: a place that is not on the ship is refused, and so is a person who is not"), !bNowhere && !bNobody && !bPads,
		                     FString::Printf(TEXT("%s | %s"), *D2, *D));
	}

	// ======================================================================================================== inside the ship
	{
		FString Detail;
		const bool bOk = W.Send({TEXT("captain")}, TEXT("Main Engineering"), Detail);
		const FString Tag = FXWorld::TagOf(Detail);
		AstraXportBenchCheck(TEXT("order: the Captain to Main Engineering is accepted, with the lock time in the answer"), bOk && Detail.Contains(TEXT("lock in about")), Detail);
		if (bOk)
		{
			TSet<uint8> Seen;
			const FVector Before = X->TestCaptainCm();
			double MovedAt = -1.0, Start = W.T;
			bool bStillDuringDemat = true;
			for (float t = 0.f; t < 30.f; t += 0.1f)
			{
				const FAstraXportJob* J = W.Job(Tag);
				if (J)
				{
					Seen.Add((uint8)J->Phase);
					if (J->Phase == EAstraXportPhase::Demat && !X->TestCaptainCm().Equals(Before, 1.0))
					{
						bStillDuringDemat = false;
					}
					if (MovedAt < 0.0 && !X->TestCaptainCm().Equals(Before, 1.0))
					{
						MovedAt = W.T - Start;
					}
					if (!AstraXportLive(J->Phase))
					{
						break;
					}
				}
				W.Tick(0.1f);
			}
			const FAstraXportJob* J = W.Job(Tag);
			const bool bDone = J && J->Phase == EAstraXportPhase::Done;
			AstraXportBenchCheck(TEXT("cycle: a lock, a warm-up, a dematerialization, a rematerialization, a settling, done"), bDone && Seen.Contains((uint8)EAstraXportPhase::Locking) && Seen.Contains((uint8)EAstraXportPhase::Warmup) &&
			                     Seen.Contains((uint8)EAstraXportPhase::Demat) && Seen.Contains((uint8)EAstraXportPhase::Remat) && Seen.Contains((uint8)EAstraXportPhase::Settle),
			                     FString::Printf(TEXT("%s; took %.1f s; %s"), *Phases(Seen), W.T - Start, J ? *J->Outcome : TEXT("(no job)")));
			AstraXportBenchCheck(TEXT("cycle: he stays where he stood while he dematerializes and appears in Main Engineering after the pattern has left"),
			                     bStillDuringDemat && MovedAt > 4.0 && W.RoomAt(X->TestCaptainCm()).Contains(TEXT("engineering")),
			                     FString::Printf(TEXT("moved at %.1f s into the order, now in %s (%.0f, %.0f, %.0f)"), MovedAt, *W.RoomAt(X->TestCaptainCm()), X->TestCaptainCm().X, X->TestCaptainCm().Y, X->TestCaptainCm().Z));
			AstraXportBenchCheck(TEXT("cycle: the Captain's controls are free again and nobody is in the beam"), !X->IsCaptainInBeam(), TEXT(""));
		}
	}

	// ---- a person from where they work to a pad of the room
	{
		const int32 Person = W.PersonOfDept(TEXT("engineering"));
		if (Person == INDEX_NONE)
		{
			AstraXportBenchCheck(TEXT("people: an engineer is found at work"), false, TEXT("nobody of engineering is on duty and out of bed in this world's morning"));
		}
		else
		{
			const FAstraLifePerson& P0 = W.Life->Sim().Person(Person);
			const FVector From = P0.Pos;
			FString Detail;
			const bool bOk = W.Send({W.NpcId(Person)}, TEXT("pad 3"), Detail);
			const FString Tag = FXWorld::TagOf(Detail);
			TSet<uint8> Seen;
			bool bThere = false;
			if (bOk)
			{
				bool bTransitSeen = false;
				for (float t = 0.f; t < 30.f; t += 0.1f)
				{
					const FAstraXportJob* J = W.Job(Tag);
					if (J)
					{
						Seen.Add((uint8)J->Phase);
						bTransitSeen |= W.Life->Sim().Person(Person).bTransit;
						if (!AstraXportLive(J->Phase))
						{
							break;
						}
					}
					W.Tick(0.1f);
				}
				const FAstraLifePerson& P1 = W.Life->Sim().Person(Person);
				bThere = FVector::Dist2D(P1.Pos, X->GetPads()[2].PosCm) < 120.0;
				AstraXportBenchCheck(TEXT("people: an engineer is beamed from her post to pad 3 and VITA puts her there"), bThere && !P1.bTransit && !P1.bAway,
				                     FString::Printf(TEXT("from (%.0f, %.0f, %.0f) to (%.0f, %.0f, %.0f); pad 3 is at (%.0f, %.0f); in transit at some point: %d; %s"), From.X, From.Y, From.Z, P1.Pos.X, P1.Pos.Y, P1.Pos.Z,
				                                     X->GetPads()[2].PosCm.X, X->GetPads()[2].PosCm.Y, bTransitSeen ? 1 : 0, *Phases(Seen)));
			}
			else
			{
				AstraXportBenchCheck(TEXT("people: an engineer is beamed from her post to pad 3 and VITA puts her there"), false, Detail);
			}
		}
	}

	// ---- two at once, and a third behind them
	{
		const int32 A = W.PersonOfDept(TEXT("weapons"));
		const int32 B = W.PersonOfDept(TEXT("weapons"), 1);
		if (A != INDEX_NONE && B != INDEX_NONE)
		{
			FString D1, D2, D3;
			const bool b1 = W.Send({W.NpcId(A), W.NpcId(B)}, TEXT("Main Engineering"), D1);
			const bool b2 = W.Send({TEXT("captain")}, TEXT("pad 1"), D2);
			const bool b3 = W.Send({W.NpcId(A)}, TEXT("pad 4"), D3);
			const FString Tag1 = FXWorld::TagOf(D1), Tag2 = FXWorld::TagOf(D2);
			AstraXportBenchCheck(TEXT("queue: a second order waits behind the first, and a person already in an order cannot be ordered again"), b1 && b2 && D2.Contains(TEXT("queued")) && !b3 && D3.Contains(TEXT("already in a transport")),
			                     FString::Printf(TEXT("%s | %s | %s"), *D1.Left(120), *D2.Right(80), *D3.Left(140)));
			TSet<uint8> S1, S2;
			W.Finish(Tag1, 40.f, S1);
			W.Finish(Tag2, 40.f, S2);
			AstraXportBenchCheck(TEXT("queue: both are carried out, one after the other"), W.Job(Tag1) && W.Job(Tag2) && W.Job(Tag1)->Phase == EAstraXportPhase::Done && W.Job(Tag2)->Phase == EAstraXportPhase::Done,
			                     FString::Printf(TEXT("%s: %s | %s: %s"), *Tag1, W.Job(Tag1) ? *W.Job(Tag1)->Outcome.Left(90) : TEXT("?"), *Tag2, W.Job(Tag2) ? *W.Job(Tag2)->Outcome.Left(90) : TEXT("?")));
		}
	}

	// ---- hold the lock until the Captain's word
	{
		FString D;
		const bool bOk = W.Send({TEXT("captain")}, TEXT("Main Engineering"), D, {TEXT("hold")});
		const FString Tag = FXWorld::TagOf(D);
		const bool bHeld = bOk && W.RunUntil([&]() { const FAstraXportJob* J = W.Job(Tag); return J && J->Phase == EAstraXportPhase::Locked; }, 12.f);
		W.Run(2.f);
		const bool bStillHeld = W.Job(Tag) && W.Job(Tag)->Phase == EAstraXportPhase::Locked;
		FString D2;
		const bool bGo = W.Xp->Energize(Tag, D2);
		TSet<uint8> Seen;
		W.Finish(Tag, 30.f, Seen);
		AstraXportBenchCheck(TEXT("hold: the lock waits as long as it is not told, and goes on the word"), bHeld && bStillHeld && bGo && W.Job(Tag) && W.Job(Tag)->Phase == EAstraXportPhase::Done, FString::Printf(TEXT("%s -> %s"), *D2, W.Job(Tag) ? *W.Job(Tag)->Outcome.Left(80) : TEXT("?")));
	}

	// ---- an abort in the middle of the beam: nobody is lost
	{
		X->SetTestCaptain(true, Bridge + FVector(150.0, 100.0, 0.0));
		W.Run(0.5f);
		FString D;
		const bool bOk = W.Send({TEXT("captain")}, TEXT("Main Engineering"), D);
		const FString Tag = FXWorld::TagOf(D);
		const FVector Before = X->TestCaptainCm();
		const bool bDemat = bOk && W.RunUntil([&]() { const FAstraXportJob* J = W.Job(Tag); return J && J->Phase == EAstraXportPhase::Demat; }, 14.f);
		W.Run(1.0f);
		FString D2;
		const bool bAborted = W.Xp->Abort(Tag, TEXT("bench"), D2);
		W.Run(0.5f);
		AstraXportBenchCheck(TEXT("abort: cancelled mid-dematerialization the Captain is where he stood and free"), bDemat && bAborted && X->TestCaptainCm().Equals(Before, 1.0) && !X->IsCaptainInBeam() && W.Job(Tag)->Phase == EAstraXportPhase::Aborted, D2);
	}

	// ======================================================================================================== the world below
	{
		X->Reset();
		X->SetTestCaptain(true, Pad2);
		W.Run(0.5f);
		FString Detail;
		FString NoWindow;
		const bool bShielded = W.Send({TEXT("captain")}, TEXT("surface"), NoWindow);
		AstraXportBenchCheck(TEXT("ground: with our shields up the beam to the ground is refused: it leaves by the ventral face"), !bShielded && NoWindow.Contains(TEXT("shields_own")) && NoWindow.Contains(TEXT("ventral")), NoWindow.Left(200));
		const bool bOk = W.Send({TEXT("captain")}, TEXT("surface"), Detail, {TEXT("window")});
		const FString Tag = FXWorld::TagOf(Detail);
		AstraXportBenchCheck(TEXT("ground: the Captain to the surface is accepted with a shield window, over the orbit's range, with the longer lock"), bOk && Detail.Contains(TEXT("1200 km")), Detail);
		if (bOk)
		{
			TSet<uint8> Seen;
			W.Finish(Tag, 40.f, Seen);
			const FAstraXportJob* J = W.Job(Tag);
			const FVector Site = W.Ship->SurfaceSite();
			AstraXportBenchCheck(TEXT("ground: he stands on the ground by the landing field, the ship knows he is down there and the card says he is away"),
			                     J && J->Phase == EAstraXportPhase::Done && X->TestCaptainOnGround() && FVector::Dist2D(X->TestCaptainCm(), Site) < 900.0 && X->GetAway().Num() == 1 && X->GetAway()[0].Id == TEXT("captain"),
			                     FString::Printf(TEXT("%s; feet (%.0f, %.0f, %.0f), the field is at (%.0f, %.0f, %.0f); %s"), *Phases(Seen), X->TestCaptainCm().X, X->TestCaptainCm().Y, X->TestCaptainCm().Z, Site.X, Site.Y, Site.Z, J ? *J->Outcome.Left(120) : TEXT("?")));
			W.Save(Fixtures, TEXT("card_captain_down.json"));
			// he calls for the pads from the ground
			// pad 3 is where the engineer was set down a minute ago and she is still standing there: the order is refused for that, not moved to another pad
			FString DBusy;
			const bool bBusy = W.Send({TEXT("captain")}, TEXT("pad 3"), DBusy, {TEXT("window")});
			AstraXportBenchCheck(TEXT("pads: an order to a pad where somebody stands is refused, not sent to another pad"), !bBusy && DBusy.Contains(TEXT("[occupied]")), DBusy.Left(160));
			FString D2;
			const bool bBack = W.Send({TEXT("captain")}, TEXT("pad 6"), D2, {TEXT("window")});
			const FString Tag2 = FXWorld::TagOf(D2);
			TSet<uint8> Seen2;
			W.Finish(Tag2, 40.f, Seen2);
			const FAstraXportJob* J2 = W.Job(Tag2);
			AstraXportBenchCheck(TEXT("ground: from the ground he is brought back to a pad of the room"), bBack && J2 && J2->Phase == EAstraXportPhase::Done && !X->TestCaptainOnGround() && X->GetAway().Num() == 0 &&
			                     FVector::Dist2D(X->TestCaptainCm(), X->GetPads()[5].PosCm) < 150.0,
			                     FString::Printf(TEXT("%s | on the ground: %d, feet (%.0f, %.0f, %.0f), pad 6 at (%.0f, %.0f)"), *D2.Left(110), X->TestCaptainOnGround() ? 1 : 0, X->TestCaptainCm().X, X->TestCaptainCm().Y, X->TestCaptainCm().Z, X->GetPads()[5].PosCm.X, X->GetPads()[5].PosCm.Y));
		}
		// cargo: a crate of supplies to the ground and back; the card lists it as away
		{
			FString D3;
			const bool bCargo = W.Send({TEXT("cargo 300 kg medical supplies")}, TEXT("surface"), D3, {TEXT("window")});
			const FString Tag3 = FXWorld::TagOf(D3);
			TSet<uint8> Seen3;
			if (bCargo)
			{
				W.Finish(Tag3, 40.f, Seen3);
			}
			AstraXportBenchCheck(TEXT("cargo: 300 kg of supplies from the cargo pad to the ground, listed as away"), bCargo && W.Job(Tag3) && W.Job(Tag3)->Phase == EAstraXportPhase::Done && X->GetAway().Num() == 1 && X->GetAway()[0].bCargo, D3.Left(160));
			FString D4;
			const bool bHeavy = W.Send({TEXT("cargo 3000 kg ore")}, TEXT("surface"), D4, {TEXT("window")});
			AstraXportBenchCheck(TEXT("cargo: three tonnes are too much for a pad"), !bHeavy && D4.Contains(TEXT("[mass]")), D4.Left(160));
		}
	}

	// ======================================================================================================== the battle
	{
		X->Reset();
		W.Run(1.f);
		GEngine->Exec(W.World, TEXT("astra.war.tune shield_scale 1.5"));
		GEngine->Exec(W.World, TEXT("astra.war.scenario sym_two aquila at=0,0,0 hold"));
		W.Battle->StartCampaign();
		W.Run(3.f);
		FString AllyId, HostileId;
		for (const UAstraBattleSubsystem::FContactView& C : W.Battle->Contacts())
		{
			UE_LOG(LogASTRA, Display, TEXT("[Transport]   contact %s %s class '%s' side %d track %d range %.1f km craft %d"), *C.ContactId, *C.Label, *C.Class, (int32)C.Side, (int32)C.Track, C.RangeKm, C.bCraft ? 1 : 0);
			if (!C.bCraft)
			{
				if (C.Side == EAstraSide::Astra && AllyId.IsEmpty())
				{
					AllyId = C.ContactId;
				}
				if (C.Side == EAstraSide::Mandate && HostileId.IsEmpty())
				{
					HostileId = C.ContactId;
				}
			}
		}
		AstraXportBenchCheck(TEXT("battle: an allied squadron and a Mandate one are on the plot"), !AllyId.IsEmpty() && !HostileId.IsEmpty(), FString::Printf(TEXT("allied %s, hostile %s"), *AllyId, *HostileId));
		if (!AllyId.IsEmpty() && !HostileId.IsEmpty())
		{
			W.Save(Fixtures, TEXT("card_battle.json"));
			X->SetTestCaptain(true, Pad2);
			// the ground and the ships, with our shields up: the console says why not, and says what clears it
			FString DH;
			const bool bHostile = W.Send({TEXT("marines 4")}, HostileId, DH);
			AstraXportBenchCheck(TEXT("shields: a landing party onto a hostile ship with her shields up is refused, by her shield and by ours"), !bHostile && DH.Contains(TEXT("shields_theirs")) && DH.Contains(TEXT("shields_own")), DH);
			FString DA;
			const bool bAlly = W.Send({TEXT("marines 4")}, AllyId, DA);
			AstraXportBenchCheck(TEXT("shields: to an allied ship the refusal is ours alone: our shields are up on the face the beam leaves through"), !bAlly && DA.Contains(TEXT("shields_own")) && !DA.Contains(TEXT("shields_theirs")), DA);
			FString DW;
			const bool bWindow = W.Send({TEXT("marines 4")}, AllyId, DW, {TEXT("window")});
			const FString Tag = FXWorld::TagOf(DW);
			AstraXportBenchCheck(TEXT("shields: with a shield window the order is accepted and says our shields will be held down"), bWindow && DW.Contains(TEXT("shield window")), DW);
			if (bWindow)
			{
				bool bDown = false, bUpBefore = W.Ship->AreShieldsUp();
				TSet<uint8> Seen;
				for (float t = 0.f; t < 45.f; t += 0.1f)
				{
					const FAstraXportJob* J = W.Job(Tag);
					if (J)
					{
						Seen.Add((uint8)J->Phase);
						bDown |= AstraXportInBeam(J->Phase) && !W.Ship->AreShieldsUp();
						if (!AstraXportLive(J->Phase))
						{
							break;
						}
					}
					W.Tick(0.1f);
				}
				W.Run(3.f);
				const FAstraXportJob* J = W.Job(Tag);
				AstraXportBenchCheck(TEXT("shields: they were down for the cycle and are up again after it"), bUpBefore && bDown && W.Ship->AreShieldsUp(), FString::Printf(TEXT("%s; %s"), *Phases(Seen), J ? *J->Outcome.Left(120) : TEXT("?")));
				AstraXportBenchCheck(TEXT("away: the party is off the ship, on the card, and the locator says so"), J && J->Phase == EAstraXportPhase::Done && W.Xp->GetAway().Num() == 4,
				                     FString::Printf(TEXT("%d away: %s"), W.Xp->GetAway().Num(), W.Xp->GetAway().Num() ? *W.Xp->GetAway()[0].WhereText : TEXT("")));
				W.Save(Fixtures, TEXT("card_away.json"));
				if (W.Xp->GetAway().Num())
				{
					const FString Locator = W.Life->LocatorText(W.Xp->GetAway()[0].Label.Right(8), 2);
					AstraXportBenchCheck(TEXT("away: the personnel locator knows them to be elsewhere"), Locator.Contains(TEXT("not aboard")), Locator.Left(200));
				}
				// ... and brought home
				FString DB;
				const bool bBack = W.Send({TEXT("away team")}, TEXT("pad 5"), DB, {TEXT("window")});
				const FString TagB = FXWorld::TagOf(DB);
				TSet<uint8> SeenB;
				W.Finish(TagB, 60.f, SeenB);
				W.Run(2.f);
				AstraXportBenchCheck(TEXT("away: the away team is called back to the pads and nobody is left out there"), bBack && W.Job(TagB) && W.Job(TagB)->Phase == EAstraXportPhase::Done && W.Xp->GetAway().Num() == 0,
				                     FString::Printf(TEXT("%s | away now %d | %s"), *DB.Left(100), W.Xp->GetAway().Num(), W.Job(TagB) ? *W.Job(TagB)->Outcome.Left(100) : TEXT("?")));
			}
			// the Mandate's face is spent: nothing in the rules forbids it any more
			GEngine->Exec(W.World, TEXT("astra.war.tune shield_scale 0"));
		}
	}

	// ======================================================================================================== the damaged room
	{
		X->Reset();
		FAstraImpactResult R;
		const int32 Comp = W.Ship->GetInterior().GetMap().CompByName.FindRef(FName(TEXT("d5_transporter_B1")), INDEX_NONE);
		X->SetTestCaptain(true, Engineering);
		if (Comp != INDEX_NONE)
		{
			W.Ship->GetInterior().Overload(Comp, 1.0f, R);
			W.Run(1.f);
			FString D;
			const bool bOk = W.Send({TEXT("captain")}, TEXT("pad 2"), D);
			AstraXportBenchCheck(TEXT("room: a room with no power sends nobody: the card says so and so does the order"), !bOk && D.Contains(TEXT("[room]")), D.Left(220));
			const FString Card = W.CardText();
			AstraXportBenchCheck(TEXT("room: the card shows the room's state"), Card.Contains(TEXT("\"state\":\"offline\"")) || Card.Contains(TEXT("\"state\":\"wrecked\"")), Card.Left(160));
			W.Save(Fixtures, TEXT("card_room_dark.json"));
		}
		else
		{
			AstraXportBenchCheck(TEXT("room: the damage model has the Transporter Room"), false, TEXT("d5_transporter_B1 is not in the damage map"));
		}
	}

	// ======================================================================================================== cost
	{
		AstraXportBenchCheck(TEXT("cost: the subsystem's tick is far under a millisecond"), X->LastTickMs() < 1.0, FString::Printf(TEXT("%.3f ms"), X->LastTickMs()));
		UE_LOG(LogASTRA, Display, TEXT("[Transport] %s"), *X->InfoText());
		for (int32 i = FMath::Max(0, W.Events.Num() - 40); i < W.Events.Num(); ++i)
		{
			if (W.Events[i].Contains(TEXT("transporter:")))
			{
				UE_LOG(LogASTRA, Display, TEXT("[Transport]   event %s"), *W.Events[i]);
			}
		}
	}
	W.Destroy();
}
