#!/usr/bin/env python3
"""The class table under the bench (BATTAGLIA-3): a variant of data/war/classes.json for a few scenarios, one summary each. The real file is never touched: the variant is written to
Saved/War/classes_<tag>.json and the bench is given it (tools/war.py batch --classes), so it is safe next to anything else that reads the real table.

  tools/war.py classes --small cd=0.85,regen=0.5 --scen ss,st,op --seeds 8 --tag c1
  tools/war.py classes --mandate-small cd=0.9 --missiles acheron=64 --salvo acheron=8,styx=4 --scen st,o13
  tools/war.py classes --exec "astra.war.tune salvo_n 2" --scen st,op          (no table change: a tuning constant, over the same scenarios)

What can change (key=value, comma separated, multipliers of what the table has, but for `salvo` and `missiles`, which are the number itself):
  --small           the three small classes together (vigilant, styx, lethe)
  --mandate-small   the Mandate's small ones (styx, lethe)
  --acheron         the Acheron's own fields
  --aquila          the Aquila's own fields
  fields: cd, dmg (the rails' cycle and damage), range (the rails' reach), track (the fire control's error), laser (the lasers' damage), mcd (the missiles' cycle), hull, shield, regen (the shield's regeneration)
  --missiles        the cells of a class: acheron=48,styx=24 ; --salvo the cells it empties together in a massed salvo: acheron=8,styx=4
  --o13 V,C,M       the battle times at which the vanguard, Constance and the 7th Fleet's main body arrive in o13 (default 230,350,440)

The scenarios (--scen, comma separated):
  ss   Styx against Styx, 600 s                          the pace of a fight between equals
  sm   sym_small, 900 s                                  three against three
  st   the Aquila against the strike group, 600 s        the helm holds 24 km; the Aquila alone: how much a strong ship loses
  op   the opening from the contact (Solm's group), 900 s
  o13  the opening as the March plays it: Solm's group at 170 s, the vanguard (an Acheron, five Styx, two Lethe and twelve craft) a minute later, Constance (a Praetorian and three Vigilants)
       at about 350 s and the 7th Fleet's main body (two Praetorians and six Vigilants) at about 440 s; the picket and the Aquila's air group are there from the start
  mb1, mb2, mb3  the Interdiction Fleet's main body (fifteen warships and the carriers' wings) against the Aurelia force (four Praetorians, ten Vigilants): the Aquila 8, 14 or 20 km behind
                 the line, her executors alone (data/war/scenarios/main_body.json); the Aquila's hull at the end is the measure
"""
from __future__ import annotations

import glob
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLASSES = ROOT / "data" / "war" / "classes.json"
WAR = ROOT / "Saved" / "War"

# the opening as the March plays it (mind/astra_mind/march_data.py: F-M1, F-M3, F-A3, F-A1): the vanguard comes out of the Gate about a minute after the strike group, Constance about three minutes
# in and the 7th Fleet's main body about four and a half (the lead's own games, 5 Oct); the picket (a Praetorian, a Vigilant and eight Falcon) is there from the first second
VANGUARD = ("{'type':'raid','hail':false,'bearing_deg':70,'range_km':48,'delay_s':55,'groups':["
            "{'name':'Interdiction Vanguard','formation':'column','goes_for':'aquila','offset_km':[0,0],'ships':[{'class':'acheron','name':'Nyx'},{'class':'styx','name':'Asphodel'}],"
            "'wings':[{'carrier':0,'kind':'fighter','n':8,'mission':'strike'},{'carrier':0,'kind':'bomber','n':4,'mission':'strike'}]},"
            "{'name':'Styx Line Dorn','formation':'line','goes_for':'escorts','offset_km':[1.5,-6],'ships':[{'class':'styx','name':'Tartarus'},{'class':'styx','name':'Hypnos'},"
            "{'class':'styx','name':'Thanatos'},{'class':'styx','name':'Erinys'}]},"
            "{'name':'Raider Wedge Morrow','formation':'wedge','goes_for':'escorts','offset_km':[2,7],'ships':[{'class':'lethe','name':'Moros'},{'class':'lethe','name':'Keres'}]}]}")
RELIEF = ("{'type':'reinforcements','granted':true,'bearing_deg':250,'range_km':25,'delay_s':60,'groups':[{'name':'Battle Group Constance','formation':'line',"
          "'ships':[{'class':'praetorian','name':'ASN Constance'},{'class':'vigilant','name':'ASN Steadfast'},{'class':'vigilant','name':'ASN Valour'},{'class':'vigilant','name':'ASN Kestrel'}],"
          "'wings':[{'carrier':0,'kind':'fighter','n':8,'mission':'cap'}]}]}")
