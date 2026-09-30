#include "AstraStations.h"
#include "AstraScreensSubsystem.h"
#include "ASTRA.h"
#include "AstraBattleSubsystem.h"
#include "AstraHarness.h"
#include "AstraShipSubsystem.h"
#include "Dom/JsonObject.h"
#include "Engine/World.h"

namespace
{
	constexpr float TickStep = 0.1f;                       // the executors run at 10 Hz
	using FContact = UAstraBattleSubsystem::FContactView;

	FString Str(const TSharedPtr<FJsonObject>& O, const TCHAR* Key, const FString& Default = FString())
	{
		FString V;
		return O.IsValid() && O->TryGetStringField(Key, V) ? V : Default;
	}

	double Num(const TSharedPtr<FJsonObject>& O, const TCHAR* Key, double Default)
	{
		double V = Default;
		return O.IsValid() && O->TryGetNumberField(Key, V) ? V : Default;
	}

	TSharedPtr<FJsonObject> Obj(std::initializer_list<TPair<FString, FString>> Pairs)
	{
		TSharedPtr<FJsonObject> O = MakeShared<FJsonObject>();
		for (const TPair<FString, FString>& P : Pairs)
		{
			O->SetStringField(P.Key, P.Value);
		}
		return O;
	}

	FVector Dir(double HeadingDeg, double MarkDeg)
	{
		return FRotator(MarkDeg, HeadingDeg, 0.0).Vector();
	}

	double AngleDeg(double H1, double M1, double H2, double M2)
	{
		return FMath::RadiansToDegrees(FMath::Acos(FMath::Clamp(FVector::DotProduct(Dir(H1, M1), Dir(H2, M2)), -1.0, 1.0)));
	}

	double WrapDeg(double D)
	{
		D = FMath::Fmod(D, 360.0);
		return D < 0.0 ? D + 360.0 : D;
	}

	// which aspect each mode name belongs to, per station (ambiguous names need an explicit aspect)
	const TMap<FString, TMap<FString, FString>>& ModeTable()
	{
		static const TMap<FString, TMap<FString, FString>> T = []
		{
			TMap<FString, TMap<FString, FString>> M;
			auto Add = [&M](const TCHAR* Station, const TCHAR* Aspect, std::initializer_list<const TCHAR*> Modes)
			{
				for (const TCHAR* Mode : Modes)
				{
					M.FindOrAdd(Station).Add(Mode, Aspect);
				}
			};
			Add(TEXT("helm"), TEXT("course"), {TEXT("hold"), TEXT("course"), TEXT("intercept"), TEXT("keep_on_bow"), TEXT("follow"),
			                                   TEXT("orbit"), TEXT("broadside"), TEXT("evade"), TEXT("retreat"), TEXT("formation"), TEXT("transit")});
			Add(TEXT("tactical"), TEXT("engagement"), {TEXT("hold_fire"), TEXT("return_fire"), TEXT("weapons_free"), TEXT("engage")});
			Add(TEXT("tactical"), TEXT("shields"), {TEXT("balanced"), TEXT("face_threat"), TEXT("sector"), TEXT("forward"), TEXT("aft"),
			                                        TEXT("port"), TEXT("starboard"), TEXT("dorsal"), TEXT("ventral"), TEXT("shields_off")});
			Add(TEXT("tactical"), TEXT("point_defense"), {TEXT("protect"), TEXT("pd_auto"), TEXT("pd_off")});
			Add(TEXT("tactical"), TEXT("missiles"), {TEXT("conserve"), TEXT("normal"), TEXT("saturate")});
			Add(TEXT("sensors"), TEXT("emcon"), {TEXT("silent"), TEXT("restricted"), TEXT("limited"), TEXT("full")});
			Add(TEXT("sensors"), TEXT("scan"), {TEXT("passive"), TEXT("sweep"), TEXT("focus")});
			Add(TEXT("ops"), TEXT("viewscreen"), {TEXT("auto"), TEXT("forward"), TEXT("target"), TEXT("tactical"), TEXT("fleet"), TEXT("comms"),
			                                      TEXT("damage"), TEXT("sector"), TEXT("off")});
			Add(TEXT("ops"), TEXT("holo"), {TEXT("ship")});
			Add(TEXT("ops"), TEXT("datapad"), {TEXT("push")});
			Add(TEXT("ops"), TEXT("damage_control"), {TEXT("priority")});
			Add(TEXT("engineering"), TEXT("power"), {TEXT("balanced"), TEXT("combat"), TEXT("evasive"), TEXT("silent"), TEXT("shields"),
			                                         TEXT("weapons"), TEXT("engines"), TEXT("custom")});
			Add(TEXT("engineering"), TEXT("heat"), {TEXT("radiators_extended"), TEXT("radiators_retracted"), TEXT("extended"), TEXT("retracted")});
			Add(TEXT("engineering"), TEXT("reactor"), {TEXT("normal"), TEXT("battle_short")});
			Add(TEXT("comms"), TEXT("channel"), {TEXT("open"), TEXT("close"), TEXT("mute"), TEXT("unmute")});
			Add(TEXT("comms"), TEXT("listen"), {TEXT("all"), TEXT("enemy")});
			Add(TEXT("xo"), TEXT("delegation"), {TEXT("delegation"), TEXT("manual"), TEXT("advise")});
			return M;
		}();
		return T;
	}

	// every aspect of every station (for "mode names an aspect" requests: {station: tactical, mode: shields, params: {mode: …}})
	const TMap<FString, TArray<FString>>& AspectTable()
	{
		static const TMap<FString, TArray<FString>> T = {
			{TEXT("helm"), {TEXT("course")}},
			{TEXT("tactical"), {TEXT("engagement"), TEXT("shields"), TEXT("point_defense"), TEXT("missiles")}},
			{TEXT("sensors"), {TEXT("emcon"), TEXT("scan")}},
			{TEXT("ops"), {TEXT("viewscreen"), TEXT("holo"), TEXT("datapad"), TEXT("damage_control")}},
			{TEXT("engineering"), {TEXT("power"), TEXT("heat"), TEXT("reactor")}},
			{TEXT("comms"), {TEXT("channel"), TEXT("listen")}},
			{TEXT("flight"), {TEXT("alpha"), TEXT("bravo"), TEXT("drones")}},
			{TEXT("xo"), {TEXT("delegation")}},
		};
		return T;
	}

	// reactor allocations of the engineering power profiles (% of nominal; the reactor's budget is the ship's)
	bool Profile(const FString& Name, TMap<FString, float>& Out)
	{
		static const TMap<FString, TArray<float>> P = {
			//                        shields weapons engines sensors life flight
			{TEXT("balanced"), {100.f, 100.f, 100.f, 100.f, 100.f, 100.f}},
			{TEXT("combat"),   {150.f, 150.f, 100.f, 110.f,  80.f, 100.f}},
			{TEXT("evasive"),  {130.f,  90.f, 150.f, 100.f,  80.f,  90.f}},
			{TEXT("silent"),   { 80.f,  60.f,  40.f,  60.f,  80.f,  60.f}},
			{TEXT("shields"),  {150.f, 110.f, 100.f, 100.f,  80.f,  90.f}},
			{TEXT("weapons"),  {120.f, 150.f, 100.f, 100.f,  80.f,  90.f}},
			{TEXT("engines"),  {110.f, 100.f, 150.f, 100.f,  80.f,  80.f}},
		};
		const TArray<float>* V = P.Find(Name);
		if (!V)
		{
			return false;
		}
		static const TCHAR* Sys[] = {TEXT("shields"), TEXT("weapons"), TEXT("engines"), TEXT("sensors"), TEXT("life_support"), TEXT("flight_deck")};
		for (int32 i = 0; i < 6; ++i)
		{
			Out.Add(Sys[i], (*V)[i]);
		}
		return true;
	}

	const FContact* FindContact(const TArray<FContact>& Cs, const FString& Id)
	{
		return Cs.FindByPredicate([&Id](const FContact& C) { return C.ContactId.Equals(Id, ESearchCase::IgnoreCase); });
	}
}

// ------------------------------------------------------------------------------------------------ the consoles
const TArray<FString>& UAstraStationsSubsystem::AspectsOf(const FString& Station)
{
	static const TArray<FString> None;
	const TArray<FString>* A = AspectTable().Find(Station);
	return A ? *A : None;
}

