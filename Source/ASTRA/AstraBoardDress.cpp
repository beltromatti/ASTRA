#include "AstraBoardDress.h"

#include "ASTRA.h"
#include "AstraBoardInterior.h"
#include "Dom/JsonObject.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

using namespace AstraBoardDress;
using AstraBoardInterior::FFaceGeo;
using AstraBoardInterior::FOpening;
using AstraBoardInterior::FWallRun;

namespace
{
	constexpr double kWall = AstraBoardInterior::WallCm;           // a wall's thickness: the visible face of a wall is this far in from the room's box
	constexpr double kBay = 200.0;                                  // a wall bay's width, the ceiling run's length, the floor plate's side
	constexpr double kBayH = 260.0;                                 // the bays' height: a taller wall has its upper part bare, a cornice capping the bays
	constexpr double kTallHall = 650.0;                             // a room taller than this (a hangar) has no ceiling dressing: it is lit from its walls
	constexpr double kRun = 400.0;                                  // the long pieces (a cornice, a guide light, a run of pipes or a cable tray) are made two metres and stand four: their clamps and rods are twice as far apart
	constexpr double kPlate = 320.0;                                // a floor plate's side in a room (made two metres: the diamond plate is a little coarser)
	constexpr double kRibW = 22.0, kRibD = 21.0, kRibH = 300.0;     // a rib: width along the wall, depth into the room, height
	constexpr double kJambW = 24.0;                                 // a door jamb's width along the wall (the frame slabs under it are 10)
	constexpr double kBlastJambW = 40.0;
	constexpr double kLaneR = 55.0;                                 // what the soldiers' lanes keep clear: a man's width and a little more
	constexpr double kPropGap = 10.0;                               // a prop stands this far off the wall's face (its relief is more: a handrail's brackets, a rib)
	constexpr double kNudge = 0.6;                                  // a piece's back plate stands this far off the structure under it (no two faces at one depth)

	// ============================================================================================================================ the catalog
#define BRD_DEF(Key, Mesh, Frame, Solid, X0, Y0, X1, Y1, H) {TEXT(Key), TEXT(Mesh), EFrame::Frame, Solid, X0, Y0, X1, Y1, H}
	const FPieceDef GDefs[] =
	{
		BRD_DEF("wall_a", "SM_BRD_WallA", Wall, false, 0, 0, 0, 0, 0),
		BRD_DEF("wall_b", "SM_BRD_WallB", Wall, false, 0, 0, 0, 0, 0),
		BRD_DEF("wall_c", "SM_BRD_WallC", Wall, false, 0, 0, 0, 0, 0),
		BRD_DEF("wall_d", "SM_BRD_WallD", Wall, false, 0, 0, 0, 0, 0),
		BRD_DEF("wall_e", "SM_BRD_WallE", Wall, false, 0, 0, 0, 0, 0),
		BRD_DEF("wall_f", "SM_BRD_WallF", Wall, false, 0, 0, 0, 0, 0),
		BRD_DEF("wall_motto", "SM_BRD_WallMotto", Wall, false, 0, 0, 0, 0, 0),
		BRD_DEF("wall_hold", "SM_BRD_WallHold", Wall, false, 0, 0, 0, 0, 0),
		BRD_DEF("wall_plain", "SM_BRD_WallPlain", Wall, false, 0, 0, 0, 0, 0),
		BRD_DEF("rib", "SM_BRD_Rib", Wall, false, 0, 0, 0, 0, 0),
		BRD_DEF("cornice", "SM_BRD_Cornice", Wall, false, 0, 0, 0, 0, 0),
		BRD_DEF("header", "SM_BRD_Header", Wall, false, 0, 0, 0, 0, 0),
		BRD_DEF("pipes", "SM_BRD_Pipes", Ceiling, false, 0, 0, 0, 0, 0),
		BRD_DEF("tray", "SM_BRD_Tray", Ceiling, false, 0, 0, 0, 0, 0),
		BRD_DEF("lamp", "SM_BRD_Lamp", Ceiling, false, 0, 0, 0, 0, 0),
		BRD_DEF("lamp_dead", "SM_BRD_LampDead", Ceiling, false, 0, 0, 0, 0, 0),
		BRD_DEF("lamp_red", "SM_BRD_LampRed", Ceiling, false, 0, 0, 0, 0, 0),
		BRD_DEF("vent", "SM_BRD_Vent", Ceiling, false, 0, 0, 0, 0, 0),
		BRD_DEF("cables", "SM_BRD_Cables", Ceiling, false, 0, 0, 0, 0, 0),
		BRD_DEF("floor", "SM_BRD_Floor", Floor, false, 0, 0, 0, 0, 0),
		BRD_DEF("threshold", "SM_BRD_Threshold", Floor, false, 0, 0, 0, 0, 0),
		BRD_DEF("guide", "SM_BRD_Guide", Floor, false, 0, 0, 0, 0, 0),
		BRD_DEF("debris", "SM_BRD_Debris", Floor, false, 0, 0, 0, 0, 0),
		BRD_DEF("jamb", "SM_BRD_Jamb", Opening, false, 0, 0, 0, 0, 0),
		BRD_DEF("door_header", "SM_BRD_DoorHeader", Opening, false, 0, 0, 0, 0, 0),
		BRD_DEF("blast_jamb", "SM_BRD_BlastJamb", Opening, false, 0, 0, 0, 0, 0),
		BRD_DEF("blast_header", "SM_BRD_BlastHeader", Opening, false, 0, 0, 0, 0, 0),
		BRD_DEF("blast_leaf", "SM_BRD_BlastLeaf", Opening, false, 0, 0, 0, 0, 0),
		BRD_DEF("crate", "SM_BRD_Crate", Prop, true, -49, -49, 49, 51, 90),
		BRD_DEF("crate_long", "SM_BRD_CrateLong", Prop, true, -33, -93, 34, 93, 64),
		BRD_DEF("barrel", "SM_BRD_Barrel", Prop, true, -32, -32, 32, 32, 101),
		BRD_DEF("locker", "SM_BRD_Locker", Prop, true, -27, -47, 33, 47, 204),
		BRD_DEF("rack", "SM_BRD_Rack", Prop, true, -31, -82, 32, 85, 227),
		BRD_DEF("bunk", "SM_BRD_Bunk", Prop, true, -46, -101, 47, 105, 190),
		BRD_DEF("table", "SM_BRD_Table", Prop, true, -45, -80, 45, 80, 86),
		BRD_DEF("bench", "SM_BRD_Bench", Prop, true, -21, -80, 21, 80, 49),
		BRD_DEF("console", "SM_BRD_Console", Prop, true, -35, -60, 35, 60, 122),
		BRD_DEF("machine", "SM_BRD_Machine", Prop, true, -45, -70, 47, 70, 112),
		BRD_DEF("motor", "SM_BRD_Motor", Prop, true, -50, -50, 52, 54, 145),
		BRD_DEF("tank", "SM_BRD_Tank", Prop, true, -71, -72, 86, 75, 236),
		BRD_DEF("reactor", "SM_BRD_Reactor", Prop, true, -68, -69, 68, 69, 295),
		BRD_DEF("breech", "SM_BRD_Breech", Prop, true, -70, -56, 76, 56, 140),
		BRD_DEF("bed", "SM_BRD_Bed", Prop, true, -46, -109, 66, 104, 172),
		BRD_DEF("cell", "SM_BRD_Cell", Prop, true, -93, -100, 94, 100, 233),
		BRD_DEF("banner", "SM_BRD_Banner", Prop, false, -4, -54, 4, 54, 242),
		BRD_DEF("body_a", "SM_BRD_BodyA", Body, false, -112, -34, 92, 71, 26),
		BRD_DEF("body_b", "SM_BRD_BodyB", Body, false, -115, -38, 113, 47, 30),
		BRD_DEF("body_c", "SM_BRD_BodyC", Body, false, -85, -48, 88, 25, 29),
	};
#undef BRD_DEF
	static_assert(UE_ARRAY_COUNT(GDefs) == (int32)EPiece::Count, "the catalog lists every piece of the kit, in the order of EPiece");

	// ============================================================================================================================ small geometry
	inline uint32 Mix(uint32 A, uint32 B) { return HashCombineFast(A, B * 2654435761u + 0x9e3779b9u); }

	inline FBox2D Square(const FVector2D& C, double R) { return FBox2D(C - FVector2D(R, R), C + FVector2D(R, R)); }

