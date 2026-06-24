# Known Limitations — amplifier-bundle-attractor-wiki v0.1.x

This file is the honest "label on the bottle." It records what is supported and proven,
what is deliberately fenced, and what is known to be untested or limited. Read this before
promoting the tool or deploying it in a new context.

---

## Supported and proven (v1)

The following have been validated through multi-trial evals, end-to-end DTU runs, and/or
independent quality judging.

| Surface | Status |
|---------|--------|
| **CLI** (`wiki-attractor` commands) | ✅ Proven — all 9 commands smoke-tested |
| **Python library** (`import wiki_attractor`) | ✅ Proven — async API (`init`, `ingest`, `ingest_folder`, `query`, `query_save`, `full_pass`, `apply_resolutions`, `review`, `lint`, `publish`) |
| **Input: prose documents** | ✅ Proven — markdown, plain text, articles, blog posts, notes, meeting transcripts |
| **Input: mixed folders** | ✅ Proven — `ingest-folder` walks a directory, triages files, loudly skips unsupported types |
| **Folder → target-dir batch flow** | ✅ Proven — `wiki-attractor ingest-folder SOURCE_FOLDER --target WIKI_DIR` |
| **Reliability: `full-pass`** | ✅ Multi-trial stable (3/3 trials) |
| **Reliability: `apply-resolutions` gate** | ✅ Deterministic after PR #9 (required-page coverage check) |
| **Reliability: `query --save` loop** | ✅ Multi-trial stable (3/3 trials) |
| **Reliability: weave connections** | ✅ Multi-trial stable; 0% content fabrication in grounding eval |
| **Reliability: attribution enforcement** | ✅ Deterministic after PR #8 (v3 named-basis suppression: BARE {0,0,0}, OVER-FLAG {0,0,0}) |
| **Interactive agent (amplifier-app-cli + bundle)** | ✅ Proven — validated end-to-end in a clean DTU: bundle installs via `amplifier bundle add --app` (v0.2.0); the `wiki_*` tools (`wiki_init`, `wiki_ingest`, `wiki_query`, `wiki_lint`, `wiki_publish`, `wiki_review`, `wiki_apply_resolutions`) mounted into an interactive Amplifier agent session; agent ran init → ingest → query producing a verify-clean wiki (6 entity pages, grounded cited answer). Minor nuance: wikilink style can vary between bare-slug (`[[ada-lovelace]]`) and type-prefixed (`[[people/ada-lovelace]]`) forms — both resolve in Obsidian and pass `verify.sh`, but the inconsistency is unfixed. |
| **Dot-graph resolver in Amplifier Resolve** | ✅ Native execution validated — On 2026-06-24 (instance `495b62d97f88`), wiki-attractor's actual `ingest.dot` (unmodified, byte-for-byte) was submitted to the dot-graph resolver via `pipeline: "custom"` + `dot_content: <full DOT>`. **All 14 ingest.dot nodes completed** natively inside the resolver's worker container: `start`, `orient` (shell: `.wiki/context/schema.md` check), `mine` (LLM), `write_pages` (LLM), `verify` (shell: `verify.sh`), `verify_gate` (router), `reconcile` (LLM), `provenance_audit` (LLM), `enforce_attribution` (shell: Python script), `weave` (LLM), `review` (LLM), `verify2` (shell: `verify.sh`), `verify2_gate` (router), `archive` (shell: file move). Confirmed via Resolve API `/api/instances/495b62d97f88/state` — every node shows `status: completed`. The `verify` and `verify2` nodes (both shell: `bash .wiki/scripts/verify.sh`) completing confirms the produced wiki passed structural validation. Total wall time: ~13 min. Stack: `amplifier-bundle-resolve @ e4cad01` (latest, pulled fresh via workspace submodule — the previous wrapper-only run used a stale external checkout with a provisioning bug). **Honest caveats:** (1) `done` (terminal Msquare exit) shows `pending` rather than `completed` — expected: the pipeline terminates when `archive` completes, before the exit node is explicitly executed. (2) Produced wiki content not captured — Gitea sidecar cleaned up after instance completed; a future run should preserve the workspace. (3) Single trial — multi-trial reliability for this mode not yet established. (4) `wiki_attractor` package not installed in the worker — box nodes operate via wiki workspace files + Amplifier session tools; scripts in `.wiki/scripts/` (added to the workspace branch) are self-contained stdlib-only Python. Artifacts: `.amplifier/evaluation/wiki-attractor-dot-resolver/20260624T0345Z-native/`. |

