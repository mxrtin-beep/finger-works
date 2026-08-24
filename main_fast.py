
import datetime
import os
import sys
import threading
import time
import urllib.request

import cv2
import mediapipe as mp
import pyautogui
import pyperclip
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import (
	HandLandmarker,
	HandLandmarkerOptions,
	RunningMode,
)
import numpy as np
from collections import deque

import mouse_control as mc
from mouse_control import execute_event_fast, screenWidth, screenHeight
from event_classifier import get_event_fast, get_zoom_event, get_paste_event, get_scroll_event, is_zoomed_in
import constants as c
import keyboard as k
import overlay as ov
import settings as fw_settings


__version__ = '0.2.0'

MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'hand_landmarker.task')
MODEL_URL = 'https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task'


def ensure_model_downloaded(model_path=MODEL_PATH, model_url=MODEL_URL):
	"""Download the HandLandmarker task model if it isn't already on disk."""
	if not os.path.exists(model_path):
		print(f'Downloading hand landmarker model to {model_path}...')
		urllib.request.urlretrieve(model_url, model_path)
	return model_path


width = 1440
height = 900

play_audio = False
history_length = 8
event_history = deque(maxlen=history_length)


# --- Focus-restore, so typing lands where you're actually typing --------
#
# Real keystrokes go to whatever window has OS focus, which is normally
# whatever you last clicked into (a text box, say). But on window managers
# that use "focus follows mouse", just moving the cursor to aim at the
# next on-screen key -- which is real cursor movement over real screen
# coordinates, not a click -- can itself silently hand focus to whatever's
# now under the cursor, stealing it away from the field you were typing
# into. That's what made typing feel like it needed constant back-and-forth
# clicking between the text box and the keyboard: after a letter or two,
# aiming at the next key had already stolen focus elsewhere.
#
# The fix: remember the last window that had focus while the cursor was
# *not* hovering the on-screen keyboard (i.e. the window you actually
# clicked into), and force it back into the foreground immediately before
# every real keystroke, regardless of whatever's currently under the
# cursor. Implemented for Windows only for now (ctypes, like the rest of
# this codebase's platform-specific bits, e.g. mouse_control.execute_zoom)
# -- a no-op elsewhere, so this doesn't help avoid the same "focus follows
# mouse" issue on Linux/macOS yet, but also doesn't regress normal
# click-to-focus typing there either.
_target_hwnd = None

if sys.platform == 'win32':
	import ctypes
	from ctypes import wintypes

	_user32 = ctypes.windll.user32
	_kernel32 = ctypes.windll.kernel32

	# Explicit argtypes/restype for every WinAPI call used below. Without
	# these, ctypes assumes plain 32-bit ints for anything it isn't told
	# about -- which silently truncates HWNDs (real pointers, 64-bit on
	# 64-bit Windows) down to 32 bits. That can turn GetForegroundWindow()
	# into flat-out the wrong handle on a 64-bit process, which is exactly
	# the kind of thing that would make restore_focus() below flaky or
	# target the wrong window without ever raising a visible error.
	_user32.GetForegroundWindow.restype = wintypes.HWND
	_user32.SetForegroundWindow.argtypes = [wintypes.HWND]
	_user32.SetForegroundWindow.restype = wintypes.BOOL
	_user32.BringWindowToTop.argtypes = [wintypes.HWND]
	_user32.BringWindowToTop.restype = wintypes.BOOL
	_user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
	_user32.ShowWindow.restype = wintypes.BOOL
	_user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
	_user32.GetWindowThreadProcessId.restype = wintypes.DWORD
	_user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
	_user32.AttachThreadInput.restype = wintypes.BOOL
	_kernel32.GetCurrentThreadId.restype = wintypes.DWORD


def capture_focused_window():
	"""Call whenever the cursor is *not* over a keyboard key (see
	main_fast.py's main loop) -- remembers the real window you're actually
	typing into before it can get silently stolen. Best-effort: swallows
	any WinAPI oddity rather than ever letting it become an unhandled
	exception that kills the whole per-frame loop."""
	global _target_hwnd
	if sys.platform != 'win32':
		return
	try:
		_target_hwnd = _user32.GetForegroundWindow()
	except Exception as exc:
		print(f'[WARN] capture_focused_window() failed: {exc}')


