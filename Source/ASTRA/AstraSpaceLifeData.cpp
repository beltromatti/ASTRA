// ASTRA — the living space of a system: the static data (hulls, places, lanes, tours) and the layout of one system. See AstraSpaceLifeData.h and docs/SPAZIO.md.

#include "AstraSpaceLifeData.h"
#include "ASTRA.h"
#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "Math/RandomStream.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

namespace AstraSpace
{
	// ------------------------------------------------------------------------------------------------------------------ names
	ERole RoleFromName(const FString& N)
	{
		if (N.Equals(TEXT("fuel"), ESearchCase::IgnoreCase) || N.Equals(TEXT("tanker"), ESearchCase::IgnoreCase)) { return ERole::Fuel; }
		if (N.Equals(TEXT("passenger"), ESearchCase::IgnoreCase) || N.Equals(TEXT("liner"), ESearchCase::IgnoreCase)) { return ERole::Passenger; }
		if (N.Equals(TEXT("tug"), ESearchCase::IgnoreCase)) { return ERole::Tug; }
		if (N.Equals(TEXT("ore"), ESearchCase::IgnoreCase)) { return ERole::Ore; }
		if (N.Equals(TEXT("patrol"), ESearchCase::IgnoreCase)) { return ERole::Patrol; }
		return ERole::Freight;
	}

	const TCHAR* RoleName(ERole R)
	{
		static const TCHAR* const Names[(int32)ERole::Num] = {TEXT("freight"), TEXT("fuel"), TEXT("passenger"), TEXT("tug"), TEXT("ore"), TEXT("patrol")};
		return Names[FMath::Clamp((int32)R, 0, (int32)ERole::Num - 1)];
	}

	EPlaceKind PlaceKindFromName(const FString& N)
	{
		if (N.Equals(TEXT("gate"), ESearchCase::IgnoreCase)) { return EPlaceKind::Gate; }
		if (N.Equals(TEXT("keeper"), ESearchCase::IgnoreCase)) { return EPlaceKind::Keeper; }
		if (N.Equals(TEXT("arsenal"), ESearchCase::IgnoreCase)) { return EPlaceKind::Arsenal; }
		if (N.Equals(TEXT("refinery"), ESearchCase::IgnoreCase)) { return EPlaceKind::Refinery; }
		if (N.Equals(TEXT("orbit"), ESearchCase::IgnoreCase)) { return EPlaceKind::Orbit; }
		if (N.Equals(TEXT("belt"), ESearchCase::IgnoreCase)) { return EPlaceKind::Belt; }
		return EPlaceKind::Station;
	}

	const TCHAR* PlaceKindName(EPlaceKind K)
	{
		static const TCHAR* const Names[(int32)EPlaceKind::Num] = {TEXT("gate"), TEXT("keeper"), TEXT("arsenal"), TEXT("refinery"), TEXT("orbit"), TEXT("belt"), TEXT("station")};
		return Names[FMath::Clamp((int32)K, 0, (int32)EPlaceKind::Num - 1)];
	}

	float PatternOn(uint8 Pattern, float T, float Phase)
	{
		const float X = T + Phase;
		switch (Pattern)
		{
		case 0:
			return 1.f;
		case 1:                                                              // the ships' white strobe: two quick flashes every second and a half
		{
			const float Tt = FMath::Fmod(X, 1.5f);
			return (Tt < 0.07f || (Tt > 0.2f && Tt < 0.27f)) ? 1.f : 0.f;
		}
		case 2:                                                              // the red pulse: a soft beat every two seconds and a bit
		{
			const float Tt = FMath::Fmod(X, 2.2f);
			return Tt < 0.5f ? FMath::Sin(Tt / 0.5f * PI) : 0.f;
		}
		case 3:                                                              // an amber blink: a flash of a fifth of a second every 1.4 s
			return FMath::Fmod(X, 1.4f) < 0.2f ? 1.f : 0.f;
		case 4:                                                              // a quick triple strobe every two seconds (obstruction lights)
		{
			const float Tt = FMath::Fmod(X, 2.0f);
			return (Tt < 0.06f || (Tt > 0.16f && Tt < 0.22f) || (Tt > 0.32f && Tt < 0.38f)) ? 1.f : 0.f;
		}
		case 5:                                                              // a slow beacon: a swell of half a second every 3.5 s
		{
			const float Tt = FMath::Fmod(X, 3.5f);
			return Tt < 0.5f ? FMath::Sin(Tt / 0.5f * PI) : 0.f;
		}
		case 6:                                                              // a chaser: a short flash every 2.4 s, the phase running down the row
			return FMath::Fmod(X, 2.4f) < 0.14f ? 1.f : 0.f;
		default:                                                             // a flame's flicker
			return FMath::Clamp(0.62f + 0.38f * FMath::Sin(T * 13.1f + Phase * 7.f) * FMath::Sin(T * 7.3f + Phase), 0.15f, 1.f);
		}
	}

