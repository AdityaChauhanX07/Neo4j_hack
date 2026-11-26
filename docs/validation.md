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

## Live virtual bench

The suite now has 61 Python tests. Full CI runs on Python 3.9, 3.11, and
3.13 x64 Linux and Python 3.11 ARM64 Linux. The Python 3.9 job installs only
the laptop test dependencies, so it also exercises the virtual mode without
`smbus2` or `pyserial`. Six WASM tests and eight browser checks cover the
ground view, including import of a freshly captured, replayed, and exported
virtual episode.

The [virtual bench guide](virtual-bench.md) gives the commands. A local
one-minute session through the actual sensor drivers and recorder yielded:

| Check | Result |
| --- | --- |
| Fault injections | F1 through F9, one each |
| Top cause and complete cause set | 9/9 each |
| First-failed-device baseline | 2/9 |
| First correct verdict reached | 9/9 |
| Resolved after clear | 9/9 |
| First correct verdict, recorded-time p50 / p95 | 1,001 / 2,508 ms |
| F5 first verdict / first correct verdict | 1,000 / 2,508 ms |

Those timestamps come from one x64 Linux run. Live host scheduling varies;
replay uses the captured timestamps. CI publishes its own full session and
matrix report as `virtual-bench-session`.

Additional independent, unlabelled cases check delayed correlated sensor
failures, a temporarily unobserved radio, and a missing driver channel.
The ambiguous power case begins at medium confidence and becomes high only
after healthy radio evidence distinguishes the regulator from its upstream
rail. A new healthy device now refreshes the existing diagnosis. Missing
driver readings remain `STALE` evidence with medium confidence, rather than
being reported as explicit bus errors.

An isolated installed wheel also completed the eight-second F1 scenario,
scored its cause correctly, replayed the capture, and exported a downlink
without board packages installed. Simulation provenance is retained in raw
JSONL, Run nodes, diagnosis output, benchmark reports, and the ground view.

## Independent ranking specification

`tests/reference_rank.py` computes dependency sets, failed and healthy
devices, coverage, contradictions, scores, and tie breaks in plain Python.
It reads topology YAML and classified event facts without calling the
production topology loader, ranking function, or Cypher engine.

Eleven comparison tests check every returned candidate, including its
position, score, covered devices, and contradicted count. They cover F1 to
F9 at the initial and final windows, exclusion passes for combined faults,
all three quadcopter faults, unknown devices, other runs, and inclusive
window boundaries. The hand-built regulator test remains separate.

```sh
python -m pytest -q tests/test_rank.py tests/test_rank_reference.py
```

The checks pass on Python 3.11 x64 Linux. The full suite now contains 72
tests; CI also runs them on the other supported Linux interpreter and
architecture combinations.

## MCP transport

Relate CLI 1.3.0 passes three sessions through the checked-in `.mcp.json`
command: linked F1 facts and citation IDs, refused mutations with an
unchanged snapshot hash, and preserved medium confidence for intermittent
evidence. The stdio server exposes `get_schema` and `read_cypher` only.
The [MCP guide](mcp.md) documents the client setup and exact checks.

The suite now contains 75 tests. The three MCP checks require the Relate
CLI and run in the Ground view workflow after installation. Other jobs
skip them when the binary is absent. This verifies the protocol path;
LLM-host configuration and narrative answer quality are separate concerns.

## Concurrent readers and downlink

A five-second live virtual capture passes with a second process following
the directory over read-only MCP. A downlink made while the recorder is
still running produces matching `.rl` and JSON content. The same follower
observes later committed events, while the snapshot remains unchanged.
See [live-store.md](live-store.md) for the process model and commands.

The suite now contains 77 tests, including four CLI integration checks.
Ground-view CI supplies the Relate CLI for those checks; Python-only jobs
skip them when it is absent.

## Mac and Windows installs

Fresh, non-editable installs on hosted macOS ARM64 and Windows x64 passed
their Python 3.11 suites and the virtual F1 CLI workflow on November 26,
2026. The Mac job also passed CLI export and the MCP protocol checks.
Linux-only errno checks and unavailable CLI/PTY integrations are skipped
explicitly on the relevant platforms. The [laptop guide](laptop-install.md)
documents commands and coverage.

The first Mac matrix run found an extra episode caused by intermittent
reply transitions aligning with the 2 Hz polling boundary. A regression
test reproduces that alias, and the virtual reply windows now alternate
every 0.75 seconds. The complete matrix then passed on both platforms.

## Shared thresholds and stuck-sensor evidence

The seven timing, classification, recovery, and retention defaults now
come from one packaged [detection config](detection.md). A subprocess check
changes the settle interval to 500 ms and verifies both the earlier
verdict and the Run's config hash. Invalid count and ratio values are
rejected. Default values retain the existing behavior.

An additional unlabelled end-to-end recording enables stuck detection on
the gyro channel. Ten repeated values identify the IMU with `STUCK`
evidence, and changing readings resolve the episode. This is an opt-in
channel policy; the default constant virtual registers do not enable it.

The suite now contains 86 tests, including four CLI integration checks.

## Published 36-injection virtual bundle

The [recorded matrix](virtual-matrix.md) retains four live repetitions of
all nine modeled faults. All 36 reach their full expected cause set and
resolve; the naive baseline scores 8/36. Recorded-time first-correct p50
and p95 are 1,000 and 2,503 ms. The 192,512-byte persistent `.rl` and its
JSON export are checked against the raw recording and file-hash manifest.

Two bundle tests verify replayed per-injection times, persistence, hashes,
and agreement with the independent scorer across every saved episode.
The suite now contains 88 tests. Six WASM tests and nine browser checks
cover the dashboard, including the full recorded graph and episode
switching. The graph loads on demand when the operator opens the session.
