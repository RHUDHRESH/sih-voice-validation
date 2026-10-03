"""Compress detailed study evidence without removing the working source data."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile


def package(root):
    archive = root/'raw_evidence.zip'
    if archive.exists():
        raise FileExistsError('Raw archive already exists; preserve it or choose another study')
    index, stored = {}, set()
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zipped:
        for folder in ('fixtures', 'runs'):
            if not (root/folder).is_dir():
                raise FileNotFoundError(folder)
            for path in sorted((root/folder).rglob('*')):
                if path.is_file():
                    digest = hashlib.sha256(path.read_bytes()).hexdigest()
                    index[path.relative_to(root).as_posix()] = digest
                    if digest not in stored:
                        zipped.write(path, 'blobs/'+digest)
                        stored.add(digest)
        zipped.writestr('index.json', json.dumps(index, sort_keys=True))
    hashes = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob('*'))
              if p.is_file() and p.name not in ('artifact_hashes.json', 'viewer_bundle.json')}
    (root/'artifact_hashes.json').write_text(json.dumps(hashes, indent=2, sort_keys=True)+'\n', encoding='utf-8')
    print(json.dumps({'archive': str(archive), 'bytes': archive.stat().st_size, 'sha256': hashes['raw_evidence.zip'],
                      'raw_files_retained': True, 'logical_files': len(index), 'unique_blobs': len(stored),
                      'restore_command': 'python restore_evidence.py '+str(root), 'hashed_artifacts': len(hashes)}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('study', type=Path)
    package(parser.parse_args().study.resolve())
