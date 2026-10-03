// ASTRA — ship simulation.

#include "AstraShipSubsystem.h"
#include "AstraLiftSubsystem.h"
#include "AstraLifeSubsystem.h"
#include "AstraBoardSubsystem.h"
#include "AstraHarness.h"
#include "AstraStations.h"
#include "AstraTransporterSubsystem.h"
#include "AstraViewscreen.h"

#include "ASTRA.h"
#include "AstraBattleSubsystem.h"
#include "AstraBridgeFX.h"
#include "AstraDamageFx.h"
#include "AstraDoor.h"
#include "AstraHangar.h"
#include "AstraPatient.h"
#include "AstraQuarters.h"
#include "AstraShipPlan.h"
#include "GameFramework/Character.h"
#include "AstraCrewMember.h"
#include "AstraLifepod.h"
#include "AstraCampaign.h"
#include "ASTRAPlayerController.h"
#include "AstraFighterPawn.h"
#include "Async/Async.h"
#include "Camera/PlayerCameraManager.h"
#include "GameFramework/PlayerController.h"
#include "AstraWorldGen.h"
#include "AstraWorldSurface.h"
#include "AstraNavLights.h"
#include "Components/DecalComponent.h"
#include "Engine/Texture2D.h"
#include "Components/DirectionalLightComponent.h"
#include "Components/LightComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/DirectionalLight.h"
#include "Engine/Light.h"
#include "Engine/PostProcessVolume.h"
#include "Engine/SkyLight.h"
#include "Components/SkyLightComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshActor.h"
#include "EngineUtils.h"
#include "TimerManager.h"
#include "Engine/Engine.h"
#include "Misc/CommandLine.h"
#include "Kismet/GameplayStatics.h"
#include "Kismet/KismetMaterialLibrary.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialParameterCollection.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Sound/SoundBase.h"

DECLARE_CYCLE_STAT(TEXT("Ship"), STAT_AstraShip, STATGROUP_Astra);
DECLARE_CYCLE_STAT(TEXT("Interior"), STAT_AstraInterior, STATGROUP_Astra);

namespace
{
	TAutoConsoleVariable<float> CVarSpaceFill(TEXT("astra.light.fill"), 0.f, TEXT("The cool fill on hulls from the main viewscreen camera's side, as a share of the star's light (outside the hull only)"));
	const FName TagSky(TEXT("ASTRA.Sky"));
	const FName TagSun(TEXT("ASTRA.Sun"));
	const FName TagShipLight(TEXT("ASTRA.ShipLight"));

	FString AlertName(EAstraAlert A)
	{
		switch (A)
		{
		case EAstraAlert::Yellow: return TEXT("yellow");
		case EAstraAlert::Red: return TEXT("red");
		default: return TEXT("green");
		}
	}

	/** Where a pawn is in the ship's plan (the decks of the whole Aquila, docs/NAVE.md): its compartment, or null off the plan (a
	 *  Falcon, a planet, a level without the plan). */
	const FAstraPlanCompartment* PlanCompartmentOf(const UWorld* World, const APawn* P)
	{
		const UAstraShipPlan* Plan = World && P ? World->GetSubsystem<UAstraShipPlan>() : nullptr;
		return Plan ? Plan->CompartmentAt(P->GetActorLocation()) : nullptr;
	}

	/** A compartment's own name without the section the plan writes into a corridor's ("Port Passage · Section C" -> "Port Passage"). */
	FString PlanRoomName(const FAstraPlanCompartment& Comp)
	{
		FString Name = Comp.Name;
		const int32 Cut = Name.Find(TEXT(" · Section"));
		return Cut != INDEX_NONE ? Name.Left(Cut) : Name;
	}

	float WrapDeg(float D) { return FMath::Fmod(FMath::Fmod(D, 360.f) + 360.f, 360.f); }
	float DeltaDeg(float From, float To) { return FMath::FindDeltaAngleDegrees(From, To); }

	FAutoConsoleCommandWithWorldAndArgs CmdLightInfo(TEXT("astra.light.info"),
		TEXT("Testing: the star's light, the planet's and the fill on the hulls (direction, intensity, channels)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& A, UWorld* World)
		{
			const UAstraShipSubsystem* Ship = World ? World->GetSubsystem<UAstraShipSubsystem>() : nullptr;
			if (Ship)
			{
				UE_LOG(LogASTRA, Display, TEXT("%s"), *Ship->LightInfo());
			}
		}));

	// testing: any ship command as the crew (or the director) would send it; single quotes stand for double quotes
	FAutoConsoleCommandWithWorldAndArgs CmdPlanet(TEXT("astra.planet"),
		TEXT("Testing: astra.planet go (the Captain on foot at Port Aurelius Field) | back (on the bridge in space)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& A, UWorld* World)
		{
			UAstraShipSubsystem* Ship = World ? World->GetSubsystem<UAstraShipSubsystem>() : nullptr;
			APawn* P = World ? UGameplayStatics::GetPlayerPawn(World, 0) : nullptr;
			if (!Ship || !P)
			{
				return;
			}
			const bool bGo = A.Num() == 0 || A[0].Equals(TEXT("go"), ESearchCase::IgnoreCase);
			Ship->SetPlanetside(bGo);
			if (bGo)
			{
				// on the apron by Pad 3, facing the tower (home); beside the landing pad elsewhere
				P->SetActorLocation(Ship->IsHomeWorld() ? UAstraShipSubsystem::PlanetZone() + FVector(1790.0, -1250.0, 194.0) * 100.0
				                                        : Ship->SurfaceSite() + FVector(2600.0, 0.0, 200.0), false, nullptr, ETeleportType::TeleportPhysics);
				if (APlayerController* PC = Cast<APlayerController>(P->GetController()))
				{
					PC->SetControlRotation(FRotator(0.f, 180.f, 0.f));
				}
				Ship->SetCaptainPlanetside(FString::Printf(TEXT("on foot at %s on %s; the XO has the conn"), *Ship->SurfaceSiteName(), *Ship->SurfaceWorldName()));
			}
			else
			{
				P->SetActorLocation(FVector(-300.0, 0.0, 120.0), false, nullptr, ETeleportType::TeleportPhysics);
			}
		}));
	FAutoConsoleCommandWithWorldAndArgs CmdMedbay(TEXT("astra.medbay"),
		TEXT("Testing: astra.medbay admit <n> (n wounded from random hits) | care <minutes> (the doctors' rounds) | go (to the ward)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& A, UWorld* World)
		{
			UAstraShipSubsystem* Ship = World ? World->GetSubsystem<UAstraShipSubsystem>() : nullptr;
			if (!Ship || A.Num() < 1)
			{
				return;
			}
			if (A[0].Equals(TEXT("go"), ESearchCase::IgnoreCase))
			{
				for (TActorIterator<AAstraHangar> It(World); It; ++It)
				{
					if (!It->MedbayLanding.IsNearlyZero())
					{
						if (APawn* P = UGameplayStatics::GetPlayerPawn(World, 0))
						{
							P->SetActorLocation(It->MedbayLanding + FVector(0, 0, 100), false, nullptr, ETeleportType::TeleportPhysics);
							if (APlayerController* PC = Cast<APlayerController>(P->GetController()))
							{
								PC->SetControlRotation(FRotator(0.f, 180.f, 0.f));
							}
						}
					}
				}
				return;
			}
			Ship->TestMedbay(A[0], A.Num() > 1 ? FCString::Atoi(*A[1]) : 3);
		}));
	FAutoConsoleCommandWithWorldAndArgs CmdHit(TEXT("astra.ship.hit"),
		TEXT("Testing: astra.ship.hit [hull damage per hit = 60] [hits = 3] (hits through the shields, from random directions)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& A, UWorld* World)
		{
			UAstraShipSubsystem* Ship = World ? World->GetSubsystem<UAstraShipSubsystem>() : nullptr;
			const float Dmg = A.Num() > 0 ? FCString::Atof(*A[0]) : 60.f;
			const int32 N = A.Num() > 1 ? FCString::Atoi(*A[1]) : 3;
			for (int32 i = 0; Ship && i < N; ++i)
			{
				Ship->OnHullHit(Dmg, 0.f, FMath::VRand());
			}
		}));
	FAutoConsoleCommandWithWorldAndArgs CmdDamageInfo(TEXT("astra.damage.info"),
		TEXT("DISTRUZIONE: the damage inside the hull: what is in play, the incidents, the books, what the model costs"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& A, UWorld* World)
		{
			const UAstraShipSubsystem* Ship = World ? World->GetSubsystem<UAstraShipSubsystem>() : nullptr;
			if (!Ship)
			{
				return;
			}
			const FAstraDamageModel& I = Ship->GetInterior();
			float Avg = 0.f, Max = 0.f;
			Ship->InteriorCost(Avg, Max);
			UE_LOG(LogASTRA, Display, TEXT("[Damage] %s | cost %.3f ms a tick (worst %.2f)"), I.IsReady() ? *I.InfoText() : TEXT("the damage model is not up (the plan is still loading or missing)"), Avg, Max);
			if (I.IsReady())
			{
				UE_LOG(LogASTRA, Display, TEXT("[Damage] power the ship's distribution still carries: shields %.2f weapons %.2f engines %.2f sensors %.2f life support %.2f flight deck %.2f"),
				       I.Power().Factor[0], I.Power().Factor[1], I.Power().Factor[2], I.Power().Factor[3], I.Power().Factor[4], I.Power().Factor[5]);
				const FAstraDmgCaptain& C = I.Captain();
				UE_LOG(LogASTRA, Display, TEXT("[Damage] the Captain: %s, peril %.2f (hypoxia %.1f, burn %.1f, smoke %.1f, trauma %.1f)"),
				       C.State == FAstraDmgCaptain::EState::Well ? TEXT("well") : (C.State == FAstraDmgCaptain::EState::Impaired ? TEXT("impaired") : (C.State == FAstraDmgCaptain::EState::Down ? TEXT("down") : TEXT("dead"))),
				       C.Peril, C.Hypoxia, C.Burn, C.Smoke, C.Trauma);
				for (const FAstraDamage& D : Ship->GetDamage())
				{
					UE_LOG(LogASTRA, Display, TEXT("[Damage]    #%d %s: %s (%s) severity %.2f%s"), D.Id, *D.Where(), *D.Kind, *D.Note, D.Severity, D.Team >= 0 ? *FString::Printf(TEXT(", team %d"), D.Team + 1) : TEXT(""));
				}
			}
		}));
	FAutoConsoleCommandWithWorldAndArgs CmdDamageStrike(TEXT("astra.damage.strike"),
		TEXT("Testing: astra.damage.strike [here | a compartment's id or part of its name] [energy 40] [kinetic|energy|explosive] [nohole]: a blow into a compartment ('here': the one the Captain is in)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& A, UWorld* World)
		{
			UAstraShipSubsystem* Ship = World ? World->GetSubsystem<UAstraShipSubsystem>() : nullptr;
			if (!Ship || !Ship->GetInterior().IsReady())
			{
				UE_LOG(LogASTRA, Warning, TEXT("[Damage] the damage model is not up"));
				return;
			}
			FAstraDamageModel& I = Ship->GetInterior();
			const FString Where = A.Num() ? A[0] : FString(TEXT("here"));
			int32 Comp = INDEX_NONE;
			if (Where.Equals(TEXT("here"), ESearchCase::IgnoreCase))
			{
				if (const APawn* P = UGameplayStatics::GetPlayerPawn(World, 0))
				{
					Comp = Ship->InteriorCompOf(P->GetActorLocation());
				}
			}
			else if (const int32* Id = I.GetMap().CompByName.Find(FName(*Where)))
			{
				Comp = *Id;
			}
			else
			{
				for (int32 i = 0; i < I.GetMap().Comps.Num() && Comp == INDEX_NONE; ++i)
				{
					Comp = I.GetMap().Comps[i].Name.Contains(Where, ESearchCase::IgnoreCase) && !I.GetMap().Comps[i].bCorridor ? i : INDEX_NONE;
				}
			}
			if (Comp == INDEX_NONE)
			{
				UE_LOG(LogASTRA, Warning, TEXT("[Damage] no such compartment (a compartment id such as d4_galley_B1, part of a name such as Galley, or here)"));
				return;
			}
			const float Energy = A.Num() > 1 ? FCString::Atof(*A[1]) : 40.f;
			const FString T = A.Num() > 2 ? A[2].ToLower() : FString(TEXT("kinetic"));
			const uint8 Type = T.StartsWith(TEXT("en")) ? 1 : (T.StartsWith(TEXT("ex")) ? 2 : 0);
			const bool bHole = !(A.Num() > 3 && A[3].StartsWith(TEXT("no")));
			FAstraImpactResult R;
			I.Strike(Comp, Energy, Type, I.GetMap().Comps[Comp].Box.GetCenter(), bHole, R);
			if (UAstraDamageFx* Fx = World->GetSubsystem<UAstraDamageFx>())
			{
				Fx->OnBlow(R, Energy);                       // the boom and the sparks too, as for a real blow
			}
			UE_LOG(LogASTRA, Display, TEXT("[Damage] a blow of %.0f into %s: %s%s"), Energy, *I.GetMap().Describe(Comp), R.Lines.Num() ? *FString::Join(R.Lines, TEXT("; ")) : TEXT("nothing came of it"),
			       R.Killed + R.Wounded ? *FString::Printf(TEXT(" — %d killed, %d wounded"), R.Killed, R.Wounded) : TEXT(""));
		}));
	FAutoConsoleCommandWithWorld CmdDamageReset(TEXT("astra.damage.reset"), TEXT("Testing: everything the damage model has in play is made whole at once (the bulkheads open, the incidents go)"),
		FConsoleCommandWithWorldDelegate::CreateLambda([](UWorld* World)
		{
			if (UAstraShipSubsystem* Ship = World ? World->GetSubsystem<UAstraShipSubsystem>() : nullptr)
			{
				Ship->ResetInterior();
			}
		}));
	FAutoConsoleCommandWithWorldAndArgs CmdHeat(TEXT("astra.heat"),
		TEXT("Testing: astra.heat <percent> sets the ship's thermal load"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& A, UWorld* World)
		{
			if (UAstraShipSubsystem* Ship = World ? World->GetSubsystem<UAstraShipSubsystem>() : nullptr)
			{
				Ship->AddHeat(A.Num() ? FCString::Atof(*A[0]) - Ship->GetHeatPct() : 0.f);
				UE_LOG(LogASTRA, Log, TEXT("[Heat] %.0f %%"), Ship->GetHeatPct());
			}
		}));
	FAutoConsoleCommandWithWorldAndArgs CmdWalk(TEXT("astra.walk"),
		TEXT("Testing: astra.walk <station> [back] walks an officer along their way to the Captain's quarters (no visit), or back"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& A, UWorld* World)
		{
			AAstraCrewMember* C = A.Num() ? AAstraCrewMember::FindByStation(World, A[0]) : nullptr;
			if (!C)
			{
				return;
			}
			if (A.Num() > 1 && A[1] == TEXT("back"))
			{
				C->Leave();
				return;
			}
			int32 WaitAt = INDEX_NONE;
			C->Visit(UAstraShipSubsystem::VisitRouteFor(C, WaitAt), WaitAt, 2.4f);
		}));
	FAutoConsoleCommandWithWorldAndArgs CmdShip(TEXT("astra.cmd"),
		TEXT("Run a ship command (testing): astra.cmd <name> <json args, ' for \">, e.g. astra.cmd director_beat {'beat':{'type':'transit','system_name':'Meridian'}}"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& A, UWorld* World)
		{
			UAstraShipSubsystem* Ship = World ? World->GetSubsystem<UAstraShipSubsystem>() : nullptr;
			if (A.Num() < 1 || !Ship)
			{
				return;
			}
			FString Json;
			for (int32 i = 1; i < A.Num(); ++i)
			{
				Json += (i > 1 ? TEXT(" ") : TEXT("")) + A[i];
			}
			Json = Json.Replace(TEXT("'"), TEXT("\""));
			TSharedPtr<FJsonObject> Args = MakeShared<FJsonObject>();
			if (!Json.IsEmpty())
			{
				TSharedRef<TJsonReader<>> R = TJsonReaderFactory<>::Create(Json);
				if (!FJsonSerializer::Deserialize(R, Args) || !Args.IsValid())
				{
					UE_LOG(LogASTRA, Warning, TEXT("[Cmd] bad JSON: %s"), *Json);
					return;
				}
			}
			FString Detail;
			const bool bOk = Ship->ApplyCommand(A[0], Args, Detail);
			UE_LOG(LogASTRA, Log, TEXT("[Cmd] %s -> %s: %s"), *A[0], bOk ? TEXT("ok") : TEXT("FAILED"), *Detail);
		}));
}

bool UAstraShipSubsystem::ShouldCreateSubsystem(UObject* Outer) const
{
	const UWorld* World = Cast<UWorld>(Outer);
	return World && (World->WorldType == EWorldType::Game || World->WorldType == EWorldType::PIE);
}

void UAstraShipSubsystem::OnWorldBeginPlay(UWorld& InWorld)
{
	Super::OnWorldBeginPlay(InWorld);
	Roster.Generate();
	CasualtyRng.Initialize(GAstraDeterministic ? FMath::Rand() : (int32)(FDateTime::Now().GetTicks() & 0x7fffffff));
	FActorSpawnParameters FXP;
	FXP.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	BridgeFX = InWorld.SpawnActor<AAstraBridgeFX>(FVector::ZeroVector, FRotator::ZeroRotator, FXP);
	// the main viewscreen: in front of the central facets of the bow window, 1.2 m above the upper deck (ARCHITETTURA §5)
	if (FApp::CanEverRender())
	{
		Viewscreen = InWorld.SpawnActor<AAstraViewscreen>(FVector(900.f, 0.f, 120.f), FRotator::ZeroRotator, FXP);
	}
	PowerPct = {{TEXT("shields"), 100.f}, {TEXT("weapons"), 100.f}, {TEXT("engines"), 100.f}, {TEXT("sensors"), 100.f},
	            {TEXT("life_support"), 100.f}, {TEXT("flight_deck"), 100.f}};
	Weapons = {{TEXT("railguns"), TEXT("ready (4 twin turrets)")}, {TEXT("lasers"), TEXT("ready (12 batteries)")},
	           {TEXT("missiles"), TEXT("ready (96 in VLS)")}, {TEXT("torpedoes"), TEXT("ready (2 loaded)")}};
	Squadrons = {{TEXT("alpha"), TEXT("on deck, ready (8 Falcons)")}, {TEXT("bravo"), TEXT("on deck, ready (7 of 8 Hammers)")},
	             {TEXT("drones"), TEXT("ready (12 Wasps)")}};
	Contacts = {
		{TEXT("T-01"), TEXT("ASTRA battleship"), TEXT("ASN Praetorian (7th Fleet flagship)"), TEXT("friendly"), 12.f, 20.f},
		{TEXT("T-02"), TEXT("ASTRA destroyer"), TEXT("ASN Vigilant"), TEXT("friendly"), 18.f, 80.f},
		{TEXT("T-07"), TEXT("freighter"), TEXT("Free Guilds hauler Brightwater"), TEXT("neutral"), 67.f, 310.f},
		{TEXT("T-11"), TEXT("unknown"), TEXT(""), TEXT("unidentified, cold drive, drifting"), 50.f, 200.f},
	};
	Heading0 = HeadingDeg;
	Mark0 = MarkDeg;
	CollectSceneRefs(InWorld);
	UpdateAttitudeVisuals();
	StartInterior();
	DoorPlacedHandle = AstraDoors::OnPlaced().AddUObject(this, &UAstraShipSubsystem::OnDoorPlaced);
	// the bridge at rest: reactor hum through the deck, air handling, far electronics (a seamless loop)
	if (USoundBase* Amb = LoadObject<USoundBase>(nullptr, TEXT("/Game/ASTRA/Audio/SW_Bridge_Ambience.SW_Bridge_Ambience")))
	{
		UGameplayStatics::SpawnSound2D(&InWorld, Amb, 0.5f);
	}
	if (FParse::Param(FCommandLine::Get(), TEXT("astra_planet")))
	{
		// testing (performance runs): the Captain on foot at Port Aurelius Field a few seconds in
		FTimerHandle H;
		InWorld.GetTimerManager().SetTimer(H, FTimerDelegate::CreateWeakLambda(this, [this]()
		{
			GEngine->Exec(GetWorld(), TEXT("astra.planet go"));
		}), 4.f, false);
	}
	FString WorldSystem;
	if (FParse::Value(FCommandLine::Get(), TEXT("astra_world="), WorldSystem))
	{
		// testing (performance runs): out of a gate in that system, then the Captain on foot at its landing field
		// (-astra_world=Cassia+blue_white+ice+Cassia_Prime: the arguments of astra.battle.arrive, joined by '+')
		WorldSystem.ReplaceInline(TEXT("+"), TEXT(" "));
		FTimerHandle H, H2;
		InWorld.GetTimerManager().SetTimer(H, FTimerDelegate::CreateWeakLambda(this, [this, WorldSystem]()
		{
			GEngine->Exec(GetWorld(), *FString::Printf(TEXT("astra.battle.arrive %s"), *WorldSystem));
		}), 3.f, false);
		InWorld.GetTimerManager().SetTimer(H2, FTimerDelegate::CreateWeakLambda(this, [this]()
		{
			GEngine->Exec(GetWorld(), TEXT("astra.planet go"));
		}), 6.f, false);
	}
	if (FParse::Param(FCommandLine::Get(), TEXT("astra_profilegpu")))
	{
		// testing: one frame's GPU breakdown in the log, once the scene has settled
		FTimerHandle H;
		InWorld.GetTimerManager().SetTimer(H, FTimerDelegate::CreateWeakLambda(this, [this]()
		{
			GEngine->Exec(GetWorld(), TEXT("ProfileGPU"));
		}), 25.f, false);
	}
	FString LaterCmds;
	if (FParse::Value(FCommandLine::Get(), TEXT("astra_later="), LaterCmds, false))
	{
		// testing: console commands run once the scene has settled, ';' between them (-astra_later="stat dumpframe -ms=0.1")
		FTimerHandle H;
		InWorld.GetTimerManager().SetTimer(H, FTimerDelegate::CreateWeakLambda(this, [this, LaterCmds]()
		{
			TArray<FString> Cmds;
			LaterCmds.ParseIntoArray(Cmds, TEXT(";"));
			APlayerController* PC = GetWorld() ? GetWorld()->GetFirstPlayerController() : nullptr;
			for (const FString& Cmd : Cmds)
			{
				// through the player's console path, which reaches the viewport too (shot, HighResShot)
				if (PC) { PC->ConsoleCommand(Cmd.TrimStartAndEnd()); } else { GEngine->Exec(GetWorld(), *Cmd.TrimStartAndEnd()); }
			}
		}), 25.f, false);
	}
	if (FParse::Param(FCommandLine::Get(), TEXT("astra_decisive")))
	{
		// testing (performance runs): a decisive battle in front of the bridge — two ASTRA destroyers join, eight Mandate
		// ships (three capital ships with their fighters) come in close, and it starts at once
		FTimerHandle H;
		InWorld.GetTimerManager().SetTimer(H, FTimerDelegate::CreateWeakLambda(this, [this]()
		{
			GEngine->Exec(GetWorld(), TEXT("astra.cmd director_beat {'beat':{'type':'reinforcements','granted':true,'range_km':6,'bearing_deg':200,")
			                          TEXT("'ships':[{'class':'vigilant','name':'ASN Resolute'},{'class':'vigilant','name':'ASN Constant'}]}}"));
			GEngine->Exec(GetWorld(), TEXT("astra.cmd director_beat {'beat':{'type':'raid','hail':false,'range_km':16,'bearing_deg':25,")
			                          TEXT("'ships':[{'class':'acheron','name':'KMS Charon'},{'class':'styx','name':'KMS Persephone'},")
			                          TEXT("{'class':'styx','name':'KMS Tartarus'},{'class':'lethe','name':'KMS Cocytus'},{'class':'lethe','name':'KMS Phlegethon'},")
			                          TEXT("{'class':'lethe','name':'KMS Asphodel'},{'class':'lethe','name':'KMS Lethe'},{'class':'lethe','name':'KMS Acheron Minor'}]}}"));
		}), 4.f, false);
	}
	if (FParse::Param(FCommandLine::Get(), TEXT("astra_mess")))
	{
		// testing (performance runs): the Captain in the Mess Hall a few seconds in, looking down the tables
		FTimerHandle H;
		InWorld.GetTimerManager().SetTimer(H, FTimerDelegate::CreateWeakLambda(this, [this]()
		{
			APawn* P = UGameplayStatics::GetPlayerPawn(this, 0);
			for (TActorIterator<AAstraHangar> It(GetWorld()); It && P; ++It)
			{
				if (!It->MessLanding.IsNearlyZero())
				{
					P->SetActorLocation(It->MessLanding + FVector(-300.f, 0.f, 100.f), false, nullptr, ETeleportType::TeleportPhysics);
					if (AController* C = P->GetController())
					{
						C->SetControlRotation(FRotator(-6.f, 180.f, 0.f));
					}
				}
			}
		}), 4.f, false);
	}
	if (FParse::Param(FCommandLine::Get(), TEXT("astra_medbay")))
	{
		// testing (performance runs): the Captain in the Medbay among eight wounded a few seconds in
		FTimerHandle H;
		InWorld.GetTimerManager().SetTimer(H, FTimerDelegate::CreateWeakLambda(this, [this]()
		{
			GEngine->Exec(GetWorld(), TEXT("astra.medbay admit 8"));
			GEngine->Exec(GetWorld(), TEXT("astra.medbay go"));
		}), 4.f, false);
	}
	UE_LOG(LogASTRA, Log, TEXT("[Ship] online: sky %s, sun %s, %d ship lights"), SkyMID ? TEXT("yes") : TEXT("no"),
	       Sun ? TEXT("yes") : TEXT("no"), ShipLights.Num());
}

