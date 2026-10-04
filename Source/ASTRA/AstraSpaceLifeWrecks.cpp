// ASTRA — what the war leaves, in the game: a ship's loss recorded (her pieces, her field, her lifepods, what was left aboard), the hand-over of her pieces from the war's effects, the wrecks
// drawn as instances, the campaign's save, the rescue hooks, the console. The records and their rules are plain C++ (AstraWrecks.*); what and why: docs/SPAZIO.md.

#include "AstraSpaceLife.h"
#include "AstraSpaceLifeDrawUtil.h"
#include "AstraBattleSubsystem.h"
#include "AstraFleetInterior.h"
#include "ASTRA.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "HAL/PlatformTime.h"
#include "Misc/DateTime.h"
#include "Misc/FileHelper.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "Policies/CondensedJsonPrintPolicy.h"

using namespace AstraSpaceDraw;
using AstraSpace::FWrecks;
using AstraSpace::FSite;
using AstraSpace::FPieceRec;
using AstraSpace::FPodRec;

namespace
{
	TAutoConsoleVariable<int32> CVarWkWrecks(TEXT("astra.space.wrecks"), 1, TEXT("What the war leaves (wrecks, debris, lifepods): 1 on, 0 off (a loss is then not recorded; the war's own effects stand alone)"));
	TAutoConsoleVariable<float> CVarWkWreckKm(TEXT("astra.space.wrecks.km"), 220.f, TEXT("A wreck's pieces are drawn out to this range from the Aquila (km)"));
	TAutoConsoleVariable<int32> CVarWkChunks(TEXT("astra.space.wrecks.chunks"), 420, TEXT("The most chunks of debris drawn at once (the nearest fields first)"));
	TAutoConsoleVariable<float> CVarWkPlotKm(TEXT("astra.space.wrecks.plot.km"), (float)AstraSpace::FWrecks::ContactKm, TEXT("The pieces of wrecks within this range of the Aquila (km) are contacts on the plot: the crew names them, the screens show them (0: none)"));
	TAutoConsoleVariable<int32> CVarWkPlotMax(TEXT("astra.space.wrecks.plot.max"), AstraSpace::FWrecks::MaxContacts, TEXT("The most wreck contacts on the plot at once, the nearest first (the plot's lists are read every frame by a dozen readers)"));
	TAutoConsoleVariable<int32> CVarWkListed(TEXT("astra.space.wrecks.listed"), AstraSpace::FWrecks::ListedContacts, TEXT("How many of the nearest wreck contacts (within 40 km) the crew's own state lists: the minds read it every turn"));

	double WkPlotKm() { return FMath::Clamp((double)CVarWkPlotKm.GetValueOnGameThread(), 0.0, 120.0); }
	int32 WkPlotMax() { return FMath::Clamp(CVarWkPlotMax.GetValueOnGameThread(), 0, 32); }
	int32 WkListed() { return FMath::Clamp(CVarWkListed.GetValueOnGameThread(), 0, 8); }

	constexpr double WkKm = 1000.0;
	constexpr double WkChunkFieldKm = 24.0;                  // a field is looked into when its edge is this near
	constexpr double WkPodHullKm = 14.0;                     // a lifepod's hull is drawn out to this range (6 m long: a few pixels)
	constexpr double WkPodLampKm = 170.0;                    // and its beacon to this
	const TCHAR* const WkSecNames[3] = {TEXT("SecBow"), TEXT("SecMid"), TEXT("SecStern")};
	const float WkChunkMeshM[3] = {13.f, 24.f, 9.f};         // the debris meshes as made (art/blender/space3_props.py): a plate, a girder, a chunk
	const TCHAR* const WkChunkNames[3] = {TEXT("Plate"), TEXT("Girder"), TEXT("Chunk")};

	TCHAR WkFactionLetter(uint8 F) { return F == 0 ? TEXT('A') : (F == 1 ? TEXT('M') : TEXT('G')); }
}

double UAstraSpaceLife::WreckClock() const
{
	return (Owner ? (double)Owner->GetBattleTime() : 0.0) + ClockBase;
}

AstraSpace::FSkyFrame UAstraSpaceLife::SkyFrame() const
{
	AstraSpace::FSkyFrame Fr;
	const AstraSpace::FAnchors A = bLaidOut ? Layout.Anchors : ReadAnchors();
	Fr.Origin = A.bGate ? A.GatePos : A.Origin;
	Fr.Att = A.bGate ? A.GateAtt : FQuat::Identity;
	return Fr;
}

// ------------------------------------------------------------------------------------------------------------------ a ship is lost
void UAstraSpaceLife::OnShipLost(const FAstraBattleShip& S, const FAstraDeathEvent& E, bool bFxPieces)
{
	if (!IsActive() || !Owner || SystemName.IsEmpty() || CVarWkWrecks.GetValueOnGameThread() == 0)
	{
		return;
	}
	if (E.How != EAstraFate::Breakup && E.How != EAstraFate::ReactorBreach && E.How != EAstraFate::Destroyed)
	{
		return;                                                 // (a ship gone dark is not lost: she stays in the plot, a derelict)
	}
	AstraSpace::FLoss L;
	L.ShipId = S.Id;
	L.Name = S.Name;
	L.Class = S.Class;
	L.Contact = S.ContactId;
	L.KnownAs = Owner->KnownLabel(S);                          // what the Aquila's sensors called her (fog of war: the beacons say no more than that)
	L.HullMesh = S.Mesh;
	L.ClassKey = S.ClassKey;
	L.Faction = S.Side == EAstraSide::Astra ? 0 : (S.Side == EAstraSide::Mandate ? 1 : 2);
	L.How = E.How == EAstraFate::ReactorBreach ? AstraSpace::EHowLost::Reactor : (E.How == EAstraFate::Breakup ? AstraSpace::EHowLost::Breakup : AstraSpace::EHowLost::Destroyed);
	L.Section = E.Section;
	L.Pos = S.Pos;
	L.Vel = S.Vel;
	L.Att = S.Att;
	L.Radius = S.Radius;
	if (S.Box.Valid())
	{
		L.BoxMid = S.Pos + S.Att.RotateVector(FVector(S.Box.Mid, 0.0, 0.0));
		L.BoxHalf = FVector(S.Box.Hx, S.Box.Hy, S.Box.Hz);
	}
	else
	{
		L.BoxMid = S.Pos;
		L.BoxHalf = FVector(S.Radius, S.Radius * 0.25, S.Radius * 0.2);
	}
	// what was left aboard: her inside's people and rooms when she had one (FLOTTA-VIVA lost them with her a moment ago: what it counted is still in it), else the class's roster
	if (const FAstraShipInterior* I = S.Interior.Get())
	{
		AstraSpace::FAboard& A = L.Aboard;
		A.bInside = true;
		A.Complement = I->CrewTotal();
		A.Killed = I->CrewDead();
		A.Alive = I->CrewLostWithShip();
		FFleetSnapshot Snap;
		I->Snapshot(Snap);
		for (const FFleetSnapshot::FRoom& R : Snap.Rooms)
		{
			if (A.Rooms.Num() >= 400)
			{
				break;
			}
			AstraSpace::FAboardRoom Room;
			Room.Comp = R.Comp;
			Room.Air = R.Air;
			Room.Hole = R.Hole;
			Room.Fire = R.Fire;
			Room.Smoke = R.Smoke;
			Room.Heat = R.Heat;
			Room.Power = R.Power;
			Room.Wreck = R.Wreck;
			Room.bGutted = R.bGutted;
			Room.bLocked = R.bLocked;
			A.Rooms.Add(Room);
		}
		for (const FName& D : Snap.SealedDoors)
		{
			if (A.SealedDoors.Num() < 120)
			{
				A.SealedDoors.Add(D.ToString());
			}
		}
	}
	// her pieces, as the war's effects made them (they hold them as actors for the first minute)
	TArray<AstraSpace::FPieceIn> Pieces;
	if (bFxPieces && Owner->WarFX)
	{
		for (const AstraFx::FPiece& P : Owner->WarFX->GetPieces())
		{
			if (P.ShipId != S.Id)
			{
				continue;
			}
			AstraSpace::FPieceIn In;
			In.Section = P.Section;
			In.Pivot = P.Pivot;
			In.PivotLocal = P.PivotLocal;
			In.Vel = P.Vel;
			In.Att = P.Att;
			In.SpinAxis = P.SpinAxis;
			In.SpinRate = P.SpinRate;
			In.Radius = P.Radius;
			In.bReactor = P.bReactor;
			Pieces.Add(In);
		}
	}
	const double Now = WreckClock();
	const uint32 LossSeed = HashCombine(GetTypeHash(SystemName.ToLower()), HashCombine((uint32)S.Id * 2654435761u, (uint32)FMath::RoundToInt((float)(Owner->GetBattleTime() * 10.0))));
	const AstraSpace::FSite& Site = Wrecks.AddLoss(SystemName, L, Pieces, Now, LossSeed, bLaidOut ? Sky : SkyFrame());
	UE_LOG(LogASTRA, Log, TEXT("[Space] lost: %s (%s), %s: %d pieces, %d chunks of debris, %d lifepods with %d survivors of %d alive aboard"), *S.Name, *S.ContactId, AstraSpace::HowLostName(L.How), Site.Pieces.Num(),
	       Site.Field.Count, Site.Pods.Num(), Site.Aboard.Escaped, Site.Aboard.Alive);
}

