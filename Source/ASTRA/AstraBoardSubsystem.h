// ASTRA — ABBORDAGGI: the fight inside the Aquila in the game (docs/ABBORDAGGI.md).
//
// The squad simulation (AstraBoardSim.*) is plain code over the ship's plan; this subsystem is its host. It reads the plan on a worker (as the damage model and VITA do),
// owns the simulation, starts a boarding (the Mandate's boarders cut in at a breach; the marines of VITA's roster take their rifles) and ends it, and turns what the
// simulation says into the game: the soldiers' bodies near the Captain (AstraCombatant.*), their rounds and wounds (AstraCombatFx.*), the pressure bulkheads that close
// and are cut through, the casualties of the roster (the wounded to the Medbay, the fallen with their names), the Captain's own wound and his fate (the damage model's
// chain: the XO's command, the abandon ship, the inquiry), the reports of the bridge and the marines' net, and the mind's words to the marines (orders to the squads).
//
// The Captain is a man of the fight: the simulation sees where he stands, and a round that reaches him is his wound. A round of his that strikes a soldier's body is
// the soldier's wound (UAstraFpsComponent calls PlayerHit).

#pragma once

#include "CoreMinimal.h"
#include "Async/Future.h"
#include "AstraBoardCraft.h"
#include "AstraBoardMap.h"
#include "AstraBoardPlans.h"
#include "AstraBoardSim.h"
#include "AstraDamageMap.h"
#include "Dom/JsonObject.h"
#include "Subsystems/WorldSubsystem.h"
#include "AstraBoardSubsystem.generated.h"

class AAstraArmoryRack;
class AAstraBoardBreach;
class AAstraCombatant;
class APawn;
class UAstraBattleSubsystem;
class UAstraCombatFx;
class UAstraFpsComponent;
class UAstraLifeSubsystem;
class UAstraShipSubsystem;

UCLASS()
class ASTRA_API UAstraBoardSubsystem : public UTickableWorldSubsystem
{
	GENERATED_BODY()

public:
	virtual void OnWorldBeginPlay(UWorld& InWorld) override;
	virtual void Deinitialize() override;
	virtual void Tick(float DeltaTime) override;
	virtual TStatId GetStatId() const override { RETURN_QUICK_DECLARE_CYCLE_STAT(UAstraBoardSubsystem, STATGROUP_Tickables); }
	virtual bool ShouldCreateSubsystem(UObject* Outer) const override;

	/** The plan is read and the tactical map built (a few hundred milliseconds on a worker after the world begins). */
	bool IsReady() const { return Phase != EPhase::Loading && Phase != EPhase::Failed; }
	/** A boarding is on on the Aquila's own decks (from the alarm to the end, the cleaning up after it not counted): the Captain's fight. */
	bool IsActive() const { return Phase == EPhase::Active && Mode == EMode::Observed; }
	/** Any boarding is on: on the Aquila's decks, or on another ship (her marines aboard a hulk, a consort taken by the Mandate), where the Captain is not. */
	bool IsFightOn() const { return Phase == EPhase::Active; }
	const FAstraBoardSim& Sim() const { return Fight; }
	/** The Aquila's own map (the soldiers' map of her plan). */
	const FAstraBoardMap* BoardMap() const { return AqMap.Get(); }

	/** What a boarding is made of. */
	struct FSpec
	{
		FString Breach;                // the plan's id of the compartment the boarders cut into; empty: the default place on Deck 7
		int32 Skiffs = 1;              // boarding craft that have docked: ten men each
		int32 Boarders = 0;            // or exactly this many (0: Skiffs * 10)
		FString Source;                // "the Mandate raider Cocytus": what the bridge says it came from
		bool bLockdown = true;         // the section bulkheads of the breach's deck close at once
		float WarnS = 45.f;            // the marines are called when the craft is seen; the boarders cut in this long after
	};
	/** Starts a boarding: the alarm, the lockdown, the marines called, the boarders on their way. False (and why) when the plan is not read or one is on. */
	bool StartBoarding(const FSpec& Spec, FString& OutDetail);
	/** Ends it (the test console, the end of a fight): the bulkheads open, the marines go back to their duty, the bodies are cleared away in a while. */
	void EndBoarding(const TCHAR* Why);

