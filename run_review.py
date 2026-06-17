#!/usr/bin/env python3
"""HITL-REVIEW HARNESS: drive wiki-review.dot deterministically over a produced
flag-queue.json, proving the human-gate loop iterates items and applies decisions.

Why a DIRECT-ENGINE harness (not the session path like run_ingest.py): the standard
PipelineOrchestrator (session path) builds its HandlerContext WITHOUT an interviewer
(amplifier_module_loop_pipeline/__init__.py constructs HandlerContext(backend, hooks)
only), so a hexagon node run through it would raise "HumanGateHandler requires an
Interviewer". The supported way to drive gates non-interactively (per the attractor
test suite) is to build the PipelineEngine directly with a QueueInterviewer wired into
the HandlerContext. wiki-review.dot uses ONLY tool + diamond + hexagon nodes (no
codergen), so backend=None is sufficient — no provider keys, no spawn, no LLM calls.
The loop control is deterministic; the only "human" is the preset QueueInterviewer.

Usage:
  ~/.local/share/uv/tools/amplifier/bin/python attractor-wiki/run_review.py \
      <wiki_dir> <decisions>     # decisions e.g. "C,X,P,C"  (one per queue item)
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

from amplifier_module_loop_pipeline.context import PipelineContext
from amplifier_module_loop_pipeline.dot_parser import parse_dot
from amplifier_module_loop_pipeline.engine import PipelineEngine
from amplifier_module_loop_pipeline.handlers import HandlerRegistry
from amplifier_module_loop_pipeline.handlers.context import HandlerContext
from amplifier_module_loop_pipeline.interviewer import Answer, QueueInterviewer
from amplifier_module_loop_pipeline.transforms import apply_transforms
from amplifier_module_loop_pipeline.validation import validate_or_raise

HERE = Path(__file__).resolve().parent
DOT_FILE = HERE / "pipelines" / "wiki-review.dot"
HELPER = HERE / "review_queue.py"
PYBIN = sys.executable


async def main() -> int:
    if len(sys.argv) < 3:
        print("usage: run_review.py <wiki_dir> <decisions e.g. C,X,P>")
        return 2
    wiki = Path(sys.argv[1]).resolve()
    decisions = [d.strip().upper() for d in sys.argv[2].split(",") if d.strip()]

    assert (wiki / "team-knowledge" / "flag-queue.json").exists(), (
        "no flag-queue.json — run the reviewer-enabled ingest first"
    )

    # Substitute absolute helper paths into the dot (engine never sees $PYBIN/$HELPER).
    dot_text = DOT_FILE.read_text()
    dot_text = dot_text.replace("$PYBIN", PYBIN).replace("$HELPER", str(HELPER))
    assert "$PYBIN" not in dot_text and "$HELPER" not in dot_text

    # Preset human answers: one per queue item. The hexagon options use accelerator
    # keys C/X/P (from edge labels "[C]onfirm" / "[X] Correct" / "[P]romote"); the
    # handler maps Answer.value -> key -> label -> target node, so value="C" suffices.
    answers = [Answer(value=d) for d in decisions]
    interviewer = QueueInterviewer(answers)

    graph = parse_dot(dot_text)
    context = PipelineContext()
    apply_transforms(graph, context)
    validate_or_raise(graph)

    registry = HandlerRegistry(HandlerContext(interviewer=interviewer))
    logs_root = tempfile.mkdtemp(prefix="wiki-review-")
    engine = PipelineEngine(
        graph=graph,
        context=context,
        handler_registry=registry,
        logs_root=logs_root,
    )

    # Tool nodes inherit process cwd when context.target_dir/source_dir are unset.
    os.chdir(wiki)
    print(f"[review] wiki      : {wiki}")
    print(f"[review] decisions : {decisions}")
    print(f"[review] logs_root : {logs_root}\n")

    outcome = await engine.run()
    print("\n========== REVIEW RESULT ==========")
    print(f"status          : {outcome.status.value}")
    print(f"completed_nodes : {engine.completed_nodes}")
    if outcome.notes:
        print(f"notes           : {outcome.notes[:400]}")
    if getattr(outcome, "failure_reason", None):
        print(f"failure_reason  : {outcome.failure_reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
