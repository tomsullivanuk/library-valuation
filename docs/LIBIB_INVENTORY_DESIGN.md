# Libib Physical Inventory Design

## Status and Design Boundary

This is the PR1 design contract for v0.10.0. Entity names and behavioral
invariants are recommended decisions. Fields, filenames, encodings, and parser
details are **tentative** until representative Libib exports are profiled in
PR2. No production schema or import behavior is introduced by this document.

Libib is evidence about physical presence, copies, locations, and audit status.
It is not the authority for intellectual identity or canonical bibliographic
metadata.

## 1. Source Boundary

### Principal source families

The shared import architecture has three principal book-source families:

1. **Amazon Import** for the existing Amazon order-history workflow;
2. **Libib Import** for Libib-managed inventory exports and audits; and
3. **Manual Entry** for project-owned intake when neither external export is the
   appropriate authority.

This is architectural direction, not a v0.10.0 migration of historical Amazon
files, schemas, IDs, or behavior. Barcode scanning is an input mechanism feeding
a Libib Import or Manual Entry; it is not a fourth durable source family.
Estate inventory, donations, inherited books, dealer purchases, and similar
provenance normally use Libib Import or Manual Entry with acquisition type,
origin, notes, dates, and source evidence where known. They do not justify new
top-level import families by themselves.

### Conceptual inputs

The importer may support a Libib CSV export and, if actual evidence justifies
it, a directory or batch containing multiple related export files. “Batch” does
not imply that arbitrary files or a proprietary backup format are supported.
PR2 must identify formats, encodings, delimiters, column names, and export
variants from representative files before support is declared.

The workflow should accept an explicit file path and, in PR3, one explicitly
selected audit-area directory. The project convention is:

```text
input/
└── libib/
    ├── living-room-bookshelf-near-office/
    ├── study/
    ├── basement-storage/
    └── ...
```

Each child directory is one operational audit area. Original Libib filenames,
such as `library_20260720_013144.csv`, should normally remain unchanged. A later
workflow may recursively import all registered audit-area directories, but
recursive discovery is not part of PR3 and must not be implemented implicitly.
Discovery must always fail on ambiguity rather than selecting a file by
unexplained filesystem order. Explicit file input wins.

### Operational import-folder policy

Folder names are workflow labels, Libib `collection` values are source
evidence, and neither is permanent inventory or location identity.
Project-owned `location_id` remains the durable physical-location identity. An
importer must preserve folder and source labels separately and must never
silently overwrite either one with the other.

PR3 should evaluate a small durable operational-metadata repository named
`inventory_import_folders` (tentative file name
`data/inventory_import_folders.csv`). It is a safety registry for audit-area
workflow, not inventory, catalog, holding, location, or source-item data.

Tentative fields:

- `folder_id`: stable project-owned registration identity;
- `folder_path`: normalized path relative to `input/libib/`;
- `expected_collection_label`: exact confirmed Libib label;
- `first_imported_at`;
- `last_imported_at`; and
- `notes`.

The schema, filename, path-normalization rules, and history treatment remain
tentative until PR3. Folder path is mutable operational metadata, not import
identity or `location_id`.

On the first successful import from a new audit-area folder, register the
folder and preserve the single observed Libib collection label exactly as
`expected_collection_label`. For example:

```text
folder_path: living-room-bookshelf-near-office
expected_collection_label: Living Room Bookshelf near office
```

Registration happens only after structural parsing succeeds. If a file has no
single usable collection label, registration requires review rather than an
invented expectation.

On a subsequent import, exact comparison with the registered label permits the
workflow to continue. A different label must not create a new location, update
the registration, or remap holdings automatically. It produces
`collection_label_changed_or_misfiled` with the registered collection, observed
collection, relative folder path, and a recommendation to verify whether the
Libib collection was intentionally renamed or the export was saved in the
wrong audit-area folder.

An intentional rename requires manual confirmation. Confirmation may update
the folder's expected label while immutable import/source evidence preserves
the former label. A later location-alias decision may map both labels to the
same `location_id`; automatic remapping is prohibited.

Renaming an audit-area folder also requires manual confirmation. The confirmed
operation updates `folder_path` while preserving `folder_id`; an unrecognized
path must not be joined to a registration merely because its collection label
or a file hash matches. Previous paths may be retained in notes or a future
registration-history design if PR3 evidence justifies it.

Explicit files outside the registered `input/libib/` convention remain
parseable, but they do not silently create a folder registration. The caller
must provide or confirm their operational audit-area context.

### Hashing, repeat detection, and provenance

Hash the exact input bytes with SHA-256 before parsing. A batch fingerprint
should be a deterministic hash of relative member names and member hashes, not
archive timestamps or discovery order. The durable import record owns a
project-generated `inventory_import_id`; a source filename or Libib identifier
does not.

