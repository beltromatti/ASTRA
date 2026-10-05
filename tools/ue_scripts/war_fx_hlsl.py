"""The shaders of the war's visual effects (tools/ue_scripts/make_war_fx.py puts each into a Custom node), kept as plain text here so that
tools/art/war_fx_shader_preview.py can check the maths of the shield, the darts and the glows on a picture before the editor ever sees them.

Conventions (docs/VFX.md):
  - Everything is a volume with a soft rim: spheres (darts, flashes, fireballs, smoke, shield shells) and tubes (beams, trails, plumes). A tube's
    cross-section is worked out from its own radial direction (the engine's cylinder may be shaded flat), a sphere's from its normal.
  - A sphere is drawn as a screen-facing disc: its normal in view space (VN) says where on the disc a pixel is, so a flipbook frame or a flare's
    arms line up with the screen however the camera turns, and zoomed or not the effect is round, never a plate seen edge-on.
  - Nothing is lit at the silhouette (the rims fade to zero), so the polygons of the engine's low-poly spheres never show, whatever the zoom.
  - Per-instance custom data (AstraWarFX.h, AstraFx::Fill): 0-2 colour, 3 intensity, 4 age, 5 P1, 6 P2, 7 seed, 8 width (m), 9 length (m).
  - A thin thing (slug, beam, wake, spark) is lit by its barrel's profile normalised by the view angle, never by a Fresnel term (see "how a thin thing is lit").
Inputs of each snippet are the names its Custom node gets; every snippet returns the type its node declares.
"""

# -------------------------------------------------------------------------------------------------------------- minimum size (vertex)
# A few pixels at least, whatever the distance and the zoom: the vertices of a thin tube or a small sphere are pushed out so that its radius
# is never under half of MinPx pixels (a pixel's width at that distance from the view's own field of view and size). Input RadW: the vertex's
# radial vector in world cm (a tube: its radial part; a sphere: the whole), WPrel: the vertex's position relative to the camera.
MINSIZE = """
float d = max(length(WPrel), 1.0);
float pxCm = d * 2.0 * TanHalf.x / max(ViewSz.x, 1.0);
float curR = length(RadW);
float minR = 0.5 * MinPx * pxCm;
float extra = max(0.0, minR - curR);
return (curR > 0.001) ? (RadW / curR) * extra : float3(0.0, 0.0, 0.0);
"""

# The plume's own vertex shader: it narrows toward its tip (the flame is a cone, not a stick) and keeps its minimum width in pixels.
MINSIZE_PLUME = """
float d = max(length(WPrel), 1.0);
float pxCm = d * 2.0 * TanHalf.x / max(ViewSz.x, 1.0);
float curR = length(RadW);
float t = saturate(LZ / 100.0 + 0.5);
float sc = lerp(1.0, 0.16, pow(t, 0.8));
float wantR = max(curR * sc, 0.5 * MinPx * pxCm * lerp(1.0, 0.6, t));
return (curR > 0.001) ? (RadW / curR) * (wantR - curR) : float3(0.0, 0.0, 0.0);
"""

# ------------------------------------------------------------------------------------------------------------------------------- how a thin thing is lit
# A slug, a beam, a wake, a spark is a cylinder along its local z (head at +z). Its Fresnel term is at most sin(theta), theta the angle between the view and the axis, so lit by
# it (as the first version was) a slug seen from behind or along the line of fire - the view of every camera that sees "our" fire: the main viewscreen, the bridge, the Aquila's
# broadside shot - was a dark disc and a beam a faint halo (VFX-2, 5 Oct: tools/art/war_fx_view_angles.py draws both from 90 degrees down to head-on). Now:
#  - the cross-section is the barrel's radial profile normalised by sin(theta) (1 on the centre line of the strip, 0 at its silhouette, whatever the angle: the lower bound 0.12
#    keeps the last degrees from blowing up);
#  - the two end discs are shaded as discs (round, bright in the middle): head-on a slug is a round glow of its own width;
#  - what runs along the axis (the tail's fade, the ends, a wake's decay) is used as far as the axis lies across the view (`side`, from sin(theta)) and is averaged away when it
#    does not: nothing hides behind its own foreshortening.
# Inputs: NW (the radial direction of the pixel, world), CamV (to the camera), LP (local position, cm), AxisW (the axis, world), then the instance's data.

