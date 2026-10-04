// ASTRA — the motion of the capital ships made readable, in the game: each frame every warship's motion is read (where she is, how fast, which way she points: AstraSpace::Observe), what
// her jets are asked is worked out (AstraSpace::Fire) and what is drawn follows: a short bright jet and a glow at each nozzle that burns, and the ribbon her drive leaves behind her. Nothing
// here moves a ship or is read back by the war. The rules and the numbers: AstraSpaceLifeMotion.h; what and why: docs/SPAZIO.md.

#include "AstraSpaceLife.h"
#include "AstraSpaceLifeDrawUtil.h"
#include "AstraBattleSubsystem.h"
#include "ASTRA.h"
#include "Engine/World.h"
#include "HAL/PlatformTime.h"

using namespace AstraSpaceDraw;

namespace
{
	TAutoConsoleVariable<int32> CVarMoMotion(TEXT("astra.space.motion"), 1, TEXT("The capital ships' manoeuvring jets and engine wakes (SPAZIO-VIVO): 1 on, 0 off"));
	TAutoConsoleVariable<float> CVarMoJetGain(TEXT("astra.space.jets.gain"), 1.f, TEXT("How bright the manoeuvring jets are (1 as made; the war effects' own intensity, astra.fx.intensity, comes on top)"));
	TAutoConsoleVariable<float> CVarMoJetKm(TEXT("astra.space.jets.km"), 45.f, TEXT("A ship's jets are drawn out to this range from the Aquila (km)"));
	TAutoConsoleVariable<int32> CVarMoWakes(TEXT("astra.space.wakes"), 1, TEXT("The engine wakes a drive leaves behind a capital ship: 1 on, 0 off"));
	TAutoConsoleVariable<float> CVarMoWakeGain(TEXT("astra.space.wakes.gain"), 1.f, TEXT("How bright the engine wakes are"));
	TAutoConsoleVariable<float> CVarMoWakeKm(TEXT("astra.space.wakes.km"), 110.f, TEXT("A ship's wake is drawn out to this range from the Aquila (km)"));
	TAutoConsoleVariable<float> CVarMoWakeLife(TEXT("astra.space.wakes.life"), 1.f, TEXT("How long the wakes last, as a multiple of the usual (10 to 24 s by the ship's length)"));

	constexpr double MoKm = 1000.0;
	constexpr int32 MoJetsPerShip = 10;                      // the most jets drawn lit for one ship at an instant
	const FLinearColor MoCoreAstra(0.78f, 0.9f, 1.f), MoCoreMandate(1.f, 0.62f, 0.3f);
	const FLinearColor MoWakeAstra(0.45f, 0.72f, 1.f), MoWakeMandate(1.f, 0.52f, 0.26f);
}

