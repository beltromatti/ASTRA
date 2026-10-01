// Shared synthetic 3D scene for the end-to-end probes: a textured floor and wall seen by a camera that moves and turns,
// rendered with Unreal-style jitter into a colour texture and a reverse-Z depth, plus the supersampled ground truth.
#pragma once
#include "probe_common.h"
#include "probe_math.h"
#include <simd/simd.h>

static const char* kSrcScene = R"MSL(
#include <metal_stdlib>
using namespace metal;
struct E2EParams { float4 Pos; float4 Right; float4 Up; float4 Fwd; float2 Tan; float2 Jitter; uint2 Size; uint SS; float MinZ; };

float Line(float d, float sigma) { return exp(-0.5 * d * d / (sigma * sigma)); }
float Sig(float2 p)
{
	float2 c = p * (1.0 / 41.0);
	float checker = 0.5 + 0.5 * sin(c.x * 6.2831853) * sin(c.y * 6.2831853);
	float l1 = Line(fmod(fabs(p.x), 9.0) - 4.5, 0.55);
	float l2 = Line(fmod(fabs(p.y + 0.37 * p.x), 13.0) - 6.5, 0.55);
	float2 q = p - float2(500.0, 100.0);
	float ring = Line(fmod(length(q), 17.0) - 8.5, 0.6);
	return clamp(0.15 + 0.35 * checker + 0.55 * l1 + 0.55 * l2 + 0.45 * ring, 0.0, 1.5);
}

// Returns linear colour, writes device depth (reverse Z, infinite far) of the nearest hit.
float4 Shade(constant E2EParams& P, float2 S, thread float& DeviceZ)
{
	float3 Dir = P.Fwd.xyz + P.Right.xyz * (S.x * P.Tan.x) + P.Up.xyz * (S.y * P.Tan.y);
	float T = 1e30;
	bool bFloor = false;
	if (Dir.z < -1e-6) { T = (0.0 - P.Pos.z) / Dir.z; bFloor = true; }
	if (Dir.x > 1e-6) { float Tw = (900.0 - P.Pos.x) / Dir.x; if (Tw < T) { T = Tw; bFloor = false; } }
	if (T > 1e29) { DeviceZ = 0.0; return float4(0.05, 0.08, 0.15, 1.0); }
	float3 Hit = P.Pos.xyz + Dir * T;
	float Zv = dot(Hit - P.Pos.xyz, P.Fwd.xyz);
	DeviceZ = P.MinZ / Zv;
	float V = bFloor ? Sig(Hit.xy) : Sig(Hit.yz + float2(17.0, 3.0));
	return bFloor ? float4(V, V * 0.85, V * 0.7, 1.0) : float4(V * 0.7, V * 0.85, V, 1.0);
}

kernel void e2e_render(texture2d<half, access::write> Color [[texture(0)]], texture2d<float, access::write> Depth [[texture(1)]],
	constant E2EParams& P [[buffer(0)]], uint2 gid [[thread_position_in_grid]])
{
	if (any(gid >= P.Size)) return;
	float4 Acc = float4(0.0); float Z = 0.0;
	for (uint sy = 0; sy < P.SS; ++sy)
		for (uint sx = 0; sx < P.SS; ++sx)
		{
			// Unreal's jitter: the image is shifted by +Jitter pixels, i.e. the sample sits at (pixel centre - Jitter).
			float2 Px = float2(gid) + (float2(sx, sy) + 0.5) / float(P.SS) - P.Jitter;
			float2 S = float2(Px.x / float(P.Size.x) * 2.0 - 1.0, 1.0 - Px.y / float(P.Size.y) * 2.0);
			float DZ; Acc += Shade(P, S, DZ); if (sx == P.SS / 2 && sy == P.SS / 2) Z = DZ;
		}
	Acc /= float(P.SS * P.SS);
	Color.write(half4(half3(Acc.rgb), 1.0h), gid);
	Depth.write(float4(Z, 0, 0, 0), gid);
}

kernel void e2e_zero_velocity(texture2d<float, access::write> Out [[texture(0)]], uint2 gid [[thread_position_in_grid]])
{
	if (gid.x >= Out.get_width() || gid.y >= Out.get_height()) return;
	Out.write(float4(0.0), gid);
}

kernel void e2e_negate(texture2d<half, access::read> In [[texture(0)]], texture2d<half, access::write> Out [[texture(1)]], uint2 gid [[thread_position_in_grid]])
{
	if (gid.x >= Out.get_width() || gid.y >= Out.get_height()) return;
	half4 V = In.read(gid); Out.write(half4(-V.x, -V.y, 0, 0), gid);
}
kernel void e2e_zero_motion(texture2d<half, access::write> Out [[texture(0)]], uint2 gid [[thread_position_in_grid]])
{
	if (gid.x >= Out.get_width() || gid.y >= Out.get_height()) return;
	Out.write(half4(0), gid);
}

kernel void e2e_bilinear(texture2d<half, access::sample> In [[texture(0)]], texture2d<half, access::write> Out [[texture(1)]], constant float2& ContentUV [[buffer(0)]], uint2 gid [[thread_position_in_grid]])
{
	if (gid.x >= Out.get_width() || gid.y >= Out.get_height()) return;
	constexpr sampler S(filter::linear, address::clamp_to_edge);
	float2 UV = (float2(gid) + 0.5) / float2(Out.get_width(), Out.get_height());
	Out.write(In.sample(S, UV * ContentUV), gid);
}
)MSL";

struct E2EParams { float Pos[4], Right[4], Up[4], Fwd[4]; float Tan[2], Jitter[2]; uint32_t Size[2]; uint32_t SS; float MinZ; };

static float Halton(int Index, int Base)
{
	float F = 1.0f, R = 0.0f;
	while (Index > 0) { F /= (float)Base; R += F * (float)(Index % Base); Index /= Base; }
	return R;
}

static Camera CameraAt(int F)
{
	Camera C;
	C.Pos[0] = 100.0 + 1.1 * F; C.Pos[1] = 40.0 + 0.6 * F + 6.0 * sin(F * 0.07); C.Pos[2] = 170.0 + 0.05 * F;
	C.Yaw = 0.30 + 0.0030 * F; C.Pitch = -0.05 + 0.0015 * F + 0.01 * sin(F * 0.05);
	return C;
}

static E2EParams MakeScene(const Camera& C, int W, int H, double HalfFov, float MinZ, float Jx, float Jy, int SS)
{
	double cy = cos(C.Yaw), sy = sin(C.Yaw), cp = cos(C.Pitch), sp = sin(C.Pitch);
	E2EParams P{};
	double Fwd[3] = { cp * cy, cp * sy, sp }, Right[3] = { -sy, cy, 0 }, Up[3] = { -sp * cy, -sp * sy, cp };
	for (int i = 0; i < 3; ++i) { P.Pos[i] = (float)C.Pos[i]; P.Right[i] = (float)Right[i]; P.Up[i] = (float)Up[i]; P.Fwd[i] = (float)Fwd[i]; }
	P.Tan[0] = (float)tan(HalfFov); P.Tan[1] = (float)(tan(HalfFov) * (double)H / W);
	P.Jitter[0] = Jx; P.Jitter[1] = Jy; P.Size[0] = W; P.Size[1] = H; P.SS = SS; P.MinZ = MinZ;
	return P;
}

