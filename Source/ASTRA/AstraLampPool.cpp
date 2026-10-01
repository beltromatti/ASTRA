// ASTRA — the lamp pool.

#include "AstraLampPool.h"

#include "ASTRA.h"
#include "Algo/Count.h"
#include "AstraShipPlan.h"
#include "Camera/PlayerCameraManager.h"
#include "Components/CapsuleComponent.h"
#include "Components/RectLightComponent.h"
#include "Engine/World.h"
#include "GameFramework/Actor.h"
#include "GameFramework/Character.h"
#include "HAL/IConsoleManager.h"
#include "Misc/App.h"
#include "Kismet/GameplayStatics.h"
#include "Materials/MaterialParameterCollection.h"
#include "Materials/MaterialParameterCollectionInstance.h"

DECLARE_CYCLE_STAT(TEXT("Lamp pool"), STAT_AstraLampPool, STATGROUP_Astra);

namespace
{
	TAutoConsoleVariable<int32> CVarLampMax(TEXT("astra.lamps.max"), 10, TEXT("Real lights the lamp pool burns at once (the plan's lamps near the Captain)"));
	TAutoConsoleVariable<float> CVarLampReach(TEXT("astra.lamps.reach"), 30.f, TEXT("Reach of the lamp pool around the Captain's eye (m)"));
	// the plan's lumens are rated for a dim ship; the whole ship is exposed like the bridge (EV100 6.6): tried on decks 4 and 6 on 30/9 at x6
	TAutoConsoleVariable<float> CVarLampGain(TEXT("astra.lamps.gain"), 6.f, TEXT("Multiplier on the plan's lamp lumens"));
	TAutoConsoleVariable<float> CVarLampFade(TEXT("astra.lamps.fade"), 0.35f, TEXT("Seconds a lamp takes to fade in or out when the pool is pointed at another"));
	TAutoConsoleVariable<int32> CVarLampOn(TEXT("astra.lamps"), 1, TEXT("0 turns the lamp pool off (every deck lamp dark)"));
	constexpr int32 SpareSlots = 4;      // a lamp fading out keeps its slot while the next fades in
}

// ------------------------------------------------------------------------------------------------------------------------------ the choice
void FAstraLampPicker::Pick(const UAstraShipPlan& Plan, const FVector& Eye, const FVector& Feet, int32 Max, float ReachCm, const TSet<int32>& Lit,
                            TArray<int32>& Out, int32* OutCompartment)
{
	Out.Reset();
	if (OutCompartment)
	{
		*OutCompartment = INDEX_NONE;
	}
	if (Max <= 0 || !Plan.EnsureLoaded())
	{
		return;
	}
	const TArray<FAstraPlanCompartment>& Comps = Plan.GetCompartments();
	const TArray<FAstraPlanLamp>& Lamps = Plan.GetLamps();
	const int32 Here = Plan.CompartmentIndexAt(Feet + FVector(0.f, 0.f, 60.f));
	if (OutCompartment)
	{
		*OutCompartment = Here;
	}
	// the compartments he can see into, with how many doors are between (0: his own and the corridors open to it; 1: a room behind a door he is at)
	const double Far2 = FMath::Square((double)ReachCm + 100.0);
	auto IsNear = [&](int32 C) { return Comps[C].Box.ComputeSquaredDistanceToPoint(Eye) < Far2; };
	TMap<int32, int32> Doors;
	TArray<int32> Open;
	if (Here != INDEX_NONE)
	{
		Doors.Add(Here, 0);
		Open.Add(Here);
	}
	else
	{
		// outside every compartment of the plan (a piece of a hall the plan does not know): the built compartments around, on this deck and the next
		for (int32 i = 0; i < Comps.Num(); ++i)
		{
			if (Comps[i].bBuilt && Comps[i].NumLamps > 0 && IsNear(i) && FMath::Abs(Comps[i].Box.GetCenter().Z - Eye.Z) < 500.0)
			{
				Doors.Add(i, 0);
			}
		}
	}
	for (int32 k = 0; k < Open.Num(); ++k)
	{
		const int32 U = Open[k];
		const int32 UDoors = Doors[U];
		for (const FAstraPlanLink& L : Plan.CompLinks(U))
		{
			if (Doors.Contains(L.Comp) || !Comps[L.Comp].bBuilt || !IsNear(L.Comp))
			{
				continue;
			}
			if (L.bDoor && (UDoors >= 1 || FVector::DistSquared(Eye, L.DoorCm) > FMath::Square(DoorSeeCm)))
			{
				continue;           // the room behind a closed door is dark until he is at it; the room behind that one never
			}
			Doors.Add(L.Comp, UDoors + (L.bDoor ? 1 : 0));
			Open.Add(L.Comp);
		}
	}
	// the lamps: nearest first, a door on the way counts as a few metres, his own room a few metres less; those already burning hold their place
	struct FCand { float Score; int32 Lamp; };
	TArray<FCand> Cands;
	const double Reach2 = FMath::Square((double)ReachCm);
	const FName HerePassage = Here != INDEX_NONE ? Comps[Here].Passage : NAME_None;
	for (const TPair<int32, int32>& KV : Doors)
	{
		const FAstraPlanCompartment& C = Comps[KV.Key];
		// a corridor of another run (the cross link and the passage beside the Spine) is seen only at its mouth: its lamps count as farther
		const float Corner = (HerePassage != NAME_None && C.Passage != NAME_None && C.Passage != HerePassage) ? 8.f : 0.f;
		for (int32 l = C.FirstLamp; l < C.FirstLamp + C.NumLamps; ++l)
		{
			const FAstraPlanLamp& Lamp = Lamps[l];
			const double D2 = FVector::DistSquared(Eye, Lamp.Pos);
			if (D2 > Reach2 || FMath::Abs(Lamp.Pos.Z - Eye.Z) > 600.0)
			{
				continue;
			}
			float Score = (float)(FMath::Sqrt(D2) / 100.0) + 4.f * KV.Value + Corner - (KV.Key == Here ? 3.f : 0.f);
			if (Lit.Contains(l))
			{
				Score *= 0.75f;
			}
			Cands.Add({Score, l});
		}
	}
	Cands.Sort([](const FCand& A, const FCand& B) { return A.Score < B.Score; });
	for (int32 i = 0; i < FMath::Min(Max, Cands.Num()); ++i)
	{
		Out.Add(Cands[i].Lamp);
	}
}

