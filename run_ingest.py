#!/usr/bin/env python3
"""INGEST PIPELINE RUN (milestone after seams 1 & 2): drive wiki-ingest.dot to
a GREEN end-to-end run against a THROWAWAY copy of a seeded wiki.

Proves a box node can MINE a source, WRITE wiki pages, and pass verify.sh, all
driven by the attractor pipeline (orient -> mine -> write_pages -> verify ->
verify_gate -> archive). Builds on the two proven seams:
  - Path-B lib wiring + spawn capability + sonnet glob  (run_seam.py)
  - llm-wiki-composed child agent override             (run_seam2.py / wiki-agent-anthropic.yaml)

NEVER point this at the real team-knowledge-wiki: an ingest run WRITES pages and
moves files. TEST_WIKI must be a throwaway copy under .amplifier/evaluation/.

$source injection: the dot uses $source in the goal, the mine prompt, and the
archive tool_command. Rather than rely on context seeding, we string-substitute
the real source filename into the dot text before running (the simplest robust
mechanism, endorsed by substitution.py's "absent key -> literal" caveat).

tool-node cwd: parallelogram nodes run subprocess with
  cwd = context.target_dir or graph.source_dir or None
Neither is set when we pass inline dot_source, so we os.chdir into the test wiki
before execute() — making the process cwd the wiki root for the deterministic
nodes. Box (codergen) nodes get the wiki via session_cwd explicitly.

Run: ~/.local/share/uv/tools/amplifier/bin/python attractor-wiki/run_ingest.py <test_wiki_dir> <source_filename>
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from amplifier_foundation import Bundle, load_bundle

import run_seam  # reuse register_spawn_capability, ATTRACTOR_BUNDLE, CURRENT_MODEL

HERE = Path(__file__).resolve().parent
WIKI_AGENT = str(HERE / "wiki-agent-anthropic.yaml")
DOT_FILE = HERE / "pipelines" / "wiki-ingest.dot"


async def main() -> int:
    if len(sys.argv) < 3:
        print("usage: run_ingest.py <test_wiki_dir> <source_filename>")
        return 2
    test_wiki = Path(sys.argv[1]).resolve()
    source_name = sys.argv[2]

    assert (test_wiki / ".wiki" / "context" / "schema.md").exists(), "not a wiki repo"
    assert (test_wiki / "raw" / source_name).exists(), f"source not in raw/: {source_name}"

    # $source injection — literal substitution into the whole dot text.
    dot_text = DOT_FILE.read_text()
    dot_text = dot_text.replace("$source", source_name)
    assert "$source" not in dot_text, "stray $source after substitution"

    print(f"[ingest] test wiki  : {test_wiki}")
    print(f"[ingest] source     : {source_name}")
    print(f"[ingest] dot        : {DOT_FILE}")

    bundle = await load_bundle(run_seam.ATTRACTOR_BUNDLE)

    overlay = Bundle(
        name="wiki-ingest-run",
        session={"orchestrator": {"module": "loop-pipeline", "config": {
            "profiles": {"anthropic": "attractor-agent-anthropic",
                         "openai": "attractor-agent-openai",
                         "gemini": "attractor-agent-gemini"},
            "dot_source": dot_text}}},
        # Override the anthropic child agent with the llm-wiki-composed profile.
        agents={"attractor-agent-anthropic": {"bundle": WIKI_AGENT}},
    )
    composed = bundle.compose(overlay)

    print("[ingest] prepare() ...")
    prepared = await composed.prepare()
    session = await prepared.create_session(session_cwd=test_wiki)
    run_seam.register_spawn_capability(session, prepared)

    # Make the test wiki the process cwd so deterministic (parallelogram) nodes,
    # whose subprocess cwd falls back to process cwd, run inside the wiki.
    os.chdir(test_wiki)

    print("[ingest] session.execute('Run the pipeline') ...\n")
    async with session:
        result = await session.execute("Run the pipeline")

    print("\n========== RAW PIPELINE RESULT ==========")
    print(result)
    try:
        d = json.loads(result)
        print("\n========== PARSED ==========")
        print(f"status          : {d.get('status')}")
        print(f"nodes_completed : {d.get('nodes_completed')}")
        print(f"node_statuses   : {d.get('node_statuses')}")
        if d.get("failure_reason"):
            print(f"failure_reason  : {d.get('failure_reason')}")
        print(f"notes           : {(d.get('notes') or '')[:1500]}")
    except json.JSONDecodeError:
        print("[ingest] (result was not JSON)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
