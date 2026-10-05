// ASTRA — ABBORDAGGI: the plan as soldiers see it (docs/ABBORDAGGI.md). See AstraBoardMap.h.

#include "AstraBoardMap.h"

namespace
{
	constexpr float BoardOpenClearCm = 310.f;      // the clear width of a corridor inside its 4 m module
	constexpr float BoardSlotBeyondCm = 55.f;      // how far past the opening's edge a man waits, along the wall
	constexpr float BoardSlotIntoCm = 75.f;        // and how far into the room or corridor
	constexpr float BoardSeeStepCm = 25.f;         // the line of sight is tested this far apart
	constexpr float BoardSeeMaxCm = 9000.f;        // nobody sees farther than this inside a ship
	constexpr float BoardApertureSlackCm = 25.f;

	FVector2D BoardUnit2D(const FVector2D& V)
	{
		const double L = V.Size();
		return L > 1.0e-6 ? V / L : FVector2D(1.0, 0.0);
	}

	/** Where the two boxes meet, if they share a face (within the walls' thickness): the face's middle on the floor, the unit normal from A to B, the unit
	 *  direction along the face and its length (cm). */
	bool BoardSharedFace(const FBox& A, const FBox& B, FVector& OutPos, FVector2D& OutNormal, FVector2D& OutAlong, float& OutLen)
	{
		constexpr double Tol = 60.0;
		auto Overlap = [](double A0, double A1, double B0, double B1, double& Lo, double& Hi)
		{
			Lo = FMath::Max(A0, B0);
			Hi = FMath::Min(A1, B1);
			return Hi - Lo > 10.0;
		};
		double Lo, Hi;
		const double FloorZ = FMath::Max(A.Min.Z, B.Min.Z);
		if (Overlap(A.Min.Y, A.Max.Y, B.Min.Y, B.Max.Y, Lo, Hi))
		{
			if (FMath::Abs(A.Max.X - B.Min.X) <= Tol)
			{
				OutPos = FVector(0.5 * (A.Max.X + B.Min.X), 0.5 * (Lo + Hi), FloorZ);
				OutNormal = FVector2D(1.0, 0.0);
				OutAlong = FVector2D(0.0, 1.0);
				OutLen = (float)(Hi - Lo);
				return true;
			}
			if (FMath::Abs(B.Max.X - A.Min.X) <= Tol)
			{
				OutPos = FVector(0.5 * (B.Max.X + A.Min.X), 0.5 * (Lo + Hi), FloorZ);
				OutNormal = FVector2D(-1.0, 0.0);
				OutAlong = FVector2D(0.0, 1.0);
				OutLen = (float)(Hi - Lo);
				return true;
			}
		}
		if (Overlap(A.Min.X, A.Max.X, B.Min.X, B.Max.X, Lo, Hi))
		{
			if (FMath::Abs(A.Max.Y - B.Min.Y) <= Tol)
			{
				OutPos = FVector(0.5 * (Lo + Hi), 0.5 * (A.Max.Y + B.Min.Y), FloorZ);
				OutNormal = FVector2D(0.0, 1.0);
				OutAlong = FVector2D(1.0, 0.0);
				OutLen = (float)(Hi - Lo);
				return true;
			}
			if (FMath::Abs(B.Max.Y - A.Min.Y) <= Tol)
			{
				OutPos = FVector(0.5 * (Lo + Hi), 0.5 * (B.Max.Y + A.Min.Y), FloorZ);
				OutNormal = FVector2D(0.0, -1.0);
				OutAlong = FVector2D(1.0, 0.0);
				OutLen = (float)(Hi - Lo);
				return true;
			}
		}
		return false;
	}

	FVector BoardClampIn(const FBox& B, const FVector& P, float Margin)
	{
		FVector Q = P;
		if (B.Max.X - B.Min.X > 2.0 * Margin) { Q.X = FMath::Clamp(Q.X, B.Min.X + Margin, B.Max.X - Margin); }
		else { Q.X = 0.5 * (B.Min.X + B.Max.X); }
		if (B.Max.Y - B.Min.Y > 2.0 * Margin) { Q.Y = FMath::Clamp(Q.Y, B.Min.Y + Margin, B.Max.Y - Margin); }
		else { Q.Y = 0.5 * (B.Min.Y + B.Max.Y); }
		return Q;
	}
}

// ================================================================================================================== building