const TArray<FString>& UAstraStationsSubsystem::ModeChoices(const FString& Station, const FString& Aspect)
{
	static const TMap<FString, TArray<FString>> T = {
		{TEXT("helm.course"), {TEXT("hold"), TEXT("course"), TEXT("intercept"), TEXT("keep_on_bow"), TEXT("follow"), TEXT("orbit"), TEXT("broadside"),
		                       TEXT("evade"), TEXT("retreat"), TEXT("formation"), TEXT("transit")}},
		{TEXT("tactical.engagement"), {TEXT("hold_fire"), TEXT("return_fire"), TEXT("weapons_free"), TEXT("engage")}},
		{TEXT("tactical.shields"), {TEXT("balanced"), TEXT("face_threat"), TEXT("forward"), TEXT("aft"), TEXT("port"), TEXT("starboard"), TEXT("shields_off")}},
		{TEXT("tactical.point_defense"), {TEXT("protect"), TEXT("pd_auto"), TEXT("pd_off")}},
		{TEXT("tactical.missiles"), {TEXT("conserve"), TEXT("normal"), TEXT("saturate")}},
		{TEXT("sensors.emcon"), {TEXT("silent"), TEXT("restricted"), TEXT("limited"), TEXT("full")}},
		{TEXT("sensors.scan"), {TEXT("passive"), TEXT("sweep"), TEXT("focus")}},
		{TEXT("ops.viewscreen"), {TEXT("auto"), TEXT("forward"), TEXT("target"), TEXT("tactical"), TEXT("fleet"), TEXT("sector"), TEXT("comms"),
		                          TEXT("damage"), TEXT("off")}},
		{TEXT("ops.holo"), {TEXT("tactical"), TEXT("sector"), TEXT("ship")}},
		{TEXT("ops.datapad"), {TEXT("push")}},
		{TEXT("ops.damage_control"), {TEXT("auto"), TEXT("priority")}},
		{TEXT("engineering.power"), {TEXT("balanced"), TEXT("combat"), TEXT("evasive"), TEXT("silent"), TEXT("shields"), TEXT("weapons"), TEXT("engines"),
		                             TEXT("custom")}},
		{TEXT("engineering.heat"), {TEXT("auto"), TEXT("extended"), TEXT("retracted")}},
		{TEXT("engineering.reactor"), {TEXT("normal"), TEXT("battle_short")}},
		{TEXT("comms.channel"), {TEXT("open"), TEXT("close"), TEXT("mute")}},
		{TEXT("comms.listen"), {TEXT("all"), TEXT("enemy"), TEXT("fleet")}},
		{TEXT("flight.alpha"), {TEXT("hold"), TEXT("cap"), TEXT("escort"), TEXT("strike"), TEXT("ew"), TEXT("recall")}},
		{TEXT("flight.bravo"), {TEXT("hold"), TEXT("cap"), TEXT("escort"), TEXT("strike"), TEXT("ew"), TEXT("recall")}},
		{TEXT("flight.drones"), {TEXT("hold"), TEXT("cap"), TEXT("escort"), TEXT("strike"), TEXT("ew"), TEXT("recall")}},
		{TEXT("xo.delegation"), {TEXT("manual"), TEXT("advise"), TEXT("auto")}},
	};
	static const TArray<FString> None;
	const TArray<FString>* M = T.Find(Station + TEXT(".") + Aspect);
	return M ? *M : None;
}

// ------------------------------------------------------------------------------------------------ lifecycle
bool UAstraStationsSubsystem::ShouldCreateSubsystem(UObject* Outer) const
{
	const UWorld* World = Cast<UWorld>(Outer);
	return World && (World->WorldType == EWorldType::Game || World->WorldType == EWorldType::PIE);
}

void UAstraStationsSubsystem::OnWorldBeginPlay(UWorld& InWorld)
{
	Super::OnWorldBeginPlay(InWorld);
	Defaults();
}

void UAstraStationsSubsystem::Defaults()
{
	Stations.Reset();
	auto Station = [this](const TCHAR* Id, const TCHAR* Officer) -> FAstraStation&
	{
		FAstraStation& S = Stations.Add(Id);
		S.Id = Id;
		S.Officer = Officer;
		return S;
	};
	DefaultModes.Reset();
	auto Set = [this](FAstraStation& S, const TCHAR* Aspect, const TCHAR* Mode, TSharedPtr<FJsonObject> Params = nullptr)
	{
		FAstraStationAspect& A = S.Aspects.Add(Aspect);
		A.Mode = Mode;
		A.Params = Params.IsValid() ? Params : MakeShared<FJsonObject>();
		DefaultModes.Add(S.Id + TEXT(".") + Aspect, Mode);
	};
	FAstraStation& Helm = Station(TEXT("helm"), TEXT("helm"));
	TSharedPtr<FJsonObject> Face = MakeShared<FJsonObject>();
	Face->SetBoolField(TEXT("face_action"), true);   // in a fight, the bow on the action (the Captain sees the battle)
	Set(Helm, TEXT("course"), TEXT("hold"), Face);
	FAstraStation& Tac = Station(TEXT("tactical"), TEXT("tactical"));
	Set(Tac, TEXT("engagement"), TEXT("return_fire"));
	Set(Tac, TEXT("shields"), TEXT("face_threat"));
	Set(Tac, TEXT("point_defense"), TEXT("pd_auto"));
	Set(Tac, TEXT("missiles"), TEXT("normal"));
	FAstraStation& Sen = Station(TEXT("sensors"), TEXT("sensors"));
	const UAstraShipSubsystem* Sh = Ship();
	Set(Sen, TEXT("emcon"), Sh ? *Sh->GetEmcon().ToLower() : TEXT("limited"));
	Set(Sen, TEXT("scan"), TEXT("passive"));
	FAstraStation& Ops = Station(TEXT("ops"), TEXT("ops"));
	Set(Ops, TEXT("viewscreen"), TEXT("auto"));
	Set(Ops, TEXT("holo"), TEXT("tactical"));
	Set(Ops, TEXT("damage_control"), TEXT("auto"));
	Set(Ops, TEXT("datapad"), TEXT("push"));             // the last page sent to the Captain (none yet)
	FAstraStation& Eng = Station(TEXT("engineering"), TEXT("engineering"));
	Set(Eng, TEXT("power"), TEXT("balanced"));
	Set(Eng, TEXT("heat"), TEXT("auto"));
	Set(Eng, TEXT("reactor"), TEXT("normal"));
	FAstraStation& Com = Station(TEXT("comms"), TEXT("comms"));
	Set(Com, TEXT("channel"), TEXT("close"));
	Set(Com, TEXT("listen"), TEXT("fleet"));
	FAstraStation& Fl = Station(TEXT("flight"), TEXT("flight"));
	Set(Fl, TEXT("alpha"), TEXT("hold"));
	Set(Fl, TEXT("bravo"), TEXT("hold"));
	Set(Fl, TEXT("drones"), TEXT("hold"));
	Station(TEXT("xo"), TEXT("xo"));
}

UAstraShipSubsystem* UAstraStationsSubsystem::Ship() const
{
	return GetWorld() ? GetWorld()->GetSubsystem<UAstraShipSubsystem>() : nullptr;
}

UAstraBattleSubsystem* UAstraStationsSubsystem::Battle() const
{
	return GetWorld() ? GetWorld()->GetSubsystem<UAstraBattleSubsystem>() : nullptr;
}

// ------------------------------------------------------------------------------------------------ the `station` command
FString UAstraStationsSubsystem::AspectFor(const FString& Station, const FString& Mode)
{
	if (Station == TEXT("flight"))
	{
		return FString();                 // flight names its squadron
	}
	const TMap<FString, FString>* M = ModeTable().Find(Station);
	const FString* A = M ? M->Find(Mode) : nullptr;
	return A ? *A : FString();
}

FAstraStationAspect* UAstraStationsSubsystem::Aspect(const FString& Station, const FString& AspectName)
{
	FAstraStation* S = Stations.Find(Station);
	return S ? S->Aspects.Find(AspectName) : nullptr;
}

FString UAstraStationsSubsystem::ModeOf(const FString& Station, const FString& AspectName) const
{
	const FAstraStation* S = Stations.Find(Station);
	const FAstraStationAspect* A = S ? S->Aspects.Find(AspectName) : nullptr;
	return A ? A->Mode : FString();
}

TSharedPtr<FJsonObject> UAstraStationsSubsystem::ParamsOf(const FString& Station, const FString& AspectName) const
{
	const FAstraStation* S = Stations.Find(Station);
	const FAstraStationAspect* A = S ? S->Aspects.Find(AspectName) : nullptr;
	return A ? A->Params : nullptr;
}

