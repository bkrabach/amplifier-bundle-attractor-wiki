#!/usr/bin/env python3
"""SEAM TEST (Step 0): prove an attractor pipeline box node can do real work
inside the team-knowledge-wiki repo, with tools, via the Path-B AmplifierSession API.

This is the thinnest provable slice of the proposed CLI -> lib -> AmplifierSession
-> .dot pipeline design. It deviates minimally from attractor's documented runnable
example (docs/APP-INTEGRATION-GUIDE.md): same Path-B triad, we only swap the DOT and
the session_cwd (the real wiki repo).

Run with the amplifier tool venv python (has amplifier_foundation):
  ~/.local/share/uv/tools/amplifier/bin/python attractor-wiki/run_seam.py
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from amplifier_foundation import Bundle, load_bundle
from amplifier_foundation.bundle import PreparedBundle
from amplifier_foundation.spawn_utils import ProviderPreference

ATTRACTOR_BUNDLE = (
    "git+https://github.com/microsoft/amplifier-bundle-attractor@main"
    "#subdirectory=bundles/attractor-pipeline.yaml"
)

WIKI_DIR = Path(__file__).resolve().parent.parent / "team-knowledge-wiki"

# The attractor bundle pins claude-sonnet-4-20250514, which retired 2026-06-15.
# Use the routing-matrix "latest sonnet" glob: the resolver matches it against the
# provider's live model list (sorted descending) and picks the newest, so it never
# pins a model that can retire out from under us.
CURRENT_MODEL = "claude-sonnet-*"

# A 1-LLM-node pipeline. The box node must reach the real repo with real tools:
# read the schema, run verify.sh, count pages -- then emit a non-empty PASS/FAIL line.
SEAM_DOT = r"""
digraph WikiSeam {
    graph [goal="Prove an attractor box node can do real work inside the team-knowledge wiki repo",
           default_fidelity="full"]

    start   [shape=Mdiamond]
    inspect [llm_provider="anthropic", prompt="You are running inside an LLM-Wiki repository; the current working directory IS the repo root. Do ALL of the following with your tools, then report:\n1. Read .wiki/context/schema.md and state the FOUR entity types and the THREE status enum values it defines.\n2. Run this exact shell command and report its EXACT stdout: bash .wiki/scripts/verify.sh\n3. Run: find team-knowledge -name '*.md' | wc -l   and report the page count.\nThen finish with ONE final line of plain text (your final assistant message must be NON-EMPTY plain text, not only tool calls): 'SEAM PASS' if step 2 printed a line beginning with 'verify: clean', otherwise 'SEAM FAIL: <one-line reason>'."]
    done    [shape=Msquare]

    start -> inspect -> done
}
"""


def register_spawn_capability(session: Any, prepared: PreparedBundle) -> None:
    """Wire session.spawn so pipeline LLM nodes get full child sessions with tools.

    Copied from amplifier-bundle-attractor/docs/APP-INTEGRATION-GUIDE.md (the
    documented reference impl). Without this, loop-pipeline silently falls back to
    the no-tools DirectProviderBackend -- which would make the seam test a false
    negative, so it is load-bearing.
    """

    async def spawn_capability(
        agent_name: str,
        instruction: str,
        parent_session: Any,
        agent_configs: dict[str, dict[str, Any]],
        sub_session_id: str | None = None,
        orchestrator_config: dict[str, Any] | None = None,
        parent_messages: list[dict[str, Any]] | None = None,
        provider_preferences: list | None = None,
        self_delegation_depth: int = 0,
        **kwargs: Any,
    ) -> dict[str, Any]:
        if agent_name in agent_configs:
            config = agent_configs[agent_name]
        elif agent_name in prepared.bundle.agents:
            config = prepared.bundle.agents[agent_name]
        else:
            available = list(agent_configs.keys()) + list(prepared.bundle.agents.keys())
            raise ValueError(f"Agent '{agent_name}' not found. Available: {available}")

        if "bundle" in config and len(config) == 1:
            ref = config["bundle"]
            # The standalone registry has no 'attractor:' namespace handler, so
            # rewrite namespace refs to resolvable git URLs before loading.
            if ref.startswith("attractor:"):
                sub = ref.split("attractor:", 1)[1]
                ref = (
                    "git+https://github.com/microsoft/amplifier-bundle-attractor@main"
                    f"#subdirectory={sub}.yaml"
                )
            child_bundle = await load_bundle(ref)
        else:
            child_bundle = Bundle(
                name=agent_name,
                version="1.0.0",
                session=config.get("session", {}),
                providers=config.get("providers", []),
                tools=config.get("tools", []),
                hooks=config.get("hooks", []),
                instruction=config.get("instruction")
                or config.get("system", {}).get("instruction"),
            )

        if not provider_preferences:
            provider_preferences = [ProviderPreference(provider="anthropic", model=CURRENT_MODEL)]
        return await prepared.spawn(
            child_bundle=child_bundle,
            instruction=instruction,
            session_id=sub_session_id,
            parent_session=parent_session,
            orchestrator_config=orchestrator_config,
            parent_messages=parent_messages,
            provider_preferences=provider_preferences,
            self_delegation_depth=self_delegation_depth,
        )

    session.coordinator.register_capability("session.spawn", spawn_capability)


async def main() -> int:
    print(f"[seam] wiki repo cwd : {WIKI_DIR}")
    assert (WIKI_DIR / ".wiki" / "scripts" / "verify.sh").exists(), "verify.sh missing"

    print("[seam] load_bundle(attractor-profile-anthropic) ...")
    bundle = await load_bundle(ATTRACTOR_BUNDLE)

    overlay = Bundle(
        name="wiki-seam-run",
        session={"orchestrator": {"module": "loop-pipeline",
                                  "config": {
                                      "profiles": {"anthropic": "attractor-agent-anthropic",
                                                   "openai": "attractor-agent-openai",
                                                   "gemini": "attractor-agent-gemini"},
                                      "dot_source": SEAM_DOT}}},
    )
    composed = bundle.compose(overlay)

    print("[seam] prepare() ...")
    prepared = await composed.prepare()

    print("[seam] create_session(cwd=wiki) + register_spawn ...")
    session = await prepared.create_session(session_cwd=WIKI_DIR)
    register_spawn_capability(session, prepared)

    print("[seam] session.execute('Run the pipeline') ...\n")
    async with session:
        result = await session.execute("Run the pipeline")

    print("\n========== RAW PIPELINE RESULT ==========")
    print(result)
    try:
        data = json.loads(result)
        print("\n========== PARSED ==========")
        print(f"status          : {data.get('status')}")
        print(f"nodes_completed : {data.get('nodes_completed')}")
        print(f"node_statuses   : {data.get('node_statuses')}")
        if data.get("failure_reason"):
            print(f"failure_reason  : {data.get('failure_reason')}")
        notes = data.get("notes") or ""
        print(f"notes           : {notes[:1200]}")
    except json.JSONDecodeError:
        print("[seam] (result was not JSON)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