	// ------------------------------------------------------------------------------------------------------------------ JSON helpers (file-local names: the module builds in unity blocks)
	namespace
	{
		using FObj = TSharedPtr<FJsonObject>;

		double SpNum(const FObj& O, const TCHAR* K, double Def)
		{
			double V = Def;
			if (O.IsValid())
			{
				O->TryGetNumberField(K, V);
			}
			return V;
		}

		FString SpStr(const FObj& O, const TCHAR* K, const FString& Def = FString())
		{
			FString V = Def;
			if (O.IsValid())
			{
				O->TryGetStringField(K, V);
			}
			return V;
		}

		bool SpBool(const FObj& O, const TCHAR* K, bool Def)
		{
			bool V = Def;
			if (O.IsValid())
			{
				O->TryGetBoolField(K, V);
			}
			return V;
		}

		const TArray<TSharedPtr<FJsonValue>>* SpArr(const FObj& O, const TCHAR* K)
		{
			const TArray<TSharedPtr<FJsonValue>>* A = nullptr;
			return O.IsValid() && O->TryGetArrayField(K, A) ? A : nullptr;
		}

		bool SpVec(const FObj& O, const TCHAR* K, FVector& Out)
		{
			if (const TArray<TSharedPtr<FJsonValue>>* A = SpArr(O, K); A && A->Num() >= 3)
			{
				Out = FVector((*A)[0]->AsNumber(), (*A)[1]->AsNumber(), (*A)[2]->AsNumber());
				return true;
			}
			return false;
		}

		FVector SpVecOr(const FObj& O, const TCHAR* K, const FVector& Def)
		{
			FVector V = Def;
			SpVec(O, K, V);
			return V;
		}

		FLinearColor SpColor(const FObj& O, const TCHAR* K, const FLinearColor& Def)
		{
			FVector V;
			return SpVec(O, K, V) ? FLinearColor((float)V.X, (float)V.Y, (float)V.Z) : Def;
		}

		TArray<FString> SpStrings(const FObj& O, const TCHAR* K)
		{
			TArray<FString> Out;
			if (const TArray<TSharedPtr<FJsonValue>>* A = SpArr(O, K))
			{
				for (const TSharedPtr<FJsonValue>& V : *A)
				{
					Out.Add(V->AsString());
				}
			}
			return Out;
		}

		TArray<FName> SpNames(const FObj& O, const TCHAR* K)
		{
			TArray<FName> Out;
			for (const FString& S : SpStrings(O, K))
			{
				Out.Add(FName(*S));
			}
			return Out;
		}

		uint32 SpRoles(const FObj& O, const TCHAR* K)
		{
			uint32 Bits = 0;
			for (const FString& S : SpStrings(O, K))
			{
				Bits |= RoleBit(RoleFromName(S));
			}
			return Bits;
		}

		void ParseLamp(const FObj& J, FLamp& L)
		{
			SpVec(J, TEXT("p"), L.P);
			L.C = SpColor(J, TEXT("c"), FLinearColor::White);
			L.SizeM = (float)SpNum(J, TEXT("s"), 1.0);
			L.Glow = (float)SpNum(J, TEXT("i"), 160.0);
			L.Pattern = (uint8)FMath::Clamp((int32)SpNum(J, TEXT("pat"), 0.0), 0, 255);
			L.Phase = (float)SpNum(J, TEXT("ph"), 0.0);
		}

