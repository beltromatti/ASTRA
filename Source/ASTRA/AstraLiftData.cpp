// ASTRA — the lift network's data (see AstraLiftData.h).

#include "AstraLiftData.h"

#include "ASTRA.h"
#include "Algo/Count.h"
#include "Dom/JsonObject.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

namespace
{
	using FLiftObj = TSharedPtr<FJsonObject>;

	double LiftNumOf(const FLiftObj& O, const TCHAR* K, double Def = 0.0)
	{
		double V = Def;
		if (O.IsValid())
		{
			O->TryGetNumberField(K, V);
		}
		return V;
	}

	FString LiftStrOf(const FLiftObj& O, const TCHAR* K, const FString& Def = FString())
	{
		FString V = Def;
		if (O.IsValid())
		{
			O->TryGetStringField(K, V);
		}
		return V;
	}

	/** A point in the plan's metres as world cm; false when the field is not three numbers. */
	bool LiftVec3Of(const FLiftObj& O, const TCHAR* K, FVector& Out)
	{
		const TArray<TSharedPtr<FJsonValue>>* A = nullptr;
		if (!O.IsValid() || !O->TryGetArrayField(K, A) || A->Num() < 3)
		{
			return false;
		}
		Out = FVector((*A)[0]->AsNumber(), (*A)[1]->AsNumber(), (*A)[2]->AsNumber()) * 100.0;
		return true;
	}

	FLiftObj LiftObjOf(const FLiftObj& O, const TCHAR* K)
	{
		const FLiftObj* Sub = nullptr;
		return O.IsValid() && O->TryGetObjectField(K, Sub) ? *Sub : FLiftObj();
	}

	/** A room of the plan, as far as the car's screen cares: where it is and how notable. */
	struct FLiftRoom
	{
		int32 Plane = 0;
		FString Kind, Name, Id;
		FVector2D Mid = FVector2D::ZeroVector;
		float X0 = 0.f, X1 = 0.f;
		bool bExisting = false;
		int32 Weight = 0;
	};

	/** How notable a kind of room is (below 40: an anonymous room that is not worth a name on a screen). The rooms a Captain goes to first: the halls the
	 *  ship had before (the existing ones), the stations that run her, where people sleep, eat and heal. */
	int32 LiftNotableWeight(const FString& Kind)
	{
		static const TMap<FString, int32> W = {
			{TEXT("bridge"), 100}, {TEXT("medbay"), 95}, {TEXT("engineering"), 95}, {TEXT("hangar"), 95}, {TEXT("mess"), 90}, {TEXT("cic"), 90},
			{TEXT("transporter"), 90}, {TEXT("armory"), 85}, {TEXT("ready_room"), 80}, {TEXT("berthing"), 80}, {TEXT("quarters"), 75}, {TEXT("surgery"), 70},
			{TEXT("range"), 70}, {TEXT("flight_ops"), 70}, {TEXT("concourse"), 65}, {TEXT("galley"), 60}, {TEXT("wardroom"), 60}, {TEXT("comms"), 60},
			{TEXT("weapons_control"), 60}, {TEXT("briefing"), 55}, {TEXT("lounge"), 55}, {TEXT("gym"), 55}, {TEXT("pharmacy"), 55}, {TEXT("library"), 50},
			{TEXT("observation"), 50}, {TEXT("sensors"), 50}, {TEXT("quarantine"), 50}, {TEXT("power"), 50}, {TEXT("chapel"), 45}, {TEXT("weapons"), 45},
			{TEXT("lab"), 40}};
		const int32* V = W.Find(Kind);
		return V ? *V : 0;
	}

	EAstraLiftKind LiftKindOf(const FString& K)
	{
		if (K == TEXT("bridge")) { return EAstraLiftKind::Bridge; }
		if (K == TEXT("service")) { return EAstraLiftKind::Service; }
		if (K == TEXT("cargo")) { return EAstraLiftKind::Cargo; }
		if (K == TEXT("shuttle")) { return EAstraLiftKind::Shuttle; }
		return EAstraLiftKind::Turbolift;
	}

	struct FLiftSection { FString Id; float X0 = 0.f, X1 = 0.f; };

