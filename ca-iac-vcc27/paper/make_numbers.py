"""Generate numbers.tex from results/summary.json and train_report.json.
Every quantitative claim in the paper is a macro defined here."""
import json, os
H = os.path.dirname(os.path.abspath(__file__))
S = json.load(open(os.path.join(H, "..", "results", "summary.json")))
T = json.load(open(os.path.join(H, "..", "results", "train_report.json")))
out = []
def d(name, val): out.append(f"\\newcommand{{\\{name}}}{{{val}}}")
pct = lambda x: f"{100*x:.1f}\\%"
def ci(e): return f"{100*e['rate']:.1f}\\% [{100*e['ci95'][0]:.1f}, {100*e['ci95'][1]:.1f}]"
d("NSeeds", S["n_seeds"]); d("NInstants", S["n_instants"]); d("NPlacements", S["n_placements"])
names = dict(static="Static", reactive="Reactive", predictive="Predictive", oracle="Oracle")
for p, n in names.items():
    d(f"Slo{n}", pct(S["slo"][p]["rate"])); d(f"Slo{n}CI", ci(S["slo"][p]))
    d(f"Slo{n}NoOut", pct(S["slo"][p + "_no_outage"]["rate"]))
wlname = dict(iot_ingest="A", regional_compliance="B", batch_ml="C")
for wl, L in wlname.items():
    for p, n in names.items():
        d(f"Slo{L}{n}", ci(S["by_workload"][wl][p]))
for k, v in S["tests"].items():
    n = "".join(w.capitalize() for w in k.split("_"))
    d(f"Mc{n}A", v["a_only"]); d(f"Mc{n}B", v["b_only"])
    d(f"Mc{n}P", f"{v['p_exact']:.2g}" if v["p_exact"] >= 1e-4 else "<10^{-4}")
for p, n in names.items():
    if p == "oracle": continue
    d(f"Resid{n}", S["residency_violations"][p]); d(f"DownEdge{n}", S["outage_placements_on_down_edge"][p])
d("OutageInstants", S["outage_instants"])
o = S["overhead_ms"]
d("CprMed", f"{o['cpr_reactive_median']:.1f}"); d("CprPninetyfive", f"{o['cpr_reactive_p95']:.1f}")
d("PredMed", f"{o['predictor_median']:.1f}"); d("PredPninetyfive", f"{o['predictor_p95']:.1f}")
for P, v in S["drift_detection"].items():
    w = {"1": "One", "2": "Two", "5": "Five", "10": "Ten"}[P]
    d(f"Drift{w}Med", f"{v['median_s']:.1f}"); d(f"Drift{w}Max", f"{v['max_s']:.1f}")
d("DriftN", S["drift_detection"]["1"]["n"])
for wl, L in wlname.items():
    for p, n in names.items():
        if p == "oracle": continue
        for t in ["edge", "fog", "cloud"]:
            d(f"Cnt{L}{n}{t.capitalize()}", S["by_workload"][wl]["tier_counts"][p][t])
d("NTrain", T["n_train"])
cv = T["cv"]
d("CovModel", f"{100*min(c['coverage_model'] for c in cv):.0f}--{100*max(c['coverage_model'] for c in cv):.0f}\\%")
d("CovReact", f"{100*min(c['coverage_reactive'] for c in cv):.0f}--{100*max(c['coverage_reactive'] for c in cv):.0f}\\%")
d("MaeModel", f"{min(c['mae_model'] for c in cv):.0f}--{max(c['mae_model'] for c in cv):.0f}")
d("MaeReact", f"{min(c['mae_reactive'] for c in cv):.0f}--{max(c['mae_reactive'] for c in cv):.0f}")
open(os.path.join(H, "numbers.tex"), "w").write("\n".join(out) + "\n")
print("\n".join(out))

# Decision-rule ablation (offline, reactive telemetry)
A = json.load(open(os.path.join(H, "..", "results", "ablation.json")))
extra = [f"\\newcommand{{\\ReplicaAgree}}{{{100*A['replica_agreement']:.0f}\\%}}"]
vs = [v["slo"] for v in A["variants"].values()]
extra.append(f"\\newcommand{{\\AblMin}}{{{100*min(vs):.1f}\\%}}")
extra.append(f"\\newcommand{{\\AblMax}}{{{100*max(vs):.1f}\\%}}")
fb = A["reactive_failures_oracle_feasible"]
extra.append(f"\\newcommand{{\\FailOpt}}{{{fb['optimistic_estimate']}}}")
extra.append(f"\\newcommand{{\\FailPess}}{{{fb['no_tier_estimated_feasible']}}}")
extra.append(f"\\newcommand{{\\FailTot}}{{{fb['optimistic_estimate']+fb['no_tier_estimated_feasible']}}}")
open(os.path.join(H, "numbers.tex"), "a").write("\n".join(extra) + "\n")
print("\n".join(extra))

