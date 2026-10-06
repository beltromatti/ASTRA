// ASTRA — the campaign and the title menu.

#include "AstraCampaign.h"
#include "AstraFonts.h"
#include "AstraApiKey.h"
#include "AstraIntro.h"
#include "ASTRAPlayerController.h"

#include "ASTRA.h"
#include "AstraBattleSubsystem.h"
#include "AstraMindSubsystem.h"
#include "AstraSettings.h"
#include "AstraShipSubsystem.h"
#include "Dom/JsonObject.h"
#include "Engine/Font.h"
#include "Engine/GameViewportClient.h"
#include "Engine/World.h"
#include "Framework/Application/SlateApplication.h"
#include "GameFramework/PlayerController.h"
#include "HAL/FileManager.h"
#include "Kismet/GameplayStatics.h"
#include "Kismet/KismetSystemLibrary.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "Styling/CoreStyle.h"
#include "Widgets/Images/SImage.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Layout/SSpacer.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/SOverlay.h"
#include "Widgets/SWeakWidget.h"
#include "Widgets/Text/STextBlock.h"

DECLARE_CYCLE_STAT(TEXT("Campaign"), STAT_AstraCampaign, STATGROUP_Astra);

namespace
{
	// testing and automation: start without the menu (console, or -astra_campaign=new|continue on the command line)
	FString GCampaignRequest;
	FAutoConsoleCommand CmdCampaign(TEXT("astra.campaign"), TEXT("Start the campaign without the menu: astra.campaign new|continue"),
		FConsoleCommandWithArgsDelegate::CreateLambda([](const TArray<FString>& A) { if (A.Num()) { GCampaignRequest = A[0].ToLower(); } }));

	FAutoConsoleCommandWithWorld CmdMenuSettings(TEXT("astra.menu.settings"), TEXT("Testing: open the menu's SETTINGS page"),
		FConsoleCommandWithWorldDelegate::CreateLambda([](UWorld* World)
		{
			if (UAstraCampaignSubsystem* C = World ? World->GetSubsystem<UAstraCampaignSubsystem>() : nullptr)
			{
				if (!C->IsMenuOpen())
				{
					C->ShowMenu(C->IsStarted());
				}
				C->ShowSettings();
			}
		}));

	const FLinearColor MenuInk(0.86f, 0.9f, 0.95f);
	const FLinearColor MenuDim(0.52f, 0.58f, 0.66f);
	const FLinearColor MenuAccent(0.42f, 0.78f, 1.f);
}

// --------------------------------------------------------------------------------------------------- the menu
class SAstraMainMenu : public SCompoundWidget
{
public:
	SLATE_BEGIN_ARGS(SAstraMainMenu) : _InGame(false) {}
		SLATE_ARGUMENT(bool, InGame)
		SLATE_ARGUMENT(FString, SaveSummary)
		SLATE_EVENT(FSimpleDelegate, OnResume)
		SLATE_EVENT(FSimpleDelegate, OnContinue)
		SLATE_EVENT(FSimpleDelegate, OnNew)
		SLATE_EVENT(FSimpleDelegate, OnControls)
		SLATE_EVENT(FSimpleDelegate, OnSettings)
		SLATE_EVENT(FSimpleDelegate, OnIntro)
		SLATE_EVENT(FSimpleDelegate, OnQuit)
	SLATE_END_ARGS()

