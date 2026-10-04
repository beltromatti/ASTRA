// TELETRASPORTO — the life of a transport (docs/TELETRASPORTO.md §4, §5): an order checked against the rules, a lock that is built and can be lost, the cycle (warm-up, the
// dematerialization, the buffer, the rematerialization, the settling), the shield window Tactical holds for it, the arrivals, and the people and things that are away. The rules are
// AstraTransportRules.*, the world read into them and the words of an order turned into subjects and ends are AstraTransporterWorld.cpp, the card is AstraTransporterCard.cpp.

#include "AstraTransporterSubsystem.h"

#include "ASTRA.h"
#include "AstraBattleSubsystem.h"
#include "AstraBoardSubsystem.h"
#include "AstraCrewMember.h"
#include "AstraDamageModel.h"
#include "AstraDeckStreaming.h"
#include "AstraLifeBody.h"
#include "AstraLifeSubsystem.h"
#include "AstraShipPlan.h"
#include "AstraShipSubsystem.h"
#include "AstraStations.h"
#include "AstraTransportConsole.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/World.h"
#include "Kismet/GameplayStatics.h"
#include "Materials/MaterialInterface.h"
#include "Misc/App.h"

using namespace AstraXport;

namespace
{
	constexpr int32 XpMaxQueue = 4;                 // transports waiting behind the one in the beam, per system
	constexpr float XpHoldArrivalGameS = 240.f;     // someone beamed to a room stays where they were set down this long (the ship's clock) before they go back to their day
	constexpr float XpWindowSafetyS = 40.f;         // a shield window that nobody closed ends by itself this long after the cycle

	FString XpArgStr(const TSharedPtr<FJsonObject>& A, const TCHAR* Key)
	{
		FString S;
		if (A->TryGetStringField(Key, S))
		{
			return S.TrimStartAndEnd();
		}
		double N = 0.0;
		if (A->TryGetNumberField(Key, N))
		{
			return FString::SanitizeFloat(N);
		}
		return FString();
	}

	bool XpArgBool(const TSharedPtr<FJsonObject>& A, const TCHAR* Key)
	{
		bool B = false;
		if (A->TryGetBoolField(Key, B))
		{
			return B;
		}
		FString S;
		if (A->TryGetStringField(Key, S))
		{
			S = S.ToLower();
			return S == TEXT("true") || S == TEXT("yes") || S == TEXT("1");
		}
		return false;
	}

	/** A list: a JSON array of strings, or one string holding several separated by semicolons, commas or bars. */
	TArray<FString> XpArgList(const TSharedPtr<FJsonObject>& A, const TCHAR* Key)
	{
		TArray<FString> Out;
		const TArray<TSharedPtr<FJsonValue>>* Arr = nullptr;
		if (A->TryGetArrayField(Key, Arr) && Arr)
		{
			for (const TSharedPtr<FJsonValue>& V : *Arr)
			{
				FString S;
				if (V.IsValid() && V->TryGetString(S))
				{
					S.TrimStartAndEndInline();
					if (!S.IsEmpty())
					{
						Out.Add(S);
					}
				}
			}
			return Out;
		}
		FString S;
		if (A->TryGetStringField(Key, S))
		{
			S = S.Replace(TEXT(","), TEXT(";")).Replace(TEXT("|"), TEXT(";"));
			TArray<FString> Parts;
			S.ParseIntoArray(Parts, TEXT(";"));
			for (FString& P : Parts)
			{
				P.TrimStartAndEndInline();
				if (!P.IsEmpty())
				{
					Out.Add(P);
				}
			}
		}
		return Out;
	}

	FString XpPct(float F) { return FString::Printf(TEXT("%.0f%%"), F * 100.f); }
}

const TCHAR* AstraXportPhaseName(EAstraXportPhase P)
{
	switch (P)
	{
	case EAstraXportPhase::Queued: return TEXT("queued");
	case EAstraXportPhase::Locking: return TEXT("locking");
	case EAstraXportPhase::Locked: return TEXT("locked");
	case EAstraXportPhase::Warmup: return TEXT("warming up");
	case EAstraXportPhase::Demat: return TEXT("dematerializing");
	case EAstraXportPhase::Buffer: return TEXT("in the buffer");
	case EAstraXportPhase::Remat: return TEXT("rematerializing");
	case EAstraXportPhase::Settle: return TEXT("settling");
	case EAstraXportPhase::Done: return TEXT("done");
	case EAstraXportPhase::Failed: return TEXT("failed");
	case EAstraXportPhase::Aborted: return TEXT("aborted");
	default: return TEXT("lost");
	}
}

// ================================================================================================ the subsystem's life
bool UAstraTransporterSubsystem::ShouldCreateSubsystem(UObject* Outer) const
{
	const UWorld* World = Cast<UWorld>(Outer);
	return World && (World->WorldType == EWorldType::Game || World->WorldType == EWorldType::PIE);
}

void UAstraTransporterSubsystem::OnWorldBeginPlay(UWorld& InWorld)
{
	Super::OnWorldBeginPlay(InWorld);
	EnsureTuned();
	if (FApp::CanEverRender())
	{
		Fx = NewObject<UAstraTransportFx>(this);
		Fx->Init(&InWorld);
	}
}

void UAstraTransporterSubsystem::Deinitialize()
{
	if (bWindowHeld)
	{
		CloseWindow(nullptr);
	}
	LockCaptain(false);
	if (Fx)
	{
		Fx->Shutdown();
		Fx = nullptr;
	}
	if (Console)
	{
		Console->Destroy();
		Console = nullptr;
	}
	if (Chief)
	{
		Chief->Destroy();
		Chief = nullptr;
	}
	for (TObjectPtr<AActor>& A : Props)
	{
		if (A)
		{
			A->Destroy();
		}
	}
	Props.Reset();
	Super::Deinitialize();
}

bool UAstraTransporterSubsystem::EnsureTuned()
{
	if (bTuned)
	{
		return true;
	}
	bTuned = true;
	const bool bRead = T.Load();
	// a lock taken on the Captain's word is built and held at lower thresholds (the weak lock he accepted): the pattern is at risk, not the rules
	TForced = T;
	TForced.LoseQ = FMath::Min(T.LoseQ, 0.08f);
	TForced.HoldQ = FMath::Min(T.HoldQ, 0.10f);
	TForced.AcquireQ = FMath::Min(T.AcquireQ, 0.12f);
	UE_LOG(LogASTRA, Log, TEXT("[Transport] %s (%s)"), *T.Describe(), bRead ? TEXT("data/ship/aquila_transport.json") : TEXT("defaults"));
	return true;
}

bool UAstraTransporterSubsystem::EnsureRoom()
{
	if (bRoomKnown)
	{
		return true;
	}
	EnsureTuned();
	UAstraShipPlan* P = Plan();
	if (!P || !P->EnsureLoaded())
	{
		return false;
	}
	for (const FAstraPlanCompartment& C : P->GetCompartments())
	{
		if (C.bBuilt && C.Kind.Equals(T.RoomKind.ToString(), ESearchCase::IgnoreCase))
		{
			BuildPads(C);
			bRoomKnown = true;
			UE_LOG(LogASTRA, Log, TEXT("[Transport] the room is %s on deck %d (origin %.0f, %.0f, %.0f, yaw %.0f): %d pads, a cargo pad, %d emergency pads"), *C.Id, C.Deck,
			       RoomOriginCm.X, RoomOriginCm.Y, RoomOriginCm.Z, RoomYawDeg, T.Pads, T.EmergencyPads);
			break;
		}
	}
	return bRoomKnown;
}

void UAstraTransporterSubsystem::BuildPads(const FAstraPlanCompartment& Comp)
{
	RoomCompId = Comp.Id;
	RoomDeck = Comp.Deck;
	RoomBoxCm = Comp.Box;
	// the kit's frame: yaw 0 for a room on the starboard side (its corner at the box's minimum), 180 on the port side (its corner at the box's maximum)
	RoomYawDeg = Comp.Box.GetCenter().Y >= 0.0 ? 0.f : 180.f;
	RoomOriginCm = RoomYawDeg == 0.f ? FVector(Comp.Box.Min.X, Comp.Box.Min.Y, Comp.Box.Min.Z) : FVector(Comp.Box.Max.X, Comp.Box.Max.Y, Comp.Box.Min.Z);
	Pads.Reset();
	const int32 N = FMath::Max(1, T.Pads);
	for (int32 i = 0; i < N; ++i)
	{
		const float A = T.FirstDeg + 360.f * (float)i / (float)N;
		FAstraXportPad P;
		P.Id = FName(*FString::Printf(TEXT("pad%d"), i + 1));
		P.Index = i;
		const FVector Local(T.DaisCentre.X + T.RingM * FMath::Cos(FMath::DegreesToRadians(A)), T.DaisCentre.Y + T.RingM * FMath::Sin(FMath::DegreesToRadians(A)), T.PadZM);
		P.PosCm = LocalToWorldCm(Local);
		P.YawDeg = RoomYawDeg + A + 180.f;                  // they face the emitter at the heart of the dais
		P.RadiusCm = T.PadRM * 100.f;
		Pads.Add(P);
	}
	FAstraXportPad Cargo;
	Cargo.Id = TEXT("cargo");
	Cargo.bCargo = true;
	Cargo.PosCm = LocalToWorldCm(FVector(T.CargoCentre.X, T.CargoCentre.Y, T.CargoZM));
	Cargo.YawDeg = RoomYawDeg;
	Cargo.RadiusCm = T.CargoRM * 100.f;
	Pads.Add(Cargo);
	for (int32 k = 0; k < T.Emergency.Num(); ++k)
	{
		FAstraXportPad P;
		P.Id = T.Emergency[k].Id;
		P.Index = k;
		P.bEmergency = true;
		P.PosCm = T.Emergency[k].PosM * 100.0;
		P.YawDeg = 0.f;
		P.RadiusCm = T.Emergency[k].PadRM * 100.f;
		Pads.Add(P);
	}
}