void UAstraSpaceLife::TickMotion(float SimDt)
{
	if (!Owner)
	{
		return;
	}
	const double T0 = FPlatformTime::Seconds();
	const AstraSpace::FJetData& Data = AstraSpace::JetData();
	if (CVarMoMotion.GetValueOnGameThread() == 0 || !Data.bLoaded)
	{
		if (Motions.Num() > 0)
		{
			Motions.Reset();
		}
		return;
	}
	MotionClock += SimDt;
	const bool bWakes = CVarMoWakes.GetValueOnGameThread() != 0;
	const float WakeKm = CVarMoWakeKm.GetValueOnGameThread();
	const float Life = CVarMoWakeLife.GetValueOnGameThread();
	for (FAstraBattleShip& S : Owner->Ships)
	{
		if (!S.bAlive || S.bGhost || S.bCraft || S.bFixture || S.bDerelict || S.MaxAccel < 0.5f)
		{
			continue;
		}
		const AstraSpace::FJetClass* C = Data.Find(S.ClassKey);
		if (!C)
		{
			continue;
		}
		AstraSpace::FMotion& M = Motions.FindOrAdd(S.Id);
		if (M.Seed == 0.f)
		{
			M.Seed = FMath::Frac(0.17f + (float)S.Id * 0.61803f);
		}
		M.Seen = Frame;
		M.ShipId = S.Id;
		M.Faction = S.Side == EAstraSide::Astra ? 0 : (S.Side == EAstraSide::Mandate ? 1 : 2);
		M.bPowered = !S.bDisabled && !S.bCold;                // (lying dark: drives off, no emissions: no jets, no wake)
		AstraSpace::Observe(M, *C, S.Pos, S.Vel, S.Att, S.MaxAccel, FMath::DegreesToRadians(S.MaxTurnDeg), SimDt);
		if (M.bPowered)
		{
			AstraSpace::Fire(M, *C, Dt);
		}
		else if (M.Peak > 0.f)
		{
			M.Kick = FVector::ZeroVector;                    // (no power: what burns goes out)
			for (float& B : M.Burn)
			{
				B = 0.f;
			}
			M.Peak = 0.f;
		}
		M.Thrust = (Owner->WarFX && Owner->WarFX->IsActive()) ? Owner->WarFX->Throttle(S) : 0.f;
		// the wake: noted where the drive burns while it does (a dead engine leaves nothing: the same test as the war's own plume)
		if (bWakes && M.bPowered && M.Thrust > 0.1f && Owner->EngineFactor(S) > 0.01f && S.Vel.SizeSquared() > 64.0
		    && FVector::DistSquared(S.Pos, F.Origin) < FMath::Square((double)WakeKm * 1.25 * MoKm))
		{
			M.Wake.Offer(S.Pos + S.Att.RotateVector(C->DriveP), MotionClock, 0.35f + 0.65f * M.Thrust, 0.05 * C->Len);
		}
	}
	// a ship no longer in the plot (lost, left) keeps only her wake, until it has faded
	for (auto It = Motions.CreateIterator(); It; ++It)
	{
		AstraSpace::FMotion& M = It.Value();
		if (M.Seen == Frame)
		{
			continue;
		}
		M.Peak = 0.f;
		const float L = M.Class ? AstraSpace::WakeLifeFor(M.Class->Len) * Life : 0.f;
		if (M.Wake.Num == 0 || MotionClock - (double)M.Wake.At(0).T > (double)L + 1.0)
		{
			It.RemoveCurrent();
		}
	}
	MotionShips = Motions.Num();
	MotionMs += (FPlatformTime::Seconds() - T0) * 1000.0;
	++MotionTicks;
}

void UAstraSpaceLife::AddJet(const AstraSpace::FMotion& M, const AstraSpace::FJet& J, float Level, float Len, float Km)
{
	// a jet is a few per cent of the hull's length (a real nozzle would be a speck at the range a battle is fought at): drawn larger the farther it is, so it reads
	const float DistK = FMath::Clamp(Km / 8.f, 1.f, 2.6f);
	const FVector Lip = M.PrevPos + M.PrevAtt.RotateVector(J.P);
	const FVector DirW = F.InvAtt.RotateVector(M.PrevAtt.RotateVector(J.D));
	const FVector LipW = F.ToWorld(Lip);
	const float Width = FMath::Max(0.0062f * Len, J.R * 2.f) * DistK;
	const float JetLen = 0.032f * Len * (0.45f + 0.55f * Level) * DistK;
	const FLinearColor Core = M.Faction == 0 ? MoCoreAstra : MoCoreMandate;
	const float Gain = LampGain * CVarMoJetGain.GetValueOnGameThread();
	FTransform* X;
	if (float* D = Jets.Next(X))
	{
		*X = FTransform(FQuat::FindBetweenNormals(FVector::ZAxisVector, DirW), LipW + DirW * (JetLen * 50.0), FVector(Width, Width, JetLen));
		AstraFx::Fill(D, Core, 60.f * Level * Gain, Clock, M.Faction == 0 ? 0.f : 1.f, 0.25f, M.Seed, Width, JetLen);
	}
	else
	{
		++JetsDropped;
	}
	if (float* D = Lamps.Next(X))
	{
		const float R = 0.0105f * Len * (0.55f + 0.45f * Level) * DistK * AstraFx::GlowK;
		*X = FTransform(FQuat::Identity, LipW + DirW * (JetLen * 0.12), FVector(R * 2.f));
		AstraFx::Fill(D, AstraFx::Mix(Core, FLinearColor::White, 0.3f), 150.f * Level * Gain, 0.f, 0.f, 0.f, M.Seed, R * 2.f, 0.f);
	}
	else
	{
		++JetsDropped;
	}
}