Import history and exact-repeat detection are keyed by content hash and
project-owned `inventory_import_id`, never by filename, modification timestamp,
folder name, or `folder_id`. Copying the same bytes under another filename does
not create a new import. A different file with the same confirmed collection
label does create a new import because its content hash differs. A known hash
encountered in another registered folder remains a duplicate and may also
produce a misplaced-file review condition; it never becomes a second import.

An exact `(source_type, file_hash, parser_contract)` repeat is a no-op or a
reported already-imported result. It must not create a second import, source
items, or holdings. A later parser version may support an explicit reprocess
operation, but must preserve the original provenance and must not masquerade as
a new observation date.

Tentative provenance includes source type, safe filename, hash, parser version,
durable schema version, imported timestamp, source-export timestamp if present,
declared audit scope, scope key or description, declared/inferred completeness,
row counts, accepted/rejected counts, and an optional parent/import relationship
for deliberate reprocessing.

### Privacy and raw files

Libib exports may contain personal notes, tags, URLs, barcodes, location names,
or account-specific fields. PR2 must inventory columns and classify each as
retained, normalized, redacted, or rejected. Logs and generated artifacts use
safe paths and must not echo raw rows. Tests use synthetic or deliberately
sanitized fixtures.

Raw user exports remain user-owned inputs and should be ignored by version
control. The project should not copy raw files into `data/` by default. Durable
source items retain only an allowlisted, privacy-reviewed evidence subset plus
the import/hash/row reference needed for audit. A raw-payload pointer is allowed
only if it does not make a private file a required generated artifact.

### Durable versus generated

Inventory imports, accepted source items, holdings, matches, and explicit user
review decisions are durable under `data/`. Parse diagnostics, reconciliation
summaries, exception CSV/XLSX files, and reviewer workbooks are generated under
`output/`. Raw exports stay under user-controlled input. Temporary staging data
is neither durable truth nor a generated report and is removed or safely
ignored after recovery.

### PR2 assumptions requiring validation

- whether Libib has one or several CSV/export variants;
- actual columns, escaping, encoding, date formats, and blank conventions;
- whether item, copy, barcode, row, library, group, or collection IDs exist and
  remain stable across exports;
- whether quantity means identical copies, a grouped record, or display data;
- whether locations are single-valued, multi-valued, hierarchical, or tags;
- whether Libib's catalog field represents a physical location, logical
  collection, ownership group, audit batch, or mixed usage;
- whether an export declares full-library versus filtered/partial scope;
- whether deleted/archive status or last-updated/audited timestamps are exposed;
- whether manually edited ISBN/title/author values can be distinguished; and
- whether sets and multi-volume records have machine-readable structure.

### PR2 observed Libib CSV profile

PR2 profiled the untouched `library_20260720_013144.csv` export (SHA-256
`0dab102fd1c99d0bf3cac1b87211853dacf20fa79468167fa2d6875936dccef6`).
The file contains 30 book records. The committed fixtures are synthetic,
privacy-safe reductions of its structure; the user's raw export is not copied
into the repository.

Observed byte and CSV characteristics:

- UTF-8 text without a byte-order mark;
- LF newlines;
- comma delimiter;
- double-quote quoting with CSV escaping;
- one header plus 30 records, each with exactly 30 fields;
- quoted commas occur in normal text fields; no embedded record newlines were
  present in this sample;
- non-ASCII text is present and decodes cleanly as UTF-8; and
- blank values are represented by empty CSV fields, not placeholder strings.

Observed columns, in order:

```text
item_type,title,creators,first_name,last_name,collection,ean_isbn13,
upc_isbn10,description,publisher,publish_date,group,tags,notes,price,
length,number_of_discs,number_of_players,age_group,ensemble,aspect_ratio,
esrb,rating,review,review_date,status,began,completed,added,copies
```

The PR2 parser requires the fields needed for source identity evidence and the
approved normalization contract: `item_type`, `title`, `creators`,
`first_name`, `last_name`, `collection`, `ean_isbn13`, `upc_isbn10`,
`publisher`, `publish_date`, `added`, and `copies`. The other observed columns
are optional. Missing optional columns and empty values are accepted. Unknown
future columns are preserved in `raw_values` and diagnosed rather than dropped.

Observed value semantics and coverage:

- All 30 `item_type` values are `book`.
- All 30 ISBN-13 values are 13-character strings with valid checksums.
- All 30 ISBN-10 values are 10-character strings with valid checksums, including
  leading-zero cases; every pair converts to the supplied ISBN-13 with no
  conflict.
- All 29 non-empty `publish_date` values use `YYYY-MM-DD`. This is bibliographic
  publication-date evidence, not an acquisition date.
