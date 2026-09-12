#!/usr/bin/env python3
"""Deterministic Stage D apply/generation checks (no router required)."""
import os, subprocess, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "luci-app-openkill/root/usr/share/openkill/openkill_network.sh"
INIT = ROOT / "luci-app-openkill/root/etc/init.d/openkill"

def run(fn, *args, env=None):
    script = '. "$1"; ' + fn + ' ' + ' '.join('"$%d"' % (i + 2) for i in range(len(args)))
    return subprocess.run(["sh", "-c", script, "stage-d", str(HELPER), *map(str, args)], text=True,
                          capture_output=True, env=env or os.environ.copy(), check=True).stdout

class StageD(unittest.TestCase):
    def test_atomic_batch_is_stable_and_scoped(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d); v4=p/'v4'; v6=p/'v6'; out=p/'batch'
            v4.write_text('203.0.113.2\n203.0.113.1\n')
            v6.write_text('2001:db8::2\n')
            run('openkill_render_nft_set_batch', v4, v6, out)
            text=out.read_text()
            self.assertIn('flush set inet fw4 openkill_node4', text)
            self.assertIn('add element inet fw4 openkill_node4 { 203.0.113.1 }', text)
            self.assertNotIn('flush ruleset', text)
            self.assertNotIn('flush table inet fw4', text)
            self.assertEqual(run('openkill_validate_nft_batch', out), '')

    def test_dynamic_set_batch_is_stable_and_scoped(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); elements=p/'elements'; out=p/'batch'
            elements.write_text('fd00::/8\nfd00:1::/48\n')
            run('openkill_render_nft_set_update_batch', 6, 'localnetwork6', elements, out)
            text=out.read_text()
            self.assertEqual(text.splitlines()[0], 'flush set inet fw4 localnetwork6')
            self.assertIn('add element inet fw4 localnetwork6 { fd00::/8 }', text)
            self.assertNotIn('flush ruleset', text)

    def test_classifier_golden_order(self):
        self.assertEqual(run('openkill_render_classifier_order').split(),
            'CONTROL_BYPASS SELF_BYPASS NODE_BYPASS LOCAL_BYPASS USER_BYPASS CHINA_DIRECT USER_PROXY DEFAULT_POLICY'.split())

    def test_classifier_match_is_used_by_runtime(self):
        self.assertEqual(run('openkill_classifier_match', 4, 'NODE_BYPASS').strip(), 'ip daddr @openkill_node4 counter return')
        self.assertEqual(run('openkill_classifier_match', 6, 'NODE_BYPASS').strip(), 'ip6 daddr @openkill_node6 counter return')
        self.assertIn('openkill_classifier_match 4 NODE_BYPASS', INIT.read_text())

    def test_minimal_apply_noop_and_runtime_loss(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); desired=p/'desired'; applied=p/'applied'; runtime=p/'runtime'
            payload='TUN_OWNER=openkill\nLOCALNETWORK6_PREFIXES=fd00::/8\nNODE4_ENDPOINTS=203.0.113.1\nNODE6_ENDPOINTS=2001:db8::1\n'
            desired.write_text(payload); applied.write_text(payload); runtime.write_text('NFT_CHAIN_PRESENT=1\n')
            self.assertEqual(run('openkill_minimal_apply_action', desired, applied, runtime).strip(), 'NO_ACTION')
            runtime.write_text('NFT_CHAIN_PRESENT=0\n')
            self.assertEqual(run('openkill_minimal_apply_action', desired, applied, runtime).strip(), 'REAPPLY_NFT')

    def test_dns_generation_deduplicates_and_is_family_aware(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); domains=p/'domains'; out4=p/'4'; out6=p/'6'
            domains.write_text('example.com\n# ignored\nexample.com\n test.example\n192.0.2.0/24\n')
            run('openkill_render_dns_set_rules', 4, domains, 'china_ip_route_pass', out4, 'nftset')
            run('openkill_render_dns_set_rules', 6, domains, 'china_ip6_route_pass', out6, 'nftset')
            self.assertEqual(out4.read_text().splitlines(), ['nftset=/example.com/4#inet#fw4#china_ip_route_pass','nftset=/test.example/4#inet#fw4#china_ip_route_pass'])
            self.assertTrue(all('/6#inet#fw4#china_ip6_route_pass' in x for x in out6.read_text().splitlines()))

    def test_init_uses_bounded_batch_and_fallback(self):
        text=INIT.read_text()
        self.assertIn('openkill_render_nft_set_batch', text)
        self.assertIn('nft -f /tmp/openkill-node-sets.batch', text)
        self.assertIn('Compatibility fallback', text)

if __name__ == '__main__':
    unittest.main()
