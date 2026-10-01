// ASTRA — the war's visual effects: what a blow looks like, what a shield does with it, explosions, and the deaths of ships.

#include "AstraWarFX.h"
#include "AstraBattleSubsystem.h"
#include "ASTRA.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/World.h"
#include "Materials/MaterialInstanceDynamic.h"

using namespace AstraFx;

namespace
{
	const FLinearColor FxWhite(1.f, 0.97f, 0.9f);
	const FLinearColor FxFire(1.f, 0.6f, 0.24f);
	const FLinearColor FxMetal(1.f, 0.7f, 0.32f);
}

// ------------------------------------------------------------------------------------------------------------------ flashes
void UAstraWarFX::OnFlash(EAstraFxFlash Kind, const FVector& Pos, float Size, float Life, const FLinearColor& Col, float Inten, const FVector& Vel, float Delay)
{
	if (!IsActive() || FVector::DistSquared(Pos, F.Origin) > FMath::Square(170000.0))
	{
		return;
	}
	switch (Kind)
	{
	case EAstraFxFlash::Flak:
	{
		// a point-defence kill: the flash, the puff of smoke that hangs, a few sparks
		if (FPuff* P = AddPuff(Pos, Vel, 0.3f, Size * 0.2f, Size * 0.55f, FLinearColor(1.f, 0.85f, 0.5f), 400.f, LGlow, Delay))
		{
			P->P1 = 1.f;
		}
		AddPuff(Pos, Vel, 0.9f, Size * 0.15f, Size * 0.5f, FxFire, 90.f, LFire, Delay);
		Smoke(Pos, Vel, Size * 0.45f, 3.5f, 0.6f, Delay + 0.1f);
		SparkBurst(Pos, FVector::UpVector, 3.f, 5, 20.f, 90.f, 0.3f, 0.8f, 7.f, FxMetal, 200.f, Vel);
		break;
	}
	case EAstraFxFlash::Decoy:
	{
		// a flare or a chaff bloom: a hot little sun that drifts and fades
		if (FPuff* P = AddPuff(Pos, Vel, Life, Size * 0.45f, Size * 0.3f, Col, Inten * 0.6f, LGlow, Delay))
		{
			P->P1 = 2.f;
		}
		break;
	}
	case EAstraFxFlash::Blast:
		Explosion(Pos, Vel, Size, false, FMath::Clamp(Size / 90.f, 0.4f, 1.6f), Delay);
		break;
	default:
	{
		if (FPuff* P = AddPuff(Pos, Vel, Life, Size * 0.3f, Size * 0.7f, Col, Inten * 3.f, LGlow, Delay))
		{
			P->P1 = 1.f;
		}
		SparkBurst(Pos, FVector::UpVector, 3.f, 4, 20.f, 100.f, 0.25f, 0.7f, 6.f, Col, 180.f, Vel);
		break;
	}
	}
}

// ------------------------------------------------------------------------------------------------------------------ explosions
void UAstraWarFX::Smoke(const FVector& Pos, const FVector& Vel, float Radius, float Life, float Dark, float Delay)
{
	if (FMath::FRand() > Room(LSmoke))
	{
		return;                              // the smoke is thick enough already
	}
	if (FPuff* P = AddPuff(Pos, Vel * 0.8f + FMath::VRand() * Radius * 0.12f, Life, Radius * 0.5f, Radius * 1.5f, FLinearColor(0.5f, 0.48f, 0.46f), 70.f, LSmoke, Delay))
	{
		P->P1 = Dark;
		P->P2 = 0.4f;                       // an ember glow inside it, fading
		P->Drag = 0.25f;
	}
}

void UAstraWarFX::Shockwave(const FVector& Pos, const FVector& Vel, float Radius, float Life, const FLinearColor& Col, float Delay)
{
	// the blast wave: an expanding shell seen as a bright ring at its limb (a sphere, so it is a ring from any side)
	if (FPuff* P = AddPuff(Pos, Vel, Life, Radius * 0.12f, Radius, Col, 140.f, LShock, Delay))
	{
		P->P2 = 0.f;
	}
}

