// ASTRA — the module's own tests of what the war leaves (AstraWrecks.h): the accounting of lifepods and survivors, determinism, the arithmetic of motion, the file, the limits, what the crew is told,
// the rescue. Plain C++ on plain records: no world, no engine objects, a second or two (tools/space.py test runs it: the commandlet's -wrecktest).

#include "AstraWrecks.h"
#include "AstraDerelicts.h"
#include "ASTRA.h"
#include "HAL/PlatformTime.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Policies/CondensedJsonPrintPolicy.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"

namespace AstraSpace
{
	namespace
	{
		struct FTestClass
		{
			const TCHAR* Key;
			float Radius;
			uint8 Faction;
		};
		const FTestClass TestClasses[] = {{TEXT("praetorian"), 460.f, 0}, {TEXT("vigilant"), 140.f, 0}, {TEXT("acheron"), 240.f, 1}, {TEXT("styx"), 130.f, 1}, {TEXT("lethe"), 90.f, 1}, {TEXT("freighter"), 170.f, 2}};

		FLoss TestLoss(int32 Id, FRandomStream& Rng, EHowLost How, bool bInside)
		{
			const FTestClass& C = TestClasses[Rng.RandRange(0, UE_ARRAY_COUNT(TestClasses) - 1)];
			FLoss L;
			L.ShipId = Id;
			L.Name = FString::Printf(TEXT("Test %d"), Id);
			L.Class = TEXT("test class");
			L.Contact = FString::Printf(TEXT("T-%d"), Id);
			L.KnownAs = FString::Printf(TEXT("Test %d (T-%d)"), Id, Id);
			L.HullMesh = FString::Printf(TEXT("SM_SHIP_TEST_%s"), C.Key);
			L.ClassKey = FName(C.Key);
			L.Faction = C.Faction;
			L.How = How;
			L.Section = (uint8)Rng.RandRange(0, 2);
			L.Pos = Rng.GetUnitVector() * Rng.FRandRange(1000.f, 30000.f);
			L.Vel = Rng.GetUnitVector() * Rng.FRandRange(0.f, 300.f);
			L.Att = FQuat(Rng.GetUnitVector(), Rng.FRandRange(0.f, 6.f));
			L.Radius = C.Radius;
			L.BoxMid = L.Pos + L.Att.RotateVector(FVector(C.Radius * 0.1, 0.0, 0.0));
			L.BoxHalf = FVector(C.Radius * 0.9, C.Radius * 0.22, C.Radius * 0.18);
			if (bInside)
			{
				const int32 N = FWrecks::ComplementOf(L.ClassKey, C.Radius, C.Faction);
				L.Aboard.bInside = true;
				L.Aboard.Complement = N;
				L.Aboard.Killed = Rng.RandRange(0, N / 3);
				L.Aboard.Alive = Rng.RandRange(N / 8, N - L.Aboard.Killed);
			}
			return L;
		}

		TArray<FPieceIn> TestPieces(const FLoss& L, FRandomStream& Rng)
		{
			TArray<FPieceIn> Out;
			if (L.How == EHowLost::Destroyed)
			{
				return Out;                                     // (the war's older explosion: no pieces)
			}
			for (int32 s = 0; s < 3; ++s)
			{
				FPieceIn P;
				P.Section = (uint8)s;
				P.Pivot = L.Pos + L.Att.RotateVector(FVector((1 - s) * L.Radius * 0.6, 0.0, 0.0));
				P.PivotLocal = FVector((1 - s) * L.Radius * 0.6, 0.0, 0.0);
				P.Vel = L.Vel + Rng.GetUnitVector() * 3.f;
				P.Att = L.Att;
				P.SpinAxis = Rng.GetUnitVector();
				P.SpinRate = Rng.FRandRange(0.008f, 0.05f);
				P.Radius = L.Radius * 0.4f;
				P.bReactor = L.How == EHowLost::Reactor;
				Out.Add(P);
			}
			return Out;
		}