	void Construct(const FArguments& Args)
	{
		UFont* Title = AstraFonts::Title();
		UFont* Mono = AstraFonts::Mono();
		auto TitleFont = [Title](int32 Size) { return Title ? FSlateFontInfo(Title, Size) : FCoreStyle::GetDefaultFontStyle("Bold", Size); };
		auto MonoFont = [Mono](int32 Size) { return Mono ? FSlateFontInfo(Mono, Size) : FCoreStyle::GetDefaultFontStyle("Mono", Size); };
		bNeedConfirm = !Args._SaveSummary.IsEmpty() || Args._InGame;
		bHasSave = !Args._SaveSummary.IsEmpty();

		TSharedRef<SVerticalBox> Items = SNew(SVerticalBox);
		auto Item = [&](const FString& Label, const FString& Sub, FSimpleDelegate Do, int32 Index)
		{
			if (Index == 0)
			{
				FirstDo = Do;
			}
			Order.Add(TPair<int32, FSimpleDelegate>(Index, Do));
			Items->AddSlot().AutoHeight().Padding(0, 6)
			[
				SAssignNew(Buttons[Index], SButton)
				.ButtonStyle(&FCoreStyle::Get().GetWidgetStyle<FButtonStyle>("NoBorder"))
				.OnClicked_Lambda([this, Do, Index]() { Click(Do, Index); return FReply::Handled(); })
				[
					SNew(SVerticalBox)
					+ SVerticalBox::Slot().AutoHeight()
					[
						SNew(STextBlock).Font(TitleFont(30)).Text_Lambda([this, Label, Index]() { return FText::FromString(LabelFor(Label, Index)); })
						.ColorAndOpacity_Lambda([this, Index]() { return FSlateColor((Buttons[Index].IsValid() && Buttons[Index]->IsHovered()) || IsSelected(Index) ? MenuAccent : MenuInk); })
					]
					+ SVerticalBox::Slot().AutoHeight().Padding(2, 0, 0, 0)
					[
						SNew(STextBlock).Font(MonoFont(11)).ColorAndOpacity(MenuDim).Text(FText::FromString(Sub)).Visibility(Sub.IsEmpty() ? EVisibility::Collapsed : EVisibility::Visible)
					]
				]
			];
		};
		if (Args._InGame)
		{
			Item(TEXT("RESUME"), FString(), Args._OnResume, 0);
			Item(TEXT("CONTROLS"), TEXT("the Captain's controls and equipment"), Args._OnControls, 5);
		}
		else if (bHasSave)
		{
			Item(TEXT("CONTINUE"), Args._SaveSummary, Args._OnContinue, 0);
		}
		Item(TEXT("NEW CAMPAIGN"), bHasSave || Args._InGame ? TEXT("the war begins again at Aurelia; the saved one is lost") : TEXT("the war begins at Aurelia"),
		     Args._OnNew, 1);
		if (!Args._InGame)
		{
			Item(TEXT("INTRODUCTION"), TEXT("a short spoken tour of your ship and the war"), Args._OnIntro, 4);
		}
		Item(TEXT("SETTINGS"), TEXT("graphics, sound, language, controls, AI key"), Args._OnSettings, 3);
		Item(TEXT("QUIT"), FString(), Args._OnQuit, 2);

		ChildSlot
		[
			SNew(SOverlay)
			+ SOverlay::Slot().HAlign(HAlign_Left).VAlign(VAlign_Fill)
			[
				SNew(SBox).WidthOverride(620.f)
				[
					SNew(SBorder).BorderImage(FCoreStyle::Get().GetBrush("WhiteBrush")).BorderBackgroundColor(FLinearColor(0.004f, 0.006f, 0.01f, 0.78f))
					.Padding(FMargin(72, 90, 48, 54))
					[
						SNew(SVerticalBox)
						+ SVerticalBox::Slot().AutoHeight()
						[
							SNew(STextBlock).Font(TitleFont(96)).ColorAndOpacity(MenuInk).Text(FText::FromString(TEXT("ASTRA")))
						]
						+ SVerticalBox::Slot().AutoHeight().Padding(4, 0, 0, 0)
						[
							SNew(STextBlock).Font(MonoFont(13)).ColorAndOpacity(MenuAccent).Text(FText::FromString(TEXT("THE AURELIA MARCH  ·  ASN AQUILA  ·  2491")))
						]
						+ SVerticalBox::Slot().AutoHeight().Padding(4, 6, 0, 0)
						[
							SNew(STextBlock).Font(MonoFont(10)).ColorAndOpacity(MenuDim).Text(FText::FromString(FString(TEXT("ALPHA  ")) + FString(ASTRA_VERSION).Replace(TEXT("-alpha"), TEXT(""))))
						]
						+ SVerticalBox::Slot().FillHeight(1.f) [ SNew(SSpacer) ]
						+ SVerticalBox::Slot().AutoHeight() [ Items ]
						+ SVerticalBox::Slot().FillHeight(0.6f) [ SNew(SSpacer) ]
						+ SVerticalBox::Slot().AutoHeight()
						[
							SNew(STextBlock).Font(MonoFont(11)).ColorAndOpacity(MenuDim).AutoWrapText(true)
							.Text(FText::FromString(FString::Printf(TEXT("Hold %s and speak to your bridge crew, in any language (or T to type).\nE: leave or take the captain's chair.   Tab: your datapad.   Esc: this menu."),
							                                        *FAstraSettings::KeyName(FAstraSettings::Get().TalkKey))))
						]
					]
				]
			]
		];
	}

