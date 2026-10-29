"""Build the Kizmit TCG paper-playtest kit (black & white, colourable).

    python build_kit.py            -> writes kit.html and TCG_Playtest_Kit.pdf

The card list below mirrors TCG_DESIGN.md §10.  Edit the data here, re-run,
re-print.  Rendering uses headless Chrome's print-to-PDF so card sizes are
exact millimetres: print at 100% / "actual size", never "fit to page".
"""
import hashlib
import html
import json

import diagrams
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# ─── Inks ─────────────────────────────────────────────────────────────────────
# Same shape-per-ink as the video game's ElementGlyph, so a B&W print still
# tells the nine inks apart (hearts and diamonds, not just red).
INK_SHAPE = {
    "White": "square", "Red": "triangle", "Orange": "diamond",
    "Yellow": "spark", "Green": "disc", "Blue": "eye",
    "Indigo": "crescent", "Purple": "hex", "Pink": "heart",
    "Wild": "wild",
}
INK_LETTER = {"White": "W", "Red": "R", "Orange": "O", "Yellow": "Y", "Green": "G",
              "Blue": "B", "Indigo": "I", "Purple": "P", "Pink": "K"}


def glyph(ink, size_mm, stroke=1.6):
    """Outline SVG of an ink's shape, white-filled so it can be coloured in."""
    s = INK_SHAPE[ink]
    sw = stroke
    common = f'fill="#fff" stroke="#000" stroke-width="{sw}" stroke-linejoin="round"'
    shapes = {
        "square": f'<rect x="12" y="12" width="76" height="76" {common}/>',
        "triangle": f'<polygon points="50,8 93,88 7,88" {common}/>',
        "diamond": f'<polygon points="50,5 95,50 50,95 5,50" {common}/>',
        "spark": f'<polygon points="50,4 61,39 96,50 61,61 50,96 39,61 4,50 39,39" {common}/>',
        "disc": f'<circle cx="50" cy="50" r="42" {common}/>',
        "eye": f'<path d="M5,50 Q50,4 95,50 Q50,96 5,50 Z" {common}/>'
               f'<circle cx="50" cy="50" r="14" fill="#fff" stroke="#000" stroke-width="{sw}"/>',
        "crescent": f'<path d="M62,8 A42,42 0 1 0 62,92 A48,48 0 0 1 62,8 Z" {common}/>',
        "hex": f'<polygon points="50,5 89,27 89,73 50,95 11,73 11,27" {common}/>',
        "heart": f'<path d="M50,90 C10,62 4,40 18,24 C30,11 46,16 50,30 C54,16 70,11 82,24 C96,40 90,62 50,90 Z" {common}/>',
        "wild": f'<circle cx="50" cy="50" r="42" fill="#fff" stroke="#000" stroke-width="{sw}" stroke-dasharray="7 5"/>'
                f'<path d="M50,22 V78 M22,50 H78 M30,30 L70,70 M70,30 L30,70" stroke="#000" stroke-width="{sw}"/>',
    }
    return (f'<svg class="glyph" viewBox="0 0 100 100" style="width:{size_mm}mm;height:{size_mm}mm">'
            f'{shapes[s]}</svg>')


def cost_html(cost):
    """cost = (generic:int, [inks]).  Generic is a number in a rounded square."""
    generic, pips = cost
    parts = []
    if generic:
        parts.append(f'<span class="generic">{generic}</span>')
    for ink in pips:
        parts.append(f'<span class="pip">{glyph(ink, 4.6, 7)}</span>')
    if not parts:
        parts.append('<span class="generic">0</span>')
    return "".join(parts)


# ─── Card data ────────────────────────────────────────────────────────────────
# Everything below comes from Design/tcg/card_data.json, the canonical card
# table (shared with simulate.py and, eventually, the Godot game).  Edit the
# JSON, not this file.  The tuple shapes are what the renderers expect:
#   spell:   (id, name, copies, (generic, [pips]), speed, type, restriction, range_text, trigger, text, art_ink)
#   terrain: (ink_a, ink_b, terrain, claimable, star_on)   star_on: None / 0 / 1
DATA_PATH = os.path.join(HERE, "..", "tcg", "card_data.json")
with open(DATA_PATH, encoding="utf-8") as _f:
    DATA = json.load(_f)
# Printed on every card and the cover so mixed printouts show at the table.
# Hashes the parsed data, not the file bytes, so line endings don't change it.
KIT_VERSION = hashlib.sha1(json.dumps(DATA, sort_keys=True).encode()).hexdigest()[:6]

RULES = DATA["rules"]
HOLDING_TARGET = RULES["holding_target"]
ROUGH = {t for t, v in DATA["terrains"].items() if v["rough"]}
RACES = DATA["races"]
RACE_HP = {r: v["hp"] for r, v in RACES.items()}
RACE_TRAIT = {r: (v["trait"]["name"], v["trait"]["text"]) for r, v in RACES.items()}
RACE_HOLD_BONUS = {r: v["trait"]["hold_bonus"] for r, v in RACES.items() if "hold_bonus" in v["trait"]}
RACE_HOLD_MIN = {r: v["trait"]["hold_min_lands"] for r, v in RACES.items() if "hold_min_lands" in v["trait"]}
SPELLS = {sp["id"]: sp for sp in DATA["spells"]}
_c = DATA["centre_land"]
CENTRE = [(_c["inks"][0], _c["inks"][1], _c["terrain"], _c["claimable"], None)]


