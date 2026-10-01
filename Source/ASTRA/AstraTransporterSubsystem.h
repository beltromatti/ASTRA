// ASTRA — TELETRASPORTO in the world (docs/TELETRASPORTO.md): the Aquila's Transporter Room, its six pads and the Medbay's two, the orders that come from the bridge
// and from the Chief, the locks, the cycles, the buffer, the arrivals and the people who are away. The rules are AstraTransportRules.*; this subsystem reads the
// world into them (the battle's shields and jamming, the ship's motion and power, the damage model's room, the plan, the planet), keeps every transport's life and
// carries it out: it moves the Captain, hands VITA's people from room to room and off the ship, asks Tactical to hold the shields down for a cycle, and tells the
// minds what is happening (`ship_state.transporter`, `transporter:` events). What is seen and heard is UAstraTransportFx.
//
// The crew's side is mind/astra_mind/transporter.py: the Chief is a person who reads the card (SnapshotJson) and carries the orders out with the commands below.
//
// Files: AstraTransporterSubsystem.cpp (the life of a transport), AstraTransporterWorld.cpp (the world read into the rules, the words of an order resolved),
// AstraTransporterCard.cpp (the card, the console's view, the console commands).

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "Dom/JsonObject.h"
#include "AstraTransportRules.h"
#include "AstraTransportFx.h"
#include "AstraTransporterSubsystem.generated.h"

class UAstraShipSubsystem;
class UAstraBattleSubsystem;
class UAstraLifeSubsystem;
class UAstraShipPlan;
class UAstraDeckStreaming;
class UAstraStationsSubsystem;
class AAstraCrewMember;
class AAstraTransportConsole;
class AStaticMeshActor;
struct FAstraPlanCompartment;

/** A pad of the Transporter Room (or the Medbay's): where a subject stands. */
struct FAstraXportPad
{
	FName Id;                                  // pad1..pad6, cargo, med1, med2
	int32 Index = 0;                           // 0..5 for the main pads, 0..1 for the emergency ones
	bool bEmergency = false, bCargo = false;
	FVector PosCm = FVector::ZeroVector;       // feet on the pad
	float YawDeg = 0.f;
	float RadiusCm = 62.f;
	FString Occupant;                          // who stands there now, in words ("" nobody)
	EAstraPadLook Look = EAstraPadLook::Idle;
};

/** One subject of a transport, resolved: who or what, where it stands now, where it will stand. */
struct FAstraXportSubject
{
	AstraXport::FSubject S;
	int32 Person = INDEX_NONE;                 // VITA's person (people); INDEX_NONE for the Captain and cargo
	bool bAway = false;                        // starts off the ship
	FString AwayWhere;                         // "surface" or a contact id: where it is away
	FVector FromCm = FVector::ZeroVector;      // its feet now (aboard)
	float FromYaw = 0.f;
	FString FromComp;                          // plan compartment id (aboard)
	FVector ToCm = FVector::ZeroVector;        // where it will stand (aboard or on the ground)
	float ToYaw = 0.f;
	FString Dept;                              // the uniform's department
	bool bFemale = false;
	int32 ColA = 0, ColB = 0;                  // the effect's columns: the dematerialization, the rematerialization
	bool bDeparted = false, bArrived = false;
	TWeakObjectPtr<AActor> Prop;               // cargo: the crate that stands where it was set down
	bool bBound = false;                       // the rematerializing column has its body
	FVector ArriveCm = FVector::ZeroVector;    // where it was really set down (an offset arrival differs from ToCm)
	float ArriveYaw = 0.f;
};

enum class EAstraXportPhase : uint8 { Queued, Locking, Locked, Warmup, Demat, Buffer, Remat, Settle, Done, Failed, Aborted, Lost };

/** The phase in words (the card, the log). */
ASTRA_API const TCHAR* AstraXportPhaseName(EAstraXportPhase P);
/** Still on its way: from the order to the end of the cycle. */
inline bool AstraXportLive(EAstraXportPhase P) { return (uint8)P < (uint8)EAstraXportPhase::Done; }
/** The beam is on: from the warm-up to the settling. */
inline bool AstraXportInBeam(EAstraXportPhase P) { return P >= EAstraXportPhase::Warmup && P <= EAstraXportPhase::Settle; }

