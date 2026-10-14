import os
import pygame

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
new_size = (100, 100)


class Piece:
    def __init__(self, color, symbol, value):
        self.color = color
        self.symbol = symbol
        self.value = value
        self.position = (0, 0)
        self.stage = 1
        self.image = None
        self.has_moved = False
        self.trapped_until = 0
        self.just_trapped = False
        self.web_square = None
        self.movement = {'type': 'piece', 'directions': [], 'max_steps': 0, 'ranged': False}

    def load_image(self, key):
        try:
            self.image = pygame.image.load(os.path.join(BASE_DIR, 'Piece Icons', f'{key}.png'))
            self.image = pygame.transform.scale(self.image, new_size)
        except FileNotFoundError:
            self.image = None


class Pawn(Piece):
    def __init__(self, color):
        super().__init__(color, 'P', 1)
        forward = -1 if color == 'white' else 1
        self.movement = {
            'type': 'pawn',
            'forward': forward,
            'start_row': 6 if color == 'white' else 1,
            'captures': [(-1, forward), (1, forward)],
        }
        self.load_image(f'white_pawn' if color == 'white' else 'black_pawn')


class Rook(Piece):
    def __init__(self, color):
        super().__init__(color, 'R', 5)
        self.movement = {
            'type': 'rook',
            'directions': [(1, 0), (-1, 0), (0, 1), (0, -1)],
            'max_steps': None,
            'ranged': True,
        }
        self.load_image(f'white_rook' if color == 'white' else 'black_rook')


class Knight(Piece):
    def __init__(self, color):
        super().__init__(color, 'N', 3)
        self.movement = {
            'type': 'knight',
            'offsets': [(-2, -1), (-2, 1), (-1, -2), (-1, 2), (1, -2), (1, 2), (2, -1), (2, 1)],
        }
        self.load_image(f'white_knight' if color == 'white' else 'black_knight')


class Bishop(Piece):
    def __init__(self, color):
        super().__init__(color, 'B', 3)
        self.movement = {
            'type': 'bishop',
            'directions': [(1, 1), (1, -1), (-1, 1), (-1, -1)],
            'max_steps': None,
            'ranged': True,
        }
        self.load_image(f'white_bishop' if color == 'white' else 'black_bishop')


class Queen(Piece):
    def __init__(self, color):
        super().__init__(color, 'Q', 9)
        self.movement = {
            'type': 'queen',
            'directions': [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)],
            'max_steps': None,
            'ranged': True,
        }
        self.load_image(f'white_queen' if color == 'white' else 'black_queen')


class Avian(Piece):
    def __init__(self, color):
        super().__init__(color, 'A', 3)
        self.stage = 0
        forward = -1 if color == 'white' else 1
        self.movement = {
            'type': 'avian',
            'forward': forward,
            'directions': [(1, 1), (1, -1), (-1, 1), (-1, -1)],
            'max_steps': None,
            'ranged': False,
            'abilities': {
                'cross_stage_attack': {'stage_deltas': [1], 'offsets': 'forward'},
            },
        }
        self.load_image(f'white_avian' if color == 'white' else 'black_avian')


class Spider(Piece):
    def __init__(self, color):
        super().__init__(color, 'S', 3)
        self.stage = 3
        self.movement = {
            'type': 'spider',
            'directions': [
                (0, -1), (-1, 0), (1, 0), (0, 1),
                (-1, -1), (-1, 1), (1, -1), (1, 1),
                (0, -2), (-2, 0), (2, 0), (0, 2),
                (-1, -2), (-2, -1), (-2, 1), (-1, 2),
                (1, -2), (2, -1), (2, 1), (1, 2),
            ],
            'max_steps': 1,
            'ranged': False,
        }
        self.load_image(f'white_spider' if color == 'white' else 'black_spider')


class Mole(Piece):
    def __init__(self, color):
        super().__init__(color, 'M', 3)
        forward = -1 if color == 'white' else 1
        self.stage = 2
        self.movement = {
            'type': 'mole',
            'forward': forward,
            'directions': [(0, -2 * forward), (0, 2 * forward), (-2, 0), (2, 0)],
            'max_steps': 2,
            'ranged': False,
            'abilities': {
                'stage_shift': {
                    'stage_deltas': [-1, 1],
                    'allowed_stages': [1, 2, 3],
                    'requires_empty': False,
                    'can_capture': True,
                },
            },
        }
        self.load_image(f'white_mole' if color == 'white' else 'black_mole')


class King(Piece):
    def __init__(self, color):
        super().__init__(color, 'K', 0)
        self.is_astral_projection = False
        self.is_vulnerable_body = False
        self.movement = {
            'type': 'king',
            'directions': [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)],
            'max_steps': 1,
        }
        self.load_image(f'white_king' if color == 'white' else 'black_king')
