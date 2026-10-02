// ASTRA — the lead's console tools for finding out what a place is made of, in the running game (no editor needed): what the Captain
// stands on, what he looks at. Each prints the actor, the component, the mesh and the collision of what the ray met, so a wall nobody
// expected or a floor that holds a rider in a lift shaft can be traced back to the script that placed it.
//
//   astra.debug.under      the ray down from the Captain's feet (2 m)
//   astra.debug.lookat     the ray from the eye along the view (50 m)
//   astra.debug.hide_material <part of a material's name>   everything drawn with such a material is hidden ("" shows it again): what a
//                          material costs, A/B with tools/perf_ab.py ("astra.debug.hide_material" "" MI_ASTRA_Glass)

#include "ASTRA.h"
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
}
