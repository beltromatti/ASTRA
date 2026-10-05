// ASTRA — DISTRUZIONE: the damage inside the Aquila (see AstraDamageModel.h and docs/DISTRUZIONE.md).

#include "AstraDamageModel.h"

#include "ASTRA.h"
#include "HAL/IConsoleManager.h"
#include "Misc/ScopeExit.h"

namespace
{
	// ---------------------------------------------------------------------------------------------------------- the tuning
	// Everything the physics reads that a fight's balance depends on lives here, named, so the bench and the console can move it
	// (astra.damage.<name> <value>) without a build.
	float GDmHole = 1.f;        // the size of the holes a blow punches
	float GDmFire = 1.f;        // how readily a blow starts a fire
	float GDmCasualty = 1.5f;    // how many a blow's blast hurts
	float GDmFields = 1.f;           // 1: containment fields on the holes; 0: none (the air tests)
	float GDmVent = 60.f;            // m/s: the speed the air leaves a hole at (the real, choked flow is twice this: the game's time is kinder)
	float GDmMix = 25.f;             // m/s: the speed it moves through an open way between two compartments
	float GDmFieldCap = 2.4f;        // m2 of hole a field at full power holds
	float GDmDoorOpen = 1.f;         // how often the doors of the ship stand open
	float GDmPowerFloor = 0.5f;      // what the allocations keep when the compartments that feed them are all lost (the backup ring)
	float GDmCaptain = 1.f;          // 1: the air and the fire can hurt the Captain
	float GDmBurn = 1.f;             // the structure the fires eat
	float GDmDoctrine = 1.f;         // 1: pressure bulkheads and lockdowns close by themselves
	float GDmMist = 1.f;             // 1: the rooms that have anything to burn but no gas system have the sprinklers' mist (BATTAGLIA-3); 0: only the machinery and stores have fixed suppression

	FAutoConsoleVariableRef DmCVarHole(TEXT("astra.damage.hole"), GDmHole, TEXT("DISTRUZIONE: scale of the holes a blow punches through the hull"));
	FAutoConsoleVariableRef DmCVarFire(TEXT("astra.damage.fire"), GDmFire, TEXT("DISTRUZIONE: how readily blows start fires"));
	FAutoConsoleVariableRef DmCVarCasualty(TEXT("astra.damage.casualties"), GDmCasualty, TEXT("DISTRUZIONE: scale of the casualties a blow's blast makes"));
	FAutoConsoleVariableRef DmCVarFields(TEXT("astra.damage.fields"), GDmFields, TEXT("DISTRUZIONE: 1 containment fields form on holes, 0 none"));
	FAutoConsoleVariableRef DmCVarVent(TEXT("astra.damage.vent"), GDmVent, TEXT("DISTRUZIONE: m/s the air leaves a hole at"));
	FAutoConsoleVariableRef DmCVarMix(TEXT("astra.damage.mix"), GDmMix, TEXT("DISTRUZIONE: m/s the air moves through an open way"));
	FAutoConsoleVariableRef DmCVarFieldCap(TEXT("astra.damage.field_cap"), GDmFieldCap, TEXT("DISTRUZIONE: m2 of hole a containment field holds at full power"));
	FAutoConsoleVariableRef DmCVarDoorOpen(TEXT("astra.damage.doors"), GDmDoorOpen, TEXT("DISTRUZIONE: scale of how often doors stand open (fire and smoke pass through open ones)"));
	FAutoConsoleVariableRef DmCVarPowerFloor(TEXT("astra.damage.power_floor"), GDmPowerFloor, TEXT("DISTRUZIONE: the share of an allocation the backup ring keeps"));
	FAutoConsoleVariableRef DmCVarCaptain(TEXT("astra.damage.captain"), GDmCaptain, TEXT("DISTRUZIONE: 1 the air, the smoke and the fire can hurt (and kill) the Captain, 0 they cannot"));
	FAutoConsoleVariableRef DmCVarBurn(TEXT("astra.damage.burn"), GDmBurn, TEXT("DISTRUZIONE: scale of the hull structure the fires eat"));
	FAutoConsoleVariableRef DmCVarDoctrine(TEXT("astra.damage.auto_seal"), GDmDoctrine, TEXT("DISTRUZIONE: 1 pressure bulkheads and lockdowns close by themselves, 0 they do not"));
	FAutoConsoleVariableRef DmCVarMist(TEXT("astra.damage.mist"), GDmMist, TEXT("BATTAGLIA-3: 1 the cabins, messes and offices have the sprinklers' mist (fixed suppression a few seconds later than the gas), 0 only the machinery and stores do"));

	constexpr float DmStep = 0.2f;                 // s: the physics' step (the Aquila's: FAstraDamageModel::StepS, which a fleet ship's inside sets longer)
	constexpr float DmHoleMin = 0.12f;             // m2: a hole big enough to be an incident (the smaller ones are sealed by the plating itself)
	constexpr float DmFireMin = 0.10f;
	constexpr float DmPowerMin = 0.85f;

	float DmPow(float X, float E) { return FMath::Pow(FMath::Max(X, 0.f), E); }

	/** The distance from a point to a segment (cm). */
	float DmDistToSegment(const FVector& P, const FVector& A, const FVector& B)
	{
		return (float)FVector::Dist(P, FMath::ClosestPointOnSegment(P, A, B));
	}

	float DmTypeFire(uint8 Type) { return Type == 1 ? 1.3f : (Type == 2 ? 1.2f : 0.35f); }       // 0 kinetic, 1 energy, 2 explosive
	float DmTypeHole(uint8 Type) { return Type == 1 ? 0.35f : (Type == 2 ? 1.5f : 1.0f); }
	float DmTypeBlast(uint8 Type) { return Type == 1 ? 0.5f : (Type == 2 ? 1.4f : 1.0f); }
	/** How much of a room a blow, a fire or a fault can take at once: a hangar is not set alight, nor cut off from its power, by one slug; a closet is. */
	float DmSize(float VolumeM3) { return FMath::Clamp(FMath::Sqrt(1500.f / FMath::Max(VolumeM3, 1.f)), 0.12f, 1.3f); }
	float DmKillRadius(uint8 Type) { return Type == 1 ? 1.8f : (Type == 2 ? 3.4f : 2.4f); }     // m: how far from the path of a blow it kills (kinetic, energy, explosive)
	float DmHurtRadius(uint8 Type) { return Type == 1 ? 3.5f : (Type == 2 ? 7.0f : 5.0f); }
	FString DmSystemsOf(const FAstraDamageMap& Map, int32 Comp);

	/** A room whose fire is news for the bridge: it holds the reactor, the coolant, the weapons, the ordnance, the engines or the sensors, or it is a magazine, Main Engineering or the bridge. The rest of the
	 *  ship burning is routine: the incident list, the damage board and the log carry it, and the crew reads them at its next turn (BATTAGLIA-3: in 23 minutes of play 53 "the fire has spread" and 25 "the fire is
	 *  out" each woke a turn of the crew). */
	bool DmIsVital(const FAstraDmgComp& C, const FAstraDmgProfile& P)
	{
		if (P.bExplosive || C.Kind == TEXT("bridge") || C.Kind == TEXT("engineering"))
		{
			return true;
		}
		for (const EAstraDmgSystem S : {EAstraDmgSystem::Reactor, EAstraDmgSystem::Coolant, EAstraDmgSystem::Weapons, EAstraDmgSystem::Ordnance, EAstraDmgSystem::Sensors, EAstraDmgSystem::Engines})
		{
			if (C.Systems.Contains((uint8)S))
			{
				return true;
			}
		}
		return false;
	}
}

// ================================================================================================================== set up

void FAstraDamageModel::Init(TSharedRef<const FAstraDamageMap> InMap, FAstraDmgHooks InHooks, int32 Seed)
{
	Map = InMap;
	Hooks = MoveTemp(InHooks);
	Rng.Initialize(Seed);
	Reset();
}

void FAstraDamageModel::Reset()
{
	if (Hooks.SealDoor && Map.IsValid())
	{
		for (const int32 D : Sealed)
		{
			Hooks.SealDoor(Map->Doors[D].Id, false);            // the bulkheads open again
		}
	}
	Active.Reset();
	Sealed.Reset();
	DoorTimer.Reset();
	SectionTimer.Reset();
	SpreadTold.Reset();
	PowerNow = FAstraDmgPower();
	Cap = FAstraDmgCaptain();
	Stats = FBooks();
	Acc = PeopleT = SyncT = SystemsT = Clock = 0.f;
	bDoorsChanged = false;
}

FAstraDmgState& FAstraDamageModel::Get(int32 Comp)
{
	FAstraDmgState& S = Active.FindOrAdd(Comp);
	if (S.Comp == INDEX_NONE)
	{
		S.Comp = Comp;
		Stats.MaxActive = FMath::Max(Stats.MaxActive, Active.Num());
	}
	S.Age = 0.f;
	return S;
}

FString FAstraDamageModel::Say(int32 Comp) const
{
	return Map->Describe(Comp);
}

void FAstraDamageModel::Flush()
{
	if (Pending.Num() == 0)
	{
		return;
	}
	const TArray<TPair<FString, bool>> Out = MoveTemp(Pending);
	Pending.Reset();
	if (Hooks.Event)
	{
		for (const TPair<FString, bool>& P : Out)
		{
			Hooks.Event(P.Key, P.Value);
		}
	}
}

float FAstraDamageModel::ExitDistanceM(int32 Comp, const FVector& PosCm) const
{
	if (!Map->Comps.IsValidIndex(Comp))
	{
		return 0.f;
	}
	float Best = -1.f;
	for (const FAstraDmgLink& L : Map->Comps[Comp].Links)
	{
		const float D = (float)(FVector::Dist2D(PosCm, L.AtCm) / 100.0);
		Best = Best < 0.f ? D : FMath::Min(Best, D);
	}
	return Best < 0.f ? 0.f : Best;
}

float FAstraDamageModel::Emergency(int32 Comp) const
{
	const FAstraDmgState* S = Active.Find(Comp);
	if (!S)
	{
		return 0.f;
	}
	return FMath::Clamp(FMath::Max(FMath::Max3((1.f - S->Power) * 1.0f, (1.f - S->Air) * 1.2f, S->Fire * 1.f), S->Smoke * 0.7f, S->Wreck * 0.8f), 0.f, 1.f);
}