DART = """
float3 ax = normalize(AxisW + float3(0.0, 0.0, 0.00001));
float3 v = normalize(CamV);
float sinT = length(cross(ax, v));
float side = smoothstep(0.05, 0.35, sinT);
float t = saturate(LP.z / 100.0 + 0.5);
float rr = length(LP.xy) / 50.0;
float3 n = normalize(NW + float3(0.00001, 0.0, 0.0));
float ndv0 = (abs(LP.z) > 49.5 && rr < 0.97) ? sqrt(saturate(1.0 - rr * rr * rr)) : saturate(abs(dot(n, v)) / max(sinT, 0.12));
float tp = lerp(1.0, sqrt(saturate(1.0 - (2.0 * t - 1.0) * (2.0 * t - 1.0))), side);
float lat = sqrt(saturate(1.0 - ndv0 * ndv0)) / max(tp, 0.06);
float ndv = sqrt(saturate(1.0 - lat * lat));
float tt = lerp(0.5, t, side);
float head = smoothstep(0.0, 0.92, tt);
float tail = lerp(1.0, pow(head, 1.3), side);
float core = pow(ndv, 6.0);
float halo = pow(ndv, 1.4);
float hot = core * (0.55 + 0.45 * head);
float3 white = float3(1.0, 0.96, 0.88);
float3 c = lerp(Col, white, saturate(hot * 1.5));
float fade = 1.0;
float tw = 1.0;
if (Style < 1.5)
{
    fade = pow(saturate(1.0 - Age), 1.5);
}
else if (Style < 2.5)
{
    float a = lerp(Age, P2, tt);
    fade = pow(saturate(1.0 - a), 1.3);
    tail = 1.0;
    hot = hot * 0.5;
    c = lerp(c, Col * 0.55, a);
}
else
{
    tw = 0.8 + 0.2 * sin(Seed * 91.0 + Tm * 55.0);
    tail = lerp(tail, 1.0, 0.55);
}
float edge = smoothstep(0.0, 0.2, ndv);
return c * Inten * (halo * 0.5 + hot * 1.7) * tail * fade * tw * edge;
"""

# ------------------------------------------------------------------------------------------------------------------------------- tube
# A beam, a trail, a stream of tracers, a slug's wake: a cylinder along its local z, head at +z (lit as above). Inputs: NW, CamV, LP, AxisW, LenM, Col, Inten, Age,
# Style (1 beam, 2 trail, 4 tracer, 5 wake), P2 (a trail: its age at the head; a wake: its decay, e^(-P2) at the tail against 1 at the head), Seed, Tm.
TUBE = """
float3 ax = normalize(AxisW + float3(0.0, 0.0, 0.00001));
float3 v = normalize(CamV);
float sinT = length(cross(ax, v));
float side = smoothstep(0.05, 0.35, sinT);
float3 n = normalize(NW + float3(0.00001, 0.0, 0.0));
float rr = length(LP.xy) / 50.0;
float ndv = (abs(LP.z) > 49.5 && rr < 0.97) ? sqrt(saturate(1.0 - rr * rr * rr)) : saturate(abs(dot(n, v)) / max(sinT, 0.12));
float t = saturate(LP.z / 100.0 + 0.5);
float tt = lerp(0.5, t, side);
float L = max(LenM, 1.0);
float e = saturate(18.0 / L);
float ends = lerp(1.0, smoothstep(0.0, e, tt) * smoothstep(1.0, 1.0 - e, tt), side);
float core = pow(ndv, 4.5);
float halo = pow(ndv, 1.25);
float3 white = float3(1.0, 0.97, 0.9);
float3 c = lerp(Col, white, saturate(core * 1.3));
float fade = 1.0;
float pulse = 1.0;
if (Style > 0.5 && Style < 1.5)
{
    pulse = 0.82 + 0.18 * sin(t * L / 7.0 - Tm * 42.0 + Seed * 6.2831853);
}
else if (Style > 1.5 && Style < 2.5)
{
    float a = lerp(Age, P2, tt);
    fade = pow(saturate(1.0 - a), 1.3);
    ends = 1.0;
    c = lerp(c, Col * 0.55, a);
}
else if (Style > 3.5 && Style < 4.5)
{
    ends = lerp(1.0, smoothstep(0.0, 0.85, tt) * smoothstep(1.0, 0.97, tt), side);
}
else if (Style > 4.5)
{
    fade = lerp(exp(-0.5 * P2), exp(-P2 * (1.0 - t)), side);
    ends = lerp(1.0, smoothstep(0.0, 0.04, tt), side);
    c = lerp(Col, c, 0.35 + 0.65 * t);
}
float edge = smoothstep(0.0, 0.18, ndv);
return c * Inten * (halo * 0.45 + core * 1.5) * ends * pulse * fade * edge;
"""

