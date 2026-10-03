// ASTRA — the war's ships and craft drawn as instances: the craft's hulls (one instanced component per kind of hull, stable slots) and every ship's
// lamps (one layer of the war's glow). How and why: AstraWarDraw.h, docs/SCALA.md.

#include "AstraWarDraw.h"
#include "AstraBattleSubsystem.h"
#include "ASTRA.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Components/SceneComponent.h"
#include "Dom/JsonObject.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "HAL/PlatformTime.h"
#include "Materials/MaterialInterface.h"

using namespace AstraDraw;

namespace
{
	TAutoConsoleVariable<int32> CVarWarDraw(TEXT("astra.war.draw"), 1,
		TEXT("The war's craft and lamps as instances (1), or as actors with their own running-light components (0: the old way; ships already in the sky keep the way they were made)"));
	TAutoConsoleVariable<float> CVarWarDrawHullKm(TEXT("astra.war.draw.hull_km"), 80.f, TEXT("A craft's hull is drawn out to this range from the Aquila (km); beyond, only its glow"));
	TAutoConsoleVariable<float> CVarWarLamps(TEXT("astra.war.lamps"), 1.f, TEXT("Strength of the instanced running lights (0 none)"));
	TAutoConsoleVariable<float> CVarWarLampsCraftKm(TEXT("astra.war.lamps.craft_km"), 30.f, TEXT("A craft's strobe fades out by this range (km); its steady lights by half of it"));

	const FTransform& DrawHiddenXf()
	{
		static const FTransform X(FQuat::Identity, FVector::ZeroVector, FVector(0.0001));
		return X;
	}

	uint32 DrawMix(uint32 A)
	{
		A ^= A >> 16; A *= 0x7FEB352Du; A ^= A >> 15; A *= 0x846CA68Bu; A ^= A >> 16;
		return A;
	}

}

// An instanced component for the war's drawing, set up like the effects' layers (no shadow, no collision, no culling by distance: it holds hundreds of things over tens of kilometres).
UInstancedStaticMeshComponent* AstraDraw::MakeComp(AActor* Owner, USceneComponent* Parent, const TCHAR* Name, UStaticMesh* Mesh, UMaterialInterface* Mat, int32 Capacity,
                                                   int32 NumData, bool bMotionVectors, bool bLit)
{
	UInstancedStaticMeshComponent* C = NewObject<UInstancedStaticMeshComponent>(Owner, Name);
	C->SetupAttachment(Parent);
	C->SetMobility(EComponentMobility::Movable);
	C->SetStaticMesh(Mesh);
	if (Mat)
	{
		C->SetMaterial(0, Mat);
	}
	C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	C->bDisableCollision = true;
	C->SetCanEverAffectNavigation(false);
	C->SetGenerateOverlapEvents(false);
	C->SetCastShadow(false);                        // km-scale shadows are invisible and cost VSM pages
	C->bCastDynamicShadow = false;
	C->bAffectDynamicIndirectLighting = false;
	C->bAffectDistanceFieldLighting = false;
	C->bNeverDistanceCull = true;
	C->bUseAsOccluder = false;
	C->SetReceivesDecals(false);
	if (bLit)
	{
		C->SetLightingChannels(true, true, false);  // outside the hull: the star's light and the planet's, like the ships
	}
	C->SetNumCustomDataFloats(NumData);
	if (bMotionVectors)
	{
		C->SetHasPerInstancePrevTransforms(true);   // a hull that moves is given where it was, so that the temporal upscaler sees its motion (the engine has no way to know)
	}
	TArray<FTransform> Init;
	Init.Init(DrawHiddenXf(), Capacity);
	C->AddInstances(Init, false, false, false);
	C->RegisterComponent();
	return C;
}

// ------------------------------------------------------------------------------------------------------------------ setup
bool UAstraWarDraw::LoadAssets()
{
	SphereMesh = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Sphere.Sphere"));
	MatGlow = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/ASTRA/Materials/M_WAR_Glow.M_WAR_Glow"));
	if (!SphereMesh || !MatGlow)
	{
		UE_LOG(LogASTRA, Warning, TEXT("[WarDraw] M_WAR_Glow missing (tools/ue_scripts/make_war_fx.py): the craft and the lamps stay actors"));
	}
	return SphereMesh && MatGlow;
}