// ------------------------------------------------------------------------------------------------------------------------------ the pool
bool UAstraLampPool::ShouldCreateSubsystem(UObject* Outer) const
{
	const UWorld* World = Cast<UWorld>(Outer);
	// (a headless bench has no scene to put lights in)
	return World && (World->WorldType == EWorldType::Game || World->WorldType == EWorldType::PIE) && FApp::CanEverRender();
}

void UAstraLampPool::OnWorldBeginPlay(UWorld& InWorld)
{
	Super::OnWorldBeginPlay(InWorld);
	const UAstraShipPlan* Plan = InWorld.GetSubsystem<UAstraShipPlan>();
	if (!Plan || !Plan->EnsureLoaded() || Plan->GetLamps().Num() == 0)
	{
		UE_LOG(LogASTRA, Log, TEXT("[Lamps] no lamps in the plan: nothing to pool"));
		return;
	}
	FActorSpawnParameters SP;
	SP.ObjectFlags |= RF_Transient;
	SP.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	PoolActor = InWorld.SpawnActor<AActor>(AActor::StaticClass(), FTransform::Identity, SP);
	if (!PoolActor)
	{
		return;
	}
#if WITH_EDITOR
	PoolActor->SetActorLabel(TEXT("AstraLampPool"));
#endif
	USceneComponent* Root = NewObject<USceneComponent>(PoolActor, TEXT("Root"));
	PoolActor->SetRootComponent(Root);
	Root->RegisterComponent();
	const int32 N = FMath::Clamp(CVarLampMax.GetValueOnGameThread(), 1, 40) + SpareSlots;
	for (int32 i = 0; i < N; ++i)
	{
		URectLightComponent* L = NewObject<URectLightComponent>(PoolActor, *FString::Printf(TEXT("Lamp%02d"), i));
		L->SetMobility(EComponentMobility::Movable);
		L->IntensityUnits = ELightUnits::Lumens;
		L->bUseTemperature = true;
		L->SetCastShadows(false);
		L->SetIntensity(0.f);
		L->AttachToComponent(Root, FAttachmentTransformRules::KeepRelativeTransform);
		L->RegisterComponent();
		L->SetVisibility(false);
		FSlot S;
		S.Light = L;
		Slots.Add(S);
	}
	ShipMPC = LoadObject<UMaterialParameterCollection>(nullptr, TEXT("/Game/ASTRA/Materials/MPC_ASTRA_Ship.MPC_ASTRA_Ship"));
	UE_LOG(LogASTRA, Log, TEXT("[Lamps] %d lamps of %d built compartments in the plan, a pool of %d lights"), Plan->GetLamps().Num(),
	       Algo::CountIf(Plan->GetCompartments(), [](const FAstraPlanCompartment& C) { return C.NumLamps > 0; }), N);
	Reselect();
}

void UAstraLampPool::Deinitialize()
{
	if (PoolActor)
	{
		PoolActor->Destroy();
		PoolActor = nullptr;
	}
	Slots.Reset();
	Super::Deinitialize();
}

