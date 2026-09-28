// ASTRA — ship simulation.

#include "AstraShipSubsystem.h"

#include "ASTRA.h"
#include "AstraBattleSubsystem.h"
#include "Components/LightComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/DirectionalLight.h"
#include "Engine/Light.h"
#include "EngineUtils.h"
#include "Kismet/GameplayStatics.h"
#include "Kismet/KismetMaterialLibrary.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialParameterCollection.h"
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
}

bool UAstraShipSubsystem::ShouldCreateSubsystem(UObject* Outer) const
{
	const UWorld* World = Cast<UWorld>(Outer);
	return World && (World->WorldType == EWorldType::Game || World->WorldType == EWorldType::PIE);
}

void UAstraShipSubsystem::OnWorldBeginPlay(UWorld& InWorld)
{
	Super::OnWorldBeginPlay(InWorld);
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
}

void UAstraShipSubsystem::Event(const FString& Text, bool bReport)
{
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
		                                 "broadside and holds the range (course follows the target)"),
		                            *Id, Brg, Mk, Rng, ThrottlePct, InterceptStandoffKm);
		return true;
	}
	if (Name == TEXT("set_course"))
	{
		InterceptId.Empty();
		TargetHeadingDeg = WrapDeg((float)Num(TEXT("heading_deg"), HeadingDeg));
		TargetMarkDeg = FMath::Clamp((float)Num(TEXT("mark_deg"), MarkDeg), -90.f, 90.f);
		bTurning = true;
		OutDetail = FString::Printf(TEXT("coming to %03.0f mark %.0f (turn rate 1.5 deg/s)"), TargetHeadingDeg, TargetMarkDeg);
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
	if (Name == TEXT("launch_squadron") || Name == TEXT("recall_squadron"))
	{
		const FString Sq = Str(TEXT("squadron"));
		if (!Squadrons.Contains(Sq))
		{
			OutDetail = FString::Printf(TEXT("no squadron %s"), *Sq);
			return false;
		}
		if (Name == TEXT("recall_squadron"))
		{
			Squadrons[Sq] = TEXT("recovering to the flight deck");
			OutDetail = FString::Printf(TEXT("%s recalled"), *Sq);
			return true;
		}
		if (!Squadrons[Sq].Contains(TEXT("ready")))
		{
			OutDetail = FString::Printf(TEXT("%s not ready: %s"), *Sq, *Squadrons[Sq]);
			return false;
		}
		const FString Mission = Str(TEXT("mission"));
		Squadrons[Sq] = FString::Printf(TEXT("launched: %s %s"), *Mission, *Str(TEXT("contact_id")));
		OutDetail = FString::Printf(TEXT("%s launching for %s"), *Sq, *Mission);
		Event(OutDetail);
		return true;
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
		OutDetail = FString::Printf(TEXT("team %d en route to the %s at %s: on scene in %.0f s, about %.0f s of work; %d teams still free"),
		                            Team + 1, *D->Kind, *D->Where(), D->Travel, D->Work, NumDamageTeams - Busy);
		return true;
	}
	if (Name == TEXT("hail"))
	{
		const FString Id = Str(TEXT("contact_id"));
		if (Id.Equals(TEXT("fleet"), ESearchCase::IgnoreCase))
		{
			OutDetail = TEXT("7th Fleet net: message sent to the flagship ASN Praetorian");
			return true;
		}
		return Battle ? Battle->PlayerHail(Id, OutDetail) : false;
	}
	if (Name == TEXT("cease_fire"))
	{
		return Battle ? Battle->PlayerCeaseFire(OutDetail) : false;
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
	S->SetStringField(TEXT("location"), TEXT("Aurelia System, en route to New Ravenna high orbit"));
	S->SetStringField(TEXT("alert"), AlertName(Alert));
	S->SetNumberField(TEXT("heading_deg"), FMath::RoundToInt(HeadingDeg));
	S->SetNumberField(TEXT("mark_deg"), FMath::RoundToInt(MarkDeg));
	if (!InterceptId.IsEmpty())
	{
		S->SetStringField(TEXT("helm"), FString::Printf(TEXT("intercepting %s, range %.1f km, %s (standoff %.0f km); course follows the target"),
		                                                *InterceptId, InterceptRangeKm, bBroadside ? TEXT("broadside, holding the range") : TEXT("closing"),
		                                                InterceptStandoffKm));
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
	TSharedRef<FJsonObject> Q = MakeShared<FJsonObject>();
	for (const auto& KV : Squadrons) { Q->SetStringField(KV.Key, KV.Value); }
	S->SetObjectField(TEXT("squadrons"), Q);
	const UAstraBattleSubsystem* Battle = GetWorld() ? GetWorld()->GetSubsystem<UAstraBattleSubsystem>() : nullptr;
	if (Battle)
	{
		S->SetArrayField(TEXT("contacts"), Battle->ContactsJson());
		S->SetObjectField(TEXT("_mandate"), Battle->MandateViewJson());   // for the enemy minds only
		S->SetNumberField(TEXT("hull_pct"), FMath::RoundToInt(100.f * Battle->PlayerHullFraction()));
		Sh->SetNumberField(TEXT("strength_pct"), FMath::RoundToInt(100.f * Battle->PlayerShieldFraction()));
	}
	S->SetStringField(TEXT("bearing_convention"), TEXT("bearings are true bearings in the Aurelia system plane, like headings: steer to a contact's bearing to point at it"));
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
	float Sum = 0.f;
	for (const auto& KV : PowerPct) { Sum += KV.Value; }
	S->SetStringField(TEXT("power_budget"), FString::Printf(TEXT("%.0f%% of %.0f%% allocated (six systems at 100%% = 600%%)"), Sum, PowerBudget));
	return S;
}

void UAstraShipSubsystem::Tick(float DeltaTime)
{
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
			if (InterceptId.IsEmpty())
			{
				Event(FString::Printf(TEXT("helm: turn complete, steady on course %03.0f mark %.0f"), HeadingDeg, MarkDeg), true);
			}
		}
		UpdateAttitudeVisuals();
	}
	// drive: speed follows the throttle (max 480 m/s at nominal engine power: a carrier cruiser, a little faster than
	// Mandate destroyers at cruise; engine power scales it)
	SpeedMps = FMath::FInterpTo(SpeedMps, ThrottlePct * 4.8f * (0.6f + 0.4f * PowerFactor(TEXT("engines"))), DeltaTime, 0.2f);
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
	}
	if (Sun)
	{
		Sun->SetActorRotation((-Delta.UnrotateVector(SunDir0)).Rotation());
	}
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
				const FString Done = D.Kind == TEXT("fire") ? TEXT("is out") : (D.Kind == TEXT("hull breach") ? TEXT("is sealed") : TEXT("is repaired, power restored"));
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
			static const TCHAR* Systems[] = {TEXT("shields"), TEXT("weapons"), TEXT("engines"), TEXT("sensors")};
			D.System = Systems[FMath::RandRange(0, 3)];
		}
		Where = FString::Printf(TEXT("%s: %s%s"), *D.Where(), *D.Kind, D.System.IsEmpty() ? TEXT("") : *FString::Printf(TEXT(" (%s power -20%%)"), *D.System));
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
