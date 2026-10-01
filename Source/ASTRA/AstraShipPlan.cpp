// ASTRA — the ship's plan and its routes.

#include "AstraShipPlan.h"

#include "ASTRA.h"
#include "DrawDebugHelpers.h"
#include "Dom/JsonObject.h"
#include "Engine/World.h"
#include "HAL/IConsoleManager.h"
#include "Kismet/GameplayStatics.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

namespace
{
	FVector Metres(const TArray<TSharedPtr<FJsonValue>>* A)
	{
		return A && A->Num() >= 3 ? FVector((*A)[0]->AsNumber(), (*A)[1]->AsNumber(), (*A)[2]->AsNumber()) * 100.0 : FVector::ZeroVector;
	}

	FAutoConsoleCommandWithWorldAndArgs CmdPlanRoute(TEXT("astra.plan.route"),
		TEXT("Testing: astra.plan.route X Y Z [X Y Z] (metres, the bridge frame): the walking route from the Captain (or the first "
		     "point) to the last point over the ship's plan, drawn for 30 s and printed"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& A, UWorld* World)
		{
			const UAstraShipPlan* Plan = World ? World->GetSubsystem<UAstraShipPlan>() : nullptr;
			if (!Plan || !Plan->EnsureLoaded() || (A.Num() != 3 && A.Num() != 6))
			{
				UE_LOG(LogASTRA, Warning, TEXT("[Plan] usage: astra.plan.route X Y Z [X Y Z] (metres), with data/ship/aquila_plan.json"));
				return;
			}
			auto P = [&A](int32 i) { return FVector(FCString::Atod(*A[i]), FCString::Atod(*A[i + 1]), FCString::Atod(*A[i + 2])) * 100.0; };
			FVector From = A.Num() == 6 ? P(0) : FVector::ZeroVector;
			if (A.Num() == 3)
			{
				if (const APawn* Pawn = UGameplayStatics::GetPlayerPawn(World, 0))
				{
					From = Pawn->GetActorLocation() - FVector(0.f, 0.f, Pawn->GetDefaultHalfHeight());
				}
			}
			const FVector To = P(A.Num() == 6 ? 3 : 0);
			TArray<FVector> Route;
			float Metres = 0.f;
			const double T0 = FPlatformTime::Seconds();
			const bool bOk = Plan->FindRoute(From, To, Route, &Metres);
			const double Ms = (FPlatformTime::Seconds() - T0) * 1000.0;
			UE_LOG(LogASTRA, Log, TEXT("[Plan] route %s: %d points, %.0f m of walking, found in %.2f ms"), bOk ? TEXT("found") : TEXT("NONE"),
			       Route.Num(), Metres, Ms);
			for (int32 i = 1; i < Route.Num(); ++i)
			{
				DrawDebugLine(World, Route[i - 1] + FVector(0, 0, 30), Route[i] + FVector(0, 0, 30), FColor(80, 220, 255), false, 30.f, 0, 6.f);
			}
		}));

	FAutoConsoleCommandWithWorld CmdPlanInfo(TEXT("astra.plan.info"), TEXT("The ship's plan: what is loaded, and where the Captain stands in it"),
		FConsoleCommandWithWorldDelegate::CreateLambda([](UWorld* World)
		{
			const UAstraShipPlan* Plan = World ? World->GetSubsystem<UAstraShipPlan>() : nullptr;
			if (!Plan || !Plan->EnsureLoaded())
			{
				UE_LOG(LogASTRA, Log, TEXT("[Plan] no plan (data/ship/aquila_plan.json)"));
				return;
			}
			FString Where = TEXT("outside the plan");
			if (const APawn* Pawn = UGameplayStatics::GetPlayerPawn(World, 0))
			{
				if (const FAstraPlanCompartment* C = Plan->CompartmentAt(Pawn->GetActorLocation()))
				{
					Where = FString::Printf(TEXT("%s (%s, deck %d, section %s)"), *C->Name, *C->Id, C->Deck, *C->Section);
				}
			}
			UE_LOG(LogASTRA, Log, TEXT("[Plan] %d places, %d ways; the Captain: %s"), Plan->NumNodes(), Plan->NumEdges(), *Where);
		}));
}