	/** Whether a segment crosses an axis-aligned box (the slab method). */
	bool SegHitsBox(const FVector2D& A, const FVector2D& B, const FBox2D& Box)
	{
		double T0 = 0.0, T1 = 1.0;
		const FVector2D D = B - A;
		for (int32 Axis = 0; Axis < 2; ++Axis)
		{
			const double Da = Axis == 0 ? D.X : D.Y, Aa = Axis == 0 ? A.X : A.Y, Lo = Axis == 0 ? Box.Min.X : Box.Min.Y, Hi = Axis == 0 ? Box.Max.X : Box.Max.Y;
			if (FMath::Abs(Da) < 1.0e-9)
			{
				if (Aa < Lo || Aa > Hi)
				{
					return false;
				}
				continue;
			}
			double Ta = (Lo - Aa) / Da, Tb = (Hi - Aa) / Da;
			if (Ta > Tb)
			{
				Swap(Ta, Tb);
			}
			T0 = FMath::Max(T0, Ta);
			T1 = FMath::Min(T1, Tb);
			if (T0 > T1)
			{
				return false;
			}
		}
		return true;
	}

	/** A face of a room: the way into the room (unit), the way along the wall to the right of one who faces it (unit), and the yaw that turns a wall piece (x along the wall, y into the room) to it. */
	struct FFaceFrame
	{
		FVector2D In, Along;
		float Yaw = 0.f;
		int32 Quarter = 0;                  // the same yaw in quarter turns: a prop's front (+X) into the room
	};

	FFaceFrame FrameOfFace(int32 Face)
	{
		FFaceFrame F;
		switch (Face)
		{
		case 0: F.In = FVector2D(-1.0, 0.0); F.Along = FVector2D(0.0, 1.0); F.Yaw = 90.f; F.Quarter = 1; break;       // the +X wall: its right is +Y
		case 1: F.In = FVector2D(1.0, 0.0); F.Along = FVector2D(0.0, -1.0); F.Yaw = -90.f; F.Quarter = 3; break;
		case 2: F.In = FVector2D(0.0, -1.0); F.Along = FVector2D(-1.0, 0.0); F.Yaw = 180.f; F.Quarter = 2; break;
		default: F.In = FVector2D(0.0, 1.0); F.Along = FVector2D(1.0, 0.0); F.Yaw = 0.f; F.Quarter = 0; break;
		}
		return F;
	}

	/** A prop's front (+X) turned so that it looks into the room from a face: yaw 180 on the +X wall (it looks towards -X), 0 on the -X wall, 270 on the +Y wall, 90 on the -Y wall. */
	float PropYawOfFace(int32 Face)
	{
		static const float Yaws[4] = {180.f, 0.f, 270.f, 90.f};
		return Yaws[FMath::Clamp(Face, 0, 3)];
	}

	/** A prop's footprint (its own frame, cm) turned by a yaw that is a multiple of 90 degrees: the box about its origin in the plan's frame. */
	FBox2D TurnedFootprint(const FPieceDef& D, float YawDeg)
	{
		const int32 Q = ((FMath::RoundToInt(YawDeg / 90.f) % 4) + 4) % 4;
		const double C = Q == 0 ? 1.0 : (Q == 2 ? -1.0 : 0.0), S = Q == 1 ? 1.0 : (Q == 3 ? -1.0 : 0.0);
		FBox2D Out(ForceInit);
		for (int32 k = 0; k < 4; ++k)
		{
			const double X = (k & 1) ? D.MaxX : D.MinX, Y = (k & 2) ? D.MaxY : D.MinY;
			Out += FVector2D(X * C - Y * S, X * S + Y * C);
		}
		return Out;
	}

	FRotator YawRot(float Yaw) { return FRotator(0.f, Yaw, 0.f); }

	// ============================================================================================================================ what kind of room
	enum class EKc : uint8 { Corridor, Stairs, Tech, Store, Crew, Command, Weapons, Medical, Hall, Lock, Tank, Other, Num };

	EKc ClassOfKind(const FString& K)
	{
		static const TMap<FString, EKc> M = {
			{TEXT("corridor"), EKc::Corridor}, {TEXT("stairs"), EKc::Stairs},
			{TEXT("machinery"), EKc::Tech}, {TEXT("engines"), EKc::Tech}, {TEXT("engineering"), EKc::Tech}, {TEXT("air_plant"), EKc::Tech}, {TEXT("damage_control"), EKc::Tech}, {TEXT("workshop"), EKc::Tech},
			{TEXT("storage"), EKc::Store}, {TEXT("cargo"), EKc::Store}, {TEXT("magazine"), EKc::Store}, {TEXT("laundry"), EKc::Store}, {TEXT("armory"), EKc::Store},
			{TEXT("cabins"), EKc::Crew}, {TEXT("berthing"), EKc::Crew}, {TEXT("quarters"), EKc::Crew}, {TEXT("heads"), EKc::Crew}, {TEXT("lounge"), EKc::Crew}, {TEXT("mess"), EKc::Crew},
			{TEXT("galley"), EKc::Crew}, {TEXT("wardroom"), EKc::Crew}, {TEXT("gym"), EKc::Crew}, {TEXT("brig"), EKc::Crew},
			{TEXT("bridge"), EKc::Command}, {TEXT("cic"), EKc::Command}, {TEXT("comms"), EKc::Command}, {TEXT("sensors"), EKc::Command}, {TEXT("weapons_control"), EKc::Command},
			{TEXT("offices"), EKc::Command}, {TEXT("briefing"), EKc::Command}, {TEXT("computer"), EKc::Command}, {TEXT("lab"), EKc::Command},
			{TEXT("weapons"), EKc::Weapons}, {TEXT("medbay"), EKc::Medical}, {TEXT("hangar"), EKc::Hall}, {TEXT("airlock"), EKc::Lock}, {TEXT("vestibule"), EKc::Lock}, {TEXT("tank"), EKc::Tank},
		};
		const EKc* Hit = M.Find(K);
		return Hit ? *Hit : EKc::Other;
	}

	/** Which of the wall bays a kind of room is dressed with: WallA (FERRY GUARD), B (pipe bank), C (louvre), D (lockers), E (hatch), Hold (HOLD FAST), Motto. */
	constexpr int32 kBayKinds = 7;
	const float GBayWeights[(int32)EKc::Num][kBayKinds] = {
		/* Corridor */ {3.0f, 2.0f, 2.0f, 1.0f, 1.2f, 1.4f, 0.9f},
		/* Stairs   */ {1.0f, 2.0f, 2.0f, 0.5f, 2.0f, 0.5f, 0.3f},
		/* Tech     */ {0.7f, 4.0f, 3.0f, 0.7f, 1.5f, 0.4f, 0.2f},
		/* Store    */ {1.0f, 1.5f, 2.0f, 3.0f, 2.0f, 0.4f, 0.2f},
		/* Crew     */ {2.0f, 0.6f, 1.0f, 3.0f, 1.0f, 0.8f, 1.6f},
		/* Command  */ {3.0f, 1.0f, 2.0f, 1.0f, 1.0f, 1.0f, 1.0f},
		/* Weapons  */ {1.5f, 2.5f, 2.0f, 1.0f, 1.5f, 1.0f, 0.4f},
		/* Medical  */ {2.0f, 1.0f, 1.0f, 3.0f, 1.5f, 0.3f, 0.3f},
		/* Hall     */ {1.5f, 1.5f, 2.0f, 2.0f, 2.0f, 1.0f, 1.5f},
		/* Lock     */ {0.5f, 1.0f, 1.0f, 0.5f, 4.0f, 0.5f, 0.1f},
		/* Tank     */ {0.3f, 4.0f, 3.0f, 0.2f, 1.0f, 0.2f, 0.1f},
		/* Other    */ {2.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f},
	};
	const EPiece GBayPieces[kBayKinds] = {EPiece::WallA, EPiece::WallB, EPiece::WallC, EPiece::WallD, EPiece::WallE, EPiece::WallHold, EPiece::WallMotto};
	/** The bays that carry the Mandate's own words: another side's ships have the plain ones. */
	bool IsMandateLettering(EPiece P) { return P == EPiece::WallA || P == EPiece::WallHold || P == EPiece::WallMotto; }

	EPiece PickBay(EKc Kc, EDressSide Side, FRandomStream& Rng)
	{
		float W[kBayKinds];
		float Sum = 0.f;
		for (int32 i = 0; i < kBayKinds; ++i)
		{
			W[i] = GBayWeights[(int32)Kc][i] * ((Side != EDressSide::Mandate && IsMandateLettering(GBayPieces[i])) ? 0.f : 1.f);
			Sum += W[i];
		}
		float R = Rng.FRand() * Sum;
		for (int32 i = 0; i < kBayKinds; ++i)
		{
			R -= W[i];
			if (R <= 0.f && W[i] > 0.f)
			{
				return GBayPieces[i];
			}
		}
		return EPiece::WallC;
	}

