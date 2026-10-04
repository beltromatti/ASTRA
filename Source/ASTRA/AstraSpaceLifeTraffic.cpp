// ASTRA — the civilian traffic of a system: tours, berths, lanes, the Gate's queue, the reactions to a war, the patrols. See AstraSpaceLifeTraffic.h and docs/SPAZIO.md.

#include "AstraSpaceLifeTraffic.h"
#include "ASTRA.h"
#include "HAL/PlatformTime.h"

namespace AstraSpace
{
	namespace
	{
		constexpr float SpFleeKm = 16.f;          // a hostile this near: run
		constexpr float SpDivertKm = 48.f;        // this near and closing: leave the lane for a refuge
		constexpr float SpCalmKm = 75.f;          // no hostile nearer than this for a while: back to the routes
		constexpr float SpCalmFor = 90.f;         // ... for this many seconds
		constexpr float SpHideAfter = 70.f;       // a vessel that has run this long with no refuge goes dark
		constexpr double SpGateRunSpeed = 420.0;  // what the Gate's field gives a vessel through the ring (m/s)
		constexpr float SpThinkEvery = 0.2f;

		FVector SpRight(const FVector& Dir)
		{
			const FVector R = FVector::CrossProduct(FVector::UpVector, Dir);
			return R.SizeSquared() > 1e-8 ? R.GetSafeNormal() : FVector::RightVector;
		}

		FQuat SpFaceAlong(const FVector& Dir, const FVector& Up = FVector::UpVector)
		{
			return FRotationMatrix::MakeFromXZ(Dir.GetSafeNormal(), Up).ToQuat();
		}

		double SpBearing(const FVector& From, const FVector& To)
		{
			const FVector D = To - From;
			return FMath::Fmod(FMath::RadiansToDegrees(FMath::Atan2(D.Y, D.X)) + 360.0, 360.0);
		}

		double SpMark(const FVector& From, const FVector& To)
		{
			const FVector D = To - From;
			return FMath::RadiansToDegrees(FMath::Atan2(D.Z, FVector2D(D.X, D.Y).Size()));
		}

		bool SpIsRefuge(EPlaceKind K) { return K == EPlaceKind::Keeper || K == EPlaceKind::Arsenal; }
	}

	const TCHAR* StateName(EVState S)
	{
		static const TCHAR* const N[(int32)EVState::Num] = {TEXT("docked"), TEXT("departing"), TEXT("cruise"), TEXT("docking"), TEXT("holding"), TEXT("gate_out"),
		                                                    TEXT("gate_in"), TEXT("away"), TEXT("fleeing"), TEXT("hiding")};
		return N[FMath::Clamp((int32)S, 0, (int32)EVState::Num - 1)];
	}

	// ------------------------------------------------------------------------------------------------------------------ making
	void FTraffic::Reset()
	{
		Vs.Reset();
		Ps.Reset();
		St = FTrafficStats();
		UsedNames.Reset();
		GateQueue.Reset();
		NextId = 1;
		SystemAlert = 0;
		AlertSince = -1.0;
		LastDanger = -1e9;
		LastMayday = -1e9;
		LastScatter = -1e9;
		bGateWasClosed = false;
		ThinkAcc = 0.f;
	}

	FString FTraffic::PickName(const FHullDef& H, FRandomStream& R)
	{
		static const TCHAR* const Suffix[] = {TEXT(""), TEXT(" II"), TEXT(" III"), TEXT(" IV"), TEXT(" V"), TEXT(" VI")};
		const FString Base = H.Names.Num() ? H.Names[R.RandRange(0, H.Names.Num() - 1)] : FString::Printf(TEXT("%s %d"), *H.Class, NextId);
		for (const TCHAR* S : Suffix)
		{
			const FString N = Base + S;
			if (!UsedNames.Contains(N))
			{
				UsedNames.Add(N);
				return N;
			}
		}
		const FString N = FString::Printf(TEXT("%s %d"), *Base, NextId);
		UsedNames.Add(N);
		return N;
	}

	FVessel FTraffic::MakeVessel(const FTourSpec& T, int32 Index)
	{
		FVessel V;
		V.Id = NextId++;
		V.Hull = T.Hull;
		V.Seed = (uint32)Rng.GetUnsignedInt();
		if (const FHullDef* H = Set->Hull(T.Hull))
		{
			V.MeshIdx = H->Meshes.Num() ? Rng.RandRange(0, H->Meshes.Num() - 1) : 0;
			V.Name = PickName(*H, Rng);
			V.Company = H->Companies.Num() ? H->Companies[Rng.RandRange(0, H->Companies.Num() - 1)] : FString();
			// where it keeps in a lane: the bigger the hull the wider it keeps, and the vessels of a lane are stacked a little in height
			V.LateralM = 380.f + H->Radius * 0.9f + Rng.FRand() * 260.f;
			V.VertM = (float)((V.Id % 3) - 1) * (160.f + H->Radius * 0.8f);
		}
		for (const FName& Id : T.Nodes)
		{
			const int32 N = L->FindNode(Id);
			if (N != INDEX_NONE)
			{
				V.Tour.Add(N);
			}
		}
		V.Dwell = T.DwellMin;
		V.ThinkT = Rng.FRand() * SpThinkEvery;
		(void)Index;
		return V;
	}

	bool FTraffic::PlaceAtStart(FVessel& V)
	{
		if (V.Tour.Num() == 0)
		{
			return false;                                    // a tour of places this system has not got
		}
		V.TourIdx = Rng.RandRange(0, V.Tour.Num() - 1);
		V.Node = V.Tour[V.TourIdx];
		const FNode& Here = L->Nodes[V.Node];
		// a tour that goes out through the Gate: some of its vessels start beyond it, due back at various times
		if (Here.Kind == EPlaceKind::Gate || Here.Kind == EPlaceKind::Orbit)
		{
			V.State = EVState::Away;
			V.ReturnAt = Clock + Rng.FRandRange(10.f, 700.f);
			return true;
		}
		const bool bFly = V.Tour.Num() > 1 && (Here.Slots.Num() == 0 || Rng.FRand() < 0.55f);
		if (!bFly)
		{
			const int32 S = ClaimSlot(V, V.Node);
			if (S != INDEX_NONE)
			{
				FSlot& Sl = L->Nodes[V.Node].Slots[S];
				Sl.Reserved = INDEX_NONE;
				Sl.Occupant = V.Id;
				V.Slot = S;
				V.State = EVState::Docked;
				V.Pos = Sl.CentreFor(HullLen(V));
				V.Att = Sl.Att;
				V.DwellLeft = Rng.FRandRange((float)V.Dwell.X, (float)V.Dwell.Y) * Rng.FRand();
				return true;
			}
		}
		// in flight on the lane between this call and the next, a random way along it
		const int32 NextIdx = (V.TourIdx + 1) % V.Tour.Num();
		V.TourIdx = NextIdx;
		BuildRoute(V, Here.Entry, V.Node, V.Tour[NextIdx]);
		V.Node = V.Tour[NextIdx];
		if (V.Route.Num() < 2)
		{
			return false;                                    // no lane between two calls of its tour: a mistake of the data (the bench says which)
		}
		double Total = 0.0;
		for (int32 i = 0; i + 1 < V.Route.Num(); ++i)
		{
			Total += FVector::Dist(V.Route[i], V.Route[i + 1]);
		}
		double Walk = Total * Rng.FRandRange(0.05f, 0.95f), Run = 0.0;
		int32 Seg = 0;
		for (; Seg + 2 < V.Route.Num(); ++Seg)
		{
			const double Len = FVector::Dist(V.Route[Seg], V.Route[Seg + 1]);
			if (Walk <= Run + Len)
			{
				break;
			}
			Run += Len;
		}
		const double Len = FMath::Max(1.0, (double)FVector::Dist(V.Route[Seg], V.Route[Seg + 1]));
		V.Pos = FMath::Lerp(V.Route[Seg], V.Route[Seg + 1], FMath::Clamp((Walk - Run) / Len, 0.0, 1.0));
		const FVector Dir = (V.Route[Seg + 1] - V.Route[Seg]).GetSafeNormal();
		const FHullDef* H = HullOf(V);
		V.Vel = Dir * (H ? H->Cruise * 0.92f : 100.f);
		V.Att = SpFaceAlong(Dir);
		V.RouteIdx = Seg + 1;
		V.State = EVState::Cruise;
		V.Thrust = 0.14f;
		return true;
	}

