# _lib.sh for the Mac questions: the same run_lines and all_ok, for zsh (the shell a Terminal window on macOS
# starts; the scripts run it as `zsh -il`), with BSD script(1) for "TTY:" lines.
run_lines() {  # $1 = label, $2 = file with one answer line per line
  local n=0 line rc
  while IFS= read -r line <&3 || [ -n "$line" ]; do
    [ -z "$line" ] && continue
    n=$((n+1))
    echo "== $1 $n: $line" | tee -a "$OUT/steps.txt"
    if [ "${line#TTY:}" != "$line" ]; then
      printf '\n' | script -q /dev/null /bin/zsh -ilc "${line#TTY:}" > "$OUT/$1-$n.txt" 2>&1; rc=$?
    else
      eval "$line" > "$OUT/$1-$n.txt" 2>&1 < /dev/null; rc=$?
    fi
    echo "$1 $n exit $rc" | tee -a "$OUT/steps.txt"; tail -3 "$OUT/$1-$n.txt"
  done 3< "$2"
}
all_ok() { ! grep -E "^$1 [0-9]+ exit [1-9]" "$OUT/steps.txt" > /dev/null; }
