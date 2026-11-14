import unittest

import numpy as np

import art_gestures as ag
import constants as c
from tests import handmodel as hm


class PoseTests(unittest.TestCase):
	def test_finger_out_matches_requested_pose(self):
		for pose in (hm.FIST, hm.ONE, hm.TWO, hm.THREE, hm.FOUR, hm.OPEN, hm.THUMB, hm.SHAKA):
			hand = hm.make_hand(out=pose)
			self.assertEqual([bool(v) for v in hand.fingers_out], [bool(v) for v in pose], pose)

	def test_left_pose_names(self):
		expected = {
			hm.FIST: 'fist', hm.THUMB: 'thumb', hm.ONE: 'one', hm.TWO: 'two',
			hm.THREE: 'three', hm.FOUR: 'four', hm.OPEN: 'four',    # thumb ignored for counts
			hm.SHAKA: None,
		}
		for pose, name in expected.items():
			self.assertEqual(ag.left_pose(hm.make_hand(out=pose).fingers_out), name, pose)

	def test_shaka_only_matches_shaka(self):
		self.assertTrue(ag.is_shaka(hm.make_hand(out=hm.SHAKA).fingers_out))
		for pose in (hm.FIST, hm.ONE, hm.TWO, hm.THREE, hm.FOUR, hm.OPEN, hm.THUMB):
			self.assertFalse(ag.is_shaka(hm.make_hand(out=pose).fingers_out), pose)

	def test_pinch_distances_respect_the_click_cutoffs(self):
		index = hm.make_hand(out=hm.OPEN, pinch='index')
		self.assertLess(index.pinch_dist(c.INDEX_IDX), c.LEFT_CLICK_CUTOFF)
		ring = hm.make_hand(out=hm.OPEN, pinch='ring')
		self.assertLess(ring.pinch_dist(c.RING_IDX), c.RIGHT_CLICK_CUTOFF)
		near = hm.make_hand(out=hm.OPEN, pinch='near_index')
		self.assertGreater(near.pinch_dist(c.INDEX_IDX), c.LEFT_CLICK_CUTOFF * ag.Pinch(0).release_factor)

	def test_pinch_point_is_where_the_pinch_is(self):
		ring = hm.make_hand(out=hm.OPEN, pinch='ring')
		tx, ty = ring.point(c.THUMB_IDX)
		rx, ry = ring.point(c.RING_IDX)
		px, py = ring.pinch_point(c.RING_IDX)
		self.assertAlmostEqual(px, (tx + rx) / 2)
		self.assertAlmostEqual(py, (ty + ry) / 2)
		# ...which is not where the default (thumb+index) point is
		self.assertGreater(abs(ring.pinch_point()[0] - px) + abs(ring.pinch_point()[1] - py), 5)


class OpennessAndTiltTests(unittest.TestCase):
	def test_openness_spans_fist_to_spread(self):
		self.assertLess(hm.make_hand(out=hm.FIST).openness(), 0.1)
		self.assertGreater(hm.make_hand(out=hm.OPEN).openness(), 0.95)
		self.assertTrue(0.0 <= hm.make_hand(out=hm.TWO).openness() <= 1.0)

	def test_roll_follows_the_tilt(self):
		for tilt in (-45, -20, 0, 20, 45):
			self.assertAlmostEqual(hm.make_hand(out=hm.OPEN, roll=tilt).roll_degrees(), tilt, delta=0.5)
		# curling the fingers must not change the measured roll
		self.assertAlmostEqual(hm.make_hand(out=hm.FIST, roll=25).roll_degrees(), 25, delta=0.5)

	def test_tilt_is_a_joystick_with_a_dead_zone(self):
		self.assertEqual(ag.tilt_rate(0), 0.0)
		self.assertEqual(ag.tilt_rate(11), 0.0)
		self.assertEqual(ag.tilt_rate(-11), 0.0)
		self.assertGreater(ag.tilt_rate(25), 0.0)
		self.assertLess(ag.tilt_rate(-25), 0.0)
		self.assertEqual(ag.tilt_rate(40), 1.0)
		self.assertEqual(ag.tilt_rate(80), 1.0)
		self.assertEqual(ag.tilt_rate(-80), -1.0)
		self.assertLess(ag.tilt_rate(20), ag.tilt_rate(30))          # monotonic

	def test_burst_needs_a_clench_then_a_fast_open(self):
		def run(values, dt=1 / 30):
			t = ag.OpennessTracker()
			fired = []
			for i, v in enumerate(values):
				fired.append(t.update(v, i * dt))
			return [b for b in fired if b > 0]
		clench = [1.0] * 5 + [0.0] * 8
		self.assertEqual(len(run(clench + [0.0, 0.5, 1.0, 1.0, 1.0, 1.0])), 1, 'clench then snap open -> one burst')
		self.assertEqual(run([1.0] * 40), [], 'a relaxed open hand never bursts')
		wobble = [0.9, 0.7, 0.95, 0.75, 1.0, 0.8] * 6
		self.assertEqual(run(wobble), [], 'ordinary wobble is not a burst')
		slow = [1.0] * 5 + [0.0] * 8 + [i / 60 for i in range(0, 60)]
		self.assertEqual(run(slow), [], 'a slow release is not a burst')
		half_open_snap = [0.5] * 6 + [1.0] * 8          # fast, but never clenched first
		self.assertEqual(run(half_open_snap), [], 'opening quickly from half-closed is not a burst')
		stale = [0.0] * 6 + [i / 40 for i in range(1, 21)] + [0.5] * 40 + [1.0] * 6   # clenched long ago, released slowly, then snapped
		self.assertEqual(run(stale), [], 'the clench must be recent')
		two = clench + [1.0] * 5 + clench + [1.0] * 5
		self.assertLessEqual(len(run(two)), 2)

	def test_burst_strength_follows_the_snap(self):
		t = ag.OpennessTracker()
		for i in range(10):
			t.update(0.0, i / 30)
		strengths = [t.update(v, (10 + i) / 30) for i, v in enumerate([1.0] * 5)]
		strength = max(strengths)
		self.assertTrue(0.45 <= strength <= 1.0)


