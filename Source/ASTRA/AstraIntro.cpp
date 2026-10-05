// ASTRA — the introduction (AstraIntro.h): the shots, the script in the crew's languages, the narrator, the captions, Space and Esc.

#include "AstraIntro.h"
#include "ASTRA.h"
#include "ASTRAPlayerController.h"
#include "AstraBattleSubsystem.h"
#include "AstraDeckStreaming.h"
#include "AstraFonts.h"
#include "AstraHangar.h"
#include "AstraMindSubsystem.h"
#include "AstraSettings.h"
#include "Camera/CameraActor.h"
#include "Camera/CameraComponent.h"
#include "Camera/PlayerCameraManager.h"
#include "Containers/Ticker.h"
#include "AstraCampaign.h"
#include "Components/LightComponent.h"
#include "Engine/DirectionalLight.h"
#include "Engine/GameViewportClient.h"
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "Framework/Application/IInputProcessor.h"
#include "Framework/Application/SlateApplication.h"
#include "GameFramework/Pawn.h"
#include "Kismet/GameplayStatics.h"
#include "Misc/ConfigCacheIni.h"
#include "Styling/CoreStyle.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/SOverlay.h"
#include "Widgets/SWeakWidget.h"
#include "Widgets/Text/STextBlock.h"

namespace AstraIntro
{
	constexpr int32 NumLines = 12;
	// the narrator's lines, one a shot: who the player is, where, what they can do and how ({talk}, {orders}: the player's own keys). The crew
	// teaches the rest in play; the proper names stay in English in every language (docs/BIBBIA.md)
	struct FScript
	{
		const TCHAR* Lang;
		const TCHAR* Lines[NumLines];
	};
	const FScript Scripts[] = {
		{TEXT("en"), {
			TEXT("The year is 2491. The Kharon Mandate has come through the Janus Gate, and the Aurelia March is at war."),
			TEXT("You command the ASN Aquila, a carrier of the 7th Fleet: six hundred crew, and every one of them thinks for themselves."),
			TEXT("You do not fight alone. Allied captains sail with you, each with a ship and a mind of their own."),
			TEXT("This is your bridge. Hold {talk} and speak, in any language: your officers answer, act, and tell you what they did."),
			TEXT("Ferri flies the ship. Voss fights her: rails, lasers, missiles, shields. Give an order, or ask what they think."),
			TEXT("The main screen follows the battle by itself. Ask to see anything: a contact, the fleet, the Aquila from outside."),
			TEXT("The holo table is the war at a glance: blue is yours, red is the Mandate."),
			TEXT("Hold {orders} for the orders wheel. Tab raises your datapad, F1 shows every control."),
			TEXT("The Aquila is yours to walk: her decks, her lifts, the mess, the medbay."),
			TEXT("On the flight deck the Falcons wait. Your squadrons launch at your word, and you can fly one yourself."),
			TEXT("Everything the Mandate sends comes through the Gate. When it lights up, ships are coming."),
			TEXT("Hold the Gate and bring your people home. Commander Serra will brief you. Good hunting, Captain."),
		}},
		{TEXT("it"), {
			TEXT("È l'anno 2491. Il Kharon Mandate ha varcato il Janus Gate, e l'Aurelia March è in guerra."),
			TEXT("Sei al comando della ASN Aquila, una portaerei della Settima Flotta: seicento persone di equipaggio, e ognuna pensa con la propria testa."),
			TEXT("Accanto a te combattono i capitani alleati, ognuno con la sua nave e la sua testa."),
			TEXT("Questo è il tuo ponte. Tieni premuto {talk} e parla, in qualsiasi lingua: i tuoi ufficiali rispondono, agiscono e ti dicono cosa hanno fatto."),
			TEXT("Ferri pilota la nave. Voss la fa combattere: cannoni a rotaia, laser, missili, scudi. Dai un ordine, o chiedi cosa ne pensano."),
			TEXT("Lo schermo principale segue la battaglia da solo. Chiedi di vedere qualsiasi cosa: un contatto, la flotta, l'Aquila da fuori."),
			TEXT("Il tavolo olografico è la guerra a colpo d'occhio: in blu i tuoi, in rosso il Mandate."),
			TEXT("Tieni premuto {orders} per la ruota degli ordini. Tab alza il datapad, F1 mostra tutti i comandi."),
			TEXT("L'Aquila puoi percorrerla a piedi: i ponti, gli ascensori, la mensa, l'infermeria."),
			TEXT("Sul ponte di volo aspettano i Falcon. Le tue squadriglie decollano al tuo ordine, e puoi pilotarne uno anche tu."),
			TEXT("Tutto ciò che il Mandate manda passa dal Gate. Quando si accende, stanno arrivando navi."),
			TEXT("Tieni il Gate e riporta a casa la tua gente. Il comandante Serra ti farà il briefing. Buona caccia, Capitano."),
		}},
		{TEXT("es"), {
			TEXT("Es el año 2491. El Kharon Mandate ha cruzado el Janus Gate, y la Aurelia March está en guerra."),
			TEXT("Estás al mando de la ASN Aquila, un portanaves de la Séptima Flota: seiscientos tripulantes, y cada uno piensa por sí mismo."),
			TEXT("A tu lado combaten los capitanes aliados, cada uno con su nave y su propio criterio."),
			TEXT("Este es tu puente. Mantén pulsada {talk} y habla, en cualquier idioma: tus oficiales responden, actúan y te cuentan lo que han hecho."),
			TEXT("Ferri pilota la nave. Voss la hace combatir: cañones de riel, láseres, misiles, escudos. Da una orden, o pregunta qué opinan."),
			TEXT("La pantalla principal sigue la batalla por sí sola. Pide ver lo que quieras: un contacto, la flota, la Aquila desde fuera."),
			TEXT("La mesa holográfica es la guerra de un vistazo: en azul los tuyos, en rojo el Mandate."),
			TEXT("Mantén pulsada {orders} para la rueda de órdenes. Tab levanta tu datapad, F1 muestra todos los controles."),
			TEXT("La Aquila se recorre a pie: sus cubiertas, sus ascensores, el comedor, la enfermería."),
			TEXT("En la cubierta de vuelo esperan los Falcon. Tus escuadrillas despegan a tu orden, y también puedes pilotar uno."),
			TEXT("Todo lo que envía el Mandate llega por el Gate. Cuando se enciende, vienen naves."),
			TEXT("Defiende el Gate y lleva a tu gente a casa. La comandante Serra te dará las instrucciones. Buena caza, Capitán."),
		}},
		{TEXT("fr"), {
			TEXT("Nous sommes en 2491. Le Kharon Mandate a franchi le Janus Gate, et l'Aurelia March est en guerre."),
			TEXT("Vous commandez l'ASN Aquila, un porte-vaisseaux de la 7e Flotte : six cents membres d'équipage, et chacun pense par lui-même."),
			TEXT("À vos côtés se battent les capitaines alliés, chacun avec son vaisseau et sa propre tête."),
			TEXT("Voici votre passerelle. Maintenez {talk} et parlez, dans n'importe quelle langue : vos officiers répondent, agissent et vous disent ce qu'ils ont fait."),
			TEXT("Ferri pilote le vaisseau. Voss le fait combattre : canons à rail, lasers, missiles, boucliers. Donnez un ordre, ou demandez leur avis."),
			TEXT("L'écran principal suit la bataille tout seul. Demandez à voir n'importe quoi : un contact, la flotte, l'Aquila vue de l'extérieur."),
			TEXT("La table holographique, c'est la guerre d'un coup d'œil : en bleu les vôtres, en rouge le Mandate."),
			TEXT("Maintenez {orders} pour la roue des ordres. Tab lève votre datapad, F1 affiche toutes les commandes."),
			TEXT("L'Aquila se parcourt à pied : ses ponts, ses ascenseurs, le mess, l'infirmerie."),
			TEXT("Sur le pont d'envol, les Falcon attendent. Vos escadrilles décollent sur votre ordre, et vous pouvez en piloter un vous-même."),
			TEXT("Tout ce que le Mandate envoie passe par le Gate. Quand il s'allume, des vaisseaux arrivent."),
			TEXT("Tenez le Gate et ramenez les vôtres à la maison. Le commandant Serra va vous briefer. Bonne chasse, Capitaine."),
		}},
		{TEXT("de"), {
			TEXT("Wir schreiben das Jahr 2491. Das Kharon Mandate ist durch das Janus Gate gekommen, und die Aurelia March steht im Krieg."),
			TEXT("Sie kommandieren die ASN Aquila, einen Träger der 7. Flotte: sechshundert Besatzungsmitglieder, und jedes denkt selbst."),
			TEXT("An Ihrer Seite kämpfen verbündete Kapitäne, jeder mit eigenem Schiff und eigenem Kopf."),
			TEXT("Das ist Ihre Brücke. Halten Sie {talk} gedrückt und sprechen Sie, in jeder Sprache: Ihre Offiziere antworten, handeln und sagen Ihnen, was sie getan haben."),
			TEXT("Ferri fliegt das Schiff. Voss kämpft mit ihm: Railguns, Laser, Raketen, Schilde. Geben Sie einen Befehl, oder fragen Sie nach ihrer Meinung."),
			TEXT("Der Hauptschirm folgt der Schlacht von selbst. Verlangen Sie, was Sie sehen wollen: einen Kontakt, die Flotte, die Aquila von außen."),
			TEXT("Der Holotisch zeigt den Krieg auf einen Blick: Blau sind Ihre, Rot ist das Mandate."),
			TEXT("Halten Sie {orders} für das Befehlsrad. Tab hebt Ihr Datapad, F1 zeigt alle Steuerungen."),
			TEXT("Die Aquila gehört Ihnen, auch zu Fuß: ihre Decks, ihre Aufzüge, die Messe, die Krankenstation."),
			TEXT("Auf dem Flugdeck warten die Falcons. Ihre Staffeln starten auf Ihr Wort, und Sie können selbst einen fliegen."),
			TEXT("Alles, was das Mandate schickt, kommt durch das Gate. Wenn es aufleuchtet, kommen Schiffe."),
			TEXT("Halten Sie das Gate und bringen Sie Ihre Leute nach Hause. Commander Serra wird Sie einweisen. Gute Jagd, Captain."),
		}},
		{TEXT("pt"), {
			TEXT("É o ano de 2491. O Kharon Mandate atravessou o Janus Gate, e a Aurelia March está em guerra."),
			TEXT("Você comanda a ASN Aquila, um porta-naves da 7ª Frota: seiscentos tripulantes, e cada um pensa por si."),
			TEXT("Ao seu lado lutam os capitães aliados, cada um com a sua nave e a sua própria cabeça."),
			TEXT("Esta é a sua ponte. Segure {talk} e fale, em qualquer língua: os seus oficiais respondem, agem e dizem o que fizeram."),
			TEXT("Ferri pilota a nave. Voss a faz combater: canhões de trilho, lasers, mísseis, escudos. Dê uma ordem, ou pergunte o que eles acham."),
			TEXT("A tela principal acompanha a batalha sozinha. Peça para ver o que quiser: um contato, a frota, a Aquila vista de fora."),
			TEXT("A mesa holográfica é a guerra num relance: em azul os seus, em vermelho o Mandate."),
			TEXT("Segure {orders} para a roda de ordens. Tab levanta o seu datapad, F1 mostra todos os controles."),
			TEXT("A Aquila pode ser percorrida a pé: os conveses, os elevadores, o refeitório, a enfermaria."),
			TEXT("No convés de voo esperam os Falcon. Os seus esquadrões decolam à sua ordem, e você pode pilotar um."),
			TEXT("Tudo o que o Mandate envia passa pelo Gate. Quando ele se acende, há naves chegando."),
			TEXT("Defenda o Gate e leve a sua gente para casa. A comandante Serra vai passar as instruções. Boa caçada, Capitão."),
		}},
		{TEXT("nl"), {
			TEXT("Het is het jaar 2491. Het Kharon Mandate is door de Janus Gate gekomen, en de Aurelia March is in oorlog."),
			TEXT("U voert het bevel over de ASN Aquila, een drager van de 7e Vloot: zeshonderd bemanningsleden, en ieder denkt zelf na."),
			TEXT("Naast u vechten bondgenoten, elke kapitein met een eigen schip en een eigen hoofd."),
			TEXT("Dit is uw brug. Houd {talk} ingedrukt en spreek, in elke taal: uw officieren antwoorden, handelen en vertellen wat ze gedaan hebben."),
			TEXT("Ferri vliegt het schip. Voss vecht ermee: railguns, lasers, raketten, schilden. Geef een bevel, of vraag wat ze ervan vinden."),
			TEXT("Het hoofdscherm volgt de strijd vanzelf. Vraag om alles wat u wilt zien: een contact, de vloot, de Aquila van buitenaf."),
			TEXT("De holotafel is de oorlog in één oogopslag: blauw is van u, rood is het Mandate."),
			TEXT("Houd {orders} ingedrukt voor het bevelenwiel. Tab heft uw datapad, F1 toont alle bediening."),
			TEXT("De Aquila kunt u te voet verkennen: haar dekken, haar liften, de messroom, de ziekenboeg."),
			TEXT("Op het vliegdek wachten de Falcons. Uw squadrons stijgen op uw woord op, en u kunt er zelf een vliegen."),
			TEXT("Alles wat het Mandate stuurt, komt door de Gate. Als hij oplicht, komen er schepen."),
			TEXT("Houd de Gate en breng uw mensen thuis. Commandant Serra geeft u de briefing. Goede jacht, Kapitein."),
		}},
	};