void UAstraWarFX::Explosion(const FVector& Pos, const FVector& Vel, float Radius, bool bAstra, float Power, float Delay)
{
	const float R = FMath::Max(Radius, 2.f);
	const float P = FMath::Clamp(Power, 0.15f, 3.f);
	const float K = FMath::Clamp(Density, 0.2f, 2.f);
	// the flash: white, round, with the anamorphic streak, brief
	if (FPuff* F0 = AddPuff(Pos, Vel, 0.3f + 0.22f * P, 0.4f * R, 1.3f * R, FxWhite, 460.f * FMath::Sqrt(P), LGlow, Delay))
	{
		F0->P1 = 1.f;
	}
	// the fireball: billows of fire from the flipbook, a little apart, living a second or two
	const int32 Billows = FMath::Clamp(FMath::RoundToInt((1.f + 1.6f * P) * K * FMath::Max(0.4f, Room(LFire))), 1, 5);
	for (int32 i = 0; i < Billows; ++i)
	{
		const FVector Off = FMath::VRand() * R * 0.22f * (float)i;
		if (FPuff* B = AddPuff(Pos + Off, Vel + Off * 0.6f, (1.5f + 1.0f * P) * FMath::FRandRange(0.8f, 1.2f), 0.4f * R, R * FMath::FRandRange(0.8f, 1.15f),
		                       FxFire, 190.f, LFire, Delay + 0.05f * i))
		{
			B->P1 = FMath::FRand();
		}
	}
	// the halo that lingers a moment and the sparks it throws
	AddPuff(Pos, Vel, 1.0f + 0.5f * P, R, 2.0f * R, FLinearColor(1.f, 0.5f, 0.18f), 22.f, LGlow, Delay);
	SparkBurst(Pos, FVector::UpVector, 3.f, 12 + (int32)(34 * P), 30.f, 90.f + 70.f * P, 0.7f, 2.0f, 9.f + 5.f * P, FxMetal, 260.f, Vel);
	// smoke, and the blast wave of a big one
	const int32 Puffs_ = FMath::Max(1, FMath::RoundToInt((1.f + 2.5f * P) * K));          // (each one asks the smoke's room in Smoke())
	for (int32 i = 0; i < Puffs_; ++i)
	{
		Smoke(Pos + FMath::VRand() * R * 0.35f, Vel + FMath::VRand() * 8.f, R * FMath::FRandRange(0.7f, 1.2f), FMath::FRandRange(4.f, 7.5f), 0.85f, Delay + 0.15f + 0.1f * i);
	}
	if (P > 0.45f)
	{
		Shockwave(Pos, Vel, R * (2.2f + 0.6f * P), 0.9f + 0.5f * P, FLinearColor(1.f, 0.7f, 0.4f), Delay + 0.03f);
	}
	// what is thrown off
	const int32 Chunks = FMath::RoundToInt((2.f + 6.f * P) * K);
	for (int32 i = 0; i < Chunks; ++i)
	{
		AddDebris(Pos + FMath::VRand() * R * 0.3f, Vel + FMath::VRand() * FMath::FRandRange(15.f, 40.f + 40.f * P), R * FMath::FRandRange(0.02f, 0.06f), bAstra, FMath::FRandRange(12.f, 24.f));
	}
	// the flash lights up what is near it
	AddLight(Pos, 0.3f + 0.35f * P, R * 9.f, 6500.f * R * R * FMath::Sqrt(P), FLinearColor(1.f, 0.72f, 0.42f), Vel, Delay);
}

// ------------------------------------------------------------------------------------------------------------------ blows
FVector UAstraWarFX::ShieldAxes(const FAstraBattleShip& S) const
{
	if (S.Box.Valid())
	{
		return FVector(S.Box.Hx * 1.14f + 10.f, S.Box.Hy * 1.55f + 12.f, S.Box.Hz * 1.55f + 12.f);
	}
	return FVector(S.Radius * 1.15f);
}

