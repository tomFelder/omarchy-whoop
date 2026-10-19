#!/usr/bin/env python3
"""Install/update a user-only reader service and bar plugin."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import shutil
import subprocess
import sys

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--address', help='Bluetooth address (kept outside the repository)')
parser.add_argument('--uninstall', action='store_true')
parser.add_argument('--yes', action='store_true', help='Accept the displayed installation/removal changes')
args = parser.parse_args()
source = Path(__file__).resolve().parent
home = Path.home()
app = home / '.local/share/omarchy-whoop'
plugin = home / '.config/omarchy/plugins/community.whoop'
shell = home / '.config/omarchy/shell.json'
unit = home / '.config/systemd/user/omarchy-whoop.service'
config = home / '.config/omarchy-whoop/config.json'
settings = json.loads(shell.read_text()) if shell.exists() else {}
backup = shell.with_name('shell.json.bak-whoop-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))

def call(*cmd):
    subprocess.run(cmd, check=True)

action = 'Stop and disable the reader, remove its user service and bar entry' if args.uninstall else (
    'Install pinned Python dependencies with uv, enable the reader at login, and add the bar widget')
print(action + '. Existing bar settings will be backed up.')
if not args.yes:
    if not sys.stdin.isatty():
        raise SystemExit('Run in a terminal to confirm, or pass --yes to accept these changes.')
    if input('Continue? [y/N] ').strip().lower() not in ('y', 'yes'):
        raise SystemExit('Cancelled; no changes made.')
if not args.uninstall and not shutil.which('uv'):
    raise SystemExit('uv is required. Install it first, then rerun this command.')

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
    for name in ('BarWidget.qml', 'manifest.json', 'install.py', 'whoop.py', 'requirements.txt', 'README.md', 'LICENSE'):
        origin, destination = source / name, plugin / name
        if origin.resolve() != destination.resolve():
            shutil.copy2(origin, destination)
    call('systemctl', '--user', 'daemon-reload')
    call('systemctl', '--user', 'enable', 'omarchy-whoop.service')
    call('systemctl', '--user', 'restart', 'omarchy-whoop.service')

settings = json.loads(shell.read_text()) if shell.exists() else {}
shell.parent.mkdir(parents=True, exist_ok=True)
if shell.exists():
    shutil.copy2(shell, backup)
layout = settings.setdefault('bar', {}).setdefault('layout', {})
# Keep an existing widget's position on updates.
present = any(entry.get('id') == 'community.whoop' for entries in layout.values() for entry in entries)
if args.uninstall:
    for section, entries in layout.items():
        layout[section] = [e for e in entries if e.get('id') != 'community.whoop']
elif not present:
    center = layout.setdefault('center', [])
    index = next((i + 1 for i, entry in enumerate(center) if entry.get('id') == 'omarchy.clock'), len(center))
    center.insert(index, {'id': 'community.whoop'})
temp = shell.with_suffix('.whoop.tmp')
temp.write_text(json.dumps(settings, indent=2) + '\n')
temp.replace(shell)
if args.uninstall:
    if (plugin / '.git').exists():
        print('Git-managed plugin retained. Remove it with: omarchy plugin remove community.whoop')
    elif plugin.exists():
        for name in ('BarWidget.qml', 'manifest.json', 'install.py', 'whoop.py', 'requirements.txt', 'README.md', 'LICENSE'):
            (plugin / name).unlink(missing_ok=True)
        # Preserve any unrelated files or local additions.
        if not any(plugin.iterdir()):
            plugin.rmdir()
    unit.unlink(missing_ok=True)
    call('systemctl', '--user', 'daemon-reload')
    print('Removed widget and service. Reader and device config retained in your home directory.')
print('Bar config backup:', backup)
