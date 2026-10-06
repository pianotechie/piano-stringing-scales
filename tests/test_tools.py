import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from tools.build_catalog import build_catalog, resolve_repository
from tools.validate import load_json, midi_note, validate_record, validate_repository

ROOT = Path(__file__).resolve().parents[1]
ID = '11111111-1111-4111-8111-111111111111'
REVISION = 'a' * 40
REPOSITORY = 'pianotechie/piano-stringing-scales'


class ScaleToolsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'repo'
        self.root.mkdir()
        shutil.copytree(ROOT / 'schema', self.root / 'schema')
        (self.root / 'scales').mkdir()
        for name in ['LICENSE-DATA', 'LICENSE-CODE']:
            shutil.copyfile(ROOT / name, self.root / name)
        self.schema = load_json(self.root / 'schema/scale-metadata.schema.json')

    def fixture(self, name='full'):
        directory = self.root / 'scales' / ID
        shutil.copytree(ROOT / 'tests/fixtures' / name / ID, directory)
        return directory

    def change_metadata(self, directory, **changes):
        metadata = load_json(directory / 'metadata.json')
        metadata.update(changes)
        (directory / 'metadata.json').write_text(json.dumps(metadata))

    def change_row(self, directory, **changes):
        path = directory / 'strings.csv'
        with path.open(newline='') as file:
            reader = csv.DictReader(file)
            rows, fields = list(reader), reader.fieldnames
        rows[0].update(changes)
        with path.open('w', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=fields, lineterminator='\n')
            writer.writeheader()
            writer.writerows(rows)

    def test_full_and_partial_fixtures(self):
        full = self.fixture()
        _, rows, warnings = validate_record(full, self.schema)
        self.assertEqual([row['midiNote'] for row in rows], [60, 61, 62])
        self.assertEqual(rows[0]['notes'], 'Synthetic, not measured')
        self.assertEqual(warnings, [])
        shutil.rmtree(full)
        partial = self.fixture('partial')
        _, rows, warnings = validate_record(partial, self.schema)
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(warnings), 1)

    def test_invalid_fixture(self):
        with self.assertRaisesRegex(ValueError, 'finite and positive'):
            validate_record(self.fixture('invalid'), self.schema)

    def test_metadata_constraints(self):
        directory = self.fixture()
        original = (directory / 'metadata.json').read_text()
        cases = [dict(schemaVersion=2), dict(id='wrong'), dict(make='  '),
                 dict(contributors=[' ']), dict(license='MIT'), dict(unknown=True),
                 dict(yearFrom=2000, yearTo=1900), dict(sourceURL='not-a-url'),
                 dict(keyRange={'lowest':62, 'highest':60})]
        for changes in cases:
            with self.subTest(changes=changes):
                (directory / 'metadata.json').write_text(original)
                self.change_metadata(directory, **changes)
                with self.assertRaises(ValueError):
                    validate_record(directory, self.schema)

    def test_measurement_constraints(self):
        directory = self.fixture()
        original = (directory / 'strings.csv').read_text()
        cases = [dict(core_mm='inf'), dict(core_mm='-1'), dict(core_mm='zero'),
                 dict(strings='4'), dict(construction='wound'), dict(note='H4'),
                 dict(note='A0'), dict(outside_mm='2'), dict(notes='multi\nline'),
                 dict(construction='single', core_mm='2', outside_mm='1'),
                 dict(construction='single', inner_layer_mm='2'),
                 dict(overall_length_mm='500'),
                 dict(construction='double', core_mm='1', inner_layer_mm='2', outside_mm='3',
                      loop_to_winding_mm='200', winding_length_mm='600', overall_length_mm='700')]
        for changes in cases:
            with self.subTest(changes=changes):
                (directory / 'strings.csv').write_text(original)
                self.change_row(directory, **changes)
                with self.assertRaises(ValueError):
                    validate_record(directory, self.schema)

    def test_duplicate_and_unsorted_notes(self):
        directory = self.fixture()
        self.change_row(directory, note='C#4')
        with self.assertRaisesRegex(ValueError, 'unique and sorted'):
            validate_record(directory, self.schema)

    def test_coverage(self):
        directory = self.fixture('partial')
        self.change_metadata(directory, coverage='full-keyboard')
        with self.assertRaisesRegex(ValueError, 'every note'):
            validate_record(directory, self.schema)
        self.change_metadata(directory, coverage='bass')
        with self.assertRaisesRegex(ValueError, 'wound strings only'):
            validate_record(directory, self.schema)
        self.change_metadata(directory, coverage='plain-wire')
        self.change_row(directory, construction='single')
        with self.assertRaisesRegex(ValueError, 'contains a wound'):
            validate_record(directory, self.schema)

    def test_comments_and_duplicate_json_keys(self):
        directory = self.fixture()
        path = directory / 'strings.csv'
        original = path.read_text()
        path.write_text('# make: Synthetic\n' + original)
        validate_record(directory, self.schema)
        path.write_text('# make: Different\n' + original)
        with self.assertRaisesRegex(ValueError, 'conflicts'):
            validate_record(directory, self.schema)
        (directory / 'metadata.json').write_text('{"id":"a","id":"b"}')
        with self.assertRaisesRegex(ValueError, 'duplicate JSON'):
            validate_record(directory, self.schema)

    def test_file_and_directory_constraints(self):
        directory = self.fixture()
        directory.rename(directory.with_name('wrong'))
        with self.assertRaisesRegex(ValueError, 'directory must match'):
            validate_repository(self.root)
        directory.with_name('wrong').rename(directory)
        (directory / 'extra.txt').write_text('unexpected')
        with self.assertRaisesRegex(ValueError, 'expected only'):
            validate_repository(self.root)
        (directory / 'extra.txt').unlink()
        path = directory / 'strings.csv'
        path.unlink()
        path.symlink_to(ROOT / 'tests/fixtures/full' / ID / 'strings.csv')
        with self.assertRaisesRegex(ValueError, 'symlink'):
            validate_repository(self.root)

    def test_stray_entries_under_scales_are_rejected(self):
        directory = self.fixture()
        (directory / 'nested').mkdir()
        with self.assertRaisesRegex(ValueError, 'expected only'):
            validate_repository(self.root)
        (directory / 'nested').rmdir()
        (self.root / 'scales' / 'notes.txt').write_text('stray')
        with self.assertRaisesRegex(ValueError, 'unexpected entry'):
            validate_repository(self.root)

    def test_note_names_match_app_conventions(self):
        for text, expected in [('A0',21), ('C#4',61), ('Db4',61), ('B♭3',58), ('60',60)]:
            self.assertEqual(midi_note(text), expected)

    def test_snapshot_is_deterministic_and_hashes_exact_bytes(self):
        directory = self.fixture()
        a, b = Path(self.temp.name) / 'a', Path(self.temp.name) / 'b'
        catalog = build_catalog(self.root, a, REVISION, REPOSITORY)
        build_catalog(self.root, b, REVISION, REPOSITORY)
        self.assertEqual((a / 'catalog.json').read_bytes(), (b / 'catalog.json').read_bytes())
        self.assertEqual(catalog['scales'][0]['sha256']['strings.csv'],
                         hashlib.sha256((directory / 'strings.csv').read_bytes()).hexdigest())
        self.assertEqual((a / 'scales' / ID / 'strings.csv').read_bytes(), (directory / 'strings.csv').read_bytes())
        self.assertEqual(catalog['scales'][0]['missingNotes'], [])
        with self.assertRaisesRegex(ValueError, 'empty'):
            build_catalog(self.root, a, REVISION, REPOSITORY)

    def test_partial_catalog_and_empty_catalog(self):
        catalog = build_catalog(self.root, Path(self.temp.name) / 'empty', REVISION, REPOSITORY)
        self.assertEqual(catalog['scales'], [])
        self.fixture('partial')
        catalog = build_catalog(self.root, Path(self.temp.name) / 'partial', REVISION, REPOSITORY)
        self.assertEqual(catalog['scales'][0]['missingNotes'], [61,62])

    def test_invalid_snapshot_writes_nothing(self):
        self.fixture('invalid')
        output = Path(self.temp.name) / 'bad'
        with self.assertRaises(ValueError):
            build_catalog(self.root, output, REVISION, REPOSITORY)
        self.assertFalse(output.exists())
        with self.assertRaisesRegex(ValueError, 'commit SHA'):
            build_catalog(self.root, output, 'main', REPOSITORY)

    def test_snapshot_records_the_given_repository(self):
        catalog = build_catalog(self.root, Path(self.temp.name) / 'repo-name', REVISION, REPOSITORY)
        self.assertEqual(catalog['repository'], 'pianotechie/piano-stringing-scales')

    def test_repository_comes_from_flag_or_environment_and_must_be_set(self):
        with patch.dict(os.environ, {'GITHUB_REPOSITORY': 'example/from-env'}):
            self.assertEqual(resolve_repository(None), 'example/from-env')
            self.assertEqual(resolve_repository('example/from-flag'), 'example/from-flag')
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, 'GITHUB_REPOSITORY'):
                resolve_repository(None)
            output = Path(self.temp.name) / 'unset'
            with self.assertRaisesRegex(ValueError, 'GITHUB_REPOSITORY'):
                build_catalog(self.root, output, REVISION, None)
            self.assertFalse(output.exists())
        with self.assertRaisesRegex(ValueError, 'OWNER/NAME'):
            resolve_repository('not a repository')


if __name__ == '__main__':
    unittest.main()
