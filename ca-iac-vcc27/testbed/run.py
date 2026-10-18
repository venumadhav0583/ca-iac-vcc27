"""Run the testbed.

  python run.py telemetry --seed 101 --duration 600 --port 21000
      Collect probe telemetry only (used to train the predictor).
  python run.py eval --seed 1 --instants 30 --port 22000 --model ../results/model.pkl
      Placement trials: at each decision instant every policy places every
      workload; then the real end-to-end latency of each workload on every tier
      is measured, so all policies are scored against the same measurements.

All raw data is written as JSONL under ../results/raw/.
"""
import argparse, asyncio, json, os, pickle, subprocess, time
import numpy as np
from config import *
import testbed as tb
from features import window_features, reactive_estimate, FEATURES

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.environ.get("CAIAC_RAW", os.path.join(HERE, "..", "results", "raw"))
CPR = os.path.join(HERE, "..", "cpr", "cpr")
TF = os.path.join(HERE, "..", "iac", "workloads.tf")
STATIC = {"iot_ingest": "edge", "regional_compliance": "fog", "batch_ml": "cloud"}
ALLOWED = {"any": TIERS, "region": ["edge", "fog"], "local": ["edge"]}


async def prober(env, probes, log):
    async def one(name):
        while True:
            t = time.monotonic() - env["t0"]
            rtt = await tb.request(env["ports"][name]["proxy"], "W 0\n", PROBE_TIMEOUT_S)
            u = None
            raw = await read_metric(env["ports"][name]["server"])
            if raw is not None:
                u = raw
            probes[name].append((t, rtt, u))
            log.write(json.dumps(dict(kind="probe", t=round(t, 3), tier=name, rtt_ms=rtt, util=u)) + "\n")
            await asyncio.sleep(PROBE_INTERVAL_S)
    return [asyncio.create_task(one(n)) for n in TIERS]


async def read_metric(port):
    try:
        r, w = await asyncio.wait_for(asyncio.open_connection("127.0.0.1", port), 0.5)
        w.write(b"M\n"); await w.drain()
        v = await asyncio.wait_for(r.readline(), 0.5); w.close()
        return float(v)
    except Exception:
        return None


def run_cpr(estimates, path):
    with open(path, "w") as f:
        json.dump(estimates, f)
    t = time.perf_counter()
    out = subprocess.run([CPR, "-tf", TF, "-estimates", path], capture_output=True, text=True, check=True)
    return json.loads(out.stdout), (time.perf_counter() - t) * 1000.0


async def measure(env, tier, compute):
    port = env["ports"][tier]["proxy"]
    jobs = []
    for i in range(MEASURE_RPS * MEASURE_S):
        jobs.append(asyncio.create_task(tb.request(port, f"W {compute}\n", REQ_TIMEOUT_S)))
        await asyncio.sleep(1.0 / MEASURE_RPS)
    lat = await asyncio.gather(*jobs)
    return [l if l is not None else REQ_TIMEOUT_S * 1000.0 for l in lat]


async def main_eval(a):
    rng = np.random.default_rng(a.seed + 999)
    T = WARMUP_S + a.instants * (len(WORKLOADS) * MEASURE_S + GAP_S + 1) + 60
    # Two edge outages per run at random times after warmup (for drift + failover).
    outs = []
    for _ in range(2 if T - 80 > WARMUP_S + 21 else 0):
        s = int(rng.integers(WARMUP_S + 20, T - 80))
        outs.append((s, s + OUTAGE_S))
    trace = tb.Trace(a.seed, T, outs)
    model = pickle.load(open(a.model, "rb")) if a.model else None
    env = await tb.start(trace, a.port, a.seed)
    probes = {n: [] for n in TIERS}
    os.makedirs(RAW, exist_ok=True)
    log = open(os.path.join(RAW, f"eval_seed{a.seed}.jsonl"), "w")
    log.write(json.dumps(dict(kind="meta", seed=a.seed, T=T, outages=outs, config=dict(
        LINK=LINK, CAPACITY=CAPACITY, MULT=MULT, EDGE_BG=EDGE_BG, WORKLOADS=WORKLOADS))) + "\n")
    ptasks = await prober(env, probes, log)
    await asyncio.sleep(WARMUP_S)
    tmp = os.path.join(RAW, f".est_{a.seed}.json")
    for k in range(a.instants):
        now = time.monotonic() - env["t0"]
        reactive = {n: reactive_estimate(probes[n], now) for n in TIERS}
        reactive = {n: v for n, v in reactive.items() if v}
        dec_r, ms_r = run_cpr(reactive, tmp)
        dec_p, ms_p, t_pred = None, None, None
        if model:
            tp = time.perf_counter()
            pred = {}
            for n in TIERS:
                f = window_features(probes[n], now)
                if f is None:
                    continue
                x = np.array([[f[c] for c in FEATURES] + [TIERS.index(n)]])
                pred[n] = dict(p95_rtt_ms=float(model["rtt"].predict(x)[0]),
                               util=float(np.clip(model["util"].predict(x)[0], 0, 1)),
                               up=reactive.get(n, {}).get("up", False))
            t_pred = (time.perf_counter() - tp) * 1000.0
            dec_p, ms_p = run_cpr(pred, tmp)
        measured = {}
        for wl, spec in WORKLOADS.items():
            res = await asyncio.gather(*[measure(env, t, spec["compute"]) for t in TIERS])
            measured[wl] = {t: dict(p95=float(np.percentile(r, 95)), p50=float(np.percentile(r, 50)),
                                    n=len(r)) for t, r in zip(TIERS, res)}
        i0 = trace.at(now)
        log.write(json.dumps(dict(
            kind="instant", k=k, t=round(now, 3),
            truth=dict(cong={n: bool(trace.cong[n][i0]) for n in TIERS},
                       edge_bg=float(trace.edge_bg[i0]), edge_outage=bool(trace.outage[i0])),
            reactive_est=reactive, decisions=dict(
                static=STATIC,
                reactive={w: d["tier"] for w, d in dec_r.items()},
                predictive=({w: d["tier"] for w, d in dec_p.items()} if dec_p else None)),
            cpr_ms=dict(reactive=ms_r, predictive=ms_p, predictor_ms=t_pred),
            measured=measured)) + "\n")
        log.flush()
        print(f"seed {a.seed} instant {k+1}/{a.instants} t={now:.0f}s", flush=True)
        await asyncio.sleep(GAP_S)
    for t in ptasks: t.cancel()
    log.close()


async def main_tel(a):
    trace = tb.Trace(a.seed, a.duration + 10)
    env = await tb.start(trace, a.port, a.seed)
    probes = {n: [] for n in TIERS}
    os.makedirs(RAW, exist_ok=True)
    log = open(os.path.join(RAW, f"telemetry_seed{a.seed}.jsonl"), "w")
    ptasks = await prober(env, probes, log)
    await asyncio.sleep(a.duration)
    for t in ptasks: t.cancel()
    log.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["eval", "telemetry"])
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--instants", type=int, default=30)
    ap.add_argument("--duration", type=int, default=600)
    ap.add_argument("--port", type=int, default=21000)
    ap.add_argument("--model", default=None)
    a = ap.parse_args()
    asyncio.run(main_eval(a) if a.mode == "eval" else main_tel(a))
