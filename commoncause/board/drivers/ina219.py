from struct import unpack
from time import sleep


class INA219:
    outputs = {"voltage", "current"}

    def __init__(self, port, shunt_ohms):
        self.port = port
        self.shunt_ohms = shunt_ohms

    def initialize(self):
        self.port.write(0x00, 0x39, 0x9F)
        sleep(0.003)

    def read(self):
        shunt, = unpack(">h", self.port.read(0x01, 2))
        bus, = unpack(">H", self.port.read(0x02, 2))
        # The current register depends on calibration. The shunt reading does not.
        return {"voltage": (bus >> 3) * 0.004, "current": shunt * 0.01 / self.shunt_ohms}
