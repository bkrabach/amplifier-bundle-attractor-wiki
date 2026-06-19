#!/usr/bin/env python3
"""
ROB GATE — prove load_bundle() on bundle.md mounts all 6 wiki tools.
Run with: /home/bkrabach/.local/share/uv/tools/amplifier/bin/python examples/prove_bundle.py
"""

from __future__ import annotations

import asyncio
from pathlib import Path


BUNDLE_MD = Path(__file__).parent.parent / "bundle.md"


async def main() -> None:
    from amplifier_foundation import load_bundle

    print(f"[prove] bundle.md path : {BUNDLE_MD}")
    print(f"[prove] bundle.md exists: {BUNDLE_MD.exists()}")

    # Step 1 — load the bundle
    print("\n[prove] load_bundle() ...")
    bundle = await load_bundle(str(BUNDLE_MD))
    print(f"[prove] name    : {bundle.name}")
    print(f"[prove] version : {bundle.version}")
    print(f"[prove] tools   : {bundle.tools}")

    # Step 2 — to_mount_plan (no session needed — just inspect the plan)
    print("\n[prove] to_mount_plan() ...")
    plan = bundle.to_mount_plan()
    tools_in_plan = plan.get("tools", [])
    print(f"[prove] mount plan keys : {list(plan.keys())}")
    print(f"[prove] tools entries   : {len(tools_in_plan)}")
    for t in tools_in_plan:
        print(f"  module: {t.get('module')}  source: {t.get('source')}")

    # Step 3 — prepare() so the module actually installs and its entry point is registered
    print("\n[prove] prepare() (will install tool-wiki from ../modules/tool-wiki) ...")
    prepared = await bundle.prepare()
    print(f"[prove] prepared type: {type(prepared).__name__}")

    # Step 4 — inspect the resolver for the registered tool-wiki module
    print("\n[prove] inspecting prepared bundle for wiki tools ...")
    # The resolver knows which modules got activated
    resolver = prepared.resolver
    if hasattr(resolver, "_resolved") or hasattr(resolver, "_modules"):
        attr = getattr(resolver, "_resolved", None) or getattr(resolver, "_modules", {})
        print(f"[prove] resolver data: {attr}")

    # Step 5 — verify the module's entry point is now importable
    print("\n[prove] import check: amplifier_module_tool_wiki ...")
    import importlib.util

    spec = importlib.util.find_spec("amplifier_module_tool_wiki")
    if spec:
        print(f"[prove] FOUND at: {spec.origin}")
    else:
        print("[prove] NOT FOUND in sys path")

    # Step 6 — actually mount the tools via a coordinator stub to get the real list
    print("\n[prove] mount() via async stub coordinator ...")
    from unittest.mock import AsyncMock, MagicMock

    coordinator = MagicMock()
    coordinator.mount = AsyncMock()

    if spec:
        from amplifier_module_tool_wiki import mount

        result = await mount(coordinator)
        print(f"[prove] mount() return: {result}")
        calls = coordinator.mount.call_args_list
        tool_names = [
            c[1].get("name", c[0][1].name if len(c[0]) > 1 else "?") for c in calls
        ]
        print(f"[prove] tools registered ({len(tool_names)}): {tool_names}")

        expected = {
            "wiki_ingest",
            "wiki_query",
            "wiki_lint",
            "wiki_publish",
            "wiki_init",
            "wiki_review",
        }
        found = set(tool_names)
        missing = expected - found
        extra = found - expected
        if not missing and not extra:
            print("\n[prove] ✓ ALL 6 WIKI TOOLS PRESENT — bundle.md PROVEN")
        else:
            print(f"\n[prove] ✗  missing={missing}  extra={extra}")
    else:
        print("[prove] SKIP mount() — module not importable; install failed")

    print("\n[prove] SUMMARY")
    print(f"  bundle.name = {bundle.name!r}")
    print(f"  tools in plan = {[t.get('module') for t in tools_in_plan]}")


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
