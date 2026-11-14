#!/usr/bin/env python3
"""Generate the animated SVGs used by README.md.

Palette and fonts mirror https://josh.codeffio.com. Each SVG embeds a
subset of the fonts it uses (GitHub renders SVGs as <img>, which cannot
load web fonts), and comes in a light and a dark variant for <picture>.

    python3 -m venv .venv && .venv/bin/pip install fonttools brotli
    .venv/bin/python scripts/build_assets.py
"""
from __future__ import annotations

import base64
import io
import math
import pathlib
import random
import urllib.request
from html import escape

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "assets"
CACHE = ROOT / "scripts" / ".fonts"

FONT_SRC = {
    "bricolage": "https://github.com/google/fonts/raw/main/ofl/bricolagegrotesque/BricolageGrotesque%5Bopsz,wdth,wght%5D.ttf",
    "instrument": "https://github.com/google/fonts/raw/main/ofl/instrumentsans/InstrumentSans%5Bwdth,wght%5D.ttf",
    "jetbrains": "https://github.com/google/fonts/raw/main/ofl/jetbrainsmono/JetBrainsMono%5Bwght%5D.ttf",
}
# family alias -> (source, axis location)
FACES = {
    "D": ("bricolage", {"wght": 700, "opsz": 72, "wdth": 100}),   # display
    "S": ("instrument", {"wght": 400, "wdth": 100}),              # sans
    "SB": ("instrument", {"wght": 600, "wdth": 100}),             # sans semibold
    "M": ("jetbrains", {"wght": 500}),                            # mono
}

THEMES = {
    "light": dict(paper="#fbf6ee", paper2="#f3eadc", paper3="#eadfcd", ink="#1c1917",
                  soft="#57534e", line="#e2d5c1", accent="#e8590c", accent2="#c2410c",
                  teal="#0f5257", sun="#f5b841", on_accent="#ffffff"),
    "dark": dict(paper="#161210", paper2="#211b17", paper3="#2c241f", ink="#f5ede0",
                 soft="#b8ac9c", line="#3a302a", accent="#ff7a2f", accent2="#ff7a2f",
                 teal="#3ba7a0", sun="#f5b841", on_accent="#161210"),
}


# ---------------------------------------------------------------- fonts
_static: dict[str, TTFont] = {}


def face(alias: str) -> TTFont:
    if alias not in _static:
        src, loc = FACES[alias]
        CACHE.mkdir(parents=True, exist_ok=True)
        path = CACHE / f"{src}.ttf"
        if not path.exists():
            urllib.request.urlretrieve(FONT_SRC[src], path)
        _static[alias] = instancer.instantiateVariableFont(TTFont(path), loc)
    return _static[alias]


def width(alias: str, text: str, size: float, tracking: float = 0) -> float:
    f = face(alias)
    cmap, hmtx, upm = f.getBestCmap(), f["hmtx"], f["head"].unitsPerEm
    total = sum(hmtx[cmap.get(ord(c), ".notdef")][0] for c in text)
    return total * size / upm + tracking * max(len(text) - 1, 0)


def font_css(alias: str, chars: set[str]) -> str:
    f = face(alias)
    buf = io.BytesIO()
    f.save(buf)
    buf.seek(0)
    sub = TTFont(buf)
    opts = subset.Options()
    opts.flavor = "woff2"
    opts.layout_features = ["kern", "liga"]
    opts.name_IDs = []
    s = subset.Subsetter(opts)
    s.populate(text="".join(sorted(chars)) + " ")
    s.subset(sub)
    out = io.BytesIO()
    sub.flavor = "woff2"
    sub.save(out)
    b64 = base64.b64encode(out.getvalue()).decode()
    return f"@font-face{{font-family:{alias};src:url(data:font/woff2;base64,{b64}) format('woff2')}}"


