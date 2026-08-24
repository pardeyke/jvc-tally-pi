# JVC DT-V17G1 Tally via Companion + Raspberry Pi

> Hardware documentation, wiring, and the Pi-side `tally-gpio` service.
> The matching Companion module lives at
> [pardeyke/companion-module-jvc-tallypi](https://github.com/pardeyke/companion-module-jvc-tallypi)
> (built package on its Releases page — *Modules → Import custom module*).

Drive the red/green tally lamp of a JVC DT-V17G1 monitor from ATEM program/preview
state: Bitfocus Companion (existing host) → HTTP → Raspberry Pi 3 → relays → the
monitor's REMOTE (MAKE/TRIGGER) RJ-45 port.

## How the monitor side works

The DT-V17G1 REMOTE (MAKE/TRIGGER) terminal is a standard RJ-45 jack. Control is by
contact closure: shorting a pin to GND activates its function.

| RJ-45 pin | Function | T568B wire color |
|-----------|-------------------------------|------------------|
| **1**     | User-assignable → assign **TALLY SEL** | orange/white |
| 2–5       | User-assignable functions     | – |
| **6**     | **TALLY** (lamp on/off)       | green |
| **7**     | **ENABLE** — strap permanently to GND | brown/white |
| **8**     | **GND**                       | brown |

Key facts:

- **Red/green tally needs three wires: pins 6, 8 and one assignable pin.**
  - Pin 6 → pin 8 closed: tally lamp ON. Open: OFF.
  - TALLY SEL pin → pin 8 closed: lamp is **green**. Open: **red**.
  - So: program = close 6 only (red), preview = close 6 + TALLY SEL (green).
- In the monitor menu, assign **TALLY SEL** to one of pins 1–5 (this README assumes
  pin 1). The same function cannot be assigned to two pins.
- **Pin 7 (ENABLE) must be closed for TALLY SEL to work** (verified by testing —
  the manual only exempts pin 6 from ENABLE). Strap pin 7 to pin 8 permanently
  inside the connector; no GPIO needed for it. Plain TALLY on/off (pin 6) works
  either way.
- Set the external control system to **MAKE** in the monitor menu (level-based:
  closed = on, open = off). TRIGGER mode is pulse-toggle and will drift out of sync.

## Hardware

Use an optocoupler so the Pi and the monitor stay galvanically isolated.

### Chosen hardware: RUNCCI‑YUN 4‑channel 5 V relay module (Amazon B0FVLQLCXT)

![Wiring diagram](wiring.svg)

(Full‑size: [wiring.svg](wiring.svg))

Opto‑isolated inputs, Songle‑type 5 V relays, screw terminals, and a **H/L jumper**
that selects high‑ or low‑level trigger. The relay contacts are true dry contacts —
exactly what the REMOTE port expects — with no pull‑up coupling between channels.

**Board setup:** set the trigger jumper to **H** (jumper between the middle pin and
*H*) → relay closes when IN is HIGH → GPIO HIGH = tally on, logic as written below.
(Fallback if the optos won't trigger from 3.3 V in H mode: move jumper to L and swap
HIGH/LOW in the Companion actions; in L mode the inputs are referenced to DC+.)

**Pi → relay board (input side)**

| Pi header | BCM | Board terminal | Notes |
|-----------|-----|----------------|-------|
| phys 2    | 5 V   | **DC+** | relay coil + opto supply (~80 mA per energised relay) |
| phys 6    | GND   | **DC−** | |
| phys 11   | GPIO17| **IN1** | TALLY |
| phys 13   | GPIO27| **IN2** | TALLY SEL |
| —         | —     | IN3/IN4 | spare (second monitor) |

**Relay contacts → RJ‑45 breakout → monitor**

| Relay contact | RJ‑45 breakout | T568B color | JVC function |
|---------------|----------------|-------------|--------------|
| K1 **COM**    | pin 6 | green        | TALLY |
| K1 **NO**     | pin 8 | brown        | GND |
| K2 **COM**    | pin 1 | orange/white | TALLY SEL (assign in monitor menu) |
| K2 **NO**     | pin 8 | brown        | GND |
| —             | pin 7 ↔ pin 8 | brown/white ↔ brown | ENABLE strap (short wire on the breakout) |

Use **NO** (normally open), not NC — the contact must be open when the relay is off.
Two wires land on pin 8 (K1 NO and K2 NO) plus the pin‑7 strap; the breakout's
screw terminal takes them together.

```
 Raspberry Pi             RUNCCI-YUN 4-ch relay            RJ-45 breakout → JVC REMOTE
 5V   (phys 2)  ──── DC+        K1 COM ────────────────── pin 6  TALLY
 GND  (phys 6)  ──── DC-        K1 NO  ───────┐
 GPIO17 (phys 11) ── IN1        K2 COM ───────┼────────── pin 1  TALLY SEL
 GPIO27 (phys 13) ── IN2        K2 NO  ───────┼────────── pin 8  GND
                     IN3/IN4 n/c   jumper = H  └────────── pin 7  ENABLE (strap to pin 8)
```

Truth table: GPIO17 HIGH → K1 closed → tally ON; GPIO27 HIGH → K2 closed → green.
Program (red) = 17 HIGH / 27 LOW. Preview (green) = both HIGH. Off = 17 LOW.
At Pi boot GPIO17/27 are inputs (pulled down) → relays off → no phantom tally.

### Not recommended: JZK 4‑ch PC817 board (Amazon B09TKVV6G3) — wiring if you try it anyway

Verdict from listing + reviews: input spec is 3.6–24 V (Pi GPIO is 3.3 V, one ESP32
reviewer reports unreliable operation), three reviewers report input and output GND
are connected on the PCB (so no real isolation), and the shared‑V1 pull‑ups couple
channels. It may work on a given monitor; test before relying on it.


Per channel the module is: **IN → opto LED → input G** on the control side, and on
the load side an open‑collector transistor: **collector = OUTn** (with a 3 kΩ pull‑up
to V1), **emitter = output G** (via the black jumper cap — leave all jumper caps ON).
When IN is HIGH, OUTn is pulled down to output G — i.e. a closed contact between
OUTn and output G. That is exactly what the JVC wants.

**Pi → module (control side)**

| Pi header | BCM | Module terminal | Purpose |
|-----------|-----|-----------------|---------|
| phys 11   | GPIO17 | **IN1** | TALLY on/off |
| phys 13   | GPIO27 | **IN2** | TALLY SEL (green) |
| phys 9    | GND    | **G** (input side) | common |

Leave IN3/IN4 unconnected (or use them for a second monitor later).

**Module → RJ‑45 breakout → monitor (load side)**

| Module terminal | RJ‑45 screw terminal | T568B color | JVC function |
|-----------------|----------------------|-------------|--------------|
| **OUT1**        | pin 6 | green        | TALLY |
| **OUT2**        | pin 1 | orange/white | TALLY SEL (assign in menu) |
| **G** (output side) | pin 8 | brown    | GND |
| —               | pin 7 ↔ pin 8 | brown/white ↔ brown | ENABLE strap (short wire on the breakout) |
| **V1**          | *leave unconnected* | | see note below |

```
 Raspberry Pi            4-ch PC817 module                 RJ-45 breakout → JVC REMOTE
 GPIO17 (phys 11) ──── IN1        OUT1 ─────────────────── pin 6  TALLY
 GPIO27 (phys 13) ──── IN2        OUT2 ─────────────────── pin 1  TALLY SEL
 GND    (phys 9)  ──── G (in)     G (out) ──────┬───────── pin 8  GND
                                  V1  (n/c)     └───────── pin 7  ENABLE (strap)
                                  IN3/IN4/OUT3/OUT4 unused
```

Truth table: GPIO17 HIGH → tally ON; GPIO27 HIGH additionally → green.
Program (red) = 17 HIGH / 27 LOW. Preview (green) = both HIGH. Off = 17 LOW.

**Note on V1 / the 3 kΩ pull‑ups.** Every OUTn has a 3 kΩ resistor to the shared V1
rail. With V1 floating, OUT1 and OUT2 are coupled through 6 kΩ. When only channel 1
is closed (red), JVC pin 1 is therefore pulled toward pin 6 (≈0 V) through 6 kΩ.
Whether the monitor reads that as "closed" depends on its internal pull‑up, which
is unknown. Test: set red (17 HIGH, 27 LOW) — if the lamp is **red**, all good. If
it comes up **green**, unsolder (or snip) the two 3 kΩ output pull‑ups of channels
1 and 2 (the resistors between OUTn and V1) and the coupling is gone. Do **not**
connect V1 to anything on the JVC side and do not tie it to the Pi — either would
defeat the isolation or make the coupling worse.

### Alternative: bare PC817s (if you ever build it by hand)

```
Raspberry Pi                    PC817 #1                 JVC REMOTE RJ-45
GPIO17 (phys 11) --[330 Ω]--> anode (1)
GND    (phys 9)  -----------> cathode (2)
                              collector (4) ----------> pin 6 (TALLY, green)
                              emitter   (3) ----------> pin 8 (GND, brown)

                                PC817 #2
GPIO27 (phys 13) --[330 Ω]--> anode (1)
GND    (phys 9)  -----------> cathode (2)
                              collector (4) ----------> pin 1 (TALLY SEL, orange/white)
                              emitter   (3) ----------> pin 8 (GND, brown)

Inside the RJ-45 plug:      pin 7 (ENABLE, brown/white) --- strapped to --- pin 8 (GND, brown)
```

- Do **not** wire GPIO directly to the monitor — the port expects a dry contact
  closure, not 3.3 V logic.

## Architecture

Companion already runs on another host in the network. The Pi is **only a network
GPIO box**: it runs a tiny HTTP service (`pi/tally_gpio.py`) that drives the relay
board; Companion's built‑in **Generic HTTP** connection calls it from ATEM‑driven
triggers. Nothing Companion‑related is installed on the Pi, so a Pi 3 is plenty.

```
ATEM ──(network)──▶ Companion host ──HTTP GET /tally/mon1/red|green|off──▶ Pi 3 ──GPIO──▶ relays ──▶ JVC REMOTE
```

## Raspberry Pi prep (Pi 3 as GPIO box)

### Do now (no Pi needed)

1. **Flash the microSD** (≥8 GB) with **Raspberry Pi Imager**
   (`brew install --cask raspberry-pi-imager`): Device *Raspberry Pi 3* · OS
   *Raspberry Pi OS Lite (64‑bit)*. In "OS customisation": hostname **`tally-pi`**,
   enable SSH, set user/password, locale. Ethernet on the show network.
2. Give the Pi a **fixed address** (DHCP reservation on the show router, or a static
   IP) — Companion will target it by IP/hostname. `tally-pi.local` works from macOS;
   from Windows hosts mDNS may not, so prefer the fixed IP in Companion.
3. Keep the `pi/` folder ready to copy (`scp -r pi <user>@tally-pi.local:`).

### First boot

```bash
ssh <user>@tally-pi.local
sudo apt update && sudo apt full-upgrade -y
cd pi && sudo ./install.sh          # installs python3-gpiozero + the tally-gpio service (listens on :8765)
./test-tally.sh                     # bench test: red 3 s → green 3 s → off (pinctrl, no service needed)
```

From the Mac / Companion host:

```bash
curl http://tally-pi.local:8765/health
curl http://tally-pi.local:8765/tally/mon1/red ; sleep 2
curl http://tally-pi.local:8765/tally/mon1/green ; sleep 2
curl http://tally-pi.local:8765/tally/mon1/off
```

Service API: `/tally/<mon>/off|red|green`, `/pin/<bcm>/0|1`, `/state`, `/health`
(GET or POST). It forces all relays off at start and on shutdown and restarts
automatically. Extra monitors: add `--monitor mon2=22,23` (K3/K4) to `ExecStart` in
`/etc/systemd/system/tally-gpio.service`. Relay jumper on L instead of H → add
`--active-low`. The service listens on all interfaces (trusted show network).

## Companion setup (on the existing Companion host)

### Option A (nicer): custom module `jvc-tallypi`

The repo contains a purpose-built Companion module in
`companion-module-jvc-tallypi/`: connection status (goes red if the Pi or ATEM
drops), a **Set tally** action with monitor/state dropdowns (monitors are
auto-discovered from the service), boolean **feedbacks** for button colours,
variables (`$(tallypi:mon1_state)`), ready-made red/green/off **presets** —
and **ATEM-follow**: enter the ATEM IP and map, per monitor, an Output (aux)
number and an M/E. The module then connects to the switcher itself (own
connection, coexists with bmd-atem) and computes red/green/off automatically:
Output source == M/E program → red, == preview → green, else off. **No triggers
needed at all**; it survives output re-routing and re-pushes state if the Pi
restarts. Set e.g. mapping 1 = `mon1` / Output 10 / M/E 4.

Published at **github.com/pardeyke/companion-module-jvc-tallypi** — the release
page has a built `jvc-tallypi-<version>.tgz`; on any Companion ≥ 4 instance:
**Modules → Import custom module** → pick the tgz. Done. (Rebuild after changes:
`npx companion-module-build`, then `gh release create`.)

Alternative for development (Companion ≥ 3.x):

1. Copy the whole `companion-module-jvc-tallypi/` folder (including its
   `node_modules/`, already installed — pure JS, works on any OS) into a folder,
   e.g. `~/companion-dev-modules/`. If you copy it without `node_modules`, run
   `npm install` inside the folder instead.
2. In the Companion web UI: cogwheel (settings) → **Developer modules path** →
   point it at `~/companion-dev-modules/`. Companion loads/watches it automatically.
3. Add connection **jvc-tallypi**: host = Pi IP, port 8765, poll 1000 ms.
4. Buttons: drag the presets from the *Presets* tab, or use the *Set tally* action.
5. Triggers (same three rows as Option B below, but with the module's
   *Set tally* action instead of raw HTTP).

### Trigger logic for "monitor follows an ATEM output" (Constellation 8K)

**Only needed with Option B** (the custom module's ATEM-follow does all of this
internally). The JVC is fed by **Output/Aux 10**; tally should reflect that
source's status on **ME 4**. Do NOT build per-camera triggers — compare ATEM variables against each
other instead. The bmd-atem connection exposes (check its *Variables* tab for the
exact names on your firmware): `$(atem:aux10_input_id)`, `$(atem:pgm4_input_id)`,
`$(atem:pvw4_input_id)`.

**Three triggers per monitor, any number of cameras:**

| Trigger | Condition — internal feedback *Check boolean expression* | Action (jvc-tallypi) |
|---------|----------------------------------------------------------|----------------------|
| Red     | `$(atem:aux10_input_id) == $(atem:pgm4_input_id)`        | Set tally mon1 red   |
| Green   | `$(atem:aux10_input_id) == $(atem:pvw4_input_id) && $(atem:aux10_input_id) != $(atem:pgm4_input_id)` | Set tally mon1 green |
| Off     | `$(atem:aux10_input_id) != $(atem:pgm4_input_id) && $(atem:aux10_input_id) != $(atem:pvw4_input_id)` | Set tally mon1 off   |

Each trigger uses the event "On condition becoming true". The three conditions are
mutually exclusive and cover every case, so "forgetting to turn it off" can't
happen. Re-routing Output 10 to another camera updates the tally automatically —
that's the point of comparing variables instead of hardcoding sources.

**One-trigger variant:** create a custom variable `tally10`, one trigger with
events "On variable change" for each of the three ATEM variables, action 1 =
internal *Set custom variable with expression*:

```
($(atem:aux10_input_id) == $(atem:pgm4_input_id)) ? 'red'
  : (($(atem:aux10_input_id) == $(atem:pvw4_input_id)) ? 'green' : 'off')
```

action 2 = jvc-tallypi *Set tally*, monitor `mon1`, state `$(custom:tally10)`
(the state field accepts variables since module v1.0.1).

### Option B: plain Generic HTTP (no custom module)

1. Add connection **Generic: HTTP Requests** (label e.g. `tally-pi`). Base URL:
   `http://<pi-ip>:8765` (Companion ≥3 has a base‑URL field; otherwise use full URLs).
2. Make sure the **ATEM** connection is present.
3. Create three **Triggers** per monitor (for the camera on this monitor, e.g. Cam 1):

| Trigger   | Condition (ATEM feedback)               | Action (Generic HTTP → GET)     |
|-----------|-----------------------------------------|---------------------------------|
| Program   | *Program input = Cam 1*                 | `/tally/mon1/red`               |
| Preview   | *Preview input = Cam 1* AND NOT program | `/tally/mon1/green`             |
| Off       | neither program nor preview             | `/tally/mon1/off`               |

Tips:
- Trigger type "on condition becoming true" for each row. The "Off" row's condition
  is the inverse of the other two.
- Optional manual override: a button with `/tally/mon1/red` on press and
  `/tally/mon1/off` on release.
- Multi‑monitor: repeat with `mon2` and Cam 2, driving K3/K4.
- If Companion ever moves onto the Pi itself, the bundled *Raspberry Pi GPIO*
  connection can replace the HTTP calls (pin 17 HIGH/LOW = TALLY, pin 27 = TALLY SEL).

Note: the BMD GPI and Tally Interface box can't do this — its relays follow
**program** tally only, so green/preview tally is a reason for the Pi.

## Test without Companion

```bash
# on the Pi — red tally 2 s, green tally 2 s, off
pinctrl set 17 op dh; sleep 2
pinctrl set 27 op dh; sleep 2
pinctrl set 17 dl; pinctrl set 27 dl
```

(`pinctrl` on Bookworm; use `raspi-gpio set 17 op dh` on older OS releases.)

## References

- [JVC DT-V17G1 manual, pp. 20–21](https://www.manualslib.com/manual/81840/Jvc-Dt-V17g1.html?page=20) — MAKE/TRIGGER pin assignment
- [Companion Raspberry Pi GPIO module help](https://github.com/bitfocus/companion-bundled-modules/blob/main/raspberry-gpio/companion/HELP.md)
- [Bitfocus connection page: RPi GPIO](https://bitfocus.io/connections/raspberry-gpio)

## Shopping list (Pi already on hand)

Minimal, no-solder build:

| # | Item | Qty | Notes |
|---|------|-----|-------|
| 1 | **RUNCCI-YUN 4-channel 5 V relay module, high/low trigger selectable** ([B0FVLQLCXT](https://www.amazon.de/dp/B0FVLQLCXT), €6.99) — ORDERED | 1 | Alternative: ELEGOO 4-ch ([B01M8G4Y7Z](https://www.amazon.de/dp/B01M8G4Y7Z), low-level trigger, JD-VCC jumper). Avoid "PC817 4-Kanal Optokoppler" boards (3.6 V min input, GNDs tied on PCB) and "12V→3.3V PLC" converters (wrong direction). |
| 2 | RJ-45 breakout board (RJ-45 jack → screw terminals) | 1 | Lets you strap pin 7→8 and land pins 1/6/8 without cutting cables. |
| 3 | Cat5/6 patch cable, 1–3 m | 1 | Breakout → monitor REMOTE jack. |
| 4 | Dupont jumper wires, female–female | 1 pack | Pi header → opto module. |
| 5 | Hook-up wire 0.5 mm², ~1 m | 1 | Opto module → RJ-45 breakout, pin 7→8 strap. |
| 6 | Small ABS enclosure, ~100×60×25 mm | 1 | Optional; keeps the opto + breakout from dangling behind the monitor. |

If you'd rather solder a bare build instead of item 1: PC817 ×2 (buy a 10-pack),
330 Ω resistors ×2, a small perfboard, and a 2×20 stacking header or Pi screw-terminal HAT.

Already have / free: Raspberry Pi 3, microSD (≥8 GB, Raspberry Pi OS Lite 64-bit), Pi PSU (2.5 A), network cable.