void UAstraSpaceLife::DrawMotion()
{
	if (Motions.Num() == 0)
	{
		return;
	}
	const AstraSpace::FJetData& Data = AstraSpace::JetData();
	const bool bWakes = CVarMoWakes.GetValueOnGameThread() != 0;
	const double JetKm = CVarMoJetKm.GetValueOnGameThread();
	const double WakeKm = CVarMoWakeKm.GetValueOnGameThread();
	const float WakeGain = LampGain * CVarMoWakeGain.GetValueOnGameThread();
	const float WakeLifeK = FMath::Max(0.1f, CVarMoWakeLife.GetValueOnGameThread());
	// the nearest ships first: when a layer is full it is the far ones that go without
	struct FItem
	{
		double D2;
		AstraSpace::FMotion* M;
	};
	TArray<FItem, TInlineAllocator<48>> Items;
	for (TPair<int32, AstraSpace::FMotion>& KV : Motions)
	{
		AstraSpace::FMotion& M = KV.Value;
		if (M.Class)
		{
			Items.Add({FVector::DistSquared(M.PrevPos, F.Origin), &M});
		}
	}
	Items.Sort([](const FItem& A, const FItem& B) { return A.D2 < B.D2; });
	for (const FItem& It : Items)
	{
		AstraSpace::FMotion& M = *It.M;
		const AstraSpace::FJetClass& C = *M.Class;
		const double Km = FMath::Sqrt(It.D2) * 0.001;
		const bool bAlive = M.Seen == Frame;
		if (bAlive && M.bPowered && M.Peak > 0.04f && Km < JetKm)
		{
			TArray<TPair<float, int32>, TInlineAllocator<32>> Lit;
			for (int32 j = 0; j < C.Jets.Num() && j < M.Burn.Num(); ++j)
			{
				const float B = M.Burn[j];
				if (B >= 0.05f && AstraSpace::PulseOn(B, Clock, FMath::Frac(M.Seed + (float)j * 0.137f)))
				{
					Lit.Add({B, j});
				}
			}
			Lit.Sort([](const TPair<float, int32>& A, const TPair<float, int32>& B) { return A.Key > B.Key; });
			for (int32 k = 0; k < FMath::Min(Lit.Num(), MoJetsPerShip); ++k)
			{
				AddJet(M, C.Jets[Lit[k].Value], Lit[k].Key, C.Len, (float)Km);
			}
			JetsLitNow += FMath::Min(Lit.Num(), MoJetsPerShip);
		}
		if (bWakes && Km < WakeKm && M.Wake.Num > 0)
		{
			const float Life = AstraSpace::WakeLifeFor(C.Len) * WakeLifeK;
			const FVector Head = bAlive ? M.PrevPos + M.PrevAtt.RotateVector(C.DriveP) : M.Wake.At(0).P;
			AstraSpace::FWakeSeg Seg[AstraSpace::Motion::WakeCap];
			const int32 N = AstraSpace::WakeSegments(M.Wake, Head, MotionClock, Life, Km < 35.0 ? 1 : (Km < 70.0 ? 2 : 4), Seg, AstraSpace::Motion::WakeCap);
			const FLinearColor Col = M.Faction == 0 ? MoWakeAstra : MoWakeMandate;
			const float W0 = FMath::Clamp(0.40f * C.DriveW, 3.f, 36.f);
			const float Gain = 24.f * WakeGain * (0.7f + 0.3f * FMath::Min(C.Len / 800.f, 1.3f));
			for (int32 i = 0; i < N; ++i)
			{
				const AstraSpace::FWakeSeg& G = Seg[i];
				const FVector A = F.ToWorld(G.A), B = F.ToWorld(G.B);
				const double L = FVector::Dist(A, B);
				if (L < 100.0)
				{
					continue;
				}
				// a bead near the eye would be a veil across the screen: it fades out inside a quarter of a kilometre and is not drawn inside sixty metres
				const double EyeM = ((A + B) * 0.5).Size() / 100.0;
				const float Near = AstraFx::Ease((float)((EyeM - 60.0) / 190.0));
				if (Near <= 0.f)
				{
					continue;
				}
				FTransform* X;
				float* D = Wakes.Next(X);
				if (!D)
				{
					++WakeDropped;
					break;
				}
				// a bead of the ribbon, an ellipsoid a little longer than its stretch of the path so that it melts into its neighbours; older: wider (the trail disperses), dimmer
				const FVector Dir = (A - B) / L;
				const float Width = W0 * (1.f + 1.9f * G.AgeB);
				const float Len = (float)(L / 100.0) * 1.7f;
				*X = FTransform(FQuat::FindBetweenNormals(FVector::ZAxisVector, Dir), (A + B) * 0.5, FVector(Width, Width, Len));
				AstraFx::Fill(D, Col, Gain * G.Str * Near, G.AgeB, 2.f, G.AgeA, M.Seed, Width, Len);
			}
		}
	}
}

