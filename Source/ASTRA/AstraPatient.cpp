// ASTRA — a bed in the Medbay and its patient.

#include "AstraPatient.h"

#include "Components/PoseableMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Materials/MaterialInterface.h"

namespace
{
	UStaticMeshComponent* MakeBedProp(AAstraPatient* Owner, const TCHAR* Name, USceneComponent* Parent)
	{
		UStaticMeshComponent* C = Owner->CreateDefaultSubobject<UStaticMeshComponent>(Name);
		C->SetupAttachment(Parent);
		C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		C->SetCanEverAffectNavigation(false);
		return C;
	}
}

AAstraPatient::AAstraPatient()
{
	Posture = EAstraCrewPosture::Lying;
	PrimaryActorTick.TickInterval = 0.f;
	// the props live in the patient's frame: the backrest's hinge on the mattress, +X towards the head of the bed
	Blanket = MakeBedProp(this, TEXT("Blanket"), Body);
	Folded = MakeBedProp(this, TEXT("Folded"), Body);
	Vitals = MakeBedProp(this, TEXT("Vitals"), Body);
	Vitals->SetCastShadow(false);
}

int32 AAstraPatient::BedNumber() const
{
	return StationId.StartsWith(TEXT("patient")) ? FCString::Atoi(*StationId.Mid(7)) : 0;
}

void AAstraPatient::BeginPlay()
{
	Super::BeginPlay();
	auto Mesh = [](const TCHAR* Name) { return LoadObject<UStaticMesh>(nullptr, *FString::Printf(TEXT("/Game/ASTRA/Kit/Medbay/%s.%s"), Name, Name)); };
	Blanket->SetStaticMesh(Mesh(TEXT("SM_MED_Blanket")));
	Folded->SetStaticMesh(Mesh(TEXT("SM_MED_BlanketFolded")));
	Vitals->SetStaticMesh(Mesh(TEXT("SM_MED_Vitals")));
	SetEmpty();   // the ship fills the beds from the roster
}

void AAstraPatient::ShowOccupied(bool bIn)
{
	bOccupied = bIn;
	Seated->SetVisibility(bIn);
	Blanket->SetVisibility(bIn);
	Vitals->SetVisibility(bIn);
	Folded->SetVisibility(!bIn);
	SetActorTickEnabled(bIn);   // an empty bed has nothing to animate
}

void AAstraPatient::SetOccupant(const FString& Name, bool bFemale, uint8 Condition)
{
	DisplayName = Name;
	if (bFemale != bFemaleBody || !Seated->GetSkinnedAsset())
	{
		bFemaleBody = bFemale;
		SetBody(bFemale);
	}
	if (Condition != ShownCondition)
	{
		ShownCondition = Condition;
		// the monitor: steady green traces, or the alarms of a critical patient
		if (UMaterialInterface* M = LoadObject<UMaterialInterface>(nullptr, Condition >= 2
			? TEXT("/Game/ASTRA/Materials/Instances/MI_MED_VitalsCritical.MI_MED_VitalsCritical")
			: TEXT("/Game/ASTRA/Materials/Instances/MI_MED_Vitals.MI_MED_Vitals")))
		{
			Vitals->SetMaterial(0, M);
		}
	}
	ShowOccupied(true);
}

void AAstraPatient::SetEmpty()
{
	DisplayName.Empty();
	ShownCondition = 255;
	ShowOccupied(false);
}
