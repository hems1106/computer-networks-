"""
CSMA/CD shared-bus Ethernet simulator with selectable queue algorithms.

Queue algorithms (the interface queue inside every station):
  droptail : one FIFO queue; the arriving frame is dropped when the queue is full
  red      : one FIFO queue; Random Early Detection drops frames *probabilistically*
             when the average queue length rises between min and max thresholds
  fq       : Fair Queuing - one queue per flow, the frame with the smallest virtual
             finish time is sent next (approximates bit-by-bit round robin);
             when full, the longest flow queue loses a frame
  drr      : Deficit Round Robin - one queue per flow, round robin with a byte
             "deficit counter" and a quantum of 1500 bytes; when full, the
             longest flow queue loses a frame

Traffic: every station sends 3 flows (Poisson arrivals) to the sink:
    heavy  : 1500-byte frames, 60 % of the station's load
    medium :  500-byte frames, 30 %
    light  :  100-byte frames, 10 %
Fair-queuing schedulers only make a difference when several flows share a queue,
which is why each station has more than one flow.

MAC: 1-persistent CSMA/CD with jam, binary exponential backoff (cap 10),
and a 16-attempt limit. All stations are `tau` seconds apart.

Single run:   python csmacd.py --queue red --n 10 --load 1.0
"""
import argparse
import random
from collections import deque

INF = float("inf")

# (name, share of the station's offered load, frame size in bytes)
DEFAULT_FLOWS = [("heavy", 0.6, 1500), ("medium", 0.3, 500), ("light", 0.1, 100)]
QUEUES = ["droptail", "fq", "red", "drr"]
QUEUE_LABEL = {"droptail": "DropTail", "fq": "FQ", "red": "RED", "drr": "DRR"}


# ------------------------------------------------------------------ queues
# A frame is a tuple (arrival_time, flow_id, size_in_bits).
# enqueue() returns (dropped_frame_or_None, dropped_early_flag).

class DropTail:
    def __init__(s, limit, F, rng, ptc):
        s.q, s.limit = deque(), limit

    def __len__(s):
        return len(s.q)

    def enqueue(s, fr, now):
        if len(s.q) >= s.limit:
            return fr, False                       # tail drop
        s.q.append(fr)
        return None, False

    def dequeue(s, now):
        return s.q.popleft()


class RED:
    """Random Early Detection (Floyd & Jacobson)."""

    def __init__(s, limit, F, rng, ptc, min_th=5, max_th=15, max_p=0.1, wq=0.02):
        s.q, s.limit, s.rng, s.ptc = deque(), limit, rng, ptc
        s.min_th, s.max_th, s.max_p, s.wq = min_th, max_th, max_p, wq
        s.avg, s.count, s.idle = 0.0, -1, 0.0

    def __len__(s):
        return len(s.q)

    def enqueue(s, fr, now):
        q = len(s.q)
        if q > 0:
            s.avg = (1 - s.wq) * s.avg + s.wq * q          # moving average of queue
        elif now > s.idle:
            s.avg *= (1 - s.wq) ** ((now - s.idle) / s.ptc)  # decay while idle
        if s.avg >= s.max_th:                              # above max threshold
            s.count = 0
            return fr, True
        if s.avg >= s.min_th:                              # between thresholds
            s.count += 1
            pb = s.max_p * (s.avg - s.min_th) / (s.max_th - s.min_th)
            d = s.count * pb
            pa = 1.0 if d >= 1 else pb / (1 - d)
            if s.rng.random() < pa:                        # early random drop
                s.count = 0
                return fr, True
        else:
            s.count = -1
        if q >= s.limit:
            return fr, False                               # buffer full
        s.q.append(fr)
        return None, False

    def dequeue(s, now):
        fr = s.q.popleft()
        if not s.q:
            s.idle = now
        return fr


