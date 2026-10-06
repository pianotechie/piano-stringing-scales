# Piano Stringing Scales

A catalog of piano stringing scales for piano technicians, published as open data that applications can download and use for restringing work.

The catalog is new: no scale datasets have been added yet.

## Licensing

- **Scale datasets and accompanying descriptions:** [Creative Commons Attribution 4.0 International (CC BY 4.0)](LICENSE-DATA). This includes scale measurements, scale metadata, source descriptions, and technical notes supplied with a scale.
- **Repository scripts and tooling:** [MIT](LICENSE-CODE).
- **Repository documentation:** CC BY 4.0, unless explicitly identified otherwise.

CC BY 4.0 permits sharing and adapting licensed material, including commercial use. When sharing licensed material, provide appropriate credit, link to the license, retain supplied notices where required, and indicate modifications. See the license for the full terms. The data license does not require applications using the data to publish their source code.

Attribution and source information will accompany each scale. A source citation identifies where material came from; it does not establish permission to republish it. Only contribute material you have permission to publish under these terms.

These licenses apply to rights held by the contributors. They do not create exclusive rights over otherwise unprotected facts or measurements. Neither publication nor review guarantees that a scale is suitable for a particular piano; technicians must verify measurements and suitability before use.

The original MIT license previously applied to this repository. Existing MIT grants remain valid; the scope above governs new contributions. No scale datasets were present when this policy was adopted.

## Contributions

Read [CONTRIBUTING.md](CONTRIBUTING.md) before submitting a scale or correction. Contributions are reviewed through pull requests. The [v1 format contract](schema/README.md), validator, and catalog generator are in this repository.

## Development

Use Python 3.12 or later:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m tools.validate --root .
.venv/bin/python -m tools.build_catalog --root . --output build/snapshot --revision "$(git rev-parse HEAD)" --repository pianotechie/piano-stringing-scales
```

The repository name comes from `--repository OWNER/NAME` or, if the flag is omitted, the `GITHUB_REPOSITORY` environment variable (set automatically in GitHub Actions); the tools fail with an error if neither is set. The snapshot output directory must be empty; use a fresh directory for each build. GitHub Actions runs tests, validates real records, and builds a snapshot on pull requests and pushes to main with read-only repository permissions. A separate publication workflow, run only on version tags or by manual dispatch, builds and verifies revision-specific release assets before promoting the latest catalog. See [publication details](schema/README.md#release-publication). There are no real scales yet, so the catalog is empty. Synthetic fixtures are never catalog entries.
