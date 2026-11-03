#!/bin/sh
# Contact sheet of a video at given times: sh edit/sheet.sh <video> <out.jpg> <width> <cols> t1 t2 ...
V=$1; OUT=$2; W=$3; C=$4; shift 4
TMP=$(mktemp -d)
i=0
for t in "$@"; do ffmpeg -loglevel error -y -ss "$t" -i "$V" -frames:v 1 -vf "scale=$W:-2" "$TMP/$(printf %03d $i).jpg"; i=$((i+1)); done
uv run --quiet --with pillow python - "$TMP" "$OUT" "$C" "$@" <<'PY'
import sys, glob
from PIL import Image, ImageDraw
tmp, out, cols, ts = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4:]
ims = [Image.open(f) for f in sorted(glob.glob(tmp + '/*.jpg'))]
w, h = ims[0].size; rows = (len(ims) + cols - 1) // cols
s = Image.new('RGB', (w * cols, h * rows), 'white'); d = ImageDraw.Draw(s)
for k, im in enumerate(ims):
    x, y = (k % cols) * w, (k // cols) * h
    s.paste(im, (x, y)); d.rectangle([x, y, x + 46, y + 16], fill='black'); d.text((x + 4, y + 3), ts[k], fill='yellow')
s.save(out, quality=80)
PY
rm -rf "$TMP"
