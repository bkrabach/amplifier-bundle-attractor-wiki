---
bundle:
  name: attractor-wiki
  version: 0.1.0
  description: >
    Attractor-pipeline automation for LLM Wikis. Exposes six wiki commands as
    mountable Amplifier tools: ingest, query, lint, publish, init, and review.
    Each tool drives a portable command-named .dot pipeline file. Load this bundle
    to add wiki automation to any AmplifierSession — no separate CLI install needed.

    Tools provided: wiki_ingest, wiki_query, wiki_lint, wiki_publish, wiki_init,
    wiki_review

    Source: https://github.com/bkrabach/amplifier-bundle-attractor-wiki

# No upstream includes needed: tool-wiki runs its own internal AmplifierSession
# (via wiki_attractor.runner.run_pipeline) for each tool invocation. Composing
# attractor or llm-wiki at this level would be dead weight — the tools are
# self-contained in their execution model.
#
# For published consumption: replace the source with the git URL below once the
# repo is live at bkrabach/amplifier-bundle-attractor-wiki:
#   source: git+https://github.com/bkrabach/amplifier-bundle-attractor-wiki@main#subdirectory=modules/tool-wiki

tools:
  - module: tool-wiki
    source: ./modules/tool-wiki
---

# attractor-wiki

Amplifier bundle for LLM Wiki automation via attractor pipelines. Loading this bundle
mounts six wiki tools into any AmplifierSession:

| Tool | Purpose |
|---|---|
| `wiki_ingest` | Mine a source from `raw/` into the wiki (mine → write → reconcile → provenance → review → verify) |
| `wiki_query` | Index-first Q&A against the wiki — cited answer written to `.wiki/query-answer.md` |
| `wiki_lint` | Read-only health check: `verify.sh` + LLM suggestions, report at `.wiki/lint-report.md` |
| `wiki_publish` | Zip the wiki package via `.wiki/scripts/publish.sh` → `.wiki/dist/` |
| `wiki_init` | Scaffold a new pure-markdown 4-type wiki from a policy brief (delegates to `wiki-policy-designer`) |
| `wiki_review` | Walk the `flag-queue.json` TODO-VERIFY queue — guided HITL: confirm / correct / promote |

Each tool is backed by a portable command-named `.dot` pipeline file in `wiki_attractor/pipelines/`.
The `.dot` files are the real work; this bundle is the mountable delivery mechanism.

See `context/using-attractor-wiki.md` for the operational loop and the query→ingest compounding pattern.
