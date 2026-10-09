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
#   ./install.sh [--skill-dir DIR] [--data-dir DIR] [--non-interactive]
#
# --data-dir links the skill's data/ to a folder you keep elsewhere (for
# example a synced folder). The folder must already exist. The installer
# never deletes or replaces a real data/ folder; it stops and tells you how
# to move it aside instead.

set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="${HOME}/.claude/skills/hotel"
DATA_DIR=""

NON_INTERACTIVE=false
UNINSTALL_HOOK=false
HOOK_SCRIPT_NAME="sync-hotel-skill.sh"
HOOK_SCRIPT_DEST="${HOME}/.claude/scripts/${HOOK_SCRIPT_NAME}"
SETTINGS_FILE="${HOME}/.claude/settings.json"

die() { echo "ERROR: $*" >&2; exit 1; }

# Parse args (zero-arg invocation keeps working)
while [[ $# -gt 0 ]]; do
  case "$1" in
    --non-interactive) NON_INTERACTIVE=true; shift ;;
    --uninstall-hook)  UNINSTALL_HOOK=true; shift ;;
    --skill-dir)
      [[ $# -ge 2 && -n "$2" ]] || die "--skill-dir requires a directory path"
      TARGET="$2"; shift 2 ;;
    --data-dir)
      [[ $# -ge 2 && -n "$2" ]] || die "--data-dir requires a directory path"
      DATA_DIR="$2"; shift 2 ;;
    --help)
      echo "Usage: ./install.sh [--skill-dir DIR] [--data-dir DIR] [--non-interactive] [--uninstall-hook] [--help]"
      echo ""
      echo "  --skill-dir DIR     Install the skill here (default: ~/.claude/skills/hotel)"
      echo "  --data-dir DIR      Link the skill's data/ to this existing folder"
      echo "  --non-interactive   Skip prompts (used by the auto-update sync script)"
      echo "  --uninstall-hook    Remove the SessionStart auto-update hook + sync script"
      echo "  --help              Show this help"
      exit 0
      ;;
    *) die "unknown option: $1 (see --help)" ;;
  esac
done

DATA="${TARGET}/data"
CITIES="${DATA}/cities"

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

# 0. Check the skill and data locations before writing anything.
#    The guard hook command holds the skill's absolute path inside a quoted YAML string
#    (see wire_guard_hook), so a path that would break that string is refused here.
case "${TARGET}" in
  /*) TARGET_PATH="${TARGET}" ;;
  *)  TARGET_PATH="${PWD}/${TARGET}" ;;
esac
if [[ "${TARGET_PATH}" == *[\"\\]* ]]; then
  die "the skill folder path contains a quote or a backslash: ${TARGET_PATH}
       The guard hook needs a plain path. Choose another --skill-dir. Nothing was installed."
fi

if [[ -n "${DATA_DIR}" ]]; then
  [[ -d "${DATA_DIR}" ]] || die "data folder not found: ${DATA_DIR}
       Create it or fix the path. Nothing was installed."
  DATA_DIR="$(cd "${DATA_DIR}" && pwd)"
  if [[ -d "${DATA}" && ! -L "${DATA}" ]]; then
    die "${DATA} is a real folder, not a link. Nothing was changed.
       Move it aside first, then re-run, for example:
         mv \"${DATA}\" \"${DATA}.bak-$(date +%Y%m%d)\""
  fi
elif [[ -L "${DATA}" && ! -e "${DATA}" ]]; then
  die "${DATA} links to a missing folder: $(readlink "${DATA}")
       Restore that folder, or re-run with --data-dir pointing at your data."
fi

echo "==> Installing /hotel skill"
echo "    source: ${SRC}"
echo "    target: ${TARGET}"

# 1. Create target directories and the data link
mkdir -p "${TARGET}"
if [[ -n "${DATA_DIR}" ]]; then
  if [[ -L "${DATA}" ]]; then
    echo "==> Re-pointing data/ (was: $(readlink "${DATA}"))"
    rm "${DATA}"
  fi
  ln -s "${DATA_DIR}" "${DATA}"
  echo "==> data/ → ${DATA_DIR}"
else
  mkdir -p "${DATA}"
fi
mkdir -p "${CITIES}"

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

# Hook commands get no ${CLAUDE_SKILL_DIR}, so SKILL.md names the guard hook as
# __HOTEL_SKILL_DIR__/bin/guard_hook.py and the installed copy gets this install's absolute
# path (KTD9). The repository's SKILL.md keeps the placeholder.
wire_guard_hook() {
    local skill_md="${TARGET}/SKILL.md" abs escaped
    if [[ ! -f "${skill_md}" ]] || ! grep -q '__HOTEL_SKILL_DIR__' "${skill_md}"; then
        return 0
    fi
    abs="$(cd "${TARGET}" && pwd)"
    escaped="$(printf '%s' "${abs}" | sed -e 's/[\\&|]/\\&/g')"
    sed "s|__HOTEL_SKILL_DIR__|${escaped}|g" "${skill_md}" > "${skill_md}.tmp"
    mv "${skill_md}.tmp" "${skill_md}"
    echo "==> Guard hook: ${abs}/bin/guard_hook.py"
}

copy_file "SKILL.md"
copy_dir "workflows"
copy_dir "references"
copy_dir "bin"
wire_guard_hook

# 3. Personal data — only seed templates into a folder that has no profile yet.
#    A folder with a profile holds real data, so nothing is added to it.
if [[ -f "${DATA}/taste-profile.md" ]]; then
  echo "==> ${DATA} already holds a profile — no templates added (your data is safe)"
  SEED_TEMPLATES=false
else
  SEED_TEMPLATES=true
fi

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

if [[ "${SEED_TEMPLATES}" == true ]]; then
    install_personal_file "taste-profile-template.md" "taste-profile.md"
    install_personal_file "booking-history-template.md" "booking-history.md"

    # Cities directory README (lightweight — never user-personal)
    if [[ -f "${SRC}/cities-template-README.md" && ! -f "${CITIES}/README.md" ]]; then
        echo "==> Seeding cities/README.md"
        cp "${SRC}/cities-template-README.md" "${CITIES}/README.md"
    fi

    # A cities-template.md sits at $DATA level for users to copy when adding a new city manually
    if [[ ! -f "${DATA}/cities-template.md" && -f "${SRC}/cities-template.md" ]]; then
        echo "==> Seeding cities-template.md (reference for new city files)"
        cp "${SRC}/cities-template.md" "${DATA}/cities-template.md"
    fi
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
