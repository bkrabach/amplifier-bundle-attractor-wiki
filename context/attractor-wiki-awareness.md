# attractor-wiki — tools mounted

You have 6 wiki automation tools:

| Tool | Purpose |
|---|---|
| `wiki_ingest` | Mine a source from `raw/` into the wiki (mine → write → reconcile → verify) |
| `wiki_query` | Read-only Q&A, index-first, cited answer written to `.wiki/query-answer.md` |
| `wiki_lint` | Read-only health check: `verify.sh` + LLM suggestions → `.wiki/lint-report.md` |
| `wiki_publish` | Zip the wiki package via `.wiki/scripts/publish.sh` → `.wiki/dist/` |
| `wiki_init` | Scaffold a new pure-markdown 4-type wiki from a policy brief |
| `wiki_review` | Walk the `flag-queue.json` TODO-VERIFY queue (confirm / correct / promote) |

All tools require `wiki_dir` (absolute path to the wiki repo root).
`wiki_query` additionally requires `question`; `wiki_ingest` requires `source` (filename in `raw/`).

The wiki must be initialized (`wiki_init`) before any other tool will work.

Full operational loop and the query→ingest compounding pattern:
`attractor-wiki:context/using-attractor-wiki.md`
