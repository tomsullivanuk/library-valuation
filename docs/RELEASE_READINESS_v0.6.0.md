# Library Valuation v0.6.0 Release Readiness Review

## Status

**Ready for release after the documentation PR is reviewed and committed.**

Tagging and GitHub Release publication remain explicit post-commit operations.

## Release Summary

v0.6.0 delivers the **Full AbeBooks Baseline & Review Artifacts** workflow:

```text
Full assessed catalog
  -> conservatively paced AbeBooks observations
  -> source-neutral Market Evidence Summary
  -> reviewer-facing Excel workbook
  -> shareable static HTML report
```

All artifacts remain generated output. The workflow does not turn asking prices
or review recommendations into durable valuation records.

## Production Behavior Confirmation

The release does not change Market Evidence Summary aggregation, confidence,
outlier, range, or recommendation semantics. It does not change Research
Assessment scoring, signals, weights, bands, or persisted assessments. Durable
catalog, acquisition, import-manifest, and Collector Review records are
unchanged, as is the standard monthly `update-library` workflow.

## Command and Artifact Checks

Release review covers:

- `collect-full-library-abebooks-observations --help`;
- `summarize-market-evidence --help` and full-baseline summary generation;
- `build-abebooks-review-workbook --help` and workbook generation;
- `build-abebooks-review-report --help` and static HTML generation;
- a bounded AbeBooks test before any full run;
- distinct full-library outputs that do not replace validation-sample outputs;
  and
- ignored/untracked status for generated files under `output/`.

## Acceptance Checklist

- [x] Source integration spike records candidate-source constraints and defers
  eBay integration.
- [x] Full-library AbeBooks observation collection is implemented with
  conservative pacing and bounded-run support.
- [x] Market Evidence Summary can be generated from the full baseline.
- [x] Review workbook can be generated with focused queues, evidence detail,
  run summary, definitions, and acquisition context.
- [x] Static HTML report can be generated with tabbed queues, usage guidance,
  acquisition-year prompts, combined ranges, sort guidance, metadata, and
  caveats.
- [x] Static HTML report has been visually reviewed in a browser during PR5.
- [x] Generated artifacts remain ignored/untracked and separate from durable
  project data.
- [x] Complete automated test suite passes.
- [x] Python compile validation passes.
- [x] CLI help checks match documented options.
- [x] Release notes, changelog, README, roadmap, backlog, and architecture are
  aligned with implemented behavior.
- [x] eBay active listings are deferred to v0.7.0.
- [x] Non-appraisal caveats are present in reviewer and release documentation.
- [ ] Confirm the working tree is clean after this documentation PR is committed.

## Known Limitations

- Evidence consists of AbeBooks seller asking prices, not completed sales.
- Asking prices are not appraisals, fair market value, realized sale prices, or
  expected sale proceeds.
- Edition, condition, dust jacket, signature, seller credibility, and physical
  possession may materially affect value.
- Edition and condition matching remain lightweight.
- The full collector is not resumable and a catalog-scale run can take hours.
- eBay and other independent market sources are absent from v0.6.0.

## Remaining Release Steps

1. Review and commit the documentation/release-readiness PR.
2. Confirm the post-commit working tree is clean.
3. Create the annotated `v0.6.0` tag.
4. Publish the GitHub Release using `docs/RELEASE_NOTES_v0.6.0.md`.
5. Run the documented post-release smoke checks.

This PR does not create the tag or publish the release.
