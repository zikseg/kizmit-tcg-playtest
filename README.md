# Kizmit TCG — playtest kit

Kizmit is a two-player card game in development.  Each player is a character on a board that both players build from terrain cards.  You move around the board, cast spells, claim land, and try to work out your opponent's hidden **character sheet** from what they play.  First to 15 holding points wins, or knock the other character out.

**Everything here is a draft.**  The point of playing is to find what's broken, boring or confusing.  Say so on the feedback sheet.

**To download:** click a PDF below, then the download button at the top right.  For everything (needed to play the computer), use the green **Code** button → **Download ZIP**.

## What to print

Print on US letter paper at **100% / "actual size"**, never "fit to page", or the cards come out the wrong size.

| For one game (2 players) | File | Pages |
|---|---|---|
| Rules (read first) | [`TCG_Playtest_Kit.pdf`](tcg_playtest/TCG_Playtest_Kit.pdf) | 1–4 |
| Two character sheets | [`TCG_Playtest_Kit.pdf`](tcg_playtest/TCG_Playtest_Kit.pdf) | 5–6 (landscape) |
| Claim tokens and pawns | [`TCG_Playtest_Kit.pdf`](tcg_playtest/TCG_Playtest_Kit.pdf) | 27 |
| Feedback sheet, **one per game** | [`TCG_Playtest_Kit.pdf`](tcg_playtest/TCG_Playtest_Kit.pdf) | 28 |
| Each player's cards | [`decks/<Character>.pdf`](tcg_playtest/decks) — pick two | 4 each |

Each deck PDF holds everything one character brings: 4 sheet-slot cards, 20 spells and 9 lands, plus the neutral centre land (you only need one centre land per game).  The cards are poker size, nine to a page, with crop marks.  A paper trimmer is much faster than scissors.

*Alternative:* kit pages 7–26 hold every card for all five characters (no crop marks).  Print them all once if you want the whole roster on hand.

The five characters:

| Character | Inks | Plays like |
|---|---|---|
| Thornback | Green / Green | tank: 80 HP, slow, heals |
| Skitterwisp | Red / Blue | token thief: fragile, teleports |
| Brasshorn | Yellow / Orange | striker: big damage |
| Vigilux | White / Indigo | controller: diagonal lines, denies land |
| Petalstep | Pink / Purple | skirmisher: moves and heals |

## Also bring

- **Card sleeves plus an old card behind each one.**  Your four sheet-slot cards sit face down, and on plain paper you can read them through the back.  Card stock works too.
- **A coin or paperclip per ink track** on the character sheet, and a pencil for HP and points.
- **A coin to flip**, and table space of about 65 × 45 cm (the board grows as you lay it).
- Coloured pencils, if you like.  The cards are black and white on purpose: every ink has its own shape, so colour is optional.

## Playing a game

Rules are on kit pages 1–4.  Setup in short:

1. Each player picks a character and takes that deck.  Put your 4 sheet-slot cards (Race, Ink, Ink, Character) **face down** on your sheet.  Your opponent shouldn't know who you are.
2. Lay the neutral centre land, flip the coin, then take turns laying your 9 lands.  Every land points the same way, from one player to the other.  Your star land goes last.
3. Whoever laid first moves second.  Start on your star square with 1 ink, shuffle your 20 spells, and draw 5.

When you play a spell, flip the sheet card it gives away.  At the end, show each other your sheets and decks to check them.

## After each game

Fill in the **feedback sheet together, straight away**, while you still remember.  Note the minutes the game took and the moments people reacted to.  The 6-character **kit code** is printed on the cover, on the feedback sheet and on every card footer.  If two people's printouts show different codes, they come from different versions; write both down.

Send the sheets (a photo is fine) to the designer.

## No one to play with? Play the computer

Needs [Python 3](https://www.python.org/downloads/), nothing else.  On Windows, double-click `tcg_playtest/play_tcg.bat`.  Anywhere else, run `python play_tcg.py` in the `tcg_playtest` folder.  A browser tab opens with a board and an Easy / Normal / Hard opponent.  It plays the same rules and cards as the paper kit.  In this version the board is laid for you, and your reactions fire automatically.

The full rulebook, with every ruling, is [`tcg/RULES.md`](tcg/RULES.md).  The § numbers in it refer to the designer's notes, which aren't published.

*Kit version 05bf85.*
