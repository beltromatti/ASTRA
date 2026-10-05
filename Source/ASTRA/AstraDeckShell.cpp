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

void AAstraDeckShell::BeginPlay()
{
	Super::BeginPlay();
	// The interior's self-check (astra.check.map, 5 Oct) found floors that flicker: lift lobbies and holds the builder had placed twice, two coplanar
	// copies of one mesh fighting over every pixel, and rooms of two meshes that overlap at a joint. The copies are dropped, and each mesh's instances
	// are lifted by up to 3 mm each (by the mesh and the instance's place), so that no two surfaces ever share a plane.
	TArray<UInstancedStaticMeshComponent*> Comps;
	GetComponents<UInstancedStaticMeshComponent>(Comps);
	TMap<const UStaticMesh*, TArray<UInstancedStaticMeshComponent*>> ByMesh;
	for (UInstancedStaticMeshComponent* C : Comps)
	{
		if (C && C->GetStaticMesh())
		{
			ByMesh.FindOrAdd(C->GetStaticMesh()).Add(C);
		}
	}
	int32 Dropped = 0, Lifted = 0;
	for (TPair<const UStaticMesh*, TArray<UInstancedStaticMeshComponent*>>& KV : ByMesh)
	{
		TSet<FString> Seen;
		const uint32 MeshHash = GetTypeHash(KV.Key->GetName());
		for (UInstancedStaticMeshComponent* C : KV.Value)
		{
			TArray<int32> Copies;
			TArray<FTransform> Moved;
			const int32 N = C->GetInstanceCount();
			Moved.Reserve(N);
			for (int32 i = 0; i < N; ++i)
			{
				FTransform T;
				C->GetInstanceTransform(i, T, true);
				const FVector L = T.GetLocation();
				const FString Key = FString::Printf(TEXT("%d,%d,%d,%d"), FMath::RoundToInt(L.X), FMath::RoundToInt(L.Y), FMath::RoundToInt(L.Z),
				                                    FMath::RoundToInt(T.Rotator().Yaw));
				bool bAlready = false;
				Seen.Add(Key, &bAlready);
				if (bAlready)
				{
					Copies.Add(i);
				}
				// (by the mesh and by the instance's own place: two neighbours of one mesh that overlap at a joint are kept apart too)
				const uint32 H = HashCombine(MeshHash, GetTypeHash(Key));
				T.AddToTranslation(FVector(0.0, 0.0, (double)(H % 97u) * 0.003));
				Moved.Add(T);
			}
			if (N > 0)
			{
				C->BatchUpdateInstancesTransforms(0, Moved, true, true, true);
				Lifted += N;
			}
			if (Copies.Num())
			{
				C->RemoveInstances(Copies);
				Dropped += Copies.Num();
			}
		}
	}
	UE_LOG(LogTemp, Log, TEXT("[DeckShell] deck %d: %d duplicate instances dropped, %d lifted apart"), Deck, Dropped, Lifted);
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
