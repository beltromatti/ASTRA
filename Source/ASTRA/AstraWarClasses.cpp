#include "AstraWarClasses.h"
#include "ASTRA.h"
#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

namespace AstraWar
{
	namespace
	{
		// the built-in table: `tools/war.py embed` writes it from data/war/classes.json
		#include "AstraWarClassesData.inl"

		TMap<FName, FShipClass> GClasses;
		bool GClassesLoaded = false;
		FShipClass GGeneric;

		double NumField(const TSharedPtr<FJsonObject>& O, const TCHAR* Name, double Default)
		{
			double V = Default;
			if (O.IsValid())
			{
				O->TryGetNumberField(Name, V);
			}
			return V;
		}

		template <int32 N>
		void ArrayField(const TSharedPtr<FJsonObject>& O, const TCHAR* Name, float (&Out)[N], bool bNormalise)
		{
			const TArray<TSharedPtr<FJsonValue>>* A = nullptr;
			if (!O->TryGetArrayField(Name, A) || A->Num() != N)
			{
				return;
			}
			float Sum = 0.f;
			for (int32 i = 0; i < N; ++i)
			{
				Out[i] = (float)(*A)[i]->AsNumber();
				Sum += Out[i];
			}
			if (bNormalise && Sum > 1e-6f)
			{
				for (int32 i = 0; i < N; ++i)
				{
					Out[i] /= Sum;
				}
			}
		}