	void FTraffic::Init(const FDataSet& InSet, FLayout& Layout, uint32 Seed, double Now, float Density)
	{
		Set = &InSet;
		L = &Layout;
		Reset();
		Rng.Initialize((int32)(Seed * 2654435761u ^ 0x5BD1E995u));
		Clock = Now;
		if (!L->Spec)
		{
			return;
		}
		for (const FTourSpec& T : L->Spec->Tours)
		{
			if (!Set->Hull(T.Hull))
			{
				continue;
			}
			const float Want = (float)T.Count * Density * L->Spec->Density;
			int32 N = FMath::FloorToInt(Want);
			N += Rng.FRand() < (Want - N) ? 1 : 0;
			for (int32 i = 0; i < N; ++i)
			{
				FVessel V = MakeVessel(T, i);
				if (PlaceAtStart(V))
				{
					Vs.Add(MoveTemp(V));
				}
				else
				{
					UE_LOG(LogASTRA, Warning, TEXT("[Space] %s: a vessel of the %s tour has no lane between its calls (or no calls here): dropped"), *L->System, *T.Hull.ToString());
				}
			}
		}
		MakePatrols();
		RebuildStats();
	}

	void FTraffic::MakePatrols()
	{
		Ps.Reset();
		if (!L->Spec)
		{
			return;
		}
		for (const FPatrolSpec& Sp : L->Spec->Patrols)
		{
			const int32 N = L->FindNode(Sp.Node);
			if (N == INDEX_NONE)
			{
				continue;
			}
			FPatrol P;
			P.Id = Ps.Num() + 1;
			P.Node = N;
			P.Mesh = Sp.Mesh;
			P.Centre = L->Nodes[N].Pos;
			P.RadiusM = Sp.RadiusKm * 1000.f;
			P.SpeedMps = Sp.SpeedMps;
			P.Phase = Rng.FRand() * 2.0 * PI;
			P.Tilt = FQuat(FVector::XAxisVector, Rng.FRandRange(-0.25f, 0.25f)) * FQuat(FVector::YAxisVector, Rng.FRandRange(-0.2f, 0.2f)) * FQuat(FVector::ZAxisVector, Rng.FRand() * 2.f * PI);
			// the formation: slots in the leader's frame (x ahead, y to starboard, z up), spaced for craft of this size
			const float S = Sp.Mesh.Contains(TEXT("Falcon")) ? 40.f : (Sp.Mesh.Contains(TEXT("Hammer")) ? 55.f : 150.f);
			P.Scale = S;
			P.Slots.Add(FVector::ZeroVector);
			const bool bWedge = Sp.Formation.Equals(TEXT("wedge"), ESearchCase::IgnoreCase), bEchelon = Sp.Formation.Equals(TEXT("echelon"), ESearchCase::IgnoreCase),
			           bDiamond = Sp.Formation.Equals(TEXT("diamond"), ESearchCase::IgnoreCase);
			for (int32 i = 1; i < Sp.Craft; ++i)
			{
				const int32 Rank = (i + 1) / 2;
				const float Side = (i % 2) ? 1.f : -1.f;
				if (bEchelon)
				{
					P.Slots.Add(FVector(-S * 1.6f * i, S * 1.4f * i, S * 0.12f * i));
				}
				else if (bDiamond)
				{
					P.Slots.Add(i == 1 ? FVector(-S * 1.8f, S * 1.5f, 0.f) : (i == 2 ? FVector(-S * 1.8f, -S * 1.5f, 0.f) : FVector(-S * 3.6f, 0.f, 0.f)));
				}
				else if (bWedge)
				{
					P.Slots.Add(FVector(-S * 1.7f * Rank, Side * S * 1.5f * Rank, S * 0.1f * Rank * Side));
				}
				else
				{
					P.Slots.Add(FVector(-S * 2.2f * i, 0.f, 0.f));      // a line astern
				}
			}
			for (int32 i = 0; i < Sp.Craft; ++i)
			{
				FPatrolCraft C;
				C.Pos = P.Centre;
				P.Craft.Add(C);
			}
			Ps.Add(MoveTemp(P));
		}
	}

	// ------------------------------------------------------------------------------------------------------------------ berths and holding points
	int32 FTraffic::ClaimSlot(FVessel& V, int32 Node)
	{
		FNode& N = L->Nodes[Node];
		const FHullDef* H = HullOf(V);
		const uint32 Role = H ? RoleBit(H->Role) : 0u;
		int32 Best = INDEX_NONE;
		double BestScore = 1e18;
		for (int32 i = 0; i < N.Slots.Num(); ++i)
		{
			const FSlot& S = N.Slots[i];
			if (S.Occupant != INDEX_NONE || (S.Reserved != INDEX_NONE && S.Reserved != V.Id))
			{
				continue;
			}
			if (H && S.MaxLen < H->Length * 0.98f)
			{
				continue;                                        // too long for the berth
			}
			if (S.Roles != 0 && !(S.Roles & Role))
			{
				continue;                                        // not for this kind of hull
			}
			// the tightest fit: a tug does not take a freighter's berth
			const double Score = (double)S.MaxLen + (S.Roles != 0 ? 0.0 : 400.0);
			if (Score < BestScore)
			{
				BestScore = Score;
				Best = i;
			}
		}
		if (Best != INDEX_NONE)
		{
			N.Slots[Best].Reserved = V.Id;
			V.Slot = Best;
			V.DockApproach = N.Slots[Best].Approach;
		}
		return Best;
	}

	void FTraffic::FreeSlot(FVessel& V)
	{
		if (V.Slot != INDEX_NONE && V.Node != INDEX_NONE && L->Nodes.IsValidIndex(V.Node) && L->Nodes[V.Node].Slots.IsValidIndex(V.Slot))
		{
			FSlot& S = L->Nodes[V.Node].Slots[V.Slot];
			if (S.Occupant == V.Id) { S.Occupant = INDEX_NONE; }
			if (S.Reserved == V.Id) { S.Reserved = INDEX_NONE; }
		}
		V.Slot = INDEX_NONE;
	}

	int32 FTraffic::ClaimHold(FVessel& V, int32 Node)
	{
		FNode& N = L->Nodes[Node];
		for (int32 i = 0; i < N.Holds.Num(); ++i)
		{
			if (N.HoldTaken[i] == INDEX_NONE)
			{
				N.HoldTaken[i] = V.Id;
				V.Hold = i;
				return i;
			}
		}
		return INDEX_NONE;
	}

	void FTraffic::FreeHold(FVessel& V)
	{
		if (V.Hold != INDEX_NONE && V.Node != INDEX_NONE && L->Nodes.IsValidIndex(V.Node) && L->Nodes[V.Node].HoldTaken.IsValidIndex(V.Hold) && L->Nodes[V.Node].HoldTaken[V.Hold] == V.Id)
		{
			L->Nodes[V.Node].HoldTaken[V.Hold] = INDEX_NONE;
		}
		V.Hold = INDEX_NONE;
	}