	const FScript& ScriptFor(const FString& Lang)
	{
		for (const FScript& S : Scripts)
		{
			if (Lang == S.Lang)
			{
				return S;
			}
		}
		return Scripts[0];
	}

	FString LangOf()
	{
		const FString& L = FAstraSettings::Get().Language;
		return &ScriptFor(L) == &Scripts[0] ? FString(TEXT("en")) : L;
	}

	/** The way the sun's light travels (the brightest directional light of the level). */
	bool SunDir(const UWorld* W, FVector& Out)
	{
		float Best = -1.f;
		for (TActorIterator<ADirectionalLight> It(W); It; ++It)
		{
			const ULightComponent* L = It->GetLightComponent();
			if (L && L->IsVisible() && L->Intensity > Best)
			{
				Best = L->Intensity;
				Out = It->GetActorForwardVector();
			}
		}
		return Best > 0.f;
	}

	const FLinearColor Ink(0.88f, 0.92f, 0.97f);
	const FLinearColor Dim(0.45f, 0.52f, 0.6f);
	constexpr float BarFill = 0.105f;     // the letterbox: a tenth of the screen above and below
	constexpr float FadeS = 0.45f;        // the dip to black between shots
	constexpr float ReturnS = 1.1f;       // the last shot's blend back to the Captain's own eyes
}