// ------------------------------------------------------------------------------------------------------------------ the war's effects let go
void UAstraSpaceLife::HandOver(double Now)
{
	UAstraWarFX* Fx = Owner ? Owner->WarFX.Get() : nullptr;
	for (FSite& S : Wrecks.SitesMutable())
	{
		if (S.System != SystemKey)
		{
			continue;
		}
		const double Age = Now - S.DiedAt;
		for (FPieceRec& P : S.Pieces)
		{
			if (!P.bInFx || P.Section > 2)
			{
				continue;                                              // (a whole hull the war's older explosion left stays its own until the system is left)
			}
			const AstraFx::FPiece* Held = nullptr;
			if (Fx)
			{
				for (const AstraFx::FPiece& FP : Fx->GetPieces())
				{
					if (FP.ShipId == S.ShipId && FP.Section == P.Section)
					{
						Held = &FP;
						break;
					}
				}
			}
			if (Held && Age < FWrecks::HandOverS)
			{
				continue;                                              // still theirs: burning at the cut, the windows going out
			}
			if (!Held && Age < 1.0)
			{
				continue;                                              // (made in this very frame)
			}
			if (Held)
			{
				// from where the effects have it now: what the player has seen goes on without a jump
				Wrecks.ReAnchor(S, P, Now, Sky, Held->Pivot, Held->Vel, Held->Att, Held->SpinAxis, Held->SpinRate);
				Fx->ReleasePiece(S.ShipId, P.Section);                 // (Held is gone from here on)
			}
			// else: the effects let it go sooner (their cap on pieces gives the oldest up when many ships break at once): its own arithmetic carries it from where it began
			P.bInFx = false;
			S.bDirty = true;
		}
	}
}

// ------------------------------------------------------------------------------------------------------------------ a frame
void UAstraSpaceLife::TickWrecks(float SimDt)
{
	if (Wrecks.Sites().Num() == 0 && WreckContactsNow == 0)
	{
		return;
	}
	const double T0 = FPlatformTime::Seconds();
	const double Now = WreckClock();
	HandOver(Now);
	if ((WreckThinkT -= SimDt) <= 0.f && Owner->Ships.Num() && Owner->Ships[0].bAlive)
	{
		WreckThinkT = 0.5f;
		FVector Falcon = FVector::ZeroVector;
		const FVector* FalconPtr = nullptr;
		if (Owner->IsPiloting())
		{
			if (const FAstraBattleShip* F2 = Owner->FindById(Owner->GetPilotedId()))
			{
				Falcon = F2->Pos;
				FalconPtr = &Falcon;
			}
		}
		Wrecks.Think(SystemName, Now, Sky, Owner->Ships[0].Pos, FalconPtr, Owner->bEngagementActive, Events);
	}
	if ((WreckPruneT -= SimDt) <= 0.f)
	{
		WreckPruneT = 60.f;
		Wrecks.Prune(Now);
	}
	TickWreckContacts(Now, SimDt);
	WrecksMs += (FPlatformTime::Seconds() - T0) * 1000.0;
}

// ------------------------------------------------------------------------------------------------------------------ the pieces as contacts of the plot
const FPieceRec* UAstraSpaceLife::PieceOfContact(const FAstraBattleShip& S, const FSite** OutSite) const
{
	if (!S.bWreck)
	{
		return nullptr;
	}
	const FSite* Site = Wrecks.FindById(S.WreckSite);
	if (!Site || !Site->Pieces.IsValidIndex(S.WreckPiece))
	{
		return nullptr;
	}
	if (OutSite)
	{
		*OutSite = Site;
	}
	return &Site->Pieces[S.WreckPiece];
}

bool UAstraSpaceLife::WreckMeshFrame(const FAstraBattleShip& S, FVector& OutOrigin, FQuat& OutAtt) const
{
	const FPieceRec* P = PieceOfContact(S);
	if (!P)
	{
		return false;
	}
	const double Now = WreckClock();
	OutAtt = Sky.ToSystem(FWrecks::AttAt(*P, Now));
	OutOrigin = Sky.ToSystem(FWrecks::PosAt(*P, Now)) - OutAtt.RotateVector(P->PivotLocal);
	return true;
}

FPieceRec* UAstraSpaceLife::MutablePieceOfContact(const FAstraBattleShip& S, FSite** OutSite)
{
	if (!S.bWreck)
	{
		return nullptr;
	}
	for (FSite& Si : Wrecks.SitesMutable())
	{
		if (Si.Id == S.WreckSite && Si.Pieces.IsValidIndex(S.WreckPiece))
		{
			if (OutSite)
			{
				*OutSite = &Si;
			}
			return &Si.Pieces[S.WreckPiece];
		}
	}
	return nullptr;
}

int32 UAstraSpaceLife::MakeWreckContact(FSite& Site, int32 Piece, double Now)
{
	FPieceRec& P = Site.Pieces[Piece];
	FString Id = FWrecks::PieceContactId(Site, Piece);
	if (Owner->FindByContact(Id))
	{
		Id = FString::Printf(TEXT("%s-%d"), *Id, Site.Id);          // (another ship has her number: a campaign that began again with the old ones)
	}
	const FVector Pos = Sky.ToSystem(FWrecks::PosAt(P, Now));
	// not a ship of any class: "wreck", no mesh of her own (the pieces are drawn as instances), so the war makes no model of her (AstraWar::KeyFor knows no such class)
	const int32 I = Owner->AddShip(Id, FWrecks::PieceName(Site, Piece), TEXT("wreck"), TEXT("SM_WRECK"), EAstraSide::Neutral, Pos, 0.f, 0.f, FMath::Max(P.Radius, 10.f), 0.f, 0.f);
	FAstraBattleShip& C = Owner->Ships[I];
	C.Pos = Pos;
	C.Vel = Sky.DirToSystem(P.Vel);
	C.Att = Sky.ToSystem(FWrecks::AttAt(P, Now));
	C.bFixture = true;                                   // for the war's rules she is a fixture: no AI runs her, nothing hits her, nobody fights over her (her place is the record's arithmetic, kept every frame)
	C.bDerelict = true;
	C.bWreck = true;
	C.WreckSite = Site.Id;
	C.WreckPiece = Piece;
	C.RailDamage = 0.f;
	C.Missiles = 0;
	C.PDChannels = 0;
	C.bShieldsUp = false;
	C.Mode = EAstraShipMode::Idle;
	C.bIdentified = C.bClassified = true;                // (she was seen to go: the crew knows what she was)
	C.Track = 2;
	P.PlotId = C.Id;
	return C.Id;
}

void UAstraSpaceLife::RemoveWreckContacts()
{
	for (FSite& S : Wrecks.SitesMutable())
	{
		for (FPieceRec& P : S.Pieces)
		{
			P.PlotId = -1;
		}
	}
	ListedWrecks.Reset();
	WreckContactsNow = 0;
	if (!Owner)
	{
		return;
	}
	const int32 Before = Owner->Ships.Num();
	Owner->Ships.RemoveAll([](const FAstraBattleShip& S) { return S.bWreck; });
	if (Owner->Ships.Num() != Before)
	{
		Owner->RebuildIdIndex();
		Owner->BuildGrid();                              // (the battle's lists of indices into its ships are made again: nobody reads a stale one between ticks)
		++Owner->PlotStamp;
	}
}