/** One transport: from the order to the arrival. */
struct FAstraXportJob
{
	int32 Serial = 0;
	FString Tag;                               // X3
	EAstraXportPhase Phase = EAstraXportPhase::Queued;
	AstraXport::FRequest Req;                  // what the rules read
	TArray<FAstraXportSubject> Subs;
	FString FromText, ToText, ToContact;       // in words; a ship's contact id
	FString FromComp, ToComp;                  // the plan's compartment ids of an end aboard
	FString By;
	float EvalT = 0.f;                         // seconds until the conditions are read again
	bool bCondOk = true;                       // what they said: the beam can be made now
	float TargetQ = 1.f;                       // and the quality they allow
	float LockNeedS = 3.f;                     // what the lock needed when it was ordered
	FString CondWhy;
	TArray<FString> Notes;                     // what degrades the lock now
	TArray<FString> Blockers;                  // what forbids the beam now (one plain sentence each)
	TArray<FString> BlockerCodes;
	bool bHold = false;                        // wait for the word to energize
	bool bEmergency = false;                   // the Medbay's pads do it
	bool bForced = false;                      // a weak lock taken on the Captain's word
	bool bCaptain = false;                     // the Captain is among them
	AstraXport::FLock Lock;
	float T = 0.f;                             // seconds in the phase
	float Cycle = 0.f, CycleS = 8.f;           // seconds into the cycle, its planned length
	AstraXport::FArrival Arrival;
	float BufferS = 0.f;                       // seconds the pattern has waited in the buffer
	float MinQ = 1.f;                          // the lowest the lock's quality fell to during the cycle
	float Quality = 0.f;                       // the lock's quality now
	float StreamWaitS = 0.f;                   // the buffer waits for the destination deck to load (the Captain)
	bool bWindow = false;                      // our shields are held down for this cycle (Tactical's shield window)
	bool bReturning = false;                   // aborted in the buffer: the pattern goes back to where it came from
	bool bNotedLost = false;
	FString Outcome;                           // how it ended, in words
	double BornAt = 0.0, EndedAt = 0.0;
	float RangeKm = 0.f;
	float EnergyMW = 40.f;
	int32 OwnFace = -1, TheirFace = -1;        // the hull faces the beam crosses (for the screen)
	float Jam = 0.f;
	bool bWindowNeeded = false;                // the verdict says our shields must be down for the cycle
	int32 Pad = INDEX_NONE;                    // the pad index the transport's destination is (for the screen)
};

/** Someone or something that is off the ship: sent by the transporter, to be brought back. */
struct FAstraXportAway
{
	FString Id;                                // npc17, captain, cargo3
	FString Label;
	int32 Person = INDEX_NONE;
	FString Where;                             // "surface" or a contact id
	FString WhereText;                         // "New Ravenna · Port Aurelius Field", "ASN Vigilant"
	double Since = 0.0;
	FString Dept;
	bool bFemale = false;
	bool bCargo = false;
	float MassKg = 90.f;
	FVector GroundCm = FVector::ZeroVector;    // on a world: where they stand
	float GroundYaw = 0.f;
	TWeakObjectPtr<AActor> Body;               // the figure or the crate standing on the ground while the Captain is there
};

/** The order as the minds give it (the `transport` command): strings that the world resolves. */
struct FAstraXportOrder
{
	TArray<FString> Who;
	FString To, From;
	bool bHold = false, bWindow = false;
	TArray<FString> Override;                  // hazard, weak_lock
	FString By;
};

/** What the console says to "could I send ... there now": one line of the card's `options` and of the wall screen. */
struct FAstraXportOption
{
	FString To;                                // as an order says it ("surface", "T-02", "med1")
	FString Label;                             // in words
	bool bOk = false;
	bool bUnknown = false;                     // the sensors cannot tell (no firm track on her shields)
	float RangeKm = 0.f;
	float LockS = 0.f;
	float QualityPct = 0.f;
	int32 OwnFace = -1, TheirFace = -1;
	TArray<FString> Why;
	FString Fix;
	TArray<FString> Notes;
};

