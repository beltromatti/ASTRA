// ASTRA — the living space, drawn: the places (their lamps, what turns on them), the vessels (hulls with stable slots, lamps, plumes), the patrol craft, the buoys' lights.
// The way it is drawn is the war's (AstraWarDraw.cpp, docs/SCALA.md): instances, one component per kind of hull, nothing made or ticked per object, and what is far is a
// lamp (a few pixels of light) before it is a hull. Everything the system holds still in its own frame (the belt, the buoys) hangs under one component, moved once a frame.

#include "AstraSpaceLife.h"
#include "AstraBattleSubsystem.h"
#include "AstraNavLights.h"
#include "ASTRA.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Components/SceneComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/World.h"
#include "Materials/MaterialInterface.h"

using namespace AstraSpaceDraw;

namespace
{
	const FTransform& SpHiddenXf()
	{
		static const FTransform X(FQuat::Identity, FVector::ZeroVector, FVector(0.0001));
		return X;
	}

	uint32 SpMix(uint32 A)
	{
		A ^= A >> 16; A *= 0x7FEB352Du; A ^= A >> 15; A *= 0x846CA68Bu; A ^= A >> 16;
		return A;
	}

	/** How much of a lamp shows at this distance (km): all of it near, a little less far, none at the edge of the system. */
	float SpLampFade(double Km)
	{
		return 1.f - 0.7f * AstraFx::Ease((float)((Km - 60.0) / 190.0)) - 0.3f * AstraFx::Ease((float)((Km - 215.0) / 35.0));
	}
}

// ------------------------------------------------------------------------------------------------------------------ the hulls' pages
int32 UAstraSpaceLife::SetFor(const FString& Mesh)
{
	if (const int32* K = SetByMesh.Find(Mesh))
	{
		return Sets[*K].bFailed ? INDEX_NONE : *K;
	}
	const int32 Idx = Sets.AddDefaulted();
	Sets[Idx].Mesh = Mesh;
	SetByMesh.Add(Mesh, Idx);
	if (!bLive)
	{
		return Idx;                                           // the bench: staged and counted, not drawn
	}
	UStaticMesh* M = LoadObject<UStaticMesh>(nullptr, *FString::Printf(TEXT("/Game/ASTRA/Space/%s.%s"), *Mesh, *Mesh), nullptr, LOAD_Quiet | LOAD_NoWarn);
	if (!M)
	{
		M = LoadObject<UStaticMesh>(nullptr, *FString::Printf(TEXT("/Game/ASTRA/Ships/%s.%s"), *Mesh, *Mesh), nullptr, LOAD_Quiet | LOAD_NoWarn);   // (the Falcon and the other craft)
	}
	if (!M)
	{
		Sets[Idx].bFailed = true;
		UE_LOG(LogASTRA, Log, TEXT("[Space] no mesh %s yet (tools/ue_scripts/import_space_v3.py): its vessels are lamps only"), *Mesh);
		return INDEX_NONE;
	}
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
		Sets[Idx].bFailed = true;
		UE_LOG(LogASTRA, Warning, TEXT("[Space] %s: its materials (%s) are not flagged 'Used with Instanced Static Meshes' (tools/ue_scripts/make_scala_materials.py): its vessels are lamps only"), *Mesh, *Unflagged.TrimEnd());
		return INDEX_NONE;
	}
	Sets[Idx].StaticMesh = M;
	KeepMeshes.AddUnique(M);
	MakePage(Idx);
	return Idx;
}

AstraDraw::FPage* UAstraSpaceLife::MakePage(int32 SetIdx)
{
	FInstSet& S = Sets[SetIdx];
	AstraDraw::FPage& P = S.Set.Pages.AddDefaulted_GetRef();
	P.Xf.Init(SpHiddenXf(), PageSize);
	P.PrevXf.Init(SpHiddenXf(), PageSize);
	P.Owner.Init(-1, PageSize);
	if (bLive && S.StaticMesh && Host)
	{
		P.Comp = AstraDraw::MakeComp(Host, Host->GetRootComponent(), *FString::Printf(TEXT("Hull_%s_%d"), *S.Mesh, S.Set.Pages.Num()), S.StaticMesh, nullptr, PageSize, 0, true, true);
	}
	return &P;
}