void UAstraSpaceLife::TickWreckContacts(double Now, float SimDt)
{
	if (!Owner || Owner->Ships.Num() == 0)
	{
		return;
	}
	const FVector Me = Owner->Ships[0].Pos;
	if ((WreckContactT -= SimDt) <= 0.f)
	{
		WreckContactT = 0.5f;
		// ---- who is on the plot: every piece within the plot's reach of the Aquila (a little farther for those already on it), the nearest few
		const double PlotKm = WkPlotKm();
		struct FCand
		{
			FSite* Site;
			int32 Piece;
			double D;
		};
		TArray<FCand, TInlineAllocator<48>> Cands;
		for (FSite& S : Wrecks.SitesMutable())
		{
			if (S.System != SystemKey)
			{
				continue;
			}
			for (int32 pi = 0; pi < S.Pieces.Num(); ++pi)
			{
				const double D = FVector::Dist(Sky.ToSystem(FWrecks::PosAt(S.Pieces[pi], Now)), Me);
				if (D < (PlotKm + (S.Pieces[pi].PlotId >= 0 ? 10.0 : 0.0)) * WkKm)
				{
					Cands.Add({&S, pi, D});
				}
			}
		}
		Cands.Sort([](const FCand& A, const FCand& B) { return A.D < B.D; });
		if (Cands.Num() > WkPlotMax())
		{
			Cands.SetNum(WkPlotMax());
		}
		TSet<const FPieceRec*> Keep;
		for (const FCand& C : Cands)
		{
			Keep.Add(&C.Site->Pieces[C.Piece]);
		}
		TArray<int32> Gone;                              // plot ids of contacts that leave the plot
		for (FSite& S : Wrecks.SitesMutable())
		{
			for (FPieceRec& P : S.Pieces)
			{
				if (P.PlotId >= 0 && !Keep.Contains(&P))
				{
					Gone.Add(P.PlotId);
					P.PlotId = -1;
				}
			}
		}
		for (int32 i = 1; i < Owner->Ships.Num(); ++i)  // (and any whose site was let go of, or whose piece no longer says it is hers)
		{
			const FAstraBattleShip& S = Owner->Ships[i];
			if (S.bWreck && !Gone.Contains(S.Id))
			{
				const FPieceRec* P = PieceOfContact(S);
				if (!P || P->PlotId != S.Id)
				{
					Gone.Add(S.Id);
				}
			}
		}
		if (Gone.Num())
		{
			Owner->Ships.RemoveAll([&Gone](const FAstraBattleShip& S) { return S.bWreck && Gone.Contains(S.Id); });
			Owner->RebuildIdIndex();
			Owner->BuildGrid();
			++Owner->PlotStamp;
		}
		for (const FCand& C : Cands)
		{
			if (C.Site->Pieces[C.Piece].PlotId < 0)
			{
				MakeWreckContact(*C.Site, C.Piece, Now);
			}
		}
		// the few the crew's own state lists: the nearest within ListedKm
		ListedWrecks.Reset();
		for (const FCand& C : Cands)
		{
			if (ListedWrecks.Num() >= WkListed() || C.D > FWrecks::ListedKm * WkKm)
			{
				break;
			}
			ListedWrecks.Add(C.Site->Pieces[C.Piece].PlotId);
		}
		WreckContactsNow = Cands.Num();
		WreckContactsPeak = FMath::Max(WreckContactsPeak, WreckContactsNow);
		// ---- the eyes near a piece learn what the range allows: the Aquila's own sensors, a flight of ours sent to look, the Captain's Falcon (her rooms from 4 km, her dead alongside)
		struct FEye
		{
			FVector Pos;
			int32 Squadron;                              // -1: the Aquila
			bool bFalcon;
		};
		TArray<FEye, TInlineAllocator<64>> Eyes;
		Eyes.Add({Me, -1, false});
		for (const FAstraBattleShip& S : Owner->Ships)
		{
			if (S.bCraft && S.bAlive && S.Side == EAstraSide::Astra && S.CraftKind != 3 && Eyes.Num() < 240)
			{
				Eyes.Add({S.Pos, S.Squadron, S.bPiloted});
			}
		}
		for (const FCand& C : Cands)
		{
			FPieceRec& P = C.Site->Pieces[C.Piece];
			if (P.Seen >= 3)
			{
				continue;
			}
			const FEye* Best = nullptr;
			double BestD = 1.0e18;
			const FVector At = Sky.ToSystem(FWrecks::PosAt(P, Now));
			for (const FEye& E : Eyes)
			{
				const double D = FVector::Dist(E.Pos, At);
				if (D < BestD)
				{
					BestD = D;
					Best = &E;
				}
			}
			const int32 Stage = Best ? FWrecks::StageForRange(BestD) : 0;
			if (Stage < 2 || Stage <= P.Seen)
			{
				continue;
			}
			FString Told;
			for (int32 St = FMath::Max<int32>(P.Seen + 1, 2); St <= Stage; ++St)
			{
				Told += (Told.IsEmpty() ? TEXT("") : TEXT("; ")) + Wrecks.Findings(*C.Site, C.Piece, St, Now);
			}
			P.Seen = (uint8)Stage;
			C.Site->bDirty = true;
			AstraSpace::FEvent E;
			E.Kind = AstraSpace::EEventKind::WreckLook;
			E.bReport = !Owner->bEngagementActive;
			E.At = At;
			FString By = TEXT("sensors");
			if (Best->Squadron >= 0 || Best->bFalcon)
			{
				By = Best->bFalcon ? FString(TEXT("flight: Eagle")) : (Owner->Squadrons.IsValidIndex(Best->Squadron) ? FString::Printf(TEXT("flight: %s"), *Owner->Squadrons[Best->Squadron].CallSign) : FString(TEXT("flight")));
			}
			E.Text = FString::Printf(TEXT("%s: %.1f km from the %s (%s) — %s"), *By, BestD / WkKm, *FWrecks::PieceName(*C.Site, C.Piece), *FWrecks::PieceContactId(*C.Site, C.Piece), *Told);
			Events.Add(E);
		}
	}
	// ---- every frame: each contact is where its record has it (a few: the plot's own tick leaves a fixture alone)
	if (WreckContactsNow > 0)
	{
		for (FSite& S : Wrecks.SitesMutable())
		{
			if (S.System != SystemKey)
			{
				continue;
			}
			for (FPieceRec& P : S.Pieces)
			{
				if (P.PlotId < 0)
				{
					continue;
				}
				if (FAstraBattleShip* C = Owner->FindById(P.PlotId))
				{
					C->Pos = Sky.ToSystem(FWrecks::PosAt(P, Now));
					C->Vel = Sky.DirToSystem(P.Vel);
					C->Att = Sky.ToSystem(FWrecks::AttAt(P, Now));
				}
			}
		}
	}
}

bool UAstraSpaceLife::WreckContactJson(const FAstraBattleShip& S, TSharedRef<FJsonObject>& Out) const
{
	const FSite* Site = nullptr;
	const FPieceRec* P = PieceOfContact(S, &Site);
	if (!P || !Owner || Owner->Ships.Num() == 0 || !ListedWrecks.Contains(S.Id))
	{
		return false;
	}
	const FVector Me = Owner->Ships[0].Pos;
	Out->SetStringField(TEXT("id"), S.ContactId);
	Out->SetStringField(TEXT("class"), TEXT("wreck"));
	Out->SetStringField(TEXT("name"), S.Name);
	Out->SetStringField(TEXT("status"), Wrecks.Status(*Site, S.WreckPiece, WreckClock()));
	Out->SetNumberField(TEXT("range_km"), FMath::RoundToDouble(FVector::Dist(Me, S.Pos) / 100.0) / 10.0);
	Out->SetNumberField(TEXT("bearing_deg"), FMath::RoundToDouble(Owner->BearingTo(S.Pos)));
	Out->SetNumberField(TEXT("mark_deg"), FMath::RoundToDouble(Owner->MarkTo(S.Pos)));
	Out->SetNumberField(TEXT("speed_mps"), FMath::RoundToDouble(S.Vel.Size()));
	return true;
}

bool UAstraSpaceLife::ScanWreck(const FAstraBattleShip& S, FString& OutDetail)
{
	FSite* Site = nullptr;
	FPieceRec* P = MutablePieceOfContact(S, &Site);
	if (!P || !Owner || Owner->Ships.Num() == 0)
	{
		OutDetail = FString::Printf(TEXT("scan of %s: nothing there any more"), *S.ContactId);
		return true;
	}
	const double Now = WreckClock();
	// the nearest eyes: the Aquila's own, or one of our craft's (a flight sent to look sees closer than she does)
	double RangeM = FVector::Dist(Owner->Ships[0].Pos, S.Pos);
	for (const FAstraBattleShip& C : Owner->Ships)
	{
		if (C.bCraft && C.bAlive && C.Side == EAstraSide::Astra && C.CraftKind != 3)
		{
			RangeM = FMath::Min(RangeM, (double)FVector::Dist(C.Pos, S.Pos));
		}
	}
	const int32 Stage = FWrecks::StageForRange(RangeM);
	const int32 SiteIndex = S.WreckPiece;
	const FString Head = FString::Printf(TEXT("scan of %s (%s) from %.1f km"), *S.ContactId, *FWrecks::PieceName(*Site, SiteIndex), RangeM / WkKm);
	if (Stage <= P->Seen)
	{
		OutDetail = FString::Printf(TEXT("%s: nothing new from this range — %s"), *Head,
		                            Stage < 2 ? TEXT("a flight sent to look, or the Aquila closing to 4 km, would show her rooms") : (Stage < 3 ? TEXT("closing to 800 m would count her dead") : TEXT("everything there is to learn from outside has been learned")));
		return true;
	}
	FString Told;
	for (int32 St = P->Seen + 1; St <= Stage; ++St)
	{
		Told += (Told.IsEmpty() ? TEXT("") : TEXT("; ")) + Wrecks.Findings(*Site, SiteIndex, St, Now);
	}
	P->Seen = (uint8)Stage;
	Site->bDirty = true;
	OutDetail = FString::Printf(TEXT("%s: %s"), *Head, *Told);
	return true;
}