// ================================================================================================ the ship's motion
void UAstraTransporterSubsystem::TickMotion(float Dt)
{
	const UAstraBattleSubsystem* B = Battle();
	if (!B || Dt < 1.0e-4f)
	{
		return;
	}
	const FVector V = B->PlayerVel();
	const FQuat Q = B->PlayerAtt();
	if (bHavePrev)
	{
		const float Acc = (float)(FVector::Dist(V, PrevVel) / Dt);
		const float Ang = FMath::RadiansToDegrees(PrevAtt.AngularDistance(Q)) / Dt;
		const float K = 1.f - FMath::Exp(-Dt / 0.7f);
		AccelSm += (FMath::Min(Acc, 60.f) - AccelSm) * K;       // (a jump of the ship, a respawn, is not a manoeuvre)
		TurnSm += (FMath::Min(Ang, 30.f) - TurnSm) * K;
	}
	PrevVel = V;
	PrevAtt = Q;
	bHavePrev = true;
}

// ================================================================================================ the tick
void UAstraTransporterSubsystem::Tick(float DeltaTime)
{
	const double T0 = FPlatformTime::Seconds();
	Super::Tick(DeltaTime);
	const float Dt = FMath::Clamp(DeltaTime, 0.f, 0.25f);
	Now = GetWorld() ? GetWorld()->GetTimeSeconds() : Now + Dt;
	if (!EnsureTuned())
	{
		return;
	}
	if (!bRoomKnown)
	{
		RoomT -= Dt;
		if (RoomT > 0.f)
		{
			return;
		}
		RoomT = 1.f;
		if (!EnsureRoom())
		{
			return;
		}
	}
	TickMotion(Dt);
	bool bLive = false;
	for (const FAstraXportJob& J : JobList)
	{
		bLive |= AstraXportLive(J.Phase);
	}
	EnvT -= Dt;
	if (bLive && EnvT <= 0.f)
	{
		EnvT = 0.15f;
		BuildEnv(EnvCache);
		bEnvFresh = true;
	}
	else if (!bLive)
	{
		bEnvFresh = false;
	}
	for (int32 i = 0; i < JobList.Num(); ++i)
	{
		TickJob(JobList[i], Dt);                                // (a job never adds or removes jobs while it ticks)
	}
	// the finished ones stay on the card a while, the last few for good
	{
		int32 Finished = 0;
		for (int32 i = JobList.Num() - 1; i >= 0; --i)
		{
			if (!AstraXportLive(JobList[i].Phase))
			{
				++Finished;
				if (Finished > 4 && Now - JobList[i].EndedAt > 120.0)
				{
					JobList.RemoveAt(i);
				}
			}
		}
	}
	if (bWindowHeld && Now > WindowEndsAt)
	{
		CloseWindow(nullptr);                                   // nobody closed it: the shields come back by themselves
	}
	PadT -= Dt;
	if (PadT <= 0.f)
	{
		PadT = 0.25f;
		SetPadLooks();
	}
	AwayT -= Dt;
	if (AwayT <= 0.f)
	{
		AwayT = 0.5f;
		SyncAway(0.5f);
	}
	ChiefT -= Dt;
	if (ChiefT <= 0.f)
	{
		ChiefT = 0.5f;
		SyncChief();
		SyncConsole();
	}
	if (Fx)
	{
		FVector Eye = FVector::ZeroVector;
		if (const APlayerCameraManager* Cam = UGameplayStatics::GetPlayerCameraManager(this, 0))
		{
			Eye = Cam->GetCameraLocation();
		}
		Fx->Tick(Dt, Eye);
	}
	TickMs = (FPlatformTime::Seconds() - T0) * 1000.0;
}

float UAstraTransporterSubsystem::ShieldLoadFactor() const
{
	return CycleOwner == INDEX_NONE ? 1.f : FMath::Max(T.ShieldFloor, 1.f - T.ShieldLoad);
}

// ================================================================================================ the commands
bool UAstraTransporterSubsystem::IsTransportCommand(const FString& Name)
{
	return Name.Equals(TEXT("transport"), ESearchCase::IgnoreCase) || Name.Equals(TEXT("transport_energize"), ESearchCase::IgnoreCase) || Name.Equals(TEXT("transport_abort"), ESearchCase::IgnoreCase);
}

bool UAstraTransporterSubsystem::ApplyCommand(const FString& Name, const TSharedPtr<FJsonObject>& Args, FString& OutDetail)
{
	const TSharedPtr<FJsonObject> A = Args.IsValid() ? Args : MakeShared<FJsonObject>();
	if (Name.Equals(TEXT("transport"), ESearchCase::IgnoreCase))
	{
		FAstraXportOrder O;
		O.Who = XpArgList(A, TEXT("who"));
		O.To = XpArgStr(A, TEXT("to"));
		O.From = XpArgStr(A, TEXT("from"));
		O.By = XpArgStr(A, TEXT("by"));
		O.bHold = XpArgStr(A, TEXT("energize")).Equals(TEXT("hold"), ESearchCase::IgnoreCase) || XpArgBool(A, TEXT("hold"));
		O.bWindow = XpArgBool(A, TEXT("shield_window")) || XpArgBool(A, TEXT("window"));
		O.Override = XpArgList(A, TEXT("override"));
		return Order(O, OutDetail);
	}
	const FString Tag = XpArgStr(A, TEXT("id")).IsEmpty() ? XpArgStr(A, TEXT("tag")) : XpArgStr(A, TEXT("id"));
	if (Name.Equals(TEXT("transport_energize"), ESearchCase::IgnoreCase))
	{
		return Energize(Tag, OutDetail);
	}
	if (Name.Equals(TEXT("transport_abort"), ESearchCase::IgnoreCase))
	{
		return Abort(Tag, XpArgStr(A, TEXT("why")), OutDetail);
	}
	OutDetail = FString::Printf(TEXT("the Transporter Room does not know %s"), *Name);
	return false;
}

FAstraXportJob* UAstraTransporterSubsystem::FindJob(const FString& Tag)
{
	return const_cast<FAstraXportJob*>(FindJobConst(Tag));
}

const FAstraXportJob* UAstraTransporterSubsystem::FindJobConst(const FString& Tag) const
{
	FString S = Tag.TrimStartAndEnd().ToUpper();
	S.RemoveFromStart(TEXT("X"));
	if (S.IsEmpty() || !S.IsNumeric())
	{
		return nullptr;
	}
	const int32 Serial = FCString::Atoi(*S);
	return JobList.FindByPredicate([Serial](const FAstraXportJob& J) { return J.Serial == Serial; });
}

FAstraXportJob* UAstraTransporterSubsystem::FindJobBySerial(int32 Serial)
{
	return JobList.FindByPredicate([Serial](const FAstraXportJob& J) { return J.Serial == Serial; });
}

bool UAstraTransporterSubsystem::IsHead(const FAstraXportJob& J) const
{
	for (const FAstraXportJob& O : JobList)
	{
		if (O.Serial == J.Serial)
		{
			return true;
		}
		if (AstraXportLive(O.Phase) && O.bEmergency == J.bEmergency)
		{
			return false;                                       // an earlier transport of the same system goes first
		}
	}
	return true;
}

FString UAstraTransporterSubsystem::Who(const FAstraXportJob& J) const
{
	if (J.Subs.Num() == 1)
	{
		return J.Subs[0].S.Label;
	}
	if (J.Subs.Num() == 2)
	{
		return J.Subs[0].S.Label + TEXT(" and ") + J.Subs[1].S.Label;
	}
	bool bCaptain = false;
	for (const FAstraXportSubject& S : J.Subs)
	{
		bCaptain |= S.S.Kind == ESubject::Captain;
	}
	return bCaptain ? FString::Printf(TEXT("the Captain and %d others"), J.Subs.Num() - 1) : FString::Printf(TEXT("%d subjects"), J.Subs.Num());
}

FString UAstraTransporterSubsystem::RefusalText(const FAstraXportJob& J, const FVerdict& V) const
{
	TArray<FString> Parts;
	for (const FBlocker& B : V.Blockers)
	{
		Parts.Add(B.Fix.IsEmpty() ? FString::Printf(TEXT("[%s] %s"), *B.Code.ToString(), *B.Why) : FString::Printf(TEXT("[%s] %s (to clear it: %s)"), *B.Code.ToString(), *B.Why, *B.Fix));
	}
	for (const FString& U : V.Unknown)
	{
		Parts.Add(FString::Printf(TEXT("[unknown] %s: a beam cannot be aimed through a shield the sensors cannot read"), *U));
	}
	return FString::Printf(TEXT("refused: %s"), *FString::Join(Parts, TEXT(" | ")));
}

