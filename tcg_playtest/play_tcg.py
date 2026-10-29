"""Play the Kizmit TCG against the computer, in your browser.

    python play_tcg.py            (then your browser opens; if not, go to the printed address)
    python play_tcg.py 8800 --no-browser   (other port, don't open a browser)

A throwaway prototype for solo playtesting.  It runs the simulator's rules
engine (simulate.Game) and its AI opponents, reading cards from
Design/tcg/card_data.json, so it plays exactly the printed kit's rules.  The
computer's hand and unrevealed sheet are never sent to the browser.

Prototype limits (kept honest in the page's help text too):
- The board is built automatically (random legal placement), not laid by hand.
- Your reactions fire automatically when their trigger happens and you can pay.
- The AI peeks at your hand when judging danger (it's how the simulator works).
"""
import json
import os
import random
import sys
import threading
import time
import webbrowser
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import build_kit as K
import simulate as S

HERE = os.path.dirname(os.path.abspath(__file__))
PAGE = os.path.join(HERE, "play_tcg.html")
LOCK = threading.Lock()


def owner_of(cid):
    for name, c in K.CHARACTERS.items():
        if any(d[0] == cid for d in c["deck"]):
            return name
    return None


def card_info(cid):
    sp = K.SPELLS[cid]
    r = sp["restriction"]
    return {"id": cid, "name": sp["name"], "generic": sp["cost"]["generic"], "pips": sp["cost"]["pips"],
            "speed": sp["speed"], "type": sp["type"], "range": sp["range_text"], "trigger": sp["trigger"],
            "text": sp["text"],
            "restriction": None if not r else (("Race: " if r["kind"] == "race" else "Signature: ") + r["value"])}


