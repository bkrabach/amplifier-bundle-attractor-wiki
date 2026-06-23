#!/usr/bin/env python3
"""
Deterministic speaker attribution enforcement for wiki-attractor.

WHAT THIS DOES
--------------
For every sources/*.md that contains anonymous @N speaker handles:
  1. Reads the SPEAKER_RESOLUTION_TABLE structured block (preferred format).
  2. Falls back to parsing the existing prose "Speaker handle resolution"
     section for source pages created before this change was merged.
  3. If the source page has @N handles but no structured block, BACKFILLS
     the structured block from the prose (upgrades old pages on first run).

For every people/*.md page — TWO passes:

PASS 1 (section-level, citation-anchored):
  - Reads the sources[] frontmatter to get cited sources.
  - For any cited source where this person appears as an INFERRED handle:
    checks that the person page has an ## Attribution confidence section.
  - If missing: ADDS it (idempotent — won't double-add).

PASS 2 (bullet-level, see-also / weave link following):
  - Scans ALL bullet lines on the person page that contain wikilinks [[slug]].
  - For each such bullet, resolves the linked page and reads ITS sources[].
  - If the linked page cites a source where THIS person is an INFERRED @N,
    appends an inline *(inferred speaker: ...)* marker to that specific bullet.
  - Idempotent: skips bullets that already carry the marker.
  - Scope-limited to avoid over-flag: only fires when the LINKED PAGE cites
    the specific inferred source — named claims from pages citing different
    (non-inferred) sources are left untouched by construction.

The structured block format written to source pages:
  <!-- SPEAKER_RESOLUTION_TABLE
  @N | Person Name | named|inferred|unresolved | basis
  END_SPEAKER_RESOLUTION_TABLE -->

  status values:
    named      — speaker identified by explicit name in transcript labels
    inferred   — speaker identified by content-matching (unreliable; hedge downstream)
    unresolved — speaker could not be reliably identified

IDEMPOTENCY
-----------
  - Never adds the ## Attribution confidence section if one already exists.
  - Never adds the SPEAKER_RESOLUTION_TABLE if one already exists.
  - Safe to run multiple times on the same wiki.

RETURN VALUE
------------
Always exits 0. Writes a one-line summary to stdout (for attractor log.md).
The calling parallelogram node should be wired to "continue" regardless.

USAGE
-----
  python3 enforce_speaker_attribution.py [WIKI_DIR]
  (default WIKI_DIR: team-knowledge)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

# Matches the SPEAKER_RESOLUTION_TABLE block (HTML comment, pipe-separated)
_TABLE_RE = re.compile(
    r"<!-- SPEAKER_RESOLUTION_TABLE\n(.*?)\nEND_SPEAKER_RESOLUTION_TABLE -->",
    re.DOTALL,
)

# Matches a single table row: @N | Person Name | status | basis
_TABLE_ROW_RE = re.compile(
    r"^@(\d+)\s*\|\s*([^|]+?)\s*\|\s*(named|inferred|unresolved)\s*\|\s*(.*)$"
)

# Matches @N patterns in the body of a source page (both `@N` and bare @N)
_HANDLE_IN_BODY_RE = re.compile(r"`?@(\d+)`?")

# Prose-resolution section header patterns (for fallback parsing)
_PROSE_HEADER_RE = re.compile(
    r"(?im)\*\*speaker\s+handle\s+resolution",
)

# Each prose bullet: - `@N` = Person — ... or - `@N` = **unresolved** — ...
_PROSE_LINE_RE = re.compile(
    r"-\s+`@(\d+)`\s+=\s+(\*\*unresolved\*\*|[A-Z][^—\n—-]+?)\s*(?:[—-]|$)",
    re.IGNORECASE,
)

# Attribution confidence section marker
_ATTR_HEDGE_RE = re.compile(
    r"^##\s+Attribution\s+confidence", re.IGNORECASE | re.MULTILINE
)

# YAML frontmatter sources: [slug1, slug2, ...] or sources: [single]
_SOURCES_RE = re.compile(r"^sources:\s*\[([^\]]*)\]", re.MULTILINE)

# YAML frontmatter title
_TITLE_RE = re.compile(r"^title:\s*[\"']?(.+?)[\"']?\s*$", re.MULTILINE)

# YAML frontmatter type
_TYPE_RE = re.compile(r"^type:\s*(\w+)", re.MULTILINE)

# Wikilinks in bullet lines: [[slug]] or [[slug|label]]
_WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]")

# Idempotency guard for bullet-level inline hedges (second pass)
_INFERRED_BULLET_MARKER_RE = re.compile(r"\*\(inferred speaker", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Resolution table parsing
# ---------------------------------------------------------------------------


def parse_resolution_table(content: str) -> dict[str, tuple[str, str, str]]:
    """Parse SPEAKER_RESOLUTION_TABLE block.

    Returns {handle_num: (person_name, status, basis)} or empty dict.
    """
    m = _TABLE_RE.search(content)
    if not m:
        return {}
    result: dict[str, tuple[str, str, str]] = {}
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line:
            continue
        rm = _TABLE_ROW_RE.match(line)
        if rm:
            handle, person, status, basis = rm.groups()
            result[handle.strip()] = (person.strip(), status.strip(), basis.strip())
    return result


def parse_resolution_prose(content: str) -> dict[str, tuple[str, str, str]]:
    """Parse prose speaker resolution section (fallback for old source pages).

    Conservative: treats all matches as 'inferred' unless the description
    contains 'confirmed', 'named by', 'named in speaker label', or
    '**unresolved**'/'unresolved'.

    Returns {handle_num: (person_name, status, basis)} or empty dict.
    """
    if not _PROSE_HEADER_RE.search(content):
        return {}

    result: dict[str, tuple[str, str, str]] = {}
    for m in _PROSE_LINE_RE.finditer(content):
        handle = m.group(1).strip()
        raw_name = m.group(2).strip()

        # Unresolved handle
        if raw_name.lower().strip("* ") == "unresolved":
            result[handle] = ("unresolved", "unresolved", "(prose)")
            continue

        # Clean name of markdown bold markers
        person = raw_name.strip("*").strip()

        # Determine status from this bullet line only (stop at next bullet or 200 chars).
        # Using a limited window prevents bleed from a later '@N = **unresolved**' bullet.
        start = m.start()
        # Find the end of this bullet (next '- `@' bullet or 200 chars, whichever first)
        next_bullet = content.find("\n-", start + 1)
        line_end = next_bullet if 0 < next_bullet - start < 200 else start + 200
        context = content[start:line_end].lower()
        if (
            "**unresolved**" in context
            or "cannot confirm" in context
            or "unresolved" in context[:60]
        ):
            status = "unresolved"
        elif (
            "named by name" in context
            or "named in speaker label" in context
            or "confirmed by name" in context
            or "appears explicitly" in context
            or ("named" in context[:80] and "inferred" not in context[:80])
        ):
            status = "named"
        elif "inferred" in context[:150]:
            status = "inferred"
        else:
            # Conservative default: if we're matching @N by content, it's inferred
            status = "inferred"

        result[handle] = (person, status, "(parsed from prose)")

    return result


def has_speaker_handles(content: str) -> bool:
    """True if this page body mentions @N style handles."""
    return bool(_HANDLE_IN_BODY_RE.search(content))


def build_resolution_table_block(resolution: dict[str, tuple[str, str, str]]) -> str:
    """Render the SPEAKER_RESOLUTION_TABLE block string."""
    rows = []
    for handle, (person, status, basis) in sorted(
        resolution.items(), key=lambda x: int(x[0])
    ):
        rows.append(f"@{handle} | {person} | {status} | {basis}")
    return (
        "<!-- SPEAKER_RESOLUTION_TABLE\n"
        + "\n".join(rows)
        + "\nEND_SPEAKER_RESOLUTION_TABLE -->"
    )


def backfill_structured_block(
    filepath: Path, resolution: dict[str, tuple[str, str, str]]
) -> bool:
    """Add SPEAKER_RESOLUTION_TABLE to a source page that lacks one.

    Inserts after the first `---` separator (after frontmatter) and before
    the first `##` heading, or appended before the first section.
    Returns True if the block was added.
    """
    content = filepath.read_text(encoding="utf-8")
    if _TABLE_RE.search(content):
        return False  # Already has a table

    block = build_resolution_table_block(resolution)

    # Find the end of the YAML frontmatter
    # Frontmatter is between the first and second '---'
    fm_end = -1
    if content.startswith("---"):
        second = content.find("\n---", 3)
        if second != -1:
            nl = content.find("\n", second + 1)
            fm_end = nl + 1 if nl != -1 else second + 4

    if fm_end > 0:
        # Insert after frontmatter
        new_content = content[:fm_end] + "\n" + block + "\n" + content[fm_end:]
    else:
        # Prepend
        new_content = block + "\n\n" + content

    filepath.write_text(new_content, encoding="utf-8")
    return True


# ---------------------------------------------------------------------------
# Person page frontmatter parsing
# ---------------------------------------------------------------------------


def get_person_name(content: str) -> str | None:
    """Extract person name from frontmatter title."""
    m = _TITLE_RE.search(content[:500])
    return m.group(1).strip() if m else None


def get_cited_sources(content: str) -> list[str]:
    """Extract source slugs from frontmatter sources: [...]."""
    m = _SOURCES_RE.search(content[:500])
    if not m:
        return []
    raw = m.group(1)
    return [s.strip().strip("'\"") for s in raw.split(",") if s.strip()]


def has_attribution_hedge(content: str) -> bool:
    """True if person page already has ## Attribution confidence section."""
    return bool(_ATTR_HEDGE_RE.search(content))