	bool IsBannerKind(const FString& K)
	{
		return K == TEXT("lounge") || K == TEXT("mess") || K == TEXT("berthing") || K == TEXT("wardroom") || K == TEXT("briefing") || K == TEXT("hangar") || K == TEXT("cic") || K == TEXT("bridge") || K == TEXT("gym");
	}

	// ============================================================================================================================ the layout of the props
	/** What stands in a kind of room: weighted pieces, a few that are placed first (a gun's breech), how much of the free wall is used, and how many at most. */
	struct FPool
	{
		TArray<TPair<EPiece, float>> Items;
		TArray<EPiece> First;
		float Density = 0.7f;
		int32 MaxCount = 12;
	};

	const TMap<FString, FPool>& Pools()
	{
		static const TMap<FString, FPool> M = []
		{
			TMap<FString, FPool> Out;
			const auto Add = [&Out](std::initializer_list<const TCHAR*> Kinds, std::initializer_list<TPair<EPiece, float>> Items, float Density, int32 Max, std::initializer_list<EPiece> First = {})
			{
				FPool P;
				P.Items = TArray<TPair<EPiece, float>>(Items);
				P.First = TArray<EPiece>(First);
				P.Density = Density;
				P.MaxCount = Max;
				for (const TCHAR* K : Kinds)
				{
					Out.Add(K, P);
				}
			};
			using E = EPiece;
			Add({TEXT("storage")}, {{E::Crate, 4.f}, {E::CrateLong, 2.f}, {E::Barrel, 3.f}, {E::Rack, 4.f}, {E::Locker, 1.f}}, 0.8f, 16);
			Add({TEXT("cargo")}, {{E::Crate, 6.f}, {E::CrateLong, 3.f}, {E::Barrel, 3.f}}, 0.85f, 24);
			Add({TEXT("magazine")}, {{E::CrateLong, 6.f}, {E::Crate, 3.f}, {E::Rack, 2.f}}, 0.8f, 18);
			Add({TEXT("laundry")}, {{E::Locker, 2.f}, {E::Bench, 2.f}, {E::Crate, 1.f}, {E::Barrel, 1.f}}, 0.6f, 8);
			Add({TEXT("workshop")}, {{E::Machine, 3.f}, {E::Motor, 2.f}, {E::Rack, 2.f}, {E::Crate, 2.f}}, 0.7f, 12);
			Add({TEXT("armory")}, {{E::Rack, 4.f}, {E::Locker, 3.f}, {E::CrateLong, 3.f}, {E::Crate, 1.f}}, 0.85f, 16);
			Add({TEXT("machinery")}, {{E::Machine, 4.f}, {E::Motor, 3.f}, {E::Crate, 1.f}}, 0.6f, 10);
			Add({TEXT("engines")}, {{E::Motor, 3.f}, {E::Machine, 3.f}, {E::Crate, 1.f}}, 0.6f, 10);
			Add({TEXT("engineering")}, {{E::Console, 3.f}, {E::Motor, 2.f}, {E::Machine, 2.f}}, 0.6f, 12);
			Add({TEXT("air_plant")}, {{E::Machine, 3.f}, {E::Tank, 2.f}, {E::Motor, 2.f}}, 0.6f, 8);
			Add({TEXT("damage_control")}, {{E::Locker, 3.f}, {E::Rack, 2.f}, {E::Crate, 2.f}, {E::Barrel, 1.f}}, 0.7f, 10);
			Add({TEXT("weapons")}, {{E::CrateLong, 2.f}, {E::Rack, 1.f}, {E::Crate, 1.f}}, 0.4f, 5, {E::Breech});
			Add({TEXT("weapons_control"), TEXT("sensors"), TEXT("comms"), TEXT("computer"), TEXT("cic"), TEXT("bridge"), TEXT("offices"), TEXT("briefing"), TEXT("lab")},
			    {{E::Console, 5.f}, {E::Table, 1.f}, {E::Bench, 1.f}}, 0.7f, 14);
			Add({TEXT("cabins")}, {{E::Bunk, 5.f}, {E::Locker, 2.f}}, 0.8f, 8);
			Add({TEXT("berthing")}, {{E::Bunk, 6.f}, {E::Locker, 2.f}, {E::Bench, 1.f}}, 0.85f, 16);
			Add({TEXT("quarters")}, {{E::Bunk, 2.f}, {E::Locker, 2.f}, {E::Table, 1.f}}, 0.7f, 5);
			Add({TEXT("wardroom"), TEXT("lounge"), TEXT("mess")}, {{E::Table, 4.f}, {E::Bench, 3.f}, {E::Locker, 1.f}}, 0.6f, 10);
			Add({TEXT("galley")}, {{E::Machine, 2.f}, {E::Rack, 2.f}, {E::Crate, 2.f}, {E::Table, 2.f}}, 0.7f, 10);
			Add({TEXT("medbay")}, {{E::Bed, 6.f}, {E::Locker, 2.f}, {E::Console, 1.f}, {E::Table, 1.f}}, 0.75f, 10);
			Add({TEXT("brig")}, {{E::Cell, 6.f}}, 0.6f, 4);
			Add({TEXT("heads")}, {{E::Bench, 2.f}, {E::Locker, 1.f}}, 0.5f, 4);
			Add({TEXT("gym")}, {{E::Bench, 4.f}, {E::Rack, 2.f}}, 0.5f, 8);
			Add({TEXT("hangar")}, {{E::Crate, 4.f}, {E::CrateLong, 3.f}, {E::Barrel, 4.f}, {E::Rack, 1.f}, {E::Machine, 1.f}}, 0.35f, 30);
			Add({TEXT("airlock"), TEXT("vestibule")}, {{E::Locker, 1.f}}, 0.3f, 2);
			return Out;
		}();
		return M;
	}

	EPiece PickPiece(const FPool& P, FRandomStream& Rng)
	{
		float Sum = 0.f;
		for (const TPair<EPiece, float>& I : P.Items)
		{
			Sum += I.Value;
		}
		float R = Rng.FRand() * Sum;
		for (const TPair<EPiece, float>& I : P.Items)
		{
			R -= I.Value;
			if (R <= 0.f)
			{
				return I.Key;
			}
		}
		return P.Items.Last().Key;
	}

	/** A room as the layout sees it: what no prop may stand in (the doorways' mouths, the corners beside them, the middle, the stairs), the lanes the soldiers walk between the doors and to the middle, the props
	 *  placed so far. */
	struct FRoomCtx
	{
		FBox2D Inner = FBox2D(ForceInit);              // the room's box less its walls
		TArray<FBox2D> Keep;
		struct FSeg { FVector2D A, B; };
		TArray<FSeg> Lanes;
		TArray<FProp> Placed;
		double Area = 0.0;

		bool Free(const FBox2D& Fp) const
		{
			if (Fp.Min.X < Inner.Min.X || Fp.Min.Y < Inner.Min.Y || Fp.Max.X > Inner.Max.X || Fp.Max.Y > Inner.Max.Y)
			{
				return false;
			}
			for (const FBox2D& K : Keep)
			{
				if (K.Intersect(Fp))
				{
					return false;
				}
			}
			const FBox2D Lane = Fp.ExpandBy(kLaneR);
			for (const FSeg& S : Lanes)
			{
				if (SegHitsBox(S.A, S.B, Lane))
				{
					return false;
				}
			}
			const FBox2D Gap = Fp.ExpandBy(12.0);
			for (const FProp& P : Placed)
			{
				if (P.Box.Intersect(Gap))
				{
					return false;
				}
			}
			return true;
		}
	};

	void BuildKeepOut(const FAstraBoardMap& Map, int32 Comp, FRoomCtx& R)
	{
		const FBoardComp& C = Map.GetComps()[Comp];
		TArray<FVector2D> Pts;
		for (const int32 Pi : C.Portals)
		{
			const FBoardPortal& P = Map.GetPortals()[Pi];
			const FVector Q = P.PosIn(Comp);
			const FVector2D Q2(Q.X, Q.Y);
			Pts.Add(Q2);
			if (P.bVertical())
			{
				R.Keep.Add(Square(Q2, 170.0));
				continue;
			}
			const double Half = P.Half + 70.0;
			R.Keep.Add(FMath::Abs(P.Normal.X) > 0.7 ? FBox2D(FVector2D(Q2.X - 150.0, Q2.Y - Half), FVector2D(Q2.X + 150.0, Q2.Y + Half)) : FBox2D(FVector2D(Q2.X - Half, Q2.Y - 150.0), FVector2D(Q2.X + Half, Q2.Y + 150.0)));
		}
		for (const int32 Si : C.Slots)
		{
			const FBoardSlot& S = Map.GetSlots()[Si];
			R.Keep.Add(Square(FVector2D(S.Pos.X, S.Pos.Y), 55.0));
			R.Keep.Add(Square(FVector2D(S.Peek.X, S.Peek.Y), 55.0));
		}
		const FVector Ctr = Map.CentreOf(Comp);
		const FVector2D Mid(Ctr.X, Ctr.Y);
		R.Keep.Add(Square(Mid, 110.0));
		Pts.Add(Mid);
		for (int32 i = 0; i < Pts.Num(); ++i)
		{
			for (int32 j = i + 1; j < Pts.Num(); ++j)
			{
				R.Lanes.Add({Pts[i], Pts[j]});
			}
		}
	}