def _spell_tuple(cid, copies):
    sp = SPELLS[cid]
    r = sp["restriction"]
    restr = "" if not r else ("Race: " if r["kind"] == "race" else "Signature: ") + r["value"]
    return (cid, sp["name"], copies, (sp["cost"]["generic"], list(sp["cost"]["pips"])), sp["speed"], sp["type"],
            restr, sp["range_text"], sp["trigger"] or "", sp["text"], sp["art_ink"])


CHARACTERS = {c["name"]: c for c in DATA["characters"]}
DECKS = {n: [_spell_tuple(cid, k) for cid, k in c["deck"]] for n, c in CHARACTERS.items()}
TERRAIN = {n: [(t["inks"][0], t["inks"][1], t["terrain"], t["claimable"], t["star"]) for t in c["terrain_half"]]
           for n, c in CHARACTERS.items()}
# Every character in the kit: (name, one-line role, deck, terrain half).
ROSTER = [(n, c["role"], DECKS[n], TERRAIN[n]) for n, c in CHARACTERS.items()]
ROSTER_TEXT = ", ".join(f"<b>{n}</b> ({role})" for n, role, _, _ in ROSTER)

# Legacy names (simulate.py and older scripts use them).
THORNBACK_DECK, SKITTERWISP_DECK, BRASSHORN_DECK = DECKS["Thornback"], DECKS["Skitterwisp"], DECKS["Brasshorn"]
VIGILUX_DECK, PETALSTEP_DECK = DECKS["Vigilux"], DECKS["Petalstep"]
THORNBACK_TERRAIN, SKITTERWISP_TERRAIN, BRASSHORN_TERRAIN = TERRAIN["Thornback"], TERRAIN["Skitterwisp"], TERRAIN["Brasshorn"]
VIGILUX_TERRAIN, PETALSTEP_TERRAIN = TERRAIN["Vigilux"], TERRAIN["Petalstep"]

# Construction rules, checked on every build so a bad edit to the JSON fails loudly.
for _n, _deck in DECKS.items():
    assert sum(c[2] for c in _deck) == RULES["deck_size"], f"{_n}: a spell deck is {RULES['deck_size']} cards"
    assert all(c[2] <= RULES["max_copies"] for c in _deck), f"{_n}: too many copies"
    assert all(c[2] == RULES["signature_copies"] for c in _deck if c[5] == "Signature"), f"{_n}: signature copies"
    _sheet = set(CHARACTERS[_n]["inks"])
    for c in _deck:
        assert set(c[3][1]) <= _sheet, f"{_n}: {c[1]} has an ink outside the sheet"
for _n, _half in TERRAIN.items():
    assert len(_half) == RULES["terrain_per_player"], f"{_n}: terrain half size"
    assert sum(1 for t in _half if t[4] is not None) == 1, f"{_n}: exactly one star card"
    assert 1 <= sum(1 for t in _half if t[3]) <= 2, f"{_n}: 1-2 claimable lands"

# ─── Doodles (line art to colour) ─────────────────────────────────────────────
DOODLE = {
    "Forest": '<path d="M10,40 L20,14 L30,40 Z M20,40 V46 M34,40 L44,8 L54,40 Z M44,40 V46 M58,40 L66,20 L74,40 Z M66,40 V46" />',
    "Mountain": '<path d="M2,46 L22,12 L34,30 L46,6 L72,46 Z M40,16 L46,6 L52,16" />',
    "Marsh": '<path d="M4,40 q8,-6 16,0 t16,0 t16,0 t16,0 M10,34 V14 M10,14 q3,-4 0,-8 M22,34 V20 M50,34 V12 M50,12 q-3,-4 0,-8 M62,34 V22" />',
    "Desert": '<path d="M2,44 Q20,24 38,44 M30,44 Q50,18 74,44 M58,14 m-7,0 a7,7 0 1,0 14,0 a7,7 0 1,0 -14,0" />',
    "Plains": '<path d="M6,44 l4,-12 l4,12 M12,44 l3,-8 l3,8 M30,44 l4,-14 l4,14 M36,44 l3,-9 l3,9 M54,44 l4,-12 l4,12 M60,44 l3,-7 l3,7" />',
    "Civilization": '<path d="M8,46 V26 L22,14 L36,26 V46 Z M18,46 V36 H26 V46 M42,46 V30 L54,20 L66,30 V46 Z M50,30 H58 V36 H50 Z" />',
}


def doodle(terrain, w_mm, h_mm):
    return (f'<svg class="doodle" viewBox="0 0 76 50" style="width:{w_mm}mm;height:{h_mm}mm">'
            f'<g fill="none" stroke="#000" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round">'
            f'{DOODLE[terrain]}</g></svg>')


FLAG = ('<svg viewBox="0 0 24 24" style="width:6.5mm;height:6.5mm"><path d="M5,22 V3 M5,4 H19 L15,9 L19,14 H5" '
        'fill="#fff" stroke="#000" stroke-width="1.8" stroke-linejoin="round"/></svg>')
