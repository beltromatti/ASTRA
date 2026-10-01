// TELETRASPORTO — the card: the console as the Chief reads it (`ship_state.transporter`), the numbers the wall screen draws, the events the minds are told, and the console commands
// (astra.xport.*) the lead tries the room with (docs/TELETRASPORTO.md §8).

#include "AstraTransporterSubsystem.h"

#include "ASTRA.h"
#include "ASTRAPlayerController.h"
#include "AstraBattleSubsystem.h"
#include "AstraDeckStreaming.h"
#include "AstraLifeSubsystem.h"
#include "AstraShipSubsystem.h"
#include "AstraTransportConsole.h"
#include "Engine/World.h"
#include "HAL/FileManager.h"
#include "HAL/IConsoleManager.h"
#include "Kismet/GameplayStatics.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"

using namespace AstraXport;

namespace
{
	TSharedPtr<FJsonValue> JStr(const FString& S) { return MakeShared<FJsonValueString>(S); }
	TArray<TSharedPtr<FJsonValue>> JStrs(const TArray<FString>& In)
	{
		TArray<TSharedPtr<FJsonValue>> Out;
		for (const FString& S : In)
		{
			Out.Add(JStr(S));
		}
		return Out;
	}
	double Round1(double X) { return FMath::RoundToDouble(X * 10.0) / 10.0; }
	double Pc(float F) { return FMath::RoundToDouble(F * 100.0); }

	const TCHAR* RoomStateOf(const FRoomState& R, const FTuning& T)
	{
		if (!R.bExists || R.bGutted || R.Wreck >= 0.9f)
		{
			return TEXT("wrecked");
		}
		if (R.Power < T.RoomOffline)
		{
			return TEXT("offline");
		}
		if (R.Fire > T.FireMax || R.Smoke > T.SmokeMax || R.Air < T.AirMin || R.Heat > T.HeatMax)
		{
			return TEXT("hazard");
		}
		return R.Power < T.RoomDegraded ? TEXT("reduced") : TEXT("ready");
	}
}

// ================================================================================================ what the console would say to a request
void UAstraTransporterSubsystem::BuildOptions(TArray<FAstraXportOption>& Out, int32 Max) const
{
	Out.Reset();
	if (!bRoomKnown)
	{
		return;
	}
	FEnv E;
	BuildEnv(E);
	auto Probe = [this, &E, &Out](const FEnd& To, const FString& Label, const FString& ToText)
	{
		FRequest R;
		FSubject S;
		S.Kind = ESubject::Person;
		S.Id = TEXT("probe");
		S.Label = TEXT("a person");
		S.MassKg = 88.f;
		R.Subjects.Add(S);
		R.From.Kind = EEndKind::Pad;
		R.From.bPad = true;
		R.From.Pad = 0;
		R.From.Label = TEXT("pad 1");
		R.From.CompKind = T.RoomKind;
		R.From.Room = E.Main;
		R.To = To;
		const FVerdict V = Evaluate(T, E, R);
		FRequest RW = R;
		RW.bShieldWindow = true;
		const FVerdict VW = Evaluate(T, E, RW);
		FAstraXportOption O;
		O.To = ToText;
		O.Label = Label;
		O.bOk = V.bOk && V.Unknown.Num() == 0;
		O.bUnknown = V.Unknown.Num() > 0;
		O.RangeKm = V.RangeKm;
		O.LockS = V.LockS;
		O.QualityPct = (float)Pc(V.Quality);
		O.OwnFace = V.OwnFace;
		O.TheirFace = V.TheirFace;
		for (const FBlocker& B : V.Blockers)
		{
			O.Why.Add(B.Why);
			if (O.Fix.IsEmpty())
			{
				O.Fix = B.Fix;
			}
		}
		for (const FString& U : V.Unknown)
		{
			O.Why.Add(U);
		}
		if (!O.bOk && VW.bOk && VW.Unknown.Num() == 0)
		{
			O.Fix = TEXT("a shield window (Tactical holds our shields down for the cycle) clears it");
		}
		O.Notes = V.Notes;
		Out.Add(O);
	};
	// the ground
	{
		FEnd G;
		FString Comp, Err;
		if (ResolveEnd(TEXT("surface"), true, TArray<FAstraXportSubject>(), G, Comp, Err))
		{
			Probe(G, G.Label, TEXT("surface"));
		}
	}
	// the ships on the plot: the nearest first (Contacts() is sorted so)
	if (const UAstraBattleSubsystem* B = Battle())
	{
		for (const UAstraBattleSubsystem::FContactView& C : B->Contacts())
		{
			if (Out.Num() >= Max)
			{
				break;
			}
			if (C.bCraft || C.Track < 2 || C.RangeKm < 0.0 || C.RangeKm > T.MaxRangeKm * 1.6)
			{
				continue;
			}
			FEnd S;
			FString Comp, Err;
			if (ResolveEnd(C.ContactId, true, TArray<FAstraXportSubject>(), S, Comp, Err))
			{
				const TCHAR* Side = S.Ship.Side == EAllegiance::Allied ? TEXT("allied") : (S.Ship.Side == EAllegiance::Hostile ? TEXT("hostile") : (S.Ship.Side == EAllegiance::Derelict ? TEXT("derelict") : TEXT("neutral")));
				Probe(S, FString::Printf(TEXT("%s (%s), %.0f km"), *S.Label, Side, C.RangeKm), C.ContactId);
			}
		}
	}
	// the Medbay's emergency pads (a system of their own)
	if (Out.Num() < Max + 1)
	{
		FEnd M;
		M.Kind = EEndKind::Pad;
		M.bPad = true;
		M.bEmergencyPad = true;
		M.Pad = 0;
		M.Label = TEXT("emergency pad 1 (Medbay)");
		M.CompKind = FName(TEXT("medbay"));
		M.Room = E.Emergency;
		Probe(M, M.Label, TEXT("med1"));
	}
}

