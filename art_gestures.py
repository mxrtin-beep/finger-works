"""Gesture helpers shared by the two artistic modes (Paint and Music).

The default Control mode has its own gesture code (event_classifier.py,
built around driving the real OS mouse/keyboard). The artistic modes don't
touch the OS cursor at all -- the right hand drives an in-app pointer and
the left hand acts as a set of dials -- so they get their own small
toolkit here instead of bending the control-mode classifier to fit.

Everything in this file is pure (no tkinter, no camera, no audio), so it
can be unit-tested with hand-built landmark arrays.
"""

import math

import numpy as np

import constants as c


# Mean wrist-to-fingertip distance (hand-scale units) of a clenched fist and
# of a fully spread hand -- the two ends of Hand.openness().
OPEN_FIST_DIST = 0.85
OPEN_SPREAD_DIST = 1.75


class Hand:
	"""One tracked hand, as the artistic modes see it.

	`abs_landmarks` are camera-frame pixels (21x3); `rel_landmarks` are
	wrist-relative *and* divided by the hand's own live size (see
	mouse_control.normalize_landmarks), which is what makes every
	finger-out / pinch cutoff in constants.py distance-independent.
	`label` is already corrected for constants.SWAP_LABELED_HANDS.
	"""

	__slots__ = ('label', 'abs', 'rel', 'frame_w', 'frame_h', '_out')

	def __init__(self, label, abs_landmarks, rel_landmarks, frame_w, frame_h):
		self.label = label
		self.abs = np.asarray(abs_landmarks, dtype=float)
		self.rel = np.asarray(rel_landmarks, dtype=float)
		self.frame_w = frame_w
		self.frame_h = frame_h
		self._out = None

	@property
	def fingers_out(self):
		"""[thumb, index, middle, ring, pinky] -> True if extended."""
		if self._out is None:
			pos = self.rel[c.FINGER_INDICES]
			self._out = np.hypot(pos[:, 0], pos[:, 1]) > c.FINGER_OUT_CUTOFF
		return self._out

	def point(self, idx):
		"""Landmark `idx` as (x, y) camera-frame pixels."""
		return float(self.abs[idx][0]), float(self.abs[idx][1])

	def pinch_point(self, finger_idx=c.INDEX_IDX):
		"""Midpoint between the thumb tip and `finger_idx`'s tip (default
		the index) -- the 'pen tip'. Used instead of the middle fingertip
		that Control mode steers with: while pinching, the middle finger
		drifts a lot, but the point where the two pinching fingertips meet
		stays put, which is what makes drawing feel like holding a real
		pen. Pass the ring tip for a thumb+ring pinch, so the point is
		where *that* pinch is rather than somewhere between the thumb and
		an unrelated index finger."""
		tx, ty = self.point(c.THUMB_IDX)
		fx, fy = self.point(finger_idx)
		return (tx + fx) / 2.0, (ty + fy) / 2.0

	def palm_point(self):
		"""Middle-finger knuckle (landmark 9): barely moves when fingers
		curl or extend, so it's the steady 'where is this hand' point for
		the left hand's dials."""
		return self.point(9)

	def openness(self):
		"""How open the hand is, 0 (clenched fist) .. 1 (fingers spread
		wide): the mean wrist-to-fingertip distance of the four fingers,
		in hand-scale units, mapped so a fist is ~0 and a fully open hand
		is ~1. Continuous, unlike the five on/off finger-out flags --
		which is what lets a squeeze or a release be a smooth *motion*."""
		tips = self.rel[[c.INDEX_IDX, c.MIDDLE_IDX, c.RING_IDX, c.PINKY_IDX]]
		mean = float(np.hypot(tips[:, 0], tips[:, 1]).mean())
		return min(max((mean - OPEN_FIST_DIST) / (OPEN_SPREAD_DIST - OPEN_FIST_DIST), 0.0), 1.0)

	def roll_degrees(self):
		"""How far the hand is tilted from upright, in degrees: 0 with the
		fingers pointing straight up, positive when it leans to the
		camera-image right (the user's right, as the image is mirrored),
		negative to the left. Measured along the wrist -> middle-knuckle
		line, which barely changes as fingers curl or spread."""
		dx, dy = self.rel[9][0], self.rel[9][1]       # image axes: y grows downward
		return math.degrees(math.atan2(dx, -dy))

	def pinch_dist(self, finger_idx):
		"""Hand-scale-normalized distance from thumb tip to `finger_idx`'s
		tip -- directly comparable to constants.LEFT/RIGHT_CLICK_CUTOFF."""
		a = self.rel[c.THUMB_IDX]
		b = self.rel[finger_idx]
		return math.hypot(a[0] - b[0], a[1] - b[1])


# --- Pose classification ---------------------------------------------------

def is_shaka(out):
	"""Thumb + pinky out, middle three folded -- the pause gesture, same
	pose Control mode uses."""
	return bool(out[0] and out[4] and not out[1] and not out[2] and not out[3])


