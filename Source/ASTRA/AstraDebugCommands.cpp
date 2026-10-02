// ASTRA — the lead's console tools for finding out what a place is made of, in the running game (no editor needed): what the Captain
// stands on, what he looks at. Each prints the actor, the component, the mesh and the collision of what the ray met, so a wall nobody
// expected or a floor that holds a rider in a lift shaft can be traced back to the script that placed it.
//
//   astra.debug.under      the ray down from the Captain's feet (2 m)
//   astra.debug.lookat     the ray from the eye along the view (50 m)
//   astra.debug.hide_material <part of a material's name>   everything drawn with such a material is hidden ("" shows it again): what a
//                          material costs, A/B with tools/perf_ab.py ("astra.debug.hide_material" "" MI_ASTRA_Glass)
//   astra.debug.floors <deck> [step m]   the gaps in a deck's floors: a grid of rays down in every built room of the plan, as the Captain's capsule
//                          meets them (the hull's skin ignored, as he ignores it): where one finds nothing, he would fall out of the ship

#include "ASTRA.h"
#include "AstraDeckStreaming.h"
#include "AstraShipPlan.h"
#include "Engine/StaticMeshActor.h"
#include "EngineUtils.h"
#include "Components/PrimitiveComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "GameFramework/Character.h"
#include "GameFramework/PlayerController.h"
#include "Camera/PlayerCameraManager.h"
#include "HAL/IConsoleManager.h"
#include "Kismet/GameplayStatics.h"
#include "Materials/MaterialInterface.h"
#include "UObject/UObjectIterator.h"

namespace
{
	void AstraDebugRay(UWorld* W, const FVector& From, const FVector& To, const TCHAR* What)
	{
		APawn* P = UGameplayStatics::GetPlayerPawn(W, 0);
		FCollisionQueryParams Q(SCENE_QUERY_STAT(AstraDebugRay), true, P);
		TArray<FHitResult> Hits;
		W->LineTraceMultiByChannel(Hits, From, To, ECC_Visibility, Q);
		FHitResult Block;
		const bool bBlock = W->LineTraceSingleByChannel(Block, From, To, ECC_Pawn, Q);
		UE_LOG(LogASTRA, Log, TEXT("[Debug] %s from (%.2f, %.2f, %.2f) m: %d visible hits; the pawn's channel is %s"), What, From.X / 100.0, From.Y / 100.0,
		       From.Z / 100.0, Hits.Num(), bBlock ? *FString::Printf(TEXT("blocked at %.2f m by %s"), Block.Distance / 100.0,
		                                                           Block.GetComponent() ? *Block.GetComponent()->GetPathName() : TEXT("?")) : TEXT("clear"));
		for (const FHitResult& H : Hits)
		{
			const UPrimitiveComponent* C = H.GetComponent();
			const UStaticMeshComponent* SM = Cast<UStaticMeshComponent>(C);
			UE_LOG(LogASTRA, Log, TEXT("[Debug]   %.2f m  at (%.2f, %.2f, %.2f)  actor %s  component %s  mesh %s  collision %s  item %d"), H.Distance / 100.0,
			       H.ImpactPoint.X / 100.0, H.ImpactPoint.Y / 100.0, H.ImpactPoint.Z / 100.0, H.GetActor() ? *H.GetActor()->GetName() : TEXT("-"),
			       C ? *C->GetName() : TEXT("-"), SM && SM->GetStaticMesh() ? *SM->GetStaticMesh()->GetName() : TEXT("-"),
			       C ? *C->GetCollisionProfileName().ToString() : TEXT("-"), H.Item);
		}
	}

