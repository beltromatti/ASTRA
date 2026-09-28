"""Summarise an Unreal CSV profile: frame/game/render/GPU times over the steady-state part of the run.
Usage: python csv_summary.py <file.csv> [--skip-frac 0.4] [--json out.json]"""
import csv
csv.field_size_limit(1 << 28)
import json
import statistics
import sys


def pct(values, p):
    v = sorted(values)
    if not v:
        return float("nan")
    k = min(len(v) - 1, max(0, int(round(p / 100.0 * (len(v) - 1)))))
    return v[k]


def main():
    path = sys.argv[1]
    skip = float(sys.argv[sys.argv.index("--skip-frac") + 1]) if "--skip-frac" in sys.argv else 0.4
    csv.field_size_limit(10 ** 9)              # the EVENTS column can be long
    with open(path, newline="") as fh:
        rows = [r for r in csv.reader(fh)]
    header, body = rows[0], rows[1:]
    if body and body[-1] and body[-1][0] == "[HasHeaderRowAtEnd]":
        # stats that appeared during the capture: the complete header is written at the end, above the metadata row
        header, body = body[-2], body[:-2]
    ft = header.index("FrameTime")

    def is_num(x):
        try:
            float(x)
            return True
        except ValueError:
            return False

    data = [r for r in body if len(r) > ft and is_num(r[ft])]
    start = int(len(data) * skip)            # skip loading / shader warm-up
    data = data[start:]
    col = {h: i for i, h in enumerate(header)}
    out = {"file": path, "frames": len(data)}
    for key in ("FrameTime", "GameThreadTime", "RenderThreadTime", "GPUTime", "RHIThreadTime",
                "GPU/Total", "GPU/BasePass", "GPU/Lumen", "GPU/ShadowDepths", "GPU/Nanite", "GPU/Translucency",
                "GPU/PostProcessing", "MemoryFreeMB", "PhysicalUsedMB"):
        if key in col:
            vals = [float(r[col[key]]) for r in data if len(r) > col[key] and r[col[key]] not in ("", "nan")]
            if vals:
                out[key] = {"median": round(statistics.median(vals), 2), "p95": round(pct(vals, 95), 2),
                            "max": round(max(vals), 2)}
    if "FrameTime" in out:
        out["fps_median"] = round(1000.0 / out["FrameTime"]["median"], 1)
        out["fps_p95_frame"] = round(1000.0 / out["FrameTime"]["p95"], 1)
    gpu_cols = sorted([h for h in header if h.startswith("GPU/")],
                      key=lambda h: -statistics.median([float(r[col[h]]) for r in data if len(r) > col[h] and r[col[h]] not in ("", "nan")] or [0]))
    out["gpu_top"] = [(h, round(statistics.median([float(r[col[h]]) for r in data if len(r) > col[h] and r[col[h]] not in ("", "nan")] or [0]), 2))
                      for h in gpu_cols[:12]]
    if "--json" in sys.argv:
        with open(sys.argv[sys.argv.index("--json") + 1], "w") as fh:
            json.dump(out, fh, indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
