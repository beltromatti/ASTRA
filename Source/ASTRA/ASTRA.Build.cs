// Copyright Epic Games, Inc. All Rights Reserved.

using UnrealBuildTool;

public class ASTRA : ModuleRules
{
	public ASTRA(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

		PublicDependencyModuleNames.AddRange(new string[] {
			"Core",
			"CoreUObject",
			"Engine",
			"InputCore",
			"EnhancedInput",
			"AIModule",
			"StateTreeModule",
			"GameplayStateTreeModule",
			"UMG",
			"Slate",
			"Json",
			"JsonUtilities",
			"WebSockets",
			"ProceduralMeshComponent"   // the ground of any world, generated at run time (AAstraWorldSurface)
		});

		PrivateDependencyModuleNames.AddRange(new string[] { "Slate", "SlateCore", "RenderCore", "RHI", "ApplicationCore", "HTTPServer", "AudioExtensions" });   // font measuring and render fences for the live screens; is the app in front (full screen on the Mac); the playtest harness (AstraHarness); the voices' own procedural wave (AstraVoiceWave)

		PublicIncludePaths.AddRange(new string[] {
			"ASTRA",
		});

		// Uncomment if you are using Slate UI
		// PrivateDependencyModuleNames.AddRange(new string[] { "Slate", "SlateCore" });

		// Uncomment if you are using online features
		// PrivateDependencyModuleNames.Add("OnlineSubsystem");

		// To include OnlineSubsystemSteam, add it to the plugins section in your uproject file with the Enabled attribute set to true
	}
}
