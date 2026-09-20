#!/usr/bin/env bash
set -euo pipefail
base="$HOME/.local/share/omarchy-glide-install"
# SSH does not load the graphical session environment. Use Omarchy's stable
# system path when OMARCHY_PATH was not exported into the noninteractive shell.
export OMARCHY_PATH="${OMARCHY_PATH:-/usr/share/omarchy}"
command -v omarchy >/dev/null || { echo 'Remote install requires Omarchy.' >&2; exit 1; }
omarchy pkg add python-evdev python-dbus python-gobject avahi
sudo systemctl enable --now avahi-daemon.service
mkdir -p "$HOME/.local/bin" "$HOME/.config/omarchy/plugins/nixfred.glide/scripts" "$HOME/.config/systemd/user"
install -m755 "$base/omarchy-glide-engine" "$HOME/.local/bin/omarchy-glide-engine"
cp "$base/Layout.qml" "$base/manifest.json" "$HOME/.config/omarchy/plugins/nixfred.glide/"
cp "$base"/scripts/*.py "$HOME/.config/omarchy/plugins/nixfred.glide/scripts/"
cp "$base/remote-install.sh" "$HOME/.config/omarchy/plugins/nixfred.glide/"
cp "$base"/omarchy-glide*.service "$HOME/.config/systemd/user/"
python3 "$HOME/.config/omarchy/plugins/nixfred.glide/scripts/setup.py"
systemctl --user daemon-reload
systemctl --user enable --now omarchy-glide.service omarchy-glide-owner.service omarchy-glide-discovery.service
omarchy plugin validate "$HOME/.config/omarchy/plugins/nixfred.glide" >/dev/null
omarchy-shell shell rescanPlugins >/dev/null 2>&1 || true
omarchy bar put nixfred.glide --section right >/dev/null 2>&1 || true
rm -rf "$base"
printf '%s\n' 'Glide installed on Omarchy and ready for pairing.'