bool UAstraStationsSubsystem::SetMode(const TSharedPtr<FJsonObject>& Args, const FString& By, FString& OutDetail)
{
	if (!Args.IsValid())
	{
		OutDetail = TEXT("station needs {station, mode, params}");
		return false;
	}
	if (Stations.Num() == 0)
	{
		Defaults();
	}
	const FString StationId = Str(Args, TEXT("station")).ToLower();
	FAstraStation* S = Stations.Find(StationId);
	if (!S)
	{
		OutDetail = FString::Printf(TEXT("no station '%s' (helm, tactical, sensors, ops, engineering, comms, flight, xo)"), *StationId);
		return false;
	}
	FString Mode = Str(Args, TEXT("mode")).ToLower();
	TSharedPtr<FJsonObject> Params = MakeShared<FJsonObject>();
	const TSharedPtr<FJsonObject>* P = nullptr;
	if (Args->TryGetObjectField(TEXT("params"), P) && P && P->IsValid())
	{
		Params = *P;
	}
	FString AspectName = Str(Args, TEXT("aspect")).ToLower();
	// {mode: "shields", params: {mode: "face_threat"}}: the mode names an aspect
	if (AspectName.IsEmpty() && AspectTable()[StationId].Contains(Mode))
	{
		AspectName = Mode;
		Mode = Str(Params, TEXT("mode"), Str(Params, TEXT("value"))).ToLower();
	}
	if (StationId == TEXT("flight"))
	{
		// a squadron's mission: {squadron, mission|mode, target}
		if (AspectName.IsEmpty())
		{
			AspectName = Str(Params, TEXT("squadron"), Str(Args, TEXT("squadron"))).ToLower();
		}
		if (!S->Aspects.Contains(AspectName))
		{
			OutDetail = TEXT("flight: say which squadron (alpha, bravo, drones)");
			return false;
		}
		if (Mode.IsEmpty())
		{
			Mode = Str(Params, TEXT("mission")).ToLower();
		}
	}
	if (StationId == TEXT("xo") && (Mode == TEXT("delegation") || AspectName == TEXT("delegation")))
	{
		const FString Target = Str(Params, TEXT("station")).ToLower();
		const FString Level = Str(Params, TEXT("delegation"), Str(Params, TEXT("level"))).ToLower();
		FAstraStation* T = Stations.Find(Target);
		if (!T || (Level != TEXT("manual") && Level != TEXT("advise") && Level != TEXT("auto")))
		{
			OutDetail = TEXT("delegation needs {station, delegation: manual|advise|auto}");
			return false;
		}
		T->Delegation = Level;
		OutDetail = FString::Printf(TEXT("%s now on %s"), *Target, *Level);
		Act(TEXT("xo"), OutDetail, false);
		return true;
	}
	// a station's own delegation, when given with the mode
	const FString Deleg = Str(Args, TEXT("delegation")).ToLower();
	if (Deleg == TEXT("manual") || Deleg == TEXT("advise") || Deleg == TEXT("auto"))
	{
		S->Delegation = Deleg;
	}
	if (Mode.IsEmpty())
	{
		OutDetail = FString::Printf(TEXT("%s: which mode?"), *StationId);
		return !Deleg.IsEmpty();
	}
	if (AspectName.IsEmpty())
	{
		AspectName = AspectFor(StationId, Mode);
	}
	// modes shared by several aspects ("auto", "off", "tactical"…): the station's main aspect unless one is named
	if (AspectName.IsEmpty())
	{
		if (Mode == TEXT("auto") && StationId == TEXT("engineering")) AspectName = TEXT("heat");
		else if ((Mode == TEXT("auto") || Mode == TEXT("off")) && StationId == TEXT("tactical")) { AspectName = TEXT("point_defense"); Mode = TEXT("pd_") + Mode; }
		else if (StationId == TEXT("ops")) AspectName = TEXT("viewscreen");
	}
	FAstraStationAspect* A = S->Aspects.Find(AspectName);
	if (!A)
	{
		OutDetail = FString::Printf(TEXT("%s has no mode '%s'%s"), *StationId, *Mode, AspectName.IsEmpty() ? TEXT("") : *FString::Printf(TEXT(" for %s"), *AspectName));
		return false;
	}
	FAstraStationAspect Old = *A;
	A->Mode = Mode;
	A->Params = Params;
	A->Until = Str(Args, TEXT("until"), TEXT("order")).ToLower();
	A->SetBy = By.IsEmpty() ? TEXT("officer") : By;
	A->Since = Now;
	A->Due = Now;
	A->Step = 0;
	if (!Enter(StationId, AspectName, *A, OutDetail))
	{
		*A = Old;                                  // refused (a bad target, the budget…): nothing changes
		return false;
	}
	const FString Note = Str(Args, TEXT("note"));
	Act(StationId, FString::Printf(TEXT("%s %s%s%s"), *AspectName, *Mode, OutDetail.IsEmpty() ? TEXT("") : *FString::Printf(TEXT(": %s"), *OutDetail),
	                               Note.IsEmpty() ? TEXT("") : *FString::Printf(TEXT(" (%s)"), *Note)), false);
	UpdateStatus();
	if (OutDetail.IsEmpty())
	{
		OutDetail = FString::Printf(TEXT("%s %s set"), *AspectName, *Mode);
	}
	return true;
}

bool UAstraStationsSubsystem::Command(const FString& Name, const TSharedPtr<FJsonObject>& Args, FString& Detail)
{
	UAstraShipSubsystem* Sh = Ship();
	return Sh && Sh->ApplyCommand(Name, Args.IsValid() ? Args : MakeShared<FJsonObject>(), Detail);
}

