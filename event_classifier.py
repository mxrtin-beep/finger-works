
import numpy as np
import constants as c


# THUMB: 35,000 - 55,000
# INDEX: 25,000 - 100,000
# MIDDLE: 16,000 - 90,000
# RING: 10,000 - 120,000
# PINKY: 7,500 - 75,000

def dist(pos):
	x = pos[0]
	y = pos[1]
	return x**2 + y**2


def dist_twopoints(p1, p2):

	return np.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)


def classify_hand(abs_landmark_list):
	"""Left/right hand classification based purely on finger geometry in
	this frame, rather than MediaPipe's own Left/Right handedness label --
	that label proved unreliable in practice (a hand could get labeled
	backwards and silently lose mouse control). This instead looks at
	which side of the wrist the thumb sits relative to the pinky, which
	mirrors between hands the same way your left and right hand mirror
	each other -- so it's a direct read of the same geometry a person
	would use to tell them apart by eye, not a learned classifier that
	can be "wrong" in an opaque way.

	If this ever comes out backwards for your camera setup (e.g. an
	unusual camera orientation), flip constants.MIRROR_HANDEDNESS_ORDER
	rather than the comparison here.
	"""
	thumb_x = abs_landmark_list[c.THUMB_IDX][0]
	pinky_x = abs_landmark_list[c.PINKY_IDX][0]

	# In the mirrored (selfie-view) image this app displays, a right hand
	# held up with fingers extended toward the camera has its thumb to
	# the *left* of its pinky on screen; a left hand has the opposite
	# ordering. is_right defaults to that assumption and can be flipped
	# wholesale via the constants flag if it's backwards in practice.
	is_right = thumb_x < pinky_x
	if c.MIRROR_HANDEDNESS_ORDER:
		is_right = not is_right

	return 'Right' if is_right else 'Left'


def get_direction(x_vel, y_vel, x_cutoff, y_cutoff):

	direction = ''

	if y_vel*2 > y_cutoff:
		direction += 'Bottom '
	elif y_vel <= -y_cutoff:
		direction += 'Top '

	if x_vel > x_cutoff:
		direction += 'Right'
	elif x_vel <= -x_cutoff:
		direction += 'Left'
	else:
		direction = direction[:-1]

	return direction


# Whether the previous frame's hand pose matched the keyboard-toggle
# gesture (a closed fist). Module-level so get_event_fast() can detect
# the *transition* into a fist rather than re-firing every frame the
# fist is held.
_was_fist = False

# Same idea, for the "scissors" gesture (index + middle extended, like a
# peace sign / scissors) used to cut the keyboard's typed-text buffer.
_was_scissors = False


def get_event_fast(abs_landmark_list, rel_landmark_list, control_state):
	global _was_fist, _was_scissors

	finger_pos = rel_landmark_list[c.FINGER_INDICES]

	distance_array_function = np.vectorize(dist)

	finger_dist = np.round((finger_pos[:, 0]**2 + finger_pos[:, 1]**2)**0.5, 1)

	finger_out_arr = finger_dist > c.FINGER_OUT_CUTOFF


	# Thumb + pinky extended, other three fingers folded: quit gesture.
	if np.array_equal(finger_out_arr, np.array([True, False, False, False, True])):
		return 'Quit'

	# Closed fist (no fingers extended): toggle Mouse/Keyboard mode.
	# Edge-triggered on the fist *starting*, not fired every frame it's
	# held -- otherwise holding the pose for more than one frame flips
	# the mode back and forth every frame (Keyboard -> Mouse -> Keyboard
	# -> ...), and whichever state happens to be active in the exact
	# frame you release the gesture is the one that "sticks". That race
	# is what made the toggle feel unreliable, independent of which
	# specific gesture was used.
	is_fist = np.array_equal(finger_out_arr, np.array([False, False, False, False, False]))
	toggle_keyboard = is_fist and not _was_fist
	_was_fist = is_fist

	if is_fist:
		if toggle_keyboard:
			if control_state == 'Keyboard':
				return 'Keyboard Off'
			return 'Keyboard On'
		# Fist held past its first frame: do nothing and wait for release,
		# rather than falling through to the click-distance checks below,
		# where a curled thumb pressed against the palm would otherwise
		# read as a spurious Left/Right-Click.
		return 'Mousing'

	# Index + middle extended, other three folded ("scissors" / peace
	# sign): cut the keyboard's typed-text buffer, as a gesture shortcut
	# for the on-screen 'Cut Typed' key. Edge-triggered like the fist
	# toggle, and only meaningful in Keyboard mode -- in Mouse mode it's
	# just treated as an ordinary hand pose (returns 'Mousing') so it
	# doesn't do anything unexpected while you're just moving the cursor.
	is_scissors = np.array_equal(finger_out_arr, np.array([False, True, True, False, False]))
	cut_typed = is_scissors and not _was_scissors and control_state == 'Keyboard'
	_was_scissors = is_scissors

	if is_scissors:
		if cut_typed:
			return 'Cut Typed Gesture'
		return 'Mousing'

	# Clicking
	thumb_index_dist = dist_twopoints(abs_landmark_list[c.THUMB_IDX], abs_landmark_list[c.INDEX_IDX])
	thumb_ring_dist = dist_twopoints(abs_landmark_list[c.THUMB_IDX], abs_landmark_list[c.RING_IDX])

	if thumb_ring_dist < c.RIGHT_CLICK_CUTOFF:
		return 'Right-Click'

	if thumb_index_dist < c.LEFT_CLICK_CUTOFF and thumb_ring_dist >= c.RIGHT_CLICK_CUTOFF:
		return 'Left-Click'



	return 'Mousing'