	FAutoConsoleCommandWithWorld CmdUnder(TEXT("astra.debug.under"), TEXT("What the Captain stands on: the ray down from his feet (actor, component, mesh, collision)"),
		FConsoleCommandWithWorldDelegate::CreateLambda([](UWorld* W)
		{
			const ACharacter* C = Cast<ACharacter>(UGameplayStatics::GetPlayerPawn(W, 0));
			if (!C)
			{
				return;
			}
			const FVector Feet = C->GetActorLocation() - FVector(0.f, 0.f, C->GetDefaultHalfHeight() - 20.f);
			AstraDebugRay(W, Feet, Feet - FVector(0.f, 0.f, 200.f), TEXT("under the Captain"));
		}));

	// the components a material name hid, to show them again (the last call's)
	TArray<TWeakObjectPtr<UPrimitiveComponent>> GHiddenByMaterial;

	void AstraHideMaterial(IConsoleVariable* Var)
	{
		for (const TWeakObjectPtr<UPrimitiveComponent>& C : GHiddenByMaterial)
		{
			if (C.IsValid())
			{
				C->SetHiddenInGame(false);
			}
		}
		GHiddenByMaterial.Reset();
		const FString Part = Var ? Var->GetString() : FString();
		if (Part.IsEmpty())
		{
			return;
		}
		int32 N = 0;
		for (TObjectIterator<UPrimitiveComponent> It; It; ++It)
		{
			UPrimitiveComponent* C = *It;
			if (!C->GetWorld() || !C->GetWorld()->IsGameWorld() || C->bHiddenInGame || !C->IsRegistered())
			{
				continue;
			}
			for (int32 M = 0; M < C->GetNumMaterials(); ++M)
			{
				const UMaterialInterface* Mat = C->GetMaterial(M);
				if (Mat && (Mat->GetName().Contains(Part) || (Mat->GetMaterial() && Mat->GetMaterial()->GetName().Contains(Part))))
				{
					C->SetHiddenInGame(true);
					GHiddenByMaterial.Add(C);
					++N;
					break;
				}
			}
		}
		UE_LOG(LogASTRA, Log, TEXT("[Debug] %d components drawn with a material named like '%s' are hidden"), N, *Part);
	}

	TAutoConsoleVariable<FString> CVarHideMaterial(TEXT("astra.debug.hide_material"), TEXT(""),
		TEXT("Hide everything drawn with a material whose name (or its parent's) contains this text; empty shows it again (for measuring a material's cost)"),
		FConsoleVariableDelegate::CreateStatic(&AstraHideMaterial));

