"""Execute the production observer against isolated state files."""
from pathlib import Path
import subprocess
import os
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
INIT = ROOT / 'luci-app-openkill/root/etc/init.d/openkill'
BASH = ('C:/Program Files/Git/bin/bash.exe' if os.name == 'nt' and
        Path('C:/Program Files/Git/bin/bash.exe').exists() else shutil.which('bash') or 'bash')


def shell_path(path: Path) -> str:
    return path.resolve().as_posix()

class AdblockLoadingTest(unittest.TestCase):
    def observe(self, mode, core):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            state = root / 'state'
            state.write_text(f'mode={mode}\nstate=generated\ngenerated=1\nsource_sha256=fixture\n')
            (root / 'dnsmasq_openkill_adblock.conf').write_text('local=/ads.example.test/\n')
            config = root / 'running.yaml'
            config.write_text('openkill-anti-ad' if core else 'rules: []')
            source = INIT.read_text(encoding='utf-8')
            function = source[source.index('openkill_adblock_runtime_verify()'):source.index('\ncheck_core_status()', source.index('openkill_adblock_runtime_verify()'))]
            function = function.replace('/tmp/openkill-adblock.state', shell_path(state))
            script = f'''DNSMASQ_CONF_DIR='{shell_path(root)}'
CONFIG_FILE='{shell_path(config)}'
pidof() {{ return 0; }}
openkill_core_process_present() {{ return 0; }}
{function}
openkill_adblock_runtime_verify
cat '{shell_path(state)}'
'''
            result = subprocess.run([BASH, '-c', script], capture_output=True, text=True, encoding='utf-8', errors='replace', check=True)
            return dict(x.split('=',1) for x in result.stdout.splitlines() if '=' in x)

    def test_standard_requires_dns_only(self):
        self.assertEqual(self.observe('standard', False)['verified'], '1')

    def test_enhanced_requires_both_consumers(self):
        self.assertEqual(self.observe('enhanced', False)['verified'], '0')
        self.assertEqual(self.observe('enhanced', True)['verified'], '1')

if __name__ == '__main__':
    unittest.main()
