// ASTRA — the war's visual effects on the hulls: scars, fires and venting, the lights going out, the pieces of a broken ship, the shields'
// shells, the drives' plumes, and where on a hull a gun or a fire is.

#include "AstraWarFX.h"
#include "AstraBattleSubsystem.h"
#include "ASTRA.h"
#include "AstraFleetInterior.h"
#include "Components/DecalComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "Materials/MaterialInstanceDynamic.h"

using namespace AstraFx;

// ------------------------------------------------------------------------------------------------------------------ the data table
namespace AstraFx
{
	struct FBell { float X, Y, Z, R, Lip; };
	struct FCutFace { int32 Piece; float X, NormalX, Cy, Cz, HalfY, HalfZ; };
	struct FPieceInfo { float Px, Py, Pz, X0, X1; };
	struct FShipTable
	{
		const TCHAR* Mesh;
		int32 NumBells;
		FBell Bells[8];
		bool bPieces;
		FPieceInfo Pieces[3];
		int32 NumFaces;
		FCutFace Faces[4];
	};

	static const FShipTable GShipTables[] =
#include "AstraWarFXData.inl"
	;

	const FShipTable* FindTable(const FString& MeshName)
	{
		for (const FShipTable& T : GShipTables)
		{
			if (MeshName.Equals(T.Mesh))
			{
				return &T;
			}
		}
		return nullptr;
	}
}

namespace
{
	/** The mesh a ship is drawn with (the Aquila's is the level's, not the battle's). */
	FString FxMeshOf(const FAstraBattleShip& S)
	{
		if (!S.Mesh.IsEmpty())
		{
			return S.Mesh;
		}
		return S.ClassKey == FName(TEXT("aquila")) ? FString(TEXT("SM_SHIP_ASTRA_Aquila")) : FString();
	}

	uint32 FxHash(uint32 A, uint32 B)
	{
		uint32 H = A * 0x9E3779B1u ^ (B + 0x7F4A7C15u + (A << 6) + (A >> 2));
		H ^= H >> 15; H *= 0x2C1B3C6Du; H ^= H >> 12; H *= 0x297A2D39u; H ^= H >> 15;
		return H;
	}
}

// ------------------------------------------------------------------------------------------------------------------ where on a hull
FVector UAstraWarFX::HullPoint(const FAstraBattleShip& S, int32 Section, float Along, float SideA, float SideB, bool bSurface) const
{
	if (!S.Box.Valid())
	{
		return S.Pos + FMath::VRand() * S.Radius * 0.5f;
	}
	const float Mid = S.Box.Mid, Hx = S.Box.Hx;
	float X0 = Mid - Hx, X1 = Mid + Hx;
	const float Bow = S.Box.CutBow, Stern = S.Box.CutStern;
	if (Bow != 0.f || Stern != 0.f)
	{
		if (Section == AstraWar::SecBow) { X0 = Bow; }
		else if (Section == AstraWar::SecStern) { X1 = Stern; }
		else { X0 = Stern; X1 = Bow; }
	}
	else
	{
		const float Third = 2.f * Hx / 3.f;
		X0 = Mid - Hx + Third * (2 - Section);
		X1 = X0 + Third;
	}
	const float X = FMath::Lerp(X0, X1, FMath::Clamp(Along, 0.f, 1.f));
	const float Sh = bSurface ? 0.96f : 0.5f;
	FVector L;
	if (SideB >= 0.999f)
	{
		L = FVector(X, SideA * S.Box.Hy * 0.8f, S.Box.Hz * Sh);          // the upper hull
	}
	else if (SideB <= -0.999f)
	{
		L = FVector(X, SideA * S.Box.Hy * 0.8f, -S.Box.Hz * Sh);         // the keel
	}
	else
	{
		L = FVector(X, (SideA >= 0.f ? 1.f : -1.f) * S.Box.Hy * Sh, SideB * S.Box.Hz * 0.8f);   // a flank
	}
	return S.Pos + S.Att.RotateVector(L);
}

FVector UAstraWarFX::MuzzleOf(const FAstraBattleShip& S, EAstraMountKind Kind, const FVector& AimDir, int32 Salt)
{
	if (!S.Box.Valid() || S.Mounts.Num() == 0 || AimDir.IsNearlyZero())
	{
		return S.Pos + AimDir * (S.Radius * 0.5f);
	}
	const FVector LocalAim = S.Att.UnrotateVector(AimDir).GetSafeNormal();
	// a mount of this kind whose field of fire holds the aim, in turn; else the one that points nearest to it
	int32 Picks[24];
	int32 N = 0;
	int32 Nearest = INDEX_NONE;
	float NearestDot = -2.f;
	for (int32 i = 0; i < S.Mounts.Num(); ++i)
	{
		const FAstraMount& M = S.Mounts[i];
		if (M.Kind != Kind)
		{
			continue;
		}
		const float Dot = FVector::DotProduct(M.Dir, LocalAim);
		if (Dot > NearestDot)
		{
			NearestDot = Dot;
			Nearest = i;
		}
		if (M.CanBear(LocalAim) && N < 24)
		{
			Picks[N++] = i;
		}
	}
	int32 Idx = Nearest;
	if (N > 0)
	{
		Idx = Picks[(NextMount[(int32)Kind] + (uint32)Salt) % (uint32)N];
		++NextMount[(int32)Kind];
	}
	if (Idx == INDEX_NONE)
	{
		return S.Pos + AimDir * (S.Radius * 0.5f);
	}
	const FAstraMount& M = S.Mounts[Idx];
	// the gun stands in its section, on the hull: a ray from the axis there along the aim leaves the box where the gun is
	const float Mid = S.Box.Mid, Hx = S.Box.Hx;
	float X0 = Mid - Hx, X1 = Mid + Hx;
	if (S.Box.CutBow != 0.f || S.Box.CutStern != 0.f)
	{
		if (M.Section == AstraWar::SecBow) { X0 = S.Box.CutBow; }
		else if (M.Section == AstraWar::SecStern) { X1 = S.Box.CutStern; }
		else { X0 = S.Box.CutStern; X1 = S.Box.CutBow; }
	}
	FRandomStream Rs((int32)FxHash((uint32)S.Id, (uint32)Idx));
	const FVector O(FMath::Lerp(X0, X1, Rs.FRandRange(0.12f, 0.88f)) - Mid, Rs.FRandRange(-0.3f, 0.3f) * S.Box.Hy, Rs.FRandRange(-0.2f, 0.2f) * S.Box.Hz);
	double Tmax = 1.0e9;
	const double H[3] = {(double)S.Box.Hx, (double)S.Box.Hy, (double)S.Box.Hz};
	for (int32 a = 0; a < 3; ++a)
	{
		const double D = LocalAim[a];
		if (FMath::Abs(D) > 1e-6)
		{
			Tmax = FMath::Min(Tmax, ((D > 0.0 ? H[a] : -H[a]) - O[a]) / D);
		}
	}
	const FVector Local = O + LocalAim * FMath::Clamp(Tmax, 0.0, 2.0 * (double)S.Radius) + FVector(Mid, 0.f, 0.f);
	return S.Pos + S.Att.RotateVector(Local);
}

