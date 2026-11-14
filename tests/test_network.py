import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
import glide_network as g


def node(name, digit, x, y, ip):
    fp=':'.join([digit*2]*32)
    return {'id':fp.replace(':','')[:32], 'name':name, 'user':'pi', 'ip':ip, 'fingerprint':fp, 'x':x, 'y':y, 'active':True}

VIC=node('vic','a',0,0,'10.0.0.10')
GUS=node('gus','b',-1,0,'10.0.0.11')
THIRD=node('third','c',-2,0,'10.0.0.12')
LINKS=[{'name':'eth0','ip':'10.0.0.10','network':'10.0.0.0/24'}]

class NetworkTests(unittest.TestCase):
    def test_nearest_neighbors_support_three_machine_chain(self):
        nodes=[VIC,GUS,THIRD]
        self.assertEqual(g.neighbors(VIC,nodes)['left']['name'],'gus')
        self.assertEqual({k:v['name'] for k,v in g.neighbors(GUS,nodes).items()},{'right':'vic','left':'third'})
        self.assertEqual(g.neighbors(THIRD,nodes)['right']['name'],'gus')
        g.validate_layout({'version':1,'machines':nodes})

    def test_three_dimensions_of_layout_validation(self):
        bads=[dict(GUS,x=0,y=0),dict(GUS,x=-1,y=-1),dict(GUS,x=-3,y=0)]
        for bad in bads:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                g.validate_layout({'version':1,'machines':[VIC,bad]})

    def test_network_and_identity_attacks_rejected(self):
        for extra in [{'ip':'100.75.37.107'},{'ip':'8.8.8.8'}, {'user':'-oProxyCommand=bad'}, {'name':'gus;bad'}, {'fingerprint':VIC['fingerprint']}, {'x':True}]:
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                g.validate_layout({'version':1,'machines':[VIC,dict(GUS,**extra)]})

    def test_lan_addresses_must_be_directly_attached(self):
        self.assertTrue(g.on_lan('10.0.0.11',LINKS))
        for ip in ['10.0.1.11','100.64.0.1','127.0.0.1','8.8.8.8','10.0.0.10','invalid']:
            self.assertFalse(g.on_lan(ip,LINKS))

    def test_config_has_no_dns_or_vpn_and_only_adjacent_certificates(self):
        with patch.object(g,'interfaces',return_value=LINKS):
            rendered=g.render_config({'version':1,'machines':[VIC,GUS,THIRD]},VIC)
        config=g.tomllib.loads(rendered)
        self.assertEqual(config['bind_address'],VIC['ip'])
        self.assertEqual(config['allowed_peer_ips'],[GUS['ip']])
        self.assertEqual(config['peer_fingerprints'],{GUS['ip']:GUS['fingerprint']})
        self.assertNotIn('hostname',config['clients'][0])
        self.assertEqual(config['authorized_fingerprints'],{GUS['fingerprint']:'gus'})
        self.assertEqual(config['clients'][0]['position'],'left')

    def test_remote_identity_mismatch_never_applies_any_config(self):
        with patch.object(g,'identity',return_value=VIC), patch.object(g,'interfaces',return_value=LINKS), patch.object(g,'model',return_value={'machines':[VIC]}), patch.object(g,'remote',return_value=dict(GUS,fingerprint=VIC['fingerprint'])) as remote, patch.object(g,'apply_local') as apply:
            with self.assertRaisesRegex(ValueError,'identity changed'):
                g.deploy({'version':1,'machines':[VIC,GUS]})
            apply.assert_not_called()
            self.assertEqual(remote.call_count,1)

    def test_partial_remote_failure_rolls_back_changed_peers(self):
        calls=[]
        def remote(peer,action,payload=None):
            calls.append((peer['name'],action))
            if action=='identity': return peer
            if action=='validate': return True
            if action=='snapshot': return {'config':'old','layout':None}
            if action=='apply' and peer['name']=='third': raise ValueError('simulated connection loss')
            return True
        with patch.object(g,'identity',return_value=VIC), patch.object(g,'interfaces',return_value=LINKS), patch.object(g,'model',return_value={'machines':[VIC]}), patch.object(g,'snapshot',return_value={'config':'local-old'}), patch.object(g,'restore_local') as restore, patch.object(g,'remote',side_effect=remote):
            with self.assertRaisesRegex(ValueError,'prior layout restored'):
                g.deploy({'version':1,'machines':[VIC,GUS,THIRD]})
            self.assertIn(('gus','restore'),calls)
            self.assertIn(('third','restore'),calls)
            restore.assert_called_once()

    def test_atomic_writes_are_private(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'config'
            g.atomic(p,'first'); g.atomic(p,'second')
            self.assertEqual(p.read_text(),'second')
            self.assertEqual(p.stat().st_mode & 0o777,0o600)

if __name__=='__main__': unittest.main()


class SessionActiveTests(unittest.TestCase):
    """Hyprland reports solitaryBlockedBy as null when nothing blocks scanout."""

    def _hypr(self, monitors):
        class Result:
            def __init__(self, stdout='', returncode=0):
                self.stdout, self.returncode = stdout, returncode

        def fake(argv, **kw):
            if argv[0] == 'systemctl': return Result(returncode=0)
            if argv[0] == 'hyprctl': return Result(stdout=json.dumps(monitors))
            if argv[:2] == ['loginctl', 'list-sessions']: return Result(stdout='3 1000 pi seat0 tty2\n')
            return Result(stdout='Active=yes\nRemote=no\nLockedHint=no\n')
        return fake

    def test_null_solitary_block_does_not_raise(self):
        with patch.object(g, 'run', self._hypr([{'name': 'DVI-I-1', 'solitaryBlockedBy': None}])), \
             patch.object(g.os, 'getuid', return_value=1000):
            self.assertTrue(g.session_active())

    def test_lock_block_still_reports_inactive(self):
        with patch.object(g, 'run', self._hypr([{'name': 'DVI-I-1', 'solitaryBlockedBy': ['LOCK']}])), \
             patch.object(g.os, 'getuid', return_value=1000):
            self.assertFalse(g.session_active())

    def test_missing_key_is_treated_as_unblocked(self):
        with patch.object(g, 'run', self._hypr([{'name': 'DVI-I-1'}])), \
             patch.object(g.os, 'getuid', return_value=1000):
            self.assertTrue(g.session_active())


# A second subnet reached through a router, as on a home VLAN setup.
ROUTED=node('routed','d',1,0,'10.1.0.20')
LINKS_TWO=[{'name':'eth0','ip':'10.0.0.10','network':'10.0.0.0/24'},{'name':'wlan0','ip':'10.0.0.11','network':'10.0.0.0/24'}]


def routed(ip,dev='eth0'):
    """Pretend the kernel routes the probe out of `dev`."""
    return patch.object(g,'routed_via',return_value=dev)


class RoutedPeerTests(unittest.TestCase):
    def test_private_ip_parser_refuses_everything_that_is_not_rfc1918(self):
        for ip in ['100.64.0.1','100.100.100.100','8.8.8.8','127.0.0.1','169.254.1.1','0.0.0.0','224.0.0.1','::1','fd00::1','10.0.0','nonsense','','10.0.0.1/24']:
            with self.subTest(ip=ip), self.assertRaises(ValueError):
                g.parse_private_ip(ip)
        for ip in ['10.1.0.20','172.16.5.5','192.168.50.2',' 10.1.0.20 ']:
            with self.subTest(ip=ip): g.parse_private_ip(ip)
        with self.assertRaisesRegex(ValueError,'own address'): g.parse_private_ip('10.0.0.10',own={'10.0.0.10'})

    def test_routed_peer_needs_a_route_out_of_the_physical_bind_interface(self):
        with routed(ROUTED['ip']): self.assertTrue(g.routed_ok(ROUTED['ip'],LINKS))
        for dev in ['tailscale0','wg0','docker0','']:
            with self.subTest(dev=dev), routed(ROUTED['ip'],dev): self.assertFalse(g.routed_ok(ROUTED['ip'],LINKS))
        # The engine binds to the first link, so leaving through the second NIC is refused too.
        with routed(ROUTED['ip'],'wlan0'): self.assertFalse(g.routed_ok(ROUTED['ip'],LINKS_TWO))

    def test_routed_peer_still_refuses_non_private_loopback_own_and_no_links(self):
        with routed('x') as probe:
            for ip in ['100.64.0.1','8.8.8.8','127.0.0.1','10.0.0.10','10.0.0.11','invalid']:
                with self.subTest(ip=ip): self.assertFalse(g.routed_ok(ip,LINKS_TWO))
            self.assertFalse(g.routed_ok(ROUTED['ip'],[]))
            probe.assert_not_called()

    def test_route_probe_uses_the_bound_source_and_rejects_non_unicast_routes(self):
        class Done:
            def __init__(self,out,code=0): self.stdout,self.returncode=out,code
        seen=[]
        def fake(out,code=0):
            def run(argv,**kw): seen.append(argv); return Done(out,code)
            return run
        with patch.object(g,'run',fake('[{"dst":"10.1.0.20","gateway":"10.0.0.1","dev":"eth0"}]')):
            self.assertEqual(g.routed_via('10.1.0.20','10.0.0.10'),'eth0')
        self.assertEqual(seen[0],['ip','-j','-4','route','get','10.1.0.20','from','10.0.0.10'])
        for out,code in [('[{"dev":"lo","type":"local"}]',0),('[{"dev":"eth0","type":"unreachable"}]',0),('',2),('not json',0),('[]',0),('{}',0)]:
            with self.subTest(out=out), patch.object(g,'run',fake(out,code)):
                self.assertEqual(g.routed_via('10.1.0.20','10.0.0.10'),'')

    def test_routed_acceptance_requires_the_manual_flag(self):
        manual=dict(ROUTED,manual=True)
        with routed(ROUTED['ip']):
            self.assertFalse(g.peer_allowed(ROUTED,LINKS))
            self.assertFalse(g.peer_allowed(dict(ROUTED,manual='yes'),LINKS))
            self.assertFalse(g.peer_allowed(dict(ROUTED,manual=1),LINKS))
            self.assertTrue(g.peer_allowed(manual,LINKS))
            self.assertTrue(g.peer_allowed(GUS,LINKS))   # attached peers need no flag
        with routed(ROUTED['ip'],'tun0'): self.assertFalse(g.peer_allowed(manual,LINKS))
        with routed('x'): self.assertFalse(g.peer_allowed(dict(ROUTED,ip='100.64.0.9',manual=True),LINKS))

    def test_layout_rejects_a_non_boolean_manual_flag(self):
        for bad in ['true',1,None,[]]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                g.validate_layout({'version':1,'machines':[VIC,dict(GUS,manual=bad)]})
        g.validate_layout({'version':1,'machines':[VIC,dict(GUS,manual=True)]})

    def test_config_for_a_routed_peer_stays_bound_to_the_lan_address(self):
        layout={'version':1,'machines':[VIC,dict(ROUTED,x=-1,manual=True)]}
        with patch.object(g,'interfaces',return_value=LINKS), routed(ROUTED['ip']):
            config=g.tomllib.loads(g.render_config(layout,VIC))
        self.assertEqual(config['bind_address'],VIC['ip'])
        self.assertNotIn(config['bind_address'],('0.0.0.0','::'))
        self.assertEqual(config['allowed_peer_ips'],[ROUTED['ip']])
        self.assertEqual(config['peer_fingerprints'],{ROUTED['ip']:ROUTED['fingerprint']})
        self.assertEqual(config['clients'][0]['ips'],[ROUTED['ip']])

    def test_config_refuses_unflagged_or_unroutable_peers(self):
        layout=lambda **kw:{'version':1,'machines':[VIC,dict(ROUTED,x=-1,**kw)]}
        with patch.object(g,'interfaces',return_value=LINKS), routed(ROUTED['ip']):
            with self.assertRaisesRegex(ValueError,'directly attached'): g.render_config(layout(),VIC)
        with patch.object(g,'interfaces',return_value=LINKS), routed(ROUTED['ip'],'wg0'):
            with self.assertRaisesRegex(ValueError,'physical LAN interface'): g.render_config(layout(manual=True),VIC)

    def test_ssh_to_a_routed_peer_is_pinned_and_gated(self):
        manual=dict(ROUTED,manual=True)
        with patch.object(g,'interfaces',return_value=LINKS), routed(ROUTED['ip']):
            with self.assertRaisesRegex(ValueError,'physical LAN'): g.ssh_args(ROUTED)
            args=g.ssh_args(manual)
        self.assertIn('ProxyJump=none',args); self.assertIn('ProxyCommand=none',args)
        self.assertIn('StrictHostKeyChecking=yes',args); self.assertEqual(args[-1],'pi@'+ROUTED['ip'])
        with patch.object(g,'interfaces',return_value=LINKS), routed(ROUTED['ip']):
            self.assertIn('StrictHostKeyChecking=ask',g.ssh_args(manual,interactive=True))


class ManualPeerStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        patcher=patch.object(g,'CONFIG',Path(self.tmp.name)/'cfg'); patcher.start(); self.addCleanup(patcher.stop)
        self.store=g.CONFIG/'manual-peers.json'

    def test_save_load_and_replace_by_id_or_address(self):
        g.save_manual_peer(ROUTED)
        self.assertEqual(g.manual_peers(),[{k:ROUTED[k] for k in ('id','name','user','fingerprint','ip')}|{'manual':True}])
        g.save_manual_peer(dict(ROUTED,name='renamed'))
        self.assertEqual([p['name'] for p in g.manual_peers()],['renamed'])
        self.assertEqual(self.store.stat().st_mode & 0o777,0o600)

    def test_hand_edited_or_hostile_entries_are_dropped(self):
        good={k:ROUTED[k] for k in ('id','name','user','fingerprint','ip')}
        rows=[good,dict(good,ip='100.64.0.1'),dict(good,user='-oProxyCommand=x'),dict(good,name='a;b'),dict(good,id='0'*32),'text',None,{}]
        self.store.parent.mkdir(parents=True); self.store.write_text(json.dumps(rows))
        self.assertEqual(len(g.manual_peers()),1)
        self.store.write_text('not json'); self.assertEqual(g.manual_peers(),[])
        self.store.write_text('{"a":1}'); self.assertEqual(g.manual_peers(),[])

    def test_count_is_capped(self):
        for n in range(g.MAX_MANUAL):
            fp=':'.join([('%02x'%(n+1))]*32)
            g.save_manual_peer(dict(node('p%d'%n,'e',0,0,'10.1.0.%d'%(n+30)),fingerprint=fp,id=fp.replace(':','')[:32]))
        with self.assertRaisesRegex(ValueError,'At most'): g.save_manual_peer(ROUTED)

    def test_forget_removes_rule_before_record_and_keeps_layout_members(self):
        g.save_manual_peer(ROUTED)
        order=[]
        with patch.object(g,'model',return_value={'machines':[VIC,ROUTED]}), patch.object(g,'firewall') as fw:
            with self.assertRaisesRegex(ValueError,'still in the layout'): g.forget_manual_peer('routed')
            fw.assert_not_called(); self.assertEqual(len(g.manual_peers()),1)
        with patch.object(g,'model',return_value={'machines':[VIC]}), patch.object(g,'firewall',side_effect=ValueError('ufw failed')):
            with self.assertRaisesRegex(ValueError,'ufw failed'): g.forget_manual_peer(ROUTED['ip'])
            self.assertEqual(len(g.manual_peers()),1)       # rule not removed, so the entry stays for a retry
        with patch.object(g,'model',return_value={'machines':[VIC]}), patch.object(g,'firewall',side_effect=lambda a,ip:order.append((a,ip))):
            self.assertEqual(g.forget_manual_peer(ROUTED['id'])['name'],'routed')
        self.assertEqual(order,[('remove-peer',ROUTED['ip'])]); self.assertEqual(g.manual_peers(),[])
        with self.assertRaisesRegex(ValueError,'No saved address'): g.forget_manual_peer('nobody')

    def test_manual_devices_flag_reachability(self):
        g.save_manual_peer(ROUTED)
        with routed(ROUTED['ip']): devices=g.manual_devices(VIC,LINKS)
        self.assertTrue(devices[0]['reachable']); self.assertTrue(devices[0]['manual'])
        with routed(ROUTED['ip'],'wg0'): self.assertFalse(g.manual_devices(VIC,LINKS)[0]['reachable'])
        self.assertEqual(g.manual_devices(ROUTED,LINKS),[])   # never lists this machine itself


class ReceiverViewTests(unittest.TestCase):
    """The machine on the far side of a routed link must accept the initiator too.

    The initiator never carries a `manual` flag for itself, so before
    `as_seen_by_peers` the far machine rejected the very layout it was sent and
    `deploy` failed at the validate step for every routed pair.
    """
    FAR_LINKS=[{'name':'eth0','ip':ROUTED['ip'],'network':'10.1.0.0/24'}]
    LAYOUT={'version':1,'machines':[VIC,dict(ROUTED,x=-1,manual=True)]}

    def test_far_machine_rejects_the_layout_as_the_panel_wrote_it(self):
        with patch.object(g,'interfaces',return_value=self.FAR_LINKS), routed(VIC['ip']):
            with self.assertRaisesRegex(ValueError,'vic is outside this machine.s directly attached LAN'):
                g.render_config(self.LAYOUT,ROUTED)

    def test_far_machine_accepts_the_layout_as_sent(self):
        sent=g.as_seen_by_peers(self.LAYOUT)
        with patch.object(g,'interfaces',return_value=self.FAR_LINKS), routed(VIC['ip']):
            config=g.tomllib.loads(g.render_config(sent,ROUTED))
        self.assertEqual(config['bind_address'],ROUTED['ip'])
        self.assertEqual(config['allowed_peer_ips'],[VIC['ip']])
        self.assertEqual(config['peer_fingerprints'],{VIC['ip']:VIC['fingerprint']})

    def test_far_machine_still_checks_its_own_route(self):
        sent=g.as_seen_by_peers(self.LAYOUT)
        with patch.object(g,'interfaces',return_value=self.FAR_LINKS):
            for dev in ['tun0','wg0','']:
                with self.subTest(dev=dev), routed(VIC['ip'],dev), self.assertRaisesRegex(ValueError,'physical LAN interface'):
                    g.render_config(sent,ROUTED)

    def test_flag_is_added_to_every_machine_and_the_input_is_untouched(self):
        sent=g.as_seen_by_peers(self.LAYOUT)
        self.assertTrue(all(n['manual'] is True for n in sent['machines']))
        self.assertEqual(sent['version'],1)
        self.assertNotIn('manual',self.LAYOUT['machines'][0])
        g.validate_layout(sent)

    def test_layout_without_an_address_added_machine_is_sent_unchanged(self):
        plain={'version':1,'machines':[VIC,GUS]}
        self.assertIs(g.as_seen_by_peers(plain),plain)
        loose={'version':1,'machines':[VIC,dict(GUS,manual=False)]}
        self.assertIs(g.as_seen_by_peers(loose),loose)

    def test_deploy_validates_and_applies_the_flagged_layout_on_the_far_machine(self):
        seen=[]
        def remote(peer,action,payload=None):
            seen.append((action,payload))
            return {'identity':dict(ROUTED,active=True),'snapshot':{}}.get(action,True)
        with patch.object(g,'identity',return_value=dict(VIC,active=True)), patch.object(g,'interfaces',return_value=LINKS), routed(ROUTED['ip']), \
             patch.object(g,'model',return_value={'machines':[VIC]}), patch.object(g,'remote',remote), \
             patch.object(g,'snapshot',return_value={}), patch.object(g,'apply_local') as apply:
            g.deploy(self.LAYOUT)
        sent=[p for a,p in seen if a in ('validate','apply')]
        self.assertEqual([a for a,_ in seen if a in ('validate','apply')],['validate','apply'])
        for payload in sent: self.assertTrue(all(n['manual'] is True for n in payload['machines']))
        apply.assert_called_once_with(self.LAYOUT)          # this machine keeps its own, unflagged copy
        self.assertNotIn('manual',apply.call_args[0][0]['machines'][0])


class AddManualPeerTests(unittest.TestCase):
    """The add flow with SSH, install, firewall and the peer's identity all faked."""
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        config=patch.object(g,'CONFIG',Path(self.tmp.name)/'cfg'); config.start(); self.addCleanup(config.stop)
        self.calls=[]
        self.identity=dict(ROUTED,active=True)
        def started(name,result=None):
            def f(*a,**k): self.calls.append(name); return result
            return f
        class Done: returncode=0
        self.ssh=Done()
        for target,new in [('identity',lambda:VIC),('interfaces',lambda:LINKS),('routed_via',lambda ip,src:'eth0'),
                           ('install_remote',started('install')),('remote',lambda peer,action,payload=None:(self.calls.append(action),self.identity)[1]),
                           ('firewall',lambda a,ip:self.calls.append('fw-'+a))]:
            patcher=patch.object(g,target,new); patcher.start(); self.addCleanup(patcher.stop)
        run=patch.object(g.subprocess,'run',lambda argv,**k:(self.calls.append('ssh'),self.ssh)[1]); run.start(); self.addCleanup(run.stop)
        say=lambda *a,**k:None
        self.add=lambda ip=ROUTED['ip'],user='pi':g.add_manual_peer(ip,user,say=say)

    def test_success_verifies_ssh_installs_reads_identity_then_opens_firewall_then_saves(self):
        found=self.add()
        self.assertEqual(self.calls,['ssh','install','identity','fw-add-peer'])
        self.assertEqual((found['id'],found['ip'],found['manual']),(ROUTED['id'],ROUTED['ip'],True))
        self.assertEqual([p['id'] for p in g.manual_peers()],[ROUTED['id']])

    def test_bad_input_never_reaches_ssh(self):
        for ip,user in [('100.64.0.4','pi'),('8.8.8.8','pi'),('127.0.0.1','pi'),(VIC['ip'],'pi'),('nonsense','pi'),(ROUTED['ip'],'-oProxyCommand=x'),(ROUTED['ip'],'Bad User'),(ROUTED['ip'],'')]:
            with self.subTest(ip=ip,user=user), self.assertRaises(ValueError): self.add(ip,user)
        self.assertEqual(self.calls,[])

    def test_vpn_routed_address_is_refused_before_ssh(self):
        with patch.object(g,'routed_via',lambda ip,src:'tailscale0'):
            with self.assertRaisesRegex(ValueError,'VPN and virtual'): self.add()
        self.assertEqual(self.calls,[])

    def test_declined_ssh_host_verification_saves_nothing(self):
        self.ssh.returncode=255
        with self.assertRaisesRegex(ValueError,'not completed'): self.add()
        self.assertEqual(self.calls,['ssh']); self.assertEqual(g.manual_peers(),[])

    def test_identity_that_disagrees_with_the_request_is_refused(self):
        for change,message in [({'ip':'10.1.0.99'},'does not use the address'),({'user':'other'},'account differs'),
                               ({'id':VIC['id'],'fingerprint':VIC['fingerprint']},'this machine'),({'fingerprint':'zz'},'Invalid certificate'),({'name':'bad;name'},'Invalid host name')]:
            with self.subTest(change=change):
                self.identity=dict(ROUTED,active=True,**change); self.calls.clear()
                with self.assertRaisesRegex(ValueError,message): self.add()
                self.assertNotIn('fw-add-peer',self.calls); self.assertEqual(g.manual_peers(),[])

    def test_firewall_failure_saves_nothing(self):
        def boom(action,ip): raise ValueError('Could not update the firewall rule for that address')
        with patch.object(g,'firewall',boom), self.assertRaisesRegex(ValueError,'firewall'): self.add()
        self.assertEqual(g.manual_peers(),[])