FString UAstraSpaceLife::MotionStat() const
{
	return FString::Printf(TEXT("motion: %d ships read, jets lit %d now (%d plumes now / %d peak, %d dropped), wake pieces %d now / %d peak (%d dropped), %.4f ms avg"),
	                       MotionShips, JetsLitNow, JetsNow, JetsPeak, JetsDropped, WakeNow, WakePeak, WakeDropped, MotionTicks ? MotionMs / MotionTicks : 0.0);
}

FString UAstraSpaceLife::MotionTable() const
{
	FString Out = FString::Printf(TEXT("motion: %d ships read (the jets' demand: kick = a change of her turn's rate not yet worked off, in the class's full rate; push = across her heading, share of the full acceleration; jets = lit above 0.1 of the class's table)"), Motions.Num());
	for (const TPair<int32, AstraSpace::FMotion>& KV : Motions)
	{
		const AstraSpace::FMotion& M = KV.Value;
		const FAstraBattleShip* S = Owner ? Owner->FindById(M.ShipId) : nullptr;
		int32 Lit = 0;
		for (float B : M.Burn)
		{
			Lit += B > 0.1f ? 1 : 0;
		}
		const AstraSpace::FDemand D = AstraSpace::DemandOf(M);
		Out += FString::Printf(TEXT("\n  %-5s %-10s %-18s %5.0f m/s  turn %.1f deg/s  kick (%+.2f %+.2f %+.2f)  push (%+.2f %+.2f %+.2f)  jets %d/%d peak %.2f  wake %d notes%s"),
		                       S ? *S->ContactId : TEXT("-"), M.Class ? *M.Class->Key.ToString() : TEXT("?"), S ? *S->Name.Left(18) : TEXT("(gone)"), M.PrevVel.Size(),
		                       FMath::RadiansToDegrees(M.PrevOmega.Size()), M.Kick.X, M.Kick.Y, M.Kick.Z, D.Push.X, D.Push.Y, D.Push.Z, Lit, M.Burn.Num(), M.Peak, M.Wake.Num,
		                       M.bPowered ? TEXT("") : TEXT("  (no power)"));
	}
	return Out;
}

