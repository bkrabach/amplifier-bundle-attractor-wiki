# CAPABILITIES.md — attractor-wiki authoritative capability enumeration

This is the **single source of truth** for all capability counts and surface enumerations.
Every other doc in this repo that names counts or lists of commands/tools/pipelines
points here rather than re-enumerating. When a count or list drifts, fix it here first.

---

## CLI commands (9)

Registered via `wiki_attractor/registry.py` + `wiki_attractor/cli.py`.

| Command | Summary |
|---|---|
| `ingest [source]` | Ingest source file(s) from `raw/` through the unified 1..N pipeline (classify → … → archive). With `source`: validates that `raw/source` exists, then processes all files in `raw/`. Without `source`: processes all files currently in `raw/`. N=1 behaves identically to the old single-file ingest; N>1 adds cross-source synthesis. |
| `query <question>` | Read-only Q&A: index-first drill, cited answer written to `.wiki/query-answer.md`. `--save` closes the compounding loop (saves answer to `raw/` and ingests it). |
| `lint` | Read-only health check: `verify.sh` + LLM surfaces contradictions/stale/orphans → `.wiki/lint-report.md`. |
| `publish` | Zip the wiki package via `.wiki/scripts/publish.sh` → `.wiki/dist/`. |
| `init <package> <brief>` | Scaffold a new pure-markdown 4-type wiki on an empty directory. |
| `review [--decisions C,X,P]` | Walk the `flag-queue.json` HITL: confirm / correct / promote each flagged claim. |
| `full-pass` | Periodic whole-wiki global pass: reconcile cross-ingest duplicates, re-audit status drift, weave OLD-TO-OLD connections. |
| `apply-resolutions` | Apply resolutions from `team-knowledge/review-queue.json` (LLM apply + semantic coverage gate; idempotent). |
| `ingest-folder <source_folder> [--target]` | Batch-ingest all prose files from a folder; triages and skips code/binary files loudly; auto-initializes the target wiki if needed. **Meta-command: no `.dot` by design** — orchestrates repeated `ingest` calls from Python. |

---

## Public API (10)

Exported from `wiki_attractor/__all__` (source: `wiki_attractor/__init__.py`):

`apply_resolutions`, `full_pass`, `ingest`, `ingest_folder`, `init`, `lint`, `publish`, `query`, `query_save`, `review`

`query_save` is the programmatic counterpart to `query --save`: run query, write answer to `raw/`, ingest it.

---

## Mounted tools (7)

The `tool-wiki` Amplifier module (`modules/tool-wiki/amplifier_module_tool_wiki/`) registers 7 tools in `_TOOLS`:

| Tool | Purpose |
|---|---|
| `wiki_ingest` | Ingest source file(s) from `raw/` into the compiled wiki (unified 1..N pipeline). Optional `source` arg: names a specific file; omit to process all files in `raw/`. |
| `wiki_query` | Read-only Q&A against the compiled wiki (index-first, cited answer). |
| `wiki_lint` | Read-only health check: `verify.sh` + surface issues → lint report. |
| `wiki_publish` | Publish the wiki package (zip to `.wiki/dist/`). |
| `wiki_init` | Scaffold a new pure-markdown wiki repo with 4-type schema. |
| `wiki_review` | Walk the `flag-queue.json` headlessly (auto-confirm or explicit C/X/P decisions). |
| `wiki_apply_resolutions` | Apply resolutions from `review-queue.json` with a semantic coverage gate; idempotent. |

All tools require `wiki_dir` (absolute path to an initialized wiki repo root).
`wiki_ingest` accepts an optional `source` (filename in `raw/`; if omitted, all files in `raw/` are ingested).
`wiki_query` also requires `question`.

---

## Portable `.dot` pipelines (8)

Located in `wiki_attractor/pipelines/`. Each file is named after its command.

| File | Drives |
|---|---|
| `ingest.dot` | `wiki-attractor ingest` — 11-stage knowledge-mining pipeline |
| `query.dot` | `wiki-attractor query` — index-first Q&A, cited answer |
| `lint.dot` | `wiki-attractor lint` — `verify.sh` + LLM health report |
| `publish.dot` | `wiki-attractor publish` — deterministic zip-to-dist (no LLM) |
| `init.dot` | `wiki-attractor init` — scaffold new wiki, plant canonical scripts |
| `review.dot` | `wiki-attractor review` — HITL flag-queue walk (hexagon gate) |
| `full-pass.dot` | `wiki-attractor full-pass` — periodic whole-wiki reconcile + weave pass |
| `apply-resolutions.dot` | `wiki-attractor apply-resolutions` — resolution application with deterministic coverage gate |

`ingest-folder` has **no `.dot`** by design; it is a Python meta-command that calls `ingest` (and `init`) repeatedly.

---

## Ingest pipeline stage sequence (11 stages)

Defined in `wiki_attractor/pipelines/ingest.dot`.

```
classify → mine → write_pages → verify → reconcile → provenance_audit → enforce_attribution → weave → review → verify2 → archive
```

Stage descriptions:

| Stage | Type | Role |
|---|---|---|
| `classify` | deterministic shell | **Fail-closed input-type guard.** Runs `classify_source.py` before any LLM work. Binary-sniffs (NUL bytes / UTF-8 failure → reject), then checks extension (code → reject, prose → accept). Any fault → reject. There is NO path from a non-accept to `mine`. |
| `mine` | LLM | Reads the source, extracts entities per schema, writes concrete ingest plan to `.wiki/ingest-plan.md`. |
| `write_pages` | LLM | Creates/edits wiki pages, updates `index.md` + `log.md`, cites every claim. |
| `verify` | deterministic shell | Runs `verify.sh`; routes `clean` → reconcile, `dirty` → write_pages retry. |
| `reconcile` | LLM (L3-scoped) | Dedup/merge in the changed-page neighborhood; heals dangling wikilinks. |
| `provenance_audit` | LLM (L3-scoped) | Audits claim support for changed pages; writes `flag-queue.json`. |
| `enforce_attribution` | deterministic shell | Guarantees speaker-attribution sections on people pages (0% LLM; idempotent). |
| `weave` | LLM (L3-scoped) | Generates new grounded associative trails between distinct pages. Adds only; never deletes. |
| `review` | LLM | Independent second-reviewer; adjudicates TODO-VERIFY flags before any human sees them. |
| `verify2` | deterministic shell | Second `verify.sh` gate; routes `clean` → archive, `dirty` → reconcile retry. |
| `archive` | deterministic shell | Moves ingested source from `raw/` to `raw/archive/`. |
