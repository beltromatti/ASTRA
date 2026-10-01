#include "AstraTransportCommandlet.h"

#include "ASTRA.h"
#include "AstraTransportBench.h"
#include "AstraTransportRules.h"
#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "HAL/PlatformTime.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"

using namespace AstraXport;

namespace
{
	struct FXCheck
	{
		FString Name;
		bool bPass = true;
		FString Detail;
	};
	TArray<FXCheck> XChecks;
	TSharedRef<FJsonObject> XRecord = MakeShared<FJsonObject>();

	void XCheck(const TCHAR* Name, bool bPass, const FString& Detail)
	{
		XChecks.Add({Name, bPass, Detail});
		UE_LOG(LogASTRA, Display, TEXT("[Transport] %s %-44s %s"), bPass ? TEXT("PASS") : TEXT("FAIL"), Name, *Detail);
	}

	// ---------------------------------------------------------------------------------------------------- the made-up world
	// The Aquila: 799 x 140 x 92 m (data/war/classes.json), the box's centre 7.53 m aft of the mesh's origin.
	const FVector AquilaHalf(399.73, 69.857, 46.2);
	const FVector AcheronHalf(293.5, 52.5, 74.5);

	FHull MakeAquila()
	{
		FHull H;
		H.bPresent = true;
		H.Id = TEXT("AQUILA");
		H.Name = TEXT("ASN Aquila");
		H.Side = EAllegiance::Own;
		H.Pos = FVector::ZeroVector;
		H.Centre = FVector(-7.53, 0.0, 0.0);
		H.Half = AquilaHalf;
		H.RadiusM = 407.f;
		return H;
	}

	FEnv BaseEnv()
	{
		FEnv E;
		E.Own = MakeAquila();
		return E;
	}

	FHull MakeShip(const TCHAR* Id, const TCHAR* Name, EAllegiance Side, const FVector& Pos, const FRotator& Rot = FRotator::ZeroRotator, const FVector& Half = AcheronHalf)
	{
		FHull H;
		H.bPresent = true;
		H.Id = Id;
		H.Name = Name;
		H.Side = Side;
		H.Pos = Pos;
		H.Centre = Pos;
		H.Att = Rot.Quaternion();
		H.Half = Half;
		H.RadiusM = (float)Half.X;
		return H;
	}

	void SetFaces(FHull& H, float F)
	{
		for (int32 f = 0; f < NumFaces; ++f)
		{
			H.Frac[f] = F;
		}
	}

	FSubject Person(const TCHAR* Name, int32 Roster = 1)
	{
		FSubject S;
		S.Kind = ESubject::Person;
		S.Id = FString::Printf(TEXT("npc%d"), Roster);
		S.Label = Name;
		S.Roster = Roster;
		return S;
	}
	FSubject CaptainSubject()
	{
		FSubject S;
		S.Kind = ESubject::Captain;
		S.Id = TEXT("captain");
		S.Label = TEXT("the Captain");
		S.MassKg = 95.f;
		return S;
	}
	FSubject Cargo(float Kg)
	{
		FSubject S;
		S.Kind = ESubject::Cargo;
		S.Id = TEXT("cargo");
		S.Label = FString::Printf(TEXT("%.0f kg of supplies"), Kg);
		S.MassKg = Kg;
		return S;
	}

	FEnd PadEnd(int32 Pad, bool bOccupied = false, bool bEmergency = false)
	{
		FEnd E;
		E.Kind = EEndKind::Pad;
		E.bPad = true;
		E.bEmergencyPad = bEmergency;
		E.Pad = Pad;
		E.bPadOccupied = bOccupied;
		E.Label = FString::Printf(TEXT("pad %d"), Pad + 1);
		E.CompKind = TEXT("transporter");
		return E;
	}
	FEnd SiteEnd(const TCHAR* Label, const char* Kind, float Fire = 0.f, float Air = 1.f, bool bInhibited = false)
	{
		FEnd E;
		E.Kind = EEndKind::Site;
		E.Label = Label;
		E.CompKind = FName(ANSI_TO_TCHAR(Kind));
		E.bInhibited = bInhibited;
		E.Room.Fire = Fire;
		E.Room.Air = Air;
		return E;
	}
	FEnd ShipEnd(const FHull& H)
	{
		FEnd E;
		E.Kind = EEndKind::Ship;
		E.Label = H.Name;
		E.Ship = H;
		return E;
	}
	FEnd SurfaceEnd(uint8 Owner = 0)
	{
		FEnd E;
		E.Kind = EEndKind::Surface;
		E.Label = TEXT("New Ravenna, Port Aurelius Field");
		E.World = TEXT("New Ravenna");
		E.Owner = Owner;
		E.DirBody = FVector(0, 0, -1);
		return E;
	}
	FRequest Req(const FEnd& From, const FEnd& To, std::initializer_list<FSubject> Subjects)
	{
		FRequest R;
		R.From = From;
		R.To = To;
		for (const FSubject& S : Subjects)
		{
			R.Subjects.Add(S);
		}
		return R;
	}
	FString Blockers(const FVerdict& V)
	{
		FString Out;
		for (const FBlocker& B : V.Blockers)
		{
			Out += FString::Printf(TEXT("%s%s"), Out.IsEmpty() ? TEXT("") : TEXT(","), *B.Code.ToString());
		}
		return Out.IsEmpty() ? FString(TEXT("-")) : Out;
	}
	FString Line(const FVerdict& V)
	{
		return FString::Printf(TEXT("ok=%d blockers=[%s] lock %.2f s, quality %.0f%%, range %.0f km (reach %.0f), faces %s/%s, jam %.0f%%, cycle %.1f s, %.0f MW"), V.bOk ? 1 : 0, *Blockers(V), V.LockS, 100.f * V.Quality,
		                       V.RangeKm, V.MaxRangeKm, FaceName(V.OwnFace), FaceName(V.TheirFace), 100.f * V.Jam, V.CycleS, V.EnergyMW);
	}
	bool Near(float A, float B, float Tol)
	{
		return FMath::Abs(A - B) <= Tol;
	}