class DebounceTests(unittest.TestCase):
	def test_pose_must_repeat_before_it_becomes_stable(self):
		t = ag.PoseTracker(frames=3)
		self.assertIsNone(t.update('one', 0.0))
		self.assertIsNone(t.update('one', 0.1))
		self.assertEqual(t.update('one', 0.2), 'one')
		self.assertEqual(t.update('two', 0.3), 'one')       # a single stray frame doesn't switch
		self.assertEqual(t.update('one', 0.4), 'one')
		for i in range(3):
			t.update('two', 0.5 + i * 0.1)
		self.assertEqual(t.stable, 'two')

	def test_latch_fires_once_per_hold(self):
		latch = ag.Latch(0.5)
		self.assertFalse(latch.update(True, 0.0))
		self.assertFalse(latch.update(True, 0.4))
		self.assertTrue(latch.update(True, 0.6))
		self.assertFalse(latch.update(True, 1.5))            # still held: no re-fire
		self.assertFalse(latch.update(False, 1.6))
		self.assertFalse(latch.update(True, 1.7))
		self.assertTrue(latch.update(True, 2.3))             # fires again after a release

	def test_pinch_hysteresis(self):
		p = ag.Pinch(0.25, release_factor=1.4)
		self.assertFalse(p.update(0.30))
		self.assertTrue(p.update(0.20))
		self.assertTrue(p.update(0.33), 'stays closed just past the closing threshold')
		self.assertFalse(p.update(0.40))
		self.assertFalse(p.update(0.30), 'does not reclose until back under the threshold')

	def test_shaka_watch_needs_consecutive_frames(self):
		w = ag.ShakaWatch(frames=4)
		shaka, fist = hm.make_hand(out=hm.SHAKA), hm.make_hand(out=hm.FIST)
		self.assertEqual([w.update([shaka]) for _ in range(3)], [False] * 3)
		self.assertFalse(w.update([fist]))                   # interrupted
		self.assertEqual([w.update([shaka]) for _ in range(4)], [False, False, False, True])
		# either hand counts
		w = ag.ShakaWatch(frames=2)
		left_shaka = hm.make_hand('Left', out=hm.SHAKA)
		self.assertEqual([w.update([fist, left_shaka]) for _ in range(2)], [False, True])


class SmoothingAndMappingTests(unittest.TestCase):
	def test_one_euro_damps_jitter_but_tracks_fast_motion(self):
		rng = np.random.default_rng(1)
		f = ag.OneEuro(min_cutoff=1.5, beta=0.01)
		jitter = [f(500 + rng.normal(0, 3), i / 30) for i in range(120)]
		self.assertLess(np.std(jitter[30:]), 1.5, 'a still hand with +-3px noise should come out steady')
		g = ag.OneEuro(min_cutoff=1.5, beta=0.01)
		out = [g(i * 40.0, i / 30) for i in range(60)]       # 1200 px/s sweep
		self.assertLess(abs(out[-1] - 59 * 40.0), 80, 'a fast sweep should not lag far behind')

	def test_frame_to_screen_maps_and_clamps(self):
		fw, fh, sw, sh = 640, 480, 1920, 1080
		x, y = ag.frame_to_screen(fw / 2, fh / 2, fw, fh, sw, sh)
		self.assertAlmostEqual(x, (sw - 1) / 2, delta=1)
		self.assertAlmostEqual(y, (sh - 1) / 2, delta=1)
		self.assertEqual(ag.frame_to_screen(0, 0, fw, fh, sw, sh), (0.0, 0.0))
		self.assertEqual(ag.frame_to_screen(fw, fh, fw, fh, sw, sh), (sw - 1, sh - 1))
		# the screen's edges are reachable without leaving the camera frame
		x, _ = ag.frame_to_screen(fw * (1 - ag.FRAME_MARGIN_X), fh / 2, fw, fh, sw, sh)
		self.assertAlmostEqual(x, sw - 1, delta=1)

	def test_height_to_level(self):
		self.assertEqual(ag.height_to_level(0, 480), 1.0)
		self.assertEqual(ag.height_to_level(479, 480), 0.0)
		self.assertGreater(ag.height_to_level(150, 480), ag.height_to_level(300, 480))

	def test_pick_hands(self):
		r, l = hm.make_hand('Right'), hm.make_hand('Left')
		self.assertEqual(ag.pick_hands([l, r]), (r, l))
		self.assertEqual(ag.pick_hands([]), (None, None))
		self.assertEqual(ag.pick_hands([r]), (r, None))


if __name__ == '__main__':
	unittest.main()