// ================================================================================================ the card
void UAstraTransporterSubsystem::GetView(FAstraXportView& V) const
{
	V = FAstraXportView();
	V.bReady = bRoomKnown;
	if (!bRoomKnown)
	{
		return;
	}
	FEnv E;
	BuildEnv(E);
	V.RoomState = RoomStateOf(E.Main, T);
	V.RoomPower = E.Main.Power;
	V.RoomWreck = E.Main.Wreck;
	V.ReachKm = ReachKm(T, E, false);
	V.CycleS = CycleSeconds(T, E.Main);
	V.EnergyMW = EnergyFor(T, 1);
	V.Accel = E.AccelMps2;
	V.Turn = E.TurnDegS;
	V.bShieldsUp = E.Own.bShieldsUp;
	for (int32 f = 0; f < NumFaces; ++f)
	{
		V.Faces[f] = E.Own.Frac[f];
	}
	V.GateKm = E.GateKm;
	V.bGateLane = E.bGateLane;
	for (const FAstraXportJob& J : JobList)
	{
		if (AstraXportLive(J.Phase))
		{
			V.OwnFace = J.OwnFace;
			V.TheirFace = J.TheirFace;
			V.Jam = FMath::Max(V.Jam, J.Jam);
			break;
		}
	}
	BuildOptions(V.Options, 3);
	V.Away = AwayList.Num();
	for (int32 i = 0; i < Pads.Num() && i < 9; ++i)
	{
		V.bPadBusy[i] = !Pads[i].Occupant.IsEmpty() || Pads[i].Look != EAstraPadLook::Idle;
		V.PadWho[i] = Pads[i].Occupant;
	}
	V.Last = LastOutcome;
}

