import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools import submission_intake as intake
from tools.validate import ValidationError, validate_repository

ROOT = Path(__file__).resolve().parents[1]
ID = '11111111-1111-4111-8111-111111111111'
FIXTURE = ROOT / 'tests/fixtures/full' / ID


def issue_body(metadata=None, strings=None, ticked=intake.CONFIRMATIONS, newline='\n', notes='Measured in the shop.'):
    """An issue body laid out the way the scale-submission form renders it."""
    metadata = (FIXTURE / 'metadata.json').read_text() if metadata is None else metadata
    strings = (FIXTURE / 'strings.csv').read_text() if strings is None else strings
    boxes = '\n'.join(f'- [{"X" if label in ticked else " "}] {label}' for label in intake.CONFIRMATIONS)
    body = (f'### {intake.HEADING_CONFIRMATIONS}\n\n{boxes}\n\n'
            f'### {intake.HEADING_METADATA}\n\n```json\n{metadata.rstrip()}\n```\n\n'
            f'### {intake.HEADING_STRINGS}\n\n```csv\n{strings.rstrip()}\n```\n\n'
            f'### {intake.HEADING_NOTES}\n\n{notes}\n')
    return body.replace('\n', newline)


class SubmissionIntakeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copytree(ROOT / 'schema', self.root / 'schema')
        (self.root / 'scales').mkdir()

    def problems(self, body):
        with self.assertRaises(intake.SubmissionError) as caught:
            intake.write_submission(self.root, body)
        return caught.exception.problems

    def test_a_form_body_becomes_a_valid_scale_folder(self):
        directory = intake.write_submission(self.root, issue_body())
        self.assertEqual(directory, self.root / 'scales' / ID)
        self.assertEqual({path.name for path in directory.iterdir()}, {'metadata.json', 'strings.csv'})
        self.assertEqual(json.loads((directory / 'metadata.json').read_text()),
                         json.loads((FIXTURE / 'metadata.json').read_text()))
        self.assertEqual((directory / 'strings.csv').read_text(), (FIXTURE / 'strings.csv').read_text())
        self.assertEqual(len(validate_repository(self.root)), 1)

    def test_windows_line_endings_are_accepted(self):
        directory = intake.write_submission(self.root, issue_body(newline='\r\n'))
        self.assertNotIn(b'\r', (directory / 'strings.csv').read_bytes())
        self.assertEqual(len(validate_repository(self.root)), 1)

    def test_unticked_confirmations_are_reported(self):
        problems = self.problems(issue_body(ticked=intake.CONFIRMATIONS[:1]))
        self.assertEqual(problems, [f'Confirmation not ticked: {intake.CONFIRMATIONS[1]}'])
        self.assertEqual(len(self.problems(issue_body(ticked=()))), 2)
        self.assertFalse((self.root / 'scales' / ID).exists())

    def test_missing_or_empty_sections_are_reported(self):
        self.assertIn('The strings.csv section is empty or missing', self.problems(issue_body(strings=' ')))
        body = issue_body().split(f'### {intake.HEADING_METADATA}')[0]
        problems = self.problems(body)
        self.assertIn('The metadata.json section is empty or missing', problems)
        self.assertIn('The strings.csv section is empty or missing', problems)

    def test_bad_json_and_ids_are_rejected_before_any_path_is_built(self):
        self.assertTrue(self.problems(issue_body(metadata='{not json'))[0].startswith('metadata.json is not valid JSON'))
        self.assertEqual(self.problems(issue_body(metadata='[1]')), ['metadata.json must be a JSON object'])
        self.assertIn('duplicate key', self.problems(issue_body(metadata='{"id": "a", "id": "b"}'))[0])
        self.assertEqual(self.problems(issue_body(metadata='[' * 20000 + ']' * 20000)),
                         ['metadata.json is nested too deeply'])
        for bad in ['../../etc', 'ABCDEF01-1111-4111-8111-111111111111', '', 'x/../y', 5]:
            body = issue_body(metadata=json.dumps({'id': bad}))
            self.assertEqual(self.problems(body), ['metadata.json "id" must be a lowercase UUID'], bad)
        self.assertEqual(list((self.root / 'scales').iterdir()), [])

    def test_an_existing_id_is_not_overwritten(self):
        shutil.copytree(FIXTURE, self.root / 'scales' / ID)
        before = (self.root / 'scales' / ID / 'strings.csv').read_text()
        self.assertIn('already exists', self.problems(issue_body(strings=before + 'E4,plain,3,1,,,540,,,,\n'))[0])
        self.assertEqual((self.root / 'scales' / ID / 'strings.csv').read_text(), before)

    def test_a_heading_inside_a_code_block_does_not_split_the_body(self):
        strings = (FIXTURE / 'strings.csv').read_text() + '# source: ### Notes\n'
        sections = intake.parse_sections(issue_body(strings=strings))
        self.assertIn('### Notes', sections[intake.HEADING_STRINGS])
        self.assertEqual(sections[intake.HEADING_NOTES], 'Measured in the shop.')

    def test_unknown_headings_are_ignored_and_plain_text_is_accepted(self):
        sections = intake.parse_sections('### Something else\nx\n### Notes\nhello\n')
        self.assertEqual(sections, {'Notes': 'hello'})
        self.assertEqual(intake.unfence('plain text'), 'plain text')
        self.assertEqual(intake.unfence('```json\n{"a": 1}\n```'), '{"a": 1}')

    def test_content_that_fails_the_validator_is_left_for_it_to_report(self):
        directory = intake.write_submission(self.root, issue_body(strings='note,construction\nC4,plain\n'))
        self.assertTrue(directory.is_dir())
        with self.assertRaisesRegex(ValidationError, 'canonical columns'):
            validate_repository(self.root)

    def test_the_issue_form_uses_the_labels_the_parser_expects(self):
        form = (ROOT / '.github/ISSUE_TEMPLATE/scale-submission.yml').read_text()
        for label in (intake.HEADING_METADATA, intake.HEADING_STRINGS, intake.HEADING_NOTES, *intake.CONFIRMATIONS):
            self.assertIn(f'label: {label}', form)
        self.assertIn('labels: ["scale-submission"]', form)
        self.assertIn('blank_issues_enabled: true',
                      (ROOT / '.github/ISSUE_TEMPLATE/config.yml').read_text())

    def test_command_line_reports_problems_and_writes_nothing(self):
        body, report = self.root / 'body.md', self.root / 'report.txt'
        body.write_text(issue_body(ticked=()))
        argv = ['--body-file', str(body), '--root', str(self.root), '--report', str(report)]
        with patch.object(sys, 'argv', ['intake', *argv]), patch.object(sys, 'stderr'):
            self.assertEqual(intake.main(), 1)
        self.assertEqual(len(report.read_text().splitlines()), 2)
        body.write_text(issue_body())
        with patch.object(sys, 'argv', ['intake', *argv]), patch.object(sys, 'stdout'):
            self.assertEqual(intake.main(), 0)
        self.assertEqual(report.read_text(), '')
        self.assertTrue((self.root / 'scales' / ID / 'metadata.json').is_file())


if __name__ == '__main__':
    unittest.main()
