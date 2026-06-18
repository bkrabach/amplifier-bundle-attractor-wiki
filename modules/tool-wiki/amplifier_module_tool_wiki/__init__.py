"""Amplifier tool module: wiki-attractor commands as mountable tools.

Registers 6 tools — one per wiki-attractor command — that an AmplifierSession
agent can invoke. Each tool is a thin wrapper:

  tool.execute(input_data)
    → calls wiki_attractor.runner.run_pipeline(dot_path, wiki_dir, subs, ...)
    → returns ToolResult(success=..., output=<answer/status>)

All real work lives in the .dot files (inside wiki_attractor/pipelines/).
This module adds NO logic beyond mapping tool arguments to run_pipeline args.

The Iron Law (creating-amplifier-modules skill): mount() MUST call
coordinator.mount() for each tool, or protocol_compliance validation fails.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

from amplifier_core import ToolResult

# wiki_attractor is the companion package (installed editably in the same venv).
from wiki_attractor import runner
from wiki_attractor.registry import REGISTRY

logger = logging.getLogger(__name__)

_PKG = Path(__file__).resolve().parent

# Paths the review pipeline needs substituted into the DOT.
_WIKI_ATTRACTOR_PKG = Path(runner.__file__).resolve().parent
_REVIEW_HELPER = _WIKI_ATTRACTOR_PKG / "review_queue.py"


# ---------------------------------------------------------------------------
# Shared thin helper — the ONLY logic in this module.
# ---------------------------------------------------------------------------


async def _run(spec_name: str, wiki_dir: str, subs: dict[str, str] | None = None,
               *, output_file: str | None = None, interviewer: Any | None = None) -> ToolResult:
    """Call run_pipeline for the named spec and return a ToolResult.

    This is the one shared helper that all 6 tool classes call. It directly
    awaits runner.run_pipeline so there is no nested asyncio.run().
    """
    spec = REGISTRY[spec_name]
    result = await runner.run_pipeline(
        dot_path=spec.dot,
        wiki_dir=Path(wiki_dir).resolve(),
        subs=subs,
        interviewer=interviewer,
        output_file=output_file if output_file is not None else spec.output_file,
    )
    status = result.get("status", "unknown")
    success = status in ("success", "completed")
    output = result.get("output") or result.get("notes") or str(result)
    return ToolResult(success=success, output=str(output)[:8000])


# ---------------------------------------------------------------------------
# Tool classes — one per command. Each is 3-8 lines of real code.
# ---------------------------------------------------------------------------


class WikiIngestTool:
    """Ingest a source from raw/ into the wiki (mine → write → reconcile → verify)."""

    @property
    def name(self) -> str:
        return "wiki_ingest"

    @property
    def description(self) -> str:
        return (
            "Ingest a source document from the wiki's raw/ inbox into the compiled wiki. "
            "Mines the source, writes entity pages, runs reconciliation to prevent duplicates, "
            "and verifies the result with verify.sh. Pass the filename (not the full path) "
            "of the file already present in raw/. The wiki must be initialized first."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "wiki_dir": {
                    "type": "string",
                    "description": "Absolute path to the wiki repository root.",
                },
                "source": {
                    "type": "string",
                    "description": "Filename in raw/ to ingest (e.g. 2026-06-20-call.md).",
                },
            },
            "required": ["wiki_dir", "source"],
        }

    async def execute(self, input_data: dict[str, Any]) -> ToolResult:
        return await _run(
            "ingest",
            input_data["wiki_dir"],
            subs={"$source": input_data["source"]},
        )


class WikiQueryTool:
    """Read-only Q&A against the compiled wiki (index-first, cited answer)."""

    @property
    def name(self) -> str:
        return "wiki_query"

    @property
    def description(self) -> str:
        return (
            "Answer a question against the compiled wiki using index-first navigation "
            "and returning a cited answer where every claim references the wiki page it "
            "came from. READ-ONLY: does not modify the wiki package. Returns the full "
            "cited answer text. Pass plain questions without embedded double-quotes."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "wiki_dir": {
                    "type": "string",
                    "description": "Absolute path to the wiki repository root.",
                },
                "question": {
                    "type": "string",
                    "description": "The question to answer against the wiki.",
                },
            },
            "required": ["wiki_dir", "question"],
        }

    async def execute(self, input_data: dict[str, Any]) -> ToolResult:
        return await _run(
            "query",
            input_data["wiki_dir"],
            subs={"$question": input_data["question"]},
        )


class WikiLintTool:
    """Read-only health check: verify.sh + surface contradictions/orphans/stale."""

    @property
    def name(self) -> str:
        return "wiki_lint"

    @property
    def description(self) -> str:
        return (
            "Run a read-only health check on the wiki: runs verify.sh (frontmatter, "
            "enums, sources resolution, duplicate titles, orphan pages) and surfaces "
            "structural issues, contradictions, and stale cross-refs. Returns the full "
            "lint report. Does NOT modify the wiki package."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "wiki_dir": {
                    "type": "string",
                    "description": "Absolute path to the wiki repository root.",
                },
            },
            "required": ["wiki_dir"],
        }

    async def execute(self, input_data: dict[str, Any]) -> ToolResult:
        return await _run("lint", input_data["wiki_dir"])


class WikiPublishTool:
    """Publish the wiki package via .wiki/scripts/publish.sh (zips to .wiki/dist/)."""

    @property
    def name(self) -> str:
        return "wiki_publish"

    @property
    def description(self) -> str:
        return (
            "Publish the wiki package by running .wiki/scripts/publish.sh, which zips "
            "the package directory to .wiki/dist/. Fails loud if the publish script is "
            "missing. Returns the publish status and what was written."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "wiki_dir": {
                    "type": "string",
                    "description": "Absolute path to the wiki repository root.",
                },
            },
            "required": ["wiki_dir"],
        }

    async def execute(self, input_data: dict[str, Any]) -> ToolResult:
        return await _run("publish", input_data["wiki_dir"])


class WikiInitTool:
    """Scaffold a new pure-markdown wiki repo with 4-type schema."""

    @property
    def name(self) -> str:
        return "wiki_init"

    @property
    def description(self) -> str:
        return (
            "Scaffold a new wiki repository: plants the canonical verify.sh and "
            "publish.sh scripts, authors the project-specific schema.md, and creates "
            "the backbone pages (overview.md, index.md, open-questions.md). Designed "
            "for 4-type pure-markdown schemas (outcome/concept/person/source). "
            "Run from the intended wiki directory (wiki_dir must be an empty or new dir)."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "wiki_dir": {
                    "type": "string",
                    "description": "Absolute path to the (new) wiki repository root.",
                },
                "package": {
                    "type": "string",
                    "description": "Package directory name for the wiki (e.g. team-knowledge, kb).",
                },
                "brief": {
                    "type": "string",
                    "description": "One-line domain brief describing the wiki (e.g. 'product team strategy KB').",
                },
            },
            "required": ["wiki_dir", "package", "brief"],
        }

    async def execute(self, input_data: dict[str, Any]) -> ToolResult:
        from wiki_attractor.registry import ASSETS_DIR  # noqa: PLC0415

        subs = {
            "$package": input_data["package"],
            "$brief": input_data["brief"],
            "$ASSETS": str(ASSETS_DIR.resolve()),
        }
        return await _run("init", input_data["wiki_dir"], subs=subs)


class WikiReviewTool:
    """Walk the flag-queue.json headlessly: auto-confirm or accept explicit decisions."""

    @property
    def name(self) -> str:
        return "wiki_review"

    @property
    def description(self) -> str:
        return (
            "Walk the wiki's flag-queue.json (produced by wiki_ingest's provenance audit) "
            "and apply a resolution to each flagged claim. By default, all flags are "
            "CONFIRMED (kept as TODO-VERIFY markers — the safest headless choice). Pass "
            "decisions as a comma-separated string of C/X/P per item to override: "
            "C=Confirm (keep flag), X=Correct (remove flag), P=Promote (verify + settle). "
            "Requires flag-queue.json to exist (run wiki_ingest first)."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "wiki_dir": {
                    "type": "string",
                    "description": "Absolute path to the wiki repository root.",
                },
                "decisions": {
                    "type": "string",
                    "description": (
                        "Optional comma-separated C/X/P decisions, one per queue item "
                        "(e.g. 'C,X,P'). If omitted, all flags are auto-confirmed (C)."
                    ),
                },
            },
            "required": ["wiki_dir"],
        }

    async def execute(self, input_data: dict[str, Any]) -> ToolResult:
        import json  # noqa: PLC0415

        from amplifier_module_loop_pipeline.interviewer import (  # noqa: PLC0415
            Answer,
            QueueInterviewer,
        )

        wiki_dir = Path(input_data["wiki_dir"]).resolve()

        # Determine queue length to build a full-length auto-confirm list if needed.
        queue_path = wiki_dir / "team-knowledge" / "flag-queue.json"
        if not queue_path.exists():
            return ToolResult(
                success=False,
                output=(
                    "flag-queue.json not found. Run wiki_ingest first so the "
                    "provenance audit node emits the queue."
                ),
            )

        try:
            queue = json.loads(queue_path.read_text())
        except Exception as exc:  # noqa: BLE001
            return ToolResult(success=False, output=f"Could not read flag-queue.json: {exc}")

        decisions_str = input_data.get("decisions", "")
        if decisions_str:
            picks = [d.strip().upper() for d in decisions_str.split(",") if d.strip()]
        else:
            # Default: confirm all (keep every TODO-VERIFY flag — the safe headless choice).
            picks = ["C"] * len(queue)

        interviewer = QueueInterviewer([Answer(value=d) for d in picks])
        subs = {"$PYBIN": sys.executable, "$HELPER": str(_REVIEW_HELPER)}

        return await _run("review", str(wiki_dir), subs=subs, interviewer=interviewer)


# ---------------------------------------------------------------------------
# mount() — THE required entry point. Iron Law: must call coordinator.mount()
# for every tool, or protocol_compliance validation fails.
# ---------------------------------------------------------------------------

_TOOLS = [
    WikiIngestTool(),
    WikiQueryTool(),
    WikiLintTool(),
    WikiPublishTool(),
    WikiInitTool(),
    WikiReviewTool(),
]


async def mount(coordinator: Any, config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Mount all 6 wiki tools into the coordinator.

    Satisfies the Iron Law: calls coordinator.mount() for each tool.
    """
    for tool in _TOOLS:
        await coordinator.mount("tools", tool, name=tool.name)
        logger.debug("tool-wiki: mounted '%s'", tool.name)

    names = [t.name for t in _TOOLS]
    logger.info("tool-wiki: mounted %d tools: %s", len(names), names)
    return {
        "name": "tool-wiki",
        "version": "0.1.0",
        "provides": names,
    }
