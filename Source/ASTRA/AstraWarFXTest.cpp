// ASTRA — trying the war's visual effects (astra.fx.*): a scene in front of the bridge, and commands that fire every weapon, hit a shield, burn a hull,
// break a ship. They drive the real battle (the same functions the war calls), so what they show is what the war will show.
//
//   astra.fx.scene [range_km 6] [bearing 0]        a Mandate cruiser broadside at that range and bearing off the bow, an ASTRA battleship and a Mandate
//                                                   destroyer to either side of it, all held where they are with their guns silent
//   astra.fx.fire <rail|laser|missile|torpedo|pd|cannon|all> [n 1] [from S|A|T|aquila] [at T|A|S|aquila]
//   astra.fx.shield [bow|stern|port|starboard|dorsal|ventral] [n 4] [on T|A|S|aquila]   hits on one face's shield; enough of them and it falls
//   astra.fx.hit <rail|laser|missile|torpedo|cannon> [damage 40] [facing bow] [on T]    one blow that gets through the shield
//   astra.fx.burn [on T]                            fires and venting in every section, one gutted
//   astra.fx.break <bow|mid|stern|reactor|disable> [on T]   the ship's end, the way the war ends ships
//   astra.fx.clear                                  the scene's ships go (no explosion)
//   astra.fx.swatch [seconds 40]                    a lineup of every kind of effect 1.2 km ahead of the bridge, in both sides' colours: the material check
//                                                   (needs no ships; if one of these looks wrong, the material is what is wrong, not the war)
//   astra.fx.stats                                  what the effects hold and what they cost

#include "AstraWarFX.h"
#include "AstraBattleSubsystem.h"
#include "ASTRA.h"
#include "Engine/StaticMeshActor.h"

struct FAstraWarFXTest
{
	struct FPending { float T; FString Line; };
	static TArray<FString> Queue;
	static TArray<FPending> Pending;
	static TArray<int32> SceneIds;
	static float SwatchT;                  // seconds the lineup has left (0: none)
	static float SwatchRespawn;            // until the particles that live and die are thrown again

	static FVector Polar(double RangeM, double BearingDeg, double MarkDeg)
	{
		const double B = FMath::DegreesToRadians(BearingDeg), M = FMath::DegreesToRadians(MarkDeg);
		return FVector(RangeM * FMath::Cos(M) * FMath::Cos(B), RangeM * FMath::Cos(M) * FMath::Sin(B), RangeM * FMath::Sin(M));
	}

	static FAstraBattleShip* Pick(UAstraWarFX& Fx, const FString& Key)
	{
		UAstraBattleSubsystem* B = Fx.Owner;
		const FString K = Key.ToLower();
		if (K == TEXT("aquila") || K == TEXT("q"))
		{
			return &B->Ships[0];
		}
		if (K == TEXT("a"))
		{
			return B->FindByContact(TEXT("FX-A"));
		}
		if (K == TEXT("s"))
		{
			return B->FindByContact(TEXT("FX-S"));
		}
		if (K == TEXT("t") || K.IsEmpty())
		{
			return B->FindByContact(TEXT("FX-T"));
		}
		return B->FindByContact(Key.ToUpper());
	}

	static void Hold(FAstraBattleShip& S)
	{
		S.bHoldStation = S.bFixedAtt = S.bHoldFire = true;     // where it is, as it is, guns silent
		S.Mode = EAstraShipMode::Idle;
		S.Vel = FVector::ZeroVector;
		S.bFog = false;
		S.bIdentified = true;
		S.bClassified = true;
		S.Track = 2;
	}

	static void Clear(UAstraWarFX& Fx)
	{
		UAstraBattleSubsystem* B = Fx.Owner;
		for (const int32 Id : SceneIds)
		{
			if (FAstraBattleShip* S = B->FindById(Id))
			{
				S->bAlive = false;
				S->Mode = EAstraShipMode::Dead;
				if (S->Actor) { S->Actor->Destroy(); S->Actor = nullptr; }
				if (S->ShieldBubble) { S->ShieldBubble->Destroy(); S->ShieldBubble = nullptr; }
				if (S->DriveFlare) { S->DriveFlare->Destroy(); S->DriveFlare = nullptr; }
				if (const AstraFx::FShipFx* F = Fx.ShipFx.Find(Id))
				{
					if (AStaticMeshActor* A = F->Shield.Actor.Get())
					{
						A->Destroy();
					}
					Fx.ShipFx.Remove(Id);
				}
			}
		}
		SceneIds.Reset();
	}