MAIN_BODY_7TH = ("{'type':'reinforcements','granted':true,'bearing_deg':245,'range_km':32,'delay_s':60,'groups':[{'name':'7th Fleet Main Body','formation':'line',"
                 "'ships':[{'class':'praetorian','name':'ASN Valiant'},{'class':'praetorian','name':'ASN Bulwark'},{'class':'vigilant','name':'ASN Vigilance'},{'class':'vigilant','name':'ASN Fortitude'},"
                 "{'class':'vigilant','name':'ASN Prudence'},{'class':'vigilant','name':'ASN Temperance'},{'class':'vigilant','name':'ASN Clemency'},{'class':'vigilant','name':'ASN Verity'}],"
                 "'wings':[{'carrier':0,'kind':'fighter','n':14,'mission':'cap'},{'carrier':0,'kind':'bomber','n':5,'mission':'strike'},{'carrier':1,'kind':'fighter','n':14,'mission':'cap'}]}]}")

def opening_at(vanguard_s: float = 230.0, constance_s: float = 350.0, main_s: float = 440.0) -> str:
    """The timed commands of the opening as the March plays it: the vanguard, Constance and the 7th Fleet's main body arrive at those battle times (the contact is at 170 s)."""
    def beat(at: float, arrive: float, body: str) -> str:
        delay = max(5.0, arrive - at)                                  # (a beat arrives its delay after it is given: 5 s at least)
        return "%g=astra.cmd director_beat {'beat':%s}" % (at, body.replace("'delay_s':55", "'delay_s':%g" % delay).replace("'delay_s':60", "'delay_s':%g" % delay))
    return "|".join([beat(175.0, vanguard_s, VANGUARD), beat(max(175.0, constance_s - 60.0), constance_s, RELIEF), beat(max(175.0, main_s - 60.0), main_s, MAIN_BODY_7TH)])


# key -> (label, scenario ('' = the opening, from the contact), the Captain's script, seconds, timed commands, more arguments for the bench)
SCENARIOS = {
    "ss": ("Styx against Styx", "duel_styx_styx", "", 600, "", []),
    "sm": ("sym_small", "sym_small", "", 900, "", []),
    "st": ("the Aquila against the strike group", "duel_aq_strike", "standoff:24", 600, "", []),
    "op": ("the opening", "", "engage", 900, "", []),
    "o13": ("the opening as the March plays it (the vanguard, Constance, the main body)", "", "engage", 1100,
            opening_at(), []),
    "mb1": ("the main body against the Aurelia force, the Aquila 8 km behind the line", "main_body", "engage", 600, "", ["--aquila-opts", "at=-16,0,0;speed=0;heading=0"]),
    "mb2": ("... 14 km behind the line", "main_body", "engage", 600, "", ["--aquila-opts", "at=-22,0,0;speed=0;heading=0"]),
    "mb3": ("... 20 km behind the line (where the lead's Captain kept her)", "main_body", "engage", 600, "", ["--aquila-opts", "at=-28,0,0;speed=0;heading=0"]),
}


