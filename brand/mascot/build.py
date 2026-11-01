#!/usr/bin/env python3
"""Build the Fitz mascot SVGs from one set of shapes and one palette.

Every file in brand/mascot/ except README.md, index.html and this script is
written by this script, so palette and line weight stay the same everywhere.

    python3 brand/mascot/build.py

Version 3: an egg-shaped body with a small tuft on top, small dot eyes set far
apart, a tiny diamond beak between them, the measuring tape as one simple band
with a short loose end, small side-flap wings, and the tail sweeping up from
behind. Two poses share every part: "front" (default) and "turn" (head turned
about three-quarters to the right, so the beak becomes a small side triangle
that can hold the tape end or a leaf).
"""

from __future__ import annotations

import math
from pathlib import Path

HERE = Path(__file__).parent

# ---------------------------------------------------------------- palette
INK = "#4A2E22"  # outlines, eyes
BODY = "#A9BC4C"  # olive yellow-green
WING = "#869E3A"  # darker olive: wings
TAIL = "#7C9334"  # darkest olive: tail
CAP = "#C4552D"  # rufous cap and tuft
BELLY = "#FFF3D3"  # cream
BEAK = "#F0A04B"  # beak, lower half
BEAK_TOP = "#CF6F2A"  # beak, upper half (a little darker)
TAPE = "#F5C243"  # measuring tape
METAL = "#C3CAD2"  # tape end tab
BLUSH = "#F2917C"
WHITE = "#FFFFFF"
SWEAT = "#7CC0E8"
LEAF = "#6CBF4E"
LEAF_DARK = "#3E8A3A"
BOX = "#E8BC7E"
BOX_DARK = "#C9924E"
SPARK = "#F5C243"
BAD = "#D9533C"
GOOD = "#4CA65A"

SW = 4.5  # outer line weight (200-unit canvas)
SW2 = 3  # inner detail line weight

# ---------------------------------------------------------------- geometry
# Egg: a little narrower at the top, one chubby head-body mass.
BODY_PATH = (
    "M100 62 C 136 62, 163 98, 163 136 C 163 166, 136 186, 100 186 "
    "C 64 186, 37 166, 37 136 C 37 98, 64 62, 100 62 Z"
)

# Tail: grows from behind the body and sweeps up and back past the left shoulder.
TAIL_PATH = (
    "M70 104 L42 122 C 33 107, 22 90, 15 73 Q 10 58 22 53.5 Q 34 49.5 38.5 63 "
    "C 43 78, 55 92, 70 104 Z"
)
TAIL_SPLIT = "M22.5 55 Q 25 60 27 66"

TUFT = "M93 67 C 86 57, 90 44, 104 41 C 99 49, 103 57, 111 65 Z"

POSES = {
    "front": dict(
        eyes=((72, 118, 1.0), (128, 118, 1.0)),
        cap="M28 118 C 44 100, 62 94, 80 96 C 88 97, 94 103, 100 110 C 106 103, 112 97, 120 96 "
        "C 138 94, 156 100, 172 118 L172 40 L28 40 Z",
        blush=((62, 130, 7, 3.8), (138, 130, 7, 3.8)),
        band=(((32, 134), (100, 154), (168, 134)), ((32, 144.5), (100, 165), (168, 144.5))),
        end_x=118,
        wings=(
            "M47 139 C 55 145, 57 160, 50 170 C 44 168, 39 156, 40 143 Z",
            "M153 139 C 145 145, 143 160, 150 170 C 156 168, 161 156, 160 143 Z",
        ),
        tuft="",
        belly=(100, 173),
    ),
    "turn": dict(
        eyes=((100, 118, 1.0), (146, 110, 0.72)),
        cap="M28 112 C 48 96, 76 90, 104 92 C 118 93, 126 96, 131 102 L138 111.5 L145 101 "
        "C 152 97, 166 96, 178 99 L178 40 L28 40 Z",
        blush=((86, 131, 7, 3.8),),
        band=(((32, 132), (118, 154), (168, 128)), ((32, 142.5), (118, 165), (168, 138.5))),
        end_x=104,
        wings=("M54 139 C 66 145, 70 161, 60 173 C 52 171, 44 159, 46 145 Z",),
        tuft='transform="rotate(-14 100 66) translate(-6 0)"',
        belly=(110, 173),
    ),
}

SHADOW = f'<ellipse class="shadow" cx="100" cy="194" rx="40" ry="3.6" fill="{INK}" opacity=".12"/>'


def qpt(p, t):
    (x0, y0), (x1, y1), (x2, y2) = p
    a, b, c = (1 - t) ** 2, 2 * t * (1 - t), t * t
    return a * x0 + b * x1 + c * x2, a * y0 + b * y1 + c * y2


def qtan(p, t):
    (x0, y0), (x1, y1), (x2, y2) = p
    dx = 2 * (1 - t) * (x1 - x0) + 2 * t * (x2 - x1)
    dy = 2 * (1 - t) * (y1 - y0) + 2 * t * (y2 - y1)
    n = math.hypot(dx, dy)
    return dx / n, dy / n


def t_at_x(p, x):
    lo, hi = 0.0, 1.0
    for _ in range(40):
        mid = (lo + hi) / 2
        if qpt(p, mid)[0] < x:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def f(v):
    return f"{v:.1f}".rstrip("0").rstrip(".")


def qd(p):
    (x0, y0), (x1, y1), (x2, y2) = p
    return f"M{f(x0)} {f(y0)} Q{f(x1)} {f(y1)} {f(x2)} {f(y2)}"


