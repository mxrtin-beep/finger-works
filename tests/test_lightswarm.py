import unittest

import numpy as np

import lightswarm as ls


def swarm(**kw):
	return ls.LightSwarm(960, 540, ambient=kw.pop('ambient', 60), sparks=kw.pop('sparks', 120), seed=kw.pop('seed', 1), **kw)


def run(s, frames, dt=1 / 30):
	for _ in range(frames):
		s.step(dt)


class MotionTests(unittest.TestCase):
	def test_ambient_orbs_drift_and_stay_in_bounds(self):
		s = swarm()
		before = s.pos.copy()
		run(s, 60)
		self.assertGreater(float(np.abs(s.pos - before).mean()), 1.0)
		self.assertTrue(((s.pos[:, 0] >= 0) & (s.pos[:, 0] < s.w) & (s.pos[:, 1] >= 0) & (s.pos[:, 1] < s.h)).all())

	def test_flow_is_divergence_free(self):
		s = swarm(ambient=4, sparks=4)
		eps = 0.5
		def vel_at(x, y):
			s.pos[:, 0], s.pos[:, 1] = x, y
			u, v = s._flow()
			return float(u[0]), float(v[0])
		for x, y in ((100.0, 80.0), (500.0, 300.0), (800.0, 40.0)):
			dudx = (vel_at(x + eps, y)[0] - vel_at(x - eps, y)[0]) / (2 * eps)
			dvdy = (vel_at(x, y + eps)[1] - vel_at(x, y - eps)[1]) / (2 * eps)
			self.assertAlmostEqual(dudx + dvdy, 0.0, delta=0.02)

	def test_attractor_gathers_orbs(self):
		s = swarm()
		run(s, 10)
		cx, cy = s.w / 2, s.h / 2
		before = s.mean_distance(cx, cy)
		for _ in range(40):
			s.attractors.append((cx, cy, 1.0, 350.0))
			s.step(1 / 30)
		self.assertLess(s.mean_distance(cx, cy), before * 0.7)

	def test_burst_shoves_orbs_outward_and_throws_sparks(self):
		s = swarm()
		run(s, 10)
		cx, cy = s.w / 2, s.h / 2
		self.assertEqual(s.sparks_alive(), 0)
		s.burst(cx, cy, 1.0)
		self.assertGreater(s.sparks_alive(), 60)
		near = s.mean_distance(cx, cy)
		run(s, 12)
		self.assertGreater(s.mean_distance(cx, cy), near)
		run(s, 60)
		self.assertEqual(len(s.shocks), 0, 'shockwaves expire')

	def test_shock_list_is_capped(self):
		s = swarm()
		for _ in range(30):
			s.burst(10, 10, 0.5)
		self.assertLessEqual(len(s.shocks), 5)

	def test_time_stop(self):
		s = swarm()
		s.set_timescale(0.0)
		before, rib = s.pos.copy(), None
		s.add_ribbon_point(10, 10, 0.1)
		run(s, 20)
		self.assertTrue(np.array_equal(before, s.pos))
		self.assertEqual(len(s.ribbon), 1, 'a stopped ribbon does not fade either')
		s.set_timescale(1.0)
		run(s, 20)
		self.assertFalse(np.array_equal(before, s.pos))

	def test_sparks_fade_out_by_themselves(self):
		s = swarm()
		s.emit_sparks(100, 100, 0, 0, 80, 0.3, life=0.8)
		self.assertGreater(s.sparks_alive(), 60)
		run(s, 60)
		self.assertEqual(s.sparks_alive(), 0)

	def test_spark_pool_is_a_ring_buffer(self):
		s = swarm(sparks=50)
		for _ in range(5):
			s.emit_sparks(10, 10, 0, 0, 40, 0.1)
		self.assertLessEqual(s.sparks_alive(), 50)


class RibbonTests(unittest.TestCase):
	def test_ribbon_ages_out_after_the_trail_time(self):
		s = swarm()
		s.trail = 1.0
		for i in range(20):
			s.add_ribbon_point(i * 10.0, 100.0, 0.2)
			s.step(1 / 30)
		self.assertGreater(len(s.ribbon), 10)
		run(s, 45)
		self.assertEqual(len(s.ribbon), 0)

	def test_a_longer_trail_keeps_more_ribbon(self):
		short, long_ = swarm(seed=2), swarm(seed=2)
		short.trail, long_.trail = 0.3, 3.0
		for s in (short, long_):
			for i in range(60):
				s.add_ribbon_point(i * 5.0, 100.0, 0.2)
				s.step(1 / 30)
		self.assertGreater(len(long_.ribbon), len(short.ribbon) * 2)

	def test_ribbon_points_fade_with_age(self):
		s = swarm()
		s.trail = 2.0
		s.add_ribbon_point(0, 0, 0.1)
		run(s, 30)
		s.add_ribbon_point(10, 0, 0.1)
		old, new = s.ribbon_points()
		self.assertLess(old[3], new[3])
		self.assertAlmostEqual(new[3], 1.0)


