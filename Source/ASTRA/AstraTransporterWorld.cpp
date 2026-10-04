// TELETRASPORTO — the subsystem's reading of the world and of the words of an order (docs/TELETRASPORTO.md §3, §4): the battle's hulls and shields, the ship's motion and
// power, the damage model's rooms, the plan and VITA's people, the planet; and the other way: "the Captain", "npc17", "the doctor", "marines 6", "pad 3", "Main Engineering",
// "T-02", "the surface" turned into subjects and ends the rules can judge.

#include "AstraTransporterSubsystem.h"

#include "ASTRA.h"
#include "ASTRACharacter.h"
#include "ASTRAPlayerController.h"
#include "AstraBattleSubsystem.h"
#include "AstraBoardSubsystem.h"
#include "AstraCrewMember.h"
#include "AstraDamageModel.h"
#include "AstraDeckStreaming.h"
#include "AstraLadderSubsystem.h"
#include "AstraLifeSubsystem.h"
#include "AstraShipPlan.h"
#include "AstraShipSubsystem.h"
#include "AstraStations.h"
#include "AstraWarClasses.h"
#include "Components/CapsuleComponent.h"
#include "Engine/World.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Kismet/GameplayStatics.h"

using namespace AstraXport;

namespace
{
	/** A phrase as the resolver compares it: lower case, no apostrophes, words joined by single spaces, no leading article. */
	FString XpNorm(const FString& In)
	{
		FString S = In.ToLower();
		for (const TCHAR* Junk : {TEXT("'"), TEXT("\""), TEXT("’"), TEXT("."), TEXT(";"), TEXT(":")})
		{
			S = S.Replace(Junk, TEXT(""));
		}
		S = S.Replace(TEXT(","), TEXT(" ")).Replace(TEXT("_"), TEXT(" "));
		TArray<FString> W;
		S.ParseIntoArrayWS(W);
		S = FString::Join(W, TEXT(" "));
		for (const TCHAR* Art : {TEXT("the "), TEXT("a "), TEXT("an ")})
		{
			if (S.StartsWith(Art))
			{
				S = S.Mid(FCString::Strlen(Art));
				break;
			}
		}
		return S;
	}

	/** "T-23", "t23", "ship:T-23" -> "T23"; "A-01" -> "A1"; empty when it is not a contact id. */
	FString XpContactKey(const FString& In)
	{
		FString S = In.ToUpper();
		S.RemoveFromStart(TEXT("SHIP:"));
		S.TrimStartAndEndInline();
		if (S.Len() < 2 || !FChar::IsAlpha(S[0]))
		{
			return FString();
		}
		FString Digits;
		for (int32 i = 1; i < S.Len(); ++i)
		{
			if (FChar::IsDigit(S[i]))
			{
				Digits.AppendChar(S[i]);
			}
			else if (S[i] != TEXT('-') && S[i] != TEXT(' '))
			{
				return FString();
			}
		}
		return Digits.IsEmpty() ? FString() : FString::Printf(TEXT("%c%d"), S[0], FCString::Atoi(*Digits));
	}

	int32 XpOwnerIndex(const FString& Owner)
	{
		const FString O = Owner.ToLower();
		return O == TEXT("astra") ? 0 : (O == TEXT("guilds") ? 1 : (O == TEXT("contested") ? 2 : (O == TEXT("mandate") ? 3 : (O == TEXT("silent") ? 4 : 1))));
	}

	/** The first run of digits in a phrase, or INDEX_NONE. */
	int32 XpFirstNumber(const FString& In)
	{
		FString D;
		for (const TCHAR Ch : In)
		{
			if (FChar::IsDigit(Ch))
			{
				D.AppendChar(Ch);
			}
			else if (!D.IsEmpty())
			{
				break;
			}
		}
		return D.IsEmpty() ? INDEX_NONE : FCString::Atoi(*D);
	}

	bool XpHasWord(const FString& S, const TCHAR* Word)
	{
		TArray<FString> W;
		S.ParseIntoArrayWS(W);
		return W.Contains(FString(Word));
	}
}

// ================================================================================================ the services the subsystem reads
UAstraShipSubsystem* UAstraTransporterSubsystem::Ship() const { return GetWorld() ? GetWorld()->GetSubsystem<UAstraShipSubsystem>() : nullptr; }
UAstraBattleSubsystem* UAstraTransporterSubsystem::Battle() const { return GetWorld() ? GetWorld()->GetSubsystem<UAstraBattleSubsystem>() : nullptr; }
UAstraBoardSubsystem* UAstraTransporterSubsystem::Board() const { return GetWorld() ? GetWorld()->GetSubsystem<UAstraBoardSubsystem>() : nullptr; }
UAstraLifeSubsystem* UAstraTransporterSubsystem::Life() const { return GetWorld() ? GetWorld()->GetSubsystem<UAstraLifeSubsystem>() : nullptr; }
UAstraShipPlan* UAstraTransporterSubsystem::Plan() const { return GetWorld() ? GetWorld()->GetSubsystem<UAstraShipPlan>() : nullptr; }
UAstraDeckStreaming* UAstraTransporterSubsystem::Streaming() const { return GetWorld() ? GetWorld()->GetSubsystem<UAstraDeckStreaming>() : nullptr; }
UAstraStationsSubsystem* UAstraTransporterSubsystem::Stations() const { return GetWorld() ? GetWorld()->GetSubsystem<UAstraStationsSubsystem>() : nullptr; }

// ================================================================================================ the room's frame
bool UAstraTransporterSubsystem::RoomFrame(FVector& OutOriginCm, float& OutYawDeg) const
{
	OutOriginCm = RoomOriginCm;
	OutYawDeg = RoomYawDeg;
	return bRoomKnown;
}

FVector UAstraTransporterSubsystem::LocalToWorldCm(const FVector& LocalM) const
{
	const FVector Rot = FRotator(0.f, RoomYawDeg, 0.f).RotateVector(FVector(LocalM.X, LocalM.Y, 0.0));
	return RoomOriginCm + Rot * 100.0 + FVector(0.0, 0.0, LocalM.Z * 100.0);
}

FVector UAstraTransporterSubsystem::ChiefStandCm() const { return LocalToWorldCm(FVector(T.ChiefStand.X, T.ChiefStand.Y, 0.0)); }
float UAstraTransporterSubsystem::ChiefYaw() const { return RoomYawDeg + T.ChiefYaw; }
FVector UAstraTransporterSubsystem::EmitterCm() const { return LocalToWorldCm(T.EmitterM); }

bool UAstraTransporterSubsystem::WallScreenCm(FVector& OutCentreCm, float& OutYawDeg, FVector2D& OutSizeCm) const
{
	if (!bRoomKnown)
	{
		return false;
	}
	OutCentreCm = LocalToWorldCm(T.WallScreenM);
	OutYawDeg = RoomYawDeg + T.WallScreenYaw;
	OutSizeCm = T.WallScreenSizeM * 100.0;
	return true;
}

// ================================================================================================ the world as the rules want it
namespace
{
	EAllegiance XpSide(EAstraSide S, bool bDerelict)
	{
		if (bDerelict)
		{
			return EAllegiance::Derelict;
		}
		return S == EAstraSide::Astra ? EAllegiance::Allied : (S == EAstraSide::Mandate ? EAllegiance::Hostile : EAllegiance::Neutral);
	}
}

FRoomState UAstraTransporterSubsystem::RoomOf(const FString& CompId, const FString& Name) const
{
	FRoomState R;
	R.Name = Name;
	const UAstraShipSubsystem* S = Ship();
	if (!S || CompId.IsEmpty())
	{
		return R;
	}
	const FAstraDamageModel& M = S->GetInterior();
	if (!M.IsReady())
	{
		return R;
	}
	const int32* Idx = M.GetMap().CompByName.Find(FName(*CompId));
	if (!Idx)
	{
		return R;
	}
	if (const FAstraDmgState* St = M.Find(*Idx))
	{
		R.Power = St->Power;
		R.Wreck = St->Wreck;
		R.Air = St->Air;
		R.Fire = St->Fire;
		R.Smoke = St->Smoke;
		R.Heat = St->Heat;
		R.bLocked = St->bLocked;
		R.bGutted = St->bGutted;
	}
	return R;
}

void UAstraTransporterSubsystem::FillRoom(FRoomState& Out, const FString& CompId, const TCHAR* Name) const
{
	Out = RoomOf(CompId, Name);
}

namespace
{
	/** One contact of the plot as a hull for the rules: what the sensors give (position, size), what the damage view lets be known (attitude, the shield sectors of a ship that is firmly tracked and classified, or of
	 *  our own side by datalink); the box is the class's own measures. A hull whose faces are not known says so (the rules refuse to aim at it). */
	bool XpFillHull(const UAstraBattleSubsystem* B, const UAstraBattleSubsystem::FContactView& C, FHull& Out)
	{
		Out = FHull();
		Out.bPresent = true;
		Out.Id = C.ContactId;
		Out.Name = C.Label;
		Out.Side = XpSide(C.Side, C.bDerelict);
		Out.Pos = C.Pos;
		Out.Vel = C.Vel;
		Out.RadiusM = C.RadiusM;
		Out.bJamming = C.bJamming;
		Out.bShieldsUp = true;
		Out.bFacesKnown = false;
		for (float& F : Out.Frac)
		{
			F = 1.f;
		}
		Out.Att = FQuat::Identity;
		FVector Half(C.RadiusM, C.RadiusM * 0.3, C.RadiusM * 0.3);
		float Mid = 0.f;
		const FName Key = AstraWar::KeyFor(C.Class.IsEmpty() ? C.Label : C.Class, FString());
		if (!Key.IsNone())
		{
			if (const AstraWar::FShipClass* Cls = AstraWar::FindClass(Key); Cls && Cls->Box.Valid())
			{
				Half = FVector(Cls->Box.Hx, Cls->Box.Hy, Cls->Box.Hz);
				Mid = Cls->Box.Mid;
			}
		}
		UAstraBattleSubsystem::FDamageView View;
		if (B->GetDamageViewById(C.Id, View))
		{
			Out.Att = View.Att;
			Out.Pos = View.Pos;
			Out.bDisabled = View.bDisabled;
			if (View.Detail >= 2)
			{
				Out.bFacesKnown = true;
				for (int32 f = 0; f < NumFaces; ++f)
				{
					Out.Frac[f] = View.ShieldFrac[f];
				}
			}
		}
		else if (C.Side == EAstraSide::Astra)
		{
			Out.bFacesKnown = true;      // our own side by datalink (a craft or a ship with no model: shields as one lump)
			for (float& F : Out.Frac)
			{
				F = C.ShieldFrac >= 0.f ? C.ShieldFrac : 1.f;
			}
		}
		Out.Half = Half;
		Out.Centre = Out.Pos + Out.Att.RotateVector(FVector(Mid, 0.0, 0.0));
		return true;
	}
}

