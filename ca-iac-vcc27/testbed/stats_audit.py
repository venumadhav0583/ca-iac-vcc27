"""Statistical audit: Holm-adjusted McNemar, and seed-cluster bootstrap CIs on
paired differences (respects within-run dependence that McNemar ignores)."""
import json, os, numpy as np
from scipy.stats import binomtest
RES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results")
rows = json.load(open(os.path.join(RES, "placements.json")))
rng = np.random.default_rng(7)
def mcn(sel, a, b):
    ao = sum(r[a] and not r[b] for r in sel); bo = sum(r[b] and not r[a] for r in sel)
    return ao, bo, binomtest(ao, ao + bo, 0.5).pvalue if ao + bo else 1.0
def diff_ci(sel, a, b, B=10000):
    seeds = sorted({r["seed"] for r in sel}); by = {s: [r for r in sel if r["seed"] == s] for s in seeds}
    d = lambda rs: np.mean([r[a] for r in rs]) - np.mean([r[b] for r in rs])
    pt = d(sel); bs = []
    for _ in range(B):
        rs = [x for s in rng.choice(seeds, len(seeds)) for x in by[s]]; bs.append(d(rs))
    return pt, np.percentile(bs, [2.5, 97.5])
out = {}
tests = [("predictive_slo", "static_slo"), ("reactive_slo", "static_slo"), ("predictive_slo", "reactive_slo")]
ps = [mcn(rows, a, b)[2] for a, b in tests]
order = np.argsort(ps); m = len(ps); holm = [None]*m; run = 0
for i, k in enumerate(order):
    run = max(run, min(1, (m - i) * ps[k])); holm[k] = run
for (a, b), p, h in zip(tests, ps, holm):
    pt, ci = diff_ci(rows, a, b)
    out[f"{a[:-4]}_vs_{b[:-4]}"] = dict(p_raw=p, p_holm=h, diff=pt, ci95=list(ci))
A = [r for r in rows if r["wl"] == "iot_ingest"]
for a in ["reactive_slo", "predictive_slo"]:
    pt, ci = diff_ci(A, a, "static_slo"); ao, bo, p = mcn(A, a, "static_slo")
    out[f"A_{a[:-4]}_vs_static"] = dict(diff=pt, ci95=list(ci), p_raw=p, discordant=[ao, bo])
json.dump(out, open(os.path.join(RES, "stats_audit.json"), "w"), indent=2)
for k, v in out.items(): print(k, {kk: (np.round(vv, 4).tolist() if not isinstance(vv, list) or isinstance(vv[0], float) else vv) for kk, vv in v.items()})