// ------------------------------------------------------------------------------------------------------------------ scars
void UAstraWarFX::AddScar(const FAstraBattleShip& S, const FAstraFxHit& H)
{
	UWorld* World = Owner ? Owner->GetWorld() : nullptr;
	if (!bLive || !World || DamageMats.Num() < 8)
	{
		return;
	}
	static int32 ThisFrame = -1, Made = 0;
	if (ThisFrame != Frame)
	{
		ThisFrame = Frame;
		Made = 0;
	}
	if (Made >= 3)
	{
		return;                                // a salvo's worth in one frame is plenty
	}
	// which scar: by what did it, and how hard
	int32 Kind;
	switch (H.Kind)
	{
	case EAstraHitKind::Laser:
	case EAstraHitKind::PointDefence:
		Kind = FMath::RandBool() ? 0 : 5;      // burn, melt
		break;
	case EAstraHitKind::Cannon:
		Kind = 4;                              // strafe
		break;
	case EAstraHitKind::Missile:
	case EAstraHitKind::Torpedo:
	case EAstraHitKind::Rocket:
		Kind = H.Felt > 90.f ? 1 : 7;          // hole, blast
		break;
	default:
		Kind = H.Felt > 70.f ? 2 : (FMath::RandBool() ? 3 : 6);   // torn, impact, gouge
		break;
	}
	UMaterialInterface* Mat = DamageMats[Kind];
	if (!Mat)
	{
		return;
	}
	const FVector W = F.ToWorld(H.Pos);
	AActor* On = nullptr;
	FVector Loc, N;
	float HalfDepth = 3000.f;                                   // cm: it reaches 30 m each way along its axis
	if (S.bPlayer)
	{
		// the Aquila's hull is the level's, with its collision: from outside the hit, in towards her keel line, to the plating it struck
		AActor* Hull = AquilaHull.Get();
		if (!Hull)
		{
			for (TActorIterator<AStaticMeshActor> It(World); It; ++It)
			{
				const UStaticMeshComponent* C = It->GetStaticMeshComponent();
				if (C && C->GetStaticMesh() && C->GetStaticMesh()->GetName() == TEXT("SM_SHIP_ASTRA_Aquila") && !It->ActorHasTag(TEXT("ASTRA.Interior")))
				{
					Hull = *It;
					AquilaHull = Hull;
					break;
				}
			}
		}
		if (!Hull)
		{
			return;
		}
		FVector C, E;
		Hull->GetActorBounds(false, C, E);
		const FVector Axis(FMath::Clamp(W.X, C.X - E.X, C.X + E.X), C.Y, C.Z);
		const FVector Out = (W - Axis).GetSafeNormal();
		FHitResult Hit;
		FCollisionQueryParams Q(SCENE_QUERY_STAT(AstraFxScar), true);
		const FVector From = Axis + Out * (E.Y + E.Z + 5000.f);
		if (Out.IsNearlyZero() || !World->LineTraceSingleByChannel(Hit, From, Axis, ECC_Visibility, Q) || !Hit.GetActor())
		{
			return;
		}
		On = Hit.GetActor();
		Loc = Hit.ImpactPoint;
		N = Hit.ImpactNormal;
	}
	else
	{
		On = S.Actor;
		if (!On)
		{
			return;
		}
		// the scar goes where the blow struck the hull box, along the face's normal, reaching 30 m in
		N = F.DirToWorld(S.Att.RotateVector(AstraWar::FacingVector(H.Facing)));
		Loc = W;
	}
	FShipFx& Fx = ShipOf(S.Id);
	const int32 MaxHere = 8 + 4 * FMath::Clamp((int32)S.SizeTier, 0, 3);
	if (Fx.Scars >= MaxHere)
	{
		// the oldest of this hull goes
		for (int32 i = 0; i < Scars.Num(); ++i)
		{
			if (Scars[i].On.Get() == On)
			{
				if (UDecalComponent* D = Scars[i].Decal.Get())
				{
					D->DestroyComponent();
				}
				Scars.RemoveAt(i);
				--Fx.Scars;
				break;
			}
		}
	}
	if (Scars.Num() >= 150)
	{
		if (UDecalComponent* D = Scars[0].Decal.Get())
		{
			D->DestroyComponent();
		}
		Scars.RemoveAt(0);
	}
	UDecalComponent* D = NewObject<UDecalComponent>(On);
	D->SetupAttachment(On->GetRootComponent());
	D->SetUsingAbsoluteScale(true);
	D->RegisterComponent();
	UMaterialInstanceDynamic* M = UMaterialInstanceDynamic::Create(Mat, D);
	M->SetScalarParameterValue(TEXT("Heat"), 1.f);
	M->SetScalarParameterValue(TEXT("Fade"), 1.f);
	D->SetDecalMaterial(M);
	const float Half = FMath::Clamp(3.5f + 0.9f * FMath::Sqrt(FMath::Max(H.Felt, 1.f)), 4.f, 26.f) * 100.f;   // 8-52 m across
	D->DecalSize = FVector(HalfDepth, Half, Half);
	FRotator R = FRotationMatrix::MakeFromX(-N).Rotator();                        // it projects along X, into the plating
	R.Roll = FMath::FRandRange(0.f, 360.f);
	D->SetWorldLocationAndRotation(Loc + N * 500.f, R);
	D->SetFadeScreenSize(0.0003f);
	FScar X;
	X.Decal = D;
	X.Mid = M;
	X.On = On;
	Scars.Add(X);
	++Fx.Scars;
	++Made;
}

void UAstraWarFX::TickScars()
{
	for (int32 i = Scars.Num() - 1; i >= 0; --i)
	{
		FScar& X = Scars[i];
		if (!X.Decal.IsValid() || !X.Mid.IsValid() || !X.On.IsValid())
		{
			Scars.RemoveAtSwap(i, EAllowShrinking::No);
			continue;
		}
		X.Heat = FMath::Max(0.f, X.Heat - Dt / 50.f);                           // the embers die in under a minute
		if (FMath::Abs(X.Heat - X.Shown) > 0.02f)
		{
			X.Shown = X.Heat;
			X.Mid->SetScalarParameterValue(TEXT("Heat"), X.Heat);
		}
	}
}