bool UAstraTransporterSubsystem::FillShip(FHull& Out, const FString& ContactId) const
{
	const UAstraBattleSubsystem* B = Battle();
	if (!B)
	{
		return false;
	}
	const FString Want = XpContactKey(ContactId);
	for (const UAstraBattleSubsystem::FContactView& C : B->Contacts())
	{
		if (C.ContactId.Equals(ContactId, ESearchCase::IgnoreCase) || (!Want.IsEmpty() && XpContactKey(C.ContactId) == Want))
		{
			return XpFillHull(B, C, Out);
		}
	}
	return false;
}

void UAstraTransporterSubsystem::BuildEnv(FEnv& Out) const
{
	Out = FEnv();
	const UAstraShipSubsystem* S = Ship();
	const UAstraBattleSubsystem* B = Battle();
	FHull& Own = Out.Own;
	Own.bPresent = true;
	Own.Id = TEXT("AQUILA");
	Own.Name = TEXT("ASN Aquila");
	Own.Side = EAllegiance::Own;
	Own.Half = FVector(399.73, 69.857, 46.2);
	float Mid = -7.53f;
	if (const AstraWar::FShipClass* Cls = AstraWar::FindClass(FName(TEXT("aquila"))); Cls && Cls->Box.Valid())
	{
		Own.Half = FVector(Cls->Box.Hx, Cls->Box.Hy, Cls->Box.Hz);
		Mid = Cls->Box.Mid;
	}
	Own.RadiusM = (float)Own.Half.X;
	if (B)
	{
		Own.Pos = B->PlayerPos();
		Own.Att = B->PlayerAtt();
		Own.Vel = B->PlayerVel();
		UAstraBattleSubsystem::FDamageView View;
		if (B->GetDamageView(TEXT("AQUILA"), View))
		{
			for (int32 f = 0; f < NumFaces; ++f)
			{
				Own.Frac[f] = View.ShieldFrac[f];
			}
			Own.bDisabled = View.bDisabled;
		}
		Out.bGateLane = B->IsInLane();
		Out.GateKm = (float)B->GateDistanceKm();
	}
	Own.Centre = Own.Pos + Own.Att.RotateVector(FVector(Mid, 0.0, 0.0));
	Own.bShieldsUp = S ? (S->AreShieldsUp() && S->PowerFactor(TEXT("shields")) > 0.05f) : true;
	Out.AccelMps2 = AccelSm;
	Out.TurnDegS = TurnSm;
	if (S)
	{
		Out.SensorsPower = S->PowerFactor(TEXT("sensors"));
		Out.ShieldsPower = S->PowerFactor(TEXT("shields"));
		Out.HeatFactor = S->HeatFactor();
		Out.bReactorOn = !S->IsShipLost() && S->GetReactorPct() > 3.f;
	}
	FillRoom(Out.Main, RoomCompId, TEXT("the Transporter Room"));
	FillRoom(Out.Emergency, TEXT("medbay"), TEXT("the Medbay"));
	if (!bRoomKnown)
	{
		Out.Main.bExists = false;
	}
	if (B)
	{
		for (const UAstraBattleSubsystem::FContactView& C : B->Contacts())
		{
			FHull H;
			if (!C.bCraft && XpFillHull(B, C, H))                  // (a craft neither jams nor opens a face: it has no pad)
			{
				Out.Others.Add(H);
			}
		}
		// an allied ship in the middle of a fight does not open her face: a hostile warship within a few km of her
		for (FHull& A : Out.Others)
		{
			if (A.Side != EAllegiance::Allied)
			{
				continue;
			}
			for (const FHull& E : Out.Others)
			{
				if (E.Side == EAllegiance::Hostile && E.RadiusM > 60.f && FVector::Dist(E.Pos, A.Pos) < T.AllyEngagedKm * 1000.0)
				{
					A.bEngaged = true;
					break;
				}
			}
		}
	}
}

// ================================================================================================ where the Captain is
bool UAstraTransporterSubsystem::CaptainFeet(FVector& OutFeetCm, float& OutYaw, bool& bOnGround, bool& bSeated) const
{
	bSeated = false;
	// ABBORDAGGI: in the troop bay of a boat that flies there is no pattern to lock on (a hull in the way); on the decks of the ship the marines are fighting aboard he is away from the Aquila, as one on a world is
	const UAstraBoardSubsystem* Bd = Board();
	if (Bd && Bd->CaptainInBoat())
	{
		return false;
	}
	const bool bAboardOther = Bd && Bd->CaptainAboardOtherShip();
	if (bTestCaptain)
	{
		OutFeetCm = TestFeetCm;
		OutYaw = 0.f;
		bOnGround = bTestPlanetside || bAboardOther;
		return true;
	}
	const APawn* P = UGameplayStatics::GetPlayerPawn(this, 0);
	const ACharacter* C = Cast<ACharacter>(P);
	if (!C)
	{
		return false;                                          // a Falcon, a pod: there is no pattern to lock on
	}
	OutFeetCm = P->GetActorLocation() - FVector(0.0, 0.0, P->GetDefaultHalfHeight());
	OutYaw = P->GetActorRotation().Yaw;
	const UAstraShipSubsystem* S = Ship();
	bOnGround = (S && S->IsPlanetside()) || bAboardOther;
	if (const AASTRAPlayerController* PC = Cast<AASTRAPlayerController>(P->GetController()))
	{
		bSeated = PC->IsSeated();
	}
	return true;
}

bool UAstraTransporterSubsystem::CaptainOnFoot() const
{
	FVector F;
	float Y;
	bool bG, bS;
	return CaptainFeet(F, Y, bG, bS);
}

void UAstraTransporterSubsystem::SetTestCaptain(bool bOn, const FVector& FeetCm)
{
	bTestCaptain = bOn;
	TestFeetCm = FeetCm;
	if (!bOn)
	{
		bTestPlanetside = false;
	}
	PushTestCaptain();
}

void UAstraTransporterSubsystem::PushTestCaptain() const
{
	// the one Captain of the tests is the ship's (the air and the fire work on him), VITA's (bodies are made for him) and the decks' (what he stands in is loaded)
	if (!bTestCaptain)
	{
		if (UAstraLifeSubsystem* L = Life())
		{
			L->ClearTestCaptain();
		}
		if (UAstraShipSubsystem* S = Ship())
		{
			S->SetTestCaptain(false, FVector::ZeroVector);
		}
		return;
	}
	if (UAstraShipSubsystem* S = Ship())
	{
		S->SetTestCaptain(true, TestFeetCm);
	}
	if (UAstraLifeSubsystem* L = Life())
	{
		L->SetTestCaptain(TestFeetCm, TestFeetCm + FVector(0.0, 0.0, 165.0), FVector::ForwardVector);
	}
	if (UAstraDeckStreaming* D = Streaming())
	{
		D->SetTestPosition(TestFeetCm);
	}
}

void UAstraTransporterSubsystem::PlaceCaptain(const FVector& FeetCm, float YawDeg, bool bOnGround)
{
	if (bTestCaptain)
	{
		TestFeetCm = FeetCm;
		bTestPlanetside = bOnGround;
		PushTestCaptain();
		return;
	}
	APawn* P = UGameplayStatics::GetPlayerPawn(this, 0);
	if (!P)
	{
		return;
	}
	if (AASTRAPlayerController* PC = Cast<AASTRAPlayerController>(P->GetController()))
	{
		PC->StandUp();                                         // out of the chair: the beam takes him from where he stands
	}
	if (UWorld* W = GetWorld())
	{
		if (UAstraLadderSubsystem* Ladder = W->GetSubsystem<UAstraLadderSubsystem>())
		{
			Ladder->Release(P);                                // (from a Jefferies ladder: it lets go of him first, or it would put him back on the rungs)
		}
	}
	if (AASTRACharacter* A = Cast<AASTRACharacter>(P))
	{
		A->ResetPosture();
	}
	const FVector At = FeetCm + FVector(0.0, 0.0, P->GetDefaultHalfHeight() + 2.0);
	P->SetActorLocationAndRotation(At, FRotator(0.f, YawDeg, 0.f), false, nullptr, ETeleportType::TeleportPhysics);
	if (AController* C = P->GetController())
	{
		C->SetControlRotation(FRotator(0.f, YawDeg, 0.f));
	}
	if (ACharacter* Ch = Cast<ACharacter>(P))
	{
		if (UCharacterMovementComponent* M = Ch->GetCharacterMovement())
		{
			M->StopMovementImmediately();
		}
	}
	(void)bOnGround;
}

