#!/usr/bin/env python3
"""The light AmplifierSession spin-up for running attractor pipelines.

PUBLIC API — one entry point:

  run_pipeline(dot_path, wiki_dir, subs, *, interviewer, output_file) → result dict

That is the ONLY function the CLI and (later) tool-modules need. Everything
else is private plumbing. The real work lives in the .dot files; this module
is ONLY responsible for standing up the attractor engine and handing it a
populated DOT string.

Two internal paths:
  _run_session_pipeline  — Path-B AmplifierSession; LLM box nodes with tools.
  _run_engine_pipeline   — direct PipelineEngine; HITL tool/diamond/hexagon.

Run only with the amplifier tool venv python (has amplifier_foundation):
  ~/.local/share/uv/tools/amplifier/bin/python
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants proven by the spikes.
# ---------------------------------------------------------------------------

ATTRACTOR_BUNDLE = (
    "git+https://github.com/microsoft/amplifier-bundle-attractor@main"
    "#subdirectory=bundles/attractor-pipeline.yaml"
)

# The routing-matrix "latest sonnet" glob: the resolver matches it against the
# provider's live model list (sorted descending) and picks the newest — never
# pins a retired model.
CURRENT_MODEL = "claude-sonnet-*"

PROFILES_MAP = {
    "anthropic": "attractor-agent-anthropic",
    "openai": "attractor-agent-openai",
    "gemini": "attractor-agent-gemini",
}

_PKG = Path(__file__).resolve().parent
# The wiki-agent child profile (schema-driven; portable via git-URL include).
WIKI_AGENT_PROFILE = _PKG / "profiles" / "wiki-agent-anthropic.yaml"


def _apply_subs(dot_text: str, subs: dict[str, str] | None) -> str:
    """Literal placeholder substitution into the DOT text before the engine sees it."""
    for key, val in (subs or {}).items():
        dot_text = dot_text.replace(key, val)
    return dot_text


# ---------------------------------------------------------------------------
# Private: session executor (LLM / box nodes).
# ---------------------------------------------------------------------------


def _register_spawn_capability(session: Any, prepared: Any) -> None:
    """Wire session.spawn so pipeline LLM nodes get full child sessions with tools."""
    from amplifier_foundation import Bundle, load_bundle
    from amplifier_foundation.spawn_utils import ProviderPreference

    # Memoize resolved child bundles by ref string — one load per unique ref per
    # run_pipeline call. Avoids repeated round-trips to the foundation registry
    # for the same profile file across all box nodes in one pipeline run.
    # The single-bundle-ref branch ("bundle" key, len==1) is the hot path: our
    # wiki-agent profile is the same on every node, so MISS happens only once;
    # subsequent nodes get HIT from this per-run cache.
    # The multi-key Bundle(...) construction path is left unchanged.
    _bundle_cache: dict[str, Any] = {}

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
            # Rewrite 'attractor:' namespace refs to resolvable git URLs.
            if ref.startswith("attractor:"):
                sub = ref.split("attractor:", 1)[1]
                ref = (
                    "git+https://github.com/microsoft/amplifier-bundle-attractor@main"
                    f"#subdirectory={sub}.yaml"
                )
            if ref not in _bundle_cache:
                _bundle_cache[ref] = await load_bundle(ref)  # cached per run; fail loud
            child_bundle = _bundle_cache[ref]
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
            provider_preferences = [
                ProviderPreference(provider="anthropic", model=CURRENT_MODEL)
            ]
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


async def _run_session_pipeline(
    dot_text: str,
    wiki_dir: Path,
    agent_profile: Path = WIKI_AGENT_PROFILE,
) -> dict[str, Any]:
    """Spin up an AmplifierSession and run a dot pipeline in wiki_dir."""
    from amplifier_foundation import Bundle, load_bundle

    bundle = await load_bundle(ATTRACTOR_BUNDLE)
    overlay = Bundle(
        name="wiki-attractor-run",
        session={
            "orchestrator": {
                "module": "loop-pipeline",
                "config": {"profiles": PROFILES_MAP, "dot_source": dot_text},
            }
        },
        agents={"attractor-agent-anthropic": {"bundle": str(agent_profile)}},
    )
    composed = bundle.compose(overlay)
    prepared = await composed.prepare()
    session = await prepared.create_session(session_cwd=wiki_dir)
    _register_spawn_capability(session, prepared)

    os.chdir(wiki_dir)

    async with session:
        result = await session.execute("Run the pipeline")

    try:
        return json.loads(result)
    except (json.JSONDecodeError, TypeError):
        return {"status": "unknown", "raw": result}


# ---------------------------------------------------------------------------
# Private: engine executor (HITL / tool+diamond+hexagon nodes, no LLM).
# ---------------------------------------------------------------------------


async def _run_engine_pipeline(
    dot_text: str,
    wiki_dir: Path,
    interviewer: Any | None = None,
) -> dict[str, Any]:
    """Run a HITL pipeline directly via PipelineEngine (no AmplifierSession)."""
    from amplifier_module_loop_pipeline.context import PipelineContext
    from amplifier_module_loop_pipeline.dot_parser import parse_dot
    from amplifier_module_loop_pipeline.engine import PipelineEngine
    from amplifier_module_loop_pipeline.handlers import HandlerRegistry
    from amplifier_module_loop_pipeline.handlers.context import HandlerContext
    from amplifier_module_loop_pipeline.transforms import apply_transforms
    from amplifier_module_loop_pipeline.validation import validate_or_raise

    graph = parse_dot(dot_text)
    context = PipelineContext()
    apply_transforms(graph, context)
    validate_or_raise(graph)

    registry = HandlerRegistry(HandlerContext(interviewer=interviewer))
    logs_root = tempfile.mkdtemp(prefix="wiki-attractor-review-")
    engine = PipelineEngine(
        graph=graph,
        context=context,
        handler_registry=registry,
        logs_root=logs_root,
    )

    os.chdir(wiki_dir)

    outcome = await engine.run()
    return {
        "status": outcome.status.value,
        "completed_nodes": getattr(engine, "completed_nodes", None),
        "notes": getattr(outcome, "notes", None),
        "failure_reason": getattr(outcome, "failure_reason", None),
        "logs_root": logs_root,
    }


# ---------------------------------------------------------------------------
# PUBLIC API — the single entry point callers use.
# ---------------------------------------------------------------------------


async def run_pipeline(
    dot_path: Path | str,
    wiki_dir: Path | str,
    subs: dict[str, str] | None = None,
    *,
    interviewer: Any | None = None,
    output_file: str | None = None,
) -> dict[str, Any]:
    """Run a .dot attractor pipeline in wiki_dir and return the result dict.

    This is the ONLY function the CLI and tool-modules call. It:
      1. Reads the .dot file and applies literal $placeholder substitutions (subs).
      2. Routes to the appropriate internal executor:
           - interviewer=None  → session executor (AmplifierSession + LLM box nodes)
           - interviewer=...   → engine executor (PipelineEngine, HITL, no LLM)
      3. If output_file is set AND the run succeeded, reads wiki_dir/output_file
         and adds its content as result["output"]. This is the clean mechanism
         for pipelines (like query) whose real output exceeds the 200-char
         node-record limit — they write to a known file; the lib reads it back.

    Args:
        dot_path:    Path to the .dot file (already-renamed, e.g. pipelines/query.dot).
        wiki_dir:    Root of the wiki repo to operate on.
        subs:        Dict of $placeholder -> value substituted into the DOT text.
        interviewer: If set, use the engine executor (HITL). None → session executor.
        output_file: Optional relative path (within wiki_dir) to read back after a
                     successful run and add as result["output"].

    Returns:
        Result dict from the engine, optionally enriched with result["output"].
    """
    wiki_dir = Path(wiki_dir).resolve()
    dot_text = _apply_subs(Path(dot_path).read_text(), subs)

    if interviewer is not None:
        result = await _run_engine_pipeline(dot_text, wiki_dir, interviewer=interviewer)
    else:
        result = await _run_session_pipeline(dot_text, wiki_dir)

    # If the pipeline succeeded and an output file is declared, read it back.
    if output_file and result.get("status") in ("success", "completed"):
        out_path = wiki_dir / output_file
        if out_path.exists():
            result["output"] = out_path.read_text()

    return result
