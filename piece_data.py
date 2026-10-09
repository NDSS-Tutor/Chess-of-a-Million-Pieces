import pygame
class Pawn:
    def __init__(self, color):
        self.color = color
        self.symbol = 'P'
        self.value = 1
        self.position = (0,0)
        if self.color == 'white':
            self.image = pygame.image.load('Piece Icons/white_pawn.png')
        else:
            self.image = pygame.image.load('Piece Icons/black_pawn.png')
class Rook:
    def __init__(self, color):
        self.color = color
        self.symbol = 'R'
        self.value = 5
        self.position = (0,0)
        if self.color == 'white':
            self.image = pygame.image.load('Piece Icons/white_rook.png')
        else:
            self.image = pygame.image.load('Piece Icons/black_rook.png')
class Knight:
    def __init__(self, color):
        self.color = color
        self.symbol = 'N'
        self.value = 3
        self.position = (0,0)
        if self.color == 'white':
            self.image = pygame.image.load('Piece Icons/white_knight.png')
        else:
            self.image = pygame.image.load('Piece Icons/black_knight.png')
class Bishop:
    def __init__(self, color):
        self.color = color
        self.symbol = 'B'
        self.value = 3
        self.position = (0,0)
        if self.color == 'white':
            self.image = pygame.image.load('Piece Icons/white_bishop.png')
        else:
            self.image = pygame.image.load('Piece Icons/black_bishop.png')
class Queen:
    def __init__(self, color):
        self.color = color
        self.symbol = 'Q'
        self.value = 9
        self.position = (0,0)
        if self.color == 'white':
            self.image = pygame.image.load('Piece Icons/white_queen.png')
        else:
            self.image = pygame.image.load('Piece Icons/black_queen.png')
class King:
    def __init__(self, color):
        self.color = color
        self.symbol = 'K'
        self.value = 0
        self.position = (0,0)
        if self.color == 'white':
            self.image = pygame.image.load('Piece Icons/white_king.png')
        else:
            self.image = pygame.image.load('Piece Icons/black_king.png')