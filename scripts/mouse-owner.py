#!/usr/bin/env python3
"""Observe physical input activity without grabbing devices or storing key data.

Physical input returns an incoming or outgoing handoff to this machine. The
daemon acknowledges an actual return before we center the local pointer.
"""
import json
import os
from pathlib import Path
import selectors
import socket
import subprocess
import time
import evdev
from evdev import ecodes as ec

HANDOFF_SETTLE_SECONDS = 0.4


def physical_pointer(device):
    # uinput devices would feed received or generated events back into ownership.
    sys_path = (Path('/sys/class/input') / Path(device.path).name / 'device').resolve()
    if str(sys_path).startswith('/sys/devices/virtual/input/') or device.info.bustype == ec.BUS_VIRTUAL:
        return False
    caps = device.capabilities(absinfo=False)
    rel = caps.get(ec.EV_REL, [])
    keys = caps.get(ec.EV_KEY, [])
    absolute = caps.get(ec.EV_ABS, [])
    return ((ec.REL_X in rel and ec.REL_Y in rel) or
            (ec.BTN_TOOL_FINGER in keys and ec.ABS_X in absolute and ec.ABS_Y in absolute))


def physical_keyboard(device):
    sys_path = (Path('/sys/class/input') / Path(device.path).name / 'device').resolve()
    if str(sys_path).startswith('/sys/devices/virtual/input/') or device.info.bustype == ec.BUS_VIRTUAL:
        return False
    keys = device.capabilities(absinfo=False).get(ec.EV_KEY, [])
    return all(key in keys for key in (ec.KEY_A, ec.KEY_Z, ec.KEY_ENTER))


def input_activity(event):
    # Use only the fact of a key press; never decode, retain, or log key values.
    return pointer_activity(event) or (
        event.type == ec.EV_KEY and 0 < event.code < ec.BTN_MISC and event.value == 1)


def pointer_activity(event):
    if event.type == ec.EV_REL:
        return event.code in (ec.REL_X, ec.REL_Y, ec.REL_WHEEL, ec.REL_HWHEEL) and event.value != 0
    if event.type == ec.EV_ABS:
        return event.code in (ec.ABS_X, ec.ABS_Y, ec.ABS_MT_POSITION_X, ec.ABS_MT_POSITION_Y)
    return event.type == ec.EV_KEY and event.code in (ec.BTN_LEFT, ec.BTN_RIGHT, ec.BTN_MIDDLE, ec.BTN_TOUCH) and event.value == 1


def monitor_center(monitors):
    active = [m for m in monitors if not m.get('disabled') and m.get('dpmsStatus', True)]
    if not active:
        raise ValueError('No active display to center on')
    monitor = next((m for m in active if m.get('focused')), active[0])
    width, height = monitor['width'], monitor['height']
    if monitor.get('transform', 0) % 2:
        width, height = height, width
    scale = monitor.get('scale', 1)
    if scale <= 0:
        raise ValueError('Invalid monitor scale')
    return (round(monitor['x'] + width / scale / 2),
            round(monitor['y'] + height / scale / 2))


def center_pointer():
    try:
        response = subprocess.run(['hyprctl', '-i', '0', '-j', 'monitors'],
                                  check=True, capture_output=True, text=True, timeout=1)
        x, y = monitor_center(json.loads(response.stdout))
        subprocess.run(['hyprctl', '-i', '0', 'dispatch', 'movecursor', str(x), str(y)],
                       check=True, capture_output=True, text=True, timeout=1)
        print(f'Local control restored; pointer centered at {x},{y}', flush=True)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        print(f'Local control restored; pointer centering failed: {exc}', flush=True)


def remote_control_state(data):
    try:
        event = json.loads(data)
        if event == 'RemoteControlActive':
            return True
        if event in ('RemoteControlInactive', 'LocalOwnershipTaken', 'LocalOwnershipActive'):
            return False
        return None
    except (ValueError, UnicodeDecodeError):
        return None


def takeover_allowed(remote_active, active_since, now):
    """Ignore edge residual motion while the compositor finishes the handoff."""
    return (remote_active and active_since is not None and
            now - active_since >= HANDOFF_SETTLE_SECONDS)


def main():
    selector = selectors.DefaultSelector()
    devices = {}
    ipc = None
    ipc_buffer = b''
    center_at = None
    remote_active = False
    remote_active_since = None
    last_scan = last_connect = last_claim = 0.0
    endpoint = str(Path(os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')) / 'lan-mouse-socket.sock')

    def close_ipc():
        nonlocal ipc, ipc_buffer, center_at, remote_active, remote_active_since
        if ipc is not None:
            selector.unregister(ipc)
            ipc.close()
            ipc = None
        ipc_buffer = b''
        center_at = None
        remote_active = False
        remote_active_since = None

    while True:
        now = time.monotonic()
        if now - last_scan >= 2:
            last_scan = now
            present = set(evdev.list_devices())
            for path in list(devices):
                if path not in present:
                    selector.unregister(devices[path])
                    devices.pop(path).close()
            for path in present - devices.keys():
                device = None
                try:
                    device = evdev.InputDevice(path)
                    if physical_pointer(device) or physical_keyboard(device):
                        selector.register(device, selectors.EVENT_READ, 'input')
                        devices[path] = device
                        print(f'Watching physical input: {device.name}', flush=True)
                    else:
                        device.close()
                except OSError:
                    if device is not None:
                        device.close()
        if ipc is None and now - last_connect >= 1:
            last_connect = now
            candidate = socket.socket(socket.AF_UNIX)
            try:
                candidate.connect(endpoint)
                candidate.setblocking(False)
                selector.register(candidate, selectors.EVENT_READ, 'ipc')
                ipc = candidate
            except OSError:
                candidate.close()
        activity = False
        wait = 0.25 if center_at is None else max(0, min(0.25, center_at - time.monotonic()))
        for key, _ in selector.select(timeout=wait):
            if key.data == 'ipc':
                try:
                    data = ipc.recv(65536)
                    if not data:
                        close_ipc()
                    else:
                        ipc_buffer += data
                        while b'\n' in ipc_buffer:
                            line, ipc_buffer = ipc_buffer.split(b'\n', 1)
                            state = remote_control_state(line)
                            if state is not None:
                                remote_active = state
                                remote_active_since = time.monotonic() if state else None
                            if state is False and line == b'"LocalOwnershipTaken"':
                                # Allow the compositor to process the engine's
                                # already-flushed unlock before warping locally.
                                center_at = time.monotonic() + 0.02
                        if len(ipc_buffer) > 262144:
                            close_ipc()
                except BlockingIOError:
                    pass
                except OSError:
                    close_ipc()
                continue
            device = key.fileobj
            try:
                for event in device.read():
                    activity = input_activity(event) or activity
            except BlockingIOError:
                pass
            except OSError:
                selector.unregister(device)
                devices.pop(device.path, None)
                device.close()
        now = time.monotonic()
        if (takeover_allowed(remote_active, remote_active_since, now) and
                activity and ipc is not None and now - last_claim >= 0.05):
            try:
                ipc.sendall(b'"TakeLocalOwnership"\n')
                last_claim = time.monotonic()
            except OSError:
                close_ipc()
        if center_at is not None and time.monotonic() >= center_at:
            center_at = None
            center_pointer()


if __name__ == '__main__':
    main()