/** Space, Enter or a click: the next shot; Esc: the whole tour. Every other key waits for the war (the tour is not the game); the system's own
 *  shortcuts (Cmd+Q, Alt+Tab) pass. The requests are taken by the next tick: nothing is torn down inside Slate's own loop of processors. */
class FAstraIntroKeys : public IInputProcessor
{
public:
	explicit FAstraIntroKeys(UAstraIntroSubsystem* InIntro) : Intro(InIntro) {}

	virtual void Tick(const float DeltaTime, FSlateApplication& App, TSharedRef<ICursor> Cursor) override {}

	virtual bool HandleKeyDownEvent(FSlateApplication& App, const FKeyEvent& E) override
	{
		UAstraIntroSubsystem* I = Intro.Get();
		if (!I || !I->IsPlaying() || E.IsCommandDown() || E.IsControlDown() || E.IsAltDown())
		{
			return false;
		}
		const FKey K = E.GetKey();
		if (!E.IsRepeat())
		{
			if (K == EKeys::Escape || K == EKeys::Gamepad_Special_Right || K == EKeys::Gamepad_FaceButton_Right)
			{
				I->Skip();
			}
			else if (K == EKeys::SpaceBar || K == EKeys::Enter || K == EKeys::Right || K == EKeys::Gamepad_FaceButton_Bottom)
			{
				I->Next();
			}
		}
		return true;
	}

	virtual bool HandleMouseButtonDownEvent(FSlateApplication& App, const FPointerEvent& E) override
	{
		UAstraIntroSubsystem* I = Intro.Get();
		if (!I || !I->IsPlaying())
		{
			return false;
		}
		if (E.GetEffectingButton() == EKeys::LeftMouseButton)
		{
			I->Next();
		}
		return true;
	}

	virtual const TCHAR* GetDebugName() const override { return TEXT("AstraIntro"); }

private:
	TWeakObjectPtr<UAstraIntroSubsystem> Intro;
};