bool UAstraTransporterSubsystem::Order(const FAstraXportOrder& O, FString& OutDetail, FString* OutTag)
{
	EnsureTuned();
	EnsureRoom();
	if (!bRoomKnown)
	{
		OutDetail = TEXT("refused: the Transporter Room is not on the ship's plan: the console is dark");
		return false;
	}
	FAstraXportJob J;
	FString Err;
	if (!MakeRequest(O, J, Err))
	{
		OutDetail = FString::Printf(TEXT("refused: %s"), *Err);
		return false;
	}
	int32 Waiting = 0;
	for (const FAstraXportJob& Other : JobList)
	{
		Waiting += AstraXportLive(Other.Phase) && Other.bEmergency == J.bEmergency ? 1 : 0;
	}
	if (Waiting > XpMaxQueue)
	{
		OutDetail = FString::Printf(TEXT("refused: the console holds %d transports already: let some finish"), Waiting);
		return false;
	}
	FEnv E;
	BuildEnv(E);
	FRequest R = J.Req;
	RefreshRequest(R, J);
	R.bShieldWindow = O.bWindow;
	const FVerdict V = Evaluate(T, E, R);
	if (!V.bOk || V.Unknown.Num() > 0 || !J.ArrivalWhy.IsEmpty())
	{
		OutDetail = V.bOk && V.Unknown.Num() == 0 ? FString(TEXT("refused: ")) : RefusalText(J, V) + (J.ArrivalWhy.IsEmpty() ? FString() : FString(TEXT(" | ")));
		if (!J.ArrivalWhy.IsEmpty())
		{
			OutDetail += FString::Printf(TEXT("[arrival] %s"), *J.ArrivalWhy);
		}
		return false;
	}
	J.Serial = NextSerial++;
	J.Tag = FString::Printf(TEXT("X%d"), J.Serial);
	J.Req = R;
	J.bWindow = V.bNeedsOwnWindow;
	J.bWindowNeeded = V.bNeedsOwnWindow;
	J.CycleS = V.CycleS;
	J.TargetQ = V.Quality;
	J.LockNeedS = V.LockS;
	J.RangeKm = V.RangeKm;
	J.EnergyMW = V.EnergyMW;
	J.OwnFace = V.OwnFace;
	J.TheirFace = V.TheirFace;
	J.Jam = V.Jam;
	J.Notes = V.Notes;
	J.BornAt = Now;
	J.Phase = EAstraXportPhase::Queued;
	J.Lock.Begin(V.LockS);
	for (const FAstraXportSubject& S : J.Subs)
	{
		J.bCaptain |= S.S.Kind == ESubject::Captain;
	}
	if (J.Req.To.bPad && J.Req.To.Pad != INDEX_NONE)
	{
		J.Pad = J.Req.To.bEmergencyPad ? T.Pads + 1 + J.Req.To.Pad : J.Req.To.Pad;
	}
	// the decks the destination is in start loading now, so that the Captain does not wait for them in the buffer
	if (UAstraDeckStreaming* DS = Streaming(); DS && J.Req.To.Aboard())
	{
		for (const FAstraXportSubject& S : J.Subs)
		{
			if (S.S.Kind == ESubject::Captain)
			{
				DS->RequestAt(S.ToCm, 45.f);
			}
		}
	}
	if (OutTag)
	{
		*OutTag = J.Tag;
	}
	TArray<FString> Told;
	Told.Add(FString::Printf(TEXT("%s accepted: %s from %s to %s"), *J.Tag, *Who(J), *J.FromText, *J.ToText));
	Told.Add(FString::Printf(TEXT("lock in about %.1f s at %s, then a %.1f s cycle, %.0f MW%s"), V.LockS, *XpPct(V.Quality), V.CycleS, V.EnergyMW,
	                         J.Req.From.Kind == EEndKind::Ship || J.Req.To.Kind == EEndKind::Ship || J.Req.From.Kind == EEndKind::Surface || J.Req.To.Kind == EEndKind::Surface
	                             ? *FString::Printf(TEXT(" over %.0f km"), V.RangeKm) : TEXT("")));
	if (V.bNeedsOwnWindow)
	{
		Told.Add(TEXT("our shields will be held down for the cycle (shield window)"));
	}
	if (J.bHold)
	{
		Told.Add(TEXT("the lock waits for your word to energize"));
	}
	for (const FString& N : V.Notes)
	{
		Told.Add(N);
	}
	OutDetail = FString::Join(Told, TEXT("; "));
	JobList.Add(J);
	FAstraXportJob& Added = JobList.Last();
	if (IsHead(Added))
	{
		StartLocking(Added);
	}
	else
	{
		OutDetail += TEXT("; queued behind the transport in the beam");
	}
	return true;
}

bool UAstraTransporterSubsystem::Energize(const FString& Tag, FString& OutDetail)
{
	FAstraXportJob* J = nullptr;
	if (Tag.TrimStartAndEnd().IsEmpty())
	{
		for (FAstraXportJob& Other : JobList)
		{
			if (AstraXportLive(Other.Phase) && Other.bHold && !AstraXportInBeam(Other.Phase))
			{
				J = &Other;
				break;
			}
		}
	}
	else
	{
		J = FindJob(Tag);
	}
	if (!J || !AstraXportLive(J->Phase))
	{
		OutDetail = Tag.IsEmpty() ? TEXT("no lock is waiting for the word") : FString::Printf(TEXT("no transport %s is waiting"), *Tag);
		return false;
	}
	if (AstraXportInBeam(J->Phase))
	{
		OutDetail = FString::Printf(TEXT("%s is in the beam already (%s)"), *J->Tag, AstraXportPhaseName(J->Phase));
		return false;
	}
	if (!J->bHold)
	{
		OutDetail = FString::Printf(TEXT("%s was not held: it goes by itself when the lock holds"), *J->Tag);
		return true;
	}
	J->bHold = false;
	OutDetail = J->Phase == EAstraXportPhase::Locked ? FString::Printf(TEXT("%s: energizing"), *J->Tag)
	                                                  : FString::Printf(TEXT("%s: the beam goes the moment the lock holds (%s of the lock built)"), *J->Tag, *XpPct(J->Lock.Progress));
	return true;
}

bool UAstraTransporterSubsystem::Abort(const FString& Tag, const FString& Why, FString& OutDetail)
{
	FAstraXportJob* J = nullptr;
	if (Tag.TrimStartAndEnd().IsEmpty())
	{
		for (FAstraXportJob& Other : JobList)
		{
			if (AstraXportLive(Other.Phase) && AstraXportInBeam(Other.Phase))
			{
				J = &Other;
				break;
			}
		}
		if (!J)
		{
			for (FAstraXportJob& Other : JobList)
			{
				if (AstraXportLive(Other.Phase))
				{
					J = &Other;
					break;
				}
			}
		}
	}
	else
	{
		J = FindJob(Tag);
	}
	if (!J || !AstraXportLive(J->Phase))
	{
		OutDetail = Tag.IsEmpty() ? TEXT("no transport is under way") : FString::Printf(TEXT("%s is not under way (finished or never ordered)"), *Tag);
		return false;
	}
	const FString Reason = Why.IsEmpty() ? FString() : FString::Printf(TEXT(" (%s)"), *Why);
	switch (J->Phase)
	{
	case EAstraXportPhase::Queued:
	case EAstraXportPhase::Locking:
	case EAstraXportPhase::Locked:
		Finish(*J, EAstraXportPhase::Aborted, FString::Printf(TEXT("cancelled before the cycle%s: nobody left their place"), *Reason));
		OutDetail = FString::Printf(TEXT("%s cancelled: nothing had left"), *J->Tag);
		return true;
	case EAstraXportPhase::Warmup:
	case EAstraXportPhase::Demat:
		if (Fx)
		{
			for (const FAstraXportSubject& S : J->Subs)
			{
				if (S.ColA)
				{
					Fx->ReverseColumn(S.ColA);
				}
			}
			if (J->bCaptain)
			{
				Fx->ReverseCaptainView();
			}
		}
		Finish(*J, EAstraXportPhase::Aborted, FString::Printf(TEXT("cancelled mid-beam%s: the patterns were recomposed where they stood"), *Reason));
		OutDetail = FString::Printf(TEXT("%s cancelled mid-beam: they are back where they stood"), *J->Tag);
		return true;
	case EAstraXportPhase::Buffer:
		J->bReturning = true;
		OutDetail = FString::Printf(TEXT("%s: the pattern is called back from the buffer to where it came from"), *J->Tag);
		News(*J, FString::Printf(TEXT("%s is being called back from the buffer to its origin%s"), *J->Tag, *Reason), true);
		return true;
	default:
		OutDetail = FString::Printf(TEXT("%s is through already (%s): nothing to abort"), *J->Tag, AstraXportPhaseName(J->Phase));
		return false;
	}
}

// ================================================================================================ one transport's life
void UAstraTransporterSubsystem::StartLocking(FAstraXportJob& J)
{
	J.Phase = EAstraXportPhase::Locking;
	J.T = 0.f;
	J.EvalT = 0.f;
	J.Lock.Begin(J.LockNeedS);
	SetPadLooks();
}

void UAstraTransporterSubsystem::TickJob(FAstraXportJob& J, float Dt)
{
	if (!AstraXportLive(J.Phase))
	{
		return;
	}
	J.T += Dt;
	if (J.Phase == EAstraXportPhase::Queued)
	{
		if (IsHead(J))
		{
			StartLocking(J);
		}
		return;
	}
	J.EvalT -= Dt;
	if (J.EvalT <= 0.f)
	{
		J.EvalT = 0.2f;
		EvaluateJob(J);
	}
	if (J.Phase == EAstraXportPhase::Locking || J.Phase == EAstraXportPhase::Locked)
	{
		TickLocking(J, Dt);
	}
	else if (AstraXportInBeam(J.Phase))
	{
		TickCycle(J, Dt);
	}
}

