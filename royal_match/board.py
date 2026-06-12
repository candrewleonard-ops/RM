"""Core match-3 board logic: matching, specials, obstacles, gravity.

This module is pure Python (no pygame) so it can be unit tested headless.
The UI consumes the event lists returned by the board operations to drive
animations.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum, auto


class Color(Enum):
    RED = 0
    GREEN = 1
    BLUE = 2
    YELLOW = 3
    PURPLE = 4
    ORANGE = 5


class Special(Enum):
    NONE = auto()
    ROCKET_H = auto()    # 4 in a vertical line -> clears its row? see make rules below
    ROCKET_V = auto()
    PROPELLER = auto()   # 2x2 square
    TNT = auto()         # L / T shaped match of 5+
    LIGHT_BALL = auto()  # 5 in a straight line


@dataclass
class Piece:
    color: Color | None          # None for color-less specials (light ball)
    special: Special = Special.NONE

    @property
    def is_special(self) -> bool:
        return self.special is not Special.NONE


@dataclass
class Cell:
    piece: Piece | None = None
    grass: int = 0      # grass layers under the piece, cleared by matches on the cell
    box: int = 0        # box hit points; a box blocks the cell (no piece while > 0)

    @property
    def blocked(self) -> bool:
        return self.box > 0


# ---------------------------------------------------------------------------
# Events: returned to the UI so it can animate what happened.
# ---------------------------------------------------------------------------

@dataclass
class ClearEvent:
    cells: list[tuple[int, int]]
    source: str = "match"        # match | rocket | tnt | propeller | light | box | grass


@dataclass
class SpecialCreatedEvent:
    pos: tuple[int, int]
    piece: Piece


@dataclass
class FallEvent:
    moves: list[tuple[tuple[int, int], tuple[int, int]]]   # (src, dst)
    spawns: list[tuple[tuple[int, int], Piece, int]]       # (dst, piece, drop_height)


@dataclass
class ResolveStep:
    clears: list[ClearEvent] = field(default_factory=list)
    specials: list[SpecialCreatedEvent] = field(default_factory=list)
    fall: FallEvent | None = None
    score: int = 0


class Board:
    def __init__(self, rows: int, cols: int, num_colors: int = 5,
                 rng: random.Random | None = None):
        self.rows = rows
        self.cols = cols
        self.colors = list(Color)[:num_colors]
        self.rng = rng or random.Random()
        self.grid: list[list[Cell]] = [[Cell() for _ in range(cols)] for _ in range(rows)]
        self.collected: dict[Color, int] = {c: 0 for c in Color}
        self.boxes_cleared = 0
        self.grass_cleared = 0

    # -- helpers ------------------------------------------------------------

    def in_bounds(self, r: int, c: int) -> bool:
        return 0 <= r < self.rows and 0 <= c < self.cols

    def cell(self, r: int, c: int) -> Cell:
        return self.grid[r][c]

    def piece(self, r: int, c: int) -> Piece | None:
        return self.grid[r][c].piece

    def fill_random(self, no_matches: bool = True) -> None:
        """Fill all empty, unblocked cells with random pieces."""
        for r in range(self.rows):
            for c in range(self.cols):
                cell = self.grid[r][c]
                if cell.blocked or cell.piece is not None:
                    continue
                choices = list(self.colors)
                if no_matches:
                    banned = self._banned_colors(r, c)
                    choices = [col for col in choices if col not in banned] or list(self.colors)
                cell.piece = Piece(self.rng.choice(choices))

    def _banned_colors(self, r: int, c: int) -> set[Color]:
        """Colors that would create an immediate match at (r, c)."""
        banned: set[Color] = set()
        for dr, dc in ((0, -1), (-1, 0)):
            a = self.piece(r + dr, c + dc) if self.in_bounds(r + dr, c + dc) else None
            b = self.piece(r + 2 * dr, c + 2 * dc) if self.in_bounds(r + 2 * dr, c + 2 * dc) else None
            if a and b and a.color is not None and a.color == b.color:
                banned.add(a.color)
        # also avoid completing a 2x2 square with the up-left neighbours
        square = [(r - 1, c - 1), (r - 1, c), (r, c - 1)]
        if all(self.in_bounds(*p) and self.piece(*p) for p in square):
            colors = {self.piece(*p).color for p in square}
            if len(colors) == 1 and None not in colors:
                banned.add(colors.pop())
        return banned

    # -- match detection ----------------------------------------------------

    def _line_runs(self) -> list[list[tuple[int, int]]]:
        """All horizontal/vertical runs of 3+ same-colored pieces."""
        runs = []
        for r in range(self.rows):
            run = [(r, 0)]
            for c in range(1, self.cols + 1):
                cur = self.piece(r, c) if c < self.cols else None
                prev = self.piece(*run[-1])
                if (cur and prev and cur.color is not None and cur.color == prev.color):
                    run.append((r, c))
                else:
                    if len(run) >= 3 and self.piece(*run[0]) and self.piece(*run[0]).color is not None:
                        runs.append(run)
                    run = [(r, c)] if c < self.cols else []
        for c in range(self.cols):
            run = [(0, c)]
            for r in range(1, self.rows + 1):
                cur = self.piece(r, c) if r < self.rows else None
                prev = self.piece(*run[-1])
                if (cur and prev and cur.color is not None and cur.color == prev.color):
                    run.append((r, c))
                else:
                    if len(run) >= 3 and self.piece(*run[0]) and self.piece(*run[0]).color is not None:
                        runs.append(run)
                    run = [(r, c)] if r < self.rows else []
        return runs

    def _square_matches(self) -> list[list[tuple[int, int]]]:
        """All 2x2 squares of the same color (Royal Match propeller shape)."""
        squares = []
        for r in range(self.rows - 1):
            for c in range(self.cols - 1):
                quad = [(r, c), (r, c + 1), (r + 1, c), (r + 1, c + 1)]
                pieces = [self.piece(*p) for p in quad]
                if all(p and p.color is not None for p in pieces):
                    if len({p.color for p in pieces}) == 1:
                        squares.append(quad)
        return squares

    def find_match_groups(self) -> list[dict]:
        """Group overlapping runs/squares; decide which special each creates.

        Returns a list of {cells, special, origin, color} dicts.
        """
        runs = self._line_runs()
        squares = self._square_matches()
        groups: list[dict] = []
        used: dict[tuple[int, int], int] = {}

        def merge_into(idx: int, cells: list[tuple[int, int]]):
            for cell in cells:
                if cell not in groups[idx]["cells"]:
                    groups[idx]["cells"].append(cell)
                used[cell] = idx

        for shape, kind in [(run, "line") for run in runs] + [(sq, "square") for sq in squares]:
            hit = next((used[c] for c in shape if c in used), None)
            if hit is None:
                groups.append({"cells": list(shape), "shapes": [(kind, shape)],
                               "color": self.piece(*shape[0]).color})
                for cell in shape:
                    used[cell] = len(groups) - 1
            else:
                groups[hit]["shapes"].append((kind, shape))
                merge_into(hit, shape)

        for g in groups:
            g["special"], g["origin"] = self._special_for_group(g)
        return groups

    def _special_for_group(self, group: dict) -> tuple[Special, tuple[int, int]]:
        lines = [s for k, s in group["shapes"] if k == "line"]
        squares = [s for k, s in group["shapes"] if k == "square"]
        h_lines = [l for l in lines if l[0][0] == l[1][0]]
        v_lines = [l for l in lines if l[0][1] == l[1][1]]
        origin = group["cells"][len(group["cells"]) // 2]

        for line in lines:
            if len(line) >= 5:
                return Special.LIGHT_BALL, line[len(line) // 2]
        if h_lines and v_lines:  # L or T shape -> TNT at the intersection
            inter = set(h_lines[0]) & set(v_lines[0])
            return Special.TNT, (inter.pop() if inter else origin)
        for line in lines:
            if len(line) == 4:
                # 4 in a row -> rocket aligned with the line direction
                special = Special.ROCKET_H if line[0][0] == line[1][0] else Special.ROCKET_V
                return special, line[1]
        if squares:
            return Special.PROPELLER, squares[0][0]
        return Special.NONE, origin

    # -- swapping -----------------------------------------------------------

    def can_swap(self, a: tuple[int, int], b: tuple[int, int]) -> bool:
        if abs(a[0] - b[0]) + abs(a[1] - b[1]) != 1:
            return False
        pa, pb = self.piece(*a), self.piece(*b)
        if pa is None or pb is None:
            return False
        if pa.is_special and pb.is_special:
            return True
        if pa.special is Special.LIGHT_BALL or pb.special is Special.LIGHT_BALL:
            return True
        self._swap_pieces(a, b)
        ok = bool(self.find_match_groups())
        self._swap_pieces(a, b)
        return ok

    def _swap_pieces(self, a: tuple[int, int], b: tuple[int, int]) -> None:
        self.grid[a[0]][a[1]].piece, self.grid[b[0]][b[1]].piece = \
            self.grid[b[0]][b[1]].piece, self.grid[a[0]][a[1]].piece

    def swap(self, a: tuple[int, int], b: tuple[int, int]) -> list[ResolveStep]:
        """Perform a swap and fully resolve the board. Returns animation steps."""
        pa, pb = self.piece(*a), self.piece(*b)
        self._swap_pieces(a, b)
        steps: list[ResolveStep] = []

        if pa and pb and (pa.is_special and pb.is_special):
            steps.append(self._combine_specials(b, a))
        elif pa and pa.special is Special.LIGHT_BALL:
            steps.append(self._activate_light_ball(b, pb.color if pb else None))
        elif pb and pb.special is Special.LIGHT_BALL:
            steps.append(self._activate_light_ball(b, pa.color if pa else None))
        steps.extend(self.resolve())
        return steps

    def tap_special(self, pos: tuple[int, int]) -> list[ResolveStep]:
        """Activate a special piece in place (Royal Match tap behaviour)."""
        p = self.piece(*pos)
        if not p or not p.is_special:
            return []
        if p.special is Special.LIGHT_BALL:
            steps = [self._activate_light_ball(pos, None)]
        else:
            cleared: set[tuple[int, int]] = set()
            self._detonate(pos, cleared)
            steps = [self._finish_clear(cleared, source=p.special.name.lower())]
        steps.extend(self.resolve())
        return steps

    # -- special activation -------------------------------------------------

    def _detonate(self, pos: tuple[int, int], cleared: set[tuple[int, int]]) -> None:
        """Clear the special at pos, chain-reacting into other specials."""
        if pos in cleared or not self.in_bounds(*pos):
            return
        p = self.piece(*pos)
        cleared.add(pos)
        if not p or not p.is_special:
            return
        targets: list[tuple[int, int]] = []
        if p.special is Special.ROCKET_H:
            targets = [(pos[0], c) for c in range(self.cols)]
        elif p.special is Special.ROCKET_V:
            targets = [(r, pos[1]) for r in range(self.rows)]
        elif p.special is Special.TNT:
            targets = [(pos[0] + dr, pos[1] + dc)
                       for dr in range(-2, 3) for dc in range(-2, 3)
                       if abs(dr) + abs(dc) <= 3]
        elif p.special is Special.PROPELLER:
            targets = [(pos[0] + dr, pos[1] + dc)
                       for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1))]
            extra = self._propeller_target(cleared)
            if extra:
                targets.append(extra)
        elif p.special is Special.LIGHT_BALL:
            color = self._most_common_color()
            targets = [(r, c) for r in range(self.rows) for c in range(self.cols)
                       if self.piece(r, c) and self.piece(r, c).color is color]
        for t in targets:
            if self.in_bounds(*t) and t not in cleared:
                tp = self.piece(*t)
                if tp and tp.is_special:
                    self._detonate(t, cleared)
                else:
                    cleared.add(t)

    def _propeller_target(self, cleared: set[tuple[int, int]]) -> tuple[int, int] | None:
        """Pick a useful target: prefer cells with obstacles, else random piece."""
        candidates = [(r, c) for r in range(self.rows) for c in range(self.cols)
                      if (r, c) not in cleared
                      and (self.grid[r][c].box > 0 or self.grid[r][c].grass > 0)]
        if not candidates:
            candidates = [(r, c) for r in range(self.rows) for c in range(self.cols)
                          if (r, c) not in cleared and self.piece(r, c)]
        return self.rng.choice(candidates) if candidates else None

    def _most_common_color(self) -> Color | None:
        counts: dict[Color, int] = {}
        for r in range(self.rows):
            for c in range(self.cols):
                p = self.piece(r, c)
                if p and p.color is not None and not p.is_special:
                    counts[p.color] = counts.get(p.color, 0) + 1
        return max(counts, key=counts.get) if counts else None

    def _activate_light_ball(self, ball_pos: tuple[int, int], color: Color | None) -> ResolveStep:
        if color is None:
            color = self._most_common_color()
        cleared = {ball_pos}
        for r in range(self.rows):
            for c in range(self.cols):
                p = self.piece(r, c)
                if p and p.color is color:
                    if p.is_special:
                        self._detonate((r, c), cleared)
                    else:
                        cleared.add((r, c))
        return self._finish_clear(cleared, source="light")

    def _combine_specials(self, at: tuple[int, int], other: tuple[int, int]) -> ResolveStep:
        pa, pb = self.piece(*at), self.piece(*other)
        kinds = {pa.special, pb.special}
        cleared: set[tuple[int, int]] = {at, other}
        r, c = at

        if kinds == {Special.LIGHT_BALL}:
            cleared |= {(rr, cc) for rr in range(self.rows) for cc in range(self.cols)
                        if self.piece(rr, cc)}
        elif Special.LIGHT_BALL in kinds:
            # Light ball + special: clear the most common color too
            color = self._most_common_color()
            for rr in range(self.rows):
                for cc in range(self.cols):
                    p = self.piece(rr, cc)
                    if p and p.color is color:
                        cleared.add((rr, cc))
            non_ball = pa if pb.special is Special.LIGHT_BALL else pb
            self.grid[r][c].piece = non_ball
            cleared.discard(at)
            self._detonate(at, cleared)
        elif Special.TNT in kinds and (Special.ROCKET_H in kinds or Special.ROCKET_V in kinds):
            for rr in range(max(0, r - 1), min(self.rows, r + 2)):
                cleared |= {(rr, cc) for cc in range(self.cols)}
            for cc in range(max(0, c - 1), min(self.cols, c + 2)):
                cleared |= {(rr, cc) for rr in range(self.rows)}
        elif kinds == {Special.TNT}:
            cleared |= {(r + dr, c + dc) for dr in range(-3, 4) for dc in range(-3, 4)
                        if self.in_bounds(r + dr, c + dc)}
        elif Special.ROCKET_H in kinds or Special.ROCKET_V in kinds:
            cleared |= {(r, cc) for cc in range(self.cols)}
            cleared |= {(rr, c) for rr in range(self.rows)}
            if Special.PROPELLER in kinds:
                extra = self._propeller_target(cleared)
                if extra:
                    cleared.add(extra)
        elif kinds == {Special.PROPELLER}:
            for _ in range(3):
                extra = self._propeller_target(cleared)
                if extra:
                    cleared.add(extra)
            cleared |= {(r + dr, c + dc) for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1))
                        if self.in_bounds(r + dr, c + dc)}
        # chain into any other specials caught in the blast
        for pos in list(cleared):
            p = self.piece(*pos) if self.in_bounds(*pos) else None
            if p and p.is_special and pos not in (at, other):
                self._detonate(pos, cleared)
        return self._finish_clear(cleared, source="combo")

    # -- clearing & resolution ----------------------------------------------

    def _finish_clear(self, cells: set[tuple[int, int]], source: str) -> ResolveStep:
        """Remove pieces, damage obstacles, count goals; return the step."""
        step = ResolveStep()
        piece_cells, box_cells, grass_cells = [], [], []
        for (r, c) in sorted(cells):
            if not self.in_bounds(r, c):
                continue
            cell = self.grid[r][c]
            if cell.box > 0:
                cell.box -= 1
                if cell.box == 0:
                    self.boxes_cleared += 1
                box_cells.append((r, c))
                continue
            if cell.piece:
                if cell.piece.color is not None:
                    self.collected[cell.piece.color] += 1
                cell.piece = None
                piece_cells.append((r, c))
                step.score += 10
            if cell.grass > 0:
                cell.grass -= 1
                self.grass_cleared += 1
                grass_cells.append((r, c))
                step.score += 20
        if piece_cells:
            step.clears.append(ClearEvent(piece_cells, source))
        if box_cells:
            step.clears.append(ClearEvent(box_cells, "box"))
        if grass_cells:
            step.clears.append(ClearEvent(grass_cells, "grass"))
        return step

    def _damage_adjacent_boxes(self, cells: set[tuple[int, int]]) -> list[tuple[int, int]]:
        """Matches damage boxes orthogonally adjacent to them (Royal Match rule)."""
        hit: list[tuple[int, int]] = []
        seen: set[tuple[int, int]] = set()
        for (r, c) in cells:
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                nr, nc = r + dr, c + dc
                if self.in_bounds(nr, nc) and (nr, nc) not in seen:
                    cell = self.grid[nr][nc]
                    if cell.box > 0:
                        seen.add((nr, nc))
                        cell.box -= 1
                        if cell.box == 0:
                            self.boxes_cleared += 1
                        hit.append((nr, nc))
        return hit

    def resolve(self) -> list[ResolveStep]:
        """Repeatedly clear matches and apply gravity until stable."""
        steps: list[ResolveStep] = []
        # settle anything already floating (e.g. after a blast)
        fall = self._apply_gravity()
        if fall.moves or fall.spawns:
            steps.append(ResolveStep(fall=fall))
        cascade = 0
        while True:
            groups = self.find_match_groups()
            if not groups:
                break
            step = ResolveStep()
            all_cells: set[tuple[int, int]] = set()
            for g in groups:
                all_cells |= set(g["cells"])
            # chain specials caught in matches
            for pos in list(all_cells):
                p = self.piece(*pos)
                if p and p.is_special:
                    self._detonate(pos, all_cells)
            clear_step = self._finish_clear(all_cells, source="match")
            box_hits = self._damage_adjacent_boxes(all_cells)
            if box_hits:
                clear_step.clears.append(ClearEvent(box_hits, "box"))
            step.clears = clear_step.clears
            step.score = clear_step.score + int(clear_step.score * 0.5 * cascade)
            # create earned specials
            for g in groups:
                if g["special"] is not Special.NONE:
                    r, c = g["origin"]
                    if not self.grid[r][c].blocked:
                        color = None if g["special"] is Special.LIGHT_BALL else g["color"]
                        piece = Piece(color, g["special"])
                        self.grid[r][c].piece = piece
                        step.specials.append(SpecialCreatedEvent((r, c), piece))
            fall = self._apply_gravity()
            if fall.moves or fall.spawns:
                step.fall = fall
            steps.append(step)
            cascade += 1
        return steps

    def _apply_gravity(self) -> FallEvent:
        moves: list[tuple[tuple[int, int], tuple[int, int]]] = []
        spawns: list[tuple[tuple[int, int], Piece, int]] = []
        for c in range(self.cols):
            write = self.rows - 1
            for r in range(self.rows - 1, -1, -1):
                cell = self.grid[r][c]
                if cell.blocked:
                    write = r - 1
                    continue
                if cell.piece is not None:
                    if r != write:
                        self.grid[write][c].piece = cell.piece
                        cell.piece = None
                        moves.append(((r, c), (write, c)))
                    write -= 1
            # refill every empty, unblocked cell (cells under boxes too, so
            # boards with boxes can never become permanently starved)
            for r in range(self.rows):
                cell = self.grid[r][c]
                if not cell.blocked and cell.piece is None:
                    piece = Piece(self.rng.choice(self.colors))
                    cell.piece = piece
                    spawns.append(((r, c), piece, r + 1))
        return FallEvent(moves, spawns)

    # -- deadlock handling ----------------------------------------------------

    def has_valid_move(self) -> bool:
        for r in range(self.rows):
            for c in range(self.cols):
                p = self.piece(r, c)
                if p and p.is_special:
                    return True
                for dr, dc in ((0, 1), (1, 0)):
                    if self.in_bounds(r + dr, c + dc) and self.can_swap((r, c), (r + dr, c + dc)):
                        return True
        return False

    def shuffle(self) -> None:
        pieces = [self.grid[r][c].piece for r in range(self.rows) for c in range(self.cols)
                  if self.grid[r][c].piece]
        for attempt in range(50):
            self.rng.shuffle(pieces)
            i = 0
            for r in range(self.rows):
                for c in range(self.cols):
                    if self.grid[r][c].piece:
                        self.grid[r][c].piece = pieces[i]
                        i += 1
            if not self.find_match_groups() and self.has_valid_move():
                return