// ------------------------------------------------------------------------------------------------------------------ ships, each frame
float UAstraWarFX::Throttle(const FAstraBattleShip& S) const
{
	const FShipFx* Fx = ShipFx.Find(S.Id);
	return Fx ? Fx->Thrust : 0.15f;
}

void UAstraWarFX::TickShips()
{
	const float Now = Owner->Time;
	for (FAstraBattleShip& S : Owner->Ships)
	{
		if (!S.bAlive || S.bGhost)
		{
			continue;
		}
		FShipFx& Fx = ShipOf(S.Id);
		// how hard the drive works: the acceleration along the heading over what the engines can do, smoothed; a ship under way keeps a cruise burn
		const float SimDt = Now - Fx.PrevTime;
		if (Fx.PrevTime >= 0.f && SimDt > 1.e-3f)
		{
			const float Accel = (float)FVector::DotProduct(S.Vel - Fx.PrevVel, S.Att.GetForwardVector()) / SimDt;
			const float Max = FMath::Max(1.f, S.MaxAccel * Owner->EngineFactor(S));
			float Want = FMath::Clamp(Accel / Max, 0.f, 1.f);
			if (S.Vel.SizeSquared() > 400.0 && !S.bDisabled)
			{
				Want = FMath::Max(Want, 0.16f);
			}
			Fx.Thrust += (Want - Fx.Thrust) * (1.f - FMath::Exp(-6.f * Dt));
		}
		Fx.PrevVel = S.Vel;
		Fx.PrevTime = Now;
		if (S.bCraft)
		{
			continue;
		}
		if (S.bDisabled)
		{
			PowerDown(S, Fx);
			Fx.Thrust = 0.f;
		}
		if (S.Dmg.bModel)
		{
			HullEmitters(S, Fx);
		}
	}
}

void UAstraWarFX::HullEmitters(const FAstraBattleShip& S, FShipFx& Fx)
{
	const FAstraShipDamage& D = S.Dmg;
	const double Dist2 = FVector::DistSquared(S.Pos, F.Origin);
	if (Dist2 > FMath::Square(160000.0))
	{
		return;
	}
	const bool bNear = Dist2 < FMath::Square(60000.0);
	const float SizeK = FMath::Clamp(S.Radius / 150.f, 0.5f, 3.2f);
	const bool bAstra = S.Side == EAstraSide::Astra;
	const float K = FMath::Clamp(Density, 0.2f, 2.f);
	if (S.Interior.IsValid())
	{
		FleetFxRefresh(S, Fx);                                                  // (a ship with an inside burns and vents where its rooms do)
	}
	for (int32 sec = 0; sec < AstraWar::NumSections; ++sec)
	{
		const bool bGut = D.GuttedT[sec] >= 0.f;
		const bool bBurn = D.Burn[sec] > 0.f || bGut;
		const bool bVent = D.Breach[sec] > 0.f;
		if (!bBurn && !bVent)
		{
			continue;
		}
		if (bBurn)
		{
			Fx.Emit[sec] += Dt * ((D.Burn[sec] > 0.f ? 2.4f : 0.f) + (bGut ? 4.5f : 0.f)) * FMath::Sqrt(SizeK) * K * Room(LFire);
			while (Fx.Emit[sec] >= 1.f)
			{
				Fx.Emit[sec] -= 1.f;
				const FVector Pt = Fx.InFire[sec].Num() ? FleetFxPoint(S, Fx.InFire[sec]) : HullPoint(S, sec, FMath::FRand(), FMath::FRandRange(-1.f, 1.f), FMath::RandBool() ? 1.f : FMath::FRandRange(-0.6f, 0.6f), true);
				const FVector Out = (Pt - S.Pos).GetSafeNormal();
				const float R0 = 2.4f * SizeK;
				if (FPuff* P = AddPuff(Pt, S.Vel + Out * FMath::FRandRange(3.f, 9.f), FMath::FRandRange(0.8f, 1.6f), R0, R0 * FMath::FRandRange(2.2f, 3.4f),
				                        FLinearColor(1.f, 0.55f, 0.2f), 150.f, LFire))
				{
					P->P1 = FMath::FRand();
				}
				if (bNear && FMath::FRand() < 0.5f)
				{
					Smoke(Pt, S.Vel + Out * 4.f, R0 * 2.2f, FMath::FRandRange(4.f, 8.f), 0.9f);
				}
				if (FMath::FRand() < 0.12f)
				{
					AddLight(Pt, 0.5f, 220.f * SizeK, 2.2e5f * SizeK * SizeK, FLinearColor(1.f, 0.55f, 0.25f), S.Vel);
				}
			}
		}
		// a section that burns blows up now and then (one that is gutted, often): a small blast inside the hull, so a ship in flames is never quiet
		if (bNear && (bGut || D.Burn[sec] > 8.f) && Room(LFire) > 0.25f)
		{
			Fx.BlastT[sec] -= Dt * K;
			if (Fx.BlastT[sec] <= 0.f)
			{
				Fx.BlastT[sec] = bGut ? FMath::FRandRange(2.5f, 7.f) : FMath::FRandRange(7.f, 16.f);
				const FVector Pt = Fx.InFire[sec].Num() ? FleetFxPoint(S, Fx.InFire[sec]) : HullPoint(S, sec, FMath::FRand(), FMath::FRandRange(-0.8f, 0.8f), FMath::RandBool() ? 1.f : FMath::FRandRange(-0.6f, 0.6f), true);
				Explosion(Pt, S.Vel, FMath::Clamp(S.Radius * FMath::FRandRange(0.035f, 0.07f), 4.f, 40.f), bAstra, bGut ? 0.38f : 0.25f, 0.f);
			}
		}
		if (bVent)
		{
			Fx.EmitVent[sec] += Dt * 14.f * K * Room(LGlow);
			while (Fx.EmitVent[sec] >= 1.f)
			{
				Fx.EmitVent[sec] -= 1.f;
				const FVector Pt = Fx.InVent[sec].Num() ? FleetFxPoint(S, Fx.InVent[sec]) : HullPoint(S, sec, FMath::FRand(), FMath::FRandRange(-1.f, 1.f), FMath::RandBool() ? 1.f : FMath::FRandRange(-0.6f, 0.6f), true);
				const FVector Out = (Pt - S.Pos).GetSafeNormal();
				if (FPuff* P = AddPuff(Pt, S.Vel + (Out + FMath::VRand() * 0.15f) * FMath::FRandRange(55.f, 95.f), FMath::FRandRange(0.5f, 0.95f), 1.2f * FMath::Sqrt(SizeK),
				                        4.6f * FMath::Sqrt(SizeK), bAstra ? FLinearColor(0.78f, 0.88f, 1.f) : FLinearColor(1.f, 0.9f, 0.78f), 60.f, LGlow))
				{
					P->P1 = 0.f;
				}
			}
		}
	}
	// the hull coming apart: blasts inside it, quicker and quicker, until it goes
	if (D.bBreakingUp && D.BreakupT > 0.f)
	{
		Fx.BreakBlast -= Dt;
		if (Fx.BreakBlast <= 0.f)
		{
			Fx.BreakBlast = FMath::FRandRange(0.35f, 0.9f) * FMath::Clamp(D.BreakupT / 4.f, 0.35f, 1.5f);
			const FVector Pt = HullPoint(S, D.BreakSection, FMath::FRand(), FMath::FRandRange(-1.f, 1.f), FMath::RandBool() ? 1.f : FMath::FRandRange(-0.6f, 0.6f), false);
			Explosion(Pt, S.Vel, S.Radius * FMath::FRandRange(0.07f, 0.16f), bAstra, 0.5f, 0.f);
		}
	}
}

