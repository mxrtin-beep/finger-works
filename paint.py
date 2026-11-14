"""Paint mode: paint with living light.

The screen is a field of luminous motes drifting in an invisible flow
(see lightfield.py) -- alive and beautiful with nobody in front of it. Your
hands act on it.

RIGHT hand -- the conductor. The point is where your *middle finger*
points (exactly like the cursor in Control mode).

    pinch thumb + index        ignite: pour light along the path
    clench your fist           gather: nearby light is drawn into orbit and
                               condenses into a blazing core
    snap the fist open         burst: a shockwave of light rings outward
    move your hand             stirs the field; every fingertip sheds sparks

LEFT hand -- the atmosphere. Hold a pose, then *tilt your hand* like a
joystick: lean right to keep raising a value, lean left to keep lowering
it, straighten up to hold it. (No range limit -- it can go as far as you
like -- and a small wrist movement is all it takes.)

    1 finger                   colour (rotates through the palette)
    2 fingers                  glow (thin sparks <-> fat halos)
    3 fingers                  flow (calm <-> turbulent)
    4 fingers / open hand      trails (short sparks <-> long exposure)
    fist, held                 stop time (release to resume)
    thumb alone, held          next palette

Leave it alone for a few seconds and a ghost painter takes over, so it's
never a blank screen.
"""

import datetime
import math
import os
import time

from PIL import Image

import art_gestures as ag
import constants as c
from lightfield import LightField, skeleton_points