	// ---------------------------------------------------------------------------------------------------- the rules' scripted cases
	void RulesBench(const FTuning& T)
	{
		// ======================================================================================================== the data
		{
			FTuning Def;
			FTuning Loaded;
			const bool bRead = Loaded.Load(FPaths::Combine(FPaths::ProjectDir(), TEXT("data/ship/aquila_transport.json")));
			const bool bSame = bRead && Near(Def.MaxRangeKm, Loaded.MaxRangeKm, 0.01f) && Near(Def.LockSurfaceS, Loaded.LockSurfaceS, 0.01f) && Near(Def.CycleMW, Loaded.CycleMW, 0.01f) &&
			                   Near(Def.AccelBlock, Loaded.AccelBlock, 0.01f) && Near((float)Def.DaisCentre.X, (float)Loaded.DaisCentre.X, 0.01f) && Loaded.Emergency.Num() == 2 &&
			                   Loaded.InhibitKinds.Contains(FName(TEXT("magazine"))) && Loaded.Pads == 6 && Near(Def.GroundJam[3], Loaded.GroundJam[3], 0.001f) && Near(Def.ScatterBelow, Loaded.ScatterBelow, 0.001f);
			XCheck(TEXT("data: the file reads and agrees with the code"), bSame, bRead ? Loaded.Describe() : FString(TEXT("data/ship/aquila_transport.json did not read")));
		}

		// ======================================================================================================== faces
		{
			// the face a line leaves a box through, normalised by the box's own measures: a ship 800 x 140 x 92 is hit "on the flank" far sooner than a sphere would say
			const FQuat Id = FQuat::Identity;
			const int32 FBow = FaceToward(Id, FVector::ZeroVector, AquilaHalf, FVector(5000, 0, 0));
			const int32 FStern = FaceToward(Id, FVector::ZeroVector, AquilaHalf, FVector(-5000, 0, 0));
			const int32 FPort = FaceToward(Id, FVector::ZeroVector, AquilaHalf, FVector(0, -5000, 0));
			const int32 FStar = FaceToward(Id, FVector::ZeroVector, AquilaHalf, FVector(0, 5000, 0));
			const int32 FDors = FaceToward(Id, FVector::ZeroVector, AquilaHalf, FVector(0, 0, 5000));
			const int32 FVent = FaceToward(Id, FVector::ZeroVector, AquilaHalf, FVector(0, 0, -5000));
			XCheck(TEXT("faces: the six axes"), FBow == 0 && FStern == 1 && FPort == 2 && FStar == 3 && FDors == 4 && FVent == 5,
			       FString::Printf(TEXT("+x %s, -x %s, -y %s, +y %s, +z %s, -z %s"), FaceName(FBow), FaceName(FStern), FaceName(FPort), FaceName(FStar), FaceName(FDors), FaceName(FVent)));
			// a target 100 m ahead and 100 m to starboard of the centre: along x 100 of 400 (0.25), along y 100 of 70 (1.43): it is the flank
			const int32 Flank = FaceToward(Id, FVector::ZeroVector, AquilaHalf, FVector(100, 100, 0));
			const int32 Quarter = FaceToward(Id, FVector::ZeroVector, AquilaHalf, FVector(900, 100, 0));
			XCheck(TEXT("faces: normalised by the box's measures"), Flank == 3 && Quarter == 0, FString::Printf(TEXT("(100,100) is %s, (900,100) is %s"), FaceName(Flank), FaceName(Quarter)));
			// the rotated hull: the Acheron turned 90 deg (bow to +y) with us at -x of it sees us on its starboard
			const FQuat Yaw90 = FRotator(0, 90, 0).Quaternion();
			const int32 Turned = FaceToward(Yaw90, FVector(5000, 0, 0), AcheronHalf, FVector::ZeroVector);
			XCheck(TEXT("faces: a rotated hull"), Turned == 3, FString::Printf(TEXT("the Acheron with her bow to +y sees the Aquila on her %s"), FaceName(Turned)));
			FHull H = MakeShip(TEXT("T-23"), TEXT("Acheron"), EAllegiance::Hostile, FVector(5000, 0, 0));
			SetFaces(H, 1.f);
			H.Frac[2] = 0.04f;
			const bool bClosed = !FaceOpen(H, 3, T), bSpent = FaceOpen(H, 2, T);
			H.bShieldsUp = false;
			const bool bDown = FaceOpen(H, 3, T);
			XCheck(TEXT("faces: open means spent, down or disabled"), bClosed && bSpent && bDown, TEXT("sector at 100% closed, at 4% open, shields down: open"));
			H.bShieldsUp = true;
			H.bDisabled = true;
			XCheck(TEXT("faces: a disabled ship has none"), FaceOpen(H, 3, T), TEXT("disabled"));
		}

		// ======================================================================================================== aboard
		{
			FEnv E = BaseEnv();
			FVerdict V = Evaluate(T, E, Req(PadEnd(2), SiteEnd(TEXT("Main Engineering"), "engineering"), {Person(TEXT("Lieutenant Sato"))}));
			XCheck(TEXT("aboard: pad to a room"), V.bOk && Near(V.LockS, T.LockAboardS, 0.01f) && V.Quality > 0.99f && !V.bNeedsOwnWindow && Near(V.CycleS, 8.f, 0.01f) && Near(V.EnergyMW, 40.f, 0.01f), Line(V));
			V = Evaluate(T, E, Req(SiteEnd(TEXT("Mess Hall"), "mess"), SiteEnd(TEXT("Medbay"), "medbay"), {Person(TEXT("A"), 1), Person(TEXT("B"), 2), Person(TEXT("C"), 3), Person(TEXT("D"), 4), Person(TEXT("E"), 5), Person(TEXT("F"), 6)}));
			XCheck(TEXT("aboard: a party of six, 70 MW"), V.bOk && Near(V.EnergyMW, 70.f, 0.01f), Line(V));
			V = Evaluate(T, E, Req(PadEnd(0), PadEnd(1), {Person(TEXT("A"), 1), Person(TEXT("B"), 2), Person(TEXT("C"), 3), Person(TEXT("D"), 4), Person(TEXT("E"), 5), Person(TEXT("F"), 6), Person(TEXT("G"), 7)}));
			XCheck(TEXT("aboard: seven do not fit six pads"), !V.bOk && V.HasBlocker(TEXT("pads")), Line(V));
			V = Evaluate(T, E, Req(PadEnd(0), SiteEnd(TEXT("Hold"), "storage"), {Cargo(2600.f)}));
			XCheck(TEXT("aboard: 2.6 t is more than a pad carries"), !V.bOk && V.HasBlocker(TEXT("mass")), Line(V));
			V = Evaluate(T, E, Req(PadEnd(0), SiteEnd(TEXT("Hold"), "storage"), {Cargo(1900.f)}));
			XCheck(TEXT("aboard: 1.9 t does"), V.bOk, Line(V));
			V = Evaluate(T, E, Req(PadEnd(0), SiteEnd(TEXT("VLS Magazine"), "magazine", 0.f, 1.f, true), {Person(TEXT("Sato"))}));
			XCheck(TEXT("aboard: a pattern-shielded room takes no beam"), !V.bOk && V.HasBlocker(TEXT("inhibit")), Line(V));
			V = Evaluate(T, E, Req(SiteEnd(TEXT("Armory"), "armory", 0.f, 1.f, true), PadEnd(1), {Person(TEXT("Sato"))}));
			XCheck(TEXT("aboard: nor does one send out"), !V.bOk && V.HasBlocker(TEXT("inhibit")), Line(V));
			V = Evaluate(T, E, Req(PadEnd(0), PadEnd(1, true), {Person(TEXT("Sato"))}));
			XCheck(TEXT("aboard: nobody lands on someone"), !V.bOk && V.HasBlocker(TEXT("occupied")), Line(V));
			FRequest Burning = Req(SiteEnd(TEXT("Mess Hall"), "mess"), SiteEnd(TEXT("Main Galley"), "galley", 0.5f), {Person(TEXT("Sato"))});
			V = Evaluate(T, E, Burning);
			XCheck(TEXT("aboard: not into a fire"), !V.bOk && V.HasBlocker(TEXT("hazard")) && V.Blockers[0].bOverridable, Line(V));
			Burning.bOverrideHazard = true;
			V = Evaluate(T, E, Burning);
			XCheck(TEXT("aboard: unless the Captain says so"), V.bOk, Line(V));
			V = Evaluate(T, E, Req(SiteEnd(TEXT("Main Galley"), "galley", 0.5f), SiteEnd(TEXT("Medbay"), "medbay"), {Person(TEXT("Sato"))}));
			XCheck(TEXT("aboard: out of a fire is the rescue the pads are for"), V.bOk, Line(V));
			V = Evaluate(T, E, Req(PadEnd(0), SiteEnd(TEXT("Deck 4 Corridor"), "corridor", 0.f, 0.3f), {Person(TEXT("Sato"))}));
			XCheck(TEXT("aboard: nor into no air"), !V.bOk && V.HasBlocker(TEXT("hazard")), Line(V));
			FSubject Gone = Person(TEXT("Crewman Berg"));
			Gone.bDead = true;
			V = Evaluate(T, E, Req(PadEnd(0), PadEnd(1), {Gone}));
			XCheck(TEXT("aboard: the dead are not carried"), !V.bOk && V.HasBlocker(TEXT("subject")), Line(V));
			FSubject Lost = Person(TEXT("Crewman Nobody"));
			Lost.bFound = false;
			V = Evaluate(T, E, Req(PadEnd(0), PadEnd(1), {Lost}));
			XCheck(TEXT("aboard: no pattern, no beam"), !V.bOk && V.HasBlocker(TEXT("subject")), Line(V));
			// motion, jamming, shields and range are about a beam that leaves the hull: inside the ship none of them matters
			E.AccelMps2 = 14.f;
			E.TurnDegS = 3.f;
			E.bGateLane = true;
			V = Evaluate(T, E, Req(PadEnd(0), SiteEnd(TEXT("Medbay"), "medbay"), {CaptainSubject()}));
			XCheck(TEXT("aboard: hard burn, turning, in the Gate's lane: no matter"), V.bOk, Line(V));
		}

		// ======================================================================================================== the surface
		{
			FEnv E = BaseEnv();
			FRequest R = Req(PadEnd(2), SurfaceEnd(0), {CaptainSubject()});
			FVerdict V = Evaluate(T, E, R);
			const float ExpectLock = T.LockSurfaceS + T.LockPer1000KmS * T.OrbitKm / 1000.f;
			XCheck(TEXT("surface: our shields up: no"), !V.bOk && V.HasBlocker(TEXT("shields_own")) && V.OwnFace == 5, Line(V));
			R.bShieldWindow = true;
			V = Evaluate(T, E, R);
			XCheck(TEXT("surface: with a shield window, yes"), V.bOk && V.bNeedsOwnWindow && Near(V.LockS, ExpectLock, 0.05f) && V.Quality > 0.99f, Line(V));
			E.Own.bShieldsUp = false;
			R.bShieldWindow = false;
			V = Evaluate(T, E, R);
			XCheck(TEXT("surface: shields down: the lock takes 5.7 s"), V.bOk && !V.bNeedsOwnWindow && Near(V.LockS, ExpectLock, 0.05f), Line(V));
			// one open face is enough: the ventral sector spent, the others full
			E.Own.bShieldsUp = true;
			E.Own.Frac[5] = 0.02f;
			V = Evaluate(T, E, R);
			XCheck(TEXT("surface: one spent face is enough"), V.bOk && V.bOwnOpen, Line(V));
			E.Own.Frac[5] = 1.f;
			E.Own.Frac[4] = 0.f;      // ... but it must be the face the beam leaves through: the dorsal is the wrong one
			V = Evaluate(T, E, R);
			XCheck(TEXT("surface: the wrong face spent is no help"), !V.bOk && V.HasBlocker(TEXT("shields_own")), Line(V));
			E.Own.bShieldsUp = false;
			// who holds the world
			const uint8 Owners[5] = {0, 1, 2, 3, 4};
			const TCHAR* OwnerNames[5] = {TEXT("astra"), TEXT("guilds"), TEXT("contested"), TEXT("mandate"), TEXT("silent")};
			FString Table;
			bool bOwnersOk = true;
			for (int32 i = 0; i < 5; ++i)
			{
				FRequest Ri = Req(PadEnd(2), SurfaceEnd(Owners[i]), {CaptainSubject()});
				const FVerdict Vi = Evaluate(T, E, Ri);
				Table += FString::Printf(TEXT("%s: %s q%.0f%% lock %.1f s;  "), OwnerNames[i], Vi.bOk ? TEXT("ok") : *Blockers(Vi), 100.f * Vi.Quality, Vi.LockS);
				if (i == 3)
				{
					bOwnersOk &= !Vi.bOk && Vi.HasBlocker(TEXT("quality")) && Vi.Jam > 0.5f && Vi.Jam < T.JamBlock;
					Ri.bForce = true;
					bOwnersOk &= Evaluate(T, E, Ri).bOk;
				}
				else
				{
					bOwnersOk &= Vi.bOk;
				}
			}
			XCheck(TEXT("surface: who holds the world: a Mandate world jams the beam below a lock, the Captain's word forces it"), bOwnersOk, Table);
			// the planet is "down": which face the beam leaves by depends on the attitude: the planet above the Aquila is the dorsal face
			FEnd Up = SurfaceEnd(0);
			Up.DirBody = FVector(0, 0.2, 0.98).GetSafeNormal();
			V = Evaluate(T, E, Req(PadEnd(2), Up, {CaptainSubject()}));
			XCheck(TEXT("surface: the face follows where the planet is"), V.OwnFace == 4, Line(V));
		}

		// ======================================================================================================== ships
		{
			FEnv E = BaseEnv();
			E.Own.bShieldsUp = false;
			// an allied ship at 12 km on the bow, quiet
			FHull Ally = MakeShip(TEXT("T-02"), TEXT("ASN Vigilant"), EAllegiance::Allied, FVector(12000, 0, 0), FRotator(0, 180, 0), FVector(153, 27, 32));
			SetFaces(Ally, 1.f);
			FRequest R = Req(PadEnd(0), ShipEnd(Ally), {Person(TEXT("Lieutenant Sato")), Person(TEXT("Corporal Reyes"), 2)});
			FVerdict V = Evaluate(T, E, R);
			XCheck(TEXT("ship: an allied ship opens her face when she is not in a fight"), V.bOk && V.bTheirsOpen && V.OwnFace == 0 && V.TheirFace == 0 && V.Notes.ContainsByPredicate([](const FString& S) { return S.Contains(TEXT("opens her")); }), Line(V));
			XCheck(TEXT("ship: a lock on a ship takes 3.5 s and the range"), Near(V.LockS, T.LockShipS + T.LockPer1000KmS * 0.012f, 0.05f), Line(V));
			Ally.bEngaged = true;
			R = Req(PadEnd(0), ShipEnd(Ally), {Person(TEXT("Lieutenant Sato"))});
			V = Evaluate(T, E, R);
			XCheck(TEXT("ship: in a fight she cannot"), !V.bOk && V.HasBlocker(TEXT("shields_theirs")), Line(V));
			// a hostile ship: her sector must be spent: the face the beam enters is the one that looks at us
			FHull Foe = MakeShip(TEXT("T-23"), TEXT("Cocytus"), EAllegiance::Hostile, FVector(5000, 0, 0), FRotator(0, 180, 0));   // bow to us
			SetFaces(Foe, 1.f);
			V = Evaluate(T, E, Req(PadEnd(0), ShipEnd(Foe), {Person(TEXT("Corporal Reyes"))}));
			XCheck(TEXT("ship: a hostile ship's shield stops the beam"), !V.bOk && V.HasBlocker(TEXT("shields_theirs")) && V.TheirFace == 0 && V.Blockers[0].Why.Contains(TEXT("100%")), Line(V));
			Foe.Frac[1] = 0.02f;           // her stern is spent: the wrong face
			V = Evaluate(T, E, Req(PadEnd(0), ShipEnd(Foe), {Person(TEXT("Corporal Reyes"))}));
			XCheck(TEXT("ship: her stern spent, her bow facing us: still no"), !V.bOk && V.HasBlocker(TEXT("shields_theirs")), Line(V));
			Foe.Frac[0] = 0.03f;           // her bow, the face that looks at us
			V = Evaluate(T, E, Req(PadEnd(0), ShipEnd(Foe), {Person(TEXT("Corporal Reyes"))}));
			XCheck(TEXT("ship: the face that looks at us spent: yes"), V.bOk && V.bTheirsOpen && Near(V.LockS, T.LockShipS + T.LockHostileExtraS + T.LockPer1000KmS * 0.005f, 0.05f), Line(V));
			SetFaces(Foe, 1.f);
			Foe.bDisabled = true;
			V = Evaluate(T, E, Req(PadEnd(0), ShipEnd(Foe), {Person(TEXT("Corporal Reyes"))}));
			XCheck(TEXT("ship: a disabled ship has no shield"), V.bOk, Line(V));
			Foe.bDisabled = false;
			Foe.bFacesKnown = false;
			V = Evaluate(T, E, Req(PadEnd(0), ShipEnd(Foe), {Person(TEXT("Corporal Reyes"))}));
			XCheck(TEXT("ship: no firm track: the crew is told it does not know"), V.bOk && V.Unknown.Num() == 1, Line(V));
			// our own shield on, with the window
			E.Own.bShieldsUp = true;
			Foe.bFacesKnown = true;
			Foe.Frac[0] = 0.f;
			FRequest Rw = Req(PadEnd(0), ShipEnd(Foe), {Person(TEXT("Corporal Reyes"))});
			V = Evaluate(T, E, Rw);
			const bool bNoWindow = !V.bOk && V.HasBlocker(TEXT("shields_own")) && V.OwnFace == 0;
			Rw.bShieldWindow = true;
			V = Evaluate(T, E, Rw);
			XCheck(TEXT("ship: our shield needs the Captain's window"), bNoWindow && V.bOk && V.bNeedsOwnWindow, Line(V));
			// the face logic from the other side: a target abeam sees us on its own flank
			FHull Beam = MakeShip(TEXT("T-30"), TEXT("Styx"), EAllegiance::Hostile, FVector(0, 4000, 0), FRotator(0, 0, 0), FVector(193, 40, 57));
			SetFaces(Beam, 1.f);
			E.Own.bShieldsUp = false;
			V = Evaluate(T, E, Req(PadEnd(0), ShipEnd(Beam), {Person(TEXT("Corporal Reyes"))}));
			XCheck(TEXT("ship: abeam, the beam leaves by our starboard and enters by her port"), V.OwnFace == 3 && V.TheirFace == 2, Line(V));
		}

		// ======================================================================================================== range
		{
			FEnv E = BaseEnv();
			E.Own.bShieldsUp = false;
			auto FarShip = [](double Km) { return MakeShip(TEXT("T-02"), TEXT("ASN Vigilant"), EAllegiance::Allied, FVector(Km * 1000.0, 0, 0), FRotator(0, 180, 0)); };
			FVerdict V = Evaluate(T, E, Req(PadEnd(0), ShipEnd(FarShip(29000)), {Person(TEXT("Sato"))}));
			XCheck(TEXT("range: 29 000 km: yes"), V.bOk && Near(V.RangeKm, 29000.f, 1.f) && Near(V.MaxRangeKm, 30000.f, 1.f), Line(V));
			V = Evaluate(T, E, Req(PadEnd(0), ShipEnd(FarShip(31000)), {Person(TEXT("Sato"))}));
			XCheck(TEXT("range: 31 000 km: no"), !V.bOk && V.HasBlocker(TEXT("range")), Line(V));
			E.Main.Power = 0.5f;
			V = Evaluate(T, E, Req(PadEnd(0), ShipEnd(FarShip(10000)), {Person(TEXT("Sato"))}));
			const bool bHalf = V.bOk && Near(V.MaxRangeKm, 30000.f * FMath::Sqrt(0.5f), 5.f);
			V = Evaluate(T, E, Req(PadEnd(0), ShipEnd(FarShip(20000)), {Person(TEXT("Sato"))}));
			const bool bEdge = V.HasBlocker(TEXT("quality"));          // inside the reach but at its edge, a weak room cannot build the lock
			V = Evaluate(T, E, Req(PadEnd(0), ShipEnd(FarShip(25000)), {Person(TEXT("Sato"))}));
			XCheck(TEXT("range: a room at half power reaches 21 200 km, and builds a lock only well inside it"), bHalf && bEdge && !V.bOk && V.HasBlocker(TEXT("range")), Line(V));
			E.Main.Power = 1.f;
			E.SensorsPower = 0.5f;
			V = Evaluate(T, E, Req(PadEnd(0), ShipEnd(FarShip(25000)), {Person(TEXT("Sato"))}));
			XCheck(TEXT("range: so does a sensor net at half power"), !V.bOk && V.HasBlocker(TEXT("range")) && V.MaxRangeKm < 22000.f, Line(V));
			E.SensorsPower = 1.5f;
			V = Evaluate(T, E, Req(PadEnd(0), ShipEnd(FarShip(29000)), {Person(TEXT("Sato"))}));
			XCheck(TEXT("range: more power to the sensors does not stretch the canon's 30 000 km"), V.MaxRangeKm <= 30000.01f, Line(V));
		}

		// ======================================================================================================== jamming
		{
			FEnv E = BaseEnv();
			E.Own.bShieldsUp = false;
			FHull Ally = MakeShip(TEXT("T-02"), TEXT("ASN Vigilant"), EAllegiance::Allied, FVector(8000, 0, 0), FRotator(0, 180, 0));
			SetFaces(Ally, 1.f);
			FString Row;
			float Prev = 2.f;
			bool bMono = true;
			for (const double Deg : {0.0, 5.0, 10.0, 15.0, 25.0, 60.0})
			{
				FEnv Ej = E;
				FHull J = MakeShip(TEXT("T-40"), TEXT("Acheron (jamming)"), EAllegiance::Hostile, FVector(30000.0 * FMath::Cos(FMath::DegreesToRadians(Deg)), 30000.0 * FMath::Sin(FMath::DegreesToRadians(Deg)), 0));
				J.bJamming = true;
				Ej.Others.Add(J);
				const FVerdict Vj = Evaluate(T, Ej, Req(PadEnd(0), ShipEnd(Ally), {Person(TEXT("Sato"))}));
				Row += FString::Printf(TEXT("%.0f deg: jam %.0f%% %s;  "), Deg, 100.f * Vj.Jam, Vj.bOk ? TEXT("ok") : *Blockers(Vj));
				bMono &= Vj.Jam <= Prev + 1e-4f;
				Prev = Vj.Jam;
			}
			FEnv Ea = E;
			FHull Jam0 = MakeShip(TEXT("T-40"), TEXT("Acheron (jamming)"), EAllegiance::Hostile, FVector(30000, 0, 0));
			Jam0.bJamming = true;
			Ea.Others.Add(Jam0);
			const FVerdict V0 = Evaluate(T, Ea, Req(PadEnd(0), ShipEnd(Ally), {Person(TEXT("Sato"))}));
			Ea.Others[0].Centre = Ea.Others[0].Pos = FVector(0, 30000, 0);
			const FVerdict V90 = Evaluate(T, Ea, Req(PadEnd(0), ShipEnd(Ally), {Person(TEXT("Sato"))}));
			XCheck(TEXT("jam: the strobe along the line blocks the lock, off the line it does not"), bMono && !V0.bOk && V0.HasBlocker(TEXT("jam")) && V90.bOk && V90.Jam < 0.01f, Row);
			// the Aquila's friends do not jam her
			FEnv Ef = E;
			FHull Friendly = Jam0;
			Friendly.Side = EAllegiance::Allied;
			Ef.Others.Add(Friendly);
			XCheck(TEXT("jam: an ally's ECM is not an enemy's"), Evaluate(T, Ef, Req(PadEnd(0), ShipEnd(Ally), {Person(TEXT("Sato"))})).bOk, TEXT("allied jammer on the line"));
			// the target is the jammer: the strobe burns through when she is close
			FString Burn;
			bool bBurn = true;
			for (const double Km : {2.0, 4.0, 6.0, 8.0, 12.0, 20.0})
			{
				FEnv Eb = E;
				FHull Foe = MakeShip(TEXT("T-23"), TEXT("Cocytus"), EAllegiance::Hostile, FVector(Km * 1000.0, 0, 0), FRotator(0, 180, 0));
				Foe.bJamming = true;
				SetFaces(Foe, 0.f);
				Eb.Others.Add(Foe);
				const FVerdict Vb = Evaluate(T, Eb, Req(PadEnd(0), ShipEnd(Foe), {Person(TEXT("Sato"))}));
				Burn += FString::Printf(TEXT("%.0f km: jam %.0f%% %s;  "), Km, 100.f * Vb.Jam, Vb.bOk ? TEXT("ok") : *Blockers(Vb));
				if (Km <= 4.0)
				{
					bBurn &= Vb.bOk;
				}
				if (Km >= 12.0)
				{
					bBurn &= Vb.HasBlocker(TEXT("jam"));
				}
			}
			XCheck(TEXT("jam: a jamming target burns through inside a few km, not beyond"), bBurn, Burn);
		}

		// ======================================================================================================== motion, the Gate
		{
			FEnv E = BaseEnv();
			E.Own.bShieldsUp = false;
			FHull Ally = MakeShip(TEXT("T-02"), TEXT("ASN Vigilant"), EAllegiance::Allied, FVector(8000, 0, 0), FRotator(0, 180, 0));
			SetFaces(Ally, 1.f);
			auto Try = [&](float Accel, float Turn) { FEnv Em = E; Em.AccelMps2 = Accel; Em.TurnDegS = Turn; return Evaluate(T, Em, Req(PadEnd(0), ShipEnd(Ally), {Person(TEXT("Sato"))})); };
			const FVerdict V0 = Try(0.f, 0.f), V4 = Try(4.f, 0.f), V10 = Try(10.f, 0.f), W1 = Try(0.f, 1.2f), W3 = Try(0.f, 2.6f);
			XCheck(TEXT("motion: steady: a clean lock"), V0.bOk && V0.Quality > 0.99f, Line(V0));
			XCheck(TEXT("motion: a hard burn costs the lock, a harder one forbids it"), V4.bOk && V4.Quality < V0.Quality - 0.1f && !V10.bOk && V10.HasBlocker(TEXT("motion")), FString::Printf(TEXT("4 m/s2: q%.0f%%; 10 m/s2: %s"), 100.f * V4.Quality, *Blockers(V10)));
			XCheck(TEXT("motion: so does turning"), W1.bOk && W1.Quality < 0.9f && !W3.bOk && W3.HasBlocker(TEXT("motion")), FString::Printf(TEXT("1.2 deg/s: q%.0f%%; 2.6 deg/s: %s"), 100.f * W1.Quality, *Blockers(W3)));
			FEnv Eg = E;
			Eg.GateKm = 80.f;
			FVerdict Vg = Evaluate(T, Eg, Req(PadEnd(0), ShipEnd(Ally), {Person(TEXT("Sato"))}));
			const float Q80 = Vg.Quality;
			Eg.GateKm = 40.f;
			Vg = Evaluate(T, Eg, Req(PadEnd(0), ShipEnd(Ally), {Person(TEXT("Sato"))}));
			const float Q40 = Vg.Quality;
			const bool bNear = Vg.bOk;
			Eg.GateKm = 20.f;
			Vg = Evaluate(T, Eg, Req(PadEnd(0), ShipEnd(Ally), {Person(TEXT("Sato"))}));
			XCheck(TEXT("gate: the field thins the lock out to 60 km and shuts the beam inside 25"), Q80 > 0.99f && Q40 < Q80 && bNear && !Vg.bOk && Vg.HasBlocker(TEXT("gate")), FString::Printf(TEXT("80 km: q%.0f%%; 40 km: q%.0f%%; 20 km: %s"), 100.f * Q80, 100.f * Q40, *Blockers(Vg)));
			Eg.GateKm = -1.f;
			Eg.bGateLane = true;
			Vg = Evaluate(T, Eg, Req(PadEnd(0), ShipEnd(Ally), {Person(TEXT("Sato"))}));
			XCheck(TEXT("gate: in the lane: never"), !Vg.bOk && Vg.HasBlocker(TEXT("gate")), Line(Vg));
		}

		// ======================================================================================================== the room
		{
			FEnv E = BaseEnv();
			const FRequest Inside = Req(PadEnd(0), SiteEnd(TEXT("Medbay"), "medbay"), {Person(TEXT("Sato"))});
			FVerdict V = Evaluate(T, E, Inside);
			const float Lock1 = V.LockS, Cycle1 = V.CycleS;
			E.Main.Power = 0.4f;
			V = Evaluate(T, E, Inside);
			XCheck(TEXT("room: on reduced power: slower lock, longer cycle, still works"), V.bOk && V.LockS > Lock1 * 1.2f && V.CycleS > Cycle1 * 1.2f && V.Notes.Num() > 0, FString::Printf(TEXT("%s | notes %d"), *Line(V), V.Notes.Num()));
			E.Main.Power = 0.08f;
			V = Evaluate(T, E, Inside);
			XCheck(TEXT("room: no power: no beam"), !V.bOk && V.HasBlocker(TEXT("room")), Line(V));
			// inside the hull the pads' own sensors do the lock: the sensor net and the ship's heat matter only to a beam that leaves it
			{
				FEnv Hot = BaseEnv();
				Hot.SensorsPower = 0.f;
				Hot.HeatFactor = 0.55f;
				const FVerdict Vin = Evaluate(T, Hot, Inside);
				FHull Far = MakeShip(TEXT("T-02"), TEXT("ASN Vigilant"), EAllegiance::Allied, FVector(20000, 0, 0), FRotator(0, 180, 0));
				Hot.Own.bShieldsUp = false;
				const FVerdict Vout = Evaluate(T, Hot, Req(PadEnd(0), ShipEnd(Far), {Person(TEXT("Sato"))}));
				XCheck(TEXT("room: inside the hull a dead sensor net and a hot ship cost the lock nothing; outside they do"), Vin.bOk && Near(Vin.Quality, 1.f, 0.01f) && Vout.Quality < 0.7f, FString::Printf(TEXT("inside %.0f%%, to a ship %.0f%%"), 100.f * Vin.Quality, 100.f * Vout.Quality));
			}
			E.Main.Power = 1.f;
			E.Main.Wreck = 0.95f;
			V = Evaluate(T, E, Inside);
			XCheck(TEXT("room: wrecked: no beam"), !V.bOk && V.HasBlocker(TEXT("room")), Line(V));
			E.Main.Wreck = 0.f;
			// a post that cannot be left, and a target that has left the plot
			{
				FRequest Posted = Inside;
				Posted.Subjects[0].Barred = TEXT("Lieutenant Sato is on station at the helm post: it cannot be left by the beam");
				const FVerdict Vp = Evaluate(T, BaseEnv(), Posted);
				FHull Gone = MakeShip(TEXT("T-02"), TEXT("ASN Vigilant"), EAllegiance::Allied, FVector(20000, 0, 0), FRotator(0, 180, 0));
				Gone.bPresent = false;
				FEnv Eg = BaseEnv();
				Eg.Own.bShieldsUp = false;
				const FVerdict Vg = Evaluate(T, Eg, Req(PadEnd(0), ShipEnd(Gone), {Person(TEXT("Sato"))}));
				XCheck(TEXT("subject: a post that cannot be left is refused; so is a ship that has left the plot"), !Vp.bOk && Vp.HasBlocker(TEXT("subject")) && !Vg.bOk && Vg.HasBlocker(TEXT("target")), FString::Printf(TEXT("%s | %s"), *Blockers(Vp), *Blockers(Vg)));
			}
			E.Main.Fire = 0.5f;
			V = Evaluate(T, E, Inside);
			XCheck(TEXT("room: on fire: the operators are out"), !V.bOk && V.HasBlocker(TEXT("room")), Line(V));
			E.Main.Fire = 0.f;
			E.bReactorOn = false;
			V = Evaluate(T, E, Inside);
			XCheck(TEXT("room: no reactor, no beam"), !V.bOk && V.HasBlocker(TEXT("power")), Line(V));
			// the Medbay's emergency pads: their own system, short range
			E = BaseEnv();
			E.Own.bShieldsUp = false;
			E.Main.Power = 0.f;
			FHull Close = MakeShip(TEXT("T-02"), TEXT("ASN Vigilant"), EAllegiance::Allied, FVector(100000, 0, 0), FRotator(0, 180, 0));
			FHull Distant = MakeShip(TEXT("T-03"), TEXT("ASN Praetorian"), EAllegiance::Allied, FVector(500000, 0, 0), FRotator(0, 180, 0));
			V = Evaluate(T, E, Req(PadEnd(0, false, true), ShipEnd(Close), {Person(TEXT("Sato"))}));
			const bool bNearOk = V.bOk && V.bEmergencySystem && Near(V.MaxRangeKm, T.EmergencyRangeKm, 1.f);
			V = Evaluate(T, E, Req(PadEnd(0, false, true), ShipEnd(Distant), {Person(TEXT("Sato"))}));
			const bool bFarNo = !V.bOk && V.HasBlocker(TEXT("range"));
			V = Evaluate(T, E, Req(PadEnd(0), ShipEnd(Close), {Person(TEXT("Sato"))}));
			XCheck(TEXT("room: the Medbay's pads reach 400 km when the main room is dark"), bNearOk && bFarNo && !V.bOk && V.HasBlocker(TEXT("room")), Line(V));
		}

		// ======================================================================================================== the lock's life
		{
			FTuning Tn = T;
			FLock L;
			L.Begin(5.72f);
			float T0 = 0.f, Acquired = -1.f;
			for (; T0 < 12.f; T0 += 0.05f)
			{
				L.Tick(Tn, 0.05f, 0.99f, 1.f);
				if (L.State == FLock::EState::Locked && Acquired < 0.f)
				{
					Acquired = T0;
				}
			}
			XCheck(TEXT("lock: builds in the time the rules say"), Near(Acquired, 5.72f, 0.2f) && L.Quality > 0.97f && L.IsLocked(), FString::Printf(TEXT("locked at %.2f s (wanted 5.72), quality %.0f%%"), Acquired, 100.f * L.Quality));
			// the quality falls under the hold line: degraded; back: locked
			float DegradedAt = -1.f;
			for (float t = 0.f; t < 4.f; t += 0.05f)
			{
				L.Tick(Tn, 0.05f, 0.30f, 1.f);
				if (L.State == FLock::EState::Degraded && DegradedAt < 0.f)
				{
					DegradedAt = t;
				}
			}
			const bool bDegraded = L.State == FLock::EState::Degraded && DegradedAt > 0.3f && DegradedAt < 1.4f;
			for (float t = 0.f; t < 8.f; t += 0.05f)
			{
				L.Tick(Tn, 0.05f, 0.9f, 1.f);
			}
			XCheck(TEXT("lock: degrades fast, recovers slowly, is not lost while the target holds"), bDegraded && L.State == FLock::EState::Locked, FString::Printf(TEXT("degraded after %.2f s; later %s, quality %.0f%%"), DegradedAt, FLock::Name(L.State), 100.f * L.Quality));
			float LostAt = -1.f;
			for (float t = 0.f; t < 6.f && L.State != FLock::EState::Lost; t += 0.05f)
			{
				L.Tick(Tn, 0.05f, 0.05f, 1.f);
				LostAt = t;
			}
			XCheck(TEXT("lock: lost when the quality stays under the line"), L.State == FLock::EState::Lost && LostAt > 1.f && LostAt < 3.5f, FString::Printf(TEXT("lost %.2f s after the quality collapsed"), LostAt));
			FLock Blocked;
			Blocked.Begin(3.f);
			for (float t = 0.f; t < 10.f; t += 0.05f)
			{
				Blocked.Tick(Tn, 0.05f, 0.10f, 1.f);
			}
			XCheck(TEXT("lock: never builds under conditions that forbid it"), Blocked.State == FLock::EState::Acquiring && Blocked.Progress < 0.05f, FString::Printf(TEXT("progress %.0f%% after 10 s at target 10%%"), 100.f * Blocked.Progress));
		}

		// ======================================================================================================== the arrival
		{
			FRandomStream Rng(7);
			auto Freq = [&](float Q, bool bForced, int32 N, float& OutDelay, float& OutOffset, float& OutScatter)
			{
				int32 D = 0, O = 0, S = 0;
				float SumDelay = 0.f;
				for (int32 i = 0; i < N; ++i)
				{
					const FArrival A = RollArrival(T, Q, bForced, Rng);
					D += A.Kind == EArrival::Delayed;
					O += A.Kind == EArrival::Offset;
					S += A.Kind == EArrival::Scattered;
					SumDelay += A.Kind == EArrival::Delayed ? A.DelayS : 0.f;
				}
				OutDelay = (float)D / N;
				OutOffset = (float)O / N;
				OutScatter = (float)S / N;
				return D ? SumDelay / D : 0.f;
			};
			float D, O, S;
			Freq(1.f, false, 20000, D, O, S);
			const bool bClean = D == 0.f && O == 0.f && S == 0.f;
			const float MeanDelay = Freq(0.5f, false, 40000, D, O, S);
			XCheck(TEXT("arrival: a perfect lock arrives clean; at 50% some wait in the buffer, some land off the mark, none are lost"),
			       bClean && Near(D, T.DelayP * 0.5f, 0.02f) && Near(O, (1.f - D) * T.OffsetP * 0.5f, 0.02f) && S == 0.f && MeanDelay > T.DelayMinS && MeanDelay < T.DelayMaxS,
			       FString::Printf(TEXT("q100%%: clean; q50%%: delayed %.1f%% (mean %.1f s), offset %.1f%%, scattered %.1f%%"), 100.f * D, MeanDelay, 100.f * O, 100.f * S));
			Freq(0.1f, true, 40000, D, O, S);
			const float WantScatter = (T.ScatterBelow - 0.1f) / T.ScatterBelow * 0.5f;
			XCheck(TEXT("arrival: only a lock forced on the Captain's word can scatter a pattern"), Near(S, WantScatter, 0.02f), FString::Printf(TEXT("q10%% forced: scattered %.1f%% (expected %.1f%%)"), 100.f * S, 100.f * WantScatter));
			Freq(0.1f, false, 40000, D, O, S);
			XCheck(TEXT("arrival: never otherwise"), S == 0.f, FString::Printf(TEXT("q10%% not forced: scattered %.1f%%"), 100.f * S));
		}

		// ======================================================================================================== the numbers
		{
			XCheck(TEXT("numbers: 40 MW and 8 s, more subjects more power, a weak room a longer cycle"),
			       Near(EnergyFor(T, 1), 40.f, 0.01f) && Near(EnergyFor(T, 6), 70.f, 0.01f) && Near(CycleSeconds(T, FRoomState()), 8.f, 0.01f) && Near(CycleSeconds(T, [] { FRoomState R; R.Power = 0.5f; return R; }()), 10.4f, 0.01f),
			       FString::Printf(TEXT("1 subject %.0f MW, 6 subjects %.0f MW; cycle %.1f s at full power, %.1f s at half"), EnergyFor(T, 1), EnergyFor(T, 6), CycleSeconds(T, FRoomState()), CycleSeconds(T, [] { FRoomState R; R.Power = 0.5f; return R; }())));
		}
	}
}

