#!/usr/bin/env python3
"""PORTABILITY RE-PROOF: prove the VENDORED llm-wiki orientation composes into a
box node from a SIBLING-LESS companion copy.

This is the exact test that FAILED for the three cross-bundle context-ref forms
(namespace / @-namespace / git-URL context.include). It must now PASS with the
vendored files referenced by companion-relative path.

Setup invariant: the box node's cwd is the THROWAWAY test wiki, which contains NO
llm-wiki orientation files. The only copy of the orientation in the whole tree is
attractor-wiki/vendor/llm-wiki/ (a different subtree the node cannot relative-read
from the wiki cwd). So if the node answers the orientation questions, the content
came from its COMPOSED SYSTEM CONTEXT -- nothing else.

Run from inside the (possibly sibling-less) companion copy:
  ~/.local/share/uv/tools/amplifier/bin/python prove_orient.py <test_wiki_dir>
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from amplifier_foundation import Bundle, load_bundle

import run_seam  # reuse register_spawn_capability, ATTRACTOR_BUNDLE, CURRENT_MODEL

HERE = Path(__file__).resolve().parent
WIKI_AGENT = str(HERE / "wiki-agent-anthropic.yaml")
PROOF_FILE = "_orient_proof.txt"

ORIENT_DOT = r"""
digraph OrientProof {
    graph [goal="Prove vendored llm-wiki orientation composes into a box node",
           default_fidelity="full"]
    start  [shape=Mdiamond]
    orient [llm_provider="anthropic", prompt="Answer STRICTLY from your already-loaded system context / orientation. Do NOT read any files for the answers; the orientation should already be mounted in your context.\nQ1: The wiki-workflow orientation states a rule for what wins when the abstract LLM-wiki pattern and a project's specific schema seem to conflict. State that rule.\nQ2: Per that orientation's three-zone convention, name the directory that is the shippable wiki content boundary, and the directory that holds operational scaffolding (schema + scripts, NOT shipped).\nQ3: The orientation names two navigational-backbone records. Name both and the one-line job of each.\nThen use write_file ONCE to write your full answers to the file '_orient_proof.txt' in the current directory. Your FINAL plain-text line must be 'ORIENT PASS' if you answered Q1-Q3 from loaded context, or 'ORIENT FAIL: orientation not in my context' if the orientation was not present."]
    done   [shape=Msquare]
    start -> orient -> done
}
"""


async def main() -> int:
    if len(sys.argv) < 2:
        print("usage: prove_orient.py <test_wiki_dir>")
        return 2
    test_wiki = Path(sys.argv[1]).resolve()
    assert (test_wiki / ".wiki" / "context" / "schema.md").exists(), "not a wiki repo"
    # Invariant: NO orientation files in the wiki cwd (only the project schema).
    for stray in ("wiki-instructions.md", "llm-wiki-pattern.md"):
        hits = list(test_wiki.rglob(stray))
        assert not hits, f"orientation file present in wiki cwd (would invalidate proof): {hits}"

    print(f"[orient] companion : {HERE}")
    print(f"[orient] wiki cwd  : {test_wiki}")
    print(f"[orient] vendored  : {(HERE / 'vendor' / 'llm-wiki').exists()}")

    bundle = await load_bundle(run_seam.ATTRACTOR_BUNDLE)
    overlay = Bundle(
        name="orient-proof-run",
        session={"orchestrator": {"module": "loop-pipeline", "config": {
            "profiles": {"anthropic": "attractor-agent-anthropic",
                         "openai": "attractor-agent-openai",
                         "gemini": "attractor-agent-gemini"},
            "dot_source": ORIENT_DOT}}},
        agents={"attractor-agent-anthropic": {"bundle": WIKI_AGENT}},
    )
    composed = bundle.compose(overlay)
    prepared = await composed.prepare()
    session = await prepared.create_session(session_cwd=test_wiki)
    run_seam.register_spawn_capability(session, prepared)

    print("[orient] execute ...\n")
    async with session:
        result = await session.execute("Run the pipeline")

    print("\n========== RESULT ==========")
    try:
        d = json.loads(result)
        print(f"status        : {d.get('status')}")
        print(f"node_statuses : {d.get('node_statuses')}")
        if d.get("failure_reason"):
            print(f"failure_reason: {d.get('failure_reason')}")
        print(f"notes(200cap) : {(d.get('notes') or '')[:200]}")
    except json.JSONDecodeError:
        print(result)

    proof = test_wiki / PROOF_FILE
    print("\n========== VERBATIM BOX-NODE ANSWER (_orient_proof.txt) ==========")
    print(proof.read_text(encoding="utf-8") if proof.exists() else "(no proof file written)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
