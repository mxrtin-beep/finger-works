

import os

import constants as c

class Button():
	def __init__(self, pos, text, size=[85, 85], is_suggestion=False):
		self.pos = pos
		self.size = size
		self.text = text
		self.color = 'idle'  # 'idle' | 'hover' | 'active' -- overlay.py maps this to a fill color
		# Set on the three word-suggestion buttons (see get_suggestion_buttons)
		# so callers can tell "tapped a suggested word" apart from "tapped a
		# same-labeled real key" -- clicking a suggestion completes the
		# current word instead of typing its label literally.
		self.is_suggestion = is_suggestion


def say_key_pressed(typed_char):
	if typed_char == ' ':
		os.system(' say space ')
	else:
		os.system(' say ' + str(typed_char).lower())


# The two "pages" of the letter grid -- like a phone keyboard's ABC/123
# pages. Both keep the same row shape as each other (same structural keys
# in the same spots -- only the letters/punctuation between them differ)
# so the layout math below doesn't need to change per page; only the
# 'symbols' toggle key's own label depends on which page it's showing.
#
# The digit row stays on both pages (kept on top per user preference,
# rather than moving it behind the symbols page like most phone keyboards
# do) -- the 'symbols' page swaps in punctuation/math symbols for the
# QWERTY rows underneath it instead.
#
# Backspace is labeled '⌫' (a dedicated "erase" glyph), not the
# literal character '<' -- it used to be '<', which collided with the
# symbols page's actual less-than key: type_char() special-cases whatever
# string means "backspace", so pressing a literal '<' meant to type the
# character was instead always erasing, no matter which page it came from.
# A sentinel that's never a real typable character rules that out for any
# future page too.
BACKSPACE = '⌫'

# Each row is a list of (label, width) pairs -- width is in "normal key"
# units (a plain letter/digit key is 1.0), so structural keys can be wider
# than the letters around them, roughly matching where they sit on a
# physical/phone keyboard: Tab/Caps/Shift on the left, Enter/Shift on the
# right, Space spanning most of the bottom row. Each row's own total width
# is spread across the panel independently (see get_button_list), so rows
# don't need to add up to the same total.
_ROW_DIGITS = [(str(d), 1.0) for d in range(1, 10)] + [('0', 1.0), (BACKSPACE, 1.0)]

_ROW_QWERTY_LETTERS = [
	('Tab', 1.5),
	('Q', 1.0), ('W', 1.0), ('E', 1.0), ('R', 1.0), ('T', 1.0),
	('Y', 1.0), ('U', 1.0), ('I', 1.0), ('O', 1.0), ('P', 1.0),
]
_ROW_QWERTY_SYMBOLS = [
	('Tab', 1.5),
	('!', 1.0), ('@', 1.0), ('#', 1.0), ('$', 1.0), ('%', 1.0),
	('^', 1.0), ('&', 1.0), ('*', 1.0), ('(', 1.0), (')', 1.0),
]

_ROW_HOME_LETTERS = [
	('Caps', 1.8),
	('A', 1.0), ('S', 1.0), ('D', 1.0), ('F', 1.0), ('G', 1.0),
	('H', 1.0), ('J', 1.0), ('K', 1.0), ('L', 1.0), (';', 1.0),
	('Enter', 1.8),
]
_ROW_HOME_SYMBOLS = [
	('Caps', 1.8),
	('-', 1.0), ('_', 1.0), ('=', 1.0), ('+', 1.0), ('[', 1.0),
	(']', 1.0), ('{', 1.0), ('}', 1.0), ('\\', 1.0), ('|', 1.0),
	('Enter', 1.8),
]