	// ------------------------------------------------------------------------------------------------------------------ routes
	int32 FTraffic::NextIdx(const FVessel& V) const
	{
		if (V.Tour.Num() == 0)
		{
			return INDEX_NONE;
		}
		// at the call it was bound for: on to the next one of the tour; docked somewhere else (a refuge): on to the call it never reached
		const bool bAtCall = V.Node == V.Tour[V.TourIdx];
		return bAtCall ? (V.TourIdx + 1) % V.Tour.Num() : V.TourIdx;
	}

	void FTraffic::BuildRoute(FVessel& V, const FVector& From, int32 FromNode, int32 ToNode)
	{
		V.Route.Reset();
		V.RouteIdx = 0;
		TArray<FVector, TInlineAllocator<10>> Pts;
		bool bFwd = true;
		const int32 Li = FromNode != INDEX_NONE ? L->FindLane(FromNode, ToNode, bFwd) : INDEX_NONE;
		const FNode& To = L->Nodes[ToNode];
		if (Li != INDEX_NONE)
		{
			const FLane& Ln = L->Lanes[Li];
			if (bFwd)
			{
				Pts.Append(Ln.Pts);
			}
			else
			{
				for (int32 i = Ln.Pts.Num() - 1; i >= 0; --i)
				{
					Pts.Add(Ln.Pts[i]);
				}
			}
		}
		else
		{
			// no lane between the two (a refuge, a place it was driven from): straight to where lanes meet the place
			const FVector Far = From;
			Pts.Add(To.Kind == EPlaceKind::Gate ? To.Pos + To.Att.GetForwardVector() * (L->Anchors.LaneEntryKm * OneKm) : To.Pos + (Far - To.Pos).GetSafeNormal() * (To.RadiusM * 1.7 + 600.0));
		}
		// the right-hand rule: a vessel keeps to its right of the lane's axis, and to its own level
		for (int32 i = 0; i < Pts.Num(); ++i)
		{
			const FVector A = Pts[FMath::Max(i - 1, 0)], B = Pts[FMath::Min(i + 1, Pts.Num() - 1)];
			const FVector Dir = (B - A).GetSafeNormal();
			const float K = (i == 0 || i == Pts.Num() - 1) ? 0.35f : 1.f;
			Pts[i] += (SpRight(Dir) * V.LateralM + FVector::UpVector * V.VertM) * K;
		}
		// out of the ring: it starts a little way in front of it (the Gate's mouth), on the lane's axis
		if (FromNode != INDEX_NONE && L->Nodes[FromNode].Kind == EPlaceKind::Gate && From.Equals(L->Nodes[FromNode].Pos, 1.0))
		{
			const FNode& G = L->Nodes[FromNode];
			V.Route.Add(G.Pos + G.Att.GetForwardVector() * 900.0);
		}
		for (const FVector& P : Pts)
		{
			V.Route.Add(P);
		}
		V.Node = ToNode;
	}

	bool FTraffic::TryDepart(FVessel& V, double Now, TArray<FEvent>& Out)
	{
		(void)Now;
		(void)Out;
		const int32 NextI = NextIdx(V);
		if (NextI == INDEX_NONE)
		{
			return false;
		}
		const int32 Next = V.Tour[NextI];
		if (Next == V.Node)
		{
			return false;
		}
		FNode& Dest = L->Nodes[Next];
		if (Dest.bClosed || SystemAlert >= 2)
		{
			return false;
		}
		// a place with berths and no room anywhere near it: wait where we are
		if (Dest.Slots.Num() && Dest.Holds.Num())
		{
			int32 FreeSlots = 0, FreeHolds = 0;
			for (const FSlot& S : Dest.Slots) { FreeSlots += (S.Occupant == INDEX_NONE && S.Reserved == INDEX_NONE) ? 1 : 0; }
			for (const int32 H : Dest.HoldTaken) { FreeHolds += H == INDEX_NONE ? 1 : 0; }
			if (FreeSlots == 0 && FreeHolds <= 1)
			{
				return false;
			}
		}
		const FNode& From = L->Nodes[V.Node];
		// where it backs out to: along the way the berth's approach lies
		if (V.Slot != INDEX_NONE && From.Slots.IsValidIndex(V.Slot))
		{
			const FSlot& S = From.Slots[V.Slot];
			V.DockPos = S.CentreFor(HullLen(V));
			V.DockBack = (S.Approach - S.Pos).GetSafeNormal();
		}
		const int32 FromNode = V.Node;
		FreeSlot(V);
		FreeHold(V);
		const FVector Start = V.Pos;
		BuildRoute(V, Start, FromNode, Next);
		V.TourIdx = NextI;
		SetState(V, EVState::Departing);
		++St.DepartedTotal;
		return true;
	}

	void FTraffic::ArriveAtNode(FVessel& V, double Now, TArray<FEvent>& Out)
	{
		(void)Out;
		FNode& N = L->Nodes[V.Node];
		FreeHold(V);
		if (N.Kind == EPlaceKind::Gate)
		{
			// the queue for the ring: a waiting point on the lane, then the Gate takes us one at a time
			const int32 H = ClaimHold(V, V.Node);
			if (H != INDEX_NONE)
			{
				V.Route.Reset();
				V.Route.Add(N.Holds[H]);
				V.RouteIdx = 0;
			}
			else
			{
				V.Route.Reset();
				V.Route.Add(V.Pos);
			}
			SetState(V, EVState::Holding);
			GateQueue.AddUnique(V.Id);
			return;
		}
		if (N.Kind == EPlaceKind::Orbit)
		{
			// down into the world's atmosphere: it is gone for a while
			SetState(V, EVState::Away);
			V.ReturnAt = Now + Rng.FRandRange((float)V.Dwell.X, (float)V.Dwell.Y);
			return;
		}
		if (N.Slots.Num())
		{
			const int32 S = ClaimSlot(V, V.Node);
			if (S != INDEX_NONE)
			{
				V.Route.Reset();
				V.Route.Add(N.Slots[S].Approach);
				V.Route.Add(N.Slots[S].CentreFor(HullLen(V)));
				V.RouteIdx = 0;
				SetState(V, EVState::Docking);
				return;
			}
			const int32 H = ClaimHold(V, V.Node);
			V.Route.Reset();
			V.Route.Add(H != INDEX_NONE ? N.Holds[H] : V.Pos);
			V.RouteIdx = 0;
			SetState(V, EVState::Holding);
			return;
		}
		// a place with nothing to dock at (a belt, a bare waypoint): it calls and goes on
		V.DwellLeft = Rng.FRandRange((float)V.Dwell.X, (float)V.Dwell.Y) * 0.25f;
		V.Route.Reset();
		V.Route.Add(V.Pos);
		SetState(V, EVState::Holding);
	}

