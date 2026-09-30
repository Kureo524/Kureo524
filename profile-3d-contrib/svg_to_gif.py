#!/usr/bin/env python3
"""
Génère un GIF animé du graph de contributions GitHub 3D isométrique.
L'effet est une croissance progressive des barres de contribution.
"""

import re
import sys
import os
import subprocess
import xml.etree.ElementTree as ET
from PIL import Image

INPUT_SVG  = sys.argv[1] if len(sys.argv) > 1 else 'profile-blue-violet-animate.svg'
OUTPUT_GIF = sys.argv[2] if len(sys.argv) > 2 else 'contrib-3d-animated.gif'
NUM_FRAMES = int(sys.argv[3]) if len(sys.argv) > 3 else 30
FPS = int(sys.argv[4]) if len(sys.argv) > 4 else 10

NS = '{http://www.w3.org/2000/svg}'
ET.register_namespace('', 'http://www.w3.org/2000/svg')

# ── palette ───────────────────────────────────────────────────────────────────
COLOR_MAP = {
    'fill-fg':     '#a0a8d0', 'stroke-fg':     '#a0a8d0',
    'fill-bg':     '#08080f', 'stroke-bg':     '#08080f',
    'fill-weak':   '#3a3a6a', 'stroke-weak':   '#3a3a6a',
    'fill-strong': 'rgb(100,60,210)', 'stroke-strong': 'rgb(100,60,210)',
}

BLUE_RGB  = (44, 62, 90)
VIOLET_RGB = (90, 90, 138)
TOP_FACE_RGB = (122, 138, 158)

Y_BOT = 825
Y_TOP = 143

def y_to_color(y):
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
    parent = None
    for p in root.iter():
        for child in list(p):
            if child is elem:
                parent = p
                break
        if parent is not None:
            break
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
    m = re.search(r'translate\(\s*(-?\d+\.?\d*)\s*[, ]\s*(-?\d+\.?\d*)\s*\)', transform)
    if m:
        return float(m.group(2))
    return None

# ── 1. Parser le SVG original ────────────────────────────────────────────────
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

# ── 3. Supprimer éléments non-voxels (texte, style, radar, icons) ──────────
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

# ── 4. Extraire les hauteurs cibles de chaque barre ─────────────────────────
# Les animations animent les hauteurs depuis 2.6 (baseline) vers une valeur cible.
# On extrait les valeurs cibles depuis les attributs height actuels des rects
# qui ont des animations, ou depuis les valeurs 'values' des animations.

# Pour chaque rect avec height > 2.6, c'est une barre de contribution.
# L'hauteur actuelle dans le SVG est souvent la valeur cible (à la fin de l'animation).
# Si le rect a une animation, on peut extraire la valeur finale depuis l'attribut values.

barres = []  # liste de (elem, hauteur_cible, ty_group)

for elem in root.iter(NS + 'rect'):
    h = elem.get('height')
    if h is None:
        continue
    try:
        h_val = float(h)
    except (ValueError, TypeError):
        continue

    # Trouver l'hauteur cible
    target_h = h_val

    # Vérifier s'il y a une animation sur ce rect (via le parent ou l'élément lui-même)
    anim = elem.find(NS + 'animate')
    if anim is not None:
        anim_values = anim.get('values', '')
        if anim_values:
            # Ex: "2.6;12.47" → la dernière valeur est la cible
            parts = anim_values.split(';')
            if parts:
                try:
                    target_h = float(parts[-1])
                except ValueError:
                    pass

    # Le baseline est 2.6 (hauteur minimale)
    baseline = 2.6
    if target_h > baseline:
        # C'est une barre de contribution
        ty_elem = None
        # Chercher le ty du groupe parent (pour le fade)
        parent = None
        for p in root.iter():
            for child in list(p):
                if child is elem:
                    parent = p
                    break
            if parent is not None:
                break
        while parent is not None:
            if parent.tag == NS + 'g':
                t = parent.get('transform', '')
                ty_elem = extract_translate_y(t)
                break
            gp = None
            for g in root.iter():
                for gc in list(g):
                    if gc is parent:
                        gp = g
                        break
                if gp is not None:
                    break
            parent = gp

        barres.append((elem, target_h, ty_elem))

remove_by_tag(root, 'animate')
remove_by_tag(root, 'animateTransform')

print(f"Barres identifiées: {len(barres)}", file=sys.stderr)

# ── 5. Assigner les couleurs de base ─────────────────────────────────────────
# On assigne les couleurs aux faces latérales (height=2.6) selon leur position Y
# ET on assigne la couleur de la face du dessus (height=18)

