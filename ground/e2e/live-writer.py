import sys
from itertools import groupby

import relate

from commoncause.classify import Reading
from commoncause.replay import Run
from commoncause.topology import load_topology
from sim.bench import records


rows = list(records("F1"))
injected, cleared = [row["ts"] for row in rows if row.get("type") == "fault"]
frames = [
    (timestamp, [Reading.from_record({**row, "simulated": True}) for row in batch])
    for timestamp, batch in groupby((row for row in rows if "channel" in row), key=lambda row: row["ts"])
]
phases = {
    "healthy": [batch for timestamp, batch in frames if timestamp < injected],
    "fault": [batch for timestamp, batch in frames if injected <= timestamp < cleared],
    "recovered": [batch for timestamp, batch in frames if timestamp >= cleared],
}
with relate.connect(sys.argv[1]) as db:
    load_topology(db, "topologies/cubesat-bench.yaml")
    run = Run(db, "bench-fixture-f1", "virtual-bench")
    print("ready", flush=True)
    for command in sys.stdin:
        phase = command.strip()
        for frame in phases[phase]:
            run.ingest(frame)
        print(phase, flush=True)
    run.finish(True)
