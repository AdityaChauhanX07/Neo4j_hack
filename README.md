# Common Cause

Find the shared cause behind several sensor alarms, using their power and
data dependencies in an embedded Relate graph.

**[Try the browser demo](https://adityachauhanx07.github.io/Neo4j_hack/)** ·
[Data and query interfaces](docs/interfaces.md) · [Validation](docs/validation.md)

## Use case

Three satellite sensors stop responding. They use two different data buses,
but share one regulator. Common Cause follows those connections and checks
the healthy devices, too, to distinguish a shared supply failure from a bus
problem or an individual sensor fault.

The intended users are student satellite teams investigating correlated
telemetry faults. This submission is a working **simulation**: the browser
and laptop paths need no hardware, API key, or cloud database. A quadcopter
example uses the same diagnosis engine with a different topology.

## Try the browser demo

1. Open the [deployed site](https://adityachauhanx07.github.io/Neo4j_hack/)
   and select **Try a fault**.
2. Follow **All healthy → The fault → The cause → Recovery**. The first
   scenario identifies Regulator B and shows why healthy sensors weaken
   the alternative bus explanation.
3. Try **A blocked data bus** or **Two faults at once**. Open **Evidence
   workspace** to inspect the full wiring, readings, candidate rankings,
   recovery guidance, and read-only Cypher console.

The walkthrough advances through recorded simulated telemetry. It does
not inject a new live fault. **Inspect the 36-fault recording** opens the
larger retained virtual-bench session; **Connect live** supports a running
laptop capture through a separate read-only Relate HTTP follower.

## How it uses Relate

- **Writable mode: directory store.** Python embeds Relate for ingestion,
  classification, diagnosis, and recovery history. A directory such as
  `board/f1-replay/store` preserves the graph while a recorder writes and
  separate readers inspect committed observations.
- **Distribution mode: single file.** The committed snapshots at
  `data/common-cause.rl` and `data/virtual-matrix.rl` let judges inspect
  persistent graphs immediately, without rerunning a capture.
- **Browser mode: in memory.** Relate WASM reconstructs a JSON downlink in
  a worker and runs Cypher locally. The source JSON and persistent native
  snapshots remain available after the tab closes.

The graph models power rails, regulators, buses, drivers, devices, telemetry
channels, events, diagnoses, failure modes, and recovery procedures.
Shared [Cypher queries](queries/) rank upstream components by the failed
devices they explain and the healthy devices that contradict them. Another
pass can identify a second cause for failures left unexplained by the first.
The default diagnosis is deterministic graph reasoning and needs no LLM.

## Try the F1 replay

Use Git and Python 3.9 or newer; Python 3.11 is the tested laptop setup.
From a terminal on Linux or macOS:

```sh
git clone https://github.com/AdityaChauhanX07/Neo4j_hack.git
cd Neo4j_hack
python3 -m venv .venv
. .venv/bin/activate
python -m pip install .
commoncause diagnose --last
commoncause explain dx:f1-fixture:1
commoncause impact REG_B
```

The bundled F1 diagnosis names `REG_B`, covers three failed devices, has
zero healthy-device contradictions, and is resolved. `explain` includes
the recorded evidence IDs and linked recovery procedure. See the
[laptop guide](docs/laptop-install.md) for Windows PowerShell commands.
Run all commands below from the repository root with this environment active.

Rebuild the graph from raw readings into a **new** store path:

```sh
commoncause replay recordings/f1-fixture.jsonl \
  --topology topologies/cubesat-bench.yaml --db board/f1-replay/store
commoncause diagnose --db board/f1-replay/store --last
commoncause matrix recordings/virtual-matrix.jsonl \
  --bench-repeats 4 --expect-count 36 --min-top-one 1 --json
```

The matrix should report `top_one: 36`, `all_causes: 36`, and `baseline: 8`.
It replays the recording with the current code; retained capture reports
identify their original source revisions. Replaying the same run into an
existing store is rejected, so choose a fresh path when repeating it.

## Run the virtual bench

This eight-second scenario uses the actual recorder and sensor drivers
with software I2C registers and UART heartbeat bytes. It injects and clears
a modeled regulator fault, then leaves raw telemetry and a persistent graph.
No board dependencies are needed.

```sh
commoncause run --virtual-bench --scenario sim/scenarios/f1.json \
  --run virtual-f1 --db board/virtual-f1/store \
  --recording board/virtual-f1/capture.jsonl --tui
commoncause matrix board/virtual-f1/capture.jsonl --expect-count 1 --min-top-one 1
```

Use new output paths for another capture. The [virtual bench guide](docs/virtual-bench.md)
covers interactive F1–F9 controls and the full matrix. The
[live browser guide](docs/live-browser.md) adds a read-only HTTP connection;
the [recovery guide](docs/virtual-recovery.md) demonstrates simulated bus
clear, fresh-telemetry verification, and an ineffective recovery attempt.

## Where the data lives

| Input or graph | Purpose |
| --- | --- |
| [recordings/f1-fixture.jsonl](recordings/f1-fixture.jsonl) | Small synthetic regulator dropout |
| [data/common-cause.rl](data/common-cause.rl) | Persistent F1 graph used by the default CLI and MCP configuration |
| [downlink/common-cause.json](downlink/common-cause.json) | Matching F1 graph for browser import |
| [recordings/virtual-matrix.jsonl](recordings/virtual-matrix.jsonl) | Raw readings and markers from 36 live virtual injections |
| [data/virtual-matrix.rl](data/virtual-matrix.rl) | Persistent graph with all 36 resolved episodes |
| [downlink/virtual-matrix.json](downlink/virtual-matrix.json) | Matching recorded-session browser export |

With the optional [Relate CLI](https://relatedb.ai/docs/get-started/install/)
installed, inspect the committed graph directly:

```sh
relate --database data/common-cause.rl --read-only \
  'MATCH (d:Diagnosis)-[s:SUSPECTS]->(c) RETURN d.id, c.id, s.score ORDER BY s.rank'
```

`commoncause downlink --db board/f1-replay/store --out board/f1-downlink`
also requires that CLI on `PATH`. It clones a frozen `.rl` and exports JSON
from that same snapshot, including while the source recorder remains active.
Raw recordings, historical snapshots, and result manifests are retained
for reproducibility; rebuilding does not overwrite them.

## Results and limits

| Simulated input | Correct complete cause set | First-failed-device baseline |
| --- | ---: | ---: |
| Deterministic CubeSat F1–F9 | 9/9 | 2/9 |
| Deterministic quadcopter faults | 3/3 | 1/3 |
| Recorded virtual bench, four repeats of F1–F9 | 36/36 | 8/36 |

The [current replay report](docs/sampling-gap-replay-results.json) retains
all 36 correct cause sets and recoveries, with first-correct recorded-time
p50/p95 of **1,000/2,503 ms**. F5 initially names a regulator, then identifies
the upstream rail after heartbeat-loss evidence arrives. First verdict,
first correct verdict, native query latency, and browser rendering are
different measurements.

These are defined software models, not a general accuracy estimate. Three
seeds with four repeats exercise 108 additional bounded trials in CI.
Physical sensor behavior, electrical isolation, flight operation, and Pi
performance are unvalidated and outside this submission's scope.

The retained full-hour capture failed its healthy gate after sampling
gaps. The corrected attribution policy replays it with **zero component
diagnoses and all 19 gap events preserved**; its cadence check still fails.
This is not a new clean live-hour measurement. See
[endurance](docs/endurance.md) and [sampling-gap handling](docs/sampling-gaps.md).

## Ground view

Use Node.js 24 and npm, in addition to the Python setup above:

```sh
python -m sim.demo
npm ci --prefix ground
npm run dev --prefix ground
```

Open the local URL printed by Vite. For a production build, run
`npm run build --prefix ground`. GitHub Actions builds and deploys the
existing Pages site when frontend code or its inputs change on `main`.

To run the checks locally:

```sh
python -m pip install '.[test]'
python -m pytest -q
npm test --prefix ground
```

CI covers Linux x64/ARM64, fresh Mac/Windows installs, Relate CLI/MCP and
concurrent-reader integration, native/WASM query agreement, and Playwright
browser flows. CLI integration cases skip locally if `relate` is unavailable.
See [validation](docs/validation.md) for the workloads and platform limits.

## Further reading

| Topic | Guide |
| --- | --- |
| Topology, JSONL, downlink, and query contracts | [Interfaces](docs/interfaces.md) |
| Thresholds and missing-data confirmation | [Detection](docs/detection.md) |
| Agent inspection and concurrent reads | [MCP](docs/mcp.md), [live store](docs/live-store.md) |
| Retained measurements | [Virtual matrix](docs/virtual-matrix.md), [runtime profile](docs/runtime-profile.md) |
| Delivered scope and excluded physical work | [Plan status](docs/plan-status.md) |
| Unvalidated physical reference | [Wiring](hardware/bench-wiring.md), [bring-up](hardware/bring-up-checklist.md) |

Licensed under [Apache-2.0](LICENSE). Browser builds include third-party
license files under `licenses/`.