TSharedRef<FJsonObject> UAstraTransporterSubsystem::SnapshotJson() const
{
	TSharedRef<FJsonObject> O = MakeShared<FJsonObject>();
	if (!bRoomKnown)
	{
		O->SetStringField(TEXT("state"), TEXT("dark: the Transporter Room is not on the plan"));
		return O;
	}
	FEnv E;
	BuildEnv(E);
	// the room and the power behind it
	{
		TSharedRef<FJsonObject> R = MakeShared<FJsonObject>();
		R->SetStringField(TEXT("state"), RoomStateOf(E.Main, T));
		R->SetNumberField(TEXT("power_pct"), Pc(E.Main.Power));
		R->SetNumberField(TEXT("wreck_pct"), Pc(E.Main.Wreck));
		R->SetNumberField(TEXT("reach_km"), FMath::RoundToDouble(ReachKm(T, E, false)));
		R->SetNumberField(TEXT("cycle_s"), Round1(CycleSeconds(T, E.Main)));
		R->SetNumberField(TEXT("energy_mw_for_one"), EnergyFor(T, 1));
		R->SetNumberField(TEXT("pads"), T.Pads);
		R->SetStringField(TEXT("emergency_pads"), FString::Printf(TEXT("%s, reach %.0f km"), RoomStateOf(E.Emergency, T), ReachKm(T, E, true)));
		R->SetStringField(TEXT("reactor"), E.bReactorOn ? TEXT("on") : TEXT("down"));
		O->SetObjectField(TEXT("room"), R);
	}
	// who stands on the pads
	{
		TArray<FString> On;
		for (const FAstraXportPad& P : Pads)
		{
			if (!P.Occupant.IsEmpty())
			{
				On.Add(FString::Printf(TEXT("%s: %s"), P.bCargo ? TEXT("cargo pad") : (P.bEmergency ? *FString::Printf(TEXT("med%d"), P.Index + 1) : *FString::Printf(TEXT("pad %d"), P.Index + 1)), *P.Occupant));
			}
		}
		O->SetArrayField(TEXT("on_pads"), JStrs(On));
	}
	// the Aquila as the beam sees her
	{
		TSharedRef<FJsonObject> S = MakeShared<FJsonObject>();
		S->SetStringField(TEXT("shields"), E.Own.bShieldsUp ? TEXT("up") : TEXT("down"));
		TSharedRef<FJsonObject> F = MakeShared<FJsonObject>();
		static const TCHAR* Names[NumFaces] = {TEXT("bow"), TEXT("stern"), TEXT("port"), TEXT("starboard"), TEXT("dorsal"), TEXT("ventral")};
		for (int32 f = 0; f < NumFaces; ++f)
		{
			F->SetNumberField(Names[f], Pc(E.Own.Frac[f]));
		}
		S->SetObjectField(TEXT("face_charge_pct"), F);
		S->SetNumberField(TEXT("accel_mps2"), Round1(E.AccelMps2));
		S->SetNumberField(TEXT("turn_deg_s"), Round1(E.TurnDegS));
		if (E.GateKm >= 0.f)
		{
			S->SetNumberField(TEXT("gate_km"), FMath::RoundToDouble(E.GateKm));
		}
		S->SetBoolField(TEXT("in_gate_lane"), E.bGateLane);
		S->SetNumberField(TEXT("sensors_power_pct"), Pc(E.SensorsPower));
		O->SetObjectField(TEXT("aquila"), S);
	}
	// the transports
	{
		TArray<TSharedPtr<FJsonValue>> Jobs;
		for (const FAstraXportJob& J : JobList)
		{
			if (!AstraXportLive(J.Phase) && Now - J.EndedAt > 90.0)
			{
				continue;
			}
			TSharedRef<FJsonObject> JO = MakeShared<FJsonObject>();
			JO->SetStringField(TEXT("id"), J.Tag);
			JO->SetStringField(TEXT("who"), Who(J));
			JO->SetStringField(TEXT("from"), J.FromText);
			JO->SetStringField(TEXT("to"), J.ToText);
			JO->SetStringField(TEXT("state"), AstraXportPhaseName(J.Phase));
			if (AstraXportLive(J.Phase))
			{
				const float K = J.CycleS / FMath::Max(0.1f, T.CycleS);
				float Eta = 0.f;
				if (J.Phase == EAstraXportPhase::Queued || J.Phase == EAstraXportPhase::Locking)
				{
					Eta = (1.f - J.Lock.Progress) * J.Lock.NeedS + J.CycleS;
				}
				else if (J.Phase == EAstraXportPhase::Locked)
				{
					Eta = J.bHold ? -1.f : J.CycleS;
				}
				else if (J.Phase == EAstraXportPhase::Buffer)
				{
					Eta = FMath::Max(0.f, J.Arrival.DelayS - J.BufferS) + T.RematS * K + T.SettleS * K;
				}
				else
				{
					Eta = FMath::Max(0.f, J.CycleS - J.Cycle);
				}
				if (Eta >= 0.f)
				{
					JO->SetNumberField(TEXT("eta_s"), Round1(Eta));
				}
				JO->SetNumberField(TEXT("lock_built_pct"), Pc(J.Lock.Progress));
				JO->SetNumberField(TEXT("lock_quality_pct"), Pc(J.Lock.Quality));
				JO->SetStringField(TEXT("lock"), FLock::Name(J.Lock.State));
				JO->SetBoolField(TEXT("waiting_for_the_word"), J.bHold && J.Phase == EAstraXportPhase::Locked);
				JO->SetBoolField(TEXT("shield_window"), J.bWindow);
				if (J.Phase == EAstraXportPhase::Buffer)
				{
					JO->SetNumberField(TEXT("buffered_s"), Round1(J.BufferS));
					JO->SetNumberField(TEXT("buffer_limit_s"), T.BufferHoldS);
				}
				if (J.Blockers.Num())
				{
					JO->SetArrayField(TEXT("in_the_way"), JStrs(J.Blockers));
				}
				if (J.Notes.Num())
				{
					JO->SetArrayField(TEXT("costs_the_lock"), JStrs(J.Notes));
				}
			}
			else
			{
				JO->SetStringField(TEXT("outcome"), J.Outcome);
			}
			if (!J.By.IsEmpty())
			{
				JO->SetStringField(TEXT("ordered_by"), J.By);
			}
			Jobs.Add(MakeShared<FJsonValueObject>(JO));
		}
		O->SetArrayField(TEXT("transports"), Jobs);
	}
	// who is away
	{
		TArray<TSharedPtr<FJsonValue>> Away;
		for (const FAstraXportAway& A : AwayList)
		{
			TSharedRef<FJsonObject> AO = MakeShared<FJsonObject>();
			AO->SetStringField(TEXT("who"), A.bCargo ? A.Label : (A.Person != INDEX_NONE ? FString::Printf(TEXT("%s (%s)"), *A.Label, *A.Id) : A.Label));
			AO->SetStringField(TEXT("where"), A.WhereText);
			AO->SetNumberField(TEXT("since_s"), FMath::RoundToDouble(Now - A.Since));
			Away.Add(MakeShared<FJsonValueObject>(AO));
		}
		O->SetArrayField(TEXT("away"), Away);
	}
	// what the console would answer to a request now
	{
		TArray<FAstraXportOption> Opts;
		BuildOptions(Opts, 6);
		TArray<TSharedPtr<FJsonValue>> Arr;
		for (const FAstraXportOption& X : Opts)
		{
			TSharedRef<FJsonObject> XO = MakeShared<FJsonObject>();
			XO->SetStringField(TEXT("to"), X.To);
			XO->SetStringField(TEXT("place"), X.Label);
			XO->SetStringField(TEXT("answer"), X.bOk ? TEXT("can be done now") : (X.bUnknown ? TEXT("cannot be aimed: the sensors cannot read her shields") : TEXT("cannot be done now")));
			if (X.RangeKm > 0.f)
			{
				XO->SetNumberField(TEXT("range_km"), FMath::RoundToDouble(X.RangeKm));
			}
			if (X.bOk || X.LockS > 0.f)
			{
				XO->SetNumberField(TEXT("lock_s"), Round1(X.LockS));
				XO->SetNumberField(TEXT("lock_quality_pct"), X.QualityPct);
			}
			if (X.Why.Num())
			{
				XO->SetArrayField(TEXT("in_the_way"), JStrs(X.Why));
			}
			if (!X.Fix.IsEmpty() && !X.bOk)
			{
				XO->SetStringField(TEXT("what_clears_it"), X.Fix);
			}
			if (X.Notes.Num())
			{
				XO->SetArrayField(TEXT("costs_the_lock"), JStrs(X.Notes));
			}
			Arr.Add(MakeShared<FJsonValueObject>(XO));
		}
		O->SetArrayField(TEXT("options"), Arr);
		O->SetStringField(TEXT("aboard"), TEXT("any room of the Aquila, from where they stand: about 1.5 s of lock, no shield matters"));
	}
	if (!LastOutcome.IsEmpty())
	{
		O->SetStringField(TEXT("last"), LastOutcome);
	}
	// the people at the consoles (VITA's): who the Chief's hands are
	if (const UAstraLifeSubsystem* L = Life(); L && L->IsRunning())
	{
		if (const int32* Ci = L->Sim().GetMap().CompByName.Find(FName(*RoomCompId)))
		{
			TArray<int32> People;
			L->Sim().PeopleInComp(*Ci, People);
			TArray<FString> Names;
			if (const UAstraShipSubsystem* S = Ship())
			{
				for (const int32 P : People)
				{
					const FAstraLifePerson& Pe = L->Sim().Person(P);
					Names.Add(FString::Printf(TEXT("%s (%s)"), *S->GetRoster().Get()[Pe.Roster].Name(), *Pe.Job));
					if (Names.Num() >= 5)
					{
						break;
					}
				}
			}
			O->SetArrayField(TEXT("in_the_room"), JStrs(Names));
		}
	}
	return O;
}