	/** The pieces of a free stretch along a wall once some stretches are taken out of it. */
	void SubtractInterval(TArray<FVector2D>& Free, double A, double B)
	{
		TArray<FVector2D> Out;
		for (const FVector2D& I : Free)
		{
			if (B <= I.X || A >= I.Y)
			{
				Out.Add(I);
				continue;
			}
			if (A > I.X)
			{
				Out.Add(FVector2D(I.X, A));
			}
			if (B < I.Y)
			{
				Out.Add(FVector2D(B, I.Y));
			}
		}
		Free = MoveTemp(Out);
	}

	void LayoutRoom(const FAstraBoardMap& Map, uint32 Seed, int32 Comp, TArray<FProp>& Out)
	{
		const FBoardComp& C = Map.GetComps()[Comp];
		const FBox& B = C.Box;
		const double Sx = B.Max.X - B.Min.X, Sy = B.Max.Y - B.Min.Y, H = B.Max.Z - B.Min.Z;
		if (C.bCorridor || Sx < 160.0 || Sy < 160.0 || H < 200.0)
		{
			return;
		}
		const FString Kind = C.Kind.ToString();
		const FPool* Pool = Pools().Find(Kind);
		if (!Pool)
		{
			return;
		}
		FRoomCtx R;
		R.Inner = FBox2D(FVector2D(B.Min.X + kWall, B.Min.Y + kWall), FVector2D(B.Max.X - kWall, B.Max.Y - kWall));
		BuildKeepOut(Map, Comp, R);
		FRandomStream Rng((int32)Mix(Seed, (uint32)Comp));
		const double AreaCap = 0.28 * (Sx - 2 * kWall) * (Sy - 2 * kWall);
		const auto Put = [&](EPiece P, const FVector2D& Org, float Yaw)
		{
			const FPieceDef& D = Def(P);
			FProp Pr;
			Pr.Piece = P;
			Pr.Pos = FVector(Org.X, Org.Y, B.Min.Z);
			Pr.Yaw = Yaw;
			const FBox2D Fp = TurnedFootprint(D, Yaw);
			Pr.Box = FBox2D(Org + Fp.Min, Org + Fp.Max);
			Pr.Height = D.Height;
			Pr.Comp = Comp;
			R.Area += (Fp.Max.X - Fp.Min.X) * (Fp.Max.Y - Fp.Min.Y);
			R.Placed.Add(Pr);
		};
		int32 Order[4] = {0, 1, 2, 3};
		for (int32 i = 3; i > 0; --i)
		{
			Swap(Order[i], Order[Rng.RandHelper(i + 1)]);
		}
		int32 FirstLeft = Pool->First.Num();
		for (int32 Oi = 0; Oi < 4 && R.Placed.Num() < Pool->MaxCount && R.Area < AreaCap; ++Oi)
		{
			const int32 Face = Order[Oi];
			FFaceGeo G;
			AstraBoardInterior::FaceGeo(Map, Comp, Face, G);
			const double Wi = G.Plane - G.Sign * kWall;                                 // the wall's visible face
			const double Perp = G.bX ? Sx : Sy;                                         // the room's width across this wall
			const double MaxDepth = FMath::Min(200.0, 0.5 * (Perp - 260.0));
			if (MaxDepth < 40.0)
			{
				continue;
			}
			TArray<FVector2D> Free;
			Free.Add(FVector2D(G.T0 + kWall + 6.0, G.T1 - kWall - 6.0));
			for (const FOpening& O : G.Opens)
			{
				SubtractInterval(Free, O.S0 - 70.0, O.S1 + 70.0);
			}
			const float Yaw = PropYawOfFace(Face);
			for (const FVector2D& Iv : Free)
			{
				double T = Iv.X + Rng.FRandRange(0.f, 30.f);
				int32 Guard = 0, Fails = 0;
				while (T < Iv.Y - 40.0 && Guard++ < 48 && R.Placed.Num() < Pool->MaxCount && R.Area < AreaCap)
				{
					const EPiece Pc = FirstLeft > 0 ? Pool->First[Pool->First.Num() - FirstLeft] : PickPiece(*Pool, Rng);
					const FPieceDef& D = Def(Pc);
					const FBox2D Fp = TurnedFootprint(D, Yaw);
					const double Along = G.bX ? (Fp.Max.Y - Fp.Min.Y) : (Fp.Max.X - Fp.Min.X);
					const double Depth = G.bX ? (Fp.Max.X - Fp.Min.X) : (Fp.Max.Y - Fp.Min.Y);
					if (Depth > MaxDepth || T + Along > Iv.Y)
					{
						if (++Fails > 4)
						{
							break;
						}
						continue;
					}
					FVector2D Org;
					if (G.bX)
					{
						Org.X = G.Sign > 0.0 ? Wi - kPropGap - Fp.Max.X : Wi + kPropGap - Fp.Min.X;
						Org.Y = T - Fp.Min.Y;
					}
					else
					{
						Org.Y = G.Sign > 0.0 ? Wi - kPropGap - Fp.Max.Y : Wi + kPropGap - Fp.Min.Y;
						Org.X = T - Fp.Min.X;
					}
					if (R.Free(FBox2D(Org + Fp.Min, Org + Fp.Max)))
					{
						Put(Pc, Org, Yaw);
						FirstLeft = FMath::Max(0, FirstLeft - 1);
						T += Along + Rng.FRandRange(12.f, 55.f);
						if (Rng.FRand() > Pool->Density)
						{
							T += Rng.FRandRange(80.f, 260.f);                           // (a stretch of bare wall: no room is wall to wall with things)
						}
					}
					else
					{
						T += 35.0;
					}
				}
			}
		}
		// the one big thing of a hall: main engineering's reactor stack stands off the walls, where the soldiers' lanes and the middle leave room
		if (Kind == TEXT("engineering") && Sx > 600.0 && Sy > 600.0)
		{
			const FVector Ctr = Map.CentreOf(Comp);
			TArray<FVector2D> Cand;
			for (double X = R.Inner.Min.X + 260.0; X <= R.Inner.Max.X - 260.0; X += 80.0)
			{
				for (double Y = R.Inner.Min.Y + 260.0; Y <= R.Inner.Max.Y - 260.0; Y += 80.0)
				{
					Cand.Add(FVector2D(X, Y));
				}
			}
			Cand.Sort([&Ctr](const FVector2D& A, const FVector2D& B2) { return FVector2D::DistSquared(A, FVector2D(Ctr.X, Ctr.Y)) < FVector2D::DistSquared(B2, FVector2D(Ctr.X, Ctr.Y)); });
			for (const FVector2D& P : Cand)
			{
				const FBox2D Fp = TurnedFootprint(Def(EPiece::Reactor), 0.f);
				if (R.Free(FBox2D(P + Fp.Min, P + Fp.Max)))
				{
					Put(EPiece::Reactor, P, 0.f);
					break;
				}
			}
		}
		Out.Append(R.Placed);
	}
}

// ================================================================================================================== the catalog's entries
const FPieceDef& AstraBoardDress::Def(EPiece P)
{
	return GDefs[FMath::Clamp((int32)P, 0, (int32)EPiece::Count - 1)];
}

FString AstraBoardDress::MeshPath(EPiece P)
{
	return FString::Printf(TEXT("/Game/ASTRA/Kit/Board/%s.%s"), Def(P).Mesh, Def(P).Mesh);
}

bool AstraBoardDress::FindPiece(const FString& Key, EPiece& Out)
{
	for (int32 i = 0; i < (int32)EPiece::Count; ++i)
	{
		if (Key == GDefs[i].Key)
		{
			Out = (EPiece)i;
			return true;
		}
	}
	return false;
}

EDressSide AstraBoardDress::SideOfStyle(const FString& PlanStyle)
{
	if (PlanStyle.Equals(TEXT("mandate"), ESearchCase::IgnoreCase))
	{
		return EDressSide::Mandate;
	}
	if (PlanStyle.Equals(TEXT("guild"), ESearchCase::IgnoreCase))
	{
		return EDressSide::Guild;
	}
	return EDressSide::Astra;
}

