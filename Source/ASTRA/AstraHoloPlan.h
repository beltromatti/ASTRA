// ASTRA — what the holographic tactical plot shows of a fleet battle, decided apart from the components that show it (F2.3, docs/SCALA.md).
//
// With fifty contacts and more the plot's old way — an icon, a stem, a velocity line and a label for every one, each label climbing above the others in the
// viewer's picture plane — became a tower of text over a heap of components. The plan below is what the table puts up instead: the ships' icons as ever, but
//   - the craft as dots (one instanced component each side, not four components each), and a tag for each flight group, not for each craft;
//   - when the ships are many (more than ten besides the Aquila), the ships that fly together (the same side, a few kilometres apart) are one tag with their
//     number, their range and their bearing, and only the ones that matter keep a name of their own: the Aquila, the target our fire control is on, whoever is
//     firing on us, and the nearest of the rest, up to a budget;
//   - every label is placed in the viewer's picture plane where it covers neither another label nor an icon: right of its icon, left, above, below, and out
//     a ring further with a leader line if those are taken; a label that finds no room is not shown (the ones that must be shown are, whatever it costs).
// It is plain functions of plain data (no components, no engine objects), so the war bench can run it on a real battle and draw what it comes to
// (tools/art/holo_plan_preview.py): the readability of the table is checked on pictures, offline.

#pragma once

#include "CoreMinimal.h"
#include "AstraBattleSubsystem.h"

namespace AstraHoloPlan
{
	/** The table's geometry and what the viewer looks from. */
	struct FParams
	{
		float PlotRadius = 118.f;          // cm: the disc
		float PlaneHeight = 42.f;          // cm: the tactical plane above the table top
		float MaxDepth = 28.f;             // cm: how far above or below the plane a contact may be drawn
		float RangeKm = 20.f;              // the range at the rim (the table smooths it)
		FVector ViewerLocal = FVector(-430.f, 0.f, 100.f);   // the viewer, in the plot's own frame
		float HeadingDeg = 0.f;            // the Aquila's, for true bearings
		int32 MaxLabels = 16;              // text components the plot may use at once
		float CharW = 0.52f;               // a character's width for its height (the table measures its own font and tells the plan)
	};

	/** A ship's icon. */
	struct FIcon
	{
		int32 Blip = -1;                   // index in the blips
		FVector P = FVector::ZeroVector;   // plot frame, cm
		bool bBeyond = false;              // past the plotted range (pinned to the rim)
		bool bMust = false;                // the Aquila, our target, who fires on us
		float Size = 18.f;                 // cm: the icon's length (smaller in a crowd, so that a fleet is not one heap)
		float Radius = 7.f;                // cm: what a label keeps clear of
	};

	struct FDot
	{
		FVector P = FVector::ZeroVector;
		float Scale = 0.014f;              // of the engine's 100 cm sphere
	};

	/** One piece of text on the plot. */
	struct FLabel
	{
		FString Text;                      // lines joined with <br>
		FLinearColor Col = FLinearColor::White;
		float Size = 5.f;                  // the text's world size, cm
		FVector Pos = FVector::ZeroVector; // where its bottom centre goes, plot frame
		FVector2D Box = FVector2D::ZeroVector;   // its width and height (cm), as the layout reckoned them
		bool bLeader = false;              // out from its icon: draw a line to it
		FVector From = FVector::ZeroVector;// the leader's foot (the icon, or a tag's centre)
		int32 Icon = -1;                   // the icon (index in Icons) it names, -1 for a tag
		int32 Key = 0;                     // what names it from one frame to the next (the ship's id; a negative number for a tag)
		int32 Prio = 0;
		bool bTag = false;                 // a group of ships or a flight group
	};

	/** A knot of ships that fly together. */
	struct FCluster
	{
		TArray<int32> Icons;
		FVector Centre = FVector::ZeroVector;
		uint8 Key = 0;                     // 0 ASTRA, 1 hostile, 2 unknown, 3 neutral
	};

	struct FPlan
	{
		TArray<FIcon> Icons;
		TArray<FDot> CraftDots[3];         // ASTRA, hostile, the rest
		TArray<FDot> MissileDots[2];       // ASTRA, hostile
		TArray<int32> Blasts;              // blip indices
		TArray<FLabel> Labels;
		TArray<int32> Threats;             // icons of the ships that fire on us (the nearest few)
		TArray<FCluster> Clusters;         // the tagged groups
		bool bDense = false;
		int32 Dropped = 0;                 // labels that found no room
	};

	/** What carries from one frame to the next: which ships were together (they stay together a little further apart), who had a label (it keeps it unless a
	 *  nearer ship wants it much more). */
	struct FState
	{
		TSet<uint64> Together;
		TSet<int32> Named;
		TMap<int32, int32> Slots;          // where each label sat (which of its candidate places): it stays there while that place is free, so labels do not hop
	};

	/** The viewer's picture plane over the plot (x to their right, y up), from where they look. */
	void ViewBasis(const FParams& Par, FVector& OutRight, FVector& OutUp);
	/** Where a viewer standing at ViewerRoot (the table's own frame) sees the plot from, once the projector has tilted it towards them (the table's own rule:
	 *  up to MaxTilt degrees, none for someone leaning over it); the plot's frame, so the same numbers the table works with: for the bench's pictures. */
	FVector ViewerInPlotFrame(const FVector& ViewerRoot, float PlotRadius, float PlaneHeight, float MaxTilt, float& OutTiltDeg);
	/** A point of the plot from a position relative to the Aquila (cm, bridge frame): the logarithmic radial scale of the disc, pinned to the rim beyond the range. */
	float RadiusOf(const FParams& Par, float Km);
	FVector PointOf(const FParams& Par, const FVector& RelCm);
	/** "4.2 km", "26 km". */
	FString RangeText(float Km);
	/** Whose colour a blip is drawn in (the Aquila, unknown, ASTRA, hostile, holding fire, neutral). */
	FLinearColor ColorOf(const FAstraHoloBlip& B);

	/** The plan for these blips. */
	void Make(const TArray<FAstraHoloBlip>& Blips, const FParams& Par, FState& State, FPlan& Out);

	/** Labels in a picture plane (x right, y up; cm), each wanting a place near its thing, covering no other label and no icon: the engine of Make, on its own so it can be tried. */
	struct FAsk
	{
		FVector2D At = FVector2D::ZeroVector;    // what it names, in the plane
		float R = 5.f;                           // how big that is: the label keeps clear of it
		float W = 10.f, H = 5.f;                 // its box
		int32 Prio = 0;                          // placed in this order (smaller first)
		bool bMust = false;                      // placed whatever the crowd
		int32 Self = -1;                         // the obstacle (index in Obstacles) that is its own thing
		int32 Prefer = -1;                       // the place it had last time (a slot number), tried first
	};
	struct FGot
	{
		bool bShown = false;
		FVector2D Offset = FVector2D::ZeroVector;   // from what it names to the label's bottom centre
		bool bLeader = false;
		int32 Slot = -1;                            // the place it took (ring * 8 + which of the eight)
	};
	void PlaceLabels(const TArray<FAsk>& Asks, const TArray<FVector3f>& Obstacles /* x, y, radius */, TArray<FGot>& Got);
}
