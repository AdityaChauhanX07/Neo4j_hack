from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import Optional

import yaml

from .drivers import I2C_DRIVERS


@dataclass(frozen=True)
class Output:
    channel: str
    signal: str
    period: float


@dataclass(frozen=True)
class Device:
    id: str
    bus: str
    chip: str
    outputs: tuple
    address: Optional[int] = None
    shunt_ohms: Optional[float] = None


@dataclass(frozen=True)
class Board:
    i2c: dict
    uart: dict
    devices: dict
    stall_channel: Optional[str]
    stall_driver: Optional[str]


def load_board(hardware_path, topology_path):
    hardware = yaml.safe_load(Path(hardware_path).read_text(encoding="utf-8"))
    topology = yaml.safe_load(Path(topology_path).read_text(encoding="utf-8"))
    if not isinstance(hardware, dict) or not isinstance(topology, dict):
        raise ValueError("The hardware and topology files must contain YAML mappings")
    if not isinstance(topology.get("devices"), list) or not isinstance(topology.get("buses"), list):
        raise ValueError("The topology needs devices and buses")
    adapters = hardware.get("buses")
    if not isinstance(adapters, dict):
        raise ValueError("The hardware config needs a buses mapping")
    wiring = {part["id"]: part for part in topology["devices"] if part.get("channels")}
    buses = {bus["id"]: bus["kind"] for bus in topology["buses"]}
    configured = hardware.get("devices")
    if not configured or not isinstance(configured, dict) or configured.keys() != wiring.keys():
        raise ValueError("The hardware devices must match the telemetry devices in the topology")

    i2c = {}
    uart = {}
    devices = {}
    addresses = set()
    for name, options in configured.items():
        if not isinstance(options, dict):
            raise ValueError(f"{name} hardware settings must be a YAML mapping")
        part = wiring[name]
        bus = part.get("bus")
        adapter = adapters.get(bus)
        chip = options.get("chip")
        address = options.get("address")
        shunt = None
        if chip == "heartbeat":
            if buses.get(bus) != "uart" or not isinstance(adapter, dict):
                raise ValueError(f"{name} needs a UART adapter")
            port, baud = adapter.get("port"), adapter.get("baud", 115200)
            if not isinstance(port, str) or not port or type(baud) is not int or baud <= 0:
                raise ValueError(f"{bus} needs a serial port and positive baud rate")
            if bus in uart:
                raise ValueError(f"{bus} already has a heartbeat reader")
            uart[bus] = (port, baud)
            signals = {"counter"}
        else:
            if not isinstance(chip, str) or chip not in I2C_DRIVERS:
                raise ValueError(f"{name} uses unknown chip {chip}")
            if buses.get(bus) != "i2c" or type(adapter) is not int or adapter < 0:
                raise ValueError(f"{bus} needs a Linux I2C adapter number")
            if type(address) is not int or not 0x08 <= address <= 0x77:
                raise ValueError(f"{name} needs a 7-bit I2C address")
            if (adapter, address) in addresses:
                raise ValueError(f"Duplicate address 0x{address:02x} on /dev/i2c-{adapter}")
            i2c[bus] = adapter
            addresses.add((adapter, address))
            signals = I2C_DRIVERS[chip].outputs
            if chip == "ina219":
                shunt = options.get("shunt_ohms")
                if type(shunt) not in (int, float) or not isfinite(shunt) or shunt <= 0:
                    raise ValueError(f"{name} needs a positive shunt_ohms value")

        channels = {ch["id"]: ch for ch in part["channels"]}
        outputs = options.get("outputs")
        if not isinstance(outputs, dict) or outputs.keys() != channels.keys():
            raise ValueError(f"{name} outputs must match its topology channels")
        bound = []
        for channel, signal in outputs.items():
            period = channels[channel].get("period_ms")
            if not isinstance(signal, str) or signal not in signals:
                raise ValueError(f"{channel} uses unknown {chip} output {signal}")
            if type(period) is not int or period <= 0:
                raise ValueError(f"{channel} needs a positive period_ms")
            if (chip == "heartbeat") != bool(channels[channel].get("heartbeat")):
                raise ValueError(f"{channel} heartbeat flag must match the hardware")
            bound.append(Output(channel, signal, period / 1000))
        if chip == "heartbeat" and len(bound) != 1:
            raise ValueError(f"{name} needs one heartbeat channel")
        devices[name] = Device(name, bus, chip, tuple(bound), address, shunt)

    if len(set(i2c.values())) != len(i2c):
        raise ValueError("Each logical I2C bus needs its own Linux adapter")
    if len({port for port, _ in uart.values()}) != len(uart):
        raise ValueError("Each UART reader needs its own serial port")

    stall = hardware.get("stall_channel")
    stall_driver = None
    if stall is not None:
        for device in devices.values():
            if any(output.channel == stall for output in device.outputs):
                stall_driver = wiring[device.id].get("driver", {}).get("id")
                break
        if not stall_driver:
            raise ValueError("The stall channel must belong to a topology Driver")
    return Board(i2c, uart, devices, stall, stall_driver)
