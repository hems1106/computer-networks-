"""
Run the CSMA/CD experiments for a chosen queue algorithm.

    python run_experiments.py --queue droptail
    python run_experiments.py --queue fq
    python run_experiments.py --queue red
    python run_experiments.py --queue drr
    python run_experiments.py --queue all        (all four + comparison graphs)

Experiment A : 10 stations, offered load G = 0.1 ... 2.0
Experiment B : G = 1.2, number of stations 2 ... 50
Experiment C : (DropTail only) propagation delay vs efficiency
Output       : results_<queue>/   tables (CSV), graphs (PNG), topology diagram
               results_compare/   comparison graphs (only with --queue all)
"""
import argparse
import csv
import os
import statistics as st
import matplotlib
matplotlib.use("Agg")                       # save PNG files, no window needed
import matplotlib.pyplot as plt
from csmacd import simulate, QUEUES, QUEUE_LABEL, DEFAULT_FLOWS
from topology import draw_topology

ap = argparse.ArgumentParser(description="CSMA/CD with DropTail / FQ / RED / DRR")
ap.add_argument("--queue", required=True, choices=QUEUES + ["all"],
                help="queue algorithm to simulate (or 'all' to compare them)")
ap.add_argument("--seeds", type=int, default=5, help="random seeds per point")
ap.add_argument("--time", type=float, default=20.0, help="simulated seconds per run")
args = ap.parse_args()

queues = QUEUES if args.queue == "all" else [args.queue]
SEEDS = list(range(1, args.seeds + 1))
WARMUP = 2.0
LOADS = [0.1, 0.2, 0.4, 0.6, 0.8, 1.0, 1.2, 1.5, 2.0]
STATIONS = [2, 5, 10, 20, 30, 40, 50]
TAUS = [5, 10, 25, 50, 100, 200, 400]
FLOW_NAMES = [f[0] for f in DEFAULT_FLOWS]
COL = {"droptail": "#4c78a8", "fq": "#54a24b", "red": "#e45756", "drr": "#b279a2"}
FCOL = {"heavy": "#e45756", "medium": "#f2a33c", "light": "#4c78a8"}

METRICS = ["throughput_Mbps", "utilization", "avg_delay_ms", "collisions_per_frame",
           "collisions", "loss_pct", "fairness"] + \
          [f"{k}_{n}{u}" for n in FLOW_NAMES
           for k, u in (("delay", "_ms"), ("loss", "_pct"), ("thr", "_Mbps"))]


def run_point(exp, q, N, G, tau_us, flows=None):
    res = [simulate(N, G, q, seed=s, tau=tau_us * 1e-6, sim_time=args.time,
                    warmup=WARMUP, flows=flows) for s in SEEDS]
    row = {"exp": exp, "queue": q, "N": N, "G": G, "tau_us": tau_us}
    for m in METRICS:
        if m in res[0]:
            v = [r[m] for r in res]
            row[m] = round(st.mean(v), 5)
            row[m + "_std"] = round(st.stdev(v), 5) if len(v) > 1 else 0.0
    return row


# ------------------------------------------------------------ run everything
data = {}                                     # (exp, queue) -> list of rows
for q in queues:
    print(f"\n=== Queue algorithm: {QUEUE_LABEL[q]} ===")
    data[("A", q)] = [run_point("A", q, 10, G, 10) for G in LOADS]
    data[("B", q)] = [run_point("B", q, N, 1.2, 10) for N in STATIONS]
    print(f"Experiment A (10 stations, varying load)")
    print(f"  {'load':>5} {'thr(Mbps)':>10} {'delay(ms)':>10} {'coll/frame':>11} "
          f"{'loss(%)':>8} {'fairness':>9}")
    for r in data[("A", q)]:
        print(f"  {r['G']:>5} {r['throughput_Mbps']:>10.3f} {r['avg_delay_ms']:>10.2f} "
              f"{r['collisions_per_frame']:>11.3f} {r['loss_pct']:>8.2f} {r['fairness']:>9.4f}")

if "droptail" in queues:                      # Experiment C: single 1000-byte flow
    data[("C", "droptail")] = [run_point("C", "droptail", 20, 2.0, t,
                                         flows=[("heavy", 1.0, 1000)]) for t in TAUS]

# ------------------------------------------------------------ save CSV tables
def save_csv(path, rows):
    keys = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader(); w.writerows(rows)


# ------------------------------------------------------------ plot helpers
def lineplot(path, series, xlabel, ylabel, title, logy=False, ideal=False, ylim=None):
    plt.figure(figsize=(7.8, 4.7))
    for label, rows, key, color in series:
        x = [r["_x"] for r in rows]
        y = [r[key] for r in rows]
        e = [r.get(key + "_std", 0) for r in rows]
        plt.errorbar(x, y, yerr=e, marker="o", lw=2, capsize=3, label=label, color=color)
    if ideal:
        plt.plot([0, 2], [0, 10], "--", color="gray", label="Ideal (throughput = load)")
    if logy:
        plt.yscale("log")
    if ylim:
        plt.ylim(*ylim)
    plt.xlabel(xlabel); plt.ylabel(ylabel); plt.title(title)
    plt.grid(True, alpha=0.4); plt.legend()
    plt.tight_layout(); plt.savefig(path, dpi=130); plt.close()


