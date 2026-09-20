#!/usr/bin/env bash
set -euo pipefail
base="$HOME/.local/share/omarchy-glide-install"
: "${OMARCHY_PATH:?Remote install requires an Omarchy desktop}"
mkdir -p "$HOME/.local/bin" "$HOME/.config/omarchy/plugins/nixfred.glide" "$HOME/.config/systemd/user"
install -m755 "$base/omarchy-glide-engine" "$HOME/.local/bin/omarchy-glide-engine"
cp "$base/Layout.qml" "$base/manifest.json" "$HOME/.config/omarchy/plugins/nixfred.glide/"
cp "$base"/scripts/*.py "$HOME/.config/omarchy/plugins/nixfred.glide/scripts/"
cp "$base/remote-install.sh" "$HOME/.config/omarchy/plugins/nixfred.glide/"
cp "$base"/omarchy-glide*.service "$HOME/.config/systemd/user/"
python3 "$HOME/.config/omarchy/plugins/nixfred.glide/scripts/setup.py"
systemctl --user daemon-reload
systemctl --user disable --now omarchy-glide-owner.service >/dev/null 2>&1 || true
systemctl --user enable --now omarchy-glide.service omarchy-glide-discovery.service
omarchy plugin validate "$HOME/.config/omarchy/plugins/nixfred.glide" >/dev/null
omarchy-shell shell rescanPlugins >/dev/null 2>&1 || true
omarchy bar put nixfred.glide --section right >/dev/null 2>&1 || true
rm -rf "$base"
printf '%s\n' 'Glide installed on Omarchy and ready for pairing.'
