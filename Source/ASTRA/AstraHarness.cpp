#include "AstraHarness.h"
#include "Components/CapsuleComponent.h"
#include "GameFramework/Character.h"
#include "ASTRA.h"
#include "ASTRACharacter.h"
#include "ASTRAPlayerController.h"
#include "AstraCampaign.h"
#include "AstraInput.h"
#include "AstraMindSubsystem.h"
#include "AstraShipSubsystem.h"
#include "Camera/CameraComponent.h"
#include "Dom/JsonObject.h"
#include "EnhancedInputSubsystems.h"
#include "Engine/Engine.h"
#include "Engine/GameInstance.h"
#include "Engine/LocalPlayer.h"
#include "Engine/World.h"
#include "Framework/Application/SlateApplication.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "HAL/FileManager.h"
#include "HttpServerModule.h"
#include "HttpServerRequest.h"
#include "HttpServerResponse.h"
#include "IHttpRouter.h"
#include "InputCoreTypes.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "Misc/ScopeLock.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "UnrealClient.h"

// ------------------------------------------------------------------------------------------------ the timeline
namespace
{
	struct FTimelineEntry
	{
		double Real = 0.0;          // FPlatformTime::Seconds()
		double Game = -1.0;         // the game world's clock (s), -1 before a world
		FString Kind;
		FString Text;
	};
	FCriticalSection GTimelineLock;
	TArray<FTimelineEntry> GTimeline;
	TWeakObjectPtr<UWorld> GTimelineWorld;
	constexpr int32 TimelineMax = 6000;

	FString ToJson(const TSharedRef<FJsonObject>& O)
	{
		FString Out;
		const TSharedRef<TJsonWriter<>> W = TJsonWriterFactory<>::Create(&Out);
		FJsonSerializer::Serialize(O, W);
		return Out;
	}

	TSharedPtr<FJsonObject> ParseBody(const FHttpServerRequest& Req)
	{
		FUTF8ToTCHAR Conv(reinterpret_cast<const ANSICHAR*>(Req.Body.GetData()), Req.Body.Num());
		const FString Text(Conv.Length(), Conv.Get());
		TSharedPtr<FJsonObject> O;
		const TSharedRef<TJsonReader<>> R = TJsonReaderFactory<>::Create(Text);
		if (!FJsonSerializer::Deserialize(R, O) || !O.IsValid())
		{
			O = MakeShared<FJsonObject>();
		}
		return O;
	}

	TUniquePtr<FHttpServerResponse> JsonResponse(const FString& Body)
	{
		return FHttpServerResponse::Create(Body, TEXT("application/json"));
	}
}

void FAstraTimeline::SetWorld(UWorld* World)
{
	GTimelineWorld = World;
}

void FAstraTimeline::Record(const TCHAR* Kind, const FString& Text)
{
	FTimelineEntry E;
	E.Real = FPlatformTime::Seconds();
	if (IsInGameThread())
	{
		if (const UWorld* W = GTimelineWorld.Get())
		{
			E.Game = W->GetTimeSeconds();
		}
	}
	E.Kind = Kind;
	E.Text = Text;
	FScopeLock Lock(&GTimelineLock);
	if (GTimeline.Num() >= TimelineMax)
	{
		GTimeline.RemoveAt(0, TimelineMax / 4, EAllowShrinking::No);
	}
	GTimeline.Add(MoveTemp(E));
}

FString FAstraTimeline::JsonSince(double RealTime, int32 MaxEntries)
{
	TArray<TSharedPtr<FJsonValue>> Arr;
	{
		FScopeLock Lock(&GTimelineLock);
		int32 First = GTimeline.Num();
		while (First > 0 && GTimeline[First - 1].Real > RealTime)
		{
			--First;
		}
		First = FMath::Max(First, GTimeline.Num() - MaxEntries);
		for (int32 i = First; i < GTimeline.Num(); ++i)
		{
			const FTimelineEntry& E = GTimeline[i];
			TSharedRef<FJsonObject> O = MakeShared<FJsonObject>();
			O->SetNumberField(TEXT("real"), E.Real);
			O->SetNumberField(TEXT("game"), E.Game);
			O->SetStringField(TEXT("kind"), E.Kind);
			O->SetStringField(TEXT("text"), E.Text);
			Arr.Add(MakeShared<FJsonValueObject>(O));
		}
	}
	TSharedRef<FJsonObject> Root = MakeShared<FJsonObject>();
	Root->SetNumberField(TEXT("now"), FPlatformTime::Seconds());
	Root->SetArrayField(TEXT("entries"), Arr);
	return ToJson(Root);
}