	static void Scene(UAstraWarFX& Fx, float RangeKm, float Bearing)
	{
		UAstraBattleSubsystem* B = Fx.Owner;
		Clear(Fx);
		const FRotator Bow = B->Ships[0].Att.Rotator();
		const auto Place = [&](double Km, double Brg, double Mark) { return B->Ships[0].Pos + Polar(Km * 1000.0, Bow.Yaw + Brg, Bow.Pitch + Mark); };
		struct FSpec { const TCHAR* Key; EAstraSide Side; const TCHAR* Contact; const TCHAR* Name; double Km, Brg, Mark; float Heading; };
		const FSpec Specs[3] = {
			{TEXT("acheron"), EAstraSide::Mandate, TEXT("FX-T"), TEXT("Target Acheron"), RangeKm, Bearing, 2.0, (float)(Bow.Yaw + Bearing + 90.0)},
			{TEXT("praetorian"), EAstraSide::Astra, TEXT("FX-A"), TEXT("Friend Praetorian"), RangeKm * 0.6, Bearing + 38.0, -2.0, (float)(Bow.Yaw + Bearing + 38.0 - 90.0)},
			{TEXT("styx"), EAstraSide::Mandate, TEXT("FX-S"), TEXT("Shooter Styx"), RangeKm + 2.0, Bearing - 34.0, 3.0, (float)(Bow.Yaw + Bearing - 34.0 + 90.0)}};
		for (const FSpec& Sp : Specs)
		{
			const int32 I = B->SpawnByKey(FName(Sp.Key), Sp.Side, Sp.Contact, Sp.Name, Place(Sp.Km, Sp.Brg, Sp.Mark), Sp.Heading);
			if (I == INDEX_NONE)
			{
				UE_LOG(LogASTRA, Warning, TEXT("[WarFX] test scene: no class %s"), Sp.Key);
				continue;
			}
			Hold(B->Ships[I]);
			SceneIds.Add(B->Ships[I].Id);
		}
		UE_LOG(LogASTRA, Display, TEXT("[WarFX] test scene: Target Acheron (FX-T) %.1f km at %+.0f deg, Friend Praetorian (FX-A), Shooter Styx (FX-S); astra.fx.fire / shield / hit / burn / break"), RangeKm, Bearing);
	}

	static int32 FacingOf(const FString& N)
	{
		const FString K = N.ToLower();
		if (K.StartsWith(TEXT("ste")) || K.StartsWith(TEXT("a"))) { return AstraWar::Stern; }          // stern, aft
		if (K.StartsWith(TEXT("p"))) { return AstraWar::Port; }
		if (K.StartsWith(TEXT("st"))) { return AstraWar::Starboard; }                                 // starboard
		if (K.StartsWith(TEXT("d")) || K.StartsWith(TEXT("t"))) { return AstraWar::Dorsal; }          // dorsal, top
		if (K.StartsWith(TEXT("v")) || K.StartsWith(TEXT("k"))) { return AstraWar::Ventral; }         // ventral, keel
		return AstraWar::Bow;
	}