		void ParseMesh(const FString& Name, const FObj& J, FMeshData& M)
		{
			M.Mesh = Name;
			SpVec(J, TEXT("min"), M.Min);
			SpVec(J, TEXT("max"), M.Max);
			M.Length = (float)SpNum(J, TEXT("length"), (M.Max.X - M.Min.X));
			if (const TArray<TSharedPtr<FJsonValue>>* A = SpArr(J, TEXT("lamps")))
			{
				M.Lamps.Reserve(A->Num());
				for (const TSharedPtr<FJsonValue>& V : *A)
				{
					FLamp L;
					ParseLamp(V->AsObject(), L);
					M.Lamps.Add(L);
				}
			}
			if (const TArray<TSharedPtr<FJsonValue>>* A = SpArr(J, TEXT("bells")))
			{
				for (const TSharedPtr<FJsonValue>& V : *A)
				{
					FBell B;
					SpVec(V->AsObject(), TEXT("p"), B.P);
					B.R = (float)SpNum(V->AsObject(), TEXT("r"), 3.0);
					M.Bells.Add(B);
				}
			}
			if (const TArray<TSharedPtr<FJsonValue>>* A = SpArr(J, TEXT("docks")))
			{
				for (const TSharedPtr<FJsonValue>& V : *A)
				{
					const FObj D = V->AsObject();
					FDock K;
					SpVec(D, TEXT("p"), K.P);
					K.Dir = SpVecOr(D, TEXT("dir"), FVector::ForwardVector).GetSafeNormal();
					K.Approach = SpVecOr(D, TEXT("approach"), K.P - K.Dir * 300.0);
					K.MaxLen = (float)SpNum(D, TEXT("max_len"), 400.0);
					K.Roles = SpRoles(D, TEXT("roles"));
					M.Docks.Add(K);
				}
			}
			if (const TArray<TSharedPtr<FJsonValue>>* A = SpArr(J, TEXT("holds")))
			{
				for (const TSharedPtr<FJsonValue>& V : *A)
				{
					const TArray<TSharedPtr<FJsonValue>>& P = V->AsArray();
					if (P.Num() >= 3)
					{
						M.Holds.Add(FVector(P[0]->AsNumber(), P[1]->AsNumber(), P[2]->AsNumber()));
					}
				}
			}
			if (const TArray<TSharedPtr<FJsonValue>>* A = SpArr(J, TEXT("parts")))
			{
				for (const TSharedPtr<FJsonValue>& V : *A)
				{
					const FObj P = V->AsObject();
					FPart Part;
					Part.Mesh = SpStr(P, TEXT("mesh"));
					SpVec(P, TEXT("pivot"), Part.Pivot);
					Part.Axis = SpVecOr(P, TEXT("axis"), FVector::ForwardVector).GetSafeNormal();
					Part.PeriodS = (float)SpNum(P, TEXT("period_s"), 600.0);
					Part.Phase = (float)SpNum(P, TEXT("phase"), 0.0);
					Part.SwingDeg = (float)SpNum(P, TEXT("swing_deg"), 0.0);
					M.Parts.Add(Part);
				}
			}
			SpVec(J, TEXT("flare"), M.Flare);
			M.FlareLenM = (float)SpNum(J, TEXT("flare_len"), 0.0);
		}

		void ParseVia(const FObj& J, FViaSpec& V)
		{
			V.Anchor = SpStr(J, TEXT("anchor"), TEXT("origin"));
			V.BearingDeg = SpNum(J, TEXT("bearing_deg"), 0.0);
			V.MarkDeg = SpNum(J, TEXT("mark_deg"), 0.0);
			V.RangeKm = SpNum(J, TEXT("range_km"), 30.0);
			V.Dir = SpStr(J, TEXT("dir"), TEXT("planet"));
			V.YawDeg = SpNum(J, TEXT("yaw_deg"), 0.0);
			V.PitchDeg = SpNum(J, TEXT("pitch_deg"), 0.0);
			V.Fraction = SpNum(J, TEXT("fraction"), 0.5);
			V.AsideKm = SpNum(J, TEXT("aside_km"), 0.0);
			V.UpKm = SpNum(J, TEXT("up_km"), 0.0);
		}

