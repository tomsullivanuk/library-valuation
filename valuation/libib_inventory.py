"""Durable, conservative inventory state for accepted Libib CSV imports.

The PR3 boundary creates import, operational-folder, and holding CSV state.  It
does not match catalog items, create catalog or location identities, reconcile
later observations, or discover audit areas recursively.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

from valuation.libib import LibibSourceRecord, parse_libib_csv


PARSER_VERSION = "libib_csv_v1"
REPOSITORY_SCHEMA_VERSION = "1"
AUDIT_COMPLETENESS_VALUES = frozenset({"complete_scope", "partial_scope", "unknown"})

INVENTORY_IMPORT_FIELDNAMES = (
    "schema_version",
    "inventory_import_id",
    "source_file_name",
    "source_file_hash",
    "source_collection_label",
    "folder_id",
    "folder_path",
    "audit_scope",
    "audit_completeness",
    "imported_at",
    "parser_version",
    "row_count",
)

INVENTORY_IMPORT_FOLDER_FIELDNAMES = (
    "schema_version",
    "folder_id",
    "folder_path",
    "expected_collection_label",
    "first_imported_at",
    "last_imported_at",
    "notes",
)

INVENTORY_HOLDING_FIELDNAMES = (
    "schema_version",
    "holding_id",
    "catalog_item_id",
    "inventory_import_id",
    "source_collection_label",
    "source_row_fingerprint",
    "source_title_key",
    "source_creator_key",
    "source_isbn_key",
    "current_location_id",
    "copies",
    "inventory_status",
    "last_verified_at",
    "raw_source_reference",
)

_HOLDING_NAMESPACE = uuid.UUID("5c29019d-3d20-42f4-bdad-a48842783d79")
_HOLDING_IDENTITY_FIELDS = (
    "item_type",
    "title",
    "creators",
    "first_name",
    "last_name",
    "ean_isbn13",
    "upc_isbn10",
    "description",
    "publisher",
    "publish_date",
)


class LibibInventoryError(ValueError):
    """Raised when an import or durable repository cannot be accepted safely."""


class LibibRepositoryError(LibibInventoryError):
    """Raised when durable inventory CSV state is malformed or incompatible."""


@dataclass(frozen=True)
class InventoryDiagnostic:
    code: str
    message: str
    registered_collection: str = ""
    observed_collection: str = ""
    folder_path: str = ""
    recommendation: str = ""
    holding_id: str = ""
    source_row_fingerprint: str = ""


@dataclass(frozen=True)
class LibibInventoryImportResult:
    status: str
    inventory_import_id: str | None
    source_file_hash: str
    folder_id: str | None
    holdings_created: int
    diagnostics: tuple[InventoryDiagnostic, ...] = ()

    @property
    def accepted(self) -> bool:
        return self.status in {"imported", "duplicate"}


class VersionedCsvRepository:
    """Strict, versioned CSV repository with atomic single-file replacement."""

    fieldnames: tuple[str, ...] = ()

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self) -> list[dict[str, str]]:
        if not self.path.exists():
            return []
        try:
            with self.path.open(newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                if tuple(reader.fieldnames or ()) != self.fieldnames:
                    raise LibibRepositoryError(
                        f"Unsupported or malformed repository header: {self.path}"
                    )
                rows = [dict(row) for row in reader]
        except UnicodeDecodeError as exc:
            raise LibibRepositoryError(f"Repository must be UTF-8: {self.path}") from exc
        except csv.Error as exc:
            raise LibibRepositoryError(f"Malformed CSV repository: {self.path}") from exc
        for row_number, row in enumerate(rows, start=2):
            if None in row or any(value is None for value in row.values()):
                raise LibibRepositoryError(
                    f"Malformed repository row {row_number}: {self.path}"
                )
            if row["schema_version"] != REPOSITORY_SCHEMA_VERSION:
                raise LibibRepositoryError(
                    f"Unsupported repository schema version {row['schema_version']!r}: {self.path}"
                )
        self.validate(rows)
        return rows

    def validate(self, rows: list[dict[str, str]]) -> None:
        """Validate repository-specific invariants before rows are accepted."""

    def rendered_bytes(self, rows: list[dict[str, str]]) -> bytes:
        self.validate(rows)
        with tempfile.SpooledTemporaryFile(mode="w+", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=self.fieldnames, lineterminator="\n")
            writer.writeheader()
            writer.writerows({field: row.get(field, "") for field in self.fieldnames} for row in rows)
            handle.seek(0)
            return handle.read().encode("utf-8")


class InventoryImportRepository(VersionedCsvRepository):
    fieldnames = INVENTORY_IMPORT_FIELDNAMES

    def validate(self, rows: list[dict[str, str]]) -> None:
        _require_unique(rows, "inventory_import_id", self.path)
        _require_unique(rows, "source_file_hash", self.path)
        for row in rows:
            if not row["inventory_import_id"] or not _is_sha256(row["source_file_hash"]):
                raise LibibRepositoryError(f"Invalid import identity in {self.path}")
            if not row["audit_scope"].strip():
                raise LibibRepositoryError(f"Blank audit_scope in {self.path}")
            if row["audit_completeness"] not in AUDIT_COMPLETENESS_VALUES:
                raise LibibRepositoryError(f"Invalid audit_completeness in {self.path}")
            try:
                count = int(row["row_count"])
            except ValueError as exc:
                raise LibibRepositoryError(f"Invalid row_count in {self.path}") from exc
            if count < 0:
                raise LibibRepositoryError(f"Invalid row_count in {self.path}")


class InventoryImportFolderRepository(VersionedCsvRepository):
    fieldnames = INVENTORY_IMPORT_FOLDER_FIELDNAMES

    def validate(self, rows: list[dict[str, str]]) -> None:
        _require_unique(rows, "folder_id", self.path)
        _require_unique(rows, "folder_path", self.path)
        for row in rows:
            if not row["folder_id"] or not row["folder_path"] or not row["expected_collection_label"]:
                raise LibibRepositoryError(f"Incomplete folder registration in {self.path}")


class InventoryHoldingRepository(VersionedCsvRepository):
    fieldnames = INVENTORY_HOLDING_FIELDNAMES

    def validate(self, rows: list[dict[str, str]]) -> None:
        _require_unique(rows, "holding_id", self.path)
        for row in rows:
            if not row["holding_id"] or not _is_sha256(row["source_row_fingerprint"]):
                raise LibibRepositoryError(f"Invalid holding identity in {self.path}")
            try:
                copies = int(row["copies"])
            except ValueError as exc:
                raise LibibRepositoryError(f"Invalid copies in {self.path}") from exc
            if copies < 1:
                raise LibibRepositoryError(f"Invalid copies in {self.path}")


def import_libib_inventory(
    source: str | Path,
    *,
    data_dir: str | Path,
    libib_input_dir: str | Path | None = None,
    audit_scope: str = "unknown",
    audit_completeness: str = "unknown",
    now: Callable[[], datetime] | None = None,
) -> LibibInventoryImportResult:
    """Import one explicit CSV or one explicitly selected audit-area directory.

    Directory selection is deliberately non-recursive.  Files outside
    ``libib_input_dir`` remain valid explicit inputs but receive no operational
    folder registration, so cross-export holding reconciliation is deferred.
    """

    audit_scope = _normalize_audit_scope(audit_scope)
    _validate_audit_completeness(audit_completeness)
    source_file = resolve_libib_import_source(source)
    source_hash = _file_sha256(source_file)
    paths = inventory_repository_paths(data_dir)
    import_repository = InventoryImportRepository(paths["imports"])
    folder_repository = InventoryImportFolderRepository(paths["folders"])
    holding_repository = InventoryHoldingRepository(paths["holdings"])

    imports = import_repository.load()
    folders = folder_repository.load()
    holdings = holding_repository.load()
    duplicate = next((row for row in imports if row["source_file_hash"] == source_hash), None)
    if duplicate is not None:
        return LibibInventoryImportResult(
            status="duplicate",
            inventory_import_id=duplicate["inventory_import_id"],
            source_file_hash=source_hash,
            folder_id=duplicate["folder_id"] or None,
            holdings_created=0,
        )

    parsed = parse_libib_csv(source_file)
    collection_label = _single_collection_label(parsed.records)
    _validate_holding_evidence(parsed.records)
    folder_path = _operational_folder_path(source_file.parent, libib_input_dir)
    folder = next((row for row in folders if row["folder_path"] == folder_path), None)
    if folder is not None and folder["expected_collection_label"] != collection_label:
        return LibibInventoryImportResult(
            status="review_required",
            inventory_import_id=None,
            source_file_hash=source_hash,
            folder_id=folder["folder_id"],
            holdings_created=0,
            diagnostics=(
                InventoryDiagnostic(
                    code="collection_label_changed_or_misfiled",
                    message="Observed Libib collection differs from the registered audit-area label",
                    registered_collection=folder["expected_collection_label"],
                    observed_collection=collection_label,
                    folder_path=folder_path,
                    recommendation=(
                        "Confirm whether the Libib collection was intentionally renamed or the export "
                        "was saved in the wrong audit-area folder; do not create a location automatically."
                    ),
                ),
            ),
        )

    imported_at = _iso_timestamp((now or _utc_now)())
    if folder_path and folder is None:
        folder = {
            "schema_version": REPOSITORY_SCHEMA_VERSION,
            "folder_id": f"LBF-{uuid.uuid4()}",
            "folder_path": folder_path,
            "expected_collection_label": collection_label,
            "first_imported_at": imported_at,
            "last_imported_at": imported_at,
            "notes": "",
        }
        folders.append(folder)
    elif folder is not None:
        folder = dict(folder)
        folder["last_imported_at"] = imported_at
        folders = [folder if row["folder_id"] == folder["folder_id"] else row for row in folders]

    inventory_import_id = f"LBI-{uuid.uuid4()}"
    folder_id = folder["folder_id"] if folder else ""
    identity_scope = folder_id or inventory_import_id
    unresolved = _changed_row_diagnostics(
        parsed.records,
        holdings=holdings,
        imports=imports,
        identity_scope=identity_scope,
        folder_id=folder_id,
        folder_path=folder_path,
    )
    if unresolved:
        return LibibInventoryImportResult(
            status="review_required",
            inventory_import_id=None,
            source_file_hash=source_hash,
            folder_id=folder_id or None,
            holdings_created=0,
            diagnostics=tuple(unresolved),
        )
    import_row = {
        "schema_version": REPOSITORY_SCHEMA_VERSION,
        "inventory_import_id": inventory_import_id,
        "source_file_name": source_file.name,
        "source_file_hash": source_hash,
        "source_collection_label": collection_label,
        "folder_id": folder_id,
        "folder_path": folder_path,
        "audit_scope": audit_scope,
        "audit_completeness": audit_completeness,
        "imported_at": imported_at,
        "parser_version": PARSER_VERSION,
        "row_count": str(len(parsed.records)),
    }
    imports.append(import_row)

    new_holdings = _build_holdings(
        parsed.records,
        inventory_import_id=inventory_import_id,
        source_file_hash=source_hash,
        collection_label=collection_label,
        identity_scope=identity_scope,
        imported_at=imported_at,
    )
    existing_ids = {row["holding_id"] for row in holdings}
    holdings.extend(row for row in new_holdings if row["holding_id"] not in existing_ids)
    _validate_repository_set(imports, folders, holdings)
    _publish_repository_set(
        ((import_repository, imports), (folder_repository, folders), (holding_repository, holdings))
    )
    return LibibInventoryImportResult(
        status="imported",
        inventory_import_id=inventory_import_id,
        source_file_hash=source_hash,
        folder_id=folder_id or None,
        holdings_created=sum(row["holding_id"] not in existing_ids for row in new_holdings),
    )


def resolve_libib_import_source(source: str | Path) -> Path:
    """Resolve one file or the single direct CSV in an audit-area directory."""

    path = Path(source)
    if path.is_file():
        return path
    if not path.is_dir():
        raise LibibInventoryError(f"Libib input does not exist: {path}")
    candidates = sorted(candidate for candidate in path.iterdir() if candidate.is_file() and candidate.suffix.lower() == ".csv")
    if len(candidates) != 1:
        raise LibibInventoryError(
            f"Audit-area directory must contain exactly one direct CSV; found {len(candidates)}: {path}"
        )
    return candidates[0]


def inventory_repository_paths(data_dir: str | Path) -> dict[str, Path]:
    root = Path(data_dir)
    return {
        "imports": root / "inventory_imports.csv",
        "folders": root / "inventory_import_folders.csv",
        "holdings": root / "inventory_holdings.csv",
    }


def source_row_fingerprint(record: LibibSourceRecord) -> str:
    """Hash identity-bearing row evidence without operational or quantity fields."""

    evidence = {key: record.raw_values.get(key, "") for key in _HOLDING_IDENTITY_FIELDS}
    canonical = json.dumps(evidence, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _build_holdings(
    records: Iterable[LibibSourceRecord],
    *,
    inventory_import_id: str,
    source_file_hash: str,
    collection_label: str,
    identity_scope: str,
    imported_at: str,
) -> list[dict[str, str]]:
    fingerprints = [source_row_fingerprint(record) for record in records]
    if len(fingerprints) != len(set(fingerprints)):
        raise LibibInventoryError(
            "Libib export contains indistinguishable duplicate rows; stable copy identity requires review"
        )
    rows = []
    for record, fingerprint in zip(records, fingerprints, strict=True):
        holding_uuid = uuid.uuid5(_HOLDING_NAMESPACE, f"{identity_scope}:{fingerprint}")
        rows.append(
            {
                "schema_version": REPOSITORY_SCHEMA_VERSION,
                "holding_id": f"HLD-{holding_uuid}",
                "catalog_item_id": "",
                "inventory_import_id": inventory_import_id,
                "source_collection_label": collection_label,
                "source_row_fingerprint": fingerprint,
                "source_title_key": _title_key(record),
                "source_creator_key": _creator_key(record),
                "source_isbn_key": _isbn_key(record),
                "current_location_id": "",
                "copies": str(record.normalized_copies),
                "inventory_status": "verified_present",
                "last_verified_at": imported_at,
                "raw_source_reference": f"sha256:{source_file_hash}#fingerprint:{fingerprint}",
            }
        )
    return rows


def _single_collection_label(records: Iterable[LibibSourceRecord]) -> str:
    labels = {record.raw_collection for record in records if record.raw_collection.strip()}
    if len(labels) != 1:
        raise LibibInventoryError(
            "A durable audit-area import requires exactly one non-empty Libib collection label"
        )
    return next(iter(labels))


def _validate_holding_evidence(records: Iterable[LibibSourceRecord]) -> None:
    invalid_rows = [str(record.source_row_number) for record in records if record.normalized_copies is None]
    if invalid_rows:
        raise LibibInventoryError(
            "Cannot create holdings where copies is missing, unknown, or invalid; rows: "
            + ", ".join(invalid_rows)
        )


def _operational_folder_path(parent: Path, libib_input_dir: str | Path | None) -> str:
    if libib_input_dir is None:
        return ""
    root = Path(libib_input_dir).resolve()
    try:
        relative = parent.resolve().relative_to(root)
    except ValueError:
        return ""
    if relative == Path("."):
        return ""
    return relative.as_posix()


def _validate_repository_set(
    imports: list[dict[str, str]],
    folders: list[dict[str, str]],
    holdings: list[dict[str, str]],
) -> None:
    import_ids = {row["inventory_import_id"] for row in imports}
    folder_ids = {row["folder_id"] for row in folders}
    for row in imports:
        if row["folder_id"] and row["folder_id"] not in folder_ids:
            raise LibibRepositoryError("Inventory import references an unknown folder_id")
    for row in holdings:
        if row["inventory_import_id"] not in import_ids:
            raise LibibRepositoryError("Inventory holding references an unknown inventory_import_id")


def _changed_row_diagnostics(
    records: Iterable[LibibSourceRecord],
    *,
    holdings: list[dict[str, str]],
    imports: list[dict[str, str]],
    identity_scope: str,
    folder_id: str,
    folder_path: str,
) -> list[InventoryDiagnostic]:
    """Find plausible changed observations without claiming they are the same copy."""

    if not folder_id:
        return []
    import_folder = {row["inventory_import_id"]: row["folder_id"] for row in imports}
    prior = [
        row for row in holdings if import_folder.get(row["inventory_import_id"]) == folder_id
    ]
    existing_ids = {row["holding_id"] for row in holdings}
    diagnostics = []
    for record in records:
        fingerprint = source_row_fingerprint(record)
        proposed_uuid = uuid.uuid5(_HOLDING_NAMESPACE, f"{identity_scope}:{fingerprint}")
        proposed_id = f"HLD-{proposed_uuid}"
        if proposed_id in existing_ids:
            continue
        title_key = _title_key(record)
        creator_key = _creator_key(record)
        isbn_key = _isbn_key(record)
        candidate = next(
            (
                row
                for row in prior
                if (isbn_key and isbn_key == row["source_isbn_key"])
                or (
                    title_key
                    and creator_key
                    and title_key == row["source_title_key"]
                    and creator_key == row["source_creator_key"]
                )
            ),
            None,
        )
        if candidate is not None:
            diagnostics.append(
                InventoryDiagnostic(
                    code="holding_identity_changed_requires_reconciliation",
                    message=(
                        "A changed Libib row plausibly represents an existing holding; "
                        "PR3 will not append or replace a holding automatically"
                    ),
                    folder_path=folder_path,
                    recommendation=(
                        "Review the changed title, creator, or ISBN in PR4 reconciliation; "
                        "preserve the existing holding until identity is confirmed."
                    ),
                    holding_id=candidate["holding_id"],
                    source_row_fingerprint=fingerprint,
                )
            )
    return diagnostics


def _title_key(record: LibibSourceRecord) -> str:
    return _normalized_key(record.raw_values.get("title", ""))


def _creator_key(record: LibibSourceRecord) -> str:
    return _normalized_key(
        record.normalized_creators or record.primary_author_display or ""
    )


def _isbn_key(record: LibibSourceRecord) -> str:
    return record.normalized_isbn13 or record.normalized_isbn10 or ""


def _normalized_key(value: str) -> str:
    return " ".join(value.casefold().split())


def _publish_repository_set(
    repository_rows: Iterable[tuple[VersionedCsvRepository, list[dict[str, str]]]],
) -> None:
    """Stage all CSVs, then replace them with rollback on in-process failure."""

    prepared = [(repository, repository.rendered_bytes(rows)) for repository, rows in repository_rows]
    originals = {repository.path: repository.path.read_bytes() if repository.path.exists() else None for repository, _ in prepared}
    temp_paths: dict[Path, Path] = {}
    replaced: list[Path] = []
    try:
        for repository, content in prepared:
            repository.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=repository.path.parent, delete=False) as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
                temp_paths[repository.path] = Path(handle.name)
        for repository, _ in prepared:
            os.replace(temp_paths.pop(repository.path), repository.path)
            replaced.append(repository.path)
    except Exception:
        for path in reversed(replaced):
            original = originals[path]
            if original is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(original)
        raise
    finally:
        for path in temp_paths.values():
            path.unlink(missing_ok=True)


def _require_unique(rows: list[dict[str, str]], field: str, path: Path) -> None:
    values = [row[field] for row in rows]
    if len(values) != len(set(values)):
        raise LibibRepositoryError(f"Duplicate {field} in {path}")


def _normalize_audit_scope(value: str) -> str:
    normalized = " ".join(value.split())
    if not normalized:
        raise LibibInventoryError("audit_scope must be a nonblank descriptive value")
    return normalized


def _validate_audit_completeness(value: str) -> None:
    if value not in AUDIT_COMPLETENESS_VALUES:
        raise LibibInventoryError(
            "audit_completeness must be one of: "
            + ", ".join(sorted(AUDIT_COMPLETENESS_VALUES))
        )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise LibibInventoryError("Import timestamp must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
