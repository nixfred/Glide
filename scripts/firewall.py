#!/usr/bin/env python3
"""Install UFW rules restricted to physical LANs; keep removal commands."""
import json
import shutil
import subprocess
from glide_network import STATE, atomic, interfaces, read_json

if not shutil.which('ufw'):
    raise SystemExit('No UFW detected. If another firewall is active, allow UDP 4242 and mDNS 5353 only on your physical LAN.')
state=subprocess.run(['sudo','ufw','status'],check=True,capture_output=True,text=True).stdout
if 'Status: active' not in state:
    print('UFW is inactive; Glide still binds only its physical LAN address and authenticates peers.')
    raise SystemExit(0)
links=interfaces()
if not links: raise SystemExit('No physical LAN connected')
owned=read_json(STATE/'firewall-rules.json',[])
for link in links:
    for destination,port in [(links[0]['ip'],'4242'),('any','5353')]:
        rule=['allow','in','on',link['name'],'from',link['network'],'to',destination,'port',port,'proto','udp','comment','Omarchy Glide LAN']
        result=subprocess.run(['sudo','ufw']+rule,check=True,capture_output=True,text=True)
        print(result.stdout.strip())
        if ('Rule added' in result.stdout or 'Rules updated' in result.stdout) and rule not in owned:
            owned.append(rule)
atomic(STATE/'firewall-rules.json',json.dumps(owned,indent=2))