void UAstraShipSubsystem::CollectSceneRefs(UWorld& InWorld)
{
	ShipMPC = LoadObject<UMaterialParameterCollection>(nullptr, TEXT("/Game/ASTRA/Materials/MPC_ASTRA_Ship.MPC_ASTRA_Ship"));
	for (TActorIterator<AActor> It(&InWorld); It; ++It)
	{
		AActor* A = *It;
		if (A->ActorHasTag(TagSky))
		{
			if (UStaticMeshComponent* SMC = A->FindComponentByClass<UStaticMeshComponent>())
			{
				SkyMID = SMC->CreateAndSetMaterialInstanceDynamic(0);
				if (SkyMID)
				{
					const TCHAR* Names[3] = {TEXT("SkyAxisX"), TEXT("SkyAxisY"), TEXT("SkyAxisZ")};
					for (int32 i = 0; i < 3; ++i)
					{
						FLinearColor C;
						SkyMID->GetVectorParameterValue(FHashedMaterialParameterInfo(Names[i]), C);
						SkyAxis0[i] = FVector(C.R, C.G, C.B);
					}
				}
			}
		}
		else if (A->ActorHasTag(TagSun))
		{
			Sun = Cast<ADirectionalLight>(A);
			if (Sun)
			{
				SunDir0 = -Sun->GetActorForwardVector();
			}
		}
		else if (A->ActorHasTag(TagShipLight))
		{
			if (ALight* L = Cast<ALight>(A))
			{
				ShipLights.Add(L);
				ShipLightBase.Add(L->GetLightComponent()->Intensity);
				ShipLightColorBase.Add(L->GetLightComponent()->GetLightColor());
			}
		}
	}
	// the star stays the main directional light (forward shading, translucency, volumetric fog): the planet's light
	// below is only a fill (the engine clamps priorities at 0, so the star is raised instead)
	if (Sun)
	{
		if (UDirectionalLightComponent* SD = Cast<UDirectionalLightComponent>(Sun->GetLightComponent()))
		{
			SD->SetForwardShadingPriority(1);
		}
	}
	// the planet's light: spawned here, aimed by UpdateAttitudeVisuals
	FActorSpawnParameters SP;
	SP.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	SP.ObjectFlags |= RF_Transient;
	PlanetLight = InWorld.SpawnActor<ADirectionalLight>(FVector::ZeroVector, FRotator::ZeroRotator, SP);
	if (PlanetLight)
	{
		if (UDirectionalLightComponent* D = Cast<UDirectionalLightComponent>(PlanetLight->GetLightComponent()))
		{
			D->SetMobility(EComponentMobility::Movable);
			D->SetCastShadows(false);
			D->SetLightingChannels(false, true, false);
			D->SetAtmosphereSunLight(false);
			D->SetSpecularScale(0.3f);
			D->SetLightSourceAngle(25.f);     // a planet is a broad source: soft highlights
			D->SetIntensity(0.f);
		}
	}
	// the night side of a hull is not a hole: a faint cool fill from the side of the main viewscreen's camera (AimSpaceFill), outside the
	// hull only (channel 1), without shadows — what a film's camera does. Without it a backlit cruiser on the screen is a black cut-out
	SpaceFill = InWorld.SpawnActor<ADirectionalLight>(FVector::ZeroVector, FRotator::ZeroRotator, SP);
	if (SpaceFill)
	{
		if (UDirectionalLightComponent* D = Cast<UDirectionalLightComponent>(SpaceFill->GetLightComponent()))
		{
			D->SetMobility(EComponentMobility::Movable);
			D->SetCastShadows(false);
			D->SetLightingChannels(false, true, false);
			D->SetAtmosphereSunLight(false);
			D->SetSpecularScale(0.15f);
			D->SetLightSourceAngle(40.f);
			D->SetLightColor(FLinearColor(0.62f, 0.74f, 1.f));
			D->SetIntensity(0.f);
		}
	}
	// the Aquila's own hull (and any ship or station placed in the level) is outside: channel 1 as well
	int32 Exterior = 0;
	for (TActorIterator<AStaticMeshActor> It(&InWorld); It; ++It)
	{
		UStaticMeshComponent* C = It->GetStaticMeshComponent();
		const UStaticMesh* M = C ? C->GetStaticMesh() : nullptr;
		if (M && (M->GetName().StartsWith(TEXT("SM_SHIP_")) || M->GetName().StartsWith(TEXT("SM_STATION_")))
		    && !It->ActorHasTag(TEXT("ASTRA.Interior")))   // a ship's model in a cabin stays inside
		{
			C->SetLightingChannels(true, true, false);
			++Exterior;
			const int32 Slot = M->GetName() == TEXT("SM_SHIP_ASTRA_Aquila") ? C->GetMaterialIndex(TEXT("MI_HULL_A_Radiator")) : INDEX_NONE;
			if (Slot != INDEX_NONE && !RadiatorGlow)
			{
				RadiatorGlow = C->CreateDynamicMaterialInstance(Slot);   // her radiators glow with her heat (TickHeat)
			}
			if (M->GetName() == TEXT("SM_SHIP_ASTRA_Aquila"))
			{
				// her own hull is the only one seen from a few metres (through the bridge's windows): the wear map, drawn for
				// hulls seen from hundreds of metres, would lay scratches like cracks and soot streaks a metre wide there.
				// Four times finer, and quieter scratches and streaks, on her paint only.
				for (const TCHAR* Part : {TEXT("MI_HULL_A_Plate"), TEXT("MI_HULL_A_Frame"), TEXT("MI_HULL_A_Livery"), TEXT("MI_HULL_A_Trim"), TEXT("MI_HULL_A_Marking")})
				{
					const int32 S = C->GetMaterialIndex(Part);
					if (S == INDEX_NONE)
					{
						continue;
					}
					if (UMaterialInstanceDynamic* Mid = C->CreateDynamicMaterialInstance(S))
					{
						Mid->SetScalarParameterValue(TEXT("WearScale"), 2.0f);
						Mid->SetScalarParameterValue(TEXT("ScratchAmount"), 0.12f);
						Mid->SetScalarParameterValue(TEXT("StreakAmount"), 0.05f);
						Mid->SetScalarParameterValue(TEXT("DirtBlotch"), 0.12f);
					}
				}
			}
			if (!It->FindComponentByClass<UAstraNavLights>())
			{
				// her running lights (no strobe over the bridge: the Captain looks out of it)
				UAstraNavLights* NL = NewObject<UAstraNavLights>(*It);
				NL->SetupAttachment(It->GetRootComponent());
				NL->RegisterComponent();
				NL->Setup(M->GetName(), M->GetName().Contains(TEXT("MANDATE")), M->GetName() == TEXT("SM_SHIP_ASTRA_Aquila"));
			}
			if (M->GetName() == TEXT("SM_SHIP_ASTRA_Aquila") && !It->FindComponentByClass<UDecalComponent>())
			{
				// her name and hull number on both flanks, forward of amidships where the plating runs flat and
				// vertical (x 150-210 m, 50.5 m out, under the blue livery band; tools/art/hull_markings.py,
				// tools/ue_scripts/make_hull_decals.py)
				if (UMaterialInterface* NameMat = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/ASTRA/Materials/Instances/MI_HULL_Name_Aquila.MI_HULL_Name_Aquila")))
				{
					// the streamer does not see decals made at run time: without this the name stays at its blurriest mip
					if (UTexture2D* Tex = LoadObject<UTexture2D>(nullptr, TEXT("/Game/ASTRA/Materials/Textures/T_HULL_Name_Aquila.T_HULL_Name_Aquila")))
					{
						Tex->SetForceMipLevelsToBeResident(1.0e7f);
					}
					for (const float Side : {-1.f, 1.f})
					{
						UDecalComponent* D = NewObject<UDecalComponent>(*It);
						D->SetupAttachment(It->GetRootComponent());
						D->SetDecalMaterial(NameMat);
						// a decal projects along its X and lays the texture's width along its Z: rolled a quarter turn so
						// the name runs along the hull, read the right way up from outside (bow to stern on the port side)
						D->DecalSize = FVector(400.f, 875.f, 3500.f);   // 8 m deep, 17.5 m high, 70 m long
						D->SetRelativeLocation(FVector(18000.f, Side * 5050.f, -800.f));   // under the livery band
						D->SetRelativeRotation(FRotator(0.f, Side < 0.f ? 90.f : -90.f, 90.f));
						D->SetFadeScreenSize(0.f);
						D->RegisterComponent();
					}
				}
			}
		}
	}
	SetPlanetFill(TEXT("ocean"));
	UE_LOG(LogASTRA, Log, TEXT("[Ship] planet light %s, %d exterior meshes"), PlanetLight ? TEXT("on") : TEXT("missing"), Exterior);
	// New Ravenna's surface zone, and the space sky and sky light it replaces when the Captain goes down
	static const FName TagPlanet(TEXT("ASTRA.Planet.NewRavenna"));
	for (TActorIterator<AActor> It(&InWorld); It; ++It)
	{
		if (It->ActorHasTag(TagPlanet))
		{
			PlanetActors.Add(*It);
		}
		else if (It->ActorHasTag(TagSky))
		{
			SpaceSkyActor = *It;
		}
		else if (It->IsA(ASkyLight::StaticClass()))
		{
			SpaceSkyLight = *It;
		}
	}
	UE_LOG(LogASTRA, Log, TEXT("[Ship] New Ravenna surface zone: %d actors"), PlanetActors.Num());
	CaptureHomeSky();
}

void UAstraShipSubsystem::SetPlanetFill(const FString& T)
{
	// the colour of the light a world throws back, and how much of it (albedo: ice and gas bright, lava dark)
	if (T == TEXT("desert")) { PlanetFill = FLinearColor(1.f, 0.72f, 0.45f); PlanetFillGain = 1.2f; }
	else if (T == TEXT("ice")) { PlanetFill = FLinearColor(0.85f, 0.93f, 1.f); PlanetFillGain = 1.6f; }
	else if (T == TEXT("lava")) { PlanetFill = FLinearColor(1.f, 0.42f, 0.2f); PlanetFillGain = 0.6f; }
	else if (T == TEXT("gas_giant")) { PlanetFill = FLinearColor(1.f, 0.84f, 0.62f); PlanetFillGain = 1.4f; }
	else if (T == TEXT("barren")) { PlanetFill = FLinearColor(0.76f, 0.73f, 0.7f); PlanetFillGain = 0.8f; }
	else { PlanetFill = FLinearColor(0.42f, 0.6f, 1.f); PlanetFillGain = 1.f; }
}

float UAstraShipSubsystem::GetStarLux() const
{
	return Sun && Sun->GetLightComponent() ? Sun->GetLightComponent()->Intensity : 1200.f;
}

FString UAstraShipSubsystem::LightInfo() const
{
	auto One = [](const TCHAR* Name, const ADirectionalLight* L) -> FString
	{
		if (!L || !L->GetLightComponent())
		{
			return FString::Printf(TEXT("%s: none"), Name);
		}
		const ULightComponent* C = L->GetLightComponent();
		return FString::Printf(TEXT("%s: dir %s intensity %.2f visible %d mobility %d channels %d%d%d"), Name, *L->GetActorForwardVector().ToCompactString(),
		                       C->Intensity, C->IsVisible() ? 1 : 0, (int32)C->Mobility, C->LightingChannels.bChannel0, C->LightingChannels.bChannel1,
		                       C->LightingChannels.bChannel2);
	};
	return One(TEXT("star"), Sun) + TEXT(" | ") + One(TEXT("planet"), PlanetLight) + TEXT(" | ") + One(TEXT("fill"), SpaceFill);
}

void UAstraShipSubsystem::AimSpaceFill(const FVector& LookDir, float DeltaTime)
{
	// the fill comes from where the main viewscreen's camera looks from (a little above it, for shape), turning in about a second when
	// the screen cuts to another subject: what the Captain studies on it shows its face, whatever side the star lights
	if (!SpaceFill || LookDir.IsNearlyZero())
	{
		return;
	}
	const FVector Want = (LookDir.GetSafeNormal() - FVector(0.f, 0.f, 0.35f)).GetSafeNormal();
	const FQuat Now = FQuat::Slerp(SpaceFill->GetActorQuat(), Want.ToOrientationQuat(), FMath::Clamp(DeltaTime * 2.5f, 0.f, 1.f));
	if (Now.AngularDistance(SpaceFill->GetActorQuat()) > FMath::DegreesToRadians(0.25f))
	{
		SpaceFill->SetActorRotation(Now);
	}
}

void UAstraShipSubsystem::UpdatePlanetLight(const FVector& SunNow, const FVector Axes[3])
{
	if (!PlanetLight || !SkyMID)
	{
		return;
	}
	FLinearColor P;
	float Radius = 0.f;
	SkyMID->GetVectorParameterValue(FHashedMaterialParameterInfo(TEXT("PlanetDirection")), P);
	SkyMID->GetScalarParameterValue(FHashedMaterialParameterInfo(TEXT("PlanetAngularRadius")), Radius);
	const FVector Dir = (Axes[0] * P.R + Axes[1] * P.G + Axes[2] * P.B).GetSafeNormal();   // ship -> planet (world)
	if (Dir.IsNearlyZero())
	{
		return;
	}
	PlanetDirNow = Dir;
	// how much of its lit face we see (full when the star is behind us), how big it is in the sky; a touch more than
	// physics (x3) so the night side of a hull is not a hole
	const float Phase = 0.5f * (1.f - FVector::DotProduct(SunNow.GetSafeNormal(), Dir));
	const float SunLux = Sun && Sun->GetLightComponent() ? Sun->GetLightComponent()->Intensity : 1200.f;
	const float S = FMath::Sin(FMath::Clamp(Radius, 0.f, 1.2f));
	PlanetLight->SetActorRotation((-Dir).Rotation());
	if (ULightComponent* LC = PlanetLight->GetLightComponent())
	{
		LC->SetIntensity(SunLux * S * S * 0.35f * 3.f * PlanetFillGain * Phase);
		LC->SetLightColor(PlanetFill);
	}
}

void UAstraShipSubsystem::CaptureHomeSky()
{
	// Aurelia as the level has it: every sky parameter except the attitude ones (they follow the ship)
	if (SkyMID)
	{
		TArray<FMaterialParameterInfo> Infos;
		TArray<FGuid> Ids;
		SkyMID->GetAllScalarParameterInfo(Infos, Ids);
		for (const FMaterialParameterInfo& I : Infos)
		{
			float V = 0.f;
			if (SkyMID->GetScalarParameterValue(FHashedMaterialParameterInfo(I.Name), V))
			{
				HomeScalars.Add(I.Name, V);
			}
		}
		Infos.Reset();
		Ids.Reset();
		SkyMID->GetAllVectorParameterInfo(Infos, Ids);
		for (const FMaterialParameterInfo& I : Infos)
		{
			const FString N = I.Name.ToString();
			if (N.StartsWith(TEXT("SkyAxis")) || N == TEXT("SunDirection"))
			{
				continue;
			}
			FLinearColor C;
			if (SkyMID->GetVectorParameterValue(FHashedMaterialParameterInfo(I.Name), C))
			{
				HomeVectors.Add(I.Name, C);
			}
		}
	}
	HomeSunDir0 = SunDir0;
	if (Sun && Sun->GetLightComponent())
	{
		HomeLux = Sun->GetLightComponent()->Intensity;
		HomeKelvin = Sun->GetLightComponent()->Temperature;
	}
	bHomeCaptured = SkyMID != nullptr;
	FAstraSystemLook Home;   // the defaults are Aurelia's
	Systems.Add(Home.Name, Home);
}

FAstraSystemLook UAstraShipSubsystem::MakeLook(const FString& Name, const FString& Star, const FString& Planet, const FString& PlanetName) const
{
	static const TCHAR* Stars[] = {TEXT("red_dwarf"), TEXT("red_dwarf"), TEXT("orange"), TEXT("orange"), TEXT("yellow"), TEXT("blue_white")};
	static const TCHAR* Worlds[] = {TEXT("barren"), TEXT("barren"), TEXT("desert"), TEXT("ice"), TEXT("gas_giant"), TEXT("gas_giant"), TEXT("ocean"), TEXT("lava")};
	auto Valid = [](const FString& V, const TCHAR* const* List, int32 N)
	{
		for (int32 i = 0; i < N; ++i)
		{
			if (V == List[i]) { return true; }
		}
		return false;
	};
	FRandomStream R((int32)GetTypeHash(Name.ToLower()));
	FAstraSystemLook L;
	L.Name = Name;
	const FString DerivedStar = Stars[R.RandHelper(UE_ARRAY_COUNT(Stars))];
	const FString DerivedWorld = Worlds[R.RandHelper(UE_ARRAY_COUNT(Worlds))];
	L.StarClass = Valid(Star, Stars, UE_ARRAY_COUNT(Stars)) ? Star : DerivedStar;
	L.PlanetType = Valid(Planet, Worlds, UE_ARRAY_COUNT(Worlds)) ? Planet : DerivedWorld;
	L.PlanetName = PlanetName.IsEmpty() ? Name + TEXT(" Prime") : PlanetName;
	L.SunWorld = FVector(R.FRandRange(-0.3f, 0.9f), R.FRandRange(-0.9f, 0.9f), R.FRandRange(0.1f, 0.6f));
	L.PlanetWorld = FVector(1.f, R.FRandRange(-0.7f, 0.7f), R.FRandRange(-0.22f, 0.12f));
	L.PlanetSize = L.PlanetType == TEXT("gas_giant") ? R.FRandRange(0.35f, 0.5f) : R.FRandRange(0.16f, 0.3f);
	L.NebulaHue = R.FRandRange(-1.2f, 1.2f);
	L.NebulaSat = R.FRandRange(0.6f, 1.3f);
	L.Seed = R.FRandRange(0.f, 50.f);
	return L;
}

FAstraSystemLook UAstraShipSubsystem::ChartSystem(const FString& InName, const FString& Star, const FString& Planet, const FString& PlanetName)
{
	const FString Name = InName.TrimStartAndEnd();
	for (const auto& KV : Systems)
	{
		if (KV.Key.Equals(Name, ESearchCase::IgnoreCase))
		{
			return KV.Value;
		}
	}
	const FAstraSystemLook L = MakeLook(Name, Star, Planet, PlanetName);
	Systems.Add(Name, L);
	return L;
}

const FAstraSectorSystem* UAstraShipSubsystem::FindSector(const FString& Name) const
{
	return Sector.FindByPredicate([&Name](const FAstraSectorSystem& S) { return S.Name.Equals(Name.TrimStartAndEnd(), ESearchCase::IgnoreCase); });
}

TSharedRef<FJsonObject> UAstraShipSubsystem::SaveJson() const
{
	TSharedRef<FJsonObject> O = MakeShared<FJsonObject>();
	O->SetStringField(TEXT("system"), SystemName);
	TArray<TSharedPtr<FJsonValue>> K, W;
	for (const int32 i : Roster.GetFallen()) { K.Add(MakeShared<FJsonValueNumber>(i)); }
	for (const int32 i : Roster.GetHurt()) { W.Add(MakeShared<FJsonValueNumber>(i)); }
	O->SetArrayField(TEXT("fallen"), K);
	O->SetArrayField(TEXT("wounded"), W);
	TArray<TSharedPtr<FJsonValue>> Care;
	for (const int32 i : Roster.GetHurt())
	{
		const FAstraCrewman& P = Roster.Get()[i];
		TSharedRef<FJsonObject> C = MakeShared<FJsonObject>();
		C->SetNumberField(TEXT("i"), i);
		C->SetStringField(TEXT("injury"), P.Injury);
		C->SetNumberField(TEXT("condition"), P.Condition);
		C->SetNumberField(TEXT("bed"), P.Bed);
		Care.Add(MakeShared<FJsonValueObject>(C));
	}
	O->SetArrayField(TEXT("medbay"), Care);
	O->SetNumberField(TEXT("heat_pct"), HeatPct);
	O->SetBoolField(TEXT("radiators_out"), bRadiatorsOut);
	O->SetNumberField(TEXT("radiator_health"), RadiatorHealth);
	O->SetNumberField(TEXT("coolant_vents"), CoolantVents);
	O->SetStringField(TEXT("casualties"), Roster.Summary());
	O->SetStringField(TEXT("hull_number"), HullNumber);
	return O;
}

void UAstraShipSubsystem::ApplyHullNumber()
{
	if (HullNumber == TEXT("CVC-01") || !GetWorld())
	{
		return;
	}
	const FString Suffix = FString::Printf(TEXT("_%s"), *HullNumber.Right(2));
	UTexture2D* HullTex = LoadObject<UTexture2D>(nullptr, *FString::Printf(TEXT("/Game/ASTRA/Materials/Textures/T_HULL_Name_Aquila%s.T_HULL_Name_Aquila%s"), *Suffix, *Suffix));
	UTexture2D* SignTex = LoadObject<UTexture2D>(nullptr, *FString::Printf(TEXT("/Game/ASTRA/UI/Signage/T_SIGN_Aquila%s.T_SIGN_Aquila%s"), *Suffix, *Suffix));
	for (TActorIterator<AActor> It(GetWorld()); It; ++It)
	{
		// the name on her flanks (the hull's decals)
		TArray<UDecalComponent*> Decals;
		It->GetComponents(Decals);
		for (UDecalComponent* D : Decals)
		{
			UMaterialInterface* M = D->GetDecalMaterial();
			if (HullTex && M && M->GetName().Contains(TEXT("MI_HULL_Name_Aquila")))
			{
				HullTex->SetForceMipLevelsToBeResident(1.0e7f);
				UMaterialInstanceDynamic* Mid = UMaterialInstanceDynamic::Create(M, D);
				Mid->SetTextureParameterValue(TEXT("Marking"), HullTex);
				D->SetDecalMaterial(Mid);
			}
		}
		// the ship's plate over the master display
		TArray<UStaticMeshComponent*> Meshes;
		It->GetComponents(Meshes);
		for (UStaticMeshComponent* C : Meshes)
		{
			for (int32 i = 0; SignTex && i < C->GetNumMaterials(); ++i)
			{
				UMaterialInterface* M = C->GetMaterial(i);
				if (M && M->GetName() == TEXT("MI_SIGN_Aquila"))
				{
					UMaterialInstanceDynamic* Mid = C->CreateDynamicMaterialInstance(i);
					Mid->SetTextureParameterValue(TEXT("ScreenTexture"), SignTex);
				}
			}
		}
	}
	UE_LOG(LogASTRA, Log, TEXT("[Ship] she is the %s now"), *HullNumber);
}

void UAstraShipSubsystem::ResumeFrom(const TSharedPtr<FJsonObject>& Save)
{
	if (!Save.IsValid())
	{
		return;
	}
	TArray<int32> K, W;
	const TArray<TSharedPtr<FJsonValue>>* A = nullptr;
	if (Save->TryGetArrayField(TEXT("fallen"), A)) { for (const auto& V : *A) { K.Add((int32)V->AsNumber()); } }
	if (Save->TryGetArrayField(TEXT("wounded"), A)) { for (const auto& V : *A) { W.Add((int32)V->AsNumber()); } }
	Roster.Restore(K, W);
	if (Save->TryGetArrayField(TEXT("medbay"), A))
	{
		for (const auto& V : *A)
		{
			const TSharedPtr<FJsonObject>* C = nullptr;
			if (V->TryGetObject(C) && C && C->IsValid())
			{
				Roster.RestoreCare((int32)(*C)->GetNumberField(TEXT("i")), (*C)->GetStringField(TEXT("injury")),
				                   (uint8)(*C)->GetNumberField(TEXT("condition")), (int32)(*C)->GetNumberField(TEXT("bed")));
			}
		}
	}
	double Num = 0.0;
	if (Save->TryGetNumberField(TEXT("heat_pct"), Num)) { HeatPct = HeatPrev = FMath::Clamp((float)Num, 0.f, 110.f); }
	if (Save->TryGetNumberField(TEXT("radiator_health"), Num)) { RadiatorHealth = FMath::Clamp((float)Num, 0.25f, 1.f); }
	if (Save->TryGetNumberField(TEXT("coolant_vents"), Num)) { CoolantVents = FMath::Clamp((int32)Num, 0, 3); }
	Save->TryGetBoolField(TEXT("radiators_out"), bRadiatorsOut);
	FString Hull;
	if (Save->TryGetStringField(TEXT("hull_number"), Hull) && !Hull.IsEmpty())
	{
		HullNumber = Hull;
		ApplyHullNumber();
	}
	FString Sys = TEXT("Aurelia");
	Save->TryGetStringField(TEXT("system"), Sys);
	ApplySystem(ChartSystem(Sys));
	LocationName = FString::Printf(TEXT("%s System, on patrol%s"), *Sys,
	                               Sys.Equals(TEXT("Aurelia"), ESearchCase::IgnoreCase) ? TEXT(" near the Janus Gate Aurelia") : TEXT(""));
	ThrottlePct = 30.f;
	SpeedMps = 150.f;
	SetAlert(EAstraAlert::Green);
}

FString UAstraShipSubsystem::KnownSystemsLine() const
{
	TArray<FString> Parts;
	for (const auto& KV : Systems)
	{
		const FAstraSystemLook& L = KV.Value;
		Parts.Add(FString::Printf(TEXT("%s (%s star, %s world %s)%s"), *L.Name, *L.StarClass.Replace(TEXT("_"), TEXT("-")),
		                          *L.PlanetType.Replace(TEXT("_"), TEXT(" ")), *L.PlanetName,
		                          L.Name.Equals(SystemName, ESearchCase::IgnoreCase) ? TEXT(" — we are here") : TEXT("")));
	}
	return FString::Join(Parts, TEXT("; "));
}

void UAstraShipSubsystem::SteerTo(float Heading, float Mark)
{
	InterceptId.Empty();
	TargetHeadingDeg = WrapDeg(Heading);
	TargetMarkDeg = FMath::Clamp(Mark, -60.f, 60.f);
	bTurning = true;
	bAutoHelm = true;
}

void UAstraShipSubsystem::DriveExternally(float Heading, float Mark, float Speed)
{
	HeadingDeg = TargetHeadingDeg = WrapDeg(Heading);
	MarkDeg = TargetMarkDeg = FMath::Clamp(Mark, -89.f, 89.f);
	SpeedMps = Speed;
	bTurning = false;
	UpdateAttitudeVisuals();
}

float UAstraShipSubsystem::HeatFactor() const
{
	const float H = HeatPct / 100.f;
	if (H < 0.7f)
	{
		return 1.f;
	}
	if (H < 0.9f)
	{
		return FMath::Lerp(1.f, 0.8f, (H - 0.7f) / 0.2f);
	}
	return FMath::Lerp(0.8f, 0.55f, FMath::Clamp((H - 0.9f) / 0.1f, 0.f, 1.f));
}

void UAstraShipSubsystem::SetBattleShort(bool bOn)
{
	if (bOn == bBattleShort)
	{
		return;
	}
	bBattleShort = bOn;
	PowerBudget = bOn ? 800.f : 700.f;
	if (!bOn)
	{
		// back inside the normal budget: every allocation above nominal comes down in proportion
		float Sum = 0.f, Over = 0.f;
		for (const auto& KV : PowerPct)
		{
			Sum += KV.Value;
			Over += FMath::Max(0.f, KV.Value - 100.f);
		}
		if (Sum > PowerBudget && Over > 0.f)
		{
			const float K = FMath::Clamp(1.f - (Sum - PowerBudget) / Over, 0.f, 1.f);
			for (auto& KV : PowerPct)
			{
				KV.Value = KV.Value > 100.f ? 100.f + (KV.Value - 100.f) * K : KV.Value;
			}
		}
	}
	Event(bOn ? TEXT("engineering: battle short — the reactor's limits are overridden: 800% of power to allocate, and she runs hot")
	          : TEXT("engineering: the reactor is back inside its limits (700%)"));
}

void UAstraShipSubsystem::TickHeat(float DeltaTime)
{
	if (DeltaTime <= 0.f)
	{
		return;
	}
	float Sum = 0.f;
	for (const auto& KV : PowerPct)
	{
		Sum += KV.Value;
	}
	// what the ship makes by herself: the reactor (by the power drawn), the drive (by the throttle and the engines' power);
	// the battle adds the rest (weapons fired, hits soaked, shields recharging: AddHeat)
	const float Gen = 0.16f * (Sum / 600.f) + 0.2f * (FMath::Abs(ThrottlePct) / 100.f) * PowerFactor(TEXT("engines")) + (bBattleShort ? 0.3f : 0.f);
	// what she sheds: the hull's own glow, plus the radiators, more the hotter she is (retracted: a cruise settles near 15 %,
	// a typical fight near 70 %, a long heavy one beyond 100 %; extended they shed 2.6 times as much, torn ones less)
	const float B = bRadiatorsOut ? 0.5f + (1.3f - 0.5f) * RadiatorHealth : 0.5f;
	HeatPct = FMath::Clamp(HeatPct + (Gen - 0.205f - B * HeatPct / 100.f) * DeltaTime, 0.f, 110.f);
	VentPlumeT = FMath::Max(0.f, VentPlumeT - DeltaTime);
	HeatRate = FMath::FInterpTo(HeatRate, (HeatPct - HeatPrev) / DeltaTime, DeltaTime, 0.5f);
	HeatPrev = HeatPct;
	// the crew hears when she runs hot and when she goes critical (once each, with some hysteresis)
	const int32 Stage = HeatPct >= 90.f ? 2 : (HeatPct >= 70.f ? 1 : 0);
	if (Stage > HeatStage)
	{
		HeatStage = Stage;
		Event(Stage == 2
			? FString::Printf(TEXT("engineering: heat critical, %.0f %% — weapons and shields throttled to %.0f %%, the drive slowed, conduits "
			                       "failing, Main Engineering sweltering (radiators %s, %d coolant vents)%s"), HeatPct, 100.f * HeatFactor(),
			                  bRadiatorsOut ? TEXT("extended") : TEXT("retracted"), CoolantVents,
			                  bRadiatorsOut ? TEXT("") : TEXT("; extending the radiators is Engineering's own call (set_radiators)"))
			: FString::Printf(TEXT("engineering: the ship is running hot, %.0f %% and rising — weapons cadence and shield regeneration "
			                       "start to drop (radiators %s, %d coolant vents)"), HeatPct, bRadiatorsOut ? TEXT("extended") : TEXT("retracted"),
			                  CoolantVents), true);
	}
	else if (HeatStage == 2 && HeatPct < 82.f)
	{
		HeatStage = 1;
	}
	else if (HeatStage >= 1 && HeatPct < 60.f)
	{
		HeatStage = 0;
		Event(FString::Printf(TEXT("engineering: heat back down to %.0f %%, systems nominal"), HeatPct), false);
	}
	// critical: the conduits of the reactor and coolant rooms run past what they carry and give way one after another, the nearest to Main Engineering first;
	// whoever is at the panels is scorched (the heat is the ship's, where it does its harm is the rooms that carry it)
	if (HeatPct >= 92.f)
	{
		ThermalStress += DeltaTime * (1.f + (HeatPct - 92.f) / 6.f) / 22.f;
		if (ThermalStress >= 1.f && Interior.IsReady())
		{
			ThermalStress = 0.f;
			const int32 Room = Interior.PickHeatRoom(ThermalSeq++);
			if (Room != INDEX_NONE)
			{
				FAstraImpactResult R;
				Interior.Overload(Room, 0.55f, R);
				Event(FString::Printf(TEXT("engineering: a power conduit overheated and failed at %s (%s power down)%s"), *Interior.GetMap().Describe(Room), *Interior.SystemsText(Room),
				                      R.People.Num() ? *(FString(TEXT(" — casualties: ")) + FString::Join(R.People, TEXT("; "))) : TEXT("")), true);
			}
		}
	}
	else
	{
		ThermalStress = FMath::Max(0.f, ThermalStress - DeltaTime * 0.05f);
	}
	// the Aquila's radiator panels glow with her heat (dull red when hot, bright when critical)
	if (RadiatorGlow)
	{
		RadiatorGlow->SetScalarParameterValue(TEXT("Intensity"), 28.f * FMath::SmoothStep(0.45f, 1.05f, HeatPct / 100.f) * (bRadiatorsOut ? 1.f : 0.6f));
	}
}

void UAstraShipSubsystem::TestMedbay(const FString& What, int32 N)
{
	if (What.Equals(TEXT("admit"), ESearchCase::IgnoreCase))
	{
		static const TCHAR* Causes[] = {TEXT("hull breach"), TEXT("fire"), TEXT("conduit damage")};
		for (int32 k = 0; k < N; ++k)
		{
			const FString Who = Roster.Casualties(FMath::RandRange(2, 11), 1, 0, CasualtyRng, Causes[FMath::RandRange(0, 2)]);
			UE_LOG(LogASTRA, Log, TEXT("[Medbay] admitted: %s"), *Who);
		}
	}
	else if (What.Equals(TEXT("care"), ESearchCase::IgnoreCase))
	{
		for (int32 m = 0; m < N; ++m)
		{
			TArray<FAstraCrewRoster::FNews> News;
			Roster.Care(1.f, CasualtyRng, News);
			for (const FAstraCrewRoster::FNews& Nw : News)
			{
				UE_LOG(LogASTRA, Log, TEXT("[Medbay] %s"), *Nw.Text);
				Event(Nw.Text, Nw.bReport);
			}
		}
	}
	UE_LOG(LogASTRA, Log, TEXT("[Medbay] %s"), *Roster.Summary());
	SyncWard();
}

TArray<FVector> UAstraShipSubsystem::VisitRouteFor(const AAstraCrewMember* C, int32& OutWaitAt)
{
	// the bridge is the world origin (metres here; deck level 0, the well -0.6, the dais +0.2): from each station out of
	// the bridge's starboard door (the v3 bridge's walks: tools/ue_scripts/bridge3_routes_cpp.py), along
	// Corridor 1-A starboard to the cabin's door (a wait there: the chime), and a step and a half inside the cabin
	TArray<FVector> R;
	auto P = [&R](float X, float Y, float Z = 0.f) { R.Add(FVector(X * 100.f, Y * 100.f, Z)); };
	const FString& S = C->StationId;
	// bridge v3 (data/ship/aquila_bridge.json routes.to_starboard_door): the helm goes round the holo table and up the port stairs
	if (S == TEXT("helm"))
	{
		R.Add(C->GetActorLocation());
		P(5.1f, -2.7f, -60.0f);
		P(3.6f, -3.3f, -60.0f);
		P(3.3f, -4.7f, -60.0f);
		P(2.25f, -4.7f);
		P(0.3f, -5.2f);
		P(-5.5f, -4.6f);
		P(-7.3f, -2.7f);
		P(-7.3f, 2.6f);
		P(-7.7f, 3.9f);
	}
	else if (S == TEXT("ops"))
	{
		R.Add(C->GetActorLocation());
		P(5.1f, 2.7f, -60.0f);
		P(3.6f, 3.3f, -60.0f);
		P(3.3f, 4.7f, -60.0f);
		P(2.25f, 4.7f);
		P(0.3f, 5.2f);
		P(-5.5f, 4.5f);
		P(-7.7f, 3.9f);
	}
	else if (S == TEXT("engineering"))
	{
		R.Add(C->GetActorLocation());
		P(0.3f, 5.2f);
		P(-5.5f, 4.5f);
		P(-7.7f, 3.9f);
	}
	else if (S == TEXT("flight"))
	{
		R.Add(C->GetActorLocation());
		P(-3.2f, 5.0f);
		P(-7.6f, 4.0f);
	}
	else if (S == TEXT("tactical"))
	{
		R.Add(C->GetActorLocation());
		P(-2.4f, 2.6f);
		P(-7.6f, 3.6f);
	}
	else if (S == TEXT("xo"))
	{
		R.Add(C->GetActorLocation());
		P(-0.7f, -2.25f, 20.0f);
		P(-0.95f, -2.4f);
		P(-5.0f, -2.6f);
		P(-7.2f, -2.0f);
		P(-7.2f, 2.0f);
		P(-7.7f, 3.6f);
	}
	else if (S == TEXT("comms"))
	{
		R.Add(C->GetActorLocation());
		P(0.3f, -5.2f);
		P(-5.5f, -4.6f);
		P(-7.3f, -2.7f);
		P(-7.3f, 2.6f);
		P(-7.7f, 3.9f);
	}
	else if (S == TEXT("sensors"))
	{
		R.Add(C->GetActorLocation());
		P(-3.0f, -5.2f);
		P(-7.3f, -2.7f);
		P(-7.3f, 2.6f);
		P(-7.7f, 3.9f);
	}
	else
	{
		// from another deck (the doctor, the Chief): up in the bridge lift, forward along Corridor 1-A port, across the
		// bridge behind the holo table
		P(-18.6f, -3.9f);
		P(-10.0f, -3.9f);
		P(-7.6f, -3.9f);
		P(-7.3f, -2.7f);
		P(-7.3f, 2.6f);
		P(-7.7f, 3.9f);
	}
	P(-9.2f, 3.9f);
	P(-17.9f, 3.9f);
	OutWaitAt = R.Num() - 1;         // 3.2 m short of the cabin's door (it opens at 2.6)
	P(-20.4f, 3.9f);
	P(-23.2f, 3.9f);
	return R;
}

bool UAstraShipSubsystem::StartVisit(const FString& Who, const FString& Why, FString& OutDetail)
{
	const APawn* P = UGameplayStatics::GetPlayerPawn(this, 0);
	AAstraQuarters* Q = nullptr;
	for (TActorIterator<AAstraQuarters> It(GetWorld()); It; ++It)
	{
		Q = *It;
	}
	if (!Q || !Q->IsPawnInside(P) || Q->IsResting())
	{
		OutDetail = TEXT("the Captain is not awake in the quarters");
		return false;
	}
	if (Visitor.IsValid())
	{
		OutDetail = TEXT("someone is already with the Captain");
		return false;
	}
	if (Alert == EAstraAlert::Red)
	{
		OutDetail = TEXT("red alert: every officer is at their station");
		return false;
	}
	AAstraCrewMember* C = AAstraCrewMember::FindByStation(GetWorld(), Who);
	if (!C || C->IsVisiting() || Who.StartsWith(TEXT("patient")) || Who.StartsWith(TEXT("mess")))
	{
		OutDetail = FString::Printf(TEXT("no officer %s free to come"), *Who);
		return false;
	}
	int32 WaitAt = INDEX_NONE;
	const TArray<FVector> Route = VisitRouteFor(C, WaitAt);
	C->Visit(Route, WaitAt, 2.4f);
	Visitor = C;
	VisitReason = Why;
	bVisitAnnounced = false;
	bVisitChimed = false;
	VisitSilentT = 0.f;
	Event(FString::Printf(TEXT("%s has left their station and is on the way to the Captain's quarters"), *C->DisplayName), false);
	OutDetail = TEXT("on the way to the Captain's quarters");
	return true;
}

void UAstraShipSubsystem::EndVisit(const TCHAR* Why, bool bHurry)
{
	if (AAstraCrewMember* V = Visitor.Get())
	{
		Event(V->HasArrived() ? FString::Printf(TEXT("%s has left the Captain's quarters and is going back to their station (%s)"), *V->DisplayName, Why)
		                      : FString::Printf(TEXT("%s turned back before reaching the Captain's quarters (%s)"), *V->DisplayName, Why), false);
		V->Leave(bHurry);
	}
	Visitor.Reset();
}

void UAstraShipSubsystem::TickVisit(float DeltaTime)
{
	AAstraCrewMember* V = Visitor.Get();
	if (!V)
	{
		return;
	}
	bool bCaptainThere = false;
	const APawn* P = UGameplayStatics::GetPlayerPawn(this, 0);
	for (TActorIterator<AAstraQuarters> It(GetWorld()); It; ++It)
	{
		bCaptainThere |= It->IsPawnInside(P) && !It->IsResting();
	}
	if (Alert == EAstraAlert::Red)
	{
		EndVisit(TEXT("action stations"), true);       // back to their station at a jog
		return;
	}
	if (!bCaptainThere)
	{
		EndVisit(TEXT("the Captain left the cabin"));
		return;
	}
	if (V->IsWaiting() && !bVisitChimed)
	{
		// at the cabin's door: the chime inside, then the door opens for them
		bVisitChimed = true;
		if (USoundBase* Chime = LoadObject<USoundBase>(nullptr, TEXT("/Game/ASTRA/Audio/SW_Door_Chime.SW_Door_Chime")))
		{
			UGameplayStatics::PlaySoundAtLocation(this, Chime, FVector(-2190.f, 390.f, 210.f), 0.7f);
		}
	}
	if (V->HasArrived() && !bVisitAnnounced)
	{
		// in the cabin: the crew hears it as an event the officer answers in person (the mind lets them speak first)
		bVisitAnnounced = true;
		Event(FString::Printf(TEXT("%s: %s has come to the Captain's quarters in person and stands just inside the door — %s"),
		                      *V->StationId, *V->DisplayName, *VisitReason), true);
	}
	VisitSilentT = V->IsSpeaking() ? 0.f : VisitSilentT + DeltaTime;
	if (V->HasArrived() && VisitSilentT > 150.f)
	{
		EndVisit(TEXT("nothing more to say"));
	}
}

// ------------------------------------------------------------------------------------------------ abandon ship
AActor* UAstraShipSubsystem::AquilaHullActor() const
{
	for (TActorIterator<AStaticMeshActor> It(GetWorld()); It; ++It)
	{
		const UStaticMeshComponent* C = It->GetStaticMeshComponent();
		if (C && C->GetStaticMesh() && C->GetStaticMesh()->GetName() == TEXT("SM_SHIP_ASTRA_Aquila") && !It->ActorHasTag(TEXT("ASTRA.Interior")))
		{
			return *It;
		}
	}
	return nullptr;
}

bool UAstraShipSubsystem::StartAbandon(bool bOrdered, FString& OutDetail)
{
	if (bShipLost)
	{
		OutDetail = TEXT("the Aquila is already lost");
		return false;
	}
	if (bAbandon)
	{
		OutDetail = FString::Printf(TEXT("the ship is already being abandoned: %.0f s to the reactor breach"), AbandonLeft);
		return true;
	}
	bAbandon = true;
	bAbandonOrdered = bOrdered;
	AbandonLeft = bOrdered ? 110.f : 70.f;
	AbandonT = 0.f;
	AbandonAlarmT = 0.f;
	AbandonCall = 0;
	PodLaunchT = 4.f;
	EvacFrac = 0.f;
	SetAlert(EAstraAlert::Red);
	ThrottlePct = 0.f;                // all stop: the drive is shut down for the evacuation
	if (Visitor.IsValid())
	{
		EndVisit(TEXT("abandon ship"), true);
	}
	for (TActorIterator<AAstraLifepodHatch> It(GetWorld()); It; ++It)
	{
		It->SetState(AAstraLifepodHatch::EState::Boarding);
	}
	Event(FString::Printf(TEXT("ship: ABANDON SHIP — %s. All hands to the lifepods: the main reactor breaches in %d seconds. The "
	                           "Captain's pods are off Corridor 1-A: 1-A on the port side by the lift, 1-B on the starboard side by the "
	                           "Captain's quarters"),
	                      bOrdered ? TEXT("the Captain's order; Engineering is overloading the reactor so the enemy cannot take her")
	                               : TEXT("the main reactor's containment is failing and cannot be held: the Aquila is lost"),
	                      FMath::RoundToInt(AbandonLeft)), true);
	OutDetail = FString::Printf(TEXT("abandon ship: all hands to the lifepods, %.0f s to the reactor breach"), AbandonLeft);
	UE_LOG(LogASTRA, Log, TEXT("[Ship] ABANDON SHIP (%s)"), bOrdered ? TEXT("ordered") : TEXT("reactor failing"));
	return true;
}

bool UAstraShipSubsystem::BoardLifepod(AAstraLifepodHatch* Hatch, APlayerController* PC, bool bHauled)
{
	if (!bAbandon || !Hatch || !PC || CaptainPod.IsValid() || Hatch->GetState() == AAstraLifepodHatch::EState::Gone)
	{
		return false;
	}
	APawn* Me = PC->GetPawn();
	if (!Me || Cast<AAstraFighterPawn>(Me))
	{
		return false;
	}
	FActorSpawnParameters SP;
	SP.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	AAstraLifepod* Pod = GetWorld()->SpawnActor<AAstraLifepod>(Hatch->PodStart(), Hatch->GetActorRotation(), SP);
	if (!Pod)
	{
		return false;
	}
	CaptainPod = Pod;
	CaptainPodName = Hatch->PodName;
	bCaptainHauled = bHauled;
	Hatch->SetState(AAstraLifepodHatch::EState::Gone);
	if (PC->PlayerCameraManager)
	{
		PC->PlayerCameraManager->StartCameraFade(0.f, 1.f, bHauled ? 0.1f : 0.35f, FLinearColor::Black, false, true);
	}
	// through the hatch, into the seat, the harness: then the pod is fired
	const AActor* Hull = AquilaHullActor();
	FVector HullC(-18000.f, 0.f, -4000.f), HullE(40000.f, 7700.f, 5000.f);
	if (Hull)
	{
		Hull->GetActorBounds(false, HullC, HullE);
	}
	const FVector Start = Hatch->PodStart();
	const FVector Dir = Hatch->LaunchDir;
	const FString Name = Hatch->PodName;
	TWeakObjectPtr<APlayerController> WPC(PC);
	TWeakObjectPtr<APawn> WMe(Me);
	TWeakObjectPtr<AAstraLifepod> WPod(Pod);
	FTimerHandle H;
	GetWorld()->GetTimerManager().SetTimer(H, [WPC, WMe, WPod, Start, Dir, HullC, Name]()
	{
		if (!WPC.IsValid() || !WPod.IsValid())
		{
			return;
		}
		WPC->Possess(WPod.Get());
		if (WMe.IsValid())
		{
			WMe->SetActorHiddenInGame(true);
			WMe->SetActorEnableCollision(false);
		}
		WPod->Launch(Start, Dir, HullC, Name);
		if (WPC->PlayerCameraManager)
		{
			WPC->PlayerCameraManager->StartCameraFade(1.f, 0.f, 1.6f, FLinearColor::Black, false, false);
		}
	}, bHauled ? 1.2f : 0.5f, false);
	Event(bHauled ? FString::Printf(TEXT("ship: the Captain did not reach a lifepod in time — Commander Serra hauled the Captain into the "
	                                     "last one, lifepod %s, and it was fired as the reactor went; Serra is in it with the Captain"), *Name)
	              : FString::Printf(TEXT("ship: the Captain is in lifepod %s and it has been fired clear of the Aquila; the crew still "
	                                     "aboard keep going to their pods (the officers now speak to the Captain over the pods' radio)"), *Name), true);
	UE_LOG(LogASTRA, Log, TEXT("[Ship] the Captain boards lifepod %s%s"), *Name, bHauled ? TEXT(" (hauled)") : TEXT(""));
	return true;
}

void UAstraShipSubsystem::HaulCaptain()
{
	APlayerController* PC = UGameplayStatics::GetPlayerController(this, 0);
	APawn* Me = PC ? PC->GetPawn() : nullptr;
	if (!Me || Cast<AAstraFighterPawn>(Me) || CaptainPod.IsValid())
	{
		return;
	}
	AAstraLifepodHatch* Best = nullptr;
	float BestD = TNumericLimits<float>::Max();
	for (TActorIterator<AAstraLifepodHatch> It(GetWorld()); It; ++It)
	{
		const float D = FVector::Dist(It->GetActorLocation(), Me->GetActorLocation());
		if (It->GetState() != AAstraLifepodHatch::EState::Gone && D < BestD)
		{
			BestD = D;
			Best = *It;
		}
	}
	if (Best)
	{
		BoardLifepod(Best, PC, true);
	}
}

void UAstraShipSubsystem::LaunchOtherPod()
{
	const AActor* Hull = AquilaHullActor();
	UStaticMesh* M = LoadObject<UStaticMesh>(nullptr, TEXT("/Game/ASTRA/Kit/Lifepod/SM_POD_Exterior.SM_POD_Exterior"));
	if (!Hull || !M)
	{
		return;
	}
	FVector C, E;
	Hull->GetActorBounds(false, C, E);
	// out of her flanks, from bow to stern, well inside the plating: they appear as they clear it
	const float Side = FMath::RandBool() ? 1.f : -1.f;
	const FVector P(C.X + FMath::FRandRange(-0.75f, 0.5f) * E.X, C.Y + Side * E.Y * 0.55f, C.Z + FMath::FRandRange(-0.2f, 0.5f) * E.Z);
	FActorSpawnParameters SP;
	SP.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	AStaticMeshActor* A = GetWorld()->SpawnActor<AStaticMeshActor>(P, FRotator(0.f, Side * 90.f + 180.f, 0.f), SP);
	if (!A)
	{
		return;
	}
	A->SetMobility(EComponentMobility::Movable);
	A->GetStaticMeshComponent()->SetStaticMesh(M);
	A->GetStaticMeshComponent()->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	A->GetStaticMeshComponent()->SetLightingChannels(true, true, false);
	UAstraNavLights* NL = NewObject<UAstraNavLights>(A);
	NL->SetupAttachment(A->GetRootComponent());
	NL->RegisterComponent();
	NL->AddBeacon(FVector(-90.f, 0.f, 185.f));
	FDriftPod D;
	D.Actor = A;
	D.Vel = FVector(FMath::FRandRange(-5.f, 5.f), Side * FMath::FRandRange(26.f, 44.f), FMath::FRandRange(3.f, 15.f)) * 100.f;
	D.Spin = FRotator(FMath::FRandRange(-9.f, 9.f), FMath::FRandRange(-9.f, 9.f), FMath::FRandRange(-14.f, 14.f));
	DriftPods.Add(D);
}

void UAstraShipSubsystem::DarkenAquila()
{
	// the hulk: her plating burnt dark, embers in the wounds; her lights, her name and her running lights gone
	for (TActorIterator<AStaticMeshActor> It(GetWorld()); It; ++It)
	{
		UStaticMeshComponent* C = It->GetStaticMeshComponent();
		const FString N = C && C->GetStaticMesh() ? C->GetStaticMesh()->GetName() : FString();
		if ((N != TEXT("SM_SHIP_ASTRA_Aquila") && N != TEXT("SM_SHIP_ASTRA_AquilaBridgeBlock")) || It->ActorHasTag(TEXT("ASTRA.Interior")))
		{
			continue;
		}
		for (int32 i = 0; i < C->GetNumMaterials(); ++i)
		{
			if (UMaterialInstanceDynamic* M = C->CreateDynamicMaterialInstance(i))
			{
				M->SetVectorParameterValue(TEXT("Tint"), FLinearColor(0.025f, 0.023f, 0.022f));
				M->SetVectorParameterValue(TEXT("EmissiveColor"), FLinearColor(0.9f, 0.3f, 0.08f));
				M->SetScalarParameterValue(TEXT("Intensity"), FMath::FRandRange(0.f, 3.f));
			}
		}
		TArray<UActorComponent*> Gone;
		for (UActorComponent* Comp : It->GetComponents())
		{
			if (Cast<UAstraNavLights>(Comp) || Cast<UDecalComponent>(Comp))
			{
				Gone.Add(Comp);
			}
		}
		for (UActorComponent* Comp : Gone)
		{
			Comp->DestroyComponent();
		}
	}
	RadiatorGlow = nullptr;
}

void UAstraShipSubsystem::TickAbandon(float DeltaTime)
{
	for (FDriftPod& D : DriftPods)
	{
		if (AActor* A = D.Actor.Get())
		{
			A->SetActorLocationAndRotation(A->GetActorLocation() + D.Vel * DeltaTime, A->GetActorRotation() + D.Spin * DeltaTime);
		}
	}
	if (!bAbandon)
	{
		return;
	}
	UAstraBattleSubsystem* Battle = GetWorld()->GetSubsystem<UAstraBattleSubsystem>();
	if (!bShipLost)
	{
		AbandonLeft -= DeltaTime;
		AbandonT += DeltaTime;
		EvacFrac = 1.f - FMath::Exp(-AbandonT / 32.f);
		if (!CaptainPod.IsValid() && (AbandonAlarmT -= DeltaTime) <= 0.f)
		{
			// the general alarm, over and over while the Captain is still aboard
			AbandonAlarmT = 8.f;
			if (USoundBase* A = LoadObject<USoundBase>(nullptr, TEXT("/Game/ASTRA/Audio/SW_Abandon_Alarm.SW_Abandon_Alarm")))
			{
				UGameplayStatics::PlaySound2D(this, A, 0.5f);
			}
		}
		if ((PodLaunchT -= DeltaTime) <= 0.f && DriftPods.Num() < 60)
		{
			PodLaunchT = FMath::FRandRange(0.8f, 3.f);
			LaunchOtherPod();
		}
		static const float Calls[] = {60.f, 30.f, 10.f};
		if (AbandonCall < 3 && AbandonLeft <= Calls[AbandonCall])
		{
			Event(FString::Printf(TEXT("ship: %d seconds to the reactor breach — %d%% of the crew are in the lifepods%s"), FMath::RoundToInt(Calls[AbandonCall]),
			                      FMath::RoundToInt(EvacFrac * 100.f), CaptainPod.IsValid() ? TEXT("") : TEXT("; the Captain is still aboard")), true);
			++AbandonCall;
		}
		if (AbandonLeft <= 0.f)
		{
			HaulCaptain();
			bShipLost = true;
			LostT = 0.f;
			LossStage = 0;
			const AActor* Hull = AquilaHullActor();
			FVector C(-18000.f, 0.f, -4000.f), E(40000.f, 7700.f, 5000.f);
			if (Hull)
			{
				Hull->GetActorBounds(false, C, E);
			}
			if (Battle)
			{
				Battle->AquilaBlasts(C, E);
			}
			ThrottlePct = 0.f;
			SpeedMps = 0.f;
		}
		return;
	}
	LostT += DeltaTime;
	if (LossStage == 0 && LostT >= 4.f)
	{
		// the reactor (Main Engineering, Deck 7): the breach
		LossStage = 1;
		if (Battle)
		{
			Battle->AquilaBreach(FVector(-34000.f, 0.f, -4800.f));
		}
		DarkenAquila();
		int32 Alive = 0;
		for (const FAstraCrewman& P : Roster.Get())
		{
			Alive += P.Status != 2 ? 1 : 0;
		}
		const int32 Lost = FMath::RoundToInt((1.f - EvacFrac) * Alive * 0.9f);
		LostSummary = Roster.LostWithShip(Lost, CasualtyRng);
		Event(FString::Printf(TEXT("ship: the Aquila's main reactor has breached — she is gone. %d%% of her crew got off in the lifepods; %d did not%s"),
		                      FMath::RoundToInt(EvacFrac * 100.f), Lost, LostSummary.IsEmpty() ? TEXT("") : *FString::Printf(TEXT(" (%s)"), *LostSummary)), true);
		for (TActorIterator<AAstraLifepodHatch> It(GetWorld()); It; ++It)
		{
			It->SetState(AAstraLifepodHatch::EState::Gone);
		}
	}
	if (LossStage == 1 && LostT >= 5.6f)
	{
		LossStage = 2;
		if (AAstraLifepod* Pod = CaptainPod.Get())
		{
			Pod->FeelBreach(1.f);
		}
	}
	if (LossStage == 2 && LostT >= 18.f)
	{
		// the story takes it from here: who finds the Captain's pod, and what follows (the mind's aftermath)
		LossStage = 3;
		const FString Friends = Battle ? Battle->ForcesLine(true) : FString();
		const FString Foes = Battle ? Battle->ForcesLine(false) : FString();
		const APawn* Me = UGameplayStatics::GetPlayerPawn(this, 0);
		const FString Where = CaptainPod.IsValid() ? FString::Printf(TEXT("the Captain is adrift in lifepod %s with its distress beacon on%s"), *CaptainPodName,
		                                                              bCaptainHauled ? TEXT(", hauled into it by Commander Serra at the last moment") : TEXT(""))
		                    : Cast<AAstraFighterPawn>(Me) ? FString(TEXT("the Captain was flying Eagle (a Falcon of Alpha) and is still out there, with nowhere to land"))
		                                                  : FString(TEXT("the Captain got off the ship"));
		Event(FString::Printf(TEXT("director: the Aquila is lost — %s in the %s system; %d%% of her crew got off in some %d lifepods%s; %s; "
		                           "still in the fight: %s; the Mandate: %s"),
		                      bAbandonOrdered ? TEXT("abandoned on the Captain's order and scuttled (reactor overload)") : TEXT("her reactor's containment failed"),
		                      *SystemName, FMath::RoundToInt(EvacFrac * 100.f), DriftPods.Num() + 1,
		                      LostSummary.IsEmpty() ? TEXT("") : *FString::Printf(TEXT(", lost with her: %s"), *LostSummary), *Where,
		                      Friends.IsEmpty() ? TEXT("no ASTRA warship") : *Friends, Foes.IsEmpty() ? TEXT("no ship left in the system") : *Foes), false);
	}
}

bool UAstraShipSubsystem::IsCaptainInMess() const
{
	const APawn* P = UGameplayStatics::GetPlayerPawn(this, 0);
	for (TActorIterator<AAstraHangar> It(GetWorld()); It; ++It)
	{
		if (It->IsPawnInMess(P))
		{
			return true;
		}
	}
	return false;
}

void UAstraShipSubsystem::SyncMess()
{
	// the off-duty watch at the tables: fit people from all over the ship, a new watch every half hour (never while the
	// Captain is among them); a place whose diner has been hurt or killed goes to someone else
	UWorld* World = GetWorld();
	if (!World || Roster.Get().Num() == 0)
	{
		return;
	}
	TArray<AAstraCrewMember*> Seats;
	for (TActorIterator<AAstraCrewMember> It(World); It; ++It)
	{
		if (It->StationId.StartsWith(TEXT("mess")) && It->StationId != TEXT("mess_cook"))
		{
			Seats.Add(*It);
		}
	}
	Seats.Sort([](const AAstraCrewMember& A, const AAstraCrewMember& B)
	{
		return FCString::Atoi(*A.StationId.Mid(4)) < FCString::Atoi(*B.StationId.Mid(4));
	});
	const bool bCaptainHere = IsCaptainInMess();
	const int32 Watch = int32(World->GetTimeSeconds() / 1800.0);
	if (Watch != MessWatch && !bCaptainHere)
	{
		MessWatch = Watch;
		MessDiners.Init(INDEX_NONE, Seats.Num());
	}
	MessDiners.SetNum(Seats.Num());
	FRandomStream R(7700 + FMath::Max(MessWatch, 0) * 131 + Roster.GetFallen().Num());
	const TArray<FAstraCrewman>& People = Roster.Get();
	for (int32 s = 0; s < Seats.Num(); ++s)
	{
		int32& Who = MessDiners[s];
		if (Who >= 0 && People[Who].Status == 0)
		{
			continue;
		}
		Who = INDEX_NONE;
		for (int32 Try = 0; Try < 400 && Who < 0; ++Try)
		{
			const int32 i = R.RandHelper(People.Num());
			if (People[i].Status == 0 && !MessDiners.Contains(i))
			{
				Who = i;
			}
		}
		if (Who >= 0)
		{
			const FAstraCrewman& M = People[Who];
			Seats[s]->DisplayName = M.Name();
			if (Seats[s]->bFemaleBody != M.bFemale)
			{
				Seats[s]->bFemaleBody = M.bFemale;
				Seats[s]->SetBody(M.bFemale);
			}
			Seats[s]->SetUniformDept(M.Dept);
		}
	}
}

void UAstraShipSubsystem::SyncWard()
{
	if (WardRev == Roster.Version() || !GetWorld())
	{
		return;
	}
	WardRev = Roster.Version();
	for (TActorIterator<AAstraPatient> It(GetWorld()); It; ++It)
	{
		const int32 i = Roster.InBed(It->BedNumber() - 1);
		if (i >= 0)
		{
			const FAstraCrewman& P = Roster.Get()[i];
			It->SetOccupant(P.Name(), P.bFemale, P.Condition);
		}
		else if (It->IsOccupied())
		{
			It->SetEmpty();
		}
	}
}

FString UAstraShipSubsystem::CaptainAboard() const
{
	if (const UAstraBoardSubsystem* Boarding = GetWorld() ? GetWorld()->GetSubsystem<UAstraBoardSubsystem>() : nullptr; Boarding && Boarding->CaptainAway())
	{
		return Boarding->CaptainWhereText();               // ABBORDAGGI: he went with the marines in a boat (the troop bay, or the other ship's decks): not on the Aquila's
	}
	if (!CaptainPlanetside.IsEmpty())
	{
		return CaptainPlanetside;
	}
	const APawn* P = UGameplayStatics::GetPlayerPawn(this, 0);
	if (P)
	{
		for (TActorIterator<AAstraHangar> It(GetWorld()); It; ++It)
		{
			if (It->IsPawnInEngineering(P))
			{
				return TEXT("in Main Engineering (Deck 7), face to face with Chief Okonkwo and the engineering watch; the XO has the conn "
				            "on the bridge and the bridge officers speak by intercom");
			}
			if (It->IsPawnInMess(P))
			{
				return TEXT("in the Mess Hall (Deck 4) among the off-duty crew at their tables: they can hear and answer the Captain; "
				            "the XO has the conn on the bridge and the bridge officers speak by intercom");
			}
			if (It->IsPawnInBerths(P))
			{
				return TEXT("in Crew Berthing (Deck 4), in the dim aisle between the racks where the Red watch sleeps (two ratings "
				            "who cannot sleep sit at the table aft); the XO has the conn and the bridge officers speak by intercom, softly");
			}
			if (It->IsPawnInMedbay(P))
			{
				return TEXT("in the Medbay (Deck 6), among the wounded, face to face with Dr. Lindqvist and the medical staff; the "
				            "patients in their beds can hear and answer the Captain; the XO has the conn on the bridge and the bridge "
				            "officers speak by intercom");
			}
		}
	}
	for (TActorIterator<AAstraQuarters> It(GetWorld()); It; ++It)
	{
		if (It->IsResting())
		{
			return TEXT("asleep in the Captain's quarters (Deck 1, behind the bridge): the XO has the conn and wakes the Captain only "
			            "for something important");
		}
		if (It->IsPawnInside(P))
		{
			return TEXT("in the Captain's quarters (Deck 1, behind the bridge), off the bridge: the XO has the conn; the bridge "
			            "officers speak by intercom");
		}
	}
	// in a lift: the car and where it is (a shaft runs through many decks)
	const UAstraLiftSubsystem* Lifts = GetWorld()->GetSubsystem<UAstraLiftSubsystem>();
	const FVector Feet = P ? P->GetActorLocation() - FVector(0.f, 0.f, Cast<ACharacter>(P) ? Cast<ACharacter>(P)->GetDefaultHalfHeight() : 90.f) : FVector::ZeroVector;
	FString LiftPlace;
	int32 LiftDeck = 0;
	if (Lifts && P && Lifts->CaptainPlace(Feet, LiftPlace, LiftDeck))
	{
		return FString::Printf(TEXT("in a lift car (%s), away from the bridge: the XO has the conn; the bridge officers speak by intercom"), *LiftPlace);
	}
	// anywhere else aboard: the compartment of the ship's plan (the bridge is one of them)
	if (const FAstraPlanCompartment* Comp = PlanCompartmentOf(GetWorld(), P); Comp && Comp->Kind != TEXT("bridge"))
	{
		const int32 Deck = Comp->Kind == TEXT("lift") && Lifts ? FMath::Max(Lifts->DeckNearZ(Feet.Z), 1) : Comp->Deck;
		FString PlanDeck;
		if (const UAstraShipPlan* Plan = GetWorld()->GetSubsystem<UAstraShipPlan>())
		{
			for (const FAstraPlanDeck& D : Plan->GetDecks())
			{
				if (D.Id == Deck) { PlanDeck = D.Name; }
			}
		}
		return FString::Printf(TEXT("in the %s (Deck %d%s, section %s), away from the bridge: the XO has the conn; the bridge officers speak "
		                            "by intercom"), *PlanRoomName(*Comp), Deck, PlanDeck.IsEmpty() ? TEXT("") : *(TEXT(" · ") + PlanDeck),
		                       *Comp->Section);
	}
	if (P && P->GetActorLocation().Z < -3000.f)
	{
		return TEXT("on the flight deck (Deck 9), away from the bridge: the XO has the conn; the Captain speaks by intercom");
	}
	return TEXT("on the bridge");
}

FString UAstraShipSubsystem::CaptainLocatorText() const
{
	if (const UAstraBoardSubsystem* Boarding = GetWorld() ? GetWorld()->GetSubsystem<UAstraBoardSubsystem>() : nullptr; Boarding && Boarding->CaptainAway())
	{
		return FString::Printf(TEXT("the Captain's badge: %s"), *Boarding->CaptainWhereText());
	}
	if (!CaptainPlanetside.IsEmpty())
	{
		return FString::Printf(TEXT("the Captain's badge: planetside (%s), on the surface link"), *CaptainPlanetside);
	}
	const APawn* P = UGameplayStatics::GetPlayerPawn(this, 0);
	if (P && !P->IsA<ACharacter>())
	{
		const UAstraBattleSubsystem* B = GetWorld()->GetSubsystem<UAstraBattleSubsystem>();
		const FString Fly = B ? B->PilotSummary() : FString();
		return FString::Printf(TEXT("the Captain's badge: in the cockpit of a Falcon (Eagle), off the ship's internal net%s. The beam does not lock through a "
		                            "cockpit in flight: the deck's recovery guidance brings her aboard (Flight Control, eagle_recover), then he is on the flight deck"),
		                       Fly.IsEmpty() ? TEXT("") : *(TEXT(": ") + Fly));
	}
	return FString::Printf(TEXT("the Captain's badge: %s, on foot, on the ship's internal net"), *CaptainPlace());
}

FString UAstraShipSubsystem::CaptainPlace() const
{
	if (const UAstraBoardSubsystem* Boarding = GetWorld() ? GetWorld()->GetSubsystem<UAstraBoardSubsystem>() : nullptr; Boarding && Boarding->CaptainAway())
	{
		return TEXT("AWAY · WITH THE MARINES");
	}
	if (!CaptainPlanetside.IsEmpty())
	{
		return TEXT("PLANETSIDE");
	}
	const APawn* P = UGameplayStatics::GetPlayerPawn(this, 0);
	if (P && !P->IsA<ACharacter>())
	{
		return TEXT("FLIGHT · IN A FALCON");
	}
	for (TActorIterator<AAstraHangar> It(GetWorld()); It && P; ++It)
	{
		if (It->IsPawnInEngineering(P)) { return TEXT("DECK 7 · MAIN ENGINEERING"); }
		if (It->IsPawnInMess(P)) { return TEXT("DECK 4 · MESS HALL"); }
		if (It->IsPawnInBerths(P)) { return TEXT("DECK 4 · CREW BERTHING"); }
		if (It->IsPawnInMedbay(P)) { return TEXT("DECK 6 · MEDBAY"); }
		if (It->IsPawnInHangar(P)) { return TEXT("DECK 9 · FLIGHT DECK"); }
	}
	for (TActorIterator<AAstraQuarters> It(GetWorld()); It && P; ++It)
	{
		if (It->IsPawnInside(P)) { return TEXT("DECK 1 · CAPTAIN'S QUARTERS"); }
	}
	// in a lift: the car and the deck it is at, or where it is going ("DECK 7 · SERVICE LIFT 1"); a shaft runs through many decks, so its compartment cannot say which
	const UAstraLiftSubsystem* Lifts = GetWorld() ? GetWorld()->GetSubsystem<UAstraLiftSubsystem>() : nullptr;
	const FVector Feet = P ? P->GetActorLocation() - FVector(0.f, 0.f, Cast<ACharacter>(P) ? Cast<ACharacter>(P)->GetDefaultHalfHeight() : 90.f) : FVector::ZeroVector;
	FString InLift;
	int32 LiftDeck = 0;
	if (Lifts && P && Lifts->CaptainPlace(Feet, InLift, LiftDeck))
	{
		return InLift;
	}
	// anywhere else aboard: the compartment of the ship's plan, as the signs say it ("DECK 4 · MESS CONCOURSE · SECTION B")
	if (const FAstraPlanCompartment* Comp = PlanCompartmentOf(GetWorld(), P))
	{
		if (Comp->Kind == TEXT("bridge"))
		{
			return TEXT("BRIDGE");
		}
		const int32 Deck = Comp->Kind == TEXT("lift") && Lifts ? FMath::Max(Lifts->DeckNearZ(Feet.Z), 1) : Comp->Deck;
		return FString::Printf(TEXT("DECK %d · %s · SECTION %s"), Deck, *PlanRoomName(*Comp).ToUpper(), *Comp->Section);
	}
	if (P && P->GetActorLocation().Z < -3000.f)
	{
		return TEXT("DECK 9 · FLIGHT DECK");
	}
	// the bridge proper spans about 20 m around its centre; beyond it, the corridors of Deck 1
	return (P && FMath::Abs(P->GetActorLocation().X) < 1000.f && FMath::Abs(P->GetActorLocation().Y) < 700.f) ? TEXT("BRIDGE")
	                                                                                                          : TEXT("DECK 1 · CORRIDORS");
}

FString UAstraShipSubsystem::GetViewscreenDescription() const
{
	return Viewscreen ? Viewscreen->Describe() : FString(TEXT("off (no viewscreen)"));
}

TSharedRef<FJsonObject> UAstraShipSubsystem::CaptainContext() const
{
	TSharedRef<FJsonObject> C = MakeShared<FJsonObject>();
	const FString Where = CaptainPlace();
	FString Place = Where.Contains(TEXT("·")) ? Where.RightChop(Where.Find(TEXT("·")) + 1).TrimStartAndEnd() : Where;
	if (Place.Contains(TEXT("·")))
	{
		Place = Place.Left(Place.Find(TEXT("·"))).TrimStartAndEnd();       // "MESS CONCOURSE · SECTION B": the room
	}
	Place = Place.ToLower().Replace(TEXT("'"), TEXT("")).Replace(TEXT("("), TEXT("")).Replace(TEXT(")"), TEXT("")).Replace(TEXT(" "), TEXT("_"));
	C->SetStringField(TEXT("place"), Place);                                // "bridge", "captains_quarters", "flight_deck", "mess_concourse"…
	C->SetStringField(TEXT("place_name"), Where);
	const APawn* P = UGameplayStatics::GetPlayerPawn(this, 0);
	if (const FAstraPlanCompartment* Comp = PlanCompartmentOf(GetWorld(), P))
	{
		// where a fire, a breach, a team is, against where the Captain is (in a lift's shaft, the deck of his car or of the floor at his feet)
		const UAstraLiftSubsystem* Lifts = GetWorld()->GetSubsystem<UAstraLiftSubsystem>();
		const FVector Feet = P ? P->GetActorLocation() - FVector(0.f, 0.f, Cast<ACharacter>(P) ? Cast<ACharacter>(P)->GetDefaultHalfHeight() : 90.f) : FVector::ZeroVector;
		FString Unused;
		int32 Deck = Comp->Deck;
		if (Lifts && !Lifts->CaptainPlace(Feet, Unused, Deck) && Comp->Kind == TEXT("lift"))
		{
			Deck = FMath::Max(Lifts->DeckNearZ(Feet.Z), 1);
		}
		C->SetNumberField(TEXT("deck"), Deck);
		C->SetStringField(TEXT("section"), Comp->Section);
	}
	const APlayerCameraManager* Cam = UGameplayStatics::GetPlayerCameraManager(this, 0);
	FString Pawn = TEXT("on_foot");
	if (CaptainPod.IsValid()) { Pawn = TEXT("pod"); }
	else if (P && !P->IsA<ACharacter>()) { Pawn = TEXT("falcon"); }
	else if (const AASTRAPlayerController* PC = P ? Cast<AASTRAPlayerController>(P->GetController()) : nullptr; PC && PC->IsSeated()) { Pawn = TEXT("seated"); }
	C->SetStringField(TEXT("pawn"), Pawn);
	// who hears the Captain's voice in the room: near enough, and no wall or closed door between
	TArray<TSharedPtr<FJsonValue>> Ear;
	FString Facing;
	float BestAngle = 22.f;
	if (Cam && Pawn != TEXT("falcon") && Pawn != TEXT("pod"))
	{
		const FVector Eye = Cam->GetCameraLocation();
		const FVector Look = Cam->GetCameraRotation().Vector();
		for (TActorIterator<AAstraCrewMember> It(GetWorld()); It; ++It)
		{
			if (It->StationId.IsEmpty() || It->IsHidden())
			{
				continue;
			}
			const FVector Head = It->GetActorLocation() + FVector(0.f, 0.f, It->Posture == EAstraCrewPosture::Standing ? 70.f : 30.f);
			const float Dist = FVector::Dist(Eye, Head);
			if (Dist > 1600.f || !It->CanBeHeardFrom(Eye, P))
			{
				continue;                  // too far, or a wall, a door, a bulkhead between them
			}
			Ear.Add(MakeShared<FJsonValueString>(It->StationId));
			const float Angle = FMath::RadiansToDegrees(FMath::Acos(FMath::Clamp(FVector::DotProduct(Look, (Head - Eye).GetSafeNormal()), -1.f, 1.f)));
			if (Dist < 1000.f && Angle < BestAngle)
			{
				BestAngle = Angle;
				Facing = It->StationId;
			}
		}
	}
	C->SetArrayField(TEXT("in_earshot"), Ear);
	if (Cam && Pawn != TEXT("falcon") && Pawn != TEXT("pod"))
	{
		// the people around the Captain, as VITA knows them (who they are, what they are doing): for the mind of the person spoken to
		if (const UAstraLifeSubsystem* Life = GetWorld()->GetSubsystem<UAstraLifeSubsystem>())
		{
			C->SetArrayField(TEXT("people"), Life->ListenersJson(Cam->GetCameraLocation(), Cam->GetCameraRotation().Vector(), 6));
		}
	}
	if (Facing.IsEmpty()) { C->SetField(TEXT("facing"), MakeShared<FJsonValueNull>()); }
	else { C->SetStringField(TEXT("facing"), Facing); }
	if (ChannelParty.IsEmpty())
	{
		C->SetField(TEXT("channel"), MakeShared<FJsonValueNull>());
	}
	else
	{
		TSharedRef<FJsonObject> Ch = MakeShared<FJsonObject>();
		Ch->SetStringField(TEXT("party"), ChannelParty);
		Ch->SetBoolField(TEXT("open"), true);
		Ch->SetBoolField(TEXT("muted"), false);
		C->SetObjectField(TEXT("channel"), Ch);
	}
	// in a lift car: which, where it is, the stops it serves (the ship's computer takes the ride, docs/ASCENSORI.md)
	if (const UAstraLiftSubsystem* L = GetWorld() ? GetWorld()->GetSubsystem<UAstraLiftSubsystem>() : nullptr)
	{
		if (const TSharedPtr<FJsonObject> J = L->ContextJson(); J.IsValid())
		{
			C->SetObjectField(TEXT("lift"), J);
		}
	}
	return C;
}

void UAstraShipSubsystem::Event(const FString& Text, bool bReport)
{
	UE_LOG(LogASTRA, Log, TEXT("[Event]%s %s"), bReport ? TEXT(" (report)") : TEXT(""), *Text);
	// the comms channel: a hail opens it ("transmission: T-21 — …"), closing it ends it
	FString Party;
	if (Text.StartsWith(TEXT("transmission: ")) && Text.Mid(14).Split(TEXT(" — "), &Party, nullptr))
	{
		ChannelParty = Party.TrimStartAndEnd();
	}
	else if (Text.StartsWith(TEXT("comms: channel closed")) || Text.StartsWith(TEXT("comms: the Mandate cut the channel")))
	{
		ChannelParty.Reset();
	}
	RecentEvents.Add(Text);
	if (RecentEvents.Num() > 16)
	{
		RecentEvents.RemoveAt(0);
	}
	OnShipEvent.Broadcast(Text, bReport);
}

const FAstraContact* UAstraShipSubsystem::FindContact(const FString& Id) const
{
	return Contacts.FindByPredicate([&Id](const FAstraContact& C) { return C.Id.Equals(Id, ESearchCase::IgnoreCase); });
}

void UAstraShipSubsystem::SetAlert(EAstraAlert NewAlert)
{
	if (NewAlert == Alert)
	{
		return;
	}
	Alert = NewAlert;
	AlertTime = 0.f;
	PlayAlertSound(NewAlert);
	OnAlertChanged.Broadcast(NewAlert);
}

bool UAstraShipSubsystem::ApplyCommand(const FString& Name, const TSharedPtr<FJsonObject>& Args, FString& OutDetail)
{
	{
		FString ArgsText;
		if (Args.IsValid())
		{
			const TSharedRef<TJsonWriter<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>> W = TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&ArgsText);
			FJsonSerializer::Serialize(Args.ToSharedRef(), W);
		}
		FAstraTimeline::Record(TEXT("cmd"), FString::Printf(TEXT("%s %s"), *Name, *ArgsText.Left(300)));
	}
	// the ship's computer rides the Captain's lift car where he asked to go (docs/ASCENSORI.md)
	if (Name == TEXT("lift_go"))
	{
		UAstraLiftSubsystem* L = GetWorld() ? GetWorld()->GetSubsystem<UAstraLiftSubsystem>() : nullptr;
		return L ? L->GoByVoice(Args, OutDetail) : false;
	}
	// the bridge stations' persistent modes (docs/ARCHITETTURA.md §4)
	if (Name == TEXT("station"))
	{
		UAstraStationsSubsystem* St = GetWorld() ? GetWorld()->GetSubsystem<UAstraStationsSubsystem>() : nullptr;
		FString By;
		if (Args.IsValid())
		{
			Args->TryGetStringField(TEXT("by"), By);
		}
		return St ? St->SetMode(Args, By.IsEmpty() ? TEXT("officer") : By, OutDetail) : false;
	}
	// ABBORDAGGI: a boarding and the marines' orders are the board subsystem's
	if (Name == TEXT("boarding") || Name == TEXT("board_ship") || Name == TEXT("marine_order") || Name == TEXT("lockdown") || Name == TEXT("issue_weapon"))
	{
		UAstraBoardSubsystem* Board = GetWorld() ? GetWorld()->GetSubsystem<UAstraBoardSubsystem>() : nullptr;
		if (!Board)
		{
			OutDetail = TEXT("the ship's marines are not available");
			return false;
		}
		return Board->HandleCommand(Name, Args, OutDetail);
	}
	if (!Args.IsValid())
	{
		OutDetail = TEXT("invalid arguments");
		return false;
	}
	UAstraBattleSubsystem* Battle = GetWorld()->GetSubsystem<UAstraBattleSubsystem>();
	auto Num = [&Args](const TCHAR* K, double Def = 0.0) { double V = Def; Args->TryGetNumberField(K, V); return V; };
	auto Str = [&Args](const TCHAR* K) { FString V; Args->TryGetStringField(K, V); return V; };

	if (Name == TEXT("transit_gate"))
	{
		return Battle ? Battle->BeginGateRun(Args, OutDetail) : false;
	}
	if (Name == TEXT("standing_orders"))
	{
		// the mind keeps the Captain's standing orders; the datapad shows them
		StandingOrders.Reset();
		const TArray<TSharedPtr<FJsonValue>>* L = nullptr;
		if (Args.IsValid() && Args->TryGetArrayField(TEXT("orders"), L))
		{
			for (const TSharedPtr<FJsonValue>& V : *L)
			{
				StandingOrders.Add(V->AsString());
			}
		}
		OutDetail = FString::Printf(TEXT("%d standing order(s) on the Captain's datapad"), StandingOrders.Num());
		return true;
	}
	if (Name == TEXT("log_entry"))
	{
		// the Captain dictated the log: the chair's console takes it (a chirp), the ship's record keeps it
		if (USoundBase* Chirp = LoadObject<USoundBase>(nullptr, TEXT("/Game/ASTRA/Audio/SW_Console_Chirp.SW_Console_Chirp")))
		{
			UGameplayStatics::PlaySound2D(GetWorld(), Chirp, 0.5f, 0.92f);
		}
		Event(TEXT("log: captain's log entry recorded"), false);
		OutDetail = TEXT("captain's log entry recorded");
		return true;
	}
	if (Name == TEXT("holo_display"))
	{
		const FString M = Str(TEXT("mode")).ToLower();
		if (M != TEXT("tactical") && M != TEXT("sector") && M != TEXT("ship"))
		{
			OutDetail = TEXT("the holo table shows the tactical plot, the sector map or the ship (her decks, the damage and the damage-control teams)");
			return false;
		}
		if (M == TEXT("sector") && Sector.Num() == 0)
		{
			OutDetail = TEXT("no sector data from the fleet yet");
			return false;
		}
		// a scanned ship instead of the Aquila: what the sensors know of her (a firm track; more once she is classified)
		FString Scan = M == TEXT("ship") ? Str(TEXT("target")).TrimStartAndEnd() : FString();
		if (Scan.Equals(TEXT("AQUILA"), ESearchCase::IgnoreCase) || Scan.Equals(TEXT("self"), ESearchCase::IgnoreCase))
		{
			Scan.Empty();
		}
		if (!Scan.IsEmpty())
		{
			const UAstraBattleSubsystem* B = GetWorld()->GetSubsystem<UAstraBattleSubsystem>();
			UAstraBattleSubsystem::FDamageView View;
			if (!B || !B->GetDamageView(Scan.ToUpper(), View))
			{
				OutDetail = FString::Printf(TEXT("the sensors hold no firm track on %s: nothing to put on the holo table"), *Scan);
				return false;
			}
			Scan = View.ContactId;
		}
		HoloMode = M;
		HoloShipId = Scan;
		OutDetail = M == TEXT("sector") ? FString(TEXT("holo table: the sector map (the March, who holds what, the gate links)"))
		          : M == TEXT("ship") && !Scan.IsEmpty() ? FString::Printf(TEXT("holo table: %s as the sensors see her — sections, shield faces, what burns"), *Scan)
		          : M == TEXT("ship")   ? FString::Printf(TEXT("holo table: the Aquila, deck by deck — %s"), *DamageSummary())
		                                : FString(TEXT("holo table: tactical plot"));
		return true;
	}
	if (Name == TEXT("opening"))
	{
		// the March (CAMPAGNA) asks once, on a new campaign, to play the opening's forces itself
		UAstraBattleSubsystem* B = GetWorld()->GetSubsystem<UAstraBattleSubsystem>();
		bool bScript = true;
		Args->TryGetBoolField(TEXT("script"), bScript);
		if (!B)
		{
			OutDetail = TEXT("no battle");
			return false;
		}
		return B->SetOpeningScript(bScript, OutDetail);
	}
	if (Name == TEXT("eagle_recover"))
	{
		// the deck's recovery guidance takes the Captain's Falcon (an automatic carrier landing): Flight Control on the bridge or the flight net calls it
		UAstraBattleSubsystem* B = GetWorld()->GetSubsystem<UAstraBattleSubsystem>();
		if (!B || !B->IsPiloting())
		{
			OutDetail = TEXT("the Captain is not flying: there is no Falcon to bring in");
			return false;
		}
		const FString By = Str(TEXT("by")).TrimStartAndEnd();
		if (!B->StartPilotRecovery(By.IsEmpty() ? FString(TEXT("Flight Control")) : By))
		{
			OutDetail = TEXT("Eagle is beyond the recovery guidance's reach (8 km of the Aquila) or down: she must close on the Aquila first");
			return false;
		}
		OutDetail = TEXT("the deck has Eagle: the recovery guidance is flying her clear of the hull, to the gate in front of the bow and in through the port tube "
		                 "(about half a minute); the Captain can take the stick back at any time");
		return true;
	}
	if (Name == TEXT("crew_locate"))
	{
		// the Captain is no entry of the personnel file: his badge, wherever he is. A job with the word in it is not him: the Transporter Chief once
		// looked for "captain" on the flight deck, found the plane captains and told him three times he was not there (2 Oct)
		const FString WhoLower = Str(TEXT("who")).TrimStartAndEnd().ToLower();
		if (WhoLower == TEXT("captain") || WhoLower == TEXT("the captain") || WhoLower == TEXT("the ship's captain") || WhoLower == TEXT("commanding officer")
		    || WhoLower == TEXT("the commanding officer") || WhoLower == TEXT("me") || WhoLower == TEXT("the captain's badge"))
		{
			OutDetail = CaptainLocatorText();
			return true;
		}
		// the personnel file and the internal locator (VITA): who someone is, where they are, what they are doing
		const UAstraLifeSubsystem* Life = GetWorld()->GetSubsystem<UAstraLifeSubsystem>();
		if (!Life || !Life->IsRunning())
		{
			OutDetail = TEXT("the internal locator is not answering");
			return false;
		}
		const FString Who = Str(TEXT("who")).TrimStartAndEnd();
		OutDetail = Life->LocatorText(Who, 4);
		if (OutDetail.IsEmpty())
		{
			OutDetail = FString::Printf(TEXT("nobody aboard matches \"%s\" in the personnel file (try a surname, a rank and a name, or a job)"), *Who);
			return false;
		}
		OutDetail = TEXT("the personnel file and the internal locator say (other crew members, not the officer who looked): ") + OutDetail;
		return true;
	}
	if (Name == TEXT("visit"))
	{
		FString Who, Why;
		Args->TryGetStringField(TEXT("officer"), Who);
		Args->TryGetStringField(TEXT("reason"), Why);
		return StartVisit(Who, Why, OutDetail);
	}
	if (Name == TEXT("abandon_ship"))
	{
		return StartAbandon(true, OutDetail);
	}
	if (bAbandon && Name == TEXT("director_beat"))
	{
		// nothing new happens to a ship being abandoned (or already lost): the story waits for the aftermath
		OutDetail = TEXT("the Aquila is being abandoned: no new beat");
		return false;
	}
	if (Name == TEXT("story_card") || Name == TEXT("story_black"))
	{
		// the aftermath's scenes (the mind): cards on a black screen, or the dark of a scene played in voices
		AASTRAPlayerController* PC = Cast<AASTRAPlayerController>(UGameplayStatics::GetPlayerController(this, 0));
		if (!PC)
		{
			OutDetail = TEXT("no player");
			return false;
		}
		if (bShipLost)
		{
			// the story has left the fight behind (hours, days later): the battle stops where it was
			if (UAstraBattleSubsystem* B = GetWorld()->GetSubsystem<UAstraBattleSubsystem>())
			{
				B->Freeze();
			}
		}
		if (Name == TEXT("story_card"))
		{
			double Hold = 5.0;
			bool bBlack = false;
			Args->TryGetNumberField(TEXT("hold"), Hold);
			Args->TryGetBoolField(TEXT("black"), bBlack);
			PC->StoryCard(Str(TEXT("title")), Str(TEXT("sub")), (float)Hold, bBlack);
			OutDetail = TEXT("card shown");
		}
		else
		{
			bool bOn = true;
			double Fade = 1.2;
			Args->TryGetBoolField(TEXT("on"), bOn);
			Args->TryGetNumberField(TEXT("fade"), Fade);
			PC->StoryBlack(bOn, (float)Fade);
			OutDetail = bOn ? TEXT("dark") : TEXT("light");
		}
		return true;
	}
	if (Name == TEXT("new_command"))
	{
		if (!bShipLost)
		{
			OutDetail = TEXT("the Aquila is not lost");
			return false;
		}
		if (UAstraCampaignSubsystem* C = GetWorld()->GetSubsystem<UAstraCampaignSubsystem>())
		{
			const FString Sys = Str(TEXT("system"));
			// a moment for the last card to fade, then the new ship
			FTimerHandle H;
			TWeakObjectPtr<UAstraCampaignSubsystem> WC(C);
			GetWorld()->GetTimerManager().SetTimer(H, [WC, Sys]() { if (WC.IsValid()) { WC->NewCommand(Sys); } }, 1.5f, false);
			OutDetail = TEXT("the new Aquila");
			return true;
		}
		OutDetail = TEXT("no campaign");
		return false;
	}
	if (Name == TEXT("visit_end") || Name == TEXT("dismiss_visitor"))
	{
		if (!Visitor.IsValid())
		{
			OutDetail = TEXT("nobody is visiting the Captain");
			return false;
		}
		EndVisit(TEXT("the Captain let them go"));
		OutDetail = TEXT("going back to their station");
		return true;
	}
	if (Name == TEXT("sector"))
	{
		// the war map from the mind: every system's look is charted (Aurelia keeps the level's sky), links and owners kept
		Args->TryGetStringArrayField(TEXT("news"), SectorNews);   // the fleet net's latest (the Mess Hall's news screen)
		const TArray<TSharedPtr<FJsonValue>>* List = nullptr;
		if (!Args->TryGetArrayField(TEXT("systems"), List))
		{
			OutDetail = TEXT("no systems");
			return false;
		}
		Sector.Reset();
		for (const TSharedPtr<FJsonValue>& V : *List)
		{
			const TSharedPtr<FJsonObject> O = V.IsValid() ? V->AsObject() : nullptr;
			if (!O.IsValid())
			{
				continue;
			}
			FAstraSectorSystem X;
			O->TryGetStringField(TEXT("name"), X.Name);
			O->TryGetStringField(TEXT("owner"), X.Owner);
			double T = 0.0, PX = 0.0, PY = 0.0;
			O->TryGetNumberField(TEXT("threat"), T);
			O->TryGetNumberField(TEXT("x"), PX);
			O->TryGetNumberField(TEXT("y"), PY);
			X.Threat = (int32)T;
			X.Pos = FVector2D(PX, PY);
			O->TryGetStringArrayField(TEXT("links"), X.Links);
			double Pop = 0.0;
			O->TryGetNumberField(TEXT("pop"), Pop);
			X.PopM = float(Pop);
			FString Star, Planet, World;
			O->TryGetStringField(TEXT("star_class"), Star);
			O->TryGetStringField(TEXT("planet_type"), Planet);
			O->TryGetStringField(TEXT("planet_name"), World);
			if (!X.Name.IsEmpty() && !X.Name.Equals(TEXT("Aurelia"), ESearchCase::IgnoreCase))
			{
				Systems.Add(X.Name, MakeLook(X.Name, Star, Planet, World));
			}
			Sector.Add(X);
		}
		if (!SystemName.Equals(TEXT("Aurelia"), ESearchCase::IgnoreCase) && FindSector(SystemName))
		{
			const FString Keep = LocationName;
			ApplySystem(Systems.FindChecked(FindSector(SystemName)->Name));   // a resumed campaign: the sector's own look
			LocationName = Keep;
		}
		// the March (CAMPAGNA): the fleets and battles as our high command holds them, for the holo table's sector view
		MarchFleets.Reset();
		MarchBattles.Reset();
		const TSharedPtr<FJsonObject>* March = nullptr;
		if (Args->TryGetObjectField(TEXT("march"), March) && March && March->IsValid())
		{
			const TArray<TSharedPtr<FJsonValue>>* Fleets = nullptr;
			if ((*March)->TryGetArrayField(TEXT("fleets"), Fleets))
			{
				for (const TSharedPtr<FJsonValue>& V : *Fleets)
				{
					const TSharedPtr<FJsonObject> O = V.IsValid() ? V->AsObject() : nullptr;
					if (!O.IsValid())
					{
						continue;
					}
					FAstraMarchFleet F;
					O->TryGetStringField(TEXT("id"), F.Id);
					O->TryGetStringField(TEXT("side"), F.Side);
					O->TryGetStringField(TEXT("name"), F.Name);
					O->TryGetStringField(TEXT("system"), F.System);
					O->TryGetStringField(TEXT("to"), F.To);
					O->TryGetStringField(TEXT("state"), F.State);
					double Eta = -1.0, N = 0.0, Age = 0.0;
					if (O->TryGetNumberField(TEXT("eta_s"), Eta)) { F.EtaS = (float)Eta; }
					O->TryGetNumberField(TEXT("ships"), N);
					O->TryGetNumberField(TEXT("age_s"), Age);
					F.Ships = (int32)N;
					F.AgeS = (float)Age;
					O->TryGetBoolField(TEXT("known"), F.bKnown);
					if (!F.System.IsEmpty())
					{
						MarchFleets.Add(F);
					}
				}
			}
			const TArray<TSharedPtr<FJsonValue>>* Battles = nullptr;
			if ((*March)->TryGetArrayField(TEXT("battles"), Battles))
			{
				for (const TSharedPtr<FJsonValue>& V : *Battles)
				{
					const TSharedPtr<FJsonObject> O = V.IsValid() ? V->AsObject() : nullptr;
					FString Sys;
					if (O.IsValid() && O->TryGetStringField(TEXT("system"), Sys))
					{
						MarchBattles.AddUnique(Sys);
					}
				}
			}
		}
		OutDetail = FString::Printf(TEXT("sector charted: %d systems%s"), Sector.Num(),
		                            MarchFleets.Num() ? *FString::Printf(TEXT(", %d fleets of the March"), MarchFleets.Num()) : TEXT(""));
		return true;
	}
	if ((Name == TEXT("intercept") || Name == TEXT("set_course")) && Battle && Battle->IsInLane())
	{
		OutDetail = TEXT("impossible: the Janus lane has the ship, the helm answers again after the transit");
		return false;
	}
	FString Aborted;
	if (Name == TEXT("intercept") || Name == TEXT("set_course"))
	{
		bAutoHelm = false;
		if (Battle && Battle->IsGateRunActive())
		{
			Battle->AbortGateRun();
			Aborted = TEXT(" (Janus approach cancelled)");
		}
	}
	if (Name == TEXT("intercept"))
	{
		const FString Id = Str(TEXT("contact_id")).ToUpper();
		double Brg = 0.0, Mk = 0.0, Rng = 0.0;
		if (!Battle || !Battle->ContactGeometry(Id, Brg, Mk, Rng))
		{
			OutDetail = FString::Printf(TEXT("no contact %s to intercept"), *Id);
			return false;
		}
		InterceptId = Id;
		InterceptStandoffKm = FMath::Clamp((float)Num(TEXT("standoff_km"), 6.0), 1.f, 30.f);
		InterceptRetargetT = 0.f;
		bBroadside = false;
		InterceptRangeKm = Rng;
		OutDetail = Rng < 0.0
			? FString::Printf(TEXT("steering down the bearing of %s: %03.0f mark %.0f, range unknown (a bearing only), throttle %.0f%%; the helm "
			                       "turns broadside at %.0f km once there is a track%s"), *Id, Brg, Mk, ThrottlePct, InterceptStandoffKm, *Aborted)
			: FString::Printf(TEXT("intercepting %s: bearing %03.0f mark %.0f, range %.1f km, throttle %.0f%%; at %.0f km the helm turns "
			                       "broadside and holds the range (course follows the target)%s"),
			                  *Id, Brg, Mk, Rng, ThrottlePct, InterceptStandoffKm, *Aborted);
		return true;
	}
	if (Name == TEXT("set_course"))
	{
		InterceptId.Empty();
		TargetHeadingDeg = WrapDeg((float)Num(TEXT("heading_deg"), HeadingDeg));
		TargetMarkDeg = FMath::Clamp((float)Num(TEXT("mark_deg"), MarkDeg), -90.f, 90.f);
		bTurning = true;
		OutDetail = FString::Printf(TEXT("coming to %03.0f mark %.0f (turn rate 1.5 deg/s)%s"), TargetHeadingDeg, TargetMarkDeg, *Aborted);
		return true;
	}
	if (Name == TEXT("set_throttle"))
	{
		ThrottlePct = FMath::Clamp((float)Num(TEXT("percent"), ThrottlePct), 0.f, 100.f);
		OutDetail = FString::Printf(TEXT("throttle %.0f%%"), ThrottlePct);
		return true;
	}
	if (Name == TEXT("set_alert"))
	{
		const FString L = Str(TEXT("level")).ToLower();
		SetAlert(L == TEXT("red") ? EAstraAlert::Red : (L == TEXT("yellow") ? EAstraAlert::Yellow : EAstraAlert::Green));
		OutDetail = FString::Printf(TEXT("condition %s set shipwide"), *AlertName(Alert));
		return true;
	}
	if (Name == TEXT("set_shields"))
	{
		const FString M = Str(TEXT("mode")).ToLower();
		if (M == TEXT("off"))
		{
			bShieldsUp = false;
			OutDetail = TEXT("shields down");
		}
		else
		{
			bShieldsUp = true;
			ShieldMode = M.IsEmpty() ? TEXT("balanced") : M;
			OutDetail = FString::Printf(TEXT("shields up, %s"), *ShieldMode);
		}
		if (Battle)
		{
			Battle->SetPlayerShields(bShieldsUp);
		}
		return true;
	}
	if (Name == TEXT("route_power"))
	{
		const FString Sys = Str(TEXT("system"));
		if (!PowerPct.Contains(Sys))
		{
			OutDetail = FString::Printf(TEXT("unknown system %s"), *Sys);
			return false;
		}
		const float Want = FMath::Clamp((float)Num(TEXT("percent"), 100.0), 0.f, 150.f);
		float Sum = 0.f;
		for (const auto& KV : PowerPct) { Sum += KV.Key == Sys ? Want : KV.Value; }
		if (Sum > PowerBudget + 0.5f)
		{
			FString Now;
			for (const auto& KV : PowerPct) { Now += FString::Printf(TEXT("%s%s %.0f"), Now.IsEmpty() ? TEXT("") : TEXT(", "), *KV.Key, KV.Value); }
			OutDetail = FString::Printf(TEXT("reactor budget exceeded: that would allocate %.0f%% of the %.0f%% available — cut another system first (now: %s)"),
			                            Sum, PowerBudget, *Now);
			return false;
		}
		PowerPct[Sys] = Want;
		ReactorPct = 78.f + FMath::Max(0.f, Sum - 600.f) * 0.13f;
		OutDetail = FString::Printf(TEXT("%s at %.0f%% of nominal; reactor at %.0f%%, %.0f%% of the %.0f%% budget allocated"), *Sys, Want, ReactorPct, Sum, PowerBudget);
		return true;
	}
	if (Name == TEXT("set_target"))
	{
		TargetId = Str(TEXT("contact_id"));
		OutDetail = FString::Printf(TEXT("target designated %s, fire control solution building"), *TargetId);
		return true;
	}
	if (Name == TEXT("fire_weapons"))
	{
		if (!Battle)
		{
			OutDetail = TEXT("fire control offline");
			return false;
		}
		const bool bOk = Battle->PlayerFire(Str(TEXT("weapon")), Str(TEXT("contact_id")), (int32)Num(TEXT("salvo"), 1), OutDetail);
		if (bOk)
		{
			TargetId = Str(TEXT("contact_id"));
		}
		return bOk;
	}
	if (Name == TEXT("set_point_defense"))
	{
		PointDefense = Str(TEXT("mode"));
		OutDetail = FString::Printf(TEXT("point defense %s"), *PointDefense);
		return true;
	}
	if (Name == TEXT("launch_squadron"))
	{
		return Battle ? Battle->LaunchSquadron(Str(TEXT("squadron")), Str(TEXT("mission")), Str(TEXT("contact_id")), OutDetail) : false;
	}
	if (Name == TEXT("recall_squadron"))
	{
		return Battle ? Battle->RecallSquadron(Str(TEXT("squadron")), OutDetail) : false;
	}
	if (Name == TEXT("dispatch_damage_control"))
	{
		const int32 Deck = (int32)Num(TEXT("deck"), 0);
		const FString SecRaw = Str(TEXT("section")).TrimStartAndEnd();
		FString Sec = SecRaw.ToUpper();
		Sec.RemoveFromStart(TEXT("SECTION "));
		const TCHAR SecC = Sec.Len() ? Sec[0] : TEXT('?');
		const FString Task = Str(TEXT("task")).ToLower();
		// what the task asks for: firefighting a fire, sealing a breach, repairing the rest ("rescue" and no task: anything)
		auto Fits = [&Task](const FAstraDamage& X)
		{
			return Task == TEXT("firefight") ? X.Kind == TEXT("fire") : (Task == TEXT("seal_breach") ? X.Kind == TEXT("hull breach")
			     : (Task == TEXT("repair") ? (X.Kind != TEXT("fire") && X.Kind != TEXT("hull breach")) : true));
		};
		auto Worst = [this](TFunctionRef<bool(const FAstraDamage&)> Pred) -> FAstraDamage*
		{
			FAstraDamage* Best = nullptr;
			for (FAstraDamage& X : Damage)
			{
				const float Kx = X.Kind == TEXT("hull breach") ? 2.f : (X.Kind == TEXT("fire") ? 1.f : 0.f);
				if (Pred(X) && (!Best || Kx + X.Severity > (Best->Kind == TEXT("hull breach") ? 2.f : (Best->Kind == TEXT("fire") ? 1.f : 0.f)) + Best->Severity))
				{
					Best = &X;
				}
			}
			return Best;
		};
		// one incident by its id (ops' own dispatcher), else the worst unattended one at that deck and section that the task fits (a fire and a breach
		// can share a section), else one named by its place ("the Main Galley"), else any unattended one on the deck
		const int32 IncidentId = (int32)Num(TEXT("id"), -1.0);
		FAstraDamage* D = IncidentId >= 0 ? Damage.FindByPredicate([&](const FAstraDamage& X) { return X.Id == IncidentId; }) : nullptr;
		if (!D)
		{
			D = Worst([&](const FAstraDamage& X) { return X.Deck == Deck && X.Section == SecC && X.Team < 0 && Fits(X); });
		}
		if (!D)
		{
			D = Worst([&](const FAstraDamage& X) { return X.Deck == Deck && X.Section == SecC && X.Team < 0; });
		}
		if (!D && SecRaw.Len() > 1)
		{
			D = Worst([&](const FAstraDamage& X) { return X.Team < 0 && !X.Place.IsEmpty() && X.Place.Contains(SecRaw, ESearchCase::IgnoreCase); });
		}
		if (!D)
		{
			D = Damage.FindByPredicate([&](const FAstraDamage& X) { return X.Deck == Deck && X.Section == SecC; });
		}
		if (D && D->Team >= 0)
		{
			OutDetail = FString::Printf(TEXT("team %d is already on the %s at %s (%s)"), D->Team + 1, *D->Kind, *D->Where(),
			                            D->Travel > 0.f ? *FString::Printf(TEXT("on scene in %.0f s"), D->Travel)
			                                            : *FString::Printf(TEXT("%.0f%% done"), 100.f * D->Progress));
			return true;
		}
		if (!D)
		{
			D = Worst([&](const FAstraDamage& X) { return X.Deck == Deck && X.Team < 0; });
		}
		if (!D)
		{
			OutDetail = FString::Printf(TEXT("no damage reported at deck %d section %c; open incidents: %s"), Deck, SecC, *DamageSummary());
			return false;
		}
		const int32 Team = FreeDamageTeam();
		if (Team < 0)
		{
			OutDetail = FString::Printf(TEXT("all %d damage-control teams are committed: %s"), NumDamageTeams, *DamageSummary());
			return false;
		}
		const FString Priority = Str(TEXT("priority")).ToLower();
		const float Speed = Priority == TEXT("critical") ? 0.8f : (Priority == TEXT("low") ? 1.2f : 1.f);
		D->Team = Team;
		// the walk the team really has, on the ship's plan (VITA), to that very compartment; else the old estimate
		const UAstraLifeSubsystem* Life = GetWorld()->GetSubsystem<UAstraLifeSubsystem>();
		const float Eta = Life ? (D->CompId.IsNone() ? Life->RepairEtaSeconds(D->Deck, D->Section, D->Id) : Life->RepairEtaFor(*D)) : 0.f;
		D->Travel = D->Travel0 = (Eta > 0.f ? Eta : (6.f + FMath::Abs(D->Deck - 6) * 1.5f)) * Speed;
		D->Work = (D->Comp != INDEX_NONE && Interior.IsReady() ? Interior.WorkSeconds(*D) : (D->Kind == TEXT("fire") ? 30.f : (D->Kind == TEXT("hull breach") ? 40.f : 25.f))) * Speed;
		D->Progress = 0.f;
		D->Baseline = 0.f;
		int32 Busy = 0;
		for (const FAstraDamage& X : Damage) { Busy += X.Team >= 0 ? 1 : 0; }
		OutDetail = FString::Printf(TEXT("team %d en route to the %s at %s%s%s: on scene in %.0f s, about %.0f s of work; %d team%s still free"),
		                            Team + 1, *D->Kind, *D->Where(), D->Note.IsEmpty() ? TEXT("") : TEXT(" — "), *D->Note, D->Travel, D->Work, NumDamageTeams - Busy, NumDamageTeams - Busy == 1 ? TEXT("") : TEXT("s"));
		return true;
	}
	if (Name == TEXT("hail"))
	{
		const FString Id = Str(TEXT("contact_id"));
		if (Id.Equals(TEXT("fleet"), ESearchCase::IgnoreCase))
		{
			OutDetail = TEXT("7th Fleet net open: Vice Admiral Adrian Rourke, 7th Fleet commander, is on the line (reply expected)");
			ChannelParty = TEXT("fleet");
			return true;
		}
		const bool bOk = Battle ? Battle->PlayerHail(Id, OutDetail) : false;
		if (bOk)
		{
			ChannelParty = Id.ToUpper();
		}
		return bOk;
	}
	if (Name == TEXT("director_beat"))
	{
		const TSharedPtr<FJsonObject>* Beat = nullptr;
		if (!Battle || !Args->TryGetObjectField(TEXT("beat"), Beat))
		{
			OutDetail = TEXT("no beat");
			return false;
		}
		return Battle->StartBeat(*Beat, OutDetail);
	}
	if (Name == TEXT("cease_fire"))
	{
		return Battle ? Battle->PlayerCeaseFire(OutDetail) : false;
	}
	if (Name == TEXT("fleet_request"))
	{
		return Battle ? Battle->FleetRequest(Str(TEXT("ship")), Str(TEXT("request")), Str(TEXT("target")), OutDetail) : false;
	}
	if (Name == TEXT("mandate_tactics"))
	{
		return Battle ? Battle->EnemyTactics(Args, OutDetail) : false;
	}
	if (Name == TEXT("group_order"))
	{
		return Battle ? Battle->GroupOrderCommand(Args, OutDetail) : false;   // docs/GUERRA.md: {side, group, order, target, for_s, by}
	}
	if (Name == TEXT("enemy_order"))
	{
		return Battle ? Battle->EnemyOrder(Str(TEXT("order")), Str(TEXT("reason")), Str(TEXT("commander")), OutDetail) : false;
	}
	if (Name == TEXT("channel_closed") || Name == TEXT("end_transmission"))
	{
		OutDetail = TEXT("channel closed");
		Event(Name == TEXT("channel_closed") ? TEXT("comms: the Mandate cut the channel") : TEXT("comms: channel closed"));
		return true;
	}
	if (Name == TEXT("set_emcon"))
	{
		Emcon = Str(TEXT("level"));
		OutDetail = FString::Printf(TEXT("emissions %s"), *Emcon);
		return true;
	}
	if (Name == TEXT("set_radiators"))
	{
		const FString St = Str(TEXT("state")).ToLower();
		if (St != TEXT("extended") && St != TEXT("retracted"))
		{
			OutDetail = TEXT("state must be extended or retracted");
			return false;
		}
		bRadiatorsOut = St == TEXT("extended");
		OutDetail = bRadiatorsOut
			? FString::Printf(TEXT("radiators extended: heat %.0f %%, now shedding it almost three times faster; the hot panels show on "
			                       "enemy sensors and can be hit"), HeatPct)
			: FString::Printf(TEXT("radiators retracted and shielded: heat %.0f %%, shedding it slowly"), HeatPct);
		Event(FString::Printf(TEXT("engineering: radiators %s"), bRadiatorsOut ? TEXT("extended") : TEXT("retracted")), false);
		return true;
	}
	if (Name == TEXT("vent_heat"))
	{
		if (CoolantVents <= 0)
		{
			OutDetail = TEXT("no coolant charges left to vent");
			return false;
		}
		--CoolantVents;
		const float Was = HeatPct;
		HeatPct *= 0.62f;
		VentPlumeT = 30.f;
		OutDetail = FString::Printf(TEXT("coolant vented: heat from %.0f %% to %.0f %%; a plume every sensor can see for half a minute; "
		                                 "%d charges left"), Was, HeatPct, CoolantVents);
		Event(FString::Printf(TEXT("engineering: coolant vented, heat down to %.0f %%"), HeatPct), false);
		return true;
	}
	if (Name == TEXT("launch_decoys"))
	{
		return Battle ? Battle->LaunchDecoys(OutDetail) : false;
	}
	if (Name == TEXT("active_scan"))
	{
		return Battle ? Battle->PlayerScan(Str(TEXT("contact_id")), OutDetail) : false;
	}
	if (UAstraTransporterSubsystem::IsTransportCommand(Name))
	{
		// TELETRASPORTO (docs/TELETRASPORTO.md): the Transporter Room's orders: transport, transport_energize, transport_abort
		UAstraTransporterSubsystem* Xport = GetWorld()->GetSubsystem<UAstraTransporterSubsystem>();
		if (!Xport)
		{
			OutDetail = TEXT("the Transporter Room does not answer");
			return false;
		}
		return Xport->ApplyCommand(Name, Args, OutDetail);
	}
	OutDetail = FString::Printf(TEXT("unknown command %s"), *Name);
	return false;
}