// ------------------------------------------------------------------------------------------------------------------ drawing
void UAstraSpaceLife::DrawWrecks(double Now)
{
	WreckHullsNow = ChunksNow = PodsNow = EmbersNow = 0;
	if (Wrecks.Sites().Num() == 0)
	{
		return;
	}
	const AstraSpace::FDataSet& D = AstraSpace::Data();
	const FString& Key = SystemKey;
	const double PieceKm = FMath::Clamp((double)CVarWkWreckKm.GetValueOnGameThread(), 20.0, 250.0);
	const int32 ChunkCap = FMath::Clamp(CVarWkChunks.GetValueOnGameThread(), 0, 1200);
	// What drifts is drawn in the system's frame, under the one component the belt and the buoys hang from: the Aquila's flight is one transform a frame (Tick) and not a transform for every
	// wreck, and a wreck is written again only when it has moved enough to show. A chunk tumbling past the window is written every frame (within 3 km), one at the other end of the sky three
	// times a second; a page nothing in it was written for is not sent at all (FlushSets).
	const auto Due = [this](double Km) -> bool
	{
		const uint32 Every = Km < 3.0 ? 1u : (Km < 10.0 ? 2u : (Km < 40.0 ? 6u : 20u));
		return Every == 1u || (Frame % Every) == 0u;
	};
	static const FString PodMeshes[3] = {TEXT("SM_POD_A"), TEXT("SM_POD_M"), TEXT("SM_POD_G")};
	static const FString PodKeys[3] = {TEXT("SM_POD_A#dead"), TEXT("SM_POD_M#dead"), TEXT("SM_POD_G#dead")};
	// the fields near the Aquila, nearest first (a cap on the chunks drawn must keep the ones she can see)
	struct FNearField { FSite* Site; double Edge; };
	TArray<FNearField, TInlineAllocator<16>> Fields;
	for (FSite& S : Wrecks.SitesMutable())
	{
		if (S.System != Key)
		{
			continue;
		}
		const uint32 SH = SpMix((uint32)S.Id * 2654435761u);
		const int32 Fac = FMath::Clamp((int32)S.Faction, 0, 2);
		// ---- the pieces: instances of the section meshes, dark (the effects hold the first minute's burning ones as actors)
		for (int32 pi = 0; pi < S.Pieces.Num(); ++pi)
		{
			FPieceRec& P = S.Pieces[pi];
			if (P.bInFx)
			{
				continue;
			}
			const FVector Pivot = Sky.ToSystem(FWrecks::PosAt(P, Now));
			const double D2 = FVector::DistSquared(Pivot, F.Origin);
			if (D2 > FMath::Square(PieceKm * WkKm))
			{
				continue;
			}
			if (P.SetIdx == -1)
			{
				const FString Name = P.Section < 3 ? FString::Printf(TEXT("%s_%s#%s"), *S.HullMesh, WkSecNames[P.Section], P.bBurnt ? TEXT("char") : TEXT("dead"))
				                                   : FString::Printf(TEXT("%s#%s"), *S.HullMesh, P.bBurnt ? TEXT("char") : TEXT("dead"));
				P.SetIdx = S.HullMesh.IsEmpty() ? INDEX_NONE : SetFor(Name);
				if (P.SetIdx == INDEX_NONE)
				{
					P.SetIdx = -2;                                      // (not drawn: its mesh is not there; asked once)
				}
			}
			if (P.SetIdx < 0)
			{
				continue;
			}
			const int32 HKey = S.Id * 4 + (P.Section < 3 ? P.Section : 3);
			if (!Due(FMath::Sqrt(D2) * 0.001) && KeepHull(P.SetIdx, HKey))
			{
				++WreckHullsNow;
				continue;
			}
			const FQuat Q = Sky.ToSystem(FWrecks::AttAt(P, Now));
			const FVector Origin = Pivot - Q.RotateVector(P.PivotLocal);
			StageHull(P.SetIdx, HKey, FTransform(Q, Origin * 100.0, FVector::OneVector));
			++WreckHullsNow;
		}
		// ---- the field: looked into when the Aquila is within its reach
		if (S.Field.Count > 0)
		{
			const FVector Mid = Sky.ToSystem(S.Field.Pos0 + S.Field.Vel * (Now - S.Field.T0));
			const double Edge = FVector::Dist(Mid, F.Origin) - (double)FWrecks::FieldRadiusAt(S.Field, Now) - (double)S.Field.R0;
			if (Edge < WkChunkFieldKm * WkKm)
			{
				Fields.Add({&S, Edge});
			}
		}
		// ---- the lifepods: a hull up close, and the beacon as far as the sky is clear
		for (int32 qi = 0; qi < S.Pods.Num(); ++qi)
		{
			FPodRec& P = S.Pods[qi];
			if (P.State == 1 || Now < P.T0)
			{
				continue;                                               // (taken aboard, or not yet clear of the wreck)
			}
			const FVector Pos = Sky.ToSystem(FWrecks::PosAt(P, Now));
			const double D2 = FVector::DistSquared(Pos, F.Origin);
			const double Km = FMath::Sqrt(D2) * 0.001;
			if (Km > WkPodLampKm)
			{
				continue;
			}
			if (Km < WkPodHullKm)
			{
				if (P.SetIdx == -1)
				{
					P.SetIdx = SetFor(PodKeys[Fac]);
					if (P.SetIdx == INDEX_NONE)
					{
						P.SetIdx = -2;
					}
				}
				if (P.SetIdx >= 0)
				{
					const int32 HKey = S.Id * 16 + qi;
					if (Due(Km) || !KeepHull(P.SetIdx, HKey))
					{
						StageHull(P.SetIdx, HKey, FTransform(Sky.ToSystem(FWrecks::AttAt(P, Now)), Pos * 100.0, FVector::OneVector));
					}
					++PodsNow;
				}
			}
			if (FWrecks::BeaconOn(P, Now))
			{
				const AstraSpace::FMeshData* MD = D.Mesh(PodMeshes[Fac]);
				if (MD && MD->Lamps.Num())
				{
					DrawLamps(MD->Lamps, Pos, Sky.ToSystem(FWrecks::AttAt(P, Now)), SpMix(SH + (uint32)qi * 40503u), D2, SpLampFade(Km), true);
				}
				else
				{
					// no table for the pod's mesh yet: a beacon on its own (white, a slow blink)
					static const TArray<AstraSpace::FLamp> Generic = []()
					{
						AstraSpace::FLamp L;
						L.P = FVector(0.2, 0.0, 3.0);
						L.C = FLinearColor(1.f, 1.f, 1.f);
						L.SizeM = 1.4f;
						L.Glow = 300.f;
						L.Pattern = 5;
						return TArray<AstraSpace::FLamp>({L});
					}();
					DrawLamps(Generic, Pos, FQuat::Identity, SpMix(SH + (uint32)qi * 40503u), D2, SpLampFade(Km), true);
				}
			}
		}
	}
	// ---- the chunks of the fields near enough to see
	Fields.Sort([](const FNearField& A, const FNearField& B) { return A.Edge < B.Edge; });
	for (const FNearField& NF : Fields)
	{
		if (ChunksNow >= ChunkCap)
		{
			break;
		}
		FSite& S = *NF.Site;
		FWrecks::MakeDefs(S);
		const bool bChar = S.How == AstraSpace::EHowLost::Reactor;
		const int32 Fac = FMath::Clamp((int32)S.Faction, 0, 2);
		for (int32 i = 0; i < S.Field.Count && ChunksNow < ChunkCap; ++i)
		{
			AstraSpace::FChunk C;
			if (!FWrecks::ChunkAt(S, i, Now, C, false))
			{
				break;
			}
			const FVector Pos = Sky.ToSystem(C.Pos);
			const double D2 = FVector::DistSquared(Pos, F.Origin);
			const double LimitKm = FMath::Clamp(0.9 * (double)(C.Size * WkChunkMeshM[C.Shape]), 3.0, 22.0);        // each chunk goes out of the picture where it would be a speck
			if (D2 > FMath::Square(LimitKm * WkKm))
			{
				continue;
			}
			int32& SI = S.Field.SetIdx[C.Shape];
			if (SI == -1)
			{
				SI = SetFor(FString::Printf(TEXT("SM_DEBRIS_%c_%s#%s"), WkFactionLetter((uint8)Fac), WkChunkNames[C.Shape], bChar ? TEXT("char") : TEXT("dead")));
				if (SI == INDEX_NONE)
				{
					SI = -2;
				}
			}
			if (SI >= 0)
			{
				const int32 HKey = S.Id * 256 + i;
				if (Due(FMath::Sqrt(D2) * 0.001) || !KeepHull(SI, HKey))
				{
					StageHull(SI, HKey, FTransform(Sky.ToSystem(FWrecks::ChunkAttitude(S, i, Now)), Pos * 100.0, FVector((double)C.Size)));
				}
				++ChunksNow;
			}
			// a hot one still glows: a point of ember on it (the glints' layer, written afresh each frame in the Aquila's frame), as long as it is anywhere near
			if (C.Ember > 0.06f)
			{
				FTransform* X;
				if (float* Dd = Glints.Next(X))
				{
					const float Rm = FMath::Max(2.f, C.Size * WkChunkMeshM[C.Shape] * 0.25f) * AstraFx::GlowK;
					*X = FTransform(FQuat::Identity, F.ToWorld(Pos), FVector(Rm * 2.f));
					AstraFx::Fill(Dd, FLinearColor(1.f, 0.46f, 0.15f), 170.f * C.Ember * LampGain, 0.f, 0.f, 0.f, (float)(i & 255) / 255.f, Rm * 2.f, 0.f);
					++EmbersNow;
				}
			}
		}
	}
	WreckHullsPeak = FMath::Max(WreckHullsPeak, WreckHullsNow);
	ChunksPeak = FMath::Max(ChunksPeak, ChunksNow);
}