def _open_camera(device, cap_width, cap_height):
	"""Open one camera device, sized and (on Windows) backended for speed.

	cv2.VideoCapture's default backend on Windows (MSMF) can take a couple
	of seconds just to enumerate/open a device; DirectShow (CAP_DSHOW) is
	usually noticeably faster to open, so it's worth requesting explicitly
	rather than leaving OpenCV to auto-pick. Other platforms don't have
	this particular slow-default problem, so they're left on the default
	backend (passing a Windows-only backend constant elsewhere would just
	error out)."""
	if sys.platform == 'win32':
		cap = cv2.VideoCapture(device, cv2.CAP_DSHOW)
	else:
		cap = cv2.VideoCapture(device)
	cap.set(cv2.CAP_PROP_FRAME_WIDTH, cap_width)
	cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cap_height)
	return cap


def restore_focus():
	"""Best-effort: put the remembered target window back in the OS
	foreground immediately before sending a real keystroke.

	A plain SetForegroundWindow() call here mostly didn't work: Windows
	deliberately restricts which processes are allowed to steal the
	foreground (its own anti-focus-stealing heuristic), and normally only
	lets the *current* foreground process hand focus to someone else --
	which we aren't, since our own windows are all NOACTIVATE and never
	become foreground themselves. The standard workaround is
	AttachThreadInput: temporarily joining our thread's input queue to the
	current foreground window's (and the target window's, if that's a
	different thread) makes Windows treat the SetForegroundWindow call as
	if it came from an already-foreground thread, which is what actually
	lets it take effect instead of silently no-op'ing (or just flashing
	the target's taskbar icon)."""
	if sys.platform != 'win32' or not _target_hwnd:
		return
	try:
		if _user32.GetForegroundWindow() == _target_hwnd:
			return  # already the foreground window -- nothing to do

		current_thread_id = _kernel32.GetCurrentThreadId()
		fg_hwnd = _user32.GetForegroundWindow()
		fg_thread_id = _user32.GetWindowThreadProcessId(fg_hwnd, None) if fg_hwnd else 0
		target_thread_id = _user32.GetWindowThreadProcessId(_target_hwnd, None)

		attached_fg = False
		attached_target = False
		if fg_thread_id and fg_thread_id != current_thread_id:
			attached_fg = bool(_user32.AttachThreadInput(current_thread_id, fg_thread_id, True))
		if target_thread_id and target_thread_id not in (current_thread_id, fg_thread_id):
			attached_target = bool(_user32.AttachThreadInput(current_thread_id, target_thread_id, True))

		try:
			_user32.ShowWindow(_target_hwnd, 9)  # SW_RESTORE, in case it's minimized
			_user32.SetForegroundWindow(_target_hwnd)
			_user32.BringWindowToTop(_target_hwnd)
		finally:
			if attached_fg:
				_user32.AttachThreadInput(current_thread_id, fg_thread_id, False)
			if attached_target:
				_user32.AttachThreadInput(current_thread_id, target_thread_id, False)
	except Exception as exc:
		print(f'[WARN] restore_focus() failed: {exc}')


# The 21 hand-landmark connections drawn for the debug video's hand
# skeleton -- the same topology mediapipe's own drawing_utils.HAND_CONNECTIONS
# uses (thumb/index/middle/ring/pinky chains off the wrist, plus the palm
# connections tying the finger bases together), just hardcoded here since
# we're drawing over plain landmark lists (the Tasks API's HandLandmarker
# output) rather than the legacy mp.solutions.hands proto type that
# draw_landmarks() expects.
_HAND_CONNECTIONS = [
	(0, 1), (1, 2), (2, 3), (3, 4),          # thumb
	(0, 5), (5, 6), (6, 7), (7, 8),          # index
	(5, 9), (9, 10), (10, 11), (11, 12),     # middle
	(9, 13), (13, 14), (14, 15), (15, 16),   # ring
	(13, 17), (17, 18), (18, 19), (19, 20),  # pinky
	(0, 17),                                 # palm base
]

# Debug-only: BGR-ish colors (fine either way round, both channels equal or
# distinct enough to read) used to trace each hand's skeleton and label its
# current gesture in the live debug video -- purely cosmetic, doesn't affect
# mouse/keyboard control at all.
_RIGHT_HAND_COLOR = (255, 210, 0)   # cyan-ish -- the mouse/keyboard hand
_LEFT_HAND_COLOR = (255, 0, 220)    # magenta-ish -- the zoom/paste hand


