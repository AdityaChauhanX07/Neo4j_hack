# Common Cause

Common Cause is a CubeSat bench demonstrator. When several sensors stop
responding, it uses their shared power and data paths to rank the components
that could explain the fault. Healthy devices help rule out suspects.

## Try the F1 replay

From the repository root, use Python 3.9 or later.

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

```sh
commoncause replay recordings/f1-fixture.jsonl \
  --topology topologies/cubesat-bench.yaml --db board/store
commoncause matrix recordings/f1-fixture.jsonl
commoncause downlink --db board/store --out downlink
```

Downlink uses the [Relate CLI](https://relatedb.ai/docs/get-started/install/).
The writer uses a directory store on the board. The downlink command clones an
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

## Try another topology

The quadcopter fixture uses the same loader and queries for the battery,
distribution rail, BEC, ESCs, motors, and sensor buses. Its generated telemetry
covers a BEC brownout, compass bus failure, and ESC 3 dropout.

```sh
python sim/quad.py > /tmp/commoncause-quad.jsonl
commoncause matrix /tmp/commoncause-quad.jsonl --topology topologies/quadcopter.yaml
```

## Ground view

The browser opens the bundled F1 fixture or a JSON downlink. It reconstructs
the graph with the bundled Relate WASM package and runs the shared Cypher
queries locally. The console supports graph reads and reports a validation
error for operators it cannot verify as read-only. [Live ground view](https://adityachauhanx07.github.io/Neo4j_hack/)

```sh
npm ci --prefix ground
npm run dev --prefix ground
```

GitHub Actions builds a downloadable `ground-preview` artifact on ground-view
pull requests. To publish the site, set **Settings**, **Pages**, **Source** to
**GitHub Actions**. A push to `main` with ground view, query, or downlink changes
then builds and deploys the site.

## Bench validation

The [bench wiring guide](hardware/bench-wiring.md) covers the Pi 4 hardware
map and the Pico heartbeat. The [bench run guide](hardware/bench-run.md)
covers the raw recorder, the first physical F1 episode, and the 36-injection
matrix. CI verifies the synthetic fault cases, driver register conversions,
and capture behavior on x64 and ARM64 Linux.
