// Is it safe to run the scaler in a SEPARATE command buffer committed in between Unreal's command buffers, without any
// explicit synchronisation? Unreal's Metal RHI allocates its textures from tracked placement heaps, so Metal's hazard
// tracking should order the three buffers. This emulates that: producer CB -> "scaler" CB -> consumer CB, per frame,
// many frames committed without waiting, every stage checking the data it reads. Tracked vs untracked heaps.
// Usage: probe_hazard [frames]
#include "probe_common.h"

static const char* kSrc = R"MSL(
#include <metal_stdlib>
using namespace metal;

// Slow producer: writes `Frame` to every texel after a long dependent ALU chain (so the next stage could overlap it).
kernel void produce(texture2d<float, access::write> Out [[texture(0)]], constant float& Frame [[buffer(0)]], constant float& Seed [[buffer(1)]], uint2 gid [[thread_position_in_grid]])
{
	if (gid.x >= Out.get_width() || gid.y >= Out.get_height()) return;
	float a = Seed + float(gid.x) * 1e-9;
	for (int i = 0; i < 6000; ++i) a = fma(a, 0.9999999, 1e-7);
	float v = Frame + (a > 1e30 ? 1.0 : 0.0);   // a never gets that large: branch only defeats constant folding
	Out.write(float4(v, v, v, 1.0), gid);
}

// "Scaler": reads In, writes Out; counts how many texels did not hold the expected frame.
kernel void mid(texture2d<float, access::read> In [[texture(0)]], texture2d<float, access::write> Out [[texture(1)]],
	constant float& Frame [[buffer(0)]], device atomic_uint* Bad [[buffer(1)]], uint2 gid [[thread_position_in_grid]])
{
	if (gid.x >= Out.get_width() || gid.y >= Out.get_height()) return;
	float v = In.read(gid).x;
	if (v != Frame) atomic_fetch_add_explicit(Bad, 1u, memory_order_relaxed);
	Out.write(float4(Frame, Frame, Frame, 1.0), gid);
}

kernel void consume(texture2d<float, access::read> In [[texture(0)]], constant float& Frame [[buffer(0)]], device atomic_uint* Bad [[buffer(1)]], uint2 gid [[thread_position_in_grid]])
{
	if (gid.x >= In.get_width() || gid.y >= In.get_height()) return;
	float v = In.read(gid).x;
	if (v != Frame) atomic_fetch_add_explicit(Bad, 1u, memory_order_relaxed);
}
)MSL";

static void Run(id<MTLDevice> Dev, id<MTLCommandQueue> Q, id<MTLLibrary> Lib, bool bTracked, bool bHeap, int Frames)
{
	const int W = 1600, H = 900;
	MTLTextureDescriptor* D = [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:MTLPixelFormatRGBA32Float width:W height:H mipmapped:NO];
	D.usage = MTLTextureUsageShaderRead | MTLTextureUsageShaderWrite;
	D.storageMode = MTLStorageModePrivate;
	D.hazardTrackingMode = bTracked ? MTLHazardTrackingModeTracked : MTLHazardTrackingModeUntracked;
	id<MTLTexture> TIn, TOut;
	if (bHeap)
	{
		MTLSizeAndAlign SA = [Dev heapTextureSizeAndAlignWithDescriptor:D];
		MTLHeapDescriptor* HD = [MTLHeapDescriptor new];
		HD.type = MTLHeapTypePlacement;
		HD.storageMode = MTLStorageModePrivate;
		HD.hazardTrackingMode = bTracked ? MTLHazardTrackingModeTracked : MTLHazardTrackingModeUntracked;
		size_t Stride = (SA.size + SA.align - 1) / SA.align * SA.align;
		HD.size = Stride * 2;
		id<MTLHeap> Heap = [Dev newHeapWithDescriptor:HD];
		TIn = [Heap newTextureWithDescriptor:D offset:0];
		TOut = [Heap newTextureWithDescriptor:D offset:Stride];
	}
	else
	{
		TIn = [Dev newTextureWithDescriptor:D];
		TOut = [Dev newTextureWithDescriptor:D];
	}
	printf("  (texture.hazardTrackingMode = %d [0 default, 1 untracked, 2 tracked], heap = %s)\n", (int)TIn.hazardTrackingMode, TIn.heap ? "yes" : "no");
	id<MTLBuffer> Bad = [Dev newBufferWithLength:16 options:MTLResourceStorageModeShared];
	memset(Bad.contents, 0, 16);
	id<MTLComputePipelineState> PsoP = MakePSO(Dev, Lib, "produce"), PsoM = MakePSO(Dev, Lib, "mid"), PsoC = MakePSO(Dev, Lib, "consume");

	double T0 = NowMs();
	id<MTLCommandBuffer> Last = nil;
	for (int F = 1; F <= Frames; ++F)
	{
		float Frame = (float)F, Seed = 0.5f;
		id<MTLCommandBuffer> CBa = [Q commandBuffer];
		{
			id<MTLComputeCommandEncoder> E = [CBa computeCommandEncoder];
			[E setComputePipelineState:PsoP]; [E setTexture:TIn atIndex:0]; [E setBytes:&Frame length:4 atIndex:0]; [E setBytes:&Seed length:4 atIndex:1];
			Dispatch2D(E, PsoP, W, H);
			[E endEncoding];
		}
		[CBa commit];
		id<MTLCommandBuffer> CBb = [Q commandBuffer];
		{
			id<MTLComputeCommandEncoder> E = [CBb computeCommandEncoder];
			[E setComputePipelineState:PsoM]; [E setTexture:TIn atIndex:0]; [E setTexture:TOut atIndex:1]; [E setBytes:&Frame length:4 atIndex:0]; [E setBuffer:Bad offset:0 atIndex:1];
			Dispatch2D(E, PsoM, W, H);
			[E endEncoding];
		}
		[CBb commit];
		id<MTLCommandBuffer> CBc = [Q commandBuffer];
		{
			id<MTLComputeCommandEncoder> E = [CBc computeCommandEncoder];
			[E setComputePipelineState:PsoC]; [E setTexture:TOut atIndex:0]; [E setBytes:&Frame length:4 atIndex:0]; [E setBuffer:Bad offset:0 atIndex:1];
			Dispatch2D(E, PsoC, W, H);
			[E endEncoding];
		}
		[CBc commit];
		Last = CBc;
	}
	[Last waitUntilCompleted];
	double Ms = (NowMs() - T0) / Frames;
	uint32_t N = *(uint32_t*)Bad.contents;
	printf("%-8s %-10s : %d frames, %.3f ms/frame, texels read with wrong data: %u  => %s\n",
		bTracked ? "tracked" : "untracked", bHeap ? "placement" : "standalone", Frames, Ms, N, N == 0 ? "no race seen" : "RACE");
}

int main(int argc, char** argv)
{
	int Frames = argc > 1 ? atoi(argv[1]) : 300;
	@autoreleasepool
	{
		id<MTLDevice> Dev = MTLCreateSystemDefaultDevice();
		id<MTLCommandQueue> Q = [Dev newCommandQueue];
		id<MTLLibrary> Lib = MakeLib(Dev, kSrc);
		Run(Dev, Q, Lib, true, true, Frames);
		Run(Dev, Q, Lib, true, false, Frames);
		Run(Dev, Q, Lib, false, true, Frames);
		Run(Dev, Q, Lib, false, false, Frames);
		Run(Dev, Q, Lib, true, true, Frames);
	}
	return 0;
}