def draw_hand_debug_overlay(image, abs_landmark_list, label, color):
	"""Trace a hand's skeleton and label its current gesture directly onto
	`image` (mutated in place) -- shown in the --debug live camera window.
	Purely cosmetic: it has no effect on how gestures are recognized or
	acted on, only on what the debug window shows while they happen."""
	points = [(int(p[0]), int(p[1])) for p in abs_landmark_list]

	for start, end in _HAND_CONNECTIONS:
		cv2.line(image, points[start], points[end], color, 2)
	for x, y in points:
		cv2.circle(image, (x, y), 4, color, -1)

	if label:
		wrist_x, wrist_y = points[0]
		cv2.putText(
			image, label, (max(0, wrist_x - 40), wrist_y + 30),
			cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2, cv2.LINE_AA,
		)


def calc_landmark_list(image, landmarks):
	image_width, image_height = image.shape[1], image.shape[0]

	landmark_point = []

	# Keypoint
	# NOTE: `landmarks` is a plain list of NormalizedLandmark objects, as
	# returned per-hand by the HandLandmarker Tasks API (no `.landmark`
	# wrapper like the old `mp.solutions.hands` API used).
	for landmark in landmarks:
		landmark_x = min(int(landmark.x * image_width), image_width - 1)
		landmark_y = min(int(landmark.y * image_height), image_height - 1)
		landmark_z = landmark.z

		landmark_point.append([landmark_x, landmark_y, landmark_z])

	return landmark_point



def pre_process_landmark(landmark_list):

	# Work on a copy: this function mutates entries in place, and since
	# Python lists are passed by reference, mutating the caller's list
	# here would silently corrupt their `abs_landmark_list` (which needs
	# to stay in true image-pixel coordinates) into these wrist-relative
	# ones. That aliasing bug is what broke the keyboard's hit-testing.
	landmark_list = [point[:] for point in landmark_list]

	base_x, base_y = landmark_list[0][0], landmark_list[0][1]

	for i in range(len(landmark_list)):
		landmark_list[i][0] -= base_x
		landmark_list[i][1] -= base_y

	#maxval = max(max(x) for x in landmark_list)
	#minval = min(min(x) for x in landmark_list)

	#max_value = float(max(maxval, -minval))
	max_value = 1

	for i in range(len(landmark_list)):
		landmark_list[i][0] = float(landmark_list[i][0]) / max_value
		landmark_list[i][1] = float(landmark_list[i][1]) / max_value
	return landmark_list


def copy_or_cut_typed_buffer(typed_text, should_clear):
	"""Copy the keyboard's own typed-text buffer (the text after the '>'
	on the overlay) to the OS clipboard, and optionally clear it -- this
	is a separate, smaller scratchpad of what you've typed *here*,
	distinct from the 'Copy'/'Cut' keys which act on whatever's selected
	elsewhere on the desktop."""
	content = typed_text[1:] if typed_text.startswith('>') else typed_text
	pyperclip.copy(content)
	return '>' if should_clear else typed_text


