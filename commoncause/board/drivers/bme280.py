import errno
from struct import unpack
from time import sleep

from ..i2c import require_id


class BME280:
    outputs = {"temperature", "pressure"}

    def __init__(self, port):
        self.port = port

    def initialize(self):
        require_id(self.port, 0xD0, b"\x60")
        if self.port.read(0xF3, 1)[0] & 0x01:
            sleep(0.01)
            if self.port.read(0xF3, 1)[0] & 0x01:
                raise OSError(errno.EAGAIN, "BME280 calibration is still loading")
        self.calibration = unpack("<HhhH8h", self.port.read(0x88, 24))
        if not self.calibration[3]:
            raise OSError(errno.EIO, "BME280 pressure calibration is invalid")
        self.port.write(0xF4, 0x00)
        self.port.write(0xF5, 0x40)
        self.port.write(0xF4, 0x27)
        sleep(0.01)

    def read(self):
        payload = self.port.read(0xF7, 6)
        pressure_adc = int.from_bytes(payload[:3], "big") >> 4
        temperature_adc = int.from_bytes(payload[3:], "big") >> 4
        if 0x80000 in (pressure_adc, temperature_adc):
            raise OSError(errno.EAGAIN, "BME280 conversion is not ready")
        temperature, pressure = compensate(temperature_adc, pressure_adc, self.calibration)
        return {"temperature": temperature, "pressure": pressure}


def compensate(temperature_adc, pressure_adc, calibration):
    t1, t2, t3, p1, p2, p3, p4, p5, p6, p7, p8, p9 = calibration
    temp_delta = temperature_adc / 131072 - t1 / 8192
    fine = ((temperature_adc / 16384 - t1 / 1024) * t2) + (temp_delta ** 2 * t3)
    offset = fine / 2 - 64000
    pressure_offset = (offset ** 2 * p6 / 32768 + 2 * offset * p5) / 4 + p4 * 65536
    pressure_gain = (1 + (p3 * offset ** 2 / 524288 + p2 * offset) / 17179869184) * p1
    pressure = (1048576 - pressure_adc - pressure_offset / 4096) * 6250 / pressure_gain
    correction = p9 * pressure ** 2 / 2147483648 + p8 * pressure / 32768 + p7
    return fine / 5120, (pressure + correction / 16) / 100
