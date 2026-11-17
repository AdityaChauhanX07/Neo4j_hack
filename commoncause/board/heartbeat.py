import re

FRAME = re.compile(rb"CC1 ([0-9]{1,10})\r?")
MAX_FRAME_BYTES = 32


class Heartbeats:
    def __init__(self):
        self.buffer = bytearray()
        self.discarding = False

    def feed(self, chunk):
        for byte in chunk:
            if byte == 10:
                if not self.discarding:
                    match = FRAME.fullmatch(self.buffer)
                    if match:
                        counter = int(match[1])
                        if counter <= 0xFFFFFFFF:
                            yield counter
                self.buffer.clear()
                self.discarding = False
            elif self.discarding:
                continue
            elif len(self.buffer) < MAX_FRAME_BYTES:
                self.buffer.append(byte)
            else:
                self.buffer.clear()
                self.discarding = True