	/** A blow on one face of a ship, coming in from outside along the face's normal (system frame position on the hull box). */
	static void Strike(UAstraWarFX& Fx, FAstraBattleShip& To, int32 Facing, float Damage, EAstraHitKind Kind, int32 FromId)
	{
		UAstraBattleSubsystem* B = Fx.Owner;
		FVector Lp = AstraWar::FacingVector(Facing);
		if (To.Box.Valid())
		{
			const FVector H(To.Box.Hx, To.Box.Hy, To.Box.Hz);
			Lp = FVector(Lp.X * H.X, Lp.Y * H.Y, Lp.Z * H.Z);
			// a point on that face, off its centre
			const FVector J(FMath::FRandRange(-0.6f, 0.6f), FMath::FRandRange(-0.6f, 0.6f), FMath::FRandRange(-0.6f, 0.6f));
			if (FMath::Abs(Lp.X) > 0.f) { Lp.Y = J.Y * H.Y; Lp.Z = J.Z * H.Z; }
			else if (FMath::Abs(Lp.Y) > 0.f) { Lp.X = J.X * H.X; Lp.Z = J.Z * H.Z; }
			else { Lp.X = J.X * H.X; Lp.Y = J.Y * H.Y; }
			Lp.X += To.Box.Mid;
		}
		else
		{
			Lp *= To.Radius;
		}
		const FVector Pos = To.Pos + To.Att.RotateVector(Lp);
		const FVector Dir = -To.Att.RotateVector(AstraWar::FacingVector(Facing));
		B->ApplyHit(To, Dir, Damage, Pos, Kind, FromId);
	}

	static EAstraHitKind KindOf(const FString& N)
	{
		const FString K = N.ToLower();
		if (K.StartsWith(TEXT("l"))) { return EAstraHitKind::Laser; }
		if (K.StartsWith(TEXT("m"))) { return EAstraHitKind::Missile; }
		if (K.StartsWith(TEXT("t"))) { return EAstraHitKind::Torpedo; }
		if (K.StartsWith(TEXT("c"))) { return EAstraHitKind::Cannon; }
		return EAstraHitKind::Rail;
	}

	static void Fire(UAstraWarFX& Fx, const FString& What, int32 N, FAstraBattleShip& From, FAstraBattleShip& To)
	{
		UAstraBattleSubsystem* B = Fx.Owner;
		const FString W = What.ToLower();
		for (int32 n = 0; n < N; ++n)
		{
			if (W.StartsWith(TEXT("r")))
			{
				for (int32 i = 0; i < FMath::Max(From.RailSlugs, 2); ++i) { B->FireRail(From, To, 0.0008f); }
			}
			else if (W.StartsWith(TEXT("l")))
			{
				for (int32 i = 0; i < 4; ++i) { B->FireLaser(From, To); }
			}
			else if (W.StartsWith(TEXT("m")) || W.StartsWith(TEXT("p")))
			{
				for (int32 i = 0; i < 6; ++i) { B->FireMissile(From, To); }
			}
			else if (W.StartsWith(TEXT("t")))
			{
				for (int32 i = 0; i < 2; ++i) { B->FireTorpedo(From, To); }
			}
			else if (W.StartsWith(TEXT("c")))
			{
				for (int32 i = 0; i < 12; ++i)
				{
					const FVector Dir = (To.Pos - From.Pos).GetSafeNormal();
					B->AddBeam(From.Pos, From.Pos + Dir * 900.0, 0.06f, FLinearColor::White, EAstraFxShot::Cannon, From.Id);
				}
			}
		}
	}

