"""Unit tests for the match-3 board logic."""

import random
import unittest

from royal_match.board import Board, Color, Piece, Special
from royal_match.levels import LEVELS, GameState


def make_board(rows=6, cols=6, colors=4, seed=1):
    return Board(rows, cols, colors, rng=random.Random(seed))


def set_colors(board, layout):
    """Fill a board from letters: R G B Y P O, '.' = empty."""
    table = {c.name[0]: c for c in Color}
    for r, row in enumerate(layout):
        for c, ch in enumerate(row):
            board.grid[r][c].piece = Piece(table[ch]) if ch in table else None


class TestMatching(unittest.TestCase):
    def test_horizontal_match_detected(self):
        b = make_board()
        set_colors(b, ["RRRGBY", "GBYGBY", "BYGBYG", "YGBYGB", "GBYGBY", "BYGBYG"])
        groups = b.find_match_groups()
        self.assertEqual(len(groups), 1)
        self.assertEqual(sorted(groups[0]["cells"]), [(0, 0), (0, 1), (0, 2)])
        self.assertIs(groups[0]["special"], Special.NONE)

    def test_no_match_on_clean_board(self):
        b = make_board()
        b.fill_random()
        self.assertEqual(b.find_match_groups(), [])

    def test_four_in_row_makes_rocket(self):
        b = make_board()
        set_colors(b, ["RRRRBY", "GBYGBY", "BYGBYG", "YGBYGB", "GBYGBY", "BYGBYG"])
        groups = b.find_match_groups()
        self.assertEqual(groups[0]["special"], Special.ROCKET_H)

    def test_five_in_row_makes_light_ball(self):
        b = make_board()
        set_colors(b, ["RRRRRY", "GBYGBY", "BYGBYG", "YGBYGB", "GBYGBY", "BYGBYG"])
        groups = b.find_match_groups()
        self.assertEqual(groups[0]["special"], Special.LIGHT_BALL)

    def test_l_shape_makes_tnt(self):
        b = make_board()
        set_colors(b, ["RRRGBY", "RBYGBY", "RYGBYG", "YGBYGB", "GBYGBY", "BYGBYG"])
        groups = b.find_match_groups()
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["special"], Special.TNT)
        self.assertEqual(groups[0]["origin"], (0, 0))

    def test_square_makes_propeller(self):
        b = make_board()
        set_colors(b, ["RRGBYG", "RRYGBY", "BYGBYG", "YGBYGB", "GBYGBY", "BYGBYG"])
        groups = b.find_match_groups()
        self.assertEqual(groups[0]["special"], Special.PROPELLER)


class TestSwap(unittest.TestCase):
    def test_valid_swap_resolves(self):
        b = make_board()
        set_colors(b, ["RRGRBY", "GBRGBY", "BYGBYG", "YGBYGB", "GBYGBY", "BYGBYG"])
        # swapping (1,2)R with (0,2)G completes RRR on row 0
        self.assertTrue(b.can_swap((0, 2), (1, 2)))
        steps = b.swap((0, 2), (1, 2))
        self.assertTrue(steps)
        self.assertGreaterEqual(b.collected[Color.RED], 3)

    def test_invalid_swap_rejected(self):
        b = make_board()
        set_colors(b, ["RGBYRG", "GBYRGB", "BYRGBY", "YRGBYR", "RGBYRG", "GBYRGB"])
        self.assertFalse(b.can_swap((0, 0), (0, 1)))

    def test_non_adjacent_swap_rejected(self):
        b = make_board()
        b.fill_random()
        self.assertFalse(b.can_swap((0, 0), (0, 2)))

    def test_board_full_after_resolve(self):
        b = make_board(seed=7)
        b.fill_random()
        # find any valid move and run it; the board must end full and stable
        for _ in range(5):
            move = None
            for r in range(b.rows):
                for c in range(b.cols):
                    for d in ((0, 1), (1, 0)):
                        if b.in_bounds(r + d[0], c + d[1]) and b.can_swap((r, c), (r + d[0], c + d[1])):
                            move = ((r, c), (r + d[0], c + d[1]))
                            break
                    if move:
                        break
                if move:
                    break
            if not move:
                b.shuffle()
                continue
            b.swap(*move)
            for r in range(b.rows):
                for c in range(b.cols):
                    self.assertIsNotNone(b.piece(r, c))
            self.assertEqual(b.find_match_groups(), [])


