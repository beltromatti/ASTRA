// Drives the plugin's own Metal code (AstraMetalFXCore.mm, compiled into this program, no Unreal) the way the game does:
// textures allocated from a TRACKED placement heap with Unreal's usage flags, bigger than the rendered rectangle, depth as
// Depth32Float_Stencil8, UNORM velocity, frames committed back to back without waiting (the MetalFX command buffer sits in
// between the "renderer's" command buffers and only Metal's hazard tracking orders them), content rectangles that vary
// (dynamic resolution) or do not start at the corner, bad frames that must be refused.
// Exits non-zero when a check fails. Usage: probe_core
#include "probe_scene.h"
#include "../../Plugins/AstraMetalFX/Source/AstraMetalFX/Private/AstraMetalFXCore.mm"

using namespace AstraMetalFX::Core;

static int GFailures = 0;
static void Check(bool bOk, const char* What)
{
	printf("  [%s] %s\n", bOk ? "ok" : "FAIL", What);
	if (!bOk) ++GFailures;
}

static const char* kSrcDepthFill = R"MSL(
#include <metal_stdlib>
using namespace metal;
struct VOut { float4 Pos [[position]]; };
vertex VOut fs_vs(uint Vid [[vertex_id]]) { float2 P = float2(float((Vid << 1) & 2), float(Vid & 2)); VOut O; O.Pos = float4(P * 2.0 - 1.0, 0.0, 1.0); return O; }
struct FOut { float Depth [[depth(any)]]; };
fragment FOut fs_depth(VOut In [[stage_in]], texture2d<float, access::read> Src [[texture(0)]]) { FOut O; O.Depth = Src.read(uint2(In.Pos.xy)).x; return O; }
kernel void fill_eye(texture2d<float, access::write> Out [[texture(0)]], constant float& E [[buffer(0)]], uint2 gid [[thread_position_in_grid]]) { Out.write(float4(E, 0, 0, 1.0), gid); }
kernel void clear_velocity(texture2d<float, access::write> Out [[texture(0)]], uint2 gid [[thread_position_in_grid]])
{ if (gid.x < Out.get_width() && gid.y < Out.get_height()) Out.write(float4(0.0), gid); }
)MSL";

// A tracked placement heap, like Unreal's resource heap.
struct FHeap
{
	id<MTLDevice> Dev;
	id<MTLHeap> Heap;
	size_t Used = 0;
	void Init(id<MTLDevice> D, size_t Bytes)
	{
		Dev = D;
		MTLHeapDescriptor* HD = [MTLHeapDescriptor new];
		HD.type = MTLHeapTypePlacement; HD.storageMode = MTLStorageModePrivate; HD.hazardTrackingMode = MTLHazardTrackingModeTracked; HD.size = Bytes;
		Heap = [D newHeapWithDescriptor:HD];
	}
	id<MTLTexture> Alloc(MTLPixelFormat Fmt, int W, int H, MTLTextureUsage Usage, bool bTracked = true)
	{
		MTLTextureDescriptor* D = [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:Fmt width:W height:H mipmapped:NO];
		D.usage = Usage; D.storageMode = MTLStorageModePrivate;
		D.hazardTrackingMode = bTracked ? MTLHazardTrackingModeTracked : MTLHazardTrackingModeUntracked;
		MTLSizeAndAlign SA = [Dev heapTextureSizeAndAlignWithDescriptor:D];
		size_t Off = (Used + SA.align - 1) / SA.align * SA.align;
		Used = Off + SA.size;
		id<MTLTexture> T = [Heap newTextureWithDescriptor:D offset:Off];
		if (!T) { printf("heap out of memory\n"); exit(3); }
		return T;
	}
};

struct FRig
{
	id<MTLDevice> Dev; id<MTLCommandQueue> Q;
	FHeap Heap;
	id<MTLComputePipelineState> PsoRender, PsoFillEye, PsoClearVel;
	id<MTLRenderPipelineState> RPS; id<MTLDepthStencilState> DSS;
	double HalfFov = 45.0 * M_PI / 180.0; float MinZ = 5.0f;

