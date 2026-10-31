import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
import firewall as f

LINK = {'name': 'eth0', 'ip': '10.0.0.10', 'network': '10.0.0.0/24'}
PEER = '10.1.0.20'


class Ufw:
    """Record every `sudo ufw ...` call; no real firewall is touched."""
    def __init__(self, status='Status: active', added='Rule added'):
        self.calls, self.status, self.added = [], status, added

    def __call__(self, argv, **kw):
        assert argv[:2] == ['sudo', 'ufw'], argv
        self.calls.append(argv[2:])
        out = self.status if argv[2] == 'status' else self.added if argv[2] == 'allow' else 'Rule deleted'
        return subprocess.CompletedProcess(argv, 0, out, '')


class PeerRuleTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        for target, value in [('STATE', Path(tmp.name)), ('interfaces', lambda: [LINK]), ('manual_peers', lambda: [])]:
            patcher = patch.object(f, target, value); patcher.start(); self.addCleanup(patcher.stop)
        self.ufw = Ufw()
        run = patch.object(f.subprocess, 'run', self.ufw); run.start(); self.addCleanup(run.stop)
        quiet = patch('sys.stdout', new=__import__('io').StringIO()); quiet.start(); self.addCleanup(quiet.stop)
        which = patch.object(f.shutil, 'which', return_value='/usr/bin/ufw'); which.start(); self.addCleanup(which.stop)
        self.owned = lambda: f.read_json(f.STATE / 'firewall-rules.json', [])

    def test_rule_allows_one_address_to_the_bind_address_only(self):
        rule = f.peer_rule(LINK, PEER)
        self.assertEqual(rule[:8], ['allow', 'in', 'on', 'eth0', 'from', PEER, 'to', '10.0.0.10'])
        self.assertEqual(rule[8:], ['port', '4242', 'proto', 'udp', 'comment', f.PEER_COMMENT])
        for forbidden in ('any', '0.0.0.0', '0.0.0.0/0', '10.1.0.0/24'):
            self.assertNotIn(forbidden, rule)

    def test_add_then_remove_deletes_exactly_what_was_added(self):
        f.main(['add-peer', PEER])
        rule = f.peer_rule(LINK, PEER)
        self.assertEqual(self.owned(), [rule])
        f.main(['remove-peer', PEER])
        self.assertEqual(self.ufw.calls[-1], ['delete'] + rule)
        self.assertEqual(self.owned(), [])

    def test_remove_leaves_other_peers_and_lan_rules_alone(self):
        other = f.peer_rule(LINK, '10.1.0.21')
        lan = ['allow', 'in', 'on', 'eth0', 'from', '10.0.0.0/24', 'to', '10.0.0.10', 'port', '4242', 'proto', 'udp', 'comment', 'Omarchy Glide LAN']
        f.atomic(f.STATE / 'firewall-rules.json', __import__('json').dumps([lan, other, f.peer_rule(LINK, PEER)]))
        f.main(['remove-peer', PEER])
        self.assertEqual(self.owned(), [lan, other])
        self.assertEqual(sum(c[0] == 'delete' for c in self.ufw.calls), 1)

    def test_add_is_idempotent_in_the_owned_list(self):
        f.main(['add-peer', PEER]); f.main(['add-peer', PEER])
        self.assertEqual(len(self.owned()), 1)

    def test_non_private_or_malformed_addresses_never_reach_ufw(self):
        for bad in ['100.64.0.1', '8.8.8.8', '0.0.0.0', '10.1.0.0/24', 'any', '::1', '']:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                f.main(['add-peer', bad])
        self.assertFalse([c for c in self.ufw.calls if c[0] == 'allow'])

    def test_inactive_ufw_changes_nothing(self):
        self.ufw.status = 'Status: inactive'
        f.main(['add-peer', PEER])
        self.assertEqual([c[0] for c in self.ufw.calls], ['status']); self.assertEqual(self.owned(), [])

    def test_default_run_also_restores_rules_for_saved_peers(self):
        with patch.object(f, 'manual_peers', lambda: [{'ip': PEER}]):
            f.main([])
        self.assertIn(f.peer_rule(LINK, PEER), self.owned())

    def test_usage_errors_exit(self):
        for argv in (['add-peer'], ['bogus', PEER], ['add-peer', PEER, 'extra']):
            with self.subTest(argv=argv), self.assertRaises(SystemExit): f.main(argv)


if __name__ == '__main__': unittest.main()
