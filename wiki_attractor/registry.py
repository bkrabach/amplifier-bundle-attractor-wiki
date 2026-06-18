#!/usr/bin/env python3
"""The pipeline registry -- the data-driven heart of the CLI.

Each entry maps a command name to its .dot pipeline, its executor kind, and the
user-supplied CLI arguments it injects into the DOT (as $placeholders). Adding a
new command later (step 4: init / lint / publish / query) is a DATA-ONLY change:
add a PipelineSpec here and drop a .dot in pipelines/ -- no new dispatch code, the
CLI builds the click command from the spec.

Executor kinds (see runner.py):
  "session" -- spins up an AmplifierSession; box (LLM) nodes spawn child sessions.
  "engine"  -- direct PipelineEngine with a human Interviewer; HITL, no LLM nodes.
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

    name: str  # click argument name, e.g. "source"
    placeholder: str  # DOT token replaced with the value, e.g. "$source"
    help: str


@dataclass(frozen=True)
class PipelineSpec:
    name: str
    dot: Path
    executor: str  # "session" | "engine"
    summary: str
    args: tuple[CliArg, ...] = field(default_factory=tuple)

    # --- two small, generic knobs the dispatch honors (see cli.py) ---
    # requires_wiki: gate that the target dir is an initialized wiki (has
    #   .wiki/context/schema.md). True for every command that operates on an
    #   EXISTING wiki; False ONLY for the bootstrap command (init), which runs
    #   on an empty dir and creates the wiki.
    requires_wiki: bool = True
    # asset_subs: placeholder -> packaged-asset relative path. The dispatch
    #   resolves each to an absolute path under wiki_attractor/assets/ and
    #   substitutes it into the DOT (same mechanism review uses for $HELPER).
    #   Lets a pipeline plant CANONICAL files (scripts) deterministically rather
    #   than have an LLM author them.
    asset_subs: tuple[tuple[str, str], ...] = field(default_factory=tuple)


REGISTRY: dict[str, PipelineSpec] = {
    "ingest": PipelineSpec(
        name="ingest",
        dot=PIPELINES_DIR / "wiki-ingest.dot",
        executor="session",
        summary="Ingest a source from raw/ into the wiki (mine -> write -> reconcile -> verify).",
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
        dot=PIPELINES_DIR / "wiki-review.dot",
        executor="engine",
        summary="Walk the flag-queue.json HITL: confirm / correct / promote each flagged claim.",
        args=(),
    ),
    "publish": PipelineSpec(
        name="publish",
        dot=PIPELINES_DIR / "wiki-publish.dot",
        executor="session",
        summary="Publish the wiki package via .wiki/scripts/publish.sh (zips to .wiki/dist/).",
        args=(),
    ),
    "lint": PipelineSpec(
        name="lint",
        dot=PIPELINES_DIR / "wiki-lint.dot",
        executor="session",
        summary="Read-only health check: run verify.sh + surface contradictions/stale/orphans/gaps to .wiki/lint-report.md.",
        args=(),
    ),
    "query": PipelineSpec(
        name="query",
        dot=PIPELINES_DIR / "wiki-query.dot",
        executor="session",
        summary="Read-only Q&A: index-first drill, cited answer written to .wiki/query-answer.md.",
        args=(
            CliArg(
                name="question",
                placeholder="$question",
                help="The question to answer against the wiki (e.g. 'what is Team Pulse?').",
            ),
        ),
    ),
    "init": PipelineSpec(
        name="init",
        dot=PIPELINES_DIR / "wiki-init.dot",
        executor="session",
        summary="Scaffold a NEW pure-markdown wiki (4-type schema): plant canonical scripts + author schema/backbone.",
        # The bootstrap command: runs on an EMPTY dir, so it skips the wiki guard
        # and plants the canonical hardened scripts from packaged assets.
        requires_wiki=False,
        asset_subs=(("$ASSETS", "."),),
        args=(
            CliArg(
                name="package",
                placeholder="$package",
                help="Package directory name for the new wiki (e.g. team-knowledge, kb, notes).",
            ),
            CliArg(
                name="brief",
                placeholder="$brief",
                help="One-line domain brief for the wiki (shapes the schema; e.g. 'product team strategy KB').",
            ),
        ),
    ),
}
