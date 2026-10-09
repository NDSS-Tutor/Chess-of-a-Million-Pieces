import pygame
import sys
import piece_data

pygame.init()

grid_size = 8
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
current_stage = 1


def draw_board():
    for i in range(grid_size):
        for j in range(grid_size):
            rect_x = i * 100
            rect_y = j * 100
            color = stages[list(stages.keys())[current_stage]][0] if (i + j) % 2 == 0 else stages[list(stages.keys())[current_stage]][1]
            pygame.draw.rect(screen, color, (rect_x, rect_y, 100, 100))
    
def draw_piece(piece, x=None, y=None):
    if x is None or y is None:
        x, y = piece.position
    if piece.image == None:
        font = pygame.font.Font(None, 72)
        color = (255, 255, 255) if piece.color == 'white' else (0, 0, 0)
        text = font.render(piece.symbol, True, color)
        text_rect = text.get_rect(center=(x * 100 + 50, y * 100 + 50))
        screen.blit(text, text_rect)
    else:
        screen.blit(piece.image, (x * 100, y * 100))
    piece.position = (x, y)
def draw_all_pieces(side):
    if side == 'black':
        draw_piece(piece_data.Rook('black'), 0, 0)
        draw_piece(piece_data.Knight('black'), 1, 0)
        draw_piece(piece_data.Bishop('black'), 2, 0)
        draw_piece(piece_data.Queen('black'), 3, 0)
        draw_piece(piece_data.King('black'), 4, 0)
        draw_piece(piece_data.Bishop('black'), 5, 0)
        draw_piece(piece_data.Knight('black'), 6, 0)
        draw_piece(piece_data.Rook('black'), 7, 0)
        for i in range(grid_size):
            draw_piece(piece_data.Pawn('black'), i, 1)
    if side == 'white':
        draw_piece(piece_data.Rook('white'), 0, 7)
        draw_piece(piece_data.Knight('white'), 1, 7)
        draw_piece(piece_data.Bishop('white'), 2, 7)
        draw_piece(piece_data.Queen('white'), 3, 7)
        draw_piece(piece_data.King('white'), 4, 7)
        draw_piece(piece_data.Bishop('white'), 5, 7)
        draw_piece(piece_data.Knight('white'), 6, 7)
        draw_piece(piece_data.Rook('white'), 7, 7)
        for i in range(grid_size):
            draw_piece(piece_data.Pawn('white'), i, 6)















screen = pygame.display.set_mode((grid_size * 100, grid_size * 100))
pygame.draw.rect(screen, (255, 0, 0), (50, 50, 100, 100))

running = True
while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                running = False
            if event.key == pygame.K_UP:
                if current_stage > 0:
                    current_stage -= 1
            if event.key == pygame.K_DOWN:
                if current_stage < len(list(stages.keys())) - 1:
                    current_stage += 1
    draw_board()
    draw_all_pieces('black')
    draw_all_pieces('white')

    pygame.display.flip()
pygame.quit()
