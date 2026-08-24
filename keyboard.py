

import os

import constants as c

class Button():
	def __init__(self, pos, text, size=[85, 85]):
		self.pos = pos
		self.size = size
		self.text = text
		self.color = 'idle'  # 'idle' | 'hover' | 'active' -- overlay.py maps this to a fill color


def say_key_pressed(typed_char):
	if typed_char == ' ':
		os.system(' say space ')
	else:
		os.system(' say ' + str(typed_char).lower())


def get_button_list(panel_width, panel_height):
	"""Build the on-screen keyboard, laid out as a fraction of the overlay
	panel's (fixed) size -- unlike the old video-frame-based layout, this
	no longer depends on the camera's resolution at all, since the
	keyboard is now drawn on its own overlay panel rather than over the
	webcam feed."""

	keyboard_keys = [
				['1', '2', '3', '4', '5', '6', '7', '8', '9', '0', '<'],
				["Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P"],
				["A", "S", "D", "F", "G", "H", "J", "K", "L", ";"],
				["Z", "X", "C", "V", "B", "N", "M", ",", ".", "/"],
				]

	# A separate, wider-buttoned row for utility actions -- distinct from
	# the QWERTY grid above since these have longer labels and there are
	# fewer of them, so they get more room each rather than being squeezed
	# into narrow single-character-sized cells.
	#
	# 'Copy'/'Cut' act on whatever's currently selected elsewhere on the
	# desktop (via a real Ctrl+C/Ctrl+X). 'Copy Typed'/'Cut Typed' instead
	# act on this keyboard's own typed-text buffer (the text shown after
	# the '>' on the overlay) -- a separate, smaller scratchpad of what
	# you've typed here, independent of whatever else you've selected on
	# your desktop.
	utility_keys = ['Space', 'Clear', 'Copy', 'Cut', 'Copy Typed', 'Cut Typed', 'Paste']

	num_letter_rows = len(keyboard_keys)
	max_cols = max(len(row) for row in keyboard_keys)

	# Leave room at the top for the event/control-state/sensitivity debug
	# text and at the bottom for the typed-text preview line. The debug
	# text is 3 lines starting at y=16 in 14pt bold (see overlay.py's
	# draw()), which run down to roughly y=82 -- floored at 100px (rather
	# than a pure fraction of panel_height) so the keyboard's top row still
	# clears it on shorter panels instead of drawing underneath it.
	margin_x = panel_width * 0.05
	margin_top = max(panel_height * 0.20, 100)
	margin_bottom = panel_height * 0.10

	usable_width = panel_width - 2 * margin_x
	usable_height = panel_height - margin_top - margin_bottom

	# The utility row is given extra height (for its longer, wrapped
	# labels), counted here as worth 1.3 letter-rows.
	cell_h = usable_height / (num_letter_rows + 1.3)

	# +0.5 columns of slack so the half-key offset on alternating rows
	# still fits within usable_width.
	cell_w = usable_width / (max_cols + 0.5)

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

	# Utility row: spread evenly across the full usable width (not the
	# QWERTY grid) since it holds fewer, wider buttons.
	utility_cell_w = usable_width / len(utility_keys)
	utility_button_w = utility_cell_w * 0.92
	utility_button_h = cell_h * 1.3 * 0.85
	utility_row_y = margin_top + cell_h * num_letter_rows

	for col_idx, key in enumerate(utility_keys):
		pos = [int(margin_x + utility_cell_w * col_idx), int(utility_row_y)]
		b = Button(pos, key, size=[int(utility_button_w), int(utility_button_h)])

		buttonList.append(b)

	return buttonList


# Whether the previous frame was already mid Left-Click (pinch held).
# Module-level so execute_event_keyboard() can fire a key press once per
# pinch (on the frame it starts) instead of once per frame the pinch is
# held -- otherwise a pinch lasting several frames (nearly all of them,
# at 30fps) types the same letter that many times.
_was_clicking = False


def execute_event_keyboard(event, mouse_screen_pos, panel_origin, button_list):
	global _was_clicking

	# Hit-test against the real OS mouse cursor's position, converted into
	# this panel's local coordinate space (the same space button_list's
	# positions are in). The cursor is being driven every frame by
	# mouse_control regardless of Mouse/Keyboard mode, so it visually
	# tracks your finger across the overlay panel; this just asks "which
	# key (if any) is it currently over".
	origin_x, origin_y = panel_origin
	finger_x = mouse_screen_pos[0] - origin_x
	finger_y = mouse_screen_pos[1] - origin_y

	is_clicking = (event == 'Left-Click')
	fire_click = is_clicking and not _was_clicking
	_was_clicking = is_clicking

	typed_char = None
	hit_button = None
	### Detect if the cursor is over a key

	for button in button_list:
		x, y = button.pos
		w, h = button.size

		if x <= finger_x <= x + w and y <= finger_y <= y + h:

			# Button found
			hit_button = button

			if event == 'Mousing':
				button.color = 'hover'
			elif is_clicking:
				button.color = 'active'
				if fire_click:
					typed_char = button.text
					print(button.text)
		else:
			button.color = 'idle'

	# DEBUG: on each new click (not every frame it's held), print the
	# cursor position and either the key it landed on, or (if it missed
	# everything) the nearest key and how far off it was.
	if fire_click:
		if hit_button is not None:
			print(f'[DEBUG] click at cursor=({finger_x:.0f},{finger_y:.0f}) '
				f'hit "{hit_button.text}" pos={hit_button.pos} size={hit_button.size}')
		else:
			nearest = min(
				button_list,
				key=lambda b: (b.pos[0] + b.size[0] / 2 - finger_x) ** 2
					+ (b.pos[1] + b.size[1] / 2 - finger_y) ** 2,
			)
			print(f'[DEBUG] click at cursor=({finger_x:.0f},{finger_y:.0f}) '
				f'missed all keys; nearest is "{nearest.text}" pos={nearest.pos} size={nearest.size}')

	return button_list, typed_char, hit_button