# ---------------------------------------------------------------- parts
def eye(cx, cy, kind, k=1.0):
    """One small dot eye, wrapped in <g class="eye"> so it can blink. k narrows the far eye."""
    rx, ry = 5.2 * k, 6.2
    if kind in ("open", "look_up", "look_down", "wide"):
        dy = {"look_up": -1.8, "look_down": 2}.get(kind, 0)
        if kind == "wide":
            rx, ry = rx * 1.3, ry * 1.3
        return (
            f'<g class="eye"><ellipse cx="{f(cx)}" cy="{f(cy + dy)}" rx="{f(rx)}" ry="{f(ry)}" fill="{INK}"/>'
            f'<circle cx="{f(cx - 1.5 * k)}" cy="{f(cy + dy - 2.2)}" r="{f(1.7 if kind == "wide" else 1.5)}" fill="{WHITE}"/></g>'
        )
    w = 6 * k
    if kind == "happy":  # closed, smiling arcs
        d = f"M{f(cx - w)} {f(cy + 2)} Q{f(cx)} {f(cy - 6)} {f(cx + w)} {f(cy + 2)}"
    elif kind == "proud":  # pointed ^ ^, chin goes up with it
        d = f"M{f(cx - w)} {f(cy + 2.5)} L{f(cx)} {f(cy - 4)} L{f(cx + w)} {f(cy + 2.5)}"
    else:
        raise ValueError(kind)
    return (
        f'<g class="eye"><path d="{d}" fill="none" stroke="{INK}" stroke-width="3.6" '
        f'stroke-linecap="round" stroke-linejoin="round"/></g>'
    )


# (left brow, right brow) as points relative to each eye centre:
# two points = straight line, three = start, control, end of a curve.
BROWS = {
    "worried": (((-7, -10), (5, -14)), ((-5, -14), (7, -10))),
    "raised": (((-6.5, -13), (0, -18), (6.5, -13)), ((-6.5, -13), (0, -18), (6.5, -13))),
    "curious": (((-6, -12), (5, -12.5)), ((-5.5, -14), (0, -20), (5.5, -14))),
    "determined": (((-6.5, -14), (5, -10.5)), ((-5, -10.5), (6.5, -14))),
}


def _brow(pts, x, y, k):
    p = [(x + a * k, y + b) for a, b in pts]
    if len(p) == 2:
        return f"M{f(p[0][0])} {f(p[0][1])} L{f(p[1][0])} {f(p[1][1])}"
    return f"M{f(p[0][0])} {f(p[0][1])} Q{f(p[1][0])} {f(p[1][1])} {f(p[2][0])} {f(p[2][1])}"


def brows(kind, eyes):
    if not kind:
        return ""
    s = f'stroke="{INK}" stroke-width="3.2" stroke-linecap="round" fill="none"'
    return (
        '<g class="brows">'
        + "".join(f'<path d="{_brow(pts, x, y, k)}" {s}/>' for pts, (x, y, k) in zip(BROWS[kind], eyes))
        + "</g>"
    )


def beak(kind="closed", pose="front"):
    """Front: a tiny diamond between the eyes. Turn: a small side triangle on the face."""
    s = f'stroke="{INK}" stroke-width="2.4" stroke-linejoin="round"'
    if pose == "turn":
        up = "M139.5 117.5 L161.5 123 L138 123.5 Z"
        lo = "M138 123.5 L161.5 123 L140 129 Z"
        inner = f'<path d="{lo}" fill="{BEAK}" {s}/><path d="{up}" fill="{BEAK_TOP}" {s}/>'
        return f'<g class="beak">{inner}</g>'
    if kind == "open":
        inner = (
            f'<ellipse cx="100" cy="126.5" rx="4.2" ry="3.4" fill="{INK}"/>'
            f'<path d="M94.5 129 L105.5 129 L100 135.5 Z" fill="{BEAK}" {s}/>'
            f'<path d="M93.5 123.5 L100 116.5 L106.5 123.5 Z" fill="{BEAK_TOP}" {s}/>'
        )
    else:
        inner = (
            f'<path d="M93.5 124 L106.5 124 L100 131 Z" fill="{BEAK}" {s}/>'
            f'<path d="M93.5 124 L100 117.5 L106.5 124 Z" fill="{BEAK_TOP}" {s}/>'
        )
    return f'<g class="beak">{inner}</g>'


def tape_ticks(top):
    out = []
    for i, t in enumerate([0.1 + k * 0.065 for k in range(13)]):
        x, y = qpt(top, t)
        tx, ty = qtan(top, t)
        nx, ny = -ty, tx
        if ny < 0:
            nx, ny = -nx, -ny
        ln = 5 if i % 2 == 0 else 3.2
        out.append(f"M{f(x)} {f(y)} L{f(x + nx * ln)} {f(y + ny * ln)}")
    return " ".join(out)


def band(cid, pose, ink=INK):
    """The tape: one band around the neck, plus a short loose end. Same idea as v1."""
    top, bot = POSES[pose]["band"]
    c, d = bot[0], bot[2]
    shape = f"{qd(top)} L{f(d[0])} {f(d[1])} Q{f(bot[1][0])} {f(bot[1][1])} {f(c[0])} {f(c[1])} Z"
    x = POSES[pose]["end_x"]
    _, y = qpt(bot, t_at_x(bot, x))
    end = (
        f'<g transform="translate({f(x)} {f(y - 6)}) rotate(-6)">'
        f'<rect x="-5.5" y="0" width="11" height="19" rx="1.5" fill="{TAPE}" stroke="{ink}" stroke-width="{SW2}"/>'
        f'<path d="M-5.5 7 L-1.5 7 M-5.5 12.5 L0 12.5" stroke="{ink}" stroke-width="1.8" stroke-linecap="round"/>'
        f'<rect x="-5.5" y="16" width="11" height="6" rx="1.5" fill="{METAL}" stroke="{ink}" stroke-width="{SW2}"/></g>'
    )
    return (
        end
        + f'<g class="band" clip-path="url(#{cid})"><path d="{shape}" fill="{TAPE}"/>'
        f'<path d="{tape_ticks(top)}" stroke="{ink}" stroke-width="1.8" stroke-linecap="round"/>'
        f'<path d="{qd(top)}" fill="none" stroke="{ink}" stroke-width="{SW2}"/>'
        f'<path d="{qd(bot)}" fill="none" stroke="{ink}" stroke-width="{SW2}"/></g>'
    )


