// ASTRA — the interior's self-check (astra.check.map): every walkable floor of the plan is solid where the plan says it is, nothing is drawn
// twice on it (two coplanar surfaces flicker), and every door can be walked through. Run with every deck loaded:
//     astra.decks.all 1     (wait until the decks are in the world)
//     astra.check.map [deck]
// The summary goes to the log; every issue, with where it is, to Saved/Check/map_check.json.

#include "ASTRA.h"
#include "AstraDoor.h"
#include "AstraShipPlan.h"
#include "CollisionQueryParams.h"
#include "Components/PrimitiveComponent.h"
#include "Dom/JsonObject.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/Character.h"
#include "HAL/IConsoleManager.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"

namespace AstraMapCheck
{
	struct FIssue
	{
		FString Kind, Comp, Name, Detail;
		int32 Deck = 0;
		FVector At = FVector::ZeroVector;
	};

	/** The kinds of compartment a person walks across (stairs, lifts, tanks, trunks and pods have floors of their own kind). */
	bool Walkable(const FString& Kind)
	{
		static const TSet<FString> No = {TEXT("trunk"), TEXT("lift"), TEXT("tank"), TEXT("stairs"), TEXT("lifepod"), TEXT("tunnel"), TEXT("crawlway")};
		return !No.Contains(Kind);
	}

	FString Owner(const FHitResult& H)
	{
		const UPrimitiveComponent* C = H.GetComponent();
		const AActor* A = H.GetActor();
		return FString::Printf(TEXT("%s/%s"), A ? *A->GetName() : TEXT("?"), C ? *C->GetName() : TEXT("?"));
	}

