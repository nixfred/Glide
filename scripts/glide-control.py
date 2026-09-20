#!/usr/bin/env python3
"""Small bounded Lan Mouse 0.11 IPC client for the Omarchy bar."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import shlex
import tomllib

UNIT = 'omarchy-glide.service'
PLUGIN_SCRIPT = '.config/omarchy/plugins/nixfred.glide/scripts/glide-control.py'

def peer_target():
    """Return the paired SSH target from Glide's verified layout."""
    layout = Path.home() / '.config/omarchy-glide/layout.json'
    try:
        data = json.loads(layout.read_text())
        machines = data.get('machines', [])
        me = socket.gethostname()
        peer = next((m for m in machines if m.get('name') != me), None)
        if not peer:
            return None
        user = peer.get('user', '')
        ip = peer.get('ip', '')
        if not user or not ip:
            return None
        return user, ip
    except (OSError, ValueError, TypeError):
        return None

def remote_action(action):
    target = peer_target()
    if not target:
        return False, 'No paired SSH target is available'
    user, ip = target
    command = (
        "uid=$(id -u); "
        "export XDG_RUNTIME_DIR=/run/user/$uid; "
        "export DBUS_SESSION_BUS_ADDRESS=unix:path=$XDG_RUNTIME_DIR/bus; "
        f"python3 {shlex.quote(PLUGIN_SCRIPT)} --local-only {shlex.quote(action)}"
    )
    args = [
        'ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5',
        '-o', 'ConnectionAttempts=1', '-o', 'ClearAllForwardings=yes',
        f'{user}@{ip}', command,
    ]
    result = subprocess.run(args, capture_output=True, text=True, timeout=12)
    if result.returncode:
        detail = (result.stderr or result.stdout).strip().splitlines()
        return False, detail[-1] if detail else f'SSH exited {result.returncode}'
    return True, ''

def status():
    result = {'running': False, 'ready': False, 'host': socket.gethostname(),
              'peer': '', 'position': 'left', 'connected': False, 'error': ''}
    try:
        config = tomllib.loads((Path.home() / '.config/lan-mouse/config.toml').read_text())
        clients = config.get('clients', [])
        if clients:
            result.update(peer=clients[0].get('hostname', ''), position=clients[0].get('position', 'left'))
        with socket.socket(socket.AF_UNIX) as sock:
            sock.settimeout(1)
            sock.connect(str(Path(os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')) / 'lan-mouse-socket.sock'))
            result['running'] = True
            capture = emulation = False
            # The daemon sends a full Sync on connection, ending with AuthorizedUpdated.
            with sock.makefile('r') as stream:
                for _ in range(32):
                    line = stream.readline(65536)
                    if not line:
                        raise ConnectionError('Sharing service disconnected')
                    event = json.loads(line)
                    if 'Enumerate' in event:
                        entries = event['Enumerate']
                        result['clients'] = entries
                        result['connected'] = any(entry[2]['alive'] for entry in entries)
                        if entries:
                            _, conf, state = entries[0]
                            result.update(peer=conf.get('hostname', ''), position=conf['pos'],
                                          active=state['active'])
                    if 'CaptureStatus' in event:
                        capture = event['CaptureStatus'] == 'Enabled'
                    if 'EmulationStatus' in event:
                        emulation = event['EmulationStatus'] == 'Enabled'
                    if 'AuthorizedUpdated' in event:
                        result['ready'] = capture and emulation and result.get('active', False)
                        break
    except (OSError, ValueError, ConnectionError) as exc:
        if result['running']:
            result['error'] = str(exc)
    return result

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['status', 'pause', 'resume', 'toggle', 'settings'], default='status', nargs='?')
    parser.add_argument('--local-only', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.action == 'status':
        print(json.dumps(status()))
        return
    if args.action == 'settings':
        subprocess.run(['systemctl', '--user', 'start', UNIT], check=True, timeout=10)
        subprocess.Popen(['/usr/bin/lan-mouse'], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    action = args.action
    if action == 'toggle':
        active = subprocess.run(['systemctl', '--user', 'is-active', '--quiet', UNIT], timeout=5).returncode == 0
        action = 'pause' if active else 'resume'
    # Stopping releases captured input and pauses both sending and receiving.
    subprocess.run(['systemctl', '--user', 'stop' if action == 'pause' else 'start', UNIT], check=True, timeout=10)
    if not args.local_only:
        ok, error = remote_action(action)
        if not ok:
            raise SystemExit(f'Local sharing changed, but paired machine could not be updated: {error}')

if __name__ == '__main__':
    main()
