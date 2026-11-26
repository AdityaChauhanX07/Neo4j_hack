# Bench bring-up checklist

This checklist applies to the optional physical bench, which has not been
validated on hardware. The [laptop demo](../README.md#try-the-f1-replay)
runs without bench equipment.

Work through this list at the bench, in order. Each step gives the command
to run and what passing output looks like. Stop at the first step that
fails and fix it before you go on. The steps cover tracker rows #6 (Pi
setup), #8 (wiring, fault switches and the back-powering check), #10 (the
first 10-minute recording) and #14 (live F1 to F5).

Run every command from the repository root on the Pi. The command defaults
point at `hardware/cubesat-pi4.yaml` and `topologies/cubesat-bench.yaml` by
relative path.

The wiring comes from [bench-wiring.md](bench-wiring.md), the plan's wiring
map, and `hardware/cubesat-pi4.yaml`. All three agree on every address
below.

| Device | Chip | Bus | Address | Supply | Channels |
| --- | --- | --- | --- | --- | --- |
| `imu` | MPU-6050 | I2C-1 | `0x68` | `REG_B` | `imu.gyro`, `imu.accel` |
| `mag` | QMC5883L | I2C-1 | `0x0d` | `REG_B` | `mag.field` |
| `epsmon` | INA219 | I2C-1 | `0x40` | `REG_A` | `eps.regb.voltage`, `eps.regb.current` |
| `thermal` | BME280 | I2C-1 | `0x76` | `REG_A` | `thermal.temp` |
| `sun1` | BH1750 | I2C-3 | `0x23` | `REG_B` | `sun1.lux` |
| `sun2` | BH1750 | I2C-3 | `0x5c` | `REG_A` | `sun2.lux` |
| `payload` | BME280 | I2C-3 | `0x77` | `REG_A` | `payload.temp`, `payload.pressure` |
| `radio` | Pico | UART0, 115200 baud | none | `RAIL_5V` | `radio.heartbeat` |

## 1. Pi setup (row #6)

- [ ] Flash **Raspberry Pi OS (64-bit)**, the release based on Debian 13
  (trixie), with Raspberry Pi Imager. Enable SSH in the Imager settings.
  Trixie is the current official 64-bit image and the only release that
  runs the whole workflow, downlink included, on the Pi. Fallback: bookworm
  runs capture and diagnosis, but not the `relate` CLI (it needs glibc
  2.39), so downlink runs on a laptop from a copied `board/store`.
- [ ] Clone and run the setup script as your normal user:

  ```sh
  git clone https://github.com/AdityaChauhanX07/Neo4j_hack.git common-cause
  cd common-cause
  scripts/pi-setup.sh
  ```

  **Pass:** it ends with `Done. Reboot to apply the boot and group changes`.
  On a Pi 4 the first line says `I2C-3 via hw`.
- [ ] `sudo reboot`, then:

  ```sh
  cd ~/common-cause
  scripts/pi-setup.sh --check
  ```

  **Pass:** every line under `== Check` starts with `ok`, and the last line
  is `Ready for hardware/bring-up-checklist.md`. `/dev/serial0` should point
  at `/dev/ttyS0` on a Pi 4 with Bluetooth enabled.
- [ ] Open the environment. Repeat this in every new shell:

  ```sh
  . .venv/bin/activate
  export PATH="$HOME/.local/bin:$PATH"
  ```

- [ ] Check the software on the Pi before any wiring:

  ```sh
  python sim/bench.py > /tmp/bench-fixtures.jsonl
  commoncause matrix /tmp/bench-fixtures.jsonl --bench-repeats 1 --min-top-one 1
  commoncause benchmark --samples 100
  ```

  **Pass:** the matrix prints `Top-1 9/9  baseline 2/9  all causes 9/9` and
  exits without an error. The benchmark prints a `Rank latency` line. Note
  its p50 and p95: they are the first Pi numbers for the README.

## 2. Power, before any sensor is connected (row #8)

Do this with the sensors unplugged and a multimeter.

- [ ] Join the grounds: the Pi GND (pin 6), the breadboard ground and the
  Pico GND.
