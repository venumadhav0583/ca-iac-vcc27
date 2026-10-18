"""Timeline figure for one evaluation seed: edge probe RTT, congestion and
outage periods (ground truth from the trace), and where static and reactive
CPR placed workload A at each decision instant."""
import json, os, sys
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
sys.path.insert(0, os.path.dirname(__file__))
import testbed as tb
HERE = os.path.dirname(os.path.abspath(__file__)); RES = os.path.join(HERE, "..", "results")
seed = int(sys.argv[1]) if len(sys.argv) > 1 else 3
rows = [json.loads(l) for l in open(os.path.join(RES, "raw", f"eval_seed{seed}.jsonl"))]
meta = rows[0]; trace = tb.Trace(seed, meta["T"], [tuple(o) for o in meta["outages"]])
pr = [(r["t"], r["rtt_ms"]) for r in rows if r["kind"] == "probe" and r["tier"] == "edge"]
inst = [r for r in rows if r["kind"] == "instant"]
plt.rcParams.update({"font.family": "serif", "font.size": 7})
fig, (a1, a2) = plt.subplots(2, 1, figsize=(3.4, 2.5), sharex=True, gridspec_kw=dict(height_ratios=[2.2, 1]))
t = np.array([p[0] for p in pr]); y = np.array([p[1] if p[1] is not None else np.nan for p in pr])
a1.plot(t, y, lw=0.5, color="#4a78b5")
fail = [p[0] for p in pr if p[1] is None]
a1.plot(fail, [140] * len(fail), "|", ms=3, color="#b23b3b", label="probe timeout")
for arr, col, lab in [(trace.cong["edge"], "#f2c14e", "congested"), (trace.outage, "#b23b3b", "outage")]:
    on = np.flatnonzero(np.diff(np.r_[0, arr.astype(int), 0]))
    for i, (s, e) in enumerate(zip(on[::2], on[1::2])):
        a1.axvspan(s, e, color=col, alpha=0.25, lw=0, label=lab if i == 0 else None)
a1.set_ylabel("Edge probe RTT (ms)"); a1.set_ylim(0, 150); a1.legend(fontsize=5.5, frameon=False, ncol=3, loc="lower center", bbox_to_anchor=(0.5, 1.0))
lvl = {"edge": 0, "fog": 1, "cloud": 2}
ti = [r["t"] for r in inst]
for pol, mk, col in [("static", "s", "#9e9e9e"), ("reactive", "o", "#4a78b5")]:
    ok = [r["measured"]["iot_ingest"][r["decisions"][pol]["iot_ingest"]]["p95"] <= 30 for r in inst]
    yy = [lvl[r["decisions"][pol]["iot_ingest"]] + (0.12 if pol == "reactive" else -0.12) for r in inst]
    a2.scatter(ti, yy, s=6, marker=mk, facecolors=[col if o else "none" for o in ok], edgecolors=col, lw=0.6,
               label=f"{pol} (filled = SLO met)")
a2.set_yticks([0, 1, 2]); a2.set_yticklabels(["edge", "fog", "cloud"]); a2.set_ylim(-0.5, 3.4)
a2.set_xlabel("Time (s)"); a2.legend(fontsize=5.5, frameon=False, ncol=2, loc="upper center", handletextpad=0.2)
for ax in (a1, a2): ax.spines[["top", "right"]].set_visible(False)
fig.tight_layout(h_pad=0.3)
fig.savefig(os.path.join(RES, "fig_timeline.pdf")); fig.savefig(os.path.join(RES, "fig_timeline.png"), dpi=200)
print("ok", seed, meta["outages"])