void UAstraTransporterSubsystem::EvaluateJob(FAstraXportJob& J)
{
	if (!bEnvFresh)
	{
		BuildEnv(EnvCache);
		bEnvFresh = true;
	}
	FRequest R = J.Req;
	RefreshRequest(R, J);
	R.bShieldWindow = J.bWindow || J.Req.bShieldWindow;
	const FVerdict V = Evaluate(T, EnvCache, R);
	// once the beam is on, the pattern is committed: a fire that breaks out in the room it will arrive in, or somebody stepping onto the pad, no longer change what the beam does
	static const TSet<FName> Physical = {FName(TEXT("shields_own")), FName(TEXT("shields_theirs")), FName(TEXT("range")), FName(TEXT("jam")), FName(TEXT("motion")), FName(TEXT("gate")),
	                                    FName(TEXT("room")), FName(TEXT("power")), FName(TEXT("target"))};
	const bool bCommitted = AstraXportInBeam(J.Phase);
	J.Blockers.Reset();
	J.BlockerCodes.Reset();
	bool bOk = true;
	for (const FBlocker& B : V.Blockers)
	{
		if (B.Code == FName(TEXT("quality")))
		{
			continue;                                           // the lock's own state machine takes a weak target (it builds slowly, degrades, is lost)
		}
		if (bCommitted && !Physical.Contains(B.Code))
		{
			continue;
		}
		bOk = false;
		J.Blockers.Add(B.Why);
		J.BlockerCodes.Add(B.Code.ToString());
	}
	for (const FString& U : V.Unknown)
	{
		bOk = false;
		J.Blockers.Add(U);
		J.BlockerCodes.Add(TEXT("unknown"));
	}
	// the window was asked for and it is not down: somebody put the shields up again on the face the beam leaves through
	if (V.bNeedsOwnWindow && J.Phase >= EAstraXportPhase::Warmup && J.Phase <= EAstraXportPhase::Buffer && !bWindowHeld)
	{
		bOk = false;
		J.Blockers.Add(TEXT("our shields are up again on the face the beam leaves through"));
		J.BlockerCodes.Add(TEXT("shields_own"));
	}
	J.bCondOk = bOk;
	J.TargetQ = V.Quality;
	if (J.Phase == EAstraXportPhase::Warmup || J.Phase == EAstraXportPhase::Demat)
	{
		J.MinQ = FMath::Min(J.MinQ, V.Quality);                 // what the conditions allowed at the worst, while the pattern was being taken: it decides how the arrival goes
	}
	J.Notes = V.Notes;
	J.RangeKm = V.RangeKm;
	J.Jam = V.Jam;
	J.OwnFace = V.OwnFace;
	J.TheirFace = V.TheirFace;
	J.bWindowNeeded = V.bNeedsOwnWindow;
	J.Req.From = R.From;
	J.Req.To = R.To;
	if (J.Phase < EAstraXportPhase::Warmup)
	{
		J.CycleS = V.CycleS;
		J.EnergyMW = V.EnergyMW;
	}
	J.CondWhy = FString::Join(J.Blockers, TEXT("; "));
}

void UAstraTransporterSubsystem::TickLocking(FAstraXportJob& J, float Dt)
{
	const FTuning& Tj = TuningFor(J);
	J.Lock.Tick(Tj, Dt, J.bCondOk ? J.TargetQ : 0.f, J.bCondOk ? 1.f : 0.f);
	J.Quality = J.Lock.Quality;
	if (J.Lock.State == FLock::EState::Lost)
	{
		Finish(J, EAstraXportPhase::Failed, FString::Printf(TEXT("the lock was lost before the cycle (%s): nobody left their place"), J.CondWhy.IsEmpty() ? TEXT("the conditions would not hold it") : *J.CondWhy));
		return;
	}
	if (J.T > T.LockMaxS + 10.f && !J.Lock.IsLocked())
	{
		Finish(J, EAstraXportPhase::Failed, FString::Printf(TEXT("no lock after %.0f s (%s of it built, quality %s): the beam gave up; nobody left their place"), J.T, *XpPct(J.Lock.Progress), *XpPct(J.Lock.Quality)));
		return;
	}
	if (!J.Lock.IsLocked())
	{
		return;
	}
	if (J.Phase == EAstraXportPhase::Locking)
	{
		J.Phase = EAstraXportPhase::Locked;
		J.T = 0.f;
		if (Fx)
		{
			Fx->PlaySound(TEXT("Lock"), EmitterCm(), 0.8f, 1.f);
		}
		if (J.bHold)
		{
			News(J, FString::Printf(TEXT("%s: lock held on %s, quality %s: waiting for the word to energize"), *J.Tag, *Who(J), *XpPct(J.TargetQ)), true);
		}
	}
	if (!J.bHold)
	{
		BeginCycle(J);
	}
}

void UAstraTransporterSubsystem::BeginCycle(FAstraXportJob& J)
{
	// the last look before the beam: everything, the destination's hazards and the pads included
	if (!bEnvFresh || EnvT < 0.05f)
	{
		BuildEnv(EnvCache);
		bEnvFresh = true;
	}
	if (J.bWindowNeeded)
	{
		OpenWindow(J);
		BuildEnv(EnvCache);
	}
	FRequest R = J.Req;
	RefreshRequest(R, J);
	R.bShieldWindow = J.bWindow;
	const FVerdict V = Evaluate(T, EnvCache, R);
	if (!V.bOk || V.Unknown.Num() > 0)
	{
		Finish(J, EAstraXportPhase::Failed, FString::Printf(TEXT("the beam could not be energized: %s: nobody left their place"), V.Unknown.Num() ? *V.Unknown[0] : *V.Summary()));
		return;
	}
	J.CycleS = V.CycleS;
	J.EnergyMW = V.EnergyMW;
	J.Phase = EAstraXportPhase::Warmup;
	J.T = 0.f;
	J.Cycle = 0.f;
	J.MinQ = V.Quality;
	J.BufferS = 0.f;
	J.EvalT = 0.f;
	if (J.bEmergency)
	{
		EmergencyOwner = J.Serial;
	}
	else
	{
		CycleOwner = J.Serial;
	}
	if (J.bCaptain)
	{
		CaptainBeamJob = J.Serial;
		LockCaptain(true);
	}
	if (UAstraShipSubsystem* S = Ship())
	{
		S->AddHeat(T.HeatPerCycle);
	}
	if (Fx)
	{
		Fx->PlaySound(TEXT("Energize"), EmitterCm(), 0.9f, 1.f);
		if (HumLoop == 0)
		{
			HumLoop = Fx->StartLoop(TEXT("Hum"), EmitterCm(), 0.6f);
		}
	}
	SetPadLooks();
}

void UAstraTransporterSubsystem::TickCycle(FAstraXportJob& J, float Dt)
{
	const float K = J.CycleS / FMath::Max(0.1f, T.CycleS);
	const float TWarm = T.WarmupS * K, TDemat = TWarm + T.DematS * K, TRemat = TDemat + T.RematS * K, TEnd = TRemat + T.SettleS * K;
	// the lock holds the beam until the pattern has left; after that the pattern is on its way and the lock has done its work
	if (J.Phase <= EAstraXportPhase::Buffer)
	{
		const FTuning& Tj = TuningFor(J);
		J.Lock.Tick(Tj, Dt, J.bCondOk ? J.TargetQ : 0.f, J.bCondOk ? 1.f : 0.f);
		J.Quality = J.Lock.Quality;
		if (J.Lock.State == FLock::EState::Lost)
		{
			OnLockLost(J);
			if (!AstraXportLive(J.Phase))
			{
				return;
			}
		}
	}
	switch (J.Phase)
	{
	case EAstraXportPhase::Warmup:
		J.Cycle += Dt;
		if (J.Cycle >= TWarm)
		{
			EnterDemat(J);
		}
		break;
	case EAstraXportPhase::Demat:
		J.Cycle += Dt;
		if (J.Cycle >= TDemat)
		{
			Depart(J);
		}
		break;
	case EAstraXportPhase::Buffer:
	{
		J.BufferS += Dt;
		if (J.BufferS >= T.BufferHoldS)
		{
			BufferExpired(J);
			break;
		}
		if (J.bReturning)
		{
			if (J.BufferS >= 0.5f)
			{
				EnterRemat(J);
			}
			break;
		}
		if (J.BufferS < J.Arrival.DelayS)
		{
			break;                                              // a delay: the pattern is held while the far lock steadies
		}
		if (!J.bCondOk || !J.Lock.IsLocked())
		{
			break;                                              // the lock is being built again (OnLockLost): the pattern waits
		}
		// a ship our marines are fighting aboard (ABBORDAGGI): where they are set down is asked again now, the fight has moved while the pattern was in the buffer; it waits there, within the buffer's
		// limit, while no room of hers is one the beam may set a person down in (never one the Mandate holds, never one with no air)
		if (J.bBoarded)
		{
			TArray<FVector> Spots;
			TArray<float> Yaws;
			FString Place, Why;
			bool bScene = false;
			const bool bFound = BoardedArrival(J.ToContact, J.Subs.Num(), J.bCaptain, Spots, Yaws, Place, Why, bScene);
			if (!bScene)
			{
				RecomposeAtOrigin(J, TEXT("the boarding ended"));
				Finish(J, EAstraXportPhase::Failed, FString::Printf(TEXT("the boarding of %s ended while the pattern was in the buffer: the console recomposed it on the pads it left"), *J.Req.To.Ship.Name));
				return;
			}
			if (!bFound)
			{
				if (!J.bNotedHold)
				{
					J.bNotedHold = true;
					News(J, FString::Printf(TEXT("%s: the pattern is held in the buffer: %s (the buffer holds %.0f s more)"), *J.Tag, *Why, FMath::Max(0.f, T.BufferHoldS - J.BufferS)), true, true);
				}
				return;
			}
			for (int32 i = 0; i < J.Subs.Num() && i < Spots.Num(); ++i)
			{
				J.Subs[i].ToCm = Spots[i];
				J.Subs[i].ToYaw = Yaws[i];
			}
			J.StreamWaitS -= Dt;
			if (J.StreamWaitS <= 0.f && J.bCaptain)
			{
				J.StreamWaitS = 1.f;
				if (UAstraBoardSubsystem* Bd = Board())
				{
					UAstraBoardSubsystem::FBeamAboard Where;
					for (int32 i = 0; i < Spots.Num(); ++i)
					{
						UAstraBoardSubsystem::FBeamSpot S;
						S.FeetWorld = Spots[i];
						S.Yaw = Yaws[i];
						Where.Spots.Add(S);
					}
					Bd->BeamPrepare(Where, true);                  // (his decks are solid where he will stand by the time he is there)
				}
			}
		}
		// the Captain's destination deck: it is loading, he waits in the buffer for it (six seconds at most, then it is made ready at once)
		UAstraDeckStreaming* DS = Streaming();
		if (J.bCaptain && DS && J.Req.To.Aboard())
		{
			for (const FAstraXportSubject& S : J.Subs)
			{
				if (S.S.Kind == ESubject::Captain && !DS->IsReadyAt(S.ToCm))
				{
					J.StreamWaitS += Dt;
					if (J.StreamWaitS < 6.f)
					{
						return;
					}
					DS->ForceReadyAt(S.ToCm);
				}
			}
		}
		EnterRemat(J);
		break;
	}
	case EAstraXportPhase::Remat:
		J.Cycle += Dt;
		if (Fx && Life())
		{
			for (FAstraXportSubject& S : J.Subs)
			{
				if (S.ColB && !S.bBound && S.Person != INDEX_NONE)
				{
					if (AAstraLifeBody* B = Life()->BodyOfPerson(S.Person))
					{
						Fx->BindSource(S.ColB, B);
						S.bBound = true;
					}
				}
			}
		}
		if (J.Cycle >= TRemat)
		{
			J.Phase = EAstraXportPhase::Settle;
			J.T = 0.f;
			if (J.bCaptain && Fx)
			{
				Fx->HoldCaptainView(0.f);
			}
		}
		break;
	case EAstraXportPhase::Settle:
		J.Cycle += Dt;
		if (J.Cycle >= TEnd)
		{
			Complete(J);
		}
		break;
	default:
		break;
	}
}

