#!/usr/bin/env python3
"""wiki-attractor -- a thin click wrapper over the wiki-attractor API.

The CLI is intentionally thin: it parses click arguments, handles CLI-specific
concerns (--fresh checkpoint clearing, ConsoleInterviewer for interactive
review, pre-flight source-file validation), and delegates to the bespoke
wiki_attractor API (wiki_attractor.api) for each command.

Layer contract:
  .dot files    — ALL real work; named as their command; portable drop-ins
  api.py        — bespoke wiki-attractor typed API; one named fn per command
  runner.py     — ONLY code that stands up + invokes the attractor engine
  cli.py        — near-zero wrapper: arg parsing, pre-flight, print result
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

import click

import wiki_attractor.api as _api
from .registry import REGISTRY, PipelineSpec

_DEFAULT_CHECKPOINT = Path("/tmp/attractor-pipeline/checkpoint.json")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clear_checkpoint() -> None:
    """Remove the engine checkpoint so a fresh run can't hit CheckpointMismatchError."""
    try:
        _DEFAULT_CHECKPOINT.unlink()
    except FileNotFoundError:
        pass


def _print_result(name: str, result: dict[str, Any]) -> int:
    """Print pipeline result. Returns 0 for success, 1 for failure."""
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
        click.echo(f"notes           : {str(notes)[:400]}")
    # output: full content read back from the pipeline's output file (e.g.
    # query-answer.md or lint-report.md). Print to stdout so callers receive it.
    output = result.get("output")
    if output:
        click.echo("")
        click.echo("---------- OUTPUT ----------")
        click.echo(output)
        click.echo("----------------------------")
    return 0 if status in ("success", "completed") else 1


# ---------------------------------------------------------------------------
# API dispatch table — maps command name to its coroutine factory.
#
# Each entry calls the bespoke named API function for that command, keeping
# the CLI data-driven while flowing entirely through the typed API layer.
# Adding a 7th command: one REGISTRY entry + one lambda here + one .dot file.
# ---------------------------------------------------------------------------

_COMMAND_DISPATCH: dict[str, Any] = {
    "ingest": lambda wd, **kw: _api.ingest(wd, kw["source"]),
    "query": lambda wd, **kw: _api.query(wd, kw["question"]),
    "lint": lambda wd, **kw: _api.lint(wd),
    "publish": lambda wd, **kw: _api.publish(wd),
    "init": lambda wd, **kw: _api.init(wd, kw["package"], kw["brief"]),
    "full-pass": lambda wd, **kw: _api.full_pass(wd),
    "apply-resolutions": lambda wd, **kw: _api.apply_resolutions(wd),
}


# ---------------------------------------------------------------------------
# Command builders (one per executor kind), wired from the registry.
# ---------------------------------------------------------------------------


def _make_session_command(spec: PipelineSpec) -> click.Command:
    @click.pass_context
    def _cmd(ctx: click.Context, **kwargs: str) -> None:
        wiki_dir = ctx.obj["wiki_dir"]

        # ingest: validate the source file exists in raw/ as a CLI pre-flight.
        # The api validates the wiki itself; this check gives a clearer error
        # message before the pipeline starts.
        if spec.name == "ingest":
            src = Path(wiki_dir).resolve() / "raw" / kwargs["source"]
            if not src.exists():
                raise click.ClickException(
                    f"source not found in raw/: {kwargs['source']}"
                )

        if ctx.obj["fresh"]:
            _clear_checkpoint()

        click.echo(f"[wiki-attractor] {spec.name}: {Path(wiki_dir).resolve()}")
        for k, v in kwargs.items():
            click.echo(f"[wiki-attractor]   {k} = {v}")

        # Call the bespoke API function for this command.
        # ValueError is api's way of signalling a user-readable error.
        try:
            result = asyncio.run(_COMMAND_DISPATCH[spec.name](wiki_dir, **kwargs))
        except ValueError as exc:
            raise click.ClickException(str(exc)) from exc

        sys.exit(_print_result(spec.name.upper(), result))

    cmd = click.command(name=spec.name, help=spec.summary)(_cmd)
    for arg in spec.args:
        cmd = click.argument(arg.name, metavar=arg.name.upper())(cmd)
    return cmd


def _make_engine_command(spec: PipelineSpec) -> click.Command:
    @click.option(
        "--decisions",
        default=None,
        help=(
            "Non-interactive: comma-separated C/X/P, one per queue item "
            "(e.g. C,X,P). Omit for an interactive human gate."
        ),
    )
    @click.pass_context
    def _cmd(ctx: click.Context, decisions: str | None) -> None:
        wiki_dir = ctx.obj["wiki_dir"]

        from amplifier_module_loop_pipeline.interviewer import (  # noqa: PLC0415
            Answer,
            ConsoleInterviewer,
            QueueInterviewer,
        )

        if decisions:
            picks = [d.strip().upper() for d in decisions.split(",") if d.strip()]
            interviewer: Any = QueueInterviewer([Answer(value=d) for d in picks])
            click.echo(f"[wiki-attractor] review (non-interactive): {picks}")
        else:
            interviewer = ConsoleInterviewer()
            click.echo("[wiki-attractor] review (interactive human gate)")

        # Call the bespoke review() API function; pass the caller-built interviewer.
        try:
            result = asyncio.run(_api.review(wiki_dir, interviewer=interviewer))
        except ValueError as exc:
            raise click.ClickException(str(exc)) from exc

        sys.exit(_print_result(spec.name.upper(), result))

    return click.command(name=spec.name, help=spec.summary)(_cmd)


