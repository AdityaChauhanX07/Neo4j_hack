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