	virtual bool SupportsKeyboardFocus() const override { return true; }
	virtual FReply OnKeyDown(const FGeometry& Geometry, const FKeyEvent& Key) override
	{
		// the keyboard as well as the mouse: Up/Down (W/S) choose, Enter (Space) takes the item lit
		const FKey K = Key.GetKey();
		if ((K == EKeys::Up || K == EKeys::W || K == EKeys::Down || K == EKeys::S) && Order.Num())
		{
			const int32 Step = (K == EKeys::Up || K == EKeys::W) ? -1 : 1;
			Selected = Selected < 0 ? (Step > 0 ? 0 : Order.Num() - 1) : (Selected + Step + Order.Num()) % Order.Num();
			return FReply::Handled();
		}
		if (K == EKeys::Enter || K == EKeys::SpaceBar)
		{
			if (Order.IsValidIndex(Selected))
			{
				Click(Order[Selected].Value, Order[Selected].Key);
				return FReply::Handled();
			}
			if (FirstDo.IsBound())
			{
				Click(FirstDo, 0);   // (SButton::SimulateClick does not exist in Shipping)
				return FReply::Handled();
			}
		}
		return FReply::Unhandled();
	}

private:
	TSharedPtr<SButton> Buttons[6];
	TArray<TPair<int32, FSimpleDelegate>> Order;   // the items as they stand, top to bottom (their index, what they do)
	int32 Selected = -1;                           // the one lit by the keyboard (none until a key is pressed)
	FSimpleDelegate FirstDo;     // Enter: the first item (resume, or continue the saved war)

	bool IsSelected(int32 Index) const { return Order.IsValidIndex(Selected) && Order[Selected].Key == Index; }
	bool bHasSave = false;
	bool bNeedConfirm = false;   // a saved war is not thrown away with one click
	bool bConfirmNew = false;

	FString LabelFor(const FString& Label, int32 Index) const
	{
		return (Index == 1 && bConfirmNew) ? FString(TEXT("NEW CAMPAIGN — CLICK AGAIN TO CONFIRM")) : Label;
	}

	void Click(const FSimpleDelegate& Do, int32 Index)
	{
		if (Index == 1 && bNeedConfirm && !bConfirmNew)
		{
			bConfirmNew = true;
			return;
		}
		Do.ExecuteIfBound();
	}
};

// ------------------------------------------------------------------------------------------------ the campaign
bool UAstraCampaignSubsystem::ShouldCreateSubsystem(UObject* Outer) const
{
	const UWorld* World = Cast<UWorld>(Outer);
	return World && (World->WorldType == EWorldType::Game || World->WorldType == EWorldType::PIE);
}

FString UAstraCampaignSubsystem::SavePath() const
{
	return FPaths::ProjectSavedDir() / TEXT("Campaign/ship.json");
}

TSharedPtr<FJsonObject> UAstraCampaignSubsystem::LoadSave() const
{
	FString Text;
	if (!FFileHelper::LoadFileToString(Text, *SavePath()))
	{
		return nullptr;
	}
	TSharedPtr<FJsonObject> O;
	TSharedRef<TJsonReader<>> R = TJsonReaderFactory<>::Create(Text);
	return FJsonSerializer::Deserialize(R, O) && O.IsValid() ? O : nullptr;
}

bool UAstraCampaignSubsystem::HasSave() const
{
	return LoadSave().IsValid();
}

