import math
import unittest

import numpy as np

import lightfield as lf
from tests import handmodel as hm


def field(**kw):
	return lf.LightField(320, 180, ambient=kw.pop('ambient', 600), ink=kw.pop('ink', 800), seed=kw.pop('seed', 1), **kw)


def run(f, frames, dt=1 / 30, render=True):
	for _ in range(frames):
		f.step(dt)
		if render:
			f.render()


class MotionTests(unittest.TestCase):
	def test_ambient_field_is_alive_and_stays_in_bounds(self):
		f = field()
		before = f.pos.copy()
		run(f, 60)
		self.assertGreater(float(np.abs(f.pos - before).mean()), 1.0, 'motes should drift on their own')
		self.assertTrue(((f.pos[:, 0] >= 0) & (f.pos[:, 0] < f.w) & (f.pos[:, 1] >= 0) & (f.pos[:, 1] < f.h)).all())

	def test_flow_is_divergence_free(self):
		# the stream-function construction must never create sources or sinks
		f = field(ambient=2000)
		eps = 0.5
		def vel_at(x, y):
			f.pos[:, 0], f.pos[:, 1] = x, y
			u, v = f._flow()
			return float(u[0]), float(v[0])
		for x, y in ((50.0, 40.0), (200.0, 120.0), (300.0, 20.0)):
			dudx = (vel_at(x + eps, y)[0] - vel_at(x - eps, y)[0]) / (2 * eps)
			dvdy = (vel_at(x, y + eps)[1] - vel_at(x, y - eps)[1]) / (2 * eps)
			self.assertAlmostEqual(dudx + dvdy, 0.0, delta=0.02)

	def test_attractor_gathers_motes(self):
		f = field()
		run(f, 10, render=False)
		cx, cy = f.w / 2, f.h / 2
		before = f.mean_distance(cx, cy)
		for _ in range(40):
			f.attractors.append((cx, cy, 1.0, 100.0))
			f.step(1 / 30)
		self.assertLess(f.mean_distance(cx, cy), before * 0.7)

	def test_burst_pushes_outward_and_adds_ink(self):
		f = field()
		run(f, 10, render=False)
		cx, cy = f.w / 2, f.h / 2
		ink0 = f.ink_alive()
		f.burst(cx, cy, 1.0)
		self.assertGreater(f.ink_alive(), ink0 + 100)
		near_before = f.mean_distance(cx, cy)
		run(f, 12, render=False)
		self.assertGreater(f.mean_distance(cx, cy), near_before, 'ambient motes near the centre are shoved outward')
		run(f, 60, render=False)
		self.assertEqual(len(f.shocks), 0, 'shockwaves expire')

	def test_shock_list_is_capped(self):
		f = field()
		for _ in range(30):
			f.burst(10, 10, 0.5)
		self.assertLessEqual(len(f.shocks), 6)

	def test_time_stop(self):
		f = field()
		f.set_timescale(0.0)
		before = f.pos.copy()
		run(f, 20, render=False)
		self.assertTrue(np.array_equal(before, f.pos), 'with time stopped nothing moves')
		f.set_timescale(1.0)
		run(f, 20, render=False)
		self.assertFalse(np.array_equal(before, f.pos))

	def test_ink_fades_out_by_itself(self):
		f = field()
		f.emit_ink(50, 50, 120, 60, 200, life=1.0)
		self.assertGreaterEqual(f.ink_alive(), 150)
		run(f, 60, render=False)
		self.assertEqual(f.ink_alive(), 0)

	def test_ink_ring_buffer_overwrites_oldest(self):
		f = field(ink=300)
		for _ in range(5):
			f.emit_ink(10, 10, 20, 20, 200)
		self.assertLessEqual(f.ink_alive(), 300)


