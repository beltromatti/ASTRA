// Read-only views of the battle for the stations' executors and the main viewscreen: what the Aquila knows, with the fog
// of war applied (a bearing-only contact has no range, no speed, no damage state).

#include "AstraBattleSubsystem.h"

void UAstraBattleSubsystem::GetContacts(TArray<FContactView>& Out) const
{
	Out.Reset();
	if (Ships.Num() == 0)
	{
		return;
	}
	const FAstraBattleShip& P = Ships[0];
	for (const FAstraBattleShip& S : Ships)
	{
		if (S.bPlayer || !S.bAlive || S.Track == 0 || S.ContactId.IsEmpty())
		{
			continue;
		}
		FContactView V;
		V.Id = S.Id;
		V.ContactId = S.ContactId;
		V.Side = S.Side;
		V.Track = S.Track;
		V.bCraft = S.bCraft;
		V.bDerelict = S.bDerelict;
		V.bCapital = !S.bCraft && !S.bDerelict && S.Side != EAstraSide::Neutral;
		V.bFleeing = S.bFleeing;
		V.bJamming = S.bJamming;
		V.bFiringAtUs = S.Side == EAstraSide::Mandate && !S.bHoldFire && (S.TargetId == P.Id || S.FireTarget == P.Id);
		V.RadiusM = S.Radius;
		const bool bFirm = S.Track >= 2;
		V.Class = (S.bClassified || !S.bFog) ? S.Class : FString();
		V.Label = (S.bIdentified || !S.bFog) ? S.Name : !V.Class.IsEmpty() ? FString::Printf(TEXT("%s (%s class)"), *S.ContactId, *V.Class) : S.ContactId;
		V.BearingDeg = BearingDeg(P.Pos, S.Pos);
		V.MarkDeg = MarkDeg(P.Pos, S.Pos);
		if (bFirm)
		{
			V.Pos = S.Pos;
			V.Vel = S.Vel;
			V.RangeKm = FVector::Dist(P.Pos, S.Pos) / 1000.0;
			V.HullFrac = S.HullMax > 0.f ? S.Hull / S.HullMax : -1.f;
			V.ShieldFrac = S.ShieldMax > 0.f ? S.Shield / S.ShieldMax : -1.f;
		}
		else
		{
			// only a bearing: a point along it, far enough to read as "out there" (no range is claimed)
			V.Pos = P.Pos + (S.Pos - P.Pos).GetSafeNormal() * 40000.0;
		}
		Out.Add(MoveTemp(V));
	}
	Out.Sort([](const FContactView& A, const FContactView& B)
	{
		const double Ra = A.RangeKm < 0.0 ? 1e9 : A.RangeKm, Rb = B.RangeKm < 0.0 ? 1e9 : B.RangeKm;
		return Ra < Rb;
	});
}

void UAstraBattleSubsystem::GetInboundMissiles(TArray<FVector>& Out) const
{
	Out.Reset();
	if (Ships.Num() == 0)
	{
		return;
	}
	const int32 Me = Ships[0].Id;
	for (const FAstraProjectile& Pr : Projectiles)
	{
		if (!Pr.bDead && Pr.Target == Me && Pr.Kind == EAstraProjKind::Missile)
		{
			Out.Add(Pr.Pos);
		}
	}
}
