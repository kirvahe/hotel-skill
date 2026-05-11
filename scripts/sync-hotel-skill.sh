#!/bin/bash
# Sync /hotel skill from upstream (kirvahe/hotel-skill) once per day
# Runs as async SessionStart hook — doesn't block Claude Code startup
#
# Behavior:
#   1. Throttle: skip if last sync < 24h ago
#   2. Maintain a persistent clone at ~/.claude/skills/hotel/.source/
#   3. git fetch + ff-only merge
#   4. If new commits arrived → run install.sh on the fresh clone (non-interactive)
#   5. Emit one-line notification if files were updated; silent otherwise

set -uo pipefail

SKILL_NAME="hotel"
UPSTREAM_URL="https://github.com/kirvahe/hotel-skill.git"
SKILL_DIR="$HOME/.claude/skills/$SKILL_NAME"
SOURCE_DIR="$SKILL_DIR/.source"
TIMESTAMP_FILE="$SKILL_DIR/.last-sync"
SYNC_INTERVAL=86400  # 24 hours

# Throttle check
if [ -f "$TIMESTAMP_FILE" ]; then
  last_sync=$(cat "$TIMESTAMP_FILE" 2>/dev/null || echo 0)
  now=$(date +%s)
  elapsed=$((now - last_sync))
  [ "$elapsed" -lt "$SYNC_INTERVAL" ] && exit 0
fi

# Skill must already be installed (don't bootstrap from this script)
[ -d "$SKILL_DIR" ] || exit 0

# Ensure source clone exists
if [ ! -d "$SOURCE_DIR/.git" ]; then
  rm -rf "$SOURCE_DIR" 2>/dev/null
  git clone --quiet --depth 50 "$UPSTREAM_URL" "$SOURCE_DIR" 2>/dev/null || exit 0
fi

cd "$SOURCE_DIR" || exit 0

# Record pre-sync HEAD
pre_head=$(git rev-parse HEAD 2>/dev/null || echo "")

# Fetch + ff-only merge
git fetch origin main --quiet 2>/dev/null || { date +%s > "$TIMESTAMP_FILE"; exit 0; }
git merge origin/main --ff-only --quiet 2>/dev/null || { date +%s > "$TIMESTAMP_FILE"; exit 0; }

post_head=$(git rev-parse HEAD 2>/dev/null || echo "")

# Always record timestamp (even if no update — prevents retry storms)
date +%s > "$TIMESTAMP_FILE"

# Nothing changed → silent exit
[ "$pre_head" = "$post_head" ] && exit 0

# Run install.sh non-interactively on the fresh clone
[ -x "./install.sh" ] || exit 0
./install.sh --non-interactive >/dev/null 2>&1 || exit 0

# Detect version for notification
new_version=$(awk -F'"' '/^version:/ {print $2; exit}' "$SOURCE_DIR/SKILL.md" 2>/dev/null || echo "")
release_url="https://github.com/kirvahe/hotel-skill/releases/latest"
[ -n "$new_version" ] && release_url="https://github.com/kirvahe/hotel-skill/releases/tag/v$new_version"

# One-line notification — CC surfaces SessionStart hook stdout as system message
if [ -n "$new_version" ]; then
  echo "✓ /hotel updated to v$new_version — $release_url"
else
  echo "✓ /hotel updated — $release_url"
fi