	struct FLiftContext
	{
		TMap<int32, FString> DeckName;
		TMap<int32, TArray<FLiftSection>> Sections;
		TArray<FLiftRoom> Rooms;
		TMap<FString, FVector> NodePos;       // only the nodes the lifts name
		TSet<FString> WantedNodes;
	};

	/** The notable rooms of a deck, the halls first, then by how notable and how near (cm from a point); at most Max different names. */
	void LiftPlacesFor(const FLiftContext& Ctx, int32 Plane, const FVector2D& Near, float X0, float X1, int32 Max, TArray<FString>& Out)
	{
		TArray<const FLiftRoom*> C;
		for (const FLiftRoom& R : Ctx.Rooms)
		{
			if (R.Plane == Plane && R.Weight >= 40 && (X1 <= X0 || (R.Mid.X >= X0 && R.Mid.X <= X1)))
			{
				C.Add(&R);
			}
		}
		C.Sort([&Near](const FLiftRoom& A, const FLiftRoom& B)
		{
			if (A.bExisting != B.bExisting)
			{
				return A.bExisting;
			}
			if (A.Weight != B.Weight)
			{
				return A.Weight > B.Weight;
			}
			return FVector2D::DistSquared(A.Mid, Near) < FVector2D::DistSquared(B.Mid, Near);
		});
		for (const FLiftRoom* R : C)
		{
			if (Out.Num() >= Max)
			{
				break;
			}
			if (!R->Name.IsEmpty() && !Out.Contains(R->Name))
			{
				Out.Add(R->Name);
			}
		}
	}