# ---------------------------------------------------------------- svg builder
class SVG:
    def __init__(self, w: int, h: int, title: str, t: dict):
        self.w, self.h, self.title, self.t = w, h, title, t
        self.parts: list[str] = []
        self.css: list[str] = []
        self.chars: dict[str, set[str]] = {}

    def add(self, s: str) -> None:
        self.parts.append(s)

    def text(self, x, y, s, f, size, fill, *, track=0, anchor="start", cls="", extra=""):
        self.chars.setdefault(f, set()).update(s)
        c = f' class="{cls}"' if cls else ""
        ls = f' letter-spacing="{track}"' if track else ""
        self.add(f'<text x="{x:.1f}" y="{y:.1f}" font-family="{f}" font-size="{size}" '
                 f'fill="{fill}" text-anchor="{anchor}"{ls}{c}{extra}>{escape(s)}</text>')

    def render(self) -> str:
        fonts = "".join(font_css(a, ch) for a, ch in self.chars.items())
        base = ("svg{shape-rendering:geometricPrecision}"
                ".up{animation:up .9s cubic-bezier(.2,.8,.2,1) both}"
                ".fade{animation:fade 1.2s ease both}"
                "@keyframes up{from{opacity:0;transform:translateY(24px)}}"
                "@keyframes fade{from{opacity:0}}"
                "@keyframes spin{to{transform:rotate(360deg)}}"
                "@keyframes ping{0%{transform:scale(1);opacity:.7}80%,100%{transform:scale(3);opacity:0}}"
                "@keyframes draw{from{stroke-dashoffset:var(--len)}}"
                "@keyframes float{50%{transform:translateY(-8px)}}"
                "@media (prefers-reduced-motion:reduce){*{animation:none!important}}")
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" '
                f'viewBox="0 0 {self.w} {self.h}" role="img" aria-label="{escape(self.title)}">'
                f'<title>{escape(self.title)}</title>'
                f'<style>{fonts}{base}{"".join(self.css)}</style>'
                + "".join(self.parts) + "</svg>")


def frame(s: SVG, fill_key="paper", r=28):
    t = s.t
    s.add(f'<rect x="1" y="1" width="{s.w-2}" height="{s.h-2}" rx="{r}" '
          f'fill="{t[fill_key]}" stroke="{t["line"]}" stroke-width="2"/>')


def dots(s: SVG, opacity=0.55):
    t = s.t
    s.add(f'<defs><pattern id="dots" width="22" height="22" patternUnits="userSpaceOnUse">'
          f'<circle cx="2" cy="2" r="1.2" fill="{t["line"]}"/></pattern>'
          f'<clipPath id="frame"><rect x="2" y="2" width="{s.w-4}" height="{s.h-4}" rx="27"/></clipPath></defs>'
          f'<rect x="2" y="2" width="{s.w-4}" height="{s.h-4}" rx="27" fill="url(#dots)" opacity="{opacity}"/>')


def star(cx, cy, r, fill, cls=""):
    pts = []
    for i in range(16):
        a = math.pi * i / 8
        rr = r if i % 2 == 0 else r * 0.42
        pts.append(f"{cx + rr*math.sin(a):.2f},{cy - rr*math.cos(a):.2f}")
    c = f' class="{cls}"' if cls else ""
    return f'<polygon points="{" ".join(pts)}" fill="{fill}"{c}/>'


