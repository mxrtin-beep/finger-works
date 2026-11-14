import os
import tempfile
import unittest

import numpy as np

import paint


def painted(engine):
	return int((np.asarray(engine.img) != np.array(paint.BACKGROUND)).any(axis=2).sum())


def stroke(engine, x0=200, x1=400, y=200, steps=20, erase=False):
	engine.begin_stroke(x0, y, erase=erase)
	for i in range(1, steps + 1):
		engine.move_stroke(x0 + (x1 - x0) * i / steps, y)
	engine.end_stroke()


class StrokeTests(unittest.TestCase):
	def setUp(self):
		self.e = paint.PaintEngine(800, 600)
		self.e.pop_dirty()

	def test_every_style_paints(self):
		for i, name in enumerate(paint.STYLES):
			e = paint.PaintEngine(800, 600)
			e.style = i
			stroke(e)
			self.assertGreater(painted(e), 100, name)

	def test_strokes_stay_inside_the_buffer_even_when_off_screen(self):
		stroke(self.e, -500, 5000, y=-40)
		stroke(self.e, 0, 0)
		stroke(self.e, 799, 799, y=599)       # corners: must not raise

	def test_symmetry_multiplies_the_ink(self):
		base = paint.PaintEngine(800, 600)
		stroke(base, 500, 600, 200)
		one = painted(base)
		for sym, copies in ((1, 2), (2, 4), (3, 6), (4, 8), (5, 12)):
			e = paint.PaintEngine(800, 600)
			e.symmetry = sym
			stroke(e, 500, 600, 200)
			self.assertGreater(painted(e), one * (copies - 1) * 0.6, paint.SYMMETRIES[sym][0])

	def test_eraser_removes_paint_and_ignores_symmetry(self):
		stroke(self.e)
		before = painted(self.e)
		self.e.symmetry = 5
		stroke(self.e, erase=True)
		self.assertLess(painted(self.e), before * 0.1)

	def test_undo_and_clear(self):
		stroke(self.e)
		self.assertGreater(painted(self.e), 0)
		self.e.clear()
		self.assertEqual(painted(self.e), 0)
		self.assertTrue(self.e.undo())                   # undo the clear
		self.assertGreater(painted(self.e), 0)
		self.assertTrue(self.e.undo())                   # undo the stroke
		self.assertEqual(painted(self.e), 0)
		self.assertFalse(self.e.undo())

	def test_undo_depth_is_bounded(self):
		for _ in range(paint.MAX_UNDO + 5):
			stroke(self.e)
		count = 0
		while self.e.undo():
			count += 1
		self.assertEqual(count, paint.MAX_UNDO)

	def test_only_touched_tiles_are_dirty(self):
		e = paint.PaintEngine(1920, 1080)
		e.pop_dirty()
		stroke(e, 100, 160, 100)
		dirty = e.pop_dirty()
		self.assertTrue(0 < len(dirty) <= 4, dirty)
		self.assertEqual(e.pop_dirty(), set())

	def test_scaled_buffer_maps_back_to_display_tiles(self):
		e = paint.PaintEngine(3840, 2160, scale=0.5)
		self.assertEqual((e.w, e.h), (1920, 1080))
		e.pop_dirty()
		stroke(e, 3000, 3100, 1500)                     # display coordinates
		dirty = e.pop_dirty()
		self.assertTrue(all(tx * paint.TILE <= 3150 and ty * paint.TILE <= 1550 for tx, ty in dirty), dirty)
		self.assertTrue(dirty)
		self.assertEqual(e.tile_image(0, 0).size, (paint.TILE, paint.TILE))
		last = e.tile_image((3840 - 1) // paint.TILE, (2160 - 1) // paint.TILE)
		self.assertEqual(last.size, (3840 - 14 * paint.TILE, 2160 - 8 * paint.TILE))

	def test_save_writes_a_png(self):
		stroke(self.e)
		with tempfile.TemporaryDirectory() as d:
			path = self.e.save(d)
			self.assertTrue(path.endswith('.png') and os.path.getsize(path) > 0)


class DialTests(unittest.TestCase):
	def test_dials_clamp_and_wrap(self):
		e = paint.PaintEngine(400, 300)
		e.adjust_size(50)
		self.assertEqual(e.size, paint.SIZE_MAX)
		e.adjust_size(-50)
		self.assertEqual(e.size, paint.SIZE_MIN)
		e.adjust_saturation(5)
		self.assertEqual(e.sat, 1.0)
		e.adjust_saturation(-5)
		self.assertEqual(e.sat, 0.0)
		e.adjust_brightness(-5)
		self.assertGreater(e.val, 0.0, 'never goes fully black -- the brush would vanish on the canvas')
		e.hue = 0.95
		e.adjust_hue(0.1)
		self.assertAlmostEqual(e.hue, 0.05)
		e.adjust_hue(-0.1)
		self.assertAlmostEqual(e.hue, 0.95)

	def test_size_changes_are_proportional(self):
		e = paint.PaintEngine(400, 300)
		e.size = 4.0
		e.adjust_size(0.3)
		small_step = e.size - 4.0
		e.size = 80.0
		e.adjust_size(0.3)
		self.assertAlmostEqual((e.size / 80.0), (4.0 + small_step) / 4.0, places=6)

	def test_style_wraps_and_symmetry_clamps(self):
		e = paint.PaintEngine(400, 300)
		e.step_style(-1)
		self.assertEqual(e.style, len(paint.STYLES) - 1)
		e.step_style(1)
		self.assertEqual(e.style, 0)
		e.step_symmetry(-1)
		self.assertEqual(e.symmetry, 0)
		for _ in range(20):
			e.step_symmetry(1)
		self.assertEqual(e.symmetry, len(paint.SYMMETRIES) - 1)


if __name__ == '__main__':
	unittest.main()