FAstraDmgLight FAstraDamageModel::LightOf(int32 Comp) const
{
	FAstraDmgLight L;
	const FAstraDmgState* S = Active.Find(Comp);
	if (!S)
	{
		return L;
	}
	if (S->bGutted || S->Wreck >= 1.f)
	{
		L.Mains = 0.f;                                  // lost: not even the strips
		return L;
	}
	// the mains give way between three quarters and an eighth of the room's power; the emergency strips (red, a seventh of the light) come up as they go
	const float Mains = FMath::SmoothStep(0.12f, 0.75f, S->Power);
	L.Mains = Mains * (1.f - 0.5f * S->Smoke);
	L.Strips = 0.14f * (1.f - Mains) * (1.f - S->Wreck);
	L.Tint = FLinearColor(1.f, 0.07f, 0.03f);
	L.Mix = FMath::Clamp((1.f - Mains) * 0.95f, 0.f, 1.f);
	// a decompression is announced in red too, and a fire lights the room orange
	if (S->Hole > 0.02f && S->Air < 0.92f)
	{
		L.Mix = FMath::Max(L.Mix, 0.55f);
	}
	if (S->Fire > 0.08f)
	{
		const float FireMix = FMath::Clamp(S->Fire * 0.7f, 0.f, 0.6f);
		if (FireMix > L.Mix)
		{
			L.Tint = FLinearColor(1.f, 0.42f, 0.1f);
			L.Mix = FireMix;
		}
	}
	// unsteady: a supply that is failing (not one that is gone), a blow a moment ago, a fire in the room
	float Flick = S->Power > 0.14f && S->Power < 0.9f ? FMath::Clamp((1.f - S->Power) * 1.6f, 0.f, 1.f) : 0.f;
	Flick = FMath::Max(Flick, FMath::Clamp(1.f - S->HitAge / 2.5f, 0.f, 1.f) * 0.8f);
	Flick = FMath::Max(Flick, FMath::Clamp(S->Fire * 1.2f, 0.f, 0.7f));
	L.Flicker = Flick;
	return L;
}

int32 FAstraDamageModel::NumWrecked() const
{
	int32 N = 0;
	for (const auto& KV : Active)
	{
		N += KV.Value.Wreck >= 1.f ? 1 : 0;
	}
	return N;
}

int32 FAstraDamageModel::NumHazards() const
{
	int32 N = 0;
	for (const auto& KV : Active)
	{
		N += (KV.Value.Hole >= DmHoleMin ? 1 : 0) + (KV.Value.Fire >= DmFireMin ? 1 : 0) + (KV.Value.Power < DmPowerMin ? 1 : 0);
	}
	return N;
}

float FAstraDamageModel::SeverityOf(const FAstraDmgState& S, int32 Kind)
{
	switch (Kind)
	{
	case 0:  return FMath::Clamp(S.Hole / 2.5f, 0.f, 1.f);
	case 1:  return FMath::Clamp(S.Fire, 0.f, 1.f);
	default: return FMath::Clamp(1.f - S.Power, 0.f, 1.f);
	}
}

FString FAstraDamageModel::InfoText() const
{
	int32 Holes = 0, Fires = 0, Dark = 0, Vac = 0;
	for (const auto& KV : Active)
	{
		Holes += KV.Value.Hole >= DmHoleMin ? 1 : 0;
		Fires += KV.Value.Fire >= DmFireMin ? 1 : 0;
		Dark += KV.Value.Power < DmPowerMin ? 1 : 0;
		Vac += KV.Value.Air < 0.5f ? 1 : 0;
	}
	return FString::Printf(TEXT("%d compartments in play: %d open to space, %d burning, %d without power, %d short of air, %d wrecked; %d fields (load %.0f %%), %d pressure bulkheads shut | "
	                            "books: %d hits (%d reached the interior), %d holes, %d fires, %d killed, %d wounded, %d fields failed, %d explosions"),
	                       Active.Num(), Holes, Fires, Dark, Vac, NumWrecked(), PowerNow.Fields, 100.f * PowerNow.FieldLoad, Sealed.Num(),
	                       Stats.Hits, Stats.HitsInside, Stats.Holes, Stats.Fires, Stats.Killed, Stats.Wounded, Stats.FieldsFailed, Stats.Explosions);
}

// ================================================================================================================== where a blow goes

bool FAstraDamageModel::SkinEntry(const FAstraHullHit& H, FVector& OutAt, FVector& OutDir) const
{
	// The hull's box (GUERRA) and the plan do not have the same height: the plan's decks fill the body of the hull from the keel to
	// the top of its highest body deck (the Aquila's Deck 2). A blow's height on the box (-1..1) is carried onto that body; its length
	// and its breadth are the same on both (the plan is the hull's frame, moved by the map's origin: the Aquila's is the bridge, a class
	// plan's is the mesh's own). The blow enters where the plan's envelope is: the plating at that height.
	const FVector Plan(H.HullM.X - Map->OriginInHullM.X, H.HullM.Y - Map->OriginInHullM.Y, H.HullM.Z - Map->OriginInHullM.Z);
	const float Tz = FMath::Clamp((H.Box.Z + 1.f) * 0.5f, 0.f, 1.f);
	const float Bottom = Map->KeelCm() + 40.f, Top = Map->BodyTopCm() - 40.f;
	const float Z = FMath::Lerp(Bottom, Top, Tz);
	const int32 Deck = FMath::Max(Map->FirstBodyDeck, Map->DeckAtZ(Z));
	const FAstraDmgDeck* D = Map->DeckById(Deck);
	if (!D)
	{
		return false;
	}
	FVector N = FVector::ZeroVector;       // the face's outward normal
	FVector At = FVector::ZeroVector;
	const float X = (float)Plan.X * 100.f;
	switch (H.Facing)
	{
	case 2:   // port
	case 3:   // starboard
	{
		const float Sign = H.Facing == 3 ? 1.f : -1.f;
		const float Xc = FMath::Clamp(X, D->XAftCm, D->XFwdCm);
		At = FVector(Xc, Sign * D->HalfWidthAt(Xc), Z);
		N = FVector(0.0, Sign, 0.0);
		break;
	}
	case 0:   // bow
	case 1:   // stern
	{
		const float Sign = H.Facing == 0 ? 1.f : -1.f;
		const float Xe = Sign > 0.f ? D->XFwdCm : D->XAftCm;
		At = FVector(Xe, H.Box.Y * D->HalfWidthAt(Xe), Z);
		N = FVector(Sign, 0.0, 0.0);
		break;
	}
	case 4:   // dorsal
	{
		const FAstraDmgDeck* Top2 = Map->DeckById(Map->FirstBodyDeck);
		const float Xc = FMath::Clamp(X, Top2->XAftCm, Top2->XFwdCm);
		At = FVector(Xc, H.Box.Y * Top2->HalfWidthAt(Xc), Map->BodyTopCm() + 20.f);
		N = FVector(0.0, 0.0, 1.0);
		// the bridge's island (a class's tower or block) stands on the top of the hull: a blow on it enters its own deck
		for (const FAstraDmgComp& C : Map->Comps)
		{
			if (!Map->IsBody(C.Deck) && At.X >= C.Box.Min.X - 300.f && At.X <= C.Box.Max.X + 300.f && At.Y >= C.Box.Min.Y - 300.f && At.Y <= C.Box.Max.Y + 300.f)
			{
				At.Z = C.Box.Max.Z + 40.f;
				break;
			}
		}
		break;
	}
	default:  // ventral
	{
		const FAstraDmgDeck* Low = Map->DeckById(Map->LastBodyDeck);
		const float Xc = FMath::Clamp(X, Low->XAftCm, Low->XFwdCm);
		At = FVector(Xc, H.Box.Y * Low->HalfWidthAt(Xc), Map->KeelCm() - 20.f);
		N = FVector(0.0, 0.0, -1.0);
		break;
	}
	}
	// the way in: the blow's own, bent towards the plating's normal when it came in at a graze (it tumbles and bites in)
	FVector Dir = H.Dir.GetSafeNormal();
	if (Dir.IsNearlyZero())
	{
		Dir = -N;
	}
	for (int32 Pass = 0; Pass < 4 && FVector::DotProduct(Dir, -N) < 0.35; ++Pass)
	{
		Dir = (Dir + (-N) * 0.6).GetSafeNormal();
	}
	OutAt = At;
	OutDir = Dir;
	return true;
}

namespace
{
	struct FDmCell
	{
		int32 Comp = INDEX_NONE;
		float Energy = 0.f;          // what it spends in this compartment
		FVector In = FVector::ZeroVector, Out = FVector::ZeroVector;
		float Arriving = 0.f;        // what reaches it
	};
}

bool FAstraDamageModel::Trace(const FAstraHullHit& H, FVector& OutEntryCm, TArray<int32>& OutComps, float* OutEnergy) const
{
	OutComps.Reset();
	if (!Map.IsValid())
	{
		return false;
	}
	FVector S, D;
	if (!SkinEntry(H, S, D))
	{
		return false;
	}
	OutEntryCm = S;
	// the path, a metre at a time: the plating first (what is left of the blow after it is the energy that reaches the first compartment),
	// then each compartment it crosses swallows a share and the walls take some more
	const float E0 = H.Felt;
	const float MaxPathM = FMath::Clamp(14.f + 0.6f * E0, 14.f, 70.f);
	int32 Cur = INDEX_NONE;
	float E = E0;
	for (float T = 0.f; T < MaxPathM && E >= 2.f; T += 1.f)
	{
		const int32 C = Map->CompartmentAt(S + D * (double)(T * 100.f), 35.f);
		if (C == INDEX_NONE || C == Cur)
		{
			continue;
		}
		if (Cur == INDEX_NONE)
		{
			E = E0 * FMath::Exp(-T / 22.f);       // the armoured belt and the frames between the plating and the first room
			if (OutEnergy)
			{
				*OutEnergy = E;
			}
			if (E < 2.f)
			{
				break;
			}
		}
		else
		{
			E *= 0.85f;                          // the wall
		}
		Cur = C;
		OutComps.Add(C);
		E *= 1.f - Map->ProfileOf(C).Fill;
		if (OutComps.Num() >= 5)
		{
			break;
		}
	}
	return OutComps.Num() > 0;
}

// ================================================================================================================== a blow