STAR = ('<svg viewBox="0 0 24 24" style="width:7mm;height:7mm"><polygon points="12,1.5 15,9 23,9.3 16.8,14.2 '
        '19,22 12,17.4 5,22 7.2,14.2 1,9.3 9,9" fill="#fff" stroke="#000" stroke-width="1.6" stroke-linejoin="round"/></svg>')


def esc(s):
    return html.escape(s)


# ─── Art ──────────────────────────────────────────────────────────────────────
# Drop images into Design/tcg/art/ named by slot key (see build_decks.py's
# ART_SLOTS for every key and its size); a card with no file keeps its line art.
ART_DIR = os.path.normpath(os.path.join(HERE, "..", "tcg", "art"))
ART_EXTS = (".png", ".jpg", ".jpeg", ".webp")


def art_file(key):
    for ext in ART_EXTS:
        p = os.path.join(ART_DIR, key + ext)
        if os.path.exists(p):
            return p
    return None


def art_img(key, cls="art"):
    p = art_file(key) if key else None
    return f'<img class="{cls}" src="file:///{p.replace(os.sep, "/")}">' if p else ""


def prefix(name):
    """A character's card-id prefix (TB, SW, …), from its signature spell's id."""
    return CHARACTERS[name]["signature"].split("-")[0]


def land_key(owner, i):
    return "CENTRE" if owner is None else f"{prefix(owner)}-L{i + 1}"


# ─── Card renderers ───────────────────────────────────────────────────────────
def spell_card(c, owner):
    cid, name, copies, cost, speed, ctype, restr, rng, trig, effect, art_ink = c
    if art_file(cid):
        art = art_img(cid)
    elif ctype == "Signature":
        art = STAR.replace("7mm", "24mm")
    elif art_ink:
        art = glyph(art_ink, 24, 2.2)
    else:
        art = '<div class="art-hint">draw me</div>'
    restr_html = f'<div class="restr">{esc(restr)}</div>' if restr else ""
    trig_html = f'<div class="trig"><b>Trigger:</b> {esc(trig)}</div>' if trig else ""
    speed_note = ("Costs 1 action." if speed == "Sorcery" else "No action. Max one reaction per opponent turn.")
    return f'''
<div class="card spell {speed.lower()}">
  <div class="sp-head"><div class="sp-name">{esc(name)}</div><div class="sp-cost">{cost_html(cost)}</div></div>
  <div class="sp-type">{speed.upper()} · {esc(ctype)}</div>
  <div class="sp-art">{art}</div>
  {restr_html}
  <div class="sp-range">{esc(rng)}</div>
  {trig_html}
  <div class="sp-effect">{esc(effect)}</div>
  <div class="sp-note">{speed_note}</div>
  <div class="foot">KIZMIT PLAYTEST {KIT_VERSION} · {cid} · {esc(owner)} · {copies}× in deck</div>
</div>'''


def blank_spell():
    return '''
<div class="card spell blank">
  <div class="sp-head"><div class="sp-name line"></div><div class="sp-cost"></div></div>
  <div class="sp-type">SORCERY / INSTANT · ________</div>
  <div class="sp-art"><div class="art-hint">design your own</div></div>
  <div class="sp-range">Range ______</div>
  <div class="sp-effect lines"></div>
  <div class="foot">KIZMIT PLAYTEST {KIT_VERSION} · BLANK</div>
</div>'''


def slot_card(kind, title, body_html, big_html=""):
    return f'''
<div class="card slot">
  <div class="slot-kind">{kind}</div>
  <div class="slot-title">{title}</div>
  <div class="slot-big">{big_html}</div>
  <div class="slot-body">{body_html}</div>
  <div class="foot">KIZMIT PLAYTEST {KIT_VERSION} · SHEET SLOT</div>
</div>'''


def race_card(race, pattern, move_text, hp, trait):
    tname, ttext = trait
    body = (f'<p><b>Movement — {pattern}</b><br>{move_text}</p>'
            f'<p class="hp">HP {hp}</p>'
            f'<p><b>Trait — {tname}</b><br>{ttext}</p>')
    return slot_card("RACE", f"{race}<span class='ph'>placeholder name</span>", body,
                     art_img(f"RACE-{race}") or '<div class="art-hint">draw me</div>')


def ink_card(ink):
    return slot_card("INK", ink, '<p class="small">One of this character\'s two ink slots.</p>',
                     art_img(f"INK-{ink}") or glyph(ink, 30, 2.2))


def character_card(name, inks, signature, sig_cost):
    body = (f'<p>Inks: <b>{" / ".join(inks)}</b></p>'
            f'<p>Signature spell: <b>{signature}</b> <span class="sig-cost">{cost_html(sig_cost)}</span></p>'
            '<p class="small">Casting the signature reveals this card.</p>')
    return slot_card("CHARACTER", name, body,
                     art_img(f"{prefix(name)}-CHAR") or '<div class="art-hint">draw me</div>')


