import re
import sys
import subprocess
import xml.etree.ElementTree as ET

INPUT_SVG = sys.argv[1] if len(sys.argv) > 1 else 'profile-blue-violet.svg'
OUTPUT_PNG = sys.argv[2] if len(sys.argv) > 2 else 'contrib-3d-minimal.png'

# ── palette (doit correspondre à settings.json) ──────────────────────────────
COLOR_MAP = {
    'fill-fg':     '#a0a8d0', 'stroke-fg':     '#a0a8d0',
    'fill-bg':     '#08080f', 'stroke-bg':     '#08080f',
    'fill-weak':   '#3a3a6a', 'stroke-weak':   '#3a3a6a',
    'fill-strong': 'rgb(100,60,210)', 'stroke-strong': 'rgb(100,60,210)',
}

NS = '{http://www.w3.org/2000/svg}'
ET.register_namespace('', 'http://www.w3.org/2000/svg')

# ── parser l'original ────────────────────────────────────────────────────────
root = ET.fromstring(open(INPUT_SVG).read())

# ── 1. Remplacer les classes CSS par des attributs inline (fill/stroke) ────
def class_to_colors(cls_value):
    """Retourne (fill_or_None, stroke_or_None) depuis une valeur de class."""
    fill = stroke = None
    for c in cls_value.split():
        if c not in COLOR_MAP:
            continue
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
    # Ne pas écraser un fill/stroke explicite déjà présent
    if fill_c and 'fill' not in elem.attrib:
        elem.set('fill', fill_c)
    if stroke_c and 'stroke' not in elem.attrib:
        elem.set('stroke', stroke_c)

# Diagnostic : counts avant nettoyage
all_rects = list(root.iter(NS + 'rect'))
with_fill_before = sum(1 for r in all_rects if r.get('fill') is not None)
without_fill_before = len(all_rects) - with_fill_before
print(f"Rects AVANT: {len(all_rects)} total, {with_fill_before} avec fill, {without_fill_before} sans fill",
      file=sys.stderr)

# ── 2. Supprimer le <style> et tous les éléments non-voxels ─────────────────
def remove_descendants(parent, tag_name):
    for elem in list(parent):
        if elem.tag == NS + tag_name:
            parent.remove(elem)
        else:
            remove_descendants(elem, tag_name)

def remove_if(parent, tag_name, pred):
    for elem in list(parent):
        if elem.tag == NS + tag_name:
            if pred(elem):
                parent.remove(elem)
        else:
            remove_if(elem, tag_name, pred)

# Supprimer le style
for elem in list(root):
    if elem.tag == NS + 'style':
        root.remove(elem)

# Supprimer texte, animations, lignes dash du radar
remove_descendants(root, 'text')
remove_descendants(root, 'animate')
remove_descendants(root, 'animateTransform')
remove_if(root, 'line', lambda e: 'stroke-dasharray' in (e.get('style') or ''))

# Supprimer les groupes spécifiques (radar chart, langs, icons)
def remove_group_by_transform(parent, target, depth=0):
    for elem in list(parent):
        if elem.tag == NS + 'g' and elem.get('transform') == target:
            parent.remove(elem)
            return True
        if elem.tag == NS + 'g' and remove_group_by_transform(elem, target, depth+1):
            return True
    return False

for t in ['translate(980, 284.5)', 'translate(40, 520)', 'translate(130, 130)']:
    remove_group_by_transform(root, t)

# Supprimer les groupes d'icônes (translate(x,y), scale(2))
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

# ── 3. Compter rects après nettoyage ────────────────────────────────────────
all_rects2 = list(root.iter(NS + 'rect'))
with_fill_after = sum(1 for r in all_rects2 if r.get('fill') is not None)
print(f"Rects APRÈS nettoyage: {len(all_rects2)} total, {with_fill_after} avec fill",
      file=sys.stderr)

# ── Diagnostic des rects sans fill ──────────────────────────────────────────
no_fill_rects = [r for r in all_rects2 if r.get('fill') is None]
if no_fill_rects:
    print(f"\nRects sans fill ({len(no_fill_rects)}):", file=sys.stderr)
    # Montrer quelques exemples
    for r in no_fill_rects[:3]:
        print(f"  attributs: {dict(r.attrib)}", file=sys.stderr)

# ── 4. Assigner des couleurs et dégradés aux faces ──────────────────────────
# Faces du dessus (height=18) → couleur solide
# Faces latérales (height=2.6) → dégradé bleu→violet (définir plus bas)
# Faces latérales de hauteur variable (contribution) → couleur solide

# On identifie les faces latérales de base (height=2.6) pour leur attribuer
# le dégradé au lieu d'une couleur. Les autres faces gardent une couleur solide.

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

    if abs(h_val - 2.6) < 0.01:
        # Face latérale basse (2.6) → dégradé (appliqué au niveau SVG string)
        elem.set('fill', 'url(#pillar-fade)')
    elif abs(h_val - 18.0) < 0.01:
        elem.set('fill', COLOR_MAP['fill-fg'])
    else:
        ratio = min(h_val / 30.0, 1.0)
        if ratio > 0.55:
            elem.set('fill', COLOR_MAP['fill-strong'])
        else:
            elem.set('fill', COLOR_MAP['fill-fg'])

# Vérification
after_assign = list(root.iter(NS + 'rect'))
with_fill_final = sum(1 for r in after_assign if r.get('fill') is not None)
print(f"Rects APRÈS assignation: {with_fill_final}/{len(after_assign)} avec fill",
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

# ── Injecter le <defs> avec le dégradé ──────────────────────────────────────
defs_block = (
    '<defs>'
    '<linearGradient id="pillar-fade" x1="0" y1="1" x2="0" y2="0">'
    '<stop offset="0%" stop-color="#4a6fa5"/>'
    '<stop offset="100%" stop-color="#643cd2"/>'
    '</linearGradient>'
    '</defs>'
)
svg_out = re.sub(r'(<svg[^>]*>)', r'\1' + defs_block, svg_out, count=1)

clean_path = 'profile-cleaned.svg'
open(clean_path, 'w').write(svg_out)
print(f"SVG écrit: {clean_path} ({len(svg_out)} chars)", file=sys.stderr)

# Vérification
if 'linearGradient' in svg_out and 'pillar-fade' in svg_out:
    print("✓ Dégradé pillar-fade présent", file=sys.stderr)
else:
    print("✗ ERREUR: dégradé manquant!", file=sys.stderr)
    sys.exit(1)

gradient_count_final = len(re.findall(r'fill="url\(#pillar-fade\)"', svg_out))
print(f"Rects avec dégradé: {gradient_count_final}", file=sys.stderr)

# Vérification finale dans le fichier
cleaned = open(clean_path).read()
sample = re.findall(r'<rect[^>]*fill="[^"]+"', cleaned)
print(f"Rects avec fill dans le fichier: {len(sample)}/{len(re.findall(r'<rect', cleaned))}",
      file=sys.stderr)
if sample:
    print(f"  Ex: {sample[0][:120]!r}", file=sys.stderr)

# ── 6. Conversion PNG ────────────────────────────────────────────────────────
res = subprocess.run(
    ['rsvg-convert', '--width', '1280', '--height', '850',
     clean_path, '-o', OUTPUT_PNG],
    capture_output=True, text=True
)
if res.returncode != 0:
    print(f"Erreur rsvg-convert: {res.stderr}", file=sys.stderr)
    sys.exit(1)

import os
print(f"PNG: {OUTPUT_PNG} ({os.path.getsize(OUTPUT_PNG)} bytes)")
