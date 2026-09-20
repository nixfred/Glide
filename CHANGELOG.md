# Changelog

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
