# Changelog

## 0.2.3

- Discovery no longer stops refreshing when Hyprland reports `solitaryBlockedBy` as null; the session check treats an absent value as "nothing blocking" instead of raising.
- The installers no longer enable `omarchy-glide-owner.service`. Lan Mouse stays the sole capture and emulation owner, as the README already described; the second evdev watcher had been re-enabled by a later change.
- `install.sh` probes the input group with `grep` instead of an undeclared `ripgrep` dependency.
- `uninstall.sh` also disables `omarchy-glide-idle.service`, which install enables.
- UFW now opens UDP 4242 to each interface's own address instead of pinning every rule to the first interface.
- Pause and resume mirror to every paired machine, not only the first one in the layout.
- The bar shows the paired machine's name again, resolved from the verified layout when the managed engine config carries no hostname.
- The machine certificate is hashed once per revision instead of on every discovery poll, cutting each identity check from 43 ms to 27 ms.

## 0.2.2

- Omarchy-only wording throughout the project documentation.
- Physical input on the sending Omarchy host now returns control from the remote host, releases the handoff, and centers the pointer on the local display.
- SSH pairing now transfers the built Glide bundle and installs it on the verified remote Omarchy desktop automatically.
- Sender-side local takeover is armed only after the remote handoff is acknowledged, so crossing an edge no longer bounces back before the handoff completes.

## 0.2.1

- Physical keyboard presses can reclaim a receiving desktop, alongside mouse and touchpad input. Synthetic devices and key repeats do not trigger takeover.
- Repeated Enter messages acknowledge the current handoff without repeatedly releasing capture.
- Late replies from inactive outgoing handoffs are ignored.
- Completed incoming handoffs remove their return-edge capture barriers.
- Entry retries are briefly suppressed after physical takeover; immediate compositor recapture is suppressed after unlocking.
- Added ownership and recapture regression tests.
- Added the Glide hero artwork, emblem, and installation guide.

## 0.2.0

- Visual layout for up to nine machines, LAN discovery, SSH pairing, distributed layout application, bar status and pause controls, and physical mouse takeover.