void FAstraDamageModel::Impact(const FAstraHullHit& H, FAstraImpactResult& Out)
{
	ON_SCOPE_EXIT { Flush(); };
	bImpactOccupied = false;
	++Stats.Hits;
	Stats.Energy += H.Felt;
	if (!Map.IsValid() || H.Felt < 3.f)
	{
		return;
	}
	FVector S, D;
	if (!SkinEntry(H, S, D))
	{
		return;
	}
	Out.EntryCm = S;
	const float E0 = H.Felt;
	const float MaxPathM = FMath::Clamp(14.f + 0.6f * E0, 14.f, 70.f);
	TArray<FDmCell, TInlineAllocator<6>> Cells;
	int32 Cur = INDEX_NONE;
	float E = E0;
	for (float T = 0.f; T < MaxPathM; T += 1.f)
	{
		const FVector P = S + D * (double)(T * 100.f);
		const int32 C = Map->CompartmentAt(P, 35.f);
		if (C == INDEX_NONE)
		{
			continue;
		}
		if (C == Cur)
		{
			Cells.Last().Out = P;
			continue;
		}
		if (Cells.Num() == 0)
		{
			E = E0 * FMath::Exp(-T / 22.f);
			if (E < 2.f)
			{
				break;
			}
			Out.Energy = E;
		}
		else
		{
			E *= 0.85f;
		}
		FDmCell Cell;
		Cell.Comp = C;
		Cell.Arriving = E;
		Cell.In = Cell.Out = P;
		const float Fill = Map->ProfileOf(C).Fill;
		Cell.Energy = E < 5.f ? E : E * Fill;                 // a blow nearly spent stays where it is
		E -= Cell.Energy;
		Cur = C;
		Cells.Add(Cell);
		if (Cells.Num() >= 5 || E < 2.f)
		{
			break;
		}
	}
	if (Cells.Num() == 0)
	{
		return;
	}
	++Stats.HitsInside;
	Stats.EnergyInside += Out.Energy;
	for (int32 i = 0; i < Cells.Num(); ++i)
	{
		const FDmCell& C = Cells[i];
		Out.Touch(C.Comp, C.In);
		Deposit(C.Comp, C.Energy, H.Type, C.In, D, i == 0, Out);
		BlastPeople(C.Comp, C.Energy * DmTypeBlast(H.Type), H.Type, C.In, C.Out, Out);
	}
	// a warhead that goes off inside throws its shock through the doors of the first room too
	if (H.Type == 2)
	{
		const FDmCell& C0 = Cells[0];
		for (const FAstraDmgLink& L : Map->Comps[C0.Comp].Links)
		{
			if (L.Kind == FAstraDmgLink::EKind::Blast || Out.Comps.Contains(L.To))
			{
				continue;
			}
			const float Splash = C0.Energy * 0.22f;
			if (Splash >= 3.f)
			{
				Deposit(L.To, Splash * 0.6f, H.Type, L.AtCm, D, false, Out);
				BlastPeople(L.To, Splash, H.Type, C0.In, L.AtCm, Out);
				Out.Touch(L.To, L.AtCm);
			}
		}
	}
}

void FAstraDamageModel::Strike(int32 Comp, float Energy, uint8 Type, const FVector& AtCm, bool bHole, FAstraImpactResult& Out)
{
	if (!Map.IsValid() || !Map->Comps.IsValidIndex(Comp))
	{
		return;
	}
	ON_SCOPE_EXIT { Flush(); };
	++Stats.Hits;
	++Stats.HitsInside;
	Stats.Energy += Energy;
	Stats.EnergyInside += Energy;
	Out.Energy = Energy;
	Out.EntryCm = AtCm;
	Out.Touch(Comp, AtCm);
	Deposit(Comp, Energy, Type, AtCm, FVector::ForwardVector, bHole, Out);
	BlastPeople(Comp, Energy * DmTypeBlast(Type), Type, AtCm, AtCm, Out);
}

void FAstraDamageModel::GutSection(float XMinCm, float XMaxCm, const FString& Name, FAstraImpactResult& Out)
{
	if (!Map.IsValid())
	{
		return;
	}
	ON_SCOPE_EXIT { Flush(); };
	int32 Rooms = 0;
	for (int32 i = 0; i < Map->Comps.Num(); ++i)
	{
		const FAstraDmgComp& C = Map->Comps[i];
		const float X = C.Box.GetCenter().X;
		if (!Map->IsBody(C.Deck) || X < XMinCm || X > XMaxCm)
		{
			continue;
		}
		FAstraDmgState& S = Get(i);
		if (S.bGutted)
		{
			continue;
		}
		++Rooms;
		S.bGutted = true;
		S.Wreck = 1.f;
		S.Power = 0.f;
		S.Air = FMath::Min(S.Air, 0.02f);
		S.Hole = 0.f;
		S.Fire = 0.f;
		S.bLocked = false;
		if (Cap.Comp == i && Cap.State != FAstraDmgCaptain::EState::Dead)
		{
			Cap.Trauma += 60.f;                                         // the section goes round the Captain: unconscious at best
			Cap.Cause = TEXT("the section gutted");
		}
		TArray<FAstraDmgPerson> There;
		if (Hooks.PeopleIn)
		{
			Hooks.PeopleIn(C, There);
		}
		for (const FAstraDmgPerson& Pr : There)
		{
			// most of whoever was in it is lost; some were in the part that held, or got out through a door before the deck gave way
			const float U = Rng.FRand();
			if (U < 0.5f)
			{
				Harm(Pr.Roster, true, EAstraDmgHarm::Blast, &Out, C);
			}
			else if (U < 0.75f)
			{
				Harm(Pr.Roster, false, EAstraDmgHarm::Blast, &Out, C);
			}
		}
	}
	++Stats.Wrecks;
	Report(FString::Printf(TEXT("damage report: the %s section of the hull is gutted — %d compartments lost with it, no air and no power there, %d killed and %d wounded"), *Name, Rooms, Out.Killed, Out.Wounded), true);
}

void FAstraDamageModel::Overload(int32 Comp, float Loss, FAstraImpactResult& Out)
{
	if (!Map.IsValid() || !Map->Comps.IsValidIndex(Comp))
	{
		return;
	}
	ON_SCOPE_EXIT { Flush(); };
	const FAstraDmgComp& C = Map->Comps[Comp];
	FAstraDmgState& S = Get(Comp);
	const bool bWas = S.Power < DmPowerMin;
	S.Power = FMath::Max(0.f, S.Power - Loss);
	if (S.Power < DmPowerMin && !bWas)
	{
		++Stats.Conduits;
		Out.bPower = true;
		Out.Lines.AddUnique(FString::Printf(TEXT("power lost in %s"), *Say(Comp)));
	}
	Out.Touch(Comp, C.Box.GetCenter());
	BlastPeople(Comp, 9.f, 1, C.Box.GetCenter(), C.Box.GetCenter(), Out);
}

FString FAstraDamageModel::SystemsText(int32 Comp) const
{
	return Map.IsValid() && Map->Comps.IsValidIndex(Comp) ? DmSystemsOf(*Map, Comp) : FString();
}

int32 FAstraDamageModel::PickHeatRoom(int32 Seq) const
{
	if (!Map.IsValid())
	{
		return INDEX_NONE;
	}
	if (HeatRooms.Num() == 0)
	{
		// the rooms that carry the reactor's and the coolant's conduits, the nearest to Main Engineering (plan x -351 m, Deck 7) first
		const FVector Engineering(-35100.0, 0.0, -5800.0);
		TArray<TPair<double, int32>> Near;
		for (int32 i = 0; i < Map->Comps.Num(); ++i)
		{
			const FAstraDmgComp& C = Map->Comps[i];
			if (!C.bCorridor && (C.Systems.Contains((uint8)EAstraDmgSystem::Reactor) || C.Systems.Contains((uint8)EAstraDmgSystem::Coolant)) && C.Deck >= 5 && C.Deck <= 8)
			{
				Near.Add({FVector::Dist(C.Box.GetCenter(), Engineering), i});
			}
		}
		Near.Sort([](const TPair<double, int32>& A, const TPair<double, int32>& B) { return A.Key < B.Key; });
		for (int32 k = 0; k < FMath::Min(6, Near.Num()); ++k)
		{
			HeatRooms.Add(Near[k].Value);
		}
	}
	return HeatRooms.Num() ? HeatRooms[Seq % HeatRooms.Num()] : INDEX_NONE;
}

float FAstraDamageModel::CategoryFactor(const FString& Name) const
{
	if (!Map.IsValid())
	{
		return 1.f;
	}
	for (int32 c = 0; c < (int32)EAstraDmgCategory::Num; ++c)
	{
		if (Name.Equals(Map->CategoryName((EAstraDmgCategory)c), ESearchCase::IgnoreCase))
		{
			return PowerNow.Factor[c];
		}
	}
	return 1.f;
}

void FAstraDamageModel::Deposit(int32 Comp, float Energy, uint8 Type, const FVector& AtCm, const FVector& Dir, bool bFirst, FAstraImpactResult& Out)
{
	if (Energy <= 0.2f)
	{
		return;
	}
	const FAstraDmgComp& C = Map->Comps[Comp];
	const FAstraDmgProfile& P = Map->ProfileOf(Comp);
	FAstraDmgState& S = Get(Comp);
	TArray<int32, TInlineAllocator<6>> Feeds;       // the rooms a corridor's bus feeds (done last: bringing a room into play may move the states)
	S.Age = 0.f;
	S.HitAge = 0.f;
	S.BlowAt = AtCm;
	// --- the hole: where the blow came in, if the room was where it came in and it had the strength to punch the plating
	if (bFirst && Energy >= 4.f)
	{
		const float Area = FMath::Min(6.f, 0.035f * GDmHole * DmTypeHole(Type) * DmPow(Energy - 3.5f, 0.9f));
		if (Area >= 0.02f)
		{
			if (S.Hole < 0.005f)
			{
				S.HoleAt = AtCm;
			}
			S.Hole = FMath::Min(8.f, S.Hole + Area);
			if (S.Field == FAstraDmgState::EField::Holding)
			{
				S.FieldStress += Area / FMath::Max(0.8f, GDmFieldCap * 0.6f);       // another hole in the same room strains the field
			}
			if (Area >= DmHoleMin)
			{
				Out.bBreach = true;
				++Stats.Holes;
				Out.Lines.AddUnique(FString::Printf(TEXT("a hull breach in %s"), *Say(Comp)));
			}
		}
	}
	// a field already holding takes the shock of whatever lands in the room
	if (S.Field == FAstraDmgState::EField::Holding)
	{
		S.FieldStress += Energy / 70.f;
	}
	// --- fire: what burns in the room, lit by what the blow is
	const float O2 = FMath::Clamp((S.Air - 0.2f) / 0.5f, 0.f, 1.f);
	const float Size = DmSize(C.VolumeM3);
	const float Ignite = FMath::Clamp(Energy / 40.f * DmTypeFire(Type) * P.Ignite * GDmFire * Size, 0.f, 0.9f) * O2;
	if (Ignite > 0.02f)
	{
		const bool bWas = S.Fire >= DmFireMin;
		if (!bWas)
		{
			S.FireAt = AtCm;
		}
		S.Fire = FMath::Clamp(S.Fire + Ignite * (1.f - S.Fire), 0.f, 1.f);
		S.Smoke = FMath::Clamp(S.Smoke + 0.3f * Ignite, 0.f, 1.f);
		if (S.Fire >= DmFireMin && !bWas)
		{
			Out.bFire = true;
			++Stats.Fires;
			Out.Lines.AddUnique(FString::Printf(TEXT("a fire in %s"), *Say(Comp)));
		}
	}
	// --- power: the conduits of the room, and of the rooms the corridor feeds
	const float Lost = FMath::Clamp(Energy / 45.f * P.Conduit * Size, 0.f, 1.f);
	if (Lost > 0.04f)
	{
		const bool bWas = S.Power < DmPowerMin;
		S.Power = FMath::Max(0.f, S.Power - Lost);
		if (C.bCorridor)
		{
			// the bus that runs along a corridor feeds the rooms off it: they are done at the end (bringing a room into play moves the books)
			for (const FAstraDmgLink& L : C.Links)
			{
				if (L.Kind == FAstraDmgLink::EKind::Door && !Out.Comps.Contains(L.To))
				{
					Feeds.Add(L.To);
				}
			}
		}
		if (S.Power < DmPowerMin && !bWas)
		{
			Out.bPower = true;
			++Stats.Conduits;
			Out.Lines.AddUnique(FString::Printf(TEXT("power lost in %s"), *Say(Comp)));
		}
	}
	// --- the room itself
	const float WasWreck = S.Wreck;
	S.Wreck = FMath::Clamp(S.Wreck + Energy / P.Hard, 0.f, 1.f);
	if (S.Wreck >= 1.f && WasWreck < 1.f)
	{
		Out.bWreck = true;
		++Stats.Wrecks;
		Out.Lines.AddUnique(FString::Printf(TEXT("%s is gutted"), *Say(Comp)));
		// everyone in it is lost with it
		TArray<FAstraDmgPerson> There;
		if (Hooks.PeopleIn)
		{
			Hooks.PeopleIn(C, There);
		}
		for (const FAstraDmgPerson& Pr : There)
		{
			Harm(Pr.Roster, Rng.FRand() < 0.75f * GDmCasualty, EAstraDmgHarm::Blast, &Out, C);
		}
	}
	for (const int32 F : Feeds)
	{
		FAstraDmgState& N = Get(F);
		N.Power = FMath::Max(0.f, N.Power - 0.35f * Lost);
	}
}

