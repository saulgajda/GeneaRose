#!/usr/bin/env python3
import json, math, html, sys
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

# Starting from this generation the names 
# will be drawn on the radius not on the arc
# We count generactions backward so:
# 0 = central person, 1 = parents, 2 = grandparents
RADIAL_FROM_GENERATION = 6
RING_WIDTH = 90
CENTER_RADIUS = 80
PADDING = 20
MAX_FONT = 16
MIN_FONT = 7


def load_tree(path):
    text = Path(path).read_text(encoding="utf-8")
    if path.endswith((".yml", ".yaml")):
        if yaml is None:
            raise RuntimeError("Install PyYAML: pip install pyyaml")
        return yaml.safe_load(text)
    return json.loads(text)


def max_depth(person):
    if not person:
        return 0
    return 1 + max(max_depth(person.get("father")), max_depth(person.get("mother")))

def split_text(text, max_chars):
    # Prefer splitting between name and dates.
    # Expected format: "Name Surname 1900 - 1980"
    date_pos = None

    for sep in [" - ", "–", "-"]:
        idx = text.find(sep)
        if idx != -1:
            # walk backwards to include the birth date before " - "
            before = text[:idx].rstrip()
            parts = before.split()
            if parts and any(ch.isdigit() for ch in parts[-1]):
                birth = parts[-1]
                name = before[: before.rfind(birth)].rstrip()
                dates = text[len(name):].strip()
                date_pos = (name, dates)
                break

    if date_pos:
        name, dates = date_pos

        if len(name) <= max_chars and len(dates) <= max_chars:
            return [name, dates]

        # If name is still too long, split inside the name.
        name_lines = split_name(name, max_chars)
        return name_lines + [dates]

    return split_name(text, max_chars)


def split_name(name, max_chars):
    words = name.split()
    lines, cur = [], ""

    for w in words:
        if not cur:
            cur = w
        elif len(cur) + 1 + len(w) <= max_chars:
            cur += " " + w
        else:
            lines.append(cur)
            cur = w

    if cur:
        lines.append(cur)

    return lines or [""]


def fmt_person(p):
    name = p.get("name", "")

    birth = str(p["birth"]) if p.get("birth") else ""
    death = str(p["death"]) if p.get("death") else ""

    if birth and death:
        return f"{name} {birth} - {death}"
    if birth:
        return f"{name} {birth}"
    if death:
        return f"{name} - {death}"

    return name


def polar(cx, cy, r, deg):
    a = math.radians(deg)
    return cx + r * math.cos(a), cy + r * math.sin(a)


def arc_path(cx, cy, r, a0, a1):
    x0, y0 = polar(cx, cy, r, a0)
    x1, y1 = polar(cx, cy, r, a1)
    large = 1 if abs(a1 - a0) > 180 else 0
    sweep = 1 if a1 > a0 else 0
    return f"M {x0:.2f} {y0:.2f} A {r:.2f} {r:.2f} 0 {large} {sweep} {x1:.2f} {y1:.2f}"


def sector_path(cx, cy, r0, r1, a0, a1):
    x1, y1 = polar(cx, cy, r1, a0)
    x2, y2 = polar(cx, cy, r1, a1)
    x3, y3 = polar(cx, cy, r0, a1)
    x4, y4 = polar(cx, cy, r0, a0)
    large = 1 if abs(a1 - a0) > 180 else 0
    return (
        f"M {x1:.2f} {y1:.2f} "
        f"A {r1:.2f} {r1:.2f} 0 {large} 1 {x2:.2f} {y2:.2f} "
        f"L {x3:.2f} {y3:.2f} "
        f"A {r0:.2f} {r0:.2f} 0 {large} 0 {x4:.2f} {y4:.2f} Z"
    )


def font_for(text, available):
    if not text:
        return MAX_FONT
    return max(MIN_FONT, min(MAX_FONT, available / (0.58 * len(text))))