/** The console as the wall screen draws it: a copy of the numbers, taken a few times a second. */
struct FAstraXportView
{
	bool bReady = false;
	FString RoomState;                         // ready | reduced | offline | wrecked
	float RoomPower = 1.f, RoomWreck = 0.f;
	float ReachKm = 0.f, CycleS = 8.f, EnergyMW = 40.f;
	float Accel = 0.f, Turn = 0.f;
	bool bShieldsUp = true;
	float Faces[AstraXport::NumFaces] = {1, 1, 1, 1, 1, 1};
	float Jam = 0.f;
	float GateKm = -1.f;
	bool bGateLane = false;
	int32 OwnFace = -1, TheirFace = -1;        // the faces the current transport's beam crosses
	TArray<FAstraXportOption> Options;
	int32 Away = 0;
	bool bPadBusy[9] = {};                     // six pads, cargo, two emergency
	FString PadWho[9];
	FString Last;
};

UCLASS()
class ASTRA_API UAstraTransporterSubsystem : public UTickableWorldSubsystem
{
	GENERATED_BODY()

public:
	virtual void OnWorldBeginPlay(UWorld& InWorld) override;
	virtual void Deinitialize() override;
	virtual void Tick(float DeltaTime) override;
	virtual TStatId GetStatId() const override { RETURN_QUICK_DECLARE_CYCLE_STAT(UAstraTransporterSubsystem, STATGROUP_Tickables); }
	virtual bool ShouldCreateSubsystem(UObject* Outer) const override;

	// ------------------------------------------------------------------------------------------------ the orders
	/** The commands of the minds that are the transporter's: transport, transport_energize, transport_abort. */
	static bool IsTransportCommand(const FString& Name);
	bool ApplyCommand(const FString& Name, const TSharedPtr<FJsonObject>& Args, FString& OutDetail);
	/** The same in C++: a transport ordered (queued behind the one in the beam), the lock's word, an abort. */
	bool Order(const FAstraXportOrder& O, FString& OutDetail, FString* OutTag = nullptr);
	bool Energize(const FString& Tag, FString& OutDetail);
	bool Abort(const FString& Tag, const FString& Why, FString& OutDetail);

	// ------------------------------------------------------------------------------------------------ what the minds and the screens read
	/** The card: the console as the Chief reads it (ship_state.transporter). */
	TSharedRef<FJsonObject> SnapshotJson() const;
	/** The console as the wall screen draws it. */
	void GetView(FAstraXportView& Out) const;
	/** The room is known (the plan has it, the tuning is read) and the world is up. */
	bool IsReady() const { return bRoomKnown; }
	const AstraXport::FTuning& Tuning() const { return T; }
	const TArray<FAstraXportJob>& Jobs() const { return JobList; }
	const TArray<FAstraXportPad>& GetPads() const { return Pads; }
	const TArray<FAstraXportAway>& GetAway() const { return AwayList; }
	/** The Captain carried by a transport now (the screen is dissolving, he cannot move). */
	bool IsCaptainInBeam() const { return CaptainBeamJob != INDEX_NONE; }
	/** A job by its tag ("X3", "x3" or "3"), or null. */
	const FAstraXportJob* FindJobConst(const FString& Tag) const;

	/** The load on the ship's power while a cycle runs: a share of the shields allocation (the cycle's 40 MW come out of the shields in a battle). 1 outside a cycle. */
	float ShieldLoadFactor() const;

	// ------------------------------------------------------------------------------------------------ for the world around it
	/** The room's place in the world (cm): where the dais, the chief's stand and the wall screen are; false before the plan is read. */
	bool RoomFrame(FVector& OutOriginCm, float& OutYawDeg) const;
	FVector LocalToWorldCm(const FVector& LocalM) const;
	FVector ChiefStandCm() const;
	float ChiefYaw() const;
	bool WallScreenCm(FVector& OutCentreCm, float& OutYawDeg, FVector2D& OutSizeCm) const;
	FVector EmitterCm() const;
	/** The tests' Captain (no pawn): where his feet are, and whether he is down on the world. The same Captain is given to the ship, VITA and the deck streaming. */
	void SetTestCaptain(bool bOn, const FVector& FeetCm);
	bool HasTestCaptain() const { return bTestCaptain; }
	FVector TestCaptainCm() const { return TestFeetCm; }
	bool TestCaptainOnGround() const { return bTestPlanetside; }
	/** Everything that is in the beam or waiting is dropped and the people are put back: a new campaign, the tests. */
	void Reset();

