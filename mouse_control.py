
import pyautogui
import constants as c
import numpy as np

screenWidth, screenHeight = pyautogui.size()

print(f'Screen Dimensions: {screenWidth, screenHeight}')

curr_mouse_x, curr_mouse_y = pyautogui.position()


# Ideas for dragging mouse

## always be moving mouse, mouse down when fingers touch --> doens't work
## have a different thing for click and drag
## have two fingers up be scroll
## record a history; if it's fast, make it a click, if it's slow, make it a drag or mousedown



# Try these:
'''
>>> pyautogui.moveTo(100, 100, 2, pyautogui.easeInQuad)     # start slow, end fast
>>> pyautogui.moveTo(100, 100, 2, pyautogui.easeOutQuad)    # start fast, end slow
>>> pyautogui.moveTo(100, 100, 2, pyautogui.easeInOutQuad)  # start and end fast, slow in middle
>>> pyautogui.moveTo(100, 100, 2, pyautogui.easeInBounce)   # bounce at the end
>>> pyautogui.moveTo(100, 100, 2, pyautogui.easeInElastic)  # rubber band at the end

'''

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


# Adaptive smoothing state for the raw fingertip position (camera-frame
# pixel units), persisted across calls. Small frame-to-frame movement --
# natural hand tremor plus landmark-estimation noise -- is heavily damped,
# while large, intentional movements pass through with little smoothing.
# Without this, tightening MOUSE_SPEED (to fix the earlier sluggishness)
# also made the cursor amplify that noise, making it hard to hold still
# over a small key. Jitter big-vs-small is judged relative to the frame
# width so it holds up across camera resolutions.
_filtered_x = None
_filtered_y = None

_JITTER_RADIUS_FRAC = 0.01   # frame-widths; deltas below this count as noise
_JITTER_ALPHA = 0.15         # smoothing factor applied to jitter-sized movement
_INTENT_ALPHA = 0.9          # smoothing factor applied to larger, intentional movement


def _smooth_fingertip(raw_x, raw_y, frame_width):
	global _filtered_x, _filtered_y

	if _filtered_x is None:
		_filtered_x, _filtered_y = raw_x, raw_y
		return raw_x, raw_y

	jitter_radius = frame_width * _JITTER_RADIUS_FRAC
	delta = ((raw_x - _filtered_x) ** 2 + (raw_y - _filtered_y) ** 2) ** 0.5
	alpha = _JITTER_ALPHA if delta < jitter_radius else _INTENT_ALPHA

	_filtered_x += alpha * (raw_x - _filtered_x)
	_filtered_y += alpha * (raw_y - _filtered_y)

	return _filtered_x, _filtered_y


def execute_event_fast(event, abs_landmark_list, event_history, frame_width, frame_height, allow_click):

	# The cursor is always moved (below) so it visually tracks your finger
	# in both Mouse and Keyboard mode -- e.g. to hover it over the
	# keyboard overlay's keys. But actually *clicking* the real desktop
	# (whatever's under the cursor) should only happen in Mouse mode;
	# in Keyboard mode the same pinch gesture is instead intercepted as a
	# key press by keyboard.execute_event_keyboard(), so it must not also
	# fire a real OS click here.
	if allow_click:
		### Left click: [Mouse] [LC] [Mouse]
		### Drag: [LC], [LC], [LC]
		if event == 'Left-Click':
			pyautogui.click()

		if event == 'Right-Click':
			pyautogui.click(button='right')

	raw_x = abs_landmark_list[c.MIDDLE_IDX][0]
	raw_y = abs_landmark_list[c.MIDDLE_IDX][1]

	raw_x, raw_y = _smooth_fingertip(raw_x, raw_y, frame_width)

	# Normalize the fingertip's position within the actual camera frame
	# (0..1 on each axis) and map that onto the screen, instead of the old
	# hardcoded (x + 250) / 250 style calibration -- that assumed a narrow,
	# specific pixel range and doesn't generalize across camera/screen
	# resolutions.
	frac_x = min(max(raw_x / frame_width, 0.0), 1.0)
	frac_y = min(max(raw_y / frame_height, 0.0), 1.0)

	scaled_x_pos = frac_x * screenWidth * c.MOUSE_X_SENS
	scaled_y_pos = frac_y * screenHeight * c.MOUSE_Y_SENS

	# Keep the cursor a couple pixels clear of the true screen edges so we
	# never trigger PyAutoGUI's corner fail-safe.
	edge_margin = 2
	scaled_x_pos = min(max(scaled_x_pos, edge_margin), screenWidth - edge_margin)
	scaled_y_pos = min(max(scaled_y_pos, edge_margin), screenHeight - edge_margin)

	curr_mouse_x, curr_mouse_y = pyautogui.position()


	if event == 'Mousing':

		### Move mouse in direction of position
		move_x = int((scaled_x_pos - curr_mouse_x) * c.MOUSE_SPEED)
		move_y = int((scaled_y_pos - curr_mouse_y) * c.MOUSE_SPEED)

		# Clamp the destination too, since pyautogui.move() is relative
		# to the current position and could otherwise still land on an
		# edge if the cursor is already near one.
		dest_x = min(max(curr_mouse_x + move_x, edge_margin), screenWidth - edge_margin)
		dest_y = min(max(curr_mouse_y + move_y, edge_margin), screenHeight - edge_margin)

		pyautogui.move(
				dest_x - curr_mouse_x,
				dest_y - curr_mouse_y,
				0.01,
				pyautogui.easeInQuad
			)


