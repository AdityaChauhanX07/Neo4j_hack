# Bench replay and measurements

Use 64-bit Raspberry Pi OS and the bench's confirmed topology. Follow the
[Pi 4 wiring guide](bench-wiring.md) and update `cubesat-pi4.yaml` to match
the devices on the board. Run the synthetic checks on the Pi before
collecting the physical fault matrix.

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install '.[board]'
python sim/bench.py > /tmp/commoncause-bench-fixtures.jsonl
commoncause matrix /tmp/commoncause-bench-fixtures.jsonl --bench-repeats 1 --min-top-one 1
commoncause benchmark --samples 100
```

## Check the channels

During bring-up, use `--device` to check one sensor without running the
diagnosis. The radio probe should show a new counter each second.

```sh
commoncause record --device imu --duration 6 --out -
commoncause record --device radio --duration 6 --out -
```

Then save ten minutes of healthy telemetry. The writer records one line
per channel, with an increasing sequence number and a timestamp in Unix
milliseconds. The check reports all 11 channels, their observed cadence,
the longest gap, and hardware faults. The 595-second floor allows for
startup and the time between the final reading and capture shutdown.
Capture commands open new output files and refuse an existing path.

```sh
commoncause run --db board/store --hardware hardware/cubesat-pi4.yaml \
  --recording recordings/bench-healthy.jsonl --duration 600 --tui
commoncause check-capture recordings/bench-healthy.jsonl --min-seconds 595 --min-rate 0.9
```

## Record the first F1 episode

Start a new capture. Wait for healthy readings, enter `F1 inject`, and
open the switch at the regulator input. Check that the top suspect is
`REG_B` and the voltage monitor reports undervoltage. Restore the switch,
enter `F1 clear`, and wait until the verdict resolves. Enter `quit` to
finish the recording.

```sh
commoncause run --db board/store --hardware hardware/cubesat-pi4.yaml \
  --recording recordings/bench-f1.jsonl --interactive --tui
commoncause matrix recordings/bench-f1.jsonl --expect-count 1 --min-top-one 1
commoncause benchmark --db board/store --samples 100
```

For raw capture without a graph, use `commoncause record --out` with a new
path. Add `--interactive` to record the same markers. The stdin mode of
`commoncause run` can still read a JSONL stream from an external recorder.

## Score the physical matrix

In the interactive capture, enter an injection and clear marker for each of
the nine faults, four runs per fault. Let each episode resolve before the
next injection. Supply an expected component when it varies, for example
`F8 inject sun2`. Record F9 as a single combined injection. F7 pauses the
configured driver channel until `F7 clear`, so its stale report comes from
the diagnosis rather than a fabricated sensor reading.

```sh
commoncause run --db board/store --hardware hardware/cubesat-pi4.yaml \
  --recording recordings/bench-run.jsonl --interactive --tui
commoncause matrix recordings/bench-run.jsonl --bench-repeats 4 --min-top-one 0.9 --json
commoncause benchmark --db board/store --samples 100 --json
commoncause downlink --db board/store --out downlink
```

The scorer reports top-1, the first-failed-device baseline, and coverage of
all expected causes. For F9, inspect both ranked causes. The recorded
time to verdict uses the timestamps in the JSONL replay.

Direct Pi capture also records the elapsed time from the first observed
anomaly through the first committed verdict. The benchmark reports
p50 and p95 for those live episodes in the selected diagnosis's run.
It times the warm native rank query separately on the machine running the
benchmark and reports the store size. Use `--id` to select a diagnosis
from a specific run. Run the benchmark on the Pi for Pi query timings.

Use the same topology when replaying sessions and a fresh store after
changes to the wiring.
