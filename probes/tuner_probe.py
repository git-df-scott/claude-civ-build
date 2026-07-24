import socket, sys, time

HOST, PORT = "127.0.0.1", 4318

s = socket.create_connection((HOST, PORT), timeout=5)
s.settimeout(3)
print("connected")

def dump(tag, data):
    print(f"--- {tag}: {len(data)} bytes")
    print(data[:2000])
    print(data[:2000].hex(" ")[:3000])

# just listen first
buf = b""
t0 = time.time()
while time.time() - t0 < 5:
    try:
        d = s.recv(65536)
        if not d:
            break
        buf += d
    except socket.timeout:
        break
dump("initial", buf)
s.close()
