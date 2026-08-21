

import cv2
import os

import constants as c

class Button():
	def __init__(self, pos, text, size=[85, 85]):
		self.pos = pos
		self.size = size
		self.text = text
		self.color = (0, 0, 0)


def say_key_pressed(typed_char):
	if typed_char == ' ':
		os.system(' say space ')
	else:
		os.system(' say ' + str(typed_char).lower())

def draw(img, buttonList, control_state):

	if control_state == 'Keyboard':
		for button in buttonList:
			x, y = button.pos
			w, h = button.size
			color = button.color

			# Scale font/line thickness to the button's own size so the
			# keyboard reads correctly at any camera resolution.
			char_size = h / 22.0
			thickness = max(1, int(round(h / 25.0)))

			#cvzone.cornerRect(img, (button.pos[0], button.pos[1],
			#	button.size[0],button.size[0]), 20 ,rt=0)
			cv2.rectangle(img, button.pos, (int(x + w), int(y + h)), (255, 144, 30), cv2.FILLED)
			cv2.putText(img, button.text, (int(x + w * 0.2), int(y + h * 0.7)),
				cv2.FONT_HERSHEY_PLAIN, char_size / len(button.text), color, thickness)
	return img



def get_button_list(frame_width, frame_height):
	"""Build the on-screen keyboard, laid out as a fraction of the actual
	camera frame size so it fits (and stays legible) regardless of the
	resolution the connected camera provides."""

	keyboard_keys = [
				['1', '2', '3', '4', '5', '6', '7', '8', '9', '0', '<'],
				["Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P"],
				["A", "S", "D", "F", "G", "H", "J", "K", "L", ";"],
				["Z", "X", "C", "V", "B", "N", "M", ",", ".", "/"],
				['Space', 'Clear']
				]

	num_rows = len(keyboard_keys)
	max_cols = max(len(row) for row in keyboard_keys)

	# Leave room at the top for the event/control-state text and at the
	# bottom for the typed-text line.
	margin_x = frame_width * 0.05
	margin_top = frame_height * 0.20
	margin_bottom = frame_height * 0.08

	usable_width = frame_width - 2 * margin_x
	usable_height = frame_height - margin_top - margin_bottom

	# +0.5 columns of slack so the half-key offset on alternating rows
	# still fits within usable_width.
	cell_w = usable_width / (max_cols + 0.5)
	cell_h = usable_height / num_rows

	button_w = cell_w * 0.85
	button_h = cell_h * 0.85

	buttonList = []
	for row_idx, row in enumerate(keyboard_keys):

		# Offset every other row of keys
		x_offset = cell_w / 2 if row_idx % 2 == 1 else 0

		for col_idx, key in enumerate(row):
			pos = [int(margin_x + cell_w * col_idx + x_offset), int(margin_top + cell_h * row_idx)]
			b = Button(pos, key, size=[int(button_w), int(button_h)])

			buttonList.append(b)

	return buttonList


def execute_event_keyboard(event, abs_landmark_list, button_list):

	# Hit-test against the index fingertip's position in the *video frame*
	# (the same pixel coordinate space the keyboard is drawn in) rather
	# than the OS mouse cursor, which lives in a completely different
	# coordinate space (the screen) and would only ever line up by chance.
	finger_x, finger_y = abs_landmark_list[c.INDEX_IDX][0], abs_landmark_list[c.INDEX_IDX][1]

	typed_char = None
	hit_button = None
	### Detect if finger is over a key

	for button in button_list:
		x, y = button.pos
		w, h = button.size

		if x <= finger_x <= x + w and y <= finger_y <= y + h:

			# Button found
			hit_button = button

			if event == 'Mousing':
				button.color = (0, 255, 0)
			elif event == 'Left-Click':
				button.color = (255, 0, 0)
				typed_char = button.text
				print(button.text)
		else:
			button.color = (0, 0, 0)

	# DEBUG: on every click attempt, print the fingertip position and
	# either the key it landed on, or (if it missed everything) the
	# nearest key and how far off it was, so a coordinate mismatch is
	# easy to spot from the console.
	if event == 'Left-Click':
		if hit_button is not None:
			print(f'[DEBUG] click at finger=({finger_x:.0f},{finger_y:.0f}) '
				f'hit "{hit_button.text}" pos={hit_button.pos} size={hit_button.size}')
		else:
			nearest = min(
				button_list,
				key=lambda b: (b.pos[0] + b.size[0] / 2 - finger_x) ** 2
					+ (b.pos[1] + b.size[1] / 2 - finger_y) ** 2,
			)
			print(f'[DEBUG] click at finger=({finger_x:.0f},{finger_y:.0f}) '
				f'missed all keys; nearest is "{nearest.text}" pos={nearest.pos} size={nearest.size}')

	return button_list, typed_char