FVector UAstraWarFX::ShieldPoint(const FAstraBattleShip& S, const FVector& HitPos, FVector& OutDir) const
{
	const FVector Axes = ShieldAxes(S);
	FVector Lp = S.Att.UnrotateVector(HitPos - S.Pos);
	FVector U;
	if (S.Box.Valid())
	{
		Lp.X -= S.Box.Mid;
		U = FVector(Lp.X / S.Box.Hx, Lp.Y / S.Box.Hy, Lp.Z / S.Box.Hz);
	}
	else
	{
		U = Lp / FMath::Max(S.Radius, 1.f);
	}
	OutDir = U.GetSafeNormal();
	if (OutDir.IsNearlyZero())
	{
		OutDir = FVector::ForwardVector;
	}
	const FVector Local = OutDir * Axes + FVector(S.Box.Valid() ? S.Box.Mid : 0.f, 0.f, 0.f);
	return S.Pos + S.Att.RotateVector(Local);
}

void UAstraWarFX::ShieldHit(const FAstraBattleShip& To, const FAstraFxHit& H)
{
	FShipFx& Fx = ShipOf(To.Id);
	FShield& Sh = Fx.Shield;
	const bool bAstra = To.Side == EAstraSide::Astra;
	const FVector Axes = ShieldAxes(To);
	FVector Dir;
	const FVector P = ShieldPoint(To, H.Pos, Dir);
	const FLinearColor Col = ShieldColor(bAstra);
	FRipple R;
	R.Dir = Dir;
	R.Strength = FMath::Clamp(0.55f + H.ShieldTook / 70.f, 0.55f, 1.8f);
	R.Radius = FMath::Clamp(7.f + 2.4f * FMath::Sqrt(H.ShieldTook), 8.f, 0.38f * FMath::Min3(Axes.X, Axes.Y, Axes.Z));
	R.Life = 0.7f + 0.35f * R.Strength;
	R.Stress = 1.f - FMath::Clamp(H.SectorFrac, 0.f, 1.f);
	R.Seed = FMath::FRand();
	if (Sh.Ripples.Num() >= 6)
	{
		Sh.Ripples.RemoveAt(0);
	}
	Sh.Ripples.Add(R);
	Sh.Idle = 0.f;
	// the flash on the shell, and a few sparks thrown off it
	if (FPuff* G = AddPuff(P, To.Vel, 0.26f, 0.25f * R.Radius, 0.7f * R.Radius, Mix(Col, FxWhite, 0.4f), 110.f * R.Strength, LGlow))
	{
		G->P1 = 1.f;
	}
	const FVector Out = To.Att.RotateVector((Dir / Axes).GetSafeNormal());
	SparkBurst(P, Out, 0.9f, 4 + (int32)(H.ShieldTook * 0.05f), 25.f, 110.f, 0.2f, 0.55f, 6.f, Col, 150.f, To.Vel);
	// a beam that ends on this ship ends on its shield: it does not reach the hull
	for (int32 i = Beams.Num() - 1; i >= 0 && i >= Beams.Num() - 6; --i)
	{
		FBeam& B = Beams[i];
		if (B.ToId == To.Id && B.Age < 0.02f && FVector::DistSquared(To.Pos + To.Att.RotateVector(B.ToLoc), H.Pos) < 4.0)
		{
			B.ToLoc = Dir * Axes + FVector(To.Box.Valid() ? To.Box.Mid : 0.f, 0.f, 0.f);
			break;
		}
	}
	if (H.bSectorFell)
	{
		// the sector gives out: the whole facing lights and flickers, and a blue-white flash on the shell
		Sh.CollapseAge = 0.f;
		Sh.CollapseDir = AstraWar::FacingVector(H.Facing);
		if (FPuff* G = AddPuff(P, To.Vel, 0.6f, 0.4f * R.Radius, 1.5f * R.Radius, FLinearColor(0.8f, 0.92f, 1.f), 300.f, LGlow))
		{
			G->P1 = 1.f;
		}
		SparkBurst(P, Out, 1.2f, 18, 40.f, 160.f, 0.3f, 0.9f, 9.f, Col, 220.f, To.Vel);
		AddLight(P, 0.45f, Axes.GetMax() * 1.2f, 2.6e6f * FMath::Square(Axes.GetMax() / 400.f + 0.4f), Col, To.Vel);
	}
}

