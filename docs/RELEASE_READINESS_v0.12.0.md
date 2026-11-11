# v0.12.0 release readiness

November 11, 2026. Owner authorized merging PR #2 and creating a release.

- 850 tests passed on the release branch; Python compilation of application, tests and operations passed; whitespace and release-note link checks passed.
- Owner combined search was verified live in Chrome and on the Mini with values and locations retained. The preceding deployment also passed all 850 tests on the Mini.
- Release scope and limitations are recorded in RELEASE_NOTES_v0.12.0.md and the roadmap. AbeBooks approval/coverage, estimate publication, physical grading and broader invitations remain follow-ups.
- Only source, synthetic fixtures and operational documentation are included. Existing untracked `outputs/` and `docs/FAMILY_BROWSING_IMPLEMENTATION_PLAN.md` are intentionally excluded, as are ignored private data and credentials.
- The existing two-address access policy remains unchanged. No data migration or new transfer is performed by publication.
- Release procedure: commit release documentation to PR #2, merge its verified head into main, create annotated v0.12.0 tag at that merge commit, publish a non-draft, non-prerelease GitHub release marked latest, then verify PR/tag/release state.

The historical release.sh requires an entirely clean working tree and tags the current branch. Its compile/test/tag/push steps are performed explicitly for this release so unrelated untracked files are preserved and the tag targets merged main.