class TestSpecials(unittest.TestCase):
    def test_rocket_clears_row(self):
        b = make_board()
        set_colors(b, ["RGBYRG", "GBYRGB", "BYRGBY", "YRGBYR", "RGBYRG", "GBYRGB"])
        b.grid[2][3].piece = Piece(Color.RED, Special.ROCKET_H)
        steps = b.tap_special((2, 3))
        cleared = steps[0].clears[0].cells
        for c in range(b.cols):
            self.assertIn((2, c), cleared)

    def test_tnt_clears_area(self):
        b = make_board()
        set_colors(b, ["RGBYRG", "GBYRGB", "BYRGBY", "YRGBYR", "RGBYRG", "GBYRGB"])
        b.grid[2][2].piece = Piece(Color.RED, Special.TNT)
        steps = b.tap_special((2, 2))
        cleared = set(steps[0].clears[0].cells)
        self.assertIn((2, 2), cleared)
        self.assertIn((0, 2), cleared)
        self.assertIn((4, 2), cleared)
        self.assertIn((2, 0), cleared)

    def test_light_ball_clears_color(self):
        b = make_board()
        set_colors(b, ["RGBYRG", "GBYRGB", "BYRGBY", "YRGBYR", "RGBYRG", "GBYRGB"])
        b.grid[0][0].piece = Piece(None, Special.LIGHT_BALL)
        b.grid[0][1].piece = Piece(Color.RED)
        before_red = sum(1 for r in range(6) for c in range(6)
                         if b.piece(r, c) and b.piece(r, c).color is Color.RED
                         and not b.piece(r, c).is_special)
        steps = b.swap((0, 0), (0, 1))
        self.assertGreaterEqual(b.collected[Color.RED], before_red)
        self.assertTrue(steps)

    def test_rocket_chain_reaction(self):
        b = make_board()
        set_colors(b, ["RGBYRG", "GBYRGB", "BYRGBY", "YRGBYR", "RGBYRG", "GBYRGB"])
        b.grid[2][2].piece = Piece(Color.RED, Special.ROCKET_H)
        b.grid[2][4].piece = Piece(Color.BLUE, Special.ROCKET_V)
        steps = b.tap_special((2, 2))
        cleared = set(steps[0].clears[0].cells)
        # the horizontal rocket hits the vertical one, which clears column 4
        self.assertIn((0, 4), cleared)
        self.assertIn((5, 4), cleared)


class TestObstacles(unittest.TestCase):
    def test_match_clears_grass_underneath(self):
        b = make_board()
        set_colors(b, ["RRGRBY", "GBRGBY", "BYGBYG", "YGBYGB", "GBYGBY", "BYGBYG"])
        b.grid[0][0].grass = 1
        b.swap((0, 2), (1, 2))
        self.assertEqual(b.grid[0][0].grass, 0)
        self.assertGreaterEqual(b.grass_cleared, 1)

    def test_match_damages_adjacent_box(self):
        b = make_board()
        set_colors(b, ["RRGRBY", "GBRGBY", "BYGBYG", "YGBYGB", "GBYGBY", "BYGBYG"])
        b.grid[1][0].piece = None
        b.grid[1][0].box = 1
        b.swap((0, 2), (1, 2))   # makes RRR on row 0, adjacent to the box
        self.assertEqual(b.grid[1][0].box, 0)
        self.assertEqual(b.boxes_cleared, 1)
        # the freed cell must have been refilled
        self.assertIsNotNone(b.piece(1, 0))

    def test_boxes_do_not_fall(self):
        b = make_board()
        b.grid[3][2].box = 2
        b.fill_random()
        b._apply_gravity()
        self.assertEqual(b.grid[3][2].box, 2)
        self.assertIsNone(b.grid[3][2].piece)


class TestLevels(unittest.TestCase):
    def test_all_levels_construct(self):
        for i, lvl in enumerate(LEVELS):
            gs = GameState(lvl, seed=42)
            self.assertFalse(gs.over)
            self.assertTrue(gs.board.has_valid_move())

    def test_goals_are_achievable(self):
        """Obstacle goals must not exceed what the layout actually contains."""
        for lvl in LEVELS:
            gs = GameState(lvl, seed=1)
            for goal in lvl.goals:
                if goal.kind == "grass":
                    self.assertLessEqual(goal.target, gs._start_grass,
                                         f"level {lvl.number}")
                elif goal.kind == "box":
                    self.assertLessEqual(goal.target, gs._start_boxes,
                                         f"level {lvl.number}")

    def test_moves_decrease_and_lose(self):
        gs = GameState(LEVELS[0], seed=3)
        gs.moves_left = 1
        move = None
        b = gs.board
        for r in range(b.rows):
            for c in range(b.cols):
                for d in ((0, 1), (1, 0)):
                    if b.in_bounds(r + d[0], c + d[1]) and b.can_swap((r, c), (r + d[0], c + d[1])):
                        move = ((r, c), (r + d[0], c + d[1]))
        self.assertIsNotNone(move)
        gs.try_swap(*move)
        self.assertEqual(gs.moves_left, 0)
        self.assertTrue(gs.over)

    def test_random_playthrough_is_stable(self):
        """Play 200 random moves across levels; nothing should crash or desync."""
        for seed in (5, 11):
            gs = GameState(LEVELS[3], seed=seed)
            rng = random.Random(seed)
            for _ in range(100):
                if gs.over:
                    break
                gs.moves_left = max(gs.moves_left, 10)
                b = gs.board
                moves = []
                for r in range(b.rows):
                    for c in range(b.cols):
                        p = b.piece(r, c)
                        if p and p.is_special:
                            moves.append(("tap", (r, c)))
                        for d in ((0, 1), (1, 0)):
                            n = (r + d[0], c + d[1])
                            if b.in_bounds(*n) and b.can_swap((r, c), n):
                                moves.append(("swap", ((r, c), n)))
                self.assertTrue(moves, "board should always have a move after shuffle")
                kind, m = rng.choice(moves)
                if kind == "tap":
                    gs.tap(m)
                else:
                    gs.try_swap(*m)
                # invariant: every unblocked cell holds a piece, no pending matches
                for r in range(b.rows):
                    for c in range(b.cols):
                        cell = b.grid[r][c]
                        if cell.blocked:
                            self.assertIsNone(cell.piece)
                        else:
                            self.assertIsNotNone(cell.piece, f"hole at {(r, c)}")
                self.assertEqual(b.find_match_groups(), [])


if __name__ == "__main__":
    unittest.main()