namespace
{
	// testing: the tour now (the console), or at the start (-astra_intro: AstraCampaign.cpp)
	FAutoConsoleCommandWithWorld CmdIntro(TEXT("astra.intro"), TEXT("Play the introduction's tour now"),
		FConsoleCommandWithWorldDelegate::CreateLambda([](UWorld* World)
		{
			if (UAstraCampaignSubsystem* C = World ? World->GetSubsystem<UAstraCampaignSubsystem>() : nullptr; C && !C->IsStarted())
			{
				C->PlayIntro();                                    // (from the title menu, and back to it)
			}
			else if (UAstraIntroSubsystem* I = World ? World->GetSubsystem<UAstraIntroSubsystem>() : nullptr)
			{
				I->Play([]() {});
			}
		}));
	FAutoConsoleCommandWithWorld CmdIntroNext(TEXT("astra.intro.next"), TEXT("Testing: the introduction's next shot (Space)"),
		FConsoleCommandWithWorldDelegate::CreateLambda([](UWorld* World)
		{
			if (UAstraIntroSubsystem* I = World ? World->GetSubsystem<UAstraIntroSubsystem>() : nullptr)
			{
				I->Next();
			}
		}));
	FAutoConsoleCommandWithWorld CmdIntroSkip(TEXT("astra.intro.skip"), TEXT("Testing: skip the introduction (Esc)"),
		FConsoleCommandWithWorldDelegate::CreateLambda([](UWorld* World)
		{
			if (UAstraIntroSubsystem* I = World ? World->GetSubsystem<UAstraIntroSubsystem>() : nullptr)
			{
				I->Skip();
			}
		}));
}

// ---------------------------------------------------------------------------------------------------- the photo camera (testing, screenshots)
namespace AstraPhotoCam
{
	// a free camera for pictures of the game (the README's, a bug's): placed in the world, aimed at a point, or framing a ship of the battle and
	// following it as it moves; the Captain's own eyes come back with `astra.cam off`
	TWeakObjectPtr<ACameraActor> Cam;
	FString Follow;                       // a contact id ("aquila", "T-41") the camera keeps framing; empty: it stays where it was put
	double Az = 0.0, El = 0.0, Dist = 3.0;
	FTSTicker::FDelegateHandle Tick;

	ACameraActor* Ensure(UWorld* W, float Fov)
	{
		if (!Cam.IsValid() || Cam->GetWorld() != W)
		{
			FActorSpawnParameters SP;
			SP.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
			SP.ObjectFlags |= RF_Transient;
			Cam = W->SpawnActor<ACameraActor>(FVector::ZeroVector, FRotator::ZeroRotator, SP);
			if (Cam.IsValid())
			{
				Cam->GetCameraComponent()->bConstrainAspectRatio = false;
			}
		}
		if (Cam.IsValid())
		{
			Cam->GetCameraComponent()->SetFieldOfView(Fov);
			if (APlayerController* PC = UGameplayStatics::GetPlayerController(W, 0); PC && PC->GetViewTarget() != Cam.Get())
			{
				PC->SetViewTarget(Cam.Get());
			}
		}
		return Cam.Get();
	}

	bool Frame(UWorld* W)
	{
		const UAstraBattleSubsystem* B = W ? W->GetSubsystem<UAstraBattleSubsystem>() : nullptr;
		FVector P;
		FQuat Q;
		float Size = 0.f;
		if (!Cam.IsValid() || !B || !B->GetContactView(Follow, P, Q, Size))
		{
			return false;
		}
		// azimuth round the ship from its bow (to starboard), elevation above its deck, distance in the ship's sizes
		const FVector Dir = Q.RotateVector(FRotator(El, Az, 0.0).Vector());
		const FVector At = P + Dir * Size * Dist;
		Cam->SetActorLocationAndRotation(At, (P - At).Rotation());
		return true;
	}

	void Off(UWorld* W)
	{
		Follow.Reset();
		if (Tick.IsValid())
		{
			FTSTicker::GetCoreTicker().RemoveTicker(Tick);
			Tick.Reset();
		}
		if (APlayerController* PC = W ? UGameplayStatics::GetPlayerController(W, 0) : nullptr; PC && PC->GetPawn())
		{
			PC->SetViewTarget(PC->GetPawn());
		}
		if (Cam.IsValid())
		{
			Cam->Destroy();
		}
		Cam.Reset();
	}

	FAutoConsoleCommandWithWorldAndArgs CmdCam(TEXT("astra.cam"),
		TEXT("A free camera (screenshots): astra.cam at <x y z> <yaw pitch> [fov] | look <x y z> <tx ty tz> [fov] | ship <contact|aquila> <azimuth elevation sizes> [fov] | off"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& A, UWorld* W)
		{
			if (!W || A.Num() == 0 || A[0] == TEXT("off"))
			{
				Off(W);
				return;
			}
			const auto F = [&A](int32 i, double Def) { return A.IsValidIndex(i) ? FCString::Atod(*A[i]) : Def; };
			if (A[0] == TEXT("at") && A.Num() >= 6)
			{
				Follow.Reset();
				if (ACameraActor* C = Ensure(W, (float)F(6, 60.0)))
				{
					C->SetActorLocationAndRotation(FVector(F(1, 0), F(2, 0), F(3, 0)), FRotator(F(5, 0), F(4, 0), 0.0));
				}
			}
			else if (A[0] == TEXT("look") && A.Num() >= 7)
			{
				Follow.Reset();
				if (ACameraActor* C = Ensure(W, (float)F(7, 60.0)))
				{
					const FVector From(F(1, 0), F(2, 0), F(3, 0)), To(F(4, 0), F(5, 0), F(6, 0));
					C->SetActorLocationAndRotation(From, (To - From).Rotation());
				}
			}
			else if (A[0] == TEXT("ship") && A.Num() >= 2)
			{
				Follow = A[1];
				Az = F(2, 35.0);
				El = F(3, 12.0);
				Dist = F(4, 3.0);
				Ensure(W, (float)F(5, 40.0));
				if (!Frame(W))
				{
					UE_LOG(LogASTRA, Warning, TEXT("[Cam] no ship %s"), *Follow);
					Off(W);
					return;
				}
				if (!Tick.IsValid())
				{
					TWeakObjectPtr<UWorld> WW(W);
					Tick = FTSTicker::GetCoreTicker().AddTicker(FTickerDelegate::CreateLambda([WW](float)
					{
						if (!WW.IsValid() || Follow.IsEmpty() || !Frame(WW.Get()))
						{
							Tick.Reset();
							return false;
						}
						return true;
					}));
				}
			}
		}));
}

