// Copyright ASTRA. The Metal compute kernels that prepare Unreal's frame for MetalFX, as MSL source embedded in the
// plugin (compiled once at start-up with newLibraryWithSource). No Unreal shader is involved: this file is also
// compiled and tested on its own by tools/metalfx_probe (probe_motion), so keep it free of any engine dependency.
//
//  astra_motion    Unreal's velocity buffer only holds the motion of the pixels that draw velocity (moving objects, bones...);
//                  every other pixel is static and its motion comes from the camera: reproject the depth with ClipToPrevClip,
//                  exactly as TSR does (TSRDepthVelocityAnalysis.ush, ComputeStaticVelocity). The result is MetalFX's motion
//                  vector: pixels of the input, previous position minus current position, x right, y down.
//  astra_exposure  MetalFX wants the exposure as a 1x1 R16Float texture: the tonemapper's global exposure, from the eye
//                  adaptation texture Unreal gives to third party upscalers (x = the exposure applied after the upscale).
//  astra_debug     Optional visualisations written into the output (r.AstraMetalFX.Debug): motion vectors, static/dynamic.
//
// The parameter block is mirrored by FAstraMotionParams in AstraMetalFXBridge.mm: change both together.

static const char* const kAstraMetalFXKernelSource = R"MSL(
#include <metal_stdlib>
using namespace metal;

struct AstraParams
{
	float4x4 ClipToPrevClip;   // Unreal's row-major matrix copied as it is: M * v here is v * M there (row vector convention)
	uint2 ViewRectMin;         // where the rendered rectangle starts inside the depth and velocity textures
	uint2 ViewSize;            // size of the rendered rectangle, in pixels (the input of the upscaler)
	uint2 VelocityExtent;      // size of the velocity texture (Unreal may bind a 1x1 dummy)
	float2 ScreenToPixel;      // ViewSize * 0.5: Unreal's screen space (-1..1) to pixels
	float ExposureFallback;    // exposure when the eye adaptation texture is not available
	uint Flags;                // bit 0: ignore the velocity texture (camera motion only)   bit 2: eye adaptation texture bound
	uint DebugMode;            // 0 off, 1 motion vectors, 2 dynamic (velocity buffer) vs static pixels
	uint Pad;
};

// Velocity buffer encoding: Common.ush, EncodeVelocityToTexture / DecodeVelocityFromTexture (gamma encoding on, as on SM5+).
constant float kVelocityInvDiv = 1.0 / (0.499 * 0.5);
constant float kVelocityZero = 32767.0 / 65535.0;

inline float2 DecodeVelocity(float2 Encoded)
{
	float2 V = Encoded * kVelocityInvDiv - kVelocityZero * kVelocityInvDiv;
	return (V * abs(V)) * 0.5;
}

// Unreal screen position (x right, y up, -1..1) of a pixel of the rendered rectangle.
inline float2 ScreenPosOf(uint2 Pixel, uint2 Size)
{
	float2 UV = (float2(Pixel) + 0.5) / float2(Size);
	return float2(UV.x * 2.0 - 1.0, 1.0 - UV.y * 2.0);
}

// Motion of one pixel in Unreal's screen space (current - previous), and whether it came from the velocity buffer.
inline float2 ScreenVelocity(depth2d<float, access::read> DepthTex, texture2d<float, access::read> VelTex,
	constant AstraParams& P, uint2 Pixel, thread bool& bDynamic)
{
	uint2 Src = Pixel + P.ViewRectMin;
	bDynamic = false;
	if ((P.Flags & 1u) == 0u && all(Src < P.VelocityExtent))
	{
		float4 Encoded = VelTex.read(Src);
		if (Encoded.x > 0.0)   // the clear value is 0: any other value is a pixel that drew its velocity
		{
			bDynamic = true;
			return DecodeVelocity(Encoded.xy);
		}
	}
	float DeviceZ = DepthTex.read(Src);
	float2 ScreenPos = ScreenPosOf(Pixel, P.ViewSize);
	float4 PrevClip = P.ClipToPrevClip * float4(ScreenPos, DeviceZ, 1.0);
	if (!(PrevClip.w > 1e-6)) return float2(0.0);
	return ScreenPos - PrevClip.xy / PrevClip.w;
}

kernel void astra_motion(
	depth2d<float, access::read> DepthTex [[texture(0)]],
	texture2d<float, access::read> VelTex [[texture(1)]],
	texture2d<half, access::write> MotionOut [[texture(2)]],
	constant AstraParams& P [[buffer(0)]],
	uint2 gid [[thread_position_in_grid]])
{
	if (any(gid >= P.ViewSize)) return;
	bool bDynamic;
	float2 V = ScreenVelocity(DepthTex, VelTex, P, gid, bDynamic);
	// Unreal: current - previous, y up.  MetalFX: previous - current, in pixels, y down.
	float2 Motion = float2(-V.x * P.ScreenToPixel.x, V.y * P.ScreenToPixel.y);
	MotionOut.write(half4(half2(clamp(Motion, -60000.0, 60000.0)), 0.0h, 0.0h), gid);
}

kernel void astra_exposure(
	texture2d<float, access::read> EyeTex [[texture(0)]],
	texture2d<half, access::write> ExposureOut [[texture(1)]],
	constant AstraParams& P [[buffer(0)]],
	uint2 gid [[thread_position_in_grid]])
{
	float E = (P.Flags & 4u) != 0u ? EyeTex.read(uint2(0, 0)).x : P.ExposureFallback;
	if (!(E > 0.0)) E = 1.0;
	ExposureOut.write(half4(half(clamp(E, 1e-4, 6e4)), 0.0h, 0.0h, 0.0h), uint2(0, 0));
}

// Writes a visualisation into the upscaler's output instead of the upscaled image.
kernel void astra_debug(
	depth2d<float, access::read> DepthTex [[texture(0)]],
	texture2d<float, access::read> VelTex [[texture(1)]],
	texture2d<half, access::read> ColorTex [[texture(2)]],
	texture2d<half, access::write> Out [[texture(3)]],
	constant AstraParams& P [[buffer(0)]],
	uint2 gid [[thread_position_in_grid]])
{
	if (gid.x >= Out.get_width() || gid.y >= Out.get_height()) return;
	float2 UV = (float2(gid) + 0.5) / float2(Out.get_width(), Out.get_height());
	uint2 Pixel = min(uint2(UV * float2(P.ViewSize)), P.ViewSize - 1u);
	float3 Base = float3(ColorTex.read(Pixel + P.ViewRectMin).rgb);
	bool bDynamic;
	float2 V = ScreenVelocity(DepthTex, VelTex, P, Pixel, bDynamic);
	float2 MotionPx = float2(-V.x * P.ScreenToPixel.x, V.y * P.ScreenToPixel.y);
	float3 Color;
	if (P.DebugMode == 2u)
	{
		Color = bDynamic ? float3(1.0, 0.25, 0.1) : Base * 0.5;
	}
	else
	{
		float Mag = length(MotionPx);
		float Angle = atan2(MotionPx.y, MotionPx.x);
		float3 Hue = clamp(abs(fmod(Angle / 6.2831853 * 6.0 + 6.0 + float3(0.0, 4.0, 2.0), 6.0) - 3.0) - 1.0, 0.0, 1.0);
		Color = mix(Base * 0.25, Hue, saturate(Mag * 0.5));
	}
	Out.write(half4(half3(Color), 1.0h), gid);
}
)MSL";
