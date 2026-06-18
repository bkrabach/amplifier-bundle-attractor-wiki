<!-- DRAFT upstream issue for github.com/microsoft/amplifier-bundle-attractor.
     Not filed. Review, then file via gh. -->

# `context.include` is silently dropped for child agents spawned by pipelines (loop-agent rebuilds the system prompt and never consults the context manager)

## Summary

A bundle's `context.include` files are **not** delivered to the system context of
an agent running under `loop-agent` — which is every child agent a `loop-pipeline`
box/codergen node spawns. Foundation correctly resolves the include and registers a
system-prompt factory on the child's context manager, and `context-simple` correctly
honors that factory in `get_messages_for_request()`. But `loop-agent`'s
`AgentSession` builds its own 5-layer system prompt from scratch and **never calls
the context manager for the system prompt**, then strips every other system message.
The factory is dead code under `loop-agent`, so any `context.include` content
silently no-ops. This breaks cross-bundle composition: composing any bundle's
orientation/instruction context into a pipeline child appears to work (the bundle
loads, the context dict is populated, the foundation guard passes) but the content
never reaches the model — with no error or warning. Notably the attractor agent
base profile's own `context.include: [context/system-anthropic.md]` is also dropped.

## Environment

- `amplifier-bundle-attractor@main` (modules/loop-pipeline + modules/loop-agent), checked out at HEAD
- `amplifier-foundation` (tool venv `amplifier_foundation`, `amplifier_core 1.0.7`)
- `amplifier-module-context-simple@main`
- Provider: anthropic, model glob `claude-sonnet-*`
- Runner: Path-B `AmplifierSession` + `loop-pipeline` orchestrator + `session.spawn`
  capability (the documented `docs/APP-INTEGRATION-GUIDE.md` reference impl)

## Minimal repro

A self-contained 2-node pipeline whose single box node spawns a child agent whose
bundle declares one `context.include` file containing an un-guessable sentinel. The
node is told to use **no tools** and echo the sentinel purely from its system
context. Session cwd is an empty dir, so the sentinel is unreachable via filesystem
tools — the only way to echo it is if `context.include` reached the system prompt.

**`sentinel-context.md`** (the include file):
```
SENTINEL=ZORBLATT-9931-QUACKFISH-7720
```

**`sentinel-agent.yaml`** (child profile = attractor anthropic base + the include):
```yaml
bundle: {name: sentinel-agent, version: 0.1.0}
includes:
  - bundle: git+https://github.com/microsoft/amplifier-bundle-attractor@main#subdirectory=agents/attractor-agent-anthropic.yaml
context:
  include:
    - sentinel-context.md
```

**Pipeline** (`start -> echo -> done`); the `echo` box node prompt:
> Do NOT use any tools. Look ONLY at your own system prompt / orientation context.
> If it contains a token of the form `SENTINEL=<value>`, output that line exactly.
> Otherwise output exactly: `NO-SENTINEL-IN-CONTEXT`.

Run the pipeline with the loop-pipeline orchestrator + a `session.spawn` capability
that does `child_bundle = await load_bundle("sentinel-agent.yaml")` and
`prepared.spawn(child_bundle=child_bundle, instruction=..., ...)` (exactly the
documented reference spawn capability).

### Expected vs actual

| | |
|---|---|
| **Expected** | Node outputs `SENTINEL=ZORBLATT-9931-QUACKFISH-7720` (the include reached its system context) |
| **Actual**   | Node outputs `NO-SENTINEL-IN-CONTEXT` — pipeline `status: success`, `echo: success` |

Verbatim run result:
```
node_statuses : {'start': 'success', 'echo': 'success'}
notes         : Plain text response: NO-SENTINEL-IN-CONTEXT
```

### Instrumentation (rules out the "context not loaded" theory)

Printed at spawn time, immediately before `prepared.spawn`:

```
child_bundle (after load_bundle):
  context = {
    'attractor-agent-anthropic:context/system-anthropic.md': <cache>/agents/context/system-anthropic.md,
    'sentinel-agent:sentinel-context.md': /tmp/ctx-include-repro/sentinel-context.md,
  }
  _pending_context = {}
effective = parent.compose(child) [what foundation.spawn checks]:
  context = { ...both entries, resolved real paths... }
  _pending_context = {}
foundation spawn guard (effective.instruction or effective.context) = True
```

So the include **is** resolved onto the bundle, survives `compose`, and the
foundation guard that gates context wiring is `True`. The content is present and
correctly plumbed up to the spawn boundary — it is dropped *after* that, inside the
child agent's prompt assembly.

## Root cause (pinned to file:line)

The system-prompt path forks at the child orchestrator. Two layers do their job; the
third bypasses them:

1. **Foundation `spawn()` — correct.**
   `amplifier_foundation/bundle/_prepared.py:869-881`: when
   `effective_bundle.instruction or effective_bundle.context` (True here), it builds
   the system-prompt factory and registers it on the child's context manager via
   `await context.set_system_prompt_factory(factory)`.

