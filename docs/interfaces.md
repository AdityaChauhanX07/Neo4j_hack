# Data and query interfaces

These contracts are shared by the recorder, replay, native Relate graph,
and browser ground view. The [README](../README.md) provides the first-run
commands; physical wiring remains unvalidated reference material.

## Topology

[cubesat-bench.yaml](../topologies/cubesat-bench.yaml) describes the CubeSat
model; [quadcopter.yaml](../topologies/quadcopter.yaml) exercises the same
loader and queries on another system. A device can declare a driver with
an `id`, `module`, and optional `version`. Set `heartbeat: true` on a
heartbeat channel. Sensors use 500 ms periods; the radio uses 1,000 ms.

Pass the same topology when reopening a writable store. A changed wiring
file requires a fresh store. Each run records its topology SHA-256 and
detection-config SHA-256. Set `COMMONCAUSE_CODE_SHA` to retain the producing
revision on a new run.

## Telemetry

A JSONL reading contains `run`, `seq`, `ts`, `channel`, `value`, and `ok`;
`error` and `simulated` are optional. Timestamps are epoch milliseconds.
Group readings by run and emit increasing sequence numbers with
nondecreasing timestamps. Simulation metadata must remain consistent
within a run. Virtual captures and generated fixtures set `simulated: true`.

`type: "fault"` markers label injections for evaluation and are ignored by
the diagnosis engine. An inject marker can carry `expected` component IDs;
F8 requires the affected component because its target can vary. The
[virtual bench guide](virtual-bench.md) documents the controls.

The matrix scorer reports final ranking, first-verdict time, and
`first_correct_ms` separately. The latter is elapsed recording time from
the first anomaly to the first complete correct ranking, or `null` if that
ranking never appears before the next injection. See the
[bench run guide](../hardware/bench-run.md) for the timing definitions.

## Graph export

Nodes contain `id`, `label`, and `props`. Relationships contain `type`,
`from`, `to`, and `props`; endpoints reference exported node IDs. Use
`props.id` or `props.code` for component names and Cypher lookups.

`commoncause downlink` requires the Relate CLI. It clones a persistent
single-file snapshot, then exports JSON from that clone. The
[live-store guide](live-store.md) describes concurrent followers and how
the frozen export is verified beside an active writer.

Missing-reading events can have `diagnostic: false`, `observed_ts`, and
`confirmed_ts`. These preserve capture-quality evidence without asserting
a component failure. Ranking respects confirmation time; older exports
without these fields remain compatible. `Run.gap_events` records the
count even when no diagnosis was established. See [sampling gaps](sampling-gaps.md).

## Shared queries

| Query | Parameters | Returned columns |
| --- | --- | --- |
| `rank` | `run`, `from`, `to`, `device_faults`, `exclude_devices` | `suspect`, `kind`, `covered`, `contradicted`, `score`, `covered_devices` |
| `impact` | `part` | `device`, `channels_lost` |
| `before` | `run`, `t0` | `channel`, `before`, `after`, `at` |
| `recovery` | `id` | `suspect`, `mode_id`, `failure_mode`, `procedure_id`, `procedure`, `steps`, `risk` |

Source files live in [queries/](../queries/). `rank` uses an inclusive
`from`/`to` window. Use an empty `exclude_devices` list for a full ranking;
the verdict writer excludes already covered devices when looking for a
second cause. `before` uses the two-second interval strictly before `t0`.
The browser's changes list uses a cutoff just after the first missed
reading so changes at that reading's timestamp remain visible.

[config/detection.yaml](../config/detection.yaml) supplies the default
thresholds. The [detection guide](detection.md) covers settling, per-channel
cadence, recovery, overrides, and provenance.

## Read-only agent access

[.mcp.json](../.mcp.json) starts `relate serve --mcp stdio --read-only`
against `data/common-cause.rl`. A compatible client can follow the
[operator instructions](../AGENTS.md) to explain a diagnosis using graph
IDs and linked procedures. The [MCP guide](mcp.md) gives the checked example
and the [live browser guide](live-browser.md) covers authenticated HTTP.