void AstraXportBenchCheck(const TCHAR* Name, bool bPass, const FString& Detail)
{
	XCheck(Name, bPass, Detail);
}

UAstraTransportCommandlet::UAstraTransportCommandlet()
{
	IsClient = false;
	IsServer = false;
	IsEditor = true;                 // the editor's plugins assume an editor engine even here (as the war and life benches)
	LogToConsole = true;
	ShowErrorCount = true;
}

int32 UAstraTransportCommandlet::Main(const FString& Params)
{
	FString Scenario = TEXT("all");
	int32 Seed = 1;
	FParse::Value(*Params, TEXT("scenario="), Scenario);
	FParse::Value(*Params, TEXT("seed="), Seed);
	FString Out = FPaths::ProjectSavedDir() / TEXT("Transport/run.json");
	FParse::Value(*Params, TEXT("out="), Out);
	FMath::RandInit(Seed);
	FMath::SRandInit(Seed);
	XChecks.Reset();
	const bool bAll = Scenario == TEXT("all");
	const double Wall0 = FPlatformTime::Seconds();

	FTuning T;
	const bool bData = T.Load(FPaths::Combine(FPaths::ProjectDir(), TEXT("data/ship/aquila_transport.json")));
	UE_LOG(LogASTRA, Display, TEXT("[Transport] %s: %s"), bData ? TEXT("data/ship/aquila_transport.json") : TEXT("(no data file: the defaults)"), *T.Describe());
	if (bAll || Scenario == TEXT("rules"))
	{
		RulesBench(T);
	}
	if (bAll || Scenario == TEXT("world"))
	{
		AstraXportRunWorldBench(FPaths::Combine(FPaths::ProjectSavedDir(), TEXT("Transport/fixtures")));
	}

	int32 Failed = 0;
	TArray<TSharedPtr<FJsonValue>> CheckRows;
	for (const FXCheck& C : XChecks)
	{
		Failed += C.bPass ? 0 : 1;
		TSharedRef<FJsonObject> R = MakeShared<FJsonObject>();
		R->SetStringField(TEXT("name"), C.Name);
		R->SetBoolField(TEXT("pass"), C.bPass);
		R->SetStringField(TEXT("detail"), C.Detail);
		CheckRows.Add(MakeShared<FJsonValueObject>(R));
	}
	XRecord->SetArrayField(TEXT("checks"), CheckRows);
	XRecord->SetStringField(TEXT("verdict"), Failed == 0 ? TEXT("PASS") : TEXT("FAIL"));
	XRecord->SetNumberField(TEXT("wall_s"), FPlatformTime::Seconds() - Wall0);
	FString Text;
	const TSharedRef<TJsonWriter<>> W = TJsonWriterFactory<>::Create(&Text);
	FJsonSerializer::Serialize(XRecord, W);
	FFileHelper::SaveStringToFile(Text, *Out);
	UE_LOG(LogASTRA, Display, TEXT("[Transport] %d checks, %d failed in %.1f s. VERDICT: %s"), XChecks.Num(), Failed, FPlatformTime::Seconds() - Wall0, Failed == 0 ? TEXT("PASS") : TEXT("FAIL"));
	return Failed == 0 ? 0 : 1;
}