	// ------------------------------------------------------------------------------------------------------------------ the step
	void FTraffic::Avoid(FVessel& V, const FWorldView& View, FVector& InOutAccel) const
	{
		const FHullDef* H = HullOf(V);
		const double R = H ? H->Radius : 150.0;
		auto Push = [&](const FVector& P, double Reach, double Strength)
		{
			const FVector D = V.Pos - P;
			const double Dist = D.Size();
			if (Dist < Reach && Dist > 1.0)
			{
				InOutAccel += (D / Dist) * Strength * (1.0 - Dist / Reach);
			}
		};
		const double Max = H ? H->Accel : 3.0;
		Push(View.Aquila, View.AquilaRadiusM * 2.0 + R * 2.0 + 800.0, Max * 3.0);
		for (const FObstacle& O : View.Obstacles)
		{
			Push(O.Pos, O.RadiusM * 1.6 + R * 2.0 + 500.0, Max * 2.5);
		}
		for (const FVessel& O : Vs)
		{
			if (O.Id == V.Id || O.State == EVState::Away || O.State == EVState::Docked)
			{
				continue;
			}
			if (const FHullDef* Ho = HullOf(O))
			{
				Push(O.Pos, (R + Ho->Radius) * 2.2 + 300.0, Max * 1.6);
			}
		}
		// the structures of the system: not the ones it is bound for, nor the Gate (its ring is crossed through the middle)
		for (int32 n = 0; n < L->Nodes.Num(); ++n)
		{
			const FNode& N = L->Nodes[n];
			if (n == V.Node || N.Kind == EPlaceKind::Gate || N.Kind == EPlaceKind::Orbit || N.Kind == EPlaceKind::Belt || N.RadiusM < 1.f)
			{
				continue;
			}
			Push(N.Pos, N.RadiusM * 1.25 + R, Max * 2.0);
		}
	}

	void FTraffic::Integrate(FVessel& V, float Dt, const FWorldView& View)
	{
		const FHullDef* H = HullOf(V);
		if (!H || V.State == EVState::Docked || V.State == EVState::Away)
		{
			return;
		}
		V.StateT += Dt;
		if (V.State == EVState::Departing)
		{
			// backing out of the berth: slowly, the bow still turned in; then it turns for the lane
			const float Out = FMath::Min(V.StateT * 0.45f, 5.5f);
			V.Vel = V.DockBack * Out;
			V.Pos += V.Vel * Dt;
			V.Thrust = FMath::FInterpTo(V.Thrust, 0.16f, Dt, 1.5f);
			if (FVector::Dist(V.Pos, V.DockPos) > H->Length * 0.85f)
			{
				SetState(V, EVState::Cruise);
			}
			return;
		}
		float SpeedCap = H->Cruise;
		float AccelMax = H->Accel;
		float TurnMax = H->TurnDeg;
		float EndSpeed = 22.f;
		FVector Aim = V.Pos + V.Vel;
		bool bHaveAim = false;
		if (V.Route.Num())
		{
			// the waypoint it flies for: it moves on when it is near (a vessel that moves fast turns early)
			const double SwitchR = FMath::Max(400.0, V.Vel.Size() * 4.0);
			while (V.RouteIdx < V.Route.Num() - 1 && FVector::Dist(V.Pos, V.Route[V.RouteIdx]) < SwitchR)
			{
				++V.RouteIdx;
			}
			Aim = V.Route[FMath::Clamp(V.RouteIdx, 0, V.Route.Num() - 1)];
			bHaveAim = true;
		}
		FVector DesVel = FVector::ZeroVector;
		switch (V.State)
		{
		case EVState::Holding:
			SpeedCap = H->Cruise * 0.3f;
			EndSpeed = 0.f;
			break;
		case EVState::Docking:
			SpeedCap = 12.f;
			EndSpeed = 1.2f;
			AccelMax = FMath::Min(AccelMax, 1.2f);
			break;
		case EVState::GateOut:
			SpeedCap = (float)FMath::Lerp((double)H->Cruise, SpGateRunSpeed, FMath::Clamp(V.StateT / 28.f, 0.f, 1.f));
			AccelMax *= 3.f;
			EndSpeed = 600.f;
			break;
		case EVState::GateIn:
			AccelMax *= 4.f;                                       // the Gate's wake: a braking burn
			break;
		case EVState::Fleeing:
			SpeedCap = H->Cruise * 1.15f;
			AccelMax *= 1.5f;
			TurnMax *= 1.6f;
			EndSpeed = 40.f;
			break;
		case EVState::Hiding:
			bHaveAim = false;                                      // dark: the drive is off, it coasts
			break;
		default:
			break;
		}
		if (V.State == EVState::Hiding)
		{
			DesVel = V.Vel;
		}
		else if (bHaveAim)
		{
			const FVector To = Aim - V.Pos;
			const double Dist = To.Size();
			double Remaining = Dist;
			for (int32 i = V.RouteIdx; i + 1 < V.Route.Num(); ++i)
			{
				Remaining += FVector::Dist(V.Route[i], V.Route[i + 1]);
			}
			const double Margin = V.State == EVState::Docking ? 0.0 : (V.State == EVState::GateOut ? 0.0 : H->Radius * 0.6);
			const double Brake = FMath::Sqrt(2.0 * AccelMax * 0.75 * FMath::Max(0.0, Remaining - Margin)) + EndSpeed;
			const double Vdes = FMath::Min((double)SpeedCap, Brake);
			DesVel = Dist > 0.5 ? To / Dist * Vdes : FVector::ZeroVector;
		}
		// accelerate towards it, as hard as the engines go; what is in the way pushes back
		FVector Acc = (DesVel - V.Vel) / FMath::Max(Dt, 1e-3f);
		Acc = Acc.GetClampedToMaxSize((double)AccelMax);
		if (V.State != EVState::Docking && V.State != EVState::GateOut)
		{
			FVector Push = FVector::ZeroVector;
			Avoid(V, View, Push);
			Acc += Push.GetClampedToMaxSize((double)AccelMax * 2.0);
		}
		const float Before = (float)V.Vel.Size();
		V.Vel += Acc * Dt;
		V.Pos += V.Vel * Dt;
		const float Used = (float)Acc.Size() / FMath::Max(AccelMax, 0.1f);
		const float Want = V.State == EVState::Hiding ? 0.f : (V.State == EVState::Fleeing ? 0.95f : FMath::Clamp(0.1f + Used * 0.85f, 0.f, 1.f));
		V.Thrust = FMath::FInterpTo(V.Thrust, Want, Dt, 2.f);
		(void)Before;
		// the attitude: the bow comes round to the way it goes, no faster than the hull can turn; into a berth it squares up to it
		const double Speed = V.Vel.Size();
		FQuat Want2 = V.Att;
		if (V.State == EVState::Docking && V.Slot != INDEX_NONE && L->Nodes.IsValidIndex(V.Node) && L->Nodes[V.Node].Slots.IsValidIndex(V.Slot) && V.Route.Num())
		{
			const double ToSlot = FVector::Dist(V.Pos, V.Route.Last());
			const FQuat SlotAtt = L->Nodes[V.Node].Slots[V.Slot].Att;
			Want2 = ToSlot < H->Length * 1.2 ? SlotAtt : SpFaceAlong(V.Route.Last() - V.Pos);
		}
		else if (V.State == EVState::Hiding)
		{
			Want2 = V.Att * FQuat(FVector(0.2, 0.3, 1.0).GetSafeNormal(), FMath::DegreesToRadians(0.4f) * Dt);   // tumbling slowly
		}
		else if (Speed > 3.0)
		{
			Want2 = SpFaceAlong(V.Vel);
		}
		const float MaxStep = FMath::DegreesToRadians(TurnMax * Dt);
		const float Ang = V.Att.AngularDistance(Want2);
		V.Att = Ang <= MaxStep ? Want2 : FQuat::Slerp(V.Att, Want2, MaxStep / Ang);
		V.Att.Normalize();
	}