def land_card(t, owner, key=None):
    """A terrain card as an upright poker card (63.5 x 88.9 mm): the two squares
    are its top and bottom halves, split at 44.45 mm (TCG_DESIGN.md §19).  Each
    half's ink name prints twice, once upside down, for the player opposite."""
    a, b, terrain, claim, star = t
    rough = terrain in ROUGH
    art = art_img(key, "land-art")
    halves = []
    for i, ink in enumerate((a, b)):
        marks = ""
        if claim:
            marks += f'<span class="mark">{FLAG}</span>'
        if star == i:
            marks += f'<span class="mark">{STAR}</span>'
        label = "Wild · gather 1 generic" if ink == "Wild" else ink
        doodle_html = "" if art else f'<div class="l-doodle">{doodle(terrain, 24, 8)}</div>'
        halves.append(f'''
    <div class="l-half">
      <div class="l-marks">{marks}</div>
      <div class="l-name flip">{label}</div>
      {glyph(ink, 16, 2.2)}
      <div class="l-name">{label}</div>
      {doodle_html}
    </div>''')
    tags = [terrain.upper(), "ROUGH: ends a move" if rough else "OPEN"]
    if claim:
        tags.append("CLAIMABLE")
    if star is not None:
        tags.append("START ★ lay last")
    return f'''
<div class="card land{" rough" if rough else ""}">
  {art}<div class="l-frame"></div>
  {"".join(halves)}
  <div class="l-seam"></div>
  <div class="l-tag">{" · ".join(tags)}</div>
  <div class="l-foot">{key or ""} · {esc(owner)} · {KIT_VERSION}</div>
</div>'''


def blank_land():
    return '''
<div class="card land blank">
  <div class="l-half"></div><div class="l-half"></div>
  <div class="l-seam"></div>
  <div class="l-tag">________ · ROUGH / OPEN · CLAIMABLE?</div>
  <div class="l-foot">your design</div>
</div>'''


# ─── Pages ────────────────────────────────────────────────────────────────────
def page(content, cls="", named=""):
    style = f' style="page:{named}"' if named else ""
    return f'<section class="page {cls}"{style}>{content}</section>'


def grid_pages(cards, per_page, cls):
    out = []
    for i in range(0, len(cards), per_page):
        chunk = cards[i:i + per_page]
        out.append(page(f'<div class="grid {cls}">{"".join(chunk)}</div>', "cards"))
    return out


RULES_1 = f'''
<h1>Kizmit TCG — Paper Playtest Kit <span class="small">kit {KIT_VERSION}</span></h1>
<p class="lede">Draft rules for a first playtest with {len(ROSTER)} characters: {ROSTER_TEXT}. Pick one each.
Every number here is a guess. Play, then change it.
Print at <b>100% / actual size</b>, cut along the card borders, colour whatever you like.</p>

<h2>What's in the kit</h2>
<ul>
<li><b>2 illustrated pages</b> (next): how each movement pattern works on different terrain, and a turn step by step.</li>
<li><b>2 character sheets</b> (landscape pages) with HP, ink and holding-point trackers.</li>
<li><b>{4 * len(ROSTER)} sheet-slot cards</b>: each character's Race, two Inks and Character card. Keep them face down on your sheet; flip one when play reveals it.</li>
<li><b>{20 * len(ROSTER)} spell cards</b>: {len(ROSTER)} 20-card decks, plus blanks to design your own.</li>
<li><b>{1 + 9 * len(ROSTER)} terrain cards</b>: the neutral centre land and {len(ROSTER)} 9-card halves (use the two that belong to the characters playing), plus blanks. Lands are poker size: the top and bottom halves are the two squares.</li>
<li>Want one character's cards on their own? <code>build_decks.py</code> prints a complete deck per character, ready for your art.</li>
<li><b>Tokens</b>: claim tokens and two anonymous pawns (a pawn must never show who you are).</li>
<li><b>A feedback sheet</b> (last page): print one per game and fill it in together right after.</li>
</ul>

<h2>Setup</h2>
<ol>
<li><b>Lock in your character</b> (in a real match: all three) before any terrain is laid.</li>
<li>Lay the <b>neutral centre land</b>. Flip a coin: the winner chooses who lays first.
Players alternate laying one terrain card from their own half. Each card must touch an
existing card edge to edge <i>(playtest assumption)</i>, and <b>every terrain card points the same way</b>
(from one player to the other), so the squares form a grid. Your <b>star card is laid last</b>.</li>
<li>The player who laid <b>first moves second</b>. Put your pawn on your star square.</li>
<li>Each player starts with <b>1 ink</b> of their starting square's colour, shuffles their
20-card deck and draws <b>5</b>.</li>
</ol>

<h2>Your turn</h2>
<p>Draw 1 card (the first player skips this on turn 1). Score holding points (below).
Then take <b>2 actions</b>, in any combination, repeats allowed:</p>
<table class="rules">
<tr><td><b>Move</b></td><td>Move using your race's movement pattern (on your Race card).</td></tr>
<tr><td><b>Gather</b></td><td>Take 1 ink of the square you stand on — <b>2</b> if it is one of your inks.
No cap on ink. Inks outside your identity only pay <b>generic</b> costs (the number).</td></tr>
<tr><td><b>Rest</b></td><td>Put a card from your hand on the bottom of your deck, then draw a card.</td></tr>
<tr><td><b>Claim</b></td><td>Standing on a claimable land with no token: place your token on it.</td></tr>
<tr><td><b>Clear</b> (free)</td><td>Standing on a land with an opponent's token: remove it. <b>Costs no action.</b></td></tr>
<tr><td><b>Cast</b></td><td>Cast a sorcery from your hand by paying its ink cost.</td></tr>
</table>
<p>You may claim and leave in the same turn.</p>
'''

