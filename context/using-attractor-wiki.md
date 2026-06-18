# Using attractor-wiki — the LLM Wiki pattern, automated

This is an **attractor-pipeline instantiation of the LLM Wiki pattern**. The *why* —
what an LLM Wiki is and why it beats query-time RAG — lives in Karpathy's idea doc
([gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f); also
vendored in the companion bundle at `amplifier-bundle-llm-wiki/docs/llm-wiki-pattern.md`).
Read that for the pattern. This file is the *how* for this specific tool, and does
not restate it.

The one-line value, in our terms: the wiki is a **persistent, compounding artifact** —
built once and *kept current* by the pipelines, not re-derived from raw sources on
every query. Each ingested source is integrated into cross-referenced, status-tracked
markdown pages; every later question reads the compiled wiki, not the raw pile. The
maintenance cost that makes humans abandon wikis is paid by the pipeline instead.

---

## The shape in one glance

```
6 commands     ingest · query · lint · publish · init · review
   │
   ▼
6 portable .dot files   ← ALL the real work lives here (wiki_attractor/pipelines/*.dot)
   │                       command-named, no Python imports, drop-in portable
   ▼
1 light lib    run_pipeline(dot, wiki_dir, subs, ...)   ← the only code that stands
   │                                                       up + runs the attractor engine
   ├──────────────┬──────────────────────────┐
   ▼              ▼                          ▼
CLI            tool-module                raw .dot drop-in
wiki-attractor  tool-wiki (6 tools)        (bare attractor engine)
```

Three **interchangeable consumers**, same value any way — proven equivalent:

| Consumer | What it is | Use it when |
|---|---|---|
| **CLI** (`wiki-attractor`) | thin click wrapper, one subcommand per dot | a human is at a terminal driving the wiki by hand |
| **tool-module** (`tool-wiki`) | 6 Amplifier tools (`wiki_ingest`, `wiki_query`, `wiki_lint`, `wiki_publish`, `wiki_init`, `wiki_review`) mounted in an AmplifierSession | an agent is given the wiki as native tools and decides when to call them |
| **raw `.dot` drop-in** | the dot files executed by any attractor runner (e.g. `amplifier-resolver-dot-graph`) with nothing from `wiki_attractor` but the dots | embedding the wiki operations inside another engine / pipeline |

The dots are the contract; the lib and the three consumers are thin skins over them.

---

## The operational loop

The Karpathy operations map directly onto our commands:

| Operation | Command | What it does |
|---|---|---|
| **Ingest** | `ingest <source>` | mine a source from `raw/` → write/update pages → reconcile (dedup/orphan-heal) → provenance audit → verify. Touches many pages per source. |
| **Lint** | `lint` | read-only health check: runs `verify.sh`, then surfaces contradictions / stale claims / orphans / concept gaps → `.wiki/lint-report.md`. |
| **Publish** | `publish` | zips the wiki package to `.wiki/dist/` via `.wiki/scripts/publish.sh` (deterministic, no LLM). |
| **Query** | `query <question>` | read-only, **index-first** Q&A with citations. Writes its cited answer to `.wiki/query-answer.md`; CLI/tool return it as `result["output"]`. Never touches the wiki package. |
| **Init** | `init <package> <brief>` | scaffold a new pure-markdown wiki (4-type schema) on an empty dir; plants canonical `verify.sh`/`publish.sh` and authors schema + backbone. |
| **Review** | `review` | optional HITL walk of `flag-queue.json` (the provenance audit's residue) — confirm / correct / promote each flagged claim. |

Two files are the **navigational backbone** (not restated here — see the pattern doc and
the per-project schema): `index.md` is the catalog read first on every query;
`log.md` is the append-only, greppable timeline. `ingest` maintains both.

Everything domain-specific — entity types, frontmatter, the `status: settled|working|unsettled`
discipline, cross-ref conventions — is the **per-project contract** in
**`.wiki/context/schema.md`**. The pipelines read it at runtime; they ship no policy of
their own. To change how *your* wiki is structured, edit the schema, not the dots.

---

## THE COMPOUNDING LOOP (the point)

The single most valuable habit, straight from Karpathy's Query operation:

> *"good answers can be filed back into the wiki as new pages … A comparison you asked
> for, an analysis, a connection you discovered — these are valuable and shouldn't
> disappear into chat history. This way your explorations compound in the knowledge
> base just like ingested sources do."*

`query` is read-only by design — it answers without mutating the wiki. That keeps Q&A
safe, but it also means a good synthesis is, by default, a one-off: it lands in
`.wiki/query-answer.md` and is overwritten by the next question. **An exploration that
stays there has vanished into chat history** — exactly the loss Karpathy warns against.

The loop closes by hand, concretely:

```
query "<a question worth its answer>"      → writes .wiki/query-answer.md (cited)
        │  the answer is good and worth keeping
        ▼
cp .wiki/query-answer.md raw/<slug>.md      → drop the synthesis into the inbox
        ▼
ingest <slug>.md                            → now it's a first-class wiki citizen:
                                              cross-referenced, status-tracked,
                                              indexed, logged, and maintained on
                                              every future ingest/lint — like any source
```

Once filed, the synthesis is no longer a transient answer — it's a page the pipeline
reconciles, provenance-audits, and keeps current as new sources arrive. Your *questions*
enrich the wiki, not just your sources. The wiki gets richer with every question asked,
not only every document added.

**This is operator/agent habit, not (yet) an automatic step.** It's deliberately manual:
not every answer deserves to become a page, and the "is this worth keeping?" judgment is
the human's (or driving agent's) to make. It *could* be automated later — a `query`
variant that offers to file its own answer — but for now it is guidance: when an answer
is worth keeping, `raw/` + `ingest` is how you keep it.

---

## Pointers (worked examples, not restated here)

- **Drop-in contract** — `wiki_attractor/pipelines/README.md`: what each dot expects from
  the host (working dir, `$placeholder` substitutions, project-side files), node-type
  discipline, and a minimal bare-engine runner.
- **The per-project contract** — `.wiki/context/schema.md` in the wiki repo: entity types,
  frontmatter, status enum, cross-ref jobs, ingest invariants. The source of truth for
  *your* wiki's shape.
- **The three consumers, proven** — runnable examples of each path:
  - `drop_in_demo.py` / `drop_in_runner.py` — raw `.dot` executed on a bare attractor engine.
  - `prove_tool_consumer.py` — the `tool-wiki` module mounted in a real AmplifierSession,
    with the agent calling `wiki_query`.
  - the `wiki-attractor` CLI itself — the terminal path (`wiki-attractor --help`).