TSharedRef<FJsonObject> UAstraShipSubsystem::Snapshot() const
{
	TSharedRef<FJsonObject> S = MakeShared<FJsonObject>();
	S->SetStringField(TEXT("ship"), TEXT("ASN Aquila"));
	if (const UAstraStationsSubsystem* St = GetWorld() ? GetWorld()->GetSubsystem<UAstraStationsSubsystem>() : nullptr)
	{
		S->SetObjectField(TEXT("stations"), St->StationsJson());
		S->SetStringField(TEXT("action_target"), St->ActionTarget());   // what "target: action" means now (tactical's target, else the nearest hostile)
		if (Viewscreen)
		{
			S->SetStringField(TEXT("viewscreen"), Viewscreen->Describe());   // what the Captain sees on the main screen now
		}
	}
	S->SetStringField(TEXT("location"), LocationName);
	if (HasSurface())
	{
		// the world below, which a Falcon can fly down to (its field speaks on the radio when Eagle comes down)
		const FAstraSystemLook* L = CurrentLook();
		TSharedRef<FJsonObject> W = MakeShared<FJsonObject>();
		W->SetStringField(TEXT("world"), SurfaceWorldName());
		W->SetStringField(TEXT("kind"), IsHomeWorld() ? FString(TEXT("ocean")) : (L ? L->PlanetType : FString()));
		W->SetStringField(TEXT("field"), SurfaceSiteName());
		W->SetBoolField(TEXT("captain_here"), bPlanetside);
		S->SetObjectField(TEXT("surface"), W);
	}
	S->SetStringField(TEXT("alert"), AlertName(Alert));
	S->SetNumberField(TEXT("heading_deg"), FMath::RoundToInt(HeadingDeg));
	S->SetNumberField(TEXT("mark_deg"), FMath::RoundToInt(MarkDeg));
	if (!InterceptId.IsEmpty())
	{
		S->SetStringField(TEXT("helm"), InterceptRangeKm < 0.0
			? FString::Printf(TEXT("steering down the bearing of %s (no range: a bearing only); broadside at %.0f km once tracked"), *InterceptId, InterceptStandoffKm)
			: FString::Printf(TEXT("intercepting %s, range %.1f km, %s (standoff %.0f km); course follows the target"),
			                  *InterceptId, InterceptRangeKm, bBroadside ? TEXT("broadside, holding the range") : TEXT("closing"), InterceptStandoffKm));
	}
	else if (const UAstraBattleSubsystem* Gate = GetWorld() ? GetWorld()->GetSubsystem<UAstraBattleSubsystem>() : nullptr; Gate && Gate->IsGateRunActive())
	{
		S->SetStringField(TEXT("helm"), Gate->GateStatus());
	}
	else if (bTurning)
	{
		S->SetStringField(TEXT("helm"), FString::Printf(TEXT("turning to %03.0f mark %.0f"), TargetHeadingDeg, TargetMarkDeg));
	}
	S->SetNumberField(TEXT("throttle_pct"), FMath::RoundToInt(ThrottlePct));
	S->SetNumberField(TEXT("speed_mps"), FMath::RoundToInt(SpeedMps));
	S->SetNumberField(TEXT("reactor_pct"), FMath::RoundToInt(ReactorPct));
	TSharedRef<FJsonObject> P = MakeShared<FJsonObject>();
	for (const auto& KV : PowerPct) { P->SetNumberField(KV.Key, FMath::RoundToInt(KV.Value)); }
	S->SetObjectField(TEXT("power_pct"), P);
	TSharedRef<FJsonObject> Sh = MakeShared<FJsonObject>();
	Sh->SetStringField(TEXT("state"), bShieldsUp ? TEXT("up") : TEXT("down"));
	Sh->SetStringField(TEXT("mode"), ShieldMode);
	S->SetObjectField(TEXT("shields"), Sh);
	TSharedRef<FJsonObject> W = MakeShared<FJsonObject>();
	const UAstraBattleSubsystem* FireControl = GetWorld() ? GetWorld()->GetSubsystem<UAstraBattleSubsystem>() : nullptr;
	if (FireControl)
	{
		W = FireControl->PlayerWeaponsJson();
	}
	else
	{
		for (const auto& KV : Weapons) { W->SetStringField(KV.Key, KV.Value); }
	}
	W->SetStringField(TEXT("point_defense"), PointDefense);
	if (FireControl)
	{
		W->SetStringField(TEXT("decoys"), FireControl->DecoyT > 0.f
			? FString::Printf(TEXT("out now (%.0f s left), %d aboard"), FireControl->DecoyT, FireControl->PlayerDecoys)
			: FString::Printf(TEXT("%d aboard (two a launch)"), FireControl->PlayerDecoys));
	}
	S->SetObjectField(TEXT("weapons"), W);
	S->SetStringField(TEXT("target"), TargetId);
	S->SetStringField(TEXT("emcon"), Emcon);
	if (const UAstraBattleSubsystem* B = GetWorld() ? GetWorld()->GetSubsystem<UAstraBattleSubsystem>() : nullptr)
	{
		// how far out the Mandate can find us, and whether they have us now
		S->SetStringField(TEXT("signature"), FString::Printf(TEXT("about %.0f km (EMCON %s, the drive, radiators %s%s)%s"), B->PlayerSignatureKm(), *Emcon,
		                  bRadiatorsOut ? TEXT("out") : TEXT("in"), VentPlumeT > 0.f ? TEXT(", a coolant plume") : TEXT(""),
		                  B->IsPlayerTracked() ? TEXT("") : TEXT(" — the Mandate has lost our track")));
	}
	{
		TSharedRef<FJsonObject> Th = MakeShared<FJsonObject>();
		Th->SetNumberField(TEXT("heat_pct"), FMath::RoundToInt(HeatPct));
		Th->SetStringField(TEXT("trend"), FMath::Abs(HeatRate) < 0.05f ? FString(TEXT("steady"))
		                   : FString::Printf(TEXT("%s%.1f %%/s"), HeatRate > 0.f ? TEXT("+") : TEXT(""), HeatRate));
		Th->SetStringField(TEXT("radiators"), FString(bRadiatorsOut ? TEXT("extended") : TEXT("retracted"))
		                   + (RadiatorHealth < 0.99f ? FString::Printf(TEXT(", damaged: %.0f %% effective"), 100.f * RadiatorHealth) : FString()));
		Th->SetNumberField(TEXT("coolant_vents"), CoolantVents);
		const float HF = HeatFactor();
		Th->SetStringField(TEXT("status"), HeatPct >= 90.f
			? FString::Printf(TEXT("critical: weapons and shields at %.0f %%, the drive slowed, conduits failing, Main Engineering sweltering"), 100.f * HF)
			: (HeatPct >= 70.f ? FString::Printf(TEXT("running hot: weapons cadence and shield regeneration at %.0f %%"), 100.f * HF)
			                   : FString(TEXT("nominal"))));
		if (VentPlumeT > 0.f)
		{
			Th->SetStringField(TEXT("vent_plume"), FString::Printf(TEXT("visible to every sensor for %.0f s more"), VentPlumeT));
		}
		S->SetObjectField(TEXT("thermal"), Th);
	}
	S->SetStringField(TEXT("holo_table"), HoloMode);
	const UAstraBattleSubsystem* Flight = GetWorld() ? GetWorld()->GetSubsystem<UAstraBattleSubsystem>() : nullptr;
	if (Flight)
	{
		S->SetObjectField(TEXT("squadrons"), Flight->SquadronsJson());
	}
	else
	{
		TSharedRef<FJsonObject> Q = MakeShared<FJsonObject>();
		for (const auto& KV : Squadrons) { Q->SetStringField(KV.Key, KV.Value); }
		S->SetObjectField(TEXT("squadrons"), Q);
	}
	const UAstraBattleSubsystem* Battle = GetWorld() ? GetWorld()->GetSubsystem<UAstraBattleSubsystem>() : nullptr;
	if (Battle)
	{
		S->SetArrayField(TEXT("contacts"), Battle->ContactsJson());
		S->SetStringField(TEXT("enemy_small_craft"), Battle->EnemyCraftSummary());
		TSharedRef<FJsonObject> MandateView = Battle->MandateViewJson();
		if (const UAstraBoardSubsystem* BoardOpts = GetWorld()->GetSubsystem<UAstraBoardSubsystem>(); BoardOpts && BoardOpts->IsReady())
		{
			const TSharedRef<FJsonObject> Opts = BoardOpts->BoardingOptionsJson(1);          // ABBORDAGGI: what the Mandate's boats could dock at now (empty when nothing)
			if (Opts->Values.Num())
			{
				MandateView->SetObjectField(TEXT("boarding"), Opts);
			}
		}
		S->SetObjectField(TEXT("_mandate"), MandateView);   // for the enemy minds only
		S->SetObjectField(TEXT("_astra_groups"), Battle->SideGroupsJson(0));   // the ASTRA groups, for the allied commanders (docs/GUERRA.md)
		// where the Captain is: in a Falcon the XO has the conn and the Captain speaks by radio
		const FString Flying = Battle->PilotSummary();
		S->SetStringField(TEXT("captain"), CaptainFate == 2 ? FString::Printf(TEXT("DEAD — %s; the Executive Officer commands the Aquila"), *Interior.Captain().Why)
		                                  : (CaptainFate == 1 ? FString::Printf(TEXT("down, unconscious (%s); the XO has the conn"), *Interior.Captain().Cause)
		                                  : (!Flying.IsEmpty() ? Flying : CaptainAboard())));
		S->SetNumberField(TEXT("hull_pct"), FMath::RoundToInt(100.f * Battle->PlayerHullFraction()));
		Sh->SetNumberField(TEXT("strength_pct"), FMath::RoundToInt(100.f * Battle->PlayerShieldFraction()));
	}
	if (Battle)
	{
		S->SetStringField(TEXT("janus_gate"), Battle->GateStatus());
	}
	if (Sector.Num() == 0)   // otherwise the mind's war map tells the crew about the sector
	{
		S->SetStringField(TEXT("known_systems"), KnownSystemsLine());
	}
	S->SetStringField(TEXT("bearing_convention"), TEXT("bearings are true bearings in the system plane, like headings: steer to a contact's bearing to point at it"));
	TArray<TSharedPtr<FJsonValue>> Dmg;
	int32 Busy = 0;
	{
		// the worst first (a dozen are plenty for a mind: the rest are counted)
		TArray<int32> Order;
		for (int32 i = 0; i < Damage.Num(); ++i)
		{
			Busy += Damage[i].Team >= 0 ? 1 : 0;
			Order.Add(i);
		}
		Order.Sort([this](int32 A, int32 B)
		{
			const FAstraDamage& X = Damage[A];
			const FAstraDamage& Y = Damage[B];
			const float Kx = X.Kind == TEXT("hull breach") ? 2.f : (X.Kind == TEXT("fire") ? 1.f : 0.f), Ky = Y.Kind == TEXT("hull breach") ? 2.f : (Y.Kind == TEXT("fire") ? 1.f : 0.f);
			return Kx + X.Severity > Ky + Y.Severity;
		});
		for (int32 k = 0; k < FMath::Min(12, Order.Num()); ++k)
		{
			const FAstraDamage& D = Damage[Order[k]];
			FString Line = FString::Printf(TEXT("%s: %s"), *D.Where(), *D.Kind);
			if (!D.Note.IsEmpty())
			{
				Line += FString::Printf(TEXT(" — %s"), *D.Note);
			}
			if (!D.System.IsEmpty())
			{
				Line += FString::Printf(TEXT(" (%s power down)"), *D.System);
			}
			Line += D.Team < 0 ? FString(TEXT(" — unattended")) :
			        (D.Travel > 0.f ? FString::Printf(TEXT(" — team %d on the way (%.0f s)"), D.Team + 1, D.Travel)
			                        : FString::Printf(TEXT(" — team %d working, %.0f%% done"), D.Team + 1, 100.f * D.Progress));
			Dmg.Add(MakeShared<FJsonValueString>(Line));
		}
		if (Order.Num() > 12)
		{
			Dmg.Add(MakeShared<FJsonValueString>(FString::Printf(TEXT("(and %d more, lesser incidents)"), Order.Num() - 12)));
		}
	}
	S->SetArrayField(TEXT("damage"), Dmg);
	S->SetStringField(TEXT("damage_control"), FString::Printf(TEXT("%d teams, %d free%s%s"), NumDamageTeams, NumDamageTeams - Busy,
	                  Interior.SealedDoors().Num() ? *FString::Printf(TEXT("; %d pressure bulkheads shut"), Interior.SealedDoors().Num()) : TEXT(""),
	                  Interior.NumWrecked() ? *FString::Printf(TEXT("; %d compartments gutted"), Interior.NumWrecked()) : TEXT("")));
	S->SetStringField(TEXT("casualties"), Roster.Summary());
	if (Roster.GetHurt().Num())
	{
		// the Medbay's ward: who lies in which bed (their `speaker` id when the Captain talks to them there)
		TArray<TSharedPtr<FJsonValue>> Ward;
		int32 Cots = 0;
		for (const int32 i : Roster.GetHurt())
		{
			const FAstraCrewman& Pt = Roster.Get()[i];
			if (Pt.Bed < 0)
			{
				++Cots;
				continue;
			}
			TSharedRef<FJsonObject> Bed = MakeShared<FJsonObject>();
			Bed->SetStringField(TEXT("speaker"), FString::Printf(TEXT("patient%d"), Pt.Bed + 1));
			// where the bed is, as the Captain sees the ward coming out of the lift (facing aft: port is on the right)
			static const TCHAR* Ordinal[] = {TEXT("first"), TEXT("second"), TEXT("third"), TEXT("fourth"), TEXT("fifth"), TEXT("sixth")};
			Bed->SetStringField(TEXT("bed"), FString::Printf(TEXT("the %s bed of the row on the %s as you come in from the lift"),
				Ordinal[Pt.Bed % 6], Pt.Bed < 6 ? TEXT("right") : TEXT("left")));
			Bed->SetStringField(TEXT("name"), Pt.Name());
			Bed->SetStringField(TEXT("gender"), Pt.bFemale ? TEXT("f") : TEXT("m"));
			Bed->SetStringField(TEXT("dept"), Pt.Dept);
			Bed->SetStringField(TEXT("home"), Pt.Home);
			Bed->SetStringField(TEXT("injury"), Pt.Injury);
			Bed->SetStringField(TEXT("condition"), Pt.Condition >= 2 ? TEXT("critical: sedated, cannot speak") : Pt.ConditionName());
			Ward.Add(MakeShared<FJsonValueObject>(Bed));
		}
		TSharedRef<FJsonObject> Med = MakeShared<FJsonObject>();
		Med->SetArrayField(TEXT("patients"), Ward);
		if (Cots)
		{
			Med->SetStringField(TEXT("overflow"), FString::Printf(TEXT("%d more wounded on cots in the passage: the ward's %d beds are full"), Cots, FAstraCrewRoster::NumBeds));
		}
		S->SetObjectField(TEXT("medbay"), Med);
	}
	if (bAbandon)
	{
		const APawn* Me = UGameplayStatics::GetPlayerPawn(this, 0);
		S->SetStringField(TEXT("abandon"), bShipLost
			? FString::Printf(TEXT("THE AQUILA IS LOST: her reactor breached; %d%% of the crew got off in the lifepods%s"), FMath::RoundToInt(EvacFrac * 100.f),
			                  CaptainPod.IsValid() ? *FString::Printf(TEXT("; the Captain is adrift in lifepod %s (the officers speak over the pods' radio)"), *CaptainPodName) : TEXT(""))
			: FString::Printf(TEXT("ABANDON SHIP in progress (%s): %.0f s to the reactor breach; %d%% of the crew in the lifepods; %s"),
			                  bAbandonOrdered ? TEXT("the Captain's order") : TEXT("the reactor is failing"), FMath::Max(0.f, AbandonLeft), FMath::RoundToInt(EvacFrac * 100.f),
			                  CaptainPod.IsValid() ? *FString::Printf(TEXT("the Captain is away in lifepod %s"), *CaptainPodName)
			                  : Cast<AAstraFighterPawn>(Me) ? TEXT("the Captain is flying Eagle")
			                  : TEXT("the Captain is still aboard: the pods are off Corridor 1-A (1-A port by the lift, 1-B starboard by the Captain's quarters)")));
	}
	if (const AAstraCrewMember* V = Visitor.Get())
	{
		S->SetStringField(TEXT("visitor"), FString::Printf(TEXT("%s (%s) %s"), *V->StationId, *V->DisplayName, V->HasArrived()
			? TEXT("is here in the Captain's quarters, in person: they speak face to face; the Captain can let them go (dismiss_visitor)")
			: TEXT("is walking to the Captain's quarters")));
	}
	if (IsCaptainInMess() && MessDiners.Num())
	{
		// the Mess Hall's tables: who sits where (their `speaker` ids when the Captain talks to them there), as the Captain
		// sees the hall coming out of the lift (facing aft: port is on the right)
		static const TCHAR* Along[] = {TEXT("nearest"), TEXT("middle"), TEXT("farthest")};
		static const TCHAR* Across[] = {TEXT("outer right"), TEXT("inner right"), TEXT("inner left"), TEXT("outer left")};
		static const int32 Tables[][2] = {{0, 1}, {0, 1}, {0, 2}, {1, 0}, {1, 0}, {1, 2}, {1, 2}, {1, 3}, {2, 1}, {2, 1}, {2, 3}, {0, 3}};
		TArray<TSharedPtr<FJsonValue>> Diners;
		for (int32 k = 0; k < MessDiners.Num(); ++k)
		{
			if (MessDiners[k] < 0)
			{
				continue;
			}
			const FAstraCrewman& M = Roster.Get()[MessDiners[k]];
			TSharedRef<FJsonObject> O = MakeShared<FJsonObject>();
			O->SetStringField(TEXT("speaker"), FString::Printf(TEXT("mess%d"), k + 1));
			const int32 (&Tb)[2] = Tables[FMath::Min(k, int32(UE_ARRAY_COUNT(Tables)) - 1)];
			O->SetStringField(TEXT("seat"), FString::Printf(TEXT("at the %s table of the %s row"), Along[Tb[0]], Across[Tb[1]]));
			O->SetStringField(TEXT("name"), M.Name());
			O->SetStringField(TEXT("gender"), M.bFemale ? TEXT("f") : TEXT("m"));
			O->SetStringField(TEXT("dept"), M.Dept);
			O->SetStringField(TEXT("deck"), FString::FromInt(M.Deck));
			O->SetStringField(TEXT("home"), M.Home);
			Diners.Add(MakeShared<FJsonValueObject>(O));
		}
		TSharedRef<FJsonObject> Mess = MakeShared<FJsonObject>();
		Mess->SetArrayField(TEXT("diners"), Diners);
		Mess->SetStringField(TEXT("cook"), TEXT("mess_cook: Petty Officer Tomas Wren, the galley's chief cook, behind the serving line"));
		// what the galley's board says is served today (tools/art/ui_screens.py mess_menu)
		Mess->SetStringField(TEXT("menu"), TEXT("braised lamb with barley (from New Ravenna's hills); Aurelian rice with saffron and peppers; "
		                                        "greens from hydroponics bay B; real coffee, beans from Meridian"));
		Mess->SetStringField(TEXT("walls"), TEXT("the fleet's news on one big screen; on the other, IN MEMORIAM: the names of the Aquila's fallen"));
		S->SetObjectField(TEXT("mess"), Mess);
	}
	float Sum = 0.f;
	for (const auto& KV : PowerPct) { Sum += KV.Value; }
	S->SetStringField(TEXT("power_budget"), FString::Printf(TEXT("%.0f%% of %.0f%% allocated (six systems at 100%% = 600%%)"), Sum, PowerBudget));
	if (const UAstraLifeSubsystem* Life = GetWorld() ? GetWorld()->GetSubsystem<UAstraLifeSubsystem>() : nullptr; Life && Life->IsRunning())
	{
		S->SetObjectField(TEXT("life"), Life->SnapshotJson());   // the ship's clock, who does what, the teams, the people near the Captain
	}
	if (const UAstraTransporterSubsystem* Xport = GetWorld() ? GetWorld()->GetSubsystem<UAstraTransporterSubsystem>() : nullptr; Xport && Xport->IsReady())
	{
		S->SetObjectField(TEXT("transporter"), Xport->SnapshotJson());   // TELETRASPORTO: the Transporter Room's console, as the Chief reads it
	}
	if (const UAstraBoardSubsystem* Board = GetWorld() ? GetWorld()->GetSubsystem<UAstraBoardSubsystem>() : nullptr; Board && (Board->IsFightOn() || Board->IsAssaultOn()))
	{
		S->SetObjectField(TEXT("boarding"), Board->Snapshot());  // ABBORDAGGI: a boarding (boats in flight, or a fight aboard the Aquila or another ship): as the bridge knows it
		if (Board->IsFightOn())
		{
			S->SetObjectField(TEXT("_marines"), Board->MarinesPicture());   // (and as the marines' net reads it: squads, places, bulkheads; the `_` keeps it out of the bridge crew's board)
		}
	}
	else if (const UAstraBoardSubsystem* BoardOpts2 = GetWorld() ? GetWorld()->GetSubsystem<UAstraBoardSubsystem>() : nullptr; BoardOpts2 && BoardOpts2->IsReady())
	{
		const TSharedRef<FJsonObject> Opts = BoardOpts2->BoardingOptionsJson(0);            // what the Aquila's own boats could dock at now (empty when nothing: no tokens)
		if (Opts->Values.Num())
		{
			S->SetObjectField(TEXT("boarding_options"), Opts);
		}
	}
	if (const UAstraBoardSubsystem* Board = GetWorld() ? GetWorld()->GetSubsystem<UAstraBoardSubsystem>() : nullptr; Board && Board->IsReady())
	{
		S->SetObjectField(TEXT("arms"), Board->ArmsJson());      // ABBORDAGGI: where the Captain's weapons are, what he carries, the armourer's errand (the crew's tool: issue_weapon)
		if (const TSharedRef<FJsonObject> Boats = Board->BoatsJson(); Boats->Values.Num())
		{
			S->SetObjectField(TEXT("boarding_boats"), Boats);   // (and the Aquila's own boats and the marines fit to go in them: the crew's tool board_ship)
		}
	}
	return S;
}