def feet():
    s = f'stroke="{INK}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" fill="none"'
    foot = "M{x} 183 L{x} 191 M{a} 194 L{x} 191 L{b} 194 M{x} 191 L{x} 195.5"
    return (
        f'<g class="feet"><path d="{foot.format(x=88, a=82, b=94)}" {s}/>'
        f'<path d="{foot.format(x=112, a=106, b=118)}" {s}/></g>'
    )


def bird(cid="fitz", pose="front", eyes="open", brow=None, beak_kind="closed", blush=True):
    P = POSES[pose]
    e = "".join(eye(x, y, eyes, k) for x, y, k in P["eyes"])
    bx, by = P["belly"]
    wings = "".join(
        f'<g class="wing {side}"><path d="{d}" fill="{WING}" stroke="{INK}" stroke-width="{SW2}" stroke-linejoin="round"/></g>'
        for side, d in zip(("l", "r"), P["wings"])
    )
    return (
        f'<defs><clipPath id="{cid}"><path d="{BODY_PATH}"/></clipPath></defs>'
        + SHADOW
        + '<g class="bird">'
        + feet()
        + f'<g class="tail"><g transform="translate(9.3 16.8) scale(.85)"><path d="{TAIL_PATH}" fill="{TAIL}" stroke="{INK}" stroke-width="{SW / .85:.2f}" stroke-linejoin="round"/>'
        f'<path d="{TAIL_SPLIT}" fill="none" stroke="{INK}" stroke-width="2.9" stroke-linecap="round"/></g></g>'
        + f'<g class="tuft" {P["tuft"]}><path d="{TUFT}" fill="{CAP}" stroke="{INK}" stroke-width="{SW}" stroke-linejoin="round"/></g>'
        + '<g class="body">'
        + f'<path d="{BODY_PATH}" fill="{BODY}"/>'
        + f'<g clip-path="url(#{cid})"><path d="{P["cap"]}" fill="{CAP}"/>'
        f'<ellipse cx="{bx}" cy="{by}" rx="46" ry="26" fill="{BELLY}"/></g>'
        + band(cid, pose)
        + f'<path d="{BODY_PATH}" fill="none" stroke="{INK}" stroke-width="{SW}"/>'
        + wings
        + (
            f'<g class="blush" fill="{BLUSH}" opacity=".55">'
            + "".join(f'<ellipse cx="{x}" cy="{y}" rx="{rx}" ry="{ry}"/>' for x, y, rx, ry in P["blush"])
            + "</g>"
            if blush
            else ""
        )
        + f'<g class="pupils">{e}</g>'
        + brows(brow, P["eyes"])
        + beak(beak_kind, pose)
        + "</g></g>"
    )


# ---------------------------------------------------------------- accents
def sparks(cls="sparks"):
    s = f'stroke="{SPARK}" stroke-width="4.5" stroke-linecap="round"'
    return (
        f'<g class="{cls}">'
        f'<path d="M156 50 L159 39" {s}/><path d="M166 58 L175 51" {s}/><path d="M170 70 L180 69" {s}/></g>'
    )


def star(x, y, r, cls="star", color=SPARK):
    k = r * 0.18
    d = (
        f"M{f(x)} {f(y - r)} Q{f(x + k)} {f(y - k)} {f(x + r)} {f(y)} "
        f"Q{f(x + k)} {f(y + k)} {f(x)} {f(y + r)} Q{f(x - k)} {f(y + k)} {f(x - r)} {f(y)} "
        f"Q{f(x - k)} {f(y - k)} {f(x)} {f(y - r)} Z"
    )
    return f'<path class="{cls}" d="{d}" fill="{color}"/>'


def question(x, y, cls="question"):
    return (
        f'<g class="{cls}" transform="translate({x} {y})" fill="none" stroke="{CAP}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round">'
        f'<path d="M-6 -7 Q-6 -15 1 -15 Q8 -15 8 -8 Q8 -3 2 -0.5 L2 4"/>'
        f'<circle cx="2" cy="11" r="1.2" fill="{CAP}"/></g>'
    )


def sweat(x, y, cls="sweat"):
    return (
        f'<g transform="translate({x} {y})"><g class="{cls}">'
        f'<path d="M0 -10 C4 -4 7 0 7 3.5 A7 7 0 0 1 -7 3.5 C-7 0 -4 -4 0 -10 Z" fill="{SWEAT}"/>'
        f'<path d="M-3 2.5 Q-3 5 -1 6" stroke="{WHITE}" stroke-width="1.8" stroke-linecap="round" fill="none"/></g></g>'
    )


def exclaim(cls="exclaim"):
    s = f'stroke="{CAP}" stroke-width="4.5" stroke-linecap="round"'
    return (
        f'<g class="{cls}"><path d="M161 46 L163 30" {s}/><path d="M172 56 L182 44" {s}/>'
        f'<path d="M176 70 L190 66" {s}/></g>'
    )


# ---------------------------------------------------------------- props
BEAK_TIP = (161, 123)  # tip of the turned beak: where props are held


