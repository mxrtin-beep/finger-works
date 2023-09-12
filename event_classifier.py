
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


def get_event(abs_landmark_list, rel_landmark_list, abs_landmark_velocities, rel_landmark_velocities):


	finger_pos = rel_landmark_list[c.FINGER_INDICES]
	
	distance_array_function = np.vectorize(dist)

	finger_dist = finger_pos[:, 0]**2 + finger_pos[:, 1]**2
	finger_out_arr = finger_dist > c.FINGER_OUT_CUTOFF

	z = abs_landmark_list[c.INDEX_IDX][2]

	if z > -0.1:
		return ''

	### DIRECTIONS
	x_vel = abs_landmark_velocities[c.INDEX_IDX][0]
	y_vel = abs_landmark_velocities[c.INDEX_IDX][1]

	direction_str = get_direction(x_vel, y_vel, c.SCROLL_VEL_CUTOFF, c.SCROLL_VEL_CUTOFF)

	print(finger_out_arr)

	
	### EVENTS
	if np.array_equal(finger_out_arr, np.array([False, False, False, False, True])):
		return 'Quit'


	thumb_index_dist = dist_twopoints(abs_landmark_list[c.THUMB_IDX], abs_landmark_list[c.INDEX_IDX])
	thumb_middle_dist = dist_twopoints(abs_landmark_list[c.THUMB_IDX], abs_landmark_list[c.MIDDLE_IDX])

	#print(thumb_index_dist, thumb_middle_dist)

	if thumb_index_dist < c.LEFT_CLICK_CUTOFF and thumb_middle_dist < c.RIGHT_CLICK_CUTOFF:
		return 'Right-Click'

	if thumb_index_dist < c.LEFT_CLICK_CUTOFF and thumb_middle_dist >= c.RIGHT_CLICK_CUTOFF:
		return 'Left-Click'


	if rel_landmark_velocities[c.INDEX_IDX][0] < -2 and rel_landmark_velocities[c.INDEX_IDX][0] > -10:
		if rel_landmark_velocities[c.INDEX_IDX][1] < 20 and rel_landmark_velocities[c.INDEX_IDX][1] > 5:
			return 'Zoom Out'


	### STEADY STATES

	if np.array_equal(finger_out_arr, np.array([False, True, False, False, False])):
		#return 'Mousing ' + direction_str
		return 'Mousing'

	if np.array_equal(finger_out_arr, np.array([False, True, True, False, False])):
		return 'Scrolling ' + direction_str

	if np.array_equal(finger_out_arr, np.array([True, True, True, True, True])):
		return 'Swiping ' + direction_str

	if np.array_equal(finger_out_arr, np.array([True, True, False, False, False])): 
		if rel_landmark_velocities[c.INDEX_IDX][0] > 2 and rel_landmark_velocities[c.INDEX_IDX][0] < 7:
			if rel_landmark_velocities[c.INDEX_IDX][1] > -15 and rel_landmark_velocities[c.INDEX_IDX][1] < -5:
				return 'Zoom In'
	

	
	return ''










