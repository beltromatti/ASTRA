#include "AstraCombatant.h"

#include "ASTRA.h"
#include "Animation/AnimSequence.h"
#include "AstraWeapon.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "Materials/MaterialInstanceDynamic.h"

namespace
{
	const TCHAR* const CbAnimRoot = TEXT("/Game/Characters/Mannequins/Anims/");
	// the eight ways of a walk or a jog, by the angle of the move against the way he faces (0 ahead, clockwise): 45 degrees each
	const TCHAR* const CbWayNames[8] = {TEXT("Fwd"), TEXT("Fwd_Right"), TEXT("Right"), TEXT("Bwd_Right"), TEXT("Bwd"), TEXT("Bwd_Left"), TEXT("Left"), TEXT("Fwd_Left")};
	constexpr float CbJogFromCmS = 235.f;          // faster than this he jogs, slower he walks
	constexpr float CbWalkRefCmS = 150.f;          // what the mannequin's cycles were made for
	constexpr float CbJogRefCmS = 340.f;
	constexpr float CbMinDwellS = 0.28f;           // an animation stays this long before another (a squad's moves are stop and go)

	UAnimSequence* CbAnim(const FString& Sub)
	{
		return LoadObject<UAnimSequence>(nullptr, *FString::Printf(TEXT("%s%s"), CbAnimRoot, *Sub));
	}
	FString CbAnimPath(const TCHAR* Dir, const FString& Name)
	{
		return FString::Printf(TEXT("%s/%s.%s"), Dir, *Name, *Name);
	}
}

AAstraCombatant::AAstraCombatant()
{
	PrimaryActorTick.bCanEverTick = true;
	Body->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
	Body->SetCollisionObjectType(ECC_Pawn);
	Body->SetCollisionResponseToAllChannels(ECR_Ignore);
	Body->SetCollisionResponseToChannel(ECC_Visibility, ECR_Block);       // the Captain's rounds
	Body->SetGenerateOverlapEvents(false);
	// a body that is always a target even where the mesh has no physics asset: a capsule round the man
	UCapsuleComponent* Hit = CreateDefaultSubobject<UCapsuleComponent>(TEXT("HitCapsule"));
	Hit->SetupAttachment(Body);
	Hit->InitCapsuleSize(28.f, 88.f);
	Hit->SetRelativeLocation(FVector(0.f, 0.f, 88.f));
	Hit->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
	Hit->SetCollisionObjectType(ECC_Pawn);
	Hit->SetCollisionResponseToAllChannels(ECR_Ignore);
	Hit->SetCollisionResponseToChannel(ECC_Visibility, ECR_Block);
	Hit->SetGenerateOverlapEvents(false);
	Hit->SetCanEverAffectNavigation(false);
	Gun = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Gun"));
	Gun->SetupAttachment(Body, FName(TEXT("HandGrip_R")));
	Gun->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Gun->SetGenerateOverlapEvents(false);
	Gun->SetCanEverAffectNavigation(false);
	SetActorHiddenInGame(true);
	SetActorTickEnabled(false);
}

void AAstraCombatant::PreloadAssets(TArray<TObjectPtr<UObject>>& OutKeep)
{
	TArray<FString> Paths;
	Paths.Add(TEXT("/Game/Characters/Mannequins/Meshes/SKM_Manny_Simple.SKM_Manny_Simple"));
	Paths.Add(TEXT("/Game/Characters/Mannequins/Meshes/SKM_Quinn_Simple.SKM_Quinn_Simple"));
	Paths.Add(AstraWeapons::Get(EAstraWeapon::Rifle).MeshPath);
	Paths.Add(FString(CbAnimRoot) + TEXT("Rifle/MF_Rifle_Idle_ADS.MF_Rifle_Idle_ADS"));
	Paths.Add(FString(CbAnimRoot) + TEXT("Rifle/MM_Rifle_Reload.MM_Rifle_Reload"));
	for (const TCHAR* Gait : {TEXT("Walk"), TEXT("Jog")})
	{
		for (const int32 Way : {0, 2, 4, 6})
		{
			const FString N = FString::Printf(TEXT("MF_Rifle_%s_%s"), Gait, CbWayNames[Way]);
			Paths.Add(FString::Printf(TEXT("%sRifle/%s/%s.%s"), CbAnimRoot, Gait, *N, *N));
		}
	}
	for (const TCHAR* D : {TEXT("MM_Death_Front_01"), TEXT("MM_Death_Back_01")})
	{
		Paths.Add(FString::Printf(TEXT("%sDeath/%s.%s"), CbAnimRoot, D, D));
	}
	for (const FString& P : Paths)
	{
		if (UObject* O = LoadObject<UObject>(nullptr, *P))
		{
			OutKeep.Add(O);
		}
	}
}

