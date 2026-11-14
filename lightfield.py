"""LightField: a living field of light, the visual engine behind Paint and
the backdrop of Music.

Thousands of luminous motes drift through an invisible, slowly evolving
flow (a divergence-free "curl" field, so they swirl and eddy like smoke or
plankton rather than clumping). The field is alive on its own; hands
*act on it*:

  * attractors pull motes into orbit -- a clenched fist gathers them into
    a tight, blazing core;
  * shockwaves push them outward in an expanding ring -- the burst when a
    clenched hand snaps open;
  * stirs drag them along with a moving fingertip;
  * ink -- bright, long-lived motes emitted along a path -- is how you
    paint: strokes are light, and they feather into the flow instead of
    sitting still;
  * every frame, drawn light (hand skeletons, rings) is added on top.

Frames accumulate into a float framebuffer that decays by a *half-life*,
so everything leaves long-exposure trails, then a two-scale bloom turns
the bright parts into glow. All numpy + Pillow, no Tk, so it can be
tested headlessly; PaintSession / MusicSession just paste render()'s
image into a window.
"""

import colorsys
import math

import numpy as np
from PIL import Image, ImageChops, ImageFilter


def _lut(stops, n=256):
	"""A cyclic color lookup table (n x 3, 0..1) through (position, rgb) stops."""
	xs = [s[0] for s in stops]
	cols = np.array([s[1] for s in stops], dtype=float)
	t = np.linspace(0.0, 1.0, n, endpoint=False)
	return np.stack([np.interp(t, xs, cols[:, i]) for i in range(3)], axis=1).astype(np.float32)


def _prism_stops():
	return [(i / 6.0, colorsys.hsv_to_rgb(i / 6.0, 0.85, 1.0)) for i in range(7)]


# Each palette is a closed loop (last stop == first) so any value wraps
# smoothly. A mote's palette coordinate + the global hue offset picks its
# color, so the left hand's tilt can rotate the whole piece through a
# palette live.
PALETTES = [
	('Aurora', _lut([(0.0, (0.05, 0.95, 0.55)), (0.33, (0.10, 0.65, 1.00)), (0.66, (0.60, 0.30, 1.00)), (1.0, (0.05, 0.95, 0.55))])),
	('Ember', _lut([(0.0, (1.00, 0.12, 0.05)), (0.33, (1.00, 0.55, 0.08)), (0.66, (1.00, 0.90, 0.45)), (1.0, (1.00, 0.12, 0.05))])),
	('Ocean', _lut([(0.0, (0.02, 0.30, 0.90)), (0.33, (0.10, 0.85, 0.95)), (0.66, (0.75, 0.95, 1.00)), (1.0, (0.02, 0.30, 0.90))])),
	('Nebula', _lut([(0.0, (1.00, 0.20, 0.70)), (0.33, (0.45, 0.20, 1.00)), (0.66, (1.00, 0.65, 0.35)), (1.0, (1.00, 0.20, 0.70))])),
	('Prism', _lut(_prism_stops())),
]
PALETTE_NAMES = [p[0] for p in PALETTES]

_BONES = [
	(0, 1), (1, 2), (2, 3), (3, 4),
	(0, 5), (5, 6), (6, 7), (7, 8),
	(5, 9), (9, 10), (10, 11), (11, 12),
	(9, 13), (13, 14), (14, 15), (15, 16),
	(13, 17), (17, 18), (18, 19), (19, 20),
	(0, 17),
]
_TIPS = [4, 8, 12, 16, 20]


