"""Monte-Carlo playtest of the Kizmit TCG paper kit.

    python simulate.py [games] [--points N] [--seed S] [--match A,B] [--usage] [--ai easy|normal|hard]

With no --match, every pairing of the kit's characters is played (the race
triangle); with --match, one pairing gets the detailed report.

Card and terrain data are imported from build_kit.py, so the simulation plays
exactly the printed cards.  Both sides are played by a greedy AI that searches
every pair of actions for its turn and scores the result with a hand-written
heuristic.  It is a smoke detector for glaring problems (games that never end,
a dominant strategy, a card nobody casts), NOT a balance oracle: a stronger or
weaker AI would shift every number here.

Known simplifications (keep in mind when reading results):
- The AI peeks at the opponent's hand when estimating threat.
- Board building is random-legal (weighted toward compact shapes), not strategic.
- Reactions are not considered during the AI's own lookahead.
"""
import random
import sys
from collections import Counter, defaultdict

import build_kit as K

ROUGH = K.ROUGH
DIRS8 = [(dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if (dx, dy) != (0, 0)]
DIRS4 = [(1, 0), (-1, 0), (0, 1), (0, -1)]
BLINK = [(2 * dx, 2 * dy) for dx, dy in DIRS8]

# Characters, HP, decks and terrain come from Design/tcg/card_data.json (via build_kit).
CHARS = {
    name: {"race": c["race"], "move": K.RACES[c["race"]]["movement"], "hp": K.RACE_HP[c["race"]],
           "inks": tuple(c["inks"]), "deck": K.DECKS[name], "terrain": K.TERRAIN[name]}
    for name, c in K.CHARACTERS.items()
}
DIAG = [(1, 1), (1, -1), (-1, 1), (-1, -1)]
MATCH = ["Thornback", "Skitterwisp"]   # the two characters in the current game


def mirror_of(name):
    """A second copy of a character, so it can play itself (player state is
    keyed by name).  Same race, deck and terrain half."""
    twin = name + " II"
    if twin not in CHARS:
        CHARS[twin] = dict(CHARS[name])
        if name in HOLD_BONUS:
            HOLD_BONUS[twin] = HOLD_BONUS[name]
        HOLD_MIN[twin] = HOLD_MIN.get(name, 1)
    return twin
CARD = {}
for name, ch in CHARS.items():
    for c in ch["deck"]:
        cid, cname, copies, cost, speed, ctype, restr, rng, trig, effect, art = c
        CARD[cid] = {"id": cid, "name": cname, "cost": cost, "speed": speed, "type": ctype,
                     "race": restr.startswith("Race"), "sig": ctype == "Signature"}

# Attack numbers come from the card data too: id -> (range, damage, needs LOS).
# Effects that aren't plain numbers (Cinder Burst's rough bonus, every non-Attack
# card) are still coded by id below.
ATTACK = {cid: (sp["range"], sp["damage"], sp["line_of_sight"]) for cid, sp in K.SPELLS.items()
          if sp["type"] == "Attack" and "damage" in sp}
LIFESTEAL = {cid: sp["heal"] for cid, sp in K.SPELLS.items() if sp["type"] == "Attack" and "heal" in sp}

# Extra holding points per turn while holding any land (race passive experiments).
HOLD_BONUS = {p: K.RACE_HOLD_BONUS.get(ch["race"], 0) for p, ch in CHARS.items() if K.RACE_HOLD_BONUS.get(ch["race"])}
HOLD_MIN = {p: K.RACE_HOLD_MIN.get(ch["race"], 1) for p, ch in CHARS.items()}   # lands needed for the bonus

DEFEND = {cid: sp["prevent"] for cid, sp in K.SPELLS.items() if "prevent" in sp}   # reaction -> damage prevented
MEND_BLOOM_HEAL = 10                 # PS-05
COURTLY_STEP_HEAL = 4                # PS-04
BLOOMCROWN_DAMAGE = 12               # PS-09
WATCHFUL_BONUS = 1                   # Skimmer: +1 range on reactions
GLIDE_STRAIGHT_STEP = True           # Glide may instead step 1 square straight (2026-10-06)
DECREE_REPLACES = False              # Decree only claims empty land (2026-10-06)
STEADY_ON = True                     # experiment switch for Ambler's Steady trait
MOMENTUM_BONUS = 6
DECKOUT_RULE = True   # see play(): both decks empty -> finish the round, most points wins
# Turn-structure rules (ruled 2026-10-17), read from card_data.json; rules_test.py overrides them.
ACTIONS_PER_TURN = K.RULES["actions_per_turn"]
CLEAR_FREE = K.RULES.get("clear_free", False)   # clearing an enemy token on your land costs no action
REST_RULE = K.RULES.get("rest", False)          # "rest": spend an action on the Rest effect below
REST_EFFECT = K.RULES.get("rest_effect", "draw")   # draw: draw a card | cycle: bottom a card from hand, then draw
REST_PER_TURN = K.RULES.get("rest_per_turn")    # max Rests per turn (None = no cap)
UPRIGHT_LANDS = K.RULES.get("lands_upright", False)   # every land laid the same way up: both squares share x
# What blocks line of sight: "gap" (no card) and/or terrain names.  Empty = nothing does (2026-10-20).
SIGHT_BLOCKERS = set(K.RULES.get("sight_blockers", ["gap"]))
REST_VALUE = 2.0          # how much the AI's lookahead values a pending draw...
REST_CYCLE_VALUE = 1.0    # ...and a cycling one (the bottomed card already left the hand)

# Character quirks: dormant comebacks that wake on a trigger, reveal the
# Character slot, and stay on for the match.  Empty = off (the printed kit);
# experiments fill it, e.g. QUIRKS["Thornback"] = "deep_roots".
#   deep_roots  (wakes: opponent reaches half the holding target) Clear reaches lands within 2
#   slippery    (wakes: below half HP) take 4 less damage
#   unstoppable (wakes: below half HP) your Attacks deal +4 and ignore Rooted
QUIRKS = {}
QUIRK_VAL = {"slippery": 4, "unstoppable": 4}
PIERCE = set()   # characters whose damage ignores Rooted (experiments)
TARGET = [15]


# ─── Board ────────────────────────────────────────────────────────────────────
class Board:
    def __init__(self):
        self.cell = {}      # (x,y) -> (card_idx, ink)
        self.cards = []     # card_idx -> dict(terrain, claimable, cells, owner_half)
        self.start = {}     # player -> (x,y)

    def place(self, t, cells, half):
        a, b, terrain, claim, star = t
        idx = len(self.cards)
        self.cards.append({"terrain": terrain, "claim": claim, "cells": cells, "half": half})
        for i, (c, ink) in enumerate(zip(cells, (a, b))):
            self.cell[c] = (idx, ink)
            if star == i:
                self.start[half] = c
        return idx

    def legal(self):
        opts = []
        for (x, y) in list(self.cell):
            for dx, dy in DIRS4:
                c1 = (x + dx, y + dy)
                if c1 in self.cell:
                    continue
                for ex, ey in DIRS4:
                    c2 = (c1[0] + ex, c1[1] + ey)
                    if c2 in self.cell or c2 == (x, y) or (UPRIGHT_LANDS and c2[0] != c1[0]):
                        continue
                    opts.append((c1, c2))
        seen, out = set(), []
        for c1, c2 in opts:
            if (c1, c2) in seen:
                continue
            seen.add((c1, c2))
            n = sum((c[0] + dx, c[1] + dy) in self.cell for c in (c1, c2) for dx, dy in DIRS4)
            out.append(((c1, c2), n))
        return out

    def rough(self, c):
        return self.cards[self.cell[c][0]]["terrain"] in ROUGH

    def los(self, a, b):
        if not SIGHT_BLOCKERS:
            return True
        (x0, y0), (x1, y1) = a, b
        n = max(abs(x1 - x0), abs(y1 - y0))
        for i in range(1, n):
            t = i / n
            c = (round(x0 + (x1 - x0) * t), round(y0 + (y1 - y0) * t))
            if c not in self.cell:
                if "gap" in SIGHT_BLOCKERS:
                    return False
            elif self.cards[self.cell[c][0]]["terrain"] in SIGHT_BLOCKERS:
                return False
        return True


def build_board(rng, first_layer):
    b = Board()
    b.place(K.CENTRE[0], ((0, 0), (0, 1)) if UPRIGHT_LANDS else ((0, 0), (1, 0)), "centre")
    halves = {}
    for p in MATCH:
        cards = [t for t in CHARS[p]["terrain"] if t[4] is None]
        rng.shuffle(cards)
        cards.append(next(t for t in CHARS[p]["terrain"] if t[4] is not None))
        halves[p] = cards
    order = [first_layer, other(first_layer)]
    for i in range(18):
        p = order[i % 2]
        t = halves[p].pop(0)
        opts = b.legal()
        weights = [n * n for _, n in opts]
        cells, _ = rng.choices(opts, weights=weights)[0]
        b.place(t, cells, p)
    if b.start[order[0]] == b.start[order[1]]:
        raise RuntimeError("starts collided")
    return b


def other(p):
    return MATCH[1] if p == MATCH[0] else MATCH[0]


def cheb(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


# ─── State ────────────────────────────────────────────────────────────────────
class State:
    __slots__ = ("pos", "hp", "ink", "hand", "deck", "tok", "pts", "moved", "bastion", "momentum", "quirk_on",
                 "frozen", "steady_used", "rested", "rests",
                 "winner", "wintype", "revealed", "log")

    def copy(self):
        s = State.__new__(State)
        s.pos = dict(self.pos); s.hp = dict(self.hp)
        s.ink = {p: Counter(v) for p, v in self.ink.items()}
        s.hand = {p: list(v) for p, v in self.hand.items()}
        s.deck = self.deck  # not mutated in lookahead
        s.tok = dict(self.tok); s.pts = dict(self.pts); s.moved = dict(self.moved)
        s.bastion = dict(self.bastion); s.momentum = dict(self.momentum); s.quirk_on = dict(self.quirk_on)
        s.frozen = set(self.frozen); s.steady_used = dict(self.steady_used); s.rested = dict(self.rested)
        s.rests = dict(self.rests)
        s.winner = self.winner; s.wintype = self.wintype
        s.revealed = self.revealed; s.log = None
        return s


def identity(p):
    return set(CHARS[p]["inks"])


def can_pay(s, p, cost):
    generic, pips = cost
    pool = Counter(s.ink[p])
    for ink in pips:
        if pool[ink] <= 0:
            return False
        pool[ink] -= 1
    return sum(pool.values()) >= generic


def pay(s, p, cost):
    generic, pips = cost
    for ink in pips:
        s.ink[p][ink] -= 1
    ident = identity(p)
    # Spend off-identity / wild ink on generic first.
    for ink in sorted(s.ink[p], key=lambda k: (k in ident, -s.ink[p][k])):
        while generic and s.ink[p][ink] > 0:
            s.ink[p][ink] -= 1
            generic -= 1
    s.ink[p] = +s.ink[p]


def quirk(s, p, name):
    return QUIRKS.get(p) == name and s.quirk_on.get(p)


def wake_quirk(s, p, stats):
    if QUIRKS.get(p) and not s.quirk_on.get(p):
        s.quirk_on[p] = True
        if stats is not None:
            s.revealed[p]["char"] = True
            mark_times(s, p, stats)
            stats["quirk"][p] += 1


def damage(s, b, target, amount, attacker, stats=None):
    if CHARS[target]["race"] == "Shellback" and not s.moved.get(target + "_last", True) \
            and not quirk(s, attacker, "unstoppable") and attacker not in PIERCE:
        amount = max(0, amount - 5)
    if quirk(s, target, "slippery"):
        amount = max(0, amount - QUIRK_VAL["slippery"])
    s.hp[target] -= amount
    if s.hp[target] < CHARS[target]["hp"] / 2 and QUIRKS.get(target) in ("slippery", "unstoppable"):
        wake_quirk(s, target, stats)
    if stats is not None:
        stats["dmg"][attacker] += amount
    if s.hp[target] <= 0 and s.winner is None:
        s.winner, s.wintype = attacker, "knockout"


def guard_moves(s, b, p, steps=None, ignore_rough=False):
    start = s.pos[p]
    if steps is None:
        steps = 1 + (1 if b.cell[start][1] in identity(p) else 0)
    opp = s.pos[other(p)]
    seen = {start: 0}
    frontier = [start]
    out = set()
    for d in range(steps):
        nxt = []
        for c in frontier:
            for dx, dy in DIRS8:
                n = (c[0] + dx, c[1] + dy)
                if n in b.cell and n != opp and n not in seen:
                    seen[n] = d + 1
                    out.add(n)
                    if ignore_rough or not b.rough(n):
                        nxt.append(n)
        frontier = nxt
    return out


def blink_moves(s, b, p, frm=None):
    c = frm or s.pos[p]
    opp = s.pos[other(p)]
    return {(c[0] + dx, c[1] + dy) for dx, dy in BLINK
            if (c[0] + dx, c[1] + dy) in b.cell and (c[0] + dx, c[1] + dy) != opp}


def straight_dests(s, b, p, max_len, ignore_rough=False, exact=False, frm=None):
    """Endpoints of straight/diagonal runs: {dest: squares travelled}.  A run stops
    at a gap or the opponent; entering rough ends it unless ignore_rough."""
    c0 = frm or s.pos[p]
    opp = s.pos[other(p)]
    out = {}
    for dx, dy in DIRS8:
        c = c0
        for k in range(1, max_len + 1):
            n = (c[0] + dx, c[1] + dy)
            if n not in b.cell or n == opp:
                break
            c = n
            stopped = not ignore_rough and b.rough(c)
            if not exact or k == max_len or stopped:
                out[c] = k
            if stopped:
                break
    return out


def glide_dests(s, b, p, max_len, frm=None):
    """Diagonal runs of up to max_len; a gap or the opponent blocks, rough ends the run."""
    c0 = frm or s.pos[p]
    opp = s.pos[other(p)]
    out = set()
    for dx, dy in DIAG:
        c = c0
        for _ in range(max_len):
            n = (c[0] + dx, c[1] + dy)
            if n not in b.cell or n == opp:
                break
            c = n
            out.add(c)
            if b.rough(c):
                break
    return out


def stride_moves(s, b, p, steps, passes):
    """Up to `steps` king steps; entering rough ends the move unless a pass is
    spent (Ambler's Steady gives one pass per turn)."""
    start = s.pos[p]
    opp = s.pos[other(p)]
    seen = {(start, passes)}
    frontier = [(start, passes)]
    out = set()
    for _ in range(steps):
        nxt = []
        for c, left in frontier:
            for dx, dy in DIRS8:
                n = (c[0] + dx, c[1] + dy)
                if n not in b.cell or n == opp:
                    continue
                out.add(n)
                if not b.rough(n):
                    st = (n, left)
                elif left > 0:
                    st = (n, left - 1)
                else:
                    continue
                if st not in seen:
                    seen.add(st)
                    nxt.append(st)
        frontier = nxt
    out.discard(start)   # stepping out and back is not a move (bug found in play, 2026-10-17)
    return out


def stride_steps(s, b, p, base=2):
    return base + (1 if b.cell[s.pos[p]][1] in identity(p) else 0)


def steady_passes(s, p):
    return 0 if not STEADY_ON or s.steady_used.get(p) or CHARS[p]["race"] != "Ambler" else 1


def stride_to(s, b, p, dest, steps):
    """Move an Ambler, spending Steady only if the move needed it."""
    if steady_passes(s, p) and dest not in stride_moves(s, b, p, steps, 0):
        s.steady_used[p] = True
    s.pos[p] = dest


def move_options(s, b, p):
    mv = CHARS[p]["move"]
    if mv == "Blink":
        return blink_moves(s, b, p)
    if mv == "Glide":
        opts = glide_dests(s, b, p, 3 + (1 if b.cell[s.pos[p]][1] in identity(p) else 0))
        if GLIDE_STRAIGHT_STEP:
            c, o = s.pos[p], s.pos[other(p)]
            opts |= {(c[0] + dx, c[1] + dy) for dx, dy in DIRS4
                     if (c[0] + dx, c[1] + dy) in b.cell and (c[0] + dx, c[1] + dy) != o}
        return opts
    if mv == "Stride":
        return stride_moves(s, b, p, stride_steps(s, b, p), steady_passes(s, p))
    if mv == "Burst":
        bonus = 1 if b.cell[s.pos[p]][1] in identity(p) else 0
        opts = guard_moves(s, b, p, steps=1 + bonus)
        opts |= set(straight_dests(s, b, p, 3 + bonus, exact=True))
        return opts
    return guard_moves(s, b, p)


def is_charge(frm, to):
    dx, dy = to[0] - frm[0], to[1] - frm[1]
    return max(abs(dx), abs(dy)) >= 3 and (dx == 0 or dy == 0 or abs(dx) == abs(dy))


def after_move(s, p, frm):
    """Ramhorn's Momentum: a 3+ square straight move arms +6 on the next Attack."""
    if CHARS[p]["race"] == "Ramhorn" and is_charge(frm, s.pos[p]):
        s.momentum[p] = True


def land_at(b, c):
    return b.cell[c][0]


def lands_within(b, c, r):
    return {land_at(b, x) for x in b.cell if cheb(c, x) <= r}


# ─── Actions ──────────────────────────────────────────────────────────────────
def candidates(s, b, p, every_rest=False):
    """All legal single actions: (kind, arg).  A cycling Rest names the card it
    puts on the bottom; the AI only considers its least useful card, a human
    (every_rest) may pick any."""
    acts = [("gather", None)]
    if REST_RULE and len(s.deck[p]) > s.rested.get(p, 0) \
            and (REST_PER_TURN is None or s.rests.get(p, 0) < REST_PER_TURN):
        if REST_EFFECT == "draw":
            acts.append(("rest", None))
        elif s.hand[p]:
            for cid in (sorted(set(s.hand[p])) if every_rest else [worst_card(s, p)]):
                acts.append(("rest", cid))
    for dest in move_options(s, b, p):
        acts.append(("move", dest))
    here = land_at(b, s.pos[p])
    if b.cards[here]["claim"] and here not in s.tok:
        acts.append(("claim", here))
    if s.tok.get(here) == other(p):
        acts.append(("clear", here))
    if quirk(s, p, "deep_roots"):
        for land in lands_within(b, s.pos[p], 2):
            if land != here and s.tok.get(land) == other(p):
                acts.append(("clear", land))
    opp = other(p)
    seen = set()
    for cid in s.hand[p]:
        c = CARD[cid]
        if c["speed"] != "Sorcery" or cid in seen or not can_pay(s, p, c["cost"]):
            continue
        seen.add(cid)
        if cid in ATTACK:
            r, _, need_los = ATTACK[cid]
            d = cheb(s.pos[p], s.pos[opp])
            if d <= r and (not need_los or b.los(s.pos[p], s.pos[opp])):
                acts.append(("cast", (cid, None)))
        elif cid == "TB-04":
            acts.append(("cast", (cid, None)))
        elif cid in ("TB-05", "TB-08", "TB-09"):
            if cid != "TB-08" or (b.cards[here]["claim"] and s.tok.get(here) != p):
                acts.append(("cast", (cid, None)))
        elif cid == "SW-04":
            for dest in guard_moves(s, b, p, steps=3, ignore_rough=True):
                acts.append(("cast", (cid, dest)))
        elif cid == "SW-05":
            for land in lands_within(b, s.pos[p], 5):
                if s.tok.get(land) == opp:
                    acts.append(("cast", (cid, land)))
        elif cid == "SW-06":
            for land in lands_within(b, s.pos[p], 2):
                if b.cards[land]["claim"] and s.tok.get(land) != p:
                    acts.append(("cast", (cid, land)))
        elif cid == "SW-09":
            dests = set()
            for m in blink_moves(s, b, p):
                dests |= blink_moves(s, b, p, m)
            dests.discard(s.pos[p])
            for dest in dests:
                acts.append(("cast", (cid, dest)))
        elif cid == "SW-10":
            for dest in blink_moves(s, b, p):
                acts.append(("cast", (cid, dest)))
        elif cid == "BH-04":
            for dest in straight_dests(s, b, p, 3, ignore_rough=True):
                acts.append(("cast", (cid, dest)))
        elif cid == "BH-05":
            acts.append(("cast", (cid, None)))
        elif cid == "BH-07":
            dests = set()
            for mid in straight_dests(s, b, p, 3):
                for dx, dy in DIRS8:
                    n = (mid[0] + dx, mid[1] + dy)
                    if n in b.cell and n != s.pos[opp]:
                        dests.add(n)
                dests.add(mid)
            dests.discard(s.pos[p])
            for dest in dests:
                acts.append(("cast", (cid, dest)))
        elif cid == "BH-08":
            for land in lands_within(b, s.pos[p], 2):
                if s.tok.get(land) == opp:
                    acts.append(("cast", (cid, land)))
        elif cid == "BH-09":
            for dest in straight_dests(s, b, p, 4, ignore_rough=True):
                acts.append(("cast", (cid, dest)))
        elif cid == "VX-05":
            for dest in guard_moves(s, b, p, steps=3, ignore_rough=True):
                acts.append(("cast", (cid, dest)))
        elif cid == "PS-05":
            acts.append(("cast", (cid, None)))
        elif cid == "VX-06":
            for land in lands_within(b, s.pos[p], 2):
                if b.cards[land]["claim"] and land not in s.tok:
                    acts.append(("cast", (cid, land)))
        elif cid == "VX-07":
            dests = set()
            ln = 3 + (1 if b.cell[s.pos[p]][1] in identity(p) else 0)
            for m in glide_dests(s, b, p, ln):
                dests.add(m)
                dests |= glide_dests(s, b, p, 3, frm=m)
            dests.discard(s.pos[p])
            dests.discard(s.pos[opp])
            for dest in dests:
                acts.append(("cast", (cid, dest)))
        elif cid == "VX-09":
            dx, dy = s.pos[opp][0] - s.pos[p][0], s.pos[opp][1] - s.pos[p][1]
            if dx and abs(dx) == abs(dy) and b.los(s.pos[p], s.pos[opp]):
                acts.append(("cast", (cid, None)))
        elif cid == "PS-03":
            for land in lands_within(b, s.pos[p], 2):
                if b.cards[land]["claim"] and s.tok.get(land) != p and (DECREE_REPLACES or land not in s.tok):
                    acts.append(("cast", (cid, land)))
        elif cid == "PS-04":
            for dest in stride_moves(s, b, p, 2, steady_passes(s, p)):
                acts.append(("cast", (cid, dest)))
        elif cid == "PS-07":
            for dest in guard_moves(s, b, p, steps=2, ignore_rough=True):
                acts.append(("cast", (cid, dest)))
        elif cid == "PS-09":
            if (b.cards[here]["claim"] and s.tok.get(here) != p) or cheb(s.pos[p], s.pos[opp]) <= 2:
                acts.append(("cast", (cid, None)))
    return acts


def worst_card(s, p):
    """The card the AI's cycling Rest puts on the bottom: a duplicate of another
    card in hand if there is one, otherwise the dearest card it can't pay for
    yet, otherwise the dearest card."""
    hand = s.hand[p]
    def key(cid):
        generic, pips = CARD[cid]["cost"]
        return (hand.count(cid) > 1, not can_pay(s, p, CARD[cid]["cost"]), generic + len(pips))
    return max(hand, key=key)


def apply(s, b, p, act, stats=None, rng=None, real=False):
    kind, arg = act
    opp = other(p)
    if kind == "rest":
        s.rests[p] = s.rests.get(p, 0) + 1
        if arg is not None:   # cycle: the named card goes to the bottom first
            s.hand[p].remove(arg)
            if real:
                s.deck[p].insert(0, arg)
        if real:
            s.hand[p].append(s.deck[p].pop())
        else:
            s.rested[p] = s.rested.get(p, 0) + 1   # lookahead: the deck is shared, don't pop it
    elif kind == "gather":
        ink = b.cell[s.pos[p]][1]
        s.ink[p][ink] += 2 if ink in identity(p) else 1
    elif kind == "move":
        frm = s.pos[p]
        if CHARS[p]["move"] == "Stride":
            stride_to(s, b, p, arg, stride_steps(s, b, p))
        s.pos[p] = arg
        s.moved[p] = True
        after_move(s, p, frm)
        if real:
            on_move(s, b, p, frm, stats, rng)
    elif kind == "claim":
        s.tok[arg] = p
    elif kind == "clear":
        del s.tok[arg]
    elif kind == "cast":
        cid, tgt = arg
        c = CARD[cid]
        pay(s, p, c["cost"])
        s.hand[p].remove(cid)
        if real:
            reveal(s, p, cid, stats)
            stats["cast"][cid] += 1
        if cid in ATTACK:
            r, dmg, need_los = ATTACK[cid]
            if cid == "SW-02" and b.rough(s.pos[opp]):
                dmg += 6
            if s.momentum.get(p):
                dmg += MOMENTUM_BONUS
                s.momentum[p] = False
            if quirk(s, p, "unstoppable"):
                dmg += QUIRK_VAL["unstoppable"]
            if not strike(s, b, p, opp, dmg, r, need_los, stats, rng, real):
                return
            if cid in LIFESTEAL:
                s.hp[p] = min(CHARS[p]["hp"], s.hp[p] + LIFESTEAL[cid])
        elif cid == "TB-04":
            if s.hp[p] >= CHARS[p]["hp"]:
                s.ink[p]["Green"] += 3
            else:
                s.hp[p] = min(CHARS[p]["hp"], s.hp[p] + 15)
        elif cid == "TB-05":
            here = s.pos[p]
            n = 1 + sum(1 for dx, dy in DIRS8
                        if (here[0] + dx, here[1] + dy) in b.cell
                        and b.cell[(here[0] + dx, here[1] + dy)][1] in identity(p))
            s.ink[p]["Green"] += n
        elif cid == "TB-08":
            here = land_at(b, s.pos[p])
            s.tok[here] = p
            s.pts[p] += 1
        elif cid == "TB-09":
            s.bastion[p] = True
            s.hp[p] = min(CHARS[p]["hp"], s.hp[p] + 10)
        elif cid in ("SW-04", "SW-09", "SW-10"):
            frm = s.pos[p]
            s.pos[p] = tgt
            s.moved[p] = True
            after_move(s, p, frm)
            if cid == "SW-04":
                here = land_at(b, s.pos[p])
                if b.cards[here]["claim"] and here not in s.tok:
                    s.tok[here] = p
            if cid == "SW-10":
                for land in lands_within(b, s.pos[p], 2):
                    if s.tok.get(land) == opp:
                        del s.tok[land]
                        break
                here = land_at(b, s.pos[p])
                if b.cards[here]["claim"]:
                    s.tok[here] = p
            if real:
                on_move(s, b, p, frm, stats, rng)
        elif cid == "SW-05":
            if s.tok.get(tgt) == opp:
                del s.tok[tgt]
        elif cid in ("BH-04", "BH-07", "BH-09"):
            frm = s.pos[p]
            s.pos[p] = tgt
            s.moved[p] = True
            after_move(s, p, frm)
            if cid == "BH-07":
                s.momentum[p] = True
            if real:
                on_move(s, b, p, frm, stats, rng)
            if s.winner is None and cheb(s.pos[p], s.pos[opp]) == 1:
                if cid == "BH-04":
                    damage(s, b, opp, 6, p, stats)
                elif cid == "BH-09":
                    strike(s, b, p, opp, 18, 1, False, stats, rng, real)
        elif cid == "BH-05":
            s.ink[p]["Yellow"] += 2
            s.ink[p]["Orange"] += 1
        elif cid == "BH-08":
            if s.tok.get(tgt) == opp:
                del s.tok[tgt]
                if tgt == land_at(b, s.pos[p]) and b.cards[tgt]["claim"]:
                    s.tok[tgt] = p
        elif cid == "SW-06":
            s.tok[tgt] = p
        elif cid == "VX-05":
            frm = s.pos[p]
            s.pos[p] = tgt
            s.moved[p] = True
            if real:
                on_move(s, b, p, frm, stats, rng)
        elif cid == "VX-06":
            s.tok[tgt] = p
        elif cid == "VX-07":
            frm = s.pos[p]
            s.pos[p] = tgt
            s.moved[p] = True
            if real:
                on_move(s, b, p, frm, stats, rng)
        elif cid == "VX-09":
            strike(s, b, p, opp, 14, 99, True, stats, rng, real)
        elif cid == "PS-03":
            s.tok[tgt] = p
        elif cid in ("PS-04", "PS-07"):
            frm = s.pos[p]
            if cid == "PS-04":
                stride_to(s, b, p, tgt, 2)
                s.hp[p] = min(CHARS[p]["hp"], s.hp[p] + COURTLY_STEP_HEAL)
            else:
                s.pos[p] = tgt
                s.momentum[p] = True   # Second Wind: next Attack this turn +6
            s.moved[p] = True
            if real:
                on_move(s, b, p, frm, stats, rng)
        elif cid == "PS-05":
            if s.hp[p] >= CHARS[p]["hp"]:
                s.ink[p]["Pink"] += 2
            else:
                s.hp[p] = min(CHARS[p]["hp"], s.hp[p] + MEND_BLOOM_HEAL)
        elif cid == "PS-09":
            here = land_at(b, s.pos[p])
            if b.cards[here]["claim"]:
                s.tok[here] = p
            if cheb(s.pos[p], s.pos[opp]) <= 2:
                strike(s, b, p, opp, BLOOMCROWN_DAMAGE, 2, False, stats, rng, real)


# ─── Reveals and reactions ────────────────────────────────────────────────────
def reveal(s, p, cid, stats):
    c = CARD[cid]
    r = s.revealed[p]
    pips = c["cost"][1]
    for ink in set(pips):
        n = pips.count(ink)
        have = r["inks"].count(ink)
        while have < n and len(r["inks"]) < 2:
            r["inks"].append(ink); have += 1
    if c["race"]:
        r["race"] = True
    if c["sig"]:
        r["char"] = True
    mark_times(s, p, stats)


def mark_times(s, p, stats):
    r = s.revealed[p]
    t = stats["turn"]
    for key, done in (("race", r["race"]), ("char", r["char"]), ("both_inks", len(r["inks"]) == 2),
                      ("any_ink", len(r["inks"]) >= 1)):
        if done and key not in r["t"]:
            r["t"][key] = t


def reaction_ok(s, reactor):
    return not s.revealed[reactor]["reacted"]


def use_reaction(s, reactor, cid, stats):
    s.revealed[reactor]["reacted"] = True
    pay(s, reactor, CARD[cid]["cost"])
    s.hand[reactor].remove(cid)
    reveal(s, reactor, cid, stats)
    stats["cast"][cid] += 1


def on_move(s, b, mover, frm, stats, rng):
    reactor = other(mover)
    if s.bastion.get(reactor) and cheb(s.pos[mover], s.pos[reactor]) <= 2:
        damage(s, b, mover, 10, reactor, stats)
    if s.winner or not reaction_ok(s, reactor):
        return
    rpos = s.pos[reactor]
    w = watchful(reactor)
    if "BH-06" in s.hand[reactor] and can_pay(s, reactor, CARD["BH-06"]["cost"]) \
            and cheb(rpos, s.pos[mover]) == 1:
        use_reaction(s, reactor, "BH-06", stats)
        damage(s, b, mover, 8, reactor, stats)
        return
    if "VX-08" in s.hand[reactor] and can_pay(s, reactor, CARD["VX-08"]["cost"]):
        dx, dy = s.pos[mover][0] - rpos[0], s.pos[mover][1] - rpos[1]
        if dx and abs(dx) == abs(dy) and abs(dx) <= 3 + w and b.los(rpos, s.pos[mover]):
            use_reaction(s, reactor, "VX-08", stats)
            damage(s, b, mover, 8, reactor, stats)
            return
    for cid, r in (("SW-03", 3), ("SW-07", 3), ("TB-06", 2), ("VX-03", 2 + w)):
        if cid in s.hand[reactor] and can_pay(s, reactor, CARD[cid]["cost"]) \
                and cheb(rpos, frm) <= r and b.los(rpos, frm):
            if cid == "SW-07" and all((len(s.revealed[mover]["inks"]) == 2, s.revealed[mover]["race"],
                                       s.revealed[mover]["char"])):
                continue
            if cid == "TB-06" and cheb(frm, s.pos[mover]) <= 1:
                continue  # nothing to cut short
            use_reaction(s, reactor, cid, stats)
            if cid == "SW-03":
                damage(s, b, mover, 6, reactor, stats)
            elif cid == "SW-07":
                rv = s.revealed[mover]
                if not rv["char"]:
                    rv["char"] = True
                elif not rv["race"]:
                    rv["race"] = True
                else:
                    rv["inks"] = list(CHARS[mover]["inks"])
                mark_times(s, mover, stats)
            elif cid in ("TB-06", "VX-03"):
                if cid == "VX-03":
                    damage(s, b, mover, 4, reactor, stats)
                # Stop on the first square of the path toward the destination.
                step = (frm[0] + (s.pos[mover][0] > frm[0]) - (s.pos[mover][0] < frm[0]),
                        frm[1] + (s.pos[mover][1] > frm[1]) - (s.pos[mover][1] < frm[1]))
                if step in b.cell and step != rpos:
                    s.pos[mover] = step
            return


def react_to_attack(s, b, target, attacker, r, need_los, stats, rng):
    """Afterimage: Skitterwisp blinks away from an incoming attack. True if it fizzles."""
    if "SW-08" not in s.hand[target] or not reaction_ok(s, target) \
            or not can_pay(s, target, CARD["SW-08"]["cost"]):
        return False
    apos = s.pos[attacker]
    escapes = [d for d in blink_moves(s, b, target) if cheb(d, apos) > r or (need_los and not b.los(apos, d))]
    use_reaction(s, target, "SW-08", stats)
    s.pos[target] = rng.choice(escapes) if escapes else rng.choice(sorted(blink_moves(s, b, target)) or [s.pos[target]])
    return bool(escapes)


def react_defend(s, target, stats):
    """Brace / Guarded Heart: damage prevented by a defensive reaction (0 if none)."""
    if not reaction_ok(s, target):
        return 0
    for cid, amount in DEFEND.items():
        if cid in s.hand[target] and can_pay(s, target, CARD[cid]["cost"]):
            use_reaction(s, target, cid, stats)
            return amount
    return 0


def strike(s, b, p, opp, dmg, r, need_los, stats, rng, real):
    """Resolve an Attack against opp, letting them react.  False if it fizzled."""
    if real and react_to_attack(s, b, opp, p, r, need_los, stats, rng):
        return False
    if real:
        dmg = max(0, dmg - react_defend(s, opp, stats))
    damage(s, b, opp, dmg, p, stats)
    return True


def watchful(p):
    return WATCHFUL_BONUS if CHARS[p]["race"] == "Skimmer" else 0


def sentinel(s, b, claimer, before, stats):
    """Sentinel Mark: a fresh claim near the reactor scores nothing next time."""
    reactor = other(claimer)
    new = [land for land, v in s.tok.items() if v == claimer and before.get(land) != claimer]
    if not new or "VX-04" not in s.hand[reactor] or not reaction_ok(s, reactor) \
            or not can_pay(s, reactor, CARD["VX-04"]["cost"]):
        return
    reach = 3 + watchful(reactor)
    for land in new:
        if any(cheb(s.pos[reactor], c) <= reach for c in b.cards[land]["cells"]):
            use_reaction(s, reactor, "VX-04", stats)
            s.frozen.add(land)
            return


def score(s, p):
    """Holding points at the start of p's turn.  A face-down (Sentinel) token
    scores nothing this once, then turns back up."""
    held = sum(1 for land, v in s.tok.items() if v == p and land not in s.frozen)
    s.pts[p] += held + (HOLD_BONUS.get(p, 0) if held >= HOLD_MIN.get(p, 1) else 0)
    s.frozen = {land for land in s.frozen if s.tok.get(land) != p}


# ─── AI ───────────────────────────────────────────────────────────────────────
def threat(s, b, p):
    """Rough damage p could take next turn (peeks at the opponent's hand)."""
    opp = other(p)
    on_ink = 1 if b.cell[s.pos[opp]][1] in identity(opp) else 0
    reach = {"Blink": 2, "Burst": 3 + on_ink, "Glide": 3 + on_ink, "Stride": 2 + on_ink}.get(
        CHARS[opp]["move"], 1 + on_ink)
    d = cheb(s.pos[p], s.pos[opp])
    best = 0
    for cid in s.hand[opp]:
        if cid in ATTACK and can_pay(s, opp, CARD[cid]["cost"]):
            r, dmg, _ = ATTACK[cid]
            if d <= r + reach:
                best = max(best, dmg)
    return best


def evaluate(s, b, p, target_pts):
    opp = other(p)
    if s.winner == p:
        return 10000
    if s.winner == opp:
        return -10000
    mytok = sum(1 for v in s.tok.values() if v == p)
    optok = sum(1 for v in s.tok.values() if v == opp)
    v = 0.0
    v += 10 * (s.pts[p] - s.pts[opp]) * (10 / target_pts)
    v += 9 * (mytok - optok)
    v += 70 * (1 - s.hp[opp] / CHARS[opp]["hp"])
    v -= 70 * (1 - s.hp[p] / CHARS[p]["hp"])
    ident = identity(p)
    usable = sum(n for ink, n in s.ink[p].items() if ink in ident)
    other_ink = sum(n for ink, n in s.ink[p].items() if ink not in ident)
    v += 2.2 * min(usable, 6) + 0.8 * min(other_ink, 3)
    v += 1.0 * sum(1 for cid in s.hand[p] if can_pay(s, p, CARD[cid]["cost"]))
    # Head for contestable land.
    targets = [i for i, c in enumerate(b.cards) if c["claim"] and s.tok.get(i) != p]
    if targets:
        dmin = min(cheb(s.pos[p], cell) for i in targets for cell in b.cards[i]["cells"])
        v -= 1.8 * dmin
    if s.bastion.get(p):
        v += 12 if cheb(s.pos[p], s.pos[opp]) <= 3 else 4
    v += (REST_CYCLE_VALUE if REST_EFFECT == "cycle" else REST_VALUE) * s.rested.get(p, 0)
    t = threat(s, b, p)
    v -= 45 * t / max(1, s.hp[p])
    return v


# AI levels.  All three share one rules engine and one evaluation; they differ
# only in how hard they look.
#   easy   — half its turns it picks any plan from the better half, otherwise a noisy best
#   normal — the best plan for this turn (greedy, one turn deep)
#   hard   — two turns deep: shortlists its best plans, plays out the opponent's
#            best reply to each, and keeps the plan that leaves it best placed
AI_LEVELS = ("random", "easy", "normal", "hard")   # "random" is a yardstick, not a difficulty
HARD_SHORTLIST = 6
EASY_NOISE = 12.0
EASY_RANDOM_CHANCE = 0.5


def turn_plans(s, b, p, target_pts):
    """Every two-action plan with its evaluation, best first.  A plan that wins
    on its first action is returned alone."""
    plans = []
    for a1 in candidates(s, b, p):
        s1 = s.copy()
        apply(s1, b, p, a1)
        if s1.winner:
            return [(10000.0, [a1], s1)]
        for a2 in candidates(s1, b, p):
            s2 = s1.copy()
            apply(s2, b, p, a2)
            plans.append((evaluate(s2, b, p, target_pts), [a1, a2], s2))
    plans.sort(key=lambda t: -t[0])
    return plans


def start_of_turn(s, p, target_pts):
    """Holding points scored at the start of p's turn (no draw: lookahead only)."""
    score(s, p)
    if s.pts[p] >= target_pts and s.winner is None:
        s.winner, s.wintype = p, "holding"
    s.steady_used[p] = False
    s.rests[p] = 0
    s.moved[p + "_last"] = s.moved[p]
    s.moved[p] = False
    s.momentum[p] = False
    s.bastion[p] = False


def choose_turn(s, b, p, rng, target_pts, level="normal"):
    plans = turn_plans(s, b, p, target_pts)
    if len(plans) == 1 and plans[0][0] >= 10000:
        return plans[0][1]
    if level == "random":
        return rng.choice(plans)[1]
    if level == "easy":
        # Often just does something plausible instead of looking for the best move.
        if rng.random() < EASY_RANDOM_CHANCE:
            return rng.choice(plans[:max(1, len(plans) // 2)])[1]
        return max(plans, key=lambda t: t[0] + rng.random() * EASY_NOISE)[1]
    if level == "normal":
        return max(plans, key=lambda t: t[0] + rng.random() * 0.5)[1]
    # hard: assume the opponent answers with their own best (normal) turn
    opp = other(p)
    best, best_v = plans[0][1], -1e18
    for v0, plan, s2 in plans[:HARD_SHORTLIST]:
        s3 = s2.copy()
        start_of_turn(s3, opp, target_pts)
        if s3.winner is None:
            reply = turn_plans(s3, b, opp, target_pts)
            if reply:
                s3 = reply[0][2]
        v = evaluate(s3, b, p, target_pts) + rng.random() * 0.5
        if v > best_v:
            best, best_v = plan, v
    return best


# ─── Game ─────────────────────────────────────────────────────────────────────
class Game:
    """One game, step by step.  play() drives it with AI on both sides; the
    playable prototype (play_tcg.py) drives the same object with a human on one
    side, so both use exactly the same rules.

        g = Game(rng, match=[a, b])
        while g.begin_turn():           # scores, draws, checks wins
            while g.actions_left:       # 2 actions (1 if first_turn_actions says so)
                g.act(some action from g.legal())
            g.end_turn()                # deck-out check
    """

    def __init__(self, rng, target_pts=K.HOLDING_TARGET, max_rounds=60, first_turn_actions=None, match=None):
        if match:
            MATCH[:] = match
        self.rng, self.target_pts, self.max_rounds = rng, target_pts, max_rounds
        self.first_turn_actions = first_turn_actions
        first_layer = rng.choice(MATCH)
        self.b = b = build_board(rng, first_layer)
        self.first_mover = other(first_layer)
        self.s = s = State()
        s.pos = {p: b.start[p] for p in MATCH}
        s.hp = {p: CHARS[p]["hp"] for p in MATCH}
        s.ink = {p: Counter({b.cell[b.start[p]][1]: 1}) for p in MATCH}
        s.deck = {}
        s.hand = {}
        for p in MATCH:
            deck = [c[0] for c in CHARS[p]["deck"] for _ in range(c[2])]
            rng.shuffle(deck)
            s.hand[p], s.deck[p] = deck[:5], deck[5:]
        s.tok, s.pts = {}, {p: 0 for p in MATCH}
        s.moved = {p: False for p in MATCH}
        s.moved.update({p + "_last": True for p in MATCH})
        s.bastion = {p: False for p in MATCH}
        s.momentum = {p: False for p in MATCH}
        s.quirk_on = {p: False for p in MATCH}
        s.frozen = set()
        s.steady_used = {p: False for p in MATCH}
        s.rested = {p: 0 for p in MATCH}
        s.rests = {p: 0 for p in MATCH}
        TARGET[0] = target_pts
        s.winner = s.wintype = None
        s.revealed = {p: {"inks": [], "race": False, "char": False, "t": {}, "reacted": False} for p in MATCH}
        self.stats = {"turn": 0, "cast": Counter(), "acts": Counter(), "dmg": Counter(),
                      "held": Counter(), "castable": Counter(), "quirk": Counter(),
                      "first_mover": self.first_mover, "deckout": Counter()}
        self.order = [self.first_mover, other(self.first_mover)]
        self.turn = 0
        self.actions_left = 0
        self.p = None
        self.over = False

    def begin_turn(self):
        """Start the next player's turn.  False if the game is over."""
        s, stats = self.s, self.stats
        if s.winner is not None or self.over or self.turn >= self.max_rounds * 2:
            self.over = True
            return False
        p = self.p = self.order[self.turn % 2]
        stats["turn"] = self.turn // 2 + 1
        s.revealed[other(p)]["reacted"] = False  # opponent may react once during this turn
        s.revealed[p]["reacted"] = False
        s.bastion[p] = False
        s.momentum[p] = False
        s.moved[p + "_last"] = s.moved[p]
        s.moved[p] = False
        s.steady_used[p] = False
        score(s, p)
        if QUIRKS.get(other(p)) == "deep_roots" and s.pts[p] * 2 >= self.target_pts:
            wake_quirk(s, other(p), stats)
        if s.pts[p] >= self.target_pts:
            s.winner, s.wintype = p, "holding"
            self.over = True
            return False
        if self.turn > 0:
            if s.deck[p]:
                s.hand[p].append(s.deck[p].pop())
            else:
                stats["deckout"][p] += 1
        first = self.first_turn_actions if self.first_turn_actions is not None else ACTIONS_PER_TURN
        self.actions_left = first if self.turn == 0 else ACTIONS_PER_TURN
        s.rested = {q: 0 for q in MATCH}
        s.rests = {q: 0 for q in MATCH}
        return True

    def legal(self):
        return candidates(self.s, self.b, self.p, every_rest=True)

    def act(self, act):
        """Take one action for the player whose turn it is."""
        s, b, p, stats = self.s, self.b, self.p, self.stats
        castable = {a[1][0] for a in candidates(s, b, p) if a[0] == "cast"}
        for cid in set(s.hand[p]):
            stats["held"][cid] += 1
            if cid in castable:
                stats["castable"][cid] += 1
        stats["acts"][act[0] if act[0] != "cast" else "cast"] += 1
        before = dict(s.tok)
        apply(s, b, p, act, stats, self.rng, real=True)
        if s.winner is None:
            sentinel(s, b, p, before, stats)
        free = act[0] == "clear" and CLEAR_FREE
        self.actions_left = 0 if s.winner is not None else self.actions_left - (0 if free else 1)

    def ai_act(self, level="normal"):
        self.act(choose_turn(self.s, self.b, self.p, self.rng, self.target_pts, level)[0])

    def end_turn(self):
        s = self.s
        self.turn += 1
        self.actions_left = 0
        # Deck-out rule (ruled 2026-10-06): once both decks are empty, finish
        # the round, then the most holding points wins.  Ties: most tokens on
        # the board, then higher HP as a share of max, then a draw.
        if DECKOUT_RULE and s.winner is None and self.turn % 2 == 0 and not any(s.deck[q] for q in MATCH):
            a, c = MATCH

            def key(q):
                return (s.pts[q], sum(1 for v in s.tok.values() if v == q), s.hp[q] / CHARS[q]["hp"])
            if key(a) != key(c):
                s.winner = a if key(a) > key(c) else c
                s.wintype = "deck-out"
            else:
                s.wintype = "deck-out draw"
            self.over = True
        if s.winner is not None:
            self.over = True

    def results(self):
        s, stats = self.s, self.stats
        stats["rounds"] = self.turn // 2 + (self.turn % 2)
        stats["winner"], stats["wintype"] = s.winner, s.wintype or "timeout"
        stats["hp"] = dict(s.hp)
        stats["revealed"] = {p: s.revealed[p]["t"] for p in MATCH}
        stats["ink_left"] = {p: sum(s.ink[p].values()) for p in MATCH}
        stats["pts"] = dict(s.pts)
        return stats


def play(rng, target_pts=K.HOLDING_TARGET, max_rounds=60, first_turn_actions=None, match=None, levels=None):
    """One full AI-vs-AI game; returns its stats."""
    levels = levels or {}
    g = Game(rng, target_pts, max_rounds, first_turn_actions, match)
    while g.begin_turn():
        while g.actions_left:
            g.ai_act(levels.get(g.p, "normal"))
        g.end_turn()
    return g.results()


def report(results, target, players):
    n = len(results)
    wins = Counter(r["winner"] for r in results)
    types = Counter((r["winner"], r["wintype"]) for r in results)
    rounds = sorted(r["rounds"] for r in results)
    fm = sum(1 for r in results if r["winner"] == r["first_mover"])
    acts = sum((r["acts"] for r in results), Counter())
    casts = sum((r["cast"] for r in results), Counter())
    print(f"=== {players[0]} vs {players[1]}: {n} games, holding target {target} ===")
    print(f"Winner: " + ", ".join(f"{k}: {v} ({v / n:.0%})" for k, v in wins.most_common()))
    for (w, t), v in sorted(types.items(), key=lambda kv: -kv[1]):
        print(f"  {w or 'nobody'} by {t}: {v} ({v / n:.0%})")
    print(f"First mover won {fm / n:.0%}")
    print(f"Rounds: mean {sum(rounds) / n:.1f}, median {rounds[n // 2]}, "
          f"10th pct {rounds[n // 10]}, 90th pct {rounds[9 * n // 10]}, max {rounds[-1]}")
    tot = sum(acts.values())
    print("Actions: " + ", ".join(f"{k} {v / tot:.0%}" for k, v in acts.most_common()))
    for p in players:
        hp = [r["hp"][p] for r in results]
        print(f"{p}: mean HP left {sum(hp) / n:.0f}/{CHARS[p]['hp']}, "
              f"mean ink unspent {sum(r['ink_left'][p] for r in results) / n:.1f}, "
              f"deck-outs {sum(r['deckout'][p] for r in results)}")
        for key in ("any_ink", "both_inks", "race", "char"):
            ts = [r["revealed"][p][key] for r in results if key in r["revealed"][p]]
            print(f"   {key:9s} revealed in {len(ts) / n:4.0%} of games"
                  + (f", on average round {sum(ts) / len(ts):.1f}" if ts else ""))
    print("Casts per game:")
    for p in players:
        row = [f"{CARD[c[0]]['name']} {casts[c[0]] / n:.2f}" for c in CHARS[p]["deck"]]
        print(f"  {p}: " + ", ".join(row))


def triangle_row(results, players):
    n = len(results)
    a, b = players
    w = Counter((r["winner"], r["wintype"]) for r in results)
    wa = sum(v for (k, _), v in w.items() if k == a)
    hold = {p: w[(p, "holding")] for p in players}
    ko = {p: w[(p, "knockout")] for p in players}
    rounds = sum(r["rounds"] for r in results) / n
    return (f"{a:11s} vs {b:11s} | {a} {wa / n:4.0%} | holding {a[:5]} {hold[a] / n:4.0%} / {b[:5]} {hold[b] / n:4.0%}"
            f" | KO {a[:5]} {ko[a] / n:4.0%} / {b[:5]} {ko[b] / n:4.0%} | rounds {rounds:4.1f}")


def main():
    args = sys.argv[1:]
    games = int(args[0]) if args and args[0].isdigit() else 200
    target = int(args[args.index("--points") + 1]) if "--points" in args else K.HOLDING_TARGET
    seed = int(args[args.index("--seed") + 1]) if "--seed" in args else 1
    level = args[args.index("--ai") + 1] if "--ai" in args else "normal"
    assert level in AI_LEVELS, f"--ai must be one of {AI_LEVELS}"
    levels = {p: level for p in CHARS}
    rng = random.Random(seed)
    if "--match" in args:
        players = args[args.index("--match") + 1].split(",")
        report([play(rng, target, match=players, levels=levels) for _ in range(games)], target, players)
        return
    names = list(CHARS)
    print(f"=== Race triangle: {games} games per pairing, holding target {target}, AI {level} ===")
    held, castable, cast, played = Counter(), Counter(), Counter(), Counter()
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            players = [names[i], names[j]]
            res = [play(rng, target, match=players, levels=levels) for _ in range(games)]
            print(triangle_row(res, players), flush=True)
            for r in res:
                held.update(r["held"]); castable.update(r["castable"]); cast.update(r["cast"])
            for p in players:
                played[p] += games
    if "--usage" in args:
        # Separates "rarely legal" from "legal but never the best move".
        print("\ncard                 | owner       | casts/game | castable when held | cast when castable")
        for p in names:
            for c in CHARS[p]["deck"]:
                cid = c[0]
                line = f"{CARD[cid]['name']:20s} | {p:11s} | {cast[cid] / played[p]:10.2f} |"
                if CARD[cid]["speed"] == "Sorcery":
                    line += (f" {castable[cid] / max(1, held[cid]):18.0%} |"
                             f" {cast[cid] / max(1, castable[cid]):18.0%}")
                else:
                    line += "   (reaction)"
                print(line)


if __name__ == "__main__":
    main()
