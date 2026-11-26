# Runtime profile

Measured on November 26, 2026 with backend `0dcf7e9`, Python 3.11.18,
Relate Python 1.0.1, and Relate CLI 1.3.0 on shared x64 Linux. The later
guided-browser change does not alter the recorder, classifier, queries,
configuration, or topology measured here. These are laptop simulation
measurements, not Pi or electrical results.

## Healthy acquisition and live reading

The [balanced repeat](final-mode-profile.json) contains eight independent
60-second captures in this order: baseline, live, recovery, combined,
combined, recovery, live, baseline. Each mode has two observations. All eight
passed channel-health checks with zero diagnoses; every live arm completed
60 polls with zero failed polls.

| Mode | Writer CPU seconds per minute, median | Writer peak RSS, median | Total measured CPU seconds per minute, median |
| --- | ---: | ---: | ---: |
| Acquisition alone | 1.039 | 43.65 MiB | 1.039 |
| With live HTTP reading | 1.027 | 43.83 MiB | 2.385 |
| With recovery policy enabled | 1.319 | 43.88 MiB | 1.319 |
| With both | 1.190 | 43.82 MiB | 2.514 |

CPU time is user plus system time, not elapsed latency. Total CPU includes
the writer and, where present, the native Relate follower and Node reader.
Individual process RSS peaks are retained in the JSON; adding those peaks
would not measure simultaneous memory use. Two short samples per mode on
a shared host do not establish statistical significance or a general
overhead percentage.

The live reader uses the actual browser HTTP client against an authenticated
read-only native follower. It loads the initial snapshot, then polls episode,
run, latest-event, and device-impact queries at approximately 1 Hz. It does
not render a browser or include Chrome's CPU and memory. Recovery-enabled
healthy arms exercise policy checks, with no recovery action triggered.

An earlier exploratory sequence had seven healthy arms and one baseline
arm with a sampling gap and one diagnosis. That failed arm is retained in
[the pilot report](profile-pilot-gap.json) and raw input. Its sensor gaps
reached 2,909 ms while the mean cadence still rounded to about 2 Hz.
The repeated sequence above is a separate measurement, not a repair or
replacement of that failure. Neither sequence alone establishes sustained
zero-false-alarm operation.

## Recovery actions

The [recovery profile](final-recovery-profile.json) measures three effective
and three ineffective virtual I2C-1 bus-clear attempts. Each starts from a
fresh store and uses the same seven-second scenario. The persistent mode
keeps the simulated bus stuck after the action.

| Outcome | Attempts | First anomaly to attempt | Attempt to verification | Diagnosis afterward |
| --- | ---: | ---: | ---: | --- |
| Fresh telemetry verifies recovery | 3 | 1,000–1,003 ms | 1,497–1,502 ms | Resolved |
| Persistent failure | 3 | 1,000–1,003 ms | 3,000 ms timeout | Open |

All six attempts named I2C-1 at high recorded confidence. Timing comes from
the stored diagnosis and recovery-attempt timestamps. It measures model
policy and fresh-telemetry verification; no physical bus-clear operation
was performed. The healthy-mode table does not include these action costs.

## Native rank query

A fresh 100-sample query measurement on the existing 36-episode snapshot
gave a median of **6.850 ms** and p95 of **8.348 ms**. The
[native benchmark](final-rank-benchmark.json) pins that graph and source
revision. This is query execution time. It does not remeasure the matrix's
historical first-verdict or first-correct times.

## Reproduction and retained input

From the repository root on Linux, with the Python package, Node dependencies,
and the Relate CLI installed:

```sh
python -m scripts.profile_modes --duration 60 --out board/profile-modes
python -m scripts.profile_recovery --source . --out board/profile-recovery
commoncause benchmark --db data/virtual-matrix.rl --samples 100 --json
```

Use new output directories. The runners leave per-process resource reports,
raw captures, stores, and logs. `profile_modes` returns a failing status if
a completed arm has unhealthy input; its report keeps that arm. A transport
or reader startup failure is an execution error, not a measured healthy arm.

The [manifest](runtime-profile-manifest.json) identifies the retained reports,
runner sources, and compressed input with byte sizes and SHA-256 hashes.
It also records hashes of decompressed JSONL. Tests reclassify the eight
repeat captures and the failed pilot input. Resource high-water marks and
action timings remain observations of the original processes and stores;
reclassifying JSONL does not reproduce operating-system resource usage.
