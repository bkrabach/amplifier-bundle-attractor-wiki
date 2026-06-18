# attractor-wiki pipeline drop-in contract

The `.dot` files in this directory are **portable attractor pipelines**. Each file
is named after its command (e.g. `ingest.dot` drives `wiki-attractor ingest`). They
are the load-bearing layer of the companion — all real work lives here, not in the
lib or CLI wrapper.

A consumer (e.g. `amplifier-resolver-dot-graph`, a custom pipeline runner, or a
standalone script) can execute these files with nothing from `wiki_attractor` except
the dot files themselves.

---

## Drop-in contract

### What travels with the dots

| File | Purpose |
|------|---------|
| `ingest.dot`  | Mine a source → write pages → reconcile → provenance audit → verify |
| `query.dot`   | Index-first Q&A; writes cited answer to `.wiki/query-answer.md` |
| `lint.dot`    | Run `verify.sh` + LLM surface contradictions/orphans/gaps |
| `publish.dot` | Run `.wiki/scripts/publish.sh`; zips package to `.wiki/dist/` |
| `init.dot`    | Scaffold a new wiki; plants canonical `verify.sh` + `publish.sh` from `$ASSETS` |
| `review.dot`  | HITL walk of `flag-queue.json` (hexagon gate; needs `$PYBIN` + `$HELPER`) |

**Supporting artifacts referenced by the dots:**

| Ref | What it is | Where from |
|-----|-----------|------------|
| `.wiki/context/schema.md` | The wiki's entity schema (project-side) | Project wiki repo |
| `.wiki/scripts/verify.sh` | Structural + provenance verifier (project-side) | Project wiki repo (or `wiki_attractor/assets/verify.sh` as canonical reference) |
| `.wiki/scripts/publish.sh` | Package zipper (project-side) | Project wiki repo (or `wiki_attractor/assets/publish.sh`) |
| `raw/<source>` / `raw/archive/` | Source inbox + archive | Project wiki repo |
| `team-knowledge/` | The wiki package (outcomes, concepts, people, sources) | Project wiki repo |

---

## What each dot expects from the host

### All dots
- **Working directory = wiki repo root** when the pipeline runs (shell commands use
  relative paths like `raw/$source`, `.wiki/scripts/verify.sh`).
- **`.wiki/context/schema.md`** must exist for any command except `init`.

### `ingest.dot`
- **`$source`** substituted into the DOT: the filename in `raw/` to ingest.
- Box (LLM) nodes need an AmplifierSession with filesystem tools (Path B) to
  actually read/write wiki files. With DirectProviderBackend they execute but
  produce degraded output (no file access).

### `query.dot`
- **`$question`** substituted into the DOT.
- Writes the full cited answer to `.wiki/query-answer.md` (the only file it
  writes — it MUST NOT touch `team-knowledge/`).
- The lib reads `.wiki/query-answer.md` back and returns it as `result["output"]`.

### `lint.dot`
- No substitutions needed.
- Writes `.wiki/lint-report.md` with findings.

### `publish.dot`
- No substitutions needed.
- Requires `.wiki/scripts/publish.sh` to exist and be executable.
- A deterministic single-tool-node pipeline; no LLM needed.
  This makes it the cleanest portability proof (runs via `PipelineEngine(backend=None)`).

### `init.dot`
- **`$package`** and **`$brief`** substituted.
- **`$ASSETS`** substituted to the absolute path of the `wiki_attractor/assets/`
  directory (contains the canonical `verify.sh` and `publish.sh`). The dot copies
  them into the new wiki's `.wiki/scripts/`.
- Runs on an **empty or new directory** (no existing wiki needed).

### `review.dot`
- **`$PYBIN`** substituted to the Python executable.
- **`$HELPER`** substituted to the absolute path of `wiki_attractor/review_queue.py`.
- Uses hexagon (human gate) nodes → requires an `Interviewer` in the `HandlerContext`.
  Run via `PipelineEngine` directly, NOT via `AmplifierSession`.
- Requires `team-knowledge/flag-queue.json` to exist (produced by `ingest.dot`'s
  reviewer node).

---

## Drop-in execution (bare engine, no wiki_attractor)

```python
# Minimal drop-in runner for a DETERMINISTIC dot (e.g. publish.dot)
import asyncio, os, tempfile
from pathlib import Path
from amplifier_module_loop_pipeline.context import PipelineContext
from amplifier_module_loop_pipeline.dot_parser import parse_dot
from amplifier_module_loop_pipeline.engine import PipelineEngine
from amplifier_module_loop_pipeline.handlers import HandlerRegistry
from amplifier_module_loop_pipeline.handlers.context import HandlerContext
from amplifier_module_loop_pipeline.transforms import apply_transforms
from amplifier_module_loop_pipeline.validation import validate_or_raise

async def run(dot_file: Path, wiki_dir: Path):
    dot = dot_file.read_text()
    graph = parse_dot(dot)
    ctx = PipelineContext(); apply_transforms(graph, ctx); validate_or_raise(graph)
    engine = PipelineEngine(graph=graph, context=ctx,
        handler_registry=HandlerRegistry(HandlerContext(backend=None)),
        logs_root=tempfile.mkdtemp())
    os.chdir(wiki_dir)
    outcome = await engine.run()
    print(outcome.status.value)

asyncio.run(run(Path("publish.dot"), Path("/my/wiki")))
```

For LLM dots (box nodes), provide a `DirectProviderBackend` or `AmplifierSession`
(see `wiki_attractor/runner.py` for the full `AmplifierSession` path — Path B).

---

## Node-type discipline (quick reference)

| Shape | Handler | LLM? | Used in these dots |
|-------|---------|------|--------------------|
| `Mdiamond` | start | No | All |
| `Msquare` | exit | No | All |
| `parallelogram` | tool (shell) | No | ingest, publish, lint |
| `box` (default) | codergen (LLM) | **Yes** | ingest, query, lint, init |
| `diamond` | conditional/router | No | ingest |
| `hexagon` | human gate | No | review |

---

## Portability note

These dots have **no Python imports** — they are pure DOT graphs. They reference:
- Shell commands in `tool_command` (parallelogram nodes) — these run against the
  host filesystem (the wiki repo the pipeline is pointed at).
- Provider names in `llm_provider` attributes (box nodes) — resolved by the engine's
  backend at runtime.
- `$placeholder` tokens (e.g. `$source`, `$question`) — substituted by the caller
  before the engine sees the DOT text.

Moving a `.dot` to a different attractor runner requires: (1) providing the same
`$placeholder` substitutions, (2) running from the wiki repo root, and (3) ensuring
the project-side `.wiki/` files (`schema.md`, `verify.sh`, `publish.sh`) exist.
