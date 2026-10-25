import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ReleaseTests(unittest.TestCase):
    def test_pinned_manifest_and_payload(self):
        encoded = (ROOT / 'release.json').read_bytes()
        digest = hashlib.sha256(encoded).hexdigest()
        self.assertIn('MANIFEST_SHA=' + digest, (ROOT / 'setup.sh').read_text())
        for name, expected in json.loads(encoded)['files'].items():
            with self.subTest(file=name):
                self.assertEqual(hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), expected)