uint32 AstraBoardDress::SeedOf(FName Class)
{
	const FString K = Class.ToString().ToLower();
	return FCrc::StrCrc32(*K);
}

TArrayView<const FProp> FLayout::PropsOf(int32 Comp) const
{
	if (!First.IsValidIndex(Comp + 1))
	{
		return TArrayView<const FProp>();
	}
	return TArrayView<const FProp>(Props.GetData() + First[Comp], First[Comp + 1] - First[Comp]);
}

TSharedRef<FLayout> AstraBoardDress::MakeLayout(FBoardShipPlan& Plan)
{
	TSharedRef<FLayout> L = MakeShared<FLayout>();
	if (!Plan.Map.IsValid() || Plan.Class.ToString().Equals(TEXT("aquila"), ESearchCase::IgnoreCase))
	{
		return L;
	}
	const FAstraBoardMap& Map = *Plan.Map;
	const int32 N = Map.GetComps().Num();
	const uint32 Seed = SeedOf(Plan.Class);
	TArray<FBox2D> BlockAll;
	TArray<int32> BlockFirst;
	L->First.Reserve(N + 1);
	BlockFirst.Reserve(N + 1);
	for (int32 c = 0; c < N; ++c)
	{
		L->First.Add(L->Props.Num());
		BlockFirst.Add(BlockAll.Num());
		LayoutRoom(Map, Seed, c, L->Props);
		for (int32 i = L->First[c]; i < L->Props.Num(); ++i)
		{
			BlockAll.Add(L->Props[i].Box);
		}
	}
	L->First.Add(L->Props.Num());
	BlockFirst.Add(BlockAll.Num());
	Plan.Map->SetBlocks(MoveTemp(BlockAll), MoveTemp(BlockFirst));
	return L;
}

// ================================================================================================================== the dressing of a room
namespace
{
	/** One room being dressed: its walls face by face, its ceiling, its floor, the doors, the props of the layout, what the war has left. */
	class FDresser
	{
	public:
		FDresser(const FDressContext& InCtx, int32 InComp, FRoomDress& InOut)
			: Ctx(InCtx), Comp(InComp), Out(InOut), Rng(0)
		{
			Plan = Ctx.Plan;
			Map = Plan && Plan->Map.IsValid() ? Plan->Map.Get() : nullptr;
			if (!Map || !Map->GetComps().IsValidIndex(Comp))
			{
				Map = nullptr;
				return;
			}
			C = &Map->GetComps()[Comp];
			B = C->Box;
			Sx = B.Max.X - B.Min.X;
			Sy = B.Max.Y - B.Min.Y;
			H = B.Max.Z - B.Min.Z;
			if (Sx < 60.0 || Sy < 60.0 || H < 120.0)
			{
				Map = nullptr;
				return;
			}
			Kind = C->Kind.ToString();
			Kc = ClassOfKind(Kind);
			Mood = Ctx.Moods ? Ctx.Moods->Find(Comp) : nullptr;
			bGutted = Mood && Mood->bGutted;
			bDark = Mood && Mood->Dark();
			Burnt = Mood ? FMath::Clamp(Mood->Fire * 1.2f + Mood->Smoke * 0.6f + (bGutted ? 0.7f : 0.f), 0.f, 0.85f) : 0.f;
			Rng = FRandomStream((int32)Mix(Ctx.Seed, (uint32)Comp + 0x51edu));
		}

		bool Ok() const { return Map != nullptr; }

		void Run(const FLayout* Layout)
		{
			if (Layout)
			{
				Props = Layout->PropsOf(Comp);
			}
			for (int32 f = 0; f < 4; ++f)
			{
				Face(f);
			}
			Ceiling();
			Floor();
			if (Ctx.Level >= 2)
			{
				PlaceProps();
				Damage();
			}
		}

	private:
		const FDressContext& Ctx;
		int32 Comp;
		FRoomDress& Out;
		FRandomStream Rng;
		const FBoardShipPlan* Plan = nullptr;
		const FAstraBoardMap* Map = nullptr;
		const FBoardComp* C = nullptr;
		FBox B = FBox(ForceInit);
		double Sx = 0.0, Sy = 0.0, H = 0.0;
		FString Kind;
		EKc Kc = EKc::Other;
		const FBoardRoomMood* Mood = nullptr;
		bool bGutted = false, bDark = false;
		float Burnt = 0.f;
		TArrayView<const FProp> Props;
		int32 LampCount = 0;

		void Add(EPiece P, const FVector& Pos, const FRotator& Rot, const FVector& Scale = FVector::OneVector, int32 Door = INDEX_NONE)
		{
			FPlacement Pl;
			Pl.Piece = P;
			Pl.Pos = Pos;
			Pl.Rot = Rot;
			Pl.Scale = Scale;
			Pl.Comp = Comp;
			Pl.Door = Door;
			Out.Pieces.Add(Pl);
		}

		/** How the room's lamps are: the lit ones of a ship with power, the red ones of a hulk (and of a dark room's every third), the dead ones of a room the war has put out. */
		ELamp LampState(int32 Index) const
		{
			if (bGutted)
			{
				return ELamp::Dead;
			}
			if (bDark)
			{
				return Index % 3 == 0 ? ELamp::Red : ELamp::Dead;
			}
			return Ctx.bHulk ? ELamp::Red : ELamp::Lit;
		}

		static EPiece LampPiece(ELamp S) { return S == ELamp::Lit ? EPiece::Lamp : (S == ELamp::Red ? EPiece::LampRed : EPiece::LampDead); }