void FAstraDamageModel::BlastPeople(int32 Comp, float Energy, uint8 Type, const FVector& From, const FVector& To, FAstraImpactResult& Out)
{
	if (Energy < 3.f)
	{
		return;
	}
	const FAstraDmgComp& C = Map->Comps[Comp];
	if (Hooks.PeopleIn)
	{
		TArray<FAstraDmgPerson> There;
		Hooks.PeopleIn(C, There);
		Stats.PeopleNear += There.Num();
		if (There.Num() && !bImpactOccupied)
		{
			bImpactOccupied = true;
			++Stats.OccupiedBlows;
		}
		for (const FAstraDmgPerson& Pr : There)
		{
			const float R = DmDistToSegment(Pr.PosCm, From, To) / 100.f;          // metres from the path of the blow
			// two zones round the path of the blow, the deadly one inside the hurtful one; each grows with the square root of the energy (the spall of a bigger
			// blow flies further) and the odds fall away linearly to its edge: a small blow hurts only who is next to it, a big one a few dozen metres of crowd
			const float Reach = FMath::Sqrt(FMath::Clamp(Energy / 20.f, 0.25f, 4.f));
			const float Force = FMath::Clamp(Energy / 15.f, 0.f, 1.f);
			const float Kill = 0.7f * Force * FMath::Clamp(1.f - R / (DmKillRadius(Type) * Reach), 0.f, 1.f) * GDmCasualty;
			const float Hurt = 0.6f * Force * FMath::Clamp(1.f - R / (DmHurtRadius(Type) * Reach), 0.f, 1.f) * GDmCasualty;
			const float U = Rng.FRand();
			if (U < Kill)
			{
				Harm(Pr.Roster, true, EAstraDmgHarm::Blast, &Out, C);
			}
			else if (U < Kill + (1.f - Kill) * Hurt)
			{
				Harm(Pr.Roster, false, EAstraDmgHarm::Blast, &Out, C);
			}
		}
	}
	// the Captain, if they stand in it: a blow close by stuns before it kills
	if (Cap.Comp == Comp && GDmCaptain > 0.5f && Cap.State != FAstraDmgCaptain::EState::Dead)
	{
		const float R = DmDistToSegment(CapPos, From, To) / 100.f;
		const float Reach = FMath::Sqrt(FMath::Clamp(Energy / 20.f, 0.25f, 4.f));
		const float Force = FMath::Clamp(Energy / 15.f, 0.f, 1.f);
		Cap.Trauma += 14.f * Force * FMath::Clamp(1.f - R / (DmKillRadius(Type) * Reach), 0.f, 1.f) + 5.f * Force * FMath::Clamp(1.f - R / (DmHurtRadius(Type) * Reach), 0.f, 1.f);
		if (Cap.Cause.IsEmpty())
		{
			Cap.Cause = TEXT("a blast");
		}
	}
}

void FAstraDamageModel::Harm(int32 Roster, bool bKill, EAstraDmgHarm Cause, FAstraImpactResult* Out, const FAstraDmgComp& Where)
{
	if (!Hooks.Harm)
	{
		return;
	}
	const FString Who = Hooks.Harm(Roster, bKill, Cause);
	if (Who.IsEmpty())
	{
		return;
	}
	(bKill ? Stats.Killed : Stats.Wounded)++;
	if (Out)
	{
		(bKill ? Out->Killed : Out->Wounded)++;
		if (Out->People.Num() < 6)
		{
			Out->People.Add(Who);
		}
	}
}

// ================================================================================================================== time

void FAstraDamageModel::Tick(float Dt, TArray<FAstraDamage>& Incidents)
{
	if (!Map.IsValid() || Dt <= 0.f)
	{
		return;
	}
	Clock += Dt;
	Acc += Dt;
	for (int32 Steps = 0; Acc >= StepS && Steps < 8; ++Steps)
	{
		Step(StepS);
		Acc -= StepS;
		PeopleT += StepS;
		SyncT += StepS;
		SystemsT += StepS;
	}
	if (Acc > 2.f)
	{
		Acc = 0.f;                 // a long stall: the physics does not run to catch up
	}
	if (PeopleT >= 1.f)
	{
		StepPeople(PeopleT);
		PeopleT = 0.f;
	}
	if (SystemsT >= 0.5f)
	{
		RecomputePower();
		SystemsT = 0.f;
	}
	if (SyncT >= 0.5f)
	{
		SyncIncidents(Incidents);
		SyncT = 0.f;
	}
	if (bDoorsChanged && Clock - DoorsChangedAt > 1.5f)
	{
		bDoorsChanged = false;
		DoorsChangedAt = Clock;
		if (Hooks.PlanChanged)
		{
			Hooks.PlanChanged();
		}
	}
	Flush();
}

float FAstraDamageModel::Openness(const FAstraDmgLink& L, const FAstraDmgState& A, const FAstraDmgState* B) const
{
	switch (L.Kind)
	{
	case FAstraDmgLink::EKind::Open:  return 1.f;
	case FAstraDmgLink::EKind::Stair: return 0.5f;
	case FAstraDmgLink::EKind::Lift:  return 0.04f;
	case FAstraDmgLink::EKind::Blast: return (L.Door != INDEX_NONE && Sealed.Contains(L.Door)) ? 0.f : 1.f;
	default:
	{
		if (A.Wreck > 0.5f || (B && B->Wreck > 0.5f))
		{
			return 1.f;                                        // the door is buckled open
		}
		if (A.bLocked || (B && B->bLocked))
		{
			return 0.f;
		}
		const float Base = AlertNow >= 2 ? 0.015f : (AlertNow == 1 ? 0.04f : 0.08f);
		const float Traffic = 0.5f * (Map->ProfileOf(A.Comp).Traffic + Map->ProfileOf(L.To).Traffic);
		const float Team = (A.TeamT > 0.f || (B && B->TeamT > 0.f)) ? 0.35f : 0.f;
		return FMath::Clamp(Base * GDmDoorOpen * Traffic + Team, 0.f, 1.f);
	}
	}
}

namespace
{
	/** The share of the air the hole lets go: all of it, unless a field is holding (then what is over what it can hold). */
	float DmLeak(const FAstraDmgState& S)
	{
		if (S.Hole <= 0.005f)
		{
			return 0.f;
		}
		if (S.Field == FAstraDmgState::EField::Holding)
		{
			return FMath::Clamp(1.f - GDmFieldCap * FMath::Clamp(S.Power, 0.f, 1.f) / S.Hole, 0.f, 1.f);
		}
		return 1.f;
	}
}

void FAstraDamageModel::Step(float Dt)
{
	AlertNow = Hooks.Alert ? Hooks.Alert() : 0;
	StepFields(Dt);
	StepAir(Dt);
	StepFire(Dt);
	if (GDmDoctrine > 0.5f)
	{
		StepDoors(Dt);
	}
	// the calm ones leave the books
	TArray<int32, TInlineAllocator<32>> Gone;
	for (auto& KV : Active)
	{
		FAstraDmgState& S = KV.Value;
		S.TeamT = FMath::Max(0.f, S.TeamT - Dt);
		S.HitAge += Dt;
		// what is too small to be an incident mends by itself, or the ship would carry every scratch of every battle for good: the plating's sealant closes a
		// small hole (in about 25 s), the ring reroutes a little lost power (in about 40 s); what the teams are on, or wait for, is left to them
		if (!S.bGutted)
		{
			if (S.Hole > 0.f && S.Hole < DmHoleMin && S.BreachId == 0)
			{
				S.Hole = S.Hole - 0.005f * Dt < 0.005f ? 0.f : S.Hole - 0.005f * Dt;
			}
			if (S.Power < 1.f && S.Power >= DmPowerMin && S.ConduitId == 0 && S.Wreck < 1.f)
			{
				S.Power = FMath::Min(1.f, S.Power + 0.004f * Dt);
			}
		}
		S.Age = S.Calm() ? S.Age + Dt : 0.f;
		if (S.Age > 3.f)
		{
			Gone.Add(KV.Key);
		}
	}
	for (const int32 K : Gone)
	{
		Active.Remove(K);
	}
	Stats.MaxActive = FMath::Max(Stats.MaxActive, Active.Num());
}