void UAstraShipSubsystem::Tick(float DeltaTime)
{
	SCOPE_CYCLE_COUNTER(STAT_AstraShip);
	if (bShipLost)
	{
		// a dead ship: no heat, no ward, no helm; only the pods drifting and the loss's own timing
		TickAbandon(DeltaTime);
		UpdateAlertVisuals(DeltaTime);
		return;
	}
	TickInterior(DeltaTime);
	TickHeat(DeltaTime);
	// the Medbay: the doctors' rounds every minute (conditions change, the healed go back to duty, some die), the beds
	// follow the roster
	if ((CareT += DeltaTime) >= 60.f)
	{
		CareT = 0.f;
		TArray<FAstraCrewRoster::FNews> News;
		Roster.Care(1.f, CasualtyRng, News);
		for (const FAstraCrewRoster::FNews& N : News)
		{
			Event(N.Text, N.bReport);
		}
	}
	TickVisit(DeltaTime);
	TickAbandon(DeltaTime);
	if (bShipLost)
	{
		UpdateAlertVisuals(DeltaTime);
		return;                        // a dead ship: no helm, no heat, no damage control
	}
	if ((MessSyncT -= DeltaTime) <= 0.f)
	{
		MessSyncT = 5.f;
		SyncMess();
	}
	if ((WardSyncT -= DeltaTime) <= 0.f)
	{
		WardSyncT = 1.f;
		SyncWard();
	}
	if (bLaneControl)   // the Janus lane drives attitude and speed (DriveExternally)
	{
		TickDamage(DeltaTime);
		UpdateAlertVisuals(DeltaTime);
		return;
	}
	// helm intercept: re-aim at the target's lead point twice a second; broadside inside the standoff (with hysteresis)
	if (!InterceptId.IsEmpty() && (InterceptRetargetT -= DeltaTime) <= 0.f)
	{
		InterceptRetargetT = 0.5f;
		double Brg = 0.0, Mk = 0.0, Rng = 0.0;
		const UAstraBattleSubsystem* Battle = GetWorld() ? GetWorld()->GetSubsystem<UAstraBattleSubsystem>() : nullptr;
		if (Battle && Battle->ContactGeometry(InterceptId, Brg, Mk, Rng))
		{
			InterceptRangeKm = Rng;
			bBroadside = Rng >= 0.0 && (bBroadside ? Rng < InterceptStandoffKm + 1.5 : Rng < InterceptStandoffKm);
			float H = (float)Brg, M = (float)Mk;
			if (bBroadside)
			{
				const float A = WrapDeg(H + 90.f), B = WrapDeg(H - 90.f);
				H = FMath::Abs(DeltaDeg(HeadingDeg, A)) < FMath::Abs(DeltaDeg(HeadingDeg, B)) ? A : B;
				M = 0.f;
			}
			TargetHeadingDeg = WrapDeg(H);
			TargetMarkDeg = FMath::Clamp(M, -60.f, 60.f);
			bTurning = true;
		}
		else
		{
			Event(FString::Printf(TEXT("helm: intercept of %s ended, the contact is gone — steady on course %03.0f"), *InterceptId, HeadingDeg), true);
			InterceptId.Empty();
		}
	}
	// helm: coordinated turn at a capital-ship rate, pitch at half of it
	if (bTurning)
	{
		// the engines are at her stern: damaged, they turn her more slowly (GUERRA: PlayerEngineFactor, 1 = sound)
		const UAstraBattleSubsystem* HelmBattle = GetWorld() ? GetWorld()->GetSubsystem<UAstraBattleSubsystem>() : nullptr;
		const float Rate = 1.5f * DeltaTime * FMath::Max(0.3f, HelmBattle ? HelmBattle->PlayerEngineFactor() : 1.f);
		const float DH = DeltaDeg(HeadingDeg, TargetHeadingDeg);
		const float DM = TargetMarkDeg - MarkDeg;
		HeadingDeg = WrapDeg(HeadingDeg + FMath::Clamp(DH, -Rate, Rate));
		MarkDeg += FMath::Clamp(DM, -Rate * 0.5f, Rate * 0.5f);
		if (FMath::Abs(DeltaDeg(HeadingDeg, TargetHeadingDeg)) < 0.05f && FMath::Abs(TargetMarkDeg - MarkDeg) < 0.05f)
		{
			HeadingDeg = TargetHeadingDeg;
			MarkDeg = TargetMarkDeg;
			bTurning = false;
			if (InterceptId.IsEmpty() && !bAutoHelm)
			{
				Event(FString::Printf(TEXT("helm: turn complete, steady on course %03.0f mark %.0f"), HeadingDeg, MarkDeg), true);
			}
		}
		UpdateAttitudeVisuals();
	}
	// drive: speed follows the throttle (max 480 m/s at nominal engine power: a carrier cruiser, a little faster than
	// Mandate destroyers at cruise; engine power scales it)
	const UAstraBattleSubsystem* DriveBattle = GetWorld() ? GetWorld()->GetSubsystem<UAstraBattleSubsystem>() : nullptr;
	const float EngineHealth = DriveBattle ? DriveBattle->PlayerEngineFactor() : 1.f;   // her engines as the war has left them
	SpeedMps = FMath::FInterpTo(SpeedMps, ThrottlePct * 4.8f * (0.6f + 0.4f * PowerFactor(TEXT("engines"))) * (HeatPct > 90.f ? 0.85f : 1.f) * EngineHealth,
	                            DeltaTime, 0.2f);
	TickDamage(DeltaTime);
	UpdateAlertVisuals(DeltaTime);
}