	void Init()
	{
		Dev = MTLCreateSystemDefaultDevice(); Q = [Dev newCommandQueue];
		Heap.Init(Dev, 768ull * 1024 * 1024);
		id<MTLLibrary> Lib = MakeLib(Dev, kSrcScene), DLib = MakeLib(Dev, kSrcDepthFill);
		PsoRender = MakePSO(Dev, Lib, "e2e_render"); PsoFillEye = MakePSO(Dev, DLib, "fill_eye"); PsoClearVel = MakePSO(Dev, DLib, "clear_velocity");
		MTLRenderPipelineDescriptor* RPD = [MTLRenderPipelineDescriptor new];
		RPD.vertexFunction = [DLib newFunctionWithName:@"fs_vs"]; RPD.fragmentFunction = [DLib newFunctionWithName:@"fs_depth"];
		RPD.depthAttachmentPixelFormat = MTLPixelFormatDepth32Float_Stencil8; RPD.stencilAttachmentPixelFormat = MTLPixelFormatDepth32Float_Stencil8;
		NSError* Err = nil; RPS = [Dev newRenderPipelineStateWithDescriptor:RPD error:&Err];
		MTLDepthStencilDescriptor* DSD = [MTLDepthStencilDescriptor new]; DSD.depthCompareFunction = MTLCompareFunctionAlways; DSD.depthWriteEnabled = YES;
		DSS = [Dev newDepthStencilStateWithDescriptor:DSD];
	}
};

// One set of "Unreal" textures: bigger than the content, content at (MinX, MinY).
struct FTextures
{
	int ExtW, ExtH, OutW, OutH;
	id<MTLTexture> Color, Depth, DepthR32, Velocity, Eye, Output;
	id<MTLTexture> SmallColor, SmallDepth;   // the content-sized render targets of the scene kernel
};

static FTextures MakeTextures(FRig& R, int ExtW, int ExtH, int OutW, int OutH, int ContentMaxW, int ContentMaxH)
{
	FTextures T{};
	T.ExtW = ExtW; T.ExtH = ExtH; T.OutW = OutW; T.OutH = OutH;
	const MTLTextureUsage RW = MTLTextureUsageShaderRead | MTLTextureUsageShaderWrite;
	T.Color = R.Heap.Alloc(MTLPixelFormatRGBA16Float, ExtW, ExtH, RW | MTLTextureUsageRenderTarget);
	T.Depth = R.Heap.Alloc(MTLPixelFormatDepth32Float_Stencil8, ExtW, ExtH, MTLTextureUsageShaderRead | MTLTextureUsageRenderTarget);
	T.DepthR32 = R.Heap.Alloc(MTLPixelFormatR32Float, ExtW, ExtH, RW);
	T.Velocity = R.Heap.Alloc(MTLPixelFormatRGBA16Unorm, ExtW, ExtH, RW | MTLTextureUsageRenderTarget);
	T.Eye = R.Heap.Alloc(MTLPixelFormatRGBA32Float, 1, 1, RW);
	T.Output = R.Heap.Alloc(MTLPixelFormatRGBA16Float, OutW, OutH, RW | MTLTextureUsageRenderTarget);
	T.SmallColor = R.Heap.Alloc(MTLPixelFormatRGBA16Float, ContentMaxW, ContentMaxH, RW);
	T.SmallDepth = R.Heap.Alloc(MTLPixelFormatR32Float, ContentMaxW, ContentMaxH, RW);
	float One = 1.0f;
	RunCB(R.Q, ^(id<MTLCommandBuffer> CB) {
		id<MTLComputeCommandEncoder> E = [CB computeCommandEncoder];
		[E setComputePipelineState:R.PsoClearVel]; [E setTexture:T.Velocity atIndex:0]; Dispatch2D(E, R.PsoClearVel, ExtW, ExtH);
		[E setComputePipelineState:R.PsoFillEye]; [E setTexture:T.Eye atIndex:0]; [E setBytes:&One length:4 atIndex:0]; [E dispatchThreadgroups:MTLSizeMake(1, 1, 1) threadsPerThreadgroup:MTLSizeMake(1, 1, 1)];
		[E endEncoding];
	});
	return T;
}

