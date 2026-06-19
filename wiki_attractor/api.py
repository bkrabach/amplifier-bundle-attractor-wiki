#!/usr/bin/env python3
"""wiki-attractor bespoke public API — one named async function per command.

Each function is the authoritative assembly point for its command:
  1. Validates / prepares wiki_dir (single shared guard, not re-checked per caller).
  2. Builds the subs dict from typed arguments + resolves asset_subs.
  3. Calls run_pipeline() — the single engine entry — with the right options.

Both code-based consumers (CLI and tool-module) call these functions instead of
calling run_pipeline() directly.  All "code-path" callers flow through here.

Adding a 7th command:
  - One PipelineSpec in registry.py + one .dot file  (data-only, unchanged).
  - One small named function in this file              (the one new code artifact
    per command — the intentional cost of a typed, named, wiki-attractor API).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .registry import ASSETS_DIR, REGISTRY
from .runner import run_pipeline

_PKG = Path(__file__).resolve().parent
_REVIEW_HELPER = _PKG / "review_queue.py"


# ---------------------------------------------------------------------------
# Shared guards — ONE place for the requires_wiki + init-mkdir logic so both
# code-path callers (CLI and tool-module) inherit it automatically.
# ---------------------------------------------------------------------------


def _check_wiki(wiki_dir: str | Path) -> Path:
    """Resolve wiki_dir and verify it is an initialized wiki.

    Raises ValueError (with a user-friendly message) if
    .wiki/context/schema.md is missing.
    """
    wiki_dir = Path(wiki_dir).resolve()
    schema = wiki_dir / ".wiki" / "context" / "schema.md"
    if not schema.exists():
        raise ValueError(
            f"{wiki_dir} is not an initialized wiki "
            "(missing .wiki/context/schema.md). Run init() first."
        )
    return wiki_dir


def _prepare_init_dir(wiki_dir: str | Path) -> Path:
    """Resolve wiki_dir and create it (init runs on a new or empty dir)."""
    wiki_dir = Path(wiki_dir).resolve()
    wiki_dir.mkdir(parents=True, exist_ok=True)
    return wiki_dir


# ---------------------------------------------------------------------------
# The 6 named API functions.
# ---------------------------------------------------------------------------


async def ingest(wiki_dir: str | Path, source: str) -> dict[str, Any]:
    """Ingest a source file from raw/ into the wiki.

    Mines the source, writes entity pages, reconciles duplicates, runs a
    provenance audit + second-LLM review, and verifies with verify.sh.
    ``source`` is the bare filename in raw/ (e.g. ``2026-06-20-call.md``).

    Returns the pipeline result dict.  ``result["status"] == "success"`` on a
    clean run.

    Raises ValueError if wiki_dir is not an initialized wiki.
    """
    wiki_dir = _check_wiki(wiki_dir)
    spec = REGISTRY["ingest"]
    subs = {"$source": source}
    return await run_pipeline(spec.dot, wiki_dir, subs=subs)


async def query(wiki_dir: str | Path, question: str) -> dict[str, Any]:
    """Answer a question against the compiled wiki (read-only, index-first, cited).

    Returns the pipeline result dict.  The full cited answer text is in
    ``result["output"]``.

    Raises ValueError if wiki_dir is not an initialized wiki.
    """
    wiki_dir = _check_wiki(wiki_dir)
    spec = REGISTRY["query"]
    subs = {"$question": question}
    return await run_pipeline(
        spec.dot, wiki_dir, subs=subs, output_file=spec.output_file
    )


async def lint(wiki_dir: str | Path) -> dict[str, Any]:
    """Run a read-only health check on the wiki.

    Runs verify.sh (frontmatter, enums, orphans, duplicate titles) and an LLM
    pass that surfaces contradictions and stale cross-refs.  Writes the full
    report to .wiki/lint-report.md and returns it in ``result["output"]``.

    Does NOT modify the wiki package directory.

    Raises ValueError if wiki_dir is not an initialized wiki.
    """
    wiki_dir = _check_wiki(wiki_dir)
    spec = REGISTRY["lint"]
    return await run_pipeline(spec.dot, wiki_dir, output_file=spec.output_file)


async def publish(wiki_dir: str | Path) -> dict[str, Any]:
    """Publish the wiki package via .wiki/scripts/publish.sh (zips to .wiki/dist/).

    Returns the pipeline result dict.

    Raises ValueError if wiki_dir is not an initialized wiki.
    """
    wiki_dir = _check_wiki(wiki_dir)
    spec = REGISTRY["publish"]
    return await run_pipeline(spec.dot, wiki_dir)


async def init(wiki_dir: str | Path, package: str, brief: str) -> dict[str, Any]:
    """Scaffold a new pure-markdown wiki in wiki_dir.

    Plants the canonical verify.sh and publish.sh scripts, authors
    .wiki/context/schema.md, and creates the backbone pages
    (overview.md, index.md, open-questions.md).

    wiki_dir is created (including parents) if it does not exist.
    ``package`` is the directory name for the wiki package (e.g. ``team-knowledge``).
    ``brief`` is a one-line domain description (e.g. ``"product team strategy KB"``).

    Returns the pipeline result dict.
    """
    wiki_dir = _prepare_init_dir(wiki_dir)
    spec = REGISTRY["init"]
    subs: dict[str, str] = {
        "$package": package,
        "$brief": brief,
    }
    # Resolve asset_subs: ("$ASSETS", ".") → absolute path of wiki_attractor/assets/.
    for placeholder, relpath in spec.asset_subs:
        subs[placeholder] = str((ASSETS_DIR / relpath).resolve())
    return await run_pipeline(spec.dot, wiki_dir, subs=subs)


async def review(
    wiki_dir: str | Path,
    *,
    interviewer: Any | None = None,
) -> dict[str, Any]:
    """Walk the flag-queue.json and apply resolutions to each flagged claim.

    The flag-queue is produced by the ``ingest`` pipeline's provenance-audit node.

    Args:
        wiki_dir:    Wiki repository root (must be an initialized wiki).
        interviewer: Controls how each flagged claim is resolved.

            - ``None`` (default): **auto-confirm all items** — every
              TODO-VERIFY flag is preserved as-is.  Safe headless default;
              never silently removes flags.
            - ``ConsoleInterviewer()``: interactive human-in-the-loop review
              (prompts the user at each item).
            - ``QueueInterviewer([Answer(value="C"), ...])``: scripted review
              with explicit C/X/P decisions per item.

    Returns the pipeline result dict.

    Raises ValueError if:
        - wiki_dir is not an initialized wiki, OR
        - team-knowledge/flag-queue.json does not exist (run ingest() first), OR
        - flag-queue.json cannot be parsed.
    """
    wiki_dir = _check_wiki(wiki_dir)
    spec = REGISTRY["review"]
    subs = {"$PYBIN": sys.executable, "$HELPER": str(_REVIEW_HELPER)}

    # Always validate the queue exists — fail loud before the pipeline starts,
    # regardless of which interviewer is used.
    queue_path = wiki_dir / "team-knowledge" / "flag-queue.json"
    if not queue_path.exists():
        raise ValueError(
            "flag-queue.json not found in team-knowledge/. "
            "Run ingest() first so the provenance audit node emits the queue."
        )

    if interviewer is None:
        # Auto-confirm all items: build a full-confirm QueueInterviewer.
        # Reads the queue to count items — never silently confirms zero items.
        from amplifier_module_loop_pipeline.interviewer import (  # noqa: PLC0415
            Answer,
            QueueInterviewer,
        )

        try:
            queue = json.loads(queue_path.read_text())
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"Could not parse flag-queue.json: {exc}") from exc

        interviewer = QueueInterviewer([Answer(value="C") for _ in queue])

    return await run_pipeline(spec.dot, wiki_dir, subs=subs, interviewer=interviewer)
