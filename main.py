import ctypes
import math
import multiprocessing as mp
import os
from queue import Empty
import random
import textwrap

import pygame
import card_data
import piece_data

pygame.init()

grid_size = 8
square_size = 100
hand_size_limit = 8
hand_card_width = 96
hand_card_height = 106
hand_card_gap = 8
colors = {
    'light_blue': (160, 190, 210),
    'dark_blue': (110, 138, 170),
    'light_green': (105, 146, 62),
    'dark_green': (78, 120, 55),
    'light_brown': (161, 126, 98),
    'dark_brown': (88, 69, 52),
    'light_grey': (80, 80, 85),
    'dark_grey': (30, 30, 35),
}
stages = {
    'sky': (colors['light_blue'], colors['dark_blue']),
    'plains': (colors['light_green'], colors['dark_green']),
    'tunnels': (colors['light_brown'], colors['dark_brown']),
    'caves': (colors['light_grey'], colors['dark_grey']),
}
stage_names = list(stages.keys())


def normalize_stage_index(value):
    if value is None:
        return 0
    try:
        value = int(value)
    except (TypeError, ValueError):
        return 0
    if value < 0:
        return 0
    if value >= len(stage_names):
        return len(stage_names) - 1
    return value


current_stage = normalize_stage_index(1)
selected_piece = None
current_turn = 'white'
last_move = None
en_passant_target = None
winner = None
game_over = False
web_tiles = {}
web_images = {}
secondary_window_process = None
secondary_window_queue = None
hand_window_process = None
hand_window_queue = None
hand_command_queue = None
pile_window_process = None
pile_window_queue = None
hands = {'white': [], 'black': []}
draw_pile = []
played_pile = []
rotated_stages = set()
reverse_card_stages = {'green': 1, 'blue': 0, 'yellow': 2, 'red': 3}


def reset_card_game():
    global draw_pile, played_pile
    draw_pile = card_data.create_deck()
    random.shuffle(draw_pile)
    played_pile = [draw_pile.pop()]
    for hand in hands.values():
        hand.clear()


def can_play_card(card, top_card):
    if top_card is None:
        return True

    card_is_uno = card.get('card_type') == 'uno_action'
    top_is_uno = top_card.get('card_type') == 'uno_action'
    card_color = card.get('color', '').lower()
    top_color = top_card.get('color', '').lower()
    if card_is_uno and card_color == 'wild':
        return True

    if card_is_uno and top_is_uno:
        return top_color == 'wild' or card_color == top_color

    if card_is_uno:
        if top_color == 'red':
            return card_color in ('red', 'yellow')
        if top_color == 'black':
            return card_color in ('green', 'blue')
        return False

    if top_is_uno:
        if top_color == 'wild':
            return True
        if top_color in ('red', 'yellow'):
            return card_color == 'red'
        if top_color in ('green', 'blue'):
            return card_color == 'black'
        return False

    same_number = card.get('rank', '').isdigit() and card.get('rank') == top_card.get('rank')
    return card_color == top_color or same_number


def draw_card_from_pile():
    if not draw_pile and len(played_pile) > 1:
        draw_pile.extend(played_pile[:-1])
        del played_pile[:-1]
        random.shuffle(draw_pile)
    if not draw_pile:
        return None
    return draw_pile.pop()


def draw_card_for_turn(color):
    if len(hands[color]) >= hand_size_limit:
        return None
    card = draw_card_from_pile()
    if card is not None:
        hands[color].append(card)
    return card


def draw_cards_for_player(color, amount):
    player_hand = hands[color]
    for _ in range(amount):
        card = draw_card_from_pile()
        if card is None:
            break
        player_hand.append(card)

    excess_count = max(0, len(player_hand) - hand_size_limit)
    if excess_count:
        discarded_cards = random.sample(player_hand, excess_count)
        for card in discarded_cards:
            player_hand.remove(card)
        if played_pile:
            played_pile[-1:-1] = discarded_cards
        else:
            played_pile.extend(discarded_cards)


def get_display_square(square, stage):
    if normalize_stage_index(stage) in rotated_stages:
        return (grid_size - 1 - square[0], grid_size - 1 - square[1])
    return square


def map_square_between_stages(square, source_stage, target_stage):
    display_square = get_display_square(square, source_stage)
    return get_display_square(display_square, target_stage)


def get_stage_shift_target_square(piece, target_stage):
    return map_square_between_stages(piece.position, piece.stage, target_stage)


def reverse_stage_colors(stage):
    global selected_piece, last_move, en_passant_target

    stage = normalize_stage_index(stage)
    if stage in rotated_stages:
        rotated_stages.remove(stage)
    else:
        rotated_stages.add(stage)

    for piece in board_pieces:
        if piece.stage != stage:
            continue
        piece.color = 'black' if piece.color == 'white' else 'white'
        piece.load_image(f'{piece.color}_{piece.__class__.__name__.lower()}')

    for web_key, owner in list(web_tiles.items()):
        if web_key[0] == stage:
            web_tiles[web_key] = 'black' if owner == 'white' else 'white'

    if selected_piece is not None and selected_piece.stage == stage:
        selected_piece = None
    if last_move is not None and last_move['piece'].stage == stage:
        last_move = None
        en_passant_target = None


def get_visible_webs():
    visible = {}
    for (stage, x, y), owner in web_tiles.items():
        if stage == normalize_stage_index(current_stage):
            visible[(x, y)] = owner
    return visible


def get_spider_movement_offsets():
    return [
        (0, -1), (-1, 0), (1, 0), (0, 1),
        (-1, -1), (-1, 1), (1, -1), (1, 1),
        (0, -2), (-2, 0), (2, 0), (0, 2),
        (-1, -2), (-2, -1), (-2, 1), (-1, 2),
        (1, -2), (2, -1), (2, 1), (1, 2),
    ]


def get_spider_attack_offsets():
    return [
        (0, -2), (-2, 0), (2, 0), (0, 2),
        (-1, -2), (-2, -1), (-2, 1), (-1, 2),
        (1, -2), (2, -1), (2, 1), (1, 2),
    ]


