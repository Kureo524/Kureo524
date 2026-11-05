"""Generates the profile README in the "Verre d'encre" art direction.

The whole profile is ONE scene (a night sky with glass panels) drawn in global coordinates, then cut into
slices: each slice is an SVG whose viewBox is a window on that scene. The README stacks the slices as
inline images aligned to the top with no whitespace between them, so they join seamlessly while each one can still carry its own link (cards, buttons).
Fonts are embedded as subset WOFF so the slices render the same everywhere.

Usage, from the repository root (requires fontTools); rewrites the block between the profile markers
in README.md:
    python3 assets/gen_profile.py"""
import base64, hashlib, io, os, random
from fontTools.ttLib import TTFont
from fontTools import subset

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS_DIR, OUT = os.path.join(HERE, "fonts"), os.path.join(HERE, "profile")

# ---------------- Design tokens ----------------
BG = "#0c0c12"
TEXT, TEXT2, TEXT3 = "#e8eefa", "#a3a6b6", "#8a8a9c"
ACCENT, ACCENT_TEXT, LAVENDER, SUCCESS, WARNING = "#8aa8e0", "#a9c4f0", "#a597c0", "#9ebd85", "#e7b52f"
GLASS = "rgba(30,30,40,0.42)"          # light glass: structure
SURFACE = "rgba(22,22,30,0.62)"        # full glass: content
RAISED = "rgba(232,238,250,0.06)"
BORDER = "rgba(232,238,250,0.09)"
BORDER_STRONG = "rgba(232,238,250,0.17)"
RIM = "rgba(232,238,250,0.24)"
ACCENT_TINT = "rgba(138,168,224,0.50)"
STATUS_BG, STATUS_BORDER, STATUS_RIM = "rgba(16,20,32,0.55)", "rgba(138,168,224,0.28)", "rgba(138,168,224,0.45)"

FONT_FILES = {
    "Gothic A1:400": "GothicA1-Regular.ttf",
    "Gothic A1:700": "GothicA1-Bold.ttf",
    "IBM Plex Mono:400": "IBMPlexMono-Regular.ttf",
    "Barlow Condensed:600": "BarlowCondensed-SemiBold.ttf",
}
REG, BOLD, MONO, NUM = FONT_FILES.keys()
_metrics = {}


def font(key):
    if key not in _metrics:
        f = TTFont(os.path.join(FONTS_DIR, FONT_FILES[key]))
        _metrics[key] = (f.getBestCmap(), f["hmtx"].metrics, f["head"].unitsPerEm)
    return _metrics[key]


def width(text, key, size):
    cmap, hmtx, upm = font(key)
    return sum(hmtx[cmap[ord(c)]][0] if ord(c) in cmap else upm * 0.5 for c in text) * size / upm


def wrap(text, key, size, max_w):
    lines, cur = [], ""
    for word in text.split(" "):
        test = (cur + " " + word).strip()
        if width(test, key, size) <= max_w or not cur:
            cur = test
        else:
            lines.append(cur)
            cur = word
    return lines + [cur] if cur else lines


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def font_faces(used):
    css = []
    for key, file in FONT_FILES.items():
        chars = used.get(key)
        if not chars:
            continue
        family, weight = key.split(":")
        opts = subset.Options()
        opts.flavor = "woff"
        opts.layout_features = ["kern", "liga"]
        opts.name_IDs = []
        f = TTFont(os.path.join(FONTS_DIR, file), recalcTimestamp=False)  # same input, same bytes
        sub = subset.Subsetter(opts)
        sub.populate(text="".join(sorted(chars | {" "})))
        sub.subset(f)
        buf = io.BytesIO()
        f.flavor = "woff"
        f.save(buf)
        css.append(f"@font-face{{font-family:'{family}';font-weight:{weight};"
                   f"src:url(data:font/woff;base64,{base64.b64encode(buf.getvalue()).decode()}) format('woff');}}")
    return "".join(css)


# ---------------- Scene ----------------
SKY, PANEL, CONTENT = 0, 1, 2   # paint layers


