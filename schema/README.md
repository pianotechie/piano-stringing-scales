# Scale format v1

Each real scale occupies `scales/<id>/metadata.json` and `strings.csv`. The ID is a permanent lowercase UUID; retain it for corrections, use a new one for a different measured example or redesign. Only these two files are allowed in a scale directory. Test fixtures are excluded from the catalog.

## Metadata

See [the JSON Schema](scale-metadata.schema.json). Required fields are `schemaVersion` (1), `id`, `make`, `model`, `kind`, `coverage`, `keyRange`, `source`, `contributors`, and `license` (`CC-BY-4.0`). Optional fields are `variant`, `yearFrom`, `yearTo`, `sourceURL`, and `notes`. Unknown fields are rejected in v1. Omitted or null years mean unknown/open bounds; a supplied start must not exceed the end.

`kind` is `measured-original`, `published-reference`, or `proposed-redesign`. Coverage is `bass` (wound strings only), `plain-wire` (plain strings only), `partial`, or `full-keyboard`. `keyRange.lowest` and `highest` are the intended piano's MIDI bounds, within 21–108 as supported by the current app importer. Coverage describes note coverage, not measurement completeness: full-keyboard requires every note in keyRange, but missing dimensions remain allowed and are reported as warnings.

Source must explain origin and measurement context. Contributors are public display names. Review and suitability are not established by contributor metadata or a successful validation check; maintainer review remains necessary.

## Measurement CSV

Use exactly this header and column order:

```csv
note,construction,strings,core_mm,inner_layer_mm,outside_mm,speaking_length_mm,loop_to_winding_mm,winding_length_mm,overall_length_mm,notes
```

One row represents one note's string specification and its unison count, not a separate row for each unison string. Notes are MIDI numbers or names such as A0, C#4, Db4, or B♭3; rows must be unique and ordered by ascending MIDI number. Construction is `plain`, `single`, or `double`; strings is 1, 2, or 3.

Dimensions are millimeters, finite and positive when supplied. Empty cells mean not measured. Inner-layer diameter is the diameter across the first winding of a double-wound string; outside diameter is across the finished winding. Supplied diameters must increase from core to inner layer to outside. Plain strings cannot have winding measurements; single-wound strings cannot have an inner-layer diameter. Supplied speaking, loop-to-winding, and winding lengths must not exceed overall length; loop-to-winding plus winding length must not exceed overall length.

Quoted commas and escaped double quotes are supported. Multiline fields are prohibited because some importers process physical lines individually. Use UTF-8. The repository contract is deliberately stricter than standalone application imports: inch columns, alternative headers, and construction aliases are not accepted here.

Metadata JSON is authoritative. Prefer CSV without metadata comments. If present, `# make:`, `# model:`, `# source:`, `# notes:`, and `# years:` must agree exactly with JSON. Years use `from-to`, with empty ends for unknown bounds. Other comment types are rejected.

Files are limited to 1 MB each. Symlinks are prohibited. Scale licensing and source permission must be assessed by reviewers; validation cannot establish permission.

## Catalog

Run `python -m tools.build_catalog --root . --output build/snapshot --revision <full-commit-sha> --repository <owner/name>` with an empty output directory. `--repository` defaults to the `GITHUB_REPOSITORY` environment variable; the tool exits with an error when neither is set. The tool validates all records before writing anything. It copies the exact CSV and metadata bytes into a snapshot, includes license files, and generates `catalog.json` containing:

- `schemaVersion`, repository identity, source revision, and `scales`.
- Each scale's metadata, relative measurement/metadata paths, SHA-256 hashes of both files, note count, missing notes within keyRange, and measurement warnings.

Catalog entries are ordered by UUID and output is deterministic for identical source files and revision. Paths resolve within the snapshot; clients must verify hashes. The generator does not publish releases. An empty catalog is valid until real scales are added. Snapshot warnings indicate incomplete measurements, not approval or a safety rating.

## Release publication

The `Publish catalog` workflow runs when a tag is pushed and can be dispatched manually (on main or a tag) to retry; it does not run on ordinary pushes to main. The repository name is taken from `GITHUB_REPOSITORY`. Publishing from a tag releases the tagged commit. Its read-only build job runs the full test suite and builds a validated bundle; a separate job receives contents-write permission for release publication. Pull requests do not trigger publication. Workflow runs are serialized, and a dispatch on main skips a superseded main revision before publishing.

Each revision gets a release tag `catalog-<full-commit-sha>` with these assets:

- `catalog.json`, containing the snapshot catalog plus revision-specific `measurementURL` and `metadataURL` per scale.
- `<scale-id>.csv` and `<scale-id>.json` for individual downloads.
- `snapshot.zip`, containing the catalog, original scale directories, and license files.
- `LICENSE-DATA`, `LICENSE-CODE`.
- `latest.json`, identifying the repository, revision, release tag, catalog URL/hash, and snapshot URL/hash.

The discovery URL is:

```
https://github.com/pianotechie/piano-stringing-scales/releases/latest/download/latest.json
```

The pointer is an asset in each revision's release, not a separately overwritten mutable file. GitHub's latest-release redirect selects the active revision. Clients must retain the pointer they downloaded, follow its revision-specific catalog URL, verify its hash, and verify each CSV against the catalog hash. Retain the last valid cached revision if any request fails. Content hashes detect corrupt or inconsistent downloads; they are not signatures or a guarantee of engineering suitability.

Publication creates a draft release, uploads the assets, downloads every asset to verify the exact bytes, and only then publishes and promotes latest. Interrupted draft uploads can be retried and replaced. Published assets are never replaced by the publisher; a mismatch fails. Existing-release lookup examines the most recent 100 releases, so retries of older releases require maintainer intervention. A commit SHA identifies a revision, but GitHub administrator access can still alter releases; these are immutable by publisher policy, not enforced server-side immutability.

For local packaging, use a fresh output directory:

```sh
.venv/bin/python -m tools.release_bundle --root . --output build/release --revision "$(git rev-parse HEAD)"
```

Maintainers normally publish through the workflow. If manually invoking `tools.publish_catalog`, use authenticated GitHub CLI credentials, serialize calls, and verify the intended revision is still main first. Do not put tokens in source files. Older releases can be retained for provenance; application to a piano must remain an explicit action.
