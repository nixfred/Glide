#!/usr/bin/env python3
"""Pair this machine with an SSH-verified peer's public fingerprint."""
import argparse
import ipaddress
from pathlib import Path
import re
import shutil
import tomllib

p = argparse.ArgumentParser()
p.add_argument('peer')
p.add_argument('position', choices=['left', 'right', 'top', 'bottom'])
p.add_argument('ip', type=ipaddress.ip_address)
p.add_argument('fingerprint')
a = p.parse_args()
if not re.fullmatch(r'[a-zA-Z0-9.-]+', a.peer):
    p.error('invalid peer name')
if not re.fullmatch(r'(?:[0-9a-fA-F]{2}:){31}[0-9a-fA-F]{2}', a.fingerprint):
    p.error('expected SHA256 certificate fingerprint')
path = Path.home() / '.config/lan-mouse/config.toml'
original = path.read_text()
current = tomllib.loads(original)
if current.get('clients') or current.get('authorized_fingerprints'):
    p.error('already paired; use Lan Mouse settings to edit existing peers')
shutil.copy2(path, path.with_suffix('.toml.before-pair'))
content = original + f'''\n[authorized_fingerprints]
"{a.fingerprint.lower()}" = "{a.peer}"

[[clients]]
hostname = "{a.peer}"
position = "{a.position}"
ips = ["{a.ip}"]
port = 4242
activate_on_startup = true
'''
tomllib.loads(content)
# Atomic replacement keeps the daemon from observing a partially written file.
tmp = path.with_suffix('.tmp')
tmp.write_text(content)
tmp.chmod(0o600)
tmp.replace(path)