bool UAstraIntroSubsystem::ShouldCreateSubsystem(UObject* Outer) const
{
	const UWorld* World = Cast<UWorld>(Outer);
	return World && (World->WorldType == EWorldType::Game || World->WorldType == EWorldType::PIE);
}

void UAstraIntroSubsystem::Deinitialize()
{
	Teardown(true);                  // (the level went away under the tour: nothing of it may stay on the viewport or in Slate's processors)
	OnDone = nullptr;
	Super::Deinitialize();
}

bool UAstraIntroSubsystem::Seen()
{
	bool b = false;
	return GConfig && GConfig->GetBool(TEXT("ASTRA.Settings"), TEXT("IntroSeen"), b, GGameUserSettingsIni) && b;
}

float UAstraIntroSubsystem::ReadSeconds(int32 Line) const
{
	return 2.5f + LineText(Line).Len() / 15.f;
}

FString UAstraIntroSubsystem::LineText(int32 Line) const
{
	const AstraIntro::FScript& S = AstraIntro::ScriptFor(FAstraSettings::Get().Language);
	FString Text = (Line >= 0 && Line < AstraIntro::NumLines) ? FString(S.Lines[Line]) : FString();
	Text.ReplaceInline(TEXT("{talk}"), *FAstraSettings::KeyName(FAstraSettings::Get().TalkKey));
	Text.ReplaceInline(TEXT("{orders}"), *FAstraSettings::KeyName(FAstraSettings::Get().OrdersKey));
	return Text;
}

