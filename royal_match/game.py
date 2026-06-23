"""Pygame frontend: rendering, input, animation, and screens."""

from __future__ import annotations

import json
import math
import os
import sys

import pygame

from .board import ClearEvent, Color, Piece, ResolveStep, Special
from .levels import LEVELS, GameState

CELL = 64
WIDTH, HEIGHT = 780, 860
FPS = 60
SAVE_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "save.json")

PIECE_COLORS = {
    Color.RED: (231, 76, 60),
    Color.GREEN: (46, 204, 113),
    Color.BLUE: (52, 152, 219),
    Color.YELLOW: (241, 196, 15),
    Color.PURPLE: (155, 89, 182),
    Color.ORANGE: (230, 126, 34),
}

BG_TOP = (24, 32, 72)
BG_BOTTOM = (52, 28, 84)
GOLD = (255, 208, 80)
WHITE = (245, 245, 250)


def lighten(color, amount=60):
    return tuple(min(255, ch + amount) for ch in color)


def darken(color, amount=60):
    return tuple(max(0, ch - amount) for ch in color)


def draw_star(surf, cx, cy, r, filled=True):
    pts = []
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        rr = r if i % 2 == 0 else r * 0.45
        pts.append((cx + math.cos(a) * rr, cy + math.sin(a) * rr))
    if filled:
        pygame.draw.polygon(surf, GOLD, pts)
        pygame.draw.polygon(surf, lighten(GOLD, 20), pts, 1)
    else:
        pygame.draw.polygon(surf, (70, 60, 95), pts)
        pygame.draw.polygon(surf, (110, 95, 150), pts, 2)


# ---------------------------------------------------------------------------
# Optional synthesized sound effects (no asset files needed).
# ---------------------------------------------------------------------------

class Sounds:
    def __init__(self):
        self.enabled = False
        self.muted = False
        try:
            import numpy as np
            pygame.mixer.init(frequency=22050, size=-16, channels=2)
            self.np = np
            self.enabled = True
            self._cache = {
                "swap": self._tone([520], 0.07, 0.25),
                "match": self._tone([660, 880], 0.12, 0.3),
                "special": self._tone([440, 660, 880], 0.2, 0.35),
                "boom": self._noise(0.25, 0.4),
                "win": self._tone([523, 659, 784, 1047], 0.5, 0.35),
                "lose": self._tone([392, 330, 262], 0.5, 0.3),
            }
        except Exception:
            self.enabled = False

    def _tone(self, freqs, dur, vol):
        np = self.np
        rate = 22050
        n = int(rate * dur)
        t = np.linspace(0, dur, n, endpoint=False)
        wave = np.zeros(n)
        seg = n // len(freqs)
        for i, f in enumerate(freqs):
            sl = slice(i * seg, n if i == len(freqs) - 1 else (i + 1) * seg)
            wave[sl] = np.sin(2 * math.pi * f * t[sl])
        env = np.minimum(1.0, np.linspace(0, 8, n)) * np.linspace(1, 0, n)
        samples = (wave * env * vol * 32767).astype(np.int16)
        return pygame.sndarray.make_sound(np.column_stack([samples, samples]).copy())

    def _noise(self, dur, vol):
        np = self.np
        rate = 22050
        n = int(rate * dur)
        wave = np.random.uniform(-1, 1, n) * np.linspace(1, 0, n) ** 2
        samples = (wave * vol * 32767).astype(np.int16)
        return pygame.sndarray.make_sound(np.column_stack([samples, samples]).copy())

    def play(self, name):
        if self.enabled and not self.muted and name in self._cache:
            self._cache[name].play()


# ---------------------------------------------------------------------------
# Piece drawing
# ---------------------------------------------------------------------------