	/** What the console would answer to a plain request right now (the chief's pre-flight; the card's `options` are made of these). OutWhy: why it could not even be read. */
	AstraXport::FVerdict Preflight(const FAstraXportOrder& O, FString& OutWhy) const;

	FString InfoText() const;
	/** The fx, for the console and the tests (null where nothing is drawn: a headless world). */
	UAstraTransportFx* GetFx() const { return Fx; }
	/** One tick's cost, for stat and the tests. */
	double LastTickMs() const { return TickMs; }

private:
	AstraXport::FTuning T;
	AstraXport::FTuning TForced;               // the same with the lock thresholds of a lock taken on the Captain's word
	bool bTuned = false;
	bool bRoomKnown = false;
	FString RoomCompId;
	FVector RoomOriginCm = FVector::ZeroVector;
	float RoomYawDeg = 0.f;
	int32 RoomDeck = 5;
	FBox RoomBoxCm = FBox(ForceInit);
	TArray<FAstraXportPad> Pads;               // the six, the cargo pad, the two emergency ones
	TArray<FAstraXportJob> JobList;
	TArray<FAstraXportAway> AwayList;
	int32 NextSerial = 1;
	int32 CaptainBeamJob = INDEX_NONE;         // serial of the job that carries the Captain
	int32 CycleOwner = INDEX_NONE;             // serial of the job in the cycle (one at a time per system: main, emergency)
	int32 EmergencyOwner = INDEX_NONE;
	double Now = 0.0;
	float EnvT = 0.f, PadT = 0.f, AwayT = 0.f, RoomT = 0.f, ChiefT = 0.f;
	double TickMs = 0.0;
	FRandomStream Rng = FRandomStream(2491);
	AstraXport::FEnv EnvCache;                 // the world as the rules read it, a few times a second while something is in the beam
	bool bEnvFresh = false;
	FString LastOutcome;

	// the world's own motion, read each tick: what makes a lock hard
	FVector PrevVel = FVector::ZeroVector;
	FQuat PrevAtt = FQuat::Identity;
	bool bHavePrev = false;
	float AccelSm = 0.f, TurnSm = 0.f;

	// the tests' Captain
	bool bTestCaptain = false;
	bool bTestPlanetside = false;
	FVector TestFeetCm = FVector::ZeroVector;

	// the shield window: what Tactical was doing before, to put back
	bool bWindowHeld = false;
	FString WindowMode;
	TSharedPtr<FJsonObject> WindowParams;
	double WindowEndsAt = 0.0;
	int32 WindowOwner = INDEX_NONE;
	bool bWindowDirect = false;                // Tactical was not there: the ship's own command did it

	UPROPERTY() TObjectPtr<UAstraTransportFx> Fx;
	UPROPERTY() TObjectPtr<AAstraTransportConsole> Console;
	UPROPERTY() TObjectPtr<AAstraCrewMember> Chief;
	UPROPERTY() TArray<TObjectPtr<AActor>> Props;
	int32 HumLoop = 0;                         // the room's hum while a cycle runs (fx loop id)
	bool bInputLocked = false;                 // the Captain's controls are held while he is in the beam (the controller counts: lock and unlock are balanced)

	// ------------------------------------------------------------------------------------------------ the room, the world
	bool EnsureTuned();
	bool EnsureRoom();
	void BuildPads(const FAstraPlanCompartment& Comp);
	UAstraShipSubsystem* Ship() const;
	UAstraBattleSubsystem* Battle() const;
	UAstraLifeSubsystem* Life() const;
	UAstraShipPlan* Plan() const;
	UAstraDeckStreaming* Streaming() const;
	UAstraStationsSubsystem* Stations() const;
	void TickMotion(float Dt);
	/** The world as the rules want it: what the sensors and the datalink tell of every hull, the damage model's rooms, the ship's motion. */
	void BuildEnv(AstraXport::FEnv& Out) const;
	void FillRoom(AstraXport::FRoomState& Out, const FString& CompId, const TCHAR* Name) const;
	bool FillShip(AstraXport::FHull& Out, const FString& ContactId) const;
	AstraXport::FRoomState RoomOf(const FString& CompId, const FString& Name) const;