void FAstraDamageModel::StepFields(float Dt)
{
	// A breached compartment wants a field; the ship's life support feeds them, the biggest holes first, and what it cannot feed goes without.
	TArray<TPair<float, int32>, TInlineAllocator<32>> Want;
	for (auto& KV : Active)
	{
		FAstraDmgState& S = KV.Value;
		if (S.Hole >= 0.01f && !S.bGutted)
		{
			Want.Add({S.Hole, KV.Key});
		}
		else
		{
			S.Field = FAstraDmgState::EField::Off;
			S.FieldStress = FMath::Max(0.f, S.FieldStress - 0.1f * Dt);
		}
	}
	Want.Sort([](const TPair<float, int32>& A, const TPair<float, int32>& B) { return A.Key > B.Key; });
	float Load = 0.f;
	int32 Fields = 0;
	for (const TPair<float, int32>& W : Want)
	{
		FAstraDmgState& S = *Active.Find(W.Value);
		const bool bPower = S.Power > 0.25f && GDmFields > 0.5f;
		const float Draw = 0.015f + 0.02f * FMath::Min(S.Hole, GDmFieldCap);
		const bool bBudget = Load + Draw <= 1.f;
		switch (S.Field)
		{
		case FAstraDmgState::EField::Off:
			if (bPower && bBudget)
			{
				S.Field = FAstraDmgState::EField::Forming;
				S.FieldT = 1.2f + 2.0f * (1.f - S.Power);
			}
			break;
		case FAstraDmgState::EField::Forming:
			if (!bPower || !bBudget)
			{
				S.Field = FAstraDmgState::EField::Off;
			}
			else if ((S.FieldT -= Dt) <= 0.f)
			{
				S.Field = FAstraDmgState::EField::Holding;
			}
			break;
		case FAstraDmgState::EField::Holding:
			if (!bPower || !bBudget)
			{
				S.Field = FAstraDmgState::EField::Failed;
				S.FieldT = 4.f;
				++Stats.FieldsFailed;
			}
			else
			{
				S.FieldStress = FMath::Max(0.f, S.FieldStress - 0.06f * Dt);
				if (S.FieldStress >= 1.f)
				{
					S.Field = FAstraDmgState::EField::Failed;
					S.FieldT = 6.f;
					S.FieldStress = 0.3f;
					++Stats.FieldsFailed;
					Report(FString::Printf(TEXT("damage report: the containment field in %s has failed — the compartment is venting"), *Say(W.Value)), S.Hole >= 0.4f);
				}
			}
			break;
		case FAstraDmgState::EField::Failed:
			if ((S.FieldT -= Dt) <= 0.f)
			{
				S.Field = FAstraDmgState::EField::Off;
			}
			break;
		}
		if (S.Field == FAstraDmgState::EField::Holding || S.Field == FAstraDmgState::EField::Forming)
		{
			Load += Draw;
			++Fields;
		}
	}
	PowerNow.FieldLoad = FMath::Min(1.f, Load);
	PowerNow.Fields = Fields;
	if (Load > 0.f && Hooks.AddHeat)
	{
		Hooks.AddHeat(0.02f * FMath::Min(1.f, Load) * Dt);       // the fields' emitters run warm
	}
}

void FAstraDamageModel::StepAir(float Dt)
{
	TArray<int32, TInlineAllocator<64>> Keys;
	Active.GetKeys(Keys);
	// what spreads wakes its neighbours: an open way to a compartment that is not in play brings it in (at its nominal state)
	TArray<int32, TInlineAllocator<16>> Wake;
	for (const int32 K : Keys)
	{
		const FAstraDmgState& S = Active[K];
		if (S.Air > 0.996f && S.Smoke < 0.02f && S.Fire < 0.03f)
		{
			continue;
		}
		for (const FAstraDmgLink& L : Map->Comps[K].Links)
		{
			if (!Active.Contains(L.To) && Openness(L, S, nullptr) > 0.001f)
			{
				Wake.AddUnique(L.To);
			}
		}
	}
	for (const int32 W : Wake)
	{
		Get(W).Age = 0.f;
	}
	Keys.Reset();
	Active.GetKeys(Keys);
	const float Plant = PowerNow.Factor[(int32)EAstraDmgCategory::LifeSupport];                    // the air plants refill what is let go (at a limited flow)
	TSet<int32> LeakingSections;                                                                  // deck * 256 + section: where air is going out now
	for (const int32 K : Keys)
	{
		if (DmLeak(Active[K]) > 0.f)
		{
			LeakingSections.Add(Map->Comps[K].Deck * 256 + (int32)Map->Comps[K].Section);
		}
	}
	// the holes
	for (const int32 K : Keys)
	{
		FAstraDmgState& S = Active[K];
		if (S.bGutted)
		{
			S.Air = FMath::Min(S.Air, 0.02f);                             // a gutted section has no air (and takes none: the pressure bulkheads hold it off)
			continue;
		}
		const float Leak = DmLeak(S);
		if (Leak > 0.f)
		{
			S.Air *= FMath::Exp(-GDmVent * S.Hole * Leak / Map->Comps[K].VolumeM3 * Dt);
		}
		else if (S.Air < 1.f)
		{
			// a plant gives what the deficit asks, up to a flow: a little while the section still leaks (its corridors cannot out-breathe a breach), a lot
			// once it is sealed and the air has to come back (the reserve tanks)
			const bool bLeaking = LeakingSections.Contains(Map->Comps[K].Deck * 256 + (int32)Map->Comps[K].Section);
			S.Air = FMath::Min(1.f, S.Air + Plant * FMath::Min(0.03f * (1.f - S.Air), (bLeaking ? 0.5f : 6.0f) / Map->Comps[K].VolumeM3) * Dt);
		}
	}
	// through the open ways: the pressure evens out (exponentially, so the step is as long as it likes)
	for (const int32 K : Keys)
	{
		FAstraDmgState& A = Active[K];
		const FAstraDmgComp& CA = Map->Comps[K];
		for (const FAstraDmgLink& L : CA.Links)
		{
			FAstraDmgState* B = Active.Find(L.To);
			if (!B || (L.To < K))
			{
				continue;                                  // (each pair once, from the lower index)
			}
			const float O = Openness(L, A, B);
			if (O < 0.001f || FMath::Abs(A.Air - B->Air) < 0.002f)
			{
				continue;
			}
			const FAstraDmgComp& CB = Map->Comps[L.To];
			const float K1 = GDmMix * L.AreaM2 * O * (1.f / CA.VolumeM3 + 1.f / CB.VolumeM3);
			const float Eq = (A.Air - B->Air) * CA.VolumeM3 * CB.VolumeM3 / (CA.VolumeM3 + CB.VolumeM3);
			const float Tr = Eq * (1.f - FMath::Exp(-K1 * Dt));
			A.Air -= Tr / CA.VolumeM3;
			B->Air += Tr / CB.VolumeM3;
		}
	}
	// the lockdown: a room that is losing its air shuts its doors (and opens them again when it has it back)
	for (const int32 K : Keys)
	{
		FAstraDmgState& S = Active[K];
		if (GDmDoctrine < 0.5f)
		{
			S.bLocked = false;
			continue;
		}
		if (!S.bLocked)
		{
			S.bLocked = !Map->Comps[K].bCorridor && (S.Air < 0.85f || (S.Hole > 0.05f && DmLeak(S) > 0.3f) || S.Fire > 0.5f);
		}
		else if (S.Air > 0.95f && S.Hole < 0.01f && S.Fire < 0.05f && S.Smoke < 0.25f && S.Wreck < 0.5f)
		{
			S.bLocked = false;
		}
	}
}