void UAstraWarDraw::Init(UAstraBattleSubsystem* InOwner)
{
	Owner = InOwner;
	UWorld* World = Owner ? Owner->GetWorld() : nullptr;
	if (!World || bInitDone)
	{
		return;
	}
	bInitDone = true;
	Lamps.Init(0);
	if (!FApp::CanEverRender())
	{
		// the bench: the same staging, nothing drawn (its cost is part of the war's)
		bSim = true;
		Lamps.Init(CapLamps);
		return;
	}
	if (!LoadAssets())
	{
		return;
	}
	FActorSpawnParameters P;
	P.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	P.ObjectFlags |= RF_Transient;
	Host = World->SpawnActor<AActor>(AActor::StaticClass(), FTransform::Identity, P);
	if (!Host)
	{
		return;
	}
	USceneComponent* Root = NewObject<USceneComponent>(Host, TEXT("DrawRoot"));
	Host->SetRootComponent(Root);
	Root->SetMobility(EComponentMobility::Movable);
	Root->RegisterComponent();
	Host->Tags.Add(TEXT("ASTRA.Sky"));                  // the main viewscreen's camera shows what is out there: tagged like the sky
	Lamps.Init(CapLamps);
	Lamps.NumData = AstraFx::Stride;
	if (UInstancedStaticMeshComponent* C = MakeComp(Host, Host->GetRootComponent(), TEXT("DrawLamps"), SphereMesh, MatGlow, CapLamps, AstraFx::Stride, false, true))
	{
		C->SetTranslucentSortPriority(4);
		Lamps.Comp = C;
	}
	bLive = true;
	UE_LOG(LogASTRA, Log, TEXT("[WarDraw] instanced drawing ready: craft hulls in pages of %d, %d lamps"), PageSize, CapLamps);
}

bool UAstraWarDraw::IsActive() const
{
	return (bLive || bSim) && CVarWarDraw.GetValueOnGameThread() != 0;
}

void UAstraWarDraw::Prewarm()
{
	if (!IsActive())
	{
		return;
	}
	for (const TCHAR* M : {TEXT("SM_CRAFT_ASTRA_Falcon"), TEXT("SM_CRAFT_ASTRA_Hammer"), TEXT("SM_CRAFT_ASTRA_Wasp"), TEXT("SM_CRAFT_MANDATE_Harpy"), TEXT("SM_CRAFT_MANDATE_Skiff"), TEXT("SM_CRAFT_ASTRA_Kestrel")})
	{
		KindFor(M);
	}
}

int32 UAstraWarDraw::KindFor(const FString& Mesh)
{
	if (const int32* K = KindByMesh.Find(Mesh))
	{
		return Kinds[*K].bFailed ? -1 : *K;
	}
	const int32 Idx = Kinds.AddDefaulted();
	Kinds[Idx].Mesh = Mesh;
	KindByMesh.Add(Mesh, Idx);
	if (bLive)
	{
		UStaticMesh* M = LoadObject<UStaticMesh>(nullptr, *FString::Printf(TEXT("/Game/ASTRA/Ships/%s.%s"), *Mesh, *Mesh), nullptr, LOAD_Quiet | LOAD_NoWarn);
		if (!M)
		{
			Kinds[Idx].bFailed = true;                  // its craft are drawn the old way
			UE_LOG(LogASTRA, Warning, TEXT("[WarDraw] no mesh %s: its craft stay actors"), *Mesh);
			return -1;
		}
		// the hull's materials must be flagged "Used with Instanced Static Meshes": the engine cannot set the flag in a game (only in an editor that is not playing), and a Nanite
		// instance whose material is not flagged is drawn with the default material (NaniteResources.cpp); better actors than grey craft
		FString Unflagged;
		for (const FStaticMaterial& SM : M->GetStaticMaterials())
		{
			if (SM.MaterialInterface && !SM.MaterialInterface->GetUsageByFlag(MATUSAGE_InstancedStaticMeshes))
			{
				Unflagged += SM.MaterialInterface->GetName() + TEXT(" ");
			}
		}
		if (!Unflagged.IsEmpty())
		{
			Kinds[Idx].bFailed = true;
			UE_LOG(LogASTRA, Warning, TEXT("[WarDraw] %s: its materials (%s) are not flagged 'Used with Instanced Static Meshes', so its craft stay actors; run tools/ue_scripts/make_scala_materials.py in the editor, once"),
			       *Mesh, *Unflagged.TrimEnd());
			return -1;
		}
		Kinds[Idx].StaticMesh = M;
		Meshes.Add(M);
		MakePage(Idx, 0);                               // the first page of the main set, ready before the first craft needs it
	}
	return Idx;
}

