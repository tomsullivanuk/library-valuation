"""Explicit completed-inventory scope; never deletes history or asserts disposal."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

SCOPE_FILE = "completed_inventory.json"


@dataclass(frozen=True)
class CompletedInventoryScope:
    completed: bool = False
    source_entries: int = 0
    source_copies: int = 0
    catalog_item_ids: tuple[str, ...] = ()
    holding_ids: tuple[str, ...] = ()
    unresolved_observation_ids: tuple[str, ...] = ()


def _rows(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def resolve_completed_inventory(data_dir, declaration=None):
    """Validate the declared immutable imports and project their current links."""
    data_dir = Path(data_dir)
    if declaration is None:
        path = data_dir / SCOPE_FILE
        if not path.exists():
            return CompletedInventoryScope()
        declaration = json.loads(path.read_text())
    if (declaration.get("schema_version") != 1
            or declaration.get("assertion") != "completed_physical_inventory"):
        raise ValueError("Invalid completed-inventory declaration")
    sources = declaration.get("sources", [])
    if not sources or len({s['sha256'] for s in sources}) != len(sources):
        raise ValueError("Completed inventory needs distinct explicit source hashes")
    empty = declaration.get('empty_collections', [])
    labels = [r['collection'] for r in [*sources, *empty]]
    if len(set(labels)) != len(labels) or any(int(r['rows']) != 0 or int(r['copies']) != 0 for r in empty):
        raise ValueError('Invalid or overlapping completed-inventory collections')
    imports = _rows(data_dir / "inventory_imports.csv")
    observations = _rows(data_dir / "inventory_observations.csv")
    holdings = _rows(data_dir / "inventory_holdings.csv")
    current = []
    for source in sources:
        matches = [r for r in imports if r['source_file_hash'] == source['sha256']]
        if len(matches) != 1:
            raise ValueError("Completed inventory source must have exactly one durable import")
        imported = matches[0]
        selected = [r for r in observations if r['inventory_import_id'] == imported['inventory_import_id']]
        if (imported['source_collection_label'] != source['collection']
                or len(selected) != int(source['rows'])
                or sum(int(r['observed_copies']) for r in selected) != int(source['copies'])):
            raise ValueError("Completed inventory source counts or collection do not match durable evidence")
        current.extend(selected)
    observation_ids = {r['inventory_observation_id'] for r in current}
    active = [r for r in holdings if r['latest_inventory_observation_id'] in observation_ids
              and r['inventory_status'] == 'verified_present']
    linked_observations = {r['latest_inventory_observation_id'] for r in active if r['catalog_item_id']}
    return CompletedInventoryScope(
        completed=True,
        source_entries=len(current),
        source_copies=sum(int(r['observed_copies']) for r in current),
        catalog_item_ids=tuple(sorted({r['catalog_item_id'] for r in active if r['catalog_item_id']})),
        holding_ids=tuple(sorted(r['holding_id'] for r in active)),
        unresolved_observation_ids=tuple(sorted(observation_ids - linked_observations)),
    )


def declaration_from_manifest(manifest, libib_input_dir):
    """Check untouched exports against an explicitly approved source manifest."""
    manifest_rows = _rows(manifest)
    sources = []
    empty_collections = []
    for row in manifest_rows:
        if Path(row['file']).name != row['file'] or not row['file'].endswith('.csv'):
            raise ValueError('Manifest file must be a CSV basename')
        candidates = list(Path(libib_input_dir).glob('*/' + row['file']))
        matches = [p for p in candidates if hashlib.sha256(p.read_bytes()).hexdigest() == row['sha256']]
        if len(matches) != 1:
            raise ValueError("Manifest export is missing, ambiguous, or changed: " + row['file'])
        entry = {k: row[k] for k in ('collection', 'sha256', 'rows', 'copies')}
        if int(row['rows']) == 0:
            from valuation.libib import parse_libib_csv
            if int(row['copies']) != 0 or parse_libib_csv(matches[0]).records:
                raise ValueError('Empty collection declaration conflicts with source')
            empty_collections.append(entry)
        else:
            sources.append(entry)
    return {'schema_version': 1, 'assertion': 'completed_physical_inventory',
            'absence_policy': 'exclude_from_active_library_preserve_history',
            'sources': sorted(sources, key=lambda r: (r['collection'], r['sha256'])),
            'empty_collections': sorted(empty_collections, key=lambda r: r['collection'])}


def publish_files(payloads):
    """Atomically replace individual files and restore the full set on failure."""
    before = {path: path.read_bytes() if path.exists() else None for path, _ in payloads}
    staged = []
    try:
        for path, payload in payloads:
            with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
                staged.append((Path(handle.name), path))
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
        for temporary, path in staged:
            os.replace(temporary, path)
    except Exception:
        for path, content in before.items():
            if content is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(content)
        raise
    finally:
        for temporary, _ in staged:
            temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--libib-input-dir', type=Path, default=Path('input/libib'))
    parser.add_argument('--data-dir', type=Path, default=Path('data'))
    parser.add_argument('--output-dir', type=Path, default=Path('output'))
    parser.add_argument('--market-evidence-summary', type=Path)
    parser.add_argument('--inventory-report', help='Explicit relative workbook path under output-dir')
    parser.add_argument('--publish', action='store_true', help='Save the explicit completed-inventory declaration')
    args = parser.parse_args()
    from valuation.steward_presentation import build_steward_presentation, DerivedEvidenceInput, RegisteredReport
    from valuation.steward_workspace import render_steward_workspace
    declaration = declaration_from_manifest(args.manifest, args.libib_input_dir)
    scope = resolve_completed_inventory(args.data_dir, declaration)
    if args.market_evidence_summary:
        from valuation.inventory_workflow import _validate_market_evidence_applicability
        _validate_market_evidence_applicability(args.market_evidence_summary, args.data_dir / 'catalog_items.csv')
    reports = []
    # Explicit registrations only; no output-directory discovery.
    report_specs = [('inventory_review_workbook', 'Inventory Review Workbook', 'inventory_review_workbook.xlsx')]
    if args.inventory_report:
        report_specs.append(('completed_inventory_workbook', 'Completed Physical Inventory', args.inventory_report))
    for key, name, relative in report_specs:
        path = args.output_dir / relative
        if path.is_file():
            reports.append(RegisteredReport(key, name, 'Inspect inventory evidence and unresolved identities',
                'Steward', 'xlsx', path, relative, 'completed-inventory-reconciliation',
                limitations='Existing inventory report; may include historical review evidence. Asking prices are not realized sale values.'))
    model = build_steward_presentation(data_dir=args.data_dir,
        completed_inventory_declaration=declaration, reports=reports,
        market_evidence=DerivedEvidenceInput(args.market_evidence_summary, identity_validated=True)
        if args.market_evidence_summary else None)
    content = render_steward_workspace(model)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    # Stage all files, then replace together with rollback on publication failure.
    payloads = []
    if args.publish:
        payloads.append((args.data_dir / SCOPE_FILE, (json.dumps(declaration, indent=2, sort_keys=True)+'\n').encode()))
    payloads.extend([
        (args.output_dir / 'steward_workspace.html', content),
        (args.output_dir / 'completed_inventory_reconciliation.json', (json.dumps(asdict(scope), indent=2)+'\n').encode()),
    ])
    publish_files(payloads)
    print(json.dumps({'published': args.publish, 'source_entries': scope.source_entries,
        'source_copies': scope.source_copies, 'active_catalog_books': len(scope.catalog_item_ids),
        'inventory_entries_needing_identification': len(scope.unresolved_observation_ids),
        'historical_catalog_books': len(model.books)-len(scope.catalog_item_ids)}, indent=2))


if __name__ == '__main__':
    main()