// ------------------------------------------------------------------------------------------------------------------ the campaign
TSharedRef<FJsonObject> UAstraSpaceLife::SaveJson()
{
	return Wrecks.ToJson(WreckClock());
}

void UAstraSpaceLife::LoadSaved(const TSharedPtr<FJsonObject>& J)
{
	double SavedClock = 0.0;
	if (Wrecks.FromJson(J, SavedClock))
	{
		ClockBase = SavedClock - (Owner ? (double)Owner->GetBattleTime() : 0.0);
		Wrecks.Settle(WreckClock());
		UE_LOG(LogASTRA, Log, TEXT("[Space] the campaign's wrecks are back: %d sites, clock %.0f s"), Wrecks.Sites().Num(), SavedClock);
	}
}

void UAstraSpaceLife::NewCampaign()
{
	RemoveWreckContacts();                       // (their records go with the war: no contact stays on the plot for a wreck that is not)
	Wrecks.Reset();
	ClockBase = 0.0;
}

void UAstraSpaceLife::AdvanceWrecks(double Seconds)
{
	ClockBase += FMath::Clamp(Seconds, 0.0, 30.0 * 86400.0);
	Wrecks.Settle(WreckClock());
}

// ------------------------------------------------------------------------------------------------------------------ the rescue hooks
bool UAstraSpaceLife::HasBeacons() const
{
	if (!bLaidOut || !Owner || Owner->Ships.Num() == 0)
	{
		return false;
	}
	TArray<AstraSpace::FBeacon> Bs;
	Wrecks.Beacons(SystemName, WreckClock(), Sky, Owner->Ships[0].Pos, FWrecks::BeaconKm, Bs);
	return Bs.Num() > 0;
}

bool UAstraSpaceLife::RescueGoal(int32 Rank, FVector& OutPos, FVector& OutVel, FString& OutOf, int32& OutSurvivors) const
{
	if (!bLaidOut || !Owner || Owner->Ships.Num() == 0)
	{
		return false;
	}
	TArray<AstraSpace::FBeacon> Bs;
	Wrecks.Beacons(SystemName, WreckClock(), Sky, Owner->Ships[0].Pos, FWrecks::BeaconKm, Bs);
	if (Bs.Num() == 0)
	{
		return false;
	}
	const AstraSpace::FBeacon& B = Bs[FMath::Abs(Rank) % Bs.Num()];
	OutPos = B.Pos;
	OutVel = B.Vel;
	OutOf = B.Of;
	OutSurvivors = B.Survivors;
	return true;
}

AstraSpace::FRescued UAstraSpaceLife::RescueTake(const FVector& At, double RadiusM, const FString& By)
{
	AstraSpace::FRescued R;
	if (!bLaidOut || !Owner)
	{
		return R;
	}
	R = Wrecks.Recover(SystemName, WreckClock(), Sky, At, RadiusM, By);
	if (R.Pods > 0)
	{
		AstraSpace::FEvent E;
		E.Kind = AstraSpace::EEventKind::Rescue;
		E.bReport = true;
		E.At = At;
		E.Text = FString::Printf(TEXT("flight: search and rescue — %s took %d %s lifepod%s of %s aboard: %d survivor%s%s"), *By, R.Pods, R.Faction == 0 ? TEXT("ASTRA") : (R.Faction == 1 ? TEXT("Mandate") : TEXT("civilian")),
		                         R.Pods == 1 ? TEXT("") : TEXT("s"), *R.Of, R.Survivors, R.Survivors == 1 ? TEXT("") : TEXT("s"),
		                         R.Faction == 1 ? TEXT(" (Mandate crew)") : TEXT(""));
		Events.Add(E);
		WreckThinkT = 0.f;
	}
	return R;
}

// ------------------------------------------------------------------------------------------------------------------ what the crew knows of them, and the numbers
TSharedRef<FJsonObject> UAstraSpaceLife::WreckSummaryJson() const
{
	TSharedRef<FJsonObject> W = MakeShared<FJsonObject>();
	if (!Owner || Owner->Ships.Num() == 0)
	{
		return W;
	}
	const FVector Me = Owner->Ships[0].Pos;
	const double Now = WreckClock();
	const FString& Key = SystemKey;
	// the wrecks within reach of her eyes and sensors, the nearest piece of each, nearest first
	struct FNearWreck { const FSite* Site; int32 Piece; double Km; FVector At; };
	TArray<FNearWreck> Near;
	int32 Here = 0;
	for (const FSite& S : Wrecks.Sites())
	{
		if (S.System != Key)
		{
			continue;
		}
		++Here;
		FNearWreck Best{&S, INDEX_NONE, 1e18, FVector::ZeroVector};
		for (int32 pi = 0; pi < S.Pieces.Num(); ++pi)
		{
			const FVector At = Sky.ToSystem(FWrecks::PosAt(S.Pieces[pi], Now));
			const double Km = FVector::Dist(At, Me) / WkKm;
			if (Km < Best.Km)
			{
				Best = {&S, pi, Km, At};
			}
		}
		if (Best.Piece != INDEX_NONE && Best.Km < 60.0)
		{
			Near.Add(Best);
		}
	}
	W->SetNumberField(TEXT("here"), Here);
	Near.Sort([](const FNearWreck& A, const FNearWreck& B) { return A.Km < B.Km; });
	TArray<TSharedPtr<FJsonValue>> Nw;
	for (int32 i = 0; i < FMath::Min(3, Near.Num()); ++i)
	{
		const FSite& S = *Near[i].Site;
		TSharedRef<FJsonObject> J = MakeShared<FJsonObject>();
		J->SetStringField(TEXT("of"), S.KnownAs);
		J->SetStringField(TEXT("piece"), FWrecks::PieceName(S, Near[i].Piece));
		if (const FAstraBattleShip* Cn = S.Pieces[Near[i].Piece].PlotId >= 0 ? Owner->FindById(S.Pieces[Near[i].Piece].PlotId) : nullptr)
		{
			J->SetStringField(TEXT("contact"), Cn->ContactId);          // (on the plot: the crew can name it, target it, put it on the screen, send a flight to look)
		}
		J->SetStringField(TEXT("how"), AstraSpace::HowLostName(S.How));
		J->SetNumberField(TEXT("lost_min_ago"), FMath::RoundToDouble((Now - S.DiedAt) / 6.0) / 10.0);
		J->SetNumberField(TEXT("bearing_deg"), FMath::RoundToDouble(Owner->BearingTo(Near[i].At)));
		J->SetNumberField(TEXT("mark_deg"), FMath::RoundToDouble(Owner->MarkTo(Near[i].At)));
		J->SetNumberField(TEXT("range_km"), FMath::RoundToDouble(Near[i].Km * 10.0) / 10.0);
		Nw.Add(MakeShared<FJsonValueObject>(J));
	}
	if (Nw.Num())
	{
		W->SetArrayField(TEXT("nearest"), Nw);
	}
	TArray<AstraSpace::FBeacon> Bs;
	Wrecks.Beacons(SystemName, Now, Sky, Me, FWrecks::BeaconKm, Bs);
	if (Bs.Num())
	{
		int32 People = 0;
		for (const AstraSpace::FBeacon& B : Bs)
		{
			People += B.Survivors;
		}
		TSharedRef<FJsonObject> P = MakeShared<FJsonObject>();
		P->SetNumberField(TEXT("beacons"), Bs.Num());
		P->SetNumberField(TEXT("survivors"), People);
		TSharedRef<FJsonObject> N = MakeShared<FJsonObject>();
		N->SetStringField(TEXT("of"), Bs[0].Of);
		N->SetStringField(TEXT("side"), Bs[0].Faction == 0 ? TEXT("ASTRA") : (Bs[0].Faction == 1 ? TEXT("Mandate") : TEXT("civilian")));
		N->SetNumberField(TEXT("survivors"), Bs[0].Survivors);
		N->SetNumberField(TEXT("bearing_deg"), FMath::RoundToDouble(Owner->BearingTo(Bs[0].Pos)));
		N->SetNumberField(TEXT("mark_deg"), FMath::RoundToDouble(Owner->MarkTo(Bs[0].Pos)));
		N->SetNumberField(TEXT("range_km"), FMath::RoundToDouble(FVector::Dist(Bs[0].Pos, Me) / 100.0) / 10.0);
		N->SetNumberField(TEXT("air_min"), FMath::RoundToDouble(Bs[0].AirLeftS / 60.0));
		P->SetObjectField(TEXT("nearest"), N);
		W->SetObjectField(TEXT("lifepods"), P);
	}
	return W;
}

FString UAstraSpaceLife::WreckStat() const
{
	const AstraSpace::FWreckStats St = Wrecks.Stats(SystemName, WreckClock());
	return FString::Printf(TEXT("wrecks: %d sites (%d here), %d pieces, %d chunks, lifepods %d (%d adrift with %d survivors, %d recovered, %d lost), %d lost ships told %d times | drawn: pieces %d now / %d peak, chunks %d now / %d peak, "
	                            "lifepods %d, embers %d | %.4f ms a tick"),
	                       St.Sites, St.SitesHere, St.Pieces, St.Chunks, St.Pods, St.PodsAdrift, St.Survivors, St.PodsRecovered, St.PodsLost, St.Losses, St.Told, WreckHullsNow, WreckHullsPeak, ChunksNow, ChunksPeak,
	                       PodsNow, EmbersNow, TickCount ? WrecksMs / TickCount : 0.0);
}