class PaintSession:
	mode = 'paint'

	# Tilt-joystick speeds (per second at full tilt)
	HUE_RATE = 0.45
	GLOW_RATE = 1.1
	SWIRL_RATE = 1.4
	TRAIL_RATE = 1.2

	IDLE_SECONDS = 4.0        # no hands this long -> the ghost painter appears

	def __init__(self, overlay, settings=None, engine=None):
		"""`engine` resumes an earlier LightField (see main_fast.start_mode,
		which hands the last one back when you return to Paint)."""
		import tkinter as tk
		from PIL import ImageTk
		from art_window import ArtWindow

		self.overlay = overlay
		self.window = ArtWindow(overlay, bg='#000000')
		self.canvas = self.window.canvas
		self.W, self.H = self.window.width, self.window.height

		# The field is simulated and rendered at roughly 1000px wide, then
		# scaled up by an integer factor inside Tk (a fast C copy), which
		# is far cheaper than shipping full-resolution frames. The glow
		# hides the pixel doubling.
		self.zoom = max(1, math.ceil(self.W / 1000))
		iw, ih = math.ceil(self.W / self.zoom), math.ceil(self.H / self.zoom)
		if engine is not None and (engine.w, engine.h) != (iw, ih):
			engine = None
		self.engine = engine or LightField(iw, ih)

		self._photo = ImageTk.PhotoImage(Image.new('RGB', (iw, ih)))
		self._big = (
			tk.PhotoImage(master=self.canvas, width=iw * self.zoom, height=ih * self.zoom)
			if self.zoom > 1 else None
		)
		self._bg_item = self.canvas.create_image(0, 0, anchor='nw', image=self._big or self._photo, tags='bg')

		# Presentation tiers, best first (see _maybe_render): 'smooth' = a
		# real interpolated upscale to the full screen size; 'fast' = Tk's
		# blocky integer zoom, about half the cost; and either can also skip
		# every other render. A 960px field shown on a 1080p screen is the
		# case where this matters; at 1:1 there's nothing to smooth.
		self._full = None
		self._smooth = self.zoom > 1
		self._smooth_retry_at = 0.0
		self._smooth_tried_at = 0.0
		self._smooth_penalty = 0.0
		self._applied_smooth = None

		self.pointer = ag.Pointer2D(min_cutoff=1.8, beta=0.015)
		self.pinch = ag.Pinch(c.LEFT_CLICK_CUTOFF)
		self.openness = ag.OpennessTracker()
		self.left_pose = ag.PoseTracker(frames=3)
		self.roll_filter = ag.OneEuro(min_cutoff=1.5, beta=0.02)
		self.palette_latch = ag.Latch(0.7)
		self.shaka = ag.ShakaWatch()

		self._aim = None
		self._tips = {}
		self._time_scale = 1.0
		self._last_t = None
		self._last_hands_time = time.time()
		self._start = time.time()
		self._gauge = None          # (label, 0..1, until)
		self._toast = None
		self._paused = False
		self._ghost_prev = None
		self._ghost_burst = -1

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
		self._left(left, now, dt)

		# Every tracked hand lights the field: skeleton as constellation,
		# fingertips shedding sparks when they move.
		for hand in hands:
			self._light_hand(hand, dt)

		if now - self._last_hands_time > self.IDLE_SECONDS:
			self._ghost(now, dt)

		f.step(dt)
		self._maybe_render()
		self._redraw_hud(hands, now)
		return False

	def _to_field(self, x, y, hand):
		sx, sy = ag.frame_to_screen(x, y, hand.frame_w, hand.frame_h, self.W, self.H)
		return sx / self.zoom, sy / self.zoom

	def _right(self, hand, now, dt):
		f = self.engine
		mx, my = hand.point(c.MIDDLE_IDX)
		sx, sy = ag.frame_to_screen(mx, my, hand.frame_w, hand.frame_h, self.W, self.H)
		sx, sy = self.pointer(sx, sy, now)
		x, y = sx / self.zoom, sy / self.zoom
		prev = self._aim
		vx = vy = 0.0
		step = 0.0
		if prev is not None:
			vx, vy = (x - prev[0]) / dt, (y - prev[1]) / dt
			step = math.hypot(x - prev[0], y - prev[1])
		self._aim = (x, y)

		pinching = self.pinch.update(hand.pinch_dist(c.INDEX_IDX))
		burst = self.openness.update(hand.openness(), now)
		o = self.openness.value

		# Clench -> gather. Even an open hand has a faint pull, so motes
		# always lazily orbit the fingertip.
		pull = (1.0 - o) ** 2
		f.attractors.append((x, y, 0.10 + 0.90 * pull, f.k * (190.0 + 170.0 * pull)))
		f.stirs.append((x, y, vx * 0.6, vy * 0.6))

		if burst > 0.0:
			f.burst(x, y, burst, pal=f.stroke_pal())

		if pinching and prev is not None:
			count = int(min(80, 10 + step * 0.55))
			f.emit_ink(
				prev[0], prev[1], x, y, count, vx, vy,
				pal0=f.stroke_pal(), pal1=f.stroke_pal(step * 0.0012),
				bright=0.95, life=5.5, spread=18.0,
			)

	def _light_hand(self, hand, dt):
		f = self.engine
		xs, ys, ints = skeleton_points(hand, lambda x, y: self._to_field(x, y, hand))
		base = 0.12 if hand.label == 'Right' else 0.62
		f.draw_points(xs, ys, ints * 0.9, base)
		for tip in (c.THUMB_IDX, c.INDEX_IDX, c.MIDDLE_IDX, c.RING_IDX, c.PINKY_IDX):
			x, y = self._to_field(*hand.point(tip), hand)
			key = (hand.label, tip)
			prev = self._tips.get(key)
			self._tips[key] = (x, y)
			if prev is None:
				continue
			vx, vy = (x - prev[0]) / dt, (y - prev[1]) / dt
			speed = math.hypot(vx, vy)
			if speed > 200.0 * f.k:
				f.sparks(x, y, vx * 0.5, vy * 0.5, min(3, int(speed / (260.0 * f.k)) + 1), base + tip * 0.012)

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
			f.adjust_halflife(rate * self.TRAIL_RATE * dt)
			label, value = 'TRAILS', (math.log(f.halflife) - math.log(0.08)) / (math.log(5.0) - math.log(0.08))
		if label is not None and abs(rate) > 0.02:
			self._gauge = (label, value, rate, now + 1.4)

		self._ease_time(0.03 if pose == 'fist' else 1.0, dt)

		if self.palette_latch.update(pose == 'thumb', now):
			self.next_palette()

	def _ease_time(self, target, dt):
		self._time_scale += (target - self._time_scale) * min(1.0, 5.0 * dt)
		self.engine.set_timescale(self._time_scale)

	def _ghost(self, now, dt):
		"""The idle ghost painter: a slow Lissajous wisp that paints, plus
		an occasional soft burst, so an unattended screen is still alive."""
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
			f.emit_ink(prev[0], prev[1], x, y, 14, vx, vy, f.stroke_pal(), f.stroke_pal(0.002), bright=0.85, life=4.5)
		cycle = int(t / 9.0)
		if cycle != self._ghost_burst and t % 9.0 > 8.0:
			self._ghost_burst = cycle
			f.burst(x, y, 0.55, f.stroke_pal())

	# ---- drawing ---------------------------------------------------------------------------

	def _maybe_render(self):
		"""Render the field and put it on screen, adapting to how fast this
		machine is so drawing never starves hand tracking:

		  smooth (full-size interpolated upscale, best looking)
		    -> fast (Tk's blocky integer zoom)
		    -> fast, rendering every other frame.

		It steps down when the smoothed cost of a render+present is over
		budget, and cautiously probes back up after things have been cheap
		for a while (backing off if the better tier doesn't hold). The
		simulation steps every frame regardless, and trails/streaks use the
		elapsed time, so skipped renders stay smooth."""
		now = time.perf_counter()
		self._frame_no = getattr(self, '_frame_no', 0) + 1
		if getattr(self, '_skip', False) and self._frame_no % 2:
			return
		self._present(self.engine.render())
		took = time.perf_counter() - now
		if self._frame_no <= 8:
			# Warm-up: the first frames include allocating the full-screen
			# image and are always slow -- not evidence about this machine.
			self._render_cost = 0.012
			return
		cost = self._render_cost = 0.8 * getattr(self, '_render_cost', took) + 0.2 * took
		now = time.perf_counter()

		if self._smooth:
			if cost > 0.034 and self.zoom > 1:
				self._smooth = False                       # too slow: drop to the blocky zoom
				self._smooth_penalty = min(self._smooth_penalty + 20.0, 80.0) if now - self._smooth_tried_at < 6.0 else 0.0
				self._smooth_retry_at = now + 15.0 + self._smooth_penalty
				self._render_cost = cost * 0.5
		elif self.zoom > 1 and now > self._smooth_retry_at and cost < 0.011 and not self._skip:
			self._smooth = True                            # cheap for a while: try smooth again
			self._smooth_tried_at = now
			self._render_cost = 0.03
		self._skip = (not self._smooth or self.zoom == 1) and self._render_cost > 0.018

	def _present(self, image):
		if self._smooth and self.zoom > 1:
			if self._full is None:
				from PIL import ImageTk
				self._full = ImageTk.PhotoImage(Image.new('RGB', (self.W, self.H)))
			self._full.paste(image.resize((self.W, self.H), Image.BILINEAR))
			wanted = self._full
		else:
			self._photo.paste(image)
			if self._big is not None:
				self.canvas.tk.call(str(self._big), 'copy', str(self._photo), '-zoom', self.zoom, self.zoom)
			wanted = self._big or self._photo
		if self._applied_smooth is not (wanted is self._full):
			self.canvas.itemconfig(self._bg_item, image=wanted)
			self._applied_smooth = wanted is self._full

	def quality_label(self):
		"""For the debug readout: which presentation tier is active."""
		if self._smooth and self.zoom > 1:
			return 'smooth'
		return 'fast (skipping)' if getattr(self, '_skip', False) else 'fast'

	def _redraw_hud(self, hands, now):
		cv = self.canvas
		cv.delete('hud')
		if self.overlay.debug:
			self.window.draw_debug(hands)
			cv.create_text(
				16, self.H - 150, anchor='nw', text=f'render: {self.quality_label()}  {1000 * getattr(self, "_render_cost", 0):.0f} ms',
				fill='#7fd17f', font=('Consolas', 11), tags='hud',
			)

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
