// Copyright ASTRA. Mac only: the module is only ever built for the Mac target (see the .uplugin allow list); on any other
// platform the game keeps TSR and this code does not exist.

using UnrealBuildTool;

public class AstraMetalFX : ModuleRules
{
	public AstraMetalFX(ReadOnlyTargetRules Target) : base(Target)
	{
		// ARC changes the compile environment, so the engine's shared PCH (built without it) cannot be used: the module is
		// small, each file includes what it needs (the same pairing the engine's own ARC modules use).
		PCHUsage = PCHUsageMode.NoPCHs;

		PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine" });

		// Renderer: TemporalUpscaler.h (the third party upscaler interface lives in the renderer's public headers).
		PrivateDependencyModuleNames.AddRange(new string[] { "RenderCore", "Renderer", "RHI", "Projects" });

		if (Target.Platform == UnrealTargetPlatform.Mac)
		{
			bRequiresPlatformSDK = true;

			// The Objective-C++ bridge (AstraMetalFXBridge.mm) uses ARC; nothing else in the module touches Objective-C.
			bEnableObjCAutomaticReferenceCounting = true;

			// IMetalDynamicRHI: the device and RHIRunOnQueue, the only public way to run work on the RHI's Metal queue.
			PrivateDependencyModuleNames.Add("MetalRHI");
			AddEngineThirdPartyPrivateStaticDependencies(Target, "MetalCPP");

			// Weak: a Mac that somehow lacks the framework still launches the game (the bridge checks at run time and falls back to TSR).
			PublicWeakFrameworks.AddRange(new string[] { "Metal", "MetalFX" });
		}
	}
}
