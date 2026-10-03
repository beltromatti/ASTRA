// ASTRA — ABBORDAGGI: the Captain's arms on the weapon (docs/ABBORDAGGI.md). The mannequin's rifle and pistol animations hold the Epic weapons with the Epic body behind them; here
// the weapon is placed against the camera (hip, sights, lowered: AstraWeapon.cpp) and the arms are made to hold it: each arm is solved from a shoulder that stands where a body
// would have it (below the picture) to the hand the weapon wants, the elbow bending away from a pole. The right hand holds the grip as the animation has it; the left goes to the
// weapon's own left grip (the animation's hand is where the Epic rifle's fore-grip is, a few centimetres from the handguard of another weapon). The forearms and the hands that
// come into the picture from its lower edge are the animation's own (the fingers, the wrists); only the elbows are moved.
//
// Pure functions on transforms (the mesh's component space): the component feeds them from the animation and writes the result into a poseable copy of the arms, and the bench
// (AstraBoardSimCommandlet, `fps`) tries them on the real mesh without a window.

#pragma once

#include "CoreMinimal.h"

struct FReferenceSkeleton;

namespace AstraArms
{
	enum { Left = 0, Right = 1 };

	/** The bones of the two arms in a skeleton (indices into its reference skeleton). */
	struct FBones
	{
		int32 Upper[2] = {INDEX_NONE, INDEX_NONE};
		int32 Lower[2] = {INDEX_NONE, INDEX_NONE};
		int32 Hand[2] = {INDEX_NONE, INDEX_NONE};
		bool IsValid() const
		{
			return Upper[0] != INDEX_NONE && Lower[0] != INDEX_NONE && Hand[0] != INDEX_NONE && Upper[1] != INDEX_NONE && Lower[1] != INDEX_NONE && Hand[1] != INDEX_NONE;
		}
	};

	/** Finds upperarm_l/r, lowerarm_l/r, hand_l/r by name. */
	ASTRA_API bool FindBones(const FReferenceSkeleton& Ref, FBones& Out);

	/** What one arm is asked to do (all in the mesh's component space, cm). */
	struct FTarget
	{
		FVector Shoulder = FVector::ZeroVector;   // where the upper arm's joint is put
		FVector Hand = FVector::ZeroVector;       // where the wrist is put
		FVector Pole = FVector(0, 0, -1);         // the elbow bends towards this side of the shoulder-to-hand line
		float Alpha = 1.f;                        // 0: the animation's arm as it is, 1: the solved arm (the three joints are blended)
	};

	/** The animation's three bone transforms (component space) go in, the solved ones come out: the upper arm carried to the shoulder, the elbow found from the lengths of the two
	 *  bones (the bones keep their lengths: the hand is held within reach), the hand put where it is wanted and turned as the animation turned it. */
	ASTRA_API void SolveArm(FTransform& Upper, FTransform& Lower, FTransform& Hand, const FTarget& T);

	/** The component-space transforms of a whole pose from its local ones (parents before children, as a reference skeleton has them). */
	ASTRA_API void ComponentSpace(const FReferenceSkeleton& Ref, const TArray<FTransform>& Local, TArray<FTransform>& OutComponent);

	/** Where the arms (the mesh) stand against the camera so that a weapon's sight point is at Target and the weapon is turned by Extra about it. The weapon's own frame (barrel +Y, top
	 *  +Z, its left +X) is the right hand's grip socket in the mesh (SocketLoc, SocketQ: its location and turn in the mesh's space); the camera's frame is x ahead, y right, z up. Gives the
	 *  mesh's location and turn against the camera, and the sight point in the mesh's space (what the weapon's kick turns the weapon about). */
	ASTRA_API void PlaceWeapon(const FVector& SocketLoc, const FQuat& SocketQ, const FVector& SightInWeapon, const FVector& Target, const FRotator& Extra, FVector& OutLoc, FQuat& OutRot, FVector& OutSightInMesh);

	/** What is asked of both arms in a frame (camera space unless said). */
	struct FSetup
	{
		FVector Shoulder[2] = {FVector::ZeroVector, FVector::ZeroVector};       // where each shoulder is put (left, right)
		FVector Pole[2] = {FVector(0.3, -0.5, -0.8), FVector(0.3, 0.5, -0.8)};  // which way each elbow bends
		FVector LeftHandDelta = FVector::ZeroVector;                            // how far the left wrist is moved from the animation's (mesh space): to the weapon's own grip
	};
	/** Both arms solved from the animation's pose (component space, all bones) with the mesh standing against the camera at (MeshQ, MeshLoc): the six solved bone transforms, in the
	 *  order upper, lower, hand of the left arm and then of the right (component space). */
	ASTRA_API void SolveBoth(const FBones& B, const TArray<FTransform>& AnimComponent, const FQuat& MeshQ, const FVector& MeshLoc, const FSetup& Setup, FTransform Out[6]);
}
