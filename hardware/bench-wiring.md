# CubeSat bench wiring

The checked-in hardware map targets a Raspberry Pi 4 and a Raspberry Pi
Pico. Confirm the chip, address straps, and supply pins on each breakout
before wiring it. The logical wiring and channel IDs live in
[`topologies/cubesat-bench.yaml`](../topologies/cubesat-bench.yaml).
Linux adapter numbers, addresses, the UART port, and the shunt value live
in [`cubesat-pi4.yaml`](cubesat-pi4.yaml).

## Pi interfaces

These are BCM GPIO numbers. Header numbers refer to the Pi 4 J8 header.

| Graph bus | Linux interface | Pi GPIO | Header pins |
| --- | --- | --- | --- |
| `I2C-1` | `/dev/i2c-1` | SDA 2, SCL 3 | 3, 5 |
| `I2C-3` | `/dev/i2c-3` | SDA 4, SCL 5 | 7, 29 |
| `UART0` | `/dev/serial0` | RX 15 | 10 |
| Signal ground | Common ground | GND | 6 |

On 64-bit Raspberry Pi OS, enable I2C and the serial hardware. In
`sudo raspi-config`, leave the login shell over serial disabled so it
doesn't consume the heartbeat. Use the following Pi 4 entries in
`/boot/firmware/config.txt`. Reboot after applying them.

```ini
dtparam=i2c_arm=on
dtoverlay=i2c3,pins_4_5
enable_uart=1
```

The Pi 4 can also route the PL011 UART to the GPIO header. If using that
route, follow the Raspberry Pi instructions for the `disable-bt` overlay
and `hciuart` service. Verify the actual serial target and device nodes
before capturing. The Pi 5 uses a different UART default and overlay
mapping, so update the hardware map to match its enabled adapters.
[Raspberry Pi serial configuration](https://www.raspberrypi.com/documentation/computers/configuration.html)
[Raspberry Pi overlay reference](https://github.com/raspberrypi/firmware/blob/master/boot/overlays/README)

```sh
ls -l /dev/i2c-1 /dev/i2c-3 /dev/serial0
readlink -f /dev/serial0
```

## Devices and supply domains

Keep GPIO data signals at 3.3 V. With power disconnected, join grounds
for the signal interfaces and keep the two positive supply outputs
separate. Check each breakout's supply input and pull-up connections
against its own schematic. [Raspberry Pi GPIO and header guide](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#gpio-and-the-40-pin-header)

| Device | Chip | Bus and address | Supply |
| --- | --- | --- | --- |
| `imu` | MPU-6050 | I2C-1 `0x68` | `REG_B` |
| `mag` | QMC5883L | I2C-1 `0x0D` | `REG_B` |
| `epsmon` | INA219 | I2C-1 `0x40` | `REG_A` |
| `thermal` | BME280 | I2C-1 `0x76` | `REG_A` |
| `sun1` | BH1750 | I2C-3 `0x23` | `REG_B` |
| `sun2` | BH1750 | I2C-3 `0x5C` | `REG_A` |
| `payload` | BME280 | I2C-3 `0x77` | `REG_A` |
| `radio` | Pico | UART0 at 115200 baud | `RAIL_5V` |

If the magnetometer is an HMC5883L, choose `hmc5883l` and its
`0x1E` address in the hardware map, then update the part in the topology.
The graph keeps the same `mag.field` channel.

Keep the INA219 logic supply on `REG_A`. Put its shunt in series between
the `REG_B` output and its loads, with `IN+` toward the regulator. The bus
register measures voltage at `IN-`. Match `shunt_ohms` to the resistor on
the breakout before logging current. [INA219 data sheet](https://www.ti.com/lit/ds/symlink/ina219.pdf)

Before counting F1, check that `epsmon`, `thermal`, `sun2`, and `payload`
keep replying when `REG_B` loses power. A powered-off breakout can hold a
shared bus low. For a clamped bus, verify the pull-ups and isolate the
power-switched segment before scoring the wiring. [TCA4307 buffer data sheet](https://www.ti.com/product/TCA4307)

## Pico radio

Flash the Raspberry Pi Pico with MicroPython. With the Pico selected over
USB, copy and reset the heartbeat program. [MicroPython Pico setup](https://docs.micropython.org/en/latest/rp2/tutorial/intro.html)
[mpremote reference](https://docs.micropython.org/en/latest/reference/mpremote.html)

```sh
mpremote fs cp firmware/radio-standin/main.py :main.py
mpremote reset
```

Wire Pico `GP0` (UART0 TX) to the Pi's GPIO 15 (RX) and share signal ground.
The Pico sends `CC1 <counter>` followed by a newline every second. The
counter resets on reboot and wraps after 32 bits.

For F5, the Pico needs to lose power with `RAIL_5V`. Use the Pico's external
supply guidance for VSYS and disconnect its programming USB cable before
that run. [Raspberry Pi Pico data sheet, section 4.5](https://datasheets.raspberrypi.com/pico/pico-datasheet.pdf)
