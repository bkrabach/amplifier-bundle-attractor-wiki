#!/usr/bin/env python3
"""Smoke test for the FAIL-LOUD unsupported-input guardrail.

4 cases, all deterministic (no LLM calls, no pipeline runs):

  Case 1 — source code (.py)   : must FAIL LOUD, no garbage pages
  Case 2 — prose (.md)         : must PASS (guard does not raise)
  Case 3 — .md with code blocks: must PASS (treated as prose by extension)
  Case 4 — binary (.png)       : must FAIL LOUD

Tests are run against the real api.ingest() for the rejection cases (proves the
ValueError surfaces through the API layer), and against _classify_source()
directly for the pass cases (guard proof, no 15-min pipeline invocation).
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

# Force PYTHONPATH to the dev tree so we get the branch code, not the cache.
dev_tree = Path(__file__).resolve().parent
if str(dev_tree) not in sys.path:
    sys.path.insert(0, str(dev_tree))

# Now import from the dev tree.
from wiki_attractor.api import _classify_source  # noqa: E402  # type: ignore[attr-defined]
import wiki_attractor.api as api  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_test_wiki(tmp: Path) -> Path:
    """Create the minimum wiki structure _check_wiki() needs."""
    wiki = tmp / "smoke-wiki"
    wiki.mkdir()
    schema = wiki / ".wiki" / "context"
    schema.mkdir(parents=True)
    (schema / "schema.md").write_text("# schema (smoke)\n")
    raw = wiki / "raw"
    raw.mkdir()
    return wiki


def _assert_raises(exc_type: type, fn, *args, **kwargs) -> str:  # type: ignore[type-arg]
    """Call fn(*args, **kwargs); assert it raises exc_type. Returns the message."""
    try:
        fn(*args, **kwargs)
    except exc_type as exc:
        return str(exc)
    raise AssertionError(f"Expected {exc_type.__name__} but no exception was raised.")


def _assert_no_raise(fn, *args, **kwargs) -> None:  # type: ignore[type-arg]
    """Call fn(*args, **kwargs); assert it does NOT raise."""
    try:
        fn(*args, **kwargs)
    except Exception as exc:
        raise AssertionError(
            f"Expected no exception but got {type(exc).__name__}: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Main smoke
# ---------------------------------------------------------------------------


def run_smoke() -> None:
    print("=== wiki-attractor FAIL-LOUD input-type guardrail smoke ===\n")

    with tempfile.TemporaryDirectory(prefix="wa-smoke-") as tmp_str:
        tmp = Path(tmp_str)
        wiki = _make_test_wiki(tmp)
        raw = wiki / "raw"

        # ── Case 1: source-code file (.py) ──────────────────────────────────
        print("Case 1: source code (.py) → must FAIL LOUD")
        # Copy the real cli.py so we have authentic source-code content.
        sample_py = raw / "sample.py"
        real_cli = dev_tree / "wiki_attractor" / "cli.py"
        sample_py.write_bytes(real_cli.read_bytes())

        # Test via api.ingest() so we prove the ValueError surfaces through the
        # full API layer (not just the classifier function in isolation).
        try:
            asyncio.run(api.ingest(wiki, "sample.py"))
            print("  FAIL: no exception raised — code file should have been rejected")
            sys.exit(1)
        except ValueError as exc:
            msg = str(exc)
            assert ".py" in msg, f"Message doesn't mention the extension: {msg!r}"
            assert "source code" in msg.lower() or "not yet supported" in msg.lower(), (
                f"Message isn't actionable enough: {msg!r}"
            )
            print("  PASS: ValueError raised ✓")
            print("  message:\n    " + msg.replace("\n", "\n    "))

        # Verify no garbage pages were created.
        pkg = wiki / "team-knowledge"
        garbage = list(pkg.rglob("*.md")) if pkg.exists() else []
        assert not garbage, f"Garbage pages were created: {garbage}"
        print("  No garbage entity pages created ✓\n")

        # ── Case 2: plain prose (.md transcript) ────────────────────────────
        print("Case 2: prose .md → must PASS (guard does not raise)")
        prose_md = raw / "2026-06-23-team-meeting.md"
        prose_md.write_text(
            "# Team Meeting — 2026-06-23\n\n"
            "Brian: we should build the weave connections layer.\n"
            "Chris: agreed, let's prove it first.\n",
            encoding="utf-8",
        )
        # Test via _classify_source directly (no pipeline — we'd need 15 min).
        # The guard is the load-bearing proof here; full-ingest success is proved
        # by the many successful ingest runs already committed to the eval log.
        _assert_no_raise(_classify_source, wiki, "2026-06-23-team-meeting.md")
        print("  PASS: _classify_source does not raise for .md prose ✓\n")

        # ── Case 3: .md with fenced code blocks ─────────────────────────────
        print("Case 3: .md with fenced code blocks → must PASS (prose by extension)")
        code_block_md = raw / "api-design-notes.md"
        code_block_md.write_text(
            "# API Design Notes\n\n"
            "We decided to use the following pattern:\n\n"
            "```python\n"
            "async def ingest(wiki_dir, source):\n"
            "    _classify_source(wiki_dir, source)\n"
            "    return await run_pipeline(...)\n"
            "```\n\n"
            "This ensures the guard runs before any LLM work.\n",
            encoding="utf-8",
        )
        _assert_no_raise(_classify_source, wiki, "api-design-notes.md")
        print("  PASS: .md with fenced code blocks is treated as prose ✓\n")

        # ── Case 4: binary file (.png) ───────────────────────────────────────
        print("Case 4: binary file (.png) → must FAIL LOUD")
        binary_png = raw / "screenshot.png"
        # Write a minimal valid PNG header (8 bytes PNG magic + IHDR chunk start).
        # Real PNG files always contain null bytes.
        png_bytes = (
            b"\x89PNG\r\n\x1a\n"  # PNG signature (contains null + 0x1a)
            b"\x00\x00\x00\rIHDR"  # IHDR chunk length (contains null bytes)
            b"\x00\x00\x00\x01"  # width = 1
            b"\x00\x00\x00\x01"  # height = 1
            b"\x08\x02\x00\x00\x00"  # bit depth, colour type, etc.
            b"\x90wS\xde"  # CRC
        )
        binary_png.write_bytes(png_bytes)

        # Test via api.ingest() to prove the ValueError surfaces through the API.
        try:
            asyncio.run(api.ingest(wiki, "screenshot.png"))
            print("  FAIL: no exception raised — binary file should have been rejected")
            sys.exit(1)
        except ValueError as exc:
            msg = str(exc)
            assert "binary" in msg.lower(), f"Message doesn't mention 'binary': {msg!r}"
            print("  PASS: ValueError raised ✓")
            print("  message:\n    " + msg.replace("\n", "\n    "))

        # No garbage pages.
        garbage = list(pkg.rglob("*.md")) if pkg.exists() else []
        assert not garbage, f"Garbage pages were created: {garbage}"
        print("  No garbage entity pages created ✓\n")

    print("=== ALL 4 CASES PASSED ===")


if __name__ == "__main__":
    run_smoke()
