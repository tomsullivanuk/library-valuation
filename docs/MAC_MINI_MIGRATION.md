# Mac Mini migration runbook

Status: source preparation completed November 5, 2026; destination connection and
startup requirements pending. No destination restore or production cutover yet.
Baseline: v0.11.1. This is milestone 1 of the revised v0.12 roadmap.

## Preparation completed on the laptop

- A private snapshot of data, imports, output evidence/reports, caches and
  configuration was created outside Git. Every one of its 3,941 archived files
  was verified against a SHA-256 manifest (approximately 162 MB compressed).
- Canonical CSV counts include 3,753 catalog rows, 3,364 acquisitions,
  2,687 holding rows and 4,504 observations. These repository counts differ from
  the Library’s active-record, physical-copy and distinct-title counts.
- Root credential files, transient state, and the existing virtual environment
  are excluded. The snapshot remains on the source laptop; it is not yet an
  independent backup, a destination restore, or the final cutover snapshot.
- No saved workspace-actions or reviewed-estimates file existed in the source
  data directory at snapshot time. Preserve them in the final transfer if created.

## Preparation

1. Record the destination hostname/account, macOS version, CPU architecture,
   available disk, installed Python, and independent backup destination. Decide
   whether service is needed before login after a reboot, including disk unlock.
2. Inventory source code revision, canonical repositories and row counts, saved
   decisions, original imports, evidence, reports, caches and configuration.
   Keep private inventories and hashes outside Git. Credentials move separately;
   never place secrets in this document or a public PR.
3. Create and verify a private preparation snapshot. Take the workspace write lock
   while copying canonical state. Exclude virtual environments, process state,
   lock files, logs and credentials. This initial snapshot is not the final cutover
   backup and is not a substitute for independent ongoing backups.

Current runtime reads `data/` plus the evidence file
`output/libib_inventory_20261020/combined_market_evidence_summary.csv` and its
identity-validation dependencies. Preserve the complete evidence directory and
relevant output tree rather than only copying catalog CSVs. Registered reports
include physical book checks, follow-up resolutions and the review workbook.
Preserve `input/`, `cache/` and configuration for future operations as well.
Classify any additional working directories before transfer.

## Rehearsal

- Restore the tagged code and private snapshot under the destination account.
  Recreate `.venv` from `requirements.txt` using a compatible Python. Do not copy
  the laptop's virtual environment or reuse its absolute paths.
- Keep destination imports, publishing and notifications disabled. Do not start
  a second writable production service during rehearsal.
- Verify manifest hashes, repository row counts, stable identities, saved task
  states and estimates, and the Library's physical/title/catalog counts.
- Run the existing automated tests in the destination environment. Exercise the
  application and save/restart behavior against a disposable data copy only.
- Select and verify the startup arrangement. The existing launcher uses a
  user-session background job; it does not establish pre-login operation.
- Establish private administration (local access or an authenticated connection).
  The current loopback-only steward service is not a public hosting solution.
- Configure independent backups and demonstrate a restore. Record actual paths,
  start/stop instructions, and the agreed reboot/login recovery result.

## Final cutover

1. Stop laptop writers and jobs, capture the final state and a new verified backup.
2. Transfer the final delta and verify hashes and application results again.
3. Enable the Mac Mini as the sole production writer. Disable laptop production
   writes and record cutover time, host/account, paths and exact revision privately.
4. Test normal operation, saved changes, startup recovery and backup recovery.
5. If rolling back after Mac Mini writes, stop writers and preserve/reconcile the
   newer state first. Do not overwrite it with an older laptop snapshot.

Migration is complete only after the acceptance gate in the roadmap is met.
Family publication and the whole-library valuation run follow this milestone.