		// ------------------------------------------------------------------------------------------------------------------------ a wall
		void Face(int32 f)
		{
			FFaceGeo G;
			AstraBoardInterior::FaceGeo(*Map, Comp, f, G);
			const FFaceFrame Fr = FrameOfFace(f);
			const bool bX = G.bX;
			const double Wi = G.Plane - G.Sign * kWall;                                    // the wall's visible face
			const double ASign = bX ? Fr.Along.Y : Fr.Along.X;                             // whether a piece's x runs towards larger values along the wall
			const double Z0 = B.Min.Z;
			const auto PointAt = [&](double T, double Into, double Z) -> FVector
			{
				const double W = Wi + (bX ? Fr.In.X : Fr.In.Y) * Into;
				return bX ? FVector(W, T, Z) : FVector(T, W, Z);
			};
			const auto Start = [&](double T0, double T1) { return ASign > 0.0 ? T0 : T1; };
			const auto EndInset = [&](double S, bool bStart) -> double
			{
				if (bStart ? FMath::Abs(S - G.T0) < 1.5 : FMath::Abs(S - G.T1) < 1.5)
				{
					return f < 2 ? kWall : kWall + kRibD + 1.0;                           // a corner: the X walls own it (and stand a rib in it); the Y walls keep clear of that rib
				}
				for (const FOpening& O : G.Opens)
				{
					if (bStart ? FMath::Abs(O.S1 - S) < 1.5 : FMath::Abs(O.S0 - S) < 1.5)
					{
						return !O.bFramed ? 0.0 : (Map->GetPortals()[O.Portal].Kind == FBoardPortal::EKind::Blast ? kBlastJambW : kJambW);
					}
				}
				return 0.0;
			};
			const bool bBanners = Ctx.Level >= 2 && Ctx.Side == EDressSide::Mandate && IsBannerKind(Kind);
			EPiece Last = EPiece::Count;
			int32 WallLamps = 0;
			for (const FWallRun& R : G.Runs)
			{
				for (const FVector2D& Sol : R.Solid)
				{
					if (Sol.X > 6.0 || Sol.Y < 120.0)
					{
						continue;                                                           // (a stretch of wall above a gap: the door's own header closes it)
					}
					const double Top = Sol.Y;
					double S0 = R.S0 + EndInset(R.S0, true), S1 = R.S1 - EndInset(R.S1, false);
					const double RibScale = FMath::Min(Top, 600.0) / kRibH;
					const auto Rib = [&](double T0, double T1) { Add(EPiece::Rib, PointAt(Start(T0, T1), kNudge, Z0), YawRot(Fr.Yaw), FVector(1.0, 1.0, RibScale)); };
					if (f < 2 && FMath::Abs(R.S0 - G.T0) < 1.5)
					{
						Rib(S0, S0 + kRibW);
						S0 += kRibW;
					}
					if (f < 2 && FMath::Abs(R.S1 - G.T1) < 1.5)
					{
						Rib(S1 - kRibW, S1);
						S1 -= kRibW;
					}
					const double L = S1 - S0;
					if (L < 40.0)
					{
						continue;
					}
					const double Sz = FMath::Min(1.0, FMath::Min(Top, kBayH) / kBayH);
					const bool bPlain = L < 140.0;
					const int32 Nb = bPlain ? FMath::Max(1, FMath::RoundToInt(L / 100.0)) : FMath::Max(1, FMath::RoundToInt(L / kBay));
					const double Wb = L / Nb, Px = bPlain ? 100.0 : kBay;
					const int32 BannerBay = (!bPlain && bBanners && Nb >= 2 && Rng.FRand() < 0.4f) ? Rng.RandHelper(Nb) : INDEX_NONE;
					for (int32 i = 0; i < Nb; ++i)
					{
						const double T0 = S0 + i * Wb, T1 = T0 + Wb;
						if (i == BannerBay)
						{
							const double Tm = 0.5 * (T0 + T1);                              // a banner on a plain wall: two plain bays and the cloth over them
							Add(EPiece::WallPlain, PointAt(Start(T0, Tm), kNudge, Z0), YawRot(Fr.Yaw), FVector((Tm - T0) / 100.0, 1.0, Sz));
							Add(EPiece::WallPlain, PointAt(Start(Tm, T1), kNudge, Z0), YawRot(Fr.Yaw), FVector((T1 - Tm) / 100.0, 1.0, Sz));
							Add(EPiece::Banner, PointAt(Tm, 12.0, Z0), YawRot(PropYawOfFace(f)));
							Last = EPiece::WallPlain;
							continue;
						}
						EPiece Pc = EPiece::WallPlain;
						if (!bPlain)
						{
							Pc = Rng.FRand() < Burnt ? EPiece::WallF : PickBay(Kc, Ctx.Side, Rng);
							if (Pc == Last && Pc != EPiece::WallF)
							{
								Pc = PickBay(Kc, Ctx.Side, Rng);                          // (not the same bay twice running, if a second pick says otherwise)
							}
						}
						Last = Pc;
						Add(Pc, PointAt(Start(T0, T1), kNudge, Z0), YawRot(Fr.Yaw), FVector((T1 - T0) / Px, 1.0, Sz));
					}
					for (int32 k = 2; k < Nb; k += 2)
					{
						const double Tb = S0 + k * Wb;
						Rib(Tb - 0.5 * kRibW, Tb + 0.5 * kRibW);
					}
					if (Top > kBayH + 30.0)
					{
						const int32 Nc = FMath::Max(1, FMath::RoundToInt(L / kRun));
						for (int32 i = 0; i < Nc; ++i)
						{
							const double T0 = S0 + i * L / Nc, T1 = S0 + (i + 1) * L / Nc;
							Add(EPiece::Cornice, PointAt(Start(T0, T1), kNudge, Z0 + kBayH), YawRot(Fr.Yaw), FVector((T1 - T0) / kBay, 1.0, 1.0));
						}
					}
					// the red guide lights along the foot of a corridor's walls, and of a dark room's
					if (C->bCorridor || bDark || Ctx.bHulk)
					{
						const int32 Ng = FMath::Max(1, FMath::RoundToInt(L / kRun));
						for (int32 i = 0; i < Ng; ++i)
						{
							const double T0 = S0 + i * L / Ng, T1 = S0 + (i + 1) * L / Ng;
							Add(EPiece::Guide, PointAt(Start(T0, T1), 14.0, Z0 + kNudge), YawRot(Fr.Yaw), FVector((T1 - T0) / kBay, 1.0, 1.0));
						}
					}
					// a tall hall (a hangar) is lit from its walls: caged lamps on their sides, at a gantry's height
					if (H > kTallHall)
					{
						for (double T = S0 + 150.0; T < S1 - 100.0 && WallLamps < 8; T += 700.0, ++WallLamps)
						{
							const ELamp St = LampState(LampCount++);
							const FRotator Rot = FRotationMatrix::MakeFromXZ(FVector(Fr.Along.X, Fr.Along.Y, 0.0), FVector(-Fr.In.X, -Fr.In.Y, 0.0)).Rotator();
							Add(LampPiece(St), PointAt(T, 1.0, Z0 + 480.0), Rot);
							Out.Lamps.Add({PointAt(T, 24.0, Z0 + 480.0), St, Comp});
						}
					}
				}
			}
			Openings(G, Fr, PointAt);
		}

		template <typename PointFn>
		void Openings(const FFaceGeo& G, const FFaceFrame& Fr, const PointFn& PointAt)
		{
			const double Z0 = B.Min.Z;
			const bool bX = G.bX;
			for (const FOpening& O : G.Opens)
			{
				if (!O.bFramed)
				{
					continue;
				}
				const FBoardPortal& P = Map->GetPortals()[O.Portal];
				const bool bBlast = P.Kind == FBoardPortal::EKind::Blast;
				const double Cn = 0.5 * (O.S0 + O.S1), W = O.S1 - O.S0;
				// the way through is a tunnel: this room's wall, the gap the plan leaves between the two rooms (a wall is thirty centimetres, a pressure bulkhead forty), the other room's wall. The frame is made once,
				// across the whole of it
				const FBox& Ob = Map->GetComps()[P.Other(Comp)].Box;
				const double Gap = FMath::Clamp(bX ? (G.Sign > 0.0 ? Ob.Min.X - G.Plane : G.Plane - Ob.Max.X) : (G.Sign > 0.0 ? Ob.Min.Y - G.Plane : G.Plane - Ob.Max.Y), 0.0, 90.0);
				const double Tunnel = 2.0 * kWall + Gap;
				// the sign over the door that says where it goes: every room has its own side's, on the header's face (a few centimetres proud of the wall)
				if (Ctx.Level >= 2 && Plan->Dmg.IsValid() && Plan->Dmg->Comps.IsValidIndex(P.Other(Comp)))
				{
					FDoorSign Sg;
					Sg.Pos = PointAt(Cn, 5.5, Z0 + O.Top + (bBlast ? 25.0 : 20.0));
					Sg.Facing = Fr.In;
					Sg.Text = Plan->Dmg->Comps[P.Other(Comp)].Name.ToUpper();
					Sg.Comp = Comp;
					if (!Sg.Text.IsEmpty())
					{
						Out.Signs.Add(Sg);
					}
				}
				if (P.A != Comp)
				{
					continue;                                                               // (the frame stands in both rooms' walls: the first room makes it)
				}
				const double MidPlane = G.Plane + G.Sign * 0.5 * Gap;                               // the middle of the tunnel
				const auto OnPlane = [&](double Plane, double T, double Z) { return bX ? FVector(Plane, T, Z) : FVector(T, Plane, Z); };
				const FRotator Yaw = YawRot(Fr.Yaw);
				// the frame's pieces are made 44, 46, 56 and 61 centimetres deep (through the wall): stretched to the tunnel and four centimetres more
				const double Through = Tunnel + 8.0;
				if (bBlast)
				{
					Add(EPiece::BlastJamb, OnPlane(MidPlane, O.S0 - 0.5 * kBlastJambW, Z0 + O.Bot), Yaw, FVector(1.0, Through / 56.0, 1.0));
					Add(EPiece::BlastJamb, OnPlane(MidPlane, O.S1 + 0.5 * kBlastJambW, Z0 + O.Bot), Yaw, FVector(1.0, Through / 56.0, 1.0));
					Add(EPiece::BlastHeader, OnPlane(MidPlane, Cn, Z0 + O.Top), Yaw, FVector(W / 100.0, Through / 61.0, 1.0));
					Add(EPiece::BlastLeaf, OnPlane(G.Plane - G.Sign * 0.5 * (kWall - 2.0), Cn, Z0 + O.Bot), Yaw, FVector(W / 100.0, 1.0, 1.0), P.Door);           // (where the leaf's collision stands)
				}
				else
				{
					Add(EPiece::Jamb, OnPlane(MidPlane, O.S0 - 0.5 * kJambW, Z0 + O.Bot), Yaw, FVector(1.0, Through / 44.0, 1.0));
					Add(EPiece::Jamb, OnPlane(MidPlane, O.S1 + 0.5 * kJambW, Z0 + O.Bot), Yaw, FVector(1.0, Through / 44.0, 1.0));
					Add(EPiece::DoorHeader, OnPlane(MidPlane, Cn, Z0 + O.Top), Yaw, FVector(W / 100.0, Through / 46.0, 1.0));
				}
				Add(EPiece::Threshold, OnPlane(MidPlane, Cn, Z0 + O.Bot + 0.2), Yaw, FVector(W / 180.0 * (bBlast ? 1.1 : 1.0), (Gap + 2.0 * kWall) / 50.0, 1.0));       // (it covers the gap between the two floors)
			}
		}

