// ASTRA — what is coming through the Gate, for the holo table and the main screen.
//
// The user's game of 5 Oct: the Gate cycled, Keeper Station reported a Mandate force coming through, and for a minute nothing on the plot said so —
// «where are the other enemy ships? I don't see them on the holo table». What the bridge has been told is coming is drawn where it will come out,
// with how many and how soon: the forces the battle has scheduled (the opening's vanguard at the Gate's mouth, the March's fleets in their last
// seconds in the Gate) and, further out, the March's fleets due in this system as ASTRA's high command holds them.

#include "AstraBattleSubsystem.h"
#include "AstraShipSubsystem.h"
#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/World.h"

namespace AstraGateWatch
{
	constexpr double Km = 1000.0;

	FVector Polar(double RangeM, double BearingDeg)
	{
		const double B = FMath::DegreesToRadians(BearingDeg);
		return FVector(RangeM * FMath::Cos(B), RangeM * FMath::Sin(B), 0.0);
	}
}

bool UAstraBattleSubsystem::GetGateWatch(FGateWatch& Out) const
{
	Out = FGateWatch();
	if (Ships.Num() == 0 || !Landmarks.IsValidIndex(GateLandmark))
	{
		return false;
	}
	const FAstraBattleShip& P = Ships[0];
	const FVector Origin = ToWorld(P.Pos);
	const FVector Gate = Landmarks[GateLandmark].Pos;
	Out.GateRel = ToWorld(Gate) - Origin;
	Out.GateKm = (float)(FVector::Dist(P.Pos, Gate) / AstraGateWatch::Km);
	const auto Add = [&Out](bool bHostile, int32 N, float EtaS, const FVector& Rel)
	{
		int32& Count = bHostile ? Out.Hostile : Out.Friendly;
		float& Soonest = bHostile ? Out.HostileEtaS : Out.FriendlyEtaS;
		FVector& Where = bHostile ? Out.HostileRel : Out.FriendlyRel;
		Count += N;
		if (Soonest < 0.f || EtaS < Soonest)
		{
			Soonest = EtaS;
			Where = Rel;
		}
	};

	// the forces the battle has scheduled: where they will come out, as ArriveBeat will put them (a fixed point, or a bearing and a range from the Aquila)
	bool bBeat[2] = {false, false};   // hostile, friendly
	for (const TPair<float, TSharedPtr<FJsonObject>>& PB : PendingBeats)
	{
		const TSharedPtr<FJsonObject>& B = PB.Value;
		if (!B.IsValid())
		{
			continue;
		}
		FString Type;
		B->TryGetStringField(TEXT("type"), Type);
		Type = Type.ToLower();
		const bool bHostile = Type == TEXT("raid");
		if (!bHostile && Type != TEXT("reinforcements"))
		{
			continue;
		}
		const TArray<TSharedPtr<FJsonValue>>* AtM = nullptr;
		const bool bAt = B->TryGetArrayField(TEXT("at_m"), AtM) && AtM->Num() >= 3;
		bool bDark = true;
		B->TryGetBoolField(TEXT("dark"), bDark);
		double Bearing = 0.0, Range = 0.0;
		const bool bBearing = B->TryGetNumberField(TEXT("bearing_deg"), Bearing) && B->TryGetNumberField(TEXT("range_km"), Range);
		// a hostile force is on the plot before it comes only when its coming was seen: the opening's vanguard Keeper Station reported (its fixed point at
		// the Gate's mouth), a force the March sends with its drives lit; a dark raid is a surprise
		if (bHostile && bDark && !bAt)
		{
			continue;
		}
		const TArray<TSharedPtr<FJsonValue>>* Ids = nullptr;
		const int32 N = B->TryGetArrayField(TEXT("_ids"), Ids) ? FMath::Max(1, Ids->Num()) : 1;
		FVector At = Gate;
		if (bAt)
		{
			At = FVector((*AtM)[0]->AsNumber(), (*AtM)[1]->AsNumber(), (*AtM)[2]->AsNumber());
		}
		else if (bBearing)
		{
			At = P.Pos + AstraGateWatch::Polar(FMath::Clamp(Range, 6.0, 250.0) * AstraGateWatch::Km, Bearing);
		}
		Add(bHostile, N, FMath::Max(0.f, PB.Key - Time), ToWorld(At) - Origin);
		bBeat[bHostile ? 0 : 1] = true;
	}

	// further out: the March's fleets due in this system (their last seconds are the beats above: a side with a beat already scheduled is not counted twice)
	const UAstraShipSubsystem* ShipSys = GetWorld() ? GetWorld()->GetSubsystem<UAstraShipSubsystem>() : nullptr;
	if (ShipSys)
	{
		const FString Here = ShipSys->GetSystemName();
		const float Since = (float)(GetWorld()->GetTimeSeconds() - ShipSys->GetMarchAt());
		for (const FAstraMarchFleet& F : ShipSys->GetMarchFleets())
		{
			const FString& Next = F.Next.IsEmpty() ? F.To : F.Next;
			if (F.EtaS < 0.f || F.Ships <= 0 || Here.IsEmpty() || !Next.Equals(Here, ESearchCase::IgnoreCase) || F.System.Equals(Here, ESearchCase::IgnoreCase))
			{
				continue;
			}
			const bool bHostile = !F.Side.Equals(TEXT("astra"), ESearchCase::IgnoreCase);
			const float Eta = F.EtaS - Since;
			if (bBeat[bHostile ? 0 : 1] || Eta < -60.f)
			{
				continue;   // (already scheduled; or long overdue: a picture that has not been renewed)
			}
			Add(bHostile, F.Ships, FMath::Max(0.f, Eta), Out.GateRel);
		}
	}
	return true;
}

bool UAstraBattleSubsystem::GetGateView(FVector& OutPos, FVector& OutAxis, float& OutRadiusCm) const
{
	if (Ships.Num() == 0 || !Landmarks.IsValidIndex(GateLandmark) || !Landmarks[GateLandmark].Actor)
	{
		return false;
	}
	const AStaticMeshActor* A = Landmarks[GateLandmark].Actor;
	FVector Origin, Extent;
	A->GetActorBounds(false, Origin, Extent);
	OutPos = Origin;
	OutAxis = A->GetActorForwardVector();
	OutRadiusCm = (float)Extent.Size();
	return true;
}

void UAstraBattleSubsystem::GetAllyViews(int32 Max, TArray<FVector4>& Out) const
{
	Out.Reset();
	if (Ships.Num() == 0)
	{
		return;
	}
	TArray<const FAstraBattleShip*> Near;
	for (int32 i = 1; i < Ships.Num(); ++i)
	{
		const FAstraBattleShip& S = Ships[i];
		if (S.bAlive && S.Side == EAstraSide::Astra && !S.bCraft && !S.bFixture && !S.bWreck && !S.bDerelict)
		{
			Near.Add(&S);
		}
	}
	const FVector P = Ships[0].Pos;
	Near.Sort([&P](const FAstraBattleShip& A, const FAstraBattleShip& B) { return FVector::DistSquared(A.Pos, P) < FVector::DistSquared(B.Pos, P); });
	for (int32 i = 0; i < Near.Num() && Out.Num() < Max; ++i)
	{
		Out.Add(FVector4(ToWorld(Near[i]->Pos), 100.f * Near[i]->Radius));
	}
}