void UAstraWarFX::OnHit(const FAstraBattleShip& To, const FAstraFxHit& H)
{
	if (!IsActive() || !Owner || FVector::DistSquared(H.Pos, F.Origin) > FMath::Square(170000.0))
	{
		return;
	}
	const bool bAstra = To.Side == EAstraSide::Astra;
	const FLinearColor Col = ShotColor(!bAstra, H.Kind);   // (the shooter's colour: the other side's)
	if (H.ShieldTook > 0.4f && To.Dmg.bModel)
	{
		ShieldHit(To, H);
	}
	else if (H.ShieldTook > 0.4f)
	{
		// a craft's little shield: a bluish flash
		if (FPuff* G = AddPuff(H.Pos, To.Vel, 0.25f, 1.2f, 4.f, ShieldColor(bAstra), 140.f, LGlow))
		{
			G->P1 = 1.f;
		}
	}
	if (H.Through <= 0.4f)
	{
		return;
	}
	const float T = FMath::Clamp(H.Through, 1.f, 500.f);
	const FVector Out = To.Dmg.bModel ? To.Att.RotateVector(H.LocalOut) : (H.Pos - To.Pos).GetSafeNormal();
	const FVector Vel = To.Vel;
	switch (H.Kind)
	{
	case EAstraHitKind::Missile:
	case EAstraHitKind::Torpedo:
	case EAstraHitKind::Rocket:
	{
		const float Tor = H.Kind == EAstraHitKind::Torpedo ? 1.5f : 1.f;
		const float Rr = (H.Kind == EAstraHitKind::Rocket ? 7.f : 12.f) * (1.f + T / 160.f) * Tor;
		Explosion(H.Pos + Out * Rr * 0.3f, Vel, FMath::Min(Rr, To.Dmg.bModel ? 60.f : 18.f), bAstra,
		          FMath::Clamp((H.Kind == EAstraHitKind::Rocket ? 0.3f : 0.45f) * Tor + T / 260.f, 0.25f, 1.5f), 0.f);
		break;
	}
	case EAstraHitKind::Laser:
	case EAstraHitKind::PointDefence:
	{
		const float R = 2.4f + 0.03f * T;
		if (FPuff* G = AddPuff(H.Pos + Out * R * 0.4f, Vel, 0.35f, R * 0.4f, R * 1.1f, Mix(Col, FxWhite, 0.4f), 240.f, LGlow))
		{
			G->P1 = 1.f;
		}
		AddPuff(H.Pos + Out * R * 0.3f, Vel, 1.4f, R * 0.5f, R * 0.7f, FLinearColor(1.f, 0.45f, 0.12f), 36.f, LGlow);   // the metal glows where it was burnt
		SparkBurst(H.Pos, Out, 1.1f, 3 + (int32)(T * 0.08f), 25.f, 110.f, 0.25f, 0.8f, 8.f, FxMetal, 220.f, Vel);
		break;
	}
	case EAstraHitKind::Cannon:
	{
		const float R = 1.4f + 0.02f * T;
		if (FPuff* G = AddPuff(H.Pos + Out * R * 0.4f, Vel, 0.2f, R * 0.4f, R, Mix(Col, FxWhite, 0.5f), 220.f, LGlow))
		{
			G->P1 = 1.f;
		}
		SparkBurst(H.Pos, Out, 1.2f, 3, 20.f, 90.f, 0.2f, 0.5f, 5.f, FxMetal, 200.f, Vel);
		break;
	}
	default:
	{
		// a slug: a hard flash, a spray of sparks and chips; a heavy one throws fire
		const float R = 4.5f + 0.1f * T;
		if (FPuff* G = AddPuff(H.Pos + Out * R * 0.35f, Vel, 0.3f, R * 0.4f, R * 1.15f, Mix(Col, FxWhite, 0.55f), 330.f, LGlow))
		{
			G->P1 = 1.f;
		}
		SparkBurst(H.Pos, Out, 1.0f, 5 + (int32)(T * 0.18f), 40.f, 190.f, 0.25f, 0.9f, 12.f, FxMetal, 260.f, Vel);
		if (T > 26.f)
		{
			for (int32 i = 0; i < 1 + (int32)(T / 40.f); ++i)
			{
				AddDebris(H.Pos + Out * 2.f, Vel + (Out + FMath::VRand() * 0.8f) * FMath::FRandRange(15.f, 70.f), FMath::FRandRange(0.6f, 1.6f), bAstra, FMath::FRandRange(8.f, 16.f));
			}
		}
		if (T > 55.f)
		{
			Explosion(H.Pos + Out * R * 0.6f, Vel, 6.f + 0.08f * T, bAstra, 0.25f + T / 400.f, 0.04f);
		}
		else if (T > 30.f)
		{
			AddLight(H.Pos + Out * 8.f, 0.16f, 90.f, 5.e5f * (T / 50.f), Mix(Col, FxWhite, 0.4f), Vel);
		}
		break;
	}
	}
	if (H.Felt > 8.f)
	{
		AddScar(To, H);                    // the plating remembers it
	}
}

