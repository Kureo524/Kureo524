"""Generates the profile README visuals in the "Verre d'encre" art direction.
Fonts are embedded as subset WOFF so the SVGs render the same everywhere.
Usage, from the repository root (requires fontTools):
    python3 assets/gen_profile.py"""
import base64, io, math, os, random
from fontTools.ttLib import TTFont
from fontTools import subset

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS_DIR, OUT = os.path.join(HERE, "fonts"), HERE

# ---------------- Design tokens ----------------
BG = "#0c0c12"
TEXT, TEXT2, TEXT3 = "#e8eefa", "#a3a6b6", "#8a8a9c"
ACCENT, ACCENT_TEXT, LAVENDER, SUCCESS, WARNING = "#8aa8e0", "#a9c4f0", "#a597c0", "#9ebd85", "#e7b52f"
SURFACE = "rgba(22,22,30,0.62)"
BORDER = "rgba(232,238,250,0.09)"
RIM = "rgba(232,238,250,0.24)"
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
    w = sum(hmtx[cmap[ord(c)]][0] if ord(c) in cmap else upm * 0.5 for c in text)
    return w * size / upm


def wrap(text, key, size, max_w):
    lines, cur = [], ""
    for word in text.split(" "):
        test = (cur + " " + word).strip()
        if width(test, key, size) <= max_w or not cur:
            cur = test
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def font_faces(used):
    """Only the fonts actually used, subset to the characters actually used."""
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
        f = TTFont(os.path.join(FONTS_DIR, file))
        sub = subset.Subsetter(opts)
        sub.populate(text="".join(sorted(chars | {" "})))
        sub.subset(f)
        buf = io.BytesIO()
        f.flavor = "woff"
        f.save(buf)
        data = base64.b64encode(buf.getvalue()).decode()
        css.append(f"@font-face{{font-family:'{family}';font-weight:{weight};"
                   f"src:url(data:font/woff;base64,{data}) format('woff');}}")
    return "".join(css)