bool UAstraLampPool::CaptainView(FVector& OutEye, FVector& OutFeet) const
{
	if (bTest)
	{
		OutEye = TestEye;
		OutFeet = TestFeet;
		return true;
	}
	// only the Captain on foot is among the decks' lamps
	const ACharacter* C = Cast<ACharacter>(UGameplayStatics::GetPlayerPawn(this, 0));
	const APlayerCameraManager* Cam = UGameplayStatics::GetPlayerCameraManager(this, 0);
	if (!C || !Cam)
	{
		return false;
	}
	OutEye = Cam->GetCameraLocation();
	OutFeet = C->GetActorLocation() - FVector(0.f, 0.f, C->GetCapsuleComponent()->GetScaledCapsuleHalfHeight());
	return true;
}

void UAstraLampPool::ReadShipState()
{
	// the ship's light level (blackout, the rails' sag) and the red alert's tint live in its material collection: the pool follows them as the ship's other
	// lights do (AstraShipSubsystem)
	if (UMaterialParameterCollection* M = ShipMPC.Get())
	{
		if (const UMaterialParameterCollectionInstance* I = GetWorld()->GetParameterCollectionInstance(M))
		{
			float V = 0.f;
			if (I->GetScalarParameterValue(TEXT("LightLevel"), V))
			{
				LightLevel = V;
			}
			if (I->GetScalarParameterValue(TEXT("AlertPulse"), V))
			{
				AlertBlend = V;
			}
		}
	}
}

void UAstraLampPool::Assign(FSlot& S, int32 LampIndex)
{
	const UAstraShipPlan* Plan = GetWorld()->GetSubsystem<UAstraShipPlan>();
	URectLightComponent* L = S.Light.Get();
	if (!Plan || !L)
	{
		return;
	}
	const FAstraPlanLamp& Lamp = Plan->GetLamps()[LampIndex];
	// the lamp faces down with its width along the ship (the way the old zone lights were placed)
	static const FRotator Down = FRotationMatrix::MakeFromXY(FVector(0.f, 0.f, -1.f), FVector(1.f, 0.f, 0.f)).Rotator();
	L->SetWorldLocationAndRotation(Lamp.Pos, Down);
	L->SetSourceWidth(FMath::Max(Lamp.bRect ? (float)Lamp.SizeCm.X : 25.f, 5.f));
	L->SetSourceHeight(FMath::Max(Lamp.bRect ? (float)Lamp.SizeCm.Y : 25.f, 5.f));
	L->SetAttenuationRadius(Lamp.RadiusCm);
	L->SetTemperature(Lamp.TempK);
	S.Lamp = LampIndex;
	S.Level = 0.f;
	S.Target = 1.f;
	S.Applied = -1.f;
}

void UAstraLampPool::Apply(FSlot& S, bool bTint)
{
	URectLightComponent* L = S.Light.Get();
	const UAstraShipPlan* Plan = GetWorld()->GetSubsystem<UAstraShipPlan>();
	if (!L || !Plan)
	{
		return;
	}
	const bool bOn = S.Lamp != INDEX_NONE && S.Level > 0.003f;
	if (L->IsVisible() != bOn)
	{
		L->SetVisibility(bOn);
	}
	if (!bOn)
	{
		S.Applied = -1.f;
		return;
	}
	const FAstraPlanLamp& Lamp = Plan->GetLamps()[S.Lamp];
	const float I = Lamp.Lumens * CVarLampGain.GetValueOnGameThread() * S.Level * LightLevel;
	if (S.Applied < 0.f || bTint)
	{
		L->SetLightColor(FMath::Lerp(FLinearColor::White, FLinearColor(1.f, 0.55f, 0.5f), AlertBlend * 0.35f));
	}
	if (S.Applied < 0.f || FMath::Abs(I - S.Applied) > 1.f)
	{
		L->SetIntensity(I);
		S.Applied = I;
	}
}