RULES_2 = f'''
<h2>Movement and terrain</h2>
<ul>
<li>Squares are counted in any direction; a diagonal step counts as 1.
You can't move off the cards or onto your opponent's square.</li>
<li><b>Ink bonus:</b> start a move on a square of one of your inks → move 1 extra square.</li>
<li><b>Rough terrain</b> (Forest, Mountain, Marsh): entering a rough square ends that move action.
<b>Blink</b> ignores this.</li>
<li><b>Line of sight</b>: nothing blocks it for now, not gaps and not rough terrain. Future terrain may block it.</li>
</ul>

<h2>Reactions (instants)</h2>
<p>An instant shows a <b>trigger</b>. When it happens on your opponent's turn and you can pay,
you may cast it. It costs <b>no action</b>. Limit: <b>one reaction per opponent turn</b>.
Your unspent ink is public, so a big ink pool is a soft tell.</p>

<h2>Your sheet and reveals</h2>
<p>Your sheet shows what your opponent has learned. Your deck may only contain spells that match
your sheet, so every card you play is a clue:</p>
<table class="rules">
<tr><td>{glyph("Red", 4.5, 7)} ink spell</td><td>reveals one Ink slot of that colour (a cost with two of the same ink reveals both)</td></tr>
<tr><td><b>Race</b> spell</td><td>reveals your Race card</td></tr>
<tr><td><b>Signature</b> spell</td><td>reveals your Character card</td></tr>
</table>
<p>Flip the matching slot card face up when it's revealed. At the end of the match, both players
show their sheets and decks to check them.</p>

<h2>Winning a game</h2>
<ul>
<li><b>Knockout:</b> reduce your opponent to 0 HP. A knocked-out character can't hold land.</li>
<li><b>Hold land:</b> at the start of your turn, score 1 point for each land holding your token.
<b>{HOLDING_TARGET} points wins.</b></li>
<li><b>Decks run out:</b> once both spell decks are empty, finish the round. The player with the most
holding points wins. Ties: most lands holding your token, then the higher share of max HP left, then a draw.
(A player whose deck is empty simply skips their draw.)</li>
</ul>

<h2>The match (best of three)</h2>
<p>The same board is used for every game. A knocked-out character is out for the match.
Survivors keep their damage and their revealed slots; winning restores nothing.
Tokens, points and ink reset each game. The loser of a game chooses who moves first next game.
<i>For a full match each player needs three characters; with this kit, play single games or split the roster.</i></p>

<h2>Things to watch while you play</h2>
<ul class="watch">
<li>Does Skitterwisp's token sniping feel fair, or too slippery?</li>
<li>Is {HOLDING_TARGET} holding points too quick or too slow?</li>
<li>Do you ever gather, or is ink too slow to bother?</li>
<li>When did you learn something about the other player's sheet, and did it change your plan?</li>
</ul>
'''


def char_sheet(player):
    hp_boxes = "".join(f'<span class="hpbox">{i}</span>' for i in range(1, 81))
    track20 = "".join(f'<span class="tb">{i}</span>' for i in range(0, 21))
    pts = "".join(f'<span class="pt">{i}</span>' for i in range(0, HOLDING_TARGET + 1))
    slots = "".join(f'<div class="slotbox"><div class="slotlabel">{s}</div>'
                    f'<div class="slothint">place card face down<br>flip when revealed</div></div>'
                    for s in ("RACE", "INK", "INK", "CHARACTER"))
    return f'''
<div class="sheet">
  <div class="sheet-head"><span class="sheet-title">Character Sheet</span>
    <span>Player {player}: ______________________</span>
    <span class="sheet-sub">This sheet is public. It shows what your opponent has learned.</span></div>
  <div class="slots">{slots}</div>
  <div class="trackers">
    <div class="tr hp"><div class="trl">HP — cross off damage (use the first N boxes for your max HP)</div><div class="hpgrid">{hp_boxes}</div></div>
    <div class="tr side">
      <div class="trl">Holding points — {HOLDING_TARGET} wins</div><div class="row">{pts}</div>
      <div class="trl">Ink — move a coin or paperclip</div>
      <div class="inkrow"><span class="ik">Ink: ______</span>{track20}</div>
      <div class="inkrow"><span class="ik">Ink: ______</span>{track20}</div>
      <div class="inkrow"><span class="ik">Other (generic)</span>{track20}</div>
    </div>
  </div>
</div>'''