def add_attribution_hedge(
    filepath: Path,
    inferred_entries: list[tuple[str, str, str, str]],
) -> None:
    """Add ## Attribution confidence section to a person page.

    inferred_entries: list of (source_slug, handle_num, basis, person_name)
    Idempotent: checks has_attribution_hedge before writing.
    """
    content = filepath.read_text(encoding="utf-8")
    if has_attribution_hedge(content):
        return

    lines = []
    for source_slug, handle_num, basis, _ in inferred_entries:
        lines.append(
            f"- **Claims from [[sources/{source_slug}]]**: attributed to "
            f"`@{handle_num}` — speaker identity inferred from content matching "
            f"({basis}). Treat claims sourced to this transcript entry as "
            f"likely but not confirmed. See the source page's SPEAKER_RESOLUTION_TABLE."
        )

    hedge_section = (
        "\n## Attribution confidence\n\n"
        "Some claims on this page trace to source transcripts where speaker "
        "identity was inferred from content, not confirmed by explicit name in "
        "the transcript speaker label:\n\n" + "\n".join(lines) + "\n\n"
        "> TODO-VERIFY: Confirm speaker identities against original recordings "
        "if attribution accuracy is critical.\n"
    )

    # Append before the final trailing newline, or just append
    filepath.write_text(content.rstrip("\n") + "\n" + hedge_section, encoding="utf-8")


