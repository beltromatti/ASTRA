"""ASTRA's score, written as code and rendered with the orchestral sampler (tools/music/sampler.py).

  MX_Aurelia    calm on the bridge — D minor, strings breathing, a horn melody, the flute answering (loop, ~90 s)
  MX_Tension    red alert, contacts closing — tremolo, clusters, timpani rolls, a heartbeat (loop, ~53 s)
  MX_Battle     the fight — spiccato ostinato, drums, brass, the trumpets' call (loop, ~56 s)
  MX_Aftermath  after the battle — a horn chorale over the strings, for the fallen and the living (loop, ~69 s)
  MX_Transit    the Janus lane — a swell that breaks on the crossing at 8.0 s (one shot, 14 s)

Run: uv run --with numpy --with scipy --with soundfile python tools/music/score.py [cue ...] -> art/_cache/music/*.wav
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sampler import ROOT, Score, m, render  # noqa: E402

OUT = os.path.join(ROOT, "art", "_cache", "music")
PERC = "Percussion"
TIMP = "Percussion/Timpani/Timpani1_Hit_v3_rr1_Sum.wav"
TIMP_SOFT = "Percussion/Timpani/Timpani1_Hit_v1_rr1_Sum.wav"
TIMP_ROLL = "Percussion/Timpani/Rolls/Timpani1_Roll_v3_rr1_Sum.wav"
SNARE_ROLL = "Percussion/Snare2-rollNS_v3_rr1_Sum.wav"
TIMP_D = -3.46          # Timpani1 sounds ~F2: shift to D2
TIMP_A = +3.54          # ... and up to A2


def chord_block(s: Score, t: float, dur: float, bass: str | None, mid: list[str], top: list[str], vel: float,
                attack: float = 1.2, release: float = 1.8, top_vel: float | None = None) -> None:
    """Strings: basses on the bass note, cellos/violas on the middle voices, violins on top."""
    if bass:
        s.n("cb_sus", m(bass), t, dur, vel, attack, release)
    for k, x in enumerate(mid):
        s.n("vc_sus" if m(x) < m("C4") else "vla_sus", m(x), t, dur, vel * (0.95 if k else 1.0), attack, release)
    for x in top:
        s.n("vln_sus", m(x), t, dur, top_vel if top_vel is not None else vel * 0.85, attack * 1.3, release)


# --------------------------------------------------------------------------------------------------- calm
def aurelia() -> Score:
    bpm, bars = 64, 24
    beat = 60 / bpm
    bar = 4 * beat
    s = Score(length=bars * bar, tail=7.0)
    chords = [  # (bass, middle voices, top voices), two bars each
        ("D2", ["D3", "A3", "F4"], ["E5", "A5"]),        # Dm9
        ("Bb1", ["Bb2", "F3", "D4"], ["E5", "A5"]),      # Bbmaj7#11
        ("A1", ["A2", "F3", "C4"], ["F5", "A5"]),        # F/A
        ("C2", ["C3", "G3", "D4"], ["E5", "G5"]),        # Csus2
        ("D2", ["D3", "A3", "F4"], ["D5", "A5"]),        # Dm
        ("G1", ["G2", "D3", "Bb3"], ["F5", "A5"]),       # Gm9
        ("Bb1", ["Bb2", "F3", "D4"], ["F5", "A5"]),      # Bbmaj7
        ("A1", ["A2", "E3", "C#4"], ["E5", "A5"]),       # A
        ("F2", ["D3", "A3", "F4"], ["D5", "A5"]),        # Dm/F
        ("G2", ["Bb2", "F3", "D4"], ["F5", "Bb5"]),      # Gm7
        ("Bb1", ["Bb2", "F3", "D4"], ["C5", "A5"]),      # Bbmaj9
        ("C2", ["C3", "G3", "E4"], ["E5", "G5"]),        # C (to Dm at the loop)
    ]
    for i, (b, mid, top) in enumerate(chords):
        t = i * 2 * bar
        # overlapping breaths: each chord starts under the previous one's release
        vel = 0.42 if i < 4 else (0.46 if i < 10 else 0.42)
        chord_block(s, max(0.0, t - 0.25), 2 * bar + 0.4, b, mid, top, vel, attack=1.6, release=2.2, top_vel=vel * 0.75)
    # the sus4 of the A chord resolving (bar 15 -> 16): violas D4 -> C#4 over the chord above
    s.n("vla_sus", m("D4"), 7 * 2 * bar, bar, 0.36, 0.8, 0.8)
    # harp: slow arpeggios in the first eight bars, shimmer in the last four
    arp = {0: ["D3", "A3", "E4", "F4", "A4", "E5"], 1: ["Bb2", "F3", "D4", "E4", "A4", "D5"],
           2: ["A2", "F3", "C4", "F4", "A4", "C5"], 3: ["C3", "G3", "D4", "E4", "G4", "D5"],
           10: ["Bb2", "F3", "C4", "D4", "A4", "C5"], 11: ["C3", "G3", "E4", "G4", "C5", "E5"]}
    for ci, notes in arp.items():
        for k in range(16):           # eighth notes over two bars
            x = notes[[0, 1, 2, 3, 4, 5, 4, 3][k % 8]]
            s.n("harp", m(x), ci * 2 * bar + k * beat / 2, beat, 0.4 + 0.08 * (k % 4 == 0))
    # the horn's melody over chords 5-10 (bars 9-20): (note, beats)
    melody = [("A4", 2), ("D5", 2), ("C5", 3), ("A4", 1),
              ("Bb4", 4), ("A4", 2), ("G4", 2),
              ("F4", 3), ("G4", 1), ("A4", 4),
              ("E5", 4), ("C#5", 4),
              ("D5", 3), ("E5", 1), ("F5", 2), ("E5", 2),
              ("D5", 4), ("Bb4", 4)]
    t = 8 * bar
    for x, b in melody:
        s.n("hn_sus", m(x), t, b * beat + 0.12, 0.3, 0.22, 0.9)
        t += b * beat
    # the flute answers softly (bars 21-24)
    t = 20 * bar
    for x, b in [("F5", 3), ("E5", 1), ("D5", 4), ("C5", 3), ("D5", 1), ("E5", 4)]:
        s.n("fl_sus", m(x), t, b * beat + 0.1, 0.36, 0.25, 1.0)
        t += b * beat
    s.hit(TIMP_SOFT, 0.0, -14, 0.0, TIMP_D)
    s.hit(TIMP_SOFT, 16 * bar, -16, 0.0, TIMP_D)
    return s


# ------------------------------------------------------------------------------------------------ tension
def tension() -> Score:
    bpm, bars = 72, 16
    beat = 60 / bpm
    bar = 4 * beat
    s = Score(length=bars * bar, tail=6.0)
    for ph in range(4):                   # four-bar swells
        t = ph * 4 * bar
        s.n("cb_trem", m("D2"), t, 4 * bar + 0.3, 0.45 + 0.1 * (ph % 2), 2.5, 1.2)
        s.n("vc_trem", m("D3"), t, 4 * bar + 0.3, 0.4, 2.0, 1.2)
        s.n("vc_trem", m("A3"), t, 4 * bar + 0.3, 0.36, 2.4, 1.2)
        s.n("vla_sus", m(["F4", "E4", "F4", "G4"][ph]), t, 4 * bar + 0.3, 0.38, 1.5, 1.4)
        if ph >= 1:   # the rub above: a minor second, high and thin
            hi = [("A5", "Bb5"), ("Bb5", "C6"), ("A5", "Bb5")][ph - 1]
            for x in hi:
                s.n("vln_sus", m(x), t + 0.3, 4 * bar, 0.3, 3.0, 1.6)
            s.n("hn_sus", m(["D3", "Eb3", "D3"][ph - 1]), t + bar, 3 * bar, 0.45, 2.5, 1.5)
            s.n("hn_sus", m(["A3", "Bb3", "A3"][ph - 1]), t + bar, 3 * bar, 0.42, 2.5, 1.5)
        # the timpani roll swelling into the next phrase, and its landing
        s.hit(TIMP_ROLL, t + 3 * bar, -9, 0.0, TIMP_D)
        s.hit(TIMP, t + 4 * bar - 0.02 if ph < 3 else 0.0, -8, 0.0, TIMP_D)
    # a heartbeat in the cellos from bar 9: da-dum on beats 1 and 3
    for b in range(8, 16):
        for q in (0, 2):
            t = b * bar + q * beat
            s.n("vc_spic", m("D3"), t, 0.2, 0.42)
            s.n("vc_spic", m("D3"), t + beat * 0.5, 0.2, 0.34)
    s.hit(f"{PERC}/BDrumNewhit_v3_rr1_Sum.wav", 8 * bar, -6)
    s.hit(f"{PERC}/BDrumNewhit_v3_rr2_Sum.wav", 12 * bar, -6)
    return s


# ------------------------------------------------------------------------------------------------- battle
def battle() -> Score:
    bpm, bars = 138, 32
    beat = 60 / bpm
    bar = 4 * beat
    e8 = beat / 2
    s = Score(length=bars * bar, tail=5.0)
    # two bars per chord: (root, quality) — phrases A B C D
    prog = [("D", "m"), ("Bb", ""), ("C", ""), ("D", "m"),
            ("D", "m"), ("Bb", ""), ("F", ""), ("A", ""),
            ("G", "m"), ("D", "m"), ("Bb", ""), ("A", ""),
            ("D", "m"), ("Bb", ""), ("C", ""), ("A", "")]
    third = {"m": 3, "": 4}
    for ci, (root, q) in enumerate(prog):
        t0 = ci * 2 * bar
        phrase = ci // 4
        r3 = m(root + "3")
        if r3 > m("F3"):
            r3 -= 12
        # the ostinato: cellos and violas in octaves, accents on 1, 2& and 4 (3+3+2)
        pattern = [0, 0, 7, 0, third[q], 0, 7, 0]
        for bb in range(2):
            for k, iv in enumerate(pattern):
                t = t0 + bb * bar + k * e8
                acc = k in (0, 3, 6)
                v = (0.72 if acc else 0.5) + 0.06 * phrase
                s.n("vc_spic", r3 + iv, t, e8, v)
                if phrase >= 1 or bb == 1:
                    s.n("vla_spic", r3 + 12 + iv, t, e8, v - 0.06)
                if acc:
                    s.n("cb_spic", r3 - 12, t, e8, v + 0.05)
        # the harmony held above: violins (tremolo in A, sustained later), horns from phrase B, low brass from C
        tri = [r3 + 12, r3 + 12 + third[q], r3 + 19]
        if phrase == 0:
            s.n("vln_trem", r3 + 24 + 7, t0, 2 * bar + 0.1, 0.34, 0.6, 0.5)
        else:
            for x in (r3 + 24, r3 + 24 + third[q]):
                s.n("vln_sus", x, t0, 2 * bar + 0.1, 0.42 + 0.06 * phrase, 0.15, 0.5)
        if phrase >= 1:
            for x in tri:
                s.n("hn_sus", x, t0, 2 * bar + 0.05, 0.5 + 0.08 * (phrase - 1), 0.1, 0.5)
        if phrase >= 2:
            s.n("tbn_sus", r3, t0, 2 * bar, 0.55, 0.05, 0.4)
            s.n("tbn_sus", r3 + 7, t0, 2 * bar, 0.5, 0.05, 0.4)
            s.n("tuba_sus", r3 - 12, t0, 2 * bar, 0.55, 0.05, 0.4)
        # drums: the timpani on every chord change; bass drum on the accents from phrase B
        s.hit(TIMP, t0, -4 + 1.5 * phrase, 0.0, TIMP_D if root in ("D", "Bb", "G") else TIMP_A)
        for bb in range(2):
            for k in ((0, 3, 6) if phrase >= 1 else ((0,) if bb == 0 else ())):
                s.hit(f"{PERC}/BDrumNewhit_v{5 + (k == 0)}_rr{1 + (bb + k) % 2}_Sum.wav", t0 + bb * bar + k * e8, -3 + phrase)
    # the snare rolls into each phrase, the crash at the top of C and D
    for ph in range(4):
        s.hit(SNARE_ROLL, (ph * 8 + 7) * bar, -8 + 2 * ph)
    for b in (16, 24):
        s.hit(f"{PERC}/cymbal-crash1_ff_rr{1 + (b == 24)}.wav", b * bar, -7, 0.1)
    # the trumpets' call: phrase C (bars 17-24) and D (25-32), horns an octave below in D
    call_c = [("D5", 2), ("Bb4", 1), ("D5", 1), ("G5", 4),
              ("F5", 2), ("E5", 1), ("D5", 1), ("A4", 4),
              ("Bb4", 2), ("C5", 1), ("D5", 1), ("F5", 3), ("E5", 1),
              ("E5", 4), ("C#5", 2), ("E5", 2)]
    call_d = [("A4", 1), ("D5", 1), ("F5", 2), ("A5", 4),
              ("G5", 2), ("F5", 1), ("D5", 1), ("F5", 4),
              ("E5", 2), ("D5", 1), ("C5", 1), ("E5", 2), ("G5", 2),
              ("A5", 4), ("A5", 2), ("E5", 2)]
    t = 16 * bar
    for x, b in call_c + call_d:
        s.n("tpt_sus", m(x), t, b * beat * 0.95, 0.62 if t < 24 * bar else 0.72, 0.03, 0.35)
        if t >= 24 * bar:
            s.n("hn_sus", m(x) - 12, t, b * beat * 0.95, 0.66, 0.03, 0.35)
        t += b * beat
    return s


# ---------------------------------------------------------------------------------------------- aftermath
def aftermath() -> Score:
    bpm, bars = 56, 16
    beat = 60 / bpm
    bar = 4 * beat
    s = Score(length=bars * bar, tail=7.0)
    prog = [("F2", ["C3", "A3", "F4"]), ("D2", ["A2", "F3", "D4"]), ("Bb1", ["F2", "D3", "Bb3"]), ("C2", ["G2", "E3", "C4"]),
            ("A1", ["C3", "F3", "C4"]), ("G1", ["D3", "F3", "Bb3"]), ("Bb1", ["F2", "D3", "Bb3"]), ("C2", ["G2", "E3", "C4"]),
            ("D2", ["A2", "F3", "D4"]), ("Bb1", ["F2", "D3", "F3"]), ("A1", ["C3", "F3", "C4"]), ("G1", ["D3", "G3", "Bb3"]),
            ("Bb1", ["F2", "D3", "F3"]), ("C2", ["G2", "E3", "C4"]), ("D2", ["A2", "F3", "D4"]), ("C2", ["G2", "E3", "C4"])]
    for i, (b, mid) in enumerate(prog):
        t = i * bar
        s.n("cb_sus", m(b), max(0.0, t - 0.2), bar + 0.4, 0.34, 1.0, 1.6)
        for x in mid:
            s.n("vc_sus" if m(x) < m("C3") + 5 else "vla_sus", m(x), max(0.0, t - 0.2), bar + 0.4, 0.3, 1.2, 1.6)
        s.n("vln_sus", m(mid[-1]) + 12, max(0.0, t - 0.2), bar + 0.4, 0.22, 1.8, 1.8)
    melody = [("A4", 4), ("F4", 2), ("A4", 2), ("Bb4", 3), ("A4", 1), ("G4", 4),
              ("A4", 2), ("C5", 2), ("Bb4", 3), ("A4", 1), ("G4", 2), ("F4", 2), ("E4", 2), ("G4", 2),
              ("A4", 4), ("D5", 3), ("C5", 1), ("C5", 2), ("A4", 2), ("Bb4", 2), ("G4", 2),
              ("F4", 3), ("G4", 1), ("A4", 2), ("G4", 2), ("F4", 4), ("E4", 2), ("G4", 2)]
    t = 0.0
    for x, b in melody:
        s.n("hn_sus", m(x), t, b * beat + 0.1, 0.46, 0.25, 1.1)
        s.n("tbn_sus", m(x) - 12, t, b * beat + 0.1, 0.28, 0.3, 1.1)
        t += b * beat
    s.hit(TIMP_SOFT, 0.0, -12, 0.0, TIMP_D + 3)   # F
    return s


# ------------------------------------------------------------------------------------------------ transit
def transit() -> Score:
    s = Score(length=14.0, tail=0.0, loop=False)
    swell = [("cb_trem", "D2", 0.0), ("vc_trem", "A2", 0.0), ("vc_trem", "D3", 2.5), ("vla_trem", "E4", 2.5),
             ("vln_trem", "A4", 5.0), ("vln_trem", "D5", 5.0), ("vln_trem", "E5", 6.5), ("vln_trem", "A5", 6.5)]
    for ins, x, t in swell:
        s.n(ins, m(x), t, 8.0 - t, 0.7, 8.0 - t, 0.25)
    s.hit(TIMP_ROLL, 5.2, -4, 0.0, TIMP_D)
    s.hit(SNARE_ROLL, 6.2, -6)
    # the crossing
    s.hit(f"{PERC}/BDrumNewhit_v7_rr1_Sum.wav", 8.0, 0)
    s.hit(TIMP, 8.0, 0, 0.0, TIMP_D)
    s.hit(f"{PERC}/cymbal-crash1_ff_rr1.wav", 8.0, -4, 0.15)
    for ins, x, v in (("hn_sus", "D4", 0.8), ("hn_sus", "F#4", 0.78), ("hn_sus", "A4", 0.78), ("tbn_sus", "D3", 0.75),
                      ("tbn_sus", "A3", 0.72), ("tuba_sus", "D2", 0.8), ("tpt_sus", "A4", 0.7), ("tpt_sus", "D5", 0.72)):
        s.n(ins, m(x), 8.0, 2.6, v, 0.0, 2.5)
    for x in ("D3", "A3", "F#4", "D5", "A5"):
        s.n("vc_sus" if m(x) < m("C4") else ("vla_sus" if m(x) < m("C5") else "vln_sus"), m(x), 8.3, 3.2, 0.4, 0.8, 2.4)
    return s


CUES = {"MX_Aurelia": aurelia, "MX_Tension": tension, "MX_Battle": battle, "MX_Aftermath": aftermath, "MX_Transit": transit}

if __name__ == "__main__":
    names = sys.argv[1:] or list(CUES)
    for name in names:
        render(CUES[name](), os.path.join(OUT, name + ".wav"), loudness_db=-19.0 if name != "MX_Transit" else -16.0)
