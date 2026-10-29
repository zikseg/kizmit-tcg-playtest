"""Movement and turn diagrams for the TCG playtest kit (black & white).

Reachable squares are COMPUTED from the movement rules (the same rules
simulate.py plays), never drawn by hand, so a diagram can't contradict the
rules.  build_kit.py calls movement_page() and turn_page().

Grid legend, one character per square:
    .  open ground          r  rough ground (Forest / Mountain / Marsh)
    i  your ink, open       _  gap (no card here)
    P  you                  Q  you, standing on your ink
    O  opponent             F  claimable land (open)
"""
DIRS8 = [(dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if (dx, dy) != (0, 0)]
DIAG = [(1, 1), (1, -1), (-1, 1), (-1, -1)]
CELL = 6.0   # mm per square


class Grid:
    def __init__(self, rows):
        self.rows = rows
        self.h, self.w = len(rows), len(rows[0])
        self.cells, self.rough, self.ink, self.claim = set(), set(), set(), set()
        self.me = self.opp = None
        for y, row in enumerate(rows):
            for x, ch in enumerate(row):
                if ch == "_":
                    continue
                self.cells.add((x, y))
                if ch == "r":
                    self.rough.add((x, y))
                if ch in "iQ":
                    self.ink.add((x, y))
                if ch == "F":
                    self.claim.add((x, y))
                if ch in "PQ":
                    self.me = (x, y)
                if ch == "O":
                    self.opp = (x, y)

    def open(self, c):
        return c in self.cells and c != self.opp


# ── Movement rules (mirror simulate.py) ──────────────────────────────────────
def king(g, steps, passes=0, ignore_rough=False):
    seen = {(g.me, passes)}
    frontier = [(g.me, passes)]
    out = set()
    for _ in range(steps):
        nxt = []
        for c, left in frontier:
            for dx, dy in DIRS8:
                n = (c[0] + dx, c[1] + dy)
                if not g.open(n) or n == g.me:
                    continue
                out.add(n)
                if ignore_rough or n not in g.rough:
                    st = (n, left)
                elif left:
                    st = (n, left - 1)
                else:
                    continue
                if st not in seen:
                    seen.add(st)
                    nxt.append(st)
        frontier = nxt
    return out


def blink(g):
    x, y = g.me
    return {(x + 2 * dx, y + 2 * dy) for dx, dy in DIRS8 if g.open((x + 2 * dx, y + 2 * dy))}


def runs(g, dirs, length, exact):
    out = set()
    for dx, dy in dirs:
        c = g.me
        for k in range(1, length + 1):
            n = (c[0] + dx, c[1] + dy)
            if not g.open(n):
                break
            c = n
            stopped = n in g.rough
            if not exact or k == length or stopped:
                out.add(c)
            if stopped:
                break
    return out


def burst(g):
    bonus = 1 if g.me in g.ink else 0
    return king(g, 1 + bonus) | runs(g, DIRS8, 3 + bonus, exact=True)


def glide(g):
    bonus = 1 if g.me in g.ink else 0
    straight = {(g.me[0] + dx, g.me[1] + dy) for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]}
    return runs(g, DIAG, 3 + bonus, exact=False) | {c for c in straight if g.open(c)}


# "Nominal" squares: where the pattern would reach on an empty board.  Any
# nominal square that exists but isn't reachable gets an X.
def nominal_king(g, steps):
    x, y = g.me
    return {(x + dx, y + dy) for dx in range(-steps, steps + 1) for dy in range(-steps, steps + 1)
            if (dx, dy) != (0, 0)}


def nominal_burst(g):
    x, y = g.me
    bonus = 1 if g.me in g.ink else 0
    return nominal_king(g, 1 + bonus) | {(x + dx * (3 + bonus), y + dy * (3 + bonus)) for dx, dy in DIRS8}


def nominal_glide(g):
    x, y = g.me
    bonus = 1 if g.me in g.ink else 0
    out = {(x + dx * k, y + dy * k) for dx, dy in DIAG for k in range(1, 4 + bonus)}
    return out | {(x + dx, y + dy) for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]}


def nominal_blink(g):
    x, y = g.me
    return {(x + 2 * dx, y + 2 * dy) for dx, dy in DIRS8}


# ── Drawing ──────────────────────────────────────────────────────────────────
INK_DISC = '<circle cx="{cx}" cy="{cy}" r="1.1" fill="#fff" stroke="#000" stroke-width="0.35"/>'


