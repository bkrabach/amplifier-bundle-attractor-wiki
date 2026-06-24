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

import datetime
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from .registry import ASSETS_DIR, REGISTRY
from .runner import run_pipeline

# ---------------------------------------------------------------------------
# Package path constants — defined early so classify and other helpers can use them.
# ---------------------------------------------------------------------------

_PKG = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# Input-type classifier — deterministic FAIL-CLOSED guard for unsupported input.
#
# WHY: the schema is prose-only (outcomes/concepts/people/sources).  Pointing
# ingest at source code or a binary file would silently mine it as prose and
# emit plausible-looking but meaningless entity pages — the worst failure class
# (silent, trust-destroying).  This guard runs BEFORE any LLM work so that
# code/binary input FAILS LOUD with an actionable message rather than
# producing garbage.  It is intentionally conservative: when in doubt, allow.
#
# SINGLE SOURCE OF TRUTH: all classification logic lives in
# wiki_attractor/assets/classify_source.py (stdlib-only, portable). That script
# is planted into .wiki/scripts/ by init, so it travels with every wiki AND runs
# as the ingest.dot classify node.  This file (api.py) calls it as a subprocess
# so both the Python-path callers (CLI, tool-module) and the native .dot pipeline
# use EXACTLY the same logic — zero duplication.
#
# FAIL CLOSED: any exception, missing file, subprocess error, or ambiguity →
# REJECT.  The guard never accepts on error.
#
# Binary-sniff-first invariant: classify_source.py reads 8 KB before any
# extension check, so a binary file renamed to notes.md is still rejected.
# ---------------------------------------------------------------------------

# Path to the shared classify helper (canonical source; planted to wikis by init).
_CLASSIFY_SCRIPT: Path = _PKG / "assets" / "classify_source.py"


