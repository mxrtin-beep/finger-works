"""Music mode: play an instrument in the air.

The hands split the job the way a musician's would:

  LEFT hand -- harmony and dynamics
      1 / 2 / 3 / 4 fingers      pick chord I / IV / V / vi  (or i / iv / VI / VII
                                 in a minor scale) -- latched until you change it
      hand height                volume: raise it to swell, drop it to soften
      thumb alone, held          next instrument

  RIGHT hand -- the instrument itself
      Harp       sweep your fingertips across the strings to strum; the strings
                 are tuned to the current chord, so any strum is consonant
      Keys       pinch thumb + index over a key to play it; slide while pinched
                 to glissando; keys in the current chord glow as a guide
      Theremin   hand left/right = pitch (gently magnetised to the scale),
                 hand height = vibrato; make a fist to silence it

Pause is the usual shaka sign. Key and scale come from Settings.
"""

import math
import random
import time
from collections import deque


import art_gestures as ag
import constants as c
import modes
import music_theory as mt
from art_window import ArtWindow, hsv_hex
from synth import AudioEngine, NoteBank, PadVoice, ThereminVoice


BG = (7, 9, 15)

_FINGERTIPS = [c.THUMB_IDX, c.INDEX_IDX, c.MIDDLE_IDX, c.RING_IDX, c.PINKY_IDX]


def _mix(color_a, color_b, t):
	"""Blend two rgb tuples; t=0 -> a, t=1 -> b."""
	t = min(max(t, 0.0), 1.0)
	return tuple(a + (b - a) * t for a, b in zip(color_a, color_b))


def _hex(rgb):
	return '#%02x%02x%02x' % tuple(int(min(max(v, 0), 255)) for v in rgb)


def _pc_color(midi, val=1.0, sat=0.65):
	"""A color per pitch class (C=red ... around the wheel), so the same
	note is the same color on every instrument and in every octave."""
	import colorsys
	r, g, b = colorsys.hsv_to_rgb((int(round(midi)) % 12) / 12.0, sat, val)
	return r * 255, g * 255, b * 255


class _Instrument:
	"""Interface the session drives. All coordinates are screen pixels."""

	name = ''
	footer = ''

	def __init__(self, session):
		self.s = session

	def start(self):
		pass

	def stop(self):
		"""Silence everything held. Called on pause, switch and close."""

	def retune(self):
		"""The chord, key or scale changed."""

	def update(self, right, now):
		pass

	def draw(self, cv, now):
		pass


# =====================================================================
# Harp
# =====================================================================