// ------------------------------------------------------------------------------------------------ the harness
bool UAstraHarness::ShouldCreateSubsystem(UObject* Outer) const
{
#if UE_BUILD_SHIPPING
	return false;
#else
	return FParse::Param(FCommandLine::Get(), TEXT("astra_harness"));
#endif
}

void UAstraHarness::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);
	FParse::Value(FCommandLine::Get(), TEXT("astra_harness_port="), Port);
	TSharedPtr<IHttpRouter> Router = FHttpServerModule::Get().GetHttpRouter(Port, true);
	if (!Router.IsValid())
	{
		UE_LOG(LogASTRA, Error, TEXT("[Harness] cannot listen on port %d"), Port);
		return;
	}
	using EVerb = EHttpServerRequestVerbs;
	auto Bind = [this, &Router](const TCHAR* Path, EVerb Verb, TFunction<FString(const TSharedPtr<FJsonObject>&, const FHttpServerRequest&)> Fn)
	{
		Router->BindRoute(FHttpPath(Path), Verb, FHttpRequestHandler::CreateLambda(
			[Fn](const FHttpServerRequest& Req, const FHttpResultCallback& OnComplete)
			{
				OnComplete(JsonResponse(Fn(ParseBody(Req), Req)));
				return true;
			}));
	};
	Bind(TEXT("/state"), EVerb::VERB_GET, [this](const TSharedPtr<FJsonObject>&, const FHttpServerRequest&)
	{
		return ToJson(StateJson());
	});
	Bind(TEXT("/ship"), EVerb::VERB_GET, [this](const TSharedPtr<FJsonObject>&, const FHttpServerRequest&)
	{
		const UWorld* W = GameWorld();
		const UAstraShipSubsystem* Ship = W ? W->GetSubsystem<UAstraShipSubsystem>() : nullptr;
		return Ship ? ToJson(Ship->Snapshot()) : FString(TEXT("{}"));
	});
	Bind(TEXT("/timeline"), EVerb::VERB_GET, [](const TSharedPtr<FJsonObject>&, const FHttpServerRequest& Req)
	{
		const FString* Since = Req.QueryParams.Find(TEXT("since"));
		return FAstraTimeline::JsonSince(Since ? FCString::Atod(**Since) : 0.0);
	});
	Bind(TEXT("/key"), EVerb::VERB_POST, [this](const TSharedPtr<FJsonObject>& B, const FHttpServerRequest&)
	{
		return Key(B->GetStringField(TEXT("key")), B->HasField(TEXT("action")) ? B->GetStringField(TEXT("action")) : TEXT("tap"),
		           B->HasField(TEXT("hold")) ? B->GetNumberField(TEXT("hold")) : 0.12);
	});
	Bind(TEXT("/look"), EVerb::VERB_POST, [this](const TSharedPtr<FJsonObject>& B, const FHttpServerRequest&)
	{
		return Look(B->HasField(TEXT("yaw")) ? B->GetNumberField(TEXT("yaw")) : 0.0, B->HasField(TEXT("pitch")) ? B->GetNumberField(TEXT("pitch")) : 0.0);
	});
	Bind(TEXT("/say"), EVerb::VERB_POST, [this](const TSharedPtr<FJsonObject>& B, const FHttpServerRequest&)
	{
		const FString Text = B->GetStringField(TEXT("text"));
		UAstraMindSubsystem* Mind = GetGameInstance()->GetSubsystem<UAstraMindSubsystem>();
		if (!Mind || Text.IsEmpty())
		{
			return FString(TEXT("{\"ok\":false}"));
		}
		Mind->SayText(Text);
		return FString(TEXT("{\"ok\":true}"));
	});
	Bind(TEXT("/cmd"), EVerb::VERB_POST, [this](const TSharedPtr<FJsonObject>& B, const FHttpServerRequest&)
	{
		const FString Cmd = B->GetStringField(TEXT("cmd"));
		FAstraTimeline::Record(TEXT("input"), FString::Printf(TEXT("console: %s"), *Cmd));
		APlayerController* P = PC();
		const FString Out = P ? P->ConsoleCommand(Cmd, true) : FString();
		TSharedRef<FJsonObject> O = MakeShared<FJsonObject>();
		O->SetBoolField(TEXT("ok"), P != nullptr);
		O->SetStringField(TEXT("out"), Out.Left(4000));
		return ToJson(O);
	});
	Bind(TEXT("/teleport"), EVerb::VERB_POST, [this](const TSharedPtr<FJsonObject>& B, const FHttpServerRequest&)
	{
		// the Captain on foot at a point of the bridge frame (metres; z = the feet), looking along yaw/pitch: for pictures
		APlayerController* P = PC();
		AASTRAPlayerController* AP = Cast<AASTRAPlayerController>(P);
		if (AP)
		{
			AP->StandUp();
		}
		ACharacter* C = P ? Cast<ACharacter>(P->GetPawn()) : nullptr;
		if (!C)
		{
			return FString(TEXT("{\"ok\":false}"));
		}
		const float Half = C->GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
		const FVector At(B->GetNumberField(TEXT("x")) * 100.0, B->GetNumberField(TEXT("y")) * 100.0,
		                 (B->HasField(TEXT("z")) ? B->GetNumberField(TEXT("z")) : 0.0) * 100.0 + Half + 2.0);
		C->SetActorLocation(At, false, nullptr, ETeleportType::TeleportPhysics);
		P->SetControlRotation(FRotator(B->HasField(TEXT("pitch")) ? B->GetNumberField(TEXT("pitch")) : 0.0, B->HasField(TEXT("yaw")) ? B->GetNumberField(TEXT("yaw")) : 0.0, 0.0));
		FAstraTimeline::Record(TEXT("input"), FString::Printf(TEXT("teleport %.1f %.1f %.1f"), At.X / 100.0, At.Y / 100.0, At.Z / 100.0));
		return FString(TEXT("{\"ok\":true}"));
	});
	Bind(TEXT("/shot"), EVerb::VERB_POST, [this](const TSharedPtr<FJsonObject>& B, const FHttpServerRequest&)
	{
		return Shot(B->GetStringField(TEXT("path")), !B->HasField(TEXT("ui")) || B->GetBoolField(TEXT("ui")));
	});
	Bind(TEXT("/quit"), EVerb::VERB_POST, [](const TSharedPtr<FJsonObject>&, const FHttpServerRequest&)
	{
		FAstraTimeline::Record(TEXT("input"), TEXT("quit"));
		FPlatformMisc::RequestExit(false, TEXT("AstraHarness"));
		return FString(TEXT("{\"ok\":true}"));
	});
	FHttpServerModule::Get().StartAllListeners();
	TickHandle = FTSTicker::GetCoreTicker().AddTicker(FTickerDelegate::CreateUObject(this, &UAstraHarness::Tick), 0.f);
	bStarted = true;
	UE_LOG(LogASTRA, Display, TEXT("[Harness] listening on http://127.0.0.1:%d"), Port);
}