bool UAstraStationsSubsystem::Enter(const FString& Station, const FString& AspectName, FAstraStationAspect& A, FString& Detail)
{
	UAstraShipSubsystem* Sh = Ship();
	UAstraBattleSubsystem* B = Battle();
	if (!Sh || !B)
	{
		Detail = TEXT("the bridge is not ready");
		return false;
	}
	const FString& M = A.Mode;
	const FString RawTarget = Str(A.Params, TEXT("target"), Str(A.Params, TEXT("contact_id")));
	const FString Target = Resolve(RawTarget);
	TArray<FContact> Cs;
	B->GetContacts(Cs);
	auto NeedTarget = [&](bool bFirm) -> bool
	{
		if (RawTarget.Equals(TEXT("action"), ESearchCase::IgnoreCase) && Target.IsEmpty())
		{
			Detail = TEXT("on the action: nothing to follow yet, it waits for the next fight");
			return true;                  // "the action" with no fight on: the mode waits (it follows whatever comes)
		}
		const FContact* C = FindContact(Cs, Target);
		if (!C)
		{
			Detail = Target.IsEmpty() ? FString::Printf(TEXT("%s needs a target"), *M) : FString::Printf(TEXT("no contact %s on the plot"), *Target);
			return false;
		}
		if (bFirm && C->Track < 2)
		{
			Detail = FString::Printf(TEXT("%s is only a bearing (no range): the helm can steer down it, not hold a distance"), *Target);
			return false;
		}
		return true;
	};
	if (Station == TEXT("helm"))
	{
		if (M == TEXT("hold"))
		{
			Sh->SteerTo(Sh->GetHeadingDeg(), Sh->GetMarkDeg());
			Detail = FString::Printf(TEXT("holding %03.0f mark %.0f%s"), Sh->GetHeadingDeg(), Sh->GetMarkDeg(),
			                         A.Params->HasField(TEXT("face_action")) && !A.Params->GetBoolField(TEXT("face_action")) ? TEXT(", bow kept as it is")
			                         : TEXT(", bow on the action if a fight starts"));
			return true;
		}
		if (M == TEXT("course"))
		{
			TSharedPtr<FJsonObject> C = MakeShared<FJsonObject>();
			C->SetNumberField(TEXT("heading_deg"), Num(A.Params, TEXT("heading_deg"), Sh->GetHeadingDeg()));
			C->SetNumberField(TEXT("mark_deg"), Num(A.Params, TEXT("mark_deg"), Sh->GetMarkDeg()));
			const bool bOk = Command(TEXT("set_course"), C, Detail);
			if (bOk && A.Params->HasField(TEXT("speed_pct")))
			{
				Sh->SetThrottle((float)Num(A.Params, TEXT("speed_pct"), Sh->GetThrottlePct()));
			}
			return bOk;
		}
		if (M == TEXT("intercept"))
		{
			if (!NeedTarget(false))
			{
				return false;
			}
			if (Target.IsEmpty())
			{
				return true;              // "the action" and no fight on yet: the executor starts the intercept when there is one
			}
			TSharedPtr<FJsonObject> C = Obj({{TEXT("contact_id"), Target}});
			C->SetNumberField(TEXT("standoff_km"), Num(A.Params, TEXT("standoff_km"), 6.0));
			const bool bOk = Command(TEXT("intercept"), C, Detail);
			if (bOk)
			{
				Sh->SetThrottle((float)Num(A.Params, TEXT("speed_pct"), FMath::Max(Sh->GetThrottlePct(), 80.f)));
			}
			return bOk;
		}
		if (M == TEXT("keep_on_bow") || M == TEXT("follow") || M == TEXT("orbit") || M == TEXT("broadside") || M == TEXT("formation"))
		{
			if (M == TEXT("formation") && Target.IsEmpty())
			{
				// the fleet's flagship leads
				for (const FContact& C : Cs)
				{
					if (C.Side == EAstraSide::Astra && C.bCapital)
					{
						A.Params->SetStringField(TEXT("target"), C.ContactId);
						Detail = FString::Printf(TEXT("taking station on %s"), *C.Label);
						return true;
					}
				}
				Detail = TEXT("no fleet ship to take station on");
				return false;
			}
			if (!NeedTarget(M != TEXT("keep_on_bow")))
			{
				return false;
			}
			const FContact* C = FindContact(Cs, Target);
			if (!C)
			{
				return true;              // "the action" and no fight on yet: NeedTarget has said so
			}
			Detail = FString::Printf(TEXT("%s %s%s"), *M.Replace(TEXT("_"), TEXT(" ")), *C->Label,
			                         C->RangeKm >= 0.0 ? *FString::Printf(TEXT(", %.1f km"), C->RangeKm) : TEXT(", range unknown"));
			return true;
		}
		if (M == TEXT("evade"))
		{
			Sh->SetThrottle(100.f);
			if (A.Until == TEXT("order"))
			{
				A.Until = TEXT("time:45");
			}
			Detail = TEXT("evasive pattern, full ahead");
			return true;
		}
		if (M == TEXT("retreat"))
		{
			Sh->SetThrottle(100.f);
			Detail = TEXT("breaking off at full ahead");
			return true;
		}
		if (M == TEXT("transit"))
		{
			return Command(TEXT("transit_gate"), Obj({{TEXT("system_name"), Str(A.Params, TEXT("system"), Str(A.Params, TEXT("system_name")))}}), Detail);
		}
		return false;
	}
	if (Station == TEXT("tactical"))
	{
		if (AspectName == TEXT("engagement"))
		{
			if (M == TEXT("hold_fire"))
			{
				EngagedId.Empty();
				return Command(TEXT("cease_fire"), nullptr, Detail);
			}
			if (M == TEXT("engage"))
			{
				// {targets: [ids]} or {target: id}; weapons: [railguns, lasers, missiles, torpedoes]; fire: sustained|volley|conserve
				const TArray<TSharedPtr<FJsonValue>>* List = nullptr;
				TArray<FString> Ids;
				if (A.Params->TryGetArrayField(TEXT("targets"), List))
				{
					for (const TSharedPtr<FJsonValue>& V : *List)
					{
						Ids.Add(V->AsString().ToUpper());
					}
				}
				if (!Target.IsEmpty())
				{
					Ids.AddUnique(Target);
				}
				// "hostiles": every hostile warship on the plot, the new ones too, until none is left
				int32 Live = 0;
				for (const FString& Id : Ids)
				{
					if (Id == TEXT("HOSTILES"))
					{
						for (const FContact& C : Cs)
						{
							Live += (C.Side == EAstraSide::Mandate && !C.bCraft) ? 1 : 0;
						}
						continue;
					}
					const FContact* C = FindContact(Cs, Resolve(Id));
					Live += (C && C->Side != EAstraSide::Astra) ? 1 : 0;
				}
				if (Live == 0 && !Ids.Contains(TEXT("HOSTILES")))
				{
					Detail = Ids.Num() ? TEXT("none of those contacts is a live hostile on the plot") : TEXT("engage needs a target");
					return false;
				}
				TArray<TSharedPtr<FJsonValue>> Arr;
				for (const FString& Id : Ids)
				{
					Arr.Add(MakeShared<FJsonValueString>(Id));
				}
				A.Params->SetArrayField(TEXT("targets"), Arr);
				Detail = Ids.Contains(TEXT("HOSTILES")) ? FString(TEXT("engaging every hostile warship, as they come, until none is left"))
				                                        : FString::Printf(TEXT("engaging %s until %s"), *FString::Join(Ids, TEXT(", ")), Ids.Num() > 1 ? TEXT("they are down") : TEXT("it is down"));
				return true;
			}
			Detail = M == TEXT("weapons_free") ? FString::Printf(TEXT("weapons free inside %.0f km"), Num(A.Params, TEXT("range_km"), 25.0))
			                                   : TEXT("returning fire on whoever fires on us");
			return true;
		}
		if (AspectName == TEXT("shields"))
		{
			if (M == TEXT("face_threat"))
			{
				LastShieldSector.Empty();
				Detail = TEXT("shields follow the main threat");
				return true;
			}
			const FString Sector = M == TEXT("sector") ? Str(A.Params, TEXT("sector"), TEXT("balanced")) : M == TEXT("shields_off") ? TEXT("off") : M;
			return Command(TEXT("set_shields"), Obj({{TEXT("mode"), Sector}}), Detail);
		}
		if (AspectName == TEXT("point_defense"))
		{
			const FString Pd = M == TEXT("pd_off") ? TEXT("off") : M == TEXT("protect") ? TEXT("protect") : TEXT("auto");
			TSharedPtr<FJsonObject> C = Obj({{TEXT("mode"), Pd}});
			if (!Target.IsEmpty())
			{
				C->SetStringField(TEXT("contact_id"), Target);
			}
			return Command(TEXT("set_point_defense"), C, Detail);
		}
		Detail = FString::Printf(TEXT("missiles: %s"), *M);
		return true;
	}
	if (Station == TEXT("sensors"))
	{
		if (AspectName == TEXT("emcon"))
		{
			if (M == TEXT("limited"))
			{
				A.Mode = TEXT("restricted");         // the ship's own word for it
			}
			return Command(TEXT("set_emcon"), Obj({{TEXT("level"), A.Mode}}), Detail);
		}
		if (AspectName == TEXT("scan"))
		{
			if (M == TEXT("sweep"))
			{
				A.Due = Now;          // a first pulse now
				Detail = FString::Printf(TEXT("active sweep every %.0f s"), Num(A.Params, TEXT("every_s"), 60.0));
				return true;
			}
			if (M == TEXT("focus"))
			{
				if (!NeedTarget(false))
				{
					return false;
				}
				A.Due = Now;
				Detail = FString::Printf(TEXT("sensors focused on %s"), *Target);
				return true;
			}
			Detail = TEXT("passive sensors only");
			return true;
		}
		Detail = FString::Printf(TEXT("%s %s"), *AspectName, *M);
		return true;
	}
	if (Station == TEXT("ops"))
	{
		if (AspectName == TEXT("datapad"))
		{
			// a page sent to the Captain's datapad: overview, contact{focus}, damage, fleet, orders
			UAstraScreensSubsystem* Scr = GetWorld()->GetSubsystem<UAstraScreensSubsystem>();
			const FString Page = Str(A.Params, TEXT("page"), TEXT("overview")).ToLower();
			const FString Focus = Str(A.Params, TEXT("focus"), Target);
			if (!Scr || !Scr->PushPad(Page, Focus, TEXT("ops")))
			{
				Detail = TEXT("datapad pages: overview, contact {focus: contact id}, damage, fleet, orders");
				return false;
			}
			Detail = FString::Printf(TEXT("datapad: the %s page%s is on the Captain's datapad"), *Page, Focus.IsEmpty() ? TEXT("") : *FString::Printf(TEXT(" on %s"), *Focus));
			return true;
		}
		if (AspectName == TEXT("holo"))
		{
			return Command(TEXT("holo_display"), Obj({{TEXT("mode"), M == TEXT("ship") ? TEXT("tactical") : M}}), Detail);
		}
		if (AspectName == TEXT("viewscreen") && M == TEXT("target") && !NeedTarget(false))
		{
			return false;
		}
		Detail = FString::Printf(TEXT("%s: %s%s"), *AspectName, *M, Target.IsEmpty() ? TEXT("") : *FString::Printf(TEXT(" %s"), *Target));
		return true;
	}
	if (Station == TEXT("engineering"))
	{
		if (AspectName == TEXT("power"))
		{
			TMap<FString, float> Want;
			if (M == TEXT("custom"))
			{
				for (const auto& KV : A.Params->Values)
				{
					double V = 0.0;
					if (KV.Value->TryGetNumber(V))
					{
						Want.Add(FString(*KV.Key), (float)V);
					}
				}
			}
			else if (!Profile(M, Want))
			{
				Detail = FString::Printf(TEXT("no power profile %s"), *M);
				return false;
			}
			// cuts first, then raises: every step stays inside the reactor's budget
			const TMap<FString, float>& Have = Sh->GetPowerPct();
			float Sum = 0.f;
			for (const auto& KV : Have)
			{
				const float* W = Want.Find(KV.Key);
				Sum += W ? *W : KV.Value;
			}
			if (Sum > Sh->GetPowerBudget() + 0.5f)
			{
				Detail = FString::Printf(TEXT("that profile needs %.0f%% of a %.0f%% budget"), Sum, Sh->GetPowerBudget());
				return false;
			}
			for (int32 Pass = 0; Pass < 2; ++Pass)
			{
				for (const auto& KV : Want)
				{
					const float* Cur = Have.Find(KV.Key);
					if (Cur && ((Pass == 0 && KV.Value < *Cur) || (Pass == 1 && KV.Value > *Cur)))
					{
						FString D;
						TSharedPtr<FJsonObject> C = Obj({{TEXT("system"), KV.Key}});
						C->SetNumberField(TEXT("percent"), KV.Value);
						Command(TEXT("route_power"), C, D);
					}
				}
			}
			Detail = FString::Printf(TEXT("power profile %s (%.0f%% of %.0f%%)"), *M, Sum, Sh->GetPowerBudget());
			return true;
		}
		if (AspectName == TEXT("heat") && M != TEXT("auto"))
		{
			const bool bOut = M == TEXT("radiators_extended") || M == TEXT("extended");
			return Command(TEXT("set_radiators"), Obj({{TEXT("state"), bOut ? TEXT("extended") : TEXT("retracted")}}), Detail);
		}
		if (AspectName == TEXT("reactor"))
		{
			Sh->SetBattleShort(M == TEXT("battle_short"));
			Detail = Sh->IsBattleShort() ? TEXT("battle short: 800% of power to allocate, the reactor runs hot") : TEXT("reactor back to its normal limits");
			return true;
		}
		Detail = FString::Printf(TEXT("%s %s"), *AspectName, *M);
		return true;
	}
	if (Station == TEXT("comms"))
	{
		if (AspectName == TEXT("channel") && M == TEXT("close"))
		{
			FString D;
			Command(TEXT("end_transmission"), nullptr, D);
		}
		Detail = FString::Printf(TEXT("%s %s%s"), *AspectName, *M, Target.IsEmpty() ? TEXT("") : *FString::Printf(TEXT(" %s"), *Target));
		return true;
	}
	if (Station == TEXT("flight"))
	{
		if (M == TEXT("recall") || M == TEXT("hold"))
		{
			SquadronTargets.Remove(AspectName);
			return M == TEXT("recall") ? B->RecallSquadron(AspectName, Detail) : (Detail = TEXT("on deck, ready"), true);
		}
		const bool bOk = B->LaunchSquadron(AspectName, M, Target, Detail);
		if (bOk && !Target.IsEmpty())
		{
			SquadronTargets.Add(AspectName, Target);
		}
		return bOk;
	}
	return false;
}

// ------------------------------------------------------------------------------------------------ the executors
void UAstraStationsSubsystem::Tick(float DeltaTime)
{
	if (!GetWorld() || Stations.Num() == 0)
	{
		return;
	}
	FAstraTimeline::SetWorld(GetWorld());
	Now = GetWorld()->GetTimeSeconds();
	Accum += DeltaTime;
	if (Accum < TickStep)
	{
		return;
	}
	Accum = 0.f;
	UAstraBattleSubsystem* B = Battle();
	if (!B || !Ship() || !B->IsStarted())
	{
		return;
	}
	// modes that ran out of time
	for (auto& SKV : Stations)
	{
		for (auto& AKV : SKV.Value.Aspects)
		{
			FAstraStationAspect& A = AKV.Value;
			if (A.Until.StartsWith(TEXT("time:")) && Now - A.Since >= FCString::Atod(*A.Until.Mid(5)))
			{
				const FString* Def = DefaultModes.Find(SKV.Key + TEXT(".") + AKV.Key);
				const FString Fallback = Def ? *Def : A.Mode;
				if (Fallback != A.Mode)
				{
					Expire(SKV.Key, AKV.Key, Fallback, TEXT("the time set for it is up"));
				}
				else
				{
					A.Until = TEXT("order");
				}
			}
		}
	}
	// what the bridge is looking at: tactical's target, else the nearest hostile the plot shows
	TArray<FContact> Cs;
	B->GetContacts(Cs);
	ActionTargetId.Empty();
	if (const FContact* E = EngagedId.IsEmpty() ? nullptr : FindContact(Cs, EngagedId))
	{
		ActionTargetId = E->ContactId;
	}
	else
	{
		for (const FContact& C : Cs)
		{
			if (C.Side == EAstraSide::Mandate && !C.bCraft && (C.RangeKm < 0.0 || C.RangeKm < 90.0))
			{
				ActionTargetId = C.ContactId;
				break;
			}
		}
	}
	TickHelm();
	TickTactical();
	TickSensors();
	TickEngineering();
	TickFlight();
	TickOps();
	TickReflexes();
	UpdateStatus();
}

