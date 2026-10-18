# CA-IaC: network-aware, continuously re-resolved placement in Infrastructure as Code

Code, raw logs and analysis behind the paper *"Placement Decisions Go Stale: Network-Aware,
Continuously Re-Resolved Placement in Infrastructure as Code for the Edge–Fog–Cloud Continuum"*
(Venumadhav Kalluru). Every number in the paper is generated from the files here.

## Layout
| Path | What it is |
|---|---|
| `iac/workloads.tf` | `continuum_placement` annotations for the three workloads |
| `cpr/` | Continuum Placement Resolver (Go, stdlib only) + unit tests |
| `testbed/config.py` | All emulation parameters (link model, capacity, workloads, sensitivity override) |
| `testbed/testbed.py` | Tier servers + user-space link proxies on localhost TCP |
| `testbed/run.py` | Telemetry collection and paired placement trials |
| `testbed/train.py` | Forecaster training (training seeds 101, 102 only) |
| `testbed/analyze.py` | SLO attainment, seed-cluster bootstrap CIs, exact McNemar, Fig. 1 |
| `testbed/stats_audit.py` | Paired differences with cluster CIs, Holm-adjusted p |
| `testbed/ablation.py` | Offline decision-rule ablation + failure breakdown |
| `testbed/staleness.py`, `lifetime.py`, `lifetime_ci.py` | Decision staleness and deployment-lifetime analysis |
| `testbed/fig_timeline.py` | Fig. 2 |
| `results/raw_logs.tar.gz` | Raw probe + trial logs: `raw/` (training telemetry 101–102, evaluation seeds 1–6) and `raw_sens4/` (sensitivity seeds 11–14, 4× longer episodes). Unpack with `tar xzf results/raw_logs.tar.gz -C results` |
| `results/*.json` | Every reported number |
| `paper/make_numbers.py` | Turns the result files into the LaTeX macros the paper uses |

## Reproduce
```bash
./run_all.sh        # ~70 min on 2 vCPUs
```
Versions used: Go 1.24.7; Python 3.13.16; numpy 2.5.3; scipy 1.18.1; scikit-learn 1.9.1; matplotlib 3.11.2.
Raw logs from the reported runs are included, so the analysis scripts can be re-run without repeating the experiments:
```bash
tar xzf results/raw_logs.tar.gz -C results
cd testbed && python3 analyze.py && python3 stats_audit.py && python3 ablation.py \
  && python3 lifetime_ci.py && python3 lifetime_ci.py ../results/raw_sens4 ../results/lifetime_ci_sens4.json
```
Timing-dependent measurements will differ slightly between machines when the experiments are re-run.

## Scope
This is an emulation on a single host. Link conditions follow seeded two-state Markov congestion
traces with lognormal jitter and loss; compute is emulated with bounded slots and service delays.
No cloud provider, Terraform apply or physical network is involved.

## License
MIT — see `LICENSE`.