def left_pose(out):
	"""Name the left hand's current pose, or None if it isn't one of the
	dial poses.

	The thumb is ignored for the counting poses ('one'..'four') -- it's the
	least reliable finger to read, and a relaxed hand drifts it in and
	out. 'thumb' (thumb alone) and 'fist' are the only poses that care
	about it.
	"""
	thumb, index, middle, ring, pinky = (bool(v) for v in out)
	fingers = (index, middle, ring, pinky)

	if not any(fingers):
		return 'thumb' if thumb else 'fist'
	if fingers == (True, False, False, False):
		return 'one'
	if fingers == (True, True, False, False):
		return 'two'
	if fingers == (True, True, True, False):
		return 'three'
	if fingers == (True, True, True, True):
		return 'four'
	return None


class PoseTracker:
	"""Debounces a per-frame pose: a pose only becomes the *stable* pose
	after being seen `frames` frames in a row. Stops a one-frame
	misclassification (which finger-out detection produces at the edges
	of its cutoffs) from changing a dial or switching a chord."""

	def __init__(self, frames=3):
		self.frames = frames
		self.stable = None
		self.stable_since = 0.0
		self._candidate = None
		self._count = 0

	def update(self, pose, now):
		if pose == self._candidate:
			self._count += 1
		else:
			self._candidate = pose
			self._count = 1
		if self._count >= self.frames and pose != self.stable:
			self.stable = pose
			self.stable_since = now
		return self.stable

	def held_for(self, now):
		return now - self.stable_since if self.stable is not None else 0.0

	def reset(self):
		self.stable = None
		self._candidate = None
		self._count = 0


class Latch:
	"""Fire-once-per-hold: becomes True a single time once `active` has
	been continuously true for `seconds`, then stays quiet until `active`
	goes false again. Used for 'hold the thumb pose to undo' style
	gestures, where firing every frame would be a disaster."""

	def __init__(self, seconds):
		self.seconds = seconds
		self._since = None
		self._fired = False

	def update(self, active, now):
		if not active:
			self._since = None
			self._fired = False
			return False
		if self._since is None:
			self._since = now
		if not self._fired and now - self._since >= self.seconds:
			self._fired = True
			return True
		return False


class Pinch:
	"""A pinch with hysteresis: it closes below `cutoff` but only opens
	again above `cutoff * release_factor`. Without this, a pinch hovering
	right at the threshold flickers on/off and a painted stroke or a held
	note shatters into dots."""

	def __init__(self, cutoff, release_factor=1.35):
		self.cutoff = cutoff
		self.release_factor = release_factor
		self.on = False

	def update(self, dist):
		if self.on:
			self.on = dist < self.cutoff * self.release_factor
		else:
			self.on = dist < self.cutoff
		return self.on

	def reset(self):
		self.on = False


# --- Smoothing & mapping -----------------------------------------------------

class OneEuro:
	"""One-euro filter (Casiez et al.): heavy smoothing while the hand is
	slow -- so a steady hand draws a steady line -- and light smoothing
	while it's fast, so quick strokes don't lag behind your fingers. A
	fixed-alpha EMA has to pick one trade-off for both.

	`min_cutoff` (Hz): jitter smoothing at rest, lower = steadier.
	`beta`: how quickly smoothing relaxes as speed grows, higher = snappier
	when moving. Tune `beta` to the units being filtered (pixels vs 0..1).
	"""

	def __init__(self, min_cutoff=1.5, beta=0.01, d_cutoff=1.0):
		self.min_cutoff = min_cutoff
		self.beta = beta
		self.d_cutoff = d_cutoff
		self._x = None
		self._dx = 0.0
		self._t = None

	@staticmethod
	def _alpha(cutoff, dt):
		tau = 1.0 / (2.0 * math.pi * cutoff)
		return 1.0 / (1.0 + tau / dt)

	def __call__(self, x, t):
		if self._x is None or self._t is None:
			self._x, self._t, self._dx = x, t, 0.0
			return x
		dt = max(t - self._t, 1e-3)
		self._t = t
		dx = (x - self._x) / dt
		a_d = self._alpha(self.d_cutoff, dt)
		self._dx = a_d * dx + (1 - a_d) * self._dx
		cutoff = self.min_cutoff + self.beta * abs(self._dx)
		a = self._alpha(cutoff, dt)
		self._x = a * x + (1 - a) * self._x
		return self._x

	def reset(self):
		self._x = None
		self._t = None
		self._dx = 0.0


class Pointer2D:
	"""Smooths an (x, y) point with a one-euro filter per axis."""

	def __init__(self, min_cutoff=1.5, beta=0.01):
		self._fx = OneEuro(min_cutoff, beta)
		self._fy = OneEuro(min_cutoff, beta)

	def __call__(self, x, y, t):
		return self._fx(x, t), self._fy(y, t)

	def reset(self):
		self._fx.reset()
		self._fy.reset()


