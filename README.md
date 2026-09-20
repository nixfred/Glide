<p align="center">
  <img src="assets/glide-hero.png" alt="Glide — One desk. Every machine. An electric lime pointer flows across three dark displays." width="100%">
</p>

<p align="center"><strong>Mouse and keyboard sharing for Omarchy.</strong><br>Move to the edge. Keep working.</p>

<p align="center">
  <img alt="Version" src="https://img.shields.io/badge/version-0.2.1-c5ff36?style=flat-square&labelColor=111111">
  <img alt="Platform" src="https://img.shields.io/badge/platform-Omarchy%20%2F%20Hyprland-c5ff36?style=flat-square&labelColor=111111">
  <img alt="Network" src="https://img.shields.io/badge/network-LAN%20only-c5ff36?style=flat-square&labelColor=111111">
</p>

Glide lets your pointer cross from one computer to the next, with your keyboard following along. Arrange your machines in the Omarchy panel, pair them, and work across your desk with one set of controls.

**Early development:** the first supported environment is Omarchy on Hyprland, using the bundled Linux engine. Physical handoff testing is still in progress. Clipboard contents stay local; this is input sharing, not screen streaming or file transfer.

## Your whole desk, connected

| Feature | What it does |
| --- | --- |
| **Cross an edge** | Move between neighboring computers with your mouse. The keyboard follows the active handoff. |
| **Map your desk** | Drag up to nine computers onto a 5 × 3 grid. Arrange neighbors left, right, above, or below. Arrow keys also move the selected machine. |
| **Discover nearby sessions** | Find active Glide desktops on your physical private LAN. Discovery never grants permission to control a machine. |
| **Pair through SSH** | Verify each device's identity through your SSH login before applying a layout. |
| **Apply one layout** | Distribute the arrangement to participating machines, with rollback attempted if deployment fails. |
| **Physical input takes priority** | Move a receiving machine's own mouse or press its physical keyboard to reclaim local control. Continued input on the sending machine keeps driving the remote desktop. |
| **Pause from the bar** | Check live status and pause or resume sharing. Right-click the bar icon for a quick toggle. |
| **Encrypted connections** | The bundled engine uses DTLS with paired certificate fingerprints in both directions. |
| **Emergency return** | Press **Left Ctrl + Left Shift + Esc** on the sending keyboard to release capture. |

<p align="center"><img src="assets/glide-icon.png" alt="Glide's black metal G and lime cursor emblem" width="180"></p>

## Install on each computer

Use an unlocked Omarchy desktop connected to the same physical private IPv4 LAN. Each computer needs SSH access for pairing and layout updates. Glide uses Avahi for discovery and UDP port 4242 for input sharing.

```bash
git clone https://github.com/nixfred/Glide.git
cd Glide
./install.sh
```

The installer builds the bundled engine, installs the bar plugin and user services, starts Avahi, and configures LAN-scoped UFW rules. It may ask for `sudo` for packages, device access, Avahi, and firewall setup. With another firewall, configure the LAN rules yourself; the installer currently expects UFW.

Physical takeover needs read access to local input devices. The installer adds session-scoped `uaccess` rules for mice, touchpads, and keyboards when necessary; it does not add your account to the `input` group. The observer uses key-down activity only, without decoding or storing typed text. Synthetic uinput devices are excluded.

An unrelated existing Lan Mouse configuration is not overwritten. Back it up and move it before installing. Do not run another Lan Mouse daemon alongside Glide: both use the same IPC socket and configuration directory.

## Set up your desk

1. Open the mouse icon in the Omarchy bar on one machine.
2. Select a nearby machine and choose **Authorize SSH**. Verify its SSH host identity before accepting it.
3. Choose **Add selected**, then drag the machine to match its physical position.
4. Choose **Apply layout**. Repeat for any additional computers.
5. Cross the corresponding screen edge to start sharing.

Connections follow the nearest machine in the same row or column. Diagonal-only arrangements do not create a connection. On the receiving computer, its own mouse or keyboard reclaims local control.

If you release control while resting on a screen edge, move inward before crossing again. Glide suppresses immediate recapture for 250 ms and rejects entry retries for 500 ms after physical takeover.

## Troubleshooting

**Release a trapped pointer:** use Left Ctrl + Left Shift + Esc on the sending keyboard. To pause sharing from a terminal on either computer:

```bash
systemctl --user stop omarchy-glide.service
```

Resume with `systemctl --user start omarchy-glide.service`.

**Inspect the services:**

```bash
systemctl --user status omarchy-glide omarchy-glide-owner omarchy-glide-discovery
journalctl --user -u omarchy-glide -u omarchy-glide-owner -n 80
python3 scripts/glide-control.py status
```

**No nearby machines:** install Glide and log into an unlocked desktop on each computer. Check Avahi and allow LAN mDNS (UDP 5353). VPN, container, loopback, public-IP, and IPv6-only networks are not discovered.

**Local takeover does not work:** check the ownership-service log for the physical mouse and keyboard names. Device permissions may need a logout/login or device reconnect after installation.

**Network address changed:** rescan and reapply the layout. Saved peer addresses and firewall rules are not a general roaming-network manager.

```bash
./uninstall.sh
```

Uninstall disables the plugin and services and removes recorded Glide firewall rules. It retains pairing identities, source, device-access rules, and recovery files.

## Development

The Python helpers manage discovery, pairing, layout deployment, status, and physical input observation. `Layout.qml` is the bar panel. `engine/` vendors Lan Mouse source, including Glide's ownership and pairing changes; it is not a submodule.

```bash
python3 -m unittest discover -s tests -v
cargo test --manifest-path engine/Cargo.toml --locked \
  --no-default-features --features layer_shell_capture,wlroots_emulation \
  -p lan-mouse -p input-capture -p lan-mouse-ipc
./build-engine.sh
```

See [CHANGELOG.md](CHANGELOG.md) for handoff fixes and [assets/README.md](assets/README.md) for the artwork.

## Credits and licensing

Built by **Fred Nix** for Omarchy, powered by **[Lan Mouse](https://github.com/feschber/lan-mouse)** by Ferdinand Schober and contributors. Vendored baseline: `0d2190e787db9e482e17d4c16fb7c00ef4841bcb` (Lan Mouse 0.11.0 source).

The Glide plugin and helpers use the [MIT license](LICENSE). The bundled Lan Mouse engine and its modifications use [GPL-3.0-or-later](engine/LICENSE). Both licenses and upstream attribution are retained.