// Renders frame F of the scene at CW x CH into the big textures at (MinX, MinY); returns the camera matrices for the motion.
static void RenderInputs(FRig& R, FTextures& T, int F, int CW, int CH, int MinX, int MinY, float Jx, float Jy, float OutC2P[16])
{
	Camera Cur = CameraAt(F), Prev = CameraAt(F > 0 ? F - 1 : 0);
	E2EParams SP = MakeScene(Cur, CW, CH, R.HalfFov, R.MinZ, Jx, Jy, 1);
	Mat ProjCur = ReversedZPerspective(R.HalfFov, CW, CH, R.MinZ), ProjPrev = ProjCur;
	double PVTCur[3] = { -Cur.Pos[0], -Cur.Pos[1], -Cur.Pos[2] }, PVTPrev[3] = { -Prev.Pos[0], -Prev.Pos[1], -Prev.Pos[2] };
	Mat C2P = ClipToPrevClip(ProjCur, TranslatedViewMatrix(Cur), PVTCur, ProjPrev, TranslatedViewMatrix(Prev), PVTPrev);
	for (int i = 0; i < 4; ++i) for (int j = 0; j < 4; ++j) OutC2P[i * 4 + j] = (float)C2P.M[i][j];

	id<MTLCommandBuffer> CB = [R.Q commandBuffer];
	{
		id<MTLComputeCommandEncoder> E = [CB computeCommandEncoder];
		[E setComputePipelineState:R.PsoRender]; [E setTexture:T.SmallColor atIndex:0]; [E setTexture:T.SmallDepth atIndex:1]; [E setBytes:&SP length:sizeof SP atIndex:0];
		Dispatch2D(E, R.PsoRender, CW, CH);
		[E endEncoding];
	}
	{
		id<MTLBlitCommandEncoder> B = [CB blitCommandEncoder];
		[B copyFromTexture:T.SmallColor sourceSlice:0 sourceLevel:0 sourceOrigin:MTLOriginMake(0, 0, 0) sourceSize:MTLSizeMake(CW, CH, 1) toTexture:T.Color destinationSlice:0 destinationLevel:0 destinationOrigin:MTLOriginMake(MinX, MinY, 0)];
		[B copyFromTexture:T.SmallDepth sourceSlice:0 sourceLevel:0 sourceOrigin:MTLOriginMake(0, 0, 0) sourceSize:MTLSizeMake(CW, CH, 1) toTexture:T.DepthR32 destinationSlice:0 destinationLevel:0 destinationOrigin:MTLOriginMake(MinX, MinY, 0)];
		[B endEncoding];
	}
	{
		MTLRenderPassDescriptor* RP = [MTLRenderPassDescriptor renderPassDescriptor];
		RP.depthAttachment.texture = T.Depth; RP.depthAttachment.loadAction = MTLLoadActionClear; RP.depthAttachment.storeAction = MTLStoreActionStore;
		RP.stencilAttachment.texture = T.Depth; RP.stencilAttachment.loadAction = MTLLoadActionClear; RP.stencilAttachment.storeAction = MTLStoreActionStore;
		id<MTLRenderCommandEncoder> E = [CB renderCommandEncoderWithDescriptor:RP];
		[E setRenderPipelineState:R.RPS]; [E setDepthStencilState:R.DSS]; [E setFragmentTexture:T.DepthR32 atIndex:0];
		[E drawPrimitives:MTLPrimitiveTypeTriangle vertexStart:0 vertexCount:3];
		[E endEncoding];
	}
	[CB commit];   // not waited for: the MetalFX command buffer is committed right behind it, as in the game
}

static std::shared_ptr<FFrameInput> MakeFrame(const FTextures& T, int CW, int CH, int MinX, int MinY, float Jx, float Jy, const float C2P[16], bool bReset, bool bVelocity, bool bEye)
{
	auto F = std::make_shared<FFrameInput>();
	F->Color = T.Color; F->Depth = T.Depth; F->Velocity = bVelocity ? T.Velocity : nil; F->Eye = bEye ? T.Eye : nil; F->Output = T.Output;
	F->ViewMinX = MinX; F->ViewMinY = MinY; F->ViewW = CW; F->ViewH = CH; F->JitterX = Jx; F->JitterY = Jy; F->PreExposure = 1.0f;
	memcpy(F->ClipToPrevClip, C2P, 64); F->bReset = bReset;
	return F;
}

static void WaitAll(FRig& R)
{
	RunCB(R.Q, ^(id<MTLCommandBuffer>) {});
	for (int i = 0; i < 2000 && FScaler::CommandBuffersInFlight() > 0; ++i) usleep(1000);
}

