# Kizmit TCG — Rules (current)

The rules **as they stand today**, written as a rulebook.  Three documents work together:

| Document | Holds |
|---|---|
| **`RULES.md`** (this file) | *What* the rules are right now.  Short, numbered, no history. |
| **`card_data.json`** | Every race, character, spell and terrain card, and the core numbers (holding target, deck size…).  The printed kit and the simulator read it. |
| **`../../TCG_DESIGN.md`** | *Why*: every ruling with its date, the simulations behind it, and the open questions. |

**How a change lands.**  A playtest finding or a design ruling updates the numbered section here, the number in `card_data.json` if a number changed, and gets a dated entry in `TCG_DESIGN.md` explaining why.  Each section lists the `TCG_DESIGN.md` sections behind it.

Markers: **[assumed]** = the playtest kit needed a rule nobody has ruled on yet; confirm or change it after playtesting.  Numbers in `code` come from `card_data.json`.

---

## 1. The game

Two players.  Each pilots **one character** on a board both players build from terrain cards.  You win a game by **knocking out** the other character or by **holding land**.  A match is **best of three**.  *(Design: §1, §4)*

## 2. Components

- **Character** — four sheet-slot cards kept face down on your character sheet: **Race**, **Ink**, **Ink**, **Character**.  *(§2, §2a)*
  - **Race** sets your movement pattern, max HP and a passive **trait** (`races` in the data).
  - **Inks** — two slots.  Both may be the same ink.
  - **Character** names you and your one **signature spell**.
- **Spell deck** — `deck_size` (20) cards.  At most `max_copies` (3) of any spell; exactly `signature_copies` (1) signature.  Every spell must match your sheet: its ink pips must be among your inks, and race or signature spells must match your race or character.  *(§2, §9.8)*
- **Terrain half** — `terrain_per_player` (9) terrain cards, each a domino of two squares.  Each square has an ink; the card has one terrain type.  A terrain card is a poker-size card (63.5 × 88.9 mm); its two squares are its top and bottom halves.  *(§19)*  Your half includes **1 star card** and **1–2 claimable lands** (flag icon).  *(§1b, §4a, §9.6)*
- **The neutral centre land** — claimable, two Wild squares.
- **Tokens and pawns** — claim tokens; one **anonymous** pawn per player.

## 3. Setup

1. **Lock in your characters** (a full match: three each) before any terrain is laid.  *(§1b)*
2. Lay the **neutral centre land**.
3. Flip a coin; the winner chooses who lays terrain first.  Players alternate laying one card from their own half.  **[assumed]** Each card must touch an existing card edge to edge.  **Every terrain card is laid the same way up**, pointing from one player to the other, so its squares line up with the grid (`lands_upright`).  Your **star card goes last**.  *(§19)*
4. Whoever laid **first moves second**.  *(§1b)*
5. Place your pawn on your star square.  Start with **1 ink** of that square's colour.  *(§9.1, §9.6)*
6. Shuffle your deck and draw `opening_hand` (5).

## 4. Your turn

1. **Draw** `draw_per_turn` (1).  **[assumed]** The first player skips this on their first turn.  An empty deck means you skip the draw, no penalty.
2. **Score** holding points (§9).
3. Take `actions_per_turn` (**2**) actions, in any mix, repeats allowed:  *(§4b)*

| Action | Effect |
|---|---|
| **Move** | Move using your race's pattern (§5). |
| **Gather** | Take ink from the square you stand on: `gather_own_ink` (2) if it is one of your inks, otherwise `gather_other_ink` (1).  No cap on ink.  Inks outside your identity only pay generic costs.  Wild squares give 1 generic. *(§9.1, §9.4)* |
| **Rest** | Put a card from your hand on the bottom of your deck, then draw a card (`rest`, `rest_effect: cycle`).  Your deck never shrinks by resting. |
| **Claim** | Standing on a claimable land with no token: place your token (it covers the whole card). |
| **Clear** (free) | Standing on a land holding an opponent's token: remove it.  **Costs no action** (`clear_free`). |
| **Cast** | Cast a sorcery by paying its ink cost. |

