#include "AstraArmsRig.h"

#include "ReferenceSkeleton.h"

bool AstraArms::FindBones(const FReferenceSkeleton& Ref, FBones& Out)
{
	static const TCHAR* const Side[2] = {TEXT("_l"), TEXT("_r")};
	for (int32 S = 0; S < 2; ++S)
	{
		Out.Upper[S] = Ref.FindBoneIndex(FName(*FString::Printf(TEXT("upperarm%s"), Side[S])));
		Out.Lower[S] = Ref.FindBoneIndex(FName(*FString::Printf(TEXT("lowerarm%s"), Side[S])));
		Out.Hand[S] = Ref.FindBoneIndex(FName(*FString::Printf(TEXT("hand%s"), Side[S])));
	}
	return Out.IsValid();
}

void AstraArms::ComponentSpace(const FReferenceSkeleton& Ref, const TArray<FTransform>& Local, TArray<FTransform>& OutComponent)
{
	OutComponent.SetNumUninitialized(Local.Num());
	for (int32 i = 0; i < Local.Num(); ++i)
	{
		const int32 P = Ref.GetParentIndex(i);
		OutComponent[i] = P >= 0 && P < i ? Local[i] * OutComponent[P] : Local[i];
	}
}

void AstraArms::SolveArm(FTransform& Upper, FTransform& Lower, FTransform& Hand, const FTarget& T)
{
	const FVector S0 = Upper.GetLocation(), E0 = Lower.GetLocation(), H0 = Hand.GetLocation();
	const double L1 = (E0 - S0).Size(), L2 = (H0 - E0).Size();
	if (L1 < 1.0 || L2 < 1.0 || T.Alpha <= 0.f)
	{
		return;                                       // not an arm, or nothing asked of it
	}
	// the whole arm is carried to the shoulder first (its bones keep their turns)
	const FVector Shift = T.Shoulder - S0;
	const FVector S = T.Shoulder, E1 = E0 + Shift, H1 = H0 + Shift;
	// the wrist's wanted place, within what the two bones reach
	const FVector ToHand = T.Hand - S;
	const double DRaw = ToHand.Size();
	if (DRaw < 1.0)
	{
		return;
	}
	const double D = FMath::Clamp(DRaw, 0.25 * (L1 + L2), 0.999 * (L1 + L2));
	const FVector U = ToHand / DRaw;
	const FVector Ht = S + U * D;
	// the elbow: on the circle of the points that are L1 from the shoulder and L2 from the wrist, on the pole's side
	const double A = (L1 * L1 - L2 * L2 + D * D) / (2.0 * D);
	const double Hgt = FMath::Sqrt(FMath::Max(L1 * L1 - A * A, 0.0));
	FVector Pv = T.Pole - U * FVector::DotProduct(T.Pole, U);
	if (Pv.SizeSquared() < 1.0e-6)
	{
		Pv = FVector::CrossProduct(U, FVector::UpVector);
		if (Pv.SizeSquared() < 1.0e-6)
		{
			Pv = FVector::CrossProduct(U, FVector::RightVector);
		}
	}
	Pv.Normalize();
	const FVector E = S + U * A + Pv * Hgt;
	// the upper arm turns about the shoulder from where the elbow was to where it is now, the forearm about the elbow from where the wrist was to where it is now
	const FQuat R1 = FQuat::FindBetweenVectors(E1 - S, E - S);
	const FVector H2 = S + R1.RotateVector(H1 - S);
	const FQuat R2 = FQuat::FindBetweenVectors(H2 - E, Ht - E);
	FTransform NewUp = Upper, NewLo = Lower, NewHd = Hand;
	NewUp.SetLocation(S);
	NewUp.SetRotation((R1 * Upper.GetRotation()).GetNormalized());
	NewLo.SetLocation(E);
	NewLo.SetRotation((R2 * R1 * Lower.GetRotation()).GetNormalized());
	NewHd.SetLocation(Ht);                            // (its turn is the animation's)
	if (T.Alpha >= 0.999f)
	{
		Upper = NewUp;
		Lower = NewLo;
		Hand = NewHd;
		return;
	}
	const auto Blend = [&](FTransform& From, const FTransform& To)
	{
		From.SetLocation(FMath::Lerp(From.GetLocation(), To.GetLocation(), (double)T.Alpha));
		From.SetRotation(FQuat::Slerp(From.GetRotation(), To.GetRotation(), (double)T.Alpha).GetNormalized());
	};
	Blend(Upper, NewUp);
	Blend(Lower, NewLo);
	Blend(Hand, NewHd);
}

void AstraArms::PlaceWeapon(const FVector& SocketLoc, const FQuat& SocketQ, const FVector& SightInWeapon, const FVector& Target, const FRotator& Extra, FVector& OutLoc, FQuat& OutRot, FVector& OutSightInMesh)
{
	const FVector B = SocketQ.RotateVector(FVector(0, 1, 0)), U = SocketQ.RotateVector(FVector(0, 0, 1)), Ex = SocketQ.RotateVector(FVector(1, 0, 0));
	const FQuat Inv = FMatrix(B, -Ex, U, FVector::ZeroVector).ToQuat();       // columns: where the camera's x, y, z go in the mesh
	const FQuat Base = Inv.Inverse();
	OutSightInMesh = SocketLoc + SocketQ.RotateVector(SightInWeapon);
	OutRot = FQuat(Extra) * Base;
	OutLoc = Target - OutRot.RotateVector(OutSightInMesh);
}

void AstraArms::SolveBoth(const FBones& B, const TArray<FTransform>& AnimComponent, const FQuat& MeshQ, const FVector& MeshLoc, const FSetup& Setup, FTransform Out[6])
{
	const FQuat Qi = MeshQ.Inverse();
	for (int32 Side = 0; Side < 2; ++Side)
	{
		FTransform Up = AnimComponent[B.Upper[Side]], Lo = AnimComponent[B.Lower[Side]], Hd = AnimComponent[B.Hand[Side]];
		FTarget T;
		T.Shoulder = Qi.RotateVector(Setup.Shoulder[Side] - MeshLoc);
		T.Hand = Hd.GetLocation() + (Side == Left ? Setup.LeftHandDelta : FVector::ZeroVector);
		T.Pole = Qi.RotateVector(Setup.Pole[Side]);
		SolveArm(Up, Lo, Hd, T);
		Out[Side * 3 + 0] = Up;
		Out[Side * 3 + 1] = Lo;
		Out[Side * 3 + 2] = Hd;
	}
}
