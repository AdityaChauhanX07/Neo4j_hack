import errno
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from struct import pack
from threading import Lock
from time import monotonic, sleep

import yaml

from ..topology import _wiring
from .recorder import Transports

FAULTS = {
    "F1": {"REG_B"}, "F2": {"I2C-1"}, "F3": {"I2C-3"},
    "F4": {"sun2"}, "F5": {"RAIL_5V"}, "F6": {"UART0"},
    "F7": set(), "F9": {"REG_B", "I2C-3"},
}
CALIBRATION = pack("<HhhH8h", 27504, 26435, -1000, 36477, -10685,
                   3024, 2855, 140, -7, 15500, -14600, 6000)
BME_SAMPLE = (415148 << 4).to_bytes(3, "big") + (519888 << 4).to_bytes(3, "big")
REGISTERS = {
    "mpu6050": {0x75: b"\x68", 0x3B: pack(">7h", 0, 0, 8192, 0, 131, 0, 0)},
    "qmc5883l": {0x0D: b"\xff", 0x06: b"\x01", 0x00: pack("<3h", 120, -240, 360)},
    "hmc5883l": {0x0A: b"H43", 0x03: pack(">3h", 109, 327, -218)},
    "bme280": {0xD0: b"\x60", 0xF3: b"\x00", 0x88: CALIBRATION, 0xF7: BME_SAMPLE},
    "ina219": {0x01: pack(">h", 110)},
    "bh1750": {},
}


class VirtualBench:
    def __init__(self, board, topology_path, *, clock=monotonic):
        topology = yaml.safe_load(Path(topology_path).read_text(encoding="utf-8"))
        nodes, links = _wiring(topology)
        parts = {part["id"] for rows in nodes.values() for part in rows}
        required = set().union(*FAULTS.values())
        if not required <= parts:
            raise ValueError("The virtual bench needs the CubeSat power rails, buses, and sun2 device")
        self.power = {
            source: target for (_, relation, _), pairs in links.items()
            if relation in {"POWERED_BY", "FED_BY"} for source, target in pairs
        }
        self.devices = {
            (board.i2c[device.bus], device.address): device
            for device in board.devices.values() if device.chip != "heartbeat"
        }
        self.radios = {
            board.uart[device.bus][0]: device
            for device in board.devices.values() if device.chip == "heartbeat"
        }
        self.monitors = {
            part["id"]: channel["monitors"] for part in topology["devices"]
            for channel in part.get("channels", []) if "monitors" in channel
        }
        self.board = board
        self.clock = clock
        self.active = {}
        self.lock = Lock()
        self.writes = {}
        self.commands = {}
        self.transports = Transports(self.open_i2c, self.open_uart, ReadMessage)

    def mark(self, fault, action, expected):
        if fault == "F8" and action == "inject":
            if len(expected) != 1 or expected[0] not in self.board.devices:
                raise ValueError("Virtual F8 needs one configured I2C device")
            if self.board.devices[expected[0]].chip == "heartbeat":
                raise ValueError("Virtual F8 needs an I2C device; use F6 for heartbeat loss")
        with self.lock:
            if action == "inject":
                self.active[fault] = (self.clock(), tuple(expected))
            else:
                self.active.pop(fault)

    def upstream(self, part):
        path = {part}
        while part in self.power:
            part = self.power[part]
            path.add(part)
        return path

    def failures(self):
        failed = set()
        with self.lock:
            for fault, (started, targets) in self.active.items():
                if fault == "F8":
                    if int((self.clock() - started) / 0.5) % 2 == 0:
                        failed.update(targets)
                else:
                    failed.update(FAULTS[fault])
        return failed

    def offline(self, device):
        return bool((self.upstream(device.id) | {device.bus}) & self.failures())

    @contextmanager
    def open_i2c(self, number):
        yield VirtualBus(self, number)

    @contextmanager
    def open_uart(self, port, **options):
        yield VirtualUART(self, self.radios[port], options["timeout"])


@dataclass
class ReadMessage:
    address: int
    size: int
    reply: bytes = b""

    def __bytes__(self):
        return self.reply


class VirtualBus:
    def __init__(self, bench, number):
        self.bench = bench
        self.number = number

    def device(self, address):
        device = self.bench.devices.get((self.number, address))
        if device is None or self.bench.offline(device):
            raise OSError(getattr(errno, "EREMOTEIO", errno.EIO), "Virtual I2C device did not answer")
        return device

    def read_i2c_block_data(self, address, register, size):
        device = self.device(address)
        if device.chip == "ina219" and register == 0x02:
            monitor = self.bench.monitors.get(device.id)
            lost = self.bench.upstream(monitor) & self.bench.failures()
            reply = pack(">H", (40 if lost else 825) << 3)
        else:
            try:
                reply = REGISTERS[device.chip][register]
            except KeyError as error:
                raise OSError(errno.EIO, f"Unsupported virtual {device.chip} register 0x{register:02x}") from error
        if len(reply) != size:
            raise OSError(errno.EIO, "Virtual register read has the wrong size")
        return list(reply)

    def write_i2c_block_data(self, address, register, values):
        self.device(address)
        self.bench.writes[self.number, address, register] = bytes(values)

    def write_byte(self, address, command):
        self.device(address)
        self.bench.commands[self.number, address] = command

    def i2c_rdwr(self, message):
        device = self.device(message.address)
        if device.chip != "bh1750" or message.size != 2:
            raise OSError(errno.EIO, "Unsupported virtual raw I2C read")
        message.reply = pack(">H", 180)


class VirtualUART:
    def __init__(self, bench, device, timeout):
        self.bench = bench
        self.device = device
        self.timeout = timeout
        self.next_frame = bench.clock()
        self.counter = 0
        self.buffer = bytearray()

    @property
    def in_waiting(self):
        return len(self.buffer)

    def read(self, size):
        deadline = monotonic() + self.timeout
        while True:
            offline = self.bench.offline(self.device)
            if offline:
                self.buffer.clear()
            now = self.bench.clock()
            if now >= self.next_frame:
                skipped = int(now - self.next_frame)
                self.counter = (self.counter + skipped) & 0xFFFFFFFF
                if not offline:
                    self.buffer.extend(f"CC1 {self.counter}\n".encode("ascii"))
                self.counter = (self.counter + 1) & 0xFFFFFFFF
                self.next_frame += skipped + 1
            if self.buffer:
                reply = bytes(self.buffer[:size])
                del self.buffer[:size]
                return reply
            if monotonic() >= deadline:
                return b""
            sleep(min(0.01, max(0, deadline - monotonic())))
