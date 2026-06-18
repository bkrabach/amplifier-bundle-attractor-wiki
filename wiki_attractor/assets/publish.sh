#!/usr/bin/env bash
# .wiki/scripts/publish.sh — zip the shippable package for backup / handoff.
#
# Low-stakes publish target: a local zip of the wiki package. No external
# destination yet (no S3, no remote, no content API). When a real target exists,
# extend this script — the contract is just "produce the shippable artifact".
#
# Writes:  .wiki/dist/team-knowledge.zip   (gitignored)
# Excludes: .gitkeep placeholder files.
#
# Usage: publish.sh [PACKAGE_DIR]   (default: team-knowledge)

set -eu

PACKAGE_DIR="${1:-team-knowledge}"
DIST_DIR=".wiki/dist"
ZIP_NAME="team-knowledge.zip"
ZIP_PATH="$DIST_DIR/$ZIP_NAME"

if [ ! -d "$PACKAGE_DIR" ]; then
  echo "publish: package directory '$PACKAGE_DIR' not found"
  exit 2
fi

if ! command -v zip > /dev/null 2>&1; then
  echo "publish: 'zip' not available; install it or adapt this script"
  exit 2
fi

mkdir -p "$DIST_DIR"
rm -f "$ZIP_PATH"

# Zip the package, excluding placeholder files. -r recurse, -q quiet.
zip -r -q "$ZIP_PATH" "$PACKAGE_DIR" -x '*/.gitkeep' -x '.gitkeep'

COUNT=$(unzip -Z1 "$ZIP_PATH" | grep -c -v '/$' || true)
SIZE=$(du -h "$ZIP_PATH" | cut -f1)

echo "publish: wrote $ZIP_PATH ($SIZE, $COUNT file(s))"
