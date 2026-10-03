"""Publication archive restoration, deduplication and tamper rejection."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import zipfile

from package_evidence import package
from restore_evidence import restore
from verify_release import verify


class EvidencePackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)/'original'
        (self.root/'fixtures').mkdir(parents=True)
        (self.root/'runs').mkdir()
        (self.root/'fixtures/a.pcm').write_bytes(b'\x01\x00\x02\x00')
        (self.root/'runs/b.pcm').write_bytes(b'\x01\x00\x02\x00')
        with redirect_stdout(io.StringIO()):
            package(self.root)
        self.fresh = Path(self.temp.name)/'published'
        self.fresh.mkdir()
        for name in ('raw_evidence.zip', 'artifact_hashes.json'):
            shutil.copyfile(self.root/name, self.fresh/name)

    def test_deduplication_and_fresh_release_restore(self):
        with zipfile.ZipFile(self.fresh/'raw_evidence.zip') as zipped:
            self.assertEqual(len([n for n in zipped.namelist() if n.startswith('blobs/')]), 1)
        with redirect_stdout(io.StringIO()):
            verify(self.fresh)
            restore(self.fresh)
        self.assertEqual((self.fresh/'runs/b.pcm').read_bytes(), (self.root/'runs/b.pcm').read_bytes())
        (self.fresh/'runs/b.pcm').write_bytes(b'changed')
        with self.assertRaises(FileExistsError), redirect_stdout(io.StringIO()):
            restore(self.fresh)

    def test_corrupted_blob_is_rejected(self):
        with zipfile.ZipFile(self.fresh/'raw_evidence.zip') as zipped:
            index = json.loads(zipped.read('index.json'))
        digest = next(iter(index.values()))
        with zipfile.ZipFile(self.fresh/'raw_evidence.zip', 'w') as zipped:
            zipped.writestr('index.json', json.dumps(index))
            zipped.writestr('blobs/'+digest, b'corrupt')
        with self.assertRaisesRegex(ValueError, 'Corrupt archived blob'):
            restore(self.fresh)

    def test_archive_path_escape_is_rejected(self):
        with zipfile.ZipFile(self.fresh/'raw_evidence.zip', 'w') as zipped:
            zipped.writestr('index.json', json.dumps({'fixtures/../../escape': '0'*64}))
        with self.assertRaisesRegex(ValueError, 'Unsafe archive path'):
            restore(self.fresh)