	FAutoConsoleCommandWithWorld CmdLookAt(TEXT("astra.debug.lookat"), TEXT("What the Captain looks at: the ray from the eye along the view, 50 m"),
		FConsoleCommandWithWorldDelegate::CreateLambda([](UWorld* W)
		{
			const APlayerCameraManager* Cam = UGameplayStatics::GetPlayerCameraManager(W, 0);
			if (!Cam)
			{
				return;
			}
			const FVector Eye = Cam->GetCameraLocation();
			AstraDebugRay(W, Eye, Eye + Cam->GetCameraRotation().Vector() * 5000.f, TEXT("along the view"));
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdFloors(TEXT("astra.debug.floors"),
		TEXT("The gaps in a deck's floors: astra.debug.floors <deck> [step in metres, default 1.5]. The deck is loaded first (run it again when the log says so)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* W)
		{
			const UAstraShipPlan* Plan = W ? W->GetSubsystem<UAstraShipPlan>() : nullptr;
			if (!Plan || !Plan->EnsureLoaded() || Args.Num() < 1)
			{
				UE_LOG(LogASTRA, Log, TEXT("[Floors] astra.debug.floors <deck> [step m] (needs the ship's plan)"));
				return;
			}
			const int32 Deck = FCString::Atoi(*Args[0]);
			const float Step = Args.Num() > 1 ? FMath::Max(0.3f, FCString::Atof(*Args[1])) * 100.f : 150.f;
			if (UAstraDeckStreaming* Decks = W->GetSubsystem<UAstraDeckStreaming>())
			{
				const bool bReady = Decks->IsDeckReady(Deck);
				Decks->RequestDeck(Deck, 90.f);
				if (!bReady)
				{
					UE_LOG(LogASTRA, Log, TEXT("[Floors] Deck %d is loading: run it again in a few seconds"), Deck);
					return;
				}
			}
			// the rays meet what the Captain's capsule meets: not the hull's skin and the island's blocks (ASTRACharacter::BeginPlay)
			FCollisionQueryParams Q(SCENE_QUERY_STAT(AstraFloors), false, UGameplayStatics::GetPlayerPawn(W, 0));
			for (TActorIterator<AStaticMeshActor> It(W); It; ++It)
			{
				const UStaticMeshComponent* SM = It->GetStaticMeshComponent();
				if (SM && SM->GetStaticMesh() && SM->GetStaticMesh()->GetName().StartsWith(TEXT("SM_SHIP_ASTRA_Aquila")))
				{
					Q.AddIgnoredActor(*It);
				}
			}
			// where an open floor is the room's nature: shafts, trunks with their ladder holes, tanks, the shuttle's tunnels, crawlways, stairwells
			static const TSet<FString> Open = {TEXT("lift"), TEXT("trunk"), TEXT("tank"), TEXT("tunnel"), TEXT("transit"), TEXT("crawlway"), TEXT("stairs")};
			const TArray<FAstraPlanCompartment>& Comps = Plan->GetCompartments();
			int32 Rooms = 0, Points = 0, Gaps = 0, GapRooms = 0;
			for (int32 I = 0; I < Comps.Num(); ++I)
			{
				const FAstraPlanCompartment& C = Comps[I];
				if (C.Deck != Deck || !C.bBuilt || Open.Contains(C.Kind))
				{
					continue;
				}
				++Rooms;
				const float Z = C.Box.Min.Z;
				int32 N = 0, G = 0;
				FVector2D Lo(1e9f, 1e9f), Hi(-1e9f, -1e9f);
				for (float X = C.Box.Min.X + 40.f; X <= C.Box.Max.X - 40.f; X += Step)
				{
					for (float Y = C.Box.Min.Y + 40.f; Y <= C.Box.Max.Y - 40.f; Y += Step)
					{
						if (Plan->CompartmentIndexAt(FVector(X, Y, Z + 50.f)) != I)
						{
							continue;                // another compartment's floor (a shaft, a trunk inside this one)
						}
						++N;
						FHitResult Hit;
						// from under the room's ceiling: a room's real floor can stand above the plan's lowest point (Main Engineering's deck plates
						// are 3 m over its reactor pit), and a gallery or a table over a floor is a floor too
						if (!W->LineTraceSingleByChannel(Hit, FVector(X, Y, C.Box.Max.Z - 20.f), FVector(X, Y, Z - 400.f), ECC_Pawn, Q))
						{
							++G;
							Lo = FVector2D(FMath::Min(Lo.X, X), FMath::Min(Lo.Y, Y));
							Hi = FVector2D(FMath::Max(Hi.X, X), FMath::Max(Hi.Y, Y));
						}
					}
				}
				Points += N;
				Gaps += G;
				if (G > 0)
				{
					++GapRooms;
					UE_LOG(LogASTRA, Warning, TEXT("[Floors] Deck %d %s (%s, %s): %d of %d points have nothing under the ceiling down to 4 m below the floor, in x %.1f..%.1f y %.1f..%.1f m (floor at %.2f m)"),
					       Deck, *C.Name, *C.Id, *C.Kind, G, N, Lo.X / 100.0, Hi.X / 100.0, Lo.Y / 100.0, Hi.Y / 100.0, Z / 100.0);
				}
			}
			UE_LOG(LogASTRA, Log, TEXT("[Floors] Deck %d: %d rooms, %d points every %.1f m, %d without a floor in %d rooms"), Deck, Rooms, Points, Step / 100.0, Gaps, GapRooms);
		}));
}