bool UAstraStationsSubsystem::Reflex(const TCHAR* Station, const TCHAR* AspectName, const TCHAR* Mode, const FString& Report)
{
	TSharedPtr<FJsonObject> Args = MakeShared<FJsonObject>();
	Args->SetStringField(TEXT("station"), Station);
	Args->SetStringField(TEXT("aspect"), AspectName);
	Args->SetStringField(TEXT("mode"), Mode);
	FString Detail;
	if (!SetMode(Args, TEXT("auto"), Detail))
	{
		return false;
	}
	Act(Station, Report, true);     // the officer says it (a report: the crew's voice, the Captain's timeline)
	return true;
}

namespace
{
	TAutoConsoleVariable<int32> CVarStationReflexes(TEXT("astra.stations.reflexes"), 7,
		TEXT("The officers' own initiative on delegation auto, for comparisons: bits 1 CAP, 2 decoys, 4 combat power (0 = none)"));
}

void UAstraStationsSubsystem::TickReflexes()
{
	const int32 Bits = CVarStationReflexes.GetValueOnGameThread();
	if (Bits == 0)
	{
		return;
	}
	// once a second; never over a mode the Captain or an officer chose (set_by captain/officer), only over the defaults
	// and over what the reflexes themselves set
	if (Now < NextReflexAt)
	{
		return;
	}
	NextReflexAt = Now + 1.0;
	UAstraShipSubsystem* Sh = Ship();
	UAstraBattleSubsystem* B = Battle();
	if (!Sh || !B)
	{
		return;
	}
	TArray<FContact> Cs;
	B->GetContacts(Cs);
	int32 CraftNear = 0, WarshipsNear = 0;
	bool bUnderFire = false;
	for (const FContact& C : Cs)
	{
		if (C.Side != EAstraSide::Mandate)
		{
			continue;
		}
		CraftNear += (C.bCraft && C.RangeKm >= 0.0 && C.RangeKm < 45.0) ? 1 : 0;
		WarshipsNear += (!C.bCraft && C.Track >= 2 && C.RangeKm < 60.0) ? 1 : 0;
		bUnderFire |= C.bFiringAtUs;
	}
	const bool bFight = CraftNear > 0 || WarshipsNear > 0 || bUnderFire;
	if (bFight)
	{
		LastFightAt = Now;
	}
	auto Free = [](const FAstraStationAspect* A) { return A && (A->SetBy == TEXT("default") || A->SetBy == TEXT("auto")); };
	auto OnAuto = [this](const TCHAR* Id) { const FAstraStation* S = Stations.Find(Id); return S && S->Delegation == TEXT("auto"); };

	// flight: Alpha up on combat air patrol over the Aquila when the enemy comes near; back aboard after three quiet minutes
	if ((Bits & 1) && OnAuto(TEXT("flight")))
	{
		const FAstraStationAspect* Al = Aspect(TEXT("flight"), TEXT("alpha"));
		if (bFight && Free(Al) && (Al->Mode == TEXT("hold") || Al->Mode == TEXT("recall")))
		{
			Reflex(TEXT("flight"), TEXT("alpha"), TEXT("cap"), CraftNear ? FString::Printf(TEXT("launching Alpha on combat air patrol: %d enemy craft inbound"), CraftNear)
			                                                             : FString(TEXT("launching Alpha on combat air patrol over the Aquila")));
		}
		else if (!bFight && Now - LastFightAt > 180.0 && Al && Al->SetBy == TEXT("auto") && Al->Mode == TEXT("cap"))
		{
			Reflex(TEXT("flight"), TEXT("alpha"), TEXT("recall"), TEXT("the sky is quiet: recalling Alpha to rearm"));
		}
	}
	// tactical: decoys into a missile salvo closing on us (two launches a minute at most: the stock is small)
	if ((Bits & 2) && OnAuto(TEXT("tactical")))
	{
		TArray<FVector> Missiles;
		B->GetInboundMissiles(Missiles);
		int32 Close = 0;
		for (const FVector& M : Missiles)
		{
			Close += FVector::Dist(M, B->PlayerPos()) < 12000.0 ? 1 : 0;
		}
		if (Close >= 2 && Now - LastDecoysAt > 30.0)
		{
			LastDecoysAt = Now;
			FString Detail;
			if (Command(TEXT("launch_decoys"), nullptr, Detail))
			{
				Act(TEXT("tactical"), FString::Printf(TEXT("decoys away: %d missiles closing"), Close), true);
			}
		}
	}
	// engineering: power to shields and weapons while the fight lasts, back to balanced two quiet minutes after
	if ((Bits & 4) && OnAuto(TEXT("engineering")))
	{
		const FAstraStationAspect* Pw = Aspect(TEXT("engineering"), TEXT("power"));
		if (bFight && Free(Pw) && Pw->Mode == TEXT("balanced"))
		{
			Reflex(TEXT("engineering"), TEXT("power"), TEXT("combat"), TEXT("combat power: shields and weapons up, life support and engines trimmed"));
		}
		else if (!bFight && Now - LastFightAt > 120.0 && Pw && Pw->SetBy == TEXT("auto") && Pw->Mode == TEXT("combat"))
		{
			Reflex(TEXT("engineering"), TEXT("power"), TEXT("balanced"), TEXT("fight's over: power back to balanced"));
		}
	}
}

void UAstraStationsSubsystem::TickOps()
{
	// damage control on auto: every free team to the worst open incident — breaches first (the air goes), then fires
	// (they spread), then the power conduits of what a fight needs; "priority {what}" puts one kind, system or deck first
	UAstraShipSubsystem* Sh = Ship();
	const FAstraStation* S = Stations.Find(TEXT("ops"));
	const FAstraStationAspect* A = S ? S->Aspects.Find(TEXT("damage_control")) : nullptr;
	if (!Sh || !A || S->Delegation != TEXT("auto"))
	{
		return;
	}
	const TArray<FAstraDamage>& Dmg = Sh->GetDamage();
	int32 Busy = 0;
	for (const FAstraDamage& D : Dmg)
	{
		Busy += D.Team >= 0 ? 1 : 0;
	}
	if (Busy >= Sh->GetNumDamageTeams())
	{
		return;
	}
	const FString What = A->Mode == TEXT("priority") ? Str(A->Params, TEXT("what"), Str(A->Params, TEXT("target"))).ToLower() : FString();
	auto Score = [&What](const FAstraDamage& D)
	{
		float Sc = D.Kind.Contains(TEXT("breach")) ? 100.f : (D.Kind.Contains(TEXT("fire")) ? 80.f : 50.f);
		if (D.System.Contains(TEXT("shield")) || D.System.Contains(TEXT("weapon")) || D.System.Contains(TEXT("engine")))
		{
			Sc += 10.f;
		}
		if (!What.IsEmpty() && (D.Kind.Contains(What) || D.System.Contains(What) || D.Where().Contains(What)))
		{
			Sc += 200.f;
		}
		return Sc;
	};
	const FAstraDamage* Best = nullptr;
	for (const FAstraDamage& D : Dmg)
	{
		if (D.Team < 0 && (!Best || Score(D) > Score(*Best)))
		{
			Best = &D;
		}
	}
	if (!Best)
	{
		return;
	}
	const FString Kind = Best->Kind, Where = Best->Where();   // copies: the command changes the list
	const int32 IncidentId = Best->Id;
	TSharedPtr<FJsonObject> Args = MakeShared<FJsonObject>();
	Args->SetNumberField(TEXT("id"), IncidentId);
	Args->SetNumberField(TEXT("deck"), Best->Deck);
	Args->SetStringField(TEXT("section"), FString::Chr(Best->Section));
	Args->SetStringField(TEXT("priority"), Kind.Contains(TEXT("breach")) ? TEXT("critical") : TEXT("normal"));
	FString Detail;
	const bool bSent = Command(TEXT("dispatch_damage_control"), Args, Detail);
	const FAstraDamage* After = Sh->GetDamage().FindByPredicate([IncidentId](const FAstraDamage& X) { return X.Id == IncidentId; });
	if (bSent && After && After->Team >= 0)
	{
		Act(TEXT("ops"), FString::Printf(TEXT("damage control: team %d to the %s at %s"), After->Team + 1, *Kind, *Where), false);
	}
}

void UAstraStationsSubsystem::Expire(const FString& Station, const FString& AspectName, const FString& Fallback, const FString& Why)
{
	FAstraStationAspect* A = Aspect(Station, AspectName);
	if (!A)
	{
		return;
	}
	const FString Was = A->Mode;
	A->Mode = Fallback;
	A->Params = MakeShared<FJsonObject>();
	if (Station == TEXT("helm") && Fallback == TEXT("hold"))
	{
		A->Params->SetBoolField(TEXT("face_action"), true);
		if (UAstraShipSubsystem* Sh = Ship())
		{
			Sh->SteerTo(Sh->GetHeadingDeg(), Sh->GetMarkDeg());
		}
	}
	A->Until = TEXT("order");
	A->SetBy = TEXT("auto");
	A->Since = Now;
	Act(Station, FString::Printf(TEXT("%s ended (%s): back to %s"), *Was.Replace(TEXT("_"), TEXT(" ")), *Why, *Fallback.Replace(TEXT("_"), TEXT(" "))), true);
}