# ---------------------------------------------------------------- pieces
def hero(t) -> SVG:
    s = SVG(1000, 520, "Joshua Karlo Claudio — I build & lead web products.", t)
    frame(s)
    dots(s)
    s.css.append(".orbit{transform-origin:830px 170px;animation:spin 40s linear infinite}"
                 ".orbit2{transform-origin:830px 170px;animation:spin 18s linear infinite reverse}"
                 ".sun{transform-origin:830px 170px;animation:fade 1.6s ease both, float 6s ease-in-out 1.6s infinite}"
                 ".ping{transform-origin:center;transform-box:fill-box;animation:ping 2s cubic-bezier(0,0,.2,1) infinite}"
                 ".squig{stroke-dasharray:var(--len);--len:260;animation:draw 1.2s cubic-bezier(.6,0,.2,1) 1.1s both}"
                 + "".join(f".d{i}{{animation-delay:{i*0.12:.2f}s}}" for i in range(12)))
    # sun + orbits
    s.add(f'<g clip-path="url(#frame)">'
          f'<circle class="sun" cx="830" cy="170" r="86" fill="{t["sun"]}"/>'
          f'<g class="orbit"><circle cx="830" cy="170" r="128" fill="none" stroke="{t["accent"]}" '
          f'stroke-width="2" stroke-dasharray="2 12" stroke-linecap="round"/>'
          f'<circle cx="958" cy="170" r="9" fill="{t["accent"]}"/></g>'
          f'<g class="orbit2"><circle cx="830" cy="170" r="176" fill="none" stroke="{t["line"]}" stroke-width="1.5"/>'
          f'<circle cx="830" cy="-6" r="6" fill="{t["teal"]}"/></g>'
          f'{star(830, 170, 30, t["paper"], "")}'
          f'</g>')
    # logo + name
    s.add(f'<g class="up d0"><rect x="56" y="48" width="44" height="44" rx="12" fill="{t["accent"]}"/>')
    s.text(78, 77, "jk", "D", 22, t["on_accent"], anchor="middle")
    s.text(116, 76, "JOSHUA KARLO CLAUDIO", "M", 14, t["ink"], track=2.4)
    s.add("</g>")
    # badge
    label = "Open to remote full-time roles"
    bw = width("SB", label, 15) + 58
    s.add(f'<g class="up d1"><rect x="56" y="118" width="{bw:.0f}" height="36" rx="18" '
          f'fill="{t["paper2"]}" stroke="{t["line"]}" stroke-width="1.5"/>'
          f'<circle class="ping" cx="80" cy="136" r="5" fill="{t["teal"]}"/>'
          f'<circle cx="80" cy="136" r="5" fill="{t["teal"]}"/>')
    s.text(96, 141.5, label, "SB", 15, t["ink"])
    s.add("</g>")
    # headline
    size = 84
    l1a = "I build & "
    s.add('<g class="up d2">')
    s.text(52, 262, "I build & lead", "D", size, t["ink"], track=-2.5)
    s.add("</g>")
    x0 = 52 + width("D", l1a, size, -2.5) + 2
    x1 = 52 + width("D", "I build & lead", size, -2.5)
    s.add(f'<path class="squig" d="M{x0:.0f} 284 q {(x1-x0)/8:.1f} -12 {(x1-x0)/4:.1f} 0 t {(x1-x0)/4:.1f} 0 '
          f't {(x1-x0)/4:.1f} 0 t {(x1-x0)/4:.1f} 0" fill="none" stroke="{t["accent"]}" '
          f'stroke-width="6" stroke-linecap="round"/>')
    s.add('<g class="up d3">')
    w_wp = width("D", "web products", size, -2.5)
    s.text(52, 352, "web products", "D", size, t["ink"], track=-2.5)
    s.add(f'<circle cx="{52 + w_wp + 16:.0f}" cy="340" r="11" fill="{t["accent"]}"/></g>')
    # sub
    s.add('<g class="up d4">')
    s.text(56, 398, "Full-stack developer · 9 years in PHP & JavaScript · Philippines, remote",
           "S", 19, t["soft"])
    s.add("</g>")
    # stats
    s.add(f'<line x1="56" y1="428" x2="944" y2="428" stroke="{t["line"]}" stroke-width="1.5" class="fade d5"/>')
    stats = [("9+", "YEARS IN PHP & JS"), ("5", "TEAMS SHIPPED WITH"),
             ("2", "PRODUCTS BUILT SOLO"), ("1", "RAG FEATURE IN PROD")]
    widths = [width("D", n, 36) + 12 + width("M", lab, 11.5, 1.2) for n, lab in stats]
    gap = (888 - sum(widths)) / (len(stats) - 1)
    x = 56.0
    for i, (n, lab) in enumerate(stats):
        s.add(f'<g class="up d{6+i}">')
        s.text(x, 474, n, "D", 36, t["accent"] if i == 0 else t["ink"])
        s.text(x + width("D", n, 36) + 12, 470, lab, "M", 11.5, t["soft"], track=1.2)
        s.add("</g>")
        x += widths[i] + gap
    return s


SKILLS = ["Laravel", "PHP", "Vue", "Nuxt", "React", "TypeScript", "Node.js", "Flutter",
          "Tailwind CSS", "PostgreSQL", "MySQL", "Typesense", "AWS", "Laravel Vapor", "Pest", "RAG / AI"]


