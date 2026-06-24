#!/usr/bin/env python3
"""
classify_source.py — deterministic input-type guard for wiki-attractor.

WHAT THIS DOES
--------------
Classifies a source file as acceptable prose (ACCEPT) or unsupported
(REJECT: code or binary) before any LLM mining starts.  Running before
the pipeline ensures code/binary input NEVER silently produces garbage
entity pages — the worst failure class (silent, trust-destroying).

CLASSIFICATION RULES (applied in order)
----------------------------------------
1. BINARY SNIFF FIRST: read first ~8 KB.
   - File unreadable / missing → REJECT (fail closed).
   - Contains NUL bytes          → REJECT (binary file).
   - Fails UTF-8 decode          → REJECT (binary or non-UTF-8).
2. CODE EXTENSION: suffix in the hard-deny list → REJECT.
3. PROSE EXTENSION: suffix in the explicit allow list → ACCEPT.
4. DEFAULT: any other extension → ACCEPT (conservative; ambiguous
   structured-prose exports like .json/.yaml pass through).

FAIL-CLOSED INVARIANT
----------------------
Any exception, unreadable file, or ambiguity → REJECT.
The script never accepts on error.

COMMAND-LINE CONTRACT (used by ingest.dot parallelogram node)
--------------------------------------------------------------
  python3 classify_source.py <file_path>

  Exit 0 + last stdout line "CLASSIFY_OK"     → ACCEPT
  Exit 1 + stdout = actionable rejection msg   → REJECT

IMPORTABLE CONTRACT (used by api.py via subprocess)
-----------------------------------------------------
  classify(file_path: Path) -> tuple[bool, str]
    True,  "CLASSIFY_OK"   → accept (safe to ingest)
    False, <message>        → reject (human-readable reason, no sentinel)

USAGE
-----
  python3 classify_source.py path/to/file.md
  python3 classify_source.py raw/2026-06-20-meeting-notes.md
"""

from __future__ import annotations

import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Classification tables
# ---------------------------------------------------------------------------

# Source-code file extensions — ALWAYS reject, no mining ever.
_CODE_EXTENSIONS: frozenset[str] = frozenset(
    {
        # Python
        ".py",
        ".pyw",
        ".pyi",
        # Rust
        ".rs",
        # TypeScript / JavaScript
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".mjs",
        ".cjs",
        # Go
        ".go",
        # Java / JVM
        ".java",
        ".kt",
        ".kts",
        ".scala",
        ".groovy",
        # C / C++
        ".c",
        ".h",
        ".cpp",
        ".cc",
        ".cxx",
        ".hpp",
        ".hh",
        ".hxx",
        # C#
        ".cs",
        # Ruby
        ".rb",
        # PHP
        ".php",
        # Swift / Objective-C
        ".swift",
        ".m",
        # Shell
        ".sh",
        ".bash",
        ".zsh",
        ".fish",
        # SQL
        ".sql",
        # Lua
        ".lua",
        # Perl
        ".pl",
        ".pm",
        # R
        ".r",
        # Web components
        ".vue",
        ".svelte",
        # Other languages
        ".dart",
        ".ex",
        ".exs",  # Elixir
        ".erl",  # Erlang
        ".hs",
        ".lhs",  # Haskell
        ".elm",
        ".clj",
        ".cljs",  # Clojure
        ".lisp",
        ".el",  # Lisp / Emacs Lisp
        ".tf",  # Terraform HCL
        ".asm",
        ".s",  # Assembly
        ".f90",
        ".f95",  # Fortran
        # Notebooks
        ".ipynb",  # Jupyter (code execution artifact)
    }
)

# Prose extensions — always allow (after binary sniff passes), skip further checks.
_PROSE_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".md",
        ".markdown",
        ".txt",
        ".rst",
        ".html",
        ".htm",
        ".tex",
        ".latex",
        ".org",
        ".adoc",
        ".asciidoc",
        ".wiki",
    }
)


# ---------------------------------------------------------------------------
# Core classification function (importable)
# ---------------------------------------------------------------------------


