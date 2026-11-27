# Detection configuration

`config/detection.yaml` contains the shared detection and retention
thresholds. The installed wheel includes the same file. Channel bounds,
sampling periods, heartbeat flags, and monitored parts remain in the
topology YAML.

| Setting | Default | Meaning |
| --- | ---: | --- |
| `stuck_samples` | 10 | Consecutive identical successful readings on a `noisy: true` channel |
| `stale_periods` | 3 | Missing-reading timeout in channel periods |
| `heartbeat_timeout_ms` | 3000 | Missing heartbeat timeout |
| `undervoltage_ratio` | 0.9 | Minimum fraction of the monitored regulator's nominal voltage |
| `settle_ms` | 1000 | Wait after an explicit anomaly; confirm inferred gaps from their observation time |
| `recovery_samples` | 3 | Consecutive OK samples needed on every affected channel |
| `ok_interval_ms` | 1000 | Interval for retaining steady OK events in the graph |

To use another complete config, copy the file, edit its values, and start
a new process with its path:

```sh
COMMONCAUSE_DETECTION_CONFIG=/absolute/path/detection.yaml commoncause replay \
  recordings/f1-fixture.jsonl --topology topologies/cubesat-bench.yaml \
  --db board/custom-detection/store
```

In PowerShell, set `$env:COMMONCAUSE_DETECTION_CONFIG` before invoking the
command. Use a new store and retain the config with the recording. New Run
nodes record `detection_sha`, the SHA-256 of the UTF-8 config text with line
endings normalized to LF. Replay, health checks, and live acquisition use
the same rules loaded at process startup. Old runs without the hash remain
readable; they do not gain retrospective provenance.

All counts and times must be positive integers. The undervoltage ratio
must be finite, greater than zero, and no greater than one. The whole
seven-field config is required so a partial override cannot silently
inherit an unexpected threshold.

## Missing readings

The classifier still records `STALE` after three sample periods and
`HEARTBEAT_LOST` after three seconds. The event timestamp is the missed
deadline. `check-capture` reports the gap as unhealthy even if later
readings are normal.

Component attribution is a separate decision. New inferred gaps start
with `diagnostic: false` and an `observed_ts` timestamp. A gap becomes
eligible fault evidence only if the channel remains missing for `settle_ms`
after that observation. Confirmation sets `diagnostic: true` and
`confirmed_ts`. A new reading is processed before confirmation at that
timestamp, so a reading arriving on the boundary can clear the pending gap.
Explicit read errors and abnormal values follow their normal episode path.

Ranking ignores unconfirmed gaps and confirmations later than its `$to`
window. Older graphs without these properties retain their original
interpretation. Replay raw telemetry to apply the new policy; importing an
old snapshot does not reclassify it or erase its recorded diagnoses.

New Run nodes store `gap_events` and `gap_confirmation_ms`. The evidence
workspace shows a missing-reading notice even when no component diagnosis
was established. The [sampling-gap notes](sampling-gaps.md) explain the
regression input and timing implications.

## Stuck readings

Stuck detection is opt-in per channel. Set `noisy: true` only for a channel
whose normal readings should vary. Constant calibration responses in the
default virtual register model are intentional, so the supplied topology
leaves this flag off. A stationary sensor can also legitimately repeat a
value; enabling the rule needs a channel-specific reason.

The end-to-end stuck-sensor test loads a topology with `imu.gyro` marked
noisy, supplies changing healthy values, holds one value for ten readings,
and then restores changing values. It must diagnose `imu` with `STUCK`
evidence and resolve after three healthy samples. The input has no fault
labels. This verifies the capability without treating the virtual model's
constant reference registers as a physical measurement of sensor noise.
