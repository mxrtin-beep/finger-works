"""Paint mode: paint with living light.

A calm swarm of soft orbs drifts through an invisible flow (lightswarm.py)
-- alive and pretty with nobody in front of it. Your hands act on it.

RIGHT hand -- the conductor. The point is where your *middle finger*
points (exactly like the cursor in Control mode).

    pinch thumb + index        ignite: a ribbon of light follows the pen
                               (and throws off sparks)
    clench your fist           gather: the orbs are drawn into orbit
                               around your fingertip
    snap the fist open         burst: a ring of light shoves them outward
    move your hand             stirs the swarm; every fingertip sheds sparks

LEFT hand -- the atmosphere. Hold a pose, then *tilt your hand* like a
joystick: lean right to keep raising a value, lean left to keep lowering
it, straighten up to hold it. (No range limit, and a small wrist movement
is all it takes.)

    1 finger                   colour (rotates through the palette)
    2 fingers                  glow (small crisp orbs <-> big soft ones)
    3 fingers                  flow (calm <-> turbulent)
    4 fingers / open hand      trail (short ribbon <-> long ribbon)
    fist, held                 stop time (release to resume)
    thumb alone, held          next palette

Leave it alone for a few seconds and a ghost painter takes over, so it's
never a blank screen.

Everything is drawn as crisp vector shapes from a fixed pool of canvas items
that are only *moved* each frame (never created/destroyed), which is what
keeps it smooth: a couple of hundred shapes, sharp at any resolution.
"""

import datetime
import math
import os
import time

import art_gestures as ag
import constants as c
from lightswarm import LightSwarm

RIBBON_SEGMENTS = 110


