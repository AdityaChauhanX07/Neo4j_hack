# Software validation

All telemetry in these checks is simulated. The tests exercise the actual
Relate database, shared Cypher, recorder, and diagnosis pipeline. They do
not establish sensor accuracy, wiring safety, or Raspberry Pi performance.
The [original-plan status](plan-status.md) maps the delivered software to
that plan and identifies deferred physical work.

## Current checks

The Python suite contains 110 test cases. CI runs Python 3.9, 3.11, and
3.13 on x64 Linux and Python 3.11 on ARM64 Linux. Fresh non-editable Python
3.11 installs also run on hosted macOS ARM64 and Windows x64, without board
extras. Platform-specific errno and PTY tests are skipped where unavailable.

Four integration tests require the Relate CLI. Python-only jobs skip them;
the Linux Ground view job and the Mac integration step run them with the
installed CLI. Seven WASM tests, three HTTP-client tests, three walkthrough-data
tests, and fifteen browser checks cover the ground view,
including a newly exported capture, the published 36-episode graph, episode
switching, loading races, rejected writes, the guided fault-to-recovery flow,
keyboard controls, and small-screen layout.

| Area | Evidence |
| --- | --- |
| Independent ranking | A plain Python dependency-set specification agrees with every candidate's order, score, coverage, and contradictions across F1–F9, early/final windows, exclusion passes, the quadcopter, unknown devices, and run/time boundaries |
| Live virtual bench | Actual drivers and recorder cover F1–F9, both F9 causes, heartbeat delay, healthy startup, simulation provenance, and recovery |
| Uncertainty | Unlabelled delayed failures, missing telemetry, ambiguous power evidence, and stuck-sensor recordings |
| MCP | Actual stdio initialization, schema/tool discovery, linked facts, valid citation IDs, preserved medium confidence, and refused mutations with an unchanged snapshot hash |
| Concurrent readers | A live MCP follower sees later commits while cloning produces matching, frozen `.rl` and JSON content beside an active recorder |
| Live browser | An authenticated HTTP follower observes a real Python writer through healthy telemetry, F1, recovery, rejected mutations, connection loss, and disconnect |
| Simulated automatic recovery | Both I2C buses, ineffective recovery, incomplete verification, unsafe-candidate refusal, physical-mode rejection, and retained graph evidence |
| Detection config | Shared packaged defaults, rejected invalid values, custom settle timing, and a config hash on new Run nodes |
| Published matrix | Raw recording preserves published causes, with timing changes documented; every persisted ranking agrees with the independent scorer; hashes and export content match |
| Runtime profile | Eight balanced healthy captures, six recovery attempts, native query timing, and a retained failed pilot; source and recording hashes with raw-input reclassification |

Reproduce the Python checks with `python -m pytest -q` after installing
`.[test]`. See the [laptop guide](laptop-install.md), [MCP guide](mcp.md),
[live-store guide](live-store.md), and [detection guide](detection.md) for
the corresponding commands and platform limits.

## Recorded virtual matrix

The [published bundle](virtual-matrix.md) contains four live repetitions of
all nine modeled faults: 36 correct full cause sets, 36 recoveries, and an
8/36 first-failed-device baseline. It retains raw JSONL, an inspectable
persistent `.rl`, matching browser JSON, scoring, query benchmarks, and a
[file-hash manifest](virtual-matrix-manifest.json). The browser loads this
larger graph on demand through **Open 36-fault session**.

The manifest identifies the capture's source revision, topology, config,
interpreter, and host. The report distinguishes the first verdict from the
first fully correct ranking. F5 can initially name the regulator and only
identify the upstream rail after heartbeat-loss evidence arrives. Report
those separate times; a first verdict is not necessarily a correct one.

The native query benchmark uses the 36-episode graph on this shared x64
Linux host. It is a different workload from the earlier F1 fixture timing
below, and neither result measures Pi performance.
The [runtime profile](runtime-profile.md) adds a fresh 100-sample native
query measurement and separates reader overhead from browser rendering.

## Bounded varied simulations

Three seeds with four repeats each produced 108 generated fault trials.
All 108 reached the correct full cause set and resolved. Twelve separate
healthy generated runs produced no diagnosis. Replaying without injection
labels must preserve the causes, keeping expected answers outside the
diagnosis path.

The generator bounds are:

- Fault start: 1,000 to 2,500 ms in 500 ms steps.
- Fault duration: 4,000 to 8,000 ms in 500 ms steps.
- Recovery observation: 3,000 to 5,000 ms after clearing.
- Frame timestamp jitter: up to 75 ms, preserving order.
- Sensor noise: uniform, up to 2% of `max(abs(value), 1)`.
- Heartbeat: increasing counter at nominal 1 Hz with frame jitter.
- Sample order: shuffled within each frame.

