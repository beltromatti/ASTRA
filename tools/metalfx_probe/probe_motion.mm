// Tests the plugin's own Metal kernels (AstraMetalFXKernels.inl, the very same source the plugin compiles) against an
// independent geometric ground truth, with Unreal's matrix and velocity conventions replicated on the CPU:
//  - a reverse-Z infinite-far perspective camera that moves and turns between two frames,
//  - depth of a world plane rendered into a Depth32Float_Stencil8 texture (what Unreal gives us),
//  - Unreal's ClipToPrevClip built with the formula of SetupCommonViewUniformBufferParameters,
//  - a rectangle of "dynamic" pixels whose velocity is stored with EncodeVelocityToTexture (RGBA16 UNORM),
//  - a content rectangle that does not start at the origin of the textures.
// The truth is the screen-space reprojection of the world point seen by each pixel, converted to MetalFX's convention
// (pixels, previous - current, y down). Usage: probe_motion
#include "probe_common.h"
#include "../../Plugins/AstraMetalFX/Source/AstraMetalFX/Private/AstraMetalFXKernels.inl"

#include "probe_math.h"

static const char* kSrcRender = R"MSL(
#include <metal_stdlib>
using namespace metal;
struct VOut { float4 Pos [[position]]; };
vertex VOut fs_vs(uint Vid [[vertex_id]])
{
	float2 P = float2(float((Vid << 1) & 2), float(Vid & 2));
	VOut O; O.Pos = float4(P * 2.0 - 1.0, 0.0, 1.0); return O;
}
struct FOut { float Depth [[depth(any)]]; };
fragment FOut fs_depth(VOut In [[stage_in]], texture2d<float, access::read> Src [[texture(0)]])
{
	FOut O; O.Depth = Src.read(uint2(In.Pos.xy)).x; return O;
}
)MSL";

struct FParams
{
	float ClipToPrevClip[16];
	uint32_t ViewRectMin[2];
	uint32_t ViewSize[2];
	uint32_t VelocityExtent[2];
	float ScreenToPixel[2];
	float ExposureFallback;
	uint32_t Flags;
	uint32_t DebugMode;
	uint32_t Pad;
};
static_assert(sizeof(FParams) == 112, "AstraParams layout");

