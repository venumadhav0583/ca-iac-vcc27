"""Testbed configuration. Every parameter that shapes the results lives here.

Network parameters describe an emulated edge-fog-cloud continuum; they are
design inputs of the emulation, not measurements of a production network.
"""

TIERS = ["edge", "fog", "cloud"]

# Per-link emulation (round-trip, milliseconds).
LINK = {
    #        base RTT  lognormal sigma  congestion factor  loss(normal)  loss(congested)  P(enter cong)  P(exit cong)
    "edge":  dict(base=4.0,  sigma=0.25, cong_factor=6.0, loss=0.002, cong_loss=0.03, p_in=0.020, p_out=0.10),
    "fog":   dict(base=16.0, sigma=0.20, cong_factor=3.0, loss=0.002, cong_loss=0.02, p_in=0.010, p_out=0.08),
    "cloud": dict(base=48.0, sigma=0.15, cong_factor=1.5, loss=0.001, cong_loss=0.005, p_in=0.005, p_out=0.10),
}
RTO_MS = 200.0  # retransmission penalty applied to a lost request

# Compute capacity: concurrent slots and slowdown relative to cloud hardware.
CAPACITY = {"edge": 4, "fog": 16, "cloud": 64}
MULT = {"edge": 3.0, "fog": 1.5, "cloud": 1.0}  # must match cpr/main.go

# Background (other-tenant) occupancy of edge slots: AR(1) around a mean, clipped.
EDGE_BG = dict(mean=0.45, phi=0.97, noise=0.06, lo=0.0, hi=1.0)

# Workloads mirror iac/workloads.tf.
WORKLOADS = {
    "iot_ingest":          dict(budget=30.0,  residency="any",    compute=1.0),
    "regional_compliance": dict(budget=40.0,  residency="region", compute=5.0),
    "batch_ml":            dict(budget=120.0, residency="any",    compute=40.0),
}

PROBE_INTERVAL_S = 0.5
PROBE_TIMEOUT_S = 1.0
WINDOW_S = 30          # reactive CPR telemetry window (as in the original design)
MEASURE_RPS = 8
MEASURE_S = 4          # per-workload measurement window after a placement
REQ_TIMEOUT_S = 2.0
GAP_S = 2
WARMUP_S = 35
OUTAGE_S = 20          # injected edge outage duration


# --- Sensitivity override (used only by the episode-length sensitivity run) ---
# CAIAC_EPISODE_SCALE=k makes congestion episodes and background-load swings k times
# longer while keeping the stationary share of congested time and the load variance.
import os as _os, math as _math
_k = float(_os.environ.get("CAIAC_EPISODE_SCALE", "1"))
if _k != 1:
    for _t in LINK:
        LINK[_t]["p_in"] /= _k; LINK[_t]["p_out"] /= _k
    _sd = EDGE_BG["noise"] / _math.sqrt(1 - EDGE_BG["phi"] ** 2)
    EDGE_BG["phi"] = EDGE_BG["phi"] ** (1 / _k)
    EDGE_BG["noise"] = _sd * _math.sqrt(1 - EDGE_BG["phi"] ** 2)
