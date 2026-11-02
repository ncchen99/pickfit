# Shared by the L2 scripts (eval/results/l2/scripts): run an answer's lines verbatim in ONE shell, in order,
# so `source ...` and exported PATHs carry to later lines, recording each exit code (section 5: verbatim).
# A line given as "TTY:<command>" is the answer's command, run under a pseudo-terminal with Enter as the only
# input: the grader accepting the installer's default (section 5), for installers that read /dev/tty.
run_lines() {  # $1 = label, $2 = file with one answer line per line
  local n=0 line rc
  while IFS= read -r line <&3 || [ -n "$line" ]; do  # also the last line when the file has no final newline
    [ -z "$line" ] && continue
    n=$((n+1))
    echo "== $1 $n: $line" | tee -a "$OUT/steps.txt"
    if [ "${line#TTY:}" != "$line" ]; then
      printf '\n' | script -qec "${line#TTY:}" /dev/null > "$OUT/$1-$n.txt" 2>&1; rc=$?
    else
      eval "$line" > "$OUT/$1-$n.txt" 2>&1 < /dev/null; rc=$?
    fi
    echo "$1 $n exit $rc" | tee -a "$OUT/steps.txt"; tail -3 "$OUT/$1-$n.txt"
  done 3< "$2"
}
all_ok() { ! grep -E "^$1 [0-9]+ exit [1-9]" "$OUT/steps.txt" > /dev/null; }  # every line of label $1 exited 0