def draw_piece(surf, piece: Piece, x, y, size=CELL, scale=1.0):
    """Draw a piece centered in the cell whose top-left is (x, y)."""
    cx, cy = x + size // 2, y + size // 2
    rad = int(size * 0.38 * scale)
    if rad <= 1:
        return
    color = PIECE_COLORS.get(piece.color, (220, 220, 230))

    if piece.special is Special.LIGHT_BALL:
        glow = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.circle(glow, (255, 240, 160, 90), (size // 2, size // 2), int(rad * 1.25))
        surf.blit(glow, (x, y))
        pygame.draw.circle(surf, (90, 60, 160), (cx, cy), rad)
        pygame.draw.circle(surf, GOLD, (cx, cy), rad, 3)
        for i in range(6):
            a = i * math.pi / 3 + pygame.time.get_ticks() * 0.002
            px = cx + math.cos(a) * rad * 0.55
            py = cy + math.sin(a) * rad * 0.55
            pygame.draw.circle(surf, (255, 240, 180), (int(px), int(py)), max(2, rad // 6))
        return

    if piece.special in (Special.ROCKET_H, Special.ROCKET_V):
        horiz = piece.special is Special.ROCKET_H
        w, h = (int(rad * 2.1), int(rad * 1.1)) if horiz else (int(rad * 1.1), int(rad * 2.1))
        body = pygame.Rect(0, 0, w, h)
        body.center = (cx, cy)
        pygame.draw.rect(surf, darken(color, 30), body, border_radius=rad // 2)
        pygame.draw.rect(surf, lighten(color, 40), body.inflate(-w // 3, -h // 3),
                         border_radius=rad // 3)
        tip = rad // 2
        if horiz:
            pygame.draw.polygon(surf, GOLD, [(body.right, cy - tip), (body.right + tip, cy),
                                             (body.right, cy + tip)])
            pygame.draw.polygon(surf, GOLD, [(body.left, cy - tip), (body.left - tip, cy),
                                             (body.left, cy + tip)])
        else:
            pygame.draw.polygon(surf, GOLD, [(cx - tip, body.top), (cx, body.top - tip),
                                             (cx + tip, body.top)])
            pygame.draw.polygon(surf, GOLD, [(cx - tip, body.bottom), (cx, body.bottom + tip),
                                             (cx + tip, body.bottom)])
        return

    if piece.special is Special.TNT:
        body = pygame.Rect(0, 0, int(rad * 1.7), int(rad * 1.9))
        body.center = (cx, cy + rad // 6)
        pygame.draw.rect(surf, (200, 50, 40), body, border_radius=6)
        pygame.draw.rect(surf, (255, 230, 200), body.inflate(-6, -int(rad * 1.3)))
        pygame.draw.line(surf, (120, 90, 50), (cx, body.top), (cx + rad // 2, body.top - rad // 2), 3)
        spark = pygame.time.get_ticks() // 120 % 2 == 0
        pygame.draw.circle(surf, GOLD if spark else (255, 120, 40),
                           (cx + rad // 2, body.top - rad // 2), 4)
        return

    if piece.special is Special.PROPELLER:
        pygame.draw.circle(surf, darken(color, 20), (cx, cy), rad // 3)
        spin = pygame.time.get_ticks() * 0.004
        for i in range(4):
            a = spin + i * math.pi / 2
            x2 = cx + math.cos(a) * rad
            y2 = cy + math.sin(a) * rad
            pygame.draw.line(surf, lighten(color, 30), (cx, cy), (x2, y2), max(3, rad // 4))
        pygame.draw.circle(surf, GOLD, (cx, cy), rad // 5)
        return

    # Normal pieces: a distinct shape per color, with a highlight.
    shape = piece.color
    if shape is Color.RED:        # heart
        r2 = rad
        pygame.draw.circle(surf, color, (cx - r2 // 2, cy - r2 // 3), r2 // 2 + 2)
        pygame.draw.circle(surf, color, (cx + r2 // 2, cy - r2 // 3), r2 // 2 + 2)
        pygame.draw.polygon(surf, color, [(cx - r2, cy - r2 // 6), (cx + r2, cy - r2 // 6),
                                          (cx, cy + r2)])
    elif shape is Color.GREEN:    # triangle gem
        pts = [(cx, cy - rad), (cx + rad, cy + rad * 0.75), (cx - rad, cy + rad * 0.75)]
        pygame.draw.polygon(surf, color, pts)
        pygame.draw.polygon(surf, lighten(color), [(cx, cy - rad // 2),
                                                   (cx + rad // 2, cy + rad // 2),
                                                   (cx - rad // 2, cy + rad // 2)])
    elif shape is Color.BLUE:     # droplet / round gem
        pygame.draw.circle(surf, color, (cx, cy), rad)
        pygame.draw.circle(surf, lighten(color), (cx - rad // 3, cy - rad // 3), rad // 3)
    elif shape is Color.YELLOW:   # star
        pts = []
        for i in range(10):
            a = -math.pi / 2 + i * math.pi / 5
            rr = rad if i % 2 == 0 else rad * 0.45
            pts.append((cx + math.cos(a) * rr, cy + math.sin(a) * rr))
        pygame.draw.polygon(surf, color, pts)
        pygame.draw.circle(surf, lighten(color, 40), (cx, cy), rad // 4)
    elif shape is Color.PURPLE:   # diamond
        pts = [(cx, cy - rad), (cx + rad * 0.8, cy), (cx, cy + rad), (cx - rad * 0.8, cy)]
        pygame.draw.polygon(surf, color, pts)
        pygame.draw.polygon(surf, lighten(color), [(cx, cy - rad // 2), (cx + rad * 0.4, cy),
                                                   (cx, cy + rad // 2), (cx - rad * 0.4, cy)])
    else:                          # hexagon (orange)
        pts = [(cx + math.cos(i * math.pi / 3) * rad, cy + math.sin(i * math.pi / 3) * rad)
               for i in range(6)]
        pygame.draw.polygon(surf, color, pts)
        pygame.draw.circle(surf, lighten(color, 40), (cx - rad // 4, cy - rad // 4), rad // 3)


# ---------------------------------------------------------------------------
# Animation phases (replay board events visually)
# ---------------------------------------------------------------------------

class Phase:
    duration = 0.2

    def __init__(self):
        self.t = 0.0

    @property
    def done(self):
        return self.t >= self.duration

    @property
    def k(self):
        return min(1.0, self.t / self.duration) if self.duration else 1.0


class SwapPhase(Phase):
    duration = 0.16

    def __init__(self, a, b, back=False):
        super().__init__()
        self.a, self.b, self.back = a, b, back


class ClearPhase(Phase):
    duration = 0.22

    def __init__(self, clears: list[ClearEvent], score: int):
        super().__init__()
        self.clears = clears
        self.score = score


class SpecialPhase(Phase):
    duration = 0.18

    def __init__(self, specials):
        super().__init__()
        self.specials = specials


class FallPhase(Phase):
    def __init__(self, fall):
        super().__init__()
        self.fall = fall
        max_dist = 1
        for (src, dst) in fall.moves:
            max_dist = max(max_dist, dst[0] - src[0])
        for (_, _, h) in fall.spawns:
            max_dist = max(max_dist, h)
        self.duration = min(0.45, 0.10 + 0.05 * max_dist)


# ---------------------------------------------------------------------------
# Main app
# ---------------------------------------------------------------------------

class Game:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Royal Match — PC Edition")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, 30)
        self.font_big = pygame.font.Font(None, 64)
        self.font_med = pygame.font.Font(None, 42)
        self.sounds = Sounds()
        self.bg = self._make_background()
        self.save = self._load_save()
        self.sounds.muted = bool(self.save.get("muted", False))
        self.scene = "menu"        # menu | play
        self.show_help = False
        self.earned_stars = 0
        self.state: GameState | None = None
        self.level_index = 0
        # play-scene visual state
        self.sprites: dict[tuple[int, int], Piece] = {}
        self.grass: dict[tuple[int, int], int] = {}
        self.boxes: dict[tuple[int, int], int] = {}
        self.phases: list[Phase] = []
        self.particles: list[list] = []
        self.selected: tuple[int, int] | None = None
        self.drag_from: tuple[int, int] | None = None
        self.idle_time = 0.0
        self.hint: tuple[tuple[int, int], tuple[int, int]] | None = None
        self.banner: tuple[str, float] | None = None   # (text, time left)
        self.end_timer = 0.0
        self._pending_steps = None
        self._pending_swap = None

    # -- persistence --------------------------------------------------------

    def _load_save(self):
        data = {"completed": [], "best": {}, "stars": {}, "muted": False}
        try:
            with open(SAVE_FILE) as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                data.update(loaded)
        except Exception:
            pass
        return data

    def _unlocked(self, index):
        """A level is playable once the previous one has been completed."""
        return index == 0 or LEVELS[index - 1].number in self.save["completed"]

    @staticmethod
    def _stars_for(moves_left, total_moves):
        ratio = moves_left / total_moves if total_moves else 0
        return 3 if ratio >= 0.4 else 2 if ratio >= 0.15 else 1

    def _write_save(self):
        try:
            with open(SAVE_FILE, "w") as f:
                json.dump(self.save, f)
        except OSError:
            pass

    # -- helpers --------------------------------------------------------------

    def _make_background(self):
        bg = pygame.Surface((WIDTH, HEIGHT))
        for y in range(HEIGHT):
            k = y / HEIGHT
            color = tuple(int(BG_TOP[i] + (BG_BOTTOM[i] - BG_TOP[i]) * k) for i in range(3))
            pygame.draw.line(bg, color, (0, y), (WIDTH, y))
        for i in range(40):   # subtle sparkle pattern
            x = (i * 197) % WIDTH
            y = (i * 311) % HEIGHT
            pygame.draw.circle(bg, lighten(BG_TOP, 25), (x, y), 2)
        return bg

    def board_origin(self):
        b = self.state.board
        return ((WIDTH - b.cols * CELL) // 2, HEIGHT - b.rows * CELL - 40)

    def cell_at(self, mx, my):
        ox, oy = self.board_origin()
        c, r = (mx - ox) // CELL, (my - oy) // CELL
        b = self.state.board
        return (r, c) if 0 <= r < b.rows and 0 <= c < b.cols else None

    def cell_rect(self, r, c):
        ox, oy = self.board_origin()
        return pygame.Rect(ox + c * CELL, oy + r * CELL, CELL, CELL)

    # -- level lifecycle ------------------------------------------------------

    def start_level(self, index):
        self.level_index = index
        self.state = GameState(LEVELS[index])
        self.scene = "play"
        self.phases = []
        self.particles = []
        self.selected = None
        self.hint = None
        self.idle_time = 0.0
        self.end_timer = 0.0
        self.earned_stars = 0
        self.banner = (f"Level {LEVELS[index].number}", 1.2)
        self._sync_visuals()

    def _sync_visuals(self):
        b = self.state.board
        self.sprites = {}
        self.grass = {}
        self.boxes = {}
        for r in range(b.rows):
            for c in range(b.cols):
                cell = b.grid[r][c]
                if cell.piece:
                    self.sprites[(r, c)] = cell.piece
                if cell.grass:
                    self.grass[(r, c)] = cell.grass
                if cell.box:
                    self.boxes[(r, c)] = cell.box

    def _queue_steps(self, steps: list[ResolveStep]):
        for step in steps:
            if step.clears:
                self.phases.append(ClearPhase(step.clears, step.score))
            if step.specials:
                self.phases.append(SpecialPhase(step.specials))
            if step.fall and (step.fall.moves or step.fall.spawns):
                self.phases.append(FallPhase(step.fall))

    # -- input ----------------------------------------------------------------

    def handle_event(self, ev):
        if ev.type == pygame.QUIT:
            pygame.quit()
            sys.exit()
        if self.scene == "menu":
            self._menu_event(ev)
        else:
            self._play_event(ev)

    def _help_button_rect(self):
        return pygame.Rect(WIDTH // 2 - 110, 620, 220, 56)

    def _mute_button_rect(self):
        return pygame.Rect(WIDTH - 76, 28, 48, 48)

    def _toggle_mute(self):
        self.sounds.muted = not self.sounds.muted
        self.save["muted"] = self.sounds.muted
        self._write_save()

    def _menu_event(self, ev):
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
            if self.show_help:
                self.show_help = False
            else:
                pygame.quit()
                sys.exit()
            return
        if ev.type != pygame.MOUSEBUTTONDOWN or ev.button != 1:
            return
        if self.show_help:
            self.show_help = False
            return
        if self._mute_button_rect().collidepoint(ev.pos):
            self._toggle_mute()
            return
        if self._help_button_rect().collidepoint(ev.pos):
            self.show_help = True
            return
        for i in range(len(LEVELS)):
            if self._level_button_rect(i).collidepoint(ev.pos):
                if self._unlocked(i):
                    self.start_level(i)
                else:
                    self.sounds.play("lose")
                return

    def _play_event(self, ev):
        if ev.type == pygame.KEYDOWN:
            if ev.key == pygame.K_ESCAPE:
                self.scene = "menu"
            elif ev.key == pygame.K_r:
                self.start_level(self.level_index)
            elif ev.key == pygame.K_m:
                self._toggle_mute()
            return
        if self.state.over and not self.phases:
            if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1 and self.end_timer > 0.6:
                if self.state.won and self.level_index + 1 < len(LEVELS):
                    self.start_level(self.level_index + 1)
                elif self.state.won:
                    self.scene = "menu"
                else:
                    self.start_level(self.level_index)
            return
        if self.phases:
            return  # animations playing: input locked
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            pos = self.cell_at(*ev.pos)
            if pos is None:
                self.selected = None
                return
            self.idle_time = 0.0
            self.hint = None
            p = self.state.board.piece(*pos)
            if self.selected and self.selected != pos and \
                    abs(self.selected[0] - pos[0]) + abs(self.selected[1] - pos[1]) == 1:
                self._attempt_swap(self.selected, pos)
                self.selected = None
            elif p and p.is_special and self.selected != pos and not (
                    self.selected and abs(self.selected[0] - pos[0]) +
                    abs(self.selected[1] - pos[1]) == 1):
                # tap special: but allow selecting it for a swap with drag
                self.drag_from = pos
                self.selected = pos
            else:
                self.selected = pos if p else None
                self.drag_from = pos if p else None
        elif ev.type == pygame.MOUSEBUTTONUP and ev.button == 1 and self.drag_from:
            pos = self.cell_at(*ev.pos)
            src = self.drag_from
            self.drag_from = None
            if pos == src:
                p = self.state.board.piece(*src)
                if p and p.is_special:
                    steps = self.state.tap(src)
                    if steps:
                        self.sounds.play("boom")
                        self._queue_steps(steps)
                        self.selected = None
            elif pos and abs(pos[0] - src[0]) + abs(pos[1] - src[1]) == 1:
                self._attempt_swap(src, pos)
                self.selected = None

    def _attempt_swap(self, a, b):
        steps = self.state.try_swap(a, b)
        if steps is None:
            # invalid: play a back-and-forth wiggle
            self.phases.append(SwapPhase(a, b))
            self.phases.append(SwapPhase(a, b, back=True))
            self.sounds.play("swap")
            return
        self.sounds.play("swap")
        # animate the swap first, then sync sprites and queue the steps
        self.phases.append(SwapPhase(a, b))
        self._pending_steps = steps
        self._pending_swap = (a, b)

    # -- update ---------------------------------------------------------------

    def update(self, dt):
        if self.scene != "play":
            return
        if self.banner:
            text, t = self.banner
            t -= dt
            self.banner = (text, t) if t > 0 else None
        for p in self.particles:
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            p[3] += 600 * dt
            p[4] -= dt
        self.particles = [p for p in self.particles if p[4] > 0]

        if self.phases:
            self.idle_time = 0.0
            phase = self.phases[0]
            phase.t += dt
            if phase.done:
                self._finish_phase(phase)
                self.phases.pop(0)
                if not self.phases and getattr(self, "_pending_steps", None):
                    steps, self._pending_steps = self._pending_steps, None
                    swap, self._pending_swap = self._pending_swap, None
                    a, b = swap
                    self.sprites[a], self.sprites[b] = \
                        self.sprites.get(b), self.sprites.get(a)
                    for k in (a, b):
                        if self.sprites.get(k) is None:
                            self.sprites.pop(k, None)
                    self._queue_steps(steps)
                if not self.phases:
                    self._sync_visuals()
                    if self.state.over and self.end_timer == 0.0:
                        self._on_level_end()
        else:
            self.idle_time += dt
            if self.idle_time > 4.0 and not self.hint and not self.state.over:
                self.hint = self._find_hint()
            if self.state.over:
                self.end_timer += dt
                if self.end_timer == dt:
                    self._on_level_end()

    def _on_level_end(self):
        self.end_timer = max(self.end_timer, 1e-6)
        if self.state.won:
            self.sounds.play("win")
            num = LEVELS[self.level_index].number
            if num not in self.save["completed"]:
                self.save["completed"].append(num)
            best = self.save["best"].get(str(num), 0)
            self.save["best"][str(num)] = max(best, self.state.score)
            self.earned_stars = self._stars_for(self.state.moves_left,
                                                self.state.level.moves)
            prev_stars = self.save["stars"].get(str(num), 0)
            self.save["stars"][str(num)] = max(prev_stars, self.earned_stars)
            self._write_save()
        else:
            self.earned_stars = 0
            self.sounds.play("lose")

    def _finish_phase(self, phase):
        if isinstance(phase, SwapPhase) and phase.back:
            pass  # board state unchanged; sprites already correct
        elif isinstance(phase, ClearPhase):
            for ev in phase.clears:
                for cell in ev.cells:
                    if ev.source == "grass":
                        if self.grass.get(cell, 0) > 0:
                            self.grass[cell] -= 1
                    elif ev.source == "box":
                        if self.boxes.get(cell, 0) > 0:
                            self.boxes[cell] -= 1
                            if self.boxes[cell] == 0:
                                del self.boxes[cell]
                    else:
                        self._burst(cell, ev.source)
                        self.sprites.pop(cell, None)
                        continue
                    self._burst(cell, ev.source)
            if any(ev.source in ("rocket_h", "rocket_v", "tnt", "combo", "light")
                   for ev in phase.clears):
                self.sounds.play("boom")
            else:
                self.sounds.play("match")
        elif isinstance(phase, SpecialPhase):
            for ev in phase.specials:
                self.sprites[ev.pos] = ev.piece
            self.sounds.play("special")
        elif isinstance(phase, FallPhase):
            new_sprites = dict(self.sprites)
            for (src, dst) in phase.fall.moves:
                new_sprites.pop(src, None)
            for (src, dst) in phase.fall.moves:
                new_sprites[dst] = self.sprites[src]
            for (dst, piece, _) in phase.fall.spawns:
                new_sprites[dst] = piece
            self.sprites = new_sprites

    def _burst(self, cell, source):
        rect = self.cell_rect(*cell)
        color = GOLD if source != "grass" else (110, 200, 90)
        piece = self.sprites.get(cell)
        if piece and piece.color in PIECE_COLORS and source not in ("grass", "box"):
            color = PIECE_COLORS[piece.color]
        rng = self.state.board.rng
        for _ in range(8):
            ang = rng.uniform(0, 2 * math.pi)
            speed = rng.uniform(60, 220)
            self.particles.append([rect.centerx, rect.centery,
                                   math.cos(ang) * speed, math.sin(ang) * speed - 80,
                                   rng.uniform(0.3, 0.6), color])

    def _find_hint(self):
        b = self.state.board
        for r in range(b.rows):
            for c in range(b.cols):
                for dr, dc in ((0, 1), (1, 0)):
                    if b.in_bounds(r + dr, c + dc) and b.can_swap((r, c), (r + dr, c + dc)):
                        return ((r, c), (r + dr, c + dc))
        return None

    # -- drawing ----------------------------------------------------------------

    def draw(self):
        self.screen.blit(self.bg, (0, 0))
        if self.scene == "menu":
            self._draw_menu()
        else:
            self._draw_play()
        pygame.display.flip()

    def _level_button_rect(self, i):
        cols = 3
        bw, bh, gap = 170, 110, 30
        x0 = (WIDTH - cols * bw - (cols - 1) * gap) // 2
        y0 = 260
        return pygame.Rect(x0 + (i % cols) * (bw + gap), y0 + (i // cols) * (bh + gap), bw, bh)

    def _draw_menu(self):
        title = self.font_big.render("ROYAL MATCH", True, GOLD)
        sub = self.font_med.render("PC Edition", True, WHITE)
        self.screen.blit(title, title.get_rect(center=(WIDTH // 2, 110)))
        self.screen.blit(sub, sub.get_rect(center=(WIDTH // 2, 165)))
        mouse = pygame.mouse.get_pos()
        for i, lvl in enumerate(LEVELS):
            rect = self._level_button_rect(i)
            done = lvl.number in self.save["completed"]
            unlocked = self._unlocked(i)
            hover = rect.collidepoint(mouse) and unlocked
            if not unlocked:
                base = (55, 48, 78)
            elif done:
                base = (60, 130, 90)
            else:
                base = (90, 70, 150)
            pygame.draw.rect(self.screen, lighten(base, 25) if hover else base, rect,
                             border_radius=14)
            pygame.draw.rect(self.screen, GOLD if done else (140, 120, 200), rect, 3,
                             border_radius=14)
            if not unlocked:
                self._draw_lock(rect.centerx, rect.centery - 4)
                continue
            num = self.font_big.render(str(lvl.number), True, WHITE)
            self.screen.blit(num, num.get_rect(center=(rect.centerx, rect.centery - 18)))
            stars = self.save["stars"].get(str(lvl.number), 0)
            for s in range(3):
                draw_star(self.screen, rect.centerx + (s - 1) * 30, rect.centery + 22,
                          12, filled=s < stars)
            best = self.save["best"].get(str(lvl.number))
            tag = f"Best {best:,}" if best else f"{lvl.moves} moves"
            small = self.font.render(tag, True, (220, 215, 240))
            self.screen.blit(small, small.get_rect(center=(rect.centerx, rect.bottom - 16)))

        help_rect = self._help_button_rect()
        h_hover = help_rect.collidepoint(mouse)
        pygame.draw.rect(self.screen, (90, 70, 150) if not h_hover else (110, 88, 175),
                         help_rect, border_radius=14)
        pygame.draw.rect(self.screen, (150, 130, 210), help_rect, 2, border_radius=14)
        ht = self.font_med.render("How to Play", True, WHITE)
        self.screen.blit(ht, ht.get_rect(center=help_rect.center))

        self._draw_mute_button()
        tip = self.font.render("Click a level to play  ·  Esc quits", True, (190, 185, 215))
        self.screen.blit(tip, tip.get_rect(center=(WIDTH // 2, HEIGHT - 60)))
        if self.show_help:
            self._draw_help()

    def _draw_lock(self, cx, cy):
        body = pygame.Rect(0, 0, 34, 26)
        body.center = (cx, cy + 8)
        pygame.draw.rect(self.screen, (150, 140, 175), body, border_radius=6)
        pygame.draw.arc(self.screen, (150, 140, 175),
                        pygame.Rect(cx - 12, cy - 16, 24, 28), 0.2, math.pi - 0.2, 5)
        pygame.draw.circle(self.screen, (60, 52, 85), (cx, body.centery), 4)

    def _draw_mute_button(self):
        rect = self._mute_button_rect()
        pygame.draw.rect(self.screen, (60, 50, 95), rect, border_radius=10)
        pygame.draw.rect(self.screen, (150, 130, 210), rect, 2, border_radius=10)
        cx, cy = rect.center
        pygame.draw.polygon(self.screen, WHITE,
                            [(cx - 10, cy - 5), (cx - 4, cy - 5), (cx + 2, cy - 11),
                             (cx + 2, cy + 11), (cx - 4, cy + 5), (cx - 10, cy + 5)])
        if self.sounds.muted:
            pygame.draw.line(self.screen, (255, 110, 100), (cx + 6, cy - 9),
                             (cx + 14, cy + 9), 3)
        else:
            for i in range(2):
                pygame.draw.arc(self.screen, WHITE,
                                pygame.Rect(cx + 2, cy - 8 - i * 3, 12 + i * 6, 16 + i * 6),
                                -0.7, 0.7, 2)

    def _draw_help(self):
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((8, 6, 24, 210))
        self.screen.blit(overlay, (0, 0))
        card = pygame.Rect(0, 0, 640, 640)
        card.center = (WIDTH // 2, HEIGHT // 2)
        pygame.draw.rect(self.screen, (40, 32, 86), card, border_radius=20)
        pygame.draw.rect(self.screen, GOLD, card, 4, border_radius=20)
        title = self.font_big.render("HOW TO PLAY", True, GOLD)
        self.screen.blit(title, title.get_rect(center=(card.centerx, card.y + 50)))
        lines = [
            "Swap two neighbours to line up 3+ of a color.",
            "Complete the goals before you run out of moves.",
            "Tap a special to fire it, or swap two for a combo.",
        ]
        y = card.y + 100
        for line in lines:
            t = self.font.render(line, True, (220, 215, 240))
            self.screen.blit(t, t.get_rect(center=(card.centerx, y)))
            y += 30
        specials = [
            (Piece(Color.BLUE, Special.ROCKET_H), "Rocket", "Match 4 in a line.",
             "Clears a whole row or column."),
            (Piece(Color.PURPLE, Special.PROPELLER), "Propeller", "Match a 2x2 square.",
             "Hits neighbours and an obstacle."),
            (Piece(Color.RED, Special.TNT), "TNT", "Match an L or T of 5.",
             "Explodes a wide radius."),
            (Piece(None, Special.LIGHT_BALL), "Light Ball", "Match 5 in a line.",
             "Clears every piece of one color."),
        ]
        y = card.y + 210
        for piece, name, how, effect in specials:
            draw_piece(self.screen, piece, card.x + 40, y - CELL // 2 + 14, CELL)
            n = self.font_med.render(name, True, GOLD)
            self.screen.blit(n, (card.x + 120, y - 26))
            d = self.font.render(f"{how}  {effect}", True, (215, 210, 235))
            self.screen.blit(d, (card.x + 120, y + 6))
            y += 86
        close = self.font.render("Click anywhere or press Esc to close",
                                 True, (180, 175, 210))
        self.screen.blit(close, close.get_rect(center=(card.centerx, card.bottom - 30)))

    def _draw_play(self):
        self._draw_hud()
        self._draw_board()
        for p in self.particles:
            pygame.draw.circle(self.screen, p[5], (int(p[0]), int(p[1])),
                               max(1, int(p[4] * 8)))
        if self.banner:
            text, t = self.banner
            label = self.font_big.render(text, True, GOLD)
            label.set_alpha(int(255 * min(1.0, t / 0.4)))
            self.screen.blit(label, label.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 60)))
        if self.state.over and not self.phases and self.end_timer > 0:
            self._draw_endcard()

    def _draw_hud(self):
        st = self.state
        # moves pill
        pygame.draw.rect(self.screen, (40, 30, 80), (20, 20, 150, 64), border_radius=14)
        pygame.draw.rect(self.screen, GOLD, (20, 20, 150, 64), 2, border_radius=14)
        moves = self.font_big.render(str(st.moves_left), True,
                                     WHITE if st.moves_left > 5 else (255, 110, 100))
        self.screen.blit(moves, moves.get_rect(center=(95, 44)))
        lbl = self.font.render("MOVES", True, (200, 195, 225))
        self.screen.blit(lbl, lbl.get_rect(center=(95, 72)))
        # score
        score = self.font_med.render(f"{st.score:,}", True, GOLD)
        self.screen.blit(score, score.get_rect(topright=(WIDTH - 24, 24)))
        lbl2 = self.font.render("SCORE", True, (200, 195, 225))
        self.screen.blit(lbl2, lbl2.get_rect(topright=(WIDTH - 24, 58)))
        # goals
        x = 200
        for goal in st.level.goals:
            prog = st.goal_progress(goal)
            done = prog >= goal.target
            rect = pygame.Rect(x, 18, 120, 70)
            pygame.draw.rect(self.screen, (40, 30, 80), rect, border_radius=12)
            pygame.draw.rect(self.screen, (110, 220, 130) if done else (140, 120, 200),
                             rect, 2, border_radius=12)
            if goal.kind == "color":
                draw_piece(self.screen, Piece(goal.color), rect.x + 8, rect.y + 6, 36)
            elif goal.kind == "grass":
                pygame.draw.rect(self.screen, (90, 170, 70),
                                 (rect.x + 12, rect.y + 12, 26, 26), border_radius=6)
            else:
                pygame.draw.rect(self.screen, (170, 120, 60),
                                 (rect.x + 12, rect.y + 12, 26, 26), border_radius=4)
            txt = "OK!" if done else f"{prog}/{goal.target}"
            t = self.font.render(txt, True, WHITE)
            self.screen.blit(t, t.get_rect(midleft=(rect.x + 48, rect.y + 26)))
            name = self.font.render(goal.label(), True, (200, 195, 225))
            self.screen.blit(name, name.get_rect(midbottom=(rect.centerx, rect.bottom - 6)))
            x += 132
        mute_txt = "M: unmute" if self.sounds.muted else "M: mute"
        hint = self.font.render(f"Esc: menu   R: restart   {mute_txt}   "
                                "Tap a special to fire it", True, (170, 165, 200))
        self.screen.blit(hint, (24, 100))

    def _draw_board(self):
        b = self.state.board
        ox, oy = self.board_origin()
        frame = pygame.Rect(ox - 10, oy - 10, b.cols * CELL + 20, b.rows * CELL + 20)
        pygame.draw.rect(self.screen, (30, 22, 60), frame, border_radius=16)
        pygame.draw.rect(self.screen, (120, 95, 190), frame, 3, border_radius=16)

        for r in range(b.rows):
            for c in range(b.cols):
                rect = self.cell_rect(r, c)
                shade = (52, 42, 96) if (r + c) % 2 == 0 else (60, 48, 110)
                pygame.draw.rect(self.screen, shade, rect)
                if self.grass.get((r, c), 0) > 0:
                    pygame.draw.rect(self.screen, (74, 150, 62), rect.inflate(-6, -6),
                                     border_radius=8)
                    pygame.draw.rect(self.screen, (96, 180, 80), rect.inflate(-6, -6), 2,
                                     border_radius=8)

        # selection / hint
        if self.selected:
            pygame.draw.rect(self.screen, GOLD, self.cell_rect(*self.selected), 4,
                             border_radius=8)
        if self.hint:
            pulse = 3 + int(2 * math.sin(pygame.time.get_ticks() * 0.008))
            for cell in self.hint:
                pygame.draw.rect(self.screen, (140, 230, 255), self.cell_rect(*cell),
                                 pulse, border_radius=8)

        moving, offsets, scales = self._phase_visuals()

        for (r, c), piece in self.sprites.items():
            if (r, c) in moving:
                continue
            rect = self.cell_rect(r, c)
            dx, dy = offsets.get((r, c), (0, 0))
            draw_piece(self.screen, piece, rect.x + dx, rect.y + dy,
                       scale=scales.get((r, c), 1.0))
        # moving sprites drawn on top
        for (r, c), (px, py, piece, scale) in moving.items():
            draw_piece(self.screen, piece, px, py, scale=scale)

        # boxes on top of cells (they block pieces)
        for (r, c), hp in self.boxes.items():
            rect = self.cell_rect(r, c).inflate(-8, -8)
            color = (150, 105, 55) if hp == 1 else (110, 75, 40)
            pygame.draw.rect(self.screen, color, rect, border_radius=8)
            pygame.draw.rect(self.screen, lighten(color, 30), rect, 3, border_radius=8)
            pygame.draw.line(self.screen, lighten(color, 30), rect.topleft, rect.bottomright, 3)
            pygame.draw.line(self.screen, lighten(color, 30), rect.topright, rect.bottomleft, 3)
            if hp > 1:
                t = self.font.render(str(hp), True, WHITE)
                self.screen.blit(t, t.get_rect(center=rect.center))

    def _phase_visuals(self):
        """Per-cell pixel offsets / scales / free-moving sprites for the active phase."""
        moving: dict = {}
        offsets: dict = {}
        scales: dict = {}
        if not self.phases:
            return moving, offsets, scales
        phase = self.phases[0]
        k = phase.k
        ease = 1 - (1 - k) ** 2
        if isinstance(phase, SwapPhase):
            a, b = phase.a, phase.b
            t = 1 - ease if phase.back else ease
            ra, rb = self.cell_rect(*a), self.cell_rect(*b)
            pa, pb = self.sprites.get(a), self.sprites.get(b)
            if pa:
                moving[a] = (ra.x + (rb.x - ra.x) * t, ra.y + (rb.y - ra.y) * t, pa, 1.0)
            if pb:
                moving[b] = (rb.x + (ra.x - rb.x) * t, rb.y + (ra.y - rb.y) * t, pb, 1.0)
        elif isinstance(phase, ClearPhase):
            for ev in phase.clears:
                if ev.source in ("grass", "box"):
                    continue
                for cell in ev.cells:
                    scales[cell] = max(0.0, 1.0 - ease * 1.1)
        elif isinstance(phase, SpecialPhase):
            for ev in phase.specials:
                scales[ev.pos] = 0.4 + 0.6 * ease + 0.25 * math.sin(ease * math.pi)
        elif isinstance(phase, FallPhase):
            for (src, dst) in phase.fall.moves:
                rs, rd = self.cell_rect(*src), self.cell_rect(*dst)
                piece = self.sprites.get(src)
                if piece:
                    moving[src] = (rs.x, rs.y + (rd.y - rs.y) * ease, piece, 1.0)
            for (dst, piece, h) in phase.fall.spawns:
                rd = self.cell_rect(*dst)
                start_y = rd.y - h * CELL
                moving[("spawn", dst)] = (rd.x, start_y + (rd.y - start_y) * ease, piece, 1.0)
        return moving, offsets, scales

    def _draw_endcard(self):
        won = self.state.won
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((10, 8, 30, 170))
        self.screen.blit(overlay, (0, 0))
        card = pygame.Rect(0, 0, 480, 360 if won else 300)
        card.center = (WIDTH // 2, HEIGHT // 2)
        pygame.draw.rect(self.screen, (45, 35, 95), card, border_radius=20)
        pygame.draw.rect(self.screen, GOLD if won else (200, 90, 90), card, 4,
                         border_radius=20)
        title = "LEVEL COMPLETE!" if won else "OUT OF MOVES"
        t = self.font_big.render(title, True, GOLD if won else (255, 130, 120))
        self.screen.blit(t, t.get_rect(center=(card.centerx, card.y + 55)))
        if won:
            # stars pop in one by one as the card settles
            for s in range(3):
                appear = self.end_timer > 0.3 + s * 0.25
                scale = 1.0
                if appear and self.end_timer < 0.55 + s * 0.25:
                    scale = 1.4
                draw_star(self.screen, card.centerx + (s - 1) * 64, card.y + 130,
                          int(26 * scale), filled=s < self.earned_stars and appear)
            s = self.font_med.render(f"Score: {self.state.score:,}", True, WHITE)
            self.screen.blit(s, s.get_rect(center=(card.centerx, card.y + 200)))
            nxt = "Click for next level" if self.level_index + 1 < len(LEVELS) \
                else "Click for menu — all levels done!"
            n = self.font.render(nxt, True, (210, 205, 235))
            self.screen.blit(n, n.get_rect(center=(card.centerx, card.y + 260)))
            esc = self.font.render("Esc for level select", True, (170, 165, 200))
            self.screen.blit(esc, esc.get_rect(center=(card.centerx, card.y + 300)))
        else:
            s = self.font_med.render(f"Score: {self.state.score:,}", True, WHITE)
            self.screen.blit(s, s.get_rect(center=(card.centerx, card.y + 130)))
            n = self.font.render("Click to retry", True, (210, 205, 235))
            self.screen.blit(n, n.get_rect(center=(card.centerx, card.y + 200)))
            esc = self.font.render("Esc for level select", True, (170, 165, 200))
            self.screen.blit(esc, esc.get_rect(center=(card.centerx, card.y + 240)))

    # -- main loop ---------------------------------------------------------------

    def run(self):
        while True:
            dt = self.clock.tick(FPS) / 1000.0
            for ev in pygame.event.get():
                self.handle_event(ev)
            self.update(dt)
            self.draw()


def main():
    Game().run()
