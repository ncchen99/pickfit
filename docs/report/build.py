"""Builds the HTML report from a Markdown file, in the site's look (DESIGN.md).

    uvx --with markdown python docs/report/build.py [SOURCE.md] [OUT_DIR]

SOURCE defaults to docs/REPORT.md, OUT_DIR to docs/report/site. OUT_DIR gets index.html plus the
fonts, Fitz and the share card it uses, so the folder can be published as it is (GitHub Pages).
"""

import html
import re
import shutil
import sys
from pathlib import Path

import markdown
from markdown.extensions.toc import TocExtension

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SITE = "https://pickfit.app"


def render(source: Path) -> tuple[str, str, str, str]:
    text = source.read_text(encoding="utf-8")
    # The first H1 is the page title; the paragraph right after it is the lede.
    m = re.match(r"\s*#\s+(.+?)\n", text)
    title = m.group(1).strip() if m else "pickfit report"
    body_md = text[m.end():] if m else text
    # Mermaid fences become <pre class="mermaid"> so mermaid.js draws them.
    body_md = re.sub(
        r"```mermaid\n(.*?)```",
        lambda b: '<pre class="mermaid">' + html.escape(b.group(1)) + "</pre>",
        body_md,
        flags=re.S,
    )
    md = markdown.Markdown(
        extensions=["tables", "fenced_code", "sane_lists", "attr_list", "md_in_html",
                    TocExtension(toc_depth="2-3", permalink="#", permalink_class="anchor")],
    )
    body = md.convert(body_md)
    first_p = re.search(r"<p>(.*?)</p>", body, re.S)
    lede = re.sub(r"<[^>]+>", "", first_p.group(1)).strip() if first_p else ""
    if first_p and first_p.start() < 40:  # the lede is shown in the hero, not twice
        body = body[:first_p.start()] + body[first_p.end():]
    # Figures (docs/report/figures/*.svg, drawn by figures.py) are inlined, so their colours follow the
    # page's theme; the Markdown links them as images, which GitHub shows in light colours.
    def figure(m: re.Match) -> str:
        caption, name = m.group(1), m.group(2)
        art = (HERE / "figures" / f"{name}.svg").read_text(encoding="utf-8")
        art = re.sub(r'\s(width|height)="\d+"', "", art, count=2)
        return f'<figure class="fig" id="fig-{name}">{art}<figcaption>{caption}</figcaption></figure>'

    body = re.sub(r'<p><img alt="([^"]*)" src="report/figures/([\w-]+)\.svg"\s*/?></p>', figure, body)
    # Wide tables scroll inside their own frame instead of the page.
    body = body.replace("<table>", '<div class="table"><table>').replace("</table>", "</table></div>")
    return title, lede, body, md.toc


def build(source: Path, out: Path) -> Path:
    title, lede, body, toc = render(source)
    page = (HERE / "template.html").read_text(encoding="utf-8")
    description = (lede[:250] + "…") if len(lede) > 250 else lede
    for key, value in {
        "{{title}}": html.escape(title),
        "{{description}}": html.escape(description, quote=True),
        "{{toc}}": toc,
        "{{body}}": body,
        "{{site}}": SITE,
    }.items():
        page = page.replace(key, value)
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(page, encoding="utf-8")
    assets = out / "assets"
    assets.mkdir(exist_ok=True)
    public = ROOT / "worker/public/assets"
    shutil.copy(public / "fonts/bricolage-grotesque.woff2", assets / "bricolage-grotesque.woff2")
    shutil.copy(ROOT / "brand/mascot/states/fitz-success.svg", assets / "fitz-success.svg")
    shutil.copy(ROOT / "brand/mascot/icons/fitz-favicon.svg", assets / "fitz-favicon.svg")
    shutil.copy(ROOT / "brand/mascot/icons/fitz-64.svg", assets / "fitz-64.svg")
    shutil.copy(public / "og/pickfit-en.png", assets / "pickfit-og.png")
    for shot in ("home.png", "tool-page.png"):
        shutil.copy(ROOT / "brand/screenshots" / shot, assets / shot)
    (out / ".nojekyll").write_text("")
    return out / "index.html"


if __name__ == "__main__":
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs/REPORT.md"
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else HERE / "site"
    print(build(src, dst))
