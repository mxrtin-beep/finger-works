
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


	# Thumb + pinky extended, other three fingers folded: pause gesture.
	# Still named/returned as 'Quit' here (event_history etc. downstream
	# key off this exact string) -- main_fast.py is what decides this now
	# pauses tracking rather than exiting the program, so an accidental
	# gesture during normal use can't end the session outright; the
	# control bar's Quit button (or Escape) is the only way to actually quit.
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


# --- Left hand: zoom toggle gesture -------------------------------------
#
# All five fingers extended (open hand): zoom in. Closed fist: zoom back
# out. Deliberately simple, maximally-distinct poses (rather than the
# earlier thumb/index pinch-and-spread) so detection itself isn't the
# weak link -- these two poses are about as far apart in finger-out/
# finger-in terms as two poses can be.
#
# This only ever runs on the hand main.py has identified as the left hand
# (see main.py's per-frame hand routing), so it doesn't collide with the
# right hand's own fist gesture (Keyboard toggle).
#
# Zoom is a single on/off level, not a repeatable "tick" -- forming the
# open-hand pose while already zoomed in does nothing (you have to close
# to a fist first), and likewise a fist does nothing unless currently
# zoomed in. That, plus requiring the pose to be held for a run of
# consecutive frames before it fires, is what keeps one gesture from
# stacking up several zoom steps in a row: each pose can only ever
# produce at most one zoom action until you deliberately reverse it.
_ZOOM_IN_POSE = np.array([True, True, True, True, True])
_ZOOM_OUT_POSE = np.array([False, False, False, False, False])

# Consecutive frames a pose must be held before it fires. At 1, it fires
# on the very first frame the pose is seen -- no held-for-a-moment delay
# at all. The single-level guard above (open-hand does nothing while
# already zoomed in, fist does nothing while already zoomed out) is what
# still keeps one continuous pose from stacking up more than one zoom
# step, so a fast trigger here doesn't reintroduce that problem; raise
# this back up if a quick incidental flash of the pose ends up
# triggering zoom by accident.
_ZOOM_ARM_FRAMES = 1

_zoom_in_frames = 0
_zoom_out_frames = 0
_is_zoomed_in = False


def get_zoom_event(rel_landmark_list):
	"""Left-hand-only zoom toggle.

	Returns (event, debug_text): event is 'Zoom In', 'Zoom Out', or None;
	debug_text is a short, always-present description of what this frame
	actually saw (which pose, and the current zoomed on/off state) --
	meant to be shown live in the overlay so it's obvious whether a
	failure to zoom is a detection problem (the pose never registers) or
	something past that (the pose registers but the OS-level zoom hotkey
	isn't landing).
	"""
	global _zoom_in_frames, _zoom_out_frames, _is_zoomed_in

	finger_pos = rel_landmark_list[c.FINGER_INDICES]
	finger_dist = np.round((finger_pos[:, 0]**2 + finger_pos[:, 1]**2)**0.5, 1)
	finger_out_arr = finger_dist > c.FINGER_OUT_CUTOFF

	is_open_hand = np.array_equal(finger_out_arr, _ZOOM_IN_POSE)
	is_fist = np.array_equal(finger_out_arr, _ZOOM_OUT_POSE)

	_zoom_in_frames = _zoom_in_frames + 1 if is_open_hand else 0
	_zoom_out_frames = _zoom_out_frames + 1 if is_fist else 0

	if is_open_hand:
		pose_text = 'open'
	elif is_fist:
		pose_text = 'fist'
	else:
		# Neither pose matched at all -- shows exactly which fingers this
		# frame read as extended, so a pose that "should" be a fist or an
		# open hand but isn't quite hitting FINGER_OUT_CUTOFF on one
		# finger is visible instead of just silently not triggering.
		out_fingers = ','.join(
			name for name, out in zip(c.FINGER_NAMES, finger_out_arr) if out
		) or 'none'
		pose_text = f'neither ({out_fingers} out)'

	debug_text = f'{pose_text}, {"zoomed" if _is_zoomed_in else "normal"}'

	# ``==`` rather than ``>=`` so this fires exactly once per continuous
	# hold of the pose, not on every frame past the arm delay.
	if is_open_hand and _zoom_in_frames == _ZOOM_ARM_FRAMES and not _is_zoomed_in:
		_is_zoomed_in = True
		return 'Zoom In', debug_text

	if is_fist and _zoom_out_frames == _ZOOM_ARM_FRAMES and _is_zoomed_in:
		_is_zoomed_in = False
		return 'Zoom Out', debug_text

	return None, debug_text