_ROW_BOTTOM_LETTERS = [
	('Shift', 2.2),
	('Z', 1.0), ('X', 1.0), ('C', 1.0), ('V', 1.0), ('B', 1.0),
	('N', 1.0), ('M', 1.0), (',', 1.0), ('.', 1.0), ('/', 1.0),
	('Shift', 2.2),
]
_ROW_BOTTOM_SYMBOLS = [
	('Shift', 2.2),
	('~', 1.0), ('`', 1.0), (':', 1.0), ('"', 1.0), ("'", 1.0),
	('<', 1.0), ('>', 1.0), ('?', 1.0), ('/', 1.0), (',', 1.0),
	('Shift', 2.2),
]

# Letters only -- used to decide which buttons get their displayed case
# flipped by Shift/Caps (see overlay.py's draw()). Symbol-page keys are
# literal characters that don't have an upper/lower form.
LETTER_CHARS = frozenset('QWERTYUIOPASDFGHJKLZXCVBNM')


def _layout_margins(panel_width, panel_height):
	"""Shared geometry between get_button_list() and get_suggestion_buttons()
	-- both need to agree on where the letter grid starts so the word-
	suggestion bar has its own reserved strip above it instead of overlapping
	the QWERTY rows or the debug text.

	Returns (margin_x, debug_margin_top, suggestion_bar_height,
	grid_margin_top, margin_bottom):
	  - debug_margin_top: same "leave room for the debug text" margin
	    get_button_list always used, kept as its own value since the
	    suggestion bar sits directly below it.
	  - suggestion_bar_height: height of the word-suggestion strip, always
	    reserved (the bar is always shown while the keyboard is open) --
	    floored in pixels so it stays usable on a small/scaled-down panel.
	  - grid_margin_top: where the letter grid itself starts -- debug_margin_top
	    plus the suggestion bar's height.
	"""
	margin_x = panel_width * 0.05
	debug_margin_top = max(panel_height * 0.20, 100)
	suggestion_bar_height = max(panel_height * 0.09, 34)
	grid_margin_top = debug_margin_top + suggestion_bar_height
	margin_bottom = panel_height * 0.10
	return margin_x, debug_margin_top, suggestion_bar_height, grid_margin_top, margin_bottom


def get_suggestion_buttons(panel_width, panel_height, suggestions):
	"""Build the (up to 3) word-suggestion buttons shown in their own strip
	above the letter grid -- the on-screen-keyboard equivalent of an
	iPhone's predictive-text bar. `suggestions` is the list of words to
	show (see word_predictions.get_suggestions()), left-to-right in the
	order given.

	Rebuilt fresh every time the current word changes (see main_fast.py)
	rather than folded into get_button_list()'s letter grid, since the grid
	itself doesn't need to change when suggestions do.
	"""
	margin_x, debug_margin_top, suggestion_bar_height, _, _ = _layout_margins(panel_width, panel_height)

	buttons = []
	if not suggestions:
		return buttons

	usable_width = panel_width - 2 * margin_x
	gap = max(3, round(panel_width * 0.006))
	cell_w = usable_width / len(suggestions)
	button_h = suggestion_bar_height * 0.8
	y = debug_margin_top + (suggestion_bar_height - button_h) / 2

	last_idx = len(suggestions) - 1
	for idx, word in enumerate(suggestions):
		left_inset = 0 if idx == 0 else gap / 2
		right_inset = 0 if idx == last_idx else gap / 2
		x = margin_x + idx * cell_w
		pos = [int(x + left_inset), int(y)]
		size = [int(cell_w - left_inset - right_inset), int(button_h)]
		buttons.append(Button(pos, word, size=size, is_suggestion=True))

	return buttons


