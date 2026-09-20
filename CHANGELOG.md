# Changelog

## 0.2.1

- Physical keyboard presses can reclaim a receiving desktop, alongside mouse and touchpad input. Synthetic devices and key repeats do not trigger takeover.
- Repeated Enter messages acknowledge the current handoff without repeatedly releasing capture.
- Late replies from inactive outgoing handoffs are ignored.
- Completed incoming handoffs remove their return-edge capture barriers.
- Entry retries are briefly suppressed after physical takeover; immediate compositor recapture is suppressed after unlocking.
- Added ownership and recapture regression tests.
- Added the Glide hero artwork, emblem, and installation guide.

## 0.2.2

- Omarchy-only wording throughout the project documentation.
- Physical input on the sending Omarchy host now returns control from the remote host, releases the handoff, and centers the pointer on the local display.
- SSH pairing now transfers the built Glide bundle and installs it on the verified remote Omarchy desktop automatically.
- Sender-side local takeover is armed only after the remote handoff is acknowledged, so crossing an edge no longer bounces back before the handoff completes.

## 0.2.0

- Visual layout for up to nine machines, LAN discovery, SSH pairing, distributed layout application, bar status and pause controls, and physical mouse takeover.
