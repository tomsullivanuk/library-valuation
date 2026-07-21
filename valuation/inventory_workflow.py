"""Safe end-to-end orchestration for one approved Libib audit export."""

from __future__ import annotations

import csv
import os
import shutil
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Mapping

from valuation.inventory_audit import write_inventory_audit_artifacts
from valuation.libib import parse_libib_csv
from valuation.libib_catalog import (
    catalog_reconciliation_repository_path,
    reconcile_inventory_catalog,
)
from valuation.libib_inventory import (
    import_libib_inventory,
    inventory_repository_paths,
    resolve_libib_import_source,
)
from valuation.repositories import ACQUISITION_FIELDNAMES


class InventoryWorkflowError(ValueError):
    """Raised when an inventory workflow cannot complete without partial state."""


DURABLE_REPOSITORY_NAMES = (
    "catalog_items.csv",
    "inventory_imports.csv",
    "inventory_import_folders.csv",
    "inventory_observations.csv",
    "inventory_reconciliation_decisions.csv",
    "inventory_holdings.csv",
    "inventory_catalog_reconciliation_decisions.csv",
)
ARTIFACT_NAMES = ("inventory_audit_summary.csv", "inventory_review_workbook.xlsx")


@dataclass(frozen=True)
class InventoryWorkflowSummary:
    source_file: str
    source_file_hash: str
    inventory_import_id: str
    mode: str
    import_status: str
    source_rows: int
    parser_diagnostics: int
    observations_created: int
    observations_reused: int
    holdings_created: int
    holdings_confirmed: int
    physical_unresolved: int
    physical_rejected: int
    catalog_existing_links: int
    catalog_items_created: int
    catalog_unresolved: int
    acquisitions_created: int
    physical_review_items: int
    catalog_review_items: int
    location_review_items: int
    audit_coverage_items: int
    newly_discovered_items: int
    reconciled_holdings: int
    summary_csv: str
    review_workbook: str
    durable_state_changed: bool
    proposed_durable_changes: bool
    repeat: bool

    def as_dict(self) -> dict[str, str | int | bool]:
        return asdict(self)


def update_inventory(
    source: str | Path,
    *,
    libib_input_dir: str | Path,
    data_dir: str | Path,
    output_dir: str | Path,
    audit_scope: str = "unknown",
    audit_completeness: str = "unknown",
    publish: bool = False,
    now: Callable[[], datetime] | None = None,
) -> InventoryWorkflowSummary:
    """Run one Libib audit through existing PR2–PR8 components.

    Preview is the default. Publication is allowed only when ``publish=True``.
    """

    source_file = resolve_libib_import_source(source).resolve()
    libib_root = Path(libib_input_dir).resolve()
    data_dir = Path(data_dir).resolve()
    output_dir = Path(output_dir).resolve()
    _validate_destinations(source_file, libib_root, data_dir, output_dir)
    parsed = parse_libib_csv(source_file)

    durable_paths = [data_dir / name for name in DURABLE_REPOSITORY_NAMES]
    artifact_paths = [output_dir / name for name in ARTIFACT_NAMES]
    real_before = _snapshot([*durable_paths, *artifact_paths])

    with tempfile.TemporaryDirectory(prefix="library-inventory-workflow-") as temporary:
        temporary_root = Path(temporary)
        if publish:
            working_data = data_dir
        else:
            working_data = temporary_root / "data"
            _copy_repository_state(data_dir, working_data)
        staged_output = temporary_root / "output"
        working_before = _snapshot([working_data / name for name in DURABLE_REPOSITORY_NAMES])
        acquisition_count_before = _acquisition_count(working_data / "acquisitions.csv")

        try:
            import_result = import_libib_inventory(
                source_file,
                data_dir=working_data,
                libib_input_dir=libib_root,
                audit_scope=audit_scope,
                audit_completeness=audit_completeness,
                now=now,
            )
            if not import_result.accepted:
                detail = import_result.diagnostics[0].message if import_result.diagnostics else import_result.status
                raise InventoryWorkflowError(f"Libib import requires review: {detail}")
            catalog_result = reconcile_inventory_catalog(data_dir=working_data, now=now)
            presentation = write_inventory_audit_artifacts(
                data_dir=working_data,
                output_dir=staged_output,
            )
            acquisition_count_after = _acquisition_count(working_data / "acquisitions.csv")
            if acquisition_count_after != acquisition_count_before:
                raise InventoryWorkflowError("Libib inventory workflow must not create acquisitions")

            proposed = _changed(
                working_before,
                [working_data / name for name in DURABLE_REPOSITORY_NAMES],
            )
            _publish_artifacts(staged_output, output_dir)
        except Exception:
            if publish:
                _restore(real_before)
            raise

    physical_counts = dict(import_result.outcome_counts)
    catalog_counts = dict(catalog_result.outcome_counts)
    existing_links = sum(
        catalog_counts.get(outcome, 0)
        for outcome in ("existing_catalog_item_linked", "existing_catalog_item_confirmed", "catalog_link_unchanged")
    )
    accepted_physical = import_result.accepted_observation_count
    return InventoryWorkflowSummary(
        source_file=str(source_file),
        source_file_hash=import_result.source_file_hash,
        inventory_import_id=import_result.inventory_import_id or "",
        mode="publish" if publish else "preview",
        import_status=import_result.status,
        source_rows=len(parsed.records),
        parser_diagnostics=len(parsed.diagnostics),
        observations_created=import_result.observations_created,
        observations_reused=len(parsed.records) if import_result.status == "duplicate" else 0,
        holdings_created=import_result.holdings_created,
        holdings_confirmed=max(accepted_physical - import_result.holdings_created, 0),
        physical_unresolved=import_result.unresolved_observation_count,
        physical_rejected=import_result.rejected_observation_count,
        catalog_existing_links=existing_links,
        catalog_items_created=catalog_result.catalog_items_created,
        catalog_unresolved=catalog_result.unresolved_count,
        acquisitions_created=0,
        physical_review_items=len(presentation.physical_review),
        catalog_review_items=len(presentation.catalog_review),
        location_review_items=len(presentation.location_review),
        audit_coverage_items=len(presentation.audit_coverage),
        newly_discovered_items=len(presentation.newly_discovered),
        reconciled_holdings=len(presentation.reconciled_holdings),
        summary_csv=str(output_dir / ARTIFACT_NAMES[0]),
        review_workbook=str(output_dir / ARTIFACT_NAMES[1]),
        durable_state_changed=publish and proposed,
        proposed_durable_changes=proposed,
        repeat=import_result.status == "duplicate",
    )