def feedback_page():
    def scale(label, low, high):
        boxes = "".join(f'<span class="fb-box">{i}</span>' for i in range(1, 6))
        return (f'<div class="fb-scale"><span class="fb-q">{label}</span>'
                f'<span class="fb-end">{low}</span>{boxes}<span class="fb-end">{high}</span></div>')

    def lines(n):
        return f'<div class="fb-lines" style="height:{n * 6.5}mm"></div>'

    def tick(options):
        return " ".join(f'<span class="fb-tick">&#9744; {o}</span>' for o in options)

    names = " ".join(f'<span class="fb-tick">&#9744; {n}</span>' for n, _, _, _ in ROSTER)
    return page(f'''
<h1 class="fb-title">Playtest Feedback <span class="fb-sub">one sheet per game &middot; fill it in together, right after</span></h1>
<div class="fb-grid">
  <div><b>Date</b> ____________ &nbsp; <b>Kit</b> {KIT_VERSION}</div>
  <div><b>Players</b> ______________________________</div>
  <div><b>Rounds played</b> ______</div>
  <div><b>Real time</b> ______ minutes</div>
</div>
<div class="fb-row"><b>Player 1 played:</b> {names}</div>
<div class="fb-row"><b>Player 2 played:</b> {names}</div>
<div class="fb-row"><b>Who moved first?</b> {tick(["Player 1", "Player 2"])} &nbsp; <b>Who won?</b> {tick(["Player 1", "Player 2", "Draw"])}</div>
<div class="fb-row"><b>How?</b> {tick(["Knockout", "Holding points", "Decks ran out"])}</div>

<h2>Rate it (circle one)</h2>
{scale("Fun", "dull", "great")}
{scale("Rules were clear", "lost", "easy")}
{scale("Guessing the other sheet was tense", "flat", "tense")}
{scale("Game length", "too short", "too long")}
{scale("Felt fair", "lopsided", "fair")}

<h2>The hidden sheet</h2>
<p class="fb-p">When did you first work out something about your opponent's sheet? What gave it away? Did it change your plan?</p>
{lines(4)}

<h2>The moment</h2>
<p class="fb-p">The play everyone reacted to, good or bad.</p>
{lines(3)}

<h2>Confusing or argued-over rules</h2>
{lines(4)}

<h2>Cards</h2>
<div class="fb-cards">
  <div><b>Too strong</b>{lines(2)}</div>
  <div><b>Too weak / never wanted to play</b>{lines(2)}</div>
</div>

<div class="fb-row"><b>Play again?</b> {tick(["Yes, now", "Yes, with changes", "No"])}</div>
<h2>One change you'd make</h2>
{lines(2)}
''', "feedback")


def tokens_page():
    t1 = "".join(f'<div class="tok"><b>1</b></div>' for _ in range(10))
    t2 = "".join('<div class="tok sq"><b>2</b></div>' for _ in range(10))
    pawns = "".join(f'''
<div class="pawn"><div class="pawn-face">PLAYER {p}</div><div class="pawn-face flip">PLAYER {p}</div><div class="pawn-base">fold ▲ glue base</div></div>'''
                    for p in (1, 2))
    return page(f'''
<h2>Claim tokens</h2>
<p class="small">Player 1 = circles, Player 2 = squares, so the board reads in black and white.</p>
<div class="toks">{t1}</div><div class="toks">{t2}</div>
<h2>Pawns</h2>
<p class="small">Fold along the middle and stand them up. Pawns are anonymous on purpose:
a pawn with a character's name on it would reveal your sheet.</p>
<div class="pawns">{pawns}</div>''', "tokens")