def get_piece_reference_pages():
    pages = [
        {
            'name': 'Pawn',
            'piece': piece_data.Pawn('white'),
            'subpages': [
                {'label': 'First Move', 'pattern': [(0, -1), (0, -2)], 'attacks': []},
                {'label': 'Movement', 'pattern': [(0, -1)], 'attacks': []},
                {'label': 'Attack', 'pattern': [], 'attacks': [(-1, -1), (1, -1)]},
            ],
        },
        {'name': 'Rook', 'piece': piece_data.Rook('white'), 'pattern': [(0, -1), (0, 1), (-1, 0), (1, 0), (0, -2), (0, 2), (-2, 0), (2, 0), (-3, 0), (3, 0)], 'attacks': []},
        {'name': 'Knight', 'piece': piece_data.Knight('white'), 'pattern': [(-1, -2), (-2, -1), (-2, 1), (-1, 2), (1, -2), (2, -1), (2, 1), (1, 2)], 'attacks': []},
        {'name': 'Bishop', 'piece': piece_data.Bishop('white'), 'pattern': [(-1, -1), (-2, -2), (-3, -3), (1, -1), (2, -2), (3, -3), (-1, 1), (-2, 2), (-3, 3), (1, 1), (2, 2), (3, 3)], 'attacks': []},
        {
            'name': 'Avian',
            'piece': piece_data.Avian('white'),
            'description': 'Divebomb lets the Avian strike the piece directly below it on the next lower layer.',
            'abilities': [
                {'name': 'divebomb', 'icon_path': os.path.join('Ability Icons', 'white_dive.png'), 'fallback_color': (235, 185, 95)},
            ],
            'subpages': [
                {'label': 'Movement', 'pattern': [(-1, -1), (-2, -2), (-3, -3), (1, -1), (2, -2), (3, -3), (-1, 1), (-2, 2), (-3, 3), (1, 1), (2, 2), (3, 3)], 'attacks': []},
                {'label': 'Attack', 'pattern': [], 'attacks': [(0, -1)]},
            ],
        },
        {
            'name': 'Spider',
            'piece': piece_data.Spider('white'),
            'description': 'Movement stays the same, but the Spider can only attack on the outer ring of that pattern.',
            'abilities': [
                {'name': 'sticky webbing', 'icon_path': os.path.join('Trap Icons', 'white_web.png'), 'fallback_color': (165, 195, 215)},
            ],
            'subpages': [
                {'label': 'Movement', 'pattern': get_spider_movement_offsets(), 'attacks': []},
                {'label': 'Attack', 'pattern': [], 'attacks': get_spider_attack_offsets()},
            ],
        },
        {
            'name': 'Mole',
            'piece': piece_data.Mole('white'),
            'description': 'The Mole can move two spaces forward, left, right, or back, or shift one ground layer up or down without leaving the board.',
            'abilities': [
                {
                    'name': 'ground shift',
                    'description': 'Shift one layer up or down into an unoccupied square.',
                    'fallback_color': (190, 145, 95),
                },
            ],
            'subpages': [
                {'label': 'Movement', 'pattern': [(0, -2), (0, 2), (-2, 0), (2, 0)], 'attacks': []},
                {'label': 'Ground Shift', 'pattern': [(0, 0)], 'attacks': []},
            ],
        },
        {'name': 'Queen', 'piece': piece_data.Queen('white'), 'pattern': [(0, -1), (0, 1), (-1, 0), (1, 0), (-1, -1), (-2, -2), (-3, -3), (1, -1), (2, -2), (3, -3), (-1, 1), (-2, 2), (-3, 3), (1, 1), (2, 2), (3, 3)], 'attacks': []},
        {'name': 'King', 'piece': piece_data.King('white'), 'pattern': [(-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)], 'attacks': []},
    ]
    return pages


def create_piece(color, piece_type, x, y):
    piece = getattr(piece_data, piece_type)(color)
    piece.position = (x, y)
    return piece


def create_initial_board():
    pieces = []

    black_back_rank = ['Rook', 'Knight', 'Bishop', 'Queen', 'King', 'Bishop', 'Knight', 'Rook']
    for column, piece_type in enumerate(black_back_rank):
        pieces.append(create_piece('black', piece_type, column, 0))
    for column in range(grid_size):
        pieces.append(create_piece('black', 'Pawn', column, 1))

    white_back_rank = ['Rook', 'Knight', 'Bishop', 'Queen', 'King', 'Bishop', 'Knight', 'Rook']
    for column, piece_type in enumerate(white_back_rank):
        pieces.append(create_piece('white', piece_type, column, 7))
    for column in range(grid_size):
        pieces.append(create_piece('white', 'Pawn', column, 6))

    pieces.extend([
        create_piece('black', 'Avian', 2, 2),
        create_piece('black', 'Avian', 5, 2),
        create_piece('white', 'Avian', 2, 5),
        create_piece('white', 'Avian', 5, 5),
        create_piece('black', 'Spider', 1, 0),
        create_piece('black', 'Spider', 6, 0),
        create_piece('white', 'Spider', 1, 7),
        create_piece('white', 'Spider', 6, 7),
        create_piece('black', 'Mole', 2, 1),
        create_piece('black', 'Mole', 5, 1),
        create_piece('white', 'Mole', 2, 6),
        create_piece('white', 'Mole', 5, 6),
    ])

    return pieces


def get_square_from_mouse(mouse_pos):
    x, y = mouse_pos
    col = x // square_size
    row = y // square_size
    if 0 <= col < grid_size and 0 <= row < grid_size:
        return get_display_square((col, row), current_stage)
    return None


def get_piece_at_square(pieces, square, stage):
    for piece in pieces:
        if piece.position == square and piece.stage == stage:
            return piece
    return None


def get_pieces_at_square(pieces, square):
    return [piece for piece in pieces if piece.position == square]


def get_piece_ability(piece, ability_name):
    return piece.movement.get('abilities', {}).get(ability_name, {})


def get_stage_shift_destinations(piece, pieces):
    ability = get_piece_ability(piece, 'stage_shift')
    allowed_stages = ability.get('allowed_stages')
    destinations = []

    for stage_delta in ability.get('stage_deltas', []):
        target_stage = piece.stage + stage_delta
        if allowed_stages is not None and target_stage not in allowed_stages:
            continue
        target_square = get_stage_shift_target_square(piece, target_stage)
        if ability.get('requires_empty', True) and get_piece_at_square(pieces, target_square, target_stage) is not None:
            continue
        destinations.append(target_stage)

    return destinations


def get_ability_target_squares(piece, ability):
    offsets = ability.get('offsets', [])
    if offsets == 'forward':
        forward = piece.movement.get('forward', -1 if piece.color == 'white' else 1)
        offsets = [(0, forward)]

    x, y = piece.position
    return [(x + dx, y + dy) for dx, dy in offsets]


def get_cross_stage_attack_targets(piece, pieces):
    ability = get_piece_ability(piece, 'cross_stage_attack')
    if not ability:
        return []

    stage_deltas = ability.get('stage_deltas', [])
    target_stages = {piece.stage + delta for delta in stage_deltas}
    attack_squares = set()
    for square in get_ability_target_squares(piece, ability):
        if not in_bounds(square) or get_piece_at_square(pieces, square, piece.stage) is not None:
            continue
        attack_squares.add(square)

    targets = []
    for target in pieces:
        target_square = map_square_between_stages(target.position, target.stage, piece.stage)
        if target.stage in target_stages and target_square in attack_squares and target.color != piece.color and can_piece_attack_target(piece, target):
            targets.append(target)
    return targets


def in_bounds(square):
    x, y = square
    return 0 <= x < grid_size and 0 <= y < grid_size


def can_piece_attack_target(attacker, target):
    if attacker is None or target is None:
        return False

    if attacker.stage != target.stage:
        ability = get_piece_ability(attacker, 'cross_stage_attack')
        return target.stage - attacker.stage in ability.get('stage_deltas', [])

    if attacker.__class__.__name__ == 'Spider':
        return target.position in [
            (attacker.position[0] + dx, attacker.position[1] + dy)
            for dx, dy in attacker.movement.get('directions', [])
        ]

    return True


def is_piece_attacking_square(piece, square, pieces, target_stage=None):
    if piece is None or square is None:
        return False

    target_pieces = get_pieces_at_square(pieces, square)
    if target_stage is not None:
        target_pieces = [target for target in target_pieces if target.stage == target_stage]
    if target_pieces and not any(can_piece_attack_target(piece, target) for target in target_pieces):
        return False

    attack_square = square
    if target_stage is not None and target_stage != piece.stage:
        attack_square = map_square_between_stages(square, target_stage, piece.stage)
    return attack_square in get_legal_moves(piece, pieces)


def get_checked_kings(pieces):
    checked_kings = []
    for king in pieces:
        if king.__class__.__name__ != 'King':
            continue

        is_in_check = any(
            piece.color != king.color and (
                piece.stage == king.stage or (
                    can_piece_attack_target(piece, king)
                )
            ) and is_piece_attacking_square(piece, king.position, pieces, king.stage)
            for piece in pieces
        )
        if is_in_check:
            checked_kings.append(king)
    return checked_kings


