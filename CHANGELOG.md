# Changelog

All notable changes to this bundle will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
