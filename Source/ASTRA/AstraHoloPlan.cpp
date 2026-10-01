// ASTRA — what the holographic tactical plot shows of a fleet battle (AstraHoloPlan.h, docs/SCALA.md).

#include "AstraHoloPlan.h"

namespace AstraHoloPlan
{
	namespace
	{
		// (the table's own colours: AstraHoloTable.cpp keeps its copies for the rest of what it draws)
		const FLinearColor ColAstra(0.22f, 0.72f, 1.f);
		const FLinearColor ColAquila(0.62f, 0.95f, 1.f);
		const FLinearColor ColHostile(1.f, 0.2f, 0.08f);
		const FLinearColor ColHolding(1.f, 0.62f, 0.12f);
		const FLinearColor ColNeutral(0.95f, 0.88f, 0.45f);
		const FLinearColor ColUnknown(0.62f, 0.66f, 0.7f);

		constexpr float LabelGap = 1.2f;          // cm between a label and what it names
		constexpr float LabelMargin = 0.5f;       // cm between two labels
		constexpr int32 MaxMust = 8;              // labels that are placed whatever the crowd
		constexpr int32 MaxIndividual = 8;        // a crowd's named ships besides the ones that must be
		constexpr int32 MaxFlightTags = 6;
		constexpr int32 DenseShips = 10;          // more ships than this (besides the Aquila) and the groups are tagged
		constexpr int32 MinGroup = 3;             // ships that make a group

		uint8 KeyOf(const FAstraHoloBlip& B)
		{
			return B.bUnknown ? 2 : (B.Side == EAstraSide::Astra ? 0 : ((B.bHostile || B.Side == EAstraSide::Mandate) ? 1 : 3));
		}

		const TCHAR* KeyName(uint8 Key)
		{
			static const TCHAR* const N[4] = {TEXT("ASTRA"), TEXT("MANDATE"), TEXT("UNKNOWN"), TEXT("NEUTRAL")};
			return N[FMath::Min<int32>(Key, 3)];
		}

		FLinearColor KeyColor(uint8 Key)
		{
			return Key == 0 ? ColAstra : (Key == 1 ? ColHostile : (Key == 2 ? ColUnknown : ColNeutral));
		}

		/** A label's box from its text: the world size of the text is a character's height (cm); lines are joined with <br>. */
		FVector2D BoxOf(const FString& Text, float Size, float CharW)
		{
			int32 Longest = 0, Lines = 1;
			int32 Run = 0;
			for (int32 i = 0; i < Text.Len(); ++i)
			{
				if (Text[i] == TEXT('<') && Text.Mid(i, 4) == TEXT("<br>"))
				{
					Longest = FMath::Max(Longest, Run);
					Run = 0;
					++Lines;
					i += 3;
				}
				else
				{
					++Run;
				}
			}
			Longest = FMath::Max(Longest, Run);
			return FVector2D(Longest * Size * CharW, Lines * Size * 1.05f);
		}

		uint64 PairKey(int32 A, int32 B)
		{
			return A < B ? ((uint64)(uint32)A << 32) | (uint32)B : ((uint64)(uint32)B << 32) | (uint32)A;
		}

		int32 RootOf(TArray<int32>& Parent, int32 X)
		{
			while (Parent[X] != X)
			{
				Parent[X] = Parent[Parent[X]];
				X = Parent[X];
			}
			return X;
		}
	}

	void ViewBasis(const FParams& Par, FVector& OutRight, FVector& OutUp)
	{
		const FVector Us(0.f, 0.f, Par.PlaneHeight);
		const FVector ViewDir = (Us - Par.ViewerLocal).GetSafeNormal();
		OutRight = FVector::CrossProduct(FVector::UpVector, ViewDir).GetSafeNormal();
		if (OutRight.IsNearlyZero())
		{
			OutRight = FVector(0.f, 1.f, 0.f);          // looking straight down or up: any right will do
		}
		OutUp = FVector::CrossProduct(ViewDir, OutRight).GetSafeNormal();
		if (OutUp.Z < 0.f)
		{
			OutUp = -OutUp;
		}
	}

