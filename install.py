#!/usr/bin/env python3
"""Install/update a user-only reader service and bar plugin."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import shutil
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--address', help='Bluetooth address (kept outside the repository)')
parser.add_argument('--uninstall', action='store_true')
args = parser.parse_args()
source = Path(__file__).resolve().parent
home = Path.home()
app = home / '.local/share/omarchy-whoop'
plugin = home / '.config/omarchy/plugins/community.whoop'
shell = home / '.config/omarchy/shell.json'
unit = home / '.config/systemd/user/omarchy-whoop.service'
config = home / '.config/omarchy-whoop/config.json'
settings = json.loads(shell.read_text())
backup = shell.with_name('shell.json.bak-whoop-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))

def call(*cmd):
    subprocess.run(cmd, check=True)

if args.uninstall:
    subprocess.run(['systemctl', '--user', 'disable', '--now', 'omarchy-whoop.service'], check=False)
else:
    for directory in (app, plugin, unit.parent, config.parent):
        directory.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source / 'whoop.py', app / 'whoop.py')
    if not (app / '.venv/bin/python').exists():
        call('uv', 'venv', str(app / '.venv'))
    call('uv', 'pip', 'install', '--python', str(app / '.venv/bin/python'), '-r', str(source / 'requirements.txt'))
    if args.address or not config.exists():
        value = json.loads(config.read_text()) if config.exists() else {'name': 'WHOOP'}
        if args.address:
            value['address'] = args.address
        config.write_text(json.dumps(value, indent=2) + '\n')
        config.chmod(0o600)
    # Quote systemd arguments, including escaping literal percent specifiers.
    def quote(path):
        return '"' + str(path).replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%') + '"'
    unit.write_text('[Unit]\nDescription=WHOOP live heart rate for Omarchy\n'
                    '[Service]\nType=simple\nExecStart=' + quote(app / '.venv/bin/python') + ' ' + quote(app / 'whoop.py') + '\n'
                    'Restart=on-failure\nRestartSec=5\nUMask=0077\n'
                    'RuntimeDirectory=omarchy-whoop\nRuntimeDirectoryMode=0700\n'
                    '[Install]\nWantedBy=default.target\n')
    for name in ('BarWidget.qml', 'manifest.json'):
        shutil.copy2(source / name, plugin / name)
    call('systemctl', '--user', 'daemon-reload')
    call('systemctl', '--user', 'enable', 'omarchy-whoop.service')
    call('systemctl', '--user', 'restart', 'omarchy-whoop.service')

settings = json.loads(shell.read_text())
shutil.copy2(shell, backup)
layout = settings.setdefault('bar', {}).setdefault('layout', {})
# Keep an existing widget's position on updates.
present = any(entry.get('id') == 'community.whoop' for entries in layout.values() for entry in entries)
if args.uninstall:
    for section, entries in layout.items():
        layout[section] = [e for e in entries if e.get('id') != 'community.whoop']
elif not present:
    right = layout.setdefault('right', [])
    index = next((i for i, entry in enumerate(right) if entry.get('id') == 'omarchy.bluetooth'), len(right))
    right.insert(index, {'id': 'community.whoop'})
temp = shell.with_suffix('.whoop.tmp')
temp.write_text(json.dumps(settings, indent=2) + '\n')
temp.replace(shell)
if args.uninstall:
    if plugin.exists():
        shutil.rmtree(plugin)
    unit.unlink(missing_ok=True)
    call('systemctl', '--user', 'daemon-reload')
    print('Removed widget and service. Reader and device config retained in your home directory.')
print('Bar config backup:', backup)
