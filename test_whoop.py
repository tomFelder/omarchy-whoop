import json
from pathlib import Path
import tempfile
import unittest
from whoop import parse_measurement, State

class MeasurementTests(unittest.TestCase):
    def test_8_bit(self):
        self.assertEqual(parse_measurement(bytes([0, 72])), (72, None))
    def test_16_bit(self):
        self.assertEqual(parse_measurement(bytes([1, 44, 1])), (300, None))
    def test_contact(self):
        self.assertEqual(parse_measurement(bytes([4, 72])), (72, False))
        self.assertEqual(parse_measurement(bytes([6, 72])), (72, True))
    def test_optional_fields_do_not_change_bpm(self):
        self.assertEqual(parse_measurement(bytes([24, 72, 1, 0, 0, 4])), (72, None))
    def test_short_packets(self):
        for data in (b'', b'\x00', b'\x01\x48'):
            with self.assertRaises(ValueError):
                parse_measurement(data)
    def test_state_replaces_current_reading_privately(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'state.json'
            state = State(path)
            state.update(status='live', bpm=72)
            state.update(status='disconnected', bpm=None)
            self.assertIsNone(json.loads(path.read_text())['bpm'])
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertFalse(path.with_suffix('.tmp').exists())

if __name__ == '__main__':
    unittest.main()
