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
}
