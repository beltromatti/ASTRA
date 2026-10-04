// ASTRA — the traffic's own life, in the game (SPAZIO-VIVO-2, docs/SPAZIO.md §14): what is worth a look to the vessels that pass (the wrecks the war leaves, the hulks nobody has in tow), the patrols the war may pull into the
// plot, and the bench's checks of all of it (convoys that come out of the Gate and keep a column under escort, a vessel that slows to look, a tug sent to a hulk, a patrol taken by the war and given back).
// The rules are the traffic's (AstraSpaceLifeTraffic.*: plain C++, deterministic); this is the glue to the world and the console.

#include "AstraSpaceLife.h"
#include "AstraBattleSubsystem.h"
#include "ASTRA.h"
#include "Engine/World.h"
#include "HAL/IConsoleManager.h"

using AstraSpace::FWrecks;

namespace
{
	constexpr double LfKm = 1000.0;
}

// ------------------------------------------------------------------------------------------------------------------ what is worth a look
void UAstraSpaceLife::ReadInterests()
{
	if ((InterestT -= Dt) > 0.f)
	{
		return;
	}
	InterestT = 0.5f;
	View.Interests.Reset();
	if (!Owner || !bLaidOut)
	{
		return;
	}
	const double Now = WreckClock();
	// the wrecks of the war: where a ship was lost not long ago, with the lifepods that got away (a wreck of long ago is no news: the traffic decides by her age)
	for (const AstraSpace::FSite& Si : Wrecks.Sites())
	{
		if (Si.System != SystemKey || Si.Pieces.Num() == 0)
		{
			continue;
		}
		AstraSpace::FInterest I;
		I.Key = 1000000 + Si.Id;
		I.Kind = 0;
		const FVector Mid = Wrecks.Middle(Si, Now);
		I.Pos = Sky.ToSystem(Mid);
		I.Vel = Sky.DirToSystem(Si.Vel);
		double R = Si.Radius;
		for (const AstraSpace::FPieceRec& P : Si.Pieces)
		{
			R = FMath::Max(R, FVector::Dist(FWrecks::PosAt(P, Now), Mid) + (double)P.Radius);
		}
		I.RadiusM = (float)FMath::Clamp(R, 150.0, 2500.0);
		I.AgeS = (float)(Now - Si.DiedAt);
		for (const AstraSpace::FPodRec& P : Si.Pods)
		{
			I.Pods += FWrecks::Alive(P, Now) ? 1 : 0;
		}
		I.Name = FWrecks::BareName(Si.KnownAs.IsEmpty() ? Si.Name : Si.KnownAs);
		I.What = FString::Printf(TEXT("the wreck of %s (%s)"), *I.Name, Si.How == AstraSpace::EHowLost::Reactor ? TEXT("her reactor breached") : (Si.How == AstraSpace::EHowLost::Breakup ? TEXT("her hull broke apart") : TEXT("she was destroyed")));
		View.Interests.Add(I);
	}
	// the hulks nobody has in tow: a ship the war disabled, a dead station or freighter a beat put here
	for (const FAstraBattleShip& S : Owner->Ships)
	{
		if (!S.bAlive || S.bPlayer || S.bCraft || S.bFixture || S.bWreck || S.bGhost || !(S.bDisabled || S.bDerelict))
		{
			continue;
		}
		AstraSpace::FInterest I;
		I.Key = S.Id;
		I.Kind = 1;
		I.Pos = S.Pos;
		I.Vel = S.Vel;
		I.RadiusM = FMath::Max(S.Radius, 40.f);
		I.Name = S.bIdentified ? S.Name : S.ContactId;
		I.What = S.bIdentified ? FString::Printf(TEXT("the hulk of %s (%s)"), *S.Name, *S.ContactId) : FString::Printf(TEXT("the hulk %s"), *S.ContactId);
		View.Interests.Add(I);
	}
	View.Interests.Append(TestInterests);
}