// ------------------------------------------------------------------------------------------------------------------ deaths
void UAstraWarFX::OnCraftDestroyed(const FAstraBattleShip& S)
{
	if (!IsActive() || FVector::DistSquared(S.Pos, F.Origin) > FMath::Square(170000.0))
	{
		return;
	}
	const float R = FMath::Max(S.Radius * 1.2f, 7.f);
	Explosion(S.Pos, S.Vel, R, S.Side == EAstraSide::Astra, S.bPiloted ? 0.8f : 0.38f, 0.f);
}

void UAstraWarFX::OnAquilaBreach(const FVector& ReactorPos, float Radius, const FVector& Vel)
{
	if (!IsActive())
	{
		return;
	}
	const float R = FMath::Max(Radius, 120.f);
	Explosion(ReactorPos, Vel, R, true, 2.4f, 0.f);
	if (FPuff* F0 = AddPuff(ReactorPos, Vel, 1.0f, 0.8f * R, 2.8f * R, FxWhite, 900.f, LGlow))
	{
		F0->P1 = 1.f;
	}
	Shockwave(ReactorPos, Vel, R * 5.f, 2.4f, FLinearColor(1.f, 0.85f, 0.6f), 0.05f);
	AddLight(ReactorPos, 1.4f, R * 14.f, 6.e9f, FLinearColor(1.f, 0.85f, 0.65f), Vel);
}

void UAstraWarFX::OnShipDisabled(const FAstraBattleShip& S)
{
	if (!IsActive())
	{
		return;
	}
	// no explosion: a last discharge of sparks from along the hull, and the power goes out (TickShips)
	const int32 N = 6 + (int32)FMath::Min(14.f, S.Radius / 40.f);
	for (int32 i = 0; i < N; ++i)
	{
		const FVector P = HullPoint(S, FMath::RandRange(0, 2), FMath::FRand(), FMath::FRandRange(-0.8f, 0.8f), FMath::FRandRange(-1.f, 1.f), true);
		SparkBurst(P, (P - S.Pos).GetSafeNormal(), 0.9f, 8, 20.f, 90.f, 0.4f, 1.4f, 8.f, FxMetal, 220.f, S.Vel);
		if (FPuff* G = AddPuff(P, S.Vel, 0.35f, 1.5f, 5.f, FLinearColor(1.f, 0.7f, 0.4f), 160.f, LGlow, FMath::FRandRange(0.f, 1.6f)))
		{
			G->P1 = 1.f;
		}
	}
	ShipOf(S.Id).bDark = false;             // (the lights go out over the next seconds)
	ShipOf(S.Id).DarkT = 0.f;
}