	void FTraffic::Think(FVessel& V, double Now, const FWorldView& View, TArray<FEvent>& Out)
	{
		const FHullDef* H = HullOf(V);
		if (!H)
		{
			return;
		}
		ReactTo(V, Now, View, Out);
		switch (V.State)
		{
		case EVState::Docked:
		{
			// a place under threat keeps its guests: nobody leaves while hostiles are near it
			if (L->Nodes.IsValidIndex(V.Node) && (L->Nodes[V.Node].Alert > 0 || SystemAlert >= 2))
			{
				break;
			}
			V.DwellLeft -= ThinkDt;
			if (V.DwellLeft <= 0.f && !TryDepart(V, Now, Out))
			{
				V.DwellLeft = Rng.FRandRange(10.f, 30.f);
			}
			break;
		}
		case EVState::Departing:
			break;
		case EVState::Cruise:
		case EVState::GateIn:
		case EVState::Fleeing:
		{
			if (V.State == EVState::Fleeing && V.Alert >= 2 && V.Route.Num() == 1 && V.Node == INDEX_NONE)
			{
				break;                                       // running blind: nowhere to arrive
			}
			if (V.Route.Num() && V.RouteIdx >= V.Route.Num() - 1 && FVector::Dist(V.Pos, V.Route.Last()) < FMath::Max(450.0, V.Vel.Size() * 5.0) && V.Node != INDEX_NONE)
			{
				ArriveAtNode(V, Now, Out);
			}
			break;
		}
		case EVState::Docking:
		{
			if (V.Route.Num() && FVector::Dist(V.Pos, V.Route.Last()) < 4.0 && V.Vel.Size() < 3.0 && L->Nodes.IsValidIndex(V.Node))
			{
				FSlot& S = L->Nodes[V.Node].Slots[V.Slot];
				S.Reserved = INDEX_NONE;
				S.Occupant = V.Id;
				V.Pos = S.CentreFor(HullLen(V));
				V.Vel = FVector::ZeroVector;
				V.Att = S.Att;
				V.Thrust = 0.f;
				V.DwellLeft = Rng.FRandRange((float)V.Dwell.X, (float)V.Dwell.Y);
				SetState(V, EVState::Docked);
				++St.DockedTotal;
			}
			break;
		}
		case EVState::Holding:
		{
			if (L->Nodes.IsValidIndex(V.Node) && L->Nodes[V.Node].Kind == EPlaceKind::Gate)
			{
				break;                                       // the Gate's own thinking calls it
			}
			// waiting for a berth, or at a place with none
			if (L->Nodes.IsValidIndex(V.Node) && L->Nodes[V.Node].Slots.Num() == 0)
			{
				V.DwellLeft -= ThinkDt;
				if (V.DwellLeft <= 0.f && V.Tour.Num() > 1)
				{
					const int32 From = V.Node;
					const int32 NextI = NextIdx(V);
					if (NextI != INDEX_NONE && V.Tour[NextI] != From)
					{
						FreeHold(V);
						BuildRoute(V, V.Pos, From, V.Tour[NextI]);
						V.TourIdx = NextI;
						SetState(V, EVState::Cruise);
					}
				}
				break;
			}
			if (L->Nodes.IsValidIndex(V.Node) && V.Hold != INDEX_NONE)
			{
				const int32 S = ClaimSlot(V, V.Node);
				if (S != INDEX_NONE)
				{
					FreeHold(V);
					const FNode& N = L->Nodes[V.Node];
					V.Route.Reset();
					V.Route.Add(N.Slots[S].Approach);
					V.Route.Add(N.Slots[S].CentreFor(HullLen(V)));
					V.RouteIdx = 0;
					SetState(V, EVState::Docking);
				}
			}
			break;
		}
		case EVState::Away:
			break;                                           // the Gate's thinking (or the orbit's, below)
		case EVState::Hiding:
			break;
		default:
			break;
		}
		// a vessel beyond an Orbit node comes back by itself, from where it went
		if (V.State == EVState::Away && L->Nodes.IsValidIndex(V.Node) && L->Nodes[V.Node].Kind == EPlaceKind::Orbit && Now >= V.ReturnAt && SystemAlert < 2)
		{
			const FNode& O = L->Nodes[V.Node];
			const int32 NextI = NextIdx(V);
			if (NextI != INDEX_NONE && V.Tour[NextI] != V.Node)
			{
				const int32 From = V.Node;
				V.Pos = O.Pos;
				V.Vel = FVector::ZeroVector;
				BuildRoute(V, V.Pos, From, V.Tour[NextI]);
				V.TourIdx = NextI;
				V.Att = V.Route.Num() ? SpFaceAlong(V.Route[0] - V.Pos) : V.Att;
				V.Vel = (V.Route.Num() ? (V.Route[0] - V.Pos).GetSafeNormal() : FVector::ForwardVector) * H->Cruise * 0.6f;
				SetState(V, EVState::Cruise);
			}
			else
			{
				V.ReturnAt = Now + 60.0;
			}
		}
	}

	// ------------------------------------------------------------------------------------------------------------------ the Gate
	void FTraffic::ThinkGate(double Now, const FWorldView& View, TArray<FEvent>& Out)
	{
		if (L->GateNode == INDEX_NONE)
		{
			return;
		}
		FNode& G = L->Nodes[L->GateNode];
		// closed: the Aquila's own transit has the lane, or hostiles are about the ring (a force coming through, a fight at the Gate)
		bool bThreat = false;
		for (const FHostile& Ho : View.Hostiles)
		{
			bThreat |= FVector::Dist(Ho.Pos, G.Pos) < 65.0 * OneKm;
		}
		const bool bClosed = View.bGateBusy || bThreat;
		G.bClosed = bClosed;
		if (bClosed != bGateWasClosed)
		{
			bGateWasClosed = bClosed;
			if (bThreat && bClosed)
			{
				FEvent E;
				E.Kind = EEventKind::GateClosed;
				E.bReport = true;
				E.At = G.Pos;
				int32 Waiting = 0;
				for (const FVessel& V : Vs) { Waiting += (V.State == EVState::Holding && V.Node == L->GateNode) ? 1 : 0; }
				E.Text = FString::Printf(TEXT("comms: Keeper Station — the Janus Gate is closed to civilian traffic while hostile contacts are about the ring (%d vessel%s holding in the lane queue; everything else is told to clear the Gate lane)"),
				                         Waiting, Waiting == 1 ? TEXT("") : TEXT("s"));
				Out.Add(E);
			}
			else if (!bClosed)
			{
				FEvent E;
				E.Kind = EEventKind::GateOpen;
				E.bReport = false;
				E.At = G.Pos;
				E.Text = TEXT("comms: Keeper Station — the Janus Gate is open to civilian traffic again");
				if (SystemAlert == 0)
				{
					Out.Add(E);
				}
			}
		}
		if (bClosed || Now < G.GateNextFree)
		{
			return;
		}
		const FVector Axis = G.Att.GetForwardVector();
		// out first: the vessel at the head of the queue (the lowest waiting point, nearest the ring)
		FVessel* Head = nullptr;
		int32 HeadHold = INT32_MAX;
		for (FVessel& V : Vs)
		{
			if (V.State == EVState::Holding && V.Node == L->GateNode && V.Hold != INDEX_NONE && V.Hold < HeadHold && V.Alert == 0)
			{
				const FVector P = G.Holds.IsValidIndex(V.Hold) ? G.Holds[V.Hold] : V.Pos;
				if (FVector::Dist(V.Pos, P) < 1500.0)
				{
					Head = &V;
					HeadHold = V.Hold;
				}
			}
		}
		if (Head)
		{
			FreeHold(*Head);
			Head->Route.Reset();
			Head->Route.Add(G.Pos + Axis * (4.0 * OneKm) + SpRight(Axis) * (double)Head->LateralM);
			Head->Route.Add(G.Pos);
			Head->RouteIdx = 0;
			Head->Node = L->GateNode;
			SetState(*Head, EVState::GateOut);
			G.GateNextFree = Now + Rng.FRandRange(22.f, 48.f);
			GateQueue.Remove(Head->Id);
			// the queue moves up: whoever waited behind it takes the point in front
			for (FVessel& W : Vs)
			{
				if (W.State == EVState::Holding && W.Node == L->GateNode && W.Hold != INDEX_NONE && W.Hold > HeadHold)
				{
					G.HoldTaken[W.Hold] = INDEX_NONE;
					--W.Hold;
					G.HoldTaken[W.Hold] = W.Id;
					W.Route.Reset();
					W.Route.Add(G.Holds[W.Hold]);
					W.RouteIdx = 0;
				}
			}
			return;
		}
		// then in: a vessel whose time is up comes out of the ring
		for (FVessel& V : Vs)
		{
			if (V.State == EVState::Away && L->Nodes.IsValidIndex(V.Node) && L->Nodes[V.Node].Kind == EPlaceKind::Gate && Now >= V.ReturnAt)
			{
				const int32 NextI = NextIdx(V);
				if (NextI == INDEX_NONE || V.Tour[NextI] == V.Node)
				{
					V.ReturnAt = Now + 90.0;
					continue;
				}
				const int32 From = V.Node;
				V.Pos = G.Pos + Axis * 500.0 - SpRight(Axis) * (double)V.LateralM;       // the inbound side of the lane
				V.Vel = Axis * (float)SpGateRunSpeed;
				V.Att = SpFaceAlong(Axis);
				BuildRoute(V, G.Pos, From, V.Tour[NextI]);
				V.TourIdx = NextI;
				V.RouteIdx = 0;
				SetState(V, EVState::GateIn);
				V.Thrust = 0.8f;
				++St.GateInTotal;
				FEvent E;
				E.Kind = EEventKind::GatePulse;
				E.At = G.Pos;
				E.Vessel = V.Id;
				E.Strength = 1.f;
				Out.Add(E);
				G.GateNextFree = Now + Rng.FRandRange(22.f, 48.f);
				return;
			}
		}
	}