def get_button_list(panel_width, panel_height, page='letters'):
	"""Build the on-screen keyboard, laid out as a fraction of the overlay
	panel's (fixed) size -- unlike the old video-frame-based layout, this
	no longer depends on the camera's resolution at all, since the
	keyboard is now drawn on its own overlay panel rather than over the
	webcam feed.

	Roughly follows where keys sit on a physical/phone keyboard: Tab/Caps/
	Shift down the left side of the QWERTY block, Enter/Shift on the
	right, a wide Space bar along the bottom, with the remaining actions
	(clipboard/undo-redo/page-switch, which have no physical-keyboard
	equivalent) in their own row underneath.

	`page` selects 'letters' (QWERTY, the default) or 'symbols' (punctuation
	and math symbols) for the letter rows -- rebuild the button list with
	the other page when the on-screen '123'/'ABC' key is pressed (see
	main_fast.py)."""

	if page == 'symbols':
		letter_rows = [_ROW_DIGITS, _ROW_QWERTY_SYMBOLS, _ROW_HOME_SYMBOLS, _ROW_BOTTOM_SYMBOLS]
	else:
		letter_rows = [_ROW_DIGITS, _ROW_QWERTY_LETTERS, _ROW_HOME_LETTERS, _ROW_BOTTOM_LETTERS]

	# Space spans most of the bottom row, like a real keyboard, with the
	# clipboard actions that don't fit anywhere else in the physical-style
	# grid above flanking it.
	#
	# 'Copy'/'Cut' act on whatever's currently selected elsewhere on the
	# desktop (via a real Ctrl+C/Ctrl+X). 'Copy Typed'/'Cut Typed' instead
	# act on this keyboard's own typed-text buffer (the text shown after
	# the '>' on the overlay) -- a separate, smaller scratchpad of what
	# you've typed here, independent of whatever else you've selected on
	# your desktop.
	row_space = [
		('Clear', 1.3), ('Copy', 1.3), ('Cut', 1.3),
		('Space', 3.5),
		('Copy Typed', 1.7), ('Cut Typed', 1.7), ('Paste', 1.3),
	]

	# Everything else that has no physical-keyboard spot of its own,
	# spread across its own row. Its page-toggle key's label flips between
	# '123' and 'ABC' depending on which page is currently showing, like a
	# phone keyboard's mode-switch key.
	page_toggle_label = 'ABC' if page == 'symbols' else '123'
	row_actions = [
		('Undo', 1.3), ('Redo', 1.3), ('Select All', 1.7), (page_toggle_label, 1.3),
	]

	utility_rows = [row_space, row_actions]

	num_letter_rows = len(letter_rows)
	num_utility_rows = len(utility_rows)

	# Leave room at the top for the event/control-state/sensitivity debug
	# text and at the bottom for the typed-text preview line. The debug
	# text is 3 lines starting at y=16 in 14pt bold (see overlay.py's
	# draw()), which run down to roughly y=82 -- floored at 100px (rather
	# than a pure fraction of panel_height) so the keyboard's top row still
	# clears it on shorter panels instead of drawing underneath it.
	margin_x, _debug_margin_top, _suggestion_bar_height, margin_top, margin_bottom = _layout_margins(
		panel_width, panel_height,
	)

	usable_width = panel_width - 2 * margin_x
	usable_height = panel_height - margin_top - margin_bottom

	# Each utility row is given extra height (for its longer, wrapped
	# labels), counted here as worth 1.3 letter-rows each.
	cell_h = usable_height / (num_letter_rows + 1.3 * num_utility_rows)
	button_h = cell_h * 0.85
	utility_button_h = cell_h * 1.3 * 0.85

	buttonList = []

	# A small, fixed pixel gutter between adjacent keys -- not a fraction
	# of each key's own width. Sizing the gap as a percentage of the key
	# (the old approach) meant a very wide key (Space) got a proportionally
	# huge gap on each side of it, which is what made the space around
	# Space and the bottom action row look oversized/uneven. A fixed gap
	# looks the same regardless of how wide the key next to it is.
	gap = max(3, round(panel_width * 0.006))

	def add_row(row, row_y, row_height):
		# Each row's own key widths are spread across the *same* usable
		# width independently of every other row's total -- so a row with
		# a few wide keys (Space's row) and a row with many narrow ones
		# (the digit row) both end up flush with the panel's edges, rather
		# than one row-wide cell size forcing every row to the same total
		# key count.
		total_units = sum(width for _, width in row)
		cell_w = usable_width / total_units

		x = margin_x
		last_idx = len(row) - 1
		for idx, (label, width) in enumerate(row):
			key_w = cell_w * width
			# Only the gap *between* keys is carved out of each button's
			# rendered width -- the first key in every row still starts
			# exactly at margin_x, and the last key in every row still
			# ends exactly at margin_x + usable_width, regardless of that
			# row's own total unit count. That's what keeps every row's
			# left and right edges flush with each other (and with the
			# panel), where shrinking every key symmetrically (including
			# its outer edge) used to leave each row's actual left/right
			# edge at a slightly different inset depending on its first/
			# last key's width.
			left_inset = 0 if idx == 0 else gap / 2
			right_inset = 0 if idx == last_idx else gap / 2
			pos = [int(x + left_inset), int(row_y)]
			size = [int(key_w - left_inset - right_inset), int(row_height)]
			buttonList.append(Button(pos, label, size=size))
			x += key_w

	for row_idx, row in enumerate(letter_rows):
		add_row(row, margin_top + cell_h * row_idx, button_h)

	utility_row_y = margin_top + cell_h * num_letter_rows
	for row in utility_rows:
		add_row(row, utility_row_y, utility_button_h)
		utility_row_y += cell_h * 1.3

	return buttonList


