
import pyautogui
import constants as c
import numpy as np

screenWidth, screenHeight = pyautogui.size()

print(f'Screen Dimensions: {screenWidth, screenHeight}')

curr_mouse_x, curr_mouse_y = pyautogui.position()




def execute_event(event, abs_landmark_list, rel_landmark_list, abs_landmark_velocities, rel_landmark_velocities):

	curr_mouse_x, curr_mouse_y = pyautogui.position()

	index_x_pos = abs_landmark_list[c.INDEX_IDX][0]
	index_y_pos = abs_landmark_list[c.INDEX_IDX][1]

	index_x_vel = abs_landmark_velocities[c.INDEX_IDX][0]
	index_y_vel = abs_landmark_velocities[c.INDEX_IDX][1]

	#print(index_x_vel, index_y_vel)

	if event == 'Mousing':
		curr_mouse_x, curr_mouse_y = curr_mouse_x + index_x_vel*c.MOUSE_X_SENS, curr_mouse_y + index_y_vel*c.MOUSE_Y_SENS

		pyautogui.moveTo(curr_mouse_x, curr_mouse_y)
		#print(f'Moving Mouse to {index_x_pos}, {index_y_pos}.')


def execute_event_fast(event, abs_landmark_list):


	if event == 'Left-Click':
		pyautogui.click()

	if event == 'Right-Click':
		pyautogui.click(button='right')
	# point history: (4, 21, 3)
	#abs_point_history = np.array(abs_point_history)
	
	smooth_window = 16

	raw_x = abs_landmark_list[c.MIDDLE_IDX][0]
	raw_y = abs_landmark_list[c.MIDDLE_IDX][1]

	#smooth_x = np.average(abs_point_history[:smooth_window, c.INDEX_IDX, 0])
	#smooth_y = np.average(abs_point_history[:smooth_window, c.INDEX_IDX, 1])

	x = raw_x
	y = raw_y

	scaled_x_pos = (x + 250) / 250. * screenWidth * c.MOUSE_X_SENS
	scaled_y_pos = (y + 400) / 350. * screenHeight * c.MOUSE_Y_SENS
	#print(index_x_pos, index_y_pos)
	if event == 'Mousing':



		### Move mouse directly to position
		#pyautogui.moveTo(int(scaled_x_pos), int(scaled_y_pos))


		### Move mouse in direction of position
		curr_mouse_x, curr_mouse_y = pyautogui.position()
		pyautogui.move(int((scaled_x_pos - curr_mouse_x)*c.MOUSE_SPEED), int((scaled_y_pos - curr_mouse_y)*c.MOUSE_SPEED))


