"""Draws the report's figures as SVG files in docs/report/figures/.

    python3 docs/report/figures.py

Colours are the site's tokens (DESIGN.md) as CSS variables with the light value as fallback, so a
figure inlined in the HTML report follows its light or dark theme, and the same file opened on its
own (GitHub's Markdown view) shows the light colours. Every number here is taken from docs/REPORT.md.
"""

from datetime import datetime, timedelta
from html import escape
from pathlib import Path

OUT = Path(__file__).resolve().parent / "figures"

STYLE = """<style>
.f-bg{fill:var(--paper,#F7F7F4)}
.f-box{fill:var(--raised,#FFFFFF);stroke:var(--fitz-line,#4A2E22);stroke-width:2}
.f-soft{fill:var(--raised,#FFFFFF);stroke:var(--line-ctl,#80817A);stroke-width:1}
.f-voice{fill:var(--voice,#F1F6E2);stroke:var(--voice-edge,#A9B77E);stroke-width:1}
.f-quiet{fill:var(--sunk,#F0F1EC)}
.f-rule{stroke:var(--rule,#DEDFD9);stroke-width:1;fill:none}
.f-line{stroke:var(--line-ctl,#80817A);stroke-width:1.5;fill:none}
.f-ink-s{stroke:var(--ink,#1A1D17);stroke-width:2;fill:none}
.f-stitch{stroke:var(--stitch,#C4552D);stroke-width:2;stroke-dasharray:7 5;fill:none}
.f-pass-s{stroke:var(--pass,#2E7A35);stroke-width:2.5;fill:none}
.f-pass{fill:var(--pass,#2E7A35)}
.f-tape{fill:var(--tape,#F5C243);stroke:var(--tape-edge,#A57710);stroke-width:1}
.f-gray{fill:var(--line-ctl,#80817A)}
.f-ink2bar{fill:var(--ink-2,#4F5149)}
.f-arrow{fill:var(--line-ctl,#80817A)}
.f-arrow-st{fill:var(--stitch,#C4552D)}
text{font-family:var(--sans,system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif);fill:var(--ink,#1A1D17)}
.t-h{font-family:var(--display,"Bricolage Grotesque",system-ui,sans-serif);font-weight:700;font-size:15px}
.t-hl{font-family:var(--display,"Bricolage Grotesque",system-ui,sans-serif);font-weight:700;font-size:17px}
.t-b{font-size:12.5px;fill:var(--ink-2,#4F5149)}
.t-s{font-size:11.5px;fill:var(--ink-3,#65655E)}
.t-n{font-family:var(--display,"Bricolage Grotesque",system-ui,sans-serif);font-weight:700;font-size:15px;font-variant-numeric:tabular-nums}
.t-big{font-family:var(--display,"Bricolage Grotesque",system-ui,sans-serif);font-weight:800;font-size:26px}
.t-pass{fill:var(--pass,#2E7A35)}
.t-st{fill:var(--stitch,#C4552D)}
.t-tape{fill:var(--tape-ink,#3A2905)}
.t-halo{stroke:var(--paper,#F7F7F4);stroke-width:5px;stroke-linejoin:round;paint-order:stroke}
</style>"""


def svg(name: str, w: int, h: int, title: str, body: list[str]) -> None:
    p = name  # id prefix, so several inlined figures never share a marker id
    defs = (
        f'<defs><marker id="{p}-a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        f'<path d="M0 0L10 5L0 10z" class="f-arrow"/></marker>'
        f'<marker id="{p}-s" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        f'<path d="M0 0L10 5L0 10z" class="f-arrow-st"/></marker></defs>'
    )
    text = "\n".join(body).replace("MARK_A", f"url(#{p}-a)").replace("MARK_S", f"url(#{p}-s)")
    OUT.mkdir(exist_ok=True)
    (OUT / f"{name}.svg").write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-labelledby="{p}-t">'
        f'<title id="{p}-t">{escape(title)}</title>{STYLE}{defs}'
        f'<rect class="f-bg" width="{w}" height="{h}"/>\n{text}\n</svg>\n',
        encoding="utf-8",
    )


def t(x, y, s, cls="t-b", anchor="start"):
    return f'<text x="{x}" y="{y}" class="{cls}" text-anchor="{anchor}">{escape(str(s))}</text>'


def lines(x, y, rows, cls="t-b", lh=16, anchor="start"):
    return [t(x, y + i * lh, r, cls, anchor) for i, r in enumerate(rows)]