bool UAstraSpaceLife::DebugJets(const FString& Which, const FString& What, float Seconds, FString& OutDetail)
{
	if (!Owner || Owner->Ships.Num() == 0 || !bLaidOut)
	{
		OutDetail = TEXT("no living space laid out here");
		return false;
	}
	const AstraSpace::FJetData& Data = AstraSpace::JetData();
	if (!Data.bLoaded || CVarMoMotion.GetValueOnGameThread() == 0)
	{
		OutDetail = TEXT("the motion is off (astra.space.motion) or its data is missing (data/space/thrusters.json)");
		return false;
	}
	FAstraBattleShip* Pick = nullptr;
	if (Which.Equals(TEXT("nearest"), ESearchCase::IgnoreCase))
	{
		double Best = 1e18;
		for (FAstraBattleShip& S : Owner->Ships)
		{
			if (&S == &Owner->Ships[0] || !S.bAlive || S.bCraft || S.bFixture || S.bGhost || !Data.Find(S.ClassKey))
			{
				continue;
			}
			const double D = FVector::DistSquared(S.Pos, Owner->Ships[0].Pos);
			if (D < Best)
			{
				Best = D;
				Pick = &S;
			}
		}
		if (!Pick)
		{
			Pick = &Owner->Ships[0];
		}
	}
	else
	{
		for (FAstraBattleShip& S : Owner->Ships)
		{
			if (S.bAlive && !S.bCraft && !S.bFixture && Data.Find(S.ClassKey) && (S.ContactId.Equals(Which, ESearchCase::IgnoreCase) || S.ClassKey.ToString().Equals(Which, ESearchCase::IgnoreCase) || S.Name.Contains(Which, ESearchCase::IgnoreCase)))
			{
				Pick = &S;
				break;
			}
		}
	}
	if (!Pick)
	{
		OutDetail = FString::Printf(TEXT("no warship called %s (a contact id, a class key, a name, or nearest)"), *Which);
		return false;
	}
	const AstraSpace::FJetClass* C = Data.Find(Pick->ClassKey);
	AstraSpace::FMotion& M = Motions.FindOrAdd(Pick->Id);
	M.Bind(C);
	AstraSpace::FDemand D;
	bool bAll = false;
	if (What.Equals(TEXT("yaw+"))) { D.Turn.Z = 1.0; }
	else if (What.Equals(TEXT("yaw-"))) { D.Turn.Z = -1.0; }
	else if (What.Equals(TEXT("pitch+"))) { D.Turn.Y = 1.0; }
	else if (What.Equals(TEXT("pitch-"))) { D.Turn.Y = -1.0; }
	else if (What.Equals(TEXT("roll+"))) { D.Turn.X = 1.0; }
	else if (What.Equals(TEXT("roll-"))) { D.Turn.X = -1.0; }
	else if (What.Equals(TEXT("brake"))) { D.Push.X = -1.0; }
	else if (What.Equals(TEXT("right"))) { D.Push.Y = 1.0; }
	else if (What.Equals(TEXT("left"))) { D.Push.Y = -1.0; }
	else if (What.Equals(TEXT("up"))) { D.Push.Z = 1.0; }
	else if (What.Equals(TEXT("down"))) { D.Push.Z = -1.0; }
	else if (What.Equals(TEXT("all"))) { bAll = true; }
	else
	{
		OutDetail = TEXT("what? yaw+ yaw- pitch+ pitch- roll+ roll- brake left right up down all");
		return false;
	}
	M.Test = D;
	M.bTestAll = bAll;
	M.TestLeft = FMath::Clamp(Seconds, 0.5f, 120.f);
	OutDetail = FString::Printf(TEXT("%s (%s, %s) fires %s for %.0f s: %d nozzles in the class's table"), *Pick->Name, *Pick->ContactId, *Pick->ClassKey.ToString(), *What, M.TestLeft, C->Jets.Num());
	return true;
}

// ------------------------------------------------------------------------------------------------------------------ the console
namespace
{
	FAutoConsoleCommandWithWorld CmdSpaceMotion(TEXT("astra.space.motion.list"), TEXT("What the capital ships' motion asks of their jets right now, ship by ship, and what the wakes hold"),
		FConsoleCommandWithWorldDelegate::CreateLambda([](UWorld* W)
		{
			UAstraBattleSubsystem* B = W ? W->GetSubsystem<UAstraBattleSubsystem>() : nullptr;
			UAstraSpaceLife* S = B ? B->GetSpace() : nullptr;
			if (!S) { UE_LOG(LogASTRA, Display, TEXT("[Space] none in this world")); return; }
			UE_LOG(LogASTRA, Display, TEXT("[Space] %s"), *S->MotionTable());
			UE_LOG(LogASTRA, Display, TEXT("[Space] %s"), *S->MotionStat());
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdSpaceJets(TEXT("astra.space.jets"), TEXT("Fire a warship's manoeuvring jets by hand, to see where they are: astra.space.jets <contact id | class | nearest> <yaw+|yaw-|pitch+|pitch-|roll+|roll-|brake|left|right|up|down|all> [seconds, default 8]"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& A, UWorld* W)
		{
			UAstraBattleSubsystem* B = W ? W->GetSubsystem<UAstraBattleSubsystem>() : nullptr;
			UAstraSpaceLife* S = B ? B->GetSpace() : nullptr;
			if (!S || A.Num() < 2) { UE_LOG(LogASTRA, Display, TEXT("[Space] astra.space.jets <contact id | class | nearest> <yaw+|yaw-|pitch+|pitch-|roll+|roll-|brake|left|right|up|down|all> [seconds]")); return; }
			FString Detail;
			S->DebugJets(A[0], A[1], A.Num() > 2 ? (float)FCString::Atod(*A[2]) : 8.f, Detail);
			UE_LOG(LogASTRA, Display, TEXT("[Space] %s"), *Detail);
		}));
}