class Scene:
    """Elements in global coordinates, each with a bounding box so a slice only embeds what it shows."""

    def __init__(self, w):
        self.w, self.h, self.els, self.slices, self.files = w, 0, [], [], {}

    def el(self, box, svg, defs="", text=None, z=CONTENT):
        self.els.append((z, box, svg, defs, text or {}))

    # --- primitives ---
    def t(self, x, y, s, size, key=REG, fill=TEXT, anchor="start"):
        w = width(s, key, size)
        x0 = x - (w if anchor == "end" else w / 2 if anchor == "middle" else 0)
        family, weight = key.split(":")
        self.el((x0, y - size, w, size * 1.4),
                f'<text x="{x:.1f}" y="{y:.1f}" font-family="{family}, sans-serif" font-weight="{weight}" '
                f'font-size="{size}" fill="{fill}" text-anchor="{anchor}">{esc(s)}</text>', text={key: set(s)})
        return w

    def para(self, x, y, text, size, max_w, lh, key=REG, fill=TEXT2):
        lines = wrap(text, key, size, max_w)
        for k, line in enumerate(lines):
            self.t(x, y + k * lh, line, size, key, fill)
        return y + (len(lines) - 1) * lh

    @staticmethod
    def rim_path(x, y, w, h, r, color):
        # Light comes from the top-left: brighter rim on the top and left edges only.
        return (f'<path d="M{x + 0.5},{y + h - r} V{y + r} A{r - 0.5},{r - 0.5} 0 0 1 {x + r},{y + 0.5} H{x + w - r}" '
                f'fill="none" stroke="{color}"/>')

    def glass(self, x, y, w, h, r=22, fill=GLASS, border=BORDER, rim=RIM, z=CONTENT):
        self.el((x, y, w, h), f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}" stroke="{border}"/>'
                + self.rim_path(x, y, w, h, r, rim), z=z)

    def panel(self, y0, y1):
        self.glass(X0, y0, PW, y1 - y0, 22, GLASS, z=PANEL)

    @staticmethod
    def status_h(text, w, size=19, pad=18, lh=None):
        lh = lh or round(size * 1.45)
        n = len(wrap(text, MONO, size, w - 2 * pad))
        return round(2 * pad + size * 0.75 + (n - 1) * lh)

    def status(self, x, y, w, text, size=19, pad=18, lh=None):
        """ORV system window: thin bluish frame, mono text between brackets. Wraps; returns its bottom."""
        lh = lh or round(size * 1.45)
        lines = wrap(text, MONO, size, w - 2 * pad)
        h = self.status_h(text, w, size, pad, lh)
        self.glass(x, y, w, h, 12, STATUS_BG, STATUS_BORDER, STATUS_RIM)
        for k, line in enumerate(lines):
            self.t(x + pad, y + pad + size * 0.75 + k * lh, line, size, MONO, ACCENT_TEXT)
        return y + h

    def badge(self, x, y, label, color, size=18, anchor="start"):
        h = size + 16
        w = width(label, BOLD, size) + 42
        if anchor == "end":
            x -= w
        self.el((x, y, w, h), f'<rect x="{x:.1f}" y="{y}" width="{w:.1f}" height="{h}" rx="{h / 2 - 3}" fill="{RAISED}" stroke="{BORDER}"/>'
                f'<circle cx="{x + 17:.1f}" cy="{y + h / 2}" r="4" fill="{color}"/>')
        self.t(x + 29, y + h / 2 + size * 0.36, label, size, BOLD, TEXT2)
        return w

    def button(self, x, y, w, h, label, hint, primary=False):
        fill, border = (ACCENT_TINT, "rgba(255,255,255,0.32)") if primary else (RAISED, BORDER_STRONG)
        self.glass(x, y, w, h, 14, fill, border, RIM)
        self.t(x + w / 2, y + h / 2 - 2, label, 23, BOLD, "#ffffff" if primary else TEXT, anchor="middle")
        self.t(x + w / 2, y + h / 2 + 24, hint, 16, MONO, "rgba(255,255,255,0.8)" if primary else TEXT3, anchor="middle")

    def stat(self, x, y, value, label, col=TEXT):
        self.t(x, y, value, 50, NUM, col)
        self.t(x, y + 30, label, 19, REG, TEXT2)

    # --- sky ---
    def sky(self, lights, seed=7, density=2600):
        w, h = self.w, self.h
        for i, (cx, cy, r, col, op) in enumerate(lights):
            gid = f"light{i}"
            self.el((cx - r, cy - r, 2 * r, 2 * r), f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="url(#{gid})"/>',
                    defs=f'<radialGradient id="{gid}" cx="{cx}" cy="{cy}" r="{r}" gradientUnits="userSpaceOnUse">'
                         f'<stop offset="0" stop-color="{col}" stop-opacity="{op}"/>'
                         f'<stop offset="1" stop-color="{col}" stop-opacity="0"/></radialGradient>', z=SKY)
        rnd = random.Random(seed)
        for _ in range(int(w * h / density)):
            x, y, r, o = rnd.uniform(0, w), rnd.uniform(0, h), rnd.uniform(0.3, 1.6), rnd.uniform(0.2, 0.65)
            self.el((x - 2, y - 2, 4, 4), f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.2f}" fill="{TEXT}" opacity="{o:.2f}"/>', z=SKY)
        for _ in range(int(w * h / 20000)):
            # Twinkling stars: slow, discreet, random phases.
            x, y = rnd.uniform(0, w), rnd.uniform(0, h)
            r, dur, begin = rnd.uniform(0.8, 1.6), rnd.uniform(3.5, 7), rnd.uniform(0, 6)
            self.el((x - 2, y - 2, 4, 4), f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.2f}" fill="{TEXT}" opacity="0.12">'
                    f'<animate attributeName="opacity" values="0.12;0.62;0.12" dur="{dur:.1f}s" begin="{begin:.1f}s" '
                    f'repeatCount="indefinite"/></circle>', z=SKY)

    def shooting_star(self, x, y, every=11, begin=2):
        # One shooting star: 140 px trail over 1.3 s, fading in and out, then idle until the next cycle.
        k = 1.3 / every
        self.el((x, y - 20, 440, 160),
                f'<g opacity="0"><animate attributeName="opacity" values="0;1;1;0;0" keyTimes="0;{k * 0.2:.3f};{k * 0.6:.3f};{k:.3f};1" '
                f'dur="{every}s" begin="{begin}s" repeatCount="indefinite"/>'
                f'<g transform="translate({x} {y}) rotate(18)"><rect y="-0.7" width="140" height="1.4" rx="0.7" fill="url(#trail)">'
                f'<animateTransform attributeName="transform" type="translate" values="0 0;260 0;260 0" keyTimes="0;{k:.3f};1" '
                f'dur="{every}s" begin="{begin}s" repeatCount="indefinite"/></rect></g></g>',
                defs='<linearGradient id="trail" x1="0" y1="0" x2="1" y2="0">'
                     '<stop offset="0" stop-color="rgb(201,214,245)" stop-opacity="0"/>'
                     '<stop offset="1" stop-color="rgb(201,214,245)" stop-opacity="0.9"/></linearGradient>', z=SKY)

    # --- slicing ---
    def slice(self, name, x, y, w, h, link=None, alt=""):
        self.slices.append((name, x, y, w, h, link, alt))

    def export(self):
        os.makedirs(OUT, exist_ok=True)
        for f in os.listdir(OUT):
            os.remove(os.path.join(OUT, f))
        W, H = self.w, self.h
        els = sorted(self.els, key=lambda e: e[0])  # stable: keeps insertion order inside a layer
        for name, x, y, w, h, link, alt in self.slices:
            used, defs, body = {}, [], []
            for _, (bx, by, bw, bh), svg, d, text in els:
                if bx < x + w and bx + bw > x and by < y + h and by + bh > y:
                    body.append(svg)
                    if d and d not in defs:
                        defs.append(d)
                    for k, v in text.items():
                        used.setdefault(k, set()).update(v)
            svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="{x} {y} {w} {h}" '
                   f'role="img" aria-label="{esc(alt)}"><title>{esc(alt)}</title><style>{font_faces(used)}</style>'
                   f'<defs><clipPath id="frame"><rect width="{W}" height="{H}" rx="22"/></clipPath>{"".join(defs)}</defs>'
                   f'<g clip-path="url(#frame)"><rect width="{W}" height="{H}" fill="{BG}"/>{"".join(body)}</g>'
                   f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="22" fill="none" stroke="{BORDER}"/></svg>\n')
            # Content hash in the FILE NAME: GitHub serves README images through a redirect that drops the query
            # string, so "?v=" does not bust the browser cache; a new name does.
            base, ext = os.path.splitext(name)
            self.files[name] = f"{base}.{hashlib.sha1(svg.encode()).hexdigest()[:8]}{ext}"
            with open(os.path.join(OUT, self.files[name]), "w", encoding="utf-8") as f:
                f.write(svg)

    def readme_block(self):
        """README HTML: one line of inline images, top-aligned (no baseline gap), no whitespace between them
        (so 50 % + 50 % fits on a row). GitHub pads floated images, hence no align="left"."""
        out = []
        for name, x, y, w, h, link, alt in self.slices:
            pct = f"{100 * w / self.w:.3f}".rstrip("0").rstrip(".") + "%"
            img = f'<img src="assets/profile/{self.files[name]}" alt="{esc(alt)}" width="{pct}" align="top">'
            out.append(f'<a href="{link}">{img}</a>' if link else img)
        return "".join(out)


