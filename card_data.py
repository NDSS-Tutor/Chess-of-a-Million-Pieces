import uuid

SUITS = ('Spades', 'Clubs', 'Hearts', 'Diamonds')
RANKS = ('A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K')
UNO_COLORS = ('Red', 'Yellow', 'Green', 'Blue')


class Card:
    def __init__(self, suit, rank, color, image_path=None):
        self.suit = suit
        self.rank = rank
        self.color = color
        self.image_path = image_path
        self.card_id = uuid.uuid4().hex

    def use(self, game_state=None):
        return True

    def display_data(self):
        return {
            'card_id': self.card_id,
            'suit': self.suit,
            'rank': self.rank,
            'color': self.color,
            'image_path': self.image_path,
        }


class PlayingCard(Card):
    def __init__(self, suit, rank, image_path=None):
        color = 'red' if suit in ('Hearts', 'Diamonds') else 'black'
        super().__init__(suit, rank, color, image_path)


class JokerCard(Card):
    def __init__(self, color, image_path=None):
        super().__init__('Joker', 'Joker', color, image_path)


class UnoActionCard(Card):
    def __init__(self, color, label, action, image_path=None):
        suit = 'Wild' if color == 'wild' else color.title()
        super().__init__(suit, label, color, image_path)
        self.action = action

    def display_data(self):
        display_data = super().display_data()
        display_data.update({
            'card_type': 'uno_action',
            'action': self.action,
            'label': self.rank,
        })
        return display_data


class CancelCard(UnoActionCard):
    def __init__(self, color):
        super().__init__(color.lower(), 'CANCEL', 'cancel')


class ReverseCard(UnoActionCard):
    def __init__(self, color):
        super().__init__(color.lower(), 'REVERSE', 'reverse')


class DrawTwoCard(UnoActionCard):
    def __init__(self, color):
        super().__init__(color.lower(), '+2', 'draw_two')


class ColorSwapCard(UnoActionCard):
    def __init__(self):
        super().__init__('wild', 'COLOR SWAP', 'color_swap')


class DrawFourCard(UnoActionCard):
    def __init__(self):
        super().__init__('wild', '+4', 'draw_four')


def create_deck():
    deck = [PlayingCard(suit, rank) for suit in SUITS for rank in RANKS]
    deck.extend((JokerCard('red'), JokerCard('black')))
    for color in UNO_COLORS:
        for _ in range(2):
            deck.extend((CancelCard(color), ReverseCard(color), DrawTwoCard(color)))
    deck.extend(ColorSwapCard() for _ in range(4))
    deck.extend(DrawFourCard() for _ in range(4))
    return deck