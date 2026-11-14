"""Paint mode: a gesture-driven canvas.

Right hand = the pen. The point where your thumb and index fingertips meet
is the brush tip; pinch thumb + index to paint, thumb + ring to erase.

Left hand = a set of dials. Which pose you hold chooses *what* you're
adjusting, and moving your hand adjusts it (relative, like a trackpad --
so switching pose never makes a value jump to wherever your hand happens
to be):

    1 finger  (index)               Hue          move up/down
    2 fingers (index+middle)        Brush size   move up/down
    3 fingers                       Tone         up/down = saturation,
                                                 left/right = brightness
    4 fingers / open hand           Brush style  left/right
                                    + symmetry   up/down
    Thumb alone, held               Undo last stroke
    Fist / anything else            Hands off -- nothing changes

PaintEngine is pure PIL/numpy (no Tk), so it can be tested headlessly.
PaintSession wires it to the camera hands and to the Tk window.
"""

import colorsys
import datetime
import math
import os
import random
import time
from collections import deque

import numpy as np
from PIL import Image, ImageChops, ImageDraw

import art_gestures as ag
import constants as c


BACKGROUND = (8, 8, 12)

STYLES = ['Ink', 'Glow', 'Spray', 'Rainbow']

# (label, rotations, mirrored). Each rotation is drawn once, and again
# reflected if `mirrored`, so the number of live copies is rotations x 1-or-2.
SYMMETRIES = [
	('Off', 1, False),
	('Mirror', 1, True),
	('Mirror x4', 2, True),
	('Kaleidoscope 6', 3, True),
	('Kaleidoscope 8', 4, True),
	('Kaleidoscope 12', 6, True),
]

SIZE_MIN, SIZE_MAX = 2.0, 120.0

TILE = 256        # display-pixel edge of the tiles the Tk window repaints
MAX_UNDO = 12