def classify(file_path: Path) -> tuple[bool, str]:
    """Classify *file_path* as acceptable prose or unsupported input.

    Returns
    -------
    (True,  "CLASSIFY_OK")
        The file is acceptable prose — safe to ingest.
    (False, <actionable_message>)
        The file is unsupported (binary, source code, unreadable, or
        missing).  The message is human-readable and does NOT include
        the "CLASSIFY_REJECTED" routing sentinel (that is added by the
        calling context — see ``main()`` and ``ingest.dot``).

    FAIL-CLOSED INVARIANT
    ----------------------
    Any exception → returns (False, reason_string).  Never raises.
    """
    # --- Step 1: Binary sniff FIRST, before any extension logic -----------
    try:
        header = file_path.read_bytes()[:8192]
    except FileNotFoundError:
        return False, (
            f"Unsupported input: {file_path} not found.\n"
            "wiki-attractor ingests plain-text prose from raw/. "
            "Ensure the file exists before ingesting."
        )
    except Exception as exc:  # noqa: BLE001
        return False, (
            f"Unsupported input: {file_path.name} could not be read ({exc}).\n"
            "wiki-attractor ingests plain-text prose only. "
            "Remove the file or ensure it is readable."
        )

    # NUL bytes → unambiguous binary indicator
    if b"\x00" in header:
        return False, (
            f"Unsupported input: {file_path.name} is a binary file "
            f"(null bytes detected — binary sniff, not extension check).\n"
            "wiki-attractor ingests plain-text prose only "
            "(documents, transcripts, notes).\n"
            "Binary files (images, PDFs, executables, archives, etc.) "
            "are not supported. Remove it or convert to plain text first."
        )

    # UTF-8 decode failure → binary or encoding mismatch → reject
    try:
        header.decode("utf-8")
    except UnicodeDecodeError:
        return False, (
            f"Unsupported input: {file_path.name} is a binary or non-UTF-8 file "
            f"(UTF-8 decode failed — binary sniff, not extension check).\n"
            "wiki-attractor ingests plain-text prose only "
            "(documents, transcripts, notes).\n"
            "Binary files (images, PDFs, executables, archives, etc.) "
            "are not supported. Remove it or convert to plain text first."
        )

    # --- Step 2: Extension checks (only reached if binary sniff passes) ---
    ext = file_path.suffix.lower()

    if ext in _CODE_EXTENSIONS:
        return False, (
            f"Unsupported input: {file_path.name} looks like source code ({ext}).\n"
            "wiki-attractor v1 ingests prose (documents, transcripts, notes);\n"
            "source code files are not yet supported — they need a codebase schema\n"
            "that the current four-type schema (outcomes/concepts/people/sources)\n"
            "does not provide. Remove it, or convert it to a prose description\n"
            "of the code's purpose, design decisions, or API contract."
        )

    if ext in _PROSE_EXTENSIONS:
        return True, "CLASSIFY_OK"

    # --- Step 3: Default allow (conservative; ambiguous extensions pass) ---
    # .yaml, .json, .toml, etc. are allowed — rejecting legitimate structured-
    # prose exports (Q&A JSON dumps, YAML-frontmatter docs) is worse than
    # occasionally ingesting a config file.
    return True, "CLASSIFY_OK"


# ---------------------------------------------------------------------------
# Entry point (command-line use by ingest.dot parallelogram node)
# ---------------------------------------------------------------------------


def main() -> None:
    """Command-line entry point.

    Usage: python3 classify_source.py <file_path>

    Stdout contract for the .dot routing engine:
      Accept: prints "CLASSIFY_OK" as the LAST line; exits 0.
      Reject: prints actionable message; exits 1.
              The calling tool_command appends "CLASSIFY_REJECTED" as the
              final routing sentinel (see ingest.dot classify node).
    """
    if len(sys.argv) < 2:
        print(
            "Unsupported input: no file path given.\n"
            "Usage: classify_source.py <file_path>\n"
            "wiki-attractor ingests plain-text prose only "
            "(documents, transcripts, notes).",
            flush=True,
        )
        sys.exit(1)

    file_path = Path(sys.argv[1])
    accepted, message = classify(file_path)

    print(message, flush=True)
    sys.exit(0 if accepted else 1)


if __name__ == "__main__":
    main()
