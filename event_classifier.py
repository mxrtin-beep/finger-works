
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


def get_event_fast(abs_landmark_list, rel_landmark_list, control_state):

	finger_pos = rel_landmark_list[c.FINGER_INDICES]

	distance_array_function = np.vectorize(dist)

	finger_dist = np.round((finger_pos[:, 0]**2 + finger_pos[:, 1]**2)**0.5, 1)

	finger_out_arr = finger_dist > c.FINGER_OUT_CUTOFF


	#if np.array_equal(finger_out_arr, np.array([False, False, False, False, True])):
	#	return 'Quit'

	if np.array_equal(finger_out_arr, np.array([True, False, False, False, False])):
		if control_state == 'Keyboard':
			return 'Keyboard Off'
		return 'Keyboard On'

	# Clicking
	thumb_index_dist = dist_twopoints(abs_landmark_list[c.THUMB_IDX], abs_landmark_list[c.INDEX_IDX])
	thumb_ring_dist = dist_twopoints(abs_landmark_list[c.THUMB_IDX], abs_landmark_list[c.RING_IDX])

	if thumb_ring_dist < c.RIGHT_CLICK_CUTOFF:
		return 'Right-Click'

	if thumb_index_dist < c.LEFT_CLICK_CUTOFF and thumb_ring_dist >= c.RIGHT_CLICK_CUTOFF:
		return 'Left-Click'



	return 'Mousing'