	// ------------------------------------------------------------------------------------------------ boarding by assault craft (AstraBoardAssault.cpp, docs/brief/ABBORDAGGI-2.md)
	/** What an order to board is made of when boats fly it: who flies from where at whom (the ships are named as the commands name them: a contact id such as T-30, a name, "aquila"). */
	struct FAssaultSpec
	{
		FString Source;                // the carrier whose boats go (empty: the Aquila's own for an assault on another ship; the Mandate's nearest carrier for an assault on the Aquila)
		FString Target;                // the ship that is boarded (empty: the Aquila)
		FString Face;                  // port | starboard | dorsal | ventral | bow | stern | any: the side of the target the boats dock on (empty: the side nearest the carrier)
		FString Objective;             // bridge | engineering | captain | armory | medbay | brig | comms | hangar, or a compartment's id (empty: engineering for the Aquila, the commander's suite for another ship)
		FString Breach;                // the plan's id of a hatch (or a compartment on the skin) for the first boat (empty: the side's best)
		int32 Craft = 0;               // boats (0: as many as the carrier has free, at most two)
		int32 Boarders = 0;            // men in all (0: the boats' full loads)
		bool bLockdown = true;         // (the Aquila boarded) the pressure bulkheads round the hatches close
		bool bCaptain = false;         // the Captain rides in the first boat (his marines')
		FString By;                    // who ordered it ("Admiral Solm", "the Captain"), for the log
	};
	/** Boats leave a carrier for a target and the fight is theirs: the boarders cut in where the boats latch; whoever survives goes home. False, and why, when it cannot be (no boat free, a shield
	 *  that holds the hatch, no hatch on that face, a boarding already on). The reply is the facts. */
	bool StartAssault(const FAssaultSpec& Spec, FString& OutDetail);
	/** The assault under way, as the minds read it (empty object when none): ships, boats and where each is, men, hatches. */
	TSharedRef<FJsonObject> AssaultJson() const;
	/** What each side may order, from what is true (the carriers' free boats and, for each enemy ship, what a boat would meet: shield on the face, point defence, fighters): the war minds' context.
	 *  SideIdx: 0 ASTRA, 1 the Mandate. */
	TSharedRef<FJsonObject> BoardingOptionsJson(int32 SideIdx) const;
	/** True while an assault is flying, fighting or coming home (a new order is refused). */
	bool IsAssaultOn() const { return Assault.bOn; }
	/** The Aquila's own boats and the marines fit to go in them (ship_state.boarding_boats: the crew's tool `board_ship` exists where this does). Empty when the battle has no Aquila yet. */
	TSharedRef<FJsonObject> BoatsJson() const;

	// ------------------------------------------------------------------------------------------------ the Captain
	/** A round of the Captain's struck a soldier (Damage: what it does after the range, Head: it hit the head). The soldier's wound; false when it did not count (a marine of
	 *  ours, or nobody is fighting). From: where it was fired (the way he falls). */
	bool PlayerHit(AAstraCombatant* Who, float Damage, bool bHead, const FVector& From);
	/** The Captain fired a round: the boarders near him hear it (where from, roughly). */
	void NoteCaptainShot() { if (Phase == EPhase::Active) { Fight.CaptainFired(); } }
	/** The Captain's strength, 0..1 (1 whole), whether he is down, and how long ago and from where he was last hit (the weapon's screen reads these). */
	float CaptainStrength() const { return FMath::Clamp(CapHp / 100.f, 0.f, 1.f); }
	bool IsCaptainDown() const { return bCapDown; }
	double SinceCaptainHurt() const;
	FVector LastHurtFrom() const { return CapHurtFrom; }
	float LastHurtAmount() const { return CapHurtAmount; }
	/** The nearest able enemy that sees the Captain, distance (cm), or a negative number. */
	float NearestThreatCm() const { return ThreatCm; }