void UAstraTransporterSubsystem::OnLockLost(FAstraXportJob& J)
{
	const FString Why = J.CondWhy.IsEmpty() ? FString(TEXT("the conditions would not hold it")) : J.CondWhy;
	switch (J.Phase)
	{
	case EAstraXportPhase::Warmup:
	case EAstraXportPhase::Demat:
		if (Fx)
		{
			for (const FAstraXportSubject& S : J.Subs)
			{
				if (S.ColA)
				{
					Fx->ReverseColumn(S.ColA);
				}
			}
			if (J.bCaptain)
			{
				Fx->ReverseCaptainView();
			}
			Fx->PlaySound(TEXT("Fault"), EmitterCm(), 0.9f, 1.f);
		}
		Finish(J, EAstraXportPhase::Failed, FString::Printf(TEXT("the lock was lost mid-cycle (%s): the patterns were recomposed where they stood, nobody was lost"), *Why));
		break;
	case EAstraXportPhase::Buffer:
		// the pattern is in the buffer and the far lock is gone: the console builds it again while the buffer holds (ninety seconds at most)
		J.Lock.Begin(FMath::Max(0.5f, 0.6f * J.LockNeedS));
		if (!J.bNotedLost)
		{
			J.bNotedLost = true;
			if (Fx)
			{
				Fx->PlaySound(TEXT("Fault"), EmitterCm(), 0.9f, 1.f);
			}
			News(J, FString::Printf(TEXT("%s: the lock is lost with %s in the buffer (%s): the console is building it again; the buffer holds %.0f s, or the pattern can be called back to its origin"), *J.Tag,
			                        *Who(J), *Why, T.BufferHoldS - J.BufferS), true, true);
		}
		break;
	default:
		break;
	}
}

void UAstraTransporterSubsystem::EnterDemat(FAstraXportJob& J)
{
	J.Phase = EAstraXportPhase::Demat;
	J.T = 0.f;
	const float K = J.CycleS / FMath::Max(0.1f, T.CycleS);
	UAstraLifeSubsystem* L = Life();
	for (FAstraXportSubject& S : J.Subs)
	{
		if (!Fx)
		{
			break;
		}
		const bool bCap = S.S.Kind == ESubject::Captain;
		FVector Feet = S.FromCm;
		float Yaw = S.FromYaw;
		if (S.bAway)
		{
			// leaving the world below or another ship: seen only by the Captain, and only when he is down there
			const FAstraXportAway* A = AwayList.FindByPredicate([&S](const FAstraXportAway& W) { return W.Id == S.S.Id; });
			bool bDown = false;
			FVector F;
			float Y;
			bool bG, bSeat;
			bDown = CaptainFeet(F, Y, bG, bSeat) && bG;
			if (!A || !bDown || A->Where != TEXT("surface") || bCap)
			{
				continue;
			}
			Feet = A->GroundCm;
			Yaw = A->GroundYaw;
		}
		AActor* Body = !S.bAway && S.Person != INDEX_NONE && L ? static_cast<AActor*>(L->BodyOfPerson(S.Person)) : nullptr;
		S.ColA = Fx->BeginColumn(Feet, Yaw, false, T.DematS * K, Body, S.S.MassKg, bCap);
	}
	if (Fx)
	{
		Fx->PlaySound(TEXT("Demat"), J.Subs.Num() ? J.Subs[0].FromCm : EmitterCm(), 0.9f, 1.f);
		if (J.bCaptain)
		{
			Fx->BeginCaptainView(false, T.DematS * K);
		}
	}
	SetPadLooks();
}

void UAstraTransporterSubsystem::Depart(FAstraXportJob& J)
{
	UAstraLifeSubsystem* L = Life();
	for (FAstraXportSubject& S : J.Subs)
	{
		S.bDeparted = true;
		if (S.Person != INDEX_NONE && L && L->IsRunning())
		{
			L->Sim().SetTransit(S.Person, true);
		}
		if (Fx && S.ColA)
		{
			Fx->EndColumn(S.ColA);
		}
	}
	if (J.bCaptain)
	{
		if (Fx)
		{
			Fx->HoldCaptainView(1.f);
		}
		// the world below is made ready while the screen is white: the sky, the ground, the light
		if (J.Req.To.Kind == EEndKind::Surface && !bTestCaptain)
		{
			if (UAstraShipSubsystem* S = Ship())
			{
				S->SetPlanetside(true);
			}
		}
	}
	// leaving a ship our marines are fighting aboard: the people who were in her fight are out of it from now (the Captain's decks stay until his pattern is set down)
	if (UAstraBoardSubsystem* Bd = Board(); Bd && J.Req.From.Kind == EEndKind::Ship)
	{
		for (FAstraXportSubject& S : J.Subs)
		{
			if (S.bAway && S.S.Kind == ESubject::Captain)
			{
				Bd->SetCaptainInBeam(true);
			}
			else if (S.bAway && S.S.Kind == ESubject::Person)
			{
				Bd->BeamedOff(S.S.Roster, false, FVector::ZeroVector);
			}
		}
	}
	J.Arrival = RollArrival(TuningFor(J), J.MinQ, J.bForced, Rng);
	J.Phase = EAstraXportPhase::Buffer;
	J.T = 0.f;
	J.BufferS = 0.f;
	if (J.Arrival.Kind == EArrival::Scattered)
	{
		Scattered(J);
		return;
	}
	if (J.Arrival.Kind == EArrival::Delayed)
	{
		News(J, FString::Printf(TEXT("%s: %s %s held in the buffer for about %.0f s: the lock is unsteady (quality %s); the pattern is safe"), *J.Tag, *Who(J), J.Subs.Num() == 1 ? TEXT("is") : TEXT("are"), J.Arrival.DelayS, *XpPct(J.MinQ)), true);
	}
}

void UAstraTransporterSubsystem::Scattered(FAstraXportJob& J)
{
	// a lock taken on the Captain's word at a quality too poor to hold the pattern: it did not hold at the far end. People are pulled back out of the buffer to the pads they left (shaken,
	// the cycle's energy gone); a load of cargo does not come back
	bool bCargoLost = false;
	for (const FAstraXportSubject& S : J.Subs)
	{
		bCargoLost |= S.S.Kind == ESubject::Cargo;
	}
	if (Fx)
	{
		Fx->PlaySound(TEXT("Fault"), EmitterCm(), 1.f, 0.9f);
	}
	RecomposeAtOrigin(J, TEXT("the pattern did not hold at the far end"));
	for (FAstraXportSubject& S : J.Subs)
	{
		if (S.S.Kind == ESubject::Cargo)
		{
			DropAway(S.S.Id);
		}
	}
	Finish(J, bCargoLost ? EAstraXportPhase::Lost : EAstraXportPhase::Failed,
	       FString::Printf(TEXT("the pattern did not hold at the far end (a lock of %s taken on the Captain's word): %s"), *XpPct(J.MinQ),
	                       bCargoLost ? TEXT("people were recomposed on the pads they left, the cargo is lost") : TEXT("they were recomposed on the pads they left, shaken but whole")));
}

void UAstraTransporterSubsystem::BufferExpired(FAstraXportJob& J)
{
	RecomposeAtOrigin(J, TEXT("the buffer's limit"));
	bool bCargo = false;
	for (const FAstraXportSubject& S : J.Subs)
	{
		bCargo |= S.S.Kind == ESubject::Cargo;
	}
	if (Fx)
	{
		Fx->PlaySound(TEXT("Fault"), EmitterCm(), 1.f, 0.9f);
	}
	Finish(J, bCargo ? EAstraXportPhase::Lost : EAstraXportPhase::Failed,
	       FString::Printf(TEXT("the pattern waited %.0f s in the buffer without a lock and the console recomposed it on the pads it left (the limit is %.0f s)%s"), J.BufferS, T.BufferHoldS,
	                       bCargo ? TEXT("; the cargo is lost") : TEXT("")));
}

