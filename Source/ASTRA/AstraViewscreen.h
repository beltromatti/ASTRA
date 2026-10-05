// The main viewscreen (docs/ARCHITETTURA.md §5): a holographic screen in front of the bow window. It shows what the
// ship's optical sensors see — a real camera placed out beyond the hull and aimed at the subject, zoomed to frame it —
// under a tactical overlay like the Falcon's HUD but richer: brackets and names of the contacts (side, class, range,
// hull and shields when known), the target fire control is on, missiles inbound, arrows for what is out of frame.
// Ops (Tanaka) runs it: the station's viewscreen mode (auto, forward, target, tactical, fleet, sector, comms, damage, off).
// In auto a director follows the action by priority — a ship just destroyed, a heavy hit, tactical's target, the ship
// firing on us, the nearest enemy, and at rest the view ahead and the fleet — each shot held a few seconds. An ordered
// subject that is destroyed or lost gives the screen back to the director (and the station's mode back to auto).

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "AstraBattleSubsystem.h"
#include "AstraViewscreen.generated.h"

class UCanvas;
class UCanvasRenderTarget2D;
class UMaterialInstanceDynamic;
class USceneCaptureComponent2D;
class UProceduralMeshComponent;
class UTextureRenderTarget2D;
class UFont;

UCLASS()
class AAstraViewscreen : public AActor
{
	GENERATED_BODY()

public:
	AAstraViewscreen();
	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;

	/** Screen size in metres (the image plane; the frame belongs to the bridge's art). */
	UPROPERTY(EditAnywhere, Category = "Viewscreen") float WidthM = 7.2f;
	UPROPERTY(EditAnywhere, Category = "Viewscreen") float HeightM = 3.0f;
	/** Feed resolution (the camera): wide, like the screen. A capture renders at 100 % of it whatever the frame's dynamic
	 *  resolution, with its own TSR (1-2 ms at 20 Hz with a hull filling it); from the chair the screen spans 270-470 of the
	 *  frame's pixels (40-70 %), so 640 wide is still oversampled, and the mips keep it from sparkling. */
	UPROPERTY(EditAnywhere, Category = "Viewscreen") int32 FeedWidth = 640;
	UPROPERTY(EditAnywhere, Category = "Viewscreen") int32 FeedHeight = 267;
	/** The overlay's resolution (text and symbols, drawn on a canvas: cheap, and kept crisp). Same aspect as the feed. */
	UPROPERTY(EditAnywhere, Category = "Viewscreen") int32 OverlayWidth = 1280;
	UPROPERTY(EditAnywhere, Category = "Viewscreen") int32 OverlayHeight = 534;

	/** What is on screen now, for the crew and the datapad ("auto: tactical's target T-23 Cocytus, zoom x38"). */
	FString Describe() const;
	/** The contact the screen is showing, when it shows one (the Captain's command wheel takes it as the target he is looking at). */
	FString SubjectId() const { return Shot == EShot::Contact ? ShotId : FString(); }
	/** The image as it is on the screen now, at full resolution, to a PNG (testing: astra.viewscreen.dump). */
	bool Dump(const FString& Path) const;
	/** Testing: log every visible component in the camera's field of view, nearest first (astra.viewscreen.what). */
	void LogWhatIsInView() const;

private:
	UPROPERTY() TObjectPtr<UProceduralMeshComponent> Screen;
	UPROPERTY() TObjectPtr<USceneCaptureComponent2D> Capture;
	UPROPERTY() TObjectPtr<UTextureRenderTarget2D> Feed;
	UPROPERTY() TObjectPtr<UCanvasRenderTarget2D> Overlay;
	UPROPERTY() TObjectPtr<UMaterialInstanceDynamic> Mid;
	UPROPERTY() TObjectPtr<UMaterialInstanceDynamic> FillMid;   // the sensor fill on the capture (M_ASTRA_ViewscreenFill)
	UPROPERTY() TObjectPtr<UFont> Mono;
	UPROPERTY() TObjectPtr<UFont> Title;
	/** A warship's death as the bridge's speakers render what the sensors see (tools/art/battle_cues.py: in the vacuum nothing else is heard). */
	UPROPERTY() TObjectPtr<class USoundBase> KillCue;
	double KillCueAt = -100.0;

