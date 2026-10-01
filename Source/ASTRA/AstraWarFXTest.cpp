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

void UAstraWarFX::RunTests()
{
	FAstraWarFXTest::Pump(*this, Dt);
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
ASTRA_FX_COMMAND(stats, "What the war's effects hold and what they cost");