class FQ:
    """Fair Queuing using self-clocked virtual finish tags."""

    def __init__(s, limit, F, rng, ptc):
        s.F, s.limit = F, limit
        s.q = [deque() for _ in range(F)]
        s.t = [deque() for _ in range(F)]                  # finish tags
        s.bits, s.last, s.V, s.n = [0] * F, [0.0] * F, 0.0, 0

    def __len__(s):
        return s.n

    def enqueue(s, fr, now):
        f = fr[1]
        tag = (s.last[f] if s.last[f] > s.V else s.V) + fr[2]
        s.q[f].append(fr); s.t[f].append(tag)
        s.last[f] = tag; s.bits[f] += fr[2]; s.n += 1
        if s.n > s.limit:                                  # drop from longest queue
            g = max(range(s.F), key=s.bits.__getitem__)
            d = s.q[g].pop(); s.t[g].pop()
            s.bits[g] -= d[2]; s.n -= 1
            s.last[g] = s.t[g][-1] if s.t[g] else s.V
            return d, False
        return None, False

    def dequeue(s, now):
        best, bt = -1, INF
        for f in range(s.F):
            if s.q[f] and s.t[f][0] < bt:
                bt, best = s.t[f][0], f
        fr = s.q[best].popleft(); s.t[best].popleft()
        s.bits[best] -= fr[2]; s.n -= 1; s.V = bt
        return fr


class DRR:
    """Deficit Round Robin (Shreedhar & Varghese), quantum = 1500 bytes."""

    def __init__(s, limit, F, rng, ptc, quantum=1500 * 8):
        s.F, s.limit, s.quantum = F, limit, quantum
        s.q = [deque() for _ in range(F)]
        s.bits, s.deficit, s.granted = [0] * F, [0] * F, [False] * F
        s.active, s.n = deque(), 0

    def __len__(s):
        return s.n

    def enqueue(s, fr, now):
        f = fr[1]
        if not s.q[f]:                                     # flow becomes active
            s.active.append(f); s.deficit[f] = 0; s.granted[f] = False
        s.q[f].append(fr); s.bits[f] += fr[2]; s.n += 1
        if s.n > s.limit:                                  # drop from longest queue
            g = max(range(s.F), key=s.bits.__getitem__)
            d = s.q[g].pop(); s.bits[g] -= d[2]; s.n -= 1
            if not s.q[g]:
                s.active.remove(g); s.deficit[g] = 0; s.granted[g] = False
            return d, False
        return None, False

    def dequeue(s, now):
        while True:
            f = s.active[0]
            if not s.granted[f]:                           # start of this flow's turn
                s.deficit[f] += s.quantum; s.granted[f] = True
            fr = s.q[f][0]
            if fr[2] <= s.deficit[f]:                      # enough credit: send it
                s.q[f].popleft()
                s.deficit[f] -= fr[2]; s.bits[f] -= fr[2]; s.n -= 1
                if not s.q[f]:
                    s.active.popleft(); s.deficit[f] = 0; s.granted[f] = False
                return fr
            s.granted[f] = False                           # not enough: next flow
            s.active.rotate(-1)


SCHEDULERS = {"droptail": DropTail, "red": RED, "fq": FQ, "drr": DRR}


