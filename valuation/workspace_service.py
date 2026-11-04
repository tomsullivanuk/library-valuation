"""Loopback-only workspace with durable, explicit steward decisions.

Generated HTML remains an offline read-only fallback. The service keeps decisions
in project repositories, never in browser storage or the generated HTML.
"""
from __future__ import annotations

import argparse
import csv
import fcntl
import hashlib
import io
import json
import secrets
import subprocess
import sys
import time
import threading
import unicodedata
from contextlib import contextmanager
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, unquote
from urllib.request import urlopen
from urllib.error import URLError

from valuation.completed_inventory import publish_files
from valuation.repositories import CollectorReviewRepository, COLLECTOR_REVIEW_FIELDNAMES
from valuation.steward_presentation import build_steward_presentation, DerivedEvidenceInput, RegisteredReport
from valuation.steward_workspace import build_recommendation_queues, render_steward_workspace

DISPOSITIONS = ("", "keep", "sell", "donate", "gift", "recycle", "undecided")
STATUSES = ("open", "complete", "deferred", "dismissed")
ACTION_LABELS = {
    "manual_market_research_needed": "Research the resale market",
    "review_for_possible_sale": "Consider this book for sale",
    "review_edition_or_condition": "Check the edition or condition for valuation",
    "fallback_research_priority": "Research this book when time permits",
    "metadata_cleanup_needed": "Check bibliographic details",
}


def _rows(path):
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def load_model(data_dir, output_dir):
    data_dir, output_dir = Path(data_dir), Path(output_dir)
    reports = []
    for key, label, fmt in [("physical_book_checks", "Physical book checks", "csv"),
                            ("inventory_followup_resolutions", "Follow-up review evidence", "csv"),
                            ("inventory_review_workbook", "Inventory review workbook", "xlsx")]:
        path = output_dir / (key + "." + fmt)
        if path.exists():
            reports.append(RegisteredReport(key, label, "Inventory review", "Steward", fmt,
                path, path.name, "workspace-service", catalog_snapshot_sha256=hashlib.sha256((data_dir / "catalog_items.csv").read_bytes()).hexdigest()))
    market = output_dir / "libib_inventory_20261020/combined_market_evidence_summary.csv"
    # The evidence is a historical snapshot; validate catalog identity before reuse.
    if market.exists():
        from valuation.inventory_workflow import _validate_market_evidence_applicability
        _validate_market_evidence_applicability(market, data_dir / "catalog_items.csv")
    return build_steward_presentation(data_dir=data_dir, reports=reports,
        market_evidence=DerivedEvidenceInput(market, identity_validated=True) if market.exists() else None)


def build_actions(model, checks):
    """Merge concrete book checks and current recommendations without duplicates."""
    actions = []
    scope = model.completed_inventory
    current_obs = set(scope.unresolved_observation_ids)
    current_obs.update(h.latest_inventory_observation_id for h in model.holdings if h.holding_id in scope.holding_ids)
    by_obs = {h.latest_inventory_observation_id: h for h in model.holdings}
    covered = set()
    for row in checks:
        oid = row["inventory_observation_id"]
        if scope.completed and oid not in current_obs:
            continue
        covered.add(oid)
        holding = by_obs.get(oid)
        actions.append(dict(id="book-check:" + oid, title=row["title"],
            action=row["question"], category="Book checks", location=row["collection"],
            evidence=row.get("bibliographic_evidence", ""),
            catalog_item_id=holding.catalog_item_id if holding else "",
            route="book/" + holding.catalog_item_id if holding and holding.catalog_item_id else "observation/" + oid))
    for queue in build_recommendation_queues(model):
        for rec in queue.recommendations:
            holding = None
            # A newly inventoried book is a fact, not by itself work to be done.
            if rec.source_kind == "inventory_newly_discovered" or rec.suggested_action in {"no_action_needed", "market_evidence_sufficient"}:
                continue
            oid = rec.entity_id if rec.entity_type == "inventory_observation" else ""
            if rec.entity_type == "holding":
                holding = next((h for h in model.holdings if h.holding_id == rec.entity_id), None)
                oid = holding.latest_inventory_observation_id if holding else ""
            if oid in covered:
                continue
            if rec.source_kind == "inventory_location_review" and holding and holding.source_collection_label:
                # Libib collection is the chosen location: a separate internal ID is unnecessary.
                continue
            actions.append(dict(id=rec.recommendation_id, title=rec.entity_label,
                action=ACTION_LABELS.get(rec.suggested_action, rec.suggested_action),
                category="Optional research" if rec.source_kind == "market_evidence" else queue.title,
                location="",
                evidence=rec.explanation.replace("_", " "),
                catalog_item_id=rec.entity_id if rec.entity_type == "catalog_item" else "",
                route=rec.primary_route))
    for action in actions:
        action["fingerprint"] = hashlib.sha256(json.dumps(action, sort_keys=True).encode()).hexdigest()
    return actions


