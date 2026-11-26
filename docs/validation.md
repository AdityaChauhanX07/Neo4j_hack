# Software validation

All inputs in these checks are simulated. They exercise the real Relate
database, shared Cypher queries, and diagnosis code. They do not establish
physical sensor accuracy, wiring safety, or Raspberry Pi performance.

## Python compatibility

On November 26, 2026, non-editable package installs passed all 40 tests on
Python 3.9.25, 3.11.18, and 3.13.5 on x64 Linux. CI tests those three
interpreter versions and Python 3.11 on ARM64 Linux. The Python 3.9 job uses
Ubuntu 24.04 because the Ubuntu 26.04 runner has no setup-python 3.9 build.

## Clean laptop install

A fresh checkout at `3d5ef2f` used Python 3.9.25 and `pip install '.[test]'`,
without the board extras. All 40 Python tests passed. The installed wheel's
queries and catalogue also worked through the CLI commands below.

```sh
commoncause diagnose --last
commoncause explain dx:f1-fixture:1
commoncause impact REG_B
commoncause replay recordings/f1-fixture.jsonl \
  --topology topologies/cubesat-bench.yaml --db board/store
commoncause matrix recordings/f1-fixture.jsonl
commoncause downlink --db board/store --out board/clean-downlink
python -m sim.demo
commoncause matrix ground/public/simulations/cubesat.jsonl \
  --expect-count 9 --min-top-one 1
commoncause matrix ground/public/simulations/quadcopter.jsonl \
  --topology topologies/quadcopter.yaml --expect-count 3 --min-top-one 1
commoncause benchmark --db board/store --samples 100
```

Relate CLI 1.3.0 exported the replay store and its JSON using the pinned
`relate-db==1.0.1` Python package. The fresh export contained 108 nodes and
206 relationships. Install the CLI before the downlink command.

| Check | Result |
| --- | --- |
| F1 replay | `REG_B`, resolved, high confidence |
| CubeSat matrix | 9/9 top cause and full cause set; baseline 2/9 |
| Quadcopter matrix | 3/3 top cause and full cause set; baseline 1/3 |
| CubeSat first correct verdict | Recorded-time p50 1,000 ms; p95 2,500 ms |
| Native rank query, 100 samples | Wall-time p50 1.779 ms; p95 2.057 ms |
| Replay store | 20,382 bytes on this x64 Linux host |

The latency and size are one laptop-style run, not Pi measurements or
hardware guarantees. Native query time measures computation; the matrix's
recorded time also includes the configured detection and heartbeat waits.

The clean browser build used Node.js 24.22.3. `npm ci`, all five WASM tests,
and `npm run build` passed. The Ground view workflow additionally replays
the F1 input into a new store, exports it, and passes that new JSON to the
browser import checks. The seven browser checks cover queries, imports,
case switching, healthy-device contradictions, loading races, and a small
screen layout.

## Varied simulations

The expanded suite has 47 Python tests. It checks seeded reproducibility,
all nine fault types with varied readings, recovery after clearing faults,
and healthy controls. Replaying the varied recordings without injection
labels must produce the same causes. This keeps the expected answers out
of the diagnosis path.

The seeded generator uses these fixed bounds:

- Fault start: 1,000 to 2,500 ms, in 500 ms steps.
- Fault duration: 4,000 to 8,000 ms, in 500 ms steps.
- Recovery observation: 3,000 to 5,000 ms after clearing the fault.
- Frame timestamps: up to 75 ms early or late, preserving time order.
- Sensor values: uniform noise of up to 2% of `max(abs(value), 1)`.
- Heartbeat: an increasing counter at a nominal 1 Hz, with frame jitter.
- Sample order: shuffled within each frame.

Three seeds with four repeats each produced 108 fault trials. All 108
reached the correct full cause set and resolved by the end of their
recording. Twelve separate healthy runs produced no diagnosis. These are
results for bounded synthetic scenarios, not an estimate of real-world
accuracy or performance under arbitrary noise and packet loss.

| Seed | Top cause | Full cause set | Resolved | First correct p50 | First correct p95 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 7 | 36/36 | 36/36 | 36/36 | 1,457 ms | 2,643 ms |
| 42 | 36/36 | 36/36 | 36/36 | 1,133 ms | 2,089 ms |
| 2026 | 36/36 | 36/36 | 36/36 | 1,110 ms | 2,530 ms |

Each seed's first-failed-device baseline scored 8/36. Times in this table
are elapsed recording time from the first anomaly. The
[result summary](simulation-results.json) includes recording, generator,
and topology hashes. Reproduce each seed with the Python version recorded
in that summary:

```sh
python sim/bench.py --seed 7 --repeats 4 > /tmp/commoncause-seed-7.jsonl
commoncause matrix /tmp/commoncause-seed-7.jsonl \
  --bench-repeats 4 --min-top-one 1 --json
```

Repeat with seeds 42 and 2026. CI also saves the seed-42 JSONL and matrix
report as the `simulated-fault-matrix` artifact on its Python 3.11 x64 job.

For a healthy control, use a new store path for each replay:

```sh
python sim/bench.py --fault healthy --seed 42 --repeats 4 > /tmp/commoncause-healthy.jsonl
commoncause replay /tmp/commoncause-healthy.jsonl \
  --topology topologies/cubesat-bench.yaml --db /tmp/commoncause-healthy-store
relate --database /tmp/commoncause-healthy-store --read-only \
  'MATCH (d:Diagnosis) RETURN count(d) AS diagnoses'
```

The expected diagnosis count is zero. Recovery and the same control for
all three seeds are checked in `tests/test_simulation.py`.