def arrow(x1, y1, x2, y2, cls="f-line", mark="MARK_A"):
    return f'<path d="M{x1} {y1}L{x2} {y2}" class="{cls}" marker-end="{mark}"/>'


def path(d, cls="f-line", mark="MARK_A"):
    return f'<path d="{d}" class="{cls}" marker-end="{mark}"/>'


def box(x, y, w, h, cls="f-box", cut=False):
    if not cut:
        return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="4" class="{cls}"/>'
    c = 14  # the cut corner, like the site's two conversation surfaces
    return f'<path d="M{x+4} {y}H{x+w-c}L{x+w} {y+c}V{y+h-4}Q{x+w} {y+h} {x+w-4} {y+h}H{x+4}Q{x} {y+h} {x} {y+h-4}V{y+4}Q{x} {y} {x+4} {y}Z" class="{cls}"/>'


# 1. The pipeline -----------------------------------------------------------------------------

def pipeline():
    W, H = 740, 420
    bw, bh, gap, x0 = 152, 132, 24, 10
    stages = [
        ("1  Discover", ["GitHub, Show HN,", "Flathub, Homebrew", "Cask, the web and", "submissions"], "no model"),
        ("2  Prescreen", ["Rules drop forks,", "libraries, templates;", "a model makes the", "first cut"], "Muse Spark Open"),
        ("3  Read", ["Facts from the", "README, each with", "a quote the code", "checks"], "Muse Spark 1.3"),
        ("4  Try", ["An agent installs", "and uses it in a", "fresh sandbox; a", "judge checks it"], "Spark Open + 1.3"),
        ("5  Replay", ["A new sandbox", "reruns the steps,", "then the network", "is cut"], "no model"),
        ("6  Score", ["Quality, popularity,", "gem, known", "vulnerabilities,", "visual defects"], "rules, 1.3, OSV, Wonder"),
        ("7  Publish", ["Schema check,", "index, deploy to", "the Worker"], "Cloudflare"),
        ("8  Answer", ["MCP for agents,", "pickfit.app for", "people, each with", "how we know"], "Spark 1.3 matches"),
    ]
    out = []
    for i, (title, body, model) in enumerate(stages):
        row, col = divmod(i, 4)
        x, y = x0 + col * (bw + gap), 24 + row * 200
        last = i == 7
        out.append(box(x, y, bw, bh, "f-voice" if last else "f-box", cut=last))
        out.append(t(x + 14, y + 26, title, "t-h"))
        out += lines(x + 14, y + 47, body, "t-b", 16)
        out.append(t(x + 14, y + bh - 12, model, "t-s t-st" if model in ("no model",) else "t-s"))
        if col < 3:
            out.append(arrow(x + bw + 3, y + bh / 2, x + bw + gap - 3, y + bh / 2))
    # row 1 end down to row 2 start
    x4 = x0 + 3 * (bw + gap) + bw / 2
    out.append(path(f"M{x4} {24+bh+3}V{24+bh+48}H{x0+bw/2}V{24+200-4}"))
    # feedback: a failure report sends the tool back to Try; a submission enters at Discover
    xa = x0 + 3 * (bw + gap) + bw
    out.append(path(f"M{xa+2} {224+bh/2}H{W-14}V{24+bh/2}H{xa+4}", "f-stitch", "MARK_S"))
    out.append(t(W - 20, 24 + bh + 20, "a real failure", "t-s t-st", "end"))
    out.append(t(W - 20, 24 + bh + 34, "report → rerun", "t-s t-st", "end"))
    out.append(t(x0, H - 14, "Only steps that passed in step 4 and again in step 5 are shown to users. Anything else says “not verified” and why.", "t-s"))
    svg("pipeline", W, H, "How pickfit works: discover, prescreen, read, try, replay, score, publish, answer", out)


# 2. The catalogue funnel ------------------------------------------------------------------------