		void ParseSystem(const FObj& J, FSystemSpec& S)
		{
			S.Name = SpStr(J, TEXT("name"));
			S.Density = (float)SpNum(J, TEXT("density"), 1.0);
			if (const TArray<TSharedPtr<FJsonValue>>* A = SpArr(J, TEXT("places")))
			{
				for (const TSharedPtr<FJsonValue>& V : *A)
				{
					const FObj P = V->AsObject();
					FPlaceSpec Pl;
					Pl.Id = FName(*SpStr(P, TEXT("id")));
					Pl.Name = SpStr(P, TEXT("name"), Pl.Id.ToString());
					Pl.Kind = PlaceKindFromName(SpStr(P, TEXT("kind")));
					Pl.Mesh = SpStr(P, TEXT("mesh"));
					Pl.Contact = SpStr(P, TEXT("contact"));
					Pl.Class = SpStr(P, TEXT("class"));
					Pl.RadiusM = (float)SpNum(P, TEXT("radius_m"), 500.0);
					Pl.Anchor = SpStr(P, TEXT("anchor"), TEXT("origin"));
					Pl.BearingDeg = SpNum(P, TEXT("bearing_deg"), 0.0);
					Pl.MarkDeg = SpNum(P, TEXT("mark_deg"), 0.0);
					Pl.RangeKm = SpNum(P, TEXT("range_km"), 50.0);
					Pl.Dir = SpStr(P, TEXT("dir"), TEXT("planet"));
					Pl.YawDeg = SpNum(P, TEXT("yaw_deg"), 0.0);
					Pl.PitchDeg = SpNum(P, TEXT("pitch_deg"), 0.0);
					Pl.GatePosKm = SpVecOr(P, TEXT("gate_pos_km"), FVector::ZeroVector);
					Pl.Face = SpStr(P, TEXT("face"), TEXT("broadside"));
					Pl.FaceYawDeg = SpNum(P, TEXT("face_yaw_deg"), 0.0);
					Pl.FacePitchDeg = SpNum(P, TEXT("face_pitch_deg"), 0.0);
					Pl.FaceRollDeg = SpNum(P, TEXT("face_roll_deg"), 0.0);
					Pl.Comms = SpStr(P, TEXT("comms"));
					Pl.Services = SpStrings(P, TEXT("services"));
					S.Places.Add(MoveTemp(Pl));
				}
			}
			if (const TArray<TSharedPtr<FJsonValue>>* A = SpArr(J, TEXT("lanes")))
			{
				for (const TSharedPtr<FJsonValue>& V : *A)
				{
					const FObj L = V->AsObject();
					FLaneSpec Ln;
					Ln.Id = FName(*SpStr(L, TEXT("id")));
					Ln.From = FName(*SpStr(L, TEXT("from")));
					Ln.To = FName(*SpStr(L, TEXT("to")));
					Ln.BuoyEveryKm = (float)SpNum(L, TEXT("buoy_every_km"), 20.0);
					Ln.BuoyColor = SpColor(L, TEXT("buoy_color"), Ln.BuoyColor);
					Ln.LateralM = (float)SpNum(L, TEXT("lateral_m"), 450.0);
					if (const TArray<TSharedPtr<FJsonValue>>* Vs = SpArr(L, TEXT("via")))
					{
						for (const TSharedPtr<FJsonValue>& VV : *Vs)
						{
							FViaSpec Via;
							ParseVia(VV->AsObject(), Via);
							Ln.Via.Add(Via);
						}
					}
					S.Lanes.Add(MoveTemp(Ln));
				}
			}
			if (const TArray<TSharedPtr<FJsonValue>>* A = SpArr(J, TEXT("tours")))
			{
				for (const TSharedPtr<FJsonValue>& V : *A)
				{
					const FObj T = V->AsObject();
					FTourSpec Tr;
					Tr.Hull = FName(*SpStr(T, TEXT("hull")));
					Tr.Count = (int32)SpNum(T, TEXT("count"), 1.0);
					Tr.Nodes = SpNames(T, TEXT("nodes"));
					if (const TArray<TSharedPtr<FJsonValue>>* D = SpArr(T, TEXT("dwell_s")); D && D->Num() >= 2)
					{
						Tr.DwellMin = FVector2D((*D)[0]->AsNumber(), (*D)[1]->AsNumber());
					}
					S.Tours.Add(MoveTemp(Tr));
				}
			}
			if (const TArray<TSharedPtr<FJsonValue>>* A = SpArr(J, TEXT("patrols")))
			{
				for (const TSharedPtr<FJsonValue>& V : *A)
				{
					const FObj P = V->AsObject();
					FPatrolSpec Pt;
					Pt.Node = FName(*SpStr(P, TEXT("node")));
					Pt.Craft = (int32)SpNum(P, TEXT("craft"), 4.0);
					Pt.RadiusKm = (float)SpNum(P, TEXT("radius_km"), 6.0);
					Pt.SpeedMps = (float)SpNum(P, TEXT("speed"), 160.0);
					Pt.Mesh = SpStr(P, TEXT("mesh"), Pt.Mesh);
					Pt.Formation = SpStr(P, TEXT("formation"), Pt.Formation);
					S.Patrols.Add(MoveTemp(Pt));
				}
			}
			const TSharedPtr<FJsonObject>* RocksP = nullptr;
			if (J.IsValid() && J->TryGetObjectField(TEXT("rocks"), RocksP) && RocksP)
			{
				const FObj R = *RocksP;
				FRockSpec& K = S.Rocks;
				K.bOn = SpBool(R, TEXT("on"), true);
				K.BearingMinDeg = SpNum(R, TEXT("bearing_min_deg"), K.BearingMinDeg);
				K.BearingMaxDeg = SpNum(R, TEXT("bearing_max_deg"), K.BearingMaxDeg);
				K.RangeMinKm = SpNum(R, TEXT("range_min_km"), K.RangeMinKm);
				K.RangeMaxKm = SpNum(R, TEXT("range_max_km"), K.RangeMaxKm);
				K.MarkSpreadDeg = SpNum(R, TEXT("mark_spread_deg"), K.MarkSpreadDeg);
				K.Count = (int32)SpNum(R, TEXT("count"), K.Count);
				K.Meshes = SpStrings(R, TEXT("meshes"));
				if (const TArray<TSharedPtr<FJsonValue>>* D = SpArr(R, TEXT("size_m")); D && D->Num() >= 2)
				{
					K.SizeM = FVector2D((*D)[0]->AsNumber(), (*D)[1]->AsNumber());
				}
			}
		}
	}