class RenderTests(unittest.TestCase):
	def test_render_shape_and_light(self):
		f = field()
		run(f, 5, render=False)
		img = f.render()
		self.assertEqual(img.size, (320, 180))
		self.assertGreater(int(np.asarray(img).sum()), 0)

	def test_ink_is_brighter_than_the_ambient_field(self):
		f = field()
		run(f, 20)
		patch = (slice(80, 100), slice(100, 220))               # where the ink will go
		base = np.asarray(f.render()).astype(int)[patch].sum()
		f.emit_ink(100, 90, 220, 90, 400)
		f.step(1 / 30)
		self.assertGreater(np.asarray(f.render()).astype(int)[patch].sum(), base * 2.0)

	def test_trails_fade_by_the_half_life(self):
		f = field(ambient=0, ink=10)
		f.halflife = 0.5
		f.fb[:] = 1.0
		f.step(0.05)
		f._acc_dt = 0.5                 # half a second has passed since the last render
		f.render()
		self.assertAlmostEqual(float(f.fb[0, 0, 0]), 0.5, delta=0.02)

	def test_skipped_renders_still_decay_by_elapsed_time(self):
		a, b = field(ambient=0, ink=10, seed=2), field(ambient=0, ink=10, seed=2)
		for f in (a, b):
			f.halflife = 0.5
			f.fb[:] = 1.0
		for _ in range(10):
			a.step(0.05)
			a.render()                  # rendered every frame
			b.step(0.05)                # ...vs rendered once at the end
		b.render()
		# 10 steps of 0.05s = 0.5s = exactly one half-life: both must have halved, however often they rendered
		self.assertAlmostEqual(float(a.fb[0, 0, 0]), 0.5, delta=0.03)
		self.assertAlmostEqual(float(b.fb[0, 0, 0]), 0.5, delta=0.03)

	def test_exposure_dims_the_picture(self):
		bright, dim = field(seed=4), field(seed=4)
		dim.exposure = 0.3
		for f in (bright, dim):
			run(f, 20)
		self.assertLess(np.asarray(dim.render()).astype(int).sum(), np.asarray(bright.render()).astype(int).sum() * 0.7)

	def test_ambient_palette_band(self):
		f = field()
		f.set_ambient_pal(0.6, 0.05)
		self.assertTrue(((f.pal[:f.n_amb] > 0.54) & (f.pal[:f.n_amb] < 0.66)).all())

	def test_palettes_are_closed_loops(self):
		for name, table in lf.PALETTES:
			self.assertEqual(table.shape, (256, 3), name)
			self.assertLess(float(np.abs(table[0] - table[-1]).max()), 0.15, f'{name} should wrap smoothly')

	def test_palette_switching_and_knobs_clamp(self):
		f = field()
		for _ in range(len(lf.PALETTES)):
			f.next_palette()
		self.assertEqual(f.palette, 0)
		f.adjust_glow(50)
		self.assertEqual(f.glow, 3.5)
		f.adjust_glow(-50)
		self.assertEqual(f.glow, 0.5)
		f.adjust_swirl(99)
		self.assertEqual(f.swirl, 3.0)
		f.adjust_swirl(-99)
		self.assertEqual(f.swirl, 0.0)
		f.adjust_halflife(50)
		self.assertEqual(f.halflife, 5.0)
		f.adjust_hue(1.25)
		self.assertAlmostEqual(f.hue, 0.25)

	def test_reset_clears_ink_and_light(self):
		f = field()
		f.emit_ink(10, 10, 100, 100, 300)
		run(f, 3)
		f.reset()
		self.assertEqual(f.ink_alive(), 0)
		self.assertEqual(float(f.fb.max()), 0.0)

	def test_snapshot_upscales(self):
		f = field()
		run(f, 3)
		self.assertEqual(f.snapshot((640, 360)).size, (640, 360))

	def test_hand_skeleton_light(self):
		hand = hm.make_hand(out=hm.OPEN)
		xs, ys, ints = lf.skeleton_points(hand, lambda x, y: (x / 2, y / 2))
		self.assertEqual(len(xs), len(ys))
		self.assertEqual(len(xs), 21 * 9 + 21)
		self.assertAlmostEqual(float(ints.max()), 1.0)          # fingertips brightest
		f = field()
		f.draw_points(xs / 2, ys / 2, ints, 0.3)
		f.render()
		self.assertGreater(float(f.fb.max()), 0.4)


if __name__ == '__main__':
	unittest.main()