void UAstraStationsSubsystem::TickHelm()
{
	FAstraStationAspect* A = Aspect(TEXT("helm"), TEXT("course"));
	UAstraShipSubsystem* Sh = Ship();
	UAstraBattleSubsystem* B = Battle();
	if (!A || !Sh || !B || B->IsGateRunActive())
	{
		return;
	}
	const FString& M = A->Mode;
	const FString Raw = Str(A->Params, TEXT("target"), Str(A->Params, TEXT("contact_id")));
	const bool bFollowsAction = Raw.Equals(TEXT("action"), ESearchCase::IgnoreCase);
	const FString Target = Resolve(Raw);
	TArray<FContact> Cs;
	B->GetContacts(Cs);
	const FContact* T = Target.IsEmpty() ? nullptr : FindContact(Cs, Target);
	const bool bNeedsTarget = M == TEXT("intercept") || M == TEXT("keep_on_bow") || M == TEXT("follow") || M == TEXT("orbit")
	                       || M == TEXT("broadside") || M == TEXT("formation");
	if (bNeedsTarget && !T)
	{
		if (bFollowsAction)
		{
			return;                       // no fight right now: the mode waits for the next one (it follows the action)
		}
		Expire(TEXT("helm"), TEXT("course"), TEXT("hold"), FString::Printf(TEXT("%s is no longer on the plot"), *Target));
		return;
	}
	if (M == TEXT("intercept"))
	{
		// the ship's own intercept flies it; if someone else took the helm, the mode follows
		if (Sh->GetInterceptId().IsEmpty())
		{
			Expire(TEXT("helm"), TEXT("course"), TEXT("hold"), TEXT("the intercept was broken off"));
		}
		return;
	}
	if (Now < A->Due)
	{
		return;
	}
	A->Due = Now + 0.5;
	const FVector P = B->PlayerPos();
	auto Steer = [&](const FVector& Point)
	{
		Sh->SteerTo((float)B->BearingTo(Point), (float)B->MarkTo(Point));
	};
	auto SpeedFor = [&](double Mps)
	{
		Sh->SetThrottle((float)FMath::Clamp(Mps / 4.8, 0.0, 100.0));
	};
	if (M == TEXT("hold"))
	{
		// in a fight, the bow comes round to the action (unless the Captain wants the heading kept)
		const bool bFace = !A->Params->HasField(TEXT("face_action")) || A->Params->GetBoolField(TEXT("face_action"));
		const FContact* Act_ = ActionTargetId.IsEmpty() ? nullptr : FindContact(Cs, ActionTargetId);
		if (bFace && Act_ && B->IsEngaged())
		{
			const double Off = AngleDeg(Sh->GetHeadingDeg(), Sh->GetMarkDeg(), Act_->BearingDeg, FMath::Clamp(Act_->MarkDeg, -60.0, 60.0));
			const bool bFacing = A->Step == 1;
			if (Off > (bFacing ? 3.0 : 12.0))
			{
				Sh->SteerTo((float)Act_->BearingDeg, (float)FMath::Clamp(Act_->MarkDeg, -60.0, 60.0));
				if (!bFacing)
				{
					A->Step = 1;
					Act(TEXT("helm"), FString::Printf(TEXT("bringing the bow round to %s"), *Act_->Label), false);
				}
			}
			else
			{
				A->Step = 0;
			}
		}
		return;
	}
	if (M == TEXT("keep_on_bow"))
	{
		Steer(T->Pos + T->Vel * 2.0);
		return;
	}
	if (M == TEXT("follow") || M == TEXT("formation"))
	{
		const double D = Num(A->Params, TEXT("distance_km"), M == TEXT("formation") ? 3.0 : 2.0) * 1000.0;
		const FString Side = Str(A->Params, TEXT("side"), Str(A->Params, TEXT("slot"), TEXT("astern"))).ToLower();
		FVector Fwd = T->Vel.SizeSquared() > 25.0 ? T->Vel.GetSafeNormal() : (T->Pos - P).GetSafeNormal();
		const FVector Up = FVector::UpVector;
		const FVector Right = FVector::CrossProduct(Up, Fwd).GetSafeNormal();
		const FVector Offset = Side == TEXT("port") ? -Right * D : Side == TEXT("starboard") ? Right * D : Side == TEXT("above") ? Up * D
		                     : Side == TEXT("below") ? -Up * D : -Fwd * D;
		const FVector Goal = T->Pos + Offset;
		const double Gap = FVector::Dist(P, Goal);
		if (Gap > 400.0)
		{
			Steer(Goal + T->Vel * 4.0);
		}
		else
		{
			Steer(P + Fwd * 10000.0);                   // on station: the leader's heading
		}
		SpeedFor(T->Vel.Size() + FMath::Clamp(Gap / 12.0, -150.0, 220.0) * (FVector::DotProduct(Goal - P, Fwd) >= 0.0 ? 1.0 : -1.0));
		return;
	}
	if (M == TEXT("orbit"))
	{
		const double R = Num(A->Params, TEXT("radius_km"), 8.0) * 1000.0;
		const FVector Rv = P - T->Pos;
		const double Dist = Rv.Size();
		const FVector Rn = Rv.GetSafeNormal();
		FVector Tangent = FVector::CrossProduct(FVector::UpVector, Rn).GetSafeNormal();
		if (Str(A->Params, TEXT("direction"), TEXT("ccw")).ToLower() == TEXT("cw"))
		{
			Tangent = -Tangent;
		}
		const double Corr = FMath::Clamp((Dist - R) / FMath::Max(R, 1.0), -1.0, 1.0);
		Steer(P + (Tangent - Rn * Corr * 1.5).GetSafeNormal() * 10000.0);
		return;
	}
	if (M == TEXT("broadside"))
	{
		const double R = Num(A->Params, TEXT("range_km"), 8.0);
		FString Side = Str(A->Params, TEXT("side"), TEXT("auto")).ToLower();
		const double Brg = T->BearingDeg;
		const double Port = WrapDeg(Brg + 90.0), Stbd = WrapDeg(Brg - 90.0);
		if (Side == TEXT("auto"))
		{
			const double H = Sh->GetHeadingDeg();
			Side = FMath::Abs(FMath::FindDeltaAngleDegrees(H, Port)) < FMath::Abs(FMath::FindDeltaAngleDegrees(H, Stbd)) ? TEXT("port") : TEXT("starboard");
			A->Params->SetStringField(TEXT("side"), Side);
		}
		double H = Side == TEXT("port") ? Port : Stbd;
		if (T->RangeKm > R + 1.5)
		{
			H = WrapDeg(H + (Side == TEXT("port") ? -35.0 : 35.0));     // edge in
		}
		else if (T->RangeKm >= 0.0 && T->RangeKm < R - 1.5)
		{
			H = WrapDeg(H + (Side == TEXT("port") ? 35.0 : -35.0));     // open the range
		}
		Sh->SteerTo((float)H, 0.f);
		return;
	}
	if (M == TEXT("evade"))
	{
		// a jink every six or seven seconds, alternating sides, with a little climb or dive
		if (Now - A->Since >= A->Step * 6.5)
		{
			const double Jink = (A->Step % 2 == 0 ? 1.0 : -1.0) * FMath::FRandRange(28.0, 48.0);
			Sh->SteerTo((float)WrapDeg(Sh->GetHeadingDeg() + Jink), (float)FMath::FRandRange(-6.0, 6.0));
			++A->Step;
		}
		return;
	}
	if (M == TEXT("retreat"))
	{
		FVector Threat = FVector::ZeroVector;
		int32 N = 0;
		for (const FContact& C : Cs)
		{
			if (C.Side == EAstraSide::Mandate && !C.bCraft && (C.RangeKm < 0.0 || C.RangeKm < 70.0))
			{
				Threat += C.Pos;
				++N;
			}
		}
		if (N > 0)
		{
			Steer(P + (P - Threat / N).GetSafeNormal() * 10000.0);
		}
		A->Due = Now + 2.0;
	}
}