void UAstraIntroSubsystem::Build()
{
	Shots.Reset();
	UWorld* W = GetWorld();
	const auto Add = [this](const FVector& From, const FVector& To, const FVector& LookFrom, const FVector& LookTo, float Fov, int32 Line, int32 Deck = -1)
	{
		FShot S;
		S.From = From;
		S.To = To;
		S.LookFrom = LookFrom;
		S.LookTo = LookTo;
		S.Fov = Fov;
		S.Line = Line;
		S.Deck = Deck;
		Shots.Add(S);
	};
	// the Aquila from outside: her hull's own meshes, within 600 m of the bridge (AstraViewscreen.cpp, RebuildShowList); the shots were framed on
	// a hull 520 m across its bounds and scale with it
	FBox Hull(ForceInit);
	for (TActorIterator<AStaticMeshActor> It(W); It; ++It)
	{
		const UStaticMeshComponent* C = It->GetStaticMeshComponent();
		if (C && C->GetStaticMesh() && !It->IsHidden() && It->GetActorLocation().SizeSquared() < FMath::Square(60000.0) &&
		    C->GetStaticMesh()->GetName().StartsWith(TEXT("SM_SHIP_")))
		{
			Hull += C->Bounds.GetBox();
		}
	}
	const FVector H = Hull.IsValid ? Hull.GetCenter() : FVector(-17200.0, 0.0, -6200.0);
	const double K = Hull.IsValid ? FMath::Clamp(Hull.GetExtent().Size() / 52000.0, 0.4, 2.5) : 1.0;
	Add(H + K * FVector(220000, 120000, 52000), H + K * FVector(190000, 95000, 42000), H, H, 40.f, 0);
	Add(H + K * FVector(60000, -32000, 9000), H + K * FVector(5000, -36000, 7000), H + K * FVector(20000, 0, 0), H + K * FVector(-20000, 0, 0), 50.f, 1);

	// an allied ship of the strike group, seen from the Aquila's side
	const UAstraBattleSubsystem* Battle = W ? W->GetSubsystem<UAstraBattleSubsystem>() : nullptr;
	TArray<FVector4> Allies;
	if (Battle)
	{
		Battle->GetAllyViews(1, Allies);
	}
	if (Allies.Num())
	{
		const FVector P(Allies[0].X, Allies[0].Y, Allies[0].Z);
		const double S = FMath::Clamp((double)Allies[0].W, 6000.0, 60000.0);
		// the camera on the side the sun lights (the light behind it, a little to one side), else from the Aquila's side
		FVector Dir = (P - H).GetSafeNormal(UE_SMALL_NUMBER, FVector::XAxisVector);
		FVector Sun;
		if (AstraIntro::SunDir(W, Sun))
		{
			Dir = Sun;
		}
		FVector Side = FVector::CrossProduct(Dir, FVector::UpVector).GetSafeNormal();
		Side = Side.IsNearlyZero() ? FVector::YAxisVector : Side;
		Add(P - Dir * S * 3.4 + Side * S * 1.6 + FVector::UpVector * S * 0.8, P - Dir * S * 2.7 - Side * S * 0.4 + FVector::UpVector * S * 0.6, P, P, 45.f, 2);
	}

	// the bridge (its frame is the level's: the bridge at the origin, the floor at 0, the bow along +X)
	Add(FVector(-650, 0, 280), FVector(-500, 0, 260), FVector(900, 0, 120), FVector(900, 0, 120), 75.f, 3);          // the bridge, from the back
	Add(FVector(330, -460, 160), FVector(330, 460, 160), FVector(650, 0, 0), FVector(650, 0, 0), 60.f, 4);             // the helm and tactical
	Add(FVector(250, -120, 170), FVector(380, 0, 150), FVector(900, 0, 120), FVector(900, 0, 120), 60.f, 5);           // the main screen
	Add(FVector(130, -260, 290), FVector(130, 260, 290), FVector(430, 0, 36), FVector(430, 0, 36), 60.f, 6);           // the holo table
	Add(FVector(-260, 80, 220), FVector(-200, 0, 200), FVector(400, 0, 110), FVector(400, 0, 110), 65.f, 7);           // the Captain's chair
	Add(FVector(-2000, -390, 165), FVector(-1300, -390, 165), FVector(-500, -390, 150), FVector(-500, -390, 150), 70.f, 8);   // Corridor 1-A
	// the flight deck: Alpha's Falcons in their bays, from the middle of the deck (its lights on for the shot: AAstraHangar::Showcase)
	FVector Bays, Along, Across;
	const AAstraHangar* Hangar = nullptr;
	if (W)
	{
		TActorIterator<AAstraHangar> It(W);
		Hangar = It ? *It : nullptr;
	}
	if (Hangar && Hangar->GetAlphaView(Bays, Along, Across))
	{
		const FVector Up = FVector::UpVector;
		Add(Bays + Across * 2000 + Up * 700 - Along * 1900, Bays + Across * 1500 + Up * 520 - Along * 1000, Bays - Along * 500, Bays + Along * 200, 72.f, 9, 9);
	}
	else
	{
		Add(FVector(6400, 1400, -6650), FVector(7600, 900, -6750), FVector(13000, 0, -7100), FVector(13000, 0, -7100), 70.f, 9, 9);
	}

	// the Janus Gate, from the side the Aquila sees
	FVector G, Axis;
	float Rg = 0.f;
	if (Battle && Battle->GetGateView(G, Axis, Rg) && Rg > 1000.f)
	{
		if (FVector::DotProduct(Axis, H - G) < 0.0)
		{
			Axis = -Axis;
		}
		FVector Side = FVector::CrossProduct(Axis, FVector::UpVector).GetSafeNormal();
		Side = Side.IsNearlyZero() ? FVector::YAxisVector : Side;
		Add(G + Axis * Rg * 2.7 + Side * Rg * 1.5 + FVector::UpVector * Rg * 0.35, G + Axis * Rg * 2.2 + Side * Rg * 0.8 + FVector::UpVector * Rg * 0.2,
		    G, G, 50.f, 10);
	}

	// home: behind the chair, closing on the Captain's own eyes (the view goes back to them as the last line ends)
	FVector Eye(0, 0, 135);
	if (const APlayerController* PC = UGameplayStatics::GetPlayerController(W, 0))
	{
		if (const APawn* Pawn = PC->GetPawn())
		{
			if (const UCameraComponent* Cam = Pawn->FindComponentByClass<UCameraComponent>())
			{
				Eye = Cam->GetComponentLocation();
			}
		}
	}
	Add(FVector(-230, 40, 210), Eye - FVector(35, 0, -5), FVector(900, 0, 120), Eye + FVector(800, 0, -10), 65.f, 11);
}