	FVector ViewerInPlotFrame(const FVector& ViewerRoot, float PlotRadius, float PlaneHeight, float MaxTilt, float& OutTiltDeg)
	{
		const FVector Centre(0.f, 0.f, PlaneHeight);
		const FVector ToViewer = ViewerRoot - Centre;
		const float Horiz = FVector2D(ToViewer.X, ToViewer.Y).Size();
		const float Elev = FMath::RadiansToDegrees(FMath::Atan2(ToViewer.Z, FMath::Max(Horiz, 1.f)));
		OutTiltDeg = FMath::Clamp(70.f - Elev, 0.f, MaxTilt) * FMath::Clamp((Horiz - PlotRadius - 50.f) / 200.f, 0.f, 1.f);
		const float Az = FMath::RadiansToDegrees(FMath::Atan2(ToViewer.Y, ToViewer.X));
		const FVector Towards = FRotator(0.f, Az, 0.f).Vector();
		const FQuat Q(FVector::CrossProduct(FVector::UpVector, Towards).GetSafeNormal(), FMath::DegreesToRadians(OutTiltDeg));
		const float Lift = FMath::Max(0.f, PlotRadius * FMath::Sin(FMath::DegreesToRadians(OutTiltDeg)) + 5.f - PlaneHeight);
		const FTransform Frame(Q, Centre - Q.RotateVector(Centre) + FVector(0.f, 0.f, Lift));
		return Frame.InverseTransformPosition(ViewerRoot);
	}

	float RadiusOf(const FParams& Par, float Km)
	{
		const float D0 = Par.RangeKm / 12.f;
		return Par.PlotRadius * FMath::Loge(1.f + Km / D0) / FMath::Loge(1.f + Par.RangeKm / D0);
	}

	FVector PointOf(const FParams& Par, const FVector& RelCm)
	{
		const float Km = RelCm.Size() / 100000.f;
		if (Km < 1e-4f)
		{
			return FVector(0, 0, Par.PlaneHeight);
		}
		FVector P = RelCm / RelCm.Size() * FMath::Min(RadiusOf(Par, Km), Par.PlotRadius);   // beyond the range: pinned to the rim
		P.Z = FMath::Clamp(P.Z, -Par.MaxDepth, Par.MaxDepth);
		return P + FVector(0, 0, Par.PlaneHeight);
	}

	FString RangeText(float Km)
	{
		return Km < 10.f ? FString::Printf(TEXT("%.1f km"), Km) : FString::Printf(TEXT("%.0f km"), Km);
	}

	FLinearColor ColorOf(const FAstraHoloBlip& B)
	{
		if (B.bPlayer) { return ColAquila; }
		if (B.bUnknown) { return ColUnknown; }
		if (B.Side == EAstraSide::Astra) { return ColAstra; }
		if (B.bHostile) { return B.bHoldFire ? ColHolding : ColHostile; }
		return B.Side == EAstraSide::Mandate ? ColHostile * 0.8f : ColNeutral;
	}