bool UAstraSpaceLife::DebugResume(FString& OutDetail)
{
	if (!Owner || Owner->Ships.Num() == 0 || !bLaidOut)
	{
		OutDetail = TEXT("no system laid out to resume from");
		return false;
	}
	// the wrecks of every system as they are, in the Gate's frame: what must be where it was after the resume
	ResumeProbe.Reset();
	ResumeClock = WreckClock();
	for (const FSite& S : Wrecks.Sites())
	{
		for (int32 pi = 0; pi < S.Pieces.Num() && pi < 50; ++pi)
		{
			ResumeProbe.Add({S.Id * 100 + pi, FWrecks::PosAt(S.Pieces[pi], ResumeClock)});
		}
		for (int32 qi = 0; qi < S.Pods.Num() && qi < 49; ++qi)
		{
			ResumeProbe.Add({S.Id * 100 + 50 + qi, FWrecks::PosAt(S.Pods[qi], ResumeClock)});
		}
	}
	// the save as the campaign writes it (text), and a resume from it as the campaign does it
	FString Text;
	const TSharedRef<TJsonWriter<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>> Wr = TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&Text);
	FJsonSerializer::Serialize(Owner->SaveJson(), Wr);
	TSharedPtr<FJsonObject> Back;
	if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Back) || !Back.IsValid())
	{
		ResumeProbe.Reset();
		OutDetail = TEXT("the save did not read back");
		return false;
	}
	bResumeProbe = true;
	Owner->ResumeFrom(Back);
	OutDetail = FString::Printf(TEXT("resumed from a save of %.1f KB: the plot is cleared, the system is laid out again in a frame or two"), Text.Len() / 1024.0);
	return true;
}

bool UAstraSpaceLife::DebugDump(const FString& Path, int32 SiteId, double AfterS, FString& OutDetail)
{
	const FSite* Found = nullptr;
	for (const FSite& S : Wrecks.Sites())
	{
		if (S.System == SystemKey && ((SiteId > 0 && S.Id == SiteId) || (SiteId <= 0 && S.Pieces.Num() >= 1)))
		{
			Found = &S;
			break;
		}
	}
	if (!Found)
	{
		OutDetail = TEXT("no such wreck site here (astra.space.wrecks.list)");
		return false;
	}
	FSite S = *Found;                                  // (a copy: its chunks' definitions are made on it)
	const double T = S.DiedAt + AfterS;
	FWrecks::MakeDefs(S);
	const FVector Mid = Wrecks.Middle(S, T);
	const auto Vec = [](const FVector& V) { return TArray<TSharedPtr<FJsonValue>>({MakeShared<FJsonValueNumber>(V.X), MakeShared<FJsonValueNumber>(V.Y), MakeShared<FJsonValueNumber>(V.Z)}); };
	const auto Quat = [](const FQuat& Q) { return TArray<TSharedPtr<FJsonValue>>({MakeShared<FJsonValueNumber>(Q.X), MakeShared<FJsonValueNumber>(Q.Y), MakeShared<FJsonValueNumber>(Q.Z), MakeShared<FJsonValueNumber>(Q.W)}); };
	TSharedRef<FJsonObject> Root = MakeShared<FJsonObject>();
	{
		TSharedRef<FJsonObject> J = MakeShared<FJsonObject>();
		J->SetNumberField(TEXT("id"), S.Id);
		J->SetStringField(TEXT("name"), S.Name);
		J->SetStringField(TEXT("class"), S.Class);
		J->SetStringField(TEXT("key"), S.ClassKey.ToString());
		J->SetStringField(TEXT("hull_mesh"), S.HullMesh);
		J->SetNumberField(TEXT("faction"), S.Faction);
		J->SetStringField(TEXT("how"), AstraSpace::HowLostName(S.How));
		J->SetNumberField(TEXT("section"), S.Section);
		J->SetNumberField(TEXT("age_s"), AfterS);
		J->SetNumberField(TEXT("radius"), S.Radius);
		J->SetStringField(TEXT("text"), Wrecks.Describe(S, -1, T));
		Root->SetObjectField(TEXT("site"), J);
	}
	TArray<TSharedPtr<FJsonValue>> Pcs, Chs, Pds;
	for (const FPieceRec& P : S.Pieces)
	{
		TSharedRef<FJsonObject> J = MakeShared<FJsonObject>();
		const FQuat Q = FWrecks::AttAt(P, T);
		const FVector Pivot = FWrecks::PosAt(P, T);
		J->SetNumberField(TEXT("section"), P.Section);
		J->SetArrayField(TEXT("pivot"), Vec(Pivot - Mid));
		J->SetArrayField(TEXT("pivot_local"), Vec(P.PivotLocal));
		J->SetArrayField(TEXT("origin"), Vec(Pivot - Q.RotateVector(P.PivotLocal) - Mid));
		J->SetArrayField(TEXT("quat"), Quat(Q));
		J->SetNumberField(TEXT("radius"), P.Radius);
		J->SetBoolField(TEXT("burnt"), P.bBurnt);
		Pcs.Add(MakeShared<FJsonValueObject>(J));
	}
	for (int32 i = 0; i < S.Field.Count; ++i)
	{
		AstraSpace::FChunk C;
		if (!FWrecks::ChunkAt(S, i, T, C))
		{
			continue;
		}
		TSharedRef<FJsonObject> J = MakeShared<FJsonObject>();
		J->SetArrayField(TEXT("pos"), Vec(C.Pos - Mid));
		J->SetArrayField(TEXT("quat"), Quat(C.Att));
		J->SetNumberField(TEXT("size"), C.Size);
		J->SetNumberField(TEXT("shape"), C.Shape);
		J->SetNumberField(TEXT("ember"), C.Ember);
		Chs.Add(MakeShared<FJsonValueObject>(J));
	}
	for (const FPodRec& P : S.Pods)
	{
		TSharedRef<FJsonObject> J = MakeShared<FJsonObject>();
		J->SetArrayField(TEXT("pos"), Vec(FWrecks::PosAt(P, T) - Mid));
		J->SetArrayField(TEXT("quat"), Quat(FWrecks::AttAt(P, T)));
		J->SetBoolField(TEXT("beacon"), FWrecks::BeaconOn(P, T));
		J->SetNumberField(TEXT("survivors"), P.Survivors);
		J->SetNumberField(TEXT("state"), P.State);
		Pds.Add(MakeShared<FJsonValueObject>(J));
	}
	Root->SetArrayField(TEXT("pieces"), Pcs);
	Root->SetArrayField(TEXT("chunks"), Chs);
	Root->SetArrayField(TEXT("pods"), Pds);
	Root->SetNumberField(TEXT("field_radius"), FWrecks::FieldRadiusAt(S.Field, T));
	FString Text;
	const TSharedRef<TJsonWriter<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>> Wr = TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&Text);
	FJsonSerializer::Serialize(Root, Wr);
	if (!FFileHelper::SaveStringToFile(Text, *Path, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM))
	{
		OutDetail = FString::Printf(TEXT("could not write %s"), *Path);
		return false;
	}
	OutDetail = FString::Printf(TEXT("%s (site %d) %.0f s after she went: %d pieces, %d chunks, %d lifepods -> %s"), *S.Name, S.Id, AfterS, Pcs.Num(), Chs.Num(), Pds.Num(), *Path);
	return true;
}

bool UAstraSpaceLife::DebugLose(const FString& Which, const FString& How, int32 Section, FString& OutDetail)
{
	if (!Owner || Owner->Ships.Num() == 0)
	{
		OutDetail = TEXT("no battle");
		return false;
	}
	FAstraBattleShip* S = nullptr;
	if (Which.Equals(TEXT("nearest"), ESearchCase::IgnoreCase))
	{
		double Best = 1e18;
		for (FAstraBattleShip& O : Owner->Ships)
		{
			if (O.bAlive && !O.bPlayer && !O.bCraft && !O.bFixture && !O.bGhost && !O.bDerelict && O.Dmg.bModel)
			{
				const double D = FVector::DistSquared(O.Pos, Owner->Ships[0].Pos);
				if (D < Best)
				{
					Best = D;
					S = &O;
				}
			}
		}
	}
	else
	{
		S = Owner->FindByContact(Which);
	}
	if (!S || !S->bAlive || S->bPlayer || S->bCraft || S->bFixture)
	{
		OutDetail = FString::Printf(TEXT("no warship '%s' to lose (astra.battle.status lists them)"), *Which);
		return false;
	}
	const EAstraFate Fate = How.StartsWith(TEXT("reactor"), ESearchCase::IgnoreCase) ? EAstraFate::ReactorBreach : (How.StartsWith(TEXT("destroy"), ESearchCase::IgnoreCase) ? EAstraFate::Destroyed : EAstraFate::Breakup);
	const FString Name = S->Name, Contact = S->ContactId;
	Owner->Destroy(*S, EAstraHitKind::Internal, Fate, (uint8)FMath::Clamp(Section, 0, 2));
	OutDetail = FString::Printf(TEXT("%s (%s) lost: %s"), *Name, *Contact, AstraSpace::HowLostName(Fate == EAstraFate::ReactorBreach ? AstraSpace::EHowLost::Reactor : (Fate == EAstraFate::Breakup ? AstraSpace::EHowLost::Breakup : AstraSpace::EHowLost::Destroyed)));
	return true;
}

