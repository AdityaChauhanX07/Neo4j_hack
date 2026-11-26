import argparse
import json
import subprocess
import sys
from collections import Counter
from contextlib import ExitStack, closing
from pathlib import Path

import relate
import yaml

from .benchmark import benchmark, percentiles
from .check_capture import check_capture, show_check
from .downlink import downlink
from .matrix import matrix
from .replay import replay
from .schema import read_asset
from .topology import load_topology
from .view import diagnosis, explain, live_view, summarize

DEFAULT_STORE = Path("data/common-cause.rl")
DEFAULT_TOPOLOGY = Path("topologies/cubesat-bench.yaml")
DEFAULT_HARDWARE = Path("hardware/cubesat-pi4.yaml")


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

    run = commands.add_parser("run", help="diagnose live telemetry from the Pi or stdin")
    run.add_argument("--db", type=Path, required=True)
    run.add_argument("--hardware", type=Path, help="read sensors using this Linux hardware map")
    run.add_argument("--recording", type=Path, help="save raw JSONL while diagnosing")
    run.add_argument("--tui", action="store_true", help="show wiring status and diagnoses as they change")
    capture_options(run)

    record = commands.add_parser("record", help="record raw telemetry from the Pi")
    record.add_argument("--hardware", type=Path, default=DEFAULT_HARDWARE)
    record.add_argument("--out", required=True, help="new JSONL file, or - for stdout")
    record.add_argument("--device", help="sample just this device during bench bring-up")
    capture_options(record)

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
    score.add_argument("--topology", type=Path, default=DEFAULT_TOPOLOGY)
    score.add_argument("--json", action="store_true")
    score.add_argument("--expect-count", type=int, help="require this many labeled injections")
    score.add_argument("--bench-repeats", type=int, help="require this many injections for each fault F1 through F9")
    score.add_argument("--min-top-one", type=float, help="require this top-1 fraction, from 0 to 1")

    check = commands.add_parser("check-capture", help="check channel health and cadence in captured JSONL")
    check.add_argument("recording", type=Path)
    check.add_argument("--topology", type=Path, default=DEFAULT_TOPOLOGY)
    check.add_argument("--min-seconds", type=float, default=0, help="require this span of recorded time")
    check.add_argument("--min-rate", type=float, default=0, help="require this fraction of each channel's configured rate")
    check.add_argument("--json", action="store_true")

    timing = commands.add_parser("benchmark", help="time the native rank query for a stored episode")
    timing.add_argument("--db", type=Path, default=DEFAULT_STORE)
    timing.add_argument("--id", help="diagnosis ID (default: latest)")
    timing.add_argument("--samples", type=int, default=100)
    timing.add_argument("--json", action="store_true")
    return root


def capture_options(command):
    command.add_argument("--topology", type=Path, default=DEFAULT_TOPOLOGY)
    command.add_argument("--duration", type=float, help="stop after this many seconds")
    command.add_argument("--run", help="recording ID, defaulting to the UTC start time")
    command.add_argument("--interactive", action="store_true", help="read fault markers from the terminal")


def main():
    args = parser().parse_args()
    try:
        return dispatch(args) or 0
    except KeyboardInterrupt:
        return 130
    except subprocess.CalledProcessError as error:
        print(f"commoncause: {error.stderr.strip() or error}", file=sys.stderr)
        return 1
    except (ValueError, OSError, relate.Error, yaml.YAMLError) as error:
        print(f"commoncause: {error}", file=sys.stderr)
        return 1


