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

# Starting from this generation, dates can be displayed on the same line as name
# For earlier generations, dates will be on a separate line
DATES_SAME_LINE_FROM_GENERATION = 6

RING_WIDTH = 90
CENTER_RADIUS = 80
PADDING = 20
MAX_FONT = 16
MIN_FONT = 7

FONT_SIZES = [
    16,
    16,
    15,
    14,
    13,
    12,
    11,
    10,
    9,
    8,
    7,
    6,
]

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
    # Split text into lines, each fitting within max_chars
    words = text.split()
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


def split_name(name, max_chars):
    if not name:
        return [""]
    if len(name) <= max_chars:
        return [name]

    words = name.split()
    if len(words) == 1:
        return [name]

    # Try to split into 2 lines first, then 3 lines if needed.
    best = None
    best_max = None

    # Two-line splits
    for i in range(1, len(words)):
        top = " ".join(words[:i])
        bottom = " ".join(words[i:])
        candidate = [top, bottom]
        candidate_max = max(len(line) for line in candidate)
        if candidate_max <= max_chars:
            return candidate
        if best_max is None or candidate_max < best_max:
            best_max = candidate_max
            best = candidate

    # Three-line splits (more aggressive balancing)
    if len(words) >= 3:
        for i in range(1, len(words) - 1):
            for j in range(i + 1, len(words)):
                a = " ".join(words[:i])
                b = " ".join(words[i:j])
                c = " ".join(words[j:])
                candidate = [a, b, c]
                candidate_max = max(len(line) for line in candidate)
                if candidate_max <= max_chars:
                    return candidate
                if candidate_max < best_max:
                    best_max = candidate_max
                    best = candidate

    # If no partition fits within max_chars, return the best (most balanced) split found,
    # otherwise fall back to generic word-wrapping.
    if best is not None:
        return best

    return split_text(name, max_chars)


def fmt_person(p):
    name = p.get("name", "")
    print("name: " + name)
    
    birth = '*' + str(p["birth"]) if p.get("birth") else ""
    death = '✝︎' + str(p["death"]) if p.get("death") else ""

    dates = ""
    if birth and death:
        dates = f"{birth} {death}"
    elif birth:
        dates = birth
    elif death:
        dates = death

    return (name, dates)


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


def font_for(text, available, gen):
    return FONT_SIZES[gen]
    if not text:
        return MAX_FONT
    length = len(text) if not isinstance(text, int) else text
    return max(MIN_FONT, min(MAX_FONT, available / (0.58 * length)))