def _validate_destinations(source: Path, libib_root: Path, data_dir: Path, output_dir: Path) -> None:
    if not libib_root.is_dir():
        raise InventoryWorkflowError(f"Libib input directory does not exist: {libib_root}")
    try:
        relative_parent = source.parent.relative_to(libib_root)
    except ValueError as exc:
        raise InventoryWorkflowError("Libib source must be inside the declared Libib input directory") from exc
    if relative_parent == Path("."):
        raise InventoryWorkflowError("Libib source must be inside an explicit audit-area folder")
    if not data_dir.is_dir():
        raise InventoryWorkflowError(f"Durable data directory does not exist: {data_dir}")
    if output_dir.name != "output":
        raise InventoryWorkflowError("Inventory review artifacts must use an output/ directory")
    if data_dir == output_dir or data_dir in output_dir.parents or output_dir in data_dir.parents:
        raise InventoryWorkflowError("Data and output directories must be separate")


def _copy_repository_state(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for path in source.iterdir():
        if path.is_file():
            shutil.copy2(path, destination / path.name)


def _snapshot(paths: list[Path]) -> dict[Path, bytes | None]:
    return {path: path.read_bytes() if path.exists() else None for path in paths}


def _changed(before: Mapping[Path, bytes | None], after_paths: list[Path]) -> bool:
    return any(before[path] != (path.read_bytes() if path.exists() else None) for path in after_paths)


def _restore(snapshot: Mapping[Path, bytes | None]) -> None:
    for path, content in snapshot.items():
        if content is None:
            path.unlink(missing_ok=True)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)


def _publish_artifacts(staged_output: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    snapshot = _snapshot([output_dir / name for name in ARTIFACT_NAMES])
    temporary_paths: list[Path] = []
    try:
        for name in ARTIFACT_NAMES:
            destination = output_dir / name
            with tempfile.NamedTemporaryFile(dir=output_dir, delete=False) as handle:
                handle.write((staged_output / name).read_bytes())
                handle.flush()
                os.fsync(handle.fileno())
                temporary_paths.append(Path(handle.name))
            os.replace(temporary_paths.pop(), destination)
    except Exception:
        _restore(snapshot)
        raise
    finally:
        for path in temporary_paths:
            path.unlink(missing_ok=True)


def _acquisition_count(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != ACQUISITION_FIELDNAMES:
            raise InventoryWorkflowError(f"Unsupported or malformed acquisition repository: {path}")
        return sum(1 for _ in reader)
