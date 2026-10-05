// ASTRA — the player's OpenRouter key (AstraApiKey.h).

#include "AstraApiKey.h"

#include "ASTRA.h"
#include "AstraFonts.h"
#include "AstraMindLaunch.h"
#include "AstraMindSubsystem.h"
#include "Dom/JsonObject.h"
#include "Engine/Engine.h"
#include "Engine/GameInstance.h"
#include "Engine/GameViewportClient.h"
#include "Engine/World.h"
#include "HAL/FileManager.h"
#include "HAL/PlatformApplicationMisc.h"
#include "HAL/PlatformProcess.h"
#include "HttpModule.h"
#include "Interfaces/IHttpRequest.h"
#include "Interfaces/IHttpResponse.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Styling/CoreStyle.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/Input/SEditableTextBox.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/SOverlay.h"
#include "Widgets/Text/STextBlock.h"
// portable-ok: the key file is made readable by its owner only where the system has POSIX permissions (Windows keeps it in the user's own folder)
#if PLATFORM_MAC || PLATFORM_LINUX
// portable-ok: (the same: POSIX permissions)
#include <sys/stat.h>
#endif

FAstraApiKey::EState FAstraApiKey::State = FAstraApiKey::EState::Unknown;
double FAstraApiKey::Balance = -1.0;
FString FAstraApiKey::Message;

namespace
{
	const FLinearColor KInk(0.86f, 0.9f, 0.95f);
	const FLinearColor KDim(0.52f, 0.58f, 0.66f);
	const FLinearColor KAccent(0.42f, 0.78f, 1.f);
	const FLinearColor KGood(0.45f, 0.9f, 0.6f);
	const FLinearColor KBad(1.f, 0.48f, 0.38f);
	const TCHAR* KeyName = TEXT("OPENROUTER_API_KEY");

	UAstraMindSubsystem* Mind()
	{
		UWorld* W = GEngine && GEngine->GameViewport ? GEngine->GameViewport->GetWorld() : nullptr;
		return W && W->GetGameInstance() ? W->GetGameInstance()->GetSubsystem<UAstraMindSubsystem>() : nullptr;
	}

	TSharedPtr<FJsonObject> JsonOf(const FHttpResponsePtr& R)
	{
		TSharedPtr<FJsonObject> O;
		if (R.IsValid())
		{
			FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(R->GetContentAsString()), O);
		}
		return O;
	}
}

FString FAstraApiKey::EnvPath()
{
	const AstraMindLaunch::FMachine M = AstraMindLaunch::FMachine::Live();
	const AstraMindLaunch::FPlan Plan = AstraMindLaunch::MakePlan(M);
	// a packaged game: the mind's own data folder; from the sources: the repository's .env (the project folder is the repository's root)
	return Plan.bPackaged && !Plan.DataDir.IsEmpty() ? FPaths::Combine(Plan.DataDir, TEXT(".env")) : FPaths::Combine(M.ProjectDir, TEXT(".env"));
}

FString FAstraApiKey::Read()
{
	TArray<FString> Lines;
	FFileHelper::LoadFileToStringArray(Lines, *EnvPath());
	for (const FString& L : Lines)
	{
		FString K, V;
		if (L.TrimStart().StartsWith(TEXT("#")) || !L.Split(TEXT("="), &K, &V))
		{
			continue;
		}
		if (K.TrimStartAndEnd() == KeyName)
		{
			return V.TrimStartAndEnd().TrimQuotes();
		}
	}
	return FString();
}