def with_x(rows, key):
    return [dict(r, _x=r[key]) for r in rows]


XL_LOAD = "Offered load G (fraction of 10 Mbps)"
XL_N = "Number of stations"

# ------------------------------------------------------------ per-queue graphs
for q in queues:
    out = f"results_{q}"
    os.makedirs(out, exist_ok=True)
    L = QUEUE_LABEL[q]
    A, B = with_x(data[("A", q)], "G"), with_x(data[("B", q)], "N")
    save_csv(f"{out}/summary_{q}.csv", data[("A", q)] + data[("B", q)])
    draw_topology(q, N=10, tau_us=10, fname=f"{out}/topology_{q}.png")

    lineplot(f"{out}/A1_throughput_vs_load.png", [(L, A, "throughput_Mbps", COL[q])],
             XL_LOAD, "Throughput (Mbps)", f"{L}: throughput vs offered load", ideal=True)
    lineplot(f"{out}/A2_delay_vs_load.png",
             [("All frames", A, "avg_delay_ms", "black")] +
             [(f"{n} flow", A, f"delay_{n}_ms", FCOL[n]) for n in FLOW_NAMES],
             XL_LOAD, "Average delay (ms)", f"{L}: average delay vs offered load", logy=True)
    lineplot(f"{out}/A3_collisions_vs_load.png", [(L, A, "collisions_per_frame", COL[q])],
             XL_LOAD, "Collisions per delivered frame", f"{L}: collisions vs offered load")
    lineplot(f"{out}/A4_loss_vs_load.png",
             [("All frames", A, "loss_pct", "black")] +
             [(f"{n} flow", A, f"loss_{n}_pct", FCOL[n]) for n in FLOW_NAMES],
             XL_LOAD, "Frames lost (%)", f"{L}: frame loss vs offered load")
    lineplot(f"{out}/B1_throughput_vs_stations.png", [(L, B, "throughput_Mbps", COL[q])],
             XL_N, "Throughput (Mbps)", f"{L}: throughput vs stations (G = 1.2)", ylim=(0, 10))
    lineplot(f"{out}/B2_delay_vs_stations.png",
             [("All frames", B, "avg_delay_ms", "black")] +
             [(f"{n} flow", B, f"delay_{n}_ms", FCOL[n]) for n in FLOW_NAMES],
             XL_N, "Average delay (ms)", f"{L}: delay vs stations (G = 1.2)")
    lineplot(f"{out}/B3_collisions_vs_stations.png", [(L, B, "collisions_per_frame", COL[q])],
             XL_N, "Collisions per delivered frame", f"{L}: collisions vs stations (G = 1.2)")

    if q == "droptail":
        C = [dict(r, _x=r["tau_us"] / 800.0) for r in data[("C", q)]]
        plt.figure(figsize=(7.8, 4.7))
        plt.errorbar([r["_x"] for r in C], [r["utilization"] for r in C],
                     yerr=[r["utilization_std"] for r in C], marker="o", lw=2, capsize=3,
                     label="Simulated (DropTail, 1000 B frames)")
        xs = [i / 200 for i in range(1, 101)]
        plt.plot(xs, [1 / (1 + 6.44 * a) for a in xs], "--", color="gray",
                 label="Theory 1/(1+6.44a)")
        plt.xlabel("a = propagation delay / frame time"); plt.ylabel("Channel utilization")
        plt.title("Utilization vs a (saturated load, 20 stations)")
        plt.ylim(0, 1); plt.grid(True, alpha=0.4); plt.legend(); plt.tight_layout()
        plt.savefig(f"{out}/C1_efficiency_vs_a.png", dpi=130); plt.close()
        save_csv(f"{out}/summary_expC.csv", data[("C", q)])