# ================= The page =================
W, M, PAD = 1200, 32, 40           # canvas width, outer margin, panel padding
X0, PW = M, W - 2 * M              # panel x and width
IX, IW = X0 + PAD, PW - 2 * PAD    # inner content x and width
GAP = 32                           # space between panels
s = Scene(W)

REPO = "https://github.com/Kureo524/CraftingSimulator"
MANHWADLE_REPO = "https://github.com/Kureo524/Manhwadle"
MANHWADLE = "https://kureo524.github.io/Manhwadle/"
CV = "https://raw.githubusercontent.com/Kureo524/Kureo524/main/CV-Monnier-Kilian.pdf"


BTN_GAP = 24


def button_row(prefix, y, items, slice_top, slice_bottom):
    """Three buttons spread over the panel's inner width, BTN_GAP apart. Each button is its own linked slice,
    cut in the middle of the gaps (the outer slices also take the panel margin)."""
    bw = (IW - 2 * BTN_GAP) / 3
    cuts = [0] + [round(IX + i * (bw + BTN_GAP) - BTN_GAP / 2) for i in (1, 2)] + [W]
    for i, (label, hint, primary, link, alt) in enumerate(items):
        s.button(round(IX + i * (bw + BTN_GAP)), y, round(bw), 86, label, hint, primary)
        s.slice(f"{prefix}{i + 1}.svg", cuts[i], slice_top, cuts[i + 1] - cuts[i], slice_bottom - slice_top, link, alt)


