#!/usr/bin/env python3
"""wiki-attractor -- a thin click wrapper over the AmplifierSession pipeline runner.

The CLI is intentionally dumb: it builds one click command per registry entry, maps
the user's CLI arguments to DOT $placeholders, and hands off to the runner. Adding a
command (step 4: init / lint / publish / query) is a data-only change in registry.py
plus a .dot file -- this dispatch code does not change.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import click

from . import runner
from .registry import REGISTRY, PipelineSpec

_PKG = Path(__file__).resolve().parent
_REVIEW_HELPER = _PKG / "review_queue.py"
_DEFAULT_CHECKPOINT = Path("/tmp/attractor-pipeline/checkpoint.json")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clear_checkpoint() -> None:
    """Remove the engine's default checkpoint so a fresh run can't collide with a
    stale graph (the CheckpointMismatchError footgun). Single-file unlink only."""
    try:
        _DEFAULT_CHECKPOINT.unlink()
    except FileNotFoundError:
        pass


def _require_wiki(wiki_dir: Path) -> Path:
    wiki_dir = Path(wiki_dir).resolve()
    schema = wiki_dir / ".wiki" / "context" / "schema.md"
    if not schema.exists():
        raise click.ClickException(
            f"{wiki_dir} is not an initialized wiki (missing .wiki/context/schema.md). "
            "Run wiki-attractor from inside a wiki repo, or pass --wiki-dir."
        )
    return wiki_dir


def _print_result(name: str, result: dict) -> int:
    status = result.get("status")
    click.echo("")
    click.echo(f"========== {name} RESULT ==========")
    click.echo(f"status          : {status}")
    if result.get("node_statuses") is not None:
        click.echo(f"node_statuses   : {result.get('node_statuses')}")
    if result.get("completed_nodes") is not None:
        click.echo(f"completed_nodes : {result.get('completed_nodes')}")
    if result.get("failure_reason"):
        click.echo(f"failure_reason  : {result.get('failure_reason')}")
    notes = result.get("notes") or result.get("raw") or ""
    if notes:
        click.echo(f"notes           : {str(notes)[:1500]}")
    ok = status in ("success", "completed")
    return 0 if ok else 1


# ---------------------------------------------------------------------------
# Command builders (one per executor kind), wired from the registry.
# ---------------------------------------------------------------------------


def _make_session_command(spec: PipelineSpec) -> click.Command:
    @click.pass_context
    def _cmd(ctx: click.Context, **kwargs: str) -> None:
        wiki_dir = _require_wiki(ctx.obj["wiki_dir"])
        subs = {arg.placeholder: kwargs[arg.name] for arg in spec.args}

        # Light, command-agnostic pre-flight for sourced pipelines.
        for arg in spec.args:
            if arg.name == "source":
                src = wiki_dir / "raw" / kwargs["source"]
                if not src.exists():
                    raise click.ClickException(
                        f"source not found in raw/: {kwargs['source']}"
                    )

        if ctx.obj["fresh"]:
            _clear_checkpoint()

        click.echo(f"[wiki-attractor] {spec.name}: {wiki_dir}")
        for k, v in subs.items():
            click.echo(f"[wiki-attractor]   {k} = {v}")

        result = asyncio.run(
            runner.run_session_pipeline(dot_path=spec.dot, wiki_dir=wiki_dir, subs=subs)
        )
        sys.exit(_print_result(spec.name.upper(), result))

    cmd = click.command(name=spec.name, help=spec.summary)(_cmd)
    for arg in spec.args:
        cmd = click.argument(arg.name, metavar=arg.name.upper())(cmd)
    return cmd


def _make_engine_command(spec: PipelineSpec) -> click.Command:
    @click.option(
        "--decisions",
        default=None,
        help="Non-interactive: comma-separated C/X/P, one per queue item (e.g. C,X,P). "
        "Omit for an interactive human gate.",
    )
    @click.pass_context
    def _cmd(ctx: click.Context, decisions: str | None) -> None:
        wiki_dir = _require_wiki(ctx.obj["wiki_dir"])
        queue = wiki_dir / "team-knowledge" / "flag-queue.json"
        if not queue.exists():
            raise click.ClickException(
                "no team-knowledge/flag-queue.json -- run `wiki-attractor ingest` first "
                "(the reviewer node emits the queue)."
            )

        from amplifier_module_loop_pipeline.interviewer import (  # noqa: PLC0415
            Answer,
            ConsoleInterviewer,
            QueueInterviewer,
        )

        if decisions:
            picks = [d.strip().upper() for d in decisions.split(",") if d.strip()]
            interviewer = QueueInterviewer([Answer(value=d) for d in picks])
            click.echo(f"[wiki-attractor] review (non-interactive): {picks}")
        else:
            interviewer = ConsoleInterviewer()
            click.echo("[wiki-attractor] review (interactive human gate)")

        subs = {"$PYBIN": sys.executable, "$HELPER": str(_REVIEW_HELPER)}
        result = asyncio.run(
            runner.run_engine_pipeline(
                dot_path=spec.dot, wiki_dir=wiki_dir, subs=subs, interviewer=interviewer
            )
        )
        sys.exit(_print_result(spec.name.upper(), result))

    return click.command(name=spec.name, help=spec.summary)(_cmd)


_BUILDERS = {"session": _make_session_command, "engine": _make_engine_command}


# ---------------------------------------------------------------------------
# Root group -- default action lists the pipelines + help.
# ---------------------------------------------------------------------------


@click.group(invoke_without_command=True)
@click.option(
    "--wiki-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Wiki repo to operate on (default: current directory).",
)
@click.option(
    "--fresh/--resume",
    default=True,
    help="Clear the engine checkpoint before a session run (default: fresh).",
)
@click.version_option(package_name="wiki-attractor", prog_name="wiki-attractor")
@click.pass_context
def main(ctx: click.Context, wiki_dir: Path | None, fresh: bool) -> None:
    """Run amplifier-bundle-llm-wiki workflows as attractor pipelines.

    Each subcommand drives a .dot pipeline (registry.py). The tool is run from
    inside a wiki repo; override with --wiki-dir.
    """
    ctx.ensure_object(dict)
    ctx.obj["wiki_dir"] = wiki_dir if wiki_dir is not None else Path.cwd()
    ctx.obj["fresh"] = fresh
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())
        click.echo("")
        click.echo("Pipelines:")
        for spec in REGISTRY.values():
            click.echo(f"  {spec.name:<8} {spec.summary}")


# Register every pipeline as a command (data-driven dispatch).
for _spec in REGISTRY.values():
    main.add_command(_BUILDERS[_spec.executor](_spec))


if __name__ == "__main__":
    main()
