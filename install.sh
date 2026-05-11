#!/usr/bin/env bash
#
# install.sh — install the /hotel skill into ~/.claude/skills/hotel
#
# Safe to re-run (idempotent). Skill code is overwritten on every run.
# Personal data files (taste-profile.md, booking-history.md, cities/*.md)
# are NEVER overwritten — if they exist, we leave them alone.
#
# Usage:
#   chmod +x install.sh
#   ./install.sh

set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="${HOME}/.claude/skills/hotel"
DATA="${TARGET}/data"
CITIES="${DATA}/cities"

NON_INTERACTIVE=false
UNINSTALL_HOOK=false
HOOK_SCRIPT_NAME="sync-hotel-skill.sh"
HOOK_SCRIPT_DEST="${HOME}/.claude/scripts/${HOOK_SCRIPT_NAME}"
SETTINGS_FILE="${HOME}/.claude/settings.json"

# Parse args (lightweight — keeps existing zero-arg invocation working)
for arg in "$@"; do
  case "$arg" in
    --non-interactive) NON_INTERACTIVE=true ;;
    --uninstall-hook)  UNINSTALL_HOOK=true ;;
    --help)
      echo "Usage: ./install.sh [--non-interactive] [--uninstall-hook] [--help]"
      echo ""
      echo "  --non-interactive   Skip prompts (used by the auto-update sync script)"
      echo "  --uninstall-hook    Remove the SessionStart auto-update hook + sync script"
      echo "  --help              Show this help"
      exit 0
      ;;
  esac
done

# Print the SessionStart hook JSON snippet for manual addition
print_hook_snippet() {
  echo ""
  echo "Add this to ~/.claude/settings.json under hooks.SessionStart[0].hooks:"
  echo ""
  echo "  {"
  echo "    \"type\": \"command\","
  echo "    \"command\": \"${HOOK_SCRIPT_DEST}\","
  echo "    \"async\": true"
  echo "  }"
  echo ""
}

