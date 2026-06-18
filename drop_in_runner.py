#!/usr/bin/env python3
"""Raw .dot drop-in runner — the THIRD consumer arm of the equivalence proof.

This script proves that query.dot works as a raw drop-in into a bare attractor
engine WITHOUT importing wiki_attractor. It mimics what any third-party consumer
(e.g. amplifier-resolver-dot-graph) would do: read the .dot file, substitute
$placeholders, spin up the attractor engine, and get the result.

KEY CONSTRAINT: this file MUST NOT import from wiki_attractor.
It uses the same underlying libraries (amplifier_foundation, loop-pipeline), but
implements the session spin-up inline — exactly as any drop-in consumer would.

The .dot files are the portable artifacts; the lib (runner.py) is one convenience
wrapper. This proves the dots work without that wrapper.

Run with:
  ~/.local/share/uv/tools/amplifier/bin/python drop_in_runner.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

# === STANDALONE CONSTANTS (copied from the attractor agent profiles — public knowledge) ===

ATTRACTOR_BUNDLE = (
    "git+https://github.com/microsoft/amplifier-bundle-attractor@main"
    "#subdirectory=bundles/attractor-pipeline.yaml"
)
CURRENT_MODEL = "claude-sonnet-*"
PROFILES_MAP = {
    "anthropic": "attractor-agent-anthropic",
    "openai": "attractor-agent-openai",
    "gemini": "attractor-agent-gemini",
}
# The wiki-agent child profile (part of the companion repo — publicly accessible).
# A true drop-in consumer would reference this by git URL; here we use local path
# since we're in the same repo, which is equivalent (same file content).
WIKI_AGENT_PROFILE = str(
    Path(__file__).resolve().parent / "wiki_attractor" / "profiles" / "wiki-agent-anthropic.yaml"
)


def _register_spawn(session, prepared):
    """Wire session.spawn — same logic any drop-in consumer would need."""
    from amplifier_foundation import Bundle, load_bundle  # noqa: PLC0415
    from amplifier_foundation.spawn_utils import ProviderPreference  # noqa: PLC0415

    async def spawn_capability(
        agent_name, instruction, parent_session, agent_configs,
        sub_session_id=None, orchestrator_config=None,
        parent_messages=None, provider_preferences=None,
        self_delegation_depth=0, **kwargs,
    ):
        if agent_name in agent_configs:
            config = agent_configs[agent_name]
        elif agent_name in prepared.bundle.agents:
            config = prepared.bundle.agents[agent_name]
        else:
            raise ValueError(f"Agent '{agent_name}' not found")

        if "bundle" in config and len(config) == 1:
            ref = config["bundle"]
            if ref.startswith("attractor:"):
                sub = ref.split("attractor:", 1)[1]
                ref = (
                    "git+https://github.com/microsoft/amplifier-bundle-attractor@main"
                    f"#subdirectory={sub}.yaml"
                )
            child_bundle = await load_bundle(ref)
        else:
            child_bundle = Bundle(
                name=agent_name, version="1.0.0",
                session=config.get("session", {}),
                providers=config.get("providers", []),
                tools=config.get("tools", []),
                hooks=config.get("hooks", []),
                instruction=config.get("instruction"),
            )

        if not provider_preferences:
            provider_preferences = [ProviderPreference(provider="anthropic", model=CURRENT_MODEL)]

        return await prepared.spawn(
            child_bundle=child_bundle, instruction=instruction,
            session_id=sub_session_id, parent_session=parent_session,
            orchestrator_config=orchestrator_config, parent_messages=parent_messages,
            provider_preferences=provider_preferences,
            self_delegation_depth=self_delegation_depth,
        )

    session.coordinator.register_capability("session.spawn", spawn_capability)


async def run_dot_dropin(dot_path: Path, wiki_dir: Path, subs: dict[str, str]) -> dict:
    """Run a .dot pipeline using a bare attractor engine — no wiki_attractor import."""
    from amplifier_foundation import Bundle, load_bundle  # noqa: PLC0415

    # Read the .dot and apply substitutions.
    dot_text = dot_path.read_text()
    for k, v in subs.items():
        dot_text = dot_text.replace(k, v)

    # Load the pipeline base bundle (the attractor engine itself).
    bundle = await load_bundle(ATTRACTOR_BUNDLE)

    # Compose: inject the DOT source + wiki-agent child mapping.
    overlay = Bundle(
        name="dropin-query",
        session={
            "orchestrator": {
                "module": "loop-pipeline",
                "config": {"profiles": PROFILES_MAP, "dot_source": dot_text},
            }
        },
        agents={"attractor-agent-anthropic": {"bundle": WIKI_AGENT_PROFILE}},
    )
    composed = bundle.compose(overlay)
    prepared = await composed.prepare()

    session = await prepared.create_session(session_cwd=wiki_dir)
    _register_spawn(session, prepared)

    os.chdir(wiki_dir)

    async with session:
        result = await session.execute("Run the pipeline")

    try:
        parsed = json.loads(result)
    except (json.JSONDecodeError, TypeError):
        parsed = {"status": "unknown", "raw": str(result)}

    # Read back the output file (query.dot writes to .wiki/query-answer.md).
    out_path = wiki_dir / ".wiki" / "query-answer.md"
    if out_path.exists() and parsed.get("status") in ("success", "completed"):
        parsed["output"] = out_path.read_text()

    return parsed


async def main() -> int:
    # The .dot file — referenced DIRECTLY by path, no wiki_attractor import.
    dot_path = Path(__file__).resolve().parent / "wiki_attractor" / "pipelines" / "query.dot"
    wiki_dir = Path("/home/bkrabach/dev/llm-wiki-pipeline/team-knowledge-wiki")
    question = "What is Team Pulse and what role does it play for the team?"

    assert dot_path.exists(), f"query.dot not found at {dot_path}"
    assert (wiki_dir / ".wiki" / "context" / "schema.md").exists(), "wiki_dir not an initialized wiki"

    print(f"[dropin] dot file  : {dot_path}")
    print(f"[dropin] wiki dir  : {wiki_dir}")
    print(f"[dropin] question  : {question}")
    print()

    # Clear checkpoint to avoid CheckpointMismatchError.
    chk = Path("/tmp/attractor-pipeline/checkpoint.json")
    try:
        chk.unlink()
    except FileNotFoundError:
        pass

    result = await run_dot_dropin(dot_path, wiki_dir, subs={"$question": question})

    print()
    print("=" * 60)
    print("RAW .DOT DROP-IN — RESULT")
    print("=" * 60)
    print(f"status         : {result.get('status')}")
    if result.get("node_statuses"):
        print(f"node_statuses  : {result.get('node_statuses')}")

    output = result.get("output")
    if output:
        print()
        print("---------- OUTPUT ----------")
        print(output[:2000])
        print("----------------------------")

    success = result.get("status") in ("success", "completed")
    print(f"\nVERDICT: {'DROP_IN_PROVEN' if success else 'NOT PROVEN'}")
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
