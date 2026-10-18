"""Telemetry window features shared by the trainer and the predictive CPR."""
import numpy as np
from config import WINDOW_S

FEATURES = ["rtt_mean", "rtt_p50", "rtt_p95", "rtt_max", "rtt_std", "rtt_last5",
            "rtt_last", "rtt_slope10", "fail_frac", "util_mean", "util_last", "util_max"]
TIMEOUT_MS = 1000.0  # failed probes enter RTT statistics at the probe timeout


def window_features(rows, now):
    """rows: list of (t, rtt_ms or None, util or None) for one tier, time-ordered."""
    w = [r for r in rows if now - WINDOW_S <= r[0] <= now]
    if len(w) < 5:
        return None
    rtt = np.array([r[1] if r[1] is not None else TIMEOUT_MS for r in w])
    ts = np.array([r[0] for r in w])
    util = np.array([r[2] for r in w if r[2] is not None] or [0.0])
    fail = np.mean([r[1] is None for r in w])
    last10 = ts >= now - 10
    slope = np.polyfit(ts[last10], rtt[last10], 1)[0] if last10.sum() >= 3 else 0.0
    return dict(rtt_mean=rtt.mean(), rtt_p50=np.percentile(rtt, 50), rtt_p95=np.percentile(rtt, 95),
                rtt_max=rtt.max(), rtt_std=rtt.std(), rtt_last5=rtt[-5:].mean(), rtt_last=rtt[-1],
                rtt_slope10=slope, fail_frac=fail, util_mean=util.mean(), util_last=util[-1],
                util_max=util.max())


def reactive_estimate(rows, now):
    f = window_features(rows, now)
    recent = [r for r in rows if r[0] >= now - 2.5]
    up = any(r[1] is not None for r in recent) if recent else False
    if f is None:
        return None
    return dict(p95_rtt_ms=float(f["rtt_p95"]), util=float(f["util_mean"]), up=bool(up))
