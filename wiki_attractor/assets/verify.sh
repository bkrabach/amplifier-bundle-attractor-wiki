#!/usr/bin/env bash
# .wiki/scripts/verify.sh — structural verification for the team-knowledge wiki
#
# PURE-MARKDOWN schema (see .wiki/context/schema.md). This does NOT parse JSON.
# For every entity page under the four type dirs it:
#   1. parses the YAML frontmatter
#   2. checks required fields are present (title, type, status, updated)
#   3. validates the `type` and `status` enum values
#   4. enforces type↔directory agreement (outcomes/ → type: outcome, etc.)
#   5. requires `date` on sources/ pages
#   6. verifies every sources[] slug resolves to sources/<slug>.md
#
# Backbone pages (index.md, overview.md, open-questions.md) are exempt — they are
# navigation/synthesis, not entities.
#
# Usage: verify.sh [PACKAGE_DIR]   (default: team-knowledge)

set -eu

WIKI_DIR="${1:-team-knowledge}"

if [ ! -d "$WIKI_DIR" ]; then
  echo "verify: package directory '$WIKI_DIR' not found"
  exit 2
fi

if ! command -v python3 > /dev/null 2>&1; then
  echo "verify: python3 not available; cannot parse frontmatter"
  exit 2
fi

python3 - "$WIKI_DIR" <<'PY'
import os, sys, glob

wiki = sys.argv[1]
TYPE_DIRS = {"outcomes": "outcome", "concepts": "concept",
             "people": "person", "sources": "source"}
VALID_TYPES = set(TYPE_DIRS.values())
VALID_STATUS = {"settled", "working", "unsettled"}
REQUIRED = ["title", "type", "status", "updated"]

errors = []

def parse_frontmatter(path):
    """Minimal YAML frontmatter parser: key: value, inline [a, b] lists."""
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    block = text[3:end].strip("\n")
    fm = {}
    for line in block.splitlines():
        line = line.rstrip()
        if not line or line.lstrip().startswith("#") or ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            fm[key] = [v.strip().strip("'\"") for v in inner.split(",") if v.strip()]
        else:
            fm[key] = val.strip("'\"")
    return fm

# collect existing source slugs
source_slugs = {
    os.path.splitext(os.path.basename(p))[0]
    for p in glob.glob(os.path.join(wiki, "sources", "*.md"))
}

checked = 0
for tdir, expected_type in TYPE_DIRS.items():
    for path in sorted(glob.glob(os.path.join(wiki, tdir, "*.md"))):
        if os.path.basename(path) == ".gitkeep":
            continue
        checked += 1
        rel = os.path.relpath(path, wiki)
        fm = parse_frontmatter(path)
        if fm is None:
            errors.append(f"{rel}: missing or unterminated YAML frontmatter")
            continue
        for field in REQUIRED:
            if field not in fm or fm[field] == "":
                errors.append(f"{rel}: missing required field '{field}'")
        t = fm.get("type")
        if t and t not in VALID_TYPES:
            errors.append(f"{rel}: invalid type '{t}' (expected one of {sorted(VALID_TYPES)})")
        if t and t != expected_type:
            errors.append(f"{rel}: type '{t}' does not match directory '{tdir}/' (expected '{expected_type}')")
        s = fm.get("status")
        if s and s not in VALID_STATUS:
            errors.append(f"{rel}: invalid status '{s}' (expected one of {sorted(VALID_STATUS)})")
        if expected_type == "source":
            if "date" not in fm or fm["date"] == "":
                errors.append(f"{rel}: sources/ page missing required 'date'")
        else:
            for slug in fm.get("sources", []):
                if slug not in source_slugs:
                    errors.append(f"{rel}: sources[] slug '{slug}' does not resolve to sources/{slug}.md")

# --- duplicate-title check: two entity pages sharing a title is a merge/dedup miss
#     (the failure mode headless ingest hits: same entity filed twice across runs) ---
import re
title_map = {}
for tdir in TYPE_DIRS:
    for path in sorted(glob.glob(os.path.join(wiki, tdir, "*.md"))):
        if os.path.basename(path) == ".gitkeep":
            continue
        fm = parse_frontmatter(path)
        if fm and fm.get("title"):
            title_map.setdefault(fm["title"].strip().lower(), []).append(
                os.path.relpath(path, wiki)
            )
for title, paths in sorted(title_map.items()):
    if len(paths) > 1:
        errors.append(f"duplicate title '{title}' shared by: {', '.join(sorted(paths))}")

# --- orphan check: an entity page nothing points to (no inbound [[wikilink]] from any
#     page, and not referenced via sources[]). Backbone pages are exempt by construction
#     (they live outside the four type dirs, so they are scanned as link SOURCES only). ---
inbound = set()
for path in glob.glob(os.path.join(wiki, "**", "*.md"), recursive=True):
    with open(path, encoding="utf-8") as fh:
        body = fh.read()
    for tgt in re.findall(r"\[\[([^\]]+)\]\]", body):
        tgt = tgt.split("|")[0].split("#")[0].strip()
        if tgt.endswith(".md"):
            tgt = tgt[:-3]
        inbound.add(tgt)                 # path form, e.g. outcomes/aios
        inbound.add(tgt.split("/")[-1])  # bare slug, e.g. aios
    fm = parse_frontmatter(path)
    if fm:
        for slug in fm.get("sources", []):
            inbound.add(slug)