void UAstraShipSubsystem::UpdateAttitudeVisuals()
{
	// the ship is the reference frame: turning the ship rotates the universe around it
	const FQuat Delta(FRotator(MarkDeg - Mark0, HeadingDeg - Heading0, 0.f));
	if (SkyMID)
	{
		FVector Cols[3];
		const FVector Basis[3] = {FVector::XAxisVector, FVector::YAxisVector, FVector::ZAxisVector};
		for (int32 j = 0; j < 3; ++j)
		{
			const FVector G = Delta.RotateVector(Basis[j]);   // system-frame direction of ship axis j
			Cols[j] = FVector(FVector::DotProduct(SkyAxis0[0], G), FVector::DotProduct(SkyAxis0[1], G), FVector::DotProduct(SkyAxis0[2], G));
		}
		const TCHAR* Names[3] = {TEXT("SkyAxisX"), TEXT("SkyAxisY"), TEXT("SkyAxisZ")};
		for (int32 i = 0; i < 3; ++i)
		{
			SkyMID->SetVectorParameterValue(Names[i], FLinearColor(Cols[0][i], Cols[1][i], Cols[2][i], 0.f));
		}
		const FVector SunNow = Delta.UnrotateVector(SunDir0);
		SkyMID->SetVectorParameterValue(TEXT("SunDirection"), FLinearColor(SunNow.X, SunNow.Y, SunNow.Z, 0.f));
		const FVector Axes[3] = {FVector(Cols[0][0], Cols[1][0], Cols[2][0]), FVector(Cols[0][1], Cols[1][1], Cols[2][1]),
		                         FVector(Cols[0][2], Cols[1][2], Cols[2][2])};
		UpdatePlanetLight(SunNow, Axes);
	}
	if (Sun && !bPlanetside)
	{
		// the star's light follows in quarter-degree steps: any turn of a directional light throws its whole shadow cache
		// away (every virtual shadow page drawn again, each frame of a turn), and a quarter of a degree moves a shadow on
		// the bridge floor by a centimetre
		// (the level's star is Stationary: it keeps the light the bridge and the ships were lit with, and a turn of it is refused with a log
		// line a frame — so it is not asked to. Made Movable it does follow the attitude, but a backlit cruiser is then black on the main
		// viewscreen, and a fill on lighting channel 1 cannot help: Nanite meshes ignore lighting channels, UE 5.8 NaniteShading.cpp)
		const FVector Want = (-Delta.UnrotateVector(SunDir0)).GetSafeNormal();
		if (Sun->GetRootComponent() && Sun->GetRootComponent()->Mobility == EComponentMobility::Movable &&
		    FVector::DotProduct(Want, Sun->GetActorForwardVector()) < FMath::Cos(FMath::DegreesToRadians(0.25f)))
		{
			Sun->SetActorRotation(Want.Rotation());
		}
		if (SpaceFill && SpaceFill->GetLightComponent())
		{
			const float SunLux = Sun->GetLightComponent() ? Sun->GetLightComponent()->Intensity : 1200.f;
			SpaceFill->GetLightComponent()->SetIntensity(SunLux * FMath::Max(0.f, CVarSpaceFill.GetValueOnGameThread()));
		}
	}
}

