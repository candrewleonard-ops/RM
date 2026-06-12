"""Level definitions and per-level game state (moves, goals, win/lose)."""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from .board import Board, Color


@dataclass
class Goal:
    kind: str                 # "color" | "grass" | "box"
    target: int
    color: Color | None = None

    def label(self) -> str:
        if self.kind == "color":
            return self.color.name.title()
        return {"grass": "Grass", "box": "Boxes"}[self.kind]


@dataclass
class LevelDef:
    number: int
    rows: int = 9
    cols: int = 9
    num_colors: int = 5
    moves: int = 25
    goals: list[Goal] = field(default_factory=list)
    # layout strings: '.' empty cell, 'g' grass, 'b' box (1hp), 'B' box (2hp)
    layout: list[str] | None = None


def _layout_rows(pattern: list[str], rows: int, cols: int) -> list[str]:
    out = [row.ljust(cols, ".")[:cols] for row in pattern]
    while len(out) < rows:
        out.append("." * cols)
    return out[:rows]


LEVELS: list[LevelDef] = [
    LevelDef(1, rows=8, cols=8, num_colors=4, moves=20, goals=[
        Goal("color", 30, Color.RED),
        Goal("color", 30, Color.BLUE),
    ]),
    LevelDef(2, rows=8, cols=8, num_colors=5, moves=22, goals=[
        Goal("color", 40, Color.GREEN),
        Goal("color", 25, Color.YELLOW),
    ]),
    LevelDef(3, rows=9, cols=9, num_colors=5, moves=24, goals=[
        Goal("grass", 20),
    ], layout=[
        ".........",
        ".ggggggg.",
        ".ggggggg.",
        ".g.....g.",
        ".g.....g.",
        ".g.....g.",
        ".ggggggg.",
        "..ggggg..",
    ]),
    LevelDef(4, rows=9, cols=9, num_colors=5, moves=26, goals=[
        Goal("box", 10),
        Goal("color", 30, Color.PURPLE),
    ], layout=[
        ".........",
        "..b...b..",
        ".b.b.b.b.",
        "..b...b..",
        ".........",
        "..b...b..",
        ".........",
    ]),
    LevelDef(5, rows=9, cols=9, num_colors=5, moves=28, goals=[
        Goal("grass", 24),
        Goal("box", 6),
    ], layout=[
        "B.g.g.g.B",
        ".ggggggg.",
        "g.g.g.g.g",
        ".ggggggg.",
        "B...g...B",
        ".g.g.g.g.",
        "B.......B",
    ]),
    LevelDef(6, rows=9, cols=9, num_colors=6, moves=30, goals=[
        Goal("color", 50, Color.ORANGE),
        Goal("grass", 30),
        Goal("box", 9),
    ], layout=[
        "bgggggggb",
        "gBgggggBg",
        "ggggggggg",
        "gg.....gg",
        "gg.bbb.gg",
        "gg.....gg",
        "ggggggggg",
        "bgggggggb",
    ]),
]


class GameState:
    """One level in play: a board plus moves, score, and goal tracking."""

    def __init__(self, level: LevelDef, seed: int | None = None):
        self.level = level
        self.board = Board(level.rows, level.cols, level.num_colors,
                           rng=random.Random(seed))
        self.moves_left = level.moves
        self.score = 0
        self._apply_layout()
        self.board.fill_random()
        if not self.board.has_valid_move():
            self.board.shuffle()
        self._start_grass = sum(self.board.grid[r][c].grass
                                for r in range(level.rows) for c in range(level.cols))
        self._start_boxes = sum(1 for r in range(level.rows) for c in range(level.cols)
                                if self.board.grid[r][c].box > 0)

    def _apply_layout(self) -> None:
        if not self.level.layout:
            return
        rows = _layout_rows(self.level.layout, self.level.rows, self.level.cols)
        for r, row in enumerate(rows):
            for c, ch in enumerate(row):
                if ch == "g":
                    self.board.grid[r][c].grass = 1
                elif ch == "b":
                    self.board.grid[r][c].box = 1
                elif ch == "B":
                    self.board.grid[r][c].box = 2

    # -- goal progress --------------------------------------------------------

    def goal_progress(self, goal: Goal) -> int:
        if goal.kind == "color":
            return min(self.board.collected[goal.color], goal.target)
        if goal.kind == "grass":
            return min(self.board.grass_cleared, goal.target)
        if goal.kind == "box":
            return min(self.board.boxes_cleared, goal.target)
        return 0

    @property
    def won(self) -> bool:
        return all(self.goal_progress(g) >= g.target for g in self.level.goals)

    @property
    def lost(self) -> bool:
        return self.moves_left <= 0 and not self.won

    @property
    def over(self) -> bool:
        return self.won or self.lost

    # -- player actions -------------------------------------------------------

    def try_swap(self, a: tuple[int, int], b: tuple[int, int]):
        """Returns resolve steps if the swap was legal, else None."""
        if self.over or not self.board.can_swap(a, b):
            return None
        self.moves_left -= 1
        steps = self.board.swap(a, b)
        self._account(steps)
        return steps

    def tap(self, pos: tuple[int, int]):
        p = self.board.piece(*pos)
        if self.over or not p or not p.is_special:
            return None
        self.moves_left -= 1
        steps = self.board.tap_special(pos)
        self._account(steps)
        return steps

    def _account(self, steps) -> None:
        for s in steps:
            self.score += s.score
        if not self.over and not self.board.has_valid_move():
            self.board.shuffle()
