"""Turn a scale-submission issue body into a scale folder for validation.

The issue body is untrusted text. It is only parsed as data: it is never
executed, interpolated into a command, or used as a path (the folder name is
the submission's own id, accepted only if it is a lowercase UUID).

Run: python -m tools.submission_intake --body-file body.md --root . --report report.txt
Exit status 0 when scales/<id>/ was written, 1 with the problems in the report.
"""
import argparse
import json
from pathlib import Path
import re
import sys

from tools.validate import MAX_BYTES

HEADING_CONFIRMATIONS = 'Confirmations'
HEADING_METADATA = 'metadata.json'
HEADING_STRINGS = 'strings.csv'
HEADING_NOTES = 'Notes'
CONFIRMATIONS = (
    'I have permission to publish this scale under CC BY 4.0.',
    'This submission contains no private information.',
)
KNOWN_HEADINGS = (HEADING_CONFIRMATIONS, HEADING_METADATA, HEADING_STRINGS, HEADING_NOTES)

UUID = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}')
HEADING = re.compile(r'### (.+?)\s*')
FENCE = re.compile(r'(`{3,}|~{3,})[^`]*')


class SubmissionError(ValueError):
    def __init__(self, problems):
        super().__init__('; '.join(problems))
        self.problems = problems


def parse_sections(body):
    """Split an issue-form body into {heading: text}, honouring only known headings outside code fences."""
    sections, current, fence = {}, None, None
    for line in body.replace('\r\n', '\n').replace('\r', '\n').split('\n'):
        marker = FENCE.fullmatch(line.strip())
        if fence is None and marker:
            fence = marker.group(1)
        elif fence is not None and line.strip() == fence:
            fence = None
        elif fence is None and (heading := HEADING.fullmatch(line)) and heading.group(1) in KNOWN_HEADINGS:
            current = heading.group(1)
            sections.setdefault(current, [])
            continue
        if current is not None:
            sections[current].append(line)
    return {name: '\n'.join(lines).strip('\n') for name, lines in sections.items()}


def unfence(text):
    """The contents of the code block an issue form wraps a render field in; plain text is returned as is."""
    lines = text.strip('\n').split('\n')
    if lines and (opening := FENCE.fullmatch(lines[0].strip())):
        closing = [i for i, line in enumerate(lines) if i > 0 and line.strip() == opening.group(1)]
        return '\n'.join(lines[1:closing[-1]] if closing else lines[1:])
    return '\n'.join(lines)


def confirmed(section):
    ticked = {match.group(1).strip() for match in re.finditer(r'^\s*[-*] \[[xX]\] (.+)$', section or '', re.M)}
    return [label for label in CONFIRMATIONS if label in ticked]


def parse_metadata(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise SubmissionError([f'metadata.json has a duplicate key {key!r}'])
            result[key] = value
        return result
    try:
        value = json.loads(text, object_pairs_hook=pairs)
    except json.JSONDecodeError as error:
        raise SubmissionError([f'metadata.json is not valid JSON ({error.msg}, line {error.lineno})']) from None
    except RecursionError:
        raise SubmissionError(['metadata.json is nested too deeply']) from None
    if not isinstance(value, dict):
        raise SubmissionError(['metadata.json must be a JSON object'])
    return value


def parse_submission(body):
    """Return (scale id, metadata.json text, strings.csv text) or raise SubmissionError listing every problem."""
    problems = []
    sections = parse_sections(body)
    missing = [label for label in CONFIRMATIONS if label not in confirmed(sections.get(HEADING_CONFIRMATIONS))]
    problems += [f'Confirmation not ticked: {label}' for label in missing]
    texts = {}
    for heading in (HEADING_METADATA, HEADING_STRINGS):
        text = unfence(sections.get(heading, '')).strip('\n')
        if not text.strip():
            problems.append(f'The {heading} section is empty or missing')
        elif len(text.encode('utf-8')) > MAX_BYTES:
            problems.append(f'The {heading} section exceeds {MAX_BYTES} bytes')
        else:
            texts[heading] = text + '\n'
    scale_id = None
    if HEADING_METADATA in texts:
        try:
            metadata = parse_metadata(texts[HEADING_METADATA])
        except SubmissionError as error:
            problems += error.problems
        else:
            value = metadata.get('id')
            if isinstance(value, str) and UUID.fullmatch(value):
                scale_id = value
            else:
                problems.append('metadata.json "id" must be a lowercase UUID')
    if problems:
        raise SubmissionError(problems)
    return scale_id, texts[HEADING_METADATA], texts[HEADING_STRINGS]


def write_submission(root, body):
    """Write the submission to <root>/scales/<id>/ and return the folder."""
    scale_id, metadata, strings = parse_submission(body)
    directory = Path(root) / 'scales' / scale_id
    if directory.exists():
        raise SubmissionError(['A scale with this id already exists. Use a new UUID for a different scale; '
                               'corrections to an existing scale go in a pull request.'])
    directory.mkdir(parents=True)
    (directory / 'metadata.json').write_text(metadata, encoding='utf-8', newline='\n')
    (directory / 'strings.csv').write_text(strings, encoding='utf-8', newline='\n')
    return directory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--body-file', type=Path, required=True)
    parser.add_argument('--root', type=Path, default=Path('.'))
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.body_file.stat().st_size > 10 * MAX_BYTES:
            raise SubmissionError(['The issue is too large'])
        directory = write_submission(args.root, args.body_file.read_text(encoding='utf-8', errors='replace'))
    except SubmissionError as error:
        args.report.write_text('\n'.join(error.problems) + '\n', encoding='utf-8')
        print('\n'.join(f'ERROR: {problem}' for problem in error.problems), file=sys.stderr)
        return 1
    args.report.write_text('', encoding='utf-8')
    print(f'Wrote {directory}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