void UAstraIntroSubsystem::Play(TFunction<void()> Done)
{
	UWorld* W = GetWorld();
	APlayerController* PC = W ? UGameplayStatics::GetPlayerController(W, 0) : nullptr;
	UGameViewportClient* VC = W ? W->GetGameViewport() : nullptr;
	if (bPlaying)
	{
		return;
	}
	if (PC && VC)
	{
		Build();
	}
	if (!PC || !VC || Shots.IsEmpty())
	{
		if (Done)
		{
			Done();
		}
		return;
	}
	OnDone = MoveTemp(Done);
	bPlaying = true;
	bFinishing = bLeaving = bNarrated = bVoiceHeard = bNextWanted = bSkipWanted = bReturned = false;
	FActorSpawnParameters SP;
	SP.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	SP.ObjectFlags |= RF_Transient;
	Camera = W->SpawnActor<ACameraActor>(Shots[0].From, (Shots[0].LookFrom - Shots[0].From).Rotation(), SP);
	if (!Camera)
	{
		bPlaying = false;
		TFunction<void()> D = MoveTemp(OnDone);
		if (D)
		{
			D();
		}
		return;
	}
	Camera->GetCameraComponent()->bConstrainAspectRatio = false;
	Camera->GetCameraComponent()->SetFieldOfView(Shots[0].Fov);
	PC->SetViewTargetWithBlend(Camera, 0.f);
	if (AASTRAPlayerController* APC = Cast<AASTRAPlayerController>(PC))
	{
		APC->SetCinematic(true);
	}

	// the screen: the picture between two black bars, the line in the lower one, the keys in the upper; a shade for the dips between shots
	UFont* Mono = AstraFonts::Mono();
	const FSlateFontInfo CapFont = Mono ? FSlateFontInfo(Mono, 18) : FCoreStyle::GetDefaultFontStyle("Mono", 18);
	const FSlateFontInfo KeyFont = Mono ? FSlateFontInfo(Mono, 11) : FCoreStyle::GetDefaultFontStyle("Mono", 11);
	const FSlateBrush* White = FCoreStyle::Get().GetBrush("WhiteBrush");
	const bool bCaption = FAstraSettings::Get().bSubtitles || !(GetMind() && GetMind()->IsConnected());
	TSharedRef<SOverlay> Root = SNew(SOverlay)
		+ SOverlay::Slot()
		[
			SAssignNew(Shade, SBorder).BorderImage(White).BorderBackgroundColor(FLinearColor::Black)
		]
		+ SOverlay::Slot()
		[
			SAssignNew(Bars, SVerticalBox)
			+ SVerticalBox::Slot().FillHeight(AstraIntro::BarFill)
			[
				SNew(SBorder).BorderImage(White).BorderBackgroundColor(FLinearColor::Black).HAlign(HAlign_Right).VAlign(VAlign_Center).Padding(FMargin(0, 0, 36, 0))
				[
					SNew(STextBlock).Font(KeyFont).ColorAndOpacity(AstraIntro::Dim).Text(FText::FromString(TEXT("SPACE  NEXT      ESC  SKIP")))
				]
			]
			+ SVerticalBox::Slot().FillHeight(1.f - 2.f * AstraIntro::BarFill)
			+ SVerticalBox::Slot().FillHeight(AstraIntro::BarFill)
			[
				SNew(SBorder).BorderImage(White).BorderBackgroundColor(FLinearColor::Black).HAlign(HAlign_Center).VAlign(VAlign_Center).Padding(FMargin(60, 0))
				[
					SNew(SBox).MaxDesiredWidth(1320.f)
					[
						SAssignNew(Caption, STextBlock).Font(CapFont).ColorAndOpacity(AstraIntro::Ink).Justification(ETextJustify::Center).AutoWrapText(true)
						.Visibility(bCaption ? EVisibility::HitTestInvisible : EVisibility::Collapsed)
					]
				]
			]
		];
	Content = Root;
	Widget = SNew(SWeakWidget).PossiblyNullContent(Content);
	VC->AddViewportWidgetContent(Widget.ToSharedRef(), 44);
	Keys = MakeShared<FAstraIntroKeys>(this);
	FSlateApplication::Get().RegisterInputPreProcessor(Keys);
	// the flight deck streams in while the tour is on the bridge and in space
	if (UAstraDeckStreaming* DS = W->GetSubsystem<UAstraDeckStreaming>())
	{
		DS->RequestDeck(9, 300.f);
	}
	Black = BlackWant = 1.f;
	Index = -1;
	bLeaving = true;                 // (the first shot begins in the dark, next tick)
	UE_LOG(LogASTRA, Log, TEXT("[Intro] the tour begins: %d shots, in %s%s"), Shots.Num(), *AstraIntro::LangOf(),
	       GetMind() && GetMind()->IsConnected() ? TEXT("") : TEXT(" (no mind: captions only)"));
}

UAstraMindSubsystem* UAstraIntroSubsystem::GetMind() const
{
	const UWorld* W = GetWorld();
	return W && W->GetGameInstance() ? W->GetGameInstance()->GetSubsystem<UAstraMindSubsystem>() : nullptr;
}

void UAstraIntroSubsystem::Begin(int32 I)
{
	Index = I;
	T = Silent = 0.f;
	bVoiceHeard = bNarrated = bLeaving = false;
	const FShot& S = Shots[I];
	Camera->GetCameraComponent()->SetFieldOfView(S.Fov);
	Camera->SetActorLocationAndRotation(S.From, (S.LookFrom - S.From).Rotation());
	if (const APlayerController* PC = UGameplayStatics::GetPlayerController(GetWorld(), 0); PC && PC->PlayerCameraManager)
	{
		PC->PlayerCameraManager->SetGameCameraCutThisFrame();      // (a new place: the upscaler's history and the exposure start over)
	}
	const FString Text = LineText(S.Line);
	if (Caption.IsValid())
	{
		Caption->SetText(FText::FromString(Text));
	}
	if (UAstraMindSubsystem* Mind = GetMind(); Mind && Mind->IsConnected())
	{
		Mind->Narrate(Text, AstraIntro::LangOf());
		bNarrated = true;
	}
	for (TActorIterator<AAstraHangar> It(GetWorld()); It; ++It)
	{
		It->Showcase(S.Deck == 9);                                 // (the flight deck lit while the tour looks at it)
	}
	if (S.Line == 10)
	{
		if (UAstraBattleSubsystem* Battle = GetWorld()->GetSubsystem<UAstraBattleSubsystem>())
		{
			Battle->PulseGate(0.35f);                               // ("when it lights up, ships are coming")
		}
	}
	BlackWant = 0.f;
	UE_LOG(LogASTRA, Log, TEXT("[Intro] shot %d/%d: line %d"), I + 1, Shots.Num(), S.Line);
}

void UAstraIntroSubsystem::Next()
{
	if (bPlaying && !bFinishing)
	{
		bNextWanted = true;
	}
}

void UAstraIntroSubsystem::Skip()
{
	if (bPlaying && !bFinishing)
	{
		bSkipWanted = true;
	}
}