def marquee(t) -> SVG:
    s = SVG(1000, 72, "Laravel, PHP, Vue, Nuxt, React, TypeScript, Node.js, Flutter and more", t)
    s.add(f'<defs><clipPath id="m"><rect x="1" y="1" width="998" height="70" rx="20"/></clipPath>'
          f'<linearGradient id="fadeL" x1="0" x2="1"><stop offset="0" stop-color="{t["paper2"]}"/>'
          f'<stop offset="1" stop-color="{t["paper2"]}" stop-opacity="0"/></linearGradient>'
          f'<linearGradient id="fadeR" x1="1" x2="0"><stop offset="0" stop-color="{t["paper2"]}"/>'
          f'<stop offset="1" stop-color="{t["paper2"]}" stop-opacity="0"/></linearGradient></defs>')
    s.add(f'<rect x="1" y="1" width="998" height="70" rx="20" fill="{t["paper2"]}" stroke="{t["line"]}" stroke-width="2"/>')
    size, gap = 26, 26
    x, items = 0.0, []
    for i, sk in enumerate(SKILLS):
        items.append(("t", x, sk))
        x += width("D", sk, size, -0.5) + gap
        items.append(("s", x + 9, i))
        x += 18 + gap
    period = x
    s.css.append(f".track{{animation:slide {period/45:.1f}s linear infinite}}"
                 f"@keyframes slide{{to{{transform:translateX(-{period:.1f}px)}}}}"
                 ".spin{transform-box:fill-box;transform-origin:center;animation:spin 6s linear infinite}")
    s.add('<g clip-path="url(#m)"><g class="track">')
    for rep in range(3):
        off = rep * period + 24
        for kind, ix, v in items:
            if kind == "t":
                s.text(ix + off, 45, v, "D", size, t["ink"], track=-0.5)
            else:
                col = [t["accent"], t["teal"], t["sun"]][v % 3]
                s.add(star(ix + off, 36, 10, col, "spin"))
    s.add('</g></g>'
          f'<rect x="2" y="2" width="70" height="68" rx="19" fill="url(#fadeL)"/>'
          f'<rect x="928" y="2" width="70" height="68" rx="19" fill="url(#fadeR)"/>')
    return s


def section(t, num, label, heading) -> SVG:
    s = SVG(1000, 120, f"{num} / {label} — {heading}", t)
    size = 44
    while width("D", heading, size, -1) > 940:
        size -= 1
    s.css.append(".rule{stroke-dasharray:var(--len);--len:1000;animation:draw 1.4s cubic-bezier(.6,0,.2,1) .2s both}")
    s.add('<g class="up">')
    s.text(4, 30, f"{num} / {label.upper()}", "M", 14, t["accent"], track=2.4)
    s.add("</g>")
    lx = 4 + width("M", f"{num} / {label.upper()}", 14, 2.4) + 18
    s.add(f'<line class="rule" x1="{lx:.0f}" y1="25" x2="996" y2="25" stroke="{t["line"]}" stroke-width="1.5"/>')
    s.add('<g class="up" style="animation-delay:.15s">')
    s.text(0, 92, heading, "D", size, t["ink"], track=-1)
    s.add("</g>")
    return s


PROJECTS = [
    dict(slug="source", name="Multiplai Source", meta="GOTEAM · 2023–26 · IN PRODUCTION",
         desc="Knowledge platform with AI writing & RAG search.",
         stack=["Laravel", "Nuxt 4", "Typesense", "Vapor"], url="app.thesource.wiki"),
    dict(slug="pulse", name="Pulse Events", meta="FREELANCE · 2026 · LIVE",
         desc="Ticketing, vouchers & QR check-in for events.",
         stack=["Laravel", "Filament", "HitPay"], url="pulseevents.ph"),
    dict(slug="daloy", name="Daloy", meta="SOLO · 2026 · PWA / ANDROID / WINDOWS",
         desc="Free worship team app for Filipino churches.",
         stack=["Laravel 13", "React Router", "Flutter", "Reverb"], url="daloy.pro"),
    dict(slug="galaw", name="Galaw", meta="SOLO · 2026 · EARLY PREVIEW",
         desc="Real-time docs, work items & whiteboards.",
         stack=["Laravel 13", "React Router", "Yjs", "Tiptap"], url="galaw.codeffio.com"),
]


