import ctypes
import copy
import math
import multiprocessing as mp
import os
from queue import Empty
import random
import textwrap

import pygame
import card_data
import piece_data
import weather_data

pygame.init()

grid_size = 8
expanded_grid_width = 50
expanded_left_columns = expanded_grid_width // 2
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
stage_widths = {stage: grid_size for stage in range(len(stage_names))}
stage_left_edges = {stage: 0 for stage in range(len(stage_names))}
stage_scroll_offsets = {stage: 0 for stage in range(len(stage_names))}
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
currency_window_process = None
currency_window_queue = None
weather_window_process = None
weather_window_queue = None
weather_window_last_state = None
debug_card_window_process = None
debug_card_window_queue = None
debug_card_command_queue = None
debug_cards = []
hands = {'white': [], 'black': []}
draw_pile = []
played_pile = []
currencies = {
    'white': {'gold': 0, 'gems': 0, 'tokens': 0},
    'black': {'gold': 0, 'gems': 0, 'tokens': 0},
}
weather_day = 1
weather_turn_counts = {'white': 0, 'black': 0}
weather_forecasts = {
    stage: [random.choice(weather_data.WEATHER_CONDITIONS_BY_STAGE[stage_names[stage]]) for _ in range(7)]
    for stage in range(len(stage_names))
}
crystal_haze_hallucinations = []
crystal_haze_source_ids = set()
crystal_haze_weather_key = None
storm_cloud_tiles = set()
storm_cloud_weather_key = None
storm_piece_exposure = {}
storm_shocked_pieces = {}
storm_turn_counts = {'white': 0, 'black': 0}
cancel_played_this_turn = False
skipped_turns = {'white': 0, 'black': 0}
rotated_stages = set()
reverse_card_stages = {'green': 1, 'blue': 0, 'yellow': 2, 'red': 3}


def reset_card_game():
    global draw_pile, played_pile, cancel_played_this_turn
    global weather_day
    global storm_cloud_tiles, storm_cloud_weather_key, storm_piece_exposure, storm_shocked_pieces
    draw_pile = card_data.create_deck()
    random.shuffle(draw_pile)
    played_pile = [draw_pile.pop()]
    cancel_played_this_turn = False
    skipped_turns.update({'white': 0, 'black': 0})
    for hand in hands.values():
        hand.clear()
    for balances in currencies.values():
        balances.update({'gold': 0, 'gems': 0, 'tokens': 0})
    weather_day = 1
    weather_turn_counts.update({'white': 0, 'black': 0})
    storm_turn_counts.update({'white': 0, 'black': 0})
    storm_cloud_tiles = set()
    storm_cloud_weather_key = None
    storm_piece_exposure.clear()
    storm_shocked_pieces.clear()
    for stage in weather_forecasts:
        weather_forecasts[stage] = [
            random.choice(weather_data.WEATHER_CONDITIONS_BY_STAGE[stage_names[stage]])
            for _ in range(7)
        ]
    send_currency_window_state()
    send_weather_window_state()


def advance_weather_turn(color):
    global weather_day
    weather_turn_counts[color] += 1
    if all(turns >= 2 for turns in weather_turn_counts.values()):
        weather_day += 1
        for stage, forecast in weather_forecasts.items():
            forecast.pop(0)
            forecast.append(random.choice(weather_data.WEATHER_CONDITIONS_BY_STAGE[stage_names[stage]]))
        weather_turn_counts.update({'white': 0, 'black': 0})
    send_weather_window_state()


def award_gold(color, amount):
    currencies[color]['gold'] += amount
    send_currency_window_state()


def can_play_card(card, top_card):
    if top_card is None:
        return True

    card_is_uno = card.get('card_type') == 'uno_action'
    top_is_uno = top_card.get('card_type') == 'uno_action'
    card_color = card.get('color', '').lower()
    top_color = top_card.get('color', '').lower()
    if (card_is_uno and card_color == 'wild') or (top_is_uno and top_color == 'wild'):
        return True

    if card_is_uno and top_is_uno:
        same_type = card.get('action') == top_card.get('action')
    elif card_is_uno or top_is_uno:
        same_type = False
    else:
        same_type = card.get('rank') == top_card.get('rank')

    return same_type or card_color == top_color


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
    stage = normalize_stage_index(stage)
    if stage in rotated_stages:
        return (
            stage_left_edges[stage] + stage_widths[stage] - 1 - (square[0] - stage_left_edges[stage]),
            grid_size - 1 - square[1],
        )
    return square


def map_square_between_stages(square, source_stage, target_stage):
    display_square = get_display_square(square, source_stage)
    return get_display_square(display_square, target_stage)


def expand_stage(stage):
    stage = normalize_stage_index(stage)
    if stage_widths[stage] > grid_size:
        return

    left_columns = range(-expanded_left_columns, 0)
    right_columns = range(grid_size, grid_size + expanded_grid_width - expanded_left_columns)
    pieces = []
    for color, row in (('black', 1), ('white', 6)):
        pieces.extend(create_piece(color, 'Pawn', column, row) for column in left_columns)
        pieces.extend(create_piece(color, 'Pawn', column, row) for column in right_columns)
    for piece in pieces:
        piece.stage = stage
    board_pieces.extend(pieces)
    stage_widths[stage] = grid_size + expanded_grid_width
    stage_left_edges[stage] = -expanded_left_columns