def draw(g, reach=(), crosses=(), arrows=(), tokens=(), zone=(), extra="", cards=(), ghosts=()):
    w, h = g.w * CELL, g.h * CELL
    out = [f'<svg viewBox="-1 -1 {w + 2} {h + 2}" style="width:{w + 2}mm;height:{h + 2}mm" class="dg">',
           '<defs><pattern id="hatch" width="1.6" height="1.6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
           '<line x1="0" y1="0" x2="0" y2="1.6" stroke="#000" stroke-width="0.35"/></pattern>'
           '<marker id="ah" viewBox="0 0 6 6" refX="5" refY="3" markerWidth="4" markerHeight="4" orient="auto">'
           '<path d="M0,0 L6,3 L0,6 Z" fill="#000"/></marker></defs>']
    for y in range(g.h):
        for x in range(g.w):
            X, Y = x * CELL, y * CELL
            if (x, y) not in g.cells:
                out.append(f'<rect x="{X + 0.6}" y="{Y + 0.6}" width="{CELL - 1.2}" height="{CELL - 1.2}" fill="none" '
                           f'stroke="#999" stroke-width="0.25" stroke-dasharray="0.8 0.8"/>')
                continue
            fill = "url(#hatch)" if (x, y) in g.rough else "#fff"
            out.append(f'<rect x="{X}" y="{Y}" width="{CELL}" height="{CELL}" fill="{fill}" stroke="#000" stroke-width="0.3"/>')
            if (x, y) in zone:
                out.append(f'<rect x="{X + 0.5}" y="{Y + 0.5}" width="{CELL - 1}" height="{CELL - 1}" fill="none" '
                           f'stroke="#000" stroke-width="0.45" stroke-dasharray="0.6 0.6"/>')
            if (x, y) in g.ink:
                out.append(INK_DISC.format(cx=X + 1.6, cy=Y + 1.6))
            if (x, y) in g.claim:
                out.append(f'<path d="M{X + 3.8},{Y + 5} V{Y + 1} H{X + 5.4} L{X + 4.8},{Y + 1.8} L{X + 5.4},{Y + 2.6} H{X + 3.8}" '
                           f'fill="#fff" stroke="#000" stroke-width="0.35"/>')
    for a, b in cards:   # a land card: one domino, two squares
        x0, y0 = min(a[0], b[0]) * CELL, min(a[1], b[1]) * CELL
        cw = (abs(a[0] - b[0]) + 1) * CELL
        ch = (abs(a[1] - b[1]) + 1) * CELL
        out.append(f'<rect x="{x0 + 0.4}" y="{y0 + 0.4}" width="{cw - 0.8}" height="{ch - 0.8}" fill="none" '
                   f'stroke="#000" stroke-width="0.9"/>')
    for (x, y), label in ghosts:   # where you end up
        cx, cy = x * CELL + CELL / 2, y * CELL + CELL / 2
        out.append(f'<circle cx="{cx}" cy="{cy}" r="2.4" fill="#fff" stroke="#000" stroke-width="0.5" stroke-dasharray="0.9 0.6"/>'
                   f'<text x="{cx}" y="{cy + 1.1}" font-size="3" text-anchor="middle" font-weight="bold">{label}</text>')
    for (x, y) in reach:
        out.append(f'<circle cx="{x * CELL + CELL / 2}" cy="{y * CELL + CELL / 2}" r="1.25" fill="#000"/>')
    for (x, y) in crosses:
        X, Y = x * CELL, y * CELL
        out.append(f'<path d="M{X + 1.7},{Y + 1.7} L{X + 4.3},{Y + 4.3} M{X + 4.3},{Y + 1.7} L{X + 1.7},{Y + 4.3}" stroke="#000" stroke-width="0.7"/>')
    for (x, y), label in tokens:
        out.append(f'<circle cx="{x * CELL + CELL / 2}" cy="{y * CELL + CELL / 2}" r="2.1" fill="#fff" stroke="#000" stroke-width="0.45"/>'
                   f'<text x="{x * CELL + CELL / 2}" y="{y * CELL + CELL / 2 + 1.1}" font-size="3" text-anchor="middle" font-weight="bold">{label}</text>')
    for (a, b) in arrows:
        x1, y1 = a[0] * CELL + CELL / 2, a[1] * CELL + CELL / 2
        x2, y2 = b[0] * CELL + CELL / 2, b[1] * CELL + CELL / 2
        d = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
        ux, uy = (x2 - x1) / d, (y2 - y1) / d
        x1, y1 = x1 + ux * 2.6, y1 + uy * 2.6     # leave the start marker's edge
        x2, y2 = x2 - ux * 3.0, y2 - uy * 3.0     # stop at the end marker's edge
        out.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#000" stroke-width="0.55" marker-end="url(#ah)"/>')
    for who, c, shape in (("P", g.me, "circle"), ("O", g.opp, "square")):
        if not c:
            continue
        cx, cy = c[0] * CELL + CELL / 2, c[1] * CELL + CELL / 2
        if shape == "circle":
            out.append(f'<circle cx="{cx}" cy="{cy}" r="2.4" fill="#fff" stroke="#000" stroke-width="0.6"/>')
        else:
            out.append(f'<rect x="{cx - 2.2}" y="{cy - 2.2}" width="4.4" height="4.4" fill="#fff" stroke="#000" stroke-width="0.6"/>')
        out.append(f'<text x="{cx}" y="{cy + 1.1}" font-size="3" text-anchor="middle" font-weight="bold">{who}</text>')
    out.append(extra)
    out.append('</svg>')
    return "".join(out)


