#!/usr/bin/env python3
"""Двигател за кръгове на подово отопление.

Вход: контур на стаята (полигон, метри), разстояние между тръбите, максимална
дължина на кръг. Изход: SVG с номерирани кръгове + списък с дължини и материали.

Алгоритъм: сканиращи линии (серпентина) с отстъп от стените, заобикаляне на
препятствия (колони) чрез изваждане от полигона, рязане на кръгове по дължина.
Само стандартна библиотека.
"""
import math
import sys

WALL_GAP = 0.15      # отстъп от стената, м
SPACING = 0.10       # стъпка между тръбите, м — стандарт за София
MAX_LOOP = 90.0      # максимална дължина на кръг, м
MANIFOLD_AT = None   # (x, y) — къде е колекторът; None = долен ляв ъгъл


# ─────────────── геометрия ───────────────
def poly_area(poly):
    s = 0.0
    for i in range(len(poly)):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % len(poly)]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2


def bbox(poly):
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    return min(xs), min(ys), max(xs), max(ys)


def inset_rect(x0, y0, x1, y1, g):
    return [(x0 + g, y0 + g), (x1 - g, y0 + g), (x1 - g, y1 - g), (x0 + g, y1 - g)]


def segments_at(poly, y):
    """Хоризонтални отсечки вътре в полигона при височина y (even-odd)."""
    xs = []
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            t = (y - y1) / (y2 - y1)
            xs.append(x1 + t * (x2 - x1))
    xs.sort()
    return [(xs[i], xs[i + 1]) for i in range(0, len(xs) - 1, 2)]


def subtract_rect(poly, rect):
    """Грубо изваждане на правоъгълник (колона) — реже отсечките по-късно."""
    return rect


# ─────────────── серпентина ───────────────
def serpentine(poly, rects, spacing=SPACING, gap=WALL_GAP):
    """Връща списък от полилинии (кръгове) в метри."""
    x0, y0, x1, y1 = bbox(poly)
    room = inset_rect(x0, y0, x1, y1, gap)
    ys = []
    y = room[0][1] + spacing / 2
    while y < room[2][1] - spacing / 2 + 1e-9:
        ys.append(round(y, 4))
        y += spacing

    # за всяка линия — отсечки, после свързваме в блуждаеща пътека
    rows = []
    for y in ys:
        segs = segments_at(poly, y)
        # махаме препятствията
        clean = []
        for a, b in segs:
            pieces = [(a, b)]
            for (rx0, ry0, rx1, ry1) in rects:
                if ry0 <= y <= ry1:
                    nxt = []
                    for pa, pb in pieces:
                        if pb <= rx0 or pa >= rx1:
                            nxt.append((pa, pb))
                        else:
                            if pa < rx0:
                                nxt.append((pa, min(rx0, pb)))
                            if pb > rx1:
                                nxt.append((max(rx1, pa), pb))
                    pieces = [(pa, pb) for pa, pb in nxt if pb - pa > 0.02]
            clean.extend(pieces)
        # ограничаваме в рамките на отстъпа
        clipped = []
        for a, b in clean:
            a2, b2 = max(a, room[0][0]), min(b, room[2][0])
            if b2 - a2 > 0.02:
                clipped.append((a2, b2))
        if clipped:
            rows.append((y, clipped))

    # свързване: редуваме посоката, скачаме между отсечките по права линия
    loops, cur, cur_len = [], [], 0.0
    flip = False
    for y, segs in rows:
        order = list(reversed(segs)) if flip else segs
        for a, b in order:
            p1, p2 = (a, y), (b, y)
            if flip:
                p1, p2 = p2, p1
            if cur:
                d = math.dist(cur[-1], p1)
                if cur_len + d > MAX_LOOP and len(cur) > 2:
                    loops.append(cur)
                    cur, cur_len = [], 0.0
                else:
                    cur.append(p1)
                    cur_len += d
            if not cur:
                cur = [p1]
            cur.append(p2)
            cur_len += abs(p2[0] - p1[0])
        flip = not flip
    if len(cur) > 1:
        loops.append(cur)
    return loops