FString UAstraCampaignSubsystem::SaveSummary() const
{
	const TSharedPtr<FJsonObject> S = LoadSave();
	if (!S.IsValid())
	{
		return FString();
	}
	FString Sys = TEXT("Aurelia"), When;
	double Hull = 1.0;
	const TSharedPtr<FJsonObject>* Ship = nullptr;
	const TSharedPtr<FJsonObject>* Battle = nullptr;
	if (S->TryGetObjectField(TEXT("ship"), Ship)) { (*Ship)->TryGetStringField(TEXT("system"), Sys); }
	if (S->TryGetObjectField(TEXT("battle"), Battle)) { (*Battle)->TryGetNumberField(TEXT("hull_frac"), Hull); }
	S->TryGetStringField(TEXT("saved"), When);
	int32 Fallen = 0;
	const TArray<TSharedPtr<FJsonValue>>* F = nullptr;
	if (Ship && (*Ship)->TryGetArrayField(TEXT("fallen"), F)) { Fallen = F->Num(); }
	return FString::Printf(TEXT("%s SYSTEM  ·  HULL %d%%  ·  %d FALLEN  ·  %s"), *Sys.ToUpper(), FMath::RoundToInt(100.0 * Hull), Fallen, *When);
}

void UAstraCampaignSubsystem::OnWorldBeginPlay(UWorld& InWorld)
{
	Super::OnWorldBeginPlay(InWorld);
	// a level starts with a clean screen: the viewport outlives the level, and an overlay of the one before (the black shade of the story's last card,
	// a transporter's wash) would stay over the new one for ever (5 Oct: the new command after the loss of the Aquila opened on a black screen)
	if (UGameViewportClient* VC = InWorld.GetGameViewport())
	{
		VC->RemoveAllViewportWidgets();
	}
	FAstraSettings::Get().Apply();   // the player's graphics, frame rate and resolution floor
	// a start already chosen: the command line (automation) or the level's URL (a new campaign from the in-game menu)
	FString Arg;
	const TCHAR* UrlMode = InWorld.URL.GetOption(TEXT("astra_campaign="), nullptr);
	if (UrlMode || FParse::Value(FCommandLine::Get(), TEXT("astra_campaign="), Arg))
	{
		PendingMode = UrlMode ? FString(UrlMode).ToLower() : Arg.ToLower();
		PendingStartT = 1.0f;
		return;
	}
	ShowMenu(false);
}

void UAstraCampaignSubsystem::Deinitialize()
{
	HideMenu();   // (saves happen during play: every minute, at every turn of the story, on Quit)
	Super::Deinitialize();
}

void UAstraCampaignSubsystem::SetMenuInput(bool bMenu)
{
	APlayerController* PC = UGameplayStatics::GetPlayerController(GetWorld(), 0);
	if (!PC)
	{
		return;
	}
	PC->SetShowMouseCursor(bMenu);
	if (bMenu)
	{
		FInputModeUIOnly M;
		if (MenuWidget.IsValid())
		{
			M.SetWidgetToFocus(Menu);
		}
		PC->SetInputMode(M);
	}
	else
	{
		PC->SetInputMode(FInputModeGameOnly());
	}
}

void UAstraCampaignSubsystem::ShowMenu(bool bInGame)
{
	if (MenuWidget.IsValid() || KeyWidget.IsValid() || !GEngine || !GetWorld() || !GetWorld()->GetGameViewport())
	{
		return;
	}
	// no way into the game without a key that works: the crew is nothing without it (a game without the mind, -astra_nomind, needs none)
	if (!bInGame && !FAstraApiKey::IsGood() && !FParse::Param(FCommandLine::Get(), TEXT("astra_nomind")))
	{
		ShowKeyGate(false);
		return;
	}
	bMenuInGame = bInGame;
	TWeakObjectPtr<UAstraCampaignSubsystem> Self(this);
	SAssignNew(Menu, SAstraMainMenu)
		.InGame(bInGame)
		.SaveSummary(bInGame ? FString() : SaveSummary())
		.OnResume_Lambda([Self]() { if (Self.IsValid()) { Self->HideMenu(); } })
		.OnContinue_Lambda([Self]() { if (Self.IsValid()) { Self->Continue(); } })
		.OnNew_Lambda([Self]() { if (Self.IsValid()) { Self->StartNew(); } })
		.OnControls_Lambda([Self]() { if (Self.IsValid()) { if (auto* PC = Cast<AASTRAPlayerController>(UGameplayStatics::GetPlayerController(Self->GetWorld(), 0))) { PC->ShowControlsFromMenu(); } } })
		.OnSettings_Lambda([Self]() { if (Self.IsValid()) { Self->ShowSettings(); } })
		.OnIntro_Lambda([Self]() { if (Self.IsValid()) { Self->PlayIntro(); } })
		.OnQuit_Lambda([Self]()
		{
			if (Self.IsValid())
			{
				if (Self->bStarted) { Self->SaveNow(TEXT("quit")); }
				UKismetSystemLibrary::QuitGame(Self->GetWorld(), nullptr, EQuitPreference::Quit, false);
			}
		});
	MenuWidget = SNew(SWeakWidget).PossiblyNullContent(Menu.ToSharedRef());
	GetWorld()->GetGameViewport()->AddViewportWidgetContent(MenuWidget.ToSharedRef(), 50);
	if (bInGame)
	{
		UGameplayStatics::SetGamePaused(GetWorld(), true);
	}
	SetMenuInput(true);
}