FString UAstraSpaceLife::WreckContactsList() const
{
	if (!Owner)
	{
		return TEXT("no battle");
	}
	FString Out;
	int32 N = 0;
	const double Now = WreckClock();
	for (const FSite& Si : Wrecks.Sites())
	{
		if (Si.System != SystemKey)
		{
			continue;
		}
		for (int32 pi = 0; pi < Si.Pieces.Num(); ++pi)
		{
			const FAstraBattleShip* C = Si.Pieces[pi].PlotId >= 0 ? Owner->FindById(Si.Pieces[pi].PlotId) : nullptr;
			if (!C)
			{
				continue;
			}
			++N;
			Out += FString::Printf(TEXT("\n  %-8s %-34s bearing %03.0f mark %+.0f %6.1f km %5.0f m/s%s | %s"), *C->ContactId, *C->Name, Owner->BearingTo(C->Pos), Owner->MarkTo(C->Pos), FVector::Dist(Owner->PlayerPos(), C->Pos) / WkKm, C->Vel.Size(),
			                       ListedWrecks.Contains(C->Id) ? TEXT(" [listed]") : TEXT(""), *Wrecks.Status(Si, pi, Now));
		}
	}
	return FString::Printf(TEXT("%d wreck contacts on the plot (the nearest %d within %.0f km are in the crew's list)%s"), N, WkListed(), FWrecks::ListedKm, *Out);
}

bool UAstraSpaceLife::DebugWreckContacts(FString& OutDetail)
{
	if (!bLaidOut || !Owner || Owner->Ships.Num() == 0)
	{
		OutDetail = TEXT("no living space laid out here");
		return false;
	}
	int32 Checked = 0, Failed = 0;
	FString Lines;
	const auto Expect = [&](bool bOk, const FString& What)
	{
		++Checked;
		if (!bOk)
		{
			++Failed;
			if (Failed <= 6)
			{
				Lines += FString::Printf(TEXT("FAIL %s; "), *What);
			}
		}
	};
	const double Now = WreckClock();
	const FVector Me = Owner->Ships[0].Pos;
	const TArray<UAstraBattleSubsystem::FContactView>& Plot = Owner->Contacts();
	TArray<TSharedPtr<FJsonValue>> Listed = Owner->ContactsJson();
	int32 Near = 0, OnPlot = 0, Listable = 0, ListedIn = 0, Pieces = 0;
	double Worst = 0.0;
	for (const TSharedPtr<FJsonValue>& V : Listed)
	{
		const TSharedPtr<FJsonObject> O = V.IsValid() ? V->AsObject() : nullptr;
		FString Class;
		ListedIn += (O.IsValid() && O->TryGetStringField(TEXT("class"), Class) && Class == TEXT("wreck")) ? 1 : 0;
	}
	for (const FSite& S : Wrecks.Sites())
	{
		if (S.System != SystemKey)
		{
			continue;
		}
		for (int32 pi = 0; pi < S.Pieces.Num(); ++pi)
		{
			const FPieceRec& P = S.Pieces[pi];
			++Pieces;
			const double D = FVector::Dist(Sky.ToSystem(FWrecks::PosAt(P, Now)), Me);
			Near += D < (WkPlotKm() - 5.0) * WkKm ? 1 : 0;
			Listable += D < (FWrecks::ListedKm - 5.0) * WkKm ? 1 : 0;
			if (P.PlotId < 0)
			{
				continue;
			}
			++OnPlot;
			const FAstraBattleShip* C = Owner->FindById(P.PlotId);
			Expect(C && C->bWreck && C->bAlive && C->WreckSite == S.Id && C->WreckPiece == pi, FString::Printf(TEXT("site %d piece %d: the plot has no wreck contact for her"), S.Id, pi));
			if (!C)
			{
				continue;
			}
			Worst = FMath::Max(Worst, (double)FVector::Dist(C->Pos, Sky.ToSystem(FWrecks::PosAt(P, Now))));
			Expect(C->ContactId.StartsWith(FWrecks::PieceContactId(S, pi)) && C->Name == FWrecks::PieceName(S, pi), FString::Printf(TEXT("%s is not called what her record says (%s, %s)"), *C->ContactId, *FWrecks::PieceContactId(S, pi), *FWrecks::PieceName(S, pi)));
			Expect(Owner->FindByContact(C->ContactId) == C && Owner->ResolveShip(C->ContactId) == C->Id, FString::Printf(TEXT("the crew cannot name %s"), *C->ContactId));
			Expect(C->bFixture && C->bDerelict && !C->Dmg.bModel && C->Side == EAstraSide::Neutral && !C->bHostile, FString::Printf(TEXT("%s is not a plain derelict fixture"), *C->ContactId));
			const UAstraBattleSubsystem::FContactView* V = Plot.FindByPredicate([C](const UAstraBattleSubsystem::FContactView& X) { return X.Id == C->Id; });
			Expect(V && V->bWreck && V->bDerelict && V->Track >= 2 && !V->bCapital && !V->bCraft && V->Side == EAstraSide::Neutral && FMath::Abs(V->RangeKm - FVector::Dist(Me, C->Pos) / WkKm) < 0.05,
			       FString::Printf(TEXT("%s is not on the plot as a firm neutral wreck"), *C->ContactId));
			double Brg = 0.0, Mrk = 0.0, Rng = 0.0;
			Expect(Owner->ContactGeometry(C->ContactId, Brg, Mrk, Rng) && Rng > 0.0, FString::Printf(TEXT("the helm cannot lay a course to %s"), *C->ContactId));
		}
	}
	Expect(OnPlot >= FMath::Min(Near, WkPlotMax()) && OnPlot <= WkPlotMax(), FString::Printf(TEXT("%d pieces are within reach and %d are contacts (at most %d)"), Near, OnPlot, WkPlotMax()));
	int32 Entries = 0;
	for (const FAstraBattleShip& S : Owner->Ships)
	{
		Entries += S.bWreck ? 1 : 0;
	}
	Expect(Entries == OnPlot, FString::Printf(TEXT("the plot holds %d wreck contacts and the records say %d (an orphan, or a piece with no contact)"), Entries, OnPlot));
	Expect(Worst < 1.0, FString::Printf(TEXT("a contact is %.1f m from where her record has her"), Worst));
	Expect(ListedIn <= WkListed() && (Listable == 0 || WkListed() == 0 || ListedIn >= 1), FString::Printf(TEXT("the crew's list holds %d wrecks (%d pieces within %.0f km)"), ListedIn, Listable, FWrecks::ListedKm - 5.0));
	// scanning: the nearest contact answers, with its number, and a second look from the same range has nothing new
	if (OnPlot > 0)
	{
		const FAstraBattleShip* Nearest = nullptr;
		double Best = 1.0e18;
		for (const FAstraBattleShip& S : Owner->Ships)
		{
			if (S.bWreck && S.bAlive && FVector::DistSquared(S.Pos, Me) < Best)
			{
				Best = FVector::DistSquared(S.Pos, Me);
				Nearest = &S;
			}
		}
		FString Detail, Again;
		if (Nearest)
		{
			const FString Id = Nearest->ContactId;
			Expect(Owner->PlayerScan(Id, Detail) && Detail.Contains(TEXT("scan of")) && Detail.Contains(Id), FString::Printf(TEXT("the scan of %s says: %s"), *Id, *Detail));
			Expect(Owner->PlayerScan(Id, Again) && Again.Contains(TEXT("nothing new")), FString::Printf(TEXT("a second scan of %s from the same range says: %s"), *Id, *Again));
		}
	}
	OutDetail = FString::Printf(TEXT("%d checks: %d pieces here, %d within reach, %d on the plot (peak %d), %d in the crew's list, the farthest contact %.2f m from her record%s"), Checked, Pieces, Near, OnPlot, WreckContactsPeak, ListedIn, Worst,
	                            Failed ? *(FString(TEXT("; ")) + Lines) : TEXT(""));
	return Failed == 0 && Checked > 0;
}

// ------------------------------------------------------------------------------------------------------------------ the console
namespace
{
	UAstraSpaceLife* WkSpaceOf(UWorld* World)
	{
		UAstraBattleSubsystem* B = World ? World->GetSubsystem<UAstraBattleSubsystem>() : nullptr;
		return B ? B->GetSpace() : nullptr;
	}