void UAstraTransporterSubsystem::RecomposeAtOrigin(FAstraXportJob& J, const FString& Why)
{
	UAstraLifeSubsystem* L = Life();
	for (FAstraXportSubject& S : J.Subs)
	{
		if (!S.bDeparted)
		{
			continue;
		}
		switch (S.S.Kind)
		{
		case ESubject::Person:
			if (S.Person != INDEX_NONE && L && L->IsRunning())
			{
				if (S.bAway)
				{
					const FAstraXportAway* A = AwayList.FindByPredicate([&S](const FAstraXportAway& W) { return W.Id == S.S.Id; });
					L->Sim().SetAway(S.Person, A ? A->WhereText : FString(TEXT("away from the ship")));
				}
				else
				{
					L->Sim().PlaceTransported(S.Person, S.FromCm, S.FromYaw, 30.f);
					L->ForceBody(S.Person, 20.f);
				}
			}
			break;
		case ESubject::Captain:
			if (!S.bAway && J.Req.To.Kind == EEndKind::Surface && !bTestCaptain)
			{
				if (UAstraShipSubsystem* Sh = Ship())
				{
					Sh->SetPlanetside(false);                    // the world was made ready for him and he never went: the ship's light is back
				}
			}
			break;
		default:
			break;
		}
		S.bDeparted = false;
		if (Fx)
		{
			if (S.ColA)
			{
				Fx->EndColumn(S.ColA);
			}
			if (S.S.Kind != ESubject::Cargo && !S.bAway)
			{
				S.ColB = Fx->BeginColumn(S.FromCm, S.FromYaw, true, T.RematS * 0.5f, nullptr, S.S.MassKg, S.S.Kind == ESubject::Captain);
			}
		}
	}
	if (Fx && J.bCaptain)
	{
		Fx->BeginCaptainView(true, T.RematS * 0.5f);
	}
	(void)Why;
}

void UAstraTransporterSubsystem::EnterRemat(FAstraXportJob& J)
{
	J.Phase = EAstraXportPhase::Remat;
	J.T = 0.f;
	const float K = J.CycleS / FMath::Max(0.1f, T.CycleS);
	const bool bBack = J.bReturning;
	const bool bAbroad = !bBack && (J.Req.To.Kind == EEndKind::Surface || J.Req.To.Kind == EEndKind::Ship);
	TArray<FVector> Taken;
	for (FAstraXportSubject& S : J.Subs)
	{
		FVector Spot = bBack ? S.FromCm : S.ToCm;
		float Yaw = bBack ? S.FromYaw : S.ToYaw;
		if (bBack && S.bAway)
		{
			if (const FAstraXportAway* Old = AwayList.FindByPredicate([&S](const FAstraXportAway& W) { return W.Id == S.S.Id; }); Old && Old->Where == TEXT("surface"))
			{
				Spot = Old->GroundCm;                           // called back to the world it was on: where it stood (on a ship, where the order found him: S.FromCm)
				Yaw = Old->GroundYaw;
			}
		}
		if (!bBack && J.Arrival.Kind == EArrival::Offset)
		{
			// set down off the mark: another place of the room, or a few metres off on the ground
			const float R = J.Arrival.OffsetM;
			if (J.Req.To.Aboard())
			{
				TArray<FVector> Avoid = Taken;
				Avoid.Add(S.ToCm);
				TArray<FVector> Spots;
				TArray<float> Yaws;
				if (PickSpots(J.ToComp, 1, Avoid, Spots, Yaws) && Spots.Num())
				{
					Spot = Spots[0];
					Yaw = Yaws[0];
				}
			}
			else if (J.Req.To.Kind == EEndKind::Surface)
			{
				const float A = Rng.FRandRange(0.f, 2.f * PI);
				Spot += FVector(FMath::Cos(A), FMath::Sin(A), 0.f) * R * 100.f;
			}
		}
		Taken.Add(Spot);
		S.ArriveCm = Spot;
		S.ArriveYaw = Yaw;
		if (bBack)
		{
			if (S.bAway)
			{
				SetSubjectAway(J, S, Spot, Yaw);               // called back from the buffer to where it was away: it is there again
			}
			else
			{
				PlaceSubject(J, S, Spot, Yaw);
			}
		}
		else if (bAbroad)
		{
			SetSubjectAway(J, S, Spot, Yaw);
		}
		else if (S.bAway)
		{
			BringBack(J, S, Spot, Yaw);
		}
		else
		{
			PlaceSubject(J, S, Spot, Yaw);
		}
		S.bArrived = true;
		S.bDeparted = false;
	}
	if (Fx)
	{
		FVector Eye;
		float Y;
		bool bG, bSeat;
		const bool bFoot = CaptainFeet(Eye, Y, bG, bSeat);
		for (FAstraXportSubject& S : J.Subs)
		{
			const bool bGroundSpot = bAbroad ? J.Req.To.Kind == EEndKind::Surface : (bBack && S.bAway && J.Req.From.Kind == EEndKind::Surface);
			// it is drawn when the Captain can see it: aboard when he is aboard, on the ground when he is down there
			if (!bFoot || (bGroundSpot != bG) || (bAbroad && J.Req.To.Kind == EEndKind::Ship))
			{
				continue;
			}
			AActor* Body = nullptr;
			if (S.Person != INDEX_NONE && Life() && !bAbroad)
			{
				Body = Life()->BodyOfPerson(S.Person);
			}
			S.bBound = Body != nullptr;
			S.ColB = Fx->BeginColumn(S.ArriveCm, S.ArriveYaw, true, T.RematS * K, Body, S.S.MassKg, S.S.Kind == ESubject::Captain);
		}
		Fx->PlaySound(TEXT("Remat"), J.Subs.Num() ? J.Subs[0].ArriveCm : EmitterCm(), 0.9f, 1.f);
		if (J.bCaptain)
		{
			Fx->BeginCaptainView(true, T.RematS * K);
		}
	}
	SetPadLooks();
}

void UAstraTransporterSubsystem::Complete(FAstraXportJob& J)
{
	TArray<FString> Told;
	if (J.bReturning)
	{
		Finish(J, EAstraXportPhase::Aborted, FString::Printf(TEXT("the pattern was called back from the buffer and set down on the pad it left (%s)"), *Who(J)));
		return;
	}
	Told.Add(FString::Printf(TEXT("%s %s at %s"), *Who(J), J.Subs.Num() == 1 ? TEXT("is") : TEXT("are"), *J.ToText));
	switch (J.Arrival.Kind)
	{
	case EArrival::Delayed:
		Told.Add(FString::Printf(TEXT("after %.0f s in the buffer"), J.BufferS));
		break;
	case EArrival::Offset:
		Told.Add(FString::Printf(TEXT("set down %.0f m off the mark"), J.Arrival.OffsetM));
		break;
	default:
		Told.Add(TEXT("a clean arrival"));
		break;
	}
	Told.Add(FString::Printf(TEXT("lock quality %s at worst, %.1f s cycle"), *XpPct(J.MinQ), J.CycleS));
	Finish(J, EAstraXportPhase::Done, FString::Join(Told, TEXT(", ")));
}

void UAstraTransporterSubsystem::Finish(FAstraXportJob& J, EAstraXportPhase End, const FString& Why)
{
	const bool bWasInBeam = AstraXportInBeam(J.Phase);
	J.Phase = End;
	J.Outcome = Why;
	J.EndedAt = Now;
	J.T = 0.f;
	if (CycleOwner == J.Serial)
	{
		CycleOwner = INDEX_NONE;
	}
	if (EmergencyOwner == J.Serial)
	{
		EmergencyOwner = INDEX_NONE;
	}
	if (J.bCaptain || J.bBoarded)
	{
		if (UAstraBoardSubsystem* Bd = Board())
		{
			Bd->BeamOver();
		}
	}
	if (CaptainBeamJob == J.Serial)
	{
		CaptainBeamJob = INDEX_NONE;
		LockCaptain(false);
		if (Fx)
		{
			if (End == EAstraXportPhase::Done)
			{
				Fx->EndCaptainView();
			}
			else
			{
				Fx->HoldCaptainView(0.f);
				Fx->EndCaptainView();
			}
		}
	}
	if (J.bWindow)
	{
		CloseWindow(&J);
	}
	if (Fx)
	{
		for (FAstraXportSubject& S : J.Subs)
		{
			if (S.ColA && End != EAstraXportPhase::Done)
			{
				Fx->EndColumn(S.ColA);
			}
		}
		if (CycleOwner == INDEX_NONE && EmergencyOwner == INDEX_NONE && HumLoop)
		{
			Fx->StopLoop(HumLoop, 0.6f);
			HumLoop = 0;
		}
	}
	const TCHAR* Verb = End == EAstraXportPhase::Done ? TEXT("done") : (End == EAstraXportPhase::Aborted ? TEXT("aborted") : (End == EAstraXportPhase::Lost ? TEXT("LOST") : TEXT("failed")));
	LastOutcome = FString::Printf(TEXT("%s %s: %s"), *J.Tag, Verb, *Why);
	UE_LOG(LogASTRA, Log, TEXT("[Transport] %s"), *LastOutcome);
	if (End != EAstraXportPhase::Aborted || bWasInBeam)
	{
		News(J, LastOutcome, End != EAstraXportPhase::Done || J.By.Len() > 0 || J.bCaptain, End == EAstraXportPhase::Failed || End == EAstraXportPhase::Lost);
	}
	else
	{
		News(J, LastOutcome, false);
	}
	SetPadLooks();
}