# ------------------------------------------------------------ comparison graphs
if args.queue == "all":
    out = "results_compare"
    os.makedirs(out, exist_ok=True)
    save_csv(f"{out}/summary_all_queues.csv",
             [r for q in queues for e in "AB" for r in data[(e, q)]])

    def over(path, exp, xkey, key, xl, yl, title, **kw):
        series = [(QUEUE_LABEL[q], with_x(data[(exp, q)], xkey), key, COL[q]) for q in queues]
        lineplot(path, series, xl, yl, title, **kw)

    over(f"{out}/cmp_A1_throughput.png", "A", "G", "throughput_Mbps", XL_LOAD,
         "Throughput (Mbps)", "Throughput vs offered load", ideal=True)
    over(f"{out}/cmp_A2_delay.png", "A", "G", "avg_delay_ms", XL_LOAD,
         "Average delay (ms)", "Average delay vs offered load", logy=True)
    over(f"{out}/cmp_A3_collisions.png", "A", "G", "collisions_per_frame", XL_LOAD,
         "Collisions per delivered frame", "Collisions vs offered load")
    over(f"{out}/cmp_A4_loss.png", "A", "G", "loss_pct", XL_LOAD,
         "Frames lost (%)", "Frame loss vs offered load")
    over(f"{out}/cmp_A5_light_flow_delay.png", "A", "G", "delay_light_ms", XL_LOAD,
         "Delay of light flow (ms)", "Delay of the light (100 B) flow", logy=True)
    over(f"{out}/cmp_A6_light_flow_loss.png", "A", "G", "loss_light_pct", XL_LOAD,
         "Light-flow frames lost (%)", "Loss of the light (100 B) flow")
    over(f"{out}/cmp_A7_heavy_flow_loss.png", "A", "G", "loss_heavy_pct", XL_LOAD,
         "Heavy-flow frames lost (%)", "Loss of the heavy (1500 B) flow")
    over(f"{out}/cmp_B1_throughput.png", "B", "N", "throughput_Mbps", XL_N,
         "Throughput (Mbps)", "Throughput vs number of stations (G = 1.2)", ylim=(0, 10))
    over(f"{out}/cmp_B2_delay.png", "B", "N", "avg_delay_ms", XL_N,
         "Average delay (ms)", "Average delay vs number of stations (G = 1.2)")
    over(f"{out}/cmp_B3_collisions.png", "B", "N", "collisions_per_frame", XL_N,
         "Collisions per delivered frame", "Collisions vs number of stations (G = 1.2)")

    # bar charts at one operating point: 10 stations, G = 1.2
    pt = {q: [r for r in data[("A", q)] if r["G"] == 1.2][0] for q in queues}
    fig, axs = plt.subplots(2, 3, figsize=(15, 8))
    simple = [("throughput_Mbps", "Throughput (Mbps)"), ("avg_delay_ms", "Average delay (ms)"),
              ("collisions_per_frame", "Collisions per frame")]
    for ax, (k, t) in zip(axs[0], simple):
        vals = [pt[q][k] for q in queues]
        bars = ax.bar([QUEUE_LABEL[q] for q in queues], vals, color=[COL[q] for q in queues])
        ax.bar_label(bars, fmt="%.2f", fontsize=9); ax.set_title(t); ax.grid(axis="y", alpha=0.3)
    ax = axs[1][0]
    bars = ax.bar([QUEUE_LABEL[q] for q in queues], [pt[q]["loss_pct"] for q in queues],
                  color=[COL[q] for q in queues])
    ax.bar_label(bars, fmt="%.1f", fontsize=9); ax.set_title("Total frame loss (%)")
    ax.grid(axis="y", alpha=0.3)
    for ax, (pre, suf, t) in zip(axs[1][1:], [("delay", "_ms", "Average delay per flow (ms)"),
                                              ("loss", "_pct", "Frame loss per flow (%)")]):
        w = 0.2
        for j, q in enumerate(queues):
            ax.bar([i + (j - 1.5) * w for i in range(3)],
                   [pt[q][f"{pre}_{n}{suf}"] for n in FLOW_NAMES], w,
                   label=QUEUE_LABEL[q], color=COL[q])
        ax.set_xticks(range(3)); ax.set_xticklabels([f"{n}\n({b} B)" for n, _, b in DEFAULT_FLOWS])
        ax.set_title(t); ax.grid(axis="y", alpha=0.3); ax.legend(fontsize=8)
    fig.suptitle("Queue algorithm comparison  (10 stations, offered load G = 1.2)",
                 fontsize=14, fontweight="bold")
    fig.tight_layout(); fig.savefig(f"{out}/cmp_bars_G1.2.png", dpi=130); plt.close(fig)

    print("\nComparison at 10 stations, G = 1.2")
    print(f"  {'queue':<9}{'thr':>7}{'delay':>9}{'coll/f':>8}{'loss%':>8}"
          f"{'heavy loss':>12}{'light loss':>12}{'light delay':>13}")
    for q in queues:
        r = pt[q]
        print(f"  {QUEUE_LABEL[q]:<9}{r['throughput_Mbps']:>7.2f}{r['avg_delay_ms']:>9.1f}"
              f"{r['collisions_per_frame']:>8.3f}{r['loss_pct']:>8.1f}"
              f"{r['loss_heavy_pct']:>12.1f}{r['loss_light_pct']:>12.1f}{r['delay_light_ms']:>13.1f}")

print("\nFinished. Graphs, CSV tables and the topology diagram are in:",
      ", ".join(f"results_{q}" for q in queues) + (", results_compare" if args.queue == "all" else ""))