void UAstraSpaceLife::StageHull(int32 SetIdx, int32 Key, const FTransform& Now)
{
	FInstSet& S = Sets[SetIdx];
	AstraDraw::FRef* R = S.Where.Find(Key);
	const bool bFresh = R == nullptr;
	if (!R)
	{
		const int32 Slot = S.Set.FreeSlots.Num() ? S.Set.FreeSlots.Pop(EAllowShrinking::No) : S.Set.NextSlot++;
		const int32 PageI = Slot / PageSize;
		while (S.Set.Pages.Num() <= PageI)
		{
			MakePage(SetIdx);
		}
		AstraDraw::FPage& P = S.Set.Pages[PageI];
		const int32 L = Slot % PageSize;
		P.Owner[L] = Key;
		++P.Live;
		P.High = FMath::Max(P.High, L + 1);
		++S.Set.Live;
		S.Set.Peak = FMath::Max(S.Set.Peak, S.Set.Live);
		AstraDraw::FRef N;
		N.Kind = (int16)SetIdx;
		N.Slot = Slot;
		R = &S.Where.Add(Key, N);
	}
	R->Frame = Frame;
	AstraDraw::FPage& P = S.Set.Pages[R->Slot / PageSize];
	const int32 L = R->Slot % PageSize;
	P.PrevXf[L] = bFresh ? Now : P.Xf[L];                  // (a hull that has just appeared has no past: it is not smeared across the sky from where its slot was last)
	P.Xf[L] = Now;
	++HullsNow;
}