// ================================================================================================ our shields
void UAstraTransporterSubsystem::OpenWindow(FAstraXportJob& J)
{
	UAstraShipSubsystem* S = Ship();
	if (!S)
	{
		return;
	}
	J.bWindow = true;
	WindowEndsAt = Now + J.CycleS + XpWindowSafetyS;
	if (bWindowHeld)
	{
		WindowOwner = J.Serial;
		return;
	}
	if (!S->AreShieldsUp())
	{
		return;                                                 // already down (a power loss, somebody else's order): nothing to hold, nothing to give back
	}
	if (UAstraStationsSubsystem* St = Stations())
	{
		WindowMode = St->ModeOf(TEXT("tactical"), TEXT("shields"));
		WindowParams = St->ParamsOf(TEXT("tactical"), TEXT("shields"));
		const TSharedPtr<FJsonObject> A = MakeShared<FJsonObject>();
		A->SetStringField(TEXT("station"), TEXT("tactical"));
		A->SetStringField(TEXT("aspect"), TEXT("shields"));
		A->SetStringField(TEXT("mode"), TEXT("shields_off"));
		A->SetStringField(TEXT("until"), FString::Printf(TEXT("time:%.0f"), J.CycleS + XpWindowSafetyS));
		A->SetStringField(TEXT("note"), TEXT("transporter shield window"));
		FString Detail;
		if (St->SetMode(A, TEXT("officer"), Detail))
		{
			bWindowHeld = true;
			bWindowDirect = false;
			WindowOwner = J.Serial;
			return;
		}
	}
	// Tactical is not there (a test world, a console without the station): the ship's own command
	const TSharedPtr<FJsonObject> A = MakeShared<FJsonObject>();
	A->SetStringField(TEXT("mode"), TEXT("off"));
	FString Detail;
	if (S->ApplyCommand(TEXT("set_shields"), A, Detail))
	{
		bWindowHeld = true;
		bWindowDirect = true;
		WindowOwner = J.Serial;
		WindowMode = TEXT("balanced");
	}
}

void UAstraTransporterSubsystem::CloseWindow(const FAstraXportJob* J)
{
	if (!bWindowHeld)
	{
		return;
	}
	for (const FAstraXportJob& Other : JobList)
	{
		if ((!J || Other.Serial != J->Serial) && AstraXportLive(Other.Phase) && Other.bWindow && Other.Phase >= EAstraXportPhase::Warmup)
		{
			WindowOwner = Other.Serial;                         // the next transport in the beam still needs them down
			return;
		}
	}
	bWindowHeld = false;
	WindowOwner = INDEX_NONE;
	if (UAstraStationsSubsystem* St = Stations(); St && !bWindowDirect)
	{
		const TSharedPtr<FJsonObject> A = MakeShared<FJsonObject>();
		A->SetStringField(TEXT("station"), TEXT("tactical"));
		A->SetStringField(TEXT("aspect"), TEXT("shields"));
		A->SetStringField(TEXT("mode"), WindowMode.IsEmpty() || WindowMode == TEXT("shields_off") ? TEXT("face_threat") : *WindowMode);
		if (WindowParams.IsValid())
		{
			A->SetObjectField(TEXT("params"), WindowParams);
		}
		A->SetStringField(TEXT("until"), TEXT("order"));
		A->SetStringField(TEXT("note"), TEXT("the transporter cycle is over"));
		FString Detail;
		St->SetMode(A, TEXT("officer"), Detail);
	}
	else if (UAstraShipSubsystem* S = Ship())
	{
		const TSharedPtr<FJsonObject> A = MakeShared<FJsonObject>();
		A->SetStringField(TEXT("mode"), WindowMode.IsEmpty() ? TEXT("balanced") : *WindowMode);
		FString Detail;
		S->ApplyCommand(TEXT("set_shields"), A, Detail);
	}
	bWindowDirect = false;
	WindowParams.Reset();
}

// ================================================================================================ the people and the things
void UAstraTransporterSubsystem::PlaceSubject(FAstraXportJob& J, FAstraXportSubject& S, const FVector& Spot, float Yaw)
{
	(void)J;
	switch (S.S.Kind)
	{
	case ESubject::Captain:
		if (!bTestCaptain)
		{
			if (UAstraShipSubsystem* Sh = Ship(); Sh && Sh->IsPlanetside())
			{
				Sh->SetPlanetside(false);                        // back aboard: the ship's light and her sky
				Sh->SetCaptainPlanetside(FString());
			}
		}
		PlaceCaptain(Spot, Yaw, false);
		LockCaptain(true);                                      // (standing up from the chair gave the controls back)
		if (J.Req.From.Kind == EEndKind::Ship)
		{
			if (UAstraBoardSubsystem* Bd = Board())
			{
				Bd->BeamedOff(INDEX_NONE, true, Spot);          // (off the decks of the ship our marines were fighting aboard: the fight goes on without him)
			}
		}
		break;
	case ESubject::Person:
		if (UAstraLifeSubsystem* L = Life(); L && L->IsRunning() && S.Person != INDEX_NONE)
		{
			L->Sim().PlaceTransported(S.Person, Spot, Yaw, XpHoldArrivalGameS);
			L->ForceBody(S.Person, 25.f);
		}
		break;
	case ESubject::Cargo:
		MakeProp(S, Spot, Yaw);
		break;
	}
}

void UAstraTransporterSubsystem::SetSubjectAway(FAstraXportJob& J, FAstraXportSubject& S, const FVector& Spot, float Yaw)
{
	const bool bSurface = J.Req.To.Kind == EEndKind::Surface || (J.bReturning && S.AwayWhere == TEXT("surface"));
	FAstraXportAway A;
	A.Id = S.S.Id;
	A.Label = S.S.Label;
	A.Person = S.Person;
	A.Where = bSurface ? FString(TEXT("surface")) : (S.bAway ? S.AwayWhere : J.ToContact);
	A.WhereText = AwayWhereText(J);
	if (J.bReturning && S.bAway)
	{
		if (const FAstraXportAway* Old = AwayList.FindByPredicate([&S](const FAstraXportAway& W) { return W.Id == S.S.Id; }))
		{
			A = *Old;                                           // called back to where it was: the same place, the same since
		}
	}
	else
	{
		A.Since = Now;
	}
	A.Dept = S.Dept;
	A.bFemale = S.bFemale;
	A.bCargo = S.S.Kind == ESubject::Cargo;
	A.MassKg = S.S.MassKg;
	if (const UAstraShipSubsystem* Sh = Ship(); Sh && A.System.IsEmpty())
	{
		A.System = Sh->GetSystemName();
	}
	if (!(J.bReturning && S.bAway))
	{
		A.GroundCm = Spot;
		A.GroundYaw = Yaw;
	}
	DropAway(S.S.Id);
	switch (S.S.Kind)
	{
	case ESubject::Captain:
		if (bSurface)
		{
			PlaceCaptain(Spot, Yaw, true);
			LockCaptain(true);
			if (UAstraShipSubsystem* Sh = Ship())
			{
				Sh->SetCaptainPlanetside(FString::Printf(TEXT("on foot at %s, beamed down from the Aquila's Transporter Room; the XO has the conn"), *J.ToText));
			}
		}
		else if (J.Req.To.Kind == EEndKind::Ship || (J.bReturning && S.bAway))
		{
			// the decks of the ship our marines are fighting aboard: he stands beside them (the boarding host makes the fight his)
			PlaceCaptain(Spot, Yaw, true);
			LockCaptain(true);
			if (UAstraBoardSubsystem* Bd = Board())
			{
				UAstraBoardSubsystem::FBeamSpot At;
				At.FeetWorld = Spot;
				At.Yaw = Yaw;
				Bd->BeamedAboard(INDEX_NONE, true, At);
			}
		}
		break;
	case ESubject::Person:
		if (UAstraLifeSubsystem* L = Life(); L && L->IsRunning() && S.Person != INDEX_NONE)
		{
			L->Sim().SetAway(S.Person, A.WhereText);
		}
		if (J.bBoarded && S.S.Roster != INDEX_NONE)
		{
			if (UAstraBoardSubsystem* Bd = Board())
			{
				UAstraBoardSubsystem::FBeamSpot At;
				At.FeetWorld = Spot;
				At.Yaw = Yaw;
				Bd->BeamedAboard(S.S.Roster, false, At);
			}
		}
		break;
	case ESubject::Cargo:
		if (bSurface)
		{
			MakeProp(S, Spot, Yaw);
			A.Body = S.Prop;
		}
		break;
	}
	AwayList.Add(A);
}

void UAstraTransporterSubsystem::BringBack(FAstraXportJob& J, FAstraXportSubject& S, const FVector& Spot, float Yaw)
{
	DropAway(S.S.Id);
	PlaceSubject(J, S, Spot, Yaw);
}

void UAstraTransporterSubsystem::DropAway(const FString& Id)
{
	for (int32 i = AwayList.Num() - 1; i >= 0; --i)
	{
		if (AwayList[i].Id == Id)
		{
			if (AActor* B = AwayList[i].Body.Get())
			{
				B->Destroy();
			}
			AwayList.RemoveAt(i);
		}
	}
}

bool UAstraTransporterSubsystem::AwayHere(const FString& Id) const
{
	return AwayList.ContainsByPredicate([&Id](const FAstraXportAway& A) { return A.Id == Id; });
}

FString UAstraTransporterSubsystem::AwayWhereText(const FAstraXportJob& J) const
{
	if (J.Req.To.Kind == EEndKind::Surface)
	{
		return FString::Printf(TEXT("on the surface of %s, at %s"), *J.Req.To.World, *J.ToText.Replace(*(J.Req.To.World + TEXT(" · ")), TEXT("")));
	}
	if (J.Req.To.Kind == EEndKind::Ship)
	{
		return FString::Printf(TEXT("aboard %s"), *J.Req.To.Ship.Name);
	}
	return J.ToText;
}

