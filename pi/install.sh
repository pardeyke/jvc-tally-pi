#!/usr/bin/env bash
# Run ON THE PI (CompanionPi / Raspberry Pi OS Bookworm):  sudo ./install.sh
set -euo pipefail
cd "$(dirname "$0")"
apt-get update -qq
apt-get install -y -qq python3-gpiozero python3-lgpio
install -d /opt/tally-gpio
install -m 755 tally_gpio.py /opt/tally-gpio/tally_gpio.py
install -m 644 tally-gpio.service /etc/systemd/system/tally-gpio.service
# service user: 'companion' if it exists (CompanionPi / companion-pi installer), else the invoking user
SVC_USER=companion
id companion >/dev/null 2>&1 || SVC_USER="${SUDO_USER:-pi}"
sed -i "s/^User=.*/User=${SVC_USER}/" /etc/systemd/system/tally-gpio.service
usermod -aG gpio "${SVC_USER}" || true
systemctl daemon-reload
systemctl enable tally-gpio.service
systemctl restart tally-gpio.service
sleep 1
systemctl --no-pager --lines=5 status tally-gpio.service || true
echo
echo "Test (from any host):  curl -s http://$(hostname).local:8765/tally/mon1/red ; sleep 2 ; curl -s localhost:8765/tally/mon1/green ; sleep 2 ; curl -s localhost:8765/tally/mon1/off"