void UAstraIntroSubsystem::Tick(float DeltaTime)
{
	const float Dt = FMath::Min(DeltaTime, 0.1f);
	APlayerController* PC = UGameplayStatics::GetPlayerController(GetWorld(), 0);
	if (!Camera || !PC)
	{
		Teardown(false);
		return;
	}
	UAstraMindSubsystem* Mind = GetMind();
	if (bSkipWanted || (bNextWanted && Index == Shots.Num() - 1))
	{
		// Esc (or Space on the last shot): out through the dark, the narrator stopped
		bSkipWanted = bNextWanted = false;
		if (Mind && bNarrated)
		{
			Mind->StopNarration();
		}
		Finish(false);
	}
	Black = FMath::FInterpConstantTo(Black, BlackWant, Dt, 1.f / AstraIntro::FadeS);
	if (Shade.IsValid())
	{
		Shade->SetBorderBackgroundColor(FLinearColor(0.f, 0.f, 0.f, Black));
	}
	if (bFinishing)
	{
		FinishT += Dt;
		if (!bReturned && (bBlendHome ? FinishT >= 0.f : Black >= 0.999f))
		{
			// the Captain's own eyes again (a blend from the last shot, which closes on them; a cut in the dark from anywhere else), and the war begins
			bReturned = true;
			FinishT = 0.f;
			if (Bars.IsValid())
			{
				Bars->SetVisibility(EVisibility::Collapsed);
			}
			if (APawn* Pawn = PC->GetPawn())
			{
				PC->SetViewTargetWithBlend(Pawn, bBlendHome ? AstraIntro::ReturnS : 0.f, VTBlend_EaseInOut, 2.f);
			}
			BlackWant = 0.f;
			if (TFunction<void()> D = MoveTemp(OnDone))
			{
				D();
			}
			OnDone = nullptr;
		}
		else if (bReturned && Black <= 0.001f && FinishT >= (bBlendHome ? AstraIntro::ReturnS + 0.25f : 0.f))
		{
			Teardown(false);
		}
		return;
	}
	if (bLeaving)
	{
		if (Black < 0.999f)
		{
			return;
		}
		// in the dark: the next shot, once its deck is in (the flight deck streams in during the bridge's shots)
		const int32 N = Index + 1;
		if (!Shots.IsValidIndex(N))
		{
			Finish(false);
			return;
		}
		const UAstraDeckStreaming* DS = GetWorld()->GetSubsystem<UAstraDeckStreaming>();
		if (Shots[N].Deck >= 0 && DS && !DS->IsDeckReady(Shots[N].Deck) && WaitDeck < 6.f)
		{
			WaitDeck += Dt;
			return;
		}
		WaitDeck = 0.f;
		Begin(N);
		return;
	}
	if (bNextWanted)
	{
		bNextWanted = false;
		if (Mind && bNarrated)
		{
			Mind->StopNarration();
		}
		bLeaving = true;
		BlackWant = 1.f;
		return;
	}
	T += Dt;
	const FShot& S = Shots[Index];
	// the camera: from its first place to its last over the time the line takes, eased; then it holds
	const float D = FMath::Max(6.f, ReadSeconds(S.Line) + 1.5f);
	const float A = FMath::InterpEaseInOut(0.f, 1.f, FMath::Clamp(T / D, 0.f, 1.f), 2.f);
	const FVector P = FMath::Lerp(S.From, S.To, (double)A);
	const FVector L = FMath::Lerp(S.LookFrom, S.LookTo, (double)A);
	Camera->SetActorLocationAndRotation(P, (L - P).Rotation());
	// the shot lasts as long as the narrator's line (and a breath after it); a voice that never came: the time to read the caption
	bool bDone;
	if (bNarrated && Mind && Mind->IsConnected())
	{
		const bool bSpeaking = Mind->IsNarratorSpeaking();
		bVoiceHeard |= bSpeaking;
		Silent = bSpeaking ? 0.f : Silent + Dt;
		bDone = bVoiceHeard ? (Silent > 0.6f && T > 4.f) : T > FMath::Max(9.f, ReadSeconds(S.Line));
	}
	else
	{
		bDone = T > ReadSeconds(S.Line);
	}
	if (bDone || T > 40.f)
	{
		if (Index == Shots.Num() - 1)
		{
			Finish(true);
		}
		else
		{
			bLeaving = true;
			BlackWant = 1.f;
		}
	}
}

void UAstraIntroSubsystem::Finish(bool bBlend)
{
	if (!bPlaying || bFinishing)
	{
		return;
	}
	bFinishing = true;
	bBlendHome = bBlend;
	bReturned = false;
	FinishT = 0.f;
	BlackWant = bBlend ? 0.f : 1.f;
	if (GConfig)
	{
		GConfig->SetBool(TEXT("ASTRA.Settings"), TEXT("IntroSeen"), true, GGameUserSettingsIni);
		GConfig->Flush(false, GGameUserSettingsIni);
	}
	UE_LOG(LogASTRA, Log, TEXT("[Intro] the tour ends (%s, at shot %d/%d)"), bBlend ? TEXT("played through") : TEXT("skipped"), Index + 1, Shots.Num());
}

void UAstraIntroSubsystem::Teardown(bool bWorldGoing)
{
	if (Keys.IsValid() && FSlateApplication::IsInitialized())
	{
		FSlateApplication::Get().UnregisterInputPreProcessor(Keys);
	}
	Keys.Reset();
	UWorld* W = GetWorld();
	if (Widget.IsValid() && W && W->GetGameViewport())
	{
		W->GetGameViewport()->RemoveViewportWidgetContent(Widget.ToSharedRef());
	}
	Widget.Reset();
	Content.Reset();
	Caption.Reset();
	Shade.Reset();
	Bars.Reset();
	const bool bWas = bPlaying;
	bPlaying = bFinishing = bLeaving = false;
	if (W && bWas && !bWorldGoing)
	{
		if (AASTRAPlayerController* APC = Cast<AASTRAPlayerController>(UGameplayStatics::GetPlayerController(W, 0)))
		{
			if (APC->GetViewTarget() == Camera && APC->GetPawn())
			{
				APC->SetViewTarget(APC->GetPawn());
			}
			APC->SetCinematic(false);
		}
	}
	if (Camera)
	{
		Camera->Destroy();
	}
	Camera = nullptr;
	if (W && bWas)
	{
		for (TActorIterator<AAstraHangar> It(W); It; ++It)
		{
			It->Showcase(false);
		}
	}
	Shots.Reset();
	Index = -1;
}
