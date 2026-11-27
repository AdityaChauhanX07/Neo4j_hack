import json

import relate

from commoncause.downlink import graph_json
from commoncause.replay import replay
from commoncause.topology import load_topology
from sim.bench import records

rows = list(records("healthy"))
start = rows[0]["ts"]
rows = [dict(row, simulated=True) for row in rows if not 1000 <= row["ts"] - start < 5000]
with relate.connect() as db:
    load_topology(db, "topologies/cubesat-bench.yaml")
    replay(db, map(json.dumps, rows))
    print(json.dumps(graph_json(db)))