def get_checked_king(pieces):
    checked_kings = get_checked_kings(pieces)
    return checked_kings[0] if checked_kings else None


def get_king_shake_angle(piece, pieces):
    if piece.__class__.__name__ != 'King' or piece not in get_checked_kings(pieces):
        return 0

    seconds = pygame.time.get_ticks() / 1000.0
    return math.sin(seconds * 18.0) * 9.0


def get_stage_local_moves(piece, pieces):
    global last_move, en_passant_target

    move_type = piece.movement['type']
    x, y = piece.position
    legal_moves = []

    if move_type == 'pawn':
        forward = piece.movement['forward']
        one_step = (x, y + forward)
        if in_bounds(one_step) and get_piece_at_square(pieces, one_step, piece.stage) is None:
            legal_moves.append(one_step)

        start_row = piece.movement['start_row']
        if y == start_row:
            two_step = (x, y + (2 * forward))
            if in_bounds(two_step) and get_piece_at_square(pieces, one_step, piece.stage) is None and get_piece_at_square(pieces, two_step, piece.stage) is None:
                legal_moves.append(two_step)

        for dx in (-1, 1):
            target = (x + dx, y + forward)
            if in_bounds(target):
                occupant = get_piece_at_square(pieces, target, piece.stage)
                if occupant is not None and occupant.color != piece.color and can_piece_attack_target(piece, occupant):
                    legal_moves.append(target)

                if last_move is not None and last_move['piece'].color != piece.color and last_move['piece'].__class__.__name__ == 'Pawn':
                    if abs(last_move['start'][1] - last_move['end'][1]) == 2 and last_move['end'] == (x + dx, y):
                        en_passant_target = (x + dx, y + forward)
                        legal_moves.append(en_passant_target)
        return legal_moves

    if move_type == 'knight':
        for dx, dy in piece.movement['offsets']:
            target = (x + dx, y + dy)
            if not in_bounds(target):
                continue
            occupant = get_piece_at_square(pieces, target, piece.stage)
            if occupant is None:
                legal_moves.append(target)
            elif occupant.color != piece.color and can_piece_attack_target(piece, occupant):
                legal_moves.append(target)
        return legal_moves

    if move_type == 'spider':
        outer_ring = {
            (0, -2), (-2, 0), (2, 0), (0, 2),
            (-1, -2), (-2, -1), (-2, 1), (-1, 2),
            (1, -2), (2, -1), (2, 1), (1, 2),
        }
        for dx, dy in piece.movement.get('directions', []):
            target = (x + dx, y + dy)
            if not in_bounds(target):
                continue
            occupant = get_piece_at_square(pieces, target, piece.stage)
            if occupant is None:
                legal_moves.append(target)
            elif occupant.color != piece.color and (dx, dy) in outer_ring and can_piece_attack_target(piece, occupant):
                legal_moves.append(target)
        return legal_moves

    if move_type == 'avian':
        directions = piece.movement.get('directions', [])
        max_steps = piece.movement.get('max_steps', 7)

        for dx, dy in directions:
            next_x = x + dx
            next_y = y + dy
            for _ in range(max_steps):
                if not in_bounds((next_x, next_y)):
                    break

                occupant = get_piece_at_square(pieces, (next_x, next_y), piece.stage)
                if occupant is None:
                    legal_moves.append((next_x, next_y))
                    next_x += dx
                    next_y += dy
                    continue

                if occupant.color != piece.color and (next_x, next_y) == (x + dx, y + dy):
                    if (dx, dy) == (0, 0):
                        legal_moves.append((next_x, next_y))
                    # Diagonal landing on an enemy is movement only; it is not a capture.
                    break

                break

        return legal_moves

    if move_type == 'mole':
        for dx, dy in piece.movement.get('directions', []):
            target = (x + dx, y + dy)
            if not in_bounds(target):
                continue
            occupant = get_piece_at_square(pieces, target, piece.stage)
            if occupant is None:
                legal_moves.append(target)
            elif occupant.color != piece.color and can_piece_attack_target(piece, occupant):
                legal_moves.append(target)

        return legal_moves

    if move_type == 'king':
        directions = piece.movement.get('directions', [])
        max_steps = piece.movement.get('max_steps', 1)
        for dx, dy in directions:
            next_x = x + dx
            next_y = y + dy
            for _ in range(max_steps):
                if not in_bounds((next_x, next_y)):
                    break
                occupant = get_piece_at_square(pieces, (next_x, next_y), piece.stage)
                if occupant is None:
                    legal_moves.append((next_x, next_y))
                else:
                    if occupant.color != piece.color and can_piece_attack_target(piece, occupant):
                        legal_moves.append((next_x, next_y))
                    break
                next_x += dx
                next_y += dy

        home_row = 0 if piece.color == 'black' else 7
        if not piece.has_moved:
            left_rook = get_piece_at_square(pieces, (0, home_row), piece.stage)
            right_rook = get_piece_at_square(pieces, (7, home_row), piece.stage)

            if left_rook is not None and left_rook.color == piece.color and left_rook.__class__.__name__ == 'Rook' and not left_rook.has_moved:
                if all(get_piece_at_square(pieces, (col, home_row), piece.stage) is None for col in range(1, 4)):
                    legal_moves.append((2, home_row))

            if right_rook is not None and right_rook.color == piece.color and right_rook.__class__.__name__ == 'Rook' and not right_rook.has_moved:
                if all(get_piece_at_square(pieces, (col, home_row), piece.stage) is None for col in range(5, 7)):
                    legal_moves.append((6, home_row))

        return legal_moves

    directions = piece.movement.get('directions', [])
    max_steps = piece.movement.get('max_steps', 1)
    for dx, dy in directions:
        next_x = x + dx
        next_y = y + dy
        for _ in range(max_steps):
            if not in_bounds((next_x, next_y)):
                break
            occupant = get_piece_at_square(pieces, (next_x, next_y), piece.stage)
            if occupant is not None:
                if occupant.color != piece.color and can_piece_attack_target(piece, occupant):
                    legal_moves.append((next_x, next_y))
                break
            legal_moves.append((next_x, next_y))
            next_x += dx
            next_y += dy

    return legal_moves


def get_legal_moves(piece, pieces):
    legal_moves = get_stage_local_moves(piece, pieces)
    legal_moves.extend(
        map_square_between_stages(target.position, target.stage, piece.stage)
        for target in get_cross_stage_attack_targets(piece, pieces)
    )
    if get_stage_shift_destinations(piece, pieces):
        legal_moves.append(piece.position)
    return list(dict.fromkeys(legal_moves))