CSS = '''
@page { size: letter; margin: 6mm; }
@page landscape { size: letter landscape; margin: 8mm; }
* { box-sizing: border-box; }
body { margin: 0; font-family: "Segoe UI", Arial, sans-serif; color: #000; font-size: 10pt; }
.page { break-after: page; }
.page:last-child { break-after: auto; }
h1 { font-family: Georgia, serif; font-size: 20pt; margin: 0 0 3mm; }
h2 { font-family: Georgia, serif; font-size: 13pt; margin: 4mm 0 1.5mm; border-bottom: 0.4mm solid #000; }
p, li { line-height: 1.35; margin: 1mm 0; }
.lede { font-size: 10.5pt; }
.small { font-size: 8pt; }
table.rules { border-collapse: collapse; width: 100%; margin: 1mm 0; }
table.rules td { border: 0.3mm solid #000; padding: 1.2mm 2mm; vertical-align: top; }
table.rules td:first-child { width: 30mm; white-space: nowrap; }
.watch li { list-style: "☐  "; }

.grid { display: grid; gap: 0; justify-content: center; }
.grid.spells { grid-template-columns: repeat(3, 63.5mm); grid-auto-rows: 88.9mm; }
.card { border: 0.35mm solid #000; position: relative; overflow: hidden; break-inside: avoid; }
.glyph { display: inline-block; vertical-align: middle; }

/* spell */
.spell { width: 63.5mm; height: 88.9mm; padding: 2.4mm 2.6mm 5mm; display: flex; flex-direction: column; }
.spell.instant { border-style: dashed; border-width: 0.5mm; }
.sp-head { display: flex; justify-content: space-between; align-items: center; gap: 1mm; }
.sp-name { font-family: Georgia, serif; font-weight: bold; font-size: 11pt; line-height: 1.1; }
.sp-name.line { border-bottom: 0.3mm solid #000; flex: 1; height: 5mm; }
.sp-cost { display: flex; align-items: center; gap: 0.6mm; white-space: nowrap; }
.generic { display: inline-flex; align-items: center; justify-content: center; width: 4.8mm; height: 4.8mm;
  border: 0.35mm solid #000; border-radius: 1.2mm; font-weight: bold; font-size: 8.5pt; }
.pip { display: inline-flex; }
.sp-type { font-size: 7pt; letter-spacing: 0.3mm; border-top: 0.3mm solid #000; border-bottom: 0.3mm solid #000;
  margin: 1.2mm 0; padding: 0.5mm 0; }
.sp-art { height: 30mm; border: 0.3mm solid #000; border-radius: 1.5mm; display: flex; align-items: center;
  justify-content: center; margin-bottom: 1.2mm; overflow: hidden; }
img.art { width: 100%; height: 100%; object-fit: cover; display: block; }
.art-hint { color: #999; font-size: 7pt; font-style: italic; }
.restr { font-size: 7.5pt; font-weight: bold; border: 0.3mm solid #000; border-radius: 3mm; padding: 0.3mm 2mm;
  align-self: flex-start; margin-bottom: 0.8mm; }
.sp-range { font-size: 8pt; font-weight: bold; }
.trig { font-size: 7.8pt; font-style: italic; margin-top: 0.8mm; }
.sp-effect { font-size: 9pt; margin-top: 1mm; line-height: 1.3; flex: 1; }
.sp-effect.lines { background: repeating-linear-gradient(transparent 0 5mm, #000 5mm 5.3mm); }
.sp-note { font-size: 6.3pt; color: #444; }
.foot { position: absolute; left: 2.6mm; right: 2.6mm; bottom: 1.4mm; font-size: 5.3pt; letter-spacing: 0.2mm; color: #333; }

/* slot */
.slot { width: 63.5mm; height: 88.9mm; padding: 2.6mm 2.6mm 5mm; display: flex; flex-direction: column; border-width: 0.6mm; }
.slot-kind { font-size: 7.5pt; letter-spacing: 0.8mm; font-weight: bold; text-align: center;
  border-bottom: 0.3mm solid #000; padding-bottom: 0.6mm; }
.slot-title { font-family: Georgia, serif; font-weight: bold; font-size: 14pt; text-align: center; margin: 1.2mm 0; }
.ph { display: block; font-family: "Segoe UI", Arial; font-weight: normal; font-size: 6.5pt; color: #666; font-style: italic; }
.slot-big { height: 28mm; border: 0.3mm solid #000; border-radius: 1.5mm; display: flex; align-items: center; justify-content: center; overflow: hidden; }
.slot-body { font-size: 8.3pt; margin-top: 1mm; }
.slot-body .hp { font-size: 12pt; font-weight: bold; margin: 0.6mm 0; }
.sig-cost { display: inline-flex; vertical-align: middle; gap: 0.5mm; }

/* land: an upright poker card, one square per half */
.land { width: 63.5mm; height: 88.9mm; border-width: 0.5mm; }
.land-art { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
.l-frame { position: absolute; inset: 0; pointer-events: none; }
.land.rough .l-frame { border: 2.2mm solid transparent;
  border-image: repeating-linear-gradient(45deg, #000 0 0.55mm, transparent 0.55mm 1.6mm) 3; }
.l-half { position: relative; height: 44.45mm; display: flex; flex-direction: column; align-items: center;
  justify-content: center; gap: 0.6mm; }
.l-name { font-size: 7.5pt; font-weight: bold; background: #fff; padding: 0 1mm; border-radius: 1mm; }
.l-name.flip { transform: rotate(180deg); }
.l-marks { position: absolute; top: 3mm; right: 3mm; display: flex; gap: 0.5mm; }
.l-marks .mark { background: #fff; border-radius: 1mm; display: inline-flex; }
.l-doodle { display: flex; justify-content: center; opacity: 0.9; margin-top: 0.4mm; }
.l-seam { position: absolute; left: 0; right: 0; top: 44.45mm; border-top: 0.4mm dashed #000; }
.l-tag { position: absolute; left: 50%; top: 44.45mm; transform: translate(-50%, -50%); max-width: 54mm;
  text-align: center; font-size: 5.8pt; line-height: 1.25; font-weight: bold; background: #fff;
  border: 0.3mm solid #000; border-radius: 2mm; padding: 0.3mm 1.6mm; width: max-content; }
.l-foot { position: absolute; left: 3mm; bottom: 2.6mm; font-size: 5pt; letter-spacing: 0.2mm; color: #333;
  background: #fff; padding: 0 0.6mm; }

/* sheet */
.sheet { width: 100%; }
.sheet-head { display: flex; align-items: baseline; gap: 6mm; border-bottom: 0.5mm solid #000; padding-bottom: 1.5mm; }
.sheet-title { font-family: Georgia, serif; font-size: 18pt; font-weight: bold; }
.sheet-sub { font-size: 8pt; font-style: italic; margin-left: auto; }
.slots { display: flex; justify-content: space-between; margin: 3mm 0; }
.slotbox { width: 64mm; height: 89mm; border: 0.5mm dashed #000; border-radius: 2mm; position: relative; display: flex;
  align-items: center; justify-content: center; }
.slotlabel { position: absolute; top: 2mm; left: 0; right: 0; text-align: center; font-weight: bold; letter-spacing: 1mm; }
.slothint { color: #888; font-size: 7.5pt; text-align: center; font-style: italic; }
.trackers { display: flex; gap: 5mm; }
.trl { font-size: 7.5pt; font-weight: bold; margin: 1mm 0 0.8mm; }
.tr.hp { width: 112mm; }
.hpgrid { display: grid; grid-template-columns: repeat(16, 7mm); grid-auto-rows: 7mm; }
.hpbox { border: 0.25mm solid #000; font-size: 5.5pt; padding: 0.3mm; color: #555; }
.tr.side { flex: 1; }
.row, .inkrow { display: flex; align-items: center; }
.pt { width: 8.6mm; height: 7mm; border: 0.3mm solid #000; display: flex; align-items: center; justify-content: center; font-weight: bold; }
.ik { width: 24mm; font-size: 7pt; }
.tb { width: 5.6mm; height: 6mm; border: 0.25mm solid #000; font-size: 5.5pt; display: flex; align-items: center; justify-content: center; }

/* feedback */
.fb-title { font-size: 18pt; margin-bottom: 2mm; }
.fb-sub { font-family: "Segoe UI", Arial; font-size: 8.5pt; font-weight: normal; font-style: italic; color: #444; }
.fb-grid { display: grid; grid-template-columns: 1fr 1.6fr; gap: 1.5mm 6mm; margin: 1mm 0 2mm; font-size: 9.5pt; }
.fb-row { font-size: 9.5pt; margin: 1.4mm 0; }
.fb-tick { margin-right: 3mm; white-space: nowrap; }
.feedback h2 { font-size: 11pt; margin: 3mm 0 1mm; }
.fb-scale { display: flex; align-items: center; gap: 1.6mm; margin: 1.2mm 0; font-size: 9.5pt; }
.fb-q { width: 72mm; }
.fb-end { width: 20mm; text-align: center; font-size: 7.5pt; color: #444; }
.fb-box { width: 7mm; height: 6mm; border: 0.3mm solid #000; border-radius: 50%; display: inline-flex; align-items: center;
  justify-content: center; font-size: 8pt; }
.fb-p { font-size: 8.5pt; margin: 0.5mm 0; color: #333; }
.fb-lines { background: repeating-linear-gradient(transparent 0 6.2mm, #000 6.2mm 6.5mm); }
.fb-cards { display: grid; grid-template-columns: 1fr 1fr; gap: 6mm; font-size: 9.5pt; }

/* tokens */
.toks { display: flex; flex-wrap: wrap; gap: 3mm; margin: 2mm 0 4mm; }
.tok { width: 18mm; height: 18mm; border: 0.5mm solid #000; border-radius: 50%; display: flex; align-items: center;
  justify-content: center; font-size: 14pt; }
.tok.sq { border-radius: 2mm; }
.pawns { display: flex; gap: 12mm; }
.pawn { width: 30mm; border: 0.4mm solid #000; }
.pawn-face { height: 34mm; display: flex; align-items: center; justify-content: center; font-weight: bold; font-size: 9pt;
  border-bottom: 0.3mm dashed #000; }
.pawn-face.flip { transform: rotate(180deg); }
.pawn-base { height: 10mm; font-size: 6pt; display: flex; align-items: center; justify-content: center; color: #555; }
'''