void UAstraShipSubsystem::SetPlanetside(bool bOn)
{
	if (bOn == bPlanetside)
	{
		return;
	}
	bPlanetside = bOn;
	if (SpaceSkyActor)
	{
		SpaceSkyActor->SetActorHiddenInGame(bOn);
	}
	if (SpaceSkyLight)
	{
		if (USkyLightComponent* SL = SpaceSkyLight->FindComponentByClass<USkyLightComponent>())
		{
			SL->SetVisibility(!bOn);
		}
	}
	// home: New Ravenna's hand-built zone; elsewhere: the world generated from its name (both in the same zone)
	const bool bHome = IsHomeWorld() && PlanetActors.Num() > 0;
	for (AActor* A : PlanetActors)
	{
		if (!A)
		{
			continue;
		}
		const bool bShow = bOn && bHome;
		A->SetActorHiddenInGame(!bShow);
		TInlineComponentArray<USceneComponent*> Cs(A);
		for (USceneComponent* C : Cs)
		{
			C->SetVisibility(bShow);
		}
		if (bShow)
		{
			if (USkyLightComponent* SL = A->FindComponentByClass<USkyLightComponent>())
			{
				SL->RecaptureSky();
			}
		}
	}
	if (!bHome && bOn)
	{
		if (AAstraWorldSurface* W = WorldBelow())
		{
			W->Show(true);
		}
	}
	else if (GeneratedWorld)
	{
		GeneratedWorld->Show(false);
	}
	if (PlanetLight && PlanetLight->GetLightComponent())
	{
		PlanetLight->GetLightComponent()->SetVisibility(!bOn);
	}
	if (SpaceFill && SpaceFill->GetLightComponent())
	{
		SpaceFill->GetLightComponent()->SetVisibility(!bOn);
	}
	if (Sun)
	{
		if (bOn && bHome)
		{
			// mid-afternoon over Port Aurelius
			Sun->SetActorRotation(FRotator(-38.f, 60.f, 0.f));
		}
		else if (bOn)
		{
			// every other world has its own hour: the height and the bearing of its sun come from its name
			FRandomStream R((int32)GetTypeHash(SurfaceWorldName().ToLower()));
			Sun->SetActorRotation(FRotator(-R.FRandRange(22.f, 56.f), R.FRandRange(0.f, 360.f), 0.f));
		}
		else
		{
			UpdateAttitudeVisuals();
		}
	}
	// a sunlit world wants a little less exposure than a bridge lit by its own lamps
	for (TActorIterator<APostProcessVolume> It(GetWorld()); It; ++It)
	{
		FPostProcessSettings& PS = It->Settings;
		if (bOn)
		{
			SpaceEV = PS.AutoExposureMinBrightness;
		}
		PS.AutoExposureMinBrightness = PS.AutoExposureMaxBrightness = bOn ? 8.3f : SpaceEV;
	}
	if (!bOn)
	{
		CaptainPlanetside.Reset();
	}
	UE_LOG(LogASTRA, Log, TEXT("[Ship] planetside %s"), bOn ? *FString::Printf(TEXT("on: %s"), *SurfaceWorldName()) : TEXT("off: space"));
}

