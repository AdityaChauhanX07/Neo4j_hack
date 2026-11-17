from struct import unpack
from time import sleep

from ..i2c import require_id


class MPU6050:
    outputs = {"gyro", "accel"}

    def __init__(self, port):
        self.port = port

    def initialize(self):
        require_id(self.port, 0x75, b"\x68")
        self.port.write(0x6B, 0x01)
        self.port.write(0x1A, 0x03)
        self.port.write(0x1B, 0x00)  # ±250 degrees per second
        self.port.write(0x1C, 0x08)  # ±4 g
        sleep(0.05)

    def read(self):
        ax, ay, az, _, gx, gy, gz = unpack(">7h", self.port.read(0x3B, 14))
        return {
            "gyro": [gx / 131, gy / 131, gz / 131],
            "accel": [ax / 8192, ay / 8192, az / 8192],
        }