void UAstraHarness::Deinitialize()
{
	if (TickHandle.IsValid())
	{
		FTSTicker::GetCoreTicker().RemoveTicker(TickHandle);
	}
	if (UWorld* W = BoundWorld.Get())
	{
		if (UAstraShipSubsystem* Ship = W->GetSubsystem<UAstraShipSubsystem>())
		{
			Ship->OnShipEvent.Remove(ShipEventHandle);
		}
	}
	if (bStarted)
	{
		FHttpServerModule::Get().StopAllListeners();
	}
	Super::Deinitialize();
}

UWorld* UAstraHarness::GameWorld() const
{
	const UGameInstance* GI = GetGameInstance();
	return GI ? GI->GetWorld() : nullptr;
}

APlayerController* UAstraHarness::PC() const
{
	const UWorld* W = GameWorld();
	return W ? W->GetFirstPlayerController() : nullptr;
}

void UAstraHarness::BindWorld()
{
	UWorld* W = GameWorld();
	if (!W || BoundWorld.Get() == W)
	{
		return;
	}
	if (UAstraShipSubsystem* Ship = W->GetSubsystem<UAstraShipSubsystem>())
	{
		BoundWorld = W;
		FAstraTimeline::SetWorld(W);
		ShipEventHandle = Ship->OnShipEvent.AddLambda([](const FString& Text, bool bReport)
		{
			FAstraTimeline::Record(bReport ? TEXT("report") : TEXT("event"), Text);
		});
	}
}

