# attractor-wiki — tools mounted

You have 7 wiki automation tools (see [CAPABILITIES.md](../CAPABILITIES.md) for the authoritative list):

| Tool | Purpose |
|---|---|
| `wiki_ingest` | Ingest source file(s) from `raw/` into the wiki, unified 1..N (classify → mine → write_pages → verify → reconcile → provenance_audit → enforce_attribution → weave → review → verify2 → archive). The `classify` stage is a fail-closed input guard: rejects code/binary before any LLM work. Optional `source`: named `raw/source` (N=1) or all files in `raw/` (N=any). |
| `wiki_query` | Read-only Q&A, index-first, cited answer written to `.wiki/query-answer.md` |
| `wiki_lint` | Read-only health check: `verify.sh` + LLM suggestions → `.wiki/lint-report.md` |
| `wiki_publish` | Zip the wiki package via `.wiki/scripts/publish.sh` → `.wiki/dist/` |
| `wiki_init` | Scaffold a new pure-markdown 4-type wiki from a policy brief |
| `wiki_review` | Walk the `flag-queue.json` TODO-VERIFY queue (confirm / correct / promote) |
| `wiki_apply_resolutions` | Apply queued review-queue resolutions to the wiki (LLM apply + deterministic coverage gate) |

All tools require `wiki_dir` (absolute path to the wiki repo root).
`wiki_query` additionally requires `question`; `wiki_ingest` accepts an optional `source` (filename in `raw/`; if omitted, all files in `raw/` are ingested).

The wiki must be initialized (`wiki_init`) before any other tool will work.

Full operational loop and the query→ingest compounding pattern:
`attractor-wiki:context/using-attractor-wiki.md`
