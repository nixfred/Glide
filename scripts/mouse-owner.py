#!/usr/bin/env python3
"""Observe physical input activity without grabbing devices or storing key data.

The daemon decides whether it is currently receiving input. The observer never
reclaims while this machine's mouse is being used to drive a remote screen.
"""
import os
from pathlib import Path
import selectors
import socket
import time
import evdev
from evdev import ecodes as ec


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


def main():
    selector = selectors.DefaultSelector()
    devices = {}
    ipc = None
    last_scan = last_connect = last_claim = 0.0
    endpoint = str(Path(os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')) / 'lan-mouse-socket.sock')

    def close_ipc():
        nonlocal ipc
        if ipc is not None:
            selector.unregister(ipc)
            ipc.close()
            ipc = None

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
        for key, _ in selector.select(timeout=0.25):
            if key.data == 'ipc':
                try:
                    if not ipc.recv(65536):
                        close_ipc()
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
        if activity and ipc is not None and time.monotonic() - last_claim >= 0.05:
            try:
                ipc.sendall(b'"TakeLocalOwnership"\n')
                last_claim = time.monotonic()
            except OSError:
                close_ipc()


if __name__ == '__main__':
    main()
