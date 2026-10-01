// Tiny row-vector matrix library replicating Unreal's FMatrix conventions and the exact formulas of the renderer,
// shared by the probes that test the plugin's kernels against a geometric ground truth.
#pragma once
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <vector>

// ---------------------------------------------------------------- tiny row-vector matrix library (Unreal's FMatrix convention)
struct Mat { double M[4][4]; };
static Mat Identity() { Mat R{}; for (int i = 0; i < 4; ++i) R.M[i][i] = 1; return R; }
static Mat Mul(const Mat& A, const Mat& B) // row vector convention: v * A * B
{
	Mat R{};
	for (int i = 0; i < 4; ++i) for (int j = 0; j < 4; ++j) { double S = 0; for (int k = 0; k < 4; ++k) S += A.M[i][k] * B.M[k][j]; R.M[i][j] = S; }
	return R;
}
static Mat Transposed(const Mat& A) { Mat R{}; for (int i = 0; i < 4; ++i) for (int j = 0; j < 4; ++j) R.M[i][j] = A.M[j][i]; return R; }
static Mat Translation(double X, double Y, double Z) { Mat R = Identity(); R.M[3][0] = X; R.M[3][1] = Y; R.M[3][2] = Z; return R; }
static void Xform(const Mat& A, const double In[4], double Out[4]) { for (int j = 0; j < 4; ++j) { double S = 0; for (int i = 0; i < 4; ++i) S += In[i] * A.M[i][j]; Out[j] = S; } }

// Generic 4x4 inverse (Gauss-Jordan) - used for InvertProjectionMatrix.
static Mat Inverse(const Mat& A)
{
	double a[4][8];
	for (int i = 0; i < 4; ++i) for (int j = 0; j < 4; ++j) { a[i][j] = A.M[i][j]; a[i][4 + j] = (i == j); }
	for (int c = 0; c < 4; ++c)
	{
		int p = c; for (int r = c + 1; r < 4; ++r) if (fabs(a[r][c]) > fabs(a[p][c])) p = r;
		for (int k = 0; k < 8; ++k) std::swap(a[c][k], a[p][k]);
		double d = a[c][c]; for (int k = 0; k < 8; ++k) a[c][k] /= d;
		for (int r = 0; r < 4; ++r) if (r != c) { double f = a[r][c]; for (int k = 0; k < 8; ++k) a[r][k] -= f * a[c][k]; }
	}
	Mat R{}; for (int i = 0; i < 4; ++i) for (int j = 0; j < 4; ++j) R.M[i][j] = a[i][4 + j];
	return R;
}

// UE: FReversedZPerspectiveMatrix (infinite far plane, clip z = MinZ, w = view z).
static Mat ReversedZPerspective(double HalfFovRad, double W, double H, double MinZ)
{
	Mat R{};
	R.M[0][0] = 1.0 / tan(HalfFovRad);
	R.M[1][1] = (W / tan(HalfFovRad)) / H;
	R.M[2][2] = 0.0; R.M[2][3] = 1.0;
	R.M[3][2] = MinZ;
	return R;
}

// A camera: position in world, yaw/pitch. World axes: x forward, y right, z up (Unreal). View space: x right, y up, z forward.
struct Camera { double Pos[3]; double Yaw, Pitch; };
static Mat TranslatedViewMatrix(const Camera& C) // rotation only: translated world -> view
{
	double cy = cos(C.Yaw), sy = sin(C.Yaw), cp = cos(C.Pitch), sp = sin(C.Pitch);
	double Fwd[3] = { cp * cy, cp * sy, sp };          // forward (world)
	double Right[3] = { -sy, cy, 0 };                   // right (world)
	double Up[3] = { -sp * cy, -sp * sy, cp };          // up (world)
	Mat R = Identity();
	// Row vector convention: v_view = v_world * R, columns are the view axes expressed in world.
	for (int i = 0; i < 3; ++i) { R.M[i][0] = Right[i]; R.M[i][1] = Up[i]; R.M[i][2] = Fwd[i]; }
	return R;
}

// Unreal's ClipToPrevClip (SceneView.cpp, SetupCommonViewUniformBufferParameters), without jitter.
static Mat ClipToPrevClip(const Mat& CurProj, const Mat& CurTV, const double CurPVT[3], const Mat& PrevProj, const Mat& PrevTV, const double PrevPVT[3])
{
	Mat InvViewProj = Mul(Inverse(CurProj), Transposed(CurTV));
	Mat PrevViewProj = Mul(Mul(Translation(PrevPVT[0] - CurPVT[0], PrevPVT[1] - CurPVT[1], PrevPVT[2] - CurPVT[2]), PrevTV), PrevProj);
	return Mul(InvViewProj, PrevViewProj);
}

// Unreal's EncodeVelocityToTexture (gamma on, depth channels irrelevant here), quantised to 16 bit UNORM.
static void EncodeVelocity(double Vx, double Vy, uint16_t Out[4])
{
	auto Enc = [](double V) { double G = (V < 0 ? -1.0 : 1.0) * sqrt(fabs(V)) * (2.0 / sqrt(2.0)); return G * (0.499 * 0.5) + 32767.0 / 65535.0; };
	auto Q = [](double U) { return (uint16_t)std::min(65535.0, std::max(0.0, std::round(U * 65535.0))); };
	Out[0] = Q(Enc(Vx)); Out[1] = Q(Enc(Vy)); Out[2] = Q(0.3); Out[3] = Q(0.2);
}