bool UAstraShipPlan::EnsureLoaded() const
{
	if (!bTried)
	{
		bTried = true;
		const double T0 = FPlatformTime::Seconds();
		const bool bOk = Load();
		UE_LOG(LogASTRA, Log, TEXT("[Plan] %s (%d places, %d ways, %d compartments, %d doors; %.0f ms)"),
		       bOk ? TEXT("ship's plan loaded") : TEXT("no ship's plan (data/ship/aquila_plan.json)"), Nodes.Num(), Edges.Num(), Comps.Num(), Doors.Num(),
		       (FPlatformTime::Seconds() - T0) * 1000.0);
	}
	return Nodes.Num() > 0;
}

bool UAstraShipPlan::Load() const
{
	FString Text;
	// staged with the game (Content/ASTRA/Data, always packaged as a loose file: DefaultGame.ini); the repository's data/ship
	// copy is the one the plan generator writes
	if (!FFileHelper::LoadFileToString(Text, *FPaths::Combine(FPaths::ProjectContentDir(), TEXT("ASTRA/Data/aquila_plan.json")))
	    && !FFileHelper::LoadFileToString(Text, *FPaths::Combine(FPaths::ProjectDir(), TEXT("data/ship/aquila_plan.json"))))
	{
		return false;
	}
	TSharedPtr<FJsonObject> Root;
	if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Root) || !Root.IsValid())
	{
		UE_LOG(LogASTRA, Warning, TEXT("[Plan] aquila_plan.json does not parse"));
		return false;
	}
	TMap<FString, int32> CompIndex;
	const TArray<TSharedPtr<FJsonValue>>* List = nullptr;
	if (Root->TryGetArrayField(TEXT("decks"), List))
	{
		for (const TSharedPtr<FJsonValue>& V : *List)
		{
			const TSharedPtr<FJsonObject> O = V->AsObject();
			if (!O.IsValid())
			{
				continue;
			}
			FAstraPlanDeck D;
			D.Id = (int32)O->GetNumberField(TEXT("id"));
			O->TryGetStringField(TEXT("name"), D.Name);
			D.FloorZ = (float)O->GetNumberField(TEXT("z")) * 100.f;
			const TArray<TSharedPtr<FJsonValue>>* Secs = nullptr;
			if (O->TryGetArrayField(TEXT("sections"), Secs))
			{
				for (const TSharedPtr<FJsonValue>& SV : *Secs)
				{
					const TSharedPtr<FJsonObject> SO = SV->AsObject();
					const TArray<TSharedPtr<FJsonValue>>* X = nullptr;
					if (SO.IsValid() && SO->TryGetArrayField(TEXT("x"), X) && X->Num() >= 2)
					{
						FAstraPlanDeck::FSection Sec;
						Sec.Id = SO->GetStringField(TEXT("id"));
						Sec.X0 = (float)FMath::Min((*X)[0]->AsNumber(), (*X)[1]->AsNumber()) * 100.f;
						Sec.X1 = (float)FMath::Max((*X)[0]->AsNumber(), (*X)[1]->AsNumber()) * 100.f;
						D.Sections.Add(Sec);
					}
				}
			}
			const TSharedPtr<FJsonObject>* Env = nullptr;
			const TArray<TSharedPtr<FJsonValue>>* HW = nullptr;
			if (O->TryGetObjectField(TEXT("envelope"), Env) && (*Env)->TryGetArrayField(TEXT("half_width"), HW))
			{
				for (const TSharedPtr<FJsonValue>& PV : *HW)
				{
					const TArray<TSharedPtr<FJsonValue>>& Pair = PV->AsArray();
					if (Pair.Num() >= 2)
					{
						D.HalfWidth.Add(FVector2D(Pair[0]->AsNumber() * 100.0, Pair[1]->AsNumber() * 100.0));
					}
				}
			}
			Decks.Add(D);
		}
		Decks.Sort([](const FAstraPlanDeck& A, const FAstraPlanDeck& B) { return A.Id < B.Id; });
	}
	if (Root->TryGetArrayField(TEXT("compartments"), List))
	{
		for (const TSharedPtr<FJsonValue>& V : *List)
		{
			const TSharedPtr<FJsonObject> O = V->AsObject();
			const TArray<TSharedPtr<FJsonValue>>* B = nullptr;
			const TArray<TSharedPtr<FJsonValue>>* Z = nullptr;
			if (!O.IsValid() || !O->TryGetArrayField(TEXT("bounds"), B) || B->Num() < 4 || !O->TryGetArrayField(TEXT("z"), Z) || Z->Num() < 2)
			{
				continue;
			}
			FAstraPlanCompartment C;
			C.Id = O->GetStringField(TEXT("id"));
			O->TryGetStringField(TEXT("name"), C.Name);
			O->TryGetStringField(TEXT("kind"), C.Kind);
			O->TryGetStringField(TEXT("section"), C.Section);
			C.Deck = (int32)O->GetNumberField(TEXT("deck"));
			C.Box = FBox(FVector((*B)[0]->AsNumber(), (*B)[1]->AsNumber(), (*Z)[0]->AsNumber()) * 100.0,
			             FVector((*B)[2]->AsNumber(), (*B)[3]->AsNumber(), (*Z)[1]->AsNumber()) * 100.0);
			CompIndex.Add(C.Id, Comps.Add(C));
		}
	}
	if (Root->TryGetArrayField(TEXT("doors"), List))
	{
		for (const TSharedPtr<FJsonValue>& V : *List)
		{
			const TSharedPtr<FJsonObject> O = V->AsObject();
			if (!O.IsValid())
			{
				continue;
			}
			FAstraPlanDoor D;
			D.Id = O->GetStringField(TEXT("id"));
			O->TryGetStringField(TEXT("kind"), D.Kind);
			D.Deck = (int32)O->GetNumberField(TEXT("deck"));
			const TArray<TSharedPtr<FJsonValue>>* P = nullptr;
			O->TryGetArrayField(TEXT("pos"), P);
			D.Pos = Metres(P);
			D.Yaw = (float)O->GetNumberField(TEXT("yaw"));
			FString A, B;
			D.A = O->TryGetStringField(TEXT("a"), A) ? CompIndex.FindRef(A, INDEX_NONE) : INDEX_NONE;
			D.B = O->TryGetStringField(TEXT("b"), B) ? CompIndex.FindRef(B, INDEX_NONE) : INDEX_NONE;
			O->TryGetBoolField(TEXT("locked"), D.bLocked);
			DoorIndex.Add(D.Id, Doors.Add(D));
		}
	}
	const TSharedPtr<FJsonObject>* Graph = nullptr;
	if (!Root->TryGetObjectField(TEXT("graph"), Graph))
	{
		return false;
	}
	TMap<FString, int32> NodeIndex;
	if ((*Graph)->TryGetArrayField(TEXT("nodes"), List))
	{
		Nodes.Reserve(List->Num());
		for (const TSharedPtr<FJsonValue>& V : *List)
		{
			const TSharedPtr<FJsonObject> O = V->AsObject();
			const TArray<TSharedPtr<FJsonValue>>* P = nullptr;
			if (!O.IsValid() || !O->TryGetArrayField(TEXT("p"), P))
			{
				continue;
			}
			FAstraPlanNode N;
			N.Id = O->GetStringField(TEXT("id"));
			N.Pos = Metres(P);
			N.Deck = (int32)O->GetNumberField(TEXT("deck"));
			N.Kind = FName(*O->GetStringField(TEXT("kind")));
			FString C;
			N.Comp = O->TryGetStringField(TEXT("comp"), C) ? CompIndex.FindRef(C, INDEX_NONE) : INDEX_NONE;
			NodeIndex.Add(N.Id, Nodes.Add(N));
		}
	}
	Adjacent.SetNum(Nodes.Num());
	if ((*Graph)->TryGetArrayField(TEXT("edges"), List))
	{
		Edges.Reserve(List->Num());
		for (const TSharedPtr<FJsonValue>& V : *List)
		{
			const TSharedPtr<FJsonObject> O = V->AsObject();
			if (!O.IsValid())
			{
				continue;
			}
			FAstraPlanEdge E;
			E.A = NodeIndex.FindRef(O->GetStringField(TEXT("a")), INDEX_NONE);
			E.B = NodeIndex.FindRef(O->GetStringField(TEXT("b")), INDEX_NONE);
			if (E.A == INDEX_NONE || E.B == INDEX_NONE)
			{
				continue;
			}
			E.LenM = (float)O->GetNumberField(TEXT("len"));
			const FString K = O->GetStringField(TEXT("kind"));
			E.Kind = K == TEXT("door") ? FAstraPlanEdge::EKind::Door : K == TEXT("stair") ? FAstraPlanEdge::EKind::Stair : K == TEXT("lift") ? FAstraPlanEdge::EKind::Lift : FAstraPlanEdge::EKind::Walk;
			FString Door;
			E.Door = O->TryGetStringField(TEXT("door"), Door) ? DoorIndex.FindRef(Door, INDEX_NONE) : INDEX_NONE;
			double W = 0.0;
			if (O->TryGetNumberField(TEXT("w"), W))
			{
				E.WidthM = (float)W;
			}
			O->TryGetBoolField(TEXT("blast"), E.bBlast);
			const int32 I = Edges.Add(E);
			Adjacent[E.A].Add(I);
			Adjacent[E.B].Add(I);
		}
	}
	return Nodes.Num() > 0;
}

