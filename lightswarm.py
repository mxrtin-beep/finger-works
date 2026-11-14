"""LightSwarm: the simulation behind Paint -- a small, calm swarm of light.

A few dozen soft orbs drift through an invisible, slowly changing flow (a
divergence-free "curl" field, so they swirl and eddy instead of clumping).
It's alive on its own, and your hands act on it:

  * attractors pull orbs into orbit -- a clenched fist gathers them around
    the fingertip;
  * shockwaves shove them outward in an expanding ring -- the burst when a
    clenched hand snaps open;
  * stirs drag them along with a moving fingertip;
  * a *ribbon* of light follows the pen, fading out with age, and throws off
    sparks that drift away with the flow.

Deliberately small (a couple of hundred things) and drawn as crisp vector
shapes by PaintSession, rather than as a pixel field: that's what keeps it
smooth and sharp at any resolution. This module is pure numpy -- no Tk, no
Pillow except in snapshot() -- so it can be tested headlessly.
"""

import colorsys
import math
from collections import deque

import numpy as np


def _lut(stops, n=256):
	xs = [s[0] for s in stops]
	cols = np.array([s[1] for s in stops], dtype=float)
	t = np.linspace(0.0, 1.0, n, endpoint=False)
	return np.stack([np.interp(t, xs, cols[:, i]) for i in range(3)], axis=1)


def _prism_stops():
	return [(i / 6.0, colorsys.hsv_to_rgb(i / 6.0, 0.8, 1.0)) for i in range(7)]


# Closed loops, so any palette coordinate wraps smoothly.
PALETTES = [
	('Aurora', _lut([(0.0, (0.05, 0.95, 0.55)), (0.33, (0.10, 0.65, 1.00)), (0.66, (0.60, 0.30, 1.00)), (1.0, (0.05, 0.95, 0.55))])),
	('Ember', _lut([(0.0, (1.00, 0.12, 0.05)), (0.33, (1.00, 0.55, 0.08)), (0.66, (1.00, 0.90, 0.45)), (1.0, (1.00, 0.12, 0.05))])),
	('Ocean', _lut([(0.0, (0.02, 0.30, 0.90)), (0.33, (0.10, 0.85, 0.95)), (0.66, (0.75, 0.95, 1.00)), (1.0, (0.02, 0.30, 0.90))])),
	('Nebula', _lut([(0.0, (1.00, 0.20, 0.70)), (0.33, (0.45, 0.20, 1.00)), (0.66, (1.00, 0.65, 0.35)), (1.0, (1.00, 0.20, 0.70))])),
	('Prism', _lut(_prism_stops())),
]
PALETTE_NAMES = [p[0] for p in PALETTES]

PAL_STEPS = 32        # palette coordinates are quantized to this many colours when drawn
LEVELS = 16           # ...and brightness to this many levels, so colour strings can be precomputed


