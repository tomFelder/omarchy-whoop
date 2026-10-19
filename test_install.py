"""Exercise real installer file operations with an isolated home and mocked services."""
import json
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parent
FILES = ('install.py', 'whoop.py', 'requirements.txt', 'manifest.json', 'BarWidget.qml', 'README.md', 'LICENSE')

class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.plugin = self.home / '.config/omarchy/plugins/community.whoop'
        self.plugin.mkdir(parents=True)
        for name in FILES:
            shutil.copy2(SOURCE / name, self.plugin / name)
        (self.plugin / '.git').mkdir()
        self.shell = self.home / '.config/omarchy/shell.json'
        self.initial = {'idle': {'lock': 300}, 'bar': {'layout': {
            'center': [{'id': 'omarchy.clock'}, {'id': 'omarchy.weather'}],
            'right': [{'id': 'omarchy.bluetooth'}]}}}
        self.shell.write_text(json.dumps(self.initial))

    def invoke(self, *args, source=None):
        script = (source or self.plugin) / 'install.py'
        with patch('pathlib.Path.home', return_value=self.home), \
             patch.object(sys, 'argv', [str(script), *args]), \
             patch('subprocess.run', return_value=subprocess.CompletedProcess([], 0)) as run, \
             patch('shutil.which', return_value='/usr/bin/uv'), \
             patch('builtins.print'):
            runpy.run_path(str(script), run_name='__main__')
        return [call.args[0] for call in run.call_args_list]

    def test_marketplace_install_in_place_and_login_startup(self):
        calls = self.invoke('--yes')
        self.assertIn(('systemctl', '--user', 'enable', 'omarchy-whoop.service'), calls)
        self.assertIn(('systemctl', '--user', 'restart', 'omarchy-whoop.service'), calls)
        unit = (self.home / '.config/systemd/user/omarchy-whoop.service').read_text()
        self.assertIn('WantedBy=default.target', unit)
        layout = json.loads(self.shell.read_text())['bar']['layout']
        self.assertEqual([x['id'] for x in layout['center']],
                         ['omarchy.clock', 'community.whoop', 'omarchy.weather'])
        self.assertTrue((self.plugin / '.git').exists())
        self.assertTrue(list(self.shell.parent.glob('shell.json.bak-whoop-*')))

    def test_update_keeps_custom_position_and_device(self):
        self.invoke('--yes', '--address', 'AA:BB:CC:DD:EE:FF')
        settings = json.loads(self.shell.read_text())
        settings['bar']['layout']['center'].remove({'id': 'community.whoop'})
        settings['bar']['layout']['right'].append({'id': 'community.whoop'})
        self.shell.write_text(json.dumps(settings))
        self.invoke('--yes')
        self.assertEqual(json.loads(self.shell.read_text()), settings)
        config = json.loads((self.home / '.config/omarchy-whoop/config.json').read_text())
        self.assertEqual(config['address'], 'AA:BB:CC:DD:EE:FF')

    def test_uninstall_preserves_checkout_and_unrelated_settings(self):
        self.invoke('--yes')
        calls = self.invoke('--uninstall', '--yes')
        self.assertIn(['systemctl', '--user', 'disable', '--now', 'omarchy-whoop.service'], calls)
        self.assertEqual(json.loads(self.shell.read_text()), self.initial)
        self.assertTrue((self.plugin / '.git').exists())
        self.assertFalse((self.home / '.config/systemd/user/omarchy-whoop.service').exists())

    def test_standalone_install_and_safe_removal(self):
        checkout = self.home / 'source'
        checkout.mkdir()
        for name in FILES:
            shutil.copy2(SOURCE / name, checkout / name)
        (self.plugin / '.git').rmdir()
        extra = self.plugin / 'personal-notes.txt'
        extra.write_text('keep me')
        self.invoke('--yes', source=checkout)
        self.assertTrue((self.plugin / 'install.py').exists())
        self.invoke('--uninstall', '--yes', source=checkout)
        self.assertEqual(extra.read_text(), 'keep me')
        self.assertFalse((self.plugin / 'manifest.json').exists())

    def test_noninteractive_requires_explicit_consent(self):
        with patch('sys.stdin.isatty', return_value=False), self.assertRaises(SystemExit):
            self.invoke()
        self.assertEqual(json.loads(self.shell.read_text()), self.initial)
        self.assertFalse((self.home / '.local/share/omarchy-whoop').exists())

if __name__ == '__main__':
    unittest.main()
