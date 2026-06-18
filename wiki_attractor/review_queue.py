#!/usr/bin/env python3
"""Deterministic queue helper for the wiki-review HITL pipeline.

The wiki-review.dot loop nodes are parallelogram (tool) nodes that shell out to
this helper. Keeping the loop MECHANICS deterministic (no LLM in the control
flow) makes the HITL mechanism cheap and provable: the only judgment in the
pipeline is the human's at the hexagon gate. The one node that could be an LLM
(applying a nuanced page edit) is implemented mechanically here because each of
the three decisions reduces to a deterministic file op:

    confirm  -> keep the flag, mark the item resolved (human agrees it's open)
    correct  -> remove the over-cautious '> TODO-VERIFY:' line from the page
    promote  -> remove the flag AND bump the page frontmatter to status: settled

All paths are relative to the CURRENT WORKING DIRECTORY, which the harness sets
to the wiki repo root (so this matches how verify.sh is invoked in wiki-ingest).

Subcommands:
    next                 pop the next status=="open" item -> review-current.{json,txt};
                         print "ITEM" (last_line) or "EMPTY" for diamond routing.
    apply <decision>     apply confirm|correct|promote to the current item + page;
                         mark the item resolved in the queue; print "applied:<decision>".
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

QUEUE = Path("team-knowledge/flag-queue.json")
CUR_JSON = Path(".wiki/review-current.json")
CUR_TXT = Path(".wiki/review-current.txt")


def _load_queue() -> list[dict]:
    if not QUEUE.exists():
        return []
    try:
        data = json.loads(QUEUE.read_text())
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def _save_queue(items: list[dict]) -> None:
    QUEUE.write_text(json.dumps(items, indent=2) + "\n")


def _norm(s: str) -> str:
    """Normalized comparison key: lowercase alphanumerics only."""
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def cmd_next() -> int:
    items = _load_queue()
    for item in items:
        if item.get("status", "open") == "open":
            CUR_JSON.parent.mkdir(parents=True, exist_ok=True)
            CUR_JSON.write_text(json.dumps(item, indent=2) + "\n")
            block = (
                f"PAGE        : {item.get('page')}\n"
                f"CLAIM       : {item.get('claim')}\n"
                f"CITED SOURCE: {item.get('cited_source')}\n"
                f"RAW SOURCE  : {item.get('raw_source')}\n"
                f"REVIEWER    : {item.get('reviewer_note')}\n"
            )
            CUR_TXT.write_text(block)
            print("ITEM")
            return 0
    # nothing open
    if CUR_JSON.exists():
        CUR_JSON.unlink()
    print("EMPTY")
    return 0


def _remove_flag_line(page: Path, claim: str) -> bool:
    """Remove the first '> TODO-VERIFY:' line on the page that references claim.

    Returns True if a line was removed.
    """
    if not page.exists():
        return False
    lines = page.read_text().splitlines(keepends=True)
    claim_key = _norm(claim)[:25]
    out: list[str] = []
    removed = False
    for line in lines:
        if (
            not removed
            and "TODO-VERIFY" in line
            and (claim_key in _norm(line) or _norm(line)[:25] in _norm(claim))
        ):
            removed = True
            continue  # drop this line
        out.append(line)
    if removed:
        page.write_text("".join(out))
    return removed


def _set_status_settled(page: Path) -> bool:
    """Bump frontmatter 'status:' to settled. Returns True if changed."""
    if not page.exists():
        return False
    text = page.read_text()
    new = re.sub(
        r"(?m)^status:\s*\w+\s*$",
        "status: settled",
        text,
        count=1,
    )
    if new != text:
        page.write_text(new)
        return True
    return False


def cmd_apply(decision: str) -> int:
    if decision not in ("confirm", "correct", "promote"):
        print(f"applied:error:bad-decision:{decision}")
        return 1
    if not CUR_JSON.exists():
        print("applied:error:no-current-item")
        return 1
    item = json.loads(CUR_JSON.read_text())
    page = Path(item.get("page", ""))
    claim = item.get("claim", "")

    note = ""
    if decision == "correct":
        removed = _remove_flag_line(page, claim)
        note = "flag-removed" if removed else "flag-not-found"
    elif decision == "promote":
        removed = _remove_flag_line(page, claim)
        bumped = _set_status_settled(page)
        note = f"flag-{'removed' if removed else 'not-found'}+status-{'settled' if bumped else 'unchanged'}"
    else:  # confirm
        note = "flag-kept"

    # Mark the item resolved in the queue (match by page + claim).
    items = _load_queue()
    target_key = (_norm(item.get("page", "")), _norm(claim))
    for q in items:
        if (_norm(q.get("page", "")), _norm(q.get("claim", ""))) == target_key:
            q["status"] = {
                "confirm": "confirmed",
                "correct": "corrected",
                "promote": "promoted",
            }[decision]
            q["resolution_note"] = note
            break
    _save_queue(items)

    # Consume the current-item marker so the loop advances.
    if CUR_JSON.exists():
        CUR_JSON.unlink()
    print(f"applied:{decision}:{note}")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: review_queue.py next | apply <confirm|correct|promote>")
        return 2
    cmd = argv[1]
    if cmd == "next":
        return cmd_next()
    if cmd == "apply":
        if len(argv) < 3:
            print("usage: review_queue.py apply <confirm|correct|promote>")
            return 2
        return cmd_apply(argv[2])
    print(f"unknown command: {cmd}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
