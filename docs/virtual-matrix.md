# Recorded virtual fault matrix

This bundle contains a live, approximately four-minute laptop session:
four repetitions of F1 through F9, captured through the sensor drivers and
recorder with software I2C and UART transports. It is entirely simulated.
The default F1 fixture remains the small starting example; this separate
bundle retains the complete 36-injection session.

Open **Evidence workspace** in the browser and choose **Open 36-fault session**. It loads
the committed JSON export on demand. The source is **Simulated bench**;
the episode selector contains all 36 resolved episodes. The latest episode
is the combined regulator/bus fault. File import supports the same JSON.

| File | Content |
| --- | --- |
| `recordings/virtual-matrix.jsonl` | Every raw reading and injection/clear marker |
| `data/virtual-matrix.rl` | Persistent, inspectable graph after the complete session |
| `downlink/virtual-matrix.json` | Matching graph for browser import |
| `docs/virtual-matrix-results.json` | Per-injection scoring and recorded-time summaries |
| `docs/virtual-matrix-benchmark.json` | Query and first-commit timing on this host |
| `docs/virtual-matrix-manifest.json` | Source, topology/config hashes, file sizes and hashes |
| `sim/scenarios/matrix-36.json` | Timed controls for another live session |

## Measured results

| Check | Result |
| --- | --- |
| Correct top cause | 36/36 |
| Correct full cause set | 36/36 |
| First-failed-device baseline | 8/36 |
| Reached the first fully correct verdict | 36/36 |
| Resolved after clearing | 36/36 |
| Recorded time to first correct verdict, p50 / p95 | 1,000 / 2,503 ms |
| Warm rank query, 100 samples, p50 / p95 | 9.160 / 11.749 ms |
| Persistent `.rl` bundle | 188,416 bytes |

These are results for the defined software models on a shared x64 Linux
host running Python 3.11.18. Scheduling and recording order vary between
live runs. They do not estimate arbitrary fault accuracy or Pi performance.
The query benchmark uses this larger 36-episode graph; it is a different
workload from the small F1 fixture's earlier timing.

F5's initial regulator verdict precedes its correct rail verdict because
heartbeat loss takes longer to observe. The report retains the first
verdict and first-correct times separately. No blanket under-two-second
claim is made for all fault types.

The [current confirmation policy](sampling-gaps.md) preserves all 36 cause
sets on replay but can increase missing-telemetry verdict times. Current
replay first-correct p50/p95 is 1,001/3,503 ms; the table above belongs to
the original capture and source revision.

## Reproduce or inspect

With the Python package installed:

```sh
commoncause matrix recordings/virtual-matrix.jsonl \
  --bench-repeats 4 --expect-count 36 --min-top-one 1 --json
commoncause replay recordings/virtual-matrix.jsonl \
  --topology topologies/cubesat-bench.yaml --db board/matrix-replay/store
commoncause diagnose --db board/matrix-replay/store --last
```

With the Relate CLI installed, inspect the committed file directly:

```sh
relate --database data/virtual-matrix.rl --read-only \
  'MATCH (dx:Diagnosis)-[s:SUSPECTS]->(c) RETURN dx.id, dx.state, c.id, s.rank ORDER BY dx.id, s.rank'
```

To capture a new live virtual matrix, use new output paths:

```sh
commoncause run --virtual-bench --scenario sim/scenarios/matrix-36.json \
  --run my-virtual-matrix --db board/matrix-live/store \
  --recording board/matrix-live/capture.jsonl
```

The bundle tests verify all hashes, compare the `.rl` with its JSON export,
check the 36 persisted rankings against the independent Python scorer,
and rescore the raw input. Browser CI opens the recorded session, changes
episodes, and restores the original fixture. Git attributes preserve LF
line endings for hashed text artifacts across platforms.