def render_person(svg, defs, person, gen, a0, a1, cx, cy, path_counter):
    if not person:
        return path_counter

    text = fmt_person(person)

    if gen == 0:
        lines = split_text(text, 18)
        svg.append(f'<circle cx="{cx}" cy="{cy}" r="{CENTER_RADIUS}" class="root"/>')
        y0 = cy - (len(lines) - 1) * 9
        for i, line in enumerate(lines):
            svg.append(
                f'<text x="{cx}" y="{y0 + i * 18}" text-anchor="middle" '
                f'dominant-baseline="middle" font-size="15">{html.escape(line)}</text>'
            )
    else:
        r0 = CENTER_RADIUS + (gen - 1) * RING_WIDTH
        r1 = CENTER_RADIUS + gen * RING_WIDTH
        rm = (r0 + r1) / 2
        angle = abs(a1 - a0)
        mid = (a0 + a1) / 2

        svg.append(f'<path d="{sector_path(cx, cy, r0, r1, a0, a1)}" class="sector"/>')

        if gen < RADIAL_FROM_GENERATION:
            available = math.radians(angle) * rm * 0.82
            font = font_for(text, available)
            max_chars = max(6, int(available / (font * 0.55)))
            lines = split_text(text, max_chars)

            for i, line in enumerate(lines):
                # First line/name goes outward, later lines/dates go inward
                rr = rm + ((len(lines) - 1) / 2 - i) * font * 1.25
                #rr = rm + (i - (len(lines) - 1) / 2) * font * 1.25
                pid = f"p{path_counter}"
                path_counter += 1
                defs.append(f'<path id="{pid}" d="{arc_path(cx, cy, rr, a0 + 3, a1 - 3)}"/>')
                svg.append(
                    f'<text font-size="{font:.1f}">'
                    f'<textPath href="#{pid}" startOffset="50%" text-anchor="middle">'
                    f'{html.escape(line)}'
                    f'</textPath></text>'
                )
        else:
            available = RING_WIDTH * 0.85
            font = font_for(text, available)
            max_chars = max(5, int(available / (font * 0.55)))
            lines = split_text(text, max_chars)

            x, y = polar(cx, cy, rm, mid)
            rotation = mid
            if 90 < rotation < 270:
                rotation += 180

            for i, line in enumerate(lines):
                dy = (i - (len(lines) - 1) / 2) * font * 1.2
                svg.append(
                    f'<text x="{x:.2f}" y="{y:.2f}" font-size="{font:.1f}" '
                    f'text-anchor="middle" dominant-baseline="middle" '
                    f'transform="rotate({rotation:.2f} {x:.2f} {y:.2f}) translate(0 {dy:.2f})">'
                    f'{html.escape(line)}</text>'
                )

    mid = (a0 + a1) / 2
    father = person.get("father")
    mother = person.get("mother")

    if father:
        path_counter = render_person(svg, defs, father, gen + 1, a0, mid, cx, cy, path_counter)
    if mother:
        path_counter = render_person(svg, defs, mother, gen + 1, mid, a1, cx, cy, path_counter)

    return path_counter


def generate_svg(root):
    depth = max_depth(root)
    radius = CENTER_RADIUS + max(0, depth - 1) * RING_WIDTH + PADDING
    size = radius * 2
    cx = cy = radius

    defs, svg = [], []

    svg.append(f'''<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 {size} {size}">
<style>
    text {{
        font-family: Arial, sans-serif;
        fill: #222;
    }}
    .root {{
        fill: #f7f7f7;
        stroke: #333;
        stroke-width: 1.5;
    }}
    .sector {{
        fill: #f7f7f7;
        stroke: #bbb;
        stroke-width: 1;
    }}
</style>
''')

    render_person(svg, defs, root, 0, 0, 360, cx, cy, 0)

    if defs:
        svg.insert(1, "<defs>\n" + "\n".join(defs) + "\n</defs>")

    svg.append("</svg>")
    return "\n".join(svg)


def main():
    if len(sys.argv) != 3:
        print("Usage: python genearose.py input.yml output.svg")
        sys.exit(1)

    root = load_tree(sys.argv[1])
    svg = generate_svg(root)
    Path(sys.argv[2]).write_text(svg, encoding="utf-8")


if __name__ == "__main__":
    main()
