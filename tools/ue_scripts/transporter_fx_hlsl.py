"""The shaders of the transporter's effects (tools/ue_scripts/make_transporter_fx.py puts each into a Custom node), kept as plain text here so that
tools/art/transporter_fx_check.py can compile each one with the engine's own DXC before the editor ever sees it.

Conventions (docs/TELETRASPORTO.md §7, docs/VFX.md): everything is unlit and additive, drawn as soft volumes (a sphere is read as a disc by its Fresnel term, a cylinder
is soft at its silhouette), nothing is a hard-edged plate. Per-instance custom data (AstraTransportFx.h, AstraXportFx::Stride = 8): 0-2 colour, 3 intensity, 4 progress or
age, 5 direction or mode, 6 fade, 7 seed. Every effect is scaled by the `astra.xport.gain` console variable on the C++ side, so a room that wants more or less light needs
no new shader.
Inputs of each snippet are the names its Custom node gets; every snippet returns a float3 (the emissive colour).
"""

# ------------------------------------------------------------------------------------------------------------------------------ wall screen
# The picture on the room's wall display: the engine's plane is 100 x 100 cm, centred, with local x to the viewer's right and local y up (the game stands it so): the
# texture coordinates come from the local position, not from the plane's own mapping. Returns a float2.
SCREEN_UV = """
return float2(LP.x * 0.01 + 0.5, 0.5 - LP.y * 0.01);
"""

# ------------------------------------------------------------------------------------------------------------------------------ sparkle
# A point of light that twinkles and fades: a small engine sphere drawn as a soft disc. Fr: Fresnel (exponent 1: 0 at the centre of the disc, 1 at its rim),
# Col, Inten, Age (0 born .. 1 gone), Seed (0..1), Tm (time, s).
SPARKLE = """
float ndv = saturate(1.0 - Fr);
float core = pow(ndv, 4.0);
float halo = pow(ndv, 1.7);
float tw = 0.62 + 0.38 * sin(Tm * (9.0 + 8.0 * Seed) + Seed * 40.0);
float fade = smoothstep(0.0, 0.12, Age) * (1.0 - smoothstep(0.5, 1.0, Age));
float3 hot = lerp(Col, float3(1.0, 0.97, 0.9), saturate(core));
return hot * Inten * (0.22 * halo + 1.5 * core) * tw * fade;
"""

# ------------------------------------------------------------------------------------------------------------------------------ column
# The shimmering cylinder round a subject: soft at its silhouette, lattice bands that climb it, and a bright front that sweeps it from the feet to the head.
# The engine's cylinder is 100 cm tall and centred, so its local z (LZ) runs -50..50: t = 0 at the feet, 1 at the head. Prog: where the front is (0..1); Dir: +1 the
# bands climb (a dematerialization), -1 they fall (a recomposition); Fade: the whole column's.
COLUMN = """
float ndv = saturate(1.0 - Fr);
float edge = pow(ndv, 1.1);
float t = saturate(LZ / 100.0 + 0.5);
float bands = 0.5 + 0.5 * sin((t * 22.0 - Tm * 4.5 * Dir) * 6.2831853 + Seed * 40.0);
bands = bands * bands;
float front = exp(-pow((t - Prog) * 6.5, 2.0));
float body = smoothstep(0.0, 0.06, t) * (1.0 - smoothstep(0.94, 1.0, t));
float grain = frac(sin(dot(float2(t * 37.0 + Seed * 91.0, floor(Tm * 18.0)), float2(12.9898, 78.233))) * 43758.5453);
float3 c = lerp(Col, float3(1.0, 0.97, 0.9), saturate(front));
float lum = 0.10 + 0.35 * bands + 1.7 * front + 0.25 * grain * front;
return c * Inten * edge * lum * body * Fade;
"""

# ------------------------------------------------------------------------------------------------------------------------------ pad ring
# A pad's ring on the floor: the engine's plane is 100 x 100 cm, the instance scale makes its half-width the pad's radius, so r runs 0..1 at the edge of the pad. Mode: the
# look (0 idle, 1 someone stands on it, 2 locking, 3 locked, 4 energizing, 5 fault): segments chase round the ring while a lock is being built or the beam is on, a locked pad
# is steady, a faulty one flickers.
RING = """
float r = length(LP.xy) / 50.0;
float ring = smoothstep(0.80, 0.86, r) * (1.0 - smoothstep(0.94, 1.0, r));
float inner = (1.0 - smoothstep(0.0, 0.8, r)) * 0.10;
float a = atan2(LP.y, LP.x);
float spin = (Mode > 3.5 && Mode < 4.5) ? 1.0 : ((Mode > 1.5 && Mode < 2.5) ? 0.6 : 0.0);
float seg = 0.5 + 0.5 * sin(a * 6.0 - Tm * (3.0 + 6.0 * spin) * spin + Seed * 6.28);
float pulse = (Mode > 1.5 && Mode < 2.5) ? 0.7 + 0.3 * sin(Tm * 4.0) : 1.0;
float flick = (Mode > 4.5) ? (0.4 + 0.6 * step(0.5, frac(sin(Tm * 31.0) * 43758.5453))) : 1.0;
float lit = (Mode < 0.5) ? 0.0 : 1.0;
float body = ring * (0.55 + 0.45 * lerp(1.0, seg, spin));
return Col * Inten * (body + inner * lit) * pulse * flick;
"""

# ------------------------------------------------------------------------------------------------------------------------------ ghost
# The figure of light that stands in for a body while it is carried: the body's own skeletal mesh, drawn with this. z runs 0 at the feet (FeetZ, cm) to 1 at the head
# (Height, cm); Prog 0..1 is a front that rises through the figure. Dir +1: a dematerialization, what is below the front is gone; Dir -1: a recomposition, what is above the
# front is not there yet. WP: the pixel's world position, Fr: Fresnel (exponent 1: high at the silhouette), Gain: the effect's brightness.
GHOST = """
float z = (WP.z - FeetZ) / max(Height, 1.0);
float rim = pow(saturate(Fr), 1.6);
float fill = 0.30 + 0.70 * rim;
float dz = z - Prog;
float vis = (Dir > 0.0) ? smoothstep(-0.03, 0.03, dz) : 1.0 - smoothstep(-0.03, 0.03, dz);
float edge = exp(-pow(dz * 16.0, 2.0));
float n = frac(sin(dot(WP.xy * 0.06 + WP.z * 0.09 + floor(Tm * 14.0), float2(12.9898, 78.233))) * 43758.5453);
float sparkle = step(0.86, n) * vis;
float3 c = lerp(Col, float3(1.0, 0.97, 0.9), saturate(edge));
float lum = fill * vis * (0.55 + 0.45 * n) + 2.2 * edge + 1.4 * sparkle;
return c * Gain * lum;
"""