# ---------------- Building blocks ----------------
class Svg:
    def __init__(self, w, h, title):
        self.w, self.h, self.title = w, h, title
        self.parts, self.used, self.uid = [], {}, 0

    def add(self, s):
        self.parts.append(s)

    def id(self, prefix):
        self.uid += 1
        return f"{prefix}{self.uid}"

    def t(self, x, y, s, size=14, key=REG, fill=TEXT, anchor="start", opacity=None):
        self.used.setdefault(key, set()).update(s)
        family, weight = key.split(":")
        op = f' opacity="{opacity}"' if opacity is not None else ""
        self.add(f'<text x="{x:.1f}" y="{y:.1f}" font-family="{family}, sans-serif" font-weight="{weight}" '
                 f'font-size="{size}" fill="{fill}" text-anchor="{anchor}"{op}>{esc(s)}</text>')

    def para(self, x, y, text, size, max_w, lh, key=REG, fill=TEXT2):
        lines = wrap(text, key, size, max_w)
        for k, line in enumerate(lines):
            self.t(x, y + k * lh, line, size, key, fill)
        return len(lines)

    def rim(self, x, y, w, h, r, color):
        # Light comes from the top-left: brighter rim on the top and left edges only.
        self.add(f'<path d="M{x + 0.5},{y + h - r} V{y + r} A{r - 0.5},{r - 0.5} 0 0 1 {x + r},{y + 0.5} H{x + w - r}" '
                 f'fill="none" stroke="{color}"/>')

    def glass(self, x, y, w, h, r=18, fill=SURFACE):
        self.add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}" stroke="{BORDER}"/>')
        self.rim(x, y, w, h, r, RIM)

    def status(self, x, y, w, h, text, size=14):
        """ORV-style system window: thin bluish frame, message in mono between brackets."""
        self.add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="{STATUS_BG}" stroke="{STATUS_BORDER}"/>')
        self.rim(x, y, w, h, 12, STATUS_RIM)
        self.t(x + 16, y + h / 2 + size * 0.36, text, size, MONO, ACCENT_TEXT)

    def chip(self, x, y, label, color, size=13, h=28):
        w = width(label, BOLD, size) + 34
        self.add(f'<rect x="{x}" y="{y}" width="{w:.1f}" height="{h}" rx="{h / 2 - 2}" fill="rgba(232,238,250,0.06)" stroke="{BORDER}"/>')
        self.add(f'<circle cx="{x + 14}" cy="{y + h / 2}" r="3" fill="{color}"/>')
        self.t(x + 24, y + h / 2 + size * 0.37, label, size, BOLD, TEXT2)
        return w

    def chips(self, x, y, items, size=13, gap=10):
        for label, col in items:
            x += self.chip(x, y, label, col, size) + gap
        return x

    def stat(self, x, y, value, label, col=TEXT):
        self.t(x, y, value, 40, NUM, col)
        self.t(x, y + 25, label, 15, REG, TEXT2)

    def sky(self, seed=7, density=2600, constellation=True, animate=False, frame_r=22):
        w, h = self.w, self.h
        m = max(w, h)
        clip = self.id("frame")
        self.add('<defs>'
                 f'<radialGradient id="lb" cx="{0.12 * w}" cy="{0.18 * h}" r="{0.42 * m}" gradientUnits="userSpaceOnUse">'
                 f'<stop offset="0" stop-color="{ACCENT}" stop-opacity="0.31"/><stop offset="1" stop-color="{ACCENT}" stop-opacity="0"/></radialGradient>'
                 f'<radialGradient id="ll" cx="{0.88 * w}" cy="{0.12 * h}" r="{0.36 * m}" gradientUnits="userSpaceOnUse">'
                 f'<stop offset="0" stop-color="{LAVENDER}" stop-opacity="0.25"/><stop offset="1" stop-color="{LAVENDER}" stop-opacity="0"/></radialGradient>'
                 f'<radialGradient id="lg" cx="{0.60 * w}" cy="{1.0 * h}" r="{0.42 * m}" gradientUnits="userSpaceOnUse">'
                 f'<stop offset="0" stop-color="{SUCCESS}" stop-opacity="0.19"/><stop offset="1" stop-color="{SUCCESS}" stop-opacity="0"/></radialGradient>'
                 f'<linearGradient id="trail" x1="0" y1="0" x2="1" y2="0">'
                 f'<stop offset="0" stop-color="rgb(201,214,245)" stop-opacity="0"/><stop offset="1" stop-color="rgb(201,214,245)" stop-opacity="0.9"/></linearGradient>'
                 f'<clipPath id="{clip}"><rect width="{w}" height="{h}" rx="{frame_r}"/></clipPath>'
                 '</defs>')
        self.add(f'<g clip-path="url(#{clip})">')
        self.add(f'<rect width="{w}" height="{h}" fill="{BG}"/>')
        for g in ("lb", "ll", "lg"):
            self.add(f'<rect width="{w}" height="{h}" fill="url(#{g})"/>')
        rnd = random.Random(seed)
        bright = []
        for _ in range(int(w * h / density)):
            x, y, r, o = rnd.uniform(0, w), rnd.uniform(0, h), rnd.uniform(0.3, 1.6), rnd.uniform(0.2, 0.65)
            self.add(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.2f}" fill="{TEXT}" opacity="{o:.2f}"/>')
            if r > 1.25:
                bright.append((x, y))
        if constellation:
            bright = bright[:14]
            for i, p1 in enumerate(bright):
                for d, p2 in sorted((math.dist(p1, p), p) for p in bright[i + 1:])[:1]:
                    if d < 0.28 * w:
                        self.add(f'<line x1="{p1[0]:.1f}" y1="{p1[1]:.1f}" x2="{p2[0]:.1f}" y2="{p2[1]:.1f}" '
                                 f'stroke="{TEXT}" stroke-opacity="0.16"/>')
        if animate:
            # Twinkling stars: slow, discreet, random phases.
            for _ in range(40):
                x, y = rnd.uniform(0, w), rnd.uniform(0, h)
                r, dur, begin = rnd.uniform(0.7, 1.5), rnd.uniform(3.5, 7), rnd.uniform(0, 6)
                self.add(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.2f}" fill="{TEXT}" opacity="0.12">'
                         f'<animate attributeName="opacity" values="0.12;0.62;0.12" dur="{dur:.1f}s" begin="{begin:.1f}s" '
                         f'repeatCount="indefinite"/></circle>')
            # One shooting star in the upper third, every 11 s, 1.3 s long.
            self.add(f'<g opacity="0"><animate attributeName="opacity" values="0;1;1;0;0" keyTimes="0;0.03;0.08;0.12;1" '
                     f'dur="11s" begin="2s" repeatCount="indefinite"/>'
                     f'<g transform="rotate(18)"><rect y="-0.6" width="140" height="1.2" rx="0.6" fill="url(#trail)">'
                     f'<animateTransform attributeName="transform" type="translate" values="{w * 0.25:.0f} {-h * 0.1:.0f};{w * 0.25 + 1100 * 0.12:.0f} {-h * 0.1:.0f};{w * 0.25 + 1100 * 0.12:.0f} {-h * 0.1:.0f}" '
                     f'keyTimes="0;0.12;1" dur="11s" begin="2s" repeatCount="indefinite"/></rect></g></g>')
        self.add(f'<rect x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" rx="{frame_r}" fill="none" stroke="{BORDER}"/>')

    def close(self):
        self.add('</g>')

    def save(self, name):
        head = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" viewBox="0 0 {self.w} {self.h}" '
                f'role="img" aria-label="{esc(self.title)}"><title>{esc(self.title)}</title>'
                f'<style>{font_faces(self.used)}</style>')
        with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
            f.write(head + "".join(self.parts) + "</svg>\n")
        print(f"{name}: {os.path.getsize(os.path.join(OUT, name)) // 1024} KB")


