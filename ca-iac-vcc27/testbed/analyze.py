"""Analyze evaluation logs -> results/summary.json + figures.

Unit of analysis: one (instant, workload) placement. All policies are scored
against the same measured per-tier latencies, so comparisons are paired.
CIs: cluster bootstrap over seeds (10,000 resamples). Paired tests: exact McNemar.
"""
import glob, json, os
import numpy as np
from scipy.stats import binomtest
from config import TIERS, WORKLOADS, PROBE_TIMEOUT_S, OUTAGE_S

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "..", "results")
ALLOWED = {"any": TIERS, "region": ["edge", "fog"], "local": ["edge"]}
POL = ["static", "reactive", "predictive", "oracle"]
rng = np.random.default_rng(12345)


def load():
    seeds = {}
    for f in sorted(glob.glob(os.path.join(RES, "raw", "eval_seed*.jsonl"))):
        meta, inst, probes = None, [], []
        for l in open(f):
            r = json.loads(l)
            if r["kind"] == "meta": meta = r
            elif r["kind"] == "instant": inst.append(r)
            elif r["kind"] == "probe": probes.append(r)
        seeds[meta["seed"]] = dict(meta=meta, inst=inst, probes=probes)
    return seeds


def outcomes(seeds):
    rows = []
    for s, d in seeds.items():
        for r in d["inst"]:
            for wl, spec in WORKLOADS.items():
                m = r["measured"][wl]
                ok_t = [t for t in ALLOWED[spec["residency"]] if m[t]["p95"] <= spec["budget"]]
                row = dict(seed=s, k=r["k"], wl=wl, outage=r["truth"]["edge_outage"],
                           cong=r["truth"]["cong"], feasible=bool(ok_t))
                for p in POL[:-1]:
                    dec = r["decisions"][p]
                    t = dec[wl] if dec else None
                    row[p + "_tier"] = t
                    row[p + "_resid_ok"] = t in ALLOWED[spec["residency"]]
                    row[p + "_slo"] = bool(row[p + "_resid_ok"] and m[t]["p95"] <= spec["budget"])
                    row[p + "_p95"] = m[t]["p95"]
                row["oracle_slo"] = bool(ok_t)
                rows.append(row)
    return rows


def cluster_ci(rows, key, filt=lambda r: True):
    by = {}
    for r in rows:
        if filt(r): by.setdefault(r["seed"], []).append(float(r[key]))
    seeds = list(by)
    point = np.mean([v for s in seeds for v in by[s]])
    boots = []
    for _ in range(10000):
        pick = rng.choice(seeds, len(seeds))
        vals = [v for s in pick for v in by[s]]
        boots.append(np.mean(vals))
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return dict(rate=float(point), ci95=[float(lo), float(hi)], n=int(sum(len(v) for v in by.values())))


def mcnemar(rows, a, b, filt=lambda r: True):
    sel = [r for r in rows if filt(r)]
    a_only = sum(r[a] and not r[b] for r in sel); b_only = sum(r[b] and not r[a] for r in sel)
    n = a_only + b_only
    p = binomtest(a_only, n, 0.5).pvalue if n else 1.0
    return dict(a_only=a_only, b_only=b_only, p_exact=float(p))


def drift(seeds, polls=(1, 2, 5, 10)):
    """Detection delay of an injected edge outage by a drift checker polling
    telemetry every P seconds and flagging after 2 consecutive failed probes.
    A failed probe's result is available PROBE_TIMEOUT_S after it was sent."""
    out = {P: [] for P in polls}
    for s, d in seeds.items():
        ep = [(p["t"], p["rtt_ms"]) for p in d["probes"] if p["tier"] == "edge"]
        for (a, b) in d["meta"]["outages"]:
            # time at which the second consecutive failure became known
            known = None
            prev_fail = False
            for t, rtt in ep:
                if t < a - 5: continue
                fail = rtt is None
                if fail and prev_fail and t + PROBE_TIMEOUT_S >= a:
                    known = t + PROBE_TIMEOUT_S; break
                prev_fail = fail
            if known is None: continue
            for P in polls:
                phase = rng.uniform(0, P)  # checker phase is independent of the outage
                base = a - P + phase       # some poll time before the outage starts
                poll_t = base + np.ceil((known - base) / P) * P
                out[P].append(float(poll_t - a))
    return {str(P): dict(n=len(v), median_s=float(np.median(v)) if v else None,
                          max_s=float(np.max(v)) if v else None) for P, v in out.items()}