def title(top, text, right=None):
    s.t(IX, top + 66, text, 38, BOLD, TEXT)
    if right:
        s.t(W - IX, top + 64, right, 20, REG, TEXT3, anchor="end")


# ---- 1. Hero ----
top = M
s.t(IX, top + 64, "Software & game developer · Bordeaux, France", 21, REG, TEXT3)
s.t(W - IX, top + 64, "[Status: open to internships]", 19, MONO, ACCENT_TEXT, anchor="end")
s.t(IX - 3, top + 150, "Kilian Monnier", 80, BOLD, TEXT)
s.t(IX, top + 200, "C# and C++: tools, gameplay systems and AI-assisted development.", 24, REG, TEXT2)
s.t(IX, top + 234, "Clean architecture, tested code, projects shipped to the end.", 24, REG, TEXT2)
s.status(IX, top + 266, 720, "[Looking for a 6-month internship in 2027.]", 20)
# Lavender constellation, its links slowly breathing (~16 s).
stars = [(850, 152), (940, 118), (1050, 142), (1110, 230), (1020, 300), (900, 286), (978, 212)]
for a, b in [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 0), (1, 6), (6, 4)]:
    (x1, y1), (x2, y2) = stars[a], stars[b]
    s.el((min(x1, x2), min(y1, y2), abs(x2 - x1) + 1, abs(y2 - y1) + 1),
         f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{LAVENDER}" stroke-opacity="0.2" stroke-width="1.3">'
         f'<animate attributeName="stroke-opacity" values="0.2;0.45;0.2" dur="16s" repeatCount="indefinite"/></line>')
for i, (x, y) in enumerate(stars):
    s.el((x - 4, y - 4, 8, 8), f'<circle cx="{x}" cy="{y}" r="{3.6 if i in (1, 3, 6) else 2.5}" fill="{LAVENDER}" opacity="0.9"/>')