class Harp(_Instrument):
	name = 'harp'
	footer = 'sweep your fingers across the strings   |   left hand: 1-4 fingers = chord, height = volume'

	STRINGS = 10
	X0, X1 = 0.10, 0.90
	# A compact harp in the top half of the screen, below the header: with
	# the hand mapped generously to the screen, a big harp meant the hand
	# itself brushed strings while moving into position.
	Y0, Y1 = 0.21, 0.50
	COOLDOWN = 0.08          # seconds before the same string can re-trigger
	MIN_SPEED = 170.0        # px/s a fingertip must cross at -- ignores resting jitter
	WINDOW = 4               # frames of history the speed is measured over

	def __init__(self, session):
		super().__init__(session)
		self.notes = []
		self.string_x = []
		self._tips = {}                 # fingertip idx -> (x, y) smoothed
		self._history = {}              # fingertip idx -> deque of recent (x, t)
		self._last_t = None
		self._cooldown = [0.0] * self.STRINGS
		self._amp = [0.0] * self.STRINGS
		self._plucked = [0.0] * self.STRINGS
		self._sparks = []               # [x, y, vx, vy, born, rgb]
		self._rings = []                # [x, y, born, rgb]
		self.retune()

	def retune(self):
		s = self.s
		self.string_x = [
			s.W * (self.X0 + (self.X1 - self.X0) * i / (self.STRINGS - 1)) for i in range(self.STRINGS)
		]
		self.notes = mt.chord_notes(s.chord, self.STRINGS, lowest=45)
		# Render this chord's notes first, then the other three chords' in
		# the same background pass, so a chord change finds its strings
		# already cached and the first strum after it doesn't hitch.
		order = [s.chord_idx] + [i for i in range(len(s.chords)) if i != s.chord_idx]
		warm = []
		for i in order:
			for note in mt.chord_notes(s.chords[i], self.STRINGS, lowest=45):
				if note not in warm:
					warm.append(note)
		s.bank.warm('harp', warm)

	def stop(self):
		self._tips.clear()
		self._history.clear()
		self._last_t = None

	def update(self, right, now):
		s = self.s
		if right is None:
			self.stop()
			return

		self._last_t = now
		top, bottom = s.H * self.Y0, s.H * self.Y1

		# Every fingertip plucks, so a whole-hand sweep is a strum. (The
		# harp is compact and sits in the top half of the screen so the hand
		# doesn't brush strings on its way there; the speed threshold and
		# multi-frame window below ignore a hand that's merely drifting.)
		for tip in _FINGERTIPS:
			x, y = right.point(tip)
			x, y = ag.frame_to_screen(x, y, right.frame_w, right.frame_h, s.W, s.H)
			prev = self._tips.get(tip)
			if prev is not None:
				# Light smoothing: enough to stop hand-tracking jitter
				# from "crossing" a string back and forth while the hand
				# rests on it, not so much that quick strums lag.
				x = prev[0] * 0.35 + x * 0.65
				y = prev[1] * 0.35 + y * 0.65
			self._tips[tip] = (x, y)
			hist = self._history.setdefault(tip, deque(maxlen=self.WINDOW))
			hist.append((x, now))
			if prev is None or len(hist) < 2 or not (top <= y <= bottom):
				continue
			# Speed over the whole window, not just the last frame: hand
			# tracking jitters a pixel or two back and forth every frame,
			# which looks fast frame-to-frame but nets out to nothing over
			# a few frames. A real strum keeps going the same way, so it
			# survives this; resting-hand jitter doesn't.
			span = hist[-1][1] - hist[0][1]
			net = hist[-1][0] - hist[0][0]
			if span <= 0 or abs(net) / span < self.MIN_SPEED:
				continue
			if (x - prev[0]) * net <= 0:
				continue            # this frame is moving against the trend
			speed = abs(net) / span
			for i, sx in enumerate(self.string_x):
				if (prev[0] - sx) * (x - sx) < 0 and now - self._cooldown[i] >= self.COOLDOWN:
					self._pluck(i, speed, x, y, now)

	def _pluck(self, i, speed, x, y, now):
		s = self.s
		self._cooldown[i] = now
		vel = min(max(0.30 + speed / 3200.0, 0.30), 1.0)
		sound = s.bank.get('harp', self.notes[i]) if s.engine.available else None
		if sound is not None:
			s.engine.play(sound, vel * s.volume, pan=(self.string_x[i] / s.W * 2.0 - 1.0) * 0.8)
		self._amp[i] = 5.0 + vel * 26.0
		self._plucked[i] = now
		s.light(self.string_x[i], y, 0.18 + 0.4 * vel, self.notes[i])
		color = _pc_color(self.notes[i], 1.0, 0.55)
		self._rings.append([self.string_x[i], y, now, color])
		for k in range(5):
			ang = -math.pi / 2 + (k - 2) * 0.55
			v = 70 + 120 * vel
			self._sparks.append([self.string_x[i], y, math.cos(ang) * v * 0.6, math.sin(ang) * v, now, color])
		del self._rings[:-24]
		del self._sparks[:-120]

	def draw(self, cv, now):
		s = self.s
		top, bottom = s.H * self.Y0, s.H * self.Y1
		segs = 26
		for i, sx in enumerate(self.string_x):
			base = _pc_color(self.notes[i], 0.5, 0.5)
			age = now - self._plucked[i]
			amp = self._amp[i] * math.exp(-age / 0.85)
			if amp > 0.4:
				bright = _pc_color(self.notes[i], 1.0, 0.45)
				pts = []
				for k in range(segs + 1):
					u = k / segs
					off = amp * math.sin(math.pi * u) * math.cos(2.0 * math.pi * 11.0 * age)
					pts += [sx + off, top + (bottom - top) * u]
				cv.create_line(*pts, fill=_hex(_mix(bright, BG, 0.6)), width=9, smooth=True)
				cv.create_line(*pts, fill=_hex(bright), width=3, smooth=True)
			else:
				cv.create_line(sx, top, sx, bottom, fill=_hex(base), width=2)
			# Anchor beads + note names.
			cv.create_oval(sx - 4, top - 4, sx + 4, top + 4, fill=_hex(base), outline='')
			cv.create_oval(sx - 4, bottom - 4, sx + 4, bottom + 4, fill=_hex(base), outline='')
			cv.create_text(
				sx, bottom + 22, text=mt.note_name(self.notes[i]),
				fill=_hex(_pc_color(self.notes[i], 0.8, 0.4)), font=('Segoe UI', 11, 'bold'),
			)

		self._rings = [r for r in self._rings if now - r[2] < 0.7]
		for x, y, born, color in self._rings:
			age = now - born
			rad = 8 + age * 230
			cv.create_oval(
				x - rad, y - rad, x + rad, y + rad,
				outline=_hex(_mix(color, BG, age / 0.7)), width=2,
			)
		self._sparks = [p for p in self._sparks if now - p[4] < 0.9]
		for x, y, vx, vy, born, color in self._sparks:
			age = now - born
			px = x + vx * age
			py = y + vy * age + 160 * age * age
			rad = 3.0 * (1 - age / 0.9) + 0.5
			cv.create_oval(
				px - rad, py - rad, px + rad, py + rad,
				fill=_hex(_mix(color, BG, age / 0.9)), outline='',
			)

		# Fingertips, so you can see what's about to cross a string.
		for x, y in self._tips.values():
			cv.create_oval(x - 5, y - 5, x + 5, y + 5, outline='#aab4d8', width=1)


