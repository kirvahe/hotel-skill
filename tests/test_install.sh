#!/usr/bin/env bash
# test_install.sh — end-to-end checks for install.sh --skill-dir / --data-dir.
# Every scenario runs in a fresh temporary root with HOME pointed inside it,
# so nothing touches the real ~/.claude. Exit code is non-zero on any failure.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FAILS=0

pass() { echo "PASS  $1"; }
fail() { echo "FAIL  $1"; FAILS=$((FAILS + 1)); }

# new_root: fresh temp root with an isolated HOME; prints the root path
new_root() {
  local root
  root="$(mktemp -d)"
  mkdir -p "$root/home"
  echo "$root"
}

# run_install ROOT ARGS... : runs the installer with HOME inside ROOT
run_install() {
  local root="$1"; shift
  HOME="$root/home" "$REPO/install.sh" --non-interactive "$@" >"$root/out.log" 2>&1
}

fixture_data() {
  # A data folder that already holds a real (non-template) profile
  local dir="$1"
  mkdir -p "$dir/cities"
  printf '# Hotel Taste Profile\n\n## Base\n- Home city: Testville\n' > "$dir/taste-profile.md"
  printf '# Booking History\n\n## Stays\n' > "$dir/booking-history.md"
}

# 1. --data-dir pointing at a fixture folder creates the link, profile unchanged
root="$(new_root)"; fixture_data "$root/mydata"
before="$(shasum "$root/mydata/taste-profile.md" | cut -d' ' -f1)"
if run_install "$root" --skill-dir "$root/skills/hotel" --data-dir "$root/mydata"; then
  after="$(shasum "$root/mydata/taste-profile.md" | cut -d' ' -f1)"
  if [[ -L "$root/skills/hotel/data" && "$(readlink "$root/skills/hotel/data")" == "$root/mydata" && "$before" == "$after" ]]; then
    pass "data-dir creates the link and keeps the profile"
  else
    fail "data-dir creates the link and keeps the profile"
  fi
else
  fail "data-dir creates the link and keeps the profile (installer exited non-zero)"
fi

# 2. --data-dir pointing at a missing folder stops and creates nothing
root="$(new_root)"
if run_install "$root" --skill-dir "$root/skills/hotel" --data-dir "$root/nope"; then
  fail "missing data-dir stops"
elif [[ -e "$root/skills/hotel" || -e "$root/nope" ]]; then
  fail "missing data-dir creates nothing"
elif grep -q "not found" "$root/out.log"; then
  pass "missing data-dir stops with a message and creates nothing"
else
  fail "missing data-dir message"
fi

# 3. --data-dir over a skill whose data/ is a real directory stops, directory untouched
root="$(new_root)"; fixture_data "$root/mydata"
mkdir -p "$root/skills/hotel/data"; printf 'mine\n' > "$root/skills/hotel/data/taste-profile.md"
if run_install "$root" --skill-dir "$root/skills/hotel" --data-dir "$root/mydata"; then
  fail "real data/ directory is refused"
elif [[ -d "$root/skills/hotel/data" && ! -L "$root/skills/hotel/data" && "$(cat "$root/skills/hotel/data/taste-profile.md")" == "mine" ]] \
     && grep -q "real folder" "$root/out.log"; then
  pass "real data/ directory is refused and left untouched"
else
  fail "real data/ directory is refused and left untouched"
fi

# 4. Re-install replaces workflows/ and references/ but keeps the data link
root="$(new_root)"; fixture_data "$root/mydata"
run_install "$root" --skill-dir "$root/skills/hotel" --data-dir "$root/mydata"
printf 'stale\n' > "$root/skills/hotel/workflows/stale.md"
if run_install "$root" --skill-dir "$root/skills/hotel" --data-dir "$root/mydata" \
   && [[ ! -e "$root/skills/hotel/workflows/stale.md" && -L "$root/skills/hotel/data" ]]; then
  pass "re-install refreshes code and keeps the data link"
else
  fail "re-install refreshes code and keeps the data link"
fi

# 5. A data folder that already holds a profile gets no template files
root="$(new_root)"; fixture_data "$root/mydata"
run_install "$root" --skill-dir "$root/skills/hotel" --data-dir "$root/mydata"
if [[ ! -e "$root/mydata/cities-template.md" && ! -e "$root/mydata/cities/README.md" ]]; then
  pass "no templates seeded into a folder with a profile"
else
  fail "no templates seeded into a folder with a profile"
fi

# 6. A dangling data link without --data-dir stops with a message
root="$(new_root)"; mkdir -p "$root/skills/hotel"
ln -s "$root/gone" "$root/skills/hotel/data"
if run_install "$root" --skill-dir "$root/skills/hotel"; then
  fail "dangling data link is refused"
elif grep -q "missing folder" "$root/out.log"; then
  pass "dangling data link is refused with a message"
else
  fail "dangling data link message"
fi

# 7. The installed SKILL.md names the guard hook by the skill's absolute path; the source keeps
#    the placeholder. Runs a copy of the repo whose SKILL.md carries the placeholder, installed
#    with a relative --skill-dir whose name holds a space and an ampersand.
root="$(new_root)"; fixture_data "$root/mydata"
src="$root/src"; mkdir -p "$src"
(cd "$REPO" && tar cf - --exclude .git --exclude docs --exclude data .) | (cd "$src" && tar xf -)
printf '\nGuard: __HOTEL_SKILL_DIR__/bin/guard_hook.py\n' >> "$src/SKILL.md"
skill="$root/A&B skills/hotel"
if (cd "$root" && HOME="$root/home" "$src/install.sh" --non-interactive --skill-dir "A&B skills/hotel" \
      --data-dir "$root/mydata" >"$root/out.log" 2>&1); then
  abs="$(cd "$skill" && pwd)"
  hook="$(sed -n 's/^Guard: //p' "$skill/SKILL.md")"
  booking='{"hook_event_name":"PreToolUse","tool_name":"WebFetch","tool_input":{"url":"https://www.booking.com/x"}}'
  printf '%s' "$booking" | python3 "$hook" >/dev/null 2>&1; status=$?
  if [[ "$hook" == "$abs/bin/guard_hook.py" && "$status" -eq 2 ]] \
     && ! grep -q "__HOTEL_SKILL_DIR__" "$skill/SKILL.md" && grep -q "__HOTEL_SKILL_DIR__" "$src/SKILL.md"; then
    pass "installed SKILL.md names the guard hook by absolute path and the hook blocks"
  else
    fail "installed SKILL.md names the guard hook by absolute path and the hook blocks (hook='$hook', exit $status)"
  fi
else
  fail "guard hook path install (installer exited non-zero)"
fi

# 8. A skill folder path with a double quote is refused before anything is written
root="$(new_root)"
if run_install "$root" --skill-dir "$root/bad\"name/hotel"; then
  fail "skill folder path with a quote is refused"
elif [[ -e "$root/bad\"name" ]]; then
  fail "skill folder path with a quote creates nothing"
elif grep -q "quote or a backslash" "$root/out.log"; then
  pass "skill folder path with a quote is refused with a message and creates nothing"
else
  fail "skill folder path with a quote message"
fi

echo
if [[ "$FAILS" -eq 0 ]]; then echo "all install tests passed"; else echo "$FAILS install test(s) failed"; fi
exit "$FAILS"