_BUILDERS = {"session": _make_session_command, "engine": _make_engine_command}


# ---------------------------------------------------------------------------
# Custom query command (--save / --save-as: Karpathy compounding loop)
#
# query is the one command that takes an extra flag: --save/--no-save closes
# the compounding loop (cited answer → raw/ → ingest).  All other commands
# are fully auto-generated from their registry specs; query needs this one
# extra surface, so it gets a bespoke builder rather than _make_session_command.
# ---------------------------------------------------------------------------


def _print_query_save_result(result: dict[str, Any]) -> None:
    """Print query_save result: cited answer then loop-closure summary."""
    query_r = result.get("query", {})
    ingest_r = result.get("ingest", {})
    raw_file = result.get("raw_file", "")

    # Print the cited answer (from the query pass)
    answer = query_r.get("output", "")
    if answer:
        click.echo("\n---------- CITED ANSWER ----------")
        click.echo(answer)
        click.echo("----------------------------------")
    else:
        click.echo(f"\nquery status: {query_r.get('status', 'unknown')}")
        if query_r.get("failure_reason"):
            click.echo(f"query failure: {query_r['failure_reason']}")

    # Print loop-closure summary
    click.echo("\n[compounding loop] Answer saved to raw/:")
    click.echo(f"  {raw_file}")

    if ingest_r:
        click.echo(f"\n[compounding loop] Ingest: {ingest_r.get('status', 'unknown')}")
        ns = ingest_r.get("node_statuses")
        if ns:
            click.echo(f"  nodes: {ns}")
        if ingest_r.get("failure_reason"):
            click.echo(f"  ingest failure: {ingest_r['failure_reason']}")

    click.echo("==================================")


def _make_query_cli_command() -> click.Command:
    """Build the `query` click command with optional --save/--no-save support."""
    spec = REGISTRY["query"]

    @click.command(
        name="query",
        help=(
            "Read-only Q&A: index-first drill, cited answer returned to caller. "
            "Add --save to close Karpathy's compounding loop: the cited answer is "
            "saved to raw/ (with query-derived provenance) and ingested as a wiki page."
        ),
    )
    @click.argument("question")
    @click.option(
        "--save/--no-save",
        default=False,
        help=(
            "Save the cited answer to raw/ and ingest it as a wiki page "
            "(the compounding loop). The saved file is marked as query-derived "
            "synthesis, not an external source. Default: off (read-only)."
        ),
    )
    @click.option(
        "--save-as",
        default=None,
        metavar="NAME",
        help=(
            "Custom slug for the saved raw/ file "
            "(default: auto-derived from the question text). "
            "Has no effect without --save."
        ),
    )
    @click.pass_context
    def _query_cmd(
        ctx: click.Context,
        question: str,
        save: bool,
        save_as: str | None,
    ) -> None:
        wiki_dir = ctx.obj["wiki_dir"]

        if ctx.obj["fresh"]:
            _clear_checkpoint()

        click.echo(f"[wiki-attractor] {spec.name}: {Path(wiki_dir).resolve()}")
        click.echo(f"[wiki-attractor]   question = {question}")
        if save:
            click.echo(
                "[wiki-attractor]   --save: will file answer back into wiki "
                "(Karpathy compounding loop)"
            )

        try:
            if save:
                result = asyncio.run(
                    _api.query_save(wiki_dir, question, save_as=save_as)
                )
                _print_query_save_result(result)
                sys.exit(0 if result.get("status") == "success" else 1)
            else:
                result = asyncio.run(_api.query(wiki_dir, question))
                sys.exit(_print_result(spec.name.upper(), result))
        except ValueError as exc:
            raise click.ClickException(str(exc)) from exc

    return _query_cmd


# ---------------------------------------------------------------------------
# Root group
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

    Each subcommand drives a .dot pipeline (wiki_attractor/pipelines/).
    Run from inside a wiki repo; override with --wiki-dir.
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


# Register every pipeline as a command.
# `query` is skipped here — it needs --save/--no-save support and uses a
# custom builder below.  All other commands are fully auto-generated.
for _spec in REGISTRY.values():
    if _spec.name == "query":
        continue
    main.add_command(_BUILDERS[_spec.executor](_spec))

# Register the query command with --save/--no-save support (compounding loop).
main.add_command(_make_query_cli_command())


if __name__ == "__main__":
    main()
