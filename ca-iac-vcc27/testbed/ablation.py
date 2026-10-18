"""Offline ablation of the CPR decision rule on logged reactive telemetry.

Each instant logs the reactive estimates the CPR saw and the measured p95
latency of every workload on every tier, so any decision rule can be scored
exactly (paired) without re-running the testbed. A Python replica of the Go
rule is first checked against the logged Go decisions.
"""
import glob, json, os
import numpy as np
from config import TIERS, WORKLOADS, MULT
HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "..", "results")
ALLOWED = {"any": TIERS, "region": ["edge", "fog"], "local": ["edge"]}
STATIC = {"iot_ingest": "edge", "regional_compliance": "fog", "batch_ml": "cloud"}


def rule(spec, est, order="edge_first", headroom=0.2, margin=0.0):
    allowed = [t for t in ALLOWED[spec["residency"]] if t in est and est[t]["up"]]
    if not est:
        return STATIC_FOR(spec)
    cand = []
    for t in allowed:
        v = est[t]["p95_rtt_ms"] + spec["compute"] * MULT[t]
        ok = v <= spec["budget"] * (1 - margin) and (1 - est[t]["util"]) >= headroom
        cand.append((t, v, ok))
    if not cand:
        return None
    feas = [c for c in cand if c[2]]
    if feas:
        if order == "edge_first":
            return feas[0][0]
        if order == "min_latency":
            return min(feas, key=lambda c: c[1])[0]
    return min(cand, key=lambda c: c[1])[0]


def STATIC_FOR(spec):
    for wl, s in WORKLOADS.items():
        if s is spec: return STATIC[wl]


def main():
    inst = []
    for f in sorted(glob.glob(os.path.join(RES, "raw", "eval_seed*.jsonl"))):
        for l in open(f):
            r = json.loads(l)
            if r["kind"] == "instant":
                r["seed"] = f; inst.append(r)
    # 1) replica check
    agree = tot = 0
    for r in inst:
        for wl, spec in WORKLOADS.items():
            d = rule(spec, r["reactive_est"])
            tot += 1; agree += (d == r["decisions"]["reactive"][wl])
    variants = {
        "edge-first, headroom 0.2 (deployed)": dict(order="edge_first", headroom=0.2),
        "edge-first, headroom 0.0": dict(order="edge_first", headroom=0.0),
        "edge-first, headroom 0.4": dict(order="edge_first", headroom=0.4),
        "edge-first, 25% budget margin": dict(order="edge_first", headroom=0.2, margin=0.25),
        "min-latency, headroom 0.2": dict(order="min_latency", headroom=0.2),
        "min-latency, 25% budget margin": dict(order="min_latency", headroom=0.2, margin=0.25),
    }
    out = dict(replica_agreement=agree / tot, n=tot, variants={})
    for name, kw in variants.items():
        ok = []; per = {wl: [] for wl in WORKLOADS}
        for r in inst:
            for wl, spec in WORKLOADS.items():
                t = rule(spec, r["reactive_est"], **kw)
                s = t is not None and t in ALLOWED[spec["residency"]] and r["measured"][wl][t]["p95"] <= spec["budget"]
                ok.append(s); per[wl].append(s)
        out["variants"][name] = dict(slo=float(np.mean(ok)), **{wl: float(np.mean(v)) for wl, v in per.items()})
    json.dump(out, open(os.path.join(RES, "ablation.json"), "w"), indent=2)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()


def failure_breakdown():
    """Classify reactive-CPR failures where the oracle succeeded."""
    import collections
    c = collections.Counter()
    for f in sorted(glob.glob(os.path.join(RES, "raw", "eval_seed*.jsonl"))):
        for l in open(f):
            r = json.loads(l)
            if r["kind"] != "instant": continue
            for wl, spec in WORKLOADS.items():
                m = r["measured"][wl]
                t = r["decisions"]["reactive"][wl]
                ok = m[t]["p95"] <= spec["budget"]
                feas = any(m[x]["p95"] <= spec["budget"] for x in ALLOWED[spec["residency"]])
                if ok or not feas:
                    continue
                est = r["reactive_est"].get(t)
                v = est["p95_rtt_ms"] + spec["compute"] * MULT[t] if est else None
                c["optimistic_estimate" if v is not None and v <= spec["budget"] else "no_tier_estimated_feasible"] += 1
    return dict(c)


if __name__ == "__main__":
    fb = failure_breakdown()
    d = json.load(open(os.path.join(RES, "ablation.json"))); d["reactive_failures_oracle_feasible"] = fb
    json.dump(d, open(os.path.join(RES, "ablation.json"), "w"), indent=2); print(fb)
