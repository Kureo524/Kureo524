import re
import sys

# Ce script nettoie le SVG 3D isométrique et le convertit en PNG minimal.
# Usage: python3 svg_to_minimal_png.py <input.svg> <output.png>

INPUT_SVG = sys.argv[1] if len(sys.argv) > 1 else 'profile-blue-violet.svg'
OUTPUT_PNG = sys.argv[2] if len(sys.argv) > 2 else 'contrib-3d-minimal.png'

# palette couleurs (doit correspondre à settings.json)
COLOR_MAP = {
    'fill-fg': '#a0a8d0', 'stroke-fg': '#a0a8d0',
    'fill-bg': '#08080f', 'stroke-bg': '#08080f',
    'fill-weak': '#3a3a6a', 'stroke-weak': '#3a3a6a',
    'fill-strong': 'rgb(100, 60, 210)', 'stroke-strong': 'rgb(100, 60, 210)',
}

with open(INPUT_SVG, 'r') as f:
    svg = f.read()

# 1. Remplacer les classes CSS par des attributs inline explicites
def fix_tag(m):
    tag = m.group(0)
    cls_match = re.search(r'class="([^"]+)"', tag)
    if not cls_match:
        return tag
    classes = cls_match.group(1).split()
    fill_c = stroke_c = None
    for c in classes:
        if c in COLOR_MAP:
            col = COLOR_MAP[c]
            if 'fill' in c:
                fill_c = col
            elif 'stroke' in c:
                stroke_c = col
    prefix = tag[:cls_match.start()]
    remainder = tag[cls_match.end():]
    new_tag = prefix + remainder
    if fill_c and 'fill=' not in new_tag:
        new_tag = new_tag.replace('>', f' fill="{fill_c}">', 1)
    if stroke_c and 'stroke=' not in new_tag and 'stroke:none' not in new_tag:
        new_tag = new_tag.replace('>', f' stroke="{stroke_c}">', 1)
    return new_tag

svg = re.sub(r'<[^>]*class="[^"]+"[^>]*>', fix_tag, svg)

# 2. Parser et nettoyer avec ElementTree
import xml.etree.ElementTree as ET
ET.register_namespace('', 'http://www.w3.org/2000/svg')
ns = '{http://www.w3.org/2000/svg}'

root = ET.fromstring(svg)

def remove_by_tag(parent, tag_name):
    for elem in list(parent):
        if elem.tag == ns + tag_name:
            parent.remove(elem)
        else:
            remove_by_tag(elem, tag_name)

def remove_by_predicate(parent, tag_name, pred):
    for elem in list(parent):
        if elem.tag == ns + tag_name:
            if pred(elem):
                parent.remove(elem)
        else:
            remove_by_predicate(elem, tag_name, pred)

def remove_group_by_transform(parent, transform_value):
    for elem in list(parent):
        if elem.tag == ns + 'g' and elem.get('transform') == transform_value:
            parent.remove(elem)
            return True
        if elem.tag == ns + 'g':
            if remove_group_by_transform(elem, transform_value):
                return True
    return False

def remove_icon_groups(parent):
    removed = 0
    for elem in list(parent):
        if elem.tag == ns + 'g':
            t = elem.get('transform', '')
            if re.match(r'translate\(\d+, \d+\), scale\(2\)', t):
                parent.remove(elem)
                removed += 1
            else:
                removed += remove_icon_groups(elem)
    return removed

# Supprimer le style
for elem in list(root):
    if elem.tag == ns + 'style':
        root.remove(elem)

# Supprimer le texte, les animations, les lignes dash du radar, les groupes specifiques
remove_by_tag(root, 'text')
remove_by_tag(root, 'animate')
remove_by_tag(root, 'animateTransform')
remove_by_predicate(root, 'line', lambda e: 'stroke-dasharray' in (e.get('style') or ''))

for t in ['translate(980, 284.5)', 'translate(40, 520)', 'translate(130, 130)']:
    remove_group_by_transform(root, t)

remove_icon_groups(root)

# Re-serialiser
output = ET.tostring(root, encoding='unicode').strip()
if not output.startswith('<svg'):
    idx = output.find('<svg')
    if idx >= 0:
        output = output[idx:]

output = '<?xml version="1.0" encoding="UTF-8"?>\n' + output + '\n'
output = re.sub(r'\s+', ' ', output)
output = re.sub(r'> <', '><', output)

svg_clean = 'profile-cleaned.svg'
with open(svg_clean, 'w') as f:
    f.write(output)

print(f'SVG nettoye: {len(output)} chars -> {svg_clean}', file=sys.stderr)

# 3. Convertir en PNG via rsvg-convert (la commande systeme)
import subprocess
result = subprocess.run(
    ['rsvg-convert', '--width', '1280', '--height', '850', svg_clean, '-o', OUTPUT_PNG],
    capture_output=True, text=True
)
if result.returncode != 0:
    print(f'Erreur rsvg-convert: {result.stderr}', file=sys.stderr)
    sys.exit(1)

print(f'PNG genere: {OUTPUT_PNG}')
