"""Minimal FireTuner (Firaxis Nexus) protocol client for Civ 6."""
import socket
import struct
import time

TAG_COMMAND = 3
TAG_HANDSHAKE = 4


class Tuner:
    def __init__(self, host="127.0.0.1", port=4318, timeout=3.0, retries=60):
        for i in range(retries):
            try:
                self.sock = socket.create_connection((host, port), timeout=5)
                break
            except OSError:
                if i == retries - 1:
                    raise
                time.sleep(3)
        self.sock.settimeout(timeout)
        self.buf = b""

    def send(self, tag, payload):
        data = payload.encode("utf-8") + b"\x00"
        self.sock.sendall(struct.pack("<II", len(data), tag) + data)

    def recv_msgs(self, wait=2.0):
        """Collect framed messages for up to `wait` seconds."""
        end = time.time() + wait
        msgs = []
        while time.time() < end:
            try:
                d = self.sock.recv(65536)
                if not d:
                    break
                self.buf += d
            except socket.timeout:
                pass
            while len(self.buf) >= 8:
                ln, tag = struct.unpack_from("<II", self.buf)
                if len(self.buf) < 8 + ln:
                    break
                payload = self.buf[8 : 8 + ln].rstrip(b"\x00").decode("utf-8", "replace")
                self.buf = self.buf[8 + ln :]
                msgs.append((tag, payload))
        return msgs

    def handshake(self):
        self.send(TAG_HANDSHAKE, "APP:FireTuner2")
        msgs = self.recv_msgs(2.0)
        self.send(TAG_HANDSHAKE, "LSQ:")
        msgs += self.recv_msgs(2.0)
        return msgs

    def cmd(self, state, lua, wait=2.0):
        self.send(TAG_COMMAND, f"CMD:{state}:{lua}")
        return self.recv_msgs(wait)


if __name__ == "__main__":
    t = Tuner()
    print("connected")
    for tag, p in t.handshake():
        print(f"[{tag}] {p!r}")
