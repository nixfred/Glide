#!/usr/bin/env python3
import argparse
import json
import sys
import time
import fcntl
from glide_network import *


def main():
    parser = argparse.ArgumentParser(description='Glide LAN discovery and authenticated machine layout')
    parser.add_argument('action', choices=['inventory','identity','snapshot','validate','apply','restore','deploy','authorize'])
    parser.add_argument('device', nargs='?')
    args = parser.parse_args()
    if args.action == 'authorize':
        found = next((d for d in inventory()['devices'] if d['id'] == args.device), None)
        if not found: raise ValueError('Machine is no longer advertised on this LAN. Scan again.')
        print(f"Authorize Glide on {found['name']} ({found['ip']}) as {found['user']}.\nSSH will ask you to verify its host identity and authenticate.\n", flush=True)
        outcome = subprocess.run(ssh_args(found, interactive=True) + ['true'])
        if outcome.returncode: raise ValueError('SSH authorization was not completed')
        # Reuse the authenticated SSH connection for subsequent layout updates.
        actual = remote(found, 'identity')
        if actual['fingerprint'] != found['fingerprint']: raise ValueError('Advertised certificate differs from the authenticated machine')
        print('Authorized. Return to Glide and add this machine.', flush=True)
        input('Press Enter to close. ')
        return
    if args.action in ('inventory','identity','snapshot'):
        result = {'inventory':inventory, 'identity':identity, 'snapshot':snapshot}[args.action]()
    else:
        raw = sys.stdin.read(65537)
        if len(raw)>65536: raise ValueError('Layout payload is too large')
        data = json.loads(raw)
        CONFIG.mkdir(parents=True, exist_ok=True, mode=0o700)
        with (CONFIG/'layout.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if args.action == 'validate':
                if not session_active(): raise ValueError('Unlock the desktop first')
                render_config(data, identity()); result = True
            elif args.action == 'apply': result = apply_local(data)
            elif args.action == 'restore': restore_local(data); result = True
            else:
                data['revision'] = str(time.time_ns())
                result = deploy(data)
    print(json.dumps({'ok':True,'result':result}))

if __name__ == '__main__':
    try: main()
    except Exception as error:
        print(json.dumps({'ok':False,'error':str(error)}))
        sys.exit(1)
