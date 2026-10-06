"""Publish a completed release bundle; existing published assets are never replaced."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile

from tools.build_catalog import resolve_repository
from tools.release_bundle import sha256


def gh(*args, repo, check=True):
    return subprocess.run(['gh', *args, '--repo', repo], check=check, capture_output=True, text=True)


def publish(assets, revision, repository):
    repository = resolve_repository(repository)
    pointer = json.loads((assets / 'latest.json').read_text())
    tag = f'catalog-{revision}'
    if pointer['revision'] != revision or pointer['releaseTag'] != tag or pointer['repository'] != repository:
        raise ValueError('release pointer does not match requested revision and repository')
    for filename, field in [('catalog.json', 'catalogSHA256'), ('snapshot.zip', 'snapshotSHA256')]:
        if sha256(assets / filename) != pointer[field]:
            raise ValueError(f'{filename}: pointer hash mismatch')
    # Caller serializes publication and rejects stale main revisions. Do not silently
    # treat authentication/network failures as a missing release.
    releases = json.loads(gh('release', 'list', '--limit', '100', '--json', 'tagName,isDraft', repo=repository).stdout)
    existing = next((release for release in releases if release['tagName'] == tag), None)
    if existing is None:
        gh('release', 'create', tag, '--target', revision, '--draft', '--title', f'Scale catalog {revision[:12]}',
           '--notes', 'Validated scale catalog snapshot. Data: CC BY 4.0. Tooling: MIT.', repo=repository)
        existing = {'isDraft': True}
    if existing['isDraft']:
        # Drafts are not discoverable by anonymous readers; replacing partial draft
        # uploads permits recovery from a failed upload before publishing.
        gh('release', 'upload', tag, *[str(path) for path in sorted(assets.iterdir())], '--clobber', repo=repository)
    details = json.loads(gh('release', 'view', tag, '--json', 'assets,isDraft,targetCommitish', repo=repository).stdout)
    expected = {path.name for path in assets.iterdir()}
    if {asset['name'] for asset in details['assets']} != expected:
        raise ValueError('release asset set does not match the validated bundle')
    # Download all assets to verify exact uploaded bytes before promoting latest.
    with tempfile.TemporaryDirectory() as temporary:
        gh('release', 'download', tag, '--dir', temporary, repo=repository)
        for name in expected:
            if sha256(Path(temporary) / name) != sha256(assets / name):
                raise ValueError(f'{name}: uploaded bytes do not match validated bundle')
    gh('release', 'edit', tag, '--draft=false', '--latest', repo=repository)
    print(f'Published verified catalog: https://github.com/{repository}/releases/tag/{tag}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assets', type=Path, required=True)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--repository', help='OWNER/NAME; defaults to $GITHUB_REPOSITORY')
    args = parser.parse_args()
    publish(args.assets, args.revision, args.repository)


if __name__ == '__main__':
    main()
