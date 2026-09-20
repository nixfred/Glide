#!/usr/bin/env bash
set -euo pipefail
base="$HOME/.local/share/omarchy-glide-install"
# SSH does not load the graphical session environment. Use Omarchy's stable
# system path when OMARCHY_PATH was not exported into the noninteractive shell.
export OMARCHY_PATH="${OMARCHY_PATH:-/usr/share/omarchy}"
command -v omarchy >/dev/null || { echo 'Remote install requires Omarchy.' >&2; exit 1; }
printf '%s\n' 'Glide needs this Omarchy user’s sudo access to install its dependencies and Avahi.'
sudo -v || { echo 'Glide remote setup stopped: this account cannot use sudo. Ask an Omarchy administrator to install Glide locally on this machine, then pair again.' >&2; exit 1; }
omarchy pkg add python-evdev python-dbus python-gobject avahi
sudo systemctl enable --now avahi-daemon.service
mkdir -p "$HOME/.local/bin" "$HOME/.config/omarchy/plugins/nixfred.glide/scripts" "$HOME/.config/omarchy/plugins/nixfred.glide/assets" "$HOME/.config/systemd/user"
install -m755 "$base/omarchy-glide-engine" "$HOME/.local/bin/omarchy-glide-engine"
cp "$base/Layout.qml" "$base/manifest.json" "$HOME/.config/omarchy/plugins/nixfred.glide/"
cp "$base/assets/glide-icon.png" "$HOME/.config/omarchy/plugins/nixfred.glide/assets/"
cp "$base"/scripts/*.py "$HOME/.config/omarchy/plugins/nixfred.glide/scripts/"
cp "$base/remote-install.sh" "$HOME/.config/omarchy/plugins/nixfred.glide/"
cp "$base"/omarchy-glide*.service "$HOME/.config/systemd/user/"
python3 "$HOME/.config/omarchy/plugins/nixfred.glide/scripts/setup.py"
python3 "$HOME/.config/omarchy/plugins/nixfred.glide/scripts/disable-screensaver-hotcorner.py"
python3 - <<'PY'
import json
from pathlib import Path
p = Path.home()/'.local/state/omarchy/glide/install.json'
p.parent.mkdir(parents=True, exist_ok=True)
p.write_text(json.dumps({'bundle': True, 'admin': True, 'units': False}))
PY
systemctl --user daemon-reload
systemctl --user disable --now omarchy-glide-owner.service >/dev/null 2>&1 || true
rm -f "$HOME/.config/systemd/user/omarchy-glide-owner.service"
systemctl --user enable --now omarchy-glide.service omarchy-glide-discovery.service omarchy-glide-idle.service
python3 - <<'PY'
import json
from pathlib import Path
p = Path.home()/'.local/state/omarchy/glide/install.json'
data = json.loads(p.read_text())
data['units'] = True
p.write_text(json.dumps(data))
PY
omarchy plugin validate "$HOME/.config/omarchy/plugins/nixfred.glide" >/dev/null
omarchy-shell shell rescanPlugins >/dev/null 2>&1 || true
omarchy bar put nixfred.glide --section right >/dev/null 2>&1 || true
rm -rf "$base"
printf '%s\n' 'Glide installed on Omarchy and ready for pairing.'