# Add the SessionStart hook to settings.json using jq.
add_hook_to_settings() {
  if ! command -v jq >/dev/null 2>&1; then
    echo "==> jq not found — cannot auto-modify settings.json"
    print_hook_snippet
    return 0
  fi

  mkdir -p "$(dirname "${SETTINGS_FILE}")"
  if [ -f "${SETTINGS_FILE}" ]; then
    cp "${SETTINGS_FILE}" "${SETTINGS_FILE}.bak-$(date +%s)"
  else
    echo '{}' > "${SETTINGS_FILE}"
  fi

  local new_hook
  new_hook=$(jq -n --arg cmd "${HOOK_SCRIPT_DEST}" \
    '{type:"command", command:$cmd, async:true}')

  local tmp="${SETTINGS_FILE}.tmp"
  if jq --argjson new "$new_hook" '
    .hooks //= {} |
    .hooks.SessionStart //= [{matcher:"startup", hooks:[]}] |
    if (.hooks.SessionStart | length) == 0 then
      .hooks.SessionStart = [{matcher:"startup", hooks:[]}]
    else . end |
    (.hooks.SessionStart[0].hooks // []) as $existing |
    if any($existing[]; .command == $new.command) then .
    else .hooks.SessionStart[0].hooks = $existing + [$new]
    end
  ' "${SETTINGS_FILE}" > "$tmp" 2>/dev/null; then
    mv "$tmp" "${SETTINGS_FILE}"
    echo "==> Auto-update hook added to ${SETTINGS_FILE}"
  else
    rm -f "$tmp"
    echo "==> Could not parse ${SETTINGS_FILE} — leaving it untouched"
    print_hook_snippet
  fi
}

# Remove our SessionStart hook from settings.json.
remove_hook_from_settings() {
  [ -f "${SETTINGS_FILE}" ] || return 0
  command -v jq >/dev/null 2>&1 || return 0

  cp "${SETTINGS_FILE}" "${SETTINGS_FILE}.bak-$(date +%s)"
  local tmp="${SETTINGS_FILE}.tmp"
  if jq --arg cmd "${HOOK_SCRIPT_DEST}" '
    if (.hooks.SessionStart // []) | length > 0 then
      .hooks.SessionStart[0].hooks = (
        (.hooks.SessionStart[0].hooks // []) | map(select(.command != $cmd))
      )
    else . end
  ' "${SETTINGS_FILE}" > "$tmp" 2>/dev/null; then
    mv "$tmp" "${SETTINGS_FILE}"
    echo "==> Auto-update hook removed from ${SETTINGS_FILE}"
  else
    rm -f "$tmp"
    echo "==> Could not modify ${SETTINGS_FILE}"
  fi
}

# Deploy sync script + optionally wire up SessionStart hook
setup_auto_update() {
  [ -f "${SRC}/scripts/${HOOK_SCRIPT_NAME}" ] || return 0

  mkdir -p "$(dirname "${HOOK_SCRIPT_DEST}")"
  cp "${SRC}/scripts/${HOOK_SCRIPT_NAME}" "${HOOK_SCRIPT_DEST}"
  chmod +x "${HOOK_SCRIPT_DEST}"
  echo "==> Installed sync script to ${HOOK_SCRIPT_DEST}"

  if [ "${NON_INTERACTIVE}" = true ]; then
    return 0
  fi

  echo ""
  echo "Enable automatic updates?"
  echo "  Adds a SessionStart hook that pulls upstream every 24h and re-runs install."
  echo "  Your taste-profile.md, booking-history.md, and cities/ are preserved."
  read -r -p "  [Y/n] " reply
  case "$reply" in
    n|N|no|No|NO)
      echo "==> Auto-update declined — to enable later, see the hook JSON below:"
      print_hook_snippet
      ;;
    *)
      add_hook_to_settings
      ;;
  esac
}

# --uninstall-hook short-circuit (no skill files touched)
if [ "${UNINSTALL_HOOK}" = true ]; then
  [ -f "${HOOK_SCRIPT_DEST}" ] && rm -f "${HOOK_SCRIPT_DEST}" && echo "==> Removed sync script ${HOOK_SCRIPT_DEST}"
  remove_hook_from_settings
  echo ""
  echo "==> Auto-update disabled. Skill files at ${TARGET} are untouched."
  exit 0
fi

echo "==> Installing /hotel skill"
echo "    source: ${SRC}"
echo "    target: ${TARGET}"

# 1. Create target directories
mkdir -p "${TARGET}" "${DATA}" "${CITIES}"

# 2. Copy skill code (always overwrite — these are the skill internals)
copy_dir() {
    local name="$1"
    if [[ -d "${SRC}/${name}" ]]; then
        echo "==> Copying ${name}/"
        rm -rf "${TARGET:?}/${name:?}"
        cp -R "${SRC}/${name}" "${TARGET}/${name}"
    fi
}

copy_file() {
    local name="$1"
    if [[ -f "${SRC}/${name}" ]]; then
        echo "==> Copying ${name}"
        cp "${SRC}/${name}" "${TARGET}/${name}"
    fi
}

copy_file "SKILL.md"
copy_dir "workflows"
copy_dir "references"

# 3. Personal data — only copy templates if user has no data yet
install_personal_file() {
    local template_src="$1"   # e.g. taste-profile-template.md
    local target_name="$2"    # e.g. taste-profile.md
    local target_path="${DATA}/${target_name}"

    if [[ -f "${target_path}" ]]; then
        echo "==> ${target_name} already exists — skipping (your data is safe)"
        return
    fi

    if [[ -f "${SRC}/${template_src}" ]]; then
        echo "==> Seeding ${target_name} from template — review and personalize"
        cp "${SRC}/${template_src}" "${target_path}"
    fi
}

install_personal_file "taste-profile-template.md" "taste-profile.md"
install_personal_file "booking-history-template.md" "booking-history.md"

# Cities directory README (lightweight — never user-personal)
if [[ -f "${SRC}/cities-template-README.md" ]]; then
    if [[ ! -f "${CITIES}/README.md" ]]; then
        echo "==> Seeding cities/README.md"
        cp "${SRC}/cities-template-README.md" "${CITIES}/README.md"
    else
        echo "==> cities/README.md already exists — skipping"
    fi
fi

# A cities-template.md sits at $DATA level for users to copy when adding a new city manually
if [[ ! -f "${DATA}/cities-template.md" && -f "${SRC}/cities-template.md" ]]; then
    echo "==> Seeding cities-template.md (reference for new city files)"
    cp "${SRC}/cities-template.md" "${DATA}/cities-template.md"
fi

echo

# Auto-update wiring (deploys sync script + optionally adds SessionStart hook)
setup_auto_update

echo
echo "==> Done."
echo
echo "Next steps:"
echo "  1. Open ${DATA}/taste-profile.md and fill in your TOP-3 anchors before using /hotel."
echo "  2. (Optional) Pre-fill ${DATA}/booking-history.md with past stays for richer learning."
echo "  3. Run /hotel in Claude Code to test."