def leaf(cls="leaf"):
    """A stitched leaf held at the beak tip: what Fitz presents."""
    shape = "M0 0 C 10 -24, 44 -32, 66 -22 C 54 -2, 26 10, 0 0 Z"
    rib = "M2 -1 Q 30 -11 62 -21"
    stitches = " ".join(
        f"M{f(sx - 3)} {f(sy - 4)} L{f(sx + 3)} {f(sy + 4)}"
        for sx, sy in [(18, -6.5), (30, -10.5), (42, -14.3), (53, -17.5)]
    )
    x, y = BEAK_TIP
    return (
        f'<g class="{cls}"><g transform="translate({x - 4} {y + 1}) rotate(4)">'
        f'<path d="{shape}" fill="{LEAF}" stroke="{INK}" stroke-width="{SW2}" stroke-linejoin="round"/>'
        f'<path d="{rib}" fill="none" stroke="{LEAF_DARK}" stroke-width="2.4" stroke-linecap="round"/>'
        f'<path d="{stitches}" stroke="{BELLY}" stroke-width="2.4" stroke-linecap="round"/>'
        f"</g></g>"
    )


def package(x=212, y=134, w=72, h=58):
    """A software package: a box with </> on it."""
    cx = x + w / 2
    my = y + h / 2 + 4
    return (
        f'<g class="package">'
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="7" fill="{BOX}" stroke="{INK}" stroke-width="{SW}"/>'
        f'<path d="M{x + 2} {y + 14} L{x + w - 2} {y + 14}" stroke="{BOX_DARK}" stroke-width="{SW2}"/>'
        f'<path d="M{f(cx - 10)} {f(my - 7)} L{f(cx - 17)} {f(my)} L{f(cx - 10)} {f(my + 7)} '
        f'M{f(cx + 10)} {f(my - 7)} L{f(cx + 17)} {f(my)} L{f(cx + 10)} {f(my + 7)} '
        f'M{f(cx + 3)} {f(my - 9)} L{f(cx - 3)} {f(my + 9)}" fill="none" stroke="{INK}" stroke-width="{SW2}" '
        f'stroke-linecap="round" stroke-linejoin="round"/></g>'
    )


def strip(x0, length, y=119, h=9, cls="strip"):
    """A straight run of tape from the beak tip, with its hook end."""
    ticks = " ".join(
        f"M{f(x)} {f(y)} L{f(x)} {f(y + (5 if k % 2 == 0 else 3))}"
        for k, x in enumerate(range(x0 + 6, x0 + length - 3, 6))
    )
    xe = x0 + length
    return (
        f'<g class="{cls}">'
        f'<rect x="{x0 - 6}" y="{y}" width="{length + 6}" height="{h}" fill="{TAPE}" stroke="{INK}" stroke-width="{SW2}"/>'
        f'<path d="{ticks}" stroke="{INK}" stroke-width="2" stroke-linecap="round"/>'
        f'<path d="M{xe} {f(y - 1)} L{xe + 4} {f(y - 1)} L{xe + 4} {f(y + h + 7)} L{xe} {f(y + h + 7)} Z" '
        f'fill="{METAL}" stroke="{INK}" stroke-width="2.5" stroke-linejoin="round"/></g>'
    )


def check_badge(x, y, r=15, cls="badge"):
    return (
        f'<g class="{cls}"><circle cx="{x}" cy="{y}" r="{r}" fill="{GOOD}" stroke="{INK}" stroke-width="{SW2}"/>'
        f'<path d="M{x - 6.5} {y + 0.5} L{x - 1.5} {y + 5.5} L{x + 7} {y - 5}" fill="none" stroke="{WHITE}" '
        f'stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/></g>'
    )


# ---------------------------------------------------------------- documents
REDUCED = "@media (prefers-reduced-motion: reduce){*{animation:none!important}}"


def doc(view, body, title, desc, css="", size=None):
    w, h = size or view.split()[2:]
    style = f"<style>{css}{REDUCED}</style>" if css else ""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view}" width="{w}" height="{h}" '
        f'role="img" aria-labelledby="t d">'
        f'<title id="t">{title}</title><desc id="d">{desc}</desc>{style}{body}</svg>\n'
    )


def write(name, text):
    p = HERE / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    print("wrote", p.relative_to(HERE))


# ---------------------------------------------------------------- build
EXPRESSIONS = {
    "neutral": dict(eyes="open"),
    "happy": dict(eyes="happy", extra=lambda: sparks()),
    "thinking": dict(eyes="look_up", brow="curious", extra=lambda: question(170, 50), tilt=-6),
    "surprised": dict(eyes="wide", brow="raised", beak_kind="open", extra=lambda: exclaim(), blush=False),
    "sorry": dict(eyes="look_down", brow="worried", extra=lambda: sweat(160, 70)),
    "proud": dict(eyes="proud", tilt=-4, extra=lambda: star(164, 48, 11) + star(182, 72, 6)),
}

VIEW = "0 0 200 200"


def build_expressions():
    for name, o in EXPRESSIONS.items():
        b = bird(eyes=o["eyes"], brow=o.get("brow"), beak_kind=o.get("beak_kind", "closed"), blush=o.get("blush", True))
        if o.get("tilt"):
            b = f'<g transform="rotate({o["tilt"]} 100 192)">{b}</g>'
        extra = o["extra"]() if "extra" in o else ""
        write(
            f"expressions/fitz-{name}.svg",
            doc(VIEW, b + extra, f"Fitz, {name}", f"Fitz the tailorbird, {name} expression."),
        )


def build_main():
    desc = (
        "Fitz, the PickFit tailorbird: an egg-shaped olive bird with a rufous cap and tuft, small dot eyes, "
        "a tiny diamond beak, its tail cocked up behind, and a tailor's measuring tape around its neck."
    )
    write("fitz.svg", doc(VIEW, bird(), "Fitz", desc))
    write("fitz-turn.svg", doc(VIEW, bird(cid="fitz-turn", pose="turn"), "Fitz, turned",
                               "Fitz with its head turned to the right; the small beak shows from the side."))


# ------------------------------------------------ animated states
BIRD_PIVOT = "transform-box:fill-box;transform-origin:50% 100%;"
PIVOTS = (
    ".tail{transform-box:fill-box;transform-origin:90% 92%}"
    ".wing{transform-box:fill-box;transform-origin:50% 5%}"
    ".eye{transform-box:fill-box;transform-origin:50% 50%}"
)


