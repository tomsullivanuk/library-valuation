"""Import an explicitly approved complete Libib snapshot, preserving prior history.

Libib source IDs corroborate unchanged row evidence across two explicit manifests.
They identify source entries, never individually invented physical copies.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import shutil
import tempfile
import uuid
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from valuation.completed_inventory import (
    SCOPE_FILE, declaration_from_manifest, publish_files, resolve_completed_inventory,
)
from valuation.libib import parse_libib_csv
from valuation import libib_inventory as inventory
from valuation.libib_catalog import reconcile_inventory_catalog, StrictCatalogRepository
from valuation.inventory_audit import write_inventory_audit_artifacts, resolve_current_decisions
from valuation.steward_presentation import build_steward_presentation, DerivedEvidenceInput, RegisteredReport
from valuation.steward_workspace import render_steward_workspace

_NAMESPACE = uuid.UUID('9c542a97-5ed3-49b4-a5ab-24a2cdc3b3fe')


def read_manifest(path, root):
    """Verify every source, count, label and source-entry ID before mutation."""
    declaration = declaration_from_manifest(path, root)
    with Path(path).open(encoding='utf-8-sig', newline='') as handle:
        manifest = list(csv.DictReader(handle))
    records = []
    ids = set()
    for row in manifest:
        source = next(p for p in Path(root).glob('*/'+row['file'])
                      if hashlib.sha256(p.read_bytes()).hexdigest() == row['sha256'])
        parsed = parse_libib_csv(source)
        if (len(parsed.records) != int(row['rows'])
                or sum(r.normalized_copies or 0 for r in parsed.records) != int(row['copies'])):
            raise ValueError('Manifest totals do not match source: '+row['collection'])
        for record in parsed.records:
            source_id = record.raw_values.get('id', '').strip()
            if not source_id or source_id in ids:
                raise ValueError('Snapshot requires unique nonblank Libib source entry IDs')
            if record.raw_collection != row['collection'] or not record.normalized_copies:
                raise ValueError('Source collection or quantity conflicts with manifest')
            ids.add(source_id)
            records.append((source_id, row['sha256'], record))
        row['path'] = source
    return manifest, declaration, records


def _csv_bytes(fields, rows):
    handle = io.StringIO(newline='')
    writer = csv.DictWriter(handle, fieldnames=fields, lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return handle.getvalue().encode('utf-8')


def refresh_snapshot(manifest, previous_manifest, *, libib_input_dir, data_dir,
                     output_dir, market_evidence_summary=None, publish=False,
                     imported_at=None):
    """Stage all imports, reconcile once, validate and publish the complete set."""
    data_dir, output_dir = Path(data_dir), Path(output_dir)
    root = Path(libib_input_dir)
    sources, declaration, records = read_manifest(manifest, root)
    _, _, prior_records = read_manifest(previous_manifest, root)
    prior_by_id = {sid: (digest, row) for sid, digest, row in prior_records}
    source_by_ref = {
        f'sha256:{digest}#row:{row.source_row_number}': sid
        for sid, digest, row in prior_records
    }
    # No dates are inferred from book acquisition or Libib's "added" field.
    stamp = imported_at or datetime.now(timezone.utc)
    original = {p.name: p.read_bytes() for p in data_dir.iterdir() if p.is_file()}
    old_holdings = inventory.InventoryHoldingRepository(data_dir/'inventory_holdings.csv').load()
    prior_holding_by_id = {}
    for holding in old_holdings:
        sid = source_by_ref.get(holding['raw_source_reference'])
        if sid:
            if sid in prior_holding_by_id:
                raise ValueError('Prior source entry maps to multiple holdings')
            prior_holding_by_id[sid] = holding
    seed = json.dumps(declaration, sort_keys=True)
    counter = 0
    def id_factory():
        nonlocal counter
        counter += 1
        return uuid.uuid5(_NAMESPACE, f'{seed}:{counter}')
    with tempfile.TemporaryDirectory(prefix='libib-snapshot-') as temporary:
        work = Path(temporary)/'data'
        shutil.copytree(data_dir, work)
        artifacts = Path(temporary)/'output'
        imports = []
        for source in sources:
            if int(source['rows']) == 0:
                continue  # Empty exports are preserved explicitly in the declaration.
            result = inventory.import_libib_inventory(
                source['path'], data_dir=work, libib_input_dir=root,
                audit_scope=source['collection'], audit_completeness='complete_scope',
                now=lambda: stamp, id_factory=id_factory)
            if not result.accepted:
                raise ValueError('Snapshot import requires review: '+source['collection'])
            imports.append(asdict(result))
        paths = inventory.inventory_repository_paths(work)
        repos = inventory._repositories(paths)
        observations = repos['observations'].load()
        decisions = repos['decisions'].load()
        holdings = repos['holdings'].load()
        current = resolve_current_decisions(decisions,
            id_field='inventory_reconciliation_decision_id', entity_field='inventory_observation_id')
        by_ref = {o['source_reference']: o for o in observations}
        by_holding = {h['holding_id']: h for h in holdings}
        timestamp = inventory._iso_timestamp(stamp)
        corroborated = new_groups = 0
        used = set()
        for sid, digest, record in records:
            observation = by_ref[f'sha256:{digest}#row:{record.source_row_number}']
            decision = current[observation['inventory_observation_id']]
            if decision['outcome'] in inventory.ACCEPTED_RECONCILIATION_OUTCOMES:
                used.add(decision['holding_id'])
                continue
            prior = prior_holding_by_id.get(sid)
            target = None
            if prior:
                prior_record = prior_by_id[sid][1]
                if (inventory.source_row_fingerprint(prior_record) == observation['source_row_fingerprint']
                        and prior['source_row_fingerprint'] == observation['source_row_fingerprint']
                        and int(prior['copies']) == record.normalized_copies):
                    target = by_holding[prior['holding_id']]
                    corroborated += 1
            elif sid not in prior_by_id:
                # Distinct declared source entries must not collapse merely by ISBN.
                if (not inventory._has_identity_conflict(observation)
                        and inventory._sufficient_new_holding_evidence(observation)):
                    hid = 'HLD-'+str(uuid.uuid5(_NAMESPACE, 'libib-source-entry:'+sid))
                    if hid in by_holding:
                        raise ValueError('New source-entry holding identity collision')
                    import_row = next(r for r in repos['imports'].load()
                                      if r['inventory_import_id'] == observation['inventory_import_id'])
                    target = inventory._new_holding_row(observation, holding_id=hid,
                        folder_id=import_row['folder_id'], decision_id='', decision_timestamp=timestamp)
                    target['copies'] = str(record.normalized_copies)
                    target['holding_state_type'] = 'quantity_group' if record.normalized_copies > 1 else 'physical_copy'
                    holdings.append(target)
                    by_holding[hid] = target
                    new_groups += int(record.normalized_copies > 1)
            if target is None:
                continue
            if target['holding_id'] in used:
                raise ValueError('Multiple current source entries would share one holding')
            used.add(target['holding_id'])
            outcome = 'quantity_group_confirmed' if int(target['copies']) > 1 else (
                'existing_holding_confirmed' if prior else 'new_holding_created')
            replacement = inventory._decision_row(observation, outcome=outcome,
                basis='verified_source_id_and_unchanged_fingerprint' if prior else 'distinct_complete_snapshot_source_entry',
                confidence='high', timestamp=timestamp, holding_id=target['holding_id'],
                supersedes=decision['inventory_reconciliation_decision_id'],
                reason_codes=('explicit_complete_snapshot', 'unchanged_prior_evidence' if prior else 'distinct_source_entry'),
                explanation=('Source entry ID, unchanged bibliographic fingerprint and exact quantity corroborate the prior holding; source collection labels may change.'
                    if prior else 'A distinct source entry in the declared complete inventory supports this holding. Exact quantities are retained as one group; no individual copy identities are invented.'))
            decisions.append(replacement)
            updated = inventory._apply_observation_to_holding(target, observation,
                decision_id=replacement['inventory_reconciliation_decision_id'], decision_timestamp=timestamp)
            target.update(updated)
        inventory._validate_repository_set(repos['imports'].load(), repos['folders'].load(),
            observations, decisions, holdings)
        inventory._validate_current_terminal_decisions(observations, decisions)
        inventory._publish_repository_set(((repos['decisions'], decisions),(repos['holdings'], holdings)))
        scope = resolve_completed_inventory(work, declaration)
        catalog_result = reconcile_inventory_catalog(data_dir=work, holding_ids=scope.holding_ids,
            now=lambda: stamp, id_factory=id_factory)
        (work/SCOPE_FILE).write_text(json.dumps(declaration, indent=2, sort_keys=True)+'\n')
        scope = resolve_completed_inventory(work)
        market_path = Path(market_evidence_summary) if market_evidence_summary else None
        if market_path:
            from valuation.inventory_workflow import _validate_market_evidence_applicability
            _validate_market_evidence_applicability(market_path, work/'catalog_items.csv')
        write_inventory_audit_artifacts(data_dir=work, output_dir=artifacts)
        catalog_hash = hashlib.sha256((work/'catalog_items.csv').read_bytes()).hexdigest()
        reports = [RegisteredReport('inventory_review_workbook','Inventory Review Workbook',
            'Review inventory evidence, catalog matches and unresolved questions','Steward','xlsx',
            artifacts/'inventory_review_workbook.xlsx','inventory_review_workbook.xlsx',
            'completed-libib-snapshot',catalog_snapshot_sha256=catalog_hash,
            limitations='Includes historical review evidence; current snapshot entries are listed separately in the Library.')]
        model = build_steward_presentation(data_dir=work, reports=reports,
            market_evidence=DerivedEvidenceInput(market_path,identity_validated=True) if market_path else None)
        (artifacts/'steward_workspace.html').write_bytes(render_steward_workspace(model))
        active = set(scope.catalog_item_ids)
        holdings = repos['holdings'].load()
        active_holdings = [h for h in holdings if h['holding_id'] in scope.holding_ids]
        linked_obs = {h['latest_inventory_observation_id'] for h in active_holdings}
        summary = dict(collections=len(sources),empty_collections=len(declaration.get('empty_collections',[])),
            source_entries=scope.source_entries,source_copies=scope.source_copies,
            accepted_holding_entries=len(active_holdings),accepted_copies=sum(int(h['copies']) for h in active_holdings),
            linked_inventory_entries=sum(bool(h['catalog_item_id']) for h in active_holdings),
            active_catalog_books=len(active),catalog_match_reviews=sum(not h['catalog_item_id'] for h in active_holdings),
            physical_identity_reviews=len(records)-len(linked_obs),
            historical_catalog_books=len(model.books)-len(active),
            preserved_existing_holding_ids=len(set(h['holding_id'] for h in old_holdings)&set(by_holding)),
            cross_export_continuities_corroborated=corroborated,new_quantity_groups=new_groups,
            catalog_result=asdict(catalog_result),published=publish)
        pending = []
        for o in model.observations:
            if o.inventory_observation_id in scope.unresolved_observation_ids:
                pending.append(dict(collection=o.source_collection_label,title=o.title,creators=o.creators,
                    isbn13=o.normalized_isbn13,isbn10=o.normalized_isbn10,copies=o.observed_copies,
                    inventory_observation_id=o.inventory_observation_id))
        (artifacts/'current_inventory_identification_review.csv').write_bytes(_csv_bytes(
            ['collection','title','creators','isbn13','isbn10','copies','inventory_observation_id'],pending))
        historical = [dict(catalog_item_id=b.catalog_item_id,title=b.title,author=b.author,
            isbn13=b.isbn13,acquisition_count=len(b.acquisition_ids),status='Outside completed inventory; purchase history preserved')
            for b in model.books if b.catalog_item_id not in active]
        (artifacts/'historical_catalog.csv').write_bytes(_csv_bytes(
            ['catalog_item_id','title','author','isbn13','acquisition_count','status'],historical))
        (artifacts/'completed_inventory_reconciliation.json').write_text(json.dumps(summary,indent=2,sort_keys=True)+'\n')
        # Original immutable rows and all purchase/review repositories are preserved.
        for name in ['acquisitions.csv','collector_reviews.csv','research_priority_assessments.csv']:
            if name in original and (work/name).read_bytes()!=original[name]:
                raise ValueError('Protected history changed: '+name)
        if any((data_dir/name).read_bytes()!=content for name,content in original.items()):
            raise ValueError('Durable state changed while snapshot was being prepared')
        output_dir.mkdir(parents=True,exist_ok=True)
        payloads = [(output_dir/p.name,p.read_bytes()) for p in artifacts.iterdir()]
        if publish:
            payloads.extend((data_dir/p.name,p.read_bytes()) for p in work.iterdir()
                            if p.is_file() and p.read_bytes()!=original.get(p.name))
        publish_files(payloads)
        return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=Path,required=True)
    parser.add_argument('--previous-manifest',type=Path,required=True)
    parser.add_argument('--libib-input-dir',type=Path,default=Path('input/libib'))
    parser.add_argument('--data-dir',type=Path,default=Path('data'))
    parser.add_argument('--output-dir',type=Path,default=Path('output'))
    parser.add_argument('--market-evidence-summary',type=Path)
    parser.add_argument('--publish',action='store_true')
    args=parser.parse_args()
    print(json.dumps(refresh_snapshot(**vars(args)),indent=2,sort_keys=True))


if __name__=='__main__':main()