		FString TestJsonText(FWrecks& W, double Now)
		{
			FString Text;
			const TSharedRef<TJsonWriter<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>> Wr = TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&Text);
			FJsonSerializer::Serialize(W.ToJson(Now), Wr);
			return Text;
		}
	}

	bool RunWreckTests(TArray<FString>& Fails, TArray<FString>& Notes)
	{
		auto Expect = [&Fails](bool bOk, const FString& What) { if (!bOk) { Fails.Add(What); } };
		FSkyFrame Frame;
		Frame.Origin = FVector(120000.0, 50000.0, 3000.0);
		Frame.Att = FRotationMatrix::MakeFromX(FVector(0.3, -0.8, 0.2).GetSafeNormal()).ToQuat();

		// ---- the accounting of people, for every way a ship goes and every class, with her inside and without
		{
			FRandomStream Rng(7);
			FWrecks W;
			int32 Checked = 0;
			int32 PodsBreakupPraetorian = 0, NBreakupPraetorian = 0, ReactorWithPods = 0, NReactor = 0;
			for (int32 i = 0; i < 1800; ++i)
			{
				const EHowLost How = (EHowLost)(i % 3);
				const bool bInside = (i / 3) % 2 == 0;
				const FLoss L = TestLoss(i + 1, Rng, How, bInside);
				W.AddLoss(TEXT("Aurelia"), L, TestPieces(L, Rng), 100.0 + i, 1000u + i, Frame);
				const FSite& S = W.Sites().Last();
				int32 Sum = 0;
				for (const FPodRec& P : S.Pods)
				{
					Sum += P.Survivors;
					Expect(P.Survivors >= 1, FString::Printf(TEXT("a lifepod with no survivor (site %d)"), S.Id));
					Expect(P.AirS > 0.4f * FWrecks::PodAirS && P.AirS <= FWrecks::PodAirS, TEXT("a lifepod's air outside its range"));
					Expect(!P.Pos0.ContainsNaN() && !P.Vel.ContainsNaN() && !P.Att0.ContainsNaN(), TEXT("a NaN in a lifepod"));
				}
				const FAboard& Ab = S.Aboard;
				Expect(Sum == Ab.Escaped, FString::Printf(TEXT("escaped %d is not the sum of the pods' survivors %d"), Ab.Escaped, Sum));
				Expect(Ab.Escaped <= FMath::FloorToInt(Ab.Alive * 0.6f), FString::Printf(TEXT("more than six in ten of %d got away: %d"), Ab.Alive, Ab.Escaped));
				Expect(Ab.Lost == Ab.Alive - Ab.Escaped, TEXT("lost + escaped is not alive"));
				Expect(S.Pods.Num() <= FWrecks::MaxPods, TEXT("too many pods"));
				Expect(S.Pieces.Num() >= 1, TEXT("a loss with no piece"));
				Expect(S.Field.Count >= 20 && S.Field.Count <= FWrecks::MaxChunks, TEXT("a field outside its limits"));
				Expect(Ab.Complement > 0 && Ab.Alive <= Ab.Complement, TEXT("alive aboard more than the class carries"));
				if (How == EHowLost::Reactor)
				{
					++NReactor;
					ReactorWithPods += S.Pods.Num() > 0 ? 1 : 0;
				}
				if (How == EHowLost::Breakup && L.ClassKey == FName(TEXT("praetorian")))
				{
					++NBreakupPraetorian;
					PodsBreakupPraetorian += S.Pods.Num();
				}
				++Checked;
				if (W.Sites().Num() >= FWrecks::MaxSites)
				{
					W.Reset();                                          // (the bench of numbers, not of the limit: that is below)
				}
			}
			Expect(NReactor > 0 && ReactorWithPods < NReactor * 0.6, FString::Printf(TEXT("a reactor breach lets lifepods away too often: %d of %d"), ReactorWithPods, NReactor));
			Expect(NBreakupPraetorian > 0 && (double)PodsBreakupPraetorian / NBreakupPraetorian >= 4.0, TEXT("a battleship breaking up launches too few lifepods"));
			Notes.Add(FString::Printf(TEXT("accounting: %d losses checked; a reactor breach lets pods away in %d of %d, a battleship's break-up launches %.1f pods on average"), Checked, ReactorWithPods, NReactor,
			                          NBreakupPraetorian ? (double)PodsBreakupPraetorian / NBreakupPraetorian : 0.0));
		}

		// ---- determinism: the same losses give the same records, byte for byte
		{
			FWrecks A, B;
			for (FWrecks* W : {&A, &B})
			{
				FRandomStream Rng(99);
				for (int32 i = 0; i < 40; ++i)
				{
					const FLoss L = TestLoss(i + 1, Rng, (EHowLost)(i % 3), i % 2 == 0);
					W->AddLoss(TEXT("Aurelia"), L, TestPieces(L, Rng), 50.0 + 10.0 * i, 77u + i, Frame);
				}
			}
			Expect(TestJsonText(A, 1000.0) == TestJsonText(B, 1000.0), TEXT("the same losses did not give the same records"));
			// and a field's chunks are a function of its seed only
			FSite S = A.Sites()[3];
			FSite S2 = A.Sites()[3];
			FWrecks::MakeDefs(S);
			FWrecks::MakeDefs(S2);
			bool bSame = S.Defs.Num() == S.Field.Count;
			for (int32 i = 0; bSame && i < S.Field.Count; ++i)
			{
				FChunk C1, C2;
				bSame = FWrecks::ChunkAt(S, i, 5000.0, C1) && FWrecks::ChunkAt(S2, i, 5000.0, C2) && C1.Pos.Equals(C2.Pos, 1e-6) && C1.Att.Equals(C2.Att, 1e-6);
			}
			Expect(bSame, TEXT("a field's chunks are not deterministic"));
		}

		// ---- the arithmetic of motion: a point and a velocity, an attitude and a spin; the debris stays within the radius its fastest chunk gives
		{
			FRandomStream Rng(5);
			FWrecks W;
			const FLoss L = TestLoss(1, Rng, EHowLost::Breakup, true);
			W.AddLoss(TEXT("Aurelia"), L, TestPieces(L, Rng), 1000.0, 5u, Frame);
			FSite S = W.Sites()[0];
			FWrecks::MakeDefs(S);
			for (const double Dt : {0.0, 10.0, 600.0, 3600.0, 36000.0, 360000.0})
			{
				const double Now = 1000.0 + Dt;
				for (const FPieceRec& P : S.Pieces)
				{
					const FVector Pos = FWrecks::PosAt(P, Now);
					Expect((Pos - (P.Pos0 + P.Vel * Dt)).IsNearlyZero(1e-6), TEXT("a piece's position is not its point plus its velocity"));
					const FQuat Q = FWrecks::AttAt(P, Now);
					Expect(FMath::Abs(Q.Size() - 1.0) < 1e-6 && !Q.ContainsNaN(), FString::Printf(TEXT("a piece's attitude is not a rotation after %.0f s"), Dt));
				}
				const double Rmax = FWrecks::FieldRadiusAt(S.Field, Now) + 1e-3;
				for (int32 i = 0; i < S.Field.Count; ++i)
				{
					FChunk C;
					Expect(FWrecks::ChunkAt(S, i, Now, C), TEXT("a chunk of a begun field is missing"));
					const FVector Mid = S.Field.Pos0 + S.Field.Vel * Dt;
					Expect(FVector::Dist(C.Pos, Mid) <= Rmax, FString::Printf(TEXT("a chunk is farther than the field's radius after %.0f s"), Dt));
					Expect(C.Ember >= 0.f && C.Ember <= 1.f, TEXT("an ember outside 0..1"));
				}
			}
			FChunk C0;
			Expect(!FWrecks::ChunkAt(S, 0, 900.0, C0), TEXT("a chunk of a field that has not begun"));
			Expect(!FWrecks::ChunkAt(S, S.Field.Count, 2000.0, C0), TEXT("a chunk past the end of a field"));
		}

		// ---- the file: every site comes back as it went in, and a save is small and cheap
		{
			FRandomStream Rng(11);
			FWrecks W;
			for (int32 i = 0; i < FWrecks::MaxSites - 1; ++i)
			{
				const FLoss L = TestLoss(i + 1, Rng, (EHowLost)(i % 3), true);
				FLoss L2 = L;
				for (int32 r = 0; r < (i >= FWrecks::MaxSites - 1 - FWrecks::RoomSites ? 60 : 0); ++r)       // (the rooms are kept for the newest sites)
				{
					FAboardRoom Room;
					Room.Comp = r * 3;
					Room.Air = Rng.FRand();
					Room.Fire = Rng.FRand() < 0.3f ? Rng.FRand() : 0.f;
					Room.bGutted = Rng.FRand() < 0.1f;
					L2.Aboard.Rooms.Add(Room);
				}
				W.AddLoss(i % 5 == 0 ? TEXT("Thule") : TEXT("Aurelia"), L2, TestPieces(L2, Rng), 100.0 + 20.0 * i, 31u + i, Frame);
			}
			const double Now = 5000.0;
			const double T0 = FPlatformTime::Seconds();
			const TSharedRef<FJsonObject> J = W.ToJson(Now);
			const double T1 = FPlatformTime::Seconds();
			const FString Text = TestJsonText(W, Now);
			const double T2 = FPlatformTime::Seconds();
			TSharedPtr<FJsonObject> Back;
			FWrecks R;
			double Clock = 0.0;
			const bool bRead = FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Back) && R.FromJson(Back, Clock);
			const double T3 = FPlatformTime::Seconds();
			Expect(bRead, TEXT("a save that does not read back"));
			Expect(FMath::Abs(Clock - Now) < 0.2, TEXT("the clock did not come back"));
			Expect(R.Sites().Num() == W.Sites().Num(), TEXT("not every site came back"));
			for (int32 i = 0; bRead && i < FMath::Min(R.Sites().Num(), W.Sites().Num()); ++i)
			{
				const FSite& X = R.Sites()[i];
				const FSite& Y = W.Sites()[i];
				Expect(X.Id == Y.Id && X.System == Y.System && X.Name == Y.Name && X.ClassKey == Y.ClassKey && X.ShipId == Y.ShipId && X.How == Y.How && X.Faction == Y.Faction, FString::Printf(TEXT("site %d: its identity changed in the file"), Y.Id));
				Expect(X.Pieces.Num() == Y.Pieces.Num() && X.Pods.Num() == Y.Pods.Num() && X.Field.Count == Y.Field.Count && X.Field.Seed == Y.Field.Seed, FString::Printf(TEXT("site %d: its parts changed in the file"), Y.Id));
				Expect(X.Aboard.Escaped == Y.Aboard.Escaped && X.Aboard.Lost == Y.Aboard.Lost && X.Aboard.Complement == Y.Aboard.Complement && X.Aboard.Killed == Y.Aboard.Killed, FString::Printf(TEXT("site %d: what was aboard changed in the file"), Y.Id));
				if (i >= W.Sites().Num() - FWrecks::RoomSites)
				{
					Expect(X.Aboard.Rooms.Num() == Y.Aboard.Rooms.Num(), FString::Printf(TEXT("site %d: its rooms changed in the file"), Y.Id));
				}
				for (int32 p = 0; p < FMath::Min(X.Pieces.Num(), Y.Pieces.Num()); ++p)
				{
					// where it is at some later time is what matters: the same to a few centimetres after an hour
					const double Later = 9000.0;
					Expect(FVector::Dist(FWrecks::PosAt(X.Pieces[p], Later), FWrecks::PosAt(Y.Pieces[p], Later)) < 1.0, FString::Printf(TEXT("site %d: a piece is elsewhere after the file"), Y.Id));
					Expect(FWrecks::AttAt(X.Pieces[p], Later).AngularDistance(FWrecks::AttAt(Y.Pieces[p], Later)) < 0.01, FString::Printf(TEXT("site %d: a piece lies otherwise after the file"), Y.Id));
				}
				for (int32 p = 0; p < FMath::Min(X.Pods.Num(), Y.Pods.Num()); ++p)
				{
					Expect(FVector::Dist(FWrecks::PosAt(X.Pods[p], 9000.0), FWrecks::PosAt(Y.Pods[p], 9000.0)) < 1.0 && X.Pods[p].Survivors == Y.Pods[p].Survivors, FString::Printf(TEXT("site %d: a lifepod changed in the file"), Y.Id));
				}
			}
			const double KbPerSite = Text.Len() / 1024.0 / FMath::Max(1, W.Sites().Num());
			Expect(Text.Len() < 150 * 1024, FString::Printf(TEXT("a save of %d sites is %.0f KB: too big"), W.Sites().Num(), Text.Len() / 1024.0));
			// a second save of what has not changed makes nothing again
			const double T4 = FPlatformTime::Seconds();
			W.ToJson(Now + 60.0);
			const double T5 = FPlatformTime::Seconds();
			Notes.Add(FString::Printf(TEXT("file: %d sites, %.1f KB (%.2f KB a site; the rooms of the newest only), objects %.2f ms the first time and %.3f ms when nothing changed, text %.2f ms, read back %.2f ms"), W.Sites().Num(),
			                          Text.Len() / 1024.0, KbPerSite, (T1 - T0) * 1000.0, (T5 - T4) * 1000.0, (T2 - T1) * 1000.0, (T3 - T2) * 1000.0));
			Expect((T5 - T4) * 1000.0 < 0.5, TEXT("a save of what has not changed is not cheap"));
		}

		// ---- the limit: the oldest without a living lifepod go first
		{
			FRandomStream Rng(21);
			FWrecks W;
			for (int32 i = 0; i < FWrecks::MaxSites * 2; ++i)
			{
				const FLoss L = TestLoss(i + 1, Rng, EHowLost::Breakup, true);
				W.AddLoss(TEXT("Aurelia"), L, TestPieces(L, Rng), 100.0 + 5.0 * i, 3u + i, Frame);
				Expect(W.Sites().Num() <= FWrecks::MaxSites, TEXT("more sites than the limit"));
			}
			Expect(W.Sites().Num() == FWrecks::MaxSites, FString::Printf(TEXT("%d sites kept, not the limit"), W.Sites().Num()));
			const FWreckStats St = W.Stats(TEXT("Aurelia"), 100.0 + 5.0 * FWrecks::MaxSites * 2);
			Expect(St.Pruned == FWrecks::MaxSites, FString::Printf(TEXT("%d pruned, not %d"), St.Pruned, FWrecks::MaxSites));
			// the newest are kept
			Expect(W.Sites().Last().ShipId == FWrecks::MaxSites * 2, TEXT("the newest loss was not kept"));
			// far and old: gone
			FWrecks Far;
			FLoss L = TestLoss(1, Rng, EHowLost::Breakup, true);
			Far.AddLoss(TEXT("Aurelia"), L, TestPieces(L, Rng), 0.0, 1u, Frame);
			Far.SitesMutable()[0].Pieces[0].Vel = FVector(2000.0, 0.0, 0.0);
			Far.SitesMutable()[0].Pieces[1].Vel = FVector(2000.0, 0.0, 0.0);
			Far.SitesMutable()[0].Pieces[2].Vel = FVector(2000.0, 0.0, 0.0);
			Far.Prune(8.0 * 3600.0);
			Expect(Far.Sites().Num() == 0, TEXT("a wreck a million kilometres out and hours old was kept"));
		}

		// ---- what the crew is told: the beacons, the silence, the close look
		{
			FRandomStream Rng(31);
			FWrecks W;
			FLoss L = TestLoss(1, Rng, EHowLost::Breakup, true);
			L.Aboard.Alive = 100;
			L.Aboard.Complement = 118;
			L.ClassKey = FName(TEXT("vigilant"));
			L.Radius = 140.f;
			L.Pos = FVector(10000.0, 0.0, 0.0);
			L.Vel = FVector::ZeroVector;
			const FSite& S0 = W.AddLoss(TEXT("Aurelia"), L, TestPieces(L, Rng), 100.0, 123u, Frame);
			const int32 Id = S0.Id;
			Expect(S0.Pods.Num() > 0, TEXT("the test loss launched no pod"));
			const FVector Aquila = L.Pos + FVector(0.0, 50000.0, 0.0);               // 50 km off
			TArray<FEvent> Ev;
			W.Think(TEXT("Aurelia"), 110.0, Frame, Aquila, nullptr, false, Ev);
			Expect(Ev.Num() == 0, TEXT("beacons heard before they started"));
			W.Think(TEXT("Aurelia"), 100.0 + 70.0, Frame, Aquila, nullptr, false, Ev);
			int32 Beacons = 0;
			for (const FEvent& E : Ev)
			{
				Beacons += E.Kind == EEventKind::Beacon ? 1 : 0;
				Expect(E.Text.StartsWith(TEXT("sensors: distress beacons")) && E.Text.Contains(S0.KnownAs) && E.bReport, TEXT("the beacon event is not in the sensors' words"));
				Expect(E.Text.Contains(FString::Printf(TEXT("%d %s lifepod"), S0.Pods.Num(), S0.Faction == 0 ? TEXT("ASTRA") : (S0.Faction == 1 ? TEXT("Mandate") : TEXT("civilian")))), FString::Printf(TEXT("the beacon event does not count all %d pods: %s"), S0.Pods.Num(), *E.Text));
			}
			Expect(Beacons == 1, FString::Printf(TEXT("%d beacon events, not one"), Beacons));
			Ev.Reset();
			W.Think(TEXT("Aurelia"), 100.0 + 75.0, Frame, Aquila, nullptr, false, Ev);
			Expect(Ev.Num() == 0, TEXT("the beacons were told twice"));
			// a rescue near the pods takes them
			TArray<FBeacon> Bs;
			W.Beacons(TEXT("Aurelia"), 100.0 + 80.0, Frame, Aquila, FWrecks::BeaconKm, Bs);
			Expect(Bs.Num() == S0.Pods.Num(), FString::Printf(TEXT("%d beacons for %d pods"), Bs.Num(), S0.Pods.Num()));
			for (int32 i = 1; i < Bs.Num(); ++i)
			{
				Expect(FVector::Dist(Bs[i - 1].Pos, Aquila) <= FVector::Dist(Bs[i].Pos, Aquila) + 1e-6, TEXT("the beacons are not nearest first"));
			}
			FRescued Got;
			if (Bs.Num())
			{
				Got = W.Recover(TEXT("Aurelia"), 100.0 + 80.0, Frame, Bs[0].Pos, 500.0, TEXT("the test"));
				Expect(Got.Pods >= 1 && Got.Survivors >= 1, TEXT("a rescue at a beacon took nobody"));
				const FRescued Again = W.Recover(TEXT("Aurelia"), 100.0 + 81.0, Frame, Bs[0].Pos, 500.0, TEXT("the test"));
				Expect(Again.Pods == 0, TEXT("a lifepod was taken twice"));
			}
			// the rest: air runs out, silence is told
			const double End = 100.0 + FWrecks::PodAirS + 60.0;
			Ev.Reset();
			W.Think(TEXT("Aurelia"), End, Frame, Aquila, nullptr, false, Ev);
			int32 Silent = 0;
			for (const FEvent& E : Ev)
			{
				Silent += E.Kind == EEventKind::BeaconSilent ? 1 : 0;
			}
			const bool bSomeLeft = (int32)Bs.Num() > Got.Pods;
			Expect(Silent == (bSomeLeft ? 1 : 0), FString::Printf(TEXT("%d silence events with %d pods left of %d"), Silent, (int32)Bs.Num() - Got.Pods, (int32)Bs.Num()));
			Ev.Reset();
			W.Think(TEXT("Aurelia"), End + 5.0, Frame, Aquila, nullptr, false, Ev);
			Expect(Ev.Num() == 0 || Ev[0].Kind == EEventKind::WreckLook, TEXT("the silence was told twice"));
			// a close look, once, and not for a wreck that is far
			FWrecks C;
			const FSite& S1 = C.AddLoss(TEXT("Aurelia"), L, TestPieces(L, Rng), 100.0, 124u, Frame);
			const FVector At = Frame.ToSystem(FWrecks::PosAt(S1.Pieces[1], 300.0));
			Ev.Reset();
			C.Think(TEXT("Aurelia"), 300.0, Frame, At + FVector(0.0, 0.0, 30000.0), nullptr, false, Ev);
			bool bLook = false;
			for (const FEvent& E : Ev) { bLook |= E.Kind == EEventKind::WreckLook; }
			Expect(!bLook, TEXT("a close look at a wreck 30 km off"));
			C.Think(TEXT("Aurelia"), 300.0, Frame, At + FVector(0.0, 4000.0, 0.0), nullptr, false, Ev);
			int32 Looks = 0;
			for (const FEvent& E : Ev) { Looks += E.Kind == EEventKind::WreckLook ? 1 : 0; if (E.Kind == EEventKind::WreckLook) { Expect(E.Text.Contains(S1.Name) && E.Text.Contains(S1.Class), TEXT("the close look does not name her")); } }
			Expect(Looks == 1, FString::Printf(TEXT("%d close looks, not one"), Looks));
			Ev.Reset();
			C.Think(TEXT("Aurelia"), 301.0, Frame, At + FVector(0.0, 4000.0, 0.0), nullptr, false, Ev);
			Expect(Ev.Num() == 0, TEXT("the close look was told twice"));
			// in the middle of a fight what is told is news and not a report (it does not take the crew's turn from the fight)
			FWrecks Fight;
			Fight.AddLoss(TEXT("Aurelia"), L, TestPieces(L, Rng), 100.0, 126u, Frame);
			Ev.Reset();
			Fight.Think(TEXT("Aurelia"), 300.0, Frame, At + FVector(0.0, 4000.0, 0.0), nullptr, true, Ev);
			Expect(Ev.Num() >= 1, TEXT("nothing was told in a fight"));
			for (const FEvent& E : Ev)
			{
				Expect(!E.bReport && !E.Text.IsEmpty(), TEXT("a wreck event took the crew's turn in a fight"));
			}
			// the Captain's Falcon looks too
			FWrecks F2;
			const FSite& S2 = F2.AddLoss(TEXT("Aurelia"), L, TestPieces(L, Rng), 100.0, 125u, Frame);
			const FVector At2 = Frame.ToSystem(FWrecks::PosAt(S2.Pieces[0], 300.0));
			const FVector Falcon = At2 + FVector(500.0, 0.0, 0.0);
			Ev.Reset();
			F2.Think(TEXT("Aurelia"), 300.0, Frame, At2 + FVector(0.0, 90000.0, 0.0), &Falcon, false, Ev);
			bool bFalcon = false;
			for (const FEvent& E : Ev) { bFalcon |= E.Kind == EEventKind::WreckLook; }
			Expect(bFalcon, TEXT("the Falcon's close look was not told"));
			(void)Id;
			const FString Text = W.Describe(W.Sites()[0], 1, 400.0);
			Expect(Text.Contains(TEXT("middle section")) && Text.Contains(TEXT("lost")) && Text.Contains(TEXT("hull broke apart")), FString::Printf(TEXT("the account of a wreck reads badly: %s"), *Text));
			Notes.Add(TEXT("what the crew is told: ") + Text);
		}

		// ---- the hand-over: the effects let a piece go from where they have it, and the record carries it on from there
		{
			FRandomStream Rng(41);
			FWrecks W;
			const FLoss L = TestLoss(1, Rng, EHowLost::Breakup, true);
			W.AddLoss(TEXT("Aurelia"), L, TestPieces(L, Rng), 0.0, 9u, Frame);
			FSite& S = W.SitesMutable()[0];
			FPieceRec& P = S.Pieces[0];
			Expect(P.bInFx, TEXT("a piece the effects made is not marked as theirs"));
			const double Now = 85.0;
			const FVector Pivot = Frame.ToSystem(FWrecks::PosAt(P, Now));
			const FQuat Att = Frame.ToSystem(FWrecks::AttAt(P, Now));
			const FVector Pos0 = P.Pos0;
			W.ReAnchor(S, P, Now, Frame, Pivot, Frame.DirToSystem(P.Vel), Att, Frame.DirToSystem(P.SpinAxis), P.SpinRate);
			Expect(!P.bInFx, TEXT("a piece handed over is still marked as the effects'"));
			Expect((FWrecks::PosAt(P, Now) - (Pos0 + P.Vel * Now)).Size() < 1e-6, TEXT("a piece jumped at the hand-over"));
			Expect(FWrecks::AttAt(P, Now).AngularDistance(Frame.FromSystem(Att)) < 1e-6, TEXT("a piece turned at the hand-over"));
			Expect(FWrecks::AttAt(P, Now + 1000.0).AngularDistance(FWrecks::AttAt(P, Now)) > 0.0, TEXT("a piece stopped turning"));
		}

		// ---- the tables that must agree with the plans (the rosters of the seven classes)
		{
			const FTestClass Classes[] = {{TEXT("praetorian"), 460.f, 0}, {TEXT("vigilant"), 140.f, 0}, {TEXT("acheron"), 240.f, 1}, {TEXT("styx"), 130.f, 1}, {TEXT("lethe"), 90.f, 1}, {TEXT("freighter"), 170.f, 2}, {TEXT("station"), 120.f, 0}};
			int32 Compared = 0;
			for (const FTestClass& C : Classes)
			{
				FString Text;
				const FString Path = FPaths::ProjectDir() / TEXT("data/ship/plans") / (FString(C.Key) + TEXT(".json"));
				if (!FFileHelper::LoadFileToString(Text, *Path))
				{
					continue;                                       // (a build without the plans: nothing to compare)
				}
				TSharedPtr<FJsonObject> J;
				const TSharedPtr<FJsonObject>* Roster = nullptr;
				double N = 0.0;
				if (FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), J) && J.IsValid() && J->TryGetObjectField(TEXT("roster"), Roster) && (*Roster)->TryGetNumberField(TEXT("complement"), N))
				{
					++Compared;
					Expect(FWrecks::ComplementOf(FName(C.Key), C.Radius, C.Faction) == (int32)N, FString::Printf(TEXT("the %s carries %d in her plan and %d in AstraWrecks.cpp"), C.Key, (int32)N, FWrecks::ComplementOf(FName(C.Key), C.Radius, C.Faction)));
				}
			}
			Notes.Add(FString::Printf(TEXT("the rosters agree with the plans: %d classes compared"), Compared));
		}

		// ---- a piece as a contact of the plot (docs/SPAZIO.md §3bis): its number, its name, its mesh, what an investigation learns by the range, and what the file keeps of what has been looked into
		{
			FRandomStream Rng(53);
			FWrecks W;
			TSet<FString> Ids;
			int32 Pieces = 0;
			for (int32 i = 0; i < 40; ++i)
			{
				FLoss L = TestLoss(i + 1, Rng, (EHowLost)(i % 3), (i % 2) == 0);
				if (i % 7 == 6)
				{
					L.Contact = FString();                          // (the odd ship that had no number)
					L.KnownAs = L.Name;
				}
				W.AddLoss(TEXT("Aurelia"), L, TestPieces(L, Rng), 100.0 + i, 500u + i, Frame);
				const FSite& S = W.Sites().Last();
				static const TCHAR* const Words[3] = {TEXT("bow section of "), TEXT("middle section of "), TEXT("stern section of ")};
				static const TCHAR* const Letters[3] = {TEXT("B"), TEXT("M"), TEXT("S")};
				for (int32 pi = 0; pi < S.Pieces.Num(); ++pi)
				{
					const uint8 Sec = S.Pieces[pi].Section;
					const FString Id = FWrecks::PieceContactId(S, pi), Name = FWrecks::PieceName(S, pi), Mesh = FWrecks::PieceMesh(S, pi);
					++Pieces;
					Expect(Id.StartsWith(TEXT("W-")) && Id.Len() >= 3 && !Ids.Contains(Id), FString::Printf(TEXT("the piece number %s of site %d is not a W number of its own"), *Id, S.Id));
					Ids.Add(Id);
					Expect(Sec < 3 ? (Id.EndsWith(Letters[Sec]) && Name.StartsWith(Words[Sec]) && Mesh.EndsWith(FString::Printf(TEXT("_Sec%s"), Sec == 0 ? TEXT("Bow") : (Sec == 1 ? TEXT("Mid") : TEXT("Stern")))))
					           : (Name.StartsWith(TEXT("wreck of ")) && Mesh == S.HullMesh && FChar::IsDigit(Id[Id.Len() - 1])),
					       FString::Printf(TEXT("a piece of site %d reads badly: %s | %s | %s"), S.Id, *Id, *Name, *Mesh));
					Expect(Name.Contains(S.Name) && !Name.Contains(TEXT("(T-")), FString::Printf(TEXT("the piece's name %s is not hers (%s) without a number"), *Name, *S.Name));
					Expect(S.Contact.IsEmpty() || Id.Contains(S.Contact.Mid(2)), FString::Printf(TEXT("%s does not carry the number of %s"), *Id, *S.Contact));
				}
			}
			Notes.Add(FString::Printf(TEXT("%d pieces of 40 losses: each its own W number, name and mesh"), Pieces));
			// the ranges a look is good for
			Expect(FWrecks::StageForRange(100.0) == 3 && FWrecks::StageForRange(799.0) == 3 && FWrecks::StageForRange(800.0) == 2 && FWrecks::StageForRange(3999.0) == 2 && FWrecks::StageForRange(4000.0) == 1 && FWrecks::StageForRange(60000.0) == 1,
			       TEXT("the ranges of an investigation's stages are not 800 m and 4 km"));
			// what each stage tells: the first look is the account of the piece, her rooms and her dead have her numbers
			FLoss L = TestLoss(900, Rng, EHowLost::Breakup, true);
			L.ClassKey = FName(TEXT("vigilant"));
			L.Aboard.Complement = 118;
			L.Aboard.Killed = 12;
			L.Aboard.Alive = 100;
			for (int32 k = 0; k < 5; ++k)
			{
				FAboardRoom R;
				R.Comp = k;
				R.bGutted = k < 2;
				R.Hole = k == 3 ? 0.8f : 0.f;
				R.Fire = k == 4 ? 0.5f : 0.f;
				R.Power = k == 1 ? 0.f : 1.f;
				L.Aboard.Rooms.Add(R);
			}
			L.Aboard.SealedDoors = {TEXT("d1"), TEXT("d2"), TEXT("d3")};
			const FSite& S = W.AddLoss(TEXT("Aurelia"), L, TestPieces(L, Rng), 100.0, 77u, Frame);
			const FString F1 = W.Findings(S, 2, 1, 400.0), F2 = W.Findings(S, 2, 2, 400.0), F3 = W.Findings(S, 2, 3, 400.0);
			Expect(F1 == W.Describe(S, 2, 400.0) && F1.Contains(TEXT("stern section")), FString::Printf(TEXT("the first look is not the account of the piece: %s"), *F1));
			Expect(F2.Contains(TEXT("open to space")) && F2.Contains(TEXT("2 gutted")) && F2.Contains(TEXT("1 burning")) && F2.Contains(TEXT("3 pressure bulkheads")) && F2.Contains(TEXT("30%")), FString::Printf(TEXT("her rooms are told badly: %s"), *F2));
			Expect(F3.Contains(TEXT("no life signs")) && F3.Contains(TEXT("12 lie dead")) && F3.Contains(FString::Printf(TEXT("%d got away"), S.Aboard.Escaped)) && F3.Contains(FString::Printf(TEXT("%d more were lost"), S.Aboard.Lost)), FString::Printf(TEXT("her dead are told badly: %s"), *F3));
			Expect(W.Status(S, 2, 400.0).StartsWith(TEXT("wreck: lost")) && W.Status(S, 2, 400.0).Contains(TEXT("no life signs")), TEXT("the status line of a piece is not a wreck's"));
			// a piece whose inside no sensor saw says so, and a whole hull has no torn end
			const FSite& Bare = W.AddLoss(TEXT("Aurelia"), TestLoss(901, Rng, EHowLost::Destroyed, false), TArray<FPieceIn>(), 100.0, 78u, Frame);
			Expect(W.Findings(Bare, 0, 2, 400.0).Contains(TEXT("burnt through")) && W.Findings(Bare, 0, 2, 400.0).Contains(TEXT("no sensor")), FString::Printf(TEXT("a hull with no inside is told badly: %s"), *W.Findings(Bare, 0, 2, 400.0)));
			// the table of shares agrees with the war's classes
			{
				const FString Path = FPaths::ProjectDir() / TEXT("data/war/classes.json");
				FString Text;
				TSharedPtr<FJsonObject> Root;
				const TArray<TSharedPtr<FJsonValue>>* List = nullptr;
				if (FFileHelper::LoadFileToString(Text, *Path) && FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Root) && Root.IsValid() && Root->TryGetArrayField(TEXT("classes"), List))
				{
					int32 Compared = 0;
					for (const TSharedPtr<FJsonValue>& V : *List)
					{
						const TSharedPtr<FJsonObject> O = V->AsObject();
						FString Key;
						const TArray<TSharedPtr<FJsonValue>>* Sec = nullptr;
						if (!O.IsValid() || !O->TryGetStringField(TEXT("key"), Key) || Key == TEXT("aquila") || !O->TryGetArrayField(TEXT("sections"), Sec) || Sec->Num() < 3)
						{
							continue;
						}
						++Compared;
						for (int32 k = 0; k < 3; ++k)
						{
							Expect(FMath::Abs(FWrecks::SectionShare(FName(*Key), (uint8)k) - (float)(*Sec)[k]->AsNumber()) < 1e-4f, FString::Printf(TEXT("the %s's section %d is %.2f of her in classes.json and %.2f in AstraWrecks.cpp"), *Key, k, (float)(*Sec)[k]->AsNumber(), FWrecks::SectionShare(FName(*Key), (uint8)k)));
						}
					}
					Notes.Add(FString::Printf(TEXT("the sections' shares agree with the war's classes: %d compared"), Compared));
				}
			}
			// a close look marks the piece as looked at; the file keeps it (and not the plot's id); a save from before the pieces were contacts reads with nothing looked at
			{
				FWrecks C;
				FLoss M = TestLoss(902, Rng, EHowLost::Breakup, true);
				M.Pos = FVector(1000.0, 0.0, 0.0);
				M.Vel = FVector::ZeroVector;
				const FSite& Cs = C.AddLoss(TEXT("Aurelia"), M, TestPieces(M, Rng), 100.0, 79u, Frame);
				const FVector Near = Frame.ToSystem(FWrecks::PosAt(Cs.Pieces[1], 200.0)) + FVector(500.0, 0.0, 0.0);
				TArray<FEvent> Ev;
				C.Think(TEXT("Aurelia"), 200.0, Frame, Near, nullptr, false, Ev);
				int32 Looked = 0;
				for (const FPieceRec& P : Cs.Pieces)
				{
					Looked += P.Seen >= 1 ? 1 : 0;
				}
				Expect(Looked == 1, FString::Printf(TEXT("%d pieces are marked as looked at after one close look, not one"), Looked));
				FSite& Mut = C.SitesMutable()[0];
				Mut.Pieces[0].Seen = 3;
				Mut.Pieces[1].Seen = 2;
				Mut.Pieces[2].Seen = 0;
				Mut.Pieces[2].PlotId = 42;
				Mut.bDirty = true;
				const FString Saved = TestJsonText(C, 200.0);
				TSharedPtr<FJsonObject> Back;
				FWrecks C2;
				double Clock = 0.0;
				Expect(FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Saved), Back) && C2.FromJson(Back, Clock), TEXT("the save with the pieces' marks does not read back"));
				if (C2.Sites().Num() == 1 && C2.Sites()[0].Pieces.Num() == 3)
				{
					const FSite& B2 = C2.Sites()[0];
					Expect(B2.Pieces[0].Seen == 3 && B2.Pieces[1].Seen == 2 && B2.Pieces[2].Seen == 0 && B2.Pieces[2].PlotId == -1, FString::Printf(TEXT("the marks came back as %d %d %d, plot id %d"), B2.Pieces[0].Seen, B2.Pieces[1].Seen, B2.Pieces[2].Seen, B2.Pieces[2].PlotId));
				}
				else
				{
					Expect(false, TEXT("the save of the pieces' marks has not got the site and its three pieces"));
				}
				// the old form: a piece's array without the mark
				TSharedPtr<FJsonObject> Old;
				Expect(FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Saved), Old), TEXT("the save does not parse"));
				if (Old.IsValid())
				{
					TArray<TSharedPtr<FJsonValue>> NewSites;
					for (const TSharedPtr<FJsonValue>& SV : Old->GetArrayField(TEXT("sites")))
					{
						const TSharedPtr<FJsonObject> SO = SV->AsObject();
						TArray<TSharedPtr<FJsonValue>> NewPieces;
						for (const TSharedPtr<FJsonValue>& PV : SO->GetArrayField(TEXT("pc")))
						{
							TArray<TSharedPtr<FJsonValue>> A = PV->AsArray();
							A.RemoveAt(A.Num() - 1);
							NewPieces.Add(MakeShared<FJsonValueArray>(A));
						}
						SO->SetArrayField(TEXT("pc"), NewPieces);
						NewSites.Add(MakeShared<FJsonValueObject>(SO));
					}
					Old->SetArrayField(TEXT("sites"), NewSites);
					FWrecks C3;
					Expect(C3.FromJson(Old, Clock) && C3.Sites().Num() == 1 && C3.Sites()[0].Pieces.Num() == 3 && C3.Sites()[0].Pieces[0].Seen == 0, TEXT("a save from before the pieces were contacts does not read"));
				}
			}
		}

		// ---- the hulks left behind (AstraDerelicts.h): the braking arithmetic, the records, the file
		RunDerelictTests(Fails, Notes);
		return Fails.Num() == 0;
	}
}