bool FAstraBoardMap::Build(TSharedRef<const FAstraDamageMap> InSrc)
{
	Src = InSrc;
	Comps.Reset();
	Portals.Reset();
	Slots.Reset();
	DoorPortal.Init(INDEX_NONE, Src->Doors.Num());
	Comps.SetNum(Src->Comps.Num());
	for (int32 i = 0; i < Src->Comps.Num(); ++i)
	{
		const FAstraDmgComp& C = Src->Comps[i];
		FBoardComp& B = Comps[i];
		B.Box = C.Box;
		B.Deck = C.Deck;
		B.Section = C.Section;
		B.bCorridor = C.bCorridor;
		B.bHall = C.bHall;
		B.Kind = C.Kind;
	}
	MakePortals();
	MakeSlots();
	return Comps.Num() > 0;
}

void FAstraBoardMap::MakePortals()
{
	TSet<uint64> Seen;
	const FAstraDamageMap& M = *Src;
	for (int32 a = 0; a < M.Comps.Num(); ++a)
	{
		for (const FAstraDmgLink& L : M.Comps[a].Links)
		{
			const int32 b = L.To;
			if (!M.Comps.IsValidIndex(b) || b == a)
			{
				continue;
			}
			const int32 Lo = FMath::Min(a, b), Hi = FMath::Max(a, b);
			const uint64 Key = ((uint64)Lo << 32) | (uint32)Hi;
			const uint64 KeyK = Key ^ ((uint64)(uint8)L.Kind << 60) ^ ((uint64)(uint32)(L.Door + 1) << 20);
			if (Seen.Contains(KeyK))
			{
				continue;
			}
			Seen.Add(KeyK);
			FBoardPortal P;
			P.A = Lo;
			P.B = Hi;
			const FBox& BA = M.Comps[Lo].Box;
			const FBox& BB = M.Comps[Hi].Box;
			switch (L.Kind)
			{
			case FAstraDmgLink::EKind::Door:
			case FAstraDmgLink::EKind::Blast:
			{
				const FAstraDmgDoor& D = M.Doors[L.Door];
				P.Kind = L.Kind == FAstraDmgLink::EKind::Blast ? FBoardPortal::EKind::Blast : FBoardPortal::EKind::Door;
				P.Door = L.Door;
				P.Pos = D.PosCm;
				P.Pos.Z = FMath::Max(BA.Min.Z, BB.Min.Z);
				P.PosB = P.Pos;
				const double Yaw = FMath::DegreesToRadians((double)D.Yaw);
				P.Along = FVector2D(FMath::Sin(Yaw), FMath::Cos(Yaw));
				P.Normal = FVector2D(FMath::Cos(Yaw), -FMath::Sin(Yaw));
				P.Half = FMath::Max(60.f, D.WidthM * 50.f);
				break;
			}
			case FAstraDmgLink::EKind::Open:
			{
				FVector Pos;
				FVector2D N, Al;
				float Len = 0.f;
				if (BoardSharedFace(BA, BB, Pos, N, Al, Len))
				{
					P.Kind = FBoardPortal::EKind::Open;
					P.Pos = Pos;
					P.PosB = Pos;
					P.Normal = N;
					P.Along = Al;
					P.Half = 0.5f * FMath::Min(Len, BoardOpenClearCm);
				}
				else
				{
					// the graph joined them but their boxes do not meet (a stretch of wall in between): the opening is where the graph says, and as wide as a corridor
					P.Kind = FBoardPortal::EKind::Open;
					P.Pos = L.AtCm;
					P.Pos.Z = FMath::Max(BA.Min.Z, BB.Min.Z);
					P.PosB = P.Pos;
					const FVector2D D = BoardUnit2D(FVector2D(BB.GetCenter().X - BA.GetCenter().X, BB.GetCenter().Y - BA.GetCenter().Y));
					P.Normal = FMath::Abs(D.X) >= FMath::Abs(D.Y) ? FVector2D(D.X > 0 ? 1.0 : -1.0, 0.0) : FVector2D(0.0, D.Y > 0 ? 1.0 : -1.0);
					P.Along = FVector2D(-P.Normal.Y, P.Normal.X);
					P.Half = 0.5f * BoardOpenClearCm;
				}
				break;
			}
			case FAstraDmgLink::EKind::Stair:
			case FAstraDmgLink::EKind::Lift:
			{
				P.Kind = L.Kind == FAstraDmgLink::EKind::Stair ? FBoardPortal::EKind::Stair : FBoardPortal::EKind::Lift;
				P.Pos = BoardClampIn(BA, L.AtCm, 90.f);
				P.Pos.Z = BA.Min.Z;
				P.PosB = BoardClampIn(BB, L.AtCm, 90.f);
				P.PosB.Z = BB.Min.Z;
				P.Normal = FVector2D(0.0, 1.0);
				P.Along = FVector2D(1.0, 0.0);
				P.Half = 100.f;
				P.ExtraCost = P.Kind == FBoardPortal::EKind::Stair ? 700.f : 2200.f;
				break;
			}
			}
			// the normal points from A to B (the damage map's door yaw does not say which way is which)
			const FVector2D Ctr(BB.GetCenter().X - BA.GetCenter().X, BB.GetCenter().Y - BA.GetCenter().Y);
			if (!P.bVertical() && FVector2D::DotProduct(P.Normal, Ctr) < 0.0 && !Ctr.IsNearlyZero(1.0))
			{
				P.Normal = -P.Normal;
			}
			const int32 Idx = Portals.Add(P);
			Comps[Lo].Portals.Add(Idx);
			Comps[Hi].Portals.Add(Idx);
			if (P.Door != INDEX_NONE && DoorPortal.IsValidIndex(P.Door))
			{
				DoorPortal[P.Door] = Idx;
			}
		}
	}
}