- [ ] Keep the two positive supplies separate. `REG_A` is the Pi's 3.3 V pin
  (pin 1 or 17). `RAIL_5V` is the breadboard supply, which feeds the
  AMS1117 (`REG_B`) and the Pico's VSYS.
- [ ] Measure. **Pass:** `RAIL_5V` reads 4.75 to 5.25 V, and the `REG_B`
  output and Pi 3.3 V both read 3.2 to 3.4 V.
- [ ] Unplug the Pico's USB cable, which would otherwise power it during F5.
  Power it from `RAIL_5V` through VSYS.
- [ ] Put in the fault switches and label them:

  | Switch | Opens | Fault |
  | --- | --- | --- |
  | S1 | `REG_B` input from `RAIL_5V` | F1 |
  | S2 | I2C-1 SDA (GPIO 2) | F2 |
  | S3 | I2C-3 SCL (GPIO 5) | F3 |
  | S4 | `sun2` VCC | F4 |
  | Unplug the breadboard supply | `RAIL_5V` | F5 |

  The plan lists four inline switches. F5 uses the supply plug unless you
  add a fifth switch.

## 3. Sensors on each bus

Wire the sensors as in the table above. GPIO 4 and 5 have no pull-ups on
the Pi, so I2C-3 relies on the breakout pull-ups.

- [ ] I2C-1:

  ```sh
  i2cdetect -y 1 | sed 1d | cut -c5- | grep -oE '[0-9a-f]{2}|UU' | tr '\n' ' '; echo
  ```

  **Pass:** exactly `0d 40 68 76`.
- [ ] I2C-3:

  ```sh
  i2cdetect -y 3 | sed 1d | cut -c5- | grep -oE '[0-9a-f]{2}|UU' | tr '\n' ' '; echo
  ```

  **Pass:** exactly `23 5c 77`.

If an address is wrong:

