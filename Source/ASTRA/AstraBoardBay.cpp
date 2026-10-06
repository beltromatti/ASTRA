// Deck 8's real inventory of Kestrels. The sequence illustrates the same roster and launch events as the simulation;
// it never launches a second craft, alters an ETA, removes a marine or changes the boarding fight.
#include "AstraBoardSubsystem.h"
#include "AstraBattleSubsystem.h"
#include "AstraLifeSubsystem.h"
#include "ASTRAPlayerController.h"
#include "Animation/AnimSequence.h"
#include "Components/BoxComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Animation/SkeletalMeshActor.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/StaticMesh.h"
#include "Engine/SkeletalMesh.h"
#include "Materials/MaterialInterface.h"
#include "Engine/World.h"
#include "Kismet/GameplayStatics.h"
#include "Misc/App.h"

bool UAstraBoardSubsystem::TryBoardBay(APawn* Pawn, FString& OutDetail)
{
    if (!Pawn || !CaptainOnFoot()) { return false; }
    const FVector P = Pawn->GetActorLocation();
    if (FMath::Abs(P.Z + 6100.0) > 200.0 || FMath::Abs(P.Y + 2440.0) > 300.0 || FMath::Min(FMath::Abs(P.X - 4750.0), FMath::Abs(P.X - 3250.0)) > 250.0) { return false; }
    if (!Assault.bOn) { OutDetail = TEXT("Give a boarding order first; the Kestrels wait for a mission."); return true; }
    CaptainJoins(OutDetail);
    return true;
}

void UAstraBoardSubsystem::BeginBayDeparture(int32 Slot, const FLeg& Leg)
{
    if (!FApp::CanEverRender() || IsRunningCommandlet() || Slot < 0 || Slot > 1) { return; }
    BayAge[Slot] = 0.f;
    const FName Tag(*FString::Printf(TEXT("ASTRA.BayVisual.%d"), Slot));
    for (int32 i = BayBoarders.Num() - 1; i >= 0; --i)
    {
        if (!BayBoarders[i] || BayBoarders[i]->ActorHasTag(Tag)) { if (BayBoarders[i]) { BayBoarders[i]->Destroy(); } BayBoarders.RemoveAt(i); }
    }
    auto* Walk = LoadObject<UAnimSequence>(nullptr, TEXT("/Game/Characters/Mannequins/Anims/Unarmed/Walk/MF_Unarmed_Walk_Fwd.MF_Unarmed_Walk_Fwd"));
    auto* Uniform = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/ASTRA/Crew/Materials/MI_Crew_Uniform.MI_Crew_Uniform"));
    auto* Jacket = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/ASTRA/Crew/Materials/MI_Crew_Dept_Security.MI_Crew_Dept_Security"));
    for (int32 i = 0; i < FMath::Min(6, Leg.Arrivals.Num()); ++i)
    {
        bool Female = false;
        if (auto* BayLife = LifeSub()) { const int32 Person = BayLife->Sim().PersonOfRoster(Leg.Arrivals[i].Roster); if (Person != INDEX_NONE) { Female = BayLife->Sim().Person(Person).bFemale; } }
        auto* Mesh = LoadObject<USkeletalMesh>(nullptr, Female ? TEXT("/Game/Characters/Mannequins/Meshes/SKM_Quinn_Simple.SKM_Quinn_Simple") : TEXT("/Game/Characters/Mannequins/Meshes/SKM_Manny_Simple.SKM_Manny_Simple"));
        if (!Mesh) { continue; }
        FActorSpawnParameters SP; SP.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
        auto* BoardingBody = GetWorld()->SpawnActor<ASkeletalMeshActor>(ASkeletalMeshActor::StaticClass(), SP);
        if (!BoardingBody) { continue; }
        BoardingBody->Tags.Add(Tag); BoardingBody->Tags.Add(FName(*FString::FromInt(i)));
        auto* Skeletal = BoardingBody->GetSkeletalMeshComponent();
        Skeletal->SetSkeletalMesh(Mesh); Skeletal->SetCollisionEnabled(ECollisionEnabled::NoCollision);
        if (Uniform) { Skeletal->SetMaterial(0, Uniform); }
        if (Jacket && Skeletal->GetNumMaterials() > 1) { Skeletal->SetMaterial(1, Jacket); }
        if (Walk) { Skeletal->PlayAnimation(Walk, true); Skeletal->SetPlayRate(1.4f); }
        BayBoarders.Add(BoardingBody);
    }
}