void FAstraBoardMap::MakeSlots()
{
	for (int32 pi = 0; pi < Portals.Num(); ++pi)
	{
		const FBoardPortal& P = Portals[pi];
		if (P.bVertical())
		{
			continue;
		}
		for (int32 Side = 0; Side < 2; ++Side)
		{
			const int32 C = Side == 0 ? P.A : P.B;
			// a compartment that is no wider than the opening (a corridor going on, the cross link of a junction) has no corner beside it; a doorway
			// in a long wall, or the mouth of a junction in the long corridor, has two
			const FBox& CB = Comps[C].Box;
			const double Across = FMath::Abs(P.Along.X) > 0.5 ? CB.Max.X - CB.Min.X : CB.Max.Y - CB.Min.Y;
			if (2.0 * P.Half + 2.0 * BoardSlotBeyondCm + 40.0 >= Across)
			{
				continue;
			}
			const FVector2D Into = Side == 0 ? -P.Normal : P.Normal;     // from the opening into this compartment
			for (int32 S = -1; S <= 1; S += 2)
			{
				const FVector2D Lat = P.Along * (double)S;
				FBoardSlot Sl;
				Sl.Comp = C;
				Sl.Portal = pi;
				const FVector Floor(P.Pos.X, P.Pos.Y, Comps[C].FloorZ());
				Sl.Pos = Floor + FVector(Lat.X * (P.Half + BoardSlotBeyondCm) + Into.X * BoardSlotIntoCm, Lat.Y * (P.Half + BoardSlotBeyondCm) + Into.Y * BoardSlotIntoCm, 0.0);
				Sl.Peek = Floor + FVector(Lat.X * (P.Half * 0.3f) + Into.X * 60.0, Lat.Y * (P.Half * 0.3f) + Into.Y * 60.0, 0.0);
				Sl.Pos = BoardClampIn(Comps[C].Box, Sl.Pos, 35.f);
				Sl.Peek = BoardClampIn(Comps[C].Box, Sl.Peek, 35.f);
				Sl.Pos.Z = Sl.Peek.Z = Comps[C].FloorZ();
				Sl.Out = -Into;
				if (FVector::Dist2D(Sl.Pos, Sl.Peek) < 55.0)
				{
					continue;
				}
				Comps[C].Slots.Add(Slots.Add(Sl));
			}
		}
	}
}

// ================================================================================================================== sight

bool FAstraBoardMap::Visible(const FVector& A, const FVector& B, const FBoardDoors* Doors, int32 ForceOpenDoor) const
{
	const double Dist = FVector::Dist(A, B);
	if (Dist > BoardSeeMaxCm)
	{
		return false;
	}
	int32 Cur = CompAt(A);
	if (Cur == INDEX_NONE)
	{
		return false;
	}
	if (Dist < 5.0)
	{
		return true;
	}
	const int32 N = FMath::Max(1, FMath::CeilToInt((float)(Dist / BoardSeeStepCm)));
	for (int32 i = 1; i <= N; ++i)
	{
		const FVector P = FMath::Lerp(A, B, (double)i / N);
		int32 C = Src->CompartmentAt(P, 0.f);
		if (C == Cur)
		{
			continue;
		}
		if (C == INDEX_NONE)
		{
			C = CompAt(P);
			if (C == INDEX_NONE)
			{
				return false;
			}
			if (C == Cur)
			{
				continue;
			}
		}
		// a face: through an opening that is open
		bool bPass = false;
		for (const int32 Pi : Comps[Cur].Portals)
		{
			const FBoardPortal& Po = Portals[Pi];
			if (Po.Other(Cur) != C || Po.bVertical())
			{
				continue;
			}
			if (FMath::Abs(FVector2D::DotProduct(FVector2D(P.X - Po.Pos.X, P.Y - Po.Pos.Y), Po.Along)) > Po.Half + BoardApertureSlackCm)
			{
				continue;
			}
			if (Po.bDoor() && Po.Door != ForceOpenDoor && Doors && !Doors->IsOpen(Po.Door))
			{
				continue;
			}
			bPass = true;
			break;
		}
		if (!bPass)
		{
			return false;
		}
		Cur = C;
	}
	return true;
}