| You see | Likely cause | Fix |
| --- | --- | --- |
| `1e` instead of `0d` | Probably an HMC5883L, not a QMC5883L | Confirm the chip ID first (section 4). Then follow [Swapping the magnetometer](#swapping-the-magnetometer) |
| `69` instead of `68` | MPU-6050 AD0 is high | Tie AD0 to GND |
| `77` on bus 1 or `76` on bus 3 | BME280 SDO strap is the wrong way round | `thermal` needs SDO to GND (`0x76`) and `payload` needs SDO to 3.3 V (`0x77`) |
| `23` twice, or no `5c` | `sun2` ADDR is low | Tie `sun2` ADDR to its own VCC for `0x5c` |
| Nothing on bus 3 | No pull-ups, or no `/dev/i2c-3` | Check `ls /dev/i2c-3` and the breakout pull-ups |
| Every address on a bus | SDA and SCL are swapped or shorted | Recheck GPIO 2/3 or GPIO 4/5 |

## 4. Each device on its own

`record --device` samples one device without the graph. Each command runs
for 6 seconds and saves the readings, and the `grep` counts the failed ones.

```sh
for device in imu mag epsmon thermal sun1 sun2 payload radio; do
  commoncause record --device "$device" --duration 6 --out "/tmp/$device.jsonl"
  printf '%-8s %3s readings  %s failed\n' "$device" \
    "$(wc -l < "/tmp/$device.jsonl")" "$(grep -c '"ok":false' "/tmp/$device.jsonl")"
done
```

The recorder refuses to overwrite a file, so run `rm -f /tmp/*.jsonl`
before you repeat the loop.

**Pass:** every device shows `0 failed` and about the readings below. Then
read each file with `cat /tmp/<device>.jsonl`.

| Device | Readings in 6 s | Values that look right |
| --- | --- | --- |
| `imu` | about 24 (two channels at 2 Hz) | `imu.accel` near `[0, 0, 1]` g lying flat, `imu.gyro` near 0 dps |
| `mag` | about 12 | `mag.field` changes when you turn the breakout |
| `epsmon` | about 24 | `eps.regb.voltage` 3.2 to 3.4, `eps.regb.current` above 0 mA |
| `thermal` | about 12 | `thermal.temp` near room temperature |
| `sun1`, `sun2` | about 12 each | `lux` drops when you cover the sensor |
| `payload` | about 24 | `payload.temp` near room temperature, `payload.pressure` about 950 to 1050 hPa at low altitude |
| `radio` | about 6 | `radio.heartbeat` counts up by 1 each second |

`"error":"EREMOTEIO"` means the device did not answer. `"error":"ENODEV"`
means it answered with the wrong chip ID. The recording keeps only the
error name, so read the ID register yourself:

| Device | Command | Expected | Common wrong part |
| --- | --- | --- | --- |
| `imu` | `i2cget -y 1 0x68 0x75` | `0x68` | `0x70`: an MPU-6500 |
| `mag` | `i2cget -y 1 0x0d 0x0d` | `0xff` | |
| `mag` (HMC5883L) | `i2cget -y 1 0x1e 0x0a; i2cget -y 1 0x1e 0x0b; i2cget -y 1 0x1e 0x0c` | `0x48 0x34 0x33` (`H43`) | |
| `thermal` | `i2cget -y 1 0x76 0xd0` | `0x60` | `0x58`: a BMP280 |
| `payload` | `i2cget -y 3 0x77 0xd0` | `0x60` | `0x58`: a BMP280 |

Swap a wrong part, or ask Adi about the driver.

### Swapping the magnetometer

Change the chip only when both the address (`0x1e`) and the ID (`H43`)
say HMC5883L. Make both edits in the same commit:

1. In `hardware/cubesat-pi4.yaml`, set `mag` to `chip: hmc5883l` and
   `address: 0x1e`.
2. In `topologies/cubesat-bench.yaml`, set the `mag` part to `HMC5883L`.
   Keep the device ID `mag` and the channel `mag.field`.

`commoncause record` and `commoncause run` refuse to start if the chip and
the part disagree.
For `commoncause run`, use a new store path after the change, such as
`--db board/store-hmc5883l`, so each store keeps one topology version.
Use that same path for diagnosis and downlink, and retain the original
store with its recordings.

## 5. Back-powering check (the plan's "Check by day 3", row #8)

An unpowered sensor can drag its I2C bus down through its pins, which
would make F1 look like F2. A powered neighbour can also feed an unpowered
sensor through the pull-ups, so it keeps answering. Check all three faults
that remove power.

- [ ] **F1:** open S1 (`REG_B` input). Then:

  ```sh
  i2cdetect -y 1 | sed 1d | cut -c5- | grep -oE '[0-9a-f]{2}|UU' | tr '\n' ' '; echo
  i2cdetect -y 3 | sed 1d | cut -c5- | grep -oE '[0-9a-f]{2}|UU' | tr '\n' ' '; echo
  commoncause record --device epsmon --duration 3 --out - | grep eps.regb.voltage
  ```

  **Pass:** bus 1 shows exactly `40 76` and bus 3 exactly `5c 77`.
  `eps.regb.voltage` reads below 2.97, which is 0.9 × 3.3 V. With the
  multimeter, the VCC pins of `imu`, `mag` and `sun1` read near 0 V. Close S1.
- [ ] **F4:** open S4 (`sun2` VCC). **Pass:** bus 1 shows `0d 40 68 76` and
  bus 3 shows exactly `23 77`. `sun2` VCC reads near 0 V. Close S4.
- [ ] **F5:** unplug `RAIL_5V`. **Pass:** the same addresses as F1, and
  `commoncause record --device radio --duration 4 --out -` ends with
  `commoncause: The recorder received no readings`. Plug it back in.

| What you see | What it means | What to do |
| --- | --- | --- |
| `REG_A` devices vanish too (`40`, `76`, `5c` or `77` missing) | The unpowered sensor clamps the bus. F1 would score as F2 | Per the plan, add an I2C hot-swap buffer (TCA4307 or similar) in front of the `REG_B` sensors, or move them. Note it in your PR: the catalogue already has `unpowered-device-clamps-bus` |
| An unpowered device still answers, or its VCC reads 1 V or more | It is back-powered through the pull-ups or I/O pins | Find the path, usually the breakout pull-ups to its own VCC. Remove those pull-ups or buffer the device |

Write down what you did, even if every check passed. The plan wants the
result recorded.

## 6. The 10-minute healthy capture (row #10, Gate 2)

- [ ] Close all switches, then:

  ```sh
  commoncause run --db board/store --hardware hardware/cubesat-pi4.yaml \
    --recording recordings/bench-healthy.jsonl --duration 600 --tui
  commoncause check-capture recordings/bench-healthy.jsonl --min-seconds 595 --min-rate 0.9
  ```

  **Pass:** the check's first line ends in `healthy` and it exits with 0
  (`echo $?` prints `0`). There is one line per channel, 11 in all, and each
  shows only `OK=...`. The observed rate is at least 1.80/2.00 Hz for the
  sensors and 0.90/1.00 Hz for `radio.heartbeat`. While it runs, the live
  view should show every device `OK` with no diagnosis.
- [ ] Commit `recordings/bench-healthy.jsonl` on a branch and open a pull
  request. Expect about 12,600 lines (10 channels at 2 Hz and the heartbeat
  at 1 Hz), roughly 1.4 MB.

## 7. Live F1 to F5 (row #14)

`--interactive` reads fault markers that you type in the same terminal.
Each marker becomes a `"type":"fault"` line in the recording, which the
scorer uses and the diagnosis never reads. Type the marker and press Enter
even while the live view scrolls. Wait for `Marker recorded: ...` before
you touch a switch. The scorer only counts a diagnosis that opens after
its inject marker.

- [ ] Start the session:

  ```sh
  commoncause run --db board/store --hardware hardware/cubesat-pi4.yaml \
    --recording recordings/bench-f1-f5.jsonl --interactive --tui
  ```

- [ ] Wait until every device shows `OK`. Then for each fault below:
  1. Type `F1 inject` and wait for `Marker recorded: F1 inject`.
  2. Open the switch and hold it for at least 5 seconds.
  3. Check the verdict.
  4. Close the switch, type `F1 clear`, and wait for the `resolved` line
     and every device `OK`. Wait about 5 seconds after F5, because the
     heartbeat needs three new frames.

  | Fault | Action | Verdict you should see |
  | --- | --- | --- |
  | F1 | Open S1 | `REG_B  UNDERVOLTAGE`, then `1. REG_B (Regulator)  1.00  covers 3  contradicted by 0` |
  | F2 | Open S2 | `1. I2C-1 (Bus)` covering 4 |
  | F3 | Open S3 | `1. I2C-3 (Bus)` covering 3 |
  | F4 | Open S4 | `1. sun2 (Device)` covering 1 |
  | F5 | Unplug `RAIL_5V` | It may first show `1. REG_B` at medium confidence. About 3 s later, when `radio  HEARTBEAT_LOST` appears, it should change to `1. RAIL_5V (PowerRail)  1.00  covers 4  contradicted by 0` |

  For reference, a simulated F1 printed this:

  ```text
  Marker recorded: F1 inject
  REG_B  UNDERVOLTAGE
  dx:bench-demo:1  open  high confidence
  1. REG_B (Regulator)  1.00  covers 3  contradicted by 0
    imu -> REG_B
    mag -> REG_B
    sun1 -> REG_B
  Marker recorded: F1 clear
  dx:bench-demo:1  resolved  high confidence
  ```

- [ ] Type `quit`, then score and time the session:

  ```sh
  commoncause matrix recordings/bench-f1-f5.jsonl --expect-count 5 --min-top-one 1
  commoncause benchmark --db board/store --samples 100
  ```

  **Pass:** `Top-1 5/5`, `First correct verdicts 5/5`, and the command exits
  with 0. Save the per-fault first-correct times and the aggregate p50/p95.
  The matrix measures elapsed recording time through the replay frame that
  commits a correct ranking. The benchmark's `Live time to verdict` measures
  wall time through the first committed verdict, which can still be wrong.
  Keep both measurements when assessing the plan's timing target.
- [ ] Downlink, if the `relate` CLI is installed (trixie):

  ```sh
  commoncause downlink --db board/store --out downlink
  ```

  Then open `downlink/common-cause.json` in the ground view with
  **Open downlink**, or with `npm run dev --prefix ground` on a laptop.
- [ ] Commit `recordings/bench-f1-f5.jsonl` in a pull request. Whether the
  bench downlink replaces `data/common-cause.rl` and
  `downlink/common-cause.json` is Adi's call.

If a fault is misranked, keep the recording. It shows what the bench
actually did. Note which check in section 5 it relates to.