// ------------------------------------------------------------------------------------------------------------------ patrols the war can take
void UAstraSpaceLife::PatrolsNear(const FVector& Pos, double RadiusM, TArray<FPatrolInfo>& Out) const
{
	for (const AstraSpace::FPatrol& P : Traffic.Patrols())
	{
		if (P.State == 2 || P.State == 3 || P.Craft.Num() == 0)
		{
			continue;
		}
		FVector Mid(0.0);
		for (const AstraSpace::FPatrolCraft& C : P.Craft)
		{
			Mid += C.Pos;
		}
		Mid /= (double)P.Craft.Num();
		const double D = FVector::Dist(Mid, Pos);
		if (D > RadiusM)
		{
			continue;
		}
		FPatrolInfo I;
		I.Id = P.Id;
		I.Where = P.NodeName;
		I.Mesh = P.Mesh;
		I.Craft = P.Craft.Num();
		I.Pos = Mid;
		I.RangeM = D;
		I.State = P.State;
		I.bEscort = P.Convoy != INDEX_NONE;
		Out.Add(I);
	}
	Out.Sort([](const FPatrolInfo& A, const FPatrolInfo& B) { return A.RangeM < B.RangeM; });
}

bool UAstraSpaceLife::PullPatrol(int32 PatrolId, TArray<AstraSpace::FPatrolCraft>& OutCraft, FString& OutMesh, FString& OutWhy)
{
	if (!bLaidOut)
	{
		OutWhy = TEXT("no system is laid out");
		return false;
	}
	float Scale = 1.f;
	if (!Traffic.TakePatrol(PatrolId, OutCraft, OutMesh, Scale, &OutWhy))
	{
		return false;
	}
	const AstraSpace::FPatrol& P = Traffic.Patrols()[Traffic.PatrolIndex(PatrolId)];
	AstraSpace::FEvent E;
	E.Kind = AstraSpace::EEventKind::Patrol;
	E.bReport = false;
	E.At = OutCraft.Num() ? OutCraft[0].Pos : FVector::ZeroVector;
	E.Text = FString::Printf(TEXT("comms: %s — %d craft of %s are released to the Aquila's command"), P.Convoy != INDEX_NONE ? *P.NodeName : *FString::Printf(TEXT("the %s patrol"), *P.NodeName),
	                         OutCraft.Num(), OutMesh.Contains(TEXT("Falcon")) ? TEXT("the Falcon patrol") : TEXT("the patrol"));
	Events.Add(E);
	return true;
}

void UAstraSpaceLife::ReturnPatrol(int32 PatrolId, int32 Survivors)
{
	const int32 I = Traffic.PatrolIndex(PatrolId);
	if (I == INDEX_NONE || Traffic.Patrols()[I].State != 3)
	{
		return;
	}
	const FString Where = Traffic.Patrols()[I].NodeName;
	const int32 Was = Traffic.Patrols()[I].Complement;
	Traffic.GivePatrolBack(PatrolId, Survivors);
	AstraSpace::FEvent E;
	E.Kind = AstraSpace::EEventKind::Patrol;
	E.bReport = false;
	E.Text = FString::Printf(TEXT("comms: %s is coming home from the Aquila's fight: %d of %d craft%s"), Traffic.Patrols()[I].Convoy != INDEX_NONE ? *Where : *FString::Printf(TEXT("the %s patrol"), *Where), Survivors, Was,
	                         Survivors == 0 ? TEXT(" (none): the yard will fly a new flight in twenty minutes") : (Survivors < Was ? TEXT("; the rest are made good in a quarter of an hour") : TEXT("")));
	Events.Add(E);
}

