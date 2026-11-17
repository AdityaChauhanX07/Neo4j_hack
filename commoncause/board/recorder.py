import errno
import json
import re
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from datetime import datetime, timezone
from functools import partial
from itertools import chain
from math import isfinite
from queue import Empty, SimpleQueue
from select import select
from threading import Event, Lock
from time import monotonic, monotonic_ns, time_ns

from .drivers import I2C_DRIVERS
from .heartbeat import Heartbeats
from .i2c import I2CDevice

FAULT = re.compile(r"F[1-9]")


class Recorder:
    def __init__(self, run_id, stall_channel=None, stall_driver=None):
        self.run_id = run_id
        self.stall_channel = stall_channel
        self.stall_driver = stall_driver
        self.seq = 0
        self.active = set()
        self.epoch = time_ns()
        self.started = monotonic_ns()

    def _timestamp(self):
        return (self.epoch + monotonic_ns() - self.started) // 1_000_000

    def _line(self, timestamp, fields):
        self.seq += 1
        return json.dumps({
            "run": self.run_id, "seq": self.seq, "ts": timestamp, **fields,
        }, separators=(",", ":"), allow_nan=False) + "\n"

    def readings(self, frame):
        timestamp = self._timestamp()
        for channel, value, error in frame:
            if channel == self.stall_channel and "F7" in self.active:
                continue
            yield self._line(timestamp, {
                "channel": channel, "value": value, "ok": error is None, "error": error,
            })

    def mark(self, command):
        parts = command.split()
        if len(parts) < 2 or not FAULT.fullmatch(parts[0]) or parts[1] not in {"inject", "clear"}:
            raise ValueError("Use F1-F9 followed by inject or clear")
        fault, action, *expected = parts
        if action == "clear" and expected:
            raise ValueError("Put the expected components on the inject marker")
        if (fault in self.active) == (action == "inject"):
            raise ValueError(f"{fault} is already {'active' if fault in self.active else 'clear'}")
        if fault == "F7" and self.stall_channel is None:
            raise ValueError("F7 needs a stall_channel in the hardware config")
        if fault == "F8" and action == "inject" and not expected:
            raise ValueError("F8 needs the affected component, for example F8 inject sun2")
        fields = {"type": "fault", "fault": fault, "action": action}
        if action == "inject":
            self.active.add(fault)
            if fault == "F7" and not expected:
                expected = [self.stall_driver]
            if expected:
                fields["expected"] = expected
        else:
            self.active.remove(fault)
        return self._line(self._timestamp(), fields)


class OperatorConsole:
    def __init__(self, stdin, stderr):
        if not stdin.isatty():
            raise ValueError("--interactive requires a terminal on stdin")
        self.stdin = stdin
        self.stderr = stderr
        print("Enter F1-F9 inject or clear. Enter quit to finish the capture.", file=stderr)

    def read(self):
        if select([self.stdin], [], [], 0)[0]:
            line = self.stdin.readline()
            return line.strip() if line else "quit"
        return None

    def invalid(self, error):
        print(f"Marker rejected: {error}", file=self.stderr, flush=True)


def _poll_sensor(device, driver, emit, stop):
    ready = False
    started = monotonic()
    due_at = dict.fromkeys((output.channel for output in device.outputs), started)
    while not stop.is_set():
        now = monotonic()
        due = [output for output in device.outputs if due_at[output.channel] <= now]
        if not due:
            stop.wait(min(due_at.values()) - now)
            continue
        error = None
        values = {}
        try:
            if not ready:
                driver.initialize()
                ready = True
            values = driver.read()
        except OSError as failure:
            ready = False
            error = errno.errorcode.get(failure.errno, "EIO")
        finished = monotonic()
        for output in due:
            planned = due_at[output.channel] + output.period
            due_at[output.channel] = planned if planned > finished else finished + output.period
        emit([
            (output.channel, None if error else values[output.signal], error)
            for output in due
        ])


def _poll_serial(channel, serial, emit, stop):
    decoder = Heartbeats()
    while not stop.is_set():
        try:
            chunk = serial.read(min(serial.in_waiting or 1, 256))
        except OSError:
            decoder = Heartbeats()
            stop.wait(0.25)
            continue
        for counter in decoder.feed(chunk):
            emit([(channel, counter, None)])


def capture(board, *, run_id=None, duration=None, console=None, device=None):
    if duration is not None and (not isfinite(duration) or duration <= 0):
        raise ValueError("Capture duration must be positive")
    if run_id is not None and not run_id.strip():
        raise ValueError("Run ID must not be blank")
    if device is not None and device not in board.devices:
        raise ValueError(f"Unknown board device {device}")
    try:
        from serial import Serial
        from smbus2 import SMBus
    except ImportError as error:
        raise ValueError("Install the board dependencies with pip install '.[board]'") from error

    selected = [board.devices[device]] if device is not None else list(board.devices.values())
    name = run_id or datetime.now(timezone.utc).strftime("bench-%Y%m%dT%H%M%S.%fZ")
    stall = board.stall_channel if any(
        item.channel == board.stall_channel for sensor in selected for item in sensor.outputs
    ) else None
    with ExitStack() as stack:
        buses = {
            bus: (stack.enter_context(SMBus(board.i2c[bus])), Lock())
            for bus in sorted({sensor.bus for sensor in selected if sensor.chip != "heartbeat"})
        }
        producers = []
        for sensor in selected:
            if sensor.chip == "heartbeat":
                port, baud = board.uart[sensor.bus]
                serial = stack.enter_context(Serial(port, baudrate=baud, timeout=0.1, exclusive=True))
                producers.append(partial(_poll_serial, sensor.outputs[0].channel, serial))
            else:
                bus, lock = buses[sensor.bus]
                port = I2CDevice(bus, lock, sensor.address)
                driver = I2C_DRIVERS[sensor.chip]
                chip = driver(port, sensor.shunt_ohms) if sensor.chip == "ina219" else driver(port)
                producers.append(partial(_poll_sensor, sensor, chip))
        yield from _collect(producers, Recorder(name, stall, board.stall_driver), duration, console)


def _collect(producers, recorder, duration, console):
    frames = SimpleQueue()
    stop = Event()
    deadline = monotonic() + duration if duration is not None else float("inf")
    received = False

    with ThreadPoolExecutor(max_workers=len(producers), thread_name_prefix="sensor") as executor:
        workers = [executor.submit(producer, frames.put, stop) for producer in producers]
        try:
            while monotonic() < deadline:
                if console:
                    command = console.read()
                    if command == "quit":
                        break
                    if command:
                        try:
                            marker = recorder.mark(command)
                        except ValueError as error:
                            console.invalid(error)
                        else:
                            yield marker
                for worker in workers:
                    if worker.done():
                        worker.result()
                if all(worker.done() for worker in workers) and frames.empty():
                    break
                try:
                    frame = frames.get(timeout=min(0.1, max(0, deadline - monotonic())))
                except Empty:
                    continue
                for row in recorder.readings(frame):
                    received = True
                    yield row
        except KeyboardInterrupt:
            if not received:
                raise
        finally:
            stop.set()

    if not received:
        raise ValueError("The recorder received no readings")


def save_capture(lines, path):
    if path.exists():
        raise FileExistsError(f"Recording already exists at {path}")
    first = next(lines)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", buffering=1) as recording:
        for line in chain((first,), lines):
            recording.write(line)
            yield line
