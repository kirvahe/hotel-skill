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
        rm -rf "${TARGET}/${name}"
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
echo "==> Done."
echo
echo "Next steps:"
echo "  1. Open ${DATA}/taste-profile.md and fill in your TOP-3 anchors before using /hotel."
echo "  2. (Optional) Pre-fill ${DATA}/booking-history.md with past stays for richer learning."
echo "  3. Run /hotel in Claude Code to test."