FPage* UAstraWarDraw::MakePage(int32 KindIdx, int32 SetIdx)
{
	FKind& Kd = Kinds[KindIdx];
	FPage& P = Kd.Sets[SetIdx].Pages.AddDefaulted_GetRef();
	P.Xf.Init(DrawHiddenXf(), PageSize);
	P.PrevXf.Init(DrawHiddenXf(), PageSize);
	P.Owner.Init(-1, PageSize);
	if (bLive && Kd.StaticMesh && Host)
	{
		const FString Name = FString::Printf(TEXT("Draw_%s_%d_%d"), *Kd.Mesh, SetIdx, Kd.Sets[SetIdx].Pages.Num());
		P.Comp = MakeComp(Host, Host->GetRootComponent(), *Name, Kd.StaticMesh, nullptr, PageSize, 0, true, true);
	}
	return &P;
}

int32 UAstraWarDraw::LampSetFor(const FAstraBattleShip& S)
{
	const bool bMandate = S.Side == EAstraSide::Mandate;
	const FString Key = S.Mesh + (bMandate ? TEXT("|M") : TEXT("|A"));
	if (const int32* I = LampSetByKey.Find(Key))
	{
		return *I;
	}
	TArray<FAstraNavLamp> Set;
	UAstraNavLights::LampsFor(S.Mesh, bMandate, false, Set);
	const int32 Idx = Set.Num() ? LampSets.Add(MoveTemp(Set)) : -1;
	LampSetByKey.Add(Key, Idx);
	return Idx;
}

bool UAstraWarDraw::Claim(FAstraBattleShip& S)
{
	S.DrawKind = -1;
	S.bDrawLamps = false;
	if (!IsActive() || S.bPlayer || S.bGhost || S.Mesh.IsEmpty())
	{
		return false;
	}
	if (S.bCraft && !S.bPiloted)
	{
		const int32 K = KindFor(S.Mesh);
		if (K >= 0)
		{
			S.DrawKind = (int16)K;
		}
	}
	if (S.DrawKind >= 0 || !S.bCraft)                   // a craft left to the actor path makes its own lamps
	{
		const int32 L = LampSetFor(S);
		if (L >= 0)
		{
			S.LampSet = (int16)L;
			S.bDrawLamps = true;
		}
	}
	return S.DrawKind >= 0;
}

// ------------------------------------------------------------------------------------------------------------------ slots
bool UAstraWarDraw::Alloc(int32 KindIdx, int32 SetIdx, int32 ShipId, FRef& OutRef)
{
	FSet& St = Kinds[KindIdx].Sets[SetIdx];
	const int32 Slot = St.FreeSlots.Num() ? St.FreeSlots.Pop(EAllowShrinking::No) : St.NextSlot++;
	const int32 PageI = Slot / PageSize;
	while (Kinds[KindIdx].Sets[SetIdx].Pages.Num() <= PageI)
	{
		MakePage(KindIdx, SetIdx);
	}
	FPage& P = Kinds[KindIdx].Sets[SetIdx].Pages[PageI];
	const int32 L = Slot % PageSize;
	P.Owner[L] = ShipId;
	++P.Live;
	P.High = FMath::Max(P.High, L + 1);
	FSet& St2 = Kinds[KindIdx].Sets[SetIdx];
	++St2.Live;
	St2.Peak = FMath::Max(St2.Peak, St2.Live);
	OutRef.Kind = (int16)KindIdx;
	OutRef.Set = (uint8)SetIdx;
	OutRef.Slot = Slot;
	return true;
}

