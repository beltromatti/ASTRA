#include "AstraInput.h"
#include "InputAction.h"
#include "InputMappingContext.h"
#include "InputModifiers.h"
#include "InputCoreTypes.h"

namespace
{
	UInputAction* NewAction(UObject* Outer, const TCHAR* Name, EInputActionValueType Type)
	{
		UInputAction* A = NewObject<UInputAction>(Outer, Name);
		A->ValueType = Type;
		return A;
	}

	/** W and S push the forward axis (Y), A and D the right axis (X); S and A negated. */
	void MapAxisKey(UInputMappingContext* C, UInputAction* A, const FKey& Key, bool bForwardAxis, bool bNegate)
	{
		FEnhancedActionKeyMapping& M = C->MapKey(A, Key);
		if (bForwardAxis)
		{
			UInputModifierSwizzleAxis* Swizzle = NewObject<UInputModifierSwizzleAxis>(C);
			Swizzle->Order = EInputAxisSwizzle::YXZ;
			M.Modifiers.Add(Swizzle);
		}
		if (bNegate)
		{
			M.Modifiers.Add(NewObject<UInputModifierNegate>(C));
		}
	}
}

void UAstraInputSet::Build()
{
	Move = NewAction(this, TEXT("IA_ASTRA_Move"), EInputActionValueType::Axis2D);
	MouseLook = NewAction(this, TEXT("IA_ASTRA_MouseLook"), EInputActionValueType::Axis2D);
	StickLook = NewAction(this, TEXT("IA_ASTRA_StickLook"), EInputActionValueType::Axis2D);
	Jump = NewAction(this, TEXT("IA_ASTRA_Jump"), EInputActionValueType::Boolean);
	Sprint = NewAction(this, TEXT("IA_ASTRA_Sprint"), EInputActionValueType::Boolean);
	Crouch = NewAction(this, TEXT("IA_ASTRA_Crouch"), EInputActionValueType::Boolean);
	LeanLeft = NewAction(this, TEXT("IA_ASTRA_LeanLeft"), EInputActionValueType::Boolean);
	LeanRight = NewAction(this, TEXT("IA_ASTRA_LeanRight"), EInputActionValueType::Boolean);
	Fire = NewAction(this, TEXT("IA_ASTRA_Fire"), EInputActionValueType::Boolean);
	Aim = NewAction(this, TEXT("IA_ASTRA_Aim"), EInputActionValueType::Boolean);
	Reload = NewAction(this, TEXT("IA_ASTRA_Reload"), EInputActionValueType::Boolean);
	Weapon1 = NewAction(this, TEXT("IA_ASTRA_Weapon1"), EInputActionValueType::Boolean);
	Weapon2 = NewAction(this, TEXT("IA_ASTRA_Weapon2"), EInputActionValueType::Boolean);
	QuickSwitch = NewAction(this, TEXT("IA_ASTRA_QuickSwitch"), EInputActionValueType::Boolean);
	Holster = NewAction(this, TEXT("IA_ASTRA_Holster"), EInputActionValueType::Boolean);
	WeaponWheel = NewAction(this, TEXT("IA_ASTRA_WeaponWheel"), EInputActionValueType::Axis1D);

	OnFoot = NewObject<UInputMappingContext>(this, TEXT("IMC_ASTRA_OnFoot"));

	// walking: WASD and the arrows, the left stick
	MapAxisKey(OnFoot, Move, EKeys::W, true, false);
	MapAxisKey(OnFoot, Move, EKeys::S, true, true);
	MapAxisKey(OnFoot, Move, EKeys::D, false, false);
	MapAxisKey(OnFoot, Move, EKeys::A, false, true);
	MapAxisKey(OnFoot, Move, EKeys::Up, true, false);
	MapAxisKey(OnFoot, Move, EKeys::Down, true, true);
	MapAxisKey(OnFoot, Move, EKeys::Right, false, false);
	MapAxisKey(OnFoot, Move, EKeys::Left, false, true);
	{
		FEnhancedActionKeyMapping& M = OnFoot->MapKey(Move, EKeys::Gamepad_Left2D);
		M.Modifiers.Add(NewObject<UInputModifierDeadZone>(OnFoot));
	}

	// looking: the mouse (the viewport reports Y up as positive; negated like Epic's template, since the engine's
	// legacy pitch scale is negative), the right stick as a rate (degrees per second before the controller's scales)
	{
		FEnhancedActionKeyMapping& M = OnFoot->MapKey(MouseLook, EKeys::Mouse2D);
		UInputModifierNegate* Negate = NewObject<UInputModifierNegate>(OnFoot);
		Negate->bX = false;
		Negate->bY = true;
		Negate->bZ = false;
		M.Modifiers.Add(Negate);
	}
	{
		FEnhancedActionKeyMapping& M = OnFoot->MapKey(StickLook, EKeys::Gamepad_Right2D);
		M.Modifiers.Add(NewObject<UInputModifierDeadZone>(OnFoot));
		UInputModifierScalar* Rate = NewObject<UInputModifierScalar>(OnFoot);
		Rate->Scalar = FVector(56.0, 40.0, 1.0);          // ×2.5 yaw and pitch scale: ~140°/s across, ~100°/s up and down
		M.Modifiers.Add(Rate);
		M.Modifiers.Add(NewObject<UInputModifierScaleByDeltaTime>(OnFoot));
		UInputModifierNegate* Negate = NewObject<UInputModifierNegate>(OnFoot);
		Negate->bX = false;
		Negate->bY = true;
		Negate->bZ = false;
		M.Modifiers.Add(Negate);
	}

	OnFoot->MapKey(Jump, EKeys::SpaceBar);
	OnFoot->MapKey(Jump, EKeys::Gamepad_FaceButton_Bottom);
	OnFoot->MapKey(Sprint, EKeys::LeftShift);
	OnFoot->MapKey(Sprint, EKeys::Gamepad_LeftThumbstick);
	OnFoot->MapKey(Crouch, EKeys::C);
	OnFoot->MapKey(Crouch, EKeys::Gamepad_FaceButton_Right);
	// leaning (held): Z and X, the shoulders of a gamepad
	OnFoot->MapKey(LeanLeft, EKeys::Z);
	OnFoot->MapKey(LeanLeft, EKeys::Gamepad_LeftShoulder);
	OnFoot->MapKey(LeanRight, EKeys::X);
	OnFoot->MapKey(LeanRight, EKeys::Gamepad_RightShoulder);

	// the weapons: the left button fires, the right looks through the sights, R reloads, 1 and 2 the rifle and the sidearm, Q the last one, H puts it away, the wheel changes
	OnFoot->MapKey(Fire, EKeys::LeftMouseButton);
	OnFoot->MapKey(Fire, EKeys::Gamepad_RightTriggerAxis);
	OnFoot->MapKey(Aim, EKeys::RightMouseButton);
	OnFoot->MapKey(Aim, EKeys::Gamepad_LeftTriggerAxis);
	OnFoot->MapKey(Reload, EKeys::R);
	OnFoot->MapKey(Reload, EKeys::Gamepad_FaceButton_Left);
	OnFoot->MapKey(Weapon1, EKeys::One);
	OnFoot->MapKey(Weapon2, EKeys::Two);
	OnFoot->MapKey(QuickSwitch, EKeys::Q);
	OnFoot->MapKey(QuickSwitch, EKeys::Gamepad_FaceButton_Top);
	OnFoot->MapKey(Holster, EKeys::H);
	OnFoot->MapKey(Holster, EKeys::Gamepad_DPad_Down);
	OnFoot->MapKey(WeaponWheel, EKeys::MouseWheelAxis);
}