void FAstraBoardMap::FightingSlots(int32 Comp, const FVector& Enemy, const FVector& From, const FBoardDoors* Doors, TArray<int32>& Out) const
{
	Out.Reset();
	if (!Comps.IsValidIndex(Comp))
	{
		return;
	}
	constexpr float Eye = 150.f;
	TArray<TPair<float, int32>, TInlineAllocator<16>> Good;
	for (const int32 Si : Comps[Comp].Slots)
	{
		const FBoardSlot& S = Slots[Si];
		const int32 Door = Portals[S.Portal].Door;
		if (Visible(S.Pos + FVector(0, 0, Eye), Enemy, Doors, INDEX_NONE))
		{
			continue;                            // he sees the corner: it is no cover
		}
		if (!Visible(S.Peek + FVector(0, 0, Eye), Enemy, Doors, Door))
		{
			continue;                            // and from the step out he cannot see him
		}
		Good.Emplace((float)FVector::Dist(S.Pos, From), Si);
	}
	Good.Sort([](const TPair<float, int32>& A, const TPair<float, int32>& B) { return A.Key < B.Key; });
	for (const TPair<float, int32>& G : Good)
	{
		Out.Add(G.Value);
		if (Out.Num() >= 8)
		{
			break;
		}
	}
}

// ================================================================================================================== routes

namespace
{
	struct FBoardNode
	{
		int32 Portal = INDEX_NONE;     // INDEX_NONE: the goal
		int32 Into = INDEX_NONE;       // the compartment it brings to
		float G = 0.f;
		float F = 0.f;
		int32 Parent = INDEX_NONE;     // index in the node list
	};
}

