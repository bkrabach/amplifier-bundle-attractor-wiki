# amplifier-bundle-attractor-wiki

Attractor-pipeline automation for [LLM Wikis](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f).
Nine wiki commands (7 as mountable Amplifier tools), each backed by a portable `.dot` pipeline.
See [CAPABILITIES.md](CAPABILITIES.md) for the authoritative list of commands, tools, and pipelines.

This is the automation companion to [`amplifier-bundle-llm-wiki`](https://github.com/microsoft/amplifier-bundle-llm-wiki) — the interactive mode bundle. Both work against the same project-side wiki (`.wiki/context/schema.md` + `.wiki/scripts/`). This one runs headless.

## What you get

| Tool / Command | What it does |
|---|---|
| `wiki_ingest` / `ingest` | Ingest a source from `raw/`: classify (fail-closed input guard) → mine → write → verify → reconcile → enforce_attribution → weave → review → archive |
| `wiki_query` / `query` | Read-only Q&A: index-first, cited answer written to `.wiki/query-answer.md`. `--save` closes the compounding loop. |
| `wiki_lint` / `lint` | Health check: `verify.sh` + LLM suggestions → `.wiki/lint-report.md` |
| `wiki_publish` / `publish` | Zip the wiki package via `.wiki/scripts/publish.sh` → `.wiki/dist/` |
| `wiki_init` / `init` | Scaffold a new pure-markdown 4-type wiki from a policy brief |
| `wiki_review` / `review` | Walk the `flag-queue.json` TODO-VERIFY queue (confirm / correct / promote) |
| `wiki_apply_resolutions` / `apply-resolutions` | Apply queued review-queue resolutions (LLM apply + deterministic coverage gate; idempotent) |
| — / `full-pass` | Periodic whole-wiki pass: reconcile cross-ingest duplicates, re-audit status drift, weave OLD-TO-OLD connections |
| — / `ingest-folder` | Batch-ingest all prose files from a folder; triages and skips code/binary loudly; auto-inits target wiki |

See [CAPABILITIES.md](CAPABILITIES.md) for the full authoritative enumeration of all 9 CLI commands, 10 public API functions, 7 mounted tools, and 8 `.dot` pipelines.

## Install

```bash
# CLI
uv tool install git+https://github.com/bkrabach/amplifier-bundle-attractor-wiki@main

# Or load as an Amplifier bundle in a session
load_bundle("git+https://github.com/bkrabach/amplifier-bundle-attractor-wiki@main")
```

## CLI usage

```bash
cd <your-wiki-repo>
wiki-attractor init   --package team-knowledge --brief "..."   # first time
wiki-attractor ingest mission-and-thesis.md
wiki-attractor lint
wiki-attractor query "what is Team Pulse and what role does it play?"
wiki-attractor publish
wiki-attractor review   # walk the flag queue
wiki-attractor full-pass   # periodic whole-wiki pass
wiki-attractor apply-resolutions   # apply review-queue resolutions
wiki-attractor ingest-folder ./raw-sources --target ./my-wiki   # batch ingest
```

## Bundle usage (AmplifierSession)

```python
from amplifier_foundation import load_bundle
bundle = await load_bundle("git+https://github.com/bkrabach/amplifier-bundle-attractor-wiki@main")
prepared = await bundle.prepare()
session = await prepared.create_session(session_cwd="/path/to/wiki")
# Agent now has the wiki tools mounted (see CAPABILITIES.md for the authoritative list)
```

## Compose as a behavior

```yaml
# In your own bundle.md
includes:
  - bundle: git+https://github.com/bkrabach/amplifier-bundle-attractor-wiki@main#subdirectory=behaviors/attractor-wiki.yaml
```

## Operational loop

See [`context/using-attractor-wiki.md`](context/using-attractor-wiki.md) for the full operational loop, the query→ingest compounding pattern, and worked examples of all three consumer arms.

## Prerequisites

- An initialized wiki repo (run `wiki-attractor init` first)
- Anthropic API key (`ANTHROPIC_API_KEY`) — the pipelines use `claude-sonnet-*`
- The wiki must have `.wiki/context/schema.md` and `.wiki/scripts/verify.sh`

## License

MIT
