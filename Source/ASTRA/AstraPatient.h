// ASTRA — a bed in the Medbay (Deck 6) and whoever lies in it: one of the Aquila's wounded, by name, from the roster
// (UAstraShipSubsystem assigns the beds). An empty bed is made up, its blanket folded at the foot and its monitor on
// standby; an occupied one has the patient under the blanket and the monitor showing their vital signs. The patient is
// a crew member like any other: the Captain can talk to them (the mind voices them as `patient<N>`).

#pragma once

#include "CoreMinimal.h"
#include "AstraCrewMember.h"
#include "AstraPatient.generated.h"

class UStaticMeshComponent;

UCLASS()
class ASTRA_API AAstraPatient : public AAstraCrewMember
{
	GENERATED_BODY()

public:
	AAstraPatient();

	/** The bed's number on the ward (1-12): StationId is "patient<Bed>". */
	int32 BedNumber() const;

	/** Somebody is admitted to this bed (or their condition changed): Condition 0 stable, 1 serious, 2 critical. */
	void SetOccupant(const FString& Name, bool bFemale, uint8 Condition);
	void SetEmpty();
	bool IsOccupied() const { return bOccupied; }

protected:
	virtual void BeginPlay() override;

	UPROPERTY(VisibleAnywhere, Category = "ASTRA")
	TObjectPtr<UStaticMeshComponent> Blanket;

	UPROPERTY(VisibleAnywhere, Category = "ASTRA")
	TObjectPtr<UStaticMeshComponent> Folded;

	UPROPERTY(VisibleAnywhere, Category = "ASTRA")
	TObjectPtr<UStaticMeshComponent> Vitals;

private:
	bool bOccupied = true;
	uint8 ShownCondition = 255;
	void ShowOccupied(bool bIn);
};
