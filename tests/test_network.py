import copy
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