def build_html():
    pages = [page(RULES_1, "rules"), page(RULES_2, "rules"),
             page(diagrams.movement_page(), "rules"), page(diagrams.turn_page(), "rules")]
    pages.append(page(char_sheet(1), "sheetpage", "landscape"))
    pages.append(page(char_sheet(2), "sheetpage", "landscape"))

    slots = []
    for name, c in CHARACTERS.items():
        race = RACES[c["race"]]
        sig = SPELLS[c["signature"]]
        slots.append(race_card(c["race"], race["movement"], race["movement_text"], race["hp"], RACE_TRAIT[c["race"]]))
        slots += [ink_card(ink) for ink in c["inks"]]
        slots.append(character_card(name, c["inks"], sig["name"], (sig["cost"]["generic"], sig["cost"]["pips"])))
    cards = list(slots)
    for owner, _, deck, _ in ROSTER:
        for c in deck:
            cards.extend(spell_card(c, owner) for _ in range(c[2]))
    while len(cards) % 9:
        cards.append(blank_spell())
    pages += grid_pages(cards, 9, "spells")

    lands = [land_card(t, "Centre (neutral)", land_key(None, 0)) for t in CENTRE]
    for owner, _, _, half in ROSTER:
        lands += [land_card(t, f"{owner} half", land_key(owner, i)) for i, t in enumerate(half)]
    while len(lands) % 9:
        lands.append(blank_land())
    pages += grid_pages(lands, 9, "spells")
    pages.append(tokens_page())
    pages.append(feedback_page())
    return (f'<!doctype html><html><head><meta charset="utf-8"><title>Kizmit TCG Playtest Kit</title>'
            f'<style>{CSS}{diagrams.CSS}</style></head><body>{"".join(pages)}</body></html>')


def find_chrome():
    for p in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"):
        if os.path.exists(p):
            return p
    return shutil.which("chrome") or shutil.which("google-chrome") or shutil.which("msedge")


def main():
    html_path = os.path.join(HERE, "kit.html")
    pdf_path = os.path.join(HERE, "TCG_Playtest_Kit.pdf")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(build_html())
    chrome = find_chrome()
    if not chrome:
        sys.exit("kit.html written; no Chrome/Edge found to print it — open it in a browser and print to PDF.")
    subprocess.run([chrome, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                    f"--print-to-pdf={pdf_path}", "file:///" + html_path.replace("\\", "/")],
                   check=True, capture_output=True)
    print("wrote", pdf_path)


if __name__ == "__main__":
    main()
