#!/bin/sh
# q12: make the local-path copy of the frozen fixture model, from the pins
# written by pin_model.py (model_pin.env + model_files.sha256 in this folder).
#
#   sh fetch_model.sh DEST
#
# Downloads each pinned file at the pinned commit with curl (no token), then
# verifies every SHA-256. Use it from the grader's account before the run when
# the answer loads the model from a folder (e.g. DEST=/Users/Shared/eval-models/<name>;
# keep /Users/Shared/eval-models at mode 700 except during that run, see README L2-2).
# POSIX sh, curl, shasum.
# PIN_BASE_URL overrides https://huggingface.co (selftest.py only).
set -eu

here=$(cd "$(dirname "$0")" && pwd)
dest=${1:?usage: fetch_model.sh DEST}
base=${PIN_BASE_URL:-https://huggingface.co}

[ -f "$here/model_pin.env" ] || { echo "model_pin.env missing: run pin_model.py at freeze" >&2; exit 2; }
[ -f "$here/model_files.sha256" ] || { echo "model_files.sha256 missing" >&2; exit 2; }
. "$here/model_pin.env"
: "${REPO_ID:?}" "${REVISION:?}"

mkdir -p "$dest"
while read -r sum path; do
  [ -n "$path" ] || continue
  mkdir -p "$dest/$(dirname "$path")"
  echo "fetching $path"
  curl -fsSL --retry 3 -o "$dest/$path" "$base/$REPO_ID/resolve/$REVISION/$path"
done < "$here/model_files.sha256"

cd "$dest"
shasum -a 256 -c "$here/model_files.sha256"
echo "local copy of $REPO_ID@$REVISION in $dest"