s.shooting_star(560, 40)
split = top + 360
bottom = split + 8 + 86 + PAD
s.panel(top, bottom)
s.slice("01-hero.svg", 0, 0, W, split,
        alt="Kilian Monnier — Software and game developer in Bordeaux, looking for a 6-month internship in 2027. C# and C++: "
            "tools, gameplay systems and AI-assisted development; clean architecture and tested code.")
cut = bottom + GAP // 2
button_row("02-hero-btn", split + 8, [
    ("Download my CV", "[CV-Monnier-Kilian.pdf]", True, CV, "Download my CV (PDF)"),
    ("Email me", "kilian.monnier524@gmail.com", False, "mailto:kilian.monnier524@gmail.com", "Email: kilian.monnier524@gmail.com"),
    ("Play my games", "kuko524.itch.io", False, "https://kuko524.itch.io", "My games on itch.io"),
], split, cut)

# ---- 2. Featured project ----
top = bottom + GAP
title(top, "Featured project")
s.badge(W - IX, top + 38, "Playable in the browser · solo project", SUCCESS, size=19, anchor="end")
cy = top + 112
img = base64.b64encode(open(os.path.join(HERE, "manhwadle.webp"), "rb").read()).decode()
iw = 540
ih = round(iw * 556 / 880)
ix = W - IX - iw
s.el((ix, cy, iw, ih),
     f'<image href="data:image/webp;base64,{img}" x="{ix}" y="{cy}" width="{iw}" height="{ih}" '
     f'preserveAspectRatio="xMidYMid slice" clip-path="url(#shot)"/>'
     f'<rect x="{ix}" y="{cy}" width="{iw}" height="{ih}" rx="18" fill="none" stroke="{BORDER}"/>'
     + s.rim_path(ix, cy, iw, ih, 18, RIM),
     defs=f'<clipPath id="shot"><rect x="{ix}" y="{cy}" width="{iw}" height="{ih}" rx="18"/></clipPath>')
lw = ix - IX - 36
s.t(IX - 2, cy + 46, "Manhwadle", 52, BOLD, TEXT)
y = s.para(IX, cy + 90, "A daily character-guessing game across five webtoons.", 23, lw, 31, REG, ACCENT_TEXT)
y = s.para(IX, y + 44, "Each guess is compared to the mystery character in 9 categories, while the constellations "
                   "comment on your run. Desktop app, browser version and installable on mobile.",
       20, lw, 30)
msg = "[Clear condition: identify the mystery incarnation.]"
y = s.status(IX, max(y + 28, cy + ih - s.status_h(msg, lw)), lw, msg)
sy = max(y, cy + ih) + 76
for i, (v, l, c) in enumerate((("107", "characters", TEXT), ("5", "webtoons", TEXT),
                                ("4", "platforms", SUCCESS))):
    s.stat(IX + i * 210, sy, v, l, c)
s.t(W - IX, sy + 30, "Electron · GitHub Actions · Cloudflare", 18, MONO, TEXT3, anchor="end")
split = sy + 66
bottom = split + 8 + 86 + PAD
s.panel(top, bottom)
s.slice("03-featured.svg", 0, cut, W, split - cut, MANHWADLE,
        "Featured project: Manhwadle, a daily character-guessing game across five webtoons. 107 characters, "
        "Windows, macOS, Linux and web; Electron, GitHub Actions, Cloudflare.")
prev, cut = cut, bottom + GAP // 2
button_row("04-featured-btn", split + 8, [
    ("Play in the browser", "kureo524.github.io/Manhwadle", True, MANHWADLE, "Play Manhwadle in the browser"),
    ("Download", "[Windows · macOS · Linux]", False, MANHWADLE_REPO + "/releases/latest", "Download Manhwadle for Windows, macOS or Linux"),
    ("Source code", "Kureo524/Manhwadle", False, MANHWADLE_REPO, "Manhwadle source code"),
], split, cut)