static std::vector<float> Luma(FRig& R, id<MTLTexture> T, int W, int H)
{
	id<MTLTexture> Sh = MakeTex2D(R.Dev, MTLPixelFormatRGBA16Float, W, H, MTLTextureUsageShaderRead, MTLStorageModeShared);
	RunCB(R.Q, ^(id<MTLCommandBuffer> CB) { id<MTLBlitCommandEncoder> B = [CB blitCommandEncoder]; [B copyFromTexture:T toTexture:Sh]; [B endEncoding]; });
	std::vector<_Float16> Raw((size_t)W * H * 4);
	[Sh getBytes:Raw.data() bytesPerRow:(size_t)W * 8 fromRegion:MTLRegionMake2D(0, 0, W, H) mipmapLevel:0];
	std::vector<float> L((size_t)W * H);
	for (size_t i = 0; i < L.size(); ++i) L[i] = 0.3f * (float)Raw[i * 4] + 0.6f * (float)Raw[i * 4 + 1] + 0.1f * (float)Raw[i * 4 + 2];
	return L;
}

static double Psnr(const std::vector<float>& A, const std::vector<float>& GT, int W, int H)
{
	double Se = 0; size_t N = 0;
	for (int y = 40; y < H - 40; ++y) for (int x = 40; x < W - 40; ++x) { double D = (double)A[(size_t)y * W + x] - GT[(size_t)y * W + x]; Se += D * D; ++N; }
	return 10.0 * log10(1.0 / (Se / (double)N));
}