# ================= 1. Header =================
def header():
    W, H = 1280, 400
    s = Svg(W, H, "Kilian Monnier — Game developer")
    s.sky(seed=3, animate=True, constellation=False)

    # A small lavender constellation on the right, its links slowly breathing (~16 s).
    stars = [(958, 112), (1060, 74), (1172, 110), (1214, 214), (1110, 262), (996, 238), (1124, 168)]
    links = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 0), (1, 6), (6, 4)]
    s.add('<g>')
    for a, b in links:
        (x1, y1), (x2, y2) = stars[a], stars[b]
        s.add(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{LAVENDER}" stroke-opacity="0.2" stroke-width="1.2">'
              f'<animate attributeName="stroke-opacity" values="0.2;0.45;0.2" dur="16s" repeatCount="indefinite"/></line>')
    for i, (x, y) in enumerate(stars):
        r = 3.4 if i in (1, 3, 6) else 2.4
        s.add(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{LAVENDER}" opacity="0.85"/>')
    s.add('</g>')

    s.glass(48, 52, 820, 296, r=22)
    s.t(84, 102, "Game developer · Bordeaux, France", 16, REG, TEXT3)
    s.t(82, 168, "Kilian Monnier", 64, BOLD, TEXT)
    s.t(84, 208, "C# and C++ with Unity and Unreal Engine. Clean architecture,", 18, REG, TEXT2)
    s.t(84, 234, "gameplay systems and multiplayer infrastructure.", 18, REG, TEXT2)
    s.status(84, 260, 748, 44, "[A new project has been released: Atelier Nucléaire.]", 15)

    # Info strip under the glass, to the right: a system-style status line.
    s.t(W - 52, H - 44, "[Status: open to opportunities]", 16, MONO, ACCENT_TEXT, anchor="end")
    s.close()
    s.save("header.svg")


# ================= 2. Featured project =================
def featured():
    W, H = 1280, 560
    s = Svg(W, H, "Atelier Nucléaire — featured project")
    s.sky(seed=11, density=3600, constellation=False)
    s.glass(32, 32, W - 64, H - 64, r=22)

    # Screenshot on the right, clipped to a radius-18 frame, with a rim like the glass.
    img = base64.b64encode(open(os.path.join(HERE, "atelier.webp"), "rb").read()).decode()
    ix, iy, iw = 600, 64, 616
    ih = round(iw * 764 / 1280)
    s.add(f'<defs><clipPath id="shot"><rect x="{ix}" y="{iy}" width="{iw}" height="{ih}" rx="18"/></clipPath></defs>')
    s.add(f'<image href="data:image/webp;base64,{img}" x="{ix}" y="{iy}" width="{iw}" height="{ih}" '
          f'preserveAspectRatio="xMidYMid slice" clip-path="url(#shot)"/>')
    s.add(f'<rect x="{ix}" y="{iy}" width="{iw}" height="{ih}" rx="18" fill="none" stroke="{BORDER}"/>')
    s.rim(ix, iy, iw, ih, 18, RIM)
    s.t(ix + iw, iy + ih + 32, "Unity 6.3 LTS · URP · UI Toolkit · Windows and Linux", 13, MONO, TEXT3, anchor="end")

    x = 72
    s.t(x, 104, "Latest release · solo project", 16, REG, TEXT3)
    s.t(x - 2, 156, "Atelier Nucléaire", 46, BOLD, TEXT)
    s.t(x, 190, "A crafting demo built on industrial process chains.", 18, REG, ACCENT_TEXT)
    s.para(x, 230, "No one-click crafting: grind, smelt, run electrolysis and sulfur chemistry, enrich uranium "
                   "and drive a fission reactor. Every item asks which machines to build, how to connect them "
                   "and at what rate to run them.", 17, 490, 26)
    s.status(x, 342, 490, 44, "[Final objective: one antimatter pellet.]", 15)
    for i, (v, l, c) in enumerate((("4", "interacting rules", TEXT), ("3", "objectives", TEXT), ("106", "EditMode tests", SUCCESS))):
        s.stat(x + i * 160, 438, v, l, c)
    s.chips(x, 482, (("Data-driven ScriptableObjects", ACCENT), ("Pure C# simulation core", LAVENDER)))
    s.close()
    s.save("featured.svg")


# ================= 3. Project cards =================
PROJECTS = [
    dict(file="card-taille.svg", title="Taille and Retry", genre="Puzzle-platformer · game jam",
         badge=("Best Gameplay award", WARNING),
         body="The level itself stretches and compresses. Built in a team for the La Horde Winter Game Jam.",
         role="[Role: deformation mechanic, movement, menus.]", seed=41),
    dict(file="card-escave.svg", title="Escave", genre="2D precision platformer · team of 8",
         badge=("Published on itch.io", SUCCESS),
         body="Celeste-inspired controls with coyote time and input buffering, a grappling hook, ice axes and a living cave full of traps.",
         role="[Role: wall grab and wall jump, main menu, saves.]", seed=43),
    dict(file="card-punkpulse.svg", title="Punk Pulse", genre="Rhythm action game",
         badge=("Playable on itch.io", SUCCESS),
         body="Collect melodies, fuse them into new ones and play them from the hotbar. The Melody Codex keeps track of every one.",
         role="[Role: melody system, Melody Codex, fusion, hotbar.]", seed=47),
    dict(file="card-pokylite.svg", title="PokyLite", genre="Multiplayer monster-battler · targeting Steam",
         badge=("In development · private", ACCENT),
         body="Server-authoritative netcode, a pure C# battle engine covered by unit tests, and an ASP.NET Core + PostgreSQL backend.",
         role="[Unity 6 · URP · FishNet · ASP.NET Core]", seed=53),
]


def card(p):
    W, H = 640, 350
    s = Svg(W, H, f"{p['title']} — {p['genre']}")
    s.sky(seed=p["seed"], density=3000, constellation=False)
    s.glass(20, 20, W - 40, H - 40, r=18)
    x = 48
    label, col = p["badge"]
    bw = width(label, BOLD, 15) + 38
    s.add(f'<rect x="{x}" y="46" width="{bw:.1f}" height="30" rx="14" fill="rgba(232,238,250,0.06)" stroke="{BORDER}"/>')
    s.add(f'<circle cx="{x + 15}" cy="61" r="3.5" fill="{col}"/>')
    s.t(x + 27, 66.5, label, 15, BOLD, TEXT2)
    s.t(x - 1, 126, p["title"], 40, BOLD, TEXT)
    s.t(x, 160, p["genre"], 19, REG, ACCENT_TEXT)
    s.para(x, 198, p["body"], 19, W - 2 * x, 28)
    s.status(x, H - 44 - 48, W - 2 * x, 48, p["role"], 16)
    s.close()
    s.save(p["file"])


# ================= 4. Toolbox =================
def toolbox():
    W, H = 1280, 310
    s = Svg(W, H, "Toolbox")
    s.sky(seed=61, density=3600, constellation=False)
    s.glass(32, 32, W - 64, H - 64, r=22)
    cols = [
        ("Languages", [("C#", ACCENT), ("C++", ACCENT)]),
        ("Engines", [("Unity 6 · URP", ACCENT), ("Unreal Engine", LAVENDER), ("UI Toolkit", ACCENT)]),
        ("Multiplayer and backend", [("FishNet", SUCCESS), ("ASP.NET Core", LAVENDER), ("PostgreSQL", LAVENDER)]),
        ("Practices", [("Server-authoritative", SUCCESS), ("Data-driven design", ACCENT), ("Unit testing", SUCCESS), ("DI · EventBus", LAVENDER)]),
    ]
    cw = (W - 64 - 2 * 40) / 4
    for i, (title, items) in enumerate(cols):
        x = 72 + i * cw
        s.t(x, 92, title, 19, BOLD, TEXT)
        for k, (label, col) in enumerate(items):
            s.chip(x, 110 + k * 40, label, col, 16, 32)
        if i:
            s.add(f'<line x1="{x - 22}" y1="72" x2="{x - 22}" y2="{H - 72}" stroke="{BORDER}"/>')
    s.close()
    s.save("toolbox.svg")


# ================= 5. Footer =================
def footer():
    W, H = 1280, 120
    s = Svg(W, H, "Thanks for visiting")
    s.sky(seed=71, density=3000, constellation=False, animate=True)
    s.t(W / 2, H / 2 + 6, "[Thanks for reading this far. Your visit has been recorded in the constellation.]", 17, MONO, ACCENT_TEXT, anchor="middle")
    s.close()
    s.save("footer.svg")


header()
featured()
for p in PROJECTS:
    card(p)
toolbox()
footer()