FString UAstraSpaceLife::ConvoyList() const
{
	FString Out = FString::Printf(TEXT("%d convoys"), Traffic.Convoys().Num());
	const double Now = Traffic.TimeNow();
	for (const AstraSpace::FConvoy& C : Traffic.Convoys())
	{
		const AstraSpace::FPatrol* Es = Traffic.Patrols().IsValidIndex(C.Patrol) ? &Traffic.Patrols()[C.Patrol] : nullptr;
		const FString EscortText = Es ? (Es->State == 0 ? FString::Printf(TEXT("escort: %d craft flying"), Es->Craft.Num()) : FString(TEXT("escort in port"))) : FString(TEXT("no escort"));
		Out += FString::Printf(TEXT("\n  %s: %d hulls bound for %s; next out of the Gate in %.0f s%s, %s%s"), *C.Name, C.Members.Num(), *C.Where, FMath::Max(0.0, C.NextAt - Now), C.FirstAwayAt >= 0.0 ? TEXT(" (the first is gone: waiting for the rest)") : TEXT(""),
		                       *EscortText, C.bToldOut ? TEXT(", announced") : TEXT(""));
		const AstraSpace::FVessel* Prev = nullptr;
		for (const int32 Id : C.Members)
		{
			for (const AstraSpace::FVessel& V : Traffic.Vessels())
			{
				if (V.Id != Id)
				{
					continue;
				}
				Out += FString::Printf(TEXT("\n    %d. %-18s %-9s %4.0f m/s%s%s"), V.ConvoyRank + 1, *V.Name, AstraSpace::StateName(V.State), V.Vel.Size(),
				                       Prev && V.State != AstraSpace::EVState::Away && Prev->State != AstraSpace::EVState::Away ? *FString::Printf(TEXT("  %.1f km behind %d."), FVector::Dist(V.Pos, Prev->Pos) / LfKm, V.ConvoyRank) : TEXT(""),
				                       V.State == AstraSpace::EVState::Away ? *FString::Printf(TEXT("  back in %.0f s"), FMath::Min(1.0e6, FMath::Max(0.0, V.ReturnAt - Now))) : TEXT(""));
				Prev = &V;
				break;
			}
		}
	}
	return Out;
}

