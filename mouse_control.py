
import sys

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
	"""
	if sys.platform == 'win32':
		pyautogui.hotkey('win', '+' if direction == 'in' else '-')
	elif sys.platform == 'darwin':
		pyautogui.hotkey('option', 'command', '=' if direction == 'in' else '-')
	else:
		pyautogui.keyDown('ctrl')
		try:
			pyautogui.scroll(200 if direction == 'in' else -200)
		finally:
			pyautogui.keyUp('ctrl')


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
		move_x = int((scaled_x_pos - curr_mouse_x) * c.MOUSE_SPEED)
		move_y = int((scaled_y_pos - curr_mouse_y) * c.MOUSE_SPEED)

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