def type_char(typed_char, typed_text, type_in_keyboard_area=False, shift_active=False):
	"""Handle one on-screen keyboard key, and return the updated local
	preview-text string shown on the overlay.

	`type_in_keyboard_area` decides where ordinary character keys, Space,
	Backspace, and Paste actually go. Always False now -- main_fast.py no
	longer exposes a Settings toggle for this (it was a confusing extra
	option; typing into whatever's really focused is what everyone
	actually wants) -- but the parameter and its True branch are kept
	rather than ripped out, since the behavior is still simple,
	self-contained, and easy to resurrect if that turns out wrong:

	- False (always, currently): a real keystroke is sent to whatever
	  window has OS focus -- exactly like a physical keyboard -- and the
	  overlay's own preview line is just an echo/log for feedback, not the
	  real destination.
	- True (unreachable via the UI right now): nothing is sent to the OS
	  at all; those keys only build up the overlay's own preview line,
	  which you then move elsewhere yourself with Copy Typed/Cut Typed.
	  This was the original behavior, before typing into the real focused
	  window existed at all.

	Copy/Cut always send their real hotkey regardless of this parameter --
	they act on the focused app's current selection, which there's no
	"keyboard area" equivalent for.

	`shift_active` (Shift held for one letter, or Caps Lock on) only
	affects letter keys (see keyboard.LETTER_CHARS) -- it decides whether
	the letter comes out upper- or lowercase, mirroring what's currently
	shown on the button (see overlay.py's draw()).

	Every branch that reaches the real OS calls restore_focus() first --
	see its docstring: aiming the cursor at this key may itself have just
	stolen OS focus away from whatever you're actually typing into, so
	it's put back immediately before the keystroke goes out.
	"""

	if typed_char == k.BACKSPACE:
		if not type_in_keyboard_area:
			restore_focus()
			pyautogui.press('backspace')
		return typed_text[:-1]

	if typed_char == 'Space':
		if not type_in_keyboard_area:
			restore_focus()
			pyautogui.press('space')
		return typed_text + ' '

	if typed_char == 'Enter':
		if not type_in_keyboard_area:
			restore_focus()
			pyautogui.press('enter')
		return typed_text + '\n'

	if typed_char == 'Tab':
		if not type_in_keyboard_area:
			restore_focus()
			pyautogui.press('tab')
		return typed_text + '\t'

	if typed_char == 'Select All':
		# Acts on the focused app's current content, same as Copy/Cut --
		# there's no "keyboard area" equivalent for it (nothing here has a
		# concept of "everything" to select), so it always sends the real
		# hotkey regardless of type_in_keyboard_area.
		restore_focus()
		if sys.platform == 'darwin':
			pyautogui.hotkey('command', 'a')
		else:
			pyautogui.hotkey('ctrl', 'a')
		return typed_text

	if typed_char == 'Clear':
		# Only clears our own preview line -- there's no general way to
		# clear whatever's focused elsewhere on the desktop.
		return ''

	if typed_char == 'Copy':
		# No way around simulating the real shortcut here -- only the
		# focused app knows what's currently selected, so it has to do the
		# actual copying into the OS clipboard itself.
		restore_focus()
		pyautogui.hotkey('ctrl', 'c')
		return typed_text

	if typed_char == 'Cut':
		restore_focus()
		pyautogui.hotkey('ctrl', 'x')
		return typed_text

	if typed_char == 'Copy Typed':
		return copy_or_cut_typed_buffer(typed_text, should_clear=False)

	if typed_char == 'Cut Typed':
		return copy_or_cut_typed_buffer(typed_text, should_clear=True)

	if typed_char == 'Paste':
		clipboard_text = pyperclip.paste()
		if not clipboard_text:
			return typed_text
		if type_in_keyboard_area:
			return typed_text + clipboard_text
		# Read the clipboard directly and type its contents as real
		# keystrokes, instead of simulating Ctrl+V -- this doesn't depend
		# on the focused app correctly intercepting the paste shortcut
		# (some apps use a different one, or can swallow/mishandle a
		# synthetic Ctrl+V), so it's more reliable across different apps.
		restore_focus()
		pyautogui.typewrite(clipboard_text)
		return typed_text

	if typed_char == 'Undo':
		restore_focus()
		if sys.platform == 'darwin':
			pyautogui.hotkey('command', 'z')
		else:
			pyautogui.hotkey('ctrl', 'z')
		return typed_text

	if typed_char == 'Redo':
		restore_focus()
		if sys.platform == 'darwin':
			pyautogui.hotkey('command', 'shift', 'z')
		else:
			pyautogui.hotkey('ctrl', 'y')
		return typed_text

	# Regular character key: a letter, digit, or symbol-page punctuation.
	# Letters respect shift_active for case; typewrite() (rather than
	# press()) is what makes uppercase/shifted-punctuation output actually
	# come out right, since it holds Shift itself for whichever characters
	# need it instead of us having to special-case each one.
	actual_char = typed_char
	if typed_char in k.LETTER_CHARS:
		actual_char = typed_char.upper() if shift_active else typed_char.lower()

	if not type_in_keyboard_area:
		restore_focus()
		pyautogui.typewrite(actual_char)

		if play_audio:
			k.say_key_pressed(actual_char)

	return typed_text + actual_char