def _kv(s: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for part in (s or "").split(","):
        if part.strip():
            k, _, v = part.partition("=")
            out[k.strip()] = float(v)
    return out


def _scale(c: dict, kv: dict[str, float]) -> None:
    """The multipliers of a class's fields (see the docstring)."""
    if "dmg" in kv:
        c["rail"]["damage"] = round(c["rail"]["damage"] * kv["dmg"], 1)
    if "cd" in kv:
        c["rail"]["cd"] = round(c["rail"]["cd"] * kv["cd"], 2)
    if "laser" in kv:
        c["laser"]["damage"] = round(c["laser"]["damage"] * kv["laser"], 1)
    if "mcd" in kv:
        c["missiles"]["cd"] = round(c["missiles"]["cd"] * kv["mcd"], 1)
    if "range" in kv:
        c["rail"]["range"] = round(c["rail"]["range"] * kv["range"])
    if "track" in kv:
        c["gunnery"]["track_mrad"] = round(c["gunnery"]["track_mrad"] * kv["track"], 2)
    if "hull" in kv:
        c["hull"] = round(c["hull"] * kv["hull"])
    if "shield" in kv:
        c["shield"] = round(c["shield"] * kv["shield"])
    if "regen" in kv:
        c["shield_regen"] = round(c["shield_regen"] * kv["regen"], 2)


def variant_table(a) -> dict:
    """data/war/classes.json with the changes the options ask for."""
    d = json.loads(CLASSES.read_text())
    small, msmall, ach, aq = _kv(a.small), _kv(a.mandate_small), _kv(a.acheron), _kv(a.aquila)
    cells, salvo = _kv(a.missiles), _kv(a.salvo)
    for c in d["classes"]:
        key = c["key"]
        if key in ("vigilant", "styx", "lethe") and small:
            _scale(c, small)
        if key in ("styx", "lethe") and msmall:
            _scale(c, msmall)
        if key == "acheron" and ach:
            _scale(c, ach)
        if key == "aquila" and aq:
            _scale(c, aq)
        if key in cells:
            c["missiles"]["count"] = int(cells[key])
        if key in salvo:
            c["missiles"]["salvo"] = int(salvo[key])
    return d


def _records(tag: str) -> list[dict]:
    files = sorted(glob.glob(f"{WAR}/{tag}_*.json"), key=lambda p: int(re.search(r"_(\d+)\.json$", p).group(1)))
    out = []
    for p in files:
        raw = Path(p).read_bytes()
        enc = "utf-16" if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else "utf-8"
        out.append(json.loads(raw.decode(enc)))
    return out


def _books(d: dict) -> dict:
    """What a record says of how it ended: the Aquila's state, the warships each side lost, the Mandate's missiles that were not stopped."""
    r = {"aq_alive": None, "aq_hull": None, "astra_lost": 0, "mandate_lost": 0, "missiles": 0, "missiles_through": 0}
    for s in d["final"]["ships"]:
        if s.get("craft") or s["side"] not in ("astra", "mandate"):
            continue
        if s["c"] == "AQUILA":
            r["aq_alive"] = 1 if s.get("alive") else 0
            r["aq_hull"] = s.get("hull") if s.get("alive") else None
            continue
        if not s.get("alive") or s.get("fate") in ("destroyed", "disabled", "gone"):
            r["astra_lost" if s["side"] == "astra" else "mandate_lost"] += 1
    m = d["stats"].get("missiles", {}).get("mandate", {})
    r["missiles"] = m.get("fired", 0)
    r["missiles_through"] = max(0, m.get("fired", 0) - m.get("shot_down", 0) - m.get("decoyed", 0))
    return r


def _mean(xs: list) -> float:
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else float("nan")


def cmd_classes(a) -> None:
    WAR.mkdir(parents=True, exist_ok=True)
    table = WAR / f"classes_{a.tag}.json"
    table.write_text(json.dumps(variant_table(a), indent=2))
    py = sys.executable or "python3"
    for key in a.scen.split(","):
        label, scenario, script, seconds, at, more = SCENARIOS[key]
        if key == "o13" and a.o13:
            at = opening_at(*[float(x) for x in a.o13.split(",")])
        tag = f"cx_{a.tag}_{key}"
        cmd = [py, str(ROOT / "tools" / "war.py"), "batch", "--seeds", str(a.seeds), "--seconds", str(seconds), "--tag", tag, "--classes", str(table)]
        cmd += ["--scenario", scenario] if scenario else ["--jump", "160"]
        if script:
            cmd += ["--script", script]
        if at:
            cmd += ["--at", at]
        if a.exec:
            cmd += ["--exec", a.exec]
        cmd += more
        out = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True).stdout
        outcome = next((l.strip() for l in out.splitlines() if "outcome over" in l), "")
        fight = subprocess.run([py, str(ROOT / "tools" / "war.py"), "fight", "--tag", tag], cwd=str(ROOT), capture_output=True, text=True).stdout
        print(f"== {a.tag} | {label}", flush=True)
        m = re.search(r"ASTRA ahead (\d+), Mandate ahead (\d+), level (\d+); survivors edge ([+-][\d.]+)±([\d.]+)", outcome)
        if m:
            print("   ahead ASTRA %s / Mandate %s / level %s, survivors edge %s ± %s" % m.groups())
        books = [_books(d) for d in _records(tag)]
        n = max(1, len(books))
        aq = [b["aq_alive"] for b in books]
        if scenario in ("duel_aq_strike", "", "main_body"):                      # (the scenarios the Aquila fights in)
            print("   Aquila alive in %d of %d, hull of the living %.0f%%, of all (the lost as 0) %.0f%%" % (sum(v or 0 for v in aq), n, _mean([b["aq_hull"] for b in books]),
                                                                                             _mean([b["aq_hull"] if b["aq_hull"] is not None else 0 for b in books])))
        print("   warships lost: ASTRA %.2f, Mandate %.2f; the Mandate's missiles: %.0f fired, %.1f not stopped" % (
            _mean([b["astra_lost"] for b in books]), _mean([b["mandate_lost"] for b in books]), _mean([b["missiles"] for b in books]), _mean([b["missiles_through"] for b in books])))
        for line in fight.splitlines():
            for k in ("action: first shot", "warships put out", "... by the Aquila", "... by ASTRA ships", "retreats (groups", "Aquila: most fires"):
                if k in line:
                    print("   " + " ".join(line.split()))
                    break
        sys.stdout.flush()