def main():
    seeds = load()
    rows = outcomes(seeds)
    summ = dict(n_seeds=len(seeds), seeds=sorted(seeds), n_instants=int(sum(len(d["inst"]) for d in seeds.values())),
                n_placements=len(rows), slo={}, by_workload={}, residency_violations={}, tests={})
    for p in POL:
        summ["slo"][p] = cluster_ci(rows, p + "_slo")
        summ["slo"][p + "_no_outage"] = cluster_ci(rows, p + "_slo", lambda r: not r["outage"])
    for wl in WORKLOADS:
        summ["by_workload"][wl] = {p: cluster_ci(rows, p + "_slo", lambda r, wl=wl: r["wl"] == wl) for p in POL}
        summ["by_workload"][wl]["tier_counts"] = {
            p: {t: sum(r[p + "_tier"] == t for r in rows if r["wl"] == wl) for t in TIERS} for p in POL[:-1]}
    for p in POL[:-1]:
        summ["residency_violations"][p] = int(sum(not r[p + "_resid_ok"] for r in rows))
    summ["tests"]["reactive_vs_static"] = mcnemar(rows, "reactive_slo", "static_slo")
    summ["tests"]["predictive_vs_reactive"] = mcnemar(rows, "predictive_slo", "reactive_slo")
    summ["tests"]["predictive_vs_static"] = mcnemar(rows, "predictive_slo", "static_slo")
    summ["outage_placements_on_down_edge"] = {
        p: int(sum(r["outage"] and r[p + "_tier"] == "edge" for r in rows)) for p in POL[:-1]}
    summ["outage_instants"] = int(sum(r["outage"] for r in rows) // len(WORKLOADS))
    cpr = [r["cpr_ms"] for d in seeds.values() for r in d["inst"]]
    summ["overhead_ms"] = dict(
        cpr_reactive_median=float(np.median([c["reactive"] for c in cpr])),
        cpr_reactive_p95=float(np.percentile([c["reactive"] for c in cpr], 95)),
        cpr_predictive_median=float(np.median([c["predictive"] for c in cpr if c["predictive"]])),
        predictor_median=float(np.median([c["predictor_ms"] for c in cpr if c["predictor_ms"]])),
        predictor_p95=float(np.percentile([c["predictor_ms"] for c in cpr if c["predictor_ms"]], 95)))
    summ["drift_detection"] = drift(seeds)
    summ["per_seed_slo"] = {str(s): {p: float(np.mean([r[p + "_slo"] for r in rows if r["seed"] == s]))
                                     for p in POL} for s in sorted(seeds)}
    json.dump(summ, open(os.path.join(RES, "summary.json"), "w"), indent=2)
    json.dump(rows, open(os.path.join(RES, "placements.json"), "w"))
    figure(rows, summ)
    print(json.dumps({k: summ[k] for k in ["n_seeds", "n_instants", "n_placements", "slo", "tests",
                                          "residency_violations", "outage_placements_on_down_edge",
                                          "overhead_ms", "drift_detection"]}, indent=1))


def figure(rows, summ):
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family": "serif", "font.size": 8})
    fig, ax = plt.subplots(figsize=(3.4, 1.9))
    wls = list(WORKLOADS); x = np.arange(len(wls)); w = 0.2
    labels = {"static": "Static", "reactive": "Reactive CPR", "predictive": "Predictive CPR", "oracle": "Oracle"}
    cols = {"static": "#9e9e9e", "reactive": "#4a78b5", "predictive": "#d1793a", "oracle": "#4b9a5b"}
    for i, p in enumerate(POL):
        v = [summ["by_workload"][wl][p] for wl in wls]
        r = np.array([e["rate"] for e in v]) * 100
        lo = r - np.array([e["ci95"][0] for e in v]) * 100; hi = np.array([e["ci95"][1] for e in v]) * 100 - r
        ax.bar(x + (i - 1.5) * w, r, w, yerr=[lo, hi], capsize=1.5, color=cols[p], label=labels[p],
               error_kw=dict(lw=0.6))
    ax.set_xticks(x); ax.set_xticklabels(["A: IoT ingest", "B: Regional", "C: Batch ML"])
    ax.set_ylabel("SLO attainment (%)"); ax.set_ylim(0, 105)
    ax.legend(ncol=2, fontsize=6, frameon=False, loc="lower left")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout(); fig.savefig(os.path.join(RES, "fig_slo.pdf")); fig.savefig(os.path.join(RES, "fig_slo.png"), dpi=200)


if __name__ == "__main__":
    main()
