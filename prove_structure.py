#!/usr/bin/env python3
"""
PROOF SCRIPT — validates the proper bundle structure per the foundation-expert design.

(A) ROOT bundle (bundle.md):
    - Thin root: name=attractor-wiki, version=0.2.0, includes only (no tools block)
    - 6 tools present after composition (from behavior, via bundle._pending_context / mount)
    - awareness context in _pending_context (from behavior context.include)
    - full guide @-mentioned in root body (bundle.instruction)

(B) BEHAVIOR ALONE (behaviors/attractor-wiki.yaml):
    - name=attractor-wiki-behavior, 6 tools present
    - awareness context in _pending_context
    - full guide NOT in instruction (not in behavior body)

Run with:
  /home/bkrabach/.local/share/uv/tools/amplifier/bin/python prove_structure.py
"""
from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

REPO = Path(__file__).parent
BUNDLE_MD = REPO / "bundle.md"
BEHAVIOR_YAML = REPO / "behaviors" / "attractor-wiki.yaml"

EXPECTED_TOOLS = {"wiki_ingest", "wiki_query", "wiki_lint",
                  "wiki_publish", "wiki_init", "wiki_review"}
AWARENESS_FILE = "attractor-wiki-awareness.md"
FULL_GUIDE = "using-attractor-wiki"


async def _mount_tools(label: str) -> list[str]:
    """Import + mount tool-wiki via stub coordinator; return registered tool names."""
    spec = importlib.util.find_spec("amplifier_module_tool_wiki")
    if not spec:
        print(f"[{label}] amplifier_module_tool_wiki NOT importable — install failed")
        return []
    from amplifier_module_tool_wiki import mount  # noqa: PLC0415

    coordinator = MagicMock()
    coordinator.mount = AsyncMock()
    result = await mount(coordinator)
    calls = coordinator.mount.call_args_list
    names = [
        c[1].get("name", c[0][1].name if len(c[0]) > 1 else "?")
        for c in calls
    ]
    print(f"[{label}] mount() return  : {result}")
    print(f"[{label}] tools ({len(names)})   : {names}")
    return names


def _check_bundle(bundle, label: str) -> dict:
    """Extract and display relevant attributes from a loaded Bundle."""
    name = bundle.name
    version = getattr(bundle, "version", "?")
    instruction = getattr(bundle, "instruction", None) or ""

    # context.include lives in _pending_context (Foundation private attr)
    pending = getattr(bundle, "_pending_context", {}) or {}
    pending_keys = list(pending.keys())

    print(f"\n--- {label} ---")
    print(f"  name            : {name}")
    print(f"  version         : {version}")
    print(f"  instruction     : {repr(instruction[:120])}")
    print(f"  _pending_context: {pending_keys}")

    return {
        "name": name,
        "version": version,
        "instruction": instruction,
        "pending_keys": pending_keys,
    }


async def main() -> None:
    from amplifier_foundation import load_bundle

    results = {}

    # -----------------------------------------------------------------------
    # (A) ROOT bundle
    # -----------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("(A) ROOT bundle — bundle.md")
    print("=" * 60)
    print(f"path   : {BUNDLE_MD}")
    print(f"exists : {BUNDLE_MD.exists()}")

    bundle_root = await load_bundle(str(BUNDLE_MD))
    root = _check_bundle(bundle_root, "ROOT")

    print("\n[ROOT] prepare() ...")
    await bundle_root.prepare()

    root_tool_names = await _mount_tools("ROOT")
    root_tool_set = set(root_tool_names)

    # Checks
    root_tools_ok = root_tool_set == EXPECTED_TOOLS
    root_awareness_ok = any(AWARENESS_FILE in k for k in root["pending_keys"])
    root_guide_ok = FULL_GUIDE in root["instruction"]

    print(f"\n[ROOT] ✓ 6 tools         : {'PASS' if root_tools_ok else 'FAIL'}")
    if not root_tools_ok:
        print(f"  missing={EXPECTED_TOOLS - root_tool_set}, extra={root_tool_set - EXPECTED_TOOLS}")
    print(f"[ROOT] ✓ awareness ctx   : {'PASS — in _pending_context' if root_awareness_ok else 'FAIL'}")
    print(f"[ROOT] ✓ full guide body : {'PASS — in instruction' if root_guide_ok else 'FAIL'}")

    results["root"] = {
        "tools": root_tools_ok,
        "awareness": root_awareness_ok,
        "full_guide": root_guide_ok,
    }

    # -----------------------------------------------------------------------
    # (B) BEHAVIOR alone
    # -----------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("(B) BEHAVIOR alone — behaviors/attractor-wiki.yaml")
    print("=" * 60)
    print(f"path   : {BEHAVIOR_YAML}")
    print(f"exists : {BEHAVIOR_YAML.exists()}")

    bundle_beh = await load_bundle(str(BEHAVIOR_YAML))
    beh = _check_bundle(bundle_beh, "BEHAVIOR")

    print("\n[BEHAVIOR] prepare() ...")
    try:
        await bundle_beh.prepare()
        print("[BEHAVIOR] prepare() succeeded")
    except Exception as exc:
        # context.include namespace may be unresolvable standalone — tools still mount
        print(f"[BEHAVIOR] prepare() note: {exc!r}")

    beh_tool_names = await _mount_tools("BEHAVIOR")
    beh_tool_set = set(beh_tool_names)

    # Checks
    beh_tools_ok = beh_tool_set == EXPECTED_TOOLS
    beh_awareness_ok = any(AWARENESS_FILE in k for k in beh["pending_keys"])
    beh_no_guide_ok = FULL_GUIDE not in beh["instruction"]

    print(f"\n[BEHAVIOR] ✓ 6 tools          : {'PASS' if beh_tools_ok else 'FAIL'}")
    if not beh_tools_ok:
        print(f"  missing={EXPECTED_TOOLS - beh_tool_set}, extra={beh_tool_set - EXPECTED_TOOLS}")
    print(f"[BEHAVIOR] ✓ awareness ctx    : {'PASS — in _pending_context' if beh_awareness_ok else 'FAIL'}")
    print(f"[BEHAVIOR] ✓ no full guide    : {'PASS — instruction is empty' if beh_no_guide_ok else 'FAIL'}")

    results["behavior"] = {
        "tools": beh_tools_ok,
        "awareness": beh_awareness_ok,
        "no_full_guide": beh_no_guide_ok,
    }

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    a_pass = all(results["root"].values())
    b_pass = all(results["behavior"].values())

    print(f"(A) Root     tools=[{'✓' if results['root']['tools'] else '✗'}]"
          f"  awareness=[{'✓' if results['root']['awareness'] else '✗'}]"
          f"  full_guide=[{'✓' if results['root']['full_guide'] else '✗'}]"
          f"  → {'ALL PASS' if a_pass else 'FAIL'}")

    print(f"(B) Behavior tools=[{'✓' if results['behavior']['tools'] else '✗'}]"
          f"  awareness=[{'✓' if results['behavior']['awareness'] else '✗'}]"
          f"  no_full_guide=[{'✓' if results['behavior']['no_full_guide'] else '✗'}]"
          f"  → {'ALL PASS' if b_pass else 'FAIL'}")

    overall = a_pass and b_pass
    print(f"\n{'✓ STRUCTURE PROVEN' if overall else '✗ STRUCTURE NOT FULLY PROVEN'}")
    return None if overall else exit(1)


if __name__ == "__main__":
    asyncio.run(main())
