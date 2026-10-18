"""How fast does a placement decision go stale? Apply the reactive CPR decision
made j instants earlier to the measurements at instant k (same run). j=0 is the
deployed behaviour; static placement is the never-refreshed limit."""
import glob, json, os
import numpy as np
from config import WORKLOADS
RES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results")
ALLOWED = {"any": ["edge", "fog", "cloud"], "region": ["edge", "fog"]}
runs = []
for f in sorted(glob.glob(os.path.join(RES, "raw", "eval_seed*.jsonl"))):
    runs.append([json.loads(l) for l in open(f) if '"instant"' in l[:30]])
gap = np.median([r[k+1]["t"] - r[k]["t"] for r in runs for k in range(len(r)-1)])
out = {"instant_spacing_s": float(gap), "lags": {}}
for j in [0, 1, 2, 4, 8, 16]:
    ok = []; okA = []
    for r in runs:
        for k in range(j, len(r)):
            for wl, s in WORKLOADS.items():
                t = r[k - j]["decisions"]["reactive"][wl]
                v = t in ALLOWED[s["residency"]] and r[k]["measured"][wl][t]["p95"] <= s["budget"]
                ok.append(v); okA += [v] if wl == "iot_ingest" else []
    out["lags"][str(j)] = dict(age_s=float(j * gap), slo=float(np.mean(ok)), slo_A=float(np.mean(okA)), n=len(ok))
json.dump(out, open(os.path.join(RES, "staleness.json"), "w"), indent=2)
for j, v in out["lags"].items(): print(f"decision age {v['age_s']:6.0f}s  SLO all {100*v['slo']:.1f}%  IoT-ingest {100*v['slo_A']:.1f}%  (n={v['n']})")