	// ------------------------------------------------------------------------------------------------------------------ the labels
	void PlaceLabels(const TArray<FAsk>& Asks, const TArray<FVector3f>& Obstacles, TArray<FGot>& Got)
	{
		Got.Reset();
		Got.SetNum(Asks.Num());
		TArray<int32> Order;
		Order.Reserve(Asks.Num());
		for (int32 i = 0; i < Asks.Num(); ++i)
		{
			Order.Add(i);
		}
		Order.StableSort([&Asks](int32 A, int32 B) { return Asks[A].Prio < Asks[B].Prio; });
		struct FRect { float X0, Y0, X1, Y1; };
		TArray<FRect> Placed;
		Placed.Reserve(Asks.Num());
		// how much of a candidate box is under the labels already put down and the icons (0: clear)
		const auto Cost = [&](const FRect& Bx, int32 Self) -> float
		{
			float C = 0.f;
			for (const FRect& P : Placed)
			{
				const float Ox = FMath::Min(Bx.X1, P.X1 + LabelMargin) - FMath::Max(Bx.X0, P.X0 - LabelMargin);
				const float Oy = FMath::Min(Bx.Y1, P.Y1 + LabelMargin) - FMath::Max(Bx.Y0, P.Y0 - LabelMargin);
				if (Ox > 0.f && Oy > 0.f)
				{
					C += Ox * Oy + 1.f;
				}
			}
			for (int32 k = 0; k < Obstacles.Num(); ++k)
			{
				if (k == Self)
				{
					continue;
				}
				const FVector3f& O = Obstacles[k];
				const float Dx = FMath::Max(Bx.X0 - O.X, FMath::Max(0.f, O.X - Bx.X1));
				const float Dy = FMath::Max(Bx.Y0 - O.Y, FMath::Max(0.f, O.Y - Bx.Y1));
				if (Dx * Dx + Dy * Dy < O.Z * O.Z)
				{
					C += O.Z * O.Z * 0.5f + 1.f;
				}
			}
			return C;
		};
		for (const int32 i : Order)
		{
			const FAsk& A = Asks[i];
			float BestCost = TNumericLimits<float>::Max();
			FVector2D BestOff = FVector2D::ZeroVector;
			int32 BestSlot = 0;
			bool bFound = false;
			const int32 Rings = A.bMust ? 5 : 2;           // (a label that must be shown goes out as far as it takes to find room: in a heap of ships that is a few rings)
			// the eight places round its thing, on a ring a label's height further out each time: slot = ring * 8 + which
			const auto PlaceOf = [&A](int32 Slot) -> FVector2D
			{
				const int32 Ring = Slot / 8;
				const float r = A.R + LabelGap + Ring * (A.H * 0.9f + 1.5f);
				const float d = r * 0.8f;
				switch (Slot % 8)
				{
				case 0: return FVector2D(0.f, r);                              // above
				case 1: return FVector2D(r + A.W * 0.5f, -A.H * 0.5f);         // right
				case 2: return FVector2D(-(r + A.W * 0.5f), -A.H * 0.5f);      // left
				case 3: return FVector2D(0.f, -(r + A.H));                     // below
				case 4: return FVector2D(d + A.W * 0.5f, d);                   // up and right
				case 5: return FVector2D(-(d + A.W * 0.5f), d);                // up and left
				case 6: return FVector2D(d + A.W * 0.5f, -(d + A.H));          // down and right
				default: return FVector2D(-(d + A.W * 0.5f), -(d + A.H));      // down and left
				}
			};
			const auto Try = [&](int32 Slot) -> bool
			{
				const FVector2D Off = PlaceOf(Slot);
				const float Cx = A.At.X + Off.X, Cy = A.At.Y + Off.Y;
				const FRect Bx{Cx - A.W * 0.5f, Cy, Cx + A.W * 0.5f, Cy + A.H};
				const float C = Cost(Bx, A.Self);
				if (C < BestCost)
				{
					BestCost = C;
					BestOff = Off;
					BestSlot = Slot;
				}
				return C <= 0.f;
			};
			if (A.Prefer >= 0 && A.Prefer < Rings * 8)
			{
				bFound = Try(A.Prefer);                                      // where it was, if that is still clear
			}
			for (int32 Slot = 0; Slot < Rings * 8 && !bFound; ++Slot)
			{
				bFound = Try(Slot);
			}
			FGot& G = Got[i];
			if (bFound || A.bMust)
			{
				// (a label that must be shown and has no clear place goes where it covers least)
				G.bShown = true;
				G.Offset = BestOff;
				G.Slot = BestSlot;
				G.bLeader = BestSlot >= 8;
				const float Cx = A.At.X + BestOff.X, Cy = A.At.Y + BestOff.Y;
				Placed.Add({Cx - A.W * 0.5f, Cy, Cx + A.W * 0.5f, Cy + A.H});
			}
		}
	}

