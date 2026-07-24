"""Holds the single precious tuner connection (game socket 127.0.0.1:4318);
exposes HTTP on 127.0.0.1:8321.

GET /states                 -> JSON {name: index}
POST /exec  body: {"state": "InGame", "lua": "...", "wait": 2.0}
                            -> JSON {"output": [lines]}  (console lines seen during wait)
GET /drain                  -> JSON {"output": [lines]}  (async lines collected since last call)
"""
import json
import os
import re
import struct
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import socket

TAG_COMMAND = 3
TAG_HANDSHAKE = 4
HOST, PORT = "127.0.0.1", 4318
HTTP_PORT = 8321
MAX_LINES = 5000            # cap on buffered console lines
FRAME_LOG = "tuner_frames.log"
FRAME_LOG_MAX = 10 * 1024 * 1024  # rotate at 10 MB


class TunerDaemon:
    def __init__(self):
        self.sock = None
        self.states = {}
        self.lines = []          # async console output
        self.lock = threading.Lock()
        self.connected = False
        self._frame_log = None

    def connect(self):
        """Keep a live tuner connection forever; reconnect whenever the game drops it."""
        threading.Thread(target=self._connect_loop, daemon=True).start()
        for _ in range(600):
            if self.connected:
                return
            time.sleep(1)
        raise SystemExit("could not connect to tuner")

    def _connect_loop(self):
        while True:
            if not self.connected:
                try:
                    s = socket.create_connection((HOST, PORT), timeout=5)
                    s.settimeout(0.5)
                    self.sock = s
                    self.connected = True
                    self.send(TAG_HANDSHAKE, "APP:FireTuner2")
                    self.send(TAG_HANDSHAKE, "LSQ:")
                    threading.Thread(target=self.reader, args=(s,), daemon=True).start()
                    print("tuner connected", flush=True)
                except OSError:
                    pass
            # Fast redial: the game re-opens its tuner listener only inside the
            # save-load rebuild window, and that window is brief. A 2s poll missed
            # it (2026-07-19), costing a game restart — 0.5s catches it.
            time.sleep(0.5)

    def send(self, tag, payload):
        if not self.connected:
            raise ConnectionError("tuner not connected")
        data = payload.encode("utf-8") + b"\x00"
        try:
            with self.lock:
                self.sock.sendall(struct.pack("<II", len(data), tag) + data)
        except OSError:
            self.connected = False
            raise ConnectionError("tuner send failed")

    def reader(self, s):
        buf = b""
        while True:
            try:
                d = s.recv(65536)
                if not d:
                    print("tuner socket closed!", flush=True)
                    self.connected = False
                    return
                buf += d
            except socket.timeout:
                continue
            except OSError:
                self.connected = False
                return
            while len(buf) >= 8:
                ln, tag = struct.unpack_from("<II", buf)
                if len(buf) < 8 + ln:
                    break
                payload = buf[8 : 8 + ln].rstrip(b"\x00").decode("utf-8", "replace")
                buf = buf[8 + ln :]
                self.handle(tag, payload)

    def _log_frame(self, tag, p):
        # Raw frame log — every message, so protocol errors are visible.
        # One persistent handle; rotate at FRAME_LOG_MAX so it can't grow forever.
        try:
            if self._frame_log is None:
                self._frame_log = open(FRAME_LOG, "a", encoding="utf-8")
            self._frame_log.write(f"[{time.time():.1f}] tag={tag} payload={p[:200]!r}\n")
            self._frame_log.flush()
            if self._frame_log.tell() > FRAME_LOG_MAX:
                self._frame_log.close()
                self._frame_log = None
                try:
                    os.replace(FRAME_LOG, FRAME_LOG + ".1")
                except OSError:
                    pass
        except OSError:
            self._frame_log = None

    def handle(self, tag, p):
        self._log_frame(tag, p)
        if p.startswith("O\x00"):
            self.lines.append(p[2:])
            if len(self.lines) > MAX_LINES:
                # drop oldest half; exec_lua clamps its mark, so in-flight
                # requests degrade to extra lines rather than an IndexError
                del self.lines[: MAX_LINES // 2]
        elif p.startswith("L\x00") or (tag == TAG_HANDSHAKE and "\x00" in p and p[:1].isdigit()):
            body = p[2:] if p.startswith("L\x00") else p
            parts = body.split("\x00")
            try:
                self.states = {parts[i + 1]: int(parts[i]) for i in range(0, len(parts) - 1, 2)}
            except (ValueError, IndexError):
                pass

    def exec_lua(self, state_name, lua, wait=2.0):
        self.send(TAG_HANDSHAKE, "LSQ:")
        time.sleep(0.3)
        idx = self.states.get(state_name)
        if idx is None:
            return {"error": f"state {state_name!r} not found", "states": self.states}
        mark = len(self.lines)
        self.send(TAG_COMMAND, f"CMD:{idx}:{lua}")
        time.sleep(wait)
        mark = min(mark, len(self.lines))  # buffer may have been trimmed
        return {"output": self.lines[mark:]}


daemon = TunerDaemon()


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def reply(self, obj):
        b = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path == "/rehandshake":
            # After a save load the game rebuilds its Lua states; re-register this
            # session on the live socket (reconnecting is not an option: the game
            # never accepts a second tuner connection per process).
            try:
                daemon.send(TAG_HANDSHAKE, "APP:FireTuner2")
                daemon.send(TAG_HANDSHAKE, "LSQ:")
                time.sleep(0.5)
                self.reply({"ok": True, "states": len(daemon.states)})
            except ConnectionError as e:
                self.reply({"ok": False, "error": str(e)})
        elif self.path == "/reconnect":
            # Loading a save invalidates the tuner session server-side (CMD goes
            # dead while LSQ still answers). Gracefully drop and let the connect
            # loop re-establish against the new Lua state set.
            try:
                daemon.connected = False
                daemon.sock.close()
            except OSError:
                pass
            for _ in range(30):
                if daemon.connected:
                    break
                time.sleep(1)
            self.reply({"connected": daemon.connected})
        elif self.path == "/states":
            try:
                daemon.send(TAG_HANDSHAKE, "LSQ:")
                time.sleep(0.3)
            except ConnectionError:
                pass
            self.reply({"connected": daemon.connected, "states": daemon.states})
        elif self.path == "/drain":
            n = len(daemon.lines)
            out, daemon.lines[:] = daemon.lines[:n], daemon.lines[n:]
            self.reply({"output": out})
        else:
            self.reply({"error": "unknown"})

    def do_POST(self):
        try:
            ln = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(ln) or b"{}")
            wait = float(req.get("wait", 2.0))
        except (ValueError, json.JSONDecodeError):
            self.reply({"error": "bad request body"})
            return
        try:
            self.reply(daemon.exec_lua(req.get("state", "InGame"), req.get("lua", ""), wait))
        except ConnectionError as e:
            self.reply({"error": str(e)})


class ExclusiveHTTPServer(ThreadingHTTPServer):
    # HTTPServer sets allow_reuse_address (SO_REUSEADDR), and on Windows that
    # lets a SECOND process bind an already-bound port — verified 2026-07-17:
    # two daemons both bound 8321 and the "lock" silently did nothing.
    allow_reuse_address = False

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


if __name__ == "__main__":
    # Bind the HTTP port FIRST — it doubles as the single-instance lock.
    # Previously a second daemon opened a doomed tuner connection before dying
    # on the port bind, corrupting the live session (see report.md).
    try:
        server = ExclusiveHTTPServer(("127.0.0.1", HTTP_PORT), H)
    except OSError:
        raise SystemExit(f"bridge_daemon already running on 127.0.0.1:{HTTP_PORT} — refusing to start a second instance")
    print("waiting for tuner port...", flush=True)
    daemon.connect()
    print(f"connected to tuner; serving on 127.0.0.1:{HTTP_PORT}", flush=True)
    server.serve_forever()