	static void Run(UAstraWarFX& Fx, const FString& Name, const TArray<FString>& A)
	{
		UAstraBattleSubsystem* B = Fx.Owner;
		const auto Arg = [&A](int32 I, const TCHAR* Def) { return A.IsValidIndex(I) ? A[I] : FString(Def); };
		if (Name == TEXT("scene"))
		{
			Scene(Fx, FCString::Atof(*Arg(0, TEXT("6"))), FCString::Atof(*Arg(1, TEXT("0"))));
		}
		else if (Name == TEXT("clear"))
		{
			Clear(Fx);
		}
		else if (Name == TEXT("stats"))
		{
			FString S;
			Fx.Stats(S);
			UE_LOG(LogASTRA, Display, TEXT("[WarFX] %s"), *S);
		}
		else if (Name == TEXT("fire"))
		{
			const FString What = Arg(0, TEXT("all"));
			const int32 N = FMath::Clamp(FCString::Atoi(*Arg(1, TEXT("1"))), 1, 12);
			FAstraBattleShip* Src = Pick(Fx, Arg(2, TEXT("S")));
			FAstraBattleShip* Dst = Pick(Fx, Arg(3, What.StartsWith(TEXT("p")) ? TEXT("A") : TEXT("T")));
			if (!Src || !Dst)
			{
				UE_LOG(LogASTRA, Warning, TEXT("[WarFX] no scene: astra.fx.scene first"));
				return;
			}
			if (What.StartsWith(TEXT("a")))
			{
				// one of each, a moment apart
				const TCHAR* Seq[6] = {TEXT("rail"), TEXT("laser"), TEXT("cannon"), TEXT("missile"), TEXT("torpedo"), TEXT("pd")};
				for (int32 i = 0; i < 6; ++i)
				{
					Pending.Add({1.2f * i, FString::Printf(TEXT("fire %s %d %s %s"), Seq[i], N, *Arg(2, TEXT("S")), *Arg(3, TEXT("T")))});
				}
				return;
			}
			FAstraBattleShip& From = *Src;
			FAstraBattleShip& To = *Dst;
			Fire(Fx, What, N, From, To);
		}
		else if (Name == TEXT("shield") || Name == TEXT("hit"))
		{
			const bool bShield = Name == TEXT("shield");
			FAstraBattleShip* To = Pick(Fx, Arg(bShield ? 2 : 3, TEXT("T")));
			if (!To)
			{
				UE_LOG(LogASTRA, Warning, TEXT("[WarFX] no scene: astra.fx.scene first"));
				return;
			}
			const int32 Facing = FacingOf(Arg(bShield ? 0 : 2, TEXT("bow")));
			const int32 N = bShield ? FMath::Clamp(FCString::Atoi(*Arg(1, TEXT("4"))), 1, 200) : 1;
			const EAstraHitKind Kind = bShield ? EAstraHitKind::Rail : KindOf(Arg(0, TEXT("rail")));
			const float Damage = bShield ? 30.f : FCString::Atof(*Arg(1, TEXT("40")));
			if (!bShield)
			{
				To->bShieldsUp = false;                            // (a blow that gets through: the shield is down for it)
			}
			for (int32 n = 0; n < N; ++n)
			{
				Pending.Add({0.22f * n, FString::Printf(TEXT("_strike %d %d %.1f %d"), To->Id, Facing, Damage, (int32)Kind)});
			}
			if (!bShield)
			{
				Pending.Add({0.5f, FString::Printf(TEXT("_shields %d"), To->Id)});
			}
		}
		else if (Name == TEXT("_strike"))
		{
			if (FAstraBattleShip* To = B->FindById(FCString::Atoi(*Arg(0, TEXT("-1")))))
			{
				Strike(Fx, *To, FCString::Atoi(*Arg(1, TEXT("0"))), FCString::Atof(*Arg(2, TEXT("30"))), (EAstraHitKind)FCString::Atoi(*Arg(3, TEXT("0"))), -1);
			}
		}
		else if (Name == TEXT("_shields"))
		{
			if (FAstraBattleShip* To = B->FindById(FCString::Atoi(*Arg(0, TEXT("-1")))))
			{
				To->bShieldsUp = true;
			}
		}
		else if (Name == TEXT("swatch"))
		{
			const float Secs = FCString::Atof(*Arg(0, TEXT("40")));
			SwatchT = Secs <= 0.f ? 0.f : FMath::Clamp(Secs, 1.f, 600.f);
			SwatchRespawn = 0.f;
			if (SwatchT > 0.f && !Fx.IsLive())
			{
				UE_LOG(LogASTRA, Warning, TEXT("[WarFX] swatch: the effects are not drawing (materials missing? run tools/ue_scripts/make_war_fx.py)"));
			}
		}
		else if (Name == TEXT("burn"))
		{
			if (FAstraBattleShip* T = Pick(Fx, Arg(0, TEXT("T"))))
			{
				for (int32 s = 0; s < 3; ++s)
				{
					T->Dmg.Burn[s] = 120.f;
					T->Dmg.Breach[s] = 120.f;
				}
				T->Dmg.GuttedT[AstraWar::SecMid] = 0.f;
				T->Dmg.Structure[AstraWar::SecMid] = 0.f;
			}
		}
		else if (Name == TEXT("break"))
		{
			FAstraBattleShip* T = Pick(Fx, Arg(1, TEXT("T")));
			const FString How = Arg(0, TEXT("mid")).ToLower();
			if (!T)
			{
				UE_LOG(LogASTRA, Warning, TEXT("[WarFX] no scene: astra.fx.scene first"));
				return;
			}
			if (How.StartsWith(TEXT("r")))
			{
				B->Destroy(*T, EAstraHitKind::Internal, EAstraFate::ReactorBreach, AstraWar::SecMid);
			}
			else if (How.StartsWith(TEXT("d")))
			{
				B->DisableShip(*T, TEXT("test"));
			}
			else
			{
				B->Destroy(*T, EAstraHitKind::Internal, EAstraFate::Breakup, How.StartsWith(TEXT("b")) ? AstraWar::SecBow : (How.StartsWith(TEXT("s")) ? AstraWar::SecStern : AstraWar::SecMid));
			}
		}
		else
		{
			UE_LOG(LogASTRA, Warning, TEXT("[WarFX] unknown test command %s"), *Name);
		}
	}