class PaintEngine:
	"""The painting itself: brush state, strokes, undo, save.

	Works in an internal pixel space (`scale` x the display size, so a 4K
	screen can paint into a cheaper buffer); strokes arrive in *display*
	coordinates and are converted here. `pop_dirty()` hands the Tk side the
	set of display tiles that changed since last asked, so each frame only
	the touched 256px tiles get re-uploaded, not a whole 1080p image.
	"""

	def __init__(self, display_w, display_h, scale=1.0):
		self.display_w = display_w
		self.display_h = display_h
		self.scale = scale
		self.w = max(1, round(display_w * scale))
		self.h = max(1, round(display_h * scale))

		self.img = Image.new('RGB', (self.w, self.h), BACKGROUND)
		self._undo = deque(maxlen=MAX_UNDO)
		self._dirty = set()
		self._masks = {}
		self._rng = random.Random()

		# Brush state -- the left-hand dials edit these.
		self.hue = 0.58
		self.sat = 0.85
		self.val = 1.0
		self.size = 18.0          # display pixels
		self.style = 0            # index into STYLES
		self.symmetry = 0         # index into SYMMETRIES

		# Stroke state
		self._last = None         # last point of the live stroke (internal px)
		self._erasing = False
		self._speed = 0.0         # smoothed px/frame, drives ink width
		self._rainbow = 0.0

		self.mark_all_dirty()

	# --- dirty tracking ------------------------------------------------

	def mark_all_dirty(self):
		cols = math.ceil(self.display_w / TILE)
		rows = math.ceil(self.display_h / TILE)
		self._dirty = {(tx, ty) for tx in range(cols) for ty in range(rows)}

	def _mark(self, x0, y0, x1, y1):
		"""Mark the tiles overlapped by an internal-pixel box."""
		inv = 1.0 / self.scale
		tx0 = max(0, int(x0 * inv) // TILE)
		ty0 = max(0, int(y0 * inv) // TILE)
		tx1 = min((self.display_w - 1) // TILE, int(x1 * inv) // TILE)
		ty1 = min((self.display_h - 1) // TILE, int(y1 * inv) // TILE)
		for ty in range(ty0, ty1 + 1):
			for tx in range(tx0, tx1 + 1):
				self._dirty.add((tx, ty))

	def pop_dirty(self):
		dirty, self._dirty = self._dirty, set()
		return dirty

	def tile_image(self, tx, ty):
		"""The display-resolution image for one tile."""
		x0, y0 = tx * TILE, ty * TILE
		x1, y1 = min(x0 + TILE, self.display_w), min(y0 + TILE, self.display_h)
		if self.scale == 1.0:
			return self.img.crop((x0, y0, x1, y1))
		s = self.scale
		return self.img.resize(
			(x1 - x0, y1 - y0), Image.BILINEAR, box=(x0 * s, y0 * s, x1 * s, y1 * s),
		)

	# --- brush color -------------------------------------------------------

	def color(self):
		r, g, b = colorsys.hsv_to_rgb(self.hue % 1.0, self.sat, self.val)
		return int(r * 255), int(g * 255), int(b * 255)

	def style_name(self):
		return STYLES[self.style]

	def symmetry_name(self):
		return SYMMETRIES[self.symmetry][0]

	# --- dial adjustments (all clamp/wrap, so callers can pass any delta) ---

	def adjust_hue(self, delta):
		self.hue = (self.hue + delta) % 1.0

	def adjust_size(self, log_delta):
		"""Exponential, so each bit of hand travel is the same *proportional*
		change -- linear steps are far too coarse at 3px and far too fine
		at 100px."""
		self.size = min(max(self.size * math.exp(log_delta), SIZE_MIN), SIZE_MAX)

	def adjust_saturation(self, delta):
		self.sat = min(max(self.sat + delta, 0.0), 1.0)

	def adjust_brightness(self, delta):
		self.val = min(max(self.val + delta, 0.12), 1.0)

	def step_style(self, step):
		self.style = (self.style + step) % len(STYLES)

	def step_symmetry(self, step):
		self.symmetry = min(max(self.symmetry + step, 0), len(SYMMETRIES) - 1)

	# --- strokes -------------------------------------------------------------

	def begin_stroke(self, x, y, erase=False):
		self._undo.append(self.img.copy())
		self._erasing = erase
		self._speed = 0.0
		p = (x * self.scale, y * self.scale)
		self._last = p
		self._dab_segment(p, p)

	def move_stroke(self, x, y):
		if self._last is None:
			self.begin_stroke(x, y, self._erasing)
			return
		p = (x * self.scale, y * self.scale)
		self._dab_segment(self._last, p)
		self._last = p

	def end_stroke(self):
		self._last = None

	@property
	def stroking(self):
		return self._last is not None

	@property
	def erasing(self):
		return self._erasing

	def clear(self):
		self._undo.append(self.img.copy())
		self.img = Image.new('RGB', (self.w, self.h), BACKGROUND)
		self._last = None
		self.mark_all_dirty()

	def undo(self):
		"""Revert the most recent stroke/clear. Returns False if there's
		nothing left to undo."""
		if not self._undo:
			return False
		self.img = self._undo.pop()
		self._last = None
		self.mark_all_dirty()
		return True

	def save(self, directory=None):
		"""Write the painting out as a PNG and return its path."""
		if directory is None:
			pictures = os.path.join(os.path.expanduser('~'), 'Pictures')
			base = pictures if os.path.isdir(pictures) else os.path.expanduser('~')
			directory = os.path.join(base, 'FingerWorks')
		os.makedirs(directory, exist_ok=True)
		name = f'painting-{datetime.datetime.now():%Y%m%d-%H%M%S}.png'
		path = os.path.join(directory, name)
		self.img.save(path)
		return path

	# --- rendering -------------------------------------------------------------

	def _copies(self, p):
		"""`p` under the current symmetry: a list of internal-pixel points."""
		_label, rotations, mirrored = SYMMETRIES[self.symmetry]
		if rotations == 1 and not mirrored:
			return [p]
		cx, cy = self.w / 2.0, self.h / 2.0
		dx, dy = p[0] - cx, p[1] - cy
		out = []
		for k in range(rotations):
			ang = 2.0 * math.pi * k / rotations
			cos, sin = math.cos(ang), math.sin(ang)
			for flip in ((False, True) if mirrored else (False,)):
				ox = -dx if flip else dx
				out.append((cx + ox * cos - dy * sin, cy + ox * sin + dy * cos))
		return out

	def _mask(self, kind, r):
		key = (kind, r)
		mask = self._masks.get(key)
		if mask is None:
			n = 2 * r + 1
			yy, xx = np.mgrid[0:n, 0:n]
			d = np.hypot(xx - r, yy - r)
			if kind == 'hard':
				a = np.clip(r + 0.5 - d, 0.0, 1.0)            # 1px anti-aliased edge
			else:
				a = np.clip(1.0 - d / (r + 0.5), 0.0, 1.0) ** 2   # soft falloff
				if kind == 'halo':
					a = a * 0.55
			mask = Image.fromarray((a * 255).astype(np.uint8), 'L')
			self._masks[key] = mask
		return mask

	def _stamp(self, x, y, r, color, kind, additive=False):
		r = int(min(max(round(r), 1), 160))
		mask = self._mask(kind, r)
		x0, y0 = int(round(x)) - r, int(round(y)) - r
		n = 2 * r + 1
		# Clip to the buffer ourselves rather than trusting paste() to.
		bx0, by0 = max(x0, 0), max(y0, 0)
		bx1, by1 = min(x0 + n, self.w), min(y0 + n, self.h)
		if bx0 >= bx1 or by0 >= by1:
			return
		m = mask.crop((bx0 - x0, by0 - y0, bx1 - x0, by1 - y0))
		if additive:
			region = self.img.crop((bx0, by0, bx1, by1))
			tint = Image.composite(
				Image.new('RGB', region.size, color), Image.new('RGB', region.size, (0, 0, 0)), m,
			)
			self.img.paste(ImageChops.add(region, tint), (bx0, by0))
		else:
			self.img.paste(color, (bx0, by0, bx1, by1), m)
		self._mark(bx0, by0, bx1, by1)

	def _dab_segment(self, p0, p1):
		"""Paint the stroke from `p0` to `p1` (internal px), under symmetry."""
		dist = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
		# Smoothed speed -> calligraphic width. Fast strokes thin out, slow
		# ones swell, which is most of what makes Ink feel like a pen
		# rather than a mouse.
		self._speed = 0.7 * self._speed + 0.3 * dist
		base_r = max(self.size * self.scale / 2.0, 0.6)

		if self._erasing:
			# Erasing ignores symmetry: you want to rub out exactly what's
			# under the tip, not under its reflections too.
			self._line(p0, p1, base_r * 1.6, BACKGROUND, 'hard')
			return

		style = STYLES[self.style]
		color = self.color()
		pairs = list(zip(self._copies(p0), self._copies(p1)))

		if style == 'Ink':
			r = base_r * min(max(1.2 - self._speed / (60.0 * self.scale), 0.45), 1.2)
			for a, b in pairs:
				self._line(a, b, r, color, 'hard')
		elif style == 'Rainbow':
			self._rainbow = (self._rainbow + dist * 0.0025 / self.scale) % 1.0
			rr, gg, bb = colorsys.hsv_to_rgb(self._rainbow, max(self.sat, 0.6), self.val)
			rainbow = (int(rr * 255), int(gg * 255), int(bb * 255))
			for a, b in pairs:
				self._line(a, b, base_r, rainbow, 'hard')
		elif style == 'Glow':
			core = tuple(int(v + (255 - v) * 0.55) for v in color)
			for a, b in pairs:
				self._line(a, b, base_r * 1.7, color, 'halo', additive=True)
				self._line(a, b, base_r * 0.45, core, 'hard')
		elif style == 'Spray':
			draw = ImageDraw.Draw(self.img)
			count = int(min(max(base_r * 2.2, 10), 140))
			for _a, b in pairs:
				pts = []
				for _ in range(count):
					ang = self._rng.random() * 2.0 * math.pi
					rad = base_r * 1.4 * math.sqrt(self._rng.random())
					x, y = b[0] + rad * math.cos(ang), b[1] + rad * math.sin(ang)
					# Each speck is a 2x2 dot: single pixels vanish at
					# normal viewing size.
					pts += [(x, y), (x + 1, y), (x, y + 1), (x + 1, y + 1)]
				draw.point(pts, fill=color)
				reach = int(base_r * 1.4) + 2
				self._mark(b[0] - reach, b[1] - reach, b[0] + reach, b[1] + reach)

	def _line(self, p0, p1, r, color, kind, additive=False):
		dist = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
		# Stamp spacing: tight enough that a round brush reads as a smooth
		# line, capped so a fast hand sweep through a kaleidoscope doesn't
		# turn one frame into hundreds of stamps.
		spacing = max(r * 0.3, 1.0)
		steps = max(1, min(int(dist / spacing), 40))
		for i in range(steps + 1):
			t = i / steps
			self._stamp(
				p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t,
				r, color, kind, additive,
			)


# =====================================================================
# The Tk-facing session
# =====================================================================

# Left-hand dial poses -> (parameter label, help blurb). Order is display order.
_DIALS = [
	('one', 'HUE', 'index finger'),
	('two', 'SIZE', 'index + middle'),
	('three', 'TONE', '3 fingers'),
	('four', 'BRUSH', '4 fingers'),
]


class PaintSession:
	mode = 'paint'

	# Hand-travel -> value gains. A "frame unit" is a fraction of the
	# camera frame, so e.g. hue = 1.5 means sweeping your hand through two
	# thirds of the frame's height cycles the whole color wheel.
	HUE_GAIN = 1.5
	SIZE_GAIN = 3.2
	SAT_GAIN = 1.8
	VAL_GAIN = 1.8
	STYLE_STEP = 0.10         # frame-widths of horizontal travel per style step
	SYMMETRY_STEP = 0.09      # frame-heights of vertical travel per symmetry step

	def __init__(self, overlay, settings=None, engine=None):
		"""`engine` resumes an earlier canvas (and brush) -- see
		main_fast.start_mode(), which hands the last one back when you
		return to Paint."""
		from PIL import ImageTk
		from art_window import ArtWindow

		self.overlay = overlay
		self._ImageTk = ImageTk
		self.window = ArtWindow(overlay, bg='#08080c')
		self.canvas = self.window.canvas
		self.W, self.H = self.window.width, self.window.height

		# Paint at native resolution up to 1920px wide (so a 1080p screen
		# needs no per-tile resizing at all), and into a 1920px buffer on
		# anything bigger: a 4K canvas would cost four times the upload
		# bandwidth and undo memory per stroke for no visible gain on a
		# hand-driven brush.
		scale = min(1.0, 1920.0 / self.W)
		self.engine = engine or PaintEngine(self.W, self.H, scale)
		self.engine.end_stroke()

		self._tiles = {}
		self._build_tiles()

		self.pointer = ag.Pointer2D(min_cutoff=1.6, beta=0.012)
		self.index_pinch = ag.Pinch(c.LEFT_CLICK_CUTOFF)
		self.ring_pinch = ag.Pinch(c.RIGHT_CLICK_CUTOFF)
		self.left_pose = ag.PoseTracker(frames=3)
		self.undo_latch = ag.Latch(0.7)
		self.shaka = ag.ShakaWatch()
		self.dial_x = ag.OneEuro(min_cutoff=1.0, beta=3.0)
		self.dial_y = ag.OneEuro(min_cutoff=1.0, beta=3.0)
		self._dial_prev = None      # (x, y) in frame fractions, or None
		self._style_acc = 0.0
		self._symmetry_acc = 0.0

		self._cursor = None
		self._active_dial = None
		self._toast = None
		self._paused = False
		self._last_hands_time = time.time()

	# --- Tk tiles -----------------------------------------------------------

	def _build_tiles(self):
		eng = self.engine
		cols = math.ceil(self.W / TILE)
		rows = math.ceil(self.H / TILE)
		for ty in range(rows):
			for tx in range(cols):
				img = eng.tile_image(tx, ty)
				photo = self._ImageTk.PhotoImage(img)
				self.canvas.create_image(tx * TILE, ty * TILE, anchor='nw', image=photo, tags='tile')
				self._tiles[(tx, ty)] = photo    # keep a reference so Tk doesn't GC it
		eng.pop_dirty()

	def _refresh_tiles(self):
		for key in self.engine.pop_dirty():
			photo = self._tiles.get(key)
			if photo is not None:
				photo.paste(self.engine.tile_image(*key))

	# --- control bar actions --------------------------------------------------

	def actions(self):
		return [('Undo', self.do_undo), ('Clear', self.do_clear), ('Save', self.do_save)]

	def do_undo(self):
		self.engine.end_stroke()
		self._flash('Undo' if self.engine.undo() else 'Nothing to undo')

	def do_clear(self):
		self.engine.end_stroke()
		self.engine.clear()
		self._flash('Canvas cleared  (Undo brings it back)')

	def do_save(self):
		try:
			path = self.engine.save()
			self._flash(f'Saved  {path}', seconds=5)
		except OSError as exc:
			self._flash(f'Could not save: {exc}', seconds=5)

	def _flash(self, text, seconds=2.5):
		self._toast = (text, time.time() + seconds)

	# --- per-frame -------------------------------------------------------------

	def set_paused(self, paused):
		if paused == self._paused:
			return
		self._paused = paused
		if paused:
			self.release()
		# Redraw once on the transition (shows or clears the 'Paused'
		# banner); the main loop calls this every frame, so it must not
		# redraw when nothing changed.
		self._redraw_hud([], time.time())

	def release(self):
		"""Let go of everything held: end the stroke, forget hand state."""
		self.engine.end_stroke()
		self.pointer.reset()
		self.index_pinch.reset()
		self.ring_pinch.reset()
		self._dial_prev = None
		self.dial_x.reset()
		self.dial_y.reset()
		self.undo_latch.update(False, 0)

	def update(self, hands, now):
		"""Process one frame. Returns True if the user asked to pause."""
		if self.shaka.update(hands):
			self.release()
			return True

		right, left = ag.pick_hands(hands)
		if hands:
			self._last_hands_time = now

		cursor = self._update_pen(right, now)
		self._update_dials(left, now)

		self._refresh_tiles()
		self._redraw_hud(hands, now, cursor=cursor)
		return False

	def _update_pen(self, right, now):
		eng = self.engine
		if right is None:
			if eng.stroking:
				eng.end_stroke()
			self.pointer.reset()
			self.index_pinch.reset()
			self.ring_pinch.reset()
			return None

		erase = self.ring_pinch.update(right.pinch_dist(c.RING_IDX))
		paint = (not erase) and self.index_pinch.update(right.pinch_dist(c.INDEX_IDX))
		if erase:
			# Only one of the two pinches can be live at once, and the
			# ring pinch wins (same priority as right-click over
			# left-click in Control mode).
			self.index_pinch.reset()

		# The pen tip is wherever the *active* pinch is: thumb+ring while
		# erasing, thumb+index otherwise (including just hovering).
		px, py = right.pinch_point(c.RING_IDX if erase else c.INDEX_IDX)
		sx, sy = ag.frame_to_screen(px, py, right.frame_w, right.frame_h, self.W, self.H)
		sx, sy = self.pointer(sx, sy, now)

		if erase or paint:
			if not eng.stroking or eng.erasing != erase:
				eng.begin_stroke(sx, sy, erase=erase)
			else:
				eng.move_stroke(sx, sy)
		elif eng.stroking:
			eng.end_stroke()

		return sx, sy, erase, paint

	def _update_dials(self, left, now):
		eng = self.engine
		if left is None:
			self._active_dial = None
			self._dial_prev = None
			self.left_pose.reset()
			self.dial_x.reset()
			self.dial_y.reset()
			self.undo_latch.update(False, now)
			return

		pose = self.left_pose.update(ag.left_pose(left.fingers_out), now)

		# Thumb alone, held: undo. Fires once per hold.
		if self.undo_latch.update(pose == 'thumb', now):
			self.do_undo()

		dial = pose if pose in ('one', 'two', 'three', 'four') else None
		if dial != self._active_dial:
			# New pose: forget where the hand was, so the first frame of
			# the new dial reads as "starting here", not a huge jump from
			# wherever the hand was under the previous pose.
			self._active_dial = dial
			self._dial_prev = None
			self._style_acc = 0.0
			self._symmetry_acc = 0.0
			self.dial_x.reset()
			self.dial_y.reset()

		if dial is None:
			return

		x, y = left.palm_point()
		fx = self.dial_x(x / left.frame_w, now)
		fy = self.dial_y(y / left.frame_h, now)
		if self._dial_prev is None:
			self._dial_prev = (fx, fy)
			return
		dx = fx - self._dial_prev[0]
		dy = self._dial_prev[1] - fy          # up is positive
		self._dial_prev = (fx, fy)

		if dial == 'one':
			eng.adjust_hue(dy * self.HUE_GAIN)
		elif dial == 'two':
			eng.adjust_size(dy * self.SIZE_GAIN)
		elif dial == 'three':
			eng.adjust_saturation(dy * self.SAT_GAIN)
			eng.adjust_brightness(dx * self.VAL_GAIN)
		elif dial == 'four':
			self._style_acc += dx
			self._symmetry_acc += dy
			while self._style_acc >= self.STYLE_STEP:
				eng.step_style(1)
				self._style_acc -= self.STYLE_STEP
			while self._style_acc <= -self.STYLE_STEP:
				eng.step_style(-1)
				self._style_acc += self.STYLE_STEP
			while self._symmetry_acc >= self.SYMMETRY_STEP:
				eng.step_symmetry(1)
				self._symmetry_acc -= self.SYMMETRY_STEP
			while self._symmetry_acc <= -self.SYMMETRY_STEP:
				eng.step_symmetry(-1)
				self._symmetry_acc += self.SYMMETRY_STEP

	# --- HUD -----------------------------------------------------------------

	def _redraw_hud(self, hands, now, cursor=None):
		from art_window import hsv_hex, rgb_hex

		cv = self.canvas
		cv.delete('hud')
		eng = self.engine

		self.window.draw_ghost_hands(hands)
		if self.overlay.debug:
			self.window.draw_debug(hands)

		# Brush cursor.
		if cursor is not None:
			sx, sy, erase, paint = cursor
			r = max(eng.size / 2.0, 3.0) * (1.6 if erase else 1.0)
			col = '#ffffff' if erase else rgb_hex(eng.color())
			cv.create_oval(
				sx - r, sy - r, sx + r, sy + r, outline=col,
				width=3 if (paint or erase) else 1, tags='hud',
			)
			cv.create_line(sx - 6, sy, sx + 6, sy, fill=col, tags='hud')
			cv.create_line(sx, sy - 6, sx, sy + 6, fill=col, tags='hud')

		# Dial panel (top-left).
		x0, y0 = 24, 24
		cv.create_rectangle(x0 - 10, y0 - 10, x0 + 306, y0 + 215, fill='#14141c', outline='#2c2c3a', tags='hud')
		cv.create_oval(x0, y0, x0 + 54, y0 + 54, fill=rgb_hex(eng.color()), outline='#ffffff', width=2, tags='hud')
		cv.create_text(
			x0 + 66, y0 + 8, anchor='nw', fill='#cccccc', font=('Segoe UI', 11, 'bold'),
			text=f'{eng.style_name()}', tags='hud',
		)
		cv.create_text(
			x0 + 66, y0 + 30, anchor='nw', fill='#888899', font=('Segoe UI', 9),
			text=eng.symmetry_name(), tags='hud',
		)

		rows = [
			('one', 'HUE', eng.hue, 'hue'),
			('two', 'SIZE', (math.log(eng.size) - math.log(SIZE_MIN)) / (math.log(SIZE_MAX) - math.log(SIZE_MIN)), 'plain'),
			('three', 'SAT', eng.sat, 'plain'),
			('three', 'LIGHT', (eng.val - 0.12) / 0.88, 'plain'),
		]
		bar_x, bar_w = x0 + 62, 190
		for i, (pose, label, frac, kind) in enumerate(rows):
			ry = y0 + 72 + i * 28
			active = self._active_dial == pose
			cv.create_text(
				x0, ry + 2, anchor='nw', text=label,
				fill='#ffffff' if active else '#777788', font=('Segoe UI', 9, 'bold'), tags='hud',
			)
			if kind == 'hue':
				segs = 24
				for s in range(segs):
					cv.create_rectangle(
						bar_x + s * bar_w / segs, ry, bar_x + (s + 1) * bar_w / segs, ry + 14,
						fill=hsv_hex(s / segs, 0.85, 0.95), outline='', tags='hud',
					)
			else:
				cv.create_rectangle(bar_x, ry, bar_x + bar_w, ry + 14, fill='#2a2a36', outline='', tags='hud')
				cv.create_rectangle(
					bar_x, ry, bar_x + bar_w * frac, ry + 14,
					fill='#e0e0ee' if active else '#7a7a90', outline='', tags='hud',
				)
			mx = bar_x + bar_w * frac
			cv.create_rectangle(
				mx - 2, ry - 3, mx + 2, ry + 17, fill='#ffffff', outline='#000000', tags='hud',
			)

		hint = {
			'one': 'moving up / down changes hue',
			'two': 'moving up / down changes size',
			'three': 'up/down = saturation   left/right = brightness',
			'four': 'left/right = brush style   up/down = symmetry',
		}.get(self._active_dial, 'left hand: 1 finger hue | 2 size | 3 tone | 4 brush')
		cv.create_text(x0, y0 + 190, anchor='nw', text=hint, fill='#9a9ab0', font=('Segoe UI', 9), tags='hud')

		# Footer hint.
		cv.create_text(
			self.W / 2, self.H - 18, fill='#555566', font=('Segoe UI', 10),
			text='pinch thumb + index to paint  |  thumb + ring to erase  |  left thumb held = undo  |  shaka = pause',
			tags='hud',
		)

		if not hands and now - self._last_hands_time > 1.0 and not self._paused:
			self.window.draw_banner('Show your hands to the camera', y=self.H * 0.45, color='#666677')

		if self._paused:
			self.window.draw_banner('Paused')

		if self._toast is not None:
			text, until = self._toast
			if now > until:
				self._toast = None
			else:
				cv.create_text(
					self.W / 2, self.H - 52, text=text, fill='#e8e8f4',
					font=('Segoe UI', 13, 'bold'), tags='hud',
				)

	# --- lifecycle ---------------------------------------------------------------

	def apply_settings(self, settings):
		pass

	def close(self):
		self.release()
		self.window.close()