float UAstraShipPlan::EdgeCost(const FAstraPlanEdge& E, bool bKeys, bool bThroughSealed) const
{
	float Extra = 0.f;
	if (Doors.IsValidIndex(E.Door))
	{
		const FAstraPlanDoor& D = Doors[E.Door];
		if (D.bSealed && !bThroughSealed)
		{
			return -1.f;
		}
		if (D.bLocked && !bKeys)
		{
			return -1.f;
		}
		Extra = D.bSealed ? 14.f : 0.f;         // a suited party cycles the hatch of a shut bulkhead
	}
	switch (E.Kind)
	{
	case FAstraPlanEdge::EKind::Stair: return E.LenM * 1.8f + Extra;          // climbing is slower than walking
	case FAstraPlanEdge::EKind::Lift:  return 12.f + E.LenM * 0.3f + Extra;   // a short wait for the car, then a quick ride
	case FAstraPlanEdge::EKind::Door:  return E.LenM + 1.f + Extra;           // a door to open
	default:                    return E.LenM + Extra;
	}
}

int32 UAstraShipPlan::NearestNode(const FVector& Cm, int32 Deck) const
{
	if (!EnsureLoaded())
	{
		return INDEX_NONE;
	}
	// a place in the same compartment first (not the corridor behind the wall), then the nearest on the deck
	const FAstraPlanCompartment* Here = CompartmentAt(Cm);
	const int32 HereIndex = Here ? (int32)(Here - Comps.GetData()) : INDEX_NONE;
	int32 Best = INDEX_NONE;
	double BestD = TNumericLimits<double>::Max();
	for (int32 i = 0; i < Nodes.Num(); ++i)
	{
		const FAstraPlanNode& N = Nodes[i];
		if (Deck != INDEX_NONE && N.Deck != Deck)
		{
			continue;
		}
		double D = FVector::DistSquared(N.Pos, Cm);
		if (HereIndex != INDEX_NONE && N.Comp != HereIndex)
		{
			D = D * 4.0 + 1.0e6;    // another room: only when nothing of this one is in the graph
		}
		if (D < BestD)
		{
			BestD = D;
			Best = i;
		}
	}
	return Best;
}

