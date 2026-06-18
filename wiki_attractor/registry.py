#!/usr/bin/env python3
"""The pipeline registry -- the data-driven heart of the CLI.

Each entry maps a command name to its .dot pipeline, its executor kind, and the
user-supplied CLI arguments it injects into the DOT (as $placeholders). Adding a
new pipeline later is a DATA-ONLY change: one PipelineSpec here + one .dot file.
No new dispatch code needed.

Executor kinds (see runner.py):
  "session" -- spins up an AmplifierSession; box (LLM) nodes spawn child sessions.
  "engine"  -- direct PipelineEngine with a human Interviewer; HITL, no LLM nodes.

output_file: optional relative path (within wiki_dir) the lib reads back after a
  successful run and returns as result["output"]. Used by pipelines whose real
  output exceeds the 200-char node-record truncation (e.g. query writes the
  full cited answer to .wiki/query-answer.md).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

_PKG = Path(__file__).resolve().parent
PIPELINES_DIR = _PKG / "pipelines"
ASSETS_DIR = _PKG / "assets"


@dataclass(frozen=True)
class CliArg:
    """A positional CLI argument injected into the DOT as a $placeholder."""

    name: str          # click argument name, e.g. "source"
    placeholder: str   # DOT token replaced with the value, e.g. "$source"
    help: str


@dataclass(frozen=True)
class PipelineSpec:
    name: str
    dot: Path
    executor: str      # "session" | "engine"
    summary: str
    args: tuple[CliArg, ...] = field(default_factory=tuple)

    # requires_wiki: gate that the target dir is an initialized wiki (has
    #   .wiki/context/schema.md). False ONLY for init, which runs on an empty dir.
    requires_wiki: bool = True

    # asset_subs: placeholder -> packaged-asset relative path. Resolved to
    #   absolute paths under wiki_attractor/assets/ and substituted into the DOT.
    #   Lets a pipeline plant canonical files (scripts) deterministically.
    asset_subs: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    # output_file: optional path relative to wiki_dir that the lib reads back
    #   after a successful run and returns as result["output"]. Use for pipelines
    #   whose real output exceeds the 200-char node-record truncation.
    output_file: str | None = None


REGISTRY: dict[str, PipelineSpec] = {
    "ingest": PipelineSpec(
        name="ingest",
        dot=PIPELINES_DIR / "ingest.dot",
        executor="session",
        summary=(
            "Ingest a source from raw/ into the wiki "
            "(mine -> write -> reconcile -> verify)."
        ),
        args=(
            CliArg(
                name="source",
                placeholder="$source",
                help="Filename in raw/ to ingest (e.g. 2026-06-16-call.md).",
            ),
        ),
    ),
    "review": PipelineSpec(
        name="review",
        dot=PIPELINES_DIR / "review.dot",
        executor="engine",
        summary="Walk the flag-queue.json HITL: confirm / correct / promote each flagged claim.",
        args=(),
    ),
    "publish": PipelineSpec(
        name="publish",
        dot=PIPELINES_DIR / "publish.dot",
        executor="session",
        summary="Publish the wiki package via .wiki/scripts/publish.sh (zips to .wiki/dist/).",
        args=(),
    ),
    "lint": PipelineSpec(
        name="lint",
        dot=PIPELINES_DIR / "lint.dot",
        executor="session",
        summary=(
            "Read-only health check: run verify.sh + surface "
            "contradictions/stale/orphans/gaps to .wiki/lint-report.md."
        ),
        output_file=".wiki/lint-report.md",
    ),
    "query": PipelineSpec(
        name="query",
        dot=PIPELINES_DIR / "query.dot",
        executor="session",
        summary="Read-only Q&A: index-first drill, cited answer returned to caller.",
        args=(
            CliArg(
                name="question",
                placeholder="$question",
                help="The question to answer against the wiki.",
            ),
        ),
        output_file=".wiki/query-answer.md",
    ),
    "init": PipelineSpec(
        name="init",
        dot=PIPELINES_DIR / "init.dot",
        executor="session",
        summary=(
            "Scaffold a NEW pure-markdown wiki (4-type schema): "
            "plant canonical scripts + author schema/backbone."
        ),
        requires_wiki=False,
        asset_subs=(("$ASSETS", "."),),
        args=(
            CliArg(
                name="package",
                placeholder="$package",
                help="Package directory name for the new wiki (e.g. team-knowledge, kb).",
            ),
            CliArg(
                name="brief",
                placeholder="$brief",
                help="One-line domain brief for the wiki (e.g. 'product team strategy KB').",
            ),
        ),
    ),
}
