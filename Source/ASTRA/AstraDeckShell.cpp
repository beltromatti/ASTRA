// ASTRA — the shell of a deck (instanced modules, rooms and signs).

#include "AstraDeckShell.h"

#include "Components/InstancedStaticMeshComponent.h"
#include "Engine/CollisionProfile.h"
#include "Engine/StaticMesh.h"

AAstraDeckShell::AAstraDeckShell()
{
	PrimaryActorTick.bCanEverTick = false;
	Root = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	Root->SetMobility(EComponentMobility::Static);
	SetRootComponent(Root);
}

int32 AAstraDeckShell::AddInstancesChunked(UStaticMesh* Mesh, const TArray<FTransform>& WorldTransforms, float ChunkCm)
{
	if (!Mesh || WorldTransforms.Num() == 0)
	{
		return 0;
	}
	ChunkCm = FMath::Max(ChunkCm, 100.f);
	// one component per run of the ship along X
	TMap<int32, TArray<FTransform>> Runs;
	for (const FTransform& T : WorldTransforms)
	{
		Runs.FindOrAdd(FMath::FloorToInt(T.GetLocation().X / ChunkCm)).Add(T);
	}
	Runs.KeyStableSort([](int32 A, int32 B) { return A > B; });      // from the bow aft, like the ship's sections
	int32 Added = 0;
	for (TPair<int32, TArray<FTransform>>& Run : Runs)
	{
		const FName Name = MakeUniqueObjectName(this, UInstancedStaticMeshComponent::StaticClass(), FName(*FString::Printf(TEXT("%s_x%d"), *Mesh->GetName(), Run.Key)));
		UInstancedStaticMeshComponent* C = NewObject<UInstancedStaticMeshComponent>(this, Name, RF_Transactional);
		C->SetMobility(EComponentMobility::Static);
		C->SetupAttachment(GetRootComponent());
		C->CreationMethod = EComponentCreationMethod::Instance;      // saved with the level like a component added in the editor
		C->SetStaticMesh(Mesh);
		C->SetCollisionProfileName(UCollisionProfile::BlockAll_ProfileName);      // architecture: static, blocks everything (as a static mesh actor's default)
		C->RegisterComponent();              // (registered first: the world-space instance transforms are taken against its placed transform)
		AddInstanceComponent(C);
		C->PreAllocateInstancesMemory(Run.Value.Num());
		C->AddInstances(Run.Value, false, true, false);
		Added += Run.Value.Num();
	}
	return Added;
}

void AAstraDeckShell::ClearInstances()
{
	TArray<UInstancedStaticMeshComponent*> Comps;
	GetComponents<UInstancedStaticMeshComponent>(Comps);
	for (UInstancedStaticMeshComponent* C : Comps)
	{
		RemoveInstanceComponent(C);
		C->DestroyComponent();
	}
}

int32 AAstraDeckShell::NumInstances() const
{
	TArray<UInstancedStaticMeshComponent*> Comps;
	GetComponents<UInstancedStaticMeshComponent>(Comps);
	int32 N = 0;
	for (const UInstancedStaticMeshComponent* C : Comps)
	{
		N += C->GetInstanceCount();
	}
	return N;
}

int32 AAstraDeckShell::NumInstanceComponents() const
{
	TArray<UInstancedStaticMeshComponent*> Comps;
	GetComponents<UInstancedStaticMeshComponent>(Comps);
	return Comps.Num();
}

int64 AAstraDeckShell::CountTriangles() const
{
	TArray<UInstancedStaticMeshComponent*> Comps;
	GetComponents<UInstancedStaticMeshComponent>(Comps);
	int64 N = 0;
	for (const UInstancedStaticMeshComponent* C : Comps)
	{
		if (const UStaticMesh* M = C->GetStaticMesh())
		{
			N += (int64)M->GetNumTriangles(0) * C->GetInstanceCount();
		}
	}
	return N;
}

int32 AAstraDeckShell::NumDistinctMeshes() const
{
	TArray<UInstancedStaticMeshComponent*> Comps;
	GetComponents<UInstancedStaticMeshComponent>(Comps);
	TSet<const UStaticMesh*> Meshes;
	for (const UInstancedStaticMeshComponent* C : Comps)
	{
		Meshes.Add(C->GetStaticMesh());
	}
	return Meshes.Num();
}