def build_states():
    # idle: blink, tail bob, breathing
    css = (
        PIVOTS
        + f".bird{{{BIRD_PIVOT}animation:breathe 4s ease-in-out infinite}}"
        ".tail{animation:bob 4s ease-in-out infinite}"
        ".eye{animation:blink 4s ease-in-out infinite}"
        "@keyframes breathe{0%,100%{transform:scale(1,1)}50%{transform:scale(1.012,.986)}}"
        "@keyframes bob{0%,55%,100%{transform:rotate(0)}64%{transform:rotate(-8deg)}74%{transform:rotate(4deg)}84%{transform:rotate(-2deg)}}"
        "@keyframes blink{0%,40%,48%,100%{transform:scaleY(1)}44%{transform:scaleY(.12)}}"
    )
    write("states/fitz-idle.svg", doc(VIEW, bird(), "Fitz, idle", "Fitz blinks and bobs its tail.", css))

    # searching: head tilts, looks left and right, dots
    css = (
        PIVOTS
        + f".bird{{{BIRD_PIVOT}animation:tilt 3.2s ease-in-out infinite}}"
        ".pupils{animation:look 3.2s ease-in-out infinite}"
        ".tail{animation:bob 3.2s ease-in-out infinite}"
        ".dot{animation:dot 1.2s ease-in-out infinite}.dot:nth-child(2){animation-delay:.2s}.dot:nth-child(3){animation-delay:.4s}"
        "@keyframes tilt{0%,100%{transform:rotate(0)}18%,38%{transform:rotate(-6deg)}60%,80%{transform:rotate(6deg)}}"
        "@keyframes look{0%,100%{transform:translateX(0)}18%,38%{transform:translateX(-3.5px)}60%,80%{transform:translateX(3.5px)}}"
        "@keyframes bob{0%,100%{transform:rotate(0)}50%{transform:rotate(-4deg)}}"
        "@keyframes dot{0%,100%{opacity:.25;transform:translateY(0)}40%{opacity:1;transform:translateY(-4px)}}"
    )
    dots = "".join(f'<circle class="dot" cx="{x}" cy="54" r="4.5" fill="{CAP}"/>' for x in (158, 172, 186))
    write(
        "states/fitz-searching.svg",
        doc(VIEW, bird(brow="curious") + f"<g>{dots}</g>", "Fitz, searching",
            "Fitz tilts its head and looks left and right while searching.", css),
    )

    # Turned poses: the tape runs from the beak tip to a package on the right.
    tip_x = int(BEAK_TIP[0])
    x0 = tip_x + 2
    reel = f'<defs><clipPath id="reel"><rect x="{x0 - 4}" y="100" width="{300 - x0}" height="60"/></clipPath></defs>'

    # testing
    view = "0 0 300 200"
    full = 284 - x0
    css = (
        PIVOTS
        + ".tail{animation:bob 3.2s ease-in-out infinite}"
        ".strip{animation:pull 3.2s cubic-bezier(.5,0,.3,1) infinite}"
        ".eye{animation:blink 3.2s ease-in-out infinite}"
        ".edge{animation:edge 3.2s ease-in-out infinite}"
        "@keyframes bob{0%,100%{transform:rotate(0)}40%{transform:rotate(-5deg)}55%{transform:rotate(2deg)}}"
        f"@keyframes pull{{0%,8%{{transform:translateX(-{full + 8}px)}}36%,72%{{transform:translateX(0)}}92%,100%{{transform:translateX(-{full + 8}px)}}}}"
        "@keyframes blink{0%,80%,88%,100%{transform:scaleY(1)}84%{transform:scaleY(.12)}}"
        "@keyframes edge{0%,34%,74%,100%{opacity:0}40%,68%{opacity:1}}"
    )
    body = (
        package()
        + reel
        + f'<g clip-path="url(#reel)">{strip(x0, full)}</g>'
        + bird(cid="fitz-test", pose="turn", brow="determined")
        + f'<path class="edge" d="M293 108 L293 138" stroke="{GOOD}" stroke-width="3" stroke-linecap="round" stroke-dasharray="4 5"/>'
    )
    write("states/fitz-testing.svg", doc(view, body, "Fitz, testing",
                                         "Fitz turns its head and pulls its measuring tape across a software package.", css))

    # test failed
    short = 254 - x0
    css = (
        PIVOTS
        + f".shake{{{BIRD_PIVOT}animation:shake 3.4s ease-in-out infinite}}"
        ".strip{animation:pull 3.4s cubic-bezier(.5,0,.3,1) infinite}"
        ".gap{animation:gap 3.4s ease-in-out infinite}"
        ".sweat{animation:drop 3.4s ease-in-out infinite}"
        ".wing{animation:droop 3.4s ease-in-out infinite}"
        f"@keyframes pull{{0%,6%{{transform:translateX(-{short + 8}px)}}26%{{transform:translateX(0)}}30%{{transform:translateX(-5px)}}"
        f"34%,52%{{transform:translateX(0)}}64%,100%{{transform:translateX(-{short + 8}px)}}}}"
        "@keyframes shake{0%,64%,90%,100%{transform:rotate(0)}68%{transform:rotate(-4deg)}74%{transform:rotate(4deg)}80%{transform:rotate(-3deg)}86%{transform:rotate(2deg)}}"
        "@keyframes gap{0%,30%,60%,100%{opacity:0}36%,54%{opacity:1}}"
        "@keyframes drop{0%,38%,94%,100%{opacity:0;transform:translateY(-4px)}46%,86%{opacity:1;transform:translateY(0)}}"
        "@keyframes droop{0%,36%,94%,100%{transform:rotate(0)}46%,86%{transform:rotate(8deg)}}"
    )
    gap = (
        f'<g class="gap" stroke="{BAD}" stroke-width="3" stroke-linecap="round" fill="none">'
        f'<path d="M261 108 L284 108" stroke-dasharray="3 5"/><path d="M261 103 L261 113 M284 103 L284 113"/>'
        f'<path d="M268 83 L278 93 M278 83 L268 93" stroke-width="3.5"/></g>'
    )
    body = (
        package()
        + '<g class="shake">' + reel + f'<g clip-path="url(#reel)">{strip(x0, short)}</g>'
        + bird(cid="fitz-fail", pose="turn", eyes="look_down", brow="worried") + "</g>"
        + gap
        + sweat(154, 64)
    )
    write("states/fitz-test-failed.svg", doc(view, body, "Fitz, test failed",
                                             "Fitz's tape comes up short of the package; it shakes its head, sorry.", css))

    # recommending: presents a stitched leaf held in the side beak
    view = "0 0 250 200"
    css = (
        PIVOTS
        + f".offer{{{BIRD_PIVOT}animation:offer 2.6s ease-in-out infinite}}"
        ".tail{animation:bob 2.6s ease-in-out infinite}"
        ".wing{animation:lift 2.6s ease-in-out infinite}"
        ".star{transform-box:fill-box;transform-origin:50% 50%;animation:twinkle 2.6s ease-in-out infinite}"
        ".star.s2{animation-delay:.35s}.star.s3{animation-delay:.7s}"
        "@keyframes offer{0%,100%{transform:rotate(0) translateY(0)}35%,65%{transform:rotate(3deg) translateY(-3px)}}"
        "@keyframes bob{0%,100%{transform:rotate(0)}45%{transform:rotate(-7deg)}60%{transform:rotate(2deg)}}"
        "@keyframes lift{0%,100%{transform:rotate(0)}35%,65%{transform:rotate(-14deg)}}"
        "@keyframes twinkle{0%,100%{transform:scale(.55);opacity:.5}40%{transform:scale(1.1);opacity:1}}"
    )
    body = (
        '<g class="offer">' + leaf() + bird(cid="fitz-rec", pose="turn", eyes="happy") + "</g>"
        + star(222, 76, 9, "star") + star(242, 104, 6, "star s2") + star(200, 62, 5, "star s3")
    )
    write("states/fitz-recommending.svg", doc(view, body, "Fitz, recommending",
                                              "Fitz turns and holds out a stitched leaf: this one fits.", css))

    # success: hop with both wings up, sparkles and a check badge
    view = "0 0 210 200"
    css = (
        PIVOTS
        + f".bird{{{BIRD_PIVOT}animation:hop 1.8s cubic-bezier(.3,0,.4,1) infinite}}"
        ".tail{animation:flick 1.8s ease-in-out infinite}"
        ".wing.l{animation:flapl 1.8s ease-in-out infinite}.wing.r{animation:flapr 1.8s ease-in-out infinite}"
        ".badge{transform-box:fill-box;transform-origin:50% 50%;animation:pop 1.8s ease-out infinite}"
        ".sparks{animation:fade 1.8s ease-in-out infinite}"
        "@keyframes hop{0%,100%{transform:translateY(0) scale(1,1)}10%{transform:translateY(0) scale(1.05,.94)}"
        "35%{transform:translateY(-14px) scale(.97,1.04)}60%{transform:translateY(0) scale(1.04,.95)}72%{transform:translateY(0) scale(1,1)}}"
        "@keyframes flick{0%,100%{transform:rotate(0)}35%{transform:rotate(-10deg)}60%{transform:rotate(3deg)}}"
        "@keyframes flapl{0%,70%,100%{transform:rotate(0)}22%{transform:rotate(30deg)}36%{transform:rotate(8deg)}48%{transform:rotate(26deg)}}"
        "@keyframes flapr{0%,70%,100%{transform:rotate(0)}22%{transform:rotate(-30deg)}36%{transform:rotate(-8deg)}48%{transform:rotate(-26deg)}}"
        "@keyframes pop{0%,100%{transform:scale(1)}30%{transform:scale(1.15)}45%{transform:scale(.96)}}"
        "@keyframes fade{0%,100%{opacity:.4}35%{opacity:1}}"
    )
    body = bird(eyes="happy") + sparks() + check_badge(188, 34)
    write("states/fitz-success.svg", doc(view, body, "Fitz, success",
                                         "Fitz hops and flaps its wings next to a green check.", css))