// ================================================================================================ the news
void UAstraTransporterSubsystem::Say(const FString& Text, bool bReport) const
{
	if (UAstraShipSubsystem* S = Ship())
	{
		S->PublishEvent(FString::Printf(TEXT("transporter: %s"), *Text), bReport);
	}
}

void UAstraTransporterSubsystem::News(const FAstraXportJob& J, const FString& Text, bool bReport) const
{
	(void)J;
	Say(Text, bReport);
}

// ================================================================================================ reset and info
void UAstraTransporterSubsystem::Reset()
{
	UAstraLifeSubsystem* L = Life();
	for (FAstraXportJob& J : JobList)
	{
		if (AstraXportLive(J.Phase))
		{
			RecomposeAtOrigin(J, TEXT("reset"));
			J.Phase = EAstraXportPhase::Aborted;
		}
	}
	JobList.Reset();
	for (const FAstraXportAway& A : AwayList)
	{
		if (A.Person != INDEX_NONE && L && L->IsRunning())
		{
			L->Sim().PlaceTransported(A.Person, L->Sim().Person(A.Person).Pos, 0.f, 1.5f);
		}
		if (AActor* B = A.Body.Get())
		{
			B->Destroy();
		}
	}
	AwayList.Reset();
	CaptainBeamJob = INDEX_NONE;
	CycleOwner = INDEX_NONE;
	EmergencyOwner = INDEX_NONE;
	if (bWindowHeld)
	{
		CloseWindow(nullptr);
	}
	LockCaptain(false);
	for (TObjectPtr<AActor>& A : Props)
	{
		if (A)
		{
			A->Destroy();
		}
	}
	Props.Reset();
	LastOutcome.Reset();
	NextSerial = 1;
	if (Fx && HumLoop)
	{
		Fx->StopLoop(HumLoop, 0.2f);
		HumLoop = 0;
	}
}