	void LiftParseShaft(const FLiftObj& V, FLiftContext& Ctx, FAstraLiftNetwork& Net)
	{
		const FLiftObj Shaft = LiftObjOf(V, TEXT("shaft"));
		if (!Shaft.IsValid() || LiftStrOf(V, TEXT("kind")) == TEXT("trunk"))
		{
			return;                                     // the stairs, the older lift (a teleport between rooms), the Jefferies trunks (ladders): not a lift's shaft
		}
		FAstraLiftLine L;
		L.Id = LiftStrOf(V, TEXT("id"));
		L.Name = LiftStrOf(V, TEXT("name"), L.Id);
		L.Kind = LiftKindOf(LiftStrOf(V, TEXT("kind"), TEXT("turbolift")));
		const FString Who = FString::Printf(TEXT("lift %s"), *L.Id);
		L.ShaftCm = FVector(LiftNumOf(Shaft, TEXT("x")) * 100.0, LiftNumOf(Shaft, TEXT("y")) * 100.0, 0.0);
		L.ShaftW = (float)LiftNumOf(Shaft, TEXT("w"), 2.8) * 100.f;
		L.ShaftD = (float)LiftNumOf(Shaft, TEXT("d"), 2.8) * 100.f;
		const TArray<TSharedPtr<FJsonValue>>* Z = nullptr;
		float ShaftZ0 = 0.f, ShaftZ1 = 0.f;
		if (Shaft->TryGetArrayField(TEXT("z"), Z) && Z->Num() >= 2)
		{
			ShaftZ0 = (float)(*Z)[0]->AsNumber() * 100.f;
			ShaftZ1 = (float)(*Z)[1]->AsNumber() * 100.f;
		}
		const FLiftObj Car = LiftObjOf(V, TEXT("car"));
		const bool bBig = L.Kind == EAstraLiftKind::Cargo;
		L.CarW = (float)LiftNumOf(Car, TEXT("w"), bBig ? 3.4 : 2.4) * 100.f;
		L.CarD = (float)LiftNumOf(Car, TEXT("d"), bBig ? 3.0 : 2.4) * 100.f;
		L.CarH = (float)LiftNumOf(Car, TEXT("h"), bBig ? 3.2 : 2.6) * 100.f;
		L.CarFloor = (float)LiftNumOf(Car, TEXT("floor"), 0.0) * 100.f;
		const bool bSlow = L.Kind == EAstraLiftKind::Service || bBig;
		L.SpeedCmS = (float)LiftNumOf(V, TEXT("speed"), bBig ? 3.0 : bSlow ? 5.0 : 8.0) * 100.f;
		L.AccelCmS2 = (float)LiftNumOf(V, TEXT("accel"), bBig ? 1.0 : bSlow ? 1.5 : 2.5) * 100.f;
		if (L.CarW > L.ShaftW - 8.f || L.CarD > L.ShaftD - 8.f)
		{
			Net.Problems.Add(FString::Printf(TEXT("%s: the car (%.2f x %.2f m) does not fit the shaft (%.2f x %.2f m)"), *Who, L.CarW / 100, L.CarD / 100, L.ShaftW / 100, L.ShaftD / 100));
		}

		const TArray<TSharedPtr<FJsonValue>>* Landings = nullptr;
		if (!V->TryGetArrayField(TEXT("landings"), Landings))
		{
			Net.Problems.Add(FString::Printf(TEXT("%s: no landings"), *Who));
			return;
		}
		for (const TSharedPtr<FJsonValue>& LV : *Landings)
		{
			const FLiftObj O = LV->AsObject();
			FVector Door;
			if (!O.IsValid() || !LiftVec3Of(O, TEXT("door"), Door))
			{
				Net.Problems.Add(FString::Printf(TEXT("%s: a landing without a door position"), *Who));
				continue;
			}
			FAstraLiftStop S;
			S.Deck = (int32)LiftNumOf(O, TEXT("deck"));
			S.Id = FString::Printf(TEXT("d%d"), S.Deck);
			S.Label = FString::Printf(TEXT("DECK %d"), S.Deck);
			S.DeckName = Ctx.DeckName.FindRef(S.Deck);
			S.FloorZ = (float)LiftNumOf(O, TEXT("z"), Door.Z / 100.0) * 100.f;
			S.DoorCm = FVector(Door.X, Door.Y, S.FloorZ);
			S.DoorYaw = (float)LiftNumOf(O, TEXT("yaw"));
			S.Lobby = LiftStrOf(O, TEXT("lobby"));
			S.NodeId = LiftStrOf(O, TEXT("node"));
			// which wall of the shaft the door is in: a door turned 0 or 180 is in a wall across x (its passage runs along x), 90 or 270 along y; the sign
			// is where it lies from the shaft's middle
			const bool bAlongX = FMath::Abs(FMath::Cos(FMath::DegreesToRadians(S.DoorYaw))) > 0.5f;
			const float Delta = bAlongX ? (float)(Door.X - L.ShaftCm.X) : (float)(Door.Y - L.ShaftCm.Y);
			S.Out = bAlongX ? FVector(Delta < 0.f ? -1.f : 1.f, 0.f, 0.f) : FVector(0.f, Delta < 0.f ? -1.f : 1.f, 0.f);
			// the door's plane is the shaft's inside face or, through a lobby's wall, up to 60 cm out of it (the landing then bridges the wall: a threshold and a reveal)
			const float Wall = FMath::Abs(Delta) - L.ShaftD * 0.5f;
			if (Wall < -15.f || Wall > 60.f)
			{
				Net.Problems.Add(FString::Printf(TEXT("%s, deck %d: the door is %.2f m from the shaft's middle; its inside face is %.2f m"), *Who, S.Deck, FMath::Abs(Delta) / 100.f, L.ShaftD / 200.f));
			}
			S.WallCm = FMath::Clamp(Wall, 0.f, 60.f);
			if (L.Stops.Num() && !S.Out.Equals(L.Stops[0].Out, 0.01f))
			{
				Net.Problems.Add(FString::Printf(TEXT("%s, deck %d: its door is on another side of the shaft than the others (a car has its door on one side): left out"), *Who, S.Deck));
				continue;
			}
			if (L.FindStopByDeck(S.Deck) != INDEX_NONE)
			{
				Net.Problems.Add(FString::Printf(TEXT("%s: deck %d is listed twice: the second is left out"), *Who, S.Deck));
				continue;
			}
			if (S.FloorZ < ShaftZ0 - 5.f || S.FloorZ > ShaftZ1 + 5.f)
			{
				Net.Problems.Add(FString::Printf(TEXT("%s, deck %d: the landing (z %.2f m) is outside the shaft (%.2f..%.2f m)"), *Who, S.Deck, S.FloorZ / 100, ShaftZ0 / 100, ShaftZ1 / 100));
			}
			if (!S.NodeId.IsEmpty())
			{
				Ctx.WantedNodes.Add(S.NodeId);
			}
			L.Stops.Add(S);
		}
		if (L.Stops.Num() < 2)
		{
			Net.Problems.Add(FString::Printf(TEXT("%s: a lift needs two landings, it has %d"), *Who, L.Stops.Num()));
			return;
		}
		L.Stops.Sort([](const FAstraLiftStop& A, const FAstraLiftStop& B) { return A.FloorZ < B.FloorZ; });
		L.Front = L.Stops[0].Out;
		L.FrontYaw = FMath::RadiansToDegrees(FMath::Atan2(L.Front.Y, L.Front.X));
		L.ZBottom = L.Stops[0].FloorZ;
		L.ZTop = L.Stops.Last().FloorZ;
		L.ShaftCm.Z = ShaftZ0;
		// the car stands against the door side of the shaft, three centimetres from its sill, with the room for the guides behind it
		const float Back = L.ShaftD * 0.5f - L.CarD * 0.5f - 3.f;
		const FVector CarXY = L.ShaftCm + L.Front * Back;
		L.Path.Build({FVector(CarXY.X, CarXY.Y, L.ZBottom), FVector(CarXY.X, CarXY.Y, L.ZTop)});
		for (FAstraLiftStop& S : L.Stops)
		{
			S.S = S.FloorZ - L.ZBottom;
		}
		Net.Lines.Add(MoveTemp(L));
	}