void FAstraDamageModel::StepFire(float Dt)
{
	TArray<int32, TInlineAllocator<64>> Keys;
	Active.GetKeys(Keys);
	struct FSeed { int32 Comp; float Amount; FVector At; };
	TArray<FSeed, TInlineAllocator<16>> Seeds;                     // fire that crosses to a neighbour: where to, how much, by which opening
	TArray<int32, TInlineAllocator<4>> Blasts;                     // magazines that go up this step
	float Burn = 0.f;
	for (const int32 K : Keys)
	{
		FAstraDmgState& S = Active[K];
		const FAstraDmgComp& C = Map->Comps[K];
		const FAstraDmgProfile& P = Map->ProfileOf(K);
		const float O2 = FMath::Clamp((S.Air - 0.2f) / 0.5f, 0.f, 1.f);
		if (S.bGutted)
		{
			continue;
		}
		if (S.Fire > 0.001f)
		{
			const bool bFuel = S.Fuel > 0.02f;
			const float Grow = 0.10f * P.Ignite * O2 * (bFuel ? 1.f : 0.f) * FMath::Sqrt(DmSize(C.VolumeM3));
			const float Decay = (1.f - O2) * 0.35f + (bFuel ? 0.f : 0.08f) + (S.Suppress > 0.f ? 0.30f : 0.f) + (S.TeamT > 0.f ? S.TeamFire : 0.f);
			S.Fire = FMath::Clamp(S.Fire + (Grow * (S.Fire + 0.015f) * (1.f - S.Fire) - Decay * S.Fire) * Dt, 0.f, 1.f);
			S.Fuel = FMath::Max(0.f, S.Fuel - S.Fire * Dt / P.Fuel);
			S.FireAge = S.Fire > 0.2f ? S.FireAge + Dt : 0.f;
			Burn += S.Fire * Dt;
			// the room loses air to a fire it is sealed with
			if (S.Air > 0.4f)
			{
				S.Air = FMath::Max(0.4f, S.Air - 0.004f * S.Fire * Dt);
			}
			if (S.Fire < 0.004f)
			{
				S.Fire = 0.f;
				S.FireAge = 0.f;
			}
			// it crosses through every way that is open
			if (S.Fire > 0.05f)
			{
				for (const FAstraDmgLink& L : C.Links)
				{
					const FAstraDmgState* B = Active.Find(L.To);
					const float O = Openness(L, S, B);
					if (O < 0.001f)
					{
						continue;
					}
					const FAstraDmgProfile& PB = Map->ProfileOf(L.To);
					const float Rate = S.Fire * O * 0.07f * PB.Ignite * GDmFire * ((B ? B->Fuel : 1.f) > 0.1f ? 1.f : 0.f);
					if (Rate * Dt > 0.0004f)
					{
						Seeds.Add({L.To, Rate * Dt, L.AtCm});
					}
				}
			}
			// fixed suppression: it discharges once the fire has stood a while (the people have had their warning), if the room has power. The machinery and the stores have
			// a gas system; the rest of the ship that has anything to burn (the cabins, the messes, the offices) has the sprinklers' mist, which comes a few seconds later and works the
			// same way (BATTAGLIA-3: a ship in a long fight is lit in dozens of rooms, and four teams cannot walk to every one: the ship's own systems carry what they can); the
			// corridors and shafts are bare and starve by themselves. A room is armed again when it has been calm a moment (it leaves the books).
			const bool bMist = GDmMist > 0.5f && !P.bSuppress && P.Fuel >= 60.f;
			if ((P.bSuppress || bMist) && !S.bSuppressSpent && S.Suppress <= 0.f && S.Fire > 0.35f && S.FireAge > (bMist ? 10.f : 6.f) && S.Power > 0.3f)
			{
				S.Suppress = 22.f;
				S.bSuppressSpent = true;
				++Stats.Suppressions;
				Report(FString::Printf(TEXT("damage report: fixed fire suppression has discharged in %s"), *Say(K)), false);
			}
			// a magazine that is let burn goes off
			if (P.bExplosive && S.Fire > 0.6f && S.FireAge > 9.f && S.Suppress <= 0.f && S.Wreck < 1.f)
			{
				Blasts.Add(K);                                  // (after the loop: a blast brings rooms into play)
				S.Fire = 0.f;
			}
		}
		{
			const float WasSuppressing = S.Suppress;
			S.Suppress = FMath::Max(0.f, S.Suppress - Dt);
			if (WasSuppressing > 0.f && S.Suppress <= 0.f && S.Fire < 0.35f)
			{
				S.Fire = 0.f;                                  // the agent has done its work: a fire that is small by then is out
				S.FireAge = 0.f;
			}
		}
		// smoke and heat: made by the fire, let out by a hole, diffusing through the open ways
		S.Smoke = FMath::Clamp(S.Smoke + (0.35f * S.Fire * DmSize(C.VolumeM3) - (0.012f + (S.Hole > 0.005f ? 0.25f * DmLeak(S) : 0.f)) * S.Smoke) * Dt, 0.f, 1.f);
		S.Heat = FMath::Clamp(S.Heat + (0.9f * S.Fire * DmSize(C.VolumeM3) - S.Heat) * (0.04f + 0.08f * (1.f - S.Air)) * Dt, 0.f, 1.f);
	}
	for (const int32 K : Blasts)
	{
		const FAstraDmgComp& C = Map->Comps[K];
		++Stats.Explosions;
		Report(FString::Printf(TEXT("damage report: the magazine at %s has gone up"), *Say(K)), true);
		FAstraImpactResult R;
		Deposit(K, 300.f, 2, C.Box.GetCenter(), FVector::ForwardVector, false, R);          // the room is gutted, and everyone in it
		BlastPeople(K, 90.f, 2, C.Box.GetCenter(), C.Box.GetCenter(), R);
		if (FAstraDmgState* Gone = Active.Find(K))
		{
			Gone->Fire = 0.f;                                                                // what there was to burn is burnt
			Gone->Fuel = 0.f;
			Gone->FireAge = 0.f;
		}
		for (const FAstraDmgLink& L : C.Links)
		{
			if (L.Kind != FAstraDmgLink::EKind::Blast)
			{
				Deposit(L.To, 22.f, 2, L.AtCm, FVector::ForwardVector, false, R);
				BlastPeople(L.To, 24.f, 2, C.Box.GetCenter(), L.AtCm, R);
			}
		}
		if (Hooks.StructureBurn)
		{
			Hooks.StructureBurn(110.f);
			Stats.StructureBurnt += 110.0;
		}
	}
	// the seeds: what crosses lights the next room (where it finds fuel and air)
	for (const FSeed& Sd : Seeds)
	{
		FAstraDmgState& B = Get(Sd.Comp);
		const float O2 = FMath::Clamp((B.Air - 0.2f) / 0.5f, 0.f, 1.f);
		if (O2 > 0.f && B.Wreck < 1.f)
		{
			const bool bWas = B.Fire >= DmFireMin;
			if (B.Fire < 0.02f)
			{
				B.FireAt = Sd.At;                                // the fire comes in by the opening it crossed
			}
			B.Fire = FMath::Clamp(B.Fire + Sd.Amount * O2 * (1.f - B.Fire) + 0.002f, 0.f, 1.f);
			if (!bWas && B.Fire >= DmFireMin)
			{
				++Stats.Fires;
				// told once for a stretch of corridor (a fire running along it is one report), room by room for the rooms
				const FAstraDmgComp& CB = Map->Comps[Sd.Comp];
				float& Told = SpreadTold.FindOrAdd(CB.Deck * 512 + (int32)CB.Section * 2 + (CB.bCorridor ? 1 : 0), -100.f);
				if (Clock - Told > (CB.bCorridor ? 30.f : 4.f))
				{
					Told = Clock;
					Report(FString::Printf(TEXT("damage report: the fire has spread to %s"), *Say(Sd.Comp)), DmIsVital(CB, Map->ProfileOf(Sd.Comp)));   // (told to the crew only where it matters: a system, a magazine, the bridge)
				}
			}
		}
	}
	// smoke through the open ways
	Keys.Reset();
	Active.GetKeys(Keys);
	for (const int32 K : Keys)
	{
		FAstraDmgState& A = Active[K];
		if (A.Smoke < 0.03f)
		{
			continue;
		}
		for (const FAstraDmgLink& L : Map->Comps[K].Links)
		{
			FAstraDmgState* B = Active.Find(L.To);
			if (!B || L.To < K)
			{
				continue;
			}
			const float O = Openness(L, A, B);
			if (O > 0.001f && FMath::Abs(A.Smoke - B->Smoke) > 0.003f)
			{
				const float Flow = FMath::Clamp(0.18f * O * Dt, 0.f, 0.5f) * (A.Smoke - B->Smoke);
				A.Smoke -= Flow;
				B->Smoke += Flow;
			}
		}
	}
	// the fires eat the hull's structure (what they have to eat is finite: the fuel of each room)
	if (Burn > 0.f && Hooks.StructureBurn)
	{
		const float Points = 0.045f * GDmBurn * Burn;
		Hooks.StructureBurn(Points);
		Stats.StructureBurnt += Points;
	}
}

void FAstraDamageModel::StepDoors(float Dt)
{
	// A section whose corridors are losing their air (or burning, or filling with smoke) is shut in: every pressure bulkhead at its ends closes, after
	// the moment of warning, and they open again once it is whole (and has had its air back for a while).
	TSet<int32> Bad;                                       // deck * 256 + section
	for (const auto& KV : Active)
	{
		const FAstraDmgState& S = KV.Value;
		const FAstraDmgComp& C = Map->Comps[KV.Key];
		if (C.bCorridor && (S.Air < 0.9f || S.Fire > 0.45f || S.Smoke > 0.6f))
		{
			Bad.Add(C.Deck * 256 + (int32)C.Section);
		}
	}
	TArray<int32, TInlineAllocator<8>> Isolate, ToSeal, ToOpen;
	for (const int32 K : Bad)
	{
		float& T = SectionTimer.FindOrAdd(K);
		T += Dt;
		if (T >= 2.5f)
		{
			Isolate.Add(K);
		}
	}
	for (auto It = SectionTimer.CreateIterator(); It; ++It)
	{
		if (!Bad.Contains(It.Key()))
		{
			It.RemoveCurrent();
		}
	}
	if (Isolate.Num())
	{
		for (const int32 D : Map->BlastDoors)
		{
			const FAstraDmgDoor& Door = Map->Doors[D];
			if (!Sealed.Contains(D) && (Isolate.Contains(Door.Deck * 256 + (int32)Door.SecAft) || Isolate.Contains(Door.Deck * 256 + (int32)Door.SecFwd)))
			{
				ToSeal.Add(D);
			}
		}
	}
	for (const int32 D : Sealed)
	{
		const FAstraDmgDoor& Door = Map->Doors[D];
		float& T = DoorTimer.FindOrAdd(D);
		const bool bBad = Bad.Contains(Door.Deck * 256 + (int32)Door.SecAft) || Bad.Contains(Door.Deck * 256 + (int32)Door.SecFwd);
		T = bBad ? 0.f : T + Dt;
		if (T >= 8.f)
		{
			ToOpen.Add(D);
		}
	}
	for (const int32 D : ToSeal)
	{
		Sealed.Add(D);
		DoorTimer.FindOrAdd(D) = 0.f;
		++Stats.DoorsSealed;
		bDoorsChanged = true;
		const FAstraDmgDoor& Door = Map->Doors[D];
		if (Hooks.SealDoor)
		{
			Hooks.SealDoor(Door.Id, true);
		}
	}
	if (ToSeal.Num())
	{
		TSet<int32> Told;
		for (const int32 D : ToSeal)
		{
			const FAstraDmgDoor& Door = Map->Doors[D];
			const int32 Key = Door.Deck * 256 + (int32)Door.SecAft;
			if (!Told.Contains(Key))
			{
				Told.Add(Key);
				Report(FString::Printf(TEXT("damage report: pressure bulkheads sealed on deck %d at the ends of the section losing its air (between sections %c and %c)"), (int32)Door.Deck, Door.SecAft, Door.SecFwd), false);
			}
		}
	}
	for (const int32 D : ToOpen)
	{
		Sealed.Remove(D);
		DoorTimer.FindOrAdd(D) = 0.f;
		bDoorsChanged = true;
		const FAstraDmgDoor& Door = Map->Doors[D];
		if (Hooks.SealDoor)
		{
			Hooks.SealDoor(Door.Id, false);
		}
	}
}

// ================================================================================================================== the people