	// ------------------------------------------------------------------------------------------------------------------ the plan
	void Make(const TArray<FAstraHoloBlip>& Blips, const FParams& Par, FState& State, FPlan& Out)
	{
		Out.Icons.Reset();
		for (TArray<FDot>& D : Out.CraftDots) { D.Reset(); }
		for (TArray<FDot>& D : Out.MissileDots) { D.Reset(); }
		Out.Blasts.Reset();
		Out.Labels.Reset();
		Out.Threats.Reset();
		Out.Clusters.Reset();
		Out.bDense = false;
		Out.Dropped = 0;

		// the viewer's picture plane: x to their right, y up
		FVector ViewRight, ViewUp;
		ViewBasis(Par, ViewRight, ViewUp);
		const auto Pic = [&](const FVector& P) { return FVector2D(FVector::DotProduct(P, ViewRight), FVector::DotProduct(P, ViewUp)); };

		// ---- what is on the plot
		TArray<int32> IconOfBlip;                        // by blip: its icon (-1: not a ship)
		IconOfBlip.Init(-1, Blips.Num());
		TMap<int32, TArray<int32>> Flights;              // squadron -> the blips of its craft within the range
		TMap<int32, int32> FlightLead;                   // squadron -> the blip that carries its name and mission
		int32 Ships = 0;
		for (int32 i = 0; i < Blips.Num(); ++i)
		{
			const FAstraHoloBlip& B = Blips[i];
			if (B.Kind == 2)
			{
				Out.Blasts.Add(i);
				continue;
			}
			const bool bBeyond = B.bBearingOnly || B.Rel.Size() / 100000.f > Par.RangeKm * 1.02f;
			if (B.Kind == 1)
			{
				if (!bBeyond)
				{
					FDot& D = Out.MissileDots[B.Side == EAstraSide::Astra ? 0 : 1].AddDefaulted_GetRef();
					D.P = PointOf(Par, B.Rel);
					D.Scale = 0.012f;
				}
				continue;
			}
			if (B.bCraft)
			{
				if (!bBeyond)
				{
					const int32 Slot = B.bUnknown ? 2 : (B.Side == EAstraSide::Astra ? 0 : (B.bHostile ? 1 : 2));
					FDot& D = Out.CraftDots[Slot].AddDefaulted_GetRef();
					D.P = PointOf(Par, B.Rel);
					D.Scale = FMath::Max(0.008f, 0.05f * B.Size);
					if (B.Squadron >= 0)
					{
						Flights.FindOrAdd(B.Squadron).Add(i);
						if (!B.bNoLabel)
						{
							FlightLead.Add(B.Squadron, i);
						}
					}
				}
				continue;
			}
			FIcon& Ic = Out.Icons.AddDefaulted_GetRef();
			Ic.Blip = i;
			Ic.P = PointOf(Par, B.bBearingOnly ? B.Rel.GetSafeNormal() * 1.0e12f : B.Rel);
			Ic.bBeyond = bBeyond;
			IconOfBlip[i] = Out.Icons.Num() - 1;
			Ships += B.bPlayer ? 0 : 1;
		}
		Out.bDense = Ships > DenseShips;
		// the icons: eighteen centimetres for a ship (twenty-two the Aquila), smaller as the crowd grows, so that a fleet is not a heap of arrowheads
		const float Shrink = Out.bDense ? FMath::Clamp(FMath::Sqrt((float)DenseShips / (float)Ships) * 1.25f, 0.5f, 1.f) : 1.f;
		for (FIcon& Ic : Out.Icons)
		{
			const FAstraHoloBlip& B = Blips[Ic.Blip];
			Ic.Size = (B.bPlayer ? 22.f : 18.f) * B.Size * (B.bPlayer ? 1.f : Shrink);
			Ic.Radius = 0.4f * Ic.Size;
		}

		// ---- who fires on us (the nearest dozen get their line; the nearest six keep their names whatever the crowd)
		TArray<int32> Firing;
		for (int32 k = 0; k < Out.Icons.Num(); ++k)
		{
			const FAstraHoloBlip& B = Blips[Out.Icons[k].Blip];
			if (B.bFiringAtUs && !B.bBearingOnly)
			{
				Firing.Add(k);
			}
		}
		Firing.Sort([&](int32 A, int32 B) { return Blips[Out.Icons[A].Blip].RangeKm < Blips[Out.Icons[B].Blip].RangeKm; });
		for (int32 n = 0; n < Firing.Num(); ++n)
		{
			if (n < 12)
			{
				Out.Threats.Add(Firing[n]);
			}
			if (n < 6)
			{
				Out.Icons[Firing[n]].bMust = true;
			}
		}
		for (FIcon& Ic : Out.Icons)
		{
			const FAstraHoloBlip& B = Blips[Ic.Blip];
			Ic.bMust |= B.bPlayer || B.bTargeted;
		}

		// ---- the ships that fly together, when there are many
		TArray<int32> ClusterOfIcon;
		ClusterOfIcon.Init(-1, Out.Icons.Num());
		TSet<uint64> TogetherNow;
		if (Out.bDense)
		{
			const float LinkKm = FMath::Clamp(0.12f * Par.RangeKm, 2.5f, 8.f);
			TArray<int32> Members;
			for (int32 k = 0; k < Out.Icons.Num(); ++k)
			{
				const FAstraHoloBlip& B = Blips[Out.Icons[k].Blip];
				if (!B.bPlayer && !B.bBearingOnly && !Out.Icons[k].bBeyond)
				{
					Members.Add(k);
				}
			}
			TArray<int32> Parent;
			Parent.SetNumUninitialized(Out.Icons.Num());
			for (int32 k = 0; k < Parent.Num(); ++k)
			{
				Parent[k] = k;
			}
			for (int32 a = 0; a < Members.Num(); ++a)
			{
				const FAstraHoloBlip& A = Blips[Out.Icons[Members[a]].Blip];
				for (int32 b = a + 1; b < Members.Num(); ++b)
				{
					const FAstraHoloBlip& Bb = Blips[Out.Icons[Members[b]].Blip];
					if (KeyOf(A) != KeyOf(Bb))
					{
						continue;
					}
					const uint64 Pk = PairKey(A.Id, Bb.Id);
					const float Link = State.Together.Contains(Pk) ? LinkKm * 1.3f : LinkKm;      // (they stay together a little further apart: no flicker at the edge)
					if (FVector::Dist(A.Rel, Bb.Rel) / 100000.0 <= Link)
					{
						TogetherNow.Add(Pk);
						Parent[RootOf(Parent, Members[a])] = RootOf(Parent, Members[b]);
					}
				}
			}
			TMap<int32, int32> RootToCluster;
			for (const int32 k : Members)
			{
				RootToCluster.FindOrAdd(RootOf(Parent, k), 0) += 1;
			}
			TMap<int32, int32> Made;
			for (const int32 k : Members)
			{
				const int32 Root = RootOf(Parent, k);
				if (RootToCluster[Root] < MinGroup)
				{
					continue;
				}
				int32* Ci = Made.Find(Root);
				if (!Ci)
				{
					FCluster C;
					C.Key = KeyOf(Blips[Out.Icons[k].Blip]);
					Ci = &Made.Add(Root, Out.Clusters.Add(C));
				}
				Out.Clusters[*Ci].Icons.Add(k);
				ClusterOfIcon[k] = *Ci;
			}
			for (FCluster& C : Out.Clusters)
			{
				FVector Sum = FVector::ZeroVector;
				for (const int32 k : C.Icons)
				{
					Sum += Out.Icons[k].P;
				}
				C.Centre = Sum / (double)C.Icons.Num();
			}
		}
		State.Together = MoveTemp(TogetherNow);

		// ---- the labels asked for
		struct FWant { FLabel L; FAsk A; int32 Key = 0; };
		TArray<FWant> Wants;
		const auto Ask = [&](FLabel&& L, const FVector& At3, float Radius, int32 Icon, bool bMust, int32 Prio, int32 Key)
		{
			FWant& W = Wants.AddDefaulted_GetRef();
			const FVector2D Box = BoxOf(L.Text, L.Size, Par.CharW);
			W.Key = Key;
			W.A.At = Pic(At3);
			W.A.R = Radius;
			W.A.W = Box.X;
			W.A.H = Box.Y;
			W.A.Prio = Prio;
			W.A.bMust = bMust;
			W.A.Self = Icon;
			const int32* Was = State.Slots.Find(Key);
			W.A.Prefer = Was ? *Was : -1;
			L.From = At3;
			L.Icon = Icon;
			L.Key = Key;
			L.Prio = Prio;
			L.Box = Box;
			W.L = MoveTemp(L);
		};
		const auto BearingOf = [&](const FAstraHoloBlip& B) { return FMath::Fmod(FMath::RadiansToDegrees(FMath::Atan2(B.Rel.Y, B.Rel.X)) + Par.HeadingDeg + 720.f, 360.f); };
		TArray<int32> Singles;
		for (int32 k = 0; k < Out.Icons.Num(); ++k)
		{
			const FIcon& Ic = Out.Icons[k];
			const FAstraHoloBlip& B = Blips[Ic.Blip];
			if (Ic.bMust || (!Out.bDense) || ClusterOfIcon[k] < 0)
			{
				if (!Ic.bMust && Out.bDense)
				{
					Singles.Add(k);                   // a crowd's ships that belong to no group: named while the budget lasts
					continue;
				}
				// the ship's own label: its name and id (or its class), and under it how far it is and what it is doing
				FLabel L;
				const FString Title = B.bPlayer ? FString(TEXT("ASN AQUILA"))
				                    : (B.Name.IsEmpty() ? FString::Printf(TEXT("%s  %s"), *B.Contact, B.ClassShort.IsEmpty() ? TEXT("UNKNOWN") : *B.ClassShort.ToUpper())
				                                        : FString::Printf(TEXT("%s  %s"), *B.Name.ToUpper(), *B.Contact));
				FString Sub = B.bPlayer ? FString() : (B.bBearingOnly ? FString(B.bJamming ? TEXT("JAMMING  NO RANGE") : TEXT("BEARING ONLY  NO RANGE"))
				                                                      : RangeText(B.RangeKm) + (B.bJamming ? TEXT("  JAMMING") : TEXT("")));
				if (B.bHoldFire) { Sub += TEXT("  HOLDING FIRE"); }
				else if (B.bRetreating) { Sub += TEXT("  WITHDRAWING"); }
				if (B.bTargeted) { Sub += TEXT("  [TARGET]"); }
				L.Text = Sub.IsEmpty() ? Title : Title + TEXT("<br>") + Sub;
				L.Col = ColorOf(B);
				L.Size = B.bPlayer ? 6.0f : 5.4f;
				Ask(MoveTemp(L), Ic.P, Ic.Radius, k, Ic.bMust, Ic.bMust ? (B.bPlayer ? -2 : (B.bTargeted ? -1 : 0)) : 200 + (int32)B.RangeKm, B.Id);
			}
		}
		// the ships of a crowd that belong to no group: the nearest few, one line each
		Singles.Sort([&](int32 A, int32 B) { return Blips[Out.Icons[A].Blip].RangeKm < Blips[Out.Icons[B].Blip].RangeKm; });
		for (int32 n = 0; n < Singles.Num() && n < MaxIndividual; ++n)
		{
			const int32 k = Singles[n];
			const FIcon& Ic = Out.Icons[k];
			const FAstraHoloBlip& B = Blips[Ic.Blip];
			FLabel L;
			const FString Title = B.Name.IsEmpty() ? FString::Printf(TEXT("%s  %s"), *B.Contact, B.ClassShort.IsEmpty() ? TEXT("UNKNOWN") : *B.ClassShort.ToUpper())
			                                       : FString::Printf(TEXT("%s  %s"), *B.Name.ToUpper(), *B.Contact);
			L.Text = B.bBearingOnly ? Title : Title + TEXT("  ") + RangeText(B.RangeKm);
			L.Col = ColorOf(B);
			L.Size = 4.4f;
			const float Keep = State.Named.Contains(B.Id) ? 3.f : 0.f;       // (a label it had is kept unless a ship nearer by a few km wants it)
			Ask(MoveTemp(L), Ic.P, Ic.Radius, k, false, 200 + (int32)(B.RangeKm - Keep), B.Id);
		}
		// a tag for each group of ships
		for (int32 c = 0; c < Out.Clusters.Num(); ++c)
		{
			const FCluster& C = Out.Clusters[c];
			const FVector2D Mid = Pic(C.Centre);
			float Reach = 0.f;
			float RangeKm = 0.f;
			FVector RelSum = FVector::ZeroVector;
			int32 LowestId = MAX_int32;                  // (what names the group from one frame to the next: its oldest ship's id)
			for (const int32 k : C.Icons)
			{
				Reach = FMath::Max(Reach, (float)FVector2D::Distance(Pic(Out.Icons[k].P), Mid) + Out.Icons[k].Radius);
				RelSum += Blips[Out.Icons[k].Blip].Rel;
				LowestId = FMath::Min(LowestId, Blips[Out.Icons[k].Blip].Id);
			}
			const FVector RelMid = RelSum / (double)C.Icons.Num();
			RangeKm = (float)(RelMid.Size() / 100000.0);
			FAstraHoloBlip Fake;
			Fake.Rel = RelMid;
			FLabel L;
			L.Text = FString::Printf(TEXT("%s x%d<br>%s  ·  %03.0f"), KeyName(C.Key), C.Icons.Num(), *RangeText(RangeKm), BearingOf(Fake));
			L.Col = KeyColor(C.Key);
			L.Size = 4.8f;
			L.bTag = true;
			Ask(MoveTemp(L), C.Centre, Reach + 1.f, -1, false, 100 + (int32)RangeKm, -1 - LowestId);
		}
		// a tag for each flight group (not a label for each craft)
		struct FFlightTag { int32 Squadron; float RangeKm; };
		TArray<FFlightTag> Tags;
		for (const TPair<int32, TArray<int32>>& KV : Flights)
		{
			if (KV.Value.Num() >= 2 && FlightLead.Contains(KV.Key))
			{
				FVector RelSum = FVector::ZeroVector;
				for (const int32 i : KV.Value)
				{
					RelSum += Blips[i].Rel;
				}
				Tags.Add({KV.Key, (float)(RelSum.Size() / (double)KV.Value.Num() / 100000.0)});
			}
		}
		Tags.Sort([](const FFlightTag& A, const FFlightTag& B) { return A.RangeKm < B.RangeKm; });
		for (int32 n = 0; n < Tags.Num() && n < MaxFlightTags; ++n)
		{
			const TArray<int32>& Craft = Flights[Tags[n].Squadron];
			const FAstraHoloBlip& Lead = Blips[FlightLead[Tags[n].Squadron]];
			FVector RelSum = FVector::ZeroVector;
			for (const int32 i : Craft)
			{
				RelSum += Blips[i].Rel;
			}
			const FVector RelMid = RelSum / (double)Craft.Num();
			FLabel L;
			L.Text = FString::Printf(TEXT("%s  %s<br>%s"), *Lead.Name.ToUpper(), *Lead.Contact, *RangeText((float)(RelMid.Size() / 100000.0)));
			L.Col = ColorOf(Lead);
			L.Size = 3.8f;
			L.bTag = true;
			Ask(MoveTemp(L), PointOf(Par, RelMid), 1.5f, -1, false, 400 + (int32)Tags[n].RangeKm, -1000000 - Tags[n].Squadron);
		}

		// ---- the places: the musts and the best of the rest, within the budget
		TArray<int32> Keep;
		{
			TArray<int32> Idx;
			for (int32 i = 0; i < Wants.Num(); ++i)
			{
				Idx.Add(i);
			}
			Idx.StableSort([&](int32 A, int32 B) { return Wants[A].A.Prio < Wants[B].A.Prio; });
			int32 Musts = 0;
			for (const int32 i : Idx)
			{
				if (Wants[i].A.bMust)
				{
					if (Musts++ < MaxMust)
					{
						Keep.Add(i);
					}
					else
					{
						Wants[i].A.bMust = false;
					}
				}
			}
			for (const int32 i : Idx)
			{
				if (!Wants[i].A.bMust && Keep.Num() < Par.MaxLabels)
				{
					Keep.Add(i);
				}
			}
			Out.Dropped = Wants.Num() - Keep.Num();
		}
		TArray<FAsk> Asks;
		for (const int32 i : Keep)
		{
			Asks.Add(Wants[i].A);
		}
		TArray<FVector3f> Obstacles;                    // the icons: x, y, radius (a label's own icon is its Self)
		for (const FIcon& Ic : Out.Icons)
		{
			const FVector2D P = Pic(Ic.P);
			Obstacles.Add(FVector3f((float)P.X, (float)P.Y, Ic.Radius));
		}
		TArray<FGot> Got;
		PlaceLabels(Asks, Obstacles, Got);
		State.Slots.Reset();
		for (int32 n = 0; n < Keep.Num(); ++n)
		{
			if (!Got[n].bShown)
			{
				++Out.Dropped;
				continue;
			}
			FLabel L = Wants[Keep[n]].L;
			L.Pos = L.From + ViewRight * Got[n].Offset.X + ViewUp * Got[n].Offset.Y;
			L.bLeader = Got[n].bLeader;
			State.Slots.Add(Wants[Keep[n]].Key, Got[n].Slot);
			Out.Labels.Add(MoveTemp(L));
		}
		State.Named.Reset();                            // who has a label now (it is kept a little longer next frame)
		for (const FLabel& L : Out.Labels)
		{
			if (L.Icon >= 0)
			{
				State.Named.Add(Blips[Out.Icons[L.Icon].Blip].Id);
			}
		}
	}
}