AAstraCombatant::EZone AAstraCombatant::ZoneOfBone(const FName& Bone)
{
	if (Bone.IsNone())
	{
		return EZone::Body;
	}
	const FString B = Bone.ToString().ToLower();
	if (B.Contains(TEXT("head")) || B.Contains(TEXT("neck")))
	{
		return EZone::Head;
	}
	for (const TCHAR* L : {TEXT("upperarm"), TEXT("lowerarm"), TEXT("hand"), TEXT("thumb"), TEXT("index"), TEXT("middle"), TEXT("ring"), TEXT("pinky"), TEXT("thigh"), TEXT("calf"), TEXT("foot"), TEXT("ball")})
	{
		if (B.Contains(L))
		{
			return EZone::Limb;
		}
	}
	return EZone::Body;
}

void AAstraCombatant::Bind(int32 InUnit, bool bInMandate, const FString& InName, bool bFemale, int32 InRoster, const FVector& At, float Yaw)
{
	UnitIdx = InUnit;
	RosterIdx = InRoster;
	bMandate = bInMandate;
	NameOf = InName;
	DisplayName = InName;
	StationId = InRoster != INDEX_NONE ? FString::Printf(TEXT("npc%d"), InRoster) : FString::Printf(TEXT("mandate%d"), InUnit);
	bFallen = false;
	bHaveHitFrom = false;
	bFirstDrive = true;
	bHide = false;
	Pose = EPose::None;
	PoseSub = -1;
	Vel = FVector::ZeroVector;
	FloorZ = At.Z;
	FloorT = 0.f;
	Goal = At;
	GoalYaw = Yaw;
	FaceYaw = Yaw;
	bFemaleBody = bFemale;
	SetBody(bFemale);
	if (bMandate)
	{
		DressMandate();
	}
	else
	{
		SetUniformDept(TEXT("marines"));
	}
	ArmUp();
	SetActorLocationAndRotation(At, FRotator(0.f, Yaw - 90.f, 0.f), false, nullptr, ETeleportType::TeleportPhysics);
	Show(true);
	SetActorTickEnabled(true);
}

void AAstraCombatant::Unbind()
{
	UnitIdx = INDEX_NONE;
	RosterIdx = INDEX_NONE;
	bFallen = false;
	Pose = EPose::None;
	Show(false);
	SetActorTickEnabled(false);
	if (Body)
	{
		Body->Stop();
	}
}

void AAstraCombatant::Show(bool bOn)
{
	SetActorHiddenInGame(!bOn);
	if (Body)
	{
		Body->SetVisibility(bOn, true);
		Body->SetCollisionEnabled(bOn ? ECollisionEnabled::QueryOnly : ECollisionEnabled::NoCollision);
	}
	if (Gun)
	{
		Gun->SetVisibility(bOn);
	}
}

void AAstraCombatant::ArmUp()
{
	if (!Gun)
	{
		return;
	}
	const FAstraWeaponDef& W = AstraWeapons::Get(EAstraWeapon::Rifle);
	UStaticMesh* M = LoadObject<UStaticMesh>(nullptr, W.MeshPath);
	if (!M)
	{
		// the model is not imported yet: a bar the size of a rifle, so that the soldier still reads as armed
		M = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cube.Cube"));
		Gun->SetRelativeScale3D(FVector(0.06f, 0.6f, 0.14f));
		Gun->SetRelativeLocation(FVector(0.f, 28.f, 8.f));
	}
	else
	{
		Gun->SetRelativeScale3D(FVector::OneVector);
		Gun->SetRelativeLocation(FVector::ZeroVector);
	}
	Gun->SetStaticMesh(M);
	if (Body->DoesSocketExist(TEXT("HandGrip_R")))
	{
		Gun->AttachToComponent(Body, FAttachmentTransformRules::SnapToTargetNotIncludingScale, FName(TEXT("HandGrip_R")));
	}
	else
	{
		Gun->AttachToComponent(Body, FAttachmentTransformRules::SnapToTargetNotIncludingScale);
		Gun->SetRelativeLocation(FVector(-20.f, 25.f, 130.f));
	}
}