const FAstraSystemLook* UAstraShipSubsystem::CurrentLook() const
{
	for (const auto& KV : Systems)
	{
		if (KV.Key.Equals(SystemName, ESearchCase::IgnoreCase))
		{
			return &KV.Value;
		}
	}
	return nullptr;
}

bool UAstraShipSubsystem::HasSurface() const
{
	if (IsHomeWorld())
	{
		return PlanetActors.Num() > 0;
	}
	const FAstraSystemLook* L = CurrentLook();
	return L && FAstraWorldGen::HasSurface(L->PlanetType);
}

FString UAstraShipSubsystem::SurfaceWorldName() const
{
	const FAstraSystemLook* L = CurrentLook();
	return IsHomeWorld() ? FString(TEXT("New Ravenna")) : (L ? L->PlanetName : SystemName + TEXT(" Prime"));
}

AAstraWorldSurface* UAstraShipSubsystem::WorldBelow()
{
	const FAstraSystemLook* L = CurrentLook();
	if (IsHomeWorld() || !L || !FAstraWorldGen::HasSurface(L->PlanetType))
	{
		return nullptr;
	}
	if (GeneratedWorld && GeneratedWorld->WorldName != L->PlanetName)
	{
		GeneratedWorld->Destroy();   // another system's world: the Aquila has moved on
		GeneratedWorld = nullptr;
	}
	if (!GeneratedWorld)
	{
		FActorSpawnParameters P;
		P.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
		GeneratedWorld = GetWorld()->SpawnActor<AAstraWorldSurface>(PlanetZone(), FRotator::ZeroRotator, P);
		if (GeneratedWorld)
		{
			const FAstraSectorSystem* Sec = FindSector(SystemName);
			GeneratedWorld->Build(L->PlanetName, L->PlanetType, Sec ? Sec->Owner : FString(), Sec ? Sec->PopM : 0.f);
			GeneratedWorld->Show(false);
		}
	}
	return GeneratedWorld;
}

FVector UAstraShipSubsystem::SurfaceSite() const
{
	if (!IsHomeWorld() && GeneratedWorld)
	{
		return GeneratedWorld->SiteWorld();
	}
	return PlanetZone() + FVector(1800.0, -1400.0, 191.4) * 100.0;   // Port Aurelius Field (art/export/newravenna/nr_sites.json, y mirrored)
}

FString UAstraShipSubsystem::SurfaceOwner() const
{
	if (IsHomeWorld())
	{
		return TEXT("astra");
	}
	const FAstraSectorSystem* S = FindSector(SystemName);
	return S ? S->Owner : FString();
}

FString UAstraShipSubsystem::SurfaceSiteName() const
{
	if (!IsHomeWorld())
	{
		return GeneratedWorld ? GeneratedWorld->SiteName() : FString::Printf(TEXT("the landing field on %s"), *SurfaceWorldName());
	}
	return TEXT("Port Aurelius Field");
}

float UAstraShipSubsystem::SurfaceSeaZ() const
{
	if (!IsHomeWorld())
	{
		return GeneratedWorld ? GeneratedWorld->SeaWorldZ() : -1.0e12f;
	}
	return PlanetZone().Z;
}

void UAstraShipSubsystem::UpdateAlertVisuals(float DeltaTime)
{
	AlertTime += DeltaTime;
	const float TargetRed = Alert == EAstraAlert::Red ? 1.f : 0.f;
	const float TargetYellow = Alert == EAstraAlert::Yellow ? 1.f : 0.f;
	AlertBlend = FMath::FInterpTo(AlertBlend, TargetRed, DeltaTime, 3.f);
	YellowBlend = FMath::FInterpTo(YellowBlend, TargetYellow, DeltaTime, 3.f);
	float LightLevel = FMath::Lerp(1.f, 0.45f, AlertBlend) * FMath::Lerp(1.f, 0.85f, YellowBlend);
	if (FlickerTime > 0.f)
	{
		FlickerTime -= DeltaTime;
		LightLevel *= 0.35f + 0.65f * (FMath::FRand() > 0.45f ? 1.f : 0.f);
	}
	if (RailDraw > 0.f)
	{
		// the rails charge: a quick sag (to about 60%) and a slower recovery over half a second
		const float Sag = RailDraw > 0.8f ? (1.f - RailDraw) / 0.2f : RailDraw / 0.8f;
		LightLevel *= 1.f - 0.4f * Sag;
		RailDraw = FMath::Max(0.f, RailDraw - DeltaTime / 0.55f);
	}
	const FLinearColor AlertColor = FMath::Lerp(FLinearColor(1.f, 0.62f, 0.1f), FLinearColor(1.f, 0.04f, 0.02f), AlertBlend);
	const float Mix = FMath::Max(AlertBlend, YellowBlend);
	if (ShipMPC)
	{
		UKismetMaterialLibrary::SetScalarParameterValue(GetWorld(), ShipMPC, TEXT("AlertMix"), Mix);
		UKismetMaterialLibrary::SetScalarParameterValue(GetWorld(), ShipMPC, TEXT("AlertRed"), AlertBlend / FMath::Max(AlertBlend + YellowBlend, 1e-3f));
		UKismetMaterialLibrary::SetVectorParameterValue(GetWorld(), ShipMPC, TEXT("AlertColor"), AlertColor);
		UKismetMaterialLibrary::SetScalarParameterValue(GetWorld(), ShipMPC, TEXT("AlertPulse"), AlertBlend);
		UKismetMaterialLibrary::SetScalarParameterValue(GetWorld(), ShipMPC, TEXT("LightLevel"), LightLevel);
	}
	// the damage inside the ship reaches the older rooms' lights by the compartment each stands in (the lamp pool does the same for the decks')
	if (!bShipLightCompsKnown && Interior.IsReady())
	{
		bShipLightCompsKnown = true;
		ShipLightComp.Reset();
		for (const ALight* L : ShipLights)
		{
			ShipLightComp.Add(L ? InteriorCompOf(L->GetActorLocation()) : INDEX_NONE);
		}
		ShipLightUnsteady.Init(1.f, ShipLights.Num());
	}
	ShipLightFlickT += DeltaTime;
	const bool bShipFlicker = ShipLightFlickT >= 0.08f;
	if (bShipFlicker)
	{
		ShipLightFlickT = 0.f;
	}
	for (int32 i = 0; i < ShipLights.Num(); ++i)
	{
		if (ULightComponent* LC = ShipLights[i] ? ShipLights[i]->GetLightComponent() : nullptr)
		{
			float Share = LightLevel;
			FLinearColor Color = FMath::Lerp(ShipLightColorBase[i], FLinearColor(1.f, 0.55f, 0.5f), AlertBlend * 0.35f);
			if (bShipLightCompsKnown && ShipLightComp.IsValidIndex(i) && ShipLightComp[i] != INDEX_NONE && Interior.Find(ShipLightComp[i]))
			{
				const FAstraDmgLight D = Interior.LightOf(ShipLightComp[i]);
				if (bShipFlicker)
				{
					ShipLightUnsteady[i] = D.Flicker > 0.f && FMath::FRand() < D.Flicker * 0.55f ? FMath::Lerp(0.05f, 0.55f, FMath::FRand()) : 1.f;
				}
				Share = (D.Mains * LightLevel + D.Strips) * ShipLightUnsteady[i];
				Color = D.Mix > 0.f ? FMath::Lerp(Color, D.Tint, D.Mix) : Color;
			}
			LC->SetIntensity(ShipLightBase[i] * Share);
			LC->SetLightColor(Color);
		}
	}
}

// ------------------------------------------------------------------------------------------------ the damage inside (DISTRUZIONE)
namespace
{
	// the Aquila's hull as the war model boxes it (data/war/classes.json: x from the stern to the bow end, the width, the height)
	constexpr double ShipBoxMid = -7.53, ShipBoxHx = 399.73, ShipBoxHy = 69.857, ShipBoxHz = 46.2;
	constexpr double ShipHullToPlanX = 172.0;       // the plan's frame is the hull mesh's, moved (docs/NAVE.md)

	/** The word a hazard's injury is filed under at the roster (its table of injuries). */
	const TCHAR* ShipHarmCause(EAstraDmgHarm C)
	{
		switch (C)
		{
		case EAstraDmgHarm::Decompression: return TEXT("hull breach");
		case EAstraDmgHarm::Fire:
		case EAstraDmgHarm::Smoke:         return TEXT("fire");
		case EAstraDmgHarm::Electric:      return TEXT("conduit damage");
		default:                           return TEXT("");
		}
	}
}

void UAstraShipSubsystem::StartInterior()
{
	// the plan's rooms and doors are read on a worker: the game does not wait for them (the first blow comes minutes later)
	bInteriorLoading = true;
	InteriorFuture = Async(EAsyncExecution::ThreadPool, []() -> TSharedPtr<FAstraDamageMap>
	{
		TSharedPtr<FAstraDamageMap> M = MakeShared<FAstraDamageMap>();
		FString Err;
		if (!M->Load(Err))
		{
			UE_LOG(LogASTRA, Log, TEXT("[Damage] %s: nothing breaks inside the hull"), *Err);
			return nullptr;
		}
		return M;
	});
}

int32 UAstraShipSubsystem::InteriorCompOf(const FVector& Cm) const
{
	const UAstraShipPlan* Plan = GetWorld() ? GetWorld()->GetSubsystem<UAstraShipPlan>() : nullptr;
	const FAstraPlanCompartment* C = Plan ? Plan->CompartmentAt(Cm) : nullptr;
	return C && Interior.IsReady() ? Interior.GetMap().CompByName.FindRef(FName(*C->Id), INDEX_NONE) : INDEX_NONE;
}

AAstraDoor* UAstraShipSubsystem::DoorActorOf(FName DoorId)
{
	if (!Interior.IsReady() || !GetWorld())
	{
		return nullptr;
	}
	if (const TWeakObjectPtr<AAstraDoor>* A = DoorActors.Find(DoorId))
	{
		if (A->IsValid())
		{
			return A->Get();
		}
	}
	// the doors of the plan, by where they stand (the level's actors are labelled with the plan's ids, but a packaged game has no labels): among the door
	// actors that are in the world now (a deck that is not loaded has none)
	const int32* Di = Interior.GetMap().DoorByName.Find(DoorId);
	if (!Di)
	{
		return nullptr;
	}
	const FVector& At = Interior.GetMap().Doors[*Di].PosCm;
	for (const TWeakObjectPtr<AAstraDoor>& W : AstraDoors::Loaded())
	{
		AAstraDoor* D = W.Get();
		if (D && FVector::DistSquared(At, D->GetActorLocation()) < 40.0 * 40.0)
		{
			DoorActors.FindOrAdd(DoorId) = D;
			return D;
		}
	}
	return nullptr;
}

AAstraBridgeFX* UAstraShipSubsystem::GetBridgeFX() const
{
	return BridgeFX;
}

void UAstraShipSubsystem::Deinitialize()
{
	AstraDoors::OnPlaced().Remove(DoorPlacedHandle);
	Super::Deinitialize();
}

void UAstraShipSubsystem::OnDoorPlaced(AAstraDoor* Door)
{
	// a deck has streamed in: a door of it that stands where a pressure bulkhead is sealed shuts (the seal was made while the deck was not there to shut)
	if (!Door || !Interior.IsReady())
	{
		return;
	}
	const int32 Di = Interior.GetMap().DoorNear(Door->GetActorLocation(), 40.f);
	if (Di == INDEX_NONE)
	{
		return;
	}
	DoorActors.FindOrAdd(Interior.GetMap().Doors[Di].Id) = Door;
	if (Interior.SealedDoors().Contains(Di) || ExternalSeals.Contains(Di))
	{
		ApplyDoorSeal(Di, Door, true);
	}
}

void UAstraShipSubsystem::ApplyDoorSeal(int32 DoorIndex, AAstraDoor* Door, bool bSealed)
{
	// shut, and it stays shut; opened, it goes back to what the level made it (a door the level keeps locked does not come unlocked because a bulkhead did)
	if (bSealed)
	{
		if (DoorIndex != INDEX_NONE && !DoorLockMemory.Contains(DoorIndex))
		{
			DoorLockMemory.Add(DoorIndex, Door->bLocked);
		}
		Door->bLocked = true;
	}
	else
	{
		bool bWas = false;
		if (DoorIndex != INDEX_NONE && DoorLockMemory.RemoveAndCopyValue(DoorIndex, bWas))
		{
			Door->bLocked = bWas;
		}
		else
		{
			Door->bLocked = false;
		}
	}
	if (UAstraDamageFx* Fx = GetWorld() ? GetWorld()->GetSubsystem<UAstraDamageFx>() : nullptr)
	{
		Fx->DressDoor(Door, bSealed);
	}
}

void UAstraShipSubsystem::ShutBulkhead(FName Id, bool bSealed)
{
	if (UAstraShipPlan* Plan = GetWorld() ? GetWorld()->GetSubsystem<UAstraShipPlan>() : nullptr)
	{
		Plan->SetDoorSealed(Id.ToString(), bSealed);
	}
	const int32 Di = Interior.IsReady() ? Interior.GetMap().DoorByName.FindRef(Id, INDEX_NONE) : INDEX_NONE;
	if (AAstraDoor* A = DoorActorOf(Id))
	{
		ApplyDoorSeal(Di, A, bSealed);
	}
	if (UAstraDamageFx* Fx = GetWorld() ? GetWorld()->GetSubsystem<UAstraDamageFx>() : nullptr; Fx && Di != INDEX_NONE)
	{
		Fx->OnBulkhead(Interior.GetMap().Doors[Di].PosCm, bSealed);
	}
}

void UAstraShipSubsystem::SealBulkhead(FName DoorId, bool bSealed)
{
	// the fight's seals (ABBORDAGGI): the door of the plan and its actor, the people's routes; remembered for a deck that streams in later
	if (Interior.IsReady())
	{
		const int32 Di = Interior.GetMap().DoorByName.FindRef(DoorId, INDEX_NONE);
		if (Di != INDEX_NONE)
		{
			if (bSealed)
			{
				ExternalSeals.Add(Di);
			}
			else
			{
				ExternalSeals.Remove(Di);
			}
		}
	}
	ShutBulkhead(DoorId, bSealed);
	if (UAstraLifeSubsystem* Life = GetWorld() ? GetWorld()->GetSubsystem<UAstraLifeSubsystem>() : nullptr; Life && Life->IsRunning())
	{
		Life->Sim().PlanChanged();                       // the routes being walked may cross a door that has shut (the damage model tells VITA itself)
	}
}

FString UAstraShipSubsystem::HarmPerson(int32 RosterIdx, bool bKill, const FString& Cause)
{
	const TArray<FAstraCrewman>& P = Roster.Get();
	if (!P.IsValidIndex(RosterIdx) || P[RosterIdx].Status != 0)
	{
		return FString();                                // hurt or fallen already
	}
	const TArray<int32> Single = {RosterIdx};
	const FString Words = Roster.Casualties(P[RosterIdx].Deck, bKill ? 0 : 1, bKill ? 1 : 0, CasualtyRng, Cause, &Single);
	if (!Words.IsEmpty())
	{
		Event(FString::Printf(TEXT("casualties: %s"), *Words), false);
	}
	return Words;
}

void UAstraShipSubsystem::TickInterior(float DeltaTime)
{
	if (bInteriorLoading && InteriorFuture.IsReady())
	{
		bInteriorLoading = false;
		TSharedPtr<FAstraDamageMap> M = InteriorFuture.Get();
		if (M.IsValid())
		{
			FAstraDmgHooks H;
			H.Event = [this](const FString& Text, bool bReport) { Event(Text, bReport); };
			H.PeopleIn = [this](const FAstraDmgComp& C, TArray<FAstraDmgPerson>& Out)
			{
				const UAstraLifeSubsystem* Life = GetWorld() ? GetWorld()->GetSubsystem<UAstraLifeSubsystem>() : nullptr;
				const int32* Ci = Life && Life->IsRunning() ? Life->Sim().GetMap().CompByName.Find(C.Id) : nullptr;
				if (!Ci)
				{
					return;
				}
				TArray<int32> People;
				Life->Sim().PeopleInComp(*Ci, People);
				for (const int32 P : People)
				{
					const FAstraLifePerson& Pr = Life->Sim().Person(P);
					FAstraDmgPerson X;
					X.Roster = Pr.Roster;
					X.PosCm = Pr.Pos;
					X.bSuited = Pr.Party != INDEX_NONE;       // a damage-control party at work wears suits
					X.bAtPost = Pr.Act == EAstraLifeAct::Battle || Pr.Act == EAstraLifeAct::Duty;
					Out.Add(X);
				}
			};
			H.Harm = [this](int32 Who, bool bKill, EAstraDmgHarm Cause) -> FString
			{
				const TArray<FAstraCrewman>& P = Roster.Get();
				if (!P.IsValidIndex(Who) || P[Who].Status != 0)
				{
					return FString();                        // already hurt or fallen: nobody else is taken in their place
				}
				const TArray<int32> Single = {Who};
				return Roster.Casualties(P[Who].Deck, bKill ? 0 : 1, bKill ? 1 : 0, CasualtyRng, ShipHarmCause(Cause), &Single);
			};
			H.SealDoor = [this](FName Id, bool bSealed) { ShutBulkhead(Id, bSealed); };
			H.PlanChanged = [this]()
			{
				if (UAstraLifeSubsystem* Life = GetWorld() ? GetWorld()->GetSubsystem<UAstraLifeSubsystem>() : nullptr; Life && Life->IsRunning())
				{
					Life->Sim().PlanChanged();                 // the routes being walked may cross a door that has shut
				}
			};
			H.AddHeat = [this](float Pct) { AddHeat(Pct); };
			H.StructureBurn = [this](float Points)
			{
				if (UAstraBattleSubsystem* B = GetWorld() ? GetWorld()->GetSubsystem<UAstraBattleSubsystem>() : nullptr)
				{
					B->PlayerInternalDamage(Points);
				}
			};
			H.Alert = [this]() { return Alert == EAstraAlert::Red ? 2 : (Alert == EAstraAlert::Yellow ? 1 : 0); };
			Interior.Init(M.ToSharedRef(), H, GAstraDeterministic ? 7001 : (int32)(FDateTime::Now().GetTicks() & 0x7fffffff));
		}
	}
	if (!Interior.IsReady())
	{
		return;
	}
	{
		SCOPE_CYCLE_COUNTER(STAT_AstraInterior);
		const double T0 = FPlatformTime::Seconds();
		Interior.Tick(DeltaTime, Damage);
		const float Ms = (float)((FPlatformTime::Seconds() - T0) * 1000.0);
		InteriorMsAvg = InteriorMsAvg * 0.98f + Ms * 0.02f;
		InteriorMsMax = FMath::Max(InteriorMsMax * 0.9995f, Ms);
	}
	FlushHitReport(false);
	// a section of the hull the war has gutted takes what lived in it (the war's structure is the war's; the rooms and the people are ours)
	if ((GutT -= DeltaTime) <= 0.f)
	{
		GutT = 1.f;
		const UAstraBattleSubsystem* Battle = GetWorld() ? GetWorld()->GetSubsystem<UAstraBattleSubsystem>() : nullptr;
		UAstraBattleSubsystem::FDamageView V;
		if (Battle && Battle->GetDamageView(TEXT("AQUILA"), V))
		{
			static const TCHAR* Names[3] = {TEXT("bow"), TEXT("mid"), TEXT("stern")};
			const float Bow = (float)((V.CutBowX - ShipHullToPlanX) * 100.0), Stern = (float)((V.CutSternX - ShipHullToPlanX) * 100.0);
			for (int32 Sec = 0; Sec < 3; ++Sec)
			{
				if (V.bGutted[Sec] && !(GutDone & (1 << Sec)))
				{
					GutDone |= 1 << Sec;
					FAstraImpactResult R;
					Interior.GutSection(Sec == 0 ? Bow : (Sec == 1 ? Stern : -1.0e7f), Sec == 0 ? 1.0e7f : (Sec == 1 ? Bow : Stern), Names[Sec], R);
				}
				else if (!V.bGutted[Sec])
				{
					GutDone &= ~(1 << Sec);            // patched up in the war's books (the rooms stay lost until the yards)
				}
			}
		}
	}
	TickCaptainFate(DeltaTime);
}

void UAstraShipSubsystem::ResetInterior()
{
	Interior.Reset();
	Damage.RemoveAll([](const FAstraDamage& D) { return D.Comp != INDEX_NONE; });
	HitReport = FHitReport();
}