# =====================================================================
# Keys
# =====================================================================

class Keys(_Instrument):
	name = 'keys'
	footer = 'pinch thumb + index over a key to play   |   slide while pinched = glissando   |   lit keys belong to the chord'

	X0, X1 = 0.04, 0.96
	Y0, Y1 = 0.34, 0.80

	def __init__(self, session):
		super().__init__(session)
		self.pinch = ag.Pinch(c.LEFT_CLICK_CUTOFF)
		self.pointer = ag.Pointer2D(min_cutoff=1.4, beta=0.01)
		self._playing = None            # (key index, channel)
		self._pressed_at = {}
		self._pos = None
		self.notes = []
		self.retune()

	def retune(self):
		s = self.s
		count = 2 * len(mt.SCALES[s.scale]) + 1
		self.notes = mt.scale_notes(s.key, s.scale, count, lowest=60)
		s.bank.warm('keys', self.notes)

	def _geometry(self):
		s = self.s
		x0, x1 = s.W * self.X0, s.W * self.X1
		return x0, x1, s.H * self.Y0, s.H * self.Y1, (x1 - x0) / len(self.notes)

	def _key_at(self, x, y):
		x0, x1, y0, y1, kw = self._geometry()
		if not (x0 <= x < x1 and y0 <= y <= y1):
			return None
		return int((x - x0) // kw)

	def stop(self):
		self._release()
		self.pinch.reset()
		self.pointer.reset()
		self._pos = None

	def _release(self):
		if self._playing is not None:
			_idx, channel = self._playing
			if channel is not None:
				try:
					channel.fadeout(240)
				except Exception:
					pass
			self._playing = None

	def update(self, right, now):
		s = self.s
		if right is None:
			self.stop()
			return
		px, py = right.pinch_point()
		sx, sy = ag.frame_to_screen(px, py, right.frame_w, right.frame_h, s.W, s.H)
		sx, sy = self.pointer(sx, sy, now)
		self._pos = (sx, sy)

		pinching = self.pinch.update(right.pinch_dist(c.INDEX_IDX))
		hover = self._key_at(sx, sy)
		if not pinching or hover is None:
			self._release()
			return
		if self._playing is not None:
			current = self._playing[0]
			if current == hover:
				return
			# Hysteresis: only glissando to a neighbouring key once the
			# pointer is clearly inside it, not the instant it touches the
			# boundary -- the pen tip wobbles a few pixels as the pinch
			# closes, and that alone shouldn't retrigger a note.
			x0, _x1, _y0, _y1, kw = self._geometry()
			boundary = x0 + (max(current, hover) * kw)
			if abs(sx - boundary) < 0.18 * kw:
				return
		# New key under a held pinch (or the pinch just closed): glissando.
		self._release()
		x0, x1, y0, y1, kw = self._geometry()
		# Strike nearer the front (bottom) of the key = harder, like a real one.
		vel = 0.55 + 0.45 * min(max((sy - y0) / (y1 - y0), 0.0), 1.0)
		channel = None
		if s.engine.available:
			sound = s.bank.get('keys', self.notes[hover])
			channel = s.engine.play(sound, vel * s.volume, pan=((sx / s.W) * 2.0 - 1.0) * 0.7)
		self._playing = (hover, channel)
		self._pressed_at[hover] = now
		s.light(x0 + (hover + 0.5) * kw, y0, 0.2 + 0.4 * vel, self.notes[hover])

	def draw(self, cv, now):
		s = self.s
		x0, x1, y0, y1, kw = self._geometry()
		chord_pcs = {(s.chord['root_pc'] + i) % 12 for i in ((0, 4, 7) if s.chord['quality'] == 'maj' else (0, 3, 7))}
		hover = self._key_at(*self._pos) if self._pos else None
		for i, midi in enumerate(self.notes):
			in_chord = (midi % 12) in chord_pcs
			held = self._playing is not None and self._playing[0] == i
			flash = max(0.0, 1.0 - (now - self._pressed_at.get(i, -9)) / 0.5)
			dim = _pc_color(midi, 0.30 if not in_chord else 0.55, 0.55)
			lit = _pc_color(midi, 1.0, 0.45)
			fill = _mix(dim, lit, 1.0 if held else flash)
			kx = x0 + i * kw
			cv.create_rectangle(
				kx + 2, y0, kx + kw - 2, y1, fill=_hex(fill),
				outline='#ffffff' if (held or (hover == i)) else ('#7a86b8' if in_chord else '#262a3c'),
				width=3 if held else 2,
			)
			cv.create_text(
				kx + kw / 2, y1 - 22, text=mt.note_name(midi),
				fill='#0b0d14' if (held or flash > 0.4) else '#cfd6f0', font=('Segoe UI', 12, 'bold'),
			)
		if self._pos:
			px, py = self._pos
			on = self.pinch.on
			cv.create_oval(px - 14, py - 14, px + 14, py + 14, outline='#ffffff', width=3 if on else 1)
			cv.create_oval(px - 3, py - 3, px + 3, py + 3, fill='#ffffff', outline='')


# =====================================================================
# Theremin
# =====================================================================

class Theremin(_Instrument):
	name = 'theremin'
	footer = 'hand left/right = pitch   |   hand height = vibrato   |   fist = silence   |   left hand height = volume'

	MIDI_LO = 48
	SPAN = 36                # three octaves across the screen
	MAGNET = 0.7             # 0 = fully continuous glide, 1 = fully snapped to the scale

	def __init__(self, session):
		super().__init__(session)
		self.pointer = ag.Pointer2D(min_cutoff=1.2, beta=0.01)
		self._trail = deque(maxlen=34)
		self._pos = None
		self._level = 0.0
		self._sounding = False
		self._last_glow = 0.0

	def start(self):
		self.s.theremin.start()

	def stop(self):
		self.s.theremin.set(amp=0.0)
		self.pointer.reset()
		self._pos = None
		self._sounding = False
		self._trail.clear()

	def update(self, right, now):
		s = self.s
		if right is None:
			self.stop()
			return
		x, y = right.palm_point()
		sx, sy = ag.frame_to_screen(x, y, right.frame_w, right.frame_h, s.W, s.H)
		sx, sy = self.pointer(sx, sy, now)
		self._pos = (sx, sy)

		raw_midi = self.MIDI_LO + (sx / s.W) * self.SPAN
		midi = mt.snap_to_scale(raw_midi, s.key, s.scale, self.MAGNET)
		fist = not any(right.fingers_out[1:])
		self._sounding = not fist
		vibrato = ag.height_to_level(right.palm_point()[1], right.frame_h)
		amp = 0.0 if fist else s.volume
		s.theremin.set(freq=mt.midi_to_freq(midi), amp=amp, vibrato=vibrato)
		self._level = amp
		self._trail.append((sx, sy, now, midi))
		if not fist and now - self._last_glow > 0.07:
			self._last_glow = now
			s.light(sx, sy, 0.12 + 0.2 * amp, midi)

	def draw(self, cv, now):
		s = self.s
		# Scale lines across the field, so the pitch landscape is visible.
		for midi in mt.scale_notes(s.key, s.scale, 80, lowest=self.MIDI_LO):
			if midi > self.MIDI_LO + self.SPAN:
				break
			x = (midi - self.MIDI_LO) / self.SPAN * s.W
			is_root = midi % 12 == mt.key_index(s.key)
			cv.create_line(
				x, s.H * 0.17, x, s.H * 0.82,
				fill=_hex(_pc_color(midi, 0.5 if is_root else 0.28, 0.5)), width=3 if is_root else 1,
			)
			if is_root:
				cv.create_text(x, s.H * 0.85, text=mt.note_name(midi), fill='#8a94b8', font=('Segoe UI', 11, 'bold'))

		pts = list(self._trail)
		for a, b in zip(pts, pts[1:]):
			age = now - b[2]
			fade = min(max(age / 0.8, 0.0), 1.0)
			col = _mix(_pc_color(b[3], 1.0, 0.6), BG, fade)
			cv.create_line(a[0], a[1], b[0], b[1], fill=_hex(col), width=max(1, int(7 * (1 - fade))))

		if self._pos:
			px, py = self._pos
			level = self._level if self._sounding else 0.0
			midi = self.MIDI_LO + (px / s.W) * self.SPAN
			col = _pc_color(mt.snap_to_scale(midi, s.key, s.scale, 1.0), 1.0, 0.6)
			for k, (rad, mix) in enumerate(((46, 0.82), (32, 0.62), (20, 0.3), (10, 0.0))):
				rr = rad * (0.55 + 0.9 * level)
				cv.create_oval(px - rr, py - rr, px + rr, py + rr, fill=_hex(_mix(col, BG, mix)), outline='')
		if not self._sounding:
			cv.create_text(
				s.W / 2, s.H * 0.5, text='open your right hand to play',
				fill='#4a5272', font=('Segoe UI', 20, 'bold'),
			)


_INSTRUMENT_CLASSES = {'harp': Harp, 'keys': Keys, 'theremin': Theremin}


# =====================================================================
# Session
# =====================================================================

class MusicSession:
	mode = 'music'

	def __init__(self, overlay, settings=None, engine=None):
		settings = settings or {}
		self.overlay = overlay
		self.window = ArtWindow(overlay, bg=_hex(BG))
		self.canvas = self.window.canvas
		self.W, self.H = self.window.width, self.window.height

		self.engine = engine or AudioEngine()
		self.bank = NoteBank(self.engine)
		self.theremin = ThereminVoice(self.engine)
		self.pad = PadVoice(self.engine)

		# Backdrop: pure vector drawing (a soft sky gradient, drifting stars,
		# and glow halos that bloom at each note). Crisp at any resolution
		# and cheap -- an earlier version rendered a pixel particle field
		# here, which looked blocky when scaled up and cost real frame time.
		rng = random.Random(7)
		self._stars = [
			(rng.random(), rng.random(), rng.random() * 6.28, 0.004 + 0.01 * rng.random(), 1 + (rng.random() < 0.2))
			for _ in range(70)
		]
		self._halos = []          # [x, y, born, rgb, strength]
		self._last_t = None

		self.key = settings.get('music_key', mt.DEFAULT_KEY)
		self.scale = settings.get('music_scale', mt.DEFAULT_SCALE)
		if self.scale not in mt.SCALES:
			self.scale = mt.DEFAULT_SCALE
		self.chords = mt.chord_set(self.key, self.scale)
		self.chord_idx = 0
		self.volume = 0.8

		self.left_pose = ag.PoseTracker(frames=3)
		self.instrument_latch = ag.Latch(0.8)
		self.shaka = ag.ShakaWatch()

		self._instruments = {}
		self.instrument = None
		self._paused = False
		self._toast = None
		self._last_hands_time = time.time()
		self.set_instrument(modes.normalize_instrument(settings.get('music_instrument')))

	@property
	def chord(self):
		return self.chords[self.chord_idx]

	# --- control bar / mode window hooks ------------------------------------------

	def actions(self):
		return [('Next instrument', self.next_instrument)]

	def instrument_name(self):
		return self.instrument.name if self.instrument else None

	def set_instrument(self, name):
		name = modes.normalize_instrument(name)
		if self.instrument is not None:
			if self.instrument.name == name:
				return
			self.instrument.stop()
		inst = self._instruments.get(name)
		if inst is None:
			inst = self._instruments[name] = _INSTRUMENT_CLASSES[name](self)
		self.instrument = inst
		inst.retune()
		if not self._paused:
			inst.start()
		self._flash(modes.INSTRUMENT_LABELS[name])

	def next_instrument(self):
		ids = modes.INSTRUMENT_IDS
		cur = ids.index(self.instrument.name)
		self.set_instrument(ids[(cur + 1) % len(ids)])

	def apply_settings(self, settings):
		key = settings.get('music_key', self.key)
		scale = settings.get('music_scale', self.scale)
		if scale not in mt.SCALES:
			scale = self.scale
		if (key, scale) == (self.key, self.scale):
			return
		self.key, self.scale = key, scale
		self.chords = mt.chord_set(self.key, self.scale)
		for inst in self._instruments.values():
			inst.retune()
		self.pad.stop()
		self._apply_pad()

	def light(self, sx, sy, strength, midi):
		"""A note was played at screen point (sx, sy): bloom a soft halo of
		the note's colour there (see _draw_backdrop)."""
		self._halos.append([sx, sy, time.time(), _pc_color(midi, 1.0, 0.6), strength])
		del self._halos[:-16]

	def _apply_pad(self):
		chord = self.chord
		self.pad.set_chord(chord['root_pc'], chord['quality'], 0.5 * self.volume)
		self.pad.set_level(0.5 * self.volume)     # left-hand height swells the pad too

	def _flash(self, text, seconds=1.8):
		self._toast = (text, time.time() + seconds)

	# --- per-frame ------------------------------------------------------------------

	def set_paused(self, paused):
		if paused == self._paused:
			return
		self._paused = paused
		if paused:
			self.release()
			self._redraw([], time.time())
		else:
			self.instrument.start()
			self._apply_pad()
			self._last_t = None

	def release(self):
		"""Silence and let go of everything (pause, mode switch, quit)."""
		if self.instrument is not None:
			self.instrument.stop()
		self.pad.stop()
		self.engine.stop_all()
		self.left_pose.reset()
		self.instrument_latch.update(False, 0)

	def update(self, hands, now):
		"""Process one frame. Returns True if the user asked to pause."""
		if self.shaka.update(hands):
			self.release()
			return True

		right, left = ag.pick_hands(hands)
		if hands:
			self._last_hands_time = now
		self._update_left(left, now)
		self.instrument.update(right, now)

		self._apply_pad()

		self._redraw(hands, now)
		return False

	def _update_left(self, left, now):
		if left is None:
			self.left_pose.reset()
			self.instrument_latch.update(False, now)
			return
		pose = self.left_pose.update(ag.left_pose(left.fingers_out), now)
		chord = {'one': 0, 'two': 1, 'three': 2, 'four': 3}.get(pose)
		if chord is not None and chord != self.chord_idx:
			self.chord_idx = chord
			self._flash(self.chord['label'], 1.0)
			for inst in self._instruments.values():
				inst.retune()
			self._apply_pad()
			# a soft pulse of light from the middle of the screen, in the new chord's colour
			self.light(self.W / 2, self.H * 0.62, 0.4, self.chord['root_pc'])

		# Hand height is a fader: up = louder. Floor of 0.25 so a hand held
		# low reads as "quiet", never "broken".
		level = ag.height_to_level(left.palm_point()[1], left.frame_h)
		target = 0.25 + 0.75 * level
		self.volume += (target - self.volume) * 0.3

		if self.instrument_latch.update(pose == 'thumb', now):
			self.next_instrument()

	# --- HUD --------------------------------------------------------------------------

	def _draw_backdrop(self, cv, now):
		W, H = self.W, self.H
		# Sky: a handful of horizontal bands fading navy -> deep violet.
		bands = 10
		for i in range(bands):
			t = i / (bands - 1)
			col = _hex(_mix((9, 12, 30), (24, 10, 34), t))
			cv.create_rectangle(0, H * i / bands, W, H * (i + 1) / bands + 1, fill=col, outline='')
		# Stars drifting slowly, twinkling.
		for x, y, phase, speed, size in self._stars:
			px = ((x + now * speed) % 1.0) * W
			b = 0.35 + 0.35 * math.sin(now * 1.3 + phase)
			col = _hex(_mix((24, 24, 44), (200, 210, 255), b))
			cv.create_oval(px - size, y * H - size, px + size, y * H + size, fill=col, outline='')
		# Glow halos: concentric discs from faint/large to bright/small, so
		# the layers read as a smooth gradient.
		self._halos = [h for h in self._halos if now - h[2] < 1.1]
		layers = 9
		for x, y, born, rgb, strength in self._halos:
			age = (now - born) / 1.1
			alpha = (1.0 - age) ** 1.6
			radius = 30 + age * 170 * (0.6 + strength)
			# Fade toward the sky colour at this height (not plain black),
			# so the halo's edge disappears into the gradient behind it.
			sky = _mix((9, 12, 30), (24, 10, 34), min(max(y / H, 0.0), 1.0))
			for k in range(layers, 0, -1):
				t = k / layers
				glow = alpha * (1.0 - t) ** 1.2 * 0.95
				if glow < 0.05:
					continue        # ~transparent: drawing it would only paint sky over a neighbouring halo
				cv.create_oval(
					x - radius * t, y - radius * t, x + radius * t, y + radius * t,
					fill=_hex(_mix(sky, rgb, glow)), outline='',
				)

	def _redraw(self, hands, now):
		cv = self.canvas
		cv.delete('all')
		self._draw_backdrop(cv, now)
		self.window.draw_ghost_hands(hands, tag='ghost', right_color='#2c4a66', left_color='#66304f')
		self.instrument.draw(cv, now)
		if self.overlay.debug:
			self.window.draw_debug(hands, tag='dbg')

		# Header: instrument, key, chord chips.
		label = modes.INSTRUMENT_LABELS[self.instrument.name]
		cv.create_text(
			28, 22, anchor='nw', fill='#dfe4f6', font=('Segoe UI', 16, 'bold'),
			text=label,
		)
		cv.create_text(
			28, 50, anchor='nw', fill='#7f89ad', font=('Segoe UI', 10),
			text=f'{self.key} {self.scale}',
		)
		for i, chord in enumerate(self.chords):
			x = 28 + i * 74
			active = i == self.chord_idx
			cv.create_rectangle(
				x, 78, x + 66, 118, fill='#e8ecff' if active else '#161a2a',
				outline='#8d99c8' if active else '#2a3048', width=2,
			)
			cv.create_text(
				x + 33, 92, text=chord['label'], fill='#0b0d14' if active else '#9aa4c8',
				font=('Segoe UI', 13, 'bold'),
			)
			cv.create_text(
				x + 33, 109, text=chord['numeral'], fill='#555d7e' if active else '#555d7e',
				font=('Segoe UI', 8),
			)
		# Volume fader.
		cv.create_text(28, 132, anchor='nw', text='VOL', fill='#7f89ad', font=('Segoe UI', 9, 'bold'))
		cv.create_rectangle(62, 134, 62 + 200, 146, fill='#161a2a', outline='')
		cv.create_rectangle(62, 134, 62 + 200 * self.volume, 146, fill='#8d99c8', outline='')

		cv.create_text(
			self.W / 2, self.H - 18, fill='#4d5575', font=('Segoe UI', 10),
			text=self.instrument.footer + '   |   thumb held = next instrument   |   shaka = pause',
		)

		if not self.engine.available:
			self.window.draw_banner(
				'No audio available -- install pygame (pip install pygame) for sound',
				y=self.H * 0.2, color='#e67e22', tag='all',
			)
		if not hands and now - self._last_hands_time > 1.0 and not self._paused:
			self.window.draw_banner('Show your hands to the camera', y=self.H * 0.12, color='#555d7e', tag='all')
		if self._paused:
			self.window.draw_banner('Paused', tag='all')
		if self._toast is not None:
			text, until = self._toast
			if now > until:
				self._toast = None
			else:
				cv.create_text(
					self.W / 2, self.H * 0.07, text=text, fill='#f2f4ff', font=('Segoe UI', 22, 'bold'),
				)

	# --- lifecycle ----------------------------------------------------------------------

	def close(self):
		self.release()
		self.theremin.stop()
		self.window.close()
