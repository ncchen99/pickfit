#!/bin/sh
# Rebuild fixture.pdf exactly as committed (2026-10-31), in the eval's dev image (python3, curl).
# The font and fontTools come from their official sources at the versions and sha256 in
# eval/fixtures/PINS.md; neither is committed. Run from this folder:
#
#   sh build_pdf.sh WORKDIR        # writes WORKDIR/fixture.pdf; compare its sha256 with README.md
set -eu
here=$(cd "$(dirname "$0")" && pwd)
w=${1:?usage: build_pdf.sh WORKDIR}
mkdir -p "$w" && cd "$w"
FONT_URL='https://raw.githubusercontent.com/google/fonts/3be1884c48c3e45b52ecc725676a08f87776373e/ofl/notosanstc/NotoSansTC%5Bwght%5D.ttf'
FONT_SHA=864727d210d54f2537bbe23b3a839436c3992af72de9322af5270897246bd44f
FT_URL='https://files.pythonhosted.org/packages/35/74/4ea331ecc65ba05a58b1e4e8ccd604c8a15565f876dfbf93fc2a2ea2e22b/fonttools-4.68.0-py3-none-any.whl'
FT_SHA=d76f8fdcb6936f5e1045a0c9dd721a4bf11112e60d1e243bfa1d39f06a8b3104
curl -fsSL -o font.ttf "$FONT_URL"
echo "$FONT_SHA  font.ttf" | sha256sum -c -
curl -fsSL -o fonttools-4.68.0-py3-none-any.whl "$FT_URL"
echo "$FT_SHA  fonttools-4.68.0-py3-none-any.whl" | sha256sum -c -
# google/fonts ships only the variable font, whose default instance is Thin (100): cut static
# Regular (400) and Bold (700) instances, as q05's needs.json asks for static Regular and Bold.
PYTHONPATH="$w/fonttools-4.68.0-py3-none-any.whl" python3 -m fontTools.varLib.instancer font.ttf wght=400 \
  --static --update-name-table -o Regular.ttf
PYTHONPATH="$w/fonttools-4.68.0-py3-none-any.whl" python3 -m fontTools.varLib.instancer font.ttf wght=700 \
  --static --update-name-table -o Bold.ttf
python3 "$here/make_pdf.py" --font Regular.ttf --bold-font Bold.ttf --content "$here/content.json" --out "$w/fixture.pdf"
sha256sum Regular.ttf Bold.ttf fixture.pdf