// ------------------------------------------------------------------------------------------------------------------ the bench
bool UAstraSpaceLife::DebugLife(const FString& What, FString& OutDetail)
{
	if (!bLaidOut || !Owner || Owner->Ships.Num() == 0)
	{
		OutDetail = TEXT("no living space laid out here");
		return false;
	}
	int32 Failed = 0, Checked = 0;
	FString Lines;
	const auto Expect = [&](bool bOk, const FString& Said)
	{
		++Checked;
		if (!bOk)
		{
			++Failed;
			Lines += FString::Printf(TEXT("FAIL %s; "), *Said);
		}
	};
	const AstraSpace::FDataSet& D = AstraSpace::Data();
	TArray<AstraSpace::FEvent> Ev;
	// the traffic on its own for a while, seeing what the world has (a quiet world: no hostile, no engagement: this is its own life, not its reaction to a war)
	const auto Run = [this, &Ev](double Seconds)
	{
		InterestT = 0.f;
		ReadInterests();
		AstraSpace::FWorldView Quiet = View;
		Quiet.Hostiles.Reset();
		Quiet.bEngagement = false;
		Quiet.bGateBusy = false;
		Traffic.Warmup(Seconds, 0.2, &Quiet, &Ev);
	};
	const auto Said = [&Ev](const TCHAR* Needle)
	{
		int32 N = 0;
		for (const AstraSpace::FEvent& E : Ev)
		{
			N += E.Text.Contains(Needle) ? 1 : 0;
		}
		return N;
	};
	FString Done;
	if (What.Equals(TEXT("look"), ESearchCase::IgnoreCase))
	{
		// a wreck is put on the lane the most vessels use, and the vessels that pass slow to look at it, once, and say so
		int32 Lane = INDEX_NONE;
		for (int32 i = 0; i < Layout.Lanes.Num(); ++i)
		{
			if (Layout.Lanes[i].Id == FName(TEXT("keeper-arsenal")) || Lane == INDEX_NONE)
			{
				Lane = i;
			}
		}
		Expect(Lane != INDEX_NONE && Layout.Lanes[Lane].Pts.Num() >= 2, TEXT("no lane to put a wreck on"));
		if (Lane != INDEX_NONE && Layout.Lanes[Lane].Pts.Num() >= 2)
		{
			const FVector Mid = Layout.Lanes[Lane].Pts[Layout.Lanes[Lane].Pts.Num() / 2];
			AstraSpace::FInterest I;
			I.Key = 900001;
			I.Kind = 0;
			I.Pos = Mid;
			I.RadiusM = 400.f;
			I.AgeS = 300.f;
			I.Pods = 3;
			I.Name = TEXT("ASN Vigilant");
			I.What = TEXT("the wreck of ASN Vigilant (her hull broke apart)");
			TestInterests.Add(I);
			const int32 Before = Traffic.Stats().LooksTotal;
			double SlowestAbs = 1.0e9, SlowestRel = 1.0e9;
			int32 MostLooking = 0;
			for (int32 Chunk = 0; Chunk < 60; ++Chunk)                   // 30 minutes in half-minute steps: what the lane's vessels do as they pass
			{
				Run(30.0);
				int32 Now2 = 0;
				for (const AstraSpace::FVessel& V : Traffic.Vessels())
				{
					if (V.Look != INDEX_NONE)
					{
						++Now2;
						const AstraSpace::FHullDef* H = D.Hull(V.Hull);
						const double Dist = FVector::Dist(V.Pos, Mid);
						if (H && Dist < 2500.0)
						{
							SlowestRel = FMath::Min(SlowestRel, V.Vel.Size() / (double)H->Cruise);
							SlowestAbs = FMath::Min(SlowestAbs, V.Vel.Size());
						}
					}
				}
				MostLooking = FMath::Max(MostLooking, Now2);
			}
			const int32 Looks = Traffic.Stats().LooksTotal - Before;
			Expect(Looks >= 1, FString::Printf(TEXT("%d looks in half an hour with a wreck on the lane"), Looks));
			Expect(Said(TEXT("is slowing to look at the wreck of ASN Vigilant")) >= 1, TEXT("nobody said they were slowing to look"));
			Expect(Said(TEXT("lifepods adrift near it")) >= 1, TEXT("what the scanners show of the lifepods was not said"));
			Expect(Said(TEXT("is slowing to look at the wreck of ASN Vigilant")) <= FMath::Max(1, Looks), TEXT("more reports than looks"));
			Expect(SlowestRel < 0.55, FString::Printf(TEXT("the slowest look within 2.5 km was at %.2f of cruise (%.0f m/s)"), SlowestRel, SlowestAbs));
			Done = FString::Printf(TEXT("%d looks, the slowest at %.0f m/s (%.2f of cruise), %d reports"), Looks, SlowestAbs, SlowestRel, Said(TEXT("is slowing to look")));
			TestInterests.Reset();
		}
	}
	else if (What.Equals(TEXT("tug"), ESearchCase::IgnoreCase))
	{
		// a hulk is put near the yards: after a few minutes a yard tug casts off for it, comes on station off it, stays a while and goes home; no second tug is sent to the same hulk
		int32 Yards = INDEX_NONE;
		for (int32 n = 0; n < Layout.Nodes.Num(); ++n)
		{
			if (Layout.Nodes[n].Kind == AstraSpace::EPlaceKind::Arsenal)
			{
				Yards = n;
			}
		}
		Expect(Yards != INDEX_NONE, TEXT("this system has no yards to send a tug from"));
		if (Yards != INDEX_NONE)
		{
			const FVector At = Layout.Nodes[Yards].Pos + FVector(0.0, 9.0 * LfKm, 2.0 * LfKm);
			AstraSpace::FInterest I;
			I.Key = 900002;
			I.Kind = 1;
			I.Pos = At;
			I.RadiusM = 90.f;
			I.Name = TEXT("Brightwater Two");
			I.What = TEXT("the hulk of Brightwater Two (T-11)");
			TestInterests.Add(I);
			double Closest = 1.0e9;
			int32 PeakTending = 0;
			for (int32 Chunk = 0; Chunk < 100; ++Chunk)                  // 50 minutes in half-minute steps
			{
				Run(30.0);
				PeakTending = FMath::Max(PeakTending, Traffic.Stats().Tending);
				for (const AstraSpace::FVessel& V : Traffic.Vessels())
				{
					if (V.State == AstraSpace::EVState::Tending)
					{
						Closest = FMath::Min(Closest, (double)FVector::Dist(V.Pos, At));
					}
				}
			}
			const AstraSpace::FTrafficStats& St = Traffic.Stats();
			Expect(St.TugsSent == 1, FString::Printf(TEXT("%d tugs were sent to one hulk"), St.TugsSent));
			Expect(PeakTending >= 1 && Closest < 700.0, FString::Printf(TEXT("a tug came on station: %d at the most, nearest %.0f m"), PeakTending, Closest));
			Expect(St.TugsHome >= 1 && St.Tending == 0, FString::Printf(TEXT("the tug went home: %d home, %d still on station"), St.TugsHome, St.Tending));
			Expect(Said(TEXT("has cast off from")) == 1 && Said(TEXT("is on station")) == 1 && Said(TEXT("is leaving the hulk")) == 1, FString::Printf(TEXT("the tug's story was told %d, %d, %d times"), Said(TEXT("has cast off from")), Said(TEXT("is on station")), Said(TEXT("is leaving the hulk"))));
			Done = FString::Printf(TEXT("one tug sent, on station %.0f m off the hulk, home again"), Closest);
			TestInterests.Reset();
		}
	}
	else if (What.Equals(TEXT("convoys"), ESearchCase::IgnoreCase))
	{
		// convoys come out of the Gate (their first hull is announced), keep a column on the lane, are escorted while they are under way, and go on being so for hours
		Expect(Traffic.Convoys().Num() >= 1, TEXT("this system has no convoy"));
		float Widest = 0.f;
		int32 PeakEscorts = 0, PeakUnder = 0;
		for (int32 Chunk = 0; Chunk < 450; ++Chunk)                      // two hours and a half in twenty-second steps (a convoy's round is about an hour: out of the Gate, three calls, back out of it, beyond it for 15 to 25 minutes)
		{
			Run(20.0);
			if (Chunk % 45 == 0)
			{
				UE_LOG(LogASTRA, Display, TEXT("[Space] life convoys at %d min: %s"), Chunk / 3, *ConvoyList());
			}
			Widest = FMath::Max(Widest, Traffic.Stats().MaxColumnGapKm);
			PeakEscorts = FMath::Max(PeakEscorts, Traffic.Stats().EscortsFlying);
			int32 Under = 0;
			for (const AstraSpace::FVessel& V : Traffic.Vessels())
			{
				Under += (V.Convoy != INDEX_NONE && (V.State == AstraSpace::EVState::Cruise || V.State == AstraSpace::EVState::GateIn)) ? 1 : 0;
			}
			PeakUnder = FMath::Max(PeakUnder, Under);
		}
		const AstraSpace::FTrafficStats& St = Traffic.Stats();
		Expect(St.ConvoysCame >= 2, FString::Printf(TEXT("%d convoys came out of the Gate"), St.ConvoysCame));
		int32 Texts = 0, OfConvoys = 0;
		for (const AstraSpace::FEvent& E : Ev)
		{
			Texts += E.Text.IsEmpty() ? 0 : 1;
			OfConvoys += E.Kind == AstraSpace::EEventKind::Convoy ? 1 : 0;
		}
		Expect(Said(TEXT("is coming out of the Janus Gate")) >= 1, FString::Printf(TEXT("the convoys were announced %d times (%d came out, %d events, %d with words, %d of the convoys')"), Said(TEXT("is coming out of the Janus Gate")), St.ConvoysCame, Ev.Num(), Texts, OfConvoys));
		Expect(PeakUnder >= 3, FString::Printf(TEXT("at most %d convoy hulls were under way at once"), PeakUnder));
		Expect(PeakEscorts >= 2, FString::Printf(TEXT("%d escort craft flew at the most"), PeakEscorts));
		const float Closest = Traffic.Stats().MinColumnGapKm;
		Expect(Widest > 0.f && Widest < 4.5f, FString::Printf(TEXT("the longest gap in a column on the lane in from the Gate was %.1f km (the convoy keeps %.1f)"), Widest, Traffic.Convoys().Num() ? Traffic.Convoys()[0].GapM / 1000.f : 0.f));
		Expect(Closest > 0.3f && Closest < 2.5f, FString::Printf(TEXT("the closest two hulls of a column came was %.2f km"), Closest));
		bool bMembers = true;
		for (const AstraSpace::FConvoy& C : Traffic.Convoys())
		{
			for (int32 r = 0; r < C.Members.Num(); ++r)
			{
				bool bFound = false;
				for (const AstraSpace::FVessel& V : Traffic.Vessels())
				{
					bFound |= V.Id == C.Members[r] && V.Convoy == C.Index && V.ConvoyRank == r;
				}
				bMembers &= bFound;
			}
		}
		Expect(bMembers, TEXT("a convoy's hulls are not the vessels that say they are its hulls"));
		Done = FString::Printf(TEXT("%d convoys out of the Gate, %d hulls under way at once, %d escort craft flying, columns closed up to %.2f km and never wider than %.1f km once settled"), St.ConvoysCame, PeakUnder, PeakEscorts, Closest, Widest);
	}
	else if (What.Equals(TEXT("patrol"), ESearchCase::IgnoreCase))
	{
		// the war takes the flight nearest the Aquila: it leaves the traffic with its craft handed over where they are; it cannot be taken twice; it comes back short and is made whole again after a rest
		TArray<FPatrolInfo> Near;
		PatrolsNear(Owner->Ships[0].Pos, 400.0 * LfKm, Near);
		const FPatrolInfo* Pick = nullptr;
		for (const FPatrolInfo& P : Near)
		{
			if (!P.bEscort && P.State == 0)
			{
				Pick = &P;
				break;
			}
		}
		Expect(Pick != nullptr, TEXT("no patrol is flying in this system"));
		if (Pick)
		{
			const int32 Id = Pick->Id;
			const int32 Complement = Pick->Craft;
			const FString Mesh = Pick->Mesh;
			const FVector Middle = Pick->Pos;
			TArray<AstraSpace::FPatrolCraft> Craft;
			FString M2, Why;
			Expect(PullPatrol(Id, Craft, M2, Why), FString::Printf(TEXT("the patrol was not taken: %s"), *Why));
			Expect(Craft.Num() == Complement && M2 == Mesh, FString::Printf(TEXT("%d craft of %s handed over, the flight had %d of %s"), Craft.Num(), *M2, Complement, *Mesh));
			bool bPlaced = true;
			for (const AstraSpace::FPatrolCraft& C : Craft)
			{
				bPlaced &= !C.Pos.ContainsNaN() && !C.Vel.ContainsNaN() && !C.Att.ContainsNaN() && FVector::Dist(C.Pos, Middle) < 12.0 * LfKm && C.Vel.Size() < 600.0;
			}
			Expect(bPlaced, TEXT("a craft handed over has no sound position, velocity or attitude"));
			TArray<FPatrolInfo> After;
			PatrolsNear(Owner->Ships[0].Pos, 400.0 * LfKm, After);
			bool bStillListed = false;
			for (const FPatrolInfo& P : After)
			{
				bStillListed |= P.Id == Id;
			}
			Expect(!bStillListed, TEXT("the patrol the war took is still listed as flying"));
			TArray<AstraSpace::FPatrolCraft> Again;
			FString M3, Why2;
			Expect(!PullPatrol(Id, Again, M3, Why2) && !Why2.IsEmpty(), TEXT("a patrol was taken twice"));
			Run(120.0);
			ReturnPatrol(Id, Complement - 1);                                // one craft lost
			Run(300.0);
			TArray<FPatrolInfo> Back;
			PatrolsNear(Owner->Ships[0].Pos, 400.0 * LfKm, Back);
			bool bBack = false;
			for (const FPatrolInfo& P : Back)
			{
				bBack |= P.Id == Id;
			}
			Expect(!bBack, TEXT("the flight that came home short is flying again at once (it should rest and be made whole)"));
			Run(1100.0);
			TArray<FPatrolInfo> Whole;
			PatrolsNear(Owner->Ships[0].Pos, 400.0 * LfKm, Whole);
			int32 Craft2 = 0;
			for (const FPatrolInfo& P : Whole)
			{
				Craft2 = P.Id == Id ? P.Craft : Craft2;
			}
			Expect(Craft2 == Complement, FString::Printf(TEXT("the flight is flying again with %d craft after a rest of a quarter of an hour, not %d"), Craft2, Complement));
			// and one the war lost entirely is made new after twenty minutes
			TArray<AstraSpace::FPatrolCraft> Craft3;
			FString M4, Why3;
			Expect(PullPatrol(Id, Craft3, M4, Why3), FString::Printf(TEXT("the patrol was not taken again: %s"), *Why3));
			ReturnPatrol(Id, 0);
			Run(1000.0);
			TArray<FPatrolInfo> Lost;
			PatrolsNear(Owner->Ships[0].Pos, 400.0 * LfKm, Lost);
			bool bFlyingLost = false;
			for (const FPatrolInfo& P : Lost)
			{
				bFlyingLost |= P.Id == Id;
			}
			Expect(!bFlyingLost, TEXT("a flight the war lost entirely is flying again before twenty minutes"));
			Run(600.0);
			TArray<FPatrolInfo> New;
			PatrolsNear(Owner->Ships[0].Pos, 400.0 * LfKm, New);
			int32 Craft4 = 0;
			for (const FPatrolInfo& P : New)
			{
				Craft4 = P.Id == Id ? P.Craft : Craft4;
			}
			Expect(Craft4 == Complement, FString::Printf(TEXT("the new flight has %d craft, not %d"), Craft4, Complement));
			for (const AstraSpace::FEvent& E : Events)                         // (what PullPatrol and ReturnPatrol said to the crew, which the world's next tick would have sent on)
			{
				Ev.Add(E);
			}
			Events.Reset();
			Expect(Said(TEXT("are released to the Aquila's command")) >= 2 && Said(TEXT("is coming home from the Aquila's fight")) >= 2, FString::Printf(TEXT("what the crew is told of the patrol: %d releases, %d homecomings"), Said(TEXT("are released to the Aquila's command")), Said(TEXT("is coming home from the Aquila's fight"))));
			Done = FString::Printf(TEXT("a flight of %d %s taken, handed over whole, not taken twice, back short and made whole in a quarter of an hour, lost and made new in twenty minutes"), Complement, *Mesh);
		}
	}
	else
	{
		OutDetail = TEXT("what? look, tug, convoys or patrol");
		return false;
	}
	// (what the traffic said of its own life, for whoever reads the log: the first few)
	int32 Shown = 0;
	for (const AstraSpace::FEvent& E : Ev)
	{
		if (!E.Text.IsEmpty() && Shown++ < 8)
		{
			UE_LOG(LogASTRA, Display, TEXT("[Space] life said: %s"), *E.Text);
		}
	}
	OutDetail = FString::Printf(TEXT("%s: %d checks: %s"), *What, Checked, Failed ? *Lines : *Done);
	return Failed == 0 && Checked > 0;
}

