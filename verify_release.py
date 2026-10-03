"""Check all published artifact hashes, including archived raw study members."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile


def verify(root):
    expected = json.loads((root/'artifact_hashes.json').read_text(encoding='utf-8'))
    archive = root/'raw_evidence.zip'
    zipped = zipfile.ZipFile(archive) if archive.exists() else None
    index = json.loads(zipped.read('index.json')) if zipped is not None and 'index.json' in zipped.namelist() else {}
    try:
        for name, digest in expected.items():
            path = (root/name).resolve()
            if not path.is_relative_to(root.resolve()):
                raise ValueError('Artifact path leaves result directory')
            if path.is_file():
                content = path.read_bytes()
            elif zipped is not None:
                content = zipped.read('blobs/'+index[name] if name in index else name)
            else:
                raise FileNotFoundError(name)
            if hashlib.sha256(content).hexdigest() != digest:
                raise ValueError(f'Artifact hash mismatch: {name}')
    finally:
        if zipped:
            zipped.close()
    print(json.dumps({'status': 'pass', 'artifacts_checked': len(expected), 'directory': str(root)}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('results', type=Path)
    verify(parser.parse_args().results.resolve())
