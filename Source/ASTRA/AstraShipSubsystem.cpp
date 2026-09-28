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

	if (Name == TEXT("set_course"))
	{
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
		PowerPct[Sys] = FMath::Clamp((float)Num(TEXT("percent"), 100.0), 0.f, 150.f);
		OutDetail = FString::Printf(TEXT("%s at %.0f%% of nominal"), *Sys, PowerPct[Sys]);
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
		OutDetail = FString::Printf(TEXT("damage control team en route to deck %d section %s"), (int32)Num(TEXT("deck"), 1), *Str(TEXT("section")));
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
	if (bTurning)
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
	for (const FString& D : DamageLog) { Dmg.Add(MakeShared<FJsonValueString>(D)); }
	S->SetArrayField(TEXT("damage"), Dmg);
	return S;
}

void UAstraShipSubsystem::Tick(float DeltaTime)
{
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
			Event(FString::Printf(TEXT("helm: turn complete, steady on course %03.0f mark %.0f"), HeadingDeg, MarkDeg), true);
		}
		UpdateAttitudeVisuals();
	}
	// drive: speed follows the throttle (max 700 m/s in this system, compressed game scale)
	SpeedMps = FMath::FInterpTo(SpeedMps, ThrottlePct * 7.f, DeltaTime, 0.2f);
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

void UAstraShipSubsystem::OnHullHit(float HullDamage, float ShieldDamage, const FVector& FromDir)
{
	FlickerTime = 0.6f;
	if (HullDamage > 8.f)
	{
		// where did it land? pick a compartment on the struck side (decks 1-12, sections A-H)
		const int32 Deck = FMath::RandRange(2, 11);
		const TCHAR Section = TEXT("ABCDEFGH")[FMath::RandRange(0, 7)];
		const float Roll = FMath::FRand();
		const FString What = Roll < 0.35f ? TEXT("hull breach, compartment venting") : (Roll < 0.65f ? TEXT("fire") : TEXT("conduit damage, power fluctuations"));
		DamageLog.Add(FString::Printf(TEXT("deck %d section %c: %s"), Deck, Section, *What));
		if (DamageLog.Num() > 8) { DamageLog.RemoveAt(0); }
	}
	const double Now = GetWorld()->GetTimeSeconds();
	if (Now - LastHitReport > 6.0)
	{
		LastHitReport = Now;
		const UAstraBattleSubsystem* Battle = GetWorld()->GetSubsystem<UAstraBattleSubsystem>();
		const int32 Sh = Battle ? FMath::RoundToInt(100.f * Battle->PlayerShieldFraction()) : 0;
		const int32 Hu = Battle ? FMath::RoundToInt(100.f * Battle->PlayerHullFraction()) : 100;
		Event(HullDamage > 8.f
			? FString::Printf(TEXT("damage report: we've been hit — %s; shields %d%%, hull %d%%"), *DamageLog.Last(), Sh, Hu)
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
