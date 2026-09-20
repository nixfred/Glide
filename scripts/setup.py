#!/usr/bin/env python3
"""Initialize a new Glide installation without replacing unrelated input settings."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
from glide_network import *

CONFIG.mkdir(parents=True, exist_ok=True, mode=0o700)
STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
pem = Path.home()/'.config/lan-mouse/lan-mouse.pem'
if LAN_CONFIG.exists() and 'Managed by Omarchy Glide' not in LAN_CONFIG.read_text():
    raise SystemExit('Existing Lan Mouse configuration is not managed by Glide. Back it up and move it before installing.')
if not pem.exists():
    pem.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory() as directory:
        key, cert = Path(directory)/'key', Path(directory)/'cert'
        subprocess.run(['openssl','req','-x509','-newkey','ec','-pkeyopt','ec_paramgen_curve:P-256','-nodes','-subj','/CN=Glide','-days','3650','-keyout',str(key),'-out',str(cert)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        # webrtc-dtls 0.12 uses PRIVATE_KEY as its PEM tag for PKCS#8 DER.
        atomic(pem, key.read_text().replace('PRIVATE KEY','PRIVATE_KEY')+cert.read_text())
        pem.chmod(0o400)
me=identity()
if not me['active'] or not me['ip']:
    raise SystemExit('Install from an unlocked Omarchy desktop connected to a private physical LAN.')
if not (CONFIG/'layout.json').exists():
    layout={'version':1,'revision':str(time.time_ns()),'machines':[dict(me,x=0,y=0)]}
    atomic(LAN_CONFIG,render_config(layout,me))
    atomic(CONFIG/'layout.json',json.dumps(layout,indent=2))
print('Glide identity ready for '+me['name']+' on '+me['ip'])