	/** The lineup of astra.fx.swatch, written straight into the layers in world centimetres (x ahead of the bridge, y to starboard, z up), eight columns
	 *  200 m apart, 1.2 km ahead. Above: glows (a soft ball, a flash, a flare, the limb of a blast wave) that age together, again and again. At eye level, the long
	 *  thin things lying sideways, head to starboard: an ASTRA and a Mandate slug, a spark, a missile with its trail, an ASTRA and a Mandate laser, a cannon's
	 *  and a point-defence tracer. Below: the two drives' plumes, a cold and a hot chunk of hull, two fireballs and two clouds of smoke. What lives and dies
	 *  (the fire, the smoke) is thrown again every few seconds. */
	static void DrawSwatch(UAstraWarFX& Fx)
	{
		if (SwatchT <= 0.f)
		{
			return;
		}
		SwatchT -= Fx.Dt;
		SwatchRespawn -= Fx.Dt;
		using namespace AstraFx;
		const double Ahead = 1200.0, Step = 200.0;       // m
		const auto W = [&](double Col, double Up) { return FVector(Ahead, (Col - 3.5) * Step, Up) * 100.0; };
		const auto Sys = [&](double Col, double Up) { return Fx.F.Origin + Fx.F.Att.RotateVector(W(Col, Up) / 100.0 + Fx.F.Bridge); };
		const FQuat Side = FQuat::FindBetweenNormals(FVector::ZAxisVector, FVector::YAxisVector);        // a tube's axis along +y: seen from its side
		const float Gain = Fx.Intensity;
		const FLinearColor Ac = ShotColor(true, EAstraHitKind::Rail), Mc = ShotColor(false, EAstraHitKind::Rail);
		const FLinearColor Al = ShotColor(true, EAstraHitKind::Laser), Ml = ShotColor(false, EAstraHitKind::Laser);
		FTransform* X;

		// row A, above: the glows
		{
			const float Age = 0.85f * FMath::Frac(Fx.Clock / 2.6f);
			struct FGlowSpec { float Kind; FLinearColor Col; float R; float Inten; };
			const FGlowSpec Specs[8] = {
				{0.f, Ac, 40.f, 220.f}, {1.f, FLinearColor(1.f, 0.97f, 0.9f), 50.f, 300.f}, {1.f, Mc, 50.f, 400.f}, {2.f, Mc, 36.f, 300.f},
				{3.f, FLinearColor(1.f, 0.7f, 0.4f), 70.f, 140.f}, {0.f, Mc, 40.f, 220.f}, {1.f, Al, 30.f, 260.f}, {1.f, Ml, 30.f, 260.f}};
			for (int32 i = 0; i < 8; ++i)
			{
				if (float* D = Fx.Glows.Next(X))
				{
					const float R = Specs[i].R * (Specs[i].Kind == 3.f ? 1.f : GlowK);         // (the blast wave's shell is drawn at its own size)
					*X = FTransform(FQuat::Identity, W(i, 250.0), FVector(R * 2.f));
					Fill(D, Specs[i].Col, Specs[i].Inten * Gain, Age, Specs[i].Kind, 0.f, 0.37f * i, R * 2.f, 0.f);
				}
			}
		}

		// row B, at eye level: slugs and a spark
		for (int32 i = 0; i < 3; ++i)
		{
			if (float* D = Fx.Darts.Next(X))
			{
				const bool bSpark = i == 2;
				const float Len = bSpark ? 24.f : 110.f, Wd = bSpark ? 1.4f : 6.f;
				*X = FTransform(Side, W(i, 0.0), FVector(Wd, Wd, Len));
				Fill(D, bSpark ? FLinearColor(1.f, 0.7f, 0.32f) : (i == 1 ? Mc : Ac), (bSpark ? 260.f : 700.f) * Gain, 0.f, bSpark ? 3.f : 0.f, 0.f, 0.3f, Wd, Len);
			}
		}
		// a missile: its glowing head and the trail of beads behind it (young at the head, old at the tail), as the war draws them
		{
			const double HeadY = 70.0, Bead = 18.0;                 // m
			if (float* D = Fx.Glows.Next(X))
			{
				const float R = 7.f * GlowK;
				*X = FTransform(FQuat::Identity, W(3, 0.0) + FVector(0.0, HeadY * 100.0, 0.0), FVector(R * 2.f));
				Fill(D, FLinearColor(1.f, 0.85f, 0.6f), 260.f * Gain, 0.f, 0.f, 0.f, 0.f, R * 2.f, 0.f);
			}
			for (int32 k = 0; k < FTrack::TrailPts; ++k)
			{
				if (float* D = Fx.Darts.Next(X))
				{
					const float AgeTail = (float)(k + 1) / (float)FTrack::TrailPts, AgeHead = (float)k / (float)FTrack::TrailPts;
					const float Wd = 2.2f * (1.f + 2.2f * AgeTail), Len = (float)Bead * 1.7f;
					*X = FTransform(Side, W(3, 0.0) + FVector(0.0, (HeadY - (k + 0.5) * Bead) * 100.0, 0.0), FVector(Wd, Wd, Len));
					Fill(D, Mc, 65.f * Gain, AgeTail, 2.f, AgeHead, 0.3f, Wd, Len);
				}
			}
		}
		// beams and tracers
		for (int32 i = 4; i < 8; ++i)
		{
			if (float* D = Fx.Tubes.Next(X))
			{
				const bool bLaser = i < 6, bAstra = (i & 1) == 0;
				const float Len = bLaser ? 160.f : 70.f, Wd = bLaser ? 5.f : (i == 6 ? 1.1f : 0.9f);
				*X = FTransform(Side, W(i, 0.0), FVector(Wd, Wd, Len));
				Fill(D, bLaser ? (bAstra ? Al : Ml) : ShotColor(bAstra, i == 6 ? EAstraHitKind::Cannon : EAstraHitKind::PointDefence),
				     (bLaser ? 520.f : (i == 6 ? 420.f : 360.f)) * Gain, 0.f, bLaser ? 1.f : 4.f, Len, 0.4f, Wd, Len);
			}
		}

		// row C, below: the plumes (ASTRA's blue-white, the Mandate's amber: lip at the port end), the chunks of hull, then the fire and the smoke thrown below
		for (int32 i = 0; i < 2; ++i)
		{
			if (float* D = Fx.Plumes.Next(X))
			{
				const float Len = 90.f, Wd = 6.6f;
				*X = FTransform(Side, W(i, -250.0), FVector(Wd, Wd, Len));
				Fill(D, i ? FLinearColor(1.f, 0.62f, 0.3f) : FLinearColor(0.78f, 0.9f, 1.f), 70.f * Gain * 0.85f, Fx.Clock, (float)i, 0.f, 0.3f, Wd, Len);
			}
		}
		for (int32 i = 0; i < 2; ++i)
		{
			if (float* D = Fx.DebrisL.Next(X))
			{
				*X = FTransform(FQuat(FVector(1.0, 0.6, 0.3).GetSafeNormal(), Fx.Clock * 0.35f), W(2 + i, -250.0), FVector(26.f, 14.f, 5.f));
				Fill(D, i ? FLinearColor(0.07f, 0.062f, 0.055f) : FLinearColor(0.5f, 0.49f, 0.46f), i ? 55.f : 0.f, 0.f, 0.f, 0.f, 0.f, 0.f, 0.f);
			}
		}
		if (SwatchRespawn <= 0.f)
		{
			SwatchRespawn = 3.4f;
			const FVector Vel = Fx.F.Vel;                           // (they keep up with the Aquila: what is thrown here stays here)
			for (int32 i = 0; i < 2; ++i)
			{
				if (FPuff* P = Fx.AddPuff(Sys(4 + i, -250.0), Vel, 2.6f, 20.f, 50.f, FLinearColor(1.f, 0.6f, 0.24f), 190.f, LFire))
				{
					P->P1 = 0.5f * (float)i;
				}
			}
			Fx.Smoke(Sys(6, -250.0), Vel, 40.f, 6.5f, 0.85f);
			Fx.Smoke(Sys(7, -250.0), Vel, 40.f, 6.5f, 0.35f);       // a paler cloud
		}
	}