int main()
{
	@autoreleasepool
	{
		id<MTLDevice> Dev = MTLCreateSystemDefaultDevice();
		id<MTLCommandQueue> Q = [Dev newCommandQueue];
		id<MTLLibrary> Lib = MakeLib(Dev, kAstraMetalFXKernelSource);
		id<MTLComputePipelineState> PsoMotion = MakePSO(Dev, Lib, "astra_motion");
		id<MTLComputePipelineState> PsoExpo = MakePSO(Dev, Lib, "astra_exposure");
		id<MTLLibrary> RLib = MakeLib(Dev, kSrcRender);

		const int TexW = 800, TexH = 500;          // the depth/velocity textures (UE allocates them bigger than the view)
		const int Ox = 16, Oy = 8;                 // content rectangle origin (not zero: a view that does not start at the corner)
		const int Cw = 640, Ch = 360;              // content size
		const double HalfFov = 45.0 * M_PI / 180.0, MinZ = 5.0;

		Camera Cur = { { 100.0, 40.0, 170.0 }, 0.30, -0.05 };
		Camera Prev = { { 96.5, 38.0, 169.0 }, 0.26, -0.08 };   // the previous frame: a bit behind, turned a bit
		Mat ProjCur = ReversedZPerspective(HalfFov, Cw, Ch, MinZ), ProjPrev = ReversedZPerspective(HalfFov, Cw, Ch, MinZ);
		Mat TVCur = TranslatedViewMatrix(Cur), TVPrev = TranslatedViewMatrix(Prev);
		double PVTCur[3] = { -Cur.Pos[0], -Cur.Pos[1], -Cur.Pos[2] }, PVTPrev[3] = { -Prev.Pos[0], -Prev.Pos[1], -Prev.Pos[2] };
		Mat C2P = ClipToPrevClip(ProjCur, TVCur, PVTCur, ProjPrev, TVPrev, PVTPrev);

		// World geometry seen by each pixel: the floor z = 0 and a back wall x = 900.
		std::vector<float> DepthData((size_t)TexW * TexH, 0.0f);
		std::vector<float> TruthX((size_t)Cw * Ch), TruthY((size_t)Cw * Ch);
		std::vector<uint16_t> VelData((size_t)TexW * TexH * 4, 0);
		const int DynX0 = 200, DynY0 = 120, DynX1 = 330, DynY1 = 240; // content coordinates of the dynamic rectangle
		const double DynVx = 0.0123, DynVy = -0.0071;                  // its screen velocity (current - previous, y up)
		for (int y = 0; y < Ch; ++y)
			for (int x = 0; x < Cw; ++x)
			{
				double Sx = ((x + 0.5) / Cw) * 2.0 - 1.0, Sy = 1.0 - ((y + 0.5) / Ch) * 2.0;
				// ray in view space: through the pixel (inverse of the projection), camera at origin.
				double Vx = Sx * tan(HalfFov), Vy = Sy * tan(HalfFov) * ((double)Ch / Cw);
				double DirV[3] = { Vx, Vy, 1.0 };
				// view -> translated world (columns of TV are view axes in world, so world = view * TV^T).
				double D4[4] = { DirV[0], DirV[1], DirV[2], 0 }, DW[4];
				Xform(Transposed(TVCur), D4, DW);
				// world ray from the camera: P = Pos + t * DW. The floor z = 0, else the wall x = 900.
				double T = 1e30;
				if (DW[2] < -1e-9) T = std::min(T, (0.0 - Cur.Pos[2]) / DW[2]);
				if (DW[0] > 1e-9) { double Tw = (900.0 - Cur.Pos[0]) / DW[0]; if (Tw < T) T = Tw; }
				if (T > 1e29 || T <= 0) T = 5000.0; // sky
				double W[4] = { Cur.Pos[0] + T * DW[0], Cur.Pos[1] + T * DW[1], Cur.Pos[2] + T * DW[2], 1.0 };
				// current clip (from the world point) and depth
				double TW[4] = { W[0] + PVTCur[0], W[1] + PVTCur[1], W[2] + PVTCur[2], 1.0 }, Clip[4];
				Xform(Mul(TVCur, ProjCur), TW, Clip);
				double DeviceZ = Clip[2] / Clip[3];
				size_t Ti = (size_t)(y + Oy) * TexW + (x + Ox);
				DepthData[Ti] = (float)DeviceZ;
				// previous clip from the same world point
				double TWp[4] = { W[0] + PVTPrev[0], W[1] + PVTPrev[1], W[2] + PVTPrev[2], 1.0 }, ClipP[4];
				Xform(Mul(TVPrev, ProjPrev), TWp, ClipP);
				double PSx = ClipP[0] / ClipP[3], PSy = ClipP[1] / ClipP[3];
				double VelX = Sx - PSx, VelY = Sy - PSy;         // current - previous, y up
				bool bDyn = (x >= DynX0 && x < DynX1 && y >= DynY0 && y < DynY1);
				if (bDyn)
				{
					EncodeVelocity(DynVx, DynVy, &VelData[Ti * 4]);
					VelX = DynVx; VelY = DynVy;
				}
				TruthX[(size_t)y * Cw + x] = (float)(-VelX * Cw * 0.5);
				TruthY[(size_t)y * Cw + x] = (float)(+VelY * Ch * 0.5);
			}

		// Depth: upload as R32Float then render it into a Depth32Float_Stencil8 target.
		id<MTLTexture> DepthSrc = MakeTex2D(Dev, MTLPixelFormatR32Float, TexW, TexH, MTLTextureUsageShaderRead, MTLStorageModeShared);
		[DepthSrc replaceRegion:MTLRegionMake2D(0, 0, TexW, TexH) mipmapLevel:0 withBytes:DepthData.data() bytesPerRow:TexW * 4];
		id<MTLTexture> Depth = MakeTex2D(Dev, MTLPixelFormatDepth32Float_Stencil8, TexW, TexH, MTLTextureUsageShaderRead | MTLTextureUsageRenderTarget);
		MTLRenderPipelineDescriptor* RPD = [MTLRenderPipelineDescriptor new];
		RPD.vertexFunction = [RLib newFunctionWithName:@"fs_vs"];
		RPD.fragmentFunction = [RLib newFunctionWithName:@"fs_depth"];
		RPD.depthAttachmentPixelFormat = MTLPixelFormatDepth32Float_Stencil8;
		RPD.stencilAttachmentPixelFormat = MTLPixelFormatDepth32Float_Stencil8;
		NSError* Err = nil;
		id<MTLRenderPipelineState> RPS = [Dev newRenderPipelineStateWithDescriptor:RPD error:&Err];
		if (!RPS) { printf("render PSO failed: %s\n", Err.localizedDescription.UTF8String); return 1; }
		MTLDepthStencilDescriptor* DSD = [MTLDepthStencilDescriptor new];
		DSD.depthCompareFunction = MTLCompareFunctionAlways; DSD.depthWriteEnabled = YES;
		id<MTLDepthStencilState> DSS = [Dev newDepthStencilStateWithDescriptor:DSD];
		RunCB(Q, ^(id<MTLCommandBuffer> CB) {
			MTLRenderPassDescriptor* RP = [MTLRenderPassDescriptor renderPassDescriptor];
			RP.depthAttachment.texture = Depth; RP.depthAttachment.loadAction = MTLLoadActionClear; RP.depthAttachment.storeAction = MTLStoreActionStore;
			RP.stencilAttachment.texture = Depth; RP.stencilAttachment.loadAction = MTLLoadActionClear; RP.stencilAttachment.storeAction = MTLStoreActionStore;
			id<MTLRenderCommandEncoder> E = [CB renderCommandEncoderWithDescriptor:RP];
			[E setRenderPipelineState:RPS]; [E setDepthStencilState:DSS]; [E setFragmentTexture:DepthSrc atIndex:0];
			[E drawPrimitives:MTLPrimitiveTypeTriangle vertexStart:0 vertexCount:3];
			[E endEncoding];
		});

		id<MTLTexture> Vel = MakeTex2D(Dev, MTLPixelFormatRGBA16Unorm, TexW, TexH, MTLTextureUsageShaderRead, MTLStorageModeShared);
		[Vel replaceRegion:MTLRegionMake2D(0, 0, TexW, TexH) mipmapLevel:0 withBytes:VelData.data() bytesPerRow:TexW * 8];
		id<MTLTexture> Motion = MakeTex2D(Dev, MTLPixelFormatRG16Float, Cw, Ch, MTLTextureUsageShaderRead | MTLTextureUsageShaderWrite);
		id<MTLTexture> Eye = MakeTex2D(Dev, MTLPixelFormatRGBA32Float, 1, 1, MTLTextureUsageShaderRead, MTLStorageModeShared);
		float EyeData[4] = { 2.75f, 0, 0, 1.0f };
		[Eye replaceRegion:MTLRegionMake2D(0, 0, 1, 1) mipmapLevel:0 withBytes:EyeData bytesPerRow:16];
		id<MTLTexture> Expo = MakeTex2D(Dev, MTLPixelFormatR16Float, 1, 1, MTLTextureUsageShaderRead | MTLTextureUsageShaderWrite);

		FParams P{};
		// Unreal's FMatrix is row-major: copy as it is (the kernel multiplies M * v for the row-vector v * M).
		for (int i = 0; i < 4; ++i) for (int j = 0; j < 4; ++j) P.ClipToPrevClip[i * 4 + j] = (float)C2P.M[i][j];
		P.ViewRectMin[0] = Ox; P.ViewRectMin[1] = Oy; P.ViewSize[0] = Cw; P.ViewSize[1] = Ch;
		P.VelocityExtent[0] = TexW; P.VelocityExtent[1] = TexH;
		P.ScreenToPixel[0] = Cw * 0.5f; P.ScreenToPixel[1] = Ch * 0.5f;
		P.ExposureFallback = 1.0f; P.Flags = 4;
		double Ms = RunCB(Q, ^(id<MTLCommandBuffer> CB) {
			id<MTLComputeCommandEncoder> E = [CB computeCommandEncoder];
			[E setComputePipelineState:PsoMotion]; [E setTexture:Depth atIndex:0]; [E setTexture:Vel atIndex:1]; [E setTexture:Motion atIndex:2]; [E setBytes:&P length:sizeof P atIndex:0];
			Dispatch2D(E, PsoMotion, Cw, Ch);
			[E setComputePipelineState:PsoExpo]; [E setTexture:Eye atIndex:0]; [E setTexture:Expo atIndex:1]; [E setBytes:&P length:sizeof P atIndex:0];
			[E dispatchThreadgroups:MTLSizeMake(1, 1, 1) threadsPerThreadgroup:MTLSizeMake(1, 1, 1)];
			[E endEncoding];
		});
		printf("kernels ran in %.3f ms for %dx%d\n", Ms, Cw, Ch);

		// Read back.
		id<MTLTexture> MotionS = MakeTex2D(Dev, MTLPixelFormatRG16Float, Cw, Ch, MTLTextureUsageShaderRead, MTLStorageModeShared);
		id<MTLTexture> ExpoS = MakeTex2D(Dev, MTLPixelFormatR16Float, 1, 1, MTLTextureUsageShaderRead, MTLStorageModeShared);
		RunCB(Q, ^(id<MTLCommandBuffer> CB) {
			id<MTLBlitCommandEncoder> B = [CB blitCommandEncoder];
			[B copyFromTexture:Motion toTexture:MotionS]; [B copyFromTexture:Expo toTexture:ExpoS];
			[B endEncoding];
		});
		std::vector<_Float16> Got((size_t)Cw * Ch * 2);
		[MotionS getBytes:Got.data() bytesPerRow:(size_t)Cw * 4 fromRegion:MTLRegionMake2D(0, 0, Cw, Ch) mipmapLevel:0];
		_Float16 ExpoGot; [ExpoS getBytes:&ExpoGot bytesPerRow:2 fromRegion:MTLRegionMake2D(0, 0, 1, 1) mipmapLevel:0];

		double MaxErrStatic = 0, MaxErrDyn = 0, SumStatic = 0; size_t NS = 0;
		double MaxMag = 0;
		for (int y = 0; y < Ch; ++y)
			for (int x = 0; x < Cw; ++x)
			{
				size_t I = (size_t)y * Cw + x;
				double Ex = (double)Got[I * 2] - TruthX[I], Ey = (double)Got[I * 2 + 1] - TruthY[I];
				double Err = sqrt(Ex * Ex + Ey * Ey);
				bool bDyn = (x >= DynX0 && x < DynX1 && y >= DynY0 && y < DynY1);
				MaxMag = std::max(MaxMag, sqrt((double)TruthX[I] * TruthX[I] + (double)TruthY[I] * TruthY[I]));
				if (bDyn) MaxErrDyn = std::max(MaxErrDyn, Err); else { MaxErrStatic = std::max(MaxErrStatic, Err); SumStatic += Err; ++NS; }
			}
		printf("motion vs geometric truth (pixels): static max error %.4f (mean %.5f), dynamic max error %.4f, largest truth magnitude %.2f px\n",
			MaxErrStatic, SumStatic / (double)NS, MaxErrDyn, MaxMag);
		printf("exposure texture: %.4f (expected 2.75)\n", (double)ExpoGot);
		bool bOk = MaxErrStatic < 0.05 && MaxErrDyn < 0.05 && fabs((double)ExpoGot - 2.75) < 0.01;
		printf("%s\n", bOk ? "PASS" : "FAIL");
		return bOk ? 0 : 2;
	}
}
