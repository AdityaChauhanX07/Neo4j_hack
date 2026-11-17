from time import sleep


class BH1750:
    outputs = {"lux"}

    def __init__(self, port):
        self.port = port

    def initialize(self):
        self.port.command(0x01)
        self.port.command(0x10)
        sleep(0.18)

    def read(self):
        return {"lux": int.from_bytes(self.port.read_raw(2), "big") / 1.2}
