// Read-only views of the battle for the stations' executors and the main viewscreen: what the Aquila knows, with the fog
// of war applied (a bearing-only contact has no range, no speed, no damage state).

#include "AstraBattleSubsystem.h"
#include "AstraWarClasses.h"
#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"

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
		// what the Aquila believes, not the truth: an unclassified or cold contact is of no known side until it shows
		// itself (the holo table's rule, GetHoloBlips); a decoy is made to look like a Mandate warship
		const bool bUnknown = (S.bFog ? !S.bClassified : !S.bIdentified) || S.bCold;
		V.bUnknown = bUnknown && !S.bHostile && !S.bGhost;
		V.Side = S.bGhost ? EAstraSide::Mandate : (V.bUnknown ? EAstraSide::Neutral : S.Side);
		V.Track = S.Track;
		V.bCraft = S.bCraft;
		V.bDerelict = S.bDerelict || S.bDisabled;      // a ship without power is a hulk: no threat, no target
		if (S.bDisabled && V.Side == EAstraSide::Mandate)
		{
			V.Side = EAstraSide::Neutral;
		}
		V.bCapital = !S.bCraft && !V.bDerelict && V.Side != EAstraSide::Neutral;
		V.bFleeing = S.bFleeing;
		V.bJamming = S.bJamming;
		V.bFiringAtUs = S.Side == EAstraSide::Mandate && !S.bHoldFire && !S.bDisabled && (S.TargetId == P.Id || S.FireTarget == P.Id);
		V.RadiusM = S.Radius;
		const bool bFirm = S.Track >= 2;
		// the class and the label change only when what is known of it does (a list of hundreds is read every frame: the strings are kept)
		const uint8 Key = (bUnknown ? 1 : 0) | (S.bIdentified ? 2 : 0);
		if (S.CvKey != Key)
		{
			S.CvKey = Key;
			S.CvClass = !bUnknown ? S.Class : FString();
			FString Head, Short;
			if (!S.CvClass.Split(TEXT(", "), &Head, &Short))
			{
				Short = S.CvClass;       // "Kharon Mandate cruiser, Acheron class" -> "Acheron class"
			}
			S.CvLabel = S.bIdentified ? S.Name : (!S.CvClass.IsEmpty() ? FString::Printf(TEXT("%s (%s)"), *S.ContactId, *Short) : S.ContactId);
		}
		V.Class = S.CvClass;
		V.Label = S.CvLabel;
		V.BearingDeg = BearingDeg(P.Pos, S.Pos);
		V.MarkDeg = MarkDeg(P.Pos, S.Pos);
		if (bFirm)
		{
			V.Pos = S.Pos;
			V.Vel = S.Vel;
			V.RangeKm = FVector::Dist(P.Pos, S.Pos) / 1000.0;
			V.HullFrac = S.HullMax > 0.f ? S.Hull / S.HullMax : -1.f;
			V.ShieldFrac = S.ShieldMax > 0.f ? S.Shield / S.ShieldMax : -1.f;
			V.Actor = S.Actor;
			V.Flare = S.DriveFlare;
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

UAstraBattleSubsystem::FWeaponRanges UAstraBattleSubsystem::GetWeaponRanges(const FString& ContactId) const
{
	FWeaponRanges R;
	if (Ships.Num() == 0)
	{
		return R;
	}
	const FAstraBattleShip* S = ContactId.IsEmpty() ? &Ships[0] : FindByContact(ContactId);
	if (!S || !S->bAlive)
	{
		return R;
	}
	// what the Aquila can know: her own side by datalink; the others once their class is known (classified, or identified)
	const bool bKnown = S->bPlayer || S->Side == EAstraSide::Astra || (S->bFog ? S->bClassified : S->bIdentified);
	if (!bKnown || S->bCraft || S->bGhost || S->bDerelict)
	{
		return R;
	}
	const AstraWar::FShipClass* C = S->ClassKey.IsNone() ? nullptr : AstraWar::FindClass(S->ClassKey);
	R.RailKm = S->RailDamage > 0.f ? S->RailRange / 1000.f : 0.f;
	R.LaserKm = (S->Dmg.bModel ? S->LaserDamage > 0.f : true) ? S->LaserRange / 1000.f : 0.f;
	R.MissileKm = ((C && C->Missiles > 0) || S->Missiles > 0) ? S->MissileRange / 1000.f : 0.f;
	R.PointDefenseKm = S->PDChannels > 0 ? S->PDRange / 1000.f : 0.f;
	return R;
}

bool UAstraBattleSubsystem::WasDestroyed(const FString& ContactId) const
{
	for (const FAstraBattleShip& S : Ships)
	{
		if (!S.bAlive && S.ContactId.Equals(ContactId, ESearchCase::IgnoreCase))
		{
			return true;
		}
	}
	return false;
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

TSharedRef<FJsonObject> UAstraBattleSubsystem::DebugState() const
{
	TSharedRef<FJsonObject> O = MakeShared<FJsonObject>();
	O->SetNumberField(TEXT("t"), Time);
	TArray<TSharedPtr<FJsonValue>> Arr;
	const FVector P0 = Ships.Num() ? Ships[0].Pos : FVector::ZeroVector;
	for (const FAstraBattleShip& S : Ships)
	{
		TSharedRef<FJsonObject> J = MakeShared<FJsonObject>();
		J->SetNumberField(TEXT("id"), S.Id);
		J->SetStringField(TEXT("c"), S.ContactId);
		J->SetStringField(TEXT("name"), S.Name);
		J->SetStringField(TEXT("side"), S.Side == EAstraSide::Astra ? TEXT("astra") : (S.Side == EAstraSide::Mandate ? TEXT("mandate") : TEXT("neutral")));
		J->SetBoolField(TEXT("craft"), S.bCraft);
		J->SetBoolField(TEXT("alive"), S.bAlive);
		J->SetStringField(TEXT("fate"), S.bAlive ? (S.bDisabled ? TEXT("disabled") : TEXT("alive")) : ((S.Mode == EAstraShipMode::Dead && !(S.bPlayer && bSandbox)) ? TEXT("destroyed") : TEXT("gone")));   // gone: left the theatre, or a craft that landed
		if (!S.bAlive)
		{
			Arr.Add(MakeShared<FJsonValueObject>(J));
			continue;
		}
		const FVector R = (S.Pos - P0) / 1000.0;
		J->SetArrayField(TEXT("km"), {MakeShared<FJsonValueNumber>(FMath::RoundToDouble(R.X * 100.0) / 100.0), MakeShared<FJsonValueNumber>(FMath::RoundToDouble(R.Y * 100.0) / 100.0),
		                              MakeShared<FJsonValueNumber>(FMath::RoundToDouble(R.Z * 100.0) / 100.0)});
		J->SetNumberField(TEXT("v"), FMath::RoundToDouble(S.Vel.Size()));
		J->SetNumberField(TEXT("hull"), FMath::RoundToDouble(100.0 * S.Hull / FMath::Max(1.f, S.HullMax)));
		J->SetNumberField(TEXT("shield"), FMath::RoundToDouble(100.0 * S.Shield / FMath::Max(1.f, S.ShieldMax)));
		J->SetNumberField(TEXT("mode"), (int32)S.Mode);
		J->SetNumberField(TEXT("target"), S.TargetId);
		J->SetNumberField(TEXT("stance"), S.Stance);
		J->SetNumberField(TEXT("track"), S.Track);
		J->SetBoolField(TEXT("fleeing"), S.bFleeing);
		J->SetBoolField(TEXT("hold_fire"), S.bHoldFire);
		if (S.bCraft)
		{
			J->SetStringField(TEXT("mission"), S.Mission);
			J->SetNumberField(TEXT("mission_target"), S.MissionTarget);
		}
		else
		{
			J->SetNumberField(TEXT("missiles"), S.Missiles);
			if (S.Dmg.bModel)
			{
				// the physical state: shield sectors (bow, stern, port, starboard, dorsal, ventral) and structure by section
				// (bow, mid, stern) in percent, and the systems (engines, sensors, hangar, bridge, reactor, point defence)
				TArray<TSharedPtr<FJsonValue>> Sh, St, Sy;
				for (int32 f = 0; f < 6; ++f) { Sh.Add(MakeShared<FJsonValueNumber>(FMath::RoundToDouble(100.0 * S.Dmg.Sector[f] / FMath::Max(1.f, S.Dmg.SectorMax[f])))); }
				for (int32 k = 0; k < 3; ++k) { St.Add(MakeShared<FJsonValueNumber>(FMath::RoundToDouble(100.0 * S.Dmg.Structure[k] / FMath::Max(1.f, S.Dmg.StructureMax[k])))); }
				for (int32 k = 0; k < 6; ++k) { Sy.Add(MakeShared<FJsonValueNumber>(FMath::RoundToDouble(100.0 * S.Dmg.Sys[k]))); }
				J->SetArrayField(TEXT("shields"), Sh);
				J->SetArrayField(TEXT("sections"), St);
				J->SetArrayField(TEXT("systems"), Sy);
			}
		}
		Arr.Add(MakeShared<FJsonValueObject>(J));
	}
	O->SetArrayField(TEXT("ships"), Arr);
	O->SetArrayField(TEXT("groups"), GroupsJson()->GetArrayField(TEXT("groups")));
	return O;
}