	// ------------------------------------------------------------------------------------------------------------------ danger
	FString FTraffic::Where(const FVector& From, const FVector& P) const
	{
		return FString::Printf(TEXT("bearing %03.0f, mark %+.0f, %.0f km"), SpBearing(From, P), SpMark(From, P), FVector::Dist(From, P) / OneKm);
	}

	void FTraffic::ThinkDanger(double Now, const FWorldView& View, TArray<FEvent>& Out)
	{
		// each vessel's nearest hostile, and the places': what every reaction reads
		for (FVessel& V : Vs)
		{
			V.DangerKm = -1.f;
			if (V.State == EVState::Away)
			{
				continue;
			}
			double Best = 1e18;
			FVector BestPos = FVector::ZeroVector;
			for (const FHostile& H : View.Hostiles)
			{
				const double D = FVector::Dist(H.Pos, V.Pos);
				if (D < Best)
				{
					Best = D;
					BestPos = H.Pos;
				}
			}
			if (Best < 130.0 * OneKm)
			{
				V.DangerKm = (float)(Best / OneKm);
				V.DangerDir = (BestPos - V.Pos).GetSafeNormal();
			}
		}
		int32 Alerted = 0;
		bool bNear = false, bWide = false;
		for (FNode& N : L->Nodes)
		{
			double Best = 1e18;
			for (const FHostile& H : View.Hostiles)
			{
				Best = FMath::Min(Best, (double)FVector::Dist(H.Pos, N.Pos));
			}
			N.Alert = Best < 32.0 * OneKm ? 2 : (Best < 70.0 * OneKm ? 1 : 0);
			if (N.Kind != EPlaceKind::Orbit && N.Kind != EPlaceKind::Belt)
			{
				bNear |= Best < 32.0 * OneKm;
				bWide |= Best < 90.0 * OneKm;
			}
		}
		for (const FVessel& V : Vs)
		{
			Alerted += V.Alert > 0 ? 1 : 0;
		}
		const int32 Raw = bNear ? 2 : ((bWide || View.bEngagement || Alerted > 0) ? 1 : 0);
		if (Raw > 0)
		{
			LastDanger = Now;
		}
		if (Raw >= SystemAlert)
		{
			if (Raw > 0 && SystemAlert == 0)
			{
				AlertSince = Now;
			}
			SystemAlert = Raw;
		}
		else if (Now - LastDanger > SpCalmFor)
		{
			// the calm: the traffic goes back to its routes
			SystemAlert = Raw;
			if (Raw == 0)
			{
				FEvent E;
				E.Kind = EEventKind::Resume;
				E.Text = TEXT("sensors: civilian traffic is resuming its routes");
				Out.Add(E);
				AlertSince = -1.0;
			}
		}
		// the first words about it, a few seconds after it begins: how many are clearing out
		if (SystemAlert > 0 && AlertSince >= 0.0 && Now - AlertSince > 6.0 && Now - LastScatter > 240.0)
		{
			int32 Divert = 0, Dark = 0, Queue = 0;
			for (const FVessel& V : Vs)
			{
				Divert += (V.Alert == 1 || V.Alert == 2) ? 1 : 0;
				Dark += V.Alert == 3 ? 1 : 0;
				Queue += (V.State == EVState::Holding && V.Node == L->GateNode) ? 1 : 0;
			}
			if (Divert + Dark >= 2)
			{
				LastScatter = Now;
				FEvent E;
				E.Kind = EEventKind::Scatter;
				E.Text = FString::Printf(TEXT("sensors: civilian traffic is clearing the area as the hostile contacts close — %d vessel%s diverting to the berths of the Arsenal and Keeper Station, %d running dark, %d holding at the Gate"),
				                         Divert, Divert == 1 ? TEXT("") : TEXT("s"), Dark, Queue);
				Out.Add(E);
			}
		}
	}

	int32 FTraffic::PickRefuge(const FVessel& V, float ClearKm) const
	{
		// the berths of the Arsenal or Keeper Station: the one furthest from the danger whose way does not lead past it (a hostile behind us is no reason not to run)
		const FVector Hostile = V.Pos + V.DangerDir * (V.DangerKm * OneKm);
		int32 Best = INDEX_NONE;
		double BestScore = -1e18;
		for (int32 n = 0; n < L->Nodes.Num(); ++n)
		{
			const FNode& N = L->Nodes[n];
			if (!SpIsRefuge(N.Kind) || N.bClosed || N.Alert >= 2)
			{
				continue;
			}
			const FVector Way = N.Pos - V.Pos;
			const double Len2 = FMath::Max(1.0, Way.SizeSquared());
			const double T = FVector::DotProduct(Hostile - V.Pos, Way) / Len2;
			if (T > 0.02 && FVector::Dist(Hostile, V.Pos + Way * FMath::Min(T, 1.0)) < ClearKm * OneKm)
			{
				continue;                                                  // the way there passes the danger
			}
			const double Score = FVector::Dist(N.Pos, Hostile) - 0.35 * FMath::Sqrt(Len2);
			if (Score > BestScore)
			{
				BestScore = Score;
				Best = n;
			}
		}
		return Best;
	}

