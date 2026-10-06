import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from tools.publish_catalog import publish
from tools.release_bundle import build_release, sha256

ROOT = Path(__file__).resolve().parents[1]
REVISION = 'b' * 40
REPOSITORY = 'pianotechie/piano-stringing-scales'
ID = '11111111-1111-4111-8111-111111111111'


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'repo'
        self.root.mkdir()
        shutil.copytree(ROOT / 'schema', self.root / 'schema')
        shutil.copytree(ROOT / 'tests/fixtures/full', self.root / 'scales')
        for name in ['LICENSE-DATA', 'LICENSE-CODE']:
            shutil.copyfile(ROOT / name, self.root / name)
        self.output = Path(self.temp.name) / 'release'
        self.pointer = build_release(self.root, self.output, REVISION, REPOSITORY)
        self.assets = self.output / 'assets'

    def test_bundle_integrity_and_reproducibility(self):
        other = Path(self.temp.name) / 'other'
        build_release(self.root, other, REVISION, REPOSITORY)
        for path in self.assets.iterdir():
            self.assertEqual(path.read_bytes(), (other / 'assets' / path.name).read_bytes())
        self.assertEqual(self.pointer['repository'], REPOSITORY)
        self.assertTrue(self.pointer['catalogURL'].startswith(f'https://github.com/{REPOSITORY}/releases/download/'))
        self.assertEqual(self.pointer['catalogSHA256'], sha256(self.assets / 'catalog.json'))
        self.assertEqual(self.pointer['snapshotSHA256'], sha256(self.assets / 'snapshot.zip'))
        catalog = json.loads((self.assets / 'catalog.json').read_text())
        entry = catalog['scales'][0]
        self.assertTrue(entry['measurementURL'].endswith(f'/{ID}.csv'))
        self.assertEqual(entry['sha256']['strings.csv'], sha256(self.assets / f'{ID}.csv'))
        with zipfile.ZipFile(self.assets / 'snapshot.zip') as archive:
            self.assertEqual(archive.read('catalog.json'), (self.assets / 'catalog.json').read_bytes())
            self.assertIn('LICENSE-DATA', archive.namelist())
            self.assertFalse(any(name.startswith('assets/') for name in archive.namelist()))

    def test_tampering_blocks_network_calls(self):
        (self.assets / 'catalog.json').write_text('{}')
        with patch('tools.publish_catalog.gh') as call:
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                publish(self.assets, REVISION, REPOSITORY)
            call.assert_not_called()

    def test_mismatched_repository_blocks_network_calls(self):
        with patch('tools.publish_catalog.gh') as call:
            with self.assertRaisesRegex(ValueError, 'repository'):
                publish(self.assets, REVISION, 'someone/else')
            call.assert_not_called()

    def mock_github(self, calls, existing=None, corrupt_download=False):
        def call(*args, **kwargs):
            calls.append(args)
            result = type('Result', (), {'stdout': ''})()
            if args[:2] == ('release', 'list'):
                result.stdout = json.dumps([] if existing is None else [existing])
            if args[:2] == ('release', 'view'):
                result.stdout = json.dumps({'assets': [{'name': path.name} for path in self.assets.iterdir()],
                                            'isDraft': True, 'targetCommitish': REVISION})
            if args[:2] == ('release', 'download'):
                destination = Path(args[args.index('--dir') + 1])
                for path in self.assets.iterdir():
                    shutil.copyfile(path, destination / path.name)
                if corrupt_download:
                    (destination / 'catalog.json').write_text('corrupt')
            return result
        return call

    def test_draft_is_verified_before_promotion(self):
        calls = []
        with patch('tools.publish_catalog.gh', side_effect=self.mock_github(calls)):
            publish(self.assets, REVISION, REPOSITORY)
        verbs = [call[1] for call in calls]
        self.assertEqual(verbs, ['list', 'create', 'upload', 'view', 'download', 'edit'])
        self.assertIn('--draft', calls[1])
        self.assertIn('--latest', calls[-1])

    def test_published_retry_does_not_replace_assets(self):
        calls = []
        existing = {'tagName': f'catalog-{REVISION}', 'isDraft': False}
        with patch('tools.publish_catalog.gh', side_effect=self.mock_github(calls, existing)):
            publish(self.assets, REVISION, REPOSITORY)
        self.assertNotIn('upload', [call[1] for call in calls])
        self.assertNotIn('create', [call[1] for call in calls])

    def test_failed_verification_never_promotes(self):
        calls = []
        with patch('tools.publish_catalog.gh', side_effect=self.mock_github(calls, corrupt_download=True)):
            with self.assertRaisesRegex(ValueError, 'uploaded bytes'):
                publish(self.assets, REVISION, REPOSITORY)
        self.assertNotIn('edit', [call[1] for call in calls])


if __name__ == '__main__':
    unittest.main()