void UAstraWarDraw::Release(const FRef& R)
{
	if (R.Kind < 0 || !Kinds.IsValidIndex(R.Kind))
	{
		return;
	}
	FSet& St = Kinds[R.Kind].Sets[R.Set];
	FPage& P = St.Pages[R.Slot / PageSize];
	const int32 L = R.Slot % PageSize;
	P.Xf[L] = DrawHiddenXf();
	P.PrevXf[L] = DrawHiddenXf();
	P.Owner[L] = -1;
	--P.Live;
	--St.Live;
	St.FreeSlots.Add(R.Slot);
}

void UAstraWarDraw::StageHull(FAstraBattleShip& S, double Dist2)
{
	FRef* R = Where.Find(S.Id);
	if (Dist2 > HullKm2 * 1.0e6)
	{
		return;                                         // too far to be more than a speck: its glow stays, its hull is let go (Sweep)
	}
	const bool bNear = bLens && S.Side == EAstraSide::Astra && S.Id != LensExempt && Dist2 < FMath::Square(LensKm * 1000.0);
	const int32 SetIdx = bNear ? 1 : 0;
	if (R && R->Set != SetIdx)
	{
		Release(*R);                                    // it crossed the lens range: it changes component (once)
		Where.Remove(S.Id);
		R = nullptr;
	}
	const bool bFresh = R == nullptr;
	if (!R)
	{
		FRef N;
		Alloc(S.DrawKind, SetIdx, S.Id, N);
		R = &Where.Add(S.Id, N);
	}
	R->Frame = Frame;
	FPage& P = Kinds[R->Kind].Sets[R->Set].Pages[R->Slot / PageSize];
	const int32 L = R->Slot % PageSize;
	const FTransform Now(F.ToWorldRot(S.Att), F.ToWorld(S.Pos), FVector::OneVector);
	P.PrevXf[L] = bFresh ? Now : P.Xf[L];                 // (a craft that has just appeared has no past: it is not smeared across the sky from where its slot was last)
	P.Xf[L] = Now;
	++Hulls;
	NearNow += SetIdx;
}

void UAstraWarDraw::StageLamps(const FAstraBattleShip& S, double Dist2)
{
	if (S.bDisabled || S.bDerelict || LampGain <= 0.f || !LampSets.IsValidIndex(S.LampSet))
	{
		return;
	}
	const double DKm = FMath::Sqrt(Dist2) * 0.001;
	if (DKm > 250.0)
	{
		return;
	}
	const TArray<FAstraNavLamp>& Set = LampSets[S.LampSet];
	const uint32 H = DrawMix((uint32)S.Id);
	for (int32 i = 0; i < Set.Num(); ++i)
	{
		const FAstraNavLamp& L = Set[i];
		float Fade;
		if (S.bCraft)
		{
			// a craft's lamps thin out with the distance, the steady ones first and the strobe last; no band is a jump
			const double Hi = L.Pattern == 1 ? CraftLampKm : CraftLampKm * 0.5;
			const double Lo = Hi * (L.Pattern == 1 ? 0.6 : 0.5);
			Fade = 1.f - AstraFx::Ease((float)((DKm - Lo) / FMath::Max(Hi - Lo, 0.1)));
		}
		else
		{
			Fade = 1.f - AstraFx::Ease((float)((DKm - 180.0) / 70.0));
		}
		if (Fade <= 0.01f)
		{
			continue;
		}
		const float Phase = (float)((H >> ((i * 5) & 31)) & 31u) / 31.f * 2.2f;       // no two ships blink together
		const float Inten = L.Glow * UAstraNavLights::PatternOn(L.Pattern, Clock, Phase) * LampGain * Fade;
		if (Inten < 1.f)
		{
			continue;                                   // the dark part of a strobe: no instance at all
		}
		FTransform* X;
		float* D = Lamps.Next(X);
		if (!D)
		{
			++LampsDropped;
			continue;
		}
		const FVector P = S.Pos + S.Att.RotateVector(L.Local * 0.01);                  // (the table is in cm)
		const float Rm = L.SizeM * 0.5f * AstraFx::GlowK;                                // the sphere is drawn larger than the glow it stands for
		*X = FTransform(FQuat::Identity, F.ToWorld(P), FVector(Rm * 2.f));
		AstraFx::Fill(D, L.Color, Inten, 0.f, 0.f, 0.f, (float)((H >> 3) & 255u) / 255.f, Rm * 2.f, 0.f);
	}
}

