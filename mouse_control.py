
import sys
import time

import pyautogui
import constants as c
import numpy as np

# pyautogui's default is to sleep 0.1s after *every* call it makes (moveTo,
# click, press, ...). We call several of these per camera frame, so at the
# default PAUSE that's up to several hundred ms of dead time per frame added
# on top of the camera/model latency -- which is what made cursor movement
# feel laggy/choppy rather than smooth, independent of the smoothing math
# below. We do our own frame-to-frame smoothing/rate-limiting, so we don't
# need pyautogui's built-in delay as well.
pyautogui.PAUSE = 0

screenWidth, screenHeight = pyautogui.size()


# Overall mouse-speed multiplier, on top of constants.MOUSE_SPEED. 1.0
# (the default) reproduces exactly the speed the program has always had;
# set via main_fast.py's --sensitivity command-line option, so the base
# feel is adjustable without editing constants.py.
_sensitivity_multiplier = 1.0

# Whether the zoom gesture currently has the screen zoomed in -- main.py
# tells us this whenever that state changes (see event_classifier's zoom
# toggle), rather than this module importing event_classifier itself just
# to ask.
_zoomed_in = False


def set_sensitivity_multiplier(multiplier):
	"""Scale overall mouse speed by `multiplier` (1.0 = default/unchanged,
	>1 faster, <1 slower). See main_fast.py's --sensitivity option."""
	global _sensitivity_multiplier
	_sensitivity_multiplier = multiplier


def set_zoomed(is_zoomed_in):
	"""Told by main.py whenever the zoom gesture's on/off state changes.
	Cursor speed is automatically reduced while zoomed in (see
	_effective_mouse_speed()) -- a given hand movement covers much more of
	the visible, zoomed-in area than it would at normal zoom, so it needs
	to move the cursor less on screen to still land precisely on the same
	target. Restored to normal the moment you zoom back out (or the
	program quits while still zoomed in -- see main.py's shutdown path)."""
	global _zoomed_in
	_zoomed_in = is_zoomed_in


def _effective_mouse_speed():
	speed = c.MOUSE_SPEED * _sensitivity_multiplier
	if _zoomed_in:
		speed *= c.ZOOMED_MOUSE_SPEED_FACTOR
	# MOUSE_SPEED is a fraction of the remaining distance closed per
	# frame; clamping to 1.0 keeps a large --sensitivity value from
	# pushing it past "snap there immediately" into overshoot territory.
	return min(speed, 1.0)


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


# Whether the OS left mouse button is currently held down by us. Module-
# level so execute_click() can tell a fresh pinch (button not yet down --
# press it) from a pinch that's still being held (already down -- do
# nothing and let the cursor keep moving underneath it, which is what
# makes this a drag rather than a repeated click).
_left_button_down = False

# Edge-trigger state for right-click, same idea as the fist/scissors
# gestures in event_classifier -- without it, holding the right-click
# pinch for multiple frames would fire a real right-click every frame.
_was_right_click = False


def execute_click(event):
	"""Translate the current gesture event into real OS mouse-button state.

	Left-click is a press/release pair tied to the pinch itself (mouseDown
	when the pinch starts, mouseUp when it releases) rather than a single
	pyautogui.click() fired once per frame. That's what makes click and
	click-and-drag the same gesture: release the pinch quickly and the
	down/up pair happens close together (an ordinary click); keep it
	pinched while moving your hand and the button stays down under a
	moving cursor (a drag). There's no separate timer distinguishing
	"click" from "hold" -- the OS's own click-vs-drag handling takes care
	of that once we're just reporting real button-down/button-up state.

	This releases the instant the pinch reads as broken, with no
	debounce -- a debounced release was tried (to smooth over noisier
	gloved-hand tracking splitting one drag into several) but the added
	latency made every release feel laggy, which is worse than the
	occasional split drag it was meant to fix. Better click/hold
	recognition itself (tightening LEFT_CLICK_CUTOFF, or smoothing the
	thumb-index distance signal rather than the button state) is the
	right way back to that, if it comes up again.
	"""
	global _left_button_down, _was_right_click

	is_left_pinch = (event == 'Left-Click')
	if is_left_pinch and not _left_button_down:
		pyautogui.mouseDown(button='left')
		_left_button_down = True
	elif not is_left_pinch and _left_button_down:
		pyautogui.mouseUp(button='left')
		_left_button_down = False

	is_right_pinch = (event == 'Right-Click')
	if is_right_pinch and not _was_right_click:
		pyautogui.click(button='right')
	_was_right_click = is_right_pinch