	void Run(UWorld* W, int32 OnlyDeck)
	{
		const UAstraShipPlan* Plan = W ? W->GetSubsystem<UAstraShipPlan>() : nullptr;
		if (!Plan || !Plan->EnsureLoaded())
		{
			UE_LOG(LogASTRA, Warning, TEXT("[MapCheck] no plan"));
			return;
		}
		FCollisionQueryParams Q(SCENE_QUERY_STAT(AstraMapCheck), false);
		FCollisionQueryParams QComplex(SCENE_QUERY_STAT(AstraMapCheckComplex), true);
		TArray<AActor*> Pawns;
		for (TActorIterator<ACharacter> It(W); It; ++It)
		{
			Pawns.Add(*It);
		}
		Q.AddIgnoredActors(Pawns);
		QComplex.AddIgnoredActors(Pawns);
		FCollisionQueryParams QDoor = Q;
		for (TActorIterator<AAstraDoor> It(W); It; ++It)
		{
			QDoor.AddIgnoredActor(*It);                 // (a door opens for him: what must not stand in the way is the frame, a wall, a crate)
		}
		const FCollisionObjectQueryParams Statics(FCollisionObjectQueryParams::InitType::AllStaticObjects);

		TArray<FIssue> Issues;
		TMap<int32, FIntVector> PerDeck;                // deck -> (points, holes, flicker)
		int32 Points = 0, Covered = 0, NotLoaded = 0;
		const TArray<FAstraPlanCompartment>& Comps = Plan->GetCompartments();
		for (const FAstraPlanCompartment& C : Comps)
		{
			if ((OnlyDeck > 0 && C.Deck != OnlyDeck) || !C.bBuilt || !Walkable(C.Kind) || !C.Box.IsValid)
			{
				continue;
			}
			const double Floor = C.Box.Min.Z;
			const double Step = 80.0, Inset = 35.0;
			const FVector Size = C.Box.GetSize();
			if (Size.X < 2.0 * Inset || Size.Y < 2.0 * Inset)
			{
				continue;
			}
			// a compartment whose deck is not in the world shows nothing at all: one probe at its middle says so
			FHitResult Probe;
			const FVector Mid(C.Box.GetCenter().X, C.Box.GetCenter().Y, Floor);
			if (!W->LineTraceSingleByObjectType(Probe, Mid + FVector(0, 0, 300), Mid - FVector(0, 0, 300), Statics, Q))
			{
				++NotLoaded;
				continue;
			}
			int32 Holes = 0, Low = 0, Flicker = 0, Sink = 0, N = 0;
			FVector FirstHole = FVector::ZeroVector, FirstLow = FVector::ZeroVector, FirstFlicker = FVector::ZeroVector, FirstSink = FVector::ZeroVector;
			FString FlickerWho, SinkWho;
			TArray<FString> HolePoints;
			for (double X = C.Box.Min.X + Inset; X <= C.Box.Max.X - Inset; X += Step)
			{
				for (double Y = C.Box.Min.Y + Inset; Y <= C.Box.Max.Y - Inset; Y += Step)
				{
					++N;
					++Points;
					const FVector P(X, Y, Floor);
					FHitResult H;
					if (!W->LineTraceSingleByChannel(H, P + FVector(0, 0, 100), P - FVector(0, 0, 150), ECC_Pawn, Q))
					{
						if (Holes++ == 0) { FirstHole = P; }
						if (HolePoints.Num() < 400) { HolePoints.Add(FString::Printf(TEXT("%.1f %.1f"), X / 100.0, Y / 100.0)); }
						continue;
					}
					const double Dz = H.ImpactPoint.Z - Floor;
					if (Dz > 60.0)
					{
						++Covered;                          // (a console, a bed, a crate on it: its floor cannot be seen from here)
						continue;
					}
					if (Dz < -30.0)
					{
						if (Low++ == 0) { FirstLow = P; }
						if (HolePoints.Num() < 400) { HolePoints.Add(FString::Printf(TEXT("%.1f %.1f low %.0f"), X / 100.0, Y / 100.0, Dz)); }
						continue;
					}
					// the floor that is drawn above the floor that is walked on: the feet sink into it
					FHitResult Seen;
					if (W->LineTraceSingleByChannel(Seen, P + FVector(0, 0, 100), P - FVector(0, 0, 150), ECC_Visibility, QComplex)
					    && Seen.ImpactPoint.Z - H.ImpactPoint.Z > 4.0 && Seen.ImpactPoint.Z - H.ImpactPoint.Z < 60.0 && Seen.ImpactNormal.Z > 0.9f)
					{
						if (Sink++ == 0)
						{
							FirstSink = P;
							SinkWho = FString::Printf(TEXT("drawn %s %.0f cm above the walked %s"), *Owner(Seen), Seen.ImpactPoint.Z - H.ImpactPoint.Z, *Owner(H));
						}
					}
					// two surfaces at the floor's height from two different meshes: the picture flickers between them
					TArray<FHitResult> Hits;
					W->LineTraceMultiByObjectType(Hits, P + FVector(0, 0, 8), P - FVector(0, 0, 8), Statics, QComplex);
					for (int32 i = 0; i < Hits.Num() && FirstFlicker.IsZero(); ++i)
					{
						for (int32 j = i + 1; j < Hits.Num(); ++j)
						{
							if (Hits[i].GetComponent() != Hits[j].GetComponent() && FMath::Abs(Hits[i].ImpactPoint.Z - Hits[j].ImpactPoint.Z) < 0.005
							    && Hits[i].ImpactNormal.Z > 0.9f && Hits[j].ImpactNormal.Z > 0.9f)
							{
								FirstFlicker = P;
								FlickerWho = Owner(Hits[i]) + TEXT(" & ") + Owner(Hits[j]);
								break;
							}
						}
					}
					Flicker += FirstFlicker == P ? 1 : 0;
				}
			}
			FIntVector& D = PerDeck.FindOrAdd(C.Deck);
			D.X += N;
			D.Y += Holes + Low;
			D.Z += Flicker;
			if (Holes + Low > 0)
			{
				// (a floor with a few points missing is a gap: walking across, he drops into it)
				Issues.Add({TEXT("floor_hole"), C.Id, C.Name, FString::Printf(TEXT("%d of %d points without a floor under them (%d with it far below): %s"), Holes + Low, N, Low,
				                                                              *FString::Join(HolePoints, TEXT("; "))),
				            C.Deck, Holes ? FirstHole : FirstLow});
			}
			if (Sink > 2)
			{
				Issues.Add({TEXT("floor_sink"), C.Id, C.Name, FString::Printf(TEXT("%d of %d points: %s"), Sink, N, *SinkWho), C.Deck, FirstSink});
			}
			if (Flicker > 0)
			{
				Issues.Add({TEXT("floor_flicker"), C.Id, C.Name, FlickerWho, C.Deck, FirstFlicker});
			}
		}

		// the doors: a body walks through each, from a metre and a quarter before it to as far after, the door itself open for him
		int32 Doors = 0, Blocked = 0;
		for (const FAstraPlanDoor& Dr : Plan->GetDoors())
		{
			if (OnlyDeck > 0 && Dr.Deck != OnlyDeck)
			{
				continue;
			}
			const FAstraPlanCompartment* A = Comps.IsValidIndex(Dr.A) ? &Comps[Dr.A] : nullptr;
			const FAstraPlanCompartment* B = Comps.IsValidIndex(Dr.B) ? &Comps[Dr.B] : nullptr;
			if (!A || !B || !A->bBuilt || !B->bBuilt)
			{
				if ((A && !A->bBuilt) || (B && !B->bBuilt))
				{
					Issues.Add({TEXT("door_to_nothing"), Dr.Id, A && !A->bBuilt ? A->Name : (B ? B->Name : FString()), TEXT("one side of the door is not built"), Dr.Deck, Dr.Pos});
				}
				continue;
			}
			FHitResult Probe;
			if (!W->LineTraceSingleByObjectType(Probe, Dr.Pos + FVector(0, 0, 200), Dr.Pos - FVector(0, 0, 200), Statics, Q))
			{
				continue;                                   // (its deck is not loaded)
			}
			++Doors;
			const FVector Dir = FRotator(0.f, Dr.Yaw, 0.f).Vector();
			const FVector Side = FVector::CrossProduct(FVector::UpVector, Dir).GetSafeNormal();
			const FVector Lift(0, 0, 97.0);
			FHitResult H;
			bool bHit = true;
			for (const double Off : {0.0, -25.0, 25.0})
			{
				FHitResult One;
				const FVector O = Side * Off + Lift;
				if (!W->SweepSingleByChannel(One, Dr.Pos - Dir * 125.0 + O, Dr.Pos + Dir * 125.0 + O, FQuat::Identity, ECC_Pawn,
				                             FCollisionShape::MakeCapsule(22.f, 85.f), QDoor))
				{
					bHit = false;
					break;
				}
				if (Off == 0.0)
				{
					H = One;
				}
			}
			if (bHit)
			{
				++Blocked;
				Issues.Add({TEXT("door_blocked"), Dr.Id, A->Name + TEXT(" | ") + B->Name, FString::Printf(TEXT("%s, %.0f cm into the walk"), *Owner(H), H.Distance), Dr.Deck, H.ImpactPoint});
			}
		}

		// the summary, and the whole list on disk
		TArray<int32> Decks;
		PerDeck.GetKeys(Decks);
		Decks.Sort();
		for (const int32 D : Decks)
		{
			const FIntVector& V = PerDeck[D];
			UE_LOG(LogASTRA, Display, TEXT("[MapCheck] deck %2d: %6d floor points, %4d without a floor, %4d flickering"), D, V.X, V.Y, V.Z);
		}
		int32 NHoles = 0, NFlicker = 0, NNothing = 0, NSink = 0;
		for (const FIssue& I : Issues)
		{
			NSink += I.Kind == TEXT("floor_sink");
			NHoles += I.Kind == TEXT("floor_hole");
			NFlicker += I.Kind == TEXT("floor_flicker");
			NNothing += I.Kind == TEXT("door_to_nothing");
		}
		UE_LOG(LogASTRA, Display, TEXT("[MapCheck] %d points (%d under furniture), %d compartments not loaded; rooms with holes %d, sinking %d, flickering %d; doors %d walked, %d blocked, %d lead to nothing"),
		       Points, Covered, NotLoaded, NHoles, NSink, NFlicker, Doors, Blocked, NNothing);
		TArray<TSharedPtr<FJsonValue>> Out;
		for (const FIssue& I : Issues)
		{
			TSharedRef<FJsonObject> O = MakeShared<FJsonObject>();
			O->SetStringField(TEXT("kind"), I.Kind);
			O->SetStringField(TEXT("id"), I.Comp);
			O->SetStringField(TEXT("name"), I.Name);
			O->SetStringField(TEXT("detail"), I.Detail);
			O->SetNumberField(TEXT("deck"), I.Deck);
			O->SetStringField(TEXT("at_m"), FString::Printf(TEXT("%.2f %.2f %.2f"), I.At.X / 100.0, I.At.Y / 100.0, I.At.Z / 100.0));
			Out.Add(MakeShared<FJsonValueObject>(O));
		}
		FString Text;
		const TSharedRef<TJsonWriter<>> Wr = TJsonWriterFactory<>::Create(&Text);
		FJsonSerializer::Serialize(Out, Wr);
		const FString Path = FPaths::ProjectSavedDir() / TEXT("Check/map_check.json");
		FFileHelper::SaveStringToFile(Text, *Path, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
		UE_LOG(LogASTRA, Display, TEXT("[MapCheck] %d issues written to %s"), Issues.Num(), *Path);
	}

	FAutoConsoleCommandWithWorldAndArgs CmdMapCheck(TEXT("astra.check.map"),
		TEXT("The interior's self-check: floors solid where the plan says (holes, sunk floors), coplanar surfaces that flicker, doors that cannot be walked through. "
		     "astra.check.map [deck]; load every deck first (astra.decks.all 1). Report: Saved/Check/map_check.json"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* W)
		{
			Run(W, Args.Num() ? FCString::Atoi(*Args[0]) : 0);
		}));
}
