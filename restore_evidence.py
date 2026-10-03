"""Restore verified content-addressed raw evidence into its original relative paths."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile


def restore(root):
    with zipfile.ZipFile(root/'raw_evidence.zip') as zipped:
        index = json.loads(zipped.read('index.json'))
        for name, digest in index.items():
            target = (root/name).resolve()
            if not target.is_relative_to(root.resolve()) or not name.startswith(('fixtures/', 'runs/')):
                raise ValueError('Unsafe archive path')
            content = zipped.read('blobs/'+digest)
            if hashlib.sha256(content).hexdigest() != digest:
                raise ValueError('Corrupt archived blob')
            if target.exists():
                if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
                    raise FileExistsError(f'Existing evidence differs: {target}')
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
    print(f'PASS: restored or matched {len(index)} evidence files in {root}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('study', type=Path)
    restore(parser.parse_args().study.resolve())