# --------------------------------------------------------------- simulator
def simulate(N, G, queue="droptail", seed=1, tau=10e-6, rate_bps=10e6,
             sim_time=10.0, warmup=1.0, qlimit=50, flows=None, slot=None,
             ifs=9.6e-6, jam_bits=32, max_attempts=16, backoff_cap=10, trace=None):
    """Simulate CSMA/CD with the chosen queue algorithm; return a metrics dict.

    N      number of sending stations (plus one sink)
    G      total offered load as a fraction of channel capacity
    queue  'droptail' | 'fq' | 'red' | 'drr'
    tau    one-way propagation delay between stations (seconds)
    trace  (t_start, t_end): also record every packet event in that time window
           (transmissions, collisions, drops, queue sizes) for the animation
    """
    flows = flows or DEFAULT_FLOWS
    F = len(flows)
    names = [f[0] for f in flows]
    rng = random.Random(seed)
    J = jam_bits / rate_bps
    if slot is None:
        slot = max(512 / rate_bps, 2 * tau)
    ptc = 1000 * 8 / rate_bps                      # typical frame time (for RED)
    Sched = SCHEDULERS[queue]

    # Poisson arrivals for every (station, flow)
    arr = []
    offered = [0] * F
    for _ in range(N):
        lst = []
        for f, (_, share, nbytes) in enumerate(flows):
            bits = nbytes * 8
            lam = share * G * rate_bps / (N * bits)
            t = 0.0
            while True:
                t += rng.expovariate(lam)
                if t > sim_time:
                    break
                lst.append((t, f, bits))
                if t >= warmup:
                    offered[f] += 1
        lst.sort()
        arr.append(lst)

    sched = [Sched(qlimit, F, rng, ptc) for _ in range(N)]
    cur = [None] * N                  # frame currently held by the MAC
    ptr = [0] * N
    attempts = [0] * N
    sf = [0.0] * N
    chan_free = 0.0

    del_station = [0] * N
    del_cnt, del_bits, del_delay = [0] * F, [0] * F, [0.0] * F
    drop_cnt = [0] * F
    collisions = q_drops = red_drops = x_drops = 0
    tr = [] if trace else None                    # event log (animation)
    qc = [[0] * F for _ in range(N)] if trace else None   # frames queued per flow

    def ingest(i, upto):
        nonlocal q_drops, red_drops
        lst, p, sc = arr[i], ptr[i], sched[i]
        while p < len(lst) and lst[p][0] <= upto:
            fr = lst[p]
            d, early = sc.enqueue(fr, fr[0])
            if tr is not None:
                if d is not fr:
                    qc[i][fr[1]] += 1
                    if d is not None:
                        qc[i][d[1]] -= 1
                if d is not None:
                    tr.append(("drop", fr[0], i, d[1], "red" if early else "queue"))
                tr.append(("q", fr[0], i, list(qc[i])))
            if d is not None and d[0] >= warmup:
                drop_cnt[d[1]] += 1
                if early:
                    red_drops += 1
                else:
                    q_drops += 1
            p += 1
        ptr[i] = p

    def take(i, now):                               # scheduler picks the next frame
        fr = sched[i].dequeue(now)
        if tr is not None:
            qc[i][fr[1]] -= 1
            tr.append(("q", now, i, list(qc[i])))
        return fr

    while True:
        for i in range(N):
            ingest(i, chan_free)
            if cur[i] is None and len(sched[i]) > 0:
                cur[i] = take(i, chan_free)

        a = [INF] * N
        for i in range(N):
            if cur[i] is not None:
                head = cur[i][0]
            elif ptr[i] < len(arr[i]):
                head = arr[i][ptr[i]][0]
            else:
                continue
            ready = head if head > sf[i] else sf[i]
            a[i] = chan_free + ifs if ready < chan_free else ready
        t1 = min(a)
        if t1 > sim_time:
            break

        C = [i for i in range(N) if a[i] < t1 + tau]
        for i in C:
            if cur[i] is None:
                ingest(i, a[i])
                if len(sched[i]) > 0:                         # (RED may drop it on arrival)
                    cur[i] = take(i, a[i])
        C = [i for i in C if cur[i] is not None]
        if not C:
            continue

        if len(C) == 1:                                       # ---- success ----
            i = C[0]
            fr = cur[i]
            deliver = t1 + fr[2] / rate_bps + tau
            if tr is not None:
                tr.append(("tx", t1, i, fr[1], fr[2], deliver))
            if warmup <= deliver <= sim_time:
                f = fr[1]
                del_station[i] += 1
                del_cnt[f] += 1
                del_bits[f] += fr[2]
                del_delay[f] += deliver - fr[0]
            cur[i] = None
            attempts[i] = 0
            sf[i] = deliver
            chan_free = deliver
        else:                                                 # ---- collision ----
            starts = sorted(a[i] for i in C)
            s0, s1 = starts[0], starts[1]
            end, stop = 0.0, {}
            for i in C:
                other = s1 if a[i] == s0 else s0
                stop[i] = other + tau + J
                end = max(end, stop[i])
            chan_free = end + tau
            if tr is not None:
                tr.append(("col", t1, [(i, a[i], stop[i]) for i in C], end))
            if t1 >= warmup:
                collisions += 1
            for i in C:
                attempts[i] += 1
                if attempts[i] > max_attempts:                # give up on this frame
                    fr = cur[i]
                    cur[i] = None
                    if tr is not None:
                        tr.append(("drop", stop[i], i, fr[1], "excess"))
                    if fr[0] >= warmup:
                        x_drops += 1
                        drop_cnt[fr[1]] += 1
                    attempts[i] = 0
                    sf[i] = stop[i]
                else:
                    n = min(attempts[i], backoff_cap)
                    sf[i] = stop[i] + rng.randrange(2 ** n) * slot

    window = sim_time - warmup
    total = sum(del_cnt)
    tbits = sum(del_bits)
    s1_ = float(sum(del_station))
    s2_ = float(sum(d * d for d in del_station))
    off_total = sum(offered)
    res = {
        "throughput_Mbps": tbits / window / 1e6,
        "utilization": tbits / window / rate_bps,
        "avg_delay_ms": sum(del_delay) / total * 1000 if total else 0.0,
        "collisions_per_frame": collisions / total if total else 0.0,
        "collisions": collisions,
        "loss_pct": 100.0 * sum(drop_cnt) / off_total if off_total else 0.0,
        "queue_drops": q_drops,
        "red_early_drops": red_drops,
        "excess_collision_drops": x_drops,
        "fairness": s1_ * s1_ / (N * s2_) if s2_ > 0 else 0.0,
        "delivered": total,
    }
    for f, nm in enumerate(names):
        res[f"delay_{nm}_ms"] = del_delay[f] / del_cnt[f] * 1000 if del_cnt[f] else 0.0
        res[f"loss_{nm}_pct"] = 100.0 * drop_cnt[f] / offered[f] if offered[f] else 0.0
        res[f"thr_{nm}_Mbps"] = del_bits[f] / window / 1e6
    if trace:
        w0, w1 = trace
        ev, last = [], {}
        for e in tr:
            if e[0] == "q":
                if e[1] < w0:
                    last[e[2]] = e                   # latest queue state before window
                elif e[1] <= w1:
                    ev.append(e)
            elif w0 <= e[1] <= w1:
                ev.append(e)
        for i, e in last.items():
            ev.append(("q", w0, i, e[3]))
        ev.sort(key=lambda e: e[1])
        res["trace"] = {"N": N, "queue": queue, "G": G, "tau": tau, "rate": rate_bps,
                        "qlimit": qlimit, "t0": w0, "t1": w1,
                        "flows": [(f[0], f[2]) for f in flows], "events": ev}
    return res