def release_all():
	"""Force the left button up if we're currently holding it down.

	Used when clicking should be suppressed for this frame (e.g. the
	cursor is over an on-screen keyboard key, so the pinch is being
	consumed as a keypress instead) -- so a drag started in Mouse mode
	can't get stuck "down" forever once control switches away from it.
	"""
	global _left_button_down
	if _left_button_down:
		pyautogui.mouseUp(button='left')
		_left_button_down = False


def execute_zoom(direction):
	"""Send a single zoom tick to the OS's own screen magnifier, so zoom
	works on *whatever's on screen* (a menu bar, a dialog, small toolbar
	icons) instead of only inside apps that implement their own zoom.

	- Windows: Win+Plus / Win+Minus drives Magnifier (Ease of Access),
	  which starts it automatically on first use. For zoom that actually
	  follows the mouse around like a loupe (which is the point here --
	  making small on-screen targets easier to click precisely), set
	  Magnifier's view to "Lens" once (Settings > Accessibility >
	  Magnifier) -- the default "Full screen" view zooms the whole
	  desktop instead of just the area around the cursor.
	- macOS: Option+Command+Equal / Option+Command+Minus drives the
	  built-in Zoom accessibility feature (System Settings >
	  Accessibility > Zoom; enable "Use scroll gesture with modifier
	  keys" or just the keyboard shortcuts, which are on by default).
	  Set its zoom style to "Lens" there for the same cursor-follow
	  behavior as Windows Magnifier's Lens mode.
	- Anything else (Linux desktops vary a lot in their screen-magnifier
	  shortcut, if they have one at all): fall back to ctrl+scroll, which
	  at least zooms inside whatever app has focus, if it supports it.

	A Windows "ding" instead of an actual zoom on Win+Plus/Minus usually
	means the shortcut key for Magnifier is turned off, not a bug here --
	that's the sound Windows Ease of Access plays specifically to say "this
	shortcut is disabled", rather than doing nothing silently. Check
	Settings > Accessibility > Magnifier > "Allow the shortcut key to
	start this feature" (and the general Ease of Access keyboard-shortcut
	toggle) if that happens.
	"""
	if sys.platform == 'win32':
		# pyautogui.hotkey('win', '+') sends the two keys close together
		# but without an explicit hold -- Windows' own global-hotkey
		# handling can be timing-sensitive enough that '+' arrives before
		# 'win' is registered as held, which reads as two unrelated
		# keypresses (Start menu, then a stray '+') instead of one
		# combo. Holding 'win' down explicitly with a short pause before
		# pressing the zoom key removes that race. 'add'/'subtract' (the
		# numpad +/-) are used rather than the top-row '+'/'-' keys since
		# they're the exact keys Magnifier's own documented shortcut
		# (Win+Numpad Plus/Minus) expects, with no shift-key ambiguity.
		pyautogui.keyDown('win')
		time.sleep(0.05)
		pyautogui.press('add' if direction == 'in' else 'subtract')
		time.sleep(0.05)
		pyautogui.keyUp('win')
	elif sys.platform == 'darwin':
		pyautogui.hotkey('option', 'command', '=' if direction == 'in' else '-')
	else:
		pyautogui.keyDown('ctrl')
		try:
			pyautogui.scroll(200 if direction == 'in' else -200)
		finally:
			pyautogui.keyUp('ctrl')


# Counts consecutive held frames of the current scroll direction, so
# execute_scroll() can only actually send a tick every SCROLL_FRAME_INTERVAL
# frames instead of every single one -- see constants.SCROLL_FRAME_INTERVAL.
# Reset (not just left to keep counting) whenever the gesture isn't held or
# switches direction, so a fresh point-up/point-down always sends its first
# tick promptly rather than picking up mid-cycle.
_scroll_frame_counter = 0
_last_scroll_direction = None


