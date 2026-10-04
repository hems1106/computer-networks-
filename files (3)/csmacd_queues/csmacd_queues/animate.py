"""
NAM-style packet animation for the CSMA/CD simulation.

Creates ONE self-contained HTML file (open it in Chrome / Edge / Firefox).
Press PLAY to watch packets travel from the stations to the sink:
    blue   = packet being delivered          orange = collision (frames collide)
    red    = dropped packet                  bars   = frames waiting in each queue
Everything shown comes from the real simulation (every transmission, collision
and drop is an event recorded by csmacd.py), not from a made-up animation.

    python animate.py --queue red                 one algorithm
    python animate.py --queue all                 all four, choose in the page
    python animate.py --queue fq --topology star  start with the star layout
"""
import argparse
import json
import os
import webbrowser
from csmacd import simulate, QUEUES, QUEUE_LABEL

HTML = r"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>CSMA/CD packet animation</title>
<style>
 body{font-family:Segoe UI,Arial,sans-serif;margin:0;background:#f4f6f9;color:#222}
 #wrap{max-width:1120px;margin:0 auto;padding:10px}
 h1{font-size:19px;margin:6px 0}
 #ctl{display:flex;flex-wrap:wrap;gap:10px;align-items:center;background:#fff;padding:8px 10px;
      border:1px solid #d5dbe3;border-radius:8px}
 button{font-size:15px;padding:6px 14px;border:1px solid #888;border-radius:6px;background:#fafafa;cursor:pointer}
 button#play{background:#1f6feb;color:#fff;border-color:#1f6feb;min-width:96px}
 select,input{font-size:14px}
 label{font-size:13px;color:#444}
 canvas{width:100%;background:#fff;border:1px solid #d5dbe3;border-radius:8px;margin-top:8px}
 #hud{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px;margin-top:8px}
 .card{background:#fff;border:1px solid #d5dbe3;border-radius:8px;padding:6px 10px}
 .card b{display:block;font-size:20px}
 .card span{font-size:12px;color:#555}
 #legend{margin-top:8px;font-size:13px;background:#fff;border:1px solid #d5dbe3;border-radius:8px;padding:6px 10px}
 .dot{display:inline-block;width:12px;height:12px;border-radius:50%;margin:0 4px 0 12px;vertical-align:middle}
 .sq{display:inline-block;width:12px;height:12px;margin:0 4px 0 12px;vertical-align:middle}
</style></head><body><div id="wrap">
<h1 id="title">CSMA/CD packet animation</h1>
<div id="ctl">
 <button id="play">&#9654; Play</button><button id="restart">&#8634; Restart</button>
 <label>Queue algorithm <select id="qsel"></select></label>
 <label>Topology <select id="tsel"><option value="bus">Bus</option><option value="star">Star (hub)</option></select></label>
 <label>Speed <input id="spd" type="range" min="0" max="100" value="40" style="width:140px"></label>
 <span id="spdlabel" style="font-size:12px;color:#555"></span>
 <label>Time <input id="scrub" type="range" min="0" max="1000" value="0" style="width:200px"></label>
</div>
<canvas id="cv" width="1100" height="600"></canvas>
<div id="hud"></div>
<div id="legend">
 <span class="dot" style="background:#1f6feb"></span>packet delivered (size = frame size)
 <span class="dot" style="background:#f28c18"></span>collision
 <span class="dot" style="background:#e5322d"></span>dropped packet
 <span class="sq" style="background:#264653"></span>queued heavy (1500 B)
 <span class="sq" style="background:#2a9d8f"></span>queued medium (500 B)
 <span class="sq" style="background:#a8dadc"></span>queued light (100 B)
</div></div>
<script>
const DATA = __DATA__;
const NAMES = __NAMES__;
const cv = document.getElementById('cv'), ctx = cv.getContext('2d');
const W = cv.width, H = cv.height;
const FLOWCOL = ['#264653', '#2a9d8f', '#a8dadc'];
const REASON = {queue: 'queue full', red: 'RED drop', excess: '16 collisions'};
let qname = Object.keys(DATA)[0], topo = '__TOPO__';
let D, N, tx, col, drops, qev, LEN, pos, paths, legs, sink, hub, busY, tapX;
let T = 0, playing = false, secPerMs = 0.5, lastTs = null;

function prep() {
  D = DATA[qname]; N = D.N; tx = []; col = []; drops = []; qev = [];
  for (let i = 0; i < N; i++) qev.push([]);
  for (const e of D.events) {
    const t = e[1] - D.t0;
    if (e[0] === 'tx') tx.push({s: t, src: e[2], flow: e[3], bits: e[4], d: e[5] - D.t0});
    else if (e[0] === 'col') col.push({t: t, end: e[3] - D.t0,
        st: e[2].map(a => ({i: a[0], a: a[1] - D.t0, stop: a[2] - D.t0}))});
    else if (e[0] === 'drop') drops.push({t: t, i: e[2], flow: e[3], reason: e[4]});
    else if (e[0] === 'q') qev[e[2]].push({t: t, c: e[3]});
  }
  LEN = D.t1 - D.t0;
  document.getElementById('title').textContent =
    'CSMA/CD packet animation  -  queue: ' + NAMES[qname] + '  -  ' + N + ' stations  -  offered load G = ' + D.G;
  layout();
}

function mkPath(pts) {
  const L = [0];
  for (let k = 1; k < pts.length; k++)
    L.push(L[k-1] + Math.hypot(pts[k][0]-pts[k-1][0], pts[k][1]-pts[k-1][1]));
  return {pts: pts, L: L, tot: L[L.length-1]};
}
function at(p, u) {
  const d = Math.max(0, Math.min(1, u)) * p.tot; let k = 1;
  while (k < p.L.length-1 && p.L[k] < d) k++;
  const seg = (p.L[k] - p.L[k-1]) || 1, f = (d - p.L[k-1]) / seg;
  return [p.pts[k-1][0] + (p.pts[k][0]-p.pts[k-1][0])*f, p.pts[k-1][1] + (p.pts[k][1]-p.pts[k-1][1])*f];
}

function layout() {
  pos = []; paths = []; legs = [];
  if (topo === 'bus') {
    busY = 385; const x0 = 50, x1 = W - 50, sy = 200; tapX = x1 - 80;
    const span = (tapX - 70) - (x0 + 50);
    for (let i = 0; i < N; i++) {
      const x = x0 + 50 + (N > 1 ? i * span / (N - 1) : 0);
      pos.push({x: x, y: sy});
      paths.push(mkPath([[x, sy+20], [x, busY], [tapX, busY], [tapX, busY+90]]));
      legs.push(mkPath([[x, sy+20], [x, busY]]));
    }
    sink = {x: tapX, y: busY + 112};
  } else {
    const cx = W/2, cy = 330, rx = 410, ry = 200; hub = {x: cx, y: cy};
    for (let i = 0; i < N; i++) {
      const th = Math.PI + (i + 0.5) / N * Math.PI;
      const x = cx + rx*Math.cos(th), y = cy + ry*Math.sin(th);
      const dx = cx - x, dy = cy - y, dl = Math.hypot(dx, dy);
      const sx = x + dx/dl*24, sy = y + dy/dl*24;
      pos.push({x: x, y: y});
      paths.push(mkPath([[sx, sy], [cx, cy], [cx, cy+170]]));
      legs.push(mkPath([[sx, sy], [cx, cy]]));
    }
    sink = {x: cx, y: cy + 195};
  }
}

function qvec(i) {
  const a = qev[i]; let lo = 0, hi = a.length - 1, r = null;
  while (lo <= hi) { const m = (lo + hi) >> 1; if (a[m].t <= T) { r = a[m].c; lo = m + 1; } else hi = m - 1; }
  return r || [0, 0, 0];
}
function circle(x, y, r, fill, stroke, alpha) {
  ctx.globalAlpha = alpha === undefined ? 1 : alpha;
  ctx.beginPath(); ctx.arc(x, y, r, 0, 6.2832); ctx.fillStyle = fill; ctx.fill();
  if (stroke) { ctx.strokeStyle = stroke; ctx.lineWidth = 1.5; ctx.stroke(); }
  ctx.globalAlpha = 1;
}
function line(p, color, w) {
  ctx.beginPath(); ctx.moveTo(p.pts[0][0], p.pts[0][1]);
  for (let k = 1; k < p.pts.length; k++) ctx.lineTo(p.pts[k][0], p.pts[k][1]);
  ctx.strokeStyle = color; ctx.lineWidth = w; ctx.lineCap = 'round'; ctx.lineJoin = 'round'; ctx.stroke();
}
function text(s, x, y, size, color, align, bold) {
  ctx.font = (bold ? 'bold ' : '') + size + 'px Segoe UI, Arial'; ctx.fillStyle = color;
  ctx.textAlign = align || 'center'; ctx.fillText(s, x, y);
}

function draw() {
  const sp = 0.001 / secPerMs;                       // simulated seconds per real second
  ctx.clearRect(0, 0, W, H);
  let busyTx = null, colNow = null;
  for (const e of tx) if (T >= e.s && T <= Math.max(e.d, e.s + 0.15*sp)) busyTx = e;
  for (const c of col) if (T >= c.t && T <= Math.max(c.end, c.t + 0.9*sp)) colNow = c;
  const colSt = {};
  if (colNow) for (const s of colNow.st) colSt[s.i] = true;

  // ---- medium: base lines
  if (topo === 'bus') {
    line(mkPath([[50, busY], [W-50, busY]]), '#c9ced6', 9);
    for (let i = 0; i < N; i++) line(legs[i], '#c9ced6', 4);
    line(mkPath([[tapX, busY], [tapX, busY+90]]), '#c9ced6', 4);
    text('Shared bus  -  ' + (D.rate/1e6) + ' Mbps  -  propagation delay ' + (D.tau*1e6) + ' us  (CSMA/CD)', 60, busY + 38, 13, '#555', 'left');
  } else {
    for (let i = 0; i < N; i++) line(legs[i], '#c9ced6', 4);
    line(mkPath([[hub.x, hub.y], [hub.x, hub.y+170]]), '#c9ced6', 4);
    text((D.rate/1e6) + ' Mbps, propagation delay ' + (D.tau*1e6) + ' us (hub = shared medium, CSMA/CD)', 20, H - 14, 13, '#555', 'left');
  }
  // ---- medium: highlight
  if (colNow) {
    for (const s of colNow.st) line(legs[s.i], '#f28c18', 6);
    if (topo === 'bus') {
      const xs = colNow.st.map(s => pos[s.i].x);
      line(mkPath([[Math.min(...xs), busY], [Math.max(...xs), busY]]), '#f28c18', 10);
    }
  } else if (busyTx) {
    line(paths[busyTx.src], '#7db4ff', 7);
  }

  if (topo === 'star') {
    circle(hub.x, hub.y, 24, colNow ? '#ffd8a8' : '#d9dee6', '#999');
    text('HUB', hub.x, hub.y + 5, 13, '#444', 'center', true);
  }
  // ---- sink
  ctx.fillStyle = '#d9f0d3'; ctx.strokeStyle = '#4a8a3d'; ctx.lineWidth = 2;
  ctx.beginPath(); ctx.rect(sink.x - 42, sink.y - 22, 84, 44); ctx.fill(); ctx.stroke();
  text('SINK', sink.x, sink.y - 3, 14, '#222', 'center', true);

  // ---- stations, queue gauges
  let delivered = 0, bits = 0, waiting = 0; const perSrc = new Array(N).fill(0);
  const win = Math.min(0.01, Math.max(T, 0.002));
  for (const e of tx) if (e.d <= T) { delivered++; perSrc[e.src]++; if (e.d > T - win) bits += e.bits; }
  for (let i = 0; i < N; i++) {
    const p = pos[i], q = qvec(i), tot = q[0] + q[1] + q[2]; waiting += tot;
    const transmitting = busyTx && busyTx.src === i;
    ctx.fillStyle = '#eef3fa';
    ctx.strokeStyle = colSt[i] ? '#f28c18' : (transmitting ? '#1f6feb' : '#6b7a90');
    ctx.lineWidth = (colSt[i] || transmitting) ? 4 : 2;
    ctx.beginPath(); ctx.rect(p.x - 26, p.y - 18, 52, 36); ctx.fill(); ctx.stroke();
    text('S' + i, p.x, p.y + 5, 15, '#222', 'center', true);
    text('sent ' + perSrc[i], p.x, p.y + 34, 12, '#444');
    // queue gauge (stacked: heavy at bottom)
    const gx = p.x - 11, gb = p.y - 24, gh = 58;
    ctx.strokeStyle = '#8895a7'; ctx.lineWidth = 1; ctx.strokeRect(gx, gb - gh, 22, gh);
    let yy = gb;
    for (let f = 0; f < 3; f++) {
      const h = Math.min(q[f], D.qlimit) / D.qlimit * gh;
      ctx.fillStyle = FLOWCOL[f]; ctx.fillRect(gx + 1, yy - h, 20, h); yy -= h;
    }
    text(String(tot), p.x, gb - gh - 4, 11, '#333');
  }

  // ---- packets in flight (blue)
  let inflight = 0;
  for (const e of tx) {
    const life = Math.max(e.d - e.s, 0.5 * sp);
    if (T >= e.s && T <= e.s + life) {
      inflight++;
      const u = (T - e.s) / life, p = at(paths[e.src], u), r = 4 + 5 * e.bits / 12000;
      circle(p[0], p[1], r, '#1f6feb', '#ffffff');
      text(D.flows[e.flow][1] + 'B', p[0] + r + 3, p[1] + 4, 10, '#1f4fa8', 'left');
    }
  }
  // ---- collisions (orange)
  let burst = null;
  for (const c of col) {
    for (const s of c.st) {
      const l2 = 0.5 * sp;
      if (T >= s.a && T <= s.a + l2) {
        const p = at(legs[s.i], (T - s.a) / l2); circle(p[0], p[1], 6, '#f28c18', '#ffffff');
      }
    }
    const bs = c.t + 0.4 * sp, bl = Math.max(c.end - c.t, 0.7 * sp);
    if (T >= bs && T <= bs + bl && (!burst || bs > burst.bs)) burst = {c: c, bs: bs, bl: bl};
  }
  if (burst) {                                         // draw only the newest burst
    const f = (T - burst.bs) / burst.bl;
    let bx, by;
    if (topo === 'bus') { const xs = burst.c.st.map(s => pos[s.i].x); bx = (Math.min(...xs) + Math.max(...xs)) / 2; by = busY; }
    else { bx = hub.x; by = hub.y; }
    circle(bx, by, 14 + 26 * f, '#f28c18', null, 0.75 * (1 - f) + 0.2);
    circle(bx, by, 9, '#d9480f', '#fff');
    text('COLLISION', bx, by - 34 - 10 * f, 13, '#d9480f', 'center', true);
  }
  // ---- dropped packets (red)
  const counts = {queue: 0, red: 0, excess: 0};
  for (const d of drops) {
    if (d.t <= T) counts[d.reason]++;
    const life = 0.9 * sp;
    if (T >= d.t && T <= d.t + life) {
      const u = (T - d.t) / life, p = pos[d.i], x = p.x + 44 + 6 * Math.sin(u * 6), y = p.y - 4 - 34 * u;
      circle(x, y, 7, '#e5322d', '#ffffff', 1 - 0.8 * u);
      ctx.globalAlpha = 1 - 0.8 * u; text('X', x, y + 4, 11, '#ffffff', 'center', true);
      text(REASON[d.reason], x, y - 11, 10, '#b3201c', 'center', true); ctx.globalAlpha = 1;
    }
  }
  text('received ' + delivered, sink.x, sink.y + 14, 12, '#333');

  // ---- HUD
  const ncol = col.filter(c => c.t <= T).length, ndrop = counts.queue + counts.red + counts.excess;
  const card = (v, l) => '<div class="card"><b>' + v + '</b><span>' + l + '</span></div>';
  document.getElementById('hud').innerHTML =
    card((T * 1000).toFixed(1) + ' ms', 'network time (window ' + (LEN * 1000).toFixed(0) + ' ms)') +
    card(delivered, 'packets delivered to sink') + card(inflight, 'packets travelling now') +
    card(ncol, 'collisions') +
    card(ndrop, 'packets dropped (queue-full ' + counts.queue + ', RED ' + counts.red + ', 16-coll. ' + counts.excess + ')') +
    card(waiting, 'packets waiting in queues') +
    card((bits / win / 1e6).toFixed(2) + ' Mbps', 'throughput (last ' + (win * 1000).toFixed(0) + ' ms)');
  document.getElementById('scrub').value = Math.round(T / LEN * 1000);
}

function frame(ts) {
  if (playing) {
    if (lastTs !== null) T += (ts - lastTs) / 1000 * (0.001 / secPerMs);
    if (T >= LEN) { T = LEN; playing = false; setPlay(); }
    lastTs = ts; draw(); requestAnimationFrame(frame);
  } else lastTs = null;
}
function setPlay() { document.getElementById('play').innerHTML = playing ? '&#10074;&#10074; Pause' : '&#9654; Play'; }
function setSpeed() {
  const v = +document.getElementById('spd').value; secPerMs = 3 * Math.pow(0.01, v / 100);
  document.getElementById('spdlabel').textContent = '1 ms of network time = ' + secPerMs.toFixed(2) + ' s';
}
document.getElementById('play').onclick = () => {
  if (T >= LEN) T = 0; playing = !playing; setPlay(); if (playing) requestAnimationFrame(frame);
};
document.getElementById('restart').onclick = () => { T = 0; draw(); };
document.getElementById('spd').oninput = setSpeed;
document.getElementById('scrub').oninput = e => { T = +e.target.value / 1000 * LEN; draw(); };
document.getElementById('tsel').onchange = e => { topo = e.target.value; layout(); draw(); };
const qs = document.getElementById('qsel');
for (const k of Object.keys(DATA)) { const o = document.createElement('option'); o.value = k; o.textContent = NAMES[k]; qs.appendChild(o); }
qs.onchange = e => { qname = e.target.value; T = 0; playing = false; setPlay(); prep(); draw(); };
document.getElementById('tsel').value = topo;
setSpeed(); prep(); draw();
</script></body></html>
"""


def build(queues, N, G, start, length, seed, tau_us):
    data = {}
    for q in queues:
        r = simulate(N, G, q, seed=seed, tau=tau_us * 1e-6, sim_time=start + length + 0.02,
                     warmup=min(1.0, start), trace=(start, start + length))
        tr = r["trace"]
        tr["events"] = [[e[0], round(e[1], 7)] + [round(v, 7) if isinstance(v, float) else v
                         for v in ([list(x) if isinstance(x, tuple) else x for x in e[2:]])]
                        if e[0] != "col" else
                        ["col", round(e[1], 7), [[a[0], round(a[1], 7), round(a[2], 7)] for a in e[2]], round(e[3], 7)]
                        for e in tr["events"]]
        for e in tr["events"]:                      # tx: round the delivery time
            if e[0] == "tx":
                e[5] = round(e[5], 7)
        data[q] = tr
    return data


def make_html(data, topology, out):
    names = {q: QUEUE_LABEL[q] for q in data}
    html = (HTML.replace("__DATA__", json.dumps(data, separators=(",", ":")))
                .replace("__NAMES__", json.dumps(names))
                .replace("__TOPO__", topology))
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="NAM-style CSMA/CD packet animation (HTML)")
    ap.add_argument("--queue", required=True, choices=QUEUES + ["all"])
    ap.add_argument("--topology", choices=["bus", "star"], default="bus",
                    help="initial layout (you can switch inside the page)")
    ap.add_argument("--n", type=int, default=8, help="number of stations (4-12 looks best)")
    ap.add_argument("--load", type=float, default=1.2, help="offered load G")
    ap.add_argument("--start", type=float, default=1.0, help="network time where the movie starts (s)")
    ap.add_argument("--length", type=float, default=0.08, help="length of the movie in network seconds")
    ap.add_argument("--tau_us", type=float, default=10, help="propagation delay (us)")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--no-open", action="store_true", help="do not open the browser")
    a = ap.parse_args()

    queues = QUEUES if a.queue == "all" else [a.queue]
    data = build(queues, a.n, a.load, a.start, a.length, a.seed, a.tau_us)
    out = f"animation_{a.queue}.html"
    make_html(data, a.topology, out)
    for q in queues:
        ev = data[q]["events"]
        print(f"{QUEUE_LABEL[q]:<9} window {a.start}-{a.start + a.length} s:  "
              f"{sum(e[0] == 'tx' for e in ev)} packets delivered, "
              f"{sum(e[0] == 'col' for e in ev)} collisions, "
              f"{sum(e[0] == 'drop' for e in ev)} packets dropped")
    print("Created", os.path.abspath(out), f"({os.path.getsize(out) // 1024} KB)")
    if not a.no_open:
        webbrowser.open("file://" + os.path.abspath(out))