bool FAstraApiKey::Write(const FString& Key)
{
	const FString Path = EnvPath();
	IFileManager::Get().MakeDirectory(*FPaths::GetPath(Path), true);
	TArray<FString> Lines, Out;
	FFileHelper::LoadFileToStringArray(Lines, *Path);
	bool bSet = false;
	for (const FString& L : Lines)
	{
		FString K, V;
		if (!L.TrimStart().StartsWith(TEXT("#")) && L.Split(TEXT("="), &K, &V) && K.TrimStartAndEnd() == KeyName)
		{
			if (!bSet)
			{
				Out.Add(FString::Printf(TEXT("%s=%s"), KeyName, *Key));
				bSet = true;
			}
			continue;
		}
		Out.Add(L);
	}
	if (!bSet)
	{
		Out.Add(FString::Printf(TEXT("%s=%s"), KeyName, *Key));
	}
	const bool bOk = FFileHelper::SaveStringToFile(FString::Join(Out, TEXT("\n")) + TEXT("\n"), *Path, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
	// portable-ok: owner-only permissions where the system has them
#if PLATFORM_MAC || PLATFORM_LINUX
	chmod(TCHAR_TO_UTF8(*Path), S_IRUSR | S_IWUSR);
#endif
	if (UAstraMindSubsystem* M = Mind())
	{
		M->SendKeyChanged();
	}
	UE_LOG(LogASTRA, Log, TEXT("[ApiKey] the OpenRouter key was saved (%s)"), bOk ? TEXT("ok") : TEXT("FAILED"));
	return bOk;
}

FString FAstraApiKey::Masked(const FString& Key)
{
	return Key.Len() > 14 ? Key.Left(9) + TEXT("…") + Key.Right(4) : (Key.IsEmpty() ? FString() : TEXT("…"));
}

void FAstraApiKey::Verify(const FString& Key, TFunction<void()> Done)
{
	State = EState::Checking;
	Message = TEXT("Checking the key with openrouter.ai...");
	if (Key.TrimStartAndEnd().IsEmpty())
	{
		State = EState::Missing;
		Message = TEXT("Paste your OpenRouter key to start.");
		Done();
		return;
	}
	const TSharedRef<IHttpRequest, ESPMode::ThreadSafe> R = FHttpModule::Get().CreateRequest();
	R->SetURL(TEXT("https://openrouter.ai/api/v1/key"));
	R->SetVerb(TEXT("GET"));
	R->SetHeader(TEXT("Authorization"), TEXT("Bearer ") + Key.TrimStartAndEnd());
	R->SetTimeout(15.f);
	R->OnProcessRequestComplete().BindLambda([Key, Done](FHttpRequestPtr, FHttpResponsePtr Resp, bool bConnected)
	{
		if (!bConnected || !Resp.IsValid())
		{
			State = EState::Offline;
			Message = TEXT("No connection to openrouter.ai: check the internet connection, then try again.");
			Done();
			return;
		}
		const int32 Code = Resp->GetResponseCode();
		if (Code == 401 || Code == 403)
		{
			State = EState::Invalid;
			Message = TEXT("OpenRouter refused this key: copy it again, whole, from openrouter.ai/keys.");
			Done();
			return;
		}
		if (Code != 200)
		{
			State = EState::Error;
			Message = FString::Printf(TEXT("openrouter.ai answered %d: try again in a moment."), Code);
			Done();
			return;
		}
		// the key's own spending limit, when it has one
		double KeyLeft = -1.0;
		if (const TSharedPtr<FJsonObject> J = JsonOf(Resp))
		{
			const TSharedPtr<FJsonObject>* Data = nullptr;
			if (J->TryGetObjectField(TEXT("data"), Data) && Data && (*Data)->HasTypedField<EJson::Number>(TEXT("limit_remaining")))
			{
				KeyLeft = (*Data)->GetNumberField(TEXT("limit_remaining"));
			}
		}
		// and the account's credit
		const TSharedRef<IHttpRequest, ESPMode::ThreadSafe> C = FHttpModule::Get().CreateRequest();
		C->SetURL(TEXT("https://openrouter.ai/api/v1/credits"));
		C->SetVerb(TEXT("GET"));
		C->SetHeader(TEXT("Authorization"), TEXT("Bearer ") + Key.TrimStartAndEnd());
		C->SetTimeout(15.f);
		C->OnProcessRequestComplete().BindLambda([KeyLeft, Done](FHttpRequestPtr, FHttpResponsePtr Resp2, bool bOk2)
		{
			double Account = -1.0;
			if (bOk2 && Resp2.IsValid() && Resp2->GetResponseCode() == 200)
			{
				if (const TSharedPtr<FJsonObject> J = JsonOf(Resp2))
				{
					const TSharedPtr<FJsonObject>* Data = nullptr;
					if (J->TryGetObjectField(TEXT("data"), Data) && Data)
					{
						Account = (*Data)->GetNumberField(TEXT("total_credits")) - (*Data)->GetNumberField(TEXT("total_usage"));
					}
				}
			}
			Balance = KeyLeft >= 0.0 ? (Account >= 0.0 ? FMath::Min(KeyLeft, Account) : KeyLeft) : Account;
			if (Balance >= 0.0 && Balance < 0.02)
			{
				State = EState::NoCredit;
				Message = KeyLeft >= 0.0 && KeyLeft < 0.02 ? TEXT("This key's spending limit is used up: raise it at openrouter.ai/keys, or make a new key.")
				                                         : TEXT("No credit left on your OpenRouter account: add some at openrouter.ai/settings/credits.");
			}
			else
			{
				State = EState::Ok;
				Message = Balance >= 0.0 ? FString::Printf(TEXT("Key accepted: $%.2f of credit. An hour of play uses about $0.50 to $1."), Balance)
				                         : FString(TEXT("Key accepted."));
			}
			UE_LOG(LogASTRA, Log, TEXT("[ApiKey] verified: %s"), *Message);
			Done();
		});
		C->ProcessRequest();
	});
	R->ProcessRequest();
}

FString FAstraApiKey::Summary()
{
	const FString Key = Read();
	if (Key.IsEmpty())
	{
		return TEXT("NOT SET");
	}
	return Masked(Key) + (State == EState::Ok && Balance >= 0.0 ? FString::Printf(TEXT("  ·  $%.2f"), Balance) : FString());
}

FString FAstraApiKey::Note()
{
	return State == EState::Ok || State == EState::Unknown ? FString(TEXT("the crew thinks through OpenRouter with your own key: Enter to change it"))
	                                                       : Message;
}

// --------------------------------------------------------------------------------------------------- the page
void SAstraKeyGate::Construct(const FArguments& Args)
{
	bChangeMode = Args._ChangeMode;
	OnDone = Args._OnDone;
	OnCancel = Args._OnCancel;
	UFont* Title = AstraFonts::Title();
	UFont* Mono = AstraFonts::Mono();
	auto TitleFont = [Title](int32 Size) { return Title ? FSlateFontInfo(Title, Size) : FCoreStyle::GetDefaultFontStyle("Bold", Size); };
	auto MonoFont = [Mono](int32 Size) { return Mono ? FSlateFontInfo(Mono, Size) : FCoreStyle::GetDefaultFontStyle("Mono", Size); };
	Status = bChangeMode ? FString(TEXT("Paste the new key, then VERIFY.")) : FString(TEXT("Paste your OpenRouter key to start."));
	StatusColour = KDim;
	auto Button = [&](const FString& Label, TFunction<void()> Do)
	{
		return SNew(SButton).ButtonStyle(&FCoreStyle::Get().GetWidgetStyle<FButtonStyle>("NoBorder"))
			.IsEnabled_Lambda([this]() { return !bBusy; })
			.OnClicked_Lambda([Do]() { Do(); return FReply::Handled(); })
			[
				SNew(SBorder).BorderImage(FCoreStyle::Get().GetBrush("WhiteBrush")).BorderBackgroundColor(FLinearColor(0.08f, 0.12f, 0.18f, 0.95f)).Padding(FMargin(18, 9))
				[
					SNew(STextBlock).Font(TitleFont(18)).ColorAndOpacity(KInk).Text(FText::FromString(Label))
				]
			];
	};
	ChildSlot
	[
		SNew(SOverlay)
		+ SOverlay::Slot()
		[
			SNew(SBorder).BorderImage(FCoreStyle::Get().GetBrush("WhiteBrush")).BorderBackgroundColor(FLinearColor(0.f, 0.f, 0.f, 0.72f))
		]
		+ SOverlay::Slot().HAlign(HAlign_Center).VAlign(VAlign_Center)
		[
			SNew(SBox).WidthOverride(820.f)
			[
				SNew(SBorder).BorderImage(FCoreStyle::Get().GetBrush("WhiteBrush")).BorderBackgroundColor(FLinearColor(0.008f, 0.012f, 0.02f, 0.97f)).Padding(FMargin(56, 46))
				[
					SNew(SVerticalBox)
					+ SVerticalBox::Slot().AutoHeight()
					[
						SNew(STextBlock).Font(TitleFont(44)).ColorAndOpacity(KInk).Text(FText::FromString(bChangeMode ? TEXT("YOUR OPENROUTER KEY") : TEXT("CONNECT YOUR CREW")))
					]
					+ SVerticalBox::Slot().AutoHeight().Padding(0, 14, 0, 0)
					[
						SNew(STextBlock).Font(MonoFont(12)).ColorAndOpacity(KDim).AutoWrapText(true).Text(FText::FromString(
							TEXT("Everyone you talk to in ASTRA (your officers, the allied captains, the enemy commanders, the admirals running the war) is an AI that thinks "
							     "in real time. They think through OpenRouter, with your own key: make one at openrouter.ai/keys and add a few dollars of credit "
							     "(an hour of play uses about $0.50 to $1). The key stays on this computer, in ASTRA's own data folder, and goes only to openrouter.ai.")))
					]
					+ SVerticalBox::Slot().AutoHeight().Padding(0, 22, 0, 0)
					[
						SAssignNew(Box, SEditableTextBox).IsPassword(true).Font(MonoFont(16))
						.HintText(FText::FromString(TEXT("sk-or-v1-...")))
						.OnTextCommitted_Lambda([this](const FText&, ETextCommit::Type How) { if (How == ETextCommit::OnEnter) { Submit(); } })
					]
					+ SVerticalBox::Slot().AutoHeight().Padding(0, 12, 0, 0)
					[
						SNew(STextBlock).Font(MonoFont(13)).AutoWrapText(true)
						.Text_Lambda([this]() { return FText::FromString(Status); })
						.ColorAndOpacity_Lambda([this]() { return FSlateColor(StatusColour); })
					]
					+ SVerticalBox::Slot().AutoHeight().Padding(0, 24, 0, 0)
					[
						SNew(SHorizontalBox)
						+ SHorizontalBox::Slot().AutoWidth().Padding(0, 0, 12, 0)
						[
							Button(TEXT("PASTE"), [this]()
							{
								FString Clip;
								FPlatformApplicationMisc::ClipboardPaste(Clip);
								if (Box.IsValid())
								{
									Box->SetText(FText::FromString(Clip.TrimStartAndEnd()));
								}
							})
						]
						+ SHorizontalBox::Slot().AutoWidth().Padding(0, 0, 12, 0)
						[
							Button(bChangeMode ? TEXT("VERIFY AND SAVE") : TEXT("VERIFY AND START"), [this]() { Submit(); })
						]
						+ SHorizontalBox::Slot().AutoWidth().Padding(0, 0, 12, 0)
						[
							Button(TEXT("GET A KEY"), []() { FPlatformProcess::LaunchURL(TEXT("https://openrouter.ai/keys"), nullptr, nullptr); })
						]
						+ SHorizontalBox::Slot().FillWidth(1.f) [ SNew(SBox) ]
						+ SHorizontalBox::Slot().AutoWidth()
						[
							Button(bChangeMode ? TEXT("BACK") : TEXT("QUIT"), [this]() { OnCancel.ExecuteIfBound(); })
						]
					]
				]
			]
		]
	];
}

void SAstraKeyGate::CheckSaved()
{
	const FString Key = FAstraApiKey::Read();
	if (Key.IsEmpty())
	{
		return;                                       // (nothing saved: the page waits for one)
	}
	bBusy = true;
	Status = TEXT("Checking your OpenRouter key...");
	StatusColour = KDim;
	TWeakPtr<SAstraKeyGate> Weak = SharedThis(this);
	FAstraApiKey::Verify(Key, [Weak, Key]()
	{
		if (TSharedPtr<SAstraKeyGate> Me = Weak.Pin())
		{
			Me->ShowResult(Key, false);
		}
	});
}

void SAstraKeyGate::Submit()
{
	if (bBusy || !Box.IsValid())
	{
		return;
	}
	const FString Key = Box->GetText().ToString().TrimStartAndEnd();
	bBusy = true;
	Status = TEXT("Checking the key with openrouter.ai...");
	StatusColour = KDim;
	TWeakPtr<SAstraKeyGate> Weak = SharedThis(this);
	FAstraApiKey::Verify(Key, [Weak, Key]()
	{
		if (TSharedPtr<SAstraKeyGate> Me = Weak.Pin())
		{
			Me->ShowResult(Key, true);
		}
	});
}

void SAstraKeyGate::ShowResult(const FString& Key, bool bSave)
{
	bBusy = false;
	Status = FAstraApiKey::Message;
	StatusColour = FAstraApiKey::IsGood() ? KGood : KBad;
	if (FAstraApiKey::IsGood())
	{
		if (bSave)
		{
			FAstraApiKey::Write(Key);
		}
		OnDone.ExecuteIfBound();
	}
}

FReply SAstraKeyGate::OnKeyDown(const FGeometry& Geometry, const FKeyEvent& Key)
{
	if (Key.GetKey() == EKeys::Escape && bChangeMode)
	{
		OnCancel.ExecuteIfBound();
		return FReply::Handled();
	}
	return FReply::Unhandled();
}