void UAstraStationsSubsystem::TickTactical()
{
	FAstraStation* S = Stations.Find(TEXT("tactical"));
	UAstraBattleSubsystem* B = Battle();
	if (!S || !B)
	{
		return;
	}
	FAstraStationAspect& Eng = S->Aspects[TEXT("engagement")];
	FAstraStationAspect& Shields = S->Aspects[TEXT("shields")];
	if (Now < Eng.Due)
	{
		return;
	}
	Eng.Due = Now + 1.0;
	TArray<FContact> Cs;
	B->GetContacts(Cs);
	const UAstraBattleSubsystem::FFireControl FC = B->GetFireControl();
	// --- who to shoot
	FString Want;
	if (Eng.Mode == TEXT("engage"))
	{
		const TArray<TSharedPtr<FJsonValue>>* List = nullptr;
		if (Eng.Params->TryGetArrayField(TEXT("targets"), List))
		{
			for (const TSharedPtr<FJsonValue>& V : *List)
			{
				const FString Id = V->AsString().ToUpper();
				if (Id == TEXT("HOSTILES"))
				{
					// every hostile warship: stay on the one we fight while it is inside missile range, else the best one in
					// reach — whoever is firing on us first, then the nearest (the plot is nearest first) — never a chase
					const FContact* Cur = EngagedId.IsEmpty() ? nullptr : FindContact(Cs, EngagedId);
					if (Cur && Cur->Side == EAstraSide::Mandate && Cur->RangeKm >= 0.0 && Cur->RangeKm < 25.0)
					{
						Want = Cur->ContactId;
						break;
					}
					const FContact* Best = nullptr;
					for (const FContact& C : Cs)
					{
						if (C.Side != EAstraSide::Mandate || C.bCraft || C.Track < 2)
						{
							continue;
						}
						if (!Best || (C.bFiringAtUs && !Best->bFiringAtUs && C.RangeKm < 30.0))
						{
							Best = &C;
						}
					}
					if (Best)
					{
						Want = Best->ContactId;
						break;
					}
					continue;
				}
				const FContact* C = FindContact(Cs, Resolve(Id));
				if (C && C->Side != EAstraSide::Astra)
				{
					Want = C->ContactId;
					break;
				}
			}
		}
		bool bAllHostiles = false;
		if (List)
		{
			for (const TSharedPtr<FJsonValue>& V : *List)
			{
				bAllHostiles |= V->AsString().Equals(TEXT("hostiles"), ESearchCase::IgnoreCase);
			}
		}
		if (Want.IsEmpty() && bAllHostiles)
		{
			EngagedId.Empty();            // no hostile warship on the plot now: the order stands for the next one
			return;
		}
		if (Want.IsEmpty())
		{
			Expire(TEXT("tactical"), TEXT("engagement"), TEXT("return_fire"), TEXT("the targets are down or gone"));
			EngagedId.Empty();
			return;
		}
	}
	else if (Eng.Mode == TEXT("return_fire") || Eng.Mode == TEXT("weapons_free"))
	{
		const double Range = Eng.Mode == TEXT("weapons_free") ? Num(Eng.Params, TEXT("range_km"), 25.0) : 30.0;
		double Best = -1e9;
		for (const FContact& C : Cs)
		{
			if (C.Side != EAstraSide::Mandate || C.Track < 2 || C.RangeKm > Range)
			{
				continue;
			}
			if (Eng.Mode == TEXT("return_fire") && !C.bFiringAtUs)
			{
				continue;
			}
			if (C.bCraft && C.RangeKm > 6.0)
			{
				continue;                    // the guns do not chase fighters far out: that is point defence's
			}
			const double Score = (C.bFiringAtUs ? 3.0 : 0.0) + (C.bCapital ? 2.0 : 0.0) + (C.ContactId == EngagedId ? 1.5 : 0.0) - C.RangeKm / 20.0;
			if (Score > Best)
			{
				Best = Score;
				Want = C.ContactId;
			}
		}
	}
	if (Want != EngagedId)
	{
		if (!Want.IsEmpty())
		{
			const FContact* C = FindContact(Cs, Want);
			Act(TEXT("tactical"), FString::Printf(TEXT("engaging %s (%s)"), C ? *C->Label : *Want,
			                                        EngagedId.IsEmpty() ? TEXT("new target") : *FString::Printf(TEXT("was %s"), *EngagedId)),
			    !EngagedId.IsEmpty());
		}
		EngagedId = Want;
		Eng.Step = 0;                     // a new target: a new volley, a new "no solution" report if it comes to that
	}
	// --- keep the guns and the cells on it (the battle opens fire by itself once inside each weapon's range)
	if (!EngagedId.IsEmpty() && Eng.Mode != TEXT("hold_fire"))
	{
		const FContact* C = FindContact(Cs, EngagedId);
		TArray<FString> Weapons;
		const TArray<TSharedPtr<FJsonValue>>* W = nullptr;
		if (Eng.Params->TryGetArrayField(TEXT("weapons"), W) && W->Num())
		{
			for (const TSharedPtr<FJsonValue>& V : *W) { Weapons.Add(V->AsString().ToLower()); }
		}
		else
		{
			Weapons = {TEXT("railguns"), TEXT("lasers"), TEXT("missiles")};
		}
		FString D;
		if (C && C->Track >= 2)
		{
			if (Weapons.Contains(TEXT("railguns")) && (FC.Target != EngagedId || FC.RailVolleys == 0))
			{
				B->PlayerFire(TEXT("railguns"), EngagedId, 3, D);
			}
			if (Weapons.Contains(TEXT("lasers")) && (FC.Target != EngagedId || FC.LaserShots == 0))
			{
				B->PlayerFire(TEXT("lasers"), EngagedId, 3, D);
			}
			const FString Policy = ModeOf(TEXT("tactical"), TEXT("missiles"));
			const FString Fire = Str(Eng.Params, TEXT("fire"), TEXT("sustained")).ToLower();
			// the magazine is finite: a salvo every cycle only to saturate; normally four every 12 s, sparingly two every 20 s
			const bool bSaturate = Policy == TEXT("saturate");
			const bool bConserve = Policy == TEXT("conserve") || Fire == TEXT("conserve");
			const double Interval = bSaturate ? 0.0 : bConserve ? 20.0 : 12.0;
			const bool bMissiles = (Weapons.Contains(TEXT("missiles")) || Weapons.Contains(TEXT("torpedoes")))
			                    && FC.MissileCycle <= 0.f && FC.Missiles > 0 && C->RangeKm >= 0.0 && C->RangeKm <= 25.0
			                    && Now - LastSalvoAt >= Interval
			                    && !(Fire == TEXT("volley") && Eng.Step > 0) && (!bConserve || C->bCapital);
			if (bMissiles && !C->bCraft)
			{
				const int32 N = bSaturate ? 8 : bConserve ? 2 : 4;
				if (B->PlayerFire(TEXT("missiles"), EngagedId, FMath::Min(N, FC.Missiles), D))
				{
					LastSalvoAt = Now;
					++Eng.Step;
					Act(TEXT("tactical"), FString::Printf(TEXT("%d missiles at %s"), FMath::Min(N, FC.Missiles), *C->Label), false);
				}
			}
		}
		else if (C && Eng.Step >= 0)
		{
			// only a bearing: no firing solution; the sensors get the job (if they may act on their own)
			Eng.Step = -1;
			Act(TEXT("tactical"), FString::Printf(TEXT("no firing solution on %s (a bearing only): asking the sensors for a track"), *C->Label), true);
			const FAstraStation* Sen = Stations.Find(TEXT("sensors"));
			if (Sen && Sen->Delegation == TEXT("auto") && ModeOf(TEXT("sensors"), TEXT("scan")) != TEXT("focus"))
			{
				TSharedPtr<FJsonObject> Args = MakeShared<FJsonObject>();
				Args->SetStringField(TEXT("station"), TEXT("sensors"));
				Args->SetStringField(TEXT("mode"), TEXT("focus"));
				Args->SetObjectField(TEXT("params"), Obj({{TEXT("target"), C->ContactId}}));
				FString Why;
				SetMode(Args, TEXT("sensors"), Why);
			}
		}
	}
	// --- the shields turn to the main threat (inbound missiles first, then the nearest warship shooting at us)
	if (Shields.Mode == TEXT("face_threat") && Now >= Shields.Due)
	{
		Shields.Due = Now + 2.0;
		TArray<FVector> Missiles;
		B->GetInboundMissiles(Missiles);
		FVector Threat = FVector::ZeroVector;
		FString Why;
		if (Missiles.Num())
		{
			for (const FVector& M : Missiles) { Threat += M; }
			Threat /= Missiles.Num();
			Why = FString::Printf(TEXT("%d missiles inbound"), Missiles.Num());
		}
		else
		{
			for (const FContact& C : Cs)
			{
				if (C.Side == EAstraSide::Mandate && C.bCapital && C.Track >= 2 && (C.bFiringAtUs || C.RangeKm < 20.0))
				{
					Threat = C.Pos;
					Why = C.Label;
					break;
				}
			}
		}
		FString Sector = TEXT("balanced");
		if (!Threat.IsZero())
		{
			const FVector L = B->PlayerAtt().Inverse().RotateVector((Threat - B->PlayerPos()).GetSafeNormal());
			const FVector Ab = L.GetAbs();
			Sector = Ab.X >= Ab.Y && Ab.X >= Ab.Z ? (L.X > 0 ? TEXT("forward") : TEXT("aft"))
			       : Ab.Y >= Ab.Z ? (L.Y > 0 ? TEXT("starboard") : TEXT("port")) : (L.Z > 0 ? TEXT("dorsal") : TEXT("ventral"));
		}
		if (Sector != LastShieldSector)
		{
			if (ShieldSectorSince <= 0.0)
			{
				ShieldSectorSince = Now;
			}
			else if (Now - ShieldSectorSince >= 2.0 || LastShieldSector.IsEmpty())
			{
				FString D;
				if (Command(TEXT("set_shields"), Obj({{TEXT("mode"), Sector}}), D))
				{
					Act(TEXT("tactical"), Sector == TEXT("balanced") ? TEXT("shields rebalanced") : FString::Printf(TEXT("shields reinforced %s (%s)"), *Sector, *Why), false);
				}
				LastShieldSector = Sector;
				ShieldSectorSince = 0.0;
			}
		}
		else
		{
			ShieldSectorSince = 0.0;
		}
	}
}

void UAstraStationsSubsystem::TickSensors()
{
	FAstraStationAspect* Scan = Aspect(TEXT("sensors"), TEXT("scan"));
	UAstraBattleSubsystem* B = Battle();
	if (!Scan || !B || Now < Scan->Due)
	{
		return;
	}
	FString D;
	if (Scan->Mode == TEXT("sweep"))
	{
		Command(TEXT("active_scan"), nullptr, D);
		Scan->Due = Now + FMath::Max(Num(Scan->Params, TEXT("every_s"), 60.0), 15.0);
		Act(TEXT("sensors"), FString::Printf(TEXT("active sweep: %s"), *D.Left(120)), false);
	}
	else if (Scan->Mode == TEXT("focus"))
	{
		const FString Target = Resolve(Str(Scan->Params, TEXT("target"), Str(Scan->Params, TEXT("contact_id"))));
		TArray<FContact> Cs;
		B->GetContacts(Cs);
		const FContact* C = FindContact(Cs, Target);
		if (!C)
		{
			Expire(TEXT("sensors"), TEXT("scan"), TEXT("passive"), FString::Printf(TEXT("%s is gone"), *Target));
			return;
		}
		Scan->Due = Now + 20.0;
		if (C->Track < 2)
		{
			Command(TEXT("active_scan"), Obj({{TEXT("contact_id"), Target}}), D);
			Act(TEXT("sensors"), FString::Printf(TEXT("focused ping on %s: %s"), *Target, *D.Left(120)), false);
		}
	}
	else
	{
		Scan->Due = Now + 1.0;
	}
}