- All 30 `added` values use `YYYY-MM-DD` and share the export's observed add
  date. `added` means added to Libib; it must not be interpreted as acquired.
- All 30 `copies` values are the string `1`. The sample provides no evidence
  about quantities greater than one or how Libib represents separately
  identified copies.
- No duplicate full rows, titles, ISBN-10 values, or ISBN-13 values occur. The
  export therefore does not resolve how duplicate books or copies are emitted.
- `collection` is populated on every row but has one label in this sample. It is
  retained as `source_collection_label`; the sample cannot establish whether it
  is a physical location, logical catalog, ownership group, or audit scope.
- `creators` contains the fullest displayed attribution. `first_name` and
  `last_name` occur within `creators` on all rows and appear to identify a
  primary creator, while `creators` can contain punctuation and additional
  names. PR2 preserves and whitespace-normalizes `creators`, and separately
  constructs `primary_author_display` as `first_name last_name`. It does not
  split `creators` into a contributor list because delimiter semantics are not
  proven.
- `publisher` is populated on 29 of 30 rows and is preserved verbatim plus a
  whitespace-normalized value.
- The export exposes no obvious stable Libib row, item, copy, or barcode ID.
  Row number is source position only and is not a durable identity.
- The export contains no explicit full/partial completeness flag, audit-scope
  type, export timestamp, or audit-completion marker. The populated `collection`
  label cannot safely substitute for those fields.

The earlier `library_20260718_115853.csv` was opened/resaved through Excel and is
not a supported-format fixture. It demonstrates real corruption: all 25
ISBN-13 cells became scientific notation, 10 ISBN-10 cells became nine-digit
values consistent with lost leading zeroes, and 49 non-empty publication/added
dates became locale-style slash dates. The parser reports these conditions and
does not silently accept the damaged values.

A zero-diagnostic parse establishes only that the CSV structure and implemented
normalization checks succeeded. It does not make Libib bibliographic metadata
canonical, prove that an ISBN identifies the intended edition, or establish
bibliographic authority.

PR2 does not settle export completeness, quantity greater than one, duplicate
copy representation, collection/location meaning, grouped/set behavior, or
stable source identity. Those remain explicit PR3 inputs or require another
representative Libib export.

## 2. Entity Model

### Naming decision

Use **Inventory Holding** and `holding_id` for one project-tracked physical copy.
This resolves the existing “Owned Copy / Inventory Holding” synonym without
adding `inventory_item_id`. “Item” is already overloaded by Catalog Item and
Source Item; `holding_id` clearly identifies the copy-level possession layer.

Use **Inventory Import** and **Inventory Source Item** as inventory-specialized
implementations of the existing Source Import and Source Item concepts. Use
**Catalog Inventory Match** for the auditable link decision. Use **Inventory
Review** only for manual match confirmation/override and unresolved disposition
or copy-splitting decisions; ordinary audit facts belong on the holding.

### Inventory Import

**Purpose:** One attempted-and-accepted Libib ingestion event and its provenance.

**Key:** Project-owned `inventory_import_id`.

**Relationship to catalog:** None directly; it owns source items.

**Field ownership:** Source fields include export timestamp and source scope;
derived fields include hash and counts; user-maintained fields are limited to
safe label, explicit completeness declaration, and notes.

**Immutability:** Hash, source type, accepted parser/schema version, timestamps,
and accepted counts do not change. Corrections create an annotated/reprocessed
import rather than editing evidence.

**Regeneration:** Source items can be reproduced from retained raw input when
available, but the accepted import identity and observation time persist.

**Tentative fields:** `inventory_import_id`, `source_type`, `source_name`,
`source_file_name`, `source_file_hash`, `source_exported_at`, `imported_at`,
`parser_version`, `schema_version`, `audit_scope_type`, `audit_scope_key`,
`audit_scope_description`, `audit_scope_completeness`, `audit_completed_at`,
`source_row_count`, `accepted_row_count`, `rejected_row_count`,
`supersedes_import_id`, `notes`.

**Schema implication:** Likely a new versioned inventory repository, not a
silent widening of the Amazon-specific `data/import_manifest.csv`.

### Inventory Source Item

**Purpose:** Preserve one privacy-filtered Libib row or logical source record as
observed, even when it cannot be matched.

**Key:** Project-owned `inventory_source_item_id`, deterministically scoped to
the import and source row/record evidence; never merely a Libib ID.

**Relationship to catalog:** None directly authoritative. Match records connect
it to zero or one accepted catalog item; a grouped row may require review and
multiple eventual holdings.

**Field ownership:** `source_*` fields are immutable evidence; normalized ISBN
and fingerprints are derived; no user corrections mutate the source row.

