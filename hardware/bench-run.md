# Bench replay and measurements

This guide covers the optional physical bench. The
[laptop demo](../README.md#try-the-f1-replay) uses generated telemetry and
requires no bench equipment. Physical capture has been tested with
simulated I/O only.

Use 64-bit Raspberry Pi OS and the bench's confirmed topology. Follow the
[Pi 4 wiring guide](bench-wiring.md) and update `cubesat-pi4.yaml` to match
the devices on the board. Run the synthetic checks on the Pi before
collecting the physical fault matrix. The
[bring-up checklist](bring-up-checklist.md) walks through every step at the
bench with the output to expect.

## Set up the Pi

`scripts/pi-setup.sh` takes a fresh 64-bit Raspberry Pi OS to a working
recorder. Clone the repository on the Pi, run the script as your normal
user, reboot, then run it again with `--check`.

```sh
git clone https://github.com/AdityaChauhanX07/Neo4j_hack.git common-cause
cd common-cause
scripts/pi-setup.sh
sudo reboot
cd common-cause && scripts/pi-setup.sh --check
```

The script makes these changes:

- Adds one marked block to `/boot/firmware/config.txt` with
  `dtparam=i2c_arm=on`, the I2C-3 overlay and `enable_uart=1`. The first
  edit saves a copy as `config.txt.common-cause.bak`.
- Removes the serial login console from `cmdline.txt` so UART0 carries the
  radio heartbeat.
- Loads `i2c-dev` at boot and adds you to the `i2c` and `dialout` groups.
- Installs `i2c-tools`, `python3-venv` and `git` if they are missing.
- Creates `.venv` and runs `pip install -e '.[board]'`.
- Installs the `relate` CLI in `~/.local/bin`. `commoncause downlink` needs it.

On a Pi 4, I2C-3 uses `dtoverlay=i2c3,pins_4_5`. On other models the
script uses the bit-banged `i2c-gpio` overlay on the same pins as bus 3.
Pass `--i2c3 hw` or `--i2c3 gpio` to choose one. On a model other than the
Pi 4, the script warns that `/dev/serial0` may not be GPIO 14 and 15. Check
the wiring guide before you capture.

Running the script again is safe. The marked block is rewritten in place,
and completed steps are skipped. `--check` passes when `/dev/i2c-1`,
`/dev/i2c-3` and `/dev/serial0` exist, `relate-db`, `smbus2` and `pyserial`
import, and the `relate` CLI runs.

The complete workflow on the Pi requires 64-bit Raspberry Pi OS based on
Debian 13 (trixie), the current official image. Every `relate` CLI release
for Linux arm64 needs glibc 2.39, and trixie has 2.41.

Fallback on bookworm (Debian 12, glibc 2.36): the script skips the CLI, and
capture and diagnosis still work on the Pi. To downlink, stop
`commoncause run`, copy `board/store` to a laptop and run
`commoncause downlink` on the laptop.

After the reboot, activate the environment in each new shell:

```sh
cd ~/common-cause
. .venv/bin/activate
export PATH="$HOME/.local/bin:$PATH"
```

## Check the software on the Pi

```sh
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
all expected causes. Those accuracy counts use the final stored ranking.
For F9, inspect both ranked causes.

The scorer also reports `first_correct_ms` for each injection and p50/p95
across injections that reach a correct verdict. Correct means that the
first-ranked component matches the first expected cause and the set of
suspects exactly matches the expected causes. A missing correct verdict is
reported as `null` in JSON or `never` in text and is excluded from the latency
percentiles. The `First correct verdicts` count shows the sample coverage.

`decision_ms` measures the first verdict's logical timestamp relative to
the first anomaly. `first_correct_ms` uses the recording timestamp of the
first replay frame that commits a fully correct ranking, relative to that
same anomaly. Later injections end the timing window. In the synthetic F5
case the first verdict takes 1000 ms, and the first correct verdict takes
2500 ms because the heartbeat timeout is observed on a later polling frame.
These recorded times can be reproduced from a JSONL file.

Direct Pi capture also records the elapsed time from the first observed
anomaly through the first committed verdict. The benchmark reports
p50 and p95 for those live episodes in the selected diagnosis's run.
This measures the first committed verdict regardless of its correctness.
It times the warm native rank query separately on the machine running the
benchmark and reports the store size. Use `--id` to select a diagnosis
from a specific run. Run the benchmark on the Pi for Pi query timings.

Use the same topology when replaying sessions and a fresh store after
changes to the wiring.