	void LiftParseTransit(const FLiftObj& V, FLiftContext& Ctx, FAstraLiftNetwork& Net)
	{
		const TArray<TSharedPtr<FJsonValue>>* PathPts = nullptr;
		if (!V.IsValid() || !V->TryGetArrayField(TEXT("path"), PathPts) || PathPts->Num() < 2)
		{
			return;                                     // the first version of the plan lists the shuttle's stops but has no line for it to run on
		}
		FAstraLiftLine L;
		L.bShuttle = true;
		L.Kind = EAstraLiftKind::Shuttle;
		L.Id = LiftStrOf(V, TEXT("id"), TEXT("shuttle"));
		L.Name = LiftStrOf(V, TEXT("name"), TEXT("Spine Shuttle"));
		const FString Who = FString::Printf(TEXT("line %s"), *L.Id);
		TArray<FVector> Pts;
		for (const TSharedPtr<FJsonValue>& PV : *PathPts)
		{
			const TArray<TSharedPtr<FJsonValue>>& A = PV->AsArray();
			if (A.Num() >= 3)
			{
				Pts.Add(FVector(A[0]->AsNumber(), A[1]->AsNumber(), A[2]->AsNumber()) * 100.0);
			}
		}
		L.Path.Build(Pts);
		if (!L.Path.IsValid())
		{
			Net.Problems.Add(FString::Printf(TEXT("%s: the path has no length"), *Who));
			return;
		}
		// the car's own frame has its door side on +x: its width runs along the doors (here the whole length of the car, along the line), its depth across
		const FLiftObj Car = LiftObjOf(V, TEXT("car"));
		L.CarLength = (float)LiftNumOf(Car, TEXT("length"), 14.0) * 100.f;
		L.CarW = L.CarLength;
		L.CarD = (float)LiftNumOf(Car, TEXT("w"), 2.8) * 100.f;
		L.CarH = (float)LiftNumOf(Car, TEXT("h"), 2.9) * 100.f;
		L.CarFloor = (float)LiftNumOf(Car, TEXT("floor"), 0.16) * 100.f;
		L.SpeedCmS = (float)LiftNumOf(V, TEXT("speed"), 16.0) * 100.f;
		L.AccelCmS2 = (float)LiftNumOf(V, TEXT("accel"), 2.2) * 100.f;
		const int32 DeckId = (int32)LiftNumOf(V, TEXT("deck"), 5.0);
		const TArray<TSharedPtr<FJsonValue>>* Stops = nullptr;
		if (!V->TryGetArrayField(TEXT("stops"), Stops))
		{
			Net.Problems.Add(FString::Printf(TEXT("%s: no stops"), *Who));
			return;
		}
		for (const TSharedPtr<FJsonValue>& SV : *Stops)
		{
			const FLiftObj O = SV->AsObject();
			FVector Door;
			if (!O.IsValid() || !LiftVec3Of(O, TEXT("door"), Door))
			{
				Net.Problems.Add(FString::Printf(TEXT("%s: a stop without a door position"), *Who));
				continue;
			}
			FAstraLiftStop S;
			S.Deck = DeckId;
			S.Section = LiftStrOf(O, TEXT("section"));
			S.Id = S.Section.IsEmpty() ? FString::Printf(TEXT("s%d"), L.Stops.Num() + 1) : FString::Printf(TEXT("sec_%s"), *S.Section.ToLower());
			S.Label = S.Section.IsEmpty() ? FString::Printf(TEXT("STOP %d"), L.Stops.Num() + 1) : FString::Printf(TEXT("SECTION %s"), *S.Section.ToUpper());
			S.DeckName = Ctx.DeckName.FindRef(DeckId);
			S.S = L.Path.Project(Door);
			const FVector OnPath = L.Path.At(S.S);
			S.DoorCm = Door;
			S.FloorZ = OnPath.Z;
			S.DoorYaw = (float)LiftNumOf(O, TEXT("yaw"));
			// the platform side: from the line to the door; a door on the line itself is across it, on the side the yaw says
			FVector Side = FVector(Door.X - OnPath.X, Door.Y - OnPath.Y, 0.0);
			if (Side.SizeSquared() < 20.0 * 20.0)
			{
				const float Y = FMath::DegreesToRadians(S.DoorYaw);
				Side = FVector(-FMath::Sin(Y), FMath::Cos(Y), 0.f);
			}
			S.Out = Side.GetSafeNormal();
			S.Lobby = LiftStrOf(O, TEXT("room"));
			S.NodeId = LiftStrOf(O, TEXT("node"));
			if (!S.NodeId.IsEmpty())
			{
				Ctx.WantedNodes.Add(S.NodeId);
			}
			L.Stops.Add(S);
		}
		if (L.Stops.Num() < 2)
		{
			Net.Problems.Add(FString::Printf(TEXT("%s: a line needs two stops, it has %d"), *Who, L.Stops.Num()));
			return;
		}
		L.Stops.Sort([](const FAstraLiftStop& A, const FAstraLiftStop& B) { return A.S < B.S; });
		for (int32 I = 1; I < L.Stops.Num(); ++I)
		{
			if (!L.Stops[I].Out.Equals(L.Stops[0].Out, 0.05f))
			{
				Net.Problems.Add(FString::Printf(TEXT("%s: stop %s is on the other side of the line than %s (the car has its doors on one side)"), *Who, *L.Stops[I].Id, *L.Stops[0].Id));
			}
			if (L.Stops[I].S - L.Stops[I - 1].S < L.CarLength * 0.5f)
			{
				Net.Problems.Add(FString::Printf(TEXT("%s: stops %s and %s are %.0f m apart: closer than half a car"), *Who, *L.Stops[I - 1].Id, *L.Stops[I].Id, (L.Stops[I].S - L.Stops[I - 1].S) / 100.f));
			}
		}
		L.Front = L.Stops[0].Out;
		L.FrontYaw = FMath::RadiansToDegrees(FMath::Atan2(L.Front.Y, L.Front.X));
		L.ZBottom = L.ZTop = L.Stops[0].FloorZ;
		L.ShaftCm = L.Path.At(0.f);
		Net.Lines.Add(MoveTemp(L));
	}
}