const FAstraPlanCompartment* UAstraShipPlan::CompartmentAt(const FVector& Cm) const
{
	if (!EnsureLoaded())
	{
		return nullptr;
	}
	// the smallest compartment containing the point (a room inside a larger space wins over the space)
	const FAstraPlanCompartment* Best = nullptr;
	double BestVolume = TNumericLimits<double>::Max();
	for (const FAstraPlanCompartment& C : Comps)
	{
		if (C.Box.IsInsideOrOn(Cm))
		{
			const double V = C.Box.GetVolume();
			if (V < BestVolume)
			{
				BestVolume = V;
				Best = &C;
			}
		}
	}
	return Best;
}

void UAstraShipPlan::SetDoorSealed(const FString& DoorId, bool bSealed)
{
	if (EnsureLoaded())
	{
		if (const int32* I = DoorIndex.Find(DoorId))
		{
			Doors[*I].bSealed = bSealed;
		}
	}
}

bool UAstraShipPlan::FindRoute(const FVector& From, const FVector& To, TArray<FVector>& Out, float* OutMetres, bool bKeys, bool bThroughSealed) const
{
	Out.Reset();
	const int32 S = NearestNode(From), G = NearestNode(To);
	if (S == INDEX_NONE || G == INDEX_NONE)
	{
		return false;
	}
	// A* on metres of walking; the estimate is the straight line at a lift's pace (never more than the real cost)
	const int32 N = Nodes.Num();
	TArray<float> Cost;
	Cost.Init(TNumericLimits<float>::Max(), N);
	TArray<int32> Came;
	Came.Init(INDEX_NONE, N);
	TArray<bool> Done;
	Done.Init(false, N);
	struct FOpen { float F; int32 Node; bool operator<(const FOpen& O) const { return F < O.F; } };
	TArray<FOpen> Open;
	auto H = [this, G](int32 i) { return (float)(FVector::Dist(Nodes[i].Pos, Nodes[G].Pos) / 100.0) * 0.3f; };
	Cost[S] = 0.f;
	Open.HeapPush({H(S), S});
	while (Open.Num())
	{
		FOpen Top;
		Open.HeapPop(Top);
		const int32 U = Top.Node;
		if (Done[U])
		{
			continue;
		}
		Done[U] = true;
		if (U == G)
		{
			break;
		}
		for (const int32 EI : Adjacent[U])
		{
			const FAstraPlanEdge& E = Edges[EI];
			const float C = EdgeCost(E, bKeys);
			if (C < 0.f)
			{
				continue;
			}
			const int32 V = E.A == U ? E.B : E.A;
			if (!Done[V] && Cost[U] + C < Cost[V])
			{
				Cost[V] = Cost[U] + C;
				Came[V] = U;
				Open.HeapPush({Cost[V] + H(V), V});
			}
		}
	}
	if (!Done[G])
	{
		return false;
	}
	// the points, from the start: where one stands, then the places of the graph, then the goal
	TArray<int32> Path;
	for (int32 i = G; i != INDEX_NONE; i = Came[i])
	{
		Path.Add(i);
	}
	Out.Add(From);
	float Metres = 0.f;
	for (int32 i = Path.Num() - 1; i >= 0; --i)
	{
		Metres += (float)(FVector::Dist(Out.Last(), Nodes[Path[i]].Pos) / 100.0);
		Out.Add(Nodes[Path[i]].Pos);
	}
	Metres += (float)(FVector::Dist(Out.Last(), To) / 100.0);
	Out.Add(To);
	if (OutMetres)
	{
		*OutMetres = Metres;
	}
	return true;
}