def funnel():
    W, H = 740, 300
    rows = [
        (970, "records in the catalogue", "f-gray"),
        (963, "listed (7 hidden by the developer)", "f-ink2bar"),
        (652, "verified at least through install", "f-pass"),
        (567, "replayed in a fresh sandbox", "f-pass"),
        (132, "hidden gems", "f-tape"),
    ]
    lx, bx, bwid = 10, 300, 360
    out = [t(lx, 24, "The catalogue on 4 Nov 2026", "t-h")]
    for i, (n, label, cls) in enumerate(rows):
        y = 50 + i * 46
        out.append(t(lx, y + 21, label, "t-b"))
        out.append(f'<rect x="{bx}" y="{y+4}" width="{bwid}" height="26" rx="3" class="f-quiet"/>')
        out.append(f'<rect x="{bx}" y="{y+4}" width="{bwid*n/970:.1f}" height="26" rx="3" class="{cls}"/>')
        out.append(t(bx + bwid + 12, y + 23, f"{n:,}", "t-n"))
    out.append(t(lx, H - 14, "A hidden gem is verified, scores at least 80 on quality and at most 45 on popularity, and has no known high or critical vulnerability.", "t-s"))
    svg("funnel", W, H, "The catalogue: 970 records, 963 listed, 652 verified, 567 replayed, 132 hidden gems", out)


# 3. The verification ladder -------------------------------------------------------------------

def ladder():
    W, H = 740, 384
    steps = [
        ("Read", ["quotes checked", "against the", "source"]),
        ("install", ["installs cleanly", "and starts"]),
        ("function", ["a real task", "works; or a live", "service, or a", "model answers"]),
        ("replay", ["fresh box,", "no model, then", "network off"]),
        ("verified", ["the steps can", "be shown to", "users"]),
    ]
    bw, gap, x0 = 124, 22, 10
    out = []
    for i, (name, body) in enumerate(steps):
        x = x0 + i * (bw + gap)
        rise = i * 14
        y = 110 - rise
        last = i == len(steps) - 1
        out.append(box(x, y, bw, 104 + rise, "f-voice" if last else "f-box", cut=last))
        out.append(t(x + 12, y + 26, name, "t-h"))
        out += lines(x + 12, y + 48, body, "t-b", 16)
        if i < len(steps) - 1:
            out.append(arrow(x + bw + 3, 170, x + bw + gap - 3, 170))
    # stitches under the levels a run proved
    out.append(f'<path d="M{x0+bw+gap} 226H{x0+4*(bw+gap)+bw}" class="f-stitch"/>')
    out.append(t(x0 + bw + gap + 60, 244, "stitched on the site: pickfit ran this", "t-s t-st"))
    # branches
    bx = x0 + bw + gap + bw / 2
    out.append(path(f"M{bx} 216V280H{bx+40}"))
    out.append(box(bx + 44, 260, 330, 42, "f-soft"))
    out.append(t(bx + 56, 278, "The sandbox can't run it (GPU, root, account)", "t-b"))
    out.append(t(bx + 56, 294, "→ “not verified” with a reason, never “failed”", "t-s"))
    out.append(box(bx + 44, 310, 330, 42, "f-soft"))
    out.append(t(bx + 56, 328, "“failed” comes only from a human", "t-b"))
    out.append(t(bx + 56, 344, "or a human check of the published files", "t-s"))
    out.append(t(x0, 24, "How a tool earns its level", "t-h"))
    out.append(t(x0, 44, "Levels are computed from the command log, not from what the agent says. A step whose exit code was hidden doesn't count.", "t-s"))
    out.append(t(x0, H - 8, "Desktop apps: a judge reads pickfit's own screenshot. Web apps: a browser agent opens the site and does a core task.", "t-s"))
    svg("ladder", W, H, "Verification levels: read, install, function, replay, verified; environment limits become not verified", out)


# 4. Matching a request -------------------------------------------------------------------------