**Immutability:** Accepted source values and their import/row reference remain
unchanged. A later export creates new source-item observations.

**Regeneration:** Normalized fields may be regenerated under a versioned parser;
original accepted values remain auditable.

**Tentative fields:** `inventory_source_item_id`, `inventory_import_id`,
`source_row_number`, `source_record_id`, `source_copy_id`, `source_isbn10`,
`source_isbn13`, `source_title`, `source_contributors`, `source_publisher`,
`source_publication_year`, `source_edition`, `source_format`, `source_quantity`,
`source_catalog_label`, `source_location`, `source_condition`, `source_tags`,
`source_audit_status`,
`source_last_audited_at`, `normalized_isbn13`, `normalized_title_author_hash`,
`source_scope_key`, `source_scope_membership`, `grouped_record_flag`,
`privacy_redacted`, `parser_version`.

**Schema implication:** A durable source-item table is required in v0.10.0.
Without it, unmatched evidence, changed rows, and match provenance cannot be
preserved reliably.

### Inventory Holding

**Purpose:** Represent one believed physical copy independently of catalog and
Libib identities.

**Key:** Immutable project-owned `holding_id`.

**Relationship to catalog:** Zero or one current `catalog_item_id` while
unresolved; normally exactly one after a confirmed match. A catalog item may
have many holdings.

**Field ownership:** Source-derived fields initialize or refresh observed
location/condition/audit facts; current status, manual location/condition,
disposition, notes, and confirmations are user-maintained or explicitly
reconciled. Source observations never silently overwrite user-maintained values.

**Immutability:** `holding_id` never changes or gets recycled. Catalog links may
be superseded through match history. Disposition changes must be explicit.

**Regeneration:** Holdings are durable, not wholesale regenerated. Reconciliation
may link a new observation to an existing holding or propose a new holding.

**Tentative fields:** `holding_id`, `catalog_item_id`, `created_from_source_item_id`,
`acquisition_id`, `inventory_status`, `location_id`, `condition_current`,
`location_confidence`, `location_verified_at`, `last_observed_import_id`,
`last_observed_at`, `last_audited_at`, `audit_status`, `disposition_type`,
`disposed_at`, `state_source`, `user_confirmed_at`, `notes`, `created_at`,
`updated_at`.

**Schema implication:** New durable repository. One row per copy is preferred;
no `quantity_current` is needed for normal holdings because multiplicity is
represented by rows. A temporary unresolved grouped source item may carry
quantity until copy expansion is safe.

### Inventory Location

**Purpose:** Represent a stable, project-owned physical place independently of
Libib labels and holding identity.

**Key:** Immutable project-owned `location_id`.

**Relationship to holdings:** An Inventory Holding references zero or one
current believed `location_id`. Many holdings may share a location. Moving a
holding changes its current `location_id`; it does not change `holding_id` or
`catalog_item_id`.

**Field ownership:** The project owns location name, hierarchy, type, status,
and notes. Source labels are evidence and mappings, not location identity.

**Immutability:** `location_id` remains stable when `location_name` changes or a
location is re-parented. IDs are not recycled.

**Regeneration:** Locations are durable and are not regenerated from Libib
labels. Unknown or ambiguous labels create review items, not locations.

**Tentative repository:** `data/inventory_locations.csv`.

**Tentative fields:** `location_id`, `location_name`, `parent_location_id`,
`location_type`, `location_status`, `notes`, `created_at`, `updated_at`.

Locations may be hierarchical—general area, room, bookcase, shelf, or box—but
fine-grained shelf discipline is optional. `Study` and `Basement Storage` are
valid durable locations. Parent references must be acyclic and may be blank.

### Source location labels and aliases

The original Libib catalog/location label remains immutable on the Inventory
Source Item, even after mapping. PR2 must determine whether that field is truly
physical, logical, mixed, or differently used across exports.

A tentative `data/inventory_location_aliases.csv` may map several normalized
source labels to one `location_id`, with fields such as `source_family`,
`source_label`, `location_id`, `mapping_status`, `mapping_confidence`,
`confirmed_by`, `confirmed_at`, and `notes`. PR3 should add this repository only
if representative evidence shows that durable mappings materially improve safe
re-import. The semantic capability is required even if mappings initially live
as inventory review decisions.

Mapping is conservative. Several inconsistent labels may map to the same
durable location after confirmation. Unknown, unmapped, ambiguous, or apparently
logical labels remain reviewable and never create locations automatically.
Mapping a label supplies location evidence; it does not by itself prove that a
holding was physically verified there.

### Catalog Inventory Match

**Purpose:** Record the proposed, automatic, manual, rejected, or superseded
relationship between an inventory source item/holding and a catalog item.

**Key:** Project-owned `inventory_match_id`.