static bool BoardAStar(const FAstraBoardMap& Map, const FVector& From, const FVector& To, const FBoardRouteOptions& Opt, TArray<int32>& OutPortals, TArray<int32>& OutInto, float& OutLen)
{
	const TArray<FBoardPortal>& Portals = Map.GetPortals();
	const TArray<FBoardComp>& Comps = Map.GetComps();
	const int32 Cs = Map.CompAt(From, 60.f), Cg = Map.CompAt(To, 60.f);
	if (Cs == INDEX_NONE || Cg == INDEX_NONE)
	{
		return false;
	}
	OutPortals.Reset();
	OutInto.Reset();
	if (Cs == Cg)
	{
		OutLen = (float)FVector::Dist(From, To);
		return true;
	}
	// the search's buffers are kept between searches (a fight asks for a great many routes)
	thread_local TArray<FBoardNode> Nodes;
	thread_local TArray<int32> Open;                       // heap of node indices by F
	thread_local TArray<float> Best;                       // by (portal, side it brings into): the best G so far
	Nodes.Reset();
	Open.Reset();
	Best.SetNumUninitialized(Portals.Num() * 2, EAllowShrinking::No);
	for (float& B : Best)
	{
		B = TNumericLimits<float>::Max();
	}
	auto Key = [&Portals](int32 Portal, int32 Into) { return Portal * 2 + (Portals[Portal].B == Into ? 1 : 0); };
	auto Less = [](int32 A, int32 B) { return Nodes[A].F < Nodes[B].F; };
	auto Cost = [&](const FBoardPortal& P, int32 Pi) -> float
	{
		float C = P.ExtraCost;
		if (Opt.PortalPenalty && Opt.PortalPenalty->IsValidIndex(Pi))
		{
			C += (*Opt.PortalPenalty)[Pi];
		}
		return C;
	};
	auto Passable = [&](const FBoardPortal& P, float& Extra) -> bool
	{
		Extra = 0.f;
		if (P.Kind == FBoardPortal::EKind::Lift || (P.Kind == FBoardPortal::EKind::Stair && !Opt.bStairs))
		{
			return false;
		}
		if (P.bDoor() && Opt.Doors && Opt.Doors->IsSealed(P.Door))
		{
			if (!Opt.bThroughSealed && !(Opt.bThroughClosed && Opt.Doors->ClosedBySide(P.Door) >= 0))
			{
				return false;
			}
			Extra = Opt.SealedCost;
		}
		return true;
	};
	auto Push = [&](int32 Portal, int32 Into, float G, const FVector& At, int32 Parent)
	{
		FBoardNode N;
		N.Portal = Portal;
		N.Into = Into;
		N.G = G;
		N.F = G + (float)FVector::Dist(At, To);
		N.Parent = Parent;
		const int32 Idx = Nodes.Add(N);
		Open.HeapPush(Idx, Less);
	};
	// out of the start compartment through each of its portals
	for (const int32 Pi : Comps[Cs].Portals)
	{
		const FBoardPortal& P = Portals[Pi];
		float Extra;
		if (!Passable(P, Extra))
		{
			continue;
		}
		const int32 Into = P.Other(Cs);
		const float G = (float)FVector::Dist(From, P.PosIn(Cs)) + Extra + Cost(P, Pi);
		const int32 K = Key(Pi, Into);
		if (Best[K] <= G)
		{
			continue;
		}
		Best[K] = G;
		Push(Pi, Into, G, P.PosIn(Into), INDEX_NONE);
	}
	int32 GoalNode = INDEX_NONE;
	int32 Pops = 0;
	while (Open.Num() && Pops++ < 40000)
	{
		int32 Cur;
		Open.HeapPop(Cur, Less, EAllowShrinking::No);
		const FBoardNode Node = Nodes[Cur];
		if (Node.Portal == INDEX_NONE)
		{
			GoalNode = Cur;
			break;
		}
		const FVector Arrive = Portals[Node.Portal].PosIn(Node.Into);
		if (Node.Into == Cg)
		{
			// the goal is in this compartment: a straight line to it
			FBoardNode G;
			G.Portal = INDEX_NONE;
			G.Into = Cg;
			G.G = Node.G + (float)FVector::Dist(Arrive, To);
			G.F = G.G;
			G.Parent = Cur;
			Open.HeapPush(Nodes.Add(G), Less);
		}
		for (const int32 Pi : Comps[Node.Into].Portals)
		{
			if (Pi == Node.Portal)
			{
				continue;
			}
			const FBoardPortal& P = Portals[Pi];
			float Extra;
			if (!Passable(P, Extra))
			{
				continue;
			}
			const int32 Into = P.Other(Node.Into);
			const float G = Node.G + (float)FVector::Dist(Arrive, P.PosIn(Node.Into)) + Extra + Cost(P, Pi);
			const int32 K = Key(Pi, Into);
			if (Best[K] <= G)
			{
				continue;
			}
			Best[K] = G;
			Push(Pi, Into, G, P.PosIn(Into), Cur);
		}
	}
	if (GoalNode == INDEX_NONE)
	{
		return false;
	}
	OutLen = Nodes[GoalNode].G;
	TArray<int32> Chain;
	for (int32 N = Nodes[GoalNode].Parent; N != INDEX_NONE; N = Nodes[N].Parent)
	{
		Chain.Add(N);
	}
	for (int32 i = Chain.Num() - 1; i >= 0; --i)
	{
		OutPortals.Add(Nodes[Chain[i]].Portal);
		OutInto.Add(Nodes[Chain[i]].Into);
	}
	return true;
}

bool FAstraBoardMap::Route(const FVector& From, const FVector& To, TArray<FVector>& Out, const FBoardRouteOptions& Opt, float* OutMetres, TArray<int32>* OutComps) const
{
	TArray<int32> Ps, Into;
	float Len = 0.f;
	if (!BoardAStar(*this, From, To, Opt, Ps, Into, Len))
	{
		return false;
	}
	Out.Reset();
	Out.Add(From);
	if (OutComps)
	{
		OutComps->Reset();
		OutComps->Add(CompAt(From, 60.f));
	}
	for (int32 i = 0; i < Ps.Num(); ++i)
	{
		const FBoardPortal& P = Portals[Ps[i]];
		const int32 Left = P.Other(Into[i]);
		Out.Add(P.PosIn(Left));
		if (P.bVertical())
		{
			Out.Add(P.PosIn(Into[i]));
		}
		if (OutComps)
		{
			OutComps->Add(Into[i]);
			if (P.bVertical())
			{
				OutComps->Add(Into[i]);
			}
		}
	}
	Out.Add(To);
	if (OutMetres)
	{
		*OutMetres = Len / 100.f;
	}
	return true;
}