# ---- 3. Projects ----
PROJECTS = [
    dict(title="Forge Studio", genre="Unity editor tools · solo", badge=("Source on GitHub", SUCCESS),
         body="A tool suite so designers build a whole dungeon crawler without code: data editing, validation before saving, dashboards and charts.",
         role="[UI Toolkit · validation · 139 tests]", link="https://github.com/Kureo524/DungeonCrawlerTools"),
    dict(title="Aegis", genre="Horde survival, MOBA controls · solo", badge=("Release v0.4", SUCCESS),
         body="Two champions, 68 items, 43 augments, waves and a boss. State machines, data-driven content, DI and an EventBus.",
         role="[Unity 6.3 · VContainer · 212 tests]", link="https://github.com/Kureo524/Aegis/releases/latest"),
    dict(title="PokyLite", genre="Multiplayer monster-battler · for Steam", badge=("In development · private", ACCENT),
         body="Server-authoritative netcode, a pure C# battle engine covered by unit tests, an ASP.NET Core + PostgreSQL backend.",
         role="[Unity 6 · FishNet · ~450 tests]", link=None),
    dict(title="Taille and Retry", genre="Puzzle-platformer · game jam", badge=("Best Gameplay award", WARNING),
         body="The level itself stretches and compresses. Made in a team for the La Horde Winter Game Jam 2025.",
         role="[Role: deformation mechanic, movement, menus.]", link="https://github.com/theo-bsl/Taille"),
]
top = bottom + GAP
title(top, "Projects", "Tools, games and work in progress")
CP, CG = 30, 16                    # card padding, gap between cards
cw = (IW - CG) / 2
tw = cw - 2 * CP
ch = max(CP + 196 + (len(wrap(p["body"], REG, 20, tw)) - 1) * 30 + 30 + s.status_h(p["role"], tw, 18, lh=26) + CP
         for p in PROJECTS)       # one height for all cards, sized for the longest