**Relationship to catalog:** References a candidate/accepted `catalog_item_id`
and an `inventory_source_item_id`; once a holding exists it may also reference
`holding_id`.

**Field ownership:** Candidate evidence and automatic outcome are derived;
manual decision, reason, and note are user-maintained.

**Immutability:** Evidence snapshot, method, rule version, and historical manual
decision are append-preserving. A later decision supersedes rather than edits
the prior accepted record.

**Regeneration:** Automatic candidates can be recomputed, but an accepted manual
decision remains authoritative until explicitly superseded or invalidated.

**Tentative fields:** `inventory_match_id`, `inventory_source_item_id`,
`holding_id`, `catalog_item_id`, `match_status`, `match_method`,
`match_confidence`, `candidate_count`, `candidate_rank`, `evidence_json_or_hash`,
`matching_rule_version`, `decided_by`, `decided_at`, `decision_reason`,
`supersedes_match_id`, `invalidated_at`.

**Schema implication:** New versioned durable match repository; do not collapse
this provenance into `catalog_items.csv`.

### Inventory Review

**Purpose:** Preserve a narrow manual decision that cannot be represented by an
accepted match or holding state, such as splitting a set, confirming quantity,
or resolving a disposition conflict.

**Key:** Project-owned `inventory_review_id`.

**Relationship to catalog:** Optional `catalog_item_id`; always references the
source item, holding, match, or exception being reviewed.

**Field ownership:** User-maintained decision and notes; derived queue status and
reason codes.

**Immutability:** Completed decisions are append-preserving and superseded
explicitly. Queue projections are regenerated.

**Regeneration:** Review records persist; open/closed queue views regenerate.

**Tentative fields:** `inventory_review_id`, `subject_type`, `subject_id`,
`catalog_item_id`, `review_reason`, `review_status`, `decision`, `reviewed_by`,
`reviewed_at`, `notes`, `supersedes_review_id`.

**Schema implication:** Prefer a new inventory-specific repository in v0.10.0.
The existing `collector_reviews.csv` is catalog-level research workflow state
and has the wrong subject and lifecycle.

### Audit scope decision

The **Inventory Import is the audit-batch boundary** in v0.10.0. It owns the
declared scope and completeness because conclusions about absence apply to an
import as a whole. Scope types must distinguish at least `partial_batch`,
`location_specific`, `filtered_export`, `full_export`, and `unknown`. Scope has
a stable key or explicit description when possible, plus completeness
`complete`, `in_progress`, or `unknown` and an optional completion time.

An Inventory Source Item may also retain its source location/scope key and
membership evidence. That row-level evidence explains why a book falls inside a
location or filter; it does not redefine the import's completeness. A separate
Audit Batch entity is deferred because it would duplicate Inventory Import in
v0.10.0. If later workflows need several imports to form one coordinated audit,
they may add a grouping entity without changing import identity.

Audit classification is a derived relationship among a catalog item, holdings,
and a particular audit scope—not a global catalog status. Required outcomes are:

- `verified_present`: a holding was explicitly observed or audited in scope;
- `not_yet_audited`: no completed applicable audit has evaluated the item;
- `outside_audit_scope`: the item is known not to belong to the current scope;
- `possible_missing` or `needs_review`: the item was expected in an applicable
  scope but evidence or scope completion is insufficient for certainty; and
- `verified_missing`: an explicit completed audit of an applicable scope
  supports non-presence under a reviewed policy.

Without scope evidence, a catalog item defaults to `not_yet_audited`, never
missing. `verified_missing` is not a disposition and does not mean sold,
donated, or discarded.

## 3. Physical Copy Semantics

- One holding row represents one physical copy. Two identical copies share a
  `catalog_item_id` but have different `holding_id` values.
- A trustworthy source quantity greater than one expands to distinct holdings
  with shared source provenance. Until PR2 validates quantity semantics, keep
  the row grouped and route it to review rather than inventing copies.
- Physical location is a durable entity referenced by `location_id`, not catalog
  metadata or a source label. Multiple copies may occupy different locations.
  Renaming a location preserves `location_id`; moving a holding changes only its
  current location reference. Conflicting simultaneous or unmapped source labels
  are exceptions.
- `present` or `believed_present` means current inventory belief. `verified`
  means direct audit evidence exists at a date. Neither is acquisition history.
- Audit coverage uses `verified_present`, `not_yet_audited`,
  `outside_audit_scope`, `possible_missing`/`needs_review`, and the narrowly
  gated `verified_missing`. Holding/disposition state separately records current
  belief and `sold`, `donated`, `given_away`, `discarded`, or `other`; absence
  alone sets none.
- `last_observed_at` records source evidence; `last_audited_at` and audit status
  record physical verification. Import time is not automatically audit time.