def matching():
    W, H = 740, 430
    bw, bh, gap, x0 = 206, 104, 40, 10
    cells = [
        (0, 0, "Your need + conditions", ["“free and offline on my", "Mac: subtitles from", "meeting recordings”"], "f-box", True),
        (1, 0, "Hard filters", ["OS, CPU, free, offline,", "data stays local;", "never relaxed"], "f-box", False),
        (2, 0, "Candidate cards", ["up to 60; for a big", "category, BM25 picks", "50 relevant + 10 gems"], "f-box", False),
        (0, 1, "One Muse Spark 1.3 call", ["picks 1–3 with reasons", "that cite card fields,", "only from candidates"], "f-box", False),
        (1, 1, "Program guard", ["drops a pick whose", "reason doesn't match", "its record"], "f-box", False),
        (2, 1, "Answer", ["picks, tradeoffs, best", "free option, how_we_know,", "evidence_url"], "f-voice", True),
    ]
    out = []
    pos = {}
    for col, row, title, body, cls, cut in cells:
        x, y = x0 + col * (bw + gap), 20 + row * 160
        pos[(col, row)] = (x, y)
        out.append(box(x, y, bw, bh, cls, cut=cut))
        out.append(t(x + 14, y + 27, title, "t-h"))
        out += lines(x + 14, y + 50, body, "t-b", 16)
    for c in range(2):
        for r in range(2):
            x, y = pos[(c, r)]
            out.append(arrow(x + bw + 3, y + bh / 2, x + bw + gap - 3, y + bh / 2))
    x, y = pos[(2, 0)]
    out.append(path(f"M{x+bw/2} {y+bh+3}V{y+bh+28}H{x0+bw/2}V{180-4}"))
    # fallback
    mx, my = pos[(0, 1)]
    out.append(path(f"M{mx+bw/2} {my+bh+3}V{my+bh+40}", "f-stitch", "MARK_S"))
    fy = my + bh + 44
    out.append(box(x0 + 30, fy, 470, 70, "f-soft"))
    out.append(t(x0 + 44, fy + 24, "Model off, over budget, slow, or every pick rejected?", "t-h"))
    out.append(t(x0 + 44, fy + 44, "Rank by rules instead: BM25 plus a fixed lexicon.", "t-s"))
    out.append(t(x0 + 44, fy + 60, "The answer says so: matched_by: rules, degraded: true.", "t-s"))
    ax, ay = pos[(2, 1)]
    out.append(path(f"M{x0+500+3} {fy+35}H{ax+bw/2}V{ay+bh+4}", "f-stitch", "MARK_S"))
    svg("matching", W, H, "How find_software matches a request: hard filters, candidate cards, one model call, a guard, and a rules fallback", out)


# 5. The week -------------------------------------------------------------------------------------

def timeline():
    W, H = 740, 430
    px0, px1, py0, py1 = 56, 724, 40, 250
    t0, t1 = datetime(2026, 10, 28, 0, 0), datetime(2026, 11, 4, 6, 0)

    def X(d):
        return px0 + (px1 - px0) * (d - t0).total_seconds() / (t1 - t0).total_seconds()

    def Y(n):
        return py1 - (py1 - py0) * n / 1000

    pts = [((10, 29, 0, 58), 39), ((10, 29, 12, 12), 96), ((10, 31, 2, 24), 165), ((10, 31, 2, 57), 503),
           ((11, 1, 1, 52), 604), ((11, 1, 1, 59), 648), ((11, 1, 22, 57), 689), ((11, 2, 7, 48), 768),
           ((11, 2, 17, 14), 856), ((11, 2, 22, 15), 961), ((11, 3, 20, 16), 963)]
    out = [t(10, 22, "Records in the catalogue, day by day (Taipei time)", "t-h")]
    for n in (0, 250, 500, 750, 1000):
        out.append(f'<path d="M{px0} {Y(n):.1f}H{px1}" class="f-rule"/>')
        out.append(t(px0 - 8, Y(n) + 4, n, "t-s", "end"))
    day = datetime(2026, 10, 28)
    while day <= t1:
        out.append(f'<path d="M{X(day):.1f} {py0}V{py1}" class="f-rule"/>')
        out.append(t(X(day) + 4, py1 + 16, day.strftime("%-m/%-d"), "t-s"))
        day += timedelta(days=1)
    d = ""
    prev = None
    for (mo, dd, hh, mi), n in pts:
        x, y = X(datetime(2026, mo, dd, hh, mi)), Y(n)
        d += f"M{x:.1f} {y:.1f}" if prev is None else f"H{x:.1f}V{y:.1f}"
        prev = (x, y)
    d += f"H{X(datetime(2026, 11, 4, 1, 0)):.1f}"
    out.append(f'<path d="{d}" class="f-pass-s"/>')
    for (mo, dd, hh, mi), n in pts:
        out.append(f'<circle cx="{X(datetime(2026, mo, dd, hh, mi)):.1f}" cy="{Y(n):.1f}" r="3" class="f-pass"/>')
    out.append(t(X(datetime(2026, 11, 2, 22, 15)) - 6, Y(961) - 10, "961", "t-n", "end"))
    out.append(t(X(datetime(2026, 10, 31, 2, 57)) - 6, Y(503) - 8, "503", "t-n", "end"))
    out.append(t(X(datetime(2026, 10, 29, 12, 12)) + 6, Y(96) - 8, "96", "t-n"))
    marks = [
        ((10, 28, 17, 6), "Evaluation frozen"),
        ((10, 29, 2, 18), "Gate G2 met, 10/10"),
        ((10, 29, 13, 6), "First deploy"),
        ((10, 31, 2, 24), "MCP servers added"),
        ((11, 1, 11, 48), "Submit to pick: 2 m 51 s"),
        ((11, 1, 19, 30), "Fitz redesign"),
        ((11, 2, 9, 0), "Evaluation runs"),
        ((11, 2, 21, 7), "Bilingual site"),
        ((11, 2, 23, 39), "pickfit.app"),
        ((11, 3, 5, 47), "Via OpenRouter"),
        ((11, 3, 16, 52), "Security check"),
        ((11, 4, 0, 50), "Demo video"),
    ]
    right = []  # per row, the right edge of the last label placed
    labels = []  # drawn after every leader line, so no line crosses a label
    for (mo, dd, hh, mi), label in marks:
        x = X(datetime(2026, mo, dd, hh, mi))
        wid = len(label) * 6.3
        anchor = "end" if x + wid > W - 6 else "start"
        left, rgt = (x - wid, x) if anchor == "end" else (x - 2, x - 2 + wid)
        row = next((r for r, edge in enumerate(right) if edge < left - 8), len(right))
        if row == len(right):
            right.append(0)
        right[row] = rgt
        ly = py1 + 46 + row * 22
        out.append(f'<path d="M{x:.1f} {py1+22}V{ly-11}" class="f-rule"/>')
        out.append(f'<circle cx="{x:.1f}" cy="{py1+22}" r="3.5" class="f-tape"/>')
        labels.append(t(x - 2 if anchor == "start" else x + 2, ly, label, "t-s t-halo", anchor))
    out += labels
    svg("timeline", W, H, "The week: catalogue growth from 39 records on 29 Oct to 963 on 3 Nov, with milestones", out)