	FAutoConsoleCommandWithWorldAndArgs CmdSpaceLose(TEXT("astra.space.lose"), TEXT("Lose a warship the way the war would, to see what is left: astra.space.lose <contact id | nearest> [breakup|reactor|destroyed] [section 0 bow|1 mid|2 stern]"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& A, UWorld* W)
		{
			UAstraSpaceLife* S = WkSpaceOf(W);
			if (!S || A.Num() < 1) { UE_LOG(LogASTRA, Display, TEXT("[Space] astra.space.lose <contact id | nearest> [breakup|reactor|destroyed] [section]")); return; }
			FString Detail;
			S->DebugLose(A[0], A.Num() > 1 ? A[1] : FString(TEXT("breakup")), A.Num() > 2 ? FCString::Atoi(*A[2]) : 1, Detail);
			UE_LOG(LogASTRA, Display, TEXT("[Space] %s"), *Detail);
		}));

	FAutoConsoleCommandWithWorld CmdSpaceWrecks(TEXT("astra.space.wrecks.list"), TEXT("What the war has left in this system: each loss, her pieces, her lifepods, what was left aboard"),
		FConsoleCommandWithWorldDelegate::CreateLambda([](UWorld* W)
		{
			UAstraSpaceLife* S = WkSpaceOf(W);
			if (!S) { UE_LOG(LogASTRA, Display, TEXT("[Space] none in this world")); return; }
			const double Now = S->WreckClock();
			UE_LOG(LogASTRA, Display, TEXT("[Space] %s"), *S->WreckStat());
			for (const FSite& Si : S->GetWrecks().Sites())
			{
				if (Si.System != S->GetSystem().ToLower()) { continue; }
				UE_LOG(LogASTRA, Display, TEXT("[Space]  #%d %s"), Si.Id, *S->GetWrecks().Describe(Si, -1, Now));
				UE_LOG(LogASTRA, Display, TEXT("[Space]     aboard: %d carried, %d alive when she went, %d killed before, %d lost with her, %d got away (%s); %d rooms not as built; class %s, ship id %d"),
				       Si.Aboard.Complement, Si.Aboard.Alive, Si.Aboard.Killed, Si.Aboard.Lost, Si.Aboard.Escaped, Si.Aboard.bInside ? TEXT("her inside's count") : TEXT("the class's estimate"), Si.Aboard.Rooms.Num(),
				       *Si.ClassKey.ToString(), Si.ShipId);
				for (int32 i = 0; i < Si.Pods.Num(); ++i)
				{
					const FPodRec& P = Si.Pods[i];
					UE_LOG(LogASTRA, Display, TEXT("[Space]     lifepod %d: %d survivors, %s, air %s"), i, P.Survivors, P.State == 1 ? TEXT("recovered") : (P.State == 2 || Now >= P.T0 + P.AirS ? TEXT("silent") : FWrecks::BeaconOn(P, Now) ? TEXT("calling") : TEXT("adrift")),
					       *FString::Printf(TEXT("%.0f min left"), FWrecks::AirLeft(P, Now) / 60.0));
				}
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdSpaceRescue(TEXT("astra.space.rescue"), TEXT("Take aboard the lifepods near the Aquila (a rescue by hand, for testing): astra.space.rescue [km, default 5]"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& A, UWorld* W)
		{
			UAstraBattleSubsystem* B = W ? W->GetSubsystem<UAstraBattleSubsystem>() : nullptr;
			UAstraSpaceLife* S = B ? B->GetSpace() : nullptr;
			if (!S) { return; }
			const AstraSpace::FRescued R = S->RescueTake(B->PlayerPos(), (A.Num() ? FCString::Atod(*A[0]) : 5.0) * WkKm, TEXT("the Aquila's own boats"));
			UE_LOG(LogASTRA, Display, TEXT("[Space] rescue: %d lifepods, %d survivors%s"), R.Pods, R.Survivors, R.Pods ? *FString::Printf(TEXT(" (of %s)"), *R.Of) : TEXT(""));
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdSpaceWrecksSave(TEXT("astra.space.wrecks.roundtrip"), TEXT("Write the wrecks as the campaign's save does, read them back into a copy and compare: size, time, sites"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& A, UWorld* W)
		{
			UAstraSpaceLife* S = WkSpaceOf(W);
			if (!S) { return; }
			const double T0 = FPlatformTime::Seconds();
			const TSharedRef<FJsonObject> J = S->SaveJson();
			const double Tj = FPlatformTime::Seconds();
			FString Text;
			const TSharedRef<TJsonWriter<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>> Wr = TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&Text);
			FJsonSerializer::Serialize(J, Wr);
			const double T1 = FPlatformTime::Seconds();
			TSharedPtr<FJsonObject> Back;
			FWrecks Copy;
			double Clock = 0.0;
			const bool bOk = FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Back) && Copy.FromJson(Back, Clock);
			const double T2 = FPlatformTime::Seconds();
			bool bSame = bOk && Copy.Sites().Num() == S->GetWrecks().Sites().Num();
			for (int32 i = 0; bSame && i < Copy.Sites().Num(); ++i)
			{
				const FSite& X = Copy.Sites()[i];
				const FSite& Y = S->GetWrecks().Sites()[i];
				bSame = X.Id == Y.Id && X.Pieces.Num() == Y.Pieces.Num() && X.Pods.Num() == Y.Pods.Num() && X.Field.Count == Y.Field.Count && X.Name == Y.Name && FMath::Abs(X.DiedAt - Y.DiedAt) < 0.2
				        && FVector::Dist(X.Pos0, Y.Pos0) < 0.2 && X.ShipId == Y.ShipId && X.ClassKey == Y.ClassKey && X.Aboard.Escaped == Y.Aboard.Escaped;
			}
			UE_LOG(LogASTRA, Display, TEXT("[Space] wrecks round trip: %s, %d sites, %.1f KB; the objects %.2f ms (the sites that have not changed are kept), the text %.2f ms, read back %.2f ms"), bSame ? TEXT("SAME") : TEXT("DIFFERENT"),
			       S->GetWrecks().Sites().Num(), Text.Len() / 1024.0, (Tj - T0) * 1000.0, (T1 - Tj) * 1000.0, (T2 - T1) * 1000.0);
		}));

	FAutoConsoleCommandWithWorld CmdSpaceWrecksResume(TEXT("astra.space.wrecks.resume"), TEXT("TESTING, destructive: resume the battle from its own save as the campaign does (the plot is cleared, a new Gate); the log then says whether every wreck is where it was"),
		FConsoleCommandWithWorldDelegate::CreateLambda([](UWorld* W)
		{
			UAstraSpaceLife* S = WkSpaceOf(W);
			if (!S) { return; }
			FString Detail;
			S->DebugResume(Detail);
			UE_LOG(LogASTRA, Display, TEXT("[Space] %s"), *Detail);
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdSpaceWrecksDump(TEXT("astra.space.wrecks.dump"), TEXT("Write a wreck site as the records place it, for the preview renders: astra.space.wrecks.dump <path.json> [site id, 0 = the first] [seconds after she went, default 180]"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& A, UWorld* W)
		{
			UAstraSpaceLife* S = WkSpaceOf(W);
			if (!S || A.Num() < 1) { UE_LOG(LogASTRA, Display, TEXT("[Space] astra.space.wrecks.dump <path.json> [site id] [seconds]")); return; }
			FString Detail;
			S->DebugDump(A[0], A.Num() > 1 ? FCString::Atoi(*A[1]) : 0, A.Num() > 2 ? FCString::Atod(*A[2]) : 180.0, Detail);
			UE_LOG(LogASTRA, Display, TEXT("[Space] %s"), *Detail);
		}));

	FAutoConsoleCommandWithWorld CmdSpaceWreckContacts(TEXT("astra.space.wrecks.contacts"), TEXT("The pieces of the wrecks that are contacts of the plot now: number, name, where, what has been looked into, and which of them the crew's own list holds"),
		FConsoleCommandWithWorldDelegate::CreateLambda([](UWorld* W)
		{
			UAstraSpaceLife* S = WkSpaceOf(W);
			if (!S) { UE_LOG(LogASTRA, Display, TEXT("[Space] none in this world")); return; }
			UE_LOG(LogASTRA, Display, TEXT("[Space] %s"), *S->WreckContactsList());
		}));

	FAutoConsoleCommandWithWorld CmdSpaceWreckContactsTest(TEXT("astra.space.wrecks.contacts.test"), TEXT("The wreck contacts in this world: each piece near is on the plot where its record puts it, named, targetable, scannable, listed by the nearest few"),
		FConsoleCommandWithWorldDelegate::CreateLambda([](UWorld* W)
		{
			UAstraSpaceLife* S = WkSpaceOf(W);
			if (!S) { UE_LOG(LogASTRA, Display, TEXT("[Space] none in this world")); return; }
			FString Detail;
			const bool bOk = S->DebugWreckContacts(Detail);
			UE_LOG(LogASTRA, Display, TEXT("[Space] wreck contacts: %s %s"), *Detail, bOk ? TEXT("WRECK_CONTACTS_OK") : TEXT("WRECK_CONTACTS_FAILED"));
		}));

	FAutoConsoleCommandWithWorld CmdSpaceWrecksReset(TEXT("astra.space.wrecks.reset"), TEXT("Forget every wreck of every system (a new war)"),
		FConsoleCommandWithWorldDelegate::CreateLambda([](UWorld* W) { if (UAstraSpaceLife* S = WkSpaceOf(W)) { S->NewCampaign(); UE_LOG(LogASTRA, Display, TEXT("[Space] the wrecks are forgotten")); } }));
}