void AAstraCombatant::DressMandate()
{
	// the Mandate's boarders: black armour over dark fatigues (the crew's uniform materials, tinted)
	if (Body->GetNumMaterials() < 2)
	{
		return;
	}
	TrousersMID = Body->CreateDynamicMaterialInstance(0);
	JacketMID = Body->CreateDynamicMaterialInstance(1);
	if (TrousersMID)
	{
		TrousersMID->SetVectorParameterValue(TEXT("Tint"), FLinearColor(0.012f, 0.013f, 0.015f));
	}
	if (JacketMID)
	{
		JacketMID->SetVectorParameterValue(TEXT("Tint"), FLinearColor(0.035f, 0.04f, 0.042f));
	}
}

FVector AAstraCombatant::MuzzleAt() const
{
	if (Gun && Gun->GetStaticMesh())
	{
		return Gun->GetComponentTransform().TransformPosition(AstraWeapons::Get(EAstraWeapon::Rifle).Muzzle);
	}
	return GetActorLocation() + FVector(0.f, 0.f, 135.f) + MuzzleDir() * 60.f;
}

FVector AAstraCombatant::MuzzleDir() const
{
	if (Gun)
	{
		// the barrel points along the gun's +Y (art/blender/weapons.py)
		return Gun->GetComponentTransform().TransformVectorNoScale(FVector(0.f, 1.f, 0.f)).GetSafeNormal();
	}
	return FRotator(0.f, FaceYaw, 0.f).Vector();
}

void AAstraCombatant::NoteShot()
{
	KickT = 0.08f;
}

void AAstraCombatant::NoteHit(const FVector& From)
{
	HitFrom = From;
	bHaveHitFrom = true;
}

void AAstraCombatant::SetPose(EPose P, int32 Sub, float Rate)
{
	if (P == Pose && Sub == PoseSub)
	{
		if (P == EPose::Walk || P == EPose::Jog)
		{
			Body->SetPlayRate(Rate);
		}
		return;
	}
	const bool bUrgent = P == EPose::Fallen || P == EPose::Reload || Pose == EPose::None || Pose == EPose::Reload;
	if (!bUrgent && PoseT < CbMinDwellS)
	{
		return;
	}
	UAnimSequence* Seq = nullptr;
	bool bLoop = true;
	switch (P)
	{
	case EPose::Idle:
		Seq = CbAnim(TEXT("Rifle/MF_Rifle_Idle_ADS.MF_Rifle_Idle_ADS"));
		break;
	case EPose::Walk:
	case EPose::Jog:
	{
		const bool bJog = P == EPose::Jog;
		const FString N = FString::Printf(TEXT("MF_Rifle_%s_%s"), bJog ? TEXT("Jog") : TEXT("Walk"), CbWayNames[FMath::Clamp(Sub, 0, 7)]);
		Seq = LoadObject<UAnimSequence>(nullptr, *CbAnimPath(*FString::Printf(TEXT("%sRifle/%s"), CbAnimRoot, bJog ? TEXT("Jog") : TEXT("Walk")), N));
		break;
	}
	case EPose::Reload:
		Seq = CbAnim(TEXT("Rifle/MM_Rifle_Reload.MM_Rifle_Reload"));
		bLoop = false;
		break;
	case EPose::Fallen:
	{
		static const TCHAR* const Falls[] = {TEXT("MM_Death_Front_01"), TEXT("MM_Death_Front_02"), TEXT("MM_Death_Front_03"), TEXT("MM_Death_Back_01"), TEXT("MM_Death_Left_01"), TEXT("MM_Death_Right_01")};
		int32 Pick = Sub >= 0 ? Sub : FMath::RandHelper(3);
		Seq = LoadObject<UAnimSequence>(nullptr, *CbAnimPath(*FString::Printf(TEXT("%sDeath"), CbAnimRoot), Falls[FMath::Clamp(Pick, 0, 5)]));
		bLoop = false;
		break;
	}
	default:
		break;
	}
	Pose = P;
	PoseSub = Sub;
	PoseT = 0.f;
	if (Seq)
	{
		Body->PlayAnimation(Seq, bLoop);
		Body->SetPlayRate(Rate);
	}
}

