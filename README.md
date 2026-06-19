# amplifier-bundle-attractor-wiki

Attractor-pipeline automation for [LLM Wikis](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f).
Six wiki commands as mountable Amplifier tools, each backed by a portable `.dot` pipeline.

This is the automation companion to [`amplifier-bundle-llm-wiki`](https://github.com/microsoft/amplifier-bundle-llm-wiki) — the interactive mode bundle. Both work against the same project-side wiki (`.wiki/context/schema.md` + `.wiki/scripts/`). This one runs headless.

## What you get

| Tool / Command | What it does |
|---|---|
| `wiki_ingest` / `ingest` | Mine a source from `raw/` into the wiki (mine → write → reconcile → provenance audit → second review → verify) |
| `wiki_query` / `query` | Read-only Q&A: index-first, cited answer written to `.wiki/query-answer.md` |
| `wiki_lint` / `lint` | Health check: `verify.sh` + LLM suggestions → `.wiki/lint-report.md` |
| `wiki_publish` / `publish` | Zip the wiki package via `.wiki/scripts/publish.sh` → `.wiki/dist/` |
| `wiki_init` / `init` | Scaffold a new pure-markdown 4-type wiki from a policy brief |
| `wiki_review` / `review` | Walk the `flag-queue.json` TODO-VERIFY queue (confirm / correct / promote) |

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
```

## Bundle usage (AmplifierSession)

```python
from amplifier_foundation import load_bundle
bundle = await load_bundle("git+https://github.com/bkrabach/amplifier-bundle-attractor-wiki@main")
prepared = await bundle.prepare()
session = await prepared.create_session(session_cwd="/path/to/wiki")
# Agent now has wiki_ingest, wiki_query, wiki_lint, wiki_publish, wiki_init, wiki_review tools
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