You may claim and then move away in the same turn.  *(§4b)*  Rest and free Clear: ruled 2026-10-17 *(§17)*; Rest cycles instead of drawing: 2026-10-20 *(§18)*.

## 5. Movement

- Distance counts squares in any direction; **a diagonal step counts as 1**.  **[assumed]**
- You can't move off the cards, across a gap, or onto your opponent's square (Blink jumps gaps and the opponent; it can't land on a gap).
- **Ink bonus**: start a move on a square of one of your inks → `own_ink_move_bonus` (+1) square.  *(§8.2, draft)*
- **Rough terrain** (Forest, Mountain, Marsh): entering a rough square ends that move.  *(§8.2, draft)*
- Patterns, from `races` in the data:  *(§8.1)*

| Pattern | Movement |
|---|---|
| Guard | 1 square in any direction |
| Stride | Up to 2 squares, turning allowed |
| Burst | 1 square, or exactly 3 in a straight or diagonal line |
| Blink | Teleport exactly 2 in a straight or diagonal line, ignoring what's between and ignoring rough terrain |
| Glide | Up to 3 diagonally, or 1 square straight |

## 6. Spells

- **Sorceries** cost an action and their ink.  **Instants** are reactions (§7).  Only one-shot spells for now: no permanents.  *(§9.2)*
- **Cost** = generic ink (any colour) + ink pips (that exact ink).
- **Range** counts squares (diagonal = 1).  **Line of sight**: nothing blocks it yet, neither gaps nor rough terrain (`sight_blockers` is empty).  Spells keep the "line of sight" keyword so that future terrain can block it.  *(§20)*

## 7. Reactions

- An instant prints its own **trigger**.  When it happens on your opponent's turn and you can pay, you may cast it.  **No action** is spent.  *(§9.5)*
- **One reaction per opponent turn.**
- Your unspent ink is public, so a big pool is a soft tell.

## 8. The sheet and reveals

- Your sheet shows what your opponent has learned.  Flip a slot face up when play reveals it.  *(§2, §9.7)*

| You cast… | It reveals |
|---|---|
| An ink spell | One Ink slot of that colour (a cost with two of the same pip reveals both) |
| A race spell | Your Race |
| Your signature | Your Character |

- **Pre-match reveals**: some abilities let you reveal a slot after terrain is built, before the first turn, for a one-game buff.  *(§3; none in the kit yet)*
- **Dormant traits**: a trait printed with a trigger (e.g. "below half HP") reveals its slot and activates when it fires, and stays active for the match.  *(§12.1; none in the kit yet)*
- **Honesty**: in competition, players register their lists.  Both players show their sheets and decks **after the match**.  *(§1c)*

## 9. Winning a game

- **Knockout**: reduce the opponent to 0 HP.  A knocked-out character can't hold land.  *(§4)*
- **Holding**: at the start of your turn, score 1 point for each land holding your token (plus any trait bonus).  `holding_target` (**15**) points wins.  *(§4a, §11.3)*
- **Decks run out**: once both decks are empty, finish the round; most holding points wins.  Ties: most lands holding your token, then the higher share of max HP left, then a draw.  *(§4b-)*

## 10. The match

- **Best of three**, on the board built once at the start.  *(§1a, §1b)*
- A knocked-out character is **out for the match**.  Survivors keep their **damage** and their **revealed slots**; winning restores nothing.  Pre-match reveal buffs last one game.  Triggered dormant traits stay active.
- **Tokens, points and ink reset** each game.  **[assumed for ink]**
- The **loser of a game picks** who moves first next game.

## 11. Balance targets (design constraints, not rules players see)

- A matchup may lean at most **69%**.  *(§12)*
- Specialists form a triangle: **Tank beats Striker, Striker beats Thief, Thief beats Tank**.  Generalists sit near **50%** against everyone, each other included.  *(§13, §14)*
- A character without a realistic knockout path must be **heavily favoured at holding**.  *(§4-)*
- **Every spell should be worth casting.**  *(§13.1)*
- Race profiles bound how far a single kiz may be tweaked.  *(§12)*
