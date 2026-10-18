"""Seed-cluster bootstrap CIs for the lifetime analysis (paired differences)."""
import glob, json, os, sys
import numpy as np
from config import WORKLOADS
RAW = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results", "raw")
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(RAW, "..", "lifetime_ci.json")
ALLOWED = {"any": ["edge", "fog", "cloud"], "region": ["edge", "fog"]}
runs = [[json.loads(l) for l in open(f) if '"instant"' in l[:30]] for f in sorted(glob.glob(os.path.join(RAW, "eval_seed*.jsonl")))]
gap = float(np.median([r[k+1]["t"] - r[k]["t"] for r in runs for k in range(len(r)-1)]))
met = lambda r, wl, t: t in ALLOWED[WORKLOADS[wl]["residency"]] and r["measured"][wl][t]["p95"] <= WORKLOADS[wl]["budget"]
rng = np.random.default_rng(3); out = dict(instant_spacing_s=gap, n_runs=len(runs), lifetimes={})
for L in [1, 2, 4, 8, 16, 30]:
    per = []  # per run: lists of (once, rere, static)
    for r in runs:
        rows = []
        for k in range(0, len(r) - L + 1):
            for wl in WORKLOADS:
                t0 = r[k]["decisions"]["reactive"][wl]
                rows.append((np.mean([met(r[k+i], wl, t0) for i in range(L)]),
                             np.mean([met(r[k+i], wl, r[k+i]["decisions"]["reactive"][wl]) for i in range(L)]),
                             np.mean([met(r[k+i], wl, r[k+i]["decisions"]["static"][wl]) for i in range(L)])))
        per.append(np.array(rows))
    allr = np.vstack(per)
    def boot(f):
        b = [f(np.vstack([per[i] for i in rng.integers(0, len(per), len(per))])) for _ in range(5000)]
        return [float(x) for x in np.percentile(b, [2.5, 97.5])]
    out["lifetimes"][str(L)] = dict(lifetime_s=L*gap, once=float(allr[:,0].mean()), rere=float(allr[:,1].mean()), static=float(allr[:,2].mean()),
        once_minus_static=float((allr[:,0]-allr[:,2]).mean()), once_minus_static_ci=boot(lambda a: (a[:,0]-a[:,2]).mean()),
        rere_minus_once=float((allr[:,1]-allr[:,0]).mean()), rere_minus_once_ci=boot(lambda a: (a[:,1]-a[:,0]).mean()))
json.dump(out, open(OUT, "w"), indent=2)
for L, v in out["lifetimes"].items():
    print(f"{v['lifetime_s']:4.0f}s once {100*v['once']:.1f} rere {100*v['rere']:.1f} static {100*v['static']:.1f} | once-static {100*v['once_minus_static']:+.1f} {np.round(np.array(v['once_minus_static_ci'])*100,1)} | rere-once {100*v['rere_minus_once']:+.1f} {np.round(np.array(v['rere_minus_once_ci'])*100,1)}")