---

## Deliberately fenced (unsupported in v1)

These inputs are **rejected loudly** at the API boundary — no silent garbage, no LLM mining.

| Input type | Behavior | Reason |
|------------|----------|--------|
| **Source code files** (`.py`, `.rs`, `.ts`, `.go`, `.java`, etc.) | `ValueError` with actionable message | The four-type schema (`outcomes/concepts/people/sources`) is prose-only. Code needs a codebase-aware schema not yet built. Convert to a prose description of purpose/design/API contract instead. |
| **Binary files** (images, PDFs, executables, archives) | `ValueError` with actionable message | Same reason. Convert to plain text first. |

---

## Known limitations and unmeasured areas

| Area | Notes |
|------|-------|
| **Full-pass context cliff (~200+ pages)** | The `full-pass` pipeline reads all wiki pages into a single LLM context. This will fail or degrade above approximately 200 pages (exact limit depends on page lengths). The pipeline header documents this; a fan-out-by-type solution is not yet built. Don't rely on `full-pass` for very large wikis without testing. |
| **Cost not formally measured** | Rough wall-time guidance: `init` ~75s, `ingest` ~10–15 min/source, `full-pass` ~13 min on ~40-page wiki. Token counts and dollar costs have not been formally measured — actual costs depend heavily on source size and wiki growth. |
| **Library calls are async-only and long-running** | All public API functions are `async` coroutines. Each call may run for minutes (it's driving attractor pipelines with multiple LLM round-trips). Callers must handle this in their async context and should not expect quick responses. |
| **Clean-room install from public repo** | The repo is currently private (`bkrabach/amplifier-bundle-attractor-wiki`). A cold `uv tool install` from a public URL has not been tested end-to-end by a new user. This is the expected path before any broader promotion. |
| **Schema is fixed at four entity types** | `outcomes`, `concepts`, `people`, `sources`. If your knowledge domain needs other types, you must adapt the schema and update the pipelines — the current pipelines hardcode this set. |
| **Single Anthropic API key required** | The pipelines use `claude-sonnet-*` (latest sonnet via the routing-matrix glob). Only Anthropic is supported; multi-provider support is not implemented. |
| **Node variance is unmeasured for most nodes** | Multi-trial reliability evals were run for `apply-resolutions` gate, attribution enforcement, `full-pass`, and `query-save`. The other nodes (`mine`, `write_pages`, `reconcile`, `provenance_audit`, `review`) have not been variance-tested — their output varies across runs in ways that have not been formally quantified. |
| **One corpus used for all tuning** | All evals and prompt tuning were done on a single team's documents (Amplifier engineering team content). Transfer to other teams' vocabulary, document formats, and domain structure has been tested once (transcript shakedown) but not systematically. |

---

## What "proven" means here

Multi-trial evals in this project follow a specific standard:

- **Multi-trial A/B**: same starting state, only one variable changed, ≥3 trials per arm
- **Deterministic oracles first**: `verify.sh`, grep-based checks, file existence checks — before any LLM judgment
- **Independent blind judges**: LLM quality judgments are run blind (arm identity hidden from judge) from a clean context
- **PR#7 lesson**: single-shot proofs of non-deterministic LLM steps have been proven to produce false positives (one fix in this project initially looked clean on a single run, failed on 2 of 3 subsequent trials). Multi-trial is the minimum standard for anything involving LLM output.

Claims of "proven" in this document meet this standard. Claims labeled ❓ do not.