# Staleness and deployment lifetime
L = json.load(open(os.path.join(H, "..", "results", "lifetime.json")))
ex = [f"\\newcommand{{\\InstGap}}{{{L['instant_spacing_s']:.0f}}}"]
w = {"1": "One", "2": "Two", "4": "Four", "8": "Eight", "16": "Sixteen", "30": "Thirty"}
for k, v in L["lifetimes"].items():
    ex.append(f"\\newcommand{{\\Lt{w[k]}Sec}}{{{v['lifetime_s']:.0f}}}")
    ex.append(f"\\newcommand{{\\Lt{w[k]}Once}}{{{100*v['placed_once']:.1f}}}")
    ex.append(f"\\newcommand{{\\Lt{w[k]}Rere}}{{{100*v['reresolved']:.1f}}}")
    ex.append(f"\\newcommand{{\\Lt{w[k]}Static}}{{{100*v['static']:.1f}}}")
open(os.path.join(H, "numbers.tex"), "a").write("\n".join(ex) + "\n")
print("\n".join(ex))

# Statistical audit: Holm-adjusted p and seed-cluster bootstrap CIs on paired differences
SA = json.load(open(os.path.join(H, "..", "results", "stats_audit.json")))
f = lambda x: f"{100*x:+.1f}"
ci2 = lambda c: f"[{100*c[0]:+.1f}, {100*c[1]:+.1f}]"
sa = []
for key, nm in [("predictive_vs_static", "PS"), ("reactive_vs_static", "RS"), ("predictive_vs_reactive", "PR")]:
    v = SA[key]
    sa += [f"\\newcommand{{\\Diff{nm}}}{{{f(v['diff'])}}}", f"\\newcommand{{\\Diff{nm}CI}}{{{ci2(v['ci95'])}}}",
           f"\\newcommand{{\\Holm{nm}}}{{{v['p_holm']:.2g}}}"]
for key, nm in [("A_reactive_vs_static", "ARS"), ("A_predictive_vs_static", "APS")]:
    v = SA[key]
    sa += [f"\\newcommand{{\\Diff{nm}}}{{{f(v['diff'])}}}", f"\\newcommand{{\\Diff{nm}CI}}{{{ci2(v['ci95'])}}}"]
LC = json.load(open(os.path.join(H, "..", "results", "lifetime_ci.json")))
for k, v in LC["lifetimes"].items():
    nm = w[k]
    sa += [f"\\newcommand{{\\Lt{nm}OS}}{{{f(v['once_minus_static'])}}}", f"\\newcommand{{\\Lt{nm}OSCI}}{{{ci2(v['once_minus_static_ci'])}}}",
           f"\\newcommand{{\\Lt{nm}RO}}{{{f(v['rere_minus_once'])}}}", f"\\newcommand{{\\Lt{nm}ROCI}}{{{ci2(v['rere_minus_once_ci'])}}}"]
p = os.path.join(H, "..", "results", "lifetime_ci_sens4.json")
if os.path.exists(p):
    LS = json.load(open(p))
    sa.append(f"\\newcommand{{\\SensRuns}}{{{LS['n_runs']}}}")
    for k, v in LS["lifetimes"].items():
        nm = w[k]
        sa += [f"\\newcommand{{\\Sens{nm}Once}}{{{100*v['once']:.1f}}}", f"\\newcommand{{\\Sens{nm}Rere}}{{{100*v['rere']:.1f}}}",
               f"\\newcommand{{\\Sens{nm}Static}}{{{100*v['static']:.1f}}}", f"\\newcommand{{\\Sens{nm}RO}}{{{f(v['rere_minus_once'])}}}",
               f"\\newcommand{{\\Sens{nm}ROCI}}{{{ci2(v['rere_minus_once_ci'])}}}", f"\\newcommand{{\\Sens{nm}OS}}{{{f(v['once_minus_static'])}}}",
               f"\\newcommand{{\\Sens{nm}OSCI}}{{{ci2(v['once_minus_static_ci'])}}}"]
open(os.path.join(H, "numbers.tex"), "a").write("\n".join(sa) + "\n")
print("\n".join(sa))
