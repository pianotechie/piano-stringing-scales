"""Build a validated, deterministic snapshot without publishing it."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys

from tools.validate import validate_repository


def resolve_repository(value=None):
    """Return OWNER/NAME from the --repository flag or the GITHUB_REPOSITORY environment variable."""
    repository = value or os.environ.get('GITHUB_REPOSITORY')
    if not repository:
        raise ValueError('repository is not set: pass --repository OWNER/NAME or set GITHUB_REPOSITORY')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
        raise ValueError(f'repository must look like OWNER/NAME, got {repository!r}')
    return repository


def build_catalog(root, output, revision, repository):
    repository = resolve_repository(repository)
    if not re.fullmatch(r'[0-9a-f]{40}', revision):
        raise ValueError('revision must be a full lowercase Git commit SHA')
    records = validate_repository(root)
    if output.resolve() == root.resolve() or root.resolve() in output.resolve().parents and 'build' not in output.relative_to(root).parts:
        raise ValueError('output inside repository must be under build/')
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError('output must be empty to avoid mixing snapshots')
    entries = []
    for directory, metadata, rows, warnings in records:
        target = output / 'scales' / metadata['id']
        target.mkdir(parents=True)
        hashes = {}
        for filename in ['metadata.json', 'strings.csv']:
            shutil.copyfile(directory / filename, target / filename)
            hashes[filename] = hashlib.sha256((target / filename).read_bytes()).hexdigest()
        entries.append({
            **metadata,
            'measurementPath': f'scales/{metadata["id"]}/strings.csv',
            'metadataPath': f'scales/{metadata["id"]}/metadata.json',
            'sha256': hashes,
            'noteCount': len(rows),
            'missingNotes': sorted(set(range(metadata['keyRange']['lowest'], metadata['keyRange']['highest'] + 1))
                                   - {row['midiNote'] for row in rows}),
            'warnings': warnings,
        })
    catalog = {'schemaVersion': 1, 'repository': repository, 'revision': revision, 'scales': entries}
    (output / 'catalog.json').write_text(json.dumps(catalog, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
    for name in ['LICENSE-DATA', 'LICENSE-CODE']:
        shutil.copyfile(root / name, output / name)
    return catalog


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('.'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--repository', help='OWNER/NAME; defaults to $GITHUB_REPOSITORY')
    args = parser.parse_args()
    try:
        catalog = build_catalog(args.root, args.output, args.revision, args.repository)
        print(f'Built catalog with {len(catalog["scales"])} scale(s) at {args.output}.')
    except (ValueError, OSError, csv.Error) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