class LightField:
	AMBIENT_LIFE = 1e9

	def __init__(self, width, height, ambient=2200, ink=4000, seed=None):
		self.w, self.h = int(width), int(height)
		self.k = self.w / 960.0                    # px-scale: tuned at 960 wide
		rng = np.random.default_rng(seed)
		self.rng = rng

		n = ambient + ink
		self.n_amb, self.n_ink, self.n = ambient, ink, n
		self.pos = (rng.random((n, 2)) * [self.w, self.h]).astype(np.float32)
		self.vel = np.zeros((n, 2), np.float32)
		self.pal = rng.random(n).astype(np.float32)
		self.bright = np.zeros(n, np.float32)
		self.bright[:ambient] = 0.10 + 0.22 * rng.random(ambient)
		self.life = np.zeros(n, np.float32)
		self.life[:ambient] = self.AMBIENT_LIFE
		self.life_max = np.ones(n, np.float32)
		self.flash = np.zeros(n, np.float32)
		self.phase = (rng.random(n) * 2.0 * math.pi).astype(np.float32)
		is_ambient = np.arange(n) < ambient
		self.relax = np.where(is_ambient, 1.4, 0.45).astype(np.float32)     # how fast velocity follows the flow
		self.att_w = np.where(is_ambient, 1.0, 0.3).astype(np.float32)      # how strongly attractors grab it
		self._ink_head = 0

		# Flow: stream function psi = sum a_i sin(k_i . p + w_i t + phi_i);
		# velocity = (dpsi/dy, -dpsi/dx), which is divergence-free (swirls,
		# never sources/sinks) and costs a few cosines per mote.
		wavelengths = np.array([900.0, 520.0, 300.0, 170.0]) * self.k
		speeds = np.array([30.0, 22.0, 14.0, 8.0]) * self.k
		angles = rng.random(4) * 2.0 * math.pi
		self._kx = (2.0 * math.pi / wavelengths * np.cos(angles)).astype(np.float32)
		self._ky = (2.0 * math.pi / wavelengths * np.sin(angles)).astype(np.float32)
		kmag = 2.0 * math.pi / wavelengths
		self._amp = (speeds / kmag).astype(np.float32)
		self._omega = (rng.uniform(-0.5, 0.5, 4)).astype(np.float32)
		self._phi = (rng.random(4) * 2.0 * math.pi).astype(np.float32)

		# Look / feel -- the knobs the left hand turns.
		self.palette = 0
		self.hue = 0.0            # palette rotation, 0..1 (wraps)
		self.glow = 1.0           # bloom radius/strength + stroke fatness
		self.swirl = 1.0          # how hard the flow stirs
		self.halflife = 0.6       # seconds for a trail to fade to half: short = sparks, long = long exposure
		self.timescale = 1.0      # 1 = normal, ~0 = time stopped

		# Dials for using the field as a quiet backdrop (Music) instead of
		# the star of the show (Paint): overall brightness, how hard a
		# shockwave lights the motes it passes, and how big bursts are.
		self.exposure = 1.0
		self.flash_gain = 1.0
		self.burst_scale = 1.0

		self.t = 0.0
		self._dt = 1.0 / 30.0
		self._acc_dt = 0.0        # simulated time since the last render() (it may run less often than step())
		self._stroke_phase = 0.0

		# Per-frame inputs (cleared after each step/render)
		self.attractors = []      # (x, y, strength 0..1, radius px)
		self.stirs = []           # (x, y, vx, vy)
		self.shocks = []          # [x, y, t0, strength, pal]
		self._points = []         # drawn-light arrays for this frame

		self.fb = np.zeros((self.h, self.w, 3), np.float32)
		self._u8 = np.zeros((self.h, self.w, 3), np.float32)
		self._last_image = None

	# ---- look ------------------------------------------------------------------

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

	def adjust_halflife(self, log_delta):
		self.halflife = min(max(self.halflife * math.exp(log_delta), 0.08), 5.0)

	def set_ambient_pal(self, center, spread):
		"""Confine the always-on ambient motes to a narrow band of the
		palette (default: the whole palette, which in a rainbow palette
		reads as confetti). Ink and bursts keep their own colors."""
		self.pal[:self.n_amb] = ((center + (self.rng.random(self.n_amb) - 0.5) * 2.0 * spread) % 1.0).astype(np.float32)

	def set_timescale(self, value):
		self.timescale = min(max(value, 0.0), 2.0)

	# ---- emitting -----------------------------------------------------------------

	def _alloc_ink(self, count):
		"""Claim `count` ink slots from the ring buffer (oldest overwritten)."""
		count = min(count, self.n_ink)
		idx = (self._ink_head + np.arange(count)) % self.n_ink + self.n_amb
		self._ink_head = (self._ink_head + count) % self.n_ink
		return idx

	def emit_ink(self, x0, y0, x1, y1, count, vx=0.0, vy=0.0, pal0=0.0, pal1=None,
				bright=0.95, life=5.0, spread=22.0):
		"""Spawn `count` bright motes spread along the segment (x0,y0)->(x1,y1)
		-- so a fast stroke is a continuous line, not a row of dots -- each
		carrying some of the stroke's velocity (it keeps drifting the way
		you were moving), plus a little scatter."""
		if count <= 0:
			return
		idx = self._alloc_ink(int(count))
		m = len(idx)
		t = self.rng.random(m).astype(np.float32)
		self.pos[idx, 0] = x0 + (x1 - x0) * t + self.rng.normal(0, 1.2 * self.k, m)
		self.pos[idx, 1] = y0 + (y1 - y0) * t + self.rng.normal(0, 1.2 * self.k, m)
		self.vel[idx, 0] = vx * 0.35 + self.rng.normal(0, spread * self.k, m)
		self.vel[idx, 1] = vy * 0.35 + self.rng.normal(0, spread * self.k, m)
		pal1 = pal0 if pal1 is None else pal1
		self.pal[idx] = (pal0 + (pal1 - pal0) * t) % 1.0
		self.bright[idx] = bright * (0.75 + 0.25 * self.rng.random(m))
		self.life[idx] = life * (0.7 + 0.3 * self.rng.random(m))
		self.life_max[idx] = self.life[idx]
		self.flash[idx] = 0.0

	def sparks(self, x, y, vx, vy, count, pal):
		"""A few short-lived, dimmer motes thrown off a fast-moving point."""
		self.emit_ink(x, y, x, y, count, vx, vy, pal, bright=0.55, life=1.3, spread=45.0)

	def burst(self, x, y, strength=1.0, pal=0.0):
		"""A shockwave from (x, y): an expanding ring that shoves motes
		outward and flashes them, plus a spray of fresh ink thrown from the
		centre. `strength` 0..1."""
		strength = min(max(strength, 0.0), 1.0)
		self.shocks.append([x, y, self.t, strength, pal])
		del self.shocks[:-6]          # a flurry of bursts must not pile up cost
		count = int((70 + 260 * strength) * self.burst_scale)
		idx = self._alloc_ink(count)
		m = len(idx)
		ang = self.rng.random(m) * 2.0 * math.pi
		speed = (140.0 + 460.0 * self.rng.random(m)) * strength * self.k
		self.pos[idx, 0] = x
		self.pos[idx, 1] = y
		self.vel[idx, 0] = np.cos(ang) * speed
		self.vel[idx, 1] = np.sin(ang) * speed
		self.pal[idx] = (pal + self.rng.normal(0, 0.1, m)) % 1.0
		self.bright[idx] = 0.9
		self.life[idx] = 1.8 + 2.0 * self.rng.random(m)
		self.life_max[idx] = self.life[idx]
		self.flash[idx] = 0.0

	def draw_points(self, xs, ys, intensity, pal):
		"""Light drawn for this frame only (hand skeletons, fingertips) --
		it isn't a mote, so it doesn't persist except through the trail
		decay. `intensity` and `pal` may be scalars or arrays."""
		xs = np.asarray(xs, np.float32).ravel()
		ys = np.asarray(ys, np.float32).ravel()
		n = len(xs)
		self._points.append((
			xs, ys,
			np.broadcast_to(np.asarray(intensity, np.float32), (n,)).copy(),
			np.broadcast_to(np.asarray(pal, np.float32), (n,)).copy(),
		))

	def stroke_pal(self, advance=0.0):
		"""A palette coordinate that drifts as a stroke gets longer, so a
		single gesture shades through the palette instead of one flat color."""
		self._stroke_phase = (self._stroke_phase + advance) % 1.0
		return self._stroke_phase

	# ---- simulation ------------------------------------------------------------------

	def _flow(self):
		x, y = self.pos[:, 0], self.pos[:, 1]
		u = np.zeros(self.n, np.float32)
		v = np.zeros(self.n, np.float32)
		for i in range(4):
			c = np.cos(self._kx[i] * x + self._ky[i] * y + self._omega[i] * self.t + self._phi[i])
			u += self._amp[i] * self._ky[i] * c
			v -= self._amp[i] * self._kx[i] * c
		return u, v

	def step(self, dt):
		"""Advance the simulation by `dt` real seconds (scaled by timescale)."""
		dt = min(max(dt, 0.0), 0.05) * self.timescale
		self._dt = dt
		self._acc_dt += dt
		if dt <= 0.0:
			self.attractors.clear()
			self.stirs.clear()
			return
		self.t += dt
		k = self.k

		# Follow the flow
		u, v = self._flow()
		rate = 1.0 - np.exp(-self.relax * dt)
		self.vel[:, 0] += (u * self.swirl - self.vel[:, 0]) * rate
		self.vel[:, 1] += (v * self.swirl - self.vel[:, 1]) * rate

		# Attractors: pull toward the centre, with a sideways component so
		# motes orbit instead of dropping straight in, and extra drag near
		# the centre so a strong pull condenses into a dense glowing core.
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
			drag = np.minimum(0.9, infl * strength * 4.0 * dt)
			self.vel *= (1.0 - drag)[:, None]

		# Stirs: motes near a moving fingertip get dragged along with it.
		for sx, sy, svx, svy in self.stirs:
			dx = self.pos[:, 0] - sx
			dy = self.pos[:, 1] - sy
			infl = np.exp(-(dx * dx + dy * dy) / (2.0 * (110.0 * k) ** 2)) * min(1.0, 7.0 * dt)
			self.vel[:, 0] += (svx - self.vel[:, 0]) * infl
			self.vel[:, 1] += (svy - self.vel[:, 1]) * infl

		# Shockwaves
		alive = []
		for shock in self.shocks:
			sx, sy, t0, strength, pal = shock
			age = self.t - t0
			if age > 1.5:
				continue
			alive.append(shock)
			fade = 1.0 - age / 1.5
			radius = 520.0 * k * age
			width = 55.0 * k * (1.0 + age)
			dx = self.pos[:, 0] - sx
			dy = self.pos[:, 1] - sy
			dist = np.sqrt(dx * dx + dy * dy) + 1e-3
			band = np.exp(-((dist - radius) / width) ** 2) * fade * strength
			push = band * 1800.0 * k * dt / dist
			self.vel[:, 0] += dx * push
			self.vel[:, 1] += dy * push
			self.flash += band * 1.4 * self.flash_gain
			# the visible ring itself
			a = np.linspace(0.0, 2.0 * math.pi, 150, endpoint=False)
			self.draw_points(sx + np.cos(a) * radius, sy + np.sin(a) * radius, 0.55 * fade * strength, pal)
		self.shocks = alive

		# Speed limit, integrate, wrap
		vmax = 1100.0 * k
		speed = np.hypot(self.vel[:, 0], self.vel[:, 1]) + 1e-3
		self.vel *= np.minimum(1.0, vmax / speed)[:, None]
		self.pos += self.vel * dt
		self.pos[:, 0] %= self.w
		self.pos[:, 1] %= self.h

		self.life[self.n_amb:] = np.maximum(self.life[self.n_amb:] - dt, 0.0)
		self.flash *= math.exp(-dt * 4.0)
		self.attractors.clear()
		self.stirs.clear()

	# ---- rendering ----------------------------------------------------------------------

	def _splat(self, xs, ys, weights, colors):
		"""Bilinear-splat weighted colored points into the framebuffer."""
		w, h = self.w, self.h
		x0 = np.floor(xs).astype(np.int32)
		y0 = np.floor(ys).astype(np.int32)
		fx, fy = xs - x0, ys - y0
		idx_parts, wt_parts, col_parts = [], [], []
		for dx, dy, bw in (
			(0, 0, (1 - fx) * (1 - fy)), (1, 0, fx * (1 - fy)),
			(0, 1, (1 - fx) * fy), (1, 1, fx * fy),
		):
			xi, yi = x0 + dx, y0 + dy
			ok = (xi >= 0) & (xi < w) & (yi >= 0) & (yi < h)
			idx_parts.append(yi[ok] * w + xi[ok])
			wt_parts.append((bw * weights)[ok])
			col_parts.append(colors[ok])
		idx = np.concatenate(idx_parts)
		wt = np.concatenate(wt_parts)
		col = np.concatenate(col_parts)
		# One bincount over (pixel, channel) pairs rather than three over
		# pixels: same result, one pass over the big output array.
		packed = (idx[:, None] * 3 + np.arange(3)).ravel()
		out = np.bincount(packed, weights=(col * wt[:, None]).ravel(), minlength=w * h * 3)
		self.fb += out.reshape(h, w, 3)

	def render(self):
		"""Fade the previous frame, add this frame's light, and return the
		bloomed result as an RGB PIL image (self.w x self.h)."""
		lut = PALETTES[self.palette][1]
		# Time since the last render, not the last step: if the caller skips
		# renders to save time, trails still fade and streaks still span the
		# right distance.
		dt = max(self._acc_dt, 1e-3)
		self._acc_dt = 0.0
		self.fb *= 0.5 ** (dt / self.halflife)

		fade = np.minimum(1.0, self.life / (0.35 * self.life_max))
		twinkle = 1.0 + 0.35 * np.sin(self.t * 1.7 + self.phase)
		twinkle[self.n_amb:] = 1.0
		intensity = (self.bright * fade * twinkle + self.flash) * self.exposure
		live = intensity > 0.004

		xs, ys = self.pos[live, 0], self.pos[live, 1]
		inten = intensity[live]
		pal = self.pal[live]
		# Each mote is drawn at its position and half a step back along its
		# velocity: fast ones smear into short streaks instead of dots.
		back = self.vel[live] * (dt * 0.5)
		moving = np.hypot(back[:, 0], back[:, 1]) > 0.6
		x_all = [xs, (xs - back[:, 0])[moving]]
		y_all = [ys, (ys - back[:, 1])[moving]]
		# energy is shared between the two samples only where a second one is drawn
		w_all = [np.where(moving, inten * 0.5, inten), (inten * 0.5)[moving]]
		p_all = [pal, pal[moving]]
		for px, py, pi, pp in self._points:
			x_all.append(px)
			y_all.append(py)
			w_all.append(pi)
			p_all.append(pp)
		self._points = []

		x_all = np.concatenate(x_all)
		y_all = np.concatenate(y_all)
		w_all = np.concatenate(w_all)
		p_all = np.concatenate(p_all)
		colors = lut[(((p_all + self.hue) % 1.0) * 256.0).astype(np.int32) & 255]
		self._splat(x_all, y_all, w_all, colors)

		np.minimum(self.fb, 1.0, out=self._u8)
		self._u8 *= 255.0
		img = Image.fromarray(self._u8.astype(np.uint8), 'RGB')

		# Two-scale bloom: a tight halo and a wide soft one, added back on.
		radius = 1.5 + 2.2 * self.glow
		strength = min(0.45 + 0.35 * self.glow, 1.4)
		# Both blurs and their sum are done at quarter resolution; only the
		# finished glow is scaled up and added, once -- full-resolution
		# resizes/adds were over half the frame time.
		quarter = img.reduce(4)
		near = quarter.filter(ImageFilter.GaussianBlur(radius))
		far = img.reduce(8).filter(ImageFilter.GaussianBlur(radius * 1.1)).resize(quarter.size, Image.BILINEAR)
		glow = ImageChops.add(
			near.point(lambda v: min(255, int(v * strength))),
			far.point(lambda v: min(255, int(v * strength * 0.9))),
		)
		img = ImageChops.add(img, glow.resize(img.size, Image.BILINEAR))
		self._last_image = img
		return img

	def snapshot(self, size=None):
		"""The most recent frame, optionally smoothly upscaled to `size`."""
		img = self._last_image if self._last_image is not None else self.render()
		if size and tuple(size) != img.size:
			img = img.resize(tuple(size), Image.BICUBIC)
		return img

	# ---- housekeeping / introspection -------------------------------------------------------

	def reset(self):
		"""Back to calm: wipe the light and the ink; the ambient motes carry on."""
		self.fb[:] = 0.0
		self.bright[self.n_amb:] = 0.0
		self.life[self.n_amb:] = 0.0
		self.flash[:] = 0.0
		self.shocks.clear()

	def ink_alive(self):
		return int((self.life[self.n_amb:] > 0.05).sum())

	def mean_distance(self, x, y, only_ambient=True):
		sl = slice(0, self.n_amb) if only_ambient else slice(0, self.n)
		d = self.pos[sl] - np.array([x, y], np.float32)
		return float(np.hypot(d[:, 0], d[:, 1]).mean())


def skeleton_points(hand, mapper, samples=9):
	"""Light for one hand: bones as faint lines of points, joints brighter,
	fingertips brightest. `mapper(x, y)` converts a camera-frame point to
	field coordinates. Returns (xs, ys, intensity) arrays."""
	pts = np.array([mapper(p[0], p[1]) for p in hand.abs], np.float32)
	xs, ys, ints = [], [], []
	t = (np.arange(samples) / samples)[:, None]
	for a, b in _BONES:
		seg = pts[a] + (pts[b] - pts[a]) * t
		xs.append(seg[:, 0])
		ys.append(seg[:, 1])
		ints.append(np.full(samples, 0.20, np.float32))
	xs.append(pts[:, 0])
	ys.append(pts[:, 1])
	node = np.full(21, 0.45, np.float32)
	node[_TIPS] = 1.0
	ints.append(node)
	return np.concatenate(xs), np.concatenate(ys), np.concatenate(ints)