void FAstraDamageModel::StepPeople(float Dt)
{
	if (!Hooks.PeopleIn)
	{
		return;
	}
	TArray<int32, TInlineAllocator<64>> Keys;
	Active.GetKeys(Keys);
	for (const int32 K : Keys)
	{
		FAstraDmgState* S = Active.Find(K);
		if (!S)
		{
			continue;
		}
		const bool bDanger = S->Air < 0.6f || S->Fire > 0.2f || S->Smoke > 0.5f || S->Heat > 0.45f;
		if (!bDanger && S->People.Num() == 0)
		{
			continue;
		}
		const FAstraDmgComp& C = Map->Comps[K];
		TArray<FAstraDmgPerson> There;
		Hooks.PeopleIn(C, There);
		if (bDanger)
		{
			for (const FAstraDmgPerson& P : There)
			{
				if (!P.bSuited && !S->People.Contains(P.Roster))
				{
					FAstraDmgExposure E;
					// how long they need to be out: a start, then the way to the nearest door at a run
					E.EscapeS = 1.5f + 2.5f * Rng.FRand() + ExitDistanceM(K, P.PosCm) / 3.0f + (P.bAtPost ? 3.f + 9.f * Rng.FRand() : 0.f);
					S->People.Add(P.Roster, E);
				}
			}
		}
		const float Hyp = FMath::Clamp((0.55f - S->Air) / 0.55f, 0.f, 1.f);
		const float Burn = FMath::Max(0.f, S->Fire * DmSize(C.VolumeM3) - 0.2f) * 1.2f + FMath::Max(0.f, S->Heat - 0.5f);
		const float Smk = FMath::Max(0.f, S->Smoke - 0.5f) * 0.7f;
		TArray<int32, TInlineAllocator<8>> Done;
		int32 Killed = 0, Wounded = 0, Rescued = 0;
		for (auto& KV : S->People)
		{
			const int32 Roster = KV.Key;
			FAstraDmgExposure& E = KV.Value;
			const FAstraDmgPerson* P = There.FindByPredicate([Roster](const FAstraDmgPerson& X) { return X.Roster == Roster; });
			if (!P || P->bSuited)
			{
				Done.Add(Roster);                                          // gone from it (walked on, harmed otherwise), or suited: a party at work
				continue;
			}
			E.Seconds += Dt;
			E.Hypoxia = Hyp > 0.f ? E.Hypoxia + Hyp * Dt : FMath::Max(0.f, E.Hypoxia - 0.6f * Dt);
			E.Burn = Burn > 0.f ? E.Burn + Burn * Dt : FMath::Max(0.f, E.Burn - 0.05f * Dt);
			E.Smoke = Smk > 0.f ? E.Smoke + Smk * Dt : FMath::Max(0.f, E.Smoke - 0.3f * Dt);
			const EAstraDmgHarm Cause = (E.Hypoxia >= E.Burn * 2.f && E.Hypoxia >= E.Smoke) ? EAstraDmgHarm::Decompression : (E.Burn >= E.Smoke * 0.4f ? EAstraDmgHarm::Fire : EAstraDmgHarm::Smoke);
			switch (E.State)
			{
			case FAstraDmgExposure::EState::Exposed:
				if (E.Hypoxia >= 12.f || E.Burn >= 6.f || E.Smoke >= 25.f)
				{
					E.State = FAstraDmgExposure::EState::Down;               // they cannot go on: whatever reaches them now reaches them there
				}
				else if (E.Seconds >= E.EscapeS)
				{
					E.State = FAstraDmgExposure::EState::Escaped;
					++Stats.Escaped;
					const float Dose = FMath::Max3(E.Hypoxia / 12.f, E.Burn / 6.f, E.Smoke / 25.f);
					if (Dose > 0.2f && Rng.FRand() < Dose)
					{
						Harm(Roster, false, Cause, nullptr, C);                  // out, but not unhurt
						++Wounded;
					}
				}
				break;
			case FAstraDmgExposure::EState::Down:
				if (E.Hypoxia >= 75.f || E.Burn >= 14.f || E.Smoke >= 60.f)
				{
					Harm(Roster, true, Cause, nullptr, C);
					++Killed;
					Done.Add(Roster);
				}
				else if (!bDanger || S->TeamT > 0.f)
				{
					Harm(Roster, false, Cause, nullptr, C);                      // got out in time (or were carried out): wounded, alive
					++Stats.Rescued;
					++Rescued;
					Done.Add(Roster);
				}
				break;
			case FAstraDmgExposure::EState::Escaped:
				if (!bDanger)
				{
					Done.Add(Roster);
				}
				break;
			}
		}
		for (const int32 R : Done)
		{
			S->People.Remove(R);
		}
		// a damage-control party at work is suited against the air and the smoke; the fire, the blasts and the failing bulkheads still find some of them
		for (const FAstraDmgPerson& P : There)
		{
			if (P.bSuited)
			{
				const float Risk = (S->Fire * DmSize(C.VolumeM3) > 0.5f ? 0.004f * S->Fire : 0.f) + (S->Air < 0.2f ? 0.0008f : 0.f);
				if (Risk > 0.f && Rng.FRand() < Risk * Dt * GDmCasualty)
				{
					Harm(P.Roster, Rng.FRand() < 0.15f, EAstraDmgHarm::Fire, nullptr, C);
					++Wounded;
				}
			}
		}
		if (!bDanger)
		{
			for (auto It = S->People.CreateIterator(); It; ++It)
			{
				if (It.Value().State == FAstraDmgExposure::EState::Escaped)
				{
					It.RemoveCurrent();
				}
			}
		}
		if (Killed || Wounded || Rescued)
		{
			const TCHAR* Cause = S->Air < 0.6f ? TEXT("the air gone") : (S->Fire > 0.2f ? TEXT("the fire") : TEXT("the smoke"));
			FString Text = FString::Printf(TEXT("damage report: casualties in %s (%s)"), *Say(K), Cause);
			if (Killed) { Text += FString::Printf(TEXT(", %d killed"), Killed); }
			if (Wounded) { Text += FString::Printf(TEXT(", %d wounded getting out"), Wounded); }
			if (Rescued) { Text += FString::Printf(TEXT(", %d carried out alive"), Rescued); }
			if (S->TeamT > 0.f) { Text += TEXT("; the damage-control team is there"); }
			Report(Text, Killed > 0 || Wounded + Rescued >= 3);          // (the dead and a handful hurt call the crew; one or two wounded getting out are in the log)
		}
	}
}

// ================================================================================================================== the Captain

void FAstraDamageModel::TickCaptain(float Dt, int32 Comp, const FVector& PosCm)
{
	if (!Map.IsValid() || Dt <= 0.f)
	{
		return;
	}
	Cap.Comp = Comp;
	CapPos = PosCm;
	if (Cap.State == FAstraDmgCaptain::EState::Dead)
	{
		return;
	}
	const FAstraDmgState* S = Comp != INDEX_NONE ? Active.Find(Comp) : nullptr;
	float Hyp = 0.f, Burn = 0.f, Smk = 0.f;
	if (S && GDmCaptain > 0.5f)
	{
		Hyp = FMath::Clamp((0.55f - S->Air) / 0.55f, 0.f, 1.f);
		Burn = FMath::Max(0.f, S->Fire * DmSize(Map->Comps[Comp].VolumeM3) - 0.2f) * 1.2f + FMath::Max(0.f, S->Heat - 0.5f);
		Smk = FMath::Max(0.f, S->Smoke - 0.5f) * 0.7f;
	}
	Cap.Hypoxia = Hyp > 0.f ? Cap.Hypoxia + Hyp * Dt : FMath::Max(0.f, Cap.Hypoxia - 0.6f * Dt);
	Cap.Burn = Burn > 0.f ? Cap.Burn + Burn * Dt : FMath::Max(0.f, Cap.Burn - 0.05f * Dt);
	Cap.Smoke = Smk > 0.f ? Cap.Smoke + Smk * Dt : FMath::Max(0.f, Cap.Smoke - 0.3f * Dt);
	Cap.Trauma = FMath::Max(0.f, Cap.Trauma - 0.05f * Dt);
	const bool bExposed = Hyp > 0.f || Burn > 0.f || Smk > 0.f;
	if (bExposed)
	{
		Cap.Cause = Hyp >= Burn * 2.f && Hyp >= Smk ? TEXT("the air gone") : (Burn >= Smk * 0.4f ? TEXT("the fire") : TEXT("the smoke"));
	}
	else if (Cap.Trauma < 0.5f)
	{
		Cap.Cause.Reset();
	}
	Cap.Peril = FMath::Clamp(FMath::Max3(Cap.Hypoxia / 12.f, Cap.Burn / 6.f, Cap.Smoke / 25.f), 0.f, 1.2f);
	Cap.Peril = FMath::Max(Cap.Peril, FMath::Clamp(Cap.Trauma / 12.f, 0.f, 1.2f));
	const bool bLethal = Cap.Hypoxia >= 75.f || Cap.Burn >= 14.f || Cap.Smoke >= 60.f;
	switch (Cap.State)
	{
	case FAstraDmgCaptain::EState::Well:
	case FAstraDmgCaptain::EState::Impaired:
		Cap.State = Cap.Peril >= 1.f ? FAstraDmgCaptain::EState::Down : (Cap.Peril > 0.35f ? FAstraDmgCaptain::EState::Impaired : FAstraDmgCaptain::EState::Well);
		Cap.DownS = 0.f;
		break;
	case FAstraDmgCaptain::EState::Down:
		Cap.DownS += Dt;
		if (bLethal)
		{
			Cap.State = FAstraDmgCaptain::EState::Dead;
			Cap.Why = FString::Printf(TEXT("died in %s of %s"), *Say(Comp), Cap.Cause.IsEmpty() ? TEXT("their injuries") : *Cap.Cause);
		}
		break;
	default:
		break;
	}
}

void FAstraDamageModel::CaptainWounded(float Trauma, const FString& Cause)
{
	if (Cap.State == FAstraDmgCaptain::EState::Dead || Trauma <= 0.f)
	{
		return;
	}
	Cap.Trauma = FMath::Max(Cap.Trauma, Trauma);
	if (Cap.Cause.IsEmpty() || Trauma >= 1.f)
	{
		Cap.Cause = Cause;
	}
}

void FAstraDamageModel::CaptainRescued()
{
	const int32 Comp = Cap.Comp;
	Cap = FAstraDmgCaptain();
	Cap.Comp = Comp;
}

// ================================================================================================================== the systems

void FAstraDamageModel::RecomputePower()
{
	constexpr int32 N = (int32)EAstraDmgSystem::Num;
	float Loss[N] = {};
	for (const auto& KV : Active)
	{
		const FAstraDmgState& S = KV.Value;
		const float L = FMath::Max(S.Wreck, 1.f - S.Power);
		if (L > 0.001f)
		{
			for (const uint8 Sys : Map->Comps[KV.Key].Systems)
			{
				Loss[Sys] += L;
			}
		}
	}
	float H[N];
	for (int32 i = 0; i < N; ++i)
	{
		const int32 Hosts = Map->Hosts[i].Num();
		// (a distribution that runs through hundreds of rooms loses more than its share when many of them are hurt: the ring is cut in places)
		const float K = i == (int32)EAstraDmgSystem::PowerBus ? 3.f : 1.f;
		H[i] = Hosts > 0 ? FMath::Clamp(1.f - K * Loss[i] / Hosts, 0.f, 1.f) : 1.f;
	}
	using Sy = EAstraDmgSystem;
	auto Set = [this](EAstraDmgCategory C, float V)
	{
		PowerNow.Factor[(int32)C] = GDmPowerFloor + (1.f - GDmPowerFloor) * FMath::Clamp(V, 0.f, 1.f);
	};
	Set(EAstraDmgCategory::Shields,     0.50f * H[(int32)Sy::Reactor] + 0.30f * H[(int32)Sy::Coolant] + 0.20f * H[(int32)Sy::PowerBus]);
	Set(EAstraDmgCategory::Weapons,     0.45f * H[(int32)Sy::Weapons] + 0.25f * H[(int32)Sy::Ordnance] + 0.30f * H[(int32)Sy::PowerBus]);
	Set(EAstraDmgCategory::Engines,     0.40f * H[(int32)Sy::Reactor] + 0.30f * H[(int32)Sy::Coolant] + 0.30f * H[(int32)Sy::PowerBus]);
	Set(EAstraDmgCategory::Sensors,     0.50f * H[(int32)Sy::Sensors] + 0.30f * H[(int32)Sy::DataTrunk] + 0.20f * H[(int32)Sy::PowerBus]);
	Set(EAstraDmgCategory::LifeSupport, 0.70f * H[(int32)Sy::LifeSupport] + 0.30f * H[(int32)Sy::PowerBus]);
	Set(EAstraDmgCategory::FlightDeck,  0.60f * H[(int32)Sy::Catapults] + 0.40f * H[(int32)Sy::PowerBus]);
	// the containment fields run on the life support's allocation first; what they draw beyond it comes out of the rest (a tenth of the fields' load)
	PowerNow.Factor[(int32)EAstraDmgCategory::LifeSupport] *= 1.f - 0.5f * PowerNow.FieldLoad;
	for (int32 c = 0; c < (int32)EAstraDmgCategory::Num; ++c)
	{
		if (c != (int32)EAstraDmgCategory::LifeSupport)
		{
			PowerNow.Factor[c] *= 1.f - 0.10f * PowerNow.FieldLoad;
		}
	}
}

