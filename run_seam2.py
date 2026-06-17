#!/usr/bin/env python3
"""SEAM-2: prove amplifier-bundle-llm-wiki ORIENTATION composes into a box node.

Seam-1 proved a box node does real work in the real repo with tools (and reaches
the PROJECT-side schema by reading .wiki/context/schema.md). Seam-2 proves the
BUNDLE-side orientation (the 'why' lens) composes in via a custom child-agent
profile -- which it must do explicitly, because llm-wiki's context is mode-gated
and a pipeline activates no mode.

The box node answers two orientation questions WITHOUT tools; it can only do so if
the llm-wiki orientation is mounted in its system context.

Run: ~/.local/share/uv/tools/amplifier/bin/python attractor-wiki/run_seam2.py
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from amplifier_foundation import Bundle, load_bundle

import run_seam  # reuse register_spawn_capability, ATTRACTOR_BUNDLE, WIKI_DIR, CURRENT_MODEL

WIKI_AGENT = str(Path(__file__).resolve().parent / "wiki-agent-anthropic.yaml")

SEAM2_DOT = r"""
digraph WikiSeam2 {
    graph [goal="Prove llm-wiki orientation composes into a pipeline box node",
           default_fidelity="full"]
    start  [shape=Mdiamond]
    orient [llm_provider="anthropic", prompt="Answer Q1 and Q2 STRICTLY from your already-loaded system context / orientation. Do NOT use any tools for Q1 or Q2.\nQ1: Wiki-workflow orientation should be mounted in your context. State the rule it gives for what wins when the abstract LLM-wiki pattern and a project's specific schema seem to conflict.\nQ2: Per that orientation's three-zone convention, name the directory that is the shippable wiki content boundary, and the directory that holds operational scaffolding (schema + scripts).\nFinish with ONE non-empty plain-text final line: 'MATERIALS PASS' if you answered Q1 and Q2 from loaded context without using tools, otherwise 'MATERIALS FAIL: orientation not in my context'."]
    done   [shape=Msquare]
    start -> orient -> done
}
"""


async def main() -> int:
    print(f"[seam2] wiki-agent profile : {WIKI_AGENT}")
    print(f"[seam2] wiki repo cwd      : {run_seam.WIKI_DIR}")
    bundle = await load_bundle(run_seam.ATTRACTOR_BUNDLE)

    overlay = Bundle(
        name="wiki-seam2-run",
        session={"orchestrator": {"module": "loop-pipeline", "config": {
            "profiles": {"anthropic": "attractor-agent-anthropic",
                         "openai": "attractor-agent-openai",
                         "gemini": "attractor-agent-gemini"},
            "dot_source": SEAM2_DOT}}},
        # Override the anthropic child agent with our llm-wiki-composed profile.
        agents={"attractor-agent-anthropic": {"bundle": WIKI_AGENT}},
    )
    composed = bundle.compose(overlay)

    print("[seam2] prepare() ...")
    prepared = await composed.prepare()
    session = await prepared.create_session(session_cwd=run_seam.WIKI_DIR)
    run_seam.register_spawn_capability(session, prepared)

    print("[seam2] session.execute('Run the pipeline') ...\n")
    async with session:
        result = await session.execute("Run the pipeline")

    print("\n========== RESULT ==========")
    try:
        d = json.loads(result)
        print(f"status        : {d.get('status')}")
        print(f"node_statuses : {d.get('node_statuses')}")
        if d.get("failure_reason"):
            print(f"failure_reason: {d.get('failure_reason')}")
        print(f"notes         : {(d.get('notes') or '')[:700]}")
    except json.JSONDecodeError:
        print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
