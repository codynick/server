import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('adapt', ROOT / 'tools/adapt_rpi.py')
adapt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapt)


class AdaptationTests(unittest.TestCase):
    def test_original_tools_and_narrow_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            adapt.adapt(ROOT / 'upstream', target)
            for name in ('code/ansi-terminal.js', 'dashboard/index.php', 'blocks/stage.js', 'blocks/designs.js'):
                self.assertEqual((ROOT / 'upstream/ide' / name).read_bytes(), (target / 'ide' / name).read_bytes())
            self.assertIn('/home/client/blockdata', (target / 'ide/blocks/index.php').read_text(encoding='utf-8'))
            self.assertIn('Student Management', (target / 'ide/index.php').read_text(encoding='utf-8'))
            self.assertIn('CN = Simulator', (target / 'client/CodyNick.py').read_text(encoding='utf-8'))
            self.assertNotIn("mainPanelUrl.port = '';", (target / 'simulator/app.js').read_text(encoding='utf-8'))