def cover(s: SVG, slug: str):
    t = s.t
    W, H = 490, 180
    if slug == "source":
        s.css.append(".hl{animation:hl 4s ease-in-out infinite}"
                     "@keyframes hl{0%,100%{opacity:0}20%,60%{opacity:1}}"
                     ".caret{animation:blink 1s steps(1) infinite}@keyframes blink{50%{opacity:0}}"
                     )
        s.add(f'<rect x="70" y="34" width="210" height="150" rx="12" fill="{t["paper"]}" stroke="{t["line"]}" stroke-width="1.5"/>')
        for i, w in enumerate([150, 170, 120, 160, 100]):
            y = 58 + i * 22
            s.add(f'<rect class="hl" style="animation-delay:{i*0.5:.1f}s" x="88" y="{y-6}" width="{w+8}" height="16" rx="4" fill="{t["sun"]}" opacity="0"/>')
            s.add(f'<rect x="92" y="{y}" width="{w}" height="5" rx="2.5" fill="{t["soft"]}" opacity=".55"/>')
        s.add(f'<rect x="250" y="54" width="200" height="40" rx="20" fill="{t["paper"]}" stroke="{t["accent"]}" stroke-width="2"/>'
              f'<circle cx="274" cy="74" r="7" fill="none" stroke="{t["accent"]}" stroke-width="2.5"/>'
              f'<line x1="279" y1="79" x2="284" y2="84" stroke="{t["accent"]}" stroke-width="2.5" stroke-linecap="round"/>')
        s.text(294, 79, "ask your workspace", "M", 12, t["ink"])
        s.add(f'<rect x="294" y="62" width="150" height="24" fill="{t["paper"]}" style="transform-origin:294px 0;animation:wipe 4s steps(18) infinite"/>'
              f'<rect class="caret" x="438" y="64" width="2" height="20" fill="{t["accent"]}"/>')
        s.css.append("@keyframes wipe{0%{transform:scaleX(1)}50%,100%{transform:scaleX(0)}}")
        s.add(f'<g style="animation:float 5s ease-in-out infinite">{star(400, 140, 18, t["accent"])}{star(436, 118, 9, t["teal"])}</g>')
    elif slug == "pulse":
        s.css.append(".scan{animation:scan 2.6s ease-in-out infinite alternate}"
                     "@keyframes scan{from{transform:translateY(0)}to{transform:translateY(96px)}}"
                     ".qr{animation:fade 2s ease both}")
        s.add(f'<path d="M90 50 h300 v28 a14 14 0 0 0 0 28 v28 h-300 v-28 a14 14 0 0 0 0 -28 z" fill="{t["paper"]}" stroke="{t["line"]}" stroke-width="1.5"/>'
              f'<line x1="300" y1="56" x2="300" y2="128" stroke="{t["line"]}" stroke-width="2" stroke-dasharray="4 6"/>')
        s.text(116, 82, "PULSE · LIVE", "M", 11, t["accent"], track=1.5)
        s.add(f'<rect x="116" y="94" width="140" height="8" rx="4" fill="{t["ink"]}" opacity=".8"/>'
              f'<rect x="116" y="110" width="90" height="6" rx="3" fill="{t["soft"]}" opacity=".5"/>')
        rnd = random.Random(7)
        s.add('<g class="qr">')
        for gx in range(8):
            for gy in range(8):
                corner = (gx < 2 and gy < 2) or (gx > 5 and gy < 2) or (gx < 2 and gy > 5)
                if corner or rnd.random() < 0.45:
                    s.add(f'<rect x="{318+gx*7}" y="{64+gy*7}" width="6" height="6" rx="1" fill="{t["ink"]}"/>')
        s.add('</g>')
        s.add(f'<rect class="scan" x="312" y="60" width="68" height="3" rx="1.5" fill="{t["teal"]}"/>')
        s.add(f'<g style="animation:float 4s ease-in-out infinite"><circle cx="430" cy="64" r="22" fill="{t["teal"]}"/>'
              f'<path d="M420 64 l7 7 l13 -14" fill="none" stroke="{t["paper"]}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/></g>')
    elif slug == "daloy":
        s.css.append(".wave{animation:wave 6s linear infinite}.w2{animation-duration:9s}.w3{animation-duration:12s}"
                     "@keyframes wave{to{transform:translateX(-160px)}}")
        def wavepath(y, amp):
            d = f"M-20 {y}"
            for i in range(8):
                d += f" q 40 {-amp if i%2==0 else amp} 80 0"
            return d
        for cls, y, amp, col, sw in [("wave", 80, 22, t["accent"], 5), ("wave w2", 104, 16, t["teal"], 4),
                                    ("wave w3", 126, 12, t["sun"], 4)]:
            s.add(f'<path class="{cls}" d="{wavepath(y, amp)}" fill="none" stroke="{col}" stroke-width="{sw}" stroke-linecap="round"/>')
        # note
        s.add(f'<g style="animation:float 4s ease-in-out infinite"><rect x="372" y="34" width="84" height="84" rx="20" fill="{t["paper"]}" stroke="{t["line"]}" stroke-width="1.5"/>'
              f'<path d="M404 96 V58 l26 -6 v36" fill="none" stroke="{t["ink"]}" stroke-width="4" stroke-linejoin="round"/>'
              f'<ellipse cx="398" cy="96" rx="8" ry="6" fill="{t["ink"]}"/><ellipse cx="424" cy="88" rx="8" ry="6" fill="{t["ink"]}"/></g>')
        s.text(456, 150, "G · D/F# · Em · C", "M", 11, t["soft"], anchor="end")
    elif slug == "galaw":
        s.add(f'<rect x="60" y="40" width="110" height="74" rx="10" fill="{t["sun"]}" opacity=".9" transform="rotate(-4 115 77)"/>'
              f'<rect x="300" y="62" width="120" height="70" rx="10" fill="{t["paper"]}" stroke="{t["line"]}" stroke-width="1.5"/>'
              f'<rect x="316" y="80" width="80" height="6" rx="3" fill="{t["soft"]}" opacity=".6"/>'
              f'<rect x="316" y="96" width="56" height="6" rx="3" fill="{t["soft"]}" opacity=".4"/>'
              f'<rect x="316" y="112" width="32" height="10" rx="5" fill="{t["teal"]}"/>')
        s.add(f'<path d="M170 82 C 230 82, 240 98, 300 98" fill="none" stroke="{t["accent"]}" stroke-width="2.5" '
              f'stroke-dasharray="6 6" style="animation:dash 1.2s linear infinite"/>')
        s.css.append("@keyframes dash{to{stroke-dashoffset:-12}}")
        for i in range(3):
            s.add(f'<rect x="{76}" y="{60+i*14}" width="{70-i*16}" height="6" rx="3" fill="{t["ink"]}" opacity=".55" transform="rotate(-4 115 77)"/>')

        def cursor(col, name, path, dur):
            nw = width("M", name, 10) + 14
            s.chars.setdefault("M", set()).update(name)
            s.add(f'<g><path d="M0 0 L0 18 L5 13 L9 21 L12 20 L8 12 L15 12 Z" fill="{col}" stroke="{t["paper"]}" stroke-width="1.5"/>'
                  f'<rect x="12" y="18" width="{nw:.0f}" height="18" rx="9" fill="{col}"/>'
                  f'<text x="19" y="31" font-family="M" font-size="10" fill="{t["paper"]}">{name}</text>'
                  f'<animateMotion dur="{dur}s" repeatCount="indefinite" path="{path}" '
                  f'calcMode="spline" keyTimes="0;0.5;1" keySplines=".5 0 .5 1;.5 0 .5 1"/></g>')
        cursor(t["accent"], "josh", "M200 130 C 260 40, 380 30, 430 120 C 380 150, 260 160, 200 130", 7)
        cursor(t["teal"], "you", "M440 40 C 360 120, 220 140, 120 130 C 200 60, 340 30, 440 40", 9)
    return W, H