def panel(title, svg, caption):
    return f'<div class="dg-panel"><div class="dg-title">{title}</div>{svg}<div class="dg-cap">{caption}</div></div>'


def moves(g, reach, nominal):
    return draw(g, reach=reach, crosses={c for c in nominal if c in g.cells and c not in reach and c != g.me})


LEGEND = ('<div class="dg-legend">'
          '<span><b>&#9679;</b> can end the move here</span>'
          '<span><b>&#10005;</b> in range, but blocked</span>'
          '<span><span class="lg-hatch"></span> rough (Forest / Mountain / Marsh)</span>'
          '<span><span class="lg-gap"></span> gap: no card</span>'
          '<span>&#9675; small corner circle = your ink</span>'
          '<span><b>P</b> you &nbsp; <b>&#9633;O</b> opponent</span>'
          '</div>')


def movement_page():
    panels = []

    g = Grid([".......", ".......", "..r....", "...P...", ".......", ".......", "......."])
    panels.append(panel("Guard: 1 square", moves(g, king(g, 1), nominal_king(g, 1)),
                        "Any of the 8 neighbours. Stepping into rough terrain is fine: it just ends the move."))

    g = Grid([".......", "...r...", ".......", "...Q...", ".......", ".._....", "......."])
    panels.append(panel("Ink bonus: +1 square", moves(g, king(g, 2), nominal_king(g, 2)),
                        "Start a move on your own ink and it goes 1 square further. Here a Guard moves 2."))

    g = Grid([".......", ".......", "..rrr..", "...P...", ".......", ".......", "......."])
    panels.append(panel("Rough terrain ends your move", moves(g, king(g, 2), nominal_king(g, 2)),
                        "Stride (2 squares). You can enter the rough squares, but your move stops there, "
                        "so everything behind them is out of reach this move."))

    g = Grid([".......", ".......", "..rrr..", "...P...", ".......", ".......", "......."])
    panels.append(panel("Ambler's Steady trait", moves(g, king(g, 2, passes=1), nominal_king(g, 2)),
                        "Same board: the first rough square each turn doesn't stop an Ambler, so the far row opens up."))

    g = Grid([".......", ".r..._.", "...__..", ".._P...", "...O...", ".......", "......."])
    nb = nominal_blink(g)
    panels.append(panel("Blink: exactly 2 away", draw(g, reach=blink(g), crosses={c for c in nb if c not in g.cells}),
                        "Teleports over gaps, rough terrain and even the opponent. It can't land on a gap (top right)."))

    g = Grid([".......", "...r...", ".......", "...P._.", ".......", ".O.....", "......."])
    panels.append(panel("Burst: 1 square, or charge exactly 3", moves(g, burst(g), nominal_burst(g)),
                        "Rough terrain ends the charge early (up). A gap (right) or the opponent (down-left) blocks the line."))

    g = Grid([".......", ".r.....", ".......", "...P...", ".......", "....._.", "......."])
    panels.append(panel("Glide: diagonals, or 1 straight", moves(g, glide(g), nominal_glide(g)),
                        "Up to 3 diagonally. Rough ends it (up-left); a gap blocks it (down-right). Or step 1 square straight."))

    g = Grid([".......", "..__...", ".._....", ".P_O...", ".._....", ".......", "......."])
    panels.append(panel("Gaps and the opponent", moves(g, king(g, 2), nominal_king(g, 2)),
                        "Stride (2). Gaps can't be crossed (only Blink jumps them), and you never move onto the opponent."))

    return f'<h1>How movement works</h1>{LEGEND}<div class="dg-grid">{"".join(panels)}</div>'