FString UAstraTransporterSubsystem::InfoText() const
{
	if (!bRoomKnown)
	{
		return TEXT("[Transport] the Transporter Room is not on the plan (yet)");
	}
	FString Out = FString::Printf(TEXT("[Transport] %s on deck %d, origin (%.0f, %.0f, %.0f) yaw %.0f; %d pads + cargo + %d emergency; %d transports on the console, %d away; fx: %s; tick %.3f ms"),
	                              *RoomCompId, RoomDeck, RoomOriginCm.X, RoomOriginCm.Y, RoomOriginCm.Z, RoomYawDeg, T.Pads, T.EmergencyPads, JobList.Num(), AwayList.Num(),
	                              Fx ? *Fx->Describe() : TEXT("none (headless)"), TickMs);
	for (const FAstraXportJob& J : JobList)
	{
		Out += FString::Printf(TEXT("\n  %s %s: %s -> %s (%s)%s"), *J.Tag, *Who(J), *J.FromText, *J.ToText, AstraXportPhaseName(J.Phase), J.Outcome.IsEmpty() ? TEXT("") : *FString::Printf(TEXT(": %s"), *J.Outcome));
	}
	for (const FAstraXportAway& A : AwayList)
	{
		Out += FString::Printf(TEXT("\n  away: %s %s"), *A.Label, *A.WhereText);
	}
	return Out;
}

