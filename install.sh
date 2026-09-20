#!/usr/bin/env bash
set -euo pipefail
base=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
: "${OMARCHY_PATH:?Run the installer from your Omarchy desktop terminal}"
omarchy pkg add lan-mouse python-evdev python-dbus python-gobject avahi
if ! command -v cargo >/dev/null; then omarchy pkg add rust; fi
"$base/build-engine.sh"
python3 "$base/scripts/setup.py"
mkdir -p "$HOME/.local/bin" "$HOME/.config/systemd/user"
install -m755 "$base/engine/target/release/lan-mouse" "$HOME/.local/bin/omarchy-glide-engine.new"
mv "$HOME/.local/bin/omarchy-glide-engine.new" "$HOME/.local/bin/omarchy-glide-engine"
"$base/scripts/install-plugin.sh"
cp "$base"/omarchy-glide*.service "$HOME/.config/systemd/user/"
# Grant only the active local session access; never add users to the input group.
if ! id -nG | tr ' ' '\n' | rg -qx input; then
  rule=$(mktemp)
  trap 'rm -f "$rule"' EXIT
  cat > "$rule" <<'RULE'
SUBSYSTEM=="input", KERNEL=="event*", ENV{ID_INPUT_MOUSE}=="1", TAG+="uaccess"
SUBSYSTEM=="input", KERNEL=="event*", ENV{ID_INPUT_TOUCHPAD}=="1", TAG+="uaccess"
SUBSYSTEM=="input", KERNEL=="event*", ENV{ID_INPUT_KEYBOARD}=="1", TAG+="uaccess"
RULE
  sudo install -m644 "$rule" /etc/udev/rules.d/70-omarchy-glide-pointers.rules
  sudo udevadm control --reload-rules
  sudo udevadm trigger --subsystem-match=input --action=change
fi
sudo systemctl enable --now avahi-daemon.service
python3 "$base/scripts/firewall.py"
systemctl --user daemon-reload
systemctl --user enable omarchy-glide-owner.service
systemctl --user enable --now omarchy-glide.service omarchy-glide-discovery.service
# Let Omarchy finish its asynchronous plugin inventory refresh.
for attempt in {1..12}; do
  if omarchy plugin list --json | jq -e '.[] | select(.id=="nixfred.glide")' >/dev/null; then break; fi
  sleep 0.25
done
omarchy bar put nixfred.glide --section right
printf '%s\n' 'Glide installed. Open the mouse icon, select a nearby machine, authorize SSH, position it, and apply.'
