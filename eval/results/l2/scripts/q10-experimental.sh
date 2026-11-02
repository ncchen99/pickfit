#!/bin/bash
# L2 for q10 (eval/fixtures/q10/README.md), run 1, experimental: base-git image; one-off command for L2-1..3 and 5,
# the answer's persistent settings and everyday command for L2-4.
set -u
FIX=$F/q10; mkdir -p "$OUT"
sh "$FIX/make_repo.sh" /work/repo > "$OUT/make_repo.txt" 2>&1; echo "make_repo exit $?" | tee -a "$OUT/steps.txt"
git -C /work/repo log --format=%H | tee -a "$OUT/steps.txt"
sh "$FIX/capture.sh" /work/repo "$OUT/out1.raw" 'git diff --word-diff=color --word-diff-regex='"'"'[A-Za-z0-9_]+|[^[:space:]]'"'"''; echo "capture out1 exit $?" | tee -a "$OUT/steps.txt"
cd /work/repo
git config --global diff.markdown.wordRegex '[A-Za-z0-9_]+|[^[:space:]]'; echo "setting wordRegex exit $?" | tee -a "$OUT/steps.txt"
printf '*.md diff=markdown\n' >> .gitattributes; echo "setting .gitattributes exit $?" | tee -a "$OUT/steps.txt"
git config --global alias.wd 'diff --word-diff=color'; echo "setting alias exit $?" | tee -a "$OUT/steps.txt"
sh "$FIX/capture.sh" /work/repo "$OUT/out2.raw" 'git wd'; echo "capture out2 exit $?" | tee -a "$OUT/steps.txt"
git -C /work/repo config --list --show-origin > "$OUT/config-list.txt" 2>&1
echo "== done"; cat "$OUT/steps.txt"