def print_report(r, queue, N, G, tau_us, flows=None):
    flows = flows or DEFAULT_FLOWS
    print(f"\nQueue algorithm: {QUEUE_LABEL[queue]}   stations={N}   "
          f"offered load G={G}   propagation delay={tau_us} us")
    print("-" * 66)
    print(f"  Throughput            : {r['throughput_Mbps']:.3f} Mbps "
          f"(utilization {r['utilization']:.3f})")
    print(f"  Average delay         : {r['avg_delay_ms']:.3f} ms")
    print(f"  Collisions per frame  : {r['collisions_per_frame']:.3f}   "
          f"(total collisions {r['collisions']})")
    print(f"  Frames lost           : {r['loss_pct']:.2f} %   "
          f"[queue-full {r['queue_drops']}, RED early {r['red_early_drops']}, "
          f"16-collision {r['excess_collision_drops']}]")
    print(f"  Station fairness      : {r['fairness']:.4f}  (Jain's index)")
    print("  Per flow:")
    for nm, _, nbytes in flows:
        print(f"    {nm:<7}({nbytes:>4} B)  throughput {r[f'thr_{nm}_Mbps']:.3f} Mbps   "
              f"delay {r[f'delay_{nm}_ms']:9.3f} ms   loss {r[f'loss_{nm}_pct']:6.2f} %")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="CSMA/CD simulator with queue algorithms")
    p.add_argument("--queue", choices=QUEUES, required=True,
                   help="queue algorithm: droptail, fq, red or drr")
    p.add_argument("--n", type=int, default=10, help="number of stations")
    p.add_argument("--load", type=float, default=1.0, help="offered load G (0.1-2.0)")
    p.add_argument("--tau_us", type=float, default=10, help="propagation delay (us)")
    p.add_argument("--time", type=float, default=10.0, help="simulated seconds")
    p.add_argument("--seed", type=int, default=1)
    a = p.parse_args()
    res = simulate(a.n, a.load, a.queue, a.seed, tau=a.tau_us * 1e-6, sim_time=a.time)
    print_report(res, a.queue, a.n, a.load, a.tau_us)