void UAstraShipSubsystem::TickCaptainFate(float DeltaTime)
{
	APlayerController* PC = UGameplayStatics::GetPlayerController(this, 0);
	const APawn* Pawn = PC ? PC->GetPawn() : nullptr;
	const ACharacter* Walker = Cast<ACharacter>(Pawn);
	if (CaptainFate == 2)
	{
		// the end: the card, then the last save
		if ((CaptainFateT += DeltaTime) > 9.f && GetWorld())
		{
			CaptainFateT = -1.0e6f;
			const UAstraCampaignSubsystem* Camp = GetWorld()->GetSubsystem<UAstraCampaignSubsystem>();
			UGameplayStatics::OpenLevel(GetWorld(), FName(*UGameplayStatics::GetCurrentLevelName(GetWorld())), true,
			                            Camp && Camp->HasSave() ? TEXT("astra_campaign=continue") : TEXT("astra_campaign=new"));
		}
		return;
	}
	if ((CaptainProbeT -= DeltaTime) > 0.f)
	{
		return;
	}
	const float Dt = 0.25f + FMath::Max(0.f, -CaptainProbeT);
	CaptainProbeT = 0.25f;
	// a Captain who is not walking the ship (in a Falcon, on a planet, in a pod) is out of its compartments' reach
	const bool bAboard = bTestCaptain || (Walker && !Cast<AAstraFighterPawn>(Pawn) && !bPlanetside && !bAbandon);
	const FVector Feet = bTestCaptain ? TestCaptainCm : (bAboard ? Pawn->GetActorLocation() : FVector::ZeroVector);
	const int32 Comp = bAboard ? InteriorCompOf(Feet) : INDEX_NONE;
	Interior.TickCaptain(Dt, Comp, Feet);
	const FAstraDmgCaptain& Cap = Interior.Captain();
	const FAstraDmgState* Here = Comp != INDEX_NONE ? Interior.Find(Comp) : nullptr;
	const FString Place = Comp != INDEX_NONE ? Interior.GetMap().Describe(Comp) : FString(TEXT("somewhere aboard"));
	APlayerCameraManager* Cam = PC ? PC->PlayerCameraManager : nullptr;
	if (CaptainFate == 0)
	{
		if (Cam)
		{
			// the air going, the smoke, the pain: the edges of the sight close in (and sound goes thin) as they get worse
			const float PerilFade = Cap.State == FAstraDmgCaptain::EState::Well ? 0.f : FMath::Clamp((Cap.Peril - 0.3f) / 0.7f, 0.f, 0.9f) * 0.8f;
			// thick smoke closes the room in grey-brown before it hurts him (the puffs seen from the inside are not drawn: the eye is in them)
			const float SmokeFade = Here ? FMath::Clamp(Here->Smoke - 0.2f, 0.f, 1.f) * 0.6f : 0.f;
			const float Fade = FMath::Max(PerilFade, SmokeFade);
			if (Fade > 0.01f || bCaptainFadeSet)
			{
				Cam->SetManualCameraFade(Fade, PerilFade >= SmokeFade ? FLinearColor::Black : FLinearColor(0.07f, 0.06f, 0.05f), PerilFade >= SmokeFade);
				bCaptainFadeSet = Fade > 0.01f;
			}
		}
		if (Cap.State == FAstraDmgCaptain::EState::Down)
		{
			CaptainFate = 1;
			CaptainFateT = 0.f;
			if (PC)
			{
				PC->SetIgnoreMoveInput(true);
				PC->SetIgnoreLookInput(true);
			}
			if (Cam)
			{
				Cam->SetManualCameraFade(1.f, FLinearColor::Black, true);
				bCaptainFadeSet = true;
			}
			Event(FString::Printf(TEXT("ship: the Captain is down — %s in %s; the XO has the conn and is sending the nearest damage-control team to the Captain"), *Cap.Cause, *Place), true);
		}
	}
	else if (CaptainFate == 1)
	{
		CaptainFateT += Dt;
		if (Cap.State == FAstraDmgCaptain::EState::Dead)
		{
			CaptainFate = 2;
			CaptainFateT = 0.f;
			if (AASTRAPlayerController* AstraPC = Cast<AASTRAPlayerController>(PC))
			{
				AstraPC->StoryCard(TEXT("THE CAPTAIN IS LOST"), FString::Printf(TEXT("ASN AQUILA · %s · %s"), *Place.ToUpper(), *Cap.Why.ToUpper()), 7.f, true);
			}
			Event(FString::Printf(TEXT("ship: the Captain is dead — %s. The Executive Officer has command of the Aquila"), *Cap.Why), true);
			UE_LOG(LogASTRA, Log, TEXT("[Damage] the Captain %s"), *Cap.Why);
			return;
		}
		// carried out once the compartment is fit again or a team has reached it
		const bool bFit = !Here || (Here->Air > 0.6f && Here->Fire < 0.2f && Here->Smoke < 0.5f && Here->Heat < 0.45f);
		if (CaptainFateT > 6.f && !Cap.bContested && (bFit || (Here && Here->TeamT > 0.f)))
		{
			Interior.CaptainRescued();
			CaptainFate = 0;
			if (PC)
			{
				PC->ResetIgnoreMoveInput();
				PC->ResetIgnoreLookInput();
			}
			if (Cam)
			{
				Cam->SetManualCameraFade(0.f, FLinearColor::Black, false);
				Cam->StartCameraFade(1.f, 0.f, 4.f, FLinearColor::Black, false, false);
				bCaptainFadeSet = false;
			}
			if (Pawn)
			{
				for (TActorIterator<AAstraHangar> It(GetWorld()); It; ++It)
				{
					if (!It->MedbayLanding.IsNearlyZero())
					{
						const_cast<APawn*>(Pawn)->SetActorLocation(It->MedbayLanding + FVector(0, 0, 100), false, nullptr, ETeleportType::TeleportPhysics);
						break;
					}
				}
			}
			Event(TEXT("medbay: the Captain was carried out alive and is awake in the Medbay, winded and hurt; the XO hands the conn back"), true);
		}
	}
}

void UAstraShipSubsystem::FlushHitReport(bool bForce)
{
	if (HitReport.Hits == 0 || !GetWorld())
	{
		return;
	}
	const double Now = GetWorld()->GetTimeSeconds();
	if (!bForce && Now - LastHitReport < 6.0)
	{
		return;
	}
	LastHitReport = Now;
	const UAstraBattleSubsystem* Battle = GetWorld()->GetSubsystem<UAstraBattleSubsystem>();
	const int32 Sh = Battle ? FMath::RoundToInt(100.f * Battle->PlayerShieldFraction()) : 0;
	const int32 Hu = Battle ? FMath::RoundToInt(100.f * Battle->PlayerHullFraction()) : 100;
	FString Where = FString::Join(HitReport.Lines, TEXT("; "));
	if (HitReport.People.Num())
	{
		const int32 Shown = FMath::Min(HitReport.People.Num(), 3);
		TArray<FString> Names;
		for (int32 i = 0; i < Shown; ++i)
		{
			Names.Add(HitReport.People[i]);
		}
		Where += (Where.IsEmpty() ? TEXT("casualties: ") : TEXT(" — casualties: ")) + FString::Join(Names, TEXT("; "));
		if (HitReport.People.Num() > Shown)
		{
			Where += FString::Printf(TEXT("; and %d more"), HitReport.People.Num() - Shown);
		}
	}
	Event(!Where.IsEmpty() ? FString::Printf(TEXT("damage report: we've been hit — %s; shields %d%%, hull %d%%"), *Where, Sh, Hu)
	                       : FString::Printf(TEXT("shields took a hit, holding at %d%%"), Sh), true);
	HitReport = FHitReport();
}

void UAstraShipSubsystem::TickDamage(float DeltaTime)
{
	// the damage-control teams: they walk (the ship's clock for it is VITA's own estimate of the walk), then work the hazard down; what the
	// damage model owns they work through it (a fire goes out when the fire is out), what the ship owns (a radiator wing) they work by the clock
	UAstraBattleSubsystem* Battle = GetWorld() ? GetWorld()->GetSubsystem<UAstraBattleSubsystem>() : nullptr;
	for (int32 i = Damage.Num() - 1; i >= 0; --i)
	{
		if (i >= Damage.Num())
		{
			continue;
		}
		FAstraDamage& D = Damage[i];
		if (D.Team < 0)
		{
			continue;
		}
		if (D.Travel > 0.f)
		{
			D.Travel -= DeltaTime;
			continue;
		}
		if (Battle)
		{
			// a team at work on the spot also mends what the war broke there: engines, sensors, mounts (GUERRA)
			Battle->RepairPlayerSystems(0.006f * DeltaTime);
		}
		if (D.Comp != INDEX_NONE && Interior.IsReady())
		{
			Interior.Work(D, DeltaTime, Damage);
			continue;                                                       // (it closes the incident itself)
		}
		D.Progress += DeltaTime / D.Work;
		if (D.Progress >= 1.f)
		{
			if (D.Kind == TEXT("radiator damage"))
			{
				RadiatorHealth = FMath::Min(1.f, RadiatorHealth + 0.25f);
			}
			const FString Text = FString::Printf(TEXT("damage control: the %s at %s %s (team %d free again)"), *D.Kind, *D.Where(),
			                                     D.Kind == TEXT("radiator damage") ? TEXT("is repaired, the panel sheds heat again") : TEXT("is repaired, power restored"), D.Team + 1);
			Damage.RemoveAt(i);
			Event(Text, false);
		}
	}
}

void UAstraShipSubsystem::RadiatorHit(const FAstraHullHit& Hit)
{
	// The radiator wings stand out along the flanks aft (sections E to G of Deck 7): a blow that lands on a flank, or on the top, over them wears
	// one down, and when what has landed there is enough one is torn, though no sooner than 20 s after the last (a hit lands near the wreck of the last).
	if (!bRadiatorsOut || RadiatorHealth < 0.3f || !GetWorld())
	{
		return;
	}
	const bool bWing = (Hit.Facing == 2 || Hit.Facing == 3 || Hit.Facing == 4) && Hit.HullM.X >= -312.0 && Hit.HullM.X <= -148.0;
	if (!bWing)
	{
		return;
	}
	RadiatorStress += Hit.Felt / 70.f;
	const double Now = GetWorld()->GetTimeSeconds();
	if (RadiatorStress < 1.f || Now - LastRadiatorTear < 20.0)
	{
		return;
	}
	// which wing: by where along the hull it struck
	const double PlanX = Hit.HullM.X - ShipHullToPlanX;
	const TCHAR First = PlanX > -384.0 ? TEXT('E') : (PlanX > -440.0 ? TEXT('F') : TEXT('G'));
	for (int32 k = 0; k < 3; ++k)
	{
		const TCHAR Sec = (TCHAR)(TEXT('E') + (First - TEXT('E') + k) % 3);
		if (Damage.ContainsByPredicate([Sec](const FAstraDamage& X) { return X.Kind == TEXT("radiator damage") && X.Section == Sec; }))
		{
			continue;
		}
		FAstraDamage D;
		D.Id = Interior.IsReady() ? Interior.NewIncidentId() : NextDamageId++;
		D.Deck = 7;                                   // the radiators are Engineering & Power's (Deck 7, sections E-G)
		D.Section = Sec;
		D.Kind = TEXT("radiator damage");
		D.Place = TEXT("radiator wing");
		D.Work = 30.f;
		// the pump room that serves the wing, where the plan has it (a party goes there)
		if (Interior.IsReady())
		{
			for (const int32 C : Interior.GetMap().Hosts[(int32)EAstraDmgSystem::PowerBus])
			{
				const FAstraDmgComp& Cm = Interior.GetMap().Comps[C];
				if (Cm.Deck == 7 && Cm.Section == Sec && Cm.Name.Contains(TEXT("Radiator")))
				{
					D.CompId = Cm.Id;
					break;
				}
			}
		}
		RadiatorStress = 0.f;
		LastRadiatorTear = Now;
		RadiatorHealth = FMath::Max(0.25f, RadiatorHealth - 0.25f);
		Damage.Add(D);
		Event(FString::Printf(TEXT("engineering: a radiator wing torn by the hit at %s — the radiators shed %.0f %% of their heat until damage control repairs them"), *D.Where(), 100.f * RadiatorHealth), true);
		return;
	}
}

void UAstraShipSubsystem::OnHullHit(const FAstraHullHit& Hit)
{
	FlickerTime = 0.6f;
	const double HitAt = GetWorld()->GetTimeSeconds();
	FAstraImpactResult Res;
	if (Interior.IsReady())
	{
		Interior.Impact(Hit, Res);
		if (UAstraDamageFx* Fx = GetWorld() ? GetWorld()->GetSubsystem<UAstraDamageFx>() : nullptr)
		{
			Fx->OnBlow(Res, Hit.Felt);
		}
	}
	// the shock runs through the frame: a fixture or a console on the bridge shorts out, the more the harder the blow and the nearer the bridge. A breaker
	// that has just tripped holds for a while: at most one every 8 s, a heavy shock after 2 s
	if (Hit.Felt > 8.f && BridgeFX)
	{
		const double DistM = (Hit.HullM - FVector(ShipHullToPlanX, 0.0, 62.0)).Size();
		const float Shock = FMath::Clamp(Hit.Felt / 45.f, 0.f, 1.3f) / (1.f + FMath::Square((float)DistM / 80.f));
		if (Shock >= 0.2f && HitAt - LastBridgeBurst > (Shock > 0.6f ? 2.0 : 8.0))
		{
			BridgeFX->RandomBurst(FMath::Clamp(Shock, 0.2f, 1.f));
			LastBridgeBurst = HitAt;
		}
	}
	if (Hit.Felt > 5.f)
	{
		RadiatorHit(Hit);
	}
	// what it did, in one report for the blows of the last seconds
	for (const FString& L : Res.Lines)
	{
		HitReport.Lines.AddUnique(L);
	}
	for (const FString& P : Res.People)
	{
		HitReport.People.Add(P);
	}
	++HitReport.Hits;
	FlushHitReport(false);
}

void UAstraShipSubsystem::OnHullHit(float HullDamage, float ShieldDamage, const FVector& FromDir)
{
	// a blow that is only a size and a direction (the console's test hits): it lands on the face that looks the way it came from, at a point of it
	FAstraHullHit H;
	const FVector Out = (-FromDir).GetSafeNormal();
	H.Facing = AstraFacingOf(Out);
	FVector B(FMath::FRandRange(-0.9f, 0.9f), FMath::FRandRange(-0.9f, 0.9f), FMath::FRandRange(-0.9f, 0.9f));
	switch (H.Facing)
	{
	case 0: B.X = 1.f; break;
	case 1: B.X = -1.f; break;
	case 2: B.Y = -1.f; break;
	case 3: B.Y = 1.f; break;
	case 4: B.Z = 1.f; break;
	default: B.Z = -1.f; break;
	}
	H.Box = B;
	H.HullM = FVector(ShipBoxMid + B.X * ShipBoxHx, B.Y * ShipBoxHy, B.Z * ShipBoxHz);
	H.Dir = FromDir.GetSafeNormal();
	H.Section = H.HullM.X > 236.0 ? 0 : (H.HullM.X < -105.0 ? 2 : 1);
	H.Damage = HullDamage + ShieldDamage;
	H.ShieldTook = ShieldDamage;
	H.StructTook = HullDamage;
	H.Felt = HullDamage;
	OnHullHit(H);
}

float UAstraShipSubsystem::PowerFactor(const FString& System) const
{
	// the allocation the crew set, times what the ship's distribution still carries of it: the compartments the systems run through that have been hit
	// (docs/DISTRUZIONE.md; the backup ring keeps half of an allocation even when every one of them is lost)
	const float* P = PowerPct.Find(System);
	const float F = (P ? *P : 100.f) / 100.f;
	float Load = 1.f;
	if (System == TEXT("shields"))
	{
		// TELETRASPORTO: a transporter cycle's 40 MW come out of the shields (BIBBIA §4)
		if (const UAstraTransporterSubsystem* Xport = GetWorld() ? GetWorld()->GetSubsystem<UAstraTransporterSubsystem>() : nullptr)
		{
			Load = Xport->ShieldLoadFactor();
		}
	}
	return F * Interior.CategoryFactor(System) * Load;
}

int32 UAstraShipSubsystem::FreeDamageTeam() const
{
	for (int32 T = 0; T < NumDamageTeams; ++T)
	{
		if (!Damage.ContainsByPredicate([T](const FAstraDamage& D) { return D.Team == T; }))
		{
			return T;
		}
	}
	return -1;
}

FString UAstraShipSubsystem::DamageSummary() const
{
	FString Out;
	for (const FAstraDamage& D : Damage)
	{
		Out += FString::Printf(TEXT("%s%s %s%s"), Out.IsEmpty() ? TEXT("") : TEXT("; "), *D.Where(), *D.Kind,
		                       D.Team >= 0 ? *FString::Printf(TEXT(" (team %d)"), D.Team + 1) : TEXT(" (unattended)"));
	}
	return Out.IsEmpty() ? TEXT("none") : Out;
}

void UAstraShipSubsystem::PlayAlertSound(EAstraAlert NewAlert)
{
	const TCHAR* Path = NewAlert == EAstraAlert::Red ? TEXT("/Game/ASTRA/Audio/SW_Alert_Red.SW_Alert_Red")
	                  : NewAlert == EAstraAlert::Yellow ? TEXT("/Game/ASTRA/Audio/SW_Alert_Yellow.SW_Alert_Yellow")
	                  : TEXT("/Game/ASTRA/Audio/SW_Alert_Clear.SW_Alert_Clear");
	if (USoundBase* S = LoadObject<USoundBase>(nullptr, Path))
	{
		UGameplayStatics::PlaySound2D(GetWorld(), S, 0.8f);
	}
}

// ----------------------------------------------------------------------------------------------- star systems
namespace
{
	void PlanetPalette(UMaterialInstanceDynamic* M, const FString& Type)
	{
		auto V = [M](const TCHAR* N, float R, float G, float B) { M->SetVectorParameterValue(N, FLinearColor(R, G, B, 1.f)); };
		auto S = [M](const TCHAR* N, float X) { M->SetScalarParameterValue(N, X); };
		// defaults: an ocean world like New Ravenna
		V(TEXT("PlanetOceanA"), 0.006f, 0.03f, 0.09f); V(TEXT("PlanetOceanB"), 0.02f, 0.11f, 0.17f);
		V(TEXT("PlanetLandA"), 0.06f, 0.13f, 0.05f); V(TEXT("PlanetLandB"), 0.26f, 0.22f, 0.13f); V(TEXT("PlanetLandC"), 0.38f, 0.33f, 0.22f);
		V(TEXT("PlanetIceC"), 0.8f, 0.84f, 0.88f); V(TEXT("PlanetCloudC"), 0.92f, 0.93f, 0.95f); V(TEXT("PlanetAtmC"), 0.32f, 0.58f, 1.f);
		S(TEXT("PlanetSea"), 0.515f); S(TEXT("PlanetIceLat"), 0.8f); S(TEXT("PlanetCloudAmt"), 1.f); S(TEXT("PlanetGas"), 0.f);
		S(TEXT("PlanetCities"), 1.f); S(TEXT("PlanetLava"), 0.f);
		if (Type == TEXT("desert"))
		{
			S(TEXT("PlanetSea"), 0.25f); V(TEXT("PlanetOceanA"), 0.05f, 0.08f, 0.1f); V(TEXT("PlanetOceanB"), 0.1f, 0.14f, 0.14f);
			V(TEXT("PlanetLandA"), 0.42f, 0.27f, 0.14f); V(TEXT("PlanetLandB"), 0.6f, 0.43f, 0.24f); V(TEXT("PlanetLandC"), 0.74f, 0.6f, 0.4f);
			S(TEXT("PlanetIceLat"), 0.93f); S(TEXT("PlanetCloudAmt"), 0.25f); V(TEXT("PlanetAtmC"), 0.85f, 0.62f, 0.42f); S(TEXT("PlanetCities"), 0.4f);
		}
		else if (Type == TEXT("ice"))
		{
			S(TEXT("PlanetSea"), 0.6f); V(TEXT("PlanetOceanA"), 0.02f, 0.05f, 0.08f); V(TEXT("PlanetOceanB"), 0.1f, 0.2f, 0.26f);
			V(TEXT("PlanetLandA"), 0.55f, 0.6f, 0.66f); V(TEXT("PlanetLandB"), 0.7f, 0.75f, 0.8f); V(TEXT("PlanetLandC"), 0.62f, 0.66f, 0.7f);
			S(TEXT("PlanetIceLat"), 0.05f); V(TEXT("PlanetIceC"), 0.86f, 0.9f, 0.95f); S(TEXT("PlanetCloudAmt"), 0.55f);
			V(TEXT("PlanetAtmC"), 0.6f, 0.8f, 1.f); S(TEXT("PlanetCities"), 0.15f);
		}
		else if (Type == TEXT("lava"))
		{
			S(TEXT("PlanetSea"), 0.35f); V(TEXT("PlanetOceanA"), 0.2f, 0.04f, 0.01f); V(TEXT("PlanetOceanB"), 0.35f, 0.08f, 0.02f);
			V(TEXT("PlanetLandA"), 0.04f, 0.035f, 0.035f); V(TEXT("PlanetLandB"), 0.1f, 0.07f, 0.06f); V(TEXT("PlanetLandC"), 0.18f, 0.11f, 0.08f);
			S(TEXT("PlanetIceLat"), 2.f); S(TEXT("PlanetCloudAmt"), 0.35f); V(TEXT("PlanetCloudC"), 0.22f, 0.2f, 0.19f);
			V(TEXT("PlanetAtmC"), 0.95f, 0.42f, 0.2f); S(TEXT("PlanetCities"), 0.f); S(TEXT("PlanetLava"), 1.f);
		}
		else if (Type == TEXT("gas_giant"))
		{
			S(TEXT("PlanetGas"), 1.f); V(TEXT("PlanetLandA"), 0.86f, 0.72f, 0.52f); V(TEXT("PlanetLandB"), 0.42f, 0.25f, 0.14f);
			V(TEXT("PlanetLandC"), 0.9f, 0.86f, 0.78f); V(TEXT("PlanetAtmC"), 0.9f, 0.8f, 0.62f); S(TEXT("PlanetCities"), 0.f);
		}
		else if (Type == TEXT("barren"))
		{
			S(TEXT("PlanetSea"), -1.f); V(TEXT("PlanetLandA"), 0.22f, 0.21f, 0.2f); V(TEXT("PlanetLandB"), 0.34f, 0.32f, 0.3f);
			V(TEXT("PlanetLandC"), 0.46f, 0.44f, 0.41f); S(TEXT("PlanetIceLat"), 2.f); S(TEXT("PlanetCloudAmt"), 0.f);
			V(TEXT("PlanetAtmC"), 0.f, 0.f, 0.f); S(TEXT("PlanetCities"), 0.f);
		}
	}
}

void UAstraShipSubsystem::ApplySystem(const FAstraSystemLook& L)
{
	SystemName = L.Name;
	if (L.Name.Equals(TEXT("Aurelia"), ESearchCase::IgnoreCase) && bHomeCaptured)
	{
		// home: the sky exactly as it was (star, New Ravenna, the nebula), the sun where it belongs among the stars
		LocationName = TEXT("Aurelia System, home of the 7th Fleet: just through the Janus Gate Aurelia, New Ravenna in the distance");
		SunDir0 = HomeSunDir0;
		for (const auto& KV : HomeScalars) { SkyMID->SetScalarParameterValue(KV.Key, KV.Value); }
		for (const auto& KV : HomeVectors) { SkyMID->SetVectorParameterValue(KV.Key, KV.Value); }
		SetPlanetFill(TEXT("ocean"));
		if (Sun && Sun->GetLightComponent())
		{
			Sun->GetLightComponent()->SetIntensity(HomeLux);
			Sun->GetLightComponent()->SetTemperature(HomeKelvin);
		}
		UpdateAttitudeVisuals();
		return;
	}
	LocationName = FString::Printf(TEXT("%s System, just through the Janus Gate%s"), *L.Name,
	                               L.PlanetName.IsEmpty() ? TEXT("") : *FString::Printf(TEXT(", the %s world %s ahead"), *L.PlanetType.Replace(TEXT("_"), TEXT(" ")), *L.PlanetName));
	const FQuat Delta(FRotator(MarkDeg - Mark0, HeadingDeg - Heading0, 0.f));
	SunDir0 = Delta.RotateVector(L.SunWorld.GetSafeNormal());
	float Lux = 1200.f, Kelvin = 4300.f, Size = 0.0075f, PlanetGlow = 6.f;
	FLinearColor StarC(1.f, 0.6f, 0.3f);
	if (L.StarClass == TEXT("red_dwarf")) { Lux = 650.f; Kelvin = 3100.f; Size = 0.013f; StarC = FLinearColor(1.f, 0.32f, 0.16f); PlanetGlow = 2.2f; }
	else if (L.StarClass == TEXT("yellow")) { Lux = 1600.f; Kelvin = 5600.f; Size = 0.0068f; StarC = FLinearColor(1.f, 0.86f, 0.62f); PlanetGlow = 4.f; }
	else if (L.StarClass == TEXT("blue_white")) { Lux = 2200.f; Kelvin = 9000.f; Size = 0.0048f; StarC = FLinearColor(0.72f, 0.84f, 1.f); PlanetGlow = 3.5f; }
	// bright worlds (ice, gas, desert) reflect far more than an ocean world: keep them out of the white
	if (L.PlanetType == TEXT("gas_giant") || L.PlanetType == TEXT("ice") || L.PlanetType == TEXT("desert"))
	{
		PlanetGlow *= 0.5f;
	}
	if (SkyMID)
	{
		SkyMID->SetVectorParameterValue(TEXT("StarColor"), StarC);
		SkyMID->SetScalarParameterValue(TEXT("StarAngularRadius"), Size);
		SkyMID->SetScalarParameterValue(TEXT("NebulaHue"), L.NebulaHue);
		SkyMID->SetScalarParameterValue(TEXT("NebulaSaturation"), L.NebulaSat);
		SkyMID->SetScalarParameterValue(TEXT("PlanetAngularRadius"), L.PlanetSize);
		SkyMID->SetScalarParameterValue(TEXT("PlanetBrightness"), PlanetGlow);
		SkyMID->SetScalarParameterValue(TEXT("PlanetSeed"), L.Seed);
		PlanetPalette(SkyMID, L.PlanetType);
		SetPlanetFill(L.PlanetType);
		// the planet's direction lives in the sky frame: express the wanted world direction with the current sky basis
		FLinearColor AX, AY, AZ;
		SkyMID->GetVectorParameterValue(FHashedMaterialParameterInfo(TEXT("SkyAxisX")), AX);
		SkyMID->GetVectorParameterValue(FHashedMaterialParameterInfo(TEXT("SkyAxisY")), AY);
		SkyMID->GetVectorParameterValue(FHashedMaterialParameterInfo(TEXT("SkyAxisZ")), AZ);
		const FVector W = L.PlanetWorld.GetSafeNormal();
		const FVector P(FVector::DotProduct(W, FVector(AX.R, AX.G, AX.B)), FVector::DotProduct(W, FVector(AY.R, AY.G, AY.B)),
		                FVector::DotProduct(W, FVector(AZ.R, AZ.G, AZ.B)));
		SkyMID->SetVectorParameterValue(TEXT("PlanetDirection"), FLinearColor(P.X, P.Y, P.Z, 0.f));
	}
	if (Sun)
	{
		if (ULightComponent* LC = Sun->GetLightComponent())
		{
			LC->SetIntensity(Lux);
			LC->SetTemperature(Kelvin);
		}
	}
	UpdateAttitudeVisuals();
}
