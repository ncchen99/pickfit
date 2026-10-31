#!/bin/sh
# Frozen seeded generator for the q03 large CSV (L2 item 3).
#
#   sh gen_big.sh OUT.csv [TARGET_BYTES] [SEED]
#
# Defaults: TARGET_BYTES=2000000000 (2 GB, decimal), SEED=20261028.
# Rows are appended until the file holds at least TARGET_BYTES bytes.
# 20 columns; group_key (column 12) has 1,000 distinct values G0000..G0999;
# about 5% of rows have a quoted note (column 5) holding a comma, and some of
# those also hold escaped quotes ("") or an embedded newline. ASCII only, LF
# line endings, header row first.
#
# Also writes OUT.csv.expected_counts.csv (group_key,count for every key, the
# frozen expected group-by result) and OUT.csv.meta (rows, bytes, seed).
#
# POSIX sh + awk only (the q03 image has no Python). The PRNG is a Lehmer
# MINSTD generator computed in exact double arithmetic, so mawk, gawk and BSD
# awk produce byte-identical files for the same seed.
set -eu
if [ $# -lt 1 ]; then
  echo "usage: gen_big.sh OUT.csv [TARGET_BYTES] [SEED]" >&2
  exit 2
fi
out=$1
target=${2:-2000000000}
seed=${3:-20261028}
LC_ALL=C
export LC_ALL

awk -v target="$target" -v seed="$seed" \
    -v counts_file="$out.expected_counts.csv" -v meta_file="$out.meta" '
function rnd() { state = (state * 48271) % 2147483647; return state }
BEGIN {
  if (seed < 1 || seed > 2147483646) { print "seed out of range" > "/dev/stderr"; exit 2 }
  state = seed
  ncat = split("books electronics garden grocery toys sports music tools beauty health auto office", cat, " ")
  ncur = split("USD EUR JPY TWD GBP", cur, " ")
  nst  = split("shipped pending cancelled returned", st, " ")
  nch  = split("web store phone partner", ch, " ")
  ndev = split("desktop mobile tablet", dev, " ")
  nctry = split("US DE JP TW GB FR IT ES NL SE NO DK FI PL CZ AT CH BE IE PT CA MX BR AR CL AU NZ KR SG IN", ctry, " ")
  ncity = split("springfield riverton fairview lakeside georgetown madison franklin clinton salem bristol oakdale milton ashland dover hudson kingston newport oxford winchester burlington", city, " ")
  nw = split("red blue green fast slow small large quiet bright early late fresh plain heavy light sharp soft warm cold dry wet new old rare daily extra prime basic smart clean urgent gift sample bulk spare backup return promo custom", w, " ")
  header = "id,ts,account,category,note,amount,qty,unit_price,currency,country,city,group_key,status,channel,flag,score,latency_ms,device,ref,comment"
  print header
  bytes = length(header) + 1
  rows = 0
  while (bytes < target) {
    rows++
    # r1: category, currency, status, channel, flag, device
    r = rnd()
    c_cat = cat[r % ncat + 1]; r = int(r / ncat)
    c_cur = cur[r % ncur + 1]; r = int(r / ncur)
    c_st  = st[r % nst + 1];   r = int(r / nst)
    c_ch  = ch[r % nch + 1];   r = int(r / nch)
    c_flag = (r % 2) ? "true" : "false"; r = int(r / 2)
    c_dev = dev[r % ndev + 1]
    # r2: country, city, qty, quote decision
    r = rnd()
    c_ctry = ctry[r % nctry + 1]; r = int(r / nctry)
    c_city = city[r % ncity + 1]; r = int(r / ncity)
    c_qty = r % 50 + 1;           r = int(r / 50)
    quoted = (r % 100) < 5
    # r3: group key, score, latency
    r = rnd()
    g = r % 1000; r = int(r / 1000)
    c_score = r % 101; r = int(r / 101)
    c_lat = r % 5000
    # r4: amount and unit price in cents
    r = rnd()
    amt = r % 100000; r = int(r / 100000)
    up = r % 10000
    # r5: timestamp
    r = rnd()
    mo = r % 12 + 1; r = int(r / 12)
    dd = r % 28 + 1; r = int(r / 28)
    hh = r % 24;     r = int(r / 24)
    mi = r % 60;     r = int(r / 60)
    ss = r % 60
    # r6: account, r7: ref
    acct = rnd() % 1000000
    ref = rnd() % 100000000
    # r8: note and comment words
    r = rnd()
    w1 = w[r % nw + 1]; r = int(r / nw)
    w2 = w[r % nw + 1]; r = int(r / nw)
    w3 = w[r % nw + 1]; r = int(r / nw)
    w4 = w[r % nw + 1]; r = int(r / nw)
    w5 = w[r % nw + 1]
    if (quoted) {
      rq = rnd()
      note = "\"" w1 ", " w2 " " w3
      if (rq % 10 < 3) note = note " said \"\"" w4 "\"\""
      rq = int(rq / 10)
      if (rq % 10 < 2) note = note "\n" w5 " " w1
      note = note "\""
    } else {
      note = w1 " " w2 " " w3
    }
    line = sprintf("%d,2026-%02d-%02dT%02d:%02d:%02dZ,ACC%06d,%s,%s,%d.%02d,%d,%d.%02d,%s,%s,%s,G%04d,%s,%s,%s,%d,%d,%s,R%08d,%s-%s",
      rows, mo, dd, hh, mi, ss, acct, c_cat, note, int(amt / 100), amt % 100, c_qty,
      int(up / 100), up % 100, c_cur, c_ctry, c_city, g, c_st, c_ch, c_flag, c_score,
      c_lat, c_dev, ref, w4, w5)
    print line
    bytes += length(line) + 1
    cnt[g]++
  }
  print "group_key,count" > counts_file
  for (i = 0; i < 1000; i++) printf("G%04d,%d\n", i, cnt[i] + 0) > counts_file
  printf("rows=%d\nbytes=%d\nseed=%d\ntarget=%d\n", rows, bytes, seed, target) > meta_file
}' > "$out"