# Atelier Nucléaire: full-width card above the grid, with a screenshot, linking to the repository.
mw_top = top + 104
mw_iw = 440
mw_ih = round(mw_iw * 764 / 1280)
mw_ix = IX + IW - CP - mw_iw
mw_tw = mw_ix - IX - 2 * CP
mw_body = "No one-click crafting: grind, smelt, run electrolysis, enrich uranium and drive a fission reactor, all the way to one antimatter pellet."
mw_role = "[Unity 6.3 LTS · UI Toolkit · 106 tests]"
# Tall enough for the screenshot and for the text column (same layout as the project cards).
mw_h = max(mw_ih + 2 * CP, CP + 170 + (len(wrap(mw_body, REG, 20, mw_tw)) - 1) * 30 + 30 + s.status_h(mw_role, mw_tw, 18, lh=26) + CP)
s.slice("05-projects.svg", 0, cut, W, mw_top - CG // 2 - cut, alt="Projects")
s.glass(IX, mw_top, IW, mw_h, 18, SURFACE)
mw_iy = mw_top + (mw_h - mw_ih) // 2
shot = base64.b64encode(open(os.path.join(HERE, "atelier.webp"), "rb").read()).decode()
s.el((mw_ix, mw_iy, mw_iw, mw_ih),
     f'<image href="data:image/webp;base64,{shot}" x="{mw_ix}" y="{mw_iy}" width="{mw_iw}" height="{mw_ih}" '
     f'preserveAspectRatio="xMidYMid slice" clip-path="url(#atshot)"/>'
     f'<rect x="{mw_ix}" y="{mw_iy}" width="{mw_iw}" height="{mw_ih}" rx="12" fill="none" stroke="{BORDER}"/>'
     + s.rim_path(mw_ix, mw_iy, mw_iw, mw_ih, 12, RIM),
     defs=f'<clipPath id="atshot"><rect x="{mw_ix}" y="{mw_iy}" width="{mw_iw}" height="{mw_ih}" rx="12"/></clipPath>')
s.badge(IX + CP, mw_top + CP, "Release · Windows / Linux", SUCCESS)
s.t(IX + CP - 2, mw_top + CP + 90, "Atelier Nucléaire", 40, BOLD, TEXT)
s.t(IX + CP, mw_top + CP + 128, "Crafting on industrial process chains · solo", 21, REG, ACCENT_TEXT)
s.para(IX + CP, mw_top + CP + 170, mw_body, 20, mw_tw, 30)
s.status(IX + CP, mw_top + mw_h - CP - s.status_h(mw_role, mw_tw, 18, lh=26), mw_tw, mw_role, 18, lh=26)
s.slice("05-atelier.svg", 0, mw_top - CG // 2, W, mw_h + CG, REPO,
        "Atelier Nucléaire — Crafting demo on industrial process chains · solo project. Release for Windows and Linux, 106 tests.")
cards_top = mw_top + mw_h + CG
for r in range(2):
    ry = cards_top + r * (ch + CG)
    for c in range(2):
        p = PROJECTS[r * 2 + c]
        x = IX + c * (cw + CG)
        s.glass(x, ry, cw, ch, 18, SURFACE)
        s.badge(x + CP, ry + CP, *p["badge"])
        s.t(x + CP - 2, ry + CP + 90, p["title"], 40, BOLD, TEXT)
        s.t(x + CP, ry + CP + 128, p["genre"], 21, REG, ACCENT_TEXT)
        s.para(x + CP, ry + CP + 170, p["body"], 20, tw, 30)
        s.status(x + CP, ry + ch - CP - s.status_h(p["role"], tw, 18, lh=26), tw, p["role"], 18, lh=26)
        s.slice(f"06-card{r * 2 + c + 1}.svg", c * W // 2, ry - CG // 2, W // 2, ch + CG, p["link"],
                f'{p["title"]} — {p["genre"]}. {p["badge"][0]}.')
cut = cards_top + 2 * ch + CG + CG // 2
end = s.status(IX, cut + 10, IW, "[Also: Escave (team of 8) and Punk Pulse, playable on itch.io. In development: Tower of the Apocalypse.]")
bottom = end + PAD
s.panel(top, bottom)

# ---- 4. Toolbox + footer ----
top = bottom + GAP
title(top, "Toolbox")
cols = [
    ("Languages", [("C#", ACCENT), ("C++", ACCENT), ("JavaScript", LAVENDER)]),
    ("Engines, tools", [("Unity 6 · URP", ACCENT), ("UI Toolkit", ACCENT), ("Unreal Engine", LAVENDER), ("Electron", LAVENDER)]),
    ("Backend, delivery", [("ASP.NET Core", LAVENDER), ("PostgreSQL", LAVENDER), ("FishNet", SUCCESS), ("GitHub Actions", SUCCESS)]),
    ("Practices", [("Unit testing", SUCCESS), ("Data-driven design", ACCENT), ("DI · EventBus", LAVENDER), ("AI-assisted dev", SUCCESS)]),
]
colw = IW / 4
for i, (name, items) in enumerate(cols):
    x = IX + i * colw
    s.t(x, top + 126, name, 22, BOLD, TEXT2)
    for k, (label, col) in enumerate(items):
        s.badge(x, top + 148 + k * 50, label, col, 19)
    if i:
        s.el((x - 20, top + 100, 1, 240), f'<line x1="{x - 20}" y1="{top + 100}" x2="{x - 20}" y2="{top + 340}" stroke="{BORDER}"/>')
bottom = top + 148 + 3 * 50 + 35 + PAD
s.panel(top, bottom)
s.t(W / 2, bottom + 66, "[Thanks for reading this far. Your visit has been recorded in the constellation.]", 19, MONO,
    ACCENT_TEXT, anchor="middle")
s.h = bottom + 116
s.slice("07-end.svg", 0, cut, W, s.h - cut,
        alt="Also: Escave and Punk Pulse on itch.io; Tower of the Apocalypse in development. Toolbox: C#, C++, JavaScript, "
            "Unity 6 with URP and UI Toolkit, Unreal Engine, Electron, ASP.NET Core, PostgreSQL, FishNet, GitHub Actions; "
            "unit testing, data-driven design, DI and EventBus, AI-assisted development.")

H = s.h
s.sky([(150, 130, 560, ACCENT, 0.31), (1060, 90, 460, LAVENDER, 0.25), (700, 900, 560, SUCCESS, 0.12),
       (120, 1500, 560, LAVENDER, 0.16), (1100, 2050, 560, ACCENT, 0.2), (600, H, 520, SUCCESS, 0.19)], seed=3)
s.export()

readme = os.path.join(HERE, "..", "README.md")
src = open(readme, encoding="utf-8").read()
a, b = "<!-- profile:start -->", "<!-- profile:end -->"
open(readme, "w", encoding="utf-8").write(src[:src.index(a) + len(a)] + "\n" + s.readme_block() + "\n" + src[src.index(b):])
print(f"{len(s.slices)} slices, canvas {W}x{H}, {sum(os.path.getsize(os.path.join(OUT, f)) for f in os.listdir(OUT)) // 1024} KB")