# Whether the previous frame was already mid Left-Click (pinch held).
# Module-level so execute_event_keyboard() can fire a key press once per
# pinch (on the frame it starts) instead of once per frame the pinch is
# held -- otherwise a pinch lasting several frames (nearly all of them,
# at 30fps) types the same letter that many times.
_was_clicking = False


def execute_event_keyboard(event, mouse_screen_pos, panel_origin, panel_size, button_list):
	global _was_clicking

	# Hit-test against the real OS mouse cursor's position, converted into
	# this panel's local coordinate space (the same space button_list's
	# positions are in). The cursor is being driven every frame by
	# mouse_control regardless of Mouse/Keyboard mode, so it visually
	# tracks your finger across the overlay panel; this just asks "which
	# key (if any) is it currently over".
	origin_x, origin_y = panel_origin
	panel_width, panel_height = panel_size
	finger_x = mouse_screen_pos[0] - origin_x
	finger_y = mouse_screen_pos[1] - origin_y

	# Whether the cursor is anywhere over the keyboard panel at all, key or
	# not -- used by main_fast.py to tell "clicked the panel's own gray
	# background" (should do nothing at all, not fall through to a real
	# desktop click on whatever's visually behind this overrideredirect
	# window) apart from "clicked somewhere else on the desktop entirely"
	# (a real click there is intentional and still allowed while the
	# keyboard is open -- see main_fast.py's allow_click).
	over_panel = 0 <= finger_x <= panel_width and 0 <= finger_y <= panel_height

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
		else:
			button.color = 'idle'

	# DEBUG: on each new click (not every frame it's held), print the
	# cursor position and either the key it landed on, or (if it missed
	# everything) the nearest key and how far off it was.
	if fire_click:
		if hit_button is not None:
			print(f'[DEBUG] click at cursor=({finger_x:.0f},{finger_y:.0f}) '
				f'hit "{hit_button.text}" pos={hit_button.pos} size={hit_button.size}')
		elif over_panel:
			nearest = min(
				button_list,
				key=lambda b: (b.pos[0] + b.size[0] / 2 - finger_x) ** 2
					+ (b.pos[1] + b.size[1] / 2 - finger_y) ** 2,
			)
			print(f'[DEBUG] click at cursor=({finger_x:.0f},{finger_y:.0f}) '
				f'hit panel background (not a key); nearest is "{nearest.text}" '
				f'pos={nearest.pos} size={nearest.size}')

	return button_list, typed_char, hit_button, over_panel
