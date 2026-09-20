"""Glide's LAN inventory, authenticated layout deployment and saved state."""
import fcntl
import getpass
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import tarfile
import tempfile
import time
import tomllib

CONFIG = Path.home() / '.config/omarchy-glide'
LAN_CONFIG = Path.home() / '.config/lan-mouse/config.toml'
STATE = Path.home() / '.local/state/omarchy/glide'
SERVICE = 'omarchy-glide.service'
PRIVATE = [ipaddress.ip_network(n) for n in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16')]
REMOTE = 'python3 .config/omarchy/plugins/nixfred.glide/scripts/network.py'
PLUGIN = Path.home() / '.config/omarchy/plugins/nixfred.glide'


def run(argv, **kw):
    return subprocess.run(argv, text=kw.pop('text', True), capture_output=True, timeout=kw.pop('timeout', 12), **kw)


def atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(data)
        os.replace(name, path)
    finally:
        if os.path.exists(name): os.unlink(name)


def read_json(path, default):
    try: return json.loads(path.read_text())
    except (OSError, ValueError): return default


def interfaces():
    result = []
    rows = json.loads(run(['ip', '-j', '-4', 'address', 'show', 'up']).stdout)
    routes = json.loads(run(['ip', '-j', '-4', 'route', 'show', 'default']).stdout)
    preferred = [r.get('dev') for r in sorted(routes, key=lambda r: r.get('metric', 0))]
    for row in rows:
        name = row['ifname']
        # Require actual hardware. Excludes VPN, bridges, containers, loopback.
        if not (Path('/sys/class/net') / name / 'device').exists(): continue
        for addr in row.get('addr_info', []):
            if addr['scope'] != 'global': continue
            ip = ipaddress.ip_address(addr['local'])
            if not any(ip in net for net in PRIVATE): continue
            network = ipaddress.ip_network(f"{ip}/{addr['prefixlen']}", strict=False)
            result.append({'name': name, 'index': row['ifindex'], 'ip': str(ip), 'network': str(network)})
    return sorted(result, key=lambda i: preferred.index(i['name']) if i['name'] in preferred else 100)


def on_lan(ip, links=None):
    try:
        address = ipaddress.ip_address(ip)
        return any(address in ipaddress.ip_network(i['network']) and str(address) != i['ip'] for i in (links if links is not None else interfaces()))
    except ValueError: return False


def session_active():
    if run(['systemctl', '--user', 'is-active', '--quiet', 'graphical-session.target']).returncode: return False
    try:
        monitors = json.loads(run(['hyprctl', '-i', '0', '-j', 'monitors']).stdout)
        if not monitors or any('LOCK' in m.get('solitaryBlockedBy', []) for m in monitors): return False
    except (ValueError, OSError): return False
    sessions = run(['loginctl', 'list-sessions', '--no-legend']).stdout.splitlines()
    for line in sessions:
        cols = line.split()
        if len(cols) < 3 or cols[1] != str(os.getuid()): continue
        props = run(['loginctl', 'show-session', cols[0], '-p', 'Remote', '-p', 'Active', '-p', 'LockedHint']).stdout
        values = dict(x.split('=', 1) for x in props.splitlines() if '=' in x)
        if values.get('Active') == 'yes' and values.get('Remote') == 'no' and values.get('LockedHint') == 'no': return True
    return False


def identity():
    pem = Path.home() / '.config/lan-mouse/lan-mouse.pem'
    cert = run(['openssl', 'x509', '-in', str(pem), '-outform', 'DER'], text=False)
    if cert.returncode: raise ValueError('Start Glide once to create this machine’s identity.')
    digest = hashlib.sha256(cert.stdout).hexdigest()
    fingerprint = ':'.join(digest[n:n+2] for n in range(0, 64, 2))
    links = interfaces()
    return {'id': digest[:32], 'name': socket.gethostname(), 'user': getpass.getuser(),
            'fingerprint': fingerprint, 'ip': links[0]['ip'] if links else '',
            'interface': links[0]['name'] if links else '', 'active': session_active(), 'version': 1}


def model():
    me = identity()
    saved = read_json(CONFIG / 'layout.json', {'version': 1, 'revision': '', 'machines': []})
    if not saved['machines']:
        saved['machines'] = [dict(me, x=0, y=0)]
    return saved


def validate_layout(layout):
    if not isinstance(layout, dict) or layout.get('version') != 1: raise ValueError('Unsupported layout format')
    nodes = layout.get('machines', [])
    if not isinstance(nodes, list) or not 1 <= len(nodes) <= 9: raise ValueError('Use between one and nine machines')
    ids, cells = set(), set()
    for node in nodes:
        if not re.fullmatch(r'[0-9a-f]{32}', str(node.get('id', ''))): raise ValueError('Invalid device identity')
        if not re.fullmatch(r'(?:[0-9a-f]{2}:){31}[0-9a-f]{2}', str(node.get('fingerprint', ''))): raise ValueError('Invalid certificate fingerprint')
        if node['id'] != node['fingerprint'].replace(':', '')[:32]: raise ValueError('Device identity does not match certificate')
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]{0,62}', str(node.get('name', ''))): raise ValueError('Invalid host name')
        if not re.fullmatch(r'[a-z_][a-z0-9_-]{0,31}', str(node.get('user', ''))): raise ValueError('Invalid account name')
        addr = ipaddress.ip_address(node.get('ip', ''))
        if addr.version != 4 or not any(addr in n for n in PRIVATE): raise ValueError('Only private physical LAN IPv4 addresses are supported')
        x, y = node.get('x'), node.get('y')
        if type(x) is not int or type(y) is not int or not -2 <= x <= 2 or not -1 <= y <= 1: raise ValueError('Place machines inside the visible grid')
        if node['id'] in ids or (x,y) in cells: raise ValueError('Each machine needs its own grid position')
        ids.add(node['id']); cells.add((x,y))
    # Every machine must be reachable via row/column neighbors.
    reached = {nodes[0]['id']}
    while True:
        previous = len(reached)
        for node in nodes:
            if node['id'] in reached:
                reached.update(n['id'] for n in neighbors(node, nodes).values())
        if len(reached) == previous: break
    if len(reached) != len(nodes): raise ValueError('Align each machine with another in a row or column')
    return nodes


