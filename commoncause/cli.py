import argparse
import json
import subprocess
import sys
from pathlib import Path

import relate
import yaml

from .downlink import downlink
from .matrix import matrix
from .replay import replay
from .schema import read_asset
from .topology import load_topology
from .view import diagnosis, explain, live_view, summarize

DEFAULT_STORE = Path("data/common-cause.rl")


def parser():
    root = argparse.ArgumentParser(prog="commoncause")
    commands = root.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="load a topology and its failure catalogue")
    init.add_argument("--db", type=Path, required=True)
    init.add_argument("--topology", type=Path, required=True)

    playback = commands.add_parser("replay", help="replay a JSONL recording")
    playback.add_argument("recording", type=Path)
    playback.add_argument("--db", type=Path, required=True)
    playback.add_argument("--topology", type=Path)
    playback.add_argument("--run", help="store a single recording under a new run ID")
    playback.add_argument("--speed", type=float, help="pace replay at a multiple of recorded time")

    run = commands.add_parser("run", help="ingest live JSONL telemetry on stdin")
    run.add_argument("--db", type=Path, required=True)
    run.add_argument("--tui", action="store_true", help="print diagnoses as they change")

    last = commands.add_parser("diagnose", help="read the latest verdict")
    last.add_argument("--db", type=Path, default=DEFAULT_STORE)
    last.add_argument("--last", action="store_true", help="read the latest verdict (default)")
    last.add_argument("--json", action="store_true")

    details = commands.add_parser("explain", help="read the evidence and recovery for a verdict")
    details.add_argument("id")
    details.add_argument("--db", type=Path, default=DEFAULT_STORE)
    details.add_argument("--json", action="store_true")

    impact = commands.add_parser("impact", help="read which devices depend on a component")
    impact.add_argument("part")
    impact.add_argument("--db", type=Path, default=DEFAULT_STORE)

    export = commands.add_parser("downlink", help="clone a store into a .rl bundle and export JSON")
    export.add_argument("--db", type=Path, required=True)
    export.add_argument("--out", type=Path, default=Path("downlink"))
    export.add_argument("--relate", default="relate", help="path to the Relate CLI")

    score = commands.add_parser("matrix", help="score a labelled fault recording")
    score.add_argument("recording", type=Path)
    score.add_argument("--topology", type=Path, default=Path("topologies/cubesat-bench.yaml"))
    score.add_argument("--json", action="store_true")
    return root


def main():
    args = parser().parse_args()
    try:
        dispatch(args)
    except subprocess.CalledProcessError as error:
        print(f"commoncause: {error.stderr.strip() or error}", file=sys.stderr)
        return 1
    except (ValueError, OSError, relate.Error, yaml.YAMLError) as error:
        print(f"commoncause: {error}", file=sys.stderr)
        return 1
    return 0


def dispatch(args):
    if args.command == "matrix":
        show_matrix(matrix(args.recording, args.topology), args.json)
        return
    if args.command == "downlink":
        downlink(args.db, args.out, args.relate)
        return

    read_only = args.command in {"diagnose", "explain", "impact"}
    with relate.connect(str(args.db), read_only=read_only) as db:
        if args.command == "init":
            load_topology(db, args.topology)
        elif args.command == "replay":
            if args.topology:
                load_topology(db, args.topology)
            with args.recording.open(encoding="utf-8") as feed:
                replay(db, feed, run_id=args.run, speed=args.speed)
        elif args.command == "run":
            replay(db, sys.stdin, source="live", on_frame=live_view() if args.tui else None)
        elif args.command == "impact":
            query = read_asset("queries", "impact.cypher")
            for row in db.execute(query, {"part": args.part}):
                print(f"{row['device']}  {', '.join(sorted(row['channels_lost']))}")
        else:
            verdict = diagnosis(db, getattr(args, "id", None))
            if verdict is None:
                raise ValueError("No matching diagnosis")
            if args.json:
                print(json.dumps(verdict))
            elif args.command == "explain":
                print(explain(verdict))
            else:
                print(summarize(verdict))


def show_matrix(rows, as_json):
    top_one = sum(row["ranked"][:1] == row["expected"][:1] for row in rows)
    baseline = sum(row["baseline"] == row["expected"][0] for row in rows)
    all_causes = sum(set(row["ranked"]) == set(row["expected"]) for row in rows)
    totals = {"injections": len(rows), "top_one": top_one, "baseline": baseline, "all_causes": all_causes}
    if as_json:
        print(json.dumps({"totals": totals, "injections": rows}))
        return
    for row in rows:
        ranked = ", ".join(row["ranked"]) or "none"
        expected = ", ".join(row["expected"])
        print(f"{row['run']} {row['fault']}  expected {expected}  ranked {ranked}  baseline {row['baseline']}")
    count = len(rows)
    print(f"Top-1 {top_one}/{count}  baseline {baseline}/{count}  all causes {all_causes}/{count}")