# How much of the camera frame's edge is dead space when mapping a hand to
# the screen. Your hand never reaches the very edge of the camera's view
# comfortably, so mapping the *whole* frame to the screen would make the
# screen's edges/corners awkward to reach -- shrinking the mapped region
# lets a comfortable range of motion cover all of it. Vertical gets a
# larger margin than horizontal because a hand moves less (and less
# comfortably) up/down in front of a laptop camera than side to side.
#
# These are generous on purpose: the central ~60% x ~52% of the camera
# frame covers the whole screen, so you can keep your hand well back from
# the camera (where the whole hand stays in view) and still reach every
# corner with a modest movement.
FRAME_MARGIN_X = 0.22
FRAME_MARGIN_Y = 0.26


def frame_to_screen(x, y, frame_w, frame_h, screen_w, screen_h):
	"""Camera-frame pixels -> screen pixels (clamped to the screen)."""
	fx = (x / frame_w - FRAME_MARGIN_X) / (1.0 - 2.0 * FRAME_MARGIN_X)
	fy = (y / frame_h - FRAME_MARGIN_Y) / (1.0 - 2.0 * FRAME_MARGIN_Y)
	fx = min(max(fx, 0.0), 1.0)
	fy = min(max(fy, 0.0), 1.0)
	return fx * (screen_w - 1), fy * (screen_h - 1)


def height_to_level(y, frame_h, low=0.85, high=0.20):
	"""Vertical hand position -> 0..1, where a hand held up at `high` (as a
	fraction of frame height, top = 0) is 1.0 and one dropped to `low` is
	0.0. Used for absolute "hand height is a fader" controls."""
	frac = y / frame_h
	level = (low - frac) / (low - high)
	return min(max(level, 0.0), 1.0)


def pick_hands(hands):
	"""(right, left): the first hand carrying each label, or None."""
	right = left = None
	for hand in hands:
		if hand.label == 'Right' and right is None:
			right = hand
		elif hand.label == 'Left' and left is None:
			left = hand
	return right, left


class ShakaWatch:
	"""Pause gesture, debounced: the thumb+pinky pose must be seen on
	`frames` consecutive frames on either hand before it fires. Control
	mode fires on the first frame, but there an accidental pause costs
	nothing; here it would cut a stroke or a held note in half."""

	def __init__(self, frames=4):
		self.frames = frames
		self._count = 0

	def update(self, hands):
		if any(is_shaka(h.fingers_out) for h in hands):
			self._count += 1
		else:
			self._count = 0
		if self._count >= self.frames:
			self._count = 0
			return True
		return False


# --- Tilt as a joystick --------------------------------------------------------

def tilt_rate(angle_degrees, dead_zone=12.0, full=40.0):
	"""Map a hand tilt to a signed rate in -1..1: nothing inside the dead
	zone (so a hand held "straight" doesn't drift), then ramping to full
	speed at `full` degrees, with the sign following the lean.

	Used as a joystick rather than a position: tilt right to keep
	increasing a value, tilt left to keep decreasing it, return to upright
	to hold it. Unlike mapping hand position to a value, that has no range
	limit at all -- the value can travel as far as you like -- and a small
	wrist movement is enough.
	"""
	magnitude = abs(angle_degrees)
	if magnitude <= dead_zone:
		return 0.0
	amount = min((magnitude - dead_zone) / (full - dead_zone), 1.0)
	return amount if angle_degrees > 0 else -amount


class OpennessTracker:
	"""Turns a hand's openness over time into the two things the light
	modes care about: a smoothed openness level (clench to gather, relax to
	let go), and a *burst* event when a clenched hand snaps open fast.

	A burst needs both halves of the gesture -- recently clenched, then
	opening quickly -- so the ordinary wobble of a relaxed open hand never
	sets one off.
	"""

	def __init__(self, burst_speed=2.2, closed_below=0.38, memory=0.7, cooldown=0.5):
		self.burst_speed = burst_speed        # openness units / second
		self.closed_below = closed_below
		self.memory = memory                  # how recently it must have been clenched
		self.cooldown = cooldown
		self.value = 1.0
		self.velocity = 0.0
		self._t = None
		self._closed_at = -1e9
		self._last_burst = -1e9

	def update(self, openness, now):
		"""Feed one frame. Returns a burst strength in 0..1 (0 = none)."""
		if self._t is None:
			self.value, self._t = openness, now
			return 0.0
		dt = max(now - self._t, 1e-3)
		self._t = now
		new_value = 0.45 * self.value + 0.55 * openness
		velocity = (new_value - self.value) / dt
		self.velocity = 0.5 * self.velocity + 0.5 * velocity
		self.value = new_value

		if self.value < self.closed_below:
			self._closed_at = now
		if (
			self.velocity > self.burst_speed
			and now - self._closed_at < self.memory
			and now - self._last_burst > self.cooldown
		):
			self._last_burst = now
			self._closed_at = -1e9          # one clench, one burst
			return min(max(self.velocity / 6.0, 0.45), 1.0)
		return 0.0

	def reset(self):
		self._t = None
		self.value = 1.0
		self.velocity = 0.0
		self._closed_at = -1e9
