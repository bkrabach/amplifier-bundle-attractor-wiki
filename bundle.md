---
bundle:
  name: attractor-wiki
  version: 0.3.0
  description: >
    Attractor-pipeline automation for LLM Wikis. Exposes the wiki tools (see
    CAPABILITIES.md for the authoritative list) as mountable Amplifier tools:
    wiki_ingest, wiki_query, wiki_lint, wiki_publish, wiki_init, wiki_review,
    wiki_apply_resolutions. Each tool drives a portable command-named .dot pipeline
    file. Load this bundle to add wiki automation to any AmplifierSession — no
    separate CLI install needed.

# Thin root: only includes. All real payload (tools + thin awareness context)
# lives in the behavior; the full operational guide is @-mentioned below.
includes:
  - bundle: attractor-wiki:behaviors/attractor-wiki
---

# attractor-wiki

@attractor-wiki:context/using-attractor-wiki.md