def neighbors(node, nodes):
    result = {}
    for other in nodes:
        dx, dy = other['x']-node['x'], other['y']-node['y']
        if dx == dy == 0 or (dx and dy): continue
        side = ('right' if dx > 0 else 'left') if dx else ('bottom' if dy > 0 else 'top')
        distance = abs(dx)+abs(dy)
        if side not in result or distance < abs(result[side]['x']-node['x'])+abs(result[side]['y']-node['y']): result[side] = other
    return result


def render_config(layout, me):
    nodes = validate_layout(layout)
    local = next((n for n in nodes if n['id'] == me['id']), None)
    if not local: raise ValueError('This machine must be in the layout')
    if local['fingerprint'] != me['fingerprint'] or local['ip'] != me['ip']: raise ValueError('This machine’s LAN address changed; scan again')
    links = interfaces()
    for node in nodes:
        if node['id'] != me['id'] and not on_lan(node['ip'], links): raise ValueError(f"{node['name']} is outside this machine’s directly attached LAN")
    peers = neighbors(local, nodes)
    lines = ['# Managed by Omarchy Glide; use the Glide layout editor.',
             'port = 4242', 'capture_backend = "layer-shell"', 'emulation_backend = "wlroots"',
             'release_bind = ["KeyLeftCtrl", "KeyLeftShift", "KeyEsc"]',
             'bind_address = ' + json.dumps(me['ip']),
             'allowed_peer_ips = ' + json.dumps([n['ip'] for n in peers.values()]), '', '[authorized_fingerprints]']
    for peer in peers.values(): lines.append(json.dumps(peer['fingerprint']) + ' = ' + json.dumps(peer['name']))
    lines.extend(['', '[peer_fingerprints]'])
    for peer in peers.values(): lines.append(json.dumps(peer['ip']) + ' = ' + json.dumps(peer['fingerprint']))
    for side, peer in peers.items():
        # No hostname in the engine config: DNS must not introduce a VPN/public address.
        lines.extend(['', '[[clients]]', 'position = '+json.dumps(side), 'ips = '+json.dumps([peer['ip']]), 'port = 4242', 'activate_on_startup = true'])
    content = '\n'.join(lines)+'\n'
    tomllib.loads(content)
    return content