		// ------------------------------------------------------------------------------------------------------------------------ the ceiling
		void Ceiling()
		{
			if (H > kTallHall)
			{
				return;                                                                     // (a hall that tall is lit from its walls; nothing hangs from a ceiling a gantry's reach away)
			}
			const double CeilZ = B.Max.Z;
			const bool bLongX = Sx >= Sy;
			const double L = bLongX ? Sx : Sy, Wd = bLongX ? Sy : Sx;
			const double U0 = bLongX ? B.Min.X : B.Min.Y, V0 = bLongX ? B.Min.Y : B.Min.X;
			const float RunYaw = bLongX ? 0.f : 90.f;
			const auto At = [&](double U, double V, double Z) { return bLongX ? FVector(U, V, Z) : FVector(V, U, Z); };
			const double Lu0 = U0 + kWall + 8.0, Lu1 = U0 + L - kWall - 8.0, Len = Lu1 - Lu0;
			if (Len < 120.0)
			{
				return;
			}
			const int32 N = FMath::Max(1, FMath::RoundToInt(Len / kRun));
			const double Wp = Len / N;
			TArray<double> PipeV, TrayV;
			if (Wd >= 230.0)
			{
				const double Edge = kWall + 44.0;                                            // a pipe's middle from the box's side: its edge keeps 22 cm off the wall's face
				PipeV.Add(V0 + Edge);
				PipeV.Add(V0 + Wd - Edge);
			}
			if (C->bCorridor)
			{
				TrayV.Add(V0 + 0.5 * Wd);
			}
			else
			{
				const int32 Nt = FMath::Clamp(FMath::RoundToInt(Wd / 330.0), 1, 6);
				for (int32 i = 0; i < Nt; ++i)
				{
					TrayV.Add(V0 + Wd * (i + 0.5) / Nt);
				}
			}
			while (TrayV.Num() > 1 && (PipeV.Num() + TrayV.Num()) * N > 150)
			{
				TrayV.RemoveAt(TrayV.Num() - 1);
			}
			for (const double V : PipeV)
			{
				for (int32 i = 0; i < N; ++i)
				{
					Add(EPiece::Pipes, At(Lu0 + i * Wp, V, CeilZ), YawRot(RunYaw), FVector(Wp / kBay, 1.0, 1.0));
				}
			}
			for (const double V : TrayV)
			{
				for (int32 i = 0; i < N; ++i)
				{
					Add(EPiece::Tray, At(Lu0 + i * Wp, V, CeilZ), YawRot(RunYaw), FVector(Wp / kBay, 1.0, 1.0));
				}
			}
			// the lamps ride the trays, one every three metres, at most fourteen in a room (the rest of a long hall is lit by the same few)
			const int32 Nl = FMath::Max(1, FMath::FloorToInt32(Len / 300.0));
			TArray<FVector2D> LampAt;
			for (const double V : TrayV)
			{
				for (int32 i = 0; i < Nl; ++i)
				{
					LampAt.Add(FVector2D(Lu0 + (i + 0.5) * Len / Nl, V));
				}
			}
			const int32 Stride = FMath::Max(1, FMath::CeilToInt32(LampAt.Num() / 14.0));
			for (int32 i = 0; i < LampAt.Num(); i += Stride)
			{
				const ELamp St = LampState(LampCount++);
				Add(LampPiece(St), At(LampAt[i].X, LampAt[i].Y, CeilZ), YawRot(RunYaw));
				Out.Lamps.Add({At(LampAt[i].X, LampAt[i].Y, CeilZ - 30.0), St, Comp});
			}
			// a grille for the air in the bigger rooms
			const int32 Nv = FMath::Min(4, FMath::FloorToInt32(Sx * Sy / 600000.0));
			for (int32 i = 0; i < Nv; ++i)
			{
				Add(EPiece::Vent, At(Lu0 + Rng.FRandRange(60.f, (float)(Len - 60.0)), V0 + Rng.FRandRange(80.f, (float)(Wd - 80.0)), CeilZ), YawRot(RunYaw));
			}
		}

		// ------------------------------------------------------------------------------------------------------------------------ the floor
		void Floor()
		{
			const double Area = Sx * Sy;
			double Cell = kPlate;
			if (Area > kPlate * kPlate * 80.0)
			{
				Cell = kPlate * FMath::CeilToDouble(FMath::Sqrt(Area / (kPlate * kPlate * 80.0)));   // (a hangar's floor is large plates: eighty of them at most)
			}
			const int32 Nx = FMath::Max(1, FMath::RoundToInt(Sx / Cell)), Ny = FMath::Max(1, FMath::RoundToInt(Sy / Cell));
			const double Px = Sx / Nx, Py = Sy / Ny;
			for (int32 i = 0; i < Nx; ++i)
			{
				for (int32 j = 0; j < Ny; ++j)
				{
					Add(EPiece::Floor, FVector(B.Min.X + i * Px, B.Min.Y + j * Py, B.Min.Z + 0.3), FRotator::ZeroRotator, FVector(Px / kBay, Py / kBay, 1.0));       // (the plate is two metres: a larger cell is the same plate, larger)
				}
			}
		}

		// ------------------------------------------------------------------------------------------------------------------------ the props
		void PlaceProps()
		{
			for (const FProp& P : Props)
			{
				Add(P.Piece, P.Pos, YawRot(P.Yaw));
				const FPieceDef& D = Def(P.Piece);
				if (D.bSolid)
				{
					const FVector2D Mid = P.Box.GetCenter(), Hf = P.Box.GetExtent() - FVector2D(3.0, 3.0);
					Out.Blocks.Add({FVector(Mid.X, Mid.Y, B.Min.Z + 0.5 * P.Height), FVector(FMath::Max(1.0, Hf.X), FMath::Max(1.0, Hf.Y), 0.5 * P.Height), Comp});
				}
			}
		}

		bool InProp(const FVector2D& P, double Pad) const
		{
			for (const FProp& Pr : Props)
			{
				if (Pr.Box.ExpandBy(Pad).IsInside(P))
				{
					return true;
				}
			}
			return false;
		}

		FVector2D FreeSpot(double Margin)
		{
			FVector2D P(0.5 * (B.Min.X + B.Max.X), 0.5 * (B.Min.Y + B.Max.Y));
			for (int32 Try = 0; Try < 12; ++Try)
			{
				P = FVector2D(Rng.FRandRange((float)(B.Min.X + Margin), (float)FMath::Max(B.Min.X + Margin + 1.0, B.Max.X - Margin)), Rng.FRandRange((float)(B.Min.Y + Margin), (float)FMath::Max(B.Min.Y + Margin + 1.0, B.Max.Y - Margin)));
				if (!InProp(P, 30.0))
				{
					break;
				}
			}
			return P;
		}

		// ------------------------------------------------------------------------------------------------------------------------ what the war has left
		void Damage()
		{
			if (!Mood)
			{
				return;
			}
			const double Area = Sx * Sy;
			const double Z0 = B.Min.Z;
			if (bGutted || Mood->Burns())
			{
				const int32 Nd = FMath::Clamp(FMath::RoundToInt((float)(Area / 300000.0) * (bGutted ? 2.f : 1.f)) + (bGutted ? 2 : 1), 1, 8);
				for (int32 i = 0; i < Nd; ++i)
				{
					const FVector2D P = FreeSpot(90.0);
					Add(EPiece::Debris, FVector(P.X, P.Y, Z0 + kNudge), YawRot(Rng.FRandRange(0.f, 360.f)), FVector(Rng.FRandRange(0.8f, 1.3f), Rng.FRandRange(0.8f, 1.3f), 1.0));
				}
			}
			// cut cables hang from the ceilings of the rooms that have lost their power, and spit
			if ((bDark || bGutted) && H <= kTallHall)
			{
				const int32 Nc = bGutted ? 3 : 2;
				for (int32 i = 0; i < Nc; ++i)
				{
					const FVector2D P = FreeSpot(70.0);
					Add(EPiece::Cables, FVector(P.X, P.Y, B.Max.Z), YawRot(Rng.FRandRange(0.f, 360.f)));
					Out.Fx.Add({FWarMark::EKind::Spark, FVector(P.X, P.Y, B.Max.Z - 70.0), 40.f, bGutted ? 1.f : 0.6f, Comp});
				}
			}
			// fire and smoke (what the war's picture of the room says)
			if (Mood->Burns())
			{
				const int32 Nf = FMath::Clamp(1 + FMath::FloorToInt32(Mood->Fire * 4.f), 1, 4);
				for (int32 i = 0; i < Nf; ++i)
				{
					FVector Pos;
					if (Props.Num() > 0 && Rng.FRand() < 0.6f)
					{
						const FProp& Pr = Props[Rng.RandHelper(Props.Num())];
						const FVector2D M = Pr.Box.GetCenter();
						Pos = FVector(M.X, M.Y, Z0 + Pr.Height * 0.7);                       // a burning crate, a burning cot
					}
					else
					{
						const FVector2D P = FreeSpot(90.0);
						Pos = FVector(P.X, P.Y, Z0);
					}
					Out.Fx.Add({FWarMark::EKind::Flame, Pos, FMath::Lerp(80.f, 150.f, FMath::Clamp(Mood->Fire, 0.f, 1.f)), FMath::Clamp(Mood->Fire, 0.2f, 1.f), Comp});
				}
			}
			if (Mood->Smoke >= 0.15f || Mood->Burns())
			{
				const int32 Ns = FMath::Clamp(2 + FMath::FloorToInt32(Mood->Smoke * 3.f) + (Mood->Burns() ? 1 : 0), 2, 5);
				for (int32 i = 0; i < Ns; ++i)
				{
					const FVector2D P = FreeSpot(60.0);
					Out.Fx.Add({FWarMark::EKind::Smoke, FVector(P.X, P.Y, FMath::Min(B.Max.Z - 90.0, Z0 + 260.0)), Rng.FRandRange(260.f, 420.f), FMath::Clamp(Mood->Smoke + (Mood->Burns() ? 0.3f : 0.f), 0.25f, 0.9f), Comp});
				}
			}
		}
	};
}