# ------------------------------------------------------------------------------------------------------------------------------- glow
# A flash, a flare, a hot spot, a drive's glare, the limb of a blast wave: a sphere drawn as a screen-facing disc. Inputs: Fr, VN (the normal in
# view space), Col, Inten, Age, Kind (0 soft ball, 1 flash with streaks, 2 flare, 3 blast-wave shell), Seed, Tm.
GLOW = """
float ndv = saturate(1.0 - Fr);
float2 xy = VN.xy;
float r = length(xy);
float rim = smoothstep(1.0, 0.80, r);
float fade = saturate(1.0 - Age);
float3 white = float3(1.0, 0.97, 0.9);
float3 rgb = float3(0.0, 0.0, 0.0);
if (Kind < 0.5)
{
    float q = r / 0.20;
    float psf = 1.0 / pow(1.0 + q * q, 1.3);
    rgb = lerp(Col, white, psf * psf) * psf * pow(fade, 0.8) * rim;
}
else if (Kind < 1.5)
{
    float q = r / 0.16;
    float core = exp(-q * q);
    float p2 = r / 0.28;
    float psf = 1.0 / pow(1.0 + p2 * p2, 1.4);
    float sh = exp(-abs(xy.y) * 18.0) * exp(-abs(xy.x) * 4.5);
    float sv = exp(-abs(xy.x) * 30.0) * exp(-abs(xy.y) * 4.0) * 0.35;
    rgb = lerp(Col, white, saturate(core * 1.4)) * (core * 1.6 + psf * 0.5 + (sh + sv) * 0.6) * pow(fade, 1.6) * rim;
}
else if (Kind < 2.5)
{
    float q = r / 0.14;
    float psf = 1.0 / pow(1.0 + q * q, 1.5);
    float tw = 0.78 + 0.22 * sin(Seed * 57.0 + Tm * 23.0) * sin(Seed * 13.0 + Tm * 11.0);
    float arms = exp(-abs(xy.y) * 24.0) * exp(-abs(xy.x) * 3.2) * 0.5 + exp(-abs(xy.x) * 24.0) * exp(-abs(xy.y) * 3.2) * 0.5;
    rgb = lerp(Col, white, psf) * (psf + arms * 0.5) * tw * pow(fade, 0.45) * rim;
}
else
{
    float qs = (ndv - 0.16) / 0.11;
    float limb = exp(-qs * qs);
    float body = pow(ndv, 3.0) * 0.05;
    rgb = lerp(Col, white, 0.3) * (limb + body) * pow(fade, 1.3) * smoothstep(0.0, 0.08, ndv);
}
return rgb * Inten;
"""

# ------------------------------------------------------------------------------------------------------------------------------- fire
# A fireball: a flipbook (T_WAR_Fire, 8 x 8 frames) drawn on a sphere as a screen-facing disc, two frames blended. The UV node returns the
# two frames' UVs (xy, zw); FireW the blend; FireShade the colour: temperature (R) through a ramp, density (G).
FIRE_UV = """
float2 p = VN.xy;
float ang = Seed * 6.2831853;
float s = sin(ang);
float c = cos(ang);
p = float2(c * p.x - s * p.y, s * p.x + c * p.y);
float2 uvc = clamp(p * 0.5 + 0.5, 0.002, 0.998);
float f = saturate(Age) * 63.0;
float f0 = floor(f);
float f1 = min(f0 + 1.0, 63.0);
float2 cell0 = float2(fmod(f0, 8.0), floor(f0 / 8.0));
float2 cell1 = float2(fmod(f1, 8.0), floor(f1 / 8.0));
return float4((cell0 + uvc) / 8.0, (cell1 + uvc) / 8.0);
"""

