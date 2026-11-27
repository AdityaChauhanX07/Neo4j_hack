# Virtual bench

The virtual bench runs the existing sensor drivers, polling threads,
heartbeat decoder, recorder, and Relate diagnosis pipeline on a laptop.
Software transports supply sensor registers and serial bytes. It needs
Python 3.9 or later and the normal package dependencies; no Pi, physical
sensors, `smbus2`, `pyserial`, or administrator access is required.

Run commands from the repository root with the Python environment active.

```sh
python -m pip install '.[test]'
```

## Try an eight-second session

Use new output paths for each capture. Stores and recordings are retained
for later inspection.

```sh
commoncause run --virtual-bench --scenario sim/scenarios/f1.json \
  --run virtual-f1 --db board/virtual-f1/store \
  --recording board/virtual-f1/capture.jsonl --tui
commoncause diagnose --db board/virtual-f1/store --last
commoncause matrix board/virtual-f1/capture.jsonl --expect-count 1 --min-top-one 1
```

The scenario disconnects the modeled `REG_B` at 2 seconds, restores it at
5 seconds, and stops at 8 seconds. Expect `REG_B` with three affected
devices, voltage sag on the monitor, and a resolved episode. Terminal
output identifies the readings as simulated.

## Operate the fault controls

```sh
commoncause run --virtual-bench --interactive --tui \
  --db board/virtual-live/store --recording board/virtual-live/capture.jsonl
```

Allow healthy readings to appear, then type `F1 inject`. Leave the fault
active for several seconds before typing `F1 clear`. Wait for the verdict
to resolve before the next injection. Enter `quit` to stop.

| Command | Modeled effect |
| --- | --- |
| `F1 inject` | Disconnect `REG_B` and lower its monitored voltage |
| `F2 inject` | Stop replies on `I2C-1` |
| `F3 inject` | Stop replies on `I2C-3` |
| `F4 inject` | Disconnect `sun2` |
| `F5 inject` | Lose `RAIL_5V`, including the regulator's devices and radio heartbeat |
| `F6 inject` | Stop UART heartbeat bytes |
| `F7 inject` | Suppress the configured driver channel, `imu.gyro` by default |
| `F8 inject sun2` | Alternate replies and failures for the named I2C device |
| `F9 inject` | Disconnect `REG_B` and stop replies on `I2C-3` together |

Use the same fault code followed by `clear` to restore it. F8 accepts one
configured I2C device; heartbeat loss uses F6. Multiple fault controls can
be active together. The expected cause fields label the scoring target;
the diagnosis code reads telemetry and graph dependencies.

F5 may initially name `REG_B`, then change to `RAIL_5V` after the missing
heartbeat is detected. F6 also needs the heartbeat timeout. Leave those
faults active for at least five seconds. Recovery requires three healthy
readings on each affected channel, so allow extra time for the 1 Hz radio.

The console polls input without blocking acquisition while a line is being
typed. POSIX terminals use `select`; Windows consoles use `msvcrt`.
Windows key handling has a test double, while full live CI runs on Linux.
Timed scenarios provide a terminal-independent alternative.

## Run the complete matrix

```sh
commoncause run --virtual-bench --scenario sim/scenarios/f1-f9.json \
  --run virtual-matrix --db board/virtual-matrix/store \
  --recording board/virtual-matrix/capture.jsonl --tui
commoncause matrix board/virtual-matrix/capture.jsonl \
  --bench-repeats 1 --min-top-one 1 --json
```

This takes about a minute and covers all nine faults with recovery between
episodes. Expected results are nine correct full cause sets and nine
resolved episodes, including both F9 causes. The test compares the first
correct verdict with the first verdict on F5. CI saves the captured JSONL
and matrix report in the `virtual-bench-session` artifact.

`commoncause benchmark --db board/virtual-matrix/store` measures rank-query
latency and first-commit timing on the host running the model. Its text and
JSON reports retain the simulation label. These are laptop measurements.

A scenario is a JSON list of `{ "at": seconds, "command": text }` objects.
Times must be nonnegative and in order, and the last command must be the
only `quit`. `--scenario` is available with `--virtual-bench` and cannot be
combined with `--interactive`. Invalid commands fail the scripted run.

## Record without diagnosis

```sh
commoncause record --virtual-bench --scenario sim/scenarios/f1.json \
  --run virtual-recording --out board/virtual-recording.jsonl
```

The recorder also accepts `--device` for one sensor, `--duration` for a
bounded capture, and `--out -` for JSONL on stdout. Status messages use
stderr. `--hardware` can select another hardware map with the CubeSat
topology, including matching HMC5883L chip and topology edits. Adapter
numbers and addresses come from that map; the virtual mode never opens
the named device files.

## Replay and open the captured graph

Install the [Relate CLI](https://relatedb.ai/docs/get-started/install/)
before exporting. Replay into a new store to inspect the same raw input.

```sh
commoncause replay board/virtual-f1/capture.jsonl \
  --topology topologies/cubesat-bench.yaml --db board/virtual-f1/replayed
commoncause downlink --db board/virtual-f1/replayed --out board/virtual-f1/downlink
```

Open the [ground view](https://adityachauhanx07.github.io/common-cause/) and
choose the exported `board/virtual-f1/downlink/common-cause.json` file.
Its source label reads **Simulated bench**. The diagnosis, timeline,
dependency paths, healthy-device contradictions, and Cypher console use
that imported graph.

Every virtual JSONL row has `simulated: true`. Replay retains that flag on
the Run node, and downlink retains it in the exported graph. A replay
rejects inconsistent simulation flags within a run. Existing unlabelled
recordings keep their original format; their import label makes no claim
that the data came from physical hardware.

## What the checks establish

The driver tests cover reference calibration, chip identification,
register conversion, changed adapter numbers, alternate magnetometer
addresses, NACK-style failures, raw light-sensor reads, and fragmented UART
frames. The complete session exercises live capture, fault controls,
committed diagnosis, recovery, recording, scoring, and replay. Browser CI
imports a newly captured and replayed virtual episode.

Independent unlabelled scenarios in `tests/test_uncertainty.py` cover
delayed correlated failures, missing driver samples, and a power fault
that stays at medium confidence until healthy radio evidence rules out
the upstream rail. New healthy context refreshes an existing verdict.

This is a register and protocol model. It does not measure electrical
isolation, back-powering, bus signal integrity, sensor accuracy, or Pi
performance. The virtual UART generates the firmware's byte protocol in
Python; it does not execute the Pico firmware.