// ================================================================================================ the console commands
namespace
{
	UAstraTransporterSubsystem* Xp(UWorld* W) { return W ? W->GetSubsystem<UAstraTransporterSubsystem>() : nullptr; }

	void XpLog(const FString& S)
	{
		UE_LOG(LogASTRA, Display, TEXT("%s"), *S);
	}

	FAutoConsoleCommandWithWorldAndArgs CmdInfo(TEXT("astra.xport.info"), TEXT("TELETRASPORTO: the Transporter Room's state, its transports and who is away"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& A, UWorld* W)
		{
			if (UAstraTransporterSubsystem* X = Xp(W))
			{
				XpLog(X->InfoText());
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdCard(TEXT("astra.xport.card"), TEXT("TELETRASPORTO: the card the Chief reads (ship_state.transporter), as JSON"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& A, UWorld* W)
		{
			if (UAstraTransporterSubsystem* X = Xp(W))
			{
				FString Json;
				const TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&Json);
				FJsonSerializer::Serialize(X->SnapshotJson(), Writer);
				XpLog(Json);
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdSend(TEXT("astra.xport.send"),
		TEXT("TELETRASPORTO: astra.xport.send <who> <to> [from=<place>] [hold] [window] [hazard] [weak]   who: captain | npc17 | \"Lieutenant Sato\" | \"marines 4\" | \"cargo 300 kg supplies\" (several: separate with ;)   to: \"pad 2\" | surface | T-02 | \"Main Engineering\" | med1"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& A, UWorld* W)
		{
			UAstraTransporterSubsystem* X = Xp(W);
			if (!X || A.Num() < 2)
			{
				XpLog(TEXT("[Transport] astra.xport.send <who> <to> [from=<place>] [hold] [window] [hazard] [weak]"));
				return;
			}
			const TSharedPtr<FJsonObject> Args = MakeShared<FJsonObject>();
			Args->SetStringField(TEXT("who"), A[0]);
			Args->SetStringField(TEXT("to"), A[1]);
			Args->SetStringField(TEXT("by"), TEXT("console"));
			TArray<TSharedPtr<FJsonValue>> Over;
			for (int32 i = 2; i < A.Num(); ++i)
			{
				if (A[i].StartsWith(TEXT("from=")))
				{
					Args->SetStringField(TEXT("from"), A[i].Mid(5));
				}
				else if (A[i] == TEXT("hold"))
				{
					Args->SetStringField(TEXT("energize"), TEXT("hold"));
				}
				else if (A[i] == TEXT("window"))
				{
					Args->SetBoolField(TEXT("shield_window"), true);
				}
				else if (A[i] == TEXT("hazard"))
				{
					Over.Add(JStr(TEXT("hazard")));
				}
				else if (A[i] == TEXT("weak"))
				{
					Over.Add(JStr(TEXT("weak_lock")));
				}
			}
			if (Over.Num())
			{
				Args->SetArrayField(TEXT("override"), Over);
			}
			FString Detail;
			const bool bOk = X->ApplyCommand(TEXT("transport"), Args, Detail);
			XpLog(FString::Printf(TEXT("[Transport] %s: %s"), bOk ? TEXT("ok") : TEXT("NO"), *Detail));
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdEnergize(TEXT("astra.xport.energize"), TEXT("TELETRASPORTO: astra.xport.energize [X3]: the word for a lock that is held"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& A, UWorld* W)
		{
			if (UAstraTransporterSubsystem* X = Xp(W))
			{
				FString D;
				const bool bOk = X->Energize(A.Num() ? A[0] : FString(), D);
				XpLog(FString::Printf(TEXT("[Transport] %s: %s"), bOk ? TEXT("ok") : TEXT("NO"), *D));
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdAbort(TEXT("astra.xport.abort"), TEXT("TELETRASPORTO: astra.xport.abort [X3]: cancel a transport (mid-cycle the pattern is recomposed, in the buffer it is called back)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& A, UWorld* W)
		{
			if (UAstraTransporterSubsystem* X = Xp(W))
			{
				FString D;
				const bool bOk = X->Abort(A.Num() ? A[0] : FString(), TEXT("console"), D);
				XpLog(FString::Printf(TEXT("[Transport] %s: %s"), bOk ? TEXT("ok") : TEXT("NO"), *D));
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdReset(TEXT("astra.xport.reset"), TEXT("TELETRASPORTO: everything in the beam is dropped, the people are put back, the shields come back"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& A, UWorld* W)
		{
			if (UAstraTransporterSubsystem* X = Xp(W))
			{
				X->Reset();
				XpLog(TEXT("[Transport] reset"));
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdRoom(TEXT("astra.xport.room"), TEXT("TELETRASPORTO: the Captain on foot in the Transporter Room, in front of the dais, facing it (for trying it out)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& A, UWorld* W)
		{
			UAstraTransporterSubsystem* X = Xp(W);
			APawn* P = W ? UGameplayStatics::GetPlayerPawn(W, 0) : nullptr;
			FVector Origin;
			float Yaw;
			if (!X || !P || !X->RoomFrame(Origin, Yaw))
			{
				XpLog(TEXT("[Transport] the room is not known (no plan) or there is no Captain"));
				return;
			}
			const FVector Stand = X->LocalToWorldCm(FVector(10.5, 8.6, 0.0));
			if (UAstraDeckStreaming* DS = W->GetSubsystem<UAstraDeckStreaming>())
			{
				DS->RequestAt(Stand, 60.f);
				DS->ForceReadyAt(Stand);
			}
			if (AASTRAPlayerController* PC = Cast<AASTRAPlayerController>(P->GetController()))
			{
				PC->StandUp();
			}
			P->SetActorLocation(Stand + FVector(0.0, 0.0, P->GetDefaultHalfHeight() + 2.0), false, nullptr, ETeleportType::TeleportPhysics);
			if (AController* C = P->GetController())
			{
				C->SetControlRotation(FRotator(-4.f, Yaw, 0.f));                      // local +X is the way to the dais
			}
			XpLog(FString::Printf(TEXT("[Transport] the Captain is in the Transporter Room (%.0f, %.0f, %.0f)"), Stand.X, Stand.Y, Stand.Z));
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdDump(TEXT("astra.xport.dump"), TEXT("TELETRASPORTO: the wall screen drawn into Saved/Transport/screen.png (needs a renderer)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& A, UWorld* W)
		{
			UAstraTransporterSubsystem* X = Xp(W);
			if (!X || !W)
			{
				return;
			}
			FVector C;
			float ScreenYaw;
			FVector2D Size;
			if (!X->WallScreenCm(C, ScreenYaw, Size))
			{
				XpLog(TEXT("[Transport] the room is not known"));
				return;
			}
			FActorSpawnParameters P;
			AAstraTransportConsole* Screen = W->SpawnActor<AAstraTransportConsole>(C, FRotator::ZeroRotator, P);
			if (!Screen)
			{
				return;
			}
			Screen->Owner = X;
			Screen->Place(C, ScreenYaw, Size);
			const FString Path = FPaths::ProjectSavedDir() / TEXT("Transport/screen.png");
			IFileManager::Get().MakeDirectory(*FPaths::GetPath(Path), true);
			XpLog(Screen->Dump(Path) ? FString::Printf(TEXT("[Transport] screen written to %s"), *Path) : FString(TEXT("[Transport] the screen could not be drawn (no renderer?)")));
			Screen->Destroy();
		}));
}