		bool ParseClasses(const FString& Json, const TCHAR* Source)
		{
			TSharedPtr<FJsonObject> Root;
			const TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(Json);
			const TArray<TSharedPtr<FJsonValue>>* List = nullptr;
			if (!FJsonSerializer::Deserialize(Reader, Root) || !Root.IsValid() || !Root->TryGetArrayField(TEXT("classes"), List))
			{
				UE_LOG(LogASTRA, Warning, TEXT("[War] ship classes: %s does not parse"), Source);
				return false;
			}
			for (const TSharedPtr<FJsonValue>& V : *List)
			{
				const TSharedPtr<FJsonObject> O = V->AsObject();
				FString Key;
				if (!O.IsValid() || !O->TryGetStringField(TEXT("key"), Key) || Key.IsEmpty())
				{
					continue;
				}
				FShipClass C = GClasses.Contains(FName(*Key)) ? GClasses[FName(*Key)] : FShipClass();
				C.Key = FName(*Key);
				O->TryGetStringField(TEXT("label"), C.Label);
				O->TryGetStringField(TEXT("mesh"), C.Mesh);
				C.Radius = (float)NumField(O, TEXT("radius"), C.Radius);
				C.Tier = (int32)NumField(O, TEXT("tier"), C.Tier);
				if (const TSharedPtr<FJsonObject>* HB = nullptr; O->TryGetObjectField(TEXT("hull_m"), HB))
				{
					float X[2] = {-C.Radius, C.Radius};
					ArrayField(*HB, TEXT("x"), X, false);
					C.Box.Mid = 0.5f * (X[0] + X[1]);
					C.Box.Hx = 0.5f * (X[1] - X[0]);
					C.Box.Hy = 0.5f * (float)NumField(*HB, TEXT("width"), 2.0 * C.Box.Hy);
					C.Box.Hz = 0.5f * (float)NumField(*HB, TEXT("height"), 2.0 * C.Box.Hz);
				}
				{
					float Cuts[2] = {C.Box.CutBow, C.Box.CutStern};
					ArrayField(O, TEXT("cuts_x_m"), Cuts, false);
					C.Box.CutBow = Cuts[0];
					C.Box.CutStern = Cuts[1];
				}
				C.Hull = (float)NumField(O, TEXT("hull"), C.Hull);
				C.Shield = (float)NumField(O, TEXT("shield"), C.Shield);
				C.ShieldRegen = (float)NumField(O, TEXT("shield_regen"), C.ShieldRegen);
				C.Accel = (float)NumField(O, TEXT("accel"), C.Accel);
				C.TurnDeg = (float)NumField(O, TEXT("turn_deg"), C.TurnDeg);
				C.Cruise = (float)NumField(O, TEXT("cruise"), C.Cruise);
				C.SensorKm = (float)NumField(O, TEXT("sensor_km"), C.SensorKm);
				C.ArmourFrac = (float)NumField(O, TEXT("armour"), C.ArmourFrac);
				C.ShieldScale = (float)NumField(O, TEXT("shield_scale"), C.ShieldScale);
				ArrayField(O, TEXT("sections"), C.SectionShare, true);
				ArrayField(O, TEXT("facing_armour"), C.FacingArmour, true);
				ArrayField(O, TEXT("shield_alloc"), C.ShieldAlloc, true);
				float Range[2] = {C.RangeMinKm, C.RangeMaxKm};
				ArrayField(O, TEXT("range_km"), Range, false);
				C.RangeMinKm = Range[0];
				C.RangeMaxKm = Range[1];
				if (const TSharedPtr<FJsonObject>* R = nullptr; O->TryGetObjectField(TEXT("rail"), R))
				{
					C.RailSlugs = (int32)NumField(*R, TEXT("slugs"), C.RailSlugs);
					C.RailDamage = (float)NumField(*R, TEXT("damage"), C.RailDamage);
					C.RailCd = (float)NumField(*R, TEXT("cd"), C.RailCd);
					C.RailRange = (float)NumField(*R, TEXT("range"), C.RailRange);
				}
				if (const TSharedPtr<FJsonObject>* M = nullptr; O->TryGetObjectField(TEXT("missiles"), M))
				{
					C.Missiles = (int32)NumField(*M, TEXT("count"), C.Missiles);
					C.MissileCd = (float)NumField(*M, TEXT("cd"), C.MissileCd);
					C.MissileRange = (float)NumField(*M, TEXT("range"), C.MissileRange);
				}
				if (const TSharedPtr<FJsonObject>* L = nullptr; O->TryGetObjectField(TEXT("laser"), L))
				{
					C.LaserDamage = (float)NumField(*L, TEXT("damage"), C.LaserDamage);
					C.LaserCd = (float)NumField(*L, TEXT("cd"), C.LaserCd);
					C.LaserRange = (float)NumField(*L, TEXT("range"), C.LaserRange);
					C.LaserFalloff = (float)NumField(*L, TEXT("falloff"), C.LaserFalloff);
				}
				if (const TSharedPtr<FJsonObject>* Gn = nullptr; O->TryGetObjectField(TEXT("gunnery"), Gn))
				{
					C.TrackMrad = (float)NumField(*Gn, TEXT("track_mrad"), C.TrackMrad);
					C.DispMrad = (float)NumField(*Gn, TEXT("disp_mrad"), C.DispMrad);
				}
				if (const TSharedPtr<FJsonObject>* P = nullptr; O->TryGetObjectField(TEXT("pd"), P))
				{
					C.PDChannels = (int32)NumField(*P, TEXT("channels"), C.PDChannels);
					C.PDRange = (float)NumField(*P, TEXT("range"), C.PDRange);
				}
				if (const TSharedPtr<FJsonObject>* S = nullptr; O->TryGetObjectField(TEXT("systems"), S))
				{
					static const TCHAR* const Names[] = {TEXT("engines"), TEXT("sensors"), TEXT("hangar"), TEXT("bridge"), TEXT("reactor")};
					for (int32 i = 0; i < 5; ++i)
					{
						C.SysSection[i] = (uint8)FMath::Clamp((int32)NumField(*S, Names[i], C.SysSection[i]), 0, NumSections - 1);
					}
				}
				const TArray<TSharedPtr<FJsonValue>>* Ms = nullptr;
				if (O->TryGetArrayField(TEXT("mounts"), Ms))
				{
					C.Mounts.Reset();
					int32 Barrels = 0;
					for (const TSharedPtr<FJsonValue>& MV : *Ms)
					{
						const TSharedPtr<FJsonObject> MO = MV->AsObject();
						if (!MO.IsValid())
						{
							continue;
						}
						FMountDef D;
						FString Kind;
						MO->TryGetStringField(TEXT("kind"), Kind);
						D.Kind = Kind.Equals(TEXT("laser"), ESearchCase::IgnoreCase) ? EAstraMountKind::Laser : EAstraMountKind::Rail;
						const TArray<TSharedPtr<FJsonValue>>* Dir = nullptr;
						if (MO->TryGetArrayField(TEXT("dir"), Dir) && Dir->Num() == 3)
						{
							D.Dir = FVector((*Dir)[0]->AsNumber(), (*Dir)[1]->AsNumber(), (*Dir)[2]->AsNumber()).GetSafeNormal();
						}
						D.ArcDeg = (float)NumField(MO, TEXT("arc"), D.ArcDeg);
						D.Barrels = (uint8)FMath::Clamp((int32)NumField(MO, TEXT("barrels"), 1), 1, 8);
						D.Section = (uint8)FMath::Clamp((int32)NumField(MO, TEXT("section"), SecMid), 0, NumSections - 1);
						Barrels += D.Kind == EAstraMountKind::Rail ? D.Barrels : 0;
						C.Mounts.Add(D);
					}
					if (Barrels != C.RailSlugs)
					{
						UE_LOG(LogASTRA, Warning, TEXT("[War] ship class %s: its rail mounts have %d barrels but the class says %d slugs a volley"), *Key, Barrels, C.RailSlugs);
					}
				}
				GClasses.Add(C.Key, C);
			}
			UE_LOG(LogASTRA, Log, TEXT("[War] ship classes from %s: %d in the table"), Source, GClasses.Num());
			return true;
		}
	}