void UAstraCampaignSubsystem::ShowSettings()
{
	UGameViewportClient* VC = GetWorld() ? GetWorld()->GetGameViewport() : nullptr;
	if (!VC || !MenuWidget.IsValid() || SettingsWidget.IsValid())
	{
		return;
	}
	// the page takes the menu's place; BACK (or Esc) puts the menu back
	VC->RemoveViewportWidgetContent(MenuWidget.ToSharedRef());
	TWeakObjectPtr<UAstraCampaignSubsystem> Self(this);
	TSharedRef<SAstraSettingsPage> Page = SNew(SAstraSettingsPage).OnBack_Lambda([Self]() { if (Self.IsValid()) { Self->HideSettings(); } })
		.OnApiKey_Lambda([Self]() { if (Self.IsValid()) { Self->ShowKeyGate(true); } });
	SettingsPage = Page;
	SettingsWidget = SNew(SWeakWidget).PossiblyNullContent(Page);
	VC->AddViewportWidgetContent(SettingsWidget.ToSharedRef(), 50);
	if (APlayerController* PC = UGameplayStatics::GetPlayerController(GetWorld(), 0))
	{
		FInputModeUIOnly M;
		M.SetWidgetToFocus(Page);
		PC->SetInputMode(M);
	}
}

void UAstraCampaignSubsystem::ShowKeyGate(bool bChange)
{
	UGameViewportClient* VC = GetWorld() ? GetWorld()->GetGameViewport() : nullptr;
	if (!VC || KeyWidget.IsValid())
	{
		return;
	}
	TWeakObjectPtr<UAstraCampaignSubsystem> Self(this);
	TSharedRef<SAstraKeyGate> Gate = SNew(SAstraKeyGate).ChangeMode(bChange)
		.OnDone_Lambda([Self, bChange]()
		{
			if (Self.IsValid())
			{
				Self->HideKeyGate();
				if (!bChange)
				{
					Self->ShowMenu(false);
				}
			}
		})
		.OnCancel_Lambda([Self, bChange]()
		{
			if (!Self.IsValid())
			{
				return;
			}
			if (bChange)
			{
				Self->HideKeyGate();
			}
			else
			{
				UKismetSystemLibrary::QuitGame(Self->GetWorld(), nullptr, EQuitPreference::Quit, false);
			}
		});
	KeyGate = Gate;
	KeyWidget = SNew(SWeakWidget).PossiblyNullContent(Gate);
	VC->AddViewportWidgetContent(KeyWidget.ToSharedRef(), 60);
	if (APlayerController* PC = UGameplayStatics::GetPlayerController(GetWorld(), 0))
	{
		PC->SetShowMouseCursor(true);
		FInputModeUIOnly M;
		M.SetWidgetToFocus(Gate);
		PC->SetInputMode(M);
	}
	if (!bChange)
	{
		Gate->CheckSaved();                          // (a key saved before and still good: straight on to the menu)
	}
}

void UAstraCampaignSubsystem::HideKeyGate()
{
	UGameViewportClient* VC = GetWorld() ? GetWorld()->GetGameViewport() : nullptr;
	if (VC && KeyWidget.IsValid())
	{
		VC->RemoveViewportWidgetContent(KeyWidget.ToSharedRef());
	}
	KeyWidget.Reset();
	KeyGate.Reset();
	if (SettingsPage.IsValid())
	{
		if (APlayerController* PC = UGameplayStatics::GetPlayerController(GetWorld(), 0))
		{
			FInputModeUIOnly M;
			M.SetWidgetToFocus(SettingsPage);
			PC->SetInputMode(M);
		}
	}
}