void UAstraWarDraw::Sweep()
{
	for (auto It = Where.CreateIterator(); It; ++It)
	{
		if (It.Value().Frame != Frame)
		{
			Release(It.Value());                        // dead, landed, gone out of range: the instance goes (hidden)
			It.RemoveCurrent();
		}
	}
}

void UAstraWarDraw::Flush()
{
	for (FKind& Kd : Kinds)
	{
		for (FSet& St : Kd.Sets)
		{
			for (FPage& P : St.Pages)
			{
				if (P.Live == 0 && !P.bWritten)
				{
					continue;                           // empty and already written hidden: nothing to send
				}
				if (UInstancedStaticMeshComponent* C = P.Comp.Get())
				{
					if (P.High > 0)
					{
						C->BatchUpdateInstancesTransforms(0, P.Xf, P.PrevXf, false, false, false);   // (the page whole: the two lists must match in length)
					}
				}
				P.bWritten = P.Live > 0;
				if (P.Live == 0)
				{
					P.High = 0;
				}
			}
		}
	}
	Lamps.Flush();
}

void UAstraWarDraw::HideAll()
{
	Where.Reset();
	for (FKind& Kd : Kinds)
	{
		for (FSet& St : Kd.Sets)
		{
			St.FreeSlots.Reset();
			St.NextSlot = 0;
			St.Live = 0;
			for (FPage& P : St.Pages)
			{
				for (FTransform& X : P.Xf)
				{
					X = DrawHiddenXf();
				}
				for (FTransform& X : P.PrevXf)
				{
					X = DrawHiddenXf();
				}
				for (int32& O : P.Owner)
				{
					O = -1;
				}
				P.Live = 0;
				P.bWritten = P.High > 0;                // one more write, all hidden
			}
		}
	}
	Lamps.Begin();
}

void UAstraWarDraw::ClearAll()
{
	HideAll();
	Flush();
}

// ------------------------------------------------------------------------------------------------------------------ a frame
void UAstraWarDraw::Tick(float InDt)
{
	if (!(bLive || bSim) || !Owner || Owner->Ships.Num() == 0)
	{
		return;                                             // (astra.war.draw 0 only stops new claims: what is already in the sky goes on being moved)
	}
	const double T0 = FPlatformTime::Seconds();
	Dt = FMath::Clamp(InDt, 0.f, 0.1f);
	Clock += Dt;
	++Frame;
	const FAstraBattleShip& A = Owner->Ships[0];
	F.Origin = A.bAlive ? A.Pos : FVector::ZeroVector;      // (a bench scenario parks the Aquila far away: what is measured is round the origin)
	F.InvAtt = A.Att.Inverse();
	F.Bridge = Owner->BridgeOffset;
	float Fx = 1.f;
	if (const TConsoleVariableData<float>* V = IConsoleManager::Get().FindTConsoleVariableDataFloat(TEXT("astra.fx.intensity")))
	{
		Fx = FMath::Clamp(V->GetValueOnGameThread(), 0.1f, 6.f);       // the effects' own brightness: the lamps follow the exposure the lead sets for them
	}
	LampGain = FMath::Max(0.f, CVarWarLamps.GetValueOnGameThread()) * Fx;
	HullKm2 = FMath::Square((double)FMath::Max(1.f, CVarWarDrawHullKm.GetValueOnGameThread()));
	CraftLampKm = FMath::Max(2.f, CVarWarLampsCraftKm.GetValueOnGameThread());
	Lamps.Begin();
	Hulls = 0;
	NearNow = 0;
	int32 Actors = 0, Comps = 0;
	for (int32 i = 1; i < Owner->Ships.Num(); ++i)
	{
		FAstraBattleShip& S = Owner->Ships[i];
		if (!S.bAlive || S.bGhost || S.bPlayer || (S.DrawKind < 0 && !S.bDrawLamps))
		{
			continue;
		}
		const double D2 = FVector::DistSquared(S.Pos, F.Origin);
		if (S.DrawKind >= 0)
		{
			StageHull(S, D2);
			++Actors;                                   // (what the actor path would have made of it: the actor and its mesh component...)
			++Comps;
		}
		if (S.bDrawLamps)
		{
			StageLamps(S, D2);
			Comps += 1 + (LampSets.IsValidIndex(S.LampSet) ? LampSets[S.LampSet].Num() : 0);   // ...the running-light component and a component per lamp
		}
	}
	Sweep();
	Flush();
	LegacyActors = Actors;
	LegacyComps = Comps;
	LegacyActorsPeak = FMath::Max(LegacyActorsPeak, LegacyActors);
	LegacyCompsPeak = FMath::Max(LegacyCompsPeak, LegacyComps);
	HullsPeak = FMath::Max(HullsPeak, Hulls);
	LampsNow = Lamps.Prev;
	LampsPeak = FMath::Max(LampsPeak, LampsNow);
	const double Ms = (FPlatformTime::Seconds() - T0) * 1000.0;
	TickMs += Ms;
	TickMsMax = FMath::Max(TickMsMax, Ms);
	++TickCount;
}

