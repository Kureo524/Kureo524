"""Generates the profile README in the "Verre d'encre" art direction.

The whole profile is ONE scene (a night sky with glass panels) drawn in global coordinates, then cut into
slices: each slice is an SVG whose viewBox is a window on that scene. The README stacks the slices as
inline images aligned to the top with no whitespace between them, so they join seamlessly while each one can still carry its own link (cards, buttons).
Fonts are embedded as subset WOFF so the slices render the same everywhere.

GitHub runs no script in a README, so the project selector is made of pages: projects/<slug>.md shows the
same Projects panel with another project selected, and each button of the list links to its page.

Usage, from the repository root (requires fontTools); rewrites README.md and projects/*.md:
    python3 assets/gen_profile.py"""
import base64, io, os, random
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
        f = TTFont(os.path.join(FONTS_DIR, file))
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
        self.w, self.h, self.els, self.slices = w, 0, [], []

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

    def export(self, out_dir):
        os.makedirs(out_dir, exist_ok=True)
        for f in os.listdir(out_dir):
            os.remove(os.path.join(out_dir, f))
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
            with open(os.path.join(out_dir, name), "w", encoding="utf-8") as f:
                f.write(svg)

    def html(self, src_prefix):
        """README HTML: one line of inline images, top-aligned (no baseline gap), no whitespace between them
        (so 50 % + 50 % fits on a row). GitHub pads floated images, hence no align="left"."""
        out = []
        for name, x, y, w, h, link, alt in self.slices:
            pct = f"{100 * w / self.w:.3f}".rstrip("0").rstrip(".") + "%"
            img = f'<img src="{src_prefix}{name}" alt="{esc(alt)}" width="{pct}" align="top">'
            out.append(f'<a href="{link}">{img}</a>' if link else img)
        return "".join(out)


# ================= Layout =================
W, M, PAD = 1200, 32, 40           # canvas width, outer margin, panel padding
X0, PW = M, W - 2 * M              # panel x and width
IX, IW = X0 + PAD, PW - 2 * PAD    # inner content x and width
GAP = 32                           # space between panels
BRANCH = "main"
SITE = "https://github.com/Kureo524/Kureo524"
PROFILE = "https://github.com/Kureo524"
REPO = "https://github.com/Kureo524/CraftingSimulator"
CV = f"https://raw.githubusercontent.com/Kureo524/Kureo524/{BRANCH}/CV-Monnier-Kilian.pdf"


def project_page(slug):
    return f"{SITE}/blob/{BRANCH}/projects/{slug}.md"


def third(i):
    return round(i * W / 3), round((i + 1) * W / 3) - round(i * W / 3)


def button_row(s, prefix, y, items, slice_top, slice_bottom):
    """Three buttons, one per third of the canvas; each third is its own linked slice."""
    for i, (label, hint, primary, link, alt) in enumerate(items):
        x, w = third(i)
        s.button(x + 52, y, w - 104, 86, label, hint, primary)
        s.slice(f"{prefix}{i + 1}.svg", x, slice_top, w, slice_bottom - slice_top, link, alt)


def title(s, top, text, right=None):
    s.t(IX, top + 66, text, 38, BOLD, TEXT)
    if right:
        s.t(W - IX, top + 64, right, 19, MONO, ACCENT_TEXT, anchor="end")


def finish(s, bottom, lights):
    s.t(W / 2, bottom + 66, "[Thanks for reading this far. Your visit has been recorded in the constellation.]", 19, MONO,
        ACCENT_TEXT, anchor="middle")
    s.h = bottom + 116
    s.sky(lights(s.h), seed=3)