	static void Pump(UAstraWarFX& Fx, float Dt)
	{
		TArray<FString> Lines = MoveTemp(Queue);
		Queue.Reset();
		for (int32 i = Pending.Num() - 1; i >= 0; --i)
		{
			if ((Pending[i].T -= Dt) <= 0.f)
			{
				Lines.Add(Pending[i].Line);
				Pending.RemoveAtSwap(i);
			}
		}
		for (const FString& L : Lines)
		{
			TArray<FString> Parts;
			L.ParseIntoArray(Parts, TEXT(" "), true);
			if (Parts.Num() == 0)
			{
				continue;
			}
			const FString Name = Parts[0];
			Parts.RemoveAt(0);
			Run(Fx, Name, Parts);
		}
	}
};

TArray<FString> FAstraWarFXTest::Queue;
TArray<FAstraWarFXTest::FPending> FAstraWarFXTest::Pending;
TArray<int32> FAstraWarFXTest::SceneIds;
float FAstraWarFXTest::SwatchT = 0.f;
float FAstraWarFXTest::SwatchRespawn = 0.f;

void UAstraWarFX::RunTests()
{
	FAstraWarFXTest::Pump(*this, Dt);
	FAstraWarFXTest::DrawSwatch(*this);
}

namespace
{
	void FxEnqueue(const TCHAR* Name, const TArray<FString>& Args)
	{
		FAstraWarFXTest::Queue.Add(FString::Printf(TEXT("%s %s"), Name, *FString::Join(Args, TEXT(" "))));
	}
}

