"""Validate repository records. Run: python -m tools.validate --root ."""
import argparse
import csv
import io
import json
import math
from pathlib import Path
import re
import sys

from jsonschema import Draft202012Validator, FormatChecker

COLUMNS = ('note,construction,strings,core_mm,inner_layer_mm,outside_mm,'
           'speaking_length_mm,loop_to_winding_mm,winding_length_mm,overall_length_mm,notes').split(',')
DIMENSIONS = COLUMNS[3:10]
MAX_BYTES = 1_000_000


class ValidationError(ValueError):
    pass


def read_text(path):
    if path.is_symlink() or not path.is_file():
        raise ValidationError(f'{path}: expected a regular file, not a symlink')
    if path.stat().st_size > MAX_BYTES:
        raise ValidationError(f'{path}: exceeds {MAX_BYTES} bytes')
    return path.read_text(encoding='utf-8')


def load_json(path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValidationError(f'{path}: duplicate JSON key {key}')
            result[key] = value
        return result
    return json.loads(read_text(path), object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValidationError(f'Invalid JSON number {value}')))


def midi_note(text):
    if re.fullmatch(r'[0-9]+', text):
        return int(text)
    match = re.fullmatch(r'([A-Ga-g])([#♯b♭]*)(-?[0-9]+)', text)
    if not match:
        raise ValidationError(f'invalid note {text!r}')
    letter, accidental, octave = match.groups()
    pitch = dict(C=0, D=2, E=4, F=5, G=7, A=9, B=11)[letter.upper()]
    pitch += sum(1 if char in '#♯' else -1 for char in accidental)
    return (int(octave) + 1) * 12 + pitch