# 6. The evaluation -------------------------------------------------------------------------------

def evaluation():
    W, H = 740, 330
    out = [t(10, 22, "Pre-registered evaluation: questions where the agent found the right software (L1)", "t-h")]
    groups = [("12 medium and hard questions", 12, [("web search only", 6, "f-gray"), ("with pickfit", 8, "f-pass"), ("pickfit, rules only", 6, "f-ink2bar")], 9),
              ("all 20 questions", 20, [("web search only", 14, "f-gray"), ("with pickfit", 16, "f-pass"), ("pickfit, rules only", 14, "f-ink2bar")], None)]
    gx = [10, 380]
    for (title, total, bars, bar_needed), x0 in zip(groups, gx):
        out.append(t(x0, 56, title, "t-b"))
        base, top = 250, 80
        for j, (label, n, cls) in enumerate(bars):
            x = x0 + 10 + j * 108
            hgt = (base - top) * n / total
            out.append(f'<rect x="{x}" y="{base-(base-top):.0f}" width="64" height="{base-top}" rx="3" class="f-quiet"/>')
            out.append(f'<rect x="{x}" y="{base-hgt:.1f}" width="64" height="{hgt:.1f}" rx="3" class="{cls}"/>')
            out.append(t(x + 32, base - hgt - 8, f"{n}/{total}", "t-n", "middle"))
            out.append(t(x + 32, base + 18, label.split(",")[0], "t-s", "middle"))
            if "," in label:
                out.append(t(x + 32, base + 32, label.split(", ")[1], "t-s", "middle"))
        if bar_needed:
            y = base - (base - top) * bar_needed / total
            out.append(f'<path d="M{x0} {y:.1f}H{x0+334}" class="f-stitch"/>')
            out.append(t(x0 + 300, y - 6, "bar: 9", "t-s t-st"))
    out.append(t(10, H - 30, "Result: 8 vs 6, short of the bar, so the pre-written verdict applies: these 20 questions did not prove pickfit better.", "t-s"))
    out.append(t(10, H - 14, "Why: none of the 26 correct answers was in the catalogue, which started with new, little-known tools.", "t-s"))
    svg("evaluation", W, H, "Evaluation: with pickfit 8 of 12, web search only 6 of 12, rules only 6 of 12; the pre-set bar was 9", out)


# 7. What we tried --------------------------------------------------------------------------------

