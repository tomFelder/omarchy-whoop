# Omarchy WHOOP

Live heart rate from a WHOOP band in the Omarchy top bar: **♥ 72 bpm**.

A small Python Bluetooth reader and a native Quickshell widget. Hover for
connection status and band battery. Readings clear after 15 seconds without a
new measurement; the reader reconnects automatically. One reader serves every
monitor. Theme colours and bar orientation follow Omarchy.

## Requirements

- Linux with BlueZ, a Bluetooth LE adapter, and a user systemd session.
- Omarchy with the Quickshell shell/plugin system (`qs.Ui.BarWidget`). Older
  Waybar-based Omarchy releases are not supported.
- Python 3.10+ and [uv](https://docs.astral.sh/uv/).
- A WHOOP with **Heart Rate Broadcast** enabled in its phone app device settings.
  See [WHOOP's instructions](https://support.whoop.com/s/article/Heart-Rate-Broadcast?language=en_US).

Tested with a connected WHOOP on Omarchy/BlueZ, Python 3.13, and Bleak 3.0.2.
Other standard Bluetooth Heart Rate Service bands may work but are untested.

## Install

```sh
git clone https://github.com/tomFelder/omarchy-whoop.git
cd omarchy-whoop
bluetoothctl devices
python install.py --address AA:BB:CC:DD:EE:FF
```

Replace the example address with your band's address. You can omit `--address`
to find a known/discoverable device whose name contains `WHOOP`. An explicit
address is recommended when multiple bands are nearby.

Run as your normal desktop user, without sudo. The installer:

- Creates an isolated Python environment under `~/.local/share/omarchy-whoop`.
- Installs `community.whoop` under `~/.config/omarchy/plugins`.
- Enables `omarchy-whoop.service` for your user session.
- Backs up `~/.config/omarchy/shell.json`, then adds the widget immediately after the clock in the centre.

The bar hot-reloads. To update, pull this repository and rerun `python install.py`.
The existing device selection and widget position are retained.

## How it works

The reader subscribes to the standard Heart Rate Measurement characteristic
(`2A37`), decodes 8-bit/16-bit BPM and sensor-contact flags, and optionally reads
the Battery Level characteristic (`2A19`). It reuses BlueZ's known device when a
connected band is no longer advertising. New device discovery uses Bleak.

Only the latest state is written, atomically, to
`$XDG_RUNTIME_DIR/omarchy-whoop/state.json` with owner-only permissions.
The widget checks this file each second and independently rejects stale readings.
No cloud account, telemetry, or heart-rate history is used. Your Bluetooth address
stays in `~/.config/omarchy-whoop/config.json`, outside the repository.

The runtime state contains the current BPM, battery, device name, timestamps,
and connection diagnostics. It is removed when the service stops. A device
connection is shared with BlueZ; stopping the reader can disconnect the band
from this computer.

## Troubleshooting

```sh
systemctl --user status omarchy-whoop.service
cat "$XDG_RUNTIME_DIR/omarchy-whoop/state.json"
journalctl --user -u omarchy-whoop.service
systemctl --user restart omarchy-whoop.service
```

`♥ —` means there is no fresh reading. Ensure Bluetooth is enabled, the band is
nearby and worn, and Heart Rate Broadcast is on. A connected band is not proof
that notifications are arriving. Another receiver may occupy its broadcast
connection. If the Bluetooth address changes, rerun the installer with the new
address. The reader retries with a delay up to 30 seconds and reconnects if no
measurements arrive for 45 seconds.

To change the band, edit `~/.config/omarchy-whoop/config.json` then restart the
service. Supported keys are `address` (preferred) and `name` (discovery substring,
default `WHOOP`). A configured address takes precedence.

## Uninstall

```sh
python install.py --uninstall
```

Removes the widget from the bar, removes its plugin and systemd unit, and stops
and disables the reader. It backs up the bar config and preserves unrelated
widgets. The isolated runtime installation and device config remain in
`~/.local/share/omarchy-whoop` and `~/.config/omarchy-whoop` for optional manual
removal.

## Development

```sh
python -B -m unittest -v test_whoop.py
```

Tests cover packet decoding, contact flags, malformed packets, and private atomic
state replacement. Hardware verification is separate and requires a real band.
Bluetooth access uses [Bleak](https://bleak.readthedocs.io/en/latest/api/client.html)
and BlueZ's D-Bus ObjectManager. The known-device adapter relies on Bleak's BlueZ
device details structure; dependency versions are pinned for reproducibility.

MIT licensed. Unofficial project; not affiliated with WHOOP.
