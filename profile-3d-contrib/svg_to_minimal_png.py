#!/usr/bin/env python3
"""Génère un PNG 3D isométrique minimal du graph de contributions GitHub.

- Parse le SVG de github-profile-3d-contrib, nettoie (supprime texte,
  animations, radar chart, icônes, lignes pointillées).
- Remplace les classes CSS par des attributs fill/stroke inline.
- Assigne une couleur à chaque face:
    * face du dessus (height=18)       → #a0a8d0 (beige-gris clair)
    * face latérale basse (height=2.6) → fade bleu→violet selon Y (calculé)
    * faces de contribution variable   → #a0a8d0 ou rgb(100,60,210) selon intensité
- Convertit en PNG via rsvg-convert.
"""

import re
import sys
import subprocess
import xml.etree.ElementTree as ET

INPUT_SVG  = sys.argv[1] if len(sys.argv) > 1 else 'profile-blue-violet.svg'
OUTPUT_PNG = sys.argv[2] if len(sys.argv) > 2 else 'contrib-3d-minimal.png'

# ── palette ───────────────────────────────────────────────────────────────────
COLOR_MAP = {
    'fill-fg':     '#a0a8d0', 'stroke-fg':     '#a0a8d0',
    'fill-bg':     '#08080f', 'stroke-bg':     '#08080f',
    'fill-weak':   '#3a3a6a', 'stroke-weak':   '#3a3a6a',
    'fill-strong': 'rgb(100,60,210)', 'stroke-strong': 'rgb(100,60,210)',
}

NS = '{http://www.w3.org/2000/svg}'
ET.register_namespace('', 'http://www.w3.org/2000/svg')

# ── fade vertical: bleu en bas, violet en haut ───────────────────────────────
# Palette professionnelle: tons mutés, pas de néon
# Bleu bas (faibles contributions) → Violet haut (fortes contributions)
# Contraste suffisant sur fond #08080f

# Couleurs extrêmes du fade
# Bas (bleu professionnel, pas trop lumineux): rgb(44, 62, 90) — #2c3e5a
# Haut (violet muté, pas néon): rgb(90, 90, 138) — #5a5a8a
BLUE_RGB  = (44, 62, 90)     # fond bas
VIOLET_RGB = (90, 90, 138)   # fond haut

# Face du dessus: gris bleu clinique, contient bien sur fond sombre
TOP_FACE_RGB = (122, 138, 158)  # #7a8a9e


def y_to_color(y):
    """Retourne une couleur RGB interpolée entre bleu (bas) et violet (haut)."""
    Y_BOT = 825   # bas de l'axe Y (bleu)
    Y_TOP = 143   # haut de l'axe Y (violet)
    if y >= Y_BOT:
        t = 0.0
    elif y <= Y_TOP:
        t = 1.0
    else:
        t = (Y_BOT - y) / (Y_BOT - Y_TOP)
    r = int(BLUE_RGB[0] + (VIOLET_RGB[0] - BLUE_RGB[0]) * t)
    g = int(BLUE_RGB[1] + (VIOLET_RGB[1] - BLUE_RGB[1]) * t)
    b = int(BLUE_RGB[2] + (VIOLET_RGB[2] - BLUE_RGB[2]) * t)
    return f"rgb({r},{g},{b})"


def find_parent_group_transform(elem, root):
    """Trouve le transform du premier <g> parent (contenant un translate)."""
    # Cherche le parent direct
    parent = None
    for p in root.iter():
        for child in list(p):
            if child is elem:
                parent = p
                break
        if parent is not None:
            break
    # Remonte jusqu'au premier <g> avec transform
    while parent is not None:
        if parent.tag == NS + 'g':
            t = parent.get('transform', '')
            if t:
                return t
        gp = None
        for g in root.iter():
            for gc in list(g):
                if gc is parent:
                    gp = g
                    break
            if gp is not None:
                break
        parent = gp
    return ''


def extract_translate_y(transform):
    """Extrait le Y du translate(x, y) d'une transform SVG."""
    # Formats possibles: translate(140 154.18) ou translate(140, 154.18) ou translate(140,154.18)
    m = re.search(r'translate\(\s*(-?\d+\.?\d*)\s*[, ]?\s*(-?\d+\.?\d*)\s*\)', transform)
    if m:
        return float(m.group(2))
    return None


# ── 1. Parser ────────────────────────────────────────────────────────────────
root = ET.fromstring(open(INPUT_SVG).read())

# ── 2. Remplacer les classes CSS ─────────────────────────────────────────────
def class_to_colors(cls_value):
    fill = stroke = None
    for c in cls_value.split():
        if c in COLOR_MAP:
            col = COLOR_MAP[c]
            if 'fill' in c:
                fill = col
            else:
                stroke = col
    return fill, stroke

for elem in root.iter():
    cls = elem.get('class')
    if cls is None:
        continue
    fill_c, stroke_c = class_to_colors(cls)
    del elem.attrib['class']
    if fill_c and 'fill' not in elem.attrib:
        elem.set('fill', fill_c)
    if stroke_c and 'stroke' not in elem.attrib:
        elem.set('stroke', stroke_c)

all_rects = list(root.iter(NS + 'rect'))
with_fill_before = sum(1 for r in all_rects if r.get('fill') is not None)
print(f"Rects AVANT: {len(all_rects)} total, {with_fill_before} avec fill",
      file=sys.stderr)

# ── 3. Supprimer le <style> et éléments superflus ───────────────────────────
def remove_by_tag(parent, tag):
    for elem in list(parent):
        if elem.tag == NS + tag:
            parent.remove(elem)
        else:
            remove_by_tag(elem, tag)

