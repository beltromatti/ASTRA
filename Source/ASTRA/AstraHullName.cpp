// ASTRA — a ship's name painted on her flanks.

#include "AstraHullName.h"

#include "ASTRA.h"
#include "CanvasItem.h"
#include "Components/DecalComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/Canvas.h"
#include "Engine/CanvasRenderTarget2D.h"
#include "Engine/Font.h"
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshActor.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Misc/Crc.h"

void UAstraHullName::Paint(AActor* Ship, const FString& InName, const FString& HullCode)
{
	AStaticMeshActor* A = Cast<AStaticMeshActor>(Ship);
	UStaticMeshComponent* C = A ? A->GetStaticMeshComponent() : nullptr;
	UMaterialInterface* Mat = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/ASTRA/Materials/M_ASTRA_HullDecalRT.M_ASTRA_HullDecalRT"));
	if (!C || !C->GetStaticMesh() || !Mat)
	{
		return;
	}
	UAstraHullName* N = NewObject<UAstraHullName>(A);
	N->Name = InName.ToUpper();
	N->Code = HullCode;
	N->Target = UCanvasRenderTarget2D::CreateCanvasRenderTarget2D(A, UCanvasRenderTarget2D::StaticClass(), 2048, 512);
	if (!N->Target)
	{
		return;
	}
	N->Target->ClearColor = FLinearColor::Black;
	N->Target->OnCanvasRenderTargetUpdate.AddDynamic(N, &UAstraHullName::Draw);
	N->Target->UpdateResource();                       // drawn once, now
	// both flanks, a little forward of amidships and above the waterline of her side, projected inward
	const FBox B = C->GetStaticMesh()->GetBoundingBox();
	const FVector Size = B.GetSize();
	const float Len = FMath::Clamp(Size.X * 0.22f, 800.f, 9000.f);
	const float Height = Len / 4.f;
	for (const float Side : {-1.f, 1.f})
	{
		UMaterialInstanceDynamic* M = UMaterialInstanceDynamic::Create(Mat, A);
		M->SetTextureParameterValue(TEXT("Marking"), N->Target);
		UDecalComponent* D = NewObject<UDecalComponent>(A);
		D->SetupAttachment(C);
		D->SetDecalMaterial(M);
		D->DecalSize = FVector(Size.Y * 0.3f + 200.f, Height * 0.5f, Len * 0.5f);
		// on the main hull's side, below the superstructure: a third of the way up her height
		D->SetRelativeLocation(FVector(B.Min.X + Size.X * 0.6f, Side * (B.Max.Y + 150.f), B.Min.Z + Size.Z * 0.33f));
		D->SetRelativeRotation(FRotator(0.f, Side < 0.f ? 90.f : -90.f, 90.f));   // like the Aquila's own name
		D->SetFadeScreenSize(0.002f);
		D->RegisterComponent();
	}
}

void UAstraHullName::Draw(UCanvas* Canvas, int32 Width, int32 Height)
{
	UFont* Title = LoadObject<UFont>(nullptr, TEXT("/Game/ASTRA/UI/Fonts/F_ASTRA_Title.F_ASTRA_Title"));
	if (!Canvas || !Title)
	{
		return;
	}
	// white on black: the decal's material reads the mask from the red channel
	const FSlateFontInfo Big(Title, 190);
	const FSlateFontInfo Small(Title, 90);
	FCanvasTextItem T(FVector2D(Width * 0.5f, Height * 0.08f), FText::FromString(Name), Big, FLinearColor::White);
	T.bCentreX = true;
	T.BlendMode = SE_BLEND_Translucent;   // white text over black: the red channel is the mask
	Canvas->DrawItem(T);
	FCanvasTextItem K(FVector2D(Width * 0.5f, Height * 0.66f), FText::FromString(Code), Small, FLinearColor::White);
	K.bCentreX = true;
	K.BlendMode = SE_BLEND_Translucent;
	Canvas->DrawItem(K);
}
