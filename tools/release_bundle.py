"""Build reproducible GitHub release assets for one validated catalog revision."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import zipfile

from tools.build_catalog import build_catalog, resolve_repository


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')


def build_release(root, output, revision, repository):
    repository = resolve_repository(repository)
    # build_catalog validates revision, source records and output before writing.
    catalog = build_catalog(root, output, revision, repository)
    tag = f'catalog-{revision}'
    base_url = f'https://github.com/{repository}/releases/download/{tag}'
    assets = output / 'assets'
    assets.mkdir()
    for entry in catalog['scales']:
        for kind, filename in [('measurement', 'strings.csv'), ('metadata', 'metadata.json')]:
            asset = f'{entry["id"]}.csv' if kind == 'measurement' else f'{entry["id"]}.json'
            shutil.copyfile(output / 'scales' / entry['id'] / filename, assets / asset)
            entry[f'{kind}URL'] = f'{base_url}/{asset}'
    write_json(output / 'catalog.json', catalog)
    shutil.copyfile(output / 'catalog.json', assets / 'catalog.json')
    for name in ['LICENSE-DATA', 'LICENSE-CODE']:
        shutil.copyfile(output / name, assets / name)
    # Fixed archive ordering, timestamps and modes make retries byte-identical.
    with zipfile.ZipFile(assets / 'snapshot.zip', 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(output.rglob('*')):
            if path.is_file() and assets not in path.parents:
                info = zipfile.ZipInfo(path.relative_to(output).as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, path.read_bytes())
    pointer = {
        'schemaVersion': 1, 'repository': repository, 'revision': revision,
        'releaseTag': tag,
        'catalogURL': f'{base_url}/catalog.json',
        'catalogSHA256': sha256(assets / 'catalog.json'),
        'snapshotURL': f'{base_url}/snapshot.zip',
        'snapshotSHA256': sha256(assets / 'snapshot.zip'),
    }
    write_json(assets / 'latest.json', pointer)
    return pointer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('.'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--repository', help='OWNER/NAME; defaults to $GITHUB_REPOSITORY')
    args = parser.parse_args()
    try:
        build_release(args.root, args.output, args.revision, args.repository)
    except (ValueError, OSError) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        return 1
    print(f'Release assets built at {args.output / "assets"}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