class PaintSoundTests(unittest.TestCase):
	def test_every_palette_has_a_mood(self):
		import paint
		self.assertEqual(len(paint.PALETTE_MOODS), len(ls.PALETTES))
		for root, quality in paint.PALETTE_MOODS:
			self.assertTrue(0 <= root < 12 and quality in ('maj', 'min'))
		self.assertEqual(len(set(paint.PALETTE_MOODS)), len(paint.PALETTE_MOODS), 'moods should be distinguishable')


class LookTests(unittest.TestCase):
	def test_intensity_is_bounded_and_ambient_is_visible(self):
		s = swarm()
		run(s, 5)
		inten = s.intensity()
		self.assertTrue(((inten >= 0) & (inten <= 1)).all())
		self.assertGreater(float(inten[:s.n_amb].min()), 0.1)
		self.assertEqual(float(inten[s.n_amb:].max()), 0.0, 'no sparks until something throws them')

	def test_palettes_are_closed_loops(self):
		for name, table in ls.PALETTES:
			self.assertEqual(table.shape, (256, 3), name)
			self.assertLess(float(np.abs(table[0] - table[-1]).max()), 0.15, f'{name} should wrap smoothly')

	def test_colours_are_valid_and_cached(self):
		s = swarm()
		for pal in (0.0, 0.37, 0.99):
			for level in (0.0, 0.5, 1.0):
				for fn in (s.colour, s.glow_colour):
					c = fn(pal, level)
					self.assertRegex(c, r'^#[0-9a-f]{6}$')
					self.assertIs(c, fn(pal, level))

	def test_glow_adds_to_the_sky_instead_of_darkening_it(self):
		# the bug this guards: a faint plain colour is darker than the lit sky
		# and shows as a dark ring; a glow must never be darker than the sky.
		s = swarm()
		sky = ls.SKY
		for pal in np.linspace(0, 0.97, 12):
			c = s.glow_colour(float(pal), 0.3)
			rgb = tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))
			self.assertTrue(all(rgb[i] >= sky[i] for i in range(3)), (pal, rgb))

	def test_hue_rotates_the_colour(self):
		s = swarm()
		before = s.colour(0.1, 1.0)
		s.adjust_hue(0.5)
		self.assertNotEqual(before, s.colour(0.1, 1.0))

	def test_palette_switching_and_knobs_clamp(self):
		s = swarm()
		for _ in range(len(ls.PALETTES)):
			s.next_palette()
		self.assertEqual(s.palette, 0)
		s.adjust_glow(50)
		self.assertEqual(s.glow, 3.5)
		s.adjust_glow(-50)
		self.assertEqual(s.glow, 0.5)
		s.adjust_swirl(99)
		self.assertEqual(s.swirl, 3.0)
		s.adjust_swirl(-99)
		self.assertEqual(s.swirl, 0.0)
		s.adjust_trail(50)
		self.assertEqual(s.trail, 5.0)
		s.adjust_trail(-50)
		self.assertEqual(s.trail, 0.15)
		s.adjust_hue(1.25)
		self.assertAlmostEqual(s.hue, 0.25)

	def test_reset_clears_ribbon_and_sparks(self):
		s = swarm()
		s.emit_sparks(10, 10, 0, 0, 50, 0.2)
		s.add_ribbon_point(1, 1, 0.1)
		s.reset()
		self.assertEqual((s.sparks_alive(), len(s.ribbon)), (0, 0))

	def test_snapshot_is_full_size_and_shows_the_ribbon(self):
		s = swarm()
		run(s, 5)
		blank = np.asarray(s.snapshot((960, 540))).astype(int).sum()
		for i in range(40):
			s.add_ribbon_point(200 + i * 8.0, 270.0, 0.3)
			s.step(1 / 30)
		img = s.snapshot((1920, 1080))
		self.assertEqual(img.size, (1920, 1080))
		patch = np.asarray(img)[500:580, 400:1000].astype(int).sum()
		self.assertGreater(patch, np.asarray(s.snapshot((1920, 1080)))[100:180, 400:1000].astype(int).sum() * 1.5)


if __name__ == '__main__':
	unittest.main()
