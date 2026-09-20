#!/usr/bin/env bash
set -euo pipefail
umask 077
base=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
if [[ -e "$HOME/.config/lan-mouse/config.toml" ]]; then
  echo 'Existing Lan Mouse configuration found; refusing to replace it.' >&2
  exit 1
fi
mkdir -p "$HOME/.config/lan-mouse" "$HOME/.config/systemd/user" "$HOME/.local/state/omarchy/glide"
sha256sum "$HOME/.config/hypr/"{hyprland,bindings,input,clipboard}.lua > "$HOME/.local/state/omarchy/glide/keyboard-before.sha256"
cp "$base/omarchy-glide.service" "$HOME/.config/systemd/user/omarchy-glide.service"
cat > "$HOME/.config/lan-mouse/config.toml" <<'CONFIG'
# Managed by Omarchy Glide. Pair only verified peer fingerprints.
port = 4242
capture_backend = "layer-shell"
emulation_backend = "wlroots"
release_bind = ["KeyLeftCtrl", "KeyLeftShift", "KeyEsc"]
CONFIG
systemctl --user daemon-reload
systemctl --user enable --now omarchy-glide.service
