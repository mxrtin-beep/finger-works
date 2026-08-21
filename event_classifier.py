
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


def get_event_fast(abs_landmark_list, rel_landmark_list, control_state):
	global _was_fist

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

	# Clicking
	thumb_index_dist = dist_twopoints(abs_landmark_list[c.THUMB_IDX], abs_landmark_list[c.INDEX_IDX])
	thumb_ring_dist = dist_twopoints(abs_landmark_list[c.THUMB_IDX], abs_landmark_list[c.RING_IDX])

	if thumb_ring_dist < c.RIGHT_CLICK_CUTOFF:
		return 'Right-Click'

	if thumb_index_dist < c.LEFT_CLICK_CUTOFF and thumb_ring_dist >= c.RIGHT_CLICK_CUTOFF:
		return 'Left-Click'



	return 'Mousing'