- Current location confidence uses `last_verified_at` or equivalent audit
  context. A mapped label without verification is weaker location evidence than
  a physically audited holding.
- Condition is copy-specific and source-attributed. Missing condition remains
  unknown and is not copied from catalog or acquisition data.
- A set, bundle, or multi-volume row remains one source item but may eventually
  create several catalog links and holdings. Until composition is proven it is
  flagged as grouped/ambiguous, not force-expanded.

These facts must remain distinct:

| Fact | Meaning | Primary durable record |
| --- | --- | --- |
| Acquisition history | How/when a copy may have entered the library | Acquisition |
| Believed inventory | Current project belief about an individual copy | Inventory Holding |
| Audit evidence | Who/what observed a copy, where, and when | Source item plus holding audit fields; event history deferred |
| Disposition history | Explicitly confirmed exit or loss | Holding state plus append-preserving review/provenance |

The current holding row is required in v0.10.0. A general inventory-event table
is deferred unless PR2/PR3 proves that safe reconciliation or auditability cannot
be achieved without it. Import/source-item and match history already preserve
source observations and link decisions; this avoids prematurely creating two
overlapping histories.

Likewise, v0.10.0 stores current believed `location_id` plus verification date
or equivalent context. A general holding-movement or location-event history is
deferred unless PR2 or implementation evidence shows it is necessary. Moving a
holding must still update timestamps/audit context without changing durable
holding, catalog, or location identities.

## 4. Matching Policy

### Conservative cascade

For each inventory source item, normalize evidence and generate all candidates
before accepting a link:

1. exact valid normalized ISBN-13;
2. valid ISBN-10 converted to ISBN-13, then exact match;
3. another exact source identifier only if PR2 proves a safe, one-to-one mapping
   to an identifier already stored on catalog records;
4. normalized title plus author, with uniqueness and compatibility checks;
5. normalized title plus edition, publisher, year, format, or contributor
   evidence sufficient to distinguish candidates;
6. weak or conflicting evidence: manual review;
7. no existing candidate: unmatched-to-existing-catalog, then either eligible
   for the new-identity gate below or preserved for manual review.

Title-only matching is never an automatic high-confidence match. ISBN agreement
is not sufficient if the catalog contains duplicate records or source evidence
conflicts materially on format/edition; such cases are reviewed.

### Required match output

Every evaluation records `match_method`, `match_confidence`, candidate count,
candidate IDs/ranks or a reproducible evidence snapshot, matching-rule version,
and outcome. Confidence describes evidence quality (`high`, `medium`, `low`,
`needs_review`), not permanent truth.

- Zero candidates remains unmatched and preserved.
- More than one eligible candidate is ambiguous; deterministic sorting may rank
  candidates but must not break a semantic tie.
- Duplicate catalog records prevent automatic acceptance unless an existing
  explicit catalog-merge/duplicate rule leaves exactly one active target.
- A single weak candidate remains reviewable rather than being promoted by
  uniqueness alone.
- Manual confirmation accepts a candidate with actor/time/reason. Manual reject
  may leave the item unmatched or choose a different candidate.
- Automatic or manual matches may later be invalidated or superseded; prior
  evidence and decisions remain auditable.
- Matching never copies Libib title/author/publisher into canonical catalog
  fields. Differences may produce a catalog-correction suggestion outside this
  release's automatic behavior.

### New catalog identity from Libib

Matching an existing catalog item, creating a new catalog identity, creating a
physical holding, and recording an acquisition are four separate decisions.
The normal resolution flow is:

1. try to match an existing catalog item;
2. if no candidate exists and bibliographic evidence is strong, internally
   consistent, and unambiguous, create a new durable `catalog_item_id`;
3. create or link the physical holding to that catalog item; and
4. link an acquisition only when independent acquisition evidence exists.

Automatic catalog creation is part of **PR4**, with full workflow acceptance in
PR7. A valid unique ISBN is the clearest initial qualifying case; PR4 must define
and test the exact threshold. Weak title/author evidence, conflicting
identifiers, grouped records, or uncertain editions remain unmatched and enter
manual review before catalog creation.

For a new catalog item, allowlisted Libib fields may initialize bibliographic
metadata with Libib provenance and source confidence because no existing record
would be overwritten. Later enrichment may reconcile those fields under normal
catalog rules. The source item remains immutable evidence. The new catalog item
gets a project-owned ID unrelated to the Libib ID or row order.

A holding linked to the new item may have `acquisition_id` blank. Acquisition
origin and date remain unknown; the importer must not fabricate an Acquisition
record or treat the Libib observation date as an acquisition date.

## 5. Reconciliation and Exception Views

Generate deterministic views for:

- Libib item unmatched to catalog;
- Libib item with multiple catalog candidates;
- catalog item with no Libib-confirmed holding;
- multiple physical copies;
- conflicting or changing locations requiring review;
- missing location;
- unmapped or ambiguous Libib catalog/location label;
- logical Libib label not confirmed as a physical location;
- invalid ISBN or conflicting ISBN evidence;
- weak title/author match;
- stale or absent audit date;
- source quantity versus resolved-holding discrepancy; and
- possible set, bundle, or multi-volume ambiguity.

Audit coverage views must separately show:

- confirmed physical holdings (`verified_present`);
- catalog items not yet audited;
- catalog items outside the current audit scope; and
- catalog items expected inside an explicitly completed audit scope but not
  found, classified as `possible_missing`/`needs_review` or `verified_missing`
  only under the reviewed completed-scope policy.

Each exception includes stable subject IDs, reason code, source import, relevant
evidence, current decision status, and suggested next step. Generated views must
not become repositories.

“Catalog item with no Libib-confirmed holding” is a reconciliation gap, not a
disposition. Absence can support stronger language only after the user explicitly
declares that a particular Libib export is a complete audited inventory and a
separate reviewed policy defines the consequence. Even then, the safe default
is `unverified` or a review task, not sold/removed.

## 6. Import and Idempotency Policy

### Exact repeat

The exact same content and parser contract returns the existing import result.
It performs no duplicate writes. A forced validation may recompute diagnostics
without changing durable identity.

### Operational folder acceptance scenarios

| Scenario | Required outcome |
| --- | --- |
| First import from a new folder | After a successful parse, create one folder registration and preserve the observed collection label exactly; create the content-hash-keyed Inventory Import under the PR3 transaction policy. |
| Second import with identical collection label | Continue normally, create a new import only when the content hash is new, and update operational `last_imported_at` after success. |
| Same export copied under a different filename | Detect the existing file hash and return the existing import result; filename does not create identity. |
| Different export with the same collection | Accept as a new Inventory Import because the hash differs; retain the existing folder registration. |
| Collection renamed in Libib | Emit `collection_label_changed_or_misfiled`; require manual confirmation before updating the expected label or creating any alias mapping. |
| Export saved into the wrong folder | Emit `collection_label_changed_or_misfiled` with both labels and the folder path; do not create a location or alter registration automatically. |
| Duplicate-file detection | Use the exact source hash regardless of filename, modification time, or folder; do not create duplicate imports or source items. |
| User renames an audit-area folder | Treat the new path as unregistered until manually confirmed; then update the existing registration's path without changing `folder_id`, import identities, holdings, or `location_id`. |
| Future location alias mapping | Permit old and new confirmed Libib labels to map to the same durable `location_id`; keep folder registration, source-label evidence, and location aliases separate and prohibit automatic remapping. |

### New full export

Create a new immutable import and source-item observations. Reconcile each row
against prior source identifiers and evidence, then catalog matches and holdings.
Retain a `holding_id` when the evidence identifies the same copy. Create a new
holding only when copy evidence or reviewed quantity expansion supports it.

Changed source metadata creates new evidence and exceptions where appropriate;
it does not overwrite catalog metadata or user-maintained holding fields. Added
rows may create proposed holdings. Removed rows become “not observed in this
import” only when the import is known complete; they do not imply disposition.

### Progressive, partial, or filtered audits

The caller or parser must classify scope as partial batch, location-specific,
filtered export, full export, or unknown, and completeness as complete,
in-progress, or unknown. Progressive imports may add or refresh positive
observations but cannot drive absence-based conclusions outside their declared
scope. A later partial import does not invalidate a holding confirmed by another
scope. Combining batches into a complete scope requires an explicit,
reproducible contract validated in PR2.

Inside an in-progress scope, no observation means `not_yet_audited` or
`needs_review`, depending on positive evidence that the item belongs in scope.
Inside an explicitly completed applicable scope, no observation may become
`possible_missing` or, only under an explicit reviewed policy and sufficient
evidence, `verified_missing`. Outside the scope it is `outside_audit_scope`.

### Identity and overwrite rules

- Prefer a verified stable copy identifier to reconnect observations. If only a
  row-level identifier exists, do not assume it identifies individual copies.
- When quantity is validated but copies lack identifiers, allocate stable
  holdings deterministically within a source lineage and never renumber existing
  holdings because row order changed.
- Preserve manual audit, location, condition, status, disposition, match, and
  notes. New source values are parallel observations or proposed updates.
- Preserve durable `location_id` values across renames. Reconcile a holding move
  as a change to current believed location plus verification context; do not
  recreate the holding or either catalog/location identity.
- Preserve every original source location label. Apply only confirmed mappings;
  unmapped or ambiguous labels remain exceptions.