FIRE_W = """
return frac(saturate(Age) * 63.0);
"""

FIRE_SHADE = """
float3 tex = lerp(TA, TB, W);
float T = tex.r;
float dens = tex.g;
float r = length(VN.xy);
float rim = smoothstep(1.0, 0.86, r);
float3 dark = Col * float3(0.55, 0.12, 0.02);
float3 hot = float3(1.0, 0.93, 0.78);
float a = smoothstep(0.05, 0.42, T);
float b = smoothstep(0.50, 0.92, T);
float3 c = lerp(lerp(dark, Col, a), hot, b);
float lum = pow(T, 1.25) * 1.7 + 0.06;
return c * lum * dens * rim * Inten;
"""

# ------------------------------------------------------------------------------------------------------------------------------- smoke
# A puff of smoke (T_WAR_Smoke): density (R), light (G), embers (B); translucent, drawn as a screen-facing disc. Returns float4: colour, opacity.
SMOKE_SHADE = """
float3 tex = lerp(TA, TB, W);
float r = length(VN.xy);
float rim = smoothstep(1.0, 0.80, r);
float fadeio = smoothstep(0.0, 0.10, Age) * (1.0 - smoothstep(0.55, 1.0, Age));
float dens = saturate(tex.r * 1.4) * rim * fadeio * lerp(0.55, 1.0, Dark);
float3 lit = Col * Inten * (0.25 + 0.75 * tex.g);
float3 ember = float3(1.0, 0.42, 0.12) * tex.b * Glow * 60.0 * (1.0 - Age);
return float4(lit + ember, dens);
"""

# ------------------------------------------------------------------------------------------------------------------------------- plume
# A drive's exhaust: a tube from the bell's lip (local z = -50) to its tip (+50), narrowing and fading, with shock diamonds. Inputs: NW, CamV, LP,
# LenM, Col (unused but for the ASTRA/Mandate palettes: Faction 0 or 1), Inten, Clock (Age slot), Faction (P1), Sputter (P2), Seed, Tm.
PLUME = """
float3 n = normalize(NW + float3(0.00001, 0.0, 0.0));
float ndv = abs(dot(n, normalize(CamV)));
float rad = length(LP.xy) / 50.0;
ndv = lerp(1.0, ndv, smoothstep(0.55, 1.0, rad));
float t = saturate(LP.z / 100.0 + 0.5);
float taper = pow(ndv, lerp(0.9, 9.0, t));
float body = pow(saturate(1.0 - t), 1.5);
float dia = 0.80 + 0.20 * cos(t * LenM * 0.55 - Tm * 14.0 + Seed * 6.2831853);
float flick = 1.0 - Sputter * step(0.5, frac(sin(floor(Tm * 17.0 + Seed * 40.0) * 91.7) * 437.58));
float3 core = (Faction < 0.5) ? float3(0.82, 0.92, 1.0) : float3(1.0, 0.7, 0.34);
float3 edge = (Faction < 0.5) ? float3(0.24, 0.52, 1.0) : float3(0.6, 0.2, 0.95);
float3 c = lerp(edge, core, pow(ndv, 3.0) * (1.0 - t * 0.7));
float e = smoothstep(0.0, 0.1, ndv);
return c * Inten * taper * body * dia * flick * e;
"""