def turn_page():
    panels = []

    g = Grid([".......", "...F...", "...F...", ".P.....", ".......", ".......", "......."])
    panels.append(panel("1. Move, then claim",
                        draw(g, arrows=[((1, 3), (3, 2))], ghosts=[((3, 2), "P")], tokens=[((3, 1), "1")],
                             cards=[((3, 1), (3, 2))]),
                        "Action 1: move onto a claimable land (flag; the thick outline is one card, two squares). "
                        "Action 2: claim it: your token covers the whole card."))

    g = Grid([".......", ".......", "..P....", "..F....", ".......", ".......", "......."])
    g.claim.add((2, 2))
    panels.append(panel("2. Claim, then leave",
                        draw(g, arrows=[((2, 2), (4, 4))], ghosts=[((4, 4), "P")], tokens=[((2, 3), "1")],
                             cards=[((2, 2), (2, 3))]),
                        "Claiming first and then moving away is allowed. The token stays, and at the start of "
                        "your next turn it scores 1 holding point."))

    g = Grid([".......", ".......", ".......", "..P....", ".......", ".O.....", "......."])
    zone = {(x, y) for x in range(7) for y in range(7) if max(abs(x - 1), abs(y - 5)) <= 2}
    panels.append(panel("3. Leaving someone's reach",
                        draw(g, arrows=[((2, 3), (4, 1))], zone=zone, ghosts=[((3, 2), "P")], crosses=[(4, 1)]),
                        "Your opponent holds Snapvine (range 2, dotted squares). You try to move from inside its range "
                        "to the &#10005;. Leaving triggers it: they cast it as a reaction, and your move ends on the next "
                        "square (dashed P). One reaction per opponent turn."))

    g = Grid([".......", "...O...", "..._...", ".......", "...P...", ".......", "......."])
    extra = (f'<line x1="{3 * CELL + CELL / 2}" y1="{4 * CELL + CELL / 2}" x2="{3 * CELL + CELL / 2}" y2="{1 * CELL + CELL / 2}" '
             f'stroke="#000" stroke-width="0.5" stroke-dasharray="1 0.8"/>')
    panels.append(panel("4. Range and line of sight",
                        draw(g, extra=extra),
                        "Range counts squares (a diagonal counts as 1): O is 3 away. Nothing blocks line of sight "
                        "yet, so a range-3 spell hits O across the gap. Gaps still block movement."))

    return (f'<h1>A turn, step by step</h1>'
            f'<p class="dg-intro">Each turn: draw 1 card, score 1 point per land holding your token, then take '
            f'<b>2 actions</b> in any mix: <b>move</b>, <b>gather</b> ink, <b>rest</b> (swap a card from hand for the top of your deck), <b>claim</b>, '
            f'or <b>cast</b> a sorcery. <b>Clearing</b> an enemy token you stand on is free.</p>'
            f'<div class="dg-grid">{"".join(panels)}</div>')


CSS = '''
.dg-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 2mm 6mm; }
.dg-panel { break-inside: avoid; }
.dg-title { font-weight: bold; font-size: 10pt; margin-bottom: 1mm; }
.dg-cap { font-size: 8pt; line-height: 1.25; margin-top: 0.6mm; }
.dg { display: block; }
.dg text { font-family: "Segoe UI", Arial, sans-serif; }
.dg-legend { display: flex; flex-wrap: wrap; gap: 1mm 5mm; font-size: 8pt; margin: 0 0 3mm; padding: 1.5mm 2mm;
  border: 0.3mm solid #000; }
.lg-hatch { display: inline-block; width: 3.5mm; height: 3.5mm; vertical-align: middle; border: 0.3mm solid #000;
  background: repeating-linear-gradient(45deg, #000 0 0.35mm, #fff 0.35mm 1.1mm); }
.lg-gap { display: inline-block; width: 3.5mm; height: 3.5mm; vertical-align: middle; border: 0.3mm dashed #999; }
.dg-intro { font-size: 9.5pt; }
'''