class Session:
    def __init__(self, you, opp, level, seed=None):
        self.you, self.opp, self.level = you, opp, level
        self.seed = seed if seed is not None else int(time.time() * 1000) % 1_000_000_007
        self.g = S.Game(random.Random(self.seed), match=[you, opp])
        self.log = []
        self.in_turn = False
        self.say(f"Board built. {'You move first' if self.g.first_mover == you else 'The opponent moves first'}.")
        self.advance()

    # ── narration ────────────────────────────────────────────────────────────
    def name(self, p):
        if p == self.you:
            return "You"
        return self.opp if self.g.s.revealed[p]["char"] or self.g.over else "Opponent"

    def say(self, text, kind="info"):
        self.log.append({"text": text, "kind": kind, "round": self.g.stats["turn"]})

    def snap(self):
        s = self.g.s
        return {"pos": dict(s.pos), "hp": dict(s.hp), "pts": dict(s.pts), "tok": dict(s.tok),
                "cast": Counter(self.g.stats["cast"]), "frozen": set(s.frozen),
                "hand": {p: list(s.hand[p]) for p in S.MATCH}}

    def narrate(self, before, actor, act=None, ink_before=None):
        s, b = self.g.s, self.g.b
        after = self.snap()
        kind = "you" if actor == self.you else "opp"
        if act and act[0] == "gather":
            gained = s.ink[actor] - (ink_before or Counter())
            what = ", ".join(f"{n} {ink}" for ink, n in gained.items()) or "nothing"
            self.say(f"{self.name(actor)} gathered {what} ink.", kind)
        elif act and act[0] == "claim":
            self.say(f"{self.name(actor)} claimed the land {'you are' if actor == self.you else 'they are'} standing on.", kind)
        elif act and act[0] == "clear":
            free = " (a free action)" if S.CLEAR_FREE else ""
            self.say(f"{self.name(actor)} cleared an enemy token{free}.", kind)
        elif act and act[0] == "rest":
            bottomed = f" put {K.SPELLS[act[1]]['name']} on the bottom of their deck and" if act[1] else ""
            if actor == self.you:
                bottomed = bottomed.replace("their", "your")
                self.say(f"You rested,{bottomed} drew {K.SPELLS[after['hand'][actor][-1]]['name']}.", kind)
            else:
                how = "put a card on the bottom of their deck and drew one" if act[1] else "drew a card"
                self.say(f"{self.name(actor)} rested: {how}.", kind)
        for cid, n in (after["cast"] - before["cast"]).items():
            who = owner_of(cid)
            speed = "reacted with" if K.SPELLS[cid]["speed"] == "Instant" else "cast"
            self.say(f"{self.name(who)} {speed} {K.SPELLS[cid]['name']}.", "you" if who == self.you else "opp")
        for p in S.MATCH:
            if after["pos"][p] != before["pos"][p]:
                (x0, y0), (x1, y1) = before["pos"][p], after["pos"][p]
                dist = max(abs(x1 - x0), abs(y1 - y0))
                self.say(f"{self.name(p)} moved {dist} square{'s' if dist != 1 else ''}.", "you" if p == self.you else "opp")
        for p in S.MATCH:
            d = after["hp"][p] - before["hp"][p]
            if d < 0:
                self.say(f"{self.name(p)} took {-d} damage.", "hit")
            elif d > 0:
                self.say(f"{self.name(p)} healed {d}.", "you" if p == self.you else "opp")
        for land, v in after["tok"].items():
            if before["tok"].get(land) != v:
                self.say(f"{self.name(v)} claimed a land.", "you" if v == self.you else "opp")
        for land, v in before["tok"].items():
            if land not in after["tok"]:
                self.say(f"{self.name(v)}'s token was removed.", "hit")
        for land in after["frozen"] - before["frozen"]:
            self.say("A freshly claimed token was turned face down: it skips its next scoring.", "hit")

    def begin(self):
        g = self.g
        before = self.snap()
        alive = g.begin_turn()
        if not alive:
            return False
        p = g.p
        self.say(f"— {'Your' if p == self.you else 'Opponent' + chr(39) + 's'} turn, round {g.stats['turn']} —", "turn")
        gained = g.s.pts[p] - before["pts"][p]
        if gained:
            self.say(f"{self.name(p)} scored {gained} holding point{'s' if gained != 1 else ''}.", "you" if p == self.you else "opp")
        if p == self.you and len(g.s.hand[p]) > len(before["hand"][p]):
            self.say(f"You drew {K.SPELLS[g.s.hand[p][-1]]['name']}.", "you")
        self.in_turn = True
        return True

    def advance(self):
        """Run turns until it is the human's move or the game ends."""
        g = self.g
        while not g.over:
            if not self.in_turn:
                if not self.begin():
                    break
            if g.p == self.you and g.actions_left:
                return
            while g.actions_left:
                before = self.snap()
                ink_before = Counter(g.s.ink[g.p])
                act = S.choose_turn(g.s, g.b, g.p, g.rng, g.target_pts, self.level)[0]
                g.act(act)
                self.narrate(before, g.p, act, ink_before)
            g.end_turn()
            self.in_turn = False
        self.finish()

    def finish(self):
        s = self.g.s
        if getattr(self, "_finished", False):
            return
        self._finished = True
        how = s.wintype or "timeout"
        if s.winner == self.you:
            self.say(f"You win by {how}!", "win")
        elif s.winner:
            self.say(f"The opponent ({self.opp}) wins by {how}.", "lose")
        else:
            self.say("The game is a draw.", "info")

    def human_act(self, index):
        g = self.g
        if g.over or g.p != self.you or not g.actions_left:
            return
        legal = g.legal()
        if not 0 <= index < len(legal):
            return
        before = self.snap()
        ink_before = Counter(g.s.ink[self.you])
        act = legal[index]
        g.act(act)
        self.narrate(before, self.you, act, ink_before)
        if not g.actions_left:
            g.end_turn()
            self.in_turn = False
        self.advance()

    # ── what the browser may see ─────────────────────────────────────────────
    def land_cells(self, land):
        return [list(c) for c in self.g.b.cards[land]["cells"]]

    def action_view(self, i, act):
        kind, arg = act
        v = {"i": i, "kind": kind, "card": None, "cells": []}
        if kind == "move":
            v["cells"] = [list(arg)]
        elif kind == "rest":
            v["bottom"] = arg   # cycling Rest: the card this option puts on the bottom
        elif kind in ("claim", "clear"):
            v["cells"] = self.land_cells(arg)
        elif kind == "cast":
            cid, tgt = arg
            v["card"] = cid
            if isinstance(tgt, tuple):
                v["cells"] = [list(tgt)]
            elif isinstance(tgt, int):
                v["cells"] = self.land_cells(tgt)
        return v

    def view(self):
        g, s, b = self.g, self.g.s, self.g.b
        me, op = self.you, self.opp
        over = g.over
        rv = s.revealed[op]
        cells = []
        for (x, y), (land, ink) in b.cell.items():
            card = b.cards[land]
            owner = s.tok.get(land)
            cells.append({"x": x, "y": y, "ink": ink, "land": land, "terrain": card["terrain"],
                          "rough": card["terrain"] in K.ROUGH, "claim": card["claim"],
                          "token": None if owner is None else ("you" if owner == me else "opp"),
                          "frozen": land in s.frozen})
        lands = [[list(c) for c in card["cells"]] for card in b.cards]

        def sheet(p, full):
            race = S.CHARS[p]["race"]
            r = K.RACES[race]
            show_race = full or s.revealed[p]["race"]
            return {
                "character": p if (full or s.revealed[p]["char"]) else None,
                "race": race if show_race else None,
                "movement": r["movement"] if show_race else None,
                "movement_text": r["movement_text"] if show_race else None,
                "trait": ({"name": r["trait"]["name"], "text": r["trait"]["text"]} if show_race else None),
                "inks": list(S.CHARS[p]["inks"]) if full else list(s.revealed[p]["inks"]),
                "max_hp": S.CHARS[p]["hp"] if show_race else None,
                "hp": s.hp[p],
                "damage": S.CHARS[p]["hp"] - s.hp[p],
                "ink": dict(s.ink[p]),
                "pts": s.pts[p],
                "hand_count": len(s.hand[p]),
                "deck_count": len(s.deck[p]),
                "pos": list(s.pos[p]),
            }

        my_turn = (not over) and g.p == me and g.actions_left > 0
        legal = [self.action_view(i, a) for i, a in enumerate(g.legal())] if my_turn else []
        return {
            "over": over, "winner": None if s.winner is None else ("you" if s.winner == me else "opp"),
            "wintype": s.wintype, "seed": self.seed, "level": self.level,
            "round": g.stats["turn"], "my_turn": my_turn, "actions_left": g.actions_left if my_turn else 0,
            "target": g.target_pts, "you_first": g.first_mover == me,
            "clear_free": S.CLEAR_FREE, "rest_effect": S.REST_EFFECT, "actions_per_turn": S.ACTIONS_PER_TURN,
            "cells": cells, "lands": lands,
            "you": sheet(me, True), "opp": sheet(op, over),
            "opp_revealed": {"race": rv["race"], "char": rv["char"], "inks": len(rv["inks"])},
            "hand": [card_info(c) for c in s.hand[me]],
            "legal": legal, "log": self.log[-250:],
            "ink_colors": INK_COLORS,
        }