- Deleted Libib rows stay represented by historical source items. Holdings
  remain unchanged until explicit reconciliation.
- Conflicting candidates, reduced quantities, or uncertain identity generate
  exceptions rather than duplicate holdings or destructive merges.

### Atomicity and recovery

Parse and validate the entire proposed import before durable mutation. Stage all
new repository versions in the same filesystem, validate referential integrity,
row counts, uniqueness, and hashes, then publish through an atomic manifest or
equivalent transaction boundary. On interruption, readers see the last accepted
state; recovery either completes the staged transaction once or discards it
safely. The exact mechanism is a PR3 implementation decision and must be tested
with injected failures.

## 7. Contract for v0.11.0 and v0.12.0

Version 0.10.0 must provide v0.11.0 Library Explorer and Action Center with
stable holdings, current copy state, source provenance, match confidence,
locations, audit freshness, exception reason codes, and review status. It does
not build those presentation or action layers.

It must provide v0.12.0 monthly refresh with idempotent import boundaries,
content fingerprints, scope/completeness, stable holding reconciliation,
versioned matching, atomic writes, and machine-readable summaries. It does not
combine Libib, Amazon, market collection, or artifact generation into one
orchestrator and does not define cross-source refresh scheduling or freshness
policy.

## 8. Open Questions and Decision Log

| Topic | PR1 decision or status |
| --- | --- |
| Canonical catalog identity | Settled: `catalog_item_id`; Libib evidence cannot replace it. |
| Stable physical-copy identity | Settled: project-owned `holding_id`. |
| Principal source families | Settled: Amazon Import, Libib Import, and Manual Entry. Barcode scan is an input mechanism; other origins use provenance within Libib or Manual Entry. Existing Amazon structures do not change in v0.10.0. |
| Operational Libib input layout | Settled: one audit-area directory below `input/libib/`; preserve original export filenames. Explicit file and one-directory imports precede later recursive all-folder import. |
| Import-folder registration | Settled concept, tentative schema: `inventory_import_folders` is operational safety metadata keyed by `folder_id`, separate from imports, source evidence, inventory, and locations. |
| Folder/collection mismatch | Settled: emit `collection_label_changed_or_misfiled`; never auto-create a location, update the expected label, or remap an alias. |
| Import identity | Settled: source file hash plus `inventory_import_id`, never filename, mtime, folder name, or folder registration. |
| Physical location identity | Settled: project-owned `location_id`; Libib labels are source evidence and never identity. |
| Location repository | Recommended tentative `data/inventory_locations.csv`; one current location per holding, optional hierarchy, broad locations valid. |
| Source-label mapping | Capability required; separate `data/inventory_location_aliases.csv` remains tentative pending PR2 evidence. Unmapped/ambiguous labels require review. |
| Movement history | Settled for v0.10.0: current believed location plus verification context; general event table deferred unless evidence requires it. |
| Libib-only catalog creation | Settled: strong, unambiguous no-match evidence may create a new catalog item in PR4; weak/conflicting evidence requires review. |
| Acquisition-free holding | Settled: allowed; acquisition origin/date remain unknown and no record is fabricated. |
| Source items durable in v0.10.0 | Settled: yes, to preserve unmatched/change/match evidence. |
| Current state versus event history | Settled for now: durable current holding plus immutable imports/source items/matches; general event table deferred unless implementation evidence requires it. |
| Manual review repository | Recommended: inventory-specific state; existing collector review has a different subject/lifecycle. Final layout in PR3/PR4. |
| Actual export formats/columns | Unresolved; profile representative files in PR2. |
| Stable Libib identifiers | Unresolved; determine identifier type, scope, uniqueness, and persistence in PR2. |
| Quantity semantics | Unresolved; do not expand copies until validated. |
| Location semantics | Unresolved; determine single/multiple/hierarchical/tag behavior. |
| Tags/groups/collections | Unresolved; determine whether descriptive, organizational, or copy-identifying. |
| Export completeness | Unresolved; find source signals and require explicit scope when absent. |
| Audit scope model | Settled: Inventory Import is the v0.10.0 audit-batch boundary; source items retain row-level scope evidence; separate grouping entity deferred. |
| Neutral audit default | Settled: `not_yet_audited`; missing requires an applicable completed scope. |
| Manually edited metadata | Settled boundary: evidence only, never silent canonical overwrite; detectability unresolved. |
| Sets and volumes | Settled boundary: preserve grouped row and review; machine-readable decomposition unresolved. |
| Raw files | Settled: user-owned ignored input; no default durable copy. |
| Exact repeat | Settled: content-hash idempotent under the same parser contract. |
| Missing later row | Settled: no automatic disposition. |

Material changes to settled decisions require an update here with evidence,
consequences, and migration impact before implementation proceeds.