	// ------------------------------------------------------------------------------------------------ the minds
	/** The commands of the game's one entrance (UAstraShipSubsystem::ApplyCommand forwards "boarding", "marine_order" and "lockdown" here). */
	bool HandleCommand(const FString& Name, const TSharedPtr<FJsonObject>& Args, FString& OutDetail);
	/** What the minds read of the fight (ship_state.boarding): empty object when none is on. */
	TSharedRef<FJsonObject> Snapshot() const;
	/** One line for the console: the fight in numbers. */
	FString InfoText() const;
	/** The fight's own report to the marines' net: the squads, where, how many, in contact; the bulkheads. (The mind's context for the marines.) */
	TSharedRef<FJsonObject> MarinesPicture() const;

	/** Draws the simulation in the world (units, squads' places, the planned route, the openings the marines hold) when the console's `astra.board.debug` asks for it. */
	void DrawDebug() const;

	/** The tests: what the bodies are doing. */
	int32 NumBodies() const;

	// ------------------------------------------------------------------------------------------------ the Captain's weapons (AstraBoardArms.cpp)
	/** E at a post of the weapons (the Marine Armory's rack, the Ready Room's locker): he takes what it holds that he lacks (the rifle, the sidearm), else puts back what it takes. The words for
	 *  his screen; false when there was nothing to do. */
	bool UseArmsPost(FName Id, APawn* Me, FString& OutNotice);
	/** What a post shows now (what hangs on it) and the key's words for the Captain who stands at it ("" when there is nothing for him to do there). False for a post that is not known. */
	bool ArmsPostView(FName Id, const UAstraFpsComponent* F, bool& bOutRifle, bool& bOutPistol, FString& OutPrompt) const;
	/** The armourer sends a weapon up to the Captain (`issue_weapon`): Kind rifle | pistol | kit; Who must be the Captain. It takes the time of the way from the armory to where he stands, and
	 *  at the end it is in his hands. False, and why, when it cannot be (he has it, the rack has none, he is flying, one is on its way already). */
	bool IssueWeapon(const FString& Kind, const FString& Who, FString& OutDetail);
	/** Where the weapons are kept, what the Captain carries, the armourer, what is on its way (ship_state.arms: the crew's picture of the arms). */
	TSharedRef<FJsonObject> ArmsJson() const;

private:
	enum class EPhase : uint8 { Loading, Failed, Idle, Active, Over };
	/** Where the fight is: on the Aquila's own decks (bodies, the Captain, her bulkheads), or on another ship (the simulation alone: reports and casualties, the Captain not in it). */
	enum class EMode : uint8 { Observed, Remote };

	EPhase Phase = EPhase::Loading;
	EMode Mode = EMode::Observed;
	TFuture<TSharedPtr<FAstraBoardMap>> MapFuture;
	TSharedPtr<FAstraDamageMap> AqDmg;               // the Aquila's own plan and map (read once; the arms and the marines of her decks use these)
	TSharedPtr<FAstraBoardMap> AqMap;
	TSharedPtr<FBoardShipPlan> AqPlan;               // the same with the hatches (her airlocks) and the places a boarding goes for
	TSharedPtr<FAstraDamageMap> Dmg;                 // the plan and map of the fight that is on (the Aquila's own, or the boarded ship's)
	TSharedPtr<FAstraBoardMap> Map;
	TSharedPtr<FBoardShipPlan> ScenePlan;            // (a fight on another ship) her plan
	FAstraBoardSim Fight;
	TWeakObjectPtr<UAstraShipSubsystem> Ship;
	TWeakObjectPtr<UAstraLifeSubsystem> Life;
	TWeakObjectPtr<UAstraCombatFx> Fx;