	void FTraffic::ReactTo(FVessel& V, double Now, const FWorldView& View, TArray<FEvent>& Out)
	{
		if (V.State == EVState::Away)
		{
			return;
		}
		const bool bNear = V.DangerKm >= 0.f;
		if (V.State == EVState::Docked)
		{
			// safe in its berth (the place's alert keeps it there); the call it made is over when the danger has been gone a while
			if (V.Alert > 0 && !(bNear && V.DangerKm < SpCalmKm))
			{
				V.CalmT += ThinkDt;
				if (V.CalmT > SpCalmFor)
				{
					V.Alert = 0;
					V.bCalled = false;
					V.CalmT = 0.f;
				}
			}
			else
			{
				V.CalmT = 0.f;
			}
			return;
		}
		if (bNear && V.DangerKm < SpFleeKm)
		{
			V.CalmT = 0.f;
			if (V.Alert < 2)
			{
				V.Alert = 2;
				V.AlertT = 0.f;
				const int32 Best = PickRefuge(V, 12.f);
				FreeHold(V);
				const bool bWasGateQueue = V.Node == L->GateNode;
				FreeSlot(V);
				GateQueue.Remove(V.Id);
				if (Best != INDEX_NONE)
				{
					const FNode& N = L->Nodes[Best];
					V.Route.Reset();
					V.Route.Add(N.Pos + (V.Pos - N.Pos).GetSafeNormal() * (N.RadiusM * 1.7 + 600.0));
					V.RouteIdx = 0;
					V.Node = Best;
				}
				else
				{
					V.Route.Reset();
					V.Route.Add(V.Pos - V.DangerDir * (60.0 * OneKm));      // nowhere to run to: away from it
					V.RouteIdx = 0;
					V.Node = INDEX_NONE;
				}
				(void)bWasGateQueue;
				SetState(V, EVState::Fleeing);
				V.bLit = true;
				// the call for help: the first vessel of an alert to be close, then others at a distance of time (the comms' watch is not a switchboard)
				if (!V.bCalled && Now - LastMayday > 25.0)
				{
					V.bCalled = true;
					LastMayday = Now;
					++St.Maydays;
					const FHullDef* H = HullOf(V);
					FEvent E;
					E.Kind = EEventKind::Mayday;
					E.bReport = FVector::Dist(V.Pos, View.Aquila) < 90.0 * OneKm;
					E.At = V.Pos;
					E.Vessel = V.Id;
					int32 Warships = 0, Fighters = 0;
					for (const FHostile& Ho : View.Hostiles)
					{
						if (FVector::Dist(Ho.Pos, V.Pos) < 30.0 * OneKm)
						{
							(Ho.bCraft ? Fighters : Warships) += 1;
						}
					}
					FString What = Warships && Fighters ? FString::Printf(TEXT("%d hostile warship%s and %d strike craft"), Warships, Warships == 1 ? TEXT("") : TEXT("s"), Fighters)
					             : (Fighters ? FString::Printf(TEXT("%d hostile strike craft"), Fighters) : FString::Printf(TEXT("%d hostile warship%s"), FMath::Max(1, Warships), Warships == 1 ? TEXT("") : TEXT("s")));
					const FString Run = Best != INDEX_NONE ? FString::Printf(TEXT("she is running for the berths of %s"), *L->Nodes[Best].Name) : FString(TEXT("she is running blind, no berth within reach"));
					E.Text = FString::Printf(TEXT("comms: distress call from the %s %s%s — %s %.0f km off her and closing; %s. She is at %s from us"),
					                         H ? *H->Class : TEXT("civilian vessel"), *V.Name, V.Company.IsEmpty() ? TEXT("") : *FString::Printf(TEXT(" (%s)"), *V.Company), *What,
					                         V.DangerKm, *Run, *Where(View.Aquila, V.Pos));
					Out.Add(E);
				}
			}
			return;
		}
		if (bNear && V.DangerKm < SpDivertKm && V.Alert < 1)
		{
			// near, and it is not going away from it: leave the lane for a refuge (a vessel already bound for one keeps its course)
			const FVector Heading = V.Vel.GetSafeNormal();
			if (FVector::DotProduct(Heading, V.DangerDir) > -0.1f || V.Vel.Size() < 20.0)
			{
				V.Alert = 1;
				V.AlertT = 0.f;
				V.CalmT = 0.f;
				const int32 Best = PickRefuge(V, 14.f);
				FreeHold(V);
				FreeSlot(V);
				GateQueue.Remove(V.Id);
				if (Best != INDEX_NONE)
				{
					const FNode& N = L->Nodes[Best];
					V.Route.Reset();
					V.Route.Add(N.Pos + (V.Pos - N.Pos).GetSafeNormal() * (N.RadiusM * 1.7 + 600.0));
					V.RouteIdx = 0;
					V.Node = Best;
					SetState(V, EVState::Cruise);
				}
				else
				{
					V.Route.Reset();
					V.Route.Add(V.Pos - V.DangerDir * (45.0 * OneKm));
					V.RouteIdx = 0;
					V.Node = INDEX_NONE;
					SetState(V, EVState::Fleeing);
				}
			}
			return;
		}
		if (V.Alert > 0)
		{
			V.AlertT += ThinkDt;
			if (bNear && V.DangerKm < SpCalmKm)
			{
				V.CalmT = 0.f;
				// running with no refuge for a long time and the danger still near: it kills the drive and the lights and drifts, a speck among the rest
				if (V.State == EVState::Fleeing && V.Node == INDEX_NONE && V.AlertT > SpHideAfter)
				{
					V.Alert = 3;
					V.bLit = false;
					SetState(V, EVState::Hiding);
				}
			}
			else
			{
				V.CalmT += ThinkDt;
				if (V.CalmT > SpCalmFor)
				{
					// the danger has gone: back to the tour, from where it is, to the call it was bound for
					V.Alert = 0;
					V.bCalled = false;
					V.bLit = true;
					V.CalmT = 0.f;
					const int32 Dest = V.Tour.Num() ? V.Tour[V.TourIdx] : INDEX_NONE;
					if (V.State == EVState::Hiding || V.State == EVState::Fleeing || V.State == EVState::Cruise || V.State == EVState::Holding)
					{
						if (Dest != INDEX_NONE)
						{
							FreeHold(V);
							BuildRoute(V, V.Pos, V.Node, Dest);
							SetState(V, EVState::Cruise);
						}
					}
				}
			}
		}
	}

