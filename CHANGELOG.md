# Changelog

All notable changes to this bundle will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.0] — 2026-06-24

### Added
- **`full-pass` pipeline** (`full-pass.dot`): periodic whole-wiki global pass — reconcile
  cross-ingest duplicates, re-audit status drift, weave OLD-TO-OLD Memex connections.
  Completes the work the L3 per-ingest scoping defers.
- **`apply-resolutions` pipeline** (`apply-resolutions.dot`): apply resolutions from
  `team-knowledge/review-queue.json`; semantic coverage gate catches incomplete applies;
  idempotent re-runs skip already-sealed items. Deterministic coverage gate added.
- **`ingest-folder` batch command**: meta-command (Python-only, no `.dot` by design) that
  triages and batch-ingests all prose files from a source folder. Skips code/binary loudly.
  Auto-initializes the target wiki if needed.
- **Fail-closed input-type guard** (`classify` node + `classify_source.py`): new first stage
  in `ingest.dot`; binary-sniffs and extension-checks the source file before any LLM work;
  rejects code/binary inputs loudly; any script fault → reject (fail-closed). Ingest pipeline
  is now 11 stages: classify → mine → write_pages → verify → reconcile → provenance_audit →
  enforce_attribution → weave → review → verify2 → archive.
- **Deterministic speaker-attribution enforcement** (`enforce_attribution` node +
  `enforce_speaker_attribution.py`): deterministic script stage in `ingest.dot` that guarantees
  `## Attribution confidence` sections on people pages citing inferred speaker handles.
  Replaces the LLM ATTRIBUTION-CONFIDENCE CHECK (33% per-trial hit rate in A/B eval).
- **`wiki_apply_resolutions` tool** (7th tool in `tool-wiki`): mounts `apply-resolutions`
  as a native AmplifierSession tool. The module now registers 7 tools.
- **`query --save` / `query_save` API**: closes Karpathy's compounding loop automatically —
  the cited answer is saved to `raw/` and immediately ingested as a wiki page.
- **`CAPABILITIES.md`** (repo root): single source of truth for all capability counts and
  surface enumerations (9 CLI commands, 10 API functions, 7 tools, 8 `.dot` pipelines,
  11-stage ingest sequence). Other docs now point here instead of re-enumerating.

### Changed
- Bundle version bumped `0.2.0` → `0.3.0` (pyproject.toml + bundle.md agree at `0.3.0`).
- All doc stale-count references updated: "six"/"6 tools"/"6 commands" corrected and pointed
  to CAPABILITIES.md as the authoritative enumeration.
- Architecture claim corrected: "ALL real work lives in .dot / no Python" retired in favour
  of the honest story — `.dot` pipelines carry the knowledge-mining work; `api.py` provides
  Python-only `ingest-folder` and `query_save` orchestration.

## [0.2.0] — 2026-06-18

### Added
- **Proper bundle structure**: thin root `bundle.md` (includes only) → behavior anchor
  (`behaviors/attractor-wiki.yaml`) that carries the real payload (tools + awareness context).
- `behaviors/attractor-wiki.yaml` — behavior bundle; mounts `tool-wiki` module + thin
  `attractor-wiki-awareness.md` context. Compose onto any bundle to add wiki tools.
- `context/attractor-wiki-awareness.md` — thin always-on tool table (loaded via behavior).
- `context/using-attractor-wiki.md` — full operational guide (@-mentioned in root body).
- `AGENTS.md`, `README.md`, `CHANGELOG.md` — standard repo files.
- `examples/` directory for the 4 worked consumer proofs.

### Changed
- Root `bundle.md` is now a thin composition layer; all tool registration moved to behavior.
- Loose proof/demo scripts moved from repo root to `examples/` (paths updated).
- Bundle version bumped `0.1.0` → `0.2.0`.

## [0.1.0] — 2026-06-18

### Added
- Initial working bundle: `bundle.md` + `modules/tool-wiki` + `wiki_attractor` package.
- 6 wiki commands as both CLI (`wiki-attractor`) and mountable Amplifier tools.
- 6 portable `.dot` pipeline files: `ingest`, `query`, `lint`, `publish`, `init`, `review`.
- In-pipeline reconcile pass + hardened `verify.sh` gate (duplicate-title + orphan detection).
- In-pipeline provenance audit + non-blocking second reviewer + `flag-queue.json`.
- Separate `wiki-review.dot` HITL pipeline (native attractor hexagon gate).
- Fix for `amplifier-bundle-attractor` `loop-agent` Layer-1 base prompt drop (PR #64).