void UAstraWarFX::FleetFxRefresh(const FAstraBattleShip& S, FShipFx& Fx)
{
	Fx.InT -= Dt;
	if (Fx.InT > 0.f)
	{
		return;
	}
	Fx.InT = 0.4f;
	FFleetFxPoints P;
	S.Interior->FxPoints(P);
	for (int32 sec = 0; sec < 3; ++sec)
	{
		Fx.InFire[sec] = MoveTemp(P.Fire[sec]);
		Fx.InVent[sec] = MoveTemp(P.Vent[sec]);
	}
	// the windows of the rooms that lost their power go dark (the lights' material has one global fraction: a disabled ship's lights are PowerDown's)
	if (!S.bDisabled && bLive && S.Actor && FMath::Abs(P.Lit - Fx.InLit) > 0.02f)
	{
		Fx.InLit = P.Lit;
		if (!Fx.LightsMid.IsValid())
		{
			if (UStaticMeshComponent* C = S.Actor->GetStaticMeshComponent())
			{
				const TCHAR Fac = S.Side == EAstraSide::Mandate ? TEXT('M') : (S.Side == EAstraSide::Astra ? TEXT('A') : TEXT('G'));
				const int32 Slot = C->GetMaterialIndex(*FString::Printf(TEXT("MI_HULL_%c_Lights"), Fac));
				if (Slot != INDEX_NONE)
				{
					Fx.LightsMid = C->CreateDynamicMaterialInstance(Slot);
				}
			}
		}
		if (UMaterialInstanceDynamic* M = Fx.LightsMid.Get())
		{
			M->SetScalarParameterValue(TEXT("LitFraction"), 0.65f * P.Lit);         // (0.65 is the windows fully lit, as PowerDown's)
		}
	}
}

FVector UAstraWarFX::FleetFxPoint(const FAstraBattleShip& S, const TArray<FVector>& Points) const
{
	const FVector P = Points[FMath::RandHelper(Points.Num())];                      // the hull's frame (m): the mesh's own, about the ship's position
	if (!S.Box.Valid())
	{
		return S.Pos + S.Att.RotateVector(P);
	}
	// it shows on the face of the hull's box it lies nearest (a fire deep in the hull is seen through the plating on the side it is nearest); the ends only for what lies at them
	const FVector R((P.X - S.Box.Mid) / S.Box.Hx, P.Y / S.Box.Hy, P.Z / S.Box.Hz);
	const FVector A = R.GetAbs();
	FVector L = P;
	if (A.X > 0.85 && A.X >= A.Y && A.X >= A.Z)
	{
		L.X = S.Box.Mid + (R.X >= 0.0 ? 1.0 : -1.0) * S.Box.Hx * 0.96;
	}
	else if (A.Y > A.Z)
	{
		L.Y = (R.Y >= 0.0 ? 1.0 : -1.0) * S.Box.Hy * 0.96;
	}
	else
	{
		L.Z = (R.Z >= 0.0 ? 1.0 : -1.0) * S.Box.Hz * 0.96;
	}
	L += FMath::VRand() * (S.Radius * 0.012f);
	return S.Pos + S.Att.RotateVector(L);
}

void UAstraWarFX::PowerDown(const FAstraBattleShip& S, FShipFx& Fx)
{
	// a ship with no power: the windows and the lamps go out (with a stutter), the drive dies
	Fx.DarkT += Dt;
	if (!bLive || !S.Actor || (Fx.bDark && Fx.DarkT > 4.f))
	{
		return;
	}
	UStaticMeshComponent* C = S.Actor->GetStaticMeshComponent();
	if (!C)
	{
		return;
	}
	if (!Fx.bDark)
	{
		Fx.bDark = true;
		const TCHAR Fac = S.Side == EAstraSide::Mandate ? TEXT('M') : (S.Side == EAstraSide::Astra ? TEXT('A') : TEXT('G'));
		const int32 Slot = C->GetMaterialIndex(*FString::Printf(TEXT("MI_HULL_%c_Lights"), Fac));
		if (Slot != INDEX_NONE)
		{
			Fx.LightsMid = C->CreateDynamicMaterialInstance(Slot);
		}
		for (const TCHAR* Part : {TEXT("Nav"), TEXT("Glow")})
		{
			const int32 Sl = C->GetMaterialIndex(*FString::Printf(TEXT("MI_HULL_%c_%s"), Fac, Part));
			if (Sl != INDEX_NONE)
			{
				if (UMaterialInstanceDynamic* M = C->CreateDynamicMaterialInstance(Sl))
				{
					M->SetScalarParameterValue(TEXT("Intensity"), 0.f);
				}
			}
		}
		// the running lights: hidden (the lamps are the other components of the actor)
		TInlineComponentArray<UStaticMeshComponent*> Comps;
		S.Actor->GetComponents(Comps);
		for (UStaticMeshComponent* Lamp : Comps)
		{
			if (Lamp != C)
			{
				Lamp->SetVisibility(false);
			}
		}
	}
	if (UMaterialInstanceDynamic* M = Fx.LightsMid.Get())
	{
		const float T = FMath::Clamp(Fx.DarkT / 3.5f, 0.f, 1.f);
		const float Stutter = FMath::FRand() < 0.35f ? 0.4f : 1.f;
		M->SetScalarParameterValue(TEXT("LitFraction"), 0.65f * (1.f - T) * Stutter);
	}
}