def main(settings):

	mouse_sensitivity = settings['sensitivity']
	debug = settings['debug']

	mc.set_sensitivity_multiplier(mouse_sensitivity)
	mc.set_scroll_speed_multiplier(settings.get('scroll_speed', 1.0))
	mc.set_cursor_snappiness(settings.get('cursor_snappiness', 0.2))
	keyboard_scale = settings.get('keyboard_scale', 1.0)

	cap_width = width
	cap_height = height

	# camera_device resolution: an explicit setting always wins, and skips
	# probing entirely (straight to opening that one device, like the
	# program always did before the camera picker existed). Auto-pick
	# (the default) only probes when it actually needs to.
	cap_device = fw_settings.pick_camera_device(settings)
	# The raw setting (None means "Auto"), kept separate from `cap_device`
	# (the actual resolved index currently in use) so the Settings window
	# shows "Auto" rather than whichever index auto-pick happened to land
	# on, unless the user explicitly chose one.
	camera_device_setting = settings.get('camera_device')

	# On-screen keyboard keys always type into whatever's really focused,
	# like a physical keyboard -- see type_char()'s docstring. (There used
	# to be a Settings toggle to instead confine typing to the overlay's
	# own preview line; removed since typing into the real focused window
	# is what everyone actually wants, and it was just adding a confusing
	# extra option.)
	type_in_keyboard_area = False

	print(
		f'FingerWorks v{__version__} -- started '
		f'{datetime.datetime.now():%Y-%m-%d %H:%M:%S} '
		f'(screen {screenWidth}x{screenHeight}, camera {cap_device}, '
		f'mouse sensitivity {mouse_sensitivity}x, debug {"on" if debug else "off"})'
	)

	min_detection_confidence = c.MIN_DETECTION_CONFIDENCE
	min_tracking_confidence = c.MIN_TRACKING_CONFIDENCE

	# Camera (used only to feed the hand-tracking model -- no video window
	# is shown by default; the overlay panel and, in debug mode, the live
	# camera-feed window are the only things on screen besides whatever
	# else you're using your computer for).
	#
	# Opened on a background thread so it overlaps with loading the
	# hand-tracking model below instead of happening after it -- the two
	# are independent (one's a camera driver call, the other's reading a
	# model file off disk into memory), and each can take a couple of
	# seconds on its own, so doing them one after another was adding their
	# times together for no reason.
	_camera_result = {}

	def _open_camera_in_background():
		t0 = time.time()
		_camera_result['cap'] = _open_camera(cap_device, cap_width, cap_height)
		print(f'Camera opened in {time.time() - t0:.1f}s')

	camera_thread = threading.Thread(target=_open_camera_in_background, daemon=True)
	camera_thread.start()

	def reopen_camera(new_device):
		"""Swap the live camera device at runtime (Settings window ->
		Apply), without restarting the program. Keeps the old camera
		running if the new one fails to open, rather than leaving `cap`
		pointing at a dead device."""
		nonlocal cap
		new_cap = _open_camera(new_device, cap_width, cap_height)
		if not new_cap.isOpened():
			print(f'[WARN] Could not open camera {new_device}; keeping current camera.')
			new_cap.release()
			return False
		cap.release()
		cap = new_cap
		return True

	def handle_settings_changed(new_settings):
		nonlocal cap_device, camera_device_setting, button_list
		fw_settings.save_settings(new_settings)

		mc.set_sensitivity_multiplier(new_settings['sensitivity'])
		overlay.set_sensitivity(new_settings['sensitivity'])
		overlay.set_debug(new_settings['debug'])
		mc.set_scroll_speed_multiplier(new_settings.get('scroll_speed', 1.0))
		mc.set_cursor_snappiness(new_settings.get('cursor_snappiness', 0.2))

		overlay.set_keyboard_scale(new_settings.get('keyboard_scale', 1.0))
		# The keyboard's button layout is sized off the overlay panel's
		# pixel dimensions (see keyboard.get_button_list), so a keyboard-
		# size change needs it rebuilt against the new panel size -- same
		# as when the letters/symbols page toggles, just triggered from
		# here instead.
		button_list = k.get_button_list(overlay.panel_width, overlay.panel_height, page=keyboard_page)

		resolved_device = fw_settings.pick_camera_device(new_settings)
		if resolved_device != cap_device:
			if reopen_camera(resolved_device):
				cap_device = resolved_device
				camera_device_setting = new_settings['camera_device']
		else:
			camera_device_setting = new_settings['camera_device']

	def get_current_settings():
		return {
			'camera_device': camera_device_setting,
			'sensitivity': overlay.mouse_sensitivity,
			'debug': overlay.debug,
			'scroll_speed': mc.get_scroll_speed_multiplier(),
			'cursor_snappiness': mc.get_cursor_snappiness(),
			'keyboard_scale': overlay.keyboard_scale,
		}

	_startup_t0 = time.time()
	model_path = ensure_model_downloaded()

	base_options = BaseOptions(model_asset_path=model_path)
	options = HandLandmarkerOptions(
		base_options=base_options,
		running_mode=RunningMode.VIDEO,
		# Two hands: the right hand drives the mouse/keyboard as before,
		# and the left hand is free for the zoom gesture (see below) --
		# so the right hand isn't overloaded with yet another gesture to
		# distinguish from clicking/typing.
		num_hands=2,
		min_hand_detection_confidence=min_detection_confidence,
		min_hand_presence_confidence=min_detection_confidence,
		min_tracking_confidence=min_tracking_confidence,
	)
	landmarker = HandLandmarker.create_from_options(options)
	print(f'Hand-tracking model loaded in {time.time() - _startup_t0:.1f}s')

	# Now wait for the camera thread started above, if it hasn't already
	# finished (it usually has, since model loading above tends to take
	# longer than opening a camera).
	camera_thread.join()
	cap = _camera_result['cap']

	# detect_for_video requires monotonically increasing timestamps.
	start_time_ms = int(time.time() * 1000)

	event = ''
	control_state = 'Mouse'	# Mouse or Keyboard
	typed_text = '>'

	overlay = ov.Overlay(
		screenWidth, screenHeight, debug=debug, mouse_sensitivity=mouse_sensitivity,
		keyboard_scale=keyboard_scale,
		on_settings_changed=handle_settings_changed,
		get_settings=get_current_settings,
		get_available_cameras=fw_settings.list_cameras,
	)

	# Keyboard case/page state. 'letters' (QWERTY) or 'symbols'
	# (punctuation/math), toggled by the on-screen '123'/'ABC' key --
	# button_list is rebuilt from scratch on that toggle since the two
	# pages show different keys (see keyboard.get_button_list). shift_once
	# is a single-shot Shift (like a phone keyboard: capitalizes the next
	# letter, then clears itself); caps_lock stays on until toggled off.
	keyboard_page = 'letters'
	shift_once = False
	caps_lock = False

	# The keyboard's layout is sized to the overlay panel (fixed at
	# startup), not the camera frame -- rebuilt only when the page toggles,
	# not every frame.
	button_list = k.get_button_list(overlay.panel_width, overlay.panel_height, page=keyboard_page)

	try:
		while not overlay.should_quit:

			ret, image = cap.read()
			if not ret:
				break
			try:
				image = cv2.flip(image, 1)  # Mirror display

				frame_height, frame_width = image.shape[:2]

				image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

				if overlay.paused:
					# Skip hand detection/gesture processing entirely while
					# paused (saves the model's per-frame cost too) -- just
					# keep the UI responsive and, in debug mode, still show the
					# raw camera feed so it's clear the camera itself is still
					# working.
					overlay.draw(event, control_state, typed_text, button_list, shift_active=(shift_once or caps_lock))
					if overlay.debug:
						overlay.draw_video(image)
					overlay.pump()
					continue

				mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=image)
				timestamp_ms = int(time.time() * 1000) - start_time_ms
				results = landmarker.detect_for_video(mp_image, timestamp_ms)

				hand_debug_text = ''

				if results.hand_landmarks:

					# Which hand does what is strictly by hand identity --
					# right hand mouses/types, left hand zooms/pastes --
					# regardless of how many hands are in frame. This is
					# MediaPipe's own per-hand Left/Right classification
					# (each hand is classified independently of whether a
					# second hand is present, so there's no reason a single
					# visible hand should be treated any differently than
					# one of a pair); constants.SWAP_LABELED_HANDS flips it
					# wholesale if it's ever backwards for your camera setup.
					# A hand-rolled geometry-based classifier was tried
					# instead of trusting this label, and came out less
					# reliable, not more, so it's gone.
					debug_parts = []
					mouse_assigned = False

					for hand_idx, hand_landmarks in enumerate(results.hand_landmarks):
						abs_landmark_list = np.array(calc_landmark_list(image, hand_landmarks))
						rel_landmark_list = np.array(pre_process_landmark(abs_landmark_list.tolist()))

						# Normalize by this hand's own live size (wrist-to-
						# middle-knuckle pixel distance) before any gesture
						# is read off it, so the ratio cutoffs in
						# constants.py (FINGER_OUT_CUTOFF, LEFT_CLICK_CUTOFF,
						# RIGHT_CLICK_CUTOFF) work the same regardless of how
						# far this hand is from the camera -- see
						# mouse_control.normalize_landmarks().
						rel_landmark_list = mc.normalize_landmarks(
							rel_landmark_list, mc.hand_scale(abs_landmark_list),
						)

						raw_label = results.handedness[hand_idx][0].category_name
						if c.SWAP_LABELED_HANDS:
							raw_label = 'Left' if raw_label == 'Right' else 'Right'

						if raw_label == 'Left':
							zoom_event, zoom_debug_text = get_zoom_event(rel_landmark_list)
							if zoom_event == 'Zoom In':
								mc.execute_zoom('in')
								mc.set_zoomed(True)
								zoom_debug_text += ' -> sent zoom-in'
							elif zoom_event == 'Zoom Out':
								mc.execute_zoom('out')
								mc.set_zoomed(False)
								zoom_debug_text += ' -> sent zoom-out'

							paste_fired, paste_debug_text = get_paste_event(rel_landmark_list)
							if paste_fired:
								# "Scissors" pose (index + middle extended) --
								# the same shape as the right hand's Cut-Typed
								# gesture, but paste on this (left) hand: a
								# shortcut for the keyboard's 'Paste' key
								# without needing the keyboard open at all.
								typed_text = type_char('Paste', typed_text, type_in_keyboard_area)

							scroll_event, scroll_debug_text = get_scroll_event(rel_landmark_list)
							mc.execute_scroll(scroll_event)

							debug_parts.append(
								f'Left [Zoom: {zoom_debug_text}] [Paste: {paste_debug_text}] '
								f'[Scroll: {scroll_debug_text}]'
							)

							if overlay.debug:
								draw_hand_debug_overlay(
									image, abs_landmark_list,
									f'Zoom: {zoom_debug_text.split(" -> ")[0]}  '
									f'Paste: {paste_debug_text.split(" -> ")[0]}  '
									f'Scroll: {scroll_debug_text.split(" -> ")[0]}',
									_LEFT_HAND_COLOR,
								)

							continue

						# raw_label == 'Right'
						if mouse_assigned:
							# A second hand also read as 'Right' (shouldn't
							# normally happen) -- ignored rather than fighting
							# over the cursor with the hand already driving it.
							debug_parts.append('Right [ignored]')
							continue
						mouse_assigned = True
						# scale=NNN is the live wrist-to-knuckle pixel size
						# gesture cutoffs are normalized against this frame
						# (see mouse_control.hand_scale()) -- shown so
						# HAND_SCALE_TUNING_REFERENCE in constants.py can be
						# calibrated by reading this number off while your
						# hand is where things register reliably, instead of
						# guessing at it.
						debug_parts.append(
							f'Right [Mouse, scale={mc.hand_scale(abs_landmark_list):.0f}]'
						)

						event = get_event_fast(rel_landmark_list, control_state)

						event_history.append(event)

						if event == 'Keyboard On':
							control_state = 'Keyboard'
						elif event == 'Keyboard Off':
							control_state = 'Mouse'
						elif event == 'Quit':
							# The thumb+pinky gesture now pauses instead of
							# quitting outright (same as the control bar's
							# Pause button) -- quitting is reserved for the
							# explicit Quit button/Escape, so an accidental
							# gesture during normal use can't end the session.
							overlay.set_paused(True)
						elif event == 'Cut Typed Gesture':
							# Gesture shortcut for the 'Cut Typed' key: index +
							# middle extended ("scissors"), cutting the
							# keyboard's typed-text buffer without needing to
							# aim at that specific key.
							typed_text = copy_or_cut_typed_buffer(typed_text, should_clear=True)

						# Always drive the real OS cursor so it tracks your
						# finger in both modes (so it visually hovers over the
						# overlay's keys too). Whether the pinch also clicks
						# the real desktop is decided below, per-frame, rather
						# than solely by Mouse-vs-Keyboard mode -- so you can
						# still click things while the keyboard is open, as
						# long as you're not currently aiming at one of its
						# keys (see hit_button below).
						hit_button = None
						over_panel = False
						if control_state == 'Keyboard':
							mouse_screen_pos = pyautogui.position()
							button_list, typed_char, hit_button, over_panel = k.execute_event_keyboard(
								event, mouse_screen_pos, overlay.origin(),
								(overlay.panel_width, overlay.panel_height), button_list,
							)

							# Case/page keys are handled here rather than inside
							# type_char() -- they change local keyboard state
							# (which page is showing, whether Shift/Caps is on)
							# rather than sending anything to the OS or the
							# typed-text preview.
							if typed_char in ('123', 'ABC'):
								keyboard_page = 'symbols' if keyboard_page == 'letters' else 'letters'
								button_list = k.get_button_list(
									overlay.panel_width, overlay.panel_height, page=keyboard_page,
								)
							elif typed_char == 'Shift':
								shift_once = not shift_once
							elif typed_char == 'Caps':
								caps_lock = not caps_lock
								shift_once = False
							elif typed_char is not None:
								typed_text = type_char(
									typed_char, typed_text, type_in_keyboard_area,
									shift_active=(shift_once or caps_lock),
								)
								# Shift is single-shot (like a phone keyboard):
								# it capitalizes exactly the next letter, then
								# clears itself -- Caps Lock is unaffected and
								# stays on until toggled off explicitly.
								if shift_once:
									shift_once = False

						if not over_panel:
							# The cursor isn't anywhere over the keyboard panel
							# at all (whether because the keyboard isn't open,
							# or it is but you're pointing at something else on
							# the desktop) -- this is the real window you're
							# actually interacting with, so remember it as the
							# restore_focus() target (see its docstring at the
							# top of this file) before it can get silently
							# stolen by aiming at the next key.
							capture_focused_window()

						# Click the real desktop when in Mouse mode, or in
						# Keyboard mode as long as the cursor isn't anywhere
						# over the keyboard panel -- landing on one of its own
						# keys was already consumed above as a keypress instead
						# (not a real click), and landing on the panel's own
						# gray background between keys must do nothing at all,
						# not fall through to a real click on whatever's
						# visually behind this overrideredirect window (that
						# stray click was what deselected whatever text field
						# you were actually typing into).
						allow_click = (control_state == 'Mouse') or not over_panel

						execute_event_fast(
							event, abs_landmark_list, event_history,
							frame_width, frame_height,
							allow_click=allow_click,
						)

						if overlay.debug:
							draw_hand_debug_overlay(
								image, abs_landmark_list, event, _RIGHT_HAND_COLOR,
							)

					hand_debug_text = f'  [{", ".join(debug_parts)}]'

				# Persistently highlight Shift/Caps while toggled on, the same
				# way a phone keyboard does -- only when nothing else (hover/
				# press) is already claiming that button's color this frame,
				# so it doesn't fight the live hover/click feedback.
				for button in button_list:
					if button.color != 'idle':
						continue
					if (button.text == 'Shift' and shift_once) or (button.text == 'Caps' and caps_lock):
						button.color = 'active'

				# Debug aid: show which detected hand is doing what right next
				# to the current action, so you can see at a glance whether
				# it's routing your hands the way you expect (see
				# constants.SWAP_LABELED_HANDS if it isn't).
				overlay.draw(event + hand_debug_text, control_state, typed_text, button_list, shift_active=(shift_once or caps_lock))

				if overlay.debug:
					# Purely cosmetic: the live camera feed with each hand's
					# skeleton traced and its current gesture labeled, shown in
					# its own always-on-top debug window. `image` is already
					# RGB (converted above for MediaPipe) and now also carries
					# whatever skeleton/labels were drawn onto it above.
					overlay.draw_video(image)
				overlay.pump()
			except Exception as exc:
				# A single bad frame (a transient camera/model/OS-call
				# hiccup) is not worth crashing the whole program over --
				# and crashing here used to print a raw Python traceback
				# straight to this console window, which (via the console's
				# own mouse-selection/QuickEdit handling, combined with the
				# real OS clicks this program drives) was a plausible way for
				# that traceback text to end up copied onto the clipboard and
				# later typed out somewhere else entirely (e.g. Notepad) by a
				# stray Paste. Log it and skip to the next frame instead.
				print(f'[WARN] Skipping a frame due to an unexpected error: {exc}')
				continue

	finally:
		if is_zoomed_in():
			# Leave the OS screen magnifier back at its normal zoom level
			# rather than exiting mid-zoom -- otherwise the last thing
			# this program did stays in effect (a zoomed-in desktop) even
			# after it's no longer running to zoom back out for you.
			mc.execute_zoom('out')
			mc.set_zoomed(False)
		cap.release()
		overlay.close()
		landmarker.close()