void UAstraTransporterSubsystem::LockCaptain(bool bOn)
{
	if (bTestCaptain || bOn == bInputLocked)
	{
		return;
	}
	APawn* P = UGameplayStatics::GetPlayerPawn(this, 0);
	AController* C = P ? P->GetController() : nullptr;
	if (!C)
	{
		return;
	}
	// (the controller counts what it is asked to ignore: every lock is given back once)
	bInputLocked = bOn;
	C->SetIgnoreMoveInput(bOn);
	C->SetIgnoreLookInput(bOn);
}

// ================================================================================================ pads and who stands on them
bool UAstraTransporterSubsystem::PadOccupiedBy(const FAstraXportPad& P, FString& OutWho) const
{
	OutWho.Reset();
	const float R2 = FMath::Square(P.RadiusCm + 25.f);
	auto OnPad = [&P, R2](const FVector& Feet) { return FVector::DistSquared2D(Feet, P.PosCm) < R2 && FMath::Abs(Feet.Z - P.PosCm.Z) < 70.f; };
	FVector Feet;
	float Yaw;
	bool bG, bS;
	if (CaptainFeet(Feet, Yaw, bG, bS) && !bG && OnPad(Feet))
	{
		OutWho = TEXT("the Captain");
		return true;
	}
	if (const UAstraLifeSubsystem* L = Life(); L && L->IsRunning())
	{
		const UAstraShipSubsystem* S = Ship();
		for (int32 i = 0; i < L->Sim().NumPeople(); ++i)
		{
			const FAstraLifePerson& Pe = L->Sim().Person(i);
			if (Pe.Status == 2 || Pe.bAway || Pe.bTransit || !OnPad(Pe.Pos))
			{
				continue;
			}
			OutWho = S ? S->GetRoster().Get()[Pe.Roster].Name() : FString::Printf(TEXT("npc%d"), Pe.Roster);
			return true;
		}
	}
	return false;
}

FString UAstraTransporterSubsystem::PadLabelAt(const FVector& FeetCm, int32* OutPad) const
{
	for (int32 i = 0; i < Pads.Num(); ++i)
	{
		const FAstraXportPad& P = Pads[i];
		if (FVector::DistSquared2D(FeetCm, P.PosCm) < FMath::Square(P.RadiusCm + 25.f) && FMath::Abs(FeetCm.Z - P.PosCm.Z) < 70.f)
		{
			if (OutPad)
			{
				*OutPad = i;
			}
			return P.Id.ToString();
		}
	}
	return FString();
}

int32 UAstraTransporterSubsystem::FreeMainPad(const TArray<int32>& Reserved) const
{
	for (int32 i = 0; i < Pads.Num(); ++i)
	{
		const FAstraXportPad& P = Pads[i];
		FString Who;
		if (P.bEmergency || P.bCargo || Reserved.Contains(i) || PadOccupiedBy(P, Who))
		{
			continue;
		}
		// a transport that is going to put someone there holds it
		bool bHeld = false;
		for (const FAstraXportJob& J : JobList)
		{
			const bool bLive = J.Phase != EAstraXportPhase::Done && J.Phase != EAstraXportPhase::Failed && J.Phase != EAstraXportPhase::Aborted && J.Phase != EAstraXportPhase::Lost;
			if (bLive && J.Req.To.bPad && !J.Req.To.bEmergencyPad && J.Req.To.Pad >= 0 && J.Req.To.Pad < Pads.Num() && Pads[J.Req.To.Pad].Id == P.Id)
			{
				bHeld = true;
			}
		}
		if (!bHeld)
		{
			return i;
		}
	}
	return INDEX_NONE;
}

// ================================================================================================ people
int32 UAstraTransporterSubsystem::FindPerson(const FString& Words, TArray<FString>* OutAlternatives) const
{
	const UAstraLifeSubsystem* L = Life();
	const UAstraShipSubsystem* S = Ship();
	if (!L || !L->IsRunning() || !S)
	{
		return INDEX_NONE;
	}
	static const TSet<FString> Little = {TEXT("the"), TEXT("and"), TEXT("our"), TEXT("who"), TEXT("where"), TEXT("is"), TEXT("of"), TEXT("on"), TEXT("called"), TEXT("named"),
	                                     TEXT("ship"), TEXT("aboard"), TEXT("duty"), TEXT("now"), TEXT("any"), TEXT("one"), TEXT("beam"), TEXT("transport")};
	FString Clean;
	for (const TCHAR Ch : Words.ToLower())
	{
		Clean.AppendChar(FChar::IsAlpha(Ch) || Ch == TEXT('-') ? Ch : TEXT(' '));
	}
	TArray<FString> Toks;
	Clean.ParseIntoArrayWS(Toks);
	Toks.RemoveAll([](const FString& Tk) { return Tk.Len() < 3 || Little.Contains(Tk); });
	if (Toks.IsEmpty())
	{
		return INDEX_NONE;
	}
	struct FHit { int32 Score; bool bName; int32 Person; };
	TArray<FHit> Hits;
	const TArray<FAstraCrewman>& Roster = S->GetRoster().Get();
	for (int32 i = 0; i < L->Sim().NumPeople(); ++i)
	{
		const FAstraLifePerson& P = L->Sim().Person(i);
		const FAstraCrewman& R = Roster[P.Roster];
		FString Last = R.Last.ToLower(), Call;
		if (const int32 Cut = Last.Find(TEXT(" (call sign ")); Cut != INDEX_NONE)
		{
			Call = Last.Mid(Cut + 12).LeftChop(1);
			Last = Last.Left(Cut);
		}
		const FString First = R.First.ToLower(), RankL = R.Rank.ToLower(), JobL = P.Job.ToLower(), DeptL = R.Dept.ToLower();
		int32 Score = 0;
		bool bName = false;
		for (const FString& Tk : Toks)
		{
			if (Tk == Last || Tk == Call) { Score += 6; bName = true; }
			else if (Tk == First) { Score += 5; bName = true; }
			else if (Tk.Len() >= 4 && (Last.StartsWith(Tk) || First.StartsWith(Tk))) { Score += 2; bName = true; }
			else if (Tk.Len() >= 4 && JobL.Contains(Tk)) { Score += 3; }
			else if (RankL.Contains(Tk)) { Score += 1; }
			else if (Tk.Len() >= 4 && DeptL.Contains(Tk)) { Score += 1; }
		}
		if (Score >= 3)
		{
			Hits.Add({Score, bName, i});
		}
	}
	if (Hits.IsEmpty())
	{
		return INDEX_NONE;
	}
	Hits.Sort([&](const FHit& A, const FHit& B)
	{
		if (A.Score != B.Score) { return A.Score > B.Score; }
		return FVector::DistSquared(L->Sim().Person(A.Person).Pos, RoomOriginCm) < FVector::DistSquared(L->Sim().Person(B.Person).Pos, RoomOriginCm);
	});
	const int32 Best = Hits[0].Score;
	const bool bByName = Hits[0].bName;
	Hits.RemoveAll([Best, bByName](const FHit& H) { return H.Score < Best - 2 || (bByName && !H.bName); });
	if (Hits.Num() > 1 && Hits[1].Score == Hits[0].Score && bByName)
	{
		if (OutAlternatives)
		{
			for (int32 k = 0; k < FMath::Min(4, Hits.Num()); ++k)
			{
				OutAlternatives->Add(FString::Printf(TEXT("%s (npc%d)"), *Roster[L->Sim().Person(Hits[k].Person).Roster].Name(), L->Sim().Person(Hits[k].Person).Roster));
			}
		}
		return INDEX_NONE;
	}
	return Hits[0].Person;
}

