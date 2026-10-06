// The Captain's real equipment: hold Q, point, release. A short tap remains quick switch.
#pragma once
#include "CoreMinimal.h"
class AASTRAPlayerController;
class SAstraEquipmentWheelWidget;
class FAstraEquipmentWheel
{
public:
    bool Open(AASTRAPlayerController* PC);
    void Tick(AASTRAPlayerController* PC, float DeltaTime);
    void Close(AASTRAPlayerController* PC, bool bExecute);
    bool IsOpen() const { return bOpen; }
private:
    bool bOpen = false;
    int32 Lit = INDEX_NONE;
    FVector2D Pointer = FVector2D::ZeroVector;
    TSharedPtr<SAstraEquipmentWheelWidget> Widget;
    void Execute(AASTRAPlayerController* PC, int32 Index);
};
