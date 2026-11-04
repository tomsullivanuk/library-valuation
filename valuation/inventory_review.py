"""Apply an explicitly reviewed per-entry plan with append-only decisions.

This is a review applier, not a replacement for conservative automatic matching.
Source-only catalog entries retain unknown identifiers and edition information.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import tempfile
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from valuation import libib_inventory as inventory
from valuation import libib_catalog as catalog_api
from valuation.completed_inventory import publish_files, resolve_completed_inventory
from valuation.inventory_audit import resolve_current_decisions, write_inventory_audit_artifacts
from valuation.libib import is_valid_isbn10, is_valid_isbn13, isbn10_to_isbn13
from valuation.libib_snapshot import _csv_bytes
from valuation.steward_presentation import build_steward_presentation, DerivedEvidenceInput, RegisteredReport
from valuation.steward_workspace import render_steward_workspace

_NAMESPACE = uuid.UUID('19c944c6-47cb-4d8a-9598-6649ef6d69a8')


def apply_reviewed_plan(plan_path, *, data_dir, output_dir,
                        market_evidence_summary=None, publish=False, reviewed_at=None, libib_input_dir='input/libib'):
    data_dir, output_dir = Path(data_dir), Path(output_dir)
    plan_bytes = Path(plan_path).read_bytes()
    plan = json.loads(plan_bytes)
    if plan.get('schema_version') != 1:
        raise ValueError('Unsupported review plan')
    before = {p.name:p.read_bytes() for p in data_dir.iterdir() if p.is_file()}
    for name, key in [('catalog_items.csv','catalog_sha256'),
                      ('inventory_holdings.csv','holdings_sha256'),
                      ('inventory_catalog_reconciliation_decisions.csv','catalog_decisions_sha256')]:
        if hashlib.sha256(before[name]).hexdigest() != plan[key]:
            raise ValueError('Review plan is stale: '+name)
    for name,digest in plan.get('repositories_sha256',{}).items():
        if name not in before or hashlib.sha256(before[name]).hexdigest()!=digest:
            raise ValueError('Review plan is stale: '+name)
    scope = resolve_completed_inventory(data_dir)
    entries = plan['reviewed_entries']
    ids = [r['observation_id'] for r in entries]
    if len(ids) != len(set(ids)) or set(ids) != set(scope.unresolved_observation_ids):
        raise ValueError('Review plan must cover each current unresolved entry exactly once')
    stamp = reviewed_at or datetime.now(timezone.utc)
    timestamp = inventory._iso_timestamp(stamp)
    receipt_id = hashlib.sha256(plan_bytes).hexdigest()
    with tempfile.TemporaryDirectory(prefix='library-inventory-review-') as temp:
        work = Path(temp)/'data'
        shutil.copytree(data_dir, work)
        artifacts = Path(temp)/'output'
        repos = inventory._repositories(inventory.inventory_repository_paths(work))
        observations = repos['observations'].load()
        observations_by_id = {o['inventory_observation_id']:o for o in observations}
        imports = repos['imports'].load()
        physical = repos['decisions'].load()
        holdings = repos['holdings'].load()
        by_holding = {h['holding_id']:h for h in holdings}
        current_physical = resolve_current_decisions(physical,
            id_field='inventory_reconciliation_decision_id', entity_field='inventory_observation_id')
        catalog_repo = catalog_api.StrictCatalogRepository(work/'catalog_items.csv')
        catalog = catalog_repo.load()
        old_catalog_count = len(catalog)
        by_catalog = {c['catalog_item_id']:c for c in catalog}
        catalog_decision_repo = catalog_api.InventoryCatalogReconciliationDecisionRepository(
            work/'inventory_catalog_reconciliation_decisions.csv')
        decisions = catalog_decision_repo.load()
        current_catalog = catalog_api._current_decisions(decisions)
        source_keys = {}
        log, questions, identifier_followup, followups = [], [], [], []
        source_cache = {}
        action_counts = Counter()
        for item in entries:
            oid = item['observation_id']
            observation = observations_by_id[oid]
            if (observation['source_row_fingerprint'] != item['source_fingerprint']
                    or observation['source_reference'] != item['source_reference']):
                raise ValueError('Reviewed source evidence changed: '+oid)
            proof = item.get('source_evidence')
            if proof:
                file_name = proof['file']
                if Path(file_name).name != file_name:
                    raise ValueError('Source proof must use an export basename')
                digest = observation['source_reference'].split(':',1)[1].split('#',1)[0]
                if file_name not in source_cache:
                    paths = [p for p in Path(libib_input_dir).glob('*/'+file_name)
                             if hashlib.sha256(p.read_bytes()).hexdigest()==digest]
                    if len(paths)!=1:
                        raise ValueError('Reviewed note evidence is missing or changed')
                    with paths[0].open(encoding='utf-8-sig',newline='') as handle:
                        source_cache[file_name]=list(csv.DictReader(handle))
                raw = source_cache[file_name][int(observation['source_row_number'])-2]
                if (raw.get('id','')!=proof['source_id']
                        or hashlib.sha256(raw.get('notes','').encode()).hexdigest()!=proof['notes_sha256']):
                    raise ValueError('Reviewed note evidence does not match the source')
            holding = by_holding.get(item['holding_id'])
            if holding and holding['latest_inventory_observation_id'] != oid:
                raise ValueError('Holding no longer refers to reviewed source')
            prior = current_catalog.get(item['holding_id'])
            if (prior['inventory_catalog_reconciliation_decision_id'] if prior else '') != item['supersedes_catalog_decision_id']:
                raise ValueError('Reviewed decision changed')
            action = item['action']
            if action not in {'link','physical_link','physical_create_source_only','create_isbn','create_source_only','needs_input'}:
                raise ValueError('Unsupported reviewed action')
            note = item['reason']
            urls = item.get('source_urls',[])
            if urls:
                if any(not u.startswith('https://') for u in urls):
                    raise ValueError('Evidence links must be HTTPS')
                note += ' Evidence: '+' ; '.join(urls)
            for followup in item.get('followup_questions',[]):
                if action=='needs_input' and followup['category']=='binding':
                    continue  # The specific binding question is already in the main checklist.
                followups.append(dict(category=followup['category'],priority=followup['priority'],
                    collection=item['collection'],title=item['title'],question=followup['question'],
                    bibliographic_evidence=followup.get('bibliographic_evidence',''),inventory_observation_id=oid))
                note += ' Follow-up ('+followup['category']+'): '+followup['question']
            physical_prior = current_physical[oid]
            if action in {'physical_link','physical_create_source_only'}:
                if holding or observation['observed_copies'] != '1' or (not urls and not proof):
                    raise ValueError('Physical override needs explicit single-entry corroboration')
                hid = 'HLD-'+str(uuid.uuid5(_NAMESPACE,oid))
                if hid in by_holding:
                    raise ValueError('Reviewed holding identity collision')
                import_row = next(r for r in imports if r['inventory_import_id']==observation['inventory_import_id'])
                replacement = inventory._decision_row(observation,
                    outcome='new_holding_created',basis=item['basis'],confidence='medium' if action=='physical_create_source_only' else 'high',
                    timestamp=timestamp,holding_id=hid,origin='manual',
                    supersedes=physical_prior['inventory_reconciliation_decision_id'],
                    reason_codes=('assisted_review','reviewed_source_notes' if action=='physical_create_source_only' else 'corroborated_source_identifier_conflict'), explanation=note)
                physical.append(replacement)
                holding = inventory._new_holding_row(observation,holding_id=hid,
                    folder_id=import_row['folder_id'],decision_id=replacement['inventory_reconciliation_decision_id'],
                    decision_timestamp=timestamp)
                holdings.append(holding)
                by_holding[hid] = holding
            elif action != 'needs_input':
                if not holding or not catalog_api._holding_has_accepted_physical_identity(holding,physical):
                    raise ValueError('Catalog review cannot bypass physical acceptance')
            cid = item.get('catalog_item_id','')
            if action == 'needs_input':
                question = item['question']
                note += ' Steward input needed: '+question
                questions.append(dict(collection=item['collection'],title=item['title'],
                    question=question,reason=item['reason'],inventory_observation_id=oid,
                    catalog_candidates='; '.join(item.get('candidate_ids',[]))))
                if not holding:
                    physical.append(inventory._decision_row(observation,
                        outcome='manual_review_required',basis='assisted_review_needs_steward_input',confidence='low',
                        timestamp=timestamp,origin='manual',
                        supersedes=physical_prior['inventory_reconciliation_decision_id'],
                        reason_codes=('steward_input_needed',),explanation=note))
                outcome = 'manual_catalog_review_required'
            else:
                if action in {'create_isbn','create_source_only','physical_create_source_only'} or (action=='physical_link' and not cid):
                    override = item.get('corrected_identifiers')
                    isbn13 = (override or {}).get('isbn13',observation['normalized_isbn13'])
                    isbn10 = (override or {}).get('isbn10',observation['normalized_isbn10'])
                    if action in {'create_source_only','physical_create_source_only'}:
                        isbn13 = isbn10 = ''
                        if not observation['raw_publisher'].strip() or (not observation['raw_creators'].strip() and action!='physical_create_source_only'):
                            raise ValueError('Source-only identity needs reviewed title/creator/publisher')
                    else:
                        if not (isbn13 and is_valid_isbn13(isbn13)):
                            raise ValueError('Reviewed ISBN identity needs valid ISBN-13')
                        if isbn10 and (not is_valid_isbn10(isbn10) or isbn10_to_isbn13(isbn10)!=isbn13):
                            raise ValueError('Reviewed identifier pair conflicts')
                    if override and not urls:
                        raise ValueError('Identifier correction needs cited evidence')
                    source_key = tuple(observation[k] for k in ['raw_title','raw_creators','raw_publisher'])
                    matches = [c for c in catalog if isbn13 and catalog_api._catalog_isbn13(c)==isbn13]
                    if len(matches)>1:
                        raise ValueError('Reviewed creation found multiple ISBN identities')
                    if matches and catalog_api._key(matches[0]['title'])!=catalog_api._key(observation['raw_title']):
                        raise ValueError('Reviewed ISBN creation found different title metadata')
                    cid = matches[0]['catalog_item_id'] if matches else source_keys.get(source_key,'') if not isbn13 else ''
                    if not cid:
                        cid = catalog_api._next_catalog_item_id(catalog)
                        record = dict(catalog_item_id=cid,isbn13=isbn13,isbn10=isbn10,
                            title=observation['raw_title'],author=observation['raw_creators'],
                            publisher=observation['raw_publisher'],publication_year='',
                            source_fingerprint=observation['source_row_fingerprint'],
                            match_confidence='high' if isbn13 and observation['raw_creators'] else 'medium')
                        catalog.append(record)
                        by_catalog[cid]=record
                        outcome='new_catalog_item_created'
                    else:
                        outcome='existing_catalog_item_linked'
                    if not isbn13:
                        source_keys[source_key]=cid
                        identifier_followup.append(dict(collection=item['collection'],title=item['title'],
                            catalog_item_id=cid,note='Catalogued from reviewed source metadata. ISBN and exact edition remain unknown; obtain identifiers before edition-specific pricing.'))
                else:
                    outcome='existing_catalog_item_linked'
                if cid not in by_catalog:
                    raise ValueError('Reviewed target is absent from catalog')
                holding['catalog_item_id']=cid
            if holding:
                decision = catalog_api._decision_row(holding_id=holding['holding_id'],observation_id=oid,
                    catalog_item_id=cid if action!='needs_input' else '',candidates=(cid,) if cid else (),
                    statuses=('active',) if cid else (),outcome=outcome,
                    basis=item.get('basis','assisted_review_needs_steward_input'),
                    confidence='low' if action=='needs_input' else 'medium' if action in {'create_source_only','physical_create_source_only'} or not observation['normalized_isbn13'] else 'high',
                    reason_codes=('assisted_review','steward_input_needed' if action=='needs_input' else 'identifier_unknown' if action in {'create_source_only','physical_create_source_only'} else action),
                    explanation=note,timestamp=timestamp,origin='manual',
                    supersedes=prior['inventory_catalog_reconciliation_decision_id'] if prior else '',
                    decision_id='ICD-'+str(uuid.uuid5(_NAMESPACE,receipt_id+':'+oid)))
                decisions.append(decision)
            action_counts[action]+=1
            log.append(dict(collection=item['collection'],title=item['title'],action=action,
                catalog_item_id=cid,inventory_observation_id=oid,reason=item['reason'],
                evidence_urls='; '.join(urls),question=item.get('question','')))
        inventory._validate_repository_set(imports,repos['folders'].load(),observations,physical,holdings)
        inventory._validate_current_terminal_decisions(observations,physical)
        catalog_api._validate_cross_repository_state(holdings,observations,physical,catalog,decisions)
        inventory._publish_repository_set(((repos['holdings'],holdings),(repos['decisions'],physical),
            (catalog_repo,catalog),(catalog_decision_repo,decisions)))
        after_scope = resolve_completed_inventory(work)
        expected_left = {i['observation_id'] for i in entries if i['action']=='needs_input'}
        if set(after_scope.unresolved_observation_ids)!=expected_left:
            raise ValueError('Review result does not balance to the remaining questions')
        market_path=Path(market_evidence_summary) if market_evidence_summary else None
        if market_path:
            from valuation.inventory_workflow import _validate_market_evidence_applicability
            _validate_market_evidence_applicability(market_path,work/'catalog_items.csv')
        write_inventory_audit_artifacts(data_dir=work,output_dir=artifacts)
        for name, rows in [('inventory_review_decisions.csv',log),('inventory_review_needs_input.csv',questions),
                           ('inventory_identifier_followup.csv',identifier_followup),('inventory_review_followups.csv',followups)]:
            if rows:
                (artifacts/name).write_bytes(_csv_bytes(list(rows[0]),rows))
        catalog_hash=hashlib.sha256((work/'catalog_items.csv').read_bytes()).hexdigest()
        reports=[]
        for key,name,fmt,purpose in [
            ('inventory_review_workbook','Inventory Review Workbook','xlsx','Review inventory and catalog evidence'),
            ('inventory_review_needs_input','Questions for the Steward','csv','Check the remaining book identities'),
            ('inventory_review_decisions','Completed Inventory Review','csv','Inspect the reasons and evidence for this review'),
            ('inventory_review_followups','Format and Location Checks','csv','Review optional binding and location confirmations'),
        ]:
            file=key+'.'+fmt
            if (artifacts/file).exists():
                reports.append(RegisteredReport(key,name,purpose,'Steward',fmt,artifacts/file,file,
                    'assisted-inventory-review',catalog_snapshot_sha256=catalog_hash,
                    limitations='Read-only review output. No acquisition history or source observations were edited.'))
        model=build_steward_presentation(data_dir=work,reports=reports,
            market_evidence=DerivedEvidenceInput(market_path,identity_validated=True) if market_path else None)
        (artifacts/'steward_workspace.html').write_bytes(render_steward_workspace(model))
        pending=[]
        for o in model.observations:
            if o.inventory_observation_id in expected_left:
                pending.append(dict(collection=o.source_collection_label,title=o.title,creators=o.creators,
                    isbn13=o.normalized_isbn13,isbn10=o.normalized_isbn10,copies=o.observed_copies,
                    inventory_observation_id=o.inventory_observation_id))
        (artifacts/'current_inventory_identification_review.csv').write_bytes(_csv_bytes(
            ['collection','title','creators','isbn13','isbn10','copies','inventory_observation_id'],pending))
        active=set(after_scope.catalog_item_ids)
        historical=[dict(catalog_item_id=b.catalog_item_id,title=b.title,author=b.author,isbn13=b.isbn13,
            acquisition_count=len(b.acquisition_ids),status='Outside completed inventory; purchase history preserved')
            for b in model.books if b.catalog_item_id not in active]
        (artifacts/'historical_catalog.csv').write_bytes(_csv_bytes(
            ['catalog_item_id','title','author','isbn13','acquisition_count','status'],historical))
        summary=dict(reviewed=len(entries),resolved=len(entries)-len(expected_left),remaining=len(expected_left),
            action_counts=dict(action_counts),new_catalog_records=len(catalog)-old_catalog_count,
            active_catalog_books=len(active),source_entries=after_scope.source_entries,
            source_copies=after_scope.source_copies,source_only_identifiers_unknown=len(identifier_followup),followup_counts=dict(Counter(f['category'] for f in followups)),
            purchase_records_preserved=len(model.acquisitions),published=publish,review_plan_sha256=receipt_id)
        (artifacts/'inventory_review_summary.json').write_text(json.dumps(summary,indent=2,sort_keys=True)+'\n')
        # Keep the main completion report current instead of leaving the pre-review counts.
        (artifacts/'completed_inventory_reconciliation.json').write_text(json.dumps(summary,indent=2,sort_keys=True)+'\n')
        modified={'catalog_items.csv','inventory_holdings.csv','inventory_reconciliation_decisions.csv',
                  'inventory_catalog_reconciliation_decisions.csv'}
        for name,content in before.items():
            if name not in modified and (work/name).read_bytes()!=content:
                raise ValueError('Protected source or history was changed: '+name)
            if (data_dir/name).read_bytes()!=content:
                raise ValueError('Durable state changed during review; retry from a fresh plan')
        output_dir.mkdir(parents=True,exist_ok=True)
        payloads=[(output_dir/p.name,p.read_bytes()) for p in artifacts.iterdir()]
        if publish:
            payloads.extend((data_dir/name,(work/name).read_bytes()) for name in sorted(modified))
        publish_files(payloads)
        return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan',dest='plan_path',type=Path,required=True)
    parser.add_argument('--data-dir',type=Path,default=Path('data'))
    parser.add_argument('--output-dir',type=Path,default=Path('output'))
    parser.add_argument('--market-evidence-summary',type=Path)
    parser.add_argument('--libib-input-dir',type=Path,default=Path('input/libib'))
    parser.add_argument('--publish',action='store_true')
    print(json.dumps(apply_reviewed_plan(**vars(parser.parse_args())),indent=2,sort_keys=True))


if __name__=='__main__':main()