int main()
{
	@autoreleasepool
	{
		const int OutW = 960, OutH = 540;
		FRig R; R.Init();
		std::vector<std::string> Logs;
		SetLogger([&](ELogLevel L, const std::string& S) { Logs.push_back(S); printf("    core log [%s]: %s\n", L == ELogLevel::Log ? "log" : (L == ELogLevel::Warning ? "warning" : "ERROR"), S.c_str()); });

		printf("create\n");
		std::string Err;
		double T0 = NowMs();
		std::shared_ptr<FScaler> S = FScaler::Create(R.Dev, OutW, OutH, Err);
		printf("  created in %.0f ms\n", NowMs() - T0);
		Check(S != nullptr && Err.empty(), "scaler created");
		if (!S) return 2;
		Check(S->MinScale() >= 1.0f && S->MaxScale() >= 3.0f, "device scale range covers 1x..3x");
		Check(FScaler::QueryUnsupportedReason(R.Dev).empty(), "device supports MetalFX");

		// Ground truth of the last frame for the quality checks.
		const int Frames = 48;
		id<MTLTexture> GTc = MakeTex2D(R.Dev, MTLPixelFormatRGBA16Float, OutW, OutH, MTLTextureUsageShaderRead | MTLTextureUsageShaderWrite);
		id<MTLTexture> GTd = MakeTex2D(R.Dev, MTLPixelFormatR32Float, OutW, OutH, MTLTextureUsageShaderRead | MTLTextureUsageShaderWrite);
		E2EParams GP = MakeScene(CameraAt(Frames - 1), OutW, OutH, R.HalfFov, R.MinZ, 0, 0, 4);
		RunCB(R.Q, ^(id<MTLCommandBuffer> CB) { id<MTLComputeCommandEncoder> E = [CB computeCommandEncoder]; [E setComputePipelineState:R.PsoRender]; [E setTexture:GTc atIndex:0]; [E setTexture:GTd atIndex:1]; [E setBytes:&GP length:sizeof GP atIndex:0]; Dispatch2D(E, R.PsoRender, OutW, OutH); [E endEncoding]; });
		std::vector<float> GT = Luma(R, GTc, OutW, OutH);

		printf("validate\n");
		{
			FTextures T = MakeTextures(R, 1024, 600, OutW, OutH, 600, 340);
			float C2P[16] = {}; RenderInputs(R, T, 0, 528, 297, 0, 0, 0, 0, C2P); WaitAll(R);
			auto F = MakeFrame(T, 528, 297, 0, 0, 0, 0, C2P, true, true, true);
			Check(S->Validate(*F).empty(), "a frame of Unreal-like textures is accepted");
			auto Bad = [&](const char* What, auto Mutate, const char* Expect) {
				auto B = std::make_shared<FFrameInput>(*F); Mutate(*B);
				std::string P = S->Validate(*B);
				char Buf[256]; snprintf(Buf, sizeof Buf, "%s is refused (%s)", What, P.c_str());
				Check(!P.empty() && (Expect == nullptr || P.find(Expect) != std::string::npos), Buf);
			};
			Bad("a missing color texture", [&](FFrameInput& B) { B.Color = nil; }, "no native");
			Bad("an untracked color texture", [&](FFrameInput& B) {
				MTLTextureDescriptor* D = [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:MTLPixelFormatRGBA16Float width:1024 height:600 mipmapped:NO];
				D.usage = MTLTextureUsageShaderRead | MTLTextureUsageShaderWrite; D.storageMode = MTLStorageModePrivate; D.hazardTrackingMode = MTLHazardTrackingModeUntracked;
				B.Color = [R.Dev newTextureWithDescriptor:D]; }, "hazard tracked");
			Bad("an RGBA8 color texture", [&](FFrameInput& B) { B.Color = R.Heap.Alloc(MTLPixelFormatRGBA8Unorm, 1024, 600, MTLTextureUsageShaderRead); }, "RGBA16F");
			Bad("a Depth32Float depth texture", [&](FFrameInput& B) { B.Depth = R.Heap.Alloc(MTLPixelFormatDepth32Float, 1024, 600, MTLTextureUsageShaderRead | MTLTextureUsageRenderTarget); }, "Depth32Float_Stencil8");
			Bad("an output of the wrong size", [&](FFrameInput& B) { B.Output = R.Heap.Alloc(MTLPixelFormatRGBA16Float, OutW + 8, OutH, MTLTextureUsageShaderRead | MTLTextureUsageShaderWrite | MTLTextureUsageRenderTarget); }, "output texture");
			Bad("an output without the render target usage", [&](FFrameInput& B) { B.Output = R.Heap.Alloc(MTLPixelFormatRGBA16Float, OutW, OutH, MTLTextureUsageShaderRead | MTLTextureUsageShaderWrite); }, "usage");
			Bad("a rectangle that does not fit", [&](FFrameInput& B) { B.ViewMinX = 600; B.ViewW = 528; }, "does not fit");
			Bad("an empty rectangle", [&](FFrameInput& B) { B.ViewW = 0; }, "does not fit");
		}

		// Runs the scene through the scaler with the given textures/content and returns the PSNR of the last frame's output.
		auto RunScene = [&](const char* Label, FTextures& T, std::shared_ptr<FScaler> Sc, auto ContentOf, int MinX, int MinY, bool bVel, bool bEye, EDebugMode Debug = EDebugMode::Off) -> double {
			double Ms0 = NowMs();
			for (int F = 0; F < Frames; ++F)
			{
				int CW, CH; ContentOf(F, CW, CH);
				float Jx = Halton(F % 26 + 1, 2) - 0.5f, Jy = Halton(F % 26 + 1, 3) - 0.5f;
				float C2P[16]; RenderInputs(R, T, F, CW, CH, MinX, MinY, Jx, Jy, C2P);
				auto Fr = MakeFrame(T, CW, CH, MinX, MinY, Jx, Jy, C2P, F == 0, bVel, bEye);
				Fr->Debug = Debug;
				std::string P = Sc->Validate(*Fr);
				if (!P.empty()) { printf("    refused: %s\n", P.c_str()); return -1; }
				Sc->Encode(R.Q, Fr);   // committed at once, not waited for
			}
			WaitAll(R);
			double Psnr_ = Psnr(Luma(R, T.Output, OutW, OutH), GT, OutW, OutH);
			printf("  %-60s PSNR %.2f dB (%d frames in %.0f ms wall)\n", Label, Psnr_, Frames, NowMs() - Ms0);
			return Psnr_;
		};

		printf("quality, frames committed back to back (the scaler's command buffer sits between the renderer's)\n");
		const int CW0 = 528, CH0 = 297;   // 55%
		FTextures Tight = MakeTextures(R, CW0, CH0, OutW, OutH, CW0, CH0);
		double PTight = RunScene("textures exactly the rendered size, no velocity texture", Tight, S, [&](int, int& W, int& H) { W = CW0; H = CH0; }, 0, 0, false, false);
		Check(PTight > 19.0, "converges to the ground truth (> 19 dB, the probe_e2e level)");

		FTextures Big = MakeTextures(R, 1024, 600, OutW, OutH, CW0, CH0);
		double PBig = RunScene("textures bigger than the content (Unreal's upper bound)", Big, S, [&](int, int& W, int& H) { W = CW0; H = CH0; }, 0, 0, true, true);
		Check(fabs(PBig - PTight) < 0.4, "same image with bigger textures, a zero velocity texture and an eye adaptation texture");

		FTextures Off = MakeTextures(R, 1024, 600, OutW, OutH, CW0, CH0);
		double POff = RunScene("content at (24, 16) of the textures (the copy path)", Off, S, [&](int, int& W, int& H) { W = CW0; H = CH0; }, 24, 16, true, false);
		Check(fabs(POff - PTight) < 0.4, "a rectangle that does not start at the corner gives the same image");

		FTextures Dyn = MakeTextures(R, 1024, 600, OutW, OutH, 672, 378);
		double PDyn = RunScene("dynamic resolution, 40%..70% changing every frame", Dyn, S, [&](int F, int& W, int& H) { float Fr = 0.42f + 0.28f * (0.5f + 0.5f * sinf(F * 0.7f)); W = (int)ceilf(OutW * Fr); H = (int)ceilf(OutH * Fr); }, 0, 0, true, true);
		Check(PDyn > 17.5, "dynamic resolution still converges (> 17.5 dB)");

		printf("timings\n");
		FTimings Tm = S->Timings();
		printf("  %llu frames completed, last %.3f ms, average %.3f ms, %llu errors\n", Tm.Frames, Tm.LastMs, Tm.AverageMs, Tm.Errors);
		Check(Tm.Frames >= (uint64_t)Frames * 4 && Tm.Errors == 0 && Tm.AverageMs > 0.0f, "the completion handlers counted every frame, no errors");
		Check(FScaler::CommandBuffersInFlight() == 0, "no command buffer left in flight");

		printf("debug views\n");
		{
			std::vector<float> Normal = Luma(R, Dyn.Output, OutW, OutH);
			RunScene("motion vectors view", Big, S, [&](int, int& W, int& H) { W = CW0; H = CH0; }, 0, 0, true, true, EDebugMode::Motion);
			std::vector<float> Motion = Luma(R, Big.Output, OutW, OutH);
			double Diff = 0; for (size_t i = 0; i < Normal.size(); ++i) Diff += fabs(Normal[i] - Motion[i]);
			Check(Diff / Normal.size() > 0.01, "the motion view draws something different from the upscaled image");
		}

		printf("out of range rectangles are clamped, not passed to MetalFX\n");
		{
			std::shared_ptr<FScaler> S2 = FScaler::Create(R.Dev, OutW, OutH, Err);
			FTextures T = MakeTextures(R, 1024, 600, OutW, OutH, 1024, 600);
			float C2P[16]; RenderInputs(R, T, 0, 1024, 600, 0, 0, 0, 0, C2P);
			WaitAll(R);
			size_t Before = Logs.size();
			S2->Encode(R.Q, MakeFrame(T, 1024, 600, 0, 0, 0, 0, C2P, true, false, false));   // bigger than the output
			S2->Encode(R.Q, MakeFrame(T, 160, 90, 0, 0, 0, 0, C2P, false, false, false));     // scale 6
			WaitAll(R);
			Check(!S2->Failed() && S2->Timings().Errors == 0 && S2->Timings().Frames == 2, "two out-of-range frames completed without an error");
			Check(Logs.size() > Before, "one warning was logged");
		}

		printf("failure\n");
		{
			std::shared_ptr<FScaler> S3 = FScaler::Create(R.Dev, OutW, OutH, Err);
			FTextures T = MakeTextures(R, 600, 340, OutW, OutH, 600, 340);
			float C2P[16]; RenderInputs(R, T, 0, 528, 297, 0, 0, 0, 0, C2P); WaitAll(R);
			S3->Fail("test failure");
			Check(S3->Failed() && S3->FailureReason() == "test failure", "a failed scaler reports its reason");
			S3->Encode(R.Q, MakeFrame(T, 528, 297, 0, 0, 0, 0, C2P, true, false, false));
			WaitAll(R);
			Check(S3->Timings().Frames == 0, "a failed scaler encodes nothing");
			// What the host does instead for such a frame: a black output, never uninitialised memory.
			{
				std::shared_ptr<FScaler> S4 = FScaler::Create(R.Dev, OutW, OutH, Err);
				S4->Encode(R.Q, MakeFrame(T, 528, 297, 0, 0, 0, 0, C2P, true, false, false));
				WaitAll(R);
				std::vector<float> Before = Luma(R, T.Output, OutW, OutH);
				double SumBefore = 0; for (float V : Before) SumBefore += V;
				ClearTexture(R.Q, T.Output);
				WaitAll(R);
				std::vector<float> After = Luma(R, T.Output, OutW, OutH);
				double SumAfter = 0; for (float V : After) SumAfter += V;
				Check(SumBefore > 1000.0 && SumAfter == 0.0, "ClearTexture turns an upscaled image into black");
			}
		}

		FScaler::ReleaseSharedResources();
		printf("%s (%d failures)\n", GFailures == 0 ? "PASS" : "FAIL", GFailures);
		return GFailures == 0 ? 0 : 2;
	}
}