def draw_board():
    for i in range(grid_size):
        for j in range(grid_size):
            rect_x = i * square_size
            rect_y = j * square_size
            stage_index = normalize_stage_index(current_stage)
            color = stages[stage_names[stage_index]][0] if (i + j) % 2 == 0 else stages[stage_names[stage_index]][1]
            pygame.draw.rect(screen, color, (rect_x, rect_y, square_size, square_size))

    for (web_x, web_y), owner in get_visible_webs().items():
        web_name = 'white_web' if owner == 'white' else 'black_web'
        if web_name not in web_images:
            web_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Trap Icons', f'{web_name}.png')
            try:
                web_image = pygame.image.load(web_path)
                web_images[web_name] = pygame.transform.smoothscale(web_image, (square_size, square_size))
            except FileNotFoundError:
                continue
        display_x, display_y = get_display_square((web_x, web_y), current_stage)
        web_rect = pygame.Rect(display_x * square_size, display_y * square_size, square_size, square_size)
        screen.blit(web_images[web_name], web_rect.topleft)

    shift_destinations = get_stage_shift_destinations(selected_piece, board_pieces) if selected_piece is not None else []
    showing_shift_destination = selected_piece is not None and current_stage in shift_destinations
    if selected_piece is not None and (selected_piece.stage == current_stage or showing_shift_destination):
        highlight_square = (
            get_stage_shift_target_square(selected_piece, current_stage)
            if showing_shift_destination and selected_piece.stage != current_stage
            else selected_piece.position
        )
        display_x, display_y = get_display_square(highlight_square, current_stage)
        selected_rect = pygame.Rect(
            display_x * square_size,
            display_y * square_size,
            square_size,
            square_size,
        )
        highlight = pygame.Surface((square_size, square_size), pygame.SRCALPHA)
        highlight_color = (255, 120, 120, 120) if showing_shift_destination else (255, 0, 0, 180)
        highlight.fill(highlight_color)
        screen.blit(highlight, selected_rect.topleft)

        if selected_piece.stage == current_stage:
            for move_x, move_y in get_legal_moves(selected_piece, board_pieces):
                if (move_x, move_y) == selected_piece.position:
                    continue
                display_move_x, display_move_y = get_display_square((move_x, move_y), current_stage)
                move_surface = pygame.Surface((square_size, square_size), pygame.SRCALPHA)
                move_surface.fill((255, 120, 120, 120))
                screen.blit(move_surface, (display_move_x * square_size, display_move_y * square_size))