bool FAstraBoardMap::RoutePortals(const FVector& From, const FVector& To, TArray<int32>& OutPortals, const FBoardRouteOptions& Opt) const
{
	TArray<int32> Into;
	float Len = 0.f;
	return BoardAStar(*this, From, To, Opt, OutPortals, Into, Len);
}

int32 FAstraBoardMap::NearestPortal(int32 Comp, const FVector& P) const
{
	int32 Best = INDEX_NONE;
	double BestD = TNumericLimits<double>::Max();
	if (Comps.IsValidIndex(Comp))
	{
		for (const int32 Pi : Comps[Comp].Portals)
		{
			const double D = FVector::DistSquared(Portals[Pi].PosIn(Comp), P);
			if (D < BestD)
			{
				BestD = D;
				Best = Pi;
			}
		}
	}
	return Best;
}

FVector FAstraBoardMap::CentreOf(int32 Comp) const
{
	if (!Comps.IsValidIndex(Comp))
	{
		return FVector::ZeroVector;
	}
	const FBox& B = Comps[Comp].Box;
	return FVector(0.5 * (B.Min.X + B.Max.X), 0.5 * (B.Min.Y + B.Max.Y), B.Min.Z);
}

FVector FAstraBoardMap::Inset(int32 Comp, const FVector& P, float MarginCm) const
{
	if (!Comps.IsValidIndex(Comp))
	{
		return P;
	}
	FVector Q = BoardClampIn(Comps[Comp].Box, P, MarginCm);
	Q.Z = Comps[Comp].Box.Min.Z;
	// and out of the props the room is dressed with: a man's width off their faces. A spot inside one is moved to the nearest spot that is in the room and clear of every prop: looked for on rings of growing
	// size round it (twenty centimetres to a ring, three metres at most: a corner crowded with props still has its way out)
	const TArrayView<const FBox2D> Blocks = BlocksOf(Comp);
	if (Blocks.Num() > 0)
	{
		const FBox& Box = Comps[Comp].Box;
		const double Pad = FMath::Min<double>(MarginCm, 40.0);
		const auto Inside = [&](const FVector& V) -> bool
		{
			for (const FBox2D& K : Blocks)
			{
				if (V.X > K.Min.X - Pad && V.X < K.Max.X + Pad && V.Y > K.Min.Y - Pad && V.Y < K.Max.Y + Pad)
				{
					return true;
				}
			}
			return false;
		};
		if (Inside(Q))
		{
			bool bFound = false;
			FVector Best = Q;
			for (int32 Ring = 1; Ring <= 15 && !bFound; ++Ring)
			{
				const double R = Ring * 20.0;
				double BestD = TNumericLimits<double>::Max();
				for (int32 i = -Ring; i <= Ring; ++i)
				{
					for (int32 k = 0; k < 4; ++k)
					{
						const double A = i * 20.0;
						const FVector Cand = k == 0 ? FVector(Q.X + A, Q.Y - R, Q.Z) : (k == 1 ? FVector(Q.X + A, Q.Y + R, Q.Z) : (k == 2 ? FVector(Q.X - R, Q.Y + A, Q.Z) : FVector(Q.X + R, Q.Y + A, Q.Z)));
						FVector C = BoardClampIn(Box, Cand, MarginCm);
						C.Z = Box.Min.Z;
						if (Inside(C))
						{
							continue;
						}
						const double D = FVector::DistSquared(C, Q);
						if (D < BestD)
						{
							BestD = D;
							Best = C;
							bFound = true;
						}
					}
				}
			}
			Q = Best;
		}
	}
	return Q;
}

void FAstraBoardMap::SetBlocks(TArray<FBox2D>&& All, TArray<int32>&& First)
{
	BlockAll = MoveTemp(All);
	BlockFirst = MoveTemp(First);
}

TArrayView<const FBox2D> FAstraBoardMap::BlocksOf(int32 Comp) const
{
	if (!BlockFirst.IsValidIndex(Comp + 1))
	{
		return TArrayView<const FBox2D>();
	}
	return TArrayView<const FBox2D>(BlockAll.GetData() + BlockFirst[Comp], BlockFirst[Comp + 1] - BlockFirst[Comp]);
}
