#!/usr/bin/env python3
"""The light AmplifierSession spin-up for running attractor pipelines.

This is the load-bearing lib the CLI wraps. It factors the PROVEN machinery out
of the run_seam.py / run_ingest.py / run_review.py spikes into two reusable
executors. Nothing here is new logic -- it is the spike code, de-duplicated:

  run_session_pipeline(...)  -- the Path-B AmplifierSession executor. Box (LLM)
      nodes spawn full child sessions with tools. Used by `wiki-attractor ingest`.
      This is "the light implementation of what is needed to spin up an
      AmplifierSession instance to run attractor pipelines."

  run_engine_pipeline(...)   -- the direct PipelineEngine executor for HITL
      pipelines (tool + diamond + hexagon nodes, no LLM). Used by
      `wiki-attractor review`. Takes an Interviewer for the human gate.

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

# The attractor bundle pins claude-sonnet-4-20250514, which retired 2026-06-15.
# Use the routing-matrix "latest sonnet" glob: the resolver matches it against the
# provider's live model list (sorted descending) and picks the newest, so it never
# pins a model that can retire out from under us.
CURRENT_MODEL = "claude-sonnet-*"

PROFILES_MAP = {
    "anthropic": "attractor-agent-anthropic",
    "openai": "attractor-agent-openai",
    "gemini": "attractor-agent-gemini",
}

_PKG = Path(__file__).resolve().parent
# The llm-wiki-composed child agent profile (schema-driven; portable via git-URL
# include). Overrides the attractor anthropic child agent at spawn time.
WIKI_AGENT_PROFILE = _PKG / "profiles" / "wiki-agent-anthropic.yaml"


def _apply_subs(dot_text: str, subs: dict[str, str] | None) -> str:
    """Literal placeholder substitution into the DOT text before the engine sees it.

    The proven mechanism for $source / $PYBIN / $HELPER injection: string-replace
    in the raw .dot text (substitution.py treats absent keys as literal anyway).
    """
    for key, val in (subs or {}).items():
        dot_text = dot_text.replace(key, val)
    return dot_text


# ---------------------------------------------------------------------------
# Session executor (ingest) -- the Path-B AmplifierSession spin-up.
# ---------------------------------------------------------------------------


def _register_spawn_capability(session: Any, prepared: Any) -> None:
    """Wire session.spawn so pipeline LLM nodes get full child sessions with tools.

    Verbatim from run_seam.py (the documented attractor reference impl, plus the
    two proven fixes: attractor:-namespace -> git-URL rewrite, and a typed
    ProviderPreference using the latest-sonnet glob). Without this, loop-pipeline
    silently falls back to the no-tools DirectProviderBackend.
    """
    from amplifier_foundation import Bundle, load_bundle
    from amplifier_foundation.spawn_utils import ProviderPreference

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


async def run_session_pipeline(
    dot_path: Path,
    wiki_dir: Path,
    subs: dict[str, str] | None = None,
    agent_profile: Path = WIKI_AGENT_PROFILE,
) -> dict[str, Any]:
    """Spin up an AmplifierSession and run a (box-node) attractor pipeline in `wiki_dir`.

    The reusable core of run_seam.py + run_ingest.py:
      load attractor base -> compose loop-pipeline overlay (profiles map +
      dot_source + wiki-agent child override) -> prepare -> create_session(cwd) ->
      register spawn -> chdir into the wiki (for deterministic tool nodes) ->
      execute -> return parsed result JSON.

    Returns the pipeline result dict (parsed JSON), or {"status": "unknown", ...}
    if the engine returned non-JSON.
    """
    from amplifier_foundation import Bundle, load_bundle

    wiki_dir = Path(wiki_dir).resolve()
    dot_text = _apply_subs(Path(dot_path).read_text(), subs)

    bundle = await load_bundle(ATTRACTOR_BUNDLE)
    overlay = Bundle(
        name="wiki-attractor-run",
        session={
            "orchestrator": {
                "module": "loop-pipeline",
                "config": {"profiles": PROFILES_MAP, "dot_source": dot_text},
            }
        },
        # Override the anthropic child agent with the llm-wiki-composed profile.
        agents={"attractor-agent-anthropic": {"bundle": str(agent_profile)}},
    )
    composed = bundle.compose(overlay)

    prepared = await composed.prepare()
    session = await prepared.create_session(session_cwd=wiki_dir)
    _register_spawn_capability(session, prepared)

    # Make the wiki the process cwd so deterministic (parallelogram) nodes, whose
    # subprocess cwd falls back to process cwd, run inside the wiki.
    os.chdir(wiki_dir)

    async with session:
        result = await session.execute("Run the pipeline")

    try:
        return json.loads(result)
    except (json.JSONDecodeError, TypeError):
        return {"status": "unknown", "raw": result}


# ---------------------------------------------------------------------------
# Engine executor (review/HITL) -- direct PipelineEngine with an Interviewer.
# ---------------------------------------------------------------------------


async def run_engine_pipeline(
    dot_path: Path,
    wiki_dir: Path,
    subs: dict[str, str] | None = None,
    interviewer: Any | None = None,
) -> dict[str, Any]:
    """Run a HITL (hexagon-gate) attractor pipeline directly via PipelineEngine.

    The reusable core of run_review.py. The standard session path builds its
    HandlerContext WITHOUT an interviewer, so a hexagon gate would raise. We build
    the PipelineEngine directly with an Interviewer wired into the HandlerContext.
    wiki-review.dot uses only tool + diamond + hexagon nodes (no codergen), so
    backend=None is sufficient -- no provider keys, no spawn, no LLM calls.

    `interviewer` is any amplifier Interviewer (ConsoleInterviewer for a real human,
    QueueInterviewer for preset/non-interactive decisions).
    """
    from amplifier_module_loop_pipeline.context import PipelineContext
    from amplifier_module_loop_pipeline.dot_parser import parse_dot
    from amplifier_module_loop_pipeline.engine import PipelineEngine
    from amplifier_module_loop_pipeline.handlers import HandlerRegistry
    from amplifier_module_loop_pipeline.handlers.context import HandlerContext
    from amplifier_module_loop_pipeline.transforms import apply_transforms
    from amplifier_module_loop_pipeline.validation import validate_or_raise

    wiki_dir = Path(wiki_dir).resolve()
    dot_text = _apply_subs(Path(dot_path).read_text(), subs)

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

    # Tool nodes inherit process cwd when context.target_dir/source_dir are unset.
    os.chdir(wiki_dir)

    outcome = await engine.run()
    return {
        "status": outcome.status.value,
        "completed_nodes": getattr(engine, "completed_nodes", None),
        "notes": getattr(outcome, "notes", None),
        "failure_reason": getattr(outcome, "failure_reason", None),
        "logs_root": logs_root,
    }