bool UAstraTransporterSubsystem::ResolveSubjects(const FAstraXportOrder& O, TArray<FAstraXportSubject>& Out, FString& OutErr) const
{
	const UAstraLifeSubsystem* L = Life();
	const UAstraShipSubsystem* S = Ship();
	TSet<FString> Seen;
	auto Add = [&](FAstraXportSubject Sub)
	{
		if (!Seen.Contains(Sub.S.Id))
		{
			Seen.Add(Sub.S.Id);
			Out.Add(MoveTemp(Sub));
		}
	};
	auto PersonSubject = [&](int32 Person) -> FAstraXportSubject
	{
		FAstraXportSubject Sub;
		const FAstraLifePerson& P = L->Sim().Person(Person);
		const FAstraCrewman& R = S->GetRoster().Get()[P.Roster];
		Sub.S.Kind = ESubject::Person;
		Sub.S.Id = FString::Printf(TEXT("npc%d"), P.Roster);
		Sub.S.Label = R.Name();
		Sub.S.MassKg = 88.f;
		Sub.S.Roster = P.Roster;
		Sub.S.bDead = P.Status == 2;
		Sub.S.bInPattern = P.bTransit;
		Sub.Person = Person;
		Sub.Dept = R.Dept;
		Sub.bFemale = R.bFemale;
		Sub.bAway = P.bAway;
		if (P.bAway)
		{
			for (const FAstraXportAway& A : AwayList)
			{
				if (A.Person == Person)
				{
					Sub.AwayWhere = A.Where;
					if (A.bStranded)
					{
						Sub.S.Barred = FString::Printf(TEXT("%s was left behind in the %s system: out of any beam's reach"), *Sub.S.Label, *A.System);
					}
				}
			}
			if (Sub.AwayWhere.IsEmpty())
			{
				// not sent by the transporter: a marine who went in a boat to the ship our marines are fighting aboard is on her decks, in the fight (the boarding host knows where)
				FString Contact;
				const UAstraBoardSubsystem* Bd = Board();
				if (Bd && Bd->PersonAboardOtherShip(P.Roster, &Contact))
				{
					Sub.AwayWhere = Contact;
				}
				else
				{
					Sub.S.bFound = false;                      // away, but not by the transporter: nobody knows where
				}
			}
		}
		else
		{
			Sub.FromCm = P.Pos;
			Sub.FromYaw = P.TargetYaw;
			const int32 C = L->Sim().CompOf(Person);
			Sub.FromComp = L->Sim().GetMap().Comps.IsValidIndex(C) ? L->Sim().GetMap().Comps[C].Id.ToString() : FString();
			// whoever the marines have taken for a boarding fight is the fight's (ABBORDAGGI: a soldier's body of its own stands where the fight puts it): the pattern would stay behind
			if (P.bCommandeered)
			{
				Sub.S.Barred = FString::Printf(TEXT("%s is in the fight with the boarders, with their squad: the marines have them, and a pattern cannot be lifted out of a fight under way"), *Sub.S.Label);
			}
			// whoever holds a post that has an actor of its own (a bridge station, a bed of the ward) cannot be taken from it: the actor would stay behind
			else if (P.Place != INDEX_NONE && L->Sim().GetMap().Places.IsValidIndex(P.Place) && L->Sim().GetMap().Places[P.Place].External != NAME_None)
			{
				const FString Post = L->Sim().GetMap().Places[P.Place].External.ToString();
				Sub.S.Barred = Post.StartsWith(TEXT("patient")) ? FString::Printf(TEXT("%s lies in the Medbay under the doctors' care"), *Sub.S.Label)
				                                                 : FString::Printf(TEXT("%s is on station at the %s post: it cannot be left by the beam"), *Sub.S.Label, *Post);
			}
		}
		return Sub;
	};

	for (const FString& Raw : O.Who)
	{
		const FString W = XpNorm(Raw);
		if (W.IsEmpty())
		{
			continue;
		}
		// ---- the Captain
		if (W == TEXT("captain") || W == TEXT("me") || W == TEXT("myself") || W == TEXT("i") || W == TEXT("the captain") || W == TEXT("commander") || W == TEXT("skipper") || W == TEXT("player"))
		{
			FAstraXportSubject Sub;
			Sub.S.Kind = ESubject::Captain;
			Sub.S.Id = TEXT("captain");
			Sub.S.Label = TEXT("the Captain");
			Sub.S.MassKg = 95.f;
			FVector Feet;
			float Yaw;
			bool bG, bSeated;
			if (!CaptainFeet(Feet, Yaw, bG, bSeated))
			{
				const UAstraBoardSubsystem* Bd = Board();
				OutErr = Bd && Bd->CaptainInBoat() ? TEXT("the Captain is in the troop bay of a Kestrel in flight: no beam locks through a boat's hull (he is on the boat's own net)")
				                                   : TEXT("the Captain is in a cockpit or a pod: there is no pattern to lock on (his badge is not on the ship's net)");
				return false;
			}
			Sub.bAway = bG;
			if (bG)
			{
				Sub.FromCm = Feet;                                    // (where he stands, wherever that is: a pattern recomposed at its origin is put back there)
				Sub.FromYaw = Yaw;
				for (const FAstraXportAway& A : AwayList)
				{
					if (A.Id == TEXT("captain"))
					{
						Sub.AwayWhere = A.Where;
					}
				}
				if (Sub.AwayWhere.IsEmpty())
				{
					// not sent by the transporter: on the decks of the ship the marines are fighting aboard (he went in a boat), or down on a world
					FString Contact;
					const UAstraBoardSubsystem* Bd = Board();
					Sub.AwayWhere = Bd && Bd->CaptainAboardOtherShip(&Contact) && !Contact.IsEmpty() ? Contact : FString(TEXT("surface"));
				}
			}
			else
			{
				Sub.FromCm = Feet;
				Sub.FromYaw = Yaw;
				if (L && L->IsRunning())
				{
					const int32 C = L->Sim().GetMap().CompartmentAt(Feet + FVector(0, 0, 30));
					Sub.FromComp = L->Sim().GetMap().Comps.IsValidIndex(C) ? L->Sim().GetMap().Comps[C].Id.ToString() : FString();
				}
			}
			Sub.S.bInPattern = CaptainBeamJob != INDEX_NONE;
			Add(Sub);
			continue;
		}
		if (!L || !L->IsRunning() || !S)
		{
			OutErr = TEXT("the personnel locator is not answering: nobody can be found by name yet");
			return false;
		}
		// ---- whoever stands on a pad
		if (W.StartsWith(TEXT("pad")) && XpFirstNumber(W) != INDEX_NONE)
		{
			const int32 N = XpFirstNumber(W);
			if (N < 1 || N > T.Pads || !Pads.IsValidIndex(N - 1))
			{
				OutErr = FString::Printf(TEXT("the room has pads 1 to %d"), T.Pads);
				return false;
			}
			FString Who;
			const FAstraXportPad& P = Pads[N - 1];
			if (!PadOccupiedBy(P, Who))
			{
				OutErr = FString::Printf(TEXT("nobody is standing on pad %d"), N);
				return false;
			}
			if (Who == TEXT("the Captain"))
			{
				FAstraXportOrder One;
				One.Who = {TEXT("captain")};
				if (!ResolveSubjects(One, Out, OutErr))
				{
					return false;
				}
				Seen.Add(TEXT("captain"));
				continue;
			}
			bool bFoundPad = false;
			for (int32 i = 0; i < L->Sim().NumPeople() && !bFoundPad; ++i)
			{
				const FAstraLifePerson& Pe = L->Sim().Person(i);
				if (Pe.Status != 2 && !Pe.bAway && !Pe.bTransit && FVector::DistSquared2D(Pe.Pos, P.PosCm) < FMath::Square(P.RadiusCm + 25.f) && FMath::Abs(Pe.Pos.Z - P.PosCm.Z) < 70.f)
				{
					Add(PersonSubject(i));
					bFoundPad = true;
				}
			}
			continue;
		}
		// ---- the people sent away and not yet brought back
		if (W.StartsWith(TEXT("away")) || W == TEXT("landing party") || W == TEXT("everyone away") || W == TEXT("the away team") || W == TEXT("landing team") || W.StartsWith(TEXT("all away")))
		{
			const FString FromKey = XpNorm(O.From);
			int32 Count = 0;
			for (const FAstraXportAway& A : AwayList)
			{
				if (A.bCargo)
				{
					continue;
				}
				if (!FromKey.IsEmpty() && XpContactKey(FromKey).IsEmpty() && !(FromKey.Contains(TEXT("surface")) || FromKey.Contains(TEXT("ground")) || FromKey.Contains(TEXT("planet"))) == (A.Where == TEXT("surface")))
				{
					continue;
				}
				if (A.Id == TEXT("captain"))
				{
					FAstraXportOrder One;
					One.Who = {TEXT("captain")};
					if (ResolveSubjects(One, Out, OutErr))
					{
						Seen.Add(TEXT("captain"));
						++Count;
					}
					continue;
				}
				if (A.Person != INDEX_NONE)
				{
					Add(PersonSubject(A.Person));
					++Count;
				}
			}
			if (Count == 0)
			{
				OutErr = TEXT("nobody is away: no one was sent off the ship by the transporter, or they are all home");
				return false;
			}
			continue;
		}
		// ---- a squad: "marines 6", "6 marines", "squad of marines"
		{
			const bool bMarines = W.Contains(TEXT("marine")) || W.Contains(TEXT("squad")) || W.Contains(TEXT("fireteam"));
			if (bMarines)
			{
				const int32 N = FMath::Clamp(XpFirstNumber(W) == INDEX_NONE ? 4 : XpFirstNumber(W), 1, 12);
				struct FPick { int32 Person; double Dist; };
				TArray<FPick> Pool;
				for (int32 i = 0; i < L->Sim().NumPeople(); ++i)
				{
					const FAstraLifePerson& Pe = L->Sim().Person(i);
					if (Pe.Status != 0 || Pe.bAway || Pe.bTransit || Pe.bCommandeered || S->GetRoster().Get()[Pe.Roster].Dept != TEXT("marines") || Seen.Contains(FString::Printf(TEXT("npc%d"), Pe.Roster)))
					{
						continue;
					}
					// not the ones in a pattern-shielded room (the armory, a magazine), nor on a post with an actor of its own
					const int32 Ci = L->Sim().CompOf(i);
					if (L->Sim().GetMap().Comps.IsValidIndex(Ci) && (T.InhibitKinds.Contains(L->Sim().GetMap().Comps[Ci].Kind) || T.InhibitIds.Contains(L->Sim().GetMap().Comps[Ci].Id)))
					{
						continue;
					}
					if (Pe.Place != INDEX_NONE && L->Sim().GetMap().Places.IsValidIndex(Pe.Place) && L->Sim().GetMap().Places[Pe.Place].External != NAME_None)
					{
						continue;
					}
					const double Pen = Pe.Act == EAstraLifeAct::Sleep ? 1.0e9 : 0.0;      // the awake first
					Pool.Add({i, FVector::Dist(Pe.Pos, RoomOriginCm) + Pen});
				}
				Pool.Sort([](const FPick& A, const FPick& B) { return A.Dist < B.Dist; });
				if (Pool.Num() < N)
				{
					OutErr = FString::Printf(TEXT("only %d fit marines can be found aboard"), Pool.Num());
					return false;
				}
				for (int32 k = 0; k < N; ++k)
				{
					Add(PersonSubject(Pool[k].Person));
				}
				continue;
			}
		}
		// ---- cargo
		if (W.Contains(TEXT("cargo")) || W.Contains(TEXT(" kg")) || W.Contains(TEXT("crate")) || W.Contains(TEXT("supplies")) || W.Contains(TEXT("tonne")) || W.Contains(TEXT(" ton ")))
		{
			float Kg = 200.f;
			const int32 Num = XpFirstNumber(W);
			if (Num != INDEX_NONE)
			{
				Kg = (float)Num * ((W.Contains(TEXT("tonne")) || W.Contains(TEXT(" ton")) || W.EndsWith(TEXT(" t"))) ? 1000.f : 1.f);
			}
			FAstraXportSubject Sub;
			Sub.S.Kind = ESubject::Cargo;
			Sub.S.Id = FString::Printf(TEXT("cargo%d"), Out.Num() + 1 + NextSerial * 10);
			FString Label = Raw.TrimStartAndEnd();
			Label.RemoveFromStart(TEXT("cargo:"));
			Label.RemoveFromStart(TEXT("cargo "));
			Sub.S.Label = Label.IsEmpty() ? FString::Printf(TEXT("%.0f kg of cargo"), Kg) : Label;
			Sub.S.MassKg = Kg;
			Sub.FromCm = Pads.IsValidIndex(T.Pads) ? Pads[T.Pads].PosCm : RoomOriginCm;          // the cargo pad (the main pads end at T.Pads)
			Sub.FromComp = RoomCompId;
			if (O.From.Len() && !XpNorm(O.From).Contains(TEXT("pad")) && !XpNorm(O.From).Contains(TEXT("cargo")))
			{
				// cargo already down on a world or on a ship: brought back
				for (const FAstraXportAway& A : AwayList)
				{
					if (A.bCargo && XpNorm(A.Label).Contains(XpNorm(Label)))
					{
						Sub.S.Id = A.Id;
						Sub.S.Label = A.Label;
						Sub.S.MassKg = A.MassKg;
						Sub.bAway = true;
						Sub.AwayWhere = A.Where;
						break;
					}
				}
			}
			Add(Sub);
			continue;
		}
		// ---- npc17
		if (W.StartsWith(TEXT("npc")) && XpFirstNumber(W) != INDEX_NONE)
		{
			const int32 Roster = XpFirstNumber(W);
			const int32 Person = L->Sim().PersonOfRoster(Roster);
			if (Person == INDEX_NONE)
			{
				OutErr = FString::Printf(TEXT("npc%d is not in the ship's company"), Roster);
				return false;
			}
			Add(PersonSubject(Person));
			continue;
		}
		// ---- a name, a job
		TArray<FString> Alt;
		const int32 Person = FindPerson(Raw, &Alt);
		if (Person == INDEX_NONE)
		{
			OutErr = Alt.Num() ? FString::Printf(TEXT("\"%s\" could be %s: say which (npc number or full name)"), *Raw, *FString::Join(Alt, TEXT(", ")))
			                   : FString::Printf(TEXT("nobody aboard matches \"%s\" in the personnel file (a surname, a rank and name, a job, or npc<number>)"), *Raw);
			return false;
		}
		Add(PersonSubject(Person));
	}
	if (Out.IsEmpty())
	{
		OutErr = TEXT("say who or what is to be beamed");
		return false;
	}
	return true;
}