def snapshot():
    return {'config': LAN_CONFIG.read_text(), 'layout': read_json(CONFIG/'layout.json', None)}


def apply_local(layout):
    me = identity()
    if not me['active']: raise ValueError('Pairing requires an active, unlocked local desktop session')
    content = render_config(layout, me)
    old = snapshot()
    atomic(STATE / ('before-layout-' + str(time.time_ns()) + '.json'), json.dumps(old))
    atomic(LAN_CONFIG, content)
    atomic(CONFIG/'layout.json', json.dumps(layout, indent=2))
    # Preserve a user's paused state across a layout edit.
    if run(['systemctl','--user','is-active','--quiet',SERVICE]).returncode == 0:
        check = run(['systemctl','--user','restart',SERVICE])
        if check.returncode: raise ValueError('Could not restart sharing: '+check.stderr.strip())
    return old


def restore_local(old):
    if not isinstance(old.get('config'), str): raise ValueError('Invalid recovery snapshot')
    tomllib.loads(old['config'])
    atomic(LAN_CONFIG, old['config'])
    if old.get('layout') is not None: atomic(CONFIG/'layout.json', json.dumps(old['layout'], indent=2))
    else: (CONFIG/'layout.json').unlink(missing_ok=True)
    run(['systemctl','--user','try-restart',SERVICE])


def ssh_args(peer, interactive=False, tty=False):
    if not on_lan(peer['ip']): raise ValueError('Peer is not on a physical LAN')
    trust = read_json(CONFIG/'trust.json', {}).get(peer['id'], {})
    alias = trust.get('alias', peer['ip'])
    if not re.fullmatch(r'[A-Za-z0-9_.:-]+', alias): raise ValueError('Invalid SSH host identity')
    CONFIG.mkdir(parents=True, exist_ok=True, mode=0o700)
    args = ['ssh', '-o', 'HostName='+peer['ip'], '-o', 'Port=22', '-o', 'ProxyJump=none', '-o', 'ProxyCommand=none', '-o', 'PermitLocalCommand=no', '-o', 'ControlMaster=auto', '-o', 'ControlPersist=600', '-o', 'ControlPath='+str(CONFIG/'ssh-%C'), '-o', 'ConnectTimeout=5', '-o', 'ConnectionAttempts=1', '-o', 'ClearAllForwardings=yes',
            '-o', 'StrictHostKeyChecking='+('ask' if interactive else 'yes'), '-o', 'HostKeyAlias='+alias]
    if not interactive: args += ['-o','BatchMode=yes']
    if tty: args += ['-tt']
    return args + [peer['user']+'@'+peer['ip']]


def remote(peer, action, payload=None):
    if action not in ('identity','snapshot','validate','apply','restore'): raise ValueError('Invalid remote action')
    response = run(ssh_args(peer)+[REMOTE+' '+action], input=json.dumps(payload) if payload is not None else '', timeout=20)
    if response.returncode:
        raise ValueError(f"{peer['name']}: SSH authorization required or peer unavailable. "+response.stderr.strip()[-350:])
    try: data = json.loads(response.stdout)
    except ValueError: raise ValueError(f"{peer['name']}: install Glide on the remote machine first")
    if not data.get('ok'): raise ValueError(f"{peer['name']}: "+data.get('error','request failed'))
    return data['result']