// =============================================================================================================================== the lines

int32 FAstraLiftLine::FindStopByDeck(int32 Deck) const
{
	for (int32 I = 0; I < Stops.Num(); ++I)
	{
		if (Stops[I].Deck == Deck)
		{
			return I;
		}
	}
	return INDEX_NONE;
}

int32 FAstraLiftLine::FindStopById(const FString& StopId) const
{
	for (int32 I = 0; I < Stops.Num(); ++I)
	{
		if (Stops[I].Id.Equals(StopId, ESearchCase::IgnoreCase))
		{
			return I;
		}
	}
	return INDEX_NONE;
}

int32 FAstraLiftLine::StopBelow(float S) const
{
	int32 Best = 0;
	for (int32 I = 0; I < Stops.Num(); ++I)
	{
		if (Stops[I].S <= S + 1.f)
		{
			Best = I;
		}
	}
	return Best;
}

FString FAstraLiftNetwork::DefaultPlanFile()
{
	const FString Staged = FPaths::Combine(FPaths::ProjectContentDir(), TEXT("ASTRA/Data/aquila_plan.json"));
	return FPaths::FileExists(Staged) ? Staged : FPaths::Combine(FPaths::ProjectDir(), TEXT("data/ship/aquila_plan.json"));
}

int32 FAstraLiftNetwork::FindLine(const FString& Id) const
{
	for (int32 I = 0; I < Lines.Num(); ++I)
	{
		if (Lines[I].Id.Equals(Id, ESearchCase::IgnoreCase))
		{
			return I;
		}
	}
	return INDEX_NONE;
}