# ---- Hero ----
def hero(s):
    top = M
    s.t(IX, top + 64, "Game developer · Bordeaux, France", 21, REG, TEXT3)
    s.t(W - IX, top + 64, "[Status: open to opportunities]", 19, MONO, ACCENT_TEXT, anchor="end")
    s.t(IX - 3, top + 150, "Kilian Monnier", 80, BOLD, TEXT)
    s.t(IX, top + 200, "C# and C++ with Unity and Unreal Engine.", 24, REG, TEXT2)
    s.t(IX, top + 234, "Clean architecture, gameplay systems and multiplayer infrastructure.", 24, REG, TEXT2)
    s.status(IX, top + 266, 720, "[A new project has been released: Atelier Nucléaire.]", 20)
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
            alt="Kilian Monnier — Game developer in Bordeaux. C# and C++ with Unity and Unreal Engine: clean architecture, "
                "gameplay systems and multiplayer infrastructure.")
    cut = bottom + GAP // 2
    button_row(s, "02-hero-btn", split + 8, [
        ("Download my CV", "[CV-Monnier-Kilian.pdf]", True, CV, "Download my CV (PDF)"),
        ("Email me", "kilian.monnier524@gmail.com", False, "mailto:kilian.monnier524@gmail.com", "Email: kilian.monnier524@gmail.com"),
        ("Play my games", "kuko524.itch.io", False, "https://kuko524.itch.io", "My games on itch.io"),
    ], split, cut)
    return bottom, cut


# ---- Featured project ----
def featured(s, bottom, cut):
    top = bottom + GAP
    title(s, top, "Featured project")
    s.badge(W - IX, top + 38, "Latest release · solo project", SUCCESS, size=19, anchor="end")
    cy = top + 112
    img = base64.b64encode(open(os.path.join(HERE, "atelier.webp"), "rb").read()).decode()
    iw = 540
    ih = round(iw * 764 / 1280)
    ix = W - IX - iw
    s.el((ix, cy, iw, ih),
         f'<image href="data:image/webp;base64,{img}" x="{ix}" y="{cy}" width="{iw}" height="{ih}" '
         f'preserveAspectRatio="xMidYMid slice" clip-path="url(#shot)"/>'
         f'<rect x="{ix}" y="{cy}" width="{iw}" height="{ih}" rx="18" fill="none" stroke="{BORDER}"/>'
         + s.rim_path(ix, cy, iw, ih, 18, RIM),
         defs=f'<clipPath id="shot"><rect x="{ix}" y="{cy}" width="{iw}" height="{ih}" rx="18"/></clipPath>')
    lw = ix - IX - 36
    s.t(IX - 2, cy + 46, "Atelier Nucléaire", 52, BOLD, TEXT)
    y = s.para(IX, cy + 90, "A crafting demo built on industrial process chains.", 23, lw, 31, REG, ACCENT_TEXT)
    y = s.para(IX, y + 44, "No one-click crafting: grind, smelt, run electrolysis, enrich uranium and drive a fission "
                           "reactor. Every item asks which machines to build, how to connect them and how fast to run them.",
               20, lw, 30)
    msg = "[Final objective: one antimatter pellet.]"
    y = s.status(IX, max(y + 28, cy + ih - s.status_h(msg, lw)), lw, msg)
    sy = max(y, cy + ih) + 76
    for i, (v, l, c) in enumerate((("4", "interacting rules", TEXT), ("3", "objectives", TEXT),
                                    ("106", "EditMode tests", SUCCESS))):
        s.stat(IX + i * 210, sy, v, l, c)
    s.t(W - IX, sy + 30, "Unity 6.3 LTS · URP · UI Toolkit", 18, MONO, TEXT3, anchor="end")
    split = sy + 66
    bottom = split + 8 + 86 + PAD
    s.panel(top, bottom)
    s.slice("03-featured.svg", 0, cut, W, split - cut, REPO,
            "Featured project: Atelier Nucléaire, a crafting demo built on industrial process chains. Unity 6.3 LTS, "
            "4 interacting rules, 3 objectives, 106 EditMode tests.")
    cut = bottom + GAP // 2
    button_row(s, "04-featured-btn", split + 8, [
        ("Download the game", "[Windows · Linux]", True, REPO + "/releases/latest", "Download Atelier Nucléaire for Windows or Linux"),
        ("Source code", "Kureo524/CraftingSimulator", False, REPO, "Atelier Nucléaire source code"),
        ("Crafting rules", "[in French]", False, REPO + "/blob/main/Docs/MesRegles.md", "Atelier Nucléaire crafting rules (French)"),
    ], split, cut)
    return bottom, cut