	// the shot: what the camera frames, where it is, how wide
	enum class EShot : uint8 { Forward, Contact, Group, Point, Ship, Swarm, Broadside, Off };
	/** The shots that see the Aquila's own hull from outside (the camera's world has it in only for these). */
	bool ShowsOwnHull(EShot S) const { return S == EShot::Ship || S == EShot::Broadside; }
	EShot Shot = EShot::Forward;
	FString ShotId;                    // the contact (Contact)
	FString ShotName;                  // how the caption calls it
	TArray<FString> GroupIds;          // the contacts to frame together (Group)
	double SwarmShotAt = -100.0;       // the last time a salvo coming in had the screen (Swarm: the missiles at the Aquila, framed as they come)
	double BroadsideShotAt = -100.0;   // the last time the Aquila's own fire had the screen (Broadside: her hull from outside, her rounds going away to the target)
	double BroadsideSince = -1.0;      // the broadside shot the camera's side was chosen for
	FVector BroadsideSide = FVector::RightVector;
	FVector ShotPoint = FVector::ZeroVector;   // system frame (Point: where a ship died)
	FString ShotWhy;                   // "TARGET", "FIRING ON US", "DESTROYED", "ORDERED", …
	int32 ShotPri = 0;                 // the director's priority of the shot on screen
	double ShotSince = -100.0;
	double HoldUntil = 0.0;            // no automatic cut to an equal or lower priority before this
	FString Mode = TEXT("auto");       // ops' viewscreen mode
	FString LastModeKey;
	float Zoom = 1.f;                  // ops' zoom on the framing (2 = twice as close)
	int32 IdleIdx = 0;                 // at rest: the view ahead, then the fleet, in turn
	double LostSince = -1.0;           // the ordered subject vanished at (the screen says so, then goes back to auto)
	float Fade = 0.f, FadeWant = 1.f;
	float Fov = 50.f, FovWant = 50.f;
	FVector CamPos = FVector::ZeroVector;      // world (cm)
	FQuat CamRot = FQuat::Identity;
	FQuat FromRot = FQuat::Identity;           // where the camera was when the subject changed (a short pan follows)
	double PanSince = -100.0;
	bool bCamInit = false;
	bool bWatched = true;              // someone on the bridge is looking this way (else nothing is rendered)
	int32 Frame = 0;
	double Now = 0.0;
	// firm tracks seen at the last look (for "just destroyed"): contact -> system position and name
	TMap<FString, TPair<FVector, FString>> LastSeen;
	TMap<FString, float> LastHull;     // hull fraction at the last look
	TMap<FString, float> RecentDamage; // hull lost in the last seconds (decays)
	struct FDeath { FString Id; FString Name; FVector Pos; double At; };
	TArray<FDeath> Deaths;             // destroyed since the last look, waiting for their moment on screen
	struct FBlow { FString Id; FString Name; FString Why; int32 Pri; double At; };
	TArray<FBlow> Blows;               // what the fight just did to a ship worth a look (BATTAGLIA-3's queue): a section gutted, a system out, a shield face down
	struct FArrival { FString Id; bool bHostile; double At; };
	TArray<FArrival> Arrivals;         // warships newly on the plot (a force through the gate, a relief): the screen goes to them once
	double ArrivalShotAt[2] = {-100.0, -100.0};   // the last arrival shot, ASTRA and hostile (a force found two ships at a time is one story)
	/** The plot, as the battle shares it (one list for each step of the battle: UAstraBattleSubsystem::Contacts); read, never kept past the frame. */
	const TArray<UAstraBattleSubsystem::FContactView>* PlotRef = nullptr;
	const TArray<UAstraBattleSubsystem::FContactView>& Plot() const
	{
		static const TArray<UAstraBattleSubsystem::FContactView> None;
		return PlotRef ? *PlotRef : None;
	}
	bool bPushIn = false;              // the next aim starts a little wide and pushes in (a cut)
	double LastCaptureAt = -1.0;       // the last refresh of the feed and the overlay
	float SmoothDt = 0.f;                 // the frame time, smoothed (the feed gives way when frames run long)
	double NextShowListAt = 0.0;       // when the list of what the camera may see is rebuilt
	double NextSizeAt = 0.0;           // when the feed's width is next weighed against the pixels the screen covers on the Captain's view
	double SlowFor = 0.0, GoodFor = 0.0;   // seconds the frame has been running long / holding its pace (the feed's width changes on these, not on a glance)
	/** The camera sees only space (the sky, the Aquila's hull, ships, weapons, wrecks): the bridge, the decks inside and
	 *  the planet's surface zone never enter its scene (half the render thread's work of a capture was theirs). */
	void RebuildShowList();

	void Direct(float Dt);
	void Aim(float DeltaSeconds);
	UFUNCTION() void DrawOverlay(UCanvas* Canvas, int32 Width, int32 Height);
	/** World point -> overlay pixel; false when behind the camera. */
	bool Project(const FVector& World, int32 W, int32 H, FVector2D& Out) const;
	void Cut(EShot NewShot, const FString& Id, const FString& Name, const FString& Why, int32 Pri, double Hold);
	/** Give ops' viewscreen back to the director (the ordered subject is gone). */
	void ReleaseOrder(const FString& Why);
};
