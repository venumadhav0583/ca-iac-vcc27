"""Train the predictive-CPR forecaster on training-seed telemetry only.

Target: the p95 probe RTT and mean utilization a tier will show over the next
H seconds (the span over which a placement is exercised). Two models:
  rtt  - GradientBoostingRegressor, quantile loss (alpha=0.9): conservative forecast
  util - GradientBoostingRegressor, squared error
Evaluation seeds are never seen here.
"""
import glob, json, os, pickle, sys
import numpy as np
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.model_selection import GroupKFold
from config import TIERS, WORKLOADS, MEASURE_S
from features import window_features, FEATURES, TIMEOUT_MS

H = len(WORKLOADS) * MEASURE_S  # seconds a placement decision is exercised for
HERE = os.path.dirname(os.path.abspath(__file__))


def load(path):
    rows = {n: [] for n in TIERS}
    for l in open(path):
        r = json.loads(l)
        if r.get("kind") == "probe":
            rows[r["tier"]].append((r["t"], r["rtt_ms"], r["util"]))
    return rows


def dataset(rows, step=1.0):
    X, yr, yu = [], [], []
    for ti, n in enumerate(TIERS):
        rs = rows[n]
        tmax = rs[-1][0]
        t = 30.0
        while t < tmax - H:
            f = window_features(rs, t)
            fut = [r for r in rs if t < r[0] <= t + H]
            if f and len(fut) >= 5:
                X.append([f[c] for c in FEATURES] + [ti])
                rt = [r[1] if r[1] is not None else TIMEOUT_MS for r in fut]
                yr.append(np.percentile(rt, 95))
                yu.append(np.mean([r[2] for r in fut if r[2] is not None] or [0]))
            t += step
    return np.array(X), np.array(yr), np.array(yu)


if __name__ == "__main__":
    files = sorted(glob.glob(os.path.join(HERE, "..", "results", "raw", "telemetry_seed*.jsonl")))
    parts = [dataset(load(f)) for f in files]
    X = np.vstack([p[0] for p in parts]); yr = np.concatenate([p[1] for p in parts])
    yu = np.concatenate([p[2] for p in parts])
    groups = np.concatenate([np.full(len(p[0]), i) for i, p in enumerate(parts)])
    mk_r = lambda: GradientBoostingRegressor(loss="quantile", alpha=0.9, n_estimators=200, max_depth=3,
                                             learning_rate=0.05, random_state=0)
    mk_u = lambda: GradientBoostingRegressor(n_estimators=200, max_depth=3, learning_rate=0.05, random_state=0)
    # Leave-one-seed-out check of forecast quality vs. the reactive window statistic.
    cv = []
    for tr, te in GroupKFold(n_splits=len(parts)).split(X, yr, groups):
        m = mk_r().fit(X[tr], yr[tr])
        p = m.predict(X[te])
        react = X[te][:, FEATURES.index("rtt_p95")]
        cv.append(dict(mae_model=float(np.mean(np.abs(p - yr[te]))),
                       mae_reactive=float(np.mean(np.abs(react - yr[te]))),
                       coverage_model=float(np.mean(yr[te] <= p)),
                       coverage_reactive=float(np.mean(yr[te] <= react))))
    model = dict(rtt=mk_r().fit(X, yr), util=mk_u().fit(X, yu), features=FEATURES, H=H,
                 n_train=int(len(X)), train_files=[os.path.basename(f) for f in files])
    out = os.path.join(HERE, "..", "results")
    pickle.dump(model, open(os.path.join(out, "model.pkl"), "wb"))
    json.dump(dict(n_train=int(len(X)), cv=cv, train_files=model["train_files"]),
              open(os.path.join(out, "train_report.json"), "w"), indent=2)
    print(json.dumps(dict(n_train=int(len(X)), cv=cv), indent=2))