bool UAstraHarness::Tick(float DeltaTime)
{
	BindWorld();
	if (DeltaTime > 0.f)
	{
		FpsAvg = FpsAvg <= 0.0 ? 1.0 / DeltaTime : FMath::Lerp(FpsAvg, 1.0 / DeltaTime, 0.05);
	}
	// keys held by /key … hold=N come back up on time
	const double Now = FPlatformTime::Seconds();
	for (int32 i = Releases.Num() - 1; i >= 0; --i)
	{
		if (Now >= Releases[i].At)
		{
			SendKey(FKey(*Releases[i].Key), false);
			Releases.RemoveAtSwap(i);
		}
	}
	return true;
}

void UAstraHarness::SendKey(const FKey& Key, bool bDown)
{
	if (!FSlateApplication::IsInitialized())
	{
		return;
	}
	FSlateApplication& App = FSlateApplication::Get();
	if (Key.IsMouseButton())
	{
		const FPointerEvent E(0, App.GetCursorPos(), App.GetLastCursorPos(), App.GetPressedMouseButtons(), Key, 0.f, App.GetModifierKeys());
		bDown ? App.ProcessMouseButtonDownEvent(nullptr, E) : App.ProcessMouseButtonUpEvent(E);
		return;
	}
	const FKeyEvent E(Key, App.GetModifierKeys(), 0, false, 0, 0);
	bDown ? App.ProcessKeyDownEvent(E) : App.ProcessKeyUpEvent(E);
}

FString UAstraHarness::Key(const FString& KeyName, const FString& Action, double Hold)
{
	const FKey K(*KeyName);
	if (!K.IsValid())
	{
		return FString::Printf(TEXT("{\"ok\":false,\"error\":\"unknown key %s\"}"), *KeyName);
	}
	FAstraTimeline::Record(TEXT("input"), FString::Printf(TEXT("key %s %s %.2f"), *KeyName, *Action, Hold));
	if (Action == TEXT("down"))
	{
		SendKey(K, true);
	}
	else if (Action == TEXT("up"))
	{
		SendKey(K, false);
	}
	else
	{
		// tap or hold: down now, up after the hold (at least one frame later)
		SendKey(K, true);
		Releases.Add({KeyName, FPlatformTime::Seconds() + FMath::Max(Hold, 0.05)});
	}
	return TEXT("{\"ok\":true}");
}

FString UAstraHarness::Look(double YawDeg, double PitchDeg)
{
	AASTRAPlayerController* P = Cast<AASTRAPlayerController>(PC());
	if (!P || !P->GetLocalPlayer())
	{
		return TEXT("{\"ok\":false}");
	}
	FAstraTimeline::Record(TEXT("input"), FString::Printf(TEXT("look yaw %+.1f pitch %+.1f"), YawDeg, PitchDeg));
	// through the same action the mouse drives: the character adds the value as yaw and pitch input, and the
	// controller's legacy scales multiply it (yaw ×2.5, pitch ×−2.5), so the action value is (yaw/2.5, −pitch/2.5)
	if (UEnhancedInputLocalPlayerSubsystem* S = ULocalPlayer::GetSubsystem<UEnhancedInputLocalPlayerSubsystem>(P->GetLocalPlayer()))
	{
		const UAstraInputSet* In = P->GetInputSet();
		if (In && P->GetPawn() && P->GetPawn()->IsA<AASTRACharacter>())
		{
			S->InjectInputForAction(In->MouseLook, FInputActionValue(FVector2D(YawDeg / 2.5, -PitchDeg / 2.5)), {}, {});
			return TEXT("{\"ok\":true}");
		}
	}
	// any other pawn (a Falcon, a lifepod): turn the view directly
	P->SetControlRotation(P->GetControlRotation() + FRotator(PitchDeg, YawDeg, 0.0));
	return TEXT("{\"ok\":true,\"direct\":true}");
}