// ------------------------------------------------------------------------------------------------------------------ the pieces of a broken hull
bool UAstraWarFX::MakePieces(FAstraBattleShip& S, const FAstraDeathEvent& E, AActor* Hull, bool bReactor)
{
	const FString Mesh = FxMeshOf(S);
	const FShipTable* T = FindTable(Mesh);
	if (!T || !T->bPieces)
	{
		return false;
	}
	UWorld* World = Owner->GetWorld();
	static const TCHAR* const Names[3] = {TEXT("Bow"), TEXT("Mid"), TEXT("Stern")};
	UStaticMesh* Meshes[3] = {nullptr, nullptr, nullptr};
	if (bLive)
	{
		for (int32 i = 0; i < 3; ++i)
		{
			Meshes[i] = LoadObject<UStaticMesh>(nullptr, *FString::Printf(TEXT("/Game/ASTRA/Ships/Sections/%s_Sec%s.%s_Sec%s"), *Mesh, Names[i], *Mesh, Names[i]));
			if (!Meshes[i])
			{
				UE_LOG(LogASTRA, Warning, TEXT("[WarFX] no piece mesh for %s (%s): the old wreck is used"), *Mesh, Names[i]);
				return false;
			}
		}
	}
	const FVector Axis = S.Att.GetForwardVector();
	const FVector Centre = S.Pos + S.Att.RotateVector(FVector(S.Box.Valid() ? S.Box.Mid : 0.f, 0.f, 0.f));
	const float Len[3] = {T->Pieces[0].X1 - T->Pieces[0].X0, T->Pieces[1].X1 - T->Pieces[1].X0, T->Pieces[2].X1 - T->Pieces[2].X0};
	const float SpeedSplit = FMath::Max(E.BreakSpeed, 6.f);
	// momentum: the two groups that part (a section lets go: it against the rest) leave in proportion to the mass of the other
	float Vx[3] = {0.f, 0.f, 0.f};
	if (!bReactor)
	{
		const int32 Sec = FMath::Clamp((int32)E.Section, 0, 2);
		if (Sec == AstraWar::SecBow)
		{
			const float Mf = Len[0], Ma = Len[1] + Len[2];
			Vx[0] = SpeedSplit * Ma / (Mf + Ma);
			Vx[1] = Vx[2] = -SpeedSplit * Mf / (Mf + Ma);
		}
		else if (Sec == AstraWar::SecStern)
		{
			const float Mf = Len[0] + Len[1], Ma = Len[2];
			Vx[0] = Vx[1] = SpeedSplit * Ma / (Mf + Ma);
			Vx[2] = -SpeedSplit * Mf / (Mf + Ma);
		}
		else
		{
			Vx[0] = 0.5f * SpeedSplit;                 // the middle of the ship went: the ends part from it
			Vx[2] = -0.5f * SpeedSplit;
			Vx[1] = 0.f;
		}
	}
	FActorSpawnParameters SP;
	SP.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	if (Pieces.Num() + 3 > CapPieces)
	{
		// the oldest broken hulls go (their obstacles stay in the war's own list)
		for (int32 k = 0; k < 3 && Pieces.Num(); ++k)
		{
			if (AStaticMeshActor* A = Pieces[0].Actor.Get())
			{
				A->Destroy();
			}
			if (AActor* H = Pieces[0].HullActor.Get())
			{
				H->Destroy();
			}
			Pieces.RemoveAt(0);
		}
	}
	const TCHAR Fac = S.Side == EAstraSide::Mandate ? TEXT('M') : (S.Side == EAstraSide::Astra ? TEXT('A') : TEXT('G'));
	int32 Leader = INDEX_NONE;                 // the piece that holds the whole hull for the viewscreen
	for (int32 i = 0; i < 3; ++i)
	{
		FPiece P;
		P.ShipId = S.Id;
		P.Section = (uint8)i;
		P.Table = T;
		P.bAstra = S.Side == EAstraSide::Astra;
		P.bReactor = bReactor;
		P.Radius = FMath::Max(Len[i] * 0.45f, 10.f);
		P.Origin = S.Pos;
		P.Att = S.Att;
		P.PivotLocal = FVector(T->Pieces[i].Px, T->Pieces[i].Py, T->Pieces[i].Pz);
		P.Pivot = S.Pos + S.Att.RotateVector(P.PivotLocal);
		P.Vel = S.Vel + Axis * Vx[i];
		if (bReactor)
		{
			// thrown out of the fireball, away from the reactor
			const FVector Away = (P.Pivot - Centre).GetSafeNormal() + FMath::VRand() * 0.35f;
			P.Vel += Away.GetSafeNormal() * FMath::FRandRange(28.f, 85.f);
			P.SpinRate = FMath::FRandRange(0.03f, 0.12f);
		}
		else
		{
			P.Vel += FMath::VRand() * 1.5f;
			P.SpinRate = FMath::FRandRange(0.008f, 0.05f) * (i == (int32)E.Section ? 2.f : 1.f);
		}
		P.SpinAxis = FVector::CrossProduct(Axis, FMath::VRand()).GetSafeNormal();
		if (P.SpinAxis.IsNearlyZero())
		{
			P.SpinAxis = S.Att.GetUpVector();
		}
		P.FaceFirst = 0;
		P.FaceCount = T->NumFaces;
		if (bLive)
		{
			AStaticMeshActor* A = World->SpawnActor<AStaticMeshActor>(S.Pos, S.Att.Rotator(), SP);
			if (!A)
			{
				continue;
			}
			A->SetMobility(EComponentMobility::Movable);
			UStaticMeshComponent* C = A->GetStaticMeshComponent();
			C->SetStaticMesh(Meshes[i]);
			C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
			C->SetCastShadow(false);
			C->bAffectDynamicIndirectLighting = false;
			C->SetLightingChannels(true, true, false);
			A->SetActorLocationAndRotation(F.ToWorld(S.Pos), F.ToWorldRot(S.Att));
			A->Tags.Add(TEXT("ASTRA.Sky"));
			P.Actor = A;
			if (Hull)
			{
				C->SetHiddenInSceneCapture(true);          // (the viewscreen has not got this actor yet: it goes on with the whole hull, see FPiece::Hold)
				P.Hold = 0.75f;
			}
			// the burnt faces start hot and cool; the windows go out
			const int32 CutSlot = C->GetMaterialIndex(*FString::Printf(TEXT("MI_HULL_%c_Cut"), Fac));
			if (CutSlot != INDEX_NONE)
			{
				P.CutMid = C->CreateDynamicMaterialInstance(CutSlot);
				if (UMaterialInstanceDynamic* M = P.CutMid.Get())
				{
					M->SetScalarParameterValue(TEXT("Heat"), 1.f);
				}
			}
			const int32 LitSlot = C->GetMaterialIndex(*FString::Printf(TEXT("MI_HULL_%c_Lights"), Fac));
			if (LitSlot != INDEX_NONE)
			{
				P.LitMid = C->CreateDynamicMaterialInstance(LitSlot);
			}
			if (bReactor)
			{
				// charred by the blast
				for (const TCHAR* Part : {TEXT("Plate"), TEXT("Frame"), TEXT("Livery"), TEXT("Trim"), TEXT("Marking")})
				{
					const int32 Sl = C->GetMaterialIndex(*FString::Printf(TEXT("MI_HULL_%c_%s"), Fac, Part));
					if (Sl == INDEX_NONE)
					{
						continue;
					}
					if (UMaterialInstanceDynamic* M = C->CreateDynamicMaterialInstance(Sl))
					{
						FLinearColor Base(0.2f, 0.2f, 0.2f);
						M->GetVectorParameterValue(FHashedMaterialParameterInfo(TEXT("Tint")), Base);
						M->SetVectorParameterValue(TEXT("Tint"), Base * 0.18f);
						P.Chars.Add(M);
					}
				}
			}
		}
		const int32 Added = Pieces.Add(P);
		if (Leader == INDEX_NONE)
		{
			Leader = Added;
		}
		// the war's own list keeps each piece as the obstacle it is for the ships that steer round it
		FAstraWreck W;
		W.Pos = P.Pivot;
		W.Vel = P.Vel;
		W.Att = P.Att;
		W.Radius = P.Radius;
		Owner->Wrecks.Add(W);
	}
	if (bLive && Leader == INDEX_NONE)
	{
		return false;                          // no piece could be made: the old explosion (the hull is untouched)
	}
	// the whole ship leaves the bridge's eye in this frame (the pieces already stand where it was); the viewscreen sees it a moment longer
	if (Hull && bLive)
	{
		TInlineComponentArray<UPrimitiveComponent*> Prims;
		Hull->GetComponents(Prims);
		for (UPrimitiveComponent* C : Prims)
		{
			C->SetVisibleInSceneCaptureOnly(true);
		}
		FPiece& L = Pieces[Leader];
		L.HullActor = Hull;
		L.HullOrigin = S.Pos;
		L.HullVel = S.Vel;
		L.HullAtt = S.Att;
	}
	return true;
}