for elem in root.iter(NS + 'rect'):
    h = elem.get('height')
    if h is None:
        continue
    try:
        h_val = float(h)
    except (ValueError, TypeError):
        continue

    if abs(h_val - 2.6) < 0.01:
        # Face latérale basse → fade selon Y
        ty_elem = None
        parent = None
        for p in root.iter():
            for child in list(p):
                if child is elem:
                    parent = p
                    break
            if parent is not None:
                break
        while parent is not None:
            if parent.tag == NS + 'g':
                t = parent.get('transform', '')
                ty_elem = extract_translate_y(t)
                break
            gp = None
            for g in root.iter():
                for gc in list(g):
                    if gc is parent:
                        gp = g
                        break
                if gp is not None:
                    break
            parent = gp

        if ty_elem is not None:
            elem.set('fill', y_to_color(ty_elem))
        else:
            elem.set('fill', COLOR_MAP['fill-weak'])
    elif abs(h_val - 18.0) < 0.01:
        elem.set('fill', f"rgb({TOP_FACE_RGB[0]},{TOP_FACE_RGB[1]},{TOP_FACE_RGB[2]})")
    else:
        ratio = min(h_val / 30.0, 1.0)
        if ratio > 0.55:
            elem.set('fill', COLOR_MAP['fill-strong'])
        else:
            elem.set('fill', f"rgb({TOP_FACE_RGB[0]},{TOP_FACE_RGB[1]},{TOP_FACE_RGB[2]})")

# ── 6. Générer les frames ────────────────────────────────────────────────────
os.makedirs('frames', exist_ok=True)

print(f"Génération de {NUM_FRAMES} frames...", file=sys.stderr)

for frame_idx in range(NUM_FRAMES):
    progress = frame_idx / (NUM_FRAMES - 1) if NUM_FRAMES > 1 else 1.0

    # Créer une copie de l'arbre pour cette frame
    frame_root = ET.Element(root.tag, root.attrib)
    # Copier récursivement sauf les rects de barres
    for child in root:
        if child.tag == NS + 'rect':
            h = child.get('height')
            if h is None:
                # Copier tel quel
                ET.SubElement(frame_root, child.tag, child.attrib)
                continue

            try:
                h_val = float(h)
            except (ValueError, TypeError):
                ET.SubElement(frame_root, child.tag, child.attrib)
                continue

            # Vérifier si c'est une barre de contribution
            is_barre = False
            target_h = h_val
            for barre_elem, barre_target, barre_ty in barres:
                if barre_elem is child:
                    is_barre = True
                    target_h = barre_target
                    break

            if is_barre:
                # Interpoler la hauteur: baseline + (target - baseline) * progress
                baseline = 2.6
                new_h = baseline + (target_h - baseline) * progress
                attribs = dict(child.attrib)
                attribs['height'] = str(new_h)
                ET.SubElement(frame_root, child.tag, attribs)
            else:
                # Rect non-barre (face du dessus, etc.) → copier tel quel
                ET.SubElement(frame_root, child.tag, child.attrib)
        else:
            # Éléments non-rect → copier
            ET.SubElement(frame_root, child.tag, child.attrib)

    # Exporter le frame SVG
    frame_svg = ET.tostring(frame_root, encoding='unicode').strip()
    if not frame_svg.startswith('<svg'):
        i = frame_svg.find('<svg')
        if i >= 0:
            frame_svg = frame_svg[i:]
    frame_svg = '<?xml version="1.0" encoding="UTF-8"?>\n' + frame_svg + '\n'
    frame_svg = re.sub(r'\s+', ' ', frame_svg)
    frame_svg = re.sub(r'> <', '><', frame_svg)

    frame_svg_path = f'frames/frame_{frame_idx:03d}.svg'
    with open(frame_svg_path, 'w') as f:
        f.write(frame_svg)

    # Convertir en PNG avec rsvg-convert
    frame_png_path = f'frames/frame_{frame_idx:03d}.png'
    res = subprocess.run(
        ['rsvg-convert', '--width', '1280', '--height', '850',
         frame_svg_path, '-o', frame_png_path],
        capture_output=True, text=True
    )
    if res.returncode != 0:
        print(f"Erreur frame {frame_idx}: {res.stderr}", file=sys.stderr)
        sys.exit(1)

    if frame_idx % 5 == 0:
        print(f"  Frame {frame_idx}/{NUM_FRAMES} générée", file=sys.stderr)

# ── 7. Créer le GIF ──────────────────────────────────────────────────────────
print("Création du GIF...", file=sys.stderr)

frames_png = []
for i in range(NUM_FRAMES):
    png_path = f'frames/frame_{i:03d}.png'
    img = Image.open(png_path).convert('RGB')
    frames_png.append(img)

# Use the first frame to initialize the GIF
frames_png[0].save(
    OUTPUT_GIF,
    save_all=True,
    append_images=frames_png[1:],
    duration=int(1000 / FPS),
    optimize=True,
    loop=0,
)

print(f"GIF créé: {OUTPUT_GIF} ({os.path.getsize(OUTPUT_GIF)} bytes)", file=sys.stderr)