	// ------------------------------------------------------------------------------------------------------------------ patrols
	void FTraffic::TickPatrols(float Dt, double Now, const FWorldView& View)
	{
		(void)Now;
		for (FPatrol& P : Ps)
		{
			if (P.State == 2)
			{
				// back after the calm
				P.AwayT += Dt;
				if (SystemAlert == 0 && P.AwayT > 150.f)
				{
					P.State = 0;
					P.Phase = FMath::Fmod(P.Phase + 1.7, 2.0 * PI);
					for (FPatrolCraft& C : P.Craft)
					{
						C.Pos = P.Centre + FVector(Rng.FRandRange(-2000.f, 2000.f), Rng.FRandRange(-2000.f, 2000.f), Rng.FRandRange(-300.f, 300.f));
					}
				}
				continue;
			}
			if (P.State == 0 && SystemAlert >= 1)
			{
				P.State = 1;                                                    // scrambled: run for the berths
			}
			if (P.State == 1)
			{
				const FNode& N = L->Nodes[P.Node];
				bool bAny = false;
				for (FPatrolCraft& C : P.Craft)
				{
					const FVector To = N.Pos - C.Pos;
					const double D = To.Size();
					if (D < 900.0)
					{
						continue;
					}
					bAny = true;
					const FVector Want = To / D * P.SpeedMps * 1.25f;
					C.Vel += (Want - C.Vel).GetClampedToMaxSize(60.0 * Dt);
					C.Pos += C.Vel * Dt;
					C.Att = FQuat::Slerp(C.Att, SpFaceAlong(C.Vel), FMath::Clamp(Dt * 2.f, 0.f, 1.f));
				}
				if (!bAny)
				{
					P.State = 2;
					P.AwayT = 0.f;
				}
				continue;
			}
			// the leader on a racetrack in a tilted plane, a figure of eight with a little roll of height; the wingmen on springs behind it
			const double W = P.SpeedMps / FMath::Max(1000.f, P.RadiusM);
			P.Phase += W * Dt;
			auto Track = [&](double Th) { return P.Centre + P.Tilt.RotateVector(FVector(P.RadiusM * FMath::Cos(Th), P.RadiusM * 0.6 * FMath::Sin(Th), P.RadiusM * 0.14 * FMath::Sin(2.0 * Th))); };
			FPatrolCraft& Lead = P.Craft[0];
			const FVector Prev = Lead.Pos;
			Lead.Pos = Track(P.Phase);
			const FVector Ahead = Track(P.Phase + 0.05);
			Lead.Vel = Dt > 1e-4f ? (Lead.Pos - Prev) / Dt : Lead.Vel;
			if (Prev.Equals(P.Centre, 1.0))
			{
				Lead.Vel = (Ahead - Lead.Pos).GetSafeNormal() * P.SpeedMps;     // the first step
			}
			const FVector Dir = (Ahead - Lead.Pos).GetSafeNormal();
			const FVector Behind = Track(P.Phase - 0.05);
			const FVector Turn = (Ahead + Behind - 2.0 * Lead.Pos);                 // the curvature: which way, how hard
			const float BankWant = FMath::Clamp((float)(FVector::DotProduct(Turn, SpRight(Dir)) / FMath::Max(1.0, Turn.Size())) * 0.9f * (float)FMath::Min(1.0, Turn.Size() / (P.RadiusM * 0.0045)), -0.9f, 0.9f);
			Lead.Bank = FMath::FInterpTo(Lead.Bank, BankWant, Dt, 1.2f);
			const FVector Up = (FVector::UpVector * FMath::Cos(Lead.Bank) + SpRight(Dir) * FMath::Sin(Lead.Bank)).GetSafeNormal();
			Lead.Att = FRotationMatrix::MakeFromXZ(Dir, Up).ToQuat();
			for (int32 i = 1; i < P.Craft.Num(); ++i)
			{
				FPatrolCraft& C = P.Craft[i];
				const FVector Target = Lead.Pos + Lead.Att.RotateVector(P.Slots[FMath::Min(i, P.Slots.Num() - 1)]);
				const FVector Old = C.Pos;
				C.Pos += (Target - C.Pos) * (1.f - FMath::Exp(-Dt / 1.3f));
				C.Vel = Dt > 1e-4f ? (C.Pos - Old) / Dt : C.Vel;
				C.Bank = FMath::FInterpTo(C.Bank, Lead.Bank, Dt, 1.2f);
				C.Att = FQuat::Slerp(C.Att, Lead.Att, FMath::Clamp(Dt * 1.6f, 0.f, 1.f));
			}
		}
		(void)View;
	}

	// ------------------------------------------------------------------------------------------------------------------ the whole
	void FTraffic::SetNodeClosed(int32 Node, bool bClosed)
	{
		if (L && L->Nodes.IsValidIndex(Node))
		{
			L->Nodes[Node].bClosed = bClosed;
		}
	}

	void FTraffic::Tick(double Now, float Dt, const FWorldView& View, TArray<FEvent>& Out)
	{
		const double T0 = FPlatformTime::Seconds();
		Clock = Now;
		Dt = FMath::Clamp(Dt, 0.f, 0.25f);
		if (!L)
		{
			return;
		}
		for (FVessel& V : Vs)
		{
			Integrate(V, Dt, View);
			// a vessel through the ring: it leaves the system
			if (V.State == EVState::GateOut && L->GateNode != INDEX_NONE)
			{
				const FNode& G = L->Nodes[L->GateNode];
				if (FVector::Dist(V.Pos, G.Pos) < 700.0 || FVector::DotProduct(V.Pos - G.Pos, G.Att.GetForwardVector()) < 200.0)
				{
					SetState(V, EVState::Away);
					V.ReturnAt = Now + Rng.FRandRange(240.f, 720.f);
					V.Vel = FVector::ZeroVector;
					++St.GateOutTotal;
					FEvent E;
					E.Kind = EEventKind::GatePulse;
					E.At = G.Pos;
					E.Vessel = V.Id;
					Out.Add(E);
				}
			}
		}
		TickPatrols(Dt, Now, View);
		ThinkAcc += Dt;
		if (ThinkAcc >= SpThinkEvery)
		{
			ThinkDt = ThinkAcc;
			ThinkAcc = 0.f;
			// the world as the traffic sees it: danger first (a few times a second at most), then each vessel's decisions, then the Gate
			ThinkDanger(Now, View, Out);
			for (FVessel& V : Vs)
			{
				Think(V, Now, View, Out);
			}
			ThinkGate(Now, View, Out);
			RebuildStats();                                  // (the counts the console and the bench read: a few dozen vessels, five times a second)
		}
		St.TickMs += (FPlatformTime::Seconds() - T0) * 1000.0;
		St.TickMsMax = FMath::Max(St.TickMsMax, (FPlatformTime::Seconds() - T0) * 1000.0);
		++St.Ticks;
	}

	void FTraffic::Warmup(double Seconds, double Step)
	{
		FWorldView Quiet;
		TArray<FEvent> Dump;
		for (double T = 0.0; T < Seconds; T += Step)
		{
			Tick(Clock + Step, (float)Step, Quiet, Dump);
			Dump.Reset();
		}
		St.TickMs = 0.0;
		St.TickMsMax = 0.0;
		St.Ticks = 0;
		St.GateOutTotal = St.GateInTotal = St.DockedTotal = St.DepartedTotal = 0;
	}

	void FTraffic::RebuildStats()
	{
		FTrafficStats Keep = St;
		for (int32& N : St.ByState) { N = 0; }
		St.Vessels = Vs.Num();
		St.QueueGate = 0;
		St.Docked = St.InFlight = St.Away = St.Alerted = 0;
		for (const FVessel& V : Vs)
		{
			++St.ByState[(int32)V.State];
			St.Docked += V.State == EVState::Docked ? 1 : 0;
			St.Away += V.State == EVState::Away ? 1 : 0;
			St.InFlight += (V.State != EVState::Docked && V.State != EVState::Away) ? 1 : 0;
			St.Alerted += V.Alert > 0 ? 1 : 0;
			St.QueueGate += (V.State == EVState::Holding && L && V.Node == L->GateNode) ? 1 : 0;
		}
		St.MaxQueue = FMath::Max(Keep.MaxQueue, (float)St.QueueGate);
	}

	FString FTraffic::Describe() const
	{
		FTraffic* Self = const_cast<FTraffic*>(this);
		Self->RebuildStats();
		FString S = FString::Printf(TEXT("%d vessels: %d docked, %d under way, %d beyond the Gate, %d in the Gate's queue, %d alerted | alert %d | gate: %d out, %d in | berths: %d dockings, %d departures | maydays %d | tick %.4f ms avg (max %.3f)"),
		                            St.Vessels, St.Docked, St.InFlight, St.Away, St.QueueGate, St.Alerted, SystemAlert, St.GateOutTotal, St.GateInTotal, St.DockedTotal, St.DepartedTotal, St.Maydays,
		                            St.Ticks ? St.TickMs / St.Ticks : 0.0, St.TickMsMax);
		return S;
	}
}