void UAstraWarFX::ReleasePiece(int32 ShipId, uint8 Section)
{
	for (int32 i = 0; i < Pieces.Num(); ++i)
	{
		FPiece& P = Pieces[i];
		if (P.ShipId != ShipId || P.Section != Section)
		{
			continue;
		}
		if (AStaticMeshActor* A = P.Actor.Get())
		{
			A->Destroy();
		}
		if (AActor* H = P.HullActor.Get())
		{
			H->Destroy();
		}
		Pieces.RemoveAtSwap(i, EAllowShrinking::No);
		return;
	}
}

void UAstraWarFX::TickPieces()
{
	const double Far2 = FMath::Square(250000.0);
	for (int32 i = Pieces.Num() - 1; i >= 0; --i)
	{
		FPiece& P = Pieces[i];
		if (bLive && !P.Actor.IsValid())
		{
			Pieces.RemoveAtSwap(i, EAllowShrinking::No);
			continue;
		}
		if (FVector::DistSquared(P.Pivot, F.Origin) > Far2)
		{
			if (AStaticMeshActor* A = P.Actor.Get())
			{
				A->Destroy();
			}
			if (AActor* H = P.HullActor.Get())
			{
				H->Destroy();
			}
			Pieces.RemoveAtSwap(i, EAllowShrinking::No);
			continue;
		}
		P.Age += Dt;
		if (P.Hold > 0.f)
		{
			// the viewscreen still shows the whole hull, on the path it had; when the time is up the pieces are shown to it too and the hull goes
			P.Hold -= Dt;
			if (P.Hold <= 0.f)
			{
				if (AStaticMeshActor* A = P.Actor.Get())
				{
					A->GetStaticMeshComponent()->SetHiddenInSceneCapture(false);
				}
				if (AActor* H = P.HullActor.Get())
				{
					H->Destroy();
				}
				P.HullActor.Reset();
			}
			else if (AActor* H = P.HullActor.Get())
			{
				P.HullOrigin += P.HullVel * Dt;
				H->SetActorLocationAndRotation(F.ToWorld(P.HullOrigin), F.ToWorldRot(P.HullAtt));
			}
		}
		P.Pivot += P.Vel * Dt;
		P.Att = FQuat(P.SpinAxis, P.SpinRate * Dt) * P.Att;
		P.Att.Normalize();
		P.Origin = P.Pivot - P.Att.RotateVector(P.PivotLocal);
		if (AStaticMeshActor* A = P.Actor.Get())
		{
			A->SetActorLocationAndRotation(F.ToWorld(P.Origin), F.ToWorldRot(P.Att));
		}
		// the cut faces cool in about a minute; the windows go out
		const float Heat = FMath::Pow(FMath::Clamp(1.f - P.Age / 60.f, 0.f, 1.f), 1.3f);
		if (UMaterialInstanceDynamic* M = P.CutMid.Get())
		{
			if (FMath::Abs(Heat - P.Heat) > 0.015f)
			{
				M->SetScalarParameterValue(TEXT("Heat"), Heat);
			}
		}
		if (FMath::Abs(Heat - P.Heat) > 0.015f)
		{
			P.Heat = Heat;
		}
		if (UMaterialInstanceDynamic* L = P.LitMid.Get())
		{
			if (P.Age < 4.f)
			{
				L->SetScalarParameterValue(TEXT("LitFraction"), 0.65f * FMath::Clamp(1.f - P.Age / 2.5f, 0.f, 1.f) * (FMath::FRand() < 0.3f ? 0.3f : 1.f));
			}
			else if (P.Age < 4.3f)
			{
				L->SetScalarParameterValue(TEXT("LitFraction"), 0.f);
			}
		}
		// fires, sparks and smoke from the cut faces (and from a reactor's pieces, all over)
		const FShipTable* T = P.Table;
		if (!T || P.Heat < 0.04f)
		{
			continue;
		}
		const double Dist2 = FVector::DistSquared(P.Pivot, F.Origin);
		if (Dist2 > FMath::Square(120000.0))
		{
			continue;
		}
		const float K = FMath::Clamp(Density, 0.2f, 2.f);
		for (int32 f = 0; f < T->NumFaces; ++f)
		{
			const FCutFace& Cf = T->Faces[f];
			if (Cf.Piece != P.Section)
			{
				continue;
			}
			const float Area = FMath::Clamp(Cf.HalfY * Cf.HalfZ / 400.f, 0.5f, 6.f);
			P.Emit += Dt * (0.8f + 3.f * Area * FMath::Pow(P.Heat, 0.6f)) * K * FMath::Min(Room(LFire), Room(LSmoke) * 1.5f);
			int32 Spawned = 0;
			while (P.Emit >= 1.f && Spawned < 6)
			{
				P.Emit -= 1.f;
				++Spawned;
				const FVector Local(Cf.X, Cf.Cy + FMath::FRandRange(-0.85f, 0.85f) * Cf.HalfY, Cf.Cz + FMath::FRandRange(-0.85f, 0.85f) * Cf.HalfZ);
				const FVector Pt = P.Origin + P.Att.RotateVector(Local);
				const FVector Nrm = P.Att.RotateVector(FVector(Cf.NormalX, 0.f, 0.f));
				const FVector Vel = P.Vel + Nrm * FMath::FRandRange(3.f, 12.f) + FMath::VRand() * 2.f;
				const float R0 = FMath::Clamp(Cf.HalfZ * 0.25f, 3.f, 18.f);
				const float Roll = FMath::FRand();
				if (Roll < 0.5f)
				{
					if (FPuff* Pf = AddPuff(Pt, Vel, FMath::FRandRange(0.9f, 1.8f), R0, R0 * FMath::FRandRange(2.2f, 3.4f), FLinearColor(1.f, 0.52f, 0.18f), 160.f * (0.4f + 0.6f * P.Heat), LFire))
					{
						Pf->P1 = FMath::FRand();
					}
				}
				else if (Roll < 0.8f)
				{
					Smoke(Pt, Vel, R0 * 2.2f, FMath::FRandRange(5.f, 9.f), 0.9f);
				}
				else
				{
					SparkBurst(Pt, Nrm, 0.8f, 3, 15.f, 70.f, 0.8f, 2.0f, 9.f, FLinearColor(1.f, 0.6f, 0.22f), 230.f, P.Vel);
				}
			}
		}
		if (P.bReactor && P.Age < 25.f && FMath::FRand() < Dt * 3.f)
		{
			const FVector Pt = P.Pivot + FMath::VRand() * P.Radius * 0.6f;
			AddPuff(Pt, P.Vel, FMath::FRandRange(1.f, 2.2f), P.Radius * 0.05f, P.Radius * 0.14f, FLinearColor(1.f, 0.5f, 0.16f), 150.f, LFire);
		}
	}
}