class LightSwarm:
	def __init__(self, width, height, ambient=80, sparks=170, seed=None):
		self.w, self.h = int(width), int(height)
		self.k = max(0.5, self.w / 1920.0)               # px-scale: tuned at 1920 wide
		rng = np.random.default_rng(seed)
		self.rng = rng

		self.n_amb, self.n_spark = ambient, sparks
		n = ambient + sparks
		self.n = n
		self.pos = (rng.random((n, 2)) * [self.w, self.h])
		self.vel = np.zeros((n, 2))
		self.pal = rng.random(n)
		self.size = np.zeros(n)
		self.size[:ambient] = (2.0 + 4.5 * rng.random(ambient)) * self.k
		self.bright = np.zeros(n)
		self.bright[:ambient] = 0.35 + 0.4 * rng.random(ambient)
		self.life = np.zeros(n)
		self.life[:ambient] = 1e9
		self.life_max = np.ones(n)
		self.flash = np.zeros(n)
		self.phase = rng.random(n) * 2.0 * math.pi
		is_amb = np.arange(n) < ambient
		self.relax = np.where(is_amb, 1.2, 0.5)
		self.att_w = np.where(is_amb, 1.0, 0.35)
		self._spark_head = 0

		# Flow: stream function psi = sum a_i sin(k_i . p + w_i t + phi_i);
		# velocity = (dpsi/dy, -dpsi/dx) is divergence-free.
		wavelengths = np.array([1100.0, 650.0, 380.0]) * self.k
		speeds = np.array([34.0, 22.0, 12.0]) * self.k
		angles = rng.random(3) * 2.0 * math.pi
		kmag = 2.0 * math.pi / wavelengths
		self._kx = kmag * np.cos(angles)
		self._ky = kmag * np.sin(angles)
		self._amp = speeds / kmag
		self._omega = rng.uniform(-0.45, 0.45, 3)
		self._phi = rng.random(3) * 2.0 * math.pi

		# Look / feel -- what the left hand tunes.
		self.palette = 0
		self.hue = 0.0
		self.glow = 1.0           # size of orbs and fatness of the ribbon
		self.swirl = 1.0          # how hard the flow stirs
		self.trail = 1.2          # seconds the pen's ribbon lasts
		self.timescale = 1.0      # 1 = normal, ~0 = time stopped

		self.t = 0.0
		self._stroke_phase = 0.0
		self.ribbon = deque(maxlen=160)     # [x, y, pal, age]
		self.attractors = []                # (x, y, strength 0..1, radius px)
		self.stirs = []                     # (x, y, vx, vy)
		self.shocks = []                    # [x, y, t0, strength, pal]

	# ---- look --------------------------------------------------------------------

	@property
	def palette_name(self):
		return PALETTE_NAMES[self.palette]

	def set_palette(self, index):
		self.palette = index % len(PALETTES)

	def next_palette(self):
		self.set_palette(self.palette + 1)
		return self.palette_name

	def adjust_hue(self, delta):
		self.hue = (self.hue + delta) % 1.0

	def adjust_glow(self, log_delta):
		self.glow = min(max(self.glow * math.exp(log_delta), 0.5), 3.5)

	def adjust_swirl(self, delta):
		self.swirl = min(max(self.swirl + delta, 0.0), 3.0)

	def adjust_trail(self, log_delta):
		self.trail = min(max(self.trail * math.exp(log_delta), 0.15), 5.0)

	def set_timescale(self, value):
		self.timescale = min(max(value, 0.0), 2.0)

	def stroke_pal(self, advance=0.0):
		"""A palette coordinate that drifts as a stroke grows, so one gesture
		shades through the palette instead of staying one flat colour."""
		self._stroke_phase = (self._stroke_phase + advance) % 1.0
		return self._stroke_phase

	# ---- emitting ------------------------------------------------------------------

	def add_ribbon_point(self, x, y, pal):
		self.ribbon.append([x, y, pal, 0.0])

	def emit_sparks(self, x, y, vx, vy, count, pal, life=1.3, bright=0.9, spread=40.0):
		"""Throw off `count` short-lived sparks from (x, y), carrying some of
		the emitter's velocity plus a little scatter. The pool is a ring
		buffer: the oldest sparks are reused first."""
		count = min(int(count), self.n_spark)
		if count <= 0:
			return
		idx = (self._spark_head + np.arange(count)) % self.n_spark + self.n_amb
		self._spark_head = (self._spark_head + count) % self.n_spark
		self.pos[idx, 0] = x + self.rng.normal(0, 2.0 * self.k, count)
		self.pos[idx, 1] = y + self.rng.normal(0, 2.0 * self.k, count)
		self.vel[idx, 0] = vx * 0.3 + self.rng.normal(0, spread * self.k, count)
		self.vel[idx, 1] = vy * 0.3 + self.rng.normal(0, spread * self.k, count)
		self.pal[idx] = (pal + self.rng.normal(0, 0.05, count)) % 1.0
		self.size[idx] = (1.4 + 1.8 * self.rng.random(count)) * self.k
		self.bright[idx] = bright
		self.life[idx] = life * (0.6 + 0.4 * self.rng.random(count))
		self.life_max[idx] = self.life[idx]
		self.flash[idx] = 0.0

	def burst(self, x, y, strength=1.0, pal=0.0):
		"""A shockwave from (x, y): an expanding ring that shoves orbs outward
		and flashes them, plus a spray of sparks. `strength` 0..1."""
		strength = min(max(strength, 0.0), 1.0)
		self.shocks.append([x, y, self.t, strength, pal])
		del self.shocks[:-5]
		count = int(40 + 110 * strength)
		idx = (self._spark_head + np.arange(min(count, self.n_spark))) % self.n_spark + self.n_amb
		self._spark_head = (self._spark_head + len(idx)) % self.n_spark
		m = len(idx)
		ang = self.rng.random(m) * 2.0 * math.pi
		speed = (140.0 + 420.0 * self.rng.random(m)) * strength * self.k
		self.pos[idx, 0], self.pos[idx, 1] = x, y
		self.vel[idx, 0], self.vel[idx, 1] = np.cos(ang) * speed, np.sin(ang) * speed
		self.pal[idx] = (pal + self.rng.normal(0, 0.08, m)) % 1.0
		self.size[idx] = (1.6 + 2.0 * self.rng.random(m)) * self.k
		self.bright[idx] = 0.95
		self.life[idx] = 1.2 + 1.3 * self.rng.random(m)
		self.life_max[idx] = self.life[idx]
		self.flash[idx] = 0.0

	# ---- simulation -------------------------------------------------------------------

	def _flow(self):
		x, y = self.pos[:, 0], self.pos[:, 1]
		u = np.zeros(self.n)
		v = np.zeros(self.n)
		for i in range(3):
			c = np.cos(self._kx[i] * x + self._ky[i] * y + self._omega[i] * self.t + self._phi[i])
			u += self._amp[i] * self._ky[i] * c
			v -= self._amp[i] * self._kx[i] * c
		return u, v

	def step(self, dt):
		"""Advance by `dt` real seconds (scaled by timescale)."""
		dt = min(max(dt, 0.0), 0.05) * self.timescale
		if dt <= 0.0:
			self.attractors.clear()
			self.stirs.clear()
			return
		self.t += dt
		k = self.k

		u, v = self._flow()
		rate = 1.0 - np.exp(-self.relax * dt)
		self.vel[:, 0] += (u * self.swirl - self.vel[:, 0]) * rate
		self.vel[:, 1] += (v * self.swirl - self.vel[:, 1]) * rate

		for ax, ay, strength, radius in self.attractors:
			if strength <= 0.0:
				continue
			dx = ax - self.pos[:, 0]
			dy = ay - self.pos[:, 1]
			r2 = dx * dx + dy * dy
			infl = np.exp(-r2 / (2.0 * radius * radius))
			r = np.sqrt(r2) + radius * 0.18
			g = strength * 1500.0 * k * self.att_w * infl
			self.vel[:, 0] += (dx / r * g + (-dy) / r * g * 0.55) * dt
			self.vel[:, 1] += (dy / r * g + dx / r * g * 0.55) * dt
			self.vel *= (1.0 - np.minimum(0.9, infl * strength * 4.0 * dt))[:, None]

		for sx, sy, svx, svy in self.stirs:
			dx = self.pos[:, 0] - sx
			dy = self.pos[:, 1] - sy
			infl = np.exp(-(dx * dx + dy * dy) / (2.0 * (130.0 * k) ** 2)) * min(1.0, 7.0 * dt)
			self.vel[:, 0] += (svx - self.vel[:, 0]) * infl
			self.vel[:, 1] += (svy - self.vel[:, 1]) * infl

		alive = []
		self.flash *= math.exp(-dt * 4.0)
		for shock in self.shocks:
			sx, sy, t0, strength, pal = shock
			age = self.t - t0
			if age > 1.4:
				continue
			alive.append(shock)
			fade = 1.0 - age / 1.4
			radius = 520.0 * k * age
			width = 60.0 * k * (1.0 + age)
			dx = self.pos[:, 0] - sx
			dy = self.pos[:, 1] - sy
			dist = np.sqrt(dx * dx + dy * dy) + 1e-3
			band = np.exp(-((dist - radius) / width) ** 2) * fade * strength
			push = band * 1800.0 * k * dt / dist
			self.vel[:, 0] += dx * push
			self.vel[:, 1] += dy * push
			self.flash += band * 1.2
		self.shocks = alive

		speed = np.hypot(self.vel[:, 0], self.vel[:, 1]) + 1e-3
		self.vel *= np.minimum(1.0, 1100.0 * k / speed)[:, None]
		self.pos += self.vel * dt
		self.pos[:, 0] %= self.w
		self.pos[:, 1] %= self.h

		self.life[self.n_amb:] = np.maximum(self.life[self.n_amb:] - dt, 0.0)

		# The pen's ribbon ages and drops off the far end.
		limit = self.trail
		for p in self.ribbon:
			p[3] += dt
		while self.ribbon and self.ribbon[0][3] > limit:
			self.ribbon.popleft()

		self.attractors.clear()
		self.stirs.clear()

	# ---- what to draw --------------------------------------------------------------------

	def intensity(self):
		"""Per-orb brightness 0..1 (fade-out, twinkle, shock flash)."""
		fade = np.minimum(1.0, self.life / (0.4 * self.life_max))
		twinkle = np.ones(self.n)
		twinkle[:self.n_amb] = 0.8 + 0.2 * np.sin(self.t * 1.6 + self.phase[:self.n_amb])
		return np.clip(self.bright * fade * twinkle + self.flash, 0.0, 1.0)

	def ribbon_points(self):
		"""Visible ribbon, oldest first: (x, y, pal, freshness 0..1 where 1 is
		brand new and 0 is about to vanish)."""
		span = max(self.trail, 1e-3)
		return [(p[0], p[1], p[2], max(0.0, 1.0 - p[3] / span)) for p in self.ribbon]

	def colour(self, pal, level):
		"""'#rrggbb' for palette coordinate `pal` (plus the hue offset) at
		brightness `level` 0..1. Quantized, so results are cached strings."""
		return _colour_cache(self.palette, int(((pal + self.hue) % 1.0) * PAL_STEPS) % PAL_STEPS,
			min(LEVELS - 1, max(0, int(level * (LEVELS - 1) + 0.5))))

	def glow_colour(self, pal, level):
		"""Like colour(), but *added to* the sky: a halo has to brighten what
		is behind it. A faint plain colour is darker than the lit sky and
		would read as a dark ring."""
		return _glow_cache(self.palette, int(((pal + self.hue) % 1.0) * PAL_STEPS) % PAL_STEPS,
			min(LEVELS - 1, max(0, int(level * (LEVELS - 1) + 0.5))))

	# ---- housekeeping / introspection ---------------------------------------------------------

	def reset(self):
		"""Back to calm: clear the ribbon and sparks; the ambient orbs carry on."""
		self.ribbon.clear()
		self.life[self.n_amb:] = 0.0
		self.flash[:] = 0.0
		self.shocks.clear()

	def sparks_alive(self):
		return int((self.life[self.n_amb:] > 0.05).sum())

	def mean_distance(self, x, y):
		d = self.pos[:self.n_amb] - np.array([x, y])
		return float(np.hypot(d[:, 0], d[:, 1]).mean())

	def snapshot(self, size=None):
		"""A full-resolution PNG-ready picture of the current state, drawn
		with Pillow (one-off, so it can afford supersampled glow)."""
		from PIL import Image, ImageChops, ImageDraw, ImageFilter
		w, h = size or (self.w, self.h)
		sx, sy = w / self.w, h / self.h
		sc = (sx + sy) / 2.0
		sky = Image.new('RGB', (1, 2))
		sky.putpixel((0, 0), (9, 12, 30))
		sky.putpixel((0, 1), (24, 10, 34))
		base = sky.resize((w, h), Image.BILINEAR)
		glow = Image.new('RGB', (w, h), (0, 0, 0))
		core = Image.new('RGB', (w, h), (0, 0, 0))
		gd, cd = ImageDraw.Draw(glow), ImageDraw.Draw(core)

		def rgb(pal, level):
			t = PALETTES[self.palette][1][int(((pal + self.hue) % 1.0) * 256) % 256]
			return tuple(int(c * 255 * level) for c in t)

		inten = self.intensity()
		for i in range(self.n):
			if inten[i] < 0.03:
				continue
			x, y, r = self.pos[i, 0] * sx, self.pos[i, 1] * sy, self.size[i] * self.glow * sc
			if i < self.n_amb:
				gd.ellipse((x - r * 3.2, y - r * 3.2, x + r * 3.2, y + r * 3.2), fill=rgb(self.pal[i], inten[i] * 0.55))
			cd.ellipse((x - r, y - r, x + r, y + r), fill=rgb(self.pal[i], inten[i]))
		pts = self.ribbon_points()
		for (x0, y0, p0, f0), (x1, y1, p1, f1) in zip(pts, pts[1:]):
			wd = (2.0 + 9.0 * f1) * self.glow * self.k * sc
			gd.line((x0 * sx, y0 * sy, x1 * sx, y1 * sy), fill=rgb(p1, f1 * 0.6), width=int(wd * 2.4) + 1)
			cd.line((x0 * sx, y0 * sy, x1 * sx, y1 * sy), fill=rgb(p1, min(1.0, f1 * 1.1)), width=int(wd) + 1)
		glow = glow.filter(ImageFilter.GaussianBlur(max(2.0, 7.0 * sc)))
		return ImageChops.add(ImageChops.add(base, glow), core)


SKY = (15, 11, 32)          # about the middle of the sky gradient PaintSession draws

_COLOUR_CACHE = {}
_GLOW_CACHE = {}


def _glow_cache(palette, pal_q, level_q):
	key = (palette, pal_q, level_q)
	s = _GLOW_CACHE.get(key)
	if s is None:
		rgb = PALETTES[palette][1][int((pal_q + 0.5) / PAL_STEPS * 256) % 256]
		f = level_q / (LEVELS - 1)
		s = _GLOW_CACHE[key] = '#%02x%02x%02x' % tuple(int(min(255, SKY[i] + rgb[i] * 255 * f)) for i in range(3))
	return s


def _colour_cache(palette, pal_q, level_q):
	key = (palette, pal_q, level_q)
	s = _COLOUR_CACHE.get(key)
	if s is None:
		rgb = PALETTES[palette][1][int((pal_q + 0.5) / PAL_STEPS * 256) % 256]
		f = (level_q / (LEVELS - 1)) ** 1.1
		s = _COLOUR_CACHE[key] = '#%02x%02x%02x' % tuple(int(min(255, c * 255 * f)) for c in rgb)
	return s