def load_book_checks(data_dir, model):
    """Read canonical reviewed follow-ups and current identity questions.

    Generated CSVs are exports of these records, not the task source of truth.
    """
    data_dir = Path(data_dir)
    checks = {}
    receipt = data_dir / "inventory_followup_reviews.json"
    if receipt.exists():
        saved = json.loads(receipt.read_text())
        if saved.get("schema_version") != 1:
            raise ValueError("Unsupported inventory follow-up review schema")
        for row in saved["reviews"]:
            if row["status"] == "physical_check_required":
                checks[row["inventory_observation_id"]] = dict(
                    inventory_observation_id=row["inventory_observation_id"],
                    title=row["title"], question=row["question"], collection=row["collection"],
                    bibliographic_evidence=row.get("bibliographic_evidence", ""))
    observations = {o.inventory_observation_id:o for o in model.observations}
    unresolved = set(model.completed_inventory.unresolved_observation_ids)
    for decision in model.decisions:
        oid = decision.inventory_observation_id
        if decision.is_current and oid in unresolved and "Steward input needed:" in decision.explanation:
            observation = observations[oid]
            evidence, question = decision.explanation.split("Steward input needed:", 1)
            checks[oid] = dict(inventory_observation_id=oid, title=observation.title,
                question=question.strip(), collection=observation.source_collection_label,
                bibliographic_evidence=evidence.strip())
    import re
    return sorted(checks.values(), key=lambda row:(
        tuple((0, int(part)) if part.isdigit() else (1, part.casefold())
              for part in re.split(r"(\d+)", row["collection"])), row["title"].casefold()))


