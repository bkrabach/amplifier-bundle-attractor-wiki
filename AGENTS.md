# amplifier-bundle-attractor-wiki — Maintainer & Agent Orientation

This is the **attractor-pipeline automation companion** to
[`amplifier-bundle-llm-wiki`](https://github.com/microsoft/amplifier-bundle-llm-wiki).
It exposes the wiki workflow operations as mountable Amplifier tools (see [CAPABILITIES.md](CAPABILITIES.md)
for the authoritative list), each backed by a portable `.dot` pipeline file.

## Layout

```
CAPABILITIES.md                   ← SINGLE SOURCE OF TRUTH: commands, tools, pipelines, stages
bundle.md                         ← thin root: includes + @-mention body
behaviors/attractor-wiki.yaml     ← THE PAYLOAD: 7 tool-wiki tools + thin awareness context
context/
  attractor-wiki-awareness.md     ← thin always-on tool table (mounted via behavior)
  using-attractor-wiki.md         ← full operational guide (@-mentioned in root body)
modules/tool-wiki/                ← Amplifier tool module: 7 mountable wiki tools
  amplifier_module_tool_wiki/
wiki_attractor/                   ← the Python package (CLI + lib + dots)
  pipelines/*.dot                 ← THE KNOWLEDGE-MINING WORK — 8 portable .dot files
  profiles/wiki-agent-anthropic.yaml
  runner.py                       ← single public entry: run_pipeline(dot, wiki_dir, ...)
  registry.py                     ← data-driven registry; adding a command = 1 PipelineSpec
  api.py                          ← bespoke typed API; named fn per command; ingest-folder lives here
  cli.py                          ← thin click wrapper; commands auto-generated from registry
pyproject.toml                    ← wiki-attractor CLI (console_scripts entry point)
examples/                         ← worked proofs of all 3 consumer arms
  prove_bundle.py                 ← load_bundle → 7 tools mounted
  prove_tool_consumer.py          ← tool-module in a real AmplifierSession
  drop_in_demo.py                 ← raw .dot via bare PipelineEngine (no wiki_attractor)
  drop_in_runner.py               ← raw .dot via bare AmplifierSession (no wiki_attractor)
UPSTREAM-ISSUE-context-include.md ← open issue filed against amplifier-bundle-attractor
```

## The three-layer shape

The knowledge-mining work — including the fail-closed input-type guard — runs in portable
`.dot` pipelines. A thin Python layer in `api.py` provides CLI/library orchestration that
the attractor environment supplies differently: the `ingest-folder` batch meta-command
(repeated `ingest` over a folder) and early-exit convenience wrappers.
`ingest-folder` has no `.dot` by design.

```
wiki_attractor/pipelines/*.dot   ← knowledge-mining work (8 portable .dot files)
           ↑
    wiki_attractor.runner         ← single entry: run_pipeline(dot, wiki_dir, ...)
     ↑              ↑              ↑
  CLI            tool-module    raw .dot drop-in
  (click)        (mount-on-session)  (direct PipelineEngine)
           ↑
    wiki_attractor.api            ← ingest-folder, query_save, early-exit wrappers (Python only)
```

## Consumer options

| Consumer | How | Use when |
|---|---|---|
| `wiki-attractor` CLI | `uv tool install .` then `wiki-attractor ingest [source]` | Interactive or scripted local use |
| Amplifier bundle | `load_bundle("bundle.md")` or `attractor-wiki:` bundle ref | Add wiki tools to any AmplifierSession |
| Raw `.dot` drop-in | Copy a `.dot` from `wiki_attractor/pipelines/` | Third-party engine without this package |

## Dogfooding note

This repo is itself an example of the pattern it provides. The `team-knowledge-wiki`
in the dev workspace was built using the interactive `amplifier-bundle-llm-wiki` bundle;
the attractor automation was eval-driven against the same source set.

## Operating tips

- All 7 tools need `wiki_dir` = absolute path to an initialized wiki repo root (see [CAPABILITIES.md](CAPABILITIES.md) for the authoritative tool list).
- `wiki_init` must run first before any other tool works.
- Adding a new `.dot`-backed command: one `PipelineSpec` entry in `registry.py` + one `<name>.dot` in `wiki_attractor/pipelines/`. Zero new dispatch code.
- `ingest-folder` is intentionally Python-only (no `.dot`) — it orchestrates multiple pipeline runs.
- The `.dot` files are the authoritative interface for the knowledge-mining work. Treat them as public API.
