import importlib.util
import io
import sys
import tarfile
import unittest
from pathlib import Path

if sys.platform != 'win32':
    spec = importlib.util.spec_from_file_location('workspace_broker', Path(__file__).resolve().parents[1] / 'server/workspace_broker.py')
    broker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(broker)


@unittest.skipIf(sys.platform == 'win32', 'Linux workspace broker')
class ArchiveTests(unittest.TestCase):
    def archive(self, name, kind=tarfile.REGTYPE):
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode='w') as tar:
            info = tarfile.TarInfo(name)
            info.type = kind
            tar.addfile(info)
        return stream.getvalue()

    def test_safe_file(self):
        broker.validate_archive(self.archive('./userfiles/demo.py'))

    def test_reject_links_and_traversal(self):
        for name, kind in [('../escape', tarfile.REGTYPE), ('/absolute', tarfile.REGTYPE), ('userfiles/link', tarfile.SYMTYPE)]:
            with self.assertRaises(ValueError):
                broker.validate_archive(self.archive(name, kind))