// ------------------------------------------------------------------------------------------------------------------ the console
namespace
{
	FAutoConsoleCommandWithWorld CmdSpaceConvoys(TEXT("astra.space.convoys"), TEXT("The convoys of the system: their hulls, what each is doing, how far behind the one ahead, when they next come out of the Gate"),
		FConsoleCommandWithWorldDelegate::CreateLambda([](UWorld* W)
		{
			UAstraBattleSubsystem* B = W ? W->GetSubsystem<UAstraBattleSubsystem>() : nullptr;
			UAstraSpaceLife* S = B ? B->GetSpace() : nullptr;
			UE_LOG(LogASTRA, Display, TEXT("[Space] %s"), S ? *S->ConvoyList() : TEXT("none in this world"));
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdSpaceLifeTest(TEXT("astra.space.life.test"), TEXT("The traffic's own life, on a quiet system with something to look at: astra.space.life.test <look|tug|convoys|patrol>"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& A, UWorld* W)
		{
			UAstraBattleSubsystem* B = W ? W->GetSubsystem<UAstraBattleSubsystem>() : nullptr;
			UAstraSpaceLife* S = B ? B->GetSpace() : nullptr;
			if (!S || A.Num() < 1) { UE_LOG(LogASTRA, Display, TEXT("[Space] astra.space.life.test <look|tug|convoys|patrol>")); return; }
			FString Detail;
			const bool bOk = S->DebugLife(A[0], Detail);
			UE_LOG(LogASTRA, Display, TEXT("[Space] life: %s %s"), *Detail, bOk ? TEXT("LIFE_OK") : TEXT("LIFE_FAILED"));
		}));
}
