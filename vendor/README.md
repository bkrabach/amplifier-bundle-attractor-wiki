# Vendored upstream files

Self-contained copies of files this companion depends on at runtime, so the
companion is portable with **zero** dependency on sibling checkouts.

## What's vendored

`llm-wiki/` — the **llm-wiki orientation** (the "why" lens), copied from
[`microsoft/amplifier-bundle-llm-wiki`](https://github.com/microsoft/amplifier-bundle-llm-wiki):

| Vendored path | Upstream path |
|---|---|
| `llm-wiki/llm-wiki-pattern.md` | `docs/llm-wiki-pattern.md` |
| `llm-wiki/wiki-instructions.md` | `context/wiki-instructions.md` |

**Pinned at upstream commit:** `091df98affd9bc6e48fb3940ccfc56ca76d630f7`

## Why vendored (not referenced upstream)

The companion mounts the llm-wiki orientation into its child-agent profile
(`wiki-agent-anthropic.yaml`) via `context.include`. We tested every cross-bundle
reference form through the attractor spawn path — bare namespace
(`llm-wiki:docs/...`), `@`-namespace (`@llm-wiki:...`), and git-URL
`context.include` — and **all three failed to compose the orientation** into the
spawned agent's context. Only a **bundle-root-relative file path** loads the
content. So we vendor the files into the companion and reference them by a
companion-relative path — the proven-loading mechanism, now self-contained.

(The git-URL `includes:` for the attractor agent *module* base resolve fine; it
is specifically cross-bundle `context.include` content that does not. Hence only
the orientation files are vendored, not the engine.)

## Refresh

```bash
SHA=$(git ls-remote https://github.com/microsoft/amplifier-bundle-llm-wiki main | cut -f1) && \
  for f in docs/llm-wiki-pattern.md:llm-wiki-pattern.md context/wiki-instructions.md:wiki-instructions.md; do \
    src=${f%%:*}; dst=${f##*:}; \
    { echo "<!-- VENDORED from github.com/microsoft/amplifier-bundle-llm-wiki@$SHA : $src. Do not edit here; refresh by re-copying from upstream. -->"; \
      curl -sL "https://raw.githubusercontent.com/microsoft/amplifier-bundle-llm-wiki/$SHA/$src"; } > vendor/llm-wiki/$dst; \
  done
```

Then update the pinned SHA above and in each file's provenance header.