// ------------------------------------------------------------------------------------------------------------------ the lens
void UAstraWarDraw::SetLensHint(bool bActive, double WithinKm, int32 ExemptId)
{
	bLens = bActive;
	LensKm = WithinKm;
	LensExempt = ExemptId;
}

void UAstraWarDraw::GetNearLensComponents(TArray<UPrimitiveComponent*>& Out) const
{
	for (const FKind& Kd : Kinds)
	{
		for (const FPage& P : Kd.Sets[1].Pages)
		{
			if (UInstancedStaticMeshComponent* C = P.Comp.Get())
			{
				Out.Add(C);
			}
		}
	}
}

// ------------------------------------------------------------------------------------------------------------------ what it holds
void UAstraWarDraw::Stats(FString& Out) const
{
	int32 Pages = 0;
	for (const FKind& Kd : Kinds)
	{
		for (const FSet& St : Kd.Sets)
		{
			Pages += St.Pages.Num();
		}
	}
	Out = FString::Printf(TEXT("%s | %.3f ms/frame (max %.2f) over %d frames | craft hulls %d now / %d peak in %d pages of %d (%d in the lens set), lamps %d now / %d peak (%d dropped) | "
	                           "what the actor path would be: %d actors, %d components (peak %d, %d)"),
	                      bLive ? TEXT("drawing") : (bSim ? TEXT("bench (not drawn)") : TEXT("off")), TickCount ? TickMs / TickCount : 0.0, TickMsMax, TickCount,
	                      Hulls, HullsPeak, Pages, PageSize, NearNow, LampsNow, LampsPeak, LampsDropped, LegacyActors, LegacyComps, LegacyActorsPeak, LegacyCompsPeak);
}

TSharedRef<FJsonObject> UAstraWarDraw::StatsJson() const
{
	TSharedRef<FJsonObject> J = MakeShared<FJsonObject>();
	J->SetNumberField(TEXT("ms_avg"), TickCount ? FMath::RoundToDouble(TickMs / TickCount * 1000.0) / 1000.0 : 0.0);
	J->SetNumberField(TEXT("ms_max"), FMath::RoundToDouble(TickMsMax * 1000.0) / 1000.0);
	J->SetNumberField(TEXT("frames"), TickCount);
	J->SetNumberField(TEXT("hulls_peak"), HullsPeak);
	J->SetNumberField(TEXT("lamps_peak"), LampsPeak);
	J->SetNumberField(TEXT("lamps_dropped"), LampsDropped);
	J->SetNumberField(TEXT("actors_it_replaces_peak"), LegacyActorsPeak);
	J->SetNumberField(TEXT("components_it_replaces_peak"), LegacyCompsPeak);
	int32 Pages = 0;
	for (const FKind& Kd : Kinds)
	{
		Pages += Kd.Sets[0].Pages.Num() + Kd.Sets[1].Pages.Num();
	}
	J->SetNumberField(TEXT("pages"), Pages);
	return J;
}