for tdir in TYPE_DIRS:
    for path in sorted(glob.glob(os.path.join(wiki, tdir, "*.md"))):
        if os.path.basename(path) == ".gitkeep":
            continue
        slug = os.path.splitext(os.path.basename(path))[0]
        if f"{tdir}/{slug}" not in inbound and slug not in inbound:
            errors.append(
                f"{tdir}/{slug}.md: orphan \u2014 no inbound [[wikilink]] or sources[] reference"
            )

# --- status-honesty check: a `status: settled` page whose own BODY declares its
#     openness is self-contradictory. The #1 full-scale eval's smoking gun: pages
#     stamped settled that carry a "## Working:" section, say "not settled", or call
#     a claim "not a confirmed team decision".
#     SCOPE: outcomes/ + concepts/ ONLY. There, `settled` is a decidedness claim
#     about the idea/product, so a self-openness marker is a true contradiction.
#     sources/ (provenance records) and people/ (role pages) legitimately *report*
#     unsettled discussions in their prose, so they are exempt to avoid false
#     positives. Markers are kept deliberately tight (specific phrasings, a
#     colon-labelled "## Working:" heading) so a page that merely *discusses* open
#     questions in passing does not trip.
SELF_OPEN_PHRASES = (
    "not settled",                    # also catches "...to react to, not settled", "DRAFT - not settled"
    "not a confirmed team decision",
    "not confirmed team decision",    # prefix - covers the plural "...decisions"
)
HEADING_RE = re.compile(r"(?im)^##\s+working\s*:")  # a "## Working:" status/draft section
for tdir in ("outcomes", "concepts"):
    for path in sorted(glob.glob(os.path.join(wiki, tdir, "*.md"))):
        if os.path.basename(path) == ".gitkeep":
            continue
        fm = parse_frontmatter(path)
        if not fm or fm.get("status") != "settled":
            continue
        rel = os.path.relpath(path, wiki)
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        body = text
        if text.startswith("---"):
            fend = text.find("\n---", 3)
            if fend != -1:
                nl = text.find("\n", fend + 1)
                body = text[nl + 1:] if nl != -1 else ""
        low = body.lower()
        markers = []
        if HEADING_RE.search(body):
            markers.append('a "## Working:" section')
        for ph in SELF_OPEN_PHRASES:
            if ph in low:
                markers.append(f'the phrase "{ph}"')
                break
        if markers:
            errors.append(
                f"{rel}: status 'settled' but body asserts its own openness "
                f"({'; '.join(markers)}) - downgrade to 'working' or remove the claim"
            )

# --- escape-sequence check: JSON unicode escapes (\\uXXXX) in markdown files are a
#     serialization bug — the LLM wrote JSON-encoded content into plain UTF-8 markdown.
#     Scan ALL .md files (entity + backbone) since backbone pages are also affected.
#     Code blocks (``` fences and inline `code`) are exempt to avoid false-positives on
#     documentation that legitimately discusses JSON escape syntax. ---
import re as _re
_ESCAPE_RE = _re.compile(r'\\u[0-9a-fA-F]{4}')
_FENCE_RE  = _re.compile(r'```.*?```', _re.DOTALL)
_INLINE_RE = _re.compile(r'`[^`\n]+`')
for _path in sorted(glob.glob(os.path.join(wiki, "**", "*.md"), recursive=True)):
    if os.path.basename(_path) in (".gitkeep",):
        continue
    with open(_path, encoding="utf-8") as _fh:
        _raw = _fh.read()
    _stripped = _FENCE_RE.sub("", _raw)
    _stripped = _INLINE_RE.sub("", _stripped)
    _hits = list(_ESCAPE_RE.finditer(_stripped))
    if _hits:
        _rel = os.path.relpath(_path, wiki)
        _ctx = _stripped[max(0, _hits[0].start()-30):_hits[0].end()+30].replace("\n", " ").strip()
        errors.append(
            f"{_rel}: JSON unicode escape '{_hits[0].group()}' in markdown — "
            f"write actual Unicode characters (e.g. \u2014 in source = em-dash —, not a JSON escape): ...{_ctx}..."
        )

# --- speaker-resolution-table check: source pages that contain @N speaker handles
#     (anonymous speaker references) but lack a SPEAKER_RESOLUTION_TABLE block
#     are ambiguous — the deterministic attribution enforcer needs the structured
#     block to guarantee correct person-page hedging. This check fires as a
#     WARNING (not an error) so old source pages don't block existing wikis;
#     new ingests should produce the block automatically via write_pages.
#     The enforce_speaker_attribution.py script backfills old pages on each run.
import re as _srt_re
_SRT_HANDLE_RE = _srt_re.compile(r'`@\d+`|\b@\d+\s*[=\(]')
_SRT_TABLE_RE = _srt_re.compile(r'<!-- SPEAKER_RESOLUTION_TABLE')
warnings = []
for _path in sorted(glob.glob(os.path.join(wiki, "sources", "*.md"))):
    if os.path.basename(_path) == ".gitkeep":
        continue
    with open(_path, encoding="utf-8") as _fh:
        _src = _fh.read()
    if _SRT_HANDLE_RE.search(_src) and not _SRT_TABLE_RE.search(_src):
        _rel = os.path.relpath(_path, wiki)
        warnings.append(
            f"{_rel}: has @N speaker handles but no SPEAKER_RESOLUTION_TABLE block "
            f"(run enforce_speaker_attribution.py to backfill)"
        )

if errors:
    for e in errors:
        print(f"ERROR: {e}")
    print(f"verify: {len(errors)} error(s) across {checked} page(s)")
    sys.exit(1)

if warnings:
    for w in warnings:
        print(f"WARNING: {w}")

print(f"verify: clean ({checked} entity page(s) checked)")
PY