// ------------------------------------------------------------------------------------------------------------------ shields, each frame
void UAstraWarFX::TickShields()
{
	UWorld* World = Owner->GetWorld();
	int32 Made = 0;                            // shells made this frame (one is enough: a battle's start has thirty ships)
	for (auto It = ShipFx.CreateIterator(); It; ++It)
	{
		FShipFx& Fx = It.Value();
		FShield& Sh = Fx.Shield;
		for (int32 i = Sh.Ripples.Num() - 1; i >= 0; --i)
		{
			Sh.Ripples[i].Age += Dt;
			if (Sh.Ripples[i].Age >= Sh.Ripples[i].Life)
			{
				Sh.Ripples.RemoveAt(i);
			}
		}
		if (Sh.CollapseAge >= 0.f)
		{
			Sh.CollapseAge += Dt;
			if (Sh.CollapseAge > 1.4f)
			{
				Sh.CollapseAge = -1.f;
			}
		}
		const bool bActive = Sh.Ripples.Num() > 0 || Sh.CollapseAge >= 0.f;
		const FAstraBattleShip* S = Owner->FindById(It.Key());
		if (!S || !S->bAlive)
		{
			if (AStaticMeshActor* A = Sh.Actor.Get())
			{
				A->Destroy();
			}
			if (!S)
			{
				It.RemoveCurrent();
			}
			else
			{
				Sh.Actor = nullptr;
			}
			continue;
		}
		if (!bLive)
		{
			continue;
		}
		AStaticMeshActor* A = Sh.Actor.Get();
		if (!A)
		{
			// A warship's shell is made as soon as the ship is near enough to matter, and stands there unseen (its component is not visible): the main
			// viewscreen takes the list of the actors it shows twice a second, so a shell made at the first blow would miss half a second of its ripple.
			if (!S->Dmg.bModel || S->bCraft || Made >= 1 || FVector::DistSquared(S->Pos, F.Origin) > FMath::Square(150000.0))
			{
				continue;
			}
			++Made;
			FActorSpawnParameters P;
			P.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
			A = World->SpawnActor<AStaticMeshActor>(FVector::ZeroVector, FRotator::ZeroRotator, P);
			if (!A)
			{
				continue;
			}
			A->SetMobility(EComponentMobility::Movable);
			UStaticMeshComponent* C = A->GetStaticMeshComponent();
			C->SetStaticMesh(BallMesh ? BallMesh.Get() : SphereMesh.Get());
			C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
			C->SetCastShadow(false);
			C->bAffectDynamicIndirectLighting = false;
			C->SetReceivesDecals(false);
			C->SetTranslucentSortPriority(-1);
			C->SetVisibility(false);
			A->Tags.Add(TEXT("ASTRA.Sky"));
			Sh.Mid = C->CreateAndSetMaterialInstanceDynamicFromMaterial(0, MatShield);
			Sh.Actor = A;
			Sh.bShown = false;
		}
		if (!bActive)
		{
			if (Sh.bShown)
			{
				A->GetStaticMeshComponent()->SetVisibility(false);       // (the actor itself is never hidden: the viewscreen leaves out the hidden)
				Sh.bShown = false;
			}
			continue;
		}
		const FVector Axes = ShieldAxes(*S);
		const FVector Centre = S->Pos + S->Att.RotateVector(FVector(S->Box.Valid() ? S->Box.Mid : 0.f, 0.f, 0.f));
		A->SetActorLocationAndRotation(F.ToWorld(Centre), F.ToWorldRot(S->Att));
		A->SetActorScale3D(Axes * 2.f);
		if (!Sh.bShown)
		{
			A->GetStaticMeshComponent()->SetVisibility(true);
			Sh.bShown = true;
		}
		if (UMaterialInstanceDynamic* M = Sh.Mid.Get())
		{
			const bool bAstra = S->Side == EAstraSide::Astra;
			const FLinearColor Col = ShieldColor(bAstra);
			M->SetVectorParameterValue(TEXT("Axes"), FLinearColor(Axes.X, Axes.Y, Axes.Z, 0.f));
			M->SetVectorParameterValue(TEXT("Color"), Col);
			M->SetScalarParameterValue(TEXT("HexSize"), FMath::Clamp(S->Radius * 0.035f, 5.f, 18.f));
			M->SetScalarParameterValue(TEXT("Gain"), Intensity);
			static const TCHAR* const HitNames[6] = {TEXT("Hit0"), TEXT("Hit1"), TEXT("Hit2"), TEXT("Hit3"), TEXT("Hit4"), TEXT("Hit5")};
			static const TCHAR* const InfoNames[6] = {TEXT("Info0"), TEXT("Info1"), TEXT("Info2"), TEXT("Info3"), TEXT("Info4"), TEXT("Info5")};
			for (int32 i = 0; i < 6; ++i)
			{
				if (i < Sh.Ripples.Num())
				{
					const FRipple& R = Sh.Ripples[i];
					const float Age01 = R.Age / R.Life;
					M->SetVectorParameterValue(HitNames[i], FLinearColor(R.Dir.X, R.Dir.Y, R.Dir.Z, R.Strength * (1.f - Age01)));
					M->SetVectorParameterValue(InfoNames[i], FLinearColor(R.Radius, Age01, R.Stress, R.Seed));
				}
				else
				{
					M->SetVectorParameterValue(HitNames[i], FLinearColor(0.f, 0.f, 1.f, 0.f));
					M->SetVectorParameterValue(InfoNames[i], FLinearColor(10.f, 1.f, 0.f, 0.f));
				}
			}
			const float Cl = Sh.CollapseAge >= 0.f ? FMath::Clamp(1.f - Sh.CollapseAge / 1.4f, 0.f, 1.f) : 0.f;
			M->SetVectorParameterValue(TEXT("Collapse"), FLinearColor(Sh.CollapseDir.X, Sh.CollapseDir.Y, Sh.CollapseDir.Z, Cl));
		}
	}
}