# --- Left hand: pinch-to-zoom gesture -----------------------------------
#
# Thumb + index extended -- the same pose you'd use to pinch-zoom on a
# touchscreen. Spreading thumb and index apart zooms in; bringing them
# together zooms out. This only ever runs on the hand main.py has
# classified as the left hand (see classify_hand()), so it doesn't need to
# also demand the other three fingers be folded just to avoid colliding
# with the right hand's mouse/keyboard gestures -- that restriction was
# there back when hand routing itself was pose-based; now that routing is
# by hand identity, requiring an exact 5-finger pose match here only made
# the gesture needlessly fussy to trigger.
_ZOOM_POSE = np.array([True, True])  # thumb, index

# Frames the pose must be held before we start reacting to it. Without
# this, a single flickering frame of "thumb+index out" while your hand is
# mid-transition between other poses (e.g. opening from a fist) could arm
# zooming by accident.
_ZOOM_ARM_FRAMES = 2

# Minimum frame-to-frame change in thumb-index pixel distance to count as
# a deliberate spread/pinch motion rather than hand tremor or landmark
# jitter. This (plus the arm delay and cooldown below) is what keeps the
# gesture from triggering accidentally -- it takes a real, sustained
# widening or narrowing motion, not just holding the pose still.
_ZOOM_TRIGGER_DELTA = 10

# Minimum frames between two zoom ticks. One continuous spread/pinch
# motion should produce a steady, controllable rate of ticks, not fire on
# every single frame of a single motion.
_ZOOM_TICK_COOLDOWN = 3

_zoom_pose_frames = 0
_zoom_prev_dist = None
_zoom_cooldown = 0


def is_zoom_pose(rel_landmark_list):
	"""Whether this hand currently shows the zoom pose (thumb + index
	extended -- the other three fingers aren't checked, see the comment
	above _ZOOM_POSE)."""
	finger_pos = rel_landmark_list[c.FINGER_INDICES[:2]]
	finger_dist = np.round((finger_pos[:, 0]**2 + finger_pos[:, 1]**2)**0.5, 1)
	finger_out_arr = finger_dist > c.FINGER_OUT_CUTOFF
	return np.array_equal(finger_out_arr, _ZOOM_POSE)


def get_zoom_event(abs_landmark_list, rel_landmark_list):
	"""Zoom gesture, meant to run on whichever hand is in the zoom pose
	(see is_zoom_pose()). Returns 'Zoom In', 'Zoom Out', or None."""
	global _zoom_pose_frames, _zoom_prev_dist, _zoom_cooldown

	if not is_zoom_pose(rel_landmark_list):
		# Pose broken (or not yet formed) -- reset all gesture state so
		# the next time it's formed, it has to be held and moved
		# deliberately again rather than picking up stale history.
		_zoom_pose_frames = 0
		_zoom_prev_dist = None
		_zoom_cooldown = 0
		return None

	_zoom_pose_frames += 1
	thumb_index_dist = dist_twopoints(abs_landmark_list[c.THUMB_IDX], abs_landmark_list[c.INDEX_IDX])

	if _zoom_pose_frames < _ZOOM_ARM_FRAMES or _zoom_prev_dist is None:
		_zoom_prev_dist = thumb_index_dist
		return None

	delta = thumb_index_dist - _zoom_prev_dist
	_zoom_prev_dist = thumb_index_dist

	if _zoom_cooldown > 0:
		_zoom_cooldown -= 1
		return None

	if delta > _ZOOM_TRIGGER_DELTA:
		_zoom_cooldown = _ZOOM_TICK_COOLDOWN
		return 'Zoom In'
	if delta < -_ZOOM_TRIGGER_DELTA:
		_zoom_cooldown = _ZOOM_TICK_COOLDOWN
		return 'Zoom Out'

	return None


# --- Left hand: pinky-only paste gesture --------------------------------
#
# Pinky extended, other four fingers folded: a shortcut for the keyboard's
# 'Paste' key, without having to open the keyboard and aim at that key.
# Left-hand-only (see main.py), same as zoom, so it doesn't collide with
# the right hand's own gestures.
_PASTE_POSE = np.array([False, False, False, False, True])

_was_paste_pose = False


def get_paste_event(rel_landmark_list):
	"""Edge-triggered like the fist/scissors gestures above -- fires once
	on the frame the pinky-alone pose starts, not every frame it's held."""
	global _was_paste_pose

	finger_pos = rel_landmark_list[c.FINGER_INDICES]
	finger_dist = np.round((finger_pos[:, 0]**2 + finger_pos[:, 1]**2)**0.5, 1)
	finger_out_arr = finger_dist > c.FINGER_OUT_CUTOFF

	is_paste_pose = np.array_equal(finger_out_arr, _PASTE_POSE)
	fire = is_paste_pose and not _was_paste_pose
	_was_paste_pose = is_paste_pose

	return fire

