#include "AstraTransportRules.h"

#include "ASTRA.h"
#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

namespace AstraXport
{
	namespace
	{
		double XNum(const TSharedPtr<FJsonObject>& O, const TCHAR* Field, double Default)
		{
			double V = Default;
			if (O.IsValid())
			{
				O->TryGetNumberField(Field, V);
			}
			return V;
		}
		const TSharedPtr<FJsonObject> XObj(const TSharedPtr<FJsonObject>& O, const TCHAR* Field)
		{
			const TSharedPtr<FJsonObject>* P = nullptr;
			return O.IsValid() && O->TryGetObjectField(Field, P) ? *P : TSharedPtr<FJsonObject>();
		}
		FVector2D XVec2(const TSharedPtr<FJsonObject>& O, const TCHAR* Field, const FVector2D& Default)
		{
			const TArray<TSharedPtr<FJsonValue>>* A = nullptr;
			return O.IsValid() && O->TryGetArrayField(Field, A) && A->Num() >= 2 ? FVector2D((*A)[0]->AsNumber(), (*A)[1]->AsNumber()) : Default;
		}
		FVector XVec3(const TSharedPtr<FJsonObject>& O, const TCHAR* Field, const FVector& Default)
		{
			const TArray<TSharedPtr<FJsonValue>>* A = nullptr;
			return O.IsValid() && O->TryGetArrayField(Field, A) && A->Num() >= 3 ? FVector((*A)[0]->AsNumber(), (*A)[1]->AsNumber(), (*A)[2]->AsNumber()) : Default;
		}
		float Sat(float X)
		{
			return FMath::Clamp(X, 0.f, 1.f);
		}
		float Smooth(float X)
		{
			X = Sat(X);
			return X * X * (3.f - 2.f * X);
		}
		FString Pct(float V)
		{
			return FString::Printf(TEXT("%.0f%%"), 100.f * V);
		}
		FString Km(float V)
		{
			return V >= 100.f ? FString::Printf(TEXT("%.0f km"), V) : (V >= 10.f ? FString::Printf(TEXT("%.1f km"), V) : FString::Printf(TEXT("%.2f km"), V));
		}
	}

	const TCHAR* AllegianceName(EAllegiance A)
	{
		switch (A)
		{
		case EAllegiance::Own: return TEXT("own");
		case EAllegiance::Allied: return TEXT("allied");
		case EAllegiance::Neutral: return TEXT("neutral");
		case EAllegiance::Hostile: return TEXT("hostile");
		default: return TEXT("derelict");
		}
	}

	const TCHAR* FaceName(int32 Face)
	{
		static const TCHAR* const N[NumFaces] = {TEXT("bow"), TEXT("stern"), TEXT("port"), TEXT("starboard"), TEXT("dorsal"), TEXT("ventral")};
		return Face >= 0 && Face < NumFaces ? N[Face] : TEXT("none");
	}