| Seed | Full cause set | Resolved | First correct p50 | First correct p95 |
| --- | ---: | ---: | ---: | ---: |
| 7 | 36/36 | 36/36 | 1,457 ms | 2,643 ms |
| 42 | 36/36 | 36/36 | 1,133 ms | 2,089 ms |
| 2026 | 36/36 | 36/36 | 1,110 ms | 2,530 ms |

Each seed's baseline scored 8/36. These are historical bounded-simulation
measurements, not an estimate of arbitrary real-world accuracy. The
[seed summary](simulation-results.json) pins their generator, recording,
topology, and source hashes. Reproduce using that recorded version:

```sh
python sim/bench.py --seed 42 --repeats 4 > /tmp/commoncause-varied.jsonl
commoncause matrix /tmp/commoncause-varied.jsonl --bench-repeats 4 --min-top-one 1 --json
```

Current CI reruns seed 42 and retains its JSONL/report as the
`simulated-fault-matrix` artifact. Healthy controls and label-free replay
are covered in `tests/test_simulation.py`.

## Earlier clean F1 measurement

A fresh checkout at `3d5ef2f` used Python 3.9.25, a non-editable install,
Relate CLI 1.3.0, and `relate-db==1.0.1`, without board packages. Its F1
replay named `REG_B`, resolved at high confidence, and exported 108 nodes
and 206 relationships.

| Historical check | Result |
| --- | --- |
| Deterministic CubeSat fixtures | 9/9 cause sets; baseline 2/9 |
| Deterministic quadcopter fixtures | 3/3 cause sets; baseline 1/3 |
| CubeSat first correct, recorded-time p50 / p95 | 1,000 / 2,500 ms |
| Warm F1 rank query, 100 samples, p50 / p95 | 1.779 / 2.057 ms |
| F1 directory store on that host | 20,382 bytes |

These figures belong to that small input and revision. Later suite sizes
and larger graph benchmarks do not replace their measurement context.

## Issues found by validation

New healthy-device evidence originally left an existing diagnosis's
confidence unchanged. The engine now refreshes the verdict when that
context rules out a competing dependency. Unlabelled regression recordings
cover both a previously unseen radio and one seen before the fault.

The first Mac matrix run exposed aliasing between the intermittent model's
half-second transitions and the 2 Hz polling boundary. A regression case
covers three affected boundaries; virtual reply windows now alternate
every 0.75 seconds.

A later Mac run exposed a Relate 1.0.1 native panic when a delayed frame
caused several verdict replacements inside one transaction. A small local
reproduction confirmed deletion of relationships created earlier in the
same transaction triggered it. Ingestion now applies all gap and sample
evidence before writing one verdict for the observed frame. The regression
case preserves each gap's timestamp while committing its verdict at the
actual observation time. No native exception is swallowed or retried.

The Mac recovery check also exposed a test observation window that could
end capture before the three-second verification timeout completed. The
integration test now allows 7.5 seconds for detection and verification,
still requires the persistent failure to remain open, and checks that the
attempt observed the complete timeout. Capture ending early continues to
produce `unverified`; the separate shutdown test preserves that behavior.

## Sustained operation

The [endurance runner](endurance.md) measures a real-clock healthy virtual
capture with minute memory/store checkpoints, channel cadence checks, raw
recordings, and source hashes. Its result is specific to the measured
revision and host. A generated hour of timestamps is not equivalent to an
hour of live acquisition.

The ten-minute recording verifies 2 Hz sensor channels and a 1 Hz radio
with no diagnosis. The completed one-hour report records peak RSS and
store growth separately from the compact downlink size. Physical power
loss, electrical isolation, and Pi resource figures remain unmeasured.

The recorded hour completed in 3,600.445 seconds, retained 33,772 events,
and opened no diagnosis. Peak acquisition RSS was 110.85 MiB; the closed
directory store was 1.54 MiB. The [report](endurance-results.json) identifies
the measured source revision, which predates the later fault-path fix.
Compressed raw inputs and their [manifest](endurance-manifest.json) are
committed, and the current suite rechecks both their hashes and channel
health without waiting another hour.

The new current-backend hour at `0dcf7e9` completed in
3,600.406 seconds, but **failed** its healthy-operation gate:
3 diagnoses opened after sampling gaps without fault injection.
Its first 601-second prefix is healthy. Peak acquisition RSS was
121.07 MiB and the closed store was 1.54 MiB.
The [current report](final-endurance-results.json) and
[retained-input manifest](final-endurance-manifest.json) preserve that failure;
current tests preserve its classifications and verify corrected attribution. The older clean
hour is not evidence that this new full-hour gate passed.

The [sampling-gap fix](sampling-gaps.md) now keeps inferred missing readings
out of component ranking until they remain missing through an observation
confirmation interval. The saved hour replays with no component diagnosis
and all 19 gap events retained; its cadence check remains unhealthy.
Replaying the 36-injection matrix still reaches all expected cause sets,
with first-correct p50/p95 of 1,001/3,503 ms under the new policy. The
original capture timings and its failed hour report remain historical facts.