# ------------------------------------------------ icons
# Each size is drawn on its own grid. The "-dark" variants swap the brown
# outline for cream so the silhouette holds on dark backgrounds.
I64 = dict(
    body="M32 15 C 45 15, 54 28, 54 40 C 54 51, 45 59, 32 59 C 19 59, 10 51, 10 40 C 10 28, 19 15, 32 15 Z",
    tuft="M29.5 16.5 C 27.5 12.5, 28.8 8.6, 33.2 7.8 C 31.8 10.6, 33 13.4, 35.6 16 Z",
    tail="M23 30 L14 36 C 10 29, 6 22, 4.5 17 Q 3.5 12 7.5 11 Q 11.5 10 13 14 C 15 20, 18.5 26, 23 30 Z",
    cap="M6 37 C 11 30, 17 27.5, 24 28.5 C 27 29, 29.5 31, 32 34 C 34.5 31, 37 29, 40 28.5 C 47 27.5, 53 30, 58 37 L58 5 L6 5 Z",
)
I32 = dict(
    body="M16 7.5 C 22.8 7.5, 27.5 14, 27.5 20 C 27.5 25.8, 22.5 29.5, 16 29.5 C 9.5 29.5, 4.5 25.8, 4.5 20 C 4.5 14, 9.2 7.5, 16 7.5 Z",
    tuft="M14.8 8.4 C 13.8 6.4, 14.4 4.4, 16.6 4 C 16 5.4, 16.6 6.8, 17.8 8 Z",
    tail="M11.5 14.5 L7.2 18 C 5.2 14.6, 3.4 11.2, 2.6 8.6 Q 2.1 6 4.1 5.6 Q 6.1 5.2 6.9 7.3 C 7.9 10.2, 9.5 12.6, 11.5 14.5 Z",
    cap="M3 18 C 6 14.5, 9 13, 12 13.6 C 13.6 14, 15 15.2, 16 16.6 C 17 15.2, 18.4 14, 20 13.6 C 23 13, 26 14.5, 29 18 L29 3 L3 3 Z",
)