class WorkspaceStore:
    def __init__(self, data_dir, output_dir, *, model=None):
        self.data_dir, self.output_dir = Path(data_dir), Path(output_dir)
        self.model = model or load_model(self.data_dir, self.output_dir)
        self.actions = build_actions(self.model, load_book_checks(self.data_dir, self.model))
        self.lock = threading.RLock()
        self.token = secrets.token_urlsafe(32)

    @property
    def path(self):
        return self.data_dir / "workspace_actions.json"

    def read(self):
        state = json.loads(self.path.read_text()) if self.path.exists() else dict(schema_version=1, revision=0, actions={}, events=[])
        if state.get("schema_version") != 1:
            raise ValueError("Unsupported saved workspace state")
        return state

    def snapshot(self):
        with self.lock:
            state = self.read()
            reviews = CollectorReviewRepository(self.data_dir / "collector_reviews.csv").load()
            actions = []
            for task in self.actions:
                saved = state["actions"].get(task["id"], {})
                if saved.get("fingerprint") != task["fingerprint"]:
                    saved = {}
                actions.append(dict(task, status=saved.get("status", "open"),
                    deferred_until=saved.get("deferred_until", ""), note=saved.get("note", "")))
            observed = {h.latest_inventory_observation_id for h in self.model.holdings if h.holding_id in self.model.completed_inventory.holding_ids}
            observed.update(self.model.completed_inventory.unresolved_observation_ids)
            titles = {" ".join(unicodedata.normalize("NFKC", o.title).casefold().split()) for o in self.model.observations if o.inventory_observation_id in observed and o.title.strip()}
            return dict(workspace_id=workspace_id(self.data_dir), revision=state["revision"], token=self.token, actions=actions,
                dispositions={r["catalog_item_id"]: r["disposition"] for r in reviews},
                disposition_choices=list(DISPOSITIONS), distinct_titles=len(titles))

    @contextmanager
    def write_lock(self):
        # Also serialize writes if two local service processes use the same data.
        with self.lock, (self.data_dir / ".workspace.lock").open("a") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def update(self, request):
        with self.write_lock():
            state = self.read()
            if type(request.get("revision")) is not int or request["revision"] != state["revision"]:
                raise RuntimeError("Another change was saved. Reload and try again.")
            stamp = datetime.now(timezone.utc).isoformat()
            kind = request.get("kind")
            payloads = []
            if kind == "action":
                task = next((t for t in self.actions if t["id"] == request.get("id")), None)
                if not task or task["fingerprint"] != request.get("fingerprint"):
                    raise ValueError("This task changed or is no longer available. Reload the workspace.")
                status = request.get("status")
                until = request.get("deferred_until", "")
                note = request.get("note", "")
                if status not in STATUSES or not isinstance(note, str) or len(note) > 4000:
                    raise ValueError("Invalid action status or note")
                if status == "deferred":
                    if not isinstance(until, str) or date.fromisoformat(until) <= datetime.now(ZoneInfo("America/Chicago")).date():
                        raise ValueError("Choose a future date for a deferred item")
                else:
                    until = ""
                value = dict(status=status, deferred_until=until, note=note,
                    fingerprint=task["fingerprint"], updated_at=stamp)
                state["actions"][task["id"]] = value
                event = dict(kind=kind, id=task["id"], **value)
            elif kind == "disposition":
                cid, value = request.get("id"), request.get("value")
                if cid not in {b.catalog_item_id for b in self.model.books} or value not in DISPOSITIONS:
                    raise ValueError("Unknown book or disposition")
                repo = CollectorReviewRepository(self.data_dir / "collector_reviews.csv")
                reviews = repo.load()
                matches = [r for r in reviews if r["catalog_item_id"] == cid]
                if len(matches) > 1:
                    raise ValueError("Conflicting review records need review before editing")
                review = matches[0] if matches else dict.fromkeys(COLLECTOR_REVIEW_FIELDNAMES, "")
                if not matches:
                    reviews.append(review)
                    review.update(catalog_item_id=cid, created_at=stamp)
                old = review["disposition"]
                review.update(disposition=value, updated_at=stamp, reviewed_at=stamp, reviewed_by="Steward")
                buffer = io.StringIO(newline="")
                writer = csv.DictWriter(buffer, fieldnames=COLLECTOR_REVIEW_FIELDNAMES)
                writer.writeheader(); writer.writerows(reviews)
                payloads.append((repo.path, buffer.getvalue().encode()))
                event = dict(kind=kind, id=cid, previous=old, value=value, updated_at=stamp)
            else:
                raise ValueError("Unknown workspace change")
            state["revision"] += 1
            state["events"].append(event)
            payloads.append((self.path, (json.dumps(state, indent=2, ensure_ascii=False) + "\n").encode()))
            publish_files(payloads)
            return self.snapshot()