def loop_length(pts):
    return sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))


# ─────────────── SVG ───────────────
COLORS = ["#e74c3c", "#2980b9", "#27ae60", "#8e44ad", "#d35400", "#16a085",
          "#c0392b", "#2c3e50", "#f39c12", "#7f8c8d"]


def render(poly, rects, loops, path, scale=90):
    x0, y0, x1, y1 = bbox(poly)
    m = 0.5
    w = (x1 - x0 + 2 * m) * scale
    h = (y1 - y0 + 2 * m) * scale

    def X(x):
        return (x - x0 + m) * scale

    def Y(y):
        return h - (y - y0 + m) * scale

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.0f}" height="{h:.0f}" '
           f'viewBox="0 0 {w:.0f} {h:.0f}">',
           '<rect width="100%" height="100%" fill="#ffffff"/>']
    # стая
    pts = " ".join(f"{X(x):.1f},{Y(y):.1f}" for x, y in poly)
    out.append(f'<polygon points="{pts}" fill="#f7f9fb" stroke="#111" stroke-width="3"/>')
    # препятствия
    for (rx0, ry0, rx1, ry1) in rects:
        out.append(f'<rect x="{X(rx0):.1f}" y="{Y(ry1):.1f}" width="{(rx1-rx0)*scale:.1f}" '
                   f'height="{(ry1-ry0)*scale:.1f}" fill="#dfe6ec" stroke="#111" stroke-width="1.5"/>')
    # кръгове
    for i, lp in enumerate(loops):
        d = "M " + " L ".join(f"{X(x):.1f} {Y(y):.1f}" for x, y in lp)
        out.append(f'<path d="{d}" fill="none" stroke="{COLORS[i % len(COLORS)]}" '
                   f'stroke-width="2.4" stroke-linejoin="round"/>')
        mx, my = lp[0]
        out.append(f'<circle cx="{X(mx):.1f}" cy="{Y(my):.1f}" r="9" fill="{COLORS[i % len(COLORS)]}"/>')
        out.append(f'<text x="{X(mx):.1f}" y="{Y(my)+4:.1f}" font-size="11" fill="#fff" '
                   f'text-anchor="middle" font-family="sans-serif">{i+1}</text>')
    # мащаб
    out.append(f'<line x1="{X(x0):.1f}" y1="{Y(y0)-18:.1f}" x2="{X(x0)+scale:.1f}" '
               f'y2="{Y(y0)-18:.1f}" stroke="#111" stroke-width="2"/>')
    out.append(f'<text x="{X(x0):.1f}" y="{Y(y0)-24:.1f}" font-size="12" '
               f'font-family="sans-serif">1 m</text>')
    out.append('</svg>')
    open(path, "w", encoding="utf-8").write("\n".join(out))


def main():
    poly = [(0, 0), (5.2, 0), (5.2, 4.0), (0, 4.0)]
    obstacles = [(3.4, 2.6, 4.2, 3.4)]        # колона 0.8×0.8
    loops = serpentine(poly, obstacles)
    area = poly_area(poly) - sum((b[2] - b[0]) * (b[3] - b[1]) for b in obstacles)
    lengths = [loop_length(l) for l in loops]
    print(f"Стая: {area:.1f} m² · стъпка {SPACING*100:.0f} см")
    for i, L in enumerate(lengths, 1):
        print(f"  кръг {i}: {L:.1f} м")
    print(f"  общо тръба: {sum(lengths):.1f} м · кръгове: {len(loops)}")
    print(f"  тръба на m²: {sum(lengths)/area:.2f} м/м²")
    man = len(loops) + 2
    print(f"  колектор: {man} извода (с 2 за захранване/връщане)")
    render(poly, obstacles, loops, "/home/ivan/abc-heating-ink/shots/kragove-primer.svg")
    print("SVG: shots/kragove-primer.svg")


if __name__ == "__main__":
    main()
