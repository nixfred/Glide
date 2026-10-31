#!/usr/bin/env python3
"""Install UFW rules restricted to physical LANs; keep removal commands.

    firewall.py                 LAN rules, plus a rule for each saved routed peer
    firewall.py add-peer IP     allow UDP 4242 from one routed peer's address only
    firewall.py remove-peer IP  delete that peer's rule
"""
import json
import shutil
import subprocess
import sys
from glide_network import STATE, atomic, interfaces, manual_peers, parse_private_ip, read_json

PEER_COMMENT = 'Omarchy Glide peer'


def peer_rule(link, ip):
    """One routed peer, one address, UDP 4242 to the address Glide binds, on its NIC."""
    return ['allow', 'in', 'on', link['name'], 'from', str(ip), 'to', link['ip'], 'port', '4242', 'proto', 'udp', 'comment', PEER_COMMENT]


def ufw(*args):
    return subprocess.run(['sudo', 'ufw', *args], check=True, capture_output=True, text=True).stdout


def active():
    if not shutil.which('ufw'):
        print('No UFW detected. If another firewall is active, allow UDP 4242 from the routed peer only.')
        return False
    if 'Status: active' not in ufw('status'):
        print('UFW is inactive; Glide still binds only its physical LAN address and authenticates peers.')
        return False
    return True


def record(owned, rule, output):
    if ('Rule added' in output or 'Rules updated' in output) and rule not in owned:
        owned.append(rule)


def add_peer(ip, owned):
    links = interfaces()
    if not links: raise SystemExit('No physical LAN connected')
    rule = peer_rule(links[0], parse_private_ip(ip))
    output = ufw(*rule)
    print(output.strip())
    record(owned, rule, output)


def remove_peer(ip, owned):
    address = str(parse_private_ip(ip))
    for rule in [r for r in owned if r[-1] == PEER_COMMENT and r[r.index('from') + 1] == address]:
        print(ufw('delete', *rule).strip())
        owned.remove(rule)


def main(argv):
    if len(argv) not in (0, 2) or (argv and argv[0] not in ('add-peer', 'remove-peer')):
        raise SystemExit(__doc__)
    if not active(): return
    owned = read_json(STATE/'firewall-rules.json', [])
    if argv:
        (add_peer if argv[0] == 'add-peer' else remove_peer)(argv[1], owned)
    else:
        links = interfaces()
        if not links: raise SystemExit('No physical LAN connected')
        for link in links:
            for destination, port in [(link['ip'], '4242'), ('any', '5353')]:
                rule = ['allow', 'in', 'on', link['name'], 'from', link['network'], 'to', destination, 'port', port, 'proto', 'udp', 'comment', 'Omarchy Glide LAN']
                output = ufw(*rule)
                print(output.strip())
                record(owned, rule, output)
        for peer in manual_peers(): add_peer(peer['ip'], owned)
    atomic(STATE/'firewall-rules.json', json.dumps(owned, indent=2))


if __name__ == '__main__':
    main(sys.argv[1:])