void UAstraCampaignSubsystem::HideSettings()
{
	UGameViewportClient* VC = GetWorld() ? GetWorld()->GetGameViewport() : nullptr;
	if (VC && SettingsWidget.IsValid())
	{
		VC->RemoveViewportWidgetContent(SettingsWidget.ToSharedRef());
	}
	SettingsWidget.Reset();
	SettingsPage.Reset();
	if (VC && MenuWidget.IsValid())
	{
		VC->AddViewportWidgetContent(MenuWidget.ToSharedRef(), 50);
		SetMenuInput(true);
	}
}

void UAstraCampaignSubsystem::HideMenu()
{
	if (SettingsWidget.IsValid() && GetWorld() && GetWorld()->GetGameViewport())
	{
		GetWorld()->GetGameViewport()->RemoveViewportWidgetContent(SettingsWidget.ToSharedRef());
	}
	SettingsWidget.Reset();
	SettingsPage.Reset();
	if (MenuWidget.IsValid() && GetWorld() && GetWorld()->GetGameViewport())
	{
		GetWorld()->GetGameViewport()->RemoveViewportWidgetContent(MenuWidget.ToSharedRef());
	}
	const bool bWas = MenuWidget.IsValid();
	MenuWidget.Reset();
	Menu.Reset();
	if (bWas && GetWorld())
	{
		const UAstraShipSubsystem* Ship = GetWorld()->GetSubsystem<UAstraShipSubsystem>();
		UGameplayStatics::SetGamePaused(GetWorld(), Ship && Ship->IsStoryPaused());   // (a story card holds the world: RESUME gives it back to the card)
		SetMenuInput(false);
	}
}

void UAstraCampaignSubsystem::StartNew()
{
	if (bStarted)
	{
		// a new war from the middle of one: start the level over, the menu's choice carried on the command line
		IFileManager::Get().Delete(*SavePath());
		HideMenu();
		UGameplayStatics::OpenLevel(GetWorld(), FName(*UGameplayStatics::GetCurrentLevelName(GetWorld())), true, TEXT("astra_campaign=new"));
		return;
	}
	Begin(TEXT("new"));
}

void UAstraCampaignSubsystem::Continue()
{
	Begin(TEXT("continue"));
}

void UAstraCampaignSubsystem::PlayIntro()
{
	UAstraIntroSubsystem* Intro = GetWorld() ? GetWorld()->GetSubsystem<UAstraIntroSubsystem>() : nullptr;
	if (!Intro || Intro->IsPlaying())
	{
		return;
	}
	HideMenu();
	TWeakObjectPtr<UAstraCampaignSubsystem> Self(this);
	Intro->Play([Self]() { if (Self.IsValid()) { Self->ShowMenu(false); } });
}

void UAstraCampaignSubsystem::Begin(const FString& Mode)
{
	HideMenu();
	// a player's first new war opens on the introduction (AstraIntro.h): the war begins when it ends. A start the command line chose (automation,
	// the test bench) goes straight in, unless it asks for the tour (-astra_intro)
	FString Arg;
	const bool bAsked = FParse::Param(FCommandLine::Get(), TEXT("astra_intro"));
	const bool bScripted = FParse::Param(FCommandLine::Get(), TEXT("astra_harness")) || FParse::Value(FCommandLine::Get(), TEXT("astra_campaign="), Arg);
	UAstraIntroSubsystem* Intro = GetWorld()->GetSubsystem<UAstraIntroSubsystem>();
	if (Mode == TEXT("new") && Intro && !Intro->IsPlaying() && !bIntroDone && (bAsked || (!bScripted && !UAstraIntroSubsystem::Seen())))
	{
		bIntroDone = true;
		TWeakObjectPtr<UAstraCampaignSubsystem> Self(this);
		Intro->Play([Self, Mode]() { if (Self.IsValid()) { Self->BeginWar(Mode); } });
		return;
	}
	BeginWar(Mode);
}