// ================================================================================================ places
bool UAstraTransporterSubsystem::PickSpots(const FString& CompId, int32 N, const TArray<FVector>& Avoid, TArray<FVector>& OutSpots, TArray<float>& OutYaws) const
{
	OutSpots.Reset();
	OutYaws.Reset();
	const UAstraLifeSubsystem* L = Life();
	auto Free = [&](const FVector& P)
	{
		for (const FVector& A : Avoid)
		{
			if (FVector::DistSquared2D(A, P) < FMath::Square(95.f) && FMath::Abs(A.Z - P.Z) < 150.f)
			{
				return false;
			}
		}
		for (const FVector& Done : OutSpots)
		{
			if (FVector::DistSquared2D(Done, P) < FMath::Square(95.f))
			{
				return false;
			}
		}
		return true;
	};
	if (L && L->IsRunning())
	{
		const FAstraLifeMap& Map = L->Sim().GetMap();
		if (const int32* Idx = Map.CompByName.Find(FName(*CompId)))
		{
			// the room's places a person can stand at: stands and posts first, then the heart of the room
			TArray<int32> Cand;
			for (const int32 P : Map.Comps[*Idx].Places)
			{
				const FAstraLifePlace& Pl = Map.Places[P];
				if (Pl.Kind == EAstraPlaceKind::Stand || Pl.Kind == EAstraPlaceKind::Work)
				{
					Cand.Add(P);
				}
			}
			for (const int32 P : Cand)
			{
				if (OutSpots.Num() >= N)
				{
					break;
				}
				const FAstraLifePlace& Pl = Map.Places[P];
				if (Free(Pl.Pos))
				{
					OutSpots.Add(Pl.Pos);
					OutYaws.Add(Pl.Yaw);
				}
			}
			// still short: a loose grid on the floor round the room's heart
			const FBox& B = Map.Comps[*Idx].Box;
			const FVector Heart = Map.Comps[*Idx].Hub != INDEX_NONE ? Map.Places[Map.Comps[*Idx].Hub].Pos : FVector(B.GetCenter().X, B.GetCenter().Y, B.Min.Z);
			for (int32 Ring = 0; Ring < 6 && OutSpots.Num() < N; ++Ring)
			{
				for (int32 k = 0; k < 8 && OutSpots.Num() < N; ++k)
				{
					const float A = (float)k * PI / 4.f + Ring * 0.4f;
					const FVector P = Heart + FVector(FMath::Cos(A), FMath::Sin(A), 0.f) * (Ring == 0 ? 0.f : 110.f * Ring);
					if (P.X > B.Min.X + 40.f && P.X < B.Max.X - 40.f && P.Y > B.Min.Y + 40.f && P.Y < B.Max.Y - 40.f && Free(P))
					{
						OutSpots.Add(P);
						OutYaws.Add(FMath::RadiansToDegrees(A) + 180.f);
					}
				}
			}
			return OutSpots.Num() >= N;
		}
	}
	// no life map: the floor of the plan's compartment
	if (const UAstraShipPlan* P = Plan())
	{
		for (const FAstraPlanCompartment& C : P->GetCompartments())
		{
			if (C.Id != CompId)
			{
				continue;
			}
			const FVector Heart(C.Box.GetCenter().X, C.Box.GetCenter().Y, C.Box.Min.Z);
			for (int32 Ring = 0; Ring < 6 && OutSpots.Num() < N; ++Ring)
			{
				for (int32 k = 0; k < 8 && OutSpots.Num() < N; ++k)
				{
					const float A = (float)k * PI / 4.f;
					const FVector Pt = Heart + FVector(FMath::Cos(A), FMath::Sin(A), 0.f) * (Ring == 0 ? 0.f : 110.f * Ring);
					if (C.Box.IsInsideOrOn(Pt + FVector(0, 0, 50)) && Free(Pt))
					{
						OutSpots.Add(Pt);
						OutYaws.Add(0.f);
					}
				}
			}
			return OutSpots.Num() >= N;
		}
	}
	return false;
}

FString UAstraTransporterSubsystem::DescribeEnd(const FEnd& E, const FString& CompId) const
{
	switch (E.Kind)
	{
	case EEndKind::Pad: return E.Label;
	case EEndKind::Surface: return E.Label;
	case EEndKind::Ship: return E.Label;
	default:
		if (const UAstraLifeSubsystem* L = Life(); L && L->IsRunning())
		{
			if (const int32* Idx = L->Sim().GetMap().CompByName.Find(FName(*CompId)))
			{
				return L->Sim().GetMap().Describe(*Idx);
			}
		}
		return E.Label;
	}
}

