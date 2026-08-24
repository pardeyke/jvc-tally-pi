#!/usr/bin/env bash
# Bench test without Companion or the service: cycles red → green → off on BCM 17/27.
# Usage: ./test-tally.sh [tally_pin] [sel_pin]   (default 17 27)
T=${1:-17}; S=${2:-27}
if command -v pinctrl >/dev/null; then          # Bookworm+
  on()  { pinctrl set "$1" op dh; }; off() { pinctrl set "$1" dl; }
elif command -v raspi-gpio >/dev/null; then     # Bullseye
  on()  { raspi-gpio set "$1" op dh; }; off() { raspi-gpio set "$1" dl; }
else echo "need pinctrl or raspi-gpio"; exit 1; fi
echo "RED   (tally on, sel off)";  on "$T"; off "$S"; sleep 3
echo "GREEN (tally on, sel on)";   on "$S";           sleep 3
echo "OFF";                        off "$T"; off "$S"