def card(t, p) -> SVG:
    s = SVG(490, 380, f'{p["name"]} — {p["desc"]}', t)
    frame(s, r=24)
    s.add(f'<defs><clipPath id="cv"><path d="M2 26 a24 24 0 0 1 24 -24 h438 a24 24 0 0 1 24 24 v168 h-486 z"/></clipPath></defs>')
    s.add(f'<g clip-path="url(#cv)"><rect x="0" y="0" width="490" height="196" fill="{t["paper2"]}"/>'
          f'<g class="fade">')
    cover(s, p["slug"])
    s.add("</g></g>")
    s.add(f'<line x1="2" y1="196" x2="488" y2="196" stroke="{t["line"]}" stroke-width="1.5"/>')
    s.add('<g class="up" style="animation-delay:.1s">')
    s.text(28, 230, p["meta"], "M", 11, t["accent"], track=1.6)
    s.text(26, 272, p["name"], "D", 32, t["ink"], track=-0.8)
    s.text(28, 302, p["desc"], "S", 15.5, t["soft"])
    s.add("</g>")
    x = 28
    s.add('<g class="up" style="animation-delay:.25s">')
    for chip in p["stack"]:
        cw = width("M", chip, 11) + 20
        s.add(f'<rect x="{x:.0f}" y="324" width="{cw:.0f}" height="26" rx="13" fill="none" stroke="{t["line"]}" stroke-width="1.5"/>')
        s.text(x + cw / 2, 341, chip, "M", 11, t["ink"], anchor="middle")
        x += cw + 8
    s.add("</g>")
    # arrow button
    s.add(f'<g style="animation:float 3.5s ease-in-out infinite"><circle cx="444" cy="262" r="22" fill="{t["accent"]}"/>'
          f'<path d="M436 270 L452 254 M440 254 H452 V266" fill="none" stroke="{t["on_accent"]}" stroke-width="2.6" '
          f'stroke-linecap="round" stroke-linejoin="round"/></g>')
    return s