void AstraBoardDress::DressRoom(const FDressContext& Ctx, const FLayout* Layout, int32 Comp, FRoomDress& Out)
{
	if (Ctx.Level <= 0)
	{
		return;
	}
	FDresser D(Ctx, Comp, Out);
	if (D.Ok())
	{
		D.Run(Layout);
	}
}

void AstraBoardDress::DressFallen(const FDressContext& Ctx, const TArray<FFallen>& Fallen, TArray<FPlacement>& Out)
{
	if (!Ctx.Plan || !Ctx.Plan->Map.IsValid() || Ctx.Level < 2)
	{
		return;
	}
	const FAstraBoardMap& Map = *Ctx.Plan->Map;
	for (const FFallen& F : Fallen)
	{
		if (!Map.GetComps().IsValidIndex(F.Comp))
		{
			continue;
		}
		const FBox& B = Map.GetComps()[F.Comp].Box;
		const uint32 Hs = Mix(Mix(Ctx.Seed, (uint32)F.Person + 17u), (uint32)F.Comp);
		const float Margin = FMath::Min(115.f, 0.5f * (float)FMath::Min(B.Max.X - B.Min.X, B.Max.Y - B.Min.Y) - 20.f);
		const FVector P = Map.Inset(F.Comp, F.Pos, FMath::Max(40.f, Margin));               // (off the walls and out of the props)
		FPlacement Pl;
		Pl.Piece = (EPiece)((int32)EPiece::BodyA + (int32)(Hs % 3u));
		Pl.Pos = FVector(P.X, P.Y, B.Min.Z + 0.3);
		Pl.Rot = YawRot((float)((Hs >> 4) % 360u));
		Pl.Scale = FVector(1.0, ((Hs >> 13) & 1u) ? -1.0 : 1.0, 1.0);
		Pl.Comp = F.Comp;
		Out.Add(Pl);
	}
}

// ================================================================================================================== the bench's numbers
void FTally::Add(const FRoomDress& R, const TArray<int32>& TrisOf)
{
	for (const FPlacement& P : R.Pieces)
	{
		++Pieces[(int32)Def(P.Piece).Frame];
		Tris += TrisOf.IsValidIndex((int32)P.Piece) ? TrisOf[(int32)P.Piece] : 0;
	}
	Blocks += R.Blocks.Num();
	Lamps += R.Lamps.Num();
	Signs += R.Signs.Num();
	Fx += R.Fx.Num();
}

int32 FTally::TotalPieces() const
{
	int32 N = 0;
	for (const int32 P : Pieces)
	{
		N += P;
	}
	return N;
}

namespace
{
	TSharedPtr<FJsonObject> LoadKitJson(FString& OutWhy)
	{
		const FString Path = FPaths::Combine(FPaths::ProjectDir(), TEXT("data/ship/board_kit.json"));
		FString Text;
		if (!FFileHelper::LoadFileToString(Text, *Path))
		{
			OutWhy = FString::Printf(TEXT("%s is missing (blender -b -P art/blender/board_kit.py makes it)"), *Path);
			return nullptr;
		}
		TSharedPtr<FJsonObject> Root;
		if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Root) || !Root.IsValid())
		{
			OutWhy = FString::Printf(TEXT("%s does not parse"), *Path);
			return nullptr;
		}
		return Root;
	}
}

bool AstraBoardDress::LoadKitTris(TArray<int32>& OutTrisOf, FString& OutWhy)
{
	OutTrisOf.Init(0, (int32)EPiece::Count);
	const TSharedPtr<FJsonObject> Root = LoadKitJson(OutWhy);
	const TSharedPtr<FJsonObject>* Pieces = nullptr;
	if (!Root.IsValid() || !Root->TryGetObjectField(TEXT("pieces"), Pieces))
	{
		if (Root.IsValid())
		{
			OutWhy = TEXT("board_kit.json lists no pieces");
		}
		return false;
	}
	for (const TPair<FString, TSharedPtr<FJsonValue>>& KV : (*Pieces)->Values)
	{
		EPiece P;
		const TSharedPtr<FJsonObject> O = KV.Value.IsValid() ? KV.Value->AsObject() : nullptr;
		if (O.IsValid() && FindPiece(KV.Key, P))
		{
			OutTrisOf[(int32)P] = (int32)O->GetNumberField(TEXT("tris"));
		}
	}
	return true;
}

FString AstraBoardDress::CheckKit()
{
	FString Why;
	const TSharedPtr<FJsonObject> Root = LoadKitJson(Why);
	const TSharedPtr<FJsonObject>* Pieces = nullptr;
	if (!Root.IsValid() || !Root->TryGetObjectField(TEXT("pieces"), Pieces))
	{
		return Root.IsValid() ? FString(TEXT("board_kit.json lists no pieces")) : Why;
	}
	TArray<FString> Problems;
	TSet<int32> Seen;
	for (const TPair<FString, TSharedPtr<FJsonValue>>& KV : (*Pieces)->Values)
	{
		EPiece P;
		const TSharedPtr<FJsonObject> O = KV.Value.IsValid() ? KV.Value->AsObject() : nullptr;
		if (!O.IsValid() || !FindPiece(KV.Key, P))
		{
			Problems.Add(FString::Printf(TEXT("the kit has a piece the catalog does not know: %s"), *KV.Key));
			continue;
		}
		Seen.Add((int32)P);
		const FPieceDef& D = Def(P);
		if (O->GetStringField(TEXT("mesh")) != D.Mesh)
		{
			Problems.Add(FString::Printf(TEXT("%s: the kit's mesh is %s, the catalog's %s"), *KV.Key, *O->GetStringField(TEXT("mesh")), D.Mesh));
		}
		if (D.Frame == EFrame::Prop || D.Frame == EFrame::Body)
		{
			const TArray<TSharedPtr<FJsonValue>>* Lo = nullptr;
			const TArray<TSharedPtr<FJsonValue>>* Hi = nullptr;
			if (O->TryGetArrayField(TEXT("min_cm"), Lo) && O->TryGetArrayField(TEXT("max_cm"), Hi) && Lo->Num() >= 3 && Hi->Num() >= 3)
			{
				const double Got[4] = {(*Lo)[0]->AsNumber(), (*Lo)[1]->AsNumber(), (*Hi)[0]->AsNumber(), (*Hi)[1]->AsNumber()};
				const double Want[4] = {D.MinX, D.MinY, D.MaxX, D.MaxY};
				for (int32 i = 0; i < 4; ++i)
				{
					if (FMath::Abs(Got[i] - Want[i]) > 3.0)
					{
						Problems.Add(FString::Printf(TEXT("%s: the footprint in the kit is (%.0f, %.0f)-(%.0f, %.0f), the catalog's (%.0f, %.0f)-(%.0f, %.0f)"), *KV.Key, Got[0], Got[1], Got[2], Got[3], Want[0], Want[1], Want[2], Want[3]));
						break;
					}
				}
				if (D.bSolid && FMath::Abs((*Hi)[2]->AsNumber() - D.Height) > 6.0)
				{
					Problems.Add(FString::Printf(TEXT("%s: %.0f cm tall in the kit, %.0f in the catalog"), *KV.Key, (*Hi)[2]->AsNumber(), D.Height));
				}
			}
		}
	}
	for (int32 i = 0; i < (int32)EPiece::Count; ++i)
	{
		if (!Seen.Contains(i))
		{
			Problems.Add(FString::Printf(TEXT("the catalog has a piece the kit does not: %s"), GDefs[i].Key));
		}
	}
	return FString::Join(Problems, TEXT("; "));
}