bool FAstraLiftNetwork::FindRide(const FVector& A, const FVector& B, int32& OutLine, int32& OutFrom, int32& OutTo, float TolCm) const
{
	auto Near = [TolCm](const FAstraLiftStop& S, const FVector& P)
	{
		const FVector W = S.WaitCm();
		return FVector::Dist2D(W, P) < TolCm && FMath::Abs(W.Z - P.Z) < 90.f;
	};
	for (int32 L = 0; L < Lines.Num(); ++L)
	{
		int32 From = INDEX_NONE, To = INDEX_NONE;
		for (int32 I = 0; I < Lines[L].Stops.Num(); ++I)
		{
			From = From == INDEX_NONE && Near(Lines[L].Stops[I], A) ? I : From;
			To = To == INDEX_NONE && Near(Lines[L].Stops[I], B) ? I : To;
		}
		if (From != INDEX_NONE && To != INDEX_NONE && From != To)
		{
			OutLine = L;
			OutFrom = From;
			OutTo = To;
			return true;
		}
	}
	return false;
}

bool FAstraLiftNetwork::Load(const FString& Path)
{
	Lines.Reset();
	Problems.Reset();
	Notes.Reset();
	Source = Path;
	FString Text;
	if (!FFileHelper::LoadFileToString(Text, *Path))
	{
		return false;
	}
	FLiftObj Root;
	if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Root) || !Root.IsValid())
	{
		Problems.Add(FString::Printf(TEXT("%s does not parse"), *Path));
		return false;
	}
	Text.Empty();
	FLiftContext Ctx;
	const TArray<TSharedPtr<FJsonValue>>* List = nullptr;
	if (Root->TryGetArrayField(TEXT("decks"), List))
	{
		for (const TSharedPtr<FJsonValue>& V : *List)
		{
			const FLiftObj O = V->AsObject();
			const int32 Id = (int32)LiftNumOf(O, TEXT("id"));
			Ctx.DeckName.Add(Id, LiftStrOf(O, TEXT("name")));
			const TArray<TSharedPtr<FJsonValue>>* Secs = nullptr;
			if (O.IsValid() && O->TryGetArrayField(TEXT("sections"), Secs))
			{
				for (const TSharedPtr<FJsonValue>& SV : *Secs)
				{
					const FLiftObj SO = SV->AsObject();
					const TArray<TSharedPtr<FJsonValue>>* X = nullptr;
					if (SO.IsValid() && SO->TryGetArrayField(TEXT("x"), X) && X->Num() >= 2)
					{
						FLiftSection S;
						S.Id = LiftStrOf(SO, TEXT("id"));
						S.X0 = (float)FMath::Min((*X)[0]->AsNumber(), (*X)[1]->AsNumber()) * 100.f;
						S.X1 = (float)FMath::Max((*X)[0]->AsNumber(), (*X)[1]->AsNumber()) * 100.f;
						Ctx.Sections.FindOrAdd(Id).Add(S);
					}
				}
			}
		}
	}
	if (Root->TryGetArrayField(TEXT("compartments"), List))
	{
		for (const TSharedPtr<FJsonValue>& V : *List)
		{
			const FLiftObj O = V->AsObject();
			const TArray<TSharedPtr<FJsonValue>>* B = nullptr;
			if (!O.IsValid() || !O->TryGetArrayField(TEXT("bounds"), B) || B->Num() < 4)
			{
				continue;
			}
			FLiftRoom R;
			R.Kind = LiftStrOf(O, TEXT("kind"));
			R.Weight = LiftNotableWeight(R.Kind);
			if (R.Weight == 0)
			{
				continue;
			}
			R.Id = LiftStrOf(O, TEXT("id"));
			R.Name = LiftStrOf(O, TEXT("name"));
			R.Plane = (int32)LiftNumOf(O, TEXT("plane"), LiftNumOf(O, TEXT("deck")));
			R.bExisting = LiftStrOf(O, TEXT("status")) == TEXT("existing");
			R.X0 = (float)FMath::Min((*B)[0]->AsNumber(), (*B)[2]->AsNumber()) * 100.f;
			R.X1 = (float)FMath::Max((*B)[0]->AsNumber(), (*B)[2]->AsNumber()) * 100.f;
			R.Mid = FVector2D((R.X0 + R.X1) * 0.5, ((*B)[1]->AsNumber() + (*B)[3]->AsNumber()) * 50.0);
			Ctx.Rooms.Add(R);
		}
	}
	if (Root->TryGetArrayField(TEXT("vertical"), List))
	{
		for (const TSharedPtr<FJsonValue>& V : *List)
		{
			LiftParseShaft(V->AsObject(), Ctx, *this);
		}
	}
	if (Root->TryGetArrayField(TEXT("transit"), List))
	{
		for (const TSharedPtr<FJsonValue>& V : *List)
		{
			LiftParseTransit(V->AsObject(), Ctx, *this);
		}
	}
	// the graph nodes the lifts name: where the crew waits for a car
	const FLiftObj Graph = LiftObjOf(Root, TEXT("graph"));
	if (Graph.IsValid() && Ctx.WantedNodes.Num() && Graph->TryGetArrayField(TEXT("nodes"), List))
	{
		for (const TSharedPtr<FJsonValue>& V : *List)
		{
			const FLiftObj O = V->AsObject();
			FVector P;
			if (O.IsValid() && Ctx.WantedNodes.Contains(LiftStrOf(O, TEXT("id"))) && LiftVec3Of(O, TEXT("p"), P))
			{
				Ctx.NodePos.Add(LiftStrOf(O, TEXT("id")), P);
			}
		}
	}
	for (FAstraLiftLine& L : Lines)
	{
		for (FAstraLiftStop& S : L.Stops)
		{
			if (const FVector* P = Ctx.NodePos.Find(S.NodeId))
			{
				S.NodeCm = *P;
				S.bNode = true;
			}
			else if (!S.NodeId.IsEmpty())
			{
				Problems.Add(FString::Printf(TEXT("%s %s: the graph has no node %s"), L.bShuttle ? TEXT("line") : TEXT("lift"), *L.Id, *S.NodeId));
			}
			// the places a car's screen lists beside this stop; the shuttle's are the rooms of its section
			if (L.bShuttle)
			{
				float X0 = 0.f, X1 = 0.f;
				for (const FLiftSection& Sec : Ctx.Sections.FindRef(S.Deck))
				{
					if (Sec.Id.Equals(S.Section, ESearchCase::IgnoreCase))
					{
						X0 = Sec.X0;
						X1 = Sec.X1;
					}
				}
				LiftPlacesFor(Ctx, S.Deck, FVector2D(S.DoorCm.X, S.DoorCm.Y), X0, X1, 4, S.Places);
			}
			else
			{
				LiftPlacesFor(Ctx, S.Deck, FVector2D(S.DoorCm.X, S.DoorCm.Y), 0.f, 0.f, 5, S.Places);
			}
		}
	}
	Notes.Add(FString::Printf(TEXT("%d lines (%d shafts, %d shuttle lines), %d landings"), Lines.Num(), Algo::CountIf(Lines, [](const FAstraLiftLine& L) { return !L.bShuttle; }),
	                          Algo::CountIf(Lines, [](const FAstraLiftLine& L) { return L.bShuttle; }), [this]() { int32 N = 0; for (const FAstraLiftLine& L : Lines) { N += L.Stops.Num(); } return N; }()));
	return true;
}