void UAstraCampaignSubsystem::BeginWar(const FString& Mode)
{
	UAstraBattleSubsystem* Battle = GetWorld()->GetSubsystem<UAstraBattleSubsystem>();
	UAstraShipSubsystem* Ship = GetWorld()->GetSubsystem<UAstraShipSubsystem>();
	const TSharedPtr<FJsonObject> Save = Mode == TEXT("continue") ? LoadSave() : nullptr;
	FString SavedWhen;
	if (Save.IsValid() && Save->TryGetStringField(TEXT("saved"), SavedWhen) && SavedWhen == TEXT("NEW COMMAND"))
	{
		// the first watch aboard the new Aquila: the scene opens in the dark on her name
		if (AASTRAPlayerController* PC = Cast<AASTRAPlayerController>(UGameplayStatics::GetPlayerController(GetWorld(), 0)))
		{
			FString Hull = TEXT("CVC-03");
			const TSharedPtr<FJsonObject>* ShipSave = nullptr;
			if (Save->TryGetObjectField(TEXT("ship"), ShipSave))
			{
				(*ShipSave)->TryGetStringField(TEXT("hull_number"), Hull);
			}
			PC->StoryCard(TEXT("ASN AQUILA"), FString::Printf(TEXT("%s · NEW RAVENNA FLEET YARDS · THE CAPTAIN'S NEW COMMAND"), *Hull), 4.f, false, true);
		}
	}
	if (Save.IsValid() && Battle && Ship)
	{
		const TSharedPtr<FJsonObject>* S = nullptr;
		if (Save->TryGetObjectField(TEXT("ship"), S)) { Ship->ResumeFrom(*S); }
		if (Save->TryGetObjectField(TEXT("battle"), S)) { Battle->ResumeFrom(*S); }
	}
	else if (Battle)
	{
		Battle->StartCampaign();
	}
	if (UAstraMindSubsystem* Mind = GetWorld()->GetGameInstance() ? GetWorld()->GetGameInstance()->GetSubsystem<UAstraMindSubsystem>() : nullptr)
	{
		Mind->SendCampaign(Save.IsValid() ? TEXT("continue") : TEXT("new"));
	}
	bStarted = true;
	AutoSaveT = 20.f;
	if (Ship && !ShipEventHandle.IsValid())
	{
		// the story moved on (an engagement ended, a beat completed, a transit): save at once
		ShipEventHandle = Ship->OnShipEvent.AddWeakLambda(this, [this](const FString& Text, bool)
		{
			if (Text.StartsWith(TEXT("director:")))
			{
				AutoSaveT = FMath::Min(AutoSaveT, 2.f);
			}
		});
	}
	UE_LOG(LogASTRA, Log, TEXT("[Campaign] %s"), Save.IsValid() ? TEXT("continued from the save") : TEXT("new campaign"));
}

void UAstraCampaignSubsystem::SaveNow(const TCHAR* Why)
{
	UAstraBattleSubsystem* Battle = GetWorld() ? GetWorld()->GetSubsystem<UAstraBattleSubsystem>() : nullptr;
	UAstraShipSubsystem* Ship = GetWorld() ? GetWorld()->GetSubsystem<UAstraShipSubsystem>() : nullptr;
	if (!Battle || !Ship)
	{
		return;
	}
	TSharedRef<FJsonObject> O = MakeShared<FJsonObject>();
	O->SetNumberField(TEXT("version"), 1);
	static const TCHAR* Months[] = {TEXT("JAN"), TEXT("FEB"), TEXT("MAR"), TEXT("APR"), TEXT("MAY"), TEXT("JUN"), TEXT("JUL"), TEXT("AUG"),
	                                TEXT("SEP"), TEXT("OCT"), TEXT("NOV"), TEXT("DEC")};
	const FDateTime Now = FDateTime::Now();
	O->SetStringField(TEXT("saved"), FString::Printf(TEXT("%d %s %02d:%02d"), Now.GetDay(), Months[Now.GetMonth() - 1], Now.GetHour(), Now.GetMinute()));
	O->SetObjectField(TEXT("ship"), Ship->SaveJson());
	O->SetObjectField(TEXT("battle"), Battle->SaveJson());
	FString Text;
	TSharedRef<TJsonWriter<>> W = TJsonWriterFactory<>::Create(&Text);
	FJsonSerializer::Serialize(O, W);
	const FString Tmp = SavePath() + TEXT(".tmp");
	if (FFileHelper::SaveStringToFile(Text, *Tmp) && IFileManager::Get().Move(*SavePath(), *Tmp, true, true))
	{
		UE_LOG(LogASTRA, Log, TEXT("[Campaign] saved (%s)"), Why);
	}
}