// ================================================================================================================== the incidents

namespace
{
	int32 DmKindOf(const FString& K) { return K == TEXT("hull breach") ? 0 : (K == TEXT("fire") ? 1 : 2); }

	/** The power allocations a compartment's conduits feed, for the incident's words ("shields, engines"). */
	FString DmSystemsOf(const FAstraDamageMap& Map, int32 Comp)
	{
		TArray<FString, TInlineAllocator<6>> Out;
		auto Add = [&Out](const TCHAR* S) { Out.AddUnique(S); };
		for (const uint8 S : Map.Comps[Comp].Systems)
		{
			switch ((EAstraDmgSystem)S)
			{
			case EAstraDmgSystem::Reactor:
			case EAstraDmgSystem::Coolant:     Add(TEXT("shields")); Add(TEXT("engines")); break;
			case EAstraDmgSystem::Weapons:
			case EAstraDmgSystem::Ordnance:    Add(TEXT("weapons")); break;
			case EAstraDmgSystem::Sensors:
			case EAstraDmgSystem::DataTrunk:   Add(TEXT("sensors")); break;
			case EAstraDmgSystem::LifeSupport: Add(TEXT("life_support")); break;
			case EAstraDmgSystem::Catapults:   Add(TEXT("flight_deck")); break;
			case EAstraDmgSystem::Engines:     Add(TEXT("engines")); break;
			default: break;
			}
		}
		return FString::Join(Out, TEXT(", "));
	}
}

void FAstraDamageModel::CloseIncident(FAstraDamage& D, const TCHAR* How)
{
	const int32 Kind = DmKindOf(D.Kind);
	const TCHAR* Done = Kind == 1 ? TEXT("is out") : (Kind == 0 ? TEXT("is sealed") : TEXT("is repaired, power restored"));
	if (D.Team >= 0)
	{
		// a breach sealed is news (the air stops going); a fire out only where the fire mattered (a system, a magazine, the bridge); a conduit mended is in the log
		const bool bVital = Kind == 1 && Map.IsValid() && Map->Comps.IsValidIndex(D.Comp) && DmIsVital(Map->Comps[D.Comp], Map->ProfileOf(D.Comp));
		Report(FString::Printf(TEXT("damage control: the %s at %s %s (team %d free again)"), *D.Kind, *D.Where(), Done, D.Team + 1), Kind == 0 || bVital);
	}
	else if (Kind == 1)
	{
		Report(FString::Printf(TEXT("damage report: the fire at %s %s"), *D.Where(), How), false);
	}
}

void FAstraDamageModel::SyncIncidents(TArray<FAstraDamage>& Incidents)
{
	// the incidents that stand for something that is over go; the others are brought up to date
	for (int32 i = Incidents.Num() - 1; i >= 0; --i)
	{
		FAstraDamage& D = Incidents[i];
		if (D.Comp == INDEX_NONE)
		{
			continue;                                                    // the ship's own (a radiator wing)
		}
		FAstraDmgState* S = Active.Find(D.Comp);
		const int32 Kind = DmKindOf(D.Kind);
		const bool bAlive = S && (Kind == 0 ? S->Hole >= 0.02f : (Kind == 1 ? S->Fire >= 0.03f : S->Power < 0.97f));
		if (!bAlive)
		{
			if (S)
			{
				(Kind == 0 ? S->BreachId : (Kind == 1 ? S->FireId : S->ConduitId)) = 0;
			}
			CloseIncident(D, TEXT("has burned itself out"));
			Incidents.RemoveAt(i);
			continue;
		}
		D.Severity = SeverityOf(*S, Kind);
		if (Cap.Comp == D.Comp && Cap.State != FAstraDmgCaptain::EState::Well)
		{
			D.Severity = FMath::Min(1.f, D.Severity + 0.6f);              // the Captain is in it: it comes first
		}
		if (Kind == 0)
		{
			const TCHAR* F = S->Field == FAstraDmgState::EField::Holding ? TEXT("field holding") : (S->Field == FAstraDmgState::EField::Forming ? TEXT("field forming")
			                 : (S->Field == FAstraDmgState::EField::Failed ? TEXT("field failed") : TEXT("no field")));
			D.Note = FString::Printf(TEXT("%s, air %.0f %%, hole %.1f m2"), F, 100.f * S->Air, S->Hole);
		}
		else if (Kind == 1)
		{
			D.Note = FString::Printf(TEXT("fire %.0f %%%s%s"), 100.f * S->Fire, S->Smoke > 0.4f ? TEXT(", smoke") : TEXT(""), S->Suppress > 0.f ? TEXT(", suppression discharging") : TEXT(""));
		}
		else
		{
			D.Note = FString::Printf(TEXT("power %.0f %%"), 100.f * S->Power);
		}
	}
	// what has no incident and should: the worst first, into the free places; a full list gives its mildest unattended one up to a much worse
	struct FNeed { float Severity; int32 Comp; int32 Kind; };
	TArray<FNeed, TInlineAllocator<16>> Need;
	for (const auto& KV : Active)
	{
		const FAstraDmgState& S = KV.Value;
		if (S.bGutted)
		{
			continue;
		}
		if (S.BreachId == 0 && S.Hole >= DmHoleMin)
		{
			Need.Add({SeverityOf(S, 0) + 0.2f, KV.Key, 0});
		}
		if (S.FireId == 0 && S.Fire >= DmFireMin)
		{
			Need.Add({SeverityOf(S, 1) + 0.1f, KV.Key, 1});
		}
		if (S.ConduitId == 0 && S.Power < DmPowerMin)
		{
			Need.Add({SeverityOf(S, 2), KV.Key, 2});
		}
	}
	Need.Sort([](const FNeed& A, const FNeed& B) { return A.Severity > B.Severity; });
	for (const FNeed& N : Need)
	{
		if (Incidents.Num() >= MaxIncidents)
		{
			int32 Weakest = INDEX_NONE;
			for (int32 i = 0; i < Incidents.Num(); ++i)
			{
				const FAstraDamage& X = Incidents[i];
				if (X.Comp != INDEX_NONE && X.Team < 0 && (Weakest == INDEX_NONE || X.Severity < Incidents[Weakest].Severity))
				{
					Weakest = i;
				}
			}
			if (Weakest == INDEX_NONE || Incidents[Weakest].Severity + 0.25f >= N.Severity)
			{
				continue;
			}
			FAstraDamage& W = Incidents[Weakest];
			if (FAstraDmgState* WS = Active.Find(W.Comp))
			{
				(DmKindOf(W.Kind) == 0 ? WS->BreachId : (DmKindOf(W.Kind) == 1 ? WS->FireId : WS->ConduitId)) = 0;
			}
			Incidents.RemoveAt(Weakest);
		}
		FAstraDmgState* S = Active.Find(N.Comp);
		if (!S)
		{
			continue;
		}
		const FAstraDmgComp& C = Map->Comps[N.Comp];
		FAstraDamage D;
		D.Id = NextIncident++;
		D.Deck = C.Deck;
		D.Section = C.Section;
		D.Kind = N.Kind == 0 ? TEXT("hull breach") : (N.Kind == 1 ? TEXT("fire") : TEXT("conduit damage"));
		D.System = N.Kind == 2 ? DmSystemsOf(*Map, N.Comp) : FString();
		D.Comp = N.Comp;
		D.CompId = C.Id;
		D.Place = C.Name;
		D.Severity = FMath::Clamp(N.Severity, 0.f, 1.f);
		(N.Kind == 0 ? S->BreachId : (N.Kind == 1 ? S->FireId : S->ConduitId)) = D.Id;
		Incidents.Add(D);
	}
	Stats.MaxIncidents = FMath::Max(Stats.MaxIncidents, Incidents.Num());
}

float FAstraDamageModel::WorkSeconds(const FAstraDamage& D) const
{
	const int32 Kind = DmKindOf(D.Kind);
	const float Sev = FMath::Clamp(D.Severity, 0.f, 1.f);
	return Kind == 0 ? 14.f + 34.f * Sev : (Kind == 1 ? 8.f + 14.f * Sev : 10.f + 22.f * Sev);
}

bool FAstraDamageModel::Work(FAstraDamage& D, float Dt, TArray<FAstraDamage>& Incidents)
{
	ON_SCOPE_EXIT { Flush(); };
	FAstraDmgState* S = D.Comp != INDEX_NONE ? Active.Find(D.Comp) : nullptr;
	const int32 Kind = DmKindOf(D.Kind);
	auto Finish = [&]()
	{
		if (S)
		{
			(Kind == 0 ? S->BreachId : (Kind == 1 ? S->FireId : S->ConduitId)) = 0;
		}
		CloseIncident(D, TEXT("is out"));
		const int32 Id = D.Id;
		Incidents.RemoveAll([Id](const FAstraDamage& X) { return X.Id == Id; });
		return true;
	};
	if (!S)
	{
		return Finish();
	}
	S->TeamT = 1.0f;
	S->Age = 0.f;
	const float Now = Kind == 0 ? S->Hole : (Kind == 1 ? S->Fire : 1.f - S->Power);
	if (D.Baseline <= 0.f || Now > D.Baseline)
	{
		D.Baseline = FMath::Max(Now, 0.05f);                   // what is worked on grows if the damage does: the team's pace follows it
	}
	const float Rate = D.Baseline / FMath::Max(4.f, D.Work);
	if (Kind == 0)
	{
		S->Hole = FMath::Max(0.f, S->Hole - Rate * Dt);
		D.Progress = FMath::Clamp(1.f - S->Hole / D.Baseline, 0.f, 1.f);
		if (S->Hole <= 0.01f)
		{
			S->Hole = 0.f;
			S->Field = FAstraDmgState::EField::Off;
			return Finish();
		}
	}
	else if (Kind == 1)
	{
		// the team sprays: the fire is put out at a rate proportional to its strength (the fire itself fights back: it is not a fixed amount that is taken away)
		S->TeamFire = 0.25f;
		D.Progress = FMath::Clamp(1.f - S->Fire / D.Baseline, 0.f, 1.f);
		if (S->Fire <= 0.06f)
		{
			S->Fire = 0.f;
			S->bSuppressSpent = false;                         // the team rearms the room's suppression
			return Finish();
		}
	}
	else
	{
		S->Power = FMath::Min(1.f, S->Power + Rate * Dt);
		D.Progress = FMath::Clamp(1.f - (1.f - S->Power) / D.Baseline, 0.f, 1.f);
		if (S->Power >= 0.98f)
		{
			S->Power = 1.f;
			return Finish();
		}
	}
	return false;
}
