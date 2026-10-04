"""Draws the network topology (shared bus) and the internals of one station."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle
from csmacd import QUEUE_LABEL, DEFAULT_FLOWS

COLORS = ["#e45756", "#f2a33c", "#4c78a8"]          # heavy, medium, light

DESC = {
    "droptail": ["ONE shared FIFO queue (limit 50 frames)",
                 "Frames sent in arrival order",
                 "Queue full -> the arriving frame is dropped"],
    "red":      ["ONE shared FIFO queue (limit 50 frames)",
                 "Average queue < 5: accept   5-15: drop randomly",
                 "Average queue > 15: drop every arriving frame"],
    "fq":       ["ONE queue PER FLOW",
                 "Send the frame with the smallest virtual finish time",
                 "(bit-by-bit round robin); full -> longest queue loses"],
    "drr":      ["ONE queue PER FLOW",
                 "Round robin, each turn adds a 1500-byte quantum to the",
                 "deficit counter; full -> longest queue loses a frame"],
}


def _box(ax, x, y, w, h, fc, ec="#333", lw=1.5, r=1.2):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={r}",
                                fc=fc, ec=ec, lw=lw))


def _arrow(ax, x1, y1, x2, y2, color="#333"):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="-|>", color=color, lw=1.8))


def draw_topology(queue, N=10, tau_us=10, fname="topology.png"):
    fig, ax = plt.subplots(figsize=(13, 8.6))
    ax.set_xlim(0, 100); ax.set_ylim(0, 100); ax.axis("off")
    q = QUEUE_LABEL[queue]

    ax.text(50, 98, f"CSMA/CD network topology  -  queue algorithm: {q}",
            ha="center", va="top", fontsize=15, fontweight="bold")

    # ---------------- top: shared bus ----------------
    bus_y = 71
    ax.plot([4, 96], [bus_y, bus_y], color="black", lw=7, solid_capstyle="round")
    ax.text(50, bus_y - 4.2,
            f"Shared bus   10 Mbps   propagation delay {tau_us:g} us   (CSMA/CD)",
            ha="center", fontsize=10.5, style="italic")

    shown = [(12, "Station 0"), (28, "Station 1"), (44, "Station 2"),
             (66, f"Station {N - 1}")]
    for x, name in shown:
        ax.plot([x, x], [bus_y, 82], color="#333", lw=2.5)
        _box(ax, x - 7, 82, 14, 10, "#dce9f7")
        ax.text(x, 88.2, name, ha="center", fontsize=10.5, fontweight="bold")
        ax.text(x, 84.6, f"queue: {q}", ha="center", fontsize=9.5, color="#1f4e79")
    ax.text(55, 87, ". . .", ha="center", va="center", fontsize=18)
    ax.text(55, 83.2, f"({N} senders)", ha="center", fontsize=8.5, color="#555")

    ax.plot([86, 86], [bus_y, 60], color="#333", lw=2.5)
    _box(ax, 79, 49, 14, 11, "#d9f0d3")
    ax.text(86, 56, "SINK", ha="center", fontsize=11, fontweight="bold")
    ax.text(86, 52.2, "(receiver)", ha="center", fontsize=9.5)
    ax.text(4, 56, "All stations send to the sink.\nStations that transmit at the same\n"
            "time collide -> jam -> random backoff.", fontsize=9.5, va="center", color="#444")

    # ---------------- bottom: inside one station ----------------
    ax.plot([2, 98], [44, 44], color="#aaa", lw=1, ls="--")
    ax.text(3, 41.5, "Inside every station", fontsize=12.5, fontweight="bold", va="top")

    # flows
    for k, (nm, share, nbytes) in enumerate(DEFAULT_FLOWS):
        y = 26 - k * 10 + 4
        _box(ax, 3, y, 20, 7.5, "white", ec=COLORS[k], lw=2.2)
        ax.text(13, y + 5.0, f"Flow {k + 1}: {nm}", ha="center", fontsize=10, fontweight="bold")
        ax.text(13, y + 1.6, f"{nbytes} B frames, {int(share * 100)}% of load", ha="center", fontsize=8.8)
        _arrow(ax, 23, y + 3.75, 31, 21)

    # queue box
    _box(ax, 31, 3, 36, 36, "#fff8e6", ec="#b8860b", lw=2)
    ax.text(49, 36.3, f"Interface queue: {q}", ha="center", fontsize=12, fontweight="bold")
    # cells
    per_flow = queue in ("fq", "drr")
    rows = 3 if per_flow else 1
    cell_w, cell_h = 2.7, 3.2
    pattern = [0, 1, 0, 2, 0, 1, 2, 0]
    for r in range(rows):
        y = (28 - r * 4.6) if per_flow else 25
        if per_flow:
            ax.text(34.5, y + 1.6, f"flow {r + 1}", fontsize=8, va="center", color=COLORS[r])
        for c in range(8):
            col = COLORS[r] if per_flow else COLORS[pattern[c]]
            ax.add_patch(Rectangle((40 + c * (cell_w + 0.3), y), cell_w, cell_h,
                                   fc=col, ec="white", lw=1))
    if per_flow:
        ax.text(49, 33.2, "per-flow queues", ha="center", fontsize=8.5, color="#555")
    else:
        ax.text(49, 30.2, "single FIFO (all flows mixed together)", ha="center",
                fontsize=8.5, color="#555")
    y0 = 14.0 if per_flow else 17.5
    for i, line in enumerate(DESC[queue]):
        ax.text(49, y0 - i * 3.8, line, ha="center", fontsize=8.8, color="#222")

    _arrow(ax, 67, 21, 73, 21)
    _box(ax, 73, 9, 25, 24, "#fdeaea", ec="#a33", lw=2)
    ax.text(85.5, 29.2, "CSMA/CD MAC", ha="center", fontsize=11.5, fontweight="bold")
    for i, line in enumerate(["1. carrier sense (wait if busy)",
                              "2. transmit, listen for collision",
                              "3. collision -> 32-bit jam",
                              "4. binary exponential backoff",
                              "5. give up after 16 attempts"]):
        ax.text(75, 25.2 - i * 3.5, line, fontsize=8.6, va="center")
    ax.annotate("", xy=(75, bus_y - 0.8), xytext=(75, 33.5),
                arrowprops=dict(arrowstyle="-|>", color="#a33", lw=1.8, ls="--"))
    ax.text(73.6, 52, "frames go onto\nthe shared bus", fontsize=8.8, color="#a33",
            ha="right", va="center")

    fig.tight_layout()
    fig.savefig(fname, dpi=140)
    plt.close(fig)


if __name__ == "__main__":
    import sys
    for qn in (sys.argv[1:] or ["droptail", "fq", "red", "drr"]):
        draw_topology(qn, fname=f"topology_{qn}.png")
        print("saved", f"topology_{qn}.png")