def install_remote(peer):
    """Install the already-built Omarchy bundle after SSH host verification."""
    staging = '.local/share/omarchy-glide-install'
    made = run(ssh_args(peer) + ['mkdir', '-p', staging], timeout=20)
    if made.returncode:
        raise ValueError(f"{peer['name']}: could not create the remote Glide staging directory")
    command = ssh_args(peer) + ['tar', '-xzf', '-', '-C', staging]
    pipe = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
    try:
        with tarfile.open(fileobj=pipe.stdin, mode='w:gz') as archive:
            files = [
                (Path.home()/'.local/bin/omarchy-glide-engine', 'omarchy-glide-engine'),
                (PLUGIN/'Layout.qml', 'Layout.qml'),
                (PLUGIN/'manifest.json', 'manifest.json'),
                (PLUGIN/'scripts', 'scripts'),
                (PLUGIN/'omarchy-glide.service', 'omarchy-glide.service'),
                (PLUGIN/'omarchy-glide-owner.service', 'omarchy-glide-owner.service'),
                (PLUGIN/'omarchy-glide-discovery.service', 'omarchy-glide-discovery.service'),
                (PLUGIN/'remote-install.sh', 'remote-install.sh'),
            ]
            for source, name in files:
                if not source.exists():
                    # Installed plugin files live beside the helper; units are
                    # copied there by install-plugin.sh for remote packaging.
                    source = Path.home()/'.config/systemd/user'/name
                if not source.exists(): raise ValueError(f'Local Glide file is missing: {source}')
                archive.add(source, arcname=name)
        pipe.stdin.close()
        if pipe.wait(timeout=40):
            error = pipe.stderr.read().decode(errors='replace')[-300:]
            raise ValueError(f"{peer['name']}: bundle transfer failed: {error}")
    finally:
        if pipe.stdin and not pipe.stdin.closed: pipe.stdin.close()
    print('Installing Glide on the remote Omarchy desktop. SSH may ask for its sudo password…', flush=True)
    installed = subprocess.run(ssh_args(peer, interactive=True, tty=True) + ['bash', staging+'/remote-install.sh'], timeout=180)
    if installed.returncode:
        raise ValueError(f"{peer['name']}: remote Glide installation failed")
    return 'Remote Glide installation completed.'


def deploy(layout):
    nodes = validate_layout(layout)
    me = identity()
    if not me['active']: raise ValueError('Unlock this desktop before changing its layout')
    render_config(layout, me)
    peers = [n for n in nodes if n['id'] != me['id']]
    previous = model()
    removed = [n for n in previous['machines'] if n['id'] != me['id'] and n['id'] not in {x['id'] for x in nodes}]
    targets = [(n, layout) for n in peers]
    # Removed machines become standalone, revoking their old trusted neighbors too.
    targets += [(n, {'version':1, 'machines':[dict(n,x=0,y=0)]}) for n in removed]
    backups = []
    for peer, proposed in targets:
        actual = remote(peer, 'identity')
        if actual['id'] != peer['id'] or actual['fingerprint'] != peer['fingerprint']: raise ValueError(f"{peer['name']}: device identity changed; reauthorize it")
        if not actual['active']: raise ValueError(f"{peer['name']}: log in and unlock its desktop first")
        remote(peer, 'validate', proposed)
        backups.append((peer, remote(peer,'snapshot')))
    done = []
    own_backup = snapshot()
    try:
        for peer, proposed in targets:
            done.append(peer)
            remote(peer, 'apply', proposed)
        apply_local(layout)
    except Exception as exc:
        failures = []
        try: restore_local(own_backup)
        except Exception as recovery: failures.append(str(recovery))
        for peer, old in backups:
            if peer in done:
                try: remote(peer,'restore',old)
                except Exception as recovery: failures.append(str(recovery))
        raise ValueError(str(exc)+('; Recovery requires attention: '+'; '.join(failures) if failures else '; prior layout restored'))
    return layout


def inventory():
    me = identity()
    cached = read_json(CONFIG/'discovery.json', {})
    devices = cached.get('devices', []) if time.time()-cached.get('updated',0) < 20 else []
    devices = [d for d in devices if d.get('id') != me['id'] and on_lan(d.get('ip',''))]
    saved = model()
    return {'self':me,'layout':saved,'devices':devices,'lan':interfaces(),
            'discovery_running':run(['systemctl','--user','is-active','--quiet','omarchy-glide-discovery.service']).returncode == 0}