def get_visible_board_width():
    return min(stage_widths[normalize_stage_index(current_stage)], screen.get_width() // square_size)


def get_board_scroll_offset(stage=None):
    if stage is None:
        stage = current_stage
    stage = normalize_stage_index(stage)
    visible_width = min(stage_widths[stage], screen.get_width() // square_size)
    minimum_offset = stage_left_edges[stage]
    maximum_offset = minimum_offset + stage_widths[stage] - visible_width
    return min(maximum_offset, max(minimum_offset, stage_scroll_offsets[stage]))


def scroll_board(columns):
    stage = normalize_stage_index(current_stage)
    visible_width = get_visible_board_width()
    min_offset = stage_left_edges[stage]
    max_offset = min_offset + stage_widths[stage] - visible_width
    stage_scroll_offsets[stage] = min(max_offset, max(min_offset, get_board_scroll_offset(stage) + columns))


def get_stage_shift_target_square(piece, target_stage):
    return map_square_between_stages(piece.position, piece.stage, target_stage)


def get_weather_effect(stage, effect_type):
    stage = normalize_stage_index(stage)
    stage_name = stage_names[stage]
    condition = weather_forecasts[stage][0]
    effect = weather_data.WEATHER_EFFECTS_BY_STAGE.get(stage_name, {}).get(condition)
    if effect is not None and effect.get('type') == effect_type:
        return effect
    return None


def ensure_storm_clouds():
    global storm_cloud_tiles, storm_cloud_weather_key, storm_piece_exposure

    sky_stage = stage_names.index('sky')
    effect = get_weather_effect(sky_stage, 'storm_clouds')
    if effect is None:
        storm_cloud_tiles = set()
        storm_cloud_weather_key = None
        storm_piece_exposure.clear()
        return

    weather_key = (weather_day, weather_forecasts[sky_stage][0])
    if weather_key == storm_cloud_weather_key:
        return

    left_edge = stage_left_edges[sky_stage]
    right_edge = left_edge + stage_widths[sky_stage]
    all_tiles = {
        (x, y)
        for x in range(left_edge, right_edge)
        for y in range(grid_size)
    }
    cloud_tiles = set()
    for _ in range(effect['clump_count']):
        available_seeds = list(all_tiles - cloud_tiles)
        if not available_seeds:
            break
        clump = {random.choice(available_seeds)}
        target_size = random.randint(effect['clump_min_tiles'], effect['clump_max_tiles'])
        while len(clump) < target_size:
            frontier = {
                (x + dx, y + dy)
                for x, y in clump
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
                if (x + dx, y + dy) in all_tiles and (x + dx, y + dy) not in clump
            }
            if not frontier:
                break
            clump.add(random.choice(list(frontier)))
        cloud_tiles.update(clump)

    storm_cloud_tiles = cloud_tiles
    storm_cloud_weather_key = weather_key
    storm_piece_exposure.clear()


def is_storm_cloud_tile(square, stage):
    ensure_storm_clouds()
    return normalize_stage_index(stage) == stage_names.index('sky') and square in storm_cloud_tiles


def advance_stormy_turn(color, pieces):
    global storm_piece_exposure, storm_shocked_pieces

    ensure_storm_clouds()
    effect = get_weather_effect(stage_names.index('sky'), 'storm_clouds')
    active_pieces = get_pieces_with_hallucinations(pieces)
    active_ids = {id(piece) for piece in active_pieces}
    storm_piece_exposure = {
        piece_id: exposure
        for piece_id, exposure in storm_piece_exposure.items()
        if piece_id in active_ids
    }
    storm_shocked_pieces = {
        piece_id: status
        for piece_id, status in storm_shocked_pieces.items()
        if piece_id in active_ids
    }

    for piece_id, status in list(storm_shocked_pieces.items()):
        if status['color'] != color:
            continue
        status['turns_remaining'] -= 1
        if status['turns_remaining'] <= 0:
            del storm_shocked_pieces[piece_id]

    if effect is not None:
        turn_count = storm_turn_counts[color]
        for piece in active_pieces:
            if piece.color != color or piece.stage != stage_names.index('sky'):
                continue
            piece_id = id(piece)
            if piece_id in storm_shocked_pieces:
                storm_piece_exposure.pop(piece_id, None)
                continue
            if not is_storm_cloud_tile(piece.position, piece.stage):
                storm_piece_exposure.pop(piece_id, None)
                continue

            exposure = storm_piece_exposure.get(piece_id)
            if exposure is None:
                storm_piece_exposure[piece_id] = {
                    'piece': piece,
                    'color': color,
                    'turn_count': turn_count,
                }
            elif turn_count - exposure['turn_count'] >= effect['turns_before_shock']:
                storm_shocked_pieces[piece_id] = {
                    'piece': piece,
                    'color': color,
                    'turns_remaining': effect['shock_duration_turns'],
                }
                storm_piece_exposure.pop(piece_id, None)

    storm_turn_counts[color] += 1


def is_square_hidden_by_fog(square, color, stage):
    effect = get_weather_effect(stage, 'fog_of_war')
    if effect is None:
        return False

    visibility_distance = effect['visibility_distance']
    nearby_pieces = (
        piece for piece in board_pieces
        if piece.stage == normalize_stage_index(stage) and piece.color == color
    )
    return not any(
        max(abs(piece.position[0] - square[0]), abs(piece.position[1] - square[1])) <= visibility_distance
        for piece in nearby_pieces
    )


def ensure_crystal_haze_hallucinations(pieces):
    global crystal_haze_hallucinations, crystal_haze_source_ids, crystal_haze_weather_key
    global selected_piece, en_passant_target, last_move

    cave_stage = stage_names.index('caves')
    effect = get_weather_effect(cave_stage, 'piece_hallucinations')
    if effect is None:
        if crystal_haze_weather_key is not None and getattr(selected_piece, 'is_hallucination', False):
            selected_piece = None
        crystal_haze_hallucinations = []
        crystal_haze_source_ids = set()
        crystal_haze_weather_key = None
        return

    weather_key = (weather_day, weather_forecasts[cave_stage][0])
    if weather_key != crystal_haze_weather_key:
        if getattr(selected_piece, 'is_hallucination', False):
            selected_piece = None
        en_passant_target = None
        last_move = None
        crystal_haze_hallucinations = []
        crystal_haze_source_ids = set()
        crystal_haze_weather_key = weather_key

    cave_pieces = [
        piece for piece in pieces
        if piece.stage == cave_stage
        and not getattr(piece, 'is_hallucination', False)
        and not getattr(piece, 'is_vulnerable_body', False)
    ]
    valid_sources = {id(piece) for piece in cave_pieces}
    crystal_haze_hallucinations = [
        copy_piece for copy_piece in crystal_haze_hallucinations
        if id(copy_piece.hallucination_source) in valid_sources
    ]
    crystal_haze_source_ids.intersection_update(valid_sources)
    pending_pieces = [piece for piece in cave_pieces if id(piece) not in crystal_haze_source_ids]
    if not pending_pieces:
        return

    occupied_squares = {piece.position for piece in cave_pieces}
    reserved_squares = occupied_squares | {
        copy_piece.position for copy_piece in crystal_haze_hallucinations
    }
    available_squares = [
        (x, y)
        for x in range(stage_left_edges[cave_stage], stage_left_edges[cave_stage] + stage_widths[cave_stage])
        for y in range(grid_size)
        if (x, y) not in reserved_squares
    ]
    random.shuffle(available_squares)

    for piece in pending_pieces:
        original_position = piece.position
        duplicate_count = random.randint(effect['duplicate_min'], effect['duplicate_max'])
        duplicate_positions = []
        for _ in range(duplicate_count):
            if available_squares:
                position = available_squares.pop()
            else:
                position = random.choice([
                    (x, y)
                    for x in range(stage_left_edges[cave_stage], stage_left_edges[cave_stage] + stage_widths[cave_stage])
                    for y in range(grid_size)
                    if (x, y) != original_position
                ])
            duplicate_positions.append(position)
            reserved_squares.add(position)

        possible_positions = [original_position, *duplicate_positions]
        real_position = random.choice(possible_positions)
        if effect['randomize_real_piece_location']:
            piece.position = real_position

        for position in possible_positions:
            if position == real_position:
                continue
            hallucination = copy.copy(piece)
            hallucination.position = position
            hallucination.is_hallucination = True
            hallucination.hallucination_source = piece
            crystal_haze_hallucinations.append(hallucination)
        crystal_haze_source_ids.add(id(piece))


def get_pieces_with_hallucinations(pieces):
    ensure_crystal_haze_hallucinations(pieces)
    known_pieces = {id(piece) for piece in pieces}
    return [
        *pieces,
        *(
            hallucination for hallucination in crystal_haze_hallucinations
            if id(hallucination) not in known_pieces
        ),
    ]


def remove_piece_hallucinations(piece):
    global crystal_haze_hallucinations, crystal_haze_source_ids
    crystal_haze_hallucinations = [
        hallucination for hallucination in crystal_haze_hallucinations
        if hallucination.hallucination_source is not piece
    ]
    crystal_haze_source_ids.discard(id(piece))


def keep_moved_piece_hallucinations(piece, old_position):
    effect = get_weather_effect(piece.stage, 'piece_hallucinations')
    if effect is None:
        return
    source_hallucinations = [
        hallucination for hallucination in crystal_haze_hallucinations
        if hallucination.hallucination_source is piece
    ]
    if source_hallucinations:
        random.choice(source_hallucinations).position = old_position


def reverse_stage_colors(stage):
    global selected_piece, last_move, en_passant_target

    stage = normalize_stage_index(stage)
    visible_width = min(stage_widths[stage], screen.get_width() // square_size)
    previous_offset = get_board_scroll_offset(stage)
    if stage in rotated_stages:
        rotated_stages.remove(stage)
    else:
        rotated_stages.add(stage)
    min_offset = stage_left_edges[stage]
    max_offset = min_offset + stage_widths[stage] - visible_width
    stage_scroll_offsets[stage] = min_offset + max_offset - previous_offset

    for piece in board_pieces:
        if piece.stage != stage:
            continue
        piece.color = 'black' if piece.color == 'white' else 'white'
        piece.load_image(f'{piece.color}_{piece.__class__.__name__.lower()}')

    for hallucination in crystal_haze_hallucinations:
        if hallucination.stage != stage:
            continue
        hallucination.color = 'black' if hallucination.color == 'white' else 'white'
        hallucination.load_image(f'{hallucination.color}_{hallucination.__class__.__name__.lower()}')

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
                {'name': 'sticky webbing', 'icon_path': os.path.join('Ability Icons', 'white_web.png'), 'fallback_color': (165, 195, 215)},
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
        {
            'name': 'King',
            'piece': piece_data.King('white'),
            'description': 'The King of Hearts can leave its vulnerable body behind as an immortal astral projection.',
            'abilities': [
                {
                    'name': 'astral projection',
                    'description': 'Play King of Hearts to leave a vulnerable body. The projection returns after six turns or by reuniting with its body.',
                    'fallback_color': (180, 155, 230),
                },
                {
                    'name': 'expansion',
                    'description': 'Play King of Clubs to add 25 files to each side of the current layer, with pawns on the new files. Use left and right arrows to scroll.',
                    'fallback_color': (175, 175, 190),
                },
            ],
            'pattern': [(-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)],
            'attacks': [],
        },
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
    col = x // square_size + get_board_scroll_offset()
    row = y // square_size
    stage = normalize_stage_index(current_stage)
    if stage_left_edges[stage] <= col < stage_left_edges[stage] + stage_widths[stage] and 0 <= row < grid_size:
        return get_display_square((col, row), current_stage)
    return None


def get_piece_at_square(pieces, square, stage):
    for piece in pieces:
        if (
            piece.position == square
            and piece.stage == stage
            and (
                not getattr(piece, 'is_astral_projection', False)
                or getattr(piece, 'is_hallucination', False)
            )
        ):
            return piece
    return None


def get_pieces_at_square(pieces, square):
    return [piece for piece in pieces if piece.position == square]


def get_piece_ability(piece, ability_name):
    return piece.movement.get('abilities', {}).get(ability_name, {})


def get_stage_shift_destinations(piece, pieces):
    pieces = get_pieces_with_hallucinations(pieces)
    ability = get_piece_ability(piece, 'stage_shift')
    allowed_stages = ability.get('allowed_stages')
    destinations = []

    for stage_delta in ability.get('stage_deltas', []):
        target_stage = piece.stage + stage_delta
        if allowed_stages is not None and target_stage not in allowed_stages:
            continue
        target_square = get_stage_shift_target_square(piece, target_stage)
        if not in_bounds(target_square, target_stage):
            continue
        occupant = get_piece_at_square(pieces, target_square, target_stage)
        astral_body = getattr(piece, 'astral_body', None)
        if occupant is astral_body:
            occupant = None
        if occupant is not None:
            if ability.get('requires_empty', True):
                continue
            if not ability.get('can_capture', False) or occupant.color == piece.color:
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
        if not in_bounds(square, piece.stage) or get_piece_at_square(pieces, square, piece.stage) is not None:
            continue
        attack_squares.add(square)

    targets = []
    for target in pieces:
        target_square = map_square_between_stages(target.position, target.stage, piece.stage)
        if target.stage in target_stages and target_square in attack_squares and target.color != piece.color and can_piece_attack_target(piece, target):
            targets.append(target)
    return targets


def in_bounds(square, stage=None):
    x, y = square
    if stage is None:
        stage = current_stage
    stage = normalize_stage_index(stage)
    return stage_left_edges[stage] <= x < stage_left_edges[stage] + stage_widths[stage] and 0 <= y < grid_size


def can_piece_attack_target(attacker, target):
    if attacker is None or target is None:
        return False

    if (
        getattr(target, 'is_astral_projection', False)
        and not getattr(target, 'is_hallucination', False)
    ):
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
        if (
            king.__class__.__name__ != 'King'
            or getattr(king, 'is_astral_projection', False)
            or getattr(king, 'is_vulnerable_body', False)
        ):
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
    if (
        piece.__class__.__name__ != 'King'
        or getattr(piece, 'is_astral_projection', False)
        or getattr(piece, 'is_vulnerable_body', False)
        or piece not in get_checked_kings(pieces)
    ):
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
        if in_bounds(one_step, piece.stage) and get_piece_at_square(pieces, one_step, piece.stage) is None:
            legal_moves.append(one_step)

        start_row = piece.movement['start_row']
        if y == start_row:
            two_step = (x, y + (2 * forward))
            if in_bounds(two_step, piece.stage) and get_piece_at_square(pieces, one_step, piece.stage) is None and get_piece_at_square(pieces, two_step, piece.stage) is None:
                legal_moves.append(two_step)

        for dx in (-1, 1):
            target = (x + dx, y + forward)
            if in_bounds(target, piece.stage):
                occupant = get_piece_at_square(pieces, target, piece.stage)
                if occupant is not None and occupant.color != piece.color and can_piece_attack_target(piece, occupant):
                    legal_moves.append(target)

                if last_move is not None and last_move['piece'].color != piece.color and last_move['piece'].__class__.__name__ == 'Pawn':
                    if (
                        not getattr(piece, 'is_hallucination', False)
                        and abs(last_move['start'][1] - last_move['end'][1]) == 2
                        and last_move['end'] == (x + dx, y)
                    ):
                        en_passant_target = (x + dx, y + forward)
                        legal_moves.append(en_passant_target)
        return legal_moves

    if move_type == 'knight':
        for dx, dy in piece.movement['offsets']:
            target = (x + dx, y + dy)
            if not in_bounds(target, piece.stage):
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
            if not in_bounds(target, piece.stage):
                continue
            occupant = get_piece_at_square(pieces, target, piece.stage)
            if occupant is None:
                legal_moves.append(target)
            elif occupant.color != piece.color and (dx, dy) in outer_ring and can_piece_attack_target(piece, occupant):
                legal_moves.append(target)
        return legal_moves

    if move_type == 'avian':
        directions = piece.movement.get('directions', [])
        max_steps = piece.movement.get('max_steps')

        for dx, dy in directions:
            next_x = x + dx
            next_y = y + dy
            steps = 0
            while in_bounds((next_x, next_y), piece.stage) and (max_steps is None or steps < max_steps):
                occupant = get_piece_at_square(pieces, (next_x, next_y), piece.stage)
                if occupant is None:
                    legal_moves.append((next_x, next_y))
                    next_x += dx
                    next_y += dy
                    steps += 1
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
            if not in_bounds(target, piece.stage):
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
                if not in_bounds((next_x, next_y), piece.stage):
                    break
                occupant = get_piece_at_square(pieces, (next_x, next_y), piece.stage)
                if occupant is getattr(piece, 'astral_body', None):
                    occupant = None
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
        steps = 0
        while in_bounds((next_x, next_y), piece.stage) and (max_steps is None or steps < max_steps):
            occupant = get_piece_at_square(pieces, (next_x, next_y), piece.stage)
            if occupant is not None:
                if occupant.color != piece.color and can_piece_attack_target(piece, occupant):
                    legal_moves.append((next_x, next_y))
                break
            legal_moves.append((next_x, next_y))
            next_x += dx
            next_y += dy
            steps += 1

    return legal_moves


def get_legal_moves(piece, pieces):
    pieces = get_pieces_with_hallucinations(pieces)
    legal_moves = get_stage_local_moves(piece, pieces)
    legal_moves.extend(
        map_square_between_stages(target.position, target.stage, piece.stage)
        for target in get_cross_stage_attack_targets(piece, pieces)
        if not is_square_hidden_by_fog(target.position, piece.color, target.stage)
    )
    legal_moves = [
        square for square in legal_moves
        if (target := get_piece_at_square(pieces, square, piece.stage)) is None
        or target.color == piece.color
        or not is_square_hidden_by_fog(square, piece.color, piece.stage)
    ]
    if get_stage_shift_destinations(piece, pieces):
        legal_moves.append(piece.position)
    return list(dict.fromkeys(legal_moves))


def draw_board():
    board_width = get_visible_board_width()
    scroll_offset = get_board_scroll_offset()
    for i in range(board_width):
        for j in range(grid_size):
            board_x = i + scroll_offset
            rect_x = i * square_size
            rect_y = j * square_size
            stage_index = normalize_stage_index(current_stage)
            color = stages[stage_names[stage_index]][0] if (board_x + j) % 2 == 0 else stages[stage_names[stage_index]][1]
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
        display_x -= scroll_offset
        if not 0 <= display_x < board_width:
            continue
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
        display_x -= scroll_offset
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
                display_move_x -= scroll_offset
                if not 0 <= display_move_x < board_width:
                    continue
                move_surface = pygame.Surface((square_size, square_size), pygame.SRCALPHA)
                move_surface.fill((255, 120, 120, 120))
                screen.blit(move_surface, (display_move_x * square_size, display_move_y * square_size))


def draw_fog_of_war():
    stage = normalize_stage_index(current_stage)
    if get_weather_effect(stage, 'fog_of_war') is None:
        return

    scroll_offset = get_board_scroll_offset(stage)
    board_width = get_visible_board_width()
    for x in range(stage_left_edges[stage], stage_left_edges[stage] + stage_widths[stage]):
        display_x, _ = get_display_square((x, 0), stage)
        display_x -= scroll_offset
        if not 0 <= display_x < board_width:
            continue
        for y in range(grid_size):
            if not is_square_hidden_by_fog((x, y), current_turn, stage):
                continue
            _, display_y = get_display_square((x, y), stage)
            pygame.draw.rect(
                screen,
                (72, 74, 80),
                (display_x * square_size, display_y * square_size, square_size, square_size),
            )


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


def move_chess_window_above_hand(hwnd, width, height):
    if hwnd is None:
        return

    user32 = ctypes.windll.user32
    screen_width = user32.GetSystemMetrics(0)
    hand_window_y = grid_size * square_size + 50
    x = max(0, (screen_width - width) // 2)
    y = max(20, hand_window_y - height - 20)
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


def move_currency_window_to_right_top(hwnd, width, height):
    if hwnd is None:
        return

    user32 = ctypes.windll.user32
    screen_width = user32.GetSystemMetrics(0)
    x = max(20, screen_width - width - 20)
    user32.MoveWindow(hwnd, x, 20, width, height, True)


def move_weather_window_to_left_top(hwnd, width, height):
    if hwnd is None:
        return
    ctypes.windll.user32.MoveWindow(hwnd, 20, 20, width, height, True)


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


def run_debug_card_window(queue, command_queue):
    columns = 8
    card_gap = 8
    margin = 14
    header_height = 52
    window_width = margin * 2 + columns * hand_card_width + (columns - 1) * card_gap
    window_height = 760
    row_height = hand_card_height + card_gap

    pygame.init()
    debug_screen = pygame.display.set_mode((window_width, window_height))
    pygame.display.set_caption('Debug Card Deck')
    clock = pygame.time.Clock()
    image_cache = {}
    cards = []
    current_player = 'white'
    status = 'Click a card to play it for the current player.'
    scroll_row = 0
    rejected_card_id = None
    rejected_at = 0
    invalid_feedback_duration = 700

    while True:
        visible_rows = max(1, (window_height - header_height - margin + card_gap) // row_height)
        total_rows = (len(cards) + columns - 1) // columns
        max_scroll_row = max(0, total_rows - visible_rows)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                return
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    pygame.quit()
                    return
                if event.key in (pygame.K_DOWN, pygame.K_PAGEDOWN):
                    scroll_row = min(max_scroll_row, scroll_row + (1 if event.key == pygame.K_DOWN else visible_rows))
                elif event.key in (pygame.K_UP, pygame.K_PAGEUP):
                    scroll_row = max(0, scroll_row - (1 if event.key == pygame.K_UP else visible_rows))
            if event.type == pygame.MOUSEWHEEL:
                scroll_row = min(max_scroll_row, max(0, scroll_row - event.y))
            if event.type == pygame.MOUSEBUTTONDOWN and event.button in (4, 5):
                scroll_row = min(max_scroll_row, max(0, scroll_row + (1 if event.button == 5 else -1)))
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mouse_x, mouse_y = event.pos
                if mouse_y >= header_height:
                    relative_x = mouse_x - margin
                    relative_y = mouse_y - header_height
                    col, card_x = divmod(relative_x, hand_card_width + card_gap)
                    row, card_y = divmod(relative_y, row_height)
                    row += scroll_row
                    if (
                        0 <= col < columns
                        and 0 <= card_x < hand_card_width
                        and 0 <= card_y < hand_card_height
                    ):
                        card_index = row * columns + col
                        if card_index < len(cards):
                            command_queue.put({'action': 'debug_play_card', 'card_id': cards[card_index]['card_id']})

        while True:
            try:
                message = queue.get_nowait()
            except Empty:
                break
            if message.get('close'):
                pygame.quit()
                return
            cards = message.get('cards', cards)
            current_player = message.get('turn', current_player)
            status = message.get('status', status)
            rejected_card_id = message.get('rejected_card_id')
            if rejected_card_id is not None:
                rejected_at = pygame.time.get_ticks()

        debug_screen.fill((24, 24, 30))
        pygame.draw.rect(debug_screen, (90, 90, 105), debug_screen.get_rect(), 3)
        title = pygame.font.Font(None, 28).render(
            f'DEBUG CARD DECK - {current_player.upper()} TO PLAY',
            True,
            (240, 240, 245),
        )
        debug_screen.blit(title, (margin, 8))
        hint = pygame.font.Font(None, 18).render(
            f'{status}  |  Scroll to browse all {len(cards)} cards.',
            True,
            (180, 180, 190),
        )
        debug_screen.blit(hint, (margin, 32))

        for index, card in enumerate(cards):
            row, col = divmod(index, columns)
            visible_row = row - scroll_row
            if not 0 <= visible_row < visible_rows:
                continue
            card_rect = pygame.Rect(
                margin + col * (hand_card_width + card_gap),
                header_height + visible_row * row_height,
                hand_card_width,
                hand_card_height,
            )
            debug_screen.blit(render_hand_card(card, image_cache), card_rect)
            if (
                card.get('card_id') == rejected_card_id
                and pygame.time.get_ticks() - rejected_at < invalid_feedback_duration
            ):
                pygame.draw.rect(debug_screen, (255, 65, 65), card_rect, 3, border_radius=6)

        pygame.display.flip()
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


def run_currency_window(queue):
    currency_width = 300
    currency_height = 190

    pygame.init()
    currency_screen = pygame.display.set_mode((currency_width, currency_height))
    hwnd = pygame.display.get_wm_info()['window']
    move_currency_window_to_right_top(hwnd, currency_width, currency_height)
    pygame.display.set_caption('Chess Currency')
    clock = pygame.time.Clock()
    current_player = 'white'
    current_currencies = {'gold': 0, 'gems': 0, 'tokens': 0}

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
            current_player = message.get('player', current_player)
            current_currencies.update(message.get('currencies', {}))

        currency_screen.fill((24, 24, 30))
        pygame.draw.rect(currency_screen, (90, 90, 105), currency_screen.get_rect(), 3)
        title = pygame.font.Font(None, 34).render('CURRENCY', True, (240, 205, 75))
        currency_screen.blit(title, title.get_rect(center=(currency_width // 2, 35)))

        for currency, y, text_color in (
            ('gold', 85, (240, 205, 75)),
            ('gems', 125, (105, 220, 190)),
            ('tokens', 165, (200, 200, 210)),
        ):
            balance = pygame.font.Font(None, 28).render(
                f'{currency.capitalize()}: {current_currencies[currency]}',
                True,
                text_color,
            )
            currency_screen.blit(balance, balance.get_rect(center=(currency_width // 2, y)))

        pygame.display.flip()
        clock.tick(30)


def run_weather_window(queue):
    day_tile_width = 112
    day_tile_height = 136
    day_tile_gap = 8
    weather_width = 28 + len(range(7)) * day_tile_width + 6 * day_tile_gap
    weather_height = 220

    pygame.init()
    weather_screen = pygame.display.set_mode((weather_width, weather_height))
    hwnd = pygame.display.get_wm_info()['window']
    move_weather_window_to_left_top(hwnd, weather_width, weather_height)
    pygame.display.set_caption('Weather Forecast')
    clock = pygame.time.Clock()
    forecast = {'day': 1, 'stage_name': '', 'forecast': []}

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT or (
                event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE
            ):
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
            forecast.update(message)

        weather_screen.fill((24, 30, 40))
        pygame.draw.rect(weather_screen, (95, 125, 150), weather_screen.get_rect(), 3)
        title = pygame.font.Font(None, 36).render('WEATHER FORECAST', True, (225, 235, 245))
        weather_screen.blit(title, title.get_rect(center=(weather_width // 2, 38)))
        stage_text = pygame.font.Font(None, 28).render(
            f"{forecast['stage_name'].capitalize()}  -  7-Day Forecast",
            True,
            (235, 210, 135),
        )
        weather_screen.blit(stage_text, stage_text.get_rect(center=(weather_width // 2, 72)))

        for index, condition in enumerate(forecast['forecast']):
            tile_x = 14 + index * (day_tile_width + day_tile_gap)
            tile_rect = pygame.Rect(tile_x, 100, day_tile_width, day_tile_height)
            pygame.draw.rect(
                weather_screen,
                (53, 67, 82) if index else (86, 79, 48),
                tile_rect,
                border_radius=7,
            )
            pygame.draw.rect(weather_screen, (125, 145, 165), tile_rect, 1, border_radius=7)

            day_text = pygame.font.Font(None, 23).render(
                f"Day {forecast['day'] + index}",
                True,
                (245, 245, 245),
            )
            weather_screen.blit(day_text, day_text.get_rect(center=(tile_rect.centerx, tile_rect.y + 34)))

            condition_lines = textwrap.wrap(condition, width=10)
            condition_font = pygame.font.Font(None, 20)
            for line_index, condition_line in enumerate(condition_lines[:3]):
                condition_text = condition_font.render(condition_line, True, (210, 225, 235))
                weather_screen.blit(
                    condition_text,
                    condition_text.get_rect(
                        center=(tile_rect.centerx, tile_rect.y + 72 + line_index * 21)
                    ),
                )

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


def toggle_debug_card_window():
    global debug_card_window_process, debug_card_window_queue, debug_card_command_queue, debug_cards

    if debug_card_window_process is not None and debug_card_window_process.is_alive():
        if debug_card_window_queue is not None:
            debug_card_window_queue.put({'close': True})
        debug_card_window_process.join(timeout=0.2)
        if debug_card_window_process.is_alive():
            debug_card_window_process.terminate()
            debug_card_window_process.join(timeout=0.5)
        debug_card_window_process = None
        debug_card_window_queue = None
        debug_card_command_queue = None
        debug_cards = []
        return

    debug_cards = card_data.create_deck()
    debug_card_window_queue = mp.Queue()
    debug_card_command_queue = mp.Queue()
    debug_card_window_process = mp.Process(
        target=run_debug_card_window,
        args=(debug_card_window_queue, debug_card_command_queue),
        daemon=True,
    )
    debug_card_window_process.start()
    send_debug_card_window_state()


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


def toggle_currency_window():
    global currency_window_process, currency_window_queue

    if currency_window_process is not None and currency_window_process.is_alive():
        if currency_window_queue is not None:
            currency_window_queue.put({'close': True})
        currency_window_process.join(timeout=0.2)
        if currency_window_process.is_alive():
            currency_window_process.terminate()
            currency_window_process.join(timeout=0.5)
        currency_window_process = None
        currency_window_queue = None
        return

    currency_window_queue = mp.Queue()
    currency_window_process = mp.Process(
        target=run_currency_window,
        args=(currency_window_queue,),
        daemon=True,
    )
    currency_window_process.start()
    send_currency_window_state()


def toggle_weather_window():
    global weather_window_process, weather_window_queue, weather_window_last_state

    if weather_window_process is not None and weather_window_process.is_alive():
        if weather_window_queue is not None:
            weather_window_queue.put({'close': True})
        weather_window_process.join(timeout=0.2)
        if weather_window_process.is_alive():
            weather_window_process.terminate()
            weather_window_process.join(timeout=0.5)
        weather_window_process = None
        weather_window_queue = None
        weather_window_last_state = None
        return

    weather_window_queue = mp.Queue()
    weather_window_last_state = None
    weather_window_process = mp.Process(
        target=run_weather_window,
        args=(weather_window_queue,),
        daemon=True,
    )
    weather_window_process.start()
    send_weather_window_state()


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


def send_debug_card_window_state(rejected_card_id=None, status=None):
    if debug_card_window_queue is None or debug_card_window_process is None:
        return
    if not debug_card_window_process.is_alive():
        return
    message = {
        'cards': [card.display_data() for card in debug_cards],
        'turn': current_turn,
        'status': status or 'Click a card to play it for the current player.',
    }
    if rejected_card_id is not None:
        message['rejected_card_id'] = rejected_card_id
    debug_card_window_queue.put(message, block=False)


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


def send_currency_window_state():
    if currency_window_queue is None or currency_window_process is None:
        return
    if not currency_window_process.is_alive():
        return
    currency_window_queue.put({
        'player': current_turn,
        'currencies': currencies[current_turn].copy(),
    }, block=False)


def send_weather_window_state():
    global weather_window_last_state
    if weather_window_queue is None or weather_window_process is None:
        return
    if not weather_window_process.is_alive():
        return
    stage = normalize_stage_index(current_stage)
    forecast = tuple(weather_forecasts[stage])
    state = {
        'day': weather_day,
        'stage': stage,
        'stage_name': stage_names[stage],
        'forecast': forecast,
    }
    if state == weather_window_last_state:
        return
    weather_window_queue.put(state, block=False)
    weather_window_last_state = state


def use_card_from_hand(player, card_id, debug=False):
    global cancel_played_this_turn

    player_hand = hands.get(player, [])
    card_pool = debug_cards if debug else player_hand
    card = next((card for card in card_pool if card.card_id == card_id), None)
    top_card = played_pile[-1].display_data() if played_pile else None
    if (
        card is None
        or (not debug and not can_play_card(card.display_data(), top_card))
        or (
            not debug
            and getattr(card, 'action', None) == 'cancel'
            and (player != current_turn or cancel_played_this_turn)
        )
        or (is_king_of_hearts(card) and get_untransformed_king(board_pieces, player) is None)
        or not card.use()
    ):
        return False
    if is_king_of_hearts(card):
        activate_king_of_hearts(board_pieces, player)
    if getattr(card, 'suit', None) == 'Spades' and getattr(card, 'rank', None) == 'K':
        award_gold(player, 50)
    if getattr(card, 'suit', None) == 'Clubs' and getattr(card, 'rank', None) == 'K':
        expand_stage(current_stage)
    if getattr(card, 'action', None) == 'reverse':
        reverse_stage_colors(reverse_card_stages[card.color])
    if not debug:
        player_hand.remove(card)
    played_pile.append(card)
    opposing_player = 'black' if player == 'white' else 'white'
    if getattr(card, 'action', None) == 'cancel':
        cancel_played_this_turn = True
        skipped_turns[opposing_player] += 1
    elif getattr(card, 'action', None) == 'draw_two':
        draw_cards_for_player(opposing_player, 2)
    elif getattr(card, 'action', None) == 'draw_four':
        draw_cards_for_player(opposing_player, 4)
    send_hand_window_state()
    send_pile_window_state()
    if debug:
        send_debug_card_window_state(status=f'Played {card.suit} {card.rank} for {player}.')
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


def process_debug_card_window_commands():
    if debug_card_command_queue is None:
        return
    while True:
        try:
            command = debug_card_command_queue.get_nowait()
        except Empty:
            return
        if command.get('action') == 'debug_play_card':
            card_id = command.get('card_id')
            if not use_card_from_hand(current_turn, card_id, debug=True):
                send_debug_card_window_state(
                    rejected_card_id=card_id,
                    status='Card could not be played in the current game state.',
                )


def begin_turn(color):
    global current_turn, cancel_played_this_turn
    if skipped_turns[color] > 0:
        skipped_turns[color] -= 1
        advance_stormy_turn(color, board_pieces)
        advance_weather_turn(color)
        next_color = 'black' if color == 'white' else 'white'
        begin_turn(next_color)
        return

    current_turn = color
    cancel_played_this_turn = False
    draw_card_for_turn(color)
    send_currency_window_state()
    send_hand_window_state()
    send_pile_window_state()
    send_debug_card_window_state()


def draw_piece(piece, x=None, y=None):
    if piece.stage != current_stage:
        return
    if x is None or y is None:
        x, y = piece.position
    x, y = get_display_square((x, y), piece.stage)
    x -= get_board_scroll_offset(piece.stage)
    if not 0 <= x < screen.get_width() // square_size:
        return

    rotation = get_king_shake_angle(piece, board_pieces)
    center_x = x * square_size + square_size // 2
    center_y = y * square_size + square_size // 2

    if piece.image is None:
        font = pygame.font.Font(None, 72)
        color = (255, 255, 255) if piece.color == 'white' else (0, 0, 0)
        text = font.render(piece.symbol, True, color)
        if getattr(piece, 'is_astral_projection', False):
            text.set_alpha(135)
        rotated_text = pygame.transform.rotate(text, rotation)
        text_rect = rotated_text.get_rect(center=(center_x, center_y))
        screen.blit(rotated_text, text_rect)
    else:
        image = piece.image
        if getattr(piece, 'is_astral_projection', False):
            image = piece.image.copy()
            image.set_alpha(135)
        rotated_image = pygame.transform.rotate(image, rotation)
        image_rect = rotated_image.get_rect(center=(center_x, center_y))
        screen.blit(rotated_image, image_rect.topleft)
    draw_piece_shock(piece, (center_x, center_y))


def draw_all_pieces(pieces):
    ensure_crystal_haze_hallucinations(pieces)
    for piece in sorted(pieces, key=lambda current_piece: getattr(current_piece, 'is_astral_projection', False)):
        if piece.stage == current_stage:
            draw_piece(piece, *piece.position)
    for hallucination in crystal_haze_hallucinations:
        if hallucination.stage == current_stage:
            draw_piece(hallucination, *hallucination.position)


def draw_storm_clouds():
    sky_stage = stage_names.index('sky')
    if normalize_stage_index(current_stage) != sky_stage:
        return
    ensure_storm_clouds()
    if not storm_cloud_tiles:
        return

    scroll_offset = get_board_scroll_offset(sky_stage)
    for square in storm_cloud_tiles:
        display_x, display_y = get_display_square(square, sky_stage)
        display_x -= scroll_offset
        if not 0 <= display_x < screen.get_width() // square_size:
            continue
        cloud_surface = pygame.Surface((square_size, square_size), pygame.SRCALPHA)
        pygame.draw.ellipse(cloud_surface, (25, 29, 43, 220), (5, 34, 91, 46))
        pygame.draw.ellipse(cloud_surface, (34, 39, 56, 235), (15, 22, 37, 43))
        pygame.draw.ellipse(cloud_surface, (30, 35, 51, 240), (37, 12, 42, 52))
        pygame.draw.ellipse(cloud_surface, (25, 29, 43, 225), (61, 25, 34, 41))
        pygame.draw.ellipse(cloud_surface, (17, 20, 31, 170), (10, 63, 80, 22))
        screen.blit(cloud_surface, (display_x * square_size, display_y * square_size))


def draw_piece_shock(piece, center):
    source = getattr(piece, 'hallucination_source', piece)
    shock = storm_shocked_pieces.get(id(source))
    if shock is None:
        shock = storm_shocked_pieces.get(id(piece))
    if shock is None:
        return

    center_x, center_y = center
    phase = pygame.time.get_ticks() // 85
    pulse = phase % 2
    glow = (255, 235, 110) if pulse else (140, 225, 255)
    radius = 39 + (phase % 3) * 2
    pygame.draw.circle(screen, glow, center, radius, 2)
    offset = (phase % 5) * 2
    bolt_points = [
        (center_x + 24 + offset, center_y - 40),
        (center_x + 13, center_y - 19),
        (center_x + 27 + offset, center_y - 15),
        (center_x + 6, center_y + 10),
        (center_x + 15, center_y - 8),
        (center_x + 3, center_y - 12),
        (center_x + 24 + offset, center_y - 40),
    ]
    pygame.draw.lines(screen, (255, 250, 190), False, bolt_points, 3)


def get_clicked_piece(mouse_pos, pieces):
    clicked_square = get_square_from_mouse(mouse_pos)
    if clicked_square is None:
        return None

    pieces = get_pieces_with_hallucinations(pieces)
    candidates = [
        piece for piece in reversed(pieces)
        if piece.stage == current_stage
        and piece.position == clicked_square
        and piece.trapped_until <= 0
        and not getattr(piece, 'is_vulnerable_body', False)
        and (
            piece.color == current_turn
            or not is_square_hidden_by_fog(clicked_square, current_turn, current_stage)
        )
    ]
    for piece in candidates:
        if not getattr(piece, 'is_astral_projection', False):
            return piece
    return candidates[0] if candidates else None


def is_king_of_hearts(card):
    return getattr(card, 'suit', None) == 'Hearts' and getattr(card, 'rank', None) == 'K'


def get_untransformed_king(pieces, color):
    return next(
        (
            piece for piece in pieces
            if piece.__class__.__name__ == 'King'
            and piece.color == color
            and not getattr(piece, 'is_astral_projection', False)
            and not getattr(piece, 'is_vulnerable_body', False)
        ),
        None,
    )


def activate_king_of_hearts(pieces, color):
    king = get_untransformed_king(pieces, color)
    if king is None:
        return False

    body = piece_data.King(color)
    body.position = king.position
    body.stage = king.stage
    body.has_moved = True
    body.is_vulnerable_body = True
    body.movement['type'] = 'king_body'

    king.is_astral_projection = True
    king.astral_body = body
    king.astral_turns_remaining = 6
    king.has_moved = True
    king.movement.setdefault('abilities', {})['stage_shift'] = {
        'stage_deltas': [
            delta for delta in range(-(len(stage_names) - 1), len(stage_names))
            if delta != 0
        ],
        'allowed_stages': list(range(len(stage_names))),
        'requires_empty': True,
        'can_capture': False,
    }
    pieces.append(body)
    return True


def end_astral_projection(projection, pieces):
    body = getattr(projection, 'astral_body', None)
    if body in pieces:
        pieces.remove(body)
    projection.is_astral_projection = False
    projection.movement.get('abilities', {}).pop('stage_shift', None)
    del projection.astral_body
    del projection.astral_turns_remaining


def advance_astral_projection_turns(color, pieces):
    for piece in pieces[:]:
        if (
            not getattr(piece, 'is_astral_projection', False)
            or piece.color != color
        ):
            continue
        piece.astral_turns_remaining -= 1
        if piece.astral_turns_remaining <= 0:
            end_astral_projection(piece, pieces)


def finish_board_action(pieces, ended_turn):
    for piece in pieces:
        if piece.trapped_until > 0 and piece.color == ended_turn:
            if piece.just_trapped:
                piece.just_trapped = False
            else:
                piece.trapped_until -= 1
                if piece.trapped_until <= 0:
                    piece.trapped_until = 0
                    piece.web_square = None
    advance_astral_projection_turns(ended_turn, pieces)
    advance_stormy_turn(ended_turn, pieces)
    advance_weather_turn(ended_turn)
    begin_turn('black' if ended_turn == 'white' else 'white')


def finish_hallucination_action(pieces, selected_hallucination, target_square=None):
    global selected_piece, en_passant_target, last_move

    effect = get_weather_effect(selected_hallucination.stage, 'piece_hallucinations')
    movement_pieces = get_pieces_with_hallucinations(pieces)
    target_piece = get_piece_at_square(movement_pieces, target_square, selected_hallucination.stage)
    legal_moves = get_legal_moves(selected_hallucination, pieces)
    if target_square == selected_hallucination.position or target_square not in legal_moves:
        return

    if target_piece is not None and target_piece.color != selected_hallucination.color:
        if (
            getattr(target_piece, 'is_hallucination', False)
            and effect['hallucinations_disappear_when_attacked']
        ):
            crystal_haze_hallucinations.remove(target_piece)
        if effect['hallucinations_disappear_when_attacking']:
            crystal_haze_hallucinations.remove(selected_hallucination)
        selected_piece = None
        en_passant_target = None
        last_move = None
        finish_board_action(pieces, current_turn)
        return

    selected_hallucination.position = target_square
    selected_piece = None
    en_passant_target = None
    last_move = None
    finish_board_action(pieces, current_turn)


def move_selected_piece_to(target_square, pieces, target_stage=None):
    global selected_piece, current_turn, last_move, en_passant_target, winner, game_over, current_stage

    if selected_piece is None or game_over:
        return

    if selected_piece.trapped_until > 0:
        return

    if selected_piece.color != current_turn:
        return

    ensure_crystal_haze_hallucinations(pieces)
    if selected_piece is None:
        return
    if getattr(selected_piece, 'is_hallucination', False):
        finish_hallucination_action(pieces, selected_piece, target_square)
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
                target_piece = get_piece_at_square(pieces, destination_square, resolved_target_stage)
                if target_piece is not None and target_piece.color != selected_piece.color:
                    award_gold(selected_piece.color, target_piece.value)
                    if target_piece.__class__.__name__ == 'King':
                        winner = selected_piece.color
                        game_over = True
                    pieces.remove(target_piece)
                    remove_piece_hallucinations(target_piece)
                selected_piece.position = destination_square
                selected_piece.stage = resolved_target_stage
                current_stage = resolved_target_stage
                selected_piece.has_moved = True
                if (
                    getattr(selected_piece, 'is_astral_projection', False)
                    and selected_piece.position == selected_piece.astral_body.position
                    and selected_piece.stage == selected_piece.astral_body.stage
                ):
                    end_astral_projection(selected_piece, pieces)
                last_move = {'piece': selected_piece, 'start': start_square, 'end': destination_square, 'stage_shift': True}
                en_passant_target = None
                selected_piece = None
                if not game_over:
                    finish_board_action(pieces, current_turn)
                return

    movement_pieces = get_pieces_with_hallucinations(pieces)
    legal_moves = get_legal_moves(selected_piece, pieces)
    if target_square not in legal_moves:
        return

    start_square = selected_piece.position
    target_piece = get_piece_at_square(movement_pieces, target_square, selected_piece.stage)

    if target_piece is None:
        target_piece = next((
            target for target in get_cross_stage_attack_targets(selected_piece, movement_pieces)
            if map_square_between_stages(target.position, target.stage, selected_piece.stage) == target_square
        ), None)

    if target_piece is not None and getattr(target_piece, 'is_hallucination', False):
        effect = get_weather_effect(target_piece.stage, 'piece_hallucinations')
        if effect is not None and effect['hallucinations_disappear_when_attacked']:
            crystal_haze_hallucinations.remove(target_piece)
            selected_piece = None
            en_passant_target = None
            last_move = None
            finish_board_action(pieces, current_turn)
            return

    if selected_piece.__class__.__name__ == 'Pawn' and target_square == en_passant_target:
        captured_pawn_square = (target_square[0], start_square[1])
        captured_pawn = get_piece_at_square(pieces, captured_pawn_square, selected_piece.stage)
        if captured_pawn is not None:
            award_gold(selected_piece.color, captured_pawn.value)
            pieces.remove(captured_pawn)
            remove_piece_hallucinations(captured_pawn)

    if target_piece is not None and target_piece.color != selected_piece.color:
        award_gold(selected_piece.color, target_piece.value)
        if target_piece.__class__.__name__ == 'King':
            winner = selected_piece.color
            game_over = True
        pieces.remove(target_piece)
        remove_piece_hallucinations(target_piece)

    if selected_piece.__class__.__name__ == 'King' and abs(target_square[0] - start_square[0]) == 2:
        rook_start = (0, start_square[1]) if target_square[0] < start_square[0] else (7, start_square[1])
        rook_target = (3, start_square[1]) if target_square[0] < start_square[0] else (5, start_square[1])
        rook = get_piece_at_square(pieces, rook_start, selected_piece.stage)
        if rook is not None:
            rook.position = rook_target

    selected_piece.position = target_square
    selected_piece.has_moved = True
    keep_moved_piece_hallucinations(selected_piece, start_square)
    if (
        getattr(selected_piece, 'is_astral_projection', False)
        and selected_piece.position == selected_piece.astral_body.position
        and selected_piece.stage == selected_piece.astral_body.stage
    ):
        end_astral_projection(selected_piece, pieces)
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
        finish_board_action(pieces, ended_turn)


screen = pygame.display.set_mode((grid_size * square_size, grid_size * square_size))
move_chess_window_above_hand(
    pygame.display.get_wm_info()['window'],
    grid_size * square_size,
    grid_size * square_size,
)
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
                elif event.key == pygame.K_BACKSPACE:
                    toggle_debug_card_window()
                elif event.key == pygame.K_h:
                    toggle_hand_window()
                    toggle_pile_window()
                elif event.unicode in ('`', '~'):
                    toggle_currency_window()
                elif event.key == pygame.K_8:
                    toggle_weather_window()
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
                    for stage in stage_widths:
                        stage_widths[stage] = grid_size
                        stage_left_edges[stage] = 0
                        stage_scroll_offsets[stage] = 0
                    reset_card_game()
                    begin_turn('white')
                elif not game_over and event.key == pygame.K_LEFT:
                    scroll_board(-1)
                elif not game_over and event.key == pygame.K_RIGHT:
                    scroll_board(1)
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
        process_debug_card_window_commands()
        current_stage = normalize_stage_index(current_stage)
        send_secondary_window_state()
        send_pile_window_state()
        send_weather_window_state()
        draw_board()
        draw_storm_clouds()
        draw_all_pieces(board_pieces)
        draw_fog_of_war()
        draw_game_over_overlay()
        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    main()