# --- Left hand: scroll gesture -------------------------------------------
#
# Point up (index finger extended and aimed upward, other four folded):
# scroll up. Point down (same pose, aimed downward): scroll down. This
# reuses the same hand that already does zoom -- zoom is your left hand's
# "how much" gesture, scroll is its "which way" gesture -- so there's
# nothing new to learn for the right (mouse) hand.
#
# Held continuously rather than edge-triggered: unlike the fist/scissors
# poses, a single scroll gesture needs to keep producing ticks for as long
# as it's held, the way an actual scroll wheel does under a moving finger.
# Pacing that down to something controllable (rather than a tick every
# camera frame) is mouse_control.execute_scroll()'s job, not this
# function's -- this just reports which way you're currently pointing,
# every frame, for as long as you're pointing.
_SCROLL_POSE = np.array([False, True, False, False, False])


def get_scroll_event(rel_landmark_list):
	"""Left-hand-only scroll gesture.

	Returns (direction, debug_text): direction is 'Scroll Up', 'Scroll
	Down', or None; debug_text mirrors get_zoom_event's/get_paste_event's
	style -- a short, always-present description of what this frame
	actually saw.
	"""
	finger_pos = rel_landmark_list[c.FINGER_INDICES]
	finger_dist = np.round((finger_pos[:, 0]**2 + finger_pos[:, 1]**2)**0.5, 1)
	finger_out_arr = finger_dist > c.FINGER_OUT_CUTOFF

	is_pointing = np.array_equal(finger_out_arr, _SCROLL_POSE)
	if not is_pointing:
		out_fingers = ','.join(
			name for name, out in zip(c.FINGER_NAMES, finger_out_arr) if out
		) or 'none'
		return None, f'neither ({out_fingers} out)'

	# rel_landmark_list is wrist-relative but still in camera-frame pixel
	# axes, so y still increases *downward* (image convention) -- a
	# fingertip aimed up on screen has a smaller/more negative y than its
	# own base knuckle.
	index_tip = rel_landmark_list[c.INDEX_IDX]
	index_base = rel_landmark_list[c.INDEX_MCP_IDX]
	dx = index_tip[0] - index_base[0]
	dy = index_tip[1] - index_base[1]

	if abs(dy) <= abs(dx):
		# Pointing mostly sideways, not up/down -- the pose is right but
		# the direction is ambiguous, so do nothing rather than guess.
		return None, 'pointing (sideways)'

	if dy < 0:
		return 'Scroll Up', 'pointing (up) -> scrolling up'
	return 'Scroll Down', 'pointing (down) -> scrolling down'


def is_zoomed_in():
	"""Whether the zoom gesture last left the screen zoomed in -- checked
	at shutdown so main.py can zoom back out to normal before exiting,
	rather than leaving the OS magnifier engaged after the program quits.
	"""
	return _is_zoomed_in


# --- Left hand: paste gesture -------------------------------------------
#
# Same "scissors" pose (index + middle extended, other three folded) as
# the right hand's Cut-Typed gesture -- but on the left hand it pastes
# instead, as a natural cut/paste mirror of the same shape rather than a
# separate pose to remember. It needs its own edge-trigger state,
# independent of get_event_fast()'s _was_scissors above, since both hands
# are processed every frame and must not affect each other's edge
# detection.
#
# (A pinky-alone pose was tried here first, but thumb+index end up close
# together when the other three fingers -- including the thumb -- are
# folded in, which is indistinguishable from the right hand's Left-Click
# pinch. Reusing the scissors pose sidesteps that: index+middle extended
# keeps thumb and index apart.)
_was_left_scissors = False


def get_paste_event(rel_landmark_list):
	"""Edge-triggered like the other pose gestures -- fires once on the
	frame the scissors pose starts on this (left) hand, not every frame
	it's held.

	Returns (fire, debug_text): fire is True on the exact frame the paste
	gesture triggers; debug_text is a short, always-present description of
	what this frame actually saw (mirrors get_zoom_event's debug_text), so
	the overlay can show *why* paste did or didn't fire, not just that it
	didn't.
	"""
	global _was_left_scissors

	finger_pos = rel_landmark_list[c.FINGER_INDICES]
	finger_dist = np.round((finger_pos[:, 0]**2 + finger_pos[:, 1]**2)**0.5, 1)
	finger_out_arr = finger_dist > c.FINGER_OUT_CUTOFF

	is_scissors = np.array_equal(finger_out_arr, np.array([False, True, True, False, False]))
	fire = is_scissors and not _was_left_scissors
	_was_left_scissors = is_scissors

	if is_scissors:
		pose_text = 'scissors'
	else:
		out_fingers = ','.join(
			name for name, out in zip(c.FINGER_NAMES, finger_out_arr) if out
		) or 'none'
		pose_text = f'neither ({out_fingers} out)'

	debug_text = pose_text + (' -> sent paste' if fire else '')

	return fire, debug_text

