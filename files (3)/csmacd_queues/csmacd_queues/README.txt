CSMA/CD with queue algorithms: DropTail, FQ, RED, DRR  (Python simulation)
=========================================================================

FILES
  animate.py          NAM-style packet animation (creates an HTML file, play button)
  animation_all.html  sample animation: all 4 algorithms, bus + star layouts
  csmacd.py           simulator: CSMA/CD MAC + the four queue algorithms
  topology.py         draws the topology diagram (shared bus + inside of a station)
  run_experiments.py  runs experiments, prints tables, saves graphs and CSV files
  requirements.txt    needs only matplotlib
  results_*/          sample output from a finished run

HOW TO RUN (Windows PowerShell, inside this folder)
  py -m pip install matplotlib                  (one time)

  py run_experiments.py --queue droptail        DropTail only
  py run_experiments.py --queue fq              Fair Queuing only
  py run_experiments.py --queue red             RED only
  py run_experiments.py --queue drr             Deficit Round Robin only
  py run_experiments.py --queue all             all four + comparison graphs (~3 min)

  A single queue takes under 1 minute. For a faster test add:  --seeds 2 --time 8

PACKET ANIMATION (like NAM)
  py animate.py --queue red                    opens animation_red.html in your browser
  py animate.py --queue all                    all four algorithms, pick one in the page
  py animate.py --queue fq --topology star     start with the star layout
  options: --n stations (4-12)  --load G  --start / --length (which part of the run)
           --no-open (do not launch the browser)
  In the page: Play/Pause, Restart, Speed slider, Time slider, Queue and Topology menus.
    blue  = packet delivered (bigger dot = bigger frame)   orange = collision
    red   = dropped packet (queue full / RED / 16 collisions)
    bars  = frames waiting in each station's queue
  Counters show packets delivered, travelling, collisions, drops, queued, throughput.
  "Star" is a hub-based star (a hub is a shared medium, so collisions still happen).
  Mesh is NOT included: mesh links are point-to-point, which have no CSMA/CD collisions.

ONE SINGLE SIMULATION (prints throughput, delay, collisions, loss per flow)
  py csmacd.py --queue red --n 10 --load 1.0
  options: --queue droptail|fq|red|drr   --n stations   --load G   --tau_us   --time

OUTPUT FOLDERS
  results_<queue>/    topology_<queue>.png  (topology diagram)
                      A1..A4  throughput, delay, collisions, loss vs load
                      B1..B3  throughput, delay, collisions vs number of stations
                      summary_<queue>.csv   (all numbers)
  results_compare/    (only with --queue all)  cmp_*.png overlays of the 4 algorithms,
                      cmp_bars_G1.2.png (bar-chart comparison), summary_all_queues.csv
  results_droptail/C1_efficiency_vs_a.png  utilization vs propagation delay + theory

THE FOUR ALGORITHMS (queue inside every station)
  DropTail  one FIFO, full queue -> drop the arriving frame
  RED       one FIFO, random early drops when average queue is between 5 and 15
  FQ        one queue per flow, smallest virtual finish time first, longest queue drops
  DRR       one queue per flow, round robin with 1500-byte quantum, longest queue drops

TRAFFIC (each station sends 3 flows to the sink)
  heavy 1500 B (60 % of load), medium 500 B (30 %), light 100 B (10 %)
  FQ and DRR need several flows per station to show any difference from DropTail.

PARAMETERS: 10 Mbps bus, propagation delay 10 us, slot 51.2 us, IFS 9.6 us,
  32-bit jam, 16 attempts, backoff cap 10, queue limit 50 frames, 20 s runs,
  2 s warm-up, 5 seeds per point.