FString UAstraHarness::Shot(const FString& Path, bool bShowUI)
{
	if (Path.IsEmpty())
	{
		return TEXT("{\"ok\":false,\"error\":\"path\"}");
	}
	IFileManager::Get().Delete(*Path, false, true, true);
	FScreenshotRequest::RequestScreenshot(Path, bShowUI, false);
	FAstraTimeline::Record(TEXT("input"), FString::Printf(TEXT("screenshot %s"), *FPaths::GetCleanFilename(Path)));
	return TEXT("{\"ok\":true}");
}

TSharedRef<FJsonObject> UAstraHarness::StateJson() const
{
	TSharedRef<FJsonObject> O = MakeShared<FJsonObject>();
	const UWorld* W = GameWorld();
	O->SetNumberField(TEXT("real"), FPlatformTime::Seconds());
	O->SetNumberField(TEXT("game"), W ? W->GetTimeSeconds() : -1.0);
	O->SetNumberField(TEXT("fps"), FMath::RoundToDouble(FpsAvg * 10.0) / 10.0);
	O->SetStringField(TEXT("map"), W ? W->GetMapName() : FString());
	O->SetBoolField(TEXT("paused"), W && W->IsPaused());
	const UAstraCampaignSubsystem* Camp = W ? W->GetSubsystem<UAstraCampaignSubsystem>() : nullptr;
	O->SetBoolField(TEXT("menu"), Camp && Camp->IsMenuOpen());
	O->SetBoolField(TEXT("campaign"), Camp && Camp->IsStarted());
	const AASTRAPlayerController* P = Cast<AASTRAPlayerController>(PC());
	if (P)
	{
		TSharedRef<FJsonObject> Pw = MakeShared<FJsonObject>();
		const APawn* Pawn = P->GetPawn();
		Pw->SetStringField(TEXT("class"), Pawn ? Pawn->GetClass()->GetName() : FString());
		const FRotator R = P->GetControlRotation();
		Pw->SetNumberField(TEXT("yaw"), FMath::RoundToDouble(R.Yaw * 10.0) / 10.0);
		Pw->SetNumberField(TEXT("pitch"), FMath::RoundToDouble(FRotator::NormalizeAxis(R.Pitch) * 10.0) / 10.0);
		Pw->SetBoolField(TEXT("seated"), P->IsSeated());
		if (Pawn)
		{
			const FVector L = Pawn->GetActorLocation() / 100.0;
			Pw->SetArrayField(TEXT("loc_m"), {MakeShared<FJsonValueNumber>(FMath::RoundToDouble(L.X * 100.0) / 100.0),
			                                  MakeShared<FJsonValueNumber>(FMath::RoundToDouble(L.Y * 100.0) / 100.0),
			                                  MakeShared<FJsonValueNumber>(FMath::RoundToDouble(L.Z * 100.0) / 100.0)});
			Pw->SetNumberField(TEXT("speed_mps"), FMath::RoundToDouble(Pawn->GetVelocity().Size2D()) / 100.0);
		}
		if (const AASTRACharacter* C = Cast<AASTRACharacter>(Pawn))
		{
			static const TCHAR* Postures[] = {TEXT("standing"), TEXT("crouched"), TEXT("prone")};
			Pw->SetStringField(TEXT("posture"), Postures[(int32)C->GetPosture()]);
			Pw->SetBoolField(TEXT("sprinting"), C->IsSprinting());
			Pw->SetNumberField(TEXT("eye_z_m"), FMath::RoundToDouble(C->GetFirstPersonCameraComponent()->GetComponentLocation().Z) / 100.0);
		}
		O->SetObjectField(TEXT("pawn"), Pw);
		if (const UAstraShipSubsystem* Ship = W->GetSubsystem<UAstraShipSubsystem>())
		{
			O->SetObjectField(TEXT("context"), Ship->CaptainContext());   // what the mind gets with the Captain's words
		}
	}
	return O;
}