def draw_game_over_overlay():
    if not game_over or winner is None:
        return

    overlay = pygame.Surface((grid_size * square_size, grid_size * square_size), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 165))
    screen.blit(overlay, (0, 0))

    font = pygame.font.Font(None, 72)
    message = font.render(f"{winner.capitalize()} Wins!", True, (255, 255, 255))
    message_rect = message.get_rect(center=(grid_size * square_size // 2, grid_size * square_size // 2 - 20))
    screen.blit(message, message_rect)

    sub_font = pygame.font.Font(None, 28)
    sub_text = sub_font.render('Press ESC to quit', True, (220, 220, 220))
    sub_rect = sub_text.get_rect(center=(grid_size * square_size // 2, grid_size * square_size // 2 + 35))
    screen.blit(sub_text, sub_rect)


def move_secondary_window_to_left_center(hwnd, width, height):
    if hwnd is None:
        return

    user32 = ctypes.windll.user32
    screen_width = user32.GetSystemMetrics(0)
    screen_height = user32.GetSystemMetrics(1)

    x = 20
    y = max(20, (screen_height - height) // 2 - 40)
    user32.MoveWindow(hwnd, x, y, width, height, True)


def move_hand_window_below_board(hwnd, width, height):
    if hwnd is None:
        return

    user32 = ctypes.windll.user32
    screen_width = user32.GetSystemMetrics(0)
    screen_height = user32.GetSystemMetrics(1)
    board_width = grid_size * square_size
    board_height = grid_size * square_size

    x = max(0, (screen_width - width) // 2)
    y = max(20, (board_height + 50))
    user32.MoveWindow(hwnd, x, y, width, height, True)


def move_pile_window_to_right_center(hwnd, width, height):
    if hwnd is None:
        return

    user32 = ctypes.windll.user32
    screen_width = user32.GetSystemMetrics(0)
    screen_height = user32.GetSystemMetrics(1)
    x = max(20, screen_width - width - 20)
    y = max(20, (screen_height - height) // 2)
    user32.MoveWindow(hwnd, x, y, width, height, True)


def get_stage_light_color(stage_index=None):
    if stage_index is None:
        stage_index = current_stage
    stage_index = normalize_stage_index(stage_index)
    return stages[stage_names[stage_index]][0]


def draw_ability_tag(info_screen, ability, y, info_width):
    tab_x = 22
    tab_width = info_width - 44
    tab_height = 82
    tab_rect = pygame.Rect(tab_x, y, tab_width, tab_height)
    pygame.draw.rect(info_screen, (54, 54, 62), tab_rect, border_radius=8)
    pygame.draw.rect(info_screen, (120, 120, 130), tab_rect, 1, border_radius=8)

    icon_size = 38
    icon_x = tab_x + 16
    icon_y = y + (tab_height - icon_size) // 2
    icon_path = ability.get('icon_path')
    icon = None
    if icon_path:
        full_icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), icon_path)
        if os.path.exists(full_icon_path):
            try:
                icon = pygame.transform.smoothscale(pygame.image.load(full_icon_path), (icon_size, icon_size))
            except pygame.error:
                pass

    if icon is not None:
        info_screen.blit(icon, (icon_x, icon_y))
    else:
        placeholder = pygame.Rect(icon_x, icon_y, icon_size, icon_size)
        pygame.draw.rect(info_screen, ability.get('fallback_color', (200, 200, 200)), placeholder, border_radius=3)

    title_x = icon_x + 46
    title_y = y + 14
    title_text = pygame.font.Font(None, 21).render(ability['name'], True, (245, 245, 245))
    info_screen.blit(title_text, (title_x, title_y))

    wrapped = textwrap.wrap(ability.get('description', ''), width=46)
    desc_font = pygame.font.Font(None, 15)
    for index, line in enumerate(wrapped[:2]):
        line_surface = desc_font.render(line, True, (210, 210, 220))
        info_screen.blit(line_surface, (title_x, title_y + 20 + index * 15))


def run_info_window(queue):
    info_width = 400
    info_height = 700
    reference_entries = get_piece_reference_pages()

    pygame.init()
    info_screen = pygame.display.set_mode((info_width, info_height))
    hwnd = pygame.display.get_wm_info()['window']
    move_secondary_window_to_left_center(hwnd, info_width, info_height)
    pygame.display.set_caption('Chess Piece Index')
    clock = pygame.time.Clock()
    page_index = 0
    subpage_index = 0
    stage_index = normalize_stage_index(current_stage)

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                return
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    pygame.quit()
                    return
                if event.key == pygame.K_TAB:
                    pygame.quit()
                    return
                if event.key == pygame.K_LEFT:
                    page_index = (page_index - 1) % len(reference_entries)
                    subpage_index = 0
                if event.key == pygame.K_RIGHT:
                    page_index = (page_index + 1) % len(reference_entries)
                    subpage_index = 0
                if event.key == pygame.K_UP:
                    entry_subpages = reference_entries[page_index].get('subpages', [])
                    if entry_subpages:
                        subpage_index = (subpage_index - 1) % len(entry_subpages)
                if event.key == pygame.K_DOWN:
                    entry_subpages = reference_entries[page_index].get('subpages', [])
                    if entry_subpages:
                        subpage_index = (subpage_index + 1) % len(entry_subpages)

        try:
            while True:
                message = queue.get_nowait()
                if message.get('close'):
                    pygame.quit()
                    return
                if 'stage_index' in message:
                    stage_index = normalize_stage_index(message['stage_index'])
        except Exception:
            pass

        stage_background = get_stage_light_color(stage_index)
        info_screen.fill((18, 18, 24))
        pygame.draw.rect(info_screen, (90, 90, 105), info_screen.get_rect(), 3)

        title_font = pygame.font.Font(None, 44)
        title = title_font.render('Piece Index', True, (255, 255, 255))
        title_rect = title.get_rect()
        title_rect.x = 18
        title_rect.centery = 42
        info_screen.blit(title, title_rect)

        divider = pygame.Surface((info_width - 32, 2), pygame.SRCALPHA)
        divider.fill((120, 120, 130, 220))
        info_screen.blit(divider, (16, 74))

        entry = reference_entries[page_index]
        piece = entry['piece']
        entry_subpages = entry.get('subpages', [])
        subpage = entry_subpages[subpage_index] if entry_subpages else {'label': '', 'pattern': entry.get('pattern', []), 'attacks': entry.get('attacks', [])}

        preview_rect = pygame.Rect(26, 100, 120, 120)
        pygame.draw.rect(info_screen, stage_background, preview_rect)
        pygame.draw.rect(info_screen, (90, 90, 110), preview_rect, 2)

        if piece.image is not None:
            scaled = pygame.transform.smoothscale(piece.image, (88, 88))
            preview = scaled.get_rect(center=preview_rect.center)
            info_screen.blit(scaled, preview)
        else:
            symbol = pygame.font.Font(None, 72).render(piece.symbol, True, (255, 255, 255))
            symbol_rect = symbol.get_rect(center=preview_rect.center)
            info_screen.blit(symbol, symbol_rect)

        name_font = pygame.font.Font(None, 32)
        name_text = name_font.render(entry['name'], True, (255, 255, 255))
        info_screen.blit(name_text, (170, 118))

        if entry_subpages:
            subtype_font = pygame.font.Font(None, 20)
            subtype_text = subtype_font.render(subpage['label'], True, (200, 200, 220))
            info_screen.blit(subtype_text, (170, 155))

        board_x = 30
        board_y = 255
        board_size = 210
        cell_size = board_size // 5
        for row in range(5):
            for col in range(5):
                rect = pygame.Rect(board_x + col * cell_size, board_y + row * cell_size, cell_size, cell_size)
                pygame.draw.rect(info_screen, (60, 60, 70), rect, 1)

        center = (2, 2)
        move_positions = {(center[0] + dx, center[1] + dy) for dx, dy in subpage.get('pattern', [])}
        attack_positions = {(center[0] + dx, center[1] + dy) for dx, dy in subpage.get('attacks', [])}

        for cx, cy in move_positions:
            if 0 <= cx < 5 and 0 <= cy < 5:
                rect = pygame.Rect(board_x + cx * cell_size, board_y + cy * cell_size, cell_size, cell_size)
                pygame.draw.rect(info_screen, (140, 190, 255), rect, 0)
                pygame.draw.rect(info_screen, (220, 220, 255), rect, 2)

        for cx, cy in attack_positions:
            if 0 <= cx < 5 and 0 <= cy < 5:
                rect = pygame.Rect(board_x + cx * cell_size, board_y + cy * cell_size, cell_size, cell_size)
                pygame.draw.rect(info_screen, (255, 170, 90), rect, 0)
                pygame.draw.rect(info_screen, (255, 220, 150), rect, 2)

        piece_rect = pygame.Rect(board_x + center[0] * cell_size, board_y + center[1] * cell_size, cell_size, cell_size)
        pygame.draw.rect(info_screen, (255, 160, 80), piece_rect, 3)

        if piece.image is not None:
            piece_scale = pygame.transform.smoothscale(piece.image, (cell_size - 12, cell_size - 12))
            piece_draw_rect = piece_scale.get_rect(center=piece_rect.center)
            info_screen.blit(piece_scale, piece_draw_rect)
        else:
            symbol = pygame.font.Font(None, 40).render(piece.symbol, True, (255, 255, 255))
            symbol_rect = symbol.get_rect(center=piece_rect.center)
            info_screen.blit(symbol, symbol_rect)

        board_label = pygame.font.Font(None, 20).render('Move pattern', True, (200, 200, 220))
        info_screen.blit(board_label, (30, 225))

        for ability_index, ability in enumerate(entry.get('abilities', [])):
            draw_ability_tag(info_screen, ability, 488 + ability_index * 88, info_width)

        footer = pygame.font.Font(None, 18).render(f'Page {page_index + 1} / {len(reference_entries)}', True, (180, 180, 180))
        info_screen.blit(footer, (18, info_height - 26))

        pygame.display.flip()
        clock.tick(30)


def toggle_secondary_window():
    global secondary_window_process, secondary_window_queue

    if secondary_window_process is not None and secondary_window_process.is_alive():
        if secondary_window_queue is not None:
            secondary_window_queue.put({'close': True})
        secondary_window_process.join(timeout=0.2)
        if secondary_window_process.is_alive():
            secondary_window_process.terminate()
            secondary_window_process.join(timeout=0.5)
        secondary_window_process = None
        secondary_window_queue = None
        return

    secondary_window_queue = mp.Queue()
    secondary_window_process = mp.Process(
        target=run_info_window,
        args=(secondary_window_queue,),
        daemon=True,
    )
    secondary_window_process.start()


def get_hand_card_rects(hand_width, card_count):
    visible_count = min(card_count, hand_size_limit)
    total_width = visible_count * hand_card_width + max(0, visible_count - 1) * hand_card_gap
    start_x = (hand_width - total_width) // 2
    return [
        pygame.Rect(start_x + index * (hand_card_width + hand_card_gap), 34, hand_card_width, hand_card_height)
        for index in range(visible_count)
    ]


def get_hand_card_index(mouse_pos, hand_width, card_count, active_index=None):
    card_rects = get_hand_card_rects(hand_width, card_count)
    if active_index is not None and 0 <= active_index < len(card_rects):
        if card_rects[active_index].move(0, -10).collidepoint(mouse_pos):
            return active_index

    for index, card_rect in enumerate(card_rects):
        if card_rect.collidepoint(mouse_pos):
            return index
    return None


def render_hand_card(card, image_cache):
    card_surface = pygame.Surface((hand_card_width, hand_card_height), pygame.SRCALPHA)
    card_rect = card_surface.get_rect()
    pygame.draw.rect(card_surface, (242, 240, 230), card_rect, border_radius=6)
    pygame.draw.rect(card_surface, (130, 130, 135), card_rect, 1, border_radius=6)

    image_path = card.get('image_path')
    image = None
    if image_path:
        if not os.path.isabs(image_path):
            image_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), image_path)
        if image_path not in image_cache and os.path.exists(image_path):
            try:
                loaded = pygame.image.load(image_path)
                image_cache[image_path] = pygame.transform.smoothscale(loaded, (hand_card_width - 12, hand_card_height - 12))
            except pygame.error:
                image_cache[image_path] = None
        image = image_cache.get(image_path)

    if image is not None:
        card_surface.blit(image, image.get_rect(center=card_rect.center))
        return card_surface

    if card.get('card_type') == 'uno_action':
        uno_colors = {
            'red': (195, 55, 65),
            'yellow': (235, 195, 55),
            'green': (55, 145, 85),
            'blue': (55, 115, 190),
            'wild': (80, 75, 95),
        }
        face_rect = card_rect.inflate(-10, -10)
        pygame.draw.rect(card_surface, uno_colors.get(card['color'], uno_colors['wild']), face_rect, border_radius=7)
        text_color = (35, 35, 40) if card['color'] == 'yellow' else (255, 255, 255)
        if card['label'] == 'COLOR SWAP':
            for index, line in enumerate(('COLOR', 'SWAP')):
                label_surface = pygame.font.Font(None, 21).render(line, True, text_color)
                label_rect = label_surface.get_rect(center=(card_rect.centerx, card_rect.centery - 9 + index * 19))
                card_surface.blit(label_surface, label_rect)
        else:
            font_size = 22 if len(card['label']) > 3 else 34
            label_surface = pygame.font.Font(None, font_size).render(card['label'], True, text_color)
            card_surface.blit(label_surface, label_surface.get_rect(center=(card_rect.centerx, card_rect.centery - 4)))
        color_label = pygame.font.Font(None, 14).render(card['suit'].upper(), True, text_color)
        card_surface.blit(color_label, color_label.get_rect(center=(card_rect.centerx, card_rect.bottom - 17)))
        return card_surface

    text_color = (180, 35, 55) if card.get('color') == 'red' else (35, 35, 40)
    if card['suit'] == 'Joker':
        rank_surface = pygame.font.Font(None, 24).render('JOKER', True, text_color)
        card_surface.blit(rank_surface, rank_surface.get_rect(center=(card_rect.centerx, card_rect.centery - 8)))
        color_surface = pygame.font.Font(None, 18).render(card['color'].upper(), True, text_color)
        card_surface.blit(color_surface, color_surface.get_rect(center=(card_rect.centerx, card_rect.centery + 14)))
    else:
        rank_surface = pygame.font.Font(None, 36).render(card['rank'], True, text_color)
        card_surface.blit(rank_surface, (8, 6))
        suit_surface = pygame.font.Font(None, 17).render(card['suit'].upper(), True, text_color)
        card_surface.blit(suit_surface, suit_surface.get_rect(center=(card_rect.centerx, 78)))
    return card_surface


def draw_burning_card(hand_screen, burn_animation, image_cache):
    elapsed = pygame.time.get_ticks() - burn_animation['started_at']
    progress = min(1.0, elapsed / burn_animation['duration'])
    card_rect = burn_animation['rect']
    card_surface = render_hand_card(burn_animation['card'], image_cache)

    scale = max(0.08, 1.0 - progress * 0.9)
    burning_surface = pygame.transform.rotozoom(card_surface, progress * 32, scale)
    burning_surface.set_alpha(int(255 * (1.0 - progress)))
    burning_rect = burning_surface.get_rect(center=(card_rect.centerx, card_rect.centery - progress * 18))
    hand_screen.blit(burning_surface, burning_rect)

    background = (24, 24, 30)
    ember = (220, 105, 35)
    ash = (125, 125, 125)
    ash_progress = min(1.0, progress * 2)
    fade = 1.0 - progress
    particle_color = tuple(
        int(background[channel] * (1 - fade) + (ember[channel] * (1 - ash_progress) + ash[channel] * ash_progress) * fade)
        for channel in range(3)
    )
    for particle in burn_animation['particles']:
        particle_x = card_rect.centerx + particle['dx'] * progress
        particle_y = card_rect.centery + particle['dy'] * progress - particle['rise'] * progress
        radius = max(1, int(particle['size'] * fade))
        pygame.draw.circle(hand_screen, particle_color, (int(particle_x), int(particle_y)), radius)

    return progress >= 1.0


def draw_hand_cards(hand_screen, cards, image_cache, active_index=None, burn_animation=None, hidden_card_id=None, invalid_animation=None):
    visible_cards = cards[:hand_size_limit]
    card_rects = get_hand_card_rects(hand_screen.get_width(), len(visible_cards))
    burning_card_id = burn_animation['card_id'] if burn_animation is not None else None

    for index, (card, base_rect) in enumerate(zip(visible_cards, card_rects)):
        card_id = card.get('card_id')
        if card_id in (burning_card_id, hidden_card_id):
            continue
        card_rect = base_rect.move(0, -10) if index == active_index else base_rect
        card_surface = render_hand_card(card, image_cache)
        if invalid_animation is not None and card_id == invalid_animation['card_id']:
            elapsed = pygame.time.get_ticks() - invalid_animation['started_at']
            progress = min(1.0, elapsed / invalid_animation['duration'])
            fade = 1.0 - progress
            shake_x = int(math.sin(elapsed * 0.075) * 7 * fade)
            flash_alpha = int((1 + math.sin(elapsed * 0.04)) * 75 * fade)
            flash = pygame.Surface(card_surface.get_size(), pygame.SRCALPHA)
            flash.fill((255, 35, 35, flash_alpha))
            card_surface.blit(flash, (0, 0))
            card_rect.x += shake_x
        hand_screen.blit(card_surface, card_rect)

    if burn_animation is not None:
        return draw_burning_card(hand_screen, burn_animation, image_cache)
    return False


def run_hand_window(queue, command_queue):
    hand_width = 860
    hand_height = 150

    pygame.init()
    hand_screen = pygame.display.set_mode((hand_width, hand_height))
    hwnd = pygame.display.get_wm_info()['window']
    move_hand_window_below_board(hwnd, hand_width, hand_height)
    pygame.display.set_caption('Card Hand')
    clock = pygame.time.Clock()
    current_hand = []
    current_player = 'white'
    top_played_card = None
    image_cache = {}
    active_card_index = None
    burn_animation = None
    invalid_animation = None
    awaiting_removal_card_id = None
    burn_duration = 900
    invalid_feedback_duration = 420

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                return
            if event.type == pygame.MOUSEMOTION:
                active_card_index = get_hand_card_index(
                    event.pos,
                    hand_width,
                    len(current_hand),
                    active_card_index,
                )
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and burn_animation is None and current_hand:
                clicked_index = get_hand_card_index(event.pos, hand_width, len(current_hand), active_card_index)
                if clicked_index is not None:
                    active_card_index = clicked_index
                    card = current_hand[clicked_index]
                    if not can_play_card(card, top_played_card):
                        invalid_animation = {
                            'card_id': card['card_id'],
                            'started_at': pygame.time.get_ticks(),
                            'duration': invalid_feedback_duration,
                        }
                        continue
                    invalid_animation = None
                    card_rect = get_hand_card_rects(hand_width, len(current_hand))[clicked_index].move(0, -10)
                    burn_animation = {
                        'card': card,
                        'card_id': card['card_id'],
                        'player': current_player,
                        'rect': card_rect,
                        'started_at': pygame.time.get_ticks(),
                        'duration': burn_duration,
                        'particles': [
                            {
                                'dx': random.uniform(-36, 36),
                                'dy': random.uniform(-16, 20),
                                'rise': random.uniform(18, 58),
                                'size': random.randint(2, 5),
                            }
                            for _ in range(22)
                        ],
                    }
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE or event.key == pygame.K_h:
                    pygame.quit()
                    return

        try:
            while True:
                message = queue.get_nowait()
                if message.get('close'):
                    pygame.quit()
                    return
                if 'hand' in message:
                    current_hand = message['hand']
                    current_player = message.get('turn', current_player)
                    top_played_card = message.get('top_played_card', top_played_card)
                    current_card_ids = {card['card_id'] for card in current_hand}
                    if message.get('rejected_card_id') == awaiting_removal_card_id:
                        awaiting_removal_card_id = None
                    if awaiting_removal_card_id not in current_card_ids:
                        awaiting_removal_card_id = None
                    if not current_hand:
                        active_card_index = None
                    elif active_card_index is not None:
                        active_card_index %= len(current_hand)
        except Exception:
            pass

        hand_screen.fill((24, 24, 30))
        pygame.draw.rect(hand_screen, (90, 90, 105), hand_screen.get_rect(), 3)
        label = pygame.font.Font(None, 20).render(
            f'{current_player.upper()} HAND  {len(current_hand)} / {hand_size_limit}',
            True,
            (220, 220, 225),
        )
        hand_screen.blit(label, (14, 6))
        burn_finished = draw_hand_cards(
            hand_screen,
            current_hand,
            image_cache,
            active_card_index,
            burn_animation,
            awaiting_removal_card_id,
            invalid_animation,
        )
        pygame.display.flip()
        if burn_finished and burn_animation is not None:
            command_queue.put({
                'action': 'use_card',
                'player': burn_animation['player'],
                'card_id': burn_animation['card_id'],
            })
            awaiting_removal_card_id = burn_animation['card_id']
            burn_animation = None
        clock.tick(30)


def run_pile_window(queue):
    pile_width = 330
    pile_height = 300

    pygame.init()
    pile_screen = pygame.display.set_mode((pile_width, pile_height))
    hwnd = pygame.display.get_wm_info()['window']
    move_pile_window_to_right_center(hwnd, pile_width, pile_height)
    pygame.display.set_caption('Draw / Play Piles')
    clock = pygame.time.Clock()
    draw_count = 0
    play_count = 0
    top_played_card = None
    image_cache = {}

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                return
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                pygame.quit()
                return

        while True:
            try:
                message = queue.get_nowait()
            except Empty:
                break
            if message.get('close'):
                pygame.quit()
                return
            draw_count = message.get('draw_count', draw_count)
            play_count = message.get('play_count', play_count)
            top_played_card = message.get('top_played_card', top_played_card)

        pile_screen.fill((24, 24, 30))
        pygame.draw.rect(pile_screen, (90, 90, 105), pile_screen.get_rect(), 3)
        title = pygame.font.Font(None, 30).render('CARD PILES', True, (240, 240, 245))
        pile_screen.blit(title, title.get_rect(center=(pile_width // 2, 28)))

        labels = (('DRAW PILE', 95), ('PLAY PILE', 235))
        for label, center_x in labels:
            label_surface = pygame.font.Font(None, 22).render(label, True, (220, 220, 225))
            pile_screen.blit(label_surface, label_surface.get_rect(center=(center_x, 66)))

        draw_card_rect = pygame.Rect(47, 82, hand_card_width, hand_card_height)
        if draw_count:
            pygame.draw.rect(pile_screen, (45, 63, 100), draw_card_rect, border_radius=6)
            pygame.draw.rect(pile_screen, (170, 180, 205), draw_card_rect, 2, border_radius=6)
            pygame.draw.rect(pile_screen, (75, 98, 145), draw_card_rect.inflate(-12, -12), 2, border_radius=4)
        else:
            pygame.draw.rect(pile_screen, (50, 50, 58), draw_card_rect, border_radius=6)
            pygame.draw.rect(pile_screen, (110, 110, 120), draw_card_rect, 1, border_radius=6)

        play_card_rect = pygame.Rect(187, 82, hand_card_width, hand_card_height)
        if top_played_card is not None:
            pile_screen.blit(render_hand_card(top_played_card, image_cache), play_card_rect)
        else:
            pygame.draw.rect(pile_screen, (50, 50, 58), play_card_rect, border_radius=6)
            pygame.draw.rect(pile_screen, (110, 110, 120), play_card_rect, 1, border_radius=6)

        count_font = pygame.font.Font(None, 22)
        draw_count_surface = count_font.render(str(draw_count), True, (240, 240, 245))
        play_count_surface = count_font.render(str(play_count), True, (240, 240, 245))
        pile_screen.blit(draw_count_surface, draw_count_surface.get_rect(center=(95, 207)))
        pile_screen.blit(play_count_surface, play_count_surface.get_rect(center=(235, 207)))

        hint = pygame.font.Font(None, 18).render(
            'Used cards reshuffle when the draw pile is empty.',
            True,
            (175, 175, 185),
        )
        pile_screen.blit(hint, hint.get_rect(center=(pile_width // 2, 263)))

        pygame.display.flip()
        clock.tick(30)


def toggle_hand_window():
    global hand_window_process, hand_window_queue, hand_command_queue

    if hand_window_process is not None and hand_window_process.is_alive():
        if hand_window_queue is not None:
            hand_window_queue.put({'close': True})
        hand_window_process.join(timeout=0.2)
        if hand_window_process.is_alive():
            hand_window_process.terminate()
            hand_window_process.join(timeout=0.5)
        hand_window_process = None
        hand_window_queue = None
        hand_command_queue = None
        return

    hand_window_queue = mp.Queue()
    hand_command_queue = mp.Queue()
    hand_window_process = mp.Process(
        target=run_hand_window,
        args=(hand_window_queue, hand_command_queue),
        daemon=True,
    )
    hand_window_process.start()
    send_hand_window_state()


def toggle_pile_window():
    global pile_window_process, pile_window_queue

    if pile_window_process is not None and pile_window_process.is_alive():
        if pile_window_queue is not None:
            pile_window_queue.put({'close': True})
        pile_window_process.join(timeout=0.2)
        if pile_window_process.is_alive():
            pile_window_process.terminate()
            pile_window_process.join(timeout=0.5)
        pile_window_process = None
        pile_window_queue = None
        return

    pile_window_queue = mp.Queue()
    pile_window_process = mp.Process(
        target=run_pile_window,
        args=(pile_window_queue,),
        daemon=True,
    )
    pile_window_process.start()
    send_pile_window_state()


def send_secondary_window_state():
    if secondary_window_queue is None or secondary_window_process is None:
        return
    if not secondary_window_process.is_alive():
        return
    try:
        secondary_window_queue.put({
            'turn': current_turn,
            'winner': winner,
            'checked': bool(get_checked_kings(board_pieces)),
            'game_over': game_over,
            'stage_index': normalize_stage_index(current_stage),
        }, block=False)
    except Exception:
        pass


def send_hand_window_state(rejected_card_id=None):
    if hand_window_queue is None or hand_window_process is None:
        return
    if not hand_window_process.is_alive():
        return
    try:
        message = {
            'hand': [card.display_data() for card in hands[current_turn]],
            'turn': current_turn,
            'hand_size_limit': hand_size_limit,
            'top_played_card': played_pile[-1].display_data() if played_pile else None,
        }
        if rejected_card_id is not None:
            message['rejected_card_id'] = rejected_card_id
        hand_window_queue.put(message, block=False)
    except Exception:
        pass


def send_pile_window_state():
    if pile_window_queue is None or pile_window_process is None:
        return
    if not pile_window_process.is_alive():
        return
    pile_window_queue.put({
        'draw_count': len(draw_pile),
        'play_count': len(played_pile),
        'top_played_card': played_pile[-1].display_data() if played_pile else None,
    }, block=False)


def use_card_from_hand(player, card_id):
    player_hand = hands.get(player, [])
    card = next((card for card in player_hand if card.card_id == card_id), None)
    top_card = played_pile[-1].display_data() if played_pile else None
    if card is None or not can_play_card(card.display_data(), top_card) or not card.use():
        return False
    if getattr(card, 'action', None) == 'reverse':
        reverse_stage_colors(reverse_card_stages[card.color])
    player_hand.remove(card)
    played_pile.append(card)
    opposing_player = 'black' if player == 'white' else 'white'
    if getattr(card, 'action', None) == 'draw_two':
        draw_cards_for_player(opposing_player, 2)
    elif getattr(card, 'action', None) == 'draw_four':
        draw_cards_for_player(opposing_player, 4)
    send_hand_window_state()
    send_pile_window_state()
    return True


def process_hand_window_commands():
    if hand_command_queue is None:
        return
    while True:
        try:
            command = hand_command_queue.get_nowait()
        except Exception:
            return
        if command.get('action') == 'use_card':
            if not use_card_from_hand(command.get('player'), command.get('card_id')):
                send_hand_window_state(rejected_card_id=command.get('card_id'))


def begin_turn(color):
    global current_turn
    current_turn = color
    draw_card_for_turn(color)
    send_hand_window_state()
    send_pile_window_state()


def draw_piece(piece, x=None, y=None):
    if piece.stage != current_stage:
        return
    if x is None or y is None:
        x, y = piece.position
    x, y = get_display_square((x, y), piece.stage)

    rotation = get_king_shake_angle(piece, board_pieces)
    center_x = x * square_size + square_size // 2
    center_y = y * square_size + square_size // 2

    if piece.image is None:
        font = pygame.font.Font(None, 72)
        color = (255, 255, 255) if piece.color == 'white' else (0, 0, 0)
        text = font.render(piece.symbol, True, color)
        rotated_text = pygame.transform.rotate(text, rotation)
        text_rect = rotated_text.get_rect(center=(center_x, center_y))
        screen.blit(rotated_text, text_rect)
    else:
        rotated_image = pygame.transform.rotate(piece.image, rotation)
        image_rect = rotated_image.get_rect(center=(center_x, center_y))
        screen.blit(rotated_image, image_rect.topleft)


def draw_all_pieces(pieces):
    for piece in pieces:
        if piece.stage == current_stage:
            draw_piece(piece, *piece.position)


def get_clicked_piece(mouse_pos, pieces):
    clicked_square = get_square_from_mouse(mouse_pos)
    if clicked_square is None:
        return None

    for piece in reversed(pieces):
        if piece.stage == current_stage and piece.position == clicked_square and piece.trapped_until <= 0:
            return piece
    return None


def move_selected_piece_to(target_square, pieces, target_stage=None):
    global selected_piece, current_turn, last_move, en_passant_target, winner, game_over, current_stage

    if selected_piece is None or game_over:
        return

    if selected_piece.trapped_until > 0:
        return

    if selected_piece.color != current_turn:
        return

    if get_piece_ability(selected_piece, 'stage_shift'):
        destinations = get_stage_shift_destinations(selected_piece, pieces)
        source_layer_click = target_stage is None and current_stage == selected_piece.stage and target_square == selected_piece.position
        resolved_target_stage = target_stage
        if resolved_target_stage is None:
            if current_stage in destinations and current_stage != selected_piece.stage:
                resolved_target_stage = current_stage
            elif source_layer_click and destinations:
                resolved_target_stage = destinations[0]

        if resolved_target_stage in destinations:
            destination_square = get_stage_shift_target_square(selected_piece, resolved_target_stage)
            if target_square == destination_square or source_layer_click:
                start_square = selected_piece.position
                selected_piece.position = destination_square
                selected_piece.stage = resolved_target_stage
                current_stage = resolved_target_stage
                selected_piece.has_moved = True
                last_move = {'piece': selected_piece, 'start': start_square, 'end': destination_square, 'stage_shift': True}
                en_passant_target = None
                selected_piece = None
                if not game_over:
                    begin_turn('black' if current_turn == 'white' else 'white')
                return

    legal_moves = get_legal_moves(selected_piece, pieces)
    if target_square not in legal_moves:
        return

    start_square = selected_piece.position
    target_piece = get_piece_at_square(pieces, target_square, selected_piece.stage)

    if target_piece is None:
        target_piece = next((
            target for target in get_cross_stage_attack_targets(selected_piece, pieces)
            if map_square_between_stages(target.position, target.stage, selected_piece.stage) == target_square
        ), None)

    if selected_piece.__class__.__name__ == 'Pawn' and target_square == en_passant_target:
        captured_pawn_square = (target_square[0], start_square[1])
        captured_pawn = get_piece_at_square(pieces, captured_pawn_square, selected_piece.stage)
        if captured_pawn is not None:
            pieces.remove(captured_pawn)

    if target_piece is not None and target_piece.color != selected_piece.color:
        if target_piece.__class__.__name__ == 'King':
            winner = selected_piece.color
            game_over = True
        pieces.remove(target_piece)

    if selected_piece.__class__.__name__ == 'King' and abs(target_square[0] - start_square[0]) == 2:
        rook_start = (0, start_square[1]) if target_square[0] < start_square[0] else (7, start_square[1])
        rook_target = (3, start_square[1]) if target_square[0] < start_square[0] else (5, start_square[1])
        rook = get_piece_at_square(pieces, rook_start, selected_piece.stage)
        if rook is not None:
            rook.position = rook_target

    selected_piece.position = target_square
    selected_piece.has_moved = True
    last_move = {'piece': selected_piece, 'start': start_square, 'end': target_square}
    en_passant_target = None

    if selected_piece.__class__.__name__ == 'Spider':
        web_tiles[(selected_piece.stage, start_square[0], start_square[1])] = selected_piece.color

    if selected_piece.trapped_until <= 0:
        web_key = (selected_piece.stage, selected_piece.position[0], selected_piece.position[1])
        enemy_web_owner = web_tiles.get(web_key)
        if enemy_web_owner is not None and enemy_web_owner != selected_piece.color:
            selected_piece.trapped_until = 1
            selected_piece.just_trapped = True
            selected_piece.web_square = selected_piece.position
            web_tiles.pop(web_key, None)

    if selected_piece.__class__.__name__ == 'Pawn' and abs(target_square[1] - start_square[1]) == 2:
        en_passant_target = (target_square[0], (start_square[1] + target_square[1]) // 2)

    if selected_piece.__class__.__name__ == 'Rook' and not selected_piece.has_moved:
        selected_piece.has_moved = True

    ended_turn = current_turn
    selected_piece = None
    if not game_over:
        next_turn = 'black' if current_turn == 'white' else 'white'
        for piece in pieces:
            if piece.trapped_until > 0 and piece.color == ended_turn:
                if piece.just_trapped:
                    piece.just_trapped = False
                else:
                    piece.trapped_until -= 1
                    if piece.trapped_until <= 0:
                        piece.trapped_until = 0
                        piece.web_square = None
        begin_turn(next_turn)


screen = pygame.display.set_mode((grid_size * square_size, grid_size * square_size))
pygame.display.set_caption('Chess of a Million Pieces')
board_pieces = create_initial_board()
reset_card_game()
begin_turn('white')


def main():
    global selected_piece, current_turn, last_move, en_passant_target, winner, game_over, board_pieces, current_stage

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_TAB:
                    toggle_secondary_window()
                elif event.key == pygame.K_h:
                    toggle_hand_window()
                    toggle_pile_window()
                elif event.key == pygame.K_r:
                    selected_piece = None
                    current_turn = 'white'
                    last_move = None
                    en_passant_target = None
                    winner = None
                    game_over = False
                    web_tiles.clear()
                    rotated_stages.clear()
                    board_pieces = create_initial_board()
                    reset_card_game()
                    begin_turn('white')
                elif not game_over and event.key == pygame.K_UP:
                    current_stage = normalize_stage_index(current_stage - 1)
                elif not game_over and event.key == pygame.K_DOWN:
                    current_stage = normalize_stage_index(current_stage + 1)
            elif not game_over and event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                clicked_square = get_square_from_mouse(event.pos)
                clicked_piece = get_clicked_piece(event.pos, board_pieces)

                if selected_piece is not None:
                    shift_destinations = get_stage_shift_destinations(selected_piece, board_pieces)
                    if selected_piece.stage == current_stage and clicked_square in get_legal_moves(selected_piece, board_pieces):
                        move_selected_piece_to(clicked_square, board_pieces)
                    elif current_stage in shift_destinations and clicked_square == get_stage_shift_target_square(selected_piece, current_stage):
                        move_selected_piece_to(clicked_square, board_pieces, current_stage)
                    elif clicked_piece is not None and clicked_piece.color == current_turn:
                        selected_piece = clicked_piece
                    else:
                        selected_piece = None
                elif clicked_piece is not None and clicked_piece.color == current_turn:
                    selected_piece = clicked_piece

                if selected_piece is not None:
                    print(f"{current_turn}'s turn - selected {selected_piece.color} {selected_piece.__class__.__name__} at {selected_piece.position}")

        process_hand_window_commands()
        current_stage = normalize_stage_index(current_stage)
        send_secondary_window_state()
        send_pile_window_state()
        draw_board()
        draw_all_pieces(board_pieces)
        draw_game_over_overlay()
        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    main()
