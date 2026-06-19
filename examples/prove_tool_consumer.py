#!/usr/bin/env python3
"""Prove the tool-module consumer works inside a real AmplifierSession.

WHAT THIS PROVES:
  1. wiki tool-module mounts via coordinator.mount() (Iron Law: protocol compliance)
  2. An AmplifierSession agent can call wiki_query as a tool
  3. wiki_query executes (calls run_pipeline internally) and the answer comes
     back through the tool result to the agent

ARCHITECTURE:
  We load attractor-agent-anthropic (loop-agent orchestrator) + mount the wiki
  tool-module on top. The session IS the agent. The agent calls wiki_query,
  which internally spins up a child session (run_pipeline) to run query.dot.
  The cited answer returns as the tool result.

Run with:
  ~/.local/share/uv/tools/amplifier/bin/python examples/prove_tool_consumer.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

WIKI_DIR = Path("/home/bkrabach/dev/llm-wiki-pipeline/team-knowledge-wiki")
QUESTION = "What is Team Pulse and what role does it play for the team?"

# Use the wiki-agent child profile directly (loop-agent + filesystem/bash/search tools).
# This is the same profile our pipelines use for child sessions.
# This file is in examples/; the profile is in ../wiki_attractor/profiles/
WIKI_AGENT_BUNDLE = str(
    Path(__file__).resolve().parent.parent
    / "wiki_attractor"
    / "profiles"
    / "wiki-agent-anthropic.yaml"
)

# Model glob: self-tracks latest sonnet via routing-matrix pattern.
CURRENT_MODEL = "claude-sonnet-*"


async def main() -> int:
    from amplifier_foundation import load_bundle
    import amplifier_module_tool_wiki  # noqa: PLC0415

    print("[proof] loading wiki-agent-anthropic profile...")
    bundle = await load_bundle(WIKI_AGENT_BUNDLE)

    print("[proof] prepare()...")
    prepared = await bundle.prepare()

    print("[proof] create_session()...")
    session = await prepared.create_session(session_cwd=WIKI_DIR)

    # === KEY STEP: Mount the wiki tool-module directly on this session's coordinator ===
    # This is exactly what foundation does when a bundle specifies tools: [tool-wiki].
    print("[proof] mounting wiki tool-module onto coordinator...")
    mount_result = await amplifier_module_tool_wiki.mount(session.coordinator)
    print(f"[proof] mount result: {mount_result}")
    print(f"[proof] tools mounted: {mount_result.get('provides', [])}")

    prompt = (
        f"You have a wiki_query tool available. Call it now with:\n"
        f"  wiki_dir: {WIKI_DIR}\n"
        f"  question: {QUESTION}\n\n"
        f"You MUST invoke the wiki_query tool — do not answer from memory. "
        f"After getting the tool result, summarize the answer in 2-3 sentences "
        f"and confirm: TOOL_CONSUMER_PROVEN"
    )

    os.chdir(WIKI_DIR)

    print("[proof] executing agent session (agent will call wiki_query tool)...")
    async with session:
        result = await session.execute(prompt)

    result_str = str(result)

    print()
    print("=" * 60)
    print("TOOL CONSUMER PROOF — RESULT")
    print("=" * 60)
    print("raw result (first 1000 chars):")
    print(result_str[:1000])
    print()

    proven = (
        "TOOL_CONSUMER_PROVEN" in result_str.upper()
        or "team pulse" in result_str.lower()
    )
    print(
        f"VERDICT: {'TOOL_CONSUMER_PROVEN' if proven else 'NOT PROVEN (check output above)'}"
    )
    return 0 if proven else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