def remove_if(parent, tag, pred):
    for elem in list(parent):
        if elem.tag == NS + tag:
            if pred(elem):
                parent.remove(elem)
        else:
            remove_if(elem, tag, pred)

for elem in list(root):
    if elem.tag == NS + 'style':
        root.remove(elem)

remove_by_tag(root, 'text')
remove_by_tag(root, 'animate')
remove_by_tag(root, 'animateTransform')
remove_if(root, 'line', lambda e: 'stroke-dasharray' in (e.get('style') or ''))

def remove_group_by_transform(parent, target):
    for elem in list(parent):
        if elem.tag == NS + 'g' and elem.get('transform') == target:
            parent.remove(elem)
            return True
        if elem.tag == NS + 'g' and remove_group_by_transform(elem, target):
            return True
    return False

for t in ['translate(980, 284.5)', 'translate(40, 520)', 'translate(130, 130)']:
    remove_group_by_transform(root, t)

def remove_icon_groups(parent):
    n = 0
    for elem in list(parent):
        if elem.tag == NS + 'g':
            t = elem.get('transform', '')
            if re.match(r'translate\(\d+,\s*\d+\),\s*scale\(2\)', t):
                parent.remove(elem)
                n += 1
            else:
                n += remove_icon_groups(elem)
    return n

remove_icon_groups(root)

final_rects_before = list(root.iter(NS + 'rect'))
with_fill_before2 = sum(1 for r in final_rects_before if r.get('fill') is not None)
print(f"Rects APRÈS nettoyage: {len(final_rects_before)} total, "
      f"{with_fill_before2} avec fill", file=sys.stderr)

# ── 4. Assigner les couleurs ─────────────────────────────────────────────────
# On fait deux passes:
#   Pass 1 : pour chaque rect latéral (height=2.6), extraire le Y du parent
#            groupe et calculer la couleur fade
#   Pass 2 : pour les autres rects, assigner les couleurs standard

# Pass 1: collecter les Y et assigner les couleurs fade
lateral_faces = []
for elem in root.iter(NS + 'rect'):
    h = elem.get('height')
    if h and abs(float(h) - 2.6) < 0.01:
        parent_transform = find_parent_group_transform(elem, root)
        ty = extract_translate_y(parent_transform)
        lateral_faces.append((elem, ty))

print(f"Faces latérales identifiées: {len(lateral_faces)}", file=sys.stderr)

# Assigner les couleurs fade
for elem, ty in lateral_faces:
    if ty is not None:
        elem.set('fill', y_to_color(ty))
    else:
        elem.set('fill', COLOR_MAP['fill-weak'])

# Pass 2: autres rects
for elem in root.iter(NS + 'rect'):
    if elem.get('fill') is not None:
        continue
    h = elem.get('height')
    if h is None:
        continue
    try:
        h_val = float(h)
    except (ValueError, TypeError):
        continue

    if abs(h_val - 18.0) < 0.01:
        elem.set('fill', f"rgb({TOP_FACE_RGB[0]},{TOP_FACE_RGB[1]},{TOP_FACE_RGB[2]})")
    else:
        ratio = min(h_val / 30.0, 1.0)
        if ratio > 0.55:
            elem.set('fill', COLOR_MAP['fill-strong'])
        else:
            elem.set('fill', f"rgb({TOP_FACE_RGB[0]},{TOP_FACE_RGB[1]},{TOP_FACE_RGB[2]})")

# Vérification
after_assign = list(root.iter(NS + 'rect'))
with_fill_after = sum(1 for r in after_assign if r.get('fill') is not None)
print(f"Rects APRÈS assignation: {with_fill_after}/{len(after_assign)} avec fill",
      file=sys.stderr)

# Diagnostic couleurs
from collections import Counter
fill_colors = Counter(r.get('fill') for r in after_assign)
print(f"\nPalette utilisée:", file=sys.stderr)
for color, count in fill_colors.most_common():
    print(f"  {color!r}: {count}", file=sys.stderr)

# Vérifier spécifiquement le fade
fade_colors = [c for c in fill_colors.keys()
               if c.startswith('rgb(') and 'fill-weak' not in c
               and 'fill-strong' not in c and 'fill-fg' not in c]
print(f"\nFaces avec couleur fade (calculée): {sum(fill_colors[c] for c in fade_colors)}",
      file=sys.stderr)
if fade_colors:
    print(f"  Exemple fade: {fade_colors[0]!r} ({fill_colors[fade_colors[0]]} faces)",
          file=sys.stderr)

# ── 5. Exporter ─────────────────────────────────────────────────────────────
svg_out = ET.tostring(root, encoding='unicode').strip()
if not svg_out.startswith('<svg'):
    i = svg_out.find('<svg')
    if i >= 0:
        svg_out = svg_out[i:]
svg_out = '<?xml version="1.0" encoding="UTF-8"?>\n' + svg_out + '\n'
svg_out = re.sub(r'\s+', ' ', svg_out)
svg_out = re.sub(r'> <', '><', svg_out)

clean_path = 'profile-cleaned.svg'
with open(clean_path, 'w') as f:
    f.write(svg_out)

print(f"SVG écrit: {clean_path} ({len(svg_out)} chars)", file=sys.stderr)

# ── 6. Convertir en PNG ─────────────────────────────────────────────────────
res = subprocess.run(
    ['rsvg-convert', '--width', '1280', '--height', '850',
     clean_path, '-o', OUTPUT_PNG],
    capture_output=True, text=True
)
if res.returncode != 0:
    print(f"Erreur rsvg-convert: {res.stderr}", file=sys.stderr)
    print(f"stdout: {res.stdout}", file=sys.stderr)
    sys.exit(1)

import os
print(f"PNG: {OUTPUT_PNG} ({os.path.getsize(OUTPUT_PNG)} bytes)")