void UAstraStationsSubsystem::TickEngineering()
{
	FAstraStationAspect* Heat = Aspect(TEXT("engineering"), TEXT("heat"));
	UAstraShipSubsystem* Sh = Ship();
	if (!Heat || !Sh || Heat->Mode != TEXT("auto") || Now < Heat->Due)
	{
		return;
	}
	Heat->Due = Now + 2.0;
	const float H = Sh->GetHeatPct();
	const bool bSilent = Sh->GetEmcon().Equals(TEXT("silent"), ESearchCase::IgnoreCase);
	FString D;
	if (H > 65.f && !Sh->AreRadiatorsOut() && !bSilent)
	{
		if (Command(TEXT("set_radiators"), Obj({{TEXT("state"), TEXT("extended")}}), D))
		{
			Act(TEXT("engineering"), FString::Printf(TEXT("heat %.0f%%: radiators extended (they show on the enemy's sensors)"), H), true);
		}
	}
	else if (H < 28.f && Sh->AreRadiatorsOut())
	{
		if (Command(TEXT("set_radiators"), Obj({{TEXT("state"), TEXT("retracted")}}), D))
		{
			Act(TEXT("engineering"), FString::Printf(TEXT("heat down to %.0f%%: radiators in"), H), false);
		}
	}
	else if (H > 96.f && Sh->GetCoolantVents() > 0)
	{
		if (Command(TEXT("vent_heat"), nullptr, D))
		{
			Act(TEXT("engineering"), FString::Printf(TEXT("heat %.0f%%: emergency coolant vent"), H), true);
		}
	}
}

void UAstraStationsSubsystem::TickFlight()
{
	UAstraBattleSubsystem* B = Battle();
	if (!B || SquadronTargets.Num() == 0)
	{
		return;
	}
	TArray<FContact> Cs;
	B->GetContacts(Cs);
	TArray<FString> Done;
	for (const auto& KV : SquadronTargets)
	{
		if (!FindContact(Cs, KV.Value))
		{
			Done.Add(KV.Key);
		}
	}
	for (const FString& Sq : Done)
	{
		const FString Target = SquadronTargets[Sq];
		SquadronTargets.Remove(Sq);
		FString D;
		if (B->LaunchSquadron(Sq, TEXT("cap"), FString(), D))
		{
			if (FAstraStationAspect* A = Aspect(TEXT("flight"), Sq))
			{
				A->Mode = TEXT("cap");
				A->Params = MakeShared<FJsonObject>();
				A->SetBy = TEXT("auto");
				A->Since = Now;
			}
			Act(TEXT("flight"), FString::Printf(TEXT("%s's target %s is gone: %s back on combat air patrol"), *Sq, *Target, *Sq), true);
		}
	}
}

// ------------------------------------------------------------------------------------------------ reports, status, state
void UAstraStationsSubsystem::Act(const FString& Station, const FString& Text, bool bReport)
{
	if (FAstraStation* S = Stations.Find(Station))
	{
		S->Actions.Add(Text);
		if (S->Actions.Num() > 6)
		{
			S->Actions.RemoveAt(0);
		}
	}
	FAstraTimeline::Record(TEXT("station"), FString::Printf(TEXT("%s: %s"), *Station, *Text));
	if (bReport)
	{
		if (UAstraShipSubsystem* Sh = Ship())
		{
			Sh->PublishEvent(FString::Printf(TEXT("%s: %s"), *Station, *Text), true);
		}
	}
}

void UAstraStationsSubsystem::UpdateStatus()
{
	UAstraShipSubsystem* Sh = Ship();
	UAstraBattleSubsystem* B = Battle();
	if (!Sh || !B)
	{
		return;
	}
	TArray<FContact> Cs;
	B->GetContacts(Cs);
	auto Label = [&Cs](const FString& Id) -> FString
	{
		const FContact* C = Id.IsEmpty() ? nullptr : FindContact(Cs, Id);
		return C ? (C->RangeKm >= 0.0 ? FString::Printf(TEXT("%s at %.1f km"), *C->Label, C->RangeKm) : FString::Printf(TEXT("%s (bearing %03.0f)"), *C->Label, C->BearingDeg))
		         : Id;
	};
	if (FAstraStation* S = Stations.Find(TEXT("helm")))
	{
		const FAstraStationAspect& A = S->Aspects[TEXT("course")];
		const FString T = Str(A.Params, TEXT("target"), Str(A.Params, TEXT("contact_id")));
		S->Status = FString::Printf(TEXT("%s%s · heading %03.0f mark %.0f · %.0f m/s (throttle %.0f%%)"), *A.Mode.Replace(TEXT("_"), TEXT(" ")).ToUpper(),
		                            T.IsEmpty() ? TEXT("") : *FString::Printf(TEXT(" %s"), *Label(T)), Sh->GetHeadingDeg(), Sh->GetMarkDeg(), Sh->GetSpeedMps(), Sh->GetThrottlePct());
	}
	if (FAstraStation* S = Stations.Find(TEXT("tactical")))
	{
		const UAstraBattleSubsystem::FFireControl FC = B->GetFireControl();
		S->Status = FString::Printf(TEXT("%s%s · rails %d · lasers %d · VLS %d%s · shields %s · PD %s"),
		                            *S->Aspects[TEXT("engagement")].Mode.Replace(TEXT("_"), TEXT(" ")).ToUpper(),
		                            EngagedId.IsEmpty() ? TEXT("") : *FString::Printf(TEXT(" %s"), *Label(EngagedId)), FC.RailVolleys, FC.LaserShots, FC.Missiles,
		                            FC.MissileCycle > 0.f ? *FString::Printf(TEXT(" (next %.0f s)"), FC.MissileCycle) : TEXT(""),
		                            *Sh->GetShieldMode(), *S->Aspects[TEXT("point_defense")].Mode.Replace(TEXT("pd_"), TEXT("")));
	}
	if (FAstraStation* S = Stations.Find(TEXT("sensors")))
	{
		int32 Firm = 0;
		for (const FContact& C : Cs) { Firm += C.Track >= 2 ? 1 : 0; }
		S->Status = FString::Printf(TEXT("EMCON %s · scan %s · %d contacts, %d tracked"), *Sh->GetEmcon().ToUpper(), *S->Aspects[TEXT("scan")].Mode, Cs.Num(), Firm);
	}
	if (FAstraStation* S = Stations.Find(TEXT("ops")))
	{
		S->Status = FString::Printf(TEXT("screen %s · holo %s · damage control %s"), *S->Aspects[TEXT("viewscreen")].Mode, *Sh->GetHoloMode(),
		                            *S->Aspects[TEXT("damage_control")].Mode);
	}
	if (FAstraStation* S = Stations.Find(TEXT("engineering")))
	{
		S->Status = FString::Printf(TEXT("power %s · reactor %.0f%% · heat %.0f%% · radiators %s · vents %d"), *S->Aspects[TEXT("power")].Mode,
		                            Sh->GetReactorPct(), Sh->GetHeatPct(), Sh->AreRadiatorsOut() ? TEXT("out") : TEXT("in"), Sh->GetCoolantVents());
	}
	if (FAstraStation* S = Stations.Find(TEXT("comms")))
	{
		S->Status = FString::Printf(TEXT("channel %s · listening %s"), *S->Aspects[TEXT("channel")].Mode, *S->Aspects[TEXT("listen")].Mode);
	}
	if (FAstraStation* S = Stations.Find(TEXT("flight")))
	{
		S->Status = B->FlightLine();
	}
}

TSharedRef<FJsonObject> UAstraStationsSubsystem::StationsJson() const
{
	TSharedRef<FJsonObject> Root = MakeShared<FJsonObject>();
	for (const auto& SKV : Stations)
	{
		const FAstraStation& S = SKV.Value;
		TSharedRef<FJsonObject> O = MakeShared<FJsonObject>();
		O->SetStringField(TEXT("officer"), S.Officer);
		O->SetStringField(TEXT("delegation"), S.Delegation);
		O->SetStringField(TEXT("status"), S.Status);
		TSharedRef<FJsonObject> As = MakeShared<FJsonObject>();
		for (const auto& AKV : S.Aspects)
		{
			const FAstraStationAspect& A = AKV.Value;
			TSharedRef<FJsonObject> Ao = MakeShared<FJsonObject>();
			Ao->SetStringField(TEXT("mode"), A.Mode);
			if (A.Params.IsValid() && A.Params->Values.Num())
			{
				Ao->SetObjectField(TEXT("params"), A.Params);
			}
			Ao->SetStringField(TEXT("until"), A.Until);
			Ao->SetStringField(TEXT("set_by"), A.SetBy);
			Ao->SetNumberField(TEXT("for_s"), FMath::RoundToDouble(Now - A.Since));
			As->SetObjectField(AKV.Key, Ao);
		}
		O->SetObjectField(TEXT("modes"), As);
		TArray<TSharedPtr<FJsonValue>> Acts;
		for (int32 i = FMath::Max(0, S.Actions.Num() - 3); i < S.Actions.Num(); ++i)
		{
			Acts.Add(MakeShared<FJsonValueString>(S.Actions[i]));
		}
		O->SetArrayField(TEXT("recent"), Acts);
		Root->SetObjectField(SKV.Key, O);
	}
	return Root;
}