def icon_64(ink=INK, suffix=""):
    cid = "i64" + suffix
    top = ((9, 44), (32, 51), (55, 44))
    w = f'fill="{WING}" stroke="{ink}" stroke-width="1.5" stroke-linejoin="round"'
    s = (
        f'<defs><clipPath id="{cid}"><path d="{I64["body"]}"/></clipPath></defs>'
        f'<path d="{I64["tail"]}" fill="{TAIL}" stroke="{ink}" stroke-width="2.4" stroke-linejoin="round"/>'
        f'<path d="{I64["tuft"]}" fill="{CAP}" stroke="{ink}" stroke-width="2.2" stroke-linejoin="round"/>'
        f'<path d="{I64["body"]}" fill="{BODY}"/>'
        f'<g clip-path="url(#{cid})"><path d="{I64["cap"]}" fill="{CAP}"/>'
        f'<ellipse cx="32" cy="57" rx="15" ry="8" fill="{BELLY}"/>'
        f'<path d="{qd(top)}" fill="none" stroke="{ink}" stroke-width="5.4"/>'
        f'<path d="{qd(top)}" fill="none" stroke="{TAPE}" stroke-width="3.4"/></g>'
        f'<path d="M38 50.5 L38 56" stroke="{ink}" stroke-width="5.4"/><path d="M38 50 L38 54" stroke="{TAPE}" stroke-width="3.4"/>'
        f'<path d="M38 54 L38 55.6" stroke="{METAL}" stroke-width="3.4"/>'
        f'<path d="{I64["body"]}" fill="none" stroke="{ink}" stroke-width="2.4"/>'
        f'<path d="M14.8 45 C 17.3 47, 17.8 52, 15.8 55 C 13.8 54, 12.3 50.5, 12.6 46.5 Z" {w}/>'
        f'<path d="M49.2 45 C 46.7 47, 46.2 52, 48.2 55 C 50.2 54, 51.7 50.5, 51.4 46.5 Z" {w}/>'
        f'<g fill="{BLUSH}" opacity=".55"><ellipse cx="18" cy="42.5" rx="2.6" ry="1.5"/><ellipse cx="46" cy="42.5" rx="2.6" ry="1.5"/></g>'
        f'<ellipse cx="22" cy="38.5" rx="1.9" ry="2.2" fill="{INK}"/><ellipse cx="42" cy="38.5" rx="1.9" ry="2.2" fill="{INK}"/>'
        f'<circle cx="21.5" cy="37.7" r=".6" fill="{WHITE}"/><circle cx="41.5" cy="37.7" r=".6" fill="{WHITE}"/>'
        f'<path d="M29.6 40.5 L34.4 40.5 L32 43.2 Z" fill="{BEAK}" stroke="{ink}" stroke-width="1" stroke-linejoin="round"/>'
        f'<path d="M29.6 40.5 L32 38 L34.4 40.5 Z" fill="{BEAK_TOP}" stroke="{ink}" stroke-width="1" stroke-linejoin="round"/>'
    )
    write(f"icons/fitz-64{suffix}.svg", doc("0 0 64 64", s, "Fitz icon", "Fitz the tailorbird, 64 px icon."))


def icon_32(ink=INK, suffix=""):
    cid = "i32" + suffix
    s = (
        f'<defs><clipPath id="{cid}"><path d="{I32["body"]}"/></clipPath></defs>'
        f'<path d="{I32["tail"]}" fill="{TAIL}" stroke="{ink}" stroke-width="1.5" stroke-linejoin="round"/>'
        f'<path d="{I32["tuft"]}" fill="{CAP}" stroke="{ink}" stroke-width="1.3" stroke-linejoin="round"/>'
        f'<path d="{I32["body"]}" fill="{BODY}"/>'
        f'<g clip-path="url(#{cid})"><path d="{I32["cap"]}" fill="{CAP}"/>'
        f'<ellipse cx="16" cy="28.5" rx="8" ry="4" fill="{BELLY}"/>'
        f'<path d="M3 22.2 Q16 26.5 29 22.2" fill="none" stroke="{TAPE}" stroke-width="2.4"/></g>'
        f'<path d="M19.2 24.5 L19.2 27.6" stroke="{TAPE}" stroke-width="2"/>'
        f'<path d="{I32["body"]}" fill="none" stroke="{ink}" stroke-width="1.5"/>'
        f'<path d="M7 22.5 Q 8.4 25 7.6 27.4 M25 22.5 Q 23.6 25 24.4 27.4" fill="none" stroke="{ink}" stroke-width="1.2" stroke-linecap="round"/>'
        f'<circle cx="11" cy="19.4" r="1.25" fill="{INK}"/><circle cx="21" cy="19.4" r="1.25" fill="{INK}"/>'
        f'<path d="M14.6 20.6 L17.4 20.6 L16 22.4 Z" fill="{BEAK}"/>'
        f'<path d="M14.6 20.6 L16 19 L17.4 20.6 Z" fill="{BEAK_TOP}"/>'
    )
    write(f"icons/fitz-32{suffix}.svg", doc("0 0 32 32", s, "Fitz icon", "Fitz the tailorbird, 32 px icon."))