# ---- Projects: detail on the left, project list on the right ----
PROJECTS = [
    dict(slug="taille-and-retry", title="Taille and Retry", short="Puzzle-platformer · jam", dot=LAVENDER,
         genre="Puzzle-platformer · game jam", badge=("Best Gameplay award", LAVENDER),
         desc="A puzzle-platformer where the level itself stretches and compresses: every room is solved by reshaping it. "
              "Built in a team for the La Horde Winter Game Jam 2025, where it won the Best Gameplay award.",
         facts=[("Event", "Winter Jam 2025"), ("Award", "Best Gameplay"), ("Engine", "Unity · C#")],
         role="[Role: deformation mechanic, character movement, menus and UI.]",
         links=[("Source code", "theo-bsl/Taille", "https://github.com/theo-bsl/Taille")]),
    dict(slug="escave", title="Escave", short="Precision platformer", dot=SUCCESS,
         genre="2D precision platformer · team of 8", badge=("Published on itch.io", SUCCESS),
         desc="A Celeste-inspired precision platformer. Fluid controls with coyote time and input buffering, "
              "a grappling hook, ice axes and a living cave full of traps.",
         facts=[("Team", "8 people"), ("Release", "itch.io"), ("Engine", "Unity · C#")],
         role="[Role: wall grab and wall jump, main menu UI, save system.]",
         links=[("Play", "lucasdrpx.itch.io", "https://lucasdrpx.itch.io/escave"),
                ("Source code", "lucasdprx/Escave", "https://github.com/lucasdprx/Escave")]),
    dict(slug="punk-pulse", title="Punk Pulse", short="Rhythm action", dot=SUCCESS,
         genre="Rhythm action game", badge=("Playable on itch.io", SUCCESS),
         desc="Melodies are your weapons. Collect them, fuse them into new ones and play them from the hotbar, "
              "while the Melody Codex records every melody you find.",
         facts=[("Genre", "Rhythm action"), ("Release", "itch.io"), ("Engine", "Unity · C#")],
         role="[Role: melody system and its UI, Melody Codex, fusion, hotbar.]",
         links=[("Play", "lawice2.itch.io", "https://lawice2.itch.io/punk-pulse"),
                ("Source code", "Instance2---2026", "https://github.com/Gabriel-Etienne/Instance2---2026")]),
    dict(slug="pokylite", title="PokyLite", short="Multiplayer battler", dot=ACCENT,
         genre="Multiplayer monster-battler · for Steam", badge=("In development · private", ACCENT),
         desc="A multiplayer monster-battler covering generations 1 to 5. Server-authoritative architecture, "
              "a pure C# battle engine covered by unit tests, persistence through an ASP.NET Core + PostgreSQL API.",
         facts=[("Netcode", "FishNet"), ("Backend", "ASP.NET Core"), ("Engine", "Unity 6 · URP")],
         role="[Private repository · in active development]", links=[]),
    dict(slug="tower-of-the-apocalypse", title="Tower of the Apocalypse", short="Mobile turn-based RPG", dot=ACCENT,
         genre="Turn-based RPG · mobile", badge=("Early development · private", ACCENT),
         desc="A turn-based RPG for mobile, with data-driven combat and a mobile-first design.",
         facts=[("Platform", "Mobile"), ("Combat", "Turn-based"), ("Engine", "Unity 6 · URP")],
         role="[Private repository · early development]", links=[]),
    dict(slug="aegis", title="Aegis", short="2.5D horde survival", dot=ACCENT,
         genre="Horde survival · 2.5D · MOBA-style controls", badge=("Public repository", ACCENT),
         desc="Hold out against hordes in 2.5D with MOBA-style controls. A project built around its architecture: "
              "state machines, data-driven design, dependency injection with VContainer and an EventBus.",
         facts=[("Controls", "MOBA-style"), ("DI", "VContainer"), ("Engine", "Unity 6.3 · C#")],
         role="[Public repository · Kureo524/Aegis]",
         links=[("Source code", "Kureo524/Aegis", "https://github.com/Kureo524/Aegis")]),
]
DEFAULT = "taille-and-retry"

ITEM_H, ITEM_GAP, LIST_PAD = 96, 8, 12
LIST_W = 360
SPLIT_X = W - IX - LIST_W - 8      # boundary between the detail column and the list column
DETAIL_W = SPLIT_X - 8 - IX
DP = 32                            # detail padding