void UAstraTransporterSubsystem::MakeProp(FAstraXportSubject& S, const FVector& Spot, float Yaw)
{
	if (!Fx || !GetWorld())
	{
		return;                                                 // a headless world: cargo is only a mass on a list
	}
	UStaticMesh* Cube = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cube.Cube"));
	if (!Cube)
	{
		return;
	}
	FActorSpawnParameters P;
	P.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	// a crate in proportion to its mass: 1 m3 holds about 400 kg of supplies
	const float Vol = FMath::Clamp(S.S.MassKg / 400.f, 0.15f, 4.f);
	const float Side = FMath::Pow(Vol, 1.f / 3.f);
	const FVector Scale(Side * 1.2f, Side * 0.8f, Side * 0.7f);
	AStaticMeshActor* Crate = GetWorld()->SpawnActor<AStaticMeshActor>(FVector(Spot.X, Spot.Y, Spot.Z + 50.f * Scale.Z), FRotator(0.f, Yaw, 0.f), P);
	if (!Crate)
	{
		return;
	}
	Crate->SetMobility(EComponentMobility::Movable);
	if (UStaticMeshComponent* C = Crate->GetStaticMeshComponent())
	{
		C->SetStaticMesh(Cube);
		if (UMaterialInterface* M = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/ASTRA/Materials/Instances/MI_SHIP_CrateOlive.MI_SHIP_CrateOlive")))
		{
			C->SetMaterial(0, M);
		}
		C->SetCastShadow(true);
		C->SetCollisionProfileName(TEXT("BlockAll"));
	}
	Crate->SetActorScale3D(Scale);
	Props.Add(Crate);
	S.Prop = Crate;
}

// ================================================================================================ pads, the Chief, the wall screen, the away list
void UAstraTransporterSubsystem::SetPadLooks()
{
	if (!bRoomKnown)
	{
		return;
	}
	for (FAstraXportPad& P : Pads)
	{
		P.Look = EAstraPadLook::Idle;
	}
	auto PadNear = [this](const FVector& Cm) -> int32
	{
		for (int32 i = 0; i < Pads.Num(); ++i)
		{
			if (FVector::DistSquared2D(Cm, Pads[i].PosCm) < FMath::Square(Pads[i].RadiusCm + 40.f) && FMath::Abs(Cm.Z - Pads[i].PosCm.Z) < 90.f)
			{
				return i;
			}
		}
		return INDEX_NONE;
	};
	for (const FAstraXportJob& J : JobList)
	{
		EAstraPadLook Look = EAstraPadLook::Idle;
		if (AstraXportLive(J.Phase))
		{
			Look = AstraXportInBeam(J.Phase) ? EAstraPadLook::Energizing : (J.Phase == EAstraXportPhase::Locked ? EAstraPadLook::Locked : EAstraPadLook::Locking);
		}
		else if ((J.Phase == EAstraXportPhase::Failed || J.Phase == EAstraXportPhase::Lost) && Now - J.EndedAt < 2.5)
		{
			Look = EAstraPadLook::Fault;
		}
		if (Look == EAstraPadLook::Idle)
		{
			continue;
		}
		for (const FAstraXportSubject& S : J.Subs)
		{
			for (const FVector& Cm : {S.FromCm, S.ToCm})
			{
				const int32 I = PadNear(Cm);
				if (I != INDEX_NONE && (uint8)Look > (uint8)Pads[I].Look)
				{
					Pads[I].Look = Look;
				}
			}
		}
		if (J.Pad != INDEX_NONE && Pads.IsValidIndex(J.Pad) && (uint8)Look > (uint8)Pads[J.Pad].Look)
		{
			Pads[J.Pad].Look = Look;
		}
	}
	for (int32 i = 0; i < Pads.Num(); ++i)
	{
		FString Who;
		FAstraXportPad& P = Pads[i];
		P.Occupant = PadOccupiedBy(P, Who) ? Who : FString();
		if (P.Look == EAstraPadLook::Idle && !P.Occupant.IsEmpty())
		{
			P.Look = EAstraPadLook::Selected;
		}
		if (Fx)
		{
			Fx->SetPadLook(i, P.PosCm, P.RadiusCm, P.Look);
		}
	}
	if (Fx)
	{
		const bool bBeam = CycleOwner != INDEX_NONE || EmergencyOwner != INDEX_NONE;
		bool bLocking = false;
		for (const FAstraXportJob& J : JobList)
		{
			bLocking |= J.Phase == EAstraXportPhase::Locking || J.Phase == EAstraXportPhase::Locked;
		}
		Fx->SetEmitter(EmitterCm(), bBeam ? 1.f : (bLocking ? 0.55f : 0.12f));
	}
}

void UAstraTransporterSubsystem::SyncAway(float Dt)
{
	(void)Dt;
	// the Aquila went through a Gate with people still away: they are where they were, a system behind, and no beam reaches them
	if (const UAstraShipSubsystem* Sh = Ship())
	{
		const FString Here = Sh->GetSystemName();
		for (FAstraXportAway& A : AwayList)
		{
			if (!A.bStranded && !A.System.IsEmpty() && !A.System.Equals(Here, ESearchCase::IgnoreCase) && A.Id != TEXT("captain"))
			{
				A.bStranded = true;
				A.WhereText = FString::Printf(TEXT("left behind in the %s system (%s)"), *A.System, *A.WhereText);
				if (UAstraLifeSubsystem* L = Life(); L && L->IsRunning() && A.Person != INDEX_NONE)
				{
					L->Sim().SetAway(A.Person, A.WhereText);
				}
				Say(FString::Printf(TEXT("%s %s: the Aquila has left the %s system and no beam reaches that far"), *A.Label, *A.WhereText, *A.System), true);
			}
		}
	}
	// the Captain who was beamed down and is back aboard by another way (the console's test command, the shuttle) is not away any more
	if (AwayHere(TEXT("captain")))
	{
		FVector F;
		float Y;
		bool bG, bS;
		const bool bFoot = CaptainFeet(F, Y, bG, bS);
		if ((bFoot && !bG) && CaptainBeamJob == INDEX_NONE)
		{
			DropAway(TEXT("captain"));
		}
	}
}

void UAstraTransporterSubsystem::SyncChief()
{
	if (!Fx || !bRoomKnown || !GetWorld())
	{
		return;                                                 // (a headless world: nobody to draw)
	}
	FVector Feet;
	float Yaw;
	bool bG, bS;
	const bool bHere = CaptainFeet(Feet, Yaw, bG, bS) && !bG;
	const FVector Stand = ChiefStandCm();
	const UAstraDeckStreaming* DS = Streaming();
	const bool bReady = !DS || DS->IsReadyAt(Stand + FVector(0.0, 0.0, 100.0));
	const double D = bHere ? FVector::Dist(Feet, Stand) : 1.0e12;
	const bool bWant = bHere && bReady && D < (Chief ? 8000.0 : 4500.0);
	if (bWant && !Chief)
	{
		FVector At = Stand;
		float FaceYaw = ChiefYaw();
		// the plan may give her a post of her own (a station whose `station` is xfer_chief): she stands there, on her feet
		if (const UAstraLifeSubsystem* L = Life(); L && L->IsRunning())
		{
			const FAstraLifeMap& Map = L->Sim().GetMap();
			if (const int32* Ci = Map.CompByName.Find(FName(*RoomCompId)))
			{
				for (const int32 P : Map.Comps[*Ci].Places)
				{
					const FAstraLifePlace& Pl = Map.Places[P];
					if (Pl.External == FName(TEXT("xfer_chief")) && (Pl.Kind == EAstraPlaceKind::Stand || Pl.Kind == EAstraPlaceKind::Work))
					{
						At = Pl.Pos;
						FaceYaw = Pl.Yaw;
						break;
					}
				}
			}
		}
		FActorSpawnParameters P;
		P.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
		const FTransform Xf(FRotator(0.f, FaceYaw - 90.f, 0.f), At);                // (the mannequin faces its own +Y)
		if (AAstraCrewMember* C = GetWorld()->SpawnActorDeferred<AAstraCrewMember>(AAstraCrewMember::StaticClass(), Xf, nullptr, nullptr, ESpawnActorCollisionHandlingMethod::AlwaysSpawn))
		{
			C->StationId = TEXT("xfer_chief");
			C->DisplayName = TEXT("Chief Petty Officer Rhea Ostrander");
			C->Posture = EAstraCrewPosture::Standing;
			C->bFemaleBody = true;
			C->FinishSpawning(Xf);
			C->SetUniformDept(TEXT("science"));
			Chief = C;
		}
	}
	else if (!bWant && Chief)
	{
		Chief->Destroy();
		Chief = nullptr;
	}
}

void UAstraTransporterSubsystem::SyncConsole()
{
	if (!Fx || !bRoomKnown || !GetWorld())
	{
		return;
	}
	FVector Feet;
	float Yaw;
	bool bG, bS;
	const bool bHere = CaptainFeet(Feet, Yaw, bG, bS) && !bG;
	FVector C;
	float ScreenYaw;
	FVector2D Size;
	if (!WallScreenCm(C, ScreenYaw, Size))
	{
		return;
	}
	const UAstraDeckStreaming* DS = Streaming();
	const bool bReady = !DS || DS->IsReadyAt(C);
	const bool bWant = bHere && bReady && FVector::Dist(Feet, C) < 3500.0;
	if (bWant && !Console)
	{
		FActorSpawnParameters P;
		P.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
		Console = GetWorld()->SpawnActor<AAstraTransportConsole>(C, FRotator::ZeroRotator, P);
		if (Console)
		{
			Console->Owner = this;
			Console->Place(C, ScreenYaw, Size);
		}
	}
	if (Console)
	{
		Console->SetShown(bWant);
	}
}