bool UAstraTransporterSubsystem::ResolveEnd(const FString& Text, bool bDest, const TArray<FAstraXportSubject>& Subs, FEnd& Out, FString& OutComp, FString& OutErr) const
{
	OutComp.Reset();
	Out = FEnd();
	const FString Q = XpNorm(Text);
	if (Q.IsEmpty())
	{
		OutErr = TEXT("where to?");
		return false;
	}
	const UAstraShipSubsystem* S = Ship();
	const UAstraLifeSubsystem* L = Life();

	// ---- the pads of the room, the cargo pad, the Medbay's
	const bool bCargoWord = Q == TEXT("cargo pad") || Q == TEXT("cargo") || Q == TEXT("cargo transporter");
	const bool bEmergencyWord = Q.StartsWith(TEXT("med")) && (Q == TEXT("med1") || Q == TEXT("med2") || Q == TEXT("med 1") || Q == TEXT("med 2")) || Q.Contains(TEXT("emergency pad")) || Q == TEXT("medbay pad") || Q == TEXT("medbay pads") || Q == TEXT("sickbay pad");
	const bool bAnyPad = Q == TEXT("pad") || Q == TEXT("pads") || Q == TEXT("a pad") || Q == TEXT("any pad") || Q == TEXT("free pad") || Q == TEXT("transporter pad") || Q == TEXT("transporter room") ||
	                     Q == TEXT("transporter") || Q == TEXT("transporter pads") || Q == TEXT("the pads") || Q == TEXT("a free pad");
	const bool bNumberedPad = Q.StartsWith(TEXT("pad")) && XpFirstNumber(Q) != INDEX_NONE;
	if (bCargoWord || bEmergencyWord || bAnyPad || bNumberedPad)
	{
		Out.Kind = EEndKind::Pad;
		Out.bPad = true;
		Out.CompKind = T.RoomKind;
		OutComp = RoomCompId;
		if (bCargoWord)
		{
			if (!Pads.IsValidIndex(T.Pads) || !Pads[T.Pads].bCargo)
			{
				OutErr = TEXT("the room's cargo pad is not known yet");
				return false;
			}
			Out.Pad = T.Pads;
			Out.Label = TEXT("the cargo pad");
		}
		else if (bEmergencyWord)
		{
			Out.bEmergencyPad = true;
			const int32 N = XpFirstNumber(Q) == INDEX_NONE ? 1 : XpFirstNumber(Q);
			Out.Pad = FMath::Clamp(N, 1, FMath::Max(1, T.EmergencyPads)) - 1;
			Out.Label = FString::Printf(TEXT("emergency pad %d (Medbay)"), Out.Pad + 1);
			OutComp = TEXT("medbay");
			Out.CompKind = TEXT("medbay");
			const int32 PadIdx = T.Pads + 1 + Out.Pad;
			if (Pads.IsValidIndex(PadIdx))
			{
				FString Who;
				Out.bPadOccupied = PadOccupiedBy(Pads[PadIdx], Who);
			}
		}
		else if (bNumberedPad)
		{
			const int32 N = XpFirstNumber(Q);
			if (N < 1 || N > T.Pads)
			{
				OutErr = FString::Printf(TEXT("the room has pads 1 to %d"), T.Pads);
				return false;
			}
			Out.Pad = N - 1;
			Out.Label = FString::Printf(TEXT("pad %d"), N);
			FString Who;
			Out.bPadOccupied = Pads.IsValidIndex(Out.Pad) && PadOccupiedBy(Pads[Out.Pad], Who) && bDest;
		}
		else
		{
			TArray<int32> Reserved;
			const int32 Free = bDest ? FreeMainPad(Reserved) : 0;
			if (Free == INDEX_NONE)
			{
				OutErr = TEXT("every pad is taken");
				return false;
			}
			Out.Pad = Free;
			Out.Label = FString::Printf(TEXT("pad %d"), Free + 1);
		}
		Out.Room = RoomOf(OutComp, bEmergencyWord ? TEXT("the Medbay") : TEXT("the Transporter Room"));
		return true;
	}

	// ---- the ground
	const FString World = S ? S->SurfaceWorldName().ToLower() : FString();
	const bool bGroundWord = Q == TEXT("surface") || Q == TEXT("planet") || Q == TEXT("ground") || Q == TEXT("down") || Q.Contains(TEXT("landing field")) || Q == TEXT("field") || Q.Contains(TEXT("planetside")) ||
	                         Q == TEXT("down below") || Q == TEXT("planet surface") || Q.StartsWith(TEXT("surface")) || Q.StartsWith(TEXT("the surface")) || (!World.IsEmpty() && Q.Contains(World)) ||
	                         (S && !S->SurfaceSiteName().IsEmpty() && Q.Contains(S->SurfaceSiteName().ToLower()));
	if (bGroundWord)
	{
		if (!S || !(S->HasSurface() || bTestSurface))
		{
			OutErr = TEXT("there is no ground to beam to: the system's main world has no surface (a gas giant) or none is charted");
			return false;
		}
		Out.Kind = EEndKind::Surface;
		Out.World = S->SurfaceWorldName();
		Out.Label = FString::Printf(TEXT("%s · %s"), *S->SurfaceWorldName(), *S->SurfaceSiteName());
		Out.Owner = (uint8)XpOwnerIndex(S->SurfaceOwner());
		Out.DirBody = S->PlanetDirectionWorld().GetSafeNormal();
		if (Out.DirBody.IsNearlyZero())
		{
			Out.DirBody = FVector(0, 0, -1);
		}
		return true;
	}

	// ---- a ship of the plot
	{
		const UAstraBattleSubsystem* B = Battle();
		FString Id;
		if (B)
		{
			const FString Want = XpContactKey(Q);
			const UAstraBattleSubsystem::FContactView* Best = nullptr;
			TArray<FString> Same;
			for (const UAstraBattleSubsystem::FContactView& C : B->Contacts())
			{
				if (!Want.IsEmpty())
				{
					if (XpContactKey(C.ContactId) == Want)
					{
						Best = &C;
						break;
					}
					continue;
				}
				// by name: the whole words of what was said are the whole words of her name ("vigilant", "asn vigilant"), never a part of one
				const int32 Paren = C.Label.Find(TEXT(" ("));
				const FString Name = XpNorm(Paren == INDEX_NONE ? C.Label : C.Label.Left(Paren));
				if (Q.Len() >= 4 && !Name.IsEmpty() && ((TEXT(" ") + Name + TEXT(" ")).Contains(TEXT(" ") + Q + TEXT(" "))))
				{
					Same.Add(FString::Printf(TEXT("%s (%s)"), *C.ContactId, *C.Label.Left(Paren == INDEX_NONE ? C.Label.Len() : Paren)));
					if (!Best || C.RangeKm < Best->RangeKm)
					{
						Best = &C;
					}
				}
			}
			if (Same.Num() > 1)
			{
				OutErr = FString::Printf(TEXT("\"%s\" could be %s: say the contact id"), *Text, *FString::Join(Same, TEXT(", ")));
				return false;
			}
			if (Best && Best->bCraft)
			{
				OutErr = FString::Printf(TEXT("%s is a craft: it has no receiving pad for a beam"), *Best->Label);
				return false;
			}
			if (Best && Best->Track < 2)
			{
				OutErr = FString::Printf(TEXT("no firm track on %s: a bearing is not enough to range a beam on"), *Best->ContactId);
				return false;
			}
			if (Best)
			{
				Id = Best->ContactId;
			}
		}
		if (!Id.IsEmpty())
		{
			Out.Kind = EEndKind::Ship;
			if (!FillShip(Out.Ship, Id))
			{
				OutErr = FString::Printf(TEXT("%s is not on the plot"), *Id);
				return false;
			}
			Out.Label = Out.Ship.Name;
			return true;
		}
		if (!XpContactKey(Q).IsEmpty())
		{
			OutErr = FString::Printf(TEXT("no contact %s on the plot"), *Text);
			return false;
		}
	}

	// ---- a room of the ship
	if (!L || !L->IsRunning())
	{
		OutErr = TEXT("the ship's plan is not up: no room can be named yet");
		return false;
	}
	const FAstraLifeMap& Map = L->Sim().GetMap();
	FString Name = Q;
	int32 DeckWant = INDEX_NONE;
	{
		const int32 Cut = Name.Find(TEXT("deck "));
		if (Cut != INDEX_NONE)
		{
			DeckWant = XpFirstNumber(Name.Mid(Cut + 5));
			// the words round the number stay: "deck 8 armory" -> "armory"; "armory deck 8" -> "armory"
			FString Left = Name.Left(Cut), Right = Name.Mid(Cut + 5);
			int32 Skip = 0;
			while (Skip < Right.Len() && (FChar::IsDigit(Right[Skip]) || FChar::IsWhitespace(Right[Skip]))) { ++Skip; }
			Name = (Left + TEXT(" ") + Right.Mid(Skip)).TrimStartAndEnd();
		}
	}
	static const TMap<FString, FString> Alias = {{TEXT("sickbay"), TEXT("medbay")}, {TEXT("infirmary"), TEXT("medbay")}, {TEXT("sick bay"), TEXT("medbay")}, {TEXT("engine room"), TEXT("main engineering")},
	                                             {TEXT("reactor room"), TEXT("main engineering")}, {TEXT("hangar"), TEXT("flight deck")}, {TEXT("hangar deck"), TEXT("flight deck")},
	                                             {TEXT("barracks"), TEXT("marine barracks")}, {TEXT("quarters"), TEXT("captains quarters")}, {TEXT("my quarters"), TEXT("captains quarters")},
	                                             {TEXT("mess"), TEXT("mess hall")}, {TEXT("armoury"), TEXT("armory")}, {TEXT("command"), TEXT("bridge")}, {TEXT("ready room"), TEXT("ready room")},
	                                             {TEXT("cic"), TEXT("combat information centre")}, {TEXT("combat information center"), TEXT("combat information centre")}};
	if (const FString* A = Alias.Find(Name))
	{
		Name = *A;
	}
	struct FCand { int32 Comp; int32 Score; double Dist; };
	TArray<FCand> Cands;
	FVector Ref = RoomOriginCm;
	if (Subs.Num() && !Subs[0].bAway)
	{
		Ref = Subs[0].FromCm;
	}
	for (int32 i = 0; i < Map.Comps.Num(); ++i)
	{
		const FAstraLifeComp& C = Map.Comps[i];
		if (C.Status == EAstraRoomStatus::Planned || C.bWalled || (DeckWant != INDEX_NONE && C.Deck != DeckWant))
		{
			continue;
		}
		FString NameL = C.Name.ToLower();
		for (const TCHAR* Junk : {TEXT("'"), TEXT("’")})
		{
			NameL = NameL.Replace(Junk, TEXT(""));
		}
		const FString KindL = C.Kind.ToString().ToLower();
		int32 Score = 0;
		if (C.Id.ToString().ToLower() == Name) { Score = 100; }
		else if (NameL == Name) { Score = 90; }
		else if (NameL.StartsWith(Name) && Name.Len() >= 3) { Score = 70; }
		else if (NameL.Contains(Name) && Name.Len() >= 3) { Score = 55; }
		else if (KindL == Name) { Score = 45; }
		if (Score > 0)
		{
			Cands.Add({i, Score, FVector::Dist(C.Box.GetCenter(), Ref)});
		}
	}
	if (Cands.IsEmpty())
	{
		OutErr = FString::Printf(TEXT("no room, ship or place called \"%s\" (a room of the Aquila by name, a pad, the surface, a ship's contact id)"), *Text);
		return false;
	}
	int32 Top = 0;
	for (const FCand& C : Cands)
	{
		Top = FMath::Max(Top, C.Score);
	}
	Cands.RemoveAll([Top](const FCand& C) { return C.Score < Top; });
	TSet<FString> Names;
	for (const FCand& C : Cands)
	{
		Names.Add(Map.Comps[C.Comp].Name);
	}
	if (Names.Num() > 1 && Top < 90)
	{
		TArray<FString> Show;
		for (const FString& N : Names)
		{
			Show.Add(N);
			if (Show.Num() >= 5)
			{
				break;
			}
		}
		OutErr = FString::Printf(TEXT("\"%s\" could be %s: say which (a deck number helps)"), *Text, *FString::Join(Show, TEXT(", ")));
		return false;
	}
	Cands.Sort([](const FCand& A, const FCand& B) { return A.Dist < B.Dist; });
	const FAstraLifeComp& C = Map.Comps[Cands[0].Comp];
	Out.Kind = EEndKind::Site;
	Out.CompKind = C.Kind;
	Out.Label = Map.Describe(Cands[0].Comp);
	OutComp = C.Id.ToString();
	Out.bInhibited = T.InhibitKinds.Contains(C.Kind) || T.InhibitIds.Contains(C.Id);
	Out.Room = RoomOf(OutComp, C.Name);
	return true;
}