def projects(s, bottom, cut, sel, head_right):
    """head_right: (kind, payload) — ("hint", text) on the profile, ("back", url) on a project page."""
    p = next(q for q in PROJECTS if q["slug"] == sel)
    n = len(PROJECTS)
    top = bottom + GAP
    title(s, top, "Projects")
    body_top = top + 104
    body_h = 2 * LIST_PAD + n * ITEM_H + (n - 1) * ITEM_GAP
    if head_right[0] == "hint":
        s.t(W - IX, top + 64, head_right[1], 19, MONO, ACCENT_TEXT, anchor="end")
        s.slice("05-projects.svg", 0, cut, W, body_top - 8 - cut, alt="Projects")
    else:
        bw, bh = 300, 64
        s.button(W - IX - bw, top + 26, bw, bh, "Back to profile", "[github.com/Kureo524]")
        s.slice("05-projects.svg", 0, cut, SPLIT_X, body_top - 8 - cut, alt="Projects")
        s.slice("05-back.svg", SPLIT_X, cut, W - SPLIT_X, body_top - 8 - cut, head_right[1], "Back to profile")

    # Detail panel (left)
    dx, dy = IX, body_top
    s.glass(dx, dy, DETAIL_W, body_h, 18, SURFACE)
    tx, tw = dx + DP, DETAIL_W - 2 * DP
    idx = PROJECTS.index(p) + 1
    s.badge(tx, dy + DP, *p["badge"], size=18)
    s.t(dx + DETAIL_W - DP, dy + DP + 24, f"[Project file {idx:02d}/{n:02d}]", 17, MONO, TEXT3, anchor="end")
    s.t(tx - 2, dy + DP + 98, p["title"], 46, BOLD, TEXT)
    s.t(tx, dy + DP + 136, p["genre"], 22, REG, ACCENT_TEXT)
    y = s.para(tx, dy + DP + 182, p["desc"], 20, tw, 30)
    # Anchored to the bottom: buttons, then the role window, then the facts above it.
    by, bh = dy + body_h - DP - 72, 72
    sy = by - 24 - s.status_h(p["role"], tw, 18, lh=26)
    fy = sy - 56
    fw = tw / 3
    for i, (label, value) in enumerate(p["facts"]):
        s.t(tx + i * fw, fy, label, 17, REG, TEXT3)
        s.t(tx + i * fw, fy + 30, value, 21, BOLD, TEXT)
    assert fy - 17 > y + 10, f"{p['title']}: description too long for the detail panel"
    s.status(tx, sy, tw, p["role"], 18, lh=26)
    bwid = (tw - 16) / 2
    for i, (label, hint, _url) in enumerate(p["links"]):
        s.button(tx + i * (bwid + 16), by, bwid, bh, label, hint, primary=(i == 0))
    if not p["links"]:
        s.t(tx, by + bh / 2 + 7, "[No public build or source for now.]", 18, MONO, TEXT3)

    # List panel (right)
    lx = SPLIT_X + 8
    s.glass(lx, dy, LIST_W, body_h, 18, SURFACE)
    rows = []
    for i, q in enumerate(PROJECTS):
        iy = dy + LIST_PAD + i * (ITEM_H + ITEM_GAP)
        ix, iw = lx + LIST_PAD, LIST_W - 2 * LIST_PAD
        if q is p:
            s.glass(ix, iy, iw, ITEM_H, 12, "rgba(138,168,224,0.16)", BORDER, RIM)
        s.el((ix + 18, iy + 30, 10, 10), f'<circle cx="{ix + 22}" cy="{iy + 35}" r="4" fill="{q["dot"]}"/>')
        s.t(ix + 38, iy + 42, q["title"], 22, BOLD, ACCENT_TEXT if q is p else TEXT)
        s.t(ix + 38, iy + 72, q["short"], 18, REG, TEXT2 if q is p else TEXT3)
        rows.append(iy)

    # Slices: one row per list item; the detail column is cut into matching strips.
    bounds = [body_top - 8] + [iy - ITEM_GAP // 2 for iy in rows[1:]] + [body_top + body_h + 8]
    main_link = p["links"][0][2] if p["links"] else None
    for i, q in enumerate(PROJECTS):
        r0, r1 = bounds[i], bounds[i + 1]
        if i < n - 1:
            s.slice(f"06-row{i + 1}-detail.svg", 0, r0, SPLIT_X, r1 - r0, main_link, f'{p["title"]}: {p["desc"]}' if i == 0 else p["title"])
        else:
            # Last row holds the detail buttons: one slice per button.
            half = round(tx + bwid + 8)
            links = p["links"] + [None] * (2 - len(p["links"]))
            s.slice(f"06-row{i + 1}-btn1.svg", 0, r0, half, r1 - r0, links[0][2] if links[0] else None,
                    f'{links[0][0]}: {p["title"]}' if links[0] else p["title"])
            s.slice(f"06-row{i + 1}-btn2.svg", half, r0, SPLIT_X - half, r1 - r0, links[1][2] if links[1] else None,
                    f'{links[1][0]}: {p["title"]}' if links[1] else p["title"])
        s.slice(f"06-row{i + 1}-item.svg", SPLIT_X, r0, W - SPLIT_X, r1 - r0, project_page(q["slug"]),
                f'Open the project file: {q["title"]}')
    bottom = body_top + body_h + PAD
    s.panel(top, bottom)
    return bottom, bounds[-1]


# ---- Toolbox ----
def toolbox(s, bottom, cut):
    top = bottom + GAP
    title(s, top, "Toolbox")
    cols = [
        ("Languages", [("C#", ACCENT), ("C++", ACCENT)]),
        ("Engines", [("Unity 6 · URP", ACCENT), ("Unreal Engine", LAVENDER), ("UI Toolkit", ACCENT)]),
        ("Multiplayer, backend", [("FishNet", SUCCESS), ("ASP.NET Core", LAVENDER), ("PostgreSQL", LAVENDER)]),
        ("Practices", [("Server-authoritative", SUCCESS), ("Data-driven design", ACCENT), ("Unit testing", SUCCESS), ("DI · EventBus", LAVENDER)]),
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
    return bottom


def lights(H):
    return [(150, 130, 560, ACCENT, 0.31), (1060, 90, 460, LAVENDER, 0.25), (700, 900, 560, SUCCESS, 0.12),
            (120, 1500, 560, LAVENDER, 0.16), (1100, 2050, 560, ACCENT, 0.2), (600, H, 520, SUCCESS, 0.19)]


def write_md(path, block, comment):
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"<!-- {comment} Generated by assets/gen_profile.py; edit the script, not this file. -->\n{block}\n")


ROOT = os.path.join(HERE, "..")

# ---- Profile README ----
s = Scene(W)
b, c = hero(s)
b, c = featured(s, b, c)
b, c = projects(s, b, c, DEFAULT, ("hint", "[Select a project to open its file.]"))
b = toolbox(s, b, c)
finish(s, b, lights)
s.slice("07-end.svg", 0, c, W, s.h - c,
        alt="Toolbox: C#, C++, Unity 6 with URP and UI Toolkit, Unreal Engine, FishNet, ASP.NET Core, PostgreSQL; "
            "server-authoritative architecture, data-driven design, unit testing, DI and EventBus.")
s.export(OUT)
write_md(os.path.join(ROOT, "README.md"), s.html("assets/profile/"), "Profile of Kilian Monnier.")
total = len(s.slices)

# ---- One page per project: same panel, another project selected ----
os.makedirs(os.path.join(ROOT, "projects"), exist_ok=True)
for p in PROJECTS:
    s = Scene(W)
    b, c = projects(s, -GAP + M - 0, 0, p["slug"], ("back", PROFILE))
    s.h = b + 24
    s.sky(lights(2400)[:2] + [(600, s.h, 520, SUCCESS, 0.19)], seed=5)
    s.slice("07-end.svg", 0, c, W, s.h - c, alt="")
    out = os.path.join(HERE, "projects", p["slug"])
    s.export(out)
    write_md(os.path.join(ROOT, "projects", f"{p['slug']}.md"), s.html(f"../assets/projects/{p['slug']}/"),
             f"Project file: {p['title']}.")
    total += len(s.slices)
print(f"{total} slices, {1 + len(PROJECTS)} pages")
