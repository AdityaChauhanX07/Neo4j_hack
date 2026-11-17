# Common Cause demo

Open [the ground view](https://adityachauhanx07.github.io/Neo4j_hack/) in a
browser and share the tab or record it. The dashboard uses simulated telemetry
from a CubeSat and a quadcopter. The recording can follow this sequence in
about 90 seconds.

1. **0:00–0:25** Open CubeSat F1. A simulated regulator dropout takes several
   devices offline. Point out `REG_B` and its highlighted paths to the affected
   devices. The diagnosis also reports how many healthy devices would
   contradict the suspect.
2. **0:25–0:45** Switch to CubeSat F2. The top suspect changes to `I2C-1`.
   Open the Cypher console, choose **Rank this episode**, and run the query to
   show Relate returning the ranking from the graph in the browser.
3. **0:45–1:10** Switch to [CubeSat F9](https://adityachauhanx07.github.io/Neo4j_hack/?case=cubesat%3AF9).
   Show `REG_B` and `I2C-3` in the ranking. The first suspect explains part
   of the failure and the second explains devices that remain uncovered.
4. **1:10–1:30** Switch to the quadcopter BEC brownout. Show `BEC_5V` on the
   new wiring graph. Point to **Download simulated readings** so viewers can
   replay the suite or inspect the raw inputs.

## Reproduce the results

From the repository root with the Python package installed, generate and
score the same readings the browser offers for download.

```sh
python -m sim.demo
commoncause matrix ground/public/simulations/cubesat.jsonl
commoncause matrix ground/public/simulations/quadcopter.jsonl \
  --topology topologies/quadcopter.yaml
```

The expected first cause comes from each injection marker. The matrix command
compares it with the graph's first ranked suspect and with the first failed
device. The graph ranks the first cause correctly in 9 of 9 CubeSat cases and
3 of 3 quadcopter cases. The first failed device matches in 2 of 9 and 1 of 3.
