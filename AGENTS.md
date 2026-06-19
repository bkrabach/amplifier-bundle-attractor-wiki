# amplifier-bundle-attractor-wiki — Maintainer & Agent Orientation

This is the **attractor-pipeline automation companion** to
[`amplifier-bundle-llm-wiki`](https://github.com/microsoft/amplifier-bundle-llm-wiki).
It exposes the six LLM Wiki workflow operations as mountable Amplifier tools, each
backed by a portable `.dot` pipeline file.

## Layout

```
bundle.md                         ← thin root: includes + @-mention body
behaviors/attractor-wiki.yaml     ← THE PAYLOAD: 6 tool-wiki tools + thin awareness context
context/
  attractor-wiki-awareness.md     ← thin always-on tool table (mounted via behavior)
  using-attractor-wiki.md         ← full operational guide (@-mentioned in root body)
modules/tool-wiki/                ← Amplifier tool module: 6 mountable wiki tools
  amplifier_module_tool_wiki/
wiki_attractor/                   ← the Python package (CLI + lib + dots)
  pipelines/*.dot                 ← THE REAL WORK — 6 command-named portable .dot files
  profiles/wiki-agent-anthropic.yaml
  runner.py                       ← single public entry: run_pipeline(dot, wiki_dir, ...)
  registry.py                     ← data-driven registry; adding a command = 1 PipelineSpec
  cli.py                          ← thin click wrapper; 6 commands auto-generated from registry
pyproject.toml                    ← wiki-attractor CLI (console_scripts entry point)
examples/                         ← worked proofs of all 3 consumer arms
  prove_bundle.py                 ← load_bundle → 6 tools mounted
  prove_tool_consumer.py          ← tool-module in a real AmplifierSession
  drop_in_demo.py                 ← raw .dot via bare PipelineEngine (no wiki_attractor)
  drop_in_runner.py               ← raw .dot via bare AmplifierSession (no wiki_attractor)
UPSTREAM-ISSUE-context-include.md ← open issue filed against amplifier-bundle-attractor
```

## The three-layer shape

```
wiki_attractor/pipelines/*.dot   ← ALL real work; portable; no Python imports
           ↑
    wiki_attractor.runner         ← single entry: run_pipeline(dot, wiki_dir, ...)
     ↑              ↑              ↑
  CLI            tool-module    raw .dot drop-in
  (click)        (mount-on-session)  (direct PipelineEngine)
```

## Consumer options

| Consumer | How | Use when |
|---|---|---|
| `wiki-attractor` CLI | `uv tool install .` then `wiki-attractor ingest <source>` | Interactive or scripted local use |
| Amplifier bundle | `load_bundle("bundle.md")` or `attractor-wiki:` bundle ref | Add wiki tools to any AmplifierSession |
| Raw `.dot` drop-in | Copy a `.dot` from `wiki_attractor/pipelines/` | Third-party engine without this package |

## Dogfooding note

This repo is itself an example of the pattern it provides. The `team-knowledge-wiki`
in the dev workspace was built using the interactive `amplifier-bundle-llm-wiki` bundle;
the attractor automation was eval-driven against the same source set.

## Operating tips

- All 6 tools need `wiki_dir` = absolute path to an initialized wiki repo root.
- `wiki_init` must run first before any other tool works.
- Adding a new command: one `PipelineSpec` entry in `registry.py` + one `<name>.dot` in `wiki_attractor/pipelines/`. Zero new dispatch code.
- The `.dot` files are the authoritative interface. Treat them as public API.