void UAstraBoardSubsystem::TickBay(float Dt)
{
    if (!GetWorld() || !FApp::CanEverRender() || IsRunningCommandlet()) { return; }
    if (BayCraft.Num() == 0)
    {
        auto* DoorMesh = LoadObject<UStaticMesh>(nullptr, TEXT("/Game/ASTRA/Kit/Ship/SM_SHIP_KestrelDoor.SM_SHIP_KestrelDoor"));
        if (!DoorMesh) { return; }
        for (int32 i = 0; i < 2; ++i)
        {
            const float X = i == 0 ? 4750.f : 3250.f;
            FActorSpawnParameters SP; SP.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
            auto* Craft = GetWorld()->SpawnActor<AStaticMeshActor>(AStaticMeshActor::StaticClass(), SP);
            auto* Mesh = LoadObject<UStaticMesh>(nullptr, *FString::Printf(TEXT("/Game/ASTRA/Kit/Ship/SM_SHIP_KestrelParked%d.SM_SHIP_KestrelParked%d"), i + 1, i + 1));
            if (!Craft || !Mesh) { if (Craft) { Craft->Destroy(); } continue; }
            Craft->GetStaticMeshComponent()->SetMobility(EComponentMobility::Movable);
            Craft->GetStaticMeshComponent()->SetStaticMesh(Mesh);
            Craft->GetStaticMeshComponent()->SetCollisionProfileName(TEXT("BlockAll"));
            Craft->SetActorLocationAndRotation(FVector(X, -3140.f, -6200.f), FRotator(0.f, 270.f, 0.f));
            BayCraft.Add(Craft);
            for (int32 side = -1; side <= 1; side += 2)
            {
                auto* Leaf = GetWorld()->SpawnActor<AStaticMeshActor>(AStaticMeshActor::StaticClass(), SP);
                Leaf->GetStaticMeshComponent()->SetMobility(EComponentMobility::Movable);
                Leaf->GetStaticMeshComponent()->SetStaticMesh(DoorMesh);
                Leaf->GetStaticMeshComponent()->SetCollisionProfileName(TEXT("BlockAll"));
                Leaf->SetActorLocationAndRotation(FVector(X + side * 230.f, -3770.f, -6200.f), FRotator(0.f, 90.f, 0.f));
                BayLeaves.Add(Leaf);
            }
            // The bay's containment field always keeps a person out of the launch tube, including when the leaves open.
            auto* Field = NewObject<UBoxComponent>(Craft);
            Field->RegisterComponent(); Field->SetWorldLocation(FVector(X, -3750.f, -6025.f)); Field->SetBoxExtent(FVector(460.f, 8.f, 175.f));
            Field->SetCollisionEnabled(ECollisionEnabled::QueryOnly); Field->SetCollisionResponseToAllChannels(ECR_Ignore); Field->SetCollisionResponseToChannel(ECC_Pawn, ECR_Block);
            Craft->AddInstanceComponent(Field);
        }
    }
    auto* B = Battle();
    const auto Bay = B ? B->BoardBayOf(B->ResolveShip(TEXT("aquila"))) : AstraBoardCraft::FBay();
    const int32 Free = Bay.Total > 0 ? Bay.Free() : 2;
    for (int32 i = 0; i < BayCraft.Num(); ++i)
    {
        if (BayAge[i] >= 0.f) { BayAge[i] += Dt; }
        const float Age = BayAge[i];
        const bool TakingOff = Age >= 0.f && Age < 5.3f;
        const float X = i == 0 ? 4750.f : 3250.f;
        BayCraft[i]->SetActorHiddenInGame(!TakingOff && i >= Free);
        BayCraft[i]->GetStaticMeshComponent()->SetCollisionEnabled(!TakingOff && i < Free ? ECollisionEnabled::QueryAndPhysics : ECollisionEnabled::NoCollision);
        const float Slide = TakingOff ? FMath::Clamp((Age - 3.1f) / 2.2f, 0.f, 1.f) : 0.f;
        BayCraft[i]->SetActorLocation(FVector(X, -3140.f - 1600.f * Slide * Slide, -6200.f + FMath::Min(Slide * 40.f, 12.f)));
        const float Open = Age >= 0.f ? FMath::Clamp(FMath::Min(Age / 1.2f, (6.5f - Age) / 1.2f), 0.f, 1.f) : 0.f;
        for (int32 j = 0; j < 2; ++j)
        {
            if (BayLeaves.IsValidIndex(i * 2 + j) && BayLeaves[i * 2 + j]) { BayLeaves[i * 2 + j]->SetActorLocation(FVector(X + (j == 0 ? -1.f : 1.f) * (230.f + 470.f * Open), -3770.f, -6200.f)); }
        }
    }
    for (int32 i = BayBoarders.Num() - 1; i >= 0; --i)
    {
        auto* BoardingBody = BayBoarders[i].Get();
        const int32 Slot = BoardingBody && BoardingBody->ActorHasTag(TEXT("ASTRA.BayVisual.1")) ? 1 : 0;
        const float Age = BayAge[Slot];
        if (!BoardingBody || Age < 0.f || Age > 3.1f) { if (BoardingBody) { BoardingBody->Destroy(); } BayBoarders.RemoveAt(i); continue; }
        const int32 N = BoardingBody->Tags.Num() > 1 ? FCString::Atoi(*BoardingBody->Tags[1].ToString()) : 0;
        const float X = Slot == 0 ? 4750.f : 3250.f;
        const float A = FMath::Clamp((Age - N * 0.12f) / 2.f, 0.f, 1.f);
        const float Y = FMath::Lerp(-2420.f + (N / 2) * 70.f, -2820.f, A);
        const float RampZ = FMath::Clamp((-Y - 2380.f) / 440.f, 0.f, 1.f) * 70.f;
        BoardingBody->SetActorLocationAndRotation(FVector(X + (N % 2 ? 38.f : -38.f), Y, -6200.f + RampZ), FRotator(0.f, 180.f, 0.f));
        BoardingBody->SetActorHiddenInGame(A >= 1.f);
    }
}