	// ------------------------------------------------------------------------------------------------------------------ the data set
	const FSystemSpec* FDataSet::System(const FString& Name) const
	{
		if (const FSystemSpec* S = Systems.Find(Name.ToLower()))
		{
			return S;
		}
		return Systems.Find(TEXT("_generic"));
	}

	bool FDataSet::Parse(const FString& SpaceJson, const FString& MeshesJson, FString& OutError)
	{
		Hulls.Reset();
		Meshes.Reset();
		Systems.Reset();
		TSharedPtr<FJsonObject> Root;
		if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(SpaceJson), Root) || !Root.IsValid())
		{
			OutError = TEXT("space.json does not parse");
			return false;
		}
		if (const TArray<TSharedPtr<FJsonValue>>* A = SpArr(Root, TEXT("hulls")))
		{
			for (const TSharedPtr<FJsonValue>& V : *A)
			{
				const FObj H = V->AsObject();
				FHullDef D;
				D.Key = FName(*SpStr(H, TEXT("key")));
				if (D.Key.IsNone())
				{
					continue;
				}
				D.Class = SpStr(H, TEXT("class"), D.Key.ToString());
				D.Role = RoleFromName(SpStr(H, TEXT("role"), D.Key.ToString()));
				D.Meshes = SpStrings(H, TEXT("meshes"));
				D.Length = (float)SpNum(H, TEXT("length"), 300.0);
				D.Radius = (float)SpNum(H, TEXT("radius"), D.Length * 0.5);
				D.Cruise = (float)SpNum(H, TEXT("cruise"), 140.0);
				D.Accel = (float)SpNum(H, TEXT("accel"), 3.0);
				D.TurnDeg = (float)SpNum(H, TEXT("turn_deg"), 2.0);
				D.Weight = (float)SpNum(H, TEXT("weight"), 1.0);
				D.bAmber = SpStr(H, TEXT("plume"), TEXT("blue")) == TEXT("amber");
				D.Names = SpStrings(H, TEXT("names"));
				D.Companies = SpStrings(H, TEXT("companies"));
				D.HullKm = (float)SpNum(H, TEXT("hull_km"), 0.0);
				Hulls.Add(D.Key, MoveTemp(D));
			}
		}
		if (const TArray<TSharedPtr<FJsonValue>>* A = SpArr(Root, TEXT("systems")))
		{
			for (const TSharedPtr<FJsonValue>& V : *A)
			{
				FSystemSpec S;
				ParseSystem(V->AsObject(), S);
				if (!S.Name.IsEmpty())
				{
					Systems.Add(S.Name.ToLower(), MoveTemp(S));
				}
			}
		}
		TSharedPtr<FJsonObject> MRoot;
		if (!MeshesJson.IsEmpty() && FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(MeshesJson), MRoot) && MRoot.IsValid())
		{
			if (const TSharedPtr<FJsonObject>* Ms = nullptr; MRoot->TryGetObjectField(TEXT("meshes"), Ms))
			{
				for (const TPair<FString, TSharedPtr<FJsonValue>>& KV : (*Ms)->Values)
				{
					FMeshData M;
					ParseMesh(KV.Key, KV.Value->AsObject(), M);
					Meshes.Add(KV.Key, MoveTemp(M));
				}
			}
		}
		return true;
	}

	namespace
	{
		FDataSet GSpaceData;

		void SpLoad()
		{
			GSpaceData = FDataSet();
			FString Space, Meshes;
			// staged with the game (Content/ASTRA/Data, always packaged as loose files: DefaultGame.ini); the repo's data/space copy is the source
			const FString A = FPaths::Combine(FPaths::ProjectContentDir(), TEXT("ASTRA/Data/space"));
			const FString B = FPaths::Combine(FPaths::ProjectDir(), TEXT("data/space"));
			const FString* Dir = FPaths::FileExists(A / TEXT("space.json")) ? &A : (FPaths::FileExists(B / TEXT("space.json")) ? &B : nullptr);
			if (!Dir)
			{
				UE_LOG(LogASTRA, Warning, TEXT("[Space] data/space/space.json is missing: no living space"));
				return;
			}
			FFileHelper::LoadFileToString(Space, *(*Dir / TEXT("space.json")));
			FFileHelper::LoadFileToString(Meshes, *(*Dir / TEXT("meshes.json")));
			FString Error;
			if (!GSpaceData.Parse(Space, Meshes, Error))
			{
				UE_LOG(LogASTRA, Warning, TEXT("[Space] %s (%s)"), *Error, **Dir);
				return;
			}
			GSpaceData.bLoaded = true;
			GSpaceData.Source = *Dir;
			UE_LOG(LogASTRA, Log, TEXT("[Space] data from %s: %d hulls, %d systems, %d meshes described"), **Dir, GSpaceData.Hulls.Num(), GSpaceData.Systems.Num(), GSpaceData.Meshes.Num());
		}
	}

	const FDataSet& Data()
	{
		static bool bDone = false;
		if (!bDone)
		{
			bDone = true;
			SpLoad();
		}
		return GSpaceData;
	}

	void ReloadData()
	{
		SpLoad();
	}

	// ------------------------------------------------------------------------------------------------------------------ the layout
	int32 FLayout::FindNode(FName Id) const
	{
		for (int32 i = 0; i < Nodes.Num(); ++i)
		{
			if (Nodes[i].Id == Id)
			{
				return i;
			}
		}
		return INDEX_NONE;
	}

	int32 FLayout::FindLane(int32 From, int32 To, bool& bForward) const
	{
		for (int32 i = 0; i < Lanes.Num(); ++i)
		{
			if (Lanes[i].A == From && Lanes[i].B == To) { bForward = true; return i; }
			if (Lanes[i].A == To && Lanes[i].B == From) { bForward = false; return i; }
		}
		return INDEX_NONE;
	}

	FVector FLayout::Polar(double RangeM, double BearingDeg, double MarkDeg)
	{
		const double B = FMath::DegreesToRadians(BearingDeg), M = FMath::DegreesToRadians(MarkDeg);
		return FVector(RangeM * FMath::Cos(M) * FMath::Cos(B), RangeM * FMath::Cos(M) * FMath::Sin(B), RangeM * FMath::Sin(M));
	}

	namespace
	{
		/** A direction in the sky ("planet" or "star") turned a little: yaw about the vertical, then pitch up from the horizontal. */
		FVector SpSkyDir(const FAnchors& A, const FString& Which, double YawDeg, double PitchDeg)
		{
			const FVector D = (Which.Equals(TEXT("star"), ESearchCase::IgnoreCase) ? A.StarDir : A.PlanetDir).GetSafeNormal();
			const double Bearing = FMath::RadiansToDegrees(FMath::Atan2(D.Y, D.X)) + YawDeg;
			const double Mark = FMath::RadiansToDegrees(FMath::Asin(FMath::Clamp(D.Z, -1.0, 1.0))) + PitchDeg;
			return FLayout::Polar(1.0, Bearing, Mark);
		}

		FQuat SpFace(const FPlaceSpec& P, const FVector& Pos, const FAnchors& A)
		{
			const FVector ToOrigin = (A.Origin - Pos).GetSafeNormal();
			FQuat Q = FQuat::Identity;
			if (P.Face.Equals(TEXT("gate_axis"), ESearchCase::IgnoreCase) && A.bGate)
			{
				Q = A.GateAtt;
			}
			else if (P.Face.Equals(TEXT("toward_origin"), ESearchCase::IgnoreCase))
			{
				Q = FRotationMatrix::MakeFromXZ(ToOrigin, FVector::UpVector).ToQuat();
			}
			else if (P.Face.Equals(TEXT("explicit"), ESearchCase::IgnoreCase))
			{
				Q = FQuat::Identity;
			}
			else
			{
				// broadside to where the Aquila comes in: the long axis across the line of sight, level
				FVector X = FVector::CrossProduct(FVector::UpVector, ToOrigin);
				if (X.SizeSquared() < 1e-6)
				{
					X = FVector::ForwardVector;
				}
				Q = FRotationMatrix::MakeFromXZ(X.GetSafeNormal(), FVector::UpVector).ToQuat();
			}
			return Q * FRotator(P.FacePitchDeg, P.FaceYawDeg, P.FaceRollDeg).Quaternion();
		}

		/** Where a lane meets a node, coming from `Toward`: clear of the structure (the Gate: out along its axis, where the battle's lane begins). */
		FVector SpLaneEnd(const FNode& N, const FVector& Toward, const FAnchors& A)
		{
			if (N.Kind == EPlaceKind::Gate)
			{
				return N.Pos + N.Att.GetForwardVector() * (A.LaneEntryKm * OneKm);
			}
			const FVector D = (Toward - N.Pos).GetSafeNormal();
			return N.Pos + D * (N.RadiusM * 1.7 + 600.0);
		}

		double SpPolylineDistance(const TArray<FVector>& Pts, const FVector& P)
		{
			double Best = 1e18;
			for (int32 i = 0; i + 1 < Pts.Num(); ++i)
			{
				Best = FMath::Min(Best, FMath::PointDistToSegment(P, Pts[i], Pts[i + 1]));
			}
			return Best;
		}
	}

	void BuildLayout(const FSystemSpec& Spec, const FDataSet& Set, const FAnchors& A, uint32 Seed, FLayout& Out)
	{
		Out = FLayout();
		Out.System = Spec.Name;
		Out.Anchors = A;
		Out.Spec = &Spec;
		FRandomStream Rng((int32)(Seed ^ GetTypeHash(Spec.Name.ToLower())));
		// ---- the places
		for (const FPlaceSpec& P : Spec.Places)
		{
			if (P.Anchor.Equals(TEXT("gate"), ESearchCase::IgnoreCase) && !A.bGate)
			{
				continue;                                   // a place that hangs on the Gate, and no Gate here
			}
			FNode N;
			N.Id = P.Id;
			N.Name = P.Name;
			N.Kind = P.Kind;
			N.RadiusM = P.RadiusM;
			N.Spec = &P;
			N.Mesh = P.Mesh.IsEmpty() ? nullptr : Set.Mesh(P.Mesh);
			if (P.Kind == EPlaceKind::Gate)
			{
				N.Pos = A.GatePos;
				N.Att = A.GateAtt;
				N.RadiusM = A.GateRadiusM;
			}
			else if (P.Anchor.Equals(TEXT("gate"), ESearchCase::IgnoreCase))
			{
				N.Pos = A.GatePos + A.GateAtt.RotateVector(P.GatePosKm * OneKm);
				N.Att = SpFace(P, N.Pos, A);
			}
			else if (P.Anchor.Equals(TEXT("sky"), ESearchCase::IgnoreCase))
			{
				N.Pos = A.Origin + SpSkyDir(A, P.Dir, P.YawDeg, P.PitchDeg) * (P.RangeKm * OneKm);
				N.Att = SpFace(P, N.Pos, A);
			}
			else
			{
				N.Pos = A.Origin + FLayout::Polar(P.RangeKm * OneKm, P.BearingDeg, P.MarkDeg);
				N.Att = SpFace(P, N.Pos, A);
			}
			N.Entry = N.Pos;
			if (N.Mesh)
			{
				for (const FDock& D : N.Mesh->Docks)
				{
					FSlot S;
					S.Pos = N.Pos + N.Att.RotateVector(D.P);
					const FVector DirW = N.Att.RotateVector(D.Dir);
					S.Att = FRotationMatrix::MakeFromXZ(DirW, N.Att.GetUpVector()).ToQuat();
					S.Approach = N.Pos + N.Att.RotateVector(D.Approach);
					S.MaxLen = D.MaxLen;
					S.Roles = D.Roles;
					N.Slots.Add(S);
				}
				for (const FVector& H : N.Mesh->Holds)
				{
					N.Holds.Add(N.Pos + N.Att.RotateVector(H));
				}
			}
			if (N.Kind == EPlaceKind::Gate)
			{
				// the queue for the lane: a column of waiting points back along the axis from where the Gate's field takes a ship, staggered a little so that two do not lie in line
				const FVector Axis = N.Att.GetForwardVector(), Right = N.Att.GetRightVector(), Up = N.Att.GetUpVector();
				for (int32 k = 0; k < 10; ++k)
				{
					N.Holds.Add(N.Pos + Axis * ((A.LaneEntryKm + 1.4 + 1.3 * k) * OneKm) + Right * (((k % 2) ? 1.0 : -1.0) * (250.0 + 60.0 * (k / 2))) + Up * (((k % 3) - 1) * 220.0));
				}
			}
			N.HoldTaken.Init(INDEX_NONE, N.Holds.Num());
			Out.Nodes.Add(MoveTemp(N));
		}
		for (int32 i = 0; i < Out.Nodes.Num(); ++i)
		{
			switch (Out.Nodes[i].Kind)
			{
			case EPlaceKind::Gate: Out.GateNode = i; break;
			case EPlaceKind::Keeper: Out.KeeperNode = i; break;
			case EPlaceKind::Orbit: Out.OrbitNode = i; break;
			default: break;
			}
		}
		// ---- the lanes
		for (const FLaneSpec& Ls : Spec.Lanes)
		{
			FLane L;
			L.Id = Ls.Id;
			L.A = Out.FindNode(Ls.From);
			L.B = Out.FindNode(Ls.To);
			if (L.A == INDEX_NONE || L.B == INDEX_NONE)
			{
				continue;
			}
			L.LateralM = Ls.LateralM;
			L.BuoyColor = Ls.BuoyColor;
			const FNode& Na = Out.Nodes[L.A];
			const FNode& Nb = Out.Nodes[L.B];
			TArray<FVector> Mid;
			for (const FViaSpec& V : Ls.Via)
			{
				if (V.Anchor.Equals(TEXT("between"), ESearchCase::IgnoreCase))
				{
					const FVector Ab = Nb.Pos - Na.Pos;
					const FVector Side = FVector::CrossProduct(FVector::UpVector, Ab).GetSafeNormal();
					Mid.Add(Na.Pos + Ab * V.Fraction + Side * (V.AsideKm * OneKm) + FVector::UpVector * (V.UpKm * OneKm));
				}
				else if (V.Anchor.Equals(TEXT("sky"), ESearchCase::IgnoreCase))
				{
					Mid.Add(A.Origin + SpSkyDir(A, V.Dir, V.YawDeg, V.PitchDeg) * (V.RangeKm * OneKm));
				}
				else
				{
					Mid.Add(A.Origin + FLayout::Polar(V.RangeKm * OneKm, V.BearingDeg, V.MarkDeg));
				}
			}
			L.Pts.Add(SpLaneEnd(Na, Mid.Num() ? Mid[0] : Nb.Pos, A));
			L.Pts.Append(Mid);
			L.Pts.Add(SpLaneEnd(Nb, Mid.Num() ? Mid.Last() : Na.Pos, A));
			for (int32 i = 0; i + 1 < L.Pts.Num(); ++i)
			{
				L.LengthM += FVector::Dist(L.Pts[i], L.Pts[i + 1]);
			}
			if (Ls.BuoyEveryKm > 1.f)
			{
				// a buoy every so many kilometres from the first point on, none in the first and last two (the structures' own lights are there)
				const double Step = Ls.BuoyEveryKm * OneKm;
				double Walk = Step, Run = 0.0;
				for (int32 i = 0; i + 1 < L.Pts.Num(); ++i)
				{
					const double Len = FVector::Dist(L.Pts[i], L.Pts[i + 1]);
					while (Walk <= Run + Len)
					{
						if (Walk > 2.0 * OneKm && Walk < L.LengthM - 2.0 * OneKm)
						{
							L.Buoys.Add(FMath::Lerp(L.Pts[i], L.Pts[i + 1], (Walk - Run) / FMath::Max(Len, 1.0)));
						}
						Walk += Step;
					}
					Run += Len;
				}
			}
			Out.Lanes.Add(MoveTemp(L));
		}
		// ---- the belt's rocks: a band of them at a distance, clear of the lanes and of the places
		if (Spec.Rocks.bOn && Spec.Rocks.Meshes.Num())
		{
			const FRockSpec& K = Spec.Rocks;
			Out.Rocks.Reserve(K.Count);
			for (int32 Try = 0; Try < K.Count * 4 && Out.Rocks.Num() < K.Count; ++Try)
			{
				// clumps: the belt is lumpy. A few centres along its arc pull the rocks together.
				const double U = Rng.FRand();
				const double Clump = FMath::Sin(U * 2.0 * PI * 3.0 + 1.3) * 0.5 + 0.5;
				if (Rng.FRand() > 0.25 + 0.75 * Clump)
				{
					continue;
				}
				const double Bearing = FMath::Lerp(K.BearingMinDeg, K.BearingMaxDeg, U);
				const double Range = FMath::Lerp(K.RangeMinKm, K.RangeMaxKm, FMath::Clamp(0.5 + 0.7 * (Rng.FRand() + Rng.FRand() - 1.0) * 0.5, 0.0, 1.0));   // (thickest in the middle of the band)
				const double Mark = K.MarkSpreadDeg * (Rng.FRand() + Rng.FRand() + Rng.FRand() - 1.5) * 0.9;
				FRock R;
				R.Pos = A.Origin + FLayout::Polar(Range * OneKm, Bearing, Mark);
				const double T = Rng.FRand();
				R.SizeM = (float)FMath::Lerp(K.SizeM.X, K.SizeM.Y, T * T * T * T);          // a long tail of small ones, a few giants
				R.Mesh = Rng.RandRange(0, K.Meshes.Num() - 1);
				R.Att = FQuat(Rng.VRand(), Rng.FRand() * 2.0 * PI);
				bool bClear = true;
				for (const FLane& L : Out.Lanes)
				{
					bClear &= SpPolylineDistance(L.Pts, R.Pos) > 6.0 * OneKm + R.SizeM;
				}
				for (const FNode& N : Out.Nodes)
				{
					bClear &= FVector::Dist(N.Pos, R.Pos) > 8.0 * OneKm + N.RadiusM + R.SizeM;
				}
				if (bClear)
				{
					Out.Rocks.Add(R);
				}
			}
		}
	}
}