def execute_scroll(direction):
	"""Send a scroll tick for the held left-hand point-up/point-down
	gesture, paced to one real scroll every SCROLL_FRAME_INTERVAL frames
	rather than one per camera frame (see that constant's comment for why
	-- an unpaced tick every frame reads as a fast, disorientating flick
	rather than a controlled scroll).

	`direction` is 'Scroll Up', 'Scroll Down', or None (gesture not
	currently held) -- as returned by event_classifier.get_scroll_event().
	"""
	global _scroll_frame_counter, _last_scroll_direction

	if direction is None:
		_scroll_frame_counter = 0
		_last_scroll_direction = None
		return

	if direction != _last_scroll_direction:
		# Just started (or switched direction): send this first tick right
		# away rather than making it wait out a stale counter.
		_scroll_frame_counter = 0
		_last_scroll_direction = direction

	if _scroll_frame_counter % c.SCROLL_FRAME_INTERVAL == 0:
		amount = c.SCROLL_AMOUNT if direction == 'Scroll Up' else -c.SCROLL_AMOUNT
		pyautogui.scroll(amount)

	_scroll_frame_counter += 1


def hand_scale(abs_landmark_list):
	"""Wrist-to-middle-knuckle pixel distance for this frame's hand -- a
	stand-in for "how big does the hand look right now" (and so, how close
	it is to the camera) that stays roughly constant across hand poses,
	unlike a fingertip-based measurement.

	main_fast.py divides every landmark's wrist-relative position by this
	before handing it to event_classifier, which is what makes gesture
	detection (FINGER_OUT_CUTOFF, LEFT_CLICK_CUTOFF, RIGHT_CLICK_CUTOFF --
	see constants.py) work the same regardless of how far your hand is
	from the camera, instead of only at one specific distance."""
	wrist = abs_landmark_list[0]
	middle_mcp = abs_landmark_list[9]
	return ((wrist[0] - middle_mcp[0]) ** 2 + (wrist[1] - middle_mcp[1]) ** 2) ** 0.5


def normalize_landmarks(rel_landmark_list, scale):
	"""Scale a hand's wrist-relative landmark positions (rel_landmark_list,
	as produced by main_fast.pre_process_landmark) down by `scale` (its
	hand_scale()) so every gesture cutoff in constants.py can be a
	distance-independent ratio instead of a raw pixel count. `scale` is
	floored well above zero so a degenerate near-zero measurement (wrist
	and middle knuckle landmarks reported on top of each other) can't blow
	this up into huge, spuriously "extended" finger distances."""
	safe_scale = max(scale, 1.0)
	normalized = rel_landmark_list.copy()
	normalized[:, 0] /= safe_scale
	normalized[:, 1] /= safe_scale
	return normalized


def execute_event_fast(event, abs_landmark_list, event_history, frame_width, frame_height, allow_click):

	# The cursor is always moved (below) so it visually tracks your finger
	# in both Mouse and Keyboard mode -- e.g. to hover it over the
	# keyboard overlay's keys. But actually *clicking* the real desktop
	# (whatever's under the cursor) should only happen when the caller
	# says so -- in Keyboard mode that's decided per-frame by whether the
	# cursor is over a key (see main_fast.py), so it must not also fire a
	# real OS click here when it isn't.
	if allow_click:
		execute_click(event)
	else:
		release_all()

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


	if event in ('Mousing', 'Left-Click', 'Right-Click'):

		### Move mouse in direction of position
		speed = _effective_mouse_speed()
		move_x = int((scaled_x_pos - curr_mouse_x) * speed)
		move_y = int((scaled_y_pos - curr_mouse_y) * speed)

		# Clamp the destination too, since we're computing it from the
		# current position and could otherwise still land past an edge
		# if the cursor is already near one.
		dest_x = min(max(curr_mouse_x + move_x, edge_margin), screenWidth - edge_margin)
		dest_y = min(max(curr_mouse_y + move_y, edge_margin), screenHeight - edge_margin)

		# moveTo() jumps straight there with no animation, unlike the
		# previous pyautogui.move(..., duration, easing) call. That
		# duration/easing tween blocks this thread for the full duration
		# on *every single frame* (with its own internal sleep loop) on
		# top of camera/model latency and pyautogui's per-call PAUSE --
		# together those were the main source of the choppy, laggy
		# cursor motion. The smoothing that actually matters (damping
		# hand jitter, closing the gap gradually via MOUSE_SPEED) already
		# happens above and in _smooth_fingertip(); an additional
		# blocking tween on top of it was redundant as well as slow.
		pyautogui.moveTo(dest_x, dest_y)