# ---------------------------------------------------------------------------
# See-also / weave-link following (second pass helpers)
# ---------------------------------------------------------------------------


def resolve_wiki_page(wiki_dir: Path, slug: str) -> Path | None:
    """Resolve a wikilink slug to a filesystem path within wiki_dir.

    Handles:
      "concepts/dreaming"  -> wiki_dir/concepts/dreaming.md
      "dreaming"           -> wiki_dir/**/dreaming.md (first match)
      "people/paul"        -> wiki_dir/people/paul.md
    Returns None if the page cannot be found.
    """
    slug = slug.strip()
    if "/" in slug:
        candidate = wiki_dir / (slug + ".md")
        if candidate.exists():
            return candidate
    else:
        for md_path in wiki_dir.rglob(f"{slug}.md"):
            return md_path
    return None


def hedge_see_also_bullets(
    person_path: Path,
    person_name: str,
    inferred_sources: dict[str, tuple[str, str]],
    wiki_dir: Path,
) -> int:
    """Second pass: hedge bullets that link to pages citing an inferred transcript source.

    For each bullet line on person_path that:
    (a) contains a wikilink [[slug]]
    (b) the linked page's sources[] includes any key from inferred_sources
    (c) does not already carry an inferred-speaker marker
    → Appends an inline *(inferred speaker: ...)* marker to that line.

    inferred_sources: {source_slug: (handle_num, basis)} — sources where this
    person appears as an INFERRED @N speaker.

    Scoping prevents over-flag: the hedge fires ONLY when the LINKED PAGE cites
    the specific inferred source. Named claims from pages citing different (non-
    inferred) sources are untouched by construction.

    Idempotent: skips bullets already carrying the marker pattern.
    Returns number of bullets hedged.
    """
    content = person_path.read_text(encoding="utf-8")
    lines = content.split("\n")
    new_lines = []
    hedges_added = 0

    for line in lines:
        stripped = line.strip()
        # Only process bullet lines that contain wikilinks
        if not (stripped.startswith("-") and "[[" in line):
            new_lines.append(line)
            continue

        # Already hedged → skip (idempotency)
        if _INFERRED_BULLET_MARKER_RE.search(line):
            new_lines.append(line)
            continue

        # Extract all wikilink slugs from this bullet
        linked_slugs = [m.group(1).strip() for m in _WIKILINK_RE.finditer(line)]
        if not linked_slugs:
            new_lines.append(line)
            continue

        # Check whether any linked page cites an inferred source for this person
        hedge_info: tuple[str, str, str] | None = (
            None  # (source_slug, handle_num, basis)
        )

        for slug in linked_slugs:
            linked_page = resolve_wiki_page(wiki_dir, slug)
            if linked_page is None:
                continue

            try:
                linked_content = linked_page.read_text(encoding="utf-8")
            except OSError:
                continue

            linked_sources = get_cited_sources(linked_content)

            # Does any inferred source for this person appear in the linked page?
            for source_slug, (handle_num, basis) in inferred_sources.items():
                if source_slug in linked_sources:
                    hedge_info = (source_slug, handle_num, basis)
                    break

            if hedge_info is not None:
                break

        if hedge_info is not None:
            source_slug, handle_num, basis = hedge_info
            marker = (
                f" *(inferred speaker: `@{handle_num}` in "
                f"[[sources/{source_slug}]] attributed to {person_name} "
                f"by content-matching \u2014 see source SPEAKER_RESOLUTION_TABLE)*"
            )
            new_lines.append(line.rstrip() + marker)
            hedges_added += 1
        else:
            new_lines.append(line)

    if hedges_added > 0:
        person_path.write_text("\n".join(new_lines), encoding="utf-8")

    return hedges_added


