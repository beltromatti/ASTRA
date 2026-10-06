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
//   astra.fx.reset                                  everything the effects hold goes (the pieces of the last break, particles, scars, shells)
//   astra.fx.swatch [seconds 40]                    a lineup of every kind of effect 1.2 km ahead of the bridge, in both sides' colours: the material check
//                                                   (needs no ships; if one of these looks wrong, the material is what is wrong, not the war)
//   astra.fx.stats                                  what the effects hold and what they cost
//   astra.fx.series <prefix> [n 8] [every_s 0.25] [vs] [do <command>]   n pictures of the game's view (no UI), every_s apart on the effects' own clock, from the frame the
//                                                   command ran (with "vs" the main viewscreen's feed too: Saved/Play/<prefix>_NN.png, <prefix>_NN_vs.png); the command
//                                                   after "do" runs first (astra.fx.series b4 12 0.1 vs do fire rail 3 aquila T): a blast or a volley in steps, the way
//                                                   the bench of the war cannot show it; with "cam" the free camera too (_cam.png)
//   astra.fx.cam <x> <y> <z> <yaw> <pitch> [fov 60]  a free camera for the tests, a pose in the bridge's frame (metres: x ahead, y to starboard, z up; the Aquila's hull is
//                                                   centred 172 m aft of and 62 m below the bridge); astra.fx.cam broadside [T] is the main viewscreen's «ASN AQUILA · FIRING
//                                                   ON ...» camera (320 m behind her centre, 210 m aside, 100 m up, looking down the line of fire to the target, 46 degrees);
//                                                   astra.fx.cam off. Its pictures come with astra.fx.series ... cam
//   astra.fx.cam look <T|A|S|aquila> <range_m> <azimuth_deg> <elevation_deg> [fov 50]   a camera that keeps a ship in the middle of its picture whatever the Aquila does: range
//                                                   off the ship; azimuth 0 on the Aquila's side of it, 90 to the right of the line between them; elevation up from the level
//                                                   (89: looking straight down on it). (The poses above are fixed in the bridge's frame: they mean something only while the Aquila is held.)
//   astra.fx.scar [on T|A|S|aquila] [kind 0-7] [facing dorsal] [felt 60]   one mark of battle damage at the middle of that face, of that kind (burn, hole, torn, impact,
//                                                   strafe, melt, gouge, blast), with no blow to go with it: whether the decals are there, and where

#include "AstraWarFX.h"
#include "AstraBattleSubsystem.h"
#include "ASTRA.h"
#include "Components/SceneCaptureComponent2D.h"
#include "Engine/Engine.h"
#include "Engine/PostProcessVolume.h"
#include "Engine/SceneCapture2D.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/TextureRenderTarget2D.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "ImageUtils.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "TextureResource.h"
#include "UnrealClient.h"

struct FAstraWarFXTest
{
	struct FPending { float T; FString Line; };
	static TArray<FString> Queue;
	static TArray<FPending> Pending;
	static TArray<int32> SceneIds;
	static float SwatchT;                  // seconds the lineup has left (0: none)
	static float SwatchRespawn;            // until the particles that live and die are thrown again
	static int32 SeriesLeft, SeriesIdx;    // astra.fx.series: pictures still to take, and the number of the next
	static float SeriesGap, SeriesNext;
	static FString SeriesPrefix;
	static bool bSeriesVs, bSeriesCam;
	static bool bCamOn, bCamBroadside, bCamLook;     // astra.fx.cam: the free camera is kept at its pose (a fixed one, the Aquila's broadside, or round a ship)
	static float CamLookRange, CamLookAz, CamLookEl;  // (look: metres off the ship, degrees round it from the Aquila's side, degrees up)
	static FVector CamPos, BroadSide;      // bridge frame, cm
	static float CamYaw, CamPitch, CamFov;
	static int32 CamW, CamH;
	static FString CamTarget;
	static bool bRecording, bOldFixed;
	static double OldDelta;
	static float RecordOrbit;
	static TWeakObjectPtr<UWorld> RecordWorld;
	static FDelegateHandle RecordCleanup;

	static FVector Polar(double RangeM, double BearingDeg, double MarkDeg)
	{
		const double B = FMath::DegreesToRadians(BearingDeg), M = FMath::DegreesToRadians(MarkDeg);
		return FVector(RangeM * FMath::Cos(M) * FMath::Cos(B), RangeM * FMath::Cos(M) * FMath::Sin(B), RangeM * FMath::Sin(M));
	}