def validate_record(directory, schema):
    metadata = load_json(directory / 'metadata.json')
    errors = sorted(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(metadata),
                    key=lambda error: str(list(error.path)))
    if errors:
        raise ValidationError(f'{directory}: {errors[0].message}')
    if directory.name != metadata['id']:
        raise ValidationError(f'{directory}: directory must match scale id')
    for field in ['make', 'model', 'source']:
        if not metadata[field].strip():
            raise ValidationError(f'{field}: must not be blank')
    if any(not credit.strip() for credit in metadata['contributors']):
        raise ValidationError('contributor credit must not be blank')
    if (metadata.get('yearFrom') is not None and metadata.get('yearTo') is not None
            and metadata['yearFrom'] > metadata['yearTo']):
        raise ValidationError('yearFrom exceeds yearTo')
    low, high = metadata['keyRange']['lowest'], metadata['keyRange']['highest']
    if low > high:
        raise ValidationError('lowest note exceeds highest note')
    raw = read_text(directory / 'strings.csv')
    # The app parses one physical line at a time; multiline CSV fields are not compatible.
    data_lines = []
    expected_comments = {key: metadata.get(key, '') for key in ['make', 'model', 'source', 'notes']}
    first, last = metadata.get('yearFrom'), metadata.get('yearTo')
    expected_comments['years'] = f'{first if first is not None else ""}-{last if last is not None else ""}'
    for line in raw.splitlines():
        if not line.strip():
            continue
        if line.startswith('#'):
            key, separator, value = line[1:].partition(':')
            if not separator or key.strip() not in expected_comments:
                raise ValidationError('CSV comments must use make, model, years, source, or notes')
            if value.strip() != expected_comments[key.strip()]:
                raise ValidationError(f'CSV {key.strip()} conflicts with metadata')
        else:
            data_lines.append(line)
    if not data_lines:
        raise ValidationError('CSV has no header')
    rows = []
    previous = None
    warnings = []
    for index, line in enumerate(data_lines):
        try:
            fields = next(csv.reader(io.StringIO(line), strict=True))
        except csv.Error as error:
            raise ValidationError(f'CSV row {index + 1}: malformed quoting or multiline field') from error
        if index == 0:
            if fields != COLUMNS:
                raise ValidationError('CSV header must match the canonical columns and millimeter units')
            continue
        if len(fields) != len(COLUMNS):
            raise ValidationError(f'CSV row {index + 1}: incorrect field count or multiline field')
        row = dict(zip(COLUMNS, fields))
        note = midi_note(row['note'])
        if not low <= note <= high:
            raise ValidationError(f'note {note} is outside keyRange')
        if previous is not None and note <= previous:
            raise ValidationError('notes must be unique and sorted in ascending MIDI order')
        previous = note
        construction = row['construction']
        if construction not in ['plain', 'single', 'double'] or row['strings'] not in ['1', '2', '3']:
            raise ValidationError(f'note {note}: invalid construction or string count')
        values = {}
        for field in DIMENSIONS:
            text = row[field]
            value = float(text) if text else None
            if value is not None and (not math.isfinite(value) or value <= 0):
                raise ValidationError(f'note {note}: {field} must be finite and positive')
            values[field] = value
        core, inner, outside = (values[field] for field in ['core_mm', 'inner_layer_mm', 'outside_mm'])
        if construction == 'plain' and any(values[field] is not None for field in
                ['inner_layer_mm', 'outside_mm', 'loop_to_winding_mm', 'winding_length_mm']):
            raise ValidationError(f'note {note}: plain wire has winding measurements')
        if construction == 'single' and inner is not None:
            raise ValidationError(f'note {note}: single winding cannot have an inner layer')
        diameters = [value for value in [core, inner, outside] if value is not None]
        if any(a >= b for a, b in zip(diameters, diameters[1:])):
            raise ValidationError(f'note {note}: winding diameters must increase')
        overall = values['overall_length_mm']
        if overall is not None:
            for field in ['speaking_length_mm', 'loop_to_winding_mm', 'winding_length_mm']:
                if values[field] is not None and values[field] > overall:
                    raise ValidationError(f'note {note}: {field} exceeds overall length')
            loop, winding = values['loop_to_winding_mm'], values['winding_length_mm']
            if loop is not None and winding is not None and loop + winding > overall:
                raise ValidationError(f'note {note}: loop plus winding exceeds overall length')
        if metadata['coverage'] == 'bass' and construction == 'plain':
            raise ValidationError('bass coverage is defined as wound strings only')
        if metadata['coverage'] == 'plain-wire' and construction != 'plain':
            raise ValidationError('plain-wire coverage contains a wound string')
        required = ['core_mm', 'speaking_length_mm']
        if construction != 'plain':
            required.append('outside_mm')
        if construction == 'double':
            required.append('inner_layer_mm')
        if any(values[field] is None for field in required):
            warnings.append(f'note {note}: incomplete design measurements')
        rows.append({'midiNote': note, 'construction': construction, 'strings': int(row['strings']), **values,
                     'notes': row['notes']})
    if not rows:
        raise ValidationError('scale must contain at least one note')
    if metadata['coverage'] == 'full-keyboard' and [row['midiNote'] for row in rows] != list(range(low, high + 1)):
        raise ValidationError('full-keyboard coverage requires every note in keyRange')
    return metadata, rows, warnings


def validate_repository(root):
    schema = load_json(root / 'schema/scale-metadata.schema.json')
    Draft202012Validator.check_schema(schema)
    scales = root / 'scales'
    if scales.is_symlink() or not scales.is_dir():
        raise ValidationError('scales must be a directory')
    records, seen = [], set()
    for directory in sorted(scales.iterdir()):
        if directory.name == 'README.md' and directory.is_file() and not directory.is_symlink():
            continue
        if directory.is_symlink() or not directory.is_dir():
            raise ValidationError(f'{directory}: unexpected entry')
        if {file.name for file in directory.iterdir()} != {'metadata.json', 'strings.csv'}:
            raise ValidationError(f'{directory}: expected only metadata.json and strings.csv')
        metadata, rows, warnings = validate_record(directory, schema)
        if metadata['id'] in seen:
            raise ValidationError(f'duplicate scale id {metadata["id"]}')
        seen.add(metadata['id'])
        records.append((directory, metadata, rows, warnings))
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('.'))
    args = parser.parse_args()
    try:
        records = validate_repository(args.root)
        for directory, _, _, warnings in records:
            for warning in warnings:
                print(f'WARNING {directory.name}: {warning}')
        print(f'Validated {len(records)} scale(s).')
    except (ValueError, OSError, csv.Error) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
