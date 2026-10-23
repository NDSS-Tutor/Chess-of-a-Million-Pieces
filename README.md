# Chess of a Million Pieces

A local two-player chess game with four stacked worlds, original chess pieces,
changing weather, and a deck of playing and action cards. White and Black take
turns on the same computer. The match ends when a player's king is captured.
You can also play with player life totals: a piece on the opponent's back rank
can attack that player directly, and reducing their life to zero wins the game.

## Getting Started

The game uses Python and Pygame. From the project folder, install Pygame if
needed and start the game:

```bash
python -m pip install pygame
python main.py
```

The board and piece artwork are included in the `Piece Icons`, `Ability Icons`,
and `Trap Icons` folders.

## Playing the Game

The game opens on the Plains layer with a chess army for each side, plus
additional Avians, Spiders, and Moles in their home layers. White and Black
alternate turns. Click one of your pieces, then click a highlighted legal
destination to move it. Captures remove opposing pieces and award gold equal
to the captured piece's value. Right-click a piece to inspect its health.

Kings can be put in check, shown by a shaking animation, but the game is won by
capturing the opposing king rather than by checkmate. Alternatively, each
player starts with 100 HP. If one of your pieces is on the opponent's back
rank, open Player Status with **P** and click the attack prompt to damage the
opponent for 1 HP. Attacking uses your turn. The player who reaches 0 HP loses.
Pawns can move two squares on their first move, capture diagonally, capture en
passant, and promote when they reach the far edge of their layer. Kings and
rooks can castle when the path is clear and neither piece has moved.

### The Four Layers

The worlds share coordinates, so a square on one layer corresponds to the same
location on another. Use the Up and Down arrows to switch layers:

| Layer | What to expect |
| --- | --- |
| Sky | Avians begin here. Storm clouds can damage pieces on this layer. |
| Plains | The opening layer, with the standard chess army. Sundays change the board colors and outline bishops in gold. |
| Tunnels | Moles begin here and can shift between ground layers. |
| Caves | Spiders begin here. Fog and Crystal Haze can affect visibility and piece positions. |

Use Left and Right to scroll horizontally. The board normally shows eight
columns. Playing the King of Clubs expands the current layer by 25 columns on
each side; use the horizontal controls to explore it.

### Original Pieces

The Piece Index (Tab) shows each piece's movement and special abilities.

| Piece | Movement and ability |
| --- | --- |
| Pawn | Moves forward one square, or two on its first move; captures diagonally. |
| Rook | Moves any number of unobstructed squares horizontally or vertically. |
| Knight | Jumps in an L shape. |
| Bishop | Moves any number of unobstructed diagonal squares. On Sundays, its visible shape is outlined in gold. |
| Queen | Moves any number of unobstructed squares in any straight or diagonal direction. |
| King | Moves one square in any direction and can castle with an eligible rook. |
| Avian | Moves diagonally without capturing on those diagonal moves. It can divebomb an enemy one square forward on the next lower layer. |
| Spider | Moves to nearby squares in its two-square movement pattern. It can capture only on the pattern's outer ring. It leaves a web behind; an enemy that steps on the web is trapped for a turn. |
| Mole | Moves exactly two squares horizontally or vertically. It can also shift one layer up or down at the corresponding square, capturing an enemy there if present. |

### Pawn Promotion and Gold

When a pawn reaches the opposite edge of its layer, the Pawn Promotion Shop
opens. Choose an affordable piece to replace the pawn. Promotion prices use
the piece values:

| Piece | Gold |
| --- | ---: |
| Pawn | 1 |
| Knight, Bishop, Avian, Spider, Mole | 3 |
| Rook | 5 |
| Queen | 9 |
| King | 0 |

Capturing pieces earns their value in gold. The King of Spades card awards 50
gold. The currency window also tracks gems and tokens, though they currently
have no other gameplay use.

## Cards

Players draw one card at the start of each non-skipped turn, up to a hand limit
of eight. Click a playable card in the Card Hand window. A card can be played
when it matches the top discard by rank or color; action cards can also match
another action of the same type, and wild cards are always playable. Playing a
card does not itself move a chess piece.

The deck contains standard playing cards, two Jokers, and UNO-style action
cards:

