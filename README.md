# Common Cause

Common Cause is a fault diagnosis demo for a simulated CubeSat. When several
sensors stop responding, it uses their shared power and data paths to rank
the components that could explain the fault. Healthy devices help rule out
suspects.

The complete demo runs in a browser or on a laptop, using generated
telemetry with a real Relate graph. No bench equipment is required.
Physical capture is an optional extension and has not been validated on
hardware.

## How it uses Relate

The graph connects devices to their power rails, regulators, buses, and
drivers. Telemetry events link to channels and devices. Diagnoses link to
the events behind each verdict and to matching recovery procedures.
Cypher traversals rank shared dependencies by the failed devices they
explain and the healthy devices that contradict them.

Python embeds Relate for ingestion and replay. A directory store keeps
the writable graph between runs, and a single-file snapshot at
`data/common-cause.rl` lets judges inspect the bundled F1 replay. The browser
loads an exported graph into in-memory Relate WASM so the ground view can
run Cypher locally. The same loader and query files support both the
CubeSat and quadcopter examples.

## Try the browser demo

Open the [live ground view](https://adityachauhanx07.github.io/Neo4j_hack/)
and choose a fault from **Case**. The ground view reconstructs the
graph with embedded Relate WASM and runs the shared Cypher queries locally.
Start with the regulator dropout, then open the
[combined regulator and bus fault](https://adityachauhanx07.github.io/Neo4j_hack/?case=cubesat%3AF9)
to see a diagnosis with two suspects. A JSON downlink can also be opened from
disk. The console accepts read-only graph queries.

| Simulation | Cases | Correct first suspect | First failed device |
| --- | ---: | ---: | ---: |
| CubeSat | 9 | 9/9 | 2/9 |
| Quadcopter | 3 | 3/3 | 1/3 |

These counts come from deterministic simulated telemetry. The baseline
picks the first device that reports a failure. The combined case also shows
the second ranked suspect. Use **Download simulated readings** to get the
JSONL for the selected suite. The [demo walkthrough](docs/demo.md) covers a
laptop-only run and the commands to reproduce both scores.

## Try the F1 replay

From the repository root, use Python 3.9 or later.
CI tests Python 3.9, 3.11, and 3.13 on x64 Linux, and Python 3.11 on ARM64 Linux.

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install '.[test]'
commoncause diagnose --last
commoncause explain dx:f1-fixture:1
commoncause impact REG_B
python -m pytest -q
```

The checked-in graph is built from `recordings/f1-fixture.jsonl`, a synthetic
regulator dropout. Its verdict points to `REG_B`, which covers three sensor
failures with zero healthy devices downstream. Read the diagnosis, its original
telemetry, and its recovery procedure with the commands above.

To build the graph again from the raw readings, use a new store path.
For the export command, first install the
[Relate CLI](https://relatedb.ai/docs/get-started/install/) and check that
`relate --version` runs in the same shell.

```sh
commoncause replay recordings/f1-fixture.jsonl \
  --topology topologies/cubesat-bench.yaml --db board/store
commoncause matrix recordings/f1-fixture.jsonl
commoncause downlink --db board/store --out downlink
```

Replay writes a directory store. The downlink command clones an
inspectable `.rl` file and exports JSON from the same snapshot. The repository
includes a fixture bundle at `data/common-cause.rl` and its JSON export at
`downlink/common-cause.json`.

```sh
relate --database data/common-cause.rl --read-only \
  'MATCH (d:Diagnosis)-[s:SUSPECTS]->(c) RETURN d.id, c.id, s.score ORDER BY s.rank'
```

## Board and ground interfaces

- **Wiring.** `topologies/cubesat-bench.yaml` describes the bench model. A device
  can declare a driver with an `id`, `module`, and optional `version`. Set
  `heartbeat: true` on a heartbeat channel. Pass the same topology file when
  reopening a store. Use a fresh store for a changed wiring file.
- **Telemetry.** `commoncause run --hardware hardware/cubesat-pi4.yaml
  --db board/store --tui` captures and diagnoses on the Pi. Give it
  `--recording` to save the raw stream. A reading has `run`, `seq`, `ts`,
  `channel`, `value`, `ok` and optional `error`. The timestamp is epoch milliseconds.
  Group readings by run and emit them with increasing sequence numbers and
  nondecreasing timestamps. The terminal view shows device status and paths
  from affected devices to each suspect. The matrix scorer uses `type: "fault"` injection
  markers. Use `expected` on a marker when the expected part varies by test.
- **Export.** Nodes contain `id`, `label`, and `props`. Relationships contain
  `type`, `from`, `to`, and `props`. Endpoints reference exported node IDs.
  For display or Cypher lookups, use the original `props.id` or `props.code`.
- **Provenance.** Each run stores its topology SHA-256. Set
  `COMMONCAUSE_CODE_SHA` to include the revision used to produce the verdicts.
- **MCP.** `.mcp.json` points a compatible client at the fixture graph with
  `relate serve --mcp stdio --read-only`. The ground agent follows
  `AGENTS.md` to explain a verdict from its graph evidence.

The shared queries live in `queries/`.

| Query | Parameters | Returned columns |
| --- | --- | --- |
| `rank` | `run`, `from`, `to`, `device_faults`, `exclude_devices` | `suspect`, `kind`, `covered`, `contradicted`, `score`, `covered_devices` |
| `impact` | `part` | `device`, `channels_lost` |
| `before` | `run`, `t0` | `channel`, `before`, `after`, `at` |
| `recovery` | `id` | `suspect`, `mode_id`, `failure_mode`, `procedure_id`, `procedure`, `steps`, `risk` |

Use an empty `exclude_devices` list for a full ranking. The verdict writer
reranks with covered devices excluded when a second fault may explain the
remaining failures.

The recorder's clock drives detection. The daemon waits 1 second after the
first anomaly, records every anomaly and status change, and keeps steady OK
samples at 1 Hz. A noisy channel becomes stuck after 10 identical readings.
Stale samples are detected after three periods, heartbeat loss after 3
seconds, and undervoltage below 90% of nominal. Recovery takes three
consecutive OK readings on each affected channel.

`commoncause matrix` reports the final ranking and the time to the first
fully correct verdict separately. Its `first_correct_ms` field uses elapsed
recording time from the first anomaly, with `null` for an injection that
never reaches the expected ranking. The [bench run guide](hardware/bench-run.md)
defines the timing fields and the optional measurements to collect on the Pi.

## Try another topology

The quadcopter fixture uses the same loader and queries for the battery,
distribution rail, BEC, ESCs, motors, and sensor buses. Its generated telemetry
covers a BEC brownout, compass bus failure, and ESC 3 dropout.

```sh
python sim/quad.py > /tmp/commoncause-quad.jsonl
commoncause matrix /tmp/commoncause-quad.jsonl --topology topologies/quadcopter.yaml
```

## Ground view

Use Node.js 24 and npm. With the Python environment set up, build the
simulated downlinks before starting Vite.

```sh
python -m sim.demo
npm ci --prefix ground
npm run dev --prefix ground
```

GitHub Actions builds a downloadable `ground-preview` artifact on ground-view
pull requests. A push to `main` with changes to the demo or its inputs builds
and deploys the site through GitHub Pages.

## Optional hardware setup

The demo and both simulation suites run on a laptop. The
[bench wiring guide](hardware/bench-wiring.md) describes the Pi 4 hardware
map and Pico heartbeat for future physical validation. The
[bench run guide](hardware/bench-run.md) covers the recorder and procedures
for collecting a healthy capture, an F1 episode, and a physical fault matrix.

Install `.[board]` to use the Pi recorder. `commoncause check-capture` checks
channel health and sampling cadence before an injection. Direct capture
records time through the first committed verdict, which
`commoncause benchmark` reports alongside native query latency. CI checks
synthetic fault replays, register conversions, and capture behavior with
simulated I/O on x64 and ARM64 Linux.