def ledger():
    shipped = [
        ("Open-weight prescreen", "agreed with Muse Spark 1.3 on 34 of 34"),
        ("Resend history each turn", "1–7 s a turn instead of 11–25 s"),
        ("Spark Open runs the sandbox agent", "0.92 of 1.3's pass rate, bar 0.85"),
        ("Quality formula b3.v1 → b3.v5", "gems stopped being 22 of 25 verified"),
        ("Relevance shortlist, rules ranking", "held-out P@5 25.9% → 32.9%"),
        ("Aimed clicks (zoom and re-aim)", "small controls hit 5 of 14 → 13 of 14"),
        ("Visual-defect deduction", "×0.95 for app-caused defects, 186 checked"),
        ("Known-vulnerability cap at 79", "hidden gems 161 → 132"),
        ("Translation by Muse Spark Open", "about $0.0045 a tool, effort medium"),
    ]
    dropped = [
        ("Usability scores", "two pre-registered rounds missed the bar"),
        ("Severity-based deductions", "second judge kept 1 of 4 real majors"),
        ("A longer GUI step cap", "60 steps rescued 0 of 12 stuck apps"),
        ("Spark Open for extraction", "62–71% field agreement, bar 90%"),
        ("SAM 3.1 as a click locator", "found 8 of 19 icons"),
        ("Planning agent sees the window", "features checked 0 vs 1 on 1.3"),
        ("jobs phrases for ranking", "no recorded result; kept on a tag"),
        ("Well-known reference records", "an unverified option shipped instead"),
    ]
    W = 740
    rows = max(len(shipped), len(dropped))
    H = 70 + rows * 46 + 30
    out = [t(10, 24, "Shipped", "t-hl t-pass"), t(380, 24, "Tried and not shipped", "t-hl")]
    for col, items, ok in ((10, shipped, True), (380, dropped, False)):
        for i, (name, note) in enumerate(items):
            y = 50 + i * 46
            out.append(f'<path d="M{col} {y-8}H{col+350}" class="f-rule"/>')
            if ok:
                out.append(f'<path d="M{col+2} {y+10}l5 5l10 -11" class="f-pass-s"/>')
            else:
                out.append(f'<path d="M{col+3} {y+3}l11 11M{col+14} {y+3}l-11 11" class="f-line"/>')
            out.append(t(col + 26, y + 13, name, "t-h"))
            out.append(t(col + 26, y + 30, note, "t-s"))
    out.append(t(10, H - 12, "Bars for every experiment were committed before the first paid call. Unmerged code is kept as git tags under archive/.", "t-s"))
    svg("ledger", W, H, "Experiments that shipped and experiments that were tried and not shipped", out)


# 8. The trust chain ------------------------------------------------------------------------------

def trust():
    layers = [
        ("Quote check", "every extracted fact carries a quote the code finds in the source", "invented facts"),
        ("Command log", "levels come from what ran and exited 0; hidden exit codes don't count", "claimed success"),
        ("A separate judge", "another model call reads the output or screenshot", "output that misses the feature"),
        ("Fresh offline replay", "a new sandbox reruns the steps with no model, then offline", "steps that worked once"),
        ("Security and visual checks", "OSV.dev advisories cap quality; screenshot defects cost 5%", "known risks, broken screens"),
        ("Labels in the answer", "how_we_know, evidence_url, “not verified”, matched_by", "over-trust"),
    ]
    W, H = 740, 70 + len(layers) * 54 + 20
    out = [t(10, 24, "Six checks between a README and an answer", "t-h"), t(560, 24, "what it catches", "t-s")]
    for i, (name, what, catches) in enumerate(layers):
        y = 44 + i * 54
        out.append(box(10, y, 530, 44, "f-box" if i < len(layers) - 1 else "f-voice"))
        out.append(f'<circle cx="34" cy="{y+22}" r="12" class="f-tape"/>')
        out.append(t(34, y + 27, i + 1, "t-n t-tape", "middle"))
        out.append(t(56, y + 19, name, "t-h"))
        out.append(t(56, y + 36, what, "t-s"))
        out.append(arrow(548, y + 22, 556, y + 22))
        out.append(t(562, y + 27, catches, "t-b"))
        if i < len(layers) - 1:
            out.append(f'<path d="M34 {y+44}V{y+54}" class="f-stitch"/>')
    svg("trust", W, H, "Six checks between a README and an answer: quote check, command log, separate judge, offline replay, security and visual checks, labels", out)


if __name__ == "__main__":
    for f in (pipeline, funnel, ladder, matching, timeline, evaluation, ledger, trust):
        f()
    print(sorted(p.name for p in OUT.glob("*.svg")))