def icon_16(ink=INK, suffix=""):
    cid = "i16" + suffix
    # edges sit on half pixels so the 1 px outline lands on whole pixels
    body_e = 'cx="8.5" cy="10.5" rx="5" ry="5"'
    s = (
        f'<defs><clipPath id="{cid}"><ellipse {body_e}/></clipPath></defs>'
        f'<path d="M6.5 7.5 L4.5 10 C 3.4 8.4, 2.2 6, 1.6 4.2 Q 1.2 2.4 2.6 2 Q 4 1.6 4.5 3 C 5.1 4.6, 5.7 6.2, 6.5 7.5 Z" fill="{TAIL}" stroke="{ink}" stroke-width="1" stroke-linejoin="round"/>'
        f'<path d="M7.6 6 C 7 4.6, 7.6 3.2, 9.2 2.9 C 8.8 3.8, 9.2 4.9, 10 5.8 Z" fill="{CAP}" stroke="{ink}" stroke-width=".8" stroke-linejoin="round"/>'
        f'<ellipse {body_e} fill="{BODY}"/>'
        f'<g clip-path="url(#{cid})"><path d="M0 9.8 C 3 8.2, 6 8, 8.5 9.6 C 11 8, 14 8.2, 17 9.8 L17 0 L0 0 Z" fill="{CAP}"/>'
        f'<path d="M0 14 Q 8.5 16 17 14 L17 16 L0 16 Z" fill="{BELLY}"/></g>'
        f'<ellipse {body_e} fill="none" stroke="{ink}" stroke-width="1"/>'
        f'<rect x="5.4" y="10" width="1.3" height="1.6" rx=".4" fill="{INK}"/><rect x="10.3" y="10" width="1.3" height="1.6" rx=".4" fill="{INK}"/>'
        f'<path d="M7.4 11.6 L8.5 10.5 L9.6 11.6 L8.5 12.9 Z" fill="{BEAK}"/>'
    )
    write(f"icons/fitz-16{suffix}.svg", doc("0 0 16 16", s, "Fitz icon", "Fitz the tailorbird, 16 px icon."))


def mono():
    """One-colour line version; uses currentColor so it can be recoloured."""
    cid = "mono-body"
    cc = "currentColor"
    P = POSES["front"]
    top, bot = P["band"]
    m = 'maskUnits="userSpaceOnUse" x="-10" y="-10" width="220" height="220"'
    full = '<rect x="-10" y="-10" width="220" height="220" fill="#fff"/>'
    wings = "".join(f'<path d="{d}" fill="#000"/>' for d in P["wings"])
    s = (
        f'<defs><clipPath id="{cid}"><path d="{BODY_PATH}"/></clipPath>'
        f'<mask id="{cid}-out" {m}>{full}<path d="{BODY_PATH}" fill="#000"/></mask>'
        f'<mask id="{cid}-wing" {m}>{full}{wings}</mask></defs>'
        f'<g fill="none" stroke="{cc}" stroke-width="{SW}" stroke-linecap="round" stroke-linejoin="round">'
        + feet().replace(INK, cc)
        + f'<g mask="url(#{cid}-out)"><g transform="translate(9.3 16.8) scale(.85)"><path d="{TAIL_PATH}" stroke-width="{SW / .85:.2f}"/></g></g>'
        f'<path d="{TUFT}" fill="{cc}" mask="url(#{cid}-out)"/>'
        f'<path d="{BODY_PATH}"/>'
        f'<g clip-path="url(#{cid})"><path d="{P["cap"]}" fill="{cc}" stroke="none"/>'
        f'<g mask="url(#{cid}-wing)" stroke-width="{SW2}"><path d="{qd(top)}"/><path d="{qd(bot)}"/>'
        f'<path d="{tape_ticks(top)}" stroke-width="1.8"/></g></g>'
        + "".join(f'<path d="{d}" stroke-width="{SW2}"/>' for d in P["wings"])
        + "</g>"
        + "".join(f'<ellipse cx="{x}" cy="{y}" rx="5.2" ry="6.2" fill="{cc}"/>' for x, y, _ in P["eyes"])
        + f'<path d="M93.5 124 L100 117.5 L106.5 124 L100 131 Z M93.5 124 L106.5 124" fill="none" stroke="{cc}" stroke-width="2.4" stroke-linejoin="round"/>'
    )
    write("fitz-mono.svg", doc(VIEW, s, "Fitz, one colour", "Fitz the tailorbird as a one-colour line drawing."))
    # 32 px mono icon: outlined body; solid cap, tuft, tail, eyes and beak
    s = (
        f'<defs><clipPath id="m32"><path d="{I32["body"]}"/></clipPath></defs>'
        f'<g fill="{cc}"><path d="{I32["tail"]}"/><path d="{I32["tuft"]}"/>'
        f'<path clip-path="url(#m32)" d="{I32["cap"]}"/>'
        '<circle cx="11" cy="19.4" r="1.3"/><circle cx="21" cy="19.4" r="1.3"/>'
        '<path d="M14.5 20.7 L16 19 L17.5 20.7 L16 22.6 Z"/></g>'
        f'<g fill="none" stroke="{cc}" stroke-linecap="round"><path d="{I32["body"]}" stroke-width="2"/>'
        '<path clip-path="url(#m32)" d="M3 22.6 Q16 27 29 22.6" stroke-width="1.3"/>'
        '<path d="M7 22.5 Q 8.4 25 7.6 27.4 M25 22.5 Q 23.6 25 24.4 27.4" stroke-width="1.2"/></g>'
    )
    write("icons/fitz-mono-32.svg", doc("0 0 32 32", s, "Fitz icon, one colour", "Fitz silhouette, one colour."))


if __name__ == "__main__":
    build_main()
    build_expressions()
    build_states()
    for ink, suffix in ((INK, ""), (BELLY, "-dark")):
        icon_64(ink, suffix)
        icon_32(ink, suffix)
        icon_16(ink, suffix)
    mono()