class PaintSession:
	mode = 'paint'

	# Tilt-joystick speeds (per second at full tilt)
	HUE_RATE = 0.45
	GLOW_RATE = 1.1
	SWIRL_RATE = 1.4
	TRAIL_RATE = 1.2

	IDLE_SECONDS = 4.0        # no hands this long -> the ghost painter appears

	def __init__(self, overlay, settings=None, engine=None):
		"""`engine` resumes an earlier LightSwarm (see main_fast.start_mode,
		which hands the last one back when you return to Paint)."""
		from art_window import ArtWindow

		self.overlay = overlay
		self.window = ArtWindow(overlay, bg='#0a0c1e')
		self.canvas = self.window.canvas
		self.W, self.H = self.window.width, self.window.height

		if engine is not None and (engine.w, engine.h) != (self.W, self.H):
			engine = None
		self.engine = engine or LightSwarm(self.W, self.H)
		self._build_items()

		self.pointer = ag.Pointer2D(min_cutoff=1.8, beta=0.015)
		self.pinch = ag.Pinch(c.LEFT_CLICK_CUTOFF)
		self.openness = ag.OpennessTracker()
		self.left_pose = ag.PoseTracker(frames=3)
		self.roll_filter = ag.OneEuro(min_cutoff=1.5, beta=0.02)
		self.palette_latch = ag.Latch(0.7)
		self.shaka = ag.ShakaWatch()

		self._aim = None
		self._pen = None              # (x, y, openness, pinching) for drawing the pointer
		self._tips = {}
		self._time_scale = 1.0
		self._last_t = None
		self._last_hands_time = time.time()
		self._start = time.time()
		self._gauge = None            # (label, 0..1, rate, until)
		self._toast = None
		self._paused = False
		self._ghost_prev = None
		self._ghost_burst = -1

	# ---- item pool --------------------------------------------------------------------

	def _build_items(self):
		"""Create every shape once. After this, drawing a frame only moves and
		recolours them -- creating and deleting hundreds of items per frame is
		what makes Tk canvases stutter."""
		cv, f = self.canvas, self.engine
		# static sky: a few bands, navy at the top fading to violet
		bands = 10
		for i in range(bands):
			t = i / (bands - 1)
			col = '#%02x%02x%02x' % (int(9 + 15 * t), int(12 - 2 * t), int(30 + 4 * t))
			cv.create_rectangle(0, self.H * i / bands, self.W, self.H * (i + 1) / bands + 1, fill=col, outline='', tags='sky')

		def oval(**kw):
			return cv.create_oval(-50, -50, -40, -40, outline='', state='hidden', **kw)

		self._amb_halo = [oval() for _ in range(f.n_amb)]          # wide, faint
		self._amb_mid = [oval() for _ in range(f.n_amb)]           # tighter, brighter
		self._amb_core = [oval() for _ in range(f.n_amb)]
		self._rib_glow = [cv.create_line(-9, -9, -8, -8, state='hidden', capstyle='round') for _ in range(RIBBON_SEGMENTS)]
		self._rib_core = [cv.create_line(-9, -9, -8, -8, state='hidden', capstyle='round') for _ in range(RIBBON_SEGMENTS)]
		self._sparks = [oval() for _ in range(f.n_spark)]
		self._rings = [cv.create_oval(-9, -9, -8, -8, fill='', state='hidden') for _ in range(5)]
		self._ptr_halo = oval()
		self._ptr_ring = cv.create_oval(-9, -9, -8, -8, fill='', state='hidden')
		self._ptr_core = oval()

		# what each item currently shows, so unchanged ones aren't touched
		self._shown = {}
		self._fill = {}
		self._width = {}

	def _set(self, item, coords, fill=None, width=None, outline=None):
		"""Show `item` at `coords`, changing colour/width only if they differ."""
		cv = self.canvas
		cv.coords(item, *coords)
		if not self._shown.get(item):
			cv.itemconfigure(item, state='normal')
			self._shown[item] = True
		if fill is not None and self._fill.get(item) != fill:
			cv.itemconfigure(item, fill=fill)
			self._fill[item] = fill
		if outline is not None and self._fill.get(item) != outline:
			cv.itemconfigure(item, outline=outline)
			self._fill[item] = outline
		if width is not None and self._width.get(item) != width:
			cv.itemconfigure(item, width=width)
			self._width[item] = width

	def _hide(self, item):
		if self._shown.get(item):
			self.canvas.itemconfigure(item, state='hidden')
			self._shown[item] = False

	def _draw_swarm(self):
		f = self.engine
		glow, k = f.glow, f.k
		inten = f.intensity()
		x, y = f.pos[:, 0], f.pos[:, 1]
		pal = f.pal

		for i in range(f.n_amb):
			level = inten[i]
			if level < 0.05:
				self._hide(self._amb_halo[i])
				self._hide(self._amb_mid[i])
				self._hide(self._amb_core[i])
				continue
			r = f.size[i] * glow
			xi, yi = x[i], y[i]
			self._set(self._amb_halo[i], (xi - 4.2 * r, yi - 4.2 * r, xi + 4.2 * r, yi + 4.2 * r), fill=f.glow_colour(pal[i], level * 0.16))
			self._set(self._amb_mid[i], (xi - 2.2 * r, yi - 2.2 * r, xi + 2.2 * r, yi + 2.2 * r), fill=f.glow_colour(pal[i], level * 0.34))
			self._set(self._amb_core[i], (xi - r, yi - r, xi + r, yi + r), fill=f.colour(pal[i], level))

		for i in range(f.n_amb, f.n):
			item = self._sparks[i - f.n_amb]
			level = inten[i]
			if level < 0.06:
				self._hide(item)
				continue
			r = f.size[i] * glow
			xi, yi = x[i], y[i]
			self._set(item, (xi - r, yi - r, xi + r, yi + r), fill=f.colour(pal[i], level))

		# the pen's ribbon: newest segment widest and brightest
		pts = f.ribbon_points()[-(RIBBON_SEGMENTS + 1):]
		segs = len(pts) - 1
		for j in range(RIBBON_SEGMENTS):
			if j >= segs:
				self._hide(self._rib_glow[j])
				self._hide(self._rib_core[j])
				continue
			x0, y0, _p0, _f0 = pts[j]
			x1, y1, p1, f1 = pts[j + 1]
			width = max(1, int((2.0 + 8.0 * f1) * glow * k))
			self._set(self._rib_glow[j], (x0, y0, x1, y1), fill=f.glow_colour(p1, f1 * 0.45), width=width * 3 + 2)
			self._set(self._rib_core[j], (x0, y0, x1, y1), fill=f.colour(p1, min(1.0, 0.25 + f1)), width=width)

		# shockwave rings
		for n, ring in enumerate(self._rings):
			if n >= len(f.shocks):
				self._hide(ring)
				continue
			sx, sy, t0, strength, spal = f.shocks[n]
			age = f.t - t0
			fade = max(0.0, 1.0 - age / 1.4)
			radius = 520.0 * k * age
			self._set(ring, (sx - radius, sy - radius, sx + radius, sy + radius), outline=f.colour(spal, min(1.0, fade * strength * 1.5)), width=max(2, int(7 * fade * k + 1)))

		# pointer
		if self._pen is None:
			for item in (self._ptr_halo, self._ptr_ring, self._ptr_core):
				self._hide(item)
		else:
			px, py, o, pinching = self._pen
			pal_head = f.stroke_pal()
			rr = (16.0 + 22.0 * o) * k
			self._set(self._ptr_halo, (px - rr * 2.0, py - rr * 2.0, px + rr * 2.0, py + rr * 2.0), fill=f.glow_colour(pal_head, 0.13))
			self._set(self._ptr_ring, (px - rr, py - rr, px + rr, py + rr), outline=f.colour(pal_head, 0.9), width=3 if pinching else 2)
			core = (5.0 + (3.0 if pinching else 0.0)) * k
			self._set(self._ptr_core, (px - core, py - core, px + core, py + core), fill=f.colour(pal_head, 1.0))

	# ---- control bar ---------------------------------------------------------------

	def actions(self):
		return [('Palette', self.next_palette), ('Reset', self.do_reset), ('Save', self.do_save)]

	def next_palette(self):
		self._flash(self.engine.next_palette())

	def do_reset(self):
		self.engine.reset()
		self._flash('Reset')

	def do_save(self):
		try:
			pictures = os.path.join(os.path.expanduser('~'), 'Pictures')
			base = pictures if os.path.isdir(pictures) else os.path.expanduser('~')
			directory = os.path.join(base, 'FingerWorks')
			os.makedirs(directory, exist_ok=True)
			path = os.path.join(directory, f'light-{datetime.datetime.now():%Y%m%d-%H%M%S}.png')
			self.engine.snapshot((self.W, self.H)).save(path)
			self._flash(f'Saved  {path}', 5.0)
		except OSError as exc:
			self._flash(f'Could not save: {exc}', 5.0)

	def _flash(self, text, seconds=2.2):
		self._toast = (text, time.time() + seconds)

	# ---- lifecycle --------------------------------------------------------------------

	def set_paused(self, paused):
		if paused == self._paused:
			return
		self._paused = paused
		if paused:
			self.release()
		self._last_t = None
		self._redraw_hud([], time.time())

	def release(self):
		self.pointer.reset()
		self.pinch.reset()
		self.openness.reset()
		self.left_pose.reset()
		self.roll_filter.reset()
		self.palette_latch.update(False, 0)
		self._aim = None
		self._pen = None
		self._tips.clear()

	def apply_settings(self, settings):
		pass

	def close(self):
		self.release()
		self.window.close()

	# ---- per frame -----------------------------------------------------------------------

	def update(self, hands, now):
		"""Process one frame. Returns True if the user asked to pause."""
		if self.shaka.update(hands):
			self.release()
			return True

		dt = 1.0 / 30.0 if self._last_t is None else min(max(now - self._last_t, 1e-3), 0.1)
		self._last_t = now
		f = self.engine
		right, left = ag.pick_hands(hands)
		if hands:
			self._last_hands_time = now

		if right is not None:
			self._right(right, now, dt)
		else:
			self.pointer.reset()
			self.pinch.reset()
			self.openness.reset()
			self._aim = None
			self._pen = None
		self._left(left, now, dt)

		for hand in hands:
			self._shed_sparks(hand, dt)

		if now - self._last_hands_time > self.IDLE_SECONDS:
			self._ghost(now, dt)

		f.step(dt)
		self._draw_swarm()
		self._redraw_hud(hands, now)
		return False

	def _right(self, hand, now, dt):
		f = self.engine
		mx, my = hand.point(c.MIDDLE_IDX)
		x, y = ag.frame_to_screen(mx, my, hand.frame_w, hand.frame_h, self.W, self.H)
		x, y = self.pointer(x, y, now)
		prev = self._aim
		vx = vy = step = 0.0
		if prev is not None:
			vx, vy = (x - prev[0]) / dt, (y - prev[1]) / dt
			step = math.hypot(x - prev[0], y - prev[1])
		self._aim = (x, y)

		pinching = self.pinch.update(hand.pinch_dist(c.INDEX_IDX))
		burst = self.openness.update(hand.openness(), now)
		o = self.openness.value
		self._pen = (x, y, o, pinching)

		# Clench -> gather. Even an open hand has a faint pull, so orbs
		# always lazily orbit the fingertip.
		pull = (1.0 - o) ** 2
		f.attractors.append((x, y, 0.10 + 0.90 * pull, f.k * (190.0 + 170.0 * pull)))
		f.stirs.append((x, y, vx * 0.6, vy * 0.6))

		if burst > 0.0:
			f.burst(x, y, burst, pal=f.stroke_pal())

		if pinching:
			f.add_ribbon_point(x, y, f.stroke_pal(step * 0.0009))
			f.emit_sparks(x, y, vx, vy, min(4, 1 + int(step / 25.0)), f.stroke_pal(), life=1.2, bright=0.9)

	def _shed_sparks(self, hand, dt):
		"""Every fingertip throws off sparks when it moves fast."""
		f = self.engine
		base = 0.12 if hand.label == 'Right' else 0.62
		for tip in (c.THUMB_IDX, c.INDEX_IDX, c.MIDDLE_IDX, c.RING_IDX, c.PINKY_IDX):
			x, y = ag.frame_to_screen(*hand.point(tip), hand.frame_w, hand.frame_h, self.W, self.H)
			key = (hand.label, tip)
			prev = self._tips.get(key)
			self._tips[key] = (x, y)
			if prev is None:
				continue
			vx, vy = (x - prev[0]) / dt, (y - prev[1]) / dt
			speed = math.hypot(vx, vy)
			if speed > 380.0 * f.k:
				f.emit_sparks(x, y, vx * 0.5, vy * 0.5, 1, base + tip * 0.012, life=0.9, bright=0.7, spread=30.0)

	def _left(self, hand, now, dt):
		f = self.engine
		if hand is None:
			self.left_pose.reset()
			self.roll_filter.reset()
			self.palette_latch.update(False, now)
			self._ease_time(1.0, dt)
			return

		pose = self.left_pose.update(ag.left_pose(hand.fingers_out), now)
		rate = ag.tilt_rate(self.roll_filter(hand.roll_degrees(), now))

		label = value = None
		if pose == 'one':
			f.adjust_hue(rate * self.HUE_RATE * dt)
			label, value = 'COLOUR', f.hue
		elif pose == 'two':
			f.adjust_glow(rate * self.GLOW_RATE * dt)
			label, value = 'GLOW', (math.log(f.glow) - math.log(0.5)) / (math.log(3.5) - math.log(0.5))
		elif pose == 'three':
			f.adjust_swirl(rate * self.SWIRL_RATE * dt)
			label, value = 'FLOW', f.swirl / 3.0
		elif pose == 'four':
			f.adjust_trail(rate * self.TRAIL_RATE * dt)
			label, value = 'TRAIL', (math.log(f.trail) - math.log(0.15)) / (math.log(5.0) - math.log(0.15))
		if label is not None and abs(rate) > 0.02:
			self._gauge = (label, value, rate, now + 1.4)

		self._ease_time(0.03 if pose == 'fist' else 1.0, dt)

		if self.palette_latch.update(pose == 'thumb', now):
			self.next_palette()

	def _ease_time(self, target, dt):
		self._time_scale += (target - self._time_scale) * min(1.0, 5.0 * dt)
		self.engine.set_timescale(self._time_scale)

	def _ghost(self, now, dt):
		"""The idle ghost painter: a slow Lissajous wisp that paints a
		ribbon, plus an occasional soft burst."""
		f = self.engine
		t = now - self._start
		x = (0.5 + 0.31 * math.sin(0.31 * t) + 0.09 * math.sin(0.93 * t)) * f.w
		y = (0.5 + 0.27 * math.sin(0.43 * t + 1.0) + 0.08 * math.cos(1.13 * t)) * f.h
		prev = self._ghost_prev or (x, y)
		self._ghost_prev = (x, y)
		vx, vy = (x - prev[0]) / dt, (y - prev[1]) / dt
		f.attractors.append((x, y, 0.2, f.k * 220.0))
		f.stirs.append((x, y, vx * 0.5, vy * 0.5))
		if math.sin(0.19 * t) > -0.35:
			f.add_ribbon_point(x, y, f.stroke_pal(0.0015))
			f.emit_sparks(x, y, vx, vy, 1, f.stroke_pal(), life=1.2, bright=0.8)
		cycle = int(t / 9.0)
		if cycle != self._ghost_burst and t % 9.0 > 8.0:
			self._ghost_burst = cycle
			f.burst(x, y, 0.55, f.stroke_pal())

	# ---- HUD ---------------------------------------------------------------------------------

	def _redraw_hud(self, hands, now):
		cv = self.canvas
		cv.delete('hud')
		self.window.draw_ghost_hands(hands, right_color='#4f86b0', left_color='#b04f96')
		if self.overlay.debug:
			self.window.draw_debug(hands)

		if self._gauge is not None:
			label, value, rate, until = self._gauge
			if now > until:
				self._gauge = None
			else:
				x, y, w = self.W / 2 - 130, self.H * 0.17, 260
				cv.create_text(self.W / 2, y - 16, text=label, fill='#dfe6ff', font=('Segoe UI', 12, 'bold'), tags='hud')
				cv.create_rectangle(x, y, x + w, y + 6, fill='#1c2030', outline='', tags='hud')
				cv.create_rectangle(x, y, x + w * min(max(value, 0.0), 1.0), y + 6, fill='#cfd8ff', outline='', tags='hud')
				cv.create_text(
					x - 18 if rate < 0 else x + w + 18, y + 3, text='◀' if rate < 0 else '▶',
					fill='#ffffff', font=('Segoe UI', 12), tags='hud',
				)

		idle = now - self._last_hands_time > 1.0
		if idle and not self._paused:
			cv.create_text(
				self.W / 2, self.H * 0.5, text='raise your hands', fill='#7d86a8',
				font=('Segoe UI', 13), tags='hud',
			)
		elif now - self._start < 30.0 or not hands:
			cv.create_text(
				self.W / 2, 22, fill='#4d5575', font=('Segoe UI', 10), tags='hud',
				text='pinch to ignite   |   clench to gather, snap open to burst   |   left hand: tilt to tune   |   fist stops time   |   shaka = pause',
			)

		if self._paused:
			self.window.draw_banner('Paused')
		if self._toast is not None:
			text, until = self._toast
			if now > until:
				self._toast = None
			else:
				cv.create_text(
					self.W / 2, self.H * 0.08, text=text, fill='#f2f4ff',
					font=('Segoe UI', 20, 'bold'), tags='hud',
				)
