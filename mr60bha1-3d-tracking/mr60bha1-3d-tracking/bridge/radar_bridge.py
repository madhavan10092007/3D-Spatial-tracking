"""
MR60BHA1 Radar Python Bridge
Reads 3D coordinate data from ESP32 via Serial and broadcasts via WebSocket.
Install dependencies: pip install pyserial websockets
Run: python radar_bridge.py --port COM14 --baud 115200
"""

import asyncio
import json
import re
import argparse
import serial
import websockets
from datetime import datetime

# ── Config ────────────────────────────────────────────────────────────────────
DEFAULT_PORT = "COM14"
DEFAULT_BAUD = 115200
WS_HOST      = "localhost"
WS_PORT      = 8765

# ── State shared across all WebSocket clients ─────────────────────────────────
connected_clients = set()
latest_data = {
    "x": 0.0,
    "y": 0.0,
    "z": 0.0,
    "detected": False,
    "timestamp": None
}

# ── Serial parser ─────────────────────────────────────────────────────────────
# Matches: X: 0.12m (Left/Right) | Y: 1.45m (Depth/Forward) | Z: -0.03m (Elevation/Height)
COORD_PATTERN = re.compile(
    r"X:\s*([-\d.]+)m.*?Y:\s*([-\d.]+)m.*?Z:\s*([-\d.]+)m",
    re.IGNORECASE
)

def parse_line(line: str) -> dict | None:
    """Parse a serial line from the ESP32 sketch and return a data dict or None."""
    line = line.strip()

    if not line:
        return None

    # 3D coordinate frame
    m = COORD_PATTERN.search(line)
    if m:
        return {
            "type":      "coordinate",
            "x":         float(m.group(1)),
            "y":         float(m.group(2)),
            "z":         float(m.group(3)),
            "detected":  True,
            "timestamp": datetime.utcnow().isoformat()
        }

    # Presence keywords from earlier debug output
    lower = line.lower()
    if "no human" in lower:
        return {"type": "presence", "detected": False, "timestamp": datetime.utcnow().isoformat()}
    if "human detected" in lower or "stationary" in lower or "movement" in lower:
        return {"type": "presence", "detected": True,  "timestamp": datetime.utcnow().isoformat()}

    return None

# ── WebSocket broadcast ───────────────────────────────────────────────────────
async def broadcast(message: str):
    if connected_clients:
        await asyncio.gather(
            *[client.send(message) for client in connected_clients],
            return_exceptions=True
        )

async def ws_handler(websocket):
    """Handle a new WebSocket client connection."""
    connected_clients.add(websocket)
    print(f"[WS]  Client connected  ({len(connected_clients)} total)")
    try:
        # Send current state immediately so the dashboard isn't blank
        await websocket.send(json.dumps({**latest_data, "type": "init"}))
        async for _ in websocket:   # keep connection alive; ignore incoming msgs
            pass
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        connected_clients.discard(websocket)
        print(f"[WS]  Client disconnected ({len(connected_clients)} total)")

# ── Serial reader (runs in a thread via asyncio.to_thread) ───────────────────
def read_serial(port: str, baud: int, loop: asyncio.AbstractEventLoop):
    """Blocking serial read loop — runs in a background thread."""
    global latest_data
    print(f"[SER] Opening {port} @ {baud} baud …")
    try:
        ser = serial.Serial(port, baud, timeout=1)
    except serial.SerialException as e:
        print(f"[SER] ERROR: {e}")
        print("[SER] Running in DEMO mode — sending simulated data.")
        import math, time
        t = 0.0
        while True:
            t += 0.1
            demo = {
                "type":      "coordinate",
                "x":         round(math.sin(t) * 1.5, 3),
                "y":         round(1.0 + abs(math.cos(t * 0.5)) * 2.0, 3),
                "z":         round(math.sin(t * 0.3) * 0.5, 3),
                "detected":  True,
                "timestamp": datetime.utcnow().isoformat()
            }
            latest_data.update(demo)
            asyncio.run_coroutine_threadsafe(broadcast(json.dumps(demo)), loop)
            time.sleep(0.1)
        return

    print(f"[SER] Connected to {port}")
    while True:
        try:
            raw = ser.readline().decode("utf-8", errors="replace")
        except serial.SerialException as e:
            print(f"[SER] Read error: {e}")
            break

        parsed = parse_line(raw)
        if parsed:
            latest_data.update(parsed)
            asyncio.run_coroutine_threadsafe(broadcast(json.dumps(parsed)), loop)
            # Pretty-print to console
            if parsed["type"] == "coordinate":
                print(f"[DAT] X={parsed['x']:+.2f}  Y={parsed['y']:+.2f}  Z={parsed['z']:+.2f}")
            else:
                status = "DETECTED" if parsed["detected"] else "absent"
                print(f"[DAT] Human {status}")

# ── Main ──────────────────────────────────────────────────────────────────────
async def main(port: str, baud: int):
    loop = asyncio.get_running_loop()

    # Start serial reader in background thread
    loop.run_in_executor(None, read_serial, port, baud, loop)

    # Start WebSocket server
    print(f"[WS]  Server listening on ws://{WS_HOST}:{WS_PORT}")
    async with websockets.serve(ws_handler, WS_HOST, WS_PORT):
        await asyncio.Future()   # run forever

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MR60BHA1 → WebSocket bridge")
    parser.add_argument("--port", default=DEFAULT_PORT, help="Serial port (e.g. COM14 or /dev/ttyUSB0)")
    parser.add_argument("--baud", default=DEFAULT_BAUD, type=int, help="Baud rate")
    args = parser.parse_args()

    try:
        asyncio.run(main(args.port, args.baud))
    except KeyboardInterrupt:
        print("\n[SYS] Shutting down.")