	// --- the event
	FString Source;
	FString BreachText;
	FVector BreachAt = FVector::ZeroVector;
	float Since = 0.f;                               // game seconds since the start
	float AfterEnd = 0.f;
	bool bBreachOpen = false;
	float WarnLeft = 0.f;
	int32 PriorAlert = 0;
	bool bRaisedAlert = false;
	TSet<int32> SealedByUs;                          // doors of the damage map the fight has sealed (ours to open again)
	TArray<int32> MarineUnits;                       // the sim's units that are roster marines
	TMap<int32, int32> RosterOfUnit;                 // unit -> roster index
	TMap<int32, int32> PersonOfUnit;                 // unit -> VITA's person index
	TSet<int32> HarmTold;                            // roster people whose wound or death the roster has been told
	TSet<int32> ToldDown;                            // units whose fall has been told
	bool bToldContact = false;
	bool bToldTakeover = false;
	float TakeoverFuse = -1.f;
	float CasualtyT = 0.f;
	int32 ToldMarinesLost = 0, ToldMandateLost = 0;
	TArray<FString> Log;                             // what happened, newest last (the marines' net reads it)

	// --- the Captain
	float CapHp = 100.f;
	bool bCapDown = false;
	float CapBleedS = 0.f;
	double CapHurtAt = -100.0;
	FVector CapHurtFrom = FVector::ZeroVector;
	float CapHurtAmount = 0.f;
	float ThreatCm = -1.f;
	float CapRegenT = 0.f;
	bool bCaptainIn = false;
	int32 CaptainSquad = INDEX_NONE;

	// --- the bodies
	UPROPERTY() TArray<TObjectPtr<AAstraCombatant>> PoolMarines;  // the bodies of the marines (a pool: they come and go as the Captain moves)
	UPROPERTY() TArray<TObjectPtr<AAstraCombatant>> PoolMandate;  // and of the Mandate's boarders
	TArray<TObjectPtr<AAstraCombatant>>& PoolOf(int32 Side) { return Side == 0 ? PoolMarines : PoolMandate; }
	TMap<int32, TObjectPtr<AAstraCombatant>> BodyOf;              // unit -> body
	UPROPERTY() TArray<TObjectPtr<UObject>> Warm;
	UPROPERTY() TArray<TObjectPtr<AAstraBoardBreach>> Breaches;   // one for each hatch that is cut open
	float BodyT = 0.f;
	TArray<double> LastShotSound;                // by unit: when it last made a sound
	float ThreatT = 0.f;
	bool bChainDown = false;                     // the ship's chain has taken the Captain's fall (so a Captain who is up again was carried out)
	FVector BreachNormal = FVector::ForwardVector;
	float SoundBudget = 0.f;
	int32 TracesLeft = 0;
	bool bWarmed = false;