// ------------------------------------------------------------------------------------------------------------------ the drives
void UAstraWarFX::DrawDrives()
{
	const FVector Eye = PlayerEye();
	(void)Eye;
	for (FAstraBattleShip& S : Owner->Ships)
	{
		if (!S.bAlive || S.bGhost)
		{
			continue;
		}
		const double Dist2 = FVector::DistSquared(S.Pos, F.Origin);
		if (Dist2 > FMath::Square(190000.0))
		{
			continue;
		}
		FShipFx* Fx = ShipFx.Find(S.Id);
		const float Thrust = Fx ? Fx->Thrust : 0.15f;
		const bool bDead = S.bDisabled || (S.Dmg.bModel && Owner->EngineFactor(S) <= 0.01f);
		const FShipTable* T = nullptr;
		if (Fx)
		{
			if (!Fx->bTableKnown)
			{
				Fx->Table = FindTable(FxMeshOf(S));            // (once: a string search a frame for every craft would be waste)
				Fx->bTableKnown = true;
			}
			T = Fx->Table;
		}
		const bool bAstra = S.Side == EAstraSide::Astra;
		const FLinearColor Core = bAstra ? FLinearColor(0.78f, 0.9f, 1.f) : FLinearColor(1.f, 0.62f, 0.3f);
		if (S.bCraft)
		{
			if (bDead || Thrust < 0.02f)
			{
				continue;
			}
			// a fighter: the glow of its drive, seen as a point at any distance (the material keeps it a few pixels)
			const FVector Back = S.Pos - S.Att.GetForwardVector() * (T && T->NumBells ? -T->Bells[0].X : 5.f);
			FTransform* X;
			if (float* D = Glows.Next(X))
			{
				const float R = FMath::Max(S.Radius * 0.25f, 1.1f) * GlowK;
				*X = FTransform(FQuat::Identity, F.ToWorld(Back), FVector(R * 2.f));
				Fill(D, Core, 110.f * Intensity * (0.35f + 0.65f * Thrust), 0.f, 0.f, 0.f, (float)(S.Id & 255) / 255.f, R * 2.f, 0.f);
			}
			// and the streak of its exhaust, along its heading (a wing that turns hard draws arcs across the sky): where a dogfight is, near enough to be seen as more than a point
			if (WakeGain > 0.f && Dist2 < FMath::Square(14000.0))
			{
				const float Len = FMath::Clamp(30.f + 260.f * Thrust, 30.f, 320.f);
				const float Wd = FMath::Clamp(S.Radius * 0.28f, 0.8f, 2.6f);
				const FVector Fwd = F.DirToWorld(S.Att.GetForwardVector());           // (to the nozzle: the bright end of the streak)
				const FVector BackW = F.ToWorld(Back);
				if (float* Dw = Tubes.Next(X))
				{
					*X = FTransform(FQuat::FindBetweenNormals(FVector::ZAxisVector, Fwd), BackW - Fwd * (Len * 50.0), FVector(Wd, Wd, Len));
					Fill(Dw, Core, 85.f * Intensity * WakeGain * (0.3f + 0.7f * Thrust), 0.f, 5.f, 2.4f, (float)(S.Id & 255) / 255.f, Wd, Len);
				}
			}
			continue;
		}
		if (!T || T->NumBells == 0)
		{
			continue;
		}
		const float Sput = S.Dmg.bModel ? FMath::Clamp(1.f - 2.f * S.Dmg.Sys[AstraWar::SysEngines], 0.f, 1.f) : 0.f;   // a hurt drive coughs
		const float Fl = bDead ? 0.f : (0.3f + 0.7f * Thrust);
		for (int32 b = 0; b < T->NumBells; ++b)
		{
			const FBell& Bl = T->Bells[b];
			if (bDead)
			{
				continue;
			}
			const FVector Lip = S.Pos + S.Att.RotateVector(FVector(Bl.X - Bl.Lip, Bl.Y, Bl.Z));
			FTransform* X;
			// the plume: a tube from the bell's lip, as long as the thrust is hard
			const float Len = Bl.R * (5.f + 25.f * Thrust);
			const float Width = Bl.R * 1.9f;
			const FVector DirW = F.DirToWorld(S.Att.RotateVector(FVector(-1.f, 0.f, 0.f)));
			if (float* D = Plumes.Next(X))
			{
				const FVector LipW = F.ToWorld(Lip);
				*X = FTransform(FQuat::FindBetweenNormals(FVector::ZAxisVector, DirW), LipW + DirW * (Len * 50.0), FVector(Width, Width, Len));
				Fill(D, Core, 70.f * Intensity * Fl, Clock, bAstra ? 0.f : 1.f, Sput, (float)(S.Id & 255) / 255.f, Width, Len);
			}
			if (float* D = Glows.Next(X))
			{
				const float R = Bl.R * GlowK * (1.5f + 1.5f * Thrust);
				*X = FTransform(FQuat::Identity, F.ToWorld(Lip), FVector(R * 2.f));
				Fill(D, Core, 210.f * Intensity * Fl, 0.f, 0.f, 0.f, (float)(S.Id & 255) / 255.f, R * 2.f, 0.f);
			}
		}
	}
}