void UAstraSpaceLife::FlushSets()
{
	for (FInstSet& S : Sets)
	{
		// what was not staged this frame is gone (docked out of view, out of range, away through the Gate): its slot goes back, hidden
		for (auto It = S.Where.CreateIterator(); It; ++It)
		{
			if (It.Value().Frame != Frame)
			{
				const AstraDraw::FRef& R = It.Value();
				AstraDraw::FPage& P = S.Set.Pages[R.Slot / PageSize];
				const int32 L = R.Slot % PageSize;
				P.Xf[L] = SpHiddenXf();
				P.PrevXf[L] = SpHiddenXf();
				P.Owner[L] = -1;
				--P.Live;
				--S.Set.Live;
				S.Set.FreeSlots.Add(R.Slot);
				It.RemoveCurrent();
			}
		}
		for (AstraDraw::FPage& P : S.Set.Pages)
		{
			if (P.Live == 0 && !P.bWritten)
			{
				continue;                                    // empty and already written hidden: nothing to send
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

void UAstraSpaceLife::HideSets()
{
	for (FInstSet& S : Sets)
	{
		S.Where.Reset();
		S.Set.FreeSlots.Reset();
		S.Set.NextSlot = 0;
		S.Set.Live = 0;
		for (AstraDraw::FPage& P : S.Set.Pages)
		{
			for (FTransform& X : P.Xf) { X = SpHiddenXf(); }
			for (FTransform& X : P.PrevXf) { X = SpHiddenXf(); }
			for (int32& O : P.Owner) { O = -1; }
			P.Live = 0;
			P.bWritten = P.High > 0;                    // one more write, all hidden
		}
	}
	FlushSets();
}

// ------------------------------------------------------------------------------------------------------------------ lamps and plumes
void UAstraSpaceLife::DrawLamps(const TArray<AstraSpace::FLamp>& Set, const FVector& Pos, const FQuat& Att, uint32 Hash, double Dist2, float Fade, bool bShipLamps)
{
	if (Fade <= 0.01f)
	{
		return;
	}
	const double DKm = FMath::Sqrt(Dist2) * 0.001;
	// a far place gives fewer lamps (a few hundred points of light would only run together): the thinning is by index, so the same ones stay
	const int32 Stride = DKm < 60.0 ? 1 : (DKm < 120.0 ? 2 : (DKm < 190.0 ? 4 : 8));
	for (int32 i = 0; i < Set.Num(); i += Stride)
	{
		const AstraSpace::FLamp& L = Set[i];
		// a ship's lamps blink out of step with every other ship's; a place's keep the phase it was given (a chaser runs along its row)
		const float Phase = L.Phase + (bShipLamps ? (float)((Hash >> ((i * 5) & 31)) & 31u) / 31.f * 2.2f : 0.f);
		float Fd = Fade;
		if (bShipLamps && L.Pattern == 0)
		{
			Fd *= 1.f - 0.6f * AstraFx::Ease((float)((DKm - 40.0) / 60.0));       // the steady ones go first
		}
		const float Inten = L.Glow * AstraSpace::PatternOn(L.Pattern, Clock, Phase) * LampGain * Fd * (float)Stride;
		if (Inten < 1.f)
		{
			continue;
		}
		FTransform* X;
		float* D = Lamps.Next(X);
		if (!D)
		{
			++LampsDropped;
			continue;
		}
		const FVector P = Pos + Att.RotateVector(L.P);
		const float Rm = L.SizeM * 0.5f * AstraFx::GlowK;
		*X = FTransform(FQuat::Identity, F.ToWorld(P), FVector(Rm * 2.f));
		AstraFx::Fill(D, L.C, Inten, 0.f, 0.f, 0.f, (float)((Hash >> 3) & 255u) / 255.f, Rm * 2.f, 0.f);
	}
}

void UAstraSpaceLife::AddPlume(const FVector& Lip, const FVector& Dir, float RadiusM, float Thrust, bool bAmber, float Salt)
{
	FTransform* X;
	float* D = Plumes.Next(X);
	if (!D)
	{
		return;
	}
	const float Len = RadiusM * (5.f + 25.f * Thrust);
	const float Width = RadiusM * 1.9f;
	const FVector DirW = F.InvAtt.RotateVector(Dir);
	const FVector LipW = F.ToWorld(Lip);
	*X = FTransform(FQuat::FindBetweenNormals(FVector::ZAxisVector, DirW), LipW + DirW * (Len * 50.0), FVector(Width, Width, Len));
	const FLinearColor Core = bAmber ? FLinearColor(1.f, 0.62f, 0.3f) : FLinearColor(0.78f, 0.9f, 1.f);
	AstraFx::Fill(D, Core, 70.f * LampGain * (0.3f + 0.7f * Thrust), Clock, bAmber ? 1.f : 0.f, 0.f, Salt, Width, Len);
}

// ------------------------------------------------------------------------------------------------------------------ the places
void UAstraSpaceLife::DrawPlaces()
{
	for (FSpaceLifePlace& P : Places)
	{
		if (!Layout.Nodes.IsValidIndex(P.Node))
		{
			continue;
		}
		const AstraSpace::FNode& N = Layout.Nodes[P.Node];
		for (FSpaceLifePlace::FTurning& T : P.Parts)
		{
			if (UStaticMeshComponent* C = T.Comp.Get())
			{
				const AstraSpace::FPart& D = T.Def;
				float Ang = D.Phase * 2.f * PI;
				if (D.SwingDeg > 0.f)
				{
					Ang += FMath::DegreesToRadians(D.SwingDeg) * FMath::Sin(Clock * 2.f * PI / FMath::Max(1.f, FMath::Abs(D.PeriodS)));
				}
				else if (FMath::Abs(D.PeriodS) > 0.1f)
				{
					Ang += Clock * 2.f * PI / D.PeriodS;
				}
				C->SetRelativeRotation(FQuat(D.Axis, Ang));
			}
		}
		if (!N.Mesh)
		{
			continue;
		}
		const double D2 = FVector::DistSquared(N.Pos, F.Origin);
		const double Km = FMath::Sqrt(D2) * 0.001;
		if (Km > 250.0)
		{
			continue;
		}
		const uint32 H = SpMix((uint32)GetTypeHash(P.Id));
		DrawLamps(N.Mesh->Lamps, N.Pos, N.Att, H, D2, SpLampFade(Km), false);
		// a refinery's flare: a torch of burning gas on its stack, flickering
		if (N.Mesh->FlareLenM > 1.f && Km < 160.0)
		{
			const float Fl = AstraSpace::PatternOn(7, Clock, (float)(H & 255u) / 40.f);
			AddPlume(N.Pos + N.Att.RotateVector(N.Mesh->Flare), N.Att.GetUpVector(), N.Mesh->FlareLenM / 30.f, 0.35f + 0.65f * Fl, true, (float)(H & 255u) / 255.f);
		}
	}
	// the buoys of the lanes: a lamp each, a chaser running along the lane
	for (const AstraSpace::FLane& L : Layout.Lanes)
	{
		for (int32 i = 0; i < L.Buoys.Num(); ++i)
		{
			const FVector& B = L.Buoys[i];
			const double D2 = FVector::DistSquared(B, F.Origin);
			const double Km = FMath::Sqrt(D2) * 0.001;
			if (Km > 200.0 || (Km > 110.0 && (i & 1)))
			{
				continue;
			}
			const float Inten = 300.f * AstraSpace::PatternOn(6, Clock, (float)i * 0.32f) * LampGain * SpLampFade(Km) * (Km > 110.0 ? 2.f : 1.f);
			if (Inten < 1.f)
			{
				continue;
			}
			FTransform* X;
			float* D = Lamps.Next(X);
			if (!D)
			{
				++LampsDropped;
				continue;
			}
			const float Rm = 1.6f * AstraFx::GlowK;
			*X = FTransform(FQuat::Identity, F.ToWorld(B + FVector(0.0, 0.0, 34.0)), FVector(Rm * 2.f));
			AstraFx::Fill(D, L.BuoyColor, Inten, 0.f, 0.f, 0.f, (float)(i & 255) / 255.f, Rm * 2.f, 0.f);
		}
	}
}

// ------------------------------------------------------------------------------------------------------------------ the vessels
namespace
{
	/** A hull's lamps when its mesh has none in data/space/meshes.json: the standard running lights from its bounds. */
	void SpGenericLamps(const AstraSpace::FHullDef& H, TArray<AstraSpace::FLamp>& Out)
	{
		const float L = H.Length * 0.5f, W = H.Length * 0.12f;
		auto Add = [&Out](const FVector& P, const FLinearColor& C, float Size, float Glow, uint8 Pat)
		{
			AstraSpace::FLamp Lp;
			Lp.P = P;
			Lp.C = C;
			Lp.SizeM = Size;
			Lp.Glow = Glow;
			Lp.Pattern = Pat;
			Out.Add(Lp);
		};
		const float S = FMath::Clamp(H.Length * 0.004f, 1.2f, 3.5f);
		Add(FVector(-L * 0.1f, -W, 0.f), FLinearColor(1.f, 0.06f, 0.04f), S, 160.f, 0);
		Add(FVector(-L * 0.1f, W, 0.f), FLinearColor(0.1f, 1.f, 0.35f), S, 160.f, 0);
		Add(FVector(-L, 0.f, 0.f), FLinearColor(1.f, 0.95f, 0.85f), S, 120.f, 0);
		Add(FVector(0.f, 0.f, W * 0.9f), FLinearColor(1.f, 1.f, 1.f), S * 1.1f, 900.f, 1);
		Add(FVector(0.f, 0.f, -W * 0.9f), FLinearColor(1.f, 0.1f, 0.05f), S, 500.f, 2);
	}
}

void UAstraSpaceLife::DrawVessels()
{
	const AstraSpace::FDataSet& D = AstraSpace::Data();
	static TMap<FName, TArray<AstraSpace::FLamp>> Generic;
	for (const AstraSpace::FVessel& V : Traffic.Vessels())
	{
		if (V.State == AstraSpace::EVState::Away)
		{
			continue;
		}
		const AstraSpace::FHullDef* H = D.Hull(V.Hull);
		if (!H)
		{
			continue;
		}
		const double D2 = FVector::DistSquared(V.Pos, F.Origin);
		const double Km = FMath::Sqrt(D2) * 0.001;
		if (Km > 250.0)
		{
			continue;
		}
		const FString& Mesh = H->Meshes.IsValidIndex(V.MeshIdx) ? H->Meshes[V.MeshIdx] : FString();
		const AstraSpace::FMeshData* MD = Mesh.IsEmpty() ? nullptr : D.Mesh(Mesh);
		// the hull, out to where it is still more than a speck (a tug: a few kilometres; a freighter: over a hundred)
		const double HullKm = H->HullKm > 0.f ? H->HullKm : (double)H->Radius * 0.35;
		if (Km < HullKm && !Mesh.IsEmpty())
		{
			const int32 SI = SetFor(Mesh);
			if (SI != INDEX_NONE)
			{
				StageHull(SI, V.Id, FTransform(F.ToWorldRot(V.Att), F.ToWorld(V.Pos), FVector::OneVector));
			}
		}
		// the lamps: a dark vessel (hiding) shows none
		if (V.bLit)
		{
			const TArray<AstraSpace::FLamp>* Lamps2 = MD && MD->Lamps.Num() ? &MD->Lamps : nullptr;
			if (!Lamps2)
			{
				TArray<AstraSpace::FLamp>& G = Generic.FindOrAdd(H->Key);
				if (G.Num() == 0)
				{
					SpGenericLamps(*H, G);
				}
				Lamps2 = &G;
			}
			DrawLamps(*Lamps2, V.Pos, V.Att, SpMix((uint32)V.Id * 2654435761u), D2, SpLampFade(Km), true);
		}
		// the drive: a plume as hard as it is working, a bell's glow
		if (V.Thrust > 0.04f && Km < 140.0)
		{
			if (MD && MD->Bells.Num())
			{
				for (const AstraSpace::FBell& B : MD->Bells)
				{
					AddPlume(V.Pos + V.Att.RotateVector(B.P), V.Att.RotateVector(FVector(-1.0, 0.0, 0.0)), B.R, V.Thrust, H->bAmber, (float)(V.Id & 255) / 255.f);
				}
			}
			else
			{
				AddPlume(V.Pos - V.Att.GetForwardVector() * (double)H->Length * 0.5, -V.Att.GetForwardVector(), H->Radius * 0.05f, V.Thrust, H->bAmber, (float)(V.Id & 255) / 255.f);
			}
		}
	}
}

void UAstraSpaceLife::DrawPatrols()
{
	for (const AstraSpace::FPatrol& P : Traffic.Patrols())
	{
		if (P.State == 2 || P.Mesh.IsEmpty())
		{
			continue;
		}
		TArray<AstraSpace::FLamp>* Cached = NavLampCache.Find(P.Mesh);
		if (!Cached)
		{
			// the ships' own table (data/ship/nav_lights.json): cm in the mesh's frame, converted to this module's metres
			TArray<FAstraNavLamp> Raw;
			UAstraNavLights::LampsFor(P.Mesh, false, false, Raw);
			TArray<AstraSpace::FLamp> Conv;
			for (const FAstraNavLamp& R : Raw)
			{
				AstraSpace::FLamp L;
				L.P = R.Local * 0.01;
				L.C = R.Color;
				L.SizeM = R.SizeM;
				L.Glow = R.Glow;
				L.Pattern = R.Pattern;
				Conv.Add(L);
			}
			Cached = &NavLampCache.Add(P.Mesh, MoveTemp(Conv));
		}
		for (int32 i = 0; i < P.Craft.Num(); ++i)
		{
			const AstraSpace::FPatrolCraft& C = P.Craft[i];
			const double D2 = FVector::DistSquared(C.Pos, F.Origin);
			const double Km = FMath::Sqrt(D2) * 0.001;
			if (Km > 120.0)
			{
				continue;
			}
			if (Km < 60.0)
			{
				const int32 SI = SetFor(P.Mesh);
				if (SI != INDEX_NONE)
				{
					StageHull(SI, 100000 + P.Id * 100 + i, FTransform(F.ToWorldRot(C.Att), F.ToWorld(C.Pos), FVector::OneVector));
				}
			}
			const uint32 H = SpMix((uint32)(P.Id * 100 + i) * 2654435761u);
			// a craft's steady lights thin out with the distance and its strobe goes last (as the war's craft do)
			DrawLamps(*Cached, C.Pos, C.Att, H, D2, 1.f - AstraFx::Ease((float)((Km - 18.0) / 30.0)), true);
			if (Km < 50.0)
			{
				AddPlume(C.Pos - C.Att.GetForwardVector() * 8.0, -C.Att.GetForwardVector(), 0.9f, 0.45f, false, (float)(H & 255u) / 255.f);
			}
		}
	}
}