	// ------------------------------------------------------------------------------------------------ the captain, the people
	bool CaptainFeet(FVector& OutFeetCm, float& OutYaw, bool& bOnGround, bool& bSeated) const;
	bool CaptainOnFoot() const;
	void PushTestCaptain() const;
	void PlaceCaptain(const FVector& FeetCm, float YawDeg, bool bOnGround);
	void LockCaptain(bool bOn);
	FString PadLabelAt(const FVector& FeetCm, int32* OutPad = nullptr) const;
	bool PadOccupiedBy(const FAstraXportPad& P, FString& OutWho) const;

	// ------------------------------------------------------------------------------------------------ resolving the words
	bool ResolveSubjects(const FAstraXportOrder& O, TArray<FAstraXportSubject>& Out, FString& OutErr) const;
	bool ResolveEnd(const FString& Text, bool bDestination, const TArray<FAstraXportSubject>& Subs, AstraXport::FEnd& Out, FString& OutComp, FString& OutErr) const;
	int32 FindPerson(const FString& Words, TArray<FString>* OutAlternatives = nullptr) const;
	bool PickSpots(const FString& CompId, int32 N, const TArray<FVector>& Avoid, TArray<FVector>& OutSpots, TArray<float>& OutYaws) const;
	int32 FreeMainPad(const TArray<int32>& Reserved) const;
	bool MakeRequest(const FAstraXportOrder& O, FAstraXportJob& OutJob, FString& OutErr) const;
	void RefreshRequest(AstraXport::FRequest& R, const FAstraXportJob& J) const;
	FString DescribeEnd(const AstraXport::FEnd& E, const FString& CompId) const;
	/** The options the card and the screen list: every kind of place the console could be asked for, with the verdict for each. */
	void BuildOptions(TArray<FAstraXportOption>& Out, int32 Max) const;

	// ------------------------------------------------------------------------------------------------ the jobs
	FAstraXportJob* FindJob(const FString& Tag);
	FAstraXportJob* FindJobBySerial(int32 Serial);
	bool IsHead(const FAstraXportJob& J) const;
	const AstraXport::FTuning& TuningFor(const FAstraXportJob& J) const { return J.bForced ? TForced : T; }
	void StartLocking(FAstraXportJob& J);
	void TickJob(FAstraXportJob& J, float Dt);
	void EvaluateJob(FAstraXportJob& J);
	void TickLocking(FAstraXportJob& J, float Dt);
	void TickCycle(FAstraXportJob& J, float Dt);
	void BeginCycle(FAstraXportJob& J);
	void EnterDemat(FAstraXportJob& J);
	void Depart(FAstraXportJob& J);
	void EnterRemat(FAstraXportJob& J);
	void Complete(FAstraXportJob& J);
	void OnLockLost(FAstraXportJob& J);
	void Scattered(FAstraXportJob& J);
	void BufferExpired(FAstraXportJob& J);
	/** Everyone who left is set down at the spots they started from (the pattern comes back to its pad). */
	void RecomposeAtOrigin(FAstraXportJob& J, const FString& Why);
	void Finish(FAstraXportJob& J, EAstraXportPhase End, const FString& Why);
	void OpenWindow(FAstraXportJob& J);
	void CloseWindow(const FAstraXportJob* J);
	void News(const FAstraXportJob& J, const FString& Text, bool bReport) const;
	void Say(const FString& Text, bool bReport) const;
	FString Who(const FAstraXportJob& J) const;
	FString RefusalText(const FAstraXportJob& J, const AstraXport::FVerdict& V) const;
	void SetPadLooks();
	void SyncAway(float Dt);
	void SyncChief();
	void SyncConsole();
	void SetSubjectAway(FAstraXportJob& J, FAstraXportSubject& S, const FVector& Spot, float Yaw);
	void BringBack(FAstraXportJob& J, FAstraXportSubject& S, const FVector& Spot, float Yaw);
	void PlaceSubject(FAstraXportJob& J, FAstraXportSubject& S, const FVector& Spot, float Yaw);
	void MakeProp(FAstraXportSubject& S, const FVector& Spot, float Yaw);
	void DropAway(const FString& Id);
	FString AwayWhereText(const FAstraXportJob& J) const;
	bool AwayHere(const FString& Id) const;

	friend struct FAstraXportTestAccess;
};