def cta(t) -> SVG:
    s = SVG(1000, 300, "Let's build something good. Open to remote full-time roles.", t)
    frame(s, "paper2")
    s.css.append(".rise{transform-origin:860px 300px;animation:rise 2s cubic-bezier(.2,.8,.2,1) both}"
                 "@keyframes rise{from{transform:translateY(120px)}}"
                 ".rays{transform-origin:860px 300px;animation:spin 50s linear infinite}")
    s.add(f'<defs><clipPath id="c"><rect x="2" y="2" width="996" height="296" rx="27"/></clipPath></defs><g clip-path="url(#c)">'
          f'<g class="rays">' + "".join(
              f'<line x1="860" y1="300" x2="{860+260*math.cos(math.pi*i/12):.1f}" y2="{300-260*math.sin(math.pi*i/12):.1f}" '
              f'stroke="{t["sun"]}" stroke-width="2" stroke-dasharray="3 9" stroke-linecap="round" opacity=".7"/>'
              for i in range(24)) +
          f'</g><circle class="rise" cx="860" cy="300" r="120" fill="{t["sun"]}"/></g>')
    s.add('<g class="up">')
    s.text(56, 70, "05 / CONTACT", "M", 14, t["accent"], track=2.4)
    s.add('</g><g class="up" style="animation-delay:.12s">')
    s.text(52, 150, "Let's build", "D", 72, t["ink"], track=-2)
    s.add('</g><g class="up" style="animation-delay:.24s">')
    s.text(52, 222, "something good.", "D", 72, t["accent"], track=-2)
    s.add('</g><g class="up" style="animation-delay:.36s">')
    s.text(56, 262, "Open to remote full-time roles  ·  Based in the Philippines", "M", 13, t["soft"], track=0.6)
    s.add("</g>")
    return s


def main():
    OUT.mkdir(exist_ok=True)
    for mode, t in THEMES.items():
        jobs = {
            "hero": hero(t),
            "skills": marquee(t),
            "about": section(t, "01", "About", "Senior engineer, team lead when it counts."),
            "work": section(t, "02", "Work", "Things I've built and shipped."),
            "experience": section(t, "03", "Experience", "Nine years, five teams."),
            "toolbox": section(t, "04", "Toolbox", "What I reach for."),
            "contact": cta(t),
            **{f"project-{p['slug']}": card(t, p) for p in PROJECTS},
        }
        for name, svg in jobs.items():
            path = OUT / f"{name}-{mode}.svg"
            path.write_text(svg.render())
            print(f"{path.relative_to(ROOT)}  {path.stat().st_size/1024:.1f} KB")


if __name__ == "__main__":
    main()
