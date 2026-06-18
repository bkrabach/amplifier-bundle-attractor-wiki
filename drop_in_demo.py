#!/usr/bin/env python3
"""Drop-in portability demo: runs a renamed attractor-wiki .dot directly via the
attractor PipelineEngine WITHOUT importing wiki_attractor (no cli, no registry).

This simulates a consumer (e.g. amplifier-resolver-dot-graph) that takes an
attractor-wiki .dot file, drops it into their own runner, and executes it.
This script proves the .dot files are PORTABLE — no dependency on wiki_attractor.

Two paths demonstrated:
  A (deterministic): publish.dot via PipelineEngine(backend=None)
      Parallelogram nodes are pure shell; no LLM needed. Completes in <5s.
  B (LLM / Path A): query.dot via PipelineEngine(backend=DirectProviderBackend)
      Box nodes make direct LLM calls (no filesystem tools). Proves LLM dots
      are also portable; for full filesystem-tool quality use AmplifierSession.

Usage:
  python drop_in_demo.py publish <wiki_dir>
  python drop_in_demo.py query   <wiki_dir> "what is Team Pulse?"
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# NO import from wiki_attractor — only attractor engine + foundation primitives.
# ---------------------------------------------------------------------------
from amplifier_module_loop_pipeline.context import PipelineContext
from amplifier_module_loop_pipeline.dot_parser import parse_dot
from amplifier_module_loop_pipeline.engine import PipelineEngine
from amplifier_module_loop_pipeline.handlers import HandlerRegistry
from amplifier_module_loop_pipeline.transforms import apply_transforms
from amplifier_module_loop_pipeline.validation import validate_or_raise


def _apply_subs(text: str, subs: dict[str, str]) -> str:
    for k, v in subs.items():
        text = text.replace(k, v)
    return text


async def run_dot_bare_deterministic(dot_file: Path, wiki_dir: Path) -> dict:
    """Run a deterministic (no-LLM) .dot via PipelineEngine(backend=None).

    Parallelogram (tool/shell) nodes execute as real shell commands.
    This is the fastest proof of portability; no provider key needed.
    """
    wiki_dir = Path(wiki_dir).resolve()
    dot_text = dot_file.read_text()

    graph = parse_dot(dot_text)
    ctx = PipelineContext()
    apply_transforms(graph, ctx)
    validate_or_raise(graph)

    # backend=None → tool nodes run as shell; LLM nodes run in simulation mode.
    # publish.dot has no LLM nodes, so this path is fully real.
    from amplifier_module_loop_pipeline.handlers.context import HandlerContext
    registry = HandlerRegistry(HandlerContext(backend=None))
    logs_root = tempfile.mkdtemp(prefix="drop-in-pub-")
    engine = PipelineEngine(graph=graph, context=ctx,
                            handler_registry=registry, logs_root=logs_root)

    os.chdir(wiki_dir)
    outcome = await engine.run()

    return {
        "status": outcome.status.value,
        "notes": getattr(outcome, "notes", None),
        "failure_reason": getattr(outcome, "failure_reason", None),
        "logs_root": logs_root,
    }


async def run_dot_bare_llm(dot_file: Path, wiki_dir: Path, subs: dict) -> dict:
    """Run a box-node (LLM) .dot via DirectProviderBackend.

    Box nodes make direct LLM calls (no filesystem tools — this is Path A).
    Proves the dot is engine-portable. For full-quality execution with tools,
    use AmplifierSession (Path B, as wiki_attractor/runner.py does).
    """
    from amplifier_module_loop_pipeline import DirectProviderBackend

    wiki_dir = Path(wiki_dir).resolve()
    dot_text = _apply_subs(dot_file.read_text(), subs)

    graph = parse_dot(dot_text)
    ctx = PipelineContext()
    apply_transforms(graph, ctx)
    validate_or_raise(graph)

    from amplifier_module_loop_pipeline.handlers.context import HandlerContext

    # provider=None → auto-creates unified_llm.Client from env vars.
    backend = DirectProviderBackend(provider=None)
    registry = HandlerRegistry(HandlerContext(backend=backend))
    logs_root = tempfile.mkdtemp(prefix="drop-in-llm-")
    engine = PipelineEngine(graph=graph, context=ctx,
                            handler_registry=registry, logs_root=logs_root)

    os.chdir(wiki_dir)
    outcome = await engine.run()

    return {
        "status": outcome.status.value,
        "notes": getattr(outcome, "notes", None),
        "failure_reason": getattr(outcome, "failure_reason", None),
        "logs_root": logs_root,
    }


def main() -> None:
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]
    wiki_dir = Path(sys.argv[2])
    question = sys.argv[3] if len(sys.argv) > 3 else "what is Team Pulse?"

    _PKG = Path(__file__).resolve().parent / "wiki_attractor" / "pipelines"

    print("[drop-in] Imports: amplifier_module_loop_pipeline only — NO wiki_attractor")

    if command == "publish":
        dot_file = _PKG / "publish.dot"
        print(f"[drop-in] dot   : {dot_file.name}  (deterministic, no LLM)")
        print(f"[drop-in] wiki  : {wiki_dir}")
        print()
        result = asyncio.run(run_dot_bare_deterministic(dot_file, wiki_dir))
    elif command == "query":
        dot_file = _PKG / "query.dot"
        print(f"[drop-in] dot   : {dot_file.name}  (LLM, DirectProviderBackend/Path A)")
        print(f"[drop-in] wiki  : {wiki_dir}")
        print(f"[drop-in] subs  : {{$question = {question!r}}}")
        print()
        result = asyncio.run(run_dot_bare_llm(dot_file, wiki_dir, {"$question": question}))
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)

    print("========== DROP-IN RESULT ==========")
    print(f"status          : {result['status']}")
    if result.get("notes"):
        print(f"notes           : {str(result['notes'])[:500]}")
    if result.get("failure_reason"):
        print(f"failure_reason  : {result['failure_reason']}")
    print()
    print(f"PROOF: {dot_file.name} executed via bare PipelineEngine — no wiki_attractor imported.")


if __name__ == "__main__":
    main()