	// ============================================================================================================ the numbers
	bool FTuning::Load(const FString& OptionalPath)
	{
		FString Path = OptionalPath;
		if (Path.IsEmpty())
		{
			// staged with the game (Content/ASTRA/Data, always packaged as a loose file), else the repository's copy
			const FString Staged = FPaths::Combine(FPaths::ProjectContentDir(), TEXT("ASTRA/Data/aquila_transport.json"));
			Path = FPaths::FileExists(Staged) ? Staged : FPaths::Combine(FPaths::ProjectDir(), TEXT("data/ship/aquila_transport.json"));
		}
		FString Text;
		TSharedPtr<FJsonObject> Root;
		if (!FFileHelper::LoadFileToString(Text, *Path) || !FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Root) || !Root.IsValid())
		{
			return false;
		}
		const TSharedPtr<FJsonObject> Lim = XObj(Root, TEXT("limits"));
		MaxRangeKm = (float)XNum(Lim, TEXT("max_range_km"), MaxRangeKm);
		EmergencyRangeKm = (float)XNum(Lim, TEXT("emergency_range_km"), EmergencyRangeKm);
		Pads = (int32)XNum(Lim, TEXT("pads"), Pads);
		EmergencyPads = (int32)XNum(Lim, TEXT("emergency_pads"), EmergencyPads);
		MassKgPerPad = (float)XNum(Lim, TEXT("mass_kg_per_pad"), MassKgPerPad);
		CargoKg = (float)XNum(Lim, TEXT("cargo_kg"), CargoKg);
		CycleS = (float)XNum(Lim, TEXT("cycle_s"), CycleS);
		WarmupS = (float)XNum(Lim, TEXT("warmup_s"), WarmupS);
		DematS = (float)XNum(Lim, TEXT("dematerialize_s"), DematS);
		RematS = (float)XNum(Lim, TEXT("rematerialize_s"), RematS);
		SettleS = (float)XNum(Lim, TEXT("settle_s"), SettleS);
		CycleMW = (float)XNum(Lim, TEXT("cycle_mw"), CycleMW);
		ExtraSubjectMW = (float)XNum(Lim, TEXT("extra_subject_mw"), ExtraSubjectMW);
		BufferHoldS = (float)XNum(Lim, TEXT("buffer_hold_s"), BufferHoldS);
		HeatPerCycle = (float)XNum(Lim, TEXT("heat_pct_per_cycle"), HeatPerCycle);
		const TSharedPtr<FJsonObject> Lk = XObj(Root, TEXT("lock"));
		LockAboardS = (float)XNum(Lk, TEXT("aboard_s"), LockAboardS);
		LockShipS = (float)XNum(Lk, TEXT("ship_s"), LockShipS);
		LockHostileExtraS = (float)XNum(Lk, TEXT("hostile_extra_s"), LockHostileExtraS);
		LockSurfaceS = (float)XNum(Lk, TEXT("surface_s"), LockSurfaceS);
		LockPer1000KmS = (float)XNum(Lk, TEXT("per_1000_km_s"), LockPer1000KmS);
		LockMaxS = (float)XNum(Lk, TEXT("max_s"), LockMaxS);
		AcquireQ = (float)XNum(Lk, TEXT("acquire_quality"), AcquireQ);
		HoldQ = (float)XNum(Lk, TEXT("hold_quality"), HoldQ);
		LoseQ = (float)XNum(Lk, TEXT("lose_quality"), LoseQ);
		LoseGraceS = (float)XNum(Lk, TEXT("lose_grace_s"), LoseGraceS);
		RiseS = (float)XNum(Lk, TEXT("rise_s"), RiseS);
		FallS = (float)XNum(Lk, TEXT("fall_s"), FallS);
		ShieldOpenBelow = (float)XNum(XObj(Root, TEXT("shield")), TEXT("open_below"), ShieldOpenBelow);
		const TSharedPtr<FJsonObject> Mo = XObj(Root, TEXT("motion"));
		AccelWarn = (float)XNum(Mo, TEXT("accel_warn_mps2"), AccelWarn);
		AccelBlock = (float)XNum(Mo, TEXT("accel_block_mps2"), AccelBlock);
		TurnWarn = (float)XNum(Mo, TEXT("turn_warn_deg_s"), TurnWarn);
		TurnBlock = (float)XNum(Mo, TEXT("turn_block_deg_s"), TurnBlock);
		TargetTurnWarn = (float)XNum(Mo, TEXT("target_turn_warn_deg_s"), TargetTurnWarn);
		GateFieldKm = (float)XNum(Mo, TEXT("gate_field_km"), GateFieldKm);
		GateApproachQ = (float)XNum(Mo, TEXT("gate_approach_quality"), GateApproachQ);
		const TSharedPtr<FJsonObject> Ja = XObj(Root, TEXT("jam"));
		JamBlock = (float)XNum(Ja, TEXT("block"), JamBlock);
		JamWarn = (float)XNum(Ja, TEXT("warn"), JamWarn);
		JamSigmaDeg = (float)XNum(Ja, TEXT("sigma_deg"), JamSigmaDeg);
		JamRangeRefKm = (float)XNum(Ja, TEXT("range_ref_km"), JamRangeRefKm);
		JamOwnFloor = (float)XNum(Ja, TEXT("own_ship_floor"), JamOwnFloor);
		const TSharedPtr<FJsonObject> Gj = XObj(Root, TEXT("ground_jam"));
		static const TCHAR* const Owners[5] = {TEXT("astra"), TEXT("guilds"), TEXT("contested"), TEXT("mandate"), TEXT("silent")};
		for (int32 i = 0; i < 5; ++i)
		{
			GroundJam[i] = (float)XNum(Gj, Owners[i], GroundJam[i]);
		}
		const TSharedPtr<FJsonObject> Su = XObj(Root, TEXT("surface"));
		OrbitKm = (float)XNum(Su, TEXT("orbit_km"), OrbitKm);
		LandingOffsetM = XVec2(Su, TEXT("landing_offset_m"), LandingOffsetM);
		const TSharedPtr<FJsonObject> Hz = XObj(Root, TEXT("hazard"));
		AirMin = (float)XNum(Hz, TEXT("air_min"), AirMin);
		FireMax = (float)XNum(Hz, TEXT("fire_max"), FireMax);
		SmokeMax = (float)XNum(Hz, TEXT("smoke_max"), SmokeMax);
		HeatMax = (float)XNum(Hz, TEXT("heat_max"), HeatMax);
		const TSharedPtr<FJsonObject> Rp = XObj(Root, TEXT("room_power"));
		RoomOffline = (float)XNum(Rp, TEXT("offline"), RoomOffline);
		RoomDegraded = (float)XNum(Rp, TEXT("degraded"), RoomDegraded);
		const TSharedPtr<FJsonObject> Pw = XObj(Root, TEXT("power"));
		ShieldLoad = (float)XNum(Pw, TEXT("shield_load"), ShieldLoad);
		ShieldFloor = (float)XNum(Pw, TEXT("shield_floor"), ShieldFloor);
		AllyEngagedKm = (float)XNum(XObj(Root, TEXT("ally")), TEXT("engaged_km"), AllyEngagedKm);
		const TArray<TSharedPtr<FJsonValue>>* List = nullptr;
		InhibitKinds.Reset();
		InhibitIds.Reset();
		if (Root->TryGetArrayField(TEXT("inhibit_kinds"), List))
		{
			for (const TSharedPtr<FJsonValue>& V : *List)
			{
				InhibitKinds.Add(FName(*V->AsString()));
			}
		}
		if (Root->TryGetArrayField(TEXT("inhibit_ids"), List))
		{
			for (const TSharedPtr<FJsonValue>& V : *List)
			{
				InhibitIds.Add(FName(*V->AsString()));
			}
		}
		const TSharedPtr<FJsonObject> Fl = XObj(Root, TEXT("failure"));
		DelayP = (float)XNum(Fl, TEXT("delay_p"), DelayP);
		DelayMinS = (float)XNum(Fl, TEXT("delay_min_s"), DelayMinS);
		DelayMaxS = (float)XNum(Fl, TEXT("delay_max_s"), DelayMaxS);
		OffsetP = (float)XNum(Fl, TEXT("offset_p"), OffsetP);
		OffsetM = (float)XNum(Fl, TEXT("offset_m"), OffsetM);
		ScatterBelow = (float)XNum(Fl, TEXT("scatter_below"), ScatterBelow);
		const TSharedPtr<FJsonObject> Room = XObj(Root, TEXT("room"));
		if (Room.IsValid())
		{
			FString Kind;
			if (Room->TryGetStringField(TEXT("kind"), Kind) && !Kind.IsEmpty())
			{
				RoomKind = FName(*Kind);
			}
			const TSharedPtr<FJsonObject> Lay = XObj(Room, TEXT("layout"));
			const TSharedPtr<FJsonObject> Dais = XObj(Lay, TEXT("dais"));
			DaisCentre = XVec2(Dais, TEXT("center"), DaisCentre);
			RingM = (float)XNum(Dais, TEXT("ring_m"), RingM);
			FirstDeg = (float)XNum(Dais, TEXT("first_deg"), FirstDeg);
			PadZM = (float)XNum(Dais, TEXT("pad_z_m"), PadZM);
			PadRM = (float)XNum(Dais, TEXT("pad_r_m"), PadRM);
			Pads = (int32)XNum(Dais, TEXT("pads"), Pads);
			const TSharedPtr<FJsonObject> Cargo = XObj(Lay, TEXT("cargo"));
			CargoCentre = XVec2(Cargo, TEXT("center"), CargoCentre);
			CargoZM = (float)XNum(Cargo, TEXT("pad_z_m"), CargoZM);
			CargoRM = (float)XNum(Cargo, TEXT("pad_r_m"), CargoRM);
			EmitterM = XVec3(XObj(Lay, TEXT("emitter")), TEXT("center"), EmitterM);
			const TSharedPtr<FJsonObject> Chief = XObj(Lay, TEXT("chief"));
			ChiefStand = XVec2(Chief, TEXT("stand"), ChiefStand);
			ChiefYaw = (float)XNum(Chief, TEXT("yaw"), ChiefYaw);
			const TSharedPtr<FJsonObject> Scr = XObj(Lay, TEXT("wall_screen"));
			WallScreenM = XVec3(Scr, TEXT("center"), WallScreenM);
			WallScreenSizeM = XVec2(Scr, TEXT("size_m"), WallScreenSizeM);
			WallScreenYaw = (float)XNum(Scr, TEXT("yaw"), WallScreenYaw);
		}
		Emergency.Reset();
		if (Root->TryGetArrayField(TEXT("emergency"), List))
		{
			for (const TSharedPtr<FJsonValue>& V : *List)
			{
				const TSharedPtr<FJsonObject> O = V->AsObject();
				if (!O.IsValid())
				{
					continue;
				}
				FEmergency E;
				E.Id = FName(*O->GetStringField(TEXT("id")));
				E.Room = FName(*O->GetStringField(TEXT("room")));
				E.PosM = XVec3(O, TEXT("pos"), FVector::ZeroVector);
				E.PadRM = (float)XNum(O, TEXT("pad_r_m"), E.PadRM);
				Emergency.Add(E);
			}
		}
		return true;
	}

	FString FTuning::Describe() const
	{
		return FString::Printf(TEXT("range %.0f km (emergency pads %.0f km), %d pads + %d emergency, cycle %.1f s at %.0f MW, buffer %.0f s, lock %.1f/%.1f/%.1f s (aboard/ship/surface), "
		                            "shields open under %.0f%%, motion block %.1f m/s2 / %.1f deg/s, jam block %.0f%%"),
		                       MaxRangeKm, EmergencyRangeKm, Pads, EmergencyPads, CycleS, CycleMW, BufferHoldS, LockAboardS, LockShipS, LockSurfaceS, 100.f * ShieldOpenBelow, AccelBlock,
		                       TurnBlock, 100.f * JamBlock);
	}

	// ============================================================================================================ geometry
	int32 FaceOfLocalDir(const FVector& D, const FVector& Half)
	{
		const double Ax = FMath::Abs(D.X) / FMath::Max(1e-3, (double)Half.X);
		const double Ay = FMath::Abs(D.Y) / FMath::Max(1e-3, (double)Half.Y);
		const double Az = FMath::Abs(D.Z) / FMath::Max(1e-3, (double)Half.Z);
		if (Ax >= Ay && Ax >= Az)
		{
			return D.X >= 0.0 ? 0 : 1;                // bow, stern
		}
		if (Ay >= Az)
		{
			return D.Y >= 0.0 ? 3 : 2;                // starboard, port
		}
		return D.Z >= 0.0 ? 4 : 5;                    // dorsal, ventral
	}

	int32 FaceToward(const FQuat& Att, const FVector& Centre, const FVector& Half, const FVector& Point)
	{
		return FaceOfLocalDir(Att.UnrotateVector(Point - Centre), Half);
	}

	bool FaceOpen(const FHull& H, int32 Face, const FTuning& T)
	{
		if (!H.bPresent || H.bDisabled || !H.bShieldsUp || Face < 0 || Face >= NumFaces)
		{
			return true;
		}
		return H.Frac[Face] <= T.ShieldOpenBelow;
	}

	float JamAlong(const FEnv& Env, const FVector& To, const FString& IgnoreId, const FTuning& T)
	{
		const FVector From = Env.Own.Centre;
		const FVector U = (To - From).GetSafeNormal();
		float Keep = 1.f;
		for (const FHull& J : Env.Others)
		{
			if (!J.bPresent || !J.bJamming || J.Side == EAllegiance::Own || J.Side == EAllegiance::Allied || J.Id == IgnoreId)
			{
				continue;
			}
			const FVector V = J.Centre - From;
			const double RangeKm = V.Size() / 1000.0;
			if (RangeKm < 1e-3)
			{
				continue;
			}
			const double Cos = FMath::Clamp(FVector::DotProduct(U, V / V.Size()), -1.0, 1.0);
			const double AngDeg = FMath::RadiansToDegrees(FMath::Acos(Cos));
			// the strobe floods the line along its own bearing: a bell round it, weaker the farther the jammer is
			float S = (float)(FMath::Exp(-0.5 * FMath::Square(AngDeg / FMath::Max(1.f, T.JamSigmaDeg))) / (1.0 + FMath::Square(RangeKm / FMath::Max(1.f, T.JamRangeRefKm))));
			// a lock on the jammer itself burns through when it is close: inside 12 km the strobe thins to nothing at 2 km
			if (FVector::Dist(J.Centre, To) < FMath::Max(300.0, (double)J.RadiusM * 1.5))
			{
				S *= Smooth((float)((RangeKm - 2.0) / 10.0));
			}
			Keep *= 1.f - Sat(S);
		}
		return 1.f - Keep;
	}

	// ============================================================================================================ the room, the reach, the cycle
	float ReachKm(const FTuning& T, const FEnv& Env, bool bEmergency)
	{
		const FRoomState& R = bEmergency ? Env.Emergency : Env.Main;
		const float Base = bEmergency ? T.EmergencyRangeKm : T.MaxRangeKm;
		const float FRoom = FMath::Sqrt(Sat(R.Power));
		const float FSens = FMath::Sqrt(FMath::Clamp(Env.SensorsPower, 0.4f, 1.25f));
		return Base * FMath::Min(1.f, FRoom * FSens);
	}

	float CycleSeconds(const FTuning& T, const FRoomState& Room)
	{
		return T.CycleS * (1.f + 0.6f * (1.f - FMath::Clamp(Room.Power, 0.4f, 1.f)));
	}

	float EnergyFor(const FTuning& T, int32 N)
	{
		return T.CycleMW + T.ExtraSubjectMW * (float)FMath::Max(0, N - 1);
	}

	float LockSeconds(const FTuning& T, const FEnv& Env, const FRequest& Req, float RangeKm, float Jam)
	{
		const bool bEmergency = Req.From.bEmergencyPad || Req.To.bEmergencyPad;
		const FRoomState& R = bEmergency ? Env.Emergency : Env.Main;
		float Base = T.LockAboardS;
		const bool bSurface = Req.From.Kind == EEndKind::Surface || Req.To.Kind == EEndKind::Surface;
		const bool bShip = Req.From.Kind == EEndKind::Ship || Req.To.Kind == EEndKind::Ship;
		if (bSurface)
		{
			Base = T.LockSurfaceS;
		}
		else if (bShip)
		{
			Base = T.LockShipS;
			const FHull& S = Req.To.Kind == EEndKind::Ship ? Req.To.Ship : Req.From.Ship;
			if (S.Side == EAllegiance::Hostile)
			{
				Base += T.LockHostileExtraS;
			}
		}
		Base += T.LockPer1000KmS * RangeKm / 1000.f;
		const float RoomRate = FMath::Clamp(0.4f + 0.6f * R.Power, 0.4f, 1.f);
		const float SensRate = FMath::Clamp(0.6f + 0.4f * Env.SensorsPower, 0.6f, 1.2f);
		const float Rate = RoomRate * SensRate * FMath::Max(0.3f, 1.f - 0.7f * Jam);
		return FMath::Min(T.LockMaxS, Base / FMath::Max(0.2f, Rate));
	}

	// ============================================================================================================ the lock's quality
	float LockTarget(const FTuning& T, const FEnv& Env, const FRequest& Req, const FVerdict& V, TArray<FString>* Notes)
	{
		float Q = 1.f;
		auto Cost = [&](float F, const FString& What)
		{
			Q *= F;
			if (Notes && F < 0.95f)
			{
				Notes->Add(FString::Printf(TEXT("%s costs %s"), *What, *Pct(1.f - F)));
			}
		};
		const bool bEmergency = V.bEmergencySystem;
		const FRoomState& R = bEmergency ? Env.Emergency : Env.Main;
		const bool bExternal = !Req.From.Aboard() || !Req.To.Aboard();
		if (bExternal)
		{
			const float Reach = FMath::Max(1.f, V.MaxRangeKm);
			Cost(1.f - 0.45f * FMath::Square(Sat(V.RangeKm / Reach)), FString::Printf(TEXT("the range (%s of %s)"), *Km(V.RangeKm), *Km(Reach)));
			Cost(1.f - Sat(V.Jam), FString::Printf(TEXT("the jamming (%s)"), *Pct(V.Jam)));
			const float A = Env.AccelMps2, W = Env.TurnDegS;
			const float Qa = 1.f - 0.9f * Sat((A - T.AccelWarn) / FMath::Max(0.1f, T.AccelBlock - T.AccelWarn));
			const float Qw = 1.f - 0.9f * Sat((W - T.TurnWarn) / FMath::Max(0.1f, T.TurnBlock - T.TurnWarn));
			Cost(FMath::Max(0.05f, Qa * Qw), FString::Printf(TEXT("the Aquila's manoeuvring (%.1f m/s2, %.1f deg/s)"), A, W));
			const FHull& S = Req.To.Kind == EEndKind::Ship ? Req.To.Ship : (Req.From.Kind == EEndKind::Ship ? Req.From.Ship : FHull());
			if (S.bPresent)
			{
				Cost(1.f - 0.3f * Sat((S.TurnDegS - T.TargetTurnWarn) / FMath::Max(0.1f, 3.f * T.TargetTurnWarn)), FString::Printf(TEXT("%s manoeuvring (%.1f deg/s)"), *S.Name, S.TurnDegS));
			}
			if (Env.GateKm >= 0.f && Env.GateKm < T.GateFieldKm + 35.f)
			{
				Cost(FMath::Lerp(T.GateApproachQ * 0.8f, 1.f, Sat((Env.GateKm - T.GateFieldKm) / 35.f)), FString::Printf(TEXT("the Janus Gate's field (%s off)"), *Km(Env.GateKm)));
			}
			// the long-range lock rides on the sensor net and the ship's thermal margin; a transport inside the hull uses the pads' own sensors
			Cost(0.7f + 0.3f * Sat(Env.SensorsPower), FString::Printf(TEXT("the sensors' power (%s)"), *Pct(Env.SensorsPower)));
			Cost(0.8f + 0.2f * Sat(Env.HeatFactor), TEXT("the heat"));
		}
		Cost(0.55f + 0.45f * Sat(R.Power), FString::Printf(TEXT("the room's power (%s)"), *Pct(R.Power)));
		return Sat(Q);
	}

	void FLock::Tick(const FTuning& T, float Dt, float Target, float Rate)
	{
		if (State == EState::Lost)
		{
			return;
		}
		// the quality eases to its target: slowly up, quickly down
		const float K = Target > Quality ? 1.f - FMath::Exp(-Dt / FMath::Max(0.05f, T.RiseS)) : 1.f - FMath::Exp(-Dt / FMath::Max(0.05f, T.FallS));
		Quality += (Target - Quality) * K;
		if (State == EState::Acquiring)
		{
			if (Target >= T.LoseQ)
			{
				Progress = FMath::Min(1.f, Progress + Dt / NeedS * FMath::Max(0.f, Rate));
			}
			LowT = Quality < T.LoseQ && Progress > 0.f ? LowT + Dt : 0.f;
			if (Progress >= 1.f && Quality >= T.AcquireQ)
			{
				State = EState::Locked;
				LowT = 0.f;
			}
			return;
		}
		// a lock in hand: it degrades under the hold quality and is lost when the quality stays under the lose quality
		if (Quality < T.LoseQ)
		{
			LowT += Dt;
			if (LowT >= T.LoseGraceS)
			{
				State = EState::Lost;
				return;
			}
		}
		else
		{
			LowT = 0.f;
		}
		if (State == EState::Degraded)
		{
			State = Quality >= T.HoldQ + 0.05f ? EState::Locked : EState::Degraded;       // a little hysteresis: it must be clearly back
		}
		else
		{
			State = Quality < T.HoldQ ? EState::Degraded : EState::Locked;
		}
	}

	const TCHAR* FLock::Name(EState S)
	{
		switch (S)
		{
		case EState::Acquiring: return TEXT("acquiring");
		case EState::Locked: return TEXT("locked");
		case EState::Degraded: return TEXT("degraded");
		default: return TEXT("lost");
		}
	}

	FArrival RollArrival(const FTuning& T, float MinQuality, bool bForced, FRandomStream& Rng)
	{
		const float Q = Sat(MinQuality);
		FArrival A;
		// a pattern is scattered only when a lock this poor was forced through on the Captain's word: nothing else in the rules kills
		if (bForced && Q < T.ScatterBelow)
		{
			const float P = Sat((T.ScatterBelow - Q) / FMath::Max(0.01f, T.ScatterBelow)) * 0.5f;
			if (Rng.FRand() < P)
			{
				A.Kind = EArrival::Scattered;
				return A;
			}
		}
		if (Rng.FRand() < T.DelayP * (1.f - Q))
		{
			A.Kind = EArrival::Delayed;
			A.DelayS = Rng.FRandRange(T.DelayMinS, T.DelayMaxS);
			return A;
		}
		if (Rng.FRand() < T.OffsetP * (1.f - Q))
		{
			A.Kind = EArrival::Offset;
			A.OffsetM = Rng.FRandRange(1.5f, FMath::Max(2.f, T.OffsetM));
		}
		return A;
	}

	// ============================================================================================================ the verdict
	bool FVerdict::HasBlocker(const TCHAR* Code) const
	{
		for (const FBlocker& B : Blockers)
		{
			if (B.Code == FName(Code))
			{
				return true;
			}
		}
		return false;
	}

	FString FVerdict::Summary() const
	{
		FString Out;
		for (const FBlocker& B : Blockers)
		{
			Out += (Out.IsEmpty() ? TEXT("") : TEXT("; ")) + B.Why;
		}
		return Out;
	}

	namespace
	{
		bool IsHazard(const FRoomState& R, const FTuning& T, FString* OutWhy)
		{
			FString Why;
			if (R.bGutted || R.Wreck >= 0.9f)
			{
				Why = TEXT("it is gutted");
			}
			else if (R.Air < T.AirMin)
			{
				Why = FString::Printf(TEXT("its air is at %s (%s is the least a person lives in)"), *Pct(R.Air), *Pct(T.AirMin));
			}
			else if (R.Fire > T.FireMax)
			{
				Why = FString::Printf(TEXT("it is on fire (%s)"), *Pct(R.Fire));
			}
			else if (R.Smoke > T.SmokeMax)
			{
				Why = FString::Printf(TEXT("it is full of smoke (%s)"), *Pct(R.Smoke));
			}
			else if (R.Heat > T.HeatMax)
			{
				Why = FString::Printf(TEXT("it is too hot (%s)"), *Pct(R.Heat));
			}
			if (OutWhy)
			{
				*OutWhy = Why;
			}
			return !Why.IsEmpty();
		}
	}

	FVerdict Evaluate(const FTuning& T, const FEnv& Env, const FRequest& Req)
	{
		FVerdict V;
		auto Block = [&V](const TCHAR* Code, const FString& Why, const FString& Fix, bool bHard, bool bOverridable)
		{
			FBlocker B;
			B.Code = FName(Code);
			B.Why = Why;
			B.Fix = Fix;
			B.bHard = bHard;
			B.bOverridable = bOverridable;
			V.Blockers.Add(B);
		};
		const bool bEmergency = Req.From.bEmergencyPad || Req.To.bEmergencyPad;
		V.bEmergencySystem = bEmergency;
		const FRoomState& Room = bEmergency ? Env.Emergency : Env.Main;
		const FString RoomName = bEmergency ? TEXT("the Medbay's emergency pads") : TEXT("the Transporter Room");
		const bool bExternal = !Req.From.Aboard() || !Req.To.Aboard();
		V.CycleS = CycleSeconds(T, Room);
		V.EnergyMW = EnergyFor(T, Req.Subjects.Num());

		// ---- the room and the power behind it
		FString HazardWhy;
		if (!Room.bExists || Room.bGutted || Room.Wreck >= 0.9f)
		{
			Block(TEXT("room"), FString::Printf(TEXT("%s are wrecked"), *RoomName), TEXT("a repair team on that room; the emergency pads in the Medbay reach 400 km"), true, false);
		}
		else if (Room.Power < T.RoomOffline)
		{
			Block(TEXT("room"), FString::Printf(TEXT("%s have no power (%s)"), *RoomName, *Pct(Room.Power)), TEXT("power back to the room (damage control), or the Medbay's emergency pads"), true, false);
		}
		else if (IsHazard(Room, T, &HazardWhy))
		{
			Block(TEXT("room"), FString::Printf(TEXT("the operators cannot work in %s: %s"), *RoomName, *HazardWhy), TEXT("put the incident out first"), true, false);
		}
		else if (Room.Power < T.RoomDegraded)
		{
			V.Notes.Add(FString::Printf(TEXT("%s are on reduced power (%s): a slower lock, a shorter reach, a longer cycle"), *RoomName, *Pct(Room.Power)));
		}
		if (!Env.bReactorOn)
		{
			Block(TEXT("power"), TEXT("the reactor is down: nothing to carry a beam"), TEXT("bring the reactor back"), true, false);
		}

		// ---- who and what
		const int32 N = Req.Subjects.Num();
		const int32 Cap = bEmergency ? T.EmergencyPads : T.Pads;
		if (N <= 0)
		{
			Block(TEXT("subject"), TEXT("nobody and nothing is named for the beam"), TEXT("say who or what"), true, false);
		}
		if (N > Cap)
		{
			Block(TEXT("pads"), FString::Printf(TEXT("%d subjects, and %s have %d pads: they go in turns"), N, *RoomName, Cap), TEXT("send them in parties of six"), false, false);
		}
		for (const FSubject& S : Req.Subjects)
		{
			if (S.bDead)
			{
				Block(TEXT("subject"), FString::Printf(TEXT("%s is dead"), *S.Label), TEXT(""), true, false);
			}
			else if (!S.Barred.IsEmpty())
			{
				Block(TEXT("subject"), S.Barred, TEXT("someone else, or the post relieved first"), true, false);
			}
			else if (!S.bFound)
			{
				Block(TEXT("subject"), FString::Printf(TEXT("no pattern to lock on %s: not where the file says, or no signal"), *S.Label), TEXT("ask the locator for where they are"), true, false);
			}
			else if (S.bInPattern)
			{
				Block(TEXT("subject"), FString::Printf(TEXT("%s is already in a transport"), *S.Label), TEXT("wait for that one"), true, false);
			}
			if (S.MassKg > T.MassKgPerPad)
			{
				Block(TEXT("mass"), FString::Printf(TEXT("%s is %.0f kg: a pad carries %.0f kg"), *S.Label, S.MassKg, T.MassKgPerPad), TEXT("split the load"), true, false);
			}
		}

		// ---- the two ends
		auto CheckAboard = [&](const FEnd& E, bool bDestination)
		{
			if (!E.Aboard())
			{
				return;
			}
			if (E.bInhibited)
			{
				Block(TEXT("inhibit"), FString::Printf(TEXT("%s is pattern-shielded: no beam goes into or out of it"), *E.Label),
				      E.OpenNear.IsEmpty() ? FString(TEXT("use the nearest room that is not shielded")) : FString::Printf(TEXT("the nearest room the beam reaches is %s"), *E.OpenNear), true, false);
			}
			if (bDestination)
			{
				FString Why;
				if (IsHazard(E.Room, T, &Why))
				{
					Block(TEXT("hazard"), FString::Printf(TEXT("%s is no place to arrive: %s"), *E.Label, *Why),
					      TEXT("put the incident out, or the Captain's word to land them there anyway"), false, !E.Room.bGutted);
				}
				if (E.bPad && E.bPadOccupied)
				{
					Block(TEXT("occupied"), FString::Printf(TEXT("%s is occupied: a pattern cannot be set down on someone"), *E.Label), TEXT("another pad"), false, false);
				}
			}
		};
		CheckAboard(Req.From, false);
		CheckAboard(Req.To, true);

		// ---- the beam's geometry, only when it leaves the hull
		if (bExternal)
		{
			const FEnd& Far = Req.To.Aboard() ? Req.From : Req.To;
			FVector FarPoint = Env.Own.Centre;
			if (Far.Kind == EEndKind::Ship && !Far.Ship.bPresent)
			{
				Block(TEXT("target"), FString::Printf(TEXT("%s is not on the plot any more: nothing to lock on"), *Far.Label), TEXT("another place"), true, false);
			}
			if (Far.Kind == EEndKind::Ship && Far.Ship.bPresent)
			{
				FarPoint = Far.Ship.Centre;
				V.RangeKm = (float)(FVector::Dist(Far.Ship.Centre, Env.Own.Centre) / 1000.0);
				V.OwnFace = FaceToward(Env.Own.Att, Env.Own.Centre, Env.Own.Half, Far.Ship.Centre);
				V.TheirFace = FaceToward(Far.Ship.Att, Far.Ship.Centre, Far.Ship.Half, Env.Own.Centre);
			}
			else if (Far.Kind == EEndKind::Surface)
			{
				V.RangeKm = T.OrbitKm;
				V.OwnFace = FaceOfLocalDir(Far.DirBody, Env.Own.Half);
				FarPoint = Env.Own.Centre + Env.Own.Att.RotateVector(Far.DirBody) * (double)T.OrbitKm * 1000.0;
			}
			V.MaxRangeKm = ReachKm(T, Env, bEmergency);
			if (V.RangeKm > V.MaxRangeKm)
			{
				Block(TEXT("range"), FString::Printf(TEXT("%s is %s away and %s reach %s"), *Far.Label, *Km(V.RangeKm), *RoomName, *Km(V.MaxRangeKm)),
				      Room.Power < 0.95f || Env.SensorsPower < 0.95f ? TEXT("more power to the room and the sensors, or close the range") : TEXT("close the range"), true, false);
			}

			// our own shield, on the face the beam leaves through
			V.bOwnOpen = FaceOpen(Env.Own, V.OwnFace, T);
			if (!V.bOwnOpen)
			{
				if (Req.bShieldWindow)
				{
					V.bNeedsOwnWindow = true;
					V.Notes.Add(FString::Printf(TEXT("our shields come down for the cycle (the %s face holds %s)"), FaceName(V.OwnFace), *Pct(Env.Own.Frac[FMath::Clamp(V.OwnFace, 0, NumFaces - 1)])));
				}
				else
				{
					Block(TEXT("shields_own"), FString::Printf(TEXT("our shields are up on the %s face, the one the beam leaves through (%s)"), FaceName(V.OwnFace),
					                                         *Pct(Env.Own.Frac[FMath::Clamp(V.OwnFace, 0, NumFaces - 1)])),
					      TEXT("Tactical lowers the shields for the cycle (a shield window), or the sector is shot down"), false, false);
				}
			}

			// theirs
			if (Far.Kind == EEndKind::Ship && Far.Ship.bPresent)
			{
				const FHull& S = Far.Ship;
				V.bTheirsOpen = FaceOpen(S, V.TheirFace, T);
				if (S.Side == EAllegiance::Allied && !V.bTheirsOpen)
				{
					if (S.bEngaged)
					{
						Block(TEXT("shields_theirs"), FString::Printf(TEXT("%s is in a fight: her captain cannot open her %s face to us now"), *S.Name, FaceName(V.TheirFace)),
						      TEXT("when she is out of the fight, or hold the transport"), false, false);
					}
					else
					{
						V.bTheirsOpen = true;
						V.Notes.Add(FString::Printf(TEXT("%s opens her %s face for the cycle at her captain's word"), *S.Name, FaceName(V.TheirFace)));
					}
				}
				else if (!V.bTheirsOpen)
				{
					if (!S.bFacesKnown)
					{
						V.Unknown.Add(FString::Printf(TEXT("%s: no firm track, so the state of her %s face is not known"), *S.Name, FaceName(V.TheirFace)));
					}
					else
					{
						Block(TEXT("shields_theirs"), FString::Printf(TEXT("%s's %s shield sector holds %s: the beam cannot pass it"), *S.Name, FaceName(V.TheirFace),
						                                            *Pct(S.Frac[FMath::Clamp(V.TheirFace, 0, NumFaces - 1)])),
						      S.Side == EAllegiance::Hostile ? TEXT("shoot that sector down below 5%, or disable her") : TEXT("her captain must lower it"), true, false);
					}
				}
			}

			// jamming along the line (the ground's, for a world held by an enemy)
			V.Jam = JamAlong(Env, FarPoint, FString(), T);       // (a jamming target's own strobe counts: it burns through when it is close)
			if (Far.Kind == EEndKind::Surface)
			{
				V.Jam = 1.f - (1.f - V.Jam) * (1.f - Sat(T.GroundJam[FMath::Clamp((int32)Far.Owner, 0, 4)]));
			}
			if (V.Jam >= T.JamBlock)
			{
				Block(TEXT("jam"), FString::Printf(TEXT("heavy electronic jamming along the beam (%s): no lock builds through it"), *Pct(V.Jam)),
				      Far.Kind == EEndKind::Surface ? TEXT("the ground's jammers cannot be outrun: a beacon on the ground, or another approach") : TEXT("turn the Aquila so that the line misses the strobe, close inside the burn-through range or silence the jammer"),
				      true, false);
			}
			else if (V.Jam >= T.JamWarn)
			{
				V.Notes.Add(FString::Printf(TEXT("jamming along the beam (%s) slows and weakens the lock"), *Pct(V.Jam)));
			}

			// the Aquila's own motion
			if (Env.AccelMps2 >= T.AccelBlock || Env.TurnDegS >= T.TurnBlock)
			{
				Block(TEXT("motion"), FString::Printf(TEXT("the Aquila is manoeuvring too hard for the aim to hold (%.1f m/s2, %.1f deg/s; the limits are %.0f and %.1f)"), Env.AccelMps2, Env.TurnDegS, T.AccelBlock, T.TurnBlock),
				      TEXT("the helm eases the ship: all stop, or a steady course"), false, false);
			}
			else if (Env.AccelMps2 >= T.AccelWarn || Env.TurnDegS >= T.TurnWarn)
			{
				V.Notes.Add(FString::Printf(TEXT("the Aquila's manoeuvring (%.1f m/s2, %.1f deg/s) costs the lock"), Env.AccelMps2, Env.TurnDegS));
			}

			// the field of a Janus Gate
			if (Env.bGateLane || (Env.GateKm >= 0.f && Env.GateKm < T.GateFieldKm))
			{
				Block(TEXT("gate"), TEXT("the Aquila is inside the Janus Gate's field: no beam crosses it"), TEXT("leave the lane, or wait for the transit to finish"), true, false);
			}
		}

		// ---- what the lock can be
		V.Quality = LockTarget(T, Env, Req, V, &V.Notes);
		V.LockS = LockSeconds(T, Env, Req, V.RangeKm, V.Jam);
		if (V.Quality < T.AcquireQ && !V.HasBlocker(TEXT("jam")) && !V.HasBlocker(TEXT("range")) && !V.HasBlocker(TEXT("motion")) && !V.HasBlocker(TEXT("gate")) && !V.HasBlocker(TEXT("room")) && !V.HasBlocker(TEXT("target")))
		{
			Block(TEXT("quality"), FString::Printf(TEXT("the lock would top out at %s and a beam needs %s"), *Pct(V.Quality), *Pct(T.AcquireQ)), TEXT("remove what costs the lock: see the notes"), false, true);
		}

		// ---- the Captain's word
		if (Req.bOverrideHazard)
		{
			V.Blockers.RemoveAll([&V](const FBlocker& B)
			{
				if (B.Code == FName(TEXT("hazard")) && B.bOverridable)
				{
					V.Notes.Add(TEXT("the Captain's word: the destination's hazard is accepted"));
					return true;
				}
				return false;
			});
		}
		if (Req.bForce)
		{
			V.Blockers.RemoveAll([&V](const FBlocker& B)
			{
				if (B.Code == FName(TEXT("quality")))
				{
					V.Notes.Add(TEXT("the Captain's word: the weak lock is accepted, at the pattern's risk"));
					return true;
				}
				return false;
			});
		}
		V.bOk = V.Blockers.Num() == 0;
		return V;
	}
}
