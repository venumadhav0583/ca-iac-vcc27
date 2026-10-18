"""Ephemeral vs long-lived deployments. A deployment placed once at instant k
and kept for L instants is scored by the share of those L instants in which its
tier met the budget. Compared with (a) the same lifetime re-resolved every
instant and (b) static placement. Same logs, same measurements."""
import glob, json, os
import numpy as np
from config import WORKLOADS
RES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results")
ALLOWED = {"any": ["edge", "fog", "cloud"], "region": ["edge", "fog"]}
runs = [[json.loads(l) for l in open(f) if '"instant"' in l[:30]]
        for f in sorted(glob.glob(os.path.join(RES, "raw", "eval_seed*.jsonl")))]
gap = float(np.median([r[k+1]["t"] - r[k]["t"] for r in runs for k in range(len(r)-1)]))
met = lambda r, wl, t: t in ALLOWED[WORKLOADS[wl]["residency"]] and r["measured"][wl][t]["p95"] <= WORKLOADS[wl]["budget"]
out = dict(instant_spacing_s=gap, lifetimes={})
for L in [1, 2, 4, 8, 16, 30]:
    once, rere, stat = [], [], []
    for r in runs:
        for k in range(0, len(r) - L + 1):
            for wl in WORKLOADS:
                t0 = r[k]["decisions"]["reactive"][wl]
                once.append(np.mean([met(r[k+i], wl, t0) for i in range(L)]))
                rere.append(np.mean([met(r[k+i], wl, r[k+i]["decisions"]["reactive"][wl]) for i in range(L)]))
                stat.append(np.mean([met(r[k+i], wl, r[k+i]["decisions"]["static"][wl]) for i in range(L)]))
    out["lifetimes"][str(L)] = dict(lifetime_s=L*gap, placed_once=float(np.mean(once)),
                                    reresolved=float(np.mean(rere)), static=float(np.mean(stat)), n=len(once))
json.dump(out, open(os.path.join(RES, "lifetime.json"), "w"), indent=2)
for L, v in out["lifetimes"].items():
    print(f"lifetime {v['lifetime_s']:5.0f}s  placed-once {100*v['placed_once']:.1f}%  re-resolved {100*v['reresolved']:.1f}%  static {100*v['static']:.1f}%")