#define ASTRA_FX_COMMAND(NAME, HELP) \
	static FAutoConsoleCommand GFxCmd_##NAME(TEXT("astra.fx." #NAME), TEXT(HELP), FConsoleCommandWithArgsDelegate::CreateStatic([](const TArray<FString>& A) { FxEnqueue(TEXT(#NAME), A); }))

ASTRA_FX_COMMAND(scene, "Effects test scene in front of the bridge: astra.fx.scene [range_km 6] [bearing 0] (a Mandate cruiser, an ASTRA battleship, a Mandate destroyer, held, guns silent)");
ASTRA_FX_COMMAND(clear, "Remove the effects test scene's ships");
ASTRA_FX_COMMAND(fire, "Fire a weapon in the test scene: astra.fx.fire <rail|laser|missile|torpedo|pd|cannon|all> [n 1] [from S|A|T|aquila] [at T|A|S|aquila]");
ASTRA_FX_COMMAND(shield, "Hit a shield sector in the test scene: astra.fx.shield [bow|stern|port|starboard|dorsal|ventral] [n 4] [on T|A|S|aquila] (enough hits and it falls)");
ASTRA_FX_COMMAND(hit, "One blow that gets through, in the test scene: astra.fx.hit <rail|laser|missile|torpedo|cannon> [damage 40] [facing bow] [on T|A|S|aquila]");
ASTRA_FX_COMMAND(burn, "Fires and venting in every section of a test ship: astra.fx.burn [on T|A|S]");
ASTRA_FX_COMMAND(break, "End a test ship: astra.fx.break <bow|mid|stern|reactor|disable> [on T|A|S]");
ASTRA_FX_COMMAND(swatch, "A lineup of every kind of effect 1.2 km ahead of the bridge, in both sides' colours (the material check): astra.fx.swatch [seconds 40]; 0 puts it away");
ASTRA_FX_COMMAND(stats, "What the war's effects hold and what they cost");