# ---------------------------------------------------------------------------
# Main enforcement logic
# ---------------------------------------------------------------------------


def enforce(wiki_dir: Path) -> tuple[int, int, int, int]:
    """Run the full enforcement pass.

    Returns (sources_processed, blocks_backfilled, section_hedges, bullet_hedges).
    """
    sources_dir = wiki_dir / "sources"
    people_dir = wiki_dir / "people"

    if not sources_dir.is_dir() or not people_dir.is_dir():
        print(
            f"enforce-attribution: skip (sources/ or people/ not found in {wiki_dir})"
        )
        return 0, 0, 0, 0

    # Build resolution map: source_slug → {handle_num: (person, status, basis)}
    resolution_map: dict[str, dict[str, tuple[str, str, str]]] = {}
    sources_processed = 0
    blocks_backfilled = 0

    for source_path in sorted(sources_dir.glob("*.md")):
        slug = source_path.stem
        content = source_path.read_text(encoding="utf-8")

        # Skip non-transcript sources (no @N handles in body)
        if not has_speaker_handles(content):
            continue

        sources_processed += 1

        # Try structured block first
        resolution = parse_resolution_table(content)

        if not resolution:
            # Fall back to prose parsing
            resolution = parse_resolution_prose(content)
            if resolution:
                # Backfill the structured block into the source page
                did_backfill = backfill_structured_block(source_path, resolution)
                if did_backfill:
                    blocks_backfilled += 1

        if resolution:
            resolution_map[slug] = resolution

    # --- Pass 1: Section-level hedges for pages that DIRECTLY CITE an inferred source ---
    section_hedges = 0

    for person_path in sorted(people_dir.glob("*.md")):
        content = person_path.read_text(encoding="utf-8")

        # Skip non-person pages
        type_m = _TYPE_RE.search(content[:300])
        if not type_m or type_m.group(1) != "person":
            continue

        person_name = get_person_name(content)
        if not person_name:
            continue

        cited_sources = get_cited_sources(content)
        if not cited_sources:
            continue

        # Find any cited source that has an inferred handle for this person
        inferred_entries: list[
            tuple[str, str, str, str]
        ] = []  # (slug, handle, basis, person_name)
        for source_slug in cited_sources:
            if source_slug not in resolution_map:
                continue
            for handle_num, (resolved_name, status, basis) in resolution_map[
                source_slug
            ].items():
                if status != "inferred":
                    continue
                # Name matching: check if resolved_name is a close match to person_name
                # Use case-insensitive first-name or last-name match
                rn_lower = resolved_name.lower()
                pn_lower = person_name.lower()
                pn_parts = pn_lower.split()
                if (
                    pn_lower in rn_lower
                    or rn_lower in pn_lower
                    or any(part in rn_lower for part in pn_parts if len(part) > 2)
                ):
                    inferred_entries.append(
                        (source_slug, handle_num, basis, person_name)
                    )

        if not inferred_entries:
            continue

        # Check if hedge already present
        if has_attribution_hedge(content):
            continue

        # Add the hedge
        add_attribution_hedge(person_path, inferred_entries)
        section_hedges += 1

    # --- Pass 2: Bullet-level hedges for bullets linking to pages that cite an ---
    # --- inferred source — catches weave-introduced attributions where the person ---
    # --- page doesn't directly cite the inferred transcript in its frontmatter.  ---

    # Build a reverse map: normalised person name → {source_slug: (handle_num, basis)}
    # using ALL inferred entries across ALL sources (not just those the person cited).
    person_inferred_all: dict[str, dict[str, tuple[str, str]]] = {}
    for source_slug, resolution in resolution_map.items():
        for handle_num, (resolved_name, status, basis) in resolution.items():
            if status != "inferred":
                continue
            key = resolved_name.strip().lower()
            if key not in person_inferred_all:
                person_inferred_all[key] = {}
            # First inferred entry for this (person, source) wins; don't overwrite
            if source_slug not in person_inferred_all[key]:
                person_inferred_all[key][source_slug] = (handle_num, basis)

    bullet_hedges = 0

    for person_path in sorted(people_dir.glob("*.md")):
        content = person_path.read_text(encoding="utf-8")

        type_m = _TYPE_RE.search(content[:300])
        if not type_m or type_m.group(1) != "person":
            continue

        person_name = get_person_name(content)
        if not person_name:
            continue

        # Find the inferred-source entries for this person across all sources
        pn_lower = person_name.lower()
        pn_parts = pn_lower.split()
        inferred_sources: dict[str, tuple[str, str]] = {}
        for key, source_map in person_inferred_all.items():
            if (
                pn_lower in key
                or key in pn_lower
                or any(part in key for part in pn_parts if len(part) > 2)
            ):
                # Merge without overwriting: first match wins per source_slug
                for slug, val in source_map.items():
                    if slug not in inferred_sources:
                        inferred_sources[slug] = val

        if not inferred_sources:
            continue

        added = hedge_see_also_bullets(
            person_path, person_name, inferred_sources, wiki_dir
        )
        bullet_hedges += added

    return sources_processed, blocks_backfilled, section_hedges, bullet_hedges


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    wiki_dir_arg = sys.argv[1] if len(sys.argv) > 1 else "team-knowledge"
    wiki_dir = Path(wiki_dir_arg)

    if not wiki_dir.is_dir():
        print(f"enforce-attribution: package directory '{wiki_dir}' not found — skip")
        sys.exit(0)

    processed, backfilled, section_hedges, bullet_hedges = enforce(wiki_dir)

    summary_parts = [f"enforce-attribution: {processed} transcript source(s) scanned"]
    if backfilled:
        summary_parts.append(f"{backfilled} structured table(s) backfilled")
    if section_hedges:
        summary_parts.append(f"{section_hedges} section hedge(s) added to person pages")
    if bullet_hedges:
        summary_parts.append(f"{bullet_hedges} see-also bullet(s) hedged inline")
    if not backfilled and not section_hedges and not bullet_hedges:
        summary_parts.append("all hedges present")

    print("; ".join(summary_parts))


if __name__ == "__main__":
    main()
