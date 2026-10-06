# Contributing

Scales and corrections are contributed by pull request. The [v1 scale schema and CSV contract](schema/README.md) describe the required format.

## Adding a record

Create a permanent lowercase UUID directory under `scales/` containing only `metadata.json` and `strings.csv`. Follow the format contract and run the validator and tests described in the README. Correct an existing record in place only when it represents the same documented scale; use a new UUID for a different measured example or redesign. Keep synthetic examples under `tests/fixtures/`, not `scales/`.

Validation rejects structural errors and reports incomplete design measurements as warnings. Passing validation does not establish licensing rights, manufacturer authenticity, or suitability for restringing. Maintainers review those separately. This repository does not currently apply automatic engineering plausibility thresholds to unusual but structurally valid dimensions.

## Contribution terms

By submitting a contribution for inclusion in this repository, you agree to license:

- Scale datasets, metadata, accompanying descriptions, and documentation under [CC BY 4.0](LICENSE-DATA).
- Scripts and tooling under [MIT](LICENSE-CODE).

You retain ownership of rights you hold. You must have authority to grant these licenses. Do not submit confidential material or material subject to incompatible third-party terms.

For every scale, provide the contributor credit you want published, its source, and whether it is a measured original, a published reference, or a proposed redesign. Identify incomplete coverage and explain corrections. Do not describe a redesign or a measurement from one particular piano as an established manufacturer specification without supporting evidence.

For third-party material, provide the original license or explicit permission and attribution requirements so maintainers can assess compatibility before inclusion. A citation alone is insufficient. Maintainers will not change third-party licensing merely by adding a repository license label.

For external imports, retain original third-party notices where required; the current schema's CC-BY-4.0 field is not a mechanism for silently replacing another license.

## Public information

Only include information intended for public distribution. Review measurement notes and source descriptions for customer names, addresses, contact details, or other private information. Contributor credit is public; choose an appropriate display name.

## Review checklist

Each scale submission must confirm:

- I have permission to publish the submitted material under CC BY 4.0.
- I supplied the source and attribution information and identified any third-party terms.
- I reviewed the submission for private information.
- I identified whether the scale is an original measurement, published reference, or redesign, and described its coverage and changes.

Corrections will be reviewed before merging. A different measured example or redesign may belong in a separate scale rather than replacing an existing reference.
