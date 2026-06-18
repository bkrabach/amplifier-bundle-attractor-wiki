#!/usr/bin/env python3
"""DETERMINISTIC probe: does wiki-agent-anthropic.yaml's context.include actually
load the vendored orientation text into the (composed) child bundle? No LLM.

Removes the confabulation variable: we inspect the loaded bundle object for a
SENTINEL string that exists ONLY in the vendored orientation
(`<package-dir>/index.md` ... the navigational-backbone line), and dump where
context content does/doesn't appear.

Run from inside the companion:
  ~/.local/share/uv/tools/amplifier/bin/python probe_context.py
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from amplifier_foundation import load_bundle

HERE = Path(__file__).resolve().parent
WIKI_AGENT = str(HERE / "wiki-agent-anthropic.yaml")

# Distinctive strings that appear ONLY in the vendored orientation, never in
# generic LLM knowledge of "llm wiki".
SENTINELS = [
    "navigational backbone",          # wiki-instructions.md section heading
    "<package-dir>/index.md",         # the actual catalog path
    "greppable",                      # log.md description
    "Karpathy",                       # llm-wiki-pattern.md
]


def scan(obj, path="bundle", depth=0, found=None):
    """Recursively stringify and search bundle attributes for sentinels."""
    if found is None:
        found = {}
    if depth > 6:
        return found
    try:
        s = str(obj)
    except Exception:
        s = ""
    for sent in SENTINELS:
        if sent in s and sent not in found:
            found[sent] = path
    return found


async def main() -> int:
    print(f"[probe] loading {WIKI_AGENT}")
    bundle = await load_bundle(WIKI_AGENT)

    # 1) What does the bundle think its context is?
    ctx = getattr(bundle, "context", None)
    print(f"[probe] bundle.context type: {type(ctx)}")
    try:
        print(f"[probe] bundle.context repr (truncated):\n{str(ctx)[:1500]}")
    except Exception as e:
        print(f"[probe] (cannot repr context: {e})")

    # 2) Full stringification search for sentinels across the whole bundle.
    full = str(bundle.__dict__) if hasattr(bundle, "__dict__") else str(bundle)
    print("\n[probe] SENTINEL presence in str(bundle.__dict__):")
    for sent in SENTINELS:
        print(f"   {'FOUND' if sent in full else 'absent':>6}  {sent!r}")

    # 3) Prepared bundle — what actually gets assembled.
    try:
        prepared = await bundle.prepare()
        pfull = str(getattr(prepared, "__dict__", prepared))
        print("\n[probe] SENTINEL presence in str(prepared.__dict__):")
        for sent in SENTINELS:
            print(f"   {'FOUND' if sent in pfull else 'absent':>6}  {sent!r}")
        # try common context attrs
        for attr in ("context", "mount_plan", "assembled_context", "system"):
            v = getattr(prepared, attr, None)
            if v is not None:
                vs = str(v)
                hit = any(s in vs for s in SENTINELS)
                print(f"[probe] prepared.{attr}: len={len(vs)} sentinel={'YES' if hit else 'no'}")
    except Exception as e:
        print(f"[probe] prepare() failed: {e!r}")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