	void TryFinishLoading();
	// --- boarding by assault craft (AstraBoardAssault.cpp): one assault at a time, flying and fighting, on one scene
	struct FLeg
	{
		int32 Index = 0;                             // its number in the assault: the battle's Leg and the simulation's party
		int32 CraftId = -1;                          // the battle's id of the boat once it has left
		FString CraftName;                           // "Skiff 2"
		FName DockId;                                // the plan's hatch
		int32 BreachComp = INDEX_NONE;               // the room the hatch opens into (the boarded ship's plan)
		FVector HatchCm = FVector::ZeroVector;       // the hatch on the skin (the plan's frame, cm)
		FVector InCm = FVector::ZeroVector;          // inside, on the floor, a step from it
		FVector Into = FVector::ForwardVector;       // the wall's normal, into the room
		FVector HullM = FVector::ZeroVector;         // the hatch in the boarded ship's hull frame (m): where the boat goes
		FVector OutNormal = FVector::ForwardVector;  // out of the hull there
		int32 Men = 0;
		TArray<AstraBoard::FArrival> Arrivals;       // who is in the boat
		enum class EState : uint8 { Ordered, Flying, Latched, Through, Lost, TurnedBack, Home } State = EState::Ordered;
		int32 Breach = INDEX_NONE;                   // its cut in the Aquila's hull (index into Breaches)
		FString PlaceText;                           // where it comes out, in words
		bool bLanded = false;                        // its men have been put into the fight
		bool bSailing = false;                       // it has left: its men are not in the ship
		bool bReported = false;
		bool Resolved() const { return State == EState::Lost || State == EState::Home || (State == EState::TurnedBack && !bSailing); }
	};
	struct FAssault
	{
		bool bOn = false;
		int32 Order = 0;
		AstraBoard::ESide Attacker = AstraBoard::ESide::Mandate;
		bool bObserved = true;                       // the Aquila's own decks are the scene (else another ship's plan)
		bool bRoster = false;                        // the attackers are the Aquila's marines of the ship's roster
		int32 CarrierId = -1, TargetId = -1;
		FString CarrierName, TargetName, CarrierClass, TargetClassText;
		FName TargetClass;
		FString Objective;                           // as ordered
		FString By;
		bool bLockdown = true;
		bool bCaptain = false;
		TArray<FLeg> Legs;
		float T = 0.f;                               // seconds since the order
		float LaunchT = 0.f;                         // ... when the battle was given the boats
		float EtaS = 0.f;                            // the first boat's flight, as the battle gave it
		bool bLaunched = false;                      // the battle has the boats
		bool bSceneBegun = false;
		bool bDeparting = false;                     // the fight is over: the boats are told to let go
		bool bFightSeen = false;                     // a fight was on the scene
		float DoneT = 0.f;
		FString PlanKey;
		TFuture<TSharedPtr<FBoardShipPlan>> PlanFuture;   // the target's plan is being read before the boats go
		bool bPlanWait = false;
		double PlanSinceS = 0.0;                     // (the wall clock when the reading began: a bench runs the game's clock a thousand times too fast for it)
		FAssaultSpec Spec;
		FString PlanWhy;
	};
	FAssault Assault;
	int32 NextOrder = 1;
	float AssaultPollT = 0.f;
	TArray<FString> AssaultNote;                     // what the order said, for the minds (last few lines)
	void BuildAquilaPlan();
	void TickAssault(float Dt);
	bool LaunchAssault(FString& OutDetail);
	bool ChooseHatches(const FBoardShipPlan& Plan, const FString& Face, const FString& BreachId, const AstraBoardCraft::FShipFacts& Target, const AstraBoardCraft::FShipFacts& Carrier,
	                   int32 Count, TArray<int32>& OutDocks, FString& OutWhy) const;
	void FillLeg(FLeg& L, const FBoardShipPlan& Plan, int32 Dock, const TCHAR* Face) const;
	void OnCraftEvent(const AstraBoardCraft::FCraftEvent& E);
	void BeginObservedScene();
	bool BeginRemoteScene();
	void LandLeg(FLeg& L);
	void CloseAssault(const TCHAR* Why);
	void EndAssaultFight(const TCHAR* Why);
	void RemoteStep(float Dt);
	void OnRemoteOutcome();
	void ReturnMarines(FLeg& L, bool bAlive);
	void MarkMarinesLost(FLeg& L, const FString& Cause);
	int32 PickMarines(int32 Total, TArray<TArray<int32>>& OutLegs) const;
	void OpenBreachAt(FLeg& L);
	FLeg* LegOf(int32 Index);
	UAstraBattleSubsystem* Battle() const;
	FString AssaultText() const;
	void ResetScene(EMode NewMode);
	void EnterObserved(const FString& SourceText, int32 BreachComp, const FVector& At, bool bLockdown, float WarnS = 0.f);
	// --- the weapons: the places the Captain's are kept (the posts, the stock of each), their pictures while he is near, and the armourer's delivery (AstraBoardArms.cpp)
	struct FArmsPost
	{
		FName Id;
		FString Label;                               // "the Marine Armory's rack"
		FString Where;                               // in words, for the crew
		FVector Pos = FVector::ZeroVector;           // on the floor under it (cm)
		float Yaw = 0.f;                             // its front (degrees)
		bool bLocker = false;
		bool bRifle = false, bPistol = false;        // what is on it now
		bool bTakesRifle = false;                    // what it takes back
		TWeakObjectPtr<AAstraArmoryRack> Actor;
	};
	struct FDelivery
	{
		bool bActive = false;
		bool bRifle = false, bPistol = false;
		float T = 0.f, EtaS = 0.f;
		float HandsWaitS = 0.f;                      // how long it has waited for his hands to be free
		FString By;                                  // "Petty Officer Dara Okafor"
	};
	TArray<FArmsPost> ArmsPosts;
	FDelivery Delivery;
	float ArmsT = 0.f;
	FString Armourer;                                // the armourer of the roster (looked up every little while)
	float ArmourerT = 0.f;
	bool bArmsBuilt = false;
	void BuildArmsPosts();
	void TickArms(float Dt);
	FArmsPost* FindPost(FName Id);
	const FArmsPost* FindPost(FName Id) const;
	FString ArmourerName(const FVector& Near) const;
	// --- the beginning
	bool PickBreach(const FString& Id, int32& OutComp, FVector& OutAt, FString& OutWhy) const;
	void MobiliseMarines();
	void SealSections(int32 BreachComp, const FVector& At);
	void OpenSections();
	void SealDoor(int32 Door, bool bSealed);
	void MakeSightOverride();
	// --- the step
	void Step(float Dt);
	void SyncCaptain(float Dt);
	void SyncLife();
	void ProcessEvents(float Dt);
	void OnShot(const AstraBoard::FBoardEvent& E);
	void OnHit(const AstraBoard::FBoardEvent& E);
	void OnFall(const AstraBoard::FBoardEvent& E, bool bDied);
	void OnOutcome();
	void OnCaptainHit(const AstraBoard::FBoardEvent& E);
	void CaptainFate(float Dt);
	void OpenBreach();
	void Tell(const FString& Text, bool bReport);
	void ManageBodies(float Dt);
	AAstraCombatant* TakeBody(int32 Side);
	void ReleaseBody(int32 Unit);
	void ClearBodies();
	void Finish(const TCHAR* Why);
	FString NameOf(const AstraBoard::FUnit& U) const;
	FString PlaceOf(const AstraBoard::FUnit& U) const;
	UAstraShipSubsystem* ShipSub() const;
	UAstraLifeSubsystem* LifeSub() const;
	UAstraCombatFx* FxSub() const;
	bool CaptainFeet(FVector& OutFeet, float& OutYaw, bool& bOutLow, float& OutSpeed) const;
};

/** What the Mandate's cutting looks like from inside: a ring of glowing cut and a hot light at the breach, up for as long as the boarders come in by it. */
UCLASS()
class ASTRA_API AAstraBoardBreach : public AActor
{
	GENERATED_BODY()

public:
	AAstraBoardBreach();
	/** The hole: where it is (floor level, cm) and which way the wall faces (the unit vector into the room). */
	void Open(const FVector& At, const FVector& IntoRoom);
	void Close();
	bool IsOpen() const { return bOpen; }

protected:
	virtual void Tick(float DeltaSeconds) override;

private:
	bool bOpen = false;
	float Age = 0.f;
	FVector Centre = FVector::ZeroVector;
	FVector Normal = FVector::ForwardVector;
	UPROPERTY() TArray<TObjectPtr<class UStaticMeshComponent>> Ring;
	UPROPERTY() TArray<TObjectPtr<class UMaterialInstanceDynamic>> RingMIDs;
	UPROPERTY() TObjectPtr<class UPointLightComponent> Glow;
	UPROPERTY() TObjectPtr<class UStaticMesh> LineMesh;
	UPROPERTY() TObjectPtr<class UMaterialInterface> GlowMat;
	void Build();
};
