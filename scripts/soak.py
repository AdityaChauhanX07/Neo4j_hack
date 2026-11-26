import argparse
import hashlib
import json
import platform
import resource
import subprocess
from contextlib import closing
from datetime import datetime, timezone
from math import isfinite
from pathlib import Path
from time import monotonic

import relate

from commoncause.board.recorder import capture, capture_clock, save_capture
from commoncause.board.settings import load_board
from commoncause.board.virtual import VirtualBench
from commoncause.check_capture import check_capture
from commoncause.replay import replay
from commoncause.topology import load_topology

ROOT = Path(__file__).resolve().parents[1]


def tree_bytes(path):
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def peak_rss():
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak if platform.system() == "Darwin" else peak * 1024


def soak(out, duration):
    if not isfinite(duration) or duration <= 0:
        raise ValueError("Duration must be finite and positive")
    topology = ROOT / "topologies" / "cubesat-bench.yaml"
    board = load_board(ROOT / "hardware" / "cubesat-pi4.yaml", topology)
    bench = VirtualBench(board, topology)
    out.mkdir(parents=True, exist_ok=False)
    recording, store = out / "healthy.jsonl", out / "store"
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    report = {
        "simulated": True, "code_sha": revision,
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "topology_sha256": hashlib.sha256(topology.read_bytes()).hexdigest(),
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(), "python": platform.python_version(),
        "requested_seconds": duration, "checkpoints": [],
    }
    started = monotonic()
    next_checkpoint = 60

    def checkpoint(db, run):
        nonlocal next_checkpoint
        elapsed = monotonic() - started
        if elapsed < next_checkpoint:
            return
        row = {
            "seconds": round(elapsed, 3), "peak_rss_bytes": peak_rss(),
            "store_bytes": tree_bytes(store),
            "diagnoses": db.execute("MATCH (dx:Diagnosis) RETURN count(dx) AS count").fetchone()["count"],
        }
        report["checkpoints"].append(row)
        (out / "progress.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(row), flush=True)
        next_checkpoint += 60

    clock = capture_clock()
    with relate.connect(str(store)) as db:
        load_topology(db, topology)
        with closing(capture(
            board, duration=duration, run_id="virtual-soak", clock=clock,
            transports=bench.transports, on_marker=bench.mark, simulated=True,
        )) as feed, closing(save_capture(feed, recording)) as saved:
            replay(db, saved, source="virtual-bench", on_frame=checkpoint, commit_clock=clock)
        report["diagnoses"] = db.execute("MATCH (dx:Diagnosis) RETURN count(dx) AS count").fetchone()["count"]
        report["events"] = db.execute("MATCH (e:Event) RETURN count(e) AS count").fetchone()["count"]
        report["peak_rss_bytes"] = peak_rss()
    report["elapsed_seconds"] = round(monotonic() - started, 3)
    report["store_bytes"] = tree_bytes(store)
    report["recording_bytes"] = recording.stat().st_size
    with recording.open() as feed:
        report["capture_health"] = check_capture(feed, topology, min_seconds=max(0, duration - 1), min_rate=0.9)
    report["recording_sha256"] = hashlib.sha256(recording.read_bytes()).hexdigest()
    report["passed"] = report["capture_health"]["healthy"] and report["diagnoses"] == 0
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: value for key, value in report.items() if key not in {"checkpoints", "capture_health"}}), flush=True)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Measure a healthy live virtual capture on this host")
    parser.add_argument("--out", type=Path, required=True, help="new output directory")
    parser.add_argument("--duration", type=float, default=3600)
    args = parser.parse_args()
    raise SystemExit(0 if soak(args.out, args.duration)["passed"] else 1)