void UAstraLampPool::Reselect()
{
	ReadShipState();
	const UAstraShipPlan* Plan = GetWorld() ? GetWorld()->GetSubsystem<UAstraShipPlan>() : nullptr;
	if (!Plan || Slots.Num() == 0)
	{
		return;
	}
	const int32 Max = FMath::Clamp(CVarLampMax.GetValueOnGameThread(), 1, Slots.Num() - SpareSlots);
	FVector Eye, Feet;
	TArray<int32> Want;
	TSet<int32> Lit;
	for (const FSlot& S : Slots)
	{
		if (S.Lamp != INDEX_NONE && S.Target > 0.f)
		{
			Lit.Add(S.Lamp);
		}
	}
	if (CVarLampOn.GetValueOnGameThread() != 0 && CaptainView(Eye, Feet))
	{
		FAstraLampPicker::Pick(*Plan, Eye, Feet, Max, FMath::Max(1.f, CVarLampReach.GetValueOnGameThread()) * 100.f, Lit, Want);
	}
	const TSet<int32> WantSet(Want);
	for (FSlot& S : Slots)
	{
		if (S.Lamp != INDEX_NONE && S.Target > 0.f && !WantSet.Contains(S.Lamp))
		{
			S.Target = 0.f;                                      // fades out, then the slot is free
		}
		else if (S.Lamp != INDEX_NONE && S.Target <= 0.f && WantSet.Contains(S.Lamp))
		{
			S.Target = 1.f;                                      // wanted again while it was fading out
			Lit.Add(S.Lamp);
		}
	}
	for (const int32 LampIndex : Want)
	{
		if (Lit.Contains(LampIndex))
		{
			continue;
		}
		FSlot* Free = Slots.FindByPredicate([](const FSlot& S) { return S.Lamp == INDEX_NONE; });
		if (!Free)
		{
			break;                                               // all slots busy fading: the next pass gets it
		}
		Assign(*Free, LampIndex);
		Lit.Add(LampIndex);
	}
	const bool bTint = FMath::Abs(AlertBlend - AppliedAlert) > 0.005f;     // the ship's level or alert may have changed
	AppliedAlert = AlertBlend;
	for (FSlot& S : Slots)
	{
		Apply(S, bTint);
	}
}

void UAstraLampPool::Tick(float DeltaTime)
{
	SCOPE_CYCLE_COUNTER(STAT_AstraLampPool);
	if (Slots.Num() == 0)
	{
		return;
	}
	Accum += DeltaTime;
	if (Accum >= 0.2f)
	{
		Accum = 0.f;
		Reselect();
	}
	Advance(DeltaTime);
}

void UAstraLampPool::Advance(float Seconds)
{
	const float Rate = 1.f / FMath::Max(0.02f, CVarLampFade.GetValueOnGameThread());
	for (FSlot& S : Slots)
	{
		if (S.Lamp == INDEX_NONE)
		{
			continue;
		}
		if (S.Level != S.Target)
		{
			S.Level = FMath::FInterpConstantTo(S.Level, S.Target, Seconds, Rate);
			Apply(S, false);
		}
		if (S.Target <= 0.f && S.Level <= 0.003f)
		{
			S.Lamp = INDEX_NONE;
			S.Level = 0.f;
			Apply(S, false);
		}
	}
}

int32 UAstraLampPool::NumLit() const
{
	int32 N = 0;
	for (const FSlot& S : Slots)
	{
		N += S.Lamp != INDEX_NONE ? 1 : 0;
	}
	return N;
}

TArray<int32> UAstraLampPool::LitLamps() const
{
	TArray<int32> Out;
	for (const FSlot& S : Slots)
	{
		if (S.Lamp != INDEX_NONE && S.Target > 0.f)
		{
			Out.Add(S.Lamp);
		}
	}
	return Out;
}

FString UAstraLampPool::Describe() const
{
	const UAstraShipPlan* Plan = GetWorld() ? GetWorld()->GetSubsystem<UAstraShipPlan>() : nullptr;
	FString Out = FString::Printf(TEXT("%d lamps in the plan, pool of %d, %d burning (gain x%.1f, light level %.2f, alert %.2f)\n"), Plan ? Plan->GetLamps().Num() : 0,
	                              Slots.Num(), NumLit(), CVarLampGain.GetValueOnGameThread(), LightLevel, AlertBlend);
	for (const FSlot& S : Slots)
	{
		if (S.Lamp != INDEX_NONE && Plan)
		{
			const FAstraPlanLamp& L = Plan->GetLamps()[S.Lamp];
			const FAstraPlanCompartment& C = Plan->GetCompartments()[L.Comp];
			Out += FString::Printf(TEXT("  %-28s %.0f lm  level %.2f -> %.0f\n"), *C.Id, L.Lumens, S.Level, S.Target);
		}
	}
	return Out;
}

namespace
{
	FAutoConsoleCommandWithWorld CmdLamps(TEXT("astra.lamps.info"), TEXT("The lamp pool: lamps in the plan, which burn now"),
		FConsoleCommandWithWorldDelegate::CreateLambda([](UWorld* World)
		{
			if (const UAstraLampPool* P = World ? World->GetSubsystem<UAstraLampPool>() : nullptr)
			{
				UE_LOG(LogASTRA, Log, TEXT("[Lamps] %s"), *P->Describe());
			}
		}));
}