def make_server(store, port=8765):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, code, body, content_type="application/json"):
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers(); self.wfile.write(body)

        def local_request(self):
            expected = f"127.0.0.1:{self.server.server_port}"
            return self.headers.get("Host") == expected and self.headers.get("Origin", "http://" + expected) == "http://" + expected

        def do_GET(self):
            if not self.local_request():
                return self.send(403, b'{"error":"Local workspace requests only"}')
            path = unquote(urlsplit(self.path).path)
            if path == "/api/state":
                return self.send(200, json.dumps(store.snapshot()).encode())
            if path in {"/", "/steward_workspace.html"}:
                # Rebuild on reload; all saved decisions remain in repositories.
                with store.lock:
                    model = load_model(store.data_dir, store.output_dir)
                    store.model = model
                    store.actions = build_actions(model, load_book_checks(store.data_dir, model))
                return self.send(200, render_steward_workspace(model, action_items=store.actions), "text/html; charset=utf-8")
            allowed = {r.public_path: r for r in store.model.reports if r.public_path}
            if path.lstrip("/") in allowed:
                file = (store.output_dir / path.lstrip("/")).resolve()
                if file.parent == store.output_dir.resolve() and file.is_file():
                    kind = "text/csv; charset=utf-8" if file.suffix == ".csv" else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    return self.send(200, file.read_bytes(), kind)
            return self.send(404, b'{"error":"Not found"}')

        def do_POST(self):
            if not self.local_request() or self.headers.get("X-Workspace-Token") != store.token:
                return self.send(403, b'{"error":"Reload the local workspace before saving"}')
            if self.path != "/api/state" or self.headers.get("Content-Type") != "application/json":
                return self.send(400, b'{"error":"Invalid request"}')
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 16384:
                    raise ValueError("Invalid request size")
                request = json.loads(self.rfile.read(length))
                if not isinstance(request, dict):
                    raise ValueError("Invalid request")
                result = store.update(request)
                self.send(200, json.dumps(result).encode())
            except RuntimeError as exc:
                self.send(409, json.dumps(dict(error=str(exc))).encode())
            except (ValueError, TypeError, KeyError) as exc:
                self.send(400, json.dumps(dict(error=str(exc))).encode())
    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def workspace_id(data_dir):
    return hashlib.sha256(str(Path(data_dir).resolve()).encode()).hexdigest()


def service_ready(port, data_dir):
    try:
        with urlopen(f"http://127.0.0.1:{port}/api/state", timeout=1) as response:
            return json.load(response).get("workspace_id") == workspace_id(data_dir)
    except (URLError, OSError, ValueError):
        return False


def start_background(data_dir, output_dir, port):
    """Start independently of the caller's terminal/session and wait for readiness."""
    if not 1 <= port <= 65535:
        raise ValueError("Background mode requires a fixed port between 1 and 65535")
    data_dir, output_dir = Path(data_dir).resolve(), Path(output_dir).resolve()
    if service_ready(port, data_dir):
        return
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / "workspace-service.log"
    command = [sys.executable, "-m", "valuation.workspace_service",
               "--data-dir", str(data_dir), "--output-dir", str(output_dir), "--port", str(port)]
    project_root = Path(__file__).resolve().parent.parent
    process = None
    label = "local.library-valuation." + workspace_id(data_dir)[:12] + "." + str(port)
    if sys.platform == "darwin":
        # launchd owns the child: chat/terminal process cleanup cannot stop it.
        subprocess.run(["/bin/launchctl", "remove", label],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        subprocess.run(["/bin/launchctl", "submit", "-l", label,
                        "-o", str(log_path), "-e", str(log_path), "--",
                        "/usr/bin/env", "PYTHONPATH=" + str(project_root), *command], check=True)
    else:
        with log_path.open("ab") as log:
            process = subprocess.Popen(command, cwd=project_root,
                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                start_new_session=True)
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if service_ready(port, data_dir):
            return
        if process is not None and process.poll() is not None:
            raise RuntimeError(f"The library could not start. Details: {log_path}")
        time.sleep(0.2)
    if process is not None:
        process.terminate()
    else:
        subprocess.run(["/bin/launchctl", "remove", label], check=False)
    raise RuntimeError(f"The library did not start in time. Details: {log_path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--background", action="store_true", help="Keep the local service running after the launcher closes")
    args = parser.parse_args()
    if args.background:
        try:
            start_background(args.data_dir, args.output_dir, args.port)
        except (ValueError, RuntimeError, OSError) as error:
            parser.exit(1, str(error) + "\n")
        print(f"Library workspace: http://127.0.0.1:{args.port}", flush=True)
        return
    server = make_server(WorkspaceStore(args.data_dir, args.output_dir), args.port)
    print(f"Library workspace: http://127.0.0.1:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