	void EnsureClassesLoaded()
	{
		if (GClassesLoaded)
		{
			return;
		}
		GClassesLoaded = true;
		FString Builtin;
		for (const char* Chunk : GAstraWarClassesJson)
		{
			if (Chunk)
			{
				Builtin += UTF8_TO_TCHAR(Chunk);
			}
		}
		ParseClasses(Builtin, TEXT("the built-in table"));
		FString Text;
		const FString Path = FPaths::Combine(FPaths::ProjectDir(), TEXT("data/war/classes.json"));
		if (FFileHelper::LoadFileToString(Text, *Path))
		{
			ParseClasses(Text, *Path);
		}
		GGeneric.Key = FName(TEXT("generic"));
		GGeneric.Label = TEXT("warship");
	}

	const FShipClass* FindClass(FName Key)
	{
		EnsureClassesLoaded();
		return GClasses.Find(Key);
	}

	const FShipClass& GetClass(FName Key)
	{
		const FShipClass* C = FindClass(Key);
		return C ? *C : GGeneric;
	}

	void ClassKeys(TArray<FName>& Out)
	{
		EnsureClassesLoaded();
		GClasses.GetKeys(Out);
	}

	FName KeyFor(const FString& ClassText, const FString& Mesh)
	{
		auto Has = [](const FString& S, const TCHAR* Sub) { return S.Contains(Sub, ESearchCase::IgnoreCase); };
		if (Has(Mesh, TEXT("_Praetorian")) || Has(ClassText, TEXT("battleship"))) { return FName(TEXT("praetorian")); }
		if (Has(Mesh, TEXT("_Vigilant"))) { return FName(TEXT("vigilant")); }
		if (Has(Mesh, TEXT("_Acheron")) || Has(ClassText, TEXT("Acheron")) || Has(ClassText, TEXT("cruiser (flagship"))) { return FName(TEXT("acheron")); }
		if (Has(Mesh, TEXT("_Styx")) || Has(ClassText, TEXT("Styx"))) { return FName(TEXT("styx")); }
		if (Has(Mesh, TEXT("_Lethe")) || Has(ClassText, TEXT("Lethe"))) { return FName(TEXT("lethe")); }
		if (Has(Mesh, TEXT("Freighter")) || Has(ClassText, TEXT("freighter"))) { return FName(TEXT("freighter")); }
		if (Has(Mesh, TEXT("STATION")) || Has(ClassText, TEXT("listening post"))) { return FName(TEXT("station")); }
		if (Has(Mesh, TEXT("_Aquila")) || Has(ClassText, TEXT("Aquila"))) { return FName(TEXT("aquila")); }
		if (Has(ClassText, TEXT("destroyer"))) { return FName(TEXT("vigilant")); }
		return NAME_None;
	}
}