if __name__ == '__main__':
	import argparse

	parser = argparse.ArgumentParser(description='FingerWorks -- touchless computer control via webcam.')
	parser.add_argument(
		'--sensitivity', type=float, default=None, metavar='MULTIPLIER',
		help=(
			'Mouse-speed multiplier. Defaults to whatever is saved in '
			'settings (1.0 the first time this is run); e.g. 1.5 moves the '
			'cursor faster, 0.5 slower. Overrides (and is then saved as) '
			'the settings-file value; also changeable at runtime from the '
			'Settings window.'
		),
	)
	parser.add_argument(
		'--debug', action='store_true', default=None,
		help=(
			'Show the debug overlay text (current event, mouse sensitivity, '
			'which hand is doing what, zoom/paste gesture state) plus a '
			'live camera window with each hand\'s skeleton traced and its '
			'gesture labeled, and keep the overlay panel visible at all '
			"times. Defaults to whatever is saved in settings (off the "
			'first time this is run). Overrides (and is then saved as) the '
			'settings-file value; also toggleable at runtime from the '
			'Settings window.'
		),
	)
	args = parser.parse_args()

	settings = fw_settings.load_settings()
	if args.sensitivity is not None:
		settings['sensitivity'] = args.sensitivity
	if args.debug is not None:
		settings['debug'] = args.debug

	main(settings)