	/** The living ship with that contact id (a scene made again leaves the old one's dead ship in the list under the same id: FindByContact would find that). */
	static FAstraBattleShip* Living(UAstraBattleSubsystem* B, const TCHAR* Contact)
	{
		for (FAstraBattleShip& S : B->Ships)
		{
			if (S.bAlive && S.ContactId.Equals(Contact, ESearchCase::IgnoreCase))
			{
				return &S;
			}
		}
		return nullptr;
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
			return Living(B, TEXT("FX-A"));
		}
		if (K == TEXT("s"))
		{
			return Living(B, TEXT("FX-S"));
		}
		if (K == TEXT("t") || K.IsEmpty())
		{
			return Living(B, TEXT("FX-T"));
		}
		return Living(B, *Key.ToUpper());
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
		else if (Name == TEXT("reset"))
		{
			Fx.ClearAll();                       // (the pieces of the last break, the particles, the scars, the shells: a clean sky for the next try)
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
			else if (SwatchT > 0.f)
			{
				UE_LOG(LogASTRA, Display, TEXT("[WarFX] swatch for %.0f s, 1.2 km ahead of the bridge, eight columns 200 m apart, left to right. Above: ASTRA ball, white flash, Mandate flash, "
				                               "Mandate flare, blast-wave ring, Mandate ball, ASTRA laser flash, Mandate laser flash. At eye level: ASTRA slug, Mandate slug, spark, "
				                               "missile with its trail, ASTRA laser, Mandate laser, ASTRA cannon tracer, point-defence tracer. Below: ASTRA plume, Mandate plume, cold chunk, "
				                               "hot chunk, two fireballs, a dark and a pale smoke (thrown every 3.4 s)"), SwatchT);
			}
		}
		else if (Name == TEXT("cam"))
		{
			const FString A0 = Arg(0, TEXT("off")).ToLower();
			if (A0 == TEXT("off"))
			{
				bCamOn = false;
				return;
			}
			CamW = 1280;
			CamH = 720;
			BroadSide = FVector::ZeroVector;
			bCamLook = false;
			if (A0 == TEXT("broadside"))
			{
				bCamBroadside = true;
				CamTarget = Arg(1, TEXT("T"));
			}
			else if (A0 == TEXT("look"))
			{
				bCamBroadside = false;
				bCamLook = true;
				CamTarget = Arg(1, TEXT("T"));
				CamLookRange = FMath::Max(FCString::Atof(*Arg(2, TEXT("1000"))), 20.f);
				CamLookAz = FCString::Atof(*Arg(3, TEXT("0")));
				CamLookEl = FCString::Atof(*Arg(4, TEXT("0")));
				CamFov = FCString::Atof(*Arg(5, TEXT("50")));
			}
			else
			{
				bCamBroadside = false;
				CamPos = FVector(FCString::Atod(*A0), FCString::Atod(*Arg(1, TEXT("0"))), FCString::Atod(*Arg(2, TEXT("0")))) * 100.0;
				CamYaw = FCString::Atof(*Arg(3, TEXT("0")));
				CamPitch = FCString::Atof(*Arg(4, TEXT("0")));
				CamFov = FCString::Atof(*Arg(5, TEXT("60")));
			}
			bCamOn = true;
			MakeCamera(Fx);
		}
		else if (Name == TEXT("record"))
        {
            if (Arg(0, TEXT("off")) == TEXT("off"))
            {
                if (bRecording) { FApp::SetUseFixedTimeStep(bOldFixed); FApp::SetFixedDeltaTime(OldDelta); }
                bRecording = false; SeriesLeft = 0; return;
            }
            if (bRecording) { FApp::SetUseFixedTimeStep(bOldFixed); FApp::SetFixedDeltaTime(OldDelta); }
            bOldFixed = FApp::UseFixedTimeStep();
            OldDelta = FApp::GetFixedDeltaTime();
            const float Fps = FMath::Clamp(FCString::Atof(*Arg(2, TEXT("60"))), 24.f, 60.f);
            FApp::SetFixedDeltaTime(1.0 / Fps); FApp::SetUseFixedTimeStep(true);
            bRecording = true;
            RecordWorld = Fx.Owner ? Fx.Owner->GetWorld() : nullptr;
            if (!RecordCleanup.IsValid())
            {
                RecordCleanup = FWorldDelegates::OnWorldCleanup.AddLambda([](UWorld* W, bool, bool)
                {
                    if (bRecording && RecordWorld.Get() == W) { FApp::SetUseFixedTimeStep(bOldFixed); FApp::SetFixedDeltaTime(OldDelta); bRecording = false; SeriesLeft = 0; }
                });
            }
            SeriesPrefix = Arg(0, TEXT("cinematic"));
            SeriesLeft = FMath::Clamp(FCString::Atoi(*Arg(1, TEXT("180"))), 1, 3600);
            SeriesIdx = 0; SeriesGap = 1.f / Fps; SeriesNext = 0.f;
            bSeriesCam = true; bSeriesVs = false;
            if (!bCamOn) { Run(Fx, TEXT("cam"), {TEXT("broadside")}); }
            CamW = FMath::Clamp(FCString::Atoi(*Arg(3, TEXT("1920"))), 640, 3840);
            CamH = FMath::Clamp(FCString::Atoi(*Arg(4, TEXT("1080"))), 360, 2160);
            RecordOrbit = FCString::Atof(*Arg(5, TEXT("0")));
            MakeCamera(Fx);
        }
		else if (Name == TEXT("series"))
		{
			SeriesPrefix = Arg(0, TEXT("series"));
			SeriesLeft = FMath::Clamp(FCString::Atoi(*Arg(1, TEXT("8"))), 1, 400);
			SeriesGap = FMath::Clamp(FCString::Atof(*Arg(2, TEXT("0.25"))), 0.02f, 10.f);
			SeriesIdx = 0;
			SeriesNext = 0.f;
			bSeriesVs = false;
			bSeriesCam = false;
			for (int32 i = 3; i < A.Num(); ++i)
			{
				if (A[i] == TEXT("vs"))
				{
					bSeriesVs = true;
				}
				else if (A[i] == TEXT("cam"))
				{
					bSeriesCam = true;
					if (!bCamOn)
					{
						Run(Fx, TEXT("cam"), {TEXT("broadside")});            // (none set: the Aquila's broadside shot)
					}
				}
				else if (A[i] == TEXT("do"))
				{
					// what the series is about, run on the frame after the first picture is asked for
					Queue.Add(FString::Join(TArrayView<const FString>(A).Mid(i + 1), TEXT(" ")));
					break;
				}
			}
		}
		else if (Name == TEXT("scar"))
		{
			FAstraBattleShip* To = Pick(Fx, Arg(0, TEXT("T")));
			if (!To)
			{
				UE_LOG(LogASTRA, Warning, TEXT("[WarFX] no scene: astra.fx.scene first"));
				return;
			}
			const int32 Facing = FacingOf(Arg(2, TEXT("dorsal")));
			FVector Lp = AstraWar::FacingVector(Facing);
			if (To->Box.Valid())
			{
				Lp = FVector(Lp.X * To->Box.Hx, Lp.Y * To->Box.Hy, Lp.Z * To->Box.Hz);
				Lp.X += To->Box.Mid;
			}
			else
			{
				Lp *= To->Radius;
			}
			FAstraFxHit H;
			H.Pos = To->Pos + To->Att.RotateVector(Lp);
			H.Dir = -To->Att.RotateVector(AstraWar::FacingVector(Facing));
			H.Kind = EAstraHitKind::Rail;
			H.Facing = Facing;
			H.LocalOut = AstraWar::FacingVector(Facing);
			H.Felt = FCString::Atof(*Arg(3, TEXT("60")));
			Fx.TestScarKind = FMath::Clamp(FCString::Atoi(*Arg(1, TEXT("0"))), 0, 7);
			Fx.AddScar(*To, H);
			Fx.TestScarKind = -1;
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

	/** The free camera of astra.fx.cam: an engine scene capture that renders everything the bridge's own view would, from wherever it is put, at the bridge's exposure. */
	static void MakeCamera(UAstraWarFX& Fx)
	{
		UWorld* World = Fx.Owner ? Fx.Owner->GetWorld() : nullptr;
		if (!World || !FApp::CanEverRender())
		{
			return;
		}
		ASceneCapture2D* A = Cast<ASceneCapture2D>(Fx.TestCamera);
		if (!A)
		{
			FActorSpawnParameters P;
			P.ObjectFlags |= RF_Transient;
			P.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
			A = World->SpawnActor<ASceneCapture2D>(FVector::ZeroVector, FRotator::ZeroRotator, P);
			Fx.TestCamera = A;
			if (!A)
			{
				return;
			}
			USceneCaptureComponent2D* C = A->GetCaptureComponent2D();
			C->bCaptureEveryFrame = false;
			C->bCaptureOnMovement = false;
			C->bAlwaysPersistRenderingState = true;
			C->CaptureSource = ESceneCaptureSource::SCS_FinalColorLDR;
			C->PrimitiveRenderMode = ESceneCapturePrimitiveRenderMode::PRM_RenderScenePrimitives;
			for (TActorIterator<APostProcessVolume> It(World); It; ++It)
			{
				if (It->bUnbound && It->Settings.bOverride_AutoExposureMinBrightness)
				{
					C->PostProcessSettings = It->Settings;            // (the bridge's own fixed exposure, EV100 6.6)
					break;
				}
			}
			C->PostProcessBlendWeight = 1.f;
			FEngineShowFlags& SF = C->ShowFlags;
			SF.SetTemporalAA(true);
			SF.SetMotionBlur(false);
			SF.SetAmbientOcclusion(false);
			SF.SetDistanceFieldAO(false);
			SF.SetScreenSpaceReflections(false);
			SF.SetFog(false);
			SF.SetVolumetricFog(false);
			SF.SetLumenGlobalIllumination(false);
			SF.SetLumenReflections(false);
		}
		if (!Fx.TestTarget || Fx.TestTarget->SizeX != CamW || Fx.TestTarget->SizeY != CamH)
		{
			UTextureRenderTarget2D* RT = NewObject<UTextureRenderTarget2D>(Fx.Owner, NAME_None);
			RT->RenderTargetFormat = ETextureRenderTargetFormat::RTF_RGBA8;
			RT->ClearColor = FLinearColor::Black;
			RT->InitAutoFormat(CamW, CamH);
			RT->UpdateResourceImmediate(true);
			Fx.TestTarget = RT;
			A->GetCaptureComponent2D()->TextureTarget = RT;
		}
	}

	/** Keeps the free camera at its pose (the broadside shot follows the target as the main viewscreen's does, with the side it chose at the start). */
	static void UpdateCamera(UAstraWarFX& Fx)
	{
		ASceneCapture2D* A = bCamOn ? Cast<ASceneCapture2D>(Fx.TestCamera) : nullptr;
		if (!A)
		{
			return;
		}
		FVector Pos = CamPos;
		FRotator Rot(CamPitch, CamYaw, 0.f);
		float Fov = CamFov;
		if (bCamLook)
		{
			// round the ship, in the bridge's frame (the world's): the Aquila's side of it at azimuth 0, her right at 90
			const FVector Hull(-17200.0, 0.0, -6200.0);
			if (const FAstraBattleShip* T = Pick(Fx, CamTarget))
			{
				const FVector TgtW = Fx.F.ToWorld(T->Pos);
				FVector Dir = TgtW - Hull;
				Dir.Z = 0.0;
				Dir = Dir.GetSafeNormal();
				if (Dir.IsNearlyZero())
				{
					Dir = FVector::ForwardVector;
				}
				const FVector Right = FVector::CrossProduct(FVector::UpVector, Dir).GetSafeNormal();
				const double Az = FMath::DegreesToRadians((double)CamLookAz), El = FMath::DegreesToRadians((double)CamLookEl);
				const FVector Off = (-Dir * FMath::Cos(Az) + Right * FMath::Sin(Az)) * FMath::Cos(El) + FVector::UpVector * FMath::Sin(El);
				Pos = TgtW + Off * (double)CamLookRange * 100.0;
				Rot = (TgtW - Pos).GetSafeNormal().Rotation();
			}
		}
		else if (bCamBroadside)
		{
			const FVector Hull(-17200.0, 0.0, -6200.0);                   // her centre in the bridge's frame (cm)
			const FAstraBattleShip* T = Pick(Fx, CamTarget);
			const FVector TgtW = T ? Fx.F.ToWorld(T->Pos) : Hull + FVector(1.0e7, 0.0, 0.0);
			const FVector Dir = (TgtW - Hull).GetSafeNormal();
			if (BroadSide.IsNearlyZero())
			{
				BroadSide = FVector::CrossProduct(FVector::UpVector, Dir).GetSafeNormal();
				if (BroadSide.IsNearlyZero())
				{
					BroadSide = FVector::RightVector;
				}
			}
			Pos = Hull - Dir * 32000.0 + BroadSide * 21000.0 + FVector(0.0, 0.0, 10000.0);
			Rot = (Hull + Dir * 250000.0 - Pos).GetSafeNormal().Rotation();
			Fov = 46.f;
		}
		A->SetActorLocationAndRotation(Pos, Rot);
		A->GetCaptureComponent2D()->FOVAngle = Fov;
	}

	static void CaptureCamera(UAstraWarFX& Fx, const FString& Path)
	{
		ASceneCapture2D* A = Cast<ASceneCapture2D>(Fx.TestCamera);
		FTextureRenderTargetResource* R = Fx.TestTarget ? Fx.TestTarget->GameThread_GetRenderTargetResource() : nullptr;
		if (!A || !R)
		{
			return;
		}
		A->GetCaptureComponent2D()->CaptureScene();
		TArray<FColor> Px;
		if (!R->ReadPixels(Px) || Px.Num() != CamW * CamH)
		{
			return;
		}
		for (FColor& C : Px)
		{
			C.A = 255;
		}
		TArray64<uint8> Png;
		FImageUtils::PNGCompressImageArray(CamW, CamH, TArrayView64<const FColor>(Px.GetData(), Px.Num()), Png);
		FFileHelper::SaveArrayToFile(Png, *Path);
	}

	/** One step of astra.fx.series: a picture of the game's view (and of the main viewscreen's feed) every SeriesGap seconds of the effects' clock. */
	static void Series(UAstraWarFX& Fx)
	{
		if (bRecording && bCamLook) { CamLookAz += RecordOrbit * Fx.Dt; }
		UpdateCamera(Fx);
		if (SeriesLeft <= 0)
		{
			return;
		}
		if (!FApp::CanEverRender() || !Fx.Owner || !Fx.Owner->GetWorld())
		{
			SeriesLeft = 0;
			if (bRecording) { FApp::SetUseFixedTimeStep(bOldFixed); FApp::SetFixedDeltaTime(OldDelta); bRecording = false; }
			return;
		}
        if (!bRecording)
        {
            SeriesNext -= Fx.Dt;
            if (SeriesNext > 0.f) { return; }
            SeriesNext = SeriesGap;
        }                // (a frame longer than the gap does not catch up)
		const FString Base = FPaths::ConvertRelativePathToFull(FPaths::ProjectSavedDir() / TEXT("Play") / FString::Printf(TEXT("%s_%02d"), *SeriesPrefix, SeriesIdx));
		if (!bRecording) { FScreenshotRequest::RequestScreenshot(Base + TEXT(".png"), false, false); }
		if (bSeriesVs)
		{
			GEngine->Exec(Fx.Owner->GetWorld(), *FString::Printf(TEXT("astra.viewscreen.dump %s_vs.png"), *Base));
		}
		if (bSeriesCam)
		{
			CaptureCamera(Fx, Base + TEXT("_cam.png"));
		}
		++SeriesIdx;
		if (--SeriesLeft == 0)
		{
			if (bRecording) { FApp::SetUseFixedTimeStep(bOldFixed); FApp::SetFixedDeltaTime(OldDelta); bRecording = false; }
			UE_LOG(LogASTRA, Display, TEXT("[WarFX] series %s: %d pictures in Saved/Play"), *SeriesPrefix, SeriesIdx);
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
			// the help reads "[on T]", "[from S] [at T]": the little words are for the reader (the arguments are positional)
			Parts.RemoveAll([](const FString& W) { return W.Equals(TEXT("on"), ESearchCase::IgnoreCase) || W.Equals(TEXT("from"), ESearchCase::IgnoreCase) || W.Equals(TEXT("at"), ESearchCase::IgnoreCase); });
			Run(Fx, Name, Parts);
		}
	}
};

TArray<FString> FAstraWarFXTest::Queue;
TArray<FAstraWarFXTest::FPending> FAstraWarFXTest::Pending;
TArray<int32> FAstraWarFXTest::SceneIds;
float FAstraWarFXTest::SwatchT = 0.f;
float FAstraWarFXTest::SwatchRespawn = 0.f;
int32 FAstraWarFXTest::SeriesLeft = 0;
int32 FAstraWarFXTest::SeriesIdx = 0;
float FAstraWarFXTest::SeriesGap = 0.25f;
float FAstraWarFXTest::SeriesNext = 0.f;
FString FAstraWarFXTest::SeriesPrefix;
bool FAstraWarFXTest::bSeriesVs = false;
bool FAstraWarFXTest::bSeriesCam = false;
bool FAstraWarFXTest::bCamOn = false;
bool FAstraWarFXTest::bCamBroadside = false;
bool FAstraWarFXTest::bCamLook = false;
float FAstraWarFXTest::CamLookRange = 1000.f;
float FAstraWarFXTest::CamLookAz = 0.f;
float FAstraWarFXTest::CamLookEl = 0.f;
FVector FAstraWarFXTest::CamPos = FVector::ZeroVector;
FVector FAstraWarFXTest::BroadSide = FVector::ZeroVector;
float FAstraWarFXTest::CamYaw = 0.f;
float FAstraWarFXTest::CamPitch = 0.f;
float FAstraWarFXTest::CamFov = 60.f;
int32 FAstraWarFXTest::CamW = 1280;
int32 FAstraWarFXTest::CamH = 720;
FString FAstraWarFXTest::CamTarget;
bool FAstraWarFXTest::bRecording = false;
bool FAstraWarFXTest::bOldFixed = false;
double FAstraWarFXTest::OldDelta = 0.0;
float FAstraWarFXTest::RecordOrbit = 0.f;
TWeakObjectPtr<UWorld> FAstraWarFXTest::RecordWorld;
FDelegateHandle FAstraWarFXTest::RecordCleanup;

void UAstraWarFX::RunTests()
{
	FAstraWarFXTest::Pump(*this, Dt);
	FAstraWarFXTest::DrawSwatch(*this);
	FAstraWarFXTest::Series(*this);
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
ASTRA_FX_COMMAND(reset, "Everything the effects hold goes: the pieces of a broken ship, the particles, the scars, the shields' shells (a clean sky for the next test)");
ASTRA_FX_COMMAND(fire, "Fire a weapon in the test scene: astra.fx.fire <rail|laser|missile|torpedo|pd|cannon|all> [n 1] [from S|A|T|aquila] [at T|A|S|aquila]");
ASTRA_FX_COMMAND(shield, "Hit a shield sector in the test scene: astra.fx.shield [bow|stern|port|starboard|dorsal|ventral] [n 4] [on T|A|S|aquila] (enough hits and it falls)");
ASTRA_FX_COMMAND(hit, "One blow that gets through, in the test scene: astra.fx.hit <rail|laser|missile|torpedo|cannon> [damage 40] [facing bow] [on T|A|S|aquila]");
ASTRA_FX_COMMAND(scar, "One mark of battle damage at the middle of a hull's face, with no blow: astra.fx.scar [on T|A|S|aquila] [kind 0-7 (burn, hole, torn, impact, strafe, melt, gouge, blast)] [facing dorsal] [felt 60]");
ASTRA_FX_COMMAND(burn, "Fires and venting in every section of a test ship: astra.fx.burn [on T|A|S]");
ASTRA_FX_COMMAND(break, "End a test ship: astra.fx.break <bow|mid|stern|reactor|disable> [on T|A|S]");
ASTRA_FX_COMMAND(swatch, "A lineup of every kind of effect 1.2 km ahead of the bridge, in both sides' colours (the material check): astra.fx.swatch [seconds 40]; 0 puts it away");
ASTRA_FX_COMMAND(stats, "What the war's effects hold and what they cost");
ASTRA_FX_COMMAND(series, "Pictures of the game's view in steps: astra.fx.series <prefix> [n 8] [every_s 0.25] [vs] [cam] [do <astra.fx command>] (Saved/Play/<prefix>_NN.png; vs: the main viewscreen's feed too; cam: the free camera's)");
ASTRA_FX_COMMAND(cam, "A free camera for the tests: astra.fx.cam <x> <y> <z> <yaw> <pitch> [fov 60] (metres in the bridge's frame: only while the Aquila is held) | broadside [T] (the Aquila-firing shot of the main viewscreen) | look <T> <range_m> <azimuth> <elevation> [fov 50] (round a ship, whatever the Aquila does) | off");

ASTRA_FX_COMMAND(record, "Fixed-step cinematic frames: astra.fx.record <prefix> [frames 180] [fps 60] [width 1920] [height 1080] [orbit_deg_s 0] | off; uses the free camera, restores the previous timestep when done");