# Canonical ink colours (CardWidgetBuilder.element_color in the Godot game).
INK_COLORS = {"White": "#ebebeb", "Red": "#ff4545", "Orange": "#ff7830", "Yellow": "#ebd421", "Green": "#70e391",
              "Blue": "#61a3e3", "Indigo": "#5282ff", "Purple": "#a370ff", "Pink": "#ff69b5", "Wild": "#bdbdbd"}

SESSION = {"s": None}


def roster_view():
    out = []
    for name, c in K.CHARACTERS.items():
        r = K.RACES[c["race"]]
        out.append({"name": name, "role": c["role"], "race": c["race"], "movement": r["movement"],
                    "hp": r["hp"], "inks": c["inks"], "trait": r["trait"]["name"]})
    return out


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send_json(self, obj, code=200):
        data = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def read_json(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            data = open(PAGE, "rb").read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        elif self.path == "/api/roster":
            self.send_json({"roster": roster_view(), "levels": ["easy", "normal", "hard"]})
        elif self.path == "/api/state":
            with LOCK:
                s = SESSION["s"]
                self.send_json(s.view() if s else {"none": True})
        else:
            self.send_json({"error": "not found"}, 404)

    def do_POST(self):
        body = self.read_json()
        with LOCK:
            if self.path == "/api/new":
                you = body.get("you")
                if you not in K.CHARACTERS:
                    return self.send_json({"error": "pick a character"}, 400)
                opp = body.get("opp") or "surprise"
                choices = [n for n in K.CHARACTERS if n != you]
                if opp == "surprise" or opp not in choices:
                    opp = random.choice(choices)
                level = body.get("level") if body.get("level") in ("easy", "normal", "hard") else "normal"
                SESSION["s"] = Session(you, opp, level)
                return self.send_json(SESSION["s"].view())
            s = SESSION["s"]
            if s is None:
                return self.send_json({"error": "no game"}, 400)
            if self.path == "/api/act":
                s.human_act(int(body.get("i", -1)))
                return self.send_json(s.view())
        self.send_json({"error": "not found"}, 404)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    port = int(args[0]) if args else 8765
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"Kizmit TCG is running at {url}  (Ctrl+C to stop)")
    if "--no-browser" not in sys.argv:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
