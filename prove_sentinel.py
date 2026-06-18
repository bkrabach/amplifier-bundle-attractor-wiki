#!/usr/bin/env python3
"""Decisive disambiguation: can a box node echo an UN-GUESSABLE sentinel that
exists ONLY in the vendored orientation? If yes -> orientation IS in the child's
context. If no -> it is NOT (the real gap), and the earlier wrong answers were
confabulation, not a loaded-but-ignored file."""
from __future__ import annotations
import asyncio, json, sys
from pathlib import Path
from amplifier_foundation import Bundle, load_bundle
import run_seam

HERE = Path(__file__).resolve().parent
WIKI_AGENT = str(HERE / "wiki-agent-anthropic.yaml")

DOT = r"""
digraph Sentinel {
    graph [goal="Echo the orientation sentinel", default_fidelity="full"]
    start  [shape=Mdiamond]
    echo   [llm_provider="anthropic", prompt="Do NOT use any tools. Your mounted orientation context contains a line labeled 'LOAD-CHECK SENTINEL:' followed by a token. Reply with ONLY that exact token on one line. If your context contains no such sentinel line, reply with exactly 'NO-SENTINEL-IN-CONTEXT'."]
    done   [shape=Msquare]
    start -> echo -> done
}
"""

async def main() -> int:
    test_wiki = Path(sys.argv[1]).resolve()
    bundle = await load_bundle(run_seam.ATTRACTOR_BUNDLE)
    overlay = Bundle(name="sentinel-run",
        session={"orchestrator": {"module": "loop-pipeline", "config": {
            "profiles": {"anthropic": "attractor-agent-anthropic",
                         "openai": "attractor-agent-openai",
                         "gemini": "attractor-agent-gemini"},
            "dot_source": DOT}}},
        agents={"attractor-agent-anthropic": {"bundle": WIKI_AGENT}})
    composed = bundle.compose(overlay)
    prepared = await composed.prepare()
    session = await prepared.create_session(session_cwd=test_wiki)
    run_seam.register_spawn_capability(session, prepared)
    async with session:
        result = await session.execute("Run the pipeline")
    try:
        d = json.loads(result)
        print(f"status: {d.get('status')}  node_statuses: {d.get('node_statuses')}")
        print(f"NOTES: {(d.get('notes') or '')[:300]}")
    except json.JSONDecodeError:
        print(result)
    return 0

if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