# ------------------------------------------------------------------------------------------------------------------------------- shield
# A ship's shield shell (a unit sphere scaled to the ellipsoid Axes, metres). A hexagonal lattice in the shell's own metres (three planes blended,
# so the cells have the same size on every side); a blow lights the cells round where it landed with a ring that spreads and a hot centre that
# dies; a sector that falls lights all of its cells and flickers. LP: the local position, cm (the unit ball is 50 cm). Hit0..5: xyz the blow's
# direction on the shell (unit, ship frame), w its strength now. Info0..5: x radius (m), y age 0..1, z stress 0..1, w seed. Collapse: xyz the
# fallen sector's direction, w how strongly. Everything is finite: no negative bases for pow(), no division by a vector's zero.
SHIELD = """
float3 u = normalize(LP + float3(0.0, 0.0, 0.0001));
float3 ax = max(Axes.xyz, float3(1.0, 1.0, 1.0));
float3 P = u * ax;
float3 nrm = abs(u / ax);
nrm = nrm / max(nrm.x + nrm.y + nrm.z, 0.0001);
float3 w = nrm * nrm * nrm * nrm;
w = w * w;
w = w / max(w.x + w.y + w.z, 0.0001);
float cell = max(HexSize, 1.0);
float mpp = length(ddx(P)) + length(ddy(P));
float fw = mpp / cell;
float aa = saturate(1.0 - fw * 1.6);
float edgeW = max(0.07, fw * 1.1);
float4 Hs[6] = {Hit0, Hit1, Hit2, Hit3, Hit4, Hit5};
float4 Inf[6] = {Info0, Info1, Info2, Info3, Info4, Info5};
float3 cdir = normalize(Collapse.xyz + float3(0.0001, 0.0, 0.0));
float lit = 0.0;
float glow = 0.0;
for (int k = 0; k < 3; k++)
{
    float2 q = (k == 0) ? P.yz : ((k == 1) ? P.xz : P.xy);
    float wk = (k == 0) ? w.x : ((k == 1) ? w.y : w.z);
    float2 p = q / cell;
    float2 s = float2(1.0, 1.7320508);
    float4 hC = floor(float4(p, p - float2(0.5, 1.0)) / s.xyxy) + 0.5;
    float4 hh = float4(p - hC.xy * s, p - (hC.zw + 0.5) * s);
    float4 hx = (dot(hh.xy, hh.xy) < dot(hh.zw, hh.zw)) ? float4(hh.xy, hC.xy) : float4(hh.zw, hC.zw + 0.5);
    float2 a2 = abs(hx.xy);
    float eg = 0.5 - max(dot(a2, s * 0.5), a2.x);
    float2 cen = hx.zw * s * cell;
    float3 Pc = (k == 0) ? float3(P.x, cen.x, cen.y) : ((k == 1) ? float3(cen.x, P.y, cen.y) : float3(cen.x, cen.y, P.z));
    float hsh = frac(sin(dot(hx.zw + float(k) * 17.0, float2(127.1, 311.7))) * 43758.5453);
    float flick = 0.55 + 0.45 * frac(sin((hsh + floor(Tm * 13.0 + hsh * 9.0)) * 78.233) * 43758.5453);
    float cl = 0.0;
    for (int i = 0; i < 6; i++)
    {
        float4 hit = Hs[i];
        float4 inf = Inf[i];
        float3 Ph = normalize(hit.xyz + float3(0.0, 0.0, 0.0001)) * ax;
        float dd = length(Pc - Ph);
        float R = max(inf.x, 1.0);
        float age = inf.y;
        float front = R * (0.2 + 0.95 * age);
        float qb = (dd - front) / (0.30 * R + cell);
        float qc = dd / (0.42 * R + cell);
        float band = exp(-qb * qb);
        float core = exp(-qc * qc) * (1.0 - age);
        float jag = lerp(1.0, flick, saturate(0.25 + inf.z));
        cl += max(hit.w, 0.0) * (0.85 * band + 1.1 * core) * jag;
    }
    float on = smoothstep(0.5, 0.9, dot(normalize(Pc / ax), cdir));
    cl += Collapse.w * on * (0.5 + 0.9 * flick);
    float edge = 1.0 - smoothstep(0.0, edgeW, eg);
    float body = 0.30 * smoothstep(0.0, 0.25, eg);
    float pat = lerp(0.45, edge + body, aa);
    lit += wk * cl * pat;
    glow += wk * cl;
}
float bloom = 0.0;
for (int j = 0; j < 6; j++)
{
    float4 hit = Hs[j];
    float4 inf = Inf[j];
    float3 Ph = normalize(hit.xyz + float3(0.0, 0.0, 0.0001)) * ax;
    float dd = length(P - Ph);
    float R = max(inf.x, 1.0);
    float qc = dd / (0.55 * R + cell);
    bloom += max(hit.w, 0.0) * exp(-qc * qc) * (1.0 - inf.y) * 0.35;
}
float total = lit + bloom;
float3 colr = lerp(Col.rgb, float3(1.0, 0.97, 0.92), saturate(total * 0.22));
return colr * total * Gain * 48.0;
"""