2. **`context-simple` — correct.**
   `amplifier_module_context_simple/__init__.py:254-258`
   (`get_messages_for_request`): if a `_system_prompt_factory` is set, it calls the
   factory and injects `{"role": "system", "content": <include content>}`. So *iff*
   the agent loop asks the context manager for its request messages, the include
   would appear.

3. **`loop-agent` — the drop.**
   `modules/loop-agent/amplifier_module_loop_agent/agent_session.py`:
   - `_build_system_prompt_text()` (**lines 497-545**) assembles the system prompt
     from exactly **five** layers: `config.system_prompt` (base), environment, tool
     descriptions, project docs (`AGENTS.md`/`CLAUDE.md` discovered from disk), and
     `config.user_instructions`. **The bundle's `context.include` is not one of these
     layers.**
   - `_convert_history_to_messages()` (**lines 558-567**) builds messages from
     `self._history` only, then **strips every system message** and prepends its own
     freshly-built one:
     ```python
     system_text = self._build_system_prompt_text()
     system_msg = Message(role="system", content=system_text)
     non_system = [m for m in messages if m.role != "system"]
     return [system_msg] + non_system
     ```
   - `loop-agent` **never calls** the mounted context manager's
     `get_messages_for_request()` (grep across `modules/loop-agent/`: zero references
     to `get_messages_for_request`, `system_prompt_factory`, or `context.include`).
     `self._history` is seeded only from the input prompt (`agent_session.py:297`)
     plus tool-result/steering turns.

Net: foundation registers the include-bearing factory on `context-simple`, but
`loop-agent` constructs its prompt from a different, disk-and-config-only source and
discards any other system message. The factory is never invoked → `context.include`
silently disappears for every agent spawned under `loop-agent`.

## Impact

- **Silent, not loud.** No error, no warning; the pipeline returns `success`. The
  bundle loads and the context dict is populated, so every shallow check passes.
- **Breaks cross-bundle composition into pipelines.** The intended pattern — compose
  bundle X's orientation/instruction context into a pipeline child so the child
  reasons with X's "why" — is a no-op. (This is exactly how we hit it: composing the
  `amplifier-bundle-llm-wiki` orientation into a wiki-ingest pipeline agent had zero
  runtime effect; the agent worked only off project-side files it read with tools.)
- **The attractor agent base profile breaks its own contract.**
  `agents/attractor-agent-anthropic.yaml` declares
  `context.include: [context/system-anthropic.md]`, which is also dropped — so the
  base agent never receives its own intended Anthropic system context.

## Bug vs by-design — verdict: **genuine bug** (silent feature drop)

`context.include` is a first-class, documented bundle feature; foundation's normal
session path and `spawn()` both wire it through the context manager, and
`context-simple` implements the consuming half. `loop-agent` is an alternative
orchestrator that re-implements message/prompt assembly and simply never wired in
the context-manager's system contribution.

Honest counter-argument: one could argue `loop-agent` is *intentionally* lean —
"agent instructions come from `config.system_prompt` + project docs, not bundle
context." But three facts defeat that reading: (1) the attractor base profile ships
its own `context.include`, evidencing the author expects includes to load; (2) the
failure is silent, the worst mode; (3) it contradicts the documented bundle
contract that foundation and `context-simple` both honor. So: bug, not design.

## Suggested fix (small, localized to `loop-agent`; we can offer a PR)

The other two layers are already correct, so the fix lives entirely in
`loop-agent/agent_session.py`: make the agent incorporate the mounted context
manager's system contribution instead of ignoring it. Two viable shapes:

- **Option A (minimal, respects existing layering):** at session init, pull the
  resolved bundle context once (invoke the registered `_system_prompt_factory` /
  read `get_messages_for_request()`'s system message) and feed it into
  `_build_system_prompt_text()` as an additional layer (e.g. a "Bundle Context"
  section between base and project docs). Sketch:
  ```python
  # in _build_system_prompt_text(), before build_system_prompt(...)
  ctx = self._coordinator.get("context")
  bundle_context = await ctx.get_bundle_system_content()  # or invoke factory once
  # pass bundle_context into build_system_prompt() as a new layer
  ```
- **Option B (delegate to the context manager):** in
  `_convert_history_to_messages()`, obtain the system message from
  `await context.get_messages_for_request()` (which already merges the factory
  output) and use it instead of/ahead of the locally built one.

There is a precedence decision (where bundle context sits relative to the existing
5 layers), so it's not a blind one-liner — but it's small, contained to one module,
and testable with the sentinel repro above. We're happy to send a PR if the
maintainers prefer Option A vs B.

## Repro artifacts (in our companion repo, for reference)

- `/tmp/ctx-include-repro/` — `sentinel-context.md`, `sentinel-agent.yaml`,
  `run_repro.py` (instrumented harness). Run with the amplifier tool venv python.