void AAstraCombatant::Drive(const AstraBoard::FUnit& U, float Dt)
{
	using namespace AstraBoard;
	if (UnitIdx == INDEX_NONE)
	{
		return;
	}
	SinceDrive = 0.f;
	Goal = U.Pos + WorldOffset;
	GoalYaw = U.Yaw;
	bStairs = U.StairT > 0.05f;
	const bool bFall = U.Act == EAct::Down || U.Act == EAct::Dead;
	if (bFall && !bFallen)
	{
		bFallen = true;
		int32 Which = -1;
		if (bHaveHitFrom)
		{
			// where the round came from, against the way he faced: from the front he goes over backwards (the mannequin's "back" falls), from behind forwards
			const FVector Fwd = FRotator(0.f, FaceYaw, 0.f).Vector();
			const FVector To = (HitFrom - GetActorLocation()).GetSafeNormal2D();
			const float Dot = (float)FVector::DotProduct(Fwd, To);
			const float Side = (float)FVector::DotProduct(FVector::CrossProduct(FVector::UpVector, Fwd), To);
			Which = Dot > 0.5f ? 3 : (Dot < -0.5f ? FMath::RandHelper(3) : (Side > 0.f ? 5 : 4));
		}
		SetPose(EPose::Fallen, Which);
	}
	else if (!bFall && bFallen)
	{
		bFallen = false;                       // up again (the Captain's rescue, a man carried out is gone and not here)
		Pose = EPose::None;
	}
	if (bFallen)
	{
		return;
	}
	if (U.Act == EAct::Reload)
	{
		SetPose(EPose::Reload, 0);
		return;
	}
	if (Pose == EPose::Reload && PoseT < 2.1f)
	{
		return;                                // the reload's cycle goes on
	}
	const float Speed = (float)Vel.Size2D();
	if (Speed > 40.f)
	{
		// the way he goes against the way he faces
		const float MoveYaw = FMath::RadiansToDegrees(FMath::Atan2(Vel.Y, Vel.X));
		float Rel = FMath::UnwindDegrees(MoveYaw - FaceYaw);
		if (Rel < 0.f)
		{
			Rel += 360.f;
		}
		const int32 Way = ((int32)FMath::RoundToInt(Rel / 45.f)) % 8;
		const bool bJog = Speed > CbJogFromCmS;
		SetPose(bJog ? EPose::Jog : EPose::Walk, Way, FMath::Clamp(Speed / (bJog ? CbJogRefCmS : CbWalkRefCmS), 0.6f, 1.5f));
	}
	else
	{
		SetPose(EPose::Idle, 0);
	}
}

void AAstraCombatant::Tick(float DeltaSeconds)
{
	// the crew member's own tick turns a body to face the Captain and back to its rest: a soldier's facing is the simulation's, so only the actor's tick runs
	AActor::Tick(DeltaSeconds);
	if (UnitIdx == INDEX_NONE)
	{
		return;
	}
	PoseT += DeltaSeconds;
	SinceDrive += DeltaSeconds;
	KickT = FMath::Max(0.f, KickT - DeltaSeconds);
	if (SinceDrive > 3.f)
	{
		return;                                // the simulation has let go of him
	}
	// in a stair tower nobody sees him: hidden until he comes out (the way VITA's people do)
	if (bStairs != bHide)
	{
		bHide = bStairs;
		Show(!bHide);
	}
	// where the feet are: the deck under him (a trace now and then), the simulation's x and y
	FloorT -= DeltaSeconds;
	if (FloorT <= 0.f && !bFallen && !bHide)
	{
		FloorT = 0.35f;
		FHitResult H;
		FCollisionQueryParams Q(SCENE_QUERY_STAT(AstraSoldierFloor), false, this);
		const FVector P = GetActorLocation();
		if (GetWorld() && GetWorld()->LineTraceSingleByChannel(H, FVector(Goal.X, Goal.Y, Goal.Z + 60.f), FVector(Goal.X, Goal.Y, Goal.Z - 110.f), ECC_Visibility, Q))
		{
			FloorZ = H.Location.Z;
		}
		else
		{
			FloorZ = Goal.Z;
		}
		(void)P;
	}
	const FVector Cur = GetActorLocation();
	FVector Want(Goal.X, Goal.Y, FloorZ);
	FVector Next;
	if (bFirstDrive || FVector::DistSquared(Cur, Want) > 220.0 * 220.0)
	{
		Next = Want;                           // arriving, or he came out of a stair tower far from where he went in
		bFirstDrive = false;
		Vel = FVector::ZeroVector;
	}
	else
	{
		Next = FMath::VInterpTo(Cur, Want, DeltaSeconds, 15.f);
		const FVector V = DeltaSeconds > 0.f ? (Next - Cur) / DeltaSeconds : FVector::ZeroVector;
		Vel = FMath::Lerp(Vel, V, FMath::Clamp(DeltaSeconds * 10.f, 0.f, 1.f));
	}
	FaceYaw = FMath::FixedTurn(FaceYaw, GoalYaw, 560.f * DeltaSeconds);
	SetActorLocationAndRotation(Next, FRotator(0.f, FaceYaw - 90.f, 0.f), false, nullptr, ETeleportType::None);
}
