#!/usr/bin/env python3
"""
Tiny HTTP → GPIO tally service for JVC monitors driven via relay contacts.

Endpoints (GET or POST):
  /tally/<monitor>/off       TALLY relay open (lamp off; monitor keeps its colour)
  /tally/<monitor>/red       TALLY closed; colour pulsed to red if needed (program)
  /tally/<monitor>/green     TALLY closed; colour pulsed to green if needed (preview)
  /calibrate/<monitor>/<red|green>  tell the service what colour the lamp shows now
  /pin/<bcm>/<0|1>           raw pin control (any configured pin)
  /state                     JSON with all monitors/pins
  /health                    200 OK

Colour semantics (verified on a DT-V17G1): the TALLY SEL pin is an edge-triggered
TOGGLE — each closure flips red<->green and the monitor latches the result. The
service therefore tracks the lamp colour per monitor (persisted across restarts)
and pulses the SEL relay only when the colour must change (--sel-mode toggle,
default). --sel-mode level restores plain level behaviour for monitors that
select colour by pin level.

Monitors are configured with --monitor NAME=TALLY_PIN,SEL_PIN (BCM numbering),
e.g. --monitor mon1=17,27 --monitor mon2=22,23

Runs on the Pi with gpiozero (lgpio/RPi.GPIO backend chosen automatically,
works on Pi 4 and Pi 5 / Bookworm). For bench testing elsewhere:
  GPIOZERO_PIN_FACTORY=mock ./tally_gpio.py --monitor mon1=17,27
"""
import argparse
import json
import os
import signal
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from gpiozero import OutputDevice

# ---------------------------------------------------------------- state ----
LOCK = threading.Lock()
PINS = {}       # bcm -> OutputDevice
MONITORS = {}   # name -> {"tally": bcm, "sel": bcm, "state": ..., "lamp": "red|green"}
ACTIVE_HIGH = True  # relay board jumper on H: GPIO HIGH = relay closed
SEL_TOGGLE = True   # DT-V17G1: SEL closure toggles colour (edge), monitor latches it
PULSE_MS = 300
STATE_FILE = None


def load_lamp_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_lamp_state():
    try:
        with open(STATE_FILE, "w") as f:
            json.dump({n: m["lamp"] for n, m in MONITORS.items()}, f)
    except OSError as e:
        print(f"warning: cannot persist lamp state: {e}", file=sys.stderr)


def get_pin(bcm):
    if bcm not in PINS:
        PINS[bcm] = OutputDevice(bcm, active_high=ACTIVE_HIGH, initial_value=False)
    return PINS[bcm]


def set_colour(mon, sel, desired):
    """Make the lamp colour match `desired`, tracking the monitor's latch."""
    if SEL_TOGGLE:
        if mon["lamp"] != desired:
            sel.on()
            time.sleep(PULSE_MS / 1000)
            sel.off()
            mon["lamp"] = desired
            save_lamp_state()
    else:  # level-based monitors: closed = green, open = red
        sel.on() if desired == "green" else sel.off()
        mon["lamp"] = desired


def set_tally(name, state):
    mon = MONITORS[name]
    tally, sel = get_pin(mon["tally"]), get_pin(mon["sel"])
    with LOCK:
        if state == "off":
            tally.off()
            if not SEL_TOGGLE:
                sel.off()
        elif state in ("red", "green"):
            tally.on()
            set_colour(mon, sel, state)
        else:
            raise ValueError(f"unknown state {state!r} (use off|red|green)")
        mon["state"] = state


def snapshot():
    return {
        "monitors": {n: dict(m) for n, m in MONITORS.items()},
        "pins": {str(b): int(d.value) for b, d in PINS.items()},
    }


# ------------------------------------------------------------- http api ----
class Handler(BaseHTTPRequestHandler):
    server_version = "tally-gpio/1.0"

    def _send(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parts = [p for p in self.path.split("?")[0].split("/") if p]
        try:
            if parts == ["health"]:
                return self._send(200, {"ok": True})
            if parts == ["state"]:
                return self._send(200, snapshot())
            if len(parts) == 3 and parts[0] == "calibrate":
                _, name, colour = parts
                if name not in MONITORS:
                    return self._send(404, {"error": f"unknown monitor {name}"})
                if colour not in ("red", "green"):
                    return self._send(400, {"error": "colour must be red or green"})
                with LOCK:
                    MONITORS[name]["lamp"] = colour
                    save_lamp_state()
                return self._send(200, {"monitor": name, "lamp": colour})
            if len(parts) == 3 and parts[0] == "tally":
                _, name, state = parts
                if name not in MONITORS:
                    return self._send(404, {"error": f"unknown monitor {name}"})
                set_tally(name, state)
                return self._send(200, {"monitor": name, "state": state})
            if len(parts) == 3 and parts[0] == "pin":
                bcm, val = int(parts[1]), parts[2]
                if val not in ("0", "1"):
                    return self._send(400, {"error": "value must be 0 or 1"})
                with LOCK:
                    get_pin(bcm).value = int(val)
                return self._send(200, {"pin": bcm, "value": int(val)})
            return self._send(404, {"error": "unknown endpoint"})
        except ValueError as e:
            return self._send(400, {"error": str(e)})

    do_POST = do_GET

    def log_message(self, fmt, *args):  # quieter journal
        sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))


# ----------------------------------------------------------------- main ----
def parse_monitor(spec):
    name, pins = spec.split("=")
    tally, sel = (int(x) for x in pins.split(","))
    return name, {"tally": tally, "sel": sel, "state": "off", "lamp": "red"}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--monitor", action="append", default=[], metavar="NAME=TALLY,SEL",
                    help="BCM pins for a monitor (repeatable). Default: mon1=17,27")
    ap.add_argument("--bind", default="127.0.0.1", help="listen address (default localhost only)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--active-low", action="store_true",
                    help="relay board jumper on L: GPIO LOW = relay closed")
    ap.add_argument("--sel-mode", choices=["toggle", "level"], default="toggle",
                    help="TALLY SEL semantics: 'toggle' pulses on colour change "
                         "(DT-V17G1, default), 'level' holds closed for green")
    ap.add_argument("--pulse-ms", type=int, default=300,
                    help="SEL pulse width in toggle mode (default 300)")
    ap.add_argument("--state-file", default=None,
                    help="lamp-colour persistence file (default: $STATE_DIRECTORY/lamp.json)")
    args = ap.parse_args()

    global ACTIVE_HIGH, SEL_TOGGLE, PULSE_MS, STATE_FILE
    ACTIVE_HIGH = not args.active_low
    SEL_TOGGLE = args.sel_mode == "toggle"
    PULSE_MS = args.pulse_ms
    state_dir = os.environ.get("STATE_DIRECTORY", ".")
    STATE_FILE = args.state_file or os.path.join(state_dir, "lamp.json")

    persisted = load_lamp_state()
    for spec in (args.monitor or ["mon1=17,27"]):
        name, cfg = parse_monitor(spec)
        if persisted.get(name) in ("red", "green"):
            cfg["lamp"] = persisted[name]
        MONITORS[name] = cfg
        get_pin(cfg["tally"]).off(); get_pin(cfg["sel"]).off()
        cfg["state"] = "off"  # lamp off at start; latched colour left untouched

    srv = ThreadingHTTPServer((args.bind, args.port), Handler)

    def shutdown(*_):
        for n in MONITORS:
            set_tally(n, "off")
        srv.shutdown()
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    print(f"tally-gpio listening on http://{args.bind}:{args.port}  monitors={MONITORS}", flush=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    signal.pause()


if __name__ == "__main__":
    main()