// ================================================================================================ the request
bool UAstraTransporterSubsystem::MakeRequest(const FAstraXportOrder& O, FAstraXportJob& OutJob, FString& OutErr) const
{
	OutJob = FAstraXportJob();
	if (!ResolveSubjects(O, OutJob.Subs, OutErr))
	{
		return false;
	}
	bool bAway = false, bAboard = false;
	FString AwayWhere;
	for (const FAstraXportSubject& Sub : OutJob.Subs)
	{
		if (Sub.bAway)
		{
			if (bAway && Sub.AwayWhere != AwayWhere)
			{
				OutErr = TEXT("they are away in different places: one source at a time");
				return false;
			}
			bAway = true;
			AwayWhere = Sub.AwayWhere;
		}
		else
		{
			bAboard = true;
		}
	}
	if (bAway && bAboard)
	{
		OutErr = TEXT("some of them are aboard and some are away: one source at a time");
		return false;
	}
	FEnd From, To;
	FString FromComp, ToComp;
	if (bAway)
	{
		if (!ResolveEnd(AwayWhere, false, OutJob.Subs, From, FromComp, OutErr))
		{
			return false;
		}
		const FString Asked = XpNorm(O.From);
		if (!Asked.IsEmpty() && !XpContactKey(Asked).IsEmpty() && From.Kind != EEndKind::Ship)
		{
			OutErr = FString::Printf(TEXT("they are not on %s: they are %s"), *O.From, *From.Label);
			return false;
		}
	}
	else
	{
		// where they stand: the first subject's room (the others' are checked below), a pad of the room when they stand on one
		const FAstraXportSubject& First = OutJob.Subs[0];
		From.Kind = EEndKind::Site;
		FromComp = First.FromComp;
		const UAstraLifeSubsystem* L = Life();
		if (L && L->IsRunning())
		{
			if (const int32* Idx = L->Sim().GetMap().CompByName.Find(FName(*FromComp)))
			{
				From.Label = L->Sim().GetMap().Describe(*Idx);
				From.CompKind = L->Sim().GetMap().Comps[*Idx].Kind;
				From.bInhibited = T.InhibitKinds.Contains(From.CompKind) || T.InhibitIds.Contains(FName(*FromComp));
			}
		}
		int32 PadIdx = INDEX_NONE;
		const FString PadId = PadLabelAt(First.FromCm, &PadIdx);
		if (!PadId.IsEmpty())
		{
			From.Kind = EEndKind::Pad;
			From.bPad = true;
			From.bEmergencyPad = Pads[PadIdx].bEmergency;
			From.Pad = Pads[PadIdx].bEmergency || Pads[PadIdx].bCargo ? Pads[PadIdx].Index : PadIdx;
			From.Label = Pads[PadIdx].bCargo ? FString(TEXT("the cargo pad")) : (Pads[PadIdx].bEmergency ? FString::Printf(TEXT("emergency pad %d"), Pads[PadIdx].Index + 1) : FString::Printf(TEXT("pad %d"), PadIdx + 1));
		}
		From.Room = RoomOf(FromComp, TEXT("the room"));
		if (From.Label.IsEmpty())
		{
			From.Label = TEXT("where they stand");
		}
		for (const FAstraXportSubject& Sub : OutJob.Subs)
		{
			if (!Sub.FromComp.IsEmpty() && (T.InhibitIds.Contains(FName(*Sub.FromComp))))
			{
				OutErr = FString::Printf(TEXT("%s stands in a pattern-shielded room: no beam goes out of it"), *Sub.S.Label);
				return false;
			}
			if (L && L->IsRunning())
			{
				if (const int32* Idx = L->Sim().GetMap().CompByName.Find(FName(*Sub.FromComp)); Idx && T.InhibitKinds.Contains(L->Sim().GetMap().Comps[*Idx].Kind))
				{
					OutErr = FString::Printf(TEXT("%s stands in %s, which is pattern-shielded: no beam goes out of it"), *Sub.S.Label, *L->Sim().GetMap().Describe(*Idx));
					return false;
				}
			}
		}
	}
	if (!ResolveEnd(O.To, true, OutJob.Subs, To, ToComp, OutErr))
	{
		return false;
	}
	if (bAway && To.Kind == From.Kind && To.Kind != EEndKind::Pad && To.Kind != EEndKind::Site && (To.Kind != EEndKind::Ship || To.Ship.Id == From.Ship.Id))
	{
		OutErr = FString::Printf(TEXT("they are already on %s"), *To.Label);
		return false;
	}
	FString BoardedPlace;
	if (!bAway && To.Kind == EEndKind::Ship)
	{
		// a ship our marines are fighting aboard has her decks in the pattern library (ABBORDAGGI makes them solid round the Captain, and the marines hold a room of them): the beam sets people down beside the
		// marines, in a room the Mandate does not hold and where there is air. Any other ship's inside is not in the library: the Captain does not go there (a person does, and is away aboard her, as ever)
		bool bCaptainGoes = false;
		for (const FAstraXportSubject& Sub : OutJob.Subs)
		{
			bCaptainGoes |= Sub.S.Kind == ESubject::Captain;
		}
		TArray<FVector> Spots;
		TArray<float> Yaws;
		FString Why;
		bool bScene = false;
		const bool bFound = BoardedArrival(To.Ship.Id, OutJob.Subs.Num(), bCaptainGoes, Spots, Yaws, BoardedPlace, Why, bScene);
		if (bCaptainGoes && !bScene)
		{
			OutErr = FString::Printf(TEXT("the Captain cannot be beamed aboard %s: %s"), *To.Label, *Why);       // (no boarding to land beside: nothing else matters)
			return false;
		}
		if (bScene)
		{
			OutJob.bBoarded = true;
			if (bFound)
			{
				for (int32 i = 0; i < OutJob.Subs.Num() && i < Spots.Num(); ++i)
				{
					OutJob.Subs[i].ToCm = Spots[i];
					OutJob.Subs[i].ToYaw = Yaws[i];
				}
			}
			else
			{
				OutJob.ArrivalWhy = bCaptainGoes ? FString::Printf(TEXT("the Captain cannot be beamed aboard %s: %s"), *To.Label, *Why) : Why;       // (the beam's own rules are read all the same: one refusal says it all)
			}
		}
	}
	if (bAway && To.Kind == EEndKind::Ship)
	{
		OutErr = TEXT("from one ship to another is no beam of ours: bring them home first");
		return false;
	}
	// who is where they will arrive: avoid the Captain and everyone near
	TArray<FVector> Avoid;
	for (const FAstraXportSubject& Sub : OutJob.Subs)
	{
		Avoid.Add(Sub.FromCm);
	}
	{
		FVector Feet;
		float Yaw;
		bool bG, bS;
		if (CaptainFeet(Feet, Yaw, bG, bS) && !bG)
		{
			Avoid.Add(Feet);
		}
		if (const UAstraLifeSubsystem* L = Life(); L && L->IsRunning() && To.Kind == EEndKind::Site)
		{
			for (int32 i = 0; i < L->Sim().NumPeople(); ++i)
			{
				const FAstraLifePerson& Pe = L->Sim().Person(i);
				if (Pe.Status != 2 && !Pe.bAway && !Pe.bTransit && L->Sim().CompOf(i) != INDEX_NONE && L->Sim().GetMap().Comps[L->Sim().CompOf(i)].Id == FName(*ToComp))
				{
					Avoid.Add(Pe.Pos);
				}
			}
		}
	}
	// the spots they will stand on
	const int32 N = OutJob.Subs.Num();
	if (To.Kind == EEndKind::Pad)
	{
		TArray<int32> Taken;
		int32 Cursor = To.bEmergencyPad ? T.Pads + 1 + To.Pad : To.Pad;
		// one person to a pad the order names, and somebody stands on it: the order is not moved to another pad behind its back, it is refused (`occupied`) and the Chief says so
		const int32 Named = To.bEmergencyPad ? T.Pads + 1 + To.Pad : To.Pad;
		bool bNamedBusy = false;
		if (N == 1 && To.bPadOccupied && OutJob.Subs[0].S.Kind != ESubject::Cargo && Pads.IsValidIndex(Named))
		{
			bNamedBusy = FVector::DistSquared2D(OutJob.Subs[0].FromCm, Pads[Named].PosCm) >= FMath::Square(Pads[Named].RadiusCm + 25.f);   // (not the subject's own pad)
		}
		for (FAstraXportSubject& Sub : OutJob.Subs)
		{
			int32 Use = INDEX_NONE;
			if (Sub.S.Kind == ESubject::Cargo)
			{
				Use = T.Pads;                                            // the cargo pad
			}
			else if (bNamedBusy)
			{
				Use = Named;
			}
			else if (To.bEmergencyPad)
			{
				for (int32 k = 0; k < T.EmergencyPads; ++k)
				{
					const int32 Idx = T.Pads + 1 + ((To.Pad + k) % FMath::Max(1, T.EmergencyPads));
					FString Who;
					if (Pads.IsValidIndex(Idx) && !Taken.Contains(Idx) && !PadOccupiedBy(Pads[Idx], Who))
					{
						Use = Idx;
						break;
					}
				}
			}
			else
			{
				for (int32 k = 0; k < T.Pads; ++k)
				{
					const int32 Idx = (To.Pad + k) % T.Pads;
					FString Who;
					bool bBeingLeft = false;
					for (const FAstraXportSubject& Other : OutJob.Subs)
					{
						bBeingLeft |= FVector::DistSquared2D(Other.FromCm, Pads[Idx].PosCm) < FMath::Square(Pads[Idx].RadiusCm + 25.f);
					}
					if (!Taken.Contains(Idx) && (!PadOccupiedBy(Pads[Idx], Who) || bBeingLeft))
					{
						Use = Idx;
						break;
					}
				}
			}
			if (Use == INDEX_NONE || !Pads.IsValidIndex(Use))
			{
				OutErr = TEXT("there are not pads enough free for all of them");
				return false;
			}
			Taken.Add(Use);
			Sub.ToCm = Pads[Use].PosCm;
			Sub.ToYaw = Pads[Use].YawDeg;
		}
		(void)Cursor;
		To.bPadOccupied = bNamedBusy;
		To.Label = N == 1 ? Pads[Taken[0]].Id == FName(TEXT("cargo")) ? FString(TEXT("the cargo pad")) : (Pads[Taken[0]].bEmergency ? FString::Printf(TEXT("emergency pad %d"), Pads[Taken[0]].Index + 1) : FString::Printf(TEXT("pad %d"), Taken[0] + 1))
		             : FString::Printf(TEXT("the pads (%s)"), *To.Label);
		To.Pad = To.bEmergencyPad ? Pads[Taken[0]].Index : Taken[0];
	}
	else if (To.Kind == EEndKind::Site)
	{
		TArray<FVector> Spots;
		TArray<float> Yaws;
		if (!PickSpots(ToComp, N, Avoid, Spots, Yaws))
		{
			OutErr = FString::Printf(TEXT("there is no clear floor for %d in %s"), N, *To.Label);
			return false;
		}
		for (int32 i = 0; i < N; ++i)
		{
			OutJob.Subs[i].ToCm = Spots[i];
			OutJob.Subs[i].ToYaw = Yaws[i];
		}
	}
	else if (To.Kind == EEndKind::Surface)
	{
		const UAstraShipSubsystem* S = Ship();
		const FVector Site = S ? S->SurfaceSite() : FVector::ZeroVector;
		for (int32 i = 0; i < N; ++i)
		{
			const float A = (float)i * 2.3999f + 0.6f;                   // a golden-angle ring round the landing spot: nobody stands on anybody
			const float R = i == 0 ? 0.f : 150.f + 55.f * (float)(i / 5);
			const FVector Base = Site + FVector((double)T.LandingOffsetM.X * 100.0, (double)T.LandingOffsetM.Y * 100.0, 0.0) + FVector(FMath::Cos(A), FMath::Sin(A), 0.f) * R;
			OutJob.Subs[i].ToCm = Base;
			OutJob.Subs[i].ToYaw = FMath::RadiansToDegrees(FMath::Atan2(Site.Y - Base.Y, Site.X - Base.X));
		}
	}
	OutJob.Req.From = From;
	OutJob.Req.To = To;
	for (FAstraXportSubject& Sub : OutJob.Subs)
	{
		// already in an order that has not finished: a second order for the same person waits for the first
		for (const FAstraXportJob& Other : JobList)
		{
			if (AstraXportLive(Other.Phase))
			{
				for (const FAstraXportSubject& O2 : Other.Subs)
				{
					Sub.S.bInPattern |= O2.S.Id == Sub.S.Id;
				}
			}
		}
		OutJob.Req.Subjects.Add(Sub.S);
	}
	for (const FString& Ov : O.Override)
	{
		const FString Ox = XpNorm(Ov);
		OutJob.Req.bOverrideHazard |= Ox.Contains(TEXT("hazard"));
		OutJob.Req.bForce |= Ox.Contains(TEXT("weak")) || Ox.Contains(TEXT("force"));
	}
	OutJob.Req.bShieldWindow = O.bWindow;
	OutJob.bForced = OutJob.Req.bForce;
	OutJob.bHold = O.bHold;
	OutJob.By = O.By;
	OutJob.FromComp = FromComp;
	OutJob.ToComp = ToComp;
	OutJob.ToContact = To.Kind == EEndKind::Ship ? To.Ship.Id : (From.Kind == EEndKind::Ship ? From.Ship.Id : FString());
	OutJob.FromText = DescribeEnd(From, FromComp);
	OutJob.ToText = DescribeEnd(To, ToComp);
	if (OutJob.bBoarded)
	{
		OutJob.ToText += FString::Printf(TEXT(", set down in %s"), *BoardedPlace);
	}
	OutJob.bEmergency = From.bEmergencyPad || To.bEmergencyPad;
	return true;
}