- **Cancel:** Skips the opponent's next turn. Only one Cancel can be played
  during a turn.
- **Reverse:** Reverses the colors and piece ownership on the layer associated
  with the card's color: Blue reverses Sky, Green Plains, Yellow Tunnels, and
  Red Caves.
- **Draw Two / Draw Four:** Makes the opponent draw two or four cards. If the
  hand exceeds eight cards, excess cards are discarded at random.
- **Color Swap:** A wild card with no additional board effect.
- **Queen of Clubs:** Places pawns on empty squares immediately around your
  queen.
- **King of Hearts:** Creates an astral projection and leaves a vulnerable
  body behind. The projection can shift between layers and returns to its
  body, or ends after six of its owner's turns. Losing the projection or its
  body removes the king.
- **King of Spades:** Awards 50 gold.
- **King of Clubs:** Expands the current layer, adding 25 columns to either
  side and pawns on the new files.

When the draw pile is empty, used cards are shuffled back into it, keeping the
top discard in play.

## Weather and Calendar

The calendar starts on Monday and shows a rolling seven-day forecast for each
layer. Each forecast gives a condition and the chance that it will occur. The
weather day advances after both players have completed three turns each.
Weather and wind can also be inspected in their separate windows.

Conditions vary by layer:

- **Sky:** Sunny, Cloudy, Rainy, Windy, Snowy, Foggy, and Stormy. Cloud cover
  drifts across the board; during Stormy weather, clouds damage pieces caught
  beneath them at the end of their owner's turn.
- **Plains:** Sunny, Cloudy, Rainy, Windy, Drought, Thunderstorm, and Foggy.
  On Sundays, the Plains use special colors and all bishops have a gold
  outline around the piece artwork.
- **Tunnels:** Dripping, Damp Mist, Cold Draft, Underground Rain, Still Air,
  and Foggy.
- **Caves:** Dustfall, Cold, Barometric Winds, Crystal Haze, Dripping, and Cave
  Fog. During Barometric Winds, every piece in the Caves is pushed in the
  current wind direction at the end of each turn, up to the current wind speed
  in squares. The Wind Indicator represents direction with its vane and speed
  with the anemometer's rotation. Pieces stop at the board edge or when
  another piece blocks them. Cave Fog limits visibility around your pieces.
  Crystal Haze creates
  deceptive duplicates and can move the apparent location of real cave
  pieces; hallucinations disappear when attacked or when they attack an
  opposing piece.

Weather also changes the board's daylight shading as the day progresses.

## Keyboard and Windows

| Key | Action |
| --- | --- |
| Up / Down | Change the active layer |
| Left / Right | Scroll horizontally on the active layer |
| Tab | Open or close the Piece Index |
| Backspace | Open or close the Debug Card Deck |
| H | Toggle the Card Hand and Draw / Play Piles windows |
| ` (backtick) | Open or close the Currency window |
| 8 | Open or close the Weather Forecast |
| 9 | Open or close the Wind Indicator |
| O | Open or close the Moon Phase window |
| P | Open or close Player Status |
| R | Restart the match |
| Esc | Quit |

The **Piece Index** uses Left and Right to browse piece types and Up and Down
to browse movement-pattern pages. The **Card Hand** and **Draw / Play Piles**
windows show your hand and the current piles. The **Pawn Promotion Shop**
appears when a pawn is ready to promote.

The **Player Status** window shows only the player whose turn it is, with their
name and HP text to the right of the A-pose stencil. When an attack is available,
the attack prompt is clickable and deals 1 HP damage. Attacking ends your turn.

The **Moon Phase** window displays the current lunar phase and in-game day. Its
eight-phase cycle advances with each in-game day and restarts with a new match.

The **Debug Card Deck** lets you play cards directly from the full deck for the
current player and skip ahead one weather day. Its cards can bypass the normal
hand and card-matching rules; it is intended for testing. Scroll through its
cards with the mouse wheel, Up / Down, or Page Up / Page Down. Long status
messages wrap within the window.

## Project Files

- `main.py` — game loop, board, rules, windows, weather, and card effects.
- `piece_data.py` — piece classes, movement definitions, and artwork loading.
- `card_data.py` — card classes and deck creation.
- `weather_data.py` — weather conditions and stage-specific effects.