def render_person(svg, defs, person, gen, a0, a1, cx, cy, path_counter, max_generation):
    # Stop recursion if we've reached max generation
    if gen > max_generation:
        return path_counter

    # Extract name and dates only if person exists
    if person:
        name, dates = fmt_person(person)
    else:
        name, dates = "", ""

    if gen == 0 and person:
        # Allow more aggressive splitting in center: try 2- or 3-line splits
        lines = split_name(name, 18)
        # If dates are present, try to append them to last line if they fit,
        # otherwise push dates as a separate line (allow up to 3 lines total).
        if dates:
            if len(lines) and len(lines[-1]) + 1 + len(dates) <= 18:
                lines[-1] += " " + dates
            else:
                # If name+dates don't fit on one line, try splitting name into 2 lines
                if len(lines) == 1 and len(lines[0]) + 1 + len(dates) > 18 and " " in name:
                    alt = split_name(name, max(3, 18 // 2))
                    if len(alt) > 1:
                        # keep name split and put dates on their own line
                        lines = alt + [dates]
                    else:
                        lines.append(dates)
                else:
                    lines.append(dates)
        if person:
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

        # Draw sector whether person exists or not
        svg.append(f'<path d="{sector_path(cx, cy, r0, r1, a0, a1)}" class="sector"/>')

        # Only render text if person exists
        if person and gen < RADIAL_FROM_GENERATION:
            available = math.radians(angle) * rm * (0.98 if gen >= 4 else 0.92)
            font = font_for(name, available, gen)
            max_chars = max(6, int(available / (font * 0.55)))
            lines = split_name(name, max_chars)
            max_line = max(len(line) for line in lines)
            font = font_for(max_line, available, gen)
            # print(f"Max chars for gen {gen} is {max_chars}")
            
            # For generations before DATES_SAME_LINE_FROM_GENERATION, always put dates on separate line
            if dates and gen < DATES_SAME_LINE_FROM_GENERATION:
                # Try an aggressive split for the name first if it's a single line and contains spaces.
                if len(lines) == 1 and " " in name:
                    forced_max = max(3, int(max_chars / 3))
                    alt = split_name(name, forced_max)
                    if len(alt) > 1:
                        lines = alt + [dates]
                    else:
                        lines.append(dates)
                else:
                    lines.append(dates)
            elif dates and gen >= DATES_SAME_LINE_FROM_GENERATION:
                # Aggressive: if dates exist and name is single-line with spaces,
                # try forcing a multi-line split using a tighter per-line budget
                if len(lines) == 1 and " " in name:
                    forced_max = max(3, int(max_chars / 3))
                    alt = split_name(name, forced_max)
                    if len(alt) > 1:
                        # put dates on their own line to avoid overflow
                        lines = alt + [dates]
                    else:
                        if len(lines[-1]) + 1 + len(dates) <= max_chars:
                            lines[-1] += " " + dates
                        else:
                            lines.append(dates)
                else:
                    # Try to fit dates on same line or separate line
                    if len(lines[-1]) + 1 + len(dates) <= max_chars:
                        lines[-1] += " " + dates
                    else:
                        lines.append(dates)

            # Check if we are in the bottom half of the circle
            is_bottom_half = 0 < mid < 180

            margin = 1 if gen >= 4 else 3
            # If sector is narrow or generation is deep, try to force a multi-line split
            if len(lines) == 1 and " " in name and (angle < 30 or gen >= 4):
                try_max = max(3, int(max_chars / 2))
                alt = split_name(name, try_max)
                if len(alt) > 1:
                    lines = alt
                    max_line = max(len(line) for line in lines)
                    font = font_for(max_line, available, gen)

            # compute sector (arc) width to estimate if text will overflow visually
            sector_width = math.radians(angle) * rm

            # If dates cause overflow on a single-line name, or name is wider than arc, try a more aggressive split
            if dates and len(lines) == 1 and (
                len(lines[0]) + 1 + len(dates) > max_chars or len(lines[0]) > max_chars * 0.7
                or (len(lines[0]) * font * 0.58) > sector_width * 0.9
            ):
                alt = split_name(name, max(3, int(max_chars / 2)))
                if len(alt) > 1:
                    # place dates on their own line if they still don't fit
                    if len(alt) < 3:
                        alt.append(dates)
                    else:
                        # if already 3 lines, try to append dates to the last line if it fits,
                        # otherwise keep dates separate (4th line is undesirable)
                        if len(alt[-1]) + 1 + len(dates) <= max_chars:
                            alt[-1] += " " + dates
                        else:
                            alt = alt[:2] + [alt[2] + ' ' + dates] if len(alt) >= 3 else alt + [dates]
                    lines = alt
                    max_line = max(len(line) for line in lines)
                    font = font_for(max_line, available, gen)
            for i, line in enumerate(lines):
                if is_bottom_half:
                    # In bottom half, text is drawn counter-clockwise (a1 to a0).
                    # Tops of letters point towards the center, so the first line (i = 0)
                    # should be closer to the center (smaller radius).
                    rr = rm - ((len(lines) - 1) / 2 - i) * font * 1.25
                    start_angle, end_angle = a1 - margin, a0 + margin
                else:
                    # In top half, text is drawn clockwise (a0 to a1).
                    # Tops of letters point outwards, so the first line (i = 0)
                    # should be further from the center (larger radius).
                    rr = rm + ((len(lines) - 1) / 2 - i) * font * 1.25
                    start_angle, end_angle = a0 + margin, a1 - margin

                pid = f"p{path_counter}"
                path_counter += 1
                defs.append(f'<path id="{pid}" d="{arc_path(cx, cy, rr, start_angle, end_angle)}"/>')
                svg.append(
                    f'<text font-size="{font:.1f}">'
                    f'<textPath href="#{pid}" startOffset="50%" text-anchor="middle">'
                    f'{html.escape(line)}'
                    f'</textPath></text>'
                )
        else:
            # Radial text for deeper generations - only render if person exists
            if person:
                available = RING_WIDTH * 0.95
                font = font_for(name, available, gen)
                max_chars = max(5, int(available / (font * 0.55)))
                lines = split_text(name, max_chars)
                
                # Add dates on separate line for earlier generations, or same line if it fits
                if dates:
                    if gen < DATES_SAME_LINE_FROM_GENERATION:
                        lines.append(dates)
                    else:
                        if len(lines[-1]) + 1 + len(dates) <= max_chars:
                            lines[-1] += " " + dates
                        else:
                            lines.append(dates)

                # Only split if the stacked lines fit within the sector's arc width
                sector_width = math.radians(angle) * rm
                if len(lines) > 1 and (len(lines) * font * 1.2) > sector_width:
                    lines = [name]
                    if dates:
                        lines.append(dates)

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
    father = person.get("father") if person else None
    mother = person.get("mother") if person else None

    # Always recurse for both slots up to max_generation
    path_counter = render_person(svg, defs, father, gen + 1, a0, mid, cx, cy, path_counter, max_generation)
    path_counter = render_person(svg, defs, mother, gen + 1, mid, a1, cx, cy, path_counter, max_generation)

    return path_counter


def generate_svg(root):
    depth = max_depth(root)
    # Calculate margin circle radius (outermost element)
    margin_radius = CENTER_RADIUS + max(0, depth - 1) * RING_WIDTH + RING_WIDTH / 3
    # SVG size must fit margin circle plus padding
    radius = margin_radius + PADDING
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
        //fill: #f7f7f7;
        fill: #ffffff;
        stroke: #333;
        stroke-width: 2;
    }}
    .sector {{
        // fill: #f7f7f7;
        fill: #ffffff;
        stroke: #bbb;
        stroke-width: 1.5;
    }}
</style>
''')

    render_person(svg, defs, root, 0, 0, 360, cx, cy, 0, depth - 1)

    # Add a margin circle at 1/3 sector width beyond the last sector
    # svg.append(f'<circle cx="{cx}" cy="{cy}" r="{margin_radius:.2f}" fill="none" stroke="#ccc" stroke-width="1"/>')

    if defs:
        svg.insert(1, "<defs>\n" + "\n".join(defs) + "\n</defs>")

    svg.append("</svg>")
    return "\n".join(svg)


def main():
    if len(sys.argv) != 3:
        print("Usage: python genearose.py input.json|input.yml output.svg")
        sys.exit(1)

    root = load_tree(sys.argv[1])
    svg = generate_svg(root)
    Path(sys.argv[2]).write_text(svg, encoding="utf-8")


if __name__ == "__main__":
    main()