float FAstraPlanDeck::HalfWidthAt(float X) const
{
	// the envelope's samples run from the bow aft (x falling); between two of them, linearly
	for (int32 i = 0; i + 1 < HalfWidth.Num(); ++i)
	{
		const FVector2D& A = HalfWidth[i];
		const FVector2D& B = HalfWidth[i + 1];
		if (X <= FMath::Max(A.X, B.X) && X >= FMath::Min(A.X, B.X))
		{
			const double T = FMath::IsNearlyEqual(A.X, B.X) ? 0.0 : (X - A.X) / (B.X - A.X);
			return (float)FMath::Lerp(A.Y, B.Y, T);
		}
	}
	return 0.f;
}

int32 UAstraShipPlan::DeckAt(const FVector& Cm) const
{
	EnsureLoaded();
	int32 Best = 0;
	float BestFloor = -1e9f;
	for (const FAstraPlanDeck& D : Decks)
	{
		// on a deck: at most a deck's height (4 m) above its floor, 1 m below it (a lift car, a sunken well)
		if (Cm.Z >= D.FloorZ - 100.f && Cm.Z < D.FloorZ + 400.f && D.FloorZ > BestFloor)
		{
			Best = D.Id;
			BestFloor = D.FloorZ;
		}
	}
	return Best;
}