def _run_classify(file_path: Path) -> tuple[bool, str]:
    """Call classify_source.py on *file_path* as a subprocess.

    Returns
    -------
    (True,  "")
        File is acceptable prose — safe to ingest.
    (False, <actionable_message>)
        File is unsupported (binary, code, unreadable, or missing).

    FAIL CLOSED: any subprocess error, timeout, or exception returns
    (False, reason) — never (True, ...).
    """
    try:
        r = subprocess.run(
            [sys.executable, str(_CLASSIFY_SCRIPT), str(file_path)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if r.returncode == 0:
            return True, ""
        msg = (
            r.stdout.strip()
            or r.stderr.strip()
            or (
                f"Unsupported input type: {file_path.name} — "
                "wiki-attractor ingests plain-text prose only."
            )
        )
        return False, msg
    except Exception as exc:  # noqa: BLE001
        return False, (
            f"Input classification error for {file_path.name}: {exc}.\n"
            "wiki-attractor ingests plain-text prose only "
            "(documents, transcripts, notes)."
        )


def _classify_file_path(file_path: Path) -> str | None:
    """Check whether *file_path* is a supported prose input.

    Returns:
        ``None``            if the file is supported prose (safe to ingest).
        A short reason str  if the file is unsupported (skip / reject).

    This is the pure-classification companion to ``_classify_source``: same
    detection logic (delegated to the shared classify_source.py helper), but
    takes an absolute ``Path`` directly rather than ``(wiki_dir, source)``.
    Used by :func:`ingest_folder` to triage files in a source folder *before*
    staging them into ``raw/``.

    Key invariant: a ``.md`` file that contains fenced code blocks is still
    treated as prose — the *extension*, not the content, is the signal.
    Binary-sniff-first: binary bytes detected before extension check, so a
    binary file renamed to .md is still rejected.
    """
    ok, msg = _run_classify(file_path)
    if ok:
        return None
    # Return a short reason (strip actionable multi-line detail for the skip list).
    first_line = msg.split("\n")[0] if msg else "unsupported input type"
    return first_line


def _classify_source(wiki_dir: Path, source: str) -> None:
    """Verify *source* is a supported prose input type.

    Raises ``ValueError`` (with a clear, actionable message) if the file is
    binary or has a source-code extension.  Prose files pass silently.

    Key invariant: a .md file that *contains* fenced code blocks is still
    treated as prose — the *extension*, not the content, is the signal.
    Binary-sniff-first: a binary file renamed to .md is still rejected.

    Delegates to the shared classify_source.py helper (stdlib-only script
    planted into .wiki/scripts/ by init and used as the ingest.dot classify
    node).  Single source of classification truth — no logic duplication.

    Runs BEFORE any LLM work so code/binary input never produces silent
    garbage entity pages.  Non-zero exit via the ValueError → ClickException
    chain at the CLI layer; same ValueError surfaces in the tool-module layer.
    """
    src = wiki_dir / "raw" / source
    ok, msg = _run_classify(src)
    if not ok:
        raise ValueError(msg)


_REVIEW_HELPER = _PKG / "review_queue.py"
_APPLY_HELPER = _PKG / "apply_resolutions_queue.py"

# The attractor pipeline engine writes its checkpoint here.  Sequential calls
# to run_pipeline() with different DOT graphs (different $source subs) will
# hit a CheckpointMismatchError unless cleared between runs.
_CHECKPOINT_PATH = Path("/tmp/attractor-pipeline/checkpoint.json")


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

    Raises ValueError if:
      - wiki_dir is not an initialized wiki, OR
      - the source file is binary (null bytes / non-UTF-8), OR
      - the source file has a source-code extension.

    The input-type check runs BEFORE any LLM work so code/binary input can
    never silently produce garbage entity pages.
    """
    wiki_dir = _check_wiki(wiki_dir)
    # FAIL-LOUD guard: reject code/binary before any LLM mining starts.
    _classify_source(wiki_dir, source)
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


async def full_pass(wiki_dir: str | Path) -> dict[str, Any]:
    """Run a periodic whole-wiki global pass.

    Performs three whole-wiki phases the per-ingest L3-scoped pipeline defers:
      1. **full_reconcile** — cross-ingest dedup/merge, type enforcement, orphan heal.
      2. **full_provenance** — status drift re-audit and cross-ingest contradiction scan.
      3. **full_weave** — OLD-TO-OLD Memex connections between pages that were never
         in the same per-ingest changed-neighborhood.

    The pass MODIFIES the wiki (adds/merges pages, adds wikilinks, writes
    .wiki/full-pass-report.md).  Run periodically after every ~5-10 ingests
    or after a major expansion.

    Returns the pipeline result dict.  ``result["output"]`` contains the
    full-pass report written by the full_weave node.

    Raises ValueError if wiki_dir is not an initialized wiki.
    """
    wiki_dir = _check_wiki(wiki_dir)
    spec = REGISTRY["full-pass"]
    return await run_pipeline(spec.dot, wiki_dir, output_file=spec.output_file)


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


async def apply_resolutions(wiki_dir: str | Path) -> dict[str, Any]:
    """Apply resolutions from team-knowledge/review-queue.json to the wiki.

    Processes every actionable item in the queue (status == "resolved" or
    status == "open" with a non-empty resolution).  For each item:

    1. **apply** (LLM) — loads only the item's target_pages and interprets the
       resolution (structured decision OR NL freetext), making the change
       faithfully (type migration, wikilink repointing, index update, etc.).
    2. **apply_verify** — runs verify.sh; structural retry if dirty.
    3. **apply_semantic_check** (LLM) — verifies the apply accomplished the
       FULL intent of the resolution.  A structurally-valid but semantically-
       incomplete apply (1 of 3 required pages changed; verify.sh passes) is
       caught and set to ``applied_uncertain`` rather than sealed as ``applied``.

    Items with ``status == "applied"`` are SKIPPED — re-running is idempotent.
    Items routed to ``applied_uncertain`` need human review or re-resolution.

    Returns the pipeline result dict.

    Raises ValueError if wiki_dir is not an initialized wiki.
    """
    wiki_dir = _check_wiki(wiki_dir)
    spec = REGISTRY["apply-resolutions"]
    subs = {"$PYBIN": sys.executable, "$HELPER": str(_APPLY_HELPER)}
    return await run_pipeline(spec.dot, wiki_dir, subs=subs)


# ---------------------------------------------------------------------------
# Helpers for query_save().
# ---------------------------------------------------------------------------


def _make_query_slug(question: str, save_as: str | None = None) -> str:
    """Build a raw/ filename for a query-derived synthesis file."""
    today = datetime.date.today().isoformat()
    if save_as:
        name = (
            re.sub(r"[^a-z0-9-]", "-", save_as.lower().strip()).strip("-").rstrip(".md")
        )
        return f"{today}-query-{name}.md"
    slug = re.sub(r"[^a-z0-9]+", "-", question.lower()).strip("-")
    slug = slug[:60].rstrip("-")
    return f"{today}-query-{slug}.md"


def _make_query_title(question: str, save_as: str | None = None) -> str:
    """Build a human-readable title for the saved query file."""
    if save_as:
        return save_as.replace("-", " ").title()
    title = question.strip()[:100]
    if not title.endswith("?"):
        title = title.rstrip("?") + "?"
    return title


async def query_save(
    wiki_dir: str | Path,
    question: str,
    *,
    save_as: str | None = None,
    run_ingest: bool = True,
) -> dict[str, Any]:
    """Answer a question, save the cited answer to raw/, and ingest it.

    This is Karpathy's **compounding loop**: good query answers are filed back
    as first-class wiki pages so future queries build on accumulated synthesis,
    not just external sources.  Closing the loop in one command means every
    query that surfaces real insight can compound into the wiki immediately.

    The saved raw/ file is marked clearly as **query-derived synthesis** — not
    an external document — so the wiki's provenance record stays honest.  The
    ``source_type: query-derived-synthesis`` frontmatter flag and a prose
    provenance comment both appear in the file so the ingest pipeline's
    sources/ page records the origin faithfully.

    Args:
        wiki_dir:    Wiki repository root (must be an initialized wiki).
        question:    The question to answer.
        save_as:     Optional custom slug for the raw/ file, e.g. ``"1.5x-disruption-link"``.
                     Default: auto-derived from the question text plus today's date.
        run_ingest:  If ``True`` (default), ingest the saved file immediately
                     — the full loop closes in one call.  Set ``False`` to
                     write raw/ only; the file will be ingested on the next
                     ``ingest()`` call.

    Returns:
        A dict with keys:
          - ``status``: ``"success"`` if both query and ingest succeed
            (``"partial"`` if query succeeded but ingest failed).
          - ``query``:    the query pipeline result dict.
          - ``raw_file``: absolute path to the saved raw/ file.
          - ``ingest``:   the ingest pipeline result dict (only when run_ingest=True).

    Raises ValueError if wiki_dir is not an initialized wiki.
    """
    wiki_dir = _check_wiki(wiki_dir)

    # Step 1 — Run the query (read-only pass; answer lands in .wiki/query-answer.md)
    query_result = await query(wiki_dir, question)
    if query_result.get("status") not in ("success", "completed"):
        return {
            "status": query_result.get("status", "fail"),
            "query": query_result,
            "failure_reason": (
                f"Query pipeline failed: {query_result.get('failure_reason', 'unknown')}"
            ),
        }

    # Step 2 — Write the cited answer to raw/ with a query-derived provenance header.
    answer_text = query_result.get("output", "")
    slug = _make_query_slug(question, save_as)
    raw_dir = wiki_dir / "raw"
    raw_dir.mkdir(exist_ok=True)
    raw_file = raw_dir / slug

    today = datetime.date.today().isoformat()
    title = _make_query_title(question, save_as)

    # Escape any double-quotes in the question so the YAML frontmatter stays valid.
    safe_question = question.replace('"', '\\"')
    file_content = (
        f"---\n"
        f'title: "{title}"\n'
        f"source_type: query-derived-synthesis\n"
        f'source_question: "{safe_question}"\n'
        f"date: {today}\n"
        f"---\n"
        f"\n"
        f"<!--\n"
        f"SOURCE TYPE: query-derived synthesis\n"
        f"Filed back from a wiki query — NOT an external document.\n"
        f"The knowledge below originated from this wiki's own compiled content.\n"
        f"When ingest creates a sources/ page for this file, record this provenance\n"
        f"so the wiki does not present its own synthesis as fresh external evidence.\n"
        f"Originating question: {question}\n"
        f"Date filed: {today}\n"
        f"-->\n"
        f"\n"
        f"{answer_text}\n"
    )
    raw_file.write_text(file_content, encoding="utf-8")

    result: dict[str, Any] = {
        "query": query_result,
        "raw_file": str(raw_file),
    }

    if not run_ingest:
        result["status"] = "success"
        return result

    # Ingest the saved file — same code path as wiki-attractor ingest
    ingest_result = await ingest(wiki_dir, slug)
    result["ingest"] = ingest_result
    result["status"] = (
        "success"
        if ingest_result.get("status") in ("success", "completed")
        else "partial"
    )
    return result


# ---------------------------------------------------------------------------
# Batch / folder ingest.
# ---------------------------------------------------------------------------


async def ingest_folder(
    source_folder: str | Path,
    wiki_dir: str | Path,
    *,
    package: str = "wiki",
    brief: str = "knowledge base",
) -> dict[str, Any]:
    """Batch-ingest all supported prose files from a folder into a wiki.

    Walks *source_folder* recursively in sorted, deterministic order.  Each
    file is **triaged** (supported prose vs. unsupported code/binary) BEFORE
    any LLM work starts.  Unsupported files are **loudly reported** and
    skipped — never silently dropped and never silently mined as prose.

    If *wiki_dir* does not exist or is not yet initialized, a new wiki is
    scaffolded there first (using *package* and *brief*).  If it already is
    an initialized wiki, files are ingested additively into it.

    Each supported file is staged into ``raw/``, ingested through the full
    ingest pipeline (mine → write → reconcile → weave → verify), then
    archived automatically by the pipeline.  Files are processed
    **sequentially** in sorted order.

    The attractor checkpoint at ``/tmp/attractor-pipeline/checkpoint.json``
    is cleared before each ingest call so that sequential runs with different
    DOT graphs (different ``$source`` subs) do not hit a
    ``CheckpointMismatchError``.

    Args:
        source_folder: Path to a directory of raw source files.
        wiki_dir:      Path to the wiki repository root (created + initialized
                       if it does not exist).
        package:       Package directory name for the wiki (used only when
                       init is needed, e.g. ``team-knowledge``).
                       Default: ``"wiki"``.
        brief:         One-line domain brief for the wiki (used only when init
                       is needed, e.g. ``"product team strategy KB"``).
                       Default: ``"knowledge base"``.

    Returns:
        A summary dict with keys:

        ``status``
            ``"success"`` if all supported files were ingested,
            ``"partial"`` if some failed, ``"fail"`` if none succeeded.
        ``wiki_dir``
            Absolute path to the wiki repository root.
        ``total_files``
            Total files found in *source_folder* (all types combined).
        ``ingested``
            List of paths relative to *source_folder* for files ingested OK.
        ``skipped``
            List of ``{file, reason}`` dicts for unsupported files.
        ``failed``
            List of ``{file, error}`` dicts for files that errored.
        ``verify_status``
            First line of verify.sh output, e.g.
            ``"verify: clean (N page(s) checked)"``.

    Raises:
        ValueError: if *source_folder* is not a directory.
    """
    import subprocess  # noqa: PLC0415 (local import avoids always-importing subprocess)

    source_folder = Path(source_folder).resolve()
    wiki_dir = Path(wiki_dir).resolve()

    if not source_folder.is_dir():
        raise ValueError(f"source_folder is not a directory: {source_folder}")

    # ── Step 1: Walk + triage in deterministic order (no LLM yet) ────────────
    all_files: list[Path] = sorted(
        fp for fp in source_folder.rglob("*") if fp.is_file()
    )

    supported: list[Path] = []
    skipped: list[dict[str, str]] = []

    for fp in all_files:
        reason = _classify_file_path(fp)
        if reason is None:
            supported.append(fp)
        else:
            skipped.append(
                {
                    "file": str(fp.relative_to(source_folder)),
                    "reason": reason,
                }
            )

    # ── Step 2: Init wiki if not already initialized ──────────────────────────
    schema_path = wiki_dir / ".wiki" / "context" / "schema.md"
    if not schema_path.exists():
        init_result = await init(str(wiki_dir), package, brief)
        if init_result.get("status") not in ("success", "completed"):
            return {
                "status": "fail",
                "wiki_dir": str(wiki_dir),
                "total_files": len(all_files),
                "ingested": [],
                "skipped": skipped,
                "failed": [],
                "verify_status": "not run (init failed)",
                "failure_reason": (
                    "Wiki init failed: "
                    + str(init_result.get("failure_reason", "unknown"))
                ),
            }

    # ── Step 3: Ingest each supported file ────────────────────────────────────
    raw_dir = wiki_dir / "raw"
    raw_dir.mkdir(exist_ok=True)

    ingested: list[str] = []
    failed: list[dict[str, str]] = []

    for src_path in supported:
        # Resolve a unique staged filename in raw/ to avoid clobbering.
        # If a file with the same name already exists in raw/ or raw/archive/
        # (already in flight or already ingested), prepend an incrementing counter.
        base_name = src_path.name
        staged_name = base_name
        counter = 0
        while (raw_dir / staged_name).exists() or (
            raw_dir / "archive" / staged_name
        ).exists():
            counter += 1
            staged_name = f"{counter}-{base_name}"

        staged = raw_dir / staged_name
        try:
            staged.write_bytes(src_path.read_bytes())
        except OSError as exc:
            failed.append(
                {
                    "file": str(src_path.relative_to(source_folder)),
                    "error": f"Could not stage file in raw/: {exc}",
                }
            )
            continue

        # Clear any stale checkpoint from the previous pipeline run.
        # Sequential ingest() calls use the same DOT template with different
        # $source substitutions, giving different graph hashes — the attractor
        # engine rejects a mismatched checkpoint rather than silently
        # double-applying side-effecting nodes.
        _CHECKPOINT_PATH.unlink(missing_ok=True)

        try:
            result = await ingest(str(wiki_dir), staged_name)
            if result.get("status") in ("success", "completed"):
                ingested.append(str(src_path.relative_to(source_folder)))
            else:
                failed.append(
                    {
                        "file": str(src_path.relative_to(source_folder)),
                        "error": (
                            "ingest pipeline: "
                            + str(result.get("failure_reason", "unknown failure"))
                        ),
                    }
                )
                # Clean up the staged file if the pipeline did not archive it.
                if staged.exists():
                    staged.unlink(missing_ok=True)
        except ValueError as exc:
            failed.append(
                {
                    "file": str(src_path.relative_to(source_folder)),
                    "error": str(exc),
                }
            )
            if staged.exists():
                staged.unlink(missing_ok=True)

    # ── Step 4: Final verify.sh ───────────────────────────────────────────────
    verify_status = "not run"
    verify_sh = wiki_dir / ".wiki" / "scripts" / "verify.sh"
    if verify_sh.exists():
        try:
            r = subprocess.run(
                [str(verify_sh), package],
                cwd=wiki_dir,
                capture_output=True,
                text=True,
                timeout=120,
            )
            stdout = (r.stdout or "").strip()
            stderr = (r.stderr or "").strip()
            first_line = (stdout or stderr or "no output").split("\n")[0]
            verify_status = first_line
        except subprocess.TimeoutExpired:
            verify_status = "verify.sh timed out"
        except Exception as exc:  # noqa: BLE001
            verify_status = f"verify.sh error: {exc}"

    # ── Step 5: Summary ───────────────────────────────────────────────────────
    if not ingested and not failed:
        # Empty folder or all files were unsupported/skipped — nothing was ingested.
        # Return a distinct status so callers can detect this case without inspecting
        # the ingested/skipped lists.  "success" would be misleading here.
        overall_status = "no_supported_sources"
    elif failed:
        overall_status = "partial" if ingested else "fail"
    else:
        overall_status = "success"

    return {
        "status": overall_status,
        "wiki_dir": str(wiki_dir),
        "total_files": len(all_files),
        "ingested": ingested,
        "skipped": skipped,
        "failed": failed,
        "verify_status": verify_status,
    }
