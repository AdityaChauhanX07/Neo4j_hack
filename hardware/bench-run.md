# Bench replay and measurements

Use 64-bit Raspberry Pi OS and the board's reviewed topology. From the
repository root, run the synthetic checks on the Pi before collecting the
physical fault matrix.

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install .
python sim/bench.py > /tmp/commoncause-bench-fixtures.jsonl
commoncause matrix /tmp/commoncause-bench-fixtures.jsonl --bench-repeats 1 --min-top-one 1
commoncause benchmark --samples 100
```

## Record a session

Check that every expected channel appears in an all-healthy recording. Use
the same Pi clock for readings and fault markers. Keep each recording
grouped by run ID, with increasing sequence numbers and nondecreasing
timestamps in Unix milliseconds.

Initialize the writer once from the final wiring file.

```sh
commoncause init --db board/store --topology topologies/cubesat-bench.yaml
```

The recorder can pipe JSONL into the terminal view while preserving the raw
stream. Use this pipeline after the recorder command.

```sh
tee recordings/bench-run.jsonl | commoncause run --db board/store --tui
```

Keep readings and markers in the same file. Use an injection and clear
marker for each of the nine faults, four runs per fault. Use the wiring
sheet to confirm the intended affected devices and let each episode
recover before the next injection. If the target varies, include its
component ID in the marker's `expected` field.

## Score the bench

```sh
commoncause matrix recordings/bench-run.jsonl --bench-repeats 4 --min-top-one 0.9 --json
commoncause benchmark --db board/store --samples 100 --json
commoncause downlink --db board/store --out downlink
```

The scorer reports top-1, the first-failed-device baseline, and coverage
of all expected causes. For F9, inspect both ranked causes. It also reports
p50 and p95 of recorded time from first anomaly to first verdict. The
benchmark separately measures the warm native rank query in wall time
and reports the store size in bytes. Run it on the Pi for Pi numbers.
Use the same topology when replaying sessions, and use a fresh store
after changes to the wiring.
