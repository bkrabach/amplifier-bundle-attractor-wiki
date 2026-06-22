#!/usr/bin/env python3
"""Deterministic queue helper for the wiki-apply-resolutions pipeline.

The apply-resolutions.dot loop nodes are parallelogram (tool) nodes that
shell out to this helper. The loop mechanics stay deterministic so the only
LLM judgment is in the 'apply' and 'apply_semantic_check' box nodes.

Queue file: team-knowledge/review-queue.json
  Each item:
    id             -- stable content-derived idempotency key
                      (sha256(kind|first_target_page|resolution_text[:50])[:16])
    kind           -- "nl_feedback" | "type_migration" | "entailment_unsure"
    status         -- "open" | "resolved" | "applied" | "applied_uncertain"
    target_pages   -- list of paths the resolution is expected to touch
    resolution     -- { decision: str OR freetext: str, note: str }
    applied        -- null | { at: iso8601, changed_pages: [str] }

  Status lifecycle:
    open              waiting for a resolution (resolution field absent/empty)
    resolved          resolution present; ready to apply
    applied           successfully applied and semantically verified; SKIP on re-run
    applied_uncertain semantically incomplete; needs human review or re-resolution

Subcommands:
    next          pop the next actionable item (status == "resolved", OR
                  status == "open" with a non-empty resolution) -- SKIPS
                  status == "applied" and status == "applied_uncertain".
                  Writes .wiki/apply-current.json and prints "ITEM" or "EMPTY".

    mark_applied  mark the current item status="applied". Reads changed pages
                  from .wiki/apply-changes.txt (one path per line, written by
                  the apply LLM node). Prints "marked_applied".

    requeue       mark the current item status="applied_uncertain". Reads the
                  semantic-check verdict from .wiki/apply-semantic-verdict.txt
                  and appends it to the item's resolution note. Does NOT seal
                  the item; leaves it for human review or re-resolution.
                  Prints "requeued".
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

QUEUE = Path("team-knowledge/review-queue.json")
CUR_JSON = Path(".wiki/apply-current.json")
CHANGES_TXT = Path(".wiki/apply-changes.txt")
VERDICT_TXT = Path(".wiki/apply-semantic-verdict.txt")


# ---------------------------------------------------------------------------
# Queue I/O helpers
# ---------------------------------------------------------------------------


def _load_queue() -> list[dict]:
    if not QUEUE.exists():
        return []
    try:
        data = json.loads(QUEUE.read_text())
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def _save_queue(items: list[dict]) -> None:
    QUEUE.write_text(json.dumps(items, indent=2, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Action gate: an item is "actionable" if it has a non-empty resolution and
# is not yet in a terminal state (applied) or needs-human state (applied_uncertain).
# ---------------------------------------------------------------------------


def _is_actionable(item: dict) -> bool:
    status = item.get("status", "open")
    if status in ("applied", "applied_uncertain"):
        return False
    resolution = item.get("resolution") or {}
    text = (resolution.get("decision") or resolution.get("freetext") or "").strip()
    return bool(text)


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


def cmd_next() -> int:
    """Yield the next actionable item; write it to .wiki/apply-current.json."""
    items = _load_queue()
    for item in items:
        if _is_actionable(item):
            CUR_JSON.parent.mkdir(parents=True, exist_ok=True)
            CUR_JSON.write_text(json.dumps(item, indent=2, ensure_ascii=False) + "\n")
            print("ITEM")
            return 0
    # Nothing actionable — queue exhausted.
    if CUR_JSON.exists():
        CUR_JSON.unlink()
    print("EMPTY")
    return 0


def cmd_mark_applied() -> int:
    """Mark the current item applied. Reads changed pages from apply-changes.txt."""
    if not CUR_JSON.exists():
        print("error:no-current-item")
        return 1
    item = json.loads(CUR_JSON.read_text())
    item_id = item.get("id", "")

    changed_pages: list[str] = []
    if CHANGES_TXT.exists():
        changed_pages = [
            line.strip()
            for line in CHANGES_TXT.read_text().splitlines()
            if line.strip()
        ]

    items = _load_queue()
    for q in items:
        if q.get("id") == item_id:
            q["status"] = "applied"
            q["applied"] = {
                "at": datetime.now(tz=timezone.utc).isoformat(),
                "changed_pages": changed_pages,
            }
            break
    _save_queue(items)

    # Clean up temp files so they don't bleed into the next item's run.
    for p in (CUR_JSON, CHANGES_TXT, VERDICT_TXT):
        if p.exists():
            p.unlink()

    print("marked_applied")
    return 0


def cmd_requeue() -> int:
    """Mark the current item applied_uncertain; append the semantic-check note."""
    if not CUR_JSON.exists():
        print("error:no-current-item")
        return 1
    item = json.loads(CUR_JSON.read_text())
    item_id = item.get("id", "")

    # Read the semantic-check verdict (written by apply_semantic_check LLM node).
    note = ""
    if VERDICT_TXT.exists():
        note = VERDICT_TXT.read_text().strip()

    items = _load_queue()
    for q in items:
        if q.get("id") == item_id:
            q["status"] = "applied_uncertain"
            resolution = q.get("resolution") or {}
            prev_note = resolution.get("note", "")
            if note:
                resolution["note"] = f"{prev_note}\n[semantic-check] {note}".strip()
            q["resolution"] = resolution
            break
    _save_queue(items)

    # Clean up temp files.
    for p in (CUR_JSON, CHANGES_TXT, VERDICT_TXT):
        if p.exists():
            p.unlink()

    print("requeued")
    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: apply_resolutions_queue.py next | mark_applied | requeue")
        return 2
    cmd = argv[1]
    if cmd == "next":
        return cmd_next()
    if cmd == "mark_applied":
        return cmd_mark_applied()
    if cmd == "requeue":
        return cmd_requeue()
    print(f"unknown command: {cmd}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
