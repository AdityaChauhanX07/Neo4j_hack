import argparse
import json
from pathlib import Path

import relate

from commoncause.downlink import graph_json
from commoncause.matrix import matrix
from commoncause.replay import replay
from commoncause.topology import load_topology

from . import bench, quad

ROOT = Path(__file__).resolve().parents[1]
BENCH_LABELS = {
    "F1": "Regulator B loses power",
    "F2": "I2C-1 goes down",
    "F3": "I2C-3 goes down",
    "F4": "Sun sensor 2 disconnects",
    "F5": "Main 5 V rail goes down",
    "F6": "Radio heartbeat stops",
    "F7": "IMU driver stalls",
    "F8": "Intermittent sun sensor connection",
    "F9": "Regulator and bus fail together",
}
QUAD_LABELS = {
    "bec-brownout": "BEC brownout",
    "compass-bus-failure": "Compass bus failure",
    "esc-3-dropout": "ESC 3 dropout",
}


def write_suite(out, slug, label, topology_name, readings, labels):
    topology = ROOT / "topologies" / topology_name
    recording = out / f"{slug}.jsonl"
    with recording.open("w", encoding="utf-8") as feed:
        for row in readings:
            feed.write(json.dumps(row, separators=(",", ":")) + "\n")

    graph_path = out / f"{slug}.json"
    with relate.connect() as db, recording.open(encoding="utf-8") as feed:
        load_topology(db, topology)
        replay(db, feed)
        graph = graph_json(db)
    graph_path.write_text(json.dumps(graph, separators=(",", ":")) + "\n", encoding="utf-8")

    cases = matrix(recording, topology)
    return {
        "id": slug,
        "label": label,
        "graph": graph_path.name,
        "recording": recording.name,
        "score": {
            "count": len(cases),
            "top_one": sum(row["ranked"][:1] == row["expected"][:1] for row in cases),
            "baseline": sum(row["baseline"] == row["expected"][0] for row in cases),
        },
        "cases": [
            {
                "id": row["fault"], "label": labels[row["fault"]], "run": row["run"],
                "expected": row["expected"], "baseline": row["baseline"],
            }
            for row in cases
        ],
    }


def build_demo(out):
    out.mkdir(parents=True, exist_ok=True)
    suites = [
        write_suite(out, "cubesat", "CubeSat", "cubesat-bench.yaml", bench.records(), BENCH_LABELS),
        write_suite(out, "quadcopter", "Quadcopter", "quadcopter.yaml", quad.records(), QUAD_LABELS),
    ]
    (out / "index.json").write_text(
        json.dumps({"suites": suites}, indent=2) + "\n", encoding="utf-8",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build the simulated telemetry demo")
    parser.add_argument("--out", type=Path, default=ROOT / "ground" / "public" / "simulations")
    build_demo(parser.parse_args().out)