void UAstraCampaignSubsystem::NewCommand(const FString& System)
{
	UAstraShipSubsystem* Ship = GetWorld() ? GetWorld()->GetSubsystem<UAstraShipSubsystem>() : nullptr;
	if (!Ship)
	{
		return;
	}
	TSharedRef<FJsonObject> O = MakeShared<FJsonObject>();
	O->SetNumberField(TEXT("version"), 1);
	O->SetStringField(TEXT("saved"), TEXT("NEW COMMAND"));
	TSharedRef<FJsonObject> S = Ship->SaveJson();
	S->SetStringField(TEXT("system"), System.IsEmpty() ? TEXT("Aurelia") : System);
	// the sister that takes her name: CVC-03 after the first Aquila, then the next (the yards have built up to -05)
	const FString Old = Ship->GetHullNumber();
	const int32 Next = Old == TEXT("CVC-01") ? 3 : FMath::Min(5, FCString::Atoi(*Old.Right(2)) + 1);
	S->SetStringField(TEXT("hull_number"), FString::Printf(TEXT("CVC-%02d"), Next));
	S->SetArrayField(TEXT("wounded"), {});
	S->SetArrayField(TEXT("medbay"), {});
	S->RemoveField(TEXT("heat_pct"));
	S->RemoveField(TEXT("radiators_out"));
	S->RemoveField(TEXT("radiator_health"));
	S->RemoveField(TEXT("coolant_vents"));
	O->SetObjectField(TEXT("ship"), S);
	TSharedRef<FJsonObject> Fresh = MakeShared<FJsonObject>();      // a new hull: her defaults (full hull, magazine, air group)...
	if (const UAstraBattleSubsystem* Battle = GetWorld()->GetSubsystem<UAstraBattleSubsystem>())
	{
		// ...in the systems as the war left them: the wrecks, the debris, the pods still calling, the old Aquila's own (SPAZIO-VIVO)
		const TSharedPtr<FJsonObject>* Space = nullptr;
		if (const TSharedRef<FJsonObject> Was = Battle->SaveJson(); Was->TryGetObjectField(TEXT("space"), Space) && Space)
		{
			Fresh->SetObjectField(TEXT("space"), *Space);
		}
	}
	O->SetObjectField(TEXT("battle"), Fresh);
	FString Text;
	TSharedRef<TJsonWriter<>> W = TJsonWriterFactory<>::Create(&Text);
	FJsonSerializer::Serialize(O, W);
	FFileHelper::SaveStringToFile(Text, *SavePath());
	UE_LOG(LogASTRA, Log, TEXT("[Campaign] new command: the new Aquila in %s"), *System);
	UGameplayStatics::OpenLevel(GetWorld(), FName(*UGameplayStatics::GetCurrentLevelName(GetWorld())), true, TEXT("astra_campaign=continue"));
}

void UAstraCampaignSubsystem::Tick(float DeltaTime)
{
	SCOPE_CYCLE_COUNTER(STAT_AstraCampaign);
	// console or command-line starts (tests, automation, "new campaign" from the menu mid-game)
	if (!GCampaignRequest.IsEmpty() && !bStarted)
	{
		PendingMode = GCampaignRequest;
		PendingStartT = 0.f;
	}
	GCampaignRequest.Empty();
	if (PendingStartT >= 0.f && (PendingStartT -= DeltaTime) <= 0.f)
	{
		PendingStartT = -1.f;
		Begin(PendingMode == TEXT("continue") ? TEXT("continue") : TEXT("new"));
	}
	if (MenuWidget.IsValid() && Menu.IsValid() && FSlateApplication::IsInitialized() && !Menu->HasKeyboardFocus())
	{
		FSlateApplication::Get().SetKeyboardFocus(Menu);   // keep Enter working on the menu
	}
	const UAstraShipSubsystem* ShipNow = GetWorld() ? GetWorld()->GetSubsystem<UAstraShipSubsystem>() : nullptr;
	if (bStarted && !MenuWidget.IsValid() && (AutoSaveT -= DeltaTime) <= 0.f && !(ShipNow && ShipNow->IsShipLost()))
	{
		// (never while the Aquila is lost: the save that follows is the new command's)
		AutoSaveT = 60.f;
		SaveNow(TEXT("autosave"));
	}
}
