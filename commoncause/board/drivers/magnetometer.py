import errno
from struct import unpack
from time import sleep

from ..i2c import require_id


class QMC5883L:
    outputs = {"field"}

    def __init__(self, port):
        self.port = port

    def initialize(self):
        require_id(self.port, 0x0D, b"\xff")
        self.port.write(0x0B, 0x01)
        self.port.write(0x09, 0x09)  # 100 Hz, ±2 gauss, continuous
        sleep(0.02)

    def read(self):
        status, = self.port.read(0x06, 1)
        if status & 0x02:
            raise OSError(errno.EOVERFLOW, "Magnetometer saturated")
        if not status & 0x01:
            raise OSError(errno.EAGAIN, "Magnetometer has no fresh sample")
        xyz = unpack("<3h", self.port.read(0x00, 6))
        return {"field": [axis / 120 for axis in xyz]}


class HMC5883L:
    outputs = {"field"}

    def __init__(self, port):
        self.port = port

    def initialize(self):
        require_id(self.port, 0x0A, b"H43")
        self.port.write(0x00, 0x70)
        self.port.write(0x01, 0x20)
        self.port.write(0x02, 0x00)
        sleep(0.08)

    def read(self):
        x, z, y = unpack(">3h", self.port.read(0x03, 6))
        if -4096 in (x, y, z):
            raise OSError(errno.EOVERFLOW, "Magnetometer saturated")
        return {"field": [axis * 100 / 1090 for axis in (x, y, z)]}