def dispatch(args):
    if args.command == "check-capture":
        with args.recording.open(encoding="utf-8") as stream:
            report = check_capture(
                stream, args.topology, min_seconds=args.min_seconds, min_rate=args.min_rate,
            )
        if args.json:
            print(json.dumps(report))
        else:
            show_check(report)
        return int(not report["healthy"])
    if args.command == "record":
        from .board.recorder import save_capture

        with ExitStack() as stack:
            feed = stack.enter_context(closing(board_feed(args)))
            if args.out != "-":
                feed = stack.enter_context(closing(save_capture(feed, Path(args.out))))
            for line in feed:
                if args.out == "-":
                    sys.stdout.write(line)
                    sys.stdout.flush()
        return
    if args.command == "matrix":
        if args.min_top_one is not None and not 0 <= args.min_top_one <= 1:
            raise ValueError("Minimum top-1 fraction must be between 0 and 1")
        rows = matrix(args.recording, args.topology)
        top_one = show_matrix(rows, args.json)
        if args.expect_count is not None and len(rows) != args.expect_count:
            raise ValueError(f"Expected {args.expect_count} injections, found {len(rows)}")
        if args.bench_repeats is not None:
            if args.bench_repeats <= 0:
                raise ValueError("Bench repeats must be positive")
            counts = Counter(row["fault"] for row in rows)
            expected = {f"F{index}": args.bench_repeats for index in range(1, 10)}
            if counts != expected:
                counted = ", ".join(f"{fault}={count}" for fault, count in sorted(counts.items()))
                raise ValueError(f"Expected {args.bench_repeats} injections per F1 through F9, found {counted}")
        if args.min_top_one is not None and top_one / len(rows) < args.min_top_one:
            raise ValueError(f"Top-1 fraction is below {args.min_top_one:.2f}")
        return
    if args.command == "downlink":
        downlink(args.db, args.out, args.relate)
        return

    read_only = args.command in {"diagnose", "explain", "impact", "benchmark"}
    with relate.connect(str(args.db), read_only=read_only) as db:
        if args.command == "init":
            load_topology(db, args.topology)
        elif args.command == "replay":
            if args.topology:
                load_topology(db, args.topology)
            with args.recording.open(encoding="utf-8") as feed:
                replay(db, feed, run_id=args.run, speed=args.speed)
        elif args.command == "run":
            on_frame = live_view() if args.tui else None
            if args.hardware:
                from .board.recorder import capture_clock, save_capture

                clock = capture_clock()
                with ExitStack() as stack:
                    load_topology(db, args.topology)
                    feed = stack.enter_context(closing(board_feed(args, clock=clock)))
                    if args.recording:
                        feed = stack.enter_context(closing(save_capture(feed, args.recording)))
                    replay(db, feed, source="live", on_frame=on_frame, commit_clock=clock)
            else:
                if args.recording or args.interactive or args.duration is not None or args.run is not None:
                    raise ValueError("Capture options require --hardware; otherwise run reads JSONL on stdin")
                replay(db, sys.stdin, source="live", on_frame=on_frame)
        elif args.command == "benchmark":
            timing = benchmark(db, args.db, args.id, args.samples)
            if args.json:
                print(json.dumps(timing))
            else:
                rank_ms = timing["rank_ms"]
                print(f"{timing['diagnosis']}  {timing['architecture']}  {timing['store_bytes']} bytes")
                print(f"Rank latency  {rank_ms['samples']} samples  "
                      f"p50 {rank_ms['p50']:.3f} ms  p95 {rank_ms['p95']:.3f} ms")
                live = timing["live_verdict_ms"]
                if live["samples"]:
                    print(f"Live time to verdict  {live['samples']} episodes  "
                          f"p50 {live['p50']} ms  p95 {live['p95']} ms")
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


def board_feed(args, *, clock=None):
    from .board.recorder import OperatorConsole, capture
    from .board.settings import load_board

    board = load_board(args.hardware, args.topology)
    console = OperatorConsole(sys.stdin, sys.stderr) if args.interactive else None
    return capture(
        board, run_id=args.run, duration=args.duration, console=console,
        device=getattr(args, "device", None), clock=clock,
    )


def show_matrix(rows, as_json):
    top_one = sum(row["ranked"][:1] == row["expected"][:1] for row in rows)
    baseline = sum(row["baseline"] == row["expected"][0] for row in rows)
    all_causes = sum(set(row["ranked"]) == set(row["expected"]) for row in rows)
    recorded = percentiles(row["decision_ms"] for row in rows if row["decision_ms"] is not None)
    correct = percentiles(row["first_correct_ms"] for row in rows if row["first_correct_ms"] is not None)
    totals = {
        "injections": len(rows), "top_one": top_one, "baseline": baseline,
        "all_causes": all_causes, "recorded_decision_ms": recorded,
        "recorded_first_correct_ms": correct,
    }
    if as_json:
        print(json.dumps({"totals": totals, "injections": rows}))
        return top_one
    for row in rows:
        ranked = ", ".join(row["ranked"]) or "none"
        expected = ", ".join(row["expected"])
        elapsed = row["first_correct_ms"]
        timing = f"{elapsed} ms" if elapsed is not None else "never"
        print(f"{row['run']} {row['fault']}  expected {expected}  ranked {ranked}  "
              f"baseline {row['baseline']}  first correct {timing}")
    count = len(rows)
    print(f"Top-1 {top_one}/{count}  baseline {baseline}/{count}  all causes {all_causes}/{count}")
    if recorded["samples"]:
        print(f"Recorded time to first verdict  p50 {recorded['p50']} ms  p95 {recorded['p95']} ms")
    print(f"First correct verdicts {correct['samples']}/{count}")
    if correct["samples"]:
        print(f"Recorded time to first correct verdict  p50 {correct['p50']} ms  p95 {correct['p95']} ms")
    return top_one
