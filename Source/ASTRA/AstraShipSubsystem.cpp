// ASTRA — ship simulation.

#include "AstraShipSubsystem.h"

#include "ASTRA.h"
#include "AstraBattleSubsystem.h"
#include "AstraBridgeFX.h"
#include "AstraHangar.h"
#include "AstraPatient.h"
#include "AstraQuarters.h"
#include "AstraWorldGen.h"
#include "AstraWorldSurface.h"
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

namespace
{
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

	float WrapDeg(float D) { return FMath::Fmod(FMath::Fmod(D, 360.f) + 360.f, 360.f); }
	float DeltaDeg(float From, float To) { return FMath::FindDeltaAngleDegrees(From, To); }

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
	CasualtyRng.Initialize((int32)(FDateTime::Now().GetTicks() & 0x7fffffff));
	FActorSpawnParameters FXP;
	FXP.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	BridgeFX = InWorld.SpawnActor<AAstraBridgeFX>(FVector::ZeroVector, FRotator::ZeroRotator, FXP);
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
	return O;
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

void UAstraShipSubsystem::RadiatorHit()
{
	if (!bRadiatorsOut || RadiatorHealth < 0.3f || FMath::FRand() > 0.3f)
	{
		return;
	}
	// a wing torn: an incident damage control can repair (each repair gives back a quarter of the radiators)
	FAstraDamage D;
	D.Id = NextDamageId++;
	D.Deck = 5;
	D.Kind = TEXT("radiator damage");
	for (const TCHAR Sec : {TEXT('E'), TEXT('F'), TEXT('G')})
	{
		if (!Damage.ContainsByPredicate([Sec](const FAstraDamage& X) { return X.Kind == TEXT("radiator damage") && X.Section == Sec; }))
		{
			D.Section = Sec;
			RadiatorHealth = FMath::Max(0.25f, RadiatorHealth - 0.25f);
			Damage.Add(D);
			if (Damage.Num() > 16)
			{
				Damage.RemoveAt(0);
			}
			Event(FString::Printf(TEXT("engineering: a radiator wing torn by the hit at %s — the radiators shed %.0f %% of their heat until "
			                           "damage control repairs them"), *D.Where(), 100.f * RadiatorHealth), true);
			return;
		}
	}
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
	const float Gen = 0.16f * (Sum / 600.f) + 0.2f * (ThrottlePct / 100.f) * PowerFactor(TEXT("engines"));
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
	// critical: conduits give way, people in the engine spaces get burned
	if (HeatPct >= 92.f)
	{
		if ((HeatHarmT -= DeltaTime) <= 0.f)
		{
			HeatHarmT = FMath::FRandRange(10.f, 16.f);
			static const TCHAR* Sys[] = {TEXT("shields"), TEXT("weapons"), TEXT("engines"), TEXT("sensors")};
			FAstraDamage D;
			D.Id = NextDamageId++;
			D.Deck = FMath::RandRange(7, 10);
			D.Section = TEXT("ABCDEFGH")[FMath::RandRange(0, 7)];
			D.Kind = TEXT("conduit damage");
			D.System = Sys[FMath::RandRange(0, 3)];
			const FString Burns = FMath::FRand() < 0.35f ? Roster.Casualties(D.Deck, 1, 0, CasualtyRng, TEXT("fire")) : FString();
			if (!Damage.ContainsByPredicate([&D](const FAstraDamage& X) { return X.Deck == D.Deck && X.Section == D.Section && X.Kind == D.Kind; }))
			{
				Damage.Add(D);
				if (Damage.Num() > 16)
				{
					Damage.RemoveAt(0);
				}
			}
			Event(FString::Printf(TEXT("engineering: a power conduit overheated and failed at %s (%s power -20%%)%s"), *D.Where(), *D.System,
			                      Burns.IsEmpty() ? TEXT("") : *(FString(TEXT(" — casualties: ")) + Burns)), true);
		}
	}
	else
	{
		HeatHarmT = 6.f;
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
	if (P && P->GetActorLocation().Z < -3000.f)
	{
		return TEXT("on the flight deck (Deck 9), away from the bridge: the XO has the conn; the Captain speaks by intercom");
	}
	return TEXT("on the bridge");
}

void UAstraShipSubsystem::Event(const FString& Text, bool bReport)
{
	UE_LOG(LogASTRA, Log, TEXT("[Event]%s %s"), bReport ? TEXT(" (report)") : TEXT(""), *Text);
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
		if (M != TEXT("tactical") && M != TEXT("sector"))
		{
			OutDetail = TEXT("the holo table shows either the tactical plot or the sector map");
			return false;
		}
		if (M == TEXT("sector") && Sector.Num() == 0)
		{
			OutDetail = TEXT("no sector data from the fleet yet");
			return false;
		}
		HoloMode = M;
		OutDetail = M == TEXT("sector") ? TEXT("holo table: the sector map (the March, who holds what, the gate links)")
		                                : TEXT("holo table: tactical plot");
		return true;
	}
	if (Name == TEXT("sector"))
	{
		// the war map from the mind: every system's look is charted (Aurelia keeps the level's sky), links and owners kept
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
		OutDetail = FString::Printf(TEXT("sector charted: %d systems"), Sector.Num());
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
		OutDetail = FString::Printf(TEXT("intercepting %s: bearing %03.0f mark %.0f, range %.1f km, throttle %.0f%%; at %.0f km the helm turns "
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
		FString Sec = Str(TEXT("section")).ToUpper().TrimStartAndEnd();
		Sec.RemoveFromStart(TEXT("SECTION "));
		const TCHAR SecC = Sec.Len() ? Sec[0] : TEXT('?');
		FAstraDamage* D = Damage.FindByPredicate([&](const FAstraDamage& X) { return X.Deck == Deck && X.Section == SecC; });
		if (D && D->Team >= 0)
		{
			OutDetail = FString::Printf(TEXT("team %d is already on the %s at %s (%s)"), D->Team + 1, *D->Kind, *D->Where(),
			                            D->Travel > 0.f ? *FString::Printf(TEXT("on scene in %.0f s"), D->Travel)
			                                            : *FString::Printf(TEXT("%.0f%% done"), 100.f * D->Progress));
			return true;
		}
		if (!D)
		{
			D = Damage.FindByPredicate([&](const FAstraDamage& X) { return X.Deck == Deck && X.Team < 0; });
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
		D->Travel = (6.f + FMath::Abs(D->Deck - 6) * 1.5f) * Speed;
		D->Work = (D->Kind == TEXT("fire") ? 30.f : (D->Kind == TEXT("hull breach") ? 40.f : 25.f)) * Speed;
		int32 Busy = 0;
		for (const FAstraDamage& X : Damage) { Busy += X.Team >= 0 ? 1 : 0; }
		OutDetail = FString::Printf(TEXT("team %d en route to the %s at %s: on scene in %.0f s, about %.0f s of work; %d team%s still free"),
		                            Team + 1, *D->Kind, *D->Where(), D->Travel, D->Work, NumDamageTeams - Busy, NumDamageTeams - Busy == 1 ? TEXT("") : TEXT("s"));
		return true;
	}
	if (Name == TEXT("hail"))
	{
		const FString Id = Str(TEXT("contact_id"));
		if (Id.Equals(TEXT("fleet"), ESearchCase::IgnoreCase))
		{
			OutDetail = TEXT("7th Fleet net open: Vice Admiral Adrian Rourke, 7th Fleet commander, is on the line (reply expected)");
			return true;
		}
		return Battle ? Battle->PlayerHail(Id, OutDetail) : false;
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
	if (Name == TEXT("active_scan"))
	{
		return Battle ? Battle->PlayerScan(Str(TEXT("contact_id")), OutDetail) : false;
	}
	OutDetail = FString::Printf(TEXT("unknown command %s"), *Name);
	return false;
}

TSharedRef<FJsonObject> UAstraShipSubsystem::Snapshot() const
{
	TSharedRef<FJsonObject> S = MakeShared<FJsonObject>();
	S->SetStringField(TEXT("ship"), TEXT("ASN Aquila"));
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
		S->SetStringField(TEXT("helm"), FString::Printf(TEXT("intercepting %s, range %.1f km, %s (standoff %.0f km); course follows the target"),
		                                                *InterceptId, InterceptRangeKm, bBroadside ? TEXT("broadside, holding the range") : TEXT("closing"),
		                                                InterceptStandoffKm));
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
		S->SetObjectField(TEXT("_mandate"), Battle->MandateViewJson());   // for the enemy minds only
		// where the Captain is: in a Falcon the XO has the conn and the Captain speaks by radio
		const FString Flying = Battle->PilotSummary();
		S->SetStringField(TEXT("captain"), !Flying.IsEmpty() ? Flying : CaptainAboard());
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
	for (const FAstraDamage& D : Damage)
	{
		Busy += D.Team >= 0 ? 1 : 0;
		FString Line = FString::Printf(TEXT("%s: %s"), *D.Where(), *D.Kind);
		if (!D.System.IsEmpty())
		{
			Line += FString::Printf(TEXT(" (%s power -20%%)"), *D.System);
		}
		Line += D.Team < 0 ? FString(TEXT(" — unattended")) :
		        (D.Travel > 0.f ? FString::Printf(TEXT(" — team %d on the way (%.0f s)"), D.Team + 1, D.Travel)
		                        : FString::Printf(TEXT(" — team %d working, %.0f%% done"), D.Team + 1, 100.f * D.Progress));
		Dmg.Add(MakeShared<FJsonValueString>(Line));
	}
	S->SetArrayField(TEXT("damage"), Dmg);
	S->SetStringField(TEXT("damage_control"), FString::Printf(TEXT("%d teams, %d free"), NumDamageTeams, NumDamageTeams - Busy));
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
	float Sum = 0.f;
	for (const auto& KV : PowerPct) { Sum += KV.Value; }
	S->SetStringField(TEXT("power_budget"), FString::Printf(TEXT("%.0f%% of %.0f%% allocated (six systems at 100%% = 600%%)"), Sum, PowerBudget));
	return S;
}

void UAstraShipSubsystem::Tick(float DeltaTime)
{
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
			bBroadside = bBroadside ? Rng < InterceptStandoffKm + 1.5 : Rng < InterceptStandoffKm;
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
		const float Rate = 1.5f * DeltaTime;
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
	SpeedMps = FMath::FInterpTo(SpeedMps, ThrottlePct * 4.8f * (0.6f + 0.4f * PowerFactor(TEXT("engines"))) * (HeatPct > 90.f ? 0.85f : 1.f),
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
		Sun->SetActorRotation((-Delta.UnrotateVector(SunDir0)).Rotation());
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
	for (int32 i = 0; i < ShipLights.Num(); ++i)
	{
		if (ULightComponent* LC = ShipLights[i] ? ShipLights[i]->GetLightComponent() : nullptr)
		{
			LC->SetIntensity(ShipLightBase[i] * LightLevel);
			LC->SetLightColor(FMath::Lerp(ShipLightColorBase[i], FLinearColor(1.f, 0.55f, 0.5f), AlertBlend * 0.35f));
		}
	}
}

float UAstraShipSubsystem::PowerFactor(const FString& System) const
{
	const float* P = PowerPct.Find(System);
	float F = (P ? *P : 100.f) / 100.f;
	for (const FAstraDamage& D : Damage)
	{
		F *= D.System == System ? 0.8f : 1.f;
	}
	return F;
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

void UAstraShipSubsystem::TickDamage(float DeltaTime)
{
	UAstraBattleSubsystem* Battle = GetWorld() ? GetWorld()->GetSubsystem<UAstraBattleSubsystem>() : nullptr;
	for (int32 i = Damage.Num() - 1; i >= 0; --i)
	{
		FAstraDamage& D = Damage[i];
		if (D.Team >= 0)
		{
			if (D.Travel > 0.f)
			{
				D.Travel -= DeltaTime;
				continue;
			}
			D.Progress += DeltaTime / D.Work;
			if (D.Progress >= 1.f)
			{
				const FString Done = D.Kind == TEXT("fire") ? TEXT("is out") : (D.Kind == TEXT("hull breach") ? TEXT("is sealed")
				                   : (D.Kind == TEXT("radiator damage") ? TEXT("is repaired, the panel sheds heat again") : TEXT("is repaired, power restored")));
				if (D.Kind == TEXT("radiator damage"))
				{
					RadiatorHealth = FMath::Min(1.f, RadiatorHealth + 0.25f);
				}
				const bool bSay = D.Kind != TEXT("conduit damage");
				const FString Text = FString::Printf(TEXT("damage control: the %s at %s %s (team %d free again)"), *D.Kind, *D.Where(), *Done, D.Team + 1);
				Damage.RemoveAt(i);
				Event(Text, bSay);
			}
		}
		else if (D.Kind == TEXT("fire") && (D.SpreadT -= DeltaTime) <= 0.f)
		{
			// an unattended fire eats the structure and may spread to the next section
			D.SpreadT = 25.f;
			if (Battle)
			{
				Battle->PlayerInternalDamage(20.f);
			}
			if (FMath::FRand() < 0.4f && D.Section < TEXT('H'))
			{
				FAstraDamage N;
				N.Id = NextDamageId++;
				N.Deck = D.Deck;
				N.Section = D.Section + 1;
				N.Kind = TEXT("fire");
				const FString Text = FString::Printf(TEXT("damage report: the unattended fire at %s has spread to section %c"), *D.Where(), N.Section);
				if (!Damage.ContainsByPredicate([&N](const FAstraDamage& X) { return X.Deck == N.Deck && X.Section == N.Section; }))
				{
					Damage.Add(N);
					Event(Text, true);
				}
			}
		}
	}
}

void UAstraShipSubsystem::OnHullHit(float HullDamage, float ShieldDamage, const FVector& FromDir)
{
	FlickerTime = 0.6f;
	FString Where;
	if (HullDamage > 8.f && BridgeFX)
	{
		// the shock runs through the frame: a fixture or a console on the bridge shorts out
		const float Strength = FMath::Clamp(HullDamage / 60.f, 0.2f, 1.f);
		if (FMath::FRand() < 0.35f + 0.5f * Strength)
		{
			BridgeFX->RandomBurst(Strength);
		}
		if (HullDamage > 35.f)
		{
			BridgeFX->RandomBurst(Strength * 0.7f);
		}
	}
	if (HullDamage > 5.f)
	{
		RadiatorHit();
	}
	if (HullDamage > 8.f)
	{
		// where did it land? a compartment (decks 1-12, sections A-H) and what it does there
		FAstraDamage D;
		D.Id = NextDamageId++;
		D.Deck = FMath::RandRange(2, 11);
		D.Section = TEXT("ABCDEFGH")[FMath::RandRange(0, 7)];
		const float Roll = FMath::FRand();
		D.Kind = Roll < 0.35f ? TEXT("hull breach") : (Roll < 0.65f ? TEXT("fire") : TEXT("conduit damage"));
		if (D.Kind == TEXT("conduit damage"))
		{
			static const TCHAR* Conduits[] = {TEXT("shields"), TEXT("weapons"), TEXT("engines"), TEXT("sensors")};
			D.System = Conduits[FMath::RandRange(0, 3)];
		}
		Where = FString::Printf(TEXT("%s: %s%s"), *D.Where(), *D.Kind, D.System.IsEmpty() ? TEXT("") : *FString::Printf(TEXT(" (%s power -20%%)"), *D.System));
		// people were in that compartment
		const float Roll2 = FMath::FRand();
		int32 W = 0, K = 0;
		if (D.Kind == TEXT("hull breach")) { W = Roll2 < 0.4f ? FMath::RandRange(1, 3) : 0; K = Roll2 < 0.1f ? 1 : 0; }
		else if (D.Kind == TEXT("fire")) { W = Roll2 < 0.35f ? FMath::RandRange(1, 2) : 0; }
		else { W = Roll2 < 0.1f ? 1 : 0; }
		const FString Names = (W || K) ? Roster.Casualties(D.Deck, W, K, CasualtyRng, D.Kind) : FString();
		if (!Names.IsEmpty())
		{
			Where += TEXT(" — casualties: ") + Names;
		}
		if (!Damage.ContainsByPredicate([&D](const FAstraDamage& X) { return X.Deck == D.Deck && X.Section == D.Section && X.Kind == D.Kind; }))
		{
			Damage.Add(D);
			if (Damage.Num() > 16)
			{
				Damage.RemoveAt(0);
			}
		}
	}
	const double Now = GetWorld()->GetTimeSeconds();
	if (Now - LastHitReport > 6.0)
	{
		LastHitReport = Now;
		const UAstraBattleSubsystem* Battle = GetWorld()->GetSubsystem<UAstraBattleSubsystem>();
		const int32 Sh = Battle ? FMath::RoundToInt(100.f * Battle->PlayerShieldFraction()) : 0;
		const int32 Hu = Battle ? FMath::RoundToInt(100.f * Battle->PlayerHullFraction()) : 100;
		Event(!Where.IsEmpty()
			? FString::Printf(TEXT("damage report: we've been hit — %s; shields %d%%, hull %d%%"), *Where, Sh, Hu)
			: FString::Printf(TEXT("shields took a hit, holding at %d%%"), Sh), true);
	}
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
