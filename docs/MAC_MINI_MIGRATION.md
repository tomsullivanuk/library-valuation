# Mac Mini migration runbook

Status: Mac Mini is the sole production host as of November 5, 2026. System
startup and daily snapshot services are installed and healthy. Final reboot
acceptance remains pending; do not claim fully unattended recovery until tested.
Baseline: v0.11.1. This is milestone 1 of the revised v0.12 roadmap.

## Preparation completed on the laptop

- A private snapshot of data, imports, output evidence/reports, caches and
  configuration was created outside Git. Every one of its 3,941 archived files
  was verified against a SHA-256 manifest (approximately 162 MB compressed).
- Canonical CSV counts include 3,753 catalog rows, 3,364 acquisitions,
  2,687 holding rows and 4,504 observations. These repository counts differ from
  the Library’s active-record, physical-copy and distinct-title counts.
- Root credential files, transient state, and the existing virtual environment
  are excluded. A preparation copy has been restored and verified on the destination. It is
  not the final cutover snapshot.
- No saved workspace-actions or reviewed-estimates file existed in the source
  data directory at snapshot time. Preserve them in the final transfer if created.

## Destination rehearsal results

- SSH key access verified; destination is Apple silicon with macOS 27.0.1 and
  approximately 274 GiB free. Host and account details remain private.
- Recreated an isolated Python 3.14.5 environment from pinned dependencies.
- Restored and hash-verified all 3,941 private snapshot files. All 603 tests and
  compilation passed on the destination.
- A temporary loopback HTTP smoke test passed against the restored records:
  2,727 physical copies, 2,565 active catalog records, 2,521 distinct titles,
  1,250 actions. The temporary server was stopped afterward. No production
  service or second production writer was enabled.
- iCloud Drive was selected for dated archive backups, with the live working
  repositories kept outside the sync folder. The preparation archive and manifest
  were copied into iCloud Drive and their local checksums verified. The independently
  synced laptop copy also passed archive checksum and all 3,941 member hashes.
  Recurring backup scheduling and a final-state recovery check remain pending.
- Fully unattended cold-boot recovery was selected. The owner explicitly approved
  disabling FileVault and completed that change; destination status was verified
  off before startup preparation. The machine already has system sleep disabled
  and restart-after-power-failure enabled. Actual cold-boot recovery still needs
  verification.
- No Time Machine destination is configured. iCloud Drive sync is not a full
  system backup; use distinct dated snapshots and verify recovery, rather than
  synchronizing the writable repositories directly.

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

## Startup and backup implementation

The prepared system LaunchDaemons run the library and daily snapshot command as
the destination account, not root. Only their plist installation requires owner
administrator authentication. The application remains bound to loopback; use SSH
forwarding for laptop administration. System service logs are private to the
account under `~/Library/Logs/LibraryValuation/`.

`operations/library_backup.py` takes the workspace write lock, archives canonical
state, imports, evidence, configuration and recovery code, verifies every member,
and publishes a dated snapshot into a separate destination folder. Transient
files, root credentials, virtual environments, prior migration archives and
symlinks are excluded. Existing snapshots are retained; monitor iCloud capacity
and agree a retention policy before pruning any recovery points. Validate an
independently synced copy periodically. iCloud synchronization may wait for the
account's cloud session/network; a successful local archive is not proof of upload.

After cutover, `data/production_moved.json` on the laptop prevents its workspace
from starting or saving. It must never be copied to the destination. This guard
does not disable unrelated command-line import tools; do not run production jobs
against the archived laptop repositories. Rollback requires preserving newer Mini
state and explicitly removing the guard only after reconciling that state.

Validation: 605 tests passed on both laptop and Apple-silicon destination after
adding snapshot coverage and the migrated-source write guard.

## Cutover and access verified

- Final frozen snapshot restored and verified against all 3,941 file hashes.
- System library service is running as the owner account; backup service completed
  successfully with exit code 0 and a dated verified snapshot in iCloud Drive.
- Laptop local service is stopped and the migrated-source guard is enabled.
- A user LaunchAgent on the laptop maintains an SSH loopback forward to the Mini.
  The usual `http://127.0.0.1:8765/` URL now resolves to the Mini workspace; its
  API workspace identity was checked against the destination. The connection
  retries after interruption and starts in the laptop user's login session.
- `Open Library.command` detects the archived-source marker and opens the remote
  library through that connection instead of starting the old local server.
- Remaining acceptance: reboot the Mini, do not log in locally, verify the system
  service starts, the laptop connection recovers, and backups complete or clearly
  report that iCloud synchronization is waiting for a user/cloud session. Then
  verify an independent cloud-synced final-state recovery copy.

The private installation artifacts and transfer receipts are retained on the
Mini outside Git. Credentials remain omitted from backup archives. Existing
source credentials will need a separate secure transfer and destination API
verification before milestone 2 starts external valuation collection.
