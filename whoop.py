#!/usr/bin/env python3
"""Local BLE heart-rate reader; current state only, no history."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import signal
import time

HR = '00002a37-0000-1000-8000-00805f9b34fb'
BATTERY = '00002a19-0000-1000-8000-00805f9b34fb'


def parse_measurement(data):
    """Decode the mandatory BPM and optional sensor-contact flags (Bluetooth HRS)."""
    if not data:
        raise ValueError('Empty heart-rate packet')
    size = 2 if data[0] & 1 else 1
    if len(data) < size + 1:
        raise ValueError('Truncated heart-rate packet')
    bpm = int.from_bytes(data[1:1 + size], 'little')
    contact = bool(data[0] & 2) if data[0] & 4 else None
    return bpm, contact


class State:
    def __init__(self, path):
        self.path = path
        self.value = dict(status='starting', bpm=None, battery=None, measured_at=0)

    def update(self, **values):
        self.value.update(values)
        self.value['updated_at'] = time.time()
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        temp = self.path.with_suffix('.tmp')
        temp.write_text(json.dumps(self.value) + '\n')
        temp.chmod(0o600)
        temp.replace(self.path)


async def known_device(config):
    """Resolve an already-known BlueZ device, including one no longer advertising."""
    from bleak.backends.device import BLEDevice
    from dbus_fast import BusType, Message, MessageType
    from dbus_fast.aio import MessageBus
    bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
    try:
        reply = await bus.call(Message(destination='org.bluez', path='/',
            interface='org.freedesktop.DBus.ObjectManager', member='GetManagedObjects'))
        if reply.message_type == MessageType.ERROR:
            return None
        for path, interfaces in reply.body[0].items():
            props = interfaces.get('org.bluez.Device1')
            if not props:
                continue
            props = {key: value.value for key, value in props.items()}
            address = props.get('Address', '')
            name = props.get('Name', '')
            requested = config.get('address')
            matches = address.casefold() == requested.casefold() if requested else (
                config.get('name', 'WHOOP').casefold() in name.casefold())
            if matches:
                return BLEDevice(address, name, {'path': path, 'props': props})
    finally:
        bus.disconnect()
    return None


async def run(config, state, stop):
    from bleak import BleakClient, BleakScanner
    retry = 2
    while not stop.is_set():
        try:
            state.update(status='connecting', bpm=None, battery=None, measured_at=0)
            disconnected = asyncio.Event()
            target = await known_device(config)
            if target is None and config.get('address'):
                target = config['address']
            if not target:
                wanted = config.get('name', 'WHOOP').casefold()
                target = await BleakScanner.find_device_by_filter(
                    lambda d, a: wanted in (a.local_name or d.name or '').casefold(), timeout=15)
                if target is None:
                    raise RuntimeError('Band not found; enable Heart Rate Broadcast')
            async with BleakClient(target, disconnected_callback=lambda _: disconnected.set(), timeout=20) as client:
                state.update(status='waiting', name=client.name, message='')
                last_received = time.monotonic()

                def received(_, data):
                    nonlocal last_received, retry
                    try:
                        bpm, contact = parse_measurement(data)
                    except ValueError:
                        return
                    last_received = time.monotonic()
                    retry = 2
                    valid = bpm > 0 and contact is not False
                    state.update(status='live' if valid else 'no_contact',
                                 bpm=bpm if valid else None, measured_at=time.time())

                await client.start_notify(HR, received)
                next_battery = 0
                while not stop.is_set() and not disconnected.is_set():
                    now = time.monotonic()
                    if now >= next_battery:
                        next_battery = now + 300
                        try:
                            battery = await asyncio.wait_for(client.read_gatt_char(BATTERY), 5)
                            if battery and battery[0] <= 100:
                                state.update(battery=battery[0])
                        except Exception:
                            pass  # Battery is optional; heart rate remains usable.
                    age = time.monotonic() - last_received
                    if age > 15:
                        state.update(status='stale', bpm=None)
                    if age > 45:
                        raise RuntimeError('No readings; check Heart Rate Broadcast and band contact')
                    await asyncio.sleep(1)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            state.update(status='disconnected', bpm=None, battery=None, message=str(exc))
        if not stop.is_set():
            state.update(status='disconnected', bpm=None, battery=None)
            try:
                await asyncio.wait_for(stop.wait(), retry)
            except asyncio.TimeoutError:
                pass
            retry = min(retry * 2, 30)


async def main(args):
    config_path = Path(args.config).expanduser()
    config = json.loads(config_path.read_text()) if config_path.exists() else {}
    if args.address:
        config['address'] = args.address
    state = State(Path(args.state))
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    task = asyncio.create_task(run(config, state, stop))
    def shutdown():
        stop.set()
        task.cancel()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown)
    try:
        await task
    except asyncio.CancelledError:
        pass
    finally:
        state.update(status='stopped', bpm=None, battery=None)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default=str(Path.home() / '.config/omarchy-whoop/config.json'))
    parser.add_argument('--address', help='Override the configured Bluetooth address')
    parser.add_argument('--state', default=str(Path(os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')) / 'omarchy-whoop/state.json'))
    asyncio.run(main(parser.parse_args()))
