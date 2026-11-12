#!/usr/bin/env bash
# Installs the cad-workshop add-in into a multiclaude checkout, or takes it out again.
#
#   multiclaude/install.sh [--root DIR] [--user NAME]    copy the add-in in
#   multiclaude/install.sh [--root DIR] --uninstall      turn it off and remove it
#
# DIR is the multiclaude checkout: $ASSISTANT_ROOT, or ~/assistant. NAME is the multiclaude user
# whose assistant uses the workshop (default: the owner in users.json). The workshop itself is this
# clone of cad-workshop; keep it in that person's folder, ~/workspaces/<NAME>/cad-workshop.
# The add-in has no code, only rules for the assistants and a setup, so multiclaude's core needs no
# patch: `assistant addon` finds any folder in addons/.
set -euo pipefail

HERE="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
CAD_HOME="$(cd "$HERE/.." && pwd)"
ROOT="${ASSISTANT_ROOT:-$HOME/assistant}"
NAME=cad-workshop
action=install user=
while [ $# -gt 0 ]; do
  case "$1" in
    --root) ROOT="${2:?--root needs a directory}"; shift 2 ;;
    --user) user="${2:?--user needs a name}"; shift 2 ;;
    --uninstall) action=uninstall; shift ;;
    -h|--help) sed -n '2,11p' "$0"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

[ -f "$ROOT/bin/assistant" ] && [ -d "$ROOT/addons" ] || { echo "error: no multiclaude checkout at $ROOT (--root DIR)" >&2; exit 1; }
ROOT="$(cd "$ROOT" && pwd)"
FOLDER="$ROOT/addons/$NAME"
is_on() { jq -e --arg n "$NAME" '.addons // [] | any(. == $n)' "$ROOT/config.json" >/dev/null 2>&1; }

if [ "$action" = uninstall ]; then
  if is_on; then "$ROOT/bin/assistant" addon disable "$NAME"; fi
  rm -rf "$FOLDER"
  echo "$NAME is out of $ROOT. The workshop itself, $CAD_HOME, is untouched."
  exit 0
fi

command -v jq >/dev/null || { echo "error: needs jq (multiclaude installs it)" >&2; exit 1; }
if [ -z "$user" ]; then
  user=$(jq -r 'to_entries[] | select(.value.role == "owner") | .key' "$ROOT/users.json" 2>/dev/null | head -1)
  [ -n "$user" ] || { echo "error: no owner in $ROOT/users.json; pass --user NAME" >&2; exit 1; }
fi
jq -e --arg u "$user" 'has($u)' "$ROOT/users.json" >/dev/null 2>&1 ||
  { echo "error: no user '$user' in $ROOT/users.json" >&2; exit 1; }
display=$(jq -r --arg u "$user" '.[$u].display // $u' "$ROOT/users.json")

case "$CAD_HOME" in
  "$HOME/workspaces/$user"/*) ;;
  *) echo "warning: $CAD_HOME is outside $user's folder ($HOME/workspaces/$user); their assistant works best on a clone there" >&2 ;;
esac

# The rules and the setup name this clone and the person; multiclaude fills in its own {{…}} later.
fill() {
  CAD_HOME="$CAD_HOME" CAD_USER="$user" CAD_DISPLAY="$display" python3 -I -c '
import os, sys
text = open(sys.argv[1]).read()
for key in ("CAD_HOME", "CAD_USER", "CAD_DISPLAY"):
    text = text.replace("{{" + key + "}}", os.environ[key])
sys.stdout.write(text)' "$1"
}
mkdir -p "$FOLDER"
install -m 644 "$HERE/addon/README.md" "$FOLDER/README.md"
fill "$HERE/addon/rules.md" > "$FOLDER/rules.md" && chmod 644 "$FOLDER/rules.md"
fill "$HERE/addon/setup" > "$FOLDER/setup" && chmod 755 "$FOLDER/setup"

# Keep the copied folder out of the checkout's `git status` and out of the way of `git pull`.
if [ -d "$ROOT/.git" ]; then
  grep -qxF "/addons/$NAME/" "$ROOT/.git/info/exclude" 2>/dev/null || echo "/addons/$NAME/" >> "$ROOT/.git/info/exclude"
fi

echo "$NAME is in $ROOT: the workshop $CAD_HOME, for $user ($display)."
if is_on; then
  echo "It was already on. To use these rules and check the workshop again: assistant addon enable $NAME"
else
  echo "Turn it on: assistant addon enable $NAME"
fi