bool UAstraWarFX::OnShipDestroyed(FAstraBattleShip& S, const FAstraDeathEvent& E)
{
	if (!IsActive() || !Owner)
	{
		return false;
	}
	if (E.How != EAstraFate::ReactorBreach && E.How != EAstraFate::Breakup)
	{
		return false;                      // any other end of a capital ship: the old explosion and the hulk it leaves
	}
	AActor* Hull = S.Actor;
	if (!Hull && bLive)
	{
		return false;
	}
	const bool bAstra = S.Side == EAstraSide::Astra;
	const float R = FMath::Max(S.Radius, 40.f);
	const FVector Centre = S.Pos + S.Att.RotateVector(FVector(S.Box.Valid() ? S.Box.Mid : 0.f, 0.f, 0.f));
	const bool bReactor = E.How == EAstraFate::ReactorBreach;
	// the hull's pieces: the whole ship is hidden and its three pieces take its place, in the same frame (the picture does not change)
	if (!MakePieces(S, E, Hull, bReactor))
	{
		return false;                      // no pieces to show: the old explosion (and its hulk) stands
	}
	if (ShipFx.Contains(S.Id))
	{
		if (AStaticMeshActor* A = ShipFx[S.Id].Shield.Actor.Get())
		{
			A->Destroy();
		}
		ShipFx.Remove(S.Id);
	}
	S.Actor = nullptr;
	if (bReactor)
	{
		// the reactor lets go: a flash and a ball of fire that swallow the ship, the blast wave, and the pieces thrown out of it
		Explosion(Centre, S.Vel, R * 0.95f, bAstra, 2.0f, 0.f);
		if (FPuff* W = AddPuff(Centre, S.Vel, 0.9f, 0.7f * R, 1.7f * R, FxWhite, 950.f, LGlow))
		{
			W->P1 = 1.f;
		}
		AddPuff(Centre, S.Vel, 3.4f, 0.5f * R, 1.4f * R, FLinearColor(1.f, 0.55f, 0.2f), 230.f, LFire);
		for (int32 i = 0; i < 6; ++i)
		{
			const FVector P = Centre + S.Att.GetForwardVector() * FMath::FRandRange(-0.8f, 0.8f) * R;
			AddPuff(P, S.Vel, FMath::FRandRange(1.6f, 3.2f), 0.2f * R, FMath::FRandRange(0.4f, 0.8f) * R, FxFire, 200.f, LFire, 0.1f + 0.18f * i);
		}
		Shockwave(Centre, S.Vel, R * 4.2f, 2.3f, FLinearColor(1.f, 0.85f, 0.6f), 0.05f);
		AddLight(Centre, 1.3f, R * 12.f, 7.e9f * FMath::Square(R / 400.f + 0.3f), FLinearColor(1.f, 0.88f, 0.7f), S.Vel);
	}
	else
	{
		// the hull breaks along the section that gave way: a flash and a fountain of sparks at the cut, the blast wave, blasts along both halves
		const FVector At = E.BreakPoint;
		const FVector Axis = E.BreakAxis.IsNearlyZero() ? S.Att.GetForwardVector() : E.BreakAxis;
		const float Cut = FMath::Clamp(R * 0.3f, 25.f, 160.f);
		if (FPuff* W = AddPuff(At, S.Vel, 0.55f, 0.4f * Cut, 1.5f * Cut, FLinearColor(1.f, 0.85f, 0.55f), 620.f, LGlow))
		{
			W->P1 = 1.f;
		}
		AddPuff(At, S.Vel, 2.2f, 0.4f * Cut, 1.2f * Cut, FxFire, 200.f, LFire);
		SparkBurst(At, Axis, 1.6f, 36, 30.f, 160.f, 0.8f, 2.4f, 14.f, FxMetal, 280.f, S.Vel);
		SparkBurst(At, -Axis, 1.6f, 36, 30.f, 160.f, 0.8f, 2.4f, 14.f, FxMetal, 280.f, S.Vel);
		Shockwave(At, S.Vel, R * 1.1f, 1.4f, FLinearColor(1.f, 0.7f, 0.4f), 0.04f);
		AddLight(At, 0.9f, R * 6.f, 1.4e9f * FMath::Square(R / 400.f + 0.3f), FLinearColor(1.f, 0.72f, 0.45f), S.Vel);
		for (int32 i = 0; i < 4; ++i)
		{
			Explosion(Centre + Axis * FMath::FRandRange(-0.7f, 0.7f) * R + FMath::VRand() * R * 0.1f, S.Vel, R * FMath::FRandRange(0.12f, 0.26f), bAstra, 0.6f,
			          0.25f + 0.45f * i);
		}
	}
	return true;
}
