"""Emulated edge-fog-cloud continuum on localhost TCP.

Each tier is a real asyncio TCP server with a bounded number of compute slots.
Each tier is reached through a user-space link proxy that delays every request
by a round-trip time drawn from a seeded, per-second link-condition trace
(two-state Markov congestion, lognormal jitter, loss -> retransmission penalty).
Edge slots are additionally occupied by background tenants (AR(1) process).
"""
import asyncio, math, random, time
import numpy as np
from config import *


class Trace:
    """Seeded per-second link and load conditions for duration T seconds."""

    def __init__(self, seed, T, outages=()):
        rng = np.random.default_rng(seed)
        self.T = T
        self.cong = {}
        for t in TIERS:
            p = LINK[t]
            s = np.zeros(T, dtype=bool)
            for i in range(1, T):
                s[i] = (rng.random() >= p["p_out"]) if s[i - 1] else (rng.random() < p["p_in"])
            self.cong[t] = s
        bg = np.zeros(T)
        u = EDGE_BG["mean"]
        for i in range(T):
            u = EDGE_BG["mean"] + EDGE_BG["phi"] * (u - EDGE_BG["mean"]) + rng.normal(0, EDGE_BG["noise"])
            u = min(max(u, EDGE_BG["lo"]), EDGE_BG["hi"])
            bg[i] = u
        self.edge_bg = bg
        self.outage = np.zeros(T, dtype=bool)
        for (a, b) in outages:
            self.outage[a:b] = True

    def at(self, sec):
        return min(max(int(sec), 0), self.T - 1)


class Tier:
    def __init__(self, name):
        self.name = name
        self.cap = CAPACITY[name]
        self.sem = asyncio.Semaphore(self.cap)
        self.active = 0
        self.bg_held = 0

    async def handle(self, reader, writer):
        try:
            line = (await reader.readline()).decode().strip()
            if line == "M":
                util = (self.active + self.bg_held) / self.cap
                writer.write(f"{util:.4f}\n".encode())
            elif line.startswith("W"):
                ms = float(line.split()[1]) * MULT[self.name]
                async with self.sem:
                    self.active += 1
                    try:
                        await asyncio.sleep(ms / 1000.0)
                    finally:
                        self.active -= 1
                writer.write(b"OK\n")
            await writer.drain()
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            writer.close()

    async def background(self, trace, t0):
        """Hold edge slots for other tenants according to the trace."""
        held = []
        while True:
            want = round(trace.edge_bg[trace.at(time.monotonic() - t0)] * self.cap) if self.name == "edge" else 0
            want = min(want, self.cap)
            while len(held) < want:
                await self.sem.acquire(); held.append(1); self.bg_held += 1
            while len(held) > want:
                held.pop(); self.sem.release(); self.bg_held -= 1
            await asyncio.sleep(0.25)


class LinkProxy:
    def __init__(self, tier, server_port, trace, t0, rng):
        self.tier, self.server_port, self.trace, self.t0, self.rng = tier, server_port, trace, t0, rng

    def sample_rtt_ms(self):
        i = self.trace.at(time.monotonic() - self.t0)
        p = LINK[self.tier]
        cong = self.trace.cong[self.tier][i]
        rtt = p["base"] * (p["cong_factor"] if cong else 1.0) * math.exp(self.rng.gauss(0, p["sigma"]))
        loss = p["cong_loss"] if cong else p["loss"]
        if self.rng.random() < loss:
            rtt += RTO_MS
        return rtt, (self.tier == "edge" and self.trace.outage[i])

    async def handle(self, reader, writer):
        try:
            line = await reader.readline()
            rtt, down = self.sample_rtt_ms()
            if down:  # black-hole: never answer during an outage
                await asyncio.sleep(REQ_TIMEOUT_S + 1)
                return
            await asyncio.sleep(rtt / 2000.0)  # forward half
            r, w = await asyncio.open_connection("127.0.0.1", self.server_port)
            w.write(line); await w.drain()
            resp = await r.readline()
            w.close()
            await asyncio.sleep(rtt / 2000.0)  # return half
            writer.write(resp); await writer.drain()
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            writer.close()


async def request(port, payload, timeout):
    """Send one request; return latency in ms or None on timeout/failure."""
    t = time.perf_counter()
    try:
        r, w = await asyncio.wait_for(asyncio.open_connection("127.0.0.1", port), timeout)
        w.write(payload.encode()); await w.drain()
        resp = await asyncio.wait_for(r.readline(), timeout)
        w.close()
        if not resp:
            return None
        return (time.perf_counter() - t) * 1000.0
    except (asyncio.TimeoutError, ConnectionError, OSError):
        return None


async def start(trace, base_port, seed):
    """Start tier servers + link proxies. Returns dict with ports and t0."""
    t0 = time.monotonic()
    rng = random.Random(seed * 7919)
    ports, servers, tasks = {}, [], []
    for k, name in enumerate(TIERS):
        tier = Tier(name)
        sp, pp = base_port + 2 * k, base_port + 2 * k + 1
        servers.append(await asyncio.start_server(tier.handle, "127.0.0.1", sp, backlog=512))
        proxy = LinkProxy(name, sp, trace, t0, random.Random(rng.random()))
        servers.append(await asyncio.start_server(proxy.handle, "127.0.0.1", pp, backlog=512))
        tasks.append(asyncio.create_task(tier.background(trace, t0)))
        ports[name] = dict(server=sp, proxy=pp)
    return dict(t0=t0, ports=ports, servers=servers, tasks=tasks)