bool UAstraTransporterSubsystem::BoardedArrival(const FString& ShipContact, int32 N, bool bCaptain, TArray<FVector>& OutSpots, TArray<float>& OutYaws, FString& OutPlace, FString& OutWhy, bool& bOutScene) const
{
	OutSpots.Reset();
	OutYaws.Reset();
	OutPlace.Reset();
	OutWhy.Reset();
	bOutScene = false;
	const UAstraBoardSubsystem* Bd = Board();
	if (!Bd)
	{
		OutWhy = TEXT("there is no boarding aboard her to land beside");
		return false;
	}
	UAstraBoardSubsystem::FBeamLimits Lim;
	Lim.AirMin = T.AirMin;
	Lim.FireMax = T.FireMax;
	Lim.SmokeMax = T.SmokeMax;
	UAstraBoardSubsystem::FBeamAboard W;
	const bool bOk = Bd->BeamAboardQuery(ShipContact, N, bCaptain, Lim, W);
	bOutScene = W.bScene;
	if (!bOk)
	{
		OutWhy = W.Fix.IsEmpty() ? W.Why : FString::Printf(TEXT("%s (to clear it: %s)"), *W.Why, *W.Fix);
		return false;
	}
	for (const UAstraBoardSubsystem::FBeamSpot& S : W.Spots)
	{
		OutSpots.Add(S.FeetWorld);
		OutYaws.Add(S.Yaw);
	}
	OutPlace = W.Place;
	return true;
}

void UAstraTransporterSubsystem::RefreshRequest(FRequest& R, const FAstraXportJob& J) const
{
	for (FEnd* E : {&R.From, &R.To})
	{
		const FString& Comp = E == &R.From ? J.FromComp : J.ToComp;
		if (E->Kind == EEndKind::Ship && !E->Ship.Id.IsEmpty())
		{
			FHull H;
			if (FillShip(H, E->Ship.Id))
			{
				E->Ship = H;
			}
			else
			{
				E->Ship.bPresent = false;                      // she left the plot
			}
		}
		else if (E->Kind == EEndKind::Pad || E->Kind == EEndKind::Site)
		{
			E->Room = RoomOf(Comp, E->Room.Name);
		}
		else if (E->Kind == EEndKind::Surface)
		{
			if (const UAstraShipSubsystem* S = Ship())
			{
				E->DirBody = S->PlanetDirectionWorld().GetSafeNormal();
				if (E->DirBody.IsNearlyZero())
				{
					E->DirBody = FVector(0, 0, -1);
				}
				E->Owner = (uint8)XpOwnerIndex(S->SurfaceOwner());
			}
		}
	}
	if (R.To.bPad)
	{
		const int32 Idx = R.To.bEmergencyPad ? T.Pads + 1 + R.To.Pad : R.To.Pad;
		FString Who;
		R.To.bPadOccupied = false;
		if (Pads.IsValidIndex(Idx) && PadOccupiedBy(Pads[Idx], Who))
		{
			bool bOurs = false;
			for (const FAstraXportSubject& S : J.Subs)
			{
				bOurs |= FVector::DistSquared2D(S.FromCm, Pads[Idx].PosCm) < FMath::Square(Pads[Idx].RadiusCm + 25.f);
			}
			R.To.bPadOccupied = !bOurs && J.Phase < EAstraXportPhase::Demat;
		}
	}
}

AstraXport::FVerdict UAstraTransporterSubsystem::Preflight(const FAstraXportOrder& O, FString& OutWhy) const
{
	FVerdict V;
	FAstraXportJob J;
	if (!MakeRequest(O, J, OutWhy))
	{
		return V;
	}
	FEnv E;
	BuildEnv(E);
	FRequest R = J.Req;
	RefreshRequest(R, J);
	V = Evaluate(T, E, R);
	if (!J.ArrivalWhy.IsEmpty())
	{
		FBlocker B;
		B.Code = FName(TEXT("arrival"));
		B.Why = J.ArrivalWhy;
		B.bHard = true;
		V.Blockers.Add(B);
		V.bOk = false;
	}
	return V;
}
